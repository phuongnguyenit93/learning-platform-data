# Device signal trong Risk-based Access và vòng đời danh tính IAM

## 1. Device signal là gì?

**Device signal (tín hiệu thiết bị)** là một thuộc tính, quan sát hoặc khẳng định liên quan đến **thiết bị đang tham gia yêu cầu truy cập** mà hệ thống IAM có thể sử dụng để **đánh giá rủi ro và điều chỉnh quyết định truy cập**. Ví dụ: thiết bị có được tổ chức quản lý không, có đáp ứng chính sách bảo mật không, hệ điều hành có bản vá phù hợp không, EDR có hoạt động không, khóa riêng có được bảo vệ bằng phần cứng không, hay thiết bị từng bị đánh dấu mất cắp.

Giả sử nhân viên Lan truy cập hệ thống tài chính bằng passkey và MFA. Yêu cầu từ laptop công ty đã đăng ký MDM, có mã hóa ổ đĩa, EDR khỏe mạnh và vừa gửi trạng thái bảo mật có thể được xử lý khác với yêu cầu từ một thiết bị không xác định. Tuy nhiên, **device signal không thay thế xác thực Lan là ai hoặc kiểm tra Lan có quyền thực hiện action đó không**.

Trong chương **Risk-based access**, device signal là đầu vào cho **risk assessment, adaptive authentication và conditional access**. Trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, nó cần được liên kết với quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**: từ xác minh, tạo account và cấp quyền đến rà soát, thay đổi vai trò và thu hồi; kết nối **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư**.

### Mục tiêu học tập

Sau khi học, bạn có thể:

1. Định nghĩa device signal và phân biệt **device identity, ownership, management, compliance, posture, attestation và risk score**.
2. Nhận diện những tín hiệu phổ biến từ **MDM/UEM, EDR, hệ điều hành, PKI, TPM và runtime**.
3. Đánh giá **nguồn gốc, tính toàn vẹn, độ mới, phạm vi áp dụng và độ chắc chắn** của tín hiệu.
4. Xây dựng chính sách **risk-based/conditional access** theo danh tính, thiết bị, action, resource và ngữ cảnh.
5. Phân biệt **MFA/step-up, deny, quarantine, restricted session và JIT** khi xử lý thiết bị có rủi ro.
6. Hiểu những giới hạn của **OIDC/SSO, token/session, SCIM và quyền truy cập thực tế**.
7. Gắn vòng đời thiết bị với **Joiner–Mover–Leaver, contractor, rejoiner và account được chia sẻ**.
8. Thiết kế **audit, bảo vệ quyền riêng tư, monitoring, reconciliation, kiểm thử và incident runbook**.

## 2. Vì sao thiết bị ảnh hưởng quyết định truy cập?

Thông tin đăng nhập hợp lệ không bảo đảm **môi trường sử dụng credential an toàn**. Một tài khoản có MFA vẫn có thể bị lạm dụng nếu thiết bị đang nhiễm mã độc, bị đánh cắp phiên đăng nhập hoặc không còn được quản lý.

Các tình huống cần phân biệt:

- Người dùng hợp lệ đăng nhập từ **laptop doanh nghiệp đang đáp ứng chính sách**.
- Cùng người dùng đăng nhập từ **laptop cá nhân không có bằng chứng posture**.
- Thiết bị từng tuân thủ nhưng **EDR vừa báo dấu hiệu xâm nhập**.
- Thiết bị công ty **bị báo mất** trong asset registry.
- Thiết bị hợp lệ nhưng yêu cầu **truy cập tài nguyên thuộc tenant khác**.
- Thiết bị đạt posture nhưng account người dùng đã **Leaver**.
- Thiết bị mang chứng thư hợp lệ nhưng certificate **bị sao chép hoặc issuer không được trust**.

Mỗi trường hợp có mức tin cậy và tác động khác nhau. **Một trạng thái “managed” đơn lẻ không chứng minh thiết bị an toàn tuyệt đối**; ngược lại, thiếu signal từ một browser không tự chứng minh user là attacker.

### Mô hình tổng quát

~~~mermaid
flowchart LR
    U[User authentication + IAM relationship] --> R[Risk / Policy Engine]
    D[Device signals: MDM, EDR, OS, attestation] --> R
    C[Context: action, resource, session, network] --> R
    R --> DEC{Policy decision}
    DEC -->|Permit| PEP[Resource enforcement]
    DEC -->|Step-up| MFA[Reauthentication / MFA]
    DEC -->|Restricted| LIM[Restricted access]
    DEC -->|Deny| DENY[Block + guidance]
    PEP --> AUD[Audit / Continuous evaluation]
    MFA --> AUD
    LIM --> AUD
    DENY --> AUD
~~~

**Risk engine đưa ra tín hiệu/quyết định; Policy Enforcement Point (PEP) phải thực thi quyết định đó**. Nếu API bỏ qua condition và vẫn trả dữ liệu, việc đăng nhập IdP đã xét device posture không đủ để bảo vệ action.

## 3. Device signal khác device identity và device trust ra sao?

| Khái niệm | Câu hỏi | Ví dụ | Giới hạn |
|---|---|---|---|
| **Device identity** | Đang nói tới thiết bị nào? | deviceId/assetId hoặc certificate bound | ID tự khai có thể giả |
| **Device ownership** | Thiết bị thuộc ai/tổ chức nào? | Corporate-owned, BYOD, shared | Sở hữu không bảo đảm posture |
| **Device management** | Có được MDM/UEM quản lý không? | Enrollment record và management channel | Managed vẫn có thể bị xâm nhập |
| **Device compliance** | Có đạt chính sách được định nghĩa? | MDM compliant=true | Phụ thuộc policy, dữ liệu và freshness |
| **Device posture** | Trạng thái bảo mật hiện tại hoặc gần đây? | EDR healthy, disk encrypted | Có thể thiếu/đến chậm |
| **Device attestation** | Có bằng chứng bảo vệ bằng cơ chế đáng tin? | TPM-backed key attestation | Không chứng minh ứng dụng không có bug |
| **Device signal** | Dữ kiện dùng trong đánh giá truy cập? | OS version, enrollment, risk alert | Mỗi signal có độ tin cậy riêng |
| **Device trust decision** | Có thể chấp nhận thiết bị cho use case này? | Eligible for read-only | Phụ thuộc resource/action và thời điểm |
| **User identity** | Người dùng là ai, quan hệ có hợp lệ? | personId + relationshipId | Không suy ra từ deviceId |
| **Access entitlement** | Người đó được phép làm gì? | finance.report.read | Không tự cấp bởi MDM |

Một device được đặt trạng thái **COMPLIANT** có thể vẫn chưa được phép truy cập production database; nhân viên có device compliant nhưng thiếu entitlement vẫn phải bị **Deny**.

## 4. Phân loại device signals theo nguồn

| Nhóm | Tín hiệu minh họa | Nguồn đáng cân nhắc |
|---|---|---|
| **Enrollment/ownership** | MDM enrollment, asset owner, managed state | MDM/UEM, asset/CMDB |
| **System posture** | OS build, patch level, secure configuration | Device management agent |
| **Endpoint protection** | EDR running, malware detection, isolation | EDR/XDR platform |
| **Data protection** | Full-disk encryption, screen-lock policy | UEM/OS attestation |
| **Boot integrity** | Secure Boot, TPM/secure element | Device attestation service |
| **Authentication binding** | Device-bound key, certificate, passkey property | IdP/PKI/platform |
| **Device lifecycle** | Lost, retired, reassigned, quarantined | Asset/MDM/Security |
| **Application health** | App protection policy, managed app status | MAM/EMM, mobile OS |
| **Connection context** | Network, IP reputation, TLS client | Gateway, network security |
| **Runtime threat** | EDR high-severity incident, tamper indication | EDR/SOC detection |
| **Signal freshness** | observedAt, validUntil, lastCheckIn | Signal producer/gateway |

**Không đánh đồng tất cả tín hiệu**: IP/network context là signal của **kết nối**, có thể bổ sung đánh giá device nhưng không chứng minh machine identity. Browser fingerprint cũng không mặc nhiên là chứng cứ thiết bị đáng tin.

## 5. Tư duy về provenance: ai phát ra signal?

Một signal có giá trị khi **nguồn phát và đường truyền có thể xác minh**.

Ví dụ có sự khác nhau lớn giữa:

- Trình duyệt tự gửi **X-Device-Managed: true**.
- Backend nhận một **compliance assertion được ký** từ thành phần có thẩm quyền và audience phù hợp.
- IAM gọi API MDM bằng danh tính dịch vụ được cấp quyền để lấy **observed device posture**.
- EDR gửi sự kiện thiết bị đã bị isolate qua integration đã xác thực.
- Device đưa ra **attestation** liên kết khóa phần cứng, challenge và policy kiểm chứng.

Giá trị từ **header hoặc JSON tự khai** có thể hữu ích cho telemetry nhưng **không nên được nâng thành chứng cứ quản lý thiết bị** khi client có thể tùy ý sửa.

### Câu hỏi kiểm tra provenance

1. Producer là MDM, EDR, gateway, app hay client tự khai?
2. Actor nào có quyền phát hoặc sửa signal?
3. Có chữ ký, authenticated API, mTLS, nonce hoặc binding phù hợp?
4. Signal áp dụng cho **device ID, instance, user, tenant và thời điểm nào**?
5. Nó mô tả observation, assessment hay chỉ là declaration?
6. Gateway có kiểm audience và không cho browser giả header được trust?
7. Có evidence reference và source version phục vụ audit?

**Trusted producer không đồng nghĩa mọi signal do producer phát đều mới hoặc chính xác**. Cần xử lý delayed delivery, lỗi mapping và trạng thái thiết bị bị chuyển owner.

## 6. Managed device: ý nghĩa của MDM/UEM enrollment

**Mobile Device Management (MDM)** và **Unified Endpoint Management (UEM)** có thể quản lý endpoint, đẩy cấu hình, thiết lập policy và báo trạng thái compliance.

Các thuộc tính thường được quản lý:

- Device enrollment và management profile.
- Operating system, model, platform và version.
- Cấu hình khóa màn hình, mã hóa ổ đĩa.
- Certificate hoặc credential liên kết thiết bị.
- Compliance policy, last check-in và remediation status.
- Device ownership và management scope.
- Lost/retired/wipe/quarantine events.
- Ứng dụng được quản lý hoặc khả năng bảo vệ dữ liệu trên mobile.

### Enrollment không phải compliance

**ENROLLED** cho biết thiết bị được ghi danh trong quản lý. **COMPLIANT** thể hiện kết luận theo policy được MDM áp dụng. Một thiết bị có thể enrolled nhưng không compliant vì bị tắt mã hóa, quá hạn patch hoặc agent không check-in.

### Compliance không phải quyền truy cập

MDM có thể đánh giá đúng chính sách endpoint, nhưng IAM/Resource Server vẫn phải kiểm **user status, action, resource, entitlement, session assurance và conditional access rule**.

### Trạng thái MDM cần được diễn giải theo thời gian

Một bản ghi compliant từ ba ngày trước có thể không đủ để cho phép **production privileged access** nếu policy yêu cầu fresh posture. Ngược lại, tín hiệu missing có thể do outage MDM; cần xác định cách xử lý theo mức rủi ro thay vì mặc định **compliant**.

## 7. Endpoint protection: EDR/XDR signal

**Endpoint Detection and Response (EDR)** có thể cung cấp signal liên quan đến trạng thái agent và phát hiện mối đe dọa.

| Signal | Ý nghĩa có thể có | Kiểm tra cần thiết |
|---|---|---|
| **Agent present** | Endpoint có agent được nhận diện | Agent có chạy và healthy? |
| **Agent lastSeen** | Lần cuối producer nhìn thấy agent | Có quá thời hạn freshness? |
| **Threat severity** | Phát hiện được phân loại low/medium/high | Event còn active hay đã remediated? |
| **Device isolated** | EDR đã cô lập endpoint | Isolation có được enforce thực tế? |
| **Tampering detected** | Có dấu hiệu vô hiệu công cụ bảo vệ | Nguồn/thời điểm/coverage |
| **Remediation status** | Threat được xử lý theo workflow | Hệ thống đã được re-evaluate? |

### Ví dụ đánh giá

Một thiết bị đạt MDM compliance nhưng EDR báo **active ransomware detection**. Policy cho tài nguyên nhạy cảm nên cân nhắc **deny hoặc quarantine** thay vì chỉ vì MDM compliant mà Permit.

Ngược lại, một EDR alert cũ đã được xác minh resolved không nên mặc định giữ thiết bị bị cấm vĩnh viễn. Cần **expiry/clearance semantics, workflow và audit**.

**“EDR installed” không tương đương “EDR healthy”**. Tín hiệu còn phụ thuộc vào quality của engine, khả năng telemetry và mức chắc chắn của phát hiện.

## 8. Operating system, patching và security configuration

Những device signals phổ biến khác gồm:

- OS family/version/build, supported/unsupported state.
- Mức bản vá hệ điều hành và thành phần quan trọng.
- Full-disk encryption và key escrow khi policy yêu cầu.
- Screen lock, idle lock và password/PIN policy.
- Local firewall, endpoint protection và cấu hình system hardening.
- Secure Boot, code integrity, protection against unauthorized changes.
- Các dấu hiệu **root/jailbreak** trên mobile theo khả năng nền tảng.
- Managed app/container policy trên thiết bị cá nhân.

### Không chỉ so phiên bản bằng chuỗi

Ví dụ **OS version 12.3** không tự chứng minh patch đầy đủ nếu các kênh update, hotfix và security bulletin khác nhau. Nên ưu tiên **platform compliance assessment có policy version** hoặc thông tin security patch level phù hợp.

### Tách điều kiện hard deny và tín hiệu điều chỉnh rủi ro

Một máy **OS đã hết hỗ trợ** có thể bị cấm truy cập dữ liệu nhạy cảm theo hard policy. Một thiết bị chỉ thiếu một bản cập nhật ít rủi ro có thể được cho **read-only trong thời gian sửa lỗi** nếu risk owner cho phép.

Ngưỡng này **không có một bộ số chung cho mọi tổ chức**. Cần dựa trên data classification, exposure, mức ưu tiên vá và availability.

## 9. Hardware-backed trust: TPM, Secure Boot và attestation

Các thành phần như **TPM, Secure Element, Secure Enclave** hoặc phương thức **hardware-backed key** có thể hỗ trợ bảo vệ khóa và chứng minh thuộc tính thiết bị theo năng lực nền tảng.

### Các khái niệm phân biệt

- **Secure Boot:** cơ chế kiểm soát chuỗi khởi động theo nền tảng.
- **TPM-backed key:** khóa được tạo/giữ và dùng theo chính sách TPM.
- **Attestation:** bằng chứng được kiểm chứng về một thuộc tính thiết bị hoặc môi trường.
- **Device-bound credential:** credential khó tái sử dụng ở thiết bị khác khi binding được thực thi đúng.
- **Measured Boot:** có thể cung cấp measurements để bên kiểm chứng đối chiếu policy.

### Attestation có thể hỗ trợ gì?

Một bên xác minh có thể kiểm rằng **challenge còn mới, bằng chứng được ký bởi khóa/chứng thư được trust, và thuộc tính đo được đáp ứng policy**. Điều này mạnh hơn một trường **secureBoot=true** do browser tự gửi.

### Attestation không cam kết điều gì?

- Không chứng minh mọi phần mềm trên máy hoàn toàn an toàn.
- Không chứng minh **người đang dùng máy** chính là nhân viên được gán thiết bị.
- Không tự cấp quyền **read, write hoặc admin**.
- Không bảo đảm endpoint không thể bị phishing, session hijacking hay bug ứng dụng.
- Không thay thế việc kiểm **attestation root, nonce/audience, expiry và device binding**.

**Hardware-backed signal có thể tăng mức chắc chắn, nhưng vẫn phải đặt trong threat model cụ thể**.

## 10. Device certificate và liên kết identity

Thiết bị có thể được cấp **certificate** qua PKI/MDM và dùng mTLS hoặc một cơ chế xác thực thiết bị được hỗ trợ.

### Vòng đời chính

~~~mermaid
flowchart TD
    ASSET[Device registered with asset/owner] --> BOOT[Bootstrap and enrollment]
    BOOT --> KEY[Generate/protect key]
    KEY --> CA[Certificate issued under CA policy]
    CA --> BIND[Bind device identity to policy]
    BIND --> USE[Present certificate / validate]
    USE --> ROT[Renew/rekey/rotate]
    ROT --> USE
    USE --> RET[Lost / reassigned / retired]
    RET --> REV[Revoke certificate, credentials and grants]
    REV --> VERIFY[Target deny / reconciliation]
~~~

### Cần kiểm tra những gì?

- Certificate do **CA được trust** phát hành và chain hợp lệ.
- SAN/identity khớp thiết bị được phép, không chỉ một CN tự chọn.
- Key Usage/Extended Key Usage phù hợp use case.
- Certificate còn trong thời gian hiệu lực và đáp ứng revocation strategy.
- Khóa riêng được giữ/khóa với thiết bị khi khả thi.
- Binding tới device registry, tenant và owner **không bị lỗi thời**.

Một certificate đúng chữ ký **không tự chứng minh posture hiện tại**. Một thiết bị bị báo mất có thể vẫn trình certificate còn hạn; cần **revocation/registry state/authorization controls** tại nơi thực thi.

## 11. Browser fingerprint và thông tin client tự khai

Browser có thể cung cấp **User-Agent, OS/browser hints, ngôn ngữ, kích thước màn hình, storage identifier** hoặc những tín hiệu fingerprint khác.

### Tại sao phải thận trọng?

- Những thuộc tính có thể bị **thay đổi/giả mạo**.
- Fingerprint có thể **biến đổi khi nâng cấp browser, privacy settings hoặc thiết bị**.
- Hai người dùng có thể có giá trị trùng nhau.
- Mạng VPN, mobile và browser privacy protections có thể làm signal thiếu hoặc lệch.
- Thu thập fingerprint có thể gây **tác động quyền riêng tư** đáng kể.
- Fingerprint không tự chứng minh thiết bị đang được MDM quản lý.

### Vai trò phù hợp

Fingerprint có thể là **tín hiệu phụ trợ cho anomaly detection hoặc risk scoring**, nhưng không nên dùng như **bằng chứng duy nhất** để cấp quyền admin hoặc khẳng định ownership. Nếu cần bảo đảm thiết bị, ưu tiên **nguồn chứng thực có thể xác minh** qua MDM, identity/certificate binding, managed app hoặc attestation khi phù hợp.

## 12. BYOD, unmanaged device và truy cập có giới hạn

**Bring Your Own Device (BYOD)** là tình huống nhân viên hoặc cộng tác viên dùng thiết bị cá nhân. Nó cần chính sách khác với laptop doanh nghiệp.

### Các lựa chọn thường gặp

| Mức tín hiệu | Ví dụ quyết định | Điều kiện |
|---|---|---|
| **Corporate managed + fresh compliant** | Có thể cho phép ứng dụng thông thường | Vẫn kiểm user/entitlement |
| **BYOD có app protection** | Cho phép truy cập qua managed app hoặc browser có kiểm soát | Chặn dữ liệu rời vùng quản lý khi phù hợp |
| **Unmanaged nhưng user MFA mạnh** | Có thể cho low-risk read-only | Không cấp đặc quyền nhạy cảm |
| **Unknown device + high-risk action** | Step-up hoặc Deny theo chính sách | Không tự bỏ qua risk vì MFA |
| **Compromised/lost device** | Block/quarantine, revoke sessions | Có evidence từ nguồn đáng tin |
| **No signal due outage** | Restricted/temporary exception hoặc deny | Có owner, expiry và audit |

### BYOD không nhất thiết phải cài MDM đầy đủ

Một số tổ chức dùng **Mobile Application Management (MAM)**, containerized apps hoặc browser-isolated access để tránh thu quá nhiều dữ liệu thiết bị cá nhân. Phải cân bằng **mục tiêu bảo vệ tài nguyên, privacy và khả năng sử dụng**.

### Người dùng cần biết vì sao bị chặn

Một trải nghiệm tốt thông báo **“thiết bị chưa đáp ứng chính sách bảo mật”** và bước khắc phục an toàn, nhưng không tiết lộ chi tiết nhạy cảm giúp attacker né detection.

## 13. Shared device, kiosk và thiết bị dùng nhiều người

Một thiết bị có thể được nhiều người sử dụng:

- Thiết bị kiosk/front desk.
- Máy POS của cửa hàng.
- Máy vận hành tại nhà máy.
- Máy phòng thí nghiệm.
- Máy dùng chung cho ca trực.

### Rủi ro

**Device compliant không chứng minh ai đang điều khiển máy ở từng thời điểm**. Nếu một user logout không đầy đủ, người dùng tiếp theo có thể thừa hưởng session hoặc quyền local cũ.

### Kiểm soát

1. Phân biệt **device identity** với **human session identity**.
2. Mỗi người phải có phương thức xác thực/authorization theo policy.
3. Hủy user session và token giữa các ca hoặc khi ownership thay đổi.
4. Hạn chế shared admin/local account.
5. Chỉ cho action phù hợp với **device purpose/location/tenant**, nếu các thuộc tính đó đáng tin.
6. Audit cả **deviceId, actorId, sessionRef và target action**.
7. Khi device mất/retire, thu hồi credential thiết bị và kiểm session còn sống.

**Một device có posture tốt không thay thế việc chứng minh user đang hành động**.

## 14. Từ signal thô đến posture assessment

Các nguồn có thể gửi hàng chục trường. Không nên để mọi ứng dụng tự viết lại logic diễn giải tùy tiện.

### Pipeline khái quát

~~~mermaid
flowchart LR
    MDM[MDM/UEM] --> IN[Trusted Signal Ingestion]
    EDR[EDR/XDR] --> IN
    AT[Hardware / OS Attestation] --> IN
    REG[Device Registry / Asset Lifecycle] --> IN
    IN --> VAL[Validate provenance and binding]
    VAL --> AGE[Freshness and conflict handling]
    AGE --> ASSESS[Normalized posture assessment]
    ASSESS --> PDP[Risk / Conditional Access Policy]
    PDP --> ENF[IdP / Gateway / API PEP]
    ENF --> AUD[Audit + Feedback]
~~~

### Phân biệt ba loại dữ liệu

- **Raw observation:** EDR nói agent last seen lúc 09:03.
- **Normalized signal:** edrHealth=HEALTHY, observedAt=09:03, source=edrA.
- **Assessment/decision:** devicePosture=ACCEPTABLE_FOR_STANDARD_ACCESS theo policy v7 lúc 09:05.

Một assessment có **policy version và scope**; không nên dùng assessment dành cho ứng dụng ít rủi ro để cấp **quyền root database**.

### Không tự diễn giải trường boolean

Ví dụ **compliant=true** cần có **issuer/source, policyRef, observedAt, validUntil**. Nếu thiếu, policy engine không có cơ sở đánh giá độ tin cậy và độ tươi.

## 15. Schema minh họa của một device signal

~~~json
{
  "signalId": "sig-device-20261123-0237",
  "schemaVersion": "1.0",
  "deviceId": "device-laptop-718",
  "subjectBinding": {
    "personId": "person-2046",
    "relationshipId": "employment-2046-v2",
    "bindingStatus": "ACTIVE"
  },
  "producer": {
    "system": "enterprise-uem",
    "sourceTrustTier": "MANAGED_API",
    "policyVersion": "endpoint-compliance-v7"
  },
  "observations": {
    "managementState": "ENROLLED",
    "complianceState": "COMPLIANT",
    "diskEncryption": "ENABLED",
    "edrHealth": "HEALTHY",
    "secureBoot": "ENABLED"
  },
  "observedAt": "2026-11-23T09:05:00+07:00",
  "receivedAt": "2026-11-23T09:05:04+07:00",
  "validUntil": "2026-11-23T09:20:00+07:00",
  "integrityReference": "verified-provider-response-ref",
  "riskNotes": []
}
~~~

Đây là **schema nội bộ minh họa**, không phải API chuẩn của một MDM/IdP cụ thể. **sourceTrustTier** là nhãn do tổ chức tự định nghĩa; nó chỉ hữu ích nếu việc xác minh nguồn được triển khai thực sự.

### Trường nên có trong thiết kế thực tế

- Device ID ổn định và namespace/trust domain.
- Source producer và cách xác minh dữ liệu.
- Subject/owner binding nếu policy cần.
- observedAt, receivedAt, expiry hoặc TTL.
- Raw value và normalized value khi có lý do lưu cả hai.
- Assessment/policy version, decision và confidence/quality.
- Error/unknown reason, không ép mọi giá trị thành true/false.
- Provenance/correlation reference đủ để kiểm toán.

**Không dùng device serial, MAC hoặc email làm định danh duy nhất ở mọi hệ thống**; các trường này có thể thiếu, trùng, giả mạo hoặc thay đổi theo platform.

## 16. Freshness: tín hiệu có đúng ở thời điểm truy cập?

Device posture là thông tin biến động:

- 09:00 MDM báo encrypted.
- 09:02 EDR báo phát hiện malware.
- 09:06 IAM nhận MDM compliance vẫn từ 09:00.
- 09:07 user yêu cầu tải dữ liệu Finance.

Nếu chỉ lấy giá trị **COMPLIANT=true** cũ mà bỏ qua EDR incident mới, quyết định có thể sai.

### Cần phân biệt

| Mốc | Nghĩa |
|---|---|
| **observedAt** | Producer thực sự quan sát trạng thái lúc nào |
| **issuedAt** | Assertion hoặc attestation được phát hành lúc nào |
| **receivedAt** | IAM/gateway nhận signal lúc nào |
| **validUntil** | Thời hạn signal có thể được dùng theo policy |
| **evaluatedAt** | Risk engine tính assessment lúc nào |
| **decisionAt** | PDP đưa ra quyết định lúc nào |
| **policyEffectiveAt** | Một policy/JML thay đổi có hiệu lực khi nào |

### Quy tắc độ tươi

- Đặt **max signal age** theo nguồn và risk tier.
- Không lấy **receivedAt** thay **observedAt** để làm mới giả dữ liệu cũ.
- Phân biệt **expired** với **producer unavailable**.
- Dùng source sequence/version để xử lý tín hiệu đến sai thứ tự.
- Đối với privileged operations, có thể yêu cầu **recheck ngay trước action**.
- Không chấp nhận thiết bị đã LOST/RETIRED chỉ vì cache compliant chưa hết TTL.

### TTL là chính sách rủi ro

Không có một TTL cố định đúng cho tất cả MDM, EDR, app và hành động. TTL ngắn giúp thu hẹp cửa sổ trạng thái lỗi thời nhưng tăng phụ thuộc vào API/telemetry; TTL dài cải thiện availability nhưng tăng residual risk.

## 17. Chất lượng tín hiệu: trust, confidence, scope và unknown

Một risk engine nên phân biệt:

1. **Provenance trust:** nguồn phát đã được xác thực mạnh đến đâu?
2. **Measurement confidence:** phép đo phản ánh đúng điều định kiểm không?
3. **Freshness:** dữ liệu còn mới theo policy không?
4. **Binding confidence:** dữ liệu thuộc đúng device/session/user đang truy cập không?
5. **Coverage:** producer kiểm được mọi thành phần cần thiết chưa?
6. **Applicability:** signal có liên quan tới action/resource này không?
7. **Conflict state:** có nguồn khác báo ngược lại không?

### Không có signal không phải trạng thái an toàn

Các trạng thái nên phân biệt ít nhất:

- **PASS:** đáp ứng policy có bằng chứng phù hợp.
- **FAIL:** có bằng chứng không đáp ứng.
- **UNKNOWN:** không đủ bằng chứng để kết luận.
- **STALE:** dữ liệu quá hạn.
- **NOT_APPLICABLE:** tiêu chí không áp dụng với platform/use case.
- **PRODUCER_ERROR:** không lấy được signal do lỗi kỹ thuật.
- **QUARANTINED/RETIRED:** lifecycle state cấm truy cập theo policy.

Một hệ thống gộp UNKNOWN và PASS sẽ dễ bị khai thác bằng cách **ngăn signal tới được engine**. Nhưng gộp mọi UNKNOWN thành permanent Deny cho cả nội dung công khai cũng không luôn phù hợp; mức phản ứng phải theo risk tier.

## 18. Device risk score: cách kết hợp tín hiệu

Một số hệ thống dùng **risk score** hoặc rule-based assessment.

### Mô hình minh họa

~~~text
deviceRisk = weightedIndicators(
    managementState,
    compliance,
    edrThreatState,
    osSupportAndPatch,
    hardwareAttestation,
    deviceLifecycle,
    signalFreshness,
    deviceIdentityBinding
)

accessDecision = evaluate(
    authenticatedUser,
    currentRelationship,
    effectiveEntitlements,
    deviceRisk,
    action,
    resource,
    sessionAssurance,
    timeAndContext
)
~~~

Đây là **giả mã**, không phải chuẩn tính điểm của một nhà cung cấp. **Không lấy tổng điểm để vượt một hard deny** như account Leaver hoặc thiết bị LOST nếu chính sách quy định chặn tuyệt đối.

### Ví dụ điểm chỉ để học

| Tín hiệu | Giá trị | Điều chỉnh rủi ro giả định |
|---|---|---:|
| MDM compliant và fresh | Có | -15 |
| EDR healthy và fresh | Có | -10 |
| OS hết hỗ trợ | Có | +35 |
| EDR high severity active | Có | +50 |
| Attestation thiếu | Unknown | +10 |
| Device lost | Có | **Hard Deny** |

**Các số này hoàn toàn minh họa**, không phải ngưỡng được khuyến nghị hoặc bằng chứng xác suất tấn công. Khi vận hành cần **calibration, kiểm false positives/negatives, explainability, risk owner và policy version**.

### Vấn đề cộng điểm

Những tín hiệu có thể **tương quan**. MDM compliant và diskEncryption=true từ cùng MDM không phải hai bằng chứng độc lập. Cộng cả hai với trọng số cao có thể thổi phồng mức chắc chắn.

## 19. Risk-based access policy: action và resource là trung tâm

Một thiết bị có thể đủ tin cậy để đọc tài liệu nội bộ nhưng chưa đủ cho thao tác đặc quyền.

| Device state | Đọc hướng dẫn nội bộ | Xem báo cáo tài chính | Export dữ liệu khách hàng | Quản trị IAM |
|---|---|---|---|---|
| **Managed, fresh compliant, no active threat** | Có thể Permit | Permit nếu user có quyền | Có thể yêu cầu step-up | Yêu cầu controls nâng cao/JIT |
| **Managed, signal stale** | Có thể limited | Re-evaluate/restricted | Step-up hoặc Deny | Deny tới khi có fresh evidence |
| **Unmanaged BYOD** | Tùy policy | Browser isolation/read-only nếu hỗ trợ | Thường hạn chế hoặc Deny | Deny theo high-risk policy |
| **EDR high severity active** | Block/quarantine theo policy | Deny nhạy cảm | Deny | Deny |
| **Lost/retired device** | Chặn corporate access theo policy | Deny | Deny | Deny |

**Bảng là ví dụ quy tắc**, không phải chuẩn bắt buộc cho mọi doanh nghiệp. Mọi nhánh Permit vẫn phải kiểm **human identity, entitlement, scope/tenant và business authorization**.

### Decision options

- **Permit:** cho phép theo policy.
- **Permit with restriction:** read-only, browser isolation, không download/copy khi enforcement hỗ trợ.
- **Require step-up:** reauthenticate/MFA thêm cho action.
- **Require remediation:** đưa người dùng tới luồng sửa posture hợp lệ.
- **Quarantine:** chỉ cho endpoint cập nhật/EDR/MDM.
- **Deny:** chặn resource/action.
- **Escalate:** review của Security nếu policy không thể tự quyết.

**Không tuyên bố restricted session nếu sản phẩm không enforce được**; một banner “chỉ đọc” không phải biện pháp chặn download ở API.

## 20. Luồng Conditional Access: từ login tới API

~~~mermaid
sequenceDiagram
    participant U as User / Browser
    participant IDP as IdP / Conditional Access
    participant MDM as MDM / EDR Providers
    participant APP as App / Gateway
    participant PDP as Risk and Authorization PDP
    participant RS as Resource Server
    U->>IDP: Login request
    IDP->>IDP: Authenticate user / MFA baseline
    IDP->>MDM: Get trustworthy device signals
    MDM-->>IDP: Bound posture, observedAt, status
    IDP->>IDP: Evaluate device access policy
    alt Device not eligible
        IDP-->>U: Deny / remediation
    else Eligible
        IDP-->>APP: Federation result / session context
        U->>APP: Request sensitive action
        APP->>PDP: User, device context, action, resource
        PDP->>PDP: Check lifecycle, entitlements, posture freshness
        PDP-->>APP: Permit / Step-up / Deny
        APP->>RS: Authorized invocation only
        RS->>RS: Enforce target resource rules
        RS-->>U: Result
    end
~~~

Sơ đồ là **luồng khái niệm**. Một số IdP đánh giá device chỉ tại login hoặc token issuance; một số gateway/app hỗ trợ reevaluation tiếp theo. Cần **xác minh tính năng và phạm vi enforcement của từng sản phẩm**, không giả định mọi IdP liên tục kiểm mỗi API request.

### Chỗ cần audit

- Quyết định device posture dựa trên **signal nào, producer nào, timestamp và policy version nào**?
- User/relationship và target resource có hợp lệ?
- Conditional access đã thực sự yêu cầu step-up/deny?
- API có bảo vệ action nếu phiên đã được tạo trước đó?
- Khi posture đổi, app/token/session có bị reevaluate hoặc revoke theo yêu cầu?

## 21. Device signal và adaptive MFA

**Adaptive authentication** thay đổi yêu cầu xác thực theo risk context. Device signal là một đầu vào, không phải toàn bộ risk.

### Ví dụ

Lan đăng nhập từ laptop doanh nghiệp, security key đã được đăng ký và thiết bị có fresh posture. Hệ thống có thể áp baseline MFA rồi cho phép truy cập theo entitlement.

Sau đó Lan đăng nhập từ thiết bị mới chưa có trusted binding. Hệ thống có thể yêu cầu **step-up** hoặc hạn chế hành động nhạy cảm.

### Những nguyên tắc

1. **MFA thành công không biến thiết bị nhiễm malware thành an toàn.**
2. **Compliant device không cho phép bỏ kiểm user identity**.
3. Chỉ yêu cầu step-up nếu phương thức mới thực sự làm tăng assurance phù hợp risk.
4. Không tin một flag **mfaComplete=true** do ứng dụng/browser tự khai.
5. Tránh biến step-up thành vòng lặp vô tận khi signal nguồn lỗi.
6. Với device LOST/COMPROMISED, có thể cần **hard deny** dù user hoàn thành MFA.
7. Khuyến nghị **phishing-resistant authentication** cho use case nhạy cảm khi phù hợp, nhưng phải kiểm được tại IdP/RP.

### Step-up khác entitlement

Một người thiếu role **finance.payment.approve** vẫn không được phê duyệt thanh toán dù có MFA và thiết bị compliant. **Authentication assurance và authorization là hai điều kiện độc lập**.

## 22. Device signal trong session và token lifecycle

Trong SSO/OIDC/OAuth, cần phân biệt:

| Đối tượng | Điều device policy có thể ảnh hưởng | Giới hạn |
|---|---|---|
| **IdP login** | Cho/không cho tạo phiên đăng nhập | Local app session có thể còn |
| **RP application session** | Session TTL, step-up, local revoke | Không tự đồng bộ khi posture đổi |
| **OAuth access token** | Issuance, scope, expiry hoặc claim khi được hỗ trợ | JWT cũ có thể còn hợp lệ tới exp |
| **OAuth refresh token** | Có thể không cho tiếp tục refresh | Access token đã phát vẫn cần xử lý |
| **PAM privileged session** | Cho phép JIT nếu thiết bị đủ posture | Session mở lâu có thể chưa bị ngắt |
| **mTLS device certificate** | Xác thực device key theo certificate | Certificate không tự cập nhật EDR posture |
| **Browser cookie** | Liên kết local session | Cookie tồn tại không chứng minh risk còn thấp |

### Ví dụ thay đổi trạng thái

09:00 laptop compliant, user nhận SSO session và access token có TTL 60 phút. 09:10 EDR báo **high risk**. Nếu API chỉ kiểm JWT signature và exp mà không có runtime re-evaluation/revocation, token có thể tiếp tục được chấp nhận đến 10:00.

Muốn cắt nhanh hơn cần năng lực phù hợp:

- **Shorter token TTL** theo sensitivity.
- **Session revocation** tại RP/IdP và hỗ trợ truyền sự kiện.
- **Token introspection hoặc centralized state check** khi dùng.
- **Continuous access evaluation / event-driven policy recheck** nếu hệ sinh thái hỗ trợ.
- **Resource-side deny/PEP** dựa trên device/account state hiện hành.
- Đóng **WebSocket/SSH/PAM sessions** có rủi ro.

Không được kết luận “đã chặn mọi truy cập” chỉ từ việc thiết bị chuyển trạng thái **NON_COMPLIANT** trong dashboard MDM.

## 23. Continuous evaluation và giới hạn của cache

Một hệ thống có thể đánh giá device:

- Khi **login**.
- Khi **issue token**.
- Khi **refresh token**.
- Khi **mở privileged session**.
- Khi **gọi action nhạy cảm**.
- Theo **event từ EDR/MDM**, có hoặc không có polling.
- Khi **thiết bị được đánh dấu LOST/RETIRED**.
- Khi **relationship JML** thay đổi.

### Các vấn đề thường gặp

- Posture cache chưa hết TTL nên không thấy incident mới.
- Event producer đến chậm hoặc sai thứ tự.
- App giữ session dài hạn dù IdP đã chặn login mới.
- API không có cách hỏi lại device state.
- Session được đánh dấu active từ trước khi device đổi chủ.
- Một workload khác dùng chung device ID/path làm sai binding.

### Phiên dài cần biện pháp riêng

WebSocket, SSH/RDP, database connection và PAM sessions có thể tiếp tục sau login. Với các action nhạy cảm, hệ thống cần **reauthorization trên action hoặc connection termination** theo policy, không chỉ kiểm device ở handshake đầu tiên.

## 24. Device context trong RBAC, ABAC và PBAC

**RBAC** cho biết người dùng giữ role nào. **ABAC/PBAC** có thể thêm điều kiện **device posture, session assurance, resource classification, time và tenant**.

### Policy khái niệm

~~~text
permit if
    identity.relationshipState == ACTIVE
    and identity.hasPermission(action, resource)
    and subject.tenantId == resource.tenantId
    and device.bindingVerified
    and device.lifecycleState == ACTIVE
    and device.signal.producerTrusted
    and device.signal.isFreshFor(resource.riskTier)
    and device.complianceState == COMPLIANT
    and device.activeCriticalThreat == false
    and session.assurance >= requiredAssurance(action)
    and not violatesSoD(subject, action, resource)
else
    denyOrStepUpByPolicy
~~~

Đây là **giả mã**: các thuộc tính ở ví dụ phải thực sự được lấy từ nguồn đáng tin. Cụm **device.signal.isFreshFor** chỉ có ý nghĩa khi hệ thống xác định freshness theo source/TTL/risk tier.

### Không cho device score vượt hard deny

Một user **LEAVER** không được được phép truy cập chỉ vì dùng laptop công ty mới cập nhật. Một role không đủ **payment.approve** cũng không được “bù điểm” bằng TPM attestation.

### Kiểm object-level authorization

Nếu API chỉ kiểm device và role ở endpoint **GET /reports/{id}** nhưng không kiểm người dùng có quyền trên **report cụ thể**, vẫn có rủi ro truy cập chéo tenant/BOLA. Device trust không thay thế authorization.

## 25. Device signals và Zero Trust

**Zero Trust** nhấn mạnh không mặc định tin chỉ vì một request ở mạng nội bộ. Device signal có thể giúp đánh giá **ngữ cảnh truy cập**, nhưng không phải một “nhãn trusted” cho phép vượt các bước kiểm.

### Một quyết định cần có

~~~text
Request:
  subject = Lan / relationship ACTIVE
  action = finance.report.export
  resource = report-tenantA-sensitive
  device = device-laptop-718
  deviceEvidence = trusted + fresh + policy compliant
  session = MFA assurance recent
  entitlement = REPORT_EXPORT approved + in scope

Decision:
  Permit only if all mandatory guards pass;
  otherwise Step-up, Restrict or Deny by policy.
~~~

### Những điều không nên làm

- **Allow all from corporate VPN** vì “đã ở trong công ty”.
- **Allow all from MDM enrolled** vì “thiết bị thuộc công ty”.
- Cấp **admin role** vì device có TPM.
- Tin **User-Agent** để phân biệt laptop an toàn.
- Giữ session vô hạn vì login đầu tiên từng có posture tốt.

**Không có bất kỳ device signal nào chứng minh rủi ro bằng 0**. Quyết định cuối cùng phải giới hạn theo subject, resource, action và context.

## 26. Joiner: đăng ký thiết bị cùng danh tính người mới

Một Joiner có thể được chuẩn bị **account, authenticator và thiết bị** trước effectiveAt. Audit cần phân biệt **đã cấp máy** với **đã được phép dùng ứng dụng production**.

### Luồng tham khảo

~~~mermaid
flowchart TD
    HR[HRIS: Joiner] --> ID[Create identity and relationship]
    ID --> PROOF[Identity proofing + authenticator enrollment]
    PROOF --> ASSET[Assign corporate device]
    ASSET --> MDM[UEM enrollment and compliance policy]
    MDM --> BIND[Bind device to person and scope]
    BIND --> ACCESS[IdP conditional access evaluation]
    ACCESS --> PEP[Resource authorization]
    PEP --> AUD[Audit evidence]
~~~

### Bằng chứng cần có

1. HRIS/contract source và **effectiveAt**.
2. Immutable personId/relationshipId.
3. Asset/device record, owner/team và management state.
4. Authenticator enrollment và device binding đúng người.
5. MDM/EDR compliance assessment **còn mới**.
6. Quyền baseline theo job/department; quyền nhạy cảm có approval.
7. IdP session và target app truy cập đúng thời điểm.
8. Audit/notification về gán thiết bị và policy.

### Cẩn thận

Một thiết bị được MDM đăng ký nhưng chưa được giao cho Joiner hợp lệ không nên tự mở quyền **Finance Portal**. Đồng thời, Joiner có thể được quyền truy cập onboarding qua một phương án hạn chế mà không cần quyền production.

## 27. Mover: thay đổi vai trò, team hoặc thiết bị

Mover có thể làm thay đổi **người được dùng device**, **loại dữ liệu được phép truy cập** hoặc **mức chính sách bảo mật yêu cầu**.

### Ví dụ

Lan chuyển từ Sales sang Finance. Laptop cũ vẫn compliant, nhưng Finance yêu cầu **mức kiểm soát cao hơn** cho action export dữ liệu. Việc chuyển vai trò cần:

- Gỡ role/entitlement Sales không còn căn cứ.
- Tính Finance baseline và quyền đặc biệt theo approval.
- Kiểm thiết bị có đạt **Finance device policy** không.
- Cập nhật device ownership hoặc asset assignment nếu chuyển đội.
- Re-evaluate/rotate session context theo policy.
- Kiểm target apps không dùng stale role hoặc stale device decision.
- Audit cả **old action Deny** và **new action Permit** ở phạm vi phù hợp.

### Không coi compliance là bất biến theo role

Một laptop đạt policy **Sales Standard** không tự có nghĩa đạt **Finance Sensitive Data**. Compliance phải đi cùng **policy reference, risk tier và phiên bản**, tránh dùng một boolean chung cho mọi use case.

### Nguy cơ hai miền quyền cùng tồn tại

Trong lúc Mover, người dùng có thể giữ đồng thời Sales Export và Finance Payment Approver; **device compliant không giải quyết xung đột SoD**. IAM vẫn phải kiểm toxic combinations và thời gian chuyển tiếp.

## 28. Leaver: thu hồi access dù thiết bị chưa được trả

**Leaver** là điểm rất quan trọng: một nhân viên nghỉ việc có thể vẫn còn laptop công ty, cookie đăng nhập và API token.

### Quy trình cần kết hợp

1. HRIS/contract xác nhận relationship **ENDED** và effectiveAt.
2. IdP chặn login mới, revoke sessions theo chính sách.
3. IAM/IGA deprovision quyền tới SaaS/SCIM/cloud/PAM.
4. MDM/asset workflow cập nhật thiết bị: **return required, lost, quarantine hoặc reassignment**.
5. Xử lý device certificates, managed app credentials và các khóa người cũ có thể dùng.
6. Revoke refresh tokens, local sessions, PAT/API keys theo phạm vi.
7. Resource server kiểm lifecycle/authorization state, không chỉ device compliance.
8. Reconciliation kiểm **action Deny** sau effectiveAt trong phạm vi quan sát.
9. Ghi finding khi thiết bị chưa trả hoặc một SaaS không hỗ trợ logout/revocation.

### Một sai lầm thường gặp

Thiết bị tiếp tục báo **MDM COMPLIANT** sau khi nhân viên Leaver. Nếu hệ thống kiểm **device compliant OR active employee**, logic sai này có thể Permit. Cần bảo đảm **active relationship AND entitlement AND device policy**, không phải OR.

### Thu hồi máy khác thu hồi quyền

**Remote wipe** hoặc **device lock** có thể hữu ích khi policy/consent/quyền quản trị cho phép, nhưng không tự vô hiệu mọi token đã được sao chép hoặc SaaS PAT nằm ngoài máy. Phải thu hồi tại **issuer/target**.

## 29. Rejoiner, chuyển giao thiết bị và identity reuse

Khi người cũ quay lại hoặc thiết bị chuyển cho người khác:

- **Không tái sử dụng session/token** từ relationship đã kết thúc.
- Xác định device registry đang gắn với người/team nào theo thời gian.
- Xóa/thu hồi những credential và profile người dùng cũ theo policy.
- Thực hiện quy trình reset/reprovision thiết bị khi cần.
- Re-enroll MDM, certificate và posture binding cho người nhận mới nếu áp dụng.
- Cấp entitlement từ **relationship mới** và approval hiện hành.
- Kiểm device certificate/key không cho giữ access của owner cũ.
- Đối soát asset chain of custody và inventory.

### Identity binding có thời hạn

Một deviceId có thể giữ nguyên sau khi được chuyển người, nhưng **binding device→person** phải có khoảng hiệu lực và provenance. Audit nếu chỉ ghép deviceId với owner hiện tại có thể **gán nhầm thao tác lịch sử** của người dùng trước.

## 30. Contractor, guest và thiết bị không thuộc tổ chức

Khách và nhà thầu có thể làm việc từ thiết bị bên thứ ba:

- Không phải lúc nào enterprise MDM cũng quản lý được endpoint.
- Có thể dùng **virtual desktop, browser isolation, app protection hoặc privileged access gateway**.
- Chính sách quyền phải gắn với **contract status, sponsor và expiry**.
- Device assessment phải tách rõ **NOT_MANAGED** và **UNSAFE**.
- Phải tránh thu thông tin thiết bị cá nhân quá mức cho mục đích IAM.
- Với dữ liệu rất nhạy cảm, policy có thể yêu cầu thiết bị do tổ chức quản lý.

### Không cố giả lập “corporate compliant”

Không nên cho contractor tự đặt header **compliant=true** để vượt chính sách. Nếu không có signal đáng tin, hãy áp **limited access hoặc workflow thay thế có kiểm soát**, thay vì tạo trường chứng thực giả.

## 31. Non-human identities và device signals

Workload, service account và machine identity không hoạt động giống một người dùng browser nhưng có thể liên quan **machine/device posture**.

### Ví dụ

- Cloud VM có **instance identity** và trạng thái hardening.
- Container host có **node posture** và workload attestation.
- CI/CD runner có **runner trust, isolation, image integrity**.
- IoT gateway có **device certificate, TPM và firmware version**.
- Service mesh sidecar dùng **SPIFFE/SVID/mTLS**.

### Ranh giới quan trọng

**Host compliant không chứng minh mọi container trên host an toàn.** Mỗi workload có thể cần identity riêng, deployment provenance và policy resource/action.

**Workload identity không phải human device session**. Không tự áp yêu cầu “browser MFA” cho machine-to-machine; thay vào đó dùng **attestation, short-lived credentials, mTLS, token audience/scope và owner governance** phù hợp.

### Owner JML

Khi owner của workload Leaver, cần gỡ **human admin access**, chuyển ownership và rotate secrets nếu rủi ro yêu cầu. Không được tự xóa production workload đang hợp lệ, nhưng cũng không để instance/role cũ tiếp tục cấp credential sau **workload Retire**.

## 32. IdP, SSO, SCIM và tích hợp device posture

### IdP / Conditional Access

IdP có thể kiểm device posture tại **authentication hoặc token issuance**, nếu được tích hợp với MDM/EDR hoặc chứng cứ tin cậy khác. Nhưng phải kiểm khả năng thực tế của sản phẩm về **refresh, continuous reevaluation và session revocation**.

### SSO

Một user có thể có:

- IdP SSO session.
- Finance Portal local session.
- CRM local session.
- OAuth access/refresh tokens.
- PAM privileged session.

Nếu MDM đổi trạng thái **NON_COMPLIANT**, chỉ chặn login mới tại IdP **không tự chặn các phiên/credential đang sống** ở mọi RP/SP.

### SCIM

SCIM thường đồng bộ **User/Group**. Nó không phải giao thức thu thập posture hay chứng thực TPM và **không tự thu hồi session ở mọi SaaS**. Có thể có integration dùng dữ liệu compliance hoặc custom API, nhưng cần phân biệt với semantics chuẩn của SCIM.

### API enforcement

Các ứng dụng nhạy cảm có thể cần **resource-side authorization** kiểm device context hiện hành, không chỉ nhận một claim **deviceTrusted=true** đã phát rất lâu trong token.

## 33. Tấn công, giả mạo và bypass device signal

| Rủi ro | Cách biểu hiện | Kiểm soát |
|---|---|---|
| **Self-reported spoofing** | Browser gửi managed=true | Trusted producer/authentication |
| **Header injection** | Client tự gửi X-Device-ID | Gateway strip/overwrite, backend trust boundary |
| **Device ID cloning** | Copy identifier sang máy khác | Hardware key/attestation/binding khi phù hợp |
| **Stolen device certificate** | Private key bị trích xuất | Key protection, revoke/rotate |
| **Stale compliance** | Cache giữ compliant sau incident | TTL/invalidations/event reevaluation |
| **EDR bypass/tamper** | Agent bị tắt hoặc giả healthy | Tamper-protection, health freshness, separate telemetry |
| **Compromised managed device** | Máy MDM compliant nhưng malware hoạt động | EDR, runtime monitoring, least privilege |
| **Session hijacking** | Cookie/token đánh cắp dùng từ máy khác | Session binding/revocation/step-up theo khả năng |
| **Token replay** | Bearer token dùng lại | Audience, TTL, sender constraint khi có |
| **Cross-tenant device binding** | Device A map sai tenant B | Immutable IDs, tenant-scoped binding |
| **JML stale event** | Event Mover cũ tạo lại access sau Leaver | SourceVersion/fencing |
| **Policy downgrade** | Attacker đổi high-risk rule thành low-risk | SoD, change approval, audit |
| **MDM outage fail-open** | Không có posture vẫn Permit admin | Risk-tier fallback policy |
| **Shared kiosk session leakage** | Người khác dùng session cũ | Per-user auth/session termination |
| **Privacy abuse** | Device tracking ngoài mục đích | Minimization, transparency, retention |
| **Attestation replay** | Bằng chứng cũ được trình lại | Nonce/challenge, expiry, key binding |
| **False compliant mapping** | Dữ liệu thuộc device khác | Producer deviceId correlation and verification |
| **Tampered connector** | Integration trả kết quả giả | Connector IAM, independent audit, trust controls |

### Không có một “device signal hoàn hảo”

Chính sách phải giả định **producer có thể lỗi, telemetry có thể trễ và endpoint có thể bị chiếm**. Defense-in-depth giảm tác động: **least privilege, resource authz, MFA, token/session controls, EDR, network egress, audit và response**.

## 34. Conflict resolution: khi các nguồn báo ngược nhau

Ví dụ:

- MDM báo **COMPLIANT lúc 09:00**.
- EDR báo **ACTIVE_CRITICAL_THREAT lúc 09:05**.
- IdP cache giữ deviceTrusted từ 08:55.
- Device registry báo **LOST lúc 09:06**.

Một engine hợp lý không nên lấy giá trị **COMPLIANT** gần nhất trong một nguồn và bỏ qua event rủi ro cao từ nguồn khác.

### Quy tắc diễn giải

1. **Lifecycle hard deny** (lost/retired/quarantined) có thể ưu tiên theo policy.
2. Active critical threat cần phản ứng phù hợp risk.
3. So sánh **scope và observedAt** của từng nguồn.
4. **Không gộp FAIL thành PASS** chỉ vì producer khác báo healthy.
5. Phân biệt **one signal recovered** với **overall device cleared**.
6. Nếu hai device IDs có thể trỏ cùng machine, cần giải quyết identity mapping.
7. Có review/exception workflow khi evidence mâu thuẫn.
8. Ghi đầy đủ **decision reasoning và các signal đã tham chiếu**.

### Ví dụ quy tắc khái niệm

~~~text
if device.lifecycle in {LOST, RETIRED, QUARANTINED}:
    return DENY
if edr.activeCriticalThreat == true and edr.provenanceValid:
    return DENY_SENSITIVE_ACTIONS
if requiredEvidence.isMissingOrStale:
    return RESTRICT_OR_DENY_BY_RESOURCE_RISK
if device.management == ENROLLED
   and compliance == COMPLIANT
   and edr == HEALTHY
   and bindingVerified:
    return ELIGIBLE_FOR_FURTHER_AUTHORIZATION
return EVALUATE_EXPLICIT_POLICY
~~~

Đây là giả mã; trạng thái **ELIGIBLE** vẫn phải đi qua **user/permission/SoD**. Không phải mọi trường hợp thiếu EDR đều cần chặn mọi ứng dụng, nhưng action nhạy cảm không được mặc định Permit thiếu chứng cứ bắt buộc.

## 35. Outage, fallback và exception workflow

Khi MDM/EDR/IdP hoặc risk engine không khả dụng, cần kế hoạch theo **sensitivity**.

| Sự cố | Không nên | Hướng phù hợp |
|---|---|---|
| MDM API timeout | Tự coi tất cả devices compliant | Sử dụng signal còn hạn hoặc policy Unknown |
| EDR producer outage | Bỏ mọi endpoint health requirement | Restricted/deny high-risk, alert |
| IdP Conditional Access lỗi | Dùng shared admin account | Recovery path được phê duyệt |
| Device vừa mất kết nối | Khóa mọi app vĩnh viễn không remediation | Grace/limited access theo risk khi policy cho phép |
| Cần khắc phục posture | Cấp full production access để cập nhật EDR | Quarantine network/portal |
| Break-glass cần thiết | Cho bypass audit/MFA không kiểm soát | JIT, dual control, owner, expiry, post-review |

### Exception cần có

- Identity/user và device scope cụ thể.
- Business need và risk reason.
- Resource/action/time window.
- Risk owner và approver độc lập khi policy yêu cầu.
- Compensating controls: managed browser, read-only, session recording, MFA mạnh.
- Tự hết hạn và cơ chế revoke.
- Audit reason, policyVersion và negative tests sau expiry.

**Một exception chưa duyệt hoặc quá hạn không được tự chuyển thành Permit chỉ vì producer đang lỗi**.

## 36. Audit device signal và risk decision

Một audit event nên cho biết **quyết định nào được đưa ra với bằng chứng nào**, không log raw secrets hoặc dữ liệu thiết bị thừa.

### Schema minh họa

~~~json
{
  "eventId": "risk-access-20261123-0142",
  "eventType": "RiskBasedAccessEvaluated",
  "occurredAt": "2026-11-23T09:15:00+07:00",
  "subjectId": "person-2046",
  "relationshipId": "employment-2046-v2",
  "deviceId": "device-laptop-718",
  "deviceBindingVersion": 5,
  "resourceId": "finance-report-01",
  "action": "report.export",
  "deviceAssessment": {
    "management": "ENROLLED",
    "compliance": "COMPLIANT",
    "edrStatus": "HEALTHY",
    "producerRefs": ["uem-event-899", "edr-event-201"],
    "lastObservedAt": "2026-11-23T09:10:00+07:00",
    "assessmentVersion": "device-risk-v9"
  },
  "authAssurance": "MFA_PHISHING_RESISTANT",
  "policyVersion": "finance-export-conditional-v4",
  "decision": "STEP_UP_REQUIRED",
  "reasonCodes": ["SENSITIVE_ACTION"],
  "correlationId": "corr-risk-7c62"
}
~~~

Đây là **schema minh họa**. Các trường **authAssurance** hoặc **compliance** chỉ có ý nghĩa khi mapping từ dữ liệu producer có thể xác minh; không phải bằng chứng tự thân.

### Audit nên ghi

- **Subject, device, target, action, tenant và session audit reference**.
- Sources, signature/provenance reference, observedAt/receivedAt và status.
- Policy version, rule, risk tier, decision và reason codes.
- Step-up challenge/outcome tách khỏi authorization.
- Device lifecycle event và JML source version.
- Target action **Permit/Deny sau quyết định**, khi quan sát được.
- Exception, remediation owner và validity window.

**Audit signal khác audit enforcement**: PDP trả DENY nhưng API bỏ qua vẫn là lỗi. Cần audit cả **decision lẫn kết quả resource server** cho đường nhạy cảm.

## 37. Quyền riêng tư và tính công bằng trong thu thập device signal

Device telemetry có thể tiết lộ **vị trí tương đối, thói quen làm việc, ứng dụng cài đặt, health/security events và thông tin thiết bị cá nhân**. Cần áp mục đích và kiểm soát phù hợp.

### Nguyên tắc

1. Chỉ thu **dữ liệu thực sự cần** cho quyết định rủi ro.
2. Ưu tiên **posture assessment** thay vì gửi toàn bộ danh sách ứng dụng cá nhân nếu không cần.
3. Cho người dùng biết yêu cầu quản lý thiết bị và hậu quả của policy.
4. Có ranh giới khác nhau cho **corporate device, BYOD, contractor và shared kiosk**.
5. Hạn chế quyền đọc device metadata và log.
6. Định nghĩa retention, deletion và legal hold theo yêu cầu áp dụng.
7. Giảm khả năng sử dụng fingerprint để theo dõi ngoài mục đích.
8. Kiểm **false positives** gây khóa người dùng hợp lệ, bao gồm người dùng có hạn chế phần cứng hoặc platform không được hỗ trợ.
9. Có remediation/appeal path và support thực tế.
10. Không tự dùng thông tin device risk để suy ra hành vi cá nhân không liên quan.

### Không đánh đồng quyền riêng tư với bỏ bảo mật

Một giải pháp có thể chỉ gửi **“meets baseline security policy” cùng provenance và expiry** thay vì xuất mọi dữ liệu endpoint, khi risk engine vẫn có đủ chứng cứ để quyết định.

## 38. Metrics và dashboard vận hành

| Metric | Ý nghĩa | Lưu ý |
|---|---|---|
| **Managed device coverage** | Tỷ lệ devices thuộc population được quản lý | Không nói lên mức an toàn |
| **Fresh compliant posture rate** | Tỷ lệ có assessment hợp lệ theo policy | Cần quality/observedAt |
| **Signal ingestion lag** | Độ trễ producer → IAM | Lag cao kéo dài rủi ro |
| **Stale/unknown signal share** | Tỷ lệ thiếu hoặc hết hạn | Không tự coi là compromised |
| **Active critical-threat devices** | Devices có incident chưa giải quyết | Cần filter severity và dedup |
| **Policy deny/step-up rate** | Tác động của conditional access | Có false positives |
| **Remediation completion time** | Thời gian từ blocked tới đáp ứng posture | Phụ thuộc support và platform |
| **Leaver bound-device backlog** | Thiết bị chưa thu hồi/chuyển giao sau Leaver | Không đồng nghĩa session còn Permit |
| **Lost-but-session-active** | Thiết bị LOST còn session/token usable | High-risk investigation |
| **Mover stale device binding** | Device→person/team mapping không cập nhật | Cần asset readback |
| **Risk exception inventory** | Ngoại lệ còn hiệu lực/đã quá hạn | Có risk owner/expiry |
| **Target authorization bypass** | API Permit dù device decision Deny | Ưu tiên security response |
| **Device evidence source coverage** | Producer nào hỗ trợ app nào | Thiếu sản phẩm legacy |
| **Token/session revoke latency** | Từ posture high-risk tới Deny thực tế | Khác MDM dashboard latency |
| **Reconciliation findings age** | Sai lệch chưa xử lý | Không đóng theo ticket Done |
| **Privacy data minimization checks** | Telemetry/log có đúng field cần? | Ngăn thu ngoài mục đích |

### Tránh vanity metrics

**100% devices “managed”** không chứng minh chúng cập nhật, không bị malware, hoặc IAM đã chặn quyền người Leaver. Ưu tiên **freshness, effective deny, ownership, incident response và end-to-end coverage**.

## 39. Kiểm thử Device signal và policy

| Test case | Điều kiện | Kết quả mong đợi |
|---|---|---|
| **Trusted fresh managed device** | MDM compliant, EDR healthy | Qua device guard; quyền vẫn kiểm riêng |
| **Self-reported managed header** | Browser tự khai compliant | Không dùng làm chứng cứ tin cậy |
| **Unknown device** | Không có device identity binding | Restrict/step-up/deny theo risk |
| **Stale signal** | observedAt quá max age | Không tự coi COMPLIANT |
| **Producer error** | MDM timeout | Áp fallback theo risk-tier policy |
| **High-severity EDR threat** | EDR trusted báo active incident | Chặn sensitive actions theo policy |
| **Conflicting signals** | MDM compliant, EDR threat active | Đánh giá precedence, không bỏ threat |
| **OS unsupported** | OS không đạt baseline | Deny/restrict theo policy |
| **Disk encryption missing** | Device không đáp ứng data protection | Chính sách tương ứng được thực thi |
| **Hardware attestation replay** | Assertion cũ/challenge sai | Reject |
| **Device cert wrong issuer** | Trust domain sai | Reject |
| **Device cert expired/revoked** | Không còn hợp lệ | Reject theo validation strategy |
| **Device ID copied** | Cùng ID trên máy khác | Binding/attestation phát hiện khi khả thi |
| **Valid device, wrong user** | User không có entitlement | Deny |
| **Valid device, Leaver user** | Relationship ENDED | Deny mọi action trái policy |
| **Valid device, wrong tenant** | User tenant A đọc resource B | Deny |
| **MFA passed, device LOST** | Device lifecycle hard deny | Deny |
| **Compliant but insufficient role** | User thiếu payment.approve | Deny |
| **Mover** | New sensitive role, posture cũ | Re-evaluate policy mới |
| **Rejoiner** | Old relationship/device binding | Không hồi sinh session/permission |
| **Shared kiosk** | User A logout, user B vào | Session A không được dùng |
| **BYOD limited path** | Unmanaged device đọc low risk | Chỉ phạm vi được policy cho phép |
| **CI runner trust** | Untrusted fork muốn prod secrets | Deny |
| **Session preexisting** | EDR risk cao sau login | Revoke/re-evaluate theo capability |
| **JWT stale claims** | Token phát trước posture change | Resource action Deny theo policy target |
| **WebSocket open** | Device LOST trong lúc kết nối | Close/revalidate theo yêu cầu |
| **Event reordering** | Old compliant event sau LOST | Version/fencing chống hồi sinh |
| **Policy exception expired** | Temporary bypass hết hạn | Deny/re-evaluate |
| **Audit** | Device decision Deny | Có evidence, không log raw tokens |
| **Target bypass** | IdP Deny, API permit qua đường khác | Phát hiện, không ghi PASS |

### Các lớp test

1. **Producer verification:** signature, trust chain, API auth và issuer mapping.
2. **Data quality:** schema, missing/null, out-of-order, conflict, freshness.
3. **Policy unit tests:** hard deny, risk thresholds và step-up rules.
4. **Browser/mobile tests:** cookie/session/token và device binding.
5. **End-to-end authorization tests:** role, tenant, resource, target PEP.
6. **JML tests:** Joiner, Mover, Leaver, Rejoiner.
7. **Non-human tests:** workload/runner/device posture và permissions.
8. **Failure injection:** MDM/EDR outage, PDP unavailable, cache stale.
9. **Adversarial tests:** forged headers, attestation replay, stolen cookie/certificate.
10. **Audit/privacy tests:** correlation, retention và secret redaction.

## 40. Runbook khi Device signal gây chặn nhầm hoặc còn đường bypass

### A. User có device công ty nhưng bị báo non-compliant

1. Xác định deviceId/owner, target resource và policy decision.
2. Kiểm signal từ **MDM/UEM và EDR**, không tin screenshot **compliant** một mình.
3. Kiểm enrollment, last check-in, observedAt/validUntil và policy version.
4. Kiểm OS patch/encryption/agent health hoặc attestation cần thiết.
5. Kiểm device binding có đúng user/tenant không.
6. Hướng dẫn remediation qua kênh được tổ chức phê duyệt.
7. Sau khi producer cập nhật, re-evaluate và kiểm action thực tế.
8. Không giải quyết bằng cách cấp wildcard bypass cho mọi users/devices.

### B. Device bị mất hoặc nghi compromise

1. Nhận bằng chứng asset LOST, EDR incident hoặc tín hiệu Security có thẩm quyền.
2. Ưu tiên chặn access nhạy cảm tại IdP/gateway/PEP.
3. Revoke device-bound credentials/certificates theo khả năng.
4. Xử lý IdP/RP sessions, OAuth refresh/access tokens và PAM/SSH connections.
5. MDM lock/wipe theo policy, quyền quản trị và điều kiện kỹ thuật.
6. Kiểm token/credential có thể đã bị copy ra ngoài.
7. Ghi incident scope, audit trail và remediation.
8. Negative test các action trong phạm vi chứng thực trước khi đóng.

### C. MDM/EDR outage làm nhiều người không đăng nhập được

1. Xác định source unavailable, error rate và freshness của last-known-good.
2. Phân loại ứng dụng theo **risk tier**; giữ hard denies.
3. Chỉ áp exception/bounded cache theo policy đã duyệt.
4. Đặt owner, expiry, scope và enhanced audit cho exception.
5. Không mở toàn bộ production admin chỉ để giảm ticket.
6. Khi source phục hồi, revalidate devices và thu hồi exceptions.
7. Audit mọi action/decision trong outage window.

### D. Leaver vẫn truy cập được từ máy đã thu hồi

1. Lấy HRIS Leaver effectiveAt, relationshipId và sourceVersion.
2. Kiểm IdP disable/account state, local SaaS sessions và token issuers.
3. Kiểm thiết bị còn MDM enrolled/compliant không—**điều này không quyết định quyền người cũ**.
4. Revoke refresh/PAT/API keys, PAM/JIT, VPN/SSH và các sessions phù hợp.
5. Kiểm backend policy đã chặn account/relationship cũ.
6. Negative test action ở API và resource quan trọng.
7. Ghi finding có owner nếu target không có API readback/logout.
8. Chỉ kết luận trong phạm vi đã chứng minh **Deny**.

### E. Device signal bị giả mạo hoặc binding sai

1. Bảo toàn event IDs, provenance và thời gian.
2. Kiểm issuer, signature/API authentication, deviceId mapping và trust boundary.
3. Ngăn client gửi/ghi đè metadata được backend tin.
4. Chặn các assertions/tokens bị compromise; rotate keys nếu cần.
5. Đối chiếu MDM/EDR/asset source bằng nguồn độc lập khi khả thi.
6. Sửa bug mapping và kiểm cross-tenant.
7. Chạy replay/forged-header negative tests.
8. Audit các action đã được Permit trong cửa sổ rủi ro.

## 41. Tình huống xuyên suốt: Risk-based Access tại Finance Portal

Giả sử doanh nghiệp dùng **HRIS, IdP có SSO/MFA, MDM, EDR, Finance Portal, CRM, SCIM và PAM**.

### Giai đoạn 1 — Joiner và gán thiết bị

Lan bắt đầu làm việc tại Sales. HRIS phát Joiner, IAM tạo personId/relationshipId và baseline role. IT gán laptop **device-laptop-718**, enrollment vào MDM và bật EDR. Đến effectiveAt, Lan đăng nhập bằng MFA; IdP nhận posture fresh từ MDM/EDR và ứng dụng chỉ Permit action có entitlement.

### Giai đoạn 2 — Truy cập từ thiết bị cá nhân

Lan mở Finance Portal từ tablet riêng chưa được quản lý. Tín hiệu managed không có nguồn tin cậy. Với resource low-risk, chính sách có thể cho read-only trong managed browser nếu hỗ trợ; với **customer.export**, policy yêu cầu thiết bị được quản lý và fresh compliance nên Deny. MFA không tự thay thế device requirement.

### Giai đoạn 3 — Phát hiện EDR incident

Laptop công ty đang compliant nhưng EDR báo một active high-severity detection. Event được gửi tới risk engine; chính sách chặn Finance sensitive actions và yêu cầu remediation. Một JWT đã phát trước đó có thể còn sống, nên Finance API hoặc gateway cần áp **resource-side deny/reevaluation** theo khả năng, không chỉ chặn login mới.

### Giai đoạn 4 — Remediation

Security xử lý incident, xác minh EDR health và producer phát fresh assessment. IAM không nên coi “EDR healthy” do user tự khai là clearance. Sau re-evaluation và đáp ứng permission hiện hành, Finance Portal có thể khôi phục access đúng scope.

### Giai đoạn 5 — Mover sang Finance

Lan chuyển vai trò Sales → Finance. Role Sales Export bị gỡ, Finance Reader được tính theo chính sách mới. Finance Payment Approval cần approval và thiết bị posture mạnh hơn. Một laptop vẫn compliant theo **Sales policy** không tự đủ điều kiện Finance. Audit ghi sourceVersion, assessmentVersion và target action outcomes.

### Giai đoạn 6 — Leaver và thiết bị chưa trả

HRIS đánh dấu Lan Leaver hiệu lực ngay, nhưng laptop vẫn ở nhà Lan và tiếp tục gửi **COMPLIANT**. IdP chặn login và revoke sessions; IAM thu hồi quyền Finance qua SCIM/API, xử lý token, vault và PAM. API không Permit chỉ vì device vẫn compliant. IT theo dõi asset return và xử lý key/device lifecycle riêng.

### Giai đoạn 7 — Chuyển laptop cho nhân viên khác

Sau khi nhận thiết bị, IT reset/reprovision theo policy, gỡ credentials của Lan và cập nhật device→person binding. Nhân viên mới cần identity/relationship, device enrollment và authorization riêng. Các audit events lịch sử vẫn gắn Lan đúng thời điểm chứ không bị ghi lại theo owner mới.

### Bài học

**Device signal có giá trị khi nó đến từ nguồn đáng tin, được gắn đúng thiết bị, còn mới và được dùng cùng danh tính, entitlement, resource và session.** Device compliant giúp giảm một phần rủi ro nhưng không tự bảo vệ khỏi malware, không tự cấp quyền và không thay thế thu hồi truy cập theo **Joiner–Mover–Leaver**.

## 42. Checklist thiết kế Device signal cho Risk-based Access

1. **Định nghĩa:** đã phân biệt device signal, identity, posture, compliance và attestation?
2. **Nguồn dữ liệu:** MDM, EDR, hardware/OS và asset registry có owner?
3. **Trust:** producer được xác thực, không tin browser self-report?
4. **Binding:** deviceId map đúng machine, user, tenant và time range?
5. **Asset lifecycle:** ACTIVE/LOST/RETIRED/REASSIGNED có authority?
6. **Enrollment:** managed state khác compliance state?
7. **EDR:** agent present khác healthy/no active critical threat?
8. **OS/patch:** policy dựa trên assessment đáng tin và version?
9. **Encryption:** disk encryption posture có evidence và freshness?
10. **Attestation:** nonce/challenge, trust chain và binding được kiểm khi dùng?
11. **Device certificate:** SAN, issuer, EKU, expiry/revocation phù hợp?
12. **Browser fingerprint:** không coi là device attestation mạnh?
13. **BYOD:** có data protection và privacy-preserving options?
14. **Shared kiosk:** user session không bị thừa hưởng giữa ca?
15. **Signal schema:** có source, observedAt, receivedAt, validUntil và policy version?
16. **Unknown:** không tự map UNKNOWN/STALE thành PASS?
17. **Conflict:** MDM compliant không bỏ qua EDR threat mới?
18. **Risk score:** calibrated, explainable, không vượt hard denies?
19. **Action/resource:** policy theo sensitivity, không chỉ login?
20. **MFA:** step-up tăng assurance nhưng không cấp entitlement?
21. **RBAC/ABAC/PBAC:** resource/object/tenant vẫn được kiểm?
22. **IdP/SSO:** local sessions và OAuth tokens được quản lý sau posture change?
23. **Continuous evaluation:** biết chính xác sản phẩm nào re-evaluate runtime?
24. **Token/session:** TTL, revoke và long-lived connections có kế hoạch?
25. **Joiner:** device bound đúng user sau proofing và effectiveAt?
26. **Mover:** role, device policy, team và session được review?
27. **Leaver:** account/token/PAM bị chặn dù device còn compliant?
28. **Rejoiner:** relationship cũ không hồi sinh quyền?
29. **Owner transfer:** khi đổi người dùng, credentials/bindings được reset theo policy?
30. **Contractor:** unmanaged device có policy hạn chế rõ?
31. **Workload:** machine posture không bị hiểu nhầm là human MFA?
32. **Adversarial:** test spoofed headers, attestation replay, ID cloning?
33. **Outage:** MDM/EDR failure có fallback risk-tier được phê duyệt?
34. **Exceptions:** mỗi bypass có scope, owner, expiry và audit?
35. **Privacy:** chỉ thu device data cần thiết, retention và access control rõ?
36. **Audit:** lưu signal provenance, freshness, decision và target effect?
37. **Monitoring:** có metrics về stale, Leaver residual và revocation latency?
38. **Testing:** role hợp lệ nhưng device LOST phải Deny theo hard policy?
39. **Reconciliation:** actual API behavior khớp risk policy và JML?
40. **Closure:** kết luận không rộng hơn coverage và evidence đã xác minh?

### Ghi nhớ

**Device signal là bằng chứng hoặc quan sát về trạng thái thiết bị được dùng để đánh giá rủi ro truy cập**, thường đến từ **MDM/UEM, EDR, hệ điều hành, certificate, TPM/attestation và device lifecycle registry**. Giá trị của nó phụ thuộc vào **nguồn phát đáng tin, device binding, độ tươi, scope, cách xử lý UNKNOWN/CONFLICT và khả năng thực thi quyết định**. **Managed không đồng nghĩa compliant; compliant không đồng nghĩa an toàn tuyệt đối; device trust không thay thế user authentication, MFA hay RBAC/ABAC authorization.** Trong mô-đun **IAM Identity Lifecycle**, risk-based access phải kết hợp **Joiner–Mover–Leaver, IdP/SSO, SCIM, session/token, service/workload identity, audit và reconciliation**, đặc biệt bảo đảm rằng **thiết bị vẫn compliant không thể duy trì quyền truy cập tồn dư cho người đã Leaver hoặc quyền đã bị thu hồi**.
