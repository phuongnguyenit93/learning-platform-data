# ReactiveOAuth2AuthorizedClientManager, ReactiveOAuth2AuthorizedClientService và ServerOAuth2AuthorizedClientRepository

## Mục tiêu và phạm vi

Bài này thuộc **Spring Security – reactive**, chủ đề **OAuth2 Client**. Sau bài học, người học có thể:

1. Phân biệt `ClientRegistration`, `OAuth2AuthorizedClient`, `ReactiveOAuth2AuthorizedClientManager`, `ReactiveOAuth2AuthorizedClientProvider`, `ReactiveOAuth2AuthorizedClientService` và `ServerOAuth2AuthorizedClientRepository`.
2. Hiểu rõ **manager điều phối cấp/đổi token**, **service quản lý bản ghi authorized client ở tầng ứng dụng** và **server repository nối bản ghi đó với WebFlux request/principal/session**. Không nhầm chúng với nơi lưu user hay OAuth2 Authorization Server.
3. Chọn `DefaultReactiveOAuth2AuthorizedClientManager` cho request có `ServerWebExchange` và `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` cho job/service không có request.
4. Viết `OAuth2AuthorizeRequest` đúng principal, registrationId và exchange attribute; hiểu `Mono<OAuth2AuthorizedClient>`, `Mono.empty()`, success/failure handlers và token refresh.
5. Giải thích `AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository`, `WebSessionServerOAuth2AuthorizedClientRepository`, `InMemoryReactiveOAuth2AuthorizedClientService` và `R2dbcReactiveOAuth2AuthorizedClientService`, cùng rủi ro lưu token.
6. Tích hợp WebClient có chọn rõ client qua `ServerOAuth2AuthorizedClientExchangeFilterFunction` mà không vô tình gắn token vào mọi outbound HTTP request.
7. Chạy project Java 17+ / Spring Boot 3.x với Spring Security 6.5 và các bài kiểm thử `WebTestClient` / `StepVerifier`. Đối chiếu một provider **mô phỏng cho học tập** với provider OAuth2 thực.
8. Kiểm soát fail-closed, refresh token, đa principal, client_credentials, logout/revocation, multi-instance và bí mật OAuth2 client.

> **Ranh giới an toàn:** project thực hành dùng `LearningAuthorizedClientProvider` tự sinh **chuỗi token giả, không có quyền truy cập tài nguyên thật**, để các test manager/service/repository chạy offline và không cần Identity Provider. Đây **không phải OAuth2 Authorization Server**, không thực hiện token exchange theo chuẩn và **không được dùng trong production**. Phần cấu hình provider thực cho `authorization_code`, `refresh_token`, `client_credentials` được trình bày riêng. Các file của project demo đầy đủ ở mục 8–11; những snippet khác được ghi rõ là minh họa.

---

## 1. Đặt các khái niệm vào đúng vị trí

Trong OAuth2, ứng dụng backend WebFlux có thể **đóng vai trò Client**: lấy access token từ Authorization Server rồi gọi API của Resource Server. Nó không trở thành Authorization Server chỉ vì có `oauth2Client()`.

```text
Người dùng / job nền
       |
       v
Spring Security OAuth2 Client (WebFlux)
       |
       +-- ReactiveClientRegistrationRepository
       |      +-- ClientRegistration("crm", clientId, tokenUri, scopes...)
       |
       +-- ReactiveOAuth2AuthorizedClientManager
       |      +-- ReactiveOAuth2AuthorizedClientProvider
       |      |      authorization_code / refresh_token / client_credentials
       |      |
       |      +-- Nơi load/save/remove OAuth2AuthorizedClient:
       |              A. ServerOAuth2AuthorizedClientRepository
       |                 (request + principal + ServerWebExchange)
       |              B. ReactiveOAuth2AuthorizedClientService
       |                 (registrationId + principalName)
       |
       v
OAuth2AuthorizedClient = registration + principalName + accessToken
                                           + optional refreshToken
       |
       v
WebClient -> Authorization: Bearer <access token>
       |
       v
Resource Server: kiểm tra token, scope/role, resource policy
```

### Bảng định nghĩa

| Loại | Chức năng | Có phải nơi tự cấp token không? |
| --- | --- | --- |
| `ClientRegistration` | Cấu hình ứng dụng Client đã đăng ký với IdP: ID, grant type, client auth, token endpoint, scope | Không |
| `ReactiveClientRegistrationRepository` | Tìm cấu hình theo `registrationId` (ví dụ `crm`, `billing`) | Không |
| `OAuth2AuthorizedClient` | Bản ghi **đã có** access token và có thể có refresh token, gắn với registration + principal | Không |
| `ReactiveOAuth2AuthorizedClientProvider` | Chiến lược thực hiện grant/token exchange hoặc refresh khi cần | Có thể yêu cầu token từ Authorization Server |
| `ReactiveOAuth2AuthorizedClientManager` | Điều phối provider, load/save/remove token và handlers | Không tự là Authorization Server |
| `ReactiveOAuth2AuthorizedClientService` | CRUD reactive authorized client ở phạm vi ứng dụng/principal name | Không |
| `ServerOAuth2AuthorizedClientRepository` | CRUD authorized client theo request WebFlux, principal và exchange | Không |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Gắn Bearer access token vào outbound `WebClient` request khi đã chọn authorized client | Không cấp token độc lập; dùng manager |

**Phân biệt registration và authorized client:**

- `ClientRegistration("crm")` có thể tồn tại ngay từ khi app khởi động, **chưa có token**.
- Khi OAuth2 flow thành công, `OAuth2AuthorizedClient` gắn registration `crm` với `principalName` và token. Với `authorization_code`, đó thường là end-user đã cấp quyền. Với `client_credentials`, principal name là **khóa ngữ cảnh ứng dụng/service** do bạn quyết định, không phải Resource Owner thực.
- Một registration có thể tạo nhiều authorized-client records cho các principal khác nhau. Nếu chỉ khóa theo registrationId sẽ có nguy cơ trộn token giữa người dùng.

### Client OAuth2 khác Resource Server

Một ứng dụng có thể vừa là Resource Server (xác thực Bearer token **đi vào**) vừa là OAuth2 Client (lấy Bearer token **đi ra**). Hai vai trò được cấu hình và quản lý khác nhau. `ServerOAuth2AuthorizedClientRepository` không phải `ReactiveAuthenticationManager`, cũng không phải JWK set/cache của JWT decoder.

## 2. Vòng đời OAuth2AuthorizedClient

Khi code cần gọi API đích:

1. Chọn đúng `clientRegistrationId` và xác định principal thích hợp.
2. Tạo `OAuth2AuthorizeRequest`.
3. `ReactiveOAuth2AuthorizedClientManager.authorize(request)` tìm authorized client đã lưu qua service hoặc repository.
4. Nếu chưa có hoặc hết hạn/cần gia hạn, manager chuyển cho `ReactiveOAuth2AuthorizedClientProvider` phù hợp grant.
5. Provider có thể trao đổi với token endpoint để lấy access token mới hoặc dùng refresh token để cấp lại token.
6. Khi thành công, manager gọi `ReactiveOAuth2AuthorizationSuccessHandler`; cấu hình mặc định lưu authorized client qua persistence được chọn.
7. Caller nhận `Mono<OAuth2AuthorizedClient>`, sử dụng `client.getAccessToken()` cho outbound request; không tự thêm token vào logs/URLs.
8. Nếu grant thất bại, manager phát lỗi hoặc kết quả không được hỗ trợ tùy tình huống. Với `invalid_grant`, failure handler mặc định có thể loại bỏ authorized client đã lưu để tránh tái dùng refresh token không hợp lệ.

```text
authorize(request)
  |
  +-- clientRegistrationId hợp lệ?
  |       |
  |       +-- Không: lỗi/không thể authorize theo contract, không fake permit
  |
  +-- load OAuth2AuthorizedClient (principal + registrationId)
  |       |
  |       +-- Token còn hiệu lực, không cần refresh: có thể dùng lại
  |       |
  |       +-- Chưa có/hết hạn:
  |               +-- provider có hỗ trợ grant?
  |                       +-- Có -> token request/refresh -> save -> return
  |                       +-- Không -> Mono.empty hoặc authorized client cũ
  |
  +-- Provider lỗi:
          +-- failure handler theo chính sách, có thể remove invalid_grant
          +-- caller xử lý lỗi an toàn, không gửi token tùy ý
```

### `Mono.empty()` không phải 403 hay access token rỗng

Contract của `ReactiveOAuth2AuthorizedClientManager.authorize` cho phép `Mono.empty()` nếu grant không được hỗ trợ và không có authorized client phù hợp. Code gọi nên xử lý:

```java
return manager.authorize(authorizeRequest)
        .switchIfEmpty(Mono.error(
                new IllegalStateException("OAuth2 client unavailable")))
        .flatMap(client -> callProtectedApi(client));
```

Đây là fragment: `callProtectedApi(...)` là hàm nghiệp vụ cần định nghĩa. **Không** viết `.defaultIfEmpty(fakeToken)` hoặc fallback sang token của principal khác. `Mono.error` từ token endpoint không được biến thành cấp quyền cho API downstream.

### Token expiry và refresh

Access token có `issuedAt`/`expiresAt`; provider có thể xem khoảng lệch đồng hồ (clock skew) để quyết định cần đổi token trước khi hết hạn thực sự. Refresh token không luôn tồn tại; `client_credentials` thường lấy access token mới từ token endpoint khi cũ hết hạn thay vì dùng refresh token. `authorization_code` có thể nhận refresh token nếu Authorization Server cấp và policy cho phép.

Đừng giả định mọi `OAuth2AuthorizedClient` đều có refresh token hoặc manager tự thay thế chính sách IdP về consent, scope và rotation. Cần test token hết hạn, invalid_grant, revocation và timeouts.

## 3. ReactiveOAuth2AuthorizedClientManager — bộ điều phối

Interface nằm trong:

```java
org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager
```

Hợp đồng quan trọng:

```java
Mono<OAuth2AuthorizedClient> authorize(
        OAuth2AuthorizeRequest authorizeRequest);
```

Nó không có `authorize(...)` trả synchronous object như Servlet `OAuth2AuthorizedClientManager`. Để giữ non-blocking:

- `return manager.authorize(...).flatMap(...)`, không gọi `.block()` trong Netty event loop.
- Không `.subscribe()` thủ công rồi đọc một biến mutable ngay sau đó.
- Với job nền, scheduler phải subscribe **một lần** theo thiết kế; tránh subscription lặp dẫn đến nhiều token requests không kiểm soát.
- Khi provider không hỗ trợ grant, phải phát hiện `Mono.empty()` và dừng an toàn.
- Khi gọi outbound `WebClient`, giới hạn timeout, retry và concurrency, không log Authorization header.

### 3.1. DefaultReactiveOAuth2AuthorizedClientManager

Đây là implementation dùng **trong `ServerWebExchange` context**, đi kèm `ServerOAuth2AuthorizedClientRepository`.

Cấu hình điển hình cho ứng dụng có user request:

```java
@Bean
ReactiveOAuth2AuthorizedClientManager browserAuthorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ServerOAuth2AuthorizedClientRepository repository) {

    ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                    .authorizationCode()
                    .refreshToken()
                    .clientCredentials()
                    .build();

    DefaultReactiveOAuth2AuthorizedClientManager manager =
            new DefaultReactiveOAuth2AuthorizedClientManager(
                    registrations, repository);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
```

Đây là fragment của cấu hình **thật**, cần import Spring Security OAuth2 reactive. Tùy nhu cầu, chỉ bật các grant mà client đăng ký hỗ trợ. Phần code project học bên dưới dùng một provider giả **thay thế**, nên không được vừa dùng mock vừa dùng provider thật trong production.

Tại một controller:

```java
OAuth2AuthorizeRequest authorizeRequest =
        OAuth2AuthorizeRequest.withClientRegistrationId("crm")
                .principal(authentication)
                .attribute(ServerWebExchange.class.getName(), exchange)
                .build();

return browserAuthorizedClientManager.authorize(authorizeRequest);
```

`authentication` được lấy từ Spring Security, `exchange` là request hiện tại. `ServerWebExchange.class.getName()` là khóa attribute mà implementation này dùng để lấy exchange. Lấy registration ID từ cấu hình đáng tin, không cho client gửi tên registration tùy ý để mượn token của ứng dụng khác.

**Không dùng DefaultReactive... trực tiếp trong `@Scheduled` job không có ServerWebExchange**, vì yêu cầu context này không tồn tại. Dùng implementation service-based.

### 3.2. AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager

Implementation này dành cho service tier, batch/job và các trường hợp **không có HTTP request**:

```java
@Bean
ReactiveOAuth2AuthorizedClientManager systemAuthorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ReactiveOAuth2AuthorizedClientService service) {

    ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build();

    AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                    registrations, service);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
```

Một job dùng principal name ổn định như `system:reports` để định danh cache token client_credentials:

```java
Authentication servicePrincipal =
        new UsernamePasswordAuthenticationToken(
                "system:reports", "N/A",
                List.of(new SimpleGrantedAuthority("ROLE_SYSTEM")));

OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest.withClientRegistrationId("machine")
                .principal(servicePrincipal)
                .build();

return systemAuthorizedClientManager.authorize(request);
```

Đây là fragment: không cấp `ROLE_SYSTEM` cho caller ngoài; principal ở đây chỉ đại diện một job **trusted**. Với client_credentials, không đánh đồng principal name đó với người dùng đang login hoặc dùng token của một user để làm việc hệ thống.

### 3.3. Hai manager có được dùng chung storage?

Có, **nếu thiết kế có chủ đích**: web manager lưu qua repository có thể delegate xuống cùng `ReactiveOAuth2AuthorizedClientService`; service manager cũng dùng service đó. Khi cùng registrationId + principalName, bản ghi có thể được nhìn thấy ở cả hai ngữ cảnh. Đây là lý do phải tách principal name giữa end-user và service account. Không dùng `"system"` cho mọi tenant/customer nếu token có quyền khác nhau.

Nếu dùng một `WebSessionServerOAuth2AuthorizedClientRepository` riêng cho browser và một application service cho job, hai nơi không tự đồng bộ. Không được giả định user vừa OAuth2 login có token trong mọi service store.

## 4. ReactiveOAuth2AuthorizedClientService — kho authorized client tầng ứng dụng

Interface:

```java
org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService
```

Có ba thao tác cốt lõi:

```java
<T extends OAuth2AuthorizedClient> Mono<T> loadAuthorizedClient(
        String clientRegistrationId, String principalName);

Mono<Void> saveAuthorizedClient(
        OAuth2AuthorizedClient authorizedClient,
        Authentication principal);

Mono<Void> removeAuthorizedClient(
        String clientRegistrationId, String principalName);
```

**Khóa logic** là `(registrationId, principalName)`. Một tên principal trùng nhau giữa hai tenant cần được phân biệt bằng identity có tenant được xác minh hoặc storage design phù hợp.

### 4.1. InMemoryReactiveOAuth2AuthorizedClientService

Phù hợp demo, integration tests, hoặc workload nhỏ không cần giữ token qua restart:

```java
@Bean
ReactiveOAuth2AuthorizedClientService authorizedClientService(
        ReactiveClientRegistrationRepository registrations) {
    return new InMemoryReactiveOAuth2AuthorizedClientService(
            registrations);
}
```

Lưu ý:

- Data mất khi app restart.
- Nhiều instance không chia sẻ bộ nhớ.
- Không dùng cho yêu cầu durability, multi-instance token cache, revocation tracking hoặc chính sách mã hóa at rest chưa được đánh giá.
- Dù lưu in-memory, token vẫn là credential nhạy cảm; không dump object hay access token trong debug logs.

### 4.2. R2dbcReactiveOAuth2AuthorizedClientService

Spring Security 6.5 cung cấp `R2dbcReactiveOAuth2AuthorizedClientService` để persist authorized clients qua database reactive khi đã cấu hình R2DBC. Cần bảng schema OAuth2 Authorized Client mà tài liệu Spring Security mô tả, connection factory và policies về:

- Mã hóa access/refresh token **at rest**, key management và quyền đọc database.
- Phân tách tenant/principal, dữ liệu token hết hạn và dọn dẹp sau revoke.
- Transaction semantics và concurrency khi hai request cùng refresh.
- Connection pool, latency và fail-closed nếu database unavailable.
- Không ghi access/refresh token vào telemetry, exception body hoặc analytics.

**Không tự chép schema JDBC OAuth2 hay dùng `JdbcOAuth2AuthorizedClientService` của Servlet**; chọn implementation reactive và đối chiếu đúng schema/version. Một ứng dụng production có thể dùng custom service để lưu encrypted records hoặc central secret store, nhưng phải giữ semantics và tests.

### 4.3. Service không tự xin token

Gọi `loadAuthorizedClient(...)` chỉ tra **đã có record**:

```java
return authorizedClientService
        .<OAuth2AuthorizedClient>loadAuthorizedClient(
                "crm", authentication.getName())
        .map(client -> client.getAccessToken().getExpiresAt());
```

Đoạn này không refresh token và không bảo đảm token còn dùng được; nếu mục đích là **lấy token đủ mới để gọi API**, ưu tiên `manager.authorize(...)`. Direct service lookup phù hợp audit trạng thái, kiểm tra đã cấp quyền, admin cleanup hoặc các thao tác quản trị có kiểm soát.

## 5. ServerOAuth2AuthorizedClientRepository — kho gắn với WebFlux exchange

Interface:

```java
org.springframework.security.oauth2.client.web.server
        .ServerOAuth2AuthorizedClientRepository
```

Method signatures:

```java
<T extends OAuth2AuthorizedClient> Mono<T> loadAuthorizedClient(
        String registrationId,
        Authentication principal,
        ServerWebExchange exchange);

Mono<Void> saveAuthorizedClient(
        OAuth2AuthorizedClient authorizedClient,
        Authentication principal,
        ServerWebExchange exchange);

Mono<Void> removeAuthorizedClient(
        String registrationId,
        Authentication principal,
        ServerWebExchange exchange);
```

Điểm khác service: **repository nhận cả Authentication và ServerWebExchange**, nên có thể dùng session/request context và chính sách authenticated/anonymous. Service chỉ dùng registration ID + principal name và không bắt buộc có HTTP request.

### 5.1. WebSessionServerOAuth2AuthorizedClientRepository

Implementation `WebSessionServerOAuth2AuthorizedClientRepository` lưu authorized client trong `WebSession`. Với browser OAuth2 flow hoặc anonymous request, loại này hữu ích khi trạng thái gắn với web session.

- Session có thể bị mất khi expired/invalidate.
- Nếu dùng distributed session, storage semantics theo session infrastructure.
- Logout/invalidating WebSession có thể xóa các record chỉ nằm ở session.
- Không đồng nghĩa xóa tất cả authorized clients ở application-level service hoặc gọi remote IdP revocation endpoint.

### 5.2. AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository

Implementation này **đóng vai trò bridge**:

- Khi principal được xác thực, delegate vào `ReactiveOAuth2AuthorizedClientService` mà bạn cung cấp.
- Khi principal anonymous/unauthenticated, delegate vào repository khác, mặc định `WebSessionServerOAuth2AuthorizedClientRepository`.
- Cho phép web manager dùng một repository có contract request-aware, đồng thời dùng application service cho principal đã login.

```java
@Bean
ServerOAuth2AuthorizedClientRepository serverAuthorizedClients(
        ReactiveOAuth2AuthorizedClientService authorizedClientService) {
    return new AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository(
            authorizedClientService);
}
```

Không nên suy rằng **mọi** implementation ServerOAuth2AuthorizedClientRepository tự ghi vào service. Điều đó đúng với bridge implementation cho principal authenticated trong cấu hình này, nhưng không đúng với pure WebSession repository.

### 5.3. Lưu/xóa khác revoke

`removeAuthorizedClient(...)` chỉ xóa record ứng dụng đang giữ. Token đã phát có thể **vẫn còn hiệu lực tại Resource Server** cho tới khi hết hạn, bị thu hồi qua OAuth2 revocation endpoint (nếu có), hoặc chính sách token/IdP vô hiệu hóa.

Với user logout, cần quyết định rõ:

- Xóa local SecurityContext/WebSession?
- Xóa authorized clients của user ở repository/service?
- Có cần revoke refresh/access token ở Authorization Server?
- Có cần OIDC RP-initiated logout khỏi IdP?
- Các background clients khác có tiếp tục được sử dụng không?

Đây là các việc **khác nhau**. Không gọi `save/remove` xong rồi tuyên bố remote token đã bị thu hồi.

## 6. Chọn implementation theo tình huống

| Tình huống | Manager phù hợp | Persistence thường dùng |
| --- | --- | --- |
| User đăng nhập OAuth2 trên trình duyệt, gọi API behalf-of user | `DefaultReactiveOAuth2AuthorizedClientManager` | `ServerOAuth2AuthorizedClientRepository` |
| User đã authenticated bởi Basic/session nhưng app cần outbound client token từ request | `DefaultReactiveOAuth2AuthorizedClientManager` | Repository gắn request; bridge xuống service khi phù hợp |
| `@Scheduled` job lấy `client_credentials` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientService` |
| Consumer/queue không có `ServerWebExchange` | Service-based manager | Application service |
| Test inspect một token record đã tồn tại | Có thể gọi service/repository trực tiếp | Đúng storage của workflow |
| WebClient gửi Bearer token khi outbound | WebClient OAuth2 filter dùng manager thích hợp | Manager quyết định refresh/persist |
| Ứng dụng multi-instance yêu cầu token cache chung | Manager theo context | Persistence có durability và cross-instance consistency |

**Không chọn manager chỉ theo việc class tên chứa chữ "Default".** Tiêu chí là nơi gọi có HTTP exchange hay không và token thuộc principal nào.

## 7. WebClient kết hợp OAuth2 Client

Trong WebFlux, Spring Security cung cấp:

```java
org.springframework.security.oauth2.client.web.reactive.function.client
        .ServerOAuth2AuthorizedClientExchangeFilterFunction
```

Ví dụ WebClient dùng manager reactive:

```java
@Bean
WebClient resourceWebClient(
        ReactiveOAuth2AuthorizedClientManager webAuthorizedClientManager) {

    ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                    webAuthorizedClientManager);

    return WebClient.builder()
            .filter(oauth2)
            .build();
}
```

Lúc gọi API, chọn **client registration cụ thể**:

```java
return resourceWebClient.get()
        .uri("https://api.example.test/v1/profile")
        .attributes(ServerOAuth2AuthorizedClientExchangeFilterFunction
                .clientRegistrationId("crm"))
        .retrieve()
        .bodyToMono(String.class);
```

**Cảnh báo:** đây là snippet tích hợp **provider OAuth2 thật** và endpoint minh họa, không nằm trong demo offline dùng token giả. Request này có thể gửi Bearer credential thật tới API đích; chỉ gọi hostname allowlisted và không cho người dùng tự kiểm soát URL outbound tùy ý (SSRF/token exfiltration).

Bạn cũng có thể dùng:

```java
.attributes(ServerOAuth2AuthorizedClientExchangeFilterFunction
        .oauth2AuthorizedClient(authorizedClient))
```

khi đã có authorized client cụ thể. Annotation `@RegisteredOAuth2AuthorizedClient("crm")` có thể resolve authorized client trong controller WebFlux, nhưng **không thay thế** cơ chế manager và storage phía sau.

### Default authorized client: tiện nhưng nguy hiểm

`setDefaultOAuth2AuthorizedClient(true)` hoặc `setDefaultClientRegistrationId("crm")` có thể khiến **mọi outbound request của WebClient đó** nhận access token theo cơ chế mặc định, kể cả request tới host không mong muốn. Spring Security khuyến cáo thận trọng. Nên chỉ định registration **theo từng request** hoặc tạo WebClient chuyên cho một protected API với host cố định và cơ chế ngăn redirect sang host khác.

### Khi Resource Server trả 401/403 cho Bearer

Token đã có không đồng nghĩa Resource Server sẽ chấp nhận. Cần phân biệt:

- `401 invalid_token`: có thể cần xóa record token lỗi/re-authorize theo policy.
- `403 insufficient_scope`: không nên đơn giản lấy token khác scope hoặc retry vô hạn để vượt quyền.
- Token endpoint lỗi: manager báo lỗi OAuth2; không dùng token giả hoặc token user khác.
- Refresh rotation và revocation: phải tuân thủ policy IdP.
- Khi sử dụng WebClient filter với manager, xem chính xác failure handler và liên kết `OAuth2AuthorizationFailureHandler` theo constructor/configuration/version để không giữ token lỗi mãi.

## 8. Project demo offline: mô phỏng provider nhưng dùng manager/service/repository thật

**Mục tiêu thực hành:** học cách **ba thành phần làm việc với nhau** bằng provider tạo ra token giả cố định trong tiến trình test. Project không liên hệ IdP, không cần client secret thật, không gọi Resource Server thật. Một số chức năng như refresh grant thực sẽ được học ở mục 12.

### 8.1. Cấu trúc

```text
authorized-client-lab/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/oauth2lab/
        AuthorizedClientLabApplication.java
        SecurityConfiguration.java
        AuthorizedClientConfiguration.java
        LearningAuthorizedClientProvider.java
        AuthorizedClientController.java
        MachineJob.java
      resources/
        application.yml
    test/
      java/example/oauth2lab/
        AuthorizedClientIntegrationTest.java
```

### 8.2. Gradle và Java 17

**`settings.gradle`:**

```groovy
rootProject.name = 'authorized-client-lab'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.yml`:**

```yaml
spring:
  application:
    name: authorized-client-lab

server:
  port: 8080
```

Không cấu hình `spring.security.oauth2.client.registration` trong project lab vì code bên dưới tạo explicit `ClientRegistration`. Không thêm MVC starter. Đối với OAuth2 client thật, có thể dùng Boot properties để cấu hình provider/registration; xem mục 12.

### 8.3. Main class

**`src/main/java/example/oauth2lab/AuthorizedClientLabApplication.java`:**

```java
package example.oauth2lab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizedClientLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthorizedClientLabApplication.class, args);
    }
}
```

### 8.4. SecurityWebFilterChain: HTTP Basic, giữ CSRF

**`src/main/java/example/oauth2lab/SecurityConfiguration.java`:**

```java
package example.oauth2lab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService demoUsers(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("local-demo-password"))
                .roles("USER")
                .build();
        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("local-demo-password"))
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(alice, bob);
    }

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .anyExchange().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

Ở đây authentication **vào** ứng dụng là Basic chỉ để test. Nó **khác** OAuth2 client_credentials dùng để lấy token **đi ra**. Chưa bật OAuth2 login; demo điều phối authorized clients trực tiếp qua manager bean nên không cần thực hiện browser authorization-code redirect.

CSRF vẫn bật mặc định. Các endpoint POST trong demo phải gửi token, kể cả đã authenticated. Không tắt CSRF để test được 200. Mật khẩu mẫu không được dùng ở production và HTTP Basic chỉ nên sử dụng qua HTTPS ngoài localhost.

### 8.5. LearningAuthorizedClientProvider: chỉ dùng trong lab

**`src/main/java/example/oauth2lab/LearningAuthorizedClientProvider.java`:**

```java
package example.oauth2lab;

import java.time.Duration;
import java.time.Instant;
import java.util.Set;

import org.springframework.security.oauth2.client.OAuth2AuthorizationContext;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("learningProvider")
public class LearningAuthorizedClientProvider
        implements ReactiveOAuth2AuthorizedClientProvider {

    @Override
    public Mono<OAuth2AuthorizedClient> authorize(
            OAuth2AuthorizationContext context) {

        if (!"sandbox".equals(
                context.getClientRegistration().getRegistrationId())) {
            return Mono.empty();
        }

        OAuth2AuthorizedClient existing = context.getAuthorizedClient();
        Instant now = Instant.now();

        if (existing != null
                && existing.getAccessToken().getExpiresAt() != null
                && existing.getAccessToken().getExpiresAt()
                        .isAfter(now.plusSeconds(60))) {
            // Existing record is valid: manager can reuse it.
            return Mono.empty();
        }

        // ONLY FOR TESTS: no network, no signature, no real OAuth2 grant.
        OAuth2AccessToken fake = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "not-a-real-access-token",
                now,
                now.plus(Duration.ofMinutes(15)),
                Set.of("demo.read"));

        return Mono.just(new OAuth2AuthorizedClient(
                context.getClientRegistration(),
                context.getPrincipal().getName(),
                fake));
    }
}
```

**Bảo mật:** class này cố ý không liên hệ token endpoint, không tạo JWT hợp lệ, không xác thực consent, không thu hồi token; **chỉ dùng trong lab**. Không cấu hình nó trong production. Khi thay bằng provider thật, token sẽ do Authorization Server cấp theo grant/client registration đã đăng ký.

Đường nhánh `Mono.empty()` khi có client còn hợp lệ biểu đạt provider không cần cấp token mới; manager có thể trả lại authorized client đã được load. Khi chưa có authorized client, provider trả record giả để kiểm chứng save/load/remove.

### 8.6. Khai báo ba thành phần và hai manager

**`src/main/java/example/oauth2lab/AuthorizedClientConfiguration.java`:**

```java
package example.oauth2lab;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;

@Configuration(proxyBeanMethods = false)
public class AuthorizedClientConfiguration {

    @Bean
    ReactiveClientRegistrationRepository registrations() {
        ClientRegistration registration = ClientRegistration
                .withRegistrationId("sandbox")
                .clientId("learning-client")
                .clientSecret("not-a-real-client-secret")
                .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri("https://idp.example.invalid/oauth2/token")
                .scope("demo.read")
                .build();

        return new InMemoryReactiveClientRegistrationRepository(registration);
    }

    @Bean
    ReactiveOAuth2AuthorizedClientService authorizedClientService(
            ReactiveClientRegistrationRepository registrations) {
        return new InMemoryReactiveOAuth2AuthorizedClientService(
                registrations);
    }

    @Bean
    ServerOAuth2AuthorizedClientRepository authorizedClientRepository(
            ReactiveOAuth2AuthorizedClientService service) {
        return new AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository(
                service);
    }

    @Bean("browserManager")
    ReactiveOAuth2AuthorizedClientManager browserManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository repository,
            @Qualifier("learningProvider")
                    ReactiveOAuth2AuthorizedClientProvider provider) {

        DefaultReactiveOAuth2AuthorizedClientManager manager =
                new DefaultReactiveOAuth2AuthorizedClientManager(
                        registrations, repository);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean("jobManager")
    ReactiveOAuth2AuthorizedClientManager jobManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService service,
            @Qualifier("learningProvider")
                    ReactiveOAuth2AuthorizedClientProvider provider) {

        AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                        registrations, service);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

**Từng bean có ý nghĩa gì?**

- `registrations()` tạo cấu hình registration `sandbox`. URI `idp.example.invalid` là placeholder **không được gọi** trong lab vì provider giả hoàn thành authorize ở bộ nhớ. Client secret cũng là chuỗi giả; không dùng trong production.
- `authorizedClientService()` là store ứng dụng, keyed theo principalName + registrationId.
- `authorizedClientRepository()` dùng bridge: với principal authenticated, repository thao tác thông qua **chính service này**; với anonymous, bridge dùng WebSession repository theo mặc định.
- `browserManager` cần `ServerWebExchange` vì dùng `DefaultReactiveOAuth2AuthorizedClientManager`.
- `jobManager` không cần exchange vì dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.
- Cả hai nhận cùng `learningProvider` để tự tạo record giả. Hai manager dùng **cùng service** với principal khác nhau, nhưng đây là quyết định minh họa có chủ đích.
- Đặt tên và `@Qualifier` tránh nhập nhằng khi có **hai bean cùng interface** `ReactiveOAuth2AuthorizedClientManager`.
- Hệ thống thật nên không tự tạo "fake provider" mà dùng `ReactiveOAuth2AuthorizedClientProviderBuilder` cho grant thực và cấu hình secrets từ secret manager.

## 9. Controller WebFlux: lưu/đọc/xóa authorized client theo request

**`src/main/java/example/oauth2lab/AuthorizedClientController.java`:**

```java
package example.oauth2lab;

import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class AuthorizedClientController {

    private final ReactiveOAuth2AuthorizedClientManager browserManager;
    private final ServerOAuth2AuthorizedClientRepository repository;

    public AuthorizedClientController(
            @Qualifier("browserManager")
                    ReactiveOAuth2AuthorizedClientManager browserManager,
            ServerOAuth2AuthorizedClientRepository repository) {
        this.browserManager = browserManager;
        this.repository = repository;
    }

    private Mono<Authentication> currentAuthentication() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication());
    }

    private Map<String, String> summary(OAuth2AuthorizedClient client) {
        return Map.of(
                "state", "present",
                "registration", client.getClientRegistration()
                        .getRegistrationId(),
                "principal", client.getPrincipalName()
        );
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @PostMapping("/demo/browser/authorize")
    public Mono<Map<String, String>> authorize(ServerWebExchange exchange) {
        return currentAuthentication()
                .flatMap(authentication -> {
                    OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
                            .withClientRegistrationId("sandbox")
                            .principal(authentication)
                            .attribute(
                                    ServerWebExchange.class.getName(),
                                    exchange)
                            .build();

                    return browserManager.authorize(request);
                })
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.BAD_GATEWAY,
                                "Authorized client unavailable")))
                .map(this::summary);
    }

    @GetMapping("/demo/browser/status")
    public Mono<Map<String, String>> status(ServerWebExchange exchange) {
        return currentAuthentication()
                .flatMap(authentication ->
                        repository.<OAuth2AuthorizedClient>
                                loadAuthorizedClient(
                                        "sandbox", authentication, exchange))
                .map(this::summary)
                .defaultIfEmpty(Map.of("state", "absent"));
    }

    @PostMapping("/demo/browser/remove")
    public Mono<Map<String, String>> remove(ServerWebExchange exchange) {
        return currentAuthentication()
                .flatMap(authentication ->
                        repository.removeAuthorizedClient(
                                "sandbox", authentication, exchange))
                .thenReturn(Map.of("state", "removed"));
    }
}
```

**Giải thích chi tiết:**

1. Controller lấy `Authentication` từ `ReactiveSecurityContextHolder` của **request subscription**, không dùng thread-local `SecurityContextHolder.getContext()`.
2. `authorize()` truyền `ServerWebExchange.class.getName()` attribute; manager chọn provider, lưu record qua repository và trả kết quả. Không tự gọi `service.save...` lần hai.
3. `status()` chỉ đọc repository, **không gọi manager**, nên không cố xin/refresh token nếu record thiếu. Nó trả "absent" hoặc metadata ít nhạy cảm, **không trả raw access token**.
4. `remove()` xóa local record, **không revoke token tại IdP**. Chỉ là demo quản trị storage và không được biến thành endpoint công khai ở production.
5. Mọi endpoint `/demo/...` yêu cầu authenticated; các POST còn chịu CSRF mặc định. Demo local sử dụng Basic trong test để tạo identity.
6. Repository dùng bridge cho authenticated user, vì thế sau browser authorize, direct service lookup với **cùng principal name** có thể tìm thấy record.
7. Đây là logic ứng dụng học, không phải endpoint OAuth2 callback, Authorization Server hoặc gateway bảo vệ token thật. Không dùng API này ở Internet production.

## 10. Job/service không có ServerWebExchange

**`src/main/java/example/oauth2lab/MachineJob.java`:**

```java
package example.oauth2lab;

import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class MachineJob {

    private final ReactiveOAuth2AuthorizedClientManager manager;

    public MachineJob(
            @Qualifier("jobManager")
                    ReactiveOAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public Mono<String> runOnce() {
        // A trusted service identity, not an HTTP user's identity.
        Authentication principal =
                new UsernamePasswordAuthenticationToken(
                        "system:reports", "N/A",
                        List.of(new SimpleGrantedAuthority("ROLE_SYSTEM")));

        OAuth2AuthorizeRequest request =
                OAuth2AuthorizeRequest
                        .withClientRegistrationId("sandbox")
                        .principal(principal)
                        .build();

        return manager.authorize(request)
                .switchIfEmpty(Mono.error(
                        new IllegalStateException(
                                "No client authorization available")))
                .map(client -> client.getClientRegistration()
                        .getRegistrationId() + ":" + client.getPrincipalName());
    }
}
```

Method này **không nhận ServerWebExchange** và không phụ thuộc HTTP Reactor Context. Trong production, một scheduler/queue consumer đáng tin có thể gọi `runOnce()` như một phần của pipeline của job. Không gọi `.subscribe()` trong service để trả thành công trước khi nhận token. Không tạo endpoint công khai cho user tùy chọn principalName và xin `client_credentials` của ứng dụng.

Kết quả dự kiến của test:

```text
sandbox:system:reports
```

Đây là **tên registration + principal**, không phải token. Với principal name riêng, token của job không bị trộn với record của `alice` hoặc `bob`.

## 11. Kiểm thử bằng WebTestClient và StepVerifier

Test tập trung đúng ba thành phần: manager **điều phối**; repository **lưu theo request/principal**; service **đọc dữ liệu ứng dụng**. Mock provider tạo token giả, nên test không cần token endpoint thật.

**`src/test/java/example/oauth2lab/AuthorizedClientIntegrationTest.java`:**

```java
package example.oauth2lab;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class AuthorizedClientIntegrationTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    ReactiveOAuth2AuthorizedClientService service;

    @Autowired
    MachineJob job;

    private WebTestClient client;

    @BeforeEach
    void prepare() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();

        StepVerifier.create(Mono.when(
                service.removeAuthorizedClient("sandbox", "alice"),
                service.removeAuthorizedClient("sandbox", "bob"),
                service.removeAuthorizedClient(
                        "sandbox", "system:reports")))
                .verifyComplete();
    }

    @Test
    void publicPingWorks() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousCannotInspectAuthorizedClient() {
        client.get().uri("/demo/browser/status")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void aliceStartsWithoutAuthorizedClient() {
        client.mutateWith(mockUser("alice"))
                .get().uri("/demo/browser/status")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.state").isEqualTo("absent");
    }

    @Test
    void authorizeWithoutCsrfIsRejected() {
        client.mutateWith(mockUser("alice"))
                .post().uri("/demo/browser/authorize")
                .exchange()
                .expectStatus().isForbidden();

        StepVerifier.create(service
                .<OAuth2AuthorizedClient>loadAuthorizedClient(
                        "sandbox", "alice"))
                .verifyComplete();
    }

    @Test
    void authorizeWithCsrfPersistsForAlice() {
        client.mutateWith(mockUser("alice"))
                .mutateWith(csrf())
                .post().uri("/demo/browser/authorize")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.registration").isEqualTo("sandbox")
                .jsonPath("$.principal").isEqualTo("alice")
                .jsonPath("$.state").isEqualTo("present");

        StepVerifier.create(service
                .<OAuth2AuthorizedClient>loadAuthorizedClient(
                        "sandbox", "alice"))
                .assertNext(saved -> {
                    assertEquals("sandbox",
                            saved.getClientRegistration().getRegistrationId());
                    assertEquals("alice", saved.getPrincipalName());
                    assertTrue(saved.getAccessToken().getExpiresAt()
                            .isAfter(java.time.Instant.now()));
                })
                .verifyComplete();
    }

    @Test
    void bobDoesNotReuseAlicesAuthorizedClient() {
        client.mutateWith(mockUser("alice"))
                .mutateWith(csrf())
                .post().uri("/demo/browser/authorize")
                .exchange()
                .expectStatus().isOk();

        client.mutateWith(mockUser("bob"))
                .get().uri("/demo/browser/status")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.state").isEqualTo("absent");
    }

    @Test
    void sameAuthenticatedPrincipalFindsSavedRecord() {
        client.mutateWith(mockUser("alice"))
                .mutateWith(csrf())
                .post().uri("/demo/browser/authorize")
                .exchange()
                .expectStatus().isOk();

        client.mutateWith(mockUser("alice"))
                .get().uri("/demo/browser/status")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.state").isEqualTo("present")
                .jsonPath("$.principal").isEqualTo("alice");
    }

    @Test
    void removingLocalRecordMakesStatusAbsent() {
        client.mutateWith(mockUser("alice"))
                .mutateWith(csrf())
                .post().uri("/demo/browser/authorize")
                .exchange()
                .expectStatus().isOk();

        client.mutateWith(mockUser("alice"))
                .mutateWith(csrf())
                .post().uri("/demo/browser/remove")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.state").isEqualTo("removed");

        client.mutateWith(mockUser("alice"))
                .get().uri("/demo/browser/status")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.state").isEqualTo("absent");
    }

    @Test
    void jobWorksWithoutServerWebExchange() {
        StepVerifier.create(job.runOnce())
                .expectNext("sandbox:system:reports")
                .verifyComplete();
    }

    @Test
    void jobRecordIsSeparateFromAlice() {
        StepVerifier.create(job.runOnce())
                .expectNext("sandbox:system:reports")
                .verifyComplete();

        StepVerifier.create(service
                .<OAuth2AuthorizedClient>loadAuthorizedClient(
                        "sandbox", "system:reports"))
                .assertNext(saved ->
                        assertEquals("system:reports",
                                saved.getPrincipalName()))
                .verifyComplete();

        StepVerifier.create(service
                .<OAuth2AuthorizedClient>loadAuthorizedClient(
                        "sandbox", "alice"))
                .verifyComplete();
    }
}
```

Chạy:

```bash
./gradlew test --tests example.oauth2lab.AuthorizedClientIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.oauth2lab.AuthorizedClientIntegrationTest
```

Kỳ vọng **10 test PASS** khi dùng project, dependencies và mock provider theo bài. Đây là **kỳ vọng từ source code**, không phải một lần compile/test thực tế đã được thực hiện trong môi trường của người học.

### Những gì kiểm thử xác nhận

| Test | Ý nghĩa |
| --- | --- |
| Public ping và anonymous | Security HTTP vẫn có hiệu lực, OAuth2 storage không tự xác thực caller |
| Alice status trước authorize | Repository không tạo token chỉ vì bị đọc |
| Alice POST thiếu CSRF | Request bị chặn trước khi manager lưu, service vẫn trống |
| Alice POST có CSRF | Web manager gọi mock provider và **lưu thông qua repository → service** |
| Bob không thấy token Alice | Record phân biệt principalName |
| Cùng Alice đọc status | Repository bridge tới service giữa hai requests dùng mock identity |
| Remove local record | Local storage xóa bản ghi, khác remote revoke |
| Job không có exchange | Service-based manager hoạt động ngoài HTTP |
| Job principal khác Alice | Không gộp token người dùng và service identity |

**Hạn chế của test:**

- `mockUser` dựng Authentication giả theo request, không kiểm chứng Basic password thực hay OAuth2 login callback.
- `csrf()` chèn CSRF token test hợp lệ; chưa chứng minh token HTML/browser thật.
- Provider giả không thực hiện token request/refresh, nên test chưa chứng minh authorization_code, PKCE, consent, refresh rotation, token endpoint timeouts, distributed DB hoặc JWT validation.
- `InMemoryReactiveOAuth2AuthorizedClientService` là store dùng chung trong test context. Các test trên reset state trước mỗi test; nếu bật **parallel testing**, phải cô lập context/storage hoặc thay cơ chế test để tránh race.
- Không kiểm tra bảo mật access token thật vì project cố ý không có token thật.

## 12. Thay provider giả bằng OAuth2 grant thật

Khi tích hợp IdP thật, **xóa `LearningAuthorizedClientProvider`** và thay cấu hình manager bằng provider builder:

```java
ReactiveOAuth2AuthorizedClientProvider provider =
        ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();

DefaultReactiveOAuth2AuthorizedClientManager webManager =
        new DefaultReactiveOAuth2AuthorizedClientManager(
                registrations, serverRepository);
webManager.setAuthorizedClientProvider(provider);

AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager jobManager =
        new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClientService);
jobManager.setAuthorizedClientProvider(
        ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build());
```

Đây là **fragment production-oriented**, giả sử registrations/repository/service đã được cấu hình từ IdP thật. Không đặt hai bean cùng tên với bean demo ở mục 8; thay thế config thay vì dán chồng mã.

### 12.1. Ví dụ Boot properties cho client_credentials

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory:
            provider: company-idp
            client-id: inventory-service
            client-secret: ${INVENTORY_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: inventory.read
        provider:
          company-idp:
            token-uri: https://idp.example.test/oauth2/token
```

Giá trị trong `${INVENTORY_CLIENT_SECRET}` được Spring resolve từ environment/secret manager khi chạy thật; **không** đưa secret thực vào Git, README, log hoặc exception. URL này chỉ mô tả topology; cần thay bằng endpoint của IdP thực có TLS và cấu hình client. Trong Code sample trên, string placeholder vẫn phải được Spring resolve lúc ứng dụng khởi động.

Để lấy token từ manager service-based trong một job:

```java
return jobManager.authorize(
        OAuth2AuthorizeRequest.withClientRegistrationId("inventory")
                .principal("system:inventory")
                .build()
).switchIfEmpty(Mono.error(
        new IllegalStateException("Token grant not supported")));
```

Đây là fragment minh họa trong service có `jobManager` đã inject; `principal(String)` là một overload của builder để định danh principal, không phải chứng cứ user login.

### 12.2. authorization_code khác client_credentials

| Đặc điểm | authorization_code | client_credentials |
| --- | --- | --- |
| Chủ thể quyền | Người dùng Resource Owner cấp consent | Client ứng dụng tự lấy quyền theo client registration |
| Browser redirect | Có, với login/authorization request và callback | Không cần user redirect |
| PKCE | Nên dùng khi provider/client flow yêu cầu, đặc biệt public clients | Không phải cơ chế chính |
| Refresh token | Có thể có, tùy IdP | Thường không cần; xin access token mới khi hết hạn |
| PrincipalName trong authorized client | User đã đăng nhập/cấp quyền | Service principal ổn định của hệ thống |
| Manager hợp lý | Web exchange manager | Service-based manager cho job nền |
| Rủi ro khi dùng nhầm | Token của Alice bị dùng thay Bob | Quyền service rộng hơn quyền user, confused deputy |

Spring Security WebFlux có `oauth2Login(...)` (đăng nhập user bằng OAuth2/OIDC) và `oauth2Client(...)` (Client support); chúng có liên quan nhưng **không phải cùng mục đích**. Client credentials không tự tạo user session và không thay authorization của API inbound.

### 12.3. Ví dụ application.yml cho authorization_code

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: company-idp
            client-id: portal-web
            client-secret: ${PORTAL_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile
        provider:
          company-idp:
            issuer-uri: https://idp.example.test
```

Đây là cấu hình **minh họa với IdP thật**, không chạy offline trong project lab. Cần IdP công khai metadata đúng, registered redirect URI chính xác, TLS/proxy forwarded configuration đúng, client authentication, PKCE theo loại client và chính sách IdP. Với ứng dụng WebFlux, có thể cấu hình `ServerHttpSecurity.oauth2Login(Customizer.withDefaults())` cùng `oauth2Client(Customizer.withDefaults())` khi cần.

### 12.4. Khi nào token được refresh?

- `authorization_code` client đã có refresh token: provider `refreshToken()` có thể xin access token mới.
- `client_credentials`: thường dùng provider `clientCredentials()` để xin access token khác khi gần hết hạn, không cần refresh token.
- Khi provider nhận `invalid_grant`, failure handler mặc định có thể remove authorized client cũ; log theo mã lỗi (không log raw token).
- Nếu token chưa cần đổi, manager có thể trả authorized client hiện tại mà không gọi token endpoint.
- Có nhiều request đồng thời cùng refresh: đừng tự giả định manager/service thực hiện single-flight cho mọi cluster; cân nhắc distributed synchronization/caching và metrics theo thực tế.

## 13. Tránh lộ token và lỗi bảo mật theo principal

### 13.1. Principal isolation

Một authorized client được định danh bởi registrationId và principalName, không phải tên registration duy nhất. Trong hệ thống đa tenant:

- Không dùng `getName()` là email có thể đổi hoặc trùng giữa tenant nếu không có tenant namespace.
- Dùng subject ID bất biến kết hợp tenant đã xác minh từ Authentication.
- Không nhận `principalName` từ HTTP query param để lấy token người khác.
- Với user Alice và Bob cùng có registration `crm`, không dùng token Alice cho request Bob.
- Với `client_credentials`, dùng tên service identity riêng, không tùy ý impersonate user.

### 13.2. Storage và secret handling

Access token và refresh token là bí mật. Cần:

- Mã hóa at rest, tối thiểu hóa quyền DB, log masking và rotation secrets.
- TTL, cleanup hết hạn và phân biệt xóa local record với remote revoke.
- Không đưa token vào exception message, response JSON, URL query string, browser localStorage không cần thiết.
- Tránh cấu hình WebClient mặc định gắn token vào mọi hostname/redirect.
- Xác thực TLS của token endpoint và Resource Server; không tắt certificate checks cho production.
- Nếu lưu token trong WebSession, bảo vệ session store/backup; cookie trình duyệt chỉ nên giữ opaque session ID, không nhét refresh token raw vào cookie.
- Đảm bảo secrets chỉ được inject từ môi trường/secret manager, không commit values vào repository.

### 13.3. Refresh token rotation

IdP có thể trả **refresh token mới** khi dùng token cũ. Service/repository phải ghi nhận authorized client mới chính xác; nếu custom persistence làm mất refresh token mới, phiên có thể thất bại ở lần tiếp theo. Xử lý concurrent refresh và invalid_grant theo policy: tránh retry vô hạn cùng refresh token cũ.

### 13.4. Logout không tự revoke access token

Nếu user logout khỏi Spring Security mà authorized client vẫn được service lưu, token có thể còn tồn tại trong app store. Quyết định cần:

- Xóa local authorized client khi session/user bị thu hồi?
- Gọi remote token revocation endpoint nếu IdP hỗ trợ?
- OIDC RP-initiated logout có yêu cầu?
- Giữ hay xóa token service-level dành cho job?
- Làm sao invalidate cache phân tán?

Đừng ghép một lệnh `SecurityContextServerLogoutHandler` rồi tuyên bố `ReactiveOAuth2AuthorizedClientService` tự xóa mọi token liên quan.

## 14. Những lỗi cấu hình điển hình

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Job không có HTTP request gọi DefaultReactive... | `ServerWebExchange` thiếu | Dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| Manager nhận sai registrationId | Không tìm thấy ClientRegistration hoặc grant khác | Cấu hình đúng registration, test expected grant |
| `authorize(...)` trả `Mono.empty()` | Provider không hỗ trợ grant hoặc không có authorized client | Kiểm tra grant/provider, fail-closed; không dùng fake permit |
| Service lookup trống, repository có token | Repository lưu trong WebSession chứ không delegate service | Xác định đúng implementation và storage |
| Alice nhìn thấy token Bob | PrincipalName bị dùng chung hoặc client tự chỉ định name | Lấy identity từ authenticated SecurityContext |
| Có token nhưng resource trả 401 | Token hết hạn/revoked/wrong audience | Refresh/re-authorize theo policy, validate IdP config |
| Resource trả 403 insufficient_scope | Client thiếu scope/permission | Cấu hình đúng grants/scopes và resource policy |
| Refresh token liên tục invalid_grant | Rotation/revocation/concurrency không nhất quán | Remove cached invalid client, yêu cầu reauth nếu cần |
| POST demo trả 403 | Thiếu CSRF token với browser session | Gửi CSRF đúng; không tắt CSRF bừa |
| WebClient gọi API khác vẫn mang Bearer | Default client trên shared WebClient | Chọn registration per request, allowlist host |
| Lỗi Netty blocked event loop | Gọi `block()` trong WebFlux hoặc JDBC blocking | Compose Mono/Flux, dùng driver reactive |
| Handler gọi `subscribe()` rồi trả ngay | Token acquisition chưa xong, mất context | Return publisher đầy đủ |
| Token mất sau restart | `InMemoryReactiveOAuth2AuthorizedClientService` | Dùng R2DBC/custom persistent storage nếu cần |
| Multi-instance refresh lặp | In-memory cache riêng hoặc thiếu coordination | Persistence/caching phân tán và retry giới hạn |
| Ghi secret vào application.yml trong Git | Client secret lộ | Env var, secret manager, rotation |
| Logout local nhưng token vẫn hoạt động | Xóa session không revoke remote token | Thiết kế revoke/logout/idp coordination |
| OAuth2 login callback sai host/scheme | Reverse proxy forwarded headers sai | Trusted Forwarded strategy, HTTPS public |
| JWT dùng để gọi outbound sai audience | Nhầm inbound access token với client token | Tách Resource Server và OAuth2 Client policy |
| Dùng Servlet OAuth2AuthorizedClientService | Sai stack synchronous | Chọn `ReactiveOAuth2AuthorizedClientService` |
| Dùng một bearer token cho tất cả request | Confused deputy/overprivileged client | Least privilege, principal isolation, scope policy |

## 15. Kiểm thử production cần bổ sung

Bộ test offline ở mục 11 **không** thay cho integration test OAuth2 thực. Checklist mở rộng:

1. Kiểm tra `authorization_code` với browser redirect và callback, state/PKCE/consent theo policy IdP.
2. Test `client_credentials` với token endpoint sandbox do bạn quản lý: client authentication, scopes và token audience.
3. Mock `invalid_grant` và xác nhận failure handler xóa client cũ đúng storage (không xóa nhầm principal).
4. Mock timeout/5xx/429 của token endpoint: không fallback cấp quyền, retry giới hạn và telemetry.
5. Test clock skew, token expiresAt, refresh trước hạn, rotation, concurrent requests.
6. Test Alice/Bob cùng registration và nhiều tenant, không lộ token chéo.
7. Test service-based manager chạy trong job không có `ServerWebExchange`.
8. Test WebClient chỉ gắn Bearer token ở hostname/resource cho phép, không gửi sang redirect/host tùy ý.
9. Test encrypted persistence, R2DBC schema, restart, multi-instance, cleanup theo TTL.
10. Test logout/session invalidation và token revocation riêng biệt.
11. Test inbound Resource Server không vô tình dựa vào client token state để xác thực caller.
12. Test 401/403/503/timeout semantically đúng và không lộ access token trong logs.

### Phân biệt các phép kiểm thử

| Phép kiểm thử | Chứng minh | Không chứng minh |
| --- | --- | --- |
| InMemory service save/load/remove | Storage keyed theo registration/principal | Token OAuth2 thật còn hiệu lực |
| Mock provider + browser manager | Manager gọi provider và persistence | Authorization Server thực cấp token |
| WebTestClient với mockUser + csrf | WebFlux filter, request principal và CSRF | OAuth2 login thật hoặc cross-origin browser |
| Service manager + StepVerifier | Job không cần HTTP exchange | Secret rotation/IdP token grant |
| Token endpoint sandbox thật | Grant HTTP/TLS và lỗi OAuth2 | Resource Server chắc chắn nhận scope/audience |
| Browser + reverse proxy + IdP | End-to-end login/callback/TLS | Không có bug ở service data policy |

## 16. Bài tập thực hành

1. Thêm client registration `billing` ngoài `sandbox`, tạo test chứng minh mỗi registrationId có authorized client độc lập.
2. Gọi POST authorize với `mockUser("alice")` rồi GET status bằng Bob: vì sao phải nhận "absent"? Đâu là key lưu trữ?
3. Chuyển `AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository` sang pure `WebSessionServerOAuth2AuthorizedClientRepository` trong nhánh test; quan sát sự khác biệt với service lookup.
4. Tạo test direct service `saveAuthorizedClient(...)` rồi `loadAuthorizedClient(...)`/`removeAuthorizedClient(...)`, không truyền ServerWebExchange. Giải thích ứng dụng nào phù hợp.
5. Thay mock provider bằng `ReactiveOAuth2AuthorizedClientProviderBuilder.builder().clientCredentials().build()`, kết nối một token endpoint sandbox. Giải thích expected HTTP exchange.
6. Thêm manager `authorizationCode().refreshToken()` và dựng flow OAuth2 login thật trên staging; test user consent, callback, refresh.
7. Giả lập access token hết hạn và refresh failure `invalid_grant`: record bị loại bỏ hay vẫn lưu? Xác minh đúng handler của phiên bản.
8. Chuyển service từ in-memory sang `R2dbcReactiveOAuth2AuthorizedClientService` với schema theo tài liệu Spring, mã hóa token khi lưu.
9. Tạo hai job dùng service principal khác nhau, chứng minh không lấy nhầm token.
10. Bổ sung WebClient outbound request tới mock resource server; dùng `clientRegistrationId("sandbox")` nhưng **không** gửi token giả ra endpoint thật. Test header Bearer qua mock server.
11. Gắn token filter lên WebClient dùng chung rồi thử host không tin cậy; sửa để không làm rò token qua SSRF/redirect.
12. Vẽ lại luồng: client registration → manager/provider → service/repository → WebClient → resource server, chú thích nơi token có thể hết hạn/thu hồi.
13. Thêm kiểm thử profile production **không** cho load bean `LearningAuthorizedClientProvider`, tránh deploy mock token.
14. So sánh điều gì xảy ra nếu user logout session nhưng authorized client vẫn được lưu ở application service; đề xuất policy remove/revoke.
15. Giải thích vì sao `oauth2Client()` không đồng nghĩa `oauth2Login()` và tại sao OAuth2 Resource Server cần cấu hình inbound riêng.

## 17. Tổng kết

**Ba khái niệm cốt lõi là ba trách nhiệm khác nhau:**

- `ReactiveOAuth2AuthorizedClientManager` **điều phối**: tra authorized client, dùng provider phù hợp grant để lấy/đổi token, gọi success/failure handlers và giữ trạng thái qua storage.
- `ReactiveOAuth2AuthorizedClientService` **quản lý ứng dụng**: lưu/đọc/xóa authorized client theo `registrationId + principalName` mà không cần HTTP request; phù hợp job/service tier và kho dữ liệu dùng chung.
- `ServerOAuth2AuthorizedClientRepository` **quản lý trong ngữ cảnh WebFlux**: lưu/đọc/xóa authorized client theo `Authentication + ServerWebExchange`; tùy implementation, có thể lưu trong WebSession hoặc delegate vào application service.

**Chọn đúng manager:** `DefaultReactiveOAuth2AuthorizedClientManager` khi có WebFlux request; `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` khi chạy ngoài ServerWebExchange. Đừng đánh đồng registration với token, token với user identity, hoặc local remove với remote revocation. Mọi token phải được quản lý như bí mật; outbound WebClient chỉ gửi tới API tin cậy với grant/scope/principal phù hợp.

## Tài liệu chính thức

- [Spring Security 6.5 — OAuth2 Client Core Interfaces and Classes (reactive)](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html)
- [Spring Security 6.5 — Reactive Authorized Client Features / WebClient](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html)
- [Spring Security 6.5 — OAuth2 WebFlux Client](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html)
- [ReactiveOAuth2AuthorizedClientManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientManager.html)
- [ReactiveOAuth2AuthorizedClientService Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientService.html)
- [ServerOAuth2AuthorizedClientRepository Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/server/ServerOAuth2AuthorizedClientRepository.html)
- [AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager.html)
- [Spring Security — OAuth2 Client Schema](https://docs.spring.io/spring-security/reference/6.5/appendix/database-schema.html)
- [Spring Security 6.5 — Reactive WebClient Test Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
