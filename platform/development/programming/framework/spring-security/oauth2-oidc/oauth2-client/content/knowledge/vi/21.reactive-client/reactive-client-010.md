# 21.10. Chọn authorized client hoặc registration theo từng request WebClient

## 1. Vì sao mỗi WebClient request phải chọn đúng OAuth2 client?

Trong ứng dụng **Spring Security OAuth 2.0 OIDC Client** xây dựng bằng **Spring WebFlux**, một `WebClient` có thể gọi nhiều Resource Server. Mỗi API có thể yêu cầu một Access Token được cấp cho **client registration**, **principal**, **audience** và **scope** khác nhau.

Ví dụ, một portal cho nhân viên đăng nhập bằng OIDC, đồng thời có job backend đọc số liệu hệ thống:

~~~text
                      +-- Reports API:
                      |    delegated user Access Token
Browser -> WebFlux ---+
                      +-- Billing API:
                      |    delegated user Access Token khác
                      |
Scheduled worker ------+-- Metrics API:
                           Client Credentials Access Token
~~~

Ba HTTP requests đều cần `Authorization: Bearer ...`, nhưng **không được dùng một token cho mọi API**. Token của nhân viên Alice không được nhầm với token của Bob; token của Metrics API không tự được Reports API chấp nhận; và Client Credentials token của backend không tự đại diện cho end-user.

Spring Security giúp chọn credential cho **từng outbound request** qua `ServerOAuth2AuthorizedClientExchangeFilterFunction`. Hai lựa chọn trọng tâm:

1. **Chỉ định một `OAuth2AuthorizedClient` đã có:** dùng request attribute `oauth2AuthorizedClient(authorizedClient)`.
2. **Chỉ định tên registration:** dùng request attribute `clientRegistrationId("registration-name")`, để `ReactiveOAuth2AuthorizedClientManager` tìm, cấp mới hoặc refresh authorized client phù hợp.

Tuy nhìn giống nhau ở việc cuối cùng WebClient gửi Bearer Token, hai cách thể hiện **ý định khác nhau**: chọn một *kết quả ủy quyền cụ thể* hoặc chọn một *cấu hình OAuth2 client* rồi nhờ manager xử lý vòng đời token.

### Kết quả cần đạt

Sau bài này, người học có thể:

- Giải thích khác nhau giữa `ClientRegistration`, `OAuth2AuthorizedClient` và `Authentication`.
- Cấu hình `ServerOAuth2AuthorizedClientExchangeFilterFunction` trên WebClient Reactive.
- Chọn authorized client trực tiếp hoặc chọn registration theo từng request, không làm rò token giữa người dùng.
- Phân biệt `DefaultReactiveOAuth2AuthorizedClientManager` và `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.
- Thiết kế request dành cho **OIDC user delegated token** và **Client Credentials service token**.
- Nhận biết rủi ro khi bật `setDefaultOAuth2AuthorizedClient(true)`, `setDefaultClientRegistrationId(...)`, hoặc cho người dùng chọn URL/registration tùy ý.
- Xử lý token hết hạn, lỗi OAuth2 và HTTP 401/403 theo đúng trách nhiệm của client và Resource Server.

> **Phạm vi:** Spring WebFlux server/reactive OAuth2 Client với `ReactiveOAuth2AuthorizedClientManager` và `ServerOAuth2AuthorizedClientExchangeFilterFunction`. Đây **không** phải `ServletOAuth2AuthorizedClientExchangeFilterFunction` dùng trong ứng dụng Servlet/MVC.

## 2. Các thành phần tham gia

### 2.1. Cấu hình khác kết quả cấp quyền

| Thành phần | Chứa gì? | Tác dụng |
| --- | --- | --- |
| `ClientRegistration` | `registrationId`, client ID, client authentication method, grant type, token URI, scopes, redirect URI... | Định nghĩa **cách client được cấp token** |
| `OAuth2AuthorizedClient` | `ClientRegistration`, `principalName`, Access Token, Refresh Token nếu có | Ghi nhận **một lần client đã được ủy quyền** cho principal |
| `ReactiveClientRegistrationRepository` | Các `ClientRegistration` | Tìm cấu hình qua registration ID |
| `ServerOAuth2AuthorizedClientRepository` | Authorized client gắn ngữ cảnh `ServerWebExchange`, Authentication | Lưu/tải/xóa trong luồng reactive web |
| `ReactiveOAuth2AuthorizedClientService` | Authorized client theo `registrationId + principalName` | Lưu/tải/xóa không cần một HTTP exchange |
| `ReactiveOAuth2AuthorizedClientManager` | Điều phối provider, load/save token, authorization/re-authorization | Trả về authorized client phù hợp |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | WebClient filter dùng authorized client/manager | Gắn `Authorization: Bearer ...` vào outbound request |
| `Resource Server` | API có authorization policy riêng | Xác minh token và quyết định có chấp nhận HTTP request không |

Ví dụ:

~~~text
ClientRegistration:
  registrationId = company-oidc
  clientId = portal-reactive
  authorizationGrantType = authorization_code

OAuth2AuthorizedClient A:
  registrationId = company-oidc
  principalName = alice
  accessToken = <TOKEN_ALICE>

OAuth2AuthorizedClient B:
  registrationId = company-oidc
  principalName = bob
  accessToken = <TOKEN_BOB>
~~~

**Registration ID không phải tên người dùng.** Một registration có thể cấp token cho nhiều principal; khóa logic của service store thường là cặp `(clientRegistrationId, principalName)`.

### 2.2. ID Token, Access Token và Refresh Token

Với OIDC Login:

- **ID Token** chứng minh thông tin xác thực OIDC cho client theo issuer, audience, thời hạn và các kiểm tra liên quan.
- **Access Token** dành để truy cập tài nguyên được ủy quyền; filter dùng nó làm Bearer Token khi gọi API.
- **Refresh Token**, khi được cấp, dùng để xin Access Token mới tại Token Endpoint; không gửi cho Resource Server.

Không dùng `OidcUser.getIdToken().getTokenValue()` làm `Authorization: Bearer` để gọi một API chỉ vì ID Token cũng có thể là JWT.

Với Client Credentials, token đại diện cho **service/client identity**, không phải người dùng đăng nhập OIDC; thường không có ID Token của end-user.

## 3. Dòng chảy chọn token cho từng request

~~~mermaid
flowchart TD
    A["Code nghiệp vụ tạo WebClient request"] --> B["Request attributes có OAuth2AuthorizedClient?"]
    B -->|Có| C["Chọn authorized client cụ thể"]
    B -->|Không| D["Có clientRegistrationId?"]
    D -->|Có| E["Chọn cấu hình ClientRegistration"]
    D -->|Không| F["Xem default client policy nếu đã cấu hình"]
    C --> G["ReactiveOAuth2AuthorizedClientManager"]
    E --> G
    F --> G
    G --> H["Tìm authorized client theo registration/principal"]
    H --> I{"Đã có token dùng được?"}
    I -->|Có| J["Tái sử dụng token"]
    I -->|Chưa có / cần làm mới| K["AuthorizedClientProvider cấp/refresh"]
    K --> L["Lưu authorized client mới"]
    L --> J
    J --> M["WebClient filter gắn Bearer Access Token"]
    M --> N["Gọi đúng Resource Server"]
    N --> O["API thực thi token validation + authorization"]
~~~

Đây là mô hình logic. **Không nhất thiết mỗi lần gọi manager đều tạo token mới**. Tùy provider và grant, manager có thể tái sử dụng bản ghi, xin token mới, refresh hoặc không thể authorize trong ngữ cảnh hiện tại.

### 3.1. Request attributes không tự gửi ra Internet

Khi viết:

~~~java
.attributes(clientRegistrationId("reports-api"))
~~~

giá trị được lưu trong **attributes nội bộ của WebClient `ClientRequest`** để filter đọc. Nó không tự được đưa vào URL, JSON request body hoặc HTTP header gửi đến Resource Server.

Điều này giúp request chọn client mà không tự thêm Bearer Token bằng string. Tuy nhiên, nếu application lấy giá trị registration từ query parameter của browser rồi truyền thẳng vào attributes, vấn đề **ủy quyền lựa chọn token** vẫn tồn tại. Request attribute là công cụ lập trình, không phải cơ chế kiểm soát quyền.

## 4. Gắn ServerOAuth2AuthorizedClientExchangeFilterFunction vào WebClient

### 4.1. Đúng class trên Reactive server

Import:

~~~java
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;
~~~

Tạo filter:

~~~java
ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServerOAuth2AuthorizedClientExchangeFilterFunction(
        authorizedClientManager);

WebClient webClient = WebClient.builder()
    .filter(oauth2)
    .build();
~~~

Ở đây, `authorizedClientManager` là một **`ReactiveOAuth2AuthorizedClientManager`** được cung cấp bởi Spring hoặc do ứng dụng cấu hình. Filter chạy ở outbound HTTP client layer; manager thực hiện phần authorized client lifecycle.

### 4.2. Bean WebClient trong Spring Configuration

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ResourceApiWebClientConfig {

    @Bean
    WebClient resourceApiWebClient(
            ReactiveOAuth2AuthorizedClientManager authorizedClientManager) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                authorizedClientManager);

        return WebClient.builder()
            .baseUrl("https://api.example.net")
            .filter(oauth2)
            .build();
    }
}
~~~

Chỉ tạo bean chưa đủ để mọi request nhận đúng token: request vẫn cần `OAuth2AuthorizedClient`, `clientRegistrationId` hoặc một default được cấu hình **có chủ đích**, cùng principal context phù hợp.

### 4.3. Cách khởi tạo qua repositories

Filter còn có constructor nhận:

~~~java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    clientRegistrationRepository,
    authorizedClientRepository);
~~~

Trong đó:

- `clientRegistrationRepository` là `ReactiveClientRegistrationRepository`.
- `authorizedClientRepository` là `ServerOAuth2AuthorizedClientRepository`.

Constructor này được dùng khi muốn để filter phối hợp với cơ chế manager dựa trên repository. Nếu ứng dụng đã cần custom provider, grant, failure handler hoặc store, constructor **nhận manager** cho phép cấu hình tập trung hơn.

**Khác biệt dễ bỏ sót:** constructor nhận repository có thể được cấu hình sẵn handler loại bỏ authorized client khi Resource Server báo OAuth2 Bearer error phù hợp; constructor nhận `ReactiveOAuth2AuthorizedClientManager` **không tự động cài** handler này. Phần 15 trình bày hậu quả và hướng thiết lập.

## 5. Cách 1 — Chọn một OAuth2AuthorizedClient cụ thể

### 5.1. Static helper oauth2AuthorizedClient(...)

Spring Security cung cấp:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;
~~~

Sau khi đã có `OAuth2AuthorizedClient` đúng principal và registration:

~~~java
Mono<String> response = webClient.get()
    .uri("/v1/profile")
    .attributes(oauth2AuthorizedClient(authorizedClient))
    .retrieve()
    .bodyToMono(String.class);
~~~

**Ý nghĩa:** yêu cầu HTTP này nên dùng **đúng authorized client** mà code đã lựa chọn. Không cần chỉ định lại string registration ID trong cùng request chỉ để nói cùng một điều.

Đối tượng `authorizedClient` phải được lấy từ một nguồn đáng tin cậy trong backend, chẳng hạn authorized client repository/service hoặc argument resolver của Spring Security. Không tạo nó bằng Access Token do browser tự gửi rồi gắn vào principal tùy ý.

### 5.2. Khi nào cách này thích hợp?

Ví dụ:

- Controller đã được inject authorized client của registration cố định cho người dùng hiện tại.
- Application cần chọn một kết nối OAuth2 cụ thể trong số các integration đã được user cấp quyền.
- Một service vừa tải authorized client bằng principal đã xác minh.
- Cần gửi chính xác client được cấp quyền với các scopes của một workflow.

Ưu điểm: ý định rõ, ít phải dựa vào giá trị mặc định hoặc tên registration trong nhiều lớp.

Điểm cần chú ý: **OAuth2AuthorizedClient không nên được lưu trong field singleton** để tái sử dụng cho mọi users. Đối tượng chứa credential có vòng đời, principal và scope; nó có thể stale hoặc thuộc tài khoản khác.

### 5.3. Ví dụ lấy authorized client từ reactive service

`ReactiveOAuth2AuthorizedClientService` có API dạng reactive:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import reactor.core.publisher.Mono;

Mono<OAuth2AuthorizedClient> selected =
    authorizedClientService.loadAuthorizedClient(
        "company", principalName);
~~~

Sau đó dùng nó trong chain:

~~~java
return authorizedClientService
    .<OAuth2AuthorizedClient>loadAuthorizedClient(
        "company", currentPrincipalName)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("Chưa có OAuth2 authorized client")))
    .flatMap(client -> webClient.get()
        .uri("/v1/profile")
        .attributes(oauth2AuthorizedClient(client))
        .retrieve()
        .bodyToMono(String.class));
~~~

Đây là ví dụ **minh họa cấu trúc**; giả định `authorizedClientService`, `webClient` và `currentPrincipalName` đã được tạo/xác định server-side. Không dùng principal name do browser tùy ý gửi.

**Phân biệt:** việc `loadAuthorizedClient(...)` trả về một record chỉ chứng minh bản ghi đã tồn tại, không chứng minh Access Token đang còn hợp lệ với Resource Server. Filter/manager và API còn chịu trách nhiệm vòng đời token và authorization; không nên tự bỏ qua chúng.

### 5.4. Không gắn cả authorized client và registration theo kiểu “chọn một trong hai”

Phản ví dụ về ý định không rõ:

~~~java
webClient.get()
    .uri("/v1/profile")
    .attributes(oauth2AuthorizedClient(alicesClient))
    .attributes(clientRegistrationId("billing-service"))
    .retrieve();
~~~

Ở đây code vừa truyền một authorized client của Alice, vừa chỉ định billing registration. **Không dựa vào thứ tự/ưu tiên nội bộ của filter để xử lý mâu thuẫn này.** Một request nên có **một chiến lược lựa chọn client rõ ràng**; tránh để các tầng service/tracing/filters thêm attributes trái nhau.

## 6. Cách 2 — Chọn clientRegistrationId cho từng request

### 6.1. Static helper clientRegistrationId(...)

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;
~~~

Ví dụ:

~~~java
Mono<String> response = webClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("reports-api"))
    .retrieve()
    .bodyToMono(String.class);
~~~

Filter nhận `reports-api`, manager tìm `ClientRegistration` có registration ID đó, rồi tải hoặc cấp `OAuth2AuthorizedClient` cho principal tương ứng.

### 6.2. Lợi ích của chọn registration

Một lần WebClient call không cần biết token value, token expiry hoặc Refresh Token. Nó chỉ nêu:

> “Request này cần quyền thông qua registration `reports-api`.”

Manager có thể:

1. Tìm authorized client đã lưu với `registrationId + principalName`.
2. Dùng lại Access Token nếu phù hợp.
3. Refresh Access Token nếu grant và Refresh Token cho phép.
4. Thực hiện Client Credentials grant để xin token mới cho machine client.
5. Lưu `OAuth2AuthorizedClient` mới theo policy.

Không có bảo đảm rằng mọi registration đều có thể authorize trong mọi ngữ cảnh. Ví dụ Authorization Code flow cần browser/authorization context; một scheduled job không thể tự đi qua consent redirect của người dùng.

### 6.3. Chọn giữa nhiều registrations

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-api:
            provider: company-auth
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: [reports.read]
          billing-api:
            provider: company-auth
            client-id: ${BILLING_CLIENT_ID}
            client-secret: ${BILLING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: [billing.read]
        provider:
          company-auth:
            token-uri: https://auth.example.net/oauth2/token
~~~

Gọi đúng API tương ứng:

~~~java
Mono<String> reports = webClient.get()
    .uri("https://reports.example.net/v1/reports")
    .attributes(clientRegistrationId("reports-api"))
    .retrieve()
    .bodyToMono(String.class);

Mono<String> invoices = webClient.get()
    .uri("https://billing.example.net/v1/invoices")
    .attributes(clientRegistrationId("billing-api"))
    .retrieve()
    .bodyToMono(String.class);
~~~

Hai đoạn giả định manager/provider có thể cấp Client Credentials token và có **principal context**. Cấu hình này có hai registrations độc lập, không phải một client ID mặc nhiên có quyền mọi API.

**Không nên dùng một WebClient chung cho arbitrary hosts** chỉ vì có thể chọn registration theo request. Với API nhạy cảm, dùng WebClient chuyên dụng với cố định destination và registration mapping server-side.

### 6.4. registrationId không phải provider ID

Trong YAML:

~~~yaml
registration:
  reports-api:
    provider: company-auth
provider:
  company-auth:
    token-uri: https://auth.example.net/oauth2/token
~~~

`reports-api` là **registrationId** dùng trong `clientRegistrationId(...)`. `company-auth` là **provider configuration ID**. Nhầm hai tên có thể khiến manager không tìm thấy registration hoặc không lấy token đúng.

## 7. Nên chọn authorized client hay registration?

| Tình huống | Nên chọn | Giải thích |
| --- | --- | --- |
| Controller đã nhận đúng `OAuth2AuthorizedClient` qua annotation/resolver | `oauth2AuthorizedClient(client)` | Dùng rõ kết quả ủy quyền của principal hiện tại |
| Service muốn manager chủ động tìm/cấp/refresh token theo registration | `clientRegistrationId("id")` | Chỉ định cấu hình client, không truyền token object |
| Background job dùng Client Credentials | `clientRegistrationId("service-id")` kèm service principal | Manager xin/tái sử dụng machine token |
| App có nhiều integrations đã được user cấp quyền | Tùy kiến trúc, nhưng chọn đúng authorized client/registration đã được phép | Tránh nhầm token giữa provider/tenant |
| Request tới API không cần OAuth2 | **Không chọn OAuth2 client** | Không phát Bearer Token vô cớ |
| HTTP request đến URL do user quyết định | Không dùng WebClient có credential nếu chưa qua policy | Ngăn SSRF và lộ Access Token |

### 7.1. Cây quyết định

~~~mermaid
flowchart TD
    A["Outbound API cần OAuth2 Access Token?"] -->|Không| B["Dùng WebClient không gắn OAuth2 filter"]
    A -->|Có| C{"Đã có authorized client được chọn tin cậy?"}
    C -->|Có| D["attributes(oauth2AuthorizedClient(client))"]
    C -->|Chưa| E{"Có registrationId được phép?"}
    E -->|Có| F["attributes(clientRegistrationId(id))"]
    E -->|Không| G["Từ chối/thiếu cấu hình; không đoán token quyền cao"]
    D --> H["Kiểm tra principal, Resource Server, scope"]
    F --> H
    H --> I["Manager + filter -> Bearer Token"]
~~~

### 7.2. Explicit selection thường an toàn hơn default

Một request ghi rõ `clientRegistrationId(...)` hoặc `oauth2AuthorizedClient(...)` cho người đọc code thấy **vì sao** có Bearer Token. Nếu bật default cho WebClient dùng nhiều nhiệm vụ, developer khác có thể thêm API call vô tình mang token.

Sự minh bạch của request attribute không thay thế authorization logic, nhưng nó giảm nguy cơ **credential bất ngờ xuất hiện** trên một request vốn không cần OAuth2.

## 8. Cấu hình project WebFlux/OIDC

### 8.1. Dependencies

Ví dụ Gradle trong Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Trong các nhánh Spring Boot mới, starter names có thể được modular hóa; chọn dependency theo BOM của phiên bản Boot mà dự án đang dùng. Ví dụ bên dưới dùng các API Spring Security Reactive OAuth2 Client hiện hành theo cách tiếp cận phổ biến ở Spring Security 6.x.

### 8.2. OIDC registration để đăng nhập người dùng

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
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - reports.read
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

Đây là giá trị minh họa. OIDC Provider thật phải có issuer, redirect URI được đăng ký và scopes phù hợp; secret được cung cấp qua môi trường/secret manager thay vì commit vào source.

**Không mặc định `reports.read` là một OIDC standard scope**. Đây là ví dụ quyền tùy API/Authorization Server; token được cấp còn phải phù hợp audience/resource của Reports API.

### 8.3. SecurityWebFilterChain

~~~java
package com.example.security;

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
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
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

`oauth2Login()` xử lý browser OIDC login; `oauth2Client()` cấu hình phần OAuth2 Client cho Reactive server. Code gọi Resource Server phải dùng **Access Token của OAuth2 client**, không lấy ID Token từ OIDC principal để gửi làm Bearer.

## 9. Reactive manager cho token của user trong WebFlux request

### 9.1. DefaultReactiveOAuth2AuthorizedClientManager

Manager thường dùng trong **WebFlux request** nhận:

~~~java
DefaultReactiveOAuth2AuthorizedClientManager manager =
    new DefaultReactiveOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        authorizedClientRepository);
~~~

Trong đó:

- `clientRegistrationRepository` là `ReactiveClientRegistrationRepository`.
- `authorizedClientRepository` là `ServerOAuth2AuthorizedClientRepository`.

Manager có thể tải/lưu authorized clients với `ServerWebExchange` và Authentication. Nó phù hợp cho OAuth2 Login delegated user flow, bao gồm Refresh Token grant khi provider cấp token phù hợp.

### 9.2. Cấu hình manager tường minh

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
public class UserAuthorizedClientManagerConfig {

    @Bean
    ReactiveOAuth2AuthorizedClientManager userAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultReactiveOAuth2AuthorizedClientManager manager =
            new DefaultReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Đây là ví dụ **cấu hình tường minh**. Nếu Spring Boot/Spring Security đã cung cấp manager phù hợp, không cần tạo bean trùng hoặc vô tình thay đổi authorized client repository mà login đang dùng.

### 9.3. Gắn WebClient filter vào user manager

~~~java
package com.example.security;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReportsWebClientConfig {

    @Bean
    WebClient userReportsWebClient(
            @Qualifier("userAuthorizedClientManager")
            ReactiveOAuth2AuthorizedClientManager manager) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

        return WebClient.builder()
            .baseUrl("https://reports.example.net")
            .filter(oauth2)
            .build();
    }
}
~~~

Nếu application chỉ có một manager bean thì qualifier có thể không cần. Nếu có cả **user manager** và **machine manager**, nên dùng bean name/qualifier rõ ràng để không inject nhầm manager với các grant/store khác nhau.

### 9.4. Code gọi API chọn registration của user

~~~java
package com.example.reports;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class UserReportsGateway {

    private final WebClient userReportsWebClient;

    public UserReportsGateway(WebClient userReportsWebClient) {
        this.userReportsWebClient = userReportsWebClient;
    }

    public Mono<String> loadMyReports() {
        return userReportsWebClient.get()
            .uri("/v1/me/reports")
            .attributes(clientRegistrationId("company"))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

Đoạn này giả định request nằm trong WebFlux authentication context của user đã login. Filter/manager phải tìm đúng Authentication và authorized client của `company`. Nếu API đòi token cho audience khác với Access Token mà OP cấp, phải sửa tích hợp/registration/resource request theo hợp đồng, không dùng ID Token để thay thế.

## 10. Chọn OAuth2AuthorizedClient trực tiếp trong Reactive Controller

Trong một số WebFlux applications, Spring Security hỗ trợ `@RegisteredOAuth2AuthorizedClient` để resolve authorized client của registration cụ thể.

Ví dụ controller:

~~~java
package com.example.web;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@RestController
public class UserProfileController {

    private final WebClient userReportsWebClient;

    public UserProfileController(WebClient userReportsWebClient) {
        this.userReportsWebClient = userReportsWebClient;
    }

    @GetMapping("/profile/remote")
    public Mono<String> remoteProfile(
            @RegisteredOAuth2AuthorizedClient("company")
            OAuth2AuthorizedClient authorizedClient) {

        return userReportsWebClient.get()
            .uri("/v1/me")
            .attributes(oauth2AuthorizedClient(authorizedClient))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

Ở đây:

1. Spring Security resolve authorized client của registration `company` trong ngữ cảnh người dùng đang đăng nhập.
2. Controller gửi trực tiếp authorized client đó vào request attribute.
3. WebClient filter dùng authorized client phù hợp để gửi Access Token.

**Không serialize `authorizedClient` hoặc `authorizedClient.getAccessToken().getTokenValue()` vào body trả cho browser.** Controller chỉ trả dữ liệu API sau khi áp dụng privacy/authorization rules.

Lưu ý: cách resolve authorized client qua annotation và việc manager refresh có thể phụ thuộc cấu hình/phiên bản. Nếu muốn một workflow luôn chủ động re-authorize, cần đảm bảo manager/provider/store đang được dùng đúng; **đừng giữ một authorized client cũ trong singleton qua nhiều requests**.

### 10.1. Chọn đúng client khi có nhiều registration user-facing

Giả sử một user đăng nhập bằng `company`, sau đó liên kết thêm tài khoản `calendar`. Controller có thể nhận authorized client của calendar nếu ứng dụng đã có luồng cấp quyền phù hợp:

~~~java
@GetMapping("/calendar/events")
public Mono<String> events(
        @RegisteredOAuth2AuthorizedClient("calendar")
        OAuth2AuthorizedClient calendarClient) {
    return calendarWebClient.get()
        .uri("/events")
        .attributes(oauth2AuthorizedClient(calendarClient))
        .retrieve()
        .bodyToMono(String.class);
}
~~~

Đây là **method minh họa**; giả định có `calendarWebClient`, import cùng ví dụ trên và registration `calendar` đã được cấu hình. Nếu user chưa cấp quyền, không được lấy một token của provider khác rồi gửi sang Calendar API.

## 11. Chọn Authentication/principal một cách tường minh

### 11.1. Principal quyết định authorized-client ownership

Với service store:

~~~text
(company, alice) -> OAuth2AuthorizedClient for Alice
(company, bob)   -> OAuth2AuthorizedClient for Bob
~~~

Nếu gọi manager với sai principal, code có thể không tìm được token hoặc nguy hiểm hơn là **truy cập token gắn với người khác** nếu application cho phép tự chỉ định principal name.

Trong WebFlux, Authentication thường được truyền qua **Reactor Context** do Spring Security quản lý, không phải dựa vào `ThreadLocal` theo cách Servlet.

### 11.2. Mặc định trong request đã authenticated

Trong một reactive controller đã được bảo vệ:

~~~java
@GetMapping("/my-reports")
public Mono<String> myReports() {
    return userReportsWebClient.get()
        .uri("/v1/me/reports")
        .attributes(clientRegistrationId("company"))
        .retrieve()
        .bodyToMono(String.class);
}
~~~

Filter có thể lấy Authentication từ reactive security context trong chuỗi request. Không cần tự xây một Authentication từ email/query parameter.

### 11.3. Request attribute authentication(...)

Khi cần truyền Authentication được xác minh một cách tường minh:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.authentication;
~~~

Ví dụ:

~~~java
Mono<String> result = webClient.get()
    .uri("/v1/me/reports")
    .attributes(clientRegistrationId("company"))
    .attributes(authentication(authenticationFromReactiveSecurity))
    .retrieve()
    .bodyToMono(String.class);
~~~

`authenticationFromReactiveSecurity` phải là một `Authentication` từ nguồn server-side đã tin cậy. Dùng request attribute không khiến một Authentication tự tạo trở thành bằng chứng xác thực hợp lệ của người dùng.

### 11.4. Nếu cần lấy SecurityContext bên trong reactive service

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

Mono<String> result =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("Không có authentication context")))
        .flatMap(authentication -> webClient.get()
            .uri("/v1/me/reports")
            .attributes(clientRegistrationId("company"))
            .attributes(
                ServerOAuth2AuthorizedClientExchangeFilterFunction.authentication(
                    authentication))
            .retrieve()
            .bodyToMono(String.class));
~~~

Đây là ví dụ về **truyền context tường minh**. Trong request thông thường, filter có thể tự giải quyết authentication; đừng thêm code phức tạp khi không cần.

### 11.5. Không dùng SecurityContextHolder của Servlet để lựa chọn user trong WebFlux

Phản ví dụ:

~~~java
// KHÔNG DÙNG làm mặc định cho Reactive WebFlux:
Authentication auth = SecurityContextHolder.getContext()
    .getAuthentication();
~~~

Reactor có thể chuyển qua nhiều threads. WebFlux security dùng **Reactor Context**, không đảm bảo một `ThreadLocal` từ request thread luôn có trên thread thực thi HTTP client. Dùng `ReactiveSecurityContextHolder` hoặc request attribute hợp lệ.

## 12. ServerWebExchange và việc chọn token theo web session

### 12.1. Khi manager cần ServerWebExchange

`DefaultReactiveOAuth2AuthorizedClientManager` sử dụng `ServerOAuth2AuthorizedClientRepository`. Repository có thể cần `ServerWebExchange` để truy cập WebSession hoặc những thông tin ngữ cảnh của request.

Trong WebFlux request, filter/manager có thể giải quyết exchange từ reactive context do Spring Security tổ chức. Với mã đặc biệt, có thể truyền exchange tường minh:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.serverWebExchange;
~~~

Ví dụ:

~~~java
return webClient.get()
    .uri("/v1/me/reports")
    .attributes(clientRegistrationId("company"))
    .attributes(serverWebExchange(exchange))
    .retrieve()
    .bodyToMono(String.class);
~~~

`exchange` là một `ServerWebExchange` thực sự của request hiện tại, được truyền vào controller/service bởi WebFlux. Không lưu exchange vào singleton hoặc queue để tái sử dụng sau khi request kết thúc.

### 12.2. Tạo Mono trong request, subscribe ngoài request

Một lỗi thường gặp:

~~~text
HTTP request /reports
  -> tạo Mono của WebClient
  -> đẩy Mono sang task queue
  -> request kết thúc
  -> Mono được subscribe sau trên thread khác
  -> thiếu Authentication hoặc ServerWebExchange
~~~

Trong Reactive program, HTTP call thường bắt đầu khi **subscribe**. Không nên cho rằng tạo một Mono bên trong controller sẽ khiến mọi context của controller tồn tại vĩnh viễn.

Nếu workflow thực sự phải chạy ngoài web request:

- Xác định việc sử dụng token sau request có được user cho phép không.
- Lưu authorized client một cách bảo mật với stable principal identity khi cần.
- Cân nhắc **`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`** thay manager phụ thuộc web exchange.
- Không mang theo một `ServerWebExchange` đã hết vòng đời.

### 12.3. WebSession hết hạn và authorized client

Nếu repository gắn dữ liệu vào session, token có thể không còn truy xuất sau session timeout hoặc session invalidation. Nếu authorized client dùng persistent service store, dữ liệu có thể còn sau khi user logout tùy chính sách.

**Logout user không mặc định có nghĩa mọi Access Token/Refresh Token trong database đã bị revoke.** Token revocation là trách nhiệm riêng khi sản phẩm cần ngắt quyền.

## 13. Client Credentials: registration theo request, principal application-level

Một worker backend không có end-user authentication thường dùng **Client Credentials** để gọi API:

~~~text
report-sync service
   -> client_credentials grant
   -> Access Token của service
   -> Reports API
~~~

Không có user authorization-code redirect, ID Token của người dùng hoặc browser session.

### 13.1. YAML cho registration machine-to-machine

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          report-sync:
            provider: internal-auth
            client-id: ${REPORT_SYNC_CLIENT_ID}
            client-secret: ${REPORT_SYNC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          internal-auth:
            token-uri: https://auth.example.net/oauth2/token
~~~

Không yêu cầu `redirect-uri`, `state`, PKCE hay `nonce` cho Client Credentials grant cơ bản.

### 13.2. AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager

Manager ngoài web exchange:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
public class MachineClientManagerConfig {

    @Bean
    AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
            machineAuthorizedClientManager(
                    ReactiveClientRegistrationRepository registrations,
                    ReactiveOAuth2AuthorizedClientService authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Service manager không cần `ServerWebExchange`. Khi grant thành công, manager thường lưu authorized client qua reactive service tương ứng để lần sau có thể dùng lại.

### 13.3. WebClient dành riêng cho machine token

~~~java
package com.example.security;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class MachineReportsClientConfig {

    @Bean
    WebClient machineReportsWebClient(
            @Qualifier("machineAuthorizedClientManager")
            AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

        return WebClient.builder()
            .baseUrl("https://reports.example.net")
            .filter(oauth2)
            .build();
    }
}
~~~

### 13.4. Gửi application Authentication rõ ràng

Trong một scheduled job, Reactor security context của user có thể không tồn tại. Dùng application principal **chỉ làm khóa lưu trữ token**, không phải giả mạo một end-user:

~~~java
package com.example.reports;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.authentication;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class MachineReportsGateway {

    private final WebClient machineReportsWebClient;

    public MachineReportsGateway(WebClient machineReportsWebClient) {
        this.machineReportsWebClient = machineReportsWebClient;
    }

    public Mono<String> loadReports() {
        Authentication servicePrincipal =
            new UsernamePasswordAuthenticationToken(
                "system-report-sync",
                "N/A",
                AuthorityUtils.NO_AUTHORITIES);

        return machineReportsWebClient.get()
            .uri("/v1/reports")
            .attributes(clientRegistrationId("report-sync"))
            .attributes(authentication(servicePrincipal))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

**Giới hạn bảo mật:** `servicePrincipal` trong ví dụ là đối tượng Authentication do backend tự dựng để manager xác định **principal name**, không phải bằng chứng đăng nhập OIDC, không được dùng để cấp quyền truy cập controller như một end-user.

Tên `system-report-sync` phải ổn định theo service identity để store tái sử dụng cùng authorized client. Không lấy principal này từ query string hay header do browser tùy ý gửi.

### 13.5. Tại sao không cần Refresh Token?

Với Client Credentials, Authorization Server thông thường **không cấp Refresh Token**. Khi Access Token hết hạn, manager có thể xin token mới bằng Client Credentials grant. Không thêm `refresh_token` hoặc `offline_access` như thể đây là OIDC end-user flow.

Khi provider từ chối `invalid_client` hoặc `invalid_scope`, đó là lỗi client authentication/policy. Không tự tăng quyền hoặc retry vô hạn.

## 14. Chọn registration theo chức năng hoặc tenant: nguyên tắc an toàn

Một ứng dụng nhiều API và nhiều tenant có thể cần mapping:

~~~text
Feature: readReports
  -> Resource Server: reports.example.net
  -> Registration: reports-read

Feature: readInvoices
  -> Resource Server: billing.example.net
  -> Registration: billing-read
~~~

### 14.1. Map từ allowlist server-side

Một cách dễ hiểu:

~~~java
enum Integration {
    REPORTS,
    BILLING
}

static String approvedRegistrationFor(Integration integration) {
    return switch (integration) {
        case REPORTS -> "reports-read";
        case BILLING -> "billing-read";
    };
}
~~~

Đây là **đoạn minh họa** cần đặt trong một Java class; mapping được quản lý bởi backend. Trong ứng dụng thật, trước khi chọn integration, còn phải xác minh caller **được phép thực hiện chức năng đó trong tenant hiện tại**.

### 14.2. Chọn theo tenant đã xác thực

Ví dụ sản phẩm nhiều tenant có các registrations `tenant-a-reports` và `tenant-b-reports`. Nếu user chỉ thuộc tenant A, ứng dụng phải:

1. Xác minh tenant membership từ Authentication/nguồn dữ liệu đáng tin.
2. Chọn registration của tenant A bằng mapping server-side.
3. Giữ principal namespace phù hợp để không load token của user/tenant khác.
4. Chỉ gửi token tới resource server thuộc tenant A.

Không tin `tenantId` từ URL là đủ để sử dụng registration chứa secret của tenant đó.

### 14.3. Tránh chọn token qua input tùy ý

Phản ví dụ:

~~~java
// KHÔNG DÙNG: caller có thể chọn credential và destination tùy ý.
webClient.get()
    .uri(userSuppliedUrl)
    .attributes(clientRegistrationId(userSuppliedRegistration))
    .retrieve()
    .bodyToMono(String.class);
~~~

Nguy cơ:

- Attacker khiến WebClient gửi Bearer Token tới host của họ.
- Một user có thể chọn registration quyền cao và dùng quyền service.
- Token của tenant này bị dùng cho tenant khác.
- Resource Server và client có thể bị khai thác SSRF, redirect abuse hoặc confused-deputy.

**Bảo vệ cả ba chiều:** URL đích, registration ID và principal phải cùng tuân theo policy đã xác minh.

## 15. Default OAuth2 authorized client: tiện nhưng dễ lộ credential

Filter hỗ trợ những lựa chọn mặc định để đỡ phải khai báo attributes ở mỗi request. Tuy nhiên, giá trị mặc định thay đổi **mọi request đi qua WebClient đó**.

### 15.1. setDefaultOAuth2AuthorizedClient(true)

~~~java
ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

oauth2.setDefaultOAuth2AuthorizedClient(true);
~~~

Khi bật, filter có thể tự chọn authorized client liên quan đến **OAuth2 authentication hiện tại** mà không cần request gắn explicit registration ID.

Rủi ro: những outbound requests không chủ đích, được tạo bởi một developer khác nhưng dùng cùng WebClient bean, **có thể được gắn Access Token của user hiện tại**.

### 15.2. setDefaultClientRegistrationId(...)

~~~java
oauth2.setDefaultClientRegistrationId("reports-read");
~~~

Thiết lập này khiến filter có thể sử dụng registration đó khi request không chỉ định client cụ thể. Phù hợp hơn với một WebClient **chuyên dụng cho một API cố định**, nhưng vẫn phải bảo đảm absolute URL và redirect không khiến token đi sang host ngoài.

### 15.3. Hai tình huống nên tránh

~~~text
WebClient global:
  default client registration = admin-service
  gọi Reports API -> admin token
  gọi public weather URL -> admin token ngoài ý muốn

WebClient global:
  default OAuth2 authorized client = current user login
  gọi UserInfo API -> Access Token user
  gọi arbitrary redirect URL -> có nguy cơ chuyển token sai đích
~~~

**Không bật default chỉ để “đỡ phải viết `clientRegistrationId(...)`”.** Hãy chọn nó vì đã thiết kế trust boundary rõ ràng.

### 15.4. Lựa chọn khuyến nghị cho code dễ review

Trong phần lớn hệ thống có nhiều APIs:

- Một WebClient bean cho mỗi Resource Server hoặc nhóm endpoints có cùng trust boundary.
- Mapping registration và principal rõ trong service layer.
- Chỉ truyền `oauth2AuthorizedClient(...)` hoặc `clientRegistrationId(...)` khi cần.
- Không dùng WebClient mang OAuth2 filter cho URL tùy ý từ browser.
- Chỉ bật default khi WebClient chuyên dụng và có kiểm soát đường dẫn/redirect.

## 16. Resource Server 401/403 và authorization failure handler

Việc chọn đúng authorized client **không bảo đảm API chấp nhận token**. Resource Server có thể từ chối vì Access Token đã bị revoke, sai issuer/audience hoặc thiếu scope.

### 16.1. Phân biệt các mã lỗi

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.write"
~~~

| Nơi xảy ra | Dấu hiệu | Diễn giải |
| --- | --- | --- |
| Token Endpoint | `invalid_client` | Client authentication không được chấp nhận |
| Token Endpoint | `invalid_scope` | Scope được yêu cầu không hợp lệ/không được phép |
| Token Endpoint | `invalid_grant` | Authorization Code/Refresh Token grant có vấn đề, tùy flow |
| Resource Server | `401 invalid_token` | Access Token không hợp lệ/hết hạn/đã thu hồi/sai thông số |
| Resource Server | `403 insufficient_scope` | Token không đủ scope cho API operation |
| Resource Server | `403` khác | Có thể là tenant/ownership/policy khác |

**Đừng dùng HTTP 403 như lý do tự xin thêm scope admin**, hoặc dùng 401 như dấu hiệu chắc chắn Client Secret sai. Lỗi ở Token Endpoint và lỗi tại Resource Server là hai tầng khác nhau.

### 16.2. Failure handler phụ thuộc cách tạo filter

Với constructor:

~~~java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    reactiveAuthorizedClientManager)
~~~

Spring Security không mặc nhiên cấu hình một `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` cho Resource Server Bearer errors. Token đã bị API từ chối có thể còn trong authorized client store và bị dùng lại ở request sau.

Với constructor:

~~~java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    reactiveClientRegistrationRepository,
    authorizedClientRepository)
~~~

filter có cơ chế cấu hình failure handler mặc định để xử lý việc loại bỏ authorized client khi lỗi phù hợp. Hành vi cụ thể theo **OAuth2/Bearer error code**, không phải “xóa mọi token mỗi khi thấy HTTP lỗi”.

### 16.3. Cần cấu hình khi dùng manager constructor

Các ứng dụng muốn kiểm soát stale token có thể cấu hình:

~~~java
// Minh họa điểm cấu hình; handler cần được tạo phù hợp
// repository/service thực tế của ứng dụng.
oauth2.setAuthorizationFailureHandler(reactiveFailureHandler);
~~~

`reactiveFailureHandler` là một implementation của `ReactiveOAuth2AuthorizationFailureHandler` được tạo từ cơ chế removal/store phù hợp. Với Spring Security có implementation `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler`, cần kết nối đúng strategy xóa authorized client theo registration/principal và store đang được manager dùng.

Không tạo handler xóa token từ JDBC service B khi manager đang lưu token ở repository A. Bản ghi stale sẽ vẫn tồn tại.

### 16.4. Có tự retry request bị 401 không?

Không nên giả định. Failure handler có thể **loại bỏ authorized client không còn hợp lệ**, để lần request kế tiếp có cơ hội xin lại token. Request hiện tại vẫn có thể kết thúc bằng `WebClientResponseException.Unauthorized` hoặc response lỗi khác.

Nếu muốn retry:

1. Chỉ retry lỗi có khả năng hồi phục và có giới hạn.
2. Với POST/PATCH/DELETE, kiểm soát idempotency và duplicate side effects.
3. Không lặp vô hạn khi provider tiếp tục cấp token sai audience.
4. Không retry `insufficient_scope` bằng cách tự nâng quyền.
5. Đảm bảo request retry vẫn chọn **cùng registration/principal hợp lệ**, không chuyển sang client quyền cao hơn.

## 17. Token hết hạn và refresh hoạt động ra sao?

### 17.1. Authorization Code/OIDC user token

~~~text
OIDC Login -> OAuth2AuthorizedClient(user, company)
      |
      +-- Access Token còn phù hợp -> tái sử dụng
      |
      +-- Access Token cần refresh
             -> refresh_token grant nếu có Refresh Token
             -> Token Endpoint trả Access Token mới
             -> manager lưu authorized client mới
             -> WebClient filter gắn Access Token mới
~~~

Provider có thể xoay vòng Refresh Token. Nếu manager không lưu token mới sau refresh, lần sau có thể dùng lại Refresh Token cũ đã bị thu hồi, dẫn đến `invalid_grant`.

### 17.2. Machine token với Client Credentials

~~~text
Client Credentials token hết hạn
  -> manager thực hiện client_credentials grant mới
  -> lưu Access Token mới cho service principal
  -> WebClient request tiếp tục gọi API
~~~

Client Credentials theo cách dùng chuẩn thông thường không có Refresh Token. Không bật OIDC `openid`/`offline_access` cho một service chỉ vì cần token mới định kỳ.

### 17.3. Manager không chỉ load token

`ReactiveOAuth2AuthorizedClientService.loadAuthorizedClient(...)` là **thao tác đọc bản ghi**. `ReactiveOAuth2AuthorizedClientManager.authorize(...)` có thể dùng provider để xin/refresh token theo cấu hình. Nếu request chỉ muốn kiểm tra trạng thái “đã kết nối hay chưa” mà không muốn kích hoạt token exchange, nên dùng service/repository load phù hợp.

### 17.4. Concurrent refresh và token rotation

~~~mermaid
sequenceDiagram
    autonumber
    participant A as WebClient Request A
    participant B as WebClient Request B
    participant S as Authorized Client Store
    participant OP as Token Endpoint
    A->>S: Tải token cũ
    B->>S: Tải token cũ
    A->>OP: Refresh Token grant
    B->>OP: Refresh Token grant với token cũ
    OP-->>A: Token mới, refresh token xoay vòng
    OP-->>B: Có thể invalid_grant
    A->>S: Lưu authorized client mới
    Note over S: Tránh request cũ xóa/ghi đè token mới
~~~

Nếu nhiều requests cùng dùng authorized client đã hết hạn, có thể cần cơ chế **single-flight theo registration/principal**, optimistic concurrency hoặc database transaction được thiết kế phù hợp. Không dùng global lock cho mọi users.

## 18. Reactive authorized client storage và vòng đời dữ liệu

### 18.1. ServerOAuth2AuthorizedClientRepository

Repository reactive có thể lưu dữ liệu theo HTTP exchange và principal, ví dụ trong WebSession hoặc thông qua service phù hợp. Nó được dùng cùng `DefaultReactiveOAuth2AuthorizedClientManager` trong luồng WebFlux request.

### 18.2. ReactiveOAuth2AuthorizedClientService

Service reactive không cần `ServerWebExchange`; nó phù hợp với persistence/worker use cases khi có principal name được xác định rõ.

Các API thường gặp:

~~~java
Mono<OAuth2AuthorizedClient> loadAuthorizedClient(
    String clientRegistrationId,
    String principalName
);

Mono<Void> saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal
);

Mono<Void> removeAuthorizedClient(
    String clientRegistrationId,
    String principalName
);
~~~

Chữ ký trên minh họa bề mặt API Reactive; dùng đúng imports/types và contract của phiên bản thư viện khi triển khai. Các phương thức trả `Mono` nên application không tự `subscribe()` tách khỏi reactive chain.

### 18.3. In-memory và persistent store

| Kiểu kho | Hành vi | Lưu ý |
| --- | --- | --- |
| In-memory reactive service | Đơn giản, token mất sau restart | Không tự chia sẻ giữa pods |
| WebSession repository | Liên kết với browser session | Hết session có thể mất authorized client |
| Persistent custom/service store | Có thể truy xuất qua nhiều instance/jobs | Cần encryption, schema, locking và data lifecycle |
| Shared session backing store | Hỗ trợ session continuity giữa instances | Cần bảo vệ cookie/session và TTL |

Không giả định mọi `ServerOAuth2AuthorizedClientRepository` luôn lưu vào session, vì repository có thể delegate về một service khác. Khi debug, xác định backing store **thực tế được bean/manager sử dụng**.

### 18.4. Logout khác xóa token và revoke

| Hành động | Tác động |
| --- | --- |
| User logout WebFlux | Kết thúc context/session theo logout policy |
| Xóa authorized client ở local store | Ứng dụng không còn tải được bản ghi token ấy |
| Gọi token revocation endpoint nếu provider hỗ trợ | Yêu cầu Authorization Server thu hồi token theo protocol |
| OIDC OP logout | Có thể kết thúc phiên đăng nhập phía OP theo hỗ trợ/config |

Không coi việc gọi `removeAuthorizedClient(...)` là bằng chứng mọi Access Token đã bị revoke ở Resource Server. Với persistent store, user logout cũng không tự xóa mọi authorized clients trừ khi policy/implementation quy định.

## 19. Bảo vệ Access Token khỏi SSRF, redirects và log

### 19.1. Một WebClient gắn OAuth2 filter là HTTP client có credential

Nếu dùng:

~~~java
webClient.get()
    .uri(untrustedUrl)
    .attributes(clientRegistrationId("admin-integration"))
    .retrieve();
~~~

attacker có thể khiến request gửi Bearer Token tới host nằm ngoài trust boundary. Đó là nguy cơ **SSRF và token exfiltration**.

### 19.2. baseUrl không phải host allowlist

~~~java
WebClient.builder()
    .baseUrl("https://reports.example.net")
    .filter(oauth2)
    .build();
~~~

Cấu hình `baseUrl` tốt cho routing nhưng **không tự chặn mọi absolute URI** mà code có thể truyền vào `.uri(...)`. Nếu URL đích có thể đến từ user input, cần kiểm tra host, scheme, port, IP resolution và redirect behavior.

### 19.3. Tách WebClients theo trust boundary

~~~text
reportsWebClient
  -> Reports API
  -> registration "reports-read"
  -> chỉ cho phép destination thuộc Reports API

billingWebClient
  -> Billing API
  -> registration "billing-read"
  -> chỉ cho phép destination thuộc Billing API

publicWebClient
  -> dữ liệu public đã kiểm soát
  -> KHÔNG gắn OAuth2 filter
~~~

Phân tách giúp code review dễ thấy request nào sử dụng credential. Không dùng một machine token quyền cao cho mọi API chỉ vì client registration có thể dùng lại.

### 19.4. Cross-host redirects

HTTP client/connector có chính sách redirects khác nhau theo transport và cấu hình. Không mặc định một redirect sang hostname khác sẽ xử lý Authorization header an toàn trong mọi tình huống.

Với client có credentials:

- Tắt hoặc giới hạn cross-host redirects khi không cần.
- Giữ allowlist destinations và kiểm tra quy tắc follow redirects.
- Không cho external URL được dùng làm redirect target của API do attacker điều khiển.
- Dùng HTTPS với TLS hostname/certificate validation.

### 19.5. Không ghi secrets trong logs

Không log:

- HTTP `Authorization: Bearer ...`.
- Access Token, Refresh Token, ID Token.
- Client Secret, client assertion, private key, token request body.
- Toàn bộ `OAuth2AuthorizedClient` hoặc JWT claims cá nhân.
- Authorization code, PKCE verifier hay OIDC nonce.

Một log metadata an toàn:

~~~text
event=outbound_oauth2_call
registration_id=reports-read
principal_type=user
resource=reports-api
result=success
http_status=200
correlation_id=internal-e43a
~~~

Đây là **format minh họa**, không phải tên log mặc định của Spring Security. Nếu cần principal ID, áp dụng privacy/retention/least privilege.

## 20. Tùy biến HTTP pipeline và retry

### 20.1. WebClient là reactive

Ví dụ:

~~~java
Mono<String> response = webClient.get()
    .uri("/v1/me")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
~~~

`Mono` mô tả pipeline. Trong WebFlux request, nên **trả Mono** hoặc compose qua `flatMap`, `zip`, `onErrorResume`. Không gọi `block()` trên Reactor event-loop để chờ API trả dữ liệu.

### 20.2. Retry HTTP 5xx và OAuth2 error không giống nhau

Một service có thể gặp:

- Network timeout/503: có thể retry **có giới hạn**, backoff và jitter.
- Token Endpoint `invalid_client`: kiểm tra secret/method; retry vô hạn không có ích.
- Token Endpoint `invalid_scope`: sửa scope/policy, không tự nâng quyền.
- Resource Server `401 invalid_token`: cần kiểm tra token/lifecycle và failure handler.
- Resource Server `403 insufficient_scope`: không tự tăng scope, cần policy/API contract.

Không dùng một `retryWhen(Retry.max(Long.MAX_VALUE))` cho mọi lỗi, vì có thể tạo token request storm hoặc lặp tác dụng phụ của API POST/DELETE.

### 20.3. Với POST/PATCH/DELETE

Giả sử API tạo báo cáo bằng POST. Nếu HTTP client timeout sau khi server đã xử lý POST, retry mù có thể tạo báo cáo lần thứ hai. Nếu cần retry, sử dụng idempotency key hoặc chính sách giao dịch được downstream hỗ trợ.

### 20.4. WebClient filter không phải đơn vị cấp quyền cho user

`clientRegistrationId("admin-service")` chỉ chọn một client registration; không tự kiểm tra user đã đăng nhập có quyền kích hoạt tính năng admin. Nếu một HTTP controller cho user thường chọn registration quyền cao, backend phải kiểm tra authorization trước khi gọi WebClient.

## 21. Khác nhau giữa Reactive và Servlet WebClient filters

| Hạng mục | Reactive WebFlux | Servlet MVC |
| --- | --- | --- |
| OAuth2 WebClient filter | **`ServerOAuth2AuthorizedClientExchangeFilterFunction`** | `ServletOAuth2AuthorizedClientExchangeFilterFunction` |
| Authorized Client Manager | `ReactiveOAuth2AuthorizedClientManager` | `OAuth2AuthorizedClientManager` |
| Repository có request context | `ServerOAuth2AuthorizedClientRepository` | `OAuth2AuthorizedClientRepository` |
| Service lưu authorized client | `ReactiveOAuth2AuthorizedClientService` | `OAuth2AuthorizedClientService` |
| Security context | Reactor Context / `ReactiveSecurityContextHolder` | `SecurityContextHolder` / Servlet context |
| HTTP exchange | `ServerWebExchange` | `HttpServletRequest`, `HttpServletResponse` |
| Controller trả kết quả | `Mono`/`Flux` thường là tự nhiên | Giá trị đồng bộ hoặc kiểu async tùy cấu hình |

Không dùng:

~~~java
// Servlet implementation — không phải reactive server filter.
new ServletOAuth2AuthorizedClientExchangeFilterFunction(
    servletAuthorizedClientManager)
~~~

trong một WebFlux server chỉ có reactive authorized client beans, rồi kỳ vọng nó truy xuất `ServerWebExchange`. Cũng không dùng `ServerOAuth2AuthorizedClientExchangeFilterFunction` làm `ClientHttpRequestInterceptor` của `RestClient`; hai HTTP client hooks khác nhau.

### 21.1. Không trộn manager/store giữa hai stacks

`OAuth2AuthorizedClientService` (Servlet/synchronous interface) và `ReactiveOAuth2AuthorizedClientService` không phải cùng contract. Nếu application tích hợp cả hai, cần thiết kế adapter/cơ chế chia sẻ backing store rõ ràng, không chỉ ép kiểu hoặc tự subscribe.

## 22. Troubleshooting theo dấu hiệu

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Request không có Bearer header | WebClient bean chưa gắn filter | Kiểm tra `.filter(oauth2)` trên đúng bean |
| Filter không tìm registration | Sai/thiếu `clientRegistrationId(...)` | Đối chiếu `spring.security.oauth2.client.registration.*` |
| Filter dùng sai registration | Default hoặc mapping sai | Dùng explicit request attribute, tách WebClients |
| Token user A bị gửi từ request user B | Sai Authentication/principal context | Kiểm tra Reactor Context và store ownership |
| WebClient request không có Authentication | Pipeline subscribe ngoài request hoặc scheduled job | Truyền context phù hợp, dùng service manager |
| Default manager thiếu ServerWebExchange | Chạy ngoài web request | Dùng service manager hoặc exchange hợp lệ |
| Manager trả empty / không cấp được token | Grant/provider không phù hợp, chưa có consent | Kiểm tra authorization flow và registration |
| Token Endpoint `invalid_client` | Secret/method/tenant/token URI sai | Sửa client authentication; không retry vô hạn |
| Token Endpoint `invalid_scope` | Scope không được cấp | Sửa policy/request scope; không tăng quyền tự động |
| API trả `401 invalid_token` | Token hết hạn/thu hồi/sai issuer/audience | Xem token validation và failure handler |
| API trả `403 insufficient_scope` | Token không đủ quyền | Kiểm tra API authorization policy |
| Sau 401 request kế vẫn dùng token cũ | Filter(manager) chưa có removal handler | Cấu hình Reactive failure handler dùng đúng store |
| Đã xóa token nhưng request hiện tại vẫn lỗi | Failure handler không auto-retry | Xem retry/idempotency policy |
| Sau deploy nhiều pods mỗi node xin token | In-memory service không chia sẻ | Shared persistence/coordination nếu cần |
| Refresh token xoay vòng bị `invalid_grant` | Hai requests refresh đồng thời, stale storage | Đồng bộ per-client, version/locking phù hợp |
| API request đưa token tới URL lạ | WebClient nhận absolute URI từ user input | SSRF checks, allowlist host, hạn chế redirects |
| JWT/Access Token xuất hiện trong logs | Wire logging hoặc debug interceptor ghi header | Redact Authorization/credentials |
| Login OIDC tốt nhưng Reports API 403 | Access Token scope/audience/policy không phù hợp | Không dùng ID Token thay Access Token |
| Logout xong token JDBC còn | Persistent store lifecycle khác session | Xác định chính sách disconnect/revocation |

### 22.1. Quy trình điều tra một request

~~~text
Outbound WebClient request lỗi
  |
  +-- Đúng WebClient bean có OAuth2 filter?
  |
  +-- Đang chọn oauth2AuthorizedClient hay clientRegistrationId?
  |
  +-- ClientRegistration có tồn tại và đúng provider?
  |
  +-- Authentication/principal có đúng user/service?
  |
  +-- Reactive manager có đúng web-context/service-context?
  |
  +-- Authorized client store có đúng khóa và backing store?
  |
  +-- Token Endpoint đã cấp/refresh thành công?
  |
  +-- Access Token đi tới đúng Resource Server?
  |
  +-- API trả 401, 403, 429, 5xx hay transport exception?
  |
  +-- Failure handler và retry policy có phù hợp?
~~~

Không cần in raw token để điều tra. Dùng registration ID, principal category, token presence, mã lỗi đã phân loại, HTTP status và correlation ID nội bộ.

## 23. Ví dụ tình huống thực tế

### Tình huống A — Controller đã có authorized client

Spring Security đã inject `@RegisteredOAuth2AuthorizedClient("company")` cho user đang đăng nhập.

**Cách làm:** truyền `.attributes(oauth2AuthorizedClient(client))`. Không lấy token value rồi tự xây header Bearer, và không lưu object vào singleton.

### Tình huống B — Service chỉ biết registration

Một service cần gọi Reports API, không muốn quản lý token lifecycle.

**Cách làm:** dùng `.attributes(clientRegistrationId("reports-api"))` và manager/provider/store đã được cấu hình. Không tự gọi Token Endpoint cho mỗi HTTP request.

### Tình huống C — WebClient chung gọi Reports và Billing

Developer sử dụng `clientRegistrationId("reports-api")` cho cả hai URLs.

**Cách làm:** tách clients/mapping theo API và đưa lựa chọn registration vào service layer đáng tin; không để Access Token của Reports đi sang Billing.

### Tình huống D — Scheduled job không có user SecurityContext

Một queue consumer chạy ngoài WebFlux request cần token Client Credentials.

**Cách làm:** dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` và `authentication(servicePrincipal)` với tên ứng dụng ổn định, chọn `clientRegistrationId("report-sync")`.

### Tình huống E — Một user đổi provider đăng nhập

User login lần trước với `company`, giờ đăng nhập với `partner`. Code vẫn hard-code `company`.

**Cách làm:** nếu tính năng phụ thuộc registration của chính login, lấy registration từ `OAuth2AuthenticationToken` đã xác minh hoặc mapping tin cậy. Không tự dùng token cũ chỉ vì username giống nhau.

### Tình huống F — User có hai connections cùng provider

Ứng dụng quản lý hai kết nối delegated OAuth2 khác nhau.

**Cách làm:** thiết kế namespace/principal/account linking phù hợp, chọn authorized client cụ thể. Không dùng một registration chỉ khóa theo email để vô tình đè token của connection khác.

### Tình huống G — Token còn hạn nhưng API trả 401

Resource Server đã thu hồi token hoặc audience không phù hợp.

**Cách làm:** kiểm tra issuer/audience; với `invalid_token` có thể xóa cached authorized client qua handler phù hợp. Không retry vô hạn nếu token được cấp mới vẫn sai audience.

### Tình huống H — API trả 403 insufficient_scope

Client có `reports.read` nhưng gọi API yêu cầu `reports.write`.

**Cách làm:** không chọn bừa registration admin để bypass; cập nhật quyền qua quy trình cấp phép chính thức nếu feature thật sự cần.

### Tình huống I — Bật default OAuth2 authorized client rồi thêm public fetch

Một WebClient được dùng cho API login và sau này có tính năng tải URL tùy ý.

**Cách làm:** tách public WebClient không credential, đặt allowlist hosts trên client có OAuth2 filter, không dựa vào defaults để gửi token tới mọi request.

### Tình huống J — Authorized client đã được cấp nhưng user logout

Một kho persistent còn giữ delegated token sau logout.

**Cách làm:** xác định quyền tiếp tục gọi API sau logout có được người dùng đồng ý/policy cho phép không; cung cấp disconnect/revoke khi cần. Không coi `setDefaultOAuth2AuthorizedClient(false)` là cơ chế revocation.

### Tình huống K — Hai requests cùng refresh token

Provider xoay Refresh Token một lần dùng, một request nhận `invalid_grant`.

**Cách làm:** kiểm soát concurrency và failure cleanup để không xóa token mới đã được request khác lưu.

### Tình huống L — Request attribute lấy từ query parameter

Backend cho user gọi `/proxy?registration=admin-client&url=...` rồi chuyển thẳng vào WebClient.

**Cách làm:** từ chối thiết kế này; dùng mapping server-side và authorization theo user/tenant/feature trước khi chọn credential và URL.

## 24. Kiểm thử việc chọn authorized client trên WebClient

Để kiểm thử đầy đủ, tách mục tiêu:

| Lớp | Kiểm tra |
| --- | --- |
| Request mapping test | `clientRegistrationId(...)` hoặc `oauth2AuthorizedClient(...)` được chọn đúng |
| Filter test | Khi có authorized client test, HTTP request chứa Bearer Test Token |
| Manager test | Dùng đúng registration/principal, cấp hoặc tái sử dụng token theo grant |
| Reactive context test | Authentication lấy đúng từ Reactor Context, không lẫn users |
| HTTP integration test | Resource Server trả 401/403 và application xử lý đúng |
| Security/SSRF test | Không gửi token đến host/URL chưa được allowlist |
| Session/storage test | Logout, expiry, persistence và multi-node đúng policy |

### 24.1. Các kịch bản tối thiểu

1. Có `OAuth2AuthorizedClient` của Alice: request Alice có Bearer token test; request Bob không lấy token của Alice.
2. `clientRegistrationId("reports-api")`: manager được yêu cầu chọn registration đúng.
3. `clientRegistrationId("billing-api")`: token Reports không bị gửi đến Billing.
4. Không có registration/authorized client/default: không tự chọn credential quyền cao.
5. Client Credentials với application principal cố định: token được lưu/tải lại dưới cùng khóa.
6. Manager không thể authorize: outbound request không được thực hiện bằng một token được dựng giả.
7. Token hết hạn: manager/provider thực hiện re-authorization khi hỗ trợ.
8. Resource Server 401 invalid_token: failure handler xử lý theo policy.
9. Resource Server 403 insufficient_scope: không tự chọn registration admin.
10. URL không thuộc allowlist: request bị chặn trước khi Bearer Token có thể rời ứng dụng.
11. Không có Reactor security context trong worker: service manager vẫn xử lý application principal.
12. Debug logging bật: token, Client Secret và Authorization header không xuất hiện trong logs.

### 24.2. Test filter với fake ExchangeFunction

Một cách kiểm thử ý tưởng là cung cấp test double cho `ReactiveOAuth2AuthorizedClientManager`, trả một `OAuth2AuthorizedClient` với token **TEST_ONLY**, rồi cho WebClient đi qua `ExchangeFunction` giả:

~~~text
WebClient.get("/v1/reports")
    attributes(clientRegistrationId("reports-api"))
       |
       v
ServerOAuth2AuthorizedClientExchangeFilterFunction
       |
       v
Fake ReactiveOAuth2AuthorizedClientManager
    -> returns TEST_ONLY_ACCESS_TOKEN
       |
       v
Fake ExchangeFunction
    assert Authorization == Bearer TEST_ONLY_ACCESS_TOKEN
    return HTTP 200 JSON
~~~

Test này chứng minh **lựa chọn token và chèn header**, không chứng minh token thật được OP phát hành hoặc Resource Server validate JWT đúng.

### 24.3. Test Authorization Code/OIDC cần lớp riêng

Mock `OAuth2AuthorizedClient` không thay thế test:

- Authorization request + `state` correlation.
- PKCE challenge/verifier.
- OIDC ID Token signature/issuer/audience/nonce.
- Token Endpoint response và Refresh Token rotation.
- User account linking và principal namespace.

Đó là các lớp kiểm thử giao thức cần OP giả lập hoặc môi trường tích hợp phù hợp.

### 24.4. Test không làm lộ credentials thật

Không dùng production Client Secret để cố tạo `invalid_client` trong môi trường test. Không lưu Access Token thật vào fixture, logs hoặc screenshots. Dùng credential giả và mock Token Endpoint/Resource Server.

## 25. Câu hỏi ôn tập

**1. `clientRegistrationId(...)` và `oauth2AuthorizedClient(...)` khác nhau thế nào?**

`clientRegistrationId(...)` chọn một cấu hình OAuth2 client để manager tìm/cấp authorized client. `oauth2AuthorizedClient(...)` truyền một authorized client cụ thể đã được chọn bởi code server-side tin cậy.

**2. Có nên truyền cả hai attributes trong cùng request?**

Không nên. Điều đó tạo ý định mâu thuẫn hoặc phụ thuộc precedence nội bộ; hãy dùng một cách chọn token nhất quán.

**3. Vì sao hai users cùng `registrationId` không được dùng chung token?**

Vì `OAuth2AuthorizedClient` gắn với principal; store cần ràng buộc token theo registration/principal, không chỉ theo registration.

**4. Reactive WebFlux lấy Authentication từ đâu?**

Thông thường từ Reactor security context do Spring Security quản lý; có thể truyền tường minh qua `authentication(...)` khi cần. Không dựa vào Servlet ThreadLocal.

**5. Scheduled job có nên dùng `DefaultReactiveOAuth2AuthorizedClientManager`?**

Không nếu công việc không có `ServerWebExchange`/web request cần thiết. Với Client Credentials thường dùng service manager và application principal rõ ràng.

**6. Default registration có nguy cơ gì?**

Mọi request qua WebClient đó có thể vô tình gắn Bearer Token, kể cả request tới URL không đáng tin nếu code cho phép.

**7. Filter(manager) có tự xóa cached token khi API trả 401 không?**

Không mặc định cấu hình RemoveAuthorizedClient failure handler cho constructor nhận manager; cần đánh giá và cấu hình handler tương ứng.

**8. Token của user có `ROLE_ADMIN` có tự có `reports.write` không?**

Không. Role của ứng dụng và scope/audience của Access Token do Authorization Server/Resource Server quản lý là các phạm vi khác nhau.

**9. `OAuth2AuthorizedClient` có nên được lưu trong biến static hoặc trả về browser không?**

Không. Nó chứa credential nhạy cảm và ràng buộc principal, grant và thời hạn.

**10. Khi API trả `403 insufficient_scope` nên xử lý thế nào?**

Kiểm tra API contract và quyền đã được cấp. Không tự chọn registration quyền cao hoặc tăng scope để bypass.

## 26. Tài liệu tham khảo

- Spring Security — Reactive OAuth2 Client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security — Reactive OAuth2 Authorized Clients: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html
- Spring Security — Reactive OAuth2 Client Core: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html
- Spring Security — Reactive OAuth2 Login: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- Spring Security — `ServerOAuth2AuthorizedClientExchangeFilterFunction` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html
- Spring Security — `ReactiveOAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientManager.html
- Spring Security — `DefaultReactiveOAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultReactiveOAuth2AuthorizedClientManager.html
- Spring Security — `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager.html
- Spring Framework — WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- OAuth 2.0 Authorization Framework (RFC 6749): https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 Bearer Token Usage (RFC 6750): https://www.rfc-editor.org/rfc/rfc6750
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700

## 27. Tổng kết: chọn token tường minh và giữ đúng ranh giới principal

~~~text
Reactive WebClient request
    |
    +-- CÁCH A: đã có authorized client cụ thể
    |      attributes(oauth2AuthorizedClient(client))
    |
    +-- CÁCH B: chọn registration cho manager
           attributes(clientRegistrationId("company" | "reports-api"))
    |
    +-- Authentication/principal:
    |      - WebFlux user: Reactor SecurityContext
    |      - Machine flow: application principal có kiểm soát
    |
    v
ServerOAuth2AuthorizedClientExchangeFilterFunction
    |
    v
ReactiveOAuth2AuthorizedClientManager
    |
    +-- Load authorized client theo registration + principal
    +-- Authorize/refresh theo grant hợp lệ nếu cần
    +-- Lưu authorized client mới
    |
    v
Authorization: Bearer <access_token>
    |
    v
Resource Server xác minh issuer/audience/scope/policy
    |
    +-- 2xx -> xử lý response
    +-- 401 invalid_token -> cân nhắc invalidation/token lifecycle
    +-- 403 insufficient_scope -> xử lý thiếu quyền, không nâng scope
    +-- 429/5xx -> retry/backoff theo policy
~~~

**Bốn điều cốt lõi:**

1. **`oauth2AuthorizedClient(client)` chọn một kết quả ủy quyền cụ thể; `clientRegistrationId(id)` chọn cấu hình để manager tìm/cấp token.** Sử dụng một chiến lược rõ ràng cho từng request.
2. **Principal là một phần của ranh giới bảo mật.** Với WebFlux user flow, Authentication đến từ reactive security context; với Client Credentials, service principal phải được backend chọn ổn định và không được nhầm là user identity.
3. **Default credentials có rủi ro lan rộng.** Tránh bật default OAuth2 client cho WebClient dùng nhiều host hoặc URL do user kiểm soát; kiểm soát destination, registration, redirects và logging.
4. **Filter chỉ đưa Access Token vào HTTP request.** Authorized client manager quản lý vòng đời token, còn Resource Server quyết định quyền truy cập; HTTP 401/403 phải được xử lý theo error code và policy, không tự bypass.

Khi nắm vững hai cách chọn **authorized client hoặc registration cho từng WebClient request**, ứng dụng Reactive có thể gọi nhiều API bằng OAuth2 một cách rõ ràng, tái sử dụng token hợp lý và tránh nhầm lẫn giữa danh tính người dùng, quyền của service và phạm vi được Resource Server cho phép.
