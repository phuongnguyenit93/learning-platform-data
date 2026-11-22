# 21.3. AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager cho tác vụ nền

## 1. Tình huống: tác vụ nền cần gọi API mà không có người dùng đăng nhập

Giả sử ứng dụng **Employee Portal** sử dụng **Spring Boot, Spring Security OAuth 2.0 Client và WebFlux**. Ngoài giao diện đăng nhập OIDC cho nhân viên, hệ thống có một **Reports Job** chạy định kỳ để tổng hợp báo cáo. Mỗi lần thực thi, job phải gọi một **Reports API** được bảo vệ bằng OAuth 2.0 Bearer token.

~~~text
01:00:00  Reports Job được kích hoạt.
01:00:01  Job cần gọi GET https://reports.example.test/api/daily-summary.
01:00:01  Reports API yêu cầu access token có scope reports.read.
01:00:02  Không có browser, không có người dùng đăng nhập và không có ServerWebExchange.
~~~

Trong một HTTP request WebFlux thông thường, Spring Security có thể lấy `Authentication` và `ServerWebExchange` để tìm authorized client. Nhưng **scheduled task, message consumer, queue worker hoặc batch job** không mặc nhiên có những đối tượng đó.

Nếu cố sử dụng manager dành cho web request, job dễ gặp lỗi thiếu exchange/context, không tìm thấy authorized client hoặc nhầm token của một người dùng với quyền của ứng dụng.

**Giải pháp phù hợp** là sử dụng:

~~~java
org.springframework.security.oauth2.client
    .AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
~~~

Đây là một implementation của **`ReactiveOAuth2AuthorizedClientManager`** sử dụng **`ReactiveOAuth2AuthorizedClientService`** để quản lý authorized client mà **không phụ thuộc vào WebFlux ServerWebExchange**.

Trong bài, grant chính là **`client_credentials`**: Reports Job gọi API bằng danh tính của **OAuth client/dịch vụ**, không giả lập một người dùng OIDC đang đăng nhập.

> Ngữ cảnh: Java 17+, Spring Boot 3, Spring Security 6 và Project Reactor. Các hostname, tên registration và token trong bài chỉ dùng minh họa. Mọi trường hợp gọi API “thay mặt người dùng” cần chính sách ủy quyền riêng; đừng dùng client credentials rồi coi đó là token của nhân viên.

## 2. Cùng là ReactiveOAuth2AuthorizedClientManager nhưng khác ngữ cảnh sử dụng

Spring Security Reactive có hai implementation thường gặp:

| Đặc điểm | `DefaultReactiveOAuth2AuthorizedClientManager` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
|---|---|---|
| Ngữ cảnh thiết kế | Request WebFlux | Tác vụ ngoài WebFlux request |
| Storage | `ServerOAuth2AuthorizedClientRepository` | `ReactiveOAuth2AuthorizedClientService` |
| Client registrations | `ReactiveClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| Cần ServerWebExchange? | Thường cần exchange/context phù hợp để dùng repository | **Không** |
| Ví dụ phù hợp | WebClient gọi API trong request của user | Scheduler, queue consumer, background worker |
| Principal | User Authentication của request hoặc context tin cậy | Tên principal/danh tính đã được ứng dụng xác định |
| Grant thường dùng | Authorization code, refresh token | Client credentials; hoặc refresh token có điều kiện nghiệp vụ |
| API cấp quyền | `Mono<OAuth2AuthorizedClient>` | `Mono<OAuth2AuthorizedClient>` |

**Hai manager có cùng interface nhưng không thể thay thế tùy tiện**. Manager của web request phối hợp với security/session context; manager dịch vụ làm việc với authorized-client service trực tiếp.

### 2.1. Cơ chế nào quản lý HTTP session?

**Không phải** `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`. Nó không tạo một `SecurityWebFilterChain`, không đăng nhập OIDC và không lưu WebSession cho browser.

Một ứng dụng có thể đồng thời:

~~~text
HTTP request của nhân viên
  -> OIDC login / SecurityContext / WebSession
  -> DefaultReactiveOAuth2AuthorizedClientManager

Background job lúc 01:00
  -> service registration: reports-service
  -> AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
  -> client_credentials access token
~~~

Mỗi luồng có **principal, storage và security boundary** khác nhau.

## 3. Kiến trúc tổng thể của manager dành cho tác vụ nền

~~~mermaid
flowchart TD
    J["@Scheduled / Queue Consumer / Background Worker"] --> G["ReportsGateway"]
    G --> A["OAuth2AuthorizeRequest"]
    A --> M["AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager"]
    M --> R["ReactiveClientRegistrationRepository"]
    M --> S["ReactiveOAuth2AuthorizedClientService"]
    M --> P["ReactiveOAuth2AuthorizedClientProvider"]
    P --> CC["client_credentials grant"]
    CC --> T["Reactive token response client"]
    T --> AS["Authorization Server token endpoint"]
    AS --> T
    T --> P
    P --> M
    M -->|save/update| S
    M -->|Mono<OAuth2AuthorizedClient>| G
    G --> W["WebClient"]
    W -->|Authorization: Bearer access token| API["Reports API"]
~~~

Trong kiến trúc này:

1. **Job** xác định nó cần gọi Reports API.
2. **Gateway** tạo `OAuth2AuthorizeRequest` cho registration `reports-service` và một service principal ổn định.
3. **Manager** kiểm tra authorized client đã lưu trong `ReactiveOAuth2AuthorizedClientService`.
4. Nếu cần cấp token mới, **provider** thực hiện grant được hỗ trợ.
5. **Authorization Server** trả access token.
6. **Manager** lưu authorized client mới qua service.
7. **WebClient** gửi Bearer token tới Reports API.

Không bước nào yêu cầu browser redirect hoặc OIDC session của người dùng.

## 4. Các thành phần cần hiểu

| Thành phần | Trách nhiệm |
|---|---|
| `ReactiveClientRegistrationRepository` | Đọc cấu hình OAuth client, token URI, grant type, client authentication method và scopes |
| `ReactiveOAuth2AuthorizedClientService` | Lưu/tải/xóa authorized client theo registration ID và principal name |
| `ReactiveOAuth2AuthorizedClientProvider` | Quyết định grant nào áp dụng và tạo token/authorized client |
| `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | Điều phối registration, provider, storage và success/failure lifecycle |
| `OAuth2AuthorizeRequest` | Chứa registration ID hoặc authorized client cùng principal/context cho một lần authorize |
| `OAuth2AuthorizedClient` | Kết quả đã được cấp quyền, chứa access token và có thể có refresh token |
| `WebClient` | Gửi HTTP request tới Resource Server |
| **Reports API / Resource Server** | Kiểm tra Bearer token, scopes/audience và quyền tài nguyên |

### 4.1. Không nhầm registration với authorized client

`ClientRegistration` là **cấu hình tĩnh/metadata**:

~~~text
registrationId = reports-service
clientId = reporting-worker
authorizationGrantType = client_credentials
tokenUri = https://login.example.test/oauth2/token
scope = reports.read
~~~

`OAuth2AuthorizedClient` là **kết quả đã có token**:

~~~text
registrationId = reports-service
principalName = reports-scheduler
accessToken = AT-1, expiresAt = 01:05
refreshToken = null (thường gặp với client_credentials)
~~~

Việc YAML có registration **không đồng nghĩa** token đã được cấp. Token chỉ được lấy khi một thành phần thực sự gọi manager/provider theo grant phù hợp.

### 4.2. Manager không tự chạy khi đồng hồ đến giờ

Tên class có chữ `Manager` không biến nó thành scheduler. Nó không tự thức dậy mỗi phút để refresh access token. **Job** hoặc consumer phải gọi:

~~~java
manager.authorize(authorizeRequest);
~~~

thì quá trình lấy/làm mới authorized client mới được kích hoạt.

## 5. client_credentials: grant phù hợp với service-to-service

Trong **Client Credentials Grant**, OAuth client sử dụng credential của **chính ứng dụng** để xin access token.

~~~mermaid
sequenceDiagram
    participant Job as Reports Job
    participant Manager as Reactive Authorized Client Manager
    participant AS as Authorization Server
    participant API as Reports API

    Job->>Manager: authorize(reports-service, reports-scheduler)
    Manager->>AS: POST /token grant_type=client_credentials
    AS-->>Manager: access_token, token_type, expires_in
    Manager-->>Job: OAuth2AuthorizedClient
    Job->>API: GET /api/daily-summary + Bearer token
    API-->>Job: 200 DailySummary
~~~

HTTP token request minh họa khi client dùng `client_secret_basic`:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <redacted-client-credentials>

grant_type=client_credentials&scope=reports.read
~~~

Response minh họa:

~~~json
{
  "access_token": "EXAMPLE_SERVICE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "reports.read"
}
~~~

Với `client_credentials`, **refresh token thường không được cấp** theo mô hình OAuth2 chuẩn. Khi access token sắp/hết hạn, manager có thể thực hiện **client_credentials grant mới** để lấy access token khác.

Không cần tạo OIDC `OidcUser`, gọi `/oauth2/authorization/...` hay giả lập một user session cho job.

### 5.1. Client token không phải user token

Token được cấp qua `client_credentials` đại diện cho quyền của **client/service**. Nếu Reports API cần biết “nhân viên nào đang yêu cầu dữ liệu”, không tự gắn tên nhân viên vào request rồi xem service token là bằng chứng người dùng đó được xác thực.

Trong các tác vụ nền, cần xác định **ai được phép đặt lịch/gửi job**, **job được truy cập tenant nào**, và **service token có scopes/audience nào**. Đây là chính sách ứng dụng/Resource Server, không tự đến từ việc manager cấp token thành công.

## 6. Cấu hình Spring Boot cho một Reports Job

### 6.1. Dependencies

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

Một ứng dụng **chỉ chạy background worker**, không mở HTTP endpoint, có thể sử dụng một tập dependency và application type khác. OAuth2 Client manager kiểu **service** không yêu cầu phải có một WebFlux HTTP server. Tuy nhiên, nếu Portal là WebFlux application, các dependency trên là bối cảnh phù hợp.

### 6.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
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

reports:
  api:
    base-url: https://reports.example.test
  job:
    fixed-delay-ms: 60000
~~~

Các biến `REPORTS_CLIENT_ID`, `REPORTS_CLIENT_SECRET` và `OIDC_ISSUER_URI` phải đến từ môi trường triển khai an toàn. Đặc biệt, **client secret không được commit vào Git, log, JavaScript hoặc tài liệu dùng chung**.

**Lưu ý về issuer-uri:** Spring Security có thể sử dụng metadata discovery của provider khi issuer được hỗ trợ. Nếu Authorization Server không hỗ trợ discovery, cấu hình rõ `token-uri` và những endpoint cần thiết theo hợp đồng provider. Với `client_credentials`, không có browser authorization endpoint trong runtime job, nhưng client vẫn cần token endpoint hợp lệ.

### 6.3. Scope không quyết định mọi quyền

`scope: reports.read` là phạm vi ứng dụng **yêu cầu**. Authorization Server quyết định scope nào được cấp, còn Reports API kiểm tra token thực tế, audience và quyền resource.

Không coi việc token chứa `reports.read` là bằng chứng job được đọc mọi tenant nếu Reports API còn có tenant authorization riêng.

## 7. ReactiveOAuth2AuthorizedClientService: nơi lưu authorized client

Manager dành cho tác vụ nền làm việc với:

~~~java
org.springframework.security.oauth2.client
    .ReactiveOAuth2AuthorizedClientService
~~~

Interface này cung cấp thao tác tương tự:

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

Với Spring Security Reactive, các thao tác trả **Mono**, phù hợp với pipeline không blocking.

### 7.1. In-memory service cho development

Một implementation:

~~~java
import org.springframework.security.oauth2.client
    .InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client
    .ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration
    .ReactiveClientRegistrationRepository;

ReactiveOAuth2AuthorizedClientService service =
    new InMemoryReactiveOAuth2AuthorizedClientService(registrations);
~~~

`registrations` là `ReactiveClientRegistrationRepository` mà Spring Boot có thể tạo từ cấu hình OAuth2 Client.

In-memory storage:

- Phù hợp với demo và môi trường một instance, dữ liệu không cần bền.
- Có thể mất authorized client khi restart.
- Không chia sẻ state giữa replicas.
- Không tự giải quyết concurrency nếu nhiều task cùng cấp token.

Nếu Spring Boot đã tự cấu hình bean `ReactiveOAuth2AuthorizedClientService` phù hợp, không cần tạo một bean thứ hai chỉ để có service. Việc tạo nhiều beans cùng type có thể làm injection mơ hồ.

### 7.2. Storage cho production

Khi job chạy trên nhiều replicas hoặc cần khôi phục state, có thể cần một triển khai `ReactiveOAuth2AuthorizedClientService` dựa trên database/cache tập trung. Tùy phiên bản Spring Security và hạ tầng, có thể dùng implementation được cung cấp hoặc xây một adapter reactive với storage hiện có.

Các yêu cầu cần đánh giá:

- Bảo vệ token value, refresh token và client secrets.
- Encryption-at-rest, TLS, access control và backup policy.
- Keying theo registration ID và principal name.
- TTL/retention/cleanup phù hợp token lifecycle.
- Race condition khi nhiều job cùng authorize.
- Tránh blocking JDBC call trực tiếp trên Reactor event loop nếu storage wrapper không thực sự reactive.

**Không tự viết `saveAuthorizedClient()` bỏ qua principal/registration mapping hoặc lưu token không mã hóa trong log.**

## 8. Tạo AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager

Đây là cấu hình cốt lõi:

~~~java
package com.example.portal.reports;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
public class ReportsOAuth2ManagerConfig {

    @Bean("reportsAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager reportsAuthorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ReactiveOAuth2AuthorizedClientService authorizedClientService
    ) {
        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations,
                authorizedClientService
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

**Đọc từng dòng quan trọng:**

1. `ReactiveClientRegistrationRepository` chứa registration `reports-service`.
2. `ReactiveOAuth2AuthorizedClientService` lưu và tải token.
3. `ReactiveOAuth2AuthorizedClientProviderBuilder.builder().clientCredentials()` cho phép provider cấp token theo grant của dịch vụ.
4. `new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(...)` tạo manager **không cần ServerWebExchange**.
5. `setAuthorizedClientProvider(provider)` gắn grant provider vào manager.
6. Bean name giúp injection rõ ràng nếu application có thêm manager của web request.

Không cần `oauth2Login()` để job chạy. Nếu Portal vẫn có login cho người dùng, cấu hình OIDC web login **là một luồng riêng**.

### 8.1. Vì sao không tự gọi token endpoint bằng WebClient?

Một cách làm thủ công:

~~~text
POST /token -> đọc JSON -> tự tính expiresAt
-> tự cache accessToken -> tự retry -> tự rotate refreshToken
~~~

có thể bỏ sót client authentication, error mapping, token response parsing và concurrency. Sử dụng provider/manager chuẩn giúp tập trung OAuth2 token lifecycle tại một nơi, tách biệt với Reports API gateway.

## 9. Mono<OAuth2AuthorizedClient>: hợp đồng Reactive của manager

Interface:

~~~java
import org.springframework.security.oauth2.client
    .ReactiveOAuth2AuthorizedClientManager;

Mono<OAuth2AuthorizedClient> authorize(
    OAuth2AuthorizeRequest authorizeRequest
);
~~~

Những khả năng khi subscribe:

| Kết quả | Ý nghĩa |
|---|---|
| Phát `OAuth2AuthorizedClient` | Có authorized client phù hợp, có access token để sử dụng theo policy |
| `Mono.empty()` | Không cấp/trả được authorized client trong context hiện tại; provider/grant có thể không áp dụng |
| `Mono.error(...)` | OAuth2 authorization hoặc tầng transport/storage gặp lỗi |

**Không coi `Mono.empty()` là token trống hợp lệ**, và không tự tạo một Bearer header rỗng để gọi Resource Server.

### 9.1. Reactive Publisher thường lazy

Khi viết:

~~~java
Mono<OAuth2AuthorizedClient> publisher = manager.authorize(request);
~~~

không có nghĩa token endpoint đã được gọi xong. Publisher cần được subscribe bởi Reactor pipeline/framework.

Tránh:

~~~java
// Không thực hiện trong service rồi bỏ qua kết quả:
manager.authorize(request).subscribe();

// Không block bên trong Reactor Netty event-loop:
OAuth2AuthorizedClient client = manager.authorize(request).block();
~~~

Thay vào đó, **trả Mono/compose bằng flatMap** để cancellation, error và lifecycle tiếp tục được quản lý.

## 10. Tạo OAuth2AuthorizeRequest cho service principal

Manager cần biết **registration** và **principal**:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-service")
        .principal("reports-scheduler")
        .build();
~~~

Ở đây:

- `reports-service` là **ClientRegistration ID** trong YAML.
- `reports-scheduler` là tên principal ổn định dùng cho authorized-client storage của job.
- Chuỗi principal đó **không** chứng minh có một người dùng tên reports-scheduler đã đăng nhập.
- Khi dùng `client_credentials`, token đại diện cho **client/dịch vụ**, không đại diện cho chuỗi principal đó như một tài khoản người dùng ở IdP.

### 10.1. Vì sao vẫn phải truyền principal?

Authorized client thường được lưu theo một khóa tương tự:

~~~text
(clientRegistrationId, principalName)

("reports-service", "reports-scheduler")
~~~

Tên principal giúp phân biệt token state của các consumer/context theo cơ chế lưu trữ. Với một job có cùng chính sách và quyền, chọn một tên **ổn định, do backend quản lý**.

Không dùng random UUID mới làm principal trên mỗi lần chạy nếu mục đích là **tái sử dụng authorized client** khi token còn hạn: mỗi lần gọi có thể tạo một storage key mới.

### 10.2. Không nhận principal name từ input không đáng tin

Không thiết kế:

~~~http
POST /internal/run-report?principalName=admin HTTP/1.1
~~~

rồi dùng `.principal("admin")` để truy xuất token đã lưu của account khác. Với service token, principal phải được cấu hình từ môi trường backend có kiểm soát; với user-authorized token, phải dựa vào Authentication đã được xác minh.

## 11. ReportsGateway: lấy token bằng manager rồi gọi WebClient

Một thiết kế dễ hiểu và ít phụ thuộc context là **lấy authorized client rõ ràng trong service**, rồi gắn access token vào request tới đúng Reports API:

~~~java
package com.example.portal.reports;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReportsGateway {

    private final ReactiveOAuth2AuthorizedClientManager manager;
    private final WebClient reportsWebClient;

    public ReportsGateway(
        @Qualifier("reportsAuthorizedClientManager")
        ReactiveOAuth2AuthorizedClientManager manager,
        @Qualifier("reportsWebClient") WebClient reportsWebClient
    ) {
        this.manager = manager;
        this.reportsWebClient = reportsWebClient;
    }

    public Mono<DailySummary> fetchDailySummary() {
        OAuth2AuthorizeRequest authorization =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reports-service")
                .principal("reports-scheduler")
                .build();

        return manager.authorize(authorization)
            .switchIfEmpty(Mono.error(
                new IllegalStateException(
                    "No authorized client for reports-service"
                )
            ))
            .flatMap(client -> reportsWebClient.get()
                .uri("/api/daily-summary")
                .headers(headers -> headers.setBearerAuth(
                    client.getAccessToken().getTokenValue()
                ))
                .retrieve()
                .bodyToMono(DailySummary.class)
            );
    }
}
~~~

Trong ví dụ trên, `DailySummary` là DTO nghiệp vụ do ứng dụng định nghĩa. `reportsWebClient` cần có base URL, timeout và bảo mật transport được cấu hình riêng.

**Giải thích thứ tự:**

1. Tạo `OAuth2AuthorizeRequest` cho registration + service principal.
2. `manager.authorize(...)` tải hoặc cấp token theo grant.
3. `switchIfEmpty(...)` ngăn tiếp tục khi manager không trả authorized client.
4. `flatMap(...)` dùng access token vừa có để gọi Reports API.
5. `bodyToMono(DailySummary.class)` decode response.

Đây là thiết kế **server-to-server**. Bearer token **không được trả về browser**.

### 11.1. Bean WebClient chuyên biệt

~~~java
package com.example.portal.reports;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ReportsWebClientConfig {

    @Bean("reportsWebClient")
    WebClient reportsWebClient(
        WebClient.Builder builder,
        @Value("${reports.api.base-url}") String baseUrl
    ) {
        return builder
            .baseUrl(baseUrl)
            .build();
    }
}
~~~

`WebClient.Builder` do Spring Boot cung cấp có thể đã dùng HTTP transport/codec configuration của app. Với production, thêm timeout, TLS, proxy và observability phù hợp; không dùng dynamic base URL do input không tin cậy cung cấp.

### 11.2. Giới hạn tác dụng của Bearer token

Mẫu `headers.setBearerAuth(...)` gắn token vào đúng request. Nếu WebClient có thể gọi **URL tuyệt đối** từ dữ liệu bên ngoài, một request tới host độc hại có thể làm lộ token.

Giới hạn các request tới Reports API bằng **base URL/allowed destinations** cố định và không tự động gửi Bearer qua redirect sang host không được tin cậy.

## 12. Có thể dùng ServerOAuth2AuthorizedClientExchangeFilterFunction không?

WebClient của Spring Security Reactive có:

~~~java
org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction
~~~

Filter có constructor nhận `ReactiveOAuth2AuthorizedClientManager`. Nó có thể giải quyết authorized client khi WebClient gọi API, tùy request attributes/principal context.

Tuy nhiên, **background job không có WebFlux request và thường không có ReactiveSecurityContextHolder của user**. Nếu dùng OAuth2 filter thay vì explicit `manager.authorize(...)`, cần cung cấp **clientRegistrationId và principal context đáng tin cậy** theo API của phiên bản Spring Security, đồng thời kiểm tra filter có làm việc với service-based manager không cần ServerWebExchange.

Ví dụ cấu hình cơ bản:

~~~java
ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServerOAuth2AuthorizedClientExchangeFilterFunction(
        reportsAuthorizedClientManager
    );

WebClient client = WebClient.builder()
    .baseUrl("https://reports.example.test")
    .filter(oauth2)
    .build();
~~~

Đoạn này mới **gắn filter**. Khi gọi API, vẫn phải chọn registration và cung cấp principal context phù hợp. Đối với một scheduled job đơn giản, mẫu **explicit manager.authorize + setBearerAuth** ở mục 11 thường dễ kiểm soát và test hơn.

**Không dùng `ServletOAuth2AuthorizedClientExchangeFilterFunction` hoặc `HttpServletRequest` trong một background WebFlux service để giải quyết token.**

## 13. @Scheduled với reactive return type: không subscribe thủ công bừa bãi

Từ **Spring Framework 6.1+**, Spring scheduling hỗ trợ các method trả `Publisher`, ví dụ `Mono<Void>`. Framework lấy Publisher và đăng ký subscription theo lịch đã cấu hình.

Ví dụ:

~~~java
package com.example.portal.reports;

import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableScheduling
public class SchedulingConfig {
}
~~~

Job:

~~~java
package com.example.portal.reports;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ReportsScheduler {

    private final ReportsGateway gateway;
    private final ReportsPersistence persistence;

    public ReportsScheduler(
        ReportsGateway gateway,
        ReportsPersistence persistence
    ) {
        this.gateway = gateway;
        this.persistence = persistence;
    }

    @Scheduled(
        fixedDelayString = "${reports.job.fixed-delay-ms:60000}"
    )
    public Mono<Void> run() {
        return Mono.defer(() ->
            gateway.fetchDailySummary()
                .flatMap(persistence::saveSummary)
        );
    }
}
~~~

`ReportsPersistence` là abstraction do ứng dụng tự định nghĩa; giả sử `saveSummary(DailySummary)` trả `Mono<Void>`. Nếu persistence dùng JDBC blocking, không gọi trực tiếp trên Reactor event loop; phải dùng một cơ chế scheduling phù hợp hoặc một storage client không blocking.

### 13.1. Vì sao có Mono.defer()?

Reactive scheduling có đặc điểm: Publisher được tạo một lần khi framework đăng ký scheduled task, rồi được **subscribe lại** theo mỗi chu kỳ.

`Mono.defer(...)` bảo đảm mỗi subscription tạo lại phần việc:

~~~text
Chu kỳ 01 -> defer -> manager.authorize -> gọi Reports API
Chu kỳ 02 -> defer -> manager.authorize -> gọi Reports API
Chu kỳ 03 -> defer -> manager.authorize -> gọi Reports API
~~~

Nếu code tạo token request, timestamp, job input hoặc side effect **eager** ở thời điểm tạo Publisher, công việc có thể không được tính lại như mong muốn. `Mono.defer` giúp ranh giới **mỗi lần thực thi** rõ ràng hơn.

### 13.2. Error signal trong reactive scheduled task

Lỗi từ token endpoint hoặc Reports API đi qua Reactor error signal. Reactive scheduled processing của Spring ghi nhận lỗi theo cơ chế scheduling, nhưng **không nên dựa chỉ vào log mặc định** khi job có SLA hoặc cần cảnh báo.

Ví dụ:

~~~java
return Mono.defer(() -> gateway.fetchDailySummary()
    .flatMap(persistence::saveSummary))
    .doOnError(error ->
        metrics.recordFailure("reports-scheduler", error))
    .onErrorResume(error ->
        notificationService.alertJobFailure(error)
            .then(Mono.empty()));
~~~

`metrics` và `notificationService` là dịch vụ ứng dụng tự định nghĩa, không phải Spring Security APIs. Chỉ trả `Mono.empty()` sau khi đã ghi nhận failure nếu đó thực sự là business policy; không biến lỗi hệ thống thành “job hoàn thành thành công” mà không có audit.

### 13.3. Spring Framework cũ hơn thì sao?

Nếu đang ở phiên bản Spring Framework không hỗ trợ reactive return types trong `@Scheduled`, cần một **scheduler adapter** hoặc một runtime quản lý subscription rõ ràng. Không chỉ viết `@Scheduled public Mono<Void> run()` rồi mặc định framework sẽ subscribe nếu phiên bản không hỗ trợ.

Nếu phải tự `subscribe()`, cần quản lý `Disposable`, error callback, cancellation/shutdown và concurrency; tránh fire-and-forget mà application không thể theo dõi tiến trình.

## 14. Fixed-delay, cron và nhiều lần chạy chồng nhau

Hai cấu hình:

~~~java
@Scheduled(fixedDelayString = "${reports.job.fixed-delay-ms}")
~~~

và:

~~~java
@Scheduled(
    cron = "0 0 1 * * *",
    zone = "Asia/Ho_Chi_Minh"
)
~~~

có semantics khác nhau:

- **Fixed delay:** khoảng thời gian sau khi lần chạy trước hoàn tất theo quy tắc scheduler.
- **Cron:** thời điểm khởi chạy theo biểu thức và múi giờ được chỉ định.

Với tác vụ reactive, cần hiểu cách scheduler subscribe/chờ hoàn thành publisher trong phiên bản đang sử dụng. Nếu một job kéo dài quá chu kỳ hoặc chạy trên nhiều replicas, có thể có **overlap**.

### 14.1. @Scheduled không phải distributed lock

Hai instances cùng chạy:

~~~text
Node A 01:00 -> Reports Job
Node B 01:00 -> Reports Job
~~~

Mỗi node có thể xin access token và gọi Reports API. Nếu việc tổng hợp báo cáo chỉ được phép chạy một lần, cần **distributed lock/leader election/queue consumer group/idempotency** ở tầng nghiệp vụ.

Manager OAuth2 **không tự bảo đảm exactly-once execution**. Nó chỉ quản lý authorized client.

### 14.2. Không dùng token cache làm khóa lịch chạy

Việc cả hai job cùng dùng `(reports-service, reports-scheduler)` không chứng minh chỉ có một job đang chạy. Authorized-client service chỉ lưu token và không phải cơ chế độc quyền của một scheduled task.

## 15. Vòng đời token của client_credentials

Giả sử Authorization Server cấp:

~~~text
01:00:00  AT-1 issued, expiresAt = 01:05:00.
01:01:00  Job chạy, manager có thể tái sử dụng AT-1.
01:04:30  Job chạy, manager thấy AT-1 sắp hết hạn theo clock skew.
01:04:31  Provider client_credentials xin AT-2.
01:05:00  AT-1 hết hạn.
~~~

Đây là ví dụ; thời điểm thực tế tùy expiresAt, clock skew, manager/provider configuration và lúc có ai **gọi manager**.

### 15.1. Không có refresh token vẫn lấy token mới được

Với `client_credentials`, khi AT-1 hết hạn, provider xin **access token mới bằng client_credentials grant**. Không cần có `refresh_token`.

~~~text
Authorization Code + Refresh Token:
  access token hết hạn
  -> dùng refresh token nếu còn hợp lệ

Client Credentials:
  access token hết hạn
  -> client authenticate ở token endpoint để xin access token mới
~~~

Đừng thêm scope `offline_access` chỉ với mục đích “bắt buộc có refresh token” cho mọi client credentials registration. Cách cấp và vòng đời token phải theo hợp đồng Authorization Server.

### 15.2. Giữ token tới lúc hết hạn không nhất thiết tốt

Token có thể mất một khoảng thời gian để đến Resource Server. Nếu chỉ xin token mới khi `Instant.now() > expiresAt`, request có thể tới API khi token vừa hết hạn.

Provider thường sử dụng **clock skew** để xem token là sắp hết hạn và cấp lại sớm hơn.

## 16. Tùy chỉnh provider client_credentials và clock skew

Khi cần kiểm soát thời điểm cấp token mới:

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.client
    .ClientCredentialsReactiveOAuth2AuthorizedClientProvider;

ClientCredentialsReactiveOAuth2AuthorizedClientProvider provider =
    new ClientCredentialsReactiveOAuth2AuthorizedClientProvider();

provider.setClockSkew(Duration.ofSeconds(60));
~~~

Sau đó gắn provider vào service manager:

~~~java
AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
    new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
        registrations,
        authorizedClientService
    );

manager.setAuthorizedClientProvider(provider);
~~~

Ở đây `registrations` và `authorizedClientService` là những dependency như ở mục 8. Đoạn code này minh họa **phương án thay thế cách tạo provider bằng builder**, không phải cấu hình manager thứ hai cùng tên trong application.

**Clock skew** làm provider xem access token sắp hết hạn sớm hơn, **không** thay:

- Thời hạn access token do Authorization Server cấp.
- Session timeout của web user.
- TTL của refresh token (nếu có).
- Chính sách quyền ở Resource Server.

Nếu access token chỉ sống 90 giây mà clock skew 60 giây, job có thể xin token lại thường xuyên. Hãy chọn theo token lifetime, network latency và giới hạn của token endpoint.

## 17. Tùy chỉnh HTTP token response client trong Reactive

Provider client_credentials cần HTTP client chuyên gọi Authorization Server token endpoint. Spring Security có implementation:

~~~java
org.springframework.security.oauth2.client.endpoint
    .WebClientReactiveClientCredentialsTokenResponseClient
~~~

Ví dụ cấu hình token WebClient với Reactor Netty:

~~~java
import java.time.Duration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.oauth2.client.endpoint
    .WebClientReactiveClientCredentialsTokenResponseClient;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

HttpClient httpClient = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(5));

WebClient tokenWebClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .build();

WebClientReactiveClientCredentialsTokenResponseClient tokenClient =
    new WebClientReactiveClientCredentialsTokenResponseClient();

tokenClient.setWebClient(tokenWebClient);
~~~

Sau đó:

~~~java
ClientCredentialsReactiveOAuth2AuthorizedClientProvider provider =
    new ClientCredentialsReactiveOAuth2AuthorizedClientProvider();

provider.setAccessTokenResponseClient(tokenClient);
provider.setClockSkew(Duration.ofSeconds(30));
~~~

**Đây là cấu hình token endpoint transport**, không phải HTTP client đi gọi Reports API.

~~~text
WebClient A: Authorization Server token endpoint
  -> POST /token, client_credentials

WebClient B: Reports Resource Server
  -> GET /api/daily-summary, Bearer access token
~~~

Tùy chỉnh timeout của WebClient B **không tự thay** timeout của WebClient A. Cả hai cần timeout/TLS/proxy độc lập theo yêu cầu.

### 17.1. Không tắt TLS verification

Đừng khắc phục lỗi token endpoint bằng cách chấp nhận mọi certificate. Client secret và token response là dữ liệu nhạy cảm; phải sử dụng HTTPS, truststore/CA hợp lệ và mTLS khi provider yêu cầu.

Không bật wire logging chứa `Authorization: Basic ...`, client secret hoặc access token response trong production.

## 18. Khi manager trả Mono.empty()

Code không nên giả định `authorize()` luôn phát token:

~~~java
return manager.authorize(request)
    .switchIfEmpty(Mono.error(
        new IllegalStateException(
            "No authorized client for reports-service"
        )
    ));
~~~

Một số nguyên nhân:

- Không có `ClientRegistration` khớp.
- Registration có grant không được provider chain hỗ trợ.
- Context không cung cấp dữ liệu grant cần thiết.
- Manager/provider không tạo được authorized client theo contract nhưng không phát lỗi.

**Không fallback sang access token của registration khác**. Việc job cần `reports.read` không cho phép tự dùng token của một user đang login với `openid profile`.

### 18.1. Nếu cần fail-fast cho cấu hình

Application có thể xác nhận khi khởi động rằng registration `reports-service` tồn tại và có grant `client_credentials`. Kiểm tra metadata sớm giúp phát hiện sai cấu hình trước khi job chạy.

Nhưng **không cần xin token production ngay ở startup** nếu policy không yêu cầu; startup token request có thể khiến ứng dụng không khởi động khi IdP tạm gián đoạn. Cân nhắc readiness và dependency policy thay vì hard-fail không kiểm soát.

## 19. Lỗi token endpoint phải được phân loại

Một request:

~~~http
POST /oauth2/token HTTP/1.1
Authorization: Basic <redacted>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
~~~

có thể thất bại:

| Lỗi | Nguyên nhân thường gặp | Xử lý phù hợp |
|---|---|---|
| `invalid_client` | Client secret/ID/mTLS/client authentication sai | Kiểm tra cấu hình/rotate secret, cảnh báo vận hành |
| `unauthorized_client` | Client không được phép dùng grant này | Kiểm tra registration và policy Authorization Server |
| `invalid_scope` | Scope không được phép | Sửa cấu hình scope/policy |
| HTTP 429 | Token endpoint rate limiting | Backoff/rate limit, không retry ồ ạt |
| HTTP 500/503 | Authorization Server sự cố | Retry có giới hạn, phù hợp deadline |
| TLS handshake failure | Sai CA/certificate/proxy/mTLS | Sửa transport, không tắt xác minh TLS |
| Timeout | Server/network chậm | Kiểm soát timeout, retry chỉ với điều kiện an toàn |
| Reactive storage failure | Không thể đọc/ghi authorized client | Kiểm tra store, không làm mất lỗi qua fallback token giả |

Đối với **client_credentials**, `invalid_grant` không phải lỗi phổ biến như refresh-token grant, vì flow này không gửi authorization code hoặc refresh token. Khi lỗi xuất hiện, hãy xem error code thực tế và hợp đồng provider thay vì suy đoán.

### 19.1. Không nuốt lỗi rồi trả token cũ

Tránh:

~~~java
return manager.authorize(request)
    .onErrorResume(error -> Mono.just(oldAuthorizedClient));
~~~

Token cũ có thể đã bị thu hồi hoặc không còn đúng scope/audience. Nếu policy cho phép sử dụng một token còn hạn khi token endpoint tạm gián đoạn, phải có điều kiện rõ và kiểm tra sự chấp nhận của Resource Server; không dùng fallback mù quáng.

### 19.2. Lỗi grant không giống lỗi Reports API

~~~text
Token endpoint:
  không cấp access token cho Reports Job

Reports API:
  nhận access token nhưng trả 401/403/500
~~~

Hai nguồn lỗi cần metric, retry và error handling riêng. Không gửi retry `GET /api/daily-summary` khi job chưa lấy được token hợp lệ.

## 20. Xử lý HTTP 401/403 từ Reports API

Reports API có thể trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Hoặc:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
                  scope="reports.admin"
~~~

Khác biệt:

- **401 invalid_token:** token được gửi bị Resource Server từ chối; cần xem authorized client có còn hợp lệ không, có bị revoked, sai audience hoặc expiry không.
- **403 insufficient_scope:** token có thể hợp lệ nhưng không có quyền mong muốn; xin token mới cùng registration/scope không nhất thiết sửa được.

Một job có thể **loại authorized client không hợp lệ** theo policy và thử cấp token mới bằng client_credentials. Nhưng không retry vô hạn: nếu issuer/audience/client policy sai, token mới vẫn có thể bị từ chối.

**Xóa local authorized client** không đồng nghĩa gửi revocation tới Authorization Server. Với machine client, các quyết định revoke/rotate credentials cần quy trình bảo mật và vận hành riêng.

## 21. Retry và timeout trong background workflow

Background job không có browser chờ response, nhưng vẫn cần **deadline** để không chiếm tài nguyên vô thời hạn.

Ví dụ xử lý API GET với giới hạn:

~~~java
import java.time.Duration;
import org.springframework.web.reactive.function.client
    .WebClientResponseException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public Mono<DailySummary> fetchWithRetry() {
    Retry retry = Retry.backoff(2, Duration.ofMillis(250))
        .maxBackoff(Duration.ofSeconds(1))
        .jitter(0.3)
        .filter(error ->
            error instanceof WebClientResponseException response
                && (
                    response.getStatusCode().value() == 502
                    || response.getStatusCode().value() == 503
                    || response.getStatusCode().value() == 504
                )
        );

    return fetchDailySummary()
        .timeout(Duration.ofSeconds(3))
        .retryWhen(retry)
        .timeout(Duration.ofSeconds(8));
}
~~~

**Lưu ý:** đây là ví dụ ý tưởng giới hạn retry cho **GET**. Trong lớp `ReportsGateway` ở mục 11, `fetchDailySummary()` bao gồm cả `manager.authorize()`, nên retry toàn pipeline có thể gọi manager lại. Nếu muốn retry **chỉ HTTP downstream**, đặt retry tại phần WebClient call sau khi đã giải quyết token và phân loại error.

Không retry lỗi client credentials như `invalid_client`, `unauthorized_client` hoặc `invalid_scope` theo cùng chính sách 502/503.

### 21.1. Retry POST hoặc ghi báo cáo

Nếu job gửi:

~~~http
POST /api/reports/generate HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{"period":"2026-11"}
~~~

và timeout sau khi server đã tạo report, retry có thể gây **hai report/side effect**.

Đối với thao tác ghi, cần idempotency key/business operation ID và contract deduplication từ Reports API. Timeout không chứng minh downstream chưa xử lý yêu cầu.

## 22. Nhiều job dùng chung một client registration

Giả sử:

~~~text
ReportsJobA: job tổng hợp doanh thu
ReportsJobB: job tổng hợp vận hành
ReportsJobC: job lấy analytics
~~~

Cả ba gọi manager với:

~~~text
registrationId = reports-service
principalName = reports-scheduler
~~~

Chúng có thể dùng cùng một authorized client/tokens **nếu thật sự cùng service identity, cùng scopes và cùng security policy**.

Ưu điểm:

- Giảm số lần xin token không cần thiết.
- Tái sử dụng token khi còn hạn.
- Có thể chia sẻ lifecycle/persistence của service principal.

Rủi ro:

- Một job có thể có quyền rộng hơn cần thiết nếu tất cả dùng cùng client.
- Concurrent requests có thể cùng xin token mới.
- Lỗi cleanup của một job có thể ảnh hưởng token còn dùng được của job khác.
- Nếu jobs thuộc tenant khác nhau, dùng chung token có thể phá vỡ isolation.

**Nguyên tắc least privilege:** không phải cứ dễ chia sẻ là nên chia sẻ. Nếu hai job có quyền/tenant khác nhau, cân nhắc tách registrations hoặc scope/security policy rõ ràng.

## 23. Multi-tenant và service principal

Giả sử hệ thống phục vụ nhiều tenant:

~~~text
Tenant A -> Reports API cho A
Tenant B -> Reports API cho B
~~~

Không suy rằng:

~~~text
principalName = tenant-A
~~~

tự làm token trở thành “token của tenant A”. Chuỗi principal chỉ là **storage key** trong OAuth2 Client; Authorization Server và Reports API không mặc nhiên tin nó.

Nếu mỗi tenant có OAuth client credential/issuer riêng, cần cấu hình registrations và authorized-client storage phân tách theo security policy. Nếu dùng chung service credential, API phải xác minh tenant/resource authorization độc lập; không tin tenant ID do job tự gửi mà không kiểm tra.

**Đừng dùng registration ID do queue message không tin cậy chỉ định tự do** để chọn một token có quyền cao hơn. Job input phải được xác thực/ủy quyền và mapping sang registration do backend quản lý.

## 24. Tác vụ chạy thay mặt người dùng: khác client_credentials

Một số worker không chạy bằng machine identity mà cần gọi API **thay mặt nhân viên đã cấp consent**. Ví dụ nhân viên chủ động lên lịch xuất dữ liệu cá nhân.

Khi đó:

~~~text
User thực hiện Authorization Code Flow trước đó
  -> Ứng dụng lưu authorized client của user với consent phù hợp
  -> Background worker cần sử dụng refresh token (nếu được cấp)
  -> Worker gọi API theo danh tính user đã được cấp quyền
~~~

Về mặt kỹ thuật, service-based reactive manager có thể được cấu hình với `refreshToken()` provider để xử lý một **existing authorized client** có refresh token và principal tương ứng.

Nhưng cần đáp ứng các điều kiện bảo mật:

1. **User đã cấp quyền rõ ràng** cho tác vụ nền theo chính sách.
2. Token/refresh token được lưu an toàn, có giới hạn retention.
3. Job xác định đúng user và scopes đã được cấp, không tự chọn principal name khác.
4. Có cơ chế ngừng xử lý khi user hủy lịch, revoke consent, disable account hoặc hết hiệu lực authorization.
5. Không coi refresh token là bằng chứng user vẫn đăng nhập WebFlux session.
6. Không tự tạo token bằng `sub` hoặc email.

### 24.1. Provider chain cho existing user authorized client

~~~java
ReactiveOAuth2AuthorizedClientProvider provider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .refreshToken()
        .build();
~~~

Đây là **một phương án cho trường hợp khác**, không nên thay provider `clientCredentials()` của Reports Job nếu Reports Job cần machine identity.

Lưu ý: refresh provider chỉ làm việc khi **authorized client có refresh token**. Không thể bắt đầu Authorization Code Flow tương tác từ một scheduled job không có browser chỉ bằng cách gắn thêm `.authorizationCode()`.

### 24.2. Khi nào không nên dùng token của người dùng trong job?

Nếu chỉ cần thống kê hệ thống với quyền dịch vụ tối thiểu, thường sử dụng `client_credentials` với scopes rõ ràng sẽ đơn giản hơn và tránh phụ thuộc refresh token của từng người.

Ngược lại, nếu dữ liệu cần quyền/consent riêng của từng user, **machine token không được mặc nhiên thay user token** để vượt qua authorization.

## 25. Authenticated user trong WebFlux và job không có SecurityContext

Trong một request WebFlux, principal có thể lấy từ Reactor SecurityContext:

~~~java
ReactiveSecurityContextHolder.getContext()
    .map(context -> context.getAuthentication());
~~~

Nhưng trong một job chạy từ scheduler:

~~~text
Không có user request
Không có browser cookie
Không có WebSession/ServerWebExchange
Không có SecurityContext của user mặc định
~~~

Do đó, không nên:

~~~java
// Sai kỳ vọng trong scheduled job:
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

`SecurityContextHolder` với ThreadLocal không phải cơ chế tìm user trong một pipeline Reactive background task. Nếu job cần user consent, phải nhận một **định danh user đã được ứng dụng ủy quyền** từ job payload đã xác minh và ánh xạ tới authorized client đúng policy.

### 25.1. Đừng giả lập Authentication cho người khác

Tạo một `Authentication` với username "admin" không chứng minh job được phép dùng admin token. OAuth2AuthorizedClientService lưu token theo principal name; đó là **chỉ số truy vấn**, không phải cơ chế chứng minh identity.

Nếu app có API kích hoạt job, cần authorization trên API đó trước khi enqueue; queue messages và worker cũng cần tính toàn vẹn/identity context thích hợp.

## 26. Manager không thay thế Token Response Client

`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` **điều phối** authorized client. Nó không trực tiếp là một HTTP client POST token endpoint.

Tầng:

~~~text
AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
    |
    +--> ReactiveOAuth2AuthorizedClientProvider
            |
            +--> ReactiveOAuth2AccessTokenResponseClient<...>
                    |
                    +--> WebClient HTTP POST /token
~~~

Với `client_credentials`, token-response client tương ứng:

~~~java
ReactiveOAuth2AccessTokenResponseClient<
    OAuth2ClientCredentialsGrantRequest
>
~~~

Với refresh-token grant, kiểu request tương ứng là `OAuth2RefreshTokenGrantRequest`. Không dùng token response client của Authorization Code Flow chỉ vì nó cũng trả access token.

## 27. Failure handler và cleanup authorized client

Manager có thể áp dụng các **authorization success/failure handlers** để lưu hoặc loại authorized client theo kết quả và chính sách. Khi dùng implementation mặc định, cần hiểu hành vi của version đang chạy trước khi thay handler.

Một số tình huống:

| Lỗi | Có xóa token không? |
|---|---|
| `invalid_client` ở token endpoint | Không xóa mọi token của mọi user/service; đây có thể là lỗi cấu hình/secret |
| Access token cũ hết hạn, xin token mới thành công | Lưu authorized client mới |
| `invalid_grant` khi refresh user token | Có thể loại authorized client lỗi theo policy |
| Reports API trả `401 invalid_token` | Có thể cleanup token service tương ứng nếu xác định đúng lỗi |
| Reports API trả `403 insufficient_scope` | Token có thể hợp lệ; không tự cleanup chỉ vì thiếu scope |
| Reports API trả `503` | Không đủ bằng chứng token sai |
| Token store timeout | Không tự thay bằng token giả hoặc xóa tất cả |

**Loại authorized client cục bộ** không đồng nghĩa **revoke token** tại Authorization Server. Nếu service credential bị lộ, cần kế hoạch thu hồi/rotate credential thực tế; xóa một row trong store không đủ khắc phục sự cố.

### 27.1. Lỗi của background job không nên làm user logout

Nếu Reports Job bị từ chối token, các nhân viên vẫn có thể tiếp tục đăng nhập Employee Portal. Đó là hai security contexts và client registrations khác nhau.

Đừng hủy mọi WebSession chỉ vì `reports-service` gặp `invalid_client` hoặc 503 từ Authorization Server.

## 28. Multi-instance và race khi cùng cấp token

Hai replicas:

~~~mermaid
sequenceDiagram
    participant A as Job Node A
    participant B as Job Node B
    participant S as Authorized Client Store
    participant AS as Authorization Server

    A->>S: load(reports-service, reports-scheduler)
    B->>S: load(reports-service, reports-scheduler)
    S-->>A: Token cũ/sắp hết hạn
    S-->>B: Token cũ/sắp hết hạn
    A->>AS: client_credentials
    B->>AS: client_credentials
    AS-->>A: AT-2
    AS-->>B: AT-3
    A->>S: save(AT-2)
    B->>S: save(AT-3)
~~~

Với client credentials, hai lần xin token mới có thể đều hợp lệ nhưng làm tăng tải Authorization Server và khiến lưu trữ token bị cập nhật liên tiếp.

Các hướng xử lý:

- Dùng storage chia sẻ khi thật sự cần chia sẻ authorized client giữa nodes.
- Giới hạn concurrency bằng lock/single-flight theo registration/principal, nếu giá trị và tải yêu cầu.
- Có client-side rate limiting và backoff cho token endpoint.
- Không dùng local `synchronized` để kỳ vọng khóa hoạt động trên nhiều replicas.
- Tách **điều phối job exactly-once** khỏi **điều phối token**.

### 28.1. Nếu flow sử dụng refresh token rotation

Với background job thực sự chạy thay mặt user bằng refresh token, hai requests dùng cùng RT-1 có thể dẫn đến `invalid_grant`, hoặc cơ chế reuse detection tại OP.

Trường hợp đó cần consistency/locking và lưu RT mới. **Client credentials thường không có refresh token**, nên rủi ro rotation không phải trường hợp mặc định của Reports Job trong bài.

## 29. Storage, bảo mật và secret rotation

Một service có thể chạy nhiều tháng nên cần quản lý **client credential**:

1. Lưu `client-secret` trong secret manager/secret store có quyền hạn rõ.
2. Không đưa secret vào source code hoặc CI logs.
3. Có quy trình rotate secret/certificate mà không dừng toàn bộ hệ thống không cần thiết.
4. Quan sát `invalid_client` sau rotation.
5. Bảo vệ token store bằng access control, TLS và encryption nếu chính sách yêu cầu.
6. Tránh đặt token trong metrics labels, exception messages hoặc HTTP access logs.
7. Không trả access token/refresh token qua API “debug” cho frontend.
8. Giới hạn egress tới token endpoint và Resource Server đã allowlist.

**Không sửa lỗi TLS bằng cách bỏ kiểm tra certificate**. Điều đó làm client secret và access token dễ bị lộ qua man-in-the-middle.

### 29.1. Client assertion/mTLS

Một số Authorization Server yêu cầu client authentication bằng mTLS hoặc private_key_jwt thay vì `client_secret_basic`. Khi đó cấu hình registration/token response transport phải đúng hợp đồng. Manager cấp token vẫn có thể là `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`, nhưng **token response client** và client authentication method cần được cấu hình phù hợp.

## 30. Giám sát tác vụ nền bằng metric và audit

Job có thể thất bại khi không có ai đang sử dụng giao diện. Vì vậy, log/metrics và cảnh báo quan trọng hơn một thông điệp popup.

Nên quan sát:

| Metric/event | Ý nghĩa |
|---|---|
| Job triggered | Scheduler thực sự kích hoạt |
| Authorization attempted | Manager được gọi |
| Token acquisition success | Access token được cấp hoặc tái sử dụng |
| Token endpoint latency | Độ chậm IdP |
| Authorized-client load/save failure | Lỗi persistence |
| HTTP 401/403 từ Reports API | Token invalid hoặc thiếu quyền |
| HTTP 429/503 từ Reports API | Rate limit/outage |
| Job success/failure | Kết quả nghiệp vụ cuối cùng |
| Job duration | Độ trễ, so với schedule và SLO |
| Overlapping executions | Các lần chạy chồng nhau |
| Stale report age | Báo cáo đã cũ bao lâu |

Không ghi:

~~~text
client_secret=<real-secret>
access_token=<real-token>
refresh_token=<real-token>
Authorization: Bearer <real-token>
~~~

Nên ghi registration ID đã được kiểm soát, error code, duration, correlation ID, job ID. Không dùng token hoặc email user làm metric label vì rò rỉ thông tin và cardinality cao.

## 31. Testing manager khi không có HTTP request

Để kiểm thử đúng trọng tâm, test cần chứng minh:

1. Manager cấp token mà **không có ServerWebExchange**.
2. `OAuth2AuthorizeRequest` dùng đúng registration và service principal.
3. Manager sử dụng service-based storage.
4. Khi access token còn hạn, provider không xin token mới không cần thiết.
5. Khi access token cần cấp lại, provider `clientCredentials()` làm việc.
6. Lỗi token endpoint đi qua Reactor error signal.
7. Job thực sự dùng token từ manager để gọi Reports API.
8. Không có sự phụ thuộc vào user login/HTTP session.

### 31.1. Test bằng StepVerifier với fake manager

Ví dụ tạo authorized client giả để test ReportsGateway:

~~~java
import java.time.Instant;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReportsGatewayTest {

    @Test
    void managerCanProvideServiceAuthorizedClientWithoutWebExchange() {
        ClientRegistration registration =
            ClientRegistration.withRegistrationId("reports-service")
                .clientId("test-service")
                .clientSecret("test-secret")
                .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri("https://login.example.test/token")
                .scope("reports.read")
                .build();

        Instant now = Instant.now();
        OAuth2AccessToken accessToken = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "FAKE_SERVICE_TOKEN",
            now.minusSeconds(10),
            now.plusSeconds(300),
            Set.of("reports.read")
        );

        OAuth2AuthorizedClient client = new OAuth2AuthorizedClient(
            registration,
            "reports-scheduler",
            accessToken
        );

        ReactiveOAuth2AuthorizedClientManager fakeManager =
            request -> Mono.just(client);

        StepVerifier.create(fakeManager.authorize(
                org.springframework.security.oauth2.client
                    .OAuth2AuthorizeRequest
                    .withClientRegistrationId("reports-service")
                    .principal("reports-scheduler")
                    .build()
            ))
            .assertNext(actual ->
                org.junit.jupiter.api.Assertions.assertEquals(
                    "reports-scheduler", actual.getPrincipalName()
                ))
            .verifyComplete();
    }
}
~~~

Test trên kiểm tra **contract/service principal** của fake manager. Nó **không chứng minh** một manager thực sự gửi HTTP tới Authorization Server. Trong integration test, cần sử dụng manager thật với token-response client mock hoặc mock HTTP server để xác nhận grant logic.

### 31.2. Test HTTP Authorization header

Sử dụng một mock WebClient `ExchangeFunction` để quan sát request mà không gọi mạng:

~~~java
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReportsHttpTest {

    @Test
    void sendsBearerTokenToExpectedReportsEndpoint() {
        AtomicReference<String> authorization = new AtomicReference<>();

        ExchangeFunction fakeHttp = request -> {
            authorization.set(
                request.headers().getFirst(HttpHeaders.AUTHORIZATION)
            );
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .body("{\"total\":7}")
                .build());
        };

        WebClient reportsWebClient = WebClient.builder()
            .baseUrl("https://reports.example.test")
            .exchangeFunction(fakeHttp)
            .build();

        StepVerifier.create(reportsWebClient.get()
            .uri("/api/daily-summary")
            .headers(headers -> headers.setBearerAuth("FAKE_SERVICE_TOKEN"))
            .retrieve()
            .bodyToMono(String.class))
            .expectNext("{\"total\":7}")
            .verifyComplete();

        assertEquals("Bearer FAKE_SERVICE_TOKEN", authorization.get());
    }
}
~~~

Đây là test của **HTTP header behavior**, không phải test full manager. Test tích hợp quan trọng hơn là gắn cả fake manager và mock WebClient vào `ReportsGateway`, xác nhận registration ID/principal chính xác và token không bị gửi đến host khác.

### 31.3. Test lỗi và empty Publisher

~~~java
ReactiveOAuth2AuthorizedClientManager emptyManager =
    request -> Mono.empty();

ReactiveOAuth2AuthorizedClientManager failingManager =
    request -> Mono.error(
        new IllegalStateException("Simulated token failure")
    );
~~~

Kiểm tra ReportsGateway:

- Khi manager `Mono.empty()`: không được gọi Reports API.
- Khi manager `Mono.error(...)`: lỗi được truyền và job ghi nhận failure.
- Khi manager trả client: request chứa đúng Bearer token giả.
- Không sử dụng token của user khác để “fallback”.

### 31.4. Test @Scheduled reactive

Đối với `@Scheduled` của Spring Framework 6.1+, test cần xác nhận **mỗi lần subscribe thực thi lại logic** trong `Mono.defer(...)`, không dùng lại một kết quả cũ do tạo publisher eager.

Nếu cần test lịch ở mức integration, dùng cấu hình scheduler/test clock phù hợp và tránh sleep dài gây flaky CI. Đừng chỉ assert method trả `Mono<Void>` rồi coi như job đã thực sự chạy.

## 32. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Job lỗi vì thiếu `ServerWebExchange` | Dùng `DefaultReactiveOAuth2AuthorizedClientManager` cho task nền | Dùng service-based reactive manager |
| Có bean manager nhưng job không dùng | Không inject đúng bean hoặc không gọi authorize | Kiểm tra constructor injection/qualifier |
| Job không bao giờ lấy token | `Mono` không được subscribe hoặc @Scheduled phiên bản cũ không hỗ trợ Publisher | Kiểm tra Reactor lifecycle/Spring Framework version |
| Mỗi lần chạy lại xin token dù AT còn hạn | principal name không ổn định, storage không bền hoặc provider/clock skew | Kiểm tra key, expiresAt, store |
| `Mono.empty()` từ manager | Grant không phù hợp hoặc thiếu registration/context | Kiểm tra provider chain và request |
| `invalid_client` | Client secret/ID/mTLS sai | Kiểm tra secrets và token endpoint config |
| `unauthorized_client` | Client chưa được phép dùng client_credentials | Kiểm tra AS policy |
| `invalid_scope` | Scope reports.read không được cấp | Kiểm tra ClientRegistration/AS permissions |
| Reports API trả 401 | Token sai audience/revoked/expired | Kiểm tra Bearer error và manager lifecycle |
| Reports API trả 403 | Scope hoặc resource permission không đủ | Không retry bừa, kiểm tra authorization |
| Token endpoint timeout | Network/IdP chậm | Kiểm tra HTTP token response client, không chỉ WebClient API |
| Lỗi chỉ khi chạy nhiều nodes | Dùng in-memory store riêng hoặc concurrency | Shared store, locking, idempotency |
| Một job làm token của job khác mất | Dùng chung registration/principal nhưng cleanup thiếu chọn lọc | Tách policy và storage key |
| Job chạy hai lần | Hai replicas cùng @Scheduled hoặc overlap | Distributed lock/queue/idempotency |
| Sau restart job xin token lại | In-memory authorized client service mất state | Bình thường nếu store in-memory |
| Token mất trong logs | HTTP wire logging/debug lộ credential | Tắt raw body/header logging, rotate credential nếu lộ |
| Cấu hình WebClient OAuth2 filter nhưng thiếu principal | Background job không có user SecurityContext | Cung cấp service principal context đúng hoặc gọi manager explicit |
| Job tồn tại nhưng không có báo cáo | Mono lỗi và bị nuốt thành empty | Metrics/audit/error signal rõ ràng |

**Thứ tự điều tra:** kiểm tra **schedule trigger → subscription → OAuth2AuthorizeRequest → manager/provider → authorized-client service → token endpoint → WebClient → Reports API → persistence**.

## 33. Các anti-pattern thường gặp

**1. Dùng manager của request WebFlux trong job không có ServerWebExchange.** Chọn manager dịch vụ.

**2. Lấy `SecurityContextHolder` trong Reactor scheduled job và tin đó là user hiện tại.** Tác vụ nền không có user web context mặc định.

**3. Dùng `client_credentials` như thể user đã cấp consent.** Machine identity và user identity là hai security boundary khác nhau.

**4. Tự POST /token, tự cache token, tự tính expiry bằng logic rời rạc ở mọi job.** Tập trung tại OAuth2 Client manager/provider.

**5. Gọi `.block()` trong event loop.** Dùng Mono/flatMap để không chặn.

**6. Dùng `.subscribe()` fire-and-forget mà không quản lý error/disposal.** Job có thể thất bại âm thầm hoặc không dừng đúng lúc.

**7. Tạo principal name random mỗi lần chạy.** Có thể làm manager liên tục xin token mới do storage key thay đổi.

**8. Dùng user input chọn registration ID và principal name.** Có thể dẫn đến truy cập token không được phép.

**9. Dùng WebClient với URL tùy ý và tự động đính Bearer token.** Có nguy cơ exfiltrate credential.

**10. Cho rằng manager bảo đảm chỉ một job chạy trên nhiều replicas.** OAuth2 token management không phải distributed scheduler.

**11. Retry vô hạn khi token endpoint invalid_client.** Lỗi cấu hình/credential không sửa được bằng retry.

**12. Log raw access token/client secret để debug.** Credential cần bảo vệ và rotate nếu đã lộ.

**13. Coi AT còn hạn là bảo đảm API sẽ chấp nhận.** Audience, scopes, revocation và business permission vẫn được Resource Server kiểm tra.

**14. Coi refresh token là bắt buộc trong client_credentials.** Grant này thường xin access token mới trực tiếp.

## 34. Bài tập thực hành

### Bài tập 1 — Chọn manager cho scheduler

Một job chạy mỗi giờ, dùng client_credentials và không có HTTP request:

~~~text
ReactiveClientRegistrationRepository
ReactiveOAuth2AuthorizedClientService
Reports Job
~~~

**Câu hỏi:** nên sử dụng manager nào?

**Hướng giải:** `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` với provider `clientCredentials()`. Nó không yêu cầu ServerWebExchange.

### Bài tập 2 — Principal name thay đổi

Job đang tạo:

~~~java
.principal(UUID.randomUUID().toString())
~~~

mỗi lần chạy.

**Câu hỏi:** tại sao token có thể không được tái sử dụng?

**Hướng giải:** Authorized-client service lưu theo registration/principal key; mỗi UUID mới có thể được coi là một identity storage mới. Với một service job có cùng quyền, dùng principal name ổn định do backend quản lý.

### Bài tập 3 — Không có refresh token

~~~text
ClientRegistration.grant = client_credentials
OAuth2AuthorizedClient.accessToken = AT-1
OAuth2AuthorizedClient.refreshToken = null
~~~

**Câu hỏi:** job có thể xin access token mới khi AT-1 hết hạn không?

**Hướng giải:** Có, nếu client credentials còn hợp lệ và provider/manager được cấu hình đúng. Manager dùng grant `client_credentials` để xin token mới, không cần refresh token.

### Bài tập 4 — Job không chạy

~~~java
@Scheduled(fixedDelay = 60000)
public Mono<Void> run() {
    return reportsGateway.fetchDailySummary().then();
}
~~~

Ứng dụng dùng Spring Framework cũ và không có reactive scheduling support.

**Câu hỏi:** Có thể mặc định publisher được subscribe không?

**Hướng giải:** Không. Phải xác nhận version hỗ trợ reactive @Scheduled. Nếu không, xây scheduler adapter quản lý subscription/error/cancellation; với Spring Framework 6.1+ nên dùng `Mono.defer` để bảo đảm mỗi subscription thực thi mới.

### Bài tập 5 — API trả 403

Reports API yêu cầu `reports.admin` nhưng token chỉ có `reports.read`.

**Câu hỏi:** retry client_credentials 10 lần có giúp tăng quyền không?

**Hướng giải:** Không. Cần sửa scope/permission theo Authorization Server/Resource Server policy; không dùng retry để nâng quyền.

### Bài tập 6 — Hai nodes cùng chạy cron

Node A và Node B đều chạy Reports Job lúc 01:00 và ghi cùng báo cáo.

**Câu hỏi:** authorized-client manager có ngăn tạo hai báo cáo không?

**Hướng giải:** Không. Manager quản lý access token, không quản lý exactly-once job execution. Cần distributed scheduling lock, queue semantics hoặc idempotency/business deduplication.

### Bài tập 7 — Token endpoint timeout

Team đã tăng timeout của WebClient gọi Reports API, nhưng token endpoint vẫn timeout.

**Câu hỏi:** cần kiểm tra gì?

**Hướng giải:** WebClient/token-response client được provider `clientCredentials()` sử dụng. Nó là HTTP transport khác với WebClient gọi Resource Server.

### Bài tập 8 — Tác vụ thay mặt người dùng

Một nhân viên cấp consent để job xuất dữ liệu cá nhân theo lịch; job cần dùng quyền user.

**Câu hỏi:** có thể chuyển sang `client_credentials` để tránh refresh token không?

**Hướng giải:** Không mặc định. Nếu API yêu cầu user delegation, cần lưu và sử dụng authorized client/refresh token của user theo chính sách consent và revocation. Machine token không tự có quyền người dùng.

## 35. Checklist triển khai

| Câu hỏi | Điều cần bảo đảm |
|---|---|
| Tác vụ có ServerWebExchange không? | Nếu không, dùng service-based manager |
| OAuth client dùng grant gì? | Thường `client_credentials` cho machine-to-machine |
| Registration ID có rõ ràng không? | `reports-service` được backend cấu hình |
| Principal name có ổn định không? | Ví dụ `reports-scheduler`, không do browser tự nhập |
| Có `ReactiveClientRegistrationRepository`? | Có cấu hình issuer/token URI/client ID và grant |
| Có `ReactiveOAuth2AuthorizedClientService`? | Có, storage phù hợp môi trường |
| Provider chain có `clientCredentials()`? | Có cho machine grant |
| Manager là class nào? | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| Mono có được subscribe đúng lifecycle? | Có, không fire-and-forget không quản lý |
| Dùng @Scheduled reactive với version nào? | Spring Framework 6.1+ hoặc adapter phù hợp |
| Mỗi lần scheduled subscribe có thực thi mới? | Sử dụng `Mono.defer` khi cần |
| WebClient có gắn token đúng API không? | Chỉ đúng Reports API/host allowlist |
| Token có scope/audience đúng không? | Kiểm tra AS và Resource Server policy |
| Clock skew có phù hợp? | Dựa token lifetime và network latency |
| Token HTTP transport có timeout/TLS? | Có, tách khỏi Reports API transport |
| Có retry có giới hạn? | Có, phân loại lỗi và idempotency |
| Multi-replica có chạy job trùng không? | Có distributed lock/queue/idempotency nếu cần |
| Authorized-client store có chia sẻ/bảo mật không? | Có nếu kiến trúc yêu cầu |
| Có cơ chế rotation client secret? | Có, kèm cảnh báo invalid_client |
| Có giám sát job thất bại không? | Metrics, logs an toàn, alert |
| Có test không có web context? | Có unit/integration test authorize mà không ServerWebExchange |
| Có test Mono.empty/error/success? | Có StepVerifier và fake token endpoint |

## 36. Tổng kết

`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` là manager **phù hợp cho tác vụ nền trong Spring Security OAuth2 Client Reactive**, nơi không có browser, WebFlux `ServerWebExchange` hoặc user session. Nó phối hợp **`ReactiveClientRegistrationRepository`**, **`ReactiveOAuth2AuthorizedClientService`** và **`ReactiveOAuth2AuthorizedClientProvider`** để tải, cấp và lưu `OAuth2AuthorizedClient` qua pipeline `Mono`.

Với scheduler/queue worker gọi API bằng quyền dịch vụ, thường cấu hình provider `clientCredentials()`, tạo request `OAuth2AuthorizeRequest.withClientRegistrationId("reports-service").principal("reports-scheduler")`, rồi dùng access token do manager trả để gọi Reports API bằng `WebClient`. Không có refresh token cũng là bình thường với grant này; khi token cần thay mới, manager có thể xin access token bằng client credentials một lần nữa.

Để chạy production ổn định, cần phân biệt **manager cho web request** với **manager cho background worker**, giữ principal/registration đúng ranh giới tin cậy, quản lý `Mono` và reactive scheduling, thiết kế timeout/retry, hạn chế job chạy trùng trên nhiều replicas, bảo vệ token/secret và giám sát lỗi Authorization Server. **Token management không phải user login và cũng không phải job orchestration**: mỗi trách nhiệm cần được xử lý ở đúng tầng.
