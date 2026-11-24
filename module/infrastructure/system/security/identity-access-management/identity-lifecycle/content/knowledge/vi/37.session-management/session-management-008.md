# Concurrent session: quản lý nhiều phiên đồng thời trong IAM Identity Lifecycle

> **Chương: Session management.** **Concurrent session** là tình huống một danh tính có **nhiều phiên đăng nhập hoặc phiên truy cập còn hiệu lực tại cùng một thời điểm**, có thể qua các trình duyệt, thiết bị, ứng dụng, mạng hoặc kênh quản trị khác nhau. Quản lý concurrent session quyết định **bao nhiêu phiên được tồn tại, loại nào được tính, phiên nào phải bị chặn hoặc kết thúc khi vượt ngưỡng**, đồng thời bảo đảm hạn chế đó **thực sự được cưỡng chế** tại IdP, ứng dụng và Resource Server. Trong quản lý vòng đời danh tính IAM, phiên đồng thời liên quan trực tiếp tới **Joiner–Mover–Leaver (JML)**, IdP/SSO, OIDC/SAML, SCIM, RBAC/ABAC/PBAC, PAM, service identities, kiểm toán và giảm quyền truy cập tồn dư.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa concurrent session và phân biệt **IdP session, RP/application session, browser session, token, token family, thiết bị và kết nối mạng**.
2. Thiết kế chính sách **số phiên tối đa, phạm vi đếm, eviction, ưu tiên phiên đặc quyền, thiết bị đáng tin, idle/absolute timeout và thời hạn token**.
3. Giải thích vì sao **chặn đăng nhập mới ở IdP** không mặc nhiên chấm dứt mọi phiên ứng dụng, token và PAM session đã phát.
4. Triển khai cơ chế **tạo, gia hạn, thay thế và kết thúc phiên an toàn** trong ứng dụng phân tán; xử lý race, timeout, retry, cache và nhiều tab.
5. Phân tích rủi ro **session fixation, cookie theft, token replay, session hijack, share account, impossible travel và session sprawl**, nhưng không coi nhiều phiên luôn là dấu hiệu tấn công.
6. Xử lý **JML, chuyển vai trò, đình chỉ, thu hồi account, thiết bị mất kiểm soát, privileged access/JIT** và không để phiên cũ tiếp tục dùng quyền trái policy.
7. Áp dụng cách đánh giá riêng cho **non-human identities, service accounts, workload tokens và long-lived credentials** thay vì dùng cứng giới hạn phiên của User.
8. Xây dựng pseudocode, ma trận kiểm thử, giám sát và bằng chứng **desired–observed–effective session access**.

## 1. Concurrent session là gì?

Giả sử nhân viên Lan đã đăng nhập vào cổng công việc trên laptop ở văn phòng. Lan sau đó mở ứng dụng trên điện thoại và đăng nhập thêm trên máy tính bảng để xử lý công việc. Cả ba nơi đều có thể sở hữu **phiên hoặc token riêng còn hợp lệ**. Đó là ví dụ thông thường về **concurrent sessions**, không mặc nhiên là lạm dụng.

Trong trường hợp khác, một quản trị viên có một phiên PAM thao tác production và đồng thời có một phiên từ trình duyệt lạ. Nếu chính sách chỉ cho **một phiên admin hoạt động** hoặc đòi quản trị viên phải dùng thiết bị được quản lý, hệ thống phải có khả năng **phát hiện và cưỡng chế** điều kiện tương ứng.

### Những khái niệm không được đánh đồng

| Đối tượng | Nó đại diện cho | Có phải một concurrent session? |
| --- | --- | --- |
| **IdP/SSO session** | Phiên xác thực của một User tại Identity Provider. | Có, nếu policy đang đếm phiên IdP. |
| **RP/application session** | Phiên của User trong một ứng dụng cụ thể. | Có, nhưng khác IdP session; một SSO login có thể tạo nhiều RP sessions. |
| **Browser tab** | Một giao diện trình duyệt. | **Không nhất thiết**; nhiều tab có thể chia sẻ cùng cookie và cùng app session. |
| **Device** | Laptop, điện thoại, kiosk, managed endpoint. | Không đồng nghĩa session; một device có thể chứa nhiều phiên và nhiều User. |
| **Access token** | Chứng cứ quyền truy cập cho một Resource Server theo audience/scope/expiry. | Không đồng nghĩa phiên; một session có thể phát nhiều access tokens. |
| **Refresh token/token family** | Cơ chế xin access token mới theo policy. | Không nhất thiết là login session, nhưng ảnh hưởng số phiên còn tái cấp token được. |
| **HTTP/TCP/WebSocket connection** | Một kết nối vận chuyển hoặc ứng dụng. | Có thể thuộc một session; không đếm mọi connection thành một login. |
| **PAM/JIT privileged session** | Phiên/khoảng quyền đặc quyền tại broker hoặc target. | Có, nhưng phạm vi rủi ro khác session User thông thường. |
| **Service-to-service credential** | Token/khóa/certificate của máy hoặc workload. | Cần chính sách workload riêng; không nên dùng số browser sessions làm thước đo. |

### Từ khóa quan trọng: “còn hiệu lực” khác “đang hoạt động”

Một phiên có thể:

- **Active/usable:** token/session hiện có thể được chấp nhận khi gọi tài nguyên.
- **Idle:** không có hành động gần đây nhưng chưa hết hạn, vẫn có thể sử dụng.
- **Suspended/restricted:** được lưu nhưng không được thực hiện những hành động theo chính sách.
- **Revoked/terminated:** lẽ ra không còn được sử dụng, cần kiểm chứng tại điểm thực thi.
- **Expired:** đã quá thời hạn, không còn hợp lệ nếu mọi bên cưỡng chế expiry đúng.
- **Unknown:** hệ thống không có đủ dữ liệu để kết luận, chẳng hạn session của app không tích hợp.

Định nghĩa **concurrent** phải nêu rõ **đếm phiên có thể dùng được, phiên có trạng thái ACTIVE trong registry, hay phiên có hoạt động gần đây**. Ba tập có thể khác nhau; một báo cáo “2 active sessions” chưa chứng minh chỉ còn hai con đường truy cập hiệu lực.

## 2. Cấu trúc một session và các ID cần phân biệt

Một session có thể được biểu diễn trong kho ứng dụng bằng bản ghi logic:

~~~json
{
  "sessionId": "sess-8e4f",
  "subjectIdentityId": "IAM:ID-LAN-2041",
  "accountRef": "idp-a/sub-2041",
  "clientId": "finance-portal",
  "tenantId": "tenant-b",
  "deviceRef": "uem:tenant-b:device-882",
  "authTime": "2026-12-01T08:15:00+07:00",
  "createdAt": "2026-12-01T08:15:00+07:00",
  "lastActivityAt": "2026-12-01T08:40:00+07:00",
  "absoluteExpiresAt": "2026-12-01T20:15:00+07:00",
  "idleExpiresAt": "2026-12-01T09:10:00+07:00",
  "privilegeTier": "STANDARD",
  "state": "ACTIVE",
  "policyVersion": "session-standard-v4",
  "sessionEpoch": 12
}
~~~

Đây là **schema nội bộ minh họa**, không phải định dạng chuẩn của OAuth, OIDC, SCIM hay một nhà cung cấp IdP. Session ID và các trường có thể khác; không lưu cookie bí mật, refresh token nguyên vẹn hay private key trong log hoặc bảng phân tích.

### Những chiều xác định phạm vi session

| Chiều | Câu hỏi | Lý do |
| --- | --- | --- |
| **Identity** | Session thuộc người hay workload nào? | Đếm đúng một chủ thể dù có alias/admin account. |
| **Account** | Nó xuất phát từ account IdP/local nào? | Điều tra đăng nhập và liên kết với quản lý account. |
| **Client/RP** | Ứng dụng nào tạo session? | Hạn 2 phiên ở Finance không nhất thiết giới hạn HR portal. |
| **Tenant** | Phiên thuộc tổ chức/pháp nhân nào? | Tránh gộp session giữa tenant không liên quan. |
| **Device** | Thiết bị nào và trust state hiện hành? | Có thể giới hạn một phiên cho mỗi thiết bị hoặc chặn thiết bị mất. |
| **Privilege tier** | Standard, sensitive, privileged? | Chính sách admin thường chặt hơn. |
| **Authentication assurance** | MFA/step-up mới nhất khi nào? | Quyền nhạy cảm có thể yêu cầu reauth. |
| **Token/session linkage** | Token family, session handle và các RP sessions liên quan? | Thu hồi đúng đường thay vì khóa nhầm mọi nơi. |
| **Lifecycle/policy version** | Quyết định dựa trên trạng thái HR/IGA/IdP nào? | Chặn retry cấp lại phiên sau Mover/Leaver. |

### Một danh tính có thể có nhiều session ở nhiều lớp

~~~text
IAM identity: IAM:ID-LAN-2041
  IdP session: idp-sso-001 (Laptop)
    RP Finance session: finance-sess-77
    RP CRM session: crm-sess-34
    OAuth access token: token-A (aud=Finance API)
    OAuth access token: token-B (aud=CRM API)
  IdP session: idp-sso-002 (Phone)
    RP Finance session: finance-sess-81
  Privileged activation:
    PAM session: pam-operator-003
~~~

Một IdP session có thể sinh nhiều RP sessions; một RP session có thể phát nhiều token. **Không đếm mỗi access token thành một phiên đăng nhập** hoặc kết luận xóa một token sẽ làm tất cả phiên cùng mất hiệu lực.

## 3. Vì sao cần chính sách concurrent session?

### Mục tiêu bảo mật

1. **Hạn chế session sprawl:** giảm số điểm có thể sử dụng account khi token/thiết bị bị lộ.
2. **Phát hiện truy cập bất thường:** session mới từ thiết bị/địa điểm trái thói quen, token replay hoặc dùng account chung.
3. **Bảo vệ quyền đặc quyền:** ngăn một admin có nhiều phiên quản trị ngoài kiểm soát hoặc sử dụng đồng thời trên những context xung đột.
4. **Thu hồi có mục tiêu:** cho phép User xem/chấm dứt các phiên cụ thể sau báo mất device.
5. **Bảo đảm JML:** không để session cũ vượt qua thay đổi trạng thái nhân sự hoặc thu hồi role.
6. **Kiểm soát tài nguyên:** giới hạn tiêu thụ session tại ứng dụng có chi phí cao, khi chính sách và nhu cầu hợp lý.
7. **Đáp ứng yêu cầu tổ chức:** bảo vệ ứng dụng nhạy cảm, terminal/kiosk và quản trị production.

### Mục tiêu trải nghiệm và tính liên tục

Việc ép mọi người **chỉ có một phiên trên toàn bộ hệ thống** có thể gây phiền toái và thậm chí rủi ro vận hành:

- User phải chuyển laptop/điện thoại liên tục, mỗi login đá phiên trước.
- Một hệ thống SSO có thể ngắt các ứng dụng đang chạy dù nghiệp vụ cần đa thiết bị.
- Các app không hỗ trợ session revoke ngay sẽ có kết quả không đồng nhất.
- Tài khoản dịch vụ dùng chung bởi nhiều replica có thể ngừng hoạt động nếu áp “max sessions = 1” máy móc.

**Cần lựa chọn chính sách theo rủi ro, kiểu principal, ứng dụng, session và môi trường**, không coi giới hạn một phiên là best practice chung cho tất cả trường hợp.

## 4. Những kiểu concurrent session policy phổ biến

| Kiểu policy | Ví dụ | Lợi ích | Điều cần cân nhắc |
| --- | --- | --- | --- |
| **Unlimited, monitored** | Cho phép nhiều phiên tiêu chuẩn, có alert bất thường. | Linh hoạt nhiều thiết bị. | Cần bảo vệ token và quản lý phiên tốt. |
| **Max N sessions per identity** | Tối đa 3 phiên web có thể dùng trong tenant B. | Giảm số phiên tồn tại. | Xử lý vượt ngưỡng và cách đếm session/token. |
| **One session per client/app** | Một phiên quản trị cho app ProductionConsole. | Chặt theo ứng dụng rủi ro. | RP session phải thực thi độc lập với IdP. |
| **One session per device** | Thiết bị chỉ giữ một phiên cho cùng identity/client. | Tránh duplicate session không cần thiết. | Nhiều browser profiles có thể tạo phiên khác nhau. |
| **Device-aware max N** | Cho laptop và phone, chặn unmanaged device. | Phân biệt thiết bị có trust. | Device identity phải xác thực, không tin header tự khai. |
| **Privilege-tier policy** | Standard 5, admin 1, break-glass theo runbook. | Dồn bảo vệ vào high risk. | Phải xác định session tier khi role thay đổi. |
| **Risk-adaptive policy** | Phân quyền session theo risk, IP/device, step-up. | Giảm ma sát cho User bình thường. | Rủi ro false positive và nguồn risk stale. |
| **Named/kiosk session policy** | Session ngắn, luôn logout khi đổi User. | Giảm lưu quyền trên máy chia sẻ. | Thiết bị phải chặn session reuse và lưu bí mật. |
| **PAM-mediated exclusivity** | Chỉ một operator session cho một resource nhạy cảm. | Audit và kiểm soát thao tác admin. | Không mặc nhiên chặn direct SSH/cloud session ngoài PAM. |

### Phạm vi đếm cần rõ ràng

Một quy tắc kiểu “maxSessions=2” là thiếu ngữ cảnh. Cần ghi rõ:

~~~yaml
policyId: FINANCE-CONCURRENT-SESSION-V4
subjectType: HUMAN
counterScope:
  identityNamespace: IAM
  tenant: tenant-b
  application: finance-portal
  privilegeTier: STANDARD
  sessionCategory: APP_INTERACTIVE
maxConcurrentUsableSessions: 2
onLimit: REJECT_NEW_SESSION
idleTimeoutMinutes: 30
absoluteTimeoutHours: 12
requiredDeviceTrust: MANAGED_FOR_SENSITIVE_ACTIONS
~~~

Đây là **schema mô phỏng**, không phải định dạng cấu hình chuẩn IdP hay SaaS. Nếu một hệ thống chỉ đếm cookie session ở một node, phải nói đúng phạm vi, không khẳng định nó đã thực thi cho toàn ứng dụng cluster.

### Vì sao “identity” nên dùng khóa ổn định?

Lan có thể có normal account và admin account, địa chỉ email thay đổi hoặc account tại nhiều issuer/tenant. Với chính sách **per person**, phải resolve về một **IAM identity ổn định**. Ngược lại, chính sách **per application account** có thể chủ ý đếm riêng từng account. Cần mô tả chính sách để tránh vừa **đếm thiếu** vừa **khóa nhầm User khác**.

## 5. IdP session, RP session và token: ai chịu trách nhiệm?

Một hệ thống SSO thường có ít nhất **ba nơi** ảnh hưởng đến concurrent sessions:

1. **Identity Provider (IdP):** duy trì phiên xác thực/SSO và cung cấp protocol login.
2. **Relying Party/Service Provider (RP/SP):** duy trì phiên ứng dụng, cookie hoặc session backend sau khi xác thực thành công.
3. **Resource Server/API:** xác minh access token và cưỡng chế quyền tại endpoint; có thể độc lập với cookie/IdP session.

~~~mermaid
flowchart LR
    U["User + device"] --> I["IdP SSO session registry"]
    I --> F["Finance RP session"]
    I --> C["CRM RP session"]
    F --> A["Finance API"]
    C --> B["CRM API"]
    T["Access / refresh token family"] -.-> A
    T -.-> B
    P["IAM lifecycle + policy"] -.-> I
    P -.-> F
    P -.-> C
    P -.-> A
    P -.-> B
~~~

### Ví dụ giới hạn ở IdP chưa đủ

IdP giới hạn User tối đa hai SSO sessions. User đã đăng nhập Finance RP, rồi IdP kết thúc một phiên SSO cũ. **Finance RP có thể vẫn giữ cookie còn hạn**, nếu nó không thực thi logout/back-channel hoặc không kiểm trạng thái phiên hiện hành. Vì vậy kết quả chính xác là **IdP session đã bị kết thúc**, không tự tuyên bố **mọi ứng dụng đã ngắt**.

### OAuth 2.0 và OIDC

- **OIDC** cung cấp cơ chế xác thực và thông tin về user/session tùy profile; ID token không mặc định là **session registry** duy nhất.
- **OAuth 2.0 access token** dùng để gọi Resource Server theo scope/audience/expiry; nó không đồng nghĩa một login session.
- **Refresh token** có thể cho phép client xin access token mới; revocation/rotation và token family semantics tùy Authorization Server.
- **RFC 7009** định nghĩa token revocation endpoint, nhưng hiệu quả với các loại token và tài nguyên phụ thuộc triển khai.
- **RFC 7662** mô tả token introspection giúp Resource Server lấy trạng thái token khi mô hình hỗ trợ; không bắt buộc mọi API phải introspect mọi JWT.
- Logout OIDC có các kiểu **RP-Initiated, Front-Channel, Back-Channel, Session Management**, nhưng **mức hỗ trợ và phạm vi ngắt phiên** khác nhau.

Không suy rằng `max concurrent OIDC sessions = 2` tự động có nghĩa toàn bộ access tokens ở tất cả API được thu hồi khi User mở session thứ ba.

### SAML 2.0

SAML SP thường lập **local application session** sau khi nhận assertion, có thể dùng `SessionIndex` cho cơ chế Single Logout tùy IdP/SP. **SAML SLO không đảm bảo thành công ở mọi SP**; các SP offline, direct sessions hoặc không hỗ trợ SLO cần xử lý riêng.

### Khi app không hỗ trợ global logout

Nếu một SaaS không có API liệt kê/revoke session hoặc back-channel logout tương thích, tổ chức phải công bố **giới hạn kiểm soát**, dựa vào TTL, giảm scope, disable account/role và monitoring/compensating controls phù hợp. Không ghi “global single-session policy enforced” nếu thực tế chỉ IdP thực hiện.

## 6. Cơ chế đếm và tạo session: phải chống đua tranh

Một giới hạn concurrent session có thể bị vượt qua nếu hai login xảy ra gần như cùng lúc:

~~~text
Limit N = 2
Current active sessions = 1

Login A reads count = 1 -> allowed
Login B reads count = 1 -> allowed
Both create new sessions

Final usable sessions = 3 -> policy violated
~~~

Đây là race **check-then-act**. Kiểm tra count rồi insert session thành hai thao tác riêng không atomic là **không đủ**.

### Nguyên tắc server-side

1. Xác thực và resolve đúng IAM identity/tenant/client/device trước khi đếm.
2. Xác định **counter key** phù hợp policy, không lấy từ giá trị tự khai của client.
3. Làm sạch hoặc bỏ qua session **đã thực sự hết hạn/thu hồi theo nguồn có thẩm quyền**, không dựa vào dấu “không thấy hoạt động”.
4. Dùng **transaction, lock theo key, optimistic concurrency/version hoặc atomic store operation** để reserve/create session.
5. Khi đã cấp session nhưng response thất bại, retry cần **idempotency** để tránh tạo trùng.
6. Khi phiên bị thay thế, thay đổi registry/epoch và **thông báo/kiểm tra tại các RP/Resource Server** phù hợp.
7. Đảm bảo các node cluster đọc/ghi nhất quán theo mức bảo đảm đã công bố.
8. Kiểm thử tình huống simultaneous logins, retry, failover và stale cache.

### Hạn chế của bộ đếm cục bộ

Nếu app có ba instances nhưng mỗi instance giữ session list trong RAM, giới hạn **N=2 ở từng instance** có thể thành sáu phiên thực tế. Sticky session/load balancer không tự sửa được vấn đề policy toàn cục. Cần **shared session registry** hoặc cơ chế cưỡng chế phân tán được thiết kế rõ.

## 7. Khi vượt giới hạn: Reject, Replace hay cho phép ngoại lệ?

| Chính sách | Hành vi | Trường hợp có thể phù hợp | Rủi ro |
| --- | --- | --- | --- |
| **Reject new** | Giữ các phiên cũ, từ chối tạo phiên mới. | Admin/high-risk session hoặc bảo vệ phiên hợp lệ khỏi bị đá. | Người dùng mất device có thể bị lockout nếu không có flow revoke/recovery. |
| **Replace oldest** | Kết thúc phiên có thời điểm tạo sớm nhất rồi nhận mới. | Trải nghiệm đa thiết bị tiêu chuẩn khi tổ chức chấp nhận. | Attacker đăng nhập mới có thể đẩy phiên hợp lệ ra ngoài. |
| **Replace least recently used** | Kết thúc phiên ít dùng gần đây. | Giảm tác động lên phiên hoạt động. | Timestamp có thể stale/được cập nhật bởi background traffic. |
| **Let user select** | Hiển thị phiên/thiết bị và yêu cầu chọn để đóng. | User có nhiều thiết bị và đủ khả năng xác minh. | Không tin lựa chọn từ client nếu thiếu authn/session binding. |
| **Step-up/reauth before replace** | Yêu cầu xác minh mạnh trước khi tạo phiên mới hoặc đẩy phiên cũ. | Ứng dụng nhạy cảm, nguy cơ takeover. | Cần luồng khả dụng khi mất device MFA. |
| **Policy exception có thời hạn** | Cho phép vượt N theo thẩm quyền và audit. | Support/recovery trường hợp đặc biệt. | Không được trở thành bypass vĩnh viễn. |

### Ví dụ thay thế phiên cũ

~~~text
Before:
  S1 Laptop       ACTIVE, created 08:00
  S2 Phone        ACTIVE, created 08:30
Policy:
  MAX = 2; onLimit = REPLACE_OLDEST

At 09:00:
  New device S3 requests login.
  Atomic transaction marks S1 REVOKED.
  Transaction commits S3 ACTIVE.

Required:
  Request using S1 is denied by app/PEP when session state is checked.
  Token/session artifacts from S1 are revoked or bounded appropriately.
~~~

**S1 đánh dấu REVOKED trong registry** là một phần công việc; nếu app hoặc Resource Server vẫn chấp nhận cookie/access token cũ, chính sách chưa được thực thi đầy đủ. Cần công bố **revocation latency** hoặc giới hạn của hệ thống.

### Không để phiên mới chưa tin cậy chiếm chỗ ngay

Một chính sách **replace-oldest** có thể tạo **denial-of-service** nếu attacker có credential và liên tục đăng nhập để đá phiên người thật. Với quyền nhạy cảm, cân nhắc step-up, device trust, anomaly detection, notification và rate limiting trước khi thay phiên. Nên ghi lại thiết bị/địa chỉ/timestamps đủ phục vụ điều tra, tránh lộ dữ liệu nhạy cảm.

## 8. Session lifecycle: idle timeout, absolute timeout và rolling expiration

Hạn phiên đồng thời chỉ có nghĩa khi định nghĩa **khi nào phiên hết hiệu lực**. Một session registry không dọn các phiên đã hết hạn sẽ khiến User bị từ chối đăng nhập dù không còn phiên dùng được; ngược lại, dọn quá sớm có thể đếm thiếu.

| Thuật ngữ | Ý nghĩa | Sai lầm phổ biến |
| --- | --- | --- |
| **Idle timeout** | Hết hạn sau khoảng không có activity được tính theo policy. | Background polling vô tình làm session không bao giờ idle. |
| **Absolute timeout** | Hạn tối đa tính từ khi tạo/authn hoặc thời điểm chính sách định. | Sliding TTL làm session tồn tại vô thời hạn. |
| **Sliding/rolling expiration** | Gia hạn idle/session TTL khi có hoạt động hợp lệ. | Gia hạn mà không kiểm absolute expiry/risk/JML. |
| **Authentication freshness** | Khoảng từ lần xác thực đủ mức gần nhất. | User có session nhưng không đủ reauthentication cho admin. |
| **Access token lifetime** | Thời điểm token hết hạn được API chấp nhận. | Coi token expiry là kết thúc mọi RP session. |
| **Refresh token lifetime** | Khoảng có thể xin token mới theo policy. | Cho refresh token sống sau Leaver/account disable. |
| **Privileged activation TTL** | Khoảng JIT/PAM role được phép dùng. | Kết thúc role nhưng admin session/credential còn quyền. |

### Ví dụ tính thời hạn

~~~text
session.createdAt       = 08:00
lastActivityAt          = 08:20
idleTimeout             = 30 minutes
absoluteTimeout         = 8 hours

idleExpiresAt           = 08:50
absoluteExpiresAt       = 16:00

At 08:55:
  session expired by idle, even though absolute expiry is 16:00.
~~~

Khi client tiếp tục thực hiện request, API phải kiểm **session state, idle/absolute expiry và authorization policy**. Không dựa hoàn toàn vào việc browser đóng tab hoặc cookie biến mất để coi server session đã hết hạn.

### Hoạt động nào được cập nhật idle?

Cần định nghĩa rõ: một request API do User chủ ý, heartbeat tự động, refresh token call hay WebSocket ping có được tính là activity không? Nếu mọi background ping được coi như thao tác, idle timeout có thể mất tác dụng. Ngược lại, nếu ứng dụng không ghi activity hợp lệ, User bị logout giữa khi đang làm việc. Thiết kế phụ thuộc rủi ro và UX, nhưng phải nhất quán và có kiểm thử.

## 9. Browser tabs, browser profiles và chia sẻ cookie

Nhiều hệ thống đếm phiên sai vì xem mỗi tab là một session, hoặc ngược lại cho rằng một device chỉ có một session.

### Các trường hợp thường gặp

| Hành vi | Kết quả có thể xảy ra | Nên đếm thế nào? |
| --- | --- | --- |
| Mở Finance Portal trên hai tab cùng browser profile. | Hai tab chia sẻ cùng cookie session. | Thường là **một** RP session nếu cùng session ID. |
| Mở ứng dụng bằng hai browser profiles riêng. | Mỗi profile có cookie jar độc lập. | Có thể tạo **hai** RP sessions. |
| Mở cửa sổ ẩn danh rồi đăng nhập thêm. | Cookie jar riêng với phiên thông thường. | Có thể là phiên thứ hai; phải xử lý theo policy. |
| SSO từ cùng device tới Finance và CRM. | Hai app tự tạo RP sessions khác nhau. | Đếm theo app hoặc theo policy cross-app đã định. |
| Đăng nhập lại sau cookie loss nhưng phiên server cũ chưa expire. | Tạo phiên mới trong khi phiên cũ vẫn tồn. | Phải có cleanup/revoke flow; không coi cookie bị xóa là server session đã hết. |
| Khôi phục tab hoặc browser sau khi crash. | Cookie session có thể vẫn hợp lệ. | Phụ thuộc server-side session và cookie lifetime, không chỉ UI. |
| Cùng laptop có hai account nhân sự. | Hai identities và contexts riêng. | Không gộp User A, User B theo device ID duy nhất. |

### Session cookie phải được bảo vệ

Với session cookie dùng cho web, nên xem xét:

- Cờ **Secure** để hạn chế truyền qua kết nối không được bảo vệ phù hợp.
- Cờ **HttpOnly** để giảm khả năng script đọc cookie; nó không tự chặn mọi hành vi XSS.
- **SameSite** phù hợp luồng ứng dụng và CSRF defense, không coi SameSite là toàn bộ bảo vệ CSRF.
- Giới hạn **Domain/Path** và scope cookie theo ứng dụng; tránh chia sẻ rộng không cần.
- **Session ID có độ ngẫu nhiên đủ mạnh**, không đoán được; lưu server-side theo cách an toàn.
- **Rotate session ID** sau xác thực, nâng mức đặc quyền và những chuyển ngữ cảnh nhạy cảm để giảm session fixation.
- Chống CSRF và XSS ở các điểm phù hợp; không hiển thị token/session ID trong URL, logs hoặc analytics.

**Không tạo quy tắc “max tabs = max sessions”** nếu mọi tab dùng chung một session handle. Khi sản phẩm muốn giới hạn số thiết bị, cần mô hình device-aware chính xác thay vì suy từ tab hoặc IP.

## 10. Token lifecycle, token family và giới hạn phiên

Một phiên có thể có nhiều **access tokens** theo audience và thời điểm; refresh-token rotation có thể tạo các token mới nối tiếp. Vì vậy policy “2 sessions” nên đếm **session handles hoặc login grants** phù hợp, không đếm mỗi access token được phát.

### Vòng đời token minh họa

~~~text
Login S1:
    IdP session sid-1
    RP app session rp-1
    Refresh token family F1
    Access token A1 exp 09:00
    Access token A2 exp 09:10 (refresh từ F1)

Login S2:
    IdP session sid-2
    RP app session rp-2
    Refresh token family F2

Policy max concurrent RP sessions = 2:
    S1 và S2 => 2 sessions
    A1 và A2 không mặc định làm thành 2 sessions riêng.
~~~

### Khi thay thế session S1

1. Đánh dấu **RP session S1** revoked hoặc tăng version/epoch phù hợp.
2. Vô hiệu **refresh token family F1** theo khả năng Authorization Server, để không tiếp tục phát token mới từ grant đó.
3. Đánh giá và xử lý **access tokens A1, A2**: introspection/revocation/short TTL/central policy lookup hoặc cơ chế khác nếu hệ thống hỗ trợ.
4. Thông báo logout tới những RP liên quan nếu IdP-level session bị kết thúc và có giao thức/khả năng tương thích.
5. Kiểm tra WebSocket, background job, local session và token ngoại vi còn được dùng không.
6. Ghi outcome theo từng nơi; không mặc định tất cả đã bị thu hồi khi một API trả thành công.

### Refresh token reuse và session hijack

Một Authorization Server có thể hỗ trợ **refresh token rotation** và phát hiện reuse của token cũ để giảm rủi ro token theft. Tín hiệu reuse có thể dẫn tới revoke token family hoặc tăng step-up theo policy. Tuy nhiên không đồng nhất **hai refresh requests đồng thời hợp lệ** (ví dụ nhiều tab, network retry) với một vụ theft đã xác nhận; thiết kế client nên tránh gửi refresh đồng thời không cần thiết và server phải có semantics rõ cho reuse/race.

### Token binding và proof-of-possession

Với những môi trường hỗ trợ token binding hoặc proof-of-possession, việc sao chép bearer token sang nơi khác có thể khó hơn. Nhưng **nếu chính device hoặc process được ràng buộc bị compromise**, attacker vẫn có thể dùng quyền của nó. Cần kiểm tra device posture, audience, scope và resource authorization riêng.

## 11. Session inventory và chức năng “Thiết bị/phiên đang đăng nhập”

Một hệ thống phục vụ người dùng có thể cung cấp **danh sách phiên còn được quản lý** để phát hiện thiết bị lạ và chủ động kết thúc.

### Trường nên hiển thị

| Trường | Mục đích |
| --- | --- |
| Loại ứng dụng/kênh | Finance web, mobile, CRM, admin console. |
| Thiết bị đã xác minh hoặc nhãn gợi ý | Nhận diện laptop/phone, không đánh đồng user-agent với device proof. |
| Thời điểm tạo và hoạt động gần nhất | Giúp người dùng nhận biết phiên cũ, với độ mới được chỉ rõ. |
| Khu vực mạng/tín hiệu đăng nhập | Phục vụ nhận diện bất thường, nhưng IP/location có thể sai. |
| Trạng thái | Active, expired, revoked, pending, unknown theo hệ thống. |
| Authentication tier | Standard hay privileged/step-up, không lộ bí mật. |
| Current session marker | Tránh vô ý đăng xuất chính phiên đang dùng nếu không có dự định. |
| Chức năng chấm dứt | Logout phiên cụ thể hoặc toàn bộ những phiên hệ thống thực sự quản lý được. |

### “Đăng xuất khỏi tất cả thiết bị” cần diễn đạt đúng

Nếu chỉ có quyền revoke **IdP sessions**, giao diện không nên hứa “đã đăng xuất mọi ứng dụng và mọi API token” khi RP sessions, PAT hoặc SAML SP chưa thực hiện logout. Mô tả phạm vi chính xác như **“đã kết thúc các phiên tại tài khoản trung tâm; một số phiên ứng dụng có thể tiếp tục tới khi hết hạn/được xử lý”** khi điều đó đúng với triển khai.

### Bảo vệ endpoint quản lý session

Session management API cũng là mục tiêu tấn công:

- Một User chỉ được liệt kê/revoke session của chính mình trừ khi có authority helpdesk/security được cấp rõ.
- Không tin sessionId do client đưa ra nếu chưa xác minh **ownership + tenant + current authn context**.
- Chống **IDOR/BOLA**: session ID của người khác không được truy cập hay xóa tùy ý.
- Các thao tác kết thúc toàn bộ phiên hoặc privileged session có thể yêu cầu **reauthentication/step-up**.
- Dùng CSRF protection phù hợp cho thao tác từ web; chú ý khi revoke chính phiên đang xác thực.
- Không trả refresh token, raw cookie, access token hoặc session secret trong API liệt kê.
- Ghi audit actor, targeted session family, scope, status và kết quả thực tế.

### Self-service recovery khi mất thiết bị

Một người mất laptop có thể đăng nhập từ thiết bị còn đáng tin để revoke session trên laptop mất. Nếu chính phương thức MFA duy nhất nằm trong laptop thất lạc, phải có **account recovery có proofing an toàn**. Đừng để quy tắc max N ngăn mọi đường tự khôi phục; nhưng cũng không cho bypass MFA tùy ý để “giải phóng slot”.

## 12. Cưỡng chế session đồng thời trong hệ thống phân tán

Ứng dụng chạy nhiều instance cần thống nhất **nơi lưu session state, thuật toán đếm và kết quả thu hồi**.

~~~mermaid
flowchart TD
    U["User login S3"] --> G["Auth gateway / app"]
    G --> I["Verify identity, lifecycle,<br/>device, client and policy"]
    I --> K["Determine counter scope key"]
    K --> T["Atomic reserve / session transaction"]
    T --> Q{"Max N reached?"}
    Q -->|No| C["Create ACTIVE session"]
    Q -->|Yes| P["Apply reject/replace policy"]
    P -->|Reject| D["DENY + recovery guidance"]
    P -->|Replace| E["Revoke chosen old session<br/>update epoch / token linkage"]
    E --> C
    C --> R["Commit session ID + TTL"]
    R --> A["Every app node/API checks<br/>session state or revocation contract"]
    A --> V["Audit and verify active sessions"]
~~~

### Những lựa chọn kho session

| Kiến trúc | Ưu điểm | Rủi ro và điều kiện |
| --- | --- | --- |
| **Central relational DB** | Transaction, unique constraints, optimistic lock. | Throughput/latency, multi-region behavior và expiry cleanup. |
| **Distributed key-value store** | Truy cập nhanh, TTL, atomic scripts/transactions tùy sản phẩm. | Replica lag, failover, tính nhất quán, key expiration race. |
| **Single-region authoritative session service** | Dễ xác định thứ tự và global counters trong một vùng. | Điểm lỗi/latency; cần kế hoạch dự phòng. |
| **Eventual-consistent multi-region registry** | Sẵn sàng và gần User. | Có thể vượt hạn N khi login đồng thời đa vùng. |
| **Local in-memory session registry** | Đơn giản cho ứng dụng một node. | Không đủ để cưỡng chế giới hạn toàn cluster nếu nhiều instances. |

Khi có nhiều vùng hoặc partition, cần quyết định rõ **ưu tiên strict concurrency limit hay availability**. Không thể quảng bá đồng thời “global exact max sessions” và “mọi vùng đều cho đăng nhập độc lập khi mất liên lạc” mà không có cơ chế phối hợp phù hợp.

### Counter key và dữ liệu nhạy cảm

~~~text
counterKey = (
    trustedIamIdentityId,
    tenantId,
    applicationId,
    sessionCategory,
    privilegeTier
)

Do NOT use:
    unverified email address,
    source IP alone,
    user-agent string,
    client-supplied device ID without proof
~~~

Một policy per-human có thể cần cộng session của nhiều accounts liên kết; policy per-account thì không. Phạm vi phải là **quyết định có chủ ý**, được kiểm thử với admin aliases, tenant membership và các identity migration.

## 13. Pseudocode tạo session atomically

Ví dụ dưới đây mô tả một **giao dịch logic**. Chi tiết transaction isolation, distributed locks, session key và TTL khác nhau theo công nghệ; không được copy nguyên xi như code production.

~~~text
startInteractiveSession(loginResult, client, device):
    authn = validateLoginResult(loginResult)
    identity = resolveTrustedIamIdentity(authn.issuer, authn.subject)
    if authn invalid or identity unresolved:
        return DENY

    lifecycle = loadCurrentLifecycle(identity)
    policy = resolveSessionPolicy(identity, client, device, authn)
    if not lifecycle.eligible or not policy.requiredGuardsPass:
        return DENY

    scopeKey = calculateTrustedCounterScope(identity, client, policy)
    requestKey = deriveIdempotencyKeyForLoginAttempt(authn, client)

    with SERIALIZABLE_TRANSACTION_OR_EQUIVALENT(scopeKey):
        if existing = lookupCommittedLoginAttempt(requestKey):
            return existing.safeSessionOutcome

        sessions = loadCurrentSessions(scopeKey)
        sessions = filterTrulyUsableSessions(sessions, now)

        if sessions.count >= policy.maxSessions:
            if policy.onLimit == REJECT_NEW:
                auditLimitReached(identity, scopeKey, sessions.count)
                return DENY_LIMIT_WITH_RECOVERY

            if policy.onLimit == REPLACE:
                victim = chooseSessionUnderApprovedPolicy(sessions, policy)
                if victim not safelyReplaceable:
                    return DENY
                markRevokedAtomically(victim)
                bumpSessionEpochOrRevokeLinkedGrant(victim)

        newSession = createUnpredictableSessionHandle(
            identity, client, device, policy,
            absoluteExpiry = now + policy.absoluteTimeout
        )
        persistSessionAndAttempt(newSession, requestKey)
        commit()

    asynchronouslyPropagateRevocationWithTrackedOutcome(victim)
    return issueSessionCookieOrHandle(newSession)
~~~

### Các điểm dễ sai

1. **Không phát session cookie/refresh token trước khi commit quyền tạo session**, trừ khi có cách xử lý bù và kiểm soát token chưa active.
2. Nếu hệ thống **reject new** thì không cần revoke phiên cũ; nhưng phải cung cấp recovery flow hợp lệ khi device mất.
3. Nếu hệ thống **replace old**, việc cập nhật registry có thể atomic nhưng **revoke ở RP khác/Resource Server** thường là bất đồng bộ; phải ghi trạng thái propagation và kiểm tra.
4. Nếu login response bị timeout nhưng transaction đã commit, retry phải nhận **cùng kết quả** hoặc sử dụng cơ chế ngăn duplicate sessions phù hợp.
5. Không để một logout callback trễ của S1 kết thúc nhầm session mới S3 do dùng cùng cache key không có generation/session ID.
6. Tính usable session phải rõ, đặc biệt các trạng thái **REVOKE_PENDING**, session token cũ và expiry.

### Kiểm tra phía API

~~~text
authorizeRequest(sessionHandle, resource, action):
    session = loadCurrentSessionState(sessionHandle)
    if session unresolved or session.state != ACTIVE:
        return DENY
    if session.isIdleExpired or session.isAbsoluteExpired:
        return DENY
    if session.epoch < currentIdentitySessionEpoch:
        return DENY

    subject = loadTrustedCurrentIdentityLifecycle(session.subject)
    if not subject.eligible:
        return DENY
    if not deviceAndRiskPolicySatisfied(session, resource):
        return DENY
    if not currentAuthorizationPolicyPermits(subject, action, resource):
        return DENY

    return PERMIT
~~~

Đây là mô hình **server-side session state**. Với API chỉ chấp nhận self-contained JWT không có session lookup, cách cưỡng chế ngay sẽ khác (TTL, token introspection, denylist, session/version claims hoặc hỗ trợ revocation tại API). Không giả vờ pseudocode trên tự áp cho mọi resource server.

## 14. Session security: fixation, hijacking, replay và chia sẻ tài khoản

Concurrent session policy có thể giảm một số rủi ro nhưng **không thay thế bảo vệ xác thực/token và kiểm tra quyền**.

### Session fixation

Kẻ tấn công cố khiến nạn nhân xác thực bằng một session ID mà attacker biết trước. Nếu ứng dụng không **rotate session ID sau đăng nhập hoặc privilege elevation**, attacker có thể sử dụng ID cố định. Việc chỉ đặt **maxSessions=1** không giải quyết nguyên nhân này.

### Session hijacking/cookie theft

Cookie hoặc token bị lấy qua malware, XSS, log rò rỉ, insecure storage hoặc thiết bị mất. Attacker có thể sử dụng **chính session hiện tại** của nạn nhân, nên số session trong registry **không tăng**. Một hệ thống báo “User có đúng một session” vẫn có thể đang bị chiếm.

### Token replay

Bearer token bị sao chép có thể được sử dụng lại trong khoảng hiệu lực nếu không có ràng buộc, revocation hoặc phát hiện bất thường. Hệ thống cần đánh giá **audience, scope, expiry, binding và context**; chỉ đếm login records không phát hiện mọi replay.

### Account sharing

Nhiều nhân viên dùng chung account có thể tạo sessions từ nhiều thiết bị. Nhưng có trường hợp một người hợp pháp có nhiều thiết bị hoặc VPN làm vị trí thay đổi. Dấu hiệu đồng thời từ nhiều nơi **không tự chứng minh account sharing**. Nên ưu tiên **named identities, MFA, credential hygiene và điều tra có bằng chứng**.

### Session race abuse

Attacker liên tục đăng nhập để:

- Đẩy phiên hợp lệ của nạn nhân (khi policy replace-oldest).
- Khiến User bị lockout bằng cách tạo đủ slot.
- Dùng nhiều request đồng thời để vượt giới hạn nếu check-then-act yếu.
- Tận dụng một phiên cũ chưa revoke khi phiên mới đã active.

Rate limiting, login risk assessment, step-up, session ID rotation, atomic creation, revocation và per-action authorization giúp giảm rủi ro.

### “Impossible travel” không phải bản án tự động

Hai session cùng User từ hai vùng địa lý khác nhau trong thời gian ngắn có thể gợi ý account compromise, nhưng VPN, mobile carrier routing, proxy hoặc độ sai của GeoIP cũng tạo cảnh báo giả. Dùng nó như **tín hiệu rủi ro kết hợp**, không làm căn cứ duy nhất thu hồi mọi tài khoản hoặc khóa sản xuất không có quy trình.

## 15. Session đồng thời trong Joiner

Với **Joiner**, tài khoản có thể được pre-provision và tham gia IdP/SSO từ trước ngày bắt đầu, nhưng quyền truy cập nghiệp vụ phải tuân **startAt, role, tenant và chính sách kích hoạt**.

### Những điểm cần kiểm soát

- User mới được proofing và account mapping đúng HR identity, không tái dùng nhầm email/account cũ.
- Các session được tạo trong luồng onboarding có thể chỉ được truy cập **portal chuẩn bị**, không mặc nhiên Finance/Production.
- Nếu thiết bị được enrollment sớm, device trust không tự cho phép business access trước startAt.
- Session registry phải mang **identityId và lifecycle sourceVersion**, không chỉ tên đăng nhập.
- Nếu Joiner bị hủy tuyển dụng hoặc dời startAt, **tất cả session và token có business access** phải được chặn theo chính sách.
- Mọi session mới sau ngày bắt đầu vẫn cần phân quyền least privilege và thiết bị đáp ứng policy.

### Ví dụ

~~~text
HR startAt = 2026-12-01 09:00 +07:00
Identity prepared = 2026-11-28
Device enrolled = 2026-11-29
Onboarding portal session = ACTIVE on 2026-11-29

Permitted:
  onboarding checklist per limited policy

Not permitted before startAt:
  finance.export
  production.admin
~~~

**Một session hợp lệ cho onboarding không đồng nghĩa hợp lệ cho mọi resource**. Resource Server phải đánh giá action và lifecycle theo từng tài nguyên, không chỉ dựa trên biến `loggedIn=true`.

### Hủy Joiner và job trễ

~~~text
v21 HR creates Joiner
v22 Portal session issued
v23 HR cancels onboarding
v24 Delayed token issuance job from v21 runs

Required:
  no new business session/token from stale v21 job;
  existing access restricted/revoked per current policy.
~~~

## 16. Session đồng thời trong Mover

**Mover** thay đổi role, department, manager hoặc tenant. Một User có thể có nhiều session **được phát với quyền cũ**, trong khi IAM đang cấp quyền cho vai trò mới.

### Ví dụ: Finance → Support

| Thành phần | Trước Mover | Sau Mover mong muốn | Rủi ro |
| --- | --- | --- | --- |
| IAM desired roles | FinanceExporter | SupportReader | Quyền cũ không cần nữa. |
| IdP Group | FinanceExporters | Đã rút Group | Token cũ vẫn chứa Group claim. |
| Finance RP session | Còn active trên laptop | Không được finance.export | App không cập nhật role/cookie. |
| Finance RP session | Còn active trên phone | Không được finance.export | Mỗi session có TTL khác. |
| Support RP session | Chưa có | Tạo mới đúng scope | Có thể cấp mới trước khi thu hồi quyền cũ. |
| PAM admin session | Đã mở khi còn role cũ | Không còn quyền role cũ nếu policy cấm | Privileged session có thể tồn tại ngoài Group. |

### Mover không nhất thiết phải logout mọi session

Nếu ứng dụng hỗ trợ **authorization lookup cập nhật theo mỗi request**, User có thể tiếp tục session mà chỉ mất những hành động không còn được phép. Nhưng nếu quyền bị **snapshot vào token/cookie/role cache**, cần **thu hồi, reauthenticate, refresh claims hoặc chặn action** theo khả năng hệ thống.

**Mục tiêu là xóa quyền không còn hợp lệ**, không nhất thiết buộc người dùng đăng nhập lại tất cả ứng dụng nếu kiểm soát runtime đủ tốt.

### Toxic combination và phiên admin

Chuyển từ role tạo nhà cung cấp sang role release payment có thể tạo **SoD conflict** nếu session cũ còn capability VendorEditor trong khi session mới có PaymentReleaser. Nên:

1. Tính desired permissions mới.
2. Thu hồi hoặc cô lập quyền cũ trước khi/đồng thời cấp quyền mới, nếu cần tránh overlap.
3. Kiểm tra **mọi RP sessions, tokens, PAM activations** có khả năng dùng quyền cũ.
4. Revalidate authorization tại API theo transaction/resource, không chỉ role assignment.
5. Theo dõi **verified revocation** và trạng thái PARTIAL_FAILURE.

## 17. Session đồng thời trong Leaver

**Leaver** là trường hợp cần phân biệt rõ **disable account**, **revoke credential** và **chấm dứt tất cả quyền còn hiệu lực**.

### Các bước phối hợp

1. HR/nguồn hợp đồng phát sự kiện Leaver với identityId, effectiveAt và sourceVersion có thẩm quyền.
2. IAM cập nhật eligibility; IdP chặn new sign-ins hoặc account access theo chính sách.
3. Revoke **IdP sessions**, refresh grants và các token/session mà nền tảng hỗ trợ.
4. Gửi logout/revocation tới các RP/SP đã tích hợp; đánh dấu kết quả từng hệ thống.
5. SCIM/connector/API thu hồi role, Group và local account rights.
6. PAM/PIM kết thúc privileged activation/session, credential checkout và quyền dùng secret theo policy.
7. Đánh giá PAT, SSH keys, VPN sessions, device certificates và service credentials độc lập có thể bị người rời đi dùng.
8. Kiểm tra effective authorization tại resource nhạy cảm, theo **revocation boundary** có thể đo.
9. Không để retry của job cũ tạo lại session hoặc grant sau Leaver.
10. Ghi tất cả đường chưa xác minh với owner, deadline và hành động containment.

### Sơ đồ xử lý

~~~mermaid
flowchart TD
    L["Authoritative Leaver<br/>identityId + effectiveAt"] --> I["Mark subject ineligible<br/>and block new sessions"]
    I --> S["Revoke IdP SSO sessions<br/>and refresh grants"]
    S --> R["Propagate RP/SP logout<br/>where supported"]
    R --> A["Revoke app-local sessions,<br/>PATs, permissions, PAM"]
    A --> T["Check tokens/claims/devices<br/>at Resource Servers"]
    T --> Q{"Required access paths<br/>no longer usable?"}
    Q -->|Yes| V["VERIFIED + audit"]
    Q -->|No or unknown| F["PARTIAL_FAILURE<br/>owner, containment and retry"]
~~~

### Không nhầm “account disabled” với “mọi session đã mất”

~~~text
17:00 HR Leaver effective
17:01 IdP denies new authentication
17:02 Refresh token family revoked
17:03 Finance RP cookie remains active
17:04 Finance API accepts old access JWT until 17:30

If policy requires immediate denial:
  Leaver revocation is not yet VERIFIED.
~~~

Trong hệ thống có **offline JWT validation** và không hỗ trợ cập nhật trạng thái tức thời, không nên hứa “thu hồi tức khắc ở mọi API” trừ khi có cơ chế cưỡng chế thực sự. Cần công bố và giảm độ trễ theo rủi ro.

### Ngăn session resurrect

Nếu worker SSO hoặc refresh job có hàng đợi, một event Joiner cũ đến sau Leaver có thể **cấp lại token hoặc đánh dấu session ACTIVE**. Mỗi tác vụ issuance cần kiểm tra **lifecycle và session revocation epoch mới nhất** trước commit, với xử lý đua tranh phù hợp.

## 18. Suspension, rehire, contractor và owner change

### Suspension

Tùy chính sách, tài khoản có thể được giữ để bảo toàn chứng cứ hoặc quay lại công việc; nhưng các session cho quyền nhạy cảm có thể phải bị **revoke hoặc hạn chế** trong thời gian đình chỉ. Không mặc định suspension = Leaver trong mọi domain, cũng không mặc định session tiếp tục được dùng.

### Rehire

Khi nhân viên được tuyển lại, identity liên kết lịch sử có thể được dùng theo quy trình proofing, nhưng **các session và token của hợp đồng cũ không tự hợp lệ trở lại**. Nên tạo session/credential mới theo role và policy hiện hành, không hạ guard chỉ vì User từng ACTIVE.

### Contractor/vendor

Nhà thầu có thể dùng nhiều thiết bị hoặc app sessions; giới hạn phải xét **sponsor, contract endAt, tenant/resource scope, partner IdP và session propagation**. Khi endAt có hiệu lực, các session liên quan không còn quyền dù partner IdP vẫn coi User là ACTIVE.

### Owner thay đổi

Khi một application/resource owner Mover/Leaver, người đó có thể mất authority quản lý sessions của người khác hoặc approve exception “thêm phiên”. Phải cập nhật **authority**, không chỉ đổi Group của User đang đăng nhập.

### Account recovery

Nếu User nghi session compromise, quy trình recovery có thể yêu cầu **revoke toàn bộ sessions trong phạm vi, reset/bind authenticator, đánh giá thiết bị và phát credentials mới**. Một session cũ không nên được phục hồi tự động chỉ vì User hoàn tất reset password; điều này phụ thuộc thiết kế nhưng cần được xác định rõ.

## 19. Concurrent session với privileged access, PAM/PIM và break-glass

Một privileged session có thể gây ảnh hưởng lớn hơn session người dùng tiêu chuẩn. Giới hạn concurrent session cần tính **quyền đang được kích hoạt, điểm truy cập, action/resource và khả năng audit**, không chỉ số lần đăng nhập.

### Ba loại thời gian cần xem

| Loại | Ví dụ | Giới hạn của một mình nó |
| --- | --- | --- |
| **PIM/PAM eligibility** | Lan được phép yêu cầu GlobalAdmin. | Không chứng minh quyền đang active; nhưng là khả năng cấp lại sau này. |
| **Privileged role activation** | GlobalAdmin active 15 phút theo JIT. | Session cloud/SSH đã mở có thể sống lâu hơn activation nếu target không chặn. |
| **Privileged session** | Một phiên PAM broker, RDP, SSH, console hoặc cloud API. | Không phải mọi direct sessions đều đi qua PAM. |

### Chính sách minh họa

~~~yaml
policyId: PROD-ADMIN-CONCURRENCY-V2
principalType: HUMAN
sessionCategory: PRIVILEGED_INTERACTIVE
scope: "production/tenant-b"
maxConcurrentSessions: 1
newLoginHandling: REJECT_NEW_UNLESS_EXISTING_REVOKED
authentication: "phishing-resistant MFA / step-up per policy"
activation: JIT_REQUIRED
absoluteTimeoutMinutes: 30
idleTimeoutMinutes: 10
independentApproval: RISK_DEPENDENT
sessionEvidence: REQUIRED_WHEN_SUPPORTED
~~~

Đây là ví dụ chính sách, không phải file cấu hình PAM thực tế. Với quyền quản trị cần **đồng thời nhiều người để phối hợp xử lý sự cố**, không nên ép chỉ một session trên toàn hệ thống nếu điều đó làm mất tính khả dụng hoặc ngăn kiểm soát bốn mắt. Có thể đếm **một session mỗi operator**, thêm SoD và giới hạn tài nguyên.

### Một người có nhiều admin accounts

Một cá nhân có account thường và account admin riêng; giới hạn “một privileged session mỗi người” có thể cần **gom theo IAM human identity** chứ không theo admin username. Đồng thời, mỗi phiên phải ghi **actual actor/account, resource, role, justification và incident/request reference**.

### Break-glass là policy khác

Emergency access có thể được kích hoạt khi SSO/PAM chính gặp lỗi. Không nên áp quy tắc **“IdP concurrency store không phản hồi → cho phép tất cả emergency sessions”**. Đường break-glass cần được chuẩn bị trước với custody, scope, TTL, alert và hậu kiểm; quy tắc đếm và giám sát có thể dùng **kênh độc lập**. Một số built-in emergency accounts không hỗ trợ revoke session như RP thông thường, nên phải công bố hạn chế.

### Step-up sau khi nâng quyền

Nếu User có session tiêu chuẩn trên nhiều thiết bị rồi kích hoạt quyền admin, nên xem **phạm vi session elevation**: quyền admin có được gắn cho **một session cụ thể** hay toàn account? Với quản trị nhạy cảm, ưu tiên session-bound elevation khi nền tảng hỗ trợ; không để mọi session cũ tự hưởng GlobalAdmin chỉ vì một phiên khác vừa được step-up.

## 20. Machine identity và workload: đồng thời không đồng nghĩa sai

Ứng dụng backend có thể chạy **10 replicas** cùng một workload identity để xử lý hàng đợi, mỗi replica nhận short-lived token và kết nối riêng. Việc yêu cầu “maxSessions=1” như User web có thể làm hỏng ứng dụng mà không đem lại kiểm soát an ninh thực chất.

### Phân biệt non-human credentials

| Dạng | Cách diễn giải concurrency | Kiểm soát chính |
| --- | --- | --- |
| **Service account dùng password/API key** | Nhiều kết nối có thể dùng cùng credential; không có browser login session. | Owner, secret rotation, scope, rate/abuse monitoring, expiry. |
| **Workload identity federation** | Mỗi instance xin token theo workload subject, trust và audience. | Trust conditions, workload attestation, token TTL/audience, namespace. |
| **mTLS client certificate** | Một certificate có thể lập nhiều TLS connections. | Private key custody, PKI revoke, endpoint policy và instance identity. |
| **Kubernetes service account** | Nhiều pods có thể chạy dưới một identity; token issuance phụ thuộc nền tảng. | Namespace, pod identity binding, RBAC và resource scope. |
| **Machine-to-machine OAuth client credentials** | Mỗi token request có thể tạo token mới cho client. | Client authentication, audience, scope, token lifetime, rate limits. |
| **Batch worker long-running job** | Một job giữ một hoặc nhiều connections trong thời gian dài. | Workload health, token refresh, no standing admin, monitoring. |

### Không nhầm số token với số workload instances

Một workload instance có thể lấy nhiều access tokens cho những audiences khác nhau. Ngược lại, nhiều instances có thể dùng cùng một service identity. Nếu cần hạn chế concurrency, nên định nghĩa mục tiêu:

- **Max active jobs** hay **max authenticated connections** của một service?
- **Max tokens issued per window** để hạn chế issuance abuse?
- **Max privileged operations in parallel** trên một resource nhạy cảm?
- **One unique identity per workload instance** khi cần attribution?

Đó là các chính sách **khác nhau**, không thể suy từ một bộ đếm login web.

### Khi workload bị compromise

Nếu một node có quyền xin token mới bị chiếm:

1. Xác định workload identity, token issuer, trust conditions, audience và affected host.
2. Hạn chế/revoke **trust hoặc issuance path** khi cần, không chỉ revoke các token đã biết.
3. Xử lý credentials bị lộ, active sessions và resource entitlements.
4. Tạo instance/credential mới trên môi trường đáng tin với quyền tối thiểu.
5. Kiểm tra token/connection cũ bị từ chối theo policy và workload hợp lệ vẫn hoạt động.

**Service owner nghỉ việc** không tự chứng minh máy/service cần bị dừng. Chuyển owner, thu hồi quyền cá nhân của người rời đi, rotate shared secrets họ biết và đánh giá service grants.

## 21. Thiết bị mất kiểm soát và các phiên đồng thời

Khi một laptop bị mất hoặc nghi compromise, User có thể còn sessions trên điện thoại/desktop khác. Policy cần **thu hồi đúng đường bị ảnh hưởng**, không khóa mù mọi thiết bị khi evidence chỉ giới hạn ở một device.

### Ví dụ

~~~text
Human identity: IAM:ID-LAN-2041
Session S1: Laptop dev-882, FINANCE, ACTIVE
Session S2: Phone dev-311, FINANCE, ACTIVE
Session S3: Laptop dev-882, CRM, ACTIVE

Incident:
    dev-882 reported STOLEN

Desired:
    Block device trust dev-882
    Revoke/contain S1 and S3 and related credentials
    Evaluate risk to human identity and token exposure
    Retain S2 only if device/account still trusted under policy
~~~

### Device binding cần được chứng minh

Các trường từ browser như user-agent, deviceName hoặc custom header **có thể bị giả mạo**. Để dùng deviceRef trong quyết định an ninh, cần **verified device registration, cryptographic binding, posture attestation hoặc nguồn tin cậy tương đương**.

### Khi không xác định session thuộc device nào

Đừng tùy tiện gắn session vào thiết bị dựa trên IP/UA. Tùy độ nhạy, có thể:

- Yêu cầu reauthentication/step-up cho các session có khả năng bị ảnh hưởng.
- Revoke toàn bộ session family/IdP sessions khi có bằng chứng credential bị lộ.
- Chặn những hành động nhạy cảm cho tới khi device trust được tái xác minh.
- Ghi rõ phần **UNKNOWN_DEVICE_BINDING** và quyết định containment.

### Remote wipe không thay session revocation

Thiết bị offline có thể chưa nhận lệnh xóa. Một cookie/token có thể đã bị sao chép trước khi wipe. Phải bảo vệ tại **IdP, app, token issuer, API và PKI/PAM** phù hợp, đồng thời theo dõi trạng thái wipe riêng.

## 22. Session policy trong RBAC, ABAC/PBAC và authorization runtime

**RBAC** có thể quy định vai trò nào có quyền tạo session quản trị. **ABAC/PBAC** bổ sung thuộc tính identity, device, session, risk, thời gian và resource. Các policy này không thay thế việc kiểm tra **effective permission** tại API.

### Pseudo-policy

~~~text
PERMIT finance.export KHI
    subject.lifecycleStatus == ACTIVE
    AND subject.hasCurrentEntitlement("FinanceExporter")
    AND subject.tenantId == resource.tenantId
    AND session.state == ACTIVE
    AND session.isWithinIdleAndAbsoluteWindow
    AND session.epoch >= currentIdentityEpoch
    AND session.authnFreshness meets resource.requiredFreshness
    AND device.trust meets resource.requiredDeviceTrust
    AND subject.currentSoDConstraintsSatisfied(resource)
    AND resource.currentPolicyAllows(action)

ELSE: NO_PERMIT
~~~

Mã giả này không phải cú pháp chuẩn của XACML hay một engine PBAC. **Kết quả Permit phải được PEP thực thi trước side effect**, không chỉ hiển thị trong giao diện hoặc bước login.

### Thời điểm role thay đổi

Một phiên có thể còn valid nhưng **role bị thu hồi**. Nếu hệ thống chỉ kiểm role lúc login, User tiếp tục dùng quyền cũ. Các lựa chọn kiến trúc:

1. Query current entitlement tại request hoặc cho những action nhạy cảm.
2. Sử dụng session/permission version để làm cũ những token/session mang claims không hợp lệ.
3. Phát token ngắn hạn và chặn refresh grant theo policy.
4. Revoke/replace app session khi Mover/Leaver, chủ động logout và kiểm chứng.

**Không có cách duy nhất phù hợp mọi ứng dụng**; cần đặt **revocation latency target** theo rủi ro và đo thực tế.

### PDP lỗi và fail-open

Nếu PIP không đọc được lifecycle hoặc session state, một API nhạy cảm không nên **mặc định Permit chỉ vì User từng login**. Cần xác định contract fail-safe và degraded-mode hợp lệ; với hoạt động low-risk/offline hoặc emergency, chính sách có thể khác nhưng **phải được thiết kế và phê duyệt trước**, không biến timeout thành cấp toàn quyền.

## 23. Logout và thu hồi xuyên ứng dụng: ma trận khả năng

| Cơ chế/đối tượng | Thông thường xử lý gì | Điều không được mặc nhiên suy ra |
| --- | --- | --- |
| **Local RP logout** | Hủy cookie/server session tại một ứng dụng. | Mọi IdP SSO session đã bị chấm dứt. |
| **IdP logout** | Kết thúc session tại Identity Provider. | Mọi RP đều có back-channel logout hoạt động. |
| **OIDC RP-Initiated Logout** | RP yêu cầu OP xử lý logout theo khả năng giao thức. | Mọi access token hoặc tất cả RP sessions được revoke. |
| **OIDC Front-Channel Logout** | Thông báo logout qua user agent. | Browser luôn tải đủ các RP và xử lý khi offline. |
| **OIDC Back-Channel Logout** | OP gửi logout token tới RP tương thích. | RP offline hoặc lỗi luôn xử lý thành công. |
| **OIDC Session Management** | Cơ chế theo dõi thay đổi trạng thái session ở OP. | Thay thế mọi cơ chế revocation ở API. |
| **SAML Single Logout** | Cố kết thúc các sessions có liên kết tại IdP/SP hỗ trợ. | Mọi SP/local account/API token cùng được ngắt. |
| **OAuth token revocation** | Yêu cầu revoke token/grant phù hợp tại Authorization Server. | Mọi self-contained JWT đang lưu tại Resource Server không còn hiệu lực tức thì. |
| **SCIM User active=false hoặc Group removal** | Cập nhật trạng thái account/membership ở target. | Cookie/session, PAT hoặc local role khác được tự thu hồi. |
| **PAM session termination** | Kết thúc brokered privileged session. | Mọi direct SSH/cloud console sessions cùng bị ngắt. |
| **Device trust revocation** | Chặn theo nguồn tin cậy thiết bị ở nơi áp policy. | Browser sessions từ device khác hoặc tokens không bind đã đổi. |

### Chuỗi logout không hoàn toàn tin cậy

~~~mermaid
sequenceDiagram
    actor U as User / Security Operator
    participant OP as IdP / OP
    participant RP1 as Finance RP
    participant RP2 as CRM RP
    participant AS as Authorization Server
    participant API as Finance API
    U->>OP: Revoke selected/all IdP sessions
    OP->>OP: Mark IdP session revoked
    OP-->>RP1: Back-channel logout if configured
    RP1-->>OP: Ack
    OP--xRP2: Logout delivery fails / RP unavailable
    OP->>AS: Revoke applicable token grants
    AS-->>OP: Status of supported revocation
    U->>API: Call with previously issued access token
    API->>API: Evaluate expiry, revocation and current policy
    API-->>U: Permit/Deny based on actual enforcement
~~~

**Điểm mấu chốt:** Hệ thống cần theo dõi **delivery status và target verification** thay vì đồng nhất “gửi logout event” với “mọi phiên đã thực sự kết thúc”.

### Session lifetime ở các lớp khác nhau

Một app session có absolute TTL 12 giờ, IdP session 8 giờ và access token 15 phút. Đăng xuất khỏi IdP ở giờ thứ 3 không nhất thiết chấm dứt app session ngay nếu RP không kiểm SSO state. Phải xem **chính sách từng lớp và cơ chế propagation**.

## 24. Sự cố phân tán và tính nhất quán của concurrency policy

### Những failure mode quan trọng

| Sự cố | Nguy cơ | Cách ứng xử/kiểm thử |
| --- | --- | --- |
| Session store timeout lúc login | Bỏ kiểm giới hạn N để cho phép session mới. | Không tự bypass strict limit; dùng degraded-mode đã định hoặc báo retry. |
| Session store timeout lúc API authorize | API tin session cũ dù đã Leaver. | Đánh giá hard guard/fail-safe theo resource risk. |
| Replica lag giữa hai vùng | Cả hai vùng thấy còn slot, tạo vượt N. | Authority/atomicity theo phạm vi policy, phát hiện và reconcile split-brain. |
| Network partition | Không xác định global active count. | Công bố trade-off availability/consistency, không hứa exact N nếu không thể. |
| Logout event bị mất | RP session vẫn active. | Retry/backoff, idempotency, dead-letter, target readback. |
| Duplicate logout callback | Xóa nhầm session mới dùng cùng key. | Session ID/generation, idempotent terminal state. |
| Clock skew | Expiry được xét lệch giữa nodes. | Time source, bounded skew, conservative policy cho quyền nhạy cảm. |
| Redis/database TTL cleanup trễ | Slot của session hết hạn vẫn bị chiếm. | Evaluate expiry trong transaction, không chỉ chờ background delete. |
| Browser refresh nhiều lần | Nhiều login/grant records trùng. | Per-attempt idempotency và session reuse theo contract. |
| Token refresh đồng thời từ nhiều tabs | Refresh reuse detection chặn User hợp lệ. | Client coordination và server semantics rõ; xử lý replay theo policy. |
| Concurrency limit đổi từ 5 xuống 2 | Có 4 phiên đang active. | Chính sách áp dụng ngay/gradual revoke được định nghĩa; thông báo và bảo vệ admin. |
| Resource Server không hỗ trợ revocation lookup | JWT cũ còn hạn. | TTL/compensating guard, xác minh window và ghi limitation. |
| Session registry đầy hoặc bị tấn công | Login/authorization chậm hoặc bypass. | Capacity planning, rate limits, bounded storage, fail-safe. |
| App offline khi User logout toàn bộ | Không nhận logout kịp. | Track missing ack, token/session TTL và reconcile sau phục hồi. |

### Cập nhật trạng thái cần đơn điệu khi thu hồi

Nếu S1 đã REVOKED, một event heartbeat cũ hoặc login callback trễ **không được chuyển S1 về ACTIVE** chỉ vì nó tới sau. Có thể dùng **session generation, monotonic revocation epoch, event ordering và terminal state** theo từng session.

~~~text
Session S1 stateVersion=42 REVOKED
Old event stateVersion=40 ACTIVE arrives late

Required:
    ignore/supersede old event
    do not resurrect S1
~~~

### Redistributed login after revocation

Một hệ thống có thể tạo session S3 mới sau khi S1 bị revoke và User đã hoàn tất xác thực. Cần kiểm tra **S3 có được cấp theo JML/policy hiện hành không**. Không có nghĩa mọi session mới sau một sự kiện revoke đều bị cấm; phân biệt **đăng nhập mới được phép** với **phục hồi session/token cũ bị thu hồi**.

## 25. Thay đổi policy giới hạn phiên trong khi User đang online

Một policy có thể giảm N từ 5 xuống 2 khi ứng dụng được phân loại rủi ro cao hơn. Những câu hỏi phải được quyết định:

1. **Áp dụng ngay hay ở lần đăng nhập tiếp theo?** Với sensitive resources có thể cần hành động ngay.
2. **Chọn phiên bị kết thúc theo rule nào?** Oldest, least recently active, device trust hoặc manual user selection.
3. **Có session privileged không thể bị thay theo rule phổ thông?** Phải tránh account lockout không kiểm soát và race ở PAM.
4. **Những token/session đã cấp có bị revoke không?** Nếu API không hỗ trợ, phải nêu thời gian tồn dư.
5. **User có được thông báo không?** Thông báo nên giúp nhận ra session lạ nhưng tránh tiết lộ thông tin nhạy cảm.
6. **Bảo đảm rollback policy không tự khôi phục session đã revoke?** N tăng trở lại không có nghĩa S1 được resurrect.
7. **Có ảnh hưởng tới service identities không?** Không dùng accidental per-human policy cho workload replicas.

### Reconcile khi N giảm

~~~text
Policy v4: max 5 sessions, usable = {S1,S2,S3,S4}
Policy v5: max 2 sessions, onChange = KEEP_MOST_RECENT_TRUSTED

Evaluation:
    pick at most 2 eligible sessions under policy v5
    mark others REVOKED with generation/version
    propagate logout/token handling
    verify actual usable count or report partial failure
~~~

Không được coi việc cập nhật một con số trong policy store là **đã giảm ngay số effective sessions**; phải thực hiện remediation và kiểm tra tại target.

## 26. Audit trail cho concurrent session

Quản trị phiên cần chứng minh được **ai mở phiên, ở đâu, dựa trên policy nào, phiên nào đã bị kết thúc và quyền còn dùng được tới khi nào**. Không chỉ log số lượng sessions.

### Những dữ liệu quan trọng

| Trường | Mục đích |
| --- | --- |
| **eventType và correlationId** | Nối login, session create, logout, revocation và API verification. |
| **identityId/accountRef** | Xác định Human/Workload thật, không nhầm email alias. |
| **sessionId hoặc session reference không bí mật** | Truy vết một phiên qua các hệ thống. |
| **clientId, tenantId, applicationId** | Biết phạm vi chính sách đếm. |
| **deviceRef và nguồn device trust** | Phân tích device bị mất/không đủ posture. |
| **policyId/version, maxN và counterScope** | Giải thích vì sao phiên mới được tạo/từ chối/thay thế. |
| **authentication method/assurance và authTime** | Phân biệt login thường với privileged step-up. |
| **createdAt, lastActivityAt, idle/absolute endAt** | Xác minh expiry và mức độ stale. |
| **stateVersion, sessionEpoch** | Điều tra race, event trễ và chặn session resurrect. |
| **replacedSessionRef, reasonCode** | Biết session nào bị revoke khi quá giới hạn. |
| **JML sourceVersion/effectiveAt** | Giải thích Mover/Leaver ảnh hưởng phiên. |
| **revocation propagation/result** | Biết IdP, RP, PAM, API đã thực thi tới đâu. |
| **verifiedAt và target evidence reference** | Chứng minh quyền thực tế đã được xử lý. |
| **actor/authority** | Phân biệt self logout, helpdesk revoke và Security operation. |

### Ví dụ session creation event

~~~json
{
  "eventType": "IAM_CONCURRENT_SESSION_CREATED",
  "correlationId": "login-flow-711",
  "subjectIdentityId": "IAM:ID-LAN-2041",
  "sessionRef": "finance:sess-8e4f",
  "counterScope": "tenant-b/finance-portal/standard",
  "clientId": "finance-portal",
  "deviceRef": "uem:tenant-b:dev-882",
  "policyVersion": "session-standard-v4",
  "maxConcurrentSessions": 2,
  "observedUsableCountBefore": 1,
  "decision": "CREATE_SESSION",
  "createdAt": "2026-12-01T08:15:00+07:00",
  "absoluteExpiresAt": "2026-12-01T20:15:00+07:00",
  "sessionEpoch": 12
}
~~~

### Ví dụ revoke event

~~~json
{
  "eventType": "IAM_SESSION_REVOKE_PROPAGATION",
  "correlationId": "security-revoke-405",
  "subjectIdentityId": "IAM:ID-LAN-2041",
  "targetSessionRef": "finance:sess-8e4f",
  "reason": "DEVICE_LOST",
  "registryState": "REVOKED",
  "registryVersion": 43,
  "targets": {
    "idpSession": "REVOKED",
    "financeRpSession": "REVOKED",
    "crmRpSession": "PENDING",
    "apiTokenEffective": "UNKNOWN"
  },
  "overallResult": "PARTIAL_FAILURE",
  "observedAt": "2026-12-01T09:20:00+07:00"
}
~~~

Hai ví dụ là **schema audit nội bộ để học**, không phải chuẩn bắt buộc của IdP/OIDC. **Không ghi raw session cookie, bearer access/refresh token, mật khẩu, private key, OTP hay MFA recovery secret** vào audit.

### Privacy và retention

Session telemetry có thể chứa IP, device fingerprint, vị trí suy đoán, thời gian làm việc và thói quen cá nhân. Chỉ thu thập trong phạm vi bảo mật/công việc cần thiết, phân quyền người xem, giới hạn thời gian lưu, bảo vệ log chống sửa và tuân thủ quy định của tổ chức.

## 27. Chỉ số vận hành và bảo đảm kiểm soát

| KPI/metric | Ý nghĩa | Cảnh báo diễn giải |
| --- | --- | --- |
| **Concurrent usable sessions per identity/app** | Số phiên được coi là usable trong phạm vi policy. | Phải nêu nguồn và độ phủ; không chỉ đếm cookie. |
| **Limit enforcement violations** | Bao nhiêu lần actual count vượt ngưỡng N. | Nếu registry thiếu RP sessions, có thể đếm thiếu. |
| **Atomic admission conflict rate** | Mức tranh chấp khi login cùng lúc. | Tỷ lệ tăng có thể do client retry hoặc tấn công. |
| **Session creation/replacement failure rate** | Trải nghiệm login và tính nhất quán. | Không tối ưu thành công bằng cách bypass guard. |
| **Logout propagation latency** | Từ revoke tới khi RP/SP xử lý. | Ack không đồng nghĩa API token đã mất quyền. |
| **Effective revocation latency** | Từ quyết định thu hồi tới khi action bị Deny. | Cần xác định resource và cách test. |
| **Stale sessions after Mover/Leaver** | Phiên có claims/role cũ còn dùng được. | Thước đo rủi ro quyền tồn dư. |
| **Orphan session count** | Session không liên kết owner/identity hợp lệ. | Identity mapping lỗi có thể khiến kết quả không chắc. |
| **Privileged session overlap time** | Khoảng hai hoặc nhiều admin sessions đồng thời trái policy. | Đếm cả direct sessions ngoài PAM. |
| **Unknown device session rate** | Phiên không có device binding đáng tin. | Browser UA không đủ để gắn device. |
| **Unverified session revocation** | Các session/token đã yêu cầu revoke nhưng chưa chứng minh. | Không tính như Verified Closed. |
| **Token refresh reuse anomalies** | Các refresh bất thường/replay nghi vấn. | Có thể do retry hoặc tabs cạnh tranh, cần điều tra. |
| **Policy/version drift across nodes** | Instance dùng session limits/guards khác nhau. | Có thể tạo bypass concurrency. |
| **Session store availability and consistency** | Khả năng phục vụ và strictness policy. | Network partition có trade-off cần công bố. |
| **User recovery success after lost device** | Người dùng lấy lại quyền hợp pháp an toàn. | Tránh làm recovery thành bypass authentication. |

### Phân biệt completion và verification

Giả sử Security yêu cầu logout 100 sessions. IdP báo đã revoke 100, RP A nhận 95 thông báo, RP B chỉ nhận 70; API không có bằng chứng về self-contained JWT. Khi đó **100% yêu cầu revoke đã được ghi nhận tại IdP** nhưng **không thể tuyên bố 100% quyền truy cập đã mất ở mọi RP/API**.

### Đặt SLO theo rủi ro

Một ứng dụng ít nhạy cảm có thể chấp nhận để token cũ hết hạn tự nhiên trong một khoảng được phê duyệt; tài nguyên quản trị production có thể yêu cầu cắt phiên ngay hoặc trong thời gian rất ngắn. Chỉ số **revocation latency** phải gắn **risk tier, expected boundary và actual verification**, không áp một con số toàn cầu không thực thi được.

## 28. Ma trận kiểm thử concurrent session

Bộ test nên dùng **danh tính, thiết bị và tài nguyên thử nghiệm có quyền**, kiểm cả hành vi được phép và các tình huống bị từ chối. Khi test session hijack/replay, dùng token mô phỏng trong môi trường kiểm soát; không lấy cookie của người khác.

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| CS-01 | User có một session hợp lệ, limit N=2, đăng nhập thêm. | Tạo session thứ hai, registry/PEP đúng count. |
| CS-02 | User có N phiên, policy REJECT_NEW. | Không tạo phiên mới; phiên cũ hợp lệ tiếp tục. |
| CS-03 | User có N phiên, policy REPLACE_OLDEST. | Phiên cũ được chọn đúng, revoke có version và phiên mới active. |
| CS-04 | Hai login đồng thời khi còn một slot. | Không vượt N nếu policy cam kết strict global limit. |
| CS-05 | Ba node app mỗi node có local session store. | Phát hiện không thể cưỡng chế global limit nếu không shared registry. |
| CS-06 | Network partition giữa hai regions. | Kết quả theo trade-off đã định; không silently bypass strict N. |
| CS-07 | Login commit rồi response timeout, client retry. | Không sinh duplicate session do idempotency. |
| CS-08 | Session hết idle nhưng chưa bị cleanup job xóa. | Không chiếm slot usable nếu policy coi đã expired. |
| CS-09 | Absolute TTL đã hết dù User liên tục gọi API. | Không gia hạn quá absolute expiry. |
| CS-10 | Background heartbeat liên tục. | Không vô hiệu idle policy trái định nghĩa user activity. |
| CS-11 | Một User mở 5 tabs cùng cookie. | Không đếm thành 5 phiên nếu cùng session ID. |
| CS-12 | Hai browser profiles trên cùng laptop. | Xử lý theo scope per-device/per-session đã định, không suy từ UA. |
| CS-13 | Hai Human identities khác nhau trên shared kiosk. | Session ownership tách biệt; logout User A không xóa nhầm User B. |
| CS-14 | User cố revoke session của User khác bằng sessionId. | API chặn IDOR/BOLA, không có side effect. |
| CS-15 | Session cookie bị thay trước authentication. | Server rotate ID và chống fixation. |
| CS-16 | Token bị replay trong cùng session handle. | Limit count không tự coi an toàn; kiểm binding/risk và policy. |
| CS-17 | User có admin account và normal account liên kết. | Policy per-human xử lý đúng identity correlation. |
| CS-18 | Role Standard nâng lên privileged. | Session elevation đúng scope và step-up; session khác không tự hưởng admin. |
| CS-19 | PAM broker đóng session nhưng direct SSH còn mở. | Báo residual access/partial failure, không VERIFIED giả. |
| CS-20 | IdP session bị logout nhưng RP cookie vẫn active. | Phát hiện gap, xử lý RP theo tích hợp và TTL. |
| CS-21 | OIDC back-channel logout thất bại do RP offline. | Retry/track unverified, không coi mọi RP đã đóng. |
| CS-22 | SAML SP không hỗ trợ Single Logout. | Nêu giới hạn, local session xử lý riêng. |
| CS-23 | Revoke refresh token nhưng JWT access token còn hạn. | Kiểm Resource Server; không tự nói token đã mất quyền. |
| CS-24 | Refresh token rotation gặp hai tab refresh đồng thời. | Hành vi rõ ràng, không làm lỗi hoặc flag compromise sai không kiểm soát. |
| CS-25 | Joiner có onboarding session trước startAt. | Không dùng business entitlement trước ngày kích hoạt. |
| CS-26 | Joiner bị hủy nhưng login job cũ retry. | Không tạo session business mới. |
| CS-27 | Mover từ Finance sang Support, Finance app session vẫn hoạt động. | Không còn finance.export theo policy hiện hành. |
| CS-28 | Mover tạo toxic privilege overlap giữa admin sessions. | Chặn/thu hồi quyền cũ hoặc áp DSoD/guard theo policy. |
| CS-29 | Leaver có nhiều IdP/RP/PAM sessions. | Revoke/chặn theo boundary, readback từng nơi. |
| CS-30 | Leaver đã block IdP nhưng JWT cũ được chấp nhận offline. | Test phát hiện residual access; không đánh dấu verified. |
| CS-31 | Suspension có exception theo policy. | Thực thi đúng trạng thái hạn chế, không mặc định giữ toàn quyền. |
| CS-32 | Rehire quay lại cùng identity nhưng session cũ từ lần trước. | Không tự hồi sinh session/refresh grants cũ. |
| CS-33 | Contractor endAt qua, partner IdP vẫn ACTIVE. | Resource session không tiếp tục quyền trái contract policy. |
| CS-34 | Laptop bị mất chỉ chứa S1/S3, phone giữ S2 tin cậy. | Revoke/contain sessions liên quan device, không xóa mù khi không cần. |
| CS-35 | Client gửi deviceId giả để được cộng quota. | Không chấp nhận device context chưa chứng thực. |
| CS-36 | Multi-replica workload xin token cho nhiều audiences. | Không áp session limit web của User máy móc. |
| CS-37 | Workload host bị compromise nhưng federation vẫn phát token. | Chặn trust/issuance path và token scope theo incident. |
| CS-38 | Policy max N giảm, một event cũ ghi ACTIVE cho S1 đã revoke. | Không resurrect session, có version guard. |
| CS-39 | Session registry/PIP lỗi khi gọi admin API. | Không tự Permit đặc quyền theo fail-safe policy. |
| CS-40 | Logout API trả success nhưng Resource Server vẫn commit action. | Test FAIL; hiệu quả ở PEP không đạt. |
| CS-41 | User logout selected session của chính mình. | Chỉ session đó bị revoke, không lộ dữ liệu sessions khác. |
| CS-42 | User yêu cầu logout all trong khi một RP không khả dụng. | Báo rõ pending/unverified và có retry/correlation. |
| CS-43 | Tenant A, B có cùng email nhưng identities khác nhau. | Không đếm/gỡ chéo tenant khi policy không yêu cầu. |
| CS-44 | Attacker tạo login mới để liên tục đá legitimate sessions. | Rate/step-up/risk control theo policy, có alert phù hợp. |
| CS-45 | Logout callback trễ của S1 trùng key với S3 mới. | Không xóa nhầm S3; dùng generation/session ID. |
| CS-46 | API session list trả raw refresh tokens. | Security test FAIL; chỉ trả metadata đủ dùng. |

### Given–When–Then

~~~gherkin
Feature: Concurrent session limits are consistent and lifecycle-aware

  Scenario: Simultaneous logins never bypass a strict limit
    Given User Lan has one active session under a maximum of two
    And two independent login attempts are authenticated at the same time
    When both attempts try to reserve the last session slot
    Then at most one new session becomes usable
    And the other attempt is rejected or handled by the configured replacement policy

  Scenario: A browser tab is not necessarily a new login session
    Given the browser uses one shared application session cookie
    When Lan opens the same application in three tabs
    Then the session registry does not count three distinct login sessions

  Scenario: A mover cannot use a stale role from another active session
    Given Lan had FinanceExporter before moving to Support
    And a Finance application session was created before the role change
    When Lan calls finance.export after the Mover effective time
    Then the Resource Server denies access according to current policy
    And stale grants or sessions are reconciled

  Scenario: Leaver prevents stale session creation jobs
    Given an old login flow was queued while Lan was ACTIVE
    And a trusted Leaver event became effective
    When the queued login job is retried
    Then no new usable session or refresh grant is created
    And the job is marked superseded by lifecycle state

  Scenario: Revoked IdP sessions do not imply all RP sessions are gone
    Given Finance and CRM have separate application sessions
    And one application does not receive the logout event
    When Security revokes the linked IdP session
    Then the workflow tracks partial logout propagation
    And no all-applications-verified claim is produced without evidence

  Scenario: A lost laptop loses device-bound sessions
    Given Lan has sessions from a laptop and a trusted phone
    And the laptop is confirmed lost
    When Security revokes that laptop's device trust
    Then relevant laptop sessions and credentials are contained
    And unrelated trusted sessions are handled according to risk policy

  Scenario: Repeated token issuance is not the same as distinct logins
    Given one authorized refresh token family belongs to one session
    When the client obtains two access tokens at different times
    Then the login session counter is not automatically incremented twice
~~~

### Tiêu chí test PASS sâu hơn response code

- HTTP **403/401** chỉ đạt yêu cầu nếu **không có unauthorized side effect**.
- Một session bị REVOKED ở registry chưa phải **effective denied** nếu app/token cũ còn được chấp nhận trái boundary.
- Kiểm thử active count cần **các node/regions cùng lúc**, không chỉ happy path tuần tự.
- Với admin sessions, cần kiểm tra **direct privileged access** ngoài broker và nguồn bằng chứng.
- Với logout all, phải xác định **độ phủ ứng dụng/Resource Server** và trạng thái pending.
- Sau Mover/Leaver, kiểm tra **quyền thực tế**, không chỉ số session hoặc tình trạng account trong IdP.

## 29. Tình huống thực hành

### Tình huống A — Ba tab nhưng chính sách chỉ cho hai phiên

**Bối cảnh:** Lan đã đăng nhập Finance Portal trên laptop. Lan mở hai tab khác trong cùng browser profile. Hệ thống kiểm soát concurrent session gửi cảnh báo “3 phiên, vượt ngưỡng 2” dù cả ba tab dùng chung một session cookie.

**Câu hỏi:** Kiểm tra sai ở đâu?

**Gợi ý:** Hệ thống đang đếm **tab/page view** thay vì **login session thực sự**. Phải xác định RP sessionId ổn định và semantics của browser profile; một tab mới không mặc nhiên là một session.

### Tình huống B — Đăng nhập thứ ba đẩy một phiên đang sử dụng

**Bối cảnh:** Policy max N=2, onLimit=REPLACE_OLDEST. Attacker biết mật khẩu của Minh, đăng nhập liên tục và khiến các phiên Minh đang sử dụng bị kết thúc.

**Câu hỏi:** Vì sao “replace oldest” có thể gây rủi ro?

**Gợi ý:** Nó có thể tạo **session denial-of-service** và che dấu takeover. Với ứng dụng nhạy cảm nên kết hợp MFA/step-up, device trust, login risk/rate limit, notifications và quy trình quản lý sessions phù hợp.

### Tình huống C — IdP chỉ còn hai phiên, Finance vẫn đăng nhập được

**Bối cảnh:** IdP kết thúc SSO session cũ khi User đạt giới hạn, nhưng Finance Portal vẫn giữ local cookie session và không hỗ trợ back-channel logout.

**Câu hỏi:** Có được báo “toàn bộ hệ thống đã đảm bảo tối đa hai phiên” không?

**Gợi ý:** Không. Giới hạn mới được chứng minh ở **IdP**, không tự áp tại Finance RP. Cần logout propagation, session lookup hoặc boundary của cookie/TTL, cùng cách báo cáo phạm vi đúng.

### Tình huống D — Hai lần login cùng lúc vượt N

**Bối cảnh:** User có N-1 sessions. Hai lần login đến hai nodes khác nhau; cả hai đọc count cũ rồi tạo phiên, khiến actual count=N+1.

**Câu hỏi:** Cơ chế nào thiếu?

**Gợi ý:** Thiếu **atomic reservation/transaction/conditional version** theo counter scope. Phải kiểm thử đồng thời và phân tán, không chỉ tuần tự trên một node.

### Tình huống E — Mover nhưng session chứa role cũ

**Bối cảnh:** Lan chuyển Finance sang Support. Group FinanceExporter đã bị rút khỏi IdP nhưng Finance API chấp nhận JWT còn hạn mang scope report.export.

**Câu hỏi:** Làm sao hạn chế cửa sổ quyền cũ?

**Gợi ý:** Tùy khả năng hệ thống, áp revocation/introspection, policy/entitlement lookup theo request, phiên bản quyền, token TTL ngắn, active session invalidation; đo **effective revocation latency** chứ không chỉ Group removal.

### Tình huống F — Leaver có PAT độc lập với SSO

**Bối cảnh:** Nhân viên nghỉ việc, IdP và SSO session đều bị thu hồi. Một PAT ứng dụng developer portal vẫn gọi API được.

**Câu hỏi:** Điều kiện nào chưa đạt?

**Gợi ý:** Offboarding chưa bao phủ **credentials ngoài SSO**. Cần inventory PAT, API keys, app-local roles và xác minh quyền ở Resource Server. “0 sessions tại IdP” không phải “0 effective access”.

### Tình huống G — Laptop mất nhưng điện thoại vẫn đáng tin

**Bối cảnh:** Minh có Finance sessions trên laptop và điện thoại. Laptop bị mất, nhưng chỉ laptop được đánh dấu compromised.

**Câu hỏi:** Có bắt buộc kết thúc mọi phiên của Minh?

**Gợi ý:** Tùy phạm vi chứng cứ/credential. Tối thiểu revoke/contain **device-linked sessions và tokens**, đánh giá account compromise và bảo vệ recovery; có thể giữ phiên điện thoại nếu chính sách và thiết bị còn tin cậy.

### Tình huống H — App mobile liên tục refresh token

**Bối cảnh:** Một mobile session nhận access tokens mới nhiều lần trong ngày. Hệ thống đếm mỗi token mới thành một “concurrent session” và từ chối User.

**Câu hỏi:** Tại sao sai?

**Gợi ý:** Access-token issuance không đồng nghĩa một login/session mới. Nên đếm theo **login grant, RP session hoặc token family** như policy định nghĩa, không phải mọi access token.

### Tình huống I — Quyền admin được kích hoạt nhưng phiên khác cũng có admin

**Bối cảnh:** Lan đăng nhập bình thường trên phone và laptop, rồi step-up để kích hoạt ProductionAdmin trên laptop. Session điện thoại vô tình được nâng quyền do hệ thống chỉ kiểm một cờ admin trên User profile.

**Câu hỏi:** Làm sao giới hạn?

**Gợi ý:** Khi hỗ trợ, gắn JIT/step-up vào **privileged session được xác minh**, resource scope và TTL, không chỉ user-wide global flag. Xác minh các phiên không tham gia không có thêm quyền admin.

### Tình huống J — PAM đóng nhưng SSH session còn mở

**Bối cảnh:** Security kết thúc PAM broker session, nhưng một SSH session trực tiếp vào production server vẫn còn.

**Câu hỏi:** Quyết định đã được thực thi đầy đủ chưa?

**Gợi ý:** Chưa nếu policy đòi ngắt mọi admin access. Phải kiểm các đường direct/broker, credential/session target và effective permissions, ghi PARTIAL_FAILURE cho đường chưa xử lý.

### Tình huống K — SSO logout khi CRM không kết nối

**Bối cảnh:** User yêu cầu “Log out everywhere”. OIDC logout tới CRM RP thất bại vì service offline.

**Câu hỏi:** Giao diện và audit nên báo gì?

**Gợi ý:** Xác nhận phần IdP và RP đã hoàn tất, đánh dấu CRM **pending/unverified** và theo dõi retry/TTL; không hứa mọi app đã logout khi không có evidence.

### Tình huống L — Workload nhiều replicas nhưng giới hạn một phiên

**Bối cảnh:** Một service có 20 replicas, mỗi replica dùng workload federation để lấy access token. Security áp một policy maxSessions=1 vốn thiết kế cho browser User.

**Câu hỏi:** Lỗi thiết kế?

**Gợi ý:** Không phân biệt **Human interactive sessions** với **workload token issuance/connections**. Nên giới hạn theo audience, trust, resource action, jobs/instances hoặc rate riêng, tránh làm hỏng service hợp lệ.

### Tình huống M — Token reuse do hai tab đồng thời

**Bối cảnh:** Hai tab cùng client gọi refresh token gần như cùng lúc. Server phát hiện token rotation reuse và revoke token family.

**Câu hỏi:** Có thể kết luận chắc chắn bị đánh cắp token không?

**Gợi ý:** Không. Có thể là race hợp lệ hoặc replay. Cần thiết kế client phối hợp refresh, server có semantics xử lý an toàn và đánh giá telemetry/binding trước khi gắn nhãn compromise.

### Tình huống N — Rehire làm sống lại phiên cũ

**Bối cảnh:** Nhân viên nghỉ tháng trước, tài khoản IdP được kích hoạt lại khi rehire. Một refresh token family cũ do lỗi hệ thống tiếp tục cấp token.

**Câu hỏi:** Vì sao nguy hiểm?

**Gợi ý:** Hồi sinh credentials thuộc **vòng đời employment cũ** mà không có approval, proofing và role mới. Cần session generation/epoch và quy trình cấp credentials mới.

### Tình huống O — Thiết bị bị giả mạo bằng header

**Bối cảnh:** App phân quota “hai session trên mỗi device” theo header deviceId do client tự gửi. Attacker thay deviceId qua mỗi lần login để tạo nhiều sessions.

**Câu hỏi:** Giải pháp?

**Gợi ý:** Không tin device identifier do client tự khai. Dùng verified device registration/binding khi policy cần per-device; vẫn cần atomic counter theo identity/client.

## 30. Các sai lầm triển khai thường gặp

1. **Đếm browser tabs là sessions.** Cùng session cookie có thể được dùng ở nhiều tab.
2. **Đếm mỗi access token issuance là login.** Một token family có thể phát nhiều token.
3. **Dùng IP hoặc user-agent làm stable device identity.** Dễ bị NAT/VPN/proxy hoặc spoofing làm sai.
4. **Dùng email để gộp sessions xuyên tenant.** Email có thể đổi/trùng; phải có identity correlation theo chính sách.
5. **Giới hạn N trong bộ nhớ từng node.** Cluster nhiều node có thể vượt giới hạn toàn cục.
6. **Check count rồi insert không atomic.** Simultaneous logins có thể tạo N+1 sessions.
7. **Không xử lý login retry/idempotency.** Timeout response có thể tạo session trùng.
8. **Cho phép fail-open khi session registry lỗi.** API đặc quyền có thể bỏ qua revocation.
9. **Thay session cũ mà không revoke token/session tại điểm dùng.** Registry sạch nhưng API vẫn Permit.
10. **Chỉ logout IdP, coi mọi RP/API đã logout.** Local sessions và self-contained tokens có thể còn hiệu lực.
11. **Chỉ gỡ SCIM Group, coi app session đã hết quyền.** SCIM không tự chuẩn hóa mọi session/logout.
12. **Cho sliding TTL kéo dài vô tận.** Không tôn trọng absolute timeout/reauthentication.
13. **Tính heartbeat nền là activity người dùng trong mọi trường hợp.** Idle timeout có thể mất ý nghĩa.
14. **Không quay session ID sau login hoặc privilege elevation.** Tăng rủi ro fixation.
15. **Hiển thị raw session token trong danh sách phiên.** Tạo nguy cơ chiếm phiên.
16. **Không kiểm ownership ở API revoke session.** Tạo IDOR/BOLA và session disruption.
17. **Áp giới hạn admin của User cho workload replicas.** Làm ngừng service hoặc tạo bypass không có lợi.
18. **Chỉ nhìn login mới, bỏ qua token replay trên chính session cũ.** Có thể không tăng số sessions nhưng đã bị hijack.
19. **Bỏ qua concurrent sessions khi Mover.** Quyền cũ nằm trong RP cookie hoặc JWT.
20. **Chỉ disable account khi Leaver.** PAT, PAM session, app-local cookie và refresh grants còn hoạt động.
21. **Cho rehire khôi phục session/token cũ.** Không gắn credential với vòng đời mới.
22. **Tự đẩy session cũ khi login từ thiết bị lạ.** Có thể tạo DoS cho User thật.
23. **Xóa sessions theo alias không đúng identity.** Khóa nhầm người hoặc bỏ sót admin account.
24. **Dùng logout callback trễ cập nhật state mới.** Có thể xóa nhầm S3 hoặc hồi sinh S1.
25. **Công bố “tất cả sessions đã thu hồi” từ một API 200/204.** Thiếu readback và effective verification.
26. **Không phân biệt trạng thái UNKNOWN với REVOKED.** Số liệu sạch giả.
27. **Không gắn policy version với audit.** Không giải thích được tại sao N=2 ở một thời điểm.
28. **Không thiết kế recovery khi mất MFA/device.** Max N biến thành lockout khó phục hồi an toàn.

## 31. Câu hỏi tự kiểm tra

**1. Concurrent session là gì?**

Là nhiều phiên truy cập hoặc xác thực còn hợp lệ đồng thời trong **một phạm vi được định nghĩa** (identity, application, tenant, session category...). Không phải cứ nhiều tab là nhiều phiên.

**2. Một IdP session có thể tạo bao nhiêu RP sessions?**

Có thể tạo nhiều sessions ở các ứng dụng khác nhau, tùy SSO flow và cách RP quản lý. Không có quy tắc một-một bắt buộc.

**3. Có nên đếm mọi access token mới là một session?**

Không mặc định. Một session/refresh token family có thể phát nhiều access tokens; phải đếm theo mô hình mà policy định nghĩa.

**4. Vì sao maxSessions=1 không tự ngăn session hijacking?**

Attacker có thể sử dụng **chính cookie/token của session đang tồn tại**, không làm tăng số session.

**5. Hai tab cùng cookie có phải hai concurrent sessions không?**

Thông thường không nếu chúng chia sẻ đúng cùng một server session ID. Nếu mỗi tab tạo token/phiên riêng theo ứng dụng, cần xem mô hình thực tế.

**6. Tại sao cần transaction/atomic reservation khi tạo phiên?**

Để tránh hai login cùng thấy còn slot rồi cùng tạo session và vượt giới hạn N.

**7. REJECT_NEW và REPLACE_OLDEST khác nhau thế nào?**

REJECT_NEW giữ phiên cũ và từ chối mới; REPLACE_OLDEST revoke phiên được chọn trước khi chấp nhận mới theo chính sách. Cần xét rủi ro DoS và token revocation.

**8. Idle timeout khác absolute timeout?**

Idle giới hạn thời gian không có hoạt động được tính; absolute là hạn tối đa độc lập với activity theo policy.

**9. Background heartbeat có luôn nên gia hạn idle session không?**

Không. Phải định nghĩa activity phù hợp để không vô hiệu idle timeout hoặc làm User bị logout bất hợp lý.

**10. Nếu IdP logout thành công, RP sessions có tự biến mất không?**

Không mặc định. RP cần logout propagation, kiểm trạng thái hoặc session TTL; không phải mọi RP/SAML SP hỗ trợ đầy đủ.

**11. SCIM active=false có đảm bảo mọi cookie/PAT tại ứng dụng không còn quyền?**

Không. Cần ứng dụng đích thực thi, thu hồi local sessions/credentials và kiểm tra quyền thực tế.

**12. Trong Mover, có nhất thiết logout mọi phiên không?**

Không nếu runtime authorization cập nhật và chặn đúng quyền cũ. Với token/role cache stale có thể cần reauthentication, session revocation hoặc quyền lookup phù hợp.

**13. Leaver có hai sessions và một PAT, IdP báo zero sessions có đủ chưa?**

Chưa. PAT và app-local tokens/sessions vẫn cần được kiểm kê và xử lý theo policy.

**14. Khi laptop bị mất, có nên luôn khóa tất cả thiết bị khác của User không?**

Không nhất thiết. Xử lý theo phạm vi chứng cứ; nếu credential/account bị lộ rộng có thể cần revoke all, nếu device-specific thì thu hồi đúng đường liên quan.

**15. Vì sao privileged session cần chính sách khác standard session?**

Ảnh hưởng lớn hơn, có nguy cơ SoD/production changes; cần step-up, JIT, scope, TTL, PAM monitoring và kiểm các đường truy cập trực tiếp.

**16. MaxSessions=1 có phù hợp với service chạy 20 replicas không?**

Không mặc định. Workload token/connection concurrency có ngữ nghĩa khác Human login sessions; cần hạn chế theo workload trust, scope, audience và mục tiêu vận hành.

**17. Một logout callback bị gửi trùng có được xóa session mới của User không?**

Không. Dùng session ID/generation và idempotent terminal state để callback cũ không tác động nhầm session mới.

**18. Session registry lỗi thì có được bỏ kiểm N cho admin API không?**

Không tự động. Cần fail-safe/degraded-mode đã được phê duyệt; timeout không phải bằng chứng cho phép admin action.

**19. Vì sao số sessions tại registry khác effective access?**

Vì RP cookie, JWT offline, direct PAM sessions, PAT và resource policies có thể còn cho phép action dù registry đã revoke.

**20. Một decision “Verified logout” cần chứng minh gì?**

Trong phạm vi xác minh đã định, những phiên/token/đường truy cập bắt buộc đã bị chặn tại điểm thực thi; các đường chưa kiểm phải ghi pending/unknown, không gộp thành Verified.

## 32. Checklist vận hành và thiết kế

Dùng checklist này khi chọn hoặc kiểm thử cơ chế concurrent session cho một ứng dụng IAM/SSO. Mỗi mục có thể đánh dấu đạt/chưa đạt/không áp dụng có lý do.

| Hạng mục | Câu hỏi xác minh |
| --- | --- |
| **Phạm vi quota** | Counter theo identity, account, tenant, app, device hay privilege tier? |
| **Định nghĩa session** | RP session, IdP session, PAM session hay token grant nào được tính? |
| **Limit và UX** | Max N bao nhiêu và vì sao, cách xử lý vượt ngưỡng nào? |
| **Concurrency atomicity** | Hai login đồng thời qua nhiều nodes/regions có vượt N không? |
| **Idempotency** | Retry sau timeout có sinh duplicate sessions không? |
| **Timeout policy** | Idle, absolute, authentication freshness có tách biệt không? |
| **Cookie/session security** | Secure/HttpOnly/SameSite, rotate ID, CSRF/XSS guard? |
| **Token handling** | Refresh token families, access token TTL, revocation/introspection/binding? |
| **SSO propagation** | IdP/RP/SAML/OIDC logout capability được kiểm chứng ở từng app? |
| **Authorization runtime** | API có kiểm JML, role, resource, tenant, session state khi cần? |
| **JML guard** | Joiner pre-start, Mover role removal, Leaver/revoke và rehire có đúng? |
| **PAM/privileged** | JIT, direct SSH/cloud sessions, SoD và session monitoring? |
| **Device trust** | Mất device có thể revoke/contain session theo identity được xác minh? |
| **Workload policy** | Service identities có thiết kế riêng, không áp quota browser sai? |
| **Recovery** | User mất device/MFA có đường self-service/helpdesk proofing an toàn? |
| **Audit và privacy** | Có session ref/actor/correlation/version không lộ bí mật và có retention? |
| **Revocation verification** | Chứng minh quyền đã bị Deny và ghi partial failures/latency? |
| **Incident resilience** | Store/PDP/IdP timeout và network partition có fail-safe contract rõ? |
| **Policy rollout** | Thay đổi N/role/tenant có migration, version và kiểm thử race? |

### Ví dụ tiêu chí nghiệm thu

~~~text
Policy: max 2 Finance interactive sessions per IAM identity in tenant B

ACCEPT nếu:
  1) Two simultaneous logins at N-1 never create 3 usable sessions.
  2) New session at N follows configured reject/replace behavior.
  3) RP session and IdP session scopes are named correctly.
  4) Mover removes effective finance.export from all old sessions.
  5) Leaver blocks new sessions and required API actions.
  6) Lost-device revoke is targeted and verified in affected RPs.
  7) Logout errors produce PENDING/PARTIAL_FAILURE, not VERIFIED.
  8) No sensitive session secret appears in audit or listing APIs.
  9) Workload access is assessed under a different approved policy.
~~~

**Hoàn thành STEP 4 của nội dung không đồng nghĩa đã kiểm thử một sản phẩm IAM cụ thể**. Các tiêu chí trên chỉ hướng dẫn thiết kế và kiểm chứng khi triển khai.

## Ghi nhớ

- **Concurrent session** nghĩa là **nhiều phiên còn khả năng sử dụng đồng thời** trong phạm vi chính sách rõ ràng; **browser tab, device, IdP session, RP session, access token và refresh token family là những thực thể khác nhau**.
- Cần xác định **counter scope, max N, reject/replace policy, idle/absolute timeout, authentication freshness và privilege tier**. Không áp “một phiên cho tất cả” máy móc cho Human Users và workloads.
- Trong ứng dụng nhiều nodes, **atomic admission, idempotency, session ID/generation, shared authoritative state và kiểm soát event stale** giúp tránh vượt giới hạn hoặc hồi sinh phiên đã revoke.
- **IdP logout không bảo đảm mọi RP/SP/API đã logout**; OIDC/SAML logout, SCIM, OAuth token revocation, PAM session termination có **phạm vi và giới hạn riêng**. Cần xem **session/token còn được Resource Server chấp nhận không**.
- **Joiner** không được mở quyền nghiệp vụ sớm; **Mover** phải xử lý role/claims cũ ở các phiên đang sống; **Leaver** phải chặn issuance mới và thu hồi các đường còn hiệu lực; **rehire, contractor và thiết bị mất** cần policy theo trạng thái/nguồn có thẩm quyền.
- **Privileged/JIT sessions** cần bảo vệ mạnh, SoD, scope và thời hạn; **machine/service identities** cần giới hạn theo workload, audience, credential/trust, không coi mọi access token hay kết nối là browser session.
- **Desired–observed–effective session access, kiểm thử đồng thời, readback, revocation latency, audit không chứa bí mật và báo cáo PARTIAL_FAILURE/UNKNOWN trung thực** là nền tảng giảm quyền truy cập tồn dư xuyên suốt vòng đời danh tính IAM.
