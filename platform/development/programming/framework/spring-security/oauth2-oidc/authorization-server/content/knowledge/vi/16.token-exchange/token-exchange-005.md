# Xác minh subject token, trạng thái token và chính sách đổi token

> **Chương: Token Exchange.** Bài học thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**: thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Mục tiêu là hiểu **vì sao subject token hợp lệ chưa đủ để được đổi token**, cách kiểm tra trạng thái token, ràng buộc client/actor và áp dụng chính sách **audience, resource, scope, tenant, delegation** trước khi cấp token mới.

## 1. Token Exchange giải quyết bài toán gì?

OAuth 2.0 Token Exchange (RFC 8693) mở rộng token endpoint để một OAuth client trình một security token hiện có (**subject token**) và đề nghị Authorization Server, đóng vai trò **Security Token Service (STS)**, phát một token khác phù hợp với đối tượng tài nguyên hoặc ngữ cảnh ủy quyền mới.

Ví dụ:

- **Authorization Server:** `https://login.example.vn`.
- **Người dùng:** `user-123` đã đăng nhập, có access token gốc để gọi `orders-api`.
- **Dịch vụ trung gian:** `orders-service` là **confidential OAuth client**, cần gọi `reports-api` trong cùng một thao tác nghiệp vụ.
- **Dịch vụ đích:** `reports-api` chỉ chấp nhận token có audience `reports-api` và quyền `reports.read`.
- **Client ID của bên đổi token:** `orders-service`, được xác thực tại token endpoint; **không** mặc định là người dùng trong subject token.

Nếu gửi access token gốc trực tiếp đến `reports-api`, tài nguyên đích có thể từ chối vì `aud` không đúng. Token Exchange cho phép AS **đánh giá chính sách** rồi phát access token mới, ví dụ có `aud=reports-api` và quyền hẹp `reports.read`.

**Token Exchange không phải:**

1. **Refresh Token grant:** làm mới credential cho cùng authorization, không chủ yếu chuyển đổi trust context/target.
2. **Client Credentials grant:** cấp quyền dưới danh tính client, không dựa trên một subject token đại diện chủ thể khác.
3. **Chuyển tiếp nguyên access token gốc:** có thể dẫn tới *confused deputy* và dùng token sai audience.
4. **Cơ chế tự động nâng quyền:** không vì token gốc có scope rộng hay người dùng có vai trò admin mà AS phải cấp scope mới.
5. **ID Token exchange mặc định:** ID Token dùng cho RP xác minh đăng nhập, không được tự coi là access token để đổi quyền API.

Một hệ thống an toàn chỉ phát token mới sau **hai bước độc lập**: (1) xác thực và kiểm tra token đầu vào; (2) xác định client, chủ thể và đích **có được phép trao đổi** theo policy không.

### 1.1. Các chủ thể và ranh giới tin cậy

| Thành phần | Vai trò | Không được suy ra điều gì |
|---|---|---|
| **Authenticated exchanging client** | Client gửi token request và tự xác thực, ví dụ `orders-service` | Client có secret hợp lệ **không tự có quyền** thay mặt mọi user |
| **Subject token** | Chứng cứ về chủ thể đang được đại diện, ví dụ `user-123` | Chữ ký JWT hợp lệ **không tự chứng minh** client được đổi token |
| **Actor token** (nếu có) | Chứng cứ về thực thể đang hành động thay chủ thể | Có actor token không tự tạo quyền delegation |
| **Authorization Server / STS** | Kiểm tra token, policy và cấp token mới | Không tin các claim chưa xác minh, URI đích tự khai hoặc role từ input |
| **Target Resource Server** | Chỉ nhận token đúng audience/issuer/quyền, kiểm tra nghiệp vụ | Không dùng token dành cho service khác chỉ vì cùng issuer |

### 1.2. Sơ đồ luồng cơ bản

```mermaid
sequenceDiagram
    autonumber
    participant User as Người dùng
    participant Orders as orders-service (OAuth client)
    participant AS as Authorization Server / STS
    participant Store as Authorization/token store
    participant Reports as reports-api

    User->>Orders: Yêu cầu tạo báo cáo, gửi access token gốc S0
    Orders->>Orders: Xác thực yêu cầu API, xác định nghiệp vụ hợp lệ
    Orders->>AS: POST /oauth2/token, client auth<br/>grant_type=token-exchange, subject_token=S0,<br/>audience=reports-api, scope=reports.read
    AS->>AS: Xác thực orders-service, kiểm tra grant được đăng ký
    AS->>Store: Tìm S0 và trạng thái authorization
    Store-->>AS: Chủ thể, issuer, scopes, expiry, revoked/active
    AS->>AS: Kiểm tra token type, state, client/tenant,<br/>target, scope, delegation và policy
    alt Hợp lệ và được phép đổi
        AS-->>Orders: Access token T1 với aud=reports-api
        Orders->>Reports: Authorization: Bearer T1
        Reports->>Reports: Kiểm tra signature/iss/aud/exp/scope
        Reports-->>Orders: Báo cáo trong phạm vi được phép
    else Token sai hoặc bị policy từ chối
        AS-->>Orders: OAuth2 error, không phát T1
    end
```

## 2. Hợp đồng RFC 8693: request, response và token types

Token Exchange dùng token endpoint hiện có, thông thường `POST /oauth2/token` qua TLS, với body `application/x-www-form-urlencoded` và một **OAuth client được xác thực** theo chính sách của AS.

### 2.1. Ví dụ HTTP request

```http
POST /oauth2/token HTTP/1.1
Host: login.example.vn
Authorization: Basic REDACTED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange&subject_token=SUBJECT_ACCESS_TOKEN_REDACTED&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token&requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token&audience=reports-api&scope=reports.read
```

Các chuỗi viết hoa là **placeholder**, không phải credential thật. `Authorization: Basic` chỉ là ví dụ confidential client dùng `client_secret_basic`; client đăng ký `private_key_jwt` hoặc phương thức khác phải sử dụng cách xác thực tương ứng. **Không** đưa subject token vào query URL hoặc log request.

| Tham số RFC 8693 | Bắt buộc? | Vai trò |
|---|---|---|
| `grant_type` | Có | Chính xác `urn:ietf:params:oauth:grant-type:token-exchange` |
| `subject_token` | Có | Token mô tả chủ thể mà request xin cấp token thay mặt |
| `subject_token_type` | Có | Kiểu security token gốc, ví dụ `urn:ietf:params:oauth:token-type:access_token` |
| `requested_token_type` | Tùy chọn | Kiểu token mong muốn được cấp; nếu vắng, AS chọn theo policy |
| `resource` | Tùy chọn theo chuẩn | URI tuyệt đối của tài nguyên đích; có thể gửi lặp nếu profile cho phép |
| `audience` | Tùy chọn theo chuẩn | Tên logic của target service, ví dụ `reports-api`; có thể lặp theo chuẩn |
| `scope` | Tùy chọn | Scope mong muốn **trong ngữ cảnh target**, không mặc nhiên được kế thừa từ source |
| `actor_token` | Tùy chọn | Token thể hiện bên đang hành động thay subject |
| `actor_token_type` | Bắt buộc **khi có `actor_token`** | Cho biết loại actor token; không gửi nếu không có actor token |

Một tổ chức có thể đặt policy **bắt buộc đúng một audience/resource được phê duyệt** dù RFC cho phép nhiều. Điều này giúp tránh cấp token dùng được ở quá nhiều dịch vụ. Nếu phải hỗ trợ nhiều đích, AS cần xét quyền cho **mỗi cặp (scope, target)**, không chỉ hợp nhất audience tùy tiện.

### 2.2. Token type URN khác token format

- `urn:ietf:params:oauth:token-type:access_token` có nghĩa **một OAuth access token**, không khẳng định nội dung là JWT.
- `urn:ietf:params:oauth:token-type:jwt` nêu hình thức JWT; JWT hợp lệ về cú pháp vẫn cần đúng **ngữ nghĩa và chính sách**.
- `urn:ietf:params:oauth:token-type:id_token` không được dùng làm access token dành cho API chỉ vì nó cũng là JWT.
- `urn:ietf:params:oauth:token-type:refresh_token` có vòng đời, quyền sử dụng khác; không biến nó thành subject access token nếu hệ thống chưa định nghĩa rõ.
- Một opaque access token có thể cần tra `OAuth2AuthorizationService` hoặc introspection; không cố parse nó như JWT.

**Không dùng `subject_token_type` do caller gửi để lựa chọn cách kiểm tra thiếu tin cậy**. Đây là lời khai yêu cầu được so khớp với **loại token xác minh được**. Sai kiểu hoặc kiểu chưa được phép phải bị từ chối, không fallback về kiểm tra yếu hơn.

### 2.3. Response thành công

```json
{
  "access_token": "ISSUED_ACCESS_TOKEN_REDACTED",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "reports.read"
}
```

`issued_token_type` mô tả token được **phát trong response**, không phải kiểu subject token đầu vào. `token_type` như `Bearer` cho biết cách trình token tới tài nguyên, không phải JWT hay opaque. `refresh_token` **không mặc nhiên** xuất hiện trong Token Exchange; RFC 8693 cho phép trong trường hợp có policy cụ thể nhưng thông thường chỉ cần access token ngắn hạn.

## 3. Xác minh subject token: không chỉ giải mã JWT

Một JWT có đủ ba đoạn base64url hoặc được decode thành claims chỉ chứng minh **định dạng**, chưa chứng minh token do nguồn tin cậy phát hành, chưa hết hạn, chưa bị thu hồi hay có quyền đổi.

### 3.1. Tám nhóm kiểm tra trước khi xem xét cấp token mới

| Nhóm kiểm tra | Điều kiện phải đạt | Nếu bỏ qua |
|---|---|---|
| **1. Kiểu token** | `subject_token_type` thuộc profile được AS hỗ trợ; token thực tế khớp loại này | Nhầm ID Token/refresh token/client assertion với access token |
| **2. Nguồn tin cậy** | `iss` thuộc allowlist/trust anchor phù hợp, không nhận issuer từ input để tự thêm vào trust store | Tin token được ký bằng khóa của attacker |
| **3. Mật mã/lookup** | JWT có chữ ký, `alg`, `kid`, JWK tin cậy đúng policy; opaque token được tra kho tin cậy/introspection | Chấp nhận token giả hoặc chưa phát hành |
| **4. Thời gian** | `exp` chưa hết hạn; `nbf` hợp lệ; `iat`/TTL/skew theo policy | Đổi token đã hết hạn hoặc chưa có hiệu lực |
| **5. Trạng thái** | Không revoked, không invalidated, authorization còn hiệu lực; trạng thái active được đọc từ nguồn phù hợp | “Rửa” token đã bị thu hồi thành token mới |
| **6. Đối tượng và phạm vi** | `aud`/resource context ban đầu phù hợp nguồn nhận token, scope của subject đã được cấp; subject có quyền xin chuyển đích | Đổi token từ API không liên quan, nâng quyền |
| **7. Client/tenant binding** | Client đang exchange có quyền sử dụng subject theo quan hệ, tenant và sender binding | Client A đổi token của user/tenant/client B |
| **8. Chính sách mục tiêu** | Target được phép, scope hẹp, vai trò/consent/actor đáp ứng policy | Phát token cho target không được phê duyệt |

**Lưu ý audience nguồn:** Không phải mọi token exchange đều giữ nguyên `aud` của subject token trong output; chuyển audience có thể là mục tiêu chính của giao thức. Nhưng **nguồn token phải được thiết kế để được trình cho STS/chuỗi dịch vụ đó** hoặc được policy chấp thuận rõ ràng. Một token chỉ dùng cho một Resource Server không nên tự động được chấp nhận ở mọi STS chỉ vì cùng issuer.

### 3.2. Ví dụ JWT subject token

Một access token gốc có thể mang claims:

```json
{
  "iss": "https://login.example.vn",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "portal-web",
  "scope": "orders.read reports.read",
  "iat": 1794790000,
  "exp": 1794790300,
  "jti": "source-token-identifier",
  "tenant_id": "tenant-a"
}
```

Đây chỉ là **JSON payload minh họa**, không phải JWT đã ký. Trước khi dùng bất cứ claim nào cho chính sách:

1. Kiểm tra signature/issuer/algorithm/key đúng nguồn tin cậy.
2. Kiểm tra token type và thời gian, kết hợp trạng thái runtime.
3. Kiểm tra chính sách cho việc `orders-service` đại diện `user-123` tại `tenant-a`.
4. Kiểm tra đích `reports-api` có cho phép `reports.read` với tình huống nghiệp vụ này không.
5. Nếu cấp token, phát một **JWT mới được ký bởi AS**, với `aud=reports-api` và quyền phù hợp; không chỉ sửa payload cũ rồi serialize lại.

**Chữ ký hợp lệ không có nghĩa token còn active.** JWT tự chứa có thể vẫn xác minh chữ ký dù quyền đã bị thu hồi hoặc người dùng đã bị vô hiệu ở backend. Cần chiến lược kiểm tra trạng thái tương ứng mức rủi ro.

### 3.3. JWT tự chứa, opaque token và token ngoại lai

| Dạng đầu vào | Cách xác minh phù hợp | Giới hạn cần chú ý |
|---|---|---|
| JWT do **chính AS** phát, có authorization được lưu | Xác minh metadata và truy xuất `OAuth2AuthorizationService`, kiểm tra token `isActive()`, claims và policy | Chỉ decode JWT không thay cho tra trạng thái nếu kiến trúc hứa revocation |
| Opaque access token do AS cấp | Dùng lookup chính xác trong authorization store hoặc introspection đáng tin | Không có JWT header/claims để tự parse |
| JWT từ **issuer bên ngoài** | Cần federation/trust registry, kiểm tra issuer/signature/audience/claims và trạng thái theo profile; có thể dùng introspection hoặc liên kết trust riêng | **Không được** giả định provider mặc định của Spring tự chấp nhận tất cả JWT external |
| SAML assertion/loại token khác | Cần validator/token translator chuyên biệt theo profile | Không đổi type URN rồi mong framework tự hỗ trợ |

Với JWT bên ngoài, `JwtDecoder` từ issuer bất kỳ **không** đủ cho bài toán STS: phải xác định **issuer nào được tin, audience nào dùng cho exchange, token được trình bởi client nào và quan hệ ủy quyền ra sao**. Cũng phải bảo vệ việc tải JWKS khỏi SSRF và key substitution.

## 4. Trạng thái token: active, expired, revoked, invalidated, unknown

OAuth2 token có thể đang tồn tại về mặt định dạng nhưng **không còn được phép sử dụng**. AS cần phân biệt ít nhất:

| Trạng thái | Ý nghĩa | Quyết định đổi token |
|---|---|---|
| **Active** | Token tồn tại, còn thời hạn và chưa bị invalidated theo kho đáng tin | Có thể tiếp tục **đánh giá policy**, chưa mặc nhiên cấp token |
| **Expired** | `now ≥ exp` hoặc hết hiệu lực theo token store | Từ chối |
| **Revoked/invalidated** | Chủ sở hữu, client hoặc quản trị viên đã thu hồi; token lưu metadata invalid | Từ chối; không phát token mới |
| **Unknown** | Không tìm thấy token, wrong issuer/store, không introspect được | **Fail closed**, không suy từ JWT có chữ ký mà cho qua nếu policy đòi lookup |
| **Not yet valid** | `nbf` ở tương lai vượt clock skew | Từ chối |
| **Actor invalid** | Subject có thể active nhưng actor token đã revoked/expired | Từ chối yêu cầu delegation có actor |
| **Session/consent changed** | Phiên, quyền, người dùng hoặc tenant không còn hợp lệ | Tùy policy phải từ chối/hạ quyền; không dùng snapshot cũ vô thời hạn |

Trong Spring Authorization Server, `OAuth2Authorization.Token.isActive()` cung cấp kiểm tra trạng thái token ở tầng authorization metadata. Nhưng **active không tự bao gồm** các chính sách bên ngoài như tài khoản bị khóa, tenant suspended, phiên độ tin cậy cao đã hết hạn, consent vừa thu hồi hoặc audience được phê duyệt. Cần đánh giá riêng nếu ứng dụng yêu cầu.

### 4.1. Token Exchange không tự tiêu thụ subject token

RFC 8693 nêu: nếu loại token không có ngữ nghĩa dùng một lần, **exchange không tự làm subject token hoặc actor token mất hiệu lực**. Khi đã đổi `S0 → T1`, subject token `S0` thường vẫn còn hiệu lực cho mục đích ban đầu.

Ngoài ra, RFC 8693 **không tạo liên kết trạng thái chặt tự động** giữa input và output. Nếu `S0` bị thu hồi sau đó, `T1` không tự mất hiệu lực trong mọi triển khai; cần thiết kế **revocation propagation**, introspection, TTL ngắn hoặc token lineage riêng khi nghiệp vụ yêu cầu.

### 4.2. Phòng tránh race với logout/revocation

```mermaid
sequenceDiagram
    autonumber
    participant Client as Exchanging client
    participant AS as Authorization Server
    participant Store as Shared authorization store
    participant Admin as Revoke / Logout service

    Client->>AS: Exchange subject S0
    AS->>Store: Đọc S0 active
    Admin->>Store: Revoke S0/authorization
    AS->>AS: Đang áp policy dựa snapshot cũ
    Note over AS,Store: Cần thứ tự commit và re-check phù hợp<br/>trước khi phát token đích
    alt Revocation thắng theo policy
        AS-->>Client: Từ chối exchange; không cấp token mới
    else Exchange commit hợp lệ trước revocation
        AS-->>Client: Phát T1, lưu lineage/audit
        Admin->>Store: Propagate revoke T1 nếu policy yêu cầu
    end
```

Với thao tác nhạy cảm, phải xác định yêu cầu **“revoke wins”** hay quy tắc thứ tự commit. Dùng transaction/snapshot version hoặc kiểm tra trạng thái gần bước cấp token. Nếu status service bên ngoài không sẵn sàng và policy bắt buộc kiểm tra live status, **không** dùng trạng thái “có vẻ active” trong cache cũ để phát quyền mạnh hơn.

### 4.3. Cache trạng thái và consistency

- Token tự chứa + Resource Server xác minh offline: nhanh, nhưng revocation có thể không tức thời.
- Opaque token + introspection: kiểm tra trạng thái tập trung dễ hơn, nhưng tăng phụ thuộc mạng và cache.
- Lookup tại `OAuth2AuthorizationService`: thích hợp token do AS phát và có lưu authorization; khi nhiều pod, store phải bền vững/nhất quán.
- Cache token status theo TTL: nếu có, phải xác định rủi ro chấp nhận token đã revoke trong TTL đó; với exchange vào target nhạy cảm, thường cần kiểm tra sát thực tế hơn.
- Đối với *replay protection* hoặc token loại một lần, cần trạng thái đã dùng/consumed với atomic update; **Token Exchange chuẩn không tự làm mọi subject token thành one-time token**.

## 5. Chính sách đổi token: chống nâng quyền và confused deputy

Mặc định an toàn cho hệ thống production là **deny-by-default** và cho phép exchange theo quan hệ đã định nghĩa: client nào, loại token nguồn nào, issuer nào, subject/tenant nào, target nào, scope nào, TTL và ngữ cảnh nghiệp vụ nào.

### 5.1. Ma trận policy minh họa

| Exchanging client | Subject token | Target cho phép | Scope output tối đa | Quy tắc khác |
|---|---|---|---|---|
| `orders-service` | Access token của user hợp lệ, issuer công ty, `tenant-a` | `reports-api` | `reports.read` | User/tenant còn active; request báo cáo hợp lệ; token nguồn chứa bằng chứng quyền thích hợp |
| `billing-service` | Token ứng dụng của `billing-job` | `invoices-api` | `invoices.read` | Chỉ service identity đã đăng ký; không tự đổi thành user token |
| `portal-web` | Access token của user tại RP | **Không** cho đổi tùy ý sang `admin-api` | Không áp dụng | Chặn escalation dù `portal-web` có thể xác thực client |
| Client bất kỳ | JWT của issuer ngoài chưa đăng ký tin cậy | Bất kỳ | Không áp dụng | Từ chối; không bootstrap trust bằng URL trong token |
| `orders-service` | Access token của user `tenant-b` | `reports-api` của `tenant-a` | Không áp dụng | Chặn cross-tenant |

**Policy không thể chỉ là `requestedScopes ⊆ registeredClient.getScopes()`.** Một client được đăng ký scope `reports.write` vẫn không thể tự cấp quyền đó nếu subject/source authorization và target policy không cho phép. Ngược lại, scope ở target có thể khác tên so với source; muốn ánh xạ phải khai báo quy tắc **tường minh** và có review, không dùng chuỗi trùng tên làm bằng chứng duy nhất.

### 5.2. Các tập quyền và ngữ cảnh phải được kết hợp

Ký hiệu:

- **C:** tập scope mà exchanging client được phép yêu cầu theo registration/policy.
- **S:** tập quyền từ **subject token đã xác minh**, cộng quyền/consent thực còn hiệu lực.
- **T:** tập quyền cho phép tại target audience và quan hệ client→target.
- **R:** tập scope client đang yêu cầu trong exchange.
- **G:** tập scope thực sự được cấp ở output.

Với mô hình quyền có **cùng ngữ nghĩa và cùng tên scope**, nguyên tắc cơ bản:

```text
R ⊆ C
R ⊆ S
R ⊆ T
G ⊆ R ∩ C ∩ S ∩ T
```

Nếu `S` và `T` dùng từ vựng scope khác nhau (ví dụ `orders.read` ↔ `reports.read`), cần một **mapping có kiểm soát** `f(S, resource, actor, businessContext)`. Không thể lấy giao tập hợp theo tên chuỗi rồi khẳng định mọi trường hợp đều đúng; nhưng càng không thể mặc định `G=R` chỉ vì client xin.

Đầu ra còn phải xác lập:
- `iss` của AS phát token mới;
- `sub` đúng chủ thể theo impersonation/delegation được cấp phép;
- `aud` chỉ target đã duyệt, tránh cấp token đa audience không cần thiết;
- `scope`/roles đã lọc;
- `exp`/TTL theo chính sách, thường ngắn, không tự kéo dài thời gian tin cậy của chủ thể vượt mức cho phép;
- thông tin actor/delegation được bảo toàn khi chính sách yêu cầu, để API đích phân biệt user và service đang hành động.

### 5.3. Ví dụ bộ lọc policy bằng Java

Đây là **business-policy helper minh họa** dùng sau khi **đã xác minh subject token, client authentication, actor và trạng thái active**. Nó **không thay thế** AuthenticationProvider, JWT decoder hay token endpoint của Spring.

```java
import java.util.Set;

record VerifiedExchangeContext(
        String clientId,
        String subjectId,
        String tenantId,
        boolean subjectActive,
        boolean actorAuthorized,
        Set<String> sourceScopes,
        Set<String> requestedScopes,
        Set<String> requestedAudiences) {}

record TargetPolicy(
        String audience,
        String tenantId,
        Set<String> allowedClientIds,
        Set<String> allowedScopes) {}

record ExchangeDecision(String audience, Set<String> grantedScopes) {}

static ExchangeDecision evaluate(
        VerifiedExchangeContext request,
        TargetPolicy target,
        Set<String> registeredClientScopes) {

    if (!request.subjectActive() || !request.actorAuthorized()) {
        throw new SecurityException("Exchange not permitted");
    }
    if (!target.tenantId().equals(request.tenantId())
            || !target.allowedClientIds().contains(request.clientId())) {
        throw new SecurityException("Client or tenant not permitted");
    }

    // Chính sách ví dụ: chỉ cho một target có tên được đăng ký.
    if (!request.requestedAudiences().equals(Set.of(target.audience()))) {
        throw new SecurityException("Invalid target");
    }

    Set<String> requested = request.requestedScopes();
    if (requested.isEmpty()
            || !registeredClientScopes.containsAll(requested)
            || !request.sourceScopes().containsAll(requested)
            || !target.allowedScopes().containsAll(requested)) {
        throw new SecurityException("Scope escalation denied");
    }

    return new ExchangeDecision(target.audience(), Set.copyOf(requested));
}
```

**Ranh giới của mã:**

1. Mọi field trong `VerifiedExchangeContext` phải được dẫn xuất từ **client đã xác thực, token đã xác minh và nguồn policy đáng tin**, không trực tiếp từ request body.
2. `actorAuthorized` phải được tính từ policy thật về delegation/impersonation (hoặc `true` chỉ với trường hợp không cần actor và đã duyệt kiểu exchange đó); không lấy boolean từ JSON client gửi.
3. Helper này **cố ý nghiêm ngặt**: quyền nguồn/đích phải có **cùng tên scope**. Muốn chuyển đổi giữa các scope khác tên, thay điều kiện bằng mapping được quản trị, kiểm thử không nâng quyền.
4. `SecurityException` chỉ là kết quả nội bộ cho dễ đọc; adapter token endpoint phải chuyển thành **OAuth2Error phù hợp**, không gửi stack trace/chi tiết tenant hay token ra client.
5. Hàm này **chưa kiểm tra audience nguồn, subject/client relation, account status, TTL và sender-constraining**. Đó là các điều kiện phải xử lý trước khi gọi helper.

Không sử dụng helper ở token customizer **sau khi** token đã được phát; chính sách phải chặn yêu cầu **trước bước sinh/lưu/ghi trả token**.

## 6. Delegation, impersonation và actor token

RFC 8693 mô tả hai trường hợp:

- **Impersonation:** token đầu ra cho phép bên sử dụng hành động như chủ thể được đại diện. Không nhất thiết lộ một actor riêng trong token; do đó nguy cơ nhầm danh tính cao nếu không có chính sách.
- **Delegation:** có một actor hành động **thay mặt** subject. Output có thể mang claim `act` cho biết ai đang thực hiện hành động; dịch vụ đích cần phân biệt subject và actor trong audit/authorization.

Ví dụ output JWT delegation (payload minh họa):

```json
{
  "iss": "https://login.example.vn",
  "sub": "user-123",
  "aud": ["reports-api"],
  "scope": "reports.read",
  "client_id": "orders-service",
  "act": {
    "sub": "orders-service"
  },
  "exp": 1794790300
}
```

- `sub=user-123`: chủ thể mà hành động diễn ra thay mặt.
- `act.sub=orders-service`: dịch vụ đang hành động.
- `client_id=orders-service`: định danh client theo profile/claims phát hành của AS; kiểm tra ý nghĩa cụ thể ở Resource Server.
- `aud=reports-api`: đối tượng tài nguyên đích.
- `scope=reports.read`: quyền sau chính sách giảm quyền.

### 6.1. Kiểm tra actor token

Nếu request gửi `actor_token`, RFC 8693 yêu cầu `actor_token_type` đi kèm. AS phải:

1. Xác minh actor token theo **kiểu, issuer, signature/lookup, thời gian và trạng thái** của chính actor.
2. Kiểm tra actor hiện tại có được phép thay mặt subject hay không, có quan hệ thuộc tenant, chủ sở hữu và target phù hợp.
3. Khi có claim `may_act` trong subject token, hiểu đó là **tín hiệu ủy quyền do bên phát subject token đáng tin cung cấp**, nhưng vẫn kiểm tra đúng actor và policy. Không lấy `may_act` từ token không được xác minh.
4. Không biến việc có hai token “đều active” thành bằng chứng delegation. Phải có **ràng buộc** cho hai chủ thể.
5. Khi output phát hành theo delegation, giữ chuỗi actor cần thiết/giới hạn độ sâu theo chính sách, không làm mất dấu vết nếu hệ thống cần audit.

### 6.2. Nếu không có actor token?

Không phải mọi yêu cầu Token Exchange đều có `actor_token`. Một số triển khai cho phép **impersonation** dựa trên client identity và subject token được chấp nhận; một số triển khai yêu cầu actor được xác thực rõ. Phải định nghĩa policy **từng client/use case**, không mặc định `actor absent ⇒ allow`.

**Không nhầm authenticated client với actor token:** client authentication chứng minh ai đang gửi request; actor token (nếu có) mô tả thực thể hành động trong delegation. Hai danh tính có thể trùng hoặc khác theo profile, nhưng không nên gộp một cách vô thức.

## 7. Spring Authorization Server: thành phần nào xác minh token?

Trong Spring Authorization Server 1.5.x, Token Exchange grant có hỗ trợ thông qua `OAuth2TokenExchangeAuthenticationConverter` và `OAuth2TokenExchangeAuthenticationProvider` ở token endpoint. Provider sử dụng `OAuth2AuthorizationService` và `OAuth2TokenGenerator`. Phiên bản thư viện khác, đặc biệt Spring Security 7.x khi Authorization Server được tích hợp, cần đối chiếu API tương ứng.

### 7.1. Một RegisteredClient được phép Token Exchange

```java
import java.time.Duration;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

static RegisteredClient exchangingClient(String encodedSecret) {
    return RegisteredClient.withId("registration-orders-service")
            .clientId("orders-service")
            .clientName("Orders Service")
            .clientSecret(encodedSecret)
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                    AuthorizationGrantType.TOKEN_EXCHANGE)
            .scope("reports.read")
            .tokenSettings(TokenSettings.builder()
                    .accessTokenTimeToLive(Duration.ofMinutes(5))
                    .build())
            .build();
}
```

Đây là **factory method**; phải thêm vào `RegisteredClientRepository` trước khi dùng. `encodedSecret` là **hash** mật khẩu của confidential client; bản rõ chỉ được cấp cho đúng client qua secret manager và TLS. Không đặt `{noop}secret` trong production.

**Lưu ý quan trọng:** cấu hình `authorizationGrantType(TOKEN_EXCHANGE)` chỉ cho phép loại grant; thêm `scope("reports.read")` chỉ đặt một giới hạn scope **trên registration**. Hai dòng này **không tự định nghĩa** quan hệ `orders-service → reports-api`, policy tenant hay quyền delegation. Phải có tầng policy riêng như mục 5.

### 7.2. Filter chain token endpoint

Ví dụ cấu hình khung cho Authorization Server (Spring Security 6.x / Spring Authorization Server 1.5.x):

```java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, Customizer.withDefaults())
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated());

    return http.build();
}
```

Các import thông thường thuộc `org.springframework.security.web.SecurityFilterChain`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer` và `org.springframework.security.config.Customizer`; `@Order` thuộc Spring Core.

Ngoài filter chain, AS cần `RegisteredClientRepository`, `OAuth2AuthorizationService`, token generator, `AuthorizationServerSettings`, signing/JWKSource nếu phát JWT và hạ tầng xác thực client. Không xây một controller `@PostMapping("/oauth2/token")` cạnh tranh với filter token endpoint chuẩn.

### 7.3. Đọc trạng thái subject token bằng repository

Ví dụ Java minh họa kiểm tra **subject access token do chính AS phát và còn lưu trong authorization service**:

```java
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.OAuth2Token;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;

record ActiveSubject(
        OAuth2Authorization authorization,
        OAuth2Authorization.Token<OAuth2Token> token) {}

static ActiveSubject requireActiveSubject(
        OAuth2AuthorizationService service, String rawSubjectToken) {

    OAuth2Authorization authorization = service.findByToken(
            rawSubjectToken, OAuth2TokenType.ACCESS_TOKEN);

    if (authorization == null) {
        throw new OAuth2AuthenticationException(
                new OAuth2Error(OAuth2ErrorCodes.INVALID_GRANT));
    }

    OAuth2Authorization.Token<OAuth2Token> token =
            authorization.getToken(rawSubjectToken);

    if (token == null || !token.isActive()) {
        throw new OAuth2AuthenticationException(
                new OAuth2Error(OAuth2ErrorCodes.INVALID_GRANT));
    }
    return new ActiveSubject(authorization, token);
}
```

Phương thức này là một **bước của pipeline** và cần được gọi **trong provider/validator đáng tin** ở phía server. Nó chưa kiểm tra `subject_token_type`, issuer, audience nguồn, subject/client relation, tenant, actor, target, scope và revocation ở hệ ngoài. Không đặt nó làm endpoint công khai chỉ nhận token từ bất kỳ client nào rồi trả thông tin authorization.

**Tương quan với Spring mặc định:** Trong mã xử lý Token Exchange của Spring, provider thường tra `OAuth2AuthorizationService.findByToken(..., ACCESS_TOKEN)`, kiểm tra token `isActive()` và một số điều kiện type/principal, grant và scope. Điều này **không** cho phép kết luận rằng provider mặc định đã áp dụng toàn bộ **custom business policy** về audience/resource, quan hệ client/subject/tenant, token lineage hoặc trust federation của tổ chức.

### 7.4. Mở rộng validation mà không vô hiệu các kiểm tra mặc định

`OAuth2TokenEndpointConfigurer` hỗ trợ `authenticationProviders(...)` để kiểm soát danh sách `AuthenticationProvider` xử lý token grants. Trong nhánh Spring Authorization Server 1.5.x, `OAuth2TokenExchangeAuthenticationProvider` là `final`, nên đừng viết ví dụ `extends OAuth2TokenExchangeAuthenticationProvider` rồi cho rằng sẽ compile.

Một chiến lược phù hợp là:

1. Giữ bộ xử lý protocol/token của Spring hoặc bọc/thay thế provider qua extension point chính thức.
2. Sau xác thực client, **trước khi sinh và trả token**, chạy validation bổ sung từ policy service.
3. Provider/adapter đọc subject authorization qua `OAuth2AuthorizationService`, actor nếu có, rồi đánh giá live token state và policy về target/scope/client/tenant.
4. Khi policy từ chối, trả `OAuth2AuthenticationException` với lỗi OAuth phù hợp. **Không** chỉ thêm kiểm tra ở `OAuth2TokenCustomizer` sau khi luồng cấp token đã bắt đầu vì không phải nơi thay thế quyết định authorization.
5. Nếu cần thay `OAuth2TokenExchangeAuthenticationProvider`, giữ nguyên các kiểm tra mặc định cần thiết (client auth, grant, token type, active state, actor rules, issuance), audit rõ mọi phần được thay. Việc chỉ nối một AuthenticationProvider **sau** provider mặc định có thể không chạy nếu provider mặc định xử lý request trước.

**Không có một setting Spring Boot chung** kiểu `app.token-exchange.allow-any-audience=true` được framework bảo đảm an toàn. Target policy là logic ứng dụng; cần triển khai và kiểm thử có chủ đích.

### 7.5. Liên kết `aud` đích với token được phát

Token Exchange có thể đổi audience nguồn sang audience đích theo policy. Khi phát JWT, phải đảm bảo `aud` ở **JWT mới** được đặt từ **kết quả policy đã xác minh**, không từ chuỗi `audience`/`resource` mà caller tự chọn. Resource Server nhận JWT mới phải kiểm tra audience cụ thể.

Với Spring Authorization Server, có thể dùng `OAuth2TokenCustomizer<JwtEncodingContext>` để tùy biến claims trong JWT access token, nhưng **customizer không phải nơi duy nhất quyết định cấp phép exchange**. Tầng policy phải xác thực target trước; sau đó customizer mới đưa audience/scope/actor đã duyệt vào token.

Ví dụ **pseudocode** về thứ tự công việc:

```text
validateClientAuthentication()
validateGrantTypeIsRegistered(TOKEN_EXCHANGE)
subject = verifySubjectTokenAndLiveStatus()
actor   = verifyActorTokenIfPresent()
decision = exchangePolicy.authorize(
    authenticatedClient, subject, actor,
    requestedAudience, requestedResource, requestedScopes)
# Nếu thất bại: OAuth2 error và KHÔNG gọi token generator.
accessToken = tokenGenerator.issue(
    sub=decision.subject,
    aud=decision.target,
    scopes=decision.scopes,
    actor=decision.actor,
    expiresAt=decision.expiry)
saveAuthorizationAndAudit(accessToken, subject, policyDecision)
respond(accessToken)
```

## 8. Không nhầm “đã active” với “được phép exchange”

Có thể chia quy trình thành hai tầng rõ ràng:

### Tầng A — **Validation** (token có đúng và còn dùng được không?)

- Đúng kiểu token, nguồn tin cậy, thuật toán và chữ ký hoặc lookup.
- Chưa hết hạn, chưa revoked/invalidated.
- Các claim `iss`, `aud`/context, `sub`, `jti` và metadata được kiểm tra theo loại token.
- Token tồn tại trong nguồn authorization hoặc introspection cần thiết.
- Không vi phạm sender binding (DPoP/mTLS) hoặc one-time semantics nếu áp dụng.
- Actor token cũng phải được validate riêng nếu xuất hiện.

### Tầng B — **Authorization policy** (đổi được để làm gì?)

- Exchanging client có đăng ký Token Exchange và được xác thực đúng phương thức.
- Client được phép đại diện **subject đó**, trong tenant đó, với loại nghiệp vụ đó.
- Resource/audience đích đã được khai báo tin cậy.
- Scope/role của output không vượt policy; khi chuyển ngữ cảnh có scope mapping minh bạch.
- Actor được phép hành động thay subject; lưu `act` khi cần audit.
- TTL và khả năng revocation propagation đáp ứng mục tiêu an toàn.
- Kết quả được lưu đúng trạng thái để có thể audit/thu hồi.

Một **subject token active** của user có quyền `orders.read`, nhưng client `orders-service` xin token `aud=payroll-api` với `salary.write`, phải bị **từ chối**. Đây không phải lỗi signature hay hết hạn; là **policy violation**.

## 9. Token ngoại lai, cross-tenant và sender-constrained tokens

### 9.1. Khi subject token do AS khác phát

Một request có `subject_token=EXTERNAL_JWT` không tự được Spring Authorization Server xử lý như token do chính nó phát. Với kho `OAuth2AuthorizationService` thông thường, JWT ngoài hệ thống sẽ **không có bản ghi authorization tương ứng**.

Nếu cần federation/token translation, phải thiết kế riêng:

1. Trust registry gắn `issuer → JWKS/introspection URL → allowed audiences/clients/tenants`.
2. Chỉ chấp nhận issuer đã đăng ký, chống SSRF khi tải metadata và public JWKS, giới hạn redirects/DNS/egress.
3. Xác minh chữ ký và token type đúng profile; kiểm tra user/account mapping có kiểm soát.
4. Xác minh trạng thái/revocation bằng cơ chế thực tế của issuer đó (nếu đòi hỏi); xác định failure mode khi issuer mất kết nối.
5. Xác định mapping subject, tenant, actor, scopes, audience và TTL theo **policy quản trị**, không tự lấy claims từ bên ngoài làm quyền nội bộ.
6. Lưu provenance/audit để phân biệt token do AS nội bộ cấp với token chuyển đổi từ nguồn ngoài.

Một `JwtDecoder` giải mã thành công token ngoại lai **không** thay các quyết định policy này.

### 9.2. Cross-tenant

- Không ghép hai user có cùng `sub` ở hai issuer/tenant thành một danh tính nội bộ nếu không có mapping xác thực.
- Khóa subject nên gắn `issuer + sub + tenant` trong identity mapping.
- Exchanging client có quyền với `tenant-a` không được đổi token của `tenant-b` sang audience của `tenant-a`.
- Cache authorization, policy và introspection phải phân vùng theo issuer/client/tenant; không cache kết quả “active” theo `jti` đơn lẻ nếu jti không duy nhất toàn cục.
- Không log/email/token nguyên văn để truy tìm lỗi tenant; dùng correlation ID và audit có quyền.

### 9.3. DPoP hoặc mTLS-bound subject token

Một subject token sender-constrained có `cnf`/binding key hoặc certificate phải được xử lý theo **proof-of-possession** tương ứng. Không chỉ kiểm tra chữ ký bearer JWT rồi đổi thành token đích không ràng buộc để vô tình **loại bỏ bảo vệ sender**.

Các lựa chọn an toàn tùy profile:

- Bắt buộc client cung cấp proof hợp lệ cho subject token (nếu protocol và token source yêu cầu).
- Chỉ cho exchange nếu policy cho phép và token đích cũng được sender-constrain theo target/actor mới.
- Từ chối chuyển đổi từ sender-bound token sang bearer token rộng hơn khi không có use case được phê duyệt.
- Kiểm tra khả năng hỗ trợ DPoP/mTLS trong **phiên bản Spring và luồng extension thực tế**; đừng giả định mọi biến thể ràng buộc token đã được xử lý tự động.

## 10. Error handling: lỗi giao thức khác lỗi policy

RFC 8693 định nghĩa lỗi OAuth2 token endpoint và bổ sung `invalid_target`. Cần phân biệt **quy tắc RFC** với **mã lỗi một framework/version đang trả**.

| Tình huống | Ý nghĩa chuẩn | Kết quả mong muốn |
|---|---|---|
| Thiếu `subject_token` hoặc `subject_token_type` | Yêu cầu sai cấu trúc | Trả `invalid_request`; không tiết lộ token |
| Subject/actor token không hợp lệ hoặc không được policy chấp nhận | Theo RFC 8693 §2.2.2, AS **MUST** tạo error response với `invalid_request`; mã khác có thể xuất hiện theo quy định/profile | **Fail closed**; test chính xác behavior của framework/profile |
| Target `audience/resource` không được hỗ trợ | Không thể hoặc không muốn cấp cho target | `invalid_target` là mã **SHOULD** theo RFC 8693 |
| Client authentication không thành công | Không chứng minh được danh tính exchanging client | `invalid_client` theo OAuth2 |
| Client không đăng ký Token Exchange grant | Grant không được phép với client | `unauthorized_client` |
| Scope yêu cầu không hợp lệ | Yêu cầu quá scope/quyền | `invalid_scope` hoặc lỗi profile phù hợp, không cấp quyền vượt policy |
| Token không tìm thấy/expired/revoked trong Spring provider | Không còn authorization hợp lệ | Một số phiên bản Spring trả `invalid_grant`; **không đồng nhất mã này với quy tắc tổng quát của RFC 8693** |
| Policy hoặc dependency bên ngoài lỗi | Không thể xác minh đủ điều kiện an toàn | Fail closed, lỗi hợp lệ/ít thông tin, alert nội bộ |

**Ví dụ response lỗi**:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_target"
}
```

Đừng trả thông điệp như “token user-123 của tenant-b tồn tại nhưng đã bị khóa lúc 10:30” về caller. Dùng error description ngắn, không tiết lộ sự tồn tại/danh tính user hoặc nội dung token; thông tin điều tra chi tiết thuộc audit nội bộ.

## 11. Các tình huống đặc biệt cần thiết kế rõ

### 11.1. Exchange cùng một subject token nhiều lần

RFC 8693 không mặc định coi subject token là single-use. Nếu client gửi cùng một subject token để xin nhiều token đích, AS có thể cho phép theo policy nhưng cần:

- rate limiting, quota và giới hạn token fan-out;
- audit theo subject/client/actor/target;
- TTL hẹp cho output;
- kiểm tra revocation/consent theo yêu cầu;
- không cho cùng source token sinh vô hạn token cho những target mới không được duyệt.

Nếu nghiệp vụ muốn one-time exchange, phải có **tiêu thụ token nguyên tử** và xử lý replay riêng; không suy từ `Token Exchange` rằng chức năng này có sẵn.

### 11.2. Token tiếp tục được trao đổi nhiều tầng

Ví dụ `S0 → T1 → T2`. Mỗi tầng có thể thêm actor, thay audience và dịch nghĩa scope. Cần giới hạn:

- chuỗi delegation/impersonation tối đa và target chuyển tiếp;
- các actor đã được ủy quyền ở từng tầng;
- không được tạo “scope inflation” qua mapping nhiều chặng;
- giới hạn TTL so với nguồn và chính sách absolute lifetime;
- thông tin provenance/actor chain để audit;
- khả năng revoke downstream tokens khi source bị thu hồi nếu yêu cầu.

Không tự động tin `T1` là source đủ quyền cho mọi target chỉ vì nó được AS nội bộ ký.

### 11.3. User, consent hoặc tenant thay đổi giữa lúc exchange

Nếu user bị disable hoặc tenant suspended sau khi token gốc được phát, `isActive()` chỉ có thể phản ánh trạng thái token được lưu. Policy phải xác định việc kiểm tra live identity/consent tại exchange. Nếu revoke xảy ra đồng thời, cần trạng thái/transaction version, thứ tự commit và kiểm thử race.

### 11.4. Token mới trả về nhưng Resource Server từ chối

Nếu token output có `aud` không đúng, scope khác chính sách hoặc ký bằng khóa không công bố, lỗi **không nhất thiết ở subject token**. Cần kiểm tra:

- metadata issuer và JWKS của AS cấp token mới;
- token claims thực tế sau generator/customizer;
- yêu cầu `audience/resource` đã qua policy và được mapping đúng;
- Resource Server xác minh `iss/aud/exp/signature/scope`;
- token type, delegation claim `act` và chính sách API đích.

Không sửa Resource Server thành “bỏ kiểm audience” để token exchange chạy được.

## 12. Kiểm thử: cả trạng thái token và chính sách đổi token

Integration test nên tạo **client và subject token thử nghiệm** trong kho AS, gọi thật `/oauth2/token`, rồi xác minh token đầu ra bằng Resource Server test. Không dùng production tokens. Với JWT ký, cần test key và metadata issuer đúng; với opaque token cần stub/store đáp ứng hợp đồng.

| STT | Ca kiểm thử | Input/thay đổi | Kỳ vọng |
|---|---|---|---|
| 1 | Happy path | Client hợp lệ, subject active, target và scope đúng | Cấp token mới, `aud` đúng target, `sub` đúng subject theo policy |
| 2 | Client không cho grant | RegisteredClient thiếu `TOKEN_EXCHANGE` | Từ chối `unauthorized_client` |
| 3 | Sai client secret | Token request không xác thực được client | Từ chối `invalid_client` |
| 4 | Thiếu subject | Không có `subject_token` hoặc type | `invalid_request` |
| 5 | Subject unknown | Token không tồn tại trong store đã tin cậy | Không phát output |
| 6 | Subject expired | `exp` đã qua | Không phát output |
| 7 | Subject revoked | Token metadata invalidated/revoked | Không phát output |
| 8 | Subject not-yet-valid | `nbf` tương lai vượt skew | Không phát output |
| 9 | Subject type sai | Gửi ID Token/refresh token dưới access_token type | Bị từ chối, không tự ép kiểu |
| 10 | JWT signature sai | Thay payload/kid/alg | Không phát output |
| 11 | JWT issuer ngoài chưa trusted | JWT ký đúng nhưng issuer không trong allowlist | Không phát output |
| 12 | Actor token sai | Actor expired/revoked hoặc type sai | Không phát output |
| 13 | Actor không có quyền | Active actor nhưng không được ủy quyền bởi subject/policy | Không phát output |
| 14 | Không có actor nhưng policy bắt buộc | Bỏ `actor_token` | Không phát output |
| 15 | Target chưa cho phép | `audience=payroll-api` | `invalid_target`/lỗi chính sách phù hợp |
| 16 | Nhiều audience quá rộng | Gửi `audience` cho hai API không nằm trong policy | Từ chối thay vì cấp multi-audience rộng |
| 17 | Scope escalation | Source `reports.read` nhưng xin `reports.write` | Không cấp scope cao hơn |
| 18 | Client được scope nhưng subject không được | RegisteredClient có `reports.write`, subject thiếu | Không cấp quyền chỉ vì scope đăng ký |
| 19 | Scope translation sai | Source/target scope có tên khác, không có mapping | Không tự nâng/đổi quyền |
| 20 | Cross-tenant | User tenant B, target tenant A | Không phát output |
| 21 | Subject đổi trạng thái | Revoke/logout giữa lookup và issuance | Không cấp sau revoke theo policy; kiểm thử concurrency |
| 22 | Output token claims | Kiểm tra JWT output | `iss/aud/sub/scope/exp/act` đúng policy |
| 23 | Input vẫn active | Exchange thành công một lần | Subject không tự bị vô hiệu (trừ policy riêng) |
| 24 | Output revoke propagation | Sau exchange, revoke subject | Output bị xử lý theo thiết kế (không giả định auto-revoke) |
| 25 | Sender-constrained input | DPoP/mTLS-bound token thiếu proof phù hợp | Không cho token bị “rửa” thành bearer rộng hơn |
| 26 | Opaque subject | Lookup/introspection với token còn active | Đánh giá policy đúng, không parse JWT giả |
| 27 | Foreign JWT | Trust registry/validator mở theo profile được cho phép | Chỉ chấp nhận issuer/client/tenant/target đã duyệt |
| 28 | Multi-pod | AS node A và B đọc cùng authorization | Policy và revocation state nhất quán |
| 29 | Load/abuse | Gửi nhiều exchange requests cùng subject | Rate limit/alert/quota, không làm lộ token |
| 30 | Error leakage | Token sai/tenant sai/target sai | Response không rò token/user/secret trong body/log |

### 12.1. Ví dụ kiểm thử policy thuần Java

Mẫu unit test sau minh họa **chỉ** chính sách scope, target, client và tenant ở mục 5.3:

```java
@Test
void deniesScopeEscalationEvenIfClientRegisteredForIt() {
    VerifiedExchangeContext ctx = new VerifiedExchangeContext(
            "orders-service",
            "user-123",
            "tenant-a",
            true,
            true,
            Set.of("reports.read"),  // Subject chỉ có quyền đọc.
            Set.of("reports.write"), // Client muốn quyền ghi.
            Set.of("reports-api"));

    TargetPolicy policy = new TargetPolicy(
            "reports-api",
            "tenant-a",
            Set.of("orders-service"),
            Set.of("reports.read", "reports.write"));

    assertThrows(SecurityException.class, () ->
            evaluate(ctx, policy,
                    Set.of("reports.read", "reports.write")));
}
```

Thêm imports JUnit 5 và đặt helper/records cùng test class hoặc package phù hợp. **Test này chưa kiểm tra chữ ký JWT, client authentication, authorization service hoặc token endpoint**; cần thêm integration tests cho tất cả trường hợp đó. Một assertion `assertThrows` ở helper không đủ để kết luận hệ thống an toàn.

### 12.2. Kiểm tra output bằng test client

Sau khi gọi token endpoint trong môi trường test, kiểm tra:

1. HTTP status và `issued_token_type`.
2. `scope` không vượt policy.
3. JWT output được xác minh chữ ký trước khi đọc claims; `aud` chỉ gồm target hợp lệ.
4. `sub` không bị thay sang service khi đang yêu cầu delegation thay người dùng, trừ policy impersonation khác có chủ đích.
5. Claim `act` được phát và kiểm tra đúng khi profile yêu cầu delegation.
6. `exp`/TTL không vô tình kéo dài quyền quá mức.
7. Resource Server đích chấp nhận token, một Resource Server **không phải target** phải từ chối token cùng ký nhưng sai audience.

Dùng test user/subject tokens giả; không chụp giá trị raw token hoặc `Authorization` header vào snapshot/log.

## 13. Troubleshooting và runbook

| Dấu hiệu | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| `unauthorized_client` khi exchange | `RegisteredClient` chưa có `TOKEN_EXCHANGE` | Kiểm tra client provisioning, grant type, quyền tối thiểu |
| `invalid_client` | Sai xác thực confidential client | Kiểm tra client secret hash, method, `private_key_jwt`/mTLS, không log credential |
| Token signed JWT “đúng” nhưng AS từ chối | Chỉ có chữ ký, thiếu record authorization hoặc sai token type/policy | Phân biệt local token lookup và external federation |
| Subject expired/revoked | `isActive()==false` hoặc live status fail | Từ chối, yêu cầu token hợp lệ mới qua grant được hỗ trợ |
| Actor không được chấp nhận | `actor_token` sai, `may_act` không khớp hoặc policy thiếu | Kiểm tra delegation relationship, issuer, claims và token state |
| `invalid_target` | Target không trong allowlist hoặc yêu cầu multi-audience quá rộng | Kiểm tra target policy và resource/audience semantics |
| Token output có scope quá rộng | Chỉ dùng `RegisteredClient.getScopes()`, không giới hạn theo subject/target | Thực thi policy trước issuance và kiểm tra claim sau generator |
| API đích trả 401 | `iss/aud/signature/exp` output sai | So sánh token claims, JWKS, issuer, Resource Server config |
| API đích trả 403 | Scope hoặc authorization nghiệp vụ không đủ | Kiểm tra quyền target, actor/subject, mapping và policy API |
| Revoke subject nhưng output vẫn gọi API được | Không có linkage/revoke propagation; JWT offline | TTL ngắn, token lineage/revocation strategy, kiểm tra API status |
| Client A đổi token tenant B | Policy thiếu binding hoặc cache lẫn tenant | Phân vùng cache, kiểm tra principal+issuer+tenant, rà soát audit |
| Sau scale-out token exchange lúc được lúc không | Token store/revocation cache không chung giữa AS pods | Shared persistence và consistency, kiểm tra session/authorization |
| External issuer JWKS fetch lỗi | DNS/TLS/network/trust config | Fail closed, không nới tin cậy sang URL không kiểm soát |
| Mất actor trên downstream | Token generator/customizer không bảo toàn `act` | Chính sách delegation và claim mapping được test end-to-end |

### 13.1. Quan sát vận hành mà không làm lộ token

Các metrics có thể gồm:

- `token_exchange_requests_total{outcome,client_class,target_class}`;
- `token_exchange_rejected_total{reason}`, phân loại `invalid_subject`/`invalid_actor`/`invalid_target`/`scope_policy`/`tenant_policy`;
- `token_exchange_latency_seconds` và `token_exchange_subject_lookup_latency_seconds`;
- `token_exchange_external_introspection_failures_total` khi có federation;
- `token_exchange_revocation_conflict_total` và `token_exchange_output_revoked_total` khi theo dõi lineage.

Không dùng raw `subject_token`, `actor_token`, client secret, user ID/email, `jti` nguyên văn hoặc Authorization header làm **metric labels**. Log chỉ nên có correlation ID, ID client theo chính sách, loại target, mã từ chối, timestamp và audit được bảo vệ; kiểm soát log retention và quyền truy cập.

### 13.2. Runbook khi tỷ lệ exchange bị từ chối tăng

1. Kiểm tra thời điểm triển khai policy, client registration hoặc token-format đổi; so sánh với phiên bản Spring đang chạy.
2. Phân nhóm lỗi: xác thực client, subject unknown/expired/revoked, actor invalid, target/scope/tenant policy hay dependency.
3. Xác nhận kho `OAuth2AuthorizationService` có bản ghi cho token gốc và không stale giữa các instance. Nếu token ngoại lai, kiểm tra trust registry và introspection/JWKS.
4. Đối chiếu issuer, audience, scope, client identity và delegated actor qua **metadata đã che**; không copy JWT raw vào ticket.
5. Nếu chính sách mới là nguyên nhân, sửa đúng mapping/quy trình provisioning có phê duyệt; **không** bật “allow any audience” hoặc bỏ `isActive()`.
6. Nếu có dấu hiệu replay/abuse, rate limit, thu hồi token liên quan, đánh giá output token đã phát và audit.
7. Tái hiện trên staging bằng bộ token giả, xác minh cả request hợp lệ và negative cases rồi mới rollout.

## 14. Checklist production và câu hỏi tự kiểm tra

- [ ] Chỉ client đã được xác thực và có `TOKEN_EXCHANGE` trong RegisteredClient mới được vào luồng.
- [ ] Phân biệt rõ identity của exchanging client, subject và actor; không nhầm client secret hợp lệ với quyền đại diện mọi người dùng.
- [ ] `subject_token` và `subject_token_type` có mặt, kiểu nằm trong allowlist; ID Token/refresh token không bị coi là access token.
- [ ] Subject và actor token (nếu có) được kiểm tra trust issuer/key, type, thời gian, trạng thái, revocation và sender binding.
- [ ] Với token do AS phát, `OAuth2AuthorizationService` trả authorization đáng tin và `token.isActive()`; với token ngoại lai có trust registry/validator riêng.
- [ ] Quy tắc client→subject/tenant→target/audience→scope được định nghĩa tường minh và **deny by default**.
- [ ] `audience/resource` được xét trước khi phát token, có giới hạn số đích và chống token fan-out.
- [ ] Không cấp scope ngoài quyền đã được source/target/client policy cho phép; mapping scope khác tên có review.
- [ ] `act`/`may_act` và chuỗi delegation có quy tắc rõ, được kiểm tra và audit.
- [ ] Token output có `iss`, `aud`, `sub`, `scope`, `exp`, `act` đúng policy; Resource Server kiểm tra lại authorization.
- [ ] Có chiến lược khi input bị revoke sau exchange: TTL ngắn, lineage, introspection/propagation tùy mức rủi ro.
- [ ] Tránh bỏ sender-constraining khi chuyển đổi token hoặc chuyển sang bearer target rộng hơn.
- [ ] Không log raw token, không dùng URL/header do token chưa xác minh điều khiển JWKS/target lookup.
- [ ] Multi-node persistence/cache nhất quán và có test race với revoke/logout.
- [ ] Có integration test về lỗi chủ thể, actor, wrong issuer, cross-tenant, scope escalation, target sai và JWT output.
- [ ] Error response không tiết lộ dữ liệu nhạy cảm, hoạt động observability có audit và rate limit.

**Câu hỏi tự kiểm tra**

1. Một JWT có chữ ký hợp lệ nhưng `OAuth2AuthorizationService` báo token đã bị thu hồi có được dùng làm subject token không?
2. Vì sao xác thực client thành công khác với việc cho phép client hành động thay mặt subject?
3. `subject_token_type=access_token` và `subject_token_type=jwt` khác nhau ở đâu?
4. Vì sao token gốc có `aud=orders-api` vẫn có thể được phép đổi sang `aud=reports-api`, nhưng điều đó cần policy bổ sung?
5. Khi cả RegisteredClient và target cho phép `reports.write`, nhưng subject chỉ có `reports.read`, AS nên xử lý request xin `reports.write` ra sao?
6. `act` và `may_act` biểu diễn khía cạnh nào của delegation?
7. Nếu `subject_token` bị thu hồi sau khi exchange thành công, token mới có tự thu hồi theo RFC 8693 không?
8. Spring Authorization Server provider mặc định có cho phép tự động federation mọi JWT từ issuer bên ngoài không?
9. Tại sao policy cần chạy **trước** token generator, không chỉ chèn audience vào JWT ở customizer?
10. Bạn sẽ thiết kế test nào để ngăn cross-tenant exchange và token laundering của DPoP-bound token?

## Tài liệu tham khảo

- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): request/response, validation subject/actor, impersonation/delegation, audience/resource/scope, token lifecycle và errors.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): token endpoint, client authentication, scope và error response.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): token misuse, hạn chế privilege escalation và security controls.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra trạng thái token qua introspection.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token, ràng buộc vòng đời token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claims và định dạng JWT access token.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constraining bằng proof key.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): certificate binding.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OAuth2TokenEndpointConfigurer`, `OAuth2TokenExchangeAuthenticationConverter` và provider mặc định.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `OAuth2Authorization` và `OAuth2AuthorizationService`.
- [Spring Authorization Server — OAuth2TokenExchangeAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenExchangeAuthenticationProvider.html): provider của Token Exchange grant.
- [Spring Authorization Server — OAuth2TokenExchangeAuthenticationToken API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenExchangeAuthenticationToken.html): tham số subject/actor, resource/audience/scope.
- [Spring Security — OAuth2 Client Authorization Grant Support](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): Token Exchange OAuth2 Client provider, cách chọn subject/actor token khi gọi grant.
