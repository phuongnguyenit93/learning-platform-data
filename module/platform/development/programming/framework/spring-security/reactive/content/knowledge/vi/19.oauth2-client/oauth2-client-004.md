# Lựa chọn manager trong yêu cầu web và trong tác vụ ngoài yêu cầu

> **Chủ đề:** Spring Security – reactive  
> **Nhóm:** OAuth2 Client  
> **Bài học:** Chọn đúng `ReactiveOAuth2AuthorizedClientManager` khi ứng dụng có `ServerWebExchange` (request WebFlux) và khi tác vụ chạy **ngoài request** (scheduler, queue consumer, batch job, service-to-service).  
> **Phạm vi phiên bản ví dụ:** Java 17+, Spring Boot 3.5.x và Spring Security 6.5.x; các API cốt lõi được đối chiếu với tài liệu Spring Security chính thức.

## 1. Vấn đề: cùng một WebClient nhưng có hai ngữ cảnh

Giả sử một ứng dụng Spring WebFlux có hai nhu cầu:

1. Người dùng `alice` đăng nhập ở website, chọn “Xem báo cáo”, và backend gọi downstream API bằng **access token được cấp cho người dùng/client**. Phép gọi diễn ra trong một HTTP request có `ServerWebExchange`, `Authentication`, WebSession và các thuộc tính web.
2. Một tác vụ `@Scheduled` chạy hằng đêm để đồng bộ báo cáo. Không có browser, HTTP request đầu vào, `ServerWebExchange` hay user login. Job xin access token bằng `client_credentials` để gọi downstream API với danh tính **chính service**.

Cả hai đều cần một **OAuth2 Client** có khả năng cấp hoặc gia hạn access token trước khi gọi API, nhưng **không dùng cùng một manager một cách mù quáng**.

**Quy tắc lựa chọn:**

| Ngữ cảnh | Manager Spring Security reactive nên dùng | Nơi lưu authorized client |
| --- | --- | --- |
| Trong WebFlux HTTP request, có `ServerWebExchange` | `DefaultReactiveOAuth2AuthorizedClientManager` | `ServerOAuth2AuthorizedClientRepository` |
| Ngoài HTTP request, ở scheduler/queue/service-tier | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientService` |

Cả hai implement **`ReactiveOAuth2AuthorizedClientManager`**; lựa chọn khác nhau ở **ngữ cảnh có sẵn, cách tải/lưu token và grant/principal được sử dụng**. Không có quy tắc “cứ dùng `WebClient` là chọn web manager”; tên `WebClient` chỉ nói bạn sử dụng một HTTP client **reactive**, không bảo đảm code đang chạy trong một server web request.

### Sau bài này bạn có thể

- Giải thích đúng `OAuth2AuthorizedClient`, `ReactiveOAuth2AuthorizedClientManager`, `ReactiveOAuth2AuthorizedClientProvider`, registration và hai kiểu store.
- Chọn manager đúng theo sự hiện diện của `ServerWebExchange` chứ không theo class gọi nó.
- Gọi `authorize(OAuth2AuthorizeRequest)` đúng và hiểu khi nào kết quả là `Mono.empty()`.
- Phân biệt `authorization_code` + `refresh_token` cho ngữ cảnh người dùng với `client_credentials` cho tác vụ hệ thống.
- Đặt chính xác `clientRegistrationId`, `Authentication`/principal và web exchange.
- Cấu hình hai `WebClient` có `@Qualifier` riêng, không vô tình gửi Bearer token tới mọi host.
- Dùng `StepVerifier` để test token **đã được seed trong store** mà không phụ thuộc IdP thật và biết giới hạn của test đó.
- Tránh lỗi blocking, cross-user token leak, dùng sai cache key, reuse token từ user request trong background task và cấu hình credential thất bại.

## 2. OAuth2 Authorized Client nghĩa là gì?

Một `ClientRegistration` chỉ mô tả **ứng dụng đã đăng ký với Authorization Server**:

```text
registrationId, clientId, clientSecret,
authorizationGrantType, scopes,
authorizationUri/tokenUri/redirectUri ...
```

Nó **không phải** access token. Sau khi OAuth2 Client được cấp phép và lấy được token, Spring Security biểu diễn trạng thái đó qua `OAuth2AuthorizedClient`:

```text
OAuth2AuthorizedClient
  ├── ClientRegistration  (client nào?)
  ├── principalName       (user hoặc system identity nào?)
  ├── OAuth2AccessToken   (Bearer token và hạn dùng)
  └── OAuth2RefreshToken? (nếu được cấp)
```

Quan trọng: authorized client gắn **registrationId + principal name**. Khi web user `alice` có token cho `reports-user`, token đó **không được tự động tái sử dụng** cho `bob`. Với một batch job, principal như `reports-scheduler` chỉ là **tên ổn định để định danh/caching token của service**; nó **không biến token client_credentials thành token người dùng**.

### 2.1. Manager làm những việc gì?

`ReactiveOAuth2AuthorizedClientManager` có API chính:

```java
Mono<OAuth2AuthorizedClient> authorize(
    OAuth2AuthorizeRequest authorizeRequest);
```

Đây là **chữ ký API** (không phải method để bạn tự viết lại). Manager có nhiệm vụ:

1. Tìm client registration theo `clientRegistrationId`.
2. Tải `OAuth2AuthorizedClient` đã lưu cho principal tương ứng nếu có.
3. Dùng `ReactiveOAuth2AuthorizedClientProvider` thích hợp để **authorize/re-authorize**, ví dụ code grant, refresh token hoặc client credentials.
4. Khi thành công, lưu/cập nhật authorized client bằng repository/service phù hợp.
5. Khi thất bại, xử lý theo failure handler/policy; một số lỗi như `invalid_grant` có thể khiến token/authorized client cũ bị xóa.

Không phải mọi `authorize` đều gọi mạng tới Authorization Server. Một token **còn hiệu lực** trong store có thể được tái sử dụng; một token cần refresh hoặc chưa có token có thể kích hoạt token endpoint.

### 2.2. Provider quyết định grant, manager quyết định phối hợp

`ReactiveOAuth2AuthorizedClientProvider` là strategy cho các authorization grants. Dùng builder:

```java
ReactiveOAuth2AuthorizedClientProvider webProvider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();

ReactiveOAuth2AuthorizedClientProvider jobProvider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();
```

Lựa chọn này **không tự thay đổi registration**. Nếu registration khai báo `client_credentials`, provider chỉ hỗ trợ `authorization_code` có thể không authorize được. Ngược lại, nếu job dùng registration `authorization_code` nhưng không có user/browser, manager ngoài request **không tự dựng được bước redirect/consent**.

Đừng bật tất cả grant types chỉ để “khỏi lỗi”; mỗi flow có threat model riêng. `password` grant đã bị loại khỏi OAuth 2.1 và không nên chọn cho thiết kế mới. `client_credentials` có ý nghĩa service-to-service, `authorization_code` dùng cho user-interactive flows.

## 3. Manager thứ nhất: DefaultReactiveOAuth2AuthorizedClientManager

### 3.1. Dùng khi có ServerWebExchange

Class đầy đủ:

```java
org.springframework.security.oauth2.client.web
    .DefaultReactiveOAuth2AuthorizedClientManager
```

Constructor:

```java
new DefaultReactiveOAuth2AuthorizedClientManager(
    ReactiveClientRegistrationRepository clientRegistrations,
    ServerOAuth2AuthorizedClientRepository authorizedClients);
```

Javadoc của Spring Security xác định đây là manager dùng **trong ngữ cảnh `ServerWebExchange`**, vì nó có thể tải và lưu authorized client theo user/request/session bằng `ServerOAuth2AuthorizedClientRepository`.

Trường hợp phù hợp:

- User đang tương tác với ứng dụng WebFlux qua browser.
- OAuth2 Login/OIDC của một user đã tạo `Authentication`.
- Controller hoặc service đang xử lý request và cần downstream access token gắn với user.
- Authorization Code/OIDC và refresh token đã được cấu hình đúng.
- Authorization repository có thể lưu token gắn với user hoặc WebSession theo policy.

### 3.2. Đọc và lưu token ở đâu?

`ServerOAuth2AuthorizedClientRepository` là abstraction gắn với request:

```java
Mono<T> loadAuthorizedClient(
    String registrationId,
    Authentication principal,
    ServerWebExchange exchange);
```

Ngoài ra có `saveAuthorizedClient(...)` và `removeAuthorizedClient(...)`. Interface có generic type bound `T extends OAuth2AuthorizedClient`, nên snippet trên chỉ diễn tả shape, không phải interface tự khai báo đầy đủ.

Các implementation hay gặp:

- `WebSessionServerOAuth2AuthorizedClientRepository`: authorized clients gắn với `WebSession`, hữu ích khi luồng web chưa đăng nhập hoặc cần storage theo session.
- `AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository`: với principal đã xác thực, ủy quyền lưu qua `ReactiveOAuth2AuthorizedClientService`; với anonymous có thể fallback đến WebSession repository. **Đừng đoán rằng mọi web token chỉ được lưu trong session.**

`DefaultReactiveOAuth2AuthorizedClientManager` mặc định dùng authorization success/failure handlers để lưu hoặc xóa authorized client theo repository. Bạn có thể thay handlers nếu có yêu cầu storage/audit/TTL riêng, nhưng phải giữ consistency khi refresh/token invalid.

### 3.3. Có bắt buộc tự truyền exchange không?

Khi gọi manager **trực tiếp**, bạn nên cung cấp `ServerWebExchange` trong attributes:

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("reports-user")
        .principal(authentication)
        .attribute(ServerWebExchange.class.getName(), exchange)
        .build();

Mono<OAuth2AuthorizedClient> authorized =
    webAuthorizedClientManager.authorize(request);
```

Đây là snippet **đặt trong method có biến `authentication` và `exchange` thật**. Tên attribute là `ServerWebExchange.class.getName()`, API được Spring Security mô tả. Không tự dựng một exchange giả trong production để “làm hài lòng” manager; **nếu thực sự không có inbound web request, hãy chọn service manager**.

Nếu dùng `ServerOAuth2AuthorizedClientExchangeFilterFunction` của WebClient, có helper:

```java
.attributes(clientRegistrationId("reports-user"))
.attributes(serverWebExchange(exchange))
```

Hai helper cùng nằm trong `org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction`. Tùy đường gọi, framework có thể lấy exchange từ context phù hợp; truyền tường minh giúp dễ audit khi service nhận exchange từ controller.

### 3.4. User token phải gắn đúng user

Một lỗi bảo mật nghiêm trọng:

```java
// Sai: lưu một authorized client của Alice vào biến static dùng chung.
static OAuth2AuthorizedClient lastAuthorizedClient;
```

Nếu Bob gọi service sau Alice, việc lấy `lastAuthorizedClient` có thể gửi access token Alice sang API hoặc trả dữ liệu Alice cho Bob. Đúng là dùng repository/service **keyed by registrationId + principal**, hoặc truyền rõ authorized client của request hiện tại, không cache global bằng một khóa chung.

## 4. Manager thứ hai: AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager

### 4.1. Dùng ngoài ServerWebExchange

Class đầy đủ:

```java
org.springframework.security.oauth2.client
    .AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
```

Constructor:

```java
new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
    ReactiveClientRegistrationRepository clientRegistrations,
    ReactiveOAuth2AuthorizedClientService authorizedClientService);
```

Javadoc nêu rõ class này **có thể hoạt động ngoài ngữ cảnh `ServerWebExchange`**, ví dụ:

- `@Scheduled` task / job hẹn giờ.
- Queue consumer (Kafka, RabbitMQ, cloud task).
- Batch import/export hoặc command-line/worker job.
- Service-tier gọi một API khi **không có inbound HTTP request**.
- Background publisher được khởi tạo sau khi HTTP request đã kết thúc.
- B2B machine-to-machine `client_credentials` không cần user login.

Không có lý do buộc `ServerWebExchange` xuất hiện trong job; cũng không nên lấy web request cũ từ static/global/ThreadLocal rồi tái dùng.

### 4.2. Dùng ReactiveOAuth2AuthorizedClientService

`ReactiveOAuth2AuthorizedClientService` cung cấp:

```java
Mono<T> loadAuthorizedClient(
    String registrationId, String principalName);
Mono<Void> saveAuthorizedClient(OAuth2AuthorizedClient authorizedClient);
Mono<Void> removeAuthorizedClient(
    String registrationId, String principalName);
```

`loadAuthorizedClient` dùng generic bound `T extends OAuth2AuthorizedClient`; snippet chỉ mô tả các chữ ký quen thuộc.

Một implementation mặc định là `InMemoryReactiveOAuth2AuthorizedClientService`, không bền vững qua restart và **không tự đồng bộ nhiều replica**. Nếu tác vụ chạy nhiều instance hoặc cần giữ refresh tokens qua restart, cân nhắc database-backed implementation (ví dụ R2DBC) và policies về mã hóa secrets, đồng bộ gia hạn, xử lý token failures và isolation giữa các tenants.

**Không nhầm:**

```text
ReactiveClientRegistrationRepository:
    lưu CẤU HÌNH client_id, grant_type, endpoint, scopes.

ReactiveOAuth2AuthorizedClientService:
    lưu KẾT QUẢ authorize: access/refresh token + principal + registration.

ServerOAuth2AuthorizedClientRepository:
    thao tác authorized client trong bối cảnh request/web session/user.
```

### 4.3. Đặt principal ổn định cho batch job

Ngay cả `client_credentials` không có end-user, `OAuth2AuthorizeRequest` **vẫn cần principal** để manager xác định authorized client. Ví dụ:

```java
Authentication system =
    new UsernamePasswordAuthenticationToken(
        "reports-scheduler",
        "not-a-password",
        List.of(new SimpleGrantedAuthority("ROLE_SYSTEM")));

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("reports-batch")
        .principal(system)
        .build();

return jobAuthorizedClientManager.authorize(request);
```

`principal` ở đây là **cache/storage key của client_credentials authorization**, không phải user thật, không được dùng để bypass phân quyền resource server. Resource Server vẫn phải xác minh access token (issuer, signature/introspection, audience và scopes).

Nếu mỗi lần gọi job lại dùng principal ngẫu nhiên, service có thể lưu ra nhiều `OAuth2AuthorizedClient` cho cùng client registration, làm giảm cache hit và gây token churn. Nếu cố dùng một principal chung cho **nhiều tenant hoặc registration có quyền khác nhau**, có thể làm mờ boundary; chọn tên principal nhất quán theo service/tenant và giới hạn đăng ký.

## 5. Cây quyết định chọn manager

```text
Bắt đầu: code cần xin token để gọi downstream API
  |
  +-- Có inbound WebFlux ServerWebExchange hiện tại?
  |      |
  |      +-- CÓ: token gắn với người đang dùng website?
  |      |         |
  |      |         +-- CÓ:
  |      |         |   DefaultReactiveOAuth2AuthorizedClientManager
  |      |         |   + ServerOAuth2AuthorizedClientRepository
  |      |         |   + user principal / exchange
  |      |         |
  |      |         +-- KHÔNG, token của chính backend/client_credentials:
  |      |             Có thể tách riêng service manager
  |      |             để không phụ thuộc request/user session.
  |      |
  |      +-- KHÔNG (scheduler/queue/background):
  |                AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
  |                + ReactiveOAuth2AuthorizedClientService
  |                + service principal ổn định
  |
  +-- Grant type của ClientRegistration phù hợp provider?
  +-- Access token được cấp cho đúng API/scopes/tenant?
  +-- Store có isolation và chính sách refresh/failure rõ ràng?
```

**Nuance:** Khi HTTP request có mặt nhưng downstream call cố tình dùng token **client_credentials** của backend, một service manager vẫn có thể là lựa chọn tốt để tránh coupling theo user/WebSession. Điều cốt lõi không phải “có HTTP = bắt buộc web manager”, mà là **token và authorized-client lifecycle gắn với đâu**. Ngược lại, không chọn web manager trong job chỉ vì code dùng `WebClient`.

### 5.1. Bảng tình huống thực chiến

| Tình huống | Manager ưu tiên | Principal | Grant và lý do |
| --- | --- | --- | --- |
| Controller xử lý dashboard của Alice, gọi API thay mặt Alice | Web manager | Alice | Authorization Code/OIDC, refresh user token |
| User đã login, controller dùng `@RegisteredOAuth2AuthorizedClient` | Web repository/client manager theo framework | User hiện tại | Dùng authorized client của request |
| Web endpoint khởi tạo báo cáo hệ thống không liên quan quyền của user | Service manager | Service/tenant | Client credentials, tránh user token leak |
| `@Scheduled` gửi dữ liệu đêm | Service manager | `reports-scheduler` | Client credentials, không có exchange |
| Kafka consumer đồng bộ inventory | Service manager | `inventory-worker` | Client credentials/identity service |
| CLI/CommandLineRunner gọi API | Service manager | `cli-service` | Không có HTTP request |
| Service reactive được gọi từ controller nhưng lấy token của user | Web manager hoặc authorized client được truyền tường minh | User | Có ngữ cảnh request; tránh lấy token global |
| Async publisher thực thi sau request, không còn exchange | Service manager nếu dùng service identity; nếu cần user authorization phải thiết kế delegation/token storage riêng | Tùy use case | Không giả định Reactor Context web còn tồn tại |
| API Resource Server chỉ kiểm tra bearer inbound | Không cần OAuth2 Client manager | JWT principal inbound | Dùng `oauth2ResourceServer`, không tự xin token |
| Authorization Server phát access token cho clients | Không phải mục đích của hai manager này | AS identity | Dùng sản phẩm/config Authorization Server riêng |

## 6. Những lỗi dễ nhầm nhất

### 6.1. Chỉ dùng default ReactiveOAuth2AuthorizedClientManager bean

Spring Boot/Spring Security có thể tạo một `ReactiveOAuth2AuthorizedClientManager` mặc định nếu ứng dụng chưa định nghĩa. Nhưng **đừng giả định bean mặc định được tối ưu cho mọi context**. Khi dự án có cả WebFlux requests và jobs, nên xác định rõ manager type, principal và storage của mỗi use case. Nếu khai báo hai bean cùng interface, mọi injection cần `@Qualifier` hoặc tên bean rõ ràng, tránh ambiguous dependency.

### 6.2. WebClient không đồng nghĩa Web Manager

```java
WebClient client = WebClient.builder().build();
```

Object trên chỉ là HTTP client reactive. Nó **không chứa `ServerWebExchange`**. Trong scheduler, `WebClient` chạy tốt nhưng dùng `DefaultReactiveOAuth2AuthorizedClientManager` có thể thất bại vì thiếu request exchange/repository context. Trong controller, `WebClient` có thể dùng web manager để lấy token user. **Nơi thực thi** và **principal được ủy quyền** mới quyết định manager.

### 6.3. Không có Authentication trong scheduler

`ReactiveSecurityContextHolder.getContext()` có thể trả `Mono.empty()` trong scheduler vì không có HTTP login. Không tự tạo một “fake Alice authentication” rồi gắn vào job để tái sử dụng user token. Đối với service-to-service, dùng `client_credentials` và principal hệ thống rõ ràng. Nếu business yêu cầu làm việc *thay mặt Alice*, cần cơ chế delegation/on-behalf-of được AS cho phép và data protection tương ứng; không “lấy token Alice mới nhất” từ cache.

### 6.4. Viết code imperative chặn reactive pipeline

```java
// Sai trong WebFlux event loop:
OAuth2AuthorizedClient c = manager.authorize(request).block();

// Sai nếu subscription không được quản lý:
manager.authorize(request).subscribe(client -> callSomething(client));
```

Trong method reactive, hãy **return** `Mono` hoặc compose bằng `flatMap`:

```java
return manager.authorize(request)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("No authorized client")))
    .flatMap(client -> downstreamCall(client));
```

Không log token. Với scheduled jobs, việc bắt đầu subscription ở ranh giới task runner phải có quản lý lifecycle, retry, timeout, cancellation và giám sát; không bắn `.subscribe()` rời rạc trong service business rồi mất tín hiệu lỗi. Nếu scheduler API là imperative, có thể dùng một adapter được thiết kế rõ, chạy trên scheduler thích hợp và **không block Netty event-loop**; không áp `.block()` tùy tiện.

## 7. Luồng web và luồng job khác nhau ở đâu?

### 7.1. Web user flow

```text
Browser Alice
   |
   v
GET /web/report
   |
   v
Spring Security WebFlux: Authentication(Alice) + ServerWebExchange
   |
   v
DefaultReactiveOAuth2AuthorizedClientManager
   |   + registrationId = reports-user
   |   + principal = Alice
   |   + exchange = request hiện tại
   |
   v
ServerOAuth2AuthorizedClientRepository
   |   + tìm token Alice đã có
   |   + refresh khi cần và được phép
   |
   v
OAuth2AuthorizedClient(Alice)
   |
   v
WebClient -> Authorization: Bearer ALICE_ACCESS_TOKEN -> API
```

Dùng provider hỗ trợ authorization code và refresh token khi đã có authorization trước đó. Nếu chưa login/consent/ủy quyền, web request cần khởi tạo **Authorization Code redirect** (thường do `oauth2Login`/framework hỗ trợ); không thể tự tạo access token “Alice” chỉ từ username.

### 7.2. Scheduler/service flow

```text
@Scheduled / queue consumer / batch job
   |
   v
Không có ServerWebExchange
   |
   v
AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
   |   + registrationId = reports-batch
   |   + principal = reports-scheduler
   |
   v
ReactiveOAuth2AuthorizedClientService
   |   + tìm access token service còn hạn
   |   + client_credentials khi token thiếu/hết hạn
   |
   v
OAuth2AuthorizedClient(reports-scheduler)
   |
   v
WebClient -> Authorization: Bearer SERVICE_ACCESS_TOKEN -> API
```

Thông thường **client_credentials không phát refresh token**; khi access token hết hạn, client dùng chính grant này để **xin access token mới** từ Token Endpoint. Không cấu hình `refreshToken()` chỉ vì muốn token của job tự đổi; provider `clientCredentials()` đã phụ trách re-authorize theo policy của framework.

### 7.3. Không gọi authorize lại vô ích ở mọi bước

Manager có thể quản lý token cache/refresh thông qua store. Không nên gọi authorization endpoint thủ công cho từng request bằng cách tự POST `grant_type=client_credentials`. Dùng manager và service được inject để giữ vòng đời token nhất quán, đồng thời tránh nhiều workers đồng loạt gọi token endpoint. Với workload rất lớn/multi-node, cần kiểm soát concurrency, rate limit, retry và shared-storage phù hợp.

## 8. Hai WebClient và cách chọn clientRegistrationId

Một `WebClient` có thể tích hợp `ServerOAuth2AuthorizedClientExchangeFilterFunction`:

```java
@Bean("userWebClient")
WebClient userWebClient(
        @Qualifier("webManager")
        ReactiveOAuth2AuthorizedClientManager webManager) {
    var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
        webManager);
    return WebClient.builder().filter(oauth2).build();
}

@Bean("batchWebClient")
WebClient batchWebClient(
        @Qualifier("jobManager")
        ReactiveOAuth2AuthorizedClientManager jobManager) {
    var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
        jobManager);
    return WebClient.builder().filter(oauth2).build();
}
```

Đây là snippets của một `@Configuration`, bản đầy đủ có imports ở mục 11.

Trong request web:

```java
return userWebClient.get()
    .uri("https://api.example.invalid/user/report")
    .attributes(clientRegistrationId("reports-user"))
    .attributes(serverWebExchange(exchange))
    .retrieve()
    .bodyToMono(String.class);
```

Trong job với service principal **không cần exchange**:

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("reports-batch")
        .principal(systemAuthentication)
        .build();

return jobManager.authorize(request)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("No service authorized client")))
    .flatMap(authorized ->
        batchWebClient.get()
            .uri("https://api.example.invalid/system/report")
            .attributes(oauth2AuthorizedClient(authorized))
            .retrieve()
            .bodyToMono(String.class));
```

Ở code thứ hai, `oauth2AuthorizedClient(authorized)` được dùng tường minh để tránh WebClient vô tình chọn user từ Reactor Context hoặc thiếu principal. Nếu filter có cơ chế tái kiểm tra/re-authorize khi token hết hạn, cần xem Javadoc đúng version.

**Quan trọng về bảo mật:** `setDefaultOAuth2AuthorizedClient(true)` hoặc `setDefaultClientRegistrationId(...)` có thể gắn Bearer token lên **mọi request** được gửi qua WebClient đó. Không bật mặc định trên WebClient chung có thể gọi host bất kỳ, redirect tùy ý hoặc URL từ client input. Dùng WebClient riêng theo downstream origin đáng tin, truyền `clientRegistrationId`/authorized client **tường minh**, giới hạn host allowlist và tránh access-token exfiltration.

### 8.1. Hai constructor WebClient filter không hoàn toàn giống nhau

`ServerOAuth2AuthorizedClientExchangeFilterFunction` có hai constructor thường gặp:

```java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    ReactiveOAuth2AuthorizedClientManager manager);
```

và:

```java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    ReactiveClientRegistrationRepository registrations,
    ServerOAuth2AuthorizedClientRepository repository);
```

Theo Javadoc Spring Security 6.5, constructor nhận `registrations + repository` có thể tự cấu hình `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` để xử lý một số downstream 401/403 theo OAuth2 error code; constructor nhận **manager** không mặc định gắn failure handler này vào filter. Khi dùng custom manager, cần cân nhắc cấu hình `setAuthorizationFailureHandler(...)` với đúng repository/service backend. Không coi **mọi 403** là dấu hiệu token invalid — 403 có thể đơn thuần là thiếu scope/permission, không nên thu hồi token vô điều kiện.

Phân biệt hai lớp lỗi:

- **Authorization failure khi xin/refresh token** từ AS (ví dụ `invalid_grant`) được manager/provider và handler tương ứng xử lý.
- **401/403 từ downstream Resource Server** xảy ra trong request WebClient; failure handler của filter mới có thể dựa vào Bearer challenge/error để xóa cached authorized client nếu phù hợp.

Không retry vô hạn khi refresh/permission 403, tránh request storm và rò dữ liệu lỗi.

## 9. Storage, scope và principal: mô hình so sánh

| Khía cạnh | Web manager | Service manager |
| --- | --- | --- |
| Tên class | `DefaultReactiveOAuth2AuthorizedClientManager` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| Interface | `ReactiveOAuth2AuthorizedClientManager` | Cùng interface |
| Context | `ServerWebExchange`, principal từ request | Không cần request, principal hệ thống |
| Store | `ServerOAuth2AuthorizedClientRepository` | `ReactiveOAuth2AuthorizedClientService` |
| Thí dụ principal | `alice`, `bob` | `reports-scheduler`, `inventory-worker` |
| Thí dụ grant | `authorization_code`, `refresh_token` | `client_credentials` |
| Session | Có thể sử dụng WebSession hoặc storage theo user | Không cần WebSession |
| Typical use | BFF/website gọi API thay mặt user | M2M, scheduler, batch |
| Quyền truy cập | Phụ thuộc user, scopes của client/token | Quyền service client được AS cấp |
| Lỗi phổ biến | Không truyền exchange, lộ token giữa users | Kỳ vọng `ReactiveSecurityContextHolder` có user |
| Scale | Token persistence theo request/principal/session | Service storage phù hợp multi-node |

**Sự thật tinh tế:** `AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository` có thể delegate tới **chính `ReactiveOAuth2AuthorizedClientService`**. Vì vậy “web manager = luôn lưu session” là **quá đơn giản và có thể sai**. Sự khác biệt ở API repository/context, không phải mặc định vật lý storage lúc nào cũng tách biệt.

### 9.1. Principal name tham gia khóa token

Cùng một `registrationId` nhưng hai principal khác nhau được xem là hai authorized clients riêng:

```text
(reports-user, alice)  -> Alice's authorized client
(reports-user, bob)    -> Bob's authorized client
(reports-batch, reports-scheduler) -> service authorized client
```

Đừng dùng `"system"` để tái biểu diễn tất cả tenants nếu downstream authorization phụ thuộc tenant; hãy thiết kế client registrations/scopes và principal naming có isolation. Khi cần audit, ghi registration ID, opaque principal identifier và status, nhưng **không log access token hay refresh token**.

### 9.2. Expiration không tự bảo đảm downstream cấp quyền

`OAuth2AuthorizedClient` có access token còn hạn, nhưng Resource Server vẫn có thể trả 401 (revoked, audience/issuer sai) hoặc 403 (thiếu scope). Manager chỉ giải quyết vòng đời **client authorization/token**; downstream vẫn tự xác minh token. Không dùng `OAuth2AuthorizedClient.getAccessToken().getExpiresAt()` như bằng chứng người dùng được phép đọc tài nguyên.

## 10. Một project Java 17+ với hai manager độc lập

Project sau **chạy được tại máy có Java 17+/Maven** để khảo sát wiring, token persistence và sự khác nhau giữa manager. Nó **không giả vờ có Authorization Server thật**: ClientRegistration dùng các endpoint `.invalid` theo chuẩn reserved domains. Các bài test seed **OAuth2AuthorizedClient còn hiệu lực** vào store để kiểm tra lựa chọn manager mà **không gọi token endpoint mạng**. Muốn kiểm thử grant mới, refresh, PKCE và downstream thật, thay endpoint/credentials bằng IdP sandbox và thêm integration tests tương ứng.

### 10.1. Cây thư mục

```text
reactive-oauth2-manager-choice/
├── pom.xml
└── src/
    ├── main/java/demo/manager/
    │   ├── Application.java
    │   ├── ManagerConfiguration.java
    │   ├── BrowserReportController.java
    │   └── BatchReportService.java
    └── test/java/demo/manager/
        └── ManagerSelectionTests.java
```

### 10.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-oauth2-manager-choice</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Ví dụ dùng Spring Boot **3.5.16** như một baseline đã phát hành với Spring Security **6.5.x**. Nhánh cũ có thể đã hết OSS support vào năm 2026, vì vậy production mới phải chọn nhánh đang được hỗ trợ và thử API theo migration guide. Không pin riêng version `spring-security-oauth2-client` khi Boot dependency management đã quản lý.

### 10.3. src/main/java/demo/manager/Application.java

```java
package demo.manager;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 10.4. src/main/java/demo/manager/ManagerConfiguration.java

```java
package demo.manager;

import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.reactive.function.client.WebClient;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class ManagerConfiguration {

    @Bean
    ReactiveClientRegistrationRepository registrations() {
        // Giá trị công khai dành riêng cho ví dụ, không phải IdP thật.
        ClientRegistration browser = ClientRegistration
            .withRegistrationId("reports-user")
            .clientId("local-browser-client")
            .clientSecret("local-demo-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .authorizationUri(
                "https://identity.example.invalid/oauth2/authorize")
            .tokenUri("https://identity.example.invalid/oauth2/token")
            .userInfoUri("https://identity.example.invalid/userinfo")
            .userNameAttributeName("sub")
            .scope("profile", "reports.read")
            .build();

        ClientRegistration batch = ClientRegistration
            .withRegistrationId("reports-batch")
            .clientId("local-service-client")
            .clientSecret("local-demo-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.CLIENT_CREDENTIALS)
            .tokenUri("https://identity.example.invalid/oauth2/token")
            .scope("reports.read")
            .build();

        return new InMemoryReactiveClientRegistrationRepository(
            browser, batch);
    }

    @Bean
    ReactiveOAuth2AuthorizedClientService authorizedClientService(
            ReactiveClientRegistrationRepository registrations) {
        return new InMemoryReactiveOAuth2AuthorizedClientService(
            registrations);
    }

    @Bean
    ServerOAuth2AuthorizedClientRepository webAuthorizedClientRepository(
            ReactiveOAuth2AuthorizedClientService service) {
        return new AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository(
            service);
    }

    @Bean("webManager")
    ReactiveOAuth2AuthorizedClientManager webManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository repository) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        var manager = new DefaultReactiveOAuth2AuthorizedClientManager(
            registrations, repository);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean("jobManager")
    ReactiveOAuth2AuthorizedClientManager jobManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService service) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, service);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean("userWebClient")
    WebClient userWebClient(
            @Qualifier("webManager")
            ReactiveOAuth2AuthorizedClientManager manager) {
        var oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);
        // Không bật default token cho mọi host.
        return WebClient.builder().filter(oauth2).build();
    }

    @Bean("batchWebClient")
    WebClient batchWebClient(
            @Qualifier("jobManager")
            ReactiveOAuth2AuthorizedClientManager manager) {
        var oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);
        return WebClient.builder().filter(oauth2).build();
    }

    @Bean
    SecurityWebFilterChain webSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/public").permitAll()
                .pathMatchers("/web/**").authenticated()
                .anyExchange().denyAll())
            .oauth2Login(withDefaults())
            .oauth2Client(withDefaults())
            .build();
    }
}
```

**Giải thích cấu hình:**

- `registrations()` tạo **hai client registrations khác grant types**, không tạo token ngay.
- `authorizedClientService()` là store in-memory dùng cho demo, thay bằng persistent service an toàn khi production cần HA/restart.
- `webAuthorizedClientRepository()` kết nối với service cho authenticated principals, fallback session cho anonymous theo default implementation.
- `webManager` chọn provider `authorizationCode().refreshToken()`, lưu qua **Server repository**, dùng khi request có exchange.
- `jobManager` chọn provider `clientCredentials()`, lưu qua **Reactive authorized client service**, không yêu cầu exchange.
- Hai `WebClient` được phân biệt tên/qualifier. Điều này giúp code dùng đúng token source và dễ auditing.
- Web security bật `oauth2Login` và `oauth2Client` để minh họa user flow; endpoint ngoài `/public` yêu cầu login. **Không** disable CSRF mặc định để sửa lỗi vô cớ.
- Domain `example.invalid` là host cố ý không tồn tại, vì vậy **chưa thể thực hiện OAuth2 authorization/token exchange thật**. Các test ở mục 11 dùng authorized clients đã seed với token còn hạn nên không gọi host này.

**Bảo mật:** `local-demo-secret` là literal chỉ cho ví dụ. Ứng dụng thật lấy client secret từ secret manager/environment và dùng HTTPS. Không in secrets/token trên HTTP response/log. Nếu IdP hỗ trợ PKCE, state, nonce hoặc issuer metadata, hãy dùng cấu hình login đầy đủ phù hợp provider; không giả định registration không có `openid` sẽ là OIDC Login.

### 10.5. src/main/java/demo/manager/BrowserReportController.java

```java
package demo.manager;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.web.server.context.ServerSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.serverWebExchange;

@RestController
public class BrowserReportController {

    private final ReactiveOAuth2AuthorizedClientManager manager;
    private final WebClient webClient;

    public BrowserReportController(
            @Qualifier("webManager")
            ReactiveOAuth2AuthorizedClientManager manager,
            @Qualifier("userWebClient") WebClient webClient) {
        this.manager = manager;
        this.webClient = webClient;
    }

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("manager choice OK");
    }

    @GetMapping("/web/report")
    public Mono<String> report(ServerWebExchange exchange) {
        return exchange.getPrincipal()
            .cast(Authentication.class)
            .flatMap(principal -> {
                OAuth2AuthorizeRequest request =
                    OAuth2AuthorizeRequest
                        .withClientRegistrationId("reports-user")
                        .principal(principal)
                        .attribute(
                            ServerWebExchange.class.getName(), exchange)
                        .build();

                return manager.authorize(request)
                    .switchIfEmpty(Mono.error(
                        new IllegalStateException(
                            "User has not authorized this client")))
                    .flatMap(client -> webClient.get()
                        .uri("https://api.example.invalid/user/report")
                        .attributes(oauth2AuthorizedClient(client))
                        .attributes(serverWebExchange(exchange))
                        .retrieve()
                        .bodyToMono(String.class));
            });
    }
}
```

`/web/report` thể hiện **đúng chỗ cần `ServerWebExchange`**, không tự chọn principal ngẫu nhiên. Nếu browser user chưa hoàn tất OAuth2 Login/authorization, manager không thể lấy token hợp lệ cho client. Vì endpoint IdP/downstream đều là ví dụ không tồn tại, **GET /web/report không dùng để thử thành công end-to-end khi giữ nguyên sample config**; integration tests bên dưới trực tiếp test manager với fixture đã lưu.

Trong hệ thống thực, service chỉ nên truy cập **downstream URL đáng tin** và phải kiểm tra access token được cấp cho đúng API audience/scopes. Controller không trả token vào body; nó chỉ trả dữ liệu API. Method protected bằng `.authenticated()` không tự bảo đảm user có `reports.read`; downstream Resource Server vẫn cần kiểm tra quyền theo access token.

### 10.6. src/main/java/demo/manager/BatchReportService.java

```java
package demo.manager;

import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@Service
public class BatchReportService {

    private final ReactiveOAuth2AuthorizedClientManager manager;
    private final WebClient webClient;

    public BatchReportService(
            @Qualifier("jobManager")
            ReactiveOAuth2AuthorizedClientManager manager,
            @Qualifier("batchWebClient") WebClient webClient) {
        this.manager = manager;
        this.webClient = webClient;
    }

    private Authentication systemPrincipal() {
        // Chỉ là khóa ổn định cho authorized-client store;
        // không phải người dùng vừa login.
        return new UsernamePasswordAuthenticationToken(
            "reports-scheduler",
            "not-a-password",
            List.of(new SimpleGrantedAuthority("ROLE_SYSTEM")));
    }

    private OAuth2AuthorizeRequest request() {
        return OAuth2AuthorizeRequest
            .withClientRegistrationId("reports-batch")
            .principal(systemPrincipal())
            .build();
    }

    // Có ích cho test wiring; không trả access token ra ngoài.
    public Mono<String> describeAuthorizedClient() {
        return manager.authorize(request())
            .switchIfEmpty(Mono.error(
                new IllegalStateException("No system authorized client")))
            .map(client -> "registration="
                + client.getClientRegistration().getRegistrationId()
                + ";principal=" + client.getPrincipalName());
    }

    // Để scheduler/queue runner quyết định khi nào subscribe.
    public Mono<String> fetchReport() {
        return manager.authorize(request())
            .switchIfEmpty(Mono.error(
                new IllegalStateException("No system authorized client")))
            .flatMap(client -> webClient.get()
                .uri("https://api.example.invalid/system/report")
                .attributes(oauth2AuthorizedClient(client))
                .retrieve()
                .bodyToMono(String.class));
    }
}
```

**Đọc thật kỹ:** `systemPrincipal()` là Authentication nhân tạo chỉ để manager đặt **principalName** nhất quán cho service token. Nó **không được đưa vào `ReactiveSecurityContextHolder` của người dùng** và **không cấp quyền cho Resource Server**. Quyền của Batch API phụ thuộc chính access token mà Authorization Server cấp theo `client_credentials`.

`fetchReport()` trả `Mono<String>`, không gọi `block()` hay `subscribe()` trong tầng business. Một scheduler thực phải điều phối subscription, metrics, timeout, retry và giới hạn đồng thời. Đừng dùng `@Scheduled` để bắn hàng trăm subscriptions không được quản lý, vì việc xin token/HTTP call bất đồng bộ có thể tràn tải hoặc tạo duplicate runs.

**Chú ý phân biệt:** `java.util.List` ở đây chỉ dùng để xây Authorities cho `Authentication`. Nếu `client_credentials` cần token theo tenant, nên định nghĩa principals/registrations riêng theo tenant, không cho phép user HTTP tự điều chỉnh service principal nhằm lấy token tenant khác.

## 11. Unit/integration tests thực hành lựa chọn manager, không dùng IdP thật

Test có mục tiêu **kiểm tra class manager, storage key và khả năng authorize lại từ token hợp lệ**. Một access token fixture được **seed** vào repository/service. Vì token còn hạn nên manager có thể tải lại mà **không gọi mạng IdP**. Đây không phải test grant exchange, refresh, chữ ký JWT, khả năng đăng nhập OIDC, hoặc downstream resource server.

### 11.1. src/test/java/demo/manager/ManagerSelectionTests.java

```java
package demo.manager;

import java.time.Instant;
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class ManagerSelectionTests {

    @Autowired @Qualifier("webManager")
    ReactiveOAuth2AuthorizedClientManager webManager;

    @Autowired @Qualifier("jobManager")
    ReactiveOAuth2AuthorizedClientManager jobManager;

    @Autowired
    ReactiveClientRegistrationRepository registrations;

    @Autowired
    ReactiveOAuth2AuthorizedClientService service;

    @Autowired
    ServerOAuth2AuthorizedClientRepository webRepository;

    @Autowired
    BatchReportService batchReportService;

    @Autowired @Qualifier("userWebClient")
    WebClient userWebClient;

    @Autowired @Qualifier("batchWebClient")
    WebClient batchWebClient;

    private static Authentication user(String name) {
        return new TestingAuthenticationToken(
            name, "unused", "ROLE_USER");
    }

    private static OAuth2AuthorizedClient issued(
            ClientRegistration registration, String principalName) {
        Instant now = Instant.now();
        OAuth2AccessToken token = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "test-access-token-for-" + principalName,
            now.minusSeconds(60),
            now.plusSeconds(3600),
            Set.of("reports.read"));
        return new OAuth2AuthorizedClient(
            registration, principalName, token);
    }

    private static ServerWebExchange exchange() {
        return MockServerWebExchange.from(
            MockServerHttpRequest.get("/web/report").build());
    }

    @Test
    void requestManagerHasWebExchangeImplementation() {
        assertInstanceOf(
            DefaultReactiveOAuth2AuthorizedClientManager.class,
            webManager);
    }

    @Test
    void taskManagerHasServiceImplementation() {
        assertInstanceOf(
            AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager.class,
            jobManager);
    }

    @Test
    void registrationsHaveDifferentGrants() {
        Mono<String> names = Mono.zip(
                registrations.findByRegistrationId("reports-user"),
                registrations.findByRegistrationId("reports-batch"))
            .map(tuple -> tuple.getT1().getAuthorizationGrantType()
                .getValue() + "|" + tuple.getT2()
                    .getAuthorizationGrantType().getValue());

        StepVerifier.create(names)
            .expectNext("authorization_code|client_credentials")
            .verifyComplete();
    }

    @Test
    void webRepositoryStoresAnAuthorizedClientForAlice() {
        Authentication alice = user("alice");
        ServerWebExchange requestExchange = exchange();

        Mono<String> loaded =
            registrations.findByRegistrationId("reports-user")
                .flatMap(reg -> {
                    OAuth2AuthorizedClient seeded = issued(reg, "alice");
                    return webRepository.saveAuthorizedClient(
                            seeded, alice, requestExchange)
                        .then(webRepository.loadAuthorizedClient(
                            "reports-user", alice, requestExchange))
                        .map(client -> client.getPrincipalName());
                });

        StepVerifier.create(loaded)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void webManagerLoadsExistingUserClientWithExchange() {
        Authentication alice = user("alice");
        ServerWebExchange requestExchange = exchange();

        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reports-user")
                .principal(alice)
                .attribute(
                    ServerWebExchange.class.getName(), requestExchange)
                .build();

        Mono<String> authorized =
            registrations.findByRegistrationId("reports-user")
                .flatMap(reg -> {
                    OAuth2AuthorizedClient seeded = issued(reg, "alice");
                    return webRepository.saveAuthorizedClient(
                            seeded, alice, requestExchange)
                        .then(webManager.authorize(request))
                        .map(client -> client.getPrincipalName());
                });

        StepVerifier.create(authorized)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void jobManagerLoadsExistingClientWithoutExchange() {
        Authentication system = user("reports-scheduler");

        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reports-batch")
                .principal(system)
                .build(); // KHÔNG có ServerWebExchange.

        Mono<String> authorized =
            registrations.findByRegistrationId("reports-batch")
                .flatMap(reg -> {
                    OAuth2AuthorizedClient seeded =
                        issued(reg, "reports-scheduler");
                    return service.saveAuthorizedClient(seeded)
                        .then(jobManager.authorize(request))
                        .map(client -> client.getPrincipalName());
                });

        StepVerifier.create(authorized)
            .expectNext("reports-scheduler")
            .verifyComplete();
    }

    @Test
    void serviceStoreDoesNotLeakTokenToAnotherPrincipal() {
        Mono<String> result =
            registrations.findByRegistrationId("reports-batch")
                .flatMap(reg -> {
                    OAuth2AuthorizedClient seeded =
                        issued(reg, "tenant-a-worker");
                    return service.saveAuthorizedClient(seeded)
                        .then(service.loadAuthorizedClient(
                            "reports-batch", "tenant-b-worker"))
                        .map(client -> client.getPrincipalName());
                });

        StepVerifier.create(result)
            .verifyComplete(); // Mono.empty(): khác principal.
    }

    @Test
    void batchServiceUsesStableServicePrincipalForCacheKey() {
        Mono<String> description =
            registrations.findByRegistrationId("reports-batch")
                .flatMap(reg ->
                    service.saveAuthorizedClient(
                        issued(reg, "reports-scheduler"))
                    .then(batchReportService.describeAuthorizedClient()));

        StepVerifier.create(description)
            .expectNext(
                "registration=reports-batch;principal=reports-scheduler")
            .verifyComplete();
    }

    @Test
    void bothWebClientsAreWiredExplicitly() {
        assertNotNull(userWebClient);
        assertNotNull(batchWebClient);
    }
}
```

Bộ test có **9 methods `@Test`**. Nó kiểm tra:

1. Manager cho request là đúng `DefaultReactiveOAuth2AuthorizedClientManager`.
2. Manager cho task là đúng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.
3. Hai registration có grant types khác nhau.
4. Web repository có thể save/load authorized client cho Alice.
5. Web manager tải client của Alice khi có `ServerWebExchange`.
6. Service manager tải client của scheduler **mà không cần exchange**.
7. Store theo principal không đưa token của worker tenant A cho worker tenant B.
8. `BatchReportService` dùng đúng principal name ổn định.
9. Hai WebClient được inject rõ ràng theo bean name.

**Giới hạn kiểm thử:** `test-access-token-for-...` chỉ là fixture trong RAM và **không gửi ra network**. `manager.authorize` ở các bài test được cấp token còn hiệu lực, do đó **không hề chứng minh** cấu hình token endpoint/PKCE/refresh thực sự thành công. Để test việc xin token mới, cần test Authorization Server (mock HTTP/token endpoint) hoặc IdP sandbox phù hợp; tuyệt đối không tự nói các test đã xác minh JWT signature.

### 11.2. Một test không nên viết

```java
// Anti-pattern: không có exchange nhưng ép chọn web manager.
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-user")
        .principal(user("reports-scheduler"))
        .build();
return webManager.authorize(request);
```

Lời gọi trên không mang `ServerWebExchange`, trái với contract sử dụng manager cho web context. Tùy phiên bản/đường code nó có thể không resolve repository hoặc dẫn tới lỗi ngữ cảnh; đừng dựa vào một exception cụ thể nếu không có test cho đúng version. **Cách sửa là đổi manager, không tạo một fake web request để lấy token của scheduler**.

## 12. Chạy Maven và quan sát kết quả

Trong thư mục chứa `pom.xml`:

```bash
java -version
mvn -version
mvn clean test
```

Với cấu hình/fixture như trên, **kỳ vọng** có 9 tests và Maven Surefire báo `Tests run: 9, Failures: 0, Errors: 0`, `BUILD SUCCESS` khi môi trường dependencies/test tương thích. Đây là **kỳ vọng theo mã**, không phải khẳng định Maven đã được chạy trong môi trường biên soạn bài.

Chạy server:

```bash
mvn spring-boot:run
```

Thử endpoint public:

```bash
curl -i http://localhost:8080/public
```

Dự kiến:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

manager choice OK
```

`/web/report` là endpoint được bảo vệ bằng OAuth2 login; bạn sẽ không nhận được report thực nếu `identity.example.invalid` và `api.example.invalid` chưa được thay bằng một IdP/API sandbox được cấu hình đúng. Đây là **chủ ý của ví dụ**: compile/test wiring không đòi secrets thật; việc chạy OAuth2 redirect/token exchange/downstream end-to-end là một bước integration riêng.

Không gọi `batchReportService.fetchReport().block()` ở controller/event loop; một job runner thật cần orchestration riêng để subscribe với timeout, retry, backoff, error reporting và cancellation. Nếu muốn cron thật, hãy cấu hình scheduling theo chính sách vận hành, không dùng `@Scheduled` + `subscribe()` vô quản lý.

### 12.1. Khi muốn test xin token mới bằng IdP sandbox

Bổ sung một test server/Authorization Server giả lập các phản hồi token endpoint (không cần lên mạng thật), với các trường hợp:

- Chưa có authorized client ⇒ service manager gọi `client_credentials`.
- AS trả `access_token`, `token_type=Bearer`, `expires_in` ⇒ lưu client trong service.
- Lần hai token còn hạn ⇒ dùng lại không gọi token endpoint mới.
- Token cũ hết hạn ⇒ re-authorize, nhận token khác và cập nhật store.
- AS trả `invalid_client` hoặc 5xx ⇒ propagate failure; retry giới hạn.
- Hai principal khác nhau ⇒ tách storage key, không dùng token của nhau.
- Web manager có exchange + user đã ủy quyền ⇒ refresh theo token/registration.
- Web manager mất exchange ⇒ fail đúng và được chuyển sang phù hợp service-manager design.
- Downstream 401 `invalid_token` ⇒ áp failure handler phù hợp, không loop vô hạn.
- Downstream 403 `insufficient_scope` ⇒ sửa scopes/AS policy, không xoá token tùy tiện.

Điều này là **bộ test đề xuất**, chưa có code mock AS trong project. Dùng WireMock hoặc Reactor Netty embedded server có mock token endpoint, nhưng phải bảo đảm TLS/issuer/config/trust policy đúng khi đem logic lên production.

## 13. Cách debug lỗi manager và authorized client

| Hiện tượng | Khả năng nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `ServerWebExchange` null trong scheduler | Dùng web manager ngoài request | Đổi sang service manager |
| Controller có exchange nhưng manager không tải token | Sai principal, registration ID hoặc store; chưa ủy quyền | Log metadata an toàn, kiểm tra OAuth2 Login/callback |
| Background job tìm `ReactiveSecurityContextHolder` empty | Không có browser/user security context | Dùng service principal ổn định, `client_credentials` |
| `authorize()` trả `Mono.empty()` | Provider không hỗ trợ grant/authorization không thể thực hiện | Kiểm tra registration và provider builder |
| `invalid_client` | Client ID/secret/auth method sai | Đối chiếu client registration của AS; secrets manager |
| `invalid_grant` | Code/refresh token invalid hoặc đã dùng/hết hạn | State/PKCE/callback/refresh policy, xóa client cũ khi phù hợp |
| `401` từ downstream | Token thiếu/hết hạn/revoked/sai audience/issuer | Check Bearer challenge và token validation, không log token |
| `403` từ downstream | Valid token nhưng thiếu scope/quyền/tenant | Xem authorities/claims, đổi policy/consent khi cần |
| Job liên tục xin token mới | Cache key principal thay đổi, token bị xóa hoặc store không share | Dùng principal ổn định, store bền, concurrency control |
| Token của user khác được gửi đi | Cache global/static hoặc WebClient default token không đúng | Cô lập principal, explicit authorized client |
| Scheduler bị `block()` gây treo | Blocking sai scheduler/event loop | Reactive composition, orchestrator đúng |
| Hai manager bean injection ambiguous | Không có `@Qualifier` | Tên `webManager` và `jobManager` rõ |
| 403 nhưng filter xóa token liên tục | Failure handler xử lý mọi 403 như invalid token | Dựa vào error code, kiểm tra scope |
| Có token nhưng API vẫn 401 | Token không dành cho audience API | Xác minh `aud`, issuer, signature, token type |
| Sau restart job lại xin token | Store in-memory reset | Dùng persistent/shared store khi cần |
| Multi-tenant token chéo nhau | Principal/store keys không phân vùng | Cô lập theo tenant/registration, test negative |
| Scheduled job có `client_credentials` nhưng không có refresh_token | Đây là hành vi phổ biến của grant | Reauthorize bằng client credentials |
| Web manager tạo redirect ở background | Auth code cần browser | Dùng M2M grant hoặc delegation protocol chuẩn |

### 13.1. Quy trình điều tra có thứ tự

1. Xác định request đang chạy trong **server web request** hay **job ngoài request**.
2. Xem manager class được inject; nếu có hai bean, kiểm tra `@Qualifier`.
3. Xác nhận `ClientRegistration.authorizationGrantType` và provider chain.
4. Xác định principal thực tế, registration ID và nơi authorized client được lưu.
5. Với web manager, xác nhận exchange hiện tại và user authentication thuộc đúng request.
6. Với service manager, xác nhận system principal key ổn định và có phân vùng tenant.
7. Xem token còn hạn và có refresh token không; không in token ra log.
8. Phân biệt lỗi AS trong quá trình authorize với 401/403 của Resource Server.
9. Nếu nhiều nodes, kiểm tra persistence/refresh concurrency, clock skew, retry và throttling.
10. Thêm integration test cho token endpoint thực/sandbox khi seed-test đã pass.

## 14. Bảo mật khi triển khai production

**Không truyền user access token vào background job** nếu user đã logout hoặc request kết thúc, trừ khi kiến trúc delegation được AS và policy cho phép. Việc giữ một `OAuth2AuthorizedClient` của user lâu hơn cần authorization, consent, refresh, storage encryption, logout/revocation và auditing rõ ràng.

**Không chia sẻ một `WebClient` có default token cho mọi URL**. Khi framework gắn Bearer token tự động, một endpoint attacker kiểm soát hoặc redirect không được kiểm soát có thể nhận token. Tách WebClient cho từng downstream host đáng tin, đặt allowlist, không log Authorization headers.

**Không lấy scope từ user input rồi tin tưởng**. Trong client credentials, scopes được xin theo registration/AS grant; Resource Server vẫn phải quyết định có cho dùng API resource. Một tài khoản service có scope rộng là một mối nguy lớn nếu token lộ, nên cấp privilege tối thiểu, giới hạn TTL, rotate secrets, mTLS/private_key_jwt nếu phù hợp.

**Không assume refresh token cho client credentials.** Hầu hết M2M dùng short-lived access tokens và xin mới khi cần. Với user code flow, refresh token (nếu được cấp) phải được bảo vệ; lưu tập trung có kiểm soát và xử lý `invalid_grant` đúng.

**Không dùng in-memory store thay production HA** khi cần persistent authorization/refresh tokens qua restart. `InMemoryReactiveOAuth2AuthorizedClientService` chỉ thích hợp demo, test hoặc use case thực sự không cần persistence. Với shared store, thiết kế encryption-at-rest, access control, key separation và TTL.

**Không nhầm Authentication giả để đặt cache key với người dùng thật.** `new UsernamePasswordAuthenticationToken("reports-scheduler", ...)` trong bài chỉ là object để service manager có principal. Nó không xác thực người dùng và không được đưa vào web security context. Resource Server sẽ validate token service do AS cấp.

### 14.1. CSRF và session vẫn là một lớp khác

OAuth2 Client web login dùng cookies/session có thể cần CSRF protection và SameSite/Secure/HttpOnly hợp lý. Manager chỉ phụ trách vòng đời token OAuth2; nó không thay thế CSRF, login session validation, CORS hay authorization theo dữ liệu.

Đối với API thuần Bearer header, CSRF threat model có thể khác; đừng sao chép `.csrf(disable)` từ M2M rồi tắt CSRF cho cả website có form login. CORS cũng không giúp service manager hoạt động trong background — CORS là chính sách browser, không tạo ServerWebExchange hay user principal.

## 15. Bài tập suy luận và đáp án

**Câu 1.** Một scheduler dùng `WebClient` thì phải dùng `DefaultReactiveOAuth2AuthorizedClientManager` không?  
**Đáp án:** Không. Dùng WebClient không có nghĩa đang có `ServerWebExchange`; ưu tiên `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` cho job.

**Câu 2.** ClientRegistration đã khai `client_credentials` thì có access token luôn chưa?  
**Đáp án:** Chưa. Registration chỉ là cấu hình; manager/provider phải authorize với AS và lưu `OAuth2AuthorizedClient`.

**Câu 3.** Trong controller xử lý user đã login cần user-scoped access token, chọn manager nào?  
**Đáp án:** Thường dùng `DefaultReactiveOAuth2AuthorizedClientManager`, web repository và principal/exchange hiện tại.

**Câu 4.** Trong request HTTP nhưng backend cần token của chính nó để gọi internal API, luôn buộc dùng web manager không?  
**Đáp án:** Không. Có thể cố ý dùng service manager + client credentials để tách khỏi user session.

**Câu 5.** Tại sao job phải có principal dù grant không có user?  
**Đáp án:** Manager/store cần khóa `registrationId + principalName` cho token được cấp. Principal ở job là tên identity hệ thống ổn định.

**Câu 6.** Scheduler gắn principal `UUID.randomUUID()` mỗi lần sẽ ảnh hưởng gì?  
**Đáp án:** Cache misses/token churn, nhiều bản ghi authorized clients; nên dùng khóa ổn định đúng service/tenant.

**Câu 7.** `ReactiveOAuth2AuthorizedClientService` khác `ReactiveClientRegistrationRepository` như thế nào?  
**Đáp án:** Registration repository lưu cấu hình OAuth client; service lưu authorized clients/token đã cấp.

**Câu 8.** Web repository có luôn lưu trong WebSession không?  
**Đáp án:** Không. `AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository` có thể dùng service cho authenticated user và session cho anonymous.

**Câu 9.** `client_credentials` thường làm mới token qua `refreshToken()` không?  
**Đáp án:** Thường không có refresh token; provider `clientCredentials()` sẽ xin access token mới khi cần.

**Câu 10.** Khi `authorize` trả `Mono.empty()`, có nên `block()` rồi trả null không?  
**Đáp án:** Không. Dùng `switchIfEmpty` và xử lý authorization không được hỗ trợ/không khả dụng rõ ràng trong reactive chain.

**Câu 11.** Có hai beans implement `ReactiveOAuth2AuthorizedClientManager`, injection không `@Qualifier` có nguy cơ gì?  
**Đáp án:** Ambiguous bean resolution hoặc code dùng sai manager. Đặt tên và inject tường minh.

**Câu 12.** Gắn `setDefaultOAuth2AuthorizedClient(true)` trên WebClient dùng để gọi nhiều host có an toàn không?  
**Đáp án:** Không nên. Token có thể được gắn lên mọi HTTP request của WebClient và bị gửi tới host không đáng tin.

**Câu 13.** Token còn hạn nhưng downstream trả 403, có nghĩa token endpoint hỏng không?  
**Đáp án:** Không. 403 có thể do thiếu scope/quyền object/tenant; cần kiểm tra authorization downstream riêng.

**Câu 14.** Tests seed OAuth2AuthorizedClient với token còn hạn có kiểm tra client secret/PKCE/AS thật không?  
**Đáp án:** Không. Tests kiểm tra manager selection/storage và dùng lại token; muốn validate protocol phải test grant exchange với IdP mock/sandbox.

**Câu 15.** `@Scheduled` job cần làm việc thay mặt một user đã logout; có nên lấy token user gần nhất từ static cache không?  
**Đáp án:** Không. Cần delegation/offline-access protocol được AS cho phép và chính sách consent, revocation và storage phù hợp.

## 16. Checklist áp dụng vào dự án

- [ ] Nhận diện context có/không có `ServerWebExchange`, tách rõ user token với service token.
- [ ] Chọn `DefaultReactiveOAuth2AuthorizedClientManager` + web repository cho web request phù hợp.
- [ ] Chọn `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` + reactive service cho background task.
- [ ] `ClientRegistration` đúng grant type, scopes, AS endpoints và client authentication.
- [ ] Provider builder chỉ hỗ trợ các grants thực sự được phép.
- [ ] Dùng principal ổn định, tách theo registration/tenant và không cache token global.
- [ ] Dùng `@Qualifier` khi có nhiều manager beans/WebClient beans.
- [ ] `OAuth2AuthorizeRequest` có principal đúng, web context có exchange khi cần.
- [ ] Gắn authorized client/clientRegistrationId vào WebClient request tường minh.
- [ ] Giới hạn downstream origins; không bật default token trên shared WebClient đa host.
- [ ] `Mono.empty()`/errors/retries được xử lý có kiểm soát.
- [ ] Không gọi `block()` hoặc `subscribe()` rời rạc trong WebFlux service.
- [ ] Service client_credentials không giả định có refresh token.
- [ ] Token/access-refresh secrets không lộ ra JSON/log/metrics.
- [ ] Khi nhiều nodes, token store/refresh concurrency có chính sách phù hợp.
- [ ] Có tests web exchange context, no-exchange service context, principal isolation.
- [ ] Có integration tests token endpoint/401/403 và AS sandbox khi đưa production.
- [ ] CSRF/session/CORS và downstream resource authorization được thiết kế riêng.

## 17. Kết luận và tài liệu chính thức

Nhớ bằng một câu:

> **Có request WebFlux và token gắn với user/request → dùng `DefaultReactiveOAuth2AuthorizedClientManager`. Không có request (scheduler, job, queue) và token service → dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.**

Cùng dùng `ReactiveOAuth2AuthorizedClientManager` và `WebClient` nhưng khác **ngữ cảnh, repository/service storage, principal và authorization grant**. Sai manager thường xuất hiện dưới dạng thiếu `ServerWebExchange`, mất authorized client, re-authorize liên tục hoặc dùng nhầm user token cho tác vụ hệ thống. Thiết kế đúng ranh giới này giúp Spring Security reactive quản lý token một cách kiểm soát và dễ kiểm thử.

**Nguồn chính thức đã đối chiếu:**

- Spring Security 6.5 – OAuth2 Client core interfaces and managers: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html
- Spring Security 6.5 – Authorized Client/WebClient integration: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html
- Spring Security 6.5 – Reactive OAuth2 Client overview: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security 6.5 – `DefaultReactiveOAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/DefaultReactiveOAuth2AuthorizedClientManager.html
- Spring Security 6.5 – `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager.html
- Spring Security 6.5 – `ServerOAuth2AuthorizedClientExchangeFilterFunction` Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html
- Spring Security – `AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/server/AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository.html
- IETF RFC 6749 – OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- IETF RFC 6750 – OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- OWASP – OAuth 2.0 Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html
