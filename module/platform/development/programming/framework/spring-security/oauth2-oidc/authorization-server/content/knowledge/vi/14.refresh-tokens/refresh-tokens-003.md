# Đổi refresh token để cấp access token mới

> **Chương:** Refresh Token  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Phạm vi:** Thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.  
> **Ngữ cảnh phiên bản:** Những ví dụ Java nhắm tới Spring Boot 3.x, Spring Security 6.x và Spring Authorization Server 1.x (Servlet stack). Với Spring Security 7.x có Authorization Server tích hợp, cần kiểm tra API và starter theo chính phiên bản triển khai.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **refresh token grant** hoạt động ra sao tại token endpoint, vì sao nó khác Authorization Code Grant và không cần chuyển hướng trình duyệt tới trang đăng nhập mỗi lần.
2. Xác định những kiểm tra bắt buộc khi nhận refresh token: **client**, **loại grant**, **trạng thái**, **thời hạn**, **scope** và chính sách phát hành.
3. Mô tả cách Spring Authorization Server dùng `RegisteredClientRepository`, `OAuth2AuthorizationService`, `OAuth2RefreshTokenAuthenticationProvider` và `OAuth2TokenGenerator` trong quá trình cấp access token mới.
4. Cấu hình `TokenSettings.accessTokenTimeToLive(...)`, `refreshTokenTimeToLive(...)` và `reuseRefreshTokens(...)` theo nhu cầu.
5. Phân biệt **tái sử dụng refresh token** với **refresh token rotation**, hiểu giới hạn của phát hiện replay, thu hồi token và chấm dứt phiên.
6. Viết kiểm thử cho refresh token hợp lệ, sai client, hết hạn, bị vô hiệu hóa, vượt scope, dùng lại sau rotation và yêu cầu đồng thời.
7. Thiết kế cách lưu giữ refresh token an toàn trong BFF, backend, mobile và các hệ thống nhiều instance.

**Câu chốt:** Refresh token không phải “vé vô hạn” có thể đổi access token ở mọi thời điểm. Nó là **credential có quyền hạn và vòng đời riêng**, được cấp cho một client trong một authorization cụ thể; AS phải kiểm tra lại các ràng buộc trước mỗi lần cấp token mới.

## 2. Phân biệt access token và refresh token

| Thuộc tính | Access token | Refresh token |
| --- | --- | --- |
| Mục đích | Cho phép Client truy cập Resource Server (RS) | Cho phép Client xin access token mới tại Authorization Server (AS) |
| Nơi gửi đến | API được bảo vệ, thường qua `Authorization: Bearer ...` | Token endpoint của AS, thông thường trong `grant_type=refresh_token` |
| Chủ thể nhận | RS kiểm tra token và quyền truy cập | AS xác thực/xác minh yêu cầu đổi token |
| Thời gian sống | Thường tương đối ngắn | Thường dài hơn access token, nhưng do chính sách AS quyết định |
| Định dạng | Có thể JWT tự chứa hoặc opaque/reference | Thường là chuỗi opaque khó đoán trong SAS 1.x; không tự giả định cấu trúc |
| Scope | Thể hiện quyền truy cập API đã được cấp | Ràng buộc với authorization/scopes cho phép, không phải quyền mặc định mở rộng |
| Thu hồi | Phụ thuộc cách RS xác minh JWT/opaque và chính sách | AS có thể đánh dấu token vô hiệu; cách phản ứng còn phụ thuộc implementation |
| Khi bị lộ | Kẻ tấn công có thể gọi API trong phạm vi token | Kẻ tấn công có thể xin access token mới nếu vượt qua các ràng buộc bổ sung |

Trong OAuth 2.0, refresh token **không gửi tới Resource Server** để truy cập dữ liệu. RS không nên chấp nhận refresh token như access token, kể cả hai chuỗi có hình dạng giống nhau. Ngược lại, access token cũng không phải credential hợp lệ để gọi grant `refresh_token`.

Refresh token có thể được cấp trong phản hồi token khi grant cho phép và chính sách AS quyết định. **Không phải mọi Client hay mọi grant đều nhận refresh token**. Đặc biệt, RFC 6749 khuyến nghị **không** phát refresh token cho Client Credentials Grant; trong Spring Authorization Server, việc đăng ký `AuthorizationGrantType.REFRESH_TOKEN` không tự động biến mọi token response thành response có refresh token.

### 2.1. Tại sao cần refresh token nếu access token đã có thời hạn?

Giả sử ứng dụng đặt phòng dùng access token chỉ có hiệu lực 5 phút. Người dùng đang thao tác trong ứng dụng lâu hơn 5 phút. Không có refresh token, client phải khởi động lại một authorization flow mới hoặc có cơ chế xác thực khác, có thể dẫn đến nhiều redirect không cần thiết.

Nếu AS đã cấp refresh token hợp lệ, client có thể xin access token mới **mà không cần người dùng nhập lại mật khẩu ở mỗi lần access token hết hạn**. Điều này cải thiện trải nghiệm, nhưng làm tăng giá trị của refresh token đối với kẻ tấn công: credential có khả năng duy trì quyền truy cập cần được lưu giữ nghiêm ngặt.

### 2.2. Refresh token không đồng nghĩa với phiên đăng nhập ở AS

Ba trạng thái cần tách rõ:

- **Phiên đăng nhập Resource Owner:** có thể tồn tại trong HTTP session tại AS để xử lý trình duyệt, login, consent.
- **Authorization và refresh token:** được AS lưu qua `OAuth2AuthorizationService` để xử lý grant trong các HTTP request khác nhau.
- **Access token tại RS:** được RS xác minh theo chữ ký JWT hoặc introspection/metadata tương ứng; không tự chia sẻ `SecurityContext` với AS.

User logout khỏi một trang web **không mặc định** đồng nghĩa mọi refresh token và JWT còn hiệu lực đều bị thu hồi. Nếu yêu cầu của hệ thống là “logout khỏi mọi thiết bị”, phải bổ sung chính sách revoke token, invalidation session và kiểm tra token ở RS phù hợp.

## 3. Luồng refresh token grant từ đầu đến cuối

Giả sử:

- **Resource Owner:** Lan.
- **OAuth2 Client:** backend/BFF `booking-web`, confidential client đã đăng ký.
- **AS:** `https://auth.example.test`.
- **RS:** `https://api.example.test`.
- Client trước đó đã hoàn tất Authorization Code + PKCE và nhận một access token cùng refresh token theo chính sách.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Resource Owner
    participant C as booking-web (Client)
    participant AS as Authorization Server
    participant DB as Authorization Store
    participant RS as Resource Server

    U->>C: Đăng nhập và thao tác lần đầu
    Note over C,AS: Authorization Code + PKCE đã hoàn tất
    AS-->>C: access_token A1 + refresh_token R1
    C->>RS: API request dùng A1
    RS-->>C: Response hợp lệ
    Note over C: A1 sắp/hết hạn; R1 còn hợp lệ
    C->>AS: POST /oauth2/token<br/>grant_type=refresh_token, R1, client authentication
    AS->>AS: Xác thực client + kiểm tra grant type
    AS->>DB: Tra R1 và authorization liên quan
    DB-->>AS: RegisteredClient binding, scopes, token status
    AS->>AS: Kiểm tra active/expiry/scopes + chính sách rotation
    alt R1 hợp lệ
        AS->>DB: Lưu access token A2<br/>và refresh token mới nếu rotation
        AS-->>C: access_token A2 + refresh_token theo chính sách
        C->>RS: API request dùng A2
        RS-->>C: Response hợp lệ
    else R1 không hợp lệ
        AS-->>C: OAuth2 error, không phát token
    end
~~~

Trong request `POST /oauth2/token`, principal thường đại diện **OAuth2 Client đang được xác thực/nhận diện**, không phải một `UsernamePasswordAuthenticationToken` của phiên browser login trước đó. Resource Owner của authorization được xác định qua bản ghi grant đã lưu, không bằng cách lấy lại ThreadLocal của request đăng nhập cũ.

### 3.1. Hai lần phát token có quan hệ nhưng không hoàn toàn giống nhau

Lần đầu, client nhận refresh token theo grant ban đầu và chính sách phát hành của AS. Những lần sau, khi refresh thành công:

- Một **access token mới** được cấp, thường với `issued_at` và `expires_at` mới.
- `refresh_token` trong response có thể là **chuỗi cũ** (reuse) hoặc **chuỗi mới** (rotation), tùy `TokenSettings` và provider.
- Scope được giữ nguyên hoặc **thu hẹp** theo yêu cầu hợp lệ; client không thể dùng refresh để tự mở rộng các scope chưa được cấp.
- Việc phát hành ID token trong bối cảnh OIDC refresh phải tuân thủ chính sách OIDC và implementation, **không mặc định suy ra chỉ vì có access token mới**.

## 4. HTTP request và HTTP response chuẩn

### 4.1. Confidential Client gửi refresh request

Ví dụ HTTP minh họa:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <encoded-client-id-and-secret>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=refresh_token&refresh_token=REFRESH_TOKEN_VALUE&scope=booking.read
~~~

Trong OAuth 2.0:

- `grant_type` **phải** là `refresh_token`.
- `refresh_token` là giá trị được AS cấp trước đó.
- `scope` là tham số **tùy chọn**. Nếu có, những scope được yêu cầu không được vượt ngoài phạm vi authorization đã được cấp. Khi không gửi `scope`, theo RFC 6749, phạm vi phải được xử lý như phạm vi ban đầu theo quy tắc server/profile.
- Confidential client phải xác thực theo **phương thức đã đăng ký**, ví dụ `client_secret_basic`. Không gửi client secret trong URL.
- Dùng TLS; không đưa refresh token hoặc secret thật vào log, ví dụ tài liệu, ảnh chụp màn hình hay công cụ analytics.

`Authorization: Basic <encoded-client-id-and-secret>` chỉ là placeholder; ứng dụng nên dùng thư viện OAuth2 Client thay vì tự ghép header xác thực bằng tay. Việc mã hóa Basic phải tuân thủ quy định OAuth2 và HTTP liên quan.

### 4.2. Token response thành công

Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "NEW_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "NEW_OR_REUSED_REFRESH_TOKEN",
  "scope": "booking.read"
}
~~~

Response này minh họa các field thường gặp:

| Field | Vai trò | Ghi chú |
| --- | --- | --- |
| `access_token` | Token mới cho RS | Có thể JWT hoặc opaque theo `TokenSettings.accessTokenFormat` |
| `token_type` | Loại token, thường `Bearer` | RS dùng đúng scheme và cách xác minh |
| `expires_in` | Số giây còn hiệu lực của access token tại thời điểm response | Client cần tính thời điểm hết hạn có trừ khoảng lệch hợp lý |
| `refresh_token` | Refresh token sau lần đổi | Giá trị được tái sử dụng hoặc mới tùy chính sách; chỉ cập nhật lưu trữ khi response hợp lệ |
| `scope` | Scope access token mới, nếu được trả về | Không bao giờ được mở rộng vượt quyền đã cấp |

Không phụ thuộc vào `refresh_token` trong mọi response của mọi AS nếu giao thức/profile cho phép không trả hoặc server thay đổi chính sách; với Spring Authorization Server 1.x, hành vi reuse/rotation được kiểm soát bởi `TokenSettings` và provider. Client cần xử lý response theo hợp đồng triển khai cụ thể.

### 4.3. Refresh request sai hoặc token không còn hiệu lực

Thông thường AS trả OAuth2 error như:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_grant"
}
~~~

`invalid_grant` thường tương ứng với refresh token sai, hết hạn, đã bị vô hiệu hóa hoặc không khớp ràng buộc grant/client. Nếu **client authentication** không hợp lệ, AS có thể trả `invalid_client` và mã HTTP/challenge phù hợp; nếu scope yêu cầu vượt quyền, có thể trả `invalid_scope`.

Không dựa vào mô tả lỗi để suy ra refresh token thuộc user nào hay tồn tại không; AS nên tránh tiết lộ dữ liệu nhạy cảm trong `error_description` và log.

## 5. Các bước xác minh trong Authorization Server

Trong Spring Authorization Server 1.x, xử lý refresh token nằm ở **Token Endpoint**, không phải Authorization Endpoint:

1. `OAuth2ClientAuthenticationFilter` và các provider liên quan nhận diện/xác thực client theo registration.
2. `OAuth2TokenEndpointFilter` dùng converter phù hợp để chuyển request thành `OAuth2RefreshTokenAuthenticationToken`.
3. `OAuth2RefreshTokenAuthenticationProvider` xử lý yêu cầu thông qua các thành phần như `RegisteredClientRepository`, `OAuth2AuthorizationService` và `OAuth2TokenGenerator`.
4. Provider xác minh client/grant/refresh token và scope, sinh access token mới; xử lý refresh token theo chính sách.
5. AS lưu authorization state cập nhật rồi tạo OAuth2 token response phù hợp.

Các bước là mô hình logic của nhánh SAS 1.x; thứ tự chi tiết hoặc API tùy chỉnh có thể khác giữa các phiên bản.

### 5.1. Bảng các điều kiện phải đạt

| Điều kiện | Điều AS cần chứng minh | Khi không đạt |
| --- | --- | --- |
| Client được nhận diện/xác thực | Phương thức phù hợp `RegisteredClient`; confidential client chứng minh credential hợp lệ | `invalid_client` hoặc lỗi client authentication |
| Client được phép refresh | Registration có `AuthorizationGrantType.REFRESH_TOKEN` | Từ chối grant |
| Refresh token tồn tại | `OAuth2AuthorizationService` có authorization/token tương ứng | `invalid_grant` |
| Token đúng loại | Đó là refresh token được AS chấp nhận, không phải access token hay ID token | `invalid_grant` hoặc lỗi request phù hợp |
| Token gắn với client | `registeredClientId` của authorization khớp client đang thực hiện grant | `invalid_grant` |
| Token còn active | Chưa hết hạn, chưa bị invalidated và chưa bị tiêu thụ theo rotation | `invalid_grant` |
| Scope hợp lệ | Scope yêu cầu không vượt `authorizedScopes` của authorization | `invalid_scope` |
| Chính sách token | Được phép phát token mới, áp dụng TTL, format, rotation, claims policy | Từ chối hoặc cấp theo policy |
| Lưu trạng thái | Kết quả cập nhật được lưu nhất quán để truy vết/revocation | Không được phản hồi thành công khi hệ thống không bảo đảm tính đúng đắn |

Một việc rất quan trọng là **binding refresh token với Client**. Biết chuỗi refresh token chưa đủ để cho Client B đổi token đã phát hành cho Client A. Ràng buộc này áp dụng cả với Client Confidential và Client Public; với public client, cơ chế bảo vệ cần dựa vào chính sách/token rotation, sender-constrained token hoặc yếu tố phù hợp vì `client_id` không phải bí mật.

### 5.2. Không cần Resource Owner đăng nhập lại ở mỗi lần refresh

Refresh token grant không phải luồng lấy lại username/password. AS dựa vào authorization đã được tạo từ trước để xác định principal/scopes được cấp. Tùy chính sách, AS có thể:

- Cho phép refresh khi refresh token còn hiệu lực và chưa bị thu hồi.
- Từ chối nếu tài khoản/consent/client đã bị khóa hoặc bị thu hồi quyền, **nếu implementation có kiểm tra trạng thái tương ứng**.
- Yêu cầu người dùng hoàn tất authorization/login mới khi refresh token hết hạn hoặc không còn hợp lệ.

**Không mặc định** rằng việc đánh dấu tài khoản `disabled` trong bảng người dùng sẽ lập tức làm tất cả refresh token cũ bị từ chối. Nếu yêu cầu này quan trọng, phải thiết kế logic thu hồi/kiểm tra trạng thái ở AS và test rõ.

## 6. Cấu hình RegisteredClient để được dùng refresh token

Mốc ví dụ: BFF backend dùng Authorization Code + PKCE, confidential client và cần giữ phiên trải nghiệm người dùng qua nhiều lần access token hết hạn.

~~~java
import java.time.Duration;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

public final class ClientFactory {

    private ClientFactory() {}

    public static RegisteredClient bookingBff(
            String secretFromSecureConfig,
            PasswordEncoder passwordEncoder) {

        return RegisteredClient
            .withId("booking-bff-internal-id")
            .clientId("booking-bff")
            .clientSecret(passwordEncoder.encode(secretFromSecureConfig))
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationGrantType(
                AuthorizationGrantType.REFRESH_TOKEN)
            .redirectUri(
                "https://app.example.test/login/oauth2/code/booking-bff")
            .scope(OidcScopes.OPENID)
            .scope("booking.read")
            .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
            .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(5))
                .refreshTokenTimeToLive(Duration.ofDays(7))
                .reuseRefreshTokens(false)
                .build())
            .build();
    }
}
~~~

Giải thích:

- `authorizationGrantType(AUTHORIZATION_CODE)` cho phép tạo grant ban đầu qua trình duyệt và PKCE.
- `authorizationGrantType(REFRESH_TOKEN)` cho phép client sử dụng refresh token grant khi có refresh token đã được AS cấp.
- `CLIENT_SECRET_BASIC` yêu cầu client xác thực tại token endpoint. Secret phải đến từ secret manager/cấu hình an toàn và được hash theo `PasswordEncoder` phù hợp.
- `requireProofKey(true)` yêu cầu PKCE trong grant ban đầu. **PKCE verifier không phải tham số thông thường của refresh token grant**, vì refresh token đã có binding riêng.
- `accessTokenTimeToLive(...)` và `refreshTokenTimeToLive(...)` quy định TTL từng loại token, không phải cùng một thời hạn.
- `reuseRefreshTokens(false)` biểu thị mong muốn **rotation**: khi refresh thành công, cấp refresh token mới thay vì tiếp tục dùng mã cũ.
- Việc chọn rotation **không tự cung cấp toàn bộ hệ thống phát hiện replay theo token family**; cần bổ sung chính sách nếu yêu cầu phản ứng khi bị đánh cắp.

**Đây chỉ là factory minh họa `RegisteredClient`.** Để có AS hoàn chỉnh phải lưu registration bằng `RegisteredClientRepository` và cấu hình authorization store, khóa ký, issuer, user authentication, consent, filter chain và các endpoint đúng phiên bản. Một ID registration phải ổn định khi lưu bền vững; không tạo lại ngẫu nhiên mỗi lần boot dẫn tới mất liên kết authorization cũ.

### 6.1. Chọn TTL có cơ sở

| Giá trị | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Access token TTL | 5 phút | Giảm thời gian access token bị đánh cắp còn có thể dùng |
| Refresh token TTL | 7 ngày | Cho phép client xin access token mới trong khoảng được cấp |
| Rotation | `false` cho `reuseRefreshTokens` | Refresh thành công phát refresh token mới theo chính sách |
| Absolute session lifetime | Ví dụ tối đa 30 ngày | **Không tự được cấu hình chỉ bằng các giá trị trên**; phải thiết kế chính sách riêng |

Các thời lượng là **ví dụ minh họa, không phải giá trị chuẩn bắt buộc**. Một hệ thống ngân hàng có thể cần TTL và re-authentication khác hẳn ứng dụng đọc tin. Phải xét loại client, rủi ro bị chiếm token, trải nghiệm người dùng, chính sách session và các yêu cầu tuân thủ.

## 7. Reuse và rotation: hai chính sách có trade-off riêng

### 7.1. Reuse refresh token

Nếu cấu hình:

~~~java
TokenSettings.builder()
    .reuseRefreshTokens(true)
    .build();
~~~

AS có thể tiếp tục dùng **cùng refresh token** cho nhiều lần đổi access token cho đến khi token hết hạn, bị thu hồi hoặc bị vô hiệu hóa theo chính sách.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server

    Note over C,AS: C đã có R1 và A1
    C->>AS: R1 xin access token mới
    AS-->>C: A2 + R1 (reuse)
    C->>AS: R1 xin access token lần nữa
    AS-->>C: A3 + R1 (reuse)
~~~

Ưu điểm: client dễ quản lý credential, ít rủi ro mất đồng bộ khi response bị đứt mạng. Nhược điểm: nếu R1 bị đánh cắp, attacker có thể tiếp tục sử dụng nó cho tới khi AS vô hiệu hóa token hoặc token hết hạn, nếu không có ràng buộc bảo vệ bổ sung.

### 7.2. Refresh token rotation

Nếu cấu hình:

~~~java
TokenSettings.builder()
    .reuseRefreshTokens(false)
    .build();
~~~

AS được yêu cầu **phát refresh token mới sau lần đổi thành công**, thường đồng thời làm token trước không còn dùng để refresh tiếp.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server

    Note over C,AS: C đang giữ R1
    C->>AS: Dùng R1
    AS->>AS: Kiểm tra R1 và thay bằng R2
    AS-->>C: A2 + R2
    C->>C: Lưu R2 thay R1
    C->>AS: Dùng R2
    AS->>AS: Kiểm tra R2 và thay bằng R3
    AS-->>C: A3 + R3
    C->>C: Lưu R3 thay R2
    Note over C,AS: Dùng R1/R2 lại phải bị từ chối nếu đã invalidated
~~~

Rotation có thể hạn chế khả năng tái sử dụng cùng một token bị lộ và tạo cơ hội phát hiện replay. Nhưng **rotation đơn thuần không phải toàn bộ cơ chế phát hiện token theft**:

- Cần nhận diện chuỗi quan hệ refresh-token family khi muốn biết token cũ bị dùng lại là dấu hiệu có attacker.
- Cần chính sách thu hồi toàn bộ family hoặc yêu cầu đăng nhập lại khi phát hiện replay.
- Cần xử lý race condition giữa hai refresh request đồng thời.
- Cần chiến lược khi response chứa R2 bị mất sau khi AS đã vô hiệu R1.
- Cần quyết định có giới hạn tổng thời gian sống của phiên hay để rotation kéo dài không giới hạn.

Spring Authorization Server cung cấp `reuseRefreshTokens(false)` cho chính sách phát hành. **Không tự kết luận rằng nó luôn thực hiện family-wide revocation, replay alert hay absolute session timeout**. Các yêu cầu này phải được triển khai/kiểm thử riêng trên phiên bản cụ thể.

### 7.3. Đổi refresh token không đồng nghĩa gia hạn vô hạn

Khi reuse R1, thời gian hết hạn ban đầu của R1 thường không thay đổi chỉ vì AS cấp access token mới. Khi rotation R1 → R2, token mới có thể có TTL mới theo cấu hình, khiến trải nghiệm duy trì đăng nhập kéo dài nếu không có giới hạn độc lập.

Nếu tổ chức yêu cầu “không được refresh sau 30 ngày kể từ lần đăng nhập ban đầu”, cần lưu và thực thi **absolute authorization/session lifetime** trong chính sách riêng. Chỉ đặt `refreshTokenTimeToLive(Duration.ofDays(7))` không phải cấu hình trần thời gian sống tuyệt đối của cả family.

## 8. Xác minh scope khi refresh

Một client không thể xin quyền rộng hơn những scope đã được chấp thuận ở authorization ban đầu.

Ví dụ authorization đã cấp:

~~~text
authorizedScopes = ["openid", "booking.read", "profile"]
~~~

Các yêu cầu:

| Refresh request | Kết quả hợp lệ về scope |
| --- | --- |
| Không có `scope` | Giữ phạm vi đã cấp theo chính sách của AS/profile |
| `scope=booking.read` | Có thể hợp lệ: thu hẹp phạm vi |
| `scope=booking.read profile` | Có thể hợp lệ: tập con của phạm vi đã cấp |
| `scope=booking.write` | Không được mở rộng: AS từ chối |
| `scope=admin` | Không được mở rộng: AS từ chối |
| `scope=booking.read admin` | Từ chối vì có scope ngoài authorization |

Ở nhánh Spring Authorization Server 1.x, `OAuth2RefreshTokenAuthenticationProvider` xử lý scope request và kiểm tra phạm vi đã được authorization cấp. Không được viết custom provider bỏ qua kiểm tra này rồi coi token mới có quyền theo `RegisteredClient.getScopes()` một cách tùy tiện.

**Phân biệt:** `RegisteredClient.getScopes()` là những scope *client có thể xin*; `OAuth2Authorization.getAuthorizedScopes()` là những scope đã thực sự được cấp cho authorization cụ thể. Tại refresh endpoint, dùng client registration alone để cấp thêm scope có thể vượt qua consent của Resource Owner.

### 8.1. Quyền người dùng đổi trong lúc refresh token còn hạn

Giả sử Lan đã được cấp `booking.read`, nhưng sau đó bị gỡ quyền xem đơn hàng. AS không mặc nhiên đọc lại database quyền người dùng ở mỗi refresh request trong mọi cấu hình. Nếu nghiệp vụ yêu cầu thay đổi có hiệu lực ngay, cần:

- Chủ động thu hồi authorization/refresh token liên quan.
- Có kiểm tra trạng thái quyền/tenant tại thời điểm cấp token mới, nếu chính sách đặt ở AS.
- Hoặc luôn kiểm tra object-level authorization tại RS thay vì tin mọi JWT claim cũ.
- Kiểm thử access token đã cấp **trước** khi thay đổi quyền và token được phát hành **sau** sự kiện thay đổi.

Không giả định refresh token rotation có thể tự đồng bộ mọi quyền nghiệp vụ.

## 9. Lưu trạng thái OAuth2Authorization và refresh token

### 9.1. Các repository/service phục vụ xử lý

| Thành phần | Nhiệm vụ | Tránh nhầm |
| --- | --- | --- |
| `RegisteredClientRepository` | Đăng ký Client và grant types, token settings | Không lưu refresh token đang hoạt động |
| `OAuth2AuthorizationService` | Lưu authorization, access/refresh token và metadata liên quan | Không thay `SecurityContext` của request login |
| `OAuth2AuthorizationConsentService` | Lưu quyết định consent khi cần | Không thay cho kiểm tra active của refresh token |
| `OAuth2TokenGenerator` | Phát token tương ứng với grant và settings | Không tự xác thực Client |
| `OAuth2RefreshTokenAuthenticationProvider` | Điều phối grant refresh token | Không xử lý form login Resource Owner |

Spring Authorization Server 1.x cung cấp triển khai in-memory để học tập và JDBC cho kho authorization theo tài liệu. Đối với production nhiều instance, cần kho dữ liệu/thiết kế chia sẻ trạng thái có đủ tính nhất quán để xử lý refresh token.

### 9.2. Tham chiếu token qua AuthorizationService

Ý tưởng tra cứu trạng thái (dạng minh họa trong code quản trị hoặc test):

~~~java
OAuth2Authorization authorization =
    authorizationService.findByToken(
        refreshTokenValue,
        OAuth2TokenType.REFRESH_TOKEN
    );

if (authorization == null) {
    // Không tồn tại hoặc không tra được authorization.
    // Tuyệt đối không phát access token.
}

OAuth2Authorization.Token<OAuth2RefreshToken> storedRefreshToken =
    authorization.getRefreshToken();

if (storedRefreshToken == null || !storedRefreshToken.isActive()) {
    // Token hết hạn, invalidated hoặc chưa active theo metadata.
    // Không phát token mới.
}
~~~

Các biến `authorizationService` và `refreshTokenValue` cần được cung cấp bởi ứng dụng/test, import `OAuth2Authorization`, `OAuth2TokenType`, `OAuth2RefreshToken` phù hợp. Đoạn mã trên **không thay thế `OAuth2RefreshTokenAuthenticationProvider`**. Nó chỉ minh họa API tra cứu và trạng thái; provider có trách nhiệm kiểm tra binding với client, scope và thực thi cấp token.

Không đưa đoạn code này vào controller công khai nhận raw refresh token rồi trả metadata cho bất kỳ caller nào. Chỉ tra cứu trong vùng bảo mật tin cậy và không log chuỗi refresh token.

### 9.3. Tính nguyên tử khi đổi token

Với rotation, hai request đến cùng lúc có thể đều cố sử dụng R1:

~~~mermaid
flowchart LR
    C["Hai request đồng thời với R1"]
    A["AS instance A"]
    B["AS instance B"]
    DB[("Authorization Store")]
    T{"Việc xác minh + thay thế R1<br/>có bảo đảm tính nhất quán?"}
    OK["Chỉ một request được refresh"]
    BAD["Nguy cơ hai request cùng thành công<br/>hoặc client lưu sai token mới"]

    C --> A
    C --> B
    A --> DB
    B --> DB
    DB --> T
    T -->|"Có"| OK
    T -->|"Không"| BAD
~~~

Trong hệ nhiều instance, chỉ dùng một repository có method `save(...)` **không tự chứng minh** quá trình read/check/update là atomic dưới concurrent load. Hãy kiểm tra transaction, optimistic/pessimistic locking hoặc cơ chế tuần tự hóa/compare-and-set tùy loại store. Test concurrency trên đúng hạ tầng lưu trữ triển khai; không chỉ test bằng `InMemoryOAuth2AuthorizationService`.

## 10. Client phải lưu và thay thế refresh token thế nào?

### 10.1. Backend hoặc BFF

Nếu client chạy trên server và có thể giữ credential an toàn, nên lưu refresh token ở server-side authorized-client store hoặc kho bí mật được bảo vệ. Trình duyệt chỉ giữ cookie phiên BFF với CSRF/XSS/cookie policy thích hợp.

~~~mermaid
flowchart TD
    B["Browser<br/>session cookie"]
    BFF["BFF / Backend OAuth2 Client<br/>authorized client manager"]
    DB[("Protected token store")]
    AS["Authorization Server<br/>/oauth2/token"]
    API["Resource Server"]

    B -->|"Request bằng cookie"| BFF
    BFF <--> DB
    BFF -->|"Dùng access token"| API
    BFF -->|"Refresh token khi cần"| AS
    AS -->|"Access token mới + RT theo policy"| BFF
    BFF -->|"Lưu thay token theo policy"| DB
~~~

Ưu điểm: không để refresh token trực tiếp trong mã JavaScript hoặc `localStorage` của browser. Vẫn phải phòng chống session hijacking, XSS có thể gọi API dưới phiên user, CSRF, log leak và truy cập trái phép kho token backend.

### 10.2. Spring Security OAuth2 Client có thể làm refresh tự động

Ở phía **OAuth2 Client** (ứng dụng gọi AS), một `OAuth2AuthorizedClientManager` có thể dùng provider hỗ trợ Authorization Code và Refresh Token:

~~~java
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientRepository authorizedClients) {

    OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
            .authorizationCode()
            .refreshToken()
            .build();

    DefaultOAuth2AuthorizedClientManager manager =
        new DefaultOAuth2AuthorizedClientManager(
            registrations, authorizedClients
        );

    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

Đoạn trên là **mảnh cấu hình dành cho ứng dụng Servlet OAuth2 Client**, không phải bean cần đưa vào Authorization Server chỉ để nó phát token. Cần import từ module `spring-security-oauth2-client`, có `ClientRegistrationRepository` và `OAuth2AuthorizedClientRepository` đã cấu hình.

Người gọi phải đưa đúng principal/authorized-client context cho manager; client library quản lý request refresh và lưu response trong cơ chế authorized client tương ứng. Không tự tái tạo endpoint refresh bằng cách gửi raw token ở browser nếu Spring OAuth2 Client đã đáp ứng trường hợp của bạn.

### 10.3. Ứng dụng mobile hoặc public client

Public client không thể chứng minh danh tính bằng một client secret được nhúng trong app. Chiến lược phát hành refresh token cho public client cần xét **khả năng bảo vệ token, rotation hoặc sender-constraining**, chính sách của AS và profile bảo mật hiện hành.

Đặc biệt với Spring Authorization Server 1.x, việc một client đăng ký `ClientAuthenticationMethod.NONE` và grant `REFRESH_TOKEN` **không tự đảm bảo AS mặc định sẽ cấp refresh token cho public client**. Cần kiểm tra khả năng/phần chính sách của phiên bản sử dụng; nếu yêu cầu public client có refresh token, thiết kế và kiểm thử rõ cơ chế bảo vệ thay vì giả định client sẽ nhận được token.

Nếu hệ thống quyết định cấp refresh token cho mobile, ứng dụng nên dùng secure storage của nền tảng (Keychain/Keystore tương đương), bảo vệ state/PKCE và hạn chế rò rỉ qua log/backup. Không coi secure storage là khả năng bảo vệ tuyệt đối khi thiết bị đã bị chiếm quyền.

### 10.4. Không lưu refresh token vào vị trí dễ đọc

Tránh:

- Đưa refresh token vào URL query, deep link, redirect URI, browser history hoặc analytics.
- Lưu trong `localStorage` của SPA mà không có đánh giá mối đe dọa và biện pháp bảo vệ tương ứng.
- Ghi refresh token vào console/log/tracing, crash report, email hoặc webhook.
- Lưu refresh token plaintext trong database không có kiểm soát truy cập, encryption-at-rest phù hợp, backup policy và audit.
- Chia sẻ cùng refresh token giữa nhiều client/device mà không có chiến lược phân tách thiết bị và vòng đời quyền.

## 11. Refresh token rotation, replay và sự cố mạng

### 11.1. Khi refresh thành công nhưng Client không nhận response

Ví dụ:

1. Client gửi R1 đến AS.
2. AS kiểm tra R1, vô hiệu R1 và phát R2.
3. AS lưu R2, trả response chứa access token mới + R2.
4. Mạng đứt; client không nhận được response.
5. Client chỉ còn R1, nhưng R1 đã không còn hợp lệ.

Client không nên lặp lại R1 vô hạn vì có thể bị AS xem là replay. Một số hệ có **grace period** hoặc idempotency policy riêng, nhưng điều này làm tăng cửa sổ có thể dùng lại token và cần thiết kế chặt. Spring Authorization Server không mặc định được giả định có mọi cơ chế phục hồi tùy biến này.

Trong nhiều ứng dụng, khi refresh đã thất bại không thể phục hồi an toàn, lựa chọn là bắt đầu một authorization/login mới phù hợp. Hành vi client phải xử lý rõ trạng thái lỗi, không tự động lưu token rỗng hoặc log raw credential để điều tra.

### 11.2. Khi hai request API cùng phát hiện access token hết hạn

Một BFF có thể tạo hai refresh request dùng cùng R1:

~~~text
API request A -> thấy A1 hết hạn -> refresh bằng R1
API request B -> thấy A1 hết hạn -> refresh bằng R1

AS (rotation):
  A có thể nhận R2 và thành công
  B dùng lại R1 có thể bị từ chối

Nếu B xử lý thất bại sai:
  - xóa authorized client đã có R2
  - ghi đè bằng R1 cũ
  - buộc người dùng login lại không cần thiết
~~~

Cần **đồng bộ một lần refresh cho mỗi authorized client** khi có nhiều request đồng thời, quản lý update token theo version/compare-and-set hoặc cơ chế phù hợp với store. Đối với nhiều BFF instance, local mutex trong một JVM có thể chưa đủ.

### 11.3. Reuse detection và family revocation

Mô hình nâng cao:

~~~mermaid
flowchart TD
    A["Client dùng R1 hợp lệ"]
    B["AS cấp R2, invalidated R1"]
    C{"R1 xuất hiện lại?"}
    D["Đánh dấu dấu hiệu replay"]
    E["Revoke refresh-token family<br/>hoặc yêu cầu re-authentication"]
    F["Tiếp tục khi token hợp lệ"]

    A --> B --> C
    C -->|"Có"| D --> E
    C -->|"Không"| F
~~~

Đây là **chính sách bảo mật cần được thiết kế**, không phải lời khẳng định `reuseRefreshTokens(false)` tự tạo một family tree hoặc tự revoke toàn bộ family khi phát hiện reuse. Nếu triển khai replay detection:

- Phân biệt retry do mạng/đồng thời với dấu hiệu đánh cắp.
- Không tiết lộ cho attacker rằng token family của một user cụ thể tồn tại.
- Có audit/alert và policy sự cố rõ ràng.
- Kiểm tra khả năng revoke hiệu lực của access token đang tồn tại: JWT tự xác minh ở RS có thể còn hợp lệ đến khi `exp`.

## 12. Thu hồi refresh token, logout và thay đổi quyền

### 12.1. Token Revocation Endpoint

RFC 7009 định nghĩa token revocation. Khi AS hỗ trợ, client có thể yêu cầu thu hồi refresh token:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <encoded-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=REFRESH_TOKEN_VALUE&token_type_hint=refresh_token
~~~

Cần dùng endpoint URI thực tế do AS metadata/settings công bố. `token_type_hint` chỉ giúp AS nhận diện loại token; AS phải xác minh caller và chính sách revocation. Một phản hồi HTTP thành công của revocation endpoint **không phải lời hứa rằng mọi JWT access token đã phát hành sẽ lập tức bị RS từ chối**.

### 12.2. Logout có thể cần nhiều hành động

| Hành động | Tác động chính | Giới hạn |
| --- | --- | --- |
| Xóa cookie phiên BFF | Browser mất phiên BFF | Refresh token server-side có thể vẫn tồn tại nếu không xóa/revoke |
| Xóa authorized client tại BFF | Client không còn dùng credential đã lưu | AS có thể chưa biết token đã bị xóa |
| Revoke refresh token tại AS | Không còn đổi access token mới bằng refresh token đó theo chính sách | Access token cũ có thể còn hiệu lực |
| Revoke authorization/token family | Vô hiệu hóa các token/grant liên quan theo implementation | Cần kiểm tra các RS có thực thi revoke ngay không |
| Đăng xuất phiên tại AS | Thay đổi phiên login browser ở AS | Không tự suy ra mọi grant đã cấp bị thu hồi |
| OIDC RP-Initiated Logout | Điều phối logout ở OIDC Provider nếu hỗ trợ | Không mặc nhiên thay OAuth2 Token Revocation |

Khi user mất quyền, xóa tài khoản hoặc nghi ngờ thiết bị bị chiếm, phải xác định rõ **phải chấm dứt cái gì**: browser session, refresh token, access token, user grants hay tất cả.

### 12.3. Revocation và RS dùng JWT/opaque

- RS chỉ verify JWT cục bộ thường không biết AS vừa revoke refresh token hoặc authorization. Access token JWT đã cấp có thể tiếp tục được chấp nhận tới hết hạn, trừ khi RS có kiểm tra bổ sung như denylist, token version hoặc trạng thái nghiệp vụ.
- RS dùng opaque introspection có thể nhận `active: false` sau revocation, nhưng cache response có thể tạo độ trễ.
- Giảm TTL access token giúp giới hạn khoảng thời gian token bị lộ còn có thể sử dụng, nhưng tăng tải refresh và không thay thế chiến lược phản ứng sự cố.

## 13. Kiểm thử refresh token grant

### 13.1. Ma trận kiểm thử bắt buộc

| Ca | Dữ kiện | Kết quả mong đợi |
| --- | --- | --- |
| Refresh hợp lệ | R1 active, đúng client, có grant, scope hợp lệ | Cấp access token mới |
| R1 hết hạn | Đồng hồ test vượt `expiresAt` | `invalid_grant`, không phát access token |
| R1 đã revoked/invalidated | Authorization store ghi token không active | Từ chối |
| R1 không tồn tại | Token bất kỳ không có trong store | Từ chối |
| Dùng access token như refresh token | Giá trị token sai loại | Từ chối |
| Client secret sai | Confidential client auth thất bại | `invalid_client` hoặc lỗi theo auth method |
| Client B đổi R1 thuộc Client A | Ràng buộc client sai | Từ chối |
| Client không được grant refresh | Registration không có `REFRESH_TOKEN` | Từ chối |
| Scope đúng bằng scope đã cấp | Không xin thêm quyền | Thành công nếu các điều kiện khác đạt |
| Xin scope là tập con | `scope=booking.read` khi đã cấp nhiều scope | Có thể thành công với phạm vi thu hẹp |
| Xin scope ngoài authorized scopes | `scope=admin` không được cấp | `invalid_scope`, không phát token |
| Reuse mode | `reuseRefreshTokens(true)` | R1 vẫn được trả/dùng theo chính sách khi còn active |
| Rotation mode | `reuseRefreshTokens(false)` | Token mới R2; R1 không được phép refresh lại |
| Dùng lại R1 sau rotation | R1 đã được thay | Từ chối; kiểm tra replay policy nếu có |
| Hai refresh request đồng thời | Cùng R1, nhiều instance | Không được phá tính một lần hoặc mất đồng bộ token |
| AS restart/failover | Token đã cấp trước restart | Phù hợp policy persistence và trạng thái |
| Quyền user bị gỡ | R1 còn hạn nhưng quyền thay đổi | Thực hiện chính sách thu hồi/kiểm tra được yêu cầu |
| Refresh token bị lộ vào log | Mô phỏng log/tracing | Đảm bảo redaction và audit phù hợp |

### 13.2. Thử nghiệm ở mức HTTP

Test tích hợp với confidential client đã đăng ký:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <valid-client-basic-credential>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=VALID_R1&scope=booking.read
~~~

Trước request này, test cần **thực sự có R1** được AS cấp từ grant hợp lệ; đừng tự đặt một chuỗi giả và chờ refresh thành công. Sau response:

1. Assert HTTP 200 và `token_type=Bearer`.
2. Assert có `access_token` mới, thời hạn phù hợp và token đủ scope.
3. Nếu rotation, assert refresh token trả về khác R1 và R1 bị từ chối ở request sau.
4. Nếu reuse, assert R1 còn được dùng theo policy và không vượt TTL.
5. Dùng access token mới gọi RS để xác minh issuer/audience/scope và quyền dữ liệu.

### 13.3. Spring Security Test: test nào đủ và test nào chưa?

`@WithMockUser` và `jwt()` trong `spring-security-test` hữu ích khi test các rule authorization. Nhưng chúng **không chứng minh refresh token thật đã qua provider**, client authentication và authorization store.

Để kiểm tra grant refresh:

- Dùng MockMvc hoặc HTTP test client với context AS thật.
- Khởi tạo registered client, authorization service và token generator/keys có thể kiểm tra.
- Lấy refresh token từ một authorization flow hợp lệ hoặc fixture tạo authorization/token metadata đúng.
- Gửi request tới `/oauth2/token` qua security filters.
- Kiểm tra response và trạng thái authorization đã cập nhật.
- Bổ sung test concurrency nếu production có nhiều worker/instance.

### 13.4. Test không nên dựa vào thứ tự lỗi nội bộ

Nếu request có cùng lúc client secret sai và refresh token hết hạn, AS có thể dừng ở bước client authentication. Muốn chứng minh refresh token hết hạn bị chặn, hãy dùng **client credential hợp lệ**. Muốn chứng minh client binding, dùng hai clients đều đăng ký đúng grant nhưng token thuộc chỉ một client.

Mục tiêu là chứng minh **mỗi điều kiện bảo mật được áp dụng**, không phải chỉ thấy một HTTP 400 bất kỳ.

## 14. Quan sát và xử lý sự cố

| Triệu chứng | Khả năng | Hướng điều tra |
| --- | --- | --- |
| Token endpoint trả `invalid_grant` | Refresh token sai, hết hạn, bị revoke, đã rotation hoặc client mismatch | Kiểm tra trạng thái trong `OAuth2AuthorizationService` và client binding; không log raw R1 |
| Token endpoint trả `invalid_client` | Secret/certificate/client auth method sai | Kiểm tra `RegisteredClient` và xác thực client |
| Trả `invalid_scope` | Client xin scope vượt `authorizedScopes` | So scope requested với authorization thực sự, không chỉ registration |
| Client không nhận được refresh token ban đầu | Grant/client type/policy không cho phát | Kiểm tra grant ban đầu, phương thức client authentication và logic phát hành của SAS phiên bản đó |
| Đổi token thành công nhưng RS trả 401 | Issuer/audience/chữ ký token sai hoặc RS dùng sai decoder | Kiểm tra token mới và cấu hình RS |
| Hai request refresh gây logout ngẫu nhiên | Rotation race; authorized-client store bị ghi đè | Đồng bộ refresh, kiểm tra version/compare-and-set |
| Sau restart refresh token không còn hiệu lực | Authorization chỉ lưu in-memory hoặc dữ liệu không đồng bộ | Kiểm tra persistence, migration, failover |
| JWT cũ vẫn truy cập API sau revoke R1 | RS verify JWT local, không kiểm tra revocation | Điều chỉnh TTL/denylist/introspection theo chính sách |
| Rotation kéo dài login vô hạn | Thiếu absolute session lifetime | Thêm chính sách trần thời gian và re-authentication |
| AS/DB chậm khi lượng refresh tăng | TTL quá ngắn, retry storm, truy vấn token chậm | Benchmark, giới hạn retry, index/store tuning, rate limit |
| Refresh token xuất hiện trong log | Log body/header hoặc dump lỗi | Redact, đổi/revoke credential bị lộ, kiểm tra retention |

### 14.1. Trình tự chẩn đoán một refresh failure

1. Token endpoint có đúng issuer/URL không? Có dùng HTTPS không?
2. Request có `grant_type=refresh_token`, một token thực, method xác thực client phù hợp không?
3. `RegisteredClient` nào đã được nhận diện, client có được phép refresh không?
4. Authorization store có bản ghi của refresh token không, và token có active không?
5. `registeredClientId` của authorization có trùng client đang yêu cầu không?
6. Scope được xin có nằm trong `authorizedScopes` không?
7. Có rotation trước đó, request đồng thời, retry hoặc response bị mất không?
8. Có chính sách riêng về account status, consent, tenant, absolute session lifetime không?
9. Nếu AS trả token thành công nhưng API lỗi, kiểm tra độc lập issuer/audience/scope ở RS.

Nên log request ID/correlation ID, loại lỗi, client ID đã được kiểm soát, trạng thái provider, thời gian xử lý, và **hash định danh một chiều có khóa hoặc mã audit riêng cho token** nếu thực sự cần tương quan; không log raw refresh token, access token, client secret hoặc full request body.

## 15. Tình huống thiết kế thực tế

### 15.1. Booking BFF với user login qua trình duyệt

Yêu cầu: user dùng web lâu, không muốn login lại mỗi 5 phút; hệ thống có server-side BFF.

**Thiết kế có thể phù hợp:**

- Authorization Code + PKCE để lấy grant ban đầu.
- Confidential client backend xác thực tại token endpoint.
- Access token TTL tương đối ngắn và refresh token được lưu server-side.
- Rotation hoặc reuse tùy yêu cầu bảo mật/trải nghiệm và khả năng xử lý concurrency.
- Có logout/revocation, absolute lifetime, session policy và kiểm tra quyền ở RS.
- Không trao refresh token trực tiếp cho browser.

### 15.2. Dịch vụ chạy máy với Client Credentials

Yêu cầu: job đồng bộ dữ liệu gọi API hàng giờ, không có Resource Owner.

**Định hướng:** Client Credentials Grant cho phép client xin access token mới trực tiếp bằng cách xác thực client tại token endpoint. Refresh token thường **không cần thiết** và RFC 6749 khuyến nghị không phát cho grant này. Khi access token hết hạn, client có thể lặp lại client credentials grant theo chính sách; không tìm cách tự tạo refresh token giả.

### 15.3. Mobile app cần sử dụng dài ngày

Yêu cầu: không có backend giữ client secret, người dùng muốn ít phải đăng nhập lại.

**Định hướng:** đánh giá xem AS và phiên bản Spring đang dùng có cơ chế cấp refresh token an toàn cho public client hay không; nếu có, cần rotation hoặc sender-constrained token phù hợp, secure storage, cách xử lý mất token/race và hành vi khi bị compromise. Việc đăng ký `NONE` với `REFRESH_TOKEN` chỉ là một phần, không bảo đảm tất cả logic production đã được cung cấp mặc định.

### 15.4. Admin portal có chính sách khóa quyền tức thì

Yêu cầu: khi nhân viên bị thu hồi quyền, không được xin thêm access token.

**Định hướng:** ngoài việc bảo vệ refresh token, AS cần có logic revoke grant/token hoặc kiểm tra account status/consent phù hợp. RS phải có chính sách chống dùng access token đã cấp trước đó cho các thao tác nhạy cảm; không dựa duy nhất vào rotation hoặc logout browser.

## 16. Những sai lầm cần tránh

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Gửi refresh token đến Resource Server | Credential nhạy cảm bị phân tán | Chỉ gửi tới token endpoint/revocation của AS |
| Cho Client B đổi refresh token của Client A | Phá ràng buộc client và quyền | Kiểm tra `registeredClientId` và client authentication |
| Cho phép scope mới chỉ vì có trong `RegisteredClient.getScopes()` | Vượt consent/quyền của grant ban đầu | Dùng `authorizedScopes` làm giới hạn |
| Dùng refresh token đã invalidated để phát access token | Replay, duy trì quyền trái phép | Kiểm tra `isActive()` và trạng thái store |
| Hiểu `reuseRefreshTokens(false)` là tự có family revocation | Không phát hiện/khắc phục đánh cắp toàn diện | Thiết kế replay handling riêng |
| Rotation mà Client không cập nhật R2 | Lần refresh sau thất bại | Cập nhật authorized-client store an toàn, atomic |
| Hai request cùng refresh không có đồng bộ | Race, mất credential mới | Single-flight refresh và optimistic locking phù hợp |
| Chỉ lưu authorization trong memory khi có nhiều AS instances | Mất trạng thái refresh sau restart/failover | Persistence chia sẻ, kiểm thử HA |
| Cho rằng thu hồi R1 lập tức làm JWT A1 vô hiệu ở RS | JWT verify local vẫn hợp lệ đến hết hạn | Thiết kế TTL và revocation ở RS |
| Đưa refresh token vào localStorage/log/query | Rủi ro credential theft | Backend/BFF/secure storage và redaction phù hợp |
| Bỏ xác thực confidential client tại refresh endpoint | Caller không chứng minh client hợp lệ | Dùng phương thức đăng ký, tuân thủ RFC 6749 |
| Cấp refresh token vô thời hạn | Truy cập kéo dài không kiểm soát | TTL, absolute lifetime và reauthentication |
| Cấp refresh token cho Client Credentials chỉ để khỏi gọi login | Sai ngữ nghĩa grant | Dùng client credentials xin access token mới |
| Tạo handler refresh riêng không kiểm tra revoke/scope | Phát token sai quyền | Ưu tiên `OAuth2RefreshTokenAuthenticationProvider` mặc định |

## 17. Checklist triển khai

- [ ] `RegisteredClient` có grant `REFRESH_TOKEN` và client auth method được cấu hình đúng.
- [ ] Hiểu rõ grant ban đầu có phát refresh token cho loại client đó hay không.
- [ ] Phân biệt access token, refresh token, authorization code, ID token.
- [ ] Token endpoint xác thực client và so refresh token với client binding.
- [ ] Refresh token còn active, chưa hết hạn và chưa bị invalidated.
- [ ] Scope yêu cầu không vượt `OAuth2Authorization.authorizedScopes`.
- [ ] TTL access/refresh token được chọn theo chính sách, có absolute session lifetime nếu cần.
- [ ] `reuseRefreshTokens` được chọn chủ đích; nếu rotation, xử lý update token và race.
- [ ] Có chính sách revoke, logout, quyền user bị thay đổi, compromise/replay.
- [ ] Authorization store phù hợp nhiều instance và có kiểm thử concurrency.
- [ ] Client lưu refresh token an toàn, không log hoặc gửi tới RS.
- [ ] Có test refresh success, expired, wrong client, wrong scope, reuse, rotation, replay.
- [ ] Đã xác minh RS chấp nhận access token mới với issuer, audience và scope đúng.
- [ ] Có monitoring lỗi `invalid_grant`, `invalid_client`, hiệu năng DB và event bất thường.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao client có refresh token hợp lệ không cần Resource Owner nhập password mỗi lần access token hết hạn?

**Đáp án:** AS đã lưu authorization/grant và xác minh refresh token cùng ràng buộc client, scope, expiry khi client yêu cầu token mới. Đăng nhập người dùng ban đầu và token refresh là hai giai đoạn khác nhau.

**Câu 2.** Client A có thể đổi refresh token cấp cho Client B nếu biết chuỗi token và có quyền scope tương tự không?

**Đáp án:** Không. AS phải đối chiếu refresh token với authorization/registered client cụ thể và xác thực caller theo phương thức đăng ký.

**Câu 3.** Cấu hình `reuseRefreshTokens(false)` có tự bảo đảm phát hiện replay và revoke toàn bộ token family không?

**Đáp án:** Không tự mặc định như vậy. Nó biểu thị chính sách phát refresh token mới, còn family tracking, replay detection, incident response và absolute lifetime cần đánh giá và có thể cần tùy biến.

**Câu 4.** Scope ban đầu là `booking.read`. Khi refresh có thể xin `booking.write` nếu scope này nằm trong RegisteredClient không?

**Đáp án:** Không. Phạm vi được cấp trong authorization ban đầu mới là giới hạn, client không thể tự nâng quyền chỉ qua refresh token grant.

**Câu 5.** Với Client Credentials, có nhất thiết phải có refresh token để hệ thống chạy liên tục không?

**Đáp án:** Không. Client có thể dùng client credentials để xin access token mới khi cần; RFC 6749 khuyến nghị không phát refresh token cho grant này.

**Câu 6.** Tại sao logout khỏi browser không nhất thiết vô hiệu mọi access token đã phát hành?

**Đáp án:** Session browser, refresh token và access token có vòng đời riêng. JWT đã cấp có thể còn được RS xác minh cục bộ cho đến hết hạn nếu không có cơ chế revoke bổ sung.

**Câu 7.** Hai request cùng dùng R1 dưới rotation có nguy cơ gì?

**Đáp án:** Một request có thể nhận R2, request kia bị từ chối do R1 đã invalidated; nếu client/store xử lý sai, token mới có thể bị ghi đè hoặc phiên bị xóa nhầm. Cần kiểm soát concurrent refresh.

## 19. Tài liệu tham khảo và kết luận

Tài liệu chính thức, nên đối chiếu theo đúng phiên bản Spring đang chạy:

- [RFC 6749 — OAuth 2.0, Refreshing an Access Token (Section 6)](https://www.rfc-editor.org/rfc/rfc6749#section-6)
- [RFC 6749 — Refresh Token (Section 1.5)](https://www.rfc-editor.org/rfc/rfc6749#section-1.5)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Core Model and Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Security — OAuth2 Client Authorized Client Manager](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html)
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)

**Tổng kết:** Để đổi refresh token thành access token mới, Authorization Server phải xác thực/nhận diện **đúng client**, tra **đúng refresh token** còn active trong `OAuth2AuthorizationService`, tôn trọng **grant type và authorized scopes**, phát access token theo `TokenSettings` và xử lý refresh token theo chính sách **reuse hoặc rotation**. Bảo mật refresh token không kết thúc khi trả HTTP 200: phải quản lý lưu trữ, replay, revoke, token family, session lifetime và kiểm thử đồng thời. Phân tách đúng trách nhiệm giữa AS, OAuth2 Client và Resource Server là điều kiện để duy trì phiên an toàn trong hệ thống OAuth 2.0/OIDC.

