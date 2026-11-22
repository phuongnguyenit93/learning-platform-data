# Yêu cầu scope khi refresh và nguyên tắc không mở rộng quyền

## 1. Vấn đề cần giải quyết

Trong **Spring Security OAuth2/OIDC Authorization Server**, một ứng dụng đã được người dùng cấp quyền có thể nhận **refresh token** để xin access token mới mà không cần đưa trình duyệt qua Authorization Endpoint ở mỗi lần access token hết hạn. Câu hỏi bảo mật quan trọng là:

> Khi dùng refresh token, client có thể gửi thêm một scope chưa từng được chấp thuận để nhận access token nhiều quyền hơn không?

**Không.** Theo **RFC 6749 §6**, tham số `scope` trong refresh token request là **tùy chọn**. Nếu có, scope yêu cầu **không được chứa quyền nào nằm ngoài tập scope đã được cấp cho authorization gốc**. Nếu không có, request được hiểu là yêu cầu lại phạm vi đã được cấp ban đầu.

Trong module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, mục tiêu là học cách **thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security, Spring Authorization Server trong Spring Boot**. Bài này thuộc chương **Refresh Token**, tập trung vào cách xử lý tham số `scope` khi refresh, nguồn dữ liệu quyết định tập quyền tối đa, các lỗi thường gặp và những kiểm thử cần có trước khi vận hành production.

Sau khi học xong, bạn cần:

1. Phân biệt **scope client đăng ký**, **scope người dùng đã đồng ý**, **scope thực tế của authorization**, **scope yêu cầu lúc refresh** và **scope của access token mới**.
2. Biết request refresh **không có `scope`**, có **scope thu hẹp**, hoặc có **scope vượt quyền** được xử lý thế nào.
3. Hiểu vì sao **không thể nâng quyền bằng refresh token**, ngay cả khi metadata client hoặc vai trò của người dùng thay đổi về sau.
4. Nhận diện các thành phần **`RegisteredClientRepository`**, **`OAuth2AuthorizationService`**, **`OAuth2RefreshTokenAuthenticationProvider`** và **`OAuth2TokenGenerator`** trong Spring Authorization Server.
5. Thiết kế kiểm thử cho refresh token rotation, chính sách thu hồi quyền, OIDC, JWT/opaque token và triển khai nhiều instance.

**Phạm vi ví dụ:** API và cấu hình được trình bày theo cách dùng **Spring Authorization Server 1.5.x / Spring Security 6.x / Spring Boot 3.x**. Khi dùng Spring Security 7.x hoặc phiên bản mới hơn, cần đối chiếu Javadoc, dependency và behavior của đúng phiên bản. Chúng ta không giả định mọi loại client, đặc biệt public SPA, luôn được cấp refresh token theo mặc định.

## 2. Năm tập scope phải phân biệt

Hãy xét client `orders-bff`, người dùng `alice` và API quản lý đơn hàng.

| Ký hiệu | Tập scope | Ai quyết định? | Ví dụ |
| --- | --- | --- | --- |
| **R** | Scope được **đăng ký** cho client | Quản trị client / `RegisteredClient.scopes` | `{orders.read, orders.write, orders.export}` |
| **G** | Scope **thực sự được cấp** cho một authorization | Authorization request, user consent và policy của AS | `{orders.read, orders.write}` |
| **Q** | Scope client **yêu cầu khi refresh** | Tham số `scope` trong request hiện tại, nếu có | `{orders.read}` |
| **I** | Scope **thực sự được phát hành** trên access token mới | Authentication provider + token policy | `{orders.read}` |
| **P** | Phạm vi **còn được chính sách hiện tại cho phép**, nếu hệ thống có đánh giá lại | Account lifecycle, client lifecycle, tenant/entitlement và resource policy | Có thể bị thu hẹp vì user mất quyền xuất báo cáo |

Các điều kiện trọng tâm:

```text
Trường hợp refresh request KHÔNG có scope:
    Q mặc định = G            (theo RFC 6749 §6)

Trường hợp refresh request CÓ scope:
    Q ⊆ G                     (không được mở rộng quyền so với grant gốc)

Access token mới:
    I ⊆ Q                     (nếu Q được gửi và server áp dụng chính sách chặt)
    hoặc I ⊆ G                (nếu Q bị bỏ qua)

Nếu triển khai chính sách thu hẹp quyền động P:
    I ⊆ G ∩ P                 (chính sách bổ sung do ứng dụng thiết kế)

Không bao giờ dùng G := R để tự nâng quyền một grant cũ.
```

Đây là **mô hình lý luận**. Trong implementation cụ thể, Authorization Server có thể dùng một tập scope được chuẩn hóa và từ chối thay vì tự thu hẹp theo `P`. Ý nghĩa chuẩn quan trọng là **không được cấp thêm quyền chưa thuộc grant ban đầu chỉ thông qua refresh token**.

### 2.1. Vì sao `RegisteredClient.scopes` không đủ?

Một client có thể đăng ký nhiều scope, nhưng người dùng chỉ đồng ý một phần. Ví dụ:

```text
Client registration R = {orders.read, orders.write, orders.export}
Authorization grant G = {orders.read, orders.write}

Refresh với scope=orders.export
    -> KHÔNG HỢP LỆ, dù orders.export có trong RegisteredClient.scopes

Refresh với scope=orders.read
    -> HỢP LỆ theo quy tắc subset, nếu các điều kiện khác đều đúng
```

Chỉ kiểm tra `requestedScopes ⊆ registeredClient.getScopes()` là **thiếu**: nó cho phép client mở rộng scope đến một quyền **đã đăng ký nhưng chưa được cấp trong authorization hiện tại**.

### 2.2. Vì sao consent đã từng lưu cũng chưa đủ?

`OAuth2AuthorizationConsentService` có thể giữ các quyền user từng đồng ý cho một client, nhưng một refresh token cụ thể phải bị ràng buộc với **authorization mà nó phát sinh**. Consent ở thời điểm khác, scope mới được user chấp thuận cho phiên khác hoặc scope mới được bổ sung vào registration **không tự biến refresh token cũ thành quyền cấp access token rộng hơn**.

**Điểm quyết định** của refresh token grant là authorization liên kết với refresh token đó và tập scope đã được cấp ban đầu. Consent, registration và policy có thể làm cơ sở đánh giá thêm; chúng không thay yêu cầu chống nâng quyền.

## 3. Chuẩn RFC 6749 §6 nói gì về `scope`?

Đối với một refresh token hợp lệ, Token Endpoint nhận request có dạng:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=REFRESH_TOKEN_VALUE
```

Các quy tắc giao thức:

1. `grant_type=refresh_token`: **bắt buộc**.
2. `refresh_token`: **bắt buộc**, giá trị phải được cấp cho client phù hợp và còn hiệu lực.
3. `scope`: **tùy chọn**; nếu có phải là một tập con của scope thuộc authorization gốc.
4. Confidential client hoặc client có yêu cầu xác thực phải thực hiện **client authentication** theo method được đăng ký.
5. AS phải xác minh token, liên kết token với client, trạng thái hết hạn/thu hồi và các chính sách grant trước khi cấp access token mới.

RFC 6749 còn nêu một chi tiết rất quan trọng: **nếu AS trả một refresh token mới khi refresh, refresh token mới phải có cùng phạm vi với refresh token đã được gửi trong request**. Việc access token mới bị thu hẹp **không ngầm thay đổi phạm vi quyền của refresh token được rotate**.

### 3.1. Ba trường hợp cần nhớ

Giả sử authorization gốc đã được cấp:

```text
G = {orders.read, orders.write}
```

| Request tới Token Endpoint | Kết quả theo nguyên tắc scope | Giải thích |
| --- | --- | --- |
| Không có `scope` | Có thể phát access token với scope từ **G** | Bỏ tham số nghĩa là yêu cầu lại scope đã cấp, không phải rỗng |
| `scope=orders.read` | Có thể cấp access token chỉ có `orders.read` | Tập con hợp lệ của G |
| `scope=orders.write` | Có thể cấp access token chỉ có `orders.write` | Vẫn nằm trong G |
| `scope=orders.read orders.write` | Có thể cấp access token với cả hai quyền | Bằng G |
| `scope=orders.export` | **Từ chối** | Quyền chưa nằm trong G |
| `scope=orders.read orders.export` | **Từ chối** | Có một quyền vượt G, không tự chấp nhận phần còn lại trừ policy rõ ràng |
| `scope=admin` | **Từ chối** | Không được dùng refresh để nâng lên quản trị |
| `scope=` (tham số có mặt nhưng trống) | Xử lý như request malformed/invalid theo validator | **Không mặc nhiên xem là bỏ tham số** |

**Phân biệt quan trọng:** “Không gửi tham số `scope`” khác với “gửi tham số `scope` có giá trị rỗng”. Khi viết HTTP client, hãy dùng API form encoding chuẩn và kiểm thử các request malformed/duplicate parameters, thay vì tự nối chuỗi tùy ý.

### 3.2. Scope là chuỗi phân cách bằng dấu cách

Định dạng `scope` theo RFC 6749 §3.3 gồm các **scope-token** phân tách bởi dấu cách. Với HTTP form encoding:

```text
scope=orders.read%20orders.write
```

hoặc dùng HTTP client để tự URL-encode. **Scope name phân biệt chữ hoa/chữ thường** theo cách xử lý thông thường của OAuth, và `orders.read` là tên quyền khác `orders.Read`. Không diễn giải dấu phẩy thành dấu phân cách scope:

```text
scope=orders.read,orders.write
```

Chuỗi trên không tương đương hai scope riêng biệt, trừ khi hệ thống đã chủ ý định nghĩa một token scope có dấu phẩy (không khuyến nghị vì gây nhầm lẫn). Không chấp nhận các tên scope lạ chỉ vì bắt đầu bằng tiền tố quen thuộc.

## 4. Minh họa luồng refresh theo phạm vi đã cấp

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client / BFF
    participant T as Token Endpoint
    participant R as RegisteredClientRepository
    participant A as OAuth2AuthorizationService
    participant G as OAuth2TokenGenerator
    C->>T: POST grant_type=refresh_token, refresh_token, scope?
    T->>R: Xác thực/tra client, kiểm tra grant
    T->>A: findByToken(refresh_token, REFRESH_TOKEN)
    A-->>T: Authorization, refresh token state, authorizedScopes=G
    T->>T: Kiểm tra đúng client, active, expiresAt/revoked
    alt scope được gửi nhưng không là tập con của G
        T-->>C: OAuth error: invalid_scope
    else scope hợp lệ hoặc bị bỏ qua
        T->>T: Chọn phạm vi access token mới từ G / Q
        T->>G: generate access token với authorizedScopes đã quyết định
        G-->>T: Token và claims tương ứng
        T->>A: save authorization/token state mới
        T-->>C: Access token mới (+ refresh token nếu rotation)
    end
```

Sơ đồ cho thấy **authentication provider** là nơi điều phối. Nó gọi repository/service/generator để bảo đảm grant và scope hợp lệ. Không phải client tự ghi scope vào access token; cũng không phải `OAuth2TokenGenerator` tự chọn thêm quyền dựa trên tên client.

### 4.1. Ví dụ A — Refresh không gửi scope

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=RT_FOR_ORDERS_GRANT
```

Nếu token thuộc authorization ban đầu với `{orders.read, orders.write}` và các điều kiện khác hợp lệ, AS có thể cấp access token với tập scope đã được cấp đó. **Không có `scope` không có nghĩa “ít quyền hơn”**.

### 4.2. Ví dụ B — Refresh chỉ yêu cầu quyền đọc

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=RT_FOR_ORDERS_GRANT&scope=orders.read
```

Ví dụ response minh họa:

```json
{
  "access_token": "NEW_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders.read"
}
```

Các token trong ví dụ chỉ là **placeholder**; một AS thực có thể thêm các trường hợp lệ khác, chẳng hạn `refresh_token` mới khi rotation và metadata của profile hỗ trợ. Với JWT access token, cần xác minh claim scope thực tế trong token và validation tại Resource Server, không chỉ tin chuỗi response.

**Hệ quả:** access token mới phù hợp để gọi API chỉ yêu cầu `orders.read`, không để gọi endpoint cần `orders.write`.

### 4.3. Ví dụ C — Client tìm cách mở rộng quyền

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=RT_FOR_ORDERS_GRANT&scope=orders.read%20orders.export
```

Response lỗi Token Endpoint theo OAuth:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_scope"
}
```

Ví dụ là kết quả **mong đợi khi client đã xác thực và refresh token còn hợp lệ**, nhưng yêu cầu vượt tập quyền đã cấp. Nếu client authentication sai hoặc refresh token không còn hợp lệ, AS có thể trả một OAuth error **khác** như `invalid_client`/`invalid_grant` theo quy tắc kiểm tra. Không dùng HTTP status của một request lỗi khác để kết luận validator scope đã chạy.

## 5. Spring Authorization Server giữ thông tin scope ở đâu?

### 5.1. RegisteredClient là giới hạn đăng ký, không phải authorization hiện tại

`RegisteredClient` có `scopes` và `authorizationGrantTypes`. Các thuộc tính này cho biết **khả năng/phạm vi được cấu hình** cho client. Ví dụ:

```java
RegisteredClient ordersBff = RegisteredClient.withId("orders-bff-internal-id")
        .clientId("orders-bff")
        .clientSecret(encodedClientSecret)
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://orders.example.com/login/oauth2/code/orders-bff")
        .scope(OidcScopes.OPENID)
        .scope("orders.read")
        .scope("orders.write")
        .scope("orders.export")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(10))
                .refreshTokenTimeToLive(Duration.ofHours(8))
                .reuseRefreshTokens(false)
                .build())
        .build();
```

Đoạn mã là **trích đoạn cấu hình model**, cần import các class Spring/Java tương ứng và cung cấp `encodedClientSecret` đã mã hóa/băm theo `PasswordEncoder` phù hợp. Một registration hợp lệ còn cần được lưu vào `RegisteredClientRepository`. Không đưa secret dạng plaintext vào source code.

Ngay cả khi registration chứa `orders.export`, điều đó **không** chứng minh authorization của `alice` từng được cấp quyền ấy.

### 5.2. OAuth2Authorization lưu scope của grant đang có

`OAuth2Authorization` biểu diễn một authorization cụ thể, chứa:

- `registeredClientId`: liên kết tới ID nội bộ của `RegisteredClient`.
- `principalName`: người dùng hoặc chủ thể phù hợp với grant.
- `authorizationGrantType`: loại grant ban đầu.
- `authorizedScopes`: **tập scope thực sự được cấp** cho authorization đó.
- `OAuth2Authorization.Token<OAuth2RefreshToken>`: refresh token và metadata/trạng thái tương ứng.
- Các access token/ID token khác khi có.

Ví dụ đọc dữ liệu từ service (minh họa quan hệ; không phải phương thức tự xác thực HTTP):

```java
import java.util.Set;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;

public class RefreshGrantInspection {
    private final OAuth2AuthorizationService authorizationService;

    public RefreshGrantInspection(OAuth2AuthorizationService authorizationService) {
        this.authorizationService = authorizationService;
    }

    public Set<String> findGrantScopes(String refreshTokenValue) {
        OAuth2Authorization authorization = authorizationService.findByToken(
                refreshTokenValue, OAuth2TokenType.REFRESH_TOKEN);
        if (authorization == null || authorization.getRefreshToken() == null ||
                !authorization.getRefreshToken().isActive()) {
            throw new IllegalStateException("Refresh token is not active");
        }
        return authorization.getAuthorizedScopes();
    }
}
```

**Cảnh báo:** Code trên chỉ dùng để giải thích mô hình lưu trữ. Nó **không kiểm tra client binding, grant, caller identity, token endpoint policy hoặc quyền người gọi**; tuyệt đối không tự mở endpoint dựa trên phương thức này. Trong ứng dụng thật, các `AuthenticationProvider` của Spring Authorization Server phải chịu trách nhiệm kiểm tra toàn bộ điều kiện giao thức.

### 5.3. Consent là tầng khác, không phải nguồn mở rộng quyền cho refresh

`OAuth2AuthorizationConsentService` có thể lưu các quyền người dùng đã chấp thuận cho một client. Nhưng:

- User có thể chấp thuận thêm một scope trong **authorization flow mới**.
- Registration có thể được mở rộng thêm scope theo quản trị.
- Một authorization **cũ** vẫn có `authorizedScopes` của lần cấp quyền tương ứng.

Không lấy tổng các scope từng xuất hiện trong consent/registration để cấp thêm quyền cho refresh token cũ. Muốn xin scope mới, hãy bắt đầu authorization flow mới, với xác thực/consent và các điều kiện cần thiết.

## 6. Luồng kiểm tra trong OAuth2RefreshTokenAuthenticationProvider

Với Spring Authorization Server, nhóm thành phần tham gia Token Endpoint gồm:

| Thành phần | Vai trò |
| --- | --- |
| `OAuth2TokenEndpointFilter` | Nhận HTTP POST tới Token Endpoint. |
| `OAuth2RefreshTokenAuthenticationConverter` | Chuyển request `grant_type=refresh_token` thành authentication token chứa refresh token và scopes được yêu cầu. |
| `OAuth2RefreshTokenAuthenticationProvider` | Thực thi validation của refresh grant và điều phối cấp token. |
| `RegisteredClientRepository` | Xác định client và grant/credential policy. |
| `OAuth2AuthorizationService` | Tra cứu authorization theo refresh token, kiểm tra trạng thái và lưu kết quả. |
| `OAuth2TokenGenerator<?>` | Tạo token theo context đã được provider thiết lập, không phải nơi tự nâng quyền. |

Trong luồng hợp lệ, provider phải xem xét **client đã xác thực**, **refresh token gắn với client nào**, **token còn active không**, **grant được cho phép không**, **scope yêu cầu có nằm trong authorization gốc không**. Sau đó nó chọn scopes cho access token mới và gọi generator.

```mermaid
flowchart TD
    A["POST /oauth2/token<br/>grant_type=refresh_token"] --> B{"Client authentication và<br/>refresh grant hợp lệ?"}
    B -->|"Không"| E["OAuth error phù hợp<br/>invalid_client / unauthorized_client"]
    B -->|"Có"| C{"Refresh token tìm thấy,<br/>đúng client và còn active?"}
    C -->|"Không"| F["invalid_grant"]
    C -->|"Có"| D{"Có tham số scope?"}
    D -->|"Không"| G["Dùng authorizedScopes G<br/>của authorization"]
    D -->|"Có"| H{"Requested scopes Q ⊆ G?"}
    H -->|"Không"| I["invalid_scope"]
    H -->|"Có"| J["Dùng tập Q hợp lệ"]
    G --> K["Token generator + chính sách bổ sung"]
    J --> K
    K --> L["Lưu token/authorization mới<br/>và trả token response"]
```

Đây là **luồng quyết định khái niệm**, không phải trace source code hoặc thứ tự exception bắt buộc của mọi phiên bản. Mã lỗi/response có thể khác khi request malformed hoặc client authentication thất bại trước bước scope.

### 6.1. Vì sao không tự thay provider để “nới” scopes?

Spring Authorization Server xử lý các ràng buộc grant ở provider. Nếu dự án tùy biến Token Endpoint, đừng vô tình thay validator bằng:

```java
// SAI: chỉ so scope yêu cầu với registration.
if (registeredClient.getScopes().containsAll(requestedScopes)) {
    // Không có nghĩa refresh token đã được cấp các scopes này!
    issueTokenWith(requestedScopes);
}
```

Đây là **pseudocode phản ví dụ**, không phải API chuẩn. Việc cho scope đã đăng ký nhưng chưa được cấp vào access token mới là **privilege escalation**. Một extension đúng phải giữ invariant `Q ⊆ G`, sau đó áp dụng các chính sách hiện hành nghiêm ngặt hơn nếu cần.

## 7. Ví dụ Java mô hình hóa nguyên tắc không nâng quyền

Đoạn code sau là **policy thuần Java**, dùng cho học tập, unit test và thiết kế validation của ứng dụng. Nó không thay thế validator nội bộ của `OAuth2RefreshTokenAuthenticationProvider`.

```java
import java.util.Objects;
import java.util.Set;

public final class RefreshScopePolicy {
    private RefreshScopePolicy() {}

    /**
     * @param granted    scopes đã lưu trên authorization gốc (G)
     * @param requested  scopes đã parse từ request (Q), nếu scopePresent=true
     * @param scopePresent scope thực sự có mặt trong HTTP form
     */
    public static Set<String> chooseScopes(
            Set<String> granted,
            Set<String> requested,
            boolean scopePresent) {

        Objects.requireNonNull(granted, "granted scopes");

        if (!scopePresent) {
            return Set.copyOf(granted); // RFC 6749 §6: mặc định là G
        }
        if (requested == null || requested.isEmpty()) {
            throw new IllegalArgumentException("invalid_scope");
        }
        if (!granted.containsAll(requested)) {
            throw new IllegalArgumentException("invalid_scope");
        }

        return Set.copyOf(requested); // request thu hẹp hợp lệ
    }
}
```

Trong một Authorization Server thực:

- HTTP parsing phải dùng component của framework, chống duplicated/malformed parameters và kiểm tra định dạng scope token.
- Ngoại lệ ứng dụng cần được ánh xạ đúng sang **OAuth2 error response** (thường `invalid_scope`), không lộ tập grant nội bộ hoặc stack trace.
- Provider còn phải kiểm tra đúng client, refresh token expiry/invalidation, consent/policy hiện tại nếu áp dụng và các ràng buộc security khác.
- Nếu có chính sách thu hẹp quyền động, **không** thay `granted` bằng scope đăng ký của client hoặc roles hiện tại rồi cho phép mở rộng. Hãy kiểm tra một tầng hạn chế bổ sung dựa trên grant gốc.

### 7.1. Unit test cho invariant tập con

```java
import java.util.Set;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class RefreshScopePolicyTest {
    private static final Set<String> GRANTED =
            Set.of("orders.read", "orders.write");

    @Test
    void omittedScopeMeansOriginallyGrantedScopes() {
        assertThat(RefreshScopePolicy.chooseScopes(GRANTED, null, false))
                .containsExactlyInAnyOrder("orders.read", "orders.write");
    }

    @Test
    void requestedSubsetIsAllowed() {
        assertThat(RefreshScopePolicy.chooseScopes(
                GRANTED, Set.of("orders.read"), true))
                .containsExactly("orders.read");
    }

    @Test
    void requestedScopeOutsideGrantIsRejected() {
        assertThatThrownBy(() -> RefreshScopePolicy.chooseScopes(
                GRANTED, Set.of("orders.read", "orders.export"), true))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("invalid_scope");
    }

    @Test
    void explicitEmptyScopeIsNotOmission() {
        assertThatThrownBy(() -> RefreshScopePolicy.chooseScopes(
                GRANTED, Set.of(), true))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
```

Đây là một **ví dụ kiểm thử policy**. Test này chứng minh phép so tập con, **không chứng minh** Token Endpoint thực tế của Spring đã chặn privilege escalation; phải thêm integration test HTTP với refresh token thật.

## 8. Khi scope của client hoặc người dùng thay đổi sau khi cấp refresh token

Đây là phần dễ phát sinh lỗi bảo mật khi hệ thống vận hành lâu dài.

### 8.1. Client được cấp thêm scope ở registration

Ngày 1:

```text
RegisteredClient.scopes = {orders.read, orders.write}
Authorization G          = {orders.read}
```

Ngày 2, quản trị viên cập nhật registration:

```text
RegisteredClient.scopes = {orders.read, orders.write, orders.export}
Authorization G cũ      = {orders.read}   // không tự thay đổi
```

Client cố gửi `scope=orders.export` với refresh token ngày 1 phải bị **từ chối**. Thay đổi registration là thay đổi quyền **có thể được cấp trong tương lai**, không phải lời chấp thuận hồi tố cho mọi refresh token đã phát hành.

Để được cấp quyền mới, client cần khởi tạo authorization flow thích hợp với scope mới, AS kiểm tra chính sách và user consent khi cần, rồi cấp authorization/token tương ứng.

### 8.2. Client bị thu hẹp scope hoặc user bị rút quyền

Ví dụ `orders.write` từng nằm trong G, nhưng hiện tại user đã bị gỡ quyền sửa đơn hàng hoặc admin loại scope đó khỏi registration:

- **Quy tắc tối thiểu RFC §6:** refresh request không được xin quyền nằm ngoài **G**, nhưng điều này **không tự đồng nghĩa framework luôn kiểm tra lại mọi entitlement/registration change** khi refresh.
- **Nhu cầu nghiệp vụ:** nếu phải thu hồi `orders.write` ngay, hãy thiết kế cập nhật/thu hồi authorization hoặc refresh token, kiểm tra entitlement ở Token Endpoint và **Resource Server**, hoặc áp dụng chính sách khác đủ mạnh.
- **JWT access token cũ:** nếu API xác minh JWT offline, thay đổi permission ở AS không tự làm JWT đang còn hạn mất hiệu lực.
- **Tái cấp quyền:** client cần authorization flow mới khi yêu cầu quyền ngoài G; nếu người dùng không còn được phép thì flow mới cũng phải bị chặn.

Không mô tả việc “xóa scope khỏi client registration” là đủ để bảo đảm **mọi access token/refresh token cũ** mất quyền ngay. Đây là một **quy trình revoke/permission-change** rộng hơn.

### 8.3. Thu hẹp scope ở một lần refresh có thay đổi grant mãi mãi không?

**Không mặc nhiên.** Giả sử G ban đầu là `{orders.read, orders.write}`:

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant AS as Authorization Server
    C->>AS: Refresh #1, scope=orders.read
    AS-->>C: Access Token #1: {orders.read}
    Note over AS: Grant gốc G vẫn có thể là {read, write}
    C->>AS: Refresh #2, scope omitted
    AS-->>C: Access Token #2: {orders.read, orders.write} (nếu grant gốc/policy vẫn cho phép)
```

Đây là **tình huống có thể xảy ra theo ngữ nghĩa RFC 6749 §6**, bởi lần refresh thứ nhất chỉ yêu cầu **access token hẹp hơn**, không phải một yêu cầu sửa grant/consent vĩnh viễn. Nếu AS rotate refresh token, RFC yêu cầu scope của refresh token thay thế **giống refresh token cũ**; không đồng nhất nó với scope access token mới.

Nếu sản phẩm yêu cầu **giảm quyền bền vững**, hãy sửa hoặc thu hồi authorization/consent/token theo chính sách và tạo grant mới phù hợp, không dựa vào việc client tự gửi một lần `scope=orders.read`.

## 9. Refresh token rotation, client binding và scope

### 9.1. Ba trục bảo vệ độc lập

| Trục | Câu hỏi | Cơ chế |
| --- | --- | --- |
| **Quyền** | Scope của access token mới có vượt grant ban đầu không? | `Q ⊆ G`, policy cấp quyền, Resource Server authorization |
| **Chủ thể/client** | Refresh token có được dùng bởi đúng client đã nhận nó không? | Client authentication/sender constraint, client binding |
| **Vòng đời** | Refresh token còn active, đã hết hạn hoặc bị dùng lại chưa? | `OAuth2AuthorizationService`, TTL, rotation, revocation, replay handling |

Việc kiểm tra scope **không** thay client authentication. Một refresh token bị đánh cắp vẫn có thể bị lạm dụng trong phạm vi scope đã cấp nếu không được bảo vệ. Ngược lại, client credential đúng không cho phép xin thêm scope ngoài G.

### 9.2. Cấu hình thời hạn và rotation

Trong Spring Authorization Server, `TokenSettings` có thể thiết lập:

```java
TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(10))
        .refreshTokenTimeToLive(Duration.ofDays(7))
        .reuseRefreshTokens(false)
        .build();
```

Đây chỉ là đoạn cấu hình policy cho `RegisteredClient`. Khi `reuseRefreshTokens(false)`, AS có thể cấp refresh token mới ở lần refresh phù hợp; ứng dụng phải cập nhật credential đang lưu **một cách an toàn**. Rotation không tự chuyển scope access token hẹp thành quyền bị rút vĩnh viễn khỏi grant.

**Quan trọng:** rotation của một token và **phát hiện token family replay với hành động thu hồi cả family** không phải cùng một bảo đảm. Khi triển khai public clients hoặc yêu cầu phát hiện lạm dụng, hãy kiểm tra tính năng thực tế của phiên bản/framework và xây chính sách/thử nghiệm bổ sung theo RFC 9700.

### 9.3. Lưu trữ client và refresh token an toàn

- Chỉ truyền refresh token qua **HTTPS**, trong form body của Token Endpoint, không đưa lên URL.
- Bảo vệ secret/token ở backend/BFF hoặc cơ chế secure storage phù hợp; không ghi raw value vào log/tracing/metric labels.
- Dùng sender-constraining hoặc rotation khi phù hợp, đặc biệt với public client theo RFC 9700.
- Thiết kế idempotency/retry cẩn thận: hai refresh request đồng thời có thể tranh chấp rotation, gây `invalid_grant` hoặc sử dụng token cũ sau khi đã được thay.
- Không đưa refresh token vào JWT claims của access token hoặc response dữ liệu ứng dụng.

**Lưu ý với public SPA:** một số phiên bản Spring Authorization Server, như luồng public client trong hướng dẫn PKCE 1.5.x, không mặc định phát refresh token cho client dùng `ClientAuthenticationMethod.NONE`. Không giả định rằng có cấu hình `authorizationGrantType(REFRESH_TOKEN)` là SPA chắc chắn nhận được refresh token; kiểm chứng hành vi thực tế và xem xét BFF khi phù hợp.

## 10. OIDC: scope `openid`, ID token và refresh grant

Trong OpenID Connect, `openid` là scope kích hoạt yêu cầu xác thực OIDC. Những scope như `profile` hoặc `email` thường cho phép yêu cầu thêm claims theo chính sách provider. Khi refresh:

1. Một refresh token phát sinh từ OIDC authorization **vẫn bị ràng buộc bởi grant gốc**; client không được dùng nó để “thêm” `email` hoặc `admin` chưa được cấp.
2. Nếu Token Endpoint hỗ trợ phát ID token khi refresh, nội dung ID token phải được xác minh theo **OIDC Core §12**, issuer/audience/signature, thời điểm và các điều kiện tương ứng. **Không mặc định** mọi refresh response đều có ID token.
3. User consent/claims thay đổi không tự biến refresh request thành một authorization request mới có tương tác người dùng.
4. Scope xuất hiện trên access token và các claims trong ID token/UserInfo là những cấu trúc liên quan nhưng **không đồng nhất**; `scope=profile` không tự bảo đảm một trường claim cụ thể luôn xuất hiện theo cùng một cách trong mọi provider.

Ví dụ: một client ban đầu chỉ được cấp `openid profile` thì request refresh `scope=openid email` **phải bị từ chối**, trừ khi `email` đã thực sự thuộc scope của authorization ban đầu. Muốn quyền mới, cần authorization flow/consent thích hợp.

## 11. Sự khác nhau giữa token response và quyền tại Resource Server

Đừng chỉ kiểm tra HTTP 200 từ Token Endpoint. Cần bảo đảm scope thực cấp được phản ánh nhất quán ở:

- Trường `scope` trong token response khi giao thức yêu cầu cung cấp.
- JWT access token claims (ví dụ claim `scope` trong profile tương ứng), hoặc metadata qua introspection với opaque token.
- `OAuth2Authorization.Token<OAuth2AccessToken>` và context cấp token phía AS.
- Quy tắc authorization tại Resource Server: endpoint `POST /orders/{id}` phải đòi `orders.write`, không được chấp nhận token chỉ có `orders.read`.

Một access token **có scope đúng** vẫn cần kiểm tra issuer, audience, expiry, chữ ký/token state và các ràng buộc liên quan. Scope không thay quyền sở hữu bản ghi hoặc tenant isolation.

### 11.1. Cẩn trọng khi tùy biến JWT claims

Nếu dự án có `OAuth2TokenCustomizer<JwtEncodingContext>`, đừng viết:

```java
// SAI: tự thêm quyền chỉ vì tài khoản có ROLE_ADMIN.
context.getClaims().claim("scope", "orders.read orders.write admin");
```

Đoạn trên là phản ví dụ, không phải cách tạo token. Mọi claim thể hiện **scope/permission** cần được sinh từ quyết định cấp quyền hợp lệ, không tự chép toàn bộ roles hiện thời của người dùng vào access token trong refresh flow.

Đặc biệt, việc thêm một custom claim mang tên khác với `scope` vẫn có thể tạo privilege escalation nếu Resource Server coi claim ấy là quyền truy cập. Kiểm thử cả **cách Token Generator tạo claims** lẫn **cách Resource Server diễn giải claims**.

### 11.2. Nếu Token Endpoint cấp scope hẹp nhưng API vẫn cho phép ghi?

Cần kiểm tra:

1. JWT/introspection thực tế có scope `orders.write` ngoài dự kiến không?
2. Spring Security Resource Server có mapping scope sang `SCOPE_orders.write` hay tự ánh xạ role quá rộng không?
3. API đã kiểm tra scope trên endpoint nhạy cảm chưa?
4. Có cache authorization ở gateway/Resource Server chưa được cập nhật không?
5. Có sử dụng một access token cũ khác (được cấp với scope rộng hơn) thay vì token mới hẹp không?

AS trả `scope=orders.read` trong JSON nhưng Resource Server vẫn cho ghi là **vấn đề phân quyền end-to-end**, không thể chỉ kết luận mã refresh token grant có lỗi.

## 12. Kiểm thử HTTP với Spring Boot

### 12.1. Bộ dữ liệu test khuyến nghị

Chuẩn bị:

- Một confidential client `orders-bff` đã đăng ký `authorization_code` và `refresh_token` với các scopes `openid`, `orders.read`, `orders.write`, `orders.export`.
- Một user test đã cấp **chỉ** `openid`, `orders.read` và `orders.write`, không có `orders.export`.
- Một authorization lưu qua `OAuth2AuthorizationService`, chứa refresh token còn hoạt động, gắn với đúng `registeredClientId`.
- Một Resource Server test có endpoint đọc cần `orders.read` và endpoint sửa cần `orders.write`.
- Các fixtures được tạo qua authorization flow thật (ưu tiên) hoặc qua service trong test tích hợp đã được kiểm soát.

Giả sử:

```text
R = {openid, orders.read, orders.write, orders.export}
G = {openid, orders.read, orders.write}
```

### 12.2. Ma trận kiểm thử scope

| ID | Request refresh | Điều mong đợi |
| --- | --- | --- |
| S01 | Không gửi `scope` | Có thể cấp access token theo G, nếu refresh token và client hợp lệ |
| S02 | `scope=orders.read` | Token mới chỉ có quyền đọc, không tự chứa `orders.write` |
| S03 | `scope=orders.write` | Scope nằm trong G, request được phép về mặt scope |
| S04 | `scope=openid orders.read` | Tập con hợp lệ khi các điều kiện OIDC/grant khác đều đáp ứng |
| S05 | `scope=openid orders.read orders.write` | Bằng G; hợp lệ về mặt scope |
| S06 | `scope=orders.export` | Từ chối `invalid_scope` dù scope này nằm trong R |
| S07 | `scope=orders.read orders.export` | Từ chối, không cấp một token rộng hơn G |
| S08 | `scope=admin` | Từ chối `invalid_scope` |
| S09 | `scope=orders.Read` | Từ chối nếu không thuộc G; scope phân biệt chữ hoa/thường |
| S10 | `scope=` có mặt nhưng rỗng | Từ chối request malformed/invalid theo validator, không xử lý như omission |
| S11 | Tham số `scope` lặp/không đúng encoding | Từ chối request mơ hồ/malformed, không chọn ngẫu nhiên một giá trị |
| S12 | Cập nhật R để thêm `orders.admin` rồi refresh token cũ đòi scope ấy | Vẫn bị từ chối; G cũ không thay |
| S13 | Refresh #1 `scope=orders.read`, Refresh #2 bỏ scope | Không được **tự giả định** lần #1 đã rút vĩnh viễn `orders.write` khỏi G |
| S14 | Refresh token hết hạn/đã vô hiệu hóa | `invalid_grant` hoặc lỗi OAuth tương ứng, không cấp token |
| S15 | Refresh token thuộc client khác | Từ chối theo binding/client authentication, không cấp token |
| S16 | Client thiếu quyền `refresh_token` grant | Từ chối theo client/grant policy |
| S17 | User hoặc client đã bị disable theo policy riêng | Không tiếp tục cấp token nếu yêu cầu nghiệp vụ là dừng phát token |
| S18 | JWT được cấp scope đọc, gọi API ghi | Resource Server trả lỗi thiếu quyền theo policy, không cho ghi |

Các case “hợp lệ về mặt scope” **không tự đồng nghĩa cấp token thành công**: refresh token phải còn hạn, không bị revoke, gắn đúng client và đáp ứng các chính sách khác.

### 12.3. Request test bằng curl

Chỉ chạy ở **môi trường test**, dùng credential fixture và tránh in token vào log terminal chung:

```bash
# Yêu cầu access token hẹp hơn grant gốc.
curl --request POST 'https://auth.test.example/oauth2/token' \
  --user 'orders-bff:TEST_CLIENT_SECRET' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=refresh_token' \
  --data-urlencode 'refresh_token=TEST_REFRESH_TOKEN' \
  --data-urlencode 'scope=orders.read'
```

Để kiểm thử mở rộng quyền, thay bằng:

```bash
curl --request POST 'https://auth.test.example/oauth2/token' \
  --user 'orders-bff:TEST_CLIENT_SECRET' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=refresh_token' \
  --data-urlencode 'refresh_token=TEST_REFRESH_TOKEN' \
  --data-urlencode 'scope=orders.read orders.export'
```

Các giá trị đều là placeholder. Với secret/token thật, tránh đặt chúng trong shell history, command-line arguments có thể bị tiến trình khác nhìn thấy, hoặc hệ thống CI log. Ưu tiên test client dùng secure secret injection và công cụ hỗ trợ redaction.

**Đọc kết quả:** nếu lần hai bị `invalid_grant` vì refresh token đã rotate/expire do lần đầu, test **chưa chứng minh được** rule `invalid_scope`. Hãy dùng fixtures độc lập hoặc tạo một refresh token mới trước mỗi case để phân biệt nguyên nhân.

### 12.4. Kiểm thử JWT/opaque và mô hình trạng thái

Sau mỗi refresh thành công:

1. Kiểm tra tập scope **thực tế** của access token mới (JWT claim hoặc introspection), không chỉ HTTP response.
2. Kiểm tra access token hẹp không gọi được endpoint cần scope lớn hơn.
3. Kiểm tra refresh token mới (nếu rotation) thay token cũ đúng cách; không suy đoán phạm vi refresh token đã bị thu hẹp vĩnh viễn.
4. Kiểm tra `OAuth2AuthorizationService` lưu token state nhất quán qua restart/multiple instances.
5. Gửi request lỗi và xác minh không có token mới được phát hành.

## 13. Vận hành nhiều instance, thay đổi quyền và thu hồi

### 13.1. Nhiều node cùng xử lý refresh

```mermaid
flowchart LR
    C["OAuth2 Client / BFF"] --> LB["Load Balancer"]
    LB --> A["AS node A"]
    LB --> B["AS node B"]
    A --> DB[("Shared OAuth2AuthorizationService<br/>G + refresh token state")]
    B --> DB
    A --> CLIENT[("RegisteredClientRepository<br/>client / grants / token policy")]
    B --> CLIENT
```

Nếu AS A lưu authorization trong memory riêng còn AS B nhận refresh request, B có thể không tìm thấy refresh token. Khi đưa vào production, cân nhắc `JdbcOAuth2AuthorizationService` hoặc storage bền vững tương ứng và giải quyết concurrency/transaction khi refresh rotation. **Không sửa lỗi trạng thái phân tán bằng cách bỏ scope validation**.

### 13.2. Rút quyền khẩn cấp

Giả sử `alice` bị mất quyền `orders.write` vì chuyển bộ phận. Một quy trình an toàn thường cần:

1. Ghi quyết định thay đổi entitlement/consent theo chính sách sản phẩm.
2. Chặn việc cấp access token mới chứa `orders.write`, kể cả request refresh **bỏ qua scope** vốn được hiểu là G cũ.
3. Thu hồi hoặc vô hiệu hóa các refresh token/authorization liên quan khi cần; không mong việc đổi registration là đủ.
4. Giải quyết access token đã phát hành tại Resource Server: TTL ngắn, opaque introspection, denylist hoặc một chính sách kiểm tra trạng thái phù hợp.
5. Kiểm chứng tác động tới toàn bộ node, cache, client và API; ghi audit không chứa raw token.

**Phân biệt:** RFC §6 bảo đảm **không tăng quyền** bằng refresh. Quy tắc này **không tự bảo đảm giảm quyền ngay khi entitlement của user thay đổi**. Yêu cầu ngừng truy cập hiện hữu phải được thiết kế thành một cơ chế vận hành riêng.

### 13.3. Theo dõi sự cố không lộ thông tin

Theo dõi tỷ lệ `invalid_scope`, `invalid_grant`, client auth failures, refresh rotation failures và lệnh revoke. Phân tách các lỗi:

- `invalid_scope`: yêu cầu scope sai hoặc vượt grant gốc.
- `invalid_grant`: refresh token hết hạn/không hợp lệ/đã thu hồi hoặc không thuộc grant/client thích hợp.
- `invalid_client`: client authentication thất bại khi áp dụng.
- `unauthorized_client`: client không được phép dùng grant theo chính sách.
- `invalid_request`: tham số thiếu, lặp hoặc malformed.

Mã lỗi cụ thể phụ thuộc ngữ cảnh kiểm tra của Token Endpoint; **đừng tiết lộ tập scope đã cấp của một user** chỉ để giải thích vì sao một request không hợp lệ. Ghi correlation ID, client ID được kiểm soát, loại lỗi, request outcome và thông tin vận hành đã redaction, không log refresh token, access token, client secret hay toàn bộ JWT payload.

## 14. Những hiểu nhầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Không gửi `scope` nghĩa là không yêu cầu quyền nào.” | Với refresh grant, bỏ scope nghĩa là xin lại phạm vi **đã cấp ban đầu**. |
| “Client đăng ký `admin` là refresh token cũ có thể xin `admin`.” | Không; Q phải thuộc authorization gốc G. |
| “Consent sau này mở rộng nghĩa là refresh token cũ được nâng quyền.” | Không tự động; grant cũ vẫn có phạm vi đã cấp của nó. |
| “`scope=orders.read` ở lần refresh đầu làm refresh token chỉ còn read mãi mãi.” | Không mặc nhiên; thu hẹp access token hiện tại khác thu hồi quyền của grant/refresh token. |
| “Rotate refresh token là thay luôn scope theo access token mới.” | RFC 6749 §6 yêu cầu refresh token mới giữ **cùng phạm vi** với refresh token trước. |
| “Có client secret đúng thì có thể xin mọi scope trong registration.” | Không; client auth không vượt qua phạm vi G. |
| “Chỉ kiểm tra `registeredClient.getScopes()` là đủ.” | Không; phải kiểm tra authorization đã cấp và policy bổ sung. |
| “Scope ít hơn đồng nghĩa JWT đã cấp trước đó cũng bị giảm scope.” | Không; JWT đã ký không tự sửa. |
| “Xóa `orders.write` khỏi registration làm mọi API lập tức chặn token cũ.” | Không; cần chiến lược revoke và kiểm tra ở Resource Server. |
| “Thấy `invalid_grant` là test `invalid_scope` đã thành công.” | Sai; cần refresh token còn active, đúng client và fixture độc lập. |
| “`OAuth2AuthorizationConsentService` là nơi Token Endpoint tự cấp scope mới.” | Consent không tự cấp rộng hơn grant gốc cho refresh. |
| “Tùy biến JWT customizer muốn thêm quyền nào cũng được.” | Resource Server có thể tin claims đó; phải ràng buộc vào chính sách grant thực tế. |

## 15. Checklist production

**Phạm vi quyền**

- [ ] Refresh request **không có scope** được hiểu theo grant ban đầu, không xem là empty permission.
- [ ] Refresh request **có scope** phải là tập con của authorized scopes của chính authorization chứa refresh token.
- [ ] Không mở rộng quyền bằng cách dùng `RegisteredClient.scopes` hoặc consent mới thay cho grant gốc.
- [ ] Kiểm tra response và JWT/introspection token mới không chứa scope vượt quyền.
- [ ] Resource Server thực sự kiểm tra scope trên những API nhạy cảm.

**Bảo mật và vòng đời**

- [ ] Refresh token được ràng buộc đúng client, còn hiệu lực và grant `refresh_token` được cho phép.
- [ ] Confidential client xác thực theo phương thức đăng ký; public client theo chính sách bảo vệ refresh token của phiên bản triển khai.
- [ ] Token TTL, rotation/replay handling, concurrent refresh và logout/revoke được kiểm thử.
- [ ] User/client lifecycle thay đổi được kết nối tới chính sách token issuance và revocation.
- [ ] Không lưu raw refresh/access token và secret vào log/tracing/analytics.

**Kiểm thử và vận hành**

- [ ] Có test scope omitted, subset, equal, superset, unknown, empty, duplicate và case sensitive.
- [ ] Có test scope đăng ký mới sau khi grant cũ được tạo; refresh cũ không nhận quyền mới.
- [ ] Có test scope hẹp ở một lần refresh **không bị hiểu nhầm** là thu hẹp grant mãi mãi.
- [ ] Có test nhiều node, restart, token rotation và trạng thái authorization bền vững.
- [ ] Có metric cho `invalid_scope`/`invalid_grant`, audit an toàn và cách khẩn cấp thu hồi quyền tại API.

## 16. Tài liệu tham khảo

- [RFC 6749 §6 — Refreshing an Access Token](https://www.rfc-editor.org/rfc/rfc6749#section-6): `scope` tùy chọn, phải nằm trong grant gốc, client binding, refresh token mới giữ cùng scope.
- [RFC 6749 §3.3 — Access Token Scope](https://www.rfc-editor.org/rfc/rfc6749#section-3.3): cú pháp và ý nghĩa scope.
- [RFC 6749 §5.1–5.2 — Token Response and Error Response](https://www.rfc-editor.org/rfc/rfc6749#section-5.1): trường `scope` trong token response và lỗi OAuth.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ refresh token, rotation/sender-constraining, scope tối thiểu và các khuyến nghị bảo mật hiện đại.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `OAuth2AuthorizationService` và `authorizedScopes`.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Token Endpoint, authentication converter/provider và cấu hình bảo mật.
- [Spring Authorization Server — How to Implement Core Services with JPA](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-jpa.html): mô hình lưu client/authorization và tham chiếu dữ liệu.
- [Spring Authorization Server — SPA Authentication with PKCE](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-pkce.html): các đặc điểm của public clients và giới hạn refresh token trong hướng dẫn phiên bản tương ứng.
- [OpenID Connect Core 1.0 §12 — Using Refresh Tokens](https://openid.net/specs/openid-connect-core-1_0.html#RefreshTokens): quy tắc refresh trong ngữ cảnh OIDC.

**Kết luận:** Refresh token cho phép xin **access token mới trong phạm vi quyền đã được cấp trước đó**, không phải một cơ hội xin quyền mới. Bỏ `scope` nghĩa là dùng phạm vi grant gốc; gửi `scope` chỉ được yêu cầu **tập con** của grant đó. Trong Spring Authorization Server, hãy dựa vào `OAuth2Authorization.authorizedScopes` và provider xử lý refresh grant, kiểm chứng token phát hành thật và thiết kế thêm cơ chế thu hồi khi quyền người dùng/client bị rút. Đó là ranh giới cốt lõi giữa **làm mới credential** và **cấp thêm đặc quyền**.
