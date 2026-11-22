# Phân biệt lấy token của ứng dụng với chuyển tiếp token người dùng trong Spring Security WebFlux

> **Chủ đề:** OAuth2 Client trong ứng dụng Spring Security Reactive. Mục tiêu là hiểu rõ khi nào một WebFlux service **tự lấy access token bằng client credentials để hoạt động nhân danh chính ứng dụng**, khi nào nó **chuyển tiếp access token thuộc ngữ cảnh người dùng đã xác thực**, và khi nào phải dùng **ủy quyền thay mặt (on-behalf-of) / token exchange** thay vì đơn giản gắn lại một chuỗi Bearer. Các ví dụ hướng tới Java 17+, Spring Boot 3.3.x và Spring Security 6.3.x; trước khi deploy production cần dùng phiên bản được hỗ trợ và cập nhật bản vá.

## 1. Tình huống: một API gọi một API khác

Giả sử có ba thành phần:

- **Frontend:** người dùng Alice đăng nhập.
- **WebFlux Gateway/BFF:** nhận request, kiểm authentication/authorization rồi gọi API báo cáo.
- **Reports API:** endpoint phía sau, có quy tắc kiểm bearer access token.

Có hai công việc khác nhau:

1. **Job hệ thống:** cứ mỗi đêm, ứng dụng tổng hợp báo cáo nội bộ. Không có user nào đang thao tác. Nó cần quyền riêng của **service account**.
2. **Yêu cầu của Alice:** Alice xem báo cáo cá nhân. Reports API phải biết và thực thi quyền của **Alice**, không chỉ quyền rộng của ứng dụng trung gian.

```text
A. APP TOKEN — client_credentials

Background task / internal service
       |
       v
WebFlux app -- client_id + client authentication --> Authorization Server
       |                   grant_type=client_credentials
       |<------------------ access_token (subject: app/client)
       |
       +-- Authorization: Bearer <APP_TOKEN> --> Reports API
                                                   |
                                         kiểm client scopes/roles

B. USER TOKEN RELAY — quyền người dùng

Alice -- Authorization: Bearer <USER_TOKEN> --> WebFlux Resource Server
                                                   |
                                             kiểm signature/issuer/
                                             audience/exp/scope
                                                   |
                                      được phép forwarding có kiểm soát?
                                                   |
             Reports API <-- Authorization: Bearer <USER_TOKEN>
                                                   |
                                         kiểm token và quyền Alice
```

**Khác biệt cốt lõi:** luồng A sử dụng **quyền của client ứng dụng**; luồng B mang theo **quyền được cấp cho người dùng**. Cả hai đều gửi HTTP header `Authorization: Bearer ...`, nhưng **quyền hạn, chủ thể, token lifecycle và hậu quả bảo mật khác nhau**. Không dùng tên header giống nhau để kết luận chúng có thể hoán đổi.

## 2. Bảng so sánh cần nhớ

| Tiêu chí | Token của ứng dụng (app token) | Chuyển tiếp token người dùng (user token relay) |
|---|---|---|
| Tác nhân được đại diện | OAuth2 client/service account | End-user hoặc workload mà inbound token đại diện |
| Cách có token | Thường `client_credentials` grant | Đã có token hợp lệ trên inbound Bearer request, hoặc access token của user nhận qua OAuth2 Login |
| Có tương tác người dùng lúc lấy token? | **Không** | Có user context ở thời điểm authorization ban đầu; forward thường không cần login lại |
| Registration | `authorization-grant-type: client_credentials` | Resource Server nhận JWT không bắt buộc phải có ClientRegistration; OAuth2 Login thường dùng `authorization_code` registration |
| Spring component tiêu biểu | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` và `ReactiveOAuth2AuthorizedClientProvider` | `oauth2ResourceServer().jwt()` + `JwtAuthenticationToken`/`@AuthenticationPrincipal Jwt`; hoặc `OAuth2AuthorizedClient` của OAuth2 Login |
| Token acquisition | Client gọi token endpoint, được cấp access token mới | Relay **không nhất thiết gọi token endpoint**; có thể chỉ forward access token đã nhận |
| `sub`/principal | Có thể là client ID hoặc service identity; theo IdP | Thường là user subject; phụ thuộc token/issuer |
| Scope/audience | Theo quyền service được cấp | Theo quyền user đã chấp thuận/được cấp |
| Làm mới token | Xin token mới khi hết hạn; client credentials thường không có refresh token | Dùng flow/authorized-client manager khi là OAuth2 Login; token inbound JWT không tự refresh |
| Kiểm quyền downstream | Quyền của service, không mặc nhiên giới hạn theo Alice | Downstream có thể áp user-level authorization nếu token đúng audience/scope |
| Audit | “service đã thực hiện” | “Alice đã thực hiện”, nếu downstream xác minh được subject |
| Nguy cơ lớn | **Confused deputy:** service dùng quyền rộng thay user không đủ quyền | **Token leakage/audience mismatch:** relay token sang nhầm nơi hoặc service không chấp nhận token đó |
| Ví dụ dùng | Batch, scheduler, cron, hệ thống đồng bộ, service-to-service | BFF/gateway/API proxy phục vụ tác vụ theo user |

**Lưu ý về các claim JWT:** không có một định dạng claim thống nhất bắt mọi IdP phải đặt `sub` là username trong mọi client-credentials token. Access token có thể là JWT hoặc opaque string. Chỉ sử dụng các claims đã được xác minh và hợp đồng issuer/resource server cụ thể.

## 3. Ba mẫu quan trọng — không gộp làm một

### 3.1 Mẫu A: client_credentials — ứng dụng tự được ủy quyền

```text
Service                  Authorization Server            Reports API
  |                              |                           |
  | POST /token                  |                           |
  | grant_type=client_credentials                            |
  | client authentication ------>|                           |
  |<------ access_token ---------|                           |
  |                              |                           |
  | GET /internal/report         |                           |
  | Authorization: Bearer APP_TOKEN ------------------------->|
  |<---------------------------------------------------------|
```

Client được IdP nhận diện bằng client ID và phương thức client authentication tương ứng (ví dụ `client_secret_basic`, private-key JWT hoặc mTLS theo khả năng IdP). IdP cấp token với **phạm vi của ứng dụng**, không cấp role của Alice chỉ vì Alice đã gọi một endpoint ở service.

**Sử dụng khi:** một job không có phiên người dùng và quyền thực sự thuộc service. Tránh dùng client credentials cho thao tác “xem đơn hàng của Alice” nếu Reports API cần quyết định theo chủ sở hữu/tenant Alice.

### 3.2 Mẫu B: inbound Bearer relay — giữ ngữ cảnh user

```text
Alice -> WebFlux BFF -> Reports API
          |
          +-- @AuthenticationPrincipal Jwt
          +-- Security filter xác minh inbound JWT
          +-- Kiểm route + scope/tenant
          +-- WebClient setBearerAuth(jwt.getTokenValue())
          +-- Chỉ gửi đến host downstream đáng tin
```

BFF là **Resource Server** ở chiều nhận token. Nó phải kiểm token **trước khi chuyển tiếp**, không lấy raw `Authorization` header chưa xác minh rồi gắn ra bất kỳ URL nào. Reports API là **một Resource Server khác**, cũng phải kiểm signature, issuer, expiry, audience, scope và object-level authorization theo hợp đồng của nó.

**Điều kiện quan trọng:** token phải được cấp cho **đúng audience downstream**. Nếu Alice đưa token chỉ có `aud=frontend-bff`, Reports API có `aud=reports-api` không nên chấp nhận token đó. Forward nguyên chuỗi không tự làm thay đổi audience. Khi token không đúng đích, cân nhắc token exchange/on-behalf-of, không nới lỏng audience validator ở downstream.

### 3.3 Mẫu C: OAuth2 Login + outbound authorized client

Một ứng dụng dùng `oauth2Login()` và cookie `WebSession` thường **không** nhận access token ở inbound request từ browser; browser chỉ gửi cookie phiên. Sau login, Spring Security có thể giữ `OAuth2AuthorizedClient` chứa access token của registration tương ứng.

```text
Browser -- cookie SESSION --> BFF đã oauth2Login
                               |
                          OAuth2AuthenticationToken
                               |
                          OAuth2AuthorizedClient
                          (registration + user token)
                               |
                         WebClient -> Reports API
```

Trường hợp này phải **lấy token từ authorized-client repository/service** gắn với user và registration, không sao chép cookie `SESSION` rồi gọi nó là OAuth2 token. Nếu access token hết hạn và user flow/refresh token hỗ trợ, `ReactiveOAuth2AuthorizedClientManager` có thể xin mới/refresh theo provider.

**Phân biệt:** “User token relay” thường được dùng rộng cho cả việc chuyển inbound bearer token và đưa access token của OAuth2 Login ra downstream. Hai nguồn token này **khác nhau về kỹ thuật**; cần mô tả rõ token từ đâu đến.

## 4. Những gì token chứa và điều downstream cần kiểm

Dưới đây là **claims minh họa**, không phải định dạng bắt buộc của mọi OAuth2 access token:

**App token** — có thể có:

```json
{
  "iss": "https://auth.example.com",
  "sub": "service-report-worker",
  "aud": ["reports-api"],
  "scope": "reports.system.read",
  "client_id": "report-worker"
}
```

**User token** — có thể có:

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-12345",
  "aud": ["reports-api"],
  "scope": "reports.read",
  "client_id": "portal-web"
}
```

Cần nhớ:

- `iss`: issuer đáng tin. Không tin chuỗi issuer do HTTP request tự khai.
- `aud`: resource/API nào là **đích** của token; **không** được bỏ kiểm chỉ để relay cho tiện.
- `scope`/`scp`: quyền được cấp, cấu trúc và mapping sang Spring authorities như `SCOPE_reports.read` phụ thuộc provider/converter.
- `sub`: subject do issuer xác định; client-credentials có thể đại diện cho **service**.
- `client_id`/`azp`: metadata client khi provider cung cấp, không phải chứng minh có end-user.
- `exp`, `nbf`, chữ ký, key ID, thuật toán: cần được resource server kiểm hợp lệ.
- **Access token** khác **OIDC ID Token**. Đừng chuyển `id_token` làm Bearer đến Reports API; ID Token dành cho client xác nhận danh tính người dùng, không được dùng như access token cho API.

**Tuyệt đối không log full token**, kể cả trong debug logs, exception hoặc test reports. Token Bearer bị lộ thường có thể bị sử dụng trong thời gian nó còn hiệu lực.

## 5. Quyết định nên dùng loại nào?

| Tình huống | Cách tiếp cận |
|---|---|
| Job nội bộ mỗi đêm gửi báo cáo thống kê chung | **Client credentials** với scope dịch vụ tối thiểu |
| Backend BFF nhận JWT của Alice để đọc report của Alice tại API cùng audience | **User token relay** sau khi xác minh, nếu resource server cho phép |
| BFF dùng OAuth2 Login/cookie rồi gọi API có scope được cấp cho user | **OAuth2AuthorizedClient** gắn user/registration, dùng WebClient OAuth2 client |
| API yêu cầu audience khác inbound token | **Token exchange/on-behalf-of** nếu Authorization Server hỗ trợ; không forward thẳng |
| Service gọi endpoint dữ liệu nhạy cảm thay Alice nhưng chỉ có app token | Thiết kế lại ủy quyền/ACL hoặc delegation có kiểm chứng; đừng giả mạo user qua `X-User-Id` |
| API giữa hai hệ thống không có user | **Client credentials** hoặc workload identity phù hợp |
| Frontend gửi ID Token cho API | **Không dùng ID Token làm access token**; yêu cầu API access token đúng audience |
| Một request phải kết hợp quyền user + quyền service | Thiết kế chính sách **ủy quyền kết hợp** rõ ràng, thường dùng OBO/token exchange; không chỉ chọn token rộng hơn |
| Ứng dụng chỉ kiểm inbound JWT | `oauth2ResourceServer().jwt()`; không cần cấu hình OAuth2 Client nếu không xin token outbound |
| Ứng dụng chỉ xin app token trong scheduler | `ReactiveOAuth2AuthorizedClientManager` với `client_credentials`; không nhất thiết mở login UI |

**Chọn loại token theo chủ thể được cấp quyền**, không theo API nào dễ cấu hình hơn.

## 6. Các interface Spring Security Reactive tương ứng

| Thành phần | Công việc |
|---|---|
| `ReactiveClientRegistrationRepository` | Tra metadata của OAuth2 client (registration, client ID, grant, provider endpoint) |
| `ClientRegistration` | Định nghĩa một client ứng dụng, **không** phải access token |
| `ReactiveOAuth2AuthorizedClientManager` | Ủy quyền/xin lại token, quản lý `OAuth2AuthorizedClient` theo provider |
| `ReactiveOAuth2AuthorizedClientProvider` | Xử lý grant, ví dụ `client_credentials`, `authorization_code`, `refresh_token` |
| `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | Manager có thể chạy **ngoài ServerWebExchange**, phù hợp jobs/background services |
| `DefaultReactiveOAuth2AuthorizedClientManager` | Manager gắn với `ServerWebExchange`, phù hợp web request/OAuth2 Login |
| `ReactiveOAuth2AuthorizedClientService` | Lưu/truy xuất authorized clients và token theo registration/principal |
| `ServerOAuth2AuthorizedClientRepository` | Authorized client theo request `ServerWebExchange`/principal |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | WebClient filter dùng OAuth2AuthorizedClient để gắn Bearer token outbound |
| `JwtAuthenticationToken`/`Jwt` | Đại diện JWT đã được Spring Resource Server giải mã/kiểm |
| `ReactiveJwtDecoder` | Thành phần xác minh JWT cho WebFlux Resource Server |
| `ServerHttpSecurity.oauth2ResourceServer()` | Bảo vệ inbound API bằng bearer token |
| `ServerHttpSecurity.oauth2Login()` | Đăng nhập browser bằng OAuth2/OIDC |
| `ServerHttpSecurity.oauth2Client()` | Tích hợp chức năng OAuth2 Client ở web flow |

**Nhớ hai manager:**

- `DefaultReactiveOAuth2AuthorizedClientManager` có `ServerOAuth2AuthorizedClientRepository` và thường hoạt động trong request context; dùng khi authorize theo user/web.
- `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` dùng `ReactiveOAuth2AuthorizedClientService`, hoạt động khi **không có request đang chạy**, như scheduler, queue consumer hoặc service tier.

Không sao chép interface Servlet `OAuth2AuthorizedClientManager` hoặc `HttpSecurity` để dùng thay cho reactive `ReactiveOAuth2AuthorizedClientManager` và `ServerHttpSecurity`.

## 7. Cấu hình app token bằng client_credentials

Spring Boot hiểu cấu hình ở tiền tố `spring.security.oauth2.client.registration.*`. Với job không cần browser:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          machine-api:
            provider: corporate-idp
            client-id: ${SYSTEM_CLIENT_ID}
            client-secret: ${SYSTEM_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: [reports.system.read]
        provider:
          corporate-idp:
            token-uri: https://auth.example.com/oauth2/token
```

Giá trị `SYSTEM_CLIENT_ID`/`SYSTEM_CLIENT_SECRET` là environment variables có thật; phải được cấp qua vault/secret manager. Client secret chỉ gửi theo client-authentication method được IdP cho phép, ví dụ `client_secret_basic` trên kết nối HTTPS đáng tin. **Không gửi secret đến resource API**, không đưa nó vào Authorization header của các request downstream.

### 7.1 Xin token xảy ra khi nào?

Một `ReactiveOAuth2AuthorizedClientManager` gọi `ReactiveOAuth2AuthorizedClientProvider` tương ứng, thường xin token ở token endpoint nếu chưa có authorized client hợp lệ, hoặc xin lại khi token hết hạn. Với client credentials, việc renew thường là **yêu cầu token mới**; không mặc định có refresh token.

```text
ClientRegistration "machine-api"
   |
   +-- grant = client_credentials
   +-- token-uri = https://auth.example.com/oauth2/token
   +-- scopes = reports.system.read
   |
ReactiveOAuth2AuthorizedClientManager
   |
   +-- authorized client cache/service có token còn hợp lệ? -> dùng
   +-- chưa có/hết hạn? --> token endpoint --> token mới --> lưu
   |
WebClient outbound Authorization: Bearer <APP_ACCESS_TOKEN>
```

Token refresh/caching cụ thể phụ thuộc authorized client manager, provider, clock skew, principal key và store. **Không tự cache chuỗi access token trong biến static lâu dài**, không phân phối token qua log hoặc event payload.

### 7.2 Java 17+: manager phù hợp job không có ServerWebExchange

```java
@Bean
ReactiveOAuth2AuthorizedClientManager machineClientManager(
        ReactiveClientRegistrationRepository registrations,
        ReactiveOAuth2AuthorizedClientService authorizedClients) {

    ReactiveOAuth2AuthorizedClientProvider provider =
        ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build();

    var manager =
        new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
            registrations, authorizedClients);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
```

Đây là **mảnh bean**; class/import đầy đủ ở mục 12. Spring Boot có thể tự đăng ký manager mặc định tùy phiên bản/cấu hình, nhưng khai báo manager rõ ràng giúp khẳng định chỉ các grant bạn chọn được dùng cho job này.

**Không dùng principal của Alice làm khóa app-token một cách vô tình**. Với client credentials, token đại diện service; đặt principal key **ổn định dành cho service**, chẳng hạn `"internal-report-job"`, tránh nhân bản cache token theo từng user và tạo ngộ nhận rằng mỗi app token là “token của Alice”.

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("machine-api")
        .principal("internal-report-job")
        .build();

Mono<OAuth2AuthorizedClient> authorized =
    machineClientManager.authorize(request);
```

`OAuth2AuthorizedClient` chứa access token hợp lệ đã được cấp cho application client. Nếu publisher rỗng hoặc lỗi, **không** tự gửi request downstream không auth rồi thử lại ngẫu nhiên bằng user token.

## 8. Chuyển inbound user bearer token đúng cách

Ở nhánh HTTP API nhận Bearer JWT:

```java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http.authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/relay/reports")
                .hasAuthority("SCOPE_reports.read")
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

Khi JWT hợp lệ, `BearerTokenAuthenticationWebFilter`/JWT authentication stack tạo authentication; controller có thể nhận `Jwt` từ `@AuthenticationPrincipal`. Spring Security đã kiểm JWT theo decoder và authorization policy **trước khi** controller thực thi.

```java
@GetMapping("/api/relay/reports")
Mono<String> relay(@AuthenticationPrincipal Jwt jwt) {
    // Chỉ đến đây sau khi Spring Security chấp nhận JWT + scope.
    return reportService.userReports(jwt);
}
```

Đây là **mảnh method**; project đầy đủ ở mục 12.

### 8.1 Vì sao không copy raw Authorization header?

```java
// SAI — không gửi raw header chưa kiểm chứng đến arbitrary URL.
String raw = exchange.getRequest().getHeaders()
    .getFirst(HttpHeaders.AUTHORIZATION);
// webClient.get().uri(userSuppliedUrl).header("Authorization", raw) ...
```

Rủi ro:

- Header có thể là Basic, Bearer sai, Bearer hết hạn, hoặc do client giả mạo.
- `userSuppliedUrl` có thể trỏ ra máy attacker (SSRF/token exfiltration).
- Token có thể đúng cho BFF nhưng **sai audience downstream**.
- Việc forward token không tự xác minh quyền đối tượng trong Reports API.
- Dễ lộ token qua tracing/HTTP logging.

**Cách đúng khi dùng JWT:** Spring Security Resource Server validate token; controller/service lấy `Jwt.getTokenValue()` từ principal đã xác thực và chuyển tới **downstream origin được allowlist**. Dù vậy, Reports API vẫn phải validate lại. Với opaque inbound token, dùng cơ chế introspection/Authentication phù hợp; không giả định raw token có cấu trúc JWT.

### 8.2 Đúng issuer nhưng sai audience vẫn không phải token relay hợp lệ

Ví dụ BFF chấp nhận token `aud=portal-bff` nhưng Reports API yêu cầu `aud=reports-api`. Nếu cấu hình verifier Reports API chấp nhận `portal-bff` chỉ để “cho relay chạy”, bạn đã làm mất ranh giới quyền giữa API. Thiết kế hợp lệ có thể là:

- Client xin access token được cấp đúng resource/audience downstream ngay từ đầu (nếu AS hỗ trợ).
- Dùng **OAuth 2.0 Token Exchange RFC 8693**/on-behalf-of để lấy token mới có audience/scope downstream, thay mặt user và theo policy AS.
- Dùng một API backend thay mặt user chỉ sau khi có một cơ chế phân quyền nghiệp vụ kiểm chứng; không gọi app token như user token.

## 9. WebClient: chủ động chỉ định token thay vì đặt default toàn cục

Spring Security Reactive có `ServerOAuth2AuthorizedClientExchangeFilterFunction` cho `WebClient`. Filter có thể xin token qua authorized-client manager và đặt Bearer trên request.

```java
@Bean
WebClient oauth2WebClient(
        ReactiveOAuth2AuthorizedClientManager authorizedClientManager) {

    var oauth2 =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(
            authorizedClientManager);
    return WebClient.builder().filter(oauth2).build();
}
```

Nếu dùng filter này, **chỉ định registration/authorized client cho từng request** để không vô tình đưa token sang HTTP host không được phép:

```java
// MẢNH CODE: machine-api đã được cấu hình ClientRegistration.
oauth2WebClient.get()
    .uri("https://reports.example.com/api/system")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .clientRegistrationId("machine-api"))
    .retrieve()
    .bodyToMono(String.class);
```

Đoạn này cần manager/provider phù hợp và chủ thể được chọn hợp lệ; với scheduler không có ServerWebExchange nên dùng manager/service như mục 7.2. Không biến ví dụ thành một `WebClient` toàn cục gắn app token vào mọi HTTP request.

### Hai nút cấu hình nguy hiểm nếu dùng tùy tiện

```java
oauth2.setDefaultOAuth2AuthorizedClient(true);
oauth2.setDefaultClientRegistrationId("machine-api");
```

Tài liệu Spring Security cảnh báo **cẩn trọng** vì request đi qua client đã cấu hình có thể nhận token mặc định, kể cả request đến dịch vụ mà bạn không định ủy quyền. Hãy dùng WebClient riêng, base URL cố định và chỉ định authorized client per request, nhất là khi app gọi nhiều domain hoặc xử lý redirect.

**Quan trọng:** `setDefaultOAuth2AuthorizedClient(true)` chủ yếu liên quan token của user đăng nhập bằng OAuth2 Login; `setDefaultClientRegistrationId(...)` chọn một registration mặc định (có thể là app client). Hai hành vi này **không đồng nghĩa** với “forward inbound Bearer đã được resource server validate”.

### Khi nào nên đặt token thủ công bằng setBearerAuth?

Trong demo mục 12, service sử dụng:

```java
.headers(headers -> headers.setBearerAuth(
    authorizedClient.getAccessToken().getTokenValue()))
```

và nhánh user:

```java
.headers(headers -> headers.setBearerAuth(jwt.getTokenValue()))
```

Cách này **cố ý tường minh** để làm nổi bật ai sở hữu token. Khi dùng production, cân nhắc WebClient filter của Spring Security để xử lý lifecycle nếu token được quản lý bằng authorized client manager; nhưng phải kiểm soát từng request/host/registration tránh leakage.

## 10. Spring Cloud Gateway TokenRelay không phải client_credentials

Spring Cloud Gateway Server WebFlux có filter tên **`TokenRelay`** (cần module/dependency và cấu hình OAuth2 client tương ứng). Ví dụ ở các phiên bản Gateway có hỗ trợ dạng cấu hình này:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: report-api
              uri: https://reports.internal.example
              predicates:
                - Path=/reports/**
              filters:
                - TokenRelay=
```

**Đây là mảnh cấu hình định hướng Gateway**, không dán vào dự án Boot WebFlux thuần ở mục 12; đường dẫn config cụ thể phụ thuộc Spring Cloud Gateway version. `TokenRelay=` không có registration ID thường chuyển access token của authenticated user từ OAuth2 Login khi flow tương ứng được cấu hình; tài liệu Gateway cũng mô tả filter với một `clientRegistrationId` để chọn authorized client.

```text
TokenRelay=                    -> thường user access token hiện tại
TokenRelay=some-registration   -> lấy authorized client của registration đó
```

Đừng nghĩ cứ gắn `TokenRelay=` là một Resource Server bất kỳ tự “login” được hoặc tự chuyển inbound raw JWT trong mọi trường hợp/phiên bản. Phải kiểm cấu hình authentication, registration, nguồn token, lifecycle và integration test. Gateway downstream vẫn kiểm aud/scope theo đúng API.

**Lưu trữ authorized client:** default implementation của Gateway có thể dùng in-memory authorized-client service. Nhiều instance hoặc yêu cầu durability/refresh cần repository/service thích hợp. Đừng lưu token nhạy cảm vào logs hoặc persistent store chưa bảo vệ.

### Một cấu hình dễ nhầm

```yaml
filters:
  - TokenRelay=machine-api
```

Đây **không nhất thiết** “relay token Alice”: bạn đã chủ động chọn `machine-api` registration. Nếu registration đó là `client_credentials`, nó có thể lấy **app token**, không phải token end-user. Muốn audit và authorization theo Alice, phải chọn flow/token phù hợp.

## 11. OAuth2 Token Exchange / on-behalf-of: khi hai loại không đủ

`OAuth 2.0 Token Exchange` (RFC 8693) cho phép một client trình một token (subject token) tới Authorization Server và **đề nghị một token mới** với audience/resource/scope thích hợp. Quy trình có thể lưu dấu actor/delegation tùy AS và policy.

```text
Alice -- USER_TOKEN(aud=bff) --> BFF
                                  |
                                  | grant_type=urn:ietf:params:oauth:grant-type:token-exchange
                                  | subject_token=USER_TOKEN
                                  | audience=reports-api (nếu AS hỗ trợ)
                                  v
                           Authorization Server
                                  |
                                  | kiểm chính sách delegation
                                  v
                           NEW_USER_DELEGATED_TOKEN
                           aud=reports-api
                                  |
                                  v
                              Reports API
```

Điểm quan trọng:

- Token Exchange **không phải** gửi nguyên token đi; một **token mới** được phát sau quyết định của AS.
- Không mặc định provider nào cũng hỗ trợ RFC 8693; nhiều IdP có cơ chế “on-behalf-of” riêng hoặc policy riêng.
- Cần giới hạn requested audience, scopes, subject token, actor, client authentication, TTL và khả năng audit.
- Không tự copy `sub` của user vào một JWT tự ký bằng ứng dụng rồi gọi nó là “delegated token”; như vậy có thể tạo lỗ hổng giả mạo.
- Spring Security 6.3+ có khả năng cấu hình các extension grants theo phiên bản; API/gói triển khai cụ thể phải kiểm tài liệu/IdP. Khi dùng ví dụ chuyên sâu, phân biệt rõ extension grant với client_credentials và authorization_code.

**Khi Reports API đòi token đúng audience, trả 403/401 hợp lý nếu chỉ có inbound token dành cho BFF**, rồi thiết kế exchange; đừng tắt kiểm issuer/audience để ép demo chạy.

## 12. Ví dụ Spring Boot 3.3.13 + WebFlux: hai nhánh token tách biệt

Mục này cung cấp các file của một ứng dụng WebFlux có:

1. **Nhánh app token** trong service method `applicationReports()`, dùng `client_credentials` thông qua `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` và một principal key `"internal-report-job"`. Không public một endpoint cấp quyền dịch vụ rộng chỉ để user nhấn gọi.
2. **Nhánh user token relay** trong `GET /api/relay/reports`, chỉ nhận JWT đã được Resource Server kiểm tra và có authority `SCOPE_reports.read`.
3. Downstream URL được cấu hình cố định. **Demo không sử dụng một URL do client cung cấp**.
4. Unit tests thay thế OAuth token manager và downstream HTTP để chứng minh header Bearer phù hợp với từng nhánh mà **không cần IdP live**.
5. Một test HTTP kiểm request không có JWT bị từ chối.

**Giới hạn có chủ đích:** `auth.example.invalid` và `reports.example.invalid` không có hệ thống thật. Vì thế chạy full HTTP outbound/flow token exchange ngoài môi trường test sẽ không thành công; thay bằng IdP/Reports API thật có TLS và hợp đồng aud/scope phù hợp. Không coi mock token trong unit test là bằng chứng security JWT production đã được kiểm.

### 12.1 Cấu trúc thư mục

```text
webflux-token-boundaries/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/demo/tokens/TokenBoundaryApplication.java
  src/main/java/demo/tokens/SecurityConfiguration.java
  src/main/java/demo/tokens/TokenBoundaryService.java
  src/main/java/demo/tokens/RelayController.java
  src/test/java/demo/tokens/TokenBoundaryServiceTest.java
  src/test/java/demo/tokens/InboundSecurityTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-token-boundaries'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.tokens'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chúng ta cần cả OAuth2 Client cho **outbound token acquisition** và OAuth2 Resource Server cho **inbound user bearer validation**. Không dùng Servlet `spring-boot-starter-web`. `reactor-test` hỗ trợ StepVerifier trong unit tests.

### 12.2 application.yml

```yaml
app:
  downstream-base-url: https://reports.example.invalid

spring:
  security:
    oauth2:
      client:
        registration:
          machine-api:
            provider: corporate-idp
            client-id: demo-app-client
            client-secret: demo-not-a-real-secret
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: [reports.system.read]
        provider:
          corporate-idp:
            token-uri: https://auth.example.invalid/oauth2/token
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.invalid
          jwk-set-uri: https://auth.example.invalid/oauth2/jwks
          audiences:
            - relay-api
```

Mặc dù credential `demo-not-a-real-secret` là chuỗi hợp lệ cú pháp, **nó không phải bí mật thật**. Trong production bắt buộc lấy client ID/secret từ environment/vault, kiểm TLS và tránh commit secrets. `issuer-uri` + `jwk-set-uri` tường minh giúp giảm phụ thuộc metadata discovery ở startup; khi token thật đến, resource server vẫn phải truy xuất JWKS hợp lệ để verify.

`audiences: relay-api` là audience **BFF** mong đợi từ inbound JWT. Nó **không** chứng minh token sẽ được Reports API chấp nhận. Nếu downstream mong `aud=reports-api`, cần access token phù hợp hoặc token exchange. Test offline chứng minh header được chọn đúng, **không** chứng minh downstream đồng ý.

### 12.3 Main application

**src/main/java/demo/tokens/TokenBoundaryApplication.java**

```java
package demo.tokens;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TokenBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(TokenBoundaryApplication.class, args);
    }
}
```

### 12.4 SecurityConfiguration.java

```java
package demo.tokens;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http.authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/relay/reports")
                    .hasAuthority("SCOPE_reports.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    ReactiveOAuth2AuthorizedClientService authorizedClientService(
            ReactiveClientRegistrationRepository registrations) {
        return new InMemoryReactiveOAuth2AuthorizedClientService(
            registrations);
    }

    @Bean
    ReactiveOAuth2AuthorizedClientManager machineClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean
    WebClient reportsWebClient(
            @Value("${app.downstream-base-url}") String baseUrl) {
        return WebClient.builder()
            .baseUrl(baseUrl)
            .build();
    }
}
```

Giải thích:

- `SecurityWebFilterChain` bảo vệ inbound endpoint; policy kiểm đúng `SCOPE_reports.read` theo JWT authority mapper mặc định khi issuer phát `scope`/`scp` như Spring hiểu.
- `ReactiveOAuth2AuthorizedClientService` giữ trạng thái authorized client. Bài dùng in-memory; trong production multi-pod phải xét cache/persistence/TTL và token confidentiality.
- `machineClientManager` là manager phù hợp background; nó chỉ bật `clientCredentials()` trong provider.
- `reportsWebClient` chỉ trỏ tới một trusted base URL, **không nhận URL tùy ý từ HTTP user**. Trong triển khai thật cần DNS/TLS allowlist, egress policy và tránh redirect làm token rò sang origin khác.
- Không có endpoint HTTP “lấy app token cho người dùng”, giảm nguy cơ dùng quyền system thay user.

### 12.5 TokenBoundaryService.java

```java
package demo.tokens;

import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class TokenBoundaryService {

    private final ReactiveOAuth2AuthorizedClientManager machineManager;
    private final WebClient reportsWebClient;

    public TokenBoundaryService(
            ReactiveOAuth2AuthorizedClientManager machineManager,
            WebClient reportsWebClient) {
        this.machineManager = machineManager;
        this.reportsWebClient = reportsWebClient;
    }

    // Dùng trong job/service tier. Không đưa token này cho caller.
    public Mono<String> applicationReports() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("machine-api")
                .principal("internal-report-job")
                .build();

        return machineManager.authorize(request)
            .switchIfEmpty(Mono.error(new IllegalStateException(
                "Machine client is not authorized")))
            .flatMap(authorized ->
                reportsWebClient.get()
                    .uri("/api/system/reports")
                    .headers(headers -> headers.setBearerAuth(
                        authorized.getAccessToken().getTokenValue()))
                    .retrieve()
                    .bodyToMono(String.class));
    }

    // jwt PHẢI là principal đã được Spring Resource Server xác minh.
    // Chỉ relay khi audience/scope downstream cho phép.
    public Mono<String> userReports(Jwt jwt) {
        if (jwt == null) {
            return Mono.error(new IllegalArgumentException(
                "Validated JWT principal is required"));
        }

        return reportsWebClient.get()
            .uri("/api/user/reports")
            .headers(headers -> headers.setBearerAuth(
                jwt.getTokenValue()))
            .retrieve()
            .bodyToMono(String.class);
    }
}
```

Cách đọc:

1. `applicationReports()` không có `Jwt` đầu vào, cũng không dùng user principal. Nó yêu cầu app token dựa trên `machine-api` registration và key ổn định `internal-report-job`.
2. Nếu không lấy được token, trả lỗi; **không fallback** sang anonymous request, raw inbound token hay session cookie.
3. `userReports(Jwt jwt)` chỉ lấy `Jwt` từ security context đã xác minh **do controller truyền vào**, không đọc raw header hoặc tự parse token.
4. Hai method dùng path downstream khác nhau, phù hợp phân quyền server. Trong hệ thống thật, vẫn cần Reports API kiểm claims/scope/tenant của token.
5. Cả hai dùng Reactor `Mono`, không `block()` trong WebFlux thread.
6. Không chia sẻ token đã lấy giữa các user qua static field/log; app token có thể được manager cache theo service principal, user token chỉ dùng trong request user đã xác minh.
7. Nếu downstream có redirect cross-origin, phải bảo đảm HTTP client không chuyển Bearer sang host khác; thiết kế egress policy, không tự follow redirect vô điều kiện.

### 12.6 RelayController.java

```java
package demo.tokens;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class RelayController {

    private final TokenBoundaryService service;

    public RelayController(TokenBoundaryService service) {
        this.service = service;
    }

    @GetMapping("/api/relay/reports")
    public Mono<String> relay(@AuthenticationPrincipal Jwt jwt) {
        if (jwt == null) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.UNAUTHORIZED));
        }
        return service.userReports(jwt);
    }
}
```

**Chú ý:** Controller **không** expose `applicationReports()`. Đó là nhánh system/service, được scheduler hoặc một internal workflow đáng tin gọi theo nhu cầu. Nếu business thật sự cần endpoint kích hoạt job, phải có authorization/admin approval, rate limits, audit, allowlist hành động, chống confused deputy; không đưa quyền service rộng cho mọi user chỉ vì họ đã login.

### 12.7 Test unit: xác nhận app token khác user token mà không cần IdP

**src/test/java/demo/tokens/TokenBoundaryServiceTest.java**

```java
package demo.tokens;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TokenBoundaryServiceTest {

    private static OAuth2AuthorizedClient machineToken() {
        ClientRegistration registration =
            ClientRegistration.withRegistrationId("machine-api")
                .clientId("demo-machine-client")
                .clientSecret("fake-secret")
                .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri("https://auth.example.invalid/token")
                .build();

        Instant now = Instant.now();
        OAuth2AccessToken access = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "app-token-123",
            now,
            now.plusSeconds(300),
            Set.of("reports.system.read"));

        return new OAuth2AuthorizedClient(
            registration, "internal-report-job", access);
    }

    private static Jwt userJwt(String value, String username) {
        Instant now = Instant.now();
        return Jwt.withTokenValue(value)
            .header("alg", "RS256")
            .claim("sub", username)
            .claim("scope", "reports.read")
            .issuedAt(now)
            .expiresAt(now.plusSeconds(300))
            .build();
    }

    private static TokenBoundaryService service(
            ReactiveOAuth2AuthorizedClientManager manager,
            List<String> sentHeaders) {

        ExchangeFunction downstream = request -> {
            sentHeaders.add(request.headers()
                .getFirst(HttpHeaders.AUTHORIZATION));

            ClientResponse response = ClientResponse
                .create(HttpStatus.OK)
                .header(HttpHeaders.CONTENT_TYPE,
                    MediaType.TEXT_PLAIN_VALUE)
                .body("downstream-ok")
                .build();

            return Mono.just(response);
        };

        WebClient fakeWebClient = WebClient.builder()
            .baseUrl("https://reports.example.invalid")
            .exchangeFunction(downstream)
            .build();

        return new TokenBoundaryService(manager, fakeWebClient);
    }

    @Test
    void appTokenUsesFixedRegistrationAndMachinePrincipal() {
        var captured = new ArrayList<String>();
        AtomicReference<String> registration = new AtomicReference<>();
        AtomicReference<String> principal = new AtomicReference<>();

        ReactiveOAuth2AuthorizedClientManager manager = request -> {
            registration.set(request.getClientRegistrationId());
            principal.set(request.getPrincipal().getName());
            return Mono.just(machineToken());
        };

        var app = service(manager, captured);

        StepVerifier.create(app.applicationReports())
            .expectNext("downstream-ok")
            .verifyComplete();

        assertEquals("machine-api", registration.get());
        assertEquals("internal-report-job", principal.get());
        assertEquals(List.of("Bearer app-token-123"), captured);
    }

    @Test
    void userRelayForwardsUserTokenNotMachineToken() {
        var captured = new ArrayList<String>();
        ReactiveOAuth2AuthorizedClientManager manager = request ->
            Mono.error(new IllegalStateException(
                "Should not acquire machine token"));

        var app = service(manager, captured);

        StepVerifier.create(app.userReports(
                userJwt("user-token-alice", "alice")))
            .expectNext("downstream-ok")
            .verifyComplete();

        assertEquals(
            List.of("Bearer user-token-alice"), captured);
    }

    @Test
    void twoUsersRetainDistinctBearerTokens() {
        var captured = new ArrayList<String>();
        ReactiveOAuth2AuthorizedClientManager manager = request ->
            Mono.empty();

        var app = service(manager, captured);

        StepVerifier.create(app.userReports(
                userJwt("token-alice", "alice")))
            .expectNext("downstream-ok").verifyComplete();

        StepVerifier.create(app.userReports(
                userJwt("token-bob", "bob")))
            .expectNext("downstream-ok").verifyComplete();

        assertEquals(List.of(
            "Bearer token-alice", "Bearer token-bob"), captured);
    }

    @Test
    void cannotAcquireAppTokenStopsBeforeDownstream() {
        var captured = new ArrayList<String>();
        ReactiveOAuth2AuthorizedClientManager manager = request ->
            Mono.empty();

        var app = service(manager, captured);

        StepVerifier.create(app.applicationReports())
            .expectError(IllegalStateException.class)
            .verify();

        assertTrue(captured.isEmpty());
    }

    @Test
    void appTokenProviderErrorDoesNotDowngradeToAnonymous() {
        var captured = new ArrayList<String>();
        ReactiveOAuth2AuthorizedClientManager manager = request ->
            Mono.error(new IllegalStateException("token unavailable"));

        var app = service(manager, captured);

        StepVerifier.create(app.applicationReports())
            .expectErrorMessage("token unavailable")
            .verify();

        assertTrue(captured.isEmpty());
    }

    @Test
    void applicationFlowDoesNotUseUserBearerToken() {
        var captured = new ArrayList<String>();
        ReactiveOAuth2AuthorizedClientManager manager = request ->
            Mono.just(machineToken());

        var app = service(manager, captured);

        StepVerifier.create(app.userReports(
                userJwt("USER-ONLY", "alice")))
            .expectNext("downstream-ok")
            .verifyComplete();

        StepVerifier.create(app.applicationReports())
            .expectNext("downstream-ok")
            .verifyComplete();

        assertEquals(List.of(
            "Bearer USER-ONLY", "Bearer app-token-123"), captured);
    }

    @Test
    void missingValidatedUserPrincipalIsRejected() {
        var captured = new ArrayList<String>();
        ReactiveOAuth2AuthorizedClientManager manager = request ->
            Mono.just(machineToken());

        var app = service(manager, captured);

        StepVerifier.create(app.userReports(null))
            .expectError(IllegalArgumentException.class)
            .verify();

        assertTrue(captured.isEmpty());
    }
}
```

**Bảy test methods** kiểm bằng fake `ReactiveOAuth2AuthorizedClientManager` và fake `ExchangeFunction`: các Bearer headers được chọn đúng, registration/principal ổn định, không dùng chéo token, token acquisition failure chặn trước downstream. Do fake `ExchangeFunction` không gửi network, test chạy offline.

**Giới hạn rõ:** test unit tạo `Jwt` bằng builder, **không xác minh chữ ký**; điều đó được thực hiện bởi Spring Security Resource Server trên HTTP request thật. Test chỉ chứng minh service **sử dụng Jwt do controller đã xác minh**, không phải test auth protocol end-to-end. Muốn kiểm chứng signature/audience cần integration test có mock JWK/Authorization Server hoặc IdP thật.

### 12.8 Test HTTP: thiếu bearer token bị từ chối

**src/test/java/demo/tokens/InboundSecurityTest.java**

```java
package demo.tokens;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class InboundSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void relayEndpointRequiresBearerAuthentication() {
        client.get().uri("/api/relay/reports")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

**Một test HTTP** này xác minh request anonymous không gọi controller/relay logic; nó **không** kiểm full JWT validation, token acquisition hoặc call tới downstream. Với `issuer-uri` và `jwk-set-uri` khai báo, ứng dụng có thể dựng decoder từ JWKS URI mà không cần gọi metadata IdP ngay ở startup, nhưng khi nhận bearer JWT thật sẽ phải có JWKS xác thực được.

### 12.9 Chạy thử

```bash
gradle test
gradle bootRun

# Endpoint inbound thiếu bearer JWT -> 401, không gọi downstream:
curl -i http://localhost:8080/api/relay/reports
```

Dùng Gradle Wrapper phù hợp khi có: `./gradlew test` hoặc Windows `gradlew.bat test`. Để gọi endpoint thành công trên hệ thống thật, phải có một access token **thật** do issuer hợp lệ cấp, `aud=relay-api` và scope `reports.read`, đồng thời downstream phải chấp nhận audience/permission đúng. Không dùng token giả trong unit test để gọi production API.

**Không tuyên bố đã chạy Gradle ở đây:** source code được rà soát theo Spring Security 6.x; kết quả của các test là kỳ vọng, cần thực thi trong môi trường có dependency thực để xác nhận.

## 13. Thiết kế production: đừng biến service thành confused deputy

**Confused deputy** là khi một thành phần có quyền rộng vô tình thực thi hành động thay một caller có quyền hẹp, mà không kiểm tra chính sách của caller.

```text
Alice (chỉ được xem báo cáo của Alice)
    |
    | GET /api/admin/export?tenant=bob
    v
BFF dùng app token có reports.system.read trên toàn bộ tenant
    |
    v
Reports API tin app token, trả báo cáo tenant Bob
    |
    v
BFF trả dữ liệu Bob cho Alice       <-- lỗ hổng nếu không có kiểm quyền
```

**Không** làm kiểu này:

```java
// Phản ví dụ: app token được dùng như bằng chứng user có quyền.
return machineClientManager.authorize(request)
    .flatMap(client -> callAdminReport(
        client.getAccessToken().getTokenValue(),
        requestTenantFromUser));
```

Một app token có thể được phép truy cập tập dữ liệu lớn. Nếu user kích hoạt job bằng một API, BFF phải kiểm quyền *người dùng* và mục tiêu nghiệp vụ ở server trước, audit requester, giới hạn allowlisted actions, và downstream cũng phải kiểm delegation/ACL nếu cần. Thậm chí khi có `X-User-Id` header do app tự thêm, downstream không nên coi header đó là chứng cứ ủy quyền nếu thiếu ranh giới tin cậy/mTLS và policy rõ.

### Quyền app không phải quyền user

- `reports.system.read` và `reports.read` là hai scopes có ý nghĩa khác nhau theo policy issuer.
- Không tự gộp tất cả roles/scope thành ADMIN vì client đã có secret.
- Service account nên dùng **least privilege**, token ngắn hạn, rotation, mTLS/private-key JWT khi phù hợp.
- User token phải được kiểm audience, scope và ownership ở downstream, không suy từ username trên URL.
- Khi app và user cùng tham gia, token exchange/ủy quyền kết hợp phải được AS chấp nhận.

## 14. Bảo vệ token trong Reactive WebClient

### 14.1 Gửi token cho đúng host và đúng route

Dù `WebClient` trỏ tới một base URL cố định, không nên lấy URL/host từ query hoặc JSON body mà không allowlist. Nguy cơ bao gồm SSRF, DNS rebinding, cross-origin redirects và leak Bearer token sang endpoint không tin cậy.

Nên cấu hình egress firewall, HTTPS với certificate validation, timeouts, bounded retries và base URL cố định. Nếu dùng redirect-follow, xác minh chính xác thư viện HTTP có giữ/loại `Authorization` trên redirect cross-origin hay không; thường nên **không follow** cross-origin redirect cho request Bearer.

### 14.2 Reactor Context và tác vụ background

`ReactiveSecurityContextHolder` mang user Authentication theo Reactor Context trong request pipeline. Scheduler/job không có user context; đừng gọi `ReactiveSecurityContextHolder.getContext()` rồi tự gắn “anonymous=user service” để mô phỏng. Dùng `client_credentials` manager phù hợp `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.

Không gọi `block()`/`subscribe()` thủ công trong WebFlux controller. `Mono`/`Flux` được framework subscribe; nếu dùng job/scheduler thì phải có cơ chế subscribe/lifecycle và error handling đúng trong scheduler/job runner.

### 14.3 Token expiry, refresh và retry

- Với client credentials, expired app token thường được **renew** bằng grant mới theo provider.
- Với OAuth2 Login, refresh token có thể khả dụng nếu AS cấp và authorized-client provider hỗ trợ refresh.
- Với inbound user JWT relay, BFF **không tự có refresh token** để xin mới; thường trả 401 phù hợp khi token hết hạn, hoặc thực hiện delegation qua flow được thiết kế.
- Khi downstream trả 401/403, đừng fallback từ user token sang app token. Đó có thể là lỗ hổng nâng quyền.
- Không retry vô hạn trên 401/invalid_client, tránh token storms/throttling; phân biệt 429/5xx và áp dụng backoff.
- Token caches cần key đúng principal/registration/tenant; tránh một user nhận token của user khác.

### 14.4 Header injection, logging và exception

Không đưa raw token vào log hoặc `toString()` của request/response. Khi trace:
- Log registration ID hoặc loại grant khi phù hợp; không client secret.
- Ghi request correlation ID, status, latency, identity **đã được xử lý/ẩn danh** theo policy.
- Redact `Authorization`, `Cookie`, query code/state, `Set-Cookie`, access/refresh token.
- Không gửi access token trở lại frontend chỉ để debug.

## 15. Token exchange không phải tự sửa JWT

Khi inbound JWT có `aud=bff` và downstream yêu cầu `aud=reports-api`, tuyệt đối không:

```java
// Sai về mô hình bảo mật:
// decode JWT, đổi claim aud, encode Base64 lại rồi gắn Authorization.
```

Chữ ký sẽ không hợp lệ; nếu ứng dụng tự ký lại token dưới identity của mình mà downstream chấp nhận tùy tiện, đó là một giao thức ủy quyền mới cần thiết kế chặt chẽ, không phải RFC 8693.

Cần một **Authorization Server đáng tin** quyết định có cho BFF trao đổi subject token thành token dành cho Reports API hay không. Downstream validate token mới, có thể giữ identity user/actor phù hợp để audit. Mỗi provider có thể có biến thể riêng, nên cần đọc tài liệu của IdP.

## 16. Ma trận kiểm thử nên có

| Bài test | Giá trị cần chứng minh |
|---|---|
| App token request dùng `grant_type=client_credentials` | Không tạo authorization redirect người dùng; đúng client credentials |
| Manager dùng registration `machine-api` và key `internal-report-job` | Không cấp token per-user ngoài ý muốn |
| User relay nhận `Jwt` từ authenticated principal | Không tin raw Authorization header |
| Alice và Bob gọi riêng | Outbound Bearer khác nhau, không mix token |
| App token lỗi/rỗng | Không gọi downstream bằng anonymous hoặc user token fallback |
| HTTP không có JWT | 401 trước controller |
| HTTP JWT sai signature/issuer/exp/aud | 401, không relay (cần IdP/JWKS mock) |
| JWT đúng nhưng thiếu `reports.read` | 403, không relay |
| JWT đủ scope nhưng record ngoại tenant | Downstream/service trả deny theo owner/tenant |
| Token đúng BFF nhưng sai downstream audience | Downstream phải từ chối hoặc token exchange |
| OAuth2 Login/cookie mode | Authorized-client token lấy đúng registration và principal |
| Outbound client gọi host giả/redirect lạ | Không rò Authorization header |
| 401/403 từ downstream | Không fallback sang app token; xử lý lỗi rõ |
| Concurrent requests app token hết hạn | Renew/caching có giới hạn, không bão request |
| Client secret rotation/provider outage | Fail closed, metrics/audit, không lộ secret |
| Gateway TokenRelay (nếu dùng) | Xác minh no-ID vs registration ID chọn đúng loại token |
| Token Exchange/OBO (nếu dùng) | Chính AS cấp token đúng aud/scopes, giữ delegation/audit |
| Multiple pods | Authorized-client service và session/token caching phù hợp |

Test unit ở mục 12 chỉ kiểm **đường đi header và sự tách biệt**. Muốn tuyên bố tích hợp OAuth2/OIDC thành công, còn phải có mock IdP thật, JWT ký được kiểm, token endpoint, callback/state hoặc client-credentials grant, JWKS/clock/issuer/audience và downstream authorization.

## 17. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách sửa |
|---|---|---|
| Dùng `client_credentials` rồi xem token là Alice | Grant không đại diện cho user | Relay user token hoặc OBO/delegation |
| Forward inbound `Authorization` chưa kiểm | Token có thể giả/sai scheme/audience | Resource Server validate trước |
| Dùng `id_token` gọi API | ID Token không phải API access token | Xin đúng access token cho API |
| Relay token có aud chỉ dành cho BFF | Downstream không phải audience | Xin resource token hoặc Token Exchange |
| Cấu hình `setDefaultOAuth2AuthorizedClient(true)` cho mọi WebClient | Token user có thể dính vào request sai host | Per-request authorized client/registration; tách WebClient |
| Set default registration machine trên client đi nhiều domain | App token có thể bị gửi sai nơi | Host allowlist và per-request token |
| Để user kích hoạt app-token export không kiểm quyền | Confused deputy, privilege escalation | Enforce user permission trước, giới hạn scope service |
| Lấy token machine bằng principal username của user | Cache phân mảnh, ngụ ý sai ngữ cảnh | Principal service cố định |
| Dùng `DefaultReactiveOAuth2AuthorizedClientManager` từ scheduler không có exchange | Manager hướng tới HTTP request | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| Dùng Servlet manager trong WebFlux | Không cùng API/reactive context | Dùng Reactive... manager/repositories |
| App token hết hạn thì lấy user token fallback | Hạ thấp security boundary/nâng quyền | Fail closed, renew đúng grant |
| Parse claims JWT không validate | Tin dữ liệu client tự khai | `ReactiveJwtDecoder`/Resource Server |
| Không kiểm scopes/tenant ở Reports API | Authentication không đủ authorization | Resource Server + business ACL |
| Log `Authorization`/`clientSecret` | Lộ bearer/secret | Redact logs, vault/rotation |
| Không cấp `client_credentials` provider trong manager | Manager không xin được app token | Configure `ReactiveOAuth2AuthorizedClientProviderBuilder.clientCredentials()` |
| Nghĩ `TokenRelay=machine-api` vẫn là token Alice | Registration có thể là client_credentials | Xem loại grant và authorized client thực |
| Dùng query `targetUrl` để forward token | SSRF/exfiltration | Cố định/allowlist HTTPS downstream |
| Đổi audience bằng sửa chuỗi JWT | Mất signature/ủy quyền hợp lệ | AS Token Exchange hoặc xin token mới |
| Nhầm 401 của token endpoint với 401 downstream | Hai hệ thống/credential khác nhau | Phân biệt nơi phát lỗi và telemetry |
| Không test tình huống không có user | Job fail khi cần principal | App manager với service principal |

## 18. Checklist trước khi triển khai

1. Ghi rõ mỗi outbound API **cần quyền app hay quyền user**. Không để phân loại này phụ thuộc “có token nào sẵn”.
2. Với app token: cấu hình `client_credentials` registration, client authentication, scope tối thiểu và token URI tin cậy.
3. Với job: dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` và principal key service ổn định.
4. Với user relay từ HTTP Bearer: xác minh token ở Resource Server (signature/issuer/audience/exp) và scope/route trước khi service chuyển tiếp.
5. Chỉ relay **access token**, không relay OIDC ID Token hoặc cookie session.
6. Kiểm issuer/audience/scopes của **downstream**; không được giả định vì BFF chấp nhận token nên downstream cũng phải chấp nhận.
7. Với OAuth2 Login: lấy `OAuth2AuthorizedClient` gắn đúng user và registration, không lấy raw cookie như access token.
8. Nếu hai resource có audience riêng, dùng token exchange/OBO theo policy IdP hoặc thiết kế một grant đúng đích.
9. Tách WebClient cho nguồn token và host cần gọi; hạn chế `setDefault...` và không gửi Bearer tới arbitrary URL.
10. Không tạo fallback từ user token thất bại sang app token có quyền mạnh hơn.
11. Kiểm quyền business/tenant/ownership ở downstream, không chỉ tin scope.
12. Dùng secret manager, TLS, secure storage và rotation; không log access/refresh tokens hay client secret.
13. Cấu hình bounded connection pool, timeouts, retries theo trạng thái, circuit breaker và tracing đã redact.
14. Test app/job không có user, nhiều user khác nhau, invalid JWT, invalid audience, scope thiếu, expired tokens và downstream errors.
15. Với Gateway TokenRelay, kiểm phiên bản module/config và ý nghĩa tùy chọn `clientRegistrationId`.
16. Kiểm multi-pod/authorized-client cache, refresh lifetime, clock skew và token endpoint outage.
17. Rà soát bảo mật sau nâng phiên bản Spring Boot/Spring Security/IdP; không suy từ tài liệu “current” rằng API 6.x/7.x giống hệt.

## 19. Bài tập vận dụng

1. Vẽ luồng cho batch job không có user: ai gọi token endpoint, ai giữ secret, vì sao `sub` không phải Alice?
2. Vẽ luồng cho Alice gọi BFF bằng JWT: ở đâu xác minh chữ ký, scope và audience? Reports API có phải xác minh lại không?
3. Sửa YAML từ `client_credentials` thành `authorization_code` và giải thích vì sao scheduler không thể tự hoàn tất user login chỉ nhờ đổi grant.
4. Thử `StepVerifier` của demo khi manager trả `Mono.empty()`, rồi khi token endpoint lỗi. Phải có outbound request nào được gửi không?
5. Thêm user token của Bob và chứng minh không bao giờ dùng lẫn Bearer của Alice.
6. Thiết kế token claims và resource server policy khi Reports API chỉ dành cho `aud=reports-api`, còn inbound JWT của BFF có `aud=relay-api`.
7. Phân biệt `OAuth2AuthorizedClient` của một `oauth2Login` user với `JwtAuthenticationToken` của request `oauth2ResourceServer`.
8. Giải thích vì sao `ServerOAuth2AuthorizedClientExchangeFilterFunction.setDefaultOAuth2AuthorizedClient(true)` có thể gây token leak nếu WebClient gọi nhiều host.
9. Viết test giả một URL redirect từ Reports API sang domain lạ và xác minh không có `Authorization` gửi tới domain đó.
10. Dùng Spring Cloud Gateway TokenRelay với và không có `clientRegistrationId`, nêu điều kiện để token được lấy từ user hoặc registration.
11. Thiết kế một chính sách cho việc Alice khởi chạy “export toàn bộ tenant” nhưng chỉ app có scope system rộng; làm sao tránh confused deputy?
12. Đọc RFC 8693 và chỉ ra vai trò `subject_token`, `audience`/`resource`, `scope`; vì sao AS phải quyết định delegation?
13. Tạo integration test với mock token endpoint cho `grant_type=client_credentials`, Basic client authentication và token expiry/renew.
14. Viết test 401 inbound và 403 thiếu scope khi có signed JWT mock/decoder test; xác minh downstream không bị gọi.
15. Liệt kê những thứ phải redact trong logs: cookie, access token, refresh token, authorization code, client secret và user PII.

## Kết luận

Hai request outbound cùng dùng `Authorization: Bearer ...` nhưng **không cùng ý nghĩa bảo mật**. Với `client_credentials`, ứng dụng xin token **nhân danh service/client**, phù hợp scheduler hoặc machine-to-machine; trong Spring Security WebFlux, manager phù hợp job là `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`. Với **user token relay**, ứng dụng phải bắt đầu từ một token **đã được xác minh** gắn với user context (ví dụ `Jwt` ở Resource Server) hoặc từ `OAuth2AuthorizedClient` của OAuth2 Login; chỉ chuyển đến downstream đáng tin **khi token đúng audience/scope**. Nếu API downstream có audience khác hoặc yêu cầu ủy quyền thay mặt, cần **OAuth2 Token Exchange/on-behalf-of**, không tắt validator hay dùng app token làm user token. Cốt lõi của triển khai an toàn là giữ tách biệt **identity, grant, token lifecycle, audience và business permissions**, kiểm bằng test âm tính trước khi deploy.

## Tài liệu tham khảo

1. Spring Security — Reactive OAuth2 Client, core classes và background service manager: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html
2. Spring Security — Authorized Client features và `WebClient` OAuth2 filter: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html
3. Spring Security 6.5 — OAuth2 WebFlux, client credentials và WebClient integration: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
4. Spring Security — Client Credentials grant và reactive token response client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html
5. Spring Boot 3.3 — OAuth2 Resource Server JWT issuer/JWKS/audiences properties: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
6. Spring Cloud Gateway Server WebFlux — TokenRelay GatewayFilter: https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html
7. Spring Security 6.3.8 — InMemoryReactiveOAuth2AuthorizedClientService: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/oauth2/client/InMemoryReactiveOAuth2AuthorizedClientService.html
8. RFC 6749 — OAuth2 Authorization Framework / Client Credentials: https://www.rfc-editor.org/rfc/rfc6749
9. RFC 6750 — Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
10. RFC 8693 — OAuth2 Token Exchange: https://www.rfc-editor.org/rfc/rfc8693
11. OpenID Connect Core 1.0 — ID Token vs Access Token: https://openid.net/specs/openid-connect-core-1_0.html
