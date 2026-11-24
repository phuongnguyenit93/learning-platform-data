# Opaque token và trạng thái server

Giả sử `orders-api` nhận access token `T1` từ một ứng dụng đã được người dùng cấp quyền đọc đơn hàng. Lúc 10:00, người dùng chọn **Thu hồi quyền truy cập**; Authorization Server (AS) cập nhật trạng thái token thành `REVOKED`. Lúc 10:01, một bản sao `T1` bị đánh cắp tiếp tục gọi API. Làm cách nào Resource Server (RS) biết `T1` đã bị thu hồi khi bản thân token chỉ là chuỗi khó đoán, không chứa một JWT payload có thể giải mã?

**Opaque token** giải quyết một phần bài toán bằng cách làm cho credential trở thành **tham chiếu không tự mô tả**: RS không suy ra user, scope, audience hay trạng thái từ chuỗi token mà phải dùng một **nguồn trạng thái đáng tin** như Authorization Server, token store hoặc **OAuth 2.0 Token Introspection (RFC 7662)**. Khi AS đổi trạng thái token, lần xác minh tiếp theo có thể thấy token không còn active. Tuy nhiên, nếu RS đang cache kết quả introspection, việc thu hồi **có thể chưa có hiệu lực tức thì**.

Bài thuộc chương **Revocation** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Chủ đề liên kết mô hình tin cậy/vòng đời token, phân biệt JWT và opaque token, access/refresh token, scope, audience, claims, lưu trữ, revocation và phòng chống đánh cắp/phát lại trong OAuth 2.0 và OIDC.

> **Tư tưởng quan trọng:** Opaque token không đồng nghĩa “an toàn tuyệt đối”, “không bao giờ bị replay” hay “thu hồi luôn tức thì”. Giá trị cốt lõi là **metadata và trạng thái sử dụng do hệ thống tin cậy quản lý**, còn mức độ thu hồi nhanh phụ thuộc cơ chế RS kiểm trạng thái, chính sách cache, độ sẵn sàng và cách phân quyền.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích opaque token là gì, tại sao **không thể phân quyền chỉ bằng cách nhìn chuỗi token**, và vì sao nó thường được dùng như *reference token*.
2. Mô tả vòng đời phát hành, sử dụng, hết hạn, thu hồi, xoay vòng và vô hiệu hóa token trong token store phía AS.
3. Phân biệt **opaque access token**, **opaque refresh token**, **JWT access token** và **ID token** về mục đích, định dạng, trạng thái và bên nhận.
4. Sử dụng đúng **RFC 7662 Token Introspection**: request, `active=true/false`, metadata, authentication của RS và xử lý dữ liệu trả về.
5. Phân biệt **RFC 7009 Token Revocation** với introspection; giải thích vì sao `HTTP 200` ở revocation endpoint không chứng minh token từng tồn tại.
6. Thiết kế Resource Server kiểm issuer, audience, expiry, scope, client, principal/tenant, quyền trên tài nguyên và sender proof.
7. Đánh giá trade-off **cache introspection, độ trễ, tính sẵn sàng và thời gian hiệu lực revocation** thay vì hứa thu hồi tức thì mà không đo.
8. Viết code minh họa tạo opaque credential bằng `SecureRandom`, lưu fingerprint/token state và cấu hình Spring Security Resource Server.
9. Thiết kế phát hiện refresh-token replay, family revocation, race conditions, incident response và audit an toàn.
10. Xây dựng ma trận kiểm thử end-to-end chống token reuse, token theft, wrong audience/scope/tenant và stale cache.

## 2. Opaque token là gì? Không tự mô tả không đồng nghĩa không có metadata

**Opaque token** là token mà bên sử dụng **không dựa vào cấu trúc nội tại để hiểu hoặc xác minh claims**. Nó có thể là chuỗi ngẫu nhiên có entropy cao, ví dụ:

~~~text
aNlmLa7ohpTczQ7R3N-4hhPv0PQ8jNo8cBW7nSkFNcs
~~~

Chuỗi ví dụ ở đây chỉ để minh họa định dạng. Khi nhận nó, RS **không thể đọc trực tiếp** `sub`, `aud`, `scope`, `exp` hoặc `status`. Các trường đó có thể nằm trong token store tại AS và được trả thông qua introspection/lookup đáng tin.

### 2.1. JWT và opaque: khác cách mang thông tin

| Đặc điểm | Opaque access token | JWT access token |
|---|---|---|
| Dạng bên ngoài | Thường là chuỗi không có claims công khai. | Thường là JWS compact có header/payload/signature; có thể profile khác. |
| RS đọc claims bằng cách nào? | Introspection hoặc server-side trusted lookup. | Decode và **xác minh** signature/issuer/audience/time/profile. |
| Trạng thái thu hồi | Có thể tra ở token store khi mỗi lần cần kiểm. | Phải bổ sung state/denylist/introspection hoặc chờ `exp` nếu offline-only. |
| Độ độc lập với AS | Thường phụ thuộc dịch vụ tra token trực tuyến hoặc cache. | Có thể validate offline bằng JWKS cached. |
| Chi phí mỗi lần xác minh | Network/lookup/cache tùy thiết kế. | Crypto + local validation, có thể không gọi AS. |
| Claims lộ nếu token bị xem? | Chuỗi token không tự bộc lộ claims. | Payload JWS thường **không được mã hóa**, ai thấy token có thể đọc claims. |
| Có bị replay khi lộ? | **Có**, nếu là bearer token còn hợp lệ. | **Có**, nếu là bearer token còn hợp lệ. |
| Quyền quyết định cuối cùng | AS + RS policies/metadata. | AS-issued claims + RS policies, có thể kèm state. |

**Không suy ra opaque token luôn là random token**, hay JWT luôn phải có ba đoạn. Opaque ở góc nhìn RS là **không thể tự diễn giải theo hợp đồng**, và hai định dạng token có thể được AS kết hợp. Một access token hoàn toàn có thể là opaque dù OP đồng thời phát **ID token dạng JWT** trong OIDC.

### 2.2. Opaque token không phải refresh token theo định nghĩa

Hai chiều phân loại độc lập:

~~~text
Purpose:
  ACCESS_TOKEN
  REFRESH_TOKEN
  ID_TOKEN (OIDC)
  AUTHORIZATION_CODE

Representation:
  OPAQUE
  STRUCTURED/JWT
~~~

Ví dụ một AS có thể cấp:

- **Opaque access token** cho Orders API, được kiểm qua introspection.
- **Opaque refresh token** cho confidential BFF, chỉ được trình tới token endpoint khi refresh.
- **JWT ID token** cho OIDC Client, có `aud` là chính client.
- **Authorization code** là chuỗi ngắn hạn dùng một lần, không thể dùng làm access token.

RS **không nhận refresh token** để gọi API; token endpoint không dùng opaque access token làm client secret; **ID token không được gửi làm bearer access token** chỉ vì cùng issuer.

### 2.3. “Opaque” không có nghĩa AS không biết token thuộc ai

AS có thể lưu metadata như:

~~~json
{
  "token_reference": "internal-record-9841",
  "kind": "ACCESS_TOKEN",
  "issuer": "https://login.example.com",
  "subject": "user-742",
  "client_id": "shop-bff",
  "audience": ["orders-api"],
  "scopes": ["orders:read"],
  "tenant_context": ["tenant-beta"],
  "issued_at": "2026-11-23T10:00:00Z",
  "expires_at": "2026-11-23T10:10:00Z",
  "status": "ACTIVE"
}
~~~

Đây là **server-side record minh họa**, không phải token response chuẩn RFC. `tenant_context` là dữ liệu chính sách nội bộ và không tự là OAuth standard claim bắt buộc. **Không trả thẳng database record cho client**; chỉ trả metadata cần thiết qua channel có phân quyền.

## 3. Mô hình tin cậy: ai cấp, ai kiểm, ai thu hồi?

- **Authorization Server (AS)** phát access/refresh tokens, giữ trạng thái/grant và xử lý revocation/introspection theo chính sách.
- **OAuth Client** nhận và lưu token, gọi Resource Server; confidential client xác thực với AS khi protocol yêu cầu.
- **Resource Server (RS)** nhận access token, xác minh nó **được chấp nhận cho chính API** và kiểm quyền trên resource.
- **Resource Owner/End-User** có thể rút consent/grant khi hệ thống hỗ trợ; không nhất thiết trực tiếp có mặt trong Client Credentials Grant.
- **OpenID Provider (OP)** là AS có chức năng OIDC; việc user logout hoặc UserInfo access **không tự thu hồi mọi access token**.

### 3.1. Luồng dùng opaque access token

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    participant ST as Trusted Token Store
    participant RS as Orders Resource Server

    C->>AS: Authorization Code grant + PKCE, client auth khi cần
    AS->>ST: Lưu token fingerprint + grant metadata, ACTIVE
    AS-->>C: opaque access token T1 + expires_in
    C->>RS: GET /orders/42, Authorization Bearer T1
    RS->>AS: POST /introspect token=T1, RS auth
    AS->>ST: Lookup token và kiểm state/time/policy
    ST-->>AS: ACTIVE + subject/client/aud/scope metadata
    AS-->>RS: active=true + metadata được phép công bố
    RS->>RS: Kiểm audience, scope, tenant, object authorization
    RS-->>C: 200 hoặc 403 tùy chính sách
~~~

Dù `active=true`, RS còn phải kiểm scope và quyền bản ghi; người dùng có `orders:read` không mặc nhiên được xem đơn của tenant khác.

### 3.2. Revocation đi qua những lớp nào?

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User hoặc Authorized Client
    participant AS as Authorization Server
    participant ST as Token Store
    participant RS as Resource Server
    participant Cache as Introspection Cache

    U->>AS: Yêu cầu thu hồi grant/token (đã xác thực)
    AS->>ST: Đánh dấu REVOKED / revoke token family theo policy
    AS-->>U: Kết quả xử lý
    RS->>Cache: Tra metadata T1
    alt Không có cache hoặc cache đã hết hạn
      RS->>AS: Introspect T1
      AS->>ST: Kiểm trạng thái mới
      ST-->>AS: REVOKED
      AS-->>RS: {"active":false}
      RS-->>RS: Từ chối Bearer T1
    else Cache vẫn ghi ACTIVE
      Cache-->>RS: active=true (stale)
      RS->>RS: Có nguy cơ chấp nhận T1 đến lúc cache hết hạn
    end
~~~

**Bản ghi server-side bị revoke không đồng nghĩa mọi RS đã biết ngay.** Phải xét cache, replica lag, request đang chạy, network partitions và cả middleware có giữ authentication context trước khi revocation xảy ra.

## 4. Vòng đời token và state machine

### 4.1. Trạng thái điển hình

~~~mermaid
stateDiagram-v2
    [*] --> ISSUED
    ISSUED --> ACTIVE: Commit issuance
    ACTIVE --> EXPIRED: now >= expiresAt
    ACTIVE --> REVOKED: Explicit revocation / grant cancellation
    ACTIVE --> SUSPENDED: Risk or policy hold
    SUSPENDED --> REVOKED: Confirmed compromise
    SUSPENDED --> ACTIVE: Policy-approved restoration
    REVOKED --> [*]
    EXPIRED --> [*]
~~~

Sơ đồ là **mô hình nội bộ**, không phải các trường status bắt buộc của OAuth RFC. Một hệ thống có thể chỉ lưu `revoked_at` và `expires_at`, rồi tính trạng thái active khi lookup. “EXPIRED” thường là **trạng thái suy ra từ đồng hồ**, không cần background job ghi lại mọi record đúng giây hết hạn.

### 4.2. Điều kiện active có thể là một phép tính

~~~text
isActive(token, now):
    token exists
    AND token.issuanceCommitted
    AND token.revokedAt == null
    AND now < token.expiresAt
    AND now >= token.notBefore (if defined)
    AND token.grant is active
    AND client/user/policy state permits continued use
    AND required binding/purpose constraints are satisfied
~~~

Không phải mọi AS tính toàn bộ các điều kiện phía trên theo đúng công thức; **contract introspection và revocation policy phải được xác định rõ**. RFC 7662 dùng `active` cho trạng thái hiệu lực theo AS nhưng không thay mọi authorization check tại RS.

### 4.3. Không nhầm trạng thái token với trạng thái phiên

| Đối tượng | Ví dụ | Vòng đời và ảnh hưởng |
|---|---|---|
| **Access token** | T1, TTL 10 phút | Hết hạn, revoke hoặc bị chặn theo policy. |
| **Refresh token** | R1, TTL dài hơn | Có thể bị rotate/revoke để ngăn xin access token mới. |
| **Refresh token family** | R1 → R2 → R3 | Reuse R1 có thể làm cả family bị khóa. |
| **OAuth grant/consent** | User cho `orders:read` | Rút grant có thể ngăn phát token mới; tác động token cũ tùy AS/RS. |
| **Client registration** | `shop-bff` active | Disable client thường ngăn cấp token mới, nhưng token cũ cần revocation semantics riêng. |
| **Browser/BFF session** | Session cookie `SID` | Logout session không nhất thiết revoke mọi token đã cấp. |
| **User account/tenant membership** | `user-742` bị khóa | RS/AS phải có chính sách cập nhật quyền; token còn hạn không tự biết thay đổi. |

### 4.4. “Revoke access token” và “revoke grant” khác nhau

AS có thể thu hồi **một** access token hoặc toàn bộ **grant/token family**, tùy yêu cầu/chính sách. Revocation một refresh token có thể ảnh hưởng access tokens liên quan theo chính sách. **Không đoán** rằng thu hồi T1 luôn thu hồi R1, hoặc thu hồi R1 luôn vô hiệu ngay mọi JWT/offline-cached access token.

### 4.5. Trạng thái không được hồi sinh sau REVOKED

Một token bị revoke không nên được **khôi phục lại ACTIVE** chỉ vì replica chậm, cache cũ hoặc worker đồng bộ trễ. Nếu nghiệp vụ cần cấp lại quyền, phát **token mới** với token ID/fingerprint mới và grant mới/hợp lệ; không “unrevoke” một bearer credential có thể đã bị lộ.

## 5. Phát hành opaque token: entropy, tính duy nhất và lookup

### 5.1. Dùng CSPRNG

Opaque bearer token phải khó đoán. Một cách phổ biến là sinh **32 byte ngẫu nhiên bằng `SecureRandom`** và encode bằng **Base64URL không padding**, cho chuỗi khoảng **43 ký tự**.

Không tạo token bằng:

- User ID + timestamp.
- `Math.random()` hoặc UUID quá ít entropy nếu không được đánh giá rõ.
- Tăng counter/id của database rồi Base64.
- SHA-256 của email, client ID hoặc ngày hiện tại.
- Chuỗi có thể đoán từ session/cookie/hostname.

### 5.2. Java 17: sinh token và fingerprint SHA-256

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;

public final class OpaqueAccessTokens {
    private static final SecureRandom RANDOM = new SecureRandom();

    private OpaqueAccessTokens() {}

    public static String generate() {
        byte[] bytes = new byte[32];  // 256 random bits.
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(bytes);
    }

    public static String sha256Fingerprint(String token) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(token.getBytes(StandardCharsets.US_ASCII));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

**Giới hạn của ví dụ:** SHA-256 fingerprint là cách đơn giản để tránh lưu **raw token** trong token store đối với token **ngẫu nhiên, entropy cao**. Nó **không phải cơ chế đủ để bảo vệ mật khẩu yếu** hoặc token có thể đoán. Trong hệ thống yêu cầu bảo vệ mạnh hơn, có thể dùng **HMAC fingerprint với key riêng trong Secret Manager/HSM**, tách quyền đọc key và database. Khi dùng HMAC key rotation phải thiết kế lookup/migration; không hardcode key trong source.

### 5.3. Lưu fingerprint thay raw token khi phù hợp

~~~text
Raw opaque token sent to client:
  T1 = high-entropy random Base64URL string

Server:
  lookupKey = SHA256(T1) or HMAC(key, T1)
  record[lookupKey] = {
    client, subject, grant, resource, scopes,
    issuedAt, expiresAt, revokedAt, tokenType
  }

At introspection:
  lookupKey = sameFingerprint(providedToken)
  record = database.get(lookupKey)
~~~

Nếu raw token bị ghi ra log, nó vẫn là bearer credential; **hash tại database không làm raw token an toàn để log**. Metadata trong token store chứa danh tính, scopes, grants và quyền nên vẫn cần encryption-at-rest, RBAC, audit, backup protection và retention.

### 5.4. Database schema minh họa

~~~sql
CREATE TABLE oauth_access_tokens (
    token_fingerprint   CHAR(64) PRIMARY KEY,
    issuer_id           VARCHAR(255) NOT NULL,
    client_id           VARCHAR(160) NOT NULL,
    principal_type      VARCHAR(32) NOT NULL,
    subject_id          VARCHAR(255) NOT NULL,
    grant_id            VARCHAR(120) NOT NULL,
    audience_ref        VARCHAR(255) NOT NULL,
    scope_set_json      TEXT NOT NULL,
    issued_at           TIMESTAMP NOT NULL,
    not_before          TIMESTAMP NULL,
    expires_at          TIMESTAMP NOT NULL,
    revoked_at          TIMESTAMP NULL,
    revoke_reason       VARCHAR(64) NULL,
    version             BIGINT NOT NULL DEFAULT 0
);
~~~

Đây là schema **minh họa duy nhất** (không phải DDL portable hoàn chỉnh). `scope_set_json`/tenant entitlements và định dạng thời gian cần theo DB thực. Một token có thể có nhiều audiences/scopes, nên production có thể cần bảng phụ/JSONB/indices. **Không ghi raw bearer token vào bất kỳ column nào nếu chỉ cần lookup bằng fingerprint.**

### 5.5. Tránh token collision và trạng thái phát hành nửa chừng

- Token fingerprint phải có unique constraint; nếu cực hiếm xảy ra collision, sinh lại token.
- Commit metadata/authorization grant trước hoặc nhất quán với việc công bố token tới client.
- Nếu token response thất bại giữa chừng, có quy trình cleanup/hạn định TTL.
- Không tái sử dụng cùng opaque token string cho access và refresh token; tách **purpose**.
- Khi revoke record, chỉ giữ dữ liệu phục vụ policy/audit đúng retention, tránh giữ tokens vô hạn.

## 6. Token response và cách OAuth Client sử dụng opaque token

Sau Authorization Code Grant được kiểm đầy đủ (client/code/PKCE/consent), AS có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "OPAQUE_ACCESS_TOKEN_EXAMPLE",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders:read"
}
~~~

**OAuth token response không bắt buộc access token là JWT**; chuỗi opaque hoàn toàn hợp lệ. Nếu grant/chính sách hỗ trợ, response có thể có `refresh_token`; nó phải được client lưu riêng, dùng chỉ tại token endpoint.

### 6.1. Client không decode opaque token

Một số SDK giả định mọi access token có dấu chấm và cố Base64-decode payload. Với opaque token, cách này sai. Client nên dựa trên:

- `expires_in` và metadata do AS trả để quản lý vòng đời token.
- `scope` được cấp thực tế (nếu response có), không chỉ requested scopes.
- Trusted authorized-client store gắn user/client/resource/grant.
- AS APIs (refresh/revoke) theo chuẩn và profile.

**Đừng biến token thành client-side permission database**. Resource Server vẫn là nơi quyết định request có được chấp nhận.

### 6.2. Bearer transport

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.com
Authorization: Bearer OPAQUE_ACCESS_TOKEN_EXAMPLE
Accept: application/json
~~~

Không đưa token vào query URL, browser history, logs hoặc analytics. Với browser-facing kiến trúc, cân nhắc BFF giữ token server-side, sử dụng cookie/session phòng CSRF/XSS theo thiết kế, thay vì phơi refresh token lâu dài ra JavaScript.

### 6.3. Access token hết hạn chưa chắc user session hết hạn

`expires_in=600` nói về **access token**, không phải thời hạn đăng nhập của OP hoặc BFF session. Client có thể refresh theo grant (nếu được cấp), hoặc reauthorize khi cần. User logout có thể yêu cầu đồng thời hủy BFF session, token/grant theo policy; **không đồng nhất các vòng đời**.

## 7. RFC 7662: Token Introspection là cách hỏi trạng thái

**OAuth 2.0 Token Introspection (RFC 7662)** định nghĩa endpoint để một protected resource hỏi AS về **trạng thái và metadata của token**, khi caller có quyền.

### 7.1. Request chuẩn: POST form

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Authorization: Basic <REGISTERED_RS_INTROSPECTION_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=OPAQUE_ACCESS_TOKEN_EXAMPLE&
token_type_hint=access_token
~~~

- `token` là credential cần kiểm, gửi **qua TLS**.
- `token_type_hint` là gợi ý không bắt buộc; AS không được dựa vào nó để bỏ qua việc tra loại token thật hoặc policy.
- RS/client gọi introspection phải được **xác thực và cho phép** theo AS policy. Ví dụ dùng Basic, nhưng các deployment có thể dùng mTLS, private-key JWT hoặc cơ chế hợp lệ khác.
- Tránh truy vấn introspection bằng GET với token trong URL.
- AS không được công bố thông tin nhạy cảm về token cho mọi caller chỉ vì họ biết URL introspection.

### 7.2. Response token active

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders:read",
  "client_id": "shop-bff",
  "username": "user-742",
  "token_type": "Bearer",
  "exp": 1795428600,
  "iat": 1795428000,
  "nbf": 1795428000,
  "sub": "user-742",
  "aud": "orders-api",
  "iss": "https://login.example.com",
  "jti": "internal-access-reference-9841"
}
~~~

Các timestamp trong ví dụ là **dữ liệu minh họa độc lập ngày hiện tại**; khi triển khai thật `exp` phải ở tương lai với clock thực. `active` là trường **bắt buộc** của introspection response; các trường như `scope`, `client_id`, `sub`, `aud`, `iss`, `jti`, `exp` thường là **tùy chọn theo AS/profile**, không được giả định luôn có.

### 7.3. Response revoked, expired hoặc không được phép introspect

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": false
}
~~~

Theo RFC 7662, `active=false` được dùng khi token không active, không tồn tại hoặc caller không được biết token đó; AS **không cần tiết lộ tại sao**. Mục tiêu là không biến endpoint thành công cụ enumeration token/client/user. **HTTP 200 ở đây chỉ là thành công khi xử lý introspection request**, không có nghĩa token được chấp nhận.

### 7.4. Khi RS có thể tin response?

Chỉ khi:

1. RS gọi **trusted AS/introspection endpoint**, xác minh TLS/hostname và xác thực chính RS.
2. HTTP response đúng định dạng, parse được JSON, có `active` kiểu boolean.
3. `active=true` và các claims metadata đáp ứng **hợp đồng tin cậy** của API.
4. Token đủ **audience**, scope và token purpose cho RS, không chỉ active.
5. Có subject/client principal mapping và tenant/resource policy cần thiết.
6. Nếu token có sender binding, RS kiểm proof tương ứng.
7. Áp cache/timeout/failure policy phù hợp rủi ro.

**Nếu `active` vắng mặt, không phải boolean hoặc response malformed, RS phải fail closed**; không giả định active dựa trên status 200.

### 7.5. Introspection auth khác với bearer token cần kiểm

`Authorization: Basic ...` trong request ví dụ là **credential của RS để gọi introspection endpoint**. `token=...` trong form là **bearer token của OAuth Client đang được kiểm**. Hai chuỗi có quyền và mục đích khác nhau. Không dùng credential của RS để impersonate end user; không đưa bearer token vào Basic username/password của introspection caller.

### 7.6. Introspection không phải identity search

Không hỗ trợ `?sub=user-admin` để RS tra token/user bất kỳ. RS chỉ cần biết **token được trình trên request có hợp lệ và có đủ quyền không**. AS phải hạn chế metadata mà một introspection caller được phép thấy, tránh rò claims của token dành cho client/resource khác.

## 8. Resource Server: từ `active` đến quyết định phân quyền

Giả sử Orders API nhận:

~~~text
Bearer token T1

Introspection result:
  active = true
  iss    = https://login.example.com
  sub    = user-742
  aud    = orders-api
  scope  = orders:read
  exp    = future timestamp

Request:
  GET /tenants/tenant-anpha/orders/42
~~~

**Chưa đủ để cho phép** nếu user không thuộc tenant Anpha hoặc không được đọc order 42.

### 8.1. Quy tắc kiểm nhiều lớp

1. **Token validation:** `active=true` hoặc JWT validation, đúng issuer/resource/time/profile.
2. **Principal validation:** kiểm `sub`/`client_id`/principal type theo hợp đồng AS; không nhầm service với user.
3. **Permission scope:** `orders:read` cho phép hành động loại “đọc” theo policy.
4. **Tenant boundary:** user/service được phép tenant đang truy vấn.
5. **Object-level policy:** ownership/ACL/relationship, trạng thái nghiệp vụ và data classification.
6. **Sender proof:** DPoP/mTLS certificate binding khi profile token áp dụng.
7. **Current risk/revocation state:** áp SLA yêu cầu trạng thái mới; cache không che các quyết định quan trọng.

### 8.2. Ma trận ra quyết định

| Trạng thái/metadata | Request | Kết quả nên có |
|---|---|---|
| `active=false` | Bất kỳ protected API nào | Từ chối token. |
| `active=true` nhưng sai `aud` | Orders API | Từ chối; token dành cho resource khác. |
| `active=true`, đúng `aud`, thiếu `orders:read` | GET order | Từ chối thiếu quyền. |
| `active=true`, scope đúng, sai tenant | GET order Anpha | Từ chối theo tenant policy. |
| `active=true`, scope đúng, tenant đúng, object ACL sai | GET order 42 | Từ chối BOLA/IDOR. |
| `active=true`, scope đúng, tenant/object policy đúng | GET order | Có thể cho phép. |
| Introspection không kết nối được | API bất kỳ | Không nên tự chấp nhận token chưa được xác minh; áp outage/fail-closed policy. |
| Token là refresh token | GET order | Từ chối sai token purpose ngay cả nếu chuỗi có trong DB. |
| Token của client/service dùng trên user-only endpoint | `GET /me/orders` | Từ chối khi policy yêu cầu USER principal. |

### 8.3. Không dùng `username` làm khóa identity duy nhất

`username` là metadata tùy chọn trong RFC 7662. Nó có thể thay đổi, không đảm bảo unique toàn issuer hoặc giữa tenants. Identity nên dùng **trusted issuer + verified subject/principal type**, còn username/email là thuộc tính hiển thị theo profile. Nếu AS không trả subject nhưng API bắt buộc cần subject, **không tự dựng user từ request header**.

### 8.4. Không cho quyền theo dữ liệu client tự gửi

Một request có header `X-User-Id: admin` hoặc body `tenant_id=another-tenant` không thể override subject/tenant grants từ trusted introspection. Token active không cho client quyền tự chọn identity/tenant. **Fail closed khi thiếu binding hoặc principal type đáng tin.**

## 9. Hiểu đúng `active=false` và nguy cơ token enumeration

### 9.1. Trả `false` không phải khai hết nguyên nhân

Một introspection endpoint an toàn có thể trả `{"active":false}` trong nhiều trường hợp:

- Token không tồn tại.
- Token đã hết hạn.
- Token đã bị revoke.
- Token chưa active (chưa tới `nbf`).
- Token không thuộc quyền mà caller introspection được phép biết.
- Token sai purpose/profile hoặc không thỏa policy.

RS thường không cần biết **lý do chi tiết** để đưa ra quyết định bảo vệ: **từ chối dùng token**.

### 9.2. Không echo raw token trong lỗi hoặc logs

**Không an toàn:**

~~~json
{
  "error": "revoked_token",
  "token": "OPAQUE_ACCESS_TOKEN_EXAMPLE",
  "owner": "user-742",
  "revoked_by": "admin-11"
}
~~~

AS nên trả response đúng RFC/caller policy, không tiết lộ token/PII. Audit nội bộ có thể dùng `token_record_id` hoặc fingerprint có chính sách RBAC, tránh đưa full token vào tracing, metrics hoặc error responses.

### 9.3. Caller introspection cũng phải được phân quyền

Một client access token có thể có nhiều claims, nhưng **không mọi Resource Server đều có quyền đọc tất cả**. AS nên ràng buộc introspection caller với allowed audiences/resources/metadata, chỉ trả những thông tin cần để RS đưa ra quyết định. Một caller không được phép introspect token có thể nhận `active=false` thay vì dữ liệu làm lộ user.

### 9.4. Đừng cho biết “token có thật” qua timing và error details

Nếu token không tồn tại và token bị revoke tạo thời gian phản hồi/lỗi quá khác nhau, attacker có thể dò. Hạn chế rate, dùng trả lời nhất quán theo chính sách, không công khai user/client metadata, và tránh log queries chứa raw token. **Không đánh đổi chuẩn RFC chỉ để tạo thông báo chi tiết dễ debug**.

## 10. RFC 7009: Token Revocation là hành động thay đổi trạng thái

**RFC 7009 — OAuth 2.0 Token Revocation** định nghĩa endpoint để client yêu cầu AS **vô hiệu token**. Đừng nhầm:

- **Introspection (RFC 7662):** “Token này còn active và có metadata gì đối với RS?”
- **Revocation (RFC 7009):** “Hãy thu hồi token này theo quyền của caller và chính sách AS.”

### 10.1. Request revocation

~~~http
POST /oauth2/revoke HTTP/1.1
Host: login.example.com
Authorization: Basic <CONFIDENTIAL_CLIENT_AUTH_EXAMPLE>
Content-Type: application/x-www-form-urlencoded

token=REFRESH_TOKEN_TO_REVOKE_EXAMPLE&
token_type_hint=refresh_token
~~~

Điều kiện quan trọng:

1. **TLS/HTTPS** để token không rò trên đường truyền.
2. Client authentication phù hợp với client type và AS registration/policy.
3. `token` là giá trị raw cần thu hồi, **không** gửi trong URL query.
4. `token_type_hint` chỉ là gợi ý cho tối ưu tra cứu, **không phải bằng chứng token là refresh/access token**.
5. AS xác minh quyền caller thu hồi token/grant theo giao thức và cấu hình.
6. AS cập nhật token state/associated grant theo chính sách; với distributed store phải xét consistency và concurrency.

### 10.2. HTTP 200 không tiết lộ token tồn tại hay không

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Length: 0
~~~

Theo RFC 7009, revocation request đối với **token không hợp lệ/không tồn tại** vẫn có thể — và theo chuẩn phải — trả HTTP `200` khi xử lý thành công, nhằm tránh tiết lộ tính tồn tại. Vì vậy:

> HTTP 200 từ revocation endpoint **không chứng minh** token từng tồn tại, thuộc client hoặc đã có access token liên quan.

Một client gọi revoke thành công nên **xóa local token** và ngừng dùng nó, không tiếp tục test bằng cách replay trên API công khai.

### 10.3. Revocation refresh token và access token

RFC 7009 yêu cầu AS **MUST hỗ trợ revocation refresh token** nếu có refresh token, và **SHOULD hỗ trợ access token revocation**. Khi thu hồi một token, AS có thể thu hồi các token liên quan của cùng grant theo policy; tác động cụ thể cần kiểm với provider.

| User action | Ví dụ policy | Không nên mặc định |
|---|---|---|
| Client logout khỏi một session | Revoke refresh token R1, bỏ local access token. | Mọi access token ở mọi RS lập tức inactive. |
| Người dùng rút consent cho client | Revoke grant/token family; chặn token mới. | Mọi session của tất cả clients đều logout. |
| Mất thiết bị | Revoke tokens gắn thiết bị/grant, có thể sender-binding. | Phải rotate signing key của cả AS. |
| Compromise client credential | Revoke/rotate client secret, có thể revoke grants đã cấp. | Chỉ revoke một access token là đủ. |
| User bị vô hiệu hóa | Từ chối login/token mới, áp risk-state ở RS. | Mọi cache token đang active tự biến mất. |

### 10.4. Khi revocation endpoint lỗi

Nếu endpoint không sẵn sàng, client **không được tuyên bố token đã được thu hồi trên AS** chỉ vì đã xóa nó ở local browser. Client có thể xóa credential phía mình để ngăn dùng tiếp, ghi nhận yêu cầu failed/retry theo policy và điều tra. RFC 7009 có các phản hồi lỗi/HTTP behavior cụ thể; **không gộp mọi network timeout thành success**.

### 10.5. Token đã revoke có được tái cấp cùng chuỗi không?

Không. Nếu client cần quyền trở lại, AS phát **token mới** sau authorization/grant phù hợp. Tái sử dụng bearer token đã bị lộ hoặc revoke tạo ambiguity trong cache/denylist và giảm tính chắc chắn của revocation.

## 11. Caching introspection: hiệu năng đổi lấy độ trễ thu hồi

Nếu RS gọi AS cho **mỗi** request, revocation có thể được phát hiện nhanh theo state store và network. Nhưng một hệ thống có 20.000 requests/giây có thể tạo áp lực lớn lên AS/introspection endpoint. Do đó nhiều hệ thống cache kết quả.

### 11.1. Một ví dụ timeline

~~~text
T0 = 10:00:00  RS introspects T1 -> active=true; caches 30 seconds
T1 = 10:00:05  AS revokes T1
T2 = 10:00:10  Attacker presents T1 to RS
T3 = 10:00:30  Positive cache expires
T4 = 10:00:31  RS introspects again -> active=false
~~~

Nếu RS cho phép dùng positive cache đến 10:00:30, bản sao T1 **vẫn có thể được chấp nhận** từ T1 đến T3 dù AS đã revoke. Đây là **revocation lag**, không phải trường hợp opaque token không thu hồi được.

### 11.2. Bound TTL theo thời gian còn lại của token

Một TTL có thể tính:

~~~text
cacheTTL = min(
    configuredMaxPositiveIntrospectionTtl,
    max(0, token.expiresAt - now - allowedSafetyMargin)
)
~~~

Chính sách còn phải xét clock skew và token validity. Nếu token còn hiệu lực 8 giây thì không cache `active=true` trong 60 giây. Với introspection response không có `exp`, phải có **TTL thận trọng của hệ thống**, không giả định token không bao giờ hết hạn.

### 11.3. Worst-case revocation delay

Khi cache positive TTL tối đa là `C` và không dùng stale-while-revalidate:

~~~text
Observed revocation delay can include:
  AS write/replica propagation delay
  + remaining RS cache TTL (<= C)
  + request/processing/clock margins
~~~

Nếu `C=30s`, chậm trễ do positive cache **có thể lên đến gần 30 giây**, cộng propagation/clock/race tùy hệ thống. Đây là **ước lượng ràng buộc của một cache theo TTL**, không phải SLA bảo đảm cho mọi hạ tầng.

Nếu có **stale-while-revalidate**, fallback khi AS down hoặc cache nhiều tầng, thời gian có thể **dài hơn nhiều**. Phải đo từ thời điểm revoke committed đến thời điểm **tất cả RS không còn chấp nhận token**.

### 11.4. Chiến lược cache theo mức rủi ro

| Chiến lược | Ưu điểm | Nhược điểm |
|---|---|---|
| **Không cache positive introspection** | Phát hiện revoked state sớm theo store consistency. | Tăng latency, AS QPS và phụ thuộc sẵn sàng. |
| **Cache rất ngắn, ví dụ vài giây** | Giảm QPS phần nào, hạn chế stale window. | Vẫn có khoảng thời gian chấp nhận token đã revoke. |
| **Cache 30–60 giây** | Tiết kiệm hạ tầng, latency thấp. | Thu hồi không thể hứa tức thời. |
| **Cache dài nhiều phút** | Ít introspection requests. | Revocation lag lớn; không hợp API rủi ro cao nếu thiếu cơ chế bổ sung. |
| **Event-driven invalidation + TTL fallback** | Gần real-time khi event delivery tốt. | Cần bảo vệ event authenticity, ordering, mất event và cross-region consistency. |
| **Central authorization/state lookup cho hành động nhạy cảm** | Revocation freshness cao hơn ở endpoint quan trọng. | Phức tạp và tăng latency cho từng thao tác. |

Các khoảng thời gian trong bảng là **ví dụ đánh đổi kỹ thuật**, không phải giá trị chuẩn bắt buộc. Mỗi hệ thống phải chọn theo rủi ro, lưu lượng, SLA thu hồi và mô hình tấn công.

### 11.5. Cache key không chỉ là URL `/introspect`

Sai:

~~~text
cacheKey = "/oauth2/introspect"
cacheKey = token client_id only
cacheKey = user email only
~~~

Một cache kiểm token thường cần gắn **token fingerprint**, trusted issuer, resource/audience context và introspection caller authorization, nếu metadata được AS lọc theo caller. Nếu cùng token được introspect bởi hai RS có quyền nhìn metadata khác nhau, **không được share kết quả không xét caller context**.

Không đặt **raw bearer token** vào metrics key/log/cache debug dump. Nếu dùng HMAC token fingerprint để cache, bảo vệ key và quản lý version khi rotate.

### 11.6. Negative caching có nên dùng?

Cache `active=false` trong một TTL rất ngắn có thể giảm brute-force introspection QPS nhưng cũng có rủi ro:

- Token vừa phát nhưng replica đọc chậm có thể bị ghi negative tạm.
- Kẻ tấn công gửi hàng triệu chuỗi ngẫu nhiên để làm đầy cache.
- Cache key có thể làm lộ token/correlation nếu dump.

Dùng giới hạn TTL/size, bảo vệ cache key, rate limits và quan sát false negatives. Không dựa vào `active=false` để hiện thông tin token từng tồn tại hay thuộc user nào.

### 11.7. AS introspection bị down: fail-open nguy hiểm

**Không an toàn:**

~~~text
if introspection server timeout:
    accept bearer token because it looks opaque and was seen before
~~~

Khi cần trạng thái còn hiệu lực mà không có kết quả tin cậy, RS nên **fail closed** hoặc áp một **degraded mode được duyệt trước** và chỉ trong phạm vi rõ. Một số API đọc ít nhạy cảm có thể dùng cache positive còn hạn; **không kéo dài stale cache vô hạn** khi AS down nếu SLA revocation không cho phép.

## 12. Distributed token state và consistency

Trong thực tế, AS/RS chạy nhiều replicas và availability zones. Có thể có:

~~~text
AS node A -> primary token database
AS node B -> read replica (lag 250ms)
Orders RS-1 -> local introspection cache
Orders RS-2 -> local introspection cache
Gateway -> shared cache and rate limit
Admin portal -> consent/grant revocation
~~~

### 12.1. Một revocation request thành công cần nói rõ điều gì?

Một contract vận hành nên định nghĩa:

- Khi nào revocation **đã committed** vào authoritative store.
- Có replication lag tối đa/được đo không.
- RS nào cần nhận invalidation event và cách retry nếu mất.
- Nếu event đến sai thứ tự, có version/sequence để không hồi sinh state cũ không.
- Khi cache không làm mới được, RS fail closed ở loại request nào.
- Cần mất bao lâu để ngăn token tiếp tục dùng theo **SLA thu hồi**.

**Không báo “revoked globally” ngay khi một node cập nhật memory** nếu các RS khác vẫn chấp nhận token do cache.

### 12.2. Immutable or monotonic revocation

Một mô hình record:

~~~text
token record:
  status     = ACTIVE | REVOKED
  version    = 8
  revoked_at = null

revoke request:
  atomic transition ACTIVE -> REVOKED
  version 8 -> 9
  revoked_at = server timestamp

out-of-order event:
  version 8 arrives after version 9 -> ignore stale update
~~~

`REVOKED` nên là trạng thái **terminal** cho một token. Nếu reauthorization hợp lệ, cấp **token mới**, không chỉnh record cũ trở lại active.

### 12.3. Revocation event không thay TTL fallback

Pub/sub invalidation có thể thất lạc event, partition mạng hoặc cache instance restart. Nên có **max TTL hữu hạn**, metrics event delivery và cơ chế reconciliation. Với hành động nhạy cảm, cân nhắc authoritative read hoặc policy state version thay vì phụ thuộc duy nhất vào message bus.

### 12.4. Read replicas có thể trả active sau revoke

Nếu AS ghi revoke vào primary nhưng introspection đọc một replica chưa đồng bộ, nó có thể trả `active=true` dù RS **không cache**. Vì vậy không cache **chưa đủ** để bảo đảm revocation tức thời; phải xác định consistency model và chọn read source phù hợp.

### 12.5. Atomic issuance/expiry/revocation

Một request revocation có thể cạnh tranh với token issuance, refresh rotation hoặc introspection:

~~~text
Request A: issue/refresh token
Request B: revoke grant
Request C: introspect access token
~~~

AS cần dùng transaction/CAS/locking thích hợp để không phát token mới sau khi grant đã được revoke theo thứ tự commit. Introspection request đã được kiểm và đang in-flight trước revoke có thể vẫn thành công; các request nhạy cảm có thể cần policy về **revocation race**.

## 13. Refresh tokens: trạng thái server và rotation theo token family

Refresh token thường có thời hạn dài hơn access token, nên khi bị đánh cắp hậu quả có thể **kéo dài qua nhiều access tokens**. Dạng opaque rất phù hợp để quản lý state/family, nhưng **randomness một mình không phát hiện replay**.

### 13.1. Lược đồ rotation

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    participant ST as Refresh Token Store

    C->>AS: POST /token, refresh_token=R1
    AS->>ST: Atomic check R1 ACTIVE and grant valid
    ST-->>AS: R1 valid, family F1
    AS->>ST: Mark R1 CONSUMED, create R2 ACTIVE
    AS-->>C: Access A2 + refresh R2
    C->>AS: Later refresh_token=R2
    AS->>ST: Atomic check R2 ACTIVE
    AS->>ST: Mark R2 CONSUMED, create R3 ACTIVE
    AS-->>C: Access A3 + refresh R3
~~~

Nếu hệ thống sử dụng **refresh token rotation**, **R1 không được tiếp tục sử dụng** sau khi đã được dùng thành công. Client phải lưu R2 đúng cách và xóa R1; không chia sẻ một refresh token cho nhiều concurrent workers không phối hợp.

### 13.2. Replay/reuse một refresh token cũ

~~~text
1. R1 issued to client, family F1.
2. Legitimate client exchanges R1 and receives R2.
3. Attacker attempts to exchange stolen R1 again.
4. AS detects R1 already CONSUMED.
5. AS applies policy, e.g. revoke active token family F1.
6. Client must reauthorize if family is revoked.
~~~

**Reuse detection chỉ có ý nghĩa khi trạng thái tiêu thụ được cập nhật nguyên tử**. Nếu hai requests cùng đọc R1 là active rồi đều phát R2/R3, AS đã tạo lỗ hổng race condition.

### 13.3. Pseudocode: consume once

~~~text
function rotateRefreshToken(rawR1, authenticatedClient):
    fp = fingerprint(rawR1)
    with atomic database transaction:
        record = lockRefreshRecordByFingerprint(fp)
        if record missing or expired or revoked:
            reject invalid_grant

        if record.client_id != authenticatedClient.id:
            reject invalid_grant

        if record.status == CONSUMED:
            markFamilyCompromisedAndRevokeActiveDescendants(record.family_id)
            reject invalid_grant

        if record.grant revoked or current policy denies:
            reject invalid_grant

        atomically mark R1 as CONSUMED
        R2 = issueFreshOpaqueRefreshToken(
            family_id = record.family_id,
            parent_id = record.id,
            client_id = record.client_id,
            authorized_scopes = record.scopes,
            grant = record.grant
        )
        A2 = issueAccessTokenWithinGrantAndPolicy(record.grant)

    return tokenResponse(A2, R2)
~~~

Đây là **pseudocode học tập**. Response và DB commit cần thống nhất để xử lý trường hợp client timeout sau khi server đã tiêu thụ R1 nhưng chưa nhận R2. **Không tùy tiện replay R1** để “lấy lại” R2 vì có thể kích hoạt compromise/revocation.

### 13.4. Legitimate concurrency vs attacker replay

Hai tabs hoặc hai backend workers refresh cùng lúc có thể khiến một request hợp lệ bị xem là reuse. Giảm lỗi thiết kế bằng:

- Một refresh coordinator/lock theo authorized-client/refresh family ở phía client.
- Single-flight refresh: nhiều requests cùng chờ một kết quả.
- Atomic consumption ở AS.
- Retry/backoff đúng error contract; không retry consumed refresh token.
- Policy ứng phó reuse có xét evidence/risk, không hứa mọi replay đều xác định được attacker.

**Không nới “reusable old refresh token” vô thời hạn** để chữa concurrency, vì như vậy bỏ cơ chế phát hiện replay.

### 13.5. Refresh token và consent/grant

Nếu người dùng rút quyền, AS phải kiểm grant đã revoke khi refresh; R2 còn hạn **không được tự phát token scope đã bị rút**. Refresh request `scope` khi có không được mở rộng quá grant gốc theo RFC 6749 `6. Revocation và rotation là hai khái niệm độc lập nhưng cùng phụ thuộc **server-side state**.

## 14. JWT, opaque và kiến trúc hybrid

Không có định dạng duy nhất tốt cho mọi hệ thống. Phải chọn dựa trên khả năng thu hồi, latency, complexity, trust boundaries và chính sách dữ liệu.

### 14.1. Khi opaque access token hữu ích

- Cần **trạng thái server** làm điểm kiểm trung tâm.
- Quyền/consent/subject có thể bị thu hồi trong TTL của token.
- Không muốn payload JWT tự tiết lộ claims khi token bị xem.
- RS có thể truy cập introspection với SLA, caching và policy rõ.
- Nhiều resource servers cần metadata đã được AS kiểm và phân phối đúng phạm vi.

### 14.2. Khi JWT access token hữu ích

- Nhiều RS cần kiểm token **offline** với độ trễ thấp.
- JWKS/signature validation đủ cho mô hình rủi ro và access token TTL ngắn.
- Claims nhỏ, được kiểm soát, ít thay đổi trong lifetime.
- Có chiến lược xử lý revoke/token compromise riêng nếu cần.

**JWT không đồng nghĩa “không thể thu hồi”**. AS/RS có thể dùng denylist `jti`, policy version, grant state hoặc introspection bổ sung. Khi đó JWT không còn hoàn toàn stateless đối với revocation.

### 14.3. Hybrid: JWT access token + opaque refresh token

Một cấu hình phổ biến:

~~~text
Access token:
  JWT, short TTL
  RS validates offline and may do state check for high-risk operations

Refresh token:
  Opaque, long-lived within policy
  AS tracks active/consumed/revoked family
  Rotation + reuse detection

OIDC ID token:
  JWT for OIDC Client, different audience/purpose
~~~

Một cấu hình khác:

~~~text
Access token:
  Opaque, introspected at RS

Refresh token:
  Opaque, rotated and stored at AS

BFF session:
  Separate secure cookie / server session
~~~

Cả hai đều có thể an toàn khi policy nhất quán. **Không coi JWT/opaque là cùng một trục với access/refresh purpose**.

### 14.4. Tránh biến opaque access token thành JWT trá hình

Nếu AS tạo chuỗi `base64(userId:scope:timestamp)` và đặt tên “opaque”, người khác vẫn có thể decode/đoán nội dung. Nếu token không có entropy đủ, attacker có thể dự đoán token. **Opaque reference token nên được sinh ngẫu nhiên bằng CSPRNG**, không phải chỉ che plain claims bằng Base64.

### 14.5. Token exchange và introspection phải giữ audience

Một service có user-associated access token `aud=orders-api` không được gửi nó nguyên trạng cho `payments-api` chỉ vì Payments có thể introspect token active. Nếu cần delegation, dùng token exchange/authorization flow được AS hỗ trợ và giới hạn scopes/resources. **`active=true` không vượt audience constraint**.

## 15. Sender-constrained token: khi opaque bearer chưa đủ

Opaque token thường được gửi như **Bearer**. Kẻ biết chuỗi token còn active có thể thử dùng nó, kể cả nếu không biết username/password. Revocation sẽ chặn khi AS/RS thấy trạng thái mới, nhưng vẫn có **cửa sổ lạm dụng**.

### 15.1. DPoP (RFC 9449)

DPoP có thể ràng buộc token với một public key và mỗi request có proof ký bằng private key tương ứng. RS phải kiểm:

- Access token được ràng buộc đúng key theo profile AS.
- Proof signature, HTTP method/URI, time/nonce (nếu áp dụng), unique `jti`/replay policy.
- Key thumbprint từ proof khớp binding trong token metadata.
- `ath` hoặc các thông tin proof cần thiết theo profile liên quan access token.
- Không nhận bearer token thiếu proof như một token đã được sender-bound.

Nếu introspection response chứa metadata ràng buộc sender như `cnf` theo profile, RS phải kiểm nó **đúng cách**; đây không chỉ là một chuỗi dùng để log.

### 15.2. mTLS certificate-bound access token (RFC 8705)

Với mTLS, token có thể được ràng buộc với client certificate. RS cần chứng minh client hiện tại sở hữu private key/chứng chỉ phù hợp và so khớp certificate binding. Nếu TLS termination qua gateway, chỉ tin certificate identity do **gateway đã xác thực và bảo vệ kênh tới RS** cung cấp, không từ arbitrary `X-Client-Cert` header.

### 15.3. Sender constraint không thay revocation hoặc authorization

DPoP/mTLS giảm khả năng một bản sao token được dùng bởi attacker **không có khóa**, nhưng:

- Nếu attacker kiểm soát process/khóa, vẫn có thể lạm dụng.
- Nếu credential bị lộ, phải có chiến lược revoke/grant response.
- Token active nhưng sai scope/tenant vẫn bị từ chối.
- Sender proof hợp lệ không biến **service principal** thành **user principal**.

## 16. Token status, consent và quyền trên tenant

### 16.1. Token active không đồng nghĩa user vẫn có role

Một user có `orders:read` tại tenant Beta hôm qua. Hôm nay admin xóa membership nhưng opaque token vẫn còn hạn:

~~~text
Token metadata cached:
  active=true
  sub=user-742
  scope=orders:read
  aud=orders-api

Current tenant policy:
  user-742 is no longer member of tenant-beta
~~~

Nếu API chỉ xem `active=true` và scope, nó có thể **tiếp tục cấp dữ liệu sai quyền**. RS phải kiểm tenant/current authorization theo policy. AS có thể đồng bộ state grant/user để introspection trả inactive, nhưng **không nên coi đó là bảo đảm** nếu hệ thống chưa có hợp đồng và cơ chế cập nhật tương ứng.

### 16.2. Không dùng token của tenant này cho tenant khác

~~~text
Service token:
  client_id=reporting-worker
  scope=reports:read
  aud=reports-api
  tenant grant=tenant-beta

Request:
  GET /tenants/tenant-anpha/reports
~~~

RS phải từ chối nếu service không được quyền Anpha. `aud=reports-api` chỉ xác định resource API, không tự chứng minh được quyền trên mọi tenant mà API lưu.

### 16.3. Phân biệt subject và client

Theo grant/token profile, token có thể đại diện:

- **End-user `sub=user-742`** được cấp qua Authorization Code/OIDC grant.
- **Service principal `client_id=reporting-worker`** qua Client Credentials Grant.
- **Delegated subject/actor** qua token exchange profile phù hợp.

Opaque introspection metadata phải được RS diễn giải theo **issuer và principal type/grant contract**. Không đoán `sub=user-admin` từ header/body hoặc email; không dùng service token để giả user. Nếu thiếu trusted principal type ở endpoint user-only, **fail closed**.

### 16.4. Object-level authorization độc lập với introspection

Một record `order_id=42` có tenant và ownership riêng. Scope `orders:read` **không thay** việc kiểm object ACL. Dùng truy vấn có tenant/ownership policy hoặc authorization service đáng tin, tránh BOLA/IDOR dù token vẫn active.

### 16.5. Revoke consent: không chỉ đổi flag UI

Khi user rút `orders:read`, hệ thống cần:

1. AS dừng cấp token mới với scope đã rút.
2. Revoke grant/refresh family/access tokens theo policy.
3. Update introspection state/token store.
4. Invalidate các cache có khả năng trả positive stale.
5. RS áp object/tenant policy hiện hành.
6. Audit decision không log bearer token.

**Không tuyên bố “thu hồi thành công cho mọi API”** nếu chưa đo được trạng thái cuối trên các RS liên quan.

## 17. Spring Security Resource Server: cấu hình opaque token introspection

Trong hệ sinh thái Java, **Spring Security OAuth2 Resource Server** hỗ trợ xác minh opaque access token qua introspection. Framework xử lý gọi endpoint, xác thực RS và chuyển scope thành authorities theo cơ chế chuẩn. Tuy nhiên, **kiểm audience, principal type, tenant và object-level policy** vẫn cần cấu hình/triển khai phù hợp, không chỉ thêm một dependency.

### 17.1. Cấu hình Spring Boot minh họa

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ${ORDERS_RS_INTROSPECTION_SECRET}
~~~

`ORDERS_RS_INTROSPECTION_SECRET` là **biến môi trường được inject từ Secret Manager ở runtime** (chuỗi dạng `${...}` trong YAML sử dụng cú pháp placeholder của Spring sau khi chuẩn hóa). Không hardcode credential hoặc commit secret vào repository. Client ID/secret của **RS introspection client** là một bộ credential riêng, không phải access token của user.

**Đoạn cấu hình giả định Spring Boot/Spring Security phiên bản hỗ trợ properties này**, issuer/AS đã có introspection endpoint và RS được quyền gọi. Kiểm khả năng hỗ trợ mTLS/private-key JWT và response contract với provider thực tế.

### 17.2. SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain ordersApiChain(HttpSecurity http)
            throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth -> oauth
                .opaqueToken(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Framework có thể map introspection `scope` thành authorities dạng `SCOPE_orders:read`, nhưng **không mặc định** xử lý các điều kiện:

- `aud=orders-api` và `iss=https://login.example.com` theo contract.
- `principal_type=USER` ở endpoint `/me`.
- Tenant, owner/ACL và status trên từng order.
- Sender-bound proof nếu có token DPoP/mTLS theo profile.
- Revocation state freshness khi có cache tùy chỉnh.
- CSRF/session policy khi một ứng dụng đồng thời nhận cookie browser; đừng tắt CSRF vô điều kiện cho mọi chain.

### 17.3. Custom OpaqueTokenIntrospector kiểm issuer và audience

Với **Spring Security 6.x**, ví dụ sau minh họa một wrapper quanh introspector. **Đây là ví dụ giáo dục**, phải đối chiếu API/deprecations với version dùng thực tế.

~~~java
import java.util.Collection;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
public class OpaqueTokenValidation {

    @Bean
    OpaqueTokenIntrospector audienceAwareIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
                String uri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
                String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
                String clientSecret) {

        OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(uri, clientId, clientSecret);

        return rawToken -> {
            OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(rawToken);

            Object aud = principal.getAttribute("aud");
            boolean intendedForOrders =
                ("orders-api".equals(aud))
                || (aud instanceof Collection<?> audiences
                    && audiences.contains("orders-api"));

            if (!intendedForOrders) {
                throw new BadOpaqueTokenException("invalid_audience");
            }

            String issuer = principal.getAttribute("iss");
            if (!"https://login.example.com".equals(issuer)) {
                throw new BadOpaqueTokenException("invalid_issuer");
            }

            return principal;
        };
    }
}
~~~

**Cảnh báo kỹ thuật và bảo mật:**

1. Constructor/API `NimbusOpaqueTokenIntrospector` có thể thay đổi hoặc được thay bằng implementation khác theo version Spring Security; ví dụ phản ánh **một cấu hình 6.x điển hình**.
2. `aud` có thể là string hoặc danh sách theo provider. Nếu provider **không trả `aud` hoặc `iss`**, mã **fail closed**. Khi triển khai, phải thống nhất metadata bắt buộc với AS; không bỏ kiểm audience chỉ để “làm cho chạy”.
3. Delegate xử lý trạng thái token/introspection, wrapper chỉ minh họa **hợp đồng issuer/audience**. Cần thêm token type, principal/grant mapping, tenant và sender proof khi profile yêu cầu.
4. Không tự log `rawToken` trong lambda, exception hoặc MDC; `BadOpaqueTokenException` chỉ nên có mã lỗi không chứa credential.
5. Nếu dùng introspection cache/custom HTTP client, thiết kế **positive TTL, failure behavior, revocation SLA, timeout và authentication**; đừng cache forever.
6. Không tự định nghĩa authorization bằng `getName()` nếu subject/client semantics chưa rõ. Service principal có thể khác user principal.
7. RS phải được bảo vệ bằng transport TLS, mTLS/client authentication của introspection caller khi AS yêu cầu. Không gửi introspection client secret tới browser.

### 17.4. Dùng principal metadata đúng phạm vi

Sau khi introspection được xác minh, một principal có thể có:

~~~text
active: true
sub: user-742
client_id: shop-bff
scope: orders:read
aud: orders-api
tenant: tenant-beta  (custom contract)
~~~

`tenant` trong ví dụ là claim tùy biến, **không phải RFC 7662 field luôn có**. Nếu API xử lý `GET /api/tenants/tenant-anpha/orders/42`, việc token có `tenant-beta` phải dẫn đến từ chối nếu không có quyền Anpha.

### 17.5. Không cấu hình JWT Resource Server khi token thực là opaque

Nếu AS phát opaque access tokens, cấu hình chỉ có `spring.security.oauth2.resourceserver.jwt.issuer-uri` sẽ không tự tra opaque token trong DB. Phải chọn **opaquetoken/introspection** hoặc một authentication manager có chủ đích. Trong hệ thống hỗ trợ cả JWT và opaque, phải có **routing/verification rõ theo issuer, audience và token format**, không dùng Base64 decode tùy tiện để “đoán là JWT”.

## 18. Server-side token store: atomically revoke và tra trạng thái

### 18.1. Lệnh SQL minh họa

~~~sql
-- Atomic status transition for one token fingerprint.
UPDATE oauth_access_tokens
SET revoked_at = CURRENT_TIMESTAMP,
    revoke_reason = 'USER_REQUEST',
    version = version + 1
WHERE token_fingerprint = :trustedFingerprint
  AND revoked_at IS NULL;
~~~

Khi thực thi:

- `trustedFingerprint` đến từ việc hash/HMAC **token hợp lệ được client gửi qua kênh TLS** trong service backend có quyền, không phải từ user-supplied “record ID” chưa xác thực.
- Nếu không có row được update, token có thể không tồn tại, đã revoke hoặc expired; **không tiết lộ thông tin nội bộ** cho caller trái quyền.
- Nếu cần revoke toàn grant, update những token/family liên quan bằng **grant ID và policy đã xác minh**, không dựa vào random user ID từ request.
- Trạng thái version có thể giúp invalidate distributed cache và tránh event out-of-order.

### 18.2. Pseudocode của AS introspection

~~~text
function introspect(rawToken, introspectionCaller, now):
    require TLS and authenticated introspection caller
    if !callerAllowedToIntrospect(introspectionCaller):
        reject caller with appropriate authorization error

    record = tokenStore.lookupByFingerprint(fingerprint(rawToken))

    if record missing:
        return {active:false}

    if !callerMaySeeToken(introspectionCaller, record):
        return {active:false}

    if record.tokenType != ACCESS_TOKEN:
        return {active:false}   // for a resource-only endpoint contract

    if record.revokedAt != null or now >= record.expiresAt:
        return {active:false}

    if now < record.notBefore or grantRevoked(record.grantId):
        return {active:false}

    if currentSecurityPolicyDenies(record):
        return {active:false}

    return {
        active:true,
        iss:record.issuer,
        sub:record.subject,
        aud:record.audience,
        scope:record.scopes,
        client_id:record.clientId,
        exp:record.expiresAtEpochSeconds
    }
~~~

**Không phải mọi RFC 7662 endpoint chỉ introspect access token**; một AS có thể introspect refresh token nếu caller/profile cho phép. Pseudocode **cố ý** biểu diễn endpoint phục vụ Resource Server, chỉ trả `active=true` cho access token có mục đích đúng, để tránh refresh-token substitution.

### 18.3. Pseudocode của revocation handler

~~~text
function revokeToken(rawToken, authenticatedOAuthClient):
    require TLS POST and client authentication as applicable
    if !authorizedRevocationCaller(authenticatedOAuthClient):
        reject according to RFC7009 client rules

    record = lookupByFingerprint(fingerprint(rawToken))

    if record absent:
        return HTTP 200 (do not disclose existence)

    if !clientPermittedToRevoke(authenticatedOAuthClient, record):
        apply RFC7009 semantics without leaking protected metadata
        return appropriate response

    atomic:
        set record.revokedAt if not already revoked
        if policy revokes associated grant:
            revoke selected refresh/access token families
        bump state version

    asynchronously publish signed/authenticated cache invalidation event
    return HTTP 200
~~~

Ranh giới atomic cập nhật **authoritative store** không tự bảo đảm mọi remote caches đã bị xóa. Nếu publish event sau DB commit thất bại, cần retry/outbox/reconciliation và TTL fallback. **Không đặt rawToken vào message queue event**; dùng opaque internal record reference/fingerprint được bảo vệ.

### 18.4. Java in-memory ví dụ về trạng thái monotonic

Mẫu nhỏ sau **không phải production token store**, chỉ minh họa `REVOKED` là terminal state và việc chuyển trạng thái trong một process có thể dùng atomic map update:

~~~java
import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;

public final class InMemoryRevocationDemo {
    public record Record(Instant expiresAt, boolean revoked, long version) {}

    private final ConcurrentHashMap<String, Record> byFingerprint =
        new ConcurrentHashMap<>();

    public void register(String fingerprint, Instant expiresAt) {
        // A real implementation must reject duplicate fingerprints.
        if (byFingerprint.putIfAbsent(fingerprint,
                new Record(expiresAt, false, 0)) != null) {
            throw new IllegalStateException("duplicate_token_fingerprint");
        }
    }

    public void revoke(String fingerprint) {
        byFingerprint.computeIfPresent(fingerprint, (key, old) ->
            old.revoked()
                ? old
                : new Record(old.expiresAt(), true, old.version() + 1)
        );
    }

    public boolean isActive(String fingerprint, Instant now) {
        Record value = byFingerprint.get(fingerprint);
        return value != null
            && !value.revoked()
            && now.isBefore(value.expiresAt());
    }
}
~~~

**Giới hạn:** `ConcurrentHashMap` chỉ đảm bảo thao tác trong **một JVM**, không thay database transaction, multi-instance consistency, ACL/grant checks hoặc revocation propagation. Trạng thái có thể thay đổi **ngay sau khi `isActive` trả true**; RS phải có policy về request in-flight. Fingerprint cũng cần được tính ở tầng an toàn, không truyền raw token qua logs.

## 19. HTTP error semantics: `401` khác `403` và AS outage

### 19.1. Token không active: Bearer `invalid_token`

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Cache-Control: no-store
~~~

Điều này phù hợp khi token hết hạn, revoked, malformed hoặc không hợp lệ cho resource. Không trả “T1 revoked lúc 10:00 bởi admin-12” cho caller chưa tin cậy.

### 19.2. Token active nhưng không đủ scope

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope",
  scope="orders:read"
Cache-Control: no-store
~~~

`scope` trong challenge là mô tả scope được yêu cầu và phải được kiểm với policy; tránh rò thông tin quyền nhạy cảm nếu không cần. Một token có `scope=orders:read` vẫn có thể bị từ chối ở object ACL; không mặc định mọi authorization denial đều là `insufficient_scope`.

### 19.3. Introspection endpoint bị lỗi hoặc timeout

Nếu RS **không biết token active hay không** vì AS không sẵn sàng, về mặt authorization nên **từ chối request** theo policy an toàn. Tùy kiến trúc, RS có thể phản hồi `503 Service Unavailable` để phân biệt dependency outage với credential sai; không tự coi mọi timeout là `invalid_token` và buộc user login lại hàng loạt.

~~~text
if introspection says active=false:
    reject as invalid token

if introspection times out:
    do not assume active=true
    respond according to fail-closed outage policy (e.g. 503)

if local positive cache exists and is still valid:
    policy may permit its use until strict bounded TTL
    never extend it indefinitely solely because AS is down
~~~

### 19.4. Không tạo oracle lộ trạng thái token

API không nên cho unauthenticated caller biết phân biệt “token này từng tồn tại”, “user cụ thể đã revoked” và “token chưa được cấp” nếu điều đó vi phạm privacy/abuse policy. Trả lỗi phù hợp chuẩn Bearer, nội bộ audit dùng mã lỗi/tracing, không echo token hoặc PII.

### 19.5. Rate limits và circuit breaker phải không mở lỗ hổng

Nếu introspection endpoint bị tấn công DoS, RS có thể dùng connection pools, timeout, circuit breaker, bounded cache và rate limits. Nhưng **circuit breaker fallback = accept any token** là fail-open nguy hiểm. Với high-risk API, khi không chứng minh được active state trong SLA, nên từ chối/503 hơn là cho phép giao dịch không xác thực.

## 20. Quan sát hệ thống: không rò token qua logs/traces

### 20.1. Audit event minh họa

~~~json
{
  "event": "oauth_access_token_revoked",
  "issuer": "https://login.example.com",
  "token_record_ref": "internal-access-9841",
  "client_ref": "shop-bff",
  "grant_ref": "grant-218",
  "reason_code": "USER_REQUEST",
  "effective_at": "2026-11-23T10:00:00Z",
  "state_version": 9,
  "result": "COMMITTED",
  "trace_id": "a312ef8b4a7a4c36a5d5884c7c92bf06"
}
~~~

Đây là **minh họa event nội bộ**. Không dùng raw access/refresh token làm `token_record_ref`. Khi event chứa user/grant references, cần giới hạn RBAC, retention, bảo vệ tracing và data minimization.

### 20.2. Những thứ không được log

~~~text
Authorization: Bearer <raw token>
Authorization: Basic <introspection client credentials>
token=<raw token> in introspection request body
token=<raw token> in revocation request body
refresh_token=<raw token> in token request body
client_secret / client_assertion / DPoP proof
Cookie / Set-Cookie / session credentials
full JWT/opaque token in span attributes
full URL query when it contains credentials
~~~

Không chỉ dùng regex tìm JWT ba đoạn vì **opaque token có thể là chuỗi đơn**. Tốt hơn là **không thu thập request bodies/headers nhạy cảm tại nguồn**, dùng allowlist metadata cho route template, HTTP status, token type, error code, client reference, trace ID và timing.

### 20.3. Metrics quan trọng

~~~text
oauth_introspection_total{result=active|inactive|error}
oauth_introspection_latency_seconds
oauth_introspection_cache_hit_total
oauth_introspection_cache_stale_positive_total
oauth_revocation_total{result=committed|already_inactive|error}
oauth_revocation_propagation_latency_seconds
oauth_refresh_reuse_detected_total
oauth_grant_family_revoked_total
oauth_resource_invalid_token_total
oauth_token_state_replica_lag_seconds
~~~

Tên metrics mang tính minh họa. **Không đặt token, user ID, email, subject, `jti` hoặc refresh family ID vào labels** gây high cardinality và dữ liệu nhạy cảm. Đo revocation delay end-to-end thực tế ở nhiều RS, không chỉ response time của revocation endpoint.

### 20.4. Alarm và SLO

Các tín hiệu vận hành đáng chú ý:

- Tăng bất thường `active=false` sau deployment.
- Introspection latency hoặc error rate tăng.
- Cache hit rate thay đổi đột ngột.
- JWT/opaque token vẫn được chấp nhận **sau thời hạn thu hồi cam kết**.
- Refresh-token reuse từ nhiều IP/device/client contexts.
- Grant được revoke nhưng token family vẫn phát access tokens mới.
- Access token sai audience/tenant xuất hiện ở RS.
- Số lượng failed invalid_token/insufficient_scope tăng bất thường.

**Không suy luận token bị tấn công chỉ vì một lỗi riêng lẻ**; xem traffic patterns, account/device context và source data đáng tin. Nhưng audit phải đủ để điều tra credential compromise mà không lưu raw tokens.

## 21. Threat model: các lỗi thu hồi thường gặp

| Lỗi hoặc tình huống tấn công | Tại sao nguy hiểm | Biện pháp |
|---|---|---|
| **Opaque token sinh từ timestamp/counter** | Attacker có thể đoán credential. | CSPRNG với entropy đủ mạnh, unique constraint. |
| **Lưu raw token trong database/log** | DB dump/APM log biến thành kho bearer credentials. | Lưu fingerprint/HMAC khi phù hợp, loại secrets khỏi telemetry. |
| **`active=true` được coi là quyền mọi API** | Token Orders dùng tại Payments hoặc vượt scope. | RS bắt buộc kiểm issuer, audience, scope và object policy. |
| **Không phân biệt access/refresh token** | Refresh token bị dùng làm Bearer tại RS. | Token-purpose binding, RS chỉ nhận access token. |
| **Introspection endpoint không có caller auth** | Attacker dùng nó để dò token/user. | Caller authentication/authorization, TLS, metadata filtering. |
| **Introspection `active=false` vẫn có metadata PII** | Lộ token existence và user. | Với inactive/unknown, trả `{"active":false}` theo contract. |
| **Cache positive không có TTL** | Revoke không có hiệu lực ở RS. | TTL hữu hạn, expiry cap và active invalidation khi phù hợp. |
| **Cache raw token dùng chung giữa RS** | Token leakage và permission cross-resource. | Fingerprint-based key + issuer/resource/caller context. |
| **AS replica stale sau revocation** | `active=true` dù đã commit revoke. | Consistency guarantees, authoritative read/monitor replica lag. |
| **RS fail-open khi AS timeout** | Attacker gửi token bất kỳ lúc outage. | Fail closed, bounded cache và degradation policy. |
| **Revocation response HTTP 200 được coi là proof token tồn tại** | Sai semantics, nguy cơ oracle. | RFC 7009 success xử lý cả token không hợp lệ. |
| **Không kiểm quyền caller khi revoke** | Một client có thể hủy trái phép token người khác. | Client binding, authorization policy, privacy response. |
| **Refresh token rotation không atomic** | R1 bị đổi hai lần thành R2/R3. | CAS/transaction, family state/replay detection. |
| **R1 đã consumed vẫn được thử lại** | Có thể kích hoạt family revoke hoặc lạm dụng. | Client single-flight, persist R2, retry policy rõ. |
| **Chỉ revoke access, refresh còn active** | Client/attacker xin token mới. | Revoke grant/family khi yêu cầu; kiểm lifecycle liên quan. |
| **Chỉ disable client, không xử lý token cũ** | Access tokens còn hạn có thể dùng tiếp. | State/denylist/TTL/permission policy cho existing tokens. |
| **Mất invalidation event** | Một RS vẫn dùng cached `active=true`. | Event retry/outbox, version, reconciliation, TTL fallback. |
| **Event cũ ghi đè revoked state** | Token bị hồi sinh. | Monotonic version và terminal revoked state. |
| **Bearer bị lộ qua query string** | Proxy/history/referrer lưu credential. | `Authorization: Bearer` qua HTTPS, URL sanitization. |
| **DPoP-bound token bị dùng như Bearer thường** | Sender-binding bị vô hiệu. | RS kiểm proof/binding, reject missing proof. |
| **mTLS cert lấy từ header attacker gửi** | Giả mạo client bound token. | Trusted TLS termination và authenticated proxy identity. |
| **Token active nhưng tenant membership đã mất** | Cross-tenant BOLA/IDOR. | RS kiểm authorization state của tenant/resource. |
| **OIDC ID token nhận như access token** | Token substitution và sai audience. | Token type/profile/aud validation. |
| **Thu hồi consent nhưng RS chỉ tin JWT offline** | Token có thể tồn tại đến exp. | Revocation SLA, state check/short TTL/denylist. |
| **A/B logout chỉ hủy session cookie** | Access/refresh tokens còn tồn tại trong store. | Logout và grant/token revocation contract riêng. |
| **Token fingerprint bị dùng làm public tracking ID** | Correlation/metadata leakage. | Restrict fingerprint access, use opaque internal references in audit. |
| **Trả lý do revoke chi tiết cho client chưa tin** | Lộ user/client/incident context. | Sanitized errors, nội bộ audit có RBAC. |

### 21.1. Tấn công đánh cắp opaque token

Một attacker không cần “giải mã” T1. Nếu T1 là bearer token còn active, biết nguyên chuỗi đã đủ để thử replay, trong phạm vi audience/scope/tenant token được phép. Do đó giải pháp cần **ngăn rò, phát hiện lạm dụng, thu hồi nhanh và giới hạn blast radius** chứ không chỉ nói opaque token “không đọc được payload”.

### 21.2. Client Credentials và không được giả danh user

Một service token introspection có thể `active=true`, `client_id=reporting-worker` và `scope=reports:read`. Điều đó không chứng minh end user đã đăng nhập. RS không được nhận `X-User-Id: admin` rồi đổi principal thành USER. Với machine-to-machine flow, kiểm **service grants** riêng; nếu cần hoạt động thay user, sử dụng delegation/token exchange có AS authorization rõ.

### 21.3. Token state không phải quyền đồng ý vô thời hạn

Consent bị rút, user bị khóa hoặc tenant role đổi là tín hiệu AS/RS cần cập nhật. Nếu token store vẫn trả `active=true` vì chưa đồng bộ policy, Resource Server phải có **current authorization checks** phù hợp. Một token store chỉ biết TTL/revoked flag không tự là **authorization engine** cho mọi dữ liệu nghiệp vụ.

## 22. Playbook ứng cứu khi token bị lộ hoặc cần thu hồi gấp

### 22.1. Tình huống

Lúc 14:00 đội vận hành phát hiện HTTP debug logs ở gateway có ghi:

~~~text
Authorization: Bearer <OPAQUE_ACCESS_TOKEN_REDACTED>
~~~

Token thuộc `shop-bff`, có thể đọc Orders API ở tenant Beta và còn 8 phút TTL. Không sử dụng bản token thật để debug trong môi trường thiếu kiểm soát.

### 22.2. Thứ tự xử lý

1. **Ngăn lộ tiếp:** tắt logging/capture raw `Authorization` ở gateway, proxy, HTTP client, APM và tracing; không đơn thuần ẩn trên dashboard.
2. **Bảo vệ chứng cứ:** xác định thời gian, phạm vi log/backup/export và ai truy cập, không phát tán token trong ticket/slack/email.
3. **Xác định blast radius:** issuer, client, audience, scope, tenant, loại token, TTL, liệu refresh token/secret cũng lộ hay không.
4. **Thu hồi đúng phạm vi:** revoke T1 hoặc grant/refresh token family theo risk policy; với client credential compromise, rotate/revoke secret/key/cert.
5. **Xử lý RS:** invalidate cache introspection, kích hoạt state/denylist hoặc giảm TTL theo playbook; chú ý các replicas/vùng địa lý.
6. **Xác minh hiệu lực:** test bằng **test token hoặc internal token reference qua kênh kiểm soát**; không tiếp tục phát lại raw compromised token như thao tác giám sát thông thường.
7. **Điều tra hành vi:** audit API access trước/sau lộ, resource IDs, tenant, anomaly signals, rate và sender-binding context.
8. **Khắc phục gốc:** chuẩn hóa log allowlist, secret manager, auth filters, TLS, service least privilege và negative tests.
9. **Rà soát SLA:** đo từ revoke committed tới khi mọi RS liên quan từ chối token trong thử nghiệm kiểm soát.
10. **Truyền thông/sửa quy trình:** tùy mức độ ảnh hưởng và yêu cầu nội bộ/pháp luật; lưu outcome và quyết định trong incident record bảo mật.

### 22.3. Phân biệt sự cố access token với refresh token

| Đã lộ | Nguy cơ | Hướng xử lý thêm |
|---|---|---|
| **Một opaque access token** | Có thể replay đến khi expired/revoked/RS cập nhật. | Revoke T1, xử lý cache và resource scope. |
| **Một refresh token R1** | Có thể phát access tokens mới, replay/rotation abuse. | Revoke family/grant, kiểm reuse, reauthorization. |
| **Client secret** | Attacker có thể xin tokens mới dưới client identity. | Rotate/revoke secret và xem xét tokens/grants đã cấp. |
| **Client private key (private_key_jwt)** | Mạo danh confidential client. | Rotate key/JWK registration, revoke liên quan. |
| **AS JWT signing key** | Rủi ro giả mạo token do AS ký. | Playbook signing key compromise riêng, không nhầm với lộ một bearer token. |
| **OIDC ID token** | Lộ identity claims, có thể bị nhầm mục đích trong hệ thống sai. | Kiểm token substitution, session/security policy; không coi là access token. |

### 22.4. Thu hồi có đồng nghĩa dữ liệu đã lấy sẽ biến mất?

Không. Revocation ngăn **việc sử dụng token tiếp theo** trong ranh giới thực thi; nó **không xóa dữ liệu** mà một client hoặc attacker đã tải xuống trước thời điểm revoke. Data privacy/retention, download audit, incident containment và contractual deletion là các công việc khác.

### 22.5. Thiết kế “emergency revoke”

Với API rủi ro cao (hoàn tiền, quản trị user, xuất dữ liệu nhạy cảm), cân nhắc một **emergency denylist/state check** có freshness cao, short-lived tokens và cơ chế cô lập client/grant. Mô hình này phải có:

- Quy trình xác thực người yêu cầu revoke.
- Tránh một người dùng thường tự thu hồi mọi token hệ thống.
- Cập nhật atomic state và theo dõi replication.
- RS fail-closed policy.
- Kiểm thử thường xuyên thời gian propagation thực tế.

## 23. Ma trận kiểm thử từ phát hành đến revocation

Mỗi test phải tạo **token test riêng** trong môi trường cô lập; không dùng credentials production, không dựa vào một giá trị hardcoded từ tài liệu và không dùng cùng token đã bị test khác revoke.

### 23.1. Fixtures

~~~text
Authorization Server:
  issuer = https://login.example.com
  introspection = https://login.example.com/oauth2/introspect
  revocation = https://login.example.com/oauth2/revoke

OAuth Client:
  id = shop-bff
  grant = authorization_code
  scopes = orders:read
  user = user-742
  tenant = tenant-beta

Resource Server:
  audience = orders-api
  scope required = orders:read

Opaque access token T1:
  type = access_token
  status = ACTIVE
  expiresAt = testClock + 10 min
  audience = orders-api
  grant = G1

Refresh token R1:
  type = refresh_token
  status = ACTIVE
  family = F1

RS introspection cache:
  positive TTL = 30 s (test policy)
  negative TTL = short and bounded
~~~

### 23.2. Token generation, storage, state tests

| Test | Điều thay đổi | Kỳ vọng |
|---|---|---|
| CSPRNG token uniqueness | Sinh nhiều tokens test. | Không duplicate, entropy đủ theo thiết kế. |
| Guessable token negative case | Thử chuỗi timestamp/ID giả. | Không lookup thành một token hợp lệ. |
| Raw token absent from store | Kiểm schema/log/test vault. | Chỉ fingerprint/metadata khi thiết kế chỉ cần lookup. |
| Hash lookup | Tạo token, tính fingerprint, lookup. | Trả đúng record; không log raw token. |
| Token malformed | Gửi chuỗi bất thường/dài quá hạn. | Từ chối an toàn, có size cap, không crash. |
| Token expired | Fake clock sau `expiresAt`. | Introspection `active=false`. |
| Token before `nbf` | Fake clock trước `notBefore`. | Introspection không active. |
| Token revoked | Đánh dấu `revokedAt`. | Introspection trả `active=false` sau state propagation. |
| Unknown token | Chuỗi random không phát hành. | `active=false`, không tiết lộ token owner. |
| Token already revoked | Revoke thêm lần nữa. | Idempotent handling, không hồi sinh token. |
| Double issuance collision | Trùng fingerprint do fixture giả. | Unique index reject/sinh lại. |
| Terminal state | Nhận stale ACTIVE event sau REVOKED. | Không hồi sinh token. |
| Grant revoked | Token record active nhưng grant bị revoke. | AS/RS theo policy không tiếp tục chấp nhận/cấp token trái quyền. |

### 23.3. RFC 7662 introspection tests

| Test | Điều thay đổi | Kỳ vọng |
|---|---|---|
| Token ACTIVE | RS auth hợp lệ, token đúng. | HTTP 200 và `active=true`, metadata theo contract. |
| Token REVOKED | RS auth hợp lệ, token bị revoke. | HTTP 200 `{"active":false}`. |
| Token không tồn tại | Gửi random token. | HTTP 200 `active=false` khi request introspection được ủy quyền. |
| Sai `token_type_hint` | Gợi ý refresh nhưng gửi access token. | AS không bỏ xác minh loại token thật. |
| RS introspection credential sai | Caller auth sai. | Từ chối caller theo OAuth/auth policy. |
| RS không được quyền biết token | Token thuộc resource/client khác. | Không lộ metadata, thường `active=false` theo policy. |
| Token thiếu `aud` mà RS bắt buộc cần | Introspection active nhưng metadata không đủ. | RS fail closed. |
| `active` là string `"true"` | Response sai schema. | RS reject, không parse truthy tùy tiện. |
| JSON có `active` thiếu | Malformed introspection response. | RS reject. |
| Token active nhưng scope thiếu | `scope=orders:write`, GET orders. | RS từ chối thiếu `orders:read`. |
| Token active nhưng sai issuer | `iss` không khớp trusted AS. | RS reject. |
| Token active nhưng sai audience | `aud=payments-api` tại Orders. | RS reject. |
| Token active nhưng khác tenant | Beta token gọi Anpha. | RS reject tenant policy. |
| Token active nhưng sai object ACL | User đọc order người khác. | RS reject BOLA/IDOR. |
| Refresh token gửi tới RS | Raw R1 trong `Authorization: Bearer`. | RS reject sai purpose. |
| ID token gửi tới RS | OIDC ID token thay access token. | RS reject purpose/audience. |
| Token bị leak vào trace | Bật HTTP wire logging với canary. | Canary token không xuất hiện trong sinks. |

### 23.4. RFC 7009 revocation tests

| Test | Điều thay đổi | Kỳ vọng |
|---|---|---|
| Revoke T1 hợp lệ | Đúng client/token. | AS commit revoke, introspection chuyển inactive theo policy. |
| Revoke unknown token | Không có record. | HTTP 200 success response theo RFC 7009 semantics; không tiết lộ tồn tại. |
| Revoke token đã revoked | Gửi lại đúng request. | Idempotent behavior, không bật lại token. |
| Revocation client authentication sai | Basic/credential không hợp lệ. | AS từ chối theo policy, không thu hồi trái phép. |
| Client khác cố revoke token | Caller không được phép. | Không lộ token metadata hoặc thu hồi trái authority. |
| Revoke refresh R1 | R1 ACTIVE. | Không refresh R1 nữa, grant/family effects đúng policy. |
| Revoke access T1 nhưng refresh R1 còn | Test policy configured. | Không giả định family bị revoke nếu policy không nói vậy. |
| Revoke grant G1 | Nhiều tokens thuộc grant. | Token/family effects khớp policy và RS freshness. |
| Disable client | Client inactive sau issuance. | Không cấp token mới; token cũ theo revocation contract. |
| Revocation endpoint timeout | Network lỗi trước confirmation. | Client không tuyên bố đã globally revoked. |
| Concurrency revoke vs introspect | Request đồng thời. | State transition atomic, behavior phù hợp thứ tự/consistency contract. |

### 23.5. Cache và distributed-state tests

| Test | Điều kiện | Kỳ vọng |
|---|---|---|
| Cache active 30s | Revoke 5s sau khi cache. | RS hành xử đúng SLA; không hứa instant revoke nếu cache còn. |
| Cache TTL > token remaining life | Token còn 8s, configured max 30s. | Positive cache không vượt token expiry. |
| Cache key thiếu resource context | Hai RS dùng cùng token. | Kiểm test phát hiện data cross-resource; sửa key/policy. |
| Introspection AS down, cache absent | Không xác minh được token. | Fail closed/503 theo policy, không accept. |
| AS down, cache positive còn hạn | Có cache bounded. | Chỉ được sử dụng trong strict policy TTL nếu cho phép. |
| AS down, cache expired | Không có trạng thái mới. | Không stale-accept vô hạn. |
| Replica lag | Primary revoke, replica chưa nhận. | Đo delay, đọc authoritative source theo SLA. |
| Invalidation event lost | Bus drop một event. | TTL fallback eventually rejects, alert lag. |
| Event out-of-order | ACTIVE v8 sau REVOKED v9. | Không phục hồi ACTIVE. |
| RS-1 và RS-2 khác cache | Revoke T1 rồi truy cả hai. | Mỗi RS đạt SLA, test toàn cụm. |
| Introspection caller credential rotated | RS còn secret cũ. | AS reject caller, RS fail closed; rollout có kế hoạch. |
| Multi-region partition | AS/RS mất kết nối. | Theo outage policy, không fail-open. |

### 23.6. Refresh token family/replay tests

| Test | Thao tác | Kỳ vọng |
|---|---|---|
| Rotation bình thường | R1 → R2 → R3. | R1/R2 consumed, chỉ refresh token hiện hành active. |
| R1 reuse sau rotate | Attacker gửi R1 cũ. | Detect replay, áp policy khóa family/reauthorize. |
| Two concurrent R1 refreshes | Hai token requests đồng thời. | Chỉ một atomic consumption/rotation thành công. |
| Client mất response R2 | Timeout sau server commit. | Client retry không vô tình sinh thêm R3; xử lý theo provider contract. |
| R2 thuộc client khác | Client B gửi R2 của A. | Reject client binding. |
| R2 hết hạn | Fake clock vượt expiry. | Reject `invalid_grant`/error phù hợp. |
| Family revoked | R3 còn hạn nhưng F1 revoke. | Không phát access token mới từ R3. |
| Refresh request mở scope | R1 chỉ có read, yêu cầu refund. | Không cấp scope ngoài grant. |
| Revoke consent khi R2 active | User rút grant, R2 còn hạn. | Không tiếp tục phát quyền bị thu hồi. |
| Public client sender constraint | Token được bound/rotation theo profile. | AS kiểm proof/binding; không chấp nhận raw stolen token trái policy. |

### 23.7. Pseudocode test revocation end-to-end

~~~text
test "opaque access token becomes inactive after revoke":
    T1 = issueTestOpaqueAccessToken(
        client=shopBff,
        audience=ordersApi,
        scope={ordersRead},
        expiresIn=600
    )
    assert introspectAsTrustedRS(T1).active == true

    result = revokeAsAuthorizedClient(T1)
    assert result.HTTP == 200

    afterPropagation = introspectAsTrustedRSWithoutCache(T1)
    assert afterPropagation.active == false

    assert ordersApiWithFreshState(T1).status in {401, 403}

test "wrong audience cannot use an active token":
    T2 = issueTestOpaqueAccessToken(
        audience=paymentsApi, scope={paymentsRead}
    )
    assert introspectAsTrustedCaller(T2).active == true
    assert ordersApi(T2) rejects bearer

test "refresh rotation is atomic":
    R1 = issueTestRefreshToken(family=F1)
    results = runInParallel(
        refresh(R1),
        refresh(R1)
    )
    assert exactly one successful R1 consumption
    assert no two independent active descendants are issued
    assert later reuse triggers configured family risk policy
~~~

Pseudocode không chạy trực tiếp; integration tests cần issuer/AS/RS thật của môi trường test, clock injection, database transaction, token signing/config tương ứng, HTTP error assertions và cache invalidation tests. **Không dùng real production bearer tokens**.

## 24. Bài tập tình huống và đáp án

### Bài 1 — Opaque có khiến token không thể bị đánh cắp?

Token `T1` là 43 ký tự Base64URL ngẫu nhiên, lưu trong browser local storage và được dùng như Bearer tại Orders API.

**Hỏi:** Nếu XSS đánh cắp T1 thì nó có an toàn hơn JWT vì không decode được không?

**Đáp án:** Không ở khía cạnh **bearer replay**. Attacker không cần decode T1; chỉ cần gửi đúng chuỗi đến RS trong thời gian T1 active. Opaque có thể giấu claims khỏi người nhìn chuỗi và hỗ trợ server-side revocation, nhưng phải bảo vệ storage, XSS, TLS, scope/audience, TTL và sender constraint nếu phù hợp.

### Bài 2 — `active=true` có đủ đọc mọi đơn không?

~~~json
{
  "active": true,
  "sub": "user-742",
  "aud": "orders-api",
  "scope": "orders:read"
}
~~~

Request `GET /tenants/tenant-anpha/orders/42`, nhưng user-742 không thuộc Anpha.

**Đáp án:** Từ chối. Introspection chứng minh token active cho API theo contract, **không cấp quyền trên tenant/order**. Resource Server phải kiểm tenant membership, ownership/ACL và các điều kiện nghiệp vụ.

### Bài 3 — Revocation HTTP 200 có đủ chắc chắn token bị thu hồi?

Client gửi revoke token `UNKNOWN_TOKEN_123` tới RFC 7009 endpoint, nhận HTTP 200.

**Đáp án:** HTTP 200 **không xác nhận token đã tồn tại**. Endpoint trả success khi request xử lý được kể cả token vô hiệu, tránh enumeration. Muốn xác minh behavior tổng thể, dùng token **test do AS phát**, revoke, đợi theo SLA/consistency, gọi introspection/RS qua đường test có kiểm soát.

### Bài 4 — Opaque với cache 60 giây

~~~text
10:00:00 RS caches active=true for 60 seconds
10:00:05 AS revokes token
10:00:30 attacker sends token
10:01:00 cache expires
~~~

**Hỏi:** Attacker có thể thành công tại 10:00:30 không?

**Đáp án:** **Có thể**, nếu RS tin cache positive đến expiry và object policy khác vẫn cho phép. Opaque không bảo đảm instant revocation. Giảm TTL, invalidation events, state check cho hành động nhạy cảm và đo revocation SLA toàn cụm.

### Bài 5 — Hai refresh requests cùng một R1

Client gửi hai refresh requests đồng thời vì hai workers thấy access token hết hạn.

**Đáp án:** AS phải **consume R1 nguyên tử**, không tạo hai hậu duệ active. Một request có thể bị xem là reuse theo policy. Client nên có single-flight refresh coordinator, không nới indefinitely khả năng dùng lại R1.

### Bài 6 — Client secret bị lộ nhưng chỉ revoke một access token

Một partner bị lộ `client_secret`. Nhóm vận hành chỉ revoke một opaque access token đã quan sát trong logs.

**Đáp án:** **Chưa đủ**. Attacker có thể tiếp tục dùng client secret xin token mới. Cần rotate/revoke client secret, xem xét disable client/related grants, xử lý issued tokens, review audit, storage/CI/log exposure và policy least privilege.

### Bài 7 — JWT hay opaque cho API nhạy cảm?

Một hệ thống cần ngăn token đã revoke được sử dụng tại `payments-api` trong vòng 5 giây theo SLA, đồng thời xử lý lưu lượng lớn.

**Đáp án:** Chọn định dạng không đủ. Có thể dùng opaque với introspection cache rất ngắn/strong consistency/invalidation, hoặc JWT với state/denylist checks, hay phương án hybrid. Cần tính propagation/caching/clock, kiểm đa vùng và test SLA thực tế. **Opaque với TTL cache 60 giây không tự đáp ứng SLA 5 giây.**

### Bài 8 — Nhầm ID token, opaque access token và opaque refresh token

~~~text
Token A: JWT aud=shop-web issued for OIDC client
Token B: Opaque token issued for orders-api, scope=orders:read
Token C: Opaque refresh token stored server-side
~~~

**Câu trả lời:**

- OIDC Client xác minh **A** như ID token, không gửi A tới Orders API.
- Orders API nhận **B** và introspect/kiểm resource authorization.
- Client trình **C** ở AS token endpoint theo Refresh Token Grant khi hợp lệ, không gửi C làm bearer tới RS.
- Khi revoke C, token family/grant effects phải theo provider policy; **B có thể còn được nhận** trong một khoảng nếu RS không kiểm state tương ứng.

### Bài 9 — Thu hồi consent khi RS đang offline

User rút consent `orders:read`. AS đã commit revoke, nhưng một RS mất kết nối với AS và còn positive cache hết hạn sau hai phút.

**Đáp án:** Phải xét **outage/revocation policy**: với API high-risk, không thể hứa chặn trong 5 giây nếu cache còn 120 giây và không có invalidation. Điều chỉnh TTL, authoritative lookup, fail-closed behavior và kiến trúc đồng bộ; đừng coi log “revoke committed” là proof mọi RS đã từ chối token.

## 25. Checklist triển khai

- [ ] Xác định token nào là opaque access, opaque refresh, JWT access và OIDC ID token theo purpose/profile.
- [ ] Tạo opaque token bằng CSPRNG có entropy cao, không dựa vào timestamp/user ID/counter.
- [ ] Không tái sử dụng raw bearer token giữa access và refresh purposes.
- [ ] Lưu token fingerprint/HMAC khi phù hợp, bảo vệ metadata/token store, không ghi raw tokens vào DB/log không cần thiết.
- [ ] AS lưu grant, client, subject/principal type, audience, scopes, issued/expiry, revoked state và version theo contract.
- [ ] Trạng thái `REVOKED` là terminal cho credential; phát token mới khi quyền được khôi phục.
- [ ] Token expiry và grant/client/user state được kiểm theo policy; không chỉ lookup thấy record là active.
- [ ] RS dùng HTTPS trusted introspection endpoint theo RFC 7662.
- [ ] RS introspection caller được xác thực/ủy quyền; không công bố token metadata cho mọi caller.
- [ ] `token_type_hint` chỉ là hint, không thay token purpose validation.
- [ ] RS parse `active` đúng boolean; `active=false` hoặc malformed response dẫn tới từ chối.
- [ ] Introspection `active=true` không tự vượt kiểm `iss`, `aud`, `scope`, token purpose và sender binding.
- [ ] End-user và service principals được phân biệt, không gán user theo headers/body tự khai.
- [ ] Resource Server kiểm tenant membership, ownership/ACL và object-level authorization độc lập.
- [ ] RFC 7009 revocation endpoint hoạt động với client auth/policy phù hợp và không tiết lộ token existence qua response.
- [ ] Biết rõ revocation một token, một refresh family, một grant và disable client có **phạm vi khác nhau**.
- [ ] Access token mới không tiếp tục được cấp sau khi grant/consent đã revoke theo policy.
- [ ] Positive introspection cache có TTL hữu hạn và không vượt token expiry.
- [ ] Revocation SLA bao gồm cache TTL, replication lag, event delivery và request in-flight.
- [ ] Event invalidation có version/ordering, retry/reconciliation và TTL fallback.
- [ ] Khi AS introspection không sẵn sàng, RS không mặc định fail-open.
- [ ] Refresh-token rotation dùng atomic consume, client single-flight và reuse/family revocation policy.
- [ ] AS kiểm scope refresh không được mở rộng ngoài grant.
- [ ] DPoP/mTLS sender-bound tokens được RS kiểm proof nếu được cấp theo profile.
- [ ] BFF/browser bảo vệ session và token storage, chống XSS/CSRF, không dùng URL query chứa tokens.
- [ ] HTTP RS phân biệt token invalid (`401`) với thiếu scope (`403`) theo Bearer error profile.
- [ ] Logs/traces/metrics không chứa raw access token, refresh token, Basic introspection credential hoặc UserInfo PII.
- [ ] Có incident playbook khi lộ access token, refresh token, client secret và signing key với scope ứng cứu khác nhau.
- [ ] Có test cho issuer, audience, wrong scope/tenant, expired/revoked token, malformed introspection, cache lag, RS outage, refresh replay và concurrency.
- [ ] Đã đo revocation latency **end-to-end ở tất cả RS**, không chỉ thời gian AS commit trạng thái.
- [ ] Khi không xác minh được hiệu lực hoặc quyền cần thiết, hệ thống **fail closed** theo chính sách đã công bố.

**Ghi nhớ:** **Opaque token là credential không tự mô tả; metadata và trạng thái được kiểm tại một nguồn server đáng tin.** Nó tạo điều kiện để thu hồi truy cập, nhưng **tốc độ thu hồi thực tế bị chi phối bởi introspection, cache và consistency**. **RFC 7662 hỏi token active không; RFC 7009 yêu cầu thu hồi token**. Dù token `active=true`, Resource Server vẫn phải kiểm **issuer, audience, scope, principal, tenant và quyền từng tài nguyên**. Access token bị lộ có thể bị replay trước khi state lan tới RS; refresh token bị lộ còn có nguy cơ tạo nhiều access tokens mới. Thiết kế an toàn kết hợp **entropy, least privilege, secure storage, atomic revocation/rotation, bounded cache, fail-closed và kiểm thử SLA thực tế**.

## 26. Tài liệu chuẩn tham khảo

- **RFC 7662 — OAuth 2.0 Token Introspection:** introspection endpoint, `active`, metadata, caller authentication/authorization và caching/security considerations.
- **RFC 7009 — OAuth 2.0 Token Revocation:** revocation request, `token_type_hint`, HTTP 200 semantics, revocation behavior và security considerations.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** access/refresh token, token endpoint, `client_credentials`, `authorization_code`, scope và Refresh Token Grant.
- **RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage:** `Authorization: Bearer`, HTTP `401/403`, `invalid_token`/`insufficient_scope` và bearer leakage/replay.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `sub`, `aud`, `exp` và JWT claims khác reference token.
- **RFC 8725 — JWT Best Current Practices:** token-substitution, signature/algorithm/issuer/audience validation và key trust.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** JWT access-token claims, `aud`, `scope` và RS validation.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** access/refresh token hardening, refresh rotation/replay, PKCE, least privilege và OAuth security recommendations.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** bảo vệ authorization code; không thay introspection/revocation.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** token targeting đến resource/audience đúng.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** sender-constrained tokens và proof validation.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** mTLS client auth/certificate-bound tokens.
- **RFC 8693 — OAuth 2.0 Token Exchange:** delegation/actor/target audience khi service cần token mới, không chuyển sai resource.
- **OpenID Connect Core 1.0:** ID token và OP authentication, phân biệt access token cho Resource Server/UserInfo.
- **OWASP OAuth 2.0 Cheat Sheet / Secrets Management Cheat Sheet:** token/credential storage, replay defense, revocation và secret rotation.
- **OWASP API Security Top 10:** Broken Object Level Authorization, Broken Authentication và Broken Function Level Authorization.
- **Spring Security Reference — OAuth2 Resource Server Opaque Tokens:** `opaquetoken` properties, `OpaqueTokenIntrospector`, Spring authorization integration và authority mapping.
- **Spring Authorization Server Reference:** token/grant persistence, refresh-token rotation, token endpoint và authorization management.
