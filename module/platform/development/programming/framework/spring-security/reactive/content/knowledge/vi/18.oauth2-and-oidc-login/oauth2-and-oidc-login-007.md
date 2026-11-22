# Lưu và khôi phục yêu cầu cấp quyền bằng `ServerAuthorizationRequestRepository` trong Spring Security Reactive

## 1. Vấn đề cần giải quyết

Khi một ứng dụng **Spring WebFlux** cho người dùng đăng nhập bằng **OAuth 2.0 Authorization Code** hoặc **OpenID Connect (OIDC)**, việc xác thực không diễn ra trong một HTTP request duy nhất. Ứng dụng chuyển trình duyệt sang Authorization Server (IdP), người dùng đăng nhập/đồng ý ở đó, rồi IdP chuyển trình duyệt về URL callback của ứng dụng.

Giữa hai lần request này, ứng dụng cần nhớ: **“Lần chuyển hướng ban đầu đã yêu cầu điều gì, cho client nào, với `state` nào và các thông tin liên quan PKCE/OIDC nào?”** Nếu không lưu và khôi phục đúng, callback không thể được đối chiếu với yêu cầu ban đầu một cách an toàn; người dùng dễ gặp `authorization_request_not_found`, `invalid_state_parameter`, lỗi PKCE, lỗi OIDC nonce hoặc vòng lặp đăng nhập.

Trong **Spring Security Reactive**, trách nhiệm lưu trữ này thuộc interface:

```java
org.springframework.security.oauth2.client.web.server
    .ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>
```

Implementation mặc định:

```java
WebSessionOAuth2ServerAuthorizationRequestRepository
```

lưu `OAuth2AuthorizationRequest` trong **Spring WebFlux `WebSession`** từ lúc khởi tạo chuyển hướng đến lúc xử lý authorization response. Bài này hướng dẫn nguyên lý, API, cấu hình, kiểm thử, các giới hạn multi-tab/multi-instance và cách mở rộng an toàn.

**Mục tiêu học tập:**

1. Giải thích khác nhau giữa **authorization request**, **authorization response**, **access token**, **authorized client** và **SecurityContext**.
2. Theo dõi đường đi `GET /oauth2/authorization/{registrationId}` → IdP → `GET /login/oauth2/code/{registrationId}`.
3. Sử dụng `saveAuthorizationRequest`, `loadAuthorizationRequest` và `removeAuthorizationRequest` đúng tính chất reactive.
4. Hiểu vì sao phải giữ nguyên **`state`, PKCE code verifier, OIDC nonce** và các attributes đi kèm.
5. Cấu hình `ServerHttpSecurity.oauth2Login().authorizationRequestRepository(...)` với một repository thống nhất.
6. Viết ứng dụng **Java 17+ / Spring Boot 3.x / Spring Security 6.x** khởi động được và kiểm thử không cần IdP thật ở cấp repository/redirect.
7. Chẩn đoán cookie, WebSession, callback URL, proxy, multi-tab, multi-node, timeout và replay.

> **Lưu ý phạm vi:** `ServerAuthorizationRequestRepository` chỉ xử lý trạng thái **tạm thời của authorization-code flow**. Nó **không phải** kho chứa access/refresh tokens, không phải `ServerSecurityContextRepository`, và không thay thế việc kiểm chứng chữ ký ID token, nonce, issuer, audience hoặc phân quyền resource.

## 2. Hai request ở hai thời điểm: vì sao cần repository?

Giả sử người dùng bấm nút “Đăng nhập bằng Demo IdP” tại ứng dụng ở `https://app.example.com`.

**Bước 1 — bắt đầu đăng nhập:**

```http
GET /oauth2/authorization/demo HTTP/1.1
Host: app.example.com
```

`OAuth2AuthorizationRequestRedirectWebFilter` nhờ `ServerOAuth2AuthorizationRequestResolver` tạo một `OAuth2AuthorizationRequest` theo client registration `demo`. Tùy cấu hình, request chứa:

- Authorization URI của IdP;
- `client_id`, `response_type=code`, scopes;
- `redirect_uri` của ứng dụng;
- **`state`** khó đoán dùng đối chiếu lần callback;
- những thông tin mở rộng cần thiết cho **PKCE/OIDC**.

Trước khi trả HTTP redirect sang IdP, ứng dụng **lưu authorization request tương ứng** trong repository. Trình duyệt được redirect đến URL của IdP và mang **cookie phiên** của ứng dụng cho những request quay về ứng dụng sau đó.

**Bước 2 — IdP xác thực và callback:**

```http
GET /login/oauth2/code/demo?code=...&state=... HTTP/1.1
Host: app.example.com
Cookie: SESSION=...
```

Spring Security tìm lại authorization request được lưu trong phiên liên quan, **đối chiếu `state` và các dữ kiện cần thiết**, sau đó xử lý authorization code để trao đổi access token với token endpoint. Nếu client đang dùng OIDC, framework tiếp tục kiểm chứng ID token và những yếu tố liên quan. Khi luồng thành công, ứng dụng có thể thiết lập `Authentication` trong `SecurityContext` rồi redirect tới trang sau login.

**Nếu WebSession không khôi phục được**, callback có `code` và `state` nhưng không biết nó tương ứng với yêu cầu ban đầu nào. Đây là tình trạng phải **fail closed**, không được tự dựng một authorization request mới từ query string để tiếp tục token exchange.

### Sơ đồ dòng thời gian

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as WebFlux OAuth2 Client
    participant R as ServerAuthorizationRequestRepository
    participant I as Identity Provider

    B->>A: GET /oauth2/authorization/demo
    A->>A: Resolver tạo OAuth2AuthorizationRequest và state
    A->>R: saveAuthorizationRequest(request, exchange)
    R-->>A: Mono<Void> hoàn tất
    A-->>B: 302 sang IdP + session cookie
    B->>I: GET /authorize?client_id&state&redirect_uri
    I->>B: Trang đăng nhập/đồng ý
    B->>I: User đăng nhập
    I-->>B: 302 về /login/oauth2/code/demo?code&state
    B->>A: GET callback + cookie cùng WebSession
    A->>R: load/removeAuthorizationRequest(exchange)
    R-->>A: Original OAuth2AuthorizationRequest
    A->>A: Correlate state và client registration
    A->>I: Đổi authorization code + PKCE verifier (nếu có)
    I-->>A: Token response
    A->>A: OAuth2/OIDC validation, lập Authentication
    A-->>B: Success redirect; không dùng lại request đã tiêu thụ
```

Sơ đồ là trình tự khái niệm. Tùy bộ lọc/implementation, callback có thể gọi thao tác **load và/hoặc remove** theo từng bước khác nhau; điều quan trọng là một lần callback hợp lệ phải tìm được trạng thái ban đầu và không biến authorization code thành thao tác có thể replay vô hạn.

## 3. Phân biệt các khái niệm rất dễ nhầm

| Thành phần | Lưu loại dữ liệu nào? | Tồn tại đến khi nào? | Vai trò |
| --- | --- | --- | --- |
| `OAuth2AuthorizationRequest` | Yêu cầu chuyển hướng, state, client/scope/redirect, attributes PKCE/OIDC | Từ khởi tạo flow đến callback | Correlation, bảo vệ luồng authorization code |
| `ServerAuthorizationRequestRepository` | `OAuth2AuthorizationRequest` đang chờ | Ngắn hạn, theo phiên/giao dịch | Save, load, remove bản ghi pending |
| `WebSessionOAuth2ServerAuthorizationRequestRepository` | Request trong `WebSession` | Theo session/việc remove | Repository mặc định của Reactive |
| `ReactiveClientRegistrationRepository` | Thông số cấu hình OAuth2 client/IdP | Theo config ứng dụng | Resolver tìm `client_id`, endpoints, scopes |
| `ServerOAuth2AuthorizationRequestResolver` | **Tạo** authorization request từ request HTTP | Tại lúc bắt đầu redirect | Dựng URL và thông số yêu cầu |
| `ServerOAuth2AuthorizedClientRepository` | Authorized client, thường liên kết token và principal | Sau khi cấp token, theo chính sách | Lưu/truy xuất `OAuth2AuthorizedClient` |
| `ServerSecurityContextRepository` | `SecurityContext` chứa `Authentication` | Sau login theo session strategy | Khôi phục danh tính trên requests tiếp theo |
| `ServerRequestCache` | Request protected ban đầu cần quay lại | Trong redirect/login flow | Lưu URL ban đầu, **không lưu OAuth2AuthorizationRequest** |
| `ReactiveOAuth2AuthorizedClientService` | Authorized client/token theo service policy | Sau cấp token | Một hình thức lưu token/client ở backend |
| `OAuth2AuthorizationResponse` | `code` và `state` callback hoặc lỗi từ IdP | Callback hiện tại | Kết quả IdP gửi về, cần đối chiếu với request đã lưu |

Điểm thường nhầm là **authorization request** và **authorized client**. Trước khi user tới IdP, ứng dụng chưa có access token; repository của bài này chỉ lưu **yêu cầu đang chờ hoàn tất**. Sau token exchange thành công mới có `OAuth2AuthorizedClient`/tokens, thuộc thành phần khác.

`ServerRequestCache` cũng không phải repository của bài này. Nó có thể nhớ `/orders/42` để redirect sau đăng nhập, nhưng không thay thế thông tin `state`/PKCE/nonce cần cho callback OAuth2.

## 4. API chính xác của `ServerAuthorizationRequestRepository`

Interface Reactive ở package `org.springframework.security.oauth2.client.web.server` có 3 phương thức chủ chốt:

```java
public interface ServerAuthorizationRequestRepository<
        T extends OAuth2AuthorizationRequest> {

    Mono<Void> saveAuthorizationRequest(
        T authorizationRequest, ServerWebExchange exchange);

    Mono<T> loadAuthorizationRequest(ServerWebExchange exchange);

    Mono<T> removeAuthorizationRequest(ServerWebExchange exchange);
}
```

Đây là **chữ ký rút gọn để học**, không tạo lại interface trong dự án. Dùng Reactor `Mono`, **không** dùng `HttpServletRequest`/`HttpServletResponse` của Servlet.

### 4.1. `saveAuthorizationRequest`

Được dùng khi chuẩn bị chuyển hướng tới IdP. Nó lưu đối tượng `OAuth2AuthorizationRequest` **đầy đủ**, không chỉ `state`:

```java
Mono<Void> saved = repository
    .saveAuthorizationRequest(authorizationRequest, exchange);
```

**Phải subscribe gián tiếp bằng cách trả publisher vào pipeline**. Chỉ tạo `saved` rồi bỏ đi sẽ không bảo đảm việc lưu được thực hiện. Trong code của Spring Security, filter chịu trách nhiệm kết hợp việc lưu với response redirect.

### 4.2. `loadAuthorizationRequest`

Dùng để tìm lại request gốc phù hợp với callback/exchange hiện tại:

```java
Mono<OAuth2AuthorizationRequest> original =
    repository.loadAuthorizationRequest(exchange);
```

Nếu không tìm thấy, trong reactive API dùng **`Mono.empty()`**, không tạo `Mono.just(null)` (Reactor không hỗ trợ null element). Với repository mặc định, trạng thái trong WebSession và callback `state` liên quan đến quá trình truy hồi.

**Không** làm:

```java
return repository.loadAuthorizationRequest(exchange)
    .switchIfEmpty(Mono.just(createNewRequestFromCallback()));
```

Đây là **minh họa phản ví dụ**, `createNewRequestFromCallback()` không thuộc một API chuẩn. Tự tạo request từ callback khi session mất sẽ đánh mất correlation và mở nguy cơ chấp nhận phản hồi không có yêu cầu ban đầu.

### 4.3. `removeAuthorizationRequest`

Trả về và đồng thời loại bỏ authorization request gốc tương ứng:

```java
Mono<OAuth2AuthorizationRequest> consumed =
    repository.removeAuthorizationRequest(exchange);
```

Sau khi request đã được tiêu thụ, một callback/replay sau đó **không được tìm lại cùng giao dịch đang chờ**. Không chỉ gọi `load` rồi để request tồn tại mãi, nhất là khi tự thay thế filter mặc định.

**Không tự gọi remove trong controller trước OAuth2 login filter**: làm vậy có thể khiến filter không còn dữ liệu để kiểm tra callback. Trong luồng chuẩn, để Spring Security sở hữu thời điểm consume; custom repository chỉ cung cấp semantics chính xác.

## 5. Repository mặc định: WebSession

`WebSessionOAuth2ServerAuthorizationRequestRepository` là implementation mặc định, lưu authorization request vào `WebSession` của Spring WebFlux.

```java
ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest> repository =
    new WebSessionOAuth2ServerAuthorizationRequestRepository();
```

Import:

```java
import org.springframework.security.oauth2.client.web.server
    .ServerAuthorizationRequestRepository;
import org.springframework.security.oauth2.client.web.server
    .WebSessionOAuth2ServerAuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint
    .OAuth2AuthorizationRequest;
```

**WebSession làm gì?**

- Browser được gắn với một `WebSession` thông qua cookie/session id phù hợp.
- Khi bắt đầu OAuth2 login, repository lưu authorization request vào session attributes.
- Khi callback quay về **với phiên tương ứng**, repository tải hoặc tiêu thụ request pending.
- Nếu session hết hạn, cookie không được gửi, state không khớp hoặc session store mất trạng thái, callback không khôi phục được request.

**Không cần tự tạo session chỉ để “sửa lỗi”** nếu mặc định hoạt động; phải xác định nguyên nhân session persistence/cookie/redirect trước. Với hệ thống nhiều replica, cần **WebSessionStore dùng chung** và kiểm thử callback có thể về node khác.

### Một session có thể có nhiều luồng OAuth2 login cùng lúc không?

**Không được giả định là có.** Các implementation và phiên bản khác nhau có chính sách lưu pending request khác nhau. Với cấu hình mặc định phổ biến, việc user mở hai tab, khởi tạo hai yêu cầu đăng nhập liên tiếp trên **cùng session** có thể làm giao dịch A bị thay bởi B. Khi callback A đến sau, không còn request/state phù hợp nên login A thất bại.

Để hỗ trợ đồng thời nhiều giao dịch:

- Cần repository tùy biến **keyed by state**, giữ nhiều request có giới hạn per session.
- Mỗi request phải có expiry/TTL, count limit, cleanup khi callback success/failure, atomic consume và ràng buộc với session/user-agent.
- Không lưu một `Map` vô hạn trong session; một client độc hại có thể khởi tạo hàng nghìn authorization requests.
- Cần phân tích các tương tác cookie, session fixation, concurrency và IdP behavior; không chỉ bật một flag cũ từng tồn tại trong Javadoc 5.x.

Nếu sản phẩm không yêu cầu multi-tab login, thông báo người dùng tránh mở nhiều login flows đồng thời và hỗ trợ retry sạch phiên là cách đơn giản hơn.

## 6. Bảo toàn `state`, PKCE và OIDC nonce

### 6.1. `state`: đối chiếu một request đã được khởi tạo

Authorization server trả lại `state` được gửi trong authorization request. Client dùng nó để correlate callback với phiên/giao dịch đã khởi tạo, giảm rủi ro response injection và login CSRF.

```text
GET /oauth2/authorization/demo
  → state = sRANDOM_A, lưu request pending trong WebSession
  → IdP /authorize?...&state=sRANDOM_A

GET /login/oauth2/code/demo?code=c123&state=sRANDOM_A
  → tìm lại request pending phù hợp và xử lý

GET /login/oauth2/code/demo?code=c123&state=WRONG
  → không được chấp nhận như callback của sRANDOM_A
```

**Không tự đặt `state` thành `username`, ngày tháng, một chuỗi cố định, hoặc giá trị từ query string chưa kiểm chứng**. Resolver mặc định của Spring Security tạo giá trị phù hợp; khi tùy biến nên giữ random, khó dự đoán và không đánh mất correlation.

Không log nguyên `state`/`code` trên URL callback: những tham số này có thể xuất hiện trong reverse proxy logs, browser history, telemetry và traces. Log event ID/kết quả/registrationId đã allowlist thay vì nguyên URL.

### 6.2. PKCE: lưu đủ `code_verifier`

PKCE (**Proof Key for Code Exchange**) bổ sung yếu tố ràng buộc code authorization:

1. Client tạo `code_verifier` ngẫu nhiên, giữ bí mật.
2. Gửi `code_challenge` (thường dùng `S256`) trong authorization request tới IdP.
3. Khi đổi code lấy token, client gửi lại **`code_verifier` gốc**.
4. IdP so khớp verifier/challenge.

Trong Spring Security, resolver có thể đưa thông tin `code_verifier` vào **attributes** của `OAuth2AuthorizationRequest` để dùng ở token exchange; `code_challenge` được gửi trên authorization URI. Nếu custom repository chỉ serialize `state` và `redirect_uri` mà bỏ `attributes`, token exchange có thể thất bại vì **không còn verifier**.

Không đưa `code_verifier` vào HTML, cookie đọc được bởi JavaScript, `state` hoặc log. Lưu server-side và bảo vệ session/store.

**Lưu ý khi bật PKCE:** Spring Security hỗ trợ PKCE tự động cho public clients cấu hình phù hợp (`client-authentication-method: none`, thiếu client secret), hoặc khi `ClientRegistration.clientSettings.requireProofKey` được bật. Có thể dùng `OAuth2AuthorizationRequestCustomizers.withPkce()` khi IdP hỗ trợ và cần tùy biến. Không phải mọi registration đều tự bật PKCE chỉ vì ứng dụng dùng OAuth2.

### 6.3. OIDC: giữ và xác minh nonce

Khi scope có `openid`, OpenID Connect thêm cơ chế danh tính như **ID token** và **nonce**. `nonce` giúp ràng buộc ID token với yêu cầu login, giảm nguy cơ replay/substitution của ID token trong một số flow.

Spring Security resolver và phần xử lý OIDC có thể giữ **nonce gốc trong attributes** của request, còn một biểu diễn nonce thích hợp được gửi tới IdP trong authorization URI. Custom repository phải bảo toàn đủ dữ liệu để bộ xác minh ID token thực hiện validation. Không tự bỏ nonce chỉ để giải quyết một lỗi ngẫu nhiên.

**State, PKCE và nonce có mục đích khác nhau:**

| Cơ chế | Điều cần ràng buộc | Lỗi khi mất |
| --- | --- | --- |
| `state` | Callback → authorization request ban đầu | Không tìm thấy request; nguy cơ response injection |
| PKCE `code_verifier` | Authorization code → client đã khởi tạo flow | Token endpoint từ chối hoặc mất bảo vệ PKCE |
| OIDC `nonce` | ID token → auth request ban đầu | OIDC nonce validation thất bại hoặc bị giảm bảo vệ |
| `redirect_uri` | URL callback đã đăng ký/phù hợp | Redirect mismatch, callback lỗi |
| `registrationId` | Client configuration/IdP được lựa chọn | Giao dịch gắn nhầm client/provider |

Framework đã tích hợp phần lớn validation khi dùng `oauth2Login`. **Việc viết repository riêng không có nghĩa bạn được bỏ validation** hoặc tự tin vào các tham số callback.

## 7. Mối quan hệ giữa resolver, redirect filter và callback filter

| Thành phần Reactive | Khi được dùng | Nhiệm vụ |
| --- | --- | --- |
| `DefaultServerOAuth2AuthorizationRequestResolver` | Request bắt đầu login | Tìm `registrationId`, dựng authorization request |
| `OAuth2AuthorizationRequestRedirectWebFilter` | `/oauth2/authorization/{registrationId}` | Lưu request và redirect tới Authorization Server |
| `ServerAuthorizationRequestRepository` | Đầu flow và callback | Save/load/remove request pending |
| `OAuth2LoginAuthenticationWebFilter` | `/login/oauth2/code/{registrationId}` | Khôi phục request, xử lý authorization response |
| `ReactiveOAuth2AccessTokenResponseClient` | Sau callback code hợp lệ | Đổi code lấy token với token endpoint |
| `ReactiveOAuth2UserService` / `OidcReactiveOAuth2UserService` | Sau token exchange | Tải user info/kiểm chứng OIDC cần thiết |
| `ServerSecurityContextRepository` | Sau authentication success | Lưu trạng thái user đăng nhập |
| `ServerOAuth2AuthorizedClientRepository` | Sau token exchange | Lưu authorized client/tokens theo policy |

Đường mặc định của Spring Security 6.x:

```text
GET /oauth2/authorization/demo
    -> Save OAuth2AuthorizationRequest
    -> Redirect to IdP authorize endpoint
GET /login/oauth2/code/demo?code=...&state=...
    -> Recover/consume matching OAuth2AuthorizationRequest
    -> Exchange authorization code for token
    -> OAuth2/OIDC validation
    -> Authentication success / SecurityContext
```

`/oauth2/authorization/{registrationId}` là **đường bắt đầu**, không phải callback. `/login/oauth2/code/{registrationId}` là **callback**; IdP cần whitelist một redirect URI đúng tuyệt đối. Thay đổi một bên nhưng không thay đổi bên còn lại có thể gây lỗi.

Nếu tự tạo `ServerOAuth2AuthorizationRequestResolver` để thêm `prompt=consent`, `login_hint` hoặc PKCE, hãy giữ nguyên các dữ kiện bắt buộc, dùng repo tương thích và kiểm thử state sau redirect.

## 8. Cấu hình repository tường minh trong `oauth2Login`

Trong ứng dụng WebFlux, cách dễ nhất là dùng repository mặc định. Khi muốn khai báo rõ ràng để dùng một instance thống nhất:

```java
@Bean
ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>
authorizationRequestRepository() {
    return new WebSessionOAuth2ServerAuthorizationRequestRepository();
}

@Bean
SecurityWebFilterChain securityChain(
        ServerHttpSecurity http,
        ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest> repo) {

    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/", "/public/**").permitAll()
            .anyExchange().authenticated())
        .oauth2Login(oauth2 ->
            oauth2.authorizationRequestRepository(repo))
        .build();
}
```

Đây là **đoạn trích cấu hình**, các import và app hoàn chỉnh nằm ở phần sau. Khi không có lý do để tùy biến, bạn có thể bỏ bean repo và `.authorizationRequestRepository(...)`, để framework dùng mặc định.

**Lưu ý phân biệt DSL:**

- `oauth2Login(oauth2 -> oauth2.authorizationRequestRepository(repo))` cấu hình state persistence cho **đăng nhập OAuth2/OIDC**.
- `oauth2Client(oauth2 -> oauth2.authorizationRequestRepository(repo))` có thể dùng khi ứng dụng cũng bật **OAuth2 client authorization** cho outgoing resource access theo luồng tương ứng.
- Hai DSL có thể được cấu hình cùng ứng dụng, nhưng phải hiểu path flow và chọn repo nhất quán cho mỗi use case. Không tạo hai repository khác nhau rồi hy vọng callback sẽ tự biết bản ghi được lưu ở đâu.
- `authorizationRequestRepository` khác với `authorizedClientRepository` (lưu token sau cấp quyền).

## 9. Ví dụ Java 17+ / Spring Boot 3.x: lưu request trong WebSession

Ví dụ dưới đây **chạy độc lập tới bước redirect OAuth2** và có kiểm thử repository không cần IdP thật. Để **hoàn tất đăng nhập thật**, phải thay địa chỉ IdP/`client-id`/`client-secret` thử nghiệm bằng đăng ký OAuth2/OIDC hợp lệ ở một Authorization Server đang hoạt động. Điều này được nêu rõ thay vì giả vờ có thể xác minh token từ một provider không tồn tại.

**Cấu trúc dự án:**

```text
src/main/java/demo/oauthstate/OAuthStateApplication.java
src/main/java/demo/oauthstate/SecurityConfig.java
src/main/java/demo/oauthstate/StartPageController.java
src/main/resources/application.yml
src/test/java/demo/oauthstate/AuthorizationRequestRepositoryTest.java
src/test/java/demo/oauthstate/OAuth2RedirectTest.java
```

### 9.1. Dependencies (`build.gradle`)

Trong dự án đã thiết lập Spring Boot Gradle plugin, repositories và Java 17+:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Không thêm `spring-boot-starter-web` để tránh chuyển demo sang Servlet. Spring Boot BOM quản lý phiên bản các starters; không trộn jar Spring Security 6.x với những API phiên bản khác mà không có kế hoạch nâng cấp.

### 9.2. `src/main/java/demo/oauthstate/OAuthStateApplication.java`

```java
package demo.oauthstate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OAuthStateApplication {
    public static void main(String[] args) {
        SpringApplication.run(OAuthStateApplication.class, args);
    }
}
```

### 9.3. `src/main/resources/application.yml`

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo
            client-id: local-demo-client
            client-secret: local-demo-secret
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: profile
        provider:
          demo:
            authorization-uri: https://idp.example.test/oauth2/authorize
            token-uri: https://idp.example.test/oauth2/token
            user-info-uri: https://idp.example.test/oauth2/userinfo
            user-name-attribute: sub
```

`idp.example.test` là địa chỉ **minh họa không cung cấp đăng nhập thực**. Ứng dụng vẫn có thể khởi động và tạo **redirect** tới URI này; không thể hoàn tất token exchange khi không có provider.

**Để đăng nhập thật**, thay toàn bộ URLs và credentials trong provider/client registration bằng thông tin IdP đã cấu hình, dùng **environment variables/secret manager** để quản lý client secret, đồng thời whitelist redirect URI tại IdP. Với OIDC, dùng provider thực hỗ trợ OIDC discovery/JWK, scope `openid` và kiểm tra issuer/ID token; không chỉ thêm chữ `openid` vào provider demo rồi cho rằng đã có một IdP OIDC.

### 9.4. `src/main/java/demo/oauthstate/SecurityConfig.java`

```java
package demo.oauthstate;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.web.server
    .ServerAuthorizationRequestRepository;
import org.springframework.security.oauth2.client.web.server
    .WebSessionOAuth2ServerAuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint
    .OAuth2AuthorizationRequest;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>
    authorizationRequestRepository() {
        return new WebSessionOAuth2ServerAuthorizationRequestRepository();
    }

    @Bean
    SecurityWebFilterChain chain(
            ServerHttpSecurity http,
            ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest> repo) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/public/**").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(oauth2 ->
                oauth2.authorizationRequestRepository(repo))
            .build();
    }
}
```

**Giải thích:**

- `@EnableWebFluxSecurity` bật cấu hình Spring Security cho WebFlux.
- Bean `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>` dùng implementation mặc định; chính bean đó được truyền vào `.oauth2Login(...)`.
- Không cần tự viết `AuthenticationWebFilter` hoặc tự so `state` bằng code của controller; Spring Security xử lý authorization code flow.
- `authorizeExchange()` bảo vệ route khác `/` và `/public/**`; filter bắt đầu OAuth2 tại `/oauth2/authorization/demo` được Spring Security cài đặt vào chain. Vì filter đảm nhiệm đường này, không tạo controller trùng URL.
- `oauth2Login` thêm OAuth2 login flow với `ReactiveClientRegistrationRepository` do Spring Boot xây từ YAML.
- `Customizer` không được dùng trong class này; nếu IDE cảnh báo unused import `Customizer`, có thể xóa dòng import đó khi định dạng mã. Lỗi unused import không cản biên dịch Java.

### 9.5. `src/main/java/demo/oauthstate/StartPageController.java`

```java
package demo.oauthstate;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class StartPageController {

    @GetMapping("/")
    public Mono<String> index() {
        return Mono.just(
            "Start OAuth2 login at /oauth2/authorization/demo");
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/private/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName());
    }
}
```

`/private/me` yêu cầu login theo security policy. Nó lấy danh tính từ **Reactor Context**, không chấp nhận tên user từ request parameter. Khi chưa có IdP thật, request này sẽ yêu cầu đăng nhập/chuyển hướng theo entry point — đó là hành vi mong đợi của demo trước khi hoàn tất OAuth2 login.

### 9.6. Chạy và quan sát redirect

```bash
# Linux/macOS
./gradlew bootRun

# Windows
gradlew.bat bootRun
```

Thử:

```bash
curl -i http://localhost:8080/public/ping

# KHÔNG thêm -L: chỉ xem redirect tới IdP demo, không gọi IdP giả.
curl -i http://localhost:8080/oauth2/authorization/demo
```

Response khởi tạo login thường là `302 Found` với header `Location` chứa thông số tương tự:

```text
https://idp.example.test/oauth2/authorize?
  response_type=code&client_id=local-demo-client&
  redirect_uri=...&state=RANDOM_VALUE&scope=profile
```

Dòng trên được xuống hàng **để dễ đọc**, không phải URL copy nguyên văn. Giá trị `state` ngẫu nhiên và thứ tự/URL encoding có thể khác. Server cũng có thể gửi cookie session để callback về nhận diện cùng WebSession.

**Không** dùng `curl -L` để theo redirect tới domain demo rồi cho rằng thất bại kết nối là lỗi Spring Security. Với IdP thực, browser được redirect sang trang đăng nhập hợp lệ; quay về callback sẽ dùng repo để khôi phục original authorization request.

## 10. Unit test có thể chạy không cần IdP: save → load → remove

Đây là **bộ test quan trọng nhất cho chính repository**. Nó không cần gọi token endpoint hoặc có Authorization Server; `MockServerWebExchange` của Spring Test mô phỏng request callback, giữ một `WebSession` test.

Tệp `src/test/java/demo/oauthstate/AuthorizationRequestRepositoryTest.java`:

```java
package demo.oauthstate;

import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.oauth2.client.web.server
    .WebSessionOAuth2ServerAuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint
    .OAuth2AuthorizationRequest;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AuthorizationRequestRepositoryTest {

    private OAuth2AuthorizationRequest original(String state) {
        return OAuth2AuthorizationRequest.authorizationCode()
            .authorizationUri(
                "https://idp.example.test/oauth2/authorize")
            .clientId("local-demo-client")
            .redirectUri(
                "http://localhost:8080/login/oauth2/code/demo")
            .scopes(Set.of("profile"))
            .state(state)
            .build();
    }

    @Test
    void savesLoadsAndConsumesOriginalRequest() {
        var repo =
            new WebSessionOAuth2ServerAuthorizationRequestRepository();

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/login/oauth2/code/demo")
                .queryParam("state", "state-for-unit-test")
                .queryParam("code", "unused-test-code"));

        var expected = original("state-for-unit-test");

        StepVerifier.create(
                repo.saveAuthorizationRequest(expected, exchange))
            .verifyComplete();

        StepVerifier.create(repo.loadAuthorizationRequest(exchange))
            .assertNext(saved -> {
                assertEquals(expected.getState(), saved.getState());
                assertEquals(expected.getClientId(), saved.getClientId());
                assertEquals(
                    expected.getRedirectUri(), saved.getRedirectUri());
            })
            .verifyComplete();

        StepVerifier.create(repo.removeAuthorizationRequest(exchange))
            .assertNext(consumed ->
                assertEquals(expected.getState(), consumed.getState()))
            .verifyComplete();

        // Callback đã consume, không được dùng lại request cũ.
        StepVerifier.create(repo.loadAuthorizationRequest(exchange))
            .verifyComplete();
    }

    @Test
    void refusesRequestWithUnexpectedState() {
        var repo =
            new WebSessionOAuth2ServerAuthorizationRequestRepository();

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/login/oauth2/code/demo")
                .queryParam("state", "wrong-state"));

        StepVerifier.create(repo.saveAuthorizationRequest(
            original("expected-state"), exchange))
            .verifyComplete();

        // Repository mặc định không trả lại authorization request
        // khi state của callback không khớp bản đã lưu.
        StepVerifier.create(repo.loadAuthorizationRequest(exchange))
            .verifyComplete();
    }
}
```

Chạy:

```bash
# Linux/macOS
./gradlew test --tests 'demo.oauthstate.AuthorizationRequestRepositoryTest'

# Windows
gradlew.bat test --tests "demo.oauthstate.AuthorizationRequestRepositoryTest"
```

**Tại sao test này đáng tin?**

- Dùng chính implementation mặc định trong Spring Security WebFlux, không viết repository mock luôn trả kết quả.
- `saveAuthorizationRequest` hoàn tất trước lần `load`.
- `load` xác minh đủ state, clientId và redirectUri gốc.
- `remove` trả và loại bỏ request; sau đó load lại là empty.
- Test thứ hai kiểm tra một callback mang state sai **không** lấy được request ban đầu trong cùng session test.

Đây là **unit test của repository**. Nó **không chứng minh** rằng browser/IdP thực dùng cùng cookie, token exchange thành công hay ID token được xác minh. Những bước đó cần integration test với IdP giả lập đầy đủ hoặc IdP test tenant.

## 11. Test integration: filter lưu request trước redirect

Ngoài gọi trực tiếp repository, ta cần test ứng dụng có một client registration và filter OAuth2 thực sự đưa browser tới IdP.

Tệp `src/test/java/demo/oauthstate/OAuth2RedirectTest.java`:

```java
package demo.oauthstate;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class OAuth2RedirectTest {

    @Autowired
    WebTestClient client;

    @Test
    void startLoginRedirectsToAuthorizationEndpoint() {
        client.get().uri("/oauth2/authorization/demo")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value("Location", location -> {
                assertTrue(location.startsWith(
                    "https://idp.example.test/oauth2/authorize"));
                assertTrue(location.contains("client_id="));
                assertTrue(location.contains("state="));
                assertTrue(location.contains("response_type=code"));
            });
    }

    @Test
    void publicPingDoesNotStartOAuth2Login() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }
}
```

Chạy:

```bash
./gradlew test --tests 'demo.oauthstate.OAuth2RedirectTest'
```

**Bộ test này có ý nghĩa giới hạn:** xác nhận Spring Security khởi tạo đúng redirect và client registration. Nó **không** thử callback đã trao đổi token thành công, vì IdP trong YAML là domain demo không cung cấp token endpoint. Khi tích hợp IdP thực, thêm test browser hoặc OAuth2 test server để xác nhận:

- Callback dùng **cùng session** với request khởi tạo.
- `state` đúng → token exchange hợp lệ.
- `state` sai/thiếu → login không thành công.
- `code` đã dùng hoặc callback lặp → bị từ chối.
- PKCE verifier/nonce còn nguyên → token/OIDC validation đúng.
- Sau login, `/private/me` có `Authentication`; trước login không có.

Không tự gắn một `Authentication` giả trong integration test này rồi tuyên bố authorization code flow đã được kiểm chứng.

## 12. Quan sát repository mà không viết lại cơ chế bảo mật

Một yêu cầu phổ biến là muốn biết **có thật sự save/load/remove không**, phục vụ debug và audit. An toàn nhất là giữ implementation mặc định rồi tạo wrapper chỉ ghi event ở mức **không nhạy cảm**, thay vì tự lưu mỗi trường.

Ví dụ class tùy chọn `src/main/java/demo/oauthstate/ObservingAuthorizationRequestRepository.java`:

```java
package demo.oauthstate;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.oauth2.client.web.server
    .ServerAuthorizationRequestRepository;
import org.springframework.security.oauth2.client.web.server
    .WebSessionOAuth2ServerAuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint
    .OAuth2AuthorizationRequest;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class ObservingAuthorizationRequestRepository
        implements ServerAuthorizationRequestRepository<
            OAuth2AuthorizationRequest> {

    private static final Logger log = LoggerFactory.getLogger(
        ObservingAuthorizationRequestRepository.class);

    private final ServerAuthorizationRequestRepository<
        OAuth2AuthorizationRequest> delegate =
            new WebSessionOAuth2ServerAuthorizationRequestRepository();

    @Override
    public Mono<Void> saveAuthorizationRequest(
            OAuth2AuthorizationRequest request,
            ServerWebExchange exchange) {
        return delegate.saveAuthorizationRequest(request, exchange)
            .doOnSuccess(ignored ->
                log.debug("OAuth2 authorization request saved"));
    }

    @Override
    public Mono<OAuth2AuthorizationRequest> loadAuthorizationRequest(
            ServerWebExchange exchange) {
        return delegate.loadAuthorizationRequest(exchange)
            .doOnNext(ignored ->
                log.debug("OAuth2 authorization request found"));
    }

    @Override
    public Mono<OAuth2AuthorizationRequest> removeAuthorizationRequest(
            ServerWebExchange exchange) {
        return delegate.removeAuthorizationRequest(exchange)
            .doOnNext(ignored ->
                log.debug("OAuth2 authorization request consumed"));
    }
}
```

**Đây là phương án thay thế tùy chọn**, không được đăng ký cùng lúc hai bean có cùng kiểu rồi mong Spring tự chọn. Để dùng wrapper, thay method `authorizationRequestRepository()` trong `SecurityConfig` bằng:

```java
@Bean
ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>
authorizationRequestRepository() {
    return new ObservingAuthorizationRequestRepository();
}
```

Các sự kiện debug **không** in ra `request.getState()`, `authorizationRequestUri`, session ID, `code_verifier`, nonce, authorization code, cookie hay access token. Trong production, có thể có audit ID độc lập, nhưng cần cơ chế correlation không tiết lộ bí mật.

**Không dùng `request.toString()` để log**: object có thể chứa attributes nhạy cảm phục vụ PKCE/OIDC. Wrapper chỉ giữ đúng behavior của delegate; mọi `Mono` đều được ghép vào pipeline và không dùng `.subscribe()`/`.block()`.

## 13. Khi nào cần custom `ServerAuthorizationRequestRepository`?

Default WebSession repo thường là lựa chọn tốt nhất cho **server-side OAuth2 login**. Chỉ thay khi có yêu cầu đã được kiểm chứng:

- Hệ thống muốn lưu pending request vào store dùng chung với TTL, thay vì WebSession attrs.
- Nhiều OAuth2 login flows phải hoạt động đồng thời trong cùng một browser session.
- Yêu cầu audit/tracing chặt chẽ, nhưng không muốn sửa framework source.
- Ứng dụng phân tán cần atomic consume/invalidation và quá trình cleanup độc lập.
- Có kiến trúc đặc biệt về cookie/session storage giữa nhiều miền/instances, đã đánh giá threat model.

Nếu tự viết implementation, cần thiết kế:

1. **Khóa tra cứu:** gắn với **session/browser transaction**, `state` ngẫu nhiên và registration/client chính xác. Không chỉ dùng `userId` vì ở thời điểm bắt đầu login user có thể chưa xác thực.
2. **Đối chiếu state:** callback chỉ được tìm request khớp `state`; sai hoặc thiếu phải fail closed.
3. **Lưu toàn bộ request:** không đánh mất `attributes` chứa PKCE verifier/OIDC nonce hoặc các thông số đã được resolver xác minh.
4. **Atomic consume:** `removeAuthorizationRequest` loại bản ghi đúng lúc, không cho hai callback cùng dùng lại state.
5. **TTL và cleanup:** bản ghi pending có thời hạn ngắn; không cho attacker tạo requests vô hạn trong memory/Redis.
6. **Mã hóa/quyền truy cập:** hạn chế truy cập store; bảo vệ PKCE verifier/nonce và metadata nhạy cảm; dùng TLS cho Redis/database.
7. **Cookie/session association:** callback phải gắn lại đúng trình duyệt/phiên khởi tạo; không dựa duy nhất vào state được đưa từ client nếu không có cơ chế bảo vệ kết hợp phù hợp.
8. **Error handling:** mất store/timeout phải fail closed, không tự xác thực khi không đọc được request; ghi metric vận hành.
9. **Concurrency:** nhiều callback hoặc nhiều login tabs có thể đua nhau; atomic compare-and-delete/transaction là yêu cầu quan trọng.
10. **Observability:** log category/result, không log state/code/verifier, raw callback URL hoặc session ID.

Không nên viết repository dựa trên `ConcurrentHashMap<String, OAuth2AuthorizationRequest>` toàn cục rồi cho phép bất kỳ caller biết `state` là lấy được request, nếu chưa xét giới hạn TTL, session binding, scaling và tấn công chiếm state. Một in-memory map có thể phục vụ một test cô lập, nhưng **không mặc nhiên phù hợp production**.

### Vì sao custom repository không được trả chính request của user khác?

Trong OAuth2 redirect flow, client chưa có `Authentication` của user ở callback. Do đó repository có vai trò như một **transaction store trước xác thực**, phải cô lập giao dịch theo browser/session và state. Nếu load nhầm bản ghi của người khác, token exchange và lập session có thể sai chủ thể, dẫn tới login CSRF/account confusion.

**Bảo đảm ở nhiều nodes** còn phải xét trường hợp Node A lưu, Node B nhận callback; một repository gắn vào memory của Node A sẽ trả empty ở Node B. Dùng WebSessionStore phân tán hoặc repository có backing store dùng chung, không dựa vào sticky sessions như một cam kết bảo mật duy nhất.

## 14. Multi-tab, refresh, back button và callback replay

Các tình huống thực tế:

| Tình huống | Kết quả/điểm cần kiểm tra |
| --- | --- |
| User khởi tạo login A, callback A ngay | Có thể khôi phục request A nếu session/state đúng |
| User khởi tạo A rồi B trong cùng session | A có thể bị thay bởi B tùy implementation; cần test multi-tab |
| Callback B tới trước A | Một flow có thể thành công, flow còn lại thất bại nếu repo chỉ giữ một pending request |
| User refresh URL callback chứa code | Code đã tiêu thụ hoặc authorization request đã remove; không được login lần nữa |
| User nhấn Back quay lại URL IdP/authorize | Có thể tạo một authorization request/state mới; không tái sử dụng state cũ |
| Session hết hạn lúc user đang ở IdP | Callback thiếu request ban đầu; hiển thị trang retry an toàn |
| Cookie bị browser chặn | Server nhận phiên khác hoặc chưa có session; không tìm được request |
| User đổi trình duyệt giữa hai bước | Session/cookie khác; default WebSession repo không tìm thấy yêu cầu |
| LB chuyển callback sang node khác | Cần shared WebSessionStore hoặc repository tương thích |
| Callback có `error=access_denied` | Thất bại OAuth2 theo protocol; cần cleanup và UI chung |
| Callback thiếu `state` hoặc state khác | Không được tự dựng request mới để “bỏ qua lỗi” |
| Token endpoint unavailable sau khi nhận callback | Lỗi hạ tầng/token exchange; không báo thành login thành công |

Một hành vi đáng chú ý của default session repository là **số lượng pending requests được quản lý** không phải lời hứa về multi-tab support. Nếu sản phẩm yêu cầu nhiều flow song song, test cụ thể dưới cùng session và viết bounded state-keyed repository đúng security contract.

Không thay logic bằng “nếu state không tìm được thì tự động cho đăng nhập lại bằng code cũ”. Authorization code ngắn hạn, single-use và gắn với client/redirect/PKCE; flow mới phải **bắt đầu lại từ endpoint authorization** với state mới.

## 15. WebSession cookie, SameSite, proxy và redirect URI

Các lỗi “không khôi phục được authorization request” thường không nằm ở repository mà ở **session continuity**.

### 15.1. Cookie phiên có quay về callback không?

IdP chuyển browser trở lại ứng dụng qua một **cross-site redirect**. Browser có thể không gửi cookie nếu:

- Cookie có `SameSite=Strict`, nên cross-site navigation không mang cookie phù hợp.
- Đường callback dùng host/domain khác đường bắt đầu login (`www` và non-`www`, subdomain khác nhau).
- Cookie `Path` không bao phủ `/login/oauth2/code/...`.
- Cookie có flag `Secure` nhưng request callback dùng HTTP thay vì HTTPS.
- Browser chặn third-party cookie hoặc app bị nhúng trong iframe.
- Session đã hết hạn hoặc bị logout/invalidate trong lúc user ở IdP.
- LB/gateway không tìm thấy session do backend store không chia sẻ.

Với luồng OAuth2 authorization-code callback **top-level GET**, `SameSite=Lax` thường là lựa chọn tương thích hơn `Strict` khi trình duyệt từ IdP quay về app. Nếu IdP cấu hình response mode **form_post** (cross-site POST), cookie policy khác và có thể cần `SameSite=None; Secure` cùng threat model thích hợp. **Không tùy tiện hạ tất cả cookie sang `SameSite=None` chỉ vì một lỗi chưa điều tra.**

### 15.2. Proxy làm sai `{baseUrl}`

Spring Security có thể xây `redirect_uri` từ các biến như:

```text
{baseUrl}/login/oauth2/code/{registrationId}
```

Nếu app chạy sau reverse proxy và thấy request nội bộ là `http://service:8080` thay vì public `https://app.example.com`, redirect URI gửi IdP có thể sai scheme/host. Cần cấu hình forwarded headers/trusted proxy theo Spring Boot/Spring WebFlux và whitelist redirect URI đúng ở IdP. **Không tin toàn bộ `X-Forwarded-*` đến từ Internet**; chỉ chấp nhận qua proxy tin cậy.

### 15.3. Không đổi callback mà quên registration

Mặc định:

```text
Bắt đầu: /oauth2/authorization/{registrationId}
Callback: /login/oauth2/code/{registrationId}
```

Muốn callback thành `/login/oauth2/callback/{registrationId}`, phải đồng bộ:

1. Matcher ở `oauth2Login().authenticationMatcher(...)`;
2. `ClientRegistration.redirectUri`;
3. Redirect URI allowlist tại IdP;
4. Route security matchers, reverse proxy và tests.

Đổi mỗi URL trong gateway mà không đổi client registration sẽ khiến callback nhận được nhưng không được xử lý đúng, hoặc IdP từ chối `redirect_uri`.

## 16. An toàn thông tin: không nhầm `state` với toàn bộ xác thực

`state` là biến liên kết OAuth2 authorization request/response, không thay cho:

- Client authentication ở token endpoint (khi applicable);
- PKCE verifier/challenge;
- Kiểm tra `redirect_uri` và `client_id`;
- OIDC ID token signature, issuer, audience, expiry và nonce;
- Authorization theo scopes/roles sau khi xác thực.

**Không** bỏ kiểm tra state để tránh `authorization_request_not_found`. **Không** lưu toàn bộ OAuth2 authorization request vào cookie plaintext dễ sửa bởi client. **Không** nhét PKCE `code_verifier` hoặc client secret vào query string/browser storage chỉ vì muốn hệ thống “stateless” bằng mọi giá.

Authorization code và state xuất hiện trên URL callback theo giao thức; log có thể vô tình lưu chúng. Nên:

- Tránh log full callback URI, `Location` header chứa code/state, raw cookies và session IDs.
- Dùng HTTPS, HSTS/cookie flags phù hợp và quản lý secrets tập trung.
- Trả trang lỗi đăng nhập chung cho client, nhưng log metric **loại lỗi**: session missing, state mismatch, token exchange timeout, provider error, registration mismatch.
- Giới hạn số login initiations trên session/IP ở mức cân bằng để chống abuse.
- Dọn các pending request đã hết hạn và kiểm tra lỗi store không để tăng vô hạn bộ nhớ.

Spring Security từng có thông báo bảo mật về **DoS do khởi tạo quá nhiều Authorization Requests** ở một số phiên bản cũ (CVE-2021-22119); các bản vá đã được phát hành từ nhiều năm trước. Điều quan trọng với custom repository là **giới hạn dữ liệu tạm và dùng phiên bản framework đã được cập nhật bảo mật**.

## 17. Kiểm thử callback thật với IdP test

Unit test ở phần 10 xác nhận repository đúng contract, nhưng một hệ thống cần các test end-to-end sau với **IdP test tenant** hoặc Authorization Server giả lập có token endpoint:

1. **Happy path:** bắt đầu `/oauth2/authorization/demo`, nhận state + cookie, IdP redirect về cùng session, `Authentication` hợp lệ được thiết lập, `/private/me` trả principal.
2. **State mismatch:** cố tình đổi một ký tự của state trên callback; login phải fail closed.
3. **No cookie:** callback không gửi cookie của lần bắt đầu; repository không khôi phục được request, không có authenticated session.
4. **Expired session:** hết hạn WebSession giữa hai bước; user được hướng dẫn bắt đầu flow mới, không được bỏ qua validation.
5. **Replay:** dùng lại `code/state` của callback thành công; không được thành công lần hai.
6. **Wrong registration:** callback đi vào registration/provider khác; không dùng request đã lưu cho client khác.
7. **PKCE:** client có `code_verifier`/challenge hợp lệ; bỏ verifier trong thử nghiệm phải thất bại token exchange.
8. **OIDC:** ID token sai nonce/issuer/audience/signature hoặc expired phải bị từ chối.
9. **Two tabs:** hai authorization requests cùng session, kiểm tra hành vi hỗ trợ/giới hạn đã công bố.
10. **Multiple replicas:** khởi tạo ở node A, callback ở node B, shared session/store vẫn đọc được request.
11. **Reverse proxy:** redirect URI đúng external HTTPS host, cookie domain/path phù hợp.
12. **Provider error:** callback `error=access_denied` hoặc token endpoint outage không biến thành authenticated user.
13. **Observability:** logs/traces không chứa authorization code, state, PKCE verifier, nonce, cookie hoặc tokens.

**Lưu ý test:** Nếu dùng `mockOAuth2Login()` hoặc một mock authentication để test controller, đó là test authorization **sau đăng nhập**, không xác minh save/load/remove của authorization request hay exchange code với IdP. Cần phân biệt test repository, test redirect filter và test toàn flow.

## 18. Chẩn đoán lỗi theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Bước kiểm tra |
| --- | --- | --- |
| `authorization_request_not_found` | Không load được request gốc | WebSession cookie, TTL, session store, state, multi-tab |
| `invalid_state_parameter` / state mismatch | Callback state khác request đã lưu | Trùng session, không thay state bằng dữ liệu tự dựng |
| Callback redirect về login liên tục | Cookie mất, OAuth2 callback lỗi, security chain sai | Network/Set-Cookie/callback, error handler, session |
| Redirect sang IdP không có `state` | Resolver/customizer bị cấu hình sai | `OAuth2AuthorizationRequest` trước redirect |
| PKCE `invalid_grant` | Verifier mất/sai, code đã dùng hoặc redirect URI khác | Có bảo toàn attributes, code verifier, client & redirect URI |
| OIDC nonce validation thất bại | Nonce không khớp hoặc bị mất trong repository | Có giữ full request attributes và OIDC validation |
| Callback về host HTTP nội bộ | Reverse proxy forwarded headers cấu hình sai | `{baseUrl}`, trusted proxy, client registration |
| Node A khởi tạo, Node B callback lỗi | Session không chia sẻ | WebSessionStore hoặc backing repository phân tán |
| Chỉ tab thứ hai login thành công | Pending request bị thay bởi flow mới | Test multi-tab / bounded state-keyed repository |
| Thử lại callback cùng code không được | Request/code đã tiêu thụ | Hành vi đúng; bắt đầu authorization flow mới |
| Backend gọi token endpoint báo timeout | Provider/network/service outage | Phân loại lỗi hạ tầng, timeout, retry an toàn |
| GET `/oauth2/authorization/demo` không redirect | Không có registration/filter/chain đúng | Starter oauth2-client, client registration, `oauth2Login()` |
| Test mock user pass nhưng IdP thật lỗi | Mock bỏ qua toàn OAuth2 grant flow | Tăng mức integration test |
| Browser khác thành công, browser hiện tại thất bại | Cookie policies, session stale, extensions | Thử profile riêng, inspect cookies an toàn |

**Quy trình debug có thứ tự:**

1. Xác định `registrationId`, request bắt đầu, callback URI và security chain đang match.
2. Xem status và `Location` của request bắt đầu: có chuyển hướng sang IdP đúng host và có `state` hay không.
3. Kiểm tra browser có nhận/gửi session cookie phù hợp giữa hai request không. Không paste giá trị cookie thực vào ticket.
4. Xác minh WebSessionStore còn dữ liệu và cùng backend/repository đang đọc; nếu nhiều replicas, kiểm tra shared storage.
5. Kiểm tra số flow đăng nhập đang chờ trong cùng session, user có mở nhiều tabs hoặc retry không.
6. Nếu state khớp mà token exchange fail, kiểm tra client/redirect/PKCE/nonce/IdP, đừng đổi repository một cách mù quáng.
7. Đối chiếu API, dependency versions và logging, sau đó test lại negative cases (missing state, replay, no cookie).
8. Không “chữa” bằng tắt state/nonce validation, kéo TTL vô hạn hoặc thêm raw tokens vào URL/log.

## 19. Sai lầm phổ biến

**Sai lầm 1 — Dùng `HttpSessionOAuth2AuthorizationRequestRepository` của Servlet trong WebFlux.**  
Reactive phải dùng `WebSessionOAuth2ServerAuthorizationRequestRepository` hoặc custom `ServerAuthorizationRequestRepository`; không lấy `HttpServletRequest` hay `HttpSecurity` làm tham số.

**Sai lầm 2 — Nhầm repository với kho lưu access token.**  
Authorization request tồn tại **trước** token exchange; `ServerOAuth2AuthorizedClientRepository`/service mới quản lý `OAuth2AuthorizedClient` sau cấp token. Thay repository của bài không thay token storage.

**Sai lầm 3 — Chỉ lưu một chuỗi `state`.**  
PKCE `code_verifier`, OIDC nonce và attributes khác có thể bị mất. Lưu full `OAuth2AuthorizationRequest` hoặc mapping có kiểm chứng đầy đủ.

**Sai lầm 4 — Tạo request gốc từ callback khi không có session.**  
Callback không đủ là bằng chứng người dùng đã khởi tạo flow. Hãy fail closed và khởi động lại login.

**Sai lầm 5 — Không remove request sau khi callback.**  
Pending request cũ dễ bị replay hoặc chiếm tài nguyên. Cần consume một lần, cleanup, TTL.

**Sai lầm 6 — Lưu map vô hạn cho nhiều tabs.**  
Không có giới hạn và TTL có nguy cơ DoS. Dùng bounded state-keyed persistence cùng atomic consume.

**Sai lầm 7 — Hai beans/repositories khác nhau cho hai đầu flow.**  
Nếu redirect filter lưu ở repository A nhưng callback filter tìm repository B, login luôn thất bại. Chỉ định cùng repo cho flow thực sự đang dùng và test end-to-end.

**Sai lầm 8 — Tắt cookie/WebSession nhưng vẫn mong mặc định lưu authorization request.**  
`NoOpServerSecurityContextRepository` và authorization request repository có vai trò khác nhau. Một OAuth2 browser redirect flow cần **nơi giữ transaction state** giữa hai request; phải thiết kế thay thế trước khi vô hiệu hóa session.

**Sai lầm 9 — SameSite=Strict trên OAuth2 callback cross-site rồi không tìm được session.**  
Kiểm tra cross-site navigation, GET/form_post, cookie flags và path trước khi đổ lỗi cho IdP.

**Sai lầm 10 — Cho redirect URI tùy ý từ query parameter.**  
Có nguy cơ open redirect/client confusion. Redirect URI phải thuộc client registration và allowlist của IdP; forwarded headers chỉ tin proxy hợp lệ.

**Sai lầm 11 — Ghi raw authorization URI, `code`, `state`, cookie vào logs.**  
Những giá trị có thể nhạy cảm; log tối thiểu, tránh gắn URL đầy đủ vào tracing span.

**Sai lầm 12 — Test chỉ kiểm tra 302 từ `/oauth2/authorization/demo`.**  
302 chứng minh luồng initiation; không chứng minh repo khôi phục đúng ở callback hay token validation thành công. Cần unit test repository và IdP integration test.

## 20. Checklist triển khai và tự đánh giá

| Nội dung | Kết quả mong đợi |
| --- | --- |
| Đúng Reactive API | `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>` |
| Save | Lưu đầy đủ request trước redirect, publisher được thực thi |
| Load | Tìm theo session và state đúng; unknown/mismatch fail closed |
| Remove | Tiêu thụ request đúng một lần, không replay |
| PKCE | `code_verifier`/attributes không bị mất |
| OIDC | Nonce và ID token validation được bảo toàn |
| Client registration | URI, clientId, scopes, redirect URI đúng IdP |
| Cookie | GET initiation và callback dùng cùng session |
| SameSite/TLS | Cross-site callback mang cookie phù hợp, HTTPS production |
| Proxy | External base URL đúng, trust forwarded headers |
| Multi-tab | Hành vi có test; nếu hỗ trợ phải bounded/TTL |
| Multi-node | Shared WebSessionStore hoặc repository tương thích |
| Custom repo | Atomic consume, TTL, session binding, fail closed |
| Error handling | Không tự cấp quyền khi store/IdP thất bại |
| Secrets | Không log state, code, verifier, nonce, cookies hoặc tokens |
| Tests | Save/load/remove, wrong state, redirect, end-to-end callback |
| Replay | Callback thứ hai không thể dùng cùng transaction |
| Authorization | Sau login vẫn kiểm tra roles/scopes/resource owner |

### Câu hỏi tự kiểm tra

**1. Repository này lưu access token hay `OAuth2AuthorizationRequest`?**  
Nó lưu **authorization request tạm thời trước callback**. Token lưu qua các authorized-client components khác.

**2. Vì sao chỉ lưu `state` là chưa đủ?**  
PKCE code verifier, OIDC nonce và những attributes khác có thể cần cho token/ID token validation.

**3. `saveAuthorizationRequest()` trả gì trong WebFlux?**  
`Mono<Void>`. Phải ghép publisher vào luồng xử lý để thao tác thực thi.

**4. Nếu callback thiếu WebSession gốc, có nên dựng request mới từ `code/state` không?**  
Không. Phải fail closed và cho user bắt đầu authorization flow mới.

**5. `removeAuthorizationRequest()` có ý nghĩa gì?**  
Tìm và **tiêu thụ/xóa** authorization request pending để không được dùng lại như một giao dịch chưa hoàn tất.

**6. `ServerRequestCache` có thay repo này không?**  
Không. Nó nhớ URL resource ban đầu, không chứa đầy đủ authorization request/PKCE/OIDC state.

**7. Vì sao login hai tab trong cùng browser đôi khi chỉ một tab hoàn tất?**  
Chúng chia sẻ WebSession; repository mặc định có thể không giữ đồng thời nhiều pending requests. Cần test và thiết kế bounded state-keyed repo nếu bắt buộc hỗ trợ.

**8. Khi chạy hai replicas, cần kiểm tra gì?**  
Node nhận callback phải truy cập được cùng WebSession/store; các thao tác consume phải an toàn dưới concurrency.

**9. `SameSite=Strict` có thể ảnh hưởng gì?**  
Browser có thể không gửi session cookie khi IdP redirect cross-site, khiến callback không tìm được original request.

**10. Lỗi `invalid_state_parameter` được “sửa” bằng cách bỏ state check được không?**  
Không. Đó là một lớp bảo vệ quan trọng; cần tìm nguyên nhân mất session, thay flow hoặc mismatch.

## Ghi nhớ

- **`ServerAuthorizationRequestRepository` lưu và khôi phục `OAuth2AuthorizationRequest` từ lúc redirect sang IdP đến callback.**
- **Mặc định Reactive dùng `WebSessionOAuth2ServerAuthorizationRequestRepository`**, không phải `HttpSessionOAuth2AuthorizationRequestRepository`.
- Ba API: `saveAuthorizationRequest(...): Mono<Void>`, `loadAuthorizationRequest(...): Mono<T>`, `removeAuthorizationRequest(...): Mono<T>`.
- **Không làm mất `state`, PKCE verifier hoặc OIDC nonce**; không tự tạo request mới từ callback khi repository trả empty.
- `ServerOAuth2AuthorizationRequestResolver` **tạo** request; repository **lưu/khôi phục**; authorized-client store **lưu tokens sau grant**; security-context repo **giữ authentication sau login**.
- WebSession cookie, SameSite, TTL, proxy host, nhiều tabs và nhiều replicas đều ảnh hưởng khả năng callback tìm lại request.
- Với custom repo, yêu cầu **bounded storage + TTL + atomic consume + session binding**, không log bí mật hoặc cho callback replay.
- Kiểm thử nhiều tầng: **repository save/load/remove**, **OAuth2 redirect**, **callback thực với IdP test**.

### Tài liệu chính thức

- [Spring Security 6.5 — OAuth2 Authorization Grant, Storing the Authorization Request](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorization-grants.html)
- [Spring Security 6.5 — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/advanced.html)
- [Spring Security 6.5 — OAuth2 WebFlux Overview](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html)
- [Spring Security 6.5 — ServerAuthorizationRequestRepository Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/server/ServerAuthorizationRequestRepository.html)
- [Spring Security — WebSessionOAuth2ServerAuthorizationRequestRepository Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.4-SNAPSHOT/api/org/springframework/security/oauth2/client/web/server/WebSessionOAuth2ServerAuthorizationRequestRepository.html)
- [Spring Security — Historical authorization-request DoS advisory (CVE-2021-22119)](https://spring.io/security/cve-2021-22119/)
