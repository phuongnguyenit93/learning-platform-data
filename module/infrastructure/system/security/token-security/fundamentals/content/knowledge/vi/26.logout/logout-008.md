# Logout sau đổi mật khẩu

**Logout sau đổi mật khẩu** là chính sách kết thúc hoặc yêu cầu xác thực lại các **phiên và credential còn tồn tại** sau khi người dùng thay đổi mật khẩu. Đây không chỉ là thao tác xóa cookie trên trang đang mở: một tài khoản có thể đồng thời có phiên trình duyệt, ứng dụng mobile, refresh token, access token JWT, thiết bị đã liên kết, phiên SSO tại OpenID Provider (OP) và các client được ủy quyền OAuth 2.0.

Bài học thuộc chương **Logout** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, vận dụng mô hình tin cậy và vòng đời token, phân biệt JWT/opaque token, access/refresh/ID token, xác thực, phân quyền OAuth 2.0/OIDC, claims, scope, audience, lưu trữ, thu hồi và chống token bị đánh cắp hoặc phát lại.

**Mục tiêu:** sau khi đổi mật khẩu thành công, hệ thống không để **các phiên được xem là không còn đáng tin** tiếp tục tạo token mới hoặc sử dụng đặc quyền. Chính sách phải nêu rõ **giữ hay đăng xuất phiên hiện tại**, **đăng xuất những thiết bị khác**, **thu hồi refresh-token family/grant nào**, và **khi nào Resource Server thực sự ngừng chấp nhận access token đã cấp**.

> **Nguyên tắc cốt lõi:** việc cập nhật `password_hash` chỉ làm thay đổi bí mật để xác thực **ở lần đăng nhập tiếp theo**. Nó **không tự động** vô hiệu cookie session, refresh token hay JWT access token đã phát hành. Muốn “logout sau đổi mật khẩu” có hiệu lực, phải có **chính sách session/token invalidation, nguồn trạng thái đáng tin và cơ chế thực thi xuyên các thành phần**.

## 1. Vì sao đổi mật khẩu nhưng phiên cũ vẫn có thể hoạt động?

Nhiều hệ thống đăng nhập bằng mật khẩu **chỉ một lần**, sau đó dùng session hoặc token thay cho việc kiểm tra mật khẩu mỗi request:

~~~text
Login bằng mật khẩu
    |
    +-- Web session cookie S1 -----------------> Web backend
    |
    +-- OAuth refresh token RT0 ---------------> AS /token
    |       |
    |       +-- AT0, AT1, ... ------------------> Resource Server
    |
    +-- App mobile session S2 -----------------> Mobile backend
    |
    +-- OP SSO browser session ----------------> OpenID Provider

User đổi mật khẩu:
    password_hash: H_old -> H_new

Nếu không có logic revoke/check:
    S1/S2 vẫn có thể active
    RT0 vẫn có thể xin AT mới
    AT0/AT1 có thể tiếp tục gọi API tới exp
    OP SSO session có thể tiếp tục hoạt động
~~~

Điều này không nhất thiết là **lỗi của hàm đổi mật khẩu**; đó là hệ quả của cách các credential đã được phát hành. Nhưng nếu sản phẩm cam kết **“đổi mật khẩu sẽ đăng xuất thiết bị cũ”**, mà chỉ sửa hash thì cam kết bảo mật **không đúng thực tế**.

### Ba mức hành động khác nhau

| Mức | Tác dụng | Chưa giải quyết |
|---|---|---|
| **Đổi mật khẩu** | Mật khẩu cũ không dùng được để xác thực mật khẩu mới | Existing sessions/RT/AT |
| **Thu hồi phiên và refresh token** | Ngăn session cũ và grant/family cũ tạo AT mới | AT đã cấp nếu RS còn tin offline |
| **Chặn access token đang lưu hành tại RS** | Chặn API request dùng AT thuộc phạm vi revoke | Cần introspection/denylist/version/event hoặc chờ `exp` |

Không gộp các mức này vào một cờ `password_changed=true` mà không thiết kế rõ **bên nào kiểm tra cờ và kiểm tra khi nào**.

## 2. Phân biệt đổi mật khẩu và đặt lại mật khẩu

Hai luồng thường có **mức tin cậy khác nhau**:

| Trường hợp | User đã chứng minh điều gì? | Chính sách logout thường nên cân nhắc |
|---|---|---|
| **Change password** trong phiên đã xác thực, nhập mật khẩu hiện tại | Có thể chứng minh biết mật khẩu cũ; vẫn phải xét tính mới của authentication và rủi ro phiên | Revoke **other sessions**; giữ current session **chỉ nếu** vừa xác thực lại/step-up và policy cho phép |
| **Change password** trong phiên lâu ngày, chỉ dựa cookie | Chỉ có session cookie có thể bị chiếm | **Yêu cầu reauthentication** (mật khẩu/MFA/passkey tùy cấu hình) trước đổi |
| **Forgot password / recovery reset** qua email/link/OTP | Chứng minh quyền sử dụng recovery channel theo mức bảo đảm riêng, chưa chắc kiểm soát tất cả phiên cũ | Thường revoke **all existing sessions/refresh tokens**, yêu cầu login mới |
| **Admin-enforced reset / suspected account takeover** | Có sự kiện security/incident | Revoke rộng hơn: sessions, refresh-token families, AT liên quan, đánh giá linked devices và OP/IdP |
| **Mật khẩu bị cập nhật bởi IdP bên ngoài** | RP có thể không tự xác minh được sự kiện nếu thiếu signal | Cần IdP/session event hoặc kiểm tra phiên tương ứng; không tự phỏng đoán |

**Không có một quy định OAuth/OIDC chung bắt mọi dịch vụ phải “logout toàn bộ thiết bị” sau *mọi* lần đổi mật khẩu.** Đây là **policy an ninh của sản phẩm**, nên phù hợp độ nhạy cảm của hệ thống, bối cảnh tài khoản và yêu cầu người dùng. Tuy nhiên, đối với **recovery reset hoặc suspected compromise**, tiếp tục giữ mọi phiên cũ thường đi ngược mục tiêu phục hồi tài khoản.

### Hành vi an toàn cho sản phẩm nhạy cảm

- Đổi mật khẩu tự nguyện: **xác thực lại**, thu hồi các phiên khác, yêu cầu xác nhận mức mạnh cho việc giữ phiên hiện tại, cung cấp tùy chọn “đăng xuất tất cả”.
- Đặt lại vì quên mật khẩu hoặc có dấu hiệu tài khoản bị chiếm: **thu hồi tất cả phiên cũ**, bắt đầu phiên xác thực mới (và MFA/step-up khi cần).
- Mỗi phương án phải được **ghi thành hành vi có thể kiểm thử**, không chỉ nhắn “Mật khẩu đã cập nhật”.

## 3. Mô hình tin cậy: những nơi cần tác động

~~~mermaid
flowchart LR
    U["User đổi mật khẩu"]
    APP["Account / Identity service"]
    DB[("User credential + auth epoch")]
    SES[("Web / mobile session store")]
    AS["OAuth Authorization Server"]
    RT[("Refresh-token family store")]
    OUTBOX[("Revocation event outbox")]
    RS["Resource Servers"]
    OP["OIDC Provider / SSO"]
    RP["OIDC Relying Parties"]

    U -->|"Reauthenticate + change"| APP
    APP -->|"Update password hash + bump epoch"| DB
    APP -->|"Revoke scoped sessions"| SES
    APP -->|"Revoke family/grants"| AS
    AS --> RT
    APP -->|"Publish commit-aware events"| OUTBOX
    OUTBOX -->|"Invalidate denylist/cache"| RS
    APP -.->|"Nếu cùng chủ sở hữu/được tích hợp"| OP
    OP -.->|"Back-channel logout khi áp dụng"| RP
~~~

Đường nét đứt là **tích hợp tùy kiến trúc**, không có chuyện một RP đổi mật khẩu trong database riêng rồi tự động điều khiển mọi OP hoặc client bên thứ ba.

### Phân công trách nhiệm

- **Account/Identity service:** xác minh user, cập nhật hash, phát security event và quyết định phạm vi phiên.
- **Session service/BFF:** vô hiệu session ID/cookie hoặc kiểm tra version tại mỗi protected request.
- **Authorization Server:** từ chối refresh-token families/grants đã revoke, không cấp token mới từ credential cũ.
- **Resource Server:** kiểm tra access token, issuer, audience, scope, expiry và **revocation/epoch** nếu có yêu cầu chặn trước `exp`.
- **OP/SSO/RPs:** xử lý logout/reauthentication bằng cơ chế OIDC khi các bên được tích hợp và cấu hình phù hợp.
- **User-facing app:** thông báo phạm vi logout thực tế, dọn local token/cookie, hướng dẫn login lại.

## 4. Session cookie, access token, refresh token và ID token khác nhau

| Credential | Được dùng ở đâu? | Sau đổi mật khẩu cần làm gì? |
|---|---|---|
| **Session cookie** | Browser → ứng dụng/RP/BFF | Revoke session server-side hoặc bắt buộc reauthentication; xóa cookie trên browser đang có |
| **Access token JWT** | Client → RS phù hợp audience | Giới hạn bằng TTL hoặc chủ động revoke qua denylist/epoch introspection nếu cần |
| **Opaque access token** | Client → RS; RS introspect | AS chuyển `active:false` theo policy khi token/grant revoked; xử lý cache |
| **Refresh token** | Client → AS token endpoint | Revoke grant/family, dừng rotate/refresh từ phiên cũ |
| **OIDC ID token** | OP → RP để xác minh authentication | Không dùng làm API token; session RP đã tạo từ ID token cần logout theo policy |
| **Authorization code / PKCE verifier** | Authorization flow đang pending | Hủy các pending flows gắn phiên cũ, không tiếp tục hoàn tất login từ context không còn tin |
| **Device code / user code** | Device Grant đang pending | Hủy pending device authorizations khi phù hợp, ngăn approve/issue từ context cũ |

Một **JWT có chữ ký hợp lệ** vẫn có thể là access token bị revoke về mặt nghiệp vụ; RS kiểm tra chữ ký offline **không tự biết** trạng thái mới. Một **refresh token** bị xóa khỏi thiết bị hiện tại **không bảo đảm** bản sao attacker đã lấy không còn dùng được; AS phải revoke ở server.

## 5. Chính sách phạm vi: current, other sessions hay toàn bộ?

Giả sử user có:

~~~text
Account U42
├── Browser Chrome thiết bị A    session S-A, RT family F-A
├── Mobile iOS thiết bị B        session S-B, RT family F-B
├── Browser Firefox thiết bị C   session S-C, RT family F-C
└── Third-party OAuth client D   grant G-D, RT family F-D
~~~

Có nhiều lựa chọn:

| Policy | Sau change password thành công | Khi phù hợp |
|---|---|---|
| **KEEP_CURRENT_REVOKE_OTHERS** | Giữ S-A sau reauth mạnh/rotate session ID, revoke S-B/S-C và các families liên quan; G-D theo policy | Trải nghiệm phù hợp với user đổi mật khẩu tự nguyện |
| **REVOKE_ALL** | Revoke cả S-A/S-B/S-C, các family/grants trong phạm vi, yêu cầu user login mới | Reset qua recovery, nghi xâm nhập, sản phẩm nhạy cảm |
| **REVOKE_ALL_AND_CONNECTED_GRANTS** | Như trên, kể cả các third-party grants liên quan được phép thu hồi | Khi nguy cơ token bị lộ rộng hoặc user chọn revoke mọi ứng dụng |
| **RISK_BASED** | Phạm vi theo incident/risk và điều kiện xác thực mới | Phải audit được lý do và không tự hạ cấp khi rủi ro cao |

**Không đồng nhất “tất cả thiết bị” với “tất cả ứng dụng OAuth/consent”** nếu người dùng không được thông báo. Thu hồi grant bên thứ ba có thể gây gián đoạn tích hợp không mong muốn; nhưng trong sự cố account takeover, thu hồi rộng có thể là cần thiết.

### Phiên hiện tại có thật sự an toàn hơn?

Nếu attacker đang chiếm **session cookie hiện tại**, giữ nó chỉ vì user nhập mật khẩu mới có thể để attacker tiếp tục sử dụng phiên. Muốn giữ current session an toàn:

1. Xác minh lại user bằng **phương thức phù hợp** trước thao tác.
2. Cân nhắc **step-up MFA/passkey** và đánh giá thiết bị/risk.
3. **Rotate session identifier** sau sự kiện bảo mật để giảm session fixation.
4. Bind phiên mới vào **credential epoch mới** và không để token/phiên cũ mặc nhiên được nâng quyền.

## 6. Bước đổi mật khẩu phải an toàn trước khi logout

**Logout không sửa được lỗ hổng đổi mật khẩu.** Endpoint thay mật khẩu cần chống CSRF, session hijack và account enumeration trước khi thay hash.

### Với change password của user đang đăng nhập

- Xác định user từ **phiên đã xác thực**, không dùng `user_id` trong body để chọn tài khoản khác.
- Áp dụng **recent authentication/reauthentication** cho hành động nhạy cảm, ví dụ xác minh mật khẩu hiện tại hoặc passkey/MFA theo policy.
- Nếu sản phẩm dùng **password hiện tại**, so khớp bằng password hashing scheme an toàn (Argon2id, scrypt hoặc lựa chọn hiện hành được hỗ trợ), **không so plain text**.
- Áp dụng password policy/denylist phù hợp, tránh yêu cầu đổi quá thường xuyên không có lý do, không log password cũ/mới.
- POST với CSRF protection cho browser cookie session; API dựa bearer cần chống XSS/token theft và các rủi ro riêng.
- Có rate limit, anti-automation, secure telemetry và cảnh báo bất thường.
- Chỉ báo thành công **sau khi hash và session/token revocation policy đã commit hoặc được bảo đảm theo hợp đồng**.

### Với forgot password / reset

- Dùng recovery token **ngắn hạn, entropy mạnh, single-use**, lưu an toàn và chỉ chấp nhận qua endpoint chính thức.
- Không cho email/phone recovery yếu tự động chứng minh quyền với mọi user profile.
- Sau reset, **không tự đăng nhập vào một phiên mức bảo đảm cao** nếu không có chính sách xác thực tương đương; thường yêu cầu đăng nhập mới.
- Không để link reset bị log/referrer/leak, và luôn invalidation reset tokens đã dùng.
- Thực hiện chính sách revoke các phiên cũ theo rủi ro, không chỉ thay password hash.

**Passwordless/federated account:** nếu ứng dụng không sở hữu mật khẩu, đừng tự tạo nút “đổi mật khẩu tại RP” rồi hứa thu hồi session OP. Chỉ IdP/OP kiểm soát credential gốc mới có quyền đổi nó; RP phải dựa trên tín hiệu/tích hợp được thiết kế.

## 7. Trình tự Change Password → Logout có thể quan sát được

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User trên browser A
    participant B as Web / BFF
    participant ID as Identity Service
    participant DB as Credential DB
    participant S as Session Store
    participant AS as Authorization Server
    participant RS as Resource Server

    U->>B: POST /account/password (reauth + CSRF)
    B->>ID: Verify current principal + recent auth
    ID->>DB: Verify expected credential epoch + update hash
    ID->>DB: Bump auth_epoch; commit security state
    ID->>S: Revoke sessions trong phạm vi policy
    ID->>AS: Revoke related refresh-token families/grants
    ID-->>B: Completed / session action theo policy
    B-->>U: Thông báo đổi mật khẩu + trạng thái đăng xuất
    Note over S,AS: Các mutation cần giao dịch/bù trừ + epoch gating
    U->>B: Request bằng session B cũ
    B->>S: Check revoked/epoch
    S-->>B: REJECT
    B-->>U: 401 / yêu cầu đăng nhập lại
    U->>RS: Request bằng access JWT cũ
    RS->>RS: Signature, expiry, epoch/denylist nếu áp dụng
    RS-->>U: 401 nếu đã revoke nhìn thấy; nếu JWT offline có thể đến exp
~~~

Sơ đồ thể hiện **mục tiêu nghiệp vụ**, không cam kết một SQL transaction phân tán tự động bao trùm tất cả hệ thống. Với Identity DB, session store, AS và RS ở các dịch vụ khác nhau, cần **nguồn sự thật và quy tắc nhất quán**: epoch/version gating, outbox/invalidation, reliable retry và fail-closed.

## 8. Auth epoch / session version: cách chặn phiên cũ

Một phương pháp phổ biến là giữ phiên bản trạng thái xác thực của tài khoản:

~~~text
users:
  user_id             = U42
  password_hash       = ...
  auth_epoch          = 12
  password_changed_at = ...

sessions:
  session_id          = S-A
  user_id             = U42
  issued_auth_epoch   = 12
  revoked_at          = null

password change:
  users.auth_epoch = 13

next request using old S-A:
  session.issued_auth_epoch == 12
  user.auth_epoch == 13
  => REJECT, dù cookie session còn tồn tại
~~~

**`auth_epoch` là biến thiết kế nội bộ**, không phải claim bắt buộc theo OIDC, RFC 6749 hoặc RFC 9068. Một số hệ thống dùng `token_version`, `security_stamp`, `password_changed_at` hay `not_before_for_user`. Ý tưởng là **một dấu hiệu chung để từ chối credentials phát hành trước sự kiện bảo mật**.

### Tại sao epoch tốt hơn chỉ xóa session rows?

Nếu một request bắt đầu trước khi process revoke hoàn tất, nó có thể đã đọc session từ cache. Khi kiểm tra epoch **từ nguồn đủ mới**, server có thể từ chối session cũ dù row chưa bị xóa.

Tuy nhiên:

- **Cache epoch stale** có thể tạo cửa sổ chấp nhận cũ.
- RS verify JWT offline **không tự đọc epoch mới**.
- Nếu cho phép giữ current session, không đơn giản tăng `issued_auth_epoch` của session cũ **mà không reauthentication/rotate session ID**.
- **Một request đã được authorize trước khi epoch tăng** có thể đang xử lý dở; không có cơ chế thu hồi thần kỳ những side effects đã commit.
- Version check cần diễn ra **ở bước kiểm tra authn/authz đủ gần thời điểm hành động**, đặc biệt đối với mutation nhạy cảm.

### Epoch nên áp dụng cho đối tượng nào?

Có thể tách:

- **`credential_epoch`** ở account: mọi credential từ trước sự kiện bị buộc kiểm tra lại.
- **`session_epoch`** ở từng session/device: logout một thiết bị mà không chặn thiết bị khác.
- **`grant_version`** ở authorization grant: revoke một app hoặc refresh family.
- **`policy_version`** ở RS: quyền/scope/object policy cập nhật theo lifecycle.

Không phải càng nhiều version càng tốt; hãy định nghĩa **nơi tăng, nơi so sánh, thứ tự commit và TTL cache** cho từng cái.

## 9. PostgreSQL: cập nhật hash và tạo sự kiện thu hồi

Mô hình gợi ý để phục vụ **REVOKE_ALL**. Cấu trúc dưới đây là **pseudocode SQL PostgreSQL**, không phải migration/mẫu giao dịch đã đầy đủ các ràng buộc:

~~~sql
-- Giả sử app đã reauthenticate và kiểm tra password policy.
-- :new_hash được tạo ở ứng dụng bằng password hasher tin cậy.
-- :expected_epoch được đọc từ snapshot xác thực và đối chiếu dưới lock.
BEGIN;

SELECT credential_epoch
FROM user_accounts
WHERE user_id = :trusted_user_id
FOR UPDATE;

-- Nếu epoch không bằng :expected_epoch, rollback và yêu cầu
-- kiểm tra lại trạng thái/thực hiện lại xác thực, không ghi đè mù.
UPDATE user_accounts
SET password_hash = :new_hash,
    credential_epoch = credential_epoch + 1,
    password_changed_at = CURRENT_TIMESTAMP
WHERE user_id = :trusted_user_id
  AND credential_epoch = :expected_epoch
RETURNING credential_epoch;

-- Require exactly 1 row; nếu không ROLLBACK.
UPDATE app_sessions
SET revoked_at = CURRENT_TIMESTAMP,
    revoke_reason = 'PASSWORD_CHANGED'
WHERE user_id = :trusted_user_id
  AND revoked_at IS NULL;

UPDATE refresh_families
SET status = 'REVOKED',
    revoked_at = CURRENT_TIMESTAMP,
    revoke_reason = 'PASSWORD_CHANGED'
WHERE user_id = :trusted_user_id
  AND status = 'ACTIVE';

INSERT INTO security_outbox
    (event_id, user_id, event_type, created_at)
VALUES
    (:event_uuid, :trusted_user_id,
     'AUTH_CREDENTIAL_EPOCH_CHANGED', CURRENT_TIMESTAMP);

COMMIT;

-- Worker gửi durable outbox event sau commit,
-- cập nhật RS caches/denylist và hệ thống liên quan.
~~~

**Giới hạn của ví dụ:**

1. Giao dịch trên chỉ bảo đảm atomicity khi **các bảng thực sự cùng database/transaction**; AS/RS bên ngoài cần **event/outbox/retry hoặc API đồng bộ có thiết kế**.
2. **Không gửi token response/session success trước khi commit.**
3. User ID phải được xác định từ **verified principal**, không lấy trực tiếp từ HTTP body.
4. Reauthentication và hash computation nên được thiết kế tránh **giữ DB lock trong thời gian Argon2/scrypt quá dài**; xác minh trước và dùng epoch/CAS + kiểm tra lại dưới lock.
5. Mọi luồng **tạo session hoặc cấp refresh token** cũng cần ghi **đúng epoch và kiểm tra source-of-truth** để không tạo phiên epoch cũ sau khi password change commit.
6. Nếu giữ current session, phải có **transition riêng** tạo session mới hoặc rotate ID sau reauth mạnh; không dùng query REVOKE_ALL như trên.
7. User sessions/refresh families có thể nằm ở nhiều datastore: cần định nghĩa **failure/retry** và epoch gating để không có cửa sổ cấp token ngoài ý muốn.
8. Nhánh lỗi phải rollback, không phát event “đổi mật khẩu thành công”.

## 10. Race condition: đổi mật khẩu cùng lúc refresh token

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Mobile / attacker
    participant AS as Authorization Server
    participant DB as Credential + grant state
    participant Web as Password-change service

    App->>AS: Refresh RT7 (epoch 12)
    Web->>DB: Change password, bump epoch 12->13
    DB-->>Web: Commit epoch 13
    Web->>AS: Revoke refresh family F7
    AS->>DB: Read family epoch/grant state
    DB-->>AS: Epoch mismatch hoặc REVOKED
    AS-->>App: invalid_grant, không cấp RT/AT mới
~~~

**Khó khăn:** nếu refresh token request bắt đầu **trước** password change commit, thứ tự commit và mức consistency quyết định nó có thể thành công hay không. Để có bảo đảm rõ ràng:

- Các bước refresh và đổi mật khẩu **phải đồng thuận trên cùng credential/grant epoch hoặc khóa trạng thái**.
- Nếu refresh commit trước password change, token vừa cấp được coi là credential thuộc epoch cũ và **phải bị policy revoke/check chặn** sau đó.
- Nếu refresh kiểm tra epoch **sau** password change commit, request cũ phải bị từ chối.
- Nếu refresh tạo RT mới trong region khác dựa trên cache stale, cần **strong consistency, home-region routing hoặc cơ chế fencing/version**.
- Sự kiện revoke cần **idempotent**; xử lý lại cùng event không được tạo family mới hoặc tăng version vô hạn.

### Không chỉ dựa vào “xóa tất cả RT đang tồn tại”

Khi password change chạy lệnh `UPDATE refresh_families ... REVOKED`, một request refresh khác có thể tạo family/token **sau** câu lệnh cập nhật nếu không dùng epoch/binding chung. Đây là **race issuance-vs-revoke**. Quy tắc “mỗi token/session mang epoch được xác minh ở AS/RS” giúp chặn những credential bị phát dưới epoch cũ, nhưng cần **tất cả luồng phát hành** kiểm tra epoch nhất quán.

## 11. Java 17: policy quyết định logout sau đổi mật khẩu

Đoạn Java chuẩn JDK minh họa **decision model**; nó không tự cập nhật password DB, không gọi AS và không thay Spring Security. Mục tiêu là **biểu diễn chính sách rõ ràng** để test.

~~~java
import java.util.Objects;

public final class PasswordChangeLogoutPolicy {
    public enum EventType {
        SELF_SERVICE_CHANGE,
        RECOVERY_RESET,
        ADMIN_FORCED_RESET,
        SUSPECTED_COMPROMISE
    }

    public enum SessionAction {
        KEEP_REAUTHENTICATED_CURRENT_REVOKE_OTHERS,
        REVOKE_ALL
    }

    public record Context(
            EventType event,
            boolean recentStrongReauthentication,
            boolean knownCurrentSession,
            boolean highRisk
    ) {
        public Context {
            Objects.requireNonNull(event);
        }
    }

    public record Decision(
            SessionAction sessionAction,
            boolean revokeRefreshFamilies,
            boolean requireNewLogin,
            boolean triggerSecurityNotification
    ) {}

    public static Decision decide(Context c) {
        boolean recoveryOrIncident =
                c.event() == EventType.RECOVERY_RESET
                || c.event() == EventType.ADMIN_FORCED_RESET
                || c.event() == EventType.SUSPECTED_COMPROMISE;

        if (recoveryOrIncident || c.highRisk()
                || !c.recentStrongReauthentication()
                || !c.knownCurrentSession()) {
            return new Decision(
                    SessionAction.REVOKE_ALL,
                    true,
                    true,
                    true
            );
        }

        // Chỉ áp dụng nếu current session đã được reauthenticate.
        return new Decision(
                SessionAction.KEEP_REAUTHENTICATED_CURRENT_REVOKE_OTHERS,
                true,  // Revoke old families; issue new under new epoch.
                false, // Current session có thể tiếp tục SAU rotate/rebind.
                true
        );
    }

    public static void main(String[] args) {
        System.out.println(decide(new Context(
                EventType.SELF_SERVICE_CHANGE, true, true, false
        )));
        System.out.println(decide(new Context(
                EventType.RECOVERY_RESET, false, false, true
        )));
    }

    private PasswordChangeLogoutPolicy() {}
}
~~~

**Không lấy `recentStrongReauthentication` hoặc `highRisk` từ boolean user tự gửi**. Các tín hiệu phải do authentication/risk subsystem tin cậy đánh giá từ session và sự kiện bảo mật. `revokeRefreshFamilies=true` ở nhánh giữ current có nghĩa **các family cũ** bị revoke; nếu cần current session dùng API tiếp, backend phải tạo **credential/session mới dưới epoch mới** theo flow đã xác thực, không khôi phục RT đã revoked.

### Cần kiểm thử policy

- `RECOVERY_RESET` luôn REVOKE_ALL trong chính sách ví dụ.
- `SELF_SERVICE_CHANGE` chỉ KEEP_CURRENT khi reauthentication mới, current session xác minh được và không high-risk.
- Nếu session hiện tại bị nghi chiếm, REVOKE_ALL kể cả user đã đăng nhập lâu trước đó.
- Không để client request override kết quả chính sách bằng `keepAllSessions=true`.

## 12. Session invalidation thực tế tại web backend

Chỉ xóa cookie trên browser A **không logout browser B**. Hệ thống phải:

1. Đánh dấu session **REVOKED** trong session repository đáng tin hoặc tăng credential/session epoch được check mỗi request.
2. Nếu policy giữ current session, **rotate session ID** và tạo context theo epoch mới sau recent authentication.
3. Nếu policy REVOKE_ALL, vô hiệu cả current session, xóa cookie trên response browser đang xử lý và yêu cầu login mới.
4. Với các browser khác, không thể đẩy `Set-Cookie` trực tiếp đến browser đang offline; **server-side session revocation** khiến cookie cũ vô dụng khi được gửi lại.
5. Nếu dùng sticky sessions, Redis/shared session store hoặc nhiều app instances, mọi instance cần nhìn cùng revocation status.

Ví dụ HTTP response minh họa khi buộc current browser logout:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Set-Cookie: __Host-session=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0

{
  "password_changed": true,
  "session_action": "REAUTHENTICATION_REQUIRED"
}
~~~

**Set-Cookie không thu hồi các phiên khác.** Cookie name/domain/path phải khớp cấu hình thực tế. Prefix `__Host-` có yêu cầu riêng (Secure, Path=/ và không có Domain); cookie trên chỉ là minh họa. Response thành công phải được gửi **sau** khi trạng thái server-side đã commit an toàn.

### Spring Security servlet cần gì?

Với Spring Security/Spring Session:

- Dùng session repository hoặc SessionRegistry tương ứng với deployment để revoke session ID theo account; **một in-memory registry ở một JVM không đủ cho cluster**.
- Với logout current session, `SecurityContextLogoutHandler` có thể clear security context và invalidate HttpSession; nó **không tự revoke RT family ở AS**.
- Với session version, thêm filter/authorization hook đọc **trusted auth epoch** và so với epoch gắn với principal/session; đừng chỉ check một lần lúc login.
- Password change không tự đồng nghĩa framework gọi logout của mọi thiết bị. Cần orchestration theo policy.
- Cấu hình session fixation protection, CSRF, logout response và transactional event delivery đúng phiên bản framework đang dùng.

**Ví dụ cấu hình không thay thế việc xác minh các thao tác revoke của hệ thống cụ thể.**

## 13. Refresh-token families: thu hồi đúng chuỗi quyền

Khi một ứng dụng dùng refresh-token rotation:

~~~text
Grant G-A, device A:
    RT0 -> RT1 -> RT2 (current tip)

Password change / reset với policy revoke G-A:
    family G-A status = REVOKED
    RT2 không thể đổi access token mới
    RT0/RT1 đã USED vẫn bị từ chối

Lần thử refresh tiếp:
    POST /token refresh_token=RT2
    => invalid_grant (hoặc error theo AS profile)
~~~

**Không chỉ revoke RT0 hoặc xóa RT khỏi local storage**. AS phải biết **family/grant** đã bị revoke và không cho active tip tiếp tục rotate.

### Khi có nhiều family

- Logout this device: có thể chỉ revoke family gắn session/device đó.
- Password reset high-risk: thường cần revoke **mọi family nằm trong security scope**.
- Đổi mật khẩu tự nguyện với KEEP_CURRENT: revoke family cũ, tạo family mới sau recent authentication nếu policy cho phép.
- OAuth client bên thứ ba: cân nhắc sự khác biệt giữa **existing user sessions** và **consent/grant của third-party clients**, thông báo rõ scope revoke.

Đừng suy **mọi `invalid_grant` đều là reuse attack**. Sau đổi mật khẩu, `invalid_grant` có thể là hệ quả của **policy-triggered revocation**; audit cần reason `PASSWORD_CHANGED`, không cáo buộc attacker.

### Tương tác với refresh token rotation

Nếu app vẫn cố refresh một RT đã bị revoke, AS từ chối. Nếu cùng lúc có duplicate refresh của token USED, AS có thể phát hiện reuse; việc family đã bị revoke vì password change cần được xử lý idempotent, không tạo spam alert hay revoke ngẫu nhiên family khác.

## 14. RFC 7009: endpoint revoke token không phải “đăng xuất tất cả”

OAuth Token Revocation (RFC 7009) cho phép client được phép yêu cầu AS vô hiệu token:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <CONFIDENTIAL_CLIENT_CREDENTIALS>

token=<REFRESH_TOKEN>&token_type_hint=refresh_token
~~~

**Ý nghĩa chính:**

- Request phải qua HTTPS và client authentication/authorization đúng registration.
- `token_type_hint` chỉ là **gợi ý**, không là bằng chứng loại credential.
- Response `HTTP 200` có thể được trả ngay cả khi token không tồn tại/đã invalid, để tránh token enumeration.
- Nếu revoke **refresh token** và AS hỗ trợ revoke access tokens, RFC 7009 **SHOULD** vô hiệu hóa các access token dựa trên cùng authorization grant.
- Nếu revoke **access token**, AS **MAY** thu hồi refresh token liên quan.
- **Không có tham số chuẩn RFC 7009 `logout_all_devices=true` hay `revoke_family=true`**.

Khi event là đổi/reset mật khẩu, Identity Service/AS có thể cần **admin/internal privileged grant-revocation API** hoặc update source of truth để revoke **nhiều family**. Gửi `/revoke` cho **một RT** không chứng minh mọi thiết bị đã logout; phải hiểu provider contract.

## 15. Access token đã phát hành: JWT offline là giới hạn lớn

Giả sử RT family của mobile đã bị revoke lúc **10:05**, nhưng access JWT `AT-42` được ký lúc **10:00** có `exp=10:10`. Orders API chỉ verify JWT signature, `iss`, `aud`, `scope`, `exp` offline.

~~~text
10:00  AS cấp AT-42 và RT-family F42
10:05  User reset password; AS revoke F42
10:06  Client cầm AT-42 gọi Orders API
       JWT signature vẫn đúng
       JWT chưa exp
       RS không tra revocation/credential epoch
       => AT-42 có thể vẫn được chấp nhận
10:10  AT-42 hết hạn
       => RS phải từ chối
~~~

**Không nên tuyên bố “sau đổi mật khẩu mọi API bị ngắt ngay”** nếu API dựa JWT offline và không có revoke signal/denylist/epoch check.

### Các chiến lược để RS biết access token cần bị chặn

| Kiến trúc AT | Mức chặn sau password change | Trade-off |
|---|---|---|
| **Opaque AT + introspection mỗi request** | AS có thể trả `active:false` ngay khi policy revoke đã commit | Phụ thuộc AS, latency và fail-closed |
| **Introspection + cache** | Chặn sau cache expiry hoặc invalidation signal | Cửa sổ stale cached `active:true` |
| **JWT offline, TTL ngắn** | Chỉ đảm bảo khi `exp` đến, trừ cơ chế bổ sung | Ít dependency nhưng không immediate revoke |
| **JWT + `auth_epoch`/version check tại RS** | Chặn khi RS nhận epoch mới/tra source-of-truth | Thêm consistency/read/caching |
| **JWT + grant/family denylist** | RS kiểm tra token `jti`/grant reference đã revoke | Cần denylist retention và propagation |
| **Revocation event tới RS caches** | Chặn sau reliable delivery/invalidation | Phải xử lý mất event, ordering, retry |

Với tài nguyên cực nhạy cảm, cần policy **không cache lâu** hoặc kiểm tra trạng thái gần thời điểm request; phải công bố **revocation visibility SLA** và test thực tế. JWT signature verification **không được bỏ qua** chỉ vì RS bổ sung epoch/denylist.

## 16. Epoch trên JWT: dấu mốc không tự thu hồi nếu RS không kiểm tra

Một hệ thống có thể đưa `cred_ver` (private claim) vào access token:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "https://orders-api.example.test",
  "scope": "orders:read",
  "iat": 1800000000,
  "exp": 1800000900,
  "cred_ver": 12
}
~~~

**JSON trên là payload minh họa, không phải JWT đã ký.** `cred_ver` không phải claim bắt buộc trong RFC 7519/9068. Chỉ thêm nó nếu AS/RS cùng hiểu contract và RS validate token chữ ký/usage chuẩn.

### Quyết định tại RS

~~~text
1. Verify JWT signature, allowed alg, typ/profile, iss, aud, exp/nbf.
2. Require token purpose = access_token.
3. Read token.cred_ver (nếu là contract bắt buộc).
4. Get trusted currentCredentialEpoch(user_id, issuer) = 13.
5. Compare:
       token.cred_ver = 12
       currentCredentialEpoch = 13
       => Reject.
6. Nếu phiên bản khớp:
       kiểm tra scope, tenant, object permissions, sender proof.
~~~

**Không nhận `currentCredentialEpoch` từ HTTP header do client cung cấp.** RS cần nguồn tin cậy từ AS/identity service hoặc cache có invalidation/TTL đủ chặt. Nếu cache current epoch ở 12 quá lâu, token cũ vẫn có thể lọt.

### `password_changed_at` thay epoch có được không?

Có thể sử dụng mốc `password_changed_at` và so với `iat` của token/session, nhưng phải xử lý **độ phân giải timestamp, clock skew, equality boundary, batch issuance, các sự kiện cùng giây và hệ phân tán**. **Monotonic integer epoch/version** thường dễ so sánh và kiểm toán hơn; vẫn phải giải quyết consistency.

## 17. Opaque token, introspection và response active=false

Với opaque access token, RS thường gọi AS qua RFC 7662:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Authorization: Basic <RESOURCE_SERVER_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<OPAQUE_ACCESS_TOKEN>&token_type_hint=access_token
~~~

Nếu AS đã revoke token/grant theo password change:

~~~json
{
  "active": false
}
~~~

Đối với token còn active trong context RS được phép introspect:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "aud": "https://orders-api.example.test",
  "scope": "orders:read",
  "exp": 1800000900,
  "sub": "user-42"
}
~~~

**`active:false`** có thể do revoked, expired, unknown hoặc RS không được phép xem token; response này nên tối giản. **`active:true` không tự authorize object**: RS còn phải kiểm tra purpose, issuer, audience, scope, exp và object/tenant ACL.

Khi AS unreachable/HTTP 5xx hoặc RS client credentials sai, RS không có một verdict đáng tin; phải **fail closed**, không ép lỗi mạng thành `active:true`. Nếu RS cache introspection, password change không nhất thiết được thấy ngay — phụ thuộc **TTL/invalidation**.

## 18. OIDC/SAML/SSO: đổi mật khẩu ở một nơi không logout mọi RP

Trong hệ thống federated, có ít nhất ba tầng phiên:

~~~text
Identity Provider / OpenID Provider
  OP SSO session (browser IdP cookie)
        |
        +-- RP-A local session (orders-web)
        |
        +-- RP-B local session (billing-web)
        |
        +-- Native client local state + OAuth tokens
~~~

Nếu user đổi mật khẩu ở **OP**, các RP có thể **vẫn giữ local session** cho tới khi nhận logout event hoặc áp dụng expiry/policy. Nếu user đổi mật khẩu chỉ trong **RP-A** (một mật khẩu nội bộ), OP và RP-B **không tự biết**.

### Các cơ chế OIDC liên quan

| Cơ chế | Ai khởi phát/nhận? | Được giải quyết | Không tự giải quyết |
|---|---|---|---|
| **RP-Initiated Logout** | RP chuyển browser đến OP end-session endpoint được hỗ trợ | Yêu cầu kết thúc OP session theo profile | Không mặc định revoke mọi OAuth RT/AT |
| **OIDC Back-Channel Logout** | OP gửi **signed Logout Token** đến RP đã đăng ký | RP vô hiệu local session tương ứng theo `sid`/`sub` và policy | Không tự khiến mọi RS chặn JWT AT |
| **OIDC Front-Channel Logout** | OP dùng browser để phát logout tới RP | Có thể hỗ trợ các session khi user agent hoạt động | Phụ thuộc browser/privacy/cookie restrictions, không nên là tín hiệu bảo mật duy nhất |
| **OP Global Session Policy** | OP/IdP sau password change | Kết thúc SSO sessions/phát sự kiện theo cấu hình | Không tự thay local app sessions nếu RP không xử lý |
| **OAuth Revocation / AS grant policy** | AS/client/internal security service | Vô hiệu RT families/grants/AT theo AS policy | Không tự gửi `Set-Cookie` để xóa cookie RP |

**Đừng coi `end_session_endpoint` là nút “revoke tất cả refresh tokens của user”**; profile logout và token revocation là hai khái niệm khác nhau.

### Bảo mật Back-Channel Logout Token

Một Logout Token là **JWT thông báo sự kiện logout**, không phải access token/ID token. RP phải kiểm tra chữ ký, `iss`, `aud`, `iat`, `jti`, `events` và `sid`/`sub` theo spec; có ràng buộc `nonce` không được xuất hiện. Không chỉ parse JSON rồi xóa bất kỳ session ID mà attacker tự đặt.

Nếu OP gửi logout event với một `sid`, RP phải định vị **đúng session của OP/subject/issuer tương ứng**. Nếu event không thể tới RP đang offline, cần retry/reconciliation/expiry policy. **Back-channel logout không thay kiểm tra auth epoch trên API token**.

## 19. Hủy giao dịch đang chờ và chống “đăng nhập lại từ flow cũ”

Ngay sau password change/recovery reset, còn có thể tồn tại:

- Authorization Code + PKCE đang pending, chưa nhận callback.
- OIDC authorization request từ một RP khác đang chờ user approve.
- Device Authorization Grant có `device_code`/`user_code` pending.
- Password reset link hoặc MFA/recovery challenge cũ chưa hết hạn.
- OAuth consent/grant request khởi tạo dưới OP session cũ.

Nếu policy yêu cầu **revoke all old sessions**, cần xác định các pending flow này có thể hoàn tất **sau** password change hay không:

1. Gắn authorization transaction với **auth epoch/session context** lúc bắt đầu.
2. Khi AS phát token hoặc xử lý callback, kiểm tra **source-of-truth state** và **recent authentication** theo policy.
3. Nếu session đã revoked/epoch cũ, **không dùng code/PKCE verifier cũ** để bỏ qua bước đăng nhập mới; fail/restart flow thích hợp.
4. Hủy device authorizations pending khi phù hợp; device code không biến thành RT.
5. Invalidate recovery links/challenges đã dùng hoặc không còn hợp lệ sau password change.
6. Với OIDC, RP kiểm tra `state`, `nonce`, issuer, ID token và freshness (`auth_time`/`max_age` nếu policy yêu cầu).

**Authorization code phát hành hợp lệ trước một password change** không được mặc định được token endpoint trao đổi sau sự kiện nếu policy quy định phải dừng mọi phiên cũ; AS phải có check grant/epoch thích hợp khi exchange.

## 20. Thứ tự commit, outbox và hiệu lực “đăng xuất”

Vì Identity DB, AS, session store và RS có thể thuộc các service khác nhau, không có một lệnh SQL phủ lên toàn bộ mà tự an toàn.

~~~mermaid
flowchart TD
    A["Validate reauthentication + password policy"] --> B["Update password hash + bump auth epoch"]
    B --> C["Commit credential + durable revoke intent"]
    C --> D["Revoke sessions / RT family ở source of truth"]
    C --> E["Outbox event tới AS/RS/OP tích hợp"]
    D --> F["Reject old sessions và refresh requests"]
    E --> G["Invalidate RS denylist/epoch cache"]
    F --> H{"Security state đạt policy trước khi báo success?"}
    G --> H
    H -->|"Có"| OK["Response success + clear/rotate current session"]
    H -->|"Chưa"| W["Fail closed cho credential cũ; retry/reconcile và báo trạng thái phù hợp"]
~~~

### Vì sao cần nguồn sự thật?

Nếu bước cập nhật mật khẩu thành công nhưng lệnh thu hồi family ở AS thất bại, client **không thể tuyên bố tất cả thiết bị đã đăng xuất ngay**. Một thiết kế thực tế có thể:

- Commit **credential epoch + durable security event** đồng thời tại source of truth.
- **Bắt mọi phiên/refresh/token issuance liên quan kiểm tra epoch** trước khi phục vụ, kể cả khi event fan-out chậm.
- Đánh dấu trạng thái **PENDING_REVOCATION** và retry tác vụ idempotent; làm rõ user-facing guarantee.
- Giám sát event delivery, cache invalidation, retry exhaustion và security SLA.
- Với hệ thống có yêu cầu cao, dùng source-of-truth auth decision ở đường critical path hoặc một cơ chế fencing tương đương.

**Không được** lấy việc gửi một message queue event thành công làm bằng chứng mọi RS/AS instances đã áp dụng thay đổi. Với các JWT RS hoàn toàn offline, cần công bố **cửa sổ còn hiệu lực tới exp** nếu không có kênh khác.

## 21. Các response HTTP và UX cần rõ ràng

### Sau change password thành công, giữ current session

~~~json
{
  "password_changed": true,
  "session_action": "CURRENT_REAUTHENTICATED_SESSION_RETAINED",
  "other_sessions_revoked": true,
  "refresh_token_policy": "OLD_FAMILIES_REVOKED",
  "access_token_revocation": "PROVIDER_POLICY_APPLIES"
}
~~~

Chỉ trả các giá trị trên **nếu backend thực sự biết policy/action đã hoàn tất hoặc trạng thái được định nghĩa rõ**. Không lộ session IDs, token values, internal admin endpoints hay vị trí thiết bị không cần thiết.

### Sau password reset, bắt buộc đăng nhập lại

~~~json
{
  "password_changed": true,
  "session_action": "REAUTHENTICATION_REQUIRED",
  "other_sessions_revoked": true,
  "message": "Mật khẩu đã được cập nhật. Vui lòng đăng nhập lại."
}
~~~

Cần tránh:

- Trả **200 success** rồi thực tế không revoke RT và không có epoch check.
- Bắt user đăng nhập lại nhưng **bản sao RT bị đánh cắp** vẫn refresh được.
- Hiển thị “Đã đăng xuất trên mọi thiết bị ngay lập tức” khi JWT offline có thể sống đến `exp`.
- Tự động gửi mật khẩu mới qua email hoặc push notification.
- Báo nguyên nhân quá chi tiết trong recovery flow có thể giúp liệt kê tài khoản.

### Thông báo security event

Sau khi đổi mật khẩu, nên gửi **thông báo out-of-band** tới kênh liên hệ đã xác minh, với thời điểm và hướng dẫn báo cáo nếu không phải user chủ động thực hiện. Không đưa mật khẩu/token/reset link bí mật vào thông báo. Nếu email cũng bị attacker kiểm soát, cần thêm cơ chế giám sát và recovery đáng tin; notification không thay revocation.

## 22. Case study: user đổi mật khẩu giữa hai thiết bị và một API JWT

Giả sử:

- User `U42` có browser Chrome **A**, mobile **B** và browser Firefox **C**.
- Credential epoch lúc đầu = **12**.
- Access JWT được AS cấp có TTL **10 phút**.
- Chính sách của sản phẩm sau **self-service change** là **KEEP_CURRENT_REVOKE_OTHERS** chỉ khi A vừa reauthenticate bằng phương thức mạnh.
- Orders API dùng JWT offline nhưng có **denylist/epoch event** nhận với độ trễ vận hành (không phải bảo đảm tức thì).

### Dòng thời gian giả định

| UTC | Diễn biến | Hệ quả |
|---|---|---|
| **10:00:00** | B có access token AT-B, `exp=10:10`, `cred_ver=12` | B gọi API được trước sự kiện |
| **10:03:00** | A reauthenticate và gửi đổi mật khẩu | Backend xác định principal và risk |
| **10:03:01** | DB commit hash mới + epoch **13** | Hash cũ không được dùng cho login mới |
| **10:03:02** | AS/session service revoke các session/family cũ; tạo session mới cho A theo policy | B/C không refresh được và cookie phiên cũ bị từ chối |
| **10:03:04** | B gửi RT cũ tới `/token` | AS trả `invalid_grant` |
| **10:03:05** | B gửi AT-B tới Orders API JWT offline | **Có thể vẫn thành công nếu RS chưa biết revoke** |
| **10:03:20** | RS nhận denylist/epoch event cho U42 | AT-B bị chặn nếu RS enforce event/epoch |
| **10:10:00** | AT-B hết hạn theo `exp` | JWT offline phải bị từ chối dù không nhận event |

Mốc 10:03:20 là **độ trễ ví dụ**, không phải cam kết của OAuth. Nếu hệ thống chỉ verify JWT offline, AT-B **có thể được chấp nhận đến 10:10:00**.

### Ba biến thể an ninh

**A. User đổi mật khẩu tự nguyện và A reauthenticated:** nếu sản phẩm cho phép, A có thể có **session mới dưới epoch 13**; B/C bị revoke.

**B. User quên mật khẩu và reset qua recovery:** policy **REVOKE_ALL** làm cả A/B/C bị từ chối, không tự cấp phiên mới chỉ từ việc nhấn link reset.

**C. Attacker đã đánh cắp RT-B:** chỉ clear storage trên B không đủ; AS phải revoke family B và các grants trong scope; RS cần biết chính sách đối với AT đã cấp, và incident có thể phải mở rộng sang các thiết bị khác.

## 23. Logging, audit và privacy sau password change

Lịch sử security event cần đủ để điều tra nhưng không chứa credentials.

Ví dụ event an toàn:

~~~json
{
  "event_type": "auth.password.changed",
  "occurred_at": "2026-11-23T10:03:01Z",
  "account_ref": "user-pseudo-42",
  "actor_category": "END_USER_REAUTHENTICATED",
  "event_kind": "SELF_SERVICE_CHANGE",
  "credential_epoch_before": 12,
  "credential_epoch_after": 13,
  "session_policy": "KEEP_CURRENT_REVOKE_OTHERS",
  "refresh_family_revocation": "COMPLETED",
  "access_token_policy": "EVENTUAL_EPOCH_INVALIDATION",
  "correlation_ref": "sec-event-pseudo-91",
  "password_logged": false
}
~~~

`password_logged=false` là trường minh họa, **không bảo đảm** toàn bộ reverse proxy, APM, tracing và crash reporting thực sự không log secret.

**Không log:**

- Mật khẩu cũ/mới, password reset token, OTP, recovery codes, hash+salt/pepper, bearer/refresh tokens.
- Cookie session ID, HTTP `Authorization` header, token endpoint request body, full reset URL.
- Thông tin vị trí/thiết bị/IP không cần thiết; nếu phục vụ incident, áp dụng access control/retention phù hợp.
- Cả `jti` hoặc family reference không được kiểm soát nếu có thể dùng để theo dõi user ngoài phạm vi cho phép.

**Nên đo:** số phiên/family revoke, số request bằng epoch cũ bị từ chối, AS `invalid_grant` sau sự kiện, AT còn được RS chấp nhận trong propagation window, outbox retry failures, thời gian hoàn tất revoke và user reauthentication success/fail.

## 24. Ma trận kiểm thử logout sau đổi mật khẩu

| Test | Thao tác | Kết quả mong đợi |
|---|---|---|
| **T1 — Reauth required** | Session cũ đổi mật khẩu không recent auth | Step-up/reauth trước khi cập nhật |
| **T2 — Wrong current password** | User nhập mật khẩu hiện tại sai | Không cập nhật hash/epoch, không phát event success |
| **T3 — Cross-user IDOR** | Body khai `user_id` của người khác | Server chỉ xử lý principal đã xác minh |
| **T4 — CSRF** | Cross-site POST dùng cookie của user | Bị CSRF/session policy từ chối |
| **T5 — Password hashing** | Cập nhật mật khẩu | Lưu hash an toàn; không lưu plaintext |
| **T6 — Password rejected** | Mật khẩu mới không đạt policy | Không revoke/không trả success giả |
| **T7 — Self-service keep current** | Recent strong reauth, risk thấp | Rotate/rebind A epoch mới; revoke phiên khác theo policy |
| **T8 — No recent reauth** | User cố `keep_current=true` | Policy không dựa boolean client, yêu cầu reauth |
| **T9 — Recovery reset** | Recovery flow hoàn tất | Revoke all existing sessions/families theo policy |
| **T10 — Admin forced reset** | Admin/AS yêu cầu reset | Revoke đúng security scope, login mới |
| **T11 — Suspicious activity** | Đổi sau nghi chiếm account | Không mặc định giữ current session |
| **T12 — Other browser** | Browser B còn cookie cũ | Backend từ chối request phiên cũ |
| **T13 — Current browser logout** | REVOKE_ALL | Invalidate server session và clear cookie đúng attributes |
| **T14 — Cookie-only logout** | Chỉ clear cookie A | Test chứng minh B vẫn còn nếu thiếu server revoke; thiết kế phải sửa |
| **T15 — Epoch mismatch** | Session epoch=12, account epoch=13 | Từ chối |
| **T16 — Epoch stale cache** | Node đọc epoch=12 cũ | Không cho request nhạy cảm vượt policy/SLA |
| **T17 — Refresh after change** | RT family cũ POST `/token` | `invalid_grant`/deny, không cấp AT/RT mới |
| **T18 — RT family current** | Policy KEEP_CURRENT | Không tự reuse RT family cũ; credential mới dưới epoch mới |
| **T19 — Parallel refresh** | RT exchange cạnh tranh với password change | Không có token epoch cũ được cấp sau boundary được bảo đảm |
| **T20 — Concurrent password changes** | Hai request change cùng expected epoch | Tối đa một epoch CAS thành công theo workflow |
| **T21 — DB rollback** | Error trong DB transaction | Không trả “password changed” nếu không commit |
| **T22 — Outbox delivery failure** | Queue consumer/AS unavailable | Security state fail-closed, retry/reconcile, cảnh báo |
| **T23 — JWT offline** | AT còn `exp` nhưng family đã revoke | Test đo thực tế RS có thể accept nếu không check epoch/denylist |
| **T24 — JWT epoch check** | AT `cred_ver=12`, latest epoch=13 | RS từ chối dù signature còn hợp lệ |
| **T25 — Opaque AT** | AS mark AT inactive sau reset | RFC 7662 trả `active:false` khi RS introspect |
| **T26 — Introspection cache** | Cached `active:true` trước revoke | TTL/invalidation tuân revocation visibility SLA |
| **T27 — Wrong audience** | AT dành Billing API gọi Orders API | Orders API từ chối |
| **T28 — Refresh token as AT** | Gửi RT trong Bearer API request | RS từ chối token purpose |
| **T29 — ID token as AT** | Gửi ID token gọi API | RS từ chối |
| **T30 — OIDC OP/RP separation** | Password đổi tại OP nhưng RP session còn | RP logout theo tích hợp, không giả định auto |
| **T31 — Back-channel logout** | OP gửi Logout Token hợp lệ | RP verify signature/claims và vô hiệu đúng session |
| **T32 — Forged Logout Token** | Attacker gửi JWT giả hoặc sai issuer/audience | RP từ chối, không logout sai user |
| **T33 — Third-party grants** | Policy chỉ logout sessions | Không âm thầm tuyên bố third-party app grants revoked |
| **T34 — All-apps revoke** | User yêu cầu thu hồi mọi app được phép | Revoke đúng grants, audit và UX thể hiện rõ |
| **T35 — Pending PKCE callback** | Callback từ flow bắt đầu trước epoch bump | Policy yêu cầu reauth, không bypass bằng code cũ |
| **T36 — Pending device grant** | Device code pending khi reset | AS hủy/deny nếu thuộc security scope |
| **T37 — Used recovery token** | Dùng lại reset link cũ | Từ chối single-use |
| **T38 — Client offline** | Mobile không có mạng lúc đổi mật khẩu | Khi online, server vẫn từ chối session/RT cũ |
| **T39 — Replayed revoke event** | Outbox event tới AS/RS hai lần | Idempotent, không làm sai phiên mới |
| **T40 — Multi-region lag** | Region B nhận epoch muộn | Không bỏ qua policy; đo và khống chế propagation |
| **T41 — Object ACL** | Token mới đúng epoch nhưng thiếu quyền order | RS từ chối object theo policy |
| **T42 — User notification** | Password change thành công | Gửi cảnh báo out-of-band không chứa secret |
| **T43 — Log canary** | Test bằng mật khẩu/token giả trong staging | Không lộ trong logs/APM/tracing/crash |
| **T44 — Reset exception path** | Password update thành công nhưng revoke fan-out lỗi | Không cam kết logout tức thời nếu policy chưa đạt; fail-closed/retry |
| **T45 — Security sign-out UX** | Người dùng đăng nhập lại sau reset | Flow/state/nonce mới; old credentials không phục hồi |
| **T46 — No false success** | Hệ thống chỉ sửa hash, chưa thực thi invalidate | Tests phát hiện lời hứa “logout all” không đúng |
| **T47 — No leaked enumeration** | Recovery account không tồn tại | Thông báo không giúp attacker liệt kê tài khoản |
| **T48 — Token expiration boundary** | `now == exp` | RS từ chối; không mở grace tùy tiện |

**Chỉ kiểm thử bằng tài khoản/test credential staging**, không gửi mật khẩu, RT/AT, reset link hoặc cookie production vào HAR, screenshot, CI log hay security report.

## 25. Những hiểu lầm thường gặp

**“Đổi mật khẩu là logout.”** Sai. Hash mới không tự vô hiệu session cookie/RT/JWT.

**“Xóa cookie ở browser hiện tại là logout tất cả thiết bị.”** Sai. Backend phải vô hiệu phiên trên server hoặc dùng epoch/version gate.

**“Revoke refresh token thì JWT access token hết tác dụng ngay.”** Sai nếu RS offline chỉ verify chữ ký/`exp`; cần introspection, denylist, epoch hoặc chờ expiry.

**“`password_changed_at` xuất hiện trong database nghĩa API sẽ tự kiểm tra nó.”** Sai. RS phải có code/policy kiểm tra và nguồn giá trị mới đủ tin cậy.

**“OIDC RP-Initiated Logout sẽ tự thu hồi mọi OAuth token.”** Sai. Logout OP/RP session và revoke RT/AT khác trách nhiệm.

**“Back-channel Logout Token là access token có thể gọi API.”** Sai. Đó là một JWT sự kiện logout được RP xác minh theo profile.

**“Đổi mật khẩu tự nguyện và reset sau nghi compromise nên logout cùng một phạm vi.”** Không nhất thiết. Recovery/incident thường cần chính sách mạnh hơn.

**“Nếu giữ current session thì không cần đổi session ID.”** Không nên. Giữ session phải dựa recent auth và xử lý fixation/session theft theo policy; rotate/rebind ID thích hợp.

**“Chỉ cần broadcast event, mọi RS đã chặn token.”** Sai. Phải có acknowledgment/retry/reconciliation hoặc chấp nhận và công bố revocation delay.

**“Mất kết nối AS khi kiểm tra token thì cứ cho phép để user khỏi bị gián đoạn.”** Sai với hệ thống yêu cầu introspection/epoch: fail-open có thể chấp nhận session bị revoke.

**“Xóa refresh token khỏi mobile thì attacker không dùng được bản sao.”** Sai. Phải revoke trên AS.

**“Đổi mật khẩu luôn thu hồi consent OAuth của mọi app.”** Sai. Đó là lựa chọn grant policy riêng, cần định nghĩa rõ scope và thông báo.

## 26. Checklist triển khai Logout sau đổi mật khẩu

1. **Phân biệt self-service change, forgot-password reset, admin reset và compromise incident**, có chính sách session/RT/AT rõ cho từng trường hợp.
2. **Yêu cầu recent authentication/step-up** trước thao tác nhạy cảm theo threat model; không tin mỗi cookie cũ.
3. **Bảo vệ endpoint đổi mật khẩu**: CSRF/session checks, password hashing, password policy, rate limit và không log password.
4. **Lấy principal từ authentication context tin cậy**, không chọn account bằng body/query do user tự khai.
5. **Cập nhật hash + bump credential epoch + durable revoke intent** có ordering/transaction nhất quán.
6. **Revoke server-side sessions** theo policy; xóa cookie chỉ ở browser hiện tại và không thay backend revocation.
7. **Nếu giữ current session**, reauthenticate, rotate session ID và bind phiên mới với epoch mới; không để phiên cũ được nâng quyền tự động.
8. **Revoke refresh-token families/grants** trong security scope; AS từ chối refresh từ RT cũ sau boundary.
9. **Chống race issuance-vs-revoke**: các luồng tạo session/RT/AT cùng đối chiếu epoch/grant source-of-truth.
10. **Định nghĩa tác động lên access token**: JWT offline, opaque introspection, cache, denylist, `jti`/version và RS enforcement.
11. **Không tuyên bố thu hồi AT tức thời** nếu còn revocation propagation delay hoặc chỉ dựa `exp`.
12. **Đừng gộp logout RP, OP SSO và OAuth grant revocation**; dùng giao thức OIDC phù hợp khi có integration.
13. **Xác minh Logout Token** nếu dùng OIDC Back-Channel Logout; chặn forged JWT/replay/mix-up.
14. **Hủy pending authorization/PKCE/device/recovery flows** theo security epoch khi phù hợp.
15. **Dùng durable outbox/idempotent workers** cho dịch vụ phân tán; bảo đảm fail-closed hoặc giao thức nhất quán.
16. **Tách current/other/all sessions và third-party grants**, tránh revoke quá rộng hoặc cam kết sai.
17. **Thông báo user** về password change/reset và phạm vi đăng xuất thật; cảnh báo kênh đã xác minh không chứa secret.
18. **Audit có allowlist**, theo dõi epoch, event reason, session/family counts, propagation latency, không log credential.
19. **Kiểm thử race/multi-device/multi-region/offline clients**, rollback và outbox failure, không chỉ happy path đổi mật khẩu.
20. **Bảo đảm RS vẫn kiểm tra issuer/audience/scope/token type/expiry/object permissions**, kể cả token thuộc epoch mới.
21. **Đặt revocation visibility SLA thực tế** và kiểm tra hoạt động của cache invalidation, introspection và denylist.
22. **Chuẩn bị đường khôi phục**: khi phiên cũ bị chặn, user đăng nhập/reauthenticate bằng flow mới, state/PKCE verifier mới nếu áp dụng.

**Kết luận:** **logout sau đổi mật khẩu** là một **thay đổi trạng thái tin cậy trên toàn hệ thống**, không chỉ là thao tác thay mật khẩu và xóa cookie. Triển khai an toàn phải **chứng minh người đổi có quyền**, **chọn đúng phạm vi session/grant**, **revoke refresh-token families**, **ngăn các credential epoch cũ được chấp nhận hoặc phát thêm**, và **có chiến lược rõ cho access token đang lưu hành**. Các tầng OIDC SSO, RP local session và Resource Server không tự đồng bộ với nhau nếu không được thiết kế. Hãy kiểm chứng bằng **trường hợp nhiều thiết bị, request đồng thời, network outage và JWT offline**, rồi mới hứa với người dùng “đã đăng xuất các thiết bị khác”.

### Tài liệu chuẩn và tham khảo

- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): vòng đời session, invalidation và reauthentication.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): reauthentication, đổi mật khẩu và chống tấn công phiên.
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): recovery token, single-use, thông báo và session sau reset.
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): password hashing và bảo vệ secrets.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): refresh token rotation, sender constraining, replay và grant security.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi RT/AT và tác động token liên quan.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`/`inactive` tại RS.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): code/refresh token grants và client authentication.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token, `invalid_token` và API request.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token profile và audience/issuer.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, `auth_time` và OIDC session authentication.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): RP yêu cầu OP kết thúc session.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): Logout Token, `sid`/`sub` và logout tới RPs.
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): browser-based logout và giới hạn thực thi.
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): current session logout với SecurityContext/HttpSession.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): session fixation/concurrency/registry.

