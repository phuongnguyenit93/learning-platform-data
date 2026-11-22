# Resource Server trả lỗi để client xử lý gia hạn theo giao thức phù hợp

## 1. Mục tiêu: trả lỗi đúng để OAuth client biết bước tiếp theo

Trong hệ thống **Spring Security OAuth 2.0/OIDC Resource Server**, access token có thời hạn và có thể bị thu hồi trước thời hạn. Khi client gọi API bằng Bearer token không còn được chấp nhận, Resource Server cần trả **HTTP status và Bearer challenge đúng giao thức** để client quyết định có xin token mới, yêu cầu người dùng đăng nhập lại hay dừng thao tác.

Ví dụ một request:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6...
```

Nếu access token đã hết hạn hoặc bị thu hồi, phản hồi điển hình:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Cache-Control: no-store
```

OAuth client có thể dùng tín hiệu `invalid_token` để xem xét lấy access token mới qua **OAuth 2.0 Token Endpoint**. Nếu có refresh token còn hiệu lực, client có thể sử dụng **Refresh Token Grant**. Nếu không có refresh token, client có thể xin access token lại bằng grant phù hợp hoặc yêu cầu người dùng đăng nhập.

Điều quan trọng là **Resource Server không tự gia hạn access token**. Nó chỉ xác minh credential và trả kết quả theo giao thức. Refresh token thuộc luồng quản lý credential giữa **OAuth client và Authorization Server**; client không gửi refresh token tới API.

Bài này giải thích:

- Phân biệt **401 invalid_token**, **403 insufficient_scope**, **400 invalid_request** và lỗi dependency.
- Ý nghĩa của `WWW-Authenticate` theo RFC 6750.
- Khi nào client nên refresh token, xin token mới, đăng nhập lại hoặc không retry.
- Cách dùng refresh token rotation, xử lý `invalid_grant` và đồng bộ nhiều request.
- Cấu hình Spring Security Resource Server và OAuth2 Client.
- Retry an toàn, idempotency, tránh vòng lặp 401 và tránh lộ credential.

> **Quy tắc nền tảng:** Resource Server phải nói đúng lý do ở mức giao thức; OAuth client chịu trách nhiệm dùng grant phù hợp để có access token mới. Một lỗi 401 không có nghĩa mọi trường hợp đều có thể refresh, và một lỗi 403 không phải tín hiệu mặc định để refresh.

## 2. Phân chia trách nhiệm: Resource Server, client và Authorization Server

Ba thành phần có nhiệm vụ khác nhau:

| Thành phần | Trách nhiệm | Không nên làm |
| --- | --- | --- |
| **OAuth 2.0 Resource Server** | Nhận access token, xác minh token, kiểm tra audience/scope và trả 401/403 hoặc kết quả phù hợp. | Nhận refresh token từ caller để đổi lấy access token; tự phát hành token mới; trả raw token hoặc secret trong lỗi. |
| **OAuth 2.0 Client** | Lưu access token/refresh token theo chính sách, gọi API, xử lý Bearer challenge, refresh hoặc xin token mới, retry request khi an toàn. | Gửi refresh token tới Resource Server; retry vô hạn; đưa token vào URL/log. |
| **Authorization Server (AS)** | Phát hành access token và refresh token theo grant/consent/client policy; xác minh refresh token; rotation/revocation; trả token mới hoặc lỗi OAuth. | Tin refresh token chỉ vì client gửi; bỏ qua client authentication hoặc binding cần thiết. |

Luồng chuẩn khi access token hết hạn:

```mermaid
sequenceDiagram
    participant C as OAuth Client
    participant RS as Resource Server
    participant AS as Authorization Server
    C->>RS: API request + Bearer access token
    RS->>RS: Validate token
    RS-->>C: 401 + WWW-Authenticate: Bearer error="invalid_token"
    Note over C: Client xác định token có thể cần được thay mới
    C->>AS: POST /token, grant_type=refresh_token
    AS->>AS: Validate refresh token + client + policy
    alt Refresh token còn hợp lệ
        AS-->>C: 200 + new access token (có thể kèm refresh token mới)
        Note over C: Lưu token mới an toàn; thay refresh token cũ nếu rotation
        C->>RS: Retry API request với access token mới
        RS->>RS: Validate token mới
        RS-->>C: 2xx nếu scope/resource/policy cho phép
    else Refresh token không còn hợp lệ
        AS-->>C: OAuth error, thường invalid_grant
        Note over C: Xóa credential cũ và yêu cầu authorization lại
    end
```

Resource Server **không cần biết refresh token nằm ở đâu**. Nó chỉ nhận access token và quyết định có chấp nhận hay không.

## 3. Bearer challenge theo RFC 6750

**RFC 6750 — OAuth 2.0 Bearer Token Usage** quy định cách gửi Bearer token và cách Resource Server thông báo lỗi bằng `WWW-Authenticate`. Những error code thường gặp:

| Bearer error | HTTP status điển hình | Ý nghĩa |
| --- | --- | --- |
| `invalid_request` | **400 Bad Request** | Request sử dụng token sai cú pháp hoặc gửi credential theo cách không hợp lệ/không nhất quán. |
| `invalid_token` | **401 Unauthorized** | Access token bị từ chối: có thể hết hạn, bị thu hồi, malformed hoặc không hợp lệ theo resource contract. |
| `insufficient_scope` | **403 Forbidden** | Token đã được chấp nhận nhưng không có scope cần thiết cho resource/action. |

### 3.1. Không có access token

Ví dụ client chưa gửi credential:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
```

Phản hồi:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
```

Theo RFC 6750, khi request **không chứa thông tin xác thực**, Resource Server thường trả Bearer challenge mà **không cần** `error="invalid_token"`. Client hiểu endpoint yêu cầu Bearer credential và cần thực hiện flow lấy access token phù hợp.

### 3.2. Có token nhưng token không hợp lệ

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
```

`invalid_token` bao gồm nhiều tình huống:

- Token đã hết hạn (`exp`).
- Token đã bị thu hồi hoặc không còn active.
- JWT có chữ ký sai, issuer/audience sai hoặc claim validation thất bại.
- Opaque token introspection trả `active=false`.
- Token không được chấp nhận theo token profile/resource contract.

Client không nhất thiết biết nguyên nhân cụ thể. Nó có thể thử lấy token mới nếu grant cho phép, nhưng phải dừng nếu lỗi lặp lại hoặc lỗi chỉ ra cấu hình sai.

### 3.3. Token hợp lệ nhưng thiếu quyền

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
```

Ví dụ token có `SCOPE_orders:read` nhưng gọi:

```http
POST /api/orders
```

trong khi endpoint yêu cầu `SCOPE_orders:write`.

Client không nên tự động refresh **cùng một authorization grant** với hy vọng token mới sẽ có thêm scope. Nếu cần scope mới, client phải có cơ chế xin quyền phù hợp, có thể yêu cầu consent hoặc một authorization request khác theo policy của AS. Refresh token grant thường bị giới hạn ở scope ban đầu đã được cấp; nó không phải cách nâng quyền tùy ý.

### 3.4. Request Bearer sai định dạng

Ví dụ:

```http
Authorization: Bearer
```

hoặc request gửi nhiều phương thức truyền token không nhất quán. Khi đó Resource Server có thể trả:

```http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request"
```

Client cần sửa cách gửi credential. Refresh token không sửa được lỗi header malformed.

### 3.5. Bảng quyết định nhanh

| Response | Hành động client phù hợp |
| --- | --- |
| 401, không có `error` và request chưa gửi token | Lấy access token theo flow đăng nhập/client đã cấu hình, rồi gửi request. |
| 401, `invalid_token` | Có thể thử refresh/reacquire **một lần** nếu grant còn hợp lệ; nếu không, yêu cầu authorization lại hoặc báo lỗi. |
| 403, `insufficient_scope` | Kiểm tra quyền/scope và policy; không refresh lặp vô hạn. |
| 400, `invalid_request` | Sửa header/body/transport theo giao thức; không refresh chỉ vì lỗi này. |
| 429 | Tôn trọng `Retry-After` nếu có và backoff; không tự refresh token. |
| 5xx/503 | Xử lý lỗi dịch vụ/dependency theo retry policy; không mặc định access token invalid. |
| 404 | Kiểm tra endpoint/resource và quyền che giấu tài nguyên; không refresh theo status này. |

## 4. WWW-Authenticate là tín hiệu giao thức, không phải debug log

Client nên đọc **HTTP status và Bearer challenge**. `error_description` là tùy chọn; client không nên phụ thuộc vào một câu tiếng Anh cụ thể để quyết định logic.

Ví dụ:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token", error_description="The access token is invalid"
```

Mô tả lỗi nên là chuỗi an toàn, ổn định. Không trả:

```http
WWW-Authenticate: Bearer error="invalid_token", error_description="JWT kid=prod-key-7 not found at https://internal-idp.svc/keys; token=eyJ..."
```

Không nên để `error_description` chứa:

- Raw access token hoặc refresh token.
- Client secret, Basic header, private key hoặc certificate private material.
- JWKS/introspection URI nội bộ, hostname/pod/namespace.
- Stack trace, exception message chưa sanitize.
- Payload claims có PII hoặc tenant metadata không cần thiết.

Client nên xử lý dựa trên `error="invalid_token"` thay vì parse chuỗi mô tả để tìm từ “expired”, “revoked” hay “signature”.

### 4.1. Realm và error_uri

`realm` có thể là tên resource ổn định như `orders-api`. Nó không bắt buộc là issuer URL hoặc introspection endpoint. Nếu dùng `error_uri`, chỉ trỏ tới tài liệu API công khai:

```http
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token", error_uri="https://docs.example.test/auth-errors"
```

Không đưa access token/refresh token vào URL; query strings có thể bị lưu trong proxy logs, browser history, referrer và analytics.

### 4.2. Missing token và invalid token khác nhau

Client cần phân biệt:

```text
Không gửi Authorization header
  → Resource Server yêu cầu Bearer authentication
  → Client lấy access token theo grant đã cấu hình.

Có gửi Bearer token nhưng token bị từ chối
  → Resource Server trả invalid_token
  → Client xem xét thay token; nếu không thể, authorization lại hoặc báo lỗi.
```

Đừng biến mọi 401 thành “refresh ngay”. Một request không có token có thể chỉ là lỗi cấu hình client hoặc endpoint public/private bị gọi nhầm.

## 5. Refresh Token Grant nằm ở Token Endpoint

**Refresh token** là credential dùng với Authorization Server để lấy access token mới. Theo OAuth 2.0, client gửi token request tới **Token Endpoint**, không gửi refresh token tới Resource Server.

Ví dụ form request:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication-if-required>

grant_type=refresh_token&refresh_token=<refresh-token-value>
```

Với public client, cách xác thực client có thể dùng `client_id` theo yêu cầu AS và cơ chế bảo vệ refresh token phù hợp. Với confidential client, client authentication được thực hiện theo đăng ký (ví dụ client secret, mTLS hoặc private_key_jwt). Không hardcode secret trong mobile app hoặc SPA.

Phản hồi thành công ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<new-access-token>",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "<new-refresh-token>",
  "scope": "orders:read"
}
```

AS có thể **không trả refresh_token mới** trong mọi cấu hình. Nếu refresh token rotation được bật, phản hồi thường chứa refresh token mới và client phải thay thế token cũ theo policy.

### 5.1. Refresh token không phải access token

| Credential | Dùng ở đâu? | Có gửi đến Resource Server? |
| --- | --- | --- |
| Access token | `Authorization: Bearer` khi gọi API. | **Có**. |
| Refresh token | Token Endpoint với `grant_type=refresh_token`. | **Không**. |
| ID token | OIDC client dùng để biết kết quả xác thực user theo OIDC contract. | Không dùng thay access token cho API. |
| Client assertion | Client xác thực với AS trong token request. | Không dùng làm Bearer access token của API. |

Resource Server không nên chấp nhận refresh token ở `Authorization: Bearer`. Refresh token có thể có quyền cấp lại access token và vì thế thường có giá trị cao hơn, phạm vi sử dụng khác.

### 5.2. Client phải thay token như thế nào?

Sau refresh thành công:

1. Cập nhật access token mới.
2. Cập nhật `expires_at`/`expires_in` và scope theo response.
3. Nếu AS trả refresh token mới, **ghi token mới an toàn và vô hiệu hóa bản cũ trong local state** theo rotation policy.
4. Chỉ sau khi lưu thành công mới tiếp tục dùng credential mới.
5. Retry request API nếu thao tác có thể được phát lại an toàn.

Không giữ refresh token mới chỉ trong RAM trong khi nhiều worker khác vẫn dùng refresh token cũ. Với rotation, tình trạng đó có thể khiến AS phát hiện reuse và thu hồi cả token family.

## 6. Khi nào client nên refresh?

Có hai cách phổ biến.

### 6.1. Refresh chủ động trước khi access token hết hạn

Client lưu thời điểm hết hạn (ví dụ `expires_in` từ token response) và refresh trước một khoảng đệm:

```text
refreshAt = expiresAt - safetyWindow
```

Ví dụ token có thời hạn 60 phút, client có thể bắt đầu refresh trước vài phút tùy latency, clock skew và UX. Giá trị thực tế cần dựa vào policy, không chọn cố định cho mọi ứng dụng.

Ưu điểm:

- Giảm số request API bị 401 do hết hạn.
- Có thể refresh ở background khi app đang hoạt động.
- Trải nghiệm người dùng mượt hơn.

Nhược điểm:

- Tốn token endpoint traffic nếu refresh quá sớm.
- Client phải quản lý timer/clock/concurrency.
- Token có thể bị thu hồi trước thời hạn; proactive refresh không thay thế xử lý 401.

### 6.2. Refresh theo phản hồi invalid_token

Client gọi API, nhận 401 `invalid_token`, rồi thử refresh nếu có refresh token. Cách này phản ứng trực tiếp với trạng thái Resource Server nhìn thấy, nhưng tăng latency cho request đầu tiên sau khi token bị từ chối.

Client cần tránh:

- Refresh mọi HTTP 401 kể cả khi không gửi token.
- Refresh khi lỗi thực chất là sai audience/issuer/client configuration.
- Retry request vô hạn nếu access token mới vẫn bị từ chối.
- Refresh khi API trả 403 `insufficient_scope`.

### 6.3. Kết hợp cả hai

Một client production thường:

1. Dựa vào token response để refresh chủ động trước hạn.
2. Vẫn xử lý 401 `invalid_token` vì token có thể bị thu hồi hoặc policy thay đổi.
3. Chỉ refresh/retry tối đa một lần cho một request flow.
4. Nếu token mới vẫn bị từ chối, dừng và báo lỗi/cần authorization lại.

**Không dựa duy nhất vào việc decode `exp` ở client để kết luận token hợp lệ.** Client có thể đọc thời gian để lập lịch, nhưng Resource Server/AS mới là bên xác minh credential theo trust policy.

## 7. Client không có refresh token thì sao?

Không phải mọi OAuth grant đều cấp refresh token.

| Client / grant | Cách lấy access token mới khi hết hạn |
| --- | --- |
| Authorization Code (user delegated) | Dùng refresh token nếu AS cấp và còn hợp lệ; nếu không, chạy lại authorization flow khi cần. |
| Authorization Code + PKCE cho public client | Có thể được cấp refresh token theo policy; phải bảo vệ refresh token và tuân thủ rotation/sender constraint. |
| Client Credentials (machine-to-machine) | Thường xin access token mới bằng client credentials grant; không giả định có refresh token. |
| Device Authorization | Có thể dùng refresh token nếu AS cấp; nếu hết/revoke, cần authorization lại trên thiết bị. |
| SPA/BFF | Phụ thuộc kiến trúc: BFF có thể giữ refresh token server-side; SPA public client phải áp dụng chính sách bảo vệ phù hợp. |

### 7.1. Client Credentials: xin access token mới

Ví dụ:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <workload-client-auth>

grant_type=client_credentials&scope=reports:read
```

Client lấy access token mới theo registration/credentials của workload. Không cần gửi refresh token nếu AS không cấp và grant không dùng refresh token.

### 7.2. Authorization Code: refresh hoặc login lại

Nếu refresh token hết hạn/bị revoke, client cần chạy lại authorization flow theo cấu hình. Với browser application, thường điều hướng user tới Authorization Server để đăng nhập/consent lại; với BFF, server quản lý phiên và redirect phù hợp.

Không yêu cầu người dùng dán refresh token vào form, ticket hoặc chat hỗ trợ.

## 8. Xử lý lỗi tại Token Endpoint

Refresh request cũng có thể thất bại. Một số lỗi OAuth thường gặp:

| Token endpoint error | Ý nghĩa | Hành động client |
| --- | --- | --- |
| `invalid_grant` | Refresh token không hợp lệ, hết hạn, bị revoke, đã dùng lại sau rotation hoặc không thuộc grant/client. | Không retry cùng refresh token vô hạn; xóa credential cũ và authorization lại khi phù hợp. |
| `invalid_client` | Client authentication sai hoặc client không được nhận diện. | Dừng, báo lỗi cấu hình/credential; không coi là user session hết hạn đơn thuần. |
| `invalid_scope` | Scope yêu cầu không hợp lệ hoặc vượt phạm vi được phép. | Sửa yêu cầu theo grant/consent; không retry cùng request vô hạn. |
| `unauthorized_client` | Client không được phép dùng grant. | Kiểm tra client registration/AS policy. |
| `unsupported_grant_type` | AS không hỗ trợ grant request. | Sửa cấu hình/protocol; không retry. |
| HTTP 429/5xx/timeout | Rate limit hoặc lỗi dịch vụ. | Backoff có giới hạn; giữ trạng thái token cũ theo policy nhưng không dùng token đã biết là invalid. |

Phản hồi lỗi ví dụ:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant",
  "error_description": "The refresh token is invalid"
}
```

Không đưa raw refresh token vào logs hoặc hiển thị cho người dùng. Client có thể dùng `error` machine-readable; không phụ thuộc vào `error_description`.

### 8.1. invalid_grant không đồng nghĩa luôn cần đăng nhập lại ngay

`invalid_grant` là một loại lỗi rộng. Tùy hệ thống, có thể do:

- Refresh token hết hạn.
- Refresh token đã bị thu hồi.
- Token rotation đã phát token mới nhưng client dùng lại token cũ.
- Refresh token không thuộc client/grant hiện tại.
- User/admin đã revoke grant hoặc consent.

Client nên dừng việc thử lại credential đó, xóa/đánh dấu invalid state theo policy và khởi tạo authorization flow mới nếu user action cần thiết. Nếu nghi do race condition, cần sửa cơ chế đồng bộ refresh thay vì yêu cầu user đăng nhập liên tục.

## 9. Refresh Token Rotation và đồng bộ nhiều request

Với **refresh token rotation**, AS cấp refresh token mới sau mỗi lần sử dụng thành công và làm token cũ mất hiệu lực. Điều này giúp phát hiện credential bị đánh cắp và dùng lại.

Ví dụ:

```text
Ban đầu:
  Access A1 + Refresh R1

Refresh thành công:
  Access A2 + Refresh R2
  R1 không còn được dùng

Request sau:
  Client phải dùng R2, không dùng R1
```

### 9.1. Race condition phổ biến

Giả sử ba request cùng phát hiện access token A1 hết hạn:

```mermaid
sequenceDiagram
    participant R1 as Request 1
    participant R2 as Request 2
    participant R3 as Request 3
    participant S as Shared Token Store
    participant AS as Authorization Server
    R1->>S: Đọc A1/R1
    R2->>S: Đọc A1/R1
    R3->>S: Đọc A1/R1
    R1->>AS: Refresh bằng R1
    R2->>AS: Refresh bằng R1
    R3->>AS: Refresh bằng R1
    AS-->>R1: A2/R2; R1 bị rotate
    AS-->>R2: invalid_grant (reuse/old token)
    AS-->>R3: invalid_grant hoặc phát hiện reuse
    R1->>S: Ghi A2/R2
```

Tùy AS, việc reuse token cũ có thể làm **thu hồi token family** hoặc grant. Vì thế client cần **single-flight refresh** hoặc lock theo grant/session.

### 9.2. Mô hình single-flight

```text
Request 1 ─┐
Request 2 ─┼─> Shared refresh operation (one per grant)
Request 3 ─┘          |
                     v
              POST token endpoint once
                     |
                     v
          Atomically store new token pair
                     |
                     v
           Release all waiting requests
```

Thiết kế:

1. Dùng một lock/lease theo **client registration + principal/session/grant**, không khóa toàn bộ ứng dụng nếu không cần.
2. Sau khi lấy lock, **đọc lại token store**; request khác có thể đã refresh thành công.
3. Nếu access token mới đã có, không gọi refresh lần hai.
4. Nếu vẫn cần refresh, gửi token hiện hành tới AS.
5. Lưu access token và refresh token mới **atomic**.
6. Chỉ release các request đang chờ sau khi cập nhật hoàn tất.
7. Nếu process chết giữa response và token persistence, cần xử lý rotation recovery theo khả năng của AS; không giả định refresh token cũ còn dùng được.

Với ứng dụng nhiều pods, lock trong bộ nhớ của một JVM không đủ. Cần token store/coordination phù hợp như database transaction, distributed lock hoặc một BFF/session owner duy nhất, có cân nhắc failure mode.

### 9.3. Atomic persistence

Nếu access token mới được lưu nhưng refresh token mới chưa được lưu (hoặc ngược lại), state có thể không nhất quán. Một transaction/record update nên thay cặp token cùng lúc:

```text
authorized_client:
  registration_id
  principal_or_session_id
  access_token_ciphertext
  access_token_expires_at
  refresh_token_ciphertext
  refresh_token_version
  updated_at
```

Đây là **schema khái niệm**, không phải schema mặc định của Spring. Dữ liệu token phải được mã hóa, kiểm soát quyền truy cập, retention và audit.

## 10. Retry request sau refresh: chỉ một lần và phải an toàn

Một thuật toán client đơn giản:

```text
1. Gửi request với access token hiện tại.
2. Nếu không phải 401 invalid_token:
     xử lý response bình thường.
3. Nếu 401 invalid_token:
     lấy lock và kiểm tra token store.
4. Nếu token đã được request khác refresh:
     dùng token mới.
   Nếu chưa:
     refresh hoặc reacquire theo grant.
5. Nếu refresh thất bại:
     dừng; authorization lại hoặc báo lỗi.
6. Retry request tối đa một lần với access token mới.
7. Nếu vẫn 401/403:
     dừng và báo lỗi; không tạo vòng lặp.
```

### 10.1. Không retry 403 insufficient_scope

Token hợp lệ nhưng thiếu scope thường không được giải quyết bằng refresh token grant thông thường. Nếu client muốn quyền mới, cần authorization request/consent phù hợp. Việc retry cùng token chỉ tạo tải và không thay đổi quyền.

### 10.2. Không retry mọi 401

401 có thể do:

- Không gửi token.
- Token sai audience/issuer.
- Token sai signature.
- Token đã bị revoke.
- Resource Server cấu hình sai.
- Gateway/AS dependency error bị map thành 401 theo custom handling.

Client có thể thử refresh một lần với `invalid_token`, nhưng nếu token mới vẫn bị từ chối, cần dừng. Nếu client không gửi credential, phải kiểm tra flow/token acquisition; nếu sai audience, phải sửa registration/resource target thay vì refresh liên tục.

### 10.3. HTTP method và idempotency

| Request | Có thể retry sau refresh? | Lưu ý |
| --- | --- | --- |
| GET | Thường có, nếu request body/side effects không có. | Kiểm tra API thực tế không làm side effect qua GET. |
| HEAD | Thường có. | Theo contract endpoint. |
| OPTIONS | Thường có. | CORS/preflight có thể không cần Bearer token. |
| PUT | Có thể nếu thao tác idempotent theo API contract và body phát lại được. | Xác nhận server không xử lý một phần trước 401. |
| DELETE | Có thể theo contract idempotent; vẫn phải kiểm soát side effects. | Không retry nếu không rõ request đầu đã được xử lý chưa. |
| POST | **Không tự động retry mù**. | Dùng Idempotency-Key/operation ID và bảo đảm request đầu bị từ chối trước khi tạo side effect. |
| Streaming upload | Phụ thuộc body có replay được không. | Có thể không phát lại được; cần thiết kế resumable upload hoặc xin token trước. |

### 10.4. Idempotency-Key cho POST

Ví dụ:

```http
POST /api/orders HTTP/1.1
Authorization: Bearer <new-access-token>
Idempotency-Key: 2e7f7b8c-...
Content-Type: application/json

{"productId":"P-100","quantity":1}
```

Nếu client cần retry do auth refresh, cùng một logical operation phải dùng **cùng Idempotency-Key** theo contract server. Server cần lưu kết quả idempotency và bảo đảm hai lần gửi không tạo hai đơn hàng.

Không tự thêm key rồi tuyên bố API hỗ trợ idempotency nếu server không triển khai.

## 11. Resource Server không nên điều khiển vòng đời refresh token

Một số thiết kế sai:

```java
// SAI về ranh giới credential: Resource Server nhận refresh token
// từ request API rồi gọi token endpoint thay caller.
@PostMapping("/api/orders")
public Mono<?> create(
        @RequestHeader("Authorization") String bearer,
        @RequestHeader("X-Refresh-Token") String refreshToken) {
    // ...
}
```

Không thêm:

- Header `X-Refresh-Token`.
- Query parameter `refresh_token`.
- Request body chứa refresh token để “API tự gia hạn”.
- Logic Resource Server lưu refresh token của mọi user chỉ để xử lý 401.

Điều đó trộn Resource Server với OAuth client, làm tăng rủi ro rò rỉ và khiến refresh token đi qua nhiều service không cần thiết.

**Nếu kiến trúc là Backend-for-Frontend (BFF)**, BFF có thể đóng vai OAuth client, giữ refresh token server-side và gọi Resource Server bằng access token. Nhưng BFF và Resource Server vẫn là **hai trách nhiệm logic khác nhau**; refresh token không được chuyển tiếp tới API resource.

## 12. Cấu hình Spring Security Resource Server trả Bearer challenge

Trong Servlet application, cấu hình OAuth2 Resource Server:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.http.HttpMethod;
import org.springframework.security.oauth2.server.resource.web
        .BearerTokenAccessDeniedHandler;
import org.springframework.security.oauth2.server.resource.web
        .BearerTokenAuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ResourceServerSecurityConfiguration {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        BearerTokenAuthenticationEntryPoint entryPoint =
                new BearerTokenAuthenticationEntryPoint();
        entryPoint.setRealmName("orders-api");

        BearerTokenAccessDeniedHandler deniedHandler =
                new BearerTokenAccessDeniedHandler();
        deniedHandler.setRealmName("orders-api");

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .requestMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:write")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .authenticationEntryPoint(entryPoint)
                        .accessDeniedHandler(deniedHandler)
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Các handler chuẩn:

- `BearerTokenAuthenticationEntryPoint` xử lý authentication failure và Bearer challenge.
- `BearerTokenAccessDeniedHandler` xử lý access denied trong Bearer resource-server flow.
- Spring Security thường tự thiết lập handler phù hợp khi dùng `oauth2ResourceServer`; ví dụ trên đặt realm tường minh.

Code dùng **Servlet stack** (`HttpSecurity`, `SecurityFilterChain`). Nếu dự án dùng WebFlux, phải dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và reactive handler tương ứng; không trộn API Servlet.

### 12.1. 401 khi thiếu token và invalid_token khi token sai

Với default Bearer handling, Resource Server có thể:

- Thiếu Bearer credential: trả 401 với challenge realm.
- Bearer credential không hợp lệ: trả 401 với `error="invalid_token"`.
- Token hợp lệ nhưng thiếu scope: trả 403 và challenge `insufficient_scope` khi ngữ nghĩa phù hợp.

Không tự tạo body chứa `exception.getMessage()` hoặc raw token. Nếu ứng dụng custom handler, phải giữ HTTP semantics và test `WWW-Authenticate`.

### 12.2. Cấu hình JWT và opaque token là hai lựa chọn xác minh

JWT:

```java
.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
```

Opaque:

```java
.oauth2ResourceServer(oauth2 ->
        oauth2.opaqueToken(Customizer.withDefaults()))
```

Chỉ cấu hình theo token contract thực tế. Một endpoint không tự động nên thử JWT rồi fallback opaque khi JWT lỗi. Nếu hệ thống nhận nhiều loại token, thiết kế resolver/route policy có trusted discriminator và test negative cases.

## 13. Spring WebFlux Resource Server

Trong WebFlux, cấu hình reactive:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveResourceServerConfiguration {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/**").permitAll()
                        .pathMatchers("/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Spring Security WebFlux cung cấp Bearer authentication/authorization handling cho reactive pipeline. Khi cần custom handler, dùng API thuộc **server/reactive namespace** đúng version (ví dụ các server-side Bearer entry point/access-denied handler), không truyền handler Servlet vào `ServerHttpSecurity`.

**Resource Server WebFlux cũng không refresh token thay caller.** Nó nhận Bearer access token, xác minh bằng `ReactiveJwtDecoder` hoặc `ReactiveOpaqueTokenIntrospector`, rồi trả lỗi tương ứng. OAuth client reactive mới là nơi dùng `ReactiveOAuth2AuthorizedClientManager` để lấy/refresh token.

## 14. Client-side refresh trong Spring Security OAuth2 Client

Spring Security OAuth2 Client có thể quản lý authorized client và refresh token. Cần phân biệt:

- **Resource Server**: xác minh token gửi đến API.
- **OAuth2 Client**: dùng registration để lấy token gọi API khác.

### 14.1. Servlet OAuth2AuthorizedClientManager

Ví dụ cấu hình provider hỗ trợ authorization code, refresh token và client credentials:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.web
        .DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web
        .OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.registration
        .ClientRegistrationRepository;

@Configuration
class OAuthClientConfiguration {

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
```

Provider `refreshToken()` cho phép manager sử dụng refresh token của authorized client khi cần theo trạng thái/expiry và cấu hình. Provider `clientCredentials()` xin access token bằng grant tương ứng; đừng giả định flow này có refresh token.

Đây là cấu hình **OAuth2 Client trong Servlet web application**, không phải cấu hình Resource Server.

### 14.2. Dùng OAuth2AuthorizedClientManager để authorize

Ví dụ lấy authorized client:

```java
OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest
                .withClientRegistrationId("orders-client")
                .principal(authentication)
                .build();

OAuth2AuthorizedClient client =
        authorizedClientManager.authorize(request);

if (client == null) {
    throw new IllegalStateException(
            "Could not authorize OAuth2 client");
}

String accessToken =
        client.getAccessToken().getTokenValue();
```

Đoạn trên là minh họa cho Servlet context; `authentication` phải là principal phù hợp và manager phải được gọi trong lifecycle đã cấu hình. Trong reactive app, không gọi API đồng bộ này trên event-loop.

### 14.3. ReactiveOAuth2AuthorizedClientManager

Với WebFlux, dùng reactive client manager/provider tương ứng. Khung cấu hình:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration
        .ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client
        .AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientService;

@Configuration
class ReactiveOAuthClientConfiguration {

    @Bean
    ReactiveOAuth2AuthorizedClientManager reactiveAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService authorizedClientService) {

        ReactiveOAuth2AuthorizedClientProvider provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .refreshToken()
                        .build();

        var manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                        registrations, authorizedClientService);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Các imports/API trên thuộc reactive OAuth2 Client; chọn đúng manager cho **service/background context** hay **web exchange context** theo loại ứng dụng. Trong WebFlux controller có user principal và repository theo request, có thể dùng `DefaultReactiveOAuth2AuthorizedClientManager` với `ServerOAuth2AuthorizedClientRepository`. Trong service không có `ServerWebExchange`, dùng service-backed manager.

**Đừng gọi `block()` trên `Mono<OAuth2AuthorizedClient>`** ở Netty event-loop. Compose kết quả bằng `flatMap`/`map` và để Reactor quản lý subscription.

### 14.4. Manager không đồng nghĩa tự retry mọi request sau 401

Authorized-client manager giúp authorize/re-authorize và refresh theo provider. Việc một request API đã nhận 401 rồi **được phát lại hay không** còn phụ thuộc WebClient filter, failure handler, token store và replayability của request.

Vì vậy, phải test riêng:

- Token hết hạn trước request: manager có refresh/reacquire đúng không?
- Resource Server trả 401 `invalid_token` dù token client nghĩ còn hạn: client có xử lý theo policy không?
- Hai request đồng thời: refresh token rotation có race không?
- 403 `insufficient_scope`: client có tránh refresh loop không?
- Request POST/streaming: body có thể phát lại và idempotency có được bảo vệ không?

Không mặc định một filter sẽ tự động thực hiện toàn bộ vòng đời refresh/retry trong mọi cấu hình Spring Security.

## 15. Client HTTP ngoài Spring: xử lý challenge theo giao thức

Pseudocode:

```text
response = send(request, currentAccessToken)

if response.status == 401
   and response.WWW-Authenticate contains Bearer error="invalid_token":

    newToken = refreshOrAcquireTokenOnce()

    if newToken is unavailable:
        requireAuthorizationAgainOrFail()
    else if requestCanBeSafelyReplayed:
        response = send(originalRequest, newToken)
    else:
        return explicitRetryRequired(newToken)

return response
```

Pseudocode không thay thế HTTP parser chuẩn. `WWW-Authenticate` có grammar riêng và có thể chứa nhiều challenges/parameters; không dùng substring parsing ngây thơ trong production nếu thư viện HTTP/OAuth client đã hỗ trợ Bearer challenges.

### 15.1. Một lần retry là giới hạn hữu ích

Không:

```text
while response is 401:
    refresh()
    retry()
```

Vòng lặp có thể:

- Gửi hàng trăm token requests tới AS.
- Tạo lock contention/refresh-token reuse.
- Che giấu lỗi issuer/audience/client configuration.
- Tạo tải lên Resource Server và Authorization Server.

Hãy giới hạn refresh/retry, ghi telemetry đã redaction và đưa người dùng vào authorization flow khi cần.

### 15.2. Kiểm tra request đã dùng token nào

Trong nhiều request đồng thời, một request có thể nhận 401 cho A1 trong khi request khác đã refresh thành A2. Trước khi gọi AS:

1. Đọc token store hiện tại.
2. Nếu token đã khác token A1 của request thất bại, dùng A2 và retry an toàn.
3. Nếu token vẫn là A1, tham gia shared refresh hoặc thực hiện refresh duy nhất.
4. Không gửi R1 cũ sau khi một request khác đã lưu R2.

Điều này tránh refresh lặp không cần thiết và giảm nguy cơ rotation reuse.

## 16. 401 có thể do token bị revoke, không chỉ hết hạn

Resource Server có thể từ chối access token trước `exp`:

- User/admin revoke consent hoặc session.
- AS revoke refresh-token family hoặc access-token grant.
- Client registration bị disable.
- Audience/issuer policy thay đổi.
- Introspection báo `active=false`.
- Token signing key bị thu hồi/không còn được tin.

Client nhận `invalid_token` nhưng thường không biết chính xác nguyên nhân. Nếu refresh token vẫn còn hợp lệ, AS có thể cấp access token mới; nếu cả grant bị revoke, AS trả `invalid_grant` và client cần authorization lại.

**Không được xem refresh token là cách vượt qua revocation policy.** AS có quyền từ chối refresh token hoặc revoke cả grant/token family.

### 16.1. Key rotation khác refresh token rotation

Hai cơ chế có tên giống nhau nhưng khác đối tượng:

| Cơ chế | Đối tượng | Mục tiêu |
| --- | --- | --- |
| JWT signing-key rotation | Private/public signing keys và JWKS | Thay khóa ký token, cho Resource Server cập nhật trusted public keys. |
| Refresh token rotation | Refresh token của OAuth grant | Thay refresh token sau mỗi lần sử dụng, phát hiện reuse. |
| Access token renewal | Access token mới | Cấp credential API mới trước/sau khi token cũ hết hạn hoặc bị từ chối. |

JWT signing key rotation **không tự refresh access token** ở client. Refresh token rotation **không tự thay JWKS**. Kiểm thử và runbook cần tách riêng.

## 17. Opaque introspection và client renewal

Với opaque token, Resource Server gọi AS introspection:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <resource-server-client-credential>
Content-Type: application/x-www-form-urlencoded

token=<caller-access-token>
```

Nếu AS trả:

```json
{"active": false}
```

Resource Server từ chối token và thường trả 401 `invalid_token` cho caller. Client có thể refresh/reacquire token qua **Token Endpoint**, nhưng không gọi introspection trực tiếp để tự quyết định quyền.

### 17.1. Phân biệt lỗi caller token và lỗi Resource Server–AS

| Lỗi | Ý nghĩa | Hành động vận hành |
| --- | --- | --- |
| Introspection HTTP 200 + `active=false` | Token caller không active theo AS. | Resource Server trả 401; client xem xét refresh/re-auth. |
| Introspection HTTP 401 `invalid_client` | Resource Server client credential sai. | Sửa secret/certificate/registration; không bắt mọi user đăng nhập lại như thể token hết hạn. |
| Introspection timeout/503 | AS/network unavailable. | Fail-closed, phân loại dependency; có thể 5xx/503 theo handler. |
| Introspection active=true, thiếu scope | Authentication thành công, quyền không đủ. | 403. |

Một số implementation có thể map lỗi dependency trong authentication thành 401 theo handler mặc định. Nếu ứng dụng cần phân biệt dependency outage thành 503, phải thiết kế exception handling có chủ đích, không làm lộ upstream response và **không tạo principal khi introspection chưa thành công**.

### 17.2. Client không nên refresh vì lỗi server credential

Nếu mọi request opaque token đồng loạt bị 401 do Resource Server dùng client secret cũ, refresh token của user không giải quyết được lỗi. Nó chỉ làm tăng tải AS. Monitoring nên phân biệt:

- `active=false`.
- `invalid_client` của introspection caller.
- TLS/connection timeout.
- AS 5xx.

Client có thể thấy một response tổng quát, nhưng đội vận hành phải có correlation ID/metrics để xác định lỗi ở hop nào.

## 18. OIDC session và refresh token

OIDC thêm ID token và user authentication context, nhưng **access token vẫn là credential gọi API**. Một web app có thể:

1. Đăng nhập bằng Authorization Code Flow.
2. Nhận ID token và access token; có thể có refresh token theo policy.
3. Dùng access token gọi Resource Server.
4. Khi access token hết hạn, OAuth client/BFF refresh theo grant hoặc thực hiện login lại.

### 18.1. ID token không dùng để gọi API thay access token

Không gửi:

```http
Authorization: Bearer <OIDC-ID-token>
```

chỉ vì token này còn hạn và có chữ ký hợp lệ. Resource Server cần access-token profile, issuer, audience/resource và scope phù hợp. ID token thường có `aud` là client ID, không phải API resource.

### 18.2. BFF giữ refresh token server-side

Trong kiến trúc BFF:

```text
Browser ── session cookie ──> BFF
                               |
                               | access token
                               v
                         Resource Server

BFF ── refresh token grant ──> Authorization Server
```

Browser có thể chỉ giữ session cookie HttpOnly/Secure/SameSite phù hợp; BFF giữ authorized client/refresh token server-side. BFF phải bảo vệ session, CSRF và token store theo mô hình threat của ứng dụng.

Không trả refresh token về JavaScript chỉ để browser tự refresh nếu kiến trúc BFF được chọn nhằm giữ credential server-side.

### 18.3. SPA/mobile public clients

Public clients không giữ được client secret một cách bí mật. Nếu AS cấp refresh token cho public client, cần áp dụng yêu cầu hiện hành của AS và OAuth security best practices như:

- Authorization Code + PKCE cho login.
- Refresh token rotation hoặc sender-constrained refresh tokens theo khả năng AS.
- Secure platform storage cho mobile; không lưu plaintext trong localStorage nếu threat model yêu cầu bảo vệ mạnh hơn.
- XSS/CSRF protections phù hợp với cách giữ token.
- Không log/analytics token.

Client public không được nhúng client secret như thể đó là một confidential client.

## 19. Token response và thời điểm hết hạn

Token endpoint thường trả:

```json
{
  "access_token": "<value>",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "<optional-value>",
  "scope": "orders:read"
}
```

Client nên lưu:

- Access token (được bảo vệ).
- Thời điểm nhận token và `expires_in`.
- Refresh token nếu AS cấp.
- Scope/resource/client registration liên quan.
- Thông tin version/rotation của token state nếu cần.

### 19.1. expires_in và clock skew

`expires_in` là khoảng thời gian tính từ lúc AS phát hành/response theo contract. Client có thể đặt safety window để tránh gửi token quá sát hạn. Đồng hồ máy client có thể sai; nên tránh dựa hoàn toàn vào local wall-clock.

Nếu client decode `exp` từ JWT:

- Chỉ dùng làm hint để lập lịch/UX.
- Không tin payload để cấp quyền hoặc bỏ qua 401.
- Không log JWT để debug.
- Resource Server vẫn xác minh token độc lập.

### 19.2. Không cache access token vô hạn

Token cache cần:

- Expiration-aware.
- Key theo client registration/principal/session/resource.
- Invalidation khi revoke/invalid_grant hoặc client logout.
- Đồng bộ khi rotation.
- Encryption/access control.
- Giới hạn retention và audit.

Không dùng một global access token cho mọi tenant/user nếu authorization contract yêu cầu tách principal hoặc resource.

## 20. Logout, revoke và token lifecycle

Logout có nhiều nghĩa tùy kiến trúc:

- Xóa session phía client/BFF.
- Thu hồi refresh token/grant tại AS nếu có revoke endpoint và policy.
- Xóa authorized client/token cache.
- Thu hồi server session.
- Vô hiệu access token theo cơ chế AS (introspection, denylist, short lifetime hoặc sender-constrained tokens).

**Xóa access token ở browser không tự thu hồi token ở AS**. JWT offline có thể vẫn được chấp nhận tới `exp` nếu Resource Server không có revocation check/denylist. Opaque introspection có thể phản ánh trạng thái revoke nhanh hơn, tùy cache.

### 20.1. Refresh token bị revoke

Sau khi AS revoke refresh token:

- Client không được tiếp tục dùng token cũ.
- Refresh tiếp theo có thể trả `invalid_grant`.
- Access token đã phát hành có thể vẫn còn hiệu lực đến `exp` nếu AS/Resource Server không có cơ chế revoke tức thời.
- Nếu hệ thống cần logout/revocation nhanh, cần thiết kế token lifetime, introspection, session version hoặc denylist phù hợp.

### 20.2. Logout không nên dựa vào client-only flag

Một biến JavaScript `loggedOut=true` không đủ thu hồi credential đã phát ra. Phải xác định server-side session/grant lifecycle và các API có thể vẫn chấp nhận token cũ trong cửa sổ nào.

## 21. Kiểm thử Resource Server và OAuth client theo luồng end-to-end

Một bộ test tốt không chỉ kiểm tra Resource Server trả 401; cần chứng minh **client xử lý challenge và refresh đúng**.

### 21.1. Ma trận phía Resource Server

| Case | Request | Token state | Kết quả mong đợi |
| --- | --- | --- | --- |
| RS-01 | Protected endpoint, không có Bearer | Không credential | 401 + Bearer challenge, thường không `error`. |
| RS-02 | Bearer token hết hạn | Invalid token | 401 `invalid_token`. |
| RS-03 | Bearer token bị revoke/inactive | Invalid token | 401 `invalid_token`. |
| RS-04 | JWT chữ ký sai | Invalid token | 401; không vào controller/domain. |
| RS-05 | JWT sai issuer/audience | Invalid token | 401; không tạo Authentication. |
| RS-06 | Opaque introspection `active=false` | Inactive | 401. |
| RS-07 | Token hợp lệ, thiếu scope | Authenticated, denied | 403; `insufficient_scope` nếu phù hợp. |
| RS-08 | Token hợp lệ, đủ scope, đúng tenant | Authenticated, allowed | 2xx theo endpoint. |
| RS-09 | Token đủ scope, sai owner/tenant | Domain denied | 403/404 theo contract. |
| RS-10 | Bearer header malformed | Request invalid | 400/401 theo resolver và RFC semantics. |
| RS-11 | Introspection/JWKS unavailable | Chưa xác minh được | Fail-closed; status theo dependency policy. |
| RS-12 | Response error | Không áp dụng | Không chứa raw token/secret/JWKS nội bộ/stack trace. |

### 21.2. Ma trận phía OAuth client

| Case | API response | Token endpoint | Kết quả mong đợi |
| --- | --- | --- | --- |
| CL-01 | 401 `invalid_token`, refresh token còn hợp lệ | 200 + access mới | Lưu token mới và retry tối đa một lần nếu request replay-safe. |
| CL-02 | 401 `invalid_token`, refresh token revoked | 400 `invalid_grant` | Dừng retry, xóa credential cũ và authorization lại khi cần. |
| CL-03 | 401 không có Bearer credential | Chưa gọi | Lấy access token theo flow; không giả định refresh token đang có. |
| CL-04 | 403 `insufficient_scope` | Không refresh tự động | Hiển thị/đề nghị quyền phù hợp hoặc báo không đủ quyền. |
| CL-05 | 400 `invalid_request` | Không refresh | Sửa request/header. |
| CL-06 | 503 Resource Server unavailable | Không refresh chỉ vì status | Backoff theo API policy, giữ phân loại dependency. |
| CL-07 | 401 sau khi token mới đã được dùng | Không refresh lần hai | Dừng, báo lỗi issuer/audience/configuration hoặc session. |
| CL-08 | Ba request đồng thời 401 cùng token | Một refresh operation | Single-flight; cả ba dùng token mới nếu replay-safe. |
| CL-09 | Refresh token rotation | AS trả R2 | Persist R2 atomically; không dùng lại R1. |
| CL-10 | POST đã có Idempotency-Key | Refresh thành công | Replay cùng logical operation một lần theo contract. |
| CL-11 | POST body không replayable | Refresh thành công | Không tự gửi lại; yêu cầu retry có chủ đích. |
| CL-12 | Client Credentials access token hết hạn | Token endpoint 200 client_credentials | Xin access token mới; không giả định refresh token. |

### 21.3. Ma trận kết hợp

| Token | Endpoint | Resource Server | Client action | Expected |
| --- | --- | --- | --- | --- |
| JWT A expired | Orders API | 401 `invalid_token` | Refresh token grant | Token mới + retry an toàn. |
| JWT A wrong audience | Orders API | 401 `invalid_token` | Refresh/reacquire chỉ nếu sửa được resource registration; không loop | Dừng nếu token mới vẫn sai. |
| JWT A valid, no read scope | GET Orders | 403 `insufficient_scope` | Không refresh tự động | Quyền không đủ. |
| Opaque B inactive | Legacy API | 401 `invalid_token` | Refresh/reacquire theo grant B | Retry một lần nếu thành công. |
| Opaque B active, no scope | Legacy API | 403 | Không refresh tự động | Cần scope/consent policy khác. |
| Client assertion gửi tới API | Orders API | 401 | Sửa OAuth client flow | Không refresh. |
| Refresh token gửi tới API | Orders API | 401 | Gửi access token đúng loại | Không dùng refresh token ở resource. |
| AS introspection credential sai | Legacy API | Fail-closed; có thể 5xx theo handler | Không refresh user token | Sửa server-to-AS credential. |

## 22. Kiểm thử bằng MockMvc và WebTestClient

### 22.1. MockMvc: test 401 và Bearer challenge

Với Servlet Resource Server, dùng integration test qua filter chain:

```java
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerBearerErrorTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void missingTokenReturnsBearerChallenge() throws Exception {
        mockMvc.perform(get("/api/orders"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().exists(
                        HttpHeaders.WWW_AUTHENTICATE));
    }

    @Test
    void invalidTokenReturnsInvalidTokenChallenge() throws Exception {
        mockMvc.perform(get("/api/orders")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer invalid-test-token"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        org.hamcrest.Matchers.containsString(
                                "invalid_token")));
    }
}
```

Test giả định `/api/orders` được bảo vệ, Resource Server decoder thật hoặc test decoder từ chối `invalid-test-token`, và default Bearer handlers được dùng. Tùy cấu hình custom handler, assertion header phải khớp contract của ứng dụng.

### 22.2. Test 403 khi token hợp lệ nhưng thiếu scope

Có thể dùng `jwt()` test support để kiểm tra authorization:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;

mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile:read"))))
        .andExpect(status().isForbidden());
```

`jwt()` tạo Authentication giả lập. Test này kiểm tra **authorization**, không chứng minh JWT signature/issuer/audience validation. Muốn kiểm tra invalid token, phải gửi Bearer value thật qua decoder.

### 22.3. WebTestClient cho WebFlux

Với WebFlux, dùng `WebTestClient` qua SecurityWebFilterChain:

```java
webTestClient.get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isUnauthorized()
        .expectHeader().exists("WWW-Authenticate");
```

Và với Bearer token test:

```java
webTestClient.get()
        .uri("/api/orders")
        .headers(headers ->
                headers.setBearerAuth("invalid-test-token"))
        .exchange()
        .expectStatus().isUnauthorized();
```

Đảm bảo test client được bind với application security filters. Không chỉ gọi controller trực tiếp.

## 23. Kiểm thử refresh token grant bằng mock Authorization Server

Client test cần một AS giả lập để xác nhận:

1. Client gọi đúng `POST /oauth2/token`.
2. `Content-Type` là form-urlencoded.
3. `grant_type=refresh_token` được gửi đúng.
4. Refresh token hiện hành được gửi tới AS, không gửi đến Resource Server.
5. Client authentication đúng loại và không bị lộ.
6. `invalid_grant` làm dừng retry và yêu cầu authorization lại.
7. Refresh rotation lưu token mới và không tái sử dụng token cũ.
8. Hai request đồng thời không tạo hai refresh requests cho cùng grant.

Pseudo test:

```text
Given:
  access token A1 expired
  refresh token R1 valid
  AS mock returns access token A2 and refresh token R2

When:
  client calls GET /api/orders with A1
  Resource Server returns 401 invalid_token
  client refreshes R1
  client retries with A2

Then:
  token endpoint refresh calls = 1
  API retry uses A2
  stored refresh token = R2
  stored refresh token != R1
  retry count for original request <= 1
```

Đây là **test scenario**, không phải kết quả test đã chạy. Trong test implementation, dùng token giả, mock AS và mock Resource Server; không sử dụng token production.

### 23.1. Test invalid_grant

```text
Given:
  access token A1 rejected
  refresh token R1 revoked

When:
  client POSTs grant_type=refresh_token

Then:
  AS returns invalid_grant
  client does not reuse R1
  client does not loop refresh
  client clears/invalidates stale authorized-client state
  client starts authorization again when appropriate
```

### 23.2. Test concurrency

```text
Given:
  three API requests use same expired access token A1
  refresh token R1 is rotating

When:
  all three receive invalid_token concurrently

Then:
  one shared refresh operation occurs
  new token pair A2/R2 is stored atomically
  waiting requests read A2/R2
  R1 is not reused
  each replay-safe request is retried at most once
```

Nếu test multi-pod deployment, lock/token store phải là shared mechanism phù hợp. Một unit test chạy trong một JVM không chứng minh distributed coordination hoạt động.

## 24. An toàn khi lưu token

Access token và refresh token đều là bearer credentials trong nhiều mô hình; ai có token có thể sử dụng nó theo phạm vi và thời hạn được cấp. Refresh token thường có thể cấp access token mới nên cần bảo vệ mạnh.

### 24.1. Những nơi không lưu token

Không lưu raw token trong:

- Source code, Git repository, YAML committed, Docker image.
- Browser URL/query string.
- Analytics, crash report, frontend console.
- Application logs, reverse proxy access logs, distributed traces.
- Support tickets/chat hoặc screenshot.
- Unencrypted database field hoặc cache có quyền truy cập rộng.

### 24.2. Lưu trữ theo loại client

| Client | Hướng bảo vệ |
| --- | --- |
| Server-side confidential client | Secret manager/KMS, encrypted token store, least-privilege service account. |
| BFF | Refresh token server-side, session cookie an toàn, CSRF protection và session rotation. |
| Native mobile | Secure platform storage như Keychain/Keystore theo platform policy; không nhúng client secret. |
| SPA public client | Hạn chế thời gian/phạm vi credential, cân nhắc BFF; bảo vệ XSS/CSRF và tuân thủ refresh rotation/sender constraint. |
| Machine workload | Workload identity/secret manager, short-lived access token, credential rotation và audit. |

### 24.3. Redaction

Log an toàn:

```java
log.info(
        "OAuth token renewal outcome: registration={}, result={}, requestId={}",
        registrationId,
        "success",
        requestId);
```

Không log:

```java
log.error(
        "Refresh failed: accessToken={}, refreshToken={}, clientSecret={}",
        accessToken, refreshToken, clientSecret);
```

Nếu cần điều tra, dùng correlation ID, grant/client registration ID được phép, error category và timestamp. Không dùng prefix/suffix dài của token để “dễ nhận diện”.

## 25. Khi nào client phải yêu cầu đăng nhập/authorization lại?

Các trường hợp thường cần authorization lại:

- Refresh token hết hạn hoặc bị revoke (`invalid_grant`).
- User/admin thu hồi consent/grant.
- Refresh-token family bị revoke sau reuse detection.
- Client registration bị vô hiệu hóa hoặc đổi policy không thể đáp ứng.
- Scope mới cần consent/authorization mà refresh grant không thể cấp.
- User session/IdP policy yêu cầu tương tác lại (MFA, re-authentication).

Client nên:

1. Xóa/đánh dấu credential stale theo policy.
2. Giữ dữ liệu nghiệp vụ chưa gửi hoặc chưa commit ở trạng thái an toàn.
3. Bắt đầu Authorization Code + PKCE/flow phù hợp khi cần user interaction.
4. Không tự động gửi lại thao tác ghi dữ liệu mà không có idempotency.
5. Hiển thị thông điệp dễ hiểu, không tiết lộ token/error nội bộ.

Ví dụ thông điệp UI:

```text
Your session has expired. Sign in again to continue.
```

Không hiển thị `invalid_grant` kèm refresh token hoặc stack trace cho người dùng cuối.

## 26. Những lỗi thiết kế phổ biến

### Lỗi 1 — Resource Server tự refresh token của caller

Resource Server không nên nhận refresh token. Refresh là nhiệm vụ OAuth client với AS.

### Lỗi 2 — Client refresh mọi 401

401 có thể do thiếu credential, sai audience, issuer, signature hoặc cấu hình. Chỉ xử lý refresh theo challenge/policy và giới hạn một lần.

### Lỗi 3 — Refresh khi gặp 403 insufficient_scope

Token hợp lệ nhưng không đủ quyền. Refresh cùng grant thường không tự cấp scope mới; cần authorization/consent policy phù hợp.

### Lỗi 4 — Dùng refresh token làm Bearer credential tới API

Refresh token không phải access token. Resource Server phải từ chối.

### Lỗi 5 — Retry request vô hạn

Tạo vòng lặp token endpoint/API, tải hệ thống và che giấu lỗi cấu hình. Giới hạn retry.

### Lỗi 6 — Retry POST mà không có idempotency

Có thể tạo đơn hàng/thanh toán hai lần nếu request đầu đã được xử lý hoặc response bị mất. Dùng Idempotency-Key và server-side deduplication theo contract.

### Lỗi 7 — Không xử lý refresh token rotation

Client tiếp tục dùng R1 sau khi AS đã cấp R2 có thể kích hoạt reuse detection và thu hồi token family. Lưu cặp token mới atomic.

### Lỗi 8 — Nhiều request đồng thời refresh cùng token

Gây race condition. Dùng single-flight/lock theo grant và đọc lại token store sau khi lấy lock.

### Lỗi 9 — Coi invalid_grant là lỗi mạng

`invalid_grant` là lỗi grant/refresh credential, không nên retry liên tục như timeout. Dừng và authorization lại khi cần.

### Lỗi 10 — Coi lỗi introspection client secret là token hết hạn

Đây là lỗi Resource Server–AS. Refresh token user không sửa được secret của Resource Server.

### Lỗi 11 — Trả chi tiết token hết hạn qua error_description

Client chỉ cần mã lỗi chuẩn; không cần raw claims, token hoặc JWKS internals.

### Lỗi 12 — Dựa vào JWT exp ở client làm nguồn quyết định bảo mật

Client có thể lập lịch refresh từ `expires_in`/`exp`, nhưng Resource Server vẫn phải tự xác minh. Client clock không phải authority.

### Lỗi 13 — Cho rằng logout xóa token khỏi mọi nơi

Xóa local state không tự thu hồi JWT offline hoặc refresh grant tại AS. Cần revocation/session design.

### Lỗi 14 — Không kiểm thử token mới sau refresh

Token mới có thể sai audience/scope/resource do registration. Phải test retry thực sự qua Resource Server, không chỉ test token endpoint trả 200.

## 27. Tình huống vận hành minh họa

### A. Access token hết hạn bình thường

Client gửi access token đã hết hạn. Resource Server trả 401 `invalid_token`. Client dùng refresh token còn hiệu lực, nhận access token mới, lưu state và retry GET một lần. API xác minh token mới và trả 2xx nếu scope/resource đúng.

### B. Access token bị revoke nhưng refresh token còn hiệu lực

Resource Server/introspection từ chối access token. Client thử refresh một lần. AS có thể cấp access token mới nếu grant còn hợp lệ. Nếu AS đã revoke cả grant, nó trả `invalid_grant` và client cần authorization lại.

### C. Token hợp lệ nhưng thiếu scope

Client có `orders:read` nhưng gọi POST yêu cầu `orders:write`. Resource Server trả 403 `insufficient_scope`. Client không refresh cùng token lặp lại; nó phải xin quyền phù hợp qua authorization policy hoặc báo user không được phép.

### D. Client Credentials token hết hạn

Workload nhận 401 `invalid_token`. Nó gọi token endpoint bằng `grant_type=client_credentials` để xin access token mới. Không giả định có refresh token; nếu client authentication sai, dừng và báo lỗi vận hành.

### E. Refresh token rotation và ba request đồng thời

Ba API requests cùng dùng A1/R1. Single-flight coordinator chỉ gửi một refresh request, nhận A2/R2 và lưu atomic. Cả ba request dùng A2 nếu có thể replay. R1 không được gửi lại.

### F. Refresh token đã bị revoke

AS trả `invalid_grant`. Client dừng refresh, xóa authorized-client state stale và điều hướng user authorization lại. Không retry R1.

### G. Sai audience

Client dùng access token dành `payments-api` gọi `orders-api`. Resource Server trả 401 `invalid_token`. Refresh cùng registration có thể tạo lại token sai resource; client cần sửa resource/audience request/registration, không refresh loop.

### H. Opaque introspection AS tạm unavailable

Resource Server không thể xác minh token, fail-closed và có thể trả 503 theo error handling. Client xử lý service availability/backoff; không refresh user token chỉ vì AS của Resource Server đang down.

### I. Resource Server dùng introspection client secret cũ

AS trả `invalid_client` cho Resource Server. API không chấp nhận token vì chưa xác minh được, nhưng lỗi gốc là server credential. Đội vận hành cập nhật secret; client không cần refresh mọi user session.

### J. POST tạo đơn hàng bị 401

Client refresh thành công rồi retry POST. Nếu API hỗ trợ Idempotency-Key, request retry giữ cùng key và server deduplicate. Nếu không thể bảo đảm request đầu chưa tạo side effect hoặc body không replayable, client yêu cầu hành động retry có chủ đích.

### K. User logout ở IdP

Refresh grant bị revoke. Access token JWT offline có thể vẫn được chấp nhận đến `exp` nếu không có revocation check. Thiết kế logout cần tính đến token lifetime/introspection/denylist và session state.

### L. Browser dùng BFF

Browser gửi session cookie tới BFF. BFF refresh token server-side và gọi Resource Server bằng access token mới. Refresh token không bao giờ được gửi tới API Orders hoặc JavaScript.

## 28. Checklist test theo luồng

Các mục sau là **đầu vào cho test plan**, không phải kết quả đã chạy:

- [ ] Không gửi Bearer credential tới protected endpoint → 401 challenge không cần `invalid_token`.
- [ ] Bearer token hết hạn → 401 `invalid_token`.
- [ ] Bearer token bị revoke/inactive → 401 `invalid_token`.
- [ ] Token sai signature/issuer/audience → 401; không vào business handler.
- [ ] Token hợp lệ nhưng thiếu scope → 403; client không refresh loop.
- [ ] Request Bearer malformed → 400/401 theo contract; client sửa request.
- [ ] Refresh token còn hợp lệ → token endpoint trả access token mới.
- [ ] Refresh token rotation → client thay token cũ bằng token mới atomically.
- [ ] Refresh token `invalid_grant` → không retry cùng token; authorization lại khi cần.
- [ ] Client Credentials hết hạn → xin access token bằng client credentials grant.
- [ ] Nhiều requests đồng thời → single-flight refresh, không reuse token cũ.
- [ ] GET retry sau refresh → tối đa một lần.
- [ ] POST retry → có Idempotency-Key và replay-safe contract hoặc không tự retry.
- [ ] Access token mới vẫn 401 → dừng, không loop.
- [ ] AS introspection unavailable → fail-closed, không giả lập principal.
- [ ] Introspection client secret sai → phân loại server-side, không nhầm user token invalid.
- [ ] Error response/log không có raw access/refresh token, client secret hoặc stack trace.
- [ ] Logout/revoke → behavior của access token và refresh grant đúng revocation policy.

## 29. Câu hỏi tự kiểm tra

**1. Resource Server có trách nhiệm refresh access token không?** Không. Nó xác minh token và trả kết quả; OAuth client gọi Token Endpoint để refresh/reacquire.

**2. Khi không gửi token, Resource Server nên trả gì?** Thường 401 với Bearer challenge, không nhất thiết có `error="invalid_token"`.

**3. Khi token hết hạn hoặc bị revoke, Bearer error nào phù hợp?** `invalid_token`, thường HTTP 401.

**4. Khi token hợp lệ nhưng thiếu scope?** `insufficient_scope`, thường HTTP 403.

**5. Client có nên refresh khi gặp mọi 401 không?** Không. Phải xem request có Bearer credential, challenge và client grant/policy.

**6. Client có nên refresh khi gặp 403 insufficient_scope không?** Không tự động. Cần quyền/consent/authorization policy khác nếu được phép.

**7. Refresh token được gửi đến đâu?** Authorization Server Token Endpoint với `grant_type=refresh_token`.

**8. Refresh token có được gửi tới Resource Server không?** Không.

**9. Client Credentials thường lấy token mới thế nào?** Gửi lại client credentials grant, không giả định có refresh token.

**10. `invalid_grant` có nên retry cùng refresh token không?** Không lặp vô hạn; token có thể hết hạn/revoke/đã rotation. Authorization lại khi phù hợp.

**11. Refresh token rotation gây race condition gì?** Nhiều request dùng cùng token cũ; AS có thể phát hiện reuse và revoke token family. Cần single-flight và atomic persistence.

**12. Có thể retry POST sau refresh không?** Chỉ khi request replay-safe, body phát lại được và idempotency được bảo đảm.

**13. Token mới vẫn bị 401 thì sao?** Dừng retry, kiểm tra issuer/audience/resource/client registration và yêu cầu authorization lại hoặc báo lỗi.

**14. Introspection AS trả 401 có nghĩa user token hết hạn không?** Không nhất thiết; có thể Resource Server client credential sai.

**15. JWT signing-key rotation khác refresh-token rotation thế nào?** Một bên thay key ký/JWKS; bên kia thay refresh credential trong OAuth grant.

**16. Xóa token ở browser có thu hồi JWT ở Resource Server không?** Không nhất thiết; JWT offline có thể còn hiệu lực tới exp nếu không có revocation mechanism.

**17. Client có thể dùng `exp` để lập lịch refresh không?** Có thể như hint, nhưng không dùng nó thay xác minh của Resource Server.

**18. Spring OAuth2AuthorizedClientManager có tự retry mọi API request 401 không?** Không nên giả định; manager/provider quản lý authorized client/token, còn request replay/failure handling cần cấu hình và test riêng.

**19. Vì sao không đưa error_description chi tiết vào Bearer challenge?** Tránh lộ token, key, endpoint nội bộ, stack trace và dữ liệu cá nhân.

**20. BFF giữ refresh token ở đâu?** Server-side authorized-client/token store được bảo vệ; browser chỉ nhận session mechanism phù hợp.

## 30. Tài liệu tham khảo chính thức

- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** `WWW-Authenticate`, `invalid_request`, `invalid_token` và `insufficient_scope`. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Token Endpoint và Refresh Token Grant. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ refresh token, rotation/sender constraint và các thực hành bảo mật OAuth hiện hành. https://www.rfc-editor.org/rfc/rfc9700
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token tại Authorization Server. https://www.rfc-editor.org/rfc/rfc7009
- **RFC 7662 — OAuth 2.0 Token Introspection:** trạng thái `active` của token. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 9110 — HTTP Semantics:** status 401/403 và authentication challenge. https://www.rfc-editor.org/rfc/rfc9110
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server JWT:** https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server Opaque Token:** https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — OAuth 2.0 Client:** https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- **Spring Security Reference — Reactive OAuth 2.0 Client:** https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- **Spring Security Reference — WebFlux OAuth 2.0 Resource Server:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html
- **Spring Security API — OAuth2AuthorizedClientManager / ReactiveOAuth2AuthorizedClientManager:** xem Javadoc đúng version Spring Security đang dùng.

## 31. Kết luận

Resource Server cần trả **Bearer challenge và HTTP status đúng giao thức** để client hiểu tình trạng credential. `401 invalid_token` cho biết access token không được chấp nhận; client có thể thử refresh/reacquire một lần nếu grant cho phép. `403 insufficient_scope` cho biết token đã được xác thực nhưng không có quyền cần thiết; refresh cùng grant không phải cách nâng scope. `400 invalid_request` yêu cầu sửa request, còn lỗi JWKS/introspection dependency cần được phân loại riêng và **fail-closed**.

Khi refresh thành công, client phải lưu access token mới và refresh token mới (nếu có rotation) một cách an toàn, xử lý concurrency bằng single-flight, rồi chỉ retry request khi body có thể phát lại và nghiệp vụ được bảo vệ bằng idempotency. Nếu AS trả `invalid_grant` hoặc token mới vẫn bị từ chối, client dừng vòng lặp và thực hiện authorization lại khi phù hợp.

**Ranh giới cần giữ rõ:** Resource Server xác minh access token; OAuth client quản lý và gia hạn credential; Authorization Server phát hành, rotate và revoke token. Khi mỗi bên làm đúng vai trò và các test bao phủ cả status, challenge, token endpoint, concurrency và side effects, vòng đời token mới có thể vận hành an toàn mà không làm lộ refresh credential hoặc vô tình cấp quyền vượt phạm vi.
