# Checklist authentication trong IAM lifecycle

> **Chương:** Tổng kết IAM lifecycle  
> **Chủ đề:** Checklist kiểm tra và vận hành **authentication (xác thực)** cho danh tính con người và danh tính máy trong mô hình **Joiner–Mover–Leaver (JML)**. Nội dung nối xác minh chủ thể, IdP, SSO, MFA, vòng đời credential, phiên/token, RBAC/ABAC, SCIM, kiểm toán và giảm quyền truy cập tồn dư.

## 1. Dùng checklist để giải quyết điều gì?

Authentication trả lời câu hỏi **“Chủ thể đang cố truy cập có thật sự là danh tính mà hệ thống tin tưởng hay không?”**. Nó là một chặng quan trọng trong IAM lifecycle nhưng không bao trùm tất cả chức năng quản trị quyền.

| Khái niệm | Câu hỏi | Ví dụ kiểm soát |
| --- | --- | --- |
| **Identity proofing / xác minh danh tính** | Hồ sơ này có gắn đúng với một cá nhân/chủ thể thật không? | HR hoặc sponsor xác minh danh tính và hợp đồng |
| **Identification / định danh** | Chủ thể khai mình là tài khoản nào? | ID bất biến của nhân viên hoặc workload |
| **Authentication / xác thực** | Chủ thể chứng minh quyền kiểm soát credential ra sao? | Passkey, security key, MFA, certificate |
| **Authorization / phân quyền** | Chủ thể đã xác thực được phép làm gì? | Role, scope, ACL, RBAC/ABAC |
| **Provisioning / cấp phát** | Account và quyền tồn tại ở hệ thống nào? | SCIM, API, quản trị ứng dụng |
| **Session management / quản lý phiên** | Sau đăng nhập, phiên hoạt động và kết thúc thế nào? | Cookie session, refresh token, timeout, logout |
| **Audit / kiểm toán** | Ai làm gì, khi nào, quyết định và kết quả là gì? | Log sự kiện xác thực, thu hồi phiên và cảnh báo |

Một người dùng có thể **xác thực thành công** nhưng không có quyền xem dữ liệu; ngược lại, một tài khoản có role nhưng không thể đăng nhập nếu credential đã thu hồi. Do đó checklist phải bao quát cả **khả năng xác thực** và cách xác thực nối sang **quyền hiệu lực**, đồng thời tách biệt kết quả của hai khâu này.

### Kết quả học tập

Người học hoàn thành bài này có thể:

1. Kiểm tra độ tin cậy của danh tính trước khi khởi tạo phương thức xác thực.
2. Rà soát cấu hình IdP/SSO/MFA và credential trước khi mở quyền cho Joiner.
3. Nhận ra thời điểm Mover cần đánh giá lại chính sách xác thực, thiết bị, quyền đặc biệt và phiên đang tồn tại.
4. Kiểm tra Leaver đã bị chặn trên IdP, ứng dụng, phiên SSO, token độc lập và account local hay chưa.
5. Áp dụng checklist tương đương cho service account, CI/CD và workload identity.
6. Ghi bằng chứng và kiểm thử các trường hợp thất bại để tránh tuyên bố hoàn tất quá sớm.

## 2. Sơ đồ kiểm tra: nguồn sự thật → đăng nhập → tài nguyên

~~~mermaid
flowchart TD
    HR["HRIS / quản lý nhà thầu / nguồn workload"] --> GOV["Identity lifecycle: Joiner–Mover–Leaver"]
    GOV --> IDP["IdP: identity, credential, MFA, nhóm, trạng thái"]
    GOV --> PROV["SCIM / API / quản trị app"]
    IDP --> SSO["SSO: SAML hoặc OIDC"]
    SSO --> APP["Ứng dụng / Service Provider"]
    PROV --> APP
    APP --> AUTHZ["Authorization: RBAC / ABAC / ACL / scope"]
    IDP --> AUDIT["Log và đối soát"]
    APP --> AUDIT
    PROV --> AUDIT
    AUDIT --> GOV
~~~

Đọc sơ đồ theo **hai đường độc lập**:

- **Đường xác thực:** IdP kiểm tra credential, MFA và điều kiện đăng nhập, sau đó truyền kết quả xác thực theo giao thức tin cậy tới ứng dụng; ứng dụng có thể tự quản lý một phiên riêng.
- **Đường cấp phát/quyền:** hệ thống vòng đời và connector tạo hoặc vô hiệu account, nhóm, role; ứng dụng ra quyết định cho phép hành động cụ thể. Một số ứng dụng giữ account local hoặc API key ngoài SSO.

Điều này giải thích tại sao **khóa IdP khi Leaver chưa đủ bảo đảm chặn toàn bộ đường truy cập**, và vì sao **SCIM cập nhật account không mặc nhiên hủy mọi token/phiên đã cấp**.

## 3. Checklist tiền đề: danh mục hệ thống và ranh giới tin cậy

Trước khi kiểm tra một ứng dụng, hãy lập hồ sơ xác thực tối thiểu:

| Cần xác định | Câu hỏi cần trả lời | Ví dụ bằng chứng |
| --- | --- | --- |
| Chủ sở hữu | Ai quyết định cấu hình và ai xử lý khi người dùng bị khóa? | Owner ứng dụng, on-call, tài liệu vận hành |
| Nguồn danh tính | Tên, trạng thái và ngày hiệu lực đến từ đâu? | HRIS/sponsor, ID ổn định và sự kiện nguồn |
| Cách đăng nhập | SSO SAML/OIDC, local password, LDAP, VPN hay API token? | Sơ đồ luồng, cấu hình app và IdP |
| Phương thức MFA | Factor nào được chấp nhận cho nhóm người dùng/rủi ro nào? | Policy IdP, cấu hình đăng ký factor |
| Provisioning | User được tạo/cập nhật/vô hiệu bằng SCIM, API hay thủ công? | Kết nối, mapping ID, log thực thi |
| Session | Cookie, refresh token, app session và timeout do ai quản lý? | Cấu hình timeout, revoke/logout, kiểm thử |
| Tài khoản đặc biệt | Có local admin, break-glass, service account, bot? | Inventory và owner |
| Quyền | Có role/ACL trực tiếp hoặc token có scope độc lập không? | Entitlement inventory, policy |
| Khôi phục | Quên/mất factor thì ai xác minh và cho đăng ký lại? | Recovery runbook và nhật ký |
| Giám sát | Log đăng nhập, lỗi MFA, token và phiên gửi về đâu? | Bản ghi sự kiện, cảnh báo và retention |

### 3.1. Checklist kiểm kê trước khi onboarding

- [ ] Mỗi ứng dụng có **owner** và phân loại mức nhạy cảm dữ liệu.
- [ ] Liệt kê đầy đủ **đường đăng nhập** (kể cả tài khoản local và API) và đường cấp quyền riêng.
- [ ] Có bảng ánh xạ **subjectId bất biến → IdP user ID → application user ID**.
- [ ] Biết điểm thực thi chính sách xác thực (IdP, ứng dụng, gateway, VPN, thiết bị).
- [ ] Kiểm chứng ứng dụng nhận và xử lý sự kiện **disable, logout, token revoke** theo cách nào.
- [ ] Có quy trình thay thế khi SSO/SCIM không sẵn sàng và người phụ trách được phân công.
- [ ] Biết bằng chứng nào chứng minh một đường đăng nhập đã bị chặn khi Leaver.
- [ ] Các tài khoản đặc biệt và workload identity có owner, mục đích, kỳ rà soát.

Nếu không biết một ứng dụng còn đăng nhập local hay không, chưa thể xác nhận luồng Leaver đã bao phủ mọi đường truy cập. Một checklist có ô “không áp dụng” cần có **lý do và người xác nhận**, tránh coi thông tin chưa biết là đã đạt.

## 4. Checklist Joiner: xác minh rồi mới cho phép đăng nhập

**Mục tiêu:** Một người mới được tạo đúng danh tính, đăng ký phương thức xác thực một cách an toàn và có thể truy cập tài nguyên hợp lệ từ thời điểm được cho phép.

### 4.1. Xác minh danh tính và khởi tạo account

- [ ] Sự kiện Joiner đến từ **HR hoặc sponsor có thẩm quyền**, ghi rõ ID ổn định, ngày bắt đầu và người quản lý.
- [ ] Có bước identity proofing thích hợp mức rủi ro; thông tin đối chiếu không chỉ là địa chỉ email do người dùng tự khai.
- [ ] Kiểm tra trùng lặp khi nhân viên đổi tên, quay lại tổ chức hoặc có tên giống người khác.
- [ ] Account IdP gắn đúng subjectId và các tài khoản đích; không dùng chung account cá nhân giữa nhiều người.
- [ ] Có quy tắc **pre-hire**: account có thể được chuẩn bị trước nhưng đăng nhập và quyền dữ liệu chỉ mở khi phù hợp ngày hiệu lực.
- [ ] Chỉ cấp các role hợp lệ từ RBAC/ABAC; quyền đặc biệt có phê duyệt riêng và thời hạn.
- [ ] Credential khởi tạo và các kênh kích hoạt được bàn giao qua phương án an toàn; không gửi mật khẩu dùng chung trong chat/email.
- [ ] Mọi account tạo thất bại hoặc không có owner đều được đưa vào hàng đợi xử lý ngoại lệ.

**Ví dụ:** HR xác nhận nhân viên mới bắt đầu ngày 01/12. IT chuẩn bị account CRM ngày 28/11, nhưng danh tính vẫn ở trạng thái chưa được phép truy cập dữ liệu thật cho đến ngày hiệu lực. Nếu sự kiện Joiner bị hủy, quy trình phải vô hiệu account đã chuẩn bị và các credential đã đăng ký thử.

### 4.2. Đăng ký credential và MFA

- [ ] Mỗi nhân viên có **credential cá nhân**, không mượn hoặc dùng lại của người khác.
- [ ] Chính sách MFA áp dụng theo rủi ro cho SSO, VPN, quản trị, dữ liệu nhạy cảm và khôi phục tài khoản.
- [ ] Ưu tiên **xác thực chống phishing** như FIDO2/WebAuthn/passkey hoặc khóa bảo mật phù hợp hệ thống, đặc biệt với tài khoản đặc quyền.
- [ ] Khi hỗ trợ factor yếu hơn như OTP hoặc push, nhận diện giới hạn và nguy cơ phishing/push fatigue; áp dụng kiểm soát bổ sung theo chính sách.
- [ ] Thiết lập ít nhất một phương thức **khôi phục hợp lệ** mà không mở lỗ hổng chiếm đoạt tài khoản.
- [ ] Việc thêm, xóa, thay factor phải yêu cầu tái xác thực hoặc xác minh đủ mạnh; được ghi log và gửi cảnh báo khi phù hợp.
- [ ] Kiểm tra các thiết bị dùng để đăng nhập đáp ứng chính sách doanh nghiệp nếu có yêu cầu về posture/trust.
- [ ] Người dùng được hướng dẫn nhận biết trang đăng nhập giả, yêu cầu MFA bất thường và phương thức báo cáo.

**Lưu ý:** Số lượng factor không quyết định toàn bộ độ mạnh. SMS, OTP và push thông thường có đặc điểm rủi ro khác khóa bảo mật chống phishing. Mức yêu cầu cần dựa trên rủi ro và khả năng triển khai, không mặc định mọi cơ chế MFA có giá trị bảo vệ như nhau.

### 4.3. Kiểm tra trước khi bàn giao cho người dùng

| Kiểm tra | Kỳ vọng |
| --- | --- |
| Login với account hợp lệ sau thời điểm hiệu lực | Được xác thực theo policy, yêu cầu MFA đúng ngữ cảnh |
| Login trước thời điểm cho phép | Bị chặn hoặc chỉ truy cập pre-hire hợp lệ |
| Login sai credential | Bị từ chối, có log và kiểm soát chống thử mật khẩu hàng loạt |
| Không có MFA bắt buộc | Không thể bỏ qua chính sách bằng đường đăng nhập khác |
| Truy cập ứng dụng qua SSO | Assertion/token hợp lệ được ứng dụng kiểm tra; account map đúng người |
| Quyền tài nguyên | Chỉ có quyền được duyệt; account không tự nhận admin |
| Bản ghi kiểm toán | Có dấu vết đăng ký factor, lần đăng nhập và kết quả kiểm chứng |

## 5. Checklist chính sách authentication đang vận hành

Checklist dưới đây áp dụng liên tục, không chỉ tại Joiner.

### 5.1. Kiểm soát phương thức đăng nhập

- [ ] Có chính sách rõ cho password, passkey, hardware key, MFA, tài khoản liên kết và đăng nhập local.
- [ ] Khi dùng password, hệ thống áp dụng chính sách mật khẩu phù hợp, kiểm tra mật khẩu bị lộ nếu có năng lực và **không lưu/ghi log plaintext password**.
- [ ] Có chống credential stuffing, password spraying và brute force bằng rate limit, giám sát, chặn theo rủi ro; tránh lockout vô tội vạ gây DoS.
- [ ] MFA bắt buộc cho các luồng rủi ro cao; không có endpoint cũ hoặc API login bỏ qua MFA ngoài ngoại lệ được duyệt.
- [ ] Tái xác thực hoặc **step-up authentication** khi truy cập hành động nhạy cảm, thay credential, thêm factor hoặc thay chính sách an ninh theo rủi ro.
- [ ] Cấu hình session timeout, idle timeout và yêu cầu xác thực lại phù hợp mức nhạy cảm.
- [ ] Nếu kiểm tra device posture, phải xác định ai cấp/thu hồi tín nhiệm thiết bị và cách phản ứng khi thiết bị mất.
- [ ] Có quy trình xử lý đăng nhập bất thường, impossible travel hoặc sign-in từ client lạ; điều chỉnh ngưỡng theo đặc tính thực tế.

### 5.2. Phân ranh xác thực và phân quyền

- [ ] Đăng nhập thành công không tự sinh role quản trị; cấp quyền tuân theo RBAC/ABAC và phê duyệt.
- [ ] Ứng dụng kiểm tra **quyền ở lúc thực thi hành động**, thay vì chỉ dựa vào việc user đã login.
- [ ] Attribute dùng trong ABAC (trạng thái làm việc, bộ phận, dự án) có nguồn có thẩm quyền và độ mới được kiểm soát.
- [ ] Có cách kiểm tra quyền cấp trực tiếp, group lồng nhau và token scope nằm ngoài tập nhóm IdP.
- [ ] Khi thay role, app có cơ chế cập nhật/quản lý claim, cache quyền hoặc phiên đã cấp.
- [ ] Thay đổi thuộc tính của một user không tự tạo một user khác trừ khi có quy trình định danh rõ ràng.

Ví dụ, một người có thể xác thực vào CRM bằng SSO, nhưng ứng dụng phải kiểm tra họ còn quyền **tickets:update** trước khi cập nhật ticket. Nếu quyền đã bị Mover thu hồi mà ứng dụng chỉ kiểm tra role trong phiên cũ, cần xác định cơ chế làm mới claim/cache hoặc vô hiệu phiên theo mức rủi ro.

## 6. Checklist IdP, SSO, SAML/OIDC và tin cậy giữa các hệ thống

**IdP (Identity Provider)** là nguồn xác thực tập trung của nhiều ứng dụng; ứng dụng nhận danh tính thường là **Service Provider (SP)** trong SAML hoặc **Relying Party/Client** trong OIDC. SSO giảm số lần phải nhập credential nhưng cũng tạo phụ thuộc quan trọng vào cấu hình federation và vòng đời phiên.

### 6.1. Các kiểm tra chung của tích hợp SSO

- [ ] Danh sách ứng dụng được phép tin IdP được quản lý; ứng dụng mới cần owner, phê duyệt và tài liệu kết nối.
- [ ] Ứng dụng chỉ chấp nhận kết quả đăng nhập từ IdP/issuer đáng tin đã cấu hình; không tin tùy ý domain hoặc metadata do client gửi.
- [ ] Mapping danh tính dùng ID ổn định, tránh gắn tài khoản bằng email có thể đổi hoặc trùng.
- [ ] Kênh kết nối dùng TLS phù hợp và cấu hình key/certificate có quy trình luân chuyển, hết hạn và thu hồi.
- [ ] Token hoặc assertion được xác minh **chữ ký, issuer, audience, thời gian hiệu lực và các điều kiện áp dụng**.
- [ ] Callback/redirect URI được ràng buộc với client đã đăng ký, tránh redirect tùy ý.
- [ ] Có cơ chế xác nhận trạng thái account ứng dụng và quyền thực tế sau lần SSO đầu tiên.
- [ ] Không để app dựa vào quyền từ assertion/token cũ quá thời hạn chính sách mà không có cách cập nhật.
- [ ] Biết rõ SSO logout, IdP session logout và **local app logout** khác nhau; kiểm thử thực tế.

### 6.2. Điểm kiểm tra riêng cho SAML

| Cần xác minh | Vì sao |
| --- | --- |
| Chữ ký response/assertion và certificate được kiểm tra theo profile tích hợp | Tránh tin assertion giả mạo |
| Issuer, recipient, destination, audience phù hợp SP | Tránh assertion phát cho hệ khác bị sử dụng sai |
| Điều kiện thời gian có kiểm tra và chấp nhận clock skew hợp lý | Không nhận assertion hết hạn/chưa hiệu lực |
| InResponseTo/đặc tính chống replay được áp dụng khi luồng yêu cầu | Giảm khả năng dùng lại assertion hoặc trộn phiên |
| NameID/thuộc tính ánh xạ tới account đúng chủ thể | Tránh chiếm account vì email/name thay đổi |
| Single Logout nếu triển khai có kiểm thử, có giải pháp khi không hỗ trợ | Logout tại IdP không mặc định chấm dứt phiên SP |

Đây là checklist ý tưởng; phương pháp xác minh và cấu hình chi tiết phải phù hợp phiên bản giao thức và profile SAML mà ứng dụng thực sự hỗ trợ.

### 6.3. Điểm kiểm tra riêng cho OIDC/OAuth 2.0

- [ ] Chọn luồng đăng nhập phù hợp loại client; với ứng dụng hiện đại, sử dụng **Authorization Code Flow** và **PKCE** khi áp dụng, tránh luồng cũ không phù hợp.
- [ ] Ràng buộc **state** chống CSRF/lẫn phiên, dùng **nonce** trong các trường hợp OIDC cần chống replay và liên kết ID token với phiên.
- [ ] Client kiểm tra ID token: chữ ký, issuer, audience/client ID, thời gian hết hạn và các claim bắt buộc theo luồng.
- [ ] API sử dụng **access token** đúng audience và scope; không coi **ID token** là token cấp quyền gọi API.
- [ ] Redirect URI khớp chính xác cấu hình đã đăng ký; client secret, signing key, refresh token được bảo vệ theo loại client.
- [ ] Token có thời hạn phù hợp; refresh token được rotation/revoke theo khả năng IdP và yêu cầu rủi ro.
- [ ] Token không được ghi vào URL/log/analytics một cách làm lộ bí mật; lưu trữ phía client theo mô hình đe dọa phù hợp.
- [ ] Có mô hình thu hồi/đánh giá access token khi user disable, role đổi hoặc credential bị compromise.

**Ví dụ:** JWT access token tự chứa đã được ký có thể vẫn vượt qua kiểm tra chữ ký và hạn sử dụng ở resource server sau khi user IdP bị disable, nếu resource server không tra trạng thái mới hoặc không có cơ chế revoke. Vì vậy cần TTL, cơ chế kiểm tra trạng thái hoặc đường chặn khẩn cấp phù hợp; không thể khẳng định “disable SSO” tương đương “mọi API token đã chết”.

## 7. Checklist session, token và credential lifecycle

Authentication thường mở ra **một phiên tiếp tục sử dụng**, do đó xác thực tại login và kiểm soát phiên sau login phải được xét cùng nhau.

### 7.1. Vòng đời phiên

- [ ] Cookie phiên có các cờ bảo vệ phù hợp (Secure, HttpOnly, SameSite theo kịch bản ứng dụng) và không truyền qua HTTP không bảo vệ.
- [ ] Session ID đủ khó đoán, có cơ chế thay mới khi đăng nhập hoặc nâng cấp đặc quyền để hạn chế session fixation.
- [ ] Có idle timeout, absolute timeout và thời điểm buộc xác thực lại phù hợp rủi ro.
- [ ] Logout hủy phiên ở bên quản lý phiên; nút logout chỉ xóa giao diện không phải bằng chứng server đã chặn token.
- [ ] Có phương án thu hồi phiên trên thiết bị bị mất, khi reset credential, bị khóa tài khoản và khi Leaver.
- [ ] Session sau khi đổi role hoặc thuộc tính nhạy cảm được cập nhật quyền hoặc buộc xác thực/đánh giá lại theo thiết kế.
- [ ] Không dùng session/cookie chưa xác thực làm bằng chứng identity đã được xác minh.
- [ ] Tìm hiểu ứng dụng có nhiều phiên đồng thời trên thiết bị nào, và liệu có thể liệt kê/thu hồi từng phiên không.

### 7.2. Vòng đời token

| Token/credential | Kiểm tra khi cấp | Kiểm tra khi thu hồi |
| --- | --- | --- |
| **Access token** | Audience, scope, TTL, cách lưu/luân chuyển | Revoke/introspection/deny-list hoặc chờ hết hạn có kiểm soát, tùy hệ thống |
| **Refresh token** | Rotation, binding hoặc bảo vệ khỏi rò rỉ nếu hỗ trợ | Revoke refresh token, kiểm tra không thể phát hành access token mới |
| **API key / PAT** | Gắn owner, mục đích, scope tối thiểu, expiry | Revoke/rotate, quét key còn hiệu lực, thay credential trong automation |
| **Session cookie** | Secure, HttpOnly, SameSite, TTL | Invalidate ở server, xử lý các session đang mở |
| **SSH key / certificate** | Ai cấp, loại tài nguyên, kỳ hạn, nơi cất private key | Gỡ trust/authorized key, revoke certificate nếu có cơ chế và kiểm tra đường kết nối |
| **Recovery code** | Cấp qua kênh an toàn, bảo vệ như credential | Vô hiệu mã cũ khi reset/khôi phục theo chính sách |

Với token có thể thu hồi tức thời ở một hệ thống nhưng không ở hệ khác, nên ghi rõ **độ trễ tối đa dự kiến và biện pháp tạm chặn**. Không gán một TTL chung cho mọi loại credential mà bỏ qua mức rủi ro và khả năng ứng dụng.

### 7.3. Sơ đồ các phiên tồn tại sau SSO

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant APP as Ứng dụng
    participant IDP as IdP
    participant API as API / Resource server
    U->>APP: Yêu cầu đăng nhập
    APP->>IDP: Chuyển tới SSO
    IDP->>U: Xác thực + MFA khi yêu cầu
    IDP-->>APP: Kết quả federation hợp lệ
    APP-->>U: Cookie phiên hoặc token ứng dụng
    U->>API: Truy cập với token đã nhận
    Note over IDP: IdP có thể disable user về sau
    Note over APP,API: Phiên/token app có thể có TTL và cách thu hồi riêng
~~~

Sơ đồ nhấn mạnh cần kiểm tra **ai cấp token**, **ai xác minh**, **ai có thể revoke** và **khoảng thời gian token còn có thể được chấp nhận**.

## 8. Checklist Mover: thay đổi vai trò, thiết bị hoặc mức tin cậy

**Mover** là sự kiện thay đổi vị trí, dự án, tổ chức, quan hệ lao động hoặc trách nhiệm. Nó chủ yếu tác động **authorization**, nhưng có thể đòi hỏi thay đổi **authentication policy**.

### 8.1. Các câu hỏi cần kiểm tra

- [ ] Đã nhận sự kiện Mover có mã chủ thể, phiên bản và thời điểm hiệu lực từ nguồn đáng tin?
- [ ] Account IdP và app vẫn ánh xạ về đúng subjectId dù email, bộ phận hoặc tên hiển thị thay đổi?
- [ ] Role mới có yêu cầu MFA mạnh hơn, step-up authentication, thiết bị được quản lý hoặc vị trí mạng khác không?
- [ ] Người chuyển sang nhóm quản trị đã được xác minh bổ sung phù hợp rủi ro trước khi nhận đặc quyền?
- [ ] Nếu đổi thiết bị, người giữ thiết bị cũ còn có phiên, security key, certificate hoặc recovery method cần thu hồi không?
- [ ] Có quyền cũ cần revoke ở ứng dụng, đồng thời quyền đó có thể được cache trong token/phiên hiện tại không?
- [ ] Có direct grant hoặc app account độc lập vẫn cung cấp đường truy cập không hợp lệ?
- [ ] Các quyền tạm thời để bàn giao có owner, hạn hết hiệu lực và sự kiện thu hồi tự động hoặc được giám sát?
- [ ] Thay đổi được đọc lại và kiểm chứng trên các hệ đích liên quan?

**Ví dụ:** Nhân viên chuyển từ Support sang Finance. Có thể không cần thay passkey vì identity vẫn là cùng một người, nhưng phải gỡ role cũ, áp dụng chính sách MFA/step-up phù hợp truy cập tài chính, xử lý phiên CRM còn mang claim cũ nếu cần, và xác minh Finance không được quyền tự tạo rồi tự duyệt thanh toán.

### 8.2. Điều kiện hoàn tất Mover về authentication

Không nên coi việc đổi vai trò là lý do bắt buộc reset mọi credential nếu không có chỉ báo rủi ro. Tuy nhiên, nếu thay đổi quyền quản trị, thiết bị hoặc miền tin cậy, workflow phải xác định có cần **buộc tái xác thực, thêm factor chống phishing, kết thúc phiên cũ, hủy credential thiết bị cũ hoặc xoay secret** hay không. Kết quả cần khớp với chính sách mới của vai trò.

## 9. Checklist Leaver: chặn xác thực trên mọi đường

**Mục tiêu:** Tại thời điểm chấm dứt quan hệ có hiệu lực, chủ thể không còn khả năng sử dụng các đường đăng nhập và credential không hợp lệ. Quyền tài nguyên, phiên và tài sản số được xử lý đồng bộ với vòng đời danh tính.

### 9.1. Trước thời điểm chấm dứt

- [ ] Có sự kiện Leaver từ nguồn đáng tin và thời điểm hiệu lực có timezone; phân biệt nghỉ theo kế hoạch với chấm dứt khẩn cấp.
- [ ] Danh mục IdP account, SaaS, VPN, local account, cloud identity, repo, token, SSH key, credential thiết bị đã được liên kết với chủ thể.
- [ ] Có người phê duyệt đúng thẩm quyền cho các thao tác khẩn cấp theo quy trình.
- [ ] Đã xác định owner các dữ liệu, workflow, dashboard, tích hợp và automation cần bàn giao.
- [ ] Có phân loại các quyền không phụ thuộc SSO; không dựa vào một thao tác disable IdP để bao trùm tất cả.
- [ ] Nếu app không có API/SCIM, đã có manual task và người nhận xử lý.

### 9.2. Tại thời điểm chấm dứt

- [ ] Disable danh tính IdP và chặn những lần xác thực liên kết mới theo cơ chế hiện có.
- [ ] Revoke session và refresh token do IdP quản lý khi hỗ trợ, ghi nhận những gì không thể thu hồi tức thời.
- [ ] Disable/deprovision account ứng dụng thông qua SCIM/API hoặc thao tác thủ công có bằng chứng.
- [ ] Chặn local login và thu hồi quyền trên VPN, hệ thống quản trị, cloud và ứng dụng không liên kết SSO.
- [ ] Revoke API key/PAT/SSH key/certificate/credential cá nhân trong phạm vi liên quan, rotate secret dùng chung nếu có rủi ro.
- [ ] Xử lý app session/access token và kiểm soát TTL/deny-list/introspection theo khả năng hệ đích.
- [ ] Gỡ phương thức khôi phục, factor hoặc thiết bị liên kết không còn phù hợp với chính sách offboarding.
- [ ] Chuyển owner của workflow, tài sản số, lịch tác vụ và dữ liệu cần tiếp tục hoạt động.
- [ ] Giữ log, hồ sơ và dữ liệu cần thiết theo chính sách; không duy trì tài khoản hoạt động chỉ để lấy dữ liệu.

### 9.3. Đối soát sau thu hồi

| Kiểm tra | Kết quả cần quan sát |
| --- | --- |
| Thử đăng nhập mới qua IdP | Bị từ chối theo trạng thái inactive |
| Truy cập app bằng SSO mới | Không tạo phiên mới khi danh tính không hợp lệ |
| Truy cập bằng app session cũ | Bị chặn hoặc kết thúc trong giới hạn kiểm soát đã xác định |
| Local account / VPN | Không còn đường đăng nhập thuộc quan hệ cũ |
| API key / PAT / SSH key | Credential không còn được chấp nhận hoặc đã có biện pháp chặn phù hợp |
| App entitlement | Quyền không hợp lệ đã bị thu hồi trên hệ đích |
| Automation | Không phụ thuộc token cá nhân của Leaver; có workload owner hợp lệ |
| Hệ thống thất bại | Có trạng thái PARTIAL/FAILED, owner, biện pháp giảm rủi ro và thời hạn xử lý |

**Không kết luận Leaver hoàn tất chỉ vì API trả HTTP 200 hoặc cổng SSO từ chối đăng nhập.** Cần bằng chứng tại từng hệ đích và các đường credential độc lập. Nếu chưa thể xác minh token do app phát hành, phải nêu rõ giới hạn và theo dõi tiếp; không tự suy đoán chúng đã vô hiệu.

### 9.4. Luồng Leaver mẫu

~~~mermaid
flowchart TD
    HR["Leaver hợp lệ từ HR/sponsor"] --> TIME{"Đến thời điểm hiệu lực?"}
    TIME -->|Chưa| PLAN["Chuẩn bị mapping, owner, bàn giao"]
    PLAN --> TIME
    TIME -->|Có| BLOCK["Disable IdP và chặn đăng nhập mới"]
    BLOCK --> SESSION["Xử lý session / refresh token / API key"]
    SESSION --> APP["Disable app, local account, VPN, ACL"]
    APP --> VERIFY["Đọc lại trạng thái và kiểm tra truy cập"]
    VERIFY --> RESULT{"Có đường truy cập còn hiệu lực?"}
    RESULT -->|Không| DONE["Ghi bằng chứng, bàn giao, đóng sự kiện"]
    RESULT -->|Có hoặc chưa rõ| EX["Cảnh báo, chặn tạm, owner khắc phục"]
    EX --> VERIFY
~~~

Trong trường hợp khẩn cấp, có thể tiến hành nhiều thao tác chặn song song theo runbook, nhưng cần quản lý trạng thái từng đích và ngăn job cấp quyền cũ chạy lại.

## 10. Checklist danh tính máy, service account và workload authentication

Danh tính máy không qua HRIS như nhân viên. Nguồn vòng đời thường đến từ **khởi tạo workload, thay đổi nhiệm vụ, đổi owner hoặc ngừng dịch vụ**. Nếu không kiểm soát, service account có thể có credential tồn tại nhiều năm và quyền truy cập rộng.

### 10.1. Khi tạo và cấp credential cho workload

- [ ] Mỗi workload/service principal có owner, môi trường, hệ thống nguồn và mục đích rõ ràng.
- [ ] Tránh sử dụng tài khoản cá nhân hoặc PAT của nhân viên làm credential lâu dài cho automation.
- [ ] Ưu tiên **workload federation, managed identity hoặc credential ngắn hạn** khi nền tảng hỗ trợ.
- [ ] Nếu phải dùng API key/secret, lưu trong secret manager phù hợp, hạn chế người/tiến trình được đọc và có vòng rotation.
- [ ] Role, scope, audience và trust policy giới hạn đúng tài nguyên/môi trường; tránh một credential quản trị toàn bộ dev và prod.
- [ ] Không đặt secret trong source code, image container, log build hoặc biến môi trường hiển thị công khai.
- [ ] Có cách thu hồi credential mà không phải xóa toàn bộ dữ liệu hoặc gây gián đoạn không kiểm soát.
- [ ] Log xác thực workload phân biệt được từng danh tính, tránh tất cả job ghi thành một tài khoản chung không truy vết được.

### 10.2. Khi workload thay đổi hoặc ngừng hoạt động

- [ ] Workload Mover: tính lại quyền và trust relationship, gỡ quyền môi trường/dự án cũ.
- [ ] Khi người phụ trách nghỉ/chuyển nhóm, chuyển owner và rà soát credential, token, secrets của workload.
- [ ] Kiểm tra có user token/PAT cá nhân đang nhúng trong automation để chuyển sang danh tính workload.
- [ ] Workload Leaver: revoke key, role, federation trust, account và secret không còn cần; xác minh không còn request hợp lệ.
- [ ] Kiểm tra dependency trước khi cắt credential để có phương án duy trì hệ thống theo rủi ro; trường hợp credential đã bị lộ, ưu tiên biện pháp chặn thích hợp.
- [ ] Đối soát định kỳ workload đang hoạt động với danh mục service principal, owner và quyền hiệu lực.

**Ví dụ:** Một pipeline CI/CD dùng PAT cá nhân của nhân viên để deploy ứng dụng. Nhân viên nghỉ, IdP bị disable nhưng pipeline vẫn chạy được qua PAT. Hướng xử lý là tạo workload identity có owner và scope deploy tối thiểu, chuyển pipeline, revoke PAT, kiểm chứng job và lưu bằng chứng. Việc giữ PAT cũ đến vô thời hạn sẽ tạo quyền tồn dư không thuộc kiểm soát của SSO.

## 11. Checklist khôi phục tài khoản và truy cập khẩn cấp

Đăng nhập an toàn có thể bị phá vỡ bởi **recovery yếu**: kẻ tấn công không cần vượt qua MFA nếu có thể lừa nhân viên hỗ trợ reset MFA và gắn thiết bị mới.

### 11.1. Account recovery

- [ ] Có quy trình khôi phục cho người mất điện thoại, mất security key, khóa account hoặc không dùng được passkey.
- [ ] Helpdesk kiểm tra danh tính theo phương án đã duyệt, tránh dựa duy nhất vào thông tin dễ tra cứu hoặc người gọi tự khai.
- [ ] Thay factor, reset credential và mở khóa quyền nhạy cảm có bước xác thực/ủy quyền phù hợp rủi ro.
- [ ] Không dùng chỉ một email hoặc SMS có thể bị chiếm đoạt làm “bằng chứng đủ mạnh” cho mọi tình huống.
- [ ] Thay đổi factor được ghi log, cảnh báo user và/hoặc owner qua kênh tin cậy khi cần.
- [ ] Nếu nghi chiếm đoạt, có thể revoke phiên, khóa account, gỡ factor đáng ngờ và yêu cầu xác minh lại.
- [ ] Sau phục hồi, kiểm tra user không bị thêm role/grant bất thường; giữ sự kiện điều tra phù hợp quy trình.
- [ ] Recovery cho tài khoản đặc quyền chặt chẽ hơn khi mức rủi ro đòi hỏi.

### 11.2. Break-glass và sự cố IdP

- [ ] Có số lượng tài khoản break-glass giới hạn, owner và mục đích cụ thể.
- [ ] Credential được bảo vệ ở cơ chế lưu giữ riêng theo runbook; hoạt động sử dụng có cảnh báo và log.
- [ ] Có phê duyệt hoặc hậu kiểm bắt buộc theo chính sách khi tài khoản khẩn cấp được dùng.
- [ ] Tài khoản break-glass được kiểm thử có kiểm soát để bảo đảm khi IdP gặp sự cố vẫn truy cập được năng lực phục hồi cần thiết.
- [ ] Quyền break-glass giới hạn phạm vi có thể, không biến thành account dùng hàng ngày.
- [ ] Có quy trình rotate/revoke credential sau lần sử dụng và khi owner thay đổi.
- [ ] Đối soát break-glass vào danh mục IAM; không để nó trở thành đường truy cập tồn dư của Leaver.

### 11.3. Độ sẵn sàng của authentication

Chính sách bảo vệ cần xét cả gián đoạn: người dùng không thể xác thực khi IdP, DNS, mạng, dịch vụ MFA hoặc khóa ký federation lỗi. Hệ thống phải có người chịu trách nhiệm, phương án khôi phục và mức ưu tiên theo hoạt động kinh doanh.

- [ ] Biết IdP, MFA, DNS, PKI và ứng dụng nào là điểm phụ thuộc quan trọng.
- [ ] Có giám sát đăng nhập thất bại hàng loạt, hết hạn certificate và lỗi liên kết SAML/OIDC.
- [ ] Quản lý thay đổi signing key/certificate trước khi hết hạn; kiểm thử quá trình rotation và rollback.
- [ ] Có quy trình xử lý dịch vụ MFA không khả dụng mà vẫn bảo đảm phê duyệt, ghi log và giới hạn rủi ro.
- [ ] Có kênh quản lý incident, xác nhận tình trạng và khôi phục sau sự cố.
- [ ] Không mở vô hạn quyền đăng nhập yếu chỉ để xử lý sự cố tạm thời.

## 12. Kiểm toán authentication và bằng chứng hoàn tất

**Không phải log nhiều là tốt hơn.** Log phải đủ trả lời đúng câu hỏi, được bảo vệ khỏi sửa trái phép và tránh chứa bí mật.

### 12.1. Những sự kiện nên truy vết

| Sự kiện | Bằng chứng nên lưu | Vì sao |
| --- | --- | --- |
| Identity được tạo/kích hoạt | subjectId, eventId, nguồn, thời điểm, trạng thái | Chứng minh Joiner đúng chủ thể và thời gian |
| Credential/factor được đăng ký, thay đổi | User, actor, phương thức, kết quả, thời gian | Phát hiện chiếm quyền qua enrollment/recovery |
| Authentication success/failure | Subject/app, phương thức, outcome, bối cảnh rủi ro phù hợp | Phát hiện tấn công và phân tích sự cố |
| MFA challenge/step-up | Yêu cầu, phương thức, kết quả | Xác minh policy có được áp dụng |
| Session tạo/revoke | Hệ thống phát hành, session reference an toàn, mốc thời gian | Đánh giá thời gian sống của phiên |
| Token/API key cấp/revoke | Owner, scope, hệ đích, trạng thái, timestamp | Theo dõi credential độc lập |
| Thay đổi tài khoản/role | eventId, policyVersion, approver, target account, outcome | Nối authentication với authorization |
| Leaver disable/deprovision | Thời điểm cần khóa, hệ đích, readback và ngoại lệ | Chứng minh offboarding |
| Break-glass/recovery | Người yêu cầu, người xử lý, lý do, hậu kiểm | Theo dõi luồng rủi ro cao |

Không ghi password, private key, raw session cookie hoặc access/refresh token vào log. Với thông tin cá nhân trong log, áp dụng nguyên tắc tối thiểu hóa, phân quyền truy cập và thời hạn lưu giữ theo chính sách, nghĩa vụ liên quan.

### 12.2. Mẫu bằng chứng cho một kiểm tra

~~~yaml
checkId: AUTH-LEAVER-007
subjectId: EMP-2104
eventId: HR-2026-0312
phase: LEAVER
targetSystem: crm-production
control: "Disable app account and revoke local sessions"
expected: "No valid app login or local session"
effectiveAt: "2026-11-30T17:00:00+07:00"
owner: "CRM Application Owner"
operationResult: "SUCCESS"
verifiedAt: "2026-11-30T17:02:13+07:00"
verificationResult: "PASS"
evidenceReference: "audit://case/HR-2026-0312/crm"
exception: null
~~~

Các giá trị là **ví dụ giả định**; link bằng chứng là định danh minh họa, không phải địa chỉ lưu trữ thật. Nên lưu reference thay vì nhúng dữ liệu nhạy cảm vào phiếu kiểm tra. Nếu verification không thực hiện được, ghi **UNKNOWN/PENDING** và người chịu trách nhiệm, không tự điền PASS.

### 12.3. Chỉ số vận hành

| Chỉ số | Ý nghĩa |
| --- | --- |
| **MFA coverage** | Tỷ lệ account trong phạm vi đã đăng ký và thực sự áp dụng MFA theo chính sách |
| **Phishing-resistant MFA coverage** | Tỷ lệ nhóm rủi ro cao dùng yếu tố có khả năng chống phishing |
| **Recovery exception rate** | Số trường hợp khôi phục yếu tố xác thực ngoại lệ hoặc xử lý thủ công |
| **Authentication failure anomalies** | Đăng nhập lỗi bất thường theo user/app/nguồn, phân tích cùng false positive |
| **Session revocation latency** | Độ trễ từ mốc yêu cầu thu hồi đến khi phiên liên quan không còn hợp lệ |
| **Leaver authentication closure** | Tỷ lệ Leaver đã xác minh mọi đường xác thực trong danh mục |
| **Orphan credential count** | Key/token/credential không gắn được với chủ thể/workload/owner còn hợp lệ |
| **Unmanaged local login coverage** | Ứng dụng còn local login ngoài policy hoặc chưa có cách kiểm soát |
| **Certificate/key expiry incidents** | Sự cố login do certificate/key hết hạn hoặc rotation lỗi |

Mọi chỉ số phải ghi **mẫu số, phạm vi, thời điểm đo và điều kiện PASS**. Ví dụ, “100% MFA enrollment” không có nghĩa toàn bộ luồng đăng nhập đều buộc MFA; “IdP disable trong hai phút” không chứng minh app session cũng bị thu hồi trong hai phút.

## 13. Kiểm thử checklist theo tình huống

Kiểm thử phải có cả **đường thành công** và **đường bị từ chối**, theo một account thử nghiệm được phép, môi trường phù hợp và người giám sát. Tránh thử trên tài khoản người khác hoặc làm gián đoạn production ngoài quy trình.

| ID | Tình huống | Kỳ vọng kiểm tra |
| --- | --- | --- |
| A01 | Joiner chưa đến ngày bắt đầu | Không truy cập dữ liệu ngoài phạm vi pre-hire |
| A02 | Joiner hợp lệ đã đăng ký MFA | SSO yêu cầu đúng factor, app ánh xạ account chính xác |
| A03 | Credential sai hoặc đăng nhập bất thường | Bị từ chối hoặc yêu cầu step-up/chặn theo policy; có log |
| A04 | Người dùng thử endpoint legacy không MFA | Không bỏ qua được policy bắt buộc |
| A05 | Mover từ role thường sang role nhạy cảm | Có phê duyệt, step-up/MFA mạnh theo chính sách |
| A06 | Mover đã gỡ role cũ nhưng session còn mở | Kiểm chứng quyền cũ bị chặn theo cách app thực thi |
| A07 | Leaver bị disable IdP | Đăng nhập SSO mới bị từ chối |
| A08 | Leaver có local account | Local login bị chặn, có bằng chứng tại app |
| A09 | Leaver có PAT/API key | Token đã revoke hoặc đường truy cập đã chặn theo cơ chế được kiểm chứng |
| A10 | Thay factor bằng recovery | Có xác minh lại, log và thông báo theo chính sách |
| A11 | IdP/SSO certificate được rotation | Phiên hợp lệ sau rotation hoạt động, chữ ký sai bị từ chối |
| A12 | Job Mover cũ chạy lại sau Leaver | Không được cấp lại tài khoản, factor hoặc role |
| A13 | Chủ sở hữu workload nghỉ việc | Workload không dùng PAT cá nhân, có owner và credential hợp lệ |
| A14 | Connector deprovision thất bại | Workflow ở trạng thái PARTIAL/FAILED, có owner/escalation |

### 13.1. Bài tập: phân tích 3 lỗi tưởng nhỏ

**Tình huống 1 — “MFA đã bật” nhưng admin vẫn đăng nhập qua API bằng password.**  
Kiểm tra luồng API có bị bỏ ngoài chính sách không, credential có scope nào, client có phải account đặc quyền không, và có phương án chuyển sang cơ chế an toàn hơn. Ghi rõ kết quả xác thực qua SSO và API độc lập.

**Tình huống 2 — “Đã khóa nhân viên” nhưng trang báo cáo vẫn mở.**  
Điều tra app session đã phát hành, token của resource server, account local và cách app xử lý logout/revoke. Xác minh bằng trạng thái thực tế thay vì chỉ xem status IdP.

**Tình huống 3 — “Đã đổi bộ phận” nhưng user bị chặn không vào được app mới.**  
Phân biệt lỗi account chưa được SCIM provision, role mới chưa được duyệt, attribute chưa đồng bộ, MFA/thiết bị không thỏa policy và lỗi giao thức SSO. Xử lý ở đúng lớp, không tùy tiện hạ bảo mật để user đăng nhập.

## 14. Mẫu checklist bàn giao cho một hệ thống

Có thể dùng mẫu này trong access review, onboarding ứng dụng hoặc buổi kiểm tra IAM định kỳ:

| Nhóm kiểm soát | Câu hỏi PASS/FAIL | Người chịu trách nhiệm | Bằng chứng cần lưu |
| --- | --- | --- | --- |
| **Danh tính** | Có nguồn chính thức và ID bất biến? | HR/sponsor + IAM | Mapping và event |
| **Đăng nhập** | Mọi đường login đều được kiểm kê? | App owner | Auth flow, cấu hình |
| **MFA** | Policy áp dụng đúng nhóm rủi ro? | IAM/Security | Policy và ca test |
| **Federation** | SAML/OIDC xác minh issuer/audience/chữ ký/thời gian? | IAM + App owner | Cấu hình, kết quả kiểm thử |
| **Credential** | Khóa/secret/factor có vòng đời và recovery an toàn? | IAM + Security | Log enrollment/rotation |
| **Phiên** | Có timeout, logout, revoke phù hợp? | App owner | Test session/token |
| **JML** | Joiner/Mover/Leaver thay đúng trạng thái? | IAM + HR | Event và readback |
| **SCIM/API** | Có phương án provision và disable thực tế? | IAM + App owner | Request ID và trạng thái đích |
| **Quyền** | Role/ABAC/ACL khớp chính sách? | Owner dữ liệu | Entitlement inventory |
| **Service account** | Có owner, scope, expiry, cách revoke? | Platform owner | Workload inventory |
| **Recovery** | Reset factor được kiểm soát và kiểm toán? | Helpdesk/Security | Runbook và log |
| **Kiểm toán** | Có log, alert, readback và ngoại lệ? | Security/Audit | Dashboard, báo cáo |

**Cách chấm kết quả:** ghi **PASS** khi có bằng chứng kiểm chứng; **FAIL** khi không đạt; **PENDING/UNKNOWN** khi chưa đủ thông tin; **N/A** chỉ khi có lý do và người xác nhận. Kèm mức rủi ro, người xử lý, hạn khắc phục và ngày tái kiểm tra. Không đánh dấu PASS chỉ vì công cụ có tính năng tương ứng nhưng chưa cấu hình hoặc chưa kiểm thử.

## 15. Tổng kết

Checklist authentication phải theo cả vòng đời **Joiner–Mover–Leaver**: xác minh đúng chủ thể và đăng ký credential an toàn; áp dụng IdP/SSO/MFA, session và token theo mức rủi ro; đánh giá lại điều kiện xác thực khi vai trò hoặc thiết bị đổi; thu hồi mọi đường đăng nhập và credential không còn hợp lệ khi Leaver. Với service account, điểm kích hoạt là vòng đời workload và chủ sở hữu thay vì sự kiện HR thông thường.

Hãy giữ chuỗi kiểm tra **Nguồn danh tính đáng tin → Credential và MFA → Federation/SSO → Session/token → Quyền tại ứng dụng → Thu hồi và đọc lại → Bằng chứng kiểm toán**. Authentication an toàn chỉ trở thành kiểm soát vòng đời đáng tin khi có thể chứng minh **đường truy cập nào đã được mở, đường nào đã bị chặn, vào lúc nào và bằng cách nào xác minh kết quả**.
