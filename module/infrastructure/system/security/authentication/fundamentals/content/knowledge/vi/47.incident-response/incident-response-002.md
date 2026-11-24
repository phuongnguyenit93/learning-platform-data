# Sự cố chiếm tài khoản — Ứng phó khi attacker kiểm soát danh tính người dùng

Một nhân viên nhận email giả mạo trang đăng nhập và nhập password vào website do attacker kiểm soát. Vài phút sau, identity provider ghi nhận đăng nhập thành công từ thiết bị chưa từng thấy. Attacker đăng ký thêm một phương thức MFA, tạo refresh token mới, thay recovery email và bắt đầu tải dữ liệu từ ứng dụng nội bộ. Bộ phận hỗ trợ nhận được thông báo rằng người dùng không thể đăng nhập, nhưng session của attacker vẫn hoạt động. Nếu đội ứng phó chỉ reset password, attacker có thể tiếp tục truy cập bằng refresh token, passkey hoặc API key vừa tạo.

**Sự cố chiếm tài khoản (account takeover — ATO)** xảy ra khi một đối tượng không được phép giành hoặc duy trì quyền kiểm soát một account hợp lệ. Attacker có thể sử dụng password bị đánh cắp, phishing, MFA fatigue, session cookie, refresh token, passkey enrollment bị lạm dụng, recovery flow hoặc quyền của một workload. Hậu quả có thể bao gồm đọc/sửa dữ liệu, gian lận, tạo persistence, chiếm các account liên kết hoặc dùng danh tính bị chiếm để tấn công hệ thống khác.

Ứng phó ATO là quá trình có phối hợp giữa security operations, identity team, application owner, IT/help desk, legal/privacy và người phụ trách nghiệp vụ. Cần xác nhận sự cố, bảo toàn bằng chứng, giới hạn quyền attacker, thu hồi mọi credential/session liên quan, khôi phục quyền kiểm soát cho đúng chủ thể và xác minh không còn persistence. Reset password là một biện pháp trong chuỗi xử lý, không phải toàn bộ quy trình.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, bài học này kết nối credential, password, MFA, passkey, certificate, token, session, federation và account recovery với incident response. Người học sẽ biết cách phân loại mức độ, dựng timeline, xác định actor/subject, containment theo rủi ro, revoke token/session/factor, kiểm tra API key và workload credential, khôi phục account an toàn, đánh giá phạm vi dữ liệu bị truy cập và cải thiện kiểm soát sau sự cố.

## 1. Nhận diện sự cố chiếm tài khoản

Không phải mọi đăng nhập bất thường đều là ATO. Một user có thể đổi thiết bị, đi công tác, dùng VPN hoặc nhập sai password. Sự cố được nghi ngờ khi có bằng chứng cho thấy credential hoặc session bị sử dụng ngoài ý muốn của chủ account, hoặc các thay đổi bảo mật được thực hiện bởi actor không được ủy quyền.

### 1.1. Dấu hiệu thường gặp

- Login thành công sau một đợt password spraying hoặc credential stuffing.
- MFA push bị từ chối nhiều lần rồi bất ngờ được approve.
- Người dùng báo không đăng nhập được hoặc nhận thông báo login/reset không yêu cầu.
- Session hoặc refresh token xuất hiện từ thiết bị/network không phù hợp.
- Recovery email/phone, MFA factor hoặc passkey bị thêm/xóa ngoài quy trình.
- Password, API key, OAuth consent hoặc application password bị thay đổi bất thường.
- Một account tạo API key, token, app password hoặc credential mới có quyền rộng.
- Một phiên đã logout hoặc bị revoke vẫn tiếp tục gọi API.
- Email forwarding rule, mailbox delegate, OAuth app consent hoặc recovery setting bị thay đổi.
- Tài khoản đặc quyền thực hiện hành động nhạy cảm ngoài change window.
- Một account dormant đột nhiên truy cập dữ liệu lớn hoặc endpoint quản trị.

### 1.2. Nguồn phát hiện

| Nguồn | Tín hiệu |
| --- | --- |
| Identity provider | Login risk, password failure burst, MFA challenge, factor enrollment |
| Session/token service | Concurrent session, refresh token reuse, session rotation, revocation |
| Endpoint/MDM | Malware, device compliance giảm, browser extension hoặc process bất thường |
| Email/collaboration | Phishing report, inbox rule, OAuth consent, forwarding/delegation change |
| API gateway/application | Principal, audience, scope, route, export và privilege change |
| Help desk/recovery | Password reset, recovery contact change, support-assisted unlock |
| Fraud/business system | Payment change, beneficiary change, order/export bất thường |
| User report | Login notification, MFA prompt không yêu cầu, dữ liệu bị thay đổi |

Một tín hiệu đơn lẻ có thể chưa đủ. Correlate login, MFA, session, recovery, privilege và hành động dữ liệu theo principal, device, request và thời gian.

### 1.3. Phân biệt exposure, suspicious authentication và confirmed ATO

- **Credential exposure:** password, token hoặc private key có khả năng bị lộ nhưng chưa có bằng chứng đã bị sử dụng.
- **Suspicious authentication:** có login hoặc challenge bất thường cần xác minh.
- **Suspected ATO:** có dấu hiệu account bị điều khiển bởi actor khác.
- **Confirmed ATO:** bằng chứng đủ cho thấy actor không được phép đã kiểm soát account hoặc thực hiện hành động trái phép.

Phân loại có thể thay đổi khi có thêm bằng chứng. Không trì hoãn containment cần thiết chỉ vì chưa xác định được danh tính attacker; đồng thời không kết luận user có hành vi sai trái chỉ dựa trên log thể hiện account của họ.

## 2. Mục tiêu và nguyên tắc ứng phó

Ứng phó ATO cần đạt các mục tiêu theo thứ tự ưu tiên:

1. Bảo vệ người dùng và ngăn thiệt hại đang diễn ra.
2. Ngăn attacker tiếp tục sử dụng account, session, token, factor và credential đã tạo.
3. Bảo toàn bằng chứng có thể phục vụ điều tra.
4. Xác định phạm vi account, thiết bị, ứng dụng, tenant và dữ liệu bị ảnh hưởng.
5. Khôi phục danh tính và quyền truy cập cho đúng chủ thể.
6. Loại bỏ persistence và nguyên nhân gốc.
7. Xác minh hệ thống an toàn trước khi đóng sự cố.
8. Cải thiện detection, recovery và control để giảm khả năng tái diễn.

### 2.1. Nguyên tắc thực thi

- **Contain first when harm is ongoing:** nếu attacker đang export dữ liệu hoặc thực hiện giao dịch, giới hạn hành động ngay trong khi điều tra tiếp tục.
- **Preserve evidence:** ghi lại timeline, event reference và quyết định trước khi thay đổi state nếu điều đó không làm tăng thiệt hại.
- **Revoke comprehensively:** xử lý mọi credential/session liên quan, không chỉ password.
- **Verify the rightful owner:** dùng quy trình identity proofing/recovery tin cậy trước khi cấp lại quyền.
- **Least privilege:** chỉ khôi phục quyền cần thiết, không tự động cấp lại mọi role cũ nếu cần review.
- **Communicate safely:** liên hệ người dùng qua kênh đã biết, không dùng email/phone vừa bị thay đổi trong sự cố làm kênh xác minh duy nhất.
- **Record decisions:** mỗi containment, exception, restore và override phải có actor, reason, time và approval.

Nếu chỉ tập trung giữ dịch vụ luôn hoạt động, attacker có thể tiếp tục dùng session và credential. Nếu khóa đồng loạt mọi account hoặc revoke toàn bộ credential của tổ chức theo một tín hiệu yếu, tổ chức có thể tự gây outage lớn. Hành động phải dựa trên bằng chứng, blast radius, mức độ nhạy cảm và khả năng rollback.

## 3. Vai trò và chỉ huy sự cố

ATO thường vượt phạm vi một nhóm. Cần xác định Incident Commander (IC) và người chịu trách nhiệm từng luồng.

| Vai trò | Trách nhiệm |
| --- | --- |
| Incident Commander | Điều phối, severity, ưu tiên, quyết định và cập nhật trạng thái |
| Identity/IdP owner | Login, MFA, passkey, federation, recovery, session và token revocation |
| Security analyst/IR | Triage, evidence, timeline, scope và threat hunting |
| Endpoint/IT | Cô lập thiết bị, kiểm tra malware, reimage và device trust |
| Application/data owner | Chặn API/action, đánh giá dữ liệu và khôi phục nghiệp vụ |
| Help desk/account recovery | Xác minh chủ thể qua quy trình an toàn, hỗ trợ reset |
| Legal/privacy | Đánh giá nghĩa vụ thông báo, bảo toàn evidence và xử lý dữ liệu cá nhân |
| Communications | Thông báo người dùng, khách hàng, đối tác và lãnh đạo |
| Fraud/finance | Chặn giao dịch, payment destination và tổn thất tài chính |

Một người có thể đảm nhiệm nhiều vai trò ở tổ chức nhỏ, nhưng quyền phê duyệt và quyền thực thi thao tác đặc quyền nên được tách khi có thể. Người bị nghi liên quan tới sự cố không nên tự phê duyệt việc khôi phục quyền của chính mình.

### 3.1. Severity

Đánh giá severity theo loại account, quyền, bằng chứng, phạm vi, tác động, trạng thái attacker và khả năng lan rộng.

| Mức | Ví dụ | Nhịp phản ứng |
| --- | --- | --- |
| Critical | Privileged account bị chiếm, attacker đang truy cập dữ liệu/điều khiển hệ thống | Kích hoạt IR ngay, containment khẩn cấp và chỉ huy tập trung |
| High | ATO được xác nhận, session/token còn hoạt động hoặc có dữ liệu nhạy cảm | Revoke/contain ngay, điều tra và khôi phục ưu tiên |
| Medium | Có dấu hiệu takeover nhưng chưa thấy hành động trái phép | Step-up/temporary restriction, xác minh nhanh và theo dõi |
| Low | Credential exposure hoặc anomaly chưa có bằng chứng sử dụng | Bảo vệ credential, kiểm tra log và theo dõi theo policy |

Severity là quyết định vận hành, không phải nhãn cố định. Nâng mức khi có bằng chứng mới hoặc giảm mức sau khi containment và scope đã được xác minh.

## 4. Quy trình ứng phó end-to-end

~~~mermaid
flowchart TD
    A[Alert / user report] --> B[Triage and validate]
    B --> C[Declare incident and assign owner]
    C --> D[Preserve evidence and build timeline]
    D --> E[Contain account, sessions and devices]
    E --> F[Revoke tokens, factors and persistence]
    F --> G[Scope data, apps and linked identities]
    G --> H[Eradicate root cause]
    H --> I[Recover rightful owner securely]
    I --> J[Monitor and validate clean state]
    J --> K[Close, notify and lessons learned]
~~~

Các bước có thể chạy song song khi cần. Ví dụ, containment session có thể diễn ra ngay trong khi analyst bảo toàn audit event; không chờ hoàn tất toàn bộ timeline nếu attacker đang gây thiệt hại.

## 5. Triage và xác nhận ban đầu

Mục tiêu triage là hiểu alert có đáng tin, account nào bị ảnh hưởng và liệu hành động trái phép còn diễn ra.

### 5.1. Thông tin cần thu thập

- Principal/account reference và tenant.
- Thời điểm phát hiện, event time và ingest time.
- Authentication method: password, passkey, MFA, certificate, federation.
- Device, browser, app, OS và posture.
- Source network, ASN, proxy/VPN context và độ tin cậy.
- Session ID/reference, token family, client ID, audience và scope.
- Các lần login failure/success, challenge/approval và recovery event.
- Thay đổi password, factor, recovery contact, linked identity và role.
- Hành động sau login: API call, export, mailbox rule, payment change.
- Người dùng có xác nhận hành động hay không qua kênh đáng tin cậy.

Không thu thập raw password, OTP, recovery code, access token, refresh token, session cookie hoặc private key để điều tra. Dùng event ID, credential reference, token family reference và audit query.

### 5.2. Kiểm tra khả năng hợp lệ

Trước khi kết luận, xem xét:

- User vừa đổi thiết bị, browser, mạng hoặc đi công tác?
- Có VPN/corporate egress/NAT làm thay đổi địa chỉ nguồn?
- Có deployment, migration, test hoặc support action đã được phê duyệt?
- Client có retry refresh token do network timeout hoặc race condition?
- IdP hoặc log pipeline có sự cố làm timestamp/outcome sai?
- Có shared workstation hoặc kiosk được phép sử dụng?

Những yếu tố này giúp tránh false positive nhưng không được dùng để bỏ qua dấu hiệu rõ như MFA prompt không yêu cầu, recovery contact bị thay hoặc export dữ liệu trái phép.

### 5.3. Xác minh với chủ account

Liên hệ qua kênh đã đăng ký và được biết là đáng tin trước sự cố, ví dụ số help desk nội bộ hoặc quy trình xác minh đã thiết lập. Không yêu cầu user gửi password, OTP, recovery code hoặc token cho analyst. Hỏi về:

- Login/device/notification mà họ không nhận ra.
- MFA prompt họ không khởi tạo.
- Email, phone, factor hoặc passkey vừa bị thay đổi.
- File, message, payment hoặc setting bất thường.
- Link/email/QR hoặc cuộc gọi họ đã tương tác.

User không nhận ra một sự kiện là tín hiệu quan trọng, nhưng không tự nó chứng minh attacker đã truy cập dữ liệu. Cần kết hợp log phía server.

## 6. Bảo toàn bằng chứng trước và trong containment

Khi có thể thực hiện an toàn, ghi lại evidence trước khi thay đổi account state. Không trì hoãn containment khẩn cấp để chụp mọi log.

### 6.1. Evidence checklist

- Identity provider sign-in/audit events.
- MFA, passkey và recovery events.
- Session/token issuance, refresh, reuse và revocation records.
- API gateway, application và database audit.
- Email/collaboration sign-in, forwarding, OAuth consent và delegate changes.
- Endpoint/EDR/MDM telemetry và device inventory.
- Secret manager, KMS, PKI và workload identity audit.
- Change ticket, deployment record và support case.
- User report, phishing email/header, URL/domain và thời điểm tương tác.
- Alert ID, rule version, query, time range và analyst notes.

### 6.2. Chain of custody

1. Lưu bản export read-only hoặc snapshot theo quy trình.
2. Ghi nguồn, người thu thập, thời điểm, query và phạm vi.
3. Tạo hash của artifact export khi phù hợp.
4. Giữ audit trail của người truy cập, sao chép và chuyển giao.
5. Lưu trong storage được kiểm soát, phân quyền và retention.
6. Phân biệt dữ kiện, suy luận và giả thuyết.

Không chỉnh sửa bản gốc để làm sạch dữ liệu. Có thể tạo bản đã redact cho chia sẻ, giữ bản gốc theo quy trình evidence.

## 7. Containment: ngăn attacker tiếp tục truy cập

Containment phải bao phủ account, session, token, factor, recovery, device, application và credential downstream. Chọn hành động theo rủi ro và khả năng gây gián đoạn.

### 7.1. Account và session

- Đánh dấu account compromised hoặc tạm disable theo policy.
- Revoke toàn bộ session liên quan, gồm browser, mobile, remembered device và federated session nếu hỗ trợ.
- Invalidate session cookie phía server; không chỉ xóa cookie trên một browser.
- Revoke refresh token family và token exchange grant liên quan.
- Buộc reauthentication cho các session khác nếu không thể xác định session an toàn.
- Chặn các action nhạy cảm hoặc giảm scope tạm thời trong lúc điều tra.
- Kiểm tra session vẫn hoạt động ở downstream app sau revocation.

Một access token JWT đã phát hành có thể tiếp tục hợp lệ đến thời điểm exp nếu resource server xác minh offline và không có denylist/introspection. Cần hiểu revocation propagation của từng hệ thống; nếu cần containment tức thời, có thể disable principal, revoke refresh token, invalidate session, chặn ở gateway hoặc áp policy deny theo subject/token family.

### 7.2. Password và credential tĩnh

- Reset password qua quy trình recovery đã xác minh chủ thể.
- Revoke application password, legacy password, API key hoặc client secret nếu có khả năng bị lộ.
- Kiểm tra password reset email, recovery contact và email account liên kết.
- Không yêu cầu user đổi password qua link không xác minh hoặc gửi password cho support.
- Nếu password reuse có khả năng, khuyến nghị thay đổi ở các dịch vụ khác qua kênh riêng và không thu thập password dùng lại.

Reset password không tự thu hồi mọi session, OAuth grant, API key hoặc app password. Mỗi loại credential cần xử lý theo lifecycle riêng.

### 7.3. MFA và passkey

- Kiểm tra factor nào được thêm/xóa/reset trong khoảng thời gian sự cố.
- Thu hồi factor do attacker thêm.
- Revoke recovery code đã phát hành trước hoặc trong sự cố.
- Yêu cầu re-enroll MFA/passkey qua quy trình identity proofing tin cậy.
- Kiểm tra thiết bị authenticator, sync account và cloud account liên quan nếu threat model bao gồm.
- Ưu tiên phương thức chống phishing như passkey/WebAuthn hoặc security key phù hợp.
- Kiểm tra MFA fatigue, push approval và support-assisted reset.

Không xóa mọi factor hợp lệ trước khi xác minh user có phương thức phục hồi an toàn; có thể làm chủ account bị khóa hoàn toàn. Với privileged account, dùng quy trình break-glass/recovery có dual control.

### 7.4. Recovery contact và linked identity

- Kiểm tra email/phone recovery có bị thay đổi.
- Khôi phục contact về giá trị đã xác minh trước sự cố nếu đúng chủ thể.
- Thu hồi recovery token, reset link và pending recovery transaction.
- Kiểm tra federated identity link, external IdP, social login và account merge.
- Revoke OAuth app consent hoặc delegated grant không được phép.
- Kiểm tra mailbox forwarding, inbox rule, delegate và recovery email access.

Nếu mailbox chính bị chiếm, dùng chính mailbox đó để gửi recovery link sẽ trao quyền lại cho attacker. Chọn kênh xác minh độc lập theo policy.

### 7.5. Device và workload

- Cô lập endpoint có dấu hiệu malware/session theft.
- Revoke device trust/certificate hoặc remove managed device enrollment khi có bằng chứng.
- Chặn token/credential từ workload bị compromise.
- Rotate secret/API key/certificate mà workload có thể đã đọc.
- Isolate pod/VM hoặc pipeline runner; giữ image/log/evidence cần thiết.
- Kiểm tra workload identity, service account, secret manager access và KMS usage.

### 7.6. Containment matrix

| Dấu hiệu | Hành động ưu tiên | Kiểm tra sau containment |
| --- | --- | --- |
| Password bị lộ, chưa thấy session lạ | Reset qua recovery tin cậy, kiểm tra login/session | Password cũ không dùng được; session cũ theo policy đã revoke |
| Refresh token reuse được xác nhận | Revoke token family và session liên quan | Refresh cũ bị từ chối ở authorization server |
| MFA factor lạ được thêm | Disable/revoke factor lạ, step-up/recovery | Chỉ factor đã xác minh còn active |
| Passkey không nhận ra | Revoke credential reference, kiểm tra device/account sync | Credential lạ không xác thực được |
| API key bị lạm dụng | Disable/rotate key, giới hạn client/scope | Key cũ bị upstream từ chối |
| Certificate private key có thể bị lộ | Revoke certificate, rotate key và trust mapping | Certificate cũ không còn được chấp nhận |
| Admin account bị chiếm | Disable hoặc restrict, revoke sessions/tokens, dual-control recovery | Không còn privileged session hoặc grant lạ |
| Email account bị chiếm | Contain mailbox, rule/delegate/OAuth grants và recovery path | Không còn forwarding/delegation trái phép |

## 8. Thu hồi token, session và federation grant

Token là một trong những nơi dễ bị bỏ sót sau password reset.

### 8.1. Access token và refresh token

- Xác định issuer, client, subject, audience, scope và token family.
- Revoke refresh token/grant ở authorization server.
- Invalidate server-side session và refresh state.
- Kiểm tra opaque token introspection và cache.
- Với JWT offline validation, dùng denylist/subject disable hoặc gateway policy nếu cần chặn trước expiry.
- Kiểm tra token exchange đã tạo token downstream hay chưa.
- Xác nhận resource server/gateway nhận revocation trong SLA.

Không ghi raw token vào ticket hoặc chat. Dùng token family reference, jti đã xử lý an toàn hoặc issuance event ID.

### 8.2. OAuth consent và federated session

Attacker có thể duy trì quyền qua OAuth application grant, refresh token hoặc federated session:

- Liệt kê grant/consent được tạo hoặc thay đổi trong cửa sổ sự cố.
- Kiểm tra client ID, publisher/owner, scope và thời điểm cấp.
- Revoke grant không được phép.
- Kiểm tra IdP session và upstream/downstream session.
- Xác minh account linking không gắn nhầm subject.
- Kiểm tra SAML/OIDC federation mapping và trust policy nếu account liên quan.

Logout khỏi một ứng dụng không nhất thiết logout khỏi IdP hoặc mọi ứng dụng federated. Cần xác minh từng session boundary.

### 8.3. Token propagation và service-to-service

Nếu user token được exchange thành token nội bộ, truy vết token descendant theo subject/actor/audience. Revoke nguồn có thể không tự thu hồi token đã phát hành ở downstream. Kiểm tra STS, gateway, service mesh và cache introspection.

## 9. Tìm persistence và đường truy cập phụ

Sau khi chặn session chính, attacker có thể còn đường truy cập khác. Kiểm tra:

- API key, app password, client secret hoặc personal access token mới.
- OAuth consent, delegated permission và service principal mới.
- MFA factor, passkey, recovery code hoặc recovery contact lạ.
- Trusted device, browser session, app password và remembered device.
- Email forwarding, inbox rules, delegate, mailbox app và transport rule.
- SSH key, cloud access key, certificate, VPN profile hoặc remote access agent.
- Local admin, scheduled task, startup item, browser extension hoặc malware.
- Workload identity, CI/CD token, service account và secret manager lease.
- Role/group membership, admin consent, conditional access exception.
- Linked account, external identity hoặc account merge.

### 9.1. Persistence checklist

| Nơi kiểm tra | Ví dụ persistence |
| --- | --- |
| Identity provider | Factor lạ, recovery contact, trusted device, federated link |
| OAuth ecosystem | Consent, refresh grant, app registration, service principal |
| Email/collaboration | Forwarding rule, delegate, inbox rule, app integration |
| Cloud/control plane | Access key, role assignment, workload identity federation |
| Developer tooling | PAT, SSH key, deploy key, CI secret, runner token |
| Endpoint | Malware, browser extension, credential stealer, remote access |
| Application | API key, webhook, secondary admin, recovery path |
| PKI | Certificate, private key, trust mapping hoặc CA enrollment |

Không xóa artifact trước khi bảo toàn evidence nếu nó có thể giúp xác định vector hoặc attacker infrastructure. Khi cần chặn ngay, ghi nhận state và action theo incident procedure trước khi thay đổi.

## 10. Xác định phạm vi ảnh hưởng

Scope assessment trả lời account nào, resource nào, dữ liệu nào và khoảng thời gian nào có thể bị ảnh hưởng.

### 10.1. Account và identity graph

- Account chính và account liên kết.
- Admin/delegate/service account có thể bị truy cập qua account này.
- Tenant, organization, role và group.
- Application/client đã cấp token hoặc consent.
- Device và session.
- Workload/API key/certificate mà account có thể quản lý.

### 10.2. Dữ liệu và hành động

- Dữ liệu đã đọc, export, download hoặc truy vấn.
- Dữ liệu đã sửa/xóa.
- Payment/beneficiary/billing/contact change.
- Email/message/file đã gửi hoặc chia sẻ.
- User/role/permission đã tạo hoặc nâng quyền.
- API key/token/certificate đã phát hành.
- Secret/key đã đọc hoặc sử dụng.
- Thao tác quản trị hoặc thay đổi cấu hình.

### 10.3. Time window

Xác định:

- Thời điểm credential có khả năng bị lộ.
- Login/session đầu tiên không được công nhận.
- Thời điểm attacker tạo factor/token/recovery path.
- Thời điểm containment có hiệu lực ở từng hệ thống.
- Thời điểm credential downstream cuối cùng bị revoke.

Không lấy thời điểm alert làm thời điểm bắt đầu compromise nếu có thể có hoạt động trước đó. Mở rộng time window khi có token/session lifetime dài, log retention thiếu hoặc credential reuse.

### 10.4. Phân loại tác động

| Tác động | Câu hỏi |
| --- | --- |
| Confidentiality | Attacker có đọc hoặc export dữ liệu không? |
| Integrity | Có thay đổi account, policy, file, payment hoặc record không? |
| Availability | User hoặc service có bị khóa/gián đoạn không? |
| Financial | Có giao dịch, chuyển tiền, fraud hoặc chargeback không? |
| Privacy | Có dữ liệu cá nhân hoặc dữ liệu nhạy cảm bị truy cập không? |
| Lateral movement | Account có tạo credential hoặc truy cập hệ thống khác không? |

Ghi rõ điều gì đã xác nhận, điều gì có khả năng xảy ra và điều gì chưa thể xác định do thiếu log. Không khẳng định không có dữ liệu bị truy cập chỉ vì không tìm thấy event nếu audit coverage không đầy đủ.

## 11. Eradication: loại bỏ nguyên nhân và persistence

Eradication diễn ra sau khi attacker đã bị containment đủ để thay đổi hệ thống an toàn.

- Loại bỏ malware, phishing persistence hoặc browser extension độc hại.
- Reimage/re-enroll thiết bị nếu integrity không thể tin cậy.
- Rotate password, token, API key, client secret, certificate và private key liên quan.
- Xóa OAuth grant, factor, passkey, trusted device và recovery path không được phép.
- Sửa conditional access, session policy, redirect URI, trust relationship hoặc role assignment bị thay đổi.
- Vá lỗ hổng, sửa cấu hình và loại bỏ đường bypass.
- Thu hồi credential ở upstream/downstream và xác minh revocation propagation.
- Kiểm tra account khác có credential reuse hoặc bị ảnh hưởng cùng vector.

Nếu attacker lấy được password qua phishing, chỉ xóa email phishing khỏi inbox không giải quyết việc credential đã bị lộ. Nếu attacker chiếm mailbox, reset password IdP nhưng giữ mailbox session có thể cho phép attacker lấy lại recovery link.

## 12. Khôi phục account cho đúng chủ thể

Khôi phục là một hoạt động authentication nhạy cảm. Nếu attacker vẫn kiểm soát email, phone, device hoặc factor cũ, recovery flow có thể trao lại account cho attacker.

### 12.1. Xác minh danh tính

Chọn quy trình dựa trên assurance và rủi ro:

- Dùng kênh liên hệ đã xác minh trước sự cố và không bị nghi compromise.
- Yêu cầu identity proofing hoặc support verification theo policy.
- Dùng yếu tố độc lập còn tin cậy; không dựa duy nhất vào email vừa bị thay.
- Với account đặc quyền, yêu cầu dual approval hoặc xác minh trực tiếp theo quy trình.
- Kiểm tra account ownership, tenant và employee/customer record.
- Ghi người xác minh, evidence reference, approval và thời điểm.

Không yêu cầu người dùng gửi password, OTP, private key hoặc recovery code cho nhân viên hỗ trợ. Không dùng câu hỏi bảo mật yếu hoặc dữ liệu công khai để thay thế identity proofing.

### 12.2. Khôi phục credential

Sau khi xác minh:

1. Cấp password mới hoặc passwordless enrollment theo policy.
2. Revoke mọi session/token/factor/recovery code cũ có khả năng bị kiểm soát.
3. Đăng ký lại MFA/passkey trên thiết bị tin cậy.
4. Xác minh recovery email/phone và linked identity.
5. Revoke OAuth grant, API key và app password không cần thiết.
6. Khôi phục role/group sau khi review privilege changes.
7. Yêu cầu reauthentication cho ứng dụng nhạy cảm.
8. Gửi thông báo qua kênh đáng tin cậy về thay đổi bảo mật.

Không khôi phục tất cả factor hoặc thiết bị trước sự cố một cách tự động. Chỉ thêm lại yếu tố đã xác minh còn an toàn.

### 12.3. Khôi phục privileged account

Với admin hoặc account có quyền cao:

- Dùng quy trình break-glass đã được kiểm soát.
- Dual control cho reset factor, cấp lại role hoặc tạo credential.
- Tạm cấp quyền tối thiểu và có expiry.
- Bắt buộc phishing-resistant MFA/passkey/security key phù hợp.
- Kiểm tra privileged session và admin action sau recovery.
- Review toàn bộ service principal, access key và delegated grant do account quản lý.

Không dùng một account admin khác chưa được xác minh để reset account bị chiếm mà không có audit/approval.

## 13. Xác minh sạch trước khi đóng containment

Sau khi khôi phục, xác minh attacker không còn đường truy cập.

### 13.1. Validation checklist

- Password/credential cũ không còn dùng được.
- Session và refresh token cũ bị revoke theo policy.
- Access token hoặc downstream session không còn được chấp nhận ngoài thời hạn/deny policy.
- MFA factor, passkey, recovery code và contact lạ đã bị thu hồi.
- OAuth consent, API key, app password và client credential lạ đã bị revoke.
- Certificate/private key và workload identity bị ảnh hưởng đã rotate/revoke.
- Email forwarding/delegate/rule lạ đã bị loại bỏ.
- Device được kiểm tra, làm sạch hoặc reimage.
- Role/group/policy đã được khôi phục hoặc phê duyệt.
- Audit trail không còn activity bất thường sau containment.
- User xác nhận có thể đăng nhập bằng phương thức mới và không nhận prompt lạ.
- Alert/detection được bật và theo dõi tăng cường trong thời gian hậu sự cố.

### 13.2. Hypercare

Trong khoảng thời gian theo dõi tăng cường:

- Theo dõi login, MFA, session, token refresh và recovery changes.
- Theo dõi export, payment, privilege và API key creation.
- Alert khi credential cũ hoặc device bị revoke tiếp tục xuất hiện.
- Liên hệ user qua kênh tin cậy nếu có dấu hiệu tái xâm nhập.
- Giữ owner và escalation path cho tới khi risk giảm theo tiêu chí.

Thời lượng hypercare tùy severity, token lifetime, data sensitivity và độ đầy đủ của telemetry; không dùng một con số chung cho mọi sự cố.

## 14. Thông báo và phối hợp

Thông báo phải chính xác, kịp thời và không tiết lộ thêm thông tin cho attacker.

### 14.1. Với người dùng bị ảnh hưởng

Thông báo:

- Điều gì đã được xác nhận và điều gì đang được điều tra.
- Những hành động bảo vệ đã thực hiện.
- Cách đăng nhập/recovery an toàn qua kênh chính thức.
- Dấu hiệu cần báo lại như MFA prompt hoặc session lạ.
- Kênh hỗ trợ đã xác minh.
- Những việc người dùng không nên làm: chia sẻ OTP, password, recovery code hoặc cài công cụ hỗ trợ từ nguồn lạ.

Không gửi raw evidence, IP attacker chưa xác minh hoặc chi tiết control có thể giúp attacker né detection.

### 14.2. Với khách hàng/đối tác và cơ quan liên quan

Legal/privacy và incident leadership đánh giá nghĩa vụ thông báo theo pháp luật, hợp đồng, ngành và khu vực dữ liệu. Cần xác định loại dữ liệu, số lượng chủ thể, khả năng truy cập/exfiltration, thời điểm phát hiện và thời hạn thông báo. Không tự suy diễn nghĩa vụ pháp lý từ một template kỹ thuật.

### 14.3. Với help desk

- Cung cấp quy trình xác minh identity và escalation.
- Cảnh báo social engineering giả danh người dùng/nhân viên IR.
- Tạm dừng reset factor qua quy trình yếu nếu có nguy cơ bị lạm dụng.
- Ghi lại mọi support action với actor, approval và ticket.
- Không gửi password/OTP hoặc recovery secret qua chat/email.

## 15. Ví dụ: điều tra chuỗi ATO

Giả sử một user báo có MFA prompt lạ. Timeline:

| Thời điểm | Event | Nhận định |
| --- | --- | --- |
| 08:41 | User nhấp link phishing | Credential có thể bị thu thập |
| 08:43 | Login password success từ device mới | Session mới đáng ngờ |
| 08:44 | 9 MFA push bị deny, 1 prompt được approve | Có dấu hiệu MFA fatigue |
| 08:45 | Refresh token family mới | Có session/token persistence |
| 08:47 | Recovery email changed | Attacker có thể kiểm soát recovery |
| 08:51 | OAuth consent cấp scope mail/files | Có thể duy trì truy cập downstream |
| 08:56 | API export dữ liệu | Có thể có exfiltration |
| 09:02 | User báo help desk | Detection từ user report |

### 15.1. Hành động ưu tiên

1. Mở incident High/Critical tùy quyền và dữ liệu.
2. Bảo toàn IdP, MFA, token, OAuth consent, mailbox và API audit.
3. Revoke session/token family và OAuth grant; chặn export nếu vẫn diễn ra.
4. Khôi phục recovery email sau khi xác minh kênh độc lập.
5. Revoke factor/passkey lạ, đăng ký lại phishing-resistant factor.
6. Kiểm tra mailbox rule, forwarding, delegate và app consent.
7. Xác định dữ liệu export, người nhận, thời gian và downstream copy.
8. Kiểm tra endpoint/browser, xử lý phishing và reimage nếu cần.
9. Rotate credential liên quan và theo dõi hypercare.

### 15.2. Vì sao reset password là chưa đủ?

Attacker có thể vẫn giữ refresh token, browser session, OAuth grant, recovery email, MFA factor hoặc API key. Nếu chỉ reset password, các credential đã phát hành có thể tiếp tục hoạt động theo semantics của từng hệ thống. Phải xác minh và revoke từng đường persistence.

## 16. Java: mô hình trạng thái incident và containment

Ví dụ dưới đây minh họa cách biểu diễn incident state và yêu cầu containment có audit. Đây là pseudocode, không phải implementation hoàn chỉnh.

~~~java
public enum AtoIncidentState {
    DETECTED,
    TRIAGED,
    CONTAINING,
    CONTAINED,
    INVESTIGATING,
    RECOVERING,
    HYPERCARE,
    CLOSED
}

public record AtoIncident(
    String incidentId,
    String principalRef,
    String tenantRef,
    String severity,
    AtoIncidentState state,
    Instant detectedAt,
    String incidentCommander
) {}

public record ContainmentRequest(
    String incidentId,
    String principalRef,
    Set<String> sessionRefs,
    Set<String> tokenFamilyRefs,
    String reason,
    String approvalRef
) {}

public interface IdentityContainment {
    void disableOrRestrictPrincipal(String principalRef, String reason);
    void revokeSessions(Set<String> sessionRefs, String reason);
    void revokeTokenFamilies(Set<String> tokenFamilyRefs, String reason);
}
~~~

### 16.1. Thực thi có kiểm soát

~~~java
@Transactional
public void contain(ContainmentRequest request, Principal responder) {
    authorization.require(responder, "incident.account.contain",
        request.principalRef());
    approvalService.requireValid(request.approvalRef(), request.incidentId());

    incidentRepository.transition(
        request.incidentId(),
        AtoIncidentState.TRIAGED,
        AtoIncidentState.CONTAINING
    );

    identityContainment.disableOrRestrictPrincipal(
        request.principalRef(), request.reason()
    );
    identityContainment.revokeSessions(
        request.sessionRefs(), request.reason()
    );
    identityContainment.revokeTokenFamilies(
        request.tokenFamilyRefs(), request.reason()
    );

    outboxRepository.insert(
        AuditEvent.accountContainment(
            request.incidentId(),
            principalRefs.of(responder),
            request.principalRef(),
            request.reason(),
            request.approvalRef()
        )
    );
}
~~~

Production không nên giả định nhiều hệ thống identity/session/token cùng nằm trong một database transaction. Cần orchestration idempotent, retry có trạng thái, timeout, partial failure handling và reconciliation. Nếu một revoke thất bại, incident phải thể hiện containment một phần và tiếp tục retry/escalate; không đánh dấu contained chỉ vì một API call thành công.

### 16.2. Không tự động disable theo một tín hiệu yếu

Automation có thể hỗ trợ revoke session/token khi risk cao, nhưng cần confidence threshold, evidence reference, scope cụ thể, approval cho hành động diện rộng, idempotency, audit và rollback/recovery path. Không tự động khóa account quản trị khẩn cấp chỉ từ một tín hiệu yếu.

## 17. Query điều tra minh họa

Ví dụ SQL để tìm credential lifecycle change và session mới quanh thời điểm ATO:

~~~sql
SELECT
    event_time,
    actor_ref,
    subject_ref,
    event_type,
    resource_ref,
    outcome,
    reason_code,
    request_id
FROM identity_audit
WHERE subject_ref = :principal_ref
  AND event_time BETWEEN :start_time AND :end_time
  AND event_type IN (
      'authentication.success',
      'mfa.factor.enrolled',
      'mfa.factor.removed',
      'recovery.contact.changed',
      'session.created',
      'token.refresh',
      'token.revoked',
      'oauth.grant.created',
      'api_key.created'
  )
ORDER BY event_time;
~~~

Ví dụ KQL-style để tìm session activity sau khi account bị đánh dấu compromised:

~~~text
let Principal = "principal-ref";
let IncidentStart = datetime(2026-01-01T08:30:00Z);
IdentityAudit
| where TimeGenerated >= IncidentStart
| where SubjectRef == Principal or ActorRef == Principal
| project TimeGenerated, EventType, ActorRef, SubjectRef,
          ResourceRef, Outcome, SessionRef, TokenFamilyRef,
          ClientId, Audience, SourceNetworkRef, RequestId
| order by TimeGenerated asc
~~~

Query chỉ là mẫu; tên bảng/field và thời gian phải khớp SIEM thực tế. Với delegated action, lọc cả actor và subject; mở rộng sang linked identity, token family, device và downstream service. Không export raw token vào kết quả.

## 18. Những lỗi ứng phó thường gặp

| Lỗi | Hậu quả | Cải thiện |
| --- | --- | --- |
| Chỉ reset password | Refresh token, session, factor hoặc OAuth grant vẫn hoạt động | Revoke toàn bộ credential/session liên quan |
| Chỉ logout trên một browser | Session server-side và thiết bị khác vẫn tồn tại | Server-side session/token revocation |
| Tin recovery email vừa bị đổi | Attacker nhận recovery link | Dùng kênh độc lập đã xác minh trước sự cố |
| Gửi OTP/recovery code cho support | Tạo thêm đường lộ credential | Identity proofing và workflow không yêu cầu secret |
| Xóa factor cũ trước khi xác minh user | Chủ account bị khóa, recovery dễ bị lạm dụng | Plan factor transition và dual control |
| Không kiểm tra OAuth consent | Attacker duy trì truy cập mailbox/files | Review và revoke grant/refresh token |
| Bỏ qua API key/app password | Persistence tiếp tục qua credential phụ | Inventory và revoke theo từng loại |
| Không cô lập endpoint bị nhiễm | Attacker lấy lại credential sau recovery | EDR containment, clean/reimage |
| Disable account mà không bảo toàn evidence | Mất context hoặc khó điều tra | Snapshot/audit export khi an toàn |
| Khóa mọi account theo IP mới | DoS user hợp lệ | Risk-based, principal/device correlation |
| Đánh dấu contained quá sớm | Downstream token/session vẫn còn hiệu lực | Reconciliation và propagation check |
| Không đánh giá dữ liệu đã export | Bỏ sót privacy/fraud impact | Scope theo resource, data owner và time window |
| Thông báo qua mailbox bị chiếm | Attacker biết kế hoạch hoặc chặn recovery | Kênh liên hệ độc lập |
| Không theo dõi sau recovery | Attacker quay lại qua persistence | Hypercare và detection tăng cường |
| Không audit thao tác IR | Không biết ai revoke/reset/override | Incident action audit và approval |
| Xóa phishing evidence quá sớm | Mất IOC và vector ban đầu | Bảo toàn email/header/URL theo quy trình |

## 19. Ma trận kiểm thử quy trình ATO

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Password bị lộ nhưng chưa có login | Credential được bảo vệ/rotate theo policy; kiểm tra session hiện hữu |
| Login thành công sau password spraying | Risk tăng và correlation tạo case |
| MFA push fatigue dẫn tới approve | Session/token được điều tra; containment theo risk |
| Attacker thêm MFA factor | Factor lạ bị revoke, owner recovery được xác minh |
| Attacker thêm passkey | Credential reference bị thu hồi; đăng ký lại bằng quy trình tin cậy |
| Recovery email bị thay | Recovery qua email mới bị tạm dừng cho tới khi xác minh |
| Refresh token reuse | Token family bị revoke theo semantics của issuer |
| JWT offline còn hạn sau password reset | Gateway/resource policy chặn theo containment plan |
| OAuth grant lạ | Grant và refresh token bị revoke; downstream session được kiểm tra |
| API key mới được tạo | Key ID/owner/scope được truy vết và key lạ bị disable |
| Certificate private key nghi lộ | Certificate/key bị revoke/rotate và trust propagation được xác minh |
| Email forwarding rule lạ | Rule/delegate bị xóa sau khi bảo toàn evidence |
| Admin account bị chiếm | Dual-control recovery, privileged session revoke và audit |
| Endpoint có malware | Cô lập, giữ evidence, clean/reimage trước khi tin lại |
| Workload identity bị lạm dụng | Disable/restrict principal, revoke lease/token và rotate downstream secret |
| Session revoke ở IdP nhưng API vẫn chấp nhận token | Detection xác định propagation gap; gateway/resource containment |
| Nhiều account cùng source IP | Không khóa toàn bộ chỉ từ IP; correlate cohort và device |
| Người dùng đổi thiết bị hợp lệ | Xác minh qua step-up, tránh false positive và không hạ policy |
| Support reset MFA | Actor, subject, approval và evidence được audit đầy đủ |
| Incident containment một phần | State không được đánh dấu contained; retry/escalate phần thất bại |
| IR automation chạy lại | Action idempotent, không tạo side effect lặp |
| Recovery hoàn tất | Factor/session cũ lạ bị revoke; user xác nhận login an toàn |
| Sau recovery có login lạ | Hypercare alert và escalation hoạt động |
| Audit store bị thiếu event | Scope ghi rõ uncertainty; không tuyên bố không có truy cập |
| Legal/privacy review cần evidence | Export read-only có hash, access log và chain of custody |

### Tình huống thực hành

Một tài khoản quản lý tài chính bị phishing. Attacker đăng nhập bằng password, vượt MFA push sau nhiều prompt, thêm passkey trên thiết bị riêng, đổi recovery phone, tạo OAuth grant đọc email và files, rồi tạo API key để gọi endpoint export. User báo sự cố từ số help desk nội bộ. IdP đã revoke session chính nhưng một API gateway vẫn chấp nhận access JWT còn hạn; mailbox có forwarding rule tới địa chỉ ngoài.

**Yêu cầu:** lập kế hoạch xử lý trong giờ đầu, sau đó khôi phục và đóng sự cố.

**Hướng phân tích:**

1. Chỉ định IC, severity High/Critical, mở case và xác định owner cho IdP, endpoint, mailbox, API và data.
2. Bảo toàn IdP/MFA/passkey/recovery/token/OAuth/API gateway/mailbox audit; ghi event IDs, time range và chain of custody.
3. Tạm disable/restrict account, revoke mọi session/refresh token family, chặn subject/token ở gateway và resource server cho tới khi JWT cũ hết hiệu lực hoặc bị deny.
4. Revoke passkey lạ, recovery phone, OAuth grant, API key và mailbox forwarding rule; kiểm tra app password/delegate khác.
5. Cô lập thiết bị của user và điều tra phishing/browser; không dùng mailbox hoặc phone vừa bị đổi để recovery.
6. Xác minh user qua kênh độc lập; cấp lại factor chống phishing, password mới và recovery contact đã xác minh.
7. Xác định dữ liệu export, email/file truy cập, người nhận, downstream copy và nghĩa vụ thông báo với legal/privacy.
8. Kiểm tra mọi credential cũ bị từ chối, downstream session đã revoke, API gateway propagation đã hoàn tất và user đăng nhập sạch.
9. Theo dõi hypercare, rà soát MFA fatigue, OAuth consent, token revocation và recovery workflow.
10. Thực hiện post-incident review, cải thiện gateway revocation, factor enrollment alert, help desk identity proofing và phishing resistance.

## 20. Post-incident review và cải thiện

Sau containment/recovery, tổ chức cần tìm nguyên nhân gốc và điểm kiểm soát đã thất bại. Không chỉ hỏi “ai bấm link?”; cần xem tại sao credential bị chấp nhận, vì sao attacker có thể thêm factor, vì sao token còn hoạt động và vì sao hành động nhạy cảm không bị phát hiện.

### 20.1. Câu hỏi review

- Vector ban đầu là phishing, password reuse, malware, recovery abuse hay token theft?
- Có thể phát hiện sớm hơn từ telemetry nào?
- MFA/passkey có chống phishing không và enrollment có được bảo vệ?
- Session/token revocation có lan tới gateway và downstream đúng SLA?
- Recovery channel có độc lập và được identity proofing không?
- Có credential phụ hoặc OAuth grant nào bị bỏ sót?
- Help desk có thể bị social engineering qua quy trình nào?
- API có authorization theo resource/tenant và rate limit phù hợp không?
- Audit trail có đủ event, integrity và retention không?
- User có nhận được cảnh báo và hỗ trợ an toàn không?

### 20.2. Hành động cải thiện

- Bắt buộc phishing-resistant MFA/passkey cho account nhạy cảm.
- Thêm step-up/approval cho factor enrollment, recovery change và OAuth consent.
- Giảm access/refresh token lifetime hoặc dùng sender-constrained token theo risk.
- Cải thiện revoke propagation và gateway deny capability.
- Thêm audit cho token, session, factor, API key, recovery và linked identity.
- Hạn chế legacy auth, application password và shared credential.
- Bảo vệ email/recovery channel và help desk workflow.
- Cải thiện device posture, endpoint detection và browser security.
- Tăng detection correlation sau login: recovery change → token issue → export.
- Thực hành tabletop và test ATO định kỳ.

### 20.3. Metrics

| Metric | Mục đích |
| --- | --- |
| Time to detect | Từ hoạt động đầu tiên đến phát hiện |
| Time to contain | Từ xác nhận đến chặn session/credential |
| Revocation propagation | Thời gian revoke có hiệu lực ở từng downstream |
| Scope determination time | Thời gian xác định account/resource/dữ liệu ảnh hưởng |
| Recovery time | Thời gian trả quyền cho đúng chủ thể |
| Persistence findings | Số factor/token/grant/key lạ được tìm thấy |
| Re-entry rate | Tỷ lệ attacker quay lại sau containment |
| User impact | Số user bị khóa nhầm, downtime hoặc hỗ trợ |
| Evidence completeness | Mức độ đầy đủ của audit/log/device evidence |

Đặt mục tiêu dựa trên risk và kiến trúc thực tế; không tối ưu time-to-contain bằng cách revoke bừa bãi gây outage.

## 21. Câu hỏi tự kiểm tra

1. **Account takeover là gì?** Attacker giành hoặc duy trì quyền kiểm soát account hợp lệ ngoài ý muốn của chủ thể.
2. **Vì sao reset password chưa đủ?** Session, refresh token, MFA factor, passkey, OAuth grant, API key và recovery path có thể vẫn hoạt động.
3. **Khi nào cần containment trước khi điều tra xong?** Khi attacker còn hoạt động hoặc thiệt hại đang diễn ra; bảo toàn bằng chứng trong phạm vi an toàn.
4. **Vì sao cần phân biệt actor và subject?** Log có thể cho biết account thực hiện hành động, nhưng chưa chứng minh người thật điều khiển account.
5. **Có nên dùng recovery email vừa bị thay để khôi phục account?** Không nếu nó có khả năng bị attacker kiểm soát; cần kênh độc lập đã xác minh.
6. **JWT offline validation gây khó khăn gì cho revocation?** Token còn hạn có thể được chấp nhận nếu resource server không có denylist/introspection hoặc policy chặn.
7. **Cần kiểm tra persistence ở đâu?** Factor/passkey, recovery, OAuth grant, API key, app password, email rule, device, certificate và workload identity.
8. **Vì sao phải cô lập endpoint?** Malware hoặc session stealer có thể lấy credential mới ngay sau khi recovery.
9. **Khi nào có thể đóng sự cố?** Khi containment, revocation, scope, eradication, recovery, validation và monitoring đáp ứng tiêu chí; uncertainty phải được ghi rõ.
10. **Post-incident review nên tập trung vào điều gì?** Nguyên nhân gốc và control gap, không chỉ hành vi của người dùng.

**Ghi nhớ:** Ứng phó sự cố chiếm tài khoản phải xử lý toàn bộ chuỗi danh tính. Xác nhận và phân loại sự cố, bảo toàn bằng chứng, containment account/session, revoke token/factor/recovery/OAuth/API key, tìm persistence, xác định dữ liệu ảnh hưởng và khôi phục cho đúng chủ thể qua kênh tin cậy. Chỉ đóng sự cố sau khi downstream revocation được xác minh, thiết bị và recovery path sạch, audit đủ để tái dựng và có kế hoạch theo dõi sau recovery.
