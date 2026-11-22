# Chuyển tiếp danh tính, token relay và kiểm tra token ở từng ranh giới

## 1. Vấn đề thực tế trong Gateway nhiều tenant

Một hệ thống SaaS có **tenant A** và **tenant B**, mỗi tenant có một issuer/Identity Provider (IdP) riêng. Người dùng đăng nhập qua **Spring Cloud Gateway Server WebFlux**, gateway định tuyến request đến một downstream **Spring WebFlux Resource Server** để đọc đơn hàng. Gateway có thể giữ WebSession chứa OAuth2 Login Authentication và chuyển access token của người dùng đến downstream bằng `TokenRelay`.

Một cấu hình có vẻ chạy được nhưng không đủ an toàn là: “Gateway login thành công, chèn `X-User-Id` và `X-Tenant-Id`, downstream tin hai header đó và đọc bảng orders”. Nếu backend bị gọi trực tiếp, route bị đặt sai hoặc client cố ý tự gửi header, hệ thống có thể lộ dữ liệu xuyên tenant.

Bài học giải quyết ba câu hỏi:

1. **Danh tính đi qua ranh giới nào?** Browser session, OAuth2 principal, Bearer access token, service credential và signed identity assertion không phải một.
2. **Token relay thực chất chuyển cái gì?** `TokenRelay` gửi **access token đã được cấp** tới downstream; không tự ký lại token, không đổi audience/scope và không tự xác nhận tenant.
3. **Ai có quyền tin ai?** Mỗi điểm nhận trách nhiệm an ninh — gateway, downstream API, service kế tiếp và data layer — phải kiểm những điều kiện phù hợp với chính nó.

Sau bài này, bạn có thể thiết kế sơ đồ trust boundary, phân biệt ba mô hình OAuth2, triển khai TokenRelay WebFlux với OAuth2 Login, xác minh issuer/audience/tenant/scope tại downstream, nhận diện giả mạo identity headers, chạy Java 17 kiểm tra policy và xây test 302/401/403 xuyên tenant.

**Nguyên tắc:** authentication tại gateway **không thay thế** authentication và authorization của downstream. Route/hostname/header tenant do client cung cấp **chỉ là lựa chọn ngữ cảnh**, không là bằng chứng người dùng được phép vào tenant ấy.

## 2. Những loại thông tin cần phân biệt

| Thành phần | Ý nghĩa | Được dùng như thế nào |
| --- | --- | --- |
| `SESSION` cookie | Browser session của gateway, thường gắn `SecurityContext` | Dùng xác thực browser→gateway; **không** forward cookie này sang mọi backend |
| `OAuth2AuthenticationToken` | Authentication được tạo sau `oauth2Login()` | Gateway biết người dùng đã đăng nhập bằng ClientRegistration nào |
| `OAuth2AuthorizedClient` | Lưu `ClientRegistration` và access token, có thể có refresh token | Gateway OAuth2 Client quản lý; token relay có thể lấy access token từ đây |
| OAuth2 **access token** | Credential dùng gọi resource server | Có `aud`/scope/expiry; downstream tự xác minh |
| OIDC **ID Token** | Bằng chứng authentication dành cho OAuth2/OIDC client | Không thay access token gọi downstream |
| `client_credentials` token | Access token cấp cho service/client | Xác thực **service actor**, không mặc nhiên đại diện end user |
| `X-User-Id`, `X-Tenant-Id` | Header thông thường, dễ giả mạo | Chỉ là input nếu chưa có một trust contract riêng |
| `iss` | Issuer ký/phát access token | Phải thuộc allowlist và được xác minh |
| `sub` | Subject ID trong namespace issuer | Không tự unique xuyên nhiều issuer |
| `tenant_id` | Claim ứng dụng được IdP/authorization service phát | Chỉ tin **sau** JWT verification/introspection và khi đúng hợp đồng |
| `aud` | Audience/API nhận token | Downstream phải kiểm chứa identity/resource của chính mình |
| `scope`/`scp` | Các phạm vi quyền được cấp | Spring Security thường map thành `SCOPE_*`; chưa đủ thay kiểm ownership |

**OAuth2 Access Token là Bearer credential:** nếu bị lộ, bên khác có thể sử dụng nó trong giới hạn hiệu lực/binding của token. Vì vậy không đưa token vào URL, log, analytics, error response, trace headers hoặc external API không tin cậy.

### 2.1. Một JWT không tự chứng minh được điều gì chỉ bằng payload

Payload minh họa:

~~~json
{
  "iss": "https://idp-a.example/issuer",
  "sub": "user-123",
  "aud": ["orders-api"],
  "tenant_id": "tenant-a",
  "scope": "orders.read",
  "exp": 1790003600
}
~~~

Payload này **không phải access token thật đã ký**. Trước khi đưa `iss`/`tenant_id`/`scope` vào quyền, Spring Security phải xác minh JWS signature, trusted algorithm/issuer, thời gian `exp`/`nbf` và audience. Một claim có tên `tenant_id` nằm trong JSON user tự gửi hoặc JWT chưa verify **không có giá trị bảo mật**.

Nếu IdP phát **opaque token** thay vì JWT, downstream cần `ReactiveOpaqueTokenIntrospector` hoặc một validation mechanism đã được IdP hỗ trợ. Không tự xem opaque string là JWT vì nó có dấu chấm hay được gọi là “token”.

### 2.2. Tenant locator khác tenant authorization

Request:

~~~http
GET /tenant-b/api/data HTTP/1.1
Host: gateway.example.com
X-Tenant-Id: tenant-b
~~~

Đường dẫn và header nói **client muốn truy cập tenant-b**, chưa nói user thuộc tenant B. Quy tắc bảo mật cho mẫu bài:

~~~text
routeTenant is configured
AND verifiedJwt.iss == issuerMappedTo(routeTenant)
AND verifiedJwt.tenant_id == routeTenant
AND verifiedJwt.aud contains "orders-api"
AND verified authorities contain "SCOPE_orders.read"
AND requested object belongs to verified tenant/user
~~~

Nếu một user có nhiều tenant memberships, cần một membership source tin cậy và active-tenant policy; không thể khẳng định một claim `tenant_id` luôn đủ cho mọi mô hình SaaS.

## 3. Trust boundaries và kiểm tra tại từng ranh giới

~~~text
Browser       Edge / WAF         Gateway WebFlux        Orders API        Database
   |              |                   |                    |                 |
   | HTTPS +      |                   |                    |                 |
   | SESSION      |                   |                    |                 |
   |------------->|------------------>|                    |                 |
   |              |            oauth2Login user            |                 |
   |              |            OAuth2AuthorizedClient      |                 |
   |              |            TokenRelay=                 |                 |
   |              |                   |                    |                 |
   |              |                   | Authorization:     |                 |
   |              |                   | Bearer accessToken |                 |
   |              |                   |------------------->|                 |
   |              |                   |              JWT / introspection     |
   |              |                   |              iss, exp, aud           |
   |              |                   |              tenant, scope          |
   |              |                   |                    | tenant-scoped    |
   |              |                   |                    | query + ownership|
   |              |                   |                    |---------------->|
   |              |                   |                    |<----------------|
   |<-------------|<------------------|<-------------------|                 |
~~~

| Ranh giới | Kiểm gì? | Không được làm gì? |
| --- | --- | --- |
| Browser → Edge | TLS, canonical host, traffic controls, request size, forwarded-header sanitization | Tin `X-Forwarded-*` do Internet client tự gửi |
| Edge → Gateway | Trust proxy; OAuth2 Login/callback, WebSession, cookie Secure/HttpOnly/SameSite, CSRF | Cho raw external identity headers trở thành principal |
| Gateway → Orders | Fixed route URI, TLS/mTLS, token relay đúng access token, hạn chế outbound host | Truyền refresh token, ID Token hoặc Bearer đến user-controlled URL |
| Orders authentication | JWT signature/JWKS hoặc opaque introspection, issuer allowlist, `aud`, `exp`/`nbf` | Coi “đến từ private network” là đã authenticated |
| Orders authorization | Verified tenant claim + route tenant, issuer per tenant, scopes/roles | Dựa vào path/header tự khai để cấp quyền tenant |
| Orders → DB | Tenant predicate, row-level security hoặc membership/ownership | Chỉ lọc bằng object ID mà quên tenant |
| Orders → service thứ ba | Credential thích hợp cho audience mới, service identity/OBO và audit actor | Tự ý reuse mọi user access token cho tất cả microservice |
| Response → client | 401/403/302 đúng flow, không lộ secrets | Echo token hoặc raw JWT claims trong lỗi |

Mỗi ranh giới có thể có TLS/service identity riêng. Mạng nội bộ không phải tuyệt đối đáng tin: một service bị compromise hoặc một route direct-to-backend sẽ phá giả định “chỉ Gateway mới gọi”.

## 4. Ba mô hình chuyển credential — không dùng lẫn

### 4.1. Browser OAuth2 Login → TokenRelay user access token

~~~text
Browser -- SESSION cookie --> Gateway (oauth2Login)
                                  |
                                  | OAuth2AuthorizedClient của user
                                  | access token đã được IdP cấp
                                  v
                             TokenRelay=
                                  |
                                  | Authorization: Bearer <user access token>
                                  v
                         Orders Resource Server
                                  |
                           verify aud/iss/tenant/scope
~~~

Đây là use case được Spring Cloud Gateway Server WebFlux mô tả: `TokenRelay=` (không tham số) chuyển access token từ authenticated user OAuth2 Login. Browser không phải giữ access token trong JavaScript. Refresh token (nếu có) vẫn do Gateway OAuth2 Client quản lý, không gửi xuống Orders API.

**Điều kiện khó nhất:** IdP phải cấp access token **dành cho Orders**. Gateway login thành công không đồng nghĩa access token có `aud=orders-api`. Một access token chỉ dành cho UserInfo hay `gateway-api` phải bị Orders từ chối.

### 4.2. Machine/mobile gửi Bearer vào Gateway Resource Server

~~~text
Mobile --> Gateway: Authorization: Bearer token
                    |
             Gateway validates bearer token
                    |
        explicit delegation strategy:
        - forward only if downstream is valid audience
        - token exchange for downstream audience
        - or derive signed internal assertion
                    |
                    v
             Downstream validates again
~~~

Đây không phải mặc định cùng flow với `oauth2Login()`. `TokenRelay=` trong cấu hình OAuth2 Client không được hiểu máy móc là “cứ có incoming Bearer header là tự relay”. Nếu Gateway vừa là Resource Server vừa phải gọi downstream, cần xác định rõ cách forward/exchange dựa trên verified incoming Authentication, nơi nào lưu authorized client và token có audience nào.

Nếu chỉ copy header `Authorization` từ incoming request sang downstream **mà không kiểm token, tenant, route và audience**, gateway có thể trở thành forward proxy chuyển credential của kẻ tấn công.

### 4.3. `TokenRelay=service-client` khác user identity

~~~yaml
filters:
  - TokenRelay=service-client
~~~

Khi `service-client` là một `client_credentials` registration, token được cấp cho **service**. Downstream thấy service principal; không mặc nhiên biết người dùng Alice nào khởi phát request.

Nếu downstream cần thao tác “thay mặt Alice”, phải có mô hình delegation/OBO và audit tách **actor service** với **subject end user**. Chèn `X-User: Alice` bên cạnh token service không tự biến Alice thành chủ thể đã được xác thực.

### 4.4. Token exchange khi audience khác

Nếu gateway có token `aud=gateway-api` còn Orders yêu cầu `aud=orders-api`, có thể dùng **OAuth2 Token Exchange (RFC 8693)** nếu Authorization Server hỗ trợ:

~~~text
User token: aud=gateway-api
      |
Gateway authenticates token + user/tenant
      |
RFC 8693 exchange / on-behalf-of
      |
New access token: aud=orders-api; narrow scope=orders.read
      |
Orders verifies new signature, issuer, audience, tenant and scope
~~~

`TokenRelay` **không tự thực hiện** token exchange. Không tự sửa JWT payload `aud` hoặc ký token “giống IDP” bằng khóa của ứng dụng. Nếu IdP không hỗ trợ RFC 8693, phải thiết kế hợp đồng ủy quyền khác có xác minh rõ ràng hoặc thay token issuance policy.

## 5. Spring Cloud Gateway WebFlux TokenRelay trong thực tế

### 5.1. Route factory

Cú pháp chính thức trong Spring Cloud Gateway Server WebFlux:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders
              uri: http://localhost:9000
              predicates:
                - Path=/api/orders/**
              filters:
                - TokenRelay=
~~~

`TokenRelay=` lấy access token từ OAuth2 Login authenticated user nếu có authorized client phù hợp. Với registration cụ thể, có thể viết `TokenRelay=my-client-registration`. Java DSL tương đương:

~~~java
@Bean
RouteLocator routes(RouteLocatorBuilder builder) {
    return builder.routes()
            .route("orders", r -> r.path("/api/orders/**")
                    .filters(f -> f.tokenRelay())
                    .uri("http://localhost:9000"))
            .build();
}
~~~

Đây là hai **snippet thay thế nhau**; không đăng ký cùng route hai lần. `localhost:9000` chỉ dành cho local development, production cần HTTPS/mTLS/trusted service DNS và outbound restrictions.

### 5.2. Điều kiện factory hoạt động

- Spring Cloud Gateway Server **WebFlux** starter, không phải MVC Gateway.
- Spring Security OAuth2 Client dependency và ít nhất một ClientRegistration hợp lệ.
- `ReactiveClientRegistrationRepository` do Boot tạo từ `spring.security.oauth2.client.*`.
- Khi browser login, `oauth2Login()` đã hoàn tất, authorized client có access token.
- Token được phát cho đúng downstream audience, issuer, scope và tenant.
- `ReactiveOAuth2AuthorizedClientService` hoặc `ServerOAuth2AuthorizedClientRepository` lưu state theo đúng context.
- Nếu nhiều replicas, lưu ý default authorized client storage có thể là **in-memory**; yêu cầu production có thể cần shared secure store và coordination refresh.

### 5.3. TokenRelay không tự làm những việc nào?

`TokenRelay` không tự:

1. Đổi audience hoặc scope của access token.
2. Biến ID Token thành access token cho downstream.
3. Verify JWT thay cho mọi resource server đích.
4. Kiểm user có quyền truy cập tenant trong path.
5. Tạo signed identity header có trusted issuer.
6. Implement RFC 8693/token exchange.
7. Thu hồi access token đã phát ở IdP khi gateway logout.
8. Bảo đảm mọi 401 downstream dẫn đến refresh ngay mà không cần xử lý lỗi.
9. Tự phân biệt service token với end-user delegation cho audit.

Những giới hạn này phải được nêu trong architecture contract; tên “TokenRelay” dễ khiến người học tưởng gateway tạo ra một danh tính đã được tất cả downstream tin cậy.

## 6. Header spoofing và confused deputy

### 6.1. Chỉ chèn `X-User` vào downstream là chưa đủ

Request giả mạo:

~~~http
GET /tenant-b/api/orders HTTP/1.1
Host: gateway.example.com
X-User-Id: admin
X-Tenant-Id: tenant-b
~~~

Nếu backend tin hai header này mà không xác minh nguồn, client có thể giả admin. Nếu gateway chèn header đúng, attacker vẫn có thể tìm đường direct-to-backend hoặc lợi dụng một internal service khác. Cần **strip client-controlled identity headers** tại edge/gateway và dùng Bearer token hoặc **signed identity assertion** được downstream xác minh (issuer, signature, audience, expiry, tenant), kèm service-to-service TLS/mTLS/network policy khi cần.

**Đừng** tin một signed assertion chỉ vì được đặt trong header đặc biệt: downstream vẫn cần biết khóa nào hợp lệ, ai được phát assertion, audience của mình và TTL. Một số hệ thống có thể đặt trust ở service mesh/gateway với mTLS và workload identities, nhưng trust contract phải được thiết kế và kiểm thử — không được ngầm suy từ IP private.

### 6.2. Confused deputy

Gateway có service token `orders.admin` rộng, người dùng tenant A chỉ có `orders.read`. Nếu gateway gọi `/tenant-b/admin/export` bằng service token thay user mà downstream chỉ nhìn thấy service admin, đó có thể là **confused deputy** dẫn tới cross-tenant leak.

Giảm rủi ro bằng:

- User-delegated access token có scope và audience hẹp, hoặc token exchange/OBO.
- Không reuse privileged service token trên mọi user-facing route.
- Nếu service token bắt buộc, giữ verified actor + subject context, enforce delegation rights tại downstream.
- Kiểm tenant + object ownership/row isolation tại data layer.
- Audit actor service, subject user, tenant, action, correlation ID theo contract đáng tin.

### 6.3. Đừng forward cookies hoặc Authorization đến host tùy ý

Ví dụ anti-pattern:

~~~java
// KHÔNG DÙNG: URL đích đến từ request bên ngoài.
String target = exchange.getRequest()
        .getQueryParams().getFirst("target");
webClient.get().uri(target)
        .headers(headers -> headers.setBearerAuth(accessToken));
~~~

Đây chỉ là **snippet cảnh báo SSRF/token exfiltration**, không phải method độc lập. Gateway nên có route/backend allowlist, không đưa refresh token, session cookie và Authorization header vào log hoặc redirect ra domain không tin cậy. Tránh bật `setDefaultOAuth2AuthorizedClient(true)` trên một WebClient dùng cho mọi loại URL.

## 7. Multi-tenancy: xác minh issuer, audience, tenant và scope

### 7.1. Issuer trong JWT chưa verify chỉ là input chọn decoder

JWT có claim `iss` nhưng trước khi verify, attacker có thể sửa payload. `JwtIssuerReactiveAuthenticationManagerResolver` của Spring Security WebFlux có thể dựa vào `iss` để **chọn** `ReactiveAuthenticationManager`, nhưng lựa chọn phải dựa trên một **trusted issuer allowlist**. Manager được chọn phải verify chữ ký và claims để tạo authenticated principal.

~~~java
JwtIssuerReactiveAuthenticationManagerResolver resolver =
        JwtIssuerReactiveAuthenticationManagerResolver
                .fromTrustedIssuers(
                        "https://idp-a.example/issuer",
                        "https://idp-b.example/issuer");
~~~

Và dùng:

~~~java
.oauth2ResourceServer(oauth2 ->
        oauth2.authenticationManagerResolver(resolver))
~~~

Đây là **WebFlux snippets**, không phải code độc lập. Không tạo JWK URL động từ bất kỳ token `iss` nào, vì attacker có thể dựng một issuer do họ kiểm soát, dẫn đến xác thực sai hoặc SSRF.

### 7.2. Một token có issuer hợp lệ vẫn có thể sai tenant

Giả sử cả issuer A và B đều hợp lệ. Token A có thể được verify thành công bởi manager A, nhưng client gửi `/tenant-b/api/orders`. Nếu authorization chỉ dùng `authenticated()`, token A có thể vào route B. Do đó cần **so issuer đã xác minh, tenant claim, route tenant, scope và audience**, không chỉ danh sách issuer.

Mô hình ví dụ này giả định 1 tenant ↔ 1 issuer. Hệ thống có 1 issuer cho nhiều tenant phải chuyển sang membership/tenant claim validation phù hợp; hệ thống một tenant có nhiều issuers cần trust policy phức tạp hơn. Đừng tạo giả định 1-1 nếu business contract khác.

### 7.3. Audience được kiểm ở mỗi API

~~~json
{
  "iss": "https://idp-a.example/issuer",
  "sub": "employee-123",
  "tenant_id": "tenant-a",
  "aud": ["gateway-api"],
  "scope": "orders.read"
}
~~~

Token trên có issuer và scope trông đúng, nhưng **Orders Resource Server yêu cầu aud=orders-api**. Nếu audience validator từ chối token này ở authentication, status thường là **401**, không phải “Gateway login thất bại”. Cần IdP cấp access token đúng audience hoặc dùng token exchange.

### 7.4. Role và tenant membership không tự xuất hiện từ scope

`scope=orders.read` thường trở thành `SCOPE_orders.read`. Nhưng scope này chỉ nói một quyền khái quát được cấp cho token; không chứng minh user được phép đọc tất cả orders của tenant A hoặc tenant B. Endpoint vẫn phải kiểm tenant và object ownership. Không tự map mọi string `"admin"` thành `ROLE_ADMIN` mà không có IdP contract/allowlist.

## 8. Java 17 độc lập: kiểm policy sau khi token đã được xác minh

Ví dụ dưới đây là **chương trình Java thuần**, không cần Spring/IdP. Nó giả định một `VerifiedIdentity` đã được authentication layer xác minh. Chỉ kiểm logic issuer/tenant/audience/scope, **không dùng để parse JWT chưa verify**.

Tạo file `BoundaryDecisionDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public final class BoundaryDecisionDemo {
    enum Decision {
        ALLOW, UNAUTHENTICATED, UNKNOWN_ROUTE,
        UNTRUSTED_ISSUER, WRONG_AUDIENCE,
        TENANT_MISMATCH, FORBIDDEN
    }

    record VerifiedIdentity(
            String issuer,
            String tenant,
            Set<String> audiences,
            Set<String> authorities) {
    }

    private static final Map<String, String> ISSUERS = Map.of(
            "tenant-a", "https://idp-a.example/issuer",
            "tenant-b", "https://idp-b.example/issuer");

    private BoundaryDecisionDemo() {
    }

    static Decision decide(
            String requestedTenant, VerifiedIdentity verified) {

        String expectedIssuer = ISSUERS.get(requestedTenant);
        if (expectedIssuer == null) {
            return Decision.UNKNOWN_ROUTE;
        }
        if (verified == null) {
            return Decision.UNAUTHENTICATED;
        }
        if (!expectedIssuer.equals(verified.issuer())) {
            return Decision.UNTRUSTED_ISSUER;
        }
        if (!verified.audiences().contains("orders-api")) {
            return Decision.WRONG_AUDIENCE;
        }
        if (!requestedTenant.equals(verified.tenant())) {
            return Decision.TENANT_MISMATCH;
        }
        if (!verified.authorities().contains("SCOPE_orders.read")) {
            return Decision.FORBIDDEN;
        }
        return Decision.ALLOW;
    }

    public static void main(String[] args) {
        VerifiedIdentity good = new VerifiedIdentity(
                "https://idp-a.example/issuer", "tenant-a",
                Set.of("orders-api"), Set.of("SCOPE_orders.read"));

        VerifiedIdentity wrongTenant = new VerifiedIdentity(
                good.issuer(), "tenant-b",
                good.audiences(), good.authorities());

        VerifiedIdentity wrongAudience = new VerifiedIdentity(
                good.issuer(), good.tenant(),
                Set.of("gateway-api"), good.authorities());

        VerifiedIdentity noScope = new VerifiedIdentity(
                good.issuer(), good.tenant(),
                good.audiences(), Set.of());

        VerifiedIdentity wrongIssuer = new VerifiedIdentity(
                "https://untrusted.example/issuer", good.tenant(),
                good.audiences(), good.authorities());

        System.out.println("good_a="
                + decide("tenant-a", good));
        System.out.println("a_token_on_b="
                + decide("tenant-b", good));
        System.out.println("wrong_tenant_claim="
                + decide("tenant-a", wrongTenant));
        System.out.println("wrong_audience="
                + decide("tenant-a", wrongAudience));
        System.out.println("missing_scope="
                + decide("tenant-a", noScope));
        System.out.println("unknown_issuer="
                + decide("tenant-a", wrongIssuer));
        System.out.println("no_principal="
                + decide("tenant-a", null));
        System.out.println("unknown_route="
                + decide("tenant-x", good));
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac BoundaryDecisionDemo.java
java BoundaryDecisionDemo
~~~

**Stdout xác định theo source:**

~~~text
good_a=ALLOW
a_token_on_b=UNTRUSTED_ISSUER
wrong_tenant_claim=TENANT_MISMATCH
wrong_audience=WRONG_AUDIENCE
missing_scope=FORBIDDEN
unknown_issuer=UNTRUSTED_ISSUER
no_principal=UNAUTHENTICATED
unknown_route=UNKNOWN_ROUTE
~~~

Các quyết định trên **không phải mã HTTP**. Trong ứng dụng thật, lỗi signature/issuer/audience ở authentication thường là 401; authenticated user thiếu quyền/không đúng tenant thường 403; unknown route có thể trả 404 theo policy. Mô hình này không thay thế JWT decoder, OIDC token exchange hoặc database membership checks.

## 9. Ví dụ tích hợp: hai ứng dụng Spring Boot WebFlux

Ta xây hai Maven projects chạy local:

- `gateway-app` — Spring Boot **4.1.2**, Spring Cloud **2025.1.2**, Spring Cloud Gateway Server WebFlux, OAuth2 Client Login + TokenRelay, cổng **8080**.
- `orders-service` — Spring Boot **4.1.2**, Spring Security reactive Resource Server JWT, cổng **9000**, tự verify hai issuers với audience `orders-api` và tenant-aware policy.

Spring Cloud 2025.1.2 hỗ trợ Spring Boot 4.1.x. Spring Boot 4 đổi tên starter OAuth2 Client/Resource Server sang `spring-boot-starter-security-oauth2-client` và `spring-boot-starter-security-oauth2-resource-server`; không lấy tên legacy từ một đoạn tài liệu Gateway cũ rồi cho rằng đó là starter chuẩn của Boot 4.

**Điều kiện bên ngoài:** cần IdP thật có OIDC discovery HTTPS, hai OAuth2 ClientRegistrations và JWT access tokens dành cho `orders-api`. Đây là source cấu hình ứng dụng có thể tích hợp, **không phải mock IdP tự khởi chạy**. Phần Java thuần ở trên hoàn toàn chạy không cần IdP.

### 9.1. Gateway pom.xml

Tạo `gateway-app/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>gateway-app</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2025.1.2</spring-cloud.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-oauth2-client</artifactId>
        </dependency>
    </dependencies>
    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>${spring-cloud.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.2. Gateway application.yml

Tạo `gateway-app/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: tenant-a-orders
              uri: http://localhost:9000
              predicates:
                - Path=/tenant-a/api/**
              filters:
                - RemoveRequestHeader=Authorization
                - RemoveRequestHeader=X-User-Id
                - RemoveRequestHeader=X-Tenant-Id
                - TokenRelay=
            - id: tenant-b-orders
              uri: http://localhost:9000
              predicates:
                - Path=/tenant-b/api/**
              filters:
                - RemoveRequestHeader=Authorization
                - RemoveRequestHeader=X-User-Id
                - RemoveRequestHeader=X-Tenant-Id
                - TokenRelay=

  security:
    oauth2:
      client:
        registration:
          corp-a:
            provider: issuer-a
            client-id: ${A_CLIENT_ID}
            client-secret: ${A_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,orders.read
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
          corp-b:
            provider: issuer-b
            client-id: ${B_CLIENT_ID}
            client-secret: ${B_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,orders.read
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          issuer-a:
            issuer-uri: ${A_ISSUER}
          issuer-b:
            issuer-uri: ${B_ISSUER}
~~~

Khi lưu bài, dấu `$` trong YAML được chuyển thành dấu dollar thông thường của **Spring property placeholder** (`$...`). Những biến này cần được cung cấp từ môi trường/secret manager; không phải credentials giả định có sẵn.

- `TokenRelay=` lấy access token của OAuth2 Login session tương ứng user hiện tại.
- `RemoveRequestHeader=Authorization` trước relay tránh chuyển mù quáng một header do client gắn vào; OAuth2 Client filter sau đó chèn token nếu resolve được.
- Các identity headers do client tự gửi cũng được loại bỏ. Orders không dựa vào các header này.
- Giữ nguyên path `/tenant-a/api/**` hoặc `/tenant-b/api/**`; downstream dùng path làm requested tenant.
- Cả hai route đi về fixed URI `http://localhost:9000` chỉ dành cho local. Production cần HTTPS/mTLS, network policy và backend allowlist.
- Gateway **không tự đổi user login provider theo path**. User đăng nhập corp-a có thể thử path tenant-b; downstream phải từ chối.
- `ClientRegistration` cần IdP có issuer metadata thật và callback đăng ký chính xác.

### 9.3. GatewayApplication.java

Tạo `gateway-app/src/main/java/com/example/gateway/GatewayApplication.java`:

~~~java
package com.example.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@SpringBootApplication
@EnableWebFluxSecurity
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain gatewaySecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

`oauth2Login()` quản lý redirect, state/callback và tạo authenticated user. OAuth2AuthorizedClient có access token; route TokenRelay gắn Bearer cho downstream. Không tắt CSRF toàn hệ thống chỉ vì gateway cung cấp JSON: cookie-backed browser requests với POST/PUT/DELETE vẫn cần CSRF threat model rõ ràng.

### 9.4. Orders pom.xml

Tạo `orders-service/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>orders-service</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-security-oauth2-resource-server</artifactId>
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
~~~

Đây là **Resource Server** nhận Bearer, không cần OAuth2 ClientRegistration để làm OAuth2 Login.

### 9.5. Orders application.properties

Tạo `orders-service/src/main/resources/application.properties`:

~~~properties
server.port=9000
tenants.a.issuer=${A_ISSUER}
tenants.b.issuer=${B_ISSUER}
orders.audience=orders-api
~~~

Issuer phải là HTTPS IdP thật mà bạn tin cậy. Token do IdP cấp phải mang `aud=orders-api` và `tenant_id=tenant-a` hoặc `tenant-b` theo hợp đồng. Nếu provider không cấp tenant claim, code minh họa chủ động từ chối route thay vì đoán từ path.

### 9.6. OrdersApplication.java — verify ở từng ranh giới

Tạo `orders-service/src/main/java/com/example/orders/OrdersApplication.java`:

~~~java
package com.example.orders;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            @Value("${tenants.a.issuer}") String issuerA,
            @Value("${tenants.b.issuer}") String issuerB,
            @Value("${orders.audience}") String audience) {

        Map<String, ReactiveAuthenticationManager> managers = Map.of(
                issuerA, jwtManager(issuerA, audience),
                issuerB, jwtManager(issuerB, audience));

        var resolver = new JwtIssuerReactiveAuthenticationManagerResolver(
                issuer -> Mono.justOrEmpty(managers.get(issuer)));

        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/tenant-a/api/data")
                                .access(tenantAccess("tenant-a", issuerA))
                        .pathMatchers("/tenant-b/api/data")
                                .access(tenantAccess("tenant-b", issuerB))
                        .anyExchange().denyAll())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.authenticationManagerResolver(resolver))
                .build();
    }

    private static ReactiveAuthenticationManager jwtManager(
            String issuer, String audience) {

        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withIssuerLocation(issuer)
                        .build();

        OAuth2TokenValidator<Jwt> audValidator =
                jwt -> jwt.getAudience().contains(audience)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error("invalid_token",
                                        "Wrong audience for orders", null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        JwtValidators.createDefaultWithIssuer(issuer),
                        audValidator));

        return new JwtReactiveAuthenticationManager(decoder);
    }

    private static ReactiveAuthorizationManager<AuthorizationContext>
            tenantAccess(String expectedTenant, String expectedIssuer) {

        return (authentication, context) ->
                authentication.map(auth -> {
                    if (!(auth instanceof JwtAuthenticationToken jwtAuth)
                            || !auth.isAuthenticated()) {
                        return new AuthorizationDecision(false);
                    }

                    Jwt jwt = jwtAuth.getToken();

                    boolean issuerOk = jwt.getIssuer() != null
                            && expectedIssuer.equals(
                                    jwt.getIssuer().toString());

                    boolean tenantOk = expectedTenant.equals(
                            jwt.getClaimAsString("tenant_id"));

                    boolean scopeOk = auth.getAuthorities().stream()
                            .map(GrantedAuthority::getAuthority)
                            .anyMatch("SCOPE_orders.read"::equals);

                    return new AuthorizationDecision(
                            issuerOk && tenantOk && scopeOk);
                }).defaultIfEmpty(new AuthorizationDecision(false));
    }

    @RestController
    static class OrdersController {

        @GetMapping(value = {
                "/tenant-a/api/data",
                "/tenant-b/api/data"
        }, produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> data(
                @AuthenticationPrincipal Jwt jwt) {

            return Mono.just(Map.of(
                    "result", "ORDERS_OK",
                    "tenant", jwt.getClaimAsString("tenant_id")));
        }
    }
}
~~~

**Điều gì được kiểm ở đâu?**

- `JwtIssuerReactiveAuthenticationManagerResolver` đọc `iss` như **đầu vào chọn manager**. `managers` chỉ có hai trusted issuer; không gọi metadata của rogue issuer bất kỳ.
- `NimbusReactiveJwtDecoder` lấy trusted JWKS/keys và verify chữ ký. `JwtValidators.createDefaultWithIssuer` xác minh issuer và timestamp. `audValidator` đảm bảo token dành cho `orders-api`; lỗi audience thường là **401**.
- `tenantAccess` là một `ReactiveAuthorizationManager` sau authentication. Nó kiểm issuer A/B đúng route, `tenant_id` trong JWT đã verify, và `SCOPE_orders.read`. Nếu user authenticated nhưng sai tenant/scope, thường là **403**.
- `anyExchange().denyAll()` từ chối mọi route chưa được liệt kê; không có “default permitAll”.
- Controller đọc `@AuthenticationPrincipal Jwt` của Security Context; không lấy identity từ `X-User-Id` hay `X-Tenant-Id`.
- Khi triển khai database thật, vẫn phải kiểm order ownership và query tenant-scoped. Demo trả kết quả tĩnh nên chỉ minh họa authentication/authorization boundary.

**Lưu ý về startup:** `withIssuerLocation(issuer)` cần trusted issuer metadata/JWK Set; tùy implementation/phiên bản có thể truy vấn IdP trong quá trình tạo decoder, nên đừng mong app chạy end-to-end với hai URL ví dụ. Với production nhiều issuers, có thể tạo managers lazily hoặc chỉ rõ trusted JWK Set URI; vẫn phải giữ issuer/audience validators.

### 9.7. Vì sao dùng resolver thay vì hai JWT chains match-all?

Hai `SecurityWebFilterChain` cùng match mọi request dễ có thứ tự không mong muốn. Resolver chọn manager theo trusted issuer trong một chain, rồi policy dựa theo **route tenant**. Khi cần split browser/API routes, dùng security matcher/order có chủ đích; không trộn Servlet `HttpSecurity` vào WebFlux.

## 10. Chạy demo với IdP đã provision

### 10.1. Chuẩn bị

Bạn cần:

1. JDK 17+, Maven hoặc wrapper.
2. Hai OIDC issuers HTTPS thực và có JWT verification keys.
3. OAuth2 client registrations `corp-a`, `corp-b` với confidential client credentials và redirect URI:
   - `http://localhost:8080/login/oauth2/code/corp-a`
   - `http://localhost:8080/login/oauth2/code/corp-b`
4. Access token thật có `aud=orders-api`, `scope=orders.read` và `tenant_id` đúng schema.
5. Gateway cổng 8080, Orders cổng 9000, proxy local HTTP **chỉ dùng dev**.
6. Production: HTTPS + trusted proxy/forwarded headers, secure cookie, mTLS/network policy nếu cần.

Không có IdP thực, token thật và callback registration thì bạn chỉ chạy được `BoundaryDecisionDemo` offline; không nên tuyên bố đã hoàn thành test login/OAuth2 protocol.

### 10.2. Orders Service

Trong shell Bash, ở thư mục `orders-service`:

~~~bash
export A_ISSUER='https://real-idp-a.example/issuer'
export B_ISSUER='https://real-idp-b.example/issuer'
./mvnw clean package
./mvnw spring-boot:run
~~~

Đây là **giá trị ví dụ**; thay bằng issuer thực. Nếu không có Maven wrapper dùng `mvn`. Với PowerShell dùng `$env:A_ISSUER="..."` và `.\mvnw.cmd spring-boot:run`.

### 10.3. Gateway

Trong terminal khác, thư mục `gateway-app`:

~~~bash
export A_CLIENT_ID='gateway-client-a'
export A_CLIENT_SECRET='secret-from-idp-a'
export A_ISSUER='https://real-idp-a.example/issuer'

export B_CLIENT_ID='gateway-client-b'
export B_CLIENT_SECRET='secret-from-idp-b'
export B_ISSUER='https://real-idp-b.example/issuer'

./mvnw clean package
./mvnw spring-boot:run
~~~

Không commit secret thật vào Git hay tài liệu, dùng secret manager cho production. Client registrations phải được IdP cho phép nhận **access token dành cho orders-api**, không chỉ ID Token/OIDC userinfo.

### 10.4. Browser tenant A

Trong browser profile A:

1. Mở `http://localhost:8080/oauth2/authorization/corp-a`.
2. Đăng nhập IdP A và hoàn thành callback; Gateway lưu WebSession.
3. Mở `http://localhost:8080/tenant-a/api/data`.
4. Gateway dùng `TokenRelay=` chuyển access token từ authorized client sang Orders.
5. Orders verify chữ ký/issuer/audience, kiểm tenant và scope; nếu hợp lệ trả **200** với JSON:

~~~json
{
  "result": "ORDERS_OK",
  "tenant": "tenant-a"
}
~~~

6. Trong **cùng profile**, mở `/tenant-b/api/data`: token A không phù hợp issuer/tenant B nên Orders **từ chối**, thường **403**.
7. Dùng **browser profile B độc lập** và login qua `corp-b` để test tenant B.

Nếu IdP A phát token có `aud=gateway-api` thay vì `orders-api`, Orders từ chối **401** — đây là đúng policy. Nếu token thiếu `SCOPE_orders.read`, Orders từ chối **403**. Không tự bỏ audience hoặc tenant check chỉ để demo trả 200.

### 10.5. Kiểm thử trực tiếp Resource Server

Trong môi trường local/trusted test khi có token thật:

~~~bash
curl -i -H "Authorization: Bearer $TENANT_A_ACCESS_TOKEN" \
  http://localhost:9000/tenant-a/api/data

curl -i -H "Authorization: Bearer $TENANT_A_ACCESS_TOKEN" \
  http://localhost:9000/tenant-b/api/data
~~~

Request đầu có thể 200 nếu đầy đủ claims; request thứ hai phải bị từ chối. Khi không có token, backend phải không tự tin header do caller đưa vào. **Không** đưa token thật vào script được commit, log hoặc terminal transcript công khai.

### 10.6. Curl tới authorization endpoint không phải login hoàn tất

~~~bash
curl -i http://localhost:8080/oauth2/authorization/corp-a
~~~

Lệnh thường cho thấy redirect tới IdP, nhưng `curl` không tự hoàn tất Authorization Code, state/nonce, cookie, callback và token exchange. Cần browser profile hoặc một OIDC integration test harness đầy đủ.

## 11. Kiểm thử ma trận từng ranh giới

| Tình huống | Expected behavior |
| --- | --- |
| Browser anonymous gọi Gateway route private | Redirect login 302 (browser flow) |
| Browser login A, gọi route A đúng claim | Relay token A, downstream 200 |
| Browser login A, gọi route B | Downstream 403 do sai issuer/tenant route |
| Browser login B, gọi route B | Downstream 200 khi claim hợp lệ |
| Client giả `X-User-Id: admin` | Header bị strip/ignored; không cấp admin |
| Client giả `X-Tenant-Id: tenant-b` với token A | Không có quyền tenant B |
| Không có Bearer tới Orders private endpoint | 401 |
| JWT signature sai hoặc key không thuộc issuer | 401 |
| Issuer ngoài allowlist | 401; không truy vấn JWKS issuer lạ |
| JWT `aud=gateway-api` | 401 tại Orders |
| JWT expired hoặc `nbf` tương lai | 401 |
| Token hợp lệ nhưng thiếu `orders.read` | 403 |
| Token hợp lệ nhưng `tenant_id` khác path | 403 |
| Token đúng tenant/scope nhưng order ID thuộc user khác | Business/data policy phải deny |
| Backend bị gọi bypass Gateway | Vẫn tự xác minh Bearer; không tin private IP |
| Route target do attacker kiểm soát | Gateway không được relay token tới đó |
| TokenRelay dùng service client_credentials | Downstream hiểu đó là service actor |
| Access token bị revoke/logout | Cần token lifecycle policy riêng, không suy cookie logout tự revoke |
| JWT ký bằng key mới | JWKS refresh/rotation theo policy, không bỏ signature |
| Downstream 401/403 | Phân biệt authentication vs authorization; không retry vô hạn |
| Gateway thiếu OAuth2AuthorizedClient | Không tự tạo fake user/token |
| Public API JSON và browser login cùng gateway | Chọn entry point/chain cho 401 vs 302 |

### 11.1. WebTestClient không chứng minh JWT signature

Spring Security Test reactive có `mockJwt()` để test authorization. Ví dụ snippet:

~~~java
// Test snippet: cần WebTestClient đã cấu hình SecurityMockServerConfigurers.
webTestClient.mutateWith(mockJwt()
        .jwt(jwt -> jwt.claim("tenant_id", "tenant-a"))
        .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders.read")))
        .get().uri("/tenant-a/api/data")
        .exchange()
        .expectStatus().isOk();
~~~

Đây **không phải class JUnit độc lập**. `mockJwt()` đưa Authentication giả, thường bypass JWT decoder, nên **không kiểm** signature/`aud`/issuer JWKS. Phải có test token ký bằng private key test + fake OIDC issuer và thực sự chạy resolver/decoder. Với Gateway TokenRelay, test thêm fake OAuth2 Login/AuthorizedClient và HTTP mock downstream để kiểm Bearer header được gắn đúng, spoofed headers bị loại.

### 11.2. Test với hai browser profiles

Dùng browser profile A và B tách cookies/local storage, không dùng cùng OAuth2 session. Sau login A:

- Đối chiếu network: browser chỉ gửi `SESSION` tới Gateway, **không** cần tự đưa refresh token vào browser.
- Gateway outbound request tới Orders có Bearer access token, không có raw session cookie cần thiết cho Orders.
- Headers client-controlled `X-User-Id`/`X-Tenant-Id` không quyết định Authentication ở Orders.
- Token A trên route B phải bị deny; đây là test quan trọng nhất của parent topic “Gateway và nhiều tenant”.

### 11.3. Test failure và token lifecycle

Nếu downstream trả 401 `invalid_token`, gateway phải có chiến lược phát hiện stale authorized client, refresh/re-login và failure handling phù hợp. `ServerOAuth2AuthorizedClientExchangeFilterFunction` có failure handler nhưng **hành vi tùy constructor**; đừng giả định Gateway TokenRelay tự thực hiện mọi cleanup/retry. Nếu downstream trả 403 thiếu scope, refresh token không tự tạo thêm quyền. Không dùng `retryWhen(Retry.indefinitely())`; các POST có side effect cần idempotency contract trước khi cho retry.

## 12. HTTP status và security semantics

| Status | Nơi thường phát | Ý nghĩa |
| --- | --- | --- |
| 302 | Gateway `oauth2Login()` | Browser anonymous được redirect login |
| 401 | Resource Server JWT/opaque authentication | Missing/invalid/expired/wrong-audience Bearer |
| 403 | Gateway hoặc Orders authorization | Authenticated nhưng thiếu scope, tenant hoặc membership |
| 404 | Gateway route hoặc business lookup | Route không tồn tại; có thể dùng để không tiết lộ tài nguyên |
| 429 | Edge/Gateway/Orders/IdP | Rate limit; không suy token bị revoke |
| 502/503 | Gateway/Orders/upstream/IdP outage | Lỗi hạ tầng, không phải user thiếu role |

Một app phục vụ browser session và API mobile cùng lúc có thể cần **hai security chains/entry points** có matchers rõ để mobile nhận JSON 401 thay vì redirect HTML login. Đừng copy cấu hình `oauth2Login()` cho một backend API chỉ nhận Bearer.

## 13. Những bẫy đặc biệt của nhiều tenant

### 13.1. Tenant không phải lúc nào bằng issuer

Một issuer có thể phát token cho nhiều tenants; một tenant cũng có thể tin nhiều IdPs. Mẫu demo cố tình dùng 1:1 để dễ kiểm tra. Khi product có membership khác:

- Tách `issuer allowlist` và `tenant membership policy`.
- Kiểm active tenant được chọn và quyền user tại tenant đó.
- Liên kết identity bằng `issuer + subject` hoặc stable internal user ID đã kiểm chứng.
- Đừng gộp theo email hoặc một `sub` không kèm issuer.
- Cache permission theo đủ tenant+issuer+subject+audience, có TTL/revocation contract.

### 13.2. IDOR sau khi tenant check pass

Token A hợp lệ với route A không có nghĩa được phép đọc order của **mọi user** trong tenant A. Repository phải query theo verified tenant và object ownership/membership, chẳng hạn `WHERE tenant_id = :tenant AND order_id = :id`, rồi kiểm quyền đọc theo account/team/role. Không lấy `tenant_id` trong JSON body làm filter duy nhất.

### 13.3. JWT nhiều audiences tăng blast radius

Một token có audience cho gateway, Orders, Billing và Admin làm tăng phạm vi nếu token bị lộ. Prefer narrow audience và scoped token, đổi token khi qua boundary nếu cần. Audience đúng ở downstream là **check bắt buộc**, không phải “tùy chọn tối ưu”.

### 13.4. Logout không tự revoke downstream token

Khi Gateway xóa WebSession, browser không thể tiếp tục sử dụng session đó, nhưng access token đã được phát trước đây có thể còn hợp lệ với Orders tới khi `exp`/revocation. Với JWT local verify, Orders không tự thấy sự kiện logout. Với yêu cầu thu hồi sớm, cần short TTL, introspection, denylist, session/token version hoặc online policy được thiết kế riêng.

### 13.5. Một service token rộng không thể thay mọi end-user token

Gateway có service client_credentials token với scope rộng không được ngầm biến thành quyền người dùng. Nếu cần làm thay user, phải có delegation protocol/OBO, actor/subject audit, tenant isolation và policy downstream. Không chỉ thêm header `X-User` vào service Bearer.

## 14. Bảo mật và vận hành production

### 14.1. TLS và Forwarded headers

- TLS/HTTPS từ client tới edge/gateway; backend HTTPS/mTLS nếu threat model yêu cầu.
- Chỉ tin `Forwarded`/`X-Forwarded-Proto`/`X-Forwarded-Host` từ proxy do operator quản lý và đã strip external header.
- Không dùng request `Host` chưa normalize làm issuer/JWKS URL hoặc redirect URI tùy ý.
- Restrict backend network policy để giảm bypass Gateway.
- Cookie browser gateway cần `Secure`, `HttpOnly`, `SameSite` phù hợp; giữ CSRF cho unsafe cookie-backed requests.
- CORS không thay thế authentication/authorization, không mở credentialed CORS cho mọi origin.

### 14.2. OAuth2AuthorizedClient storage và rotation

TokenRelay có thể dùng store in-memory mặc định khi chạy một instance. Multi-node yêu cầu đánh giá session persistence, secure shared storage, refresh token rotation concurrency, outage và cleanup. Store có thể chứa refresh token/secret, phải mã hóa và phân quyền đọc. Không log `Authorization` hoặc raw JWT/ID Token/userinfo.

### 14.3. Tác động của key rotation và token revocation

Resource Server JWT cache trusted public keys. Key rotation cần JWKS refresh hợp lệ; không tắt signature check khi gặp unknown `kid`. JWT local có thể tiếp tục accept token chưa hết hạn sau revoke nếu không có online status check. Audit event/permission change phải có SLA. Với opaque, introspection endpoint trên critical path và có network failure/caching tradeoffs.

### 14.4. Rate limiting và tenant fairness

Gateway/Orders phải chống request burst, malformed tokens và authentication manager discovery storm. Đừng gọi untrusted issuer JWKS từ token. Theo dõi QPS/latency/401/403 theo các **tenant IDs đã allowlist hoặc bounded-cardinality labels**, không dùng raw bearer subject/token trong metric tag. Hạn chế một tenant gây cạn tài nguyên của toàn cụm.

## 15. Checklist áp dụng

1. Đã xác định ai phát, ai giữ và ai dùng access token tại từng boundary.
2. OAuth2 Login browser cookie không bị forward bừa tới downstream.
3. TokenRelay chuyển đúng access token, không ID Token/refresh token.
4. Gateway route target cố định/allowlisted, outbound HTTPS/mTLS đúng policy.
5. Không tin `X-User`/`X-Tenant` từ external client; strip hoặc dùng signed assertion có xác minh.
6. Downstream tự xác minh JWT/introspection; không phụ thuộc hoàn toàn Gateway.
7. Trusted issuer allowlist được quản lý server-side, không tự lấy JWKS từ `iss` bất kỳ.
8. Downstream kiểm `aud` dành cho chính API, không chỉ issuer/scope.
9. Route tenant khớp issuer/tenant claim/membership được xác minh.
10. Scope/role đủ, object ownership/row isolation ở database.
11. Service token khác user token; dùng token exchange/OBO khi cần delegation.
12. Không lộ access/refresh token, client secret, raw JWT claims trong log.
13. Browser, machine API và downstream errors có 302/401/403 đúng hợp đồng.
14. Có test cross-tenant, spoofed headers, wrong-audience, unknown issuer, expired, missing scope và bypass gateway.
15. Có kế hoạch token expiry/revocation/logout, IdP/JWKS outage và refresh rotation.
16. Với nhiều replicas có shared/secure state theo nhu cầu và kiểm concurrency.
17. Không trộn Servlet `HttpSecurity`/Gateway MVC API với `ServerHttpSecurity`/Gateway Server WebFlux.
18. Security review khi thêm tenant, route, issuer hoặc microservice mới.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Gateway đã OAuth2 Login thành công thì Orders có cần xác minh access token không?

**Đáp án:** Có. Orders là boundary khác, cần issuer/signature/exp/audience/scope/tenant và data ownership của chính mình.

**Câu 2.** `TokenRelay=` tự đổi `aud=gateway-api` thành `aud=orders-api` không?

**Đáp án:** Không. Cần IdP cấp đúng access token hoặc token exchange/OBO theo protocol được hỗ trợ.

**Câu 3.** Client gửi `X-Tenant-Id: tenant-b` thì có được vào tenant B?

**Đáp án:** Không. Header/path chỉ là lựa chọn tenant, phải khớp verified identity/membership và policy.

**Câu 4.** `TokenRelay=service-client` với client_credentials đại diện user Alice không?

**Đáp án:** Không mặc định. Nó đại diện service principal, cần delegation/actor semantics riêng nếu thao tác thay user.

**Câu 5.** Vì sao issuer trong JWT có thể được đọc trước verify mà vẫn không được tin?

**Đáp án:** Nó chỉ dùng **chọn manager trong allowlist**; manager phải verify signature/iss/exp/aud trước khi trao authority.

**Câu 6.** Token A đúng signature có thể vào route tenant B không?

**Đáp án:** Không theo policy. Issuer được phép cho tenant B, tenant claim và membership phải khớp route B.

**Câu 7.** Vì sao token đúng tenant và scope vẫn có thể không được đọc một order cụ thể?

**Đáp án:** Order có thể thuộc user/team khác. Cần kiểm object-level authorization và tenant scoped database query.

**Câu 8.** `mockJwt()` chứng minh điều gì?

**Đáp án:** Kiểm được HTTP authorization với Authentication giả; không chứng minh JWT cryptographic verification hoặc end-to-end token relay.

**Câu 9.** Xóa Gateway session có tự revoke mọi JWT ở Orders không?

**Đáp án:** Không. JWT local có thể còn hợp lệ đến exp; cần revocation policy khác nếu yêu cầu.

**Câu 10.** Khi downstream 403 vì thiếu scope, có nên refresh token vô hạn?

**Đáp án:** Không. Refresh không tự cấp thêm quyền và có thể tạo retry storm. Phân loại lỗi và điều chỉnh scope/authorization contract.

## 17. Tài liệu chính thức

- [Spring Cloud Gateway WebFlux — TokenRelay GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html)
- [Spring Cloud Gateway WebFlux — Spring Security Integration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/spring-security.html)
- [Spring Cloud Gateway — Server WebFlux Starter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/starter.html)
- [Spring Cloud — Spring Boot Release Train Compatibility](https://spring.io/projects/spring-cloud/)
- [Spring Security — Reactive OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html)
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html)
- [Javadoc — JwtIssuerReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html)
- [Javadoc — JwtReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtReactiveAuthenticationManager.html)
- [Javadoc — NimbusReactiveJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html)
- [Javadoc — ServerOAuth2AuthorizedClientExchangeFilterFunction](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html)
- [Spring Boot 4 Migration — OAuth2 Security Starter Names](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8693 — OAuth2 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 9068 — JWT Profile for OAuth2 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
