# Refresh token — Gia hạn quyền truy cập an toàn

**Refresh token** là credential do authorization server cấp cho OAuth client để client có thể yêu cầu access token mới sau khi access token hiện tại hết hạn hoặc không còn phù hợp. Refresh token thường có thời hạn dài hơn access token và chỉ được gửi tới **token endpoint** của authorization server đã phát hành nó. Resource server/API không được dùng refresh token để xác thực request nghiệp vụ.

Trong hệ thống authentication, refresh token duy trì quyền truy cập mà không buộc người dùng nhập lại mật khẩu hoặc thực hiện passkey/MFA ở mọi request. Đổi lại, refresh token trở thành credential có giá trị cao: nếu bị đánh cắp, attacker có thể liên tục xin access token mới trong phạm vi grant cho đến khi token hết hạn, bị thu hồi hoặc bị phát hiện reuse. Vì vậy cần quản lý vòng đời, lưu trữ, rotation, ràng buộc client, giới hạn scope, phát hiện tái sử dụng và logout một cách nhất quán.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt access token, refresh token, ID token và session cookie.
2. Mô tả vai trò của authorization server, OAuth client và resource server trong refresh grant.
3. Thiết kế thời hạn, scope, audience/resource, client binding và điều kiện cấp refresh token.
4. Triển khai refresh token rotation, token family và phát hiện reuse.
5. Xử lý request refresh đồng thời, retry, timeout và lỗi mạng mà không vô tình làm mất phiên hợp lệ.
6. Bảo vệ refresh token ở web, mobile, backend và workload.
7. Thu hồi token khi logout, đổi credential, mất thiết bị, nghi ngờ compromise hoặc thay đổi quyền.
8. Viết threat model và bộ kiểm thử cho token theft, replay, rotation race, downgrade và revocation.

## 2. Access token và refresh token khác nhau thế nào?

| Thuộc tính | Access token | Refresh token |
| --- | --- | --- |
| Mục đích | Gọi resource server/API để truy cập tài nguyên | Xin access token mới tại authorization server |
| Bên nhận | API/resource server có audience phù hợp | Token endpoint của authorization server đã phát hành |
| Thời hạn | Thường ngắn | Thường dài hơn, có giới hạn inactivity/absolute expiry theo policy |
| Nội dung/quyền | Có thể mang scope, audience, subject, expiry và claims cần thiết | Thường là opaque secret tham chiếu tới grant/session; không cần mang quyền API trực tiếp |
| Mức độ nhạy cảm | Cao; bearer access token bị lộ có thể bị dùng tới khi hết hạn/thu hồi | Rất cao; có thể tạo ra nhiều access token mới |
| Rotation | Có thể cấp token mới theo mỗi lần refresh | Có thể xoay mỗi lần sử dụng để phát hiện reuse |
| Nơi sử dụng | Gửi tới API/resource server | Chỉ gửi tới token endpoint được phép |

**ID token** trong OpenID Connect (OIDC) có mục đích khác: nó mang khẳng định về sự kiện xác thực và subject tới OIDC client. ID token không phải access token để gọi API và cũng không phải refresh token. Không dùng ID token hoặc refresh token thay cho session cookie tùy tiện.

Refresh token thường là chuỗi opaque ngẫu nhiên được authorization server tra cứu ở phía server. Một số hệ thống có thể dùng token tự chứa, nhưng chữ ký JWT hợp lệ không tự giải quyết được rotation, phát hiện reuse, ràng buộc grant và thu hồi tức thời. Nếu cần các thuộc tính đó, vẫn phải có trạng thái server-side hoặc cơ chế tương đương.

## 3. Thành phần và ranh giới tin cậy

| Thành phần | Vai trò | Trách nhiệm |
| --- | --- | --- |
| **Resource owner / người dùng** | Cấp quyền truy cập hoặc đăng nhập qua authorization server | Quản lý tài khoản và có thể thu hồi consent/session theo chính sách. |
| **OAuth client** | Ứng dụng yêu cầu access token và lưu refresh token | Bảo vệ token, xác thực client nếu là confidential client, chỉ refresh đúng grant. |
| **Authorization server** | Phát hành, xoay vòng, kiểm tra và thu hồi token | Kiểm soát client, grant, scope, thời hạn, token family và reuse detection. |
| **Resource server/API** | Nhận access token để bảo vệ tài nguyên | Kiểm tra access token, audience, scope/permission và trạng thái theo policy; không nhận refresh token. |
| **Client storage / device** | Nơi refresh token được giữ giữa các lần gọi | Cần bảo vệ khỏi XSS, malware, backup không an toàn, debug log và truy cập trái phép. |

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server
    U->>C: Đăng nhập và cấp quyền
    C->>AS: Authorization Code + PKCE
    AS-->>C: Access token + refresh token
    C->>RS: Request với access token
    RS-->>C: Resource response
    Note over C,AS: Khi access token hết hạn hoặc cần thay mới
    C->>AS: Refresh grant với refresh token
    AS->>AS: Kiểm tra client, grant, token và trạng thái
    AS-->>C: Access token mới + refresh token mới (nếu rotation)
    C->>RS: Request với access token mới
    RS-->>C: Resource response
~~~

Ranh giới quan trọng nhất là **client → authorization server** khi refresh. Client phải gửi token tới đúng issuer/token endpoint; không gửi qua resource server hoặc URL tùy ý. Authorization server chỉ cấp token mới khi refresh token hợp lệ, còn hiệu lực, gắn với đúng client/grant và đáp ứng policy.

## 4. Khi nào cấp refresh token?

Refresh token thường được cấp trong luồng authorization phù hợp sau khi người dùng hoặc chính sách đã cho phép client truy cập. Trong OAuth 2.0 hiện đại, ứng dụng web/mobile thường dùng **Authorization Code Flow + PKCE**; không sử dụng Resource Owner Password Credentials grant cho ứng dụng mới. Implicit flow cũng không nên dùng cho ứng dụng mới theo hướng dẫn bảo mật hiện hành.

Refresh token có thể được cấp khi:
- Client cần duy trì quyền truy cập lâu hơn tuổi thọ của access token.
- Người dùng đã cấp consent/grant phù hợp.
- Client và authorization server có cơ chế bảo vệ refresh token tương ứng với loại client.
- Scope/resource được cấp rõ ràng và có thể giới hạn.
- Chính sách session, inactivity và absolute lifetime được xác định.

Không phải mọi client đều cần refresh token. Một client có thể yêu cầu người dùng đăng nhập lại khi access token hết hạn, đặc biệt nếu dữ liệu nhạy cảm hoặc thời gian truy cập cần ngắn. Cấp refresh token cho một ứng dụng chỉ để tránh mọi tương tác người dùng có thể làm tăng đáng kể hậu quả khi thiết bị bị chiếm.

### 4.1. Confidential client và public client

| Loại client | Ví dụ | Kiểm soát cần có |
| --- | --- | --- |
| **Confidential client** | Backend web app có thể giữ client credential an toàn | Client authentication tại token endpoint, bảo vệ refresh token server-side, rotation/reuse detection và giới hạn grant. |
| **Public client** | SPA chạy trong browser, mobile app, desktop app không thể giữ client secret bí mật | Không nhúng client secret; dùng PKCE cho authorization code; bảo vệ refresh token bằng rotation hoặc sender-constraining theo yêu cầu hiện hành. |

Một client secret được nhúng trong JavaScript hoặc mobile binary không còn là bí mật đáng tin. Không dùng nó như bằng chứng xác thực client mạnh. Với public clients, RFC 9700 yêu cầu biện pháp phát hiện replay phù hợp cho refresh token, như rotation hoặc sender-constrained refresh token.

## 5. Refresh grant diễn ra như thế nào?

Khi access token hết hạn, client gửi refresh token tới token endpoint. Một request minh họa theo OAuth 2.0:

~~~http
POST /oauth/token HTTP/1.1
Host: auth.studyhub.example
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
refresh_token=<refresh-token-value>&
client_id=studyhub-web
~~~

Với confidential client, request còn phải xác thực client theo phương thức đã đăng ký (ví dụ client authentication ở token endpoint). Với public client, không gửi client secret giả; authorization server áp policy phù hợp và kiểm tra ràng buộc client/token.

Server kiểm tra:
1. Token có tồn tại, đúng issuer và đúng loại refresh token không?
2. Token còn hạn, chưa bị revoke, chưa bị tiêu thụ và grant vẫn active không?
3. Token được cấp cho client này không? Client authentication/sender constraint có hợp lệ không?
4. Người dùng, session và consent/grant có còn hợp lệ không?
5. Scope/resource yêu cầu có nằm trong phạm vi đã được cấp không?
6. Token family có dấu hiệu reuse, rotation bất thường hoặc compromise không?

Nếu hợp lệ, authorization server cấp access token mới. Khi rotation được bật, server đồng thời phát hành refresh token mới, vô hiệu refresh token cũ và lưu quan hệ giữa hai token trong cùng family. Client phải thay token cũ bằng token mới một cách an toàn.

### 5.1. Sequence diagram có rotation

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Authorization Server
    participant DB as Token Store
    C->>AS: refresh_token = R1
    AS->>DB: Kiểm tra R1, client, grant và trạng thái
    DB-->>AS: R1 active
    AS->>DB: Atomic consume R1, tạo R2 trong cùng family
    DB-->>AS: Rotation committed
    AS-->>C: Access token A2 + refresh token R2
    C->>C: Lưu R2 an toàn, loại R1 khỏi storage
    Note over AS,DB: Nếu R1 được dùng lại sau khi đã rotate
    C->>AS: Refresh với R1 cũ
    AS->>DB: Phát hiện reuse của token đã tiêu thụ
    AS->>DB: Revoke token family theo policy
    AS-->>C: invalid_grant / yêu cầu xác thực lại
~~~

Rotation phải được thực hiện **nguyên tử**: không để hai request đồng thời cùng tiêu thụ một refresh token và tạo ra hai nhánh token hợp lệ ngoài dự kiến.

## 6. Refresh token rotation và token family

**Refresh token rotation** thay token hiện tại bằng token mới mỗi khi refresh thành công. Token cũ trở thành không hợp lệ. Authorization server lưu trạng thái và quan hệ lineage/family để phát hiện một token đã bị tiêu thụ nhưng xuất hiện lại.

Ví dụ:
- R1 được cấp ban đầu.
- Client dùng R1 và nhận A2 + R2.
- R1 được đánh dấu consumed/revoked; R2 active.
- Nếu R1 xuất hiện lần nữa, server có thể suy ra token đã bị sao chép hoặc một client cũ đang dùng dữ liệu stale.
- Vì server không luôn biết bên nào là attacker và bên nào là client hợp lệ, policy thường revoke **active token family** và yêu cầu authorization lại.

Token family là nhóm refresh token thuộc cùng một grant/session lineage. Việc revoke family ngăn các token kế tiếp tiếp tục được dùng sau khi phát hiện reuse.

### 6.1. Tại sao reuse detection quan trọng?

Nếu refresh token chỉ là bearer secret sống lâu và không rotate, attacker có thể sử dụng nó nhiều lần cho tới khi hết hạn hoặc bị revoke. Rotation làm cho token cũ chỉ được sử dụng một lần. Nếu token cũ bị dùng lại, server có tín hiệu replay và có thể chặn toàn bộ chuỗi refresh.

Tuy nhiên, reuse không luôn chứng minh có attacker: request đồng thời, retry sau timeout hoặc client lưu token mới không thành công cũng có thể làm token cũ xuất hiện lại. Vì vậy client phải quản lý refresh một cách có phối hợp, còn server phải thiết kế trạng thái và lỗi rõ ràng.

### 6.2. Atomic rotation

Server cần thực hiện logic gần với compare-and-swap/transaction:

~~~text
rotate(refreshToken, client):
    begin transaction
    record = findTokenByVerifier(refreshToken)

    if record missing:
        reject invalid_grant

    if record.status == consumed:
        revokeActiveFamily(record.familyId)
        audit reuse_detected
        commit
        reject invalid_grant

    assert record.status == active
    assert record.clientId == client.id
    assert record.grantStatus == active
    assert notExpired(record)
    assert senderConstraintMatchesIfConfigured(record, request)

    mark record consumed
    newToken = secureRandomRefreshToken()
    insert newToken with same family and parent=record.id
    update family currentTokenId=newToken.id
    commit

    return new access token and new refresh token
~~~

Pseudocode minh họa các bất biến. Việc so khớp token, khóa dòng, cập nhật family và ghi audit phải được thiết kế để hai request đồng thời không thể cùng thắng. Không giữ transaction database mở trong lúc gọi dịch vụ ngoài không cần thiết.

### 6.3. Race condition và refresh đồng thời

Một số client có nhiều request cùng phát hiện access token hết hạn và cùng gọi refresh. Nếu cả hai gửi R1:
- Request thứ nhất rotate R1 thành R2.
- Request thứ hai có thể bị coi là reuse và khiến family bị revoke.
- Nếu response thứ nhất bị mất hoặc client không lưu R2, client có thể chỉ còn R1 đã bị tiêu thụ.

Biện pháp phía client:
- Dùng **single-flight refresh**: chỉ một refresh request được thực hiện cho mỗi session/token tại một thời điểm.
- Các request khác chờ kết quả và dùng access token mới.
- Cập nhật token store nguyên tử trước khi giải phóng các request đang chờ.
- Không tự retry vô hạn bằng refresh token cũ sau timeout.
- Nếu response mất sau khi server đã rotate, áp dụng recovery/re-auth theo policy; không giả định server có thể phát lại token mới nếu không có cơ chế idempotency an toàn.

Biện pháp phía server:
- Rotation atomic và có token family.
- Có telemetry phân biệt reuse, duplicate request và lỗi vận hành nếu có đủ tín hiệu.
- Nếu thiết kế grace window hoặc idempotency, phải ràng buộc chặt với client, sender key, request ID và thời gian; tránh tạo cơ hội dùng lại token cũ cho attacker.
- Không dùng grace period rộng như cách chữa mặc định cho race condition.

## 7. Lưu trữ refresh token an toàn

Refresh token có giá trị cao vì có thể tạo access token mới. Cách lưu phụ thuộc loại client.

| Môi trường | Hướng lưu trữ | Rủi ro cần xử lý |
| --- | --- | --- |
| Backend web app/BFF | Server-side session/token store hoặc secret store được bảo vệ | Database dump, log, quyền vận hành, backup, server compromise. |
| SPA trong browser | Ưu tiên Backend-for-Frontend (BFF) để giữ refresh token phía server; nếu kiến trúc browser-only, đánh giá kỹ rotation/sender constraint và nguy cơ XSS | JavaScript có thể đọc localStorage/sessionStorage; XSS có thể đánh cắp token hoặc thực hiện refresh thay người dùng. |
| Mobile app | Secure storage do hệ điều hành cung cấp (Keychain/Keystore hoặc tương đương), bảo vệ thiết bị và backup | Root/jailbreak, malware, backup/restore, thiết bị bị mất. |
| Desktop app | OS credential vault/keychain hoặc cơ chế lưu secret phù hợp nền tảng | Token trong file cấu hình, profile, crash dump và process memory. |
| Service-to-service | Secret manager, workload identity hoặc cơ chế OAuth client phù hợp | Shared secret, quyền rộng, rotation và quản lý vòng đời workload. |

### 7.1. Browser và cookie

Không lưu refresh token dài hạn trong localStorage nếu có thể tránh. JavaScript chạy cùng origin có thể đọc localStorage; XSS có thể lấy token và gửi ra ngoài. Một BFF giữ refresh token ở server và cấp cookie session cho browser thường giảm việc browser trực tiếp giữ refresh token.

Nếu dùng cookie:
- Đặt Secure, HttpOnly, SameSite phù hợp.
- Có CSRF protection cho các request làm thay đổi trạng thái hoặc dùng cookie phiên.
- Không đưa refresh token vào URL.
- Giới hạn cookie theo host/path và thời hạn cần thiết.
- Chống XSS; HttpOnly ngăn đọc cookie nhưng script độc hại vẫn có thể gọi request dưới phiên nạn nhân.

Cookie bảo vệ token khi lưu và truyền theo một số điều kiện, nhưng không tự giải quyết mọi tấn công. BFF cũng cần kiểm tra session, authorization, logout và thu hồi token ở backend.

### 7.2. Không log hoặc telemetry refresh token

Không ghi refresh token vào access log, application log, trace, crash report, analytics, exception hoặc metrics label. Redact header/body token ở proxy, APM và công cụ hỗ trợ. Log token ID/family ID đã chuẩn hóa nếu cần điều tra, không log giá trị bí mật.

## 8. Thời hạn, inactivity và phạm vi grant

Refresh token thường có thời hạn dài hơn access token, nhưng không nên tồn tại vô thời hạn. Policy có thể bao gồm:

- **Absolute lifetime:** thời điểm tối đa từ lúc cấp token/grant, sau đó phải xác thực/ủy quyền lại.
- **Idle/inactivity timeout:** thu hồi nếu không được sử dụng trong một khoảng thời gian.
- **Rotation lifetime:** token cũ hết hiệu lực sau mỗi lần sử dụng; family có thể có thời hạn tổng thể.
- **Grant/session status:** consent bị thu hồi, account bị khóa hoặc session bị chấm dứt thì refresh token không còn hợp lệ.
- **Risk policy:** hoạt động bất thường, thiết bị bị mất hoặc credential bị đổi có thể dẫn tới revoke.
- **Scope/resource restriction:** access token mới không được mở rộng quyền vượt grant ban đầu.

Khi client gửi scope mới trong refresh request, authorization server không được cấp rộng hơn quyền đã được người dùng/authorization grant chấp thuận; nếu scope được gửi, nó phải nằm trong phạm vi được phép theo OAuth. Một refresh token không phải cơ chế xin quyền mới vô hạn.

### 8.1. Token không thay thế quyền nghiệp vụ

Refresh token chỉ giúp xin access token mới. Resource server vẫn phải kiểm tra access token có đúng issuer, audience, thời hạn, scope và các ràng buộc cần thiết. Sau đó API còn phải kiểm tra quyền đối với resource/tenant và hành động cụ thể. Không suy ra “có refresh token” đồng nghĩa với “được quyền làm mọi việc”.

## 9. Revocation, logout và thay đổi trạng thái tài khoản

Refresh token có thể bị revoke khi:
- Người dùng logout hoặc thu hồi consent.
- Người dùng thay đổi mật khẩu, passkey hoặc phương thức MFA trong một sự cố cần chấm dứt phiên cũ.
- Thiết bị bị mất hoặc bị nghi compromise.
- Client bị gỡ bỏ, secret client bị lộ hoặc integration bị dừng.
- Tài khoản bị khóa, xóa hoặc deprovisioned.
- Token family có dấu hiệu reuse hoặc replay.
- Grant/scope bị thay đổi hoặc hết hạn.

OAuth có **revocation endpoint** theo RFC 7009 để client yêu cầu thu hồi token. Authorization server cần áp dụng policy cho token và token liên quan. Một số hệ thống thu hồi refresh token family hoặc grant; access token tự chứa có thể tiếp tục hợp lệ đến khi hết hạn nếu resource server không kiểm tra trạng thái. Vì vậy hãy kết hợp access token ngắn hạn, introspection/revocation hoặc cơ chế session version/denylist khi yêu cầu thu hồi nhanh.

### 9.1. Local logout và federated logout

Logout khỏi ứng dụng có thể:
1. Xóa cookie/session local.
2. Revoke refresh token hoặc grant phía authorization server.
3. Revoke/expire refresh token family.
4. Thu hồi access token nếu kiến trúc hỗ trợ.
5. Điều phối logout với IdP khi ứng dụng dùng OIDC SSO.

Chỉ xóa cookie ở browser không bảo đảm refresh token phía server đã bị revoke. Ngược lại, revoke refresh token không nhất thiết kết thúc ngay mọi access token đã được phát hành. Cần xác định rõ phạm vi logout và thông báo đúng cho người dùng.

### 9.2. Đổi mật khẩu hoặc mất thiết bị

Sau thay đổi credential nhạy cảm, authorization server có thể revoke refresh token/session cũ theo policy. Không phải mọi đổi mật khẩu đều bắt buộc chấm dứt mọi session trong mọi sản phẩm, nhưng hệ thống phải có quyết định rõ dựa trên rủi ro. Với báo mất thiết bị, revoke token family/refresh token gắn với thiết bị đó và xử lý access token còn hiệu lực.

## 10. Sender-constrained refresh token

Bearer token có thể bị sử dụng bởi bất kỳ bên nào lấy được giá trị. **Sender-constrained token** bổ sung ràng buộc với một khóa hoặc client, khiến token chỉ có thể dùng khi request chứng minh sở hữu khóa tương ứng.

Hai cơ chế phổ biến:
- **mTLS-bound token:** ràng buộc token với chứng chỉ client; request tới token/resource endpoint phải chứng minh sở hữu private key tương ứng.
- **DPoP:** client ký một proof JWT gắn với HTTP method, URI, thời điểm, nonce (khi áp dụng) và key; server xác minh proof và ràng buộc token với public key thumbprint.

Sender-constraining có thể giảm tác động token bị sao chép, nhưng không làm token an toàn tuyệt đối: attacker có thể chiếm cả môi trường giữ private key, lạm dụng client đang hoạt động hoặc tấn công ứng dụng. Rotation/reuse detection và bảo vệ storage vẫn cần được đánh giá theo threat model.

## 11. Lỗi refresh và cách xử lý

| Lỗi | Ý nghĩa thường gặp | Cách xử lý |
| --- | --- | --- |
| invalid_grant | Refresh token sai, hết hạn, revoked, đã dùng hoặc grant không còn hợp lệ | Dừng refresh với token đó; xóa token stale; yêu cầu authorization lại theo policy. |
| invalid_client | Client authentication thất bại hoặc client không hợp lệ | Kiểm tra cấu hình client ở server; không retry vô hạn. |
| unauthorized_client | Client không được phép dùng grant này | Kiểm tra registration và policy. |
| invalid_scope | Scope yêu cầu không hợp lệ/vượt grant | Không tự mở rộng scope; yêu cầu consent/authorization phù hợp. |
| temporarily_unavailable / lỗi mạng | Authorization server hoặc đường truyền tạm thời lỗi | Retry có backoff/jitter khi an toàn; không gửi lại token cũ một cách mù quáng sau khi chưa biết rotation đã commit hay chưa. |
| Response timeout sau rotation | Server có thể đã tiêu thụ token cũ nhưng client chưa nhận token mới | Không lặp vô hạn; dùng single-flight, trạng thái client rõ ràng và yêu cầu authorization lại khi không thể phục hồi an toàn. |
| Reuse detected | Token đã tiêu thụ được gửi lại | Revoke family theo policy, ghi audit và yêu cầu xác thực/ủy quyền lại. |

Không hiển thị raw token endpoint response hoặc token trong giao diện. Client cần phân biệt lỗi cần tương tác người dùng với lỗi tạm thời có thể retry. Retry phải có giới hạn, backoff và idempotency/rotation semantics rõ.

## 12. Pseudocode phía client và authorization server

### 12.1. Client: single-flight refresh

~~~text
getValidAccessToken():
    if accessTokenStillValidWithSafetyMargin():
        return currentAccessToken

    acquire refreshLock for this session
    try:
        recheck access token after acquiring lock
        if another request already refreshed:
            return currentAccessToken

        response = callTokenEndpointOnce(
            grant_type="refresh_token",
            refresh_token=currentRefreshToken
        )

        if response success:
            atomicallyPersist(
                accessToken=response.access_token,
                refreshToken=response.refresh_token if returned
            )
            return response.access_token

        if response is invalid_grant:
            clearLocalTokenState()
            requireAuthorizationAgain()
        else:
            handleTransientFailureWithoutBlindReplay()
    finally:
        release refreshLock
~~~

Pseudocode chỉ mô tả điều phối. Trong môi trường nhiều process/device, lock phải phù hợp với cách token store được chia sẻ; mutex trong một process không ngăn hai instance backend cùng refresh một token. Không ghi token vào log khi debug.

### 12.2. Authorization server: kiểm tra refresh grant

~~~text
handleRefreshGrant(request, authenticatedClient):
    presentedToken = request.refresh_token
    tokenRecord = lookupBySecureVerifier(presentedToken)

    if tokenRecord missing:
        return invalid_grant

    if tokenRecord.status == consumed:
        revokeTokenFamily(tokenRecord.familyId)
        audit("refresh_token_reuse_detected", tokenRecord.id)
        return invalid_grant

    require tokenRecord.status == active
    require tokenRecord.clientId == authenticatedClient.id
    require tokenRecord.grant.status == active
    require tokenRecord.notExpired
    require senderProofValidIfRequired(request, tokenRecord)

    scope = validateRequestedScopeWithinGrant(request.scope, tokenRecord.grant)
    atomically:
        consume(tokenRecord)
        nextRefreshToken = createRandomToken()
        persistNextTokenInSameFamily(nextRefreshToken, tokenRecord.familyId)
        updateFamilyCurrentToken(nextRefreshToken)

    accessToken = issueAccessToken(
        subject=tokenRecord.subject,
        audience=allowedResource(request, tokenRecord.grant),
        scope=scope,
        expiry=shortLifetime
    )
    return accessToken + nextRefreshToken
~~~

Đây là logic khái niệm. Trong triển khai, phải xác minh dữ liệu đầu vào, ràng buộc database, transaction và audit một cách rõ ràng. Token secret có thể được lưu dưới dạng verifier/hash; server không cần lưu token rõ để tra cứu.

## 13. Bài thực hành: thiết kế refresh token cho StudyHub

**Bối cảnh:** StudyHub có web app dùng BFF, mobile app và API. Access token có thời hạn ngắn; refresh token được cấp cho grant đọc tài liệu và hồ sơ. Giảng viên có thể truy cập dữ liệu điểm; quản trị viên có quyền nhạy cảm hơn. Ứng dụng hỗ trợ logout, thu hồi consent và đăng nhập passkey/MFA qua OIDC.

### 13.1. Quyết định thiết kế

Hãy lập bảng policy cho:
- Client type (confidential/public) và cách xác thực client.
- Refresh token có được cấp không; grant và scope tương ứng.
- Rotation bật ở đâu, token family lưu thế nào và reuse xử lý ra sao.
- Absolute lifetime, inactivity timeout và thời gian access token.
- Lưu token ở BFF, mobile secure storage và browser.
- Xử lý đồng thời, timeout sau rotation và retry.
- Logout, đổi mật khẩu, mất thiết bị, deprovisioning và consent revocation.
- Có cần sender-constrained token bằng DPoP hoặc mTLS không.

### 13.2. Bộ ca kiểm thử chấp nhận

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Refresh token hợp lệ, đúng client và grant | Cấp access token mới; rotation phát hành refresh token mới nếu policy bật. |
| Refresh token hết hạn hoặc revoked | Trả lỗi phù hợp; không cấp access token. |
| Refresh token của client A dùng tại client B | Bị từ chối. |
| Refresh token gửi tới resource server | API từ chối; refresh token chỉ được gửi tới token endpoint. |
| Refresh token cũ dùng lại sau rotation | Phát hiện reuse và revoke family theo policy. |
| Hai request đồng thời refresh cùng token | Client single-flight; server atomic; không tạo hai nhánh token hợp lệ. |
| Response timeout sau khi server đã rotate | Client không retry mù quáng bằng token cũ; xử lý trạng thái theo policy hoặc yêu cầu authorization lại. |
| Scope refresh rộng hơn grant ban đầu | Bị từ chối hoặc chỉ cấp phạm vi không vượt grant. |
| Client secret của public app được gửi | Không được xem là xác thực client đáng tin; áp policy public client. |
| Logout local | Session local bị vô hiệu; refresh token/grant được revoke theo yêu cầu đã công bố. |
| Mất thiết bị | Token family/phiên liên quan bị thu hồi; access token còn hiệu lực được xử lý theo policy. |
| Tài khoản bị deprovisioned | Refresh grant không còn hợp lệ; không phát access token mới. |
| Sender-constrained proof sai hoặc thiếu | Token endpoint từ chối. |
| Refresh token xuất hiện trong log | Kiểm thử thất bại; hệ thống phải redact. |
| Reuse bị phát hiện | Có audit event; người dùng được yêu cầu xác thực/ủy quyền lại. |
| ID token được gửi như refresh token | Bị từ chối do sai loại token/grant. |

### 13.3. Câu hỏi tự đánh giá

1. Vì sao refresh token có giá trị cao hơn access token trong nhiều kiến trúc?
2. Refresh token có được gửi tới resource server không? Vì sao?
3. Rotation và reuse detection hoạt động thế nào?
4. Vì sao cần token family thay vì chỉ lưu token hiện tại?
5. Điều gì xảy ra nếu hai request đồng thời cùng refresh một token?
6. Vì sao timeout sau khi server rotate nguy hiểm cho retry?
7. BFF giúp giảm rủi ro nào khi browser sử dụng refresh token?
8. Logout khỏi ứng dụng có tự động thu hồi mọi access token không?
9. Sender-constrained token khác bearer token ra sao?
10. Vì sao một JWT refresh token có chữ ký hợp lệ vẫn cần trạng thái thu hồi/rotation trong nhiều hệ thống?

**Tiêu chí hoàn thành:** Người học có thể vẽ refresh grant, xác định đúng nơi token được gửi, giải thích token family và reuse detection, xử lý concurrency/timeout, bảo vệ token storage và chứng minh bằng test rằng token hết hạn, bị thu hồi hoặc bị replay không tạo access token mới.

## 14. Vận hành và giám sát

Các sự kiện nên theo dõi:
- Refresh thành công/thất bại theo client, grant và token family ID.
- Token family bị revoke và lý do (logout, reuse, account disabled, incident).
- Tỷ lệ reuse detected và refresh failure bất thường.
- Tần suất refresh, độ tuổi token và inactivity.
- Request refresh đồng thời hoặc retry tăng đột biến.
- Thiết bị/client mới dùng refresh token.
- Thay đổi scope/consent, credential, MFA và trạng thái tài khoản.
- Thời gian từ yêu cầu revoke tới khi access token không còn được chấp nhận theo thiết kế.

Audit chỉ lưu token ID/family ID đã chuẩn hóa, client ID, subject nội bộ, thời gian, kết quả và lý do. Không log refresh token, access token, ID token hoặc client secret. Hạn chế quyền truy cập log và thiết lập retention theo chính sách.

Khi phát hiện reuse, có thể cần revoke family, đánh dấu phiên nghi ngờ, thông báo người dùng, yêu cầu authorization lại và điều tra nguồn lộ. Đội vận hành cần phân biệt token theft với lỗi concurrency/retry để giảm false positive, nhưng không được âm thầm chấp nhận token cũ vô thời hạn.

## 15. Tài liệu nên đọc tiếp

- **RFC 6749 — OAuth 2.0 Authorization Framework**: refresh token grant và quy tắc scope.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security**: bảo vệ refresh token cho public client, rotation, sender-constraining và phát hiện replay.
- **RFC 7009 — OAuth 2.0 Token Revocation**: thu hồi token.
- **OpenID Connect Core**: phân biệt ID token, access token và refresh token trong OIDC.
- **OAuth 2.0 Security Best Current Practice / OAuth browser-based apps guidance**: lưu trữ token và mô hình BFF.
- **OWASP OAuth 2.0 Cheat Sheet và ASVS**: chuyển các yêu cầu thành kiểm soát và test.

Khi triển khai thật, hãy xác định loại client, grant, token audience, scope, thời hạn, rotation semantics và cách thu hồi trước khi chọn thư viện. **Refresh token chỉ nên được chấp nhận tại authorization server, trong đúng grant và client đã được cấp; rotation hoàn tất khi token cũ không thể tiếp tục tạo access token và hành vi đó được kiểm chứng.**
