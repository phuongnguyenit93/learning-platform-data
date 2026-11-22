# Đăng ký grant token-exchange cho client được ủy quyền

## 1. Bài toán: không phải client nào cũng được phép đổi token

Trong chương **Token Exchange** của mô-đun **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, chúng ta tìm hiểu cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành Authorization Server dựa trên **Spring Security**, **Spring Authorization Server** và **Spring Boot**.

Giả sử người dùng Alice đăng nhập vào `orders-web` để xem đơn hàng. Ứng dụng này nhận access token cho API đơn hàng, rồi gọi dịch vụ `orders-aggregator`. Dịch vụ aggregator cần gọi tiếp `reports-api` để tổng hợp báo cáo, nhưng access token ban đầu có audience dành cho API thứ nhất, không nên được chuyển nguyên vẹn đến mọi dịch vụ khác.

**OAuth 2.0 Token Exchange (RFC 8693)** cho phép một OAuth client gửi **subject token** tới Token Endpoint và, nếu được Authorization Server chấp thuận, nhận **token mới** phù hợp hơn với target, audience, scope và ngữ cảnh ủy quyền.

Tuy nhiên, đây là năng lực nhạy cảm: nếu mọi client đều có thể gửi một token nhặt được và đổi nó thành token có audience rộng hơn, Token Exchange có thể trở thành đường vòng để chiếm quyền. Vì thế cần hai lớp bảo vệ:

1. **Registration:** chỉ client được đăng ký grant `urn:ietf:params:oauth:grant-type:token-exchange` mới được thực hiện luồng.
2. **Authorization policy cho từng exchange:** sau khi xác thực client và kiểm tra subject token, server chỉ cấp token nếu mối quan hệ client–subject–target–scope–actor được chính sách cho phép.

**Đăng ký grant là điều kiện cần, không phải giấy phép đổi mọi token sang mọi audience.**

### Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

- Phân biệt client gửi exchange request, chủ thể trong `subject_token`, actor và Resource Server đích.
- Đăng ký grant token exchange bằng `RegisteredClient` và `AuthorizationGrantType.TOKEN_EXCHANGE`.
- Hiểu vai trò `RegisteredClientRepository`, Token Endpoint và các converter/provider trong Spring Authorization Server.
- Xác định các điều kiện bảo mật bắt buộc ngoài việc client có grant.
- Gửi request RFC 8693, đọc response và nhận diện những lỗi thường gặp.
- Thiết kế chính sách allowlist, scope downscoping, audience restriction và kiểm thử âm tính.
- Phân biệt hỗ trợ xử lý token exchange của framework với **ủy quyền delegation/impersonation của nghiệp vụ**.

## 2. Bốn danh tính/thành phần cần phân biệt

| Thành phần | Ví dụ | Vai trò trong lần exchange |
| --- | --- | --- |
| **Authenticated requesting client** | `orders-aggregator` | Client gọi `/oauth2/token` và phải được phép dùng grant |
| **Subject token** | Access token trước đó của Alice | Bằng chứng về subject/ngữ cảnh mà client muốn đem trao đổi |
| **Actor token**, nếu có | Token định danh một tác nhân trung gian | Hỗ trợ mô hình delegation theo chính sách |
| **Target Resource Server** | `reports-api` | Nơi token mới dự kiến được sử dụng; xác định audience/quyền cần cấp |

Một client **đã xác thực** với Token Endpoint chưa đồng nghĩa nó được phép hành động nhân danh **bất kỳ** subject nào. Subject token cũng không đồng nghĩa client đang sở hữu nó có quyền đưa token sang một target khác. Authorization Server phải đánh giá đồng thời cả hai nguồn thông tin.

### Các grant thường bị nhầm

| Grant | Client làm gì? | Resource Owner tương tác? | Yếu tố phân biệt |
| --- | --- | --- | --- |
| `authorization_code` | Đổi authorization code sau khi user cấp quyền | Thường có | Cần code, callback, PKCE |
| `client_credentials` | Xin token nhân danh ứng dụng | Không | Không có subject token được gửi để exchange |
| `refresh_token` | Xin access token mới dựa trên refresh token | Không ở lần refresh | Dùng một token có vai trò refresh theo chính sách |
| **Token Exchange** | Xin security token mới bằng cách trình một subject token | Không đòi tương tác browser tại chính exchange request | `subject_token`, `subject_token_type` và policy exchange |

Token Exchange là **extension grant của Token Endpoint**, không phải một `response_type` mới ở `/oauth2/authorize`. Nó cũng không mặc nhiên biến một client M2M thành người dùng Alice.

## 3. RFC 8693 yêu cầu gì trong Token Exchange Request?

Token Exchange sử dụng `POST /oauth2/token`, body `application/x-www-form-urlencoded` và giá trị grant đầy đủ:

```text
urn:ietf:params:oauth:grant-type:token-exchange
```

### Bảng tham số quan trọng

| Tham số | Bắt buộc? | Ý nghĩa |
| --- | --- | --- |
| `grant_type` | Có | Luôn là URN token exchange theo RFC 8693 |
| `subject_token` | Có | Token đại diện subject mà client muốn sử dụng làm căn cứ |
| `subject_token_type` | Có | Định danh **loại token nguồn**, ví dụ access token |
| `requested_token_type` | Không | Loại token mong muốn được cấp; nếu bỏ qua, RFC 8693 có giá trị mặc định |
| `audience` | Không | Tên logic của bên nhận token mới; có thể xuất hiện nhiều lần |
| `resource` | Không | URI tài nguyên/dịch vụ đích; có thể xuất hiện nhiều lần |
| `scope` | Không | Scope mong muốn cho token mới |
| `actor_token` | Không | Token của bên đang thực hiện hành động trong mô hình delegation |
| `actor_token_type` | Có **khi có actor_token** | Định danh loại actor token |

Một số giá trị **token type identifier**:

```text
urn:ietf:params:oauth:token-type:access_token
urn:ietf:params:oauth:token-type:refresh_token
urn:ietf:params:oauth:token-type:id_token
urn:ietf:params:oauth:token-type:jwt
```

**Phân biệt ba chuỗi URN:**

- `urn:ietf:params:oauth:grant-type:token-exchange` là **grant type** ở `grant_type`.
- `urn:ietf:params:oauth:token-type:access_token` là **token type identifier**, dùng cho `subject_token_type` hoặc `requested_token_type`.
- `Bearer` là **cách sử dụng access token** thường trả trong `token_type`; không phải grant type hoặc token type identifier RFC 8693.

Ví dụ yêu cầu HTTP tối thiểu có target:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <base64-of-exchange-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=SUBJECT_ACCESS_TOKEN
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&audience=reports-api
&scope=orders.read
```

Các giá trị `SUBJECT_ACCESS_TOKEN` và header Basic trên chỉ là placeholder minh họa. Trong hệ thống thật phải dùng TLS, client credentials an toàn, token nguồn hợp lệ và target được policy cho phép. RFC 8693 không yêu cầu một client phải dùng đúng `client_secret_basic`; đó là phương thức chúng ta chọn cho ví dụ confidential client. Với `private_key_jwt` hoặc mTLS, cách xác thực client sẽ khác.

### Response có cấu trúc khác OAuth token response thông thường

```json
{
  "access_token": "NEW_TARGET_ACCESS_TOKEN",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
```

Trong RFC 8693, `issued_token_type` là trường **bắt buộc** mô tả loại security token đã được cấp. `refresh_token` không phải kết quả được cấp mặc nhiên: việc cấp refresh token trong exchange cần chính sách riêng, thường không phù hợp với việc đổi một credential tạm thời để dùng ở target khác.

## 4. Chuỗi xử lý khi client được phép exchange

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng Alice
    participant Web as orders-web
    participant A as orders-aggregator
    participant AS as Spring Authorization Server
    participant Repo as RegisteredClientRepository
    participant API as reports-api
    U->>Web: Đăng nhập / yêu cầu xem đơn hàng
    Web->>AS: Authorization Code + PKCE
    AS-->>Web: Subject access token
    Web->>A: Gửi request được bảo vệ bằng token nguồn
    A->>AS: Token exchange + client authentication
    AS->>Repo: findByClientId(orders-aggregator)
    AS->>AS: Client đúng và có TOKEN_EXCHANGE?
    AS->>AS: Xác minh subject token, target, scope, actor nếu có
    AS->>AS: Áp dụng policy delegation / impersonation
    alt Được phép
      AS-->>A: Token mới, audience dành cho reports-api
      A->>API: Gọi API với token mới
      API->>API: Kiểm tra iss, aud, exp, scope, loại subject
      API-->>A: Trả dữ liệu được phép
    else Không được phép
      AS-->>A: OAuth error; không phát token mới
    end
```

Sơ đồ mô tả **kiến trúc mục tiêu**, trong đó có policy exchange do hệ thống triển khai. Đừng suy luận rằng cấu hình một grant trong `RegisteredClient` sẽ tự thiết lập tất cả logic kiểm tra actor, trust giữa nhiều issuer hoặc audience của dịch vụ đích.

### Một điểm đặc biệt về `subject_token`

Token nguồn có thể mang `sub=alice` nhưng đã được cấp cho một audience khác. Chỉ vì bên trung gian đã nhận token đó để phục vụ request ban đầu **không có nghĩa** nó có quyền gửi token này tới mọi Token Endpoint hoặc biến nó thành token quản trị. Authorization Server phải xác minh chữ ký/trạng thái của token nguồn, issuer, audience/usage phù hợp, thời hạn, client được phép acting/exchange và policy mục tiêu.

**Cấp token mới không tự làm token nguồn hết hiệu lực.** Các hành vi thu hồi, chặn replay, token chaining và TTL của hai token là những quyết định riêng cần kiểm thử.

## 5. Spring Authorization Server hỗ trợ grant token-exchange ra sao?

Theo tài liệu chính thức:

- `AuthorizationGrantType.TOKEN_EXCHANGE` có trong Spring Security từ **6.3**; hằng này ánh xạ đến URN token exchange của RFC 8693.
- Spring Authorization Server cung cấp `OAuth2TokenExchangeAuthenticationConverter` và `OAuth2TokenExchangeAuthenticationProvider` từ nhánh **1.3** và đưa chúng vào cấu hình mặc định của Token Endpoint trên các phiên bản có hỗ trợ tương ứng.
- Với cấu hình Token Endpoint mặc định trên phiên bản tương thích, **không cần tự viết converter/provider chỉ để nhận biết grant**. Cần đăng ký client được phép dùng grant, cấu hình nguồn token và bổ sung policy thực tế nếu hệ thống yêu cầu.

Các phiên bản cũ hơn hoặc một cấu hình custom đã thay thế danh sách provider có thể không có đường xử lý này. Trước khi triển khai, xác minh version thực tế và dependency management của Spring Boot, thay vì trộn API của Spring Security/Spring Authorization Server ở nhiều nhánh.

| Thành phần | Trách nhiệm |
| --- | --- |
| `RegisteredClient` | Khai báo client **được phép** dùng `TOKEN_EXCHANGE`, cách xác thực, scopes |
| `RegisteredClientRepository` | Tìm registration theo client ID đã được nhận diện |
| `OAuth2ClientAuthenticationFilter` và các provider client authentication | Xác thực confidential client theo phương thức đã đăng ký |
| `OAuth2TokenEndpointFilter` | Tiếp nhận HTTP POST token request |
| `OAuth2TokenExchangeAuthenticationConverter` | Phân tích body token exchange request |
| `OAuth2TokenExchangeAuthenticationProvider` | Xử lý grant token exchange theo khả năng của phiên bản |
| `OAuth2AuthorizationService` | Tra cứu/lưu trạng thái authorization/token do AS quản lý |
| `OAuth2TokenGenerator` | Tạo token mới dựa trên context và chính sách |
| Policy/extension của hệ thống | Kiểm soát client nào được exchange token nào, target nào, scope nào |

**Hai tầng phải cùng thành công:** *client authentication* xác minh credential của client, còn *grant authorization* xác minh registration cho phép `TOKEN_EXCHANGE` và policy exchange chấp thuận request cụ thể.

## 6. Đăng ký grant Token Exchange cho client được ủy quyền

### 6.1. Cấu hình hai loại client có quyền khác nhau

Trong ví dụ, `orders-web` là client đăng nhập người dùng qua Authorization Code Flow. `orders-aggregator` là confidential backend **chỉ được cấp** grant Token Exchange để xin token mới theo subject token và policy.

```java
package com.example.authorization;

import java.util.UUID;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

@Configuration
public class TokenExchangeClientConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    RegisteredClientRepository registeredClientRepository(PasswordEncoder encoder) {
        RegisteredClient ordersWeb = RegisteredClient
                .withId(UUID.randomUUID().toString())
                .clientId("orders-web")
                .clientSecret(encoder.encode("lab-orders-web-secret"))
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationGrantType(
                        AuthorizationGrantType.REFRESH_TOKEN)
                .redirectUri("https://orders.example.com/callback")
                .scope("orders.read")
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(true)
                        .build())
                .build();

        RegisteredClient aggregator = RegisteredClient
                .withId(UUID.randomUUID().toString())
                .clientId("orders-aggregator")
                .clientSecret(encoder.encode("lab-aggregator-secret"))
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.TOKEN_EXCHANGE)
                .scope("orders.read")
                .build();

        return new InMemoryRegisteredClientRepository(ordersWeb, aggregator);
    }
}
```

**Giải thích từng lựa chọn:**

- `AuthorizationGrantType.TOKEN_EXCHANGE` là quyền **dùng extension grant**; không phải scope và không phải phương thức client authentication.
- `CLIENT_SECRET_BASIC` yêu cầu aggregator chứng minh danh tính bằng client secret khi gọi Token Endpoint. Đăng ký client chỉ với `client_id` mà không có phương thức xác thực phù hợp là thiết kế rủi ro cho endpoint đổi token.
- `scope("orders.read")` giới hạn một phần quyền mà client có thể xin. Nó **không** có nghĩa aggregator được tự cấp `orders.read` cho bất kỳ người dùng nào.
- Aggregator **không** được cấu hình `AUTHORIZATION_CODE` hay `CLIENT_CREDENTIALS`; vì vậy nó không được tự dùng những grant đó chỉ nhờ tồn tại trong repository.
- `orders-web` không có `TOKEN_EXCHANGE`; nếu chính `orders-web` cố gửi grant exchange, request phải bị từ chối theo registration.
- Không khai báo redirect URI cho aggregator vì exchange thực hiện **back channel** tại Token Endpoint, không trả authorization code qua browser.

Đoạn code chỉ tạo **RegisteredClientRepository minh họa**. Để chạy một Authorization Server hoàn chỉnh, ứng dụng cần thêm cấu hình HTTP Security, issuer, signing keys/JWK, user authentication (cho Authorization Code Flow), `OAuth2AuthorizationService` và các service liên quan. **Đăng ký ở trên chưa triển khai chính sách cross-client exchange** giữa token của `orders-web` và aggregator; chính sách đó phải được định nghĩa và thử nghiệm riêng.

Không dùng secret, ID sinh ngẫu nhiên sau mỗi lần restart hoặc repository in-memory này làm nguồn registration production. Khi triển khai thực tế, dùng secret manager, mã hóa secret dạng hash và lưu registration bền vững bằng JDBC/triển khai phù hợp.

### 6.2. Kích hoạt grant cho một client đã đăng ký

Nếu `orders-aggregator` đã tồn tại trong repository và được xét duyệt để bổ sung Token Exchange, **giữ nguyên ID nội bộ** và chỉ thêm grant:

```java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

public void enableTokenExchange(
        RegisteredClientRepository repository,
        String clientId) {

    RegisteredClient current = repository.findByClientId(clientId);
    if (current == null) {
        throw new IllegalArgumentException("Unknown client");
    }

    // Caller của hàm này phải được hệ thống quản trị phê duyệt trước.
    RegisteredClient updated = RegisteredClient.from(current)
            .authorizationGrantType(AuthorizationGrantType.TOKEN_EXCHANGE)
            .build();

    repository.save(updated);
}
```

Đây là mã **quản trị nội bộ**, không phải endpoint cho client tự bật grant. Cần authentication, phân quyền quản trị, audit, chính sách phê duyệt và chống hai lần cập nhật đồng thời trước khi cho phép thay registration. Giữ ID nội bộ giúp tránh làm đứt liên hệ với các bản ghi authorization đã lưu.

**Lưu ý về lược đồ:** Khi dùng `JdbcRegisteredClientRepository`, grant types được lưu theo schema và cách mapping của phiên bản Spring Authorization Server đang chạy. Đừng tự suy tên cột hay format serialization; hãy dùng schema chính thức và kiểm thử upgrade.

### 6.3. Không cấp grant Token Exchange đại trà

Một chính sách allowlist dễ hiểu:

| Client | Grant `TOKEN_EXCHANGE`? | Lý do |
| --- | --- | --- |
| `orders-aggregator` | **Có**, sau phê duyệt | Backend cần token downstream, có credential bảo vệ |
| `orders-web` | Không, theo nhu cầu ví dụ | Chỉ thực hiện login/ủy quyền ban đầu |
| `public-spa` | Không | Không có khả năng giữ shared secret; không được trao quyền exchange mặc định |
| `batch-export` | Không, nếu chỉ cần `client_credentials` | Không có nhu cầu trao đổi subject token người dùng |
| Client không xác định | Không | Không có registration |

Không đưa `TOKEN_EXCHANGE` vào một template registration chung chỉ vì “server có hỗ trợ”. Với mỗi client được duyệt, phải có **owner**, use case, nguồn subject token tin cậy, target/audience hợp lệ, scope được xin, mức độ ủy quyền và thời hạn đánh giá lại.

## 7. Phân biệt đăng ký grant với chính sách cho phép exchange

Sau khi một `RegisteredClient` có `TOKEN_EXCHANGE`, Authorization Server vẫn phải tự trả lời:

1. Client đã được xác thực bằng phương thức được đăng ký chưa?
2. Subject token có thật, đúng loại, đúng issuer/trust boundary, chưa hết hạn và chưa bị vô hiệu không?
3. Client này được phép đổi **token của subject/issuer/client nguồn này** không?
4. Target `audience` hoặc `resource` có nằm trong allowlist của client/ngữ cảnh đó không?
5. Scope request có phải tập quyền được policy cho phép và không vượt quyền nguồn không?
6. Có `actor_token` không? Nếu có thì actor được tin cậy và có quyền delegation không?
7. Token mới có TTL, issuer, subject/actor, audience, scope và format đúng với hợp đồng của Resource Server đích không?

Nếu bất kỳ điều kiện nào không đạt, **không cấp token mới**.

### 7.1. Một chính sách allowlist cụ thể

Ví dụ quy tắc nghiệp vụ cho `orders-aggregator`:

```text
requesting_client       = orders-aggregator
accepted_subject_issuer = https://auth.example.com
accepted_subject_client = orders-web
allowed_subject_types   = access_token
allowed_target_audience = reports-api
allowed_scopes          = {orders.read}
max_issued_ttl          = 5 minutes
actor_token             = unsupported trong bài lab
```

Chính sách phải được **server** nắm giữ, không tin giá trị client tự gửi. Nếu `subject_token` đã có `orders.read`, token mới trong ví dụ chỉ được xin `orders.read` hoặc tập con được cho phép; không được tự thêm `orders.write`, `admin` hay audience `billing-api`.

Đây là mô hình **định nghĩa policy**, không phải thuộc tính có sẵn được `RegisteredClient` bảo đảm tự thực thi. Các phiên bản Spring Authorization Server có thể hỗ trợ extension points khác nhau; nếu cần kiểm tra cross-client, actor và audience nghiêm ngặt, phải dùng cơ chế mở rộng/validation ở Token Endpoint và token generator phù hợp.

### 7.2. Ví dụ hàm quyết định policy trên dữ liệu đã được xác minh

Hàm Java sau minh họa một lớp **quyết định có thể unit test**, không tự đăng ký với Spring Authorization Server:

```java
package com.example.authorization;

import java.util.Set;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

public final class ExchangePolicy {

    public record VerifiedSubject(
            String issuer,
            String originalClientId,
            String subject,
            Set<String> scopes) {
    }

    private static final Set<String> ALLOWED_SCOPES = Set.of("orders.read");

    private ExchangePolicy() {
    }

    public static boolean mayExchange(
            RegisteredClient requestingClient,
            VerifiedSubject subject,
            String requestedAudience,
            Set<String> requestedScopes) {

        if (requestingClient == null || subject == null
                || requestedAudience == null || requestedScopes == null) {
            return false;
        }

        if (!"orders-aggregator".equals(requestingClient.getClientId())) {
            return false;
        }
        if (!requestingClient.getAuthorizationGrantTypes()
                .contains(AuthorizationGrantType.TOKEN_EXCHANGE)) {
            return false;
        }
        if (!"https://auth.example.com".equals(subject.issuer())) {
            return false;
        }
        if (!"orders-web".equals(subject.originalClientId())) {
            return false;
        }
        if (!"reports-api".equals(requestedAudience)) {
            return false;
        }
        return !requestedScopes.isEmpty()
                && subject.scopes().containsAll(requestedScopes)
                && requestingClient.getScopes().containsAll(requestedScopes)
                && ALLOWED_SCOPES.containsAll(requestedScopes);
    }
}
```

**Ranh giới tin cậy:** Đối tượng `VerifiedSubject` **phải được tạo từ subject token đã xác minh bởi Authorization Server** (hoặc từ authorization record đáng tin), không phải từ JSON/body do client tự gửi và càng không phải từ JWT chỉ được Base64URL-decode mà chưa kiểm tra chữ ký. Hàm trên không kiểm tra token signature, thời hạn, trạng thái revoke, actor và target resource URI — các kiểm tra đó phải có ở phần xử lý giao thức.

Vì đây là hàm chính sách độc lập, **chỉ thêm code này vào project không làm Token Endpoint tự áp dụng nó**. Cần tích hợp policy vào authentication provider/validation pipeline phù hợp, đảm bảo không bỏ qua các kiểm tra mặc định của framework. Trước khi cấp token mới, AS phải kiểm soát cả việc tạo claims/TTL/audience và không tin các thuộc tính request chưa xác minh.

### 7.3. `actor_token` không phải cách tự nhận quyền

RFC 8693 cho phép token exchange với `actor_token` để mô tả bên đang hành động. Một exchange **chỉ có subject token** thường mang ý nghĩa impersonation theo ví dụ RFC; có actor token và policy phù hợp có thể biểu đạt delegation.

Không nên khẳng định rằng thêm hai tham số `actor_token` và `actor_token_type` sẽ tự động khiến Spring Authorization Server phát claim `act` với đúng chuỗi ủy quyền. Cần kiểm tra chính xác khả năng của phiên bản và triển khai policy/claim tương ứng. Trong bài lab này **chưa hỗ trợ actor token**; request có actor token cần được từ chối an toàn nếu chưa có chính sách xử lý.

### 7.4. Vì sao `audience` và `resource` cần allowlist?

Client có thể gửi `audience=billing-api` hoặc `resource=https://internal-admin.example.com/`. Đây mới chỉ là **mong muốn** của client, không phải bằng chứng nó được phép truy cập đích. AS cần map target hợp lệ sang audience được cấp, giới hạn scope, và chỉ phát token cho target được chủ sở hữu hệ thống phê duyệt.

Không sinh trực tiếp JWT `aud` bằng cách chép nguyên mọi `audience` hoặc `resource` trong request mà không kiểm tra. Resource Server đích cần kiểm tra audience **trên token đã ký**; nếu không, token đổi ra có thể bị sử dụng chéo dịch vụ.

## 8. Luồng thực hành: client được đăng ký thực hiện exchange

### 8.1. Điều kiện đầu vào

Để thử luồng sau trong **môi trường cách ly**, chuẩn bị:

- Authorization Server trên `https://auth.example.com` (hoặc localhost qua HTTPS), có endpoint `/oauth2/token` và signing keys phù hợp.
- `orders-web` có thể hoàn tất Authorization Code + PKCE và tạo **subject access token** thực tế cho một người dùng thử nghiệm.
- `orders-aggregator` là confidential client đã đăng ký `TOKEN_EXCHANGE`, có secret/khóa hợp lệ.
- Chính sách exchange đã được triển khai, cho phép aggregator đổi token nguồn từ `orders-web` sang audience `reports-api` với scope `orders.read`.
- Token generator tạo token đích với claim/audience/TTL được kiểm soát; `reports-api` đã cấu hình xác minh token.

Điểm cuối cùng rất quan trọng: **đoạn RegisteredClient ở phần 6 không đủ** để bảo đảm cross-client exchange sẽ thành công với mọi loại subject token hoặc tạo audience mong muốn. Nếu chưa cấu hình policy và token generation, ví dụ dưới đây có thể được server **từ chối đúng** hoặc không sinh claims như bạn mong đợi.

### 8.2. Gửi token exchange request

Giả sử `SUBJECT_ACCESS_TOKEN` là access token đã được cấp thực sự từ Authorization Code Flow:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <encoded-orders-aggregator-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=SUBJECT_ACCESS_TOKEN
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&audience=reports-api
&scope=orders.read
```

Trong PowerShell, có thể thử bằng `curl.exe`, sử dụng giá trị demo từ môi trường:

```powershell
# Các biến này phải được cấp an toàn trong môi trường lab.
# Không lưu production secret hoặc access token vào file/log.
$subjectToken = $env:LAB_SUBJECT_ACCESS_TOKEN
$clientSecret = $env:LAB_EXCHANGE_CLIENT_SECRET

if ([string]::IsNullOrWhiteSpace($subjectToken) -or
        [string]::IsNullOrWhiteSpace($clientSecret)) {
    throw "Can cau hinh LAB_SUBJECT_ACCESS_TOKEN va LAB_EXCHANGE_CLIENT_SECRET"
}

$responseJson = curl.exe -sS `
    -u ("orders-aggregator:" + $clientSecret) `
    -H "Content-Type: application/x-www-form-urlencoded" `
    --data-urlencode "grant_type=urn:ietf:params:oauth:grant-type:token-exchange" `
    --data-urlencode "subject_token=$subjectToken" `
    --data-urlencode "subject_token_type=urn:ietf:params:oauth:token-type:access_token" `
    --data-urlencode "requested_token_type=urn:ietf:params:oauth:token-type:access_token" `
    --data-urlencode "audience=reports-api" `
    --data-urlencode "scope=orders.read" `
    "https://auth.example.com/oauth2/token"

$result = $responseJson | ConvertFrom-Json
if (-not $result.access_token) {
    throw "Exchange khong thanh cong; kiem tra error code tai AS"
}
$issuedAccessToken = $result.access_token
$result | Select-Object issued_token_type, token_type, expires_in, scope
```

**Giới hạn bảo mật của lệnh lab:** tùy hệ điều hành, `curl.exe -u` và form body có thể xuất hiện trong process arguments, môi trường chạy và lịch sử chẩn đoán. Với production, dùng HTTP client có cơ chế bảo vệ secret/token an toàn hơn, HTTPS bắt buộc, không bật verbose logging cho credential và không in raw token.

### 8.3. Kiểm tra response và token đích

Một response hợp lệ có thể giống:

```json
{
  "access_token": "NEW_ACCESS_TOKEN",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
```

Token mới phải có audience và scope phù hợp chính sách, ví dụ:

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-1042",
  "aud": ["reports-api"],
  "scope": "orders.read",
  "client_id": "orders-aggregator"
}
```

Đây là **payload JWT minh họa**, không phải toàn bộ claims bắt buộc hoặc bảo đảm mặc định của framework. Chủ thể `sub` và `client_id` trong token mới phải tuân theo hợp đồng issuer cho loại exchange đã phê duyệt. Nếu chính sách yêu cầu mô hình delegation, cần thông tin actor tin cậy và cách kiểm tra riêng, không suy từ token nguồn.

**Resource Server** phải kiểm tra chữ ký/trạng thái, `iss`, `aud=reports-api`, hạn token, scope và chính sách chủ thể/actor. Giải mã JWT bằng cách đọc payload không phải kiểm chứng chữ ký. Cuối cùng, `GET /api/reports` chỉ nên trả dữ liệu mà policy đích cho phép.

### 8.4. Nên kiểm tra cả token ban đầu và token được đổi

| Thuộc tính | Token ban đầu | Token sau exchange |
| --- | --- | --- |
| Issuer | AS đã cấp token nguồn | AS phát token đích, có thể cùng issuer hoặc khác theo kiến trúc được hỗ trợ |
| Audience | Dành cho API nhận request ban đầu | **Chỉ** dành cho target được cấp phép |
| Subject | Subject của authorization nguồn | Theo policy delegation/impersonation đã duyệt |
| Client ID | Client đã nhận token nguồn | Client được xác thực để xin exchange, theo hợp đồng issuer |
| Scope | Quyền có trong token nguồn | Không vượt các giới hạn của token nguồn, client và chính sách exchange |
| Thời hạn | TTL của token nguồn | TTL được ấn định độc lập theo chính sách, thường ngắn |
| Trạng thái thu hồi | Theo vòng đời token nguồn | Theo vòng đời token được cấp, cần chính sách liên kết nếu mong muốn |

**Không giả định** token đổi ra chắc chắn có cùng `sub`, một `act` claim hoặc cùng token format; những yếu tố đó thuộc hồ sơ trao đổi và chính sách cụ thể. Một Authorization Server chỉ nên cấp những kiểu token và actor semantics mà nó biết xác minh, phát hành và bảo vệ đúng.

## 9. Những lỗi phổ biến khi đăng ký grant và gọi Token Endpoint

Một lỗi ở Token Endpoint có thể phát sinh **trước** bước xử lý subject token, trong bước xác thực client, khi kiểm tra quyền dùng grant hoặc khi áp dụng target policy. Phải tách nguyên nhân để không chữa sai bằng cách nới quyền client.

| Lỗi/mã phản hồi | Điều kiện điển hình | Cách chẩn đoán |
| --- | --- | --- |
| `invalid_client` | Secret/khóa sai, authentication method không đúng, client chưa đăng ký hoặc credential hết hạn | Xác minh client registration, method và credential theo log nội bộ |
| `unauthorized_client` | Client xác thực được nhưng **không có `TOKEN_EXCHANGE`** | Kiểm tra `authorizationGrantTypes` của đúng client |
| `unsupported_grant_type` | Authorization Server không hỗ trợ/không kích hoạt xử lý token exchange trong cấu hình/version đang chạy | Kiểm tra phiên bản và Token Endpoint converter/provider |
| `invalid_request` | Thiếu hoặc sai cú pháp `subject_token`/`subject_token_type`, cặp actor không hợp lệ, tham số mâu thuẫn | Kiểm tra RFC 8693 và request parser; không lộ token vào log |
| `invalid_grant` | Subject token sai, hết hạn, bị thu hồi, không đúng loại hoặc không đáp ứng điều kiện của exchange | Kiểm tra xác minh token nguồn và ràng buộc client/authorization |
| `invalid_scope` | Xin quyền ngoài policy/registration hoặc không được cấp | So sánh scope yêu cầu với source token, client scopes và allowlist |
| `invalid_target` | Target `audience`/`resource` không hợp lệ hoặc không được AS cho phép theo RFC 8693 | Kiểm tra danh sách target được phép và ánh xạ audience |
| `server_error` | Lỗi nội bộ như kho dữ liệu/khóa ký/generator gặp vấn đề | Kiểm tra giám sát AS; không chuyển thành việc cấp token bỏ qua policy |

**Lưu ý:** Mã lỗi cụ thể, HTTP status và thông điệp có thể thay đổi theo bước thất bại, phiên bản Spring Authorization Server và policy tùy biến. Bảng này trình bày **ý nghĩa chuẩn/điển hình**, không phải cam kết từng tình huống luôn trả cùng một chuỗi lỗi.

### 9.1. Khi request bị từ chối dù client có `TOKEN_EXCHANGE`

Hãy lần lượt đối chiếu:

1. Client đã **xác thực thành công** chưa?
2. Registration có `AuthorizationGrantType.TOKEN_EXCHANGE` không, hay chỉ có `AUTHORIZATION_CODE`/`CLIENT_CREDENTIALS`?
3. Subject token có được AS nhận diện và xác minh theo **loại token được khai báo** không?
4. Có cố đổi một ID Token thành access token mặc dù hệ thống chỉ chấp nhận subject access token không?
5. Subject token được phát hành cho client/issuer nào; chính sách có cho phép client hiện tại exchange token đó không?
6. Scope target có vượt scope token nguồn hoặc policy không?
7. `audience`/`resource` có hợp lệ và thuộc allowlist không?
8. Actor token có xuất hiện trong request trong khi hệ thống chưa hỗ trợ actor semantics không?
9. Token mới được generator phát hành với audience/format mong muốn chưa?

Đặc biệt, **sửa thành công lỗi `unauthorized_client` bằng cách thêm grant** không bảo đảm các bước sau đều hợp lệ. Sau khi sửa registration, phải chạy lại cả positive và negative tests để chứng minh không mở quyền trao đổi quá rộng.

### 9.2. Những lỗi triển khai nguy hiểm

| Anti-pattern | Rủi ro | Thiết kế thay thế |
| --- | --- | --- |
| Đăng ký `TOKEN_EXCHANGE` cho mọi client | Tăng bề mặt tấn công và khả năng lạm dụng subject token | Allowlist theo use case/owner/target |
| Chỉ kiểm tra `client_id`, bỏ client authentication | Bất kỳ bên sở hữu token nguồn có thể tìm cách đổi token | Confidential client authentication, rate limit, policy |
| Chỉ decode JWT nguồn rồi tin `sub`/`scope` | Dữ liệu giả mạo được dùng để cấp token thật | Xác minh cryptographic signature, issuer, audience, TTL, trạng thái |
| Chép `scope` request vào JWT đích | Tự mở rộng quyền bằng cách thêm tham số | Downscope/giới hạn theo source, registration, target policy |
| Chép `audience` không kiểm tra | Token cho API nhạy cảm không được cấp phép | Allowlist và mapping target theo client |
| Coi mọi token nguồn là token người dùng | Nhầm client subject với user subject | Kiểm tra source type/grant/principal theo hợp đồng |
| Cho đổi token giữa nhiều issuer mà không xác định trust | Token kém tin cậy được “nâng cấp” | Explicit issuer trust, signature/JWKS/introspection, issuer-specific policy |
| Giả định `actor_token` tự tạo delegation | Mạo danh actor hoặc thiếu audit | Implement/validate actor chain tường minh |
| Không giới hạn TTL token đích | Credential mới còn hiệu lực lâu hơn phạm vi chấp nhận | TTL ngắn, chính sách revocation/expiry rõ ràng |
| Chỉ kiểm tra JWT đích có HTTP 200 | Không phát hiện audience/type/scope leo quyền | Test token issuance + Resource Server policy |

## 10. Kiểm thử grant registration và authorization policy

Nên kiểm thử ít nhất ba lớp riêng biệt:

1. **Repository/registration:** đúng client được thêm `TOKEN_EXCHANGE`; client khác không có grant.
2. **Token Endpoint:** xác thực client, kiểm tra token nguồn và policy, xử lý đúng cả thành công và thất bại.
3. **Resource Server:** token mới chỉ có thể sử dụng ở đúng target, audience, scope và subject/actor policy.

### 10.1. Unit test cho RegisteredClient

Mẫu assertion JUnit 5 sau kiểm tra điều kiện **cần** tại registration:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@SpringBootTest
class ExchangeRegistrationTest {
    @Autowired
    private RegisteredClientRepository clients;

    @Test
    void onlyAggregatorHasExchangeGrant() {
        RegisteredClient aggregator =
                clients.findByClientId("orders-aggregator");
        RegisteredClient web = clients.findByClientId("orders-web");

        assertNotNull(aggregator);
        assertNotNull(web);
        assertTrue(aggregator.getAuthorizationGrantTypes().contains(
                AuthorizationGrantType.TOKEN_EXCHANGE));
        assertFalse(web.getAuthorizationGrantTypes().contains(
                AuthorizationGrantType.TOKEN_EXCHANGE));
    }
}
```

**Ví dụ giả định project có `spring-boot-starter-test` và `RegisteredClientRepository` là Spring bean**. Có thể thay `@SpringBootTest` bằng một unit test tự tạo repository in-memory để giảm chi phí kiểm thử. Việc kiểm tra registration pass **không chứng minh token exchange được server cấp quyền cho mọi target**.

### 10.2. Ma trận positive và negative tests

| Mã | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| EX-01 | `orders-aggregator` xác thực đúng, có grant, subject token hợp lệ, target/scope được duyệt | Có thể cấp token mới theo policy |
| EX-02 | `orders-web` gửi exchange dù không đăng ký grant | Từ chối, điển hình `unauthorized_client` |
| EX-03 | Client ID không tồn tại | Từ chối xác thực/nhận diện client |
| EX-04 | Secret aggregator sai hoặc hết hạn | Từ chối client authentication |
| EX-05 | Dùng sai URN trong `grant_type` | Không được xử lý như Token Exchange |
| EX-06 | Thiếu `subject_token` | Từ chối request |
| EX-07 | Thiếu `subject_token_type` | Từ chối request |
| EX-08 | `subject_token_type` chưa được hỗ trợ | Từ chối an toàn; không tự coi mọi chuỗi là access token |
| EX-09 | Subject token giả chữ ký | Không cấp token |
| EX-10 | Subject token đã hết hạn | Không cấp token |
| EX-11 | Subject token bị thu hồi theo trạng thái server | Hành vi từ chối phù hợp chính sách kiểm tra nguồn |
| EX-12 | Token nguồn thuộc client/issuer không nằm trong allowlist | Không cấp token |
| EX-13 | Xin `scope=orders.write` khi nguồn chỉ có `orders.read` | Từ chối/không cấp quyền vượt nguồn và policy |
| EX-14 | Xin `audience=billing-api` ngoài allowlist | Không phát token cho billing |
| EX-15 | Cố thay `resource` sang URL nội bộ nhạy cảm | Không cấp token đích trái phép |
| EX-16 | Gửi `actor_token` khi deployment chưa hỗ trợ actor | Từ chối an toàn |
| EX-17 | `actor_token` có nhưng thiếu `actor_token_type` | Từ chối request không hợp lệ |
| EX-18 | Đổi cùng token nguồn nhiều lần | Áp dụng chính sách replay/rate limit/cấp token; không mặc định token nguồn bị consume |
| EX-19 | Token đích thiếu audience phù hợp | Resource Server đích từ chối |
| EX-20 | Token đích có chữ ký đúng nhưng scope sai | Resource Server đích từ chối |
| EX-21 | Token đích hết hạn hoặc issuer sai | Resource Server từ chối |
| EX-22 | Client tự gửi `sub=admin` trong extra parameter | AS không tự tạo admin token; chỉ tin subject đã xác minh và policy |
| EX-23 | Exchange yêu cầu token type không được hỗ trợ | Từ chối; không tự chuyển mọi kiểu token |
| EX-24 | Hai instance AS cùng xử lý exchange, dùng repository chung | Kết quả nhất quán, không cấp token trái policy khi có race |

### 10.3. Test ranh giới scope/audience bằng một chính sách thuần

Với lớp `ExchangePolicy` ở phần 7, có thể kiểm tra bằng pseudo-fixture:

```java
RegisteredClient requestingClient = clients.findByClientId("orders-aggregator");

ExchangePolicy.VerifiedSubject validatedSource =
        new ExchangePolicy.VerifiedSubject(
                "https://auth.example.com",
                "orders-web",
                "user-1042",
                Set.of("orders.read"));

boolean permitted = ExchangePolicy.mayExchange(
        requestingClient, validatedSource, "reports-api", Set.of("orders.read"));

boolean wrongAudience = ExchangePolicy.mayExchange(
        requestingClient, validatedSource, "billing-api", Set.of("orders.read"));

boolean escalatedScope = ExchangePolicy.mayExchange(
        requestingClient, validatedSource, "reports-api", Set.of("orders.write"));

assertTrue(permitted);
assertFalse(wrongAudience);
assertFalse(escalatedScope);
```

Mẫu kiểm tra cần fixture repository và imports từ JUnit 5/Java collections để chạy. Đặc biệt, **`VerifiedSubject` ở unit test là dữ liệu giả lập đã xác minh**; integration test của Authorization Server vẫn phải xác nhận dữ liệu thật đến từ token đã qua cryptographic validation và không thể bị client giả mạo.

## 11. Triển khai và vận hành Token Exchange an toàn

### 11.1. Cấu hình Token Endpoint theo phiên bản framework

Với Spring Authorization Server ở phiên bản có hỗ trợ Token Exchange, `OAuth2TokenEndpointFilter` đã đăng ký các converter/provider cần thiết theo cấu hình mặc định. Một ví dụ **khung SecurityFilterChain của Authorization Server**:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer as =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(as.getEndpointsMatcher())
            .with(as, Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated());

    return http.build();
}
```

Đây **chưa phải toàn bộ cấu hình Spring Boot**: bạn cần `RegisteredClientRepository`, `AuthorizationServerSettings`, signing keys/JWK, token/authorization services và cơ chế đăng nhập nếu client khác sử dụng Authorization Code Flow. Với REST client dùng token exchange riêng, cũng cần cấu hình client authentication phù hợp. Không mở công khai/token endpoint chỉ để “bỏ lỗi 401”.

**Phân biệt hai hệ thống Spring khác nhau:**

- **Spring Authorization Server (AS):** quyết định client nào được phép exchange và token nào được phát hành; dùng `RegisteredClient.authorizationGrantTypes`, `OAuth2TokenExchangeAuthenticationProvider` cùng policy.
- **Spring Security OAuth2 Client:** phía dịch vụ thực hiện exchange; có `TokenExchangeOAuth2AuthorizedClientProvider` hoặc `RestClientTokenExchangeTokenResponseClient` tùy phiên bản và cách tích hợp.

Cấu hình OAuth2AuthorizedClientProvider ở client **không tự cấp grant** trên Authorization Server. Ngược lại, đăng ký `TOKEN_EXCHANGE` ở AS **không tự khiến mọi downstream service gửi token exchange request**.

### 11.2. Bổ sung policy mà không phá validation mặc định

Trong phiên bản Spring Authorization Server tương thích, `OAuth2TokenEndpointConfigurer` cho phép cấu hình `authenticationProviders(...)` và các converter/provider liên quan. Khi cần policy đặc thù, có thể mở rộng **bước xử lý grant** tại endpoint này bằng một thành phần chính sách được thiết kế rõ ràng.

Không nên tự viết một authentication provider chỉ kiểm tra client ID rồi phát JWT ngay. Nó dễ bỏ qua việc xác thực subject token, grant, token type, actor, scope và trạng thái revoke. Một đường tích hợp an toàn cần:

1. Giữ lại hoặc thay thế có kiểm soát các bước xác thực client và validation mặc định.
2. Xác minh token nguồn theo issuer/token type đã được cho phép.
3. Tra authorization/claims từ **nguồn đáng tin**, không decode JWT không xác minh.
4. Chạy `ExchangePolicy` trên subject đã xác minh và registration của requesting client.
5. Chỉ khi policy đồng ý, tạo token đích với audience/scope/TTL/actor rõ ràng.
6. Ghi audit và kiểm thử từng đường bị từ chối.

Vì cách móc policy vào provider có thể thay đổi theo phiên bản, bài này không giả định mọi ứng dụng đều có thể cài một interceptor chung và tự động đáp ứng toàn bộ RFC 8693. Nếu phiên bản/framework thiếu chức năng cần thiết, phải viết extension theo hướng dẫn chính thức và kiểm thử giao thức trọn vẹn trước khi dùng production.

### 11.3. Vận hành nhiều Authorization Server instance

Khi deployment có nhiều node:

- Dùng repository đăng ký client và kho authorization phù hợp, không để instance A có grant còn instance B thiếu grant.
- Đồng bộ thay đổi allowlist target, issuer trust và version policy; cân nhắc invalidation của cache.
- Quản lý signing key/JWKS nhất quán; Resource Server phải kiểm chứng token đổi từ bất kỳ node nào.
- Xác định cách kiểm tra trạng thái của token nguồn (JWT offline, introspection, authorization storage) và độ trễ thu hồi chấp nhận được.
- Đặt TTL token đích vừa đủ, tránh tự động làm dài quyền vượt thời điểm hết hạn/ủy quyền của nguồn khi policy không cho phép.
- Giới hạn tốc độ exchange per client/subject/target và giám sát số token mới phát hành.

**Vấn đề khó:** Token nguồn bị revoke sau khi token đích đã phát hành. RFC 8693 không tự buộc mọi token đích bị revoke theo nguồn. Nếu nghiệp vụ yêu cầu chặn truy cập ngay, cần thiết kế **liên kết vòng đời/thu hồi** hoặc introspection online; không suy rằng chỉ cần xóa authorization nguồn là mọi Resource Server ngừng nhận token đích tức thì.

### 11.4. Audit, quan sát và phản ứng khi có dấu hiệu lạm dụng

Một bản ghi audit hữu ích có thể gồm:

```json
{
  "event": "token_exchange_decision",
  "requesting_client_id": "orders-aggregator",
  "source_issuer": "https://auth.example.com",
  "source_subject_reference": "pseudonymous-subject-id",
  "target_audience": "reports-api",
  "requested_scopes": ["orders.read"],
  "policy_version": "exchange-policy-v3",
  "outcome": "allowed",
  "correlation_id": "request-trace-id"
}
```

Đây là **schema ví dụ do hệ thống tự định nghĩa**, không phải nội dung log mặc định của Spring Authorization Server. **Không log raw subject token, actor token, token mới, client secret, Basic header hoặc toàn bộ JWT payload**. Chủ thể/audience có thể là thông tin nhạy cảm, vì thế vẫn cần kiểm soát quyền xem audit và retention.

Nên cảnh báo khi:

- Client chưa được duyệt liên tục thử grant `TOKEN_EXCHANGE`.
- Một client đột ngột exchange token cho nhiều target/subject bất thường.
- Tỷ lệ `invalid_grant`, `invalid_target` hoặc `unauthorized_client` tăng.
- Số lượng token phát hành vượt ngưỡng bình thường.
- Token nguồn từ issuer lạ hoặc actor chain không tin cậy liên tục được gửi.
- Một thay đổi registration/policy mở rộng grant, scope hoặc audience quá nhanh mà không có phê duyệt.

### 11.5. Quy trình thay đổi quyền exchange

Khi cấp mới hoặc gỡ quyền `TOKEN_EXCHANGE`:

1. Xác định owner, lý do nghiệp vụ, client authentication method, source issuer, subject types, target audience, scopes.
2. Đánh giá bảo mật và yêu cầu delegation/impersonation; không mặc nhiên cho mọi client dùng mọi subject token.
3. Kiểm thử registration, positive path, các negative paths, concurrency và trường hợp token nguồn bị revoke/hết hạn.
4. Triển khai policy và cấu hình repository đồng bộ tới toàn bộ AS instances.
5. Giám sát token endpoint và Resource Server sau thay đổi.
6. Ghi audit; xác định cách thu hồi token đã phát nếu phát hiện cấp sai quyền.

Gỡ `TOKEN_EXCHANGE` khỏi registration ngăn **những request exchange mới** của client đó; nó **không tự bảo đảm** token đích đã cấp trước đây hết hiệu lực. Phải xử lý token lifecycle theo yêu cầu bảo mật.

## 12. Bài tập thiết kế, câu hỏi kiểm tra và checklist

### 12.1. Bài tập: hai backend cùng có subject token nhưng khác quyền

Bạn quản lý ba thành phần:

| Thành phần | Chức năng | Nhu cầu Token Exchange |
| --- | --- | --- |
| `orders-web` | Người dùng đăng nhập xem đơn hàng | Không cần exchange trực tiếp |
| `orders-aggregator` | Gọi `reports-api` theo ngữ cảnh đã được ủy quyền | Được duyệt exchange có giới hạn |
| `billing-admin-service` | Quản trị thanh toán | Không được phép dùng subject token đơn hàng để xin billing token |

Yêu cầu:

1. Đăng ký `orders-web` với `AUTHORIZATION_CODE`; đăng ký aggregator với `TOKEN_EXCHANGE`.
2. Chọn client authentication method phù hợp cho aggregator.
3. Thiết kế policy cho source issuer, original client, target audience và scope.
4. Mô tả điều gì xảy ra nếu `billing-admin-service` cố gửi exchange request dù có một subject token hợp lệ.
5. Thử request của aggregator với `scope=orders.write` và `audience=billing-api`; giải thích lý do phải từ chối.
6. Mô tả cách xác minh access token đích ở `reports-api` và cách xử lý khi subject token nguồn bị thu hồi.
7. Thiết kế test chứng minh việc thêm grant trên `RegisteredClient` **không** làm policy tự cho phép target mới.

### 12.2. Câu hỏi tự kiểm tra

**Câu 1.** Chỉ thêm `authorizationGrantType(AuthorizationGrantType.TOKEN_EXCHANGE)` đã đủ để aggregator đổi mọi access token thành billing token chưa?  
**Đáp án:** Chưa. Grant registration chỉ cho phép dùng loại grant; subject token, quyền client–subject, audience và scope phải được policy xác minh.

**Câu 2.** Trong Token Exchange, `grant_type` và `subject_token_type` có cùng URN không?  
**Đáp án:** Không. Grant là `urn:ietf:params:oauth:grant-type:token-exchange`; access token type là `urn:ietf:params:oauth:token-type:access_token`.

**Câu 3.** Client chỉ có grant `client_credentials` có mặc nhiên được token exchange không?  
**Đáp án:** Không. Nó cần `TOKEN_EXCHANGE` trên `RegisteredClient` và các điều kiện policy khác.

**Câu 4.** Ai quyết định `aud` của access token mới?  
**Đáp án:** Authorization Server theo target được phép và policy phát hành; không sao chép tùy ý request `audience`.

**Câu 5.** Thêm `actor_token` có tự bảo đảm an toàn delegation không?  
**Đáp án:** Không. Cần kiểm tra loại actor token, danh tính, mối quan hệ ủy quyền, chain và token claims theo chính sách được triển khai.

**Câu 6.** Việc đổi token có tự thu hồi token nguồn không?  
**Đáp án:** Không mặc định. Vòng đời token nguồn và token đích phải được thiết kế riêng, có liên kết thu hồi nếu nghiệp vụ yêu cầu.

**Câu 7.** Vì sao không nên cho Token Exchange đối với mọi public client?  
**Đáp án:** Token Exchange cho phép phát hành credential mới từ token đang có. Nếu caller khó xác thực hoặc không có policy chặt, một token bị đánh cắp có thể bị sử dụng để xin token đích; phải đánh giá đặc điểm client và phương thức bảo vệ phù hợp.

### 12.3. Checklist triển khai

- [ ] Đã xác nhận Spring Security/Spring Authorization Server phiên bản đang dùng hỗ trợ Token Exchange.
- [ ] Chỉ client được phê duyệt có `AuthorizationGrantType.TOKEN_EXCHANGE`.
- [ ] Requesting client được xác thực bằng phương thức đã đăng ký và kênh TLS an toàn.
- [ ] Subject token được kiểm tra issuer/trust, chữ ký hoặc introspection, thời hạn, trạng thái và loại token.
- [ ] Quy định rõ source token nào và original client nào có thể exchange.
- [ ] Chỉ nhận actor token nếu implementation và policy hỗ trợ đầy đủ.
- [ ] Target audience/resource được allowlist; không chép nguyên request target vào JWT.
- [ ] Scope token đích không vượt source token, client registration và policy đích.
- [ ] TTL, token type/format và claims token mới được kiểm soát.
- [ ] Resource Server đích kiểm tra chữ ký/trạng thái, issuer, audience, scope và subject/actor.
- [ ] Có positive và negative tests cho grant, client auth, token nguồn, target, scope và actor.
- [ ] Có chiến lược token revocation và điều tra lạm dụng phù hợp.
- [ ] Registration, policy, signing keys và authorization state nhất quán giữa các node.
- [ ] Audit không chứa client secret hoặc bất kỳ raw token nào.
- [ ] Thay đổi grant/policy có owner, phê duyệt, rollback/khôi phục và giám sát sau deploy.

### Bản đồ ghi nhớ

```text
RegisteredClientRepository
    |
    +-- orders-web
    |       grants: authorization_code, refresh_token
    |       KHÔNG có token_exchange
    |
    +-- orders-aggregator
            grants: token_exchange
            client authentication: client_secret_basic
            scopes: orders.read
                    |
                    v
Token Endpoint: POST /oauth2/token
    grant_type = urn:ietf:params:oauth:grant-type:token-exchange
    subject_token + subject_token_type
    audience / resource / scope (+ actor nếu policy hỗ trợ)
                    |
                    v
Client authentication + kiểm tra grant trong RegisteredClient
                    |
                    v
Xác minh subject token và actor (nếu có)
                    |
                    v
Authorization policy: client x source x target x scope
                    |
             +------+------+
             |             |
           DENY          ALLOW
             |             |
        OAuth error     Phát token mới
                          đúng aud/scope/TTL
                              |
                              v
                    Resource Server xác minh
```

**Kết luận:** Để **đăng ký grant token-exchange cho client được ủy quyền**, hãy cấp chính xác `AuthorizationGrantType.TOKEN_EXCHANGE` trên `RegisteredClient` thích hợp và cấu hình client authentication an toàn. Sau đó, tách riêng **quyền thực hiện một lần exchange cụ thể**: subject token, actor nếu có, source issuer/client, target, scope, token type và TTL đều phải được chính sách server kiểm soát. Đây là ranh giới quyết định Token Exchange là một cơ chế delegation đáng tin hay thành đường leo quyền ngoài ý muốn.

## Tài liệu chuẩn để đối chiếu

- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): grant URN, subject/actor token, target, response, delegation và các vấn đề bảo mật.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, grant types và repository.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): các converter/provider mặc định ở Token Endpoint.
- [Spring Authorization Server — OAuth2TokenExchangeAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenExchangeAuthenticationProvider.html): thành phần xử lý grant.
- [Spring Security — AuthorizationGrantType API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/AuthorizationGrantType.html): hằng `TOKEN_EXCHANGE` và các grant khác.
- [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/): thành phần phía client để xin token, bao gồm Token Exchange ở các phiên bản hỗ trợ.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Token Endpoint, client authentication, extension grant và lỗi giao thức.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): yêu cầu xác minh và giới hạn trust của JWT access token khi dùng profile này.
