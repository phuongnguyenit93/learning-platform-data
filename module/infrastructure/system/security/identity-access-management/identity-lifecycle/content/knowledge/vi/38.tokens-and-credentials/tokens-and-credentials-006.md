# Token expiration trong IAM: thời hạn token, làm mới và thu hồi quyền theo vòng đời danh tính

## 1. Token expiration là gì?

Trong **Identity and Access Management (IAM)**, **Token expiration** là cơ chế **giới hạn thời điểm hoặc khoảng thời gian mà một token còn có thể được chấp nhận** theo quy tắc của bên phát hành (issuer), bên kiểm tra (verifier) và chính sách áp dụng. Khi vượt mốc hết hạn, token không được tiếp tục được dùng để chứng minh quyền truy cập trong phạm vi mà token đó đại diện.

Ví dụ, một **OAuth 2.0 access token** được phát hành lúc 09:00, có hạn đến 09:15. Sau 09:15, API kiểm tra token đúng cách phải từ chối access token ấy, ngay cả khi người dùng còn đăng nhập ứng dụng. Client có thể xin token mới nếu còn **phiên hoặc refresh grant hợp lệ**, nhưng điều đó phải được quyết định theo trạng thái danh tính và quyền hiện hành.

Trong thực tế, “token hết hạn” có thể nói đến nhiều loại token khác nhau: **access token, ID token, refresh token, session token, API token, signed assertion hoặc token đăng ký thiết bị**. Không thể lấy thời hạn và hành vi của một loại rồi áp dụng cho mọi loại.

**Token expiration là một phần của vòng đời quyền truy cập, nhưng không thay thế revocation hoặc deprovisioning.** Nếu nhân viên đã **Leaver** lúc 10:00 và token có hạn tới 10:30, việc chỉ chờ 10:30 mới ngăn quyền có thể vi phạm chính sách offboarding. Ngược lại, token vừa hết hạn không có nghĩa người dùng đã mất toàn bộ quyền: một quy trình làm mới hợp lệ có thể cấp token mới với scope phù hợp.

Trong module **Security — Identity Access Management — Identity Lifecycle**, nội dung này gắn với **Joiner–Mover–Leaver (JML)**, **IdP, SSO, OAuth/OIDC, SCIM, RBAC/ABAC/PBAC, tài khoản dịch vụ, kiểm toán** và mục tiêu giảm **quyền truy cập tồn dư**.

### Sau bài học, người học có thể

1. Phân biệt thời hạn access token, ID token, refresh token, session và credential.
2. Hiểu chính xác JWT **exp, nbf, iat**, NumericDate và clock skew.
3. Thiết kế TTL theo mục đích, rủi ro, client type và khả năng thu hồi.
4. Hiểu refresh flow, refresh-token rotation và dấu hiệu replay/reuse.
5. Phân biệt expiration, revocation, logout, suspension, deprovisioning và key rotation.
6. Kiểm tra token đúng cách tại authorization server, API gateway và resource server.
7. Xử lý quyền thay đổi khi **Joiner, Mover, Leaver** hoặc khi owner của non-human account đổi.
8. Thiết kế giám sát, audit, kiểm thử ranh giới thời gian và reconciliation với quyền thực tế.

## 2. Tại sao token phải có thời hạn?

Token thường được dùng như một **bằng chứng ủy quyền hoặc xác thực có thể trình lại**. Nếu kẻ khác chiếm được bearer token còn hợp lệ, họ có thể thử dùng token đó trong phạm vi được phép. **Thời hạn ngắn giới hạn cửa sổ bị lạm dụng**, nhưng không tự ngăn hành động xảy ra trong cửa sổ ấy.

Những lý do chính để đặt expiration:

| Mục tiêu | Điều được cải thiện | Giới hạn |
| --- | --- | --- |
| **Giới hạn rủi ro lộ token** | Token đánh cắp có khoảng hiệu lực hữu hạn | Kẻ tấn công vẫn có thể hành động trước khi hết hạn |
| **Buộc cấp lại quyền theo chính sách** | Token mới có thể phản ánh role/scope mới | Token cũ có thể tiếp tục được chấp nhận trong thời gian còn hạn |
| **Giảm quyền truy cập tồn dư** | Token cũ ngừng hoạt động sau mốc hết hạn | Không thay thế yêu cầu thu hồi ngay khi Leaver |
| **Hỗ trợ token ngắn hạn cho workload** | Không cần lưu secret dài hạn cho mọi API call | Trust policy và nguồn phát hành vẫn phải được bảo vệ |
| **Giảm phụ thuộc vào thay đổi trạng thái tức thời** | Một số hệ thống JWT có thể tự kiểm tra chữ ký và thời gian | Khó thu hồi sớm nếu chỉ validate offline |
| **Hạn chế thời gian phiên đặc quyền** | Giảm thời gian sử dụng quyền JIT/PAM | Phải đóng session và kiểm tra quyền thực tại target |

**TTL ngắn không tự làm ứng dụng an toàn hơn** nếu token bị ghi vào log, bị gửi tới sai audience, lưu trong nơi client có thể bị chiếm quyền, hoặc API bỏ qua authorization ở mức đối tượng.

## 3. Phân biệt token, credential, grant, session và entitlement

| Khái niệm | Bản chất | Có thể có thời hạn? | Thường do ai quản lý? |
| --- | --- | --- | --- |
| **Credential** | Bí mật/khóa/chứng chỉ để chứng thực chủ thể | Có, tùy loại | IdP, CA/PKI, vault, platform |
| **OAuth access token** | Bằng chứng để gọi protected resource | Có, thường ngắn | Authorization server và resource server |
| **OIDC ID token** | Token biểu diễn sự kiện/xác thực người dùng cho client | Có; OIDC ID Token có exp | OpenID Provider và OIDC client |
| **Refresh token** | Credential để xin access token mới | Có thể có inactivity/absolute lifetime và revocation | Authorization server |
| **Authorization grant** | Căn cứ client được cấp token/scope | Có thể bị thu hồi, giới hạn thời gian | Authorization server và user/policy |
| **Session** | Trạng thái đăng nhập người dùng/thiết bị | Idle timeout và absolute timeout | IdP/app/PAM |
| **Entitlement** | Quyền nghiệp vụ đã cấp cho identity | Có thể bắt đầu/kết thúc theo policy | IAM/IGA, app owner, resource server |
| **API key** | Credential do hệ thống cấp để gọi API | Có thể có expiry/rotation, không nhất thiết theo JWT | API provider |
| **Certificate** | Chứng nhận public key/subject theo CA | NotBefore/NotAfter | PKI/CA và TLS verifier |

Một **refresh token vẫn hợp lệ** không bảo đảm authorization server phải cấp access token có cùng quyền như trước. Trước khi làm mới, policy có thể kiểm tra **client, user status, employment relation, consent, entitlement, risk và grant state**.

Một **entitlement bị thu hồi** không tự làm một access token JWT đang được kiểm tra offline hết hạn. Hai tiến trình chỉ nhất quán nếu có cơ chế **revocation, introspection, security epoch, denylist, online authorization hoặc TTL phù hợp**.

## 4. Những loại token quan trọng và mục đích của chúng

| Token | Ai nhận/kiểm tra? | Dùng để làm gì? | Sai lầm cần tránh |
| --- | --- | --- | --- |
| **Access token** | Resource server/API đúng audience | Truy cập tài nguyên được bảo vệ | Dùng ID token thay access token |
| **ID token** | OIDC relying party/client | Xác minh kết quả authentication cho client | Gửi ID token để gọi API như access token |
| **Refresh token** | Authorization server/token endpoint | Xin token mới theo grant | Gửi refresh token tới resource server |
| **Session cookie** | Ứng dụng hoặc IdP đúng origin | Duy trì phiên ứng dụng/SSO | Coi session cookie và OAuth token là một |
| **Client assertion** | Authorization server/verifier | Xác thực client bằng chứng cứ ký | Dùng assertion ngoài đúng audience |
| **Device-bound proof** | Verifier hỗ trợ sender constraint | Chứng minh client nắm khóa gắn với token | Coi proof thay user/device authorization |
| **Personal Access Token (PAT)** | Product/API vendor | Truy cập API theo quyền account/token | Coi PAT tự hết hạn giống mọi OAuth token |
| **Recovery/enrollment token** | Dịch vụ phục hồi/đăng ký | Một hành động nhạy cảm có hạn | Tái sử dụng token một lần hoặc ghi vào log |

**Tên token không quyết định format**. OAuth access token có thể là **opaque string** hoặc **JWT** tùy Authorization Server và contract của API. Không cố giải mã mọi access token dưới dạng JWT.

## 5. Timeline: thời hạn token khác thời hạn phiên

Ví dụ **giả định**:

~~~text
09:00  User đăng nhập SSO, tạo phiên có hạn tối đa đến 17:00
09:01  Client nhận access token A, exp=09:16
09:14  Client dùng refresh grant để xin access token B, exp=09:29
09:16  Token A hết hạn; B vẫn có thể hợp lệ
09:20  HRIS xác nhận Mover; role cũ bị thu hồi theo policy
09:21  Authorization server re-evaluate; token mới không còn scope cũ
09:29  Token B hết hạn theo exp
17:00  Phiên SSO tới mốc absolute timeout nếu chưa bị kết thúc sớm
~~~

**Phiên IdP còn đến 17:00 không đồng nghĩa access token A còn giá trị sau 09:16**. **Token B còn hạn đến 09:29 không tự chứng minh quyền Mover đã được rút tại API từ 09:20**, nếu resource server chưa biết sự kiện thay đổi quyền.

~~~mermaid
sequenceDiagram
    participant U as User/Workload
    participant C as OAuth client
    participant AS as Authorization Server/IdP
    participant RS as Resource Server
    U->>C: Bắt đầu phiên hợp lệ
    C->>AS: Xin access token theo grant
    AS-->>C: Token A, exp=T1
    C->>RS: Gửi Token A trước T1
    RS-->>C: Permit khi token và policy hợp lệ
    Note over C,AS: Gần T1: làm mới theo grant nếu được phép
    C->>AS: Refresh hoặc obtain new token
    AS-->>C: Token B, exp=T2, scope hiện hành
    C->>RS: Gửi Token A sau T1
    RS-->>C: 401/invalid_token
    C->>RS: Gửi Token B còn hạn
    RS-->>C: Quyết định theo token và quyền thực tế
~~~

Sơ đồ minh họa một trường hợp. Trong **client credentials**, workload thường **xin access token mới bằng credential của client**, không cần refresh token. Trong một số luồng còn phải qua user interaction, consent hoặc step-up khi grant cũ không còn đủ.

## 6. TTL, expiresAt, absolute và sliding expiration

**TTL (Time To Live)** là độ dài dự kiến token/phiên còn được chấp nhận. **expiresAt** là mốc thời gian tuyệt đối. Cần phân biệt:

| Cơ chế | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Fixed/absolute expiration** | Hết hạn đúng mốc, việc sử dụng không kéo dài | Access token A exp=09:16 |
| **Idle/inactivity timeout** | Hết hạn sau khoảng không có hoạt động hợp lệ | Phiên ứng dụng ngừng sau 20 phút không hoạt động |
| **Sliding expiration** | Hoạt động hợp lệ có thể kéo dài thời hạn trong giới hạn | Session mới được gia hạn khi user còn active |
| **Maximum/absolute session lifetime** | Giới hạn cứng dù có activity liên tục | Phiên kết thúc hoặc yêu cầu reauthentication theo policy |
| **Refresh-token inactivity expiry** | Không dùng refresh trong khoảng quy định thì grant hết hiệu lực | Refresh token bị vô hiệu sau khoảng idle |
| **Credential/certificate expiry** | Bản thân bằng chứng xác thực đạt NotAfter hoặc expiresAt | Client certificate tới hạn |
| **Entitlement/access endAt** | Quyền nghiệp vụ không còn hợp lệ sau thời gian được duyệt | Project role hết hạn khi kết thúc bàn giao |

**Sliding session expiration không được kéo dài access token JWT đã phát hành bằng cách đổi đồng hồ phía client.** Để có thời hạn token mới, issuer cần **phát hành token mới** hoặc dùng cơ chế token stateful có contract tương ứng.

Nếu có **absolute maximum**, việc refresh liên tục không được vượt quá mốc cứng đó, trừ quy trình reauthentication/regrant được phép và ghi nhận rõ.

## 7. JWT exp: giá trị và ý nghĩa

Với **JSON Web Token (JWT)**, claim **exp (Expiration Time)** chỉ thời điểm **on or after** token **không được chấp nhận** để xử lý, ngoại trừ một khoảng dung sai nhỏ do clock skew hợp lệ đã được cấu hình. Theo cách biểu diễn JWT, **exp là NumericDate**, thường là số giây tính từ Unix epoch, không phải số mili giây và không phải chuỗi ngày tùy tiện.

Ví dụ **payload minh họa đã che dữ liệu nhạy cảm**:

~~~json
{
  "iss": "https://idp.example.invalid",
  "sub": "iam-user-482",
  "aud": "reports-api",
  "iat": 1795405200,
  "nbf": 1795405200,
  "exp": 1795406100,
  "scope": "reports:read",
  "jti": "token-reference-482-001"
}
~~~

Khoảng chênh **exp - iat = 900 giây**, tức 15 phút. Các con số và URL chỉ là ví dụ, không phải token thật hoặc cấu hình mặc định.

### Những điểm dễ nhầm

- **exp là thời điểm tuyệt đối**, không phải duration.
- **JWT không tự mặc định 15 phút**; issuer/profile/policy quyết định TTL.
- Một JWT tổng quát có thể không chứa exp nếu profile không bắt buộc, nhưng **authorization profile dùng trong hệ thống nên yêu cầu expiration thích hợp**. Trong **OIDC ID Token**, exp là claim bắt buộc.
- Không dùng **thời gian của browser** làm thẩm quyền quyết định token đã hết hạn; quyết định ở verifier/server.
- Một token có payload exp hợp lý nhưng **signature sai, issuer sai hoặc audience không khớp** vẫn phải bị từ chối.

## 8. NumericDate: giây, mili giây, UTC và định dạng

Trong JWT, **NumericDate** biểu diễn giây kể từ mốc Unix epoch theo UTC. Giá trị có thể là số không nguyên trong những trường hợp được quy ước, nhưng nhiều hệ thống thực tế dùng giây nguyên.

~~~text
iat = 1795405200  # số giây Unix epoch (minh họa)
exp = 1795406100
ttl = exp - iat   # 900 seconds

SAI: exp = currentTimeMillis() + 900
SAI: verifier so NumericDate với epoch milliseconds
ĐÚNG: time value cùng đơn vị, kiểm tra tại server
~~~

**Sai đơn vị giây/mili giây** có thể khiến token được xem là còn hạn hàng nghìn năm hoặc hết hạn ngay. Một lỗi khác là cộng **local timezone offset hai lần** khi chuyển sang Unix timestamp. Unix epoch/Instant đã là mốc tuyệt đối; timezone chỉ dùng cho hiển thị hoặc lịch nghiệp vụ.

**Không tin giá trị exp chỉ vì JSON parse được**. Việc kiểm tra expiration chỉ diễn ra sau hoặc trong quy trình xác minh token đáng tin, bao gồm issuer, signature/MAC, algorithm, audience và token type.

## 9. exp, nbf và iat khác nhau thế nào?

| JWT claim | Ý nghĩa | Kiểm tra đúng |
| --- | --- | --- |
| **exp** | Thời điểm token không còn được chấp nhận | Từ chối khi tới/sau exp, có bounded skew allowance nếu policy cho |
| **nbf** (*Not Before*) | Thời điểm sớm nhất token được chấp nhận | Không chấp nhận trước nbf, trừ skew allowance hợp lệ |
| **iat** (*Issued At*) | Thời điểm issuer nói token được phát hành | Hỗ trợ tính age, kiểm tra dữ liệu bất thường và policy về tuổi token |
| **auth_time** (OIDC) | Thời điểm user đã được xác thực | Dùng khi client yêu cầu freshness/reauthentication |
| **jti** | Định danh JWT nếu issuer cung cấp | Hữu ích cho audit/replay detection/denylist nếu contract hỗ trợ |

**iat không phải là expiration**. Token có iat trong quá khứ không tự hết hạn nếu exp vẫn còn, trừ khi hệ thống đặt thêm giới hạn tuổi token. **nbf không thể thay exp**: nó chỉ giới hạn lúc bắt đầu hiệu lực.

**auth_time cũng khác iat**: một ID Token có thể được phát hành sau khi user xác thực từ trước; khi yêu cầu xác thực mới, cần kiểm tra auth_time/max_age hoặc chính sách assurance phù hợp, không suy user vừa nhập MFA từ thời điểm token vừa cấp.

## 10. Clock skew/leeway: dung sai hợp lý, không phải gia hạn quyền

Máy issuer, gateway và resource server có thể lệch đồng hồ. Một số verifier cho phép **leeway nhỏ** quanh exp/nbf để giảm lỗi do clock skew hoặc truyền nhận.

~~~text
T0 = exp của token
Client gửi request ở gần T0
Resource server clock có thể nhanh hoặc chậm so với issuer

Verifier:
    xác minh toàn bộ token và claims
    dùng leeway có giới hạn do policy cấu hình
    ghi log nguồn và độ lệch thời gian khi bất thường
~~~

**Leeway không nên trở thành “thêm 30 phút sử dụng” chỉ vì người dùng đang bận**. Dung sai lớn mở rộng cửa sổ lộ token và làm khó việc đảm bảo cắt quyền tại deadline.

Với **Leaver/compromise**, cần cơ chế thu hồi nhanh theo risk policy; không dựa vào leeway hay TTL để chờ hết hạn. Đồng hồ các node nên được đồng bộ và giám sát, đồng thời log **eventTime/receivedAt** phục vụ điều tra.

## 11. Resource server phải kiểm tra gì ngoài exp?

Một API nhận JWT access token không nên chỉ thực hiện **decode → đọc exp → Permit**. Tùy token profile, các bước cần xem xét:

1. Token có đúng định dạng/loại được API hỗ trợ và không vượt giới hạn parser?
2. **Signature/MAC** được xác minh bằng key đáng tin và thuật toán được cấu hình cho issuer?
3. **iss** có nằm trong trust policy, không lấy key từ URL do token tự chỉ để tin vô điều kiện?
4. **aud** có dành cho đúng resource server/API?
5. **exp**, **nbf**, giới hạn tuổi token và clock skew có hợp lệ?
6. **Client/subject/tenant** có được ràng buộc đúng namespace và loại token?
7. **Scope, role, resource/action authorization** có phù hợp nghiệp vụ hiện hành?
8. **Revocation/security epoch/grant state** có cần kiểm tra theo mức rủi ro không?
9. Nếu là **sender-constrained token**, proof về khóa/client có hợp lệ không?
10. Kết quả phải được thực thi ở **PEP/backend**, có audit và reasonCode phù hợp.

**Không tự chọn thuật toán ký theo header JWT mà bỏ allowlist và key policy**. Cần tránh **algorithm confusion**, nhầm ID Token thành access token và nhầm access token giữa nhiều API/issuer.

Một token được ký hợp lệ **chỉ chứng minh issuer đã phát hành nội dung đó**, không tự chứng minh entitlement còn phù hợp với HR/project state hiện nay.

## 12. JWT access token và opaque access token

| Tiêu chí | JWT/self-contained token | Opaque/reference token |
| --- | --- | --- |
| Resource server kiểm tra | Có thể xác minh chữ ký và claims offline | Thường cần introspection/gateway/stateful lookup theo contract |
| Kiểm tra exp | Token claim exp nếu profile yêu cầu | Metadata active/exp do hệ thống có thẩm quyền trả về |
| Thu hồi sớm | Có thể cần denylist, epoch, online check hoặc TTL ngắn | Có thể cập nhật trạng thái tập trung và introspect |
| Tác động outage | Đôi khi tiếp tục validate offline | Có thể phụ thuộc availability của introspection |
| Freshness quyền | Claims có thể cũ đến khi token hết hạn | Có thể kiểm tra trạng thái cập nhật hơn nếu hệ thống làm đúng |
| Rủi ro | Token bearer bị lộ, cache/policy stale | Introspection cache stale, điểm phụ thuộc tập trung |

**Opaque token không phải chuỗi ngẫu nhiên có thể tự giải mã thành exp**. Resource server phải dùng contract của issuer, thường qua introspection hoặc token validation service.

**JWT không mặc định luôn được chấp nhận cho đến exp**. API có thể kiểm tra thêm online entitlement/revocation. Ngược lại, **opaque token cũng có thể bị cache quá lâu** khiến quyết định active không còn mới. Cả hai đều cần một chính sách về **thời gian chấp nhận trạng thái cũ**.

## 13. Expiration khác revocation, logout và disable account

| Cơ chế | Ý nghĩa | Điều có thể vẫn tồn tại |
| --- | --- | --- |
| **Expiration** | Token tự hết hiệu lực theo mốc thời gian | Phiên khác, refresh token hoặc entitlement |
| **Revocation** | Issuer/hệ thống có thẩm quyền đánh dấu token/grant không còn được dùng | Token đã cấp ở resource server không hỗ trợ kiểm tra trạng thái |
| **Logout** | Kết thúc một hoặc nhiều phiên tùy app/IdP | API key, access token khác hoặc local SaaS session |
| **Disable user** | Không cho account tiếp tục hoạt động theo policy IdP | PAT/local account, JWT offline, device credential |
| **Remove entitlement** | Rút quyền nghiệp vụ, role/group/ACL | Token cũ chứa claim quyền hoặc cache |
| **Rotate signing key** | Thay key dùng ký token | Token cũ có thể còn được chấp nhận trong overlap window |
| **Revoke refresh grant** | Không cho cấp access token mới qua grant đó | Access token đã cấp có thể còn hạn |
| **Expire certificate** | Certificate đã qua NotAfter | Phiên TLS/token khác chưa chắc bị đóng |

**Expiration là điều kiện về thời gian; revocation là điều kiện về trạng thái hiện hành**. Khi quyền cần chấm dứt ngay, không nên lấy “token sẽ hết hạn sau 15 phút” làm bằng chứng đã thu hồi tại thời điểm chính sách yêu cầu.

## 14. Phân loại các mốc hết hạn cần thiết kế

Một ứng dụng có thể quản lý đồng thời:

~~~text
userSessionIdleTimeout      -> không hoạt động quá lâu
userSessionAbsoluteTimeout  -> giới hạn cứng của phiên
accessTokenExpiresAt        -> exp của token gọi API
refreshTokenIdleExpiresAt   -> refresh grant không được sử dụng
refreshTokenAbsoluteEnd     -> hết hạn cứng của grant
authenticationFreshness     -> khoảng được chấp nhận từ auth_time
entitlementEndAt            -> mốc quyền nghiệp vụ bị thu hồi
employmentEndAt             -> quan hệ làm việc đã hết
clientCredentialExpiresAt   -> key/certificate/secret hết hạn
emergencyAccessEndAt        -> thời hạn của JIT/PAM lease
~~~

**Không dùng một biến “SESSION_TIMEOUT” cho tất cả**. Nếu entitlementEndAt đến trước access token exp, resource server phải xử lý theo chính sách cắt quyền; nếu refresh token hết hạn nhưng access token vẫn còn trong hạn, hai kết quả có thể khác nhau.

Thời hạn tương đối như “hai ngày làm việc” phải được **chuyển sang mốc hiệu lực theo policy và calendar**; token exp bản thân thường là thời điểm tuyệt đối, không mang khái niệm ngày làm việc.

## 15. Chọn TTL theo rủi ro và khả năng kiểm soát

Không có **một TTL phổ quát** phù hợp với mọi OAuth access token, client, hệ thống dữ liệu hay mức độ rủi ro.

| Ngữ cảnh | Các yếu tố cần cân nhắc |
| --- | --- |
| **API dữ liệu thông thường** | Token storage, risk level, refresh UX, online revocation |
| **Production administrator** | JIT window, PAM session, step-up, revocation nhanh |
| **Tài chính/PII/secret** | Data classification, action sensitivity, fresh entitlement checks |
| **Mobile/offline client** | Khả năng kết nối, credential theft, device-bound token |
| **Browser client** | XSS/session fixation, BFF/cookie strategy, token exposure |
| **Machine-to-machine** | Token acquisition automation, workload identity, issuer availability |
| **IoT/OT offline** | Khả năng đồng bộ thời gian/revocation và an toàn vận hành |
| **Cross-tenant integration** | Audience/resource specificity, sponsor và contract end |
| **Break-glass/emergency** | Hạn ngắn, audit độc lập, hard cutoff và containment |

TTL ngắn hơn thường giảm cửa sổ token lộ **nhưng tăng tần suất cấp lại token**, làm tăng phụ thuộc authorization server và rủi ro mất sẵn sàng. TTL dài hơn có thể giảm tải token endpoint nhưng tăng thời gian token bị đánh cắp hoặc claims cũ còn tác dụng.

Một ví dụ **giả định**, không phải mặc định chuẩn: access token nội bộ có thể có TTL 10–20 phút; phiên quản trị đặc quyền có thể bị giới hạn thêm bằng JIT lease ngắn và kiểm tra live policy; còn M2M token có thể có TTL phù hợp với khả năng lấy mới tự động. Chọn giá trị dựa trên **threat model và khả năng revoke**, không sao chép tùy tiện từ sản phẩm khác.

## 16. Cấp token mới: TTL phải bắt nguồn từ policy đáng tin

Authorization server thường phải xét:

- Client identity, grant type và chính sách đăng ký client.
- User identity/assurance nếu có user.
- Employment/sponsorship và access eligibility.
- Requested audience/resource và scopes.
- Role/ABAC conditions, risk classification và consent khi áp dụng.
- Client type và mức bảo vệ credential.
- Session/grant absolute lifetime còn lại.
- Chính sách token binding/revocation.

Ví dụ ý tưởng:

~~~text
effectiveTtl = min(
    allowedAccessTokenTtlForClient,
    allowedTtlForResourceSensitivity,
    remainingGrantLifetime,
    remainingApprovedAccessWindow
)

if effectiveTtl <= 0:
    denyTokenIssuance()
else:
    token.exp = trustedNow + effectiveTtl
~~~

Đây là **mã giả**. Một số hệ thống không ràng buộc trực tiếp exp với entitlementEndAt mà dùng online authorization; khi đó phải đảm bảo **resource server kiểm tra quyền hiện hành**. Quan trọng là không để token mới có hiệu lực vượt căn cứ đã được duyệt nếu chính sách cấm.

## 17. Refresh token: xin access token mới không phải kéo dài token cũ

**Refresh token** cho phép client yêu cầu access token mới từ authorization server, khi client và grant đáp ứng điều kiện. Một chu trình điển hình:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>AS: Authorization grant hợp lệ
    AS-->>C: Access Token A + Refresh Token R1 (nếu được cấp)
    C->>RS: Dùng A trước exp
    RS-->>C: Access theo policy
    Note over C,RS: A gần hết hạn hoặc đã hết hạn
    C->>AS: Refresh với R1, client auth nếu yêu cầu
    AS->>AS: Kiểm tra grant, revocation, client, scope và rotation
    AS-->>C: Access Token B + Refresh Token R2 nếu rotation
    C->>RS: Gửi B
    RS-->>C: Quyết định dựa trên B và authorization hiện hành
~~~

**Không phải OAuth grant nào cũng cấp refresh token**, và **client credentials thường không cần refresh token**: workload tự xin access token mới theo client authentication/trust. **Grant đã hết hạn hoặc bị revoke** không được tự sống lại chỉ vì client còn giữ một refresh token cũ.

Việc **access token A hết hạn** có thể dẫn đến refresh hợp lệ, nhưng không chứng minh user vừa được MFA lại. Với hành động yêu cầu fresh authentication, client/IdP có thể phải thực hiện **reauthentication hoặc step-up**.

## 18. Refresh-token rotation và phát hiện reuse

**Refresh-token rotation** là cơ chế phát hành refresh token mới khi client sử dụng token hiện tại, đồng thời làm token cũ không còn hợp lệ. Nó giảm rủi ro **một token bị sao chép có thể được tái sử dụng lâu dài**, và có thể hỗ trợ phát hiện reuse.

~~~text
R1 (ACTIVE) -> refresh thành công -> R2 (ACTIVE)
R1 -> INVALIDATED
R2 -> refresh thành công -> R3 (ACTIVE)
R2 -> INVALIDATED

Reuse:
    R1 được trình lại sau khi đã bị invalidated
    -> có thể là replay/credential theft hoặc client retry bất thường
    -> xử lý theo family policy, log, revoke và reauthentication nếu cần
~~~

**Phát hiện reuse không tự chứng minh chắc chắn bên nào là attacker**. Retry đồng thời, mất response, nhiều tab hoặc các instance client chia sẻ cùng refresh token có thể tạo cùng triệu chứng. Thiết kế cần **atomic rotation, token family state, concurrency handling và audit**.

Với **public clients**, thực hành an toàn hiện đại thường yêu cầu **refresh-token rotation hoặc sender constraint** phù hợp với môi trường và profile; chính sách triển khai phải xét khả năng token bị trộm, client type và các tiêu chuẩn áp dụng.

## 19. Refresh-token family: inactivity và absolute maximum

Một hệ thống có thể dùng **token family** để quản lý nhiều refresh token được tạo từ cùng grant.

| Thuộc tính | Công dụng |
| --- | --- |
| **familyId/grantId** | Theo dõi quan hệ các lần rotate |
| **currentTokenRef** | Token đang được phép dùng |
| **lastUsedAt** | Phục vụ inactivity timeout |
| **absoluteExpiresAt** | Không refresh vượt giới hạn cứng |
| **revokedAt/reason** | Xác định grant bị vô hiệu |
| **clientBinding** | Gắn family với client/credential theo policy |
| **rotationVersion** | Chống race và retry |
| **riskEventRef** | Ghi nhận reuse/compromise hoặc chính sách đặc biệt |

**Mỗi lần rotate không được mặc định đẩy xa absoluteExpiresAt vô hạn**. Nếu policy giới hạn grant tối đa 30 ngày, việc phát R2/R3 chỉ làm mới token trong **giới hạn grant đã duyệt**, trừ quy trình reauthorization/reauthentication riêng.

Khi một refresh token trong family bị nghi replay, chính sách có thể revoke cả family để cắt quyền, nhưng phải cân nhắc tác động và cung cấp đường **reauthentication an toàn**. Không log raw refresh token để điều tra.

## 20. Storage và token exposure trên từng loại client

| Client | Rủi ro | Hướng kiểm soát |
| --- | --- | --- |
| **Browser SPA** | XSS lấy access/refresh token nếu lưu trực tiếp trong JavaScript-readable storage | Giảm phạm vi token trong browser, cân nhắc BFF/session cookie an toàn |
| **Backend/BFF** | Lộ session cookie hoặc server-side token store | HttpOnly/Secure/SameSite theo nhu cầu, CSRF protection, server-side storage |
| **Native mobile** | Device compromise, backup credential, app extraction | OS secure storage, PKCE, sender constraint nếu hỗ trợ |
| **Confidential server** | Secret leak từ config/log, CI/CD | Vault, managed identity, short-lived tokens, key rotation |
| **CLI** | Token lưu cache trên máy dùng chung | Permission của file, OS keystore, logout/revoke |
| **IoT/OT device** | Khó quản lý key và đồng hồ | Hardware key nếu có, gateway, TTL và offline policy |

**Token expiration không sửa được lỗ hổng lộ token trong log hoặc XSS**. Nếu bearer token bị đánh cắp, kẻ tấn công có thể dùng ngay trong thời hạn; cần **bảo vệ storage, sender constraint khi phù hợp và anomaly detection**.

Không đặt **refresh token hoặc client secret** trong URL, query string, telemetry, screenshot hay general-purpose application log. Nếu dùng cookie cho session, phải đánh giá **CSRF, same-site behavior, domain/path scope và logout semantics**.

## 21. SSO session, application session và token phải được quản lý riêng

Trong hệ thống SSO, có thể cùng tồn tại:

1. **Phiên tại IdP**: user đăng nhập với authentication assurance nhất định.
2. **Phiên tại ứng dụng**: cookie hoặc session server-side độc lập.
3. **ID token**: kết quả authentication được client sử dụng tại một thời điểm.
4. **Access token**: dùng để gọi API đúng audience.
5. **Refresh token/grant**: dùng tại authorization server để lấy token mới.
6. **Phiên tại resource/target SaaS**: có thể tồn tại ngoài IdP.

~~~text
SSO session: ACTIVE
App cookie: ACTIVE
Access Token A: EXPIRED
Refresh grant: ACTIVE
Target local session: UNKNOWN

=> Client có thể cần xin Access Token B; không được tiếp tục dùng A.
=> Nếu user bị Leaver, phải xử lý cả grant/session/target access.
~~~

**Sign-out ở một ứng dụng không tự sign-out mọi ứng dụng**, và **xóa cookie trong browser không bảo đảm refresh token phía server đã bị revoke**. SSO logout, front/back-channel logout và session revocation tùy sự hỗ trợ/contract của nền tảng.

## 22. OIDC ID token expiration và authentication freshness

**OIDC ID Token** phục vụ cho **OpenID Connect Relying Party** xác minh kết quả người dùng được OpenID Provider xác thực, với các claim và kiểm tra dành cho ID token.

Một OIDC client thường cần xác minh:

- **iss, aud, exp, iat** theo ID Token validation profile.
- Signature/MAC theo cấu hình client/issuer và thuật toán được phép.
- **nonce** khi flow và client yêu cầu để chống token injection/replay.
- **azp** và các quy tắc audience liên quan khi áp dụng.
- **auth_time/acr/amr** nếu chính sách yêu cầu fresh/step-up authentication.

**ID Token hết hạn không tự đồng nghĩa user session ở IdP đã kết thúc**; ứng dụng có thể thực hiện giao thức phù hợp để xác thực lại hoặc duy trì session tùy chính sách. Ngược lại, **ID Token còn hạn không dùng để thay access token gọi API**.

Khi cần hành động nhạy cảm, **max_age hoặc step-up** giúp xác định freshness của việc xác thực con người; không nên dùng “access token mới được phát hành” như bằng chứng user vừa nhập MFA.

## 23. OAuth flow ảnh hưởng vòng đời token

| Luồng/cơ chế | Tình huống | Điều cần lưu ý về expiration |
| --- | --- | --- |
| **Authorization Code + PKCE** | Web/native/public client phù hợp | Access token hết hạn có thể cần refresh hoặc authorization mới |
| **Client Credentials** | Service-to-service không có user tương tác | Client tự lấy token mới theo credential/trust hợp lệ |
| **Device Authorization Grant** | Thiết bị hạn chế nhập liệu | Mã user/device và polling có thời hạn riêng; không nhầm với device registration |
| **Token Exchange** | Uỷ quyền giữa các service khi được hỗ trợ | Token mới có audience/scope/TTL riêng và ràng buộc nguồn |
| **Refresh Token Grant** | Lấy access token mới | Cần kiểm tra grant, client, rotation và absolute lifetime |
| **JWT/Client Assertion** | Chứng minh client bằng assertion có chữ ký | Assertion có thời hạn riêng, chống replay và đúng audience |

**Không sử dụng grant cũ hoặc flow không được khuyến nghị** chỉ vì dễ lấy refresh token dài hạn. Chọn cơ chế theo mô hình trust, public/confidential client, môi trường và khả năng bảo vệ credential.

**Device authorization mã xác minh hết hạn** không đồng nghĩa thiết bị vật lý bị xóa đăng ký, tương tự **token exchange thất bại** không tự chứng minh account đã Leaver.

## 24. Machine-to-machine: access token ngắn hạn nhưng trust phải chặt

Với **service account, managed identity, Kubernetes workload, CI/CD và OAuth client credentials**, vòng đời token khác user tương tác:

~~~text
Workload identity validated
    -> issuer/trust policy verifies source
    -> obtains short-lived token for target audience
    -> calls API within scope/tenant
    -> token expires
    -> obtains new token if workload and trust remain eligible
~~~

Review nên kiểm tra **issuer, subject/namespace/repository, audience, allowed roles, TTL, signing keys, client credential và owner**. Token TTL ngắn không cứu được trust policy kiểu **mọi repository có thể assume production-admin**.

Nếu service đã decommission, **không cấp token mới** và phải kiểm tra những token đã cấp, phiên, service principals và direct grants còn khả năng truy cập không. Owner nhân sự đã Leaver không tự chứng minh workload cũng phải bị xóa; cần **chuyển owner và rotate/revoke credential từng do người cũ kiểm soát**.

## 25. Bearer token và sender-constrained token

**Bearer token** có thể được sử dụng bởi bên nắm giữ chuỗi token, nếu resource server không có kiểm soát bổ sung. Khi token bị lộ, TTL chỉ hạn chế thời gian bị dùng trái phép.

**Sender-constrained access token** gắn token với khóa hoặc chứng cứ của client. Ví dụ một số kiến trúc dùng:

- **Mutual TLS (mTLS)** để ràng buộc access token với client certificate khi các bên hỗ trợ.
- **DPoP** (Demonstrating Proof of Possession) để ràng buộc access token với public key và yêu cầu proof trên request phù hợp.

Ở resource server, ngoài kiểm tra exp/issuer/audience/scope còn cần **đúng khóa, request method/URI binding và replay protection** theo giao thức. **DPoP proof có thời gian riêng không thay exp của access token**; access token hết hạn vẫn không hợp lệ dù proof mới.

**Sender constraint không tự đảm bảo workload an toàn**: malware kiểm soát process đang giữ private key có thể khiến client ký request trong thời hạn. Cần bảo vệ key, giảm scope, audit và revocation.

## 26. Token expiration khác hạn của client secret, private key và certificate

**Credential của client** thường dùng để **xin token**, còn **access token** dùng để gọi resource server. Hai thứ có thời hạn và revocation khác nhau.

| Đối tượng | Ví dụ | Điều xảy ra khi hết hạn | Cần xử lý riêng |
| --- | --- | --- | --- |
| **Access token** | JWT tới exp | API không được nhận token đó khi hết hạn | Những access token khác và entitlement |
| **OAuth client secret** | Secret dùng ở token endpoint | Client có thể không chứng thực được để lấy token mới | Token đã cấp, key/secret cũ bị sao chép |
| **Signed client assertion** | JWT xác thực client | Assertion cũ không còn dùng được | Key ký và client policy |
| **X.509 certificate** | mTLS client certificate | TLS verifier không nên chấp nhận certificate ngoài validity window | CRL/OCSP/revocation, TLS session hiện có |
| **Private key** | Khóa gắn với device/workload | Bản thân key không có exp theo cách giống JWT | Chứng chỉ, trust mapping, compromise và rotation |
| **PAT/API key** | Token do SaaS phát hành | Hành vi phụ thuộc API provider | Key inventory, revoke/readback và API sessions |
| **Refresh token** | R2 của OAuth grant | Không xin được access token mới bằng R2 nếu hết hiệu lực | Access token còn hạn và grant family |

**Cấp certificate mới không tự làm access token cũ hết hạn**, và **client secret bị thu hồi không tự vô hiệu access token JWT đã cấp** nếu API chưa kiểm tra trạng thái liên quan.

Vì vậy, review phải quản lý các vòng đời riêng: **credential issuance/rotation, token issuance/expiry, entitlement validity, session lifetime và target access enforcement**.

## 27. Expiration trong offline access và mạng không liên tục

Một số ứng dụng mobile, edge, IoT hoặc OT có thể cần hoạt động khi thiếu kết nối. Điều này tạo căng thẳng giữa **sẵn sàng vận hành** và **nhu cầu cắt quyền sớm**.

Các phương án cần đánh giá:

- Access token có TTL đủ phù hợp với kết nối, nhưng không dài quá risk appetite.
- **Local offline capability** chỉ cho phép hành động ít rủi ro, không tự trao quyền production admin.
- **Token scope và audience cực hẹp** cho môi trường ngắt kết nối.
- Đồng hồ thiết bị có cơ chế xác thực/sync phù hợp; **không tin đồng hồ client tự thay đổi**.
- Khi quay online, bắt buộc **refresh entitlement/posture** và gửi audit backlog.
- Với quyền có hạn cứng, cần thiết kế phương án **không thể tiếp tục hành động sau cutoff** trong khả năng hệ thống, hoặc nêu rõ rủi ro offline chưa thể chặn tức thời.

**Không nên đơn giản cấp bearer token một năm cho thiết bị offline** mà bỏ qua nguy cơ mất máy hoặc bị sao chép credential. Với hệ thống an toàn vận hành đặc thù, giải pháp cần được threat-model theo loại hành động và khả năng cắt quyền.

## 28. Refresh đồng thời: multi-tab, nhiều pod và retry

Một lỗi thường thấy là nhiều tab trình duyệt hoặc nhiều instance backend cùng dùng một refresh token:

~~~text
10:00:00.000  Tab A dùng R1 để refresh
10:00:00.010  Authorization server rotate R1 -> R2
10:00:00.020  Tab B cũng gửi R1 vì chưa biết R2
10:00:00.030  R1 đã invalidated; server phát hiện reuse
~~~

Nếu không thiết kế concurrency, hệ thống có thể **log tất cả người dùng ra ngoài** hoặc vô tình mở cửa sổ replay quá rộng.

Các hướng kiểm soát:

1. **Single-flight refresh** trong phạm vi client: một lần refresh cho cùng grant tại một thời điểm.
2. **Centralized token manager** với backend/BFF hoặc store phiên bản hóa khi kiến trúc phù hợp.
3. **Atomic rotation** ở authorization server, không để hai request cùng nhận hai nhánh refresh hợp lệ ngoài policy.
4. **Idempotent retry/recovery** theo contract của provider; không tự sáng tạo grace window không giới hạn.
5. **Token family revocation và alert** khi reuse đáng ngờ.
6. **Không log token thô** để debug lỗi đồng bộ; chỉ dùng requestId, token reference và state/version.

Không có chiến lược chung cho mọi sản phẩm. Một số authorization servers có cơ chế xử lý refresh race riêng; client cần tuân theo contract thay vì giả định “reuse trong 5 phút luôn được chấp nhận”.

## 29. Cơ chế thu hồi sớm ngoài exp

Những lựa chọn kiến trúc chính:

| Cơ chế | Cách hoạt động | Đánh đổi |
| --- | --- | --- |
| **Short-lived access token** | Chờ exp nhanh hơn | Vẫn có cửa sổ còn hạn |
| **Token introspection** | API hỏi authorization server về trạng thái active | Phụ thuộc latency/availability và cache |
| **Token denylist/revocation list** | Resource server kiểm tra token reference bị chặn | Cần phân phối và expiry của denylist |
| **Subject/session security epoch** | Từ chối token phát trước mốc revoke/credential change | Cần trạng thái hiện hành ở verifier và policy |
| **Grant/family revocation** | Cấm refresh và token cấp mới từ grant | Access token cũ có thể còn hiệu lực nếu API không check |
| **Event-driven session invalidation** | Gửi sự kiện revoke đến gateway/app | Event delivery/cached state có thể trễ |
| **Online entitlement/ABAC check** | Mỗi hành động hoặc một số hành động hỏi trạng thái quyền | Tăng phụ thuộc PIP/PDP, cần cache strategy |
| **Sender constraint + key revocation** | Khó dùng token nếu không nắm khóa tương ứng | Key/nonce/cert revocation vẫn cần truyền tới verifier |

**Không một phương án nào tự giải quyết mọi trường hợp**. Một hệ thống nhạy cảm có thể cần **TTL ngắn + online policy check + event-driven revocation + audit**. Đối với quyền thông thường, tổ chức có thể chấp nhận độ trễ tối đa cụ thể dựa trên rủi ro và SLA.

Nếu policy yêu cầu quyền bị chặn ngay sau Leaver, phải có **enforcement ở nơi chấp nhận token**. Chỉ đổi trạng thái ở IAM database mà API không kiểm tra là chưa hoàn tất.

## 30. Security epoch và token version theo danh tính

Một cách để cắt quyền của token đã phát là lưu **mốc thay đổi bảo mật** hoặc **token version** từ nguồn có thẩm quyền, rồi kiểm tra ở resource server.

Ví dụ:

~~~text
Token claims:
    sub = user-482
    iat = 10:00
    exp = 10:15

Identity security state:
    revokedBefore = 10:07

Resource server at 10:08:
    token iat < revokedBefore
    -> DENY ngay cả khi exp=10:15
~~~

Triển khai thật cần lưu mốc theo **Instant, source authority, tenant và relation** đúng. Với NumericDate giây, ranh giới **iat == revokedBefore** có thể không phân biệt hai issuance cùng giây; có thể dùng **sessionId/tokenVersion/securityVersion** theo contract để tránh lỗi. Không dùng thời điểm máy client làm nguồn để hợp thức hóa token cũ.

**Epoch check chỉ hiệu quả khi API nhận được trạng thái đủ mới**. Một cache trạng thái user có TTL 30 phút sẽ không đáp ứng SLA cắt quyền trong một phút, dù đã thêm trường revokedBefore vào database.

## 31. Token cache và dữ liệu authorization bị cũ

Resource server có thể cache:

- Kết quả **token introspection**.
- **JWKS/public signing keys**.
- **User/group/role memberships**.
- **PDP decisions**.
- **Employment/tenant mapping**.
- **Security epoch/revocation state**.

Mỗi cache có **mục tiêu và giới hạn thời gian riêng**.

Ví dụ:

| Cache | Lợi ích | Khi sai lệch nguy hiểm |
| --- | --- | --- |
| JWKS | Tránh tải key cho từng request | Không nhận key mới hoặc giữ key bị mất trust quá lâu |
| Introspection | Giảm tải authorization server | Tiếp tục tin active sau revoke |
| Role/group | Tăng tốc kiểm tra permission | Mover vẫn được giữ role cũ |
| PDP Permit | Giảm latency ở API | Permit cũ vẫn được dùng sau khi scope đổi |
| Session state | Tránh lookup thường xuyên | Leaver session còn tác dụng |

**Không dùng TTL cache dài hơn mức chấp nhận quyền tồn dư** nếu hệ thống cần cắt quyền nhanh. Với resource nhạy cảm, có thể cần event-driven invalidation, no-cache trên action đặc quyền hoặc forced online check.

**Token exp phải được kiểm tra mỗi lần quyết định**, ngay cả khi API cache kết quả chữ ký/validation. Không dùng cache Permit từ khi token còn hạn để tiếp tục cho phép token đã hết hạn.

## 32. Joiner: không cấp token có quyền trước mốc hợp lệ

Trong **Joiner lifecycle**, người mới có thể có account được tạo từ trước start date. Cần phân biệt **identity provisioned** với **employment/entitlement effective**.

Quy trình:

1. **HRIS/sponsor** cung cấp personId, employmentRelationId, start date, organization và trạng thái xác minh.
2. **IdP/IAM** chuẩn bị account/SSO/MFA theo quy định, nhưng không tự cấp quyền truy cập nhạy cảm trước ngày hiệu lực.
3. **IGA/RBAC/ABAC** quyết định birthright entitlement có phạm vi rõ.
4. **Authorization server** chỉ phát token/scope đúng trạng thái eligibility và thời gian hiệu lực.
5. **Resource server** kiểm tra audience, token validity và resource policy.
6. Sau khi cấp, **readback** entitlement và kiểm thử quyền được phép/bị cấm.

Ví dụ:

~~~text
Account created:         2026-11-29
Employment startAt:      2026-12-01 09:00
Access entitlement:      ReportViewer after startAt
Token issued on 11/29:   Không được mang quyền ReportViewer nếu chưa hợp lệ
Report API before start: DENY
~~~

**Token chưa hết hạn không làm một entitlement có hiệu lực sớm**. Các claim employment/role trong token cần phản ánh policy; API đặc biệt nhạy cảm có thể kiểm tra trực tiếp trạng thái hiện hành.

## 33. Mover: thay role trong khi token cũ vẫn còn hạn

**Mover** thường làm một người **mất quyền dự án cũ và nhận quyền dự án mới**. Nếu access token cũ chứa role AtlasAdmin nhưng người dùng chuyển sang Nova, sẽ có nguy cơ token còn cho phép action Atlas đến exp.

| Trạng thái | Thời điểm | Mong muốn |
| --- | --- | --- |
| Có role AtlasAdmin | Trước Mover | Permit theo policy Atlas |
| HRIS/project event Mover có hiệu lực | T0 | Thu hồi expected Atlas, đánh giá Nova |
| Token cũ exp sau T0 | T0 đến exp | API phải áp dụng revocation/freshness phù hợp cutoff |
| Token mới | Sau T0 | Chỉ chứa/cho phép quyền hiện hành |
| Local SaaS ACL còn AtlasAdmin | Sau T0 | Finding quyền tồn dư, remediation |

Hệ thống cần:

- Tính **full expected access delta**, không chỉ thêm role mới.
- Revoke/invalidating grant và security epoch khi chính sách yêu cầu.
- Cập nhật **SCIM Group/role, IdP groups, direct ACL và target local roles**.
- Không để **old refresh token** xin lại scope AtlasAdmin sau Mover.
- Kiểm tra token cũ không còn được dùng để thao tác ngoài quyền cho phép.
- Gắn trạng thái với **employment relation/tenant**, tránh xóa nhầm quyền độc lập ở tổ chức khác.

Một approval cũ hoặc event cấp quyền retry **không được mở lại AtlasAdmin** sau khi đã Mover. Các job provisioning phải revalidate source version và trạng thái đích.

## 34. Leaver: chặn quyền sớm hơn exp khi cần

Trong **Leaver lifecycle**, sự kiện kết thúc quan hệ từ nguồn có thẩm quyền phải kích hoạt **cắt quyền theo deadline chính sách**.

Ví dụ:

~~~text
10:00  HRIS xác nhận termination có hiệu lực
10:01  IdP user disabled; refresh/session grants revoked
10:02  IGA phát lệnh revoke groups, roles, local SaaS grants
10:03  Security epoch/session deny propagated tới API
10:04  Negative test: token cũ gọi API -> DENY
10:30  Access token cũ có exp tại 10:30
~~~

Ở ví dụ này, **mốc cần đạt là 10:04 hoặc SLA theo policy**, không phải chờ token exp 10:30. Những hành động cần xét:

1. Chặn cấp token mới và refresh cho quan hệ đã chấm dứt.
2. Kết thúc IdP/app sessions và revoke grants phù hợp.
3. Thu hồi SCIM User/Group, application role, direct ACL.
4. Xử lý **PAT, SSH key, local account, API key, device credential** từng dùng bởi người đó.
5. Với JWT offline, dùng **denylist/epoch/online check hoặc cơ chế tương đương** để đạt cutoff.
6. Ngăn job/event Joiner/Mover cũ **regrant**.
7. **Readback + negative effective-access test** tại resource server theo phạm vi.

**SCIM active=false không tự làm mọi JWT đã phát hành hết hạn**. Resource server vẫn phải kiểm tra trạng thái cần thiết; ngoài ra có thể có phiên SaaS hoặc session cloud độc lập.

Nếu person có quan hệ hợp lệ ở **org-b** nhưng chấm dứt ở **org-a**, cần revoke **đúng quan hệ và tenant**, không mặc định xóa toàn bộ danh tính/person hoặc quyền độc lập không liên quan.

## 35. Contractor, partner, guest và consent có hạn

Tài khoản bên ngoài thường có **sponsor, contractEndAt hoặc approvedAccessEndAt**. Token expiration phải phối hợp với những mốc này.

Ví dụ đối tác được đọc dữ liệu trong dự án đến **17:00 ngày 30/11**. Authorization server không nên phát token có quyền vượt mốc đó nếu hệ thống chỉ dựa vào token exp để thực thi cutoff. Nếu token còn hạn dài hơn vì kiến trúc hiện tại, **resource server phải kiểm tra endAt và sponsorship state**.

Một thiết kế cần:

- Liên kết token/authorization với **guest identity, sponsor và tenant**.
- Kiểm tra expiry của **contract, access request, group membership**.
- Revalidate khi sponsor đổi hoặc dự án kết thúc.
- Có **revocation plan** khi hợp đồng hết hạn sớm.
- Không tự cho phép refresh/renewal chỉ vì app còn session.

**Token có hạn 10 phút không thay thế sponsor review**, còn sponsor approval cũng không thay token validation. Hai cơ chế bảo vệ những ranh giới khác nhau.

## 36. Non-human account: token hết hạn nhưng service vẫn tiếp tục

Với **service principal, workload federation, CI/CD bot, RPA và integration account**, access token có thể được tự lấy mới trong suốt đời dịch vụ.

| Biến động | Điều cần làm |
| --- | --- |
| **Access token exp** | Workload xin token mới nếu principal/trust còn hợp lệ |
| **Client secret exp** | Rotate/migrate credential có kế hoạch, không tự dùng secret hết hạn |
| **Certificate exp** | Renew/reissue và kiểm tra mTLS trust trước cutoff |
| **Role/tenant thay đổi** | Xin token scope mới theo policy, cắt token/grant cũ nếu cần |
| **Workload decommission** | Dừng issuance, revoke trust/role/credential, xử lý session/token |
| **Service owner Leaver** | Chuyển owner, rà soát shared secret/PAT và quyền của người cũ |
| **Trust policy compromised** | Revoke/contain và thu hẹp subject/issuer/audience |

Một service **không bị “logout” theo cách người dùng tương tác**. Cần xác định **principal, owner, credential issuer, trust subject, grant và resource server** để ngăn workload xin token mới sau khi bị chấm dứt.

**Token ngắn hạn không tự an toàn khi trust rộng**: nếu một repository bất kỳ được assume production role, attacker có thể liên tục xin token mới hợp lệ. Review trust và quyền có thể quan trọng hơn chỉ giảm access-token TTL.

## 37. Emergency access/PAM: expiration phải gắn lease và session

Trong **Emergency Access**, một **JIT/PAM lease** thường có hạn rõ và audit riêng. Ví dụ operator được cấp quyền tạm 30 phút để khôi phục production.

Một kịch bản có:

~~~text
Emergency approval: valid for incident INC-2026-041
PAM lease:         10:00 -> 10:30
Access token A:    10:00 -> 10:10
Access token B:    10:10 -> 10:20
Access token C:    10:20 -> 10:30

After 10:30:
    No new privileged token from this lease
    Privileged API actions must be DENY
    Existing privileged sessions/caches require cleanup/checks
~~~

**Không cho một lần refresh gần 10:30 tạo token đặc quyền có quyền đến 11:00** nếu chính sách JIT yêu cầu cắt quyền ở 10:30. Khi cần kéo dài, phải có **exception/approval mới** và audit.

**PAM session ended không chứng minh mọi long-lived PAT, token hoặc direct ACL đã bị thu hồi**. Cần kiểm tra quyền còn lại tại target và ghi log hành động phát sinh trong phiên, bao gồm tạo credential mới.

## 38. SCIM, SSO, RBAC/ABAC và Token expiration phối hợp thế nào?

| Thành phần | Trách nhiệm | Không được nhầm |
| --- | --- | --- |
| **HRIS/sponsor** | Quan hệ làm việc, start/end, owner | Không trực tiếp quyết định mọi token JWT |
| **IAM/IGA** | Expected entitlements, approval, JML, review | Approval status không chứng minh API Deny |
| **IdP/SSO/OIDC** | Authentication, sessions, ID tokens và claims | ID Token không dùng gọi API |
| **OAuth Authorization Server** | Access/refresh token issuance, grant, expiry, revocation | Revoke grant không tự cập nhật mọi local ACL |
| **SCIM Service Provider** | User/Group provisioning/deprovisioning | SCIM update không tự hết hạn mọi token đã cấp |
| **RBAC** | Role permissions và hierarchy | Role trong token có thể stale |
| **ABAC/PBAC/PDP** | Policy theo identity, resource, action, environment, time | Policy dữ liệu cũ vẫn có thể tạo Permit sai |
| **PEP/resource server** | Validate token, enforcement, audit | Token exp hợp lệ không thay object-level authorization |
| **Vault/PKI** | Client credentials, keys, certificate lifecycle | Key/cert expiry khác exp của access token |
| **Audit/SIEM** | Phát hiện token misuse, revoke propagation và quyền tồn dư | Không có log không chứng minh không có hành động |

**Access token còn hạn** là điều kiện cần nhưng **không đủ** cho quyền truy cập. **Access token hết hạn** là điều kiện để từ chối chính token đó; hệ thống vẫn phải xử lý việc cấp token mới và những grant khác.

## 39. HTTP 401, 403 và lỗi token

Khi resource server dùng **Bearer access token**:

| Tình huống | Phản hồi thường phù hợp | Ý nghĩa |
| --- | --- | --- |
| Thiếu access token cho protected endpoint | **401 Unauthorized** cùng authentication challenge | Cần token/xác thực phù hợp |
| Access token hết hạn hoặc không hợp lệ | **401** và Bearer error **invalid_token** khi phù hợp | Client không nên retry y nguyên token cũ |
| Token đúng nhưng thiếu scope | **403 Forbidden** với **insufficient_scope** theo contract | Có thể phải xin grant đúng scope nếu được phép |
| Token đúng scope nhưng resource ABAC Deny | **403** hoặc phản hồi che giấu resource theo policy | Quyền nghiệp vụ không được cho |
| Authorization server tạm lỗi | Theo API contract, có thể **503** | Không được fail-open Permit |
| Refresh token hết hạn/revoked tại token endpoint | Lỗi OAuth như **invalid_grant** theo điều kiện | Cần reauthorization hoặc cơ chế phục hồi |

Ví dụ token hết hạn:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="reports-api", error="invalid_token"
Cache-Control: no-store

{"code":"ACCESS_TOKEN_EXPIRED"}
~~~

Response này là **minh họa**; chi tiết thông báo và challenge phụ thuộc API/security contract. Không trả raw token, server secret hoặc dữ liệu xác thực nhạy cảm trong error.

**Không coi 403 là “token hết hạn”** nếu thực chất token hợp lệ nhưng không có quyền. Client có thể refresh một lần theo hợp đồng khi nhận 401 invalid_token, nhưng **không được lặp refresh vô hạn**, và refresh không thể sửa một quyết định **SoD/ABAC Deny**.

## 40. State machine: access token và refresh grant

~~~mermaid
stateDiagram-v2
    [*] --> ISSUED
    ISSUED --> ACTIVE: Trong hạn và policy hợp lệ
    ACTIVE --> EXPIRED: now đạt exp
    ACTIVE --> REVOKED: Revoke/token denial
    ACTIVE --> INVALID_FOR_RESOURCE: Sai audience/scope/policy
    ISSUED --> NOT_YET_VALID: now trước nbf
    NOT_YET_VALID --> ACTIVE: Đến nbf và vẫn hợp lệ
    INVALID_FOR_RESOURCE --> ACTIVE: Chỉ với request khác hợp lệ và còn hạn
    EXPIRED --> [*]
    REVOKED --> [*]
~~~

**Sơ đồ access token mô tả các điều kiện kiểm tra**, không nhất thiết là tất cả trạng thái được lưu trong database. Token tự chứa có thể không có record phía server, nhưng verifier vẫn phải từ chối token hết hạn.

Refresh token family có thể có trạng thái riêng:

~~~mermaid
stateDiagram-v2
    [*] --> GRANT_ACTIVE
    GRANT_ACTIVE --> R1_ACTIVE: Refresh token R1 hợp lệ
    R1_ACTIVE --> R1_INVALIDATED: Rotate R1 sang R2
    R1_INVALIDATED --> R2_ACTIVE: R2 trở thành token hiện hành
    R2_ACTIVE --> FAMILY_REVOKED: Reuse/compromise/policy revoke
    R2_ACTIVE --> GRANT_EXPIRED: Idle/absolute lifetime
    FAMILY_REVOKED --> [*]
    GRANT_EXPIRED --> [*]
~~~

**Một refresh token bị invalidated không nhất thiết làm access token đã cấp biến mất ngay**. Đối với quyền nhạy cảm, cần thêm enforcement/revocation ở resource server.

## 41. Mã giả: resource server kiểm tra token expiration

Đoạn này là **mã giả**, không thay thư viện JWT/OAuth đã được kiểm chứng:

~~~text
authorizeApiRequest(request, trustedNow):
    token = extractExpectedAccessToken(request)
    if token is missing:
        return HTTP_401_AUTHENTICATION_REQUIRED

    profile = selectTrustedTokenProfileForApi()
    result = validateTokenSignatureOrIntrospect(token, profile)

    if result.unverified or result.typeNotAllowed:
        return HTTP_401_INVALID_TOKEN

    if result.issuer not in profile.allowedIssuers:
        return HTTP_401_INVALID_TOKEN
    if result.audience does not contain profile.requiredAudience:
        return HTTP_401_INVALID_TOKEN

    if result.exp is missing when profile.requiresExp:
        return HTTP_401_INVALID_TOKEN
    if trustedNow >= result.exp + profile.boundedClockSkewLeeway:
        return HTTP_401_INVALID_TOKEN
    if result.nbf exists
       and trustedNow + profile.boundedClockSkewLeeway < result.nbf:
        return HTTP_401_INVALID_TOKEN

    if not tokenSenderConstraintProofValidWhenRequired(result, request):
        return HTTP_401_INVALID_TOKEN

    if tokenRevokedOrSubjectSecurityEpochInvalid(result):
        return HTTP_401_INVALID_TOKEN

    principal = resolveVerifiedSubjectAndTenant(result)
    policy = loadCurrentPolicyForActionAndResource(request)
    if not policy.permit(principal, result.scope, request.action, request.resource):
        return HTTP_403_FORBIDDEN

    recordSanitizedDecisionAndEnforcement()
    return PROCESS_AUTHORIZED_ACTION
~~~

**Điểm cần lưu ý:** điều kiện exp minh họa xử lý leeway theo policy. Nếu policy không cho leeway, verifier phải từ chối ngay **now >= exp**. Một số thư viện sẽ tự kiểm tra exp/nbf sau khi đã validate signature; không cộng leeway hai lần trong code ứng dụng.

**Không tự triển khai thuật toán mật mã** bằng mã giả này. Dùng thư viện đã được đánh giá, cấu hình issuer/audience/key/algorithm/token type rõ và kiểm thử phản hồi trước/sau ranh giới thời gian.

## 42. Mã giả: refresh-token rotation an toàn

~~~text
refreshAccessToken(presentedRefreshToken, authenticatedClient, trustedNow):
    tokenRef = lookupHashedTokenReference(presentedRefreshToken)
    family = lockCurrentGrantFamily(tokenRef.familyId)

    if family.revoked or trustedNow >= family.absoluteExpiresAt:
        return OAUTH_INVALID_GRANT

    if family.idleExpiredAt(trustedNow):
        return OAUTH_INVALID_GRANT

    if not authenticatedClient.matchesBoundClient(family):
        audit("CLIENT_BINDING_MISMATCH")
        return OAUTH_INVALID_GRANT_OR_CLIENT_AUTH_ERROR

    if tokenRef != family.currentRefreshTokenRef:
        audit("REFRESH_TOKEN_REUSE", family.id)
        applyApprovedReplayResponse(family)
        return OAUTH_INVALID_GRANT

    principal = loadCurrentSubjectOrWorkloadEligibility(family)
    if principal.inactiveOrRevoked or not family.grantStillValid:
        revokeFamilyAtomically(family)
        return OAUTH_INVALID_GRANT

    permissions = calculateCurrentApprovedScopeAndAudience(family, principal)
    if permissions.empty:
        return OAUTH_INVALID_GRANT_OR_POLICY_ERROR

    newRefreshRef = createCryptographicallyRandomRotatedToken()
    atomicallyReplaceCurrentRefreshToken(family, newRefreshRef)
    newAccessToken = issueScopedAccessToken(
        permissions,
        maxExpiry = min(family.absoluteExpiresAt, policyTtlLimit)
    )
    auditWithoutRawTokens("REFRESH_ROTATED", family.id)
    return newAccessToken + newRefreshTokenAccordingToContract
~~~

Mã giả giả định có **khóa/transaction/compare-and-set** bảo đảm chỉ một token hiện hành trong family tại một thời điểm. Mọi retry do mất response phải theo **server/client contract**, không tự cho reuse không giới hạn. Với public client, lựa chọn rotation hay sender constraint và phản ứng compromise cần phù hợp chính sách bảo mật.

**Không lưu raw refresh token trong log**. Nếu store phải giữ verifier cho token, dùng cơ chế phù hợp (ví dụ token reference được bảo vệ hoặc keyed hash theo thiết kế), tránh biến database thành kho bearer token dễ tái sử dụng.

## 43. Mã giả: cấp token không vượt hạn quyền

~~~text
issueToken(principalRef, clientRef, requestedAudience, requestedScope, now):
    principal = loadVerifiedCurrentPrincipal(principalRef)
    client = loadApprovedClient(clientRef)
    relation = principal.currentEmploymentOrWorkloadRelation()

    if not relation.activeAt(now):
        return DENY
    if not client.allowedFor(requestedAudience):
        return DENY

    grant = loadCurrentGrant(client, principal)
    approvedScope = intersect(
        requestedScope,
        grant.currentAllowedScope,
        policy.currentResourceScopes(principal, requestedAudience)
    )
    if approvedScope.empty:
        return DENY

    cutoff = min(
        policy.maxAccessTokenLifetimeFrom(now),
        grant.approvedEndAt,
        relation.endAtIfPresent,
        activeJitLeaseEndAtIfApplicable
    )

    if cutoff <= now:
        return DENY

    return signAccessToken(
        issuer = trustedIssuer,
        subject = principal.stableId,
        audience = requestedAudience,
        scope = approvedScope,
        iat = now,
        exp = cutoff
    )
~~~

Đây là **mô hình thiết kế có cutoff chặt**. Một số hệ thống không thể đưa mọi deadline vào exp vì deadline thay đổi sau issuance; lúc đó phải có **online policy checks/revocation** đủ nhanh tại API. Việc đặt exp ngắn hơn endAt chỉ làm giảm rủi ro, không thay việc áp dụng hard deny khi quyền bị rút sớm.

## 44. Ví dụ cấu hình chính sách token

~~~yaml
tokenPolicy:
  name: reports-api-token-policy
  version: v7
  issuer: https://idp.example.invalid
  audiences:
    - reports-api
  accessToken:
    requiresExpiration: true
    maxTtlSeconds: 900
    clockSkewLeewaySeconds: 30
    requiredClaims:
      - iss
      - aud
      - exp
      - sub
    senderConstraintRequiredForPrivilegedActions: true
  refreshToken:
    enabledForEligibleClients: true
    rotation: true
    inactivityTtlDays: 7
    absoluteMaxDays: 30
    reuseResponse: REVOKE_FAMILY_AND_REAUTHENTICATE
  enforcement:
    checkCurrentEmployment: true
    checkCurrentResourceAuthorization: true
    checkSecurityEpochForHighRisk: true
    introspectionCacheMaxSeconds: 30
  logging:
    includeRawTokenValues: false
    auditIssuanceRotationRevocation: true
~~~

**Đây là file policy giả định**, không phải cú pháp chính thức của Spring Security, Keycloak, Entra ID hoặc sản phẩm IdP nào. Các TTL chỉ dùng để minh họa các **mốc độc lập**, không phải khuyến nghị chung cho mọi ứng dụng.

**Bản thân file cấu hình không chứng minh policy đã được thực thi**. Cần test ở Authorization Server, Resource Server, gateway và những đường access không đi qua gateway.

## 45. Audit: cần ghi gì khi token hết hạn, refresh hoặc revoke?

| Event | Dữ liệu nên ghi | Không ghi |
| --- | --- | --- |
| **TOKEN_ISSUED** | tokenRef/jti khi có, client, issuer, aud, scope summary, iat/exp | Raw access token |
| **TOKEN_VALIDATION_DENIED** | reasonCode expired/issuer/audience/revoked, endpoint và correlation | Raw token/headers |
| **REFRESH_SUCCEEDED** | grantRef, client, rotationVersion, timestamp | Raw refresh token |
| **REFRESH_REUSE_DETECTED** | familyRef, eventId, client/context và response | Token bị nghi đánh cắp |
| **GRANT_REVOKED** | grantId, actor, lý do, affected scopes | Secret và thông tin không cần thiết |
| **SUBJECT_DISABLED** | identityRelation, effectiveAt, sourceVersion | Hồ sơ HR đầy đủ |
| **EPOCH_CHANGED** | subject/tenant, newVersion, reason, propagatedAt | Credential bí mật |
| **ENTITLEMENT_CHANGED** | role/ACL delta, owner và effectiveAt | Token đã phát hành |
| **TARGET_DENY_VERIFIED** | endpoint/action/resource test scope, verifiedAt | Dữ liệu cá nhân không cần thiết |

Ví dụ JSON:

~~~json
{
  "eventId": "token-audit-2026-0142",
  "eventType": "ACCESS_TOKEN_REJECTED",
  "correlationId": "req-reports-842",
  "issuer": "https://idp.example.invalid",
  "tokenReference": "token-jti-or-protected-ref-482",
  "principalRef": "iam-user-482",
  "employmentRelationRef": "emp-org-a-482",
  "clientRef": "reports-web-client",
  "targetResource": "reports-api/org-a/project-atlas",
  "reasonCode": "TOKEN_EXPIRED",
  "tokenExpiresAt": "2026-11-23T10:15:00+07:00",
  "verifiedAt": "2026-11-23T10:15:02+07:00",
  "policyVersion": "reports-token-v7",
  "authorizationResult": "DENY"
}
~~~

**Event này chỉ chứng minh một token cụ thể bị từ chối tại một endpoint và thời điểm**. Nó không chứng minh mọi session/credential của identity đã bị khóa. Dùng correlationId, principal/tenant, target version và test coverage để giải thích phạm vi bằng chứng.

## 46. Monitoring và KPI về Token expiration

| Chỉ số/tín hiệu | Ý nghĩa | Hành động |
| --- | --- | --- |
| **Expired-token rejection rate** | Tỷ lệ request sử dụng token đã hết hạn | Phân biệt client lỗi refresh với hành vi đáng ngờ |
| **Refresh success/failure rate** | Chất lượng token lifecycle | Xem invalid_grant, outage, client binding |
| **Refresh reuse detection** | Dấu hiệu replay hoặc race | Điều tra family, concurrency và credential theft |
| **Time to revocation enforcement** | Từ quyết định revoke đến resource server Deny | Đo theo risk tier/SLA |
| **Leaver old-token acceptance** | Token cũ còn ALLOW sau endAt | Finding bảo mật cần ưu tiên |
| **Mover stale-role window** | Thời gian role cũ tiếp tục tác dụng | Kiểm tra claim/cache/target state |
| **Token issuing past grant cutoff** | Authorization server cấp token vượt hạn quyền | Sửa policy/issuance guard |
| **Excessive leeway** | Verifier tiếp tục chấp nhận token quá exp không hợp lý | Điều chỉnh clock sync và validation |
| **High-risk token lifetime** | Token đặc quyền có TTL vượt policy | Review client/audience/resource |
| **Introspection cache staleness** | API nhận active sau revoke | Giảm cache hoặc invalidate |
| **Client-credential expiry incidents** | Service ngừng do secret/certificate đến hạn | Rotation automation và alert |
| **Unknown token inventory/coverage** | Target không hỗ trợ readback/introspection | Risk owner và remediation plan |

**Không đặt mục tiêu bằng 0 cho mọi lỗi invalid_token**: token hết hạn được từ chối chính là hành vi mong đợi. Điều cần đánh giá là **token expired có được Deny đúng**, client có khả năng recovery phù hợp và quyền bị rút có bị sử dụng trái chính sách hay không.

## 47. Những anti-pattern thường gặp

| Anti-pattern | Tác hại | Cách sửa |
| --- | --- | --- |
| Chỉ decode JWT và đọc exp | Chấp nhận token giả hoặc sai issuer/audience | Verify signature, profile và claims |
| So exp giây với timestamp mili giây | Token hết hạn sai | Thống nhất Unix epoch seconds |
| Cho phép leeway quá lớn | Gia tăng cửa sổ token bị dùng | Clock sync và bounded leeway |
| Coi refresh token hết hạn như access token hết hạn | Xử lý sai lỗi client/grant | Phân biệt hai vòng đời |
| Gửi refresh token tới API | Rò credential | Chỉ gửi tới token endpoint |
| Dùng ID token để gọi API | Token confusion | Validate đúng access-token profile |
| JWT vẫn ALLOW sau Leaver | Residual access | Revocation/epoch/online policy checks |
| Refresh không revalidate role | Mover xin lại scope cũ | Tính lại allowed scope từ nguồn hiện hành |
| Client credentials dùng static key vô thời hạn | Rủi ro lộ credential | Managed/federated identity, rotation |
| Access token được ghi nguyên trong log | Lộ bearer credential | Token reference và redaction |
| Cache Permit vượt exp | Xài token hết hạn | Kiểm tra exp ở mọi request |
| Không kiểm tra aud | Token dùng sai API | Pin resource audience |
| Reuse refresh token bị bỏ qua | Token replay kéo dài | Rotation, family state và response |
| Leaver chỉ logout IdP | SaaS/local API access còn | Target reconciliation và negative tests |
| Key rotation được coi là token revocation | Hiểu sai tác dụng của signing key | Kế hoạch overlap/revoke thực tế |
| Client refresh vô hạn khi 403 | Bỏ qua deny nghiệp vụ | Phân biệt invalid_token và insufficient_scope |
| Hard-coded TTL cho mọi tài nguyên | Quá dài với admin, quá ngắn với offline | Risk-based policy và UX/load testing |

**Sự tồn tại của exp không bảo đảm implementation an toàn** nếu parser, verifier, cache, policy hoặc target không thực thi đúng.

## 48. Bộ kiểm thử Token expiration

| Test | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| T01 | Access token còn hạn, đúng signature/issuer/aud | Tiếp tục kiểm tra authorization, không auto ALLOW |
| T02 | Request đúng mốc exp khi không có leeway | Token bị từ chối |
| T03 | Request sau exp quá leeway hợp lệ | 401 invalid_token |
| T04 | Token dùng epoch milliseconds thay seconds | Token bị đánh giá không hợp lệ theo profile |
| T05 | JWT thiếu exp khi access-token profile yêu cầu | Reject |
| T06 | JWT có chữ ký sai nhưng exp còn xa | Reject |
| T07 | JWT từ issuer khác | Reject |
| T08 | JWT đúng issuer nhưng aud của API khác | Reject |
| T09 | ID Token được gửi làm access token | Reject token confusion |
| T10 | nbf nằm ở tương lai | Reject trước mốc hợp lệ, xét bounded skew |
| T11 | Token iat ở tương lai bất thường | Xử lý theo issuer/profile và max-age policy |
| T12 | Refresh hợp lệ và còn grant | Cấp token mới đúng policy |
| T13 | Refresh grant bị revoke | invalid_grant/không cấp token |
| T14 | Refresh R1 đã rotate rồi reuse | Detection và response theo family policy |
| T15 | Hai tab refresh đồng thời | Atomic behavior, không để family bất nhất |
| T16 | Access token hết hạn nhưng SSO session còn | Không dùng token cũ; có thể xin token mới hợp lệ |
| T17 | User Leaver trước exp | Old token bị chặn theo SLA, không cần đợi exp |
| T18 | User Mover khỏi Atlas nhưng token cũ có role Atlas | API Atlas Deny theo cutoff policy |
| T19 | Token mới sau Mover | Không còn quyền Atlas trái policy |
| T20 | Guest contract hết hạn | Không phát token mới vượt căn cứ |
| T21 | Org-a Leaver, org-b relation còn hợp lệ | Không xóa nhầm quyền org-b |
| T22 | Client secret hết hạn, access token còn hạn | Phân biệt token/client authentication behavior |
| T23 | Service principal decommission | Ngăn issuance mới, revoke trust/grant |
| T24 | JWT signing key rotate | Xử lý JWKS overlap theo policy, không giả định revoked |
| T25 | Introspection cache stale sau revoke | Không vượt revocation SLA |
| T26 | DPoP proof mới nhưng access token đã exp | Reject |
| T27 | PAT local vẫn active sau logout IdP | Finding residual, không verified |
| T28 | SCIM User disabled nhưng API JWT còn ALLOW | Finding cần xử lý |
| T29 | PAM lease hết hạn giữa lúc refresh | Không cấp privileged token vượt JIT cutoff |
| T30 | API 403 vì thiếu scope | Không refresh vô hạn hoặc gọi lại trái policy |
| T31 | Device offline không đồng bộ giờ | Áp dụng policy time assurance; không Permit mù |
| T32 | Một key bị nghi compromise | Containment và token/credential revocation theo playbook |
| T33 | Thử làm giả exp trong JWT payload | Signature verification phát hiện |
| T34 | Cached Permit sau exp | Token phải bị Deny |
| T35 | Refresh request timeout sau rotation | Client/server xử lý retry nhất quán, không tạo family vô hạn |
| T36 | Target không cung cấp trạng thái token | Ghi UNKNOWN, không tuyên bố Deny toàn hệ thống |

**Boundary tests nên dùng fake clock/time injection** thay vì phải chờ đúng thời điểm thực. Integration tests cần kiểm tra Authorization Server, client, gateway, resource server và những đường không đi qua gateway.

Không dùng token production thật trong bộ test hoặc log; phải sử dụng **test tenant, test credentials và tài nguyên được ủy quyền**.

## 49. Tình huống thực hành: Mover và access token chưa hết hạn

**Bối cảnh:** Công ty có hệ thống báo cáo của hai dự án **Atlas** và **Nova**, truy cập qua OIDC login và OAuth API. Nhân viên Lan được cấp quyền **Atlas ReportEditor**. Sau khi chuyển dự án, Lan chỉ được giữ **Nova ReportViewer**.

### Bước 1 — Token trước Mover

~~~text
09:50  Lan nhận access token A cho reports-api
        exp=10:20
        scope=reports:read reports:edit
        projectAssignment=Atlas
~~~

API hợp lệ có thể cho Lan chỉnh sửa báo cáo Atlas trước thời điểm chuyển vai trò, theo scope và policy.

### Bước 2 — Sự kiện Mover có hiệu lực

~~~text
10:00  HRIS/project registry: Lan chuyển Atlas -> Nova
10:01  IGA expected access: Atlas DENY, Nova READ
10:02  SCIM/IdP group update: gỡ AtlasEditor, thêm NovaViewer nếu hợp lệ
10:03  Security epoch/entitlement policy đã cập nhật tại API
~~~

**Access token A còn exp=10:20**, nhưng không còn là căn cứ đủ để giữ quyền Atlas sau khi policy đã yêu cầu rút.

### Bước 3 — Kiểm thử API sau Mover

| Request | Mốc | Kết quả mong đợi |
| --- | --- | --- |
| A gọi EDIT Atlas | 10:04 | **DENY** theo revoke/online policy |
| A gọi READ Atlas | 10:04 | **DENY** nếu quyền Atlas đã hết |
| Client xin token mới với scope Editor Atlas | 10:05 | Không cấp scope Atlas đã bị rút |
| Token mới B gọi READ Nova | 10:06 | **ALLOW** nếu được duyệt và đủ điều kiện |
| Token B gọi EDIT Nova | 10:06 | **DENY** vì chỉ Viewer |
| Token A gọi reports-api sau exp | Sau 10:20 | **401/invalid_token** |

**Trạng thái 403 hay 401** khi token A bị cắt sớm phụ thuộc việc resource server coi nó bị revoke/invalid hay token còn hợp lệ nhưng quyền bị Deny; điều quan trọng là **không ALLOW** và audit reason nhất quán.

### Bước 4 — Nếu refresh token cũ vẫn xin được AtlasEditor?

Đây là lỗi ở token issuance hoặc grant/policy refresh. Cần chặn scope cũ, vô hiệu grant/token family khi thích hợp, kiểm tra nguồn quyền và xem có role tại SaaS/ACL còn sót không.

### Bước 5 — Nếu API chỉ kiểm tra chữ ký và exp?

Token A có thể còn được chấp nhận cho đến 10:20, gây **residual access window**. Nếu không phù hợp yêu cầu nghiệp vụ, phải bổ sung **security epoch/introspection/online entitlement checks hoặc thay kiến trúc**. Giảm TTL xuống vài phút làm cửa sổ ngắn hơn nhưng vẫn không tương đương revoke tức thời.

### Bước 6 — Hậu kiểm

Audit liên kết **HR eventId, sourceVersion, entitlement changes, token issuance, token validation decisions, session/grant state và target verification**. Không đóng Mover khi chỉ thấy group removed; phải kiểm tra quyền thực tế ở tài nguyên mục tiêu.

## 50. Câu hỏi tự kiểm tra

**Câu 1: Token A đã hết hạn, nhưng user vẫn đăng nhập SSO. Có thể tiếp tục gửi A tới API không?**

**Trả lời:** Không. Client phải dùng token mới theo quy trình hợp lệ; phiên SSO còn hoạt động không gia hạn exp của token A.

**Câu 2: Người dùng nghỉ việc lúc 10:00, access token hết hạn lúc 10:30. Có được chờ 10:30 để khóa quyền không?**

**Trả lời:** Không nếu chính sách yêu cầu cắt quyền sớm hơn. Phải revoke/deny theo SLA ở resource server và xử lý các grant/session khác.

**Câu 3: Claim iat có thể dùng thay exp không?**

**Trả lời:** Không. iat là thời điểm phát hành; expiration phải theo exp hoặc cơ chế lifetime được profile/verifier chấp nhận.

**Câu 4: JWT có exp hợp lệ nhưng audience của API khác thì sao?**

**Trả lời:** Phải Reject; exp chỉ là một điều kiện của token validation.

**Câu 5: Refresh token còn hạn có chắc chắn cấp được access token có role Admin cũ không?**

**Trả lời:** Không. Authorization server phải xét grant, client, current eligibility, role/scope và policy.

**Câu 6: Revoke refresh token có làm JWT access token đã cấp bị từ chối ngay không?**

**Trả lời:** Không tự động. API cần cơ chế nhận biết revocation hoặc chờ exp trong giới hạn chính sách.

**Câu 7: Vì sao client credentials flow thường không cần refresh token?**

**Trả lời:** Workload có thể chứng thực client/trust lại để nhận access token mới, miễn principal/credential và policy còn hợp lệ.

**Câu 8: Có nên tăng clock skew leeway lớn để tránh user gặp lỗi 401?**

**Trả lời:** Không mặc định. Cần sửa đồng bộ đồng hồ, refresh behavior và chỉ dùng leeway nhỏ theo risk policy.

**Câu 9: DPoP proof mới có làm một access token đã exp tiếp tục hợp lệ không?**

**Trả lời:** Không. Proof và token có hai điều kiện thời gian riêng; token hết hạn vẫn bị từ chối.

**Câu 10: SCIM báo user bị deactivate đã đủ hoàn thành Leaver chưa?**

**Trả lời:** Chưa. Phải kiểm tra token/session/PAT/local ACL và kết quả Deny ở target phù hợp phạm vi.

## 51. Checklist thiết kế Token expiration trong Identity Lifecycle

| Câu hỏi | Bằng chứng hoặc kiểm soát cần có |
| --- | --- |
| Phân loại đúng access/ID/refresh/session/credential? | Token contract và actor/resource owner |
| Có exp bắt buộc theo token profile? | Issuer config và verifier tests |
| NumericDate được so cùng đơn vị UTC? | Seconds/Instant conversion và boundary tests |
| Có kiểm tra nbf, iat, age/freshness khi cần? | Profile validation và clock policy |
| Có giới hạn leeway hợp lý? | Clock sync và skew monitoring |
| JWT signature/alg/issuer/aud/type đúng? | Pinned verifier trust profile |
| Opaque token được introspect đúng? | Introspection response, active và cache TTL |
| Có TTL theo client/resource/risk? | Risk review và policy version |
| Session idle và absolute timeout có tách? | IdP/app session config |
| Refresh token có inactivity/absolute lifetime? | Grant/family expiry model |
| Refresh rotation/reuse được xử lý? | Atomic state, family revocation, retry strategy |
| Client có an toàn khi refresh đồng thời? | Single-flight và concurrency tests |
| Token được lưu an toàn? | BFF/secure storage, CSP/XSS/CSRF controls tùy app |
| Có bảo vệ token khỏi log leak? | Redaction/allowlist và security tests |
| Bearer token rủi ro cao có sender constraint? | mTLS/DPoP theo hỗ trợ thực tế |
| OAuth access token không bị nhầm ID token? | Token type/audience/profile checks |
| Có revocation strategy trước exp? | Introspection/denylist/epoch/online authz |
| Cache không vượt expiry và revoke SLA? | Cache TTL/invalidation và tests |
| RBAC/ABAC/PBAC được thực thi ở API? | Object/action/tenant authorization |
| Joiner có chặn quyền trước startAt? | Employment validity và issuance checks |
| Mover có rút role cũ trong token mới? | Updated scope và target rights |
| Mover có chặn token cũ theo cutoff? | Revoke/epoch/PEP tests |
| Leaver có chặn refresh và token còn hạn? | Session/grant/target deprovision evidence |
| Contractor có endAt và sponsor? | Contract grant cutoff và revalidation |
| Workload service có owner và trust rõ? | Client credential/federation/role review |
| Emergency/PAM token có gắn lease? | Hard cutoff, audit và negative tests |
| Client secret/certificate có lifecycle riêng? | PKI/vault rotation/revocation |
| SCIM provisioning có được đối soát? | User/group/role target readback |
| Có phân biệt HTTP 401 và 403? | Error contract và client handling |
| Có audit token issuance/refresh/revoke? | Metadata không chứa token thô |
| Có monitoring TTL, refresh reuse và stale rights? | KPI/SIEM và owner response |
| Có thử boundary đúng tại exp? | Fake clock tests, leeway policy |
| Có kết quả effective Deny sau thu hồi? | Negative API tests và scope evidence |
| Có UNKNOWN/UNVERIFIED khi thiếu dữ liệu? | Không kết luận hoàn tất khi chưa có bằng chứng |

## 52. Tổng kết

**Token expiration** là cơ chế giới hạn thời điểm token còn được chấp nhận. Với JWT, **exp** là mốc expiration theo **NumericDate**; **nbf** quy định không dùng trước thời điểm xác định, còn **iat** chỉ thời điểm phát hành. Việc kiểm tra đúng còn phải bao gồm **chữ ký, thuật toán, issuer, audience, token type, policy, scope và trạng thái quyền hiện hành**. Token có thể hết hạn trong khi session/refresh grant vẫn hoạt động; token chưa hết hạn vẫn có thể bị từ chối vì revoke, mất quyền hoặc sai resource.

Trong vòng đời **Joiner–Mover–Leaver**, **HRIS/nguồn bảo trợ** quyết định căn cứ và mốc hiệu lực; **IAM/IGA** quản lý expected access, approval và deprovisioning; **IdP/SSO/OIDC** xác thực và quản lý các phiên/ID tokens; **OAuth Authorization Server** cấp access/refresh token; **SCIM** đồng bộ account/group; còn **RBAC/ABAC/PBAC và resource server/PEP** thực thi quyền đúng tài nguyên. **Non-human identities** có vòng đời token, credential và trust riêng, không thể chỉ áp logic logout của người dùng.

Thiết kế đáng tin cậy cần **TTL theo mức rủi ro, refresh rotation và concurrency an toàn, credential storage tốt, revocation trước exp khi cần, cache/policy đủ mới, kiểm thử đúng ranh giới thời gian, audit không lộ token và đối soát quyền hiệu lực tại target**. Chỉ như vậy expiration mới là một **lớp phòng vệ có ích** thay vì cảm giác an toàn giả tạo trước **quyền truy cập tồn dư**.
