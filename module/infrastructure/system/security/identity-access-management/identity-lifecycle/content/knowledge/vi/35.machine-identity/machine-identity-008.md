# Device trust: đánh giá độ tin cậy của thiết bị trong Machine identity và IAM

Một nhân viên đăng nhập SSO bằng mật khẩu đúng và MFA hợp lệ từ máy tính chưa từng được quản lý. Một máy tính khác thuộc tổ chức, có chứng chỉ thiết bị hợp lệ nhưng hệ điều hành đã lỗi thời và EDR báo nguy cơ bị xâm nhập. Cả hai đều có thể chứng minh một phần danh tính, nhưng **không nên tự động được coi là thiết bị đáng tin cậy để truy cập tài nguyên nhạy cảm**.

**Device trust** là việc xác định và duy trì mức độ tin cậy của thiết bị dựa trên **danh tính thiết bị, bằng chứng kiểm soát thiết bị, trạng thái bảo mật, tính toàn vẹn, ngữ cảnh và chính sách truy cập**. Mục tiêu không phải gắn nhãn “máy này an toàn vĩnh viễn”, mà là đưa ra quyết định **có căn cứ, đúng thời điểm, đúng tài nguyên**, đồng thời phát hiện và thu hồi những thiết bị không còn đáp ứng yêu cầu.

Bài thuộc chương **Machine identity**, chủ đề trực tiếp **Device trust**, trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Mô-đun tìm hiểu quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**: từ xác minh, tạo tài khoản và cấp quyền tới rà soát, thu hồi khi đổi vai trò; có liên kết **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và giảm quyền truy cập tồn dư.

Sau bài học, người học có thể:

- Phân biệt **device identity, device authentication, device posture, device compliance, device trust và user authentication**.
- Hiểu **enrollment, MDM/UEM, EDR, device certificates, TPM/Secure Enclave, attestation và cryptographic proof-of-possession**.
- Thiết kế **Zero Trust/conditional access** với tín hiệu thiết bị, tài khoản, ứng dụng, tài nguyên và mức rủi ro.
- Giải thích vì sao **enrolled/managed/compliant không tự đồng nghĩa trusted**, và vì sao chứng chỉ hợp lệ không chứng minh máy đang an toàn.
- Liên kết vòng đời thiết bị với **Joiner–Mover–Leaver, thiết bị BYOD, mất cắp, tái sử dụng, tài khoản máy và service/workload identities**.
- Kiểm tra **session/token/certificate revocation**, phát hiện drift, thiếu telemetry và sai lệch IdP–MDM–ứng dụng.
- Xây dựng policy, luồng quyết định, case study, kiểm thử, bằng chứng audit và KPI thực tế.

## 1. Device trust giải quyết bài toán gì?

Trong nhiều hệ thống, sau khi người dùng xác thực thành công, ứng dụng tiếp tục tin cậy phiên của họ trong một khoảng thời gian. Nhưng **user identity và device identity là hai chủ thể khác nhau**:

- Người dùng có thể đúng danh tính nhưng dùng thiết bị bị nhiễm mã độc.
- Một thiết bị có thể thuộc tổ chức nhưng đang được sử dụng bởi người không được phép.
- Thiết bị đã từng đạt compliance nhưng vừa tắt EDR, mất cập nhật hoặc bị thu hồi.
- Device certificate có thể còn hiệu lực dù máy đã mất hoặc account chủ sở hữu đã Leaver.
- Một token đã phát hành có thể tiếp tục được dùng dù tín hiệu posture mới đã chuyển sang không đạt.

**Device trust** bổ sung ngữ cảnh về endpoint để đưa ra quyết định như:

1. **ALLOW:** đáp ứng điều kiện cho tài nguyên hiện tại.
2. **STEP_UP:** cần thêm xác thực, nâng mức bảo đảm hoặc kiểm tra posture.
3. **RESTRICT:** cho quyền hạn chế, chỉ web/VDI hoặc chỉ thao tác an toàn.
4. **REMEDIATE:** hướng dẫn cập nhật OS, bật mã hóa hoặc hoàn thành quản lý thiết bị.
5. **DENY/QUARANTINE:** chặn truy cập nhạy cảm hoặc cô lập máy bị nghi xâm nhập theo policy.

Kết quả là **quyết định truy cập có điều kiện**, không phải lời khẳng định thiết bị tuyệt đối an toàn.

### 1.1. Ví dụ ba trường hợp

| Trường hợp | Bằng chứng | Quyết định minh họa |
| --- | --- | --- |
| Laptop công ty, người dùng ACTIVE, MDM compliant, EDR healthy, thiết bị khớp session. | Nhiều tín hiệu tươi và đáng tin. | Có thể cho truy cập tài nguyên phù hợp quyền người dùng. |
| Laptop công ty có khóa thiết bị hợp lệ, nhưng EDR phát hiện nguy cơ cao. | Device identity đúng, posture không đạt. | Từ chối hoặc cô lập truy cập nhạy cảm; mở incident. |
| Máy cá nhân mới, người dùng xác thực MFA thành công, chưa có evidence thiết bị. | User identity được xác minh, device trust chưa xác định. | Có thể chỉ cho quyền thấp hoặc yêu cầu enrollment theo policy. |

Những quyết định là **ví dụ**, không phải rule bắt buộc áp dụng giống nhau cho mọi tổ chức.

## 2. Các thuật ngữ rất dễ nhầm

| Thuật ngữ | Trả lời câu hỏi | Không tự bảo đảm |
| --- | --- | --- |
| **Device identity** | Đây là thiết bị/principal nào trong một namespace? | Thiết bị đang an toàn hay còn thuộc tổ chức. |
| **Device authentication** | Thiết bị có chứng minh quyền sở hữu credential/key đã đăng ký không? | OS không nhiễm mã độc. |
| **Device enrollment/registration** | Thiết bị đã được ghi danh với IdP/MDM/UEM theo quy trình nào? | Có compliant ở thời điểm hiện tại. |
| **Device management** | Tổ chức có thể áp policy và nhận telemetry qua công cụ quản lý không? | Mọi policy đã thực sự được thực thi. |
| **Device posture** | Tình trạng bảo mật quan sát được hiện tại: patch, EDR, mã hóa, boot... | Chủ thiết bị và actor là đúng người. |
| **Device compliance** | Thiết bị có thỏa tập điều kiện compliance đã định nghĩa không? | Không bị tấn công và không có quyền dư. |
| **Device trust** | Có đủ căn cứ chấp nhận thiết bị trong ngữ cảnh truy cập cụ thể không? | Tính an toàn tuyệt đối hoặc mãi mãi. |
| **User authentication** | Chủ thể con người đã được xác thực ra sao? | Thiết bị của người đó đáng tin. |
| **Authorization** | Principal có được thao tác này trên tài nguyên này lúc này không? | Mọi thiết bị đều nên được cấp cùng mức. |
| **Device attestation** | Một thực thể tin cậy có chứng thực thuộc tính/đo lường của thiết bị hoặc khóa không? | Mọi thuộc tính không nằm trong phạm vi attestation đều đạt. |

### 2.1. Nhận định quan trọng

~~~text
registered != managed
managed != compliant
compliant != uncompromised
authenticated device != authorized user
valid certificate != current healthy posture
prior trust decision != permanent trust
~~~

Một nền tảng có thể dùng từ “joined”, “registered”, “managed” hay “compliant” với định nghĩa riêng. Khi thiết kế hệ thống, phải ghi **ngữ nghĩa thuộc tính, nguồn sở hữu và độ tươi**, không suy từ tên trường.

## 3. Device identity khác User identity và Workload identity

Một ứng dụng có thể nhận đồng thời:

~~~text
Person / Engagement
      │
      ├── User account tại IdP
      │      └── Sign-in / MFA / SSO session
      │
      └── Sử dụng Device D-101
                 ├── Device record tại UEM/MDM
                 ├── Device credential / private key
                 ├── OS, EDR, encryption, patch posture
                 └── Trust evidence và trạng thái thu hồi

Application/Service workload W-22
      └── Workload principal + service credentials
             └── Chạy trên host/device/node H-05
~~~

Ba quan hệ cần tách:

- **Human → Account:** Person và Engagement tương ứng user account nào?
- **Human/Workload → Device:** thiết bị hiện được quản lý/được dùng bởi ai và trong ngữ cảnh gì?
- **Device → Resource/session:** thiết bị nào đã tham gia phiên hoặc kết nối được xác thực?

### 3.1. Vì sao không dùng email làm khóa thiết bị?

Một laptop có thể được bàn giao từ người A sang người B. Email chủ cũ có thể đổi hoặc tái cấp; nhân viên tái tuyển có engagement mới. **Device ID phải được namespace và quản lý vòng đời riêng**; không suy luận cùng thiết bị chỉ từ hostname, email hoặc địa chỉ IP.

### 3.2. Thiết bị không tự động thay mặt chủ sở hữu

Chứng chỉ thiết bị xác thực máy D-101 **không đồng nghĩa** người dùng hiện tại là chủ được phép truy cập dữ liệu tài chính. Ngược lại, user đã đăng nhập đúng không chứng minh họ dùng D-101 nếu server không xác minh **liên kết phiên với thiết bị**.

### 3.3. Host identity và workload identity

Trong máy chủ và container, **host/node trust** có thể là một thành phần của điều kiện cấp workload identity. Tuy nhiên, **container, pod, service account, VM và node là các principal khác nhau**. Một pod có token workload hợp lệ không tự chứng minh node an toàn; một node có posture tốt cũng không tự cấp quyền production cho mọi workload chạy trên đó.

## 4. Những tín hiệu cấu thành device trust

Các tổ chức thường đánh giá một tổ hợp tín hiệu:

| Nhóm tín hiệu | Ví dụ | Điểm cần thận trọng |
| --- | --- | --- |
| **Identity/ownership** | Device ID, tenant, asset owner, enrollment source. | Record cũ, thiết bị tái sử dụng hoặc spoofed attributes. |
| **Cryptographic proof** | Chứng minh possession của private key thiết bị, mTLS, attestation. | Khóa có thể bị lộ hoặc chứng chỉ bị thu hồi. |
| **Management** | UEM/MDM enrollment, policy sync, remote configuration. | Enrollment alone không chứng minh compliance. |
| **Platform integrity** | Secure Boot, measured boot, attested boot state. | Phạm vi và trust anchor attestation phụ thuộc nền tảng. |
| **Endpoint protection** | EDR/antimalware health, tamper status, detections. | Telemetry có độ trễ, EDR có thể bị vô hiệu. |
| **OS posture** | Phiên bản OS, bản vá, cấu hình firewall, disk encryption. | Policy về patch grace period phải rõ. |
| **Credential health** | Certificate expiry/revocation, key rotation, storage protection. | Chứng chỉ hợp lệ không xác nhận chủ thể nhân sự còn ACTIVE. |
| **Usage/context** | Network, location signal, geovelocity, thiết bị mới, time. | IP/VPN/NAT không đủ để nhận diện máy. |
| **Risk telemetry** | Device risk score, threat detection, anomalous sessions. | Score là tín hiệu được đánh giá, không là phép đo tuyệt đối. |
| **Lifecycle** | Assigned, lost, retired, wiped, quarantined, unmanaged. | Status phải đồng bộ về nơi thực thi. |

### 4.1. Độ tươi của tín hiệu

Một báo cáo MDM “compliant” được ghi lúc 08:00 nhưng truy cập lúc 18:00 không giống một kiểm tra mới tại 18:00. Khi thiết kế, cần xác định:

- `observedAt`: thiết bị được đo lúc nào.
- `receivedAt`: hệ thống chính sách nhận tín hiệu lúc nào.
- `expiresAt/ttl`: khi nào evidence hết giá trị theo policy.
- `sourceVersion`: phiên bản cấu hình/định nghĩa compliance.
- `attestationScope`: attestation chứng minh điều gì, trên nền tảng nào.
- `lastSeenAt`: thiết bị có còn liên lạc với quản lý không.

**Không lấy “đã từng đạt” làm “đang đạt”.** Nếu tín hiệu quá hạn hoặc nguồn telemetry lỗi, phải quyết định theo chính sách **UNKNOWN/STALE** riêng.

## 5. Trust là quyết định theo ngữ cảnh, không là một cờ toàn cục

Một device D có thể được chấp nhận để đọc tài liệu nội bộ ít nhạy cảm nhưng không được phép xuất dữ liệu khách hàng hoặc sửa IAM policy.

### 5.1. Mô hình quyết định khái niệm

~~~text
Device trust decision =
    evaluate(
        device_identity,
        proof_of_possession,
        posture + attestation + freshness,
        lifecycle_status,
        user_or_workload_identity,
        authentication_strength,
        resource_sensitivity,
        action + environment + time,
        applicable_policy
    )
~~~

Mô hình chỉ minh họa, không có công thức số universal cho mọi môi trường. **Allow/Deny/Step-up/Restrict** nên là kết quả của policy gắn với hành động và tài nguyên.

### 5.2. Cách phân tầng nguồn lực

| Tài nguyên minh họa | Điều kiện tối thiểu minh họa | Biện pháp khi thiếu bằng chứng |
| --- | --- | --- |
| Portal công khai có tài liệu nội bộ ít nhạy cảm. | User authorization và xác thực theo rủi ro; thiết bị có thể unmanaged nếu policy cho. | Session giới hạn chức năng. |
| CRM chứa dữ liệu cá nhân. | User ACTIVE, role phù hợp, device managed/compliant có evidence tươi. | Hạn chế export hoặc chỉ VDI, theo policy. |
| Production admin console. | Privileged role/JIT, xác thực mạnh, trusted device và kiểm ngữ cảnh. | Từ chối/step-up hoặc kênh quản trị được bảo vệ. |
| Emergency recovery interface. | Cơ chế continuity đặc biệt có audit, scope và hậu kiểm. | Không dựa hoàn toàn vào IdP/MDM bị outage nhưng vẫn áp kiểm soát bù. |

**RBAC quyết định những hành động được phép theo role; ABAC có thể thêm điều kiện về thiết bị và ngữ cảnh.** Thiết bị compliant không tự biến user Reader thành Admin.

## 6. Kiến trúc tham chiếu: tín hiệu đến quyết định và enforcement

~~~mermaid
flowchart LR
    HR["HRIS / Contract<br/>Person + JML"] --> ID["IdP / Identity correlation"]
    UEM["UEM / MDM<br/>Enrollment + compliance"] --> PIP["Device signals / PIP"]
    EDR["EDR / OS telemetry<br/>Risk + patch + encryption"] --> PIP
    PKI["PKI / Attestation<br/>Certificate + key proof"] --> PIP
    ASSET["Asset registry<br/>Ownership + lifecycle"] --> PIP
    ID --> PDP["Policy decision point<br/>User + Device + Resource"]
    PIP --> PDP
    CAT["Role catalog / RBAC / ABAC<br/>Resource + risk"] --> PDP
    PDP --> PEP["Policy enforcement point<br/>Proxy / Gateway / App"]
    PEP --> APP["SaaS / API / Admin / Data"]
    PEP --> AUD["Decision + session audit"]
    PIP --> MON["Drift / Incident / Reconciliation"]
    MON --> PDP
~~~

Trong sơ đồ:

- **PIP (Policy Information Point):** nơi cung cấp thông tin thuộc tính và rủi ro.
- **PDP (Policy Decision Point):** nơi đánh giá policy dựa trên dữ liệu được xác minh.
- **PEP (Policy Enforcement Point):** nơi chặn/cho yêu cầu ở proxy, API, ứng dụng hoặc dịch vụ.
- **UEM/MDM:** hệ thống quản trị endpoint.
- **PKI/Attestation:** xác thực khóa hoặc thuộc tính nền tảng theo khả năng.

### 6.1. Cảnh báo ranh giới tin cậy

Không nên để client tự gửi `deviceCompliant=true` rồi PDP tin ngay. Thuộc tính phải tới từ **nguồn được xác thực, gắn đúng deviceId, có tính toàn vẹn, tenant/namespace và hạn sử dụng**. Nếu policy dựa vào một claim trong token, cần xác định **ai phát claim, token cho audience nào, claim được đo khi nào và cách xử lý khi posture thay đổi**.

### 6.2. Enforcement ở đâu?

Device trust có thể được thực thi ở:

1. **Trước đăng nhập hoặc cấp token:** IdP/conditional access từ chối nếu thiếu device posture theo policy.
2. **Ở proxy/ZTNA:** kiểm device identity, posture và user trước khi nối vào tài nguyên.
3. **Ở API/application:** kiểm token/session, quyền người dùng và thiết bị phù hợp với hành động.
4. **Trong session đang hoạt động:** re-evaluate liên tục/định kỳ, thu hồi hoặc hạn chế khi risk thay đổi nếu nền tảng hỗ trợ.

**Một cổng đăng nhập đã cho qua không tự bảo vệ mọi API và phiên dài hạn phía sau**. Phải xác định điểm kiểm tra thực tế và độ trễ cập nhật.

## 7. Thiết lập danh tính thiết bị: enrollment và registration

Trust ban đầu phụ thuộc cách thiết bị được **đưa vào quản lý** và gắn với owner/tenant.

### 7.1. Luồng gợi ý

1. **Xác minh nguồn thiết bị:** tài sản công ty, thiết bị cá nhân được cho phép, máy chủ hoặc thiết bị chuyên dụng.
2. **Định danh duy nhất theo namespace:** tạo hoặc liên kết `deviceId` tại hệ thống quản lý và IdP.
3. **Đăng ký bằng chứng sở hữu:** credential thiết bị/khóa/chứng chỉ phù hợp nền tảng.
4. **Enrollment vào UEM/MDM** khi policy yêu cầu, gán baseline bảo mật.
5. **Liên kết đúng owner và mục đích:** Person/Engagement, shared device pool hoặc workload/ownerTeam.
6. **Kiểm posture ban đầu:** OS, encryption, EDR, patch, integrity, policy.
7. **Cập nhật trust evidence:** compliant/managed/attested với timestamp và version.
8. **Chỉ cho truy cập tài nguyên** phù hợp authorization và trust policy.

### 7.2. Những mối quan hệ cần phân biệt

~~~text
deviceId       = định danh thiết bị trong tenant/nguồn cụ thể
assetId        = mã tài sản doanh nghiệp (nếu có)
mdmRecordId    = bản ghi trong hệ thống quản lý
idpDeviceId    = bản ghi IdP (có thể khác mdmRecordId)
certificateId  = credential xác thực thiết bị (có thể thay khi rotate)
ownerSubjectId = người/nhóm/workload chịu trách nhiệm
sessionId      = một lần truy cập, không phải identity cố định
~~~

Không nên chỉ dùng **MAC address, IP, hostname hoặc serial number tự khai** làm bằng chứng xác thực thiết bị. Các giá trị có thể bị thay đổi, tái sử dụng, NAT hoặc spoof; serial/hardware ID có thể hữu ích khi đi kèm nguồn đã xác minh nhưng không thay proof-of-possession.

### 7.3. Chứng chỉ nhiều thiết bị và tái đăng ký

Khi máy được cài lại hoặc thay bo mạch, device record/credential có thể đổi. Cần xác định **bằng chứng cho phép liên kết lại thiết bị cũ hay tạo identity mới**, thu hồi credential cũ đúng lúc và tránh để hai device IDs cùng được coi tin cậy nếu một là bản sao không hợp lệ.

## 8. TPM, Secure Enclave và khóa không xuất được

**TPM (Trusted Platform Module)** là một thành phần bảo mật phần cứng hoặc firmware được thiết kế để hỗ trợ lưu/trình chứng minh khóa và phép đo trạng thái nền tảng. Một số thiết bị di động dùng các thành phần như **Secure Enclave/hardware-backed keystore** với chức năng khác nhau tùy hệ sinh thái.

### 8.1. Những khả năng liên quan

| Khả năng | Ý nghĩa | Không nên suy luận |
| --- | --- | --- |
| **Key generation/storage** | Tạo hoặc bảo vệ private key với phần cứng/bộ phận tin cậy. | Mọi khóa đều chắc chắn không thể bị lạm dụng qua malware. |
| **Proof of possession** | Bên kia xác minh client có thể dùng private key đã đăng ký. | OS đang sạch hoặc người dùng là người hợp lệ. |
| **Measured boot** | Tạo phép đo hoặc log của các thành phần khởi động theo cơ chế nền tảng. | Toàn bộ user-space runtime không có mã độc. |
| **Remote attestation** | Verifier kiểm bằng chứng đã ký về khóa/trạng thái trong phạm vi đo. | Mọi thông tin ngoài phạm vi được chứng thực đều an toàn. |
| **Hardware-backed key restrictions** | Hạn chế xuất/private-key use theo khả năng nền tảng. | Không còn rủi ro nếu OS hoặc tài khoản có quyền dùng key bị chiếm. |

### 8.2. Proof-of-possession khác device posture

Nếu client ký một challenge bằng khóa đăng ký, server có thể kiểm **nó sở hữu hoặc có thể sử dụng khóa ấy**. Nhưng nếu malware đang điều khiển tiến trình hợp lệ, nó cũng có thể yêu cầu phần cứng ký trong một số thiết kế. Vì vậy cần kết hợp **attestation khi có, MDM/EDR, lifecycle, session controls và authorization**.

### 8.3. Kiểm attestation đúng phạm vi

Verifier cần xác minh, khi áp dụng:

- Chuỗi chứng thực và **trust anchor** được tin.
- Nonce/challenge chống dùng lại chứng cứ cũ.
- Device/tenant/credential binding.
- Loại bằng chứng, thuật toán, phiên bản nền tảng và chính sách chấp nhận.
- Timestamp/freshness và revocation status của chứng chỉ/chains.
- Những phép đo cần thiết (chẳng hạn trạng thái boot) thực sự có trong attestation.

**Không phải thiết bị nào cũng hỗ trợ cùng kiểu attestation**; policy cần xử lý `UNSUPPORTED` riêng thay vì coi mọi máy không có TPM là nguy hiểm tuyệt đối hoặc coi việc không kiểm chứng được là PASS.

## 9. PKI, chứng chỉ thiết bị và mutual TLS

Một cách phổ biến để xác thực machine/device là **chứng chỉ X.509** cùng private key tương ứng. Trong một số kết nối, **mutual TLS (mTLS)** cho phép cả client và server xác thực bằng chứng chỉ.

### 9.1. mTLS cho biết gì?

Một phiên mTLS có thể chứng minh **client có quyền sử dụng private key gắn với certificate đã được server chấp nhận**. Nếu certificate được cấp qua enrollment đáng tin, đó là tín hiệu mạnh về **device/workload identity** trong namespace đã định.

Nhưng **mTLS không tự kiểm OS patch, EDR, trạng thái Mover/Leaver hoặc scope quyền dữ liệu**. Phải đánh giá theo policy.

### 9.2. Kiểm chứng chỉ đúng cách

| Kiểm tra | Tại sao cần |
| --- | --- |
| **Certificate chain** | CA/issuer có nằm trong trust store được cho phép? |
| **Validity period** | NotBefore/NotAfter và clock validity. |
| **Subject/SAN/device binding** | Chứng chỉ có khớp device/tenant/workload được đăng ký? |
| **Extended Key Usage / key usage** | Chứng chỉ được phép dùng cho mục đích client authentication không? |
| **Proof of private-key control** | Client thực sự kiểm soát khóa. |
| **Revocation status** | Chứng chỉ đã bị thu hồi, mất máy hoặc nghi lộ chưa? |
| **Policy mapping** | Device có còn managed/compliant và user có quyền resource không? |

Khi dùng CRL/OCSP hoặc cơ chế revocation khác, cần lưu ý **độ trễ công bố, caching, độ sẵn sàng và cách xử lý outage**. Một certificate có `NotAfter` trong tương lai **không chứng minh certificate chưa bị thu hồi**.

### 9.3. Certificate rotation

Xoay khóa/chứng chỉ phải:

1. Phát credential mới qua quy trình được xác thực.
2. Chuyển kết nối/service mà không tạo quyền thừa.
3. Vô hiệu hóa credential cũ khi kết thúc giai đoạn chuyển đổi có kiểm soát.
4. Kiểm không có phiên hoặc client bị bỏ quên vẫn dùng key cũ.
5. Ghi audit và đối soát đúng owner/tenant.

Tạo chứng chỉ mới **không phải lý do tự gia hạn mọi quyền** của thiết bị, nếu asset đã mất, retire hoặc thuộc account Leaver.

## 10. MDM/UEM: quản lý không đồng nghĩa tin cậy vô điều kiện

**MDM/UEM** hỗ trợ enrollment, cấu hình, kiểm compliance, khóa/xóa quản trị và thu thập tín hiệu endpoint tùy nền tảng.

### 10.1. Các trạng thái cần tách

| Trạng thái | Ý nghĩa khả dĩ | Kiểm soát cần hỏi |
| --- | --- | --- |
| **Registered** | Có bản ghi về device với IdP/management. | Ai đăng ký? Credential và ownership có đáng tin? |
| **Enrolled** | Có kênh quản lý, policy assignment. | Enrollment còn active và thuộc tenant đúng? |
| **Managed** | Có khả năng áp policy/quản trị thiết bị. | Agent kết nối gần đây và có chống giả dữ liệu? |
| **Compliant** | Đạt bộ điều kiện MDM định nghĩa tại snapshot. | Policy version, freshness, điều kiện có bao phủ risk không? |
| **Noncompliant** | Không đạt một hoặc nhiều điều kiện. | Lỗi gì, remediation và mức hạn chế tương ứng? |
| **Unknown/Stale** | Không có tín hiệu đủ mới để kết luận. | Có được truy cập resource nhạy cảm không? |
| **Retired/Lost/Wiped** | Đã ngừng quản lý, mất hoặc xóa thiết bị. | Certificate/session/token và local grants đã xử lý chưa? |

### 10.2. Policy compliance gợi ý

~~~yaml
# Policy nội bộ minh họa; không phải định dạng MDM chuẩn.
devicePolicyId: CORP-ENDPOINT-BASELINE
policyVersion: 7
requiredSignals:
  diskEncryption: enabled
  osSupport: supported
  securityPatch: withinApprovedGraceWindow
  endpointProtection: healthy
  screenLock: enabled
  management: enrolledAndActive
  lastCheckIn: withinPolicyFreshnessWindow
onSignalUnknown: RESTRICT_OR_DENY_BY_RESOURCE_RISK
onConfirmedHighRisk: DENY_SENSITIVE_ACCESS_AND_ALERT
~~~

Không nên hardcode mọi số ngày “patch mới nhất”, thời hạn check-in hoặc mức risk chung cho tất cả thiết bị. Những ngưỡng đó phụ thuộc hệ điều hành, loại thiết bị, phơi lộ và năng lực vận hành.

### 10.3. Compliance là đầu vào của quyết định, không phải kết quả cuối

Một máy `compliant=true` có thể được dùng bởi người đã Leaver. Một máy compliant vẫn có thể bị đánh cắp trong lúc chưa cập nhật hệ thống quản trị. **User authorization, device lifecycle, khóa chứng thực và session risk** phải tiếp tục được kiểm.

## 11. EDR và đánh giá nguy cơ thiết bị

**EDR (Endpoint Detection and Response)** phát hiện và hỗ trợ ứng cứu các dấu hiệu rủi ro ở endpoint. Tích hợp EDR có thể cung cấp tín hiệu:

- Malware/suspicious activity detections và mức severity.
- Agent health, tamper protection, khả năng gửi telemetry.
- Thời điểm last seen/last scan.
- Isolation/quarantine status.
- Thiết bị đã xử lý/remediate nhưng chưa được xác minh sạch.

### 11.1. Không nhầm “không có detection” với “không có malware”

Không có cảnh báo EDR có thể do **thiết bị chưa được giám sát**, agent offline, thiếu coverage hoặc kẻ tấn công né phát hiện. Policy phải phân biệt:

~~~text
EDR_HEALTHY_AND_NO_HIGH_RISK_DETECTION
EDR_HIGH_RISK_DETECTION
EDR_AGENT_MISSING_OR_OFFLINE
EDR_TELEMETRY_STALE
EDR_NOT_SUPPORTED_BY_PLATFORM
~~~

Các trạng thái không nên bị gộp thành một boolean `isSafe`. Nếu EDR báo rủi ro cao, có thể kích hoạt **incident/quarantine**, song vẫn cần quy trình giảm thiểu false positives và phục hồi thiết bị hợp lệ.

### 11.2. Khi risk thay đổi trong session

Giả sử 09:00 device được cho vào CRM; 09:20 EDR chuyển sang HIGH_RISK. Cần biết:

1. Event đến PDP/PEP sau bao lâu?
2. Session/token nào có liên quan tới deviceId?
3. Ứng dụng có hỗ trợ **reauth, session termination hoặc continuous access evaluation** không?
4. Có thể chặn **download/export** ngay cả khi phiên web vẫn mở?
5. Nếu policy chỉ áp ở sign-in tiếp theo, cửa sổ truy cập tồn dư dài bao lâu?

**Không tuyên bố “chặn tức thì” nếu không có bằng chứng enforcement và độ trễ đo được**.

## 12. Zero Trust và Conditional Access

**Zero Trust** hướng tới việc không mặc nhiên tin cậy dựa vào vị trí mạng hoặc việc đã từng đăng nhập, mà xác minh rõ danh tính, trạng thái và quyền ở từng quyết định phù hợp. Device trust là **một tập tín hiệu** trong mô hình đó.

### 12.1. Các yếu tố của policy

| Yếu tố | Ví dụ |
| --- | --- |
| **Subject** | Employee ACTIVE, Contractor còn hợp đồng, service principal có owner. |
| **Device** | Managed/compliant, key proven, attested, EDR healthy. |
| **Resource/action** | Đọc dữ liệu, export, thay cấu hình IAM, production deployment. |
| **Auth strength** | MFA hoặc phishing-resistant authentication theo mức rủi ro. |
| **Context** | Risk signals, location, network trust, giờ làm việc, threat intel. |
| **Policy exception** | BYOD low-risk, emergency access, VDI, thiết bị kiosk. |
| **Time/freshness** | Token/session lifespan, posture age, device enrollment expiry. |

### 12.2. Không dùng “ở trong VPN” để kết luận tin cậy

VPN, IP nội bộ hoặc NAT **không xác định duy nhất thiết bị** và không nói OS còn được bảo vệ. Một máy đã bị chiếm và kết nối VPN vẫn có thể gây hại. Nên phối hợp **identity, device binding, posture, network context và resource policy**.

### 12.3. Conditional access không thay authorization của ứng dụng

Nếu policy xác định user A chỉ có role Reader, việc A đăng nhập từ máy compliant không cho phép họ xóa dữ liệu. **Ứng dụng/API vẫn phải kiểm quyền nghiệp vụ và object/resource scope** qua RBAC/ABAC. Device trust không nên được dùng thay cho kiểm tra SoD hoặc least privilege.

## 13. Ví dụ Conditional Access kết hợp thiết bị và RBAC/ABAC

Giả sử hệ thống có tài nguyên **customer-data** và quyền **report.export** dành cho một số nhân viên Finance. Chính sách có thể:

1. Xác minh user/account còn ACTIVE và đang có Engagement hợp lệ.
2. Kiểm user có permission `report.export` trong đúng tenant.
3. Xác minh thiết bị khớp device identity đã đăng ký và bằng chứng possession.
4. Kiểm thiết bị managed/compliant với tín hiệu còn đủ mới.
5. Kiểm EDR không có nguy cơ cao được xác nhận.
6. Kiểm session/token đủ mức bảo đảm và chưa bị thu hồi.
7. Nếu tất cả điều kiện đáp ứng: **PERMIT**; nếu posture thiếu: **RESTRICT/STEP_UP/DENY** theo policy; nếu thiết bị bị đánh cắp: **DENY**.

### 13.1. Pseudocode quyết định

~~~text
authorize(subject, device, action, resource, context):
    identity = loadAuthoritativeIdentity(subject)
    if identity.engagementState != ACTIVE:
        return DENY("SUBJECT_NOT_ELIGIBLE")

    permissions = evaluateEffectivePermissions(subject, resource)
    if not permissions.allows(action):
        return DENY("INSUFFICIENT_AUTHORIZATION")

    proof = verifyDeviceAuthenticationAndSessionBinding(device, context)
    if not proof.valid:
        return DENY("DEVICE_PROOF_INVALID")

    lifecycle = loadDeviceLifecycle(device)
    if lifecycle in [LOST, STOLEN, RETIRED, REVOKED]:
        return DENY("DEVICE_REVOKED")

    posture = fetchTrustedPostureEvidence(device)
    if posture.missing or posture.stale:
        return decisionForUnknownPosture(resource.riskTier)
    if posture.confirmedHighRisk:
        return DENY_AND_ALERT("DEVICE_RISK")

    if not policyAllowsDeviceForResource(posture, action, resource):
        return RESTRICT_OR_DENY("DEVICE_POLICY")

    return PERMIT_WITH_SESSION_LIMITS(context)
~~~

Đây là **giả mã**, không phải code có sẵn của IdP nào. Một sản phẩm có thể hỗ trợ STEP_UP hoặc QUARANTINE ở những điểm khác nhau; không nên giả định mọi API đều có cơ chế cập nhật session tức thì.

### 13.2. Bảng quyết định ngữ cảnh

| Subject | Device | Action/resource | Kết quả minh họa |
| --- | --- | --- | --- |
| ACTIVE + Reader | Healthy/compliant | Read báo cáo được phép. | ALLOW. |
| ACTIVE + Reader | Healthy/compliant | Delete database. | DENY vì **không đủ quyền**. |
| ACTIVE + Exporter | Unknown/BYOD | Export dữ liệu nhạy cảm. | DENY/RESTRICT theo policy. |
| ACTIVE + Exporter | Healthy/compliant | Export đúng tenant, MFA đạt. | Có thể ALLOW. |
| TERMINATED | Healthy/compliant | Read dữ liệu công ty. | DENY vì **subject không hợp lệ**. |
| ACTIVE + Admin | STOLEN/REVOKED | Quản trị production. | DENY, xử lý incident nếu cần. |
| Workload principal hợp lệ | Host không đạt attestation bắt buộc. | Lấy credential production. | Không cấp credential theo policy. |

**Không có một loại thiết bị nào tự động được mọi quyền**. Tính hợp lệ của user, resource/action và thiết bị phải được xét đồng thời.

## 14. Device trust và bảo đảm xác thực người dùng

**MFA, phishing-resistant authentication, passkeys/WebAuthn và device trust** có thể hỗ trợ nhau nhưng giải quyết những câu hỏi khác.

### 14.1. Điều gì được chứng minh?

| Cơ chế | Bằng chứng chính | Không tự chứng minh |
| --- | --- | --- |
| **Password + OTP MFA** | User đáp ứng các yếu tố xác thực theo thiết kế. | Thiết bị quản lý đạt posture. |
| **Passkey/WebAuthn** | Authenticator thực hiện ký challenge cho RP ID/origin liên quan; chống phishing theo giao thức. | Laptop chứa trình duyệt đã được MDM kiểm hay không. |
| **WebAuthn authenticator attestation** | Thông tin về kiểu/nguồn authenticator nếu được cung cấp và tin cậy. | Toàn bộ thiết bị đang chạy trình duyệt sạch mã độc. |
| **Device certificate / mTLS** | Client chứng minh khả năng sử dụng khóa thiết bị đã đăng ký. | User nào đang ngồi trước máy. |
| **Device platform attestation** | Thuộc tính/đo lường nền tảng trong phạm vi được chứng thực. | User được phép truy cập mọi resource. |
| **MDM compliance** | Thiết bị thỏa policy tại snapshot. | Xác thực thành công user trong phiên cụ thể. |

### 14.2. Không nhầm OAuth 2.0 Device Authorization Grant

Tên **OAuth 2.0 Device Authorization Grant** (thường gọi *device code flow*) có chữ *device*, nhưng nó là một **luồng cấp quyền OAuth cho thiết bị có khả năng nhập liệu hạn chế**. Nó **không tự xác thực thiết bị đang an toàn, không mặc nhiên chứng minh device posture, ownership hoặc enrollment**.

Khi ứng dụng đòi “trusted device”, đừng chỉ kiểm việc OAuth device flow thành công. Phải bổ sung **device identity proof, posture evidence và authorization policy** theo yêu cầu.

### 14.3. Token-binding và chứng minh sở hữu

Một số thiết kế dùng **sender-constrained access tokens** như mTLS-bound tokens hoặc DPoP để giảm khả năng token bị đánh cắp rồi dùng từ client khác. Tuy nhiên:

- Cần kiểm **binding** của token với khóa thực tế được client sử dụng.
- DPoP chứng minh quyền sử dụng một khóa, nhưng khóa đó **không mặc nhiên là device identity phần cứng tin cậy**.
- Thiết bị bị nhiễm mã độc vẫn có thể điều khiển một client hợp lệ sử dụng khóa.
- Resource server phải hỗ trợ kiểm binding; chỉ có claim trong token không bảo đảm enforcement.

**Proof-of-possession giúp giảm rủi ro token replay, không thay đánh giá posture và lifecycle**.

## 15. Vòng đời Device identity và trạng thái tin cậy

Trong IAM, thiết bị cũng có vòng đời gần giống Joiner–Mover–Leaver của con người, nhưng **không được đồng nhất hai vòng đời**.

~~~mermaid
flowchart TD
    A["Procure / Discover<br/>asset + source"] --> B["Register / Enroll<br/>deviceId + credentials"]
    B --> C["Assign Owner / Workload<br/>policy + scope"]
    C --> D["Assess Posture<br/>managed / compliant / attested"]
    D --> E["Trusted for specific access<br/>conditional decision"]
    E --> F{"Lifecycle event"}
    F -->|"Patch / Risk change"| D
    F -->|"Transfer / Reassign"| G["Revalidate ownership<br/>rotate/reset / re-enroll"]
    G --> D
    F -->|"Lost / Stolen"| H["Revoke / block / incident"]
    F -->|"Retire / Dispose"| I["Deprovision + erase<br/>revoke credentials"]
    H --> J["Verify no effective access"]
    I --> J
    J --> K["Audit / asset closure"]
~~~

### 15.1. Trạng thái vòng đời khác trạng thái posture

Một thiết bị có thể đồng thời:

~~~text
assetState = ASSIGNED
enrollmentState = ENROLLED
postureState = NONCOMPLIANT
identityCredentialState = VALID
accessDecision = DENY_SENSITIVE
~~~

Nếu chỉ có một cờ `trusted=true`, rất khó phân biệt nguyên nhân và biện pháp khắc phục. Nên giữ các thuộc tính riêng và tính **access decision** theo policy.

### 15.2. Các sự kiện cần làm thay đổi trust

| Sự kiện | Hành động tương ứng |
| --- | --- |
| Device mới được cấp. | Register, owner mapping, enrollment, certificate và posture baseline. |
| Device bị tắt mã hóa. | Mark noncompliant, hạn chế resource theo risk, remediation. |
| EDR phát hiện nguy cơ cao. | Alert/incident, deny/quarantine theo policy. |
| Device không check-in quá TTL. | Chuyển posture sang stale/unknown, re-evaluate. |
| Device được bàn giao. | Đổi owner, kiểm/erase dữ liệu, re-enroll/rotate credential khi cần. |
| Device bị mất/đánh cắp. | Mark LOST/STOLEN, revoke credential/session/token và giám sát. |
| Device bị thay phần cứng. | Kiểm lại identity binding/attestation và enroll mới khi phù hợp. |
| Device được loại bỏ. | Deprovision, wipe, revoke PKI/IdP/MDM, cập nhật asset registry. |
| Issuer/CA mất tin cậy. | Thu hồi trust anchor/certificate theo quy trình rủi ro. |

Một device record có thể còn để phục vụ kiểm toán sau khi hết quyền, nhưng **record còn tồn tại không được hiểu là credential vẫn hợp lệ**.

## 16. Joiner: cấp thiết bị và quyền theo nhân sự mới

Trong Joiner, tổ chức thường tạo account/IdP và cấp máy trước ngày làm việc đầu tiên.

### 16.1. Luồng vận hành

1. HRIS/hợp đồng xác nhận Person, Engagement, worker type, manager và `startDate`.
2. Asset/IT ghi nhận thiết bị nào được giao, theo quy trình kiểm soát kho.
3. UEM/MDM enrollment thiết bị, áp baseline.
4. Cấp device credential qua quá trình định danh đã kiểm chứng.
5. Liên kết `personId / engagementId` với `deviceId` tại hệ thống có thẩm quyền.
6. Kiểm posture/attestation theo capability của thiết bị.
7. IdP/conditional access chỉ cho sử dụng quyền nghiệp vụ khi **cả user và device** đủ điều kiện.
8. Đối soát trạng thái actual ở IdP, MDM và những ứng dụng áp thiết bị.

### 16.2. Preboarding không có nghĩa mở toàn bộ truy cập

Máy có thể được enrollment trước Start date để cài ứng dụng và policy. Điều đó không có nghĩa **user được quyền truy cập dữ liệu production trước ngày bắt đầu**. Có thể có preboarding access hẹp theo policy, nhưng phải phân biệt:

- **Device ready**: máy được cấu hình.
- **User engagement active**: nhân viên đã đủ điều kiện.
- **Entitlement granted**: role nghiệp vụ đã có hiệu lực.
- **Session authorized**: quyền cụ thể được cho tại thời điểm truy cập.

### 16.3. Trường hợp máy được bàn giao không đúng Person

Nếu device D-101 thuộc tài khoản người khác trong MDM, việc user A đăng nhập và MFA thành công không đủ để tự gắn D-101 cho A. Cần kiểm **asset assignment/ownership source** và quy trình bàn giao, đặc biệt với thiết bị chia sẻ hoặc kiosk.

## 17. Mover: chuyển bộ phận, đổi vai trò hoặc chuyển thiết bị

Mover có thể thay **entitlements** của user và **chính sách áp lên thiết bị**. Ví dụ kỹ sư SRE chuyển sang Product:

- Quyền SSH/admin production và JIT eligibility của người đó phải được rà soát.
- Thiết bị có thể vẫn do người đó sử dụng, nhưng **risk tier và allowed resources thay đổi**.
- Device compliance không tự thu hồi role SRE cũ.
- Nếu laptop được bàn giao cho SRE mới, owner binding và local credential phải được xem xét.
- Các session/token đã cấp từ trước khi Mover có thể còn hiệu lực theo khả năng IdP/ứng dụng.

### 17.1. Bảng thay đổi

| Thành phần | Trước Mover | Sau Mover |
| --- | --- | --- |
| **User/Engagement** | SRE, quyền production. | Product, chỉ role theo nhiệm vụ mới. |
| **Device identity** | Laptop D-101. | Có thể vẫn D-101 nếu không bàn giao. |
| **Device posture** | Managed/compliant. | Tiếp tục đánh giá kỹ thuật, không tự đổi từ role. |
| **Access policy** | Cho admin console nếu thỏa PAM/JIT. | Không cho console nếu không còn entitlement. |
| **Local device privilege** | Có thể có local admin theo job cũ. | Rà soát/thu hồi nếu không cần. |
| **Sessions/tokens** | Session admin có thể đang hoạt động. | Xử lý theo policy, verify chấm dứt đường cũ. |

### 17.2. Không nhầm quyền thiết bị với quyền nghiệp vụ

Một Mover có thể giữ máy compliant nhưng **không còn được phép truy cập production**. Ngược lại, một Mover sang đội security vẫn phải có thiết bị đáp ứng mức tin cậy mới; việc cấp role mới **không tự làm máy hiện tại đủ an toàn**.

### 17.3. Khi device chuyển chủ sở hữu

Đừng chỉ cập nhật `ownerEmail` trên asset inventory. Cần:

1. Xác nhận bàn giao và quyền sở hữu mới.
2. Bảo vệ/xóa dữ liệu cũ theo chính sách, xử lý key và local profiles.
3. Re-enroll hoặc rebind credential nếu trust model yêu cầu.
4. Thu hồi chứng chỉ/token/device sessions gắn người/chủ cũ khi cần.
5. Đánh giá lại policy và posture theo owner/role mới.
6. Kiểm thiết bị không còn đường truy cập thuộc người cũ.

## 18. Leaver: thu hồi cả Human access và Device access

Leaver là sự kiện có rủi ro cao: nếu tổ chức disable account nhưng máy vẫn có local admin, VPN certificate hoặc API credential, **quyền tồn dư có thể tiếp tục tồn tại**.

### 18.1. Những lớp cần xử lý

| Lớp | Thao tác cần xem | Xác minh |
| --- | --- | --- |
| **Human account** | IdP/directory disable, privileged grants, SSO access. | Account và effective permissions đúng. |
| **Device ownership** | Đánh dấu thu hồi tài sản, ngăn dùng thiết bị theo user cũ. | Asset/MDM state được đối soát. |
| **Device certificate/key** | Thu hồi/rotate credential theo ownership/lifecycle. | PKI/issuer/PEP không còn chấp nhận credential bị thu hồi. |
| **Device management** | Wipe/retire/reassign theo loại tài sản. | MDM job và trạng thái thực tế khi có thể kiểm. |
| **Network/remote access** | VPN/ZTNA device trust, sessions/cert. | Gateway không còn chấp nhận truy cập không hợp lệ. |
| **Application/API** | App-local sessions, PAT/API key, refresh/access tokens. | Resource/issuer đã vô hiệu hoặc hết hạn phù hợp. |
| **PAM/privileged access** | JIT eligibility, SSH keys, admin sessions. | Không còn đường đặc quyền gắn user cũ. |
| **Workload ownership** | Bàn giao job/credential độc lập nếu vẫn cần hoạt động. | Workload không phụ thuộc account Leaver. |

### 18.2. Lệnh remote wipe chưa chắc đã thành công

Thiết bị có thể offline hoặc không còn liên lạc UEM. Một lệnh **remote wipe queued/acknowledged** không chứng minh dữ liệu thật đã được xóa. Báo cáo phải phân biệt:

~~~text
WIPE_REQUESTED
WIPE_DELIVERED
WIPE_CONFIRMED_BY_PLATFORM
WIPE_UNVERIFIABLE
~~~

Với thiết bị không liên lạc, cần **chặn quyền truy cập server-side, revoke credential/session** và ghi rủi ro dữ liệu tại endpoint theo policy, không chờ wipe.

### 18.3. Leaver không đồng nghĩa tiêu hủy mọi thiết bị

Laptop công ty có thể được tái sử dụng sau khi đã xử lý dữ liệu, thu hồi credentials và re-enroll theo quy trình. Điều cần đóng là **mối liên hệ quyền tin cậy với Person/Engagement cũ**, không nhất thiết xóa mã tài sản.

## 19. Rehire, thiết bị dùng chung, Contractor và BYOD

### 19.1. Rehire

Một người trở lại làm việc có thể dùng email tương tự, nhưng **Engagement mới** cần được xác minh. Không tự khôi phục:

- Device certificate gắn với quyền cũ không còn hợp lệ.
- Device trust exception từng được phê duyệt.
- Admin/JIT eligibility hoặc quyền máy cục bộ.
- Refresh tokens, đăng nhập offline hoặc API credentials còn tồn.

Thiết bị do tổ chức cấp lại phải được kiểm ownership, security posture, và **authorization hiện tại**.

### 19.2. Contractor/partner

Đối tác có thể dùng thiết bị do tổ chức khác quản lý. Khi đó policy cần trả lời:

- Tổ chức có chấp nhận attestation hoặc compliance assertion từ **partner IdP/MDM** không?
- Trust anchor và federation mapping được phê duyệt thế nào?
- Có giới hạn role/resource và ngày kết thúc hợp đồng không?
- Khi partner đổi owner hoặc nhân sự nghỉ, tín hiệu revoke đến nhanh thế nào?
- Nếu không tin hoặc không quan sát posture partner, có thể dùng **VDI/ZTNA/proxy restricted session** không?

**Không mặc định tin hoàn toàn vào thuộc tính `managed=true` do đối tác tự khai** nếu chưa có trust agreement, issuer validation và phạm vi được quy định.

### 19.3. BYOD và quyền riêng tư

**Bring Your Own Device (BYOD)** đòi cân bằng bảo mật với quyền riêng tư:

| Cách tiếp cận | Ưu điểm | Giới hạn |
| --- | --- | --- |
| **Ứng dụng được quản lý** | Giới hạn dữ liệu công việc trong app/container được quản lý. | Khả năng kiểm toàn OS có thể giới hạn. |
| **Device enrollment** | Nhiều posture/management signals hơn. | Cần minh bạch những gì tổ chức thu thập và có thể xóa. |
| **VDI/browser isolation** | Dữ liệu nhạy cảm ở môi trường quản lý. | Không loại bỏ mọi rủi ro session/endpoint. |
| **Restricted web access** | Phù hợp dữ liệu thấp hơn, không cần quản lý toàn máy. | Có thể cấm download/export/local sync. |
| **Deny high-risk actions** | Bảo vệ tài nguyên khi thiếu evidence. | Phải có kênh hợp lệ để hoàn thành công việc. |

Không nên thu thập dữ liệu cá nhân ngoài mục đích như nội dung ảnh, tin nhắn, vị trí chi tiết hay file riêng tư chỉ để chứng minh compliance nếu không có căn cứ pháp lý/chính sách phù hợp. Hãy công bố **loại dữ liệu, lý do, quyền truy cập, giữ bao lâu và tác động khi unenroll**.

### 19.4. Shared/kiosk devices

Máy kiosk hoặc thiết bị chung có thể không có `ownerPersonId` duy nhất. Cần tách **asset owner/team** với **user của phiên hiện tại**, quản lý session separation, credential per-user và xóa dữ liệu phiên. Không dùng device certificate chung để thay xác thực từng nhân viên.

## 20. Device trust cho server, IoT/OT và endpoint không quản lý truyền thống

**Machine identity** không chỉ là laptop và điện thoại. Máy chủ, VM, thiết bị mạng, IoT và hệ thống OT có thể cần xác thực máy và đánh giá trust theo khả năng thực tế.

### 20.1. Những ràng buộc khác workstation

| Loại thiết bị | Bằng chứng phù hợp | Hạn chế phổ biến |
| --- | --- | --- |
| **Server/VM** | CMDB/host ID, certificate/mTLS, workload attestation, patch/EDR. | Ephemeral VM, auto-scaling và identity thay đổi nhanh. |
| **Kubernetes node** | Node identity, control-plane auth, admission/attestation theo thiết kế. | Node trust không tự chứng minh mọi pod được phép. |
| **Network appliance** | Device cert, signed firmware, config integrity, inventory. | Agent MDM/EDR có thể không được hỗ trợ. |
| **IoT sensor** | Hardware identity, certificate, firmware provenance, secure boot nếu có. | Tài nguyên hạn chế, cập nhật chậm, physical access risk. |
| **OT/industrial device** | Device identity, network segmentation, approved maintenance policy. | Availability/safety có thể ưu tiên, patch window nghiêm ngặt. |
| **BYOD mobile** | Managed app, platform integrity/attestation khi hỗ trợ. | Giới hạn quyền thu thập và quản trị toàn thiết bị. |

### 20.2. Không ép tất cả thiết bị phải có EDR/MDM desktop

Thiết bị IoT có thể không hỗ trợ EDR. Điều này không tự có nghĩa tổ chức phải cho phép không kiểm soát. Có thể áp **segmentation, mTLS, allowlisted services, firmware validation, gateway-based enforcement, physical inventory và time-bound exception**, tùy threat model và yêu cầu an toàn vận hành.

### 20.3. Lifecycle của máy ephemeral

VM/pod được tạo và xóa liên tục không nên sở hữu credential dài hạn gắn tên instance dễ tái sử dụng. Khi phù hợp, dùng **workload identity/token ngắn hạn** gắn với trust context của môi trường chạy. Device/node identity là một phần của quyết định; vẫn cần kiểm workload owner, service account và resource authorization riêng.

## 21. Thiết kế bảo mật liên kết Device trust với Workload identity

Một workload có thể xin credential từ một identity provider dựa trên:

1. **Workload identity**: service principal, namespace, service account hoặc workload selector được phép.
2. **Platform/host claims**: node/VM/cluster thuộc môi trường được tin cậy khi policy yêu cầu.
3. **Execution context**: image, deployment, trust domain, service owner và điều kiện thời gian.
4. **Cryptographic proof**: khóa/token/attestation đủ khả năng xác minh.
5. **Authorization**: workload chỉ nhận quyền cần thiết trên đúng API/resource.

### 21.1. Ví dụ role quá rộng

Một job **backup-reader** cần đọc dữ liệu sao lưu của một ứng dụng. Dù host đã được attested và có device certificate hợp lệ, **không được cấp cloud Owner toàn subscription**. Host trust và service identity chỉ là điều kiện, không thay yêu cầu **least privilege**.

### 21.2. Thiết bị khỏe nhưng workload không hợp lệ

Nếu node đạt posture nhưng pod được chạy với service account không có quyền hoặc image không được phê duyệt, token production vẫn phải bị từ chối. Ngược lại, workload identity hợp lệ nhưng host bị cách ly cũng có thể không đủ điều kiện cấp mới credential theo policy.

### 21.3. Machine-to-machine mTLS và trust domain

Trong service mesh hoặc hệ thống phân tán, mTLS có thể xác thực **service/workload identity** với chứng chỉ ngắn hạn. Nên ghi rõ **trust domain, certificate issuer, service identity, key rotation và scope authorization**; không tự kết luận đó là danh tính của **thiết bị vật lý** đang chạy.

## 22. Device trust trong quy trình IdP, SSO và SCIM

### 22.1. IdP và conditional access

IdP có thể lấy tín hiệu thiết bị từ UEM/MDM, yêu cầu `compliant device` hoặc kiểm device binding trong đăng nhập. Hệ thống cần phân biệt:

- **User token issued**: token đã được phát.
- **Device signal evaluated**: có kiểm và từ nguồn nào?
- **Device identity bound**: token/session thực sự được ràng buộc với device nào, nếu hệ thống hỗ trợ?
- **Resource authorization**: API có dùng kết quả đó để bảo vệ hành động không?

Một token hợp lệ nhưng **không có đủ device claims** không phải bằng chứng thiết bị đáng tin; một claim `compliant` cũ cũng không thay kiểm trạng thái hiện tại nếu policy yêu cầu re-evaluation.

### 22.2. SSO và session tồn dư

SAML/OIDC SSO thường thực hiện xác thực tại thời điểm phát assertion/token. Sau đó ứng dụng có thể có session riêng. Khi device chuyển `NONCOMPLIANT` hoặc `LOST`, **IdP block new sign-ins** không bảo đảm những phiên SaaS đã phát hành lập tức mất quyền.

Cần thiết kế:

1. Ngưỡng session lifetime và reauthentication theo rủi ro.
2. Token revocation/continuous access evaluation nếu hệ thống hỗ trợ.
3. Back-channel/front-channel logout hoặc app-specific session termination theo khả năng.
4. API authorization kiểm device context hoặc gateway enforcement khi cần.
5. Reconciliation và rủi ro giới hạn kỹ thuật nếu không thể đóng phiên tức thì.

### 22.3. SCIM không phải giao thức Device posture

**SCIM** chủ yếu chuẩn hóa provisioning **User/Group** và một số thuộc tính liên quan tại ứng dụng. Nó **không tự cung cấp hệ thống attestation, quản lý endpoint hay device posture**. Vì vậy:

- SCIM `active=false` có thể giúp disable app user nhưng không bảo đảm device cert bị thu hồi.
- Xóa Group qua SCIM không nhất thiết vô hiệu mọi session hoặc PAT.
- Device trust phải lấy từ **IdP/UEM/PKI/EDR/conditional access** và được hệ thống đích thực thi theo thiết kế.
- Quan hệ Person–Account–Device có thể cần inventory/linking riêng, không mặc định có trong SCIM User.

### 22.4. RBAC/ABAC và thiết bị

RBAC xác định quyền dựa role, còn ABAC có thể thêm điều kiện:

~~~text
ALLOW report.export
IF subject.role includes "finance-exporter"
AND subject.engagementState == ACTIVE
AND device.trustDecision == ACCEPTABLE_FOR_HIGH_RISK
AND deviceEvidence.fresh == true
AND resource.tenantId == subject.authorizedTenant
AND session.authStrength satisfies policy
~~~

Đây là **rule mô tả**, không phải policy syntax của engine cụ thể. Nếu thiếu một bằng chứng bắt buộc, hệ thống cần quyết định **UNKNOWN/DENY/RESTRICT** theo độ nhạy; không suy ra ALLOW do dữ liệu vắng mặt.

## 23. Threat model: Device trust có thể bị vượt qua thế nào?

| Mối đe dọa | Biểu hiện/rủi ro | Hướng phòng vệ |
| --- | --- | --- |
| **Device spoofing** | Client giả hostname, IP, MDM ID hoặc headers. | Proof-of-possession, signed/asserted device evidence, server-side lookup. |
| **Credential theft/cloning** | Khóa thiết bị hoặc certificate bị sao chép/dùng trái phép. | Hardware-backed keys khi phù hợp, revocation, rotation và key-use monitoring. |
| **Stale compliance** | Tín hiệu “healthy” còn trong cache khi máy đã bị xâm nhập. | Freshness TTL, event propagation, risk re-evaluation. |
| **Malicious enrolled device** | Máy được quản lý nhưng có malware. | EDR/attestation/behavior signals và least privilege. |
| **Compromised admin/UEM** | Kẻ tấn công sửa posture/ownership hoặc policy từ control plane. | SoD, privileged access review, audit/immutable logs, bảo vệ management plane. |
| **Lost/stolen device** | Máy vẫn giữ session/certificate. | Asset incident, credential/session revocation, device risk deny. |
| **Token replay** | Token bị lấy từ máy hợp lệ và dùng ở client khác. | Sender-constrained token khi hỗ trợ, short TTL, audience/scope và resource checks. |
| **Trust assertion forgery** | App tin `trusted=true` từ request header. | Chỉ chấp nhận assertion từ trusted proxy/issuer, verify integrity. |
| **Cross-tenant confusion** | Device ID/chứng chỉ được nhận sai namespace. | Issuer/tenant namespace và strict resource mapping. |
| **Enrollment abuse** | Thiết bị giả đăng ký như asset hợp lệ. | Enrollment authorization, hardware/ownership verification, anomaly alerts. |
| **Offline device** | MDM không còn nhận telemetry, lệnh wipe chưa chạy. | Server-side deny, mark stale, revoke credentials. |
| **Physical compromise** | Thiết bị IoT bị can thiệp vật lý, khóa/firmware bị thay. | Tamper controls, firmware validation, segmentation, asset inspection. |

**Không có tín hiệu đơn lẻ nào giải quyết mọi rủi ro**. Sự kết hợp cần dựa vào loại endpoint, dữ liệu, khả năng của nền tảng và chi phí vận hành.

## 24. Thu hồi Device trust: quyết định, chứng chỉ, phiên và quyền thực tế

Thu hồi trust không phải một lệnh duy nhất. Khi thiết bị bị mất, không còn compliant hoặc chấm dứt sử dụng, cần xử lý **nhiều đường truy cập**.

### 24.1. Chuỗi xử lý đề xuất

~~~mermaid
flowchart TD
    A["Lost / Risk / Retire / Leaver event"] --> B["Resolve deviceId + owner<br/>affected accounts + sessions"]
    B --> C["Mark device REVOKED/UNTRUSTED<br/>in authoritative registry"]
    C --> D["Notify IdP / Conditional Access<br/>ZTNA / APIs"]
    C --> E["Revoke certificates / keys<br/>and workload credentials"]
    C --> F["Terminate/limit sessions<br/>tokens where supported"]
    C --> G["MDM wipe/isolate when appropriate<br/>record delivery/confirmation"]
    D --> H["Readback target states<br/>test authorized access paths"]
    E --> H
    F --> H
    G --> H
    H --> I{"All required paths verified?"}
    I -->|"Yes"| J["REVOKED_VERIFIED<br/>Audit + close"]
    I -->|"No"| K["Exception / Incident<br/>owner + mitigation + dueAt"]
    K --> H
~~~

### 24.2. Các lớp thu hồi

| Lớp | Trạng thái nên đối soát | Những điều có thể chưa hoàn tất |
| --- | --- | --- |
| **Device registry** | Device state LOST/REVOKED/RETIRED. | PEP khác chưa biết trạng thái mới. |
| **IdP/conditional access** | Device bị block cho sign-in mới. | Session SSO cũ vẫn còn. |
| **PKI** | Certificate revoked/expired, CA/status được cập nhật. | CRL/OCSP cache hoặc PEP không kiểm revocation. |
| **MDM/UEM** | Unenroll/retire/wipe queued/confirmed. | Thiết bị offline chưa nhận lệnh. |
| **EDR/ZTNA** | Isolation hoặc access policy đã áp dụng. | Một đường API không đi qua ZTNA. |
| **SaaS/app** | Session/role/token bị chặn theo cơ chế hỗ trợ. | App-local password và PAT riêng. |
| **Cloud/workload** | Temporary credentials, role assumption, trust policy được kiểm. | Token cũ còn hạn hoặc service principal độc lập. |

### 24.3. Kết luận VERIFIED phải có scope

~~~text
Device D-101:
  IdP new sign-in: DENIED_VERIFIED
  VPN mTLS certificate: REVOKED_VERIFIED
  SaaS A session: TERMINATED_VERIFIED
  SaaS B local session: UNVERIFIABLE
  MDM wipe: REQUESTED_DEVICE_OFFLINE

=> Không được báo “mọi đường truy cập đã thu hồi 100%”.
~~~

Đối với SaaS B và wipe offline, ghi **owner, severity, hạn xử lý và biện pháp giảm thiểu**; có thể chặn phía resource/network, rút ngắn session lifetime hoặc xử lý credential theo những gì hệ thống hỗ trợ.

### 24.4. Đừng chờ thiết bị online để chặn server-side

Remote wipe hoặc EDR isolate cần máy liên lạc được. Khi máy mất cắp và offline, ưu tiên **server-side deny, IdP device state, certificate/key revocation, gateway/app sessions và PAT** theo chính sách. Dữ liệu nằm cục bộ trên máy vẫn cần được đánh giá theo tình trạng disk encryption và exposure.

## 25. Hành động khi phát hiện máy không còn đáng tin

### 25.1. Luồng điều tra và giảm thiểu

1. **Xác định tín hiệu:** EDR HIGH_RISK, mất máy, MDM stale, attestation failed, enrollment lạ...
2. **Kiểm nguồn và thời điểm:** deviceId, tenant, source trust, observedAt, risk level, có false positive hoặc dữ liệu thiếu không?
3. **Xác định tác động:** user/workload nào, sessions/tokens nào, tài nguyên nào có thể truy cập?
4. **Áp policy tạm:** DENY/RESTRICT/quarantine hoặc yêu cầu khắc phục theo mức rủi ro.
5. **Điều tra nguyên nhân:** malware, mất asset, agent lỗi, OS patch chậm, key compromise, cấu hình trust.
6. **Sửa nguồn gốc:** patch, recover endpoint, rotate keys, re-enroll hoặc thay thiết bị khi cần.
7. **Xác minh thực tế:** readback MDM/IdP/PEP và kiểm đường truy cập theo kịch bản được ủy quyền.
8. **Audit và re-enable:** chỉ khôi phục trust khi có bằng chứng đáp ứng policy; không chỉ đổi boolean thủ công.

### 25.2. Phân biệt lỗi posture thông thường với security incident

| Tình huống | Có thể xử lý như | Tối thiểu cần |
| --- | --- | --- |
| Máy chưa cập nhật bản vá nhưng trong grace window. | Remediation theo chính sách cập nhật. | Độ tươi, mức rủi ro tài nguyên. |
| Device MDM check-in muộn do mạng lỗi. | UNKNOWN/STALE, kiểm lại kết nối. | Không mặc định compliant. |
| EDR xác nhận hành vi mã độc nguy cơ cao. | Security incident/containment. | Hạn chế truy cập, evidence preservation. |
| Private key thiết bị nghi bị lộ. | Credential incident. | Revoke/rotate, đánh giá token/session và các lần sử dụng. |
| Laptop bị mất có dữ liệu nhạy cảm. | Asset/security/privacy incident tùy policy. | Chặn truy cập, kiểm mã hóa và nghĩa vụ báo cáo áp dụng. |
| Nhân viên Leaver không trả thiết bị. | Offboarding/asset recovery và security assessment. | Chặn server-side, ghi rủi ro và thu hồi tài sản. |

### 25.3. Tránh làm mất bằng chứng

Nếu nghi bị xâm nhập, việc wipe ngay có thể làm mất chứng cứ cần thiết. Quy trình ứng cứu cần cân bằng **ngăn chặn rủi ro, bảo vệ dữ liệu và bảo toàn chứng cứ**. Không tự ý xóa log hoặc bằng chứng endpoint chỉ để đưa trạng thái về compliant.

## 26. Quản lý trust khi nguồn dữ liệu lỗi hoặc không đồng bộ

Trong thực tế, MDM, EDR, IdP, PKI, ZTNA và ứng dụng có độ trễ khác nhau.

### 26.1. Những trạng thái khó

| Kịch bản | Rủi ro | Cách xử lý chính sách |
| --- | --- | --- |
| **MDM outage** | Không lấy compliance mới. | UNKNOWN/STALE, hạn chế theo mức độ nhạy cảm và continuity. |
| **EDR feed delayed** | Risk HIGH chưa tới IdP. | Event integration, freshness threshold và audit delay. |
| **CA/OCSP unavailable** | Không kiểm được revocation hiện tại. | Quy định riêng về fail behavior theo rủi ro, không coi revocation check đã pass. |
| **Device enrollment pending** | Device record có nhưng key chưa xác minh. | Không cấp trust cao khi proof chưa hoàn tất. |
| **Conflicting records** | MDM nói compliant, asset registry nói stolen. | Đặt precedence theo source authority và risk; không lấy trung bình vô nghĩa. |
| **Out-of-order JML events** | Mover cũ ghi đè Leaver mới. | Source version, effectiveAt, idempotency, reconciliation. |
| **Token issued before risk signal** | Phiên cũ tiếp tục hoạt động. | Session enforcement, token lifetime và revocation capability. |
| **Time skew** | Attestation/chứng chỉ bị kiểm sai hạn. | Đồng bộ thời gian, timezone và trusted timestamp. |

### 26.2. Fail-closed và fail-open phải nói đúng phạm vi

“Fail closed” không nhất thiết nghĩa **cắt mọi hệ thống** khi MDM chậm 10 phút; với dịch vụ cứu hộ hoặc OT, availability cũng có thể là yêu cầu an toàn. Chính sách cần nêu:

- **Tài nguyên cực nhạy:** DENY hoặc chỉ cho phương án đã được phê duyệt khi evidence thiếu.
- **Tài nguyên rủi ro thấp:** có thể cho quyền hạn chế/TTL ngắn nếu policy cho.
- **Sự cố continuity:** dùng kênh emergency được kiểm soát, audit, time limit và post-event review.
- **Mọi trường hợp:** ghi UNKNOWN, không biến thiếu tín hiệu thành `compliant=true`.

### 26.3. Phân biệt sự kiện đến muộn và trạng thái hiện hành

~~~text
09:00  D-101: COMPLIANT (MDM version 104).
09:10  D-101: LOST, policy chặn (asset version 22).
09:12  Một job cũ gửi lại COMPLIANT từ 09:00.

Kết quả đúng:
    D-101 vẫn bị chặn.
    Event MDM cũ không đảo được trạng thái LOST hiện hành.
~~~

Thực thi cần **source-of-authority precedence, version/timestamp và quy trình giải quyết xung đột**. Không chỉ ghi bản tin tới cuối vào một trường `trusted`.

## 27. Mô hình dữ liệu device trust và audit

### 27.1. Những thực thể cần giữ riêng

| Entity | Dữ liệu tiêu biểu | Vai trò |
| --- | --- | --- |
| **DeviceRecord** | deviceId, tenant, platform, lifecycleState, registeredAt. | Danh tính thiết bị. |
| **AssetAssignment** | assetId, ownerPerson/Team, engagement, assignedAt, returnedAt. | Quyền sở hữu và bàn giao. |
| **Enrollment** | mdmRecordId, enrollmentMethod, managementState, policyVersion. | Quản lý thiết bị. |
| **DeviceCredential** | credentialId, key type, cert issuer/serial, expiry/revocationRef. | Chứng thực possession. |
| **PostureEvidence** | source, observedAt, receivedAt, signals, evidenceTTL. | Bằng chứng tình trạng. |
| **AttestationEvidence** | verifier, claims/measurements, nonceRef, trustAnchorRef, verifiedAt. | Phạm vi đo lường/attestation. |
| **DeviceTrustDecision** | decisionId, deviceId, resource/action, result, policyVersion, asOf. | Quyết định theo ngữ cảnh. |
| **SessionBinding** | sessionId, deviceId, user/workloadId, issuedAt, expiresAt. | Liên kết phiên và thiết bị nếu có. |
| **RevocationTask** | target, action, requestedAt, providerResponse, verifiedAt. | Thu hồi nhiều đích. |
| **RiskException** | reason, riskOwner, controls, expiresAt, status. | Xử lý đường chưa thể kiểm. |

### 27.2. Ví dụ JSON giả định

~~~json
{
  "eventType": "DEVICE_TRUST_DECISION",
  "decisionId": "device-dec-202612-0142",
  "deviceId": "corp-device-0101",
  "tenantId": "tenant-a",
  "assetId": "asset-laptop-108",
  "ownerSubjectId": "person-1042",
  "engagementId": "EMP-5812",
  "lifecycleState": "ASSIGNED",
  "deviceCredentialRef": "cert-ref-411",
  "managementState": "MANAGED",
  "posture": {
    "compliance": "COMPLIANT",
    "edrRisk": "LOW",
    "diskEncryption": "ENABLED",
    "observedAt": "2026-12-01T08:58:00+07:00",
    "source": "uem-and-edr",
    "policyVersion": "device-baseline-v7"
  },
  "resourceId": "finance-reporting",
  "action": "report.export",
  "subjectAuthorization": "PERMITTED",
  "deviceDecision": "ACCEPTED_FOR_RESOURCE",
  "decisionAt": "2026-12-01T09:00:00+07:00",
  "accessPolicyVersion": "conditional-access-v12",
  "evidenceRefs": ["posture-881", "device-proof-219"]
}
~~~

Schema trên chỉ là **ví dụ nội bộ**, không phải response chuẩn của IdP, SCIM, MDM hay X.509. `ACCEPTED_FOR_RESOURCE` mang nghĩa **tài nguyên/hành động cụ thể ở thời điểm đó**, không đồng nghĩa thiết bị trở nên tin cậy toàn cục.

### 27.3. Các quy tắc bảo đảm dữ liệu

~~~text
deviceTrustDecision must reference trusted evidence source
deviceTrustDecision must include policyVersion + evaluatedAt
deviceId must be namespaced by issuer/tenant
posture.evidenceAge must satisfy policy freshness
REVOKED device cannot become trusted from stale COMPLIANT event
VERIFIED revocation requires target evidence, not only task ACK
owner reassign must preserve identity/audit history, not blindly transfer keys
~~~

Đây là **invariants thiết kế**, không phải cú pháp của một chuẩn duy nhất. Hệ thống cần bổ sung concurrency/version control và quy trình correction khi nguồn authoritative thay đổi.

## 28. Case study 1 – Nhân viên đúng danh tính, laptop không đáng tin

**Bối cảnh giả định:** Lan là nhân viên Finance ACTIVE, có `report.export`. Lan đăng nhập SSO bằng MFA từ một laptop cá nhân mới không đăng ký UEM để xuất dữ liệu nhạy cảm.

### 28.1. Các tín hiệu

| Dữ liệu | Kết quả giả định |
| --- | --- |
| User authentication | Thành công, MFA đạt. |
| HRIS/Engagement | ACTIVE. |
| Role/authorization | `report.export` đúng tenant. |
| Device identity | Chưa có device record đáng tin. |
| Device management | Unmanaged. |
| EDR/posture evidence | Không có, không thể xác minh. |
| Resource sensitivity | High: export dữ liệu khách hàng. |

### 28.2. Quyết định và phương án

**Không nên:** “User MFA đã đúng nên cho phép export”. Device trust thiếu bằng chứng theo chính sách high-risk.

**Có thể:** deny export từ máy chưa đủ điều kiện, đồng thời cho đường hợp lệ: laptop được quản lý, VDI được bảo vệ hoặc chính sách app-managed cụ thể. Nếu tài nguyên thấp hơn, có thể cho read-only khi policy cho.

### 28.3. Bài học

Device trust không thay user authorization, nhưng **quyền user có sẵn cũng không mặc nhiên bỏ qua rủi ro endpoint**. Cần biết cấp bằng chứng nào được yêu cầu cho từng loại hành động.

## 29. Case study 2 – Laptop compliant bị mất sau Leaver

**Bối cảnh giả định:** nhân viên Minh kết thúc công việc lúc 17:00, nhưng chưa trả laptop công ty. MDM vẫn ghi COMPLIANT từ 16:45; thiết bị đã offline. Một VPN certificate còn hạn đến tháng sau.

### 29.1. Dòng thời gian

| Thời điểm giả định | Sự kiện | Ý nghĩa |
| --- | --- | --- |
| **16:45** | MDM ghi COMPLIANT. | Chỉ là snapshot trước Leaver. |
| **17:00** | HRIS phát Leaver có hiệu lực. | User entitlement không còn hợp lệ. |
| **17:01** | IdP disable account. | Chặn nhiều đường đăng nhập mới, chưa chắc mọi session. |
| **17:03** | Asset owner ghi laptop chưa trả, status LOST_PENDING. | Cần quản trị rủi ro tài sản. |
| **17:04** | UEM gửi remote wipe, device offline. | WIPE_REQUESTED, chưa verified. |
| **17:05** | PKI đưa device certificate vào quy trình revoke. | Cần kiểm gateway đã nhận trạng thái. |
| **17:08** | VPN/ZTNA readback từ chối credential bị thu hồi. | Xác minh một đường truy cập. |
| **17:10** | SaaS A session chưa được xác minh đóng. | Exception cần owner, không giả định an toàn. |

### 29.2. Điều phải báo cáo

~~~text
Person/Engagement: TERMINATED
Device asset status: NOT_RETURNED / AT_RISK
IdP user: DISABLED_VERIFIED
VPN cert: REVOKED_VERIFIED (tại gateway được kiểm)
MDM wipe: REQUESTED, device offline
SaaS session: UNVERIFIABLE
Risk exception: OPEN với owner và mitigation
~~~

**Không nên:** “Device trust vẫn PASS vì MDM compliant” hoặc “Đã xóa dữ liệu vì wipe request gửi thành công”.

### 29.3. Bài học

**Lifecycle Leaver có thể làm mất tư cách truy cập nhanh hơn độ trễ posture telemetry.** Quyền và trust phải được điều chỉnh dựa trên cả nguồn HRIS và asset/security, không phụ thuộc một boolean của MDM.

## 30. Case study 3 – Máy chủ có chứng chỉ hợp lệ nhưng host risk tăng

**Bối cảnh giả định:** một VM chạy `orders-service` có chứng chỉ mTLS còn hạn và workload principal được phép gọi `payments-api`. EDR báo hành vi bất thường sau khi VM bị can thiệp, nhưng mTLS handshake vẫn thành công.

### 30.1. Các lớp quyết định

| Lớp | Trạng thái | Kết luận |
| --- | --- | --- |
| **Workload identity** | `orders-service` hợp lệ. | Service principal đã được xác thực theo trust. |
| **mTLS** | Handshake thành công. | Key/chứng chỉ được chấp nhận; chưa nói host an toàn. |
| **Host/Device posture** | EDR HIGH_RISK. | Không thỏa điều kiện truy cập nhạy cảm theo policy. |
| **Authorization** | Service được phép gọi một tập API. | Không đồng nghĩa mọi request lúc này được cho qua. |
| **PEP** | Cần kiểm risk signal và deny/restrict. | Chính nơi thực thi quyết định cuối. |

### 30.2. Xử lý hợp lý

1. Xác minh alert và mức rủi ro, liên kết đúng VM/node.
2. Giới hạn kết nối/credential theo incident runbook, tránh làm lan rộng sự cố.
3. Xử lý VM: isolate/rebuild từ image được phê duyệt nếu cần.
4. Xoay hoặc thu hồi credentials nghi bị lộ, không chỉ chờ certificate expiry.
5. Kiểm lại workload identity, host trust và service authorization.
6. Chỉ mở lại quyền sau khi evidence và policy đạt.

**Bài học:** **mTLS authenticated** không đồng nghĩa **trusted host** hoặc **authorized action at this moment**.

## 31. Case study 4 – Bàn giao máy từ SRE sang Finance

**Bối cảnh giả định:** một laptop được giao cho nhân viên SRE A với local admin tools và cấu hình SSH phục vụ production. Sau khi A Mover, laptop được bàn giao cho nhân viên Finance B. Asset registry chỉ đổi tên owner, còn OS profile, SSH key và device certificate cũ vẫn tồn tại.

### 31.1. Những câu hỏi cần trả lời

- Laptop vẫn có deviceId cũ; credential này xác thực **thiết bị** hay **người A**?
- SSH keys có liên kết với account/role SRE của A không?
- Local admin grants và privileged sessions còn tồn tại không?
- Dữ liệu công việc cũ đã được xử lý đúng retention/privacy policy chưa?
- Person B có đủ điều kiện dùng máy và policy bảo mật của Finance không?
- Cách re-enroll/re-key theo thiết kế có để lại hai đường credential song song không?

### 31.2. Kết quả cần đạt

Sau bàn giao, hệ thống nên có:

1. Owner mới được xác minh từ asset/HRIS.
2. Dữ liệu/profile/credential của A được xử lý theo chính sách.
3. Device re-enrollment, key/certificate rotation/rebinding nếu trust model yêu cầu.
4. Local admin, SSH keys, PAM eligibility và sessions của A được thu hồi.
5. Device posture được đánh giá lại và các ứng dụng chỉ cấp quyền của B.
6. Audit giữ lịch sử chủ sở hữu cũ **không phải để cấp quyền tiếp cho A**.

**Bài học:** “máy vẫn compliant” không chứng minh **bàn giao quyền, bí mật và dữ liệu** đã được thực hiện.

## 32. Kiểm thử Device trust: từ chứng chỉ tới quyền thực tế

Một policy device trust chưa thể xem là hiệu quả nếu chỉ kiểm UI hiển thị “Managed”. Cần **negative tests, positive tests, boundary tests, outage tests và reconciliation** ở đúng PEP.

### 32.1. Ma trận kiểm thử gợi ý

| Test ID | Tiền điều kiện | Hành động kiểm thử trong môi trường được phép | Expected |
| --- | --- | --- | --- |
| **DT-01** | User ACTIVE, managed/compliant, có role phù hợp. | Truy cập tài nguyên đúng scope. | ALLOW với audit/policy version. |
| **DT-02** | User ACTIVE, managed/compliant, không có quyền nghiệp vụ. | Gọi API thuộc role khác. | DENY vì authorization. |
| **DT-03** | User ACTIVE, device unregistered. | Yêu cầu export dữ liệu high-risk. | DENY/RESTRICT theo policy. |
| **DT-04** | Device managed nhưng NONCOMPLIANT. | Đăng nhập admin console. | DENY/REMEDIATE theo policy. |
| **DT-05** | Device evidence quá TTL. | Dùng session token trước đó. | Re-evaluate/RESTRICT/DENY theo resource risk. |
| **DT-06** | Device status LOST/REVOKED. | Dùng device certificate cũ qua gateway. | DENY nếu PEP kiểm revocation đúng. |
| **DT-07** | Certificate đã hết hạn. | Thử xác thực mTLS. | DENY do certificate validity. |
| **DT-08** | Certificate còn hạn nhưng CA/issuer không tin. | Thử xác thực mTLS. | DENY, không chấp nhận trust chain. |
| **DT-09** | Certificate thuộc tenant-b. | Yêu cầu resource tenant-a. | DENY nếu trust policy không cho cross-tenant. |
| **DT-10** | Client có deviceId tự khai nhưng không có key proof. | Gửi claim `trusted=true`. | DENY/UNKNOWN, không tin client. |
| **DT-11** | User đã TERMINATED, máy vẫn compliant. | Thử truy cập tài nguyên. | DENY do user lifecycle. |
| **DT-12** | Mover đã bỏ role admin, máy vẫn compliant. | Thử action admin. | DENY do entitlement mới. |
| **DT-13** | Device EDR HIGH_RISK sau khi sign-in. | Dùng session cũ vào dữ liệu nhạy cảm. | Chặn hoặc ghi rõ hạn chế/độ trễ enforcement. |
| **DT-14** | MDM outage, không có posture mới. | Yêu cầu resource high-risk. | UNKNOWN được xử lý theo policy, không tự PASS. |
| **DT-15** | Reassignment device A → B. | Dùng credential/session của A. | Không còn quyền của A. |
| **DT-16** | BYOD không managed nhưng có user MFA. | Read low-risk vs export high-risk. | Kết quả khác nhau theo resource policy. |
| **DT-17** | Host healthy nhưng workload principal không có role. | Gọi protected API. | DENY vì workload authorization. |
| **DT-18** | Workload được cấp role nhưng host attestation fail. | Yêu cầu credential production khi policy đòi host trust. | DENY/QUARANTINE theo policy. |
| **DT-19** | Device cert đã revoke, PEP dùng cache cũ. | Kiểm access/revocation propagation. | Phát hiện window và mitigation; không tuyên bố revoke tức thời. |
| **DT-20** | Device mất kết nối và wipe đang queued. | Kiểm gateway/API access. | Chặn server-side; wipe vẫn PENDING. |
| **DT-21** | IdP báo compliance mới nhưng app vẫn giữ session cũ. | Kiểm quyền API ở app. | Đúng contract thực thi, ghi chưa được verify nếu không thể kiểm. |
| **DT-22** | Thiết bị ký challenge với khóa không khớp bản ghi. | Device authentication. | DENY, không chấp nhận tự khai identity. |

Các expected outcome là **mục tiêu thử nghiệm theo chính sách minh họa**, không phải response code chung của mọi IdP/UEM/PEP. Một policy cho phép restricted access khi posture thiếu sẽ cần test expected `RESTRICT` thay vì `DENY`.

### 32.2. Chứng minh quyết định và trạng thái đích

Một test điển hình cần ghi:

~~~text
Test case ID: DT-06
Policy: DEVICE-ACCESS-HIGH-RISK / version 12
Subject: test-person-1042 (ACTIVE)
Device: test-device-0101 (REVOKED)
Credential: cert-ref-411 (revoked)
Resource: staging-admin-api
Expected: DENY
Actual at IdP/PEP: DENY
Session: blocked/terminated within documented scope
Evidence: traceId + gateway log + device registry readback
Cleanup: verified, no test privileges remain
~~~

**Không chỉ kiểm HTTP 403 hoặc UI thông báo.** Cần xác định hệ thống có thực sự không tạo phiên/token/quyền mới, có audit đúng actor/device và có đường truy cập thay thế không được bảo vệ hay không.

### 32.3. Kiểm thử attestation

Với hệ thống hỗ trợ attestation, nên kiểm các tình huống:

- Evidence đúng chain/nonce, device binding, acceptable measurement → có thể PASS theo policy.
- Nonce cũ bị replay → từ chối.
- Chữ ký/chứng chỉ/issuer không hợp lệ → từ chối.
- Attestation evidence thuộc device khác hoặc tenant khác → từ chối.
- Measurement/firmware không được chấp nhận → xử lý theo risk.
- Platform không hỗ trợ attestation → không tự giả evidence PASS.
- Evidence đã quá thời hạn → yêu cầu đánh giá mới.

**Attestation verifier phải có trust roots và logic kiểm riêng**. Nếu unit test sử dụng cùng một hàm làm expected oracle và actual evaluator, có thể bỏ sót lỗi trong cả hai.

### 32.4. Test theo thời gian và concurrency

Test những trường hợp:

1. Device bị LOST đúng lúc conditional access cấp token.
2. Certificate bị revoke trong khi mTLS session dài đang mở.
3. HRIS Leaver đến sau khi IdP phát token.
4. MDM compliance event cũ được replay sau risk/quarantine event mới.
5. Hai tenant cùng phát device ID dạng chuỗi giống nhau.
6. UEM re-enrollment tạo record mới, record cũ còn tin cậy.
7. Role mới được cấp trong khi device trust bị hạ xuống.

Kỳ vọng tổng quát: **không có sự kiện hoặc approval cũ được phép ghi đè trạng thái chặn hiện hành**; nếu cần giới hạn tạm vì eventual consistency, phải có SLA và bằng chứng cửa sổ rủi ro.

### 32.5. Bảo vệ môi trường kiểm thử

Không đánh cắp thiết bị thật, làm hỏng máy, phát tán mã độc hoặc cô lập hệ thống production chỉ để test. Dùng **fixture, máy thử nghiệm, mock posture, CA thử nghiệm, tenant staging và kiểm thử được ủy quyền**. Mọi certificate/credential/device principal test phải được dọn và đối soát sau khi chạy.

## 33. Audit, reporting và KPI cho Device trust

### 33.1. Nhật ký cần trả lời gì?

Một quyết định trust nên truy vết được:

1. **Ai/Workload nào** yêu cầu action, với user/account ID đáng tin?
2. **Device nào** tham gia, được chứng minh bằng credential/key/attestation nào?
3. **Nguồn posture nào** được dùng, cập nhật lúc nào, policy version nào?
4. **Resource/action nào** được yêu cầu và role/ABAC điều kiện nào áp dụng?
5. **PDP đã trả kết quả gì**, vì sao (reason code) và PEP đã thực thi thế nào?
6. Khi device bị LOST/REVOKED/NONCOMPLIANT, những **session/token/cert** nào đã bị xử lý?
7. Có **đường nào không thể quan sát**, exception nào còn mở, owner và hạn xử lý không?

### 33.2. Các KPI hữu ích

| KPI | Cách tính/diễn giải | Điều phản ánh |
| --- | --- | --- |
| **Managed device coverage** | Thiết bị thuộc phạm vi phải quản lý đã enrolled ÷ population phải quản lý. | Độ bao phủ UEM, không là tỷ lệ an toàn tuyệt đối. |
| **Trusted device decision coverage** | Quyết định thuộc policy có đủ identity + posture evidence ÷ quyết định thuộc phạm vi. | Độ hoàn chỉnh kiểm soát trust. |
| **Posture freshness compliance** | Evidence nằm trong TTL ÷ evidence dùng cho quyết định cần tươi. | Khả năng dùng dữ liệu hiện hành. |
| **High-risk devices with access** | Device HIGH_RISK vẫn có đường truy cập nhạy cảm được xác minh. | Rủi ro cần xử lý khẩn. |
| **Unknown/stale posture rate** | Quyết định thiếu posture tươi ÷ quyết định thuộc phạm vi. | Telemetry gap. |
| **Device identity mapping coverage** | Device/asset liên kết owner/workload đáng tin ÷ thiết bị thuộc diện bắt buộc. | Rủi ro orphan/shared mapping. |
| **Certificate expiry/revocation hygiene** | Credentials hết hạn hoặc phải revoke nhưng vẫn được chấp nhận. | Chất lượng PKI và PEP revocation. |
| **Revocation verification latency** | `verifiedAt - requiredRevokeAt` theo risk tier. | Thời gian rủi ro tồn dư. |
| **Session residual access** | Session/token vẫn thực thi sau device revoke/lifecycle event. | Hiệu lực enforcement. |
| **Lost/retired devices still accepted** | Các thiết bị đã LOST/RETIRED còn được PEP chấp nhận. | Device lifecycle drift. |
| **JML device offboarding completion** | Leaver/transfer có device-access paths được verified ÷ đường bắt buộc. | Khép kín quyền nhân sự và thiết bị. |
| **Unmanaged high-risk access attempts** | Yêu cầu từ device không đáp ứng policy tới resource nhạy cảm. | Phơi lộ/người dùng cần remediation. |
| **Posture recovery time** | Thời gian từ NONCOMPLIANT tới VERIFIED compliant. | Khả năng hỗ trợ người dùng. |
| **Exception aging** | Số exception trust quá hạn, thiếu owner hoặc mitigation. | Nợ rủi ro. |
| **Test cleanup completeness** | Credential/session test được confirmed revoked ÷ tổng fixture tạo. | Kiểm soát môi trường thử nghiệm. |

### 33.3. Báo cáo phải ghi phạm vi và mẫu số

Nếu một tổ chức có 500 laptop managed và 1.000 thiết bị BYOD chưa thuộc chương trình quản lý, không thể báo “100% thiết bị tuân thủ” chỉ vì **500/500 laptop managed compliant**. Phải chỉ rõ **device population, BYOD/IoT coverage, tenant, platform, time range và thiết bị không có telemetry**.

### 33.4. Mẫu báo cáo vận hành

~~~text
DEVICE TRUST – OPERATIONAL REPORT (ILLUSTRATIVE)
As-of: 2026-12-01 10:00 +07:00
Scope: Managed corporate laptops at tenant-a only

In-scope devices: 500
Managed/enrolled: 490
Compliant with fresh evidence: 461
Noncompliant: 19
Posture unknown/stale: 10
Not enrolled: 10

Untrusted devices with confirmed active sensitive access: 3
Lost devices with revocation not fully verified: 2
Open certificate/session revocation exceptions: 4

Immediate actions:
  - Block/contain confirmed high-risk access.
  - Resolve missing enrollment and stale posture.
  - Verify pending certificate/session revocation.
  - Review scope not covered: BYOD, IoT, workloads.
~~~

Các số **chỉ minh họa**, không phải số liệu của tổ chức thật. 490 thiết bị managed được chia thành 461 compliant + 19 noncompliant + 10 unknown/stale. Không tự kết luận 461/500 là “overall security level”, vì outcome còn phụ thuộc authorization, tài nguyên, phiên và những thiết bị ngoài population.

## 34. Operating model và phân công trách nhiệm

| Vai trò | Trách nhiệm |
| --- | --- |
| **IAM/IdP owner** | Device/subject correlation, conditional access và token/session enforcement. |
| **UEM/MDM owner** | Enrollment, baseline, compliance signals, quarantine/wipe workflow. |
| **Endpoint/SOC/EDR owner** | Threat telemetry, incident triage, isolation và recovery. |
| **PKI/certificate owner** | Issuance, device binding, rotation, CA trust và revocation. |
| **Asset/IT owner** | Thiết bị giao/thu hồi, bàn giao, inventory và disposal. |
| **HR/JML owner** | Engagement effectiveAt, manager, Joiner/Mover/Leaver events. |
| **Application/resource owner** | Mức độ nhạy cảm tài nguyên, PEP enforcement, khả năng thu hồi session. |
| **Cloud/workload owner** | Host/workload trust, service credential và least privilege. |
| **Security governance** | Risk-tier policy, exception, SoD, audit requirements. |
| **Privacy/compliance** | Kiểm mục đích dữ liệu device, BYOD disclosure và retention theo quy định. |

### 34.1. Định nghĩa nguồn có thẩm quyền theo từng thuộc tính

Không phải mọi đội cùng là “owner” của một cờ tổng hợp:

- HRIS là nguồn có thẩm quyền về **Engagement** nếu tổ chức quy định vậy.
- Asset inventory chịu trách nhiệm **bàn giao vật lý**.
- MDM/UEM chịu trách nhiệm **enrollment/compliance evidence**.
- EDR chịu trách nhiệm **threat telemetry**.
- PKI/issuer chịu trách nhiệm **credential issuance/revocation**.
- IdP/PEP chịu trách nhiệm **thực thi policy tại điểm được tích hợp**.

Khi tín hiệu mâu thuẫn, cần quy tắc **precedence theo loại trạng thái và rủi ro**, chứ không chọn hệ thống vừa cập nhật gần nhất một cách máy móc.

### 34.2. Change management

Thay **compliance policy, CA trust, conditional-access policy, role catalog, MDM connector hoặc session TTL** có thể ảnh hưởng hàng nghìn người. Trước thay đổi, cần:

1. Impact analysis theo hệ điều hành, thiết bị, role, app và risk tier.
2. Thử nghiệm trên tenant/nhóm nhỏ được phép.
3. Kiểm cả **người hợp lệ vẫn vào được** và **thiết bị không hợp lệ bị chặn**.
4. Kế hoạch rollback/continuity an toàn, không mở admin blanket.
5. Theo dõi khi triển khai và audit policy version.
6. Reconciliation sau triển khai để phát hiện drift.

## 35. Sai lầm thường gặp với Device trust

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| **Coi enrolled là trusted vĩnh viễn** | Máy cũ/noncompliant vẫn được cấp quyền. | Fresh posture + lifecycle/credential evidence. |
| **Tin MDM compliant là không có malware** | Bỏ qua EDR và rủi ro runtime. | Kết hợp risk telemetry, policy và resource checks. |
| **Dùng IP/VPN làm identity của thiết bị** | NAT, spoofing và shared network gây nhận diện sai. | Credential/device binding đáng tin. |
| **Tin header `trusted=true` từ client** | Có thể giả posture. | Signed/verified evidence, server-side lookup. |
| **mTLS success ⇒ cho mọi quyền** | Device được xác thực nhưng user/workload không có entitlement. | RBAC/ABAC và resource-level authorization. |
| **Passkey/MFA success ⇒ device compliant** | User đúng danh tính nhưng endpoint không đạt. | Kiểm riêng device posture. |
| **OAuth device code flow ⇒ trusted device** | Nhầm luồng OAuth với security posture. | Enrollment, proof-of-possession và compliance evidence. |
| **Quên kiểm certificate revocation** | Máy mất/cert bị lộ vẫn kết nối. | PKI lifecycle + revocation enforcement audit. |
| **Dùng compliance cache quá cũ** | Quyết định dựa tín hiệu không còn đúng. | TTL, freshness và event-driven re-evaluation. |
| **Chỉ chặn new sign-in khi device LOST** | Existing app sessions có thể còn sống. | Session/token/PEP revocation theo khả năng. |
| **Coi remote wipe queued là dữ liệu đã xóa** | Máy offline còn dữ liệu. | Phân biệt queued và confirmed, server-side mitigation. |
| **Chỉ disable account Leaver** | Device cert, PAT, VPN hoặc local sessions còn tồn. | Multi-target offboarding và readback. |
| **Chuyển owner laptop chỉ bằng email** | Local profile, key và entitlement cũ còn. | Reassign/re-enroll và credential cleanup. |
| **Cho mọi workload trên host healthy cùng quyền** | Privilege escalation giữa các services. | Workload identity, scope và service-level authorization. |
| **Không xét BYOD privacy** | Thu thập dữ liệu quá mức và mất niềm tin. | Data minimization, transparency, app/VDI alternatives. |
| **Không có phương án khi MDM/IdP outage** | Tự mở bypass hoặc tê liệt ứng cứu. | Continuity policy, controlled emergency access, post-event review. |
| **Sự kiện MDM cũ ghi đè LOST/Leaver** | Trust bị bật lại trái thời điểm. | Source version, precedence, idempotency. |
| **Đóng incident từ một API 200** | Quyền đích/phiên chưa chắc thay đổi. | Target readback và scope-specific verification. |

## 36. Checklist triển khai Device trust

### 36.1. Danh tính, bằng chứng và kiến trúc

1. Đã xác định rõ **device identity, enrollment, management, compliance, trust và authorization** là các khái niệm khác nhau chưa?
2. Mỗi device có **ID đúng tenant/issuer, owner/asset hoặc workload mapping** đáng tin cậy không?
3. Có cơ chế **device credential proof-of-possession**, issuer/CA trust và lifecycle phù hợp khi policy yêu cầu không?
4. Bằng chứng **attestation**, nếu dùng, có kiểm nonce, trust anchor, key/device binding, measurements và freshness không?
5. Có quản lý certificate **issuance, expiry, rotation và revocation** không?
6. MDM/UEM có ghi rõ **enrollment state, compliance policy version, observedAt và check-in freshness** không?
7. EDR/OS posture có phân biệt **healthy, high-risk, offline, stale và unsupported** không?
8. Có tránh tin **IP, hostname, serial, header tự khai hoặc `compliant=true` do client gửi** không?

### 36.2. Quyết định và thực thi quyền

9. Conditional access có kết hợp **user/workload identity, role/entitlement, device risk, action, resource và session context** không?
10. Tài nguyên rủi ro khác nhau có **policy trust và biện pháp hạn chế khác nhau** không?
11. Có điểm thực thi ở **IdP/ZTNA/API/app**, tránh chỉ bảo vệ UI không?
12. Có kiểm authorization **RBAC/ABAC và SoD** độc lập với device trust không?
13. Có phân biệt passkey/MFA, device certificate, platform attestation và OAuth device authorization flow không?
14. Có ghi rõ cách xử lý **posture UNKNOWN/STALE, MDM outage, CA revocation check lỗi** không?
15. Có cơ chế **re-evaluate active sessions hoặc giới hạn thời hạn** khi posture thay đổi không?
16. Có đánh giá độ trễ **risk signal → PDP → PEP** và những đường session/token tồn dư không?

### 36.3. Joiner–Mover–Leaver và tài khoản máy

17. Joiner có kiểm **Start date, Person/Engagement, device assignment và baseline posture** trước khi mở quyền nghiệp vụ không?
18. Mover có cập nhật **entitlement cũ/mới, policy theo job, local admin và active sessions** không?
19. Leaver có thu hồi **IdP/SSO, VPN/ZTNA, device cert, PAM, PAT/API keys, app sessions và asset assignment** theo phạm vi không?
20. Thiết bị **offline/lost** có được chặn server-side thay vì đợi remote wipe không?
21. Rehire có dùng **Engagement mới** và không tự kích hoạt lại credential/role cũ không?
22. Bàn giao thiết bị có xử lý **local data, profiles, keys, re-enrollment và owner binding** không?
23. BYOD/Contractor/shared devices có mô hình **scope, privacy, trust issuer và alternative access** rõ không?
24. Server/IoT/OT/workload có **device/host trust riêng với workload/service identity**, không gộp máy và pod không?

### 36.4. Thu hồi, kiểm toán và chất lượng

25. Có phân biệt **revoke requested, provider acknowledged và effective-access revoked verified** không?
26. Khi cert bị revoke, có xác minh gateway/PEP thật sự từ chối trong **phạm vi và độ trễ** đã cam kết không?
27. Có xử lý **stale events, out-of-order JML, device re-enrollment và duplicate records** không?
28. Risk exception có **owner, severity, compensating control, expiry và review** không?
29. Audit có **deviceId, subjectId/workloadId, action, resource, evidence versions, policy và decision timestamp** không?
30. Có bảo vệ **credential, certificate private key, token, PII và metadata thiết bị nhạy cảm** trong report/log không?
31. Có kiểm thử **positive/negative, stale, lost, revoked, mTLS, attestation, JML, session và BYOD** không?
32. Khi test thất bại hoặc chưa thể kiểm, có ghi **FAIL/BLOCKED/INDETERMINATE**, không tính thành PASS không?
33. Các device credentials/test accounts có được **cleanup và readback** đúng không?
34. KPI có thể hiện **coverage, posture freshness, untrusted access, revocation latency, residual sessions, ownerless devices và exception aging** không?
35. Khi một số hệ thống không cung cấp posture/session readback, báo cáo có công bố **giới hạn quan sát** không?
36. Có phương án **emergency access và hậu kiểm** không dựa hoàn toàn vào hạ tầng đang bị sự cố nhưng vẫn kiểm soát rủi ro không?

## 37. Kết luận: tin cậy thiết bị phải có bằng chứng và có thời hạn

Device trust là một quá trình, không phải nhãn dán được cấp một lần cho một chiếc máy.

~~~text
THIẾT BỊ ĐƯỢC XÁC ĐỊNH ĐÚNG
    deviceId + asset/owner + cryptographic identity
                    ↓
BẰNG CHỨNG ĐỦ TIN CẬY
    MDM/UEM + EDR + PKI/attestation + freshness
                    ↓
ĐÁNH GIÁ THEO NGỮ CẢNH
    Person/Engagement hoặc Workload + Resource + Action + Risk
                    ↓
QUYẾT ĐỊNH VÀ THỰC THI
    Allow / Step-up / Restrict / Deny tại IdP/PEP
                    ↓
THEO DÕI THAY ĐỔI
    Posture drift + Device lifecycle + JML + Session/token
                    ↓
THU HỒI VÀ XÁC MINH
    Certificates + Sessions + App/Cloud/API + Evidence
~~~

**Ghi nhớ:** **Device trust không đồng nghĩa “thiết bị đã đăng ký” hoặc “chứng chỉ còn hạn”**. Nó đòi hỏi **xác thực danh tính thiết bị, bằng chứng posture/attestation có độ tươi phù hợp, liên kết đúng owner hoặc workload và quyết định truy cập theo tài nguyên**. Ngay cả máy compliant cũng không tự cấp quyền cho người đã Leaver hoặc workload không được authorization. Tổ chức cần phối hợp **IdP/SSO, UEM/MDM, PKI/mTLS, EDR, RBAC/ABAC, SCIM và PAM** trong vòng đời **Joiner–Mover–Leaver**, xử lý mất máy, rủi ro runtime và quyền phiên/token còn tồn dư. Chất lượng kiểm soát được chứng minh bằng **quyền thực tế được cho phép hoặc bị từ chối ở hệ thống đích**, có audit, owner và quy trình thu hồi kiểm chứng được.
