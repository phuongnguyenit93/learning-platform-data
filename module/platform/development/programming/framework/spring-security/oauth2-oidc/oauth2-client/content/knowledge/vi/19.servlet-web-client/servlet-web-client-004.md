# 19.4. Lựa chọn clientRegistrationId qua request attributes

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, một ứng dụng Servlet (Spring MVC) có thể dùng `WebClient` để gọi API phía sau bằng access token mà Authorization Server đã cấp. Nếu ứng dụng chỉ kết nối với một API, cấu hình mặc định đôi khi đủ dùng. Nhưng khi backend gọi nhiều API, dùng nhiều nhà cung cấp danh tính hoặc có cả token người dùng và token `client_credentials`, ứng dụng cần **chọn chính xác OAuth2 client registration cho từng outbound request**.

Với tích hợp Servlet OAuth2 Client, Spring Security cung cấp `ServletOAuth2AuthorizedClientExchangeFilterFunction`. Một cách phổ biến để chọn registration là truyền một **request attribute** khi xây lệnh gọi `WebClient`:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<String> result = webClient.get()
        .uri("https://reports-api.example.org/v1/reports")
        .attributes(clientRegistrationId("reports-client"))
        .retrieve()
        .bodyToMono(String.class);
```

Đây là điểm cốt lõi của bài: `clientRegistrationId("reports-client")` đưa một giá trị vào **attributes của riêng `ClientRequest`** do `WebClient` tạo ra. Nếu `WebClient` đã được lắp OAuth2 exchange filter phù hợp, filter sẽ dùng thông tin đó để xác định `ClientRegistration`/`OAuth2AuthorizedClient` và gắn access token tương ứng lên HTTP request tới API.

**Đừng nhầm `request attribute` này với HTTP header, query parameter, cookie hoặc thuộc tính của `HttpServletRequest`.** Nó là dữ liệu điều phối nội bộ giữa ứng dụng và các `ExchangeFilterFunction` của `WebClient`; nó không tự trở thành một tham số gửi tới Resource Server.

## 1. Bối cảnh: WebClient trong ứng dụng Servlet

`WebClient` là HTTP client dựa trên Reactor, thường được giới thiệu cùng Spring WebFlux. Tuy nhiên, nó **có thể được dùng trong ứng dụng Spring MVC/Servlet** để gọi API downstream. Trong trường hợp đó:

- Request **đi vào** ứng dụng được xử lý bởi Servlet filter chain và `SecurityContextHolder`.
- Request **đi ra** được tạo bởi `WebClient` và có thể mang bearer access token.
- `ServletOAuth2AuthorizedClientExchangeFilterFunction` kết nối hai thế giới bằng cách dùng ngữ cảnh `Authentication`, Servlet request/response khi có, và `OAuth2AuthorizedClientManager` hoặc repository tương ứng.
- Resource Server ở đầu bên kia vẫn tự xác minh access token theo issuer, audience, thời hạn, scope và chính sách API.

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant M as Spring MVC + SecurityContext
    participant W as WebClient
    participant F as Servlet OAuth2 Exchange Filter
    participant S as Authorized Client Store
    participant OP as Authorization Server
    participant A as Reports API
    B->>M: GET /dashboard/reports
    M->>W: GET Reports API, attribute registrationId
    W->>F: ClientRequest + attributes
    F->>S: Tìm authorized client theo registration + principal
    alt Chưa có hoặc cần tái cấp quyền
        F->>OP: OAuth2 authorize/refresh theo grant và ngữ cảnh
        OP-->>F: Access token mới
        F->>S: Lưu authorized client khi phù hợp
    end
    F->>A: GET /reports, Bearer Access Token
    A-->>W: HTTP response
    W-->>M: Dữ liệu báo cáo
    M-->>B: Dashboard response
```

Sơ đồ mô tả trách nhiệm tổng thể, không ngụ ý mọi registration có thể tự thực hiện flow đăng nhập trong một HTTP call. Với `authorization_code`, việc cấp quyền ban đầu cần browser và Authorization Request/Callback; filter không thể tự giả lập một lần người dùng tương tác với OpenID Provider.

### 1.1. Mục tiêu của lựa chọn tường minh

Một backend có thể sở hữu:

| Registration ID | Grant | Mục đích |
|---|---|---|
| `company-login` | `authorization_code` | Người dùng đăng nhập OIDC qua Corporate OP; có thể dùng access token được cấp cho API phù hợp |
| `partner-login` | `authorization_code` | Người dùng đăng nhập qua Partner OP, có token theo tài khoản đối tác |
| `inventory-service` | `client_credentials` | Backend/job gọi Inventory API với quyền của ứng dụng |
| `audit-service` | `client_credentials` | Backend gọi Audit API bằng tài khoản dịch vụ riêng |

Nếu không chỉ rõ, một default registration có thể được dùng cho các request không phù hợp, hoặc không có registration nào được chọn. Việc đặt `clientRegistrationId` cho từng yêu cầu giúp source code thể hiện rõ **API nào gắn với OAuth2 client nào**.

### 1.2. Chọn client registration khác với chọn tài khoản người dùng

`clientRegistrationId` là khóa mà Spring Security dùng để tìm `ClientRegistration`. Nó không phải:

- `client-id` do Authorization Server phát hành;
- tên `OAuth2AuthorizedClient` của user;
- OIDC `sub` hoặc `iss` trong ID Token;
- authorization `scope` hay `audience`;
- một bearer token có thể truyền vào header;
- ID của browser session.

Thông tin principal và authorized client thực tế vẫn quan trọng. Cùng một `registrationId` có thể tương ứng với authorized clients khác nhau của Alice và Bob, hoặc một service principal dùng trong `client_credentials`.

## 2. ClientRegistration, OAuth2AuthorizedClient và clientRegistrationId

Để hiểu một dòng `.attributes(clientRegistrationId("reports-client"))`, hãy bắt đầu từ ba kiểu dữ liệu của Spring Security.

### 2.1. ClientRegistration

`ClientRegistration` chứa cấu hình OAuth2 client, ví dụ:

```text
registrationId = "reports-client"
clientId       = "reports-portal-prod"
grantType      = "authorization_code"
provider       = "company-idp"
scopes         = ["openid", "profile", "reports.read"]
redirectUri    = "{baseUrl}/login/oauth2/code/{registrationId}"
```

Spring Boot thường đọc cấu hình từ `spring.security.oauth2.client.registration.*` và tạo `ClientRegistrationRepository`.

### 2.2. OAuth2AuthorizedClient

`OAuth2AuthorizedClient` đại diện cho registration **đã được cấp quyền** trong ngữ cảnh principal. Nó giữ registration, principal name, access token và refresh token nếu có. Vì vậy có thể có:

```text
(reports-client, alice) -> Access Token của Alice
(reports-client, bob)   -> Access Token của Bob
(audit-service, service:audit-export) -> Access Token của service
```

`clientRegistrationId(...)` chỉ chọn **registration** cho một call; filter/manager còn phải tìm đúng authorized client theo **principal**, storage và grant.

### 2.3. Request attributes của WebClient

Một `ClientRequest` của WebClient mang URL, HTTP method, headers, body và attributes. `attributes(...)` là DSL dành cho metadata xử lý phía client, ví dụ:

```java
webClient.get()
        .uri("https://reports-api.example.org/v1/summary")
        .attributes(clientRegistrationId("reports-client"))
        .retrieve()
        .bodyToMono(String.class);
```

Ở đây Spring Security đọc attribute để chọn registration; **Resource Server không nhận được chuỗi `reports-client` như một HTTP header riêng**, trừ khi ứng dụng tự viết thêm logic khác.

## 3. Cấu hình cơ bản một WebClient có Servlet OAuth2 filter

Đối với Spring MVC, starter và thành phần chính:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

`spring-boot-starter-webflux` có thể được dùng để lấy `WebClient` và Reactor Netty làm HTTP client, **không bắt buộc biến ứng dụng thành WebFlux server** nếu Spring MVC vẫn là web stack chủ đạo. Cấu hình auto-detection của Spring Boot và sự kết hợp hai starters cần được xét theo phiên bản ứng dụng.

Ví dụ khai báo OAuth2 Client trong `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company-login:
            provider: company
            client-id: "${COMPANY_CLIENT_ID}"
            client-secret: "${COMPANY_CLIENT_SECRET}"
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, reports.read]
          inventory-service:
            provider: company
            client-id: "${INVENTORY_CLIENT_ID}"
            client-secret: "${INVENTORY_CLIENT_SECRET}"
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: [inventory.read]
        provider:
          company:
            issuer-uri: "https://idp.example.org/realms/company"
```

Provider phải chấp nhận scope/redirect tương ứng. Scope `reports.read` và `inventory.read` là ví dụ phi chuẩn, cần được Authorization Server hỗ trợ. Client secret phải đến từ secret manager/environment, không hardcode vào Git.

### 3.1. Tạo WebClient qua ClientRegistrationRepository và AuthorizedClientRepository

Tích hợp cho Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class OAuth2WebClientConfig {

    @Bean
    WebClient oauth2WebClient(
            ClientRegistrationRepository clientRegistrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        var oauth2 =
                new ServletOAuth2AuthorizedClientExchangeFilterFunction(
                        clientRegistrations, authorizedClients);

        return WebClient.builder()
                .apply(oauth2.oauth2Configuration())
                .build();
    }
}
```

`oauth2Configuration()` đăng ký exchange filter và những thiết lập tích hợp mà hàm này cung cấp. Đây là **`ServletOAuth2AuthorizedClientExchangeFilterFunction`**, không phải `ServerOAuth2AuthorizedClientExchangeFilterFunction` dành cho WebFlux server.

Với cấu hình này, filter phải nhận đủ ngữ cảnh từ request Servlet và Authentication để tìm đúng authorized client. Tùy nơi thực thi và cách khởi tạo, bạn cũng có thể cấu hình filter bằng một `OAuth2AuthorizedClientManager` riêng (xem mục 8).

### 3.2. Cấu hình SecurityFilterChain cho người dùng đăng nhập

Nếu client `company-login` phục vụ OIDC Login:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
```

Người dùng có thể bắt đầu login ở `/oauth2/authorization/company-login`. Sau callback thành công, Spring Security tạo `Authentication` và lưu authorized client của lần đăng nhập theo repository/service được cấu hình.

**Có cấu hình registration chưa có nghĩa authorization đã hoàn tất.** Nếu một người dùng chưa từng cấp quyền cho registration khác, chọn registration đó trong WebClient không bảo đảm backend có access token sẵn để gọi API.

## 4. Chọn registration trực tiếp trên từng WebClient request

Helper quan trọng là:

```java
ServletOAuth2AuthorizedClientExchangeFilterFunction
        .clientRegistrationId("company-login")
```

Được dùng trong DSL:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<ReportSummary> result = webClient.get()
        .uri("https://reports-api.example.org/v1/summary")
        .attributes(clientRegistrationId("company-login"))
        .retrieve()
        .bodyToMono(ReportSummary.class);
```

Ví dụ này giả định:

1. `webClient` đã được tạo kèm Servlet OAuth2 filter ở mục 3.
2. User hiện tại đã đăng nhập qua `company-login` và authorized client có access token thích hợp.
3. Token có scope/audience mà Reports API yêu cầu.
4. `ReportSummary` là DTO do ứng dụng triển khai.

`clientRegistrationId(...)` **không phải phương thức của `WebClient`**, mà là helper của OAuth2 filter trả về một consumer để thêm metadata vào attributes của `ClientRequest`.

### 4.1. Gọi từ Spring MVC service

Một service Servlet có thể dùng WebClient nhưng trả về kết quả đồng bộ tại boundary service:

```java
import java.time.Duration;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

@Service
class ReportsGateway {

    private final WebClient oauth2WebClient;

    ReportsGateway(WebClient oauth2WebClient) {
        this.oauth2WebClient = oauth2WebClient;
    }

    ReportSummary loadSummary() {
        return oauth2WebClient.get()
                .uri("https://reports-api.example.org/v1/summary")
                .attributes(clientRegistrationId("company-login"))
                .retrieve()
                .bodyToMono(ReportSummary.class)
                .block(Duration.ofSeconds(5));
    }
}
```

`block(Duration)` có thể được dùng từ một luồng Servlet blocking khi kiến trúc cho phép, nhưng không nên dùng nó trên Reactor event loop. Cần cấu hình **connect/read/response timeout** của HTTP client, xử lý lỗi `null`/timeout và tránh giữ Servlet thread vô hạn. Đoạn code minh họa; API production còn cần xác định base URL tin cậy, retry policy, circuit breaker và authorization nghiệp vụ.

### 4.2. Đổi registration theo loại tác vụ, không theo user input tùy ý

Giả sử có hai luồng được xác định **từ server**:

```java
Mono<String> companyResult = oauth2WebClient.get()
        .uri("https://reports-api.example.org/v1/public-summary")
        .attributes(clientRegistrationId("company-login"))
        .retrieve()
        .bodyToMono(String.class);

Mono<String> partnerResult = oauth2WebClient.get()
        .uri("https://partner-api.example.org/v1/account")
        .attributes(clientRegistrationId("partner-login"))
        .retrieve()
        .bodyToMono(String.class);
```

`partner-login` phải được đăng ký và người dùng phải có authorized client phù hợp nếu đó là authorization-code registration. Không thể tự sử dụng token của `company-login` như token của `partner-login`.

Nếu service tự chọn dựa trên operation, dùng allowlist thay vì nhận thẳng `registrationId` trong query/body request:

```java
enum DataSource {
    COMPANY_REPORTS,
    PARTNER_ACCOUNT
}

record OutboundTarget(String registrationId, String baseUrl) {}

static final Map<DataSource, OutboundTarget> TARGETS = Map.of(
        DataSource.COMPANY_REPORTS,
        new OutboundTarget(
                "company-login",
                "https://reports-api.example.org"),
        DataSource.PARTNER_ACCOUNT,
        new OutboundTarget(
                "partner-login",
                "https://partner-api.example.org"));
```

Đây là một bảng định tuyến minh họa. Trước khi chọn target, ứng dụng vẫn phải kiểm tra user có được phép sử dụng nguồn dữ liệu đó và tài khoản/tenant nào được phép truy cập.

### 4.3. Chỉ định attribute ở request cuối cùng

Một nguyên tắc hữu ích là thêm `clientRegistrationId` **cùng vị trí với URL API đích**:

```java
webClient.post()
        .uri("https://billing-api.example.org/v1/invoices")
        .attributes(clientRegistrationId("billing-writer"))
        .bodyValue(invoiceRequest)
        .retrieve()
        .bodyToMono(InvoiceReceipt.class);
```

Nhìn vào đoạn code, người đọc biết request dùng registration `billing-writer`. Nhưng **OAuth2 filter chỉ thêm authorization header khi đã có authorized client hoặc có thể authorize theo grant được cấu hình**. Ví dụ `billing-writer` cần tồn tại trong `ClientRegistrationRepository` và được liên kết với cơ chế manager tương ứng.

Với HTTP POST nghiệp vụ, không tự replay request chỉ vì token hết hạn hoặc API trả 401; cần xem xét idempotency và hợp đồng của Billing API.

## 5. Vì sao request attributes tốt hơn một default registration không kiểm soát?

`ServletOAuth2AuthorizedClientExchangeFilterFunction` có những lựa chọn cấu hình mặc định, chẳng hạn sử dụng registration được chỉ định mặc định hoặc dùng authorized client liên quan tới authentication hiện tại. Những tính năng này hữu ích với ứng dụng thực sự chỉ gọi một API, nhưng có rủi ro khi WebClient được tái sử dụng cho **nhiều host và API**.

### 5.1. setDefaultClientRegistrationId

Ví dụ:

```java
var oauth2 =
        new ServletOAuth2AuthorizedClientExchangeFilterFunction(
                registrations, authorizedClientRepository);

oauth2.setDefaultClientRegistrationId("inventory-service");

WebClient client = WebClient.builder()
        .apply(oauth2.oauth2Configuration())
        .build();
```

Với WebClient này, nếu request không chỉ định registration tường minh, filter có thể áp dụng default `inventory-service`. Điều này phù hợp khi **toàn bộ WebClient chỉ dùng cho Inventory API** và quyền gọi token đã được cấu hình chính xác.

Tuy nhiên, một WebClient chung gọi cả Inventory, Billing và Partner API có thể vô tình gửi token sai nơi nhận. Trường hợp nhiều target, nên chọn tường minh bằng `.attributes(clientRegistrationId(...))` và định tuyến URL qua allowlist.

### 5.2. setDefaultOAuth2AuthorizedClient(true)

Một lựa chọn khác là sử dụng authorized client từ authentication hiện tại làm mặc định:

```java
oauth2.setDefaultOAuth2AuthorizedClient(true);
```

Điều này có thể rất tiện nếu mọi outbound call đều dành cho API phù hợp với token đăng nhập của user. Nhưng nếu WebClient chung được dùng để gọi URL bất kỳ, **token của người dùng có thể bị gắn vào request ngoài ý muốn**, bao gồm một host khác mà developer không dự định nhận credential.

**Khuyến nghị thiết kế:** ở hệ thống gọi nhiều API hoặc nhiều OAuth2 client, tránh mặc định gắn token lên mọi request. Chọn registration/authorized client rõ ràng tại call site hoặc dùng WebClient tách theo host và chính sách.

### 5.3. So sánh các cách chọn token

| Cách chọn | Ví dụ | Khi phù hợp |
|---|---|---|
| Registration theo từng request | `.attributes(clientRegistrationId("company-login"))` | Nhiều client/API, cần sự tường minh |
| Authorized client cụ thể | `.attributes(oauth2AuthorizedClient(client))` | Đã có đối tượng authorized client hợp lệ và muốn dùng đúng đối tượng đó |
| Default registration trên filter | `setDefaultClientRegistrationId(...)` | WebClient chuyên biệt cho một registration |
| Default authorized client từ Authentication | `setDefaultOAuth2AuthorizedClient(true)` | Chỉ khi mọi request của WebClient đều được phép dùng token của Authentication hiện tại |
| Tự set Bearer token thủ công | `headers(h -> h.setBearerAuth(...))` | Chỉ trong tích hợp có quản lý token cẩn trọng; dễ sai/lộ token nếu dùng thay filter |

Đừng dựa vào giả định về thứ tự ưu tiên giữa các cơ chế khi code cung cấp đồng thời nhiều nguồn. Với API phức tạp, hãy chọn **một nguồn tường minh**, và xác nhận contract thực tế của phiên bản Spring Security đang dùng.

## 6. Request attributes: thứ gì được truyền, thứ gì không?

Một lệnh gọi:

```java
webClient.get()
        .uri("https://reports-api.example.org/v1/reports")
        .attributes(clientRegistrationId("company-login"))
        .retrieve()
        .bodyToMono(String.class);
```

được hiểu như sau:

```text
ClientRequest (bên trong WebClient)
    method     = GET
    url        = https://reports-api.example.org/v1/reports
    attributes = {
        oauth2.clientRegistrationId: "company-login"  # tên key nội bộ do filter định nghĩa
    }
    |
    v
ServletOAuth2AuthorizedClientExchangeFilterFunction
    |
    +-- đọc attribute, resolve authorized client
    +-- gắn Authorization: Bearer <ACCESS_TOKEN> khi phù hợp
    |
    v
HTTP request tới Reports API
    GET /v1/reports
    Authorization: Bearer <ACCESS_TOKEN>
```

Tên key trong sơ đồ là **minh họa ý nghĩa**, không phải một tên constant mà ứng dụng nên hardcode. Hãy dùng helper public `clientRegistrationId(...)` để tránh phụ thuộc chi tiết implementation.

### 6.1. Không phải HTTP request attribute của Servlet

Trong Spring MVC:

```java
servletRequest.setAttribute("tenantId", "tenant-north");
```

đặt dữ liệu vào `HttpServletRequest`. Ngược lại:

```java
webClient.get()
        .uri(target)
        .attributes(clientRegistrationId("company-login"));
```

đặt metadata vào `ClientRequest` của WebClient. Hai map này không tự đồng bộ.

Nếu chọn registration dựa trên tenant trong Servlet request, ứng dụng phải **xác minh tenant trước**, ánh xạ qua chính sách backend và truyền registration đã được duyệt vào WebClient.

### 6.2. Không phải HTTP query parameter

Không có chuyện:

```text
https://reports-api.example.org/reports?clientRegistrationId=company-login
```

được tự thêm vào URL chỉ vì gọi `clientRegistrationId(...)`. API downstream nhận bearer token chứ không cần biết tên registration nội bộ của BFF.

### 6.3. Không phải OAuth2AuthorizeRequest.attributes

Trong Spring Security có một API khác:

```java
OAuth2AuthorizeRequest.withClientRegistrationId("company-login")
        .principal(authentication)
        .attributes(attrs -> attrs.put("app.operation", "reports.read"))
        .build();
```

Đây là attributes của **OAuth2AuthorizeRequest** đưa vào `OAuth2AuthorizedClientManager`. Nó không phải cùng kiểu với **`ClientRequest.attributes` của WebClient**, dù adapter/filter có thể chuyển một số thông tin theo contract.

Chỉ định `clientRegistrationId` trong WebClient có mục đích cụ thể: **chọn registration**. Không đặt custom attributes rồi kỳ vọng chúng tự được gửi đến token endpoint hoặc tự thay đổi OAuth2 scope.

## 7. Chọn theo registration khác với chỉ định OAuth2AuthorizedClient

Nếu ứng dụng đã có đối tượng `OAuth2AuthorizedClient` được lấy bằng một cơ chế được tin cậy, helper:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

webClient.get()
        .uri("https://reports-api.example.org/v1/summary")
        .attributes(oauth2AuthorizedClient(authorizedClient))
        .retrieve()
        .bodyToMono(String.class);
```

chỉ định client đã được cấp quyền thay vì yêu cầu filter resolve theo registration name.

| Tiêu chí | `clientRegistrationId("x")` | `oauth2AuthorizedClient(client)` |
|---|---|---|
| Đầu vào | Chuỗi registration ID | Đối tượng authorized client |
| Chọn cấu hình client | Filter/manager tìm theo registration ID | Registration đã nằm trong authorized client |
| Gắn với principal | Filter/manager phải xác định principal phù hợp | Đối tượng đã có `principalName`, nhưng vẫn cần policy sở hữu |
| Khi dùng | Tường minh ở call site, muốn manager resolve/reauthorize | Có authorized client từ repository/service/argument resolver |
| Rủi ro khi lấy từ request không tin cậy | Chọn sai registration/quyền rộng | Dùng nhầm token của user khác nếu service cung cấp client sai chủ sở hữu |

**Không chấp nhận bất kỳ authorized client nào do người dùng chọn.** Backend phải bảo đảm authorized client thuộc đúng principal và registration mà caller được phép sử dụng.

### 7.1. Tương tác với @RegisteredOAuth2AuthorizedClient

Spring Security Servlet cung cấp argument resolver:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@RestController
class PortfolioController {

    private final WebClient webClient;

    PortfolioController(WebClient webClient) {
        this.webClient = webClient;
    }

    @GetMapping("/portfolio")
    String portfolio(
            @RegisteredOAuth2AuthorizedClient("company-login")
            OAuth2AuthorizedClient client) {

        return webClient.get()
                .uri("https://reports-api.example.org/v1/portfolio")
                .attributes(oauth2AuthorizedClient(client))
                .retrieve()
                .bodyToMono(String.class)
                .block(java.time.Duration.ofSeconds(5));
    }
}
```

Đây là ví dụ cho một endpoint truy cập sau OAuth2 Login phù hợp. Controller không trả access token cho browser; nó sử dụng token ở backend để gọi Reports API. Cần xử lý khi không có authorized client và những lỗi API thực tế.

### 7.2. Khi đã chỉ định authorized client thì còn cần registration ID không?

Thông thường không cần cung cấp cả hai để biểu đạt cùng một lựa chọn: `OAuth2AuthorizedClient` đã giữ registration của nó. Dùng đồng thời các cơ chế có thể gây nhầm lẫn với developer và làm khó việc chẩn đoán.

Để code rõ ràng, một request nên chọn **một phương pháp**:

```java
.attributes(clientRegistrationId("company-login"))
```

hoặc:

```java
.attributes(oauth2AuthorizedClient(client))
```

Với method bảo mật nhạy cảm, cần xác nhận authority/tenant của principal trước khi sử dụng client.

## 8. Dùng OAuth2AuthorizedClientManager với WebClient Servlet

Khi ứng dụng có cấu hình manager riêng, `ServletOAuth2AuthorizedClientExchangeFilterFunction` hỗ trợ nhận `OAuth2AuthorizedClientManager` thay vì tự tạo từ repositories.

### 8.1. Tạo manager cho Servlet request

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
class ServletAuthorizedClientConfig {

    @Bean
    OAuth2AuthorizedClientManager servletAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository repository) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .clientCredentials()
                        .build();

        var manager = new DefaultOAuth2AuthorizedClientManager(
                registrations, repository);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

`authorizationCode()` dành cho luồng có Authorization Request/Callback của browser; `refreshToken()` quản lý làm mới khi có refresh token; `clientCredentials()` hỗ trợ service token theo cấu hình. Không nên bật grant không dùng chỉ để “đủ tính năng”; danh sách provider phải phù hợp kiến trúc.

### 8.2. Gắn manager vào filter

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Bean
WebClient oauth2WebClient(OAuth2AuthorizedClientManager servletAuthorizedClientManager) {

    var oauth2 = new ServletOAuth2AuthorizedClientExchangeFilterFunction(
            servletAuthorizedClientManager);

    return WebClient.builder()
            .filter(oauth2)
            .build();
}
```

Đây là **một cách cấu hình thay thế** cho WebClient ở mục 3; không đăng ký cả hai bean cùng tên và cùng mục đích trong ứng dụng thật. Nếu application có nhiều manager bean, nên dùng qualifier rõ ràng để tránh Spring chọn nhầm service manager thay cho Servlet manager.

### 8.3. Vì sao manager và storage quan trọng?

Trong Servlet:

- `DefaultOAuth2AuthorizedClientManager` làm việc với `OAuth2AuthorizedClientRepository` và ngữ cảnh Servlet request/response.
- `AuthorizedClientServiceOAuth2AuthorizedClientManager` làm việc với `OAuth2AuthorizedClientService`, thường phù hợp background/service ngoài web request.

Nếu authorized client được lưu trong HTTP session repository, service manager riêng không nhất thiết thấy token đó. Dù cả hai cùng nhận `clientRegistrationId("company-login")`, kết quả khác nhau nếu **storage hoặc principal không trùng**.

Đối với `client_credentials` trong một backend có cả web traffic và background jobs, thường nên có **service token manager riêng** với principal logic ổn định, thay vì để service token bị lưu theo mỗi người dùng browser.

## 9. Truyền Servlet request/response và Authentication khi cần

Trong nhiều Servlet controller, filter có thể lấy `Authentication` và HTTP request/response từ ngữ cảnh Spring Security/Spring MVC hiện tại. Nhưng các luồng bất đồng bộ, callback chạy trong thread khác, scheduler hoặc component khởi tạo WebClient ngoài request có thể **không có thread-local Servlet context**.

Spring Security cung cấp helper để đặt ngữ cảnh tường minh vào request attributes khi cần, ví dụ:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.authentication;
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.servletRequest;
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.servletResponse;
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<String> response = webClient.get()
        .uri("https://reports-api.example.org/v1/summary")
        .attributes(clientRegistrationId("company-login"))
        .attributes(authentication(authentication))
        .attributes(servletRequest(request))
        .attributes(servletResponse(response))
        .retrieve()
        .bodyToMono(String.class);
```

Trong snippet, `authentication`, `request`, `response` ở tham số helper là những biến từ ngữ cảnh controller/service; cách đặt tên biến `response` trùng với biến `Mono<String> response` là không nên khi đưa vào code thực tế. Một cách đặt tên rõ ràng hơn:

```java
Mono<String> downstreamResult = webClient.get()
        .uri("https://reports-api.example.org/v1/summary")
        .attributes(clientRegistrationId("company-login"))
        .attributes(authentication(currentAuthentication))
        .attributes(servletRequest(httpServletRequest))
        .attributes(servletResponse(httpServletResponse))
        .retrieve()
        .bodyToMono(String.class);
```

Mã này minh họa cách truyền context khi các biến đã được lấy từ phương thức Servlet của ứng dụng. Nó không biến một background job thành browser login và không cấp quyền thay người dùng.

**Không giữ `HttpServletRequest` hoặc `HttpServletResponse` trong static field, cache hoặc queue chạy lâu dài.** Chúng có vòng đời request, có thể không còn hợp lệ khi tác vụ bất đồng bộ thực thi. Trong background job, chọn manager/service storage không phụ thuộc Servlet.

### 9.1. Principal phải là nguồn được xác thực

Ví dụ nguy hiểm:

```java
// KHÔNG NÊN: principalName do browser gửi dùng để lấy token người khác.
String selectedUser = httpServletRequest.getParameter("principalName");
```

Sau đó tạo fake Authentication cho `selectedUser` để resolve authorized client có thể dẫn tới rò rỉ token hoặc truy cập dữ liệu người khác. Khi dùng bearer token của người dùng, principal phải đến từ `SecurityContext` đã xác thực và tenant/resource policy của backend.

### 9.2. Reactor context và thread-local không giống nhau

`WebClient` sử dụng Reactor publisher. Trong một call chain bất đồng bộ, thread hiện tại có thể thay đổi. Không nên giả định `SecurityContextHolder` dạng thread-local luôn tồn tại ở mọi Reactor scheduler hoặc callback.

Nếu luồng phải đi qua các scheduler/thread khác nhau, **truyền Authentication/ngữ cảnh cần thiết một cách tường minh theo API hỗ trợ**, hoặc dùng cơ chế context propagation phù hợp phiên bản Spring. Không tự đọc thread-local ở callback không kiểm soát rồi kết luận principal đang bị null là do token hết hạn.

## 10. Chọn registration theo nghiệp vụ: thiết kế an toàn

Một cổng báo cáo có hai API:

```text
Operation: READ_FINANCE_REPORTS
    -> registrationId: company-login
    -> URL: https://reports-api.example.org

Operation: READ_PARTNER_ACCOUNT
    -> registrationId: partner-login
    -> URL: https://partner-api.example.org
```

Lựa chọn có thể do một service server-side thực hiện:

```java
enum DownstreamOperation {
    FINANCE_REPORTS,
    PARTNER_ACCOUNT
}

record OAuth2Target(
        String registrationId,
        String endpoint) {}

final class TargetRegistry {

    private static final Map<DownstreamOperation, OAuth2Target> TARGETS =
            Map.of(
                    DownstreamOperation.FINANCE_REPORTS,
                    new OAuth2Target(
                            "company-login",
                            "https://reports-api.example.org/v1/finance"),
                    DownstreamOperation.PARTNER_ACCOUNT,
                    new OAuth2Target(
                            "partner-login",
                            "https://partner-api.example.org/v1/account"));

    static OAuth2Target forOperation(DownstreamOperation operation) {
        OAuth2Target target = TARGETS.get(operation);
        if (target == null) {
            throw new IllegalArgumentException("Unsupported operation");
        }
        return target;
    }
}
```

Service dùng registry:

```java
Mono<String> load(DownstreamOperation operation) {
    OAuth2Target target = TargetRegistry.forOperation(operation);

    return webClient.get()
            .uri(target.endpoint())
            .attributes(clientRegistrationId(target.registrationId()))
            .retrieve()
            .bodyToMono(String.class);
}
```

Đây là ví dụ về **routing cấu hình phía server**, không phải policy authorization. Trước khi gọi `load`, ứng dụng phải xác minh user có quyền với operation, tài khoản đối tác và tenant tương ứng. Nếu browser có thể chọn enum operation, service vẫn phải chặn operation không được phép.

### 10.1. Vì sao không nhận registrationId trực tiếp qua API?

Anti-pattern:

```java
@GetMapping("/proxy")
String proxy(
        @RequestParam String clientRegistrationId,
        @RequestParam String url) {

    return webClient.get()
            .uri(url)
            .attributes(clientRegistrationId(clientRegistrationId))
            .retrieve()
            .bodyToMono(String.class)
            .block();
}
```

Đoạn code **không an toàn** vì caller có thể:

1. Chọn registration có quyền mạnh hơn quyền của mình.
2. Đổi URL sang host do attacker kiểm soát.
3. Khi filter gắn bearer token, token có thể bị gửi sang server không đáng tin.
4. Dùng backend làm proxy tới mạng nội bộ (SSRF).

Giải pháp không phải chỉ regex registration ID: phải ràng buộc **operation → registration → URL/API đích → quyền user/tenant** bằng allowlist và authorization phía server.

### 10.2. Registration ID không phải security permission

Việc chọn `company-login` không chứng minh user có quyền xuất toàn bộ báo cáo. Nó chỉ nói filter nên chọn loại authorized client nào. API nhận request phải kiểm tra access token và quyền trên đối tượng.

Tương tự, một registration có scope `reports.read` không tự đồng nghĩa user được phép xem tất cả báo cáo của mọi tổ chức. Object-level authorization vẫn cần được thực thi tại Resource Server/service.

## 11. Client Credentials qua WebClient Servlet

Ngoài user-delegated tokens, một ứng dụng Servlet còn có thể gọi API bằng token `client_credentials` của chính backend. Tuy nhiên, nếu để filter Servlet lấy principal từ user login hiện tại, service token có thể bị lưu theo từng user, tạo nhiều bản ghi không cần thiết.

### 11.1. Manager riêng cho background/service identity

Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Bean
OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService authorizedClients) {

    var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                    registrations, authorizedClients);

    manager.setAuthorizedClientProvider(
            OAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build());

    return manager;
}
```

Lớp service dùng principal logic ổn định:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

OAuth2AuthorizeRequest authorizeRequest =
        OAuth2AuthorizeRequest.withClientRegistrationId("inventory-service")
                .principal("service:inventory-sync")
                .build();

OAuth2AuthorizedClient authorized =
        serviceAuthorizedClientManager.authorize(authorizeRequest);

if (authorized == null) {
    throw new IllegalStateException("Cannot authorize inventory-service");
}
```

Đoạn code này lấy token qua manager bên ngoài browser và không cần `OidcUser`. Nếu muốn dùng WebClient, có thể tạo một WebClient riêng với filter dựa trên service manager, **hoặc dùng token do manager trả về** thông qua integration phù hợp; không dùng default user authentication để chọn service principal.

### 11.2. Một WebClient riêng cho service token

```java
@Bean
WebClient serviceWebClient(
        @Qualifier("serviceAuthorizedClientManager")
        OAuth2AuthorizedClientManager manager) {

    var oauth2 = new ServletOAuth2AuthorizedClientExchangeFilterFunction(
            manager);

    return WebClient.builder()
            .filter(oauth2)
            .build();
}
```

Nếu gọi `serviceWebClient` từ một job không có `Authentication` trong SecurityContext, cách dễ kiểm soát nhất là **có principal service logic do server tạo và cung cấp theo API tích hợp**:

```java
Mono<String> inventory = serviceWebClient.get()
        .uri("https://inventory-api.example.org/v1/items")
        .attributes(clientRegistrationId("inventory-service"))
        .attributes(
                ServletOAuth2AuthorizedClientExchangeFilterFunction.authentication(
                        serviceAuthentication))
        .retrieve()
        .bodyToMono(String.class);
```

`serviceAuthentication` phải là identity do **ứng dụng backend khởi tạo và tin cậy**, không lấy từ browser. Trong nhiều background job, việc gọi manager trực tiếp với `.principal("service:inventory-sync")` như mục 11.1 rõ ràng hơn; sau đó có thể dùng `oauth2AuthorizedClient(authorized)` trên request nếu muốn đưa authorized client đã resolve vào filter.

Không biến client credentials token thành danh tính người dùng cuối; BFF vẫn phải kiểm tra user/operation trước khi thực hiện một công việc nhạy cảm bằng service token.

### 11.3. Giới hạn theo token của API

Khi `inventory-service` có scope `inventory.read`, chỉ gửi token đó tới Inventory API được cấu hình. Không dùng access token của `inventory-service` để gọi Partner API chỉ vì WebClient có thể kết nối tới mọi URL.

Resource Server cần kiểm tra `aud`/resource, issuer, thời hạn, scope và policy. `clientRegistrationId` là lựa chọn phía client, **không thay thế token validation của API**.

## 12. Nhiều issuer, nhiều tenant và cùng tên registration

Một hệ thống có thể tích hợp:

```text
registrationId "company-login" -> Corporate OP
registrationId "partner-login" -> Partner OP
registrationId "inventory-service" -> Corporate service realm
```

Mỗi `ClientRegistration` cần gắn với đúng provider, token endpoint, client ID, scopes và client authentication method. Chọn registration sai có thể dẫn tới:

- Filter không tìm được authorized client.
- Request tới Authorization Server khác nhưng client không được đăng ký.
- Access token có issuer/audience khác API kỳ vọng.
- Rò rỉ token tới nơi nhận không được phép nếu routing HTTP cũng sai.
- Một user từ provider đối tác bị áp policy nhân viên nội bộ nếu identity linking sai.

### 12.1. Tenant ID không tự là một registration ID

Nếu một SaaS có các tenant A và B:

```text
tenant-a -> registrationId partner-a-client
tenant-b -> registrationId partner-b-client
```

Có thể dùng một registry mapping tenant đã được xác minh sang registration riêng. Nhưng không được:

```java
String registrationId = "partner-" + request.getParameter("tenant") + "-client";
```

và coi kết quả đó là đáng tin. Trước tiên phải xác nhận người dùng/job có quyền với tenant; sau đó lấy registration từ nguồn cấu hình server-side được bảo vệ.

### 12.2. Principal name và token storage

`OAuth2AuthorizedClientService` thường dùng khóa `(registrationId, principalName)`. Với user login, `principalName` có thể là `Authentication.getName()`/OIDC `sub` theo cấu hình. Với service job, nó thường là tên service logic.

Nếu một registration được dùng cho nhiều tenant cùng principalName và token thực sự có quyền khác nhau, cần đánh giá isolation ở storage và Authorization Server. Chỉ thay request attribute `clientRegistrationId` **không đủ** để giải quyết mọi xung đột tenant.

Tương tự, OIDC `sub` chỉ ổn định trong ngữ cảnh issuer. Không tự gộp local user giữa hai issuer dựa vào subject string hoặc email.

## 13. Khi registration không có authorized client

Hãy phân biệt hai loại registration:

| Grant | Khi chưa có authorized client | Có thể tự xử lý ở background request? |
|---|---|---|
| `client_credentials` | Manager có thể dùng client credentials xin token mới | Có, với client registration, credential và network đúng |
| `authorization_code` | Cần một lần ủy quyền người dùng qua browser theo giao thức | Không thể tự tạo authorization code từ job không có browser |
| `refresh_token` | Cần đã có refresh token hợp lệ gắn với authorized client trước đó | Không thể tự tạo refresh token nếu chưa được cấp |

Ví dụ người dùng đăng nhập bằng `company-login`, nhưng code WebClient lại chỉ định:

```java
.attributes(clientRegistrationId("partner-login"))
```

Nếu chưa có `partner-login` authorized client, lệnh gọi có thể thất bại hoặc yêu cầu khởi động luồng authorization tùy manager/cấu hình, chứ không thể âm thầm đổi token từ Corporate OP sang Partner OP. Ứng dụng cần hiển thị hoặc điều hướng người dùng sang flow phù hợp nếu thực sự muốn cho phép đăng nhập/liên kết provider đó.

### 13.1. Sai registration so với resource audience

Có authorized client không đồng nghĩa token dùng được với mọi API. Ví dụ:

```text
company-login token:
    aud = portal-client
    scope = openid profile

Reports API expects:
    aud = reports-api
    scope = reports.read
```

Khi đó `company-login` có thể đăng nhập hợp lệ nhưng token không được Reports API chấp nhận. Giải pháp là chỉnh hợp đồng cấp access token/provider hoặc registration/ủy quyền tương ứng, **không xóa audience validation của API**.

## 14. Debug lỗi khi chọn clientRegistrationId

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Outbound request không có Authorization header | WebClient chưa lắp OAuth2 filter; không có authorized client; sai ngữ cảnh principal; filter không resolve được | Xác nhận bean WebClient, helper `clientRegistrationId`, manager và storage |
| `clientRegistrationId` không tồn tại | Nhập sai tên registration; chọn `clientId` thay vì registration ID | Kiểm tra `spring.security.oauth2.client.registration` và khóa nội bộ |
| Filter dùng token khác mong đợi | Default registration/authorized client và per-request selection bị trộn; mapper hoặc manager khác | Chọn một nguồn tường minh; kiểm tra cấu hình filter |
| OIDC login thành công nhưng API trả 403 | Access token thiếu scope/audience hoặc user thiếu quyền báo cáo | Kiểm tra API contract, resource policy và registration phù hợp |
| Gọi partner API bị yêu cầu login lại | Chưa có authorized client cho `partner-login` | Khởi động authorization flow được hỗ trợ và giải thích cho user |
| Ứng dụng MVC thấy WebClient mất Authentication | Luồng reactive/thread khác, ngoài Servlet request hoặc truyền context sai | Truyền ngữ cảnh hợp lệ tường minh hoặc dùng manager phù hợp |
| Batch job không tìm thấy Servlet request | Dùng `DefaultOAuth2AuthorizedClientManager` dựa trên HTTP request ngoài web context | Dùng service manager cho background |
| Token được lưu theo từng user dù muốn service token chung | `client_credentials` dùng principal từ SecurityContext user web | Dùng service principal logic ổn định và service manager |
| Token của API A gửi tới API B | WebClient dùng default token trên nhiều host hoặc URL do input điều khiển | Tách WebClient theo target, routing allowlist, chọn registration tường minh |
| Access token hết hạn và API trả 401 | Client không refresh/reauthorize được hoặc dùng token stale | Kiểm tra provider chain, refresh token, expiration và manager |
| Một user dùng nhầm token user khác | Principal name được giả mạo hoặc load client không kiểm tra sở hữu | Lấy Authentication từ SecurityContext, kiểm tra identity/tenant |
| Sau deploy không tìm được token | Session storage/memory khác instance; principal name thay đổi | Kiểm tra repository/service, session stickiness/shared store và key |

### 14.1. Sơ đồ chẩn đoán nhanh

```mermaid
flowchart TD
    A["WebClient OAuth2 request lỗi"] --> B{"Có Servlet OAuth2 filter?"}
    B -- Không --> C["Cấu hình ServletOAuth2AuthorizedClientExchangeFilterFunction"]
    B -- Có --> D{"Đúng clientRegistrationId?"}
    D -- Không --> E["Kiểm tra ClientRegistrationRepository và routing"]
    D -- Có --> F{"Đúng principal và storage?"}
    F -- Không --> G["Kiểm tra Authentication, repository/service, session"]
    F -- Có --> H{"Có authorized client hoặc grant phù hợp?"}
    H -- Không --> I["Làm authorization user hoặc client_credentials theo contract"]
    H -- Có --> J{"Token dùng đúng API đích?"}
    J -- Không --> K["Kiểm tra issuer, audience, scope, URL routing"]
    J -- Có --> L{"Business policy cho phép?"}
    L -- Không --> M["Kiểm tra tenant/resource authorization"]
    L -- Có --> N["Kiểm tra lỗi HTTP/network của downstream"]
```

Đừng bắt đầu bằng việc in nguyên access token ra log rồi decode: token và headers có thể chứa credential nhạy cảm. Phân biệt lỗi **lựa chọn registration**, **authorized client storage**, **token issuance** và **Resource Server authorization**.

### 14.2. Quan sát an toàn

Một log có kiểm soát có thể ghi:

```text
operation=reports.summary
oauth2.registrationId=company-login
downstream=reports-api
outbound.status=403
correlationId=server-generated
```

Hạn chế đưa principalName/tenant ID vào metric label có cardinality cao hoặc chứa dữ liệu cá nhân. Tuyệt đối tránh:

- `Authorization: Bearer ...`;
- `client-secret`, private key/client assertion;
- access token, refresh token, ID Token;
- authorization code, PKCE verifier, session cookie;
- full HTTP token request/response body hoặc toàn bộ OIDC claims.

Để xác định token có đúng registration, ưu tiên metadata đã được phép quan sát như `registrationId`, downstream host cố định, mã lỗi, scope expected và kết quả kiểm tra authorization của API — không log token nguyên văn.

## 15. Kiểm thử lựa chọn registration

Một hệ thống có hai API nên có các lớp kiểm thử độc lập:

| Cấp kiểm thử | Điều cần chứng minh |
|---|---|
| Unit test routing | Operation được phép chọn đúng registration ID và URL, từ chối operation không có trong allowlist |
| OAuth2 filter integration | `.attributes(clientRegistrationId("x"))` khiến filter sử dụng đúng authorized client trong ngữ cảnh test |
| Spring MVC integration | Sau OIDC Login, principal và authorized client đúng user được dùng trong outbound call |
| Multi-registration | Registration A không được lẫn với token của B |
| Client credentials | Backend lấy token service với principal ổn định, không phụ thuộc user browser |
| Token expiry | Khi token hết hạn, manager refresh/reauthorize theo grant thích hợp |
| Resource Server contract | API từ chối token sai issuer/audience/scope |
| SSRF/token leak | Không thể thay URL hoặc registration bằng input browser để gửi bearer token đến host không được phép |
| Concurrent requests | Không lấy nhầm token giữa Alice/Bob hoặc tenant A/B khi nhiều request đồng thời |

### 15.1. Một test ý tưởng với token giả

Giả sử token store trong test chứa:

```text
(company-login, alice) -> fake-company-access-token
(partner-login, alice) -> fake-partner-access-token
```

Với WebClient đã lắp filter và downstream mock server:

1. Call tới Reports API có `clientRegistrationId("company-login")`.
2. Mock server của Reports API nhận `Authorization: Bearer fake-company-access-token`.
3. Call tới Partner API có `clientRegistrationId("partner-login")`.
4. Mock server của Partner API nhận token của partner.
5. Thử một registration không được phép từ business routing phải bị chặn **trước khi gửi request**.

Token giả không cần là JWT hợp lệ vì mục tiêu test ở đây là **routing và gắn header của WebClient**, không phải xác thực chữ ký tại Resource Server. Một integration test đầy đủ nên kiểm chứng thêm provider, user login và API authorization theo contract.

### 15.2. Test khi WebClient không có OAuth2 filter

Một `WebClient` bình thường vẫn có API:

```java
.attributes(clientRegistrationId("company-login"))
```

nhưng nếu không đăng ký exchange filter hiểu attribute đó, **không có cơ chế tự gắn bearer token**. Test này giúp phát hiện trường hợp developer tạo `WebClient.create()` ở một service thay vì inject bean `oauth2WebClient` đã cấu hình.

## 16. Tình huống tổng hợp: Portal gọi hai API bằng hai loại token

Một cổng nội bộ có:

- `company-login`: OIDC Login cho nhân viên để gọi Reports API theo quyền người dùng.
- `inventory-service`: `client_credentials` dùng cho công việc đọc tồn kho mà backend thực hiện.
- Reports API kiểm tra token user; Inventory API kiểm tra token service.

```text
Browser / employee
    |
    v
Spring MVC Portal (SecurityContext có OidcUser)
    |
    +--> GET /dashboard/reports
    |       WebClient:
    |       .attributes(clientRegistrationId("company-login"))
    |             |
    |             v
    |       Reports API (User access token)
    |
    +--> GET /dashboard/inventory
            Business authorization: user được xem tồn kho?
            Service AuthorizedClientManager:
                registrationId = inventory-service
                principal      = service:inventory-sync
                    |
                    v
            Inventory API (Client Credentials access token)
```

Hai đường đi có ý nghĩa khác nhau:

1. Token OIDC/Login có thể đại diện cho quyền được cấp **thay mặt user**, nếu Authorization Server phát access token cho API tương ứng.
2. Token `client_credentials` đại diện cho **ứng dụng/service**, không tự mang chủ thể Alice.
3. Cùng một Portal có thể sử dụng cả hai, nhưng phải kiểm tra nghiệp vụ trước khi cho phép user kích hoạt tác vụ backend sử dụng service credential.
4. `clientRegistrationId` chỉ chọn registration; token phải đúng audience/scope ở API.
5. Dù dùng WebClient chung hay tách WebClient, không được gửi nhầm bearer token sang host khác.

### 16.1. Một thiết kế dễ kiểm soát

```text
ReportsGateway
    allowed URL: reports-api.example.org
    registration: company-login
    principal: authenticated user

InventoryGateway
    allowed URL: inventory-api.example.org
    registration: inventory-service
    principal: service:inventory-sync
    authorization: business policy at Portal + API policy
```

Mỗi gateway giới hạn URL và registration của riêng nó. Nếu hệ thống thêm Partner API, hãy tạo mapping rõ ràng và kiểm tra tenant, không chỉ thêm một đường dẫn tùy ý vào WebClient chung.

## 17. Những lỗi thiết kế cần tránh

1. **Nhầm `registrationId` với `clientId`**, dẫn đến filter không tìm thấy đăng ký.
2. **Dùng `WebClient.create()` không có OAuth2 filter** rồi nghĩ attributes sẽ tự gắn token.
3. **Đặt một default registration cho WebClient gọi nhiều API**, gây gửi token sai host.
4. **Bật `setDefaultOAuth2AuthorizedClient(true)` không kiểm soát**, khiến token người dùng bị gắn lên mọi outbound call có thể không phù hợp.
5. **Lấy registration ID hoặc URL từ query parameter và không dùng allowlist**, mở đường cho token leak/SSRF.
6. **Coi việc chọn registration là được cấp quyền**, bỏ qua authorization của user/tenant và Resource Server.
7. **Quên rằng authorization code registration cần người dùng cấp quyền**, không thể tự lấy token cho một provider khác từ background.
8. **Dùng user principal cho token client credentials dùng chung**, tạo kho token theo từng user không chủ đích.
9. **Không phân biệt Servlet manager với Reactive manager**, dẫn tới lookup sai storage/context.
10. **Giả định thread-local SecurityContext luôn tồn tại trong mọi Reactor callback**, nhất là khi scheduler thay đổi.
11. **Gửi ID Token thay access token** khi gọi API, nhầm token dùng xác thực với token cho tài nguyên.
12. **Tự replay HTTP POST nghiệp vụ khi nhận 401**, không kiểm tra idempotency và side effects.
13. **Log bearer token hoặc full OAuth2AuthorizedClient** để điều tra lỗi.
14. **Coi `clientRegistrationId` là một HTTP header**, trong khi đây là WebClient request metadata phía client.
15. **Chỉ dùng scope trong YAML để kết luận token có quyền**, không kiểm tra granted scopes và API contract.

## 18. Câu hỏi ôn tập

1. `ServletOAuth2AuthorizedClientExchangeFilterFunction` đóng vai trò gì trong một Spring MVC dùng `WebClient`?
2. Dòng `.attributes(clientRegistrationId("company-login"))` thay đổi phần nào của `ClientRequest` và có được gửi nguyên văn tới API không?
3. `registrationId` khác `clientId` thế nào? Vì sao truyền client ID vào helper có thể gây lỗi?
4. Vì sao `ClientRegistration` đã được cấu hình không có nghĩa `OAuth2AuthorizedClient` đã tồn tại cho mọi user?
5. Khi nào nên chọn `clientRegistrationId(...)` và khi nào nên truyền `oauth2AuthorizedClient(...)`?
6. `setDefaultClientRegistrationId(...)` và `setDefaultOAuth2AuthorizedClient(true)` có nguy cơ gì khi WebClient gọi nhiều host?
7. Vì sao không nên lấy registration ID và URL đích trực tiếp từ `@RequestParam`?
8. Khi dùng WebClient ngoài Servlet request, nên dùng manager nào cho background `client_credentials`?
9. `HttpServletRequest` attributes và `WebClient ClientRequest.attributes` khác nhau thế nào?
10. Nếu WebClient có OAuth2 filter nhưng API trả 403, ngoài registration ID cần kiểm tra những yếu tố nào?
11. Làm sao bảo đảm `inventory-service` token không bị gửi tới Reports API?
12. Nếu một user đăng nhập bằng Corporate OP nhưng WebClient chọn `partner-login`, tại sao không được giả định có token partner?
13. Trong ứng dụng nhiều tenant, ai phải quyết định tenant và authorized client nào được phép sử dụng?
14. Làm sao test được request attribute chọn đúng token mà không dùng credential thật?
15. Vì sao `WebClient` dùng trong MVC không tự biến security context thành WebFlux security context?

## Tài liệu tham khảo

- [Spring Security Reference — OAuth2 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security Reference — OAuth2 Client with WebClient (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html)
- [Spring Security Reference — OAuth2 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security API — ServletOAuth2AuthorizedClientExchangeFilterFunction](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServletOAuth2AuthorizedClientExchangeFilterFunction.html)
- [Spring Security API — OAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html)
- [Spring Security API — OAuth2AuthorizedClient](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClient.html)
- [Spring Security API — ClientRegistration](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/registration/ClientRegistration.html)
- [Spring Security API — OAuth2AuthorizedClientRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizedClientRepository.html)
- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://datatracker.ietf.org/doc/html/rfc6749)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html)
