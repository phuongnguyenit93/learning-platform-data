# Interactive login đối với Non-human account: khi nào phải chặn và khi nào cần ngoại lệ?

**Interactive login** (*đăng nhập tương tác*) là quá trình một chủ thể tạo **phiên đăng nhập để tương tác trực tiếp với hệ điều hành, giao diện ứng dụng hoặc môi trường quản trị** — ví dụ đăng nhập desktop, RDP, SSH shell, trang SSO hay console bằng một account. Trong chủ đề **Non-human account**, câu hỏi quan trọng là: **tài khoản dành cho dịch vụ, workload hoặc tác vụ tự động có được sử dụng để mở phiên tương tác như tài khoản của người hay không?**

**Nguyên tắc mặc định:** **Non-human account (NHA/NHI)** phục vụ tác vụ máy–máy hoặc automation nên được **thiết kế để không đăng nhập tương tác bằng người**, ngoại trừ tình huống đã được đánh giá, phê duyệt và kiểm soát riêng. Việc người quản trị có thể đăng nhập qua một account dịch vụ không làm account đó trở thành danh tính người; ngược lại nó có thể tạo **shared access**, làm mất **attribution**, lộ credential và mở đường leo thang quyền. Tuy nhiên, một số **robot process automation (RPA)** hoặc ứng dụng legacy buộc phải thao tác GUI; một số đường **break-glass** dành cho khôi phục khẩn cấp lại cần phiên tương tác. Cần **phân loại đúng chủ thể và use case**, không áp một quy tắc kỹ thuật sai cho mọi loại account.

Bài học thuộc chương **Non-human account** trong module **Security — Identity and Access Management (IAM) — Identity Lifecycle**. Mục tiêu của module là quản lý danh tính theo **Joiner–Mover–Leaver (JML)**: xác minh, tạo tài khoản, cấp quyền, rà soát, thay đổi và thu hồi khi vai trò thay đổi. Chúng ta sẽ nối interactive login với **IdP/SSO, OAuth/OIDC, SCIM, RBAC/ABAC, PAM/JIT, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư**.

> **Ba điều không được đánh đồng:** **(1)** Tài khoản có thể xác thực bằng API không đồng nghĩa được phép mở desktop/browser session. **(2)** Một tiến trình tự động điều khiển GUI có thể tạo phiên giống interactive, nhưng chủ thể vẫn là automation, không phải một human identity. **(3)** Chặn interactive login không tự động thu hồi API keys, service logon rights, role grants hoặc token đã phát hành.

## 1. Interactive login chính xác là gì?

Interactive login được hiểu theo **ngữ nghĩa của từng nền tảng**, chứ không phải chỉ vì request xuất phát từ bàn phím hay sử dụng giao thức HTTP.

Một số ví dụ:
- **Windows console logon**: người sử dụng một account để mở desktop trực tiếp.
- **Remote Desktop Services (RDP)**: tạo phiên Windows từ xa; thường được phân loại RemoteInteractive.
- **Linux/Unix shell login** qua console hoặc SSH: chủ thể có shell/terminal để chạy lệnh.
- **SSO qua trình duyệt**: người nhập/xác nhận thông tin đăng nhập tại Identity Provider (IdP), nhận phiên ứng dụng.
- **Ứng dụng có UI**: account được sử dụng để thao tác trực tiếp trên giao diện sau khi xác thực.
- **RPA bot**: phần mềm tự điều khiển browser/desktop, đôi khi bắt buộc tạo một phiên hệ điều hành có đặc tính interactive.

Các cơ chế **không nhất thiết** là interactive login:
- Một service chạy dưới account qua hệ thống quản lý dịch vụ.
- Scheduled job chạy bằng batch/service logon rights.
- OAuth 2.0 **client credentials** gọi API máy–máy.
- Một Kubernetes Pod dùng ServiceAccount token để nói chuyện với API server.
- Workload sử dụng managed identity, certificate hoặc mTLS để gọi resource server.
- CI/CD pipeline dùng workload identity federation nhận short-lived token.

### 1.1. Phân biệt mục đích nghiệp vụ và loại logon kỹ thuật

Một phiên RDP được tạo bởi bot RPA có thể mang **logon type kỹ thuật giống đăng nhập người dùng**, nhưng mục đích là automation. Ngược lại, một nhân viên dùng tài khoản dịch vụ và gọi API bằng script không tạo desktop session, nhưng vẫn là **human misuse of machine credentials** nếu chính sách cấm.

Bởi vậy, kiểm soát hiệu quả phải xét cả:
1. **Account identity/type**: human, service, workload, robot, emergency.
2. **Authentication mechanism và session type**.
3. **Actor thực sự khởi tạo** (người hay job, đã được ủy quyền không).
4. **Mục đích/target/action** và phạm vi quyền.
5. **Risk, owner và policy exception**.
6. **Thời điểm và vòng đời danh tính**.

### 1.2. Một sơ đồ so sánh

~~~mermaid
flowchart TD
    I["Tác vụ cần quyền truy cập"] --> Q{"Có cần người/bot tương tác UI?"}
    Q -->|Không| N["Machine-to-machine auth: managed identity, mTLS, OAuth client credentials"]
    Q -->|Người| H["Named human identity -> SSO/MFA -> scoped role"]
    Q -->|Bot/RPA bắt buộc GUI| R["Dedicated robot identity + approved interactive exception"]
    Q -->|Khôi phục khi IdP/PAM lỗi| E["Pre-designed break-glass human access path"]
    N --> A["Resource-side RBAC/ABAC + audit"]
    H --> A
    R --> A
    E --> A
~~~

Sơ đồ là cách phân loại, **không áp một giao thức duy nhất cho tất cả ứng dụng**. RPA vẫn nên ưu tiên API/platform-native automation nếu khả thi.

## 2. Vì sao non-human account thường bị cấm interactive login?

Non-human account thường có một hoặc nhiều đặc điểm:
- Được cấp quyền liên tục để chạy dịch vụ.
- Có credential lưu trong secret manager/configuration hoặc được platform tự cấp.
- Không gắn trực tiếp với một nhân sự duy nhất.
- Được nhiều job/instance sử dụng nếu thiết kế chưa tách bạch.
- Có quyền vượt một người dùng thông thường, ví dụ đọc dữ liệu hàng loạt hoặc sửa cấu hình.
- Không tham gia quy trình passwordless/MFA của người theo cách tương đương.

Nếu ai đó dùng account này để mở shell/RDP/SSO session, những rủi ro xuất hiện:

| Rủi ro | Cơ chế | Tác động |
| --- | --- | --- |
| **Mất attribution** | Nhiều người đăng nhập dưới cùng `svc-billing`. | Log không phân biệt ai đã thao tác. |
| **Credential exposure** | Mật khẩu/secret được tiết lộ để người đăng nhập. | Secret có thể bị copy rồi sử dụng ngoài workload. |
| **Privilege escalation** | Service principal quyền DB/cloud cao được dùng bằng shell. | Thao tác admin ngoài nhiệm vụ của service. |
| **Lateral movement** | Account có quyền đến nhiều máy hoặc tài nguyên. | Kẻ tấn công di chuyển sang hệ thống khác. |
| **Bypass human controls** | Account không chịu MFA/conditional access như nhân viên. | Không có step-up, device posture, SoD cần thiết. |
| **Orphaned access** | Người quản lý account đã Mover/Leaver. | Vẫn có người biết password hoặc PAT. |
| **Persistence** | Tạo session/token/direct grant khó phát hiện. | Quyền còn sau khi job hoặc incident kết thúc. |
| **Incident complexity** | Không thể disable account vì dịch vụ sản xuất đang dùng. | Khó cô lập attacker mà không gián đoạn. |

**Cấm interactive login là một control giảm bề mặt tấn công**, không phải một lời bảo đảm toàn bộ account an toàn: quyền network logon, service rights, API authentication và credentials vẫn cần kiểm soát riêng.

## 3. Identity, account, credential và session: bốn đối tượng khác nhau

Ví dụ hệ thống `billing-etl` có:

~~~text
Logical machine identity: billing-etl-prod
Owner team: finance-data-platform
OS account (nếu có): svc-billing-etl
Cloud principal: app-billing-etl-042
Database user: billing_writer
Credential: projected token / private-key JWT / secret
Entitlement: SELECT view-vn, INSERT summary-vn
Session: DB connection hoặc API token session
~~~

**Identity** trả lời “workload nào”, **account/principal** là đại diện tại hệ thống cụ thể, **credential** chứng minh claim, **session** là trạng thái truy cập đã thiết lập. Việc chặn **console login** của `svc-billing-etl` không đồng nghĩa:
- Cloud principal bị gỡ role.
- OAuth client secret đã bị revoke.
- Database sessions đang mở bị ngắt.
- Target không còn chấp nhận PAT/API key.
- Service principal không còn quyền impersonation.

### 3.1. Owner con người không phải account dùng để chạy service

Owner `person-2048` có trách nhiệm phê duyệt và vận hành, nhưng service nên dùng `billing-etl-prod` để gọi API. Khi owner rời công ty, xử lý **human access và credential exposure** mà **không xóa nhầm workload đang chạy**.

### 3.2. Account có cùng tên nhưng bản chất khác nhau

Một số ứng dụng gọi mọi đối tượng là “User”, kể cả bot. Một cloud có “service principal”; Kubernetes có “ServiceAccount”; Windows có domain service account/gMSA; DB có technical user. **Không suy login type chỉ từ label**. Phải xem cách account được xác thực, thực thi, quyền và policy thực tế.

## 4. Phân loại account và lựa chọn interactive login

| Loại identity/account | Mục đích | Interactive login mặc định | Giải pháp ưu tiên |
| --- | --- | --- | --- |
| **Human named account** | Nhân viên đăng nhập để làm việc. | Được phép theo role/policy. | IdP/SSO, phishing-resistant MFA khi phù hợp, RBAC/ABAC. |
| **Service account** | Chạy service/daemon/batch. | **Deny**, trừ exception được quản trị. | Service/batch logon, managed identity, noninteractive tokens. |
| **Workload identity** | Pod, function, CI/CD, job. | **Không phải human login**. | Attestation/federation, mTLS, short-lived tokens. |
| **OAuth app/service principal** | API machine-to-machine. | Không dùng browser user-login thay client authentication. | Client credentials/federation được hỗ trợ. |
| **RPA/unattended bot account** | Tự động thao tác UI. | Có thể **cần phiên tương tác** theo thiết kế. | Bot account riêng, vault/PAM, scoped session, owner và log. |
| **Attended RPA** | Bot hỗ trợ người đang thao tác UI. | Thường nên dùng named user context theo nền tảng/policy. | Delegated user context, controls theo người. |
| **Shared emergency/break-glass account** | Khôi phục khi đường chính lỗi. | Có thể cần login tương tác. | Đường khẩn riêng, custody/attribution/post-use review. |
| **Device identity** | Thiết bị xác thực với control plane. | Không đồng nghĩa human desktop login. | Hardware-backed key/certificate và enrollment. |

**Deny by default không phải deny mọi access.** Một service cần được phép **chạy đúng tác vụ** bằng credential thích hợp; điều bị cấm là mở phiên tương tác không có business basis.

## 5. Các hình thức đăng nhập không tương tác phổ biến

### 5.1. Service execution

Hệ điều hành/service manager khởi chạy daemon bằng account đã cấu hình. Chủ thể không đăng nhập qua desktop; vẫn có **process token/identity**, quyền file/network và các credential cần thiết.

### 5.2. Batch và scheduled task

Job chạy theo lịch hoặc được orchestrator khởi động, có thể sử dụng service/batch logon semantics tùy hệ điều hành. **Tắt quyền interactive không nên phá nhầm khả năng chạy job**; phải kiểm tra quyền nào phục vụ tiến trình và quyền nào không cần.

### 5.3. OAuth 2.0 Client Credentials

Workload lấy access token cho **chính client**, không thay mặt một người đang tương tác.

~~~mermaid
sequenceDiagram
    autonumber
    participant W as Workload / API client
    participant AS as Authorization server
    participant RS as Resource server
    W->>AS: Token request + client authentication
    AS->>AS: Validate client/trust, requested scope, policy
    AS-->>W: Short-lived access token
    W->>RS: API request + access token
    RS->>RS: Validate issuer, audience, exp, scope + resource policy
    RS-->>W: Permit/Deny
~~~

**OAuth client credentials** không yêu cầu human browser login hoặc user consent trong mỗi request. Tùy server, client có thể xác thực bằng client secret, mTLS hoặc private-key JWT. **Client ID là identifier, không phải secret.**

### 5.4. Workload identity federation

Một cloud/kubernetes/CI platform phát workload assertion, hệ thống đích xác minh **issuer, subject, audience, environment và trust binding**, rồi cấp credential ngắn hạn scoped. Phương án này thường tránh static key có tuổi thọ dài.

### 5.5. mTLS, certificate và managed identity

Workload có thể chứng minh identity bằng key/certificate hoặc cơ chế managed identity. **Xác thực thành công không thay thế authorization**: API vẫn phải xét role, resource, action, tenant và lifecycle status.

## 6. Windows: interactive, remote interactive, batch và service logon

Windows có khái niệm **logon type** trong security events, giúp phân biệt **phương thức logon kỹ thuật**.

| Logon type thường gặp | Ý nghĩa | Liên hệ non-human account |
| --- | --- | --- |
| **2 — Interactive** | Local console/desktop logon. | Service account thường không nên xuất hiện. |
| **10 — RemoteInteractive** | Remote Desktop/Terminal Services logon. | RDP bằng service account là tín hiệu cần điều tra. |
| **4 — Batch** | Batch processing/scheduled task. | Có thể hợp lệ nếu account được dùng cho job. |
| **5 — Service** | Service Control Manager khởi động service. | Có thể hợp lệ với dedicated service identity. |
| **3 — Network** | Xác thực qua network. | Có thể hợp lệ hoặc lạm dụng; phải xét target/protocol/action. |
| **7 — Unlock** | Mở khóa session đã có. | Cần đối chiếu nguồn session. |
| **11 — CachedInteractive** | Interactive logon từ cached credentials trong tình huống tương ứng. | Không nên bỏ sót khi đánh giá workstation access. |

Các loại/ID này phục vụ **phân tích Windows security events**, không phải định nghĩa chung của mọi Unix/cloud/SSO. Windows còn các biến thể khác; việc xác định hành vi cần đối chiếu **event ID, account SID, source host, workstation, logon process và target**.

### 6.1. Kiểm soát bằng logon rights

Với service account có thể cần thiết lập:
- **Deny log on locally**: chặn console interactive trên máy áp dụng policy.
- **Deny log on through Remote Desktop Services**: chặn RemoteInteractive.
- **Log on as a service** hoặc **Log on as a batch job**: chỉ cấp khi workload tương ứng cần.
- Đánh giá các quyền network, delegation và local administrator riêng.

**Không gỡ bừa mọi logon rights** khỏi một account đang vận hành service; điều đó có thể làm dịch vụ dừng. Tương tự, Deny interactive không chặn mọi network logon, Kerberos delegation hay service-to-service authentication.

### 6.2. GPO áp tới phạm vi nào?

Một deny policy chỉ có tác dụng trên **những host/OU hoặc phạm vi đã nhận policy**. Nếu service account có interactive rights trên workstation khác, người dùng có thể vẫn đăng nhập ở đó. Cần:
1. Inventory các host được phép chạy service.
2. Xác định account/groups có policy.
3. Đánh giá GPO precedence, exception và hiệu lực thực tế.
4. Kiểm thử trên máy đích để không chặn service/batch job hợp lệ.
5. Theo dõi Windows logon events để phát hiện account dịch vụ đăng nhập kiểu 2/10.

### 6.3. Group Managed Service Account (gMSA)

Với Windows/Active Directory, **gMSA** là một lựa chọn phù hợp cho nhiều dịch vụ vì hệ thống quản lý credential theo cơ chế nền tảng và hạn chế cách dùng account so với user/password tự quản. Dù vậy vẫn phải kiểm soát:
- Những host được phép sử dụng gMSA.
- Service/logon rights và local privileges.
- SPN/delegation theo yêu cầu thực.
- Quyền target/resource và audit.
- Owner, inventory và decommission.

**gMSA không có nghĩa mọi loại đăng nhập/ủy quyền tự an toàn**, cũng không thay permission review.

### 6.4. Tình huống thường gặp

~~~text
Expected:
  account: svc-report-export
  host: app-server-02
  logonType: Service (5)

Unexpected:
  account: svc-report-export
  host: admin-workstation-17
  logonType: RemoteInteractive (10)

Điều tra:
  ai dùng credential?
  host có được phép?
  có thay đổi role/secret?
  có credential leak hoặc lateral movement?
~~~

Không tự kết luận mọi event 10 là tấn công; một RPA/legacy exception có thể hợp lệ, nhưng phải có **approved scope, actor attribution và expiration**.

## 7. Linux/Unix: shell, SSH, sudo và system services

Linux service identity có thể là OS user chuyên chạy daemon, với **shell không cho interactive login** (ví dụ cấu hình `/usr/sbin/nologin` trên hệ thống phù hợp). Tuy nhiên đây chỉ là **một lớp control**, không phải bảo đảm mọi API, SSH/key path, sudo hoặc service privilege đều bị chặn.

### 7.1. Phân biệt shell login và tiến trình dịch vụ

| Đường truy cập | Điều cần kiểm tra |
| --- | --- |
| **Console/SSH shell** | Login shell, sshd config, PAM, authorized keys, access restrictions. |
| **systemd/daemon** | `User=`, filesystem permissions, capabilities, sandboxing, network grants. |
| **Scheduled cron/batch** | Owner, user context, task restrictions, credential location. |
| **sudo/su** | Ai được chuyển thành service user/root và trên host nào. |
| **SSH forced command/subsystem** | Thao tác nào được phép dù không có shell thông thường. |
| **API/DB auth** | Tokens, keys và application authorization, không phụ thuộc shell. |

### 7.2. Ví dụ nguyên tắc cấu hình

~~~text
OS service user: svc-ingest
Human SSH login as svc-ingest: denied by policy
Daemon process as svc-ingest: allowed on approved host
Filesystem scope: only /srv/ingest and required secrets
Network scope: only intended upstream/downstream services
sudo to root: not granted
Credential rotation and audit: configured
~~~

Đây là **mô tả thiết kế**, không phải lệnh cấu hình triển khai. Một control shell riêng lẻ có thể không chặn mọi đường **remote command, authorized key, API hoặc direct privilege**; phải test đúng giao thức.

### 7.3. Không dùng shared root password thay workflow

Nếu nhân viên cần debug một service, nên đăng nhập bằng **named human account** và dùng cơ chế elevation/PAM với audit. Không chia mật khẩu `svc-ingest` hoặc root để nhân viên SSH trực tiếp. Nếu ứng dụng legacy thực sự buộc login bằng technical account, xử lý như **exception** với thời hạn, người chịu trách nhiệm và kiểm soát.

## 8. Kubernetes và cloud: không gán human login semantics sai

### 8.1. Kubernetes ServiceAccount

Kubernetes ServiceAccount dùng để gắn danh tính cho Pod và tương tác với Kubernetes API hoặc federation. Nó **không phải một người dùng có password để đăng nhập dashboard**, dù có thể bị lạm dụng thông qua API token.

Rủi ro liên quan:
- Token bị đọc từ Pod hoặc metadata/trust path.
- RBAC cho ServiceAccount quá rộng.
- Người dùng được `exec` vào Pod và sử dụng credential của workload.
- Tạo token qua quyền tạo TokenRequest/ServiceAccount impersonation không kiểm soát.
- Mapped cloud role rộng hơn mục đích service.

**Chặn interactive login của một account Linux không bảo vệ được Kubernetes service-account token** nếu Pod/token bị truy cập trái phép. Cần cluster RBAC, admission controls, token audience/binding, trust policy, runtime hardening.

### 8.2. Cloud service principals, managed identities và human users

Nhiều cloud phân biệt:
- **Human/workforce identity** phục vụ console/browser login.
- **Application/service principal** phục vụ API hoặc delegated integrations.
- **Managed/workload identity** được nền tảng xác thực và phát credentials.

Không phải mỗi cloud service principal đều có khái niệm “interactive login” giống OS user. Thay vì tìm một checkbox chung, kiểm tra:
1. Principal có bị expose credential ra người dùng không?
2. Role assignments và trust policies có hợp lệ?
3. Có đường portal/console login qua linked human account hoặc service user không?
4. Token có đúng issuer/audience/scope và expiration?
5. Có quyền impersonate, create key hoặc assign roles không?
6. Có dấu vết con người dùng service credential ngoài runtime hợp lệ không?

### 8.3. CI/CD pipeline không nên dùng shared console account

Pipeline nên dùng workload federation/short-lived scoped identity khi provider hỗ trợ. Một named human login vào cloud portal rồi copy token admin vào pipeline có thể tạo:
- Phụ thuộc người và MFA session của họ.
- Khó thu hồi khi Leaver.
- Grant quá rộng cho job.
- Credential lưu trong runner/artifact.
- Thiếu SoD giữa code author, approver và deployer.

## 9. IdP, SSO và OAuth/OIDC: phân biệt giao thức phù hợp

Một tổ chức có thể dùng cùng IdP để quản trị cả người và ứng dụng, nhưng **authentication flow** có ý nghĩa khác nhau.

| Trường hợp | Flow/context thường gặp | Điều cần lưu ý |
| --- | --- | --- |
| Nhân viên đăng nhập web app | OIDC Authorization Code hoặc SAML SSO. | Human session, MFA, Conditional Access và user permissions. |
| Backend gọi API tự động | OAuth 2.0 Client Credentials / workload federation. | App-only context, issuer, audience, scope, client authentication. |
| Service gọi thay người dùng | Delegated/on-behalf-of flow nếu nền tảng hỗ trợ. | Kiểm tra cả caller workload và end-user context theo policy. |
| RPA GUI không có API | Robot session theo chính sách nền tảng. | Có thể cần browser/desktop auth; không bypass MFA mặc định. |
| Recovery account khi IdP lỗi | Break-glass path riêng. | Cần độc lập khỏi dependency bị lỗi, có audit/custody. |

### 9.1. Interactive OIDC và app-only token không đồng nhất

Trong OIDC Authorization Code, **end user** thường xác thực tại IdP qua browser; relying party nhận ID token/session. Trong OAuth Client Credentials, client xác thực **như ứng dụng** để nhận access token.

Không dùng **ID token** thay access token để gọi API. Cũng không dùng `client_id` như một bí mật. Resource server cần kiểm issuer, audience, expiration, token binding khi áp dụng, scopes/roles và authorization theo đối tượng tài nguyên.

### 9.2. Tránh dựng automation bằng user password grant

Những flow trực tiếp dùng username/password (thường gọi `password grant`/ROPC) làm tăng rủi ro lộ human credentials và thường không phù hợp với MFA hiện đại. Đừng chọn nó chỉ để “headless hóa” một tài khoản người hoặc service user. Ưu tiên **protocol machine-to-machine phù hợp** hoặc cơ chế RPA được quản trị.

### 9.3. Device authorization flow không phải mẹo bỏ MFA cho bot

OAuth Device Authorization Grant được thiết kế cho thiết bị/client có khả năng input hạn chế, với **một người sử dụng thực hiện authorization ở thiết bị khác**. Dùng flow này để robot âm thầm giả lập người dùng hoặc xin token mà không có human authority là sai mục đích và có thể tạo nguy cơ phishing. Workload nên dùng flow/app-only identity phù hợp.

### 9.4. SSO portal có bot tile không chứng minh account an toàn

Một portal có thể cho khởi chạy ứng dụng theo assignment. Việc bot/account nhìn thấy tile hay đăng nhập thành công qua browser **không chứng minh quyền đang đúng business need**, và chưa chắc session được chặn khi account dịch vụ thay đổi. Cần kiểm **target permissions và session lifecycle**.

## 10. RPA: khi bot bắt buộc thao tác giao diện

**Robotic Process Automation (RPA)** có hai hình thức thường gặp:
- **Attended automation**: bot hỗ trợ người đang làm việc, thường chạy theo human session.
- **Unattended automation**: bot tự vận hành trong môi trường được chỉ định, có thể tạo một desktop/browser session và dùng robot account.

Không phải mọi RPA đều cần một shared service account có interactive login. Nếu hệ thống cung cấp **API ổn định, webhook, scheduled job hoặc machine-to-machine integration**, các đường đó thường dễ phân quyền và audit hơn.

### 10.1. Khi không có API

Một ứng dụng legacy chỉ có GUI có thể cần unattended robot account. Thay vì cho `svc-admin` truy cập mọi thứ, thiết kế:
- **Dedicated robot identity** cho use case, environment và app.
- Service owner/business sponsor và technical owner rõ.
- **Interactive exception** được phê duyệt riêng, có review định kỳ.
- Robot host/VDI/broker **được phép duy nhất**.
- Credential do vault hoặc RPA credential manager bảo vệ.
- Chỉ cấp **role/action trong UI cần thiết**.
- Không cho người tự dùng robot account ngoài workflow.
- Có session/activity logs, job ID, queue ID và incident correlation.
- Timeout, concurrent session limits và session termination.
- Cơ chế MFA/authentication tương thích đã được đánh giá thay vì tắt MFA toàn cục.
- Kế hoạch thay thế bằng API/tích hợp chuẩn khi ứng dụng nâng cấp.

### 10.2. Phân biệt người phê duyệt với robot thực thi

Nếu RPA bot tạo thanh toán và cũng có thể duyệt thanh toán, SoD có thể bị phá dù không có người ngồi trước UI. Phê duyệt giao dịch cần actor độc lập khi policy yêu cầu. Một technical account được chia sẻ cho nhiều workflows là không đủ attribution.

### 10.3. Cách giữ attribution

~~~text
Robot identity: rpa-invoice-processor-prod
Job ID: run-2026-1042
Business task: invoice-approval-assist
Human sponsor: finance-operations
Target: legacy-erp
Allowed host: rpa-runner-vn-02
Credential source: managed vault
Session: brokered/recorded as supported
Transaction maker/checker: independent human identity
~~~

Target có thể chỉ thấy robot account. Hệ thống RPA/IGA phải nối **job ID, robot identity, human approver và target transaction ID** để truy nguyên, không tạo giả một human login event.

### 10.4. RPA account là ngoại lệ có điều kiện, không phải cách làm mặc định

Nếu robot account cần password dài hạn do app legacy, phải định nghĩa **rotation, retrieval, expiry/review, offboarding, session controls và compromised-credential response**. Càng ít dùng interactive login thì bề mặt rủi ro càng nhỏ.

## 11. Legacy service account: xử lý ngoại lệ interactive login

Ứng dụng cũ đôi khi:
- Buộc một Windows user đăng nhập desktop trước khi process chạy.
- Cần desktop session để in/export báo cáo.
- Không hỗ trợ OAuth app-only hoặc managed identity.
- Dùng technical user để chạy tác vụ quản trị bằng UI.
- Có script vận hành dựa trên shell của service user.

Đây là **design constraint** cần quản trị, không phải lý do bỏ hết kiểm soát.

### 11.1. Các bước đánh giá ngoại lệ

1. **Xác minh hạn chế sản phẩm**: thực sự không có API/service execution tương đương?
2. **Xác định tác vụ**: action/resource và mức privilege nhỏ nhất?
3. **Tách account**: có thể tạo robot/maintenance account riêng, không dùng account chạy service chính?
4. **Ràng buộc host/network**: chỉ máy/jump host được phép.
5. **MFA/credential controls**: đánh giá cách xác thực hợp lệ mà automation sử dụng được.
6. **Actor attribution**: ai/phần mềm nào mở phiên, trong ticket nào?
7. **SoD/approval**: có hành động nhạy cảm cần reviewer độc lập?
8. **Time limit**: JIT/PAM session hoặc thời hạn exception.
9. **Monitoring/audit**: log hệ điều hành, app transaction và privileged commands.
10. **Retirement plan**: ai chịu trách nhiệm thay thế legacy mechanism?

### 11.2. Đừng mở interactive cho account service có quyền toàn domain

Nếu không thể tránh GUI, cần **tách chức năng/credential**: một robot account hẹp cho UI khác với account dịch vụ chạy backend. Tránh account vừa có khả năng RDP, vừa có local administrator/domain-wide rights, vừa giữ database credentials mà nhiều người biết.

### 11.3. Exception có hạn và review

Một exception nên có `exceptionId`, business reason, owner, allowed account/host/action, start/end/review date, approvers, compensating controls, target tests và remediation roadmap. **Không biến exception thành quyền vô thời hạn** vì ticket từng được approved một lần.

## 12. Break-glass khác tài khoản dịch vụ dùng để login

**Break-glass** là đường truy cập khẩn cấp, thường cho **người vận hành được ủy quyền** khi IdP/SSO/PAM hoặc control plane gặp sự cố. Đây là **một use case khác** với service account chạy batch.

Một break-glass account có thể cần hỗ trợ **interactive console/portal login**. Tuy nhiên nó phải:
- Được chuẩn bị và kiểm thử trước outage.
- Có owner, custody và những người được phép truy xuất.
- Có authentication mechanism phù hợp failure mode.
- Có alert/session logging hoặc evidence dự phòng.
- Chỉ dùng trong điều kiện khẩn cấp được chính sách cho phép.
- Hạn chế scope/time khi khả thi; có post-use review.
- Rotate/reseal credential sau sử dụng khi policy yêu cầu.
- Không để đường recovery phụ thuộc hoàn toàn vào IdP đang bị lỗi.

### 12.1. Không lấy service account làm break-glass tùy tiện

Một account `svc-database` có password đã chia sẻ cho nhiều job không nên trở thành “emergency admin login” không kiểm soát. Điều đó trộn lẫn **availability dependency, attribution và quyền**. Dùng một recovery path riêng, giới hạn và quản trị phù hợp.

### 12.2. Hạn cuối chưa phải đã mất quyền

Nếu emergency session hết hạn trên ticket nhưng RDP/SSH hoặc OAuth token vẫn còn usable, **actual privileged access có thể tồn dư**. Cần revoke/rotate/session termination và target readback; không coi `EXPIRED` là `VERIFIED_CLOSED`.

## 13. PAM/JIT: debug dịch vụ mà không chia sẻ password

Một mô hình vận hành an toàn hơn:

~~~mermaid
sequenceDiagram
    autonumber
    actor O as Named operator
    participant IDP as IdP/MFA
    participant PAM as PAM/JIT
    participant POL as IAM policy
    participant T as Target host/application
    participant AUD as Audit
    O->>IDP: Authenticate as individual
    IDP-->>O: Authenticated session
    O->>PAM: Request scoped maintenance, ticket, duration
    PAM->>POL: Eligibility, SoD, owner approval
    POL-->>PAM: Permit within policy
    PAM->>T: Broker target access; no shared password disclosure if supported
    T-->>PAM: Scoped privileged session
    PAM-->>AUD: Person, request, target, session ID
    O->>T: Perform approved maintenance
    PAM->>T: Close/revoke when ending or expired
    PAM-->>AUD: Revocation + verification
~~~

### 13.1. Named operator trước, privilege sau

Người bảo trì **đăng nhập bằng personal identity**, không dùng account `svc-app` như danh tính của chính mình. PAM có thể broker/proxy đến target bằng privileged credential hoặc cấp JIT entitlement, tùy sản phẩm. Điều quan trọng là **định danh người thật và kiểm soát phạm vi**.

### 13.2. Không đồng nhất PAM recording với prevention

Session recording có thể hỗ trợ audit, nhưng nếu PAM vẫn cho operator dùng account service toàn quyền ngoài phạm vi hoặc không terminate session lúc hết hạn, nó chưa thực thi least privilege. Cần **command/resource restrictions, approval, expiry và readback**.

### 13.3. Tách quyền sửa job và quyền sửa IAM policy

Người có thể tạo/rotate credential của service cũng có thể tự tạo đường login. Các thao tác sửa policy, reset password, bật interactive login, cấp RDP rights hoặc thêm admin group membership cần **privileged change governance** và phê duyệt độc lập khi rủi ro yêu cầu.

## 14. MFA và conditional access cho non-human account

### 14.1. Vì sao không thể ép MFA người lên mỗi machine request?

Một daemon chạy 24/7 không thể bấm push notification hoặc dùng FIDO2 như một người mỗi phút. Workload cần **machine authentication** phù hợp:
- mTLS/key possession.
- Short-lived workload tokens.
- Trusted issuer + audience/subject binding.
- Managed identity/federation.
- Hardware-backed key hoặc platform attestation khi cần.
- Vault/PAM và credential rotation.

**Không có interactive MFA không đồng nghĩa bỏ xác thực.** Security của workload được chứng minh bằng trust và credential control phù hợp, không bằng cách tắt kiểm tra chữ ký/scope.

### 14.2. Khi người điều hành dùng account kỹ thuật

Người xin quyền quản trị máy phải qua **human MFA/step-up** theo risk. Với robot GUI exception, cần giải pháp xác thực được nền tảng hỗ trợ và policy phê duyệt; không đặt “MFA excluded” cho toàn bộ nhóm service accounts chỉ vì một legacy bot không xử lý được push MFA.

### 14.3. Conditional access có phạm vi áp dụng khác nhau

IdP có thể hỗ trợ chính sách riêng cho **users**, **workload identities/service principals** hoặc **sign-in risk**, tùy sản phẩm và license/configuration. Không giả định một rule “Block interactive login for service accounts” áp được **mọi IdP và mọi app**.

Kiểm tra riêng:
- Human browser/console sign-in.
- Service principal sign-in.
- OAuth client credentials.
- Legacy/basic auth protocol.
- Direct application/local login bypassing IdP.
- RPA/automation exception.

### 14.4. Không cấu hình blanket exceptions

Một ngoại lệ MFA/conditional access quá rộng có thể khiến attacker dùng password service user qua browser từ bất kỳ thiết bị nào. Nếu exception phải tồn tại, giới hạn **account, app, protocol, trusted execution location, resource, duration và monitoring** theo khả năng hệ thống.

## 15. SCIM và trạng thái account: active không đồng nghĩa interactive

**SCIM 2.0** chuẩn hóa provisioning phổ biến qua User/Group và khả năng extension theo provider, nhưng **không định nghĩa thuộc tính User chuẩn phổ quát tên `interactiveLoginAllowed`** để chặn login tương tác trên mọi hệ thống.

Một tài khoản được biểu diễn là `User` trong SCIM có thể phục vụ:
- Human user.
- Robot/service account trong sản phẩm cụ thể.
- Shared technical account (không lý tưởng).
- Local/app-only principal được connector ánh xạ.

### 15.1. Cẩn trọng với `active=false`

SCIM User `active=false` thường được provider hiểu là deactivate account theo semantics của ứng dụng; nó có thể **chặn cả workload/API operation hợp lệ**, không chỉ desktop login. Nếu mục tiêu là cấm interactive nhưng giữ batch/service hoạt động, không dùng `active=false` như một “công tắc universal non-interactive” mà chưa biết provider behavior.

### 15.2. Dùng source-of-authority đúng

Ví dụ IdP quản lý app assignment; target SaaS có local login policy riêng. Chỉ gỡ group tại IdP chưa chắc chặn login bằng local password nếu target còn cho phép. Ngược lại, chặn local interactive UI mà không quản lý OAuth client grants chưa đủ kiểm soát NHI.

### 15.3. Deprovision khi retire

Khi service account thật sự ngừng dùng, phải xử lý:
- IdP/directory account và application assignments.
- SCIM User/Group hoặc target-specific roles.
- API keys, OAuth client registrations, secret/certificates.
- Local account và sessions.
- Dynamic membership/direct grants.
- Reconciliation xem có được re-provision hay không.

**SCIM response thành công không đồng nghĩa mọi credential đã hết hiệu lực.**

## 16. RBAC/ABAC: chặn quyền theo actor, channel và context

Chính sách tốt kiểm **identity type và cách dùng quyền**, nhưng không chỉ tin một claim được client tự gửi.

~~~text
function allowInteractiveSession(subject, loginContext, resource):
    if subject.lifecycleStatus != ACTIVE:
        return DENY

    if subject.accountClass in {SERVICE, WORKLOAD, AUTOMATION}:
        exception = trustedPolicy.findActiveException(
            subject.identityId,
            loginContext.protocol,
            resource.id,
            loginContext.trustedTime
        )

        if exception missing or exception.controlsNotSatisfied:
            return DENY

    if not subject.hasExplicitLoginRight(resource, loginContext.channel):
        return DENY

    if not trustedAuthenticationAssuranceSatisfiesPolicy:
        return DENY

    return evaluateResourceRBACAndABAC()
~~~

Đây là **pseudocode khái niệm**: trong môi trường thật, các nền tảng khác nhau có logon rights, protocol restrictions và PEP riêng. Một “human/service” flag từ request header không phải bằng chứng đáng tin.

### 16.1. Không chỉ chặn UI, phải giảm role

Một service account bị chặn RDP nhưng vẫn có `DomainAdmin` hoặc `DatabaseSuperuser` sẽ tiếp tục tạo rủi ro qua network/API. **Deny interactive** và **least privilege** là hai lớp kiểm soát khác nhau.

### 16.2. Scope theo môi trường

Một robot account production không nên dùng trong staging hoặc ngược lại nếu trust boundary khác:
- Identity riêng cho environment.
- Resource scope chính xác.
- Allowed execution hosts/runners.
- Network controls và egress constraints phù hợp.
- Secret vault và credential rotation riêng.
- Audit theo tenant, action, app và job.

### 16.3. Phân tách nhiệm vụ trong quản trị

Người xin bật interactive login cho service account không nên đồng thời là người phê duyệt ngoại lệ và xóa log của mình nếu policy yêu cầu độc lập. Cần **SoD approval** và kiểm soát quyền sửa account policy.

## 17. Source of truth và inventory các non-human accounts

Một policy không thể được kiểm chứng nếu tổ chức không biết **NHI nào đang tồn tại**.

### 17.1. Những trường cần quản lý

| Trường | Vì sao quan trọng? |
| --- | --- |
| `machineIdentityId` | Định danh ổn định cho workload/service. |
| `accountId`, `system`, `tenant` | Account thực tế tại OS/IdP/SaaS/cloud/DB. |
| `accountClass` | SERVICE, WORKLOAD, RPA, EMERGENCY hoặc loại phù hợp. |
| `businessPurpose` | Tại sao tồn tại và tác vụ được phép. |
| `ownerTeam` / `sponsor` | Ai chịu trách nhiệm và xử lý cảnh báo. |
| `environment`, `allowedHosts` | Ràng buộc nơi được chạy/đăng nhập. |
| `interactivePolicy` | DENY_BY_DEFAULT hoặc EXCEPTION_APPROVED có điều kiện. |
| `allowedProtocols` | RDP, SSH, GUI web, API, service/batch theo policy. |
| `credentialRefs` | Loại credential, nơi quản lý, hạn/rotation, không lưu plaintext. |
| `entitlementRefs` | Role/group/direct grants và permission effective. |
| `reviewDueAt`, `exceptionExpiresAt` | Ngày kiểm tra và thời hạn ngoại lệ. |
| `lifecycleState` | Active, Suspended, Retired, VerifiedClosed. |
| `targetEvidence` | Trạng thái thực thi và readback. |

### 17.2. Các nguồn phát hiện

- Active Directory/directory service accounts và gMSA.
- Windows services, scheduled tasks, host logon events.
- Linux OS users, systemd units, cron/SSH configs.
- Cloud service principals/managed identities, role assignments.
- Kubernetes ServiceAccounts, RoleBindings và tokens.
- OAuth clients, API gateway keys, SaaS technical users.
- RPA/VDI orchestration platforms, robot credential vaults.
- Database technical accounts và secret managers.
- IAM/IGA certification/approval records, CMDB/service catalog.

Một organization chỉ kiểm “mọi account tên bắt đầu bằng `svc_`” sẽ bỏ sót robot/service users được đặt tên giống người. Cần **phân loại từ nhiều nguồn** và owner attestations.

### 17.3. Không suy ra account vô dụng từ login count thấp

Một DR/recovery identity có thể không sử dụng trong nhiều tháng nhưng vẫn quan trọng. Không tự disable chỉ vì `lastInteractiveLoginAt=null`. Phải xác minh **service purpose, dependency, owner, scheduled usage và emergency readiness**.

## 18. JML: Joiner của nhân sự không nên tạo shared service login

Trong **Joiner**, HRIS/contractor registry xác minh person identity, manager và assignment. Employee nhận account IdP/human SSO theo policy.

Một lỗi thiết kế là: để employee mới chạy hỗ trợ, admin chia password của `svc-finance` vì user chưa được cấp quyền. Điều này:
- Bỏ qua identity proofing/authorization cá nhân.
- Làm mất attribution.
- Tạo credential exposure kéo dài.
- Không tạo access review theo employee.
- Khó thu hồi khi employee rời tổ chức.

### 18.1. Cách đúng

- Xác minh danh tính Joiner qua HRIS.
- Tạo named human account/SSO và MFA phù hợp.
- Gán role support/operator tối thiểu qua RBAC/ABAC và approval.
- Cho privileged action qua PAM/JIT khi cần.
- Không cho human đăng nhập trực tiếp bằng service identity.
- Giữ service identity riêng cho workload.

### 18.2. Joiner của workload

Khi service mới được triển khai:
- Owner đăng ký workload/service.
- IAM cấp identity/credential theo trust.
- Chỉ cho machine-to-machine role cần thiết.
- Cấu hình deny interactive login mặc định ở những nền tảng có khái niệm này.
- Test service/batch vẫn hoạt động.
- Ghi inventory và review lịch rotation.

**Không nhầm JML của người với lifecycle của dịch vụ**; chúng có thể liên kết qua ownership.

## 19. Mover: owner đổi vai trò nhưng workload vẫn chạy

Ví dụ Lan quản lý `billing-etl` rồi chuyển từ Finance Data sang Security.

### 19.1. Phân tách hai hướng xử lý

**Human Mover track:**
- Thu hồi Lan khỏi secret manager admin, CI/CD deploy, database owner và NHI management roles nếu hết căn cứ.
- Re-evaluate PAM eligibility/SSO app assignments.
- Chặn Lan mở interactive session dùng robot/service account.
- Xử lý PAT, SSH keys hoặc credential Lan từng kiểm soát.

**Workload continuity track:**
- Cập nhật ownerTeam/sponsor của `billing-etl`.
- Giữ workload chạy với least privilege còn hợp lệ.
- Kiểm tra credential có cần rotate không.
- Rà soát exception interactive/RPA, nếu có, với approver mới.
- Không xóa account dịch vụ chỉ vì owner nhân sự chuyển bộ phận.

### 19.2. Rủi ro khi quyền mới và cũ chồng lắp

Một engineer chuyển sang audit nhưng còn quyền mở interactive login bằng `svc-payments-admin` sẽ có khả năng thao tác ngoài vai trò mới. Phải thu hồi đường quản trị **theo effectiveAt**, không chờ manager mới approve các quyền khác.

### 19.3. Không dùng exception cũ cho vai trò mới

Interactive exception gắn với nhiệm vụ hỗ trợ Operations không được tự gia hạn khi người đó chuyển Finance. Cần re-evaluate **purpose, scope, approver, allowed hosts, effective dates**.

## 20. Leaver: người nghỉ không đồng nghĩa dừng service

Khi HRIS/contractor source xác nhận Leaver có hiệu lực:
1. Disable human IdP/SSO account và privileged identities theo policy.
2. Gỡ quyền quản trị workload, vault, CI/CD, cloud IAM, RPA orchestrator.
3. Revoke personal PAT/API tokens và SSH keys.
4. Xử lý shared service secret mà người đó đã thấy/có thể lấy, **rotate theo risk**.
5. Chấm dứt interactive service-account sessions không còn được phép.
6. Chuyển owner/sponsor và on-call responsibility.
7. Kiểm tra approvals/delegations/exception còn ghi tên người đã nghỉ.
8. Reconcile target accounts, group memberships, direct grants và session/token access.
9. Tiếp tục workload nếu service còn business purpose và owner hợp lệ.

### 20.1. Account service không tự trở thành Leaver

Một dịch vụ thanh toán chạy `svc-payments` vẫn có thể cần hoạt động sau khi người tạo account nghỉ việc. **Tắt service account bằng `active=false` chỉ để xử lý human Leaver** có thể làm mất hệ thống thanh toán. Thu hồi **quyền của người**, đánh giá shared credential exposure, rồi thực hiện **service lifecycle review** độc lập.

### 20.2. Trường hợp password của service đã được chia sẻ

Nếu Leaver từng biết password service có thể mở RDP/SSH, chỉ disable human SSO **không bảo đảm** họ mất khả năng truy cập. Cần:
- Rotate/disable credential liên quan và các phiên đang mở.
- Chặn interactive logon của service account theo policy.
- Rà soát host/network paths.
- Kiểm tra logs cho hành vi sử dụng credential sau cutoff.
- Giữ service vận hành qua managed credential/rollover nếu cần.

### 20.3. Rehire

Nhân viên quay lại không tự nhận quyền dùng service account đã được họ biết từ lần làm trước. Cần identity revalidation, fresh approval và least privilege theo assignment hiện tại.

## 21. Decommission non-human account và quyền truy cập tồn dư

Một service/job thật sự retired thì account kỹ thuật liên quan cần được **deprovision** theo phạm vi phù hợp.

~~~mermaid
flowchart TD
    S["Service retired / use case ended"] --> I["Inventory identity, account, credential, sessions, grants"]
    I --> D["Compute desired access and dependencies"]
    D --> R["Revoke source-of-authority grants"]
    R --> T["Rotate/revoke keys, clients, tokens, sessions"]
    T --> V["Target readback + effective-access verification"]
    V --> Q{"Quyền còn dùng được không?"}
    Q -->|Không| C["VERIFIED_CLOSED + audit"]
    Q -->|Có| M["REMEDIATION_REQUIRED + owner/SLA"]
    M --> R
~~~

### 21.1. Những đường phải xét

- OS local/domain account và interactive/service/batch rights.
- SCIM User/Group, IdP group/application assignment.
- Cloud service principal và resource-based IAM policy.
- Kubernetes ServiceAccount, bindings/tokens.
- OAuth client secret/certificate và token grants.
- Database user, direct SQL GRANT, SSH keys.
- RPA credential vault, scheduled robot jobs, desktop sessions.
- API keys/PATs và long-lived application sessions.
- PAM eligibility, active sessions và emergency paths.

### 21.2. Thu hồi quyền interactive không phải xóa sạch mọi thứ

Nếu use case chỉ yêu cầu **chặn đăng nhập UI** nhưng service vẫn chạy, cần giữ service/batch capabilities và các grants còn có căn cứ. Nếu service retired hoàn toàn, mới tính **full deprovision**. Cả hai cần readback, negative test và audit.

### 21.3. Không đóng ticket chỉ vì connector trả 200

Một PATCH/group removal trả thành công nhưng:
- Password vẫn đăng nhập được trực tiếp tại app.
- Local account còn active.
- Token/cookie session chưa bị invalidated.
- Role direct còn trong DB.
- Dynamic group tự cấp lại.

Đó là **residual access** cần remediation; `APPROVED`/`EXECUTED` chưa đồng nghĩa `VERIFIED_CLOSED`.

## 22. Phát hiện interactive login bất thường qua audit

### 22.1. Những tín hiệu gợi ý

| Signal | Ý nghĩa có thể | Cách kiểm chứng |
| --- | --- | --- |
| Service account có Windows logon type **2/10**. | Local/RDP interactive use. | Có approved robot/PAM exception không? |
| Service user có SSH shell trên host lạ. | Human/debug hoặc misuse. | Source IP, command audit, owner và incident. |
| NHI xuất hiện trong **interactive IdP sign-in**. | Technical user dùng browser flow. | Authentication flow, account classification. |
| OAuth client liên tục dùng user/password flow. | Automation dùng sai giao thức. | Client app, owner, IdP configuration. |
| Service credential được dùng từ workstation. | Credential bị copy hoặc chia sẻ. | Expected runners/hosts, PAM checkouts. |
| Robot account login ngoài khung lịch. | Misuse/compromise hoặc task bất thường. | Job schedule, exception, incident. |
| Interactive session tiếp tục sau expiry. | Privileged residual access. | Session/token state và target enforcement. |
| Service account tạo role/credential mới. | Escalation hoặc task admin được phép? | Authorized workflow, IAM logs, SoD. |
| Nhiều địa lý/host khác nhau dùng cùng service key. | Shared/copy hoặc distributed workload. | Trust environment và deployment inventory. |
| Exception approver đã Leaver. | Approval authority không còn hợp lệ. | JML current status và delegation. |

**Cảnh báo không phải kết luận chắc chắn về tấn công**. Một logon type 3 có thể là network authentication bình thường của service; không nên coi mọi network logon là interactive human access.

### 22.2. Dữ liệu audit cần liên kết

- `eventTime`, normalized timestamp/timezone.
- `accountId`, `machineIdentityId`, tenant/resource.
- `accountClass` và ownerTeam.
- `logonType`, protocol/flow nếu có.
- `sourceHost`, network/device, targetHost.
- `actorPersonIdentityId` nếu phiên được brokered qua PAM hoặc RPA job có người điều hành.
- `sessionId`, `jobId`, `ticketId`, `exceptionId`.
- `credentialRef` (tham chiếu, **không lưu secret**).
- `policyDecision`, `reasonCode`, `result` và target evidence.

### 22.3. Tránh lộ credential trong logging

Không ghi password, OTP, private key, full access token, session cookie, RDP file chứa secret. Logs cần được **phân quyền, hạn chế retention đúng chính sách và bảo vệ tính toàn vẹn**, nhất là khi principal có quyền sửa monitoring.

## 23. Mô hình policy: không interactive theo mặc định, exception được ràng buộc

Một policy có thể tổ chức như sau:

~~~text
POLICY NHI-INTERACTIVE-01

Default:
  SERVICE, WORKLOAD, API_CLIENT -> DENY interactive login

Allowed noninteractive:
  service/batch execution on registered hosts
  API workload federation / mTLS / client credentials
  scoped target resource access

Exception categories:
  LEGACY_GUI_ROBOT
  APPROVED_MAINTENANCE
  PREDEFINED_EMERGENCY_RECOVERY

Exception required fields:
  accountId, owner, resource, protocol, allowed host,
  purpose, start, end, approvers, compensating controls,
  audit plan, revocation plan, reviewDueAt

Prohibited:
  self-approval for privileged exceptions
  one secret shared broadly across users
  blanket MFA bypass where not authorized
  indefinite unrestricted interactive admin
~~~

Đây là **mẫu chính sách nội bộ minh họa**, không phải cấu hình triển khai cho Windows/IdP/cloud nào. Một số machine identities không hỗ trợ interactive login về mặt sản phẩm; không nên tạo “exception UI” cho những loại đó.

### 23.1. Quyết định theo tình huống

~~~mermaid
flowchart TD
    Q["Login attempt + identity/account classification"] --> I{"Human named identity?"}
    I -->|Có| H["Human SSO/MFA/role policy"]
    I -->|Không| T{"Non-human account?"}
    T -->|Không rõ| U["Investigate classification; no unverified exception"]
    T -->|Có| C{"Channel interactive?"}
    C -->|Không| N["Noninteractive service/workload AuthN + AuthZ"]
    C -->|Có| E{"Approved scoped exception active?"}
    E -->|Không| D["DENY + alert/audit"]
    E -->|Có| V["Check owner, source, host, time, MFA/PAM, SoD"]
    V -->|Pass| P["PERMIT narrow session + monitoring"]
    V -->|Fail| D
~~~

### 23.2. No-self-approval và ủy quyền

Một service owner có thể yêu cầu exception, nhưng quyền đặc biệt có thể cần **Security, resource owner hoặc risk owner độc lập**. Không dùng hai tài khoản của cùng người để tạo hai approval khi policy đòi hai người khác nhau. Delegation phải có scope/time và không vượt authority.

## 24. JSON hồ sơ exception minh họa

~~~json
{
  "accountId": "rpa-invoice-processor-prod",
  "accountClass": "RPA_ROBOT",
  "machineIdentityId": "robot-finance-invoice-prod",
  "ownerTeamRef": "finance-operations",
  "target": {
    "applicationRef": "legacy-erp",
    "tenantRef": "tenant-vn",
    "resourceScope": "invoice-processing"
  },
  "interactiveAccess": {
    "defaultPolicy": "DENY",
    "exceptionId": "NHI-EX-2026-007",
    "approved": true,
    "allowedChannels": ["GUI_SESSION"],
    "allowedHosts": ["rpa-runner-vn-02"],
    "validFrom": "2026-12-02T09:00:00+07:00",
    "validUntil": "2026-12-02T17:00:00+07:00",
    "controlRefs": [
      "vault-managed-credential",
      "session-monitoring",
      "transaction-approval-sod"
    ]
  },
  "access": {
    "roleRefs": ["InvoiceProcessingRobot"],
    "privilegedOperations": "NONE"
  },
  "lifecycle": {
    "status": "ACTIVE",
    "reviewPolicyRef": "rpa-quarterly-access-review"
  },
  "verification": {
    "interactiveExceptionActive": "PENDING_TARGET_CHECK"
  }
}
~~~

Đây là **schema nội bộ minh họa**, không phải SCIM extension/OIDC claim chuẩn. `approved=true` ở registry **không tự làm Windows, SaaS hoặc RPA broker thực thi đúng exception**. Target phải kiểm policy hoặc được cấu hình phù hợp, sau đó readback/test.

### 24.1. Bản ghi phiên gắn người hoặc job

~~~json
{
  "eventId": "interactive-attempt-2026-0910",
  "time": "2026-12-02T10:15:00+07:00",
  "accountId": "rpa-invoice-processor-prod",
  "jobId": "rpa-run-3018",
  "sourceHost": "rpa-runner-vn-02",
  "targetApplication": "legacy-erp",
  "loginChannel": "GUI_SESSION",
  "policyRef": "NHI-EX-2026-007",
  "decision": "PERMIT",
  "sessionRef": "rpa-session-991",
  "credentialRef": "vault-secret-ref-27"
}
~~~

Log không nên chứa plaintext secret hay full token. Nếu account do người điều khiển thông qua PAM, cần thêm **actor person ID** theo bằng chứng có thẩm quyền.

## 25. Pseudocode: kiểm tra interactive session cho account kỹ thuật

~~~text
function decideInteractiveLogin(accountId, context, now):
    account = resolveTrustedAccountAndMachineIdentity(accountId)
    if account missing or account.status != ACTIVE:
        return DENY

    if context.channel is not INTERACTIVE:
        return evaluateNonInteractiveAuthNAndAuthZ()

    if account.classification == HUMAN:
        return evaluateHumanLoginPolicy(context, account)

    if account.classification not in {SERVICE, RPA_ROBOT, AUTOMATION}:
        return DENY

    exception = loadCurrentApprovedException(
        account.machineIdentityId, account.target, context.channel
    )

    if exception missing or exception.versionInvalid:
        return DENY

    if now < exception.validFrom or now >= exception.validUntil:
        return DENY

    if context.sourceHost not in exception.allowedHosts:
        return DENY

    if not exception.hasRequiredIndependentApprovals:
        return DENY

    if not exception.compensatingControlsActive:
        return DENY

    if not authenticationAssuranceMeetsPolicy(context):
        return DENY

    if account.ownerTeamMissing or account.serviceRetired:
        return DENY

    return evaluateScopedTargetAuthorization(account, context)
~~~

Đây là **pseudocode khái niệm**, không phải một hàm sẵn có của IAM. Trong thực tế cần tránh time-of-check/time-of-use, stale directory data, race conditions, forged client context và bypass qua đường local/app-specific login.

### 25.1. Không dùng account type do client tự gửi

Một request từ browser có thể gửi `accountClass=HUMAN`, nhưng hệ thống phải lấy classification từ **identity registry/target policy đáng tin**. Tương tự, source IP hoặc user agent tự khai không phải bằng chứng đủ về actor. Cần platform logs, session broker và verified device/network identity khi áp dụng.

### 25.2. Expiry phải có hiệu lực ở target

Nếu exception hết hạn 17:00 nhưng SaaS session còn hoạt động tới 20:00, quy trình chưa **thực thi giới hạn thời gian**. Cần session termination, claim/credential revocation, runtime checks hoặc giảm session TTL theo khả năng target. Đừng chỉ sửa một ô `expired=true` tại IAM.

## 26. Thiết kế audit và detection rule mẫu

### 26.1. Dạng sự kiện chuẩn hóa

~~~json
{
  "eventType": "NHI_INTERACTIVE_LOGIN",
  "timestamp": "2026-12-02T09:15:00Z",
  "accountRef": "svc-report-export",
  "machineIdentityRef": "service-report-export-prod",
  "accountClass": "SERVICE",
  "platform": "WINDOWS",
  "logonType": 10,
  "sourceHost": "admin-workstation-17",
  "targetHost": "app-server-02",
  "approvedExceptionRef": null,
  "decision": "ALERT",
  "severity": "HIGH"
}
~~~

Ví dụ sự kiện đã chuẩn hóa từ Windows log; **`logonType=10` không phải JSON field chung do Windows phát ra đúng schema này**. Một SIEM thường phải ingest/normalize các logs khác nhau.

### 26.2. Logic giám sát

~~~text
if event.accountClass in {SERVICE, WORKLOAD, RPA_ROBOT}
   and event.loginChannel is INTERACTIVE:
    if no approved matching exception
       or event.sourceHost not allowed
       or event.timestamp outside exception window:
        alert security + account owner
        consider containment according to policy
~~~

Cần đánh giá false positives:
- RPA GUI hợp lệ.
- Scheduled task không phải interactive.
- Windows type 3 network auth của service.
- Maintenance đã được brokered qua PAM.
- Emergency recovery theo break-glass policy.

### 26.3. Response khi phát hiện lạm dụng

- Xác định account, source host, target, timestamp và owner.
- Xác minh exception/ticket và danh tính người hoặc job thực sự dùng account.
- Bảo toàn logs, session metadata và event correlation.
- Nếu không được phép: chặn interactive path, khóa session, cô lập host hoặc credential khi phù hợp.
- Rà soát quyền admin/direct grants, token và secret exposure.
- Rotate/revoke credential nếu có nguy cơ bị lộ; tránh làm dừng service mà không có kế hoạch.
- Đối soát các thao tác thực hiện và phát hiện privilege escalation.
- Ghi incident/remediation, nguyên nhân, corrective controls và validation.

Không tự động disable toàn bộ service account production theo một cảnh báo chưa xác minh nếu hậu quả availability nghiêm trọng; cần playbook phân tầng risk và containment, nhưng **không trì hoãn** ngăn chặn hành vi đang gây hại.

## 27. Tình huống xuyên suốt: service account dùng để RDP kiểm tra production

**Bối cảnh:** Ứng dụng báo cáo chạy trên Windows server bằng domain account `svc-reports`. Account có quyền đọc một số secrets và kết nối database. Một kỹ sư mới không có quyền vào server nên người quản lý chia sẻ password `svc-reports` để RDP kiểm tra lỗi.

### 27.1. Điều sai

1. Kỹ sư sử dụng danh tính của service, không phải danh tính nhân viên.
2. Log Windows ghi `svc-reports`, thiếu attribution ai là người thực hiện.
3. Password service đã bị tiết lộ cho người dùng, có thể dùng lại ngoài nhiệm vụ.
4. RDP tạo đường mới ngoài service execution.
5. Khi kỹ sư Mover/Leaver, disable personal SSO không chặn password service đã biết.
6. Nếu account có quyền DB/network rộng, kẻ tấn công có thể lạm dụng.
7. Khi rotate ngay password, service có thể không khởi động nếu không có rollout.

### 27.2. Phương án xử lý

- Kỹ sư dùng **named human account** để login vào jump host/target theo policy.
- Cấp quyền troubleshooting tối thiểu hoặc PAM/JIT scoped elevation, kèm ticket.
- Chặn local/RDP interactive login của `svc-reports` trên host áp dụng, **sau khi kiểm thử service vẫn chạy**.
- Cân nhắc chuyển sang gMSA hoặc platform-managed service credentials khi phù hợp.
- Rotate password đã chia sẻ theo quy trình an toàn và kiểm tra mọi dependent services.
- Kiểm tra Windows logon events, source hosts, credential usage và target actions.
- Rà soát database/direct role, giảm privilege không cần.
- Ghi owner, access review, session/token validation và remediation.

### 27.3. Kết quả cần chứng minh

| Kiểm thử | Kết quả kỳ vọng |
| --- | --- |
| Service chạy lại sau deployment/restart. | Hoạt động bằng account/credential được phép. |
| Nhân viên dùng personal account qua PAM để debug. | Được vào đúng host và action đã duyệt. |
| Ai đó thử RDP bằng `svc-reports`. | Deny theo policy tại host áp dụng. |
| Từ máy không được phép gọi DB bằng key cũ. | Credential cũ bị thu hồi hoặc bị chặn. |
| Log thao tác sửa cấu hình. | Có attribution người/jump host/ticket. |
| Người cũ Leaver. | Không còn secret hoặc quyền quản trị workload ngoài căn cứ. |

**Không kết luận đã xử lý chỉ vì bật Deny RDP**: nếu password đã lộ, kiểm tra **service credential rotation, network logon và direct API/DB access** vẫn bắt buộc.

## 28. Tình huống: unattended RPA trong hệ thống ERP legacy

Một robot xử lý hóa đơn đăng nhập ứng dụng ERP chỉ hỗ trợ GUI, không có API được phép dùng.

### 28.1. Thiết kế nên có

- Robot account riêng: `rpa-invoice-prod`.
- Được phân loại **RPA_ROBOT**, không nhầm human identity.
- Chỉ có role UI phục vụ xử lý hóa đơn đã được owner duyệt.
- Tương tác từ những runner/VDI được đăng ký.
- Credential vault có rotation/custody và secret masking.
- Một **interactive exception** được phê duyệt, có owner/risk review/expiry.
- Bot không được duyệt thanh toán do chính nó tạo nếu transaction SoD yêu cầu người khác.
- RPA job audit gắn transaction ID, phiên, business approver và artifact.
- Detection cho login từ nguồn khác, giờ khác, role khác.
- Kế hoạch chuyển sang API khi ERP được nâng cấp.

### 28.2. Khi owner của bot nghỉ việc

Không xóa bot account ngay nếu job vẫn chạy. Chuyển owner, revoke quyền người cũ ở RPA/vault/ERP, rotate credential có rủi ro, revalidate interactive exception và kiểm tra transaction audit.

### 28.3. Khi bot không còn cần

Disable schedule/runner, gỡ ERP role/account và interactive exception, revoke secret/session, readback target access, tránh job tự re-enable sau khi connector chạy lại.

## 29. Tình huống: CI/CD pipeline dùng tài khoản người để deploy

Một pipeline dùng username/password của một nhân viên để login cloud console và copy session token cho deploy. Hệ quả:
- Pipeline phụ thuộc người/mật khẩu/MFA và có thể dừng khi Leaver.
- Token và password có thể nằm trong runner/log.
- Cloud audit có thể ghi người đó thay vì workload/job.
- Quyền thường rộng hơn cần thiết và không ràng buộc artifact.
- SoD giữa commit và production deploy dễ bị bỏ qua.

### 29.1. Cách thiết kế lại

1. Đăng ký logical workload identity cho pipeline.
2. Dùng federation/managed identity hoặc client authentication phù hợp.
3. Ràng buộc subject/audience/issuer và repository/environment/workflow theo trust policy.
4. Cấp short-lived token với role/resource scope tối thiểu.
5. Yêu cầu independent approval trước prod deploy nếu SoD policy cần.
6. Log job ID, code revision/artifact, actor approver và target.
7. Revoke human password grant/old tokens và kiểm chứng pipeline vẫn hoạt động.
8. Khi owner Mover/Leaver, chuyển ownership và gỡ **quyền con người**, không phá pipeline.

Không cho pipeline `iam:assign-role` hoặc quyền tự sửa approval policy nếu không được kiểm soát, vì đây là đường **tự nâng quyền** dù pipeline không có interactive login.

## 30. Ma trận kiểm thử interactive login

| Test | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| **T1** | Windows service account thử console logon. | Deny trên host theo policy. |
| **T2** | Windows service account thử RDP. | Deny nếu không có exception hợp lệ. |
| **T3** | Cùng account khởi chạy service đã được đăng ký. | Service chạy bình thường với rights cần thiết. |
| **T4** | Batch job được phép chạy theo schedule. | Không bị block do nhầm batch=interactive. |
| **T5** | Service account network authentication hợp lệ. | Được đánh giá đúng AuthZ, không báo sai mọi type 3. |
| **T6** | SSH shell bằng Linux service user. | Deny nếu policy cấm, không ảnh hưởng daemon. |
| **T7** | Sử dụng service private key từ workstation lạ. | Deny/alert theo trust/policy; điều tra exposure. |
| **T8** | OAuth client credentials được dùng đúng app-only. | API Permit đúng scope, không cần browser user session. |
| **T9** | Browser interactive login bằng account service không có exception. | Deny/audit. |
| **T10** | IdP conditional access chỉ áp human nhưng service principal còn quyền rộng. | Kiểm riêng service-principal policy/target AuthZ. |
| **T11** | Robot GUI login từ runner hợp lệ trong cửa sổ duyệt. | Permit action hẹp và ghi attribution/job ID. |
| **T12** | Robot GUI login từ host lạ. | Deny và alert. |
| **T13** | Robot session còn sau exception expiry. | Terminate/restrict, không coi Verified. |
| **T14** | Robot tạo và tự duyệt cùng thanh toán. | Chặn nếu transaction SoD bắt buộc. |
| **T15** | Owner Mover, interactive exception còn active. | Re-evaluate và revoke nếu không còn căn cứ. |
| **T16** | Human owner Leaver, service vẫn cần. | Human rights revoked; workload có owner mới. |
| **T17** | Leaver từng biết service password. | Rotate/revoke exposed credential và sessions, giữ service ổn định. |
| **T18** | SCIM `active=false` với account chạy service. | Không dùng để chặn interactive nếu sẽ gây downtime sai mục tiêu. |
| **T19** | Account retire, OAuth key còn dùng được. | Closure failed; remediation. |
| **T20** | Kubernetes ServiceAccount token từ pod sai. | Chặn theo issuer/subject/audience/trust policy. |
| **T21** | PAM operator login bằng personal identity. | Attribution và least privilege đúng. |
| **T22** | Người dùng hai account để tự approve exception. | SoD check chặn nếu policy yêu cầu độc lập. |
| **T23** | Dynamic group re-add service principal sau revoke. | Regrant detected, sửa authoritative source. |
| **T24** | SIEM alert NHI logon type 10 có approved RPA exception. | Nhận diện hợp lệ nhưng vẫn kiểm host/time/actions. |

### 30.1. Test tích cực và tiêu cực

- **Positive:** workload vẫn gọi API/khởi chạy service/batch đúng nhiệm vụ sau khi interactive bị chặn.
- **Negative:** không thể mở desktop/browser/shell session trái policy.
- **Exception:** approved robot/emergency path hoạt động đúng host, thời hạn và scope.
- **Closure:** sau expiry/Leaver/retire, tài khoản hoặc credential không còn tạo access path trái căn cứ.
- **Audit:** phân biệt human actor, robot job, machine identity và target action.

Không thực hiện thử truy cập trái phép vào môi trường production; dùng **tài khoản/hệ thống được ủy quyền, test target có kiểm soát hoặc policy simulation**.

## 31. KPI và cách đo hiệu quả

| KPI | Ý nghĩa | Cẩn trọng |
| --- | --- | --- |
| **NHI inventory coverage** | Machine/service/robot accounts có trong inventory. | Không chỉ đếm tên bắt đầu `svc_`. |
| **Owner coverage** | NHI có ownerTeam/business purpose hiện hành. | Owner Leaver không tính hợp lệ. |
| **Interactive-deny coverage** | Tỷ lệ NHI phù hợp có policy chặn UI/shell/RDP. | Phải đo trên hosts/targets thực tế, không chỉ policy registry. |
| **Interactive NHI sign-ins** | Số phiên interactive theo account, host, exception. | RPA exception hợp lệ khác unauthorized login. |
| **Unapproved interactive incidents** | Phát hiện phiên không có policy/exception. | Không suy 100% từ log type duy nhất. |
| **Exception expiry compliance** | Ngoại lệ chấm dứt đúng hạn, session bị chặn. | `EXPIRED` ở ticket chưa là target verified. |
| **Shared credential count** | Secret/service account dùng cho nhiều workloads/người. | Cần phân biệt legitimate replicas với cross-service sharing. |
| **Secret exposure response latency** | Thời gian chặn credential dùng trái phép. | Chỉ rotate key chưa chắc dừng attacker còn chiếm workload. |
| **Human-owner Leaver handover SLA** | Thời gian chuyển owner/gỡ quyền người cũ. | Không xóa service còn hợp lệ. |
| **API-first migration progress** | Bot GUI legacy được thay bằng integration chuẩn. | Không hy sinh business controls/SoD. |
| **Residual interactive access** | Session/token/login còn hợp lệ sau revoke deadline. | Cần evidence tại target. |
| **SoD exceptions reviewed** | Ngoại lệ có independent owner/risk approval. | Số click approval không phải quality. |
| **Target verification rate** | Kiểm chứng deny interactive và service continuity. | Log 200/403 đơn lẻ không đủ đầy đủ. |

**Không có ngưỡng tỷ lệ universal** cho mọi hệ thống; phân nhóm theo sensitivity, privilege, môi trường, loại automation và khả năng giám sát.

## 32. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi service account là user tiện để RDP debug. | Mất attribution và lộ password. | Named human account + PAM/JIT. |
| Đặt `Deny log on locally` rồi kết luận service hoàn toàn an toàn. | Network/API privileges vẫn rộng. | Least privilege và grant-path review. |
| Gỡ mọi service/batch logon rights để “chặn login”. | Dịch vụ/jobs dừng. | Chặn đúng loại interactive, test continuity. |
| Cho mọi NHI miễn MFA/Conditional Access toàn cục. | Human có thể dùng service password qua browser. | Machine-specific AuthN + scoped GUI exceptions. |
| Bắt bot API gọi MFA push mỗi lần. | Automation không hoạt động, khuyến khích workaround. | Client credentials/federation/mTLS. |
| Dùng OIDC browser session của nhân viên làm CI/CD credential. | Phụ thuộc human Leaver và token leak. | Workload identity và protected deployment approvals. |
| Dùng một account/secret cho RPA và backend service. | Blast radius, khó revoke. | Split identity by purpose/trust boundary. |
| Coi Kubernetes ServiceAccount là Windows/Linux interactive user. | Policy áp sai điểm. | Token/issuer/RBAC/runtime controls. |
| Chỉ dựa vào prefix `svc_` để inventory. | Bỏ sót bot/account kỹ thuật tên người. | Multi-source discovery và ownership. |
| Chỉ xem Windows logon type 3 như bằng chứng human misuse. | False positives. | Correlate protocol/host/job/use case. |
| Phê duyệt ngoại lệ vô thời hạn. | Interactive privilege trở thành thường trực. | Scope, expiry, reapproval, target verification. |
| Robot có quyền tự tạo và tự duyệt giao dịch. | SoD bị bỏ qua. | Independent transaction control. |
| SCIM `active=false` để chặn GUI nhưng service vẫn cần hoạt động. | Service outage. | Provider-specific interactive policy. |
| Không rotate password khi employee biết secret nghỉ việc. | Leaver vẫn có đường truy cập. | Credential exposure review, rotation. |
| Xóa machine identity khi human owner Leaver. | Gián đoạn workload. | Owner handover + human permission revoke. |
| Chỉ đóng ticket khi IdP group đã gỡ. | Local account/token/session còn. | Target readback và effective-access tests. |
| Quên shared emergency account trong inventory. | Recovery misuse không có attribution. | Break-glass governance riêng. |
| Đưa password/full token vào SIEM. | Log trở thành kho credential. | Redaction và secret references. |

## 33. Checklist thiết kế và vận hành

### 33.1. Trước khi tạo NHI

- [ ] Phân loại đúng SERVICE/WORKLOAD/RPA/DEVICE/EMERGENCY/HUMAN.
- [ ] Có owner team, service purpose, environment, target account mapping.
- [ ] Xác định rõ tác vụ cần machine-to-machine hay GUI.
- [ ] Ưu tiên API/federation/mTLS/managed identity nếu khả thi.
- [ ] Không dùng human password cho daemon/job.
- [ ] Không dùng chung secret/admin account giữa trust boundaries không cần thiết.
- [ ] Chỉ cấp RBAC/ABAC permission tối thiểu.
- [ ] Cấu hình deny interactive ở tầng có khả năng enforce, trừ exception hợp lệ.
- [ ] Test account vẫn có service/batch rights cần thiết.
- [ ] Có secret storage, rotation/expiry, audit và owner review.

### 33.2. Với RPA hoặc legacy exception

- [ ] Có lý do vì sao API/noninteractive không đáp ứng.
- [ ] Robot/maintenance account riêng, không dùng service backend identity toàn quyền.
- [ ] Exception có scope, host, protocol, thời hạn, owner và approvals.
- [ ] MFA/authentication mechanism phù hợp sản phẩm, không bypass blanket.
- [ ] PAM/RPA broker và secret vault bảo vệ credential.
- [ ] User action/transaction có independent SoD khi cần.
- [ ] Logs liên kết session/job, target và người yêu cầu/phê duyệt.
- [ ] Có session termination và revocation/readback ở expiry.
- [ ] Có kế hoạch cải tiến/migration khỏi GUI dependency.

### 33.3. Trong JML và khi ngừng dùng

- [ ] Human Joiner dùng named SSO identity, không chia service password.
- [ ] Human Mover gỡ quyền cũ vào vault, CI/CD, PAM, robot, target.
- [ ] Human Leaver disable person account, xử lý secret exposure và owner handover.
- [ ] Không xóa workload vẫn có business purpose chỉ vì owner nghỉ.
- [ ] Khi service retired, revoke OS/cloud/DB/SCIM/OAuth keys/tokens/sessions.
- [ ] Xử lý direct grants, dynamic groups và scheduled re-provisioning.
- [ ] Readback đúng target và kiểm tra negative interactive access.
- [ ] Kiểm tra positive business task vẫn hoạt động khi chỉ chặn GUI.
- [ ] Audit có decision, actor/job, owner, policy, target, timestamp.
- [ ] Chỉ đánh dấu `VERIFIED_CLOSED` khi không còn đường truy cập trái căn cứ.

## 34. Bài tập tự kiểm tra

### 34.1. Bài A — Type 5 hay type 10?

Windows service dùng `svc-report` tạo logon type 5 trên app server, rồi cùng account xuất hiện logon type 10 từ workstation lạ. Hai event khác nhau ở đâu? Điều tra theo host/actor/exception và cách giữ service hoạt động khi chặn RDP.

### 34.2. Bài B — Linux shell và API

Một Linux service account có shell `nologin` nhưng API key của nó vẫn có quyền tạo admin trong hệ thống khác. Vì sao “không login shell được” chưa đạt least privilege? Thiết kế grant inventory và credential controls.

### 34.3. Bài C — IdP và OAuth

Một developer muốn để batch job đăng nhập web SSO bằng human username/password vì chưa biết OAuth client credentials. Hãy phân biệt interactive user flow, app-only token và MFA, rồi đề xuất kiến trúc đúng.

### 34.4. Bài D — Unattended RPA

Bot phải xử lý invoice trong ERP chỉ có GUI. Nêu lý do ngoại lệ có thể hợp lệ, các controls cần có, cách tách maker/checker và cách truy vết job tới target transaction.

### 34.5. Bài E — Break-glass không phải service account

IdP đang offline. Người vận hành đề nghị dùng password của `svc-database-admin` vốn do ba jobs cùng dùng. Hãy đề xuất recovery path riêng có custody/audit, giải thích vì sao không chia credential service làm human login.

### 34.6. Bài F — Human Mover/Leaver

Engineer sở hữu `billing-etl` chuyển nhóm rồi nghỉ, account workload vẫn được DB cho INSERT. Phải giữ/thu hồi những quyền nào? Khi nào rotate key và vì sao không tự xóa workload?

### 34.7. Bài G — SCIM inactive

Một connector gửi `active=false` cho User đại diện service account nhằm “chặn interactive login”. Service API lập tức lỗi. Sai lầm thiết kế ở đâu? Những policy nào mới chặn riêng GUI nhưng giữ service operation?

### 34.8. Bài H — Kubernetes token

Pod dùng ServiceAccount `default` có cluster-admin; kẻ tấn công lấy token từ Pod. Vì sao Windows Deny RDP không giúp? Những kiểm soát issuer, audience, K8s RBAC, token projection, namespace và runtime nào cần có?

### 34.9. Bài I — Token còn sau hạn

Interactive exception của robot hết lúc 17:00, nhưng browser session vẫn xử lý invoice lúc 18:00. Tại sao ticket EXPIRED chưa là VERIFIED_CLOSED? Đề xuất session termination và target negative test.

### 34.10. Bài J — SIEM detection

Security lập rule “mọi logon type 3 của svc_* đều là tấn công”, tạo hàng nghìn cảnh báo. Hãy giải thích khác biệt network/service/interactive logon và đề xuất rule sử dụng account classification, logon type 2/10, host, exception, owner và baseline.

### 34.11. Bài K — Shared credential

Ba workloads và hai nhân viên dùng cùng `svc-finance-admin` password. Một workload retired, một nhân viên Leaver. Hãy thiết kế tách principal, chuyển từng workload, rotate/revoke key và giữ business continuity.

### 34.12. Bài L — Đo hiệu quả

Tổ chức báo đã chặn interactive cho 100% NHI trong IdP, nhưng local Windows accounts, RPA bots và SaaS local login không được inventory. Đây có phải coverage 100%? Hãy xây chỉ số dựa trên **multi-source NHI inventory và target-enforced verification**.

**Điểm cần ghi nhớ:** **Interactive login của non-human account phải được xem là một khả năng rủi ro cần kiểm soát riêng**, không phải thuộc tính mặc định của mọi service identity. Phân biệt **interactive session** với **service/batch/network/API authentication**, bảo vệ **human attribution**, và **deny interactive by default** tại những điểm có thể enforce, nhưng giữ hoạt động machine-to-machine hợp lệ. Nếu legacy GUI/RPA hoặc break-glass thực sự cần login, dùng **account/đường truy cập riêng, approval, PAM/credential vault, scope, time limit, SoD và audit**. Trong vòng đời IAM **Joiner–Mover–Leaver**, phải thu hồi quyền của **người quản trị** khi không còn căn cứ, quản lý **workload owner** độc lập và đối soát IdP/SSO, SCIM, RBAC/ABAC, sessions/tokens/credentials tới khi **quyền thực tế ở target** đúng chính sách, tránh **shared access và residual privilege**.

