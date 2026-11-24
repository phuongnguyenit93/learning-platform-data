# Thiết bị mất kiểm soát: phát hiện, cô lập và khôi phục machine identity trong IAM

> **Chương: Machine identity.** **Thiết bị mất kiểm soát** là tình huống một thiết bị, máy chủ, máy ảo, node, endpoint, thiết bị IoT/OT hoặc thực thể máy khác **không còn nằm trong trạng thái quản trị và mức tin cậy mà tổ chức yêu cầu**, hoặc có bằng chứng cho thấy danh tính máy, khóa, chứng chỉ, phiên hay quyền truy cập của nó đã bị chiếm đoạt hoặc sử dụng trái phép. “Mất kiểm soát” có thể là **mất vật lý, bị xâm nhập, không còn nhận chính sách quản lý, chứng chỉ/khóa bị lộ, bị thay đổi chủ sở hữu, thiết bị giả mạo hoặc không thể xác minh trạng thái**. Trong quản lý vòng đời danh tính IAM, phản ứng đúng không chỉ là khóa một User: phải xác định **device identity**, chủ thể liên kết, đường xác thực, quyền hiệu lực, mức độ bằng chứng, phạm vi ảnh hưởng, cách cô lập và **khi nào có thể tin cậy trở lại**. Bài học liên hệ Joiner–Mover–Leaver, IdP/SSO, SCIM, RBAC/ABAC, PKI/mTLS, MDM/UEM, EDR, service identities và kiểm toán để giảm quyền truy cập tồn dư.

## Mục tiêu học tập

Sau khi hoàn thành bài, bạn có thể:

1. Giải thích **thiết bị mất kiểm soát** và phân biệt nó với **thiết bị offline**, **thiết bị không tuân thủ**, **thiết bị mất cắp**, **device identity bị compromise**, và **thiết bị không xác định nguồn gốc**.
2. Nhận diện các lớp danh tính: **human identity, device identity, machine/workload identity, service account, certificate, key, token và session**, tránh quy mọi sự cố về một username.
3. Thiết lập **device inventory và ownership** với stable identifiers, tenant, loại thiết bị, trust anchor, enrollment, trạng thái và các quan hệ với User/workload/resource.
4. Thiết kế tín hiệu phát hiện và quy trình **triage → contain → revoke → investigate → recover → verify**, có xử lý tình huống dữ liệu thiếu.
5. Giải thích vai trò của **MDM/UEM, EDR, IdP, CA/PKI, mTLS, RBAC/ABAC/PBAC, API/Resource Server, PAM và hệ thống quản lý secret** trong cô lập thiết bị.
6. Thu hồi đúng **certificate, key, refresh/access token, enrollment, account/role, phiên, trust và resource access** khi cần; không tuyên bố thành công chỉ vì một endpoint báo 200.
7. Quản trị **Joiner–Mover–Leaver**, đổi owner, máy dùng chung, IoT không online liên tục, service identity và trường hợp thiết bị cần bảo toàn chứng cứ.
8. Thiết kế policy, event model, pseudocode, ma trận kiểm thử, bài tập tình huống và chỉ số đo **residual device access**.

## 1. Tình huống mở đầu: laptop thất lạc nhưng tài khoản vẫn hoạt động

Nhân viên Lan dùng một laptop được quản lý để đăng nhập qua IdP và truy cập ứng dụng báo cáo. Laptop chứa khóa đăng ký thiết bị, có certificate dùng truy cập VPN hoặc Wi-Fi và có thể giữ phiên SSO, cookie ứng dụng, access/refresh token hoặc khóa SSH được bảo vệ theo từng nền tảng. Lan báo mất laptop khi di chuyển.

Một phản ứng đơn giản như “đổi mật khẩu của Lan” chưa chắc xử lý được:

- Khóa thiết bị/certificate có thể vẫn được tin cậy ở VPN, gateway hoặc API.
- Session và token đã phát trước thời điểm báo mất có thể còn hiệu lực.
- Thiết bị có thể đăng nhập lại với refresh token dù mật khẩu đã đổi, tùy cơ chế.
- Một service account hoặc credential cục bộ trên máy có thể không liên kết với User Lan.
- Thiết bị có thể vẫn xuất hiện là **compliant** trong cache của một dịch vụ dù đã bị đánh dấu mất ở MDM.
- Nếu máy chứa dữ liệu nhạy cảm offline, khóa account không tự xóa được dữ liệu đã lưu.

Ngược lại, **không phải cứ mất kết nối MDM là máy bị đánh cắp**: thiết bị có thể hết pin, mất mạng hoặc đang trong vùng không có kết nối. Cần phân biệt **độ tin cậy hiện tại** với **bằng chứng xâm nhập** để đưa ra phản ứng tương xứng.

### Mục tiêu thực sự

> Chặn hoặc hạn chế các đường truy cập của thiết bị không còn đáng tin, bảo vệ dữ liệu và nguồn chứng cứ, không làm gián đoạn sai các thiết bị hoặc workload còn hợp lệ, rồi chỉ khôi phục quyền khi danh tính và trạng thái thiết bị được kiểm chứng lại.

## 2. Những trạng thái “mất kiểm soát” cần phân biệt

| Trạng thái | Tín hiệu minh họa | Mức tin cậy | Phản ứng ban đầu |
| --- | --- | --- | --- |
| **LOST / STOLEN** | Chủ thiết bị xác nhận thất lạc hoặc bị lấy cắp. | Rủi ro vật lý, credential và dữ liệu tại chỗ. | Đánh dấu mất, hạn chế truy cập, bảo vệ dữ liệu, điều tra. |
| **SUSPECTED_COMPROMISED** | EDR phát hiện hành vi nguy hiểm, certificate dùng từ nguồn bất thường. | Có nghi vấn nhưng chưa đủ kết luận toàn hệ thống. | Containment theo mức rủi ro, thu thập chứng cứ. |
| **CONFIRMED_COMPROMISED** | Bằng chứng tin cậy cho thấy khóa/thiết bị hoặc phiên bị chiếm quyền. | Không chấp nhận cho truy cập như cũ. | Revoke/rotate theo phạm vi, cách ly và incident response. |
| **UNMANAGED / UNENROLLED** | Không còn dưới MDM/UEM hoặc không còn profile quản trị. | Không đáp ứng yêu cầu quản lý. | Chặn những tài nguyên yêu cầu managed device, xác minh lại. |
| **NONCOMPLIANT** | Không đạt policy: mã hóa, bản vá, endpoint protection hoặc posture. | Không đủ điều kiện với tài nguyên rủi ro. | Remediate hoặc hạn chế theo risk tier. |
| **OFFLINE / STALE_TELEMETRY** | Không gửi check-in trong khoảng thời gian quy định. | Trạng thái hiện hành không chắc chắn. | Áp freshness policy; không tự kết luận đã bị compromise. |
| **IDENTITY_CLONE_SUSPECTED** | Cùng credential/device ID được dùng trái mô hình từ nhiều nơi. | Nghi lộ khóa hoặc thiết bị giả mạo. | Tạm ngừng tin cậy, điều tra khóa/attestation và các đường truy cập. |
| **DECOMMISSIONED** | Thiết bị đã được retire/hủy theo quy trình. | Không còn được truy cập. | Thu hồi registration, certificate, trust, roles và credentials. |
| **OWNERSHIP_UNKNOWN** | Thiết bị còn hoạt động nhưng không xác định được owner/sponsor. | Thiếu trách nhiệm quản trị. | Cách ly hoặc hạn chế có kiểm soát, xác minh owner. |
| **QUARANTINED** | Đã áp chế độ cô lập/hạn chế. | Có thể còn hoạt động kỹ thuật nhưng không được truy cập như trước. | Cho phép các kênh remediation được thiết kế riêng. |

**Đây là taxonomy nội bộ minh họa**, không phải danh sách trạng thái chuẩn bắt buộc của MDM, PKI hay SCIM.

### Ba câu hỏi không đồng nghĩa

1. **Device còn hoạt động không?** Máy online hoặc ping được chỉ nói về kết nối.
2. **Device còn được quản lý và đáng tin không?** Cần enrollment, posture, khóa, chứng thực và các điều kiện tài nguyên.
3. **Device còn quyền truy cập thực tế không?** Phụ thuộc token/session, certificate, trust, direct grants, gateway và PEP.

Một device đang offline vẫn có credential hợp lệ; một device đang online nhưng mất quản lý vẫn có thể bị policy chặn; một device vừa bị thu hồi registration vẫn có thể giữ token cũ nếu Resource Server không áp revocation phù hợp.

## 3. Device identity khác human identity và workload identity

Một máy có thể liên quan **nhiều danh tính**:

| Danh tính/đối tượng | Đại diện cho | Ví dụ | Điểm quản lý |
| --- | --- | --- | --- |
| **Human identity** | Người chịu trách nhiệm hoặc sử dụng. | IAM:ID-LAN-2041 | HR/JML, IdP, MFA, approval. |
| **Device identity** | Một thiết bị/instance đã đăng ký và chứng thực. | device:tenant-b:dev-882 | MDM/UEM, registry, key/cert, posture. |
| **Workload identity** | Tiến trình, service, pod, VM workload gọi API. | workload:payments-worker | Service registry, cloud IAM, workload federation. |
| **Service account** | Account dùng bởi automation/daemon. | service:backup-agent | Owner, grants, credentials, vòng đời service. |
| **Credential** | Bằng chứng dùng để xác thực. | X.509 certificate, private key, signing key, token | PKI/CA, secret store, TPM/HSM, revocation. |
| **Device/user session** | Phiên đã xác thực trong một ứng dụng/gateway. | SSO session, VPN session, SSH session | IdP, VPN, app, PAM, Resource Server. |
| **Resource entitlement** | Quyền thực hiện hành động trên tài nguyên. | storage.read, deploy.update | RBAC/ABAC/PBAC, ACL, resource policy. |

### Một thiết bị không nhất thiết có một người sử dụng

- **Máy cá nhân được cấp cho một nhân viên:** owner/assignee có thể liên kết với HR identity.
- **Máy dùng chung/kiosk:** có thể có nhiều người đăng nhập trong các phiên khác nhau; không dùng device ID để suy ra ai đã thực hiện mọi hành động.
- **Thiết bị IoT/OT:** có site owner và operator, nhưng không nhất thiết có HR user thường xuyên.
- **Server/VM:** có application owner và workload owner; root account có thể là account cục bộ, không phải “người”.
- **Container/pod:** vòng đời ngắn; workload identity có thể đại diện service chứ không ổn định theo tên pod.
- **Thiết bị bên thứ ba/BYOD:** ownership, quyền remote wipe và dữ liệu cá nhân có giới hạn riêng.

Một người nghỉ việc không có nghĩa mọi workload của team phải bị xóa; ngược lại, **khóa human account không tự thu hồi machine credential** đã được phân phát cho một thiết bị.

## 4. Chuỗi tin cậy của machine identity

Trong một mô hình điển hình, thiết bị phải được **enroll** vào hệ thống quản lý, có cơ chế chứng minh khóa thuộc về nó, được đánh giá posture và chỉ sau đó mới được cho truy cập tài nguyên được bảo vệ.

~~~mermaid
flowchart LR
    D["Physical/virtual device"] --> K["Device key / TPM / secure storage"]
    K --> E["Enrollment / device registry"]
    E --> C["PKI certificate hoặc device assertion"]
    E --> M["MDM/UEM posture & compliance"]
    C --> P["Gateway / IdP / Resource PEP"]
    M --> P
    U["Human or workload identity"] --> P
    P --> R["Protected resource"]
    X["Incident & lifecycle policy"] -.-> P
    X -.-> E
    X -.-> C
~~~

Sơ đồ là mô hình khái niệm. **Không phải mọi nền tảng có cùng các thành phần hoặc kiểm tra posture đồng thời**. Một số dịch vụ chỉ kiểm certificate trong mTLS, trong khi một số dịch vụ dùng IdP device registration và conditional access.

### Các lớp phải phân biệt

1. **Hardware/boot integrity:** có tín hiệu từ secure boot, TPM, attestation hoặc nền tảng tương đương.
2. **Key possession:** bên kết nối chứng minh kiểm soát private key/token phù hợp.
3. **Enrollment/trust:** khóa hoặc certificate có được CA/registry và policy hiện hành chấp nhận?
4. **Management posture:** thiết bị đáp ứng yêu cầu cấu hình, mã hóa, EDR, patch, thời gian check-in?
5. **Human/workload identity:** ai đang dùng thiết bị và có quyền gì?
6. **Authorization/runtime:** resource có thực thi scope, tenant, session, device state và revocation?

**Có certificate hợp lệ không chứng minh máy đang sạch malware.** Ngược lại, một thiết bị có EDR “healthy” không thay thế kiểm tra subject, audience, permission hoặc resource scope.

### TPM, secure enclave và non-exportable key

Khóa được tạo/bảo vệ bởi phần cứng có thể **giảm khả năng xuất private key**, nhưng không bảo đảm thiết bị không bị chiếm quyền sử dụng khóa hoặc không thể ra lệnh ký khi hệ điều hành/ứng dụng đã bị compromise. Tương tự, attestation có giá trị khi **chuỗi chứng thực, nonce/freshness và phép đánh giá** được xác minh; nó không phải “giấy chứng nhận máy sạch” vĩnh viễn.

## 5. Inventory và ownership: điều kiện để cô lập đúng thiết bị

Không thể thu hồi đúng nếu tổ chức chỉ biết hostname. Hostname có thể đổi, được tái sử dụng, trùng giữa tenant hoặc bị giả mạo.

### Các trường inventory tối thiểu

| Trường | Mục đích |
| --- | --- |
| **deviceId, namespace, tenant** | Định danh ổn định trong hệ thống có thẩm quyền. |
| **assetId/serialRef** | Liên kết với tài sản vật lý khi có. Không dùng đơn lẻ làm chứng cứ identity. |
| **deviceType, environment, location/site** | Laptop, server, kiosk, IoT; production/staging/site. |
| **owner/sponsor và assignee** | Ai chịu trách nhiệm, ai đang sử dụng và ai phê duyệt. |
| **enrollmentId/provider** | Device registration ở MDM/IdP/UEM. |
| **certificate thumbprints / key IDs** | Những credential nào thuộc thiết bị, không lưu private key. |
| **workload/service bindings** | Service principals, apps và identities có thể chạy trên máy. |
| **role/entitlements/access paths** | VPN, Wi-Fi, cloud, API, SSH, SaaS, local admin. |
| **management/compliance state** | Managed, compliant, stale, quarantined và nguồn tín hiệu. |
| **lastSeenAt/lastAttestedAt** | Độ mới của tình trạng thiết bị. |
| **lifecycle state** | Enrolled, active, missing, compromised, decommissioned, recovered. |
| **credential validity/revocation state** | Phát hành, expiration, rotate/revoke và nguồn tin. |
| **incident/recovery references** | Bằng chứng xử lý và lịch sử re-enrollment. |

### Ví dụ bản ghi nội bộ

~~~json
{
  "deviceRef": "uem:tenant-b:dev-882",
  "assetRef": "ASSET-882",
  "deviceType": "LAPTOP",
  "tenant": "tenant-b",
  "assignedHumanIdentityId": "IAM:ID-LAN-2041",
  "serviceOwnerId": null,
  "enrollmentRef": "uem-enrollment-882",
  "certificateRefs": ["cert-thumbprint-1"],
  "managementState": "MANAGED",
  "trustState": "SUSPECTED_LOST",
  "lastSeenAt": "2026-12-01T08:55:00+07:00",
  "incidentId": "INC-DEVICE-2026-008"
}
~~~

Đây là schema minh họa, không phải chuẩn SCIM, CMDB, MDM hay PKI. Không đưa **private key, raw access token, cookie hoặc mật khẩu** vào inventory.

### Quan hệ một-nhiều phải được giữ rõ

~~~text
Human Lan
    -> managed laptop dev-882
    -> smartphone dev-311
    -> cloud admin account admin-lan

Laptop dev-882
    -> device certificate cert-1
    -> VPN session vpn-882
    -> cached SaaS session session-45
    -> SSH key/key reference key-22

Workload payments-worker
    -> runs on VM node-14
    -> workload federation trust trust-8
    -> API permission payments.read
~~~

Khi laptop dev-882 bị mất, phải **xử lý các credential/session gắn với chính device**. Không mặc định vô hiệu smartphone dev-311 hoặc production workload nếu không có bằng chứng phạm vi ảnh hưởng rộng hơn; cũng không bỏ sót credentials độc lập chạy trên dev-882.

## 6. Phát hiện mất kiểm soát: tín hiệu, nguồn và mức tin cậy

### Nguồn tín hiệu

| Nguồn | Tín hiệu hữu ích | Giới hạn |
| --- | --- | --- |
| **Người dùng/asset owner** | Báo mất, bị cướp, bị tháo quản lý, thay người sử dụng. | Cần xác minh người báo và định danh asset. |
| **MDM/UEM** | Enrollment, policy compliance, check-in, trạng thái khóa/xóa. | Agent offline không nhận lệnh ngay; dữ liệu có độ trễ. |
| **EDR/XDR** | Hành vi thực thi bất thường, dấu hiệu compromise. | False positive/negative, sensor có thể bị vô hiệu hoặc offline. |
| **IdP/Conditional Access** | Device registration, posture claim, sign-in risk, session activity. | Cache/token và tình trạng thiết bị có thể không đồng thời. |
| **PKI/CA** | Chứng chỉ phát hành, trạng thái revoke/expire, issuance anomalies. | Revocation check phụ thuộc relying party và reachability. |
| **VPN/Network/NAC** | Kết nối từ device certificate/host/network khác thường. | Địa chỉ IP không phải định danh máy duy nhất. |
| **Cloud/Workload IAM** | Role assumption, service token issuance, trust anomalies. | Principal có thể là service chứ không đại diện host cụ thể. |
| **SIEM/Audit** | Correlation giữa certificate, User, resource, action và incident. | Log có thể chậm, không bao phủ mọi đường truy cập. |
| **Inventory/CMDB** | Owner, asset disposal, site, vòng đời phần cứng. | Metadata thủ công có thể cũ. |

### “Stale telemetry” không luôn là compromise

Ví dụ chính sách yêu cầu device check-in trong 24 giờ cho quyền truy cập dữ liệu nhạy cảm. Sau 26 giờ không có check-in, ta có thể **chưa đủ evidence device compliant hiện hành**, vì vậy chặn hoặc yêu cầu revalidation tại tài nguyên rủi ro. Tuy nhiên không nên tự kết luận “đã bị malware” chỉ từ con số đó.

Ngưỡng freshness cần điều chỉnh theo thiết bị và môi trường: laptop công sở, kiosk, OT sensor thỉnh thoảng kết nối hoặc cluster không có Internet có những đặc điểm khác nhau.

### Phân biệt Detection, Classification, Enforcement

- **Detection:** nhận tín hiệu “device certificate có dấu hiệu bị dùng ngoài thiết bị dự kiến”.
- **Classification:** nghi lộ key, xác nhận lộ, hay chỉ thiết bị thay mạng?
- **Enforcement:** gateway chặn certificate/token, IAM revoke trust, EDR isolate endpoint, hoặc yêu cầu step-up.

Một cảnh báo không tự thu hồi quyền; một trạng thái MDM không tự được mọi Resource Server thực thi.

## 7. Phân loại mức ảnh hưởng trước khi xử lý

Một máy chủ chứa CI credential production có thể ảnh hưởng nhiều tài nguyên hơn laptop đọc tài liệu. Tuy nhiên laptop bị mất có dữ liệu nhạy cảm chưa mã hóa cũng có rủi ro cao. Nên xét:

1. **Mức tin cậy của bằng chứng:** nghi ngờ, có chỉ báo mạnh, hay đã xác nhận compromise.
2. **Quyền hiệu lực:** account/role, private key, token, privileged session và đường tự tăng quyền.
3. **Dữ liệu tại chỗ:** offline cache, mã hóa ổ đĩa, secret/backup, dữ liệu khách hàng.
4. **Phạm vi tài nguyên:** tenant/project, app, cluster, mạng nội bộ, production.
5. **Khả năng cô lập:** EDR/MDM online, gateway và CA có nhận revocation hay không.
6. **Mức độ chia sẻ:** device dùng bởi một người, nhiều người hoặc nhiều workload.
7. **Tính quan trọng availability:** máy phục vụ điều khiển thiết bị công nghiệp, hệ thống thanh toán hoặc recovery.
8. **Khả năng lan rộng:** credential được dùng lại, trust cross-tenant, quyền sửa IAM policy, signer.
9. **Yêu cầu pháp lý/nghiệp vụ:** bảo toàn chứng cứ, dữ liệu cá nhân, thời hạn thông báo khi áp dụng.

### Ma trận quyết định sơ bộ

| Bằng chứng | Quyền/độ nhạy | Hướng phản ứng |
| --- | --- | --- |
| Stale heartbeat, chỉ dữ liệu ít rủi ro | Không có dấu hiệu compromise khác | Hạn chế theo freshness, điều tra và recheck; không xóa mù. |
| Laptop mất cắp, có session/credential ứng dụng | Có khả năng dữ liệu/phiên bị lộ | Chặn device access, xử lý token/session, cân nhắc lock/wipe theo policy và khả năng online. |
| Lộ private key dùng mTLS production | Có quyền API hoặc deploy | Thu hồi key/cert/trust, rotate, ngăn phiên mới và kiểm tra các phiên còn sống. |
| Server CI bị chiếm quyền, có quyền production | Tác động tới pipeline và secrets | Contain host, revoke credentials bị ảnh hưởng, kiểm tra trust/supply chain và bảo toàn chứng cứ. |
| Sensor OT mất kết nối, nằm trong mạng điều khiển | Tác động availability/safety | Phối hợp owner OT/safety, containment được phê duyệt; tránh wipe/restart tự phát. |

Đây là định hướng nghiệp vụ chứ không phải công thức auto-action cho mọi tình huống. Với hệ thống safety-critical, cô lập thiếu kế hoạch có thể làm phát sinh rủi ro vật lý.

## 8. Triage: xác định đúng thiết bị và đường truy cập

Một sự kiện mất kiểm soát cần gắn **deviceRef ổn định** với những credential và tài nguyên liên quan.

### Checklist triage

1. Xác thực người báo mất hoặc nguồn alert bằng kênh đáng tin.
2. Xác nhận assetId, deviceId, enrollmentId, tenant, owner, loại thiết bị và environment.
3. Ghi **eventAt, detectedAt, lastSeenAt**; không gộp mọi thời điểm thành một.
4. Đánh giá loại mất kiểm soát: LOST, STOLEN, COMPROMISED, NONCOMPLIANT, UNMANAGED, OFFLINE/UNKNOWN.
5. Liệt kê certificate/key IDs, refresh tokens, active sessions, device-bound tokens, local accounts, SSH keys, workload credentials có thể bị ảnh hưởng.
6. Tìm những User/workload dùng chung thiết bị và tài nguyên đang được truy cập.
7. Xác định mức dữ liệu tại chỗ, encryption/backup, khả năng remote lock/wipe.
8. Chọn containment thích hợp và người có authority; lưu incident correlationId.
9. Xác định cần **forensic preservation** hay khôi phục nhanh.
10. Phân rõ việc **cần làm ngay** và điều chưa thể làm vì máy offline; ghi trạng thái pending.

### Incident record minh họa

~~~json
{
  "incidentId": "INC-DEVICE-2026-008",
  "deviceRef": "uem:tenant-b:dev-882",
  "assignedIdentityId": "IAM:ID-LAN-2041",
  "classification": "LOST_REPORTED",
  "reportSource": "VERIFIED_ASSET_OWNER",
  "eventAt": "2026-12-01T09:15:00+07:00",
  "detectedAt": "2026-12-01T09:21:00+07:00",
  "lastSeenAt": "2026-12-01T08:55:00+07:00",
  "riskTier": "HIGH",
  "requiredActions": [
    "BLOCK_DEVICE_TRUST",
    "REVOKE_RELEVANT_SESSIONS",
    "EVALUATE_CERTIFICATE_REVOCATION"
  ],
  "status": "TRIAGE"
}
~~~

Không lưu thông tin bí mật hoặc các dữ liệu nhạy cảm không cần thiết trong event này. Incident ID chỉ là khóa liên kết, không phải bằng chứng duy nhất thiết bị đã mất.

## 9. Chu trình xử lý: Identify → Contain → Revoke → Recover → Verify

~~~mermaid
flowchart TD
    A["Alert / Owner report / Device signal"] --> B["Verify device identity, owner,<br/>incident and affected access paths"]
    B --> C["Classify risk / source confidence"]
    C --> D{"Có nghi vấn đáng kể<br/>hoặc mất quản lý?"}
    D -->|Chưa đủ| E["Restrict by freshness policy,<br/>investigate and recheck"]
    D -->|Có| F["Contain: quarantine, block new trust,<br/>restrict network/device access"]
    F --> G["Revoke/rotate affected certificate,<br/>keys, tokens, sessions, grants"]
    G --> H["Forensics + recovery decision<br/>wipe/reimage/re-enroll or retire"]
    H --> I["New trust proof / attestation<br/>resource policy + least privilege"]
    I --> J["Readback target and test effective access"]
    J --> K{"Old identity and paths<br/>no longer authorized?"}
    K -->|Có| L["VERIFIED + audit + owner signoff"]
    K -->|Không| M["PARTIAL_FAILURE<br/>containment, retry, escalation"]
    M --> G
~~~

Thứ tự các bước có thể chồng lấn: khi thấy credential production đã lộ, **thu hồi khẩn cấp** có thể bắt đầu song song với việc lấy chứng cứ. Không ép phải hoàn tất phân tích forensics rồi mới chặn token đang bị khai thác.

### Kết quả cần đạt ở từng lớp

| Lớp | Ví dụ hành động | Cần xác minh |
| --- | --- | --- |
| **Device registry / MDM** | Mark lost/quarantined, disable registration, lock/wipe khi phù hợp. | Registry state, command status, device ack nếu có. |
| **PKI / mTLS** | Revoke certificate, rotate affected keys, remove trust. | Revocation publication và kiểm tra của relying parties. |
| **IdP/SSO** | Disable affected device trust; revoke device-linked sessions/tokens nếu hỗ trợ. | New sign-in bị chặn; session behavior trong boundary. |
| **VPN/NAC/network** | Block device cert/identity, restrict route hoặc isolate endpoint. | Kết nối cũ/mới, policy hiệu lực ở gateway. |
| **Apps/APIs** | Revoke local sessions, PAT/API keys, direct grants theo scope. | Không còn effective access qua đường cũ. |
| **Cloud/Workload IAM** | Revoke role/credential/trust gắn workload hoặc host bị ảnh hưởng. | Token/session và role assumption còn hợp lệ hay không. |
| **PAM** | Close privileged sessions, vault checkout, rotate secret đã lộ. | Target sessions thật sự đóng khi policy yêu cầu. |
| **Inventory/Audit** | Cập nhật incident, owner, device/cert lineage, outcome. | Bằng chứng readback đầy đủ, không đánh dấu hoàn tất giả. |

## 10. Containment: chặn đường truy cập ngay cả khi thiết bị offline

**Containment** là tập biện pháp giảm khả năng thiết bị hoặc credential bị lạm dụng trước khi xử lý nguyên nhân gốc.

### Nguyên tắc ưu tiên

- Đối với device đã mất hoặc nghi bị compromise ở mức cao, **hạn chế/chặn truy cập mới** tại các điểm kiểm soát có thể thực thi từ xa.
- Nếu máy online, có thể dùng EDR isolation hoặc MDM lock theo tính năng và policy. Không mặc định một lệnh đã gửi là đã được thực hiện.
- Nếu máy offline, **không chờ remote wipe** mới chặn các phiên/chứng chỉ/token tại IdP, gateway, PKI hoặc ứng dụng.
- Với một thiết bị dùng chung, phân biệt credential **gắn device**, **gắn User** và **gắn workload** để không vô hiệu hóa nhầm toàn bộ dịch vụ.
- Khi một host chứa secret/tokens có phạm vi cao, phải giả định các bí mật có thể đã bị phơi lộ theo threat model và **đánh giá rotate/revoke riêng**, không chỉ đánh dấu host quarantined.
- Đảm bảo hệ thống security/forensics có **đường quản lý hạn chế** nếu cần thu thập chứng cứ; quarantine không nhất thiết là rút dây mạng của mọi trường hợp.

### Remote lock khác remote wipe

| Hành động | Mục tiêu | Giới hạn |
| --- | --- | --- |
| **Remote lock** | Khóa phiên/giao diện thiết bị theo khả năng MDM. | Không tự thu hồi token hoặc copy dữ liệu đã bị lấy. |
| **Selective wipe** | Xóa dữ liệu/cấu hình công ty được quản lý trên BYOD. | Cần xác định dữ liệu được phép xóa và bảo vệ quyền riêng tư. |
| **Full wipe** | Xóa toàn bộ thiết bị theo quyền sở hữu và quy trình. | Có thể phá chứng cứ, dữ liệu cá nhân, gây outage; lệnh có thể pending khi offline. |
| **EDR isolation** | Hạn chế network của endpoint. | Một số luồng vẫn được cho phép; không thu hồi keys đã bị copy. |
| **Network deny/NAC quarantine** | Hạn chế truy cập tới mạng/dịch vụ. | Các phiên đã mở hoặc kết nối ngoài mạng này cần xử lý riêng. |
| **Certificate revocation** | Dừng relying party tin certificate bị ảnh hưởng. | Chỉ hiệu lực khi relying party kiểm tra trạng thái và chính sách hỗ trợ. |

**Đặc biệt:** Nếu cần điều tra số hóa, hãy cân nhắc **bảo toàn chứng cứ trước khi thực hiện thao tác phá hủy** khi thời gian và rủi ro cho phép, theo quy trình IR và thẩm quyền pháp lý. Không tự wipe mọi thiết bị bị nghi compromise.

## 11. Certificate, key và mTLS khi thiết bị mất kiểm soát

Machine identities thường dùng **X.509 certificates, private keys, SSH certificates/keys, workload tokens hoặc mTLS**. Cần xem **credential nào thực sự bị ảnh hưởng**, không thu hồi ngẫu nhiên cả CA nếu chỉ một endpoint bị mất.

### PKI: các thành phần liên quan

| Thành phần | Vai trò | Điều phải kiểm tra |
| --- | --- | --- |
| **Certificate Authority (CA)** | Ký certificate theo chính sách phát hành. | Có đúng CA/trust chain, issuance controls, revocation support? |
| **Certificate** | Liên kết public key với danh tính/thông tin và validity. | Serial, issuer, subject/SAN, EKU, notBefore/notAfter, status. |
| **Private key** | Chứng minh quyền sở hữu khóa trong phiên TLS hoặc ký. | Có bảo vệ phần cứng, copy được không, nghi lộ hay không? |
| **Relying party** | Gateway, app hoặc service xác minh certificate. | Có kiểm chain, purpose, name, expiry, revocation và mapping identity? |
| **CRL / OCSP** | Cơ chế cung cấp trạng thái thu hồi theo cách triển khai. | Endpoint có kiểm không, freshness/cache và hành vi khi unreachable? |
| **Device enrollment** | Gắn cert/khóa với device được quản trị. | Re-enroll có thể tạo lại trust bị thu hồi không? |

### Thu hồi chứng chỉ cần hai phía

1. **Phía cấp/registry:** đánh dấu revoke certificate đúng serial/issuer, phát hành thông tin thu hồi phù hợp.
2. **Phía chấp nhận (relying party):** thực thi policy kiểm certificate/status để từ chối certificate bị thu hồi khi kết nối.

Nếu gateway không kiểm revocation, cache lâu hoặc cố ý **fail-open** khi OCSP/CRL không có, CA báo “revoked” chưa chắc ngăn được truy cập ngay. Phải thử **negative handshake** trong phạm vi an toàn và ghi giới hạn thực tế.

### Ví dụ luồng mTLS

~~~mermaid
sequenceDiagram
    participant D as Device / Client
    participant GW as mTLS Gateway
    participant CA as CA/Revocation Service
    participant IAM as Device Registry / IAM
    participant API as Protected API
    D->>GW: TLS handshake + client certificate
    GW->>GW: Check chain, EKU, identity binding, time
    GW->>CA: Check current revocation status per policy
    CA-->>GW: Valid / revoked / unavailable
    GW->>IAM: Device trust and lifecycle posture
    IAM-->>GW: Allowed / blocked / unknown
    alt Certificate and device eligible
        GW->>API: Forward authenticated identity + scoped context
        API->>API: Authorize action and resource
    else Revoked, blocked or required data unknown
        GW-->>D: Reject according to policy
    end
~~~

**mTLS chứng minh bên kết nối kiểm soát private key**, không bảo đảm người điều khiển device là chủ thể được phép, thiết bị không có malware, hoặc API action được tự động Permit. Authorization vẫn cần kiểm scope, tenant, principal và resource.

### Khi private key bị nghi lộ

- Không chỉ revoke certificate nhưng **giữ nguyên private key** rồi cấp cert mới cho khóa đó.
- Tạo key pair mới trong môi trường đáng tin, phát certificate mới sau khi re-enrollment/attestation đạt policy.
- Đánh giá service/key reuse: có cùng private key trên nhiều thiết bị hoặc ứng dụng không?
- Xử lý những credential/tokens được phát dựa trên certificate cũ và các session TLS đang mở.
- Đối với CA hoặc signing key compromise, phạm vi có thể lớn hơn một device; incident cần đánh giá trust chain và nhiều relying parties.

Không đồng nhất **certificate expiry** với một tín hiệu runtime revoke ngay lập tức; connection/session đã được thiết lập có thể vẫn hoạt động tùy ứng dụng.

## 12. Access token, refresh token và session còn tồn tại

Một device có thể mất kiểm soát **sau khi** đã nhận access token, refresh token, cookie hoặc phiên quản trị. Thu hồi enrollment không bảo đảm toàn bộ những vật chứng xác thực ấy mất hiệu lực tức thì.

### Phân biệt những đường truy cập

| Đường truy cập | Thường được kiểm ở đâu? | Rủi ro sau mất device |
| --- | --- | --- |
| **SSO session/cookie** | IdP và application session store. | Có thể tái đăng nhập hoặc gọi API khi còn session. |
| **OAuth/OIDC access token** | Resource Server xác minh signature, audience, scope, expiry và policy. | Token tự chứa có thể còn hạn nếu không tra trạng thái hiện hành. |
| **OAuth refresh token** | Authorization Server hoặc token endpoint. | Có thể lấy access token mới khi còn hợp lệ, tùy token binding/rotation. |
| **Device-bound token/credential** | Dịch vụ xác minh ràng buộc thiết bị/khóa. | Rủi ro phụ thuộc việc bảo vệ khóa và kiểm binding thực tế. |
| **API key/PAT** | Ứng dụng hoặc API gateway. | Có thể độc lập với account SSO và MDM. |
| **SSH key/certificate** | SSH server/bastion/PAM. | Host key hoặc principal vẫn được chấp nhận nếu không revoke. |
| **VPN/TLS session** | VPN gateway hoặc mTLS endpoint. | Phiên đã thiết lập có thể tiếp tục dù cert vừa revoke. |
| **Local admin session** | OS, PAM, terminal, RDP/SSH. | Quản trị host không phụ thuộc session IdP còn có thể dùng. |
| **Workload access token** | Cloud IAM/Service API. | Một workload chạy trên host có thể giữ token ngoài phạm vi User. |

### Ví dụ quyền tồn dư

~~~text
09:00    API phát JWT có scope storage.read, exp=10:00
09:15    Laptop bị mất
09:20    Device registry đánh dấu LOST
09:22    IdP chặn lần sign-in mới từ device
09:23    User refresh token bị revoke theo khả năng
09:24    API vẫn kiểm JWT offline chỉ bằng chữ ký/exp

Rủi ro:
    JWT đã phát có thể còn được chấp nhận tới exp,
    nếu không có revocation hoặc kiểm policy hiện hành.
~~~

Một đáp ứng có thể kết hợp **short-lived access token, introspection/revocation checks, session termination, Continuous Access Evaluation nếu được triển khai tương thích, device binding và API-level authorization**. Không khẳng định có một cơ chế áp được cho mọi nền tảng hoặc rằng mọi API sẽ ngắt token ngay.

### Token binding không đồng nghĩa device không bị chiếm

Ràng buộc token với khóa thiết bị có thể giảm nguy cơ **sao chép bearer token sang máy khác**, nhưng nếu chính thiết bị đã bị kẻ tấn công điều khiển, phần mềm độc hại có thể vẫn sử dụng token hoặc yêu cầu ký thay trong phạm vi khóa cho phép. Do đó vẫn cần **posture, hành vi, hạn quyền và incident controls**.

## 13. IdP, SSO và conditional access khi device bị mất kiểm soát

Một kiến trúc hiện đại có thể dùng IdP để xác thực User và **conditional access/device trust** để kiểm soát việc đăng nhập hoặc tiếp tục phiên.

### Luồng logic

~~~text
User authentication:
    subject = IAM:ID-LAN-2041

Device context:
    deviceRef = uem:tenant-b:dev-882
    managementState = QUARANTINED
    trustStatus = REVOKED
    observedAt = time with source authority

Resource request:
    action = finance-report.read
    tenant = tenant-b

Decision:
    User hợp lệ + token có scope
    vẫn KHÔNG ĐỦ nếu resource yêu cầu managed trusted device
    và device trust bị revoke.
~~~

Điều kiện này chỉ đáng tin khi **device context do thành phần được ủy quyền xác nhận**, không phải tham số tùy ý được browser/client gửi tới API.

### Kiểm soát theo lớp

1. **Block new sign-in/enrollment:** thu hồi device registration hoặc đặt device state không đủ điều kiện.
2. **Revoke affected sessions:** ở IdP và ứng dụng hỗ trợ.
3. **Require trusted device context:** gateway/API áp policy cho tài nguyên nhạy cảm, không chỉ UI login.
4. **Reauthentication/step-up:** yêu cầu xác minh lại trên thiết bị còn tin cậy, nếu policy và tính năng cho phép.
5. **Check device freshness:** bảo đảm posture và trust không bị dùng quá thời gian hiệu lực.
6. **Account recovery:** không cho kẻ giữ device tự đặt lại MFA hoặc enrollment trên account hợp lệ.

### Chặn device khác với khóa cả nhân viên

Lan có thể mất laptop nhưng còn một điện thoại đã đăng ký đáng tin hoặc được cấp thiết bị mới. Tổ chức có thể **khóa device dev-882 và các phiên của nó**, đồng thời cho Lan tiếp tục truy cập từ thiết bị khác sau proofing và policy. Nếu có nghi vấn lộ account credentials, có thể phải **mở rộng containment tới User/session**. Quyết định phụ thuộc **phạm vi chứng cứ**, không phải quy tắc tất cả hoặc không.

### Rủi ro với thiết bị đăng ký lại

Nếu attacker còn quyền đăng nhập User, việc gỡ một device trong IdP nhưng cho phép User tự đăng ký device mới qua recovery yếu có thể mở lại đường truy cập. Cần bảo vệ **enrollment/reauthentication/recovery**, nhất là với quyền đặc quyền.

## 14. MDM/UEM, EDR, NAC và PKI phối hợp thế nào?

| Thành phần | Quản lý chính | Những điều không tự chứng minh |
| --- | --- | --- |
| **MDM/UEM** | Enrollment, cấu hình, compliance, lock/wipe theo tính năng. | API token ở SaaS đã bị revoke, máy offline nhận lệnh wipe. |
| **EDR** | Endpoint telemetry, detection, containment theo agent. | Mọi key/token đã bị lộ được rotate, device identity không thể dùng ở dịch vụ khác. |
| **NAC/VPN** | Network admission, network quarantine, certificate-based access. | Cloud API gọi trực tiếp từ Internet cũng đã bị chặn. |
| **PKI/CA** | Certificate issuance, status, revocation, key lifecycle. | Relying party chắc chắn kiểm revocation hoặc session đang mở đã bị ngắt. |
| **IdP/SSO** | User login, device registration, conditional access, session. | Local admin, PAT hoặc workload credentials không dùng IdP đều bị thu hồi. |
| **IAM/IGA** | Identity correlation, ownership, desired access, JML, review. | Thay đổi target đã hội tụ và không còn quyền runtime. |
| **PAM/PIM** | Đặc quyền, JIT, vault, session/custody theo tính năng. | Tất cả phiên direct SSH/cloud token đã mất hiệu lực. |
| **Resource Server/PEP** | Quyết định thực thi trên action/resource. | Nguồn trust, device state và policy luôn mới nếu PIP/caching lỗi. |

### Không có “một nút revoke tất cả”

Khi một thiết bị mất kiểm soát, phản ứng thường là **fan-out** tới nhiều control plane: MDM, IdP, VPN, CA, SaaS, cloud IAM, secret store và PAM. Mỗi bên có kiểu dữ liệu/độ trễ/trạng thái riêng. Một hệ thống trung tâm cần theo dõi **từng thao tác và readback**, không kết luận “đã cô lập hoàn toàn” vì một API trả HTTP 200/204.

### Dữ liệu từ các nguồn có thể mâu thuẫn

Ví dụ:

~~~text
UEM:       device dev-882 = QUARANTINED
IdP:       device dev-882 = COMPLIANT (cache 2 hours old)
VPN:       certificate cert-1 = still accepted
CA:        cert-1 = REVOKED, status published 15 minutes ago
App:       existing session = ACTIVE

Conclusion:
    NOT VERIFIED_CLOSED.
    Apply authoritative and freshness policy to each field,
    investigate enforcement gaps and residual sessions.
~~~

Không lấy “trạng thái mới nhất theo thời điểm nhận được” làm sự thật tuyệt đối nếu các hệ thống dùng **nguồn và semantics khác nhau**. Cần field ownership, event version, observedAt và policy cho dữ liệu thiếu.

## 15. RBAC, ABAC/PBAC và Zero Trust cho thiết bị mất kiểm soát

**RBAC** giới hạn quyền của User/service theo vai trò. **ABAC/PBAC** có thể đưa **device trust, posture, environment, resource sensitivity, thời điểm và dấu hiệu incident** vào quyết định. Tư duy **Zero Trust** nhấn mạnh không cho phép chỉ vì thiết bị đang “ở trong mạng nội bộ”.

### Pseudo-policy

~~~text
PERMIT finance.report.read KHI
    subject.lifecycleStatus == ACTIVE
    AND subject.hasEntitlement("FinanceReportReader")
    AND subject.tenantId == report.tenantId
    AND session.authenticationAssurance meets report.requiredAssurance
    AND device.deviceRef is verified
    AND device.trustStatus == TRUSTED
    AND device.managementState == MANAGED
    AND device.postureFreshAt(now, policy.maxPostureAge)
    AND device.incidentState NOT IN {LOST, COMPROMISED, QUARANTINED}
    AND resourcePolicy.allMandatoryGuardsPass

ELSE: NO_PERMIT
~~~

Đây là **mã giả** không thuộc ngữ pháp chuẩn của một policy engine. Nếu thiết bị là workload server không có MDM người dùng, policy phải dùng **nguồn attestation/trust phù hợp loại workload** chứ không máy móc yêu cầu trường UEM của laptop.

### Hard deny, default deny và remediation scope

~~~text
DENY privileged.* nếu device.trustStatus == COMPROMISED
DENY sensitive.export nếu device.trustStatus == LOST
DENY production.deploy nếu workload.attestationState không đạt
DENY newDeviceEnrollment nếu identity.lifecycleStatus == TERMINATED
DENY resource.* nếu tenant mismatch không có trust được phê duyệt
~~~

Một device bị quarantined có thể vẫn cần truy cập **endpoint cập nhật agent, chứng thực lại hoặc helpdesk portal** qua một policy hạn chế. Đừng áp một Deny toàn mạng khiến device không có cách remediating dù đó là mục tiêu quản trị.

### Trạng thái Unknown

Khi không đọc được trạng thái device:

- Với tài nguyên rủi ro cao, policy có thể **từ chối hoặc yêu cầu revalidation** thay vì tiếp tục dùng một trust claim cũ.
- Với tác vụ remediation được phép, có thể cho phép đường hạn chế trong environment cách ly.
- Không tự giả định **UNKNOWN = TRUSTED**, cũng không luôn khẳng định **UNKNOWN = COMPROMISED**.
- Ghi cụ thể nguồn không khả dụng và control bù nếu cần.

## 16. Joiner: đăng ký thiết bị mới an toàn

Trong **Joiner**, tổ chức có thể chuẩn bị account, laptop và authenticator trước ngày làm việc. Đây là lúc identity có thể bị gắn nhầm device hoặc cấp quyền sử dụng sớm.

### Quy trình Joiner

1. Xác minh HR identity bằng stable ID, xác định contract/startAt và owner thiết bị.
2. Gán asset/device tới đúng nhân viên, tenant, vị trí và nhóm quản lý theo chính sách.
3. Enrollment qua kênh tin cậy, tạo **device key riêng** và certificate/registration theo yêu cầu.
4. Gắn IdP User với device ID qua cơ chế có xác minh, tránh chỉ ghép theo email.
5. Bật baseline quản lý: encryption, endpoint protection, updates, screen lock, compliance.
6. Giới hạn truy cập **trước startAt**; pre-enrollment không mặc nhiên đồng nghĩa được sử dụng dữ liệu nghiệp vụ.
7. Cấp role/entitlement theo công việc, least privilege, SoD và resource policy.
8. Kiểm thử positive/negative: thiết bị hợp lệ truy cập đúng scope, thiết bị chưa enroll bị chặn theo policy.
9. Ghi owner, device lineage, certificate IDs, activationAt và review schedule.

### Joiner bị hủy sau pre-enrollment

~~~text
v20 HR: Joiner scheduled, startAt 2026-12-01
v21 UEM: Device dev-882 enrolled
v22 HR: Onboarding cancelled
v23 Queue: old app assignment retry

Required:
    dev-882 must not receive production access due to v23.
    enrollment/device trust and sessions are reviewed or revoked.
~~~

Trước mọi job cấp quyền, phải revalidate lifecycle/approval với sourceVersion/effectiveAt đáng tin. Nếu device đã giao vật lý cho ứng viên, cần quy trình thu hồi tài sản và bảo vệ dữ liệu riêng.

## 17. Mover: thay người dùng, chủ sở hữu và phạm vi thiết bị

Một **Mover** có thể đổi team/project/location/tenant, thay thiết bị hoặc chuyển owner của server/workload. Rủi ro gồm cả **quyền cũ còn hiệu lực** và **gắn nhầm device sang người mới**.

### Các kiểu Mover

| Loại | Ví dụ | Việc phải cập nhật |
| --- | --- | --- |
| **User chuyển team** | Lan từ Finance sang Support. | Gỡ role Finance, cập nhật chính sách thiết bị theo resource/tenant. |
| **Laptop bàn giao người khác** | dev-882 từ Lan sang Minh. | Reimage/reset phù hợp, thu hồi session/user tokens cũ, enrollment/assignment mới. |
| **Server đổi owner** | Node dev-prod-14 từ Platform A sang Platform B. | Service owner, access policy, cert trust và secrets liên quan. |
| **Workload đổi environment** | Build agent staging chuyển sang production. | Identity và credential riêng, không tự kế thừa staging trust. |
| **Chuyển tenant/pháp nhân** | Asset được chuyển sang tenant C. | Tách device registration, policy, certificate, keys và dữ liệu cũ. |
| **Device đổi trạng thái quản lý** | Unmanaged BYOD chuyển sang corporate-managed. | Proofing, enrollment, compliance, quyền truy cập theo policy mới. |

### Bàn giao máy không phải chỉ đổi tên Owner

Nếu một laptop từng chứa token/sessions/SSH keys của Lan được giao cho Minh, cập nhật CMDB assignee không làm những bí mật cũ tự biến mất. Cần quy trình **wipe/reimage hoặc secure reset có kiểm soát**, revoke các credential cá nhân cũ, re-enroll identity mới và xác minh không còn đường truy cập của người trước.

### Rủi ro thứ tự sự kiện

Nếu quyền production của người mới được bật khi máy vẫn chứa credential hoặc trust của người cũ, có thể tạo **cross-identity privilege accumulation**. Nên đảm bảo một ranh giới chuyển giao: **thu hồi/clean quyền cũ → xác minh trạng thái thiết bị → tạo trust mới → cấp quyền mới**.

### Mover của service owner

Khi người sở hữu server/pipeline đổi bộ phận, không xóa workload production chỉ vì owner rời team. Phải **bàn giao service ownership**, đánh giá credentials người cũ biết, giảm role/trust không cần thiết và cập nhật responders, audit.

## 18. Leaver: thu hồi account người và device trust là hai việc khác

**Leaver** khiến nhiều đường truy cập phải bị thu hồi nhanh, đặc biệt những thiết bị đã cấp cho nhân viên hoặc đăng ký dưới tài khoản cá nhân.

### Danh mục xử lý theo Leaver

1. **Human identity:** disable sign-in/SSO theo hiệu lực chính sách, revoke sessions và Group/role.
2. **Managed devices:** thu hồi tài sản, cập nhật device ownership/assignment và đánh dấu trạng thái tạm dừng phù hợp.
3. **Device enrollment/trust:** xem device có cần bị unenroll, quarantine, reassign hoặc retire.
4. **Credentials:** xử lý device certificate, SSH keys, passkeys/device-bound credentials theo quyền sở hữu và rủi ro; không xóa ngẫu nhiên credentials của workload khác.
5. **SaaS/local accounts:** gỡ direct grants, PAT, app sessions, local admin nếu còn liên kết người rời đi.
6. **Privileged paths:** PAM checkout, broker session, API key, cloud role và trust đã giao cho nhân viên.
7. **Shared credentials:** đánh giá rotation nếu người đã rời biết mật khẩu/bí mật vẫn dùng chung.
8. **Workload ownership:** chuyển owner của service machine identities; không tự dừng service sống.
9. **Evidence:** readback các đường truy cập bị yêu cầu thu hồi, ghi pending/partial failures.

### Phân biệt ba trường hợp

| Tình huống | Hành động chính |
| --- | --- |
| Nhân viên Leaver trả lại laptop công ty | Thu hồi User/session/credential; xử lý tài sản, reset/re-enroll hoặc retire. |
| Nhân viên Leaver không trả laptop | Xử lý như asset lost/unreturned; chặn device trust và đánh giá credential/data exposure. |
| Nhân viên Leaver là owner của server production | Thu hồi human admin grants; bàn giao service/workload owner, kiểm soát secrets, không xóa máy chủ mù. |

### Leaver và token đã phát

~~~text
17:00 HR Leaver effective
17:01 IdP blocks new sign-ins
17:02 UEM marks assigned laptop as retired
17:03 SaaS session from laptop still active
17:04 Resource API accepts old JWT

Conclusion:
    Employee and device access are not yet fully revoked
    within a boundary that requires immediate denial.
~~~

Trong thực tế phải xác định **thời hạn thu hồi chấp nhận được theo tài nguyên**; không tuyên bố “Leaver verified” khi còn những đường quan trọng chưa xử lý hoặc không thể kiểm chứng.

## 19. Tài khoản dịch vụ và workload identity chạy trên thiết bị mất kiểm soát

Một host bị compromise có thể chạy **nhiều service**, mỗi service có identity/secret khác nhau. Cần đánh giá theo **host-to-workload-to-credential-to-resource graph**.

~~~mermaid
flowchart TD
    H["Compromised VM node-14"] --> A["Payments API workload"]
    H --> B["Metrics collector"]
    H --> C["Deploy agent"]
    A --> K1["Workload token / audience payments"]
    B --> K2["Metrics API key"]
    C --> K3["CI/CD credential"]
    K1 --> R1["Payments resources"]
    K2 --> R2["Observability"]
    K3 --> R3["Production control plane"]
    IR["Incident response"] -.-> K1
    IR -.-> K2
    IR -.-> K3
~~~

### Các câu hỏi cần đặt

- Những workload nào chạy trên host tại thời điểm compromise?
- Identity nào được **federate** từ metadata service hoặc workload identity provider?
- Token/secret có thể bị lấy khỏi host và sử dụng ở nơi khác không?
- Các credential có **audience/scope/environment** phù hợp hay được dùng lại giữa staging/production?
- Đường CI/CD hoặc agent có thể deploy/code change, assume role hay đọc secrets khác không?
- Có quyền sửa trust policy, role bindings hoặc tạo long-lived credential không?
- Có cách thay host mà giữ continuity của dịch vụ nhưng phát identity/credential mới?

### Đừng tự coi host bị compromise là mọi service đều đã lộ toàn bộ

Mức độ ảnh hưởng phụ thuộc cách cô lập workload, khóa, metadata service, runtime, logs và thời điểm. Tuy nhiên, khi thiếu bằng chứng đầy đủ, cần **đánh giá theo threat model và phạm vi tối đa hợp lý**, ưu tiên thu hồi credential nhạy cảm có khả năng bị tiếp cận. Không bỏ qua khả năng lộ chỉ vì token chỉ có thời hạn ngắn.

### Quy trình khôi phục workload

1. Cô lập node/host bị nghi xâm nhập theo hướng dẫn ứng cứu.
2. Bảo vệ chứng cứ trước thao tác phá hủy khi khả thi.
3. Xác định affected service identities, keys, token issuers và active grants.
4. Revoke/rotate credentials nhạy cảm, cập nhật trust/policy.
5. Tạo workload mới trên image/host được kiểm chứng, có identity riêng và phạm vi tối thiểu.
6. Không copy credentials bị nghi lộ sang host mới.
7. Kiểm tra API hoạt động hợp lệ và negative access qua credentials cũ bị chặn.
8. Decommission node cũ và reconcile inventory/owner.

### Federation không xóa bỏ yêu cầu bảo vệ metadata

Workload identity federation giảm phụ thuộc secret lâu dài, nhưng nếu attacker điều khiển runtime được quyền phát token, họ có thể xin token mới khi trust còn hợp lệ. Cần **revoke workload trust, chặn nguồn phát từ host/instance bị nghi lộ, kiểm audience/subject/claims và kiểm phiên đã phát**.

## 20. Thiết bị IoT/OT, máy ngoại tuyến và thiết bị safety-critical

Thiết bị IoT/OT có thể không check-in hàng ngày, không cài EDR phổ thông và chịu ràng buộc về **safety/availability**. Một quy tắc áp cho laptop có thể không phù hợp với máy điều khiển sản xuất.

### Những điều khác biệt

| Khía cạnh | Laptop văn phòng | IoT/OT hoặc edge device |
| --- | --- | --- |
| Kết nối | Thường có Internet/MDM định kỳ. | Có thể offline dài ngày, mạng phân đoạn. |
| Quản lý | UEM/EDR/IdP phổ biến. | Device registry, gateway, firmware attest, OT platform. |
| Credential | User SSO, device cert, VPN, passkey. | Device certificate, pre-provisioned keys, PSK, gateway trust. |
| Revoke | IdP/gateway/MDM khi kết nối. | Có thể phải đợi gateway nhận CRL/policy hoặc vận hành tại chỗ. |
| Wipe/reimage | Tùy quyền sở hữu và dữ liệu. | Có thể gây ngừng chức năng vật lý, rủi ro safety. |
| Recovery | Cấp lại device/user enrollment. | Field service, secure provisioning, replacement và safety approval. |

### Một thiết bị offline không đồng nghĩa nên wipe từ xa

Nếu thiết bị điều khiển máy móc có nguy cơ mất kết nối, quyết định cô lập nên có **system owner, safety engineer và incident commander** theo chính sách. Có thể cần:

- Ngăn **kết nối điều khiển mới qua gateway** trước khi xử lý device.
- Giữ chế độ hoạt động an toàn của thiết bị theo thiết kế.
- Có đường xác minh certificate/key qua gateway hoặc kiểm soát tại hiện trường.
- Thay thiết bị/firmware và tạo identity mới sau khi được xác minh.
- Theo dõi các lệnh revoke chưa tới được device và các gateway chưa cập nhật.

Không tự xem “đã gửi revoke event” là device offline đã nhận hoặc chấp hành.

### Giới hạn của CRL/OCSP trong mạng phân đoạn

Nếu gateway không thể truy cập OCSP/CRL, cần **chính sách revocation freshness, phân phối trạng thái nội bộ, TTL và xử lý khi nguồn không khả dụng** phù hợp mức rủi ro. Không mặc định fail-open; nhưng cũng cần thiết kế availability/safety có kiểm soát, chứ không rút toàn bộ chức năng quan trọng khi chưa có phương án vận hành an toàn.

## 21. Bảo toàn chứng cứ, data protection và remote wipe

Lệnh xóa/khóa có thể ảnh hưởng **tính sẵn sàng, khả năng điều tra, dữ liệu cá nhân và quyền sở hữu thiết bị**.

### Quyết định trước khi wipe

1. Thiết bị thuộc tổ chức, BYOD hay đối tác?
2. Dữ liệu tại chỗ có được mã hóa và quản lý key đúng chính sách không?
3. Có khả năng selective wipe dữ liệu công ty thay vì full wipe không?
4. Có nghi sự cố bảo mật cần forensic image, audit/chain of custody không?
5. Thiết bị online và có nhận lệnh hay chưa?
6. Có tài khoản/dịch vụ production phụ thuộc thiết bị?
7. Ai được phê duyệt hành động có thể hủy chứng cứ/dữ liệu?
8. Những credentials/token vẫn có thể được dùng **sau wipe** từ nơi khác?

### Lệnh gửi và lệnh hoàn thành khác nhau

~~~text
MDM Command:
    WIPE_REQUESTED at 09:30
    device offline from 09:15
    WIPE_ACKNOWLEDGED = false

Correct status:
    WIPE_PENDING / UNVERIFIED

Incorrect claim:
    "Device data erased and safe" only because API returned 202.
~~~

Một wipe được thiết bị xác nhận cũng không chứng minh **mọi bản sao dữ liệu đã bị truy cập trước đó** hoặc credentials đã bị lấy cắp. Hãy xử lý token/key/trust và exposure assessment độc lập.

### Chain of custody

Khi cần điều tra, ghi **ai thu thập thiết bị hoặc forensic evidence, lúc nào, bằng công cụ/quy trình nào, hash/tính toàn vẹn, nơi lưu, ai có quyền xem**. Không tự ý thay đổi hoặc xóa dấu vết chỉ để đưa device về compliance.

## 22. Khôi phục niềm tin: quarantine không tự hết khi máy online trở lại

Mục tiêu phục hồi không phải “máy đã kết nối MDM” mà là **thiết bị, identity, khóa, cấu hình và các đường truy cập đáp ứng lại yêu cầu tin cậy hiện hành**.

### Những điều kiện được xem trước khi khôi phục

| Điều kiện | Bằng chứng phù hợp |
| --- | --- |
| **Incident đã được đánh giá** | IR kết luận root cause/phạm vi cần thiết hoặc có quyết định rebuild an toàn. |
| **Asset identity đúng** | Device hardware/instance identity, tenant/asset và owner xác minh. |
| **Đường boot/runtime đáng tin** | Reimage/rebuild từ nguồn được kiểm soát, security baseline, attestation nếu có. |
| **Credential mới** | Key/certificate/token trust được phát sau khi xử lý ảnh hưởng, không tái dùng bí mật nghi lộ. |
| **Enrollment hợp lệ** | MDM/UEM/registry thông qua quy trình có quyền và chống enrollment giả. |
| **Posture đủ mới** | Encryption, EDR, patch, key protection, lastAttestedAt và chính sách tương ứng. |
| **JML/owner hiện hành** | User/workload/service owner còn ACTIVE, đúng team/tenant. |
| **Quyền tối thiểu** | RBAC/ABAC/PBAC, SoD, resource scope, JIT nếu cần. |
| **Không còn đường cũ trái phép** | Certificate cũ, token/key/session, direct grants đã được xử lý. |
| **Test dương và âm** | Identity mới hoạt động đúng; đường cũ/bị revoke bị từ chối. |

### Nên dùng identity cũ hay tạo identity mới?

Phụ thuộc **khả năng chứng minh continuity và threat model**:

- Nếu device chỉ **hết kiểm tra posture** và đã khắc phục cập nhật an toàn, có thể revalidate/enroll lại theo policy mà không cần thay hardware identity.
- Nếu **private key bị lộ hoặc host bị compromise**, việc phát khóa/chứng chỉ mới và vô hiệu credential cũ thường cần thiết; đôi khi nên tạo **new enrollment/device identity instance**.
- Nếu asset đổi owner hoặc tenant, cần tránh reuse trust, sessions và credential của người/tenant trước.
- Nếu máy đã decommission và số serial/hostname được tái sử dụng, stable ID/lịch sử phải ngăn **ghost device identity** quay lại tự động.

### Re-enrollment không phải “xóa cờ compromised”

Một attacker có thể cố re-register thiết bị bị block bằng User account vẫn còn hợp lệ. Vì vậy việc quay lại trạng thái trusted cần **proofing chủ thể, phương thức enrollment được bảo vệ, policy của asset/tenant, key mới khi cần và kiểm soát recovery**.

### Mô hình state machine

~~~mermaid
stateDiagram-v2
    [*] --> REGISTERED
    REGISTERED --> TRUSTED: Enrollment, proofing, posture verified
    TRUSTED --> STALE: Posture/heartbeat timeout
    STALE --> TRUSTED: Revalidation succeeds
    STALE --> QUARANTINED: Risk policy requires restriction
    TRUSTED --> SUSPECTED: Loss report / threat signal
    SUSPECTED --> QUARANTINED: Containment decision
    SUSPECTED --> TRUSTED: Investigation clears + revalidation
    QUARANTINED --> REVOKED: Credential/trust compromised or retire
    QUARANTINED --> REVALIDATING: Remediation or rebuild verified
    REVOKED --> REVALIDATING: New authorized enrollment, new credential
    REVALIDATING --> TRUSTED: Required proofs and access checks pass
    REVALIDATING --> QUARANTINED: Verification fails
    REVOKED --> DECOMMISSIONED: Retirement confirmed
    DECOMMISSIONED --> [*]
~~~

**Đây là một ví dụ trạng thái vận hành**, không phải protocol bắt buộc. Chuyển từ REVOKED sang REVALIDATING cần chính sách rõ: có thể là **thiết bị được cấp danh tính mới**, không phải khôi phục certificate/key đã bị revoke.

## 23. Race condition, cache và event đến sai thứ tự

Device trust là trạng thái phân tán. Một event MDM, thay đổi IdP và certificate revocation có thể đến các điểm kiểm soát **không đồng thời**, gây cửa sổ truy cập trái policy.

### Tình huống retry cũ tái mở thiết bị

~~~text
v41 Joiner: enroll dev-882, trust=TRUSTED
v42 Incident: dev-882 reported LOST, trust=BLOCKED
v43 PKI: cert-1 revoked

Execution order:
    v42/v43 complete
    delayed v41 enrollment retry arrives

Required:
    v41 cannot recreate trust for cert-1/dev-882
    without a new authorized recovery/re-enrollment process.
~~~

Điều này tương tự các race trong Joiner–Mover–Leaver: một **job cấp quyền cũ** không được ghi đè **trạng thái thu hồi mới**. Cần authority source, version theo device/identity, idempotency key và guard tại **thời điểm commit**, không chỉ ở bước đọc queue.

### Bảng lỗi đồng thời

| Race hoặc lỗi | Nguy cơ | Biện pháp |
| --- | --- | --- |
| Enrollment retry sau revoke | Trust và certificate bị mở lại. | SourceVersion/epoch, terminal guard hoặc yêu cầu recovery mới. |
| User Leaver sau khi request certificate được duyệt | Phát credential cho người đã nghỉ. | Revalidate human lifecycle tại issuance. |
| Device đã LOST nhưng posture cache vẫn COMPLIANT | API nhận trust cũ. | Tách trust revoke khỏi compliance, freshness/deny signal ưu tiên. |
| CA revoke nhưng CRL chưa cập nhật gateway | New mTLS handshake vẫn vào được. | Kiểm revocation distribution, policy freshness, containment tại gateway. |
| Session đã mở trước khi certificate revoke | Session tiếp tục. | Session termination/authorization recheck theo target. |
| Re-enrollment song song với incident response | Máy bị nghi compromise được xem trusted quá sớm. | Điều kiện release quarantine và verified recovery version. |
| Hai operator cùng gán owner khác nhau | Thu hồi nhầm hoặc mất attribution. | Optimistic concurrency, owner registry có thẩm quyền. |
| Device đổi tenant trong khi token tenant cũ còn sống | Có cross-tenant access. | Revoke old trust/session, issue new tenant scoped identities. |
| API timeout khi gửi revoke | Không biết đã revoke chưa; retry không an toàn. | Readback theo credential ID, idempotent retry. |
| Device ID được tái sử dụng sau decommission | Old trust có thể gắn máy khác. | Stable namespace, tombstone, fresh identity/attestation. |

### Không dùng timestamp một mình làm authority

Một hệ thống có **eventAt**, **receivedAt**, **observedAt** và **effectiveAt**; nguồn khác nhau có semantics khác nhau. Một message mới đến chưa chắc mô tả sự kiện mới hơn. Ví dụ certificate được revoke lúc 10:00, sau đó MDM gửi một posture report được tạo lúc 09:55 nhưng đến 10:05. Không dùng report cũ để đảo trạng thái REVOKED.

### Quan hệ incident state với JML

Khi một device mất kiểm soát, có thể cần cập nhật cả identity người và machine. Ngược lại, một User Leaver có thể làm thiết bị được gán **không còn eligible cho role** dù bản thân máy chưa compromise. Hãy quản lý **hai trạng thái độc lập** và áp luật cho cả hai:

~~~text
resourcePermit =
    humanOrWorkloadEligible
    AND deviceTrustedForResource
    AND entitlementValid
    AND sessionValid
    AND resourcePolicyAllows
~~~

Điều này giúp tránh hai lỗi: **block toàn tổ chức chỉ vì một device** và **Permit vì User còn ACTIVE dù device đã revoke**.

## 24. Desired, observed và effective device access

Quản trị thành công phải kiểm chứng ba lớp.

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Desired trust/access** | Theo incident và policy, device còn được phép gì? | dev-882 LOST: chỉ có remediation channel, không được FinanceReports. |
| **Observed state** | Registry, CA, IdP, gateway, app và MDM thực tế báo gì? | CA revoked cert-1; app cookie vẫn active. |
| **Effective access** | Device/key/token/session còn thực hiện được hành động gì tại resource? | API có còn trả dữ liệu qua JWT cũ hay không? |

### Bảng reconciliation

| Desired | Observed | Effective | Kết luận |
| --- | --- | --- | --- |
| Device trusted và thuộc đúng owner | Enrollment valid, posture đủ mới | Resource cho phép đúng scope | MATCH. |
| Device LOST, chặn ứng dụng | IdP device blocked | SaaS local session còn đọc được | RESIDUAL_ACCESS. |
| Device COMPROMISED, cert revoke | CA revoked | Gateway không kiểm CRL nên mTLS còn thành công | REVOCATION_ENFORCEMENT_GAP. |
| Device NONCOMPLIANT, chỉ remediation | UEM quarantine | Endpoint nhận update được, Finance API Deny | MATCH theo policy remediation. |
| Device REVOKED, không tạo lại | Enrollment job cũ active | API còn cấp device assertion | STALE_REGRANT. |
| Device cần recover | Credential mới, posture đạt | Old key Deny, new key đúng scope Permit | RECOVERY_VERIFIED. |
| Thiếu API để kiểm sessions | Registry báo blocked | Không thể xác minh app-local session | UNKNOWN_EFFECTIVE_ACCESS. |

**Không được chuyển UNKNOWN thành VERIFIED** để đạt KPI. Một hệ thống báo “no active devices” nhưng connector thiếu quyền đọc hoặc phân trang chưa đầy đủ không thể là bằng chứng sạch.

### Kiểm tra negative có kiểm soát

Với certificate hoặc token đã thu hồi, có thể dùng **test credential/identity được phép** để xác nhận gateway từ chối trong môi trường phù hợp. Không nên thử brute-force, tái sử dụng secret của người thật hoặc thực hiện hành động phá hoại trên production chỉ để xác minh Deny. Với action nhạy cảm, dùng policy simulation/dry-run hoặc mục tiêu thử nghiệm không gây side effect nếu đủ tin cậy.

### Độ phủ xác minh

Nếu một laptop có 5 đường truy cập bắt buộc thu hồi nhưng mới chứng minh được 3 đường, **coverage=3/5**, không phải đã xử lý xong. Cần ghi danh mục nguồn/đường truy cập, loại credential, verifiedAt và owner cho hai đường còn lại.

## 25. Pseudocode xử lý device mất kiểm soát

Mã giả chỉ minh họa các **invariants và quyết định nghiệp vụ**. Không phải code production hoặc API của một nền tảng IdP/MDM/PKI cụ thể.

### 25.1. Tiếp nhận và phân loại sự cố

~~~text
handleDeviceControlIncident(report):
    evidence = verifySourceAndIncident(report)
    device = resolveTrustedDevice(
        provider = report.provider,
        tenant = report.tenant,
        deviceId = report.deviceId
    )

    if device unresolved or evidence untrusted:
        recordInvestigationWithoutMutatingUnknownDevice(report)
        return IDENTITY_OR_EVIDENCE_UNRESOLVED

    current = loadCurrentDeviceStateAndVersion(device)
    classification = assessDeviceRisk(
        evidence,
        device.owner,
        device.entitlements,
        device.lastAttestation,
        device.dataClassification
    )

    with versionGuard(device):
        recordIncidentAndClassification(
            device,
            classification,
            evidence.reference,
            effectiveAt = report.effectiveAt
        )
        if classification.requiresContainment:
            transitionToQuarantineOrRevokedAccordingToPolicy(device)
            blockNewDeviceTrustAndCredentialIssuance(device)

    enqueueScopedCredentialAndSessionAssessment(
        device,
        incidentId = report.incidentId,
        stateVersion = device.currentVersion
    )

    return CONTAINMENT_STARTED_OR_INVESTIGATION_REQUIRED
~~~

**Tách bước “nghi vấn” khỏi “đã xác nhận”**, nhưng không đợi bằng chứng hoàn hảo mới chặn một đường truy cập nguy hiểm khi risk policy cho phép containment khẩn cấp.

### 25.2. Revoke các đường có thể bị ảnh hưởng

~~~text
reconcileCompromisedDevice(deviceRef, incidentId):
    device = loadCurrentTrustedDevice(deviceRef)
    incident = loadCurrentIncident(incidentId)
    if incident not linked to device:
        return DENY_WRONG_TARGET

    paths = inventoryRequiredCredentialAndAccessPaths(
        deviceRef,
        includeCertificates = true,
        includeSessions = true,
        includeTokens = true,
        includeLocalGrants = true,
        includeWorkloadCredentials = true
    )

    if paths.hasUnknownOwnershipOrIncompleteCoverage:
        recordInvestigationAndContainmentOwner(paths)

    for path in paths.verifiedAffectedPaths:
        if incident.policyRequiresRevocation(path):
            revokeOrRotateIdempotently(path, incident.version)
        else if incident.policyRequiresRestriction(path):
            restrictToRemediationScope(path)

    observed = readBackAllRequiredSources(paths)
    effective = verifyTargetEnforcementWhereSupported(paths)

    if observed.hasUnverifiedPaths or effective.hasResidualAccess:
        return PARTIAL_FAILURE_WITH_OWNER_AND_DEADLINE

    return VERIFIED_FOR_SCOPE_OF_CHECKED_PATHS
~~~

Đối với **workload production đang hoạt động**, việc revoke cần phối hợp dependency và phương án thay thế credential để tránh outage không cần thiết; không xóa mù một service account chỉ vì host/owner có liên quan tới sự cố.

### 25.3. Không tự tin cậy trở lại khi có thiết bị online

~~~text
requestDeviceRecovery(deviceRef, newEnrollmentEvidence):
    old = loadCurrentDeviceAndIncident(deviceRef)
    if old.incidentState not eligibleForRecovery:
        return DENY

    proof = validateAssetOwnershipAndIdentity(newEnrollmentEvidence)
    security = validateRebuildOrRemediationAndFreshPosture(proof)
    keys = verifyFreshKeysAndRequiredCertificateIssuance(proof)
    lifecycle = verifyCurrentHumanOrServiceOwnership(old)

    if any required proof unavailable:
        return REVALIDATION_REQUIRED
    if not oldCredentialRevocationBoundaryVerified:
        return PARTIAL_FAILURE_OR_COMPENSATING_REVIEW

    newIdentity = issueOrLinkNewDeviceIdentityAccordingToPolicy(
        old.deviceRef, proof, keys, lifecycle
    )
    assignMinimalAccessUsingCurrentPolicy(newIdentity)

    if positiveAndNegativeAccessChecksPass(newIdentity, old):
        markTrustedWithIncidentClosureEvidence(newIdentity)
        return RECOVERED_VERIFIED

    quarantine(newIdentity)
    return RECOVERY_PARTIAL_FAILURE
~~~

### 25.4. Chặn job cũ sau revoke/Leaver

~~~text
provisionDeviceTrust(job):
    device = loadLatestAuthoritativeDeviceState(job.deviceRef)
    principal = loadLatestOwnerOrWorkloadLifecycle(job.principalRef)

    if job.deviceVersion is superseded by device.version:
        return SUPERSEDED_NO_GRANT
    if device.trustState in {LOST, COMPROMISED, REVOKED, DECOMMISSIONED}:
        return DENY_NO_GRANT
    if principal is not eligible under current policy:
        return DENY_NO_GRANT
    if enrollmentProofOrScopeNotCurrent(job):
        return DENY_NO_GRANT

    return provisionIdempotentlyAndReadBack(job)
~~~

### 25.5. Các giả định không được ẩn

- Một nguồn có version tăng dần không có nghĩa tất cả nguồn **cùng một thứ tự toàn cục**.
- “Certificate revoked” không bảo đảm relying party đã kiểm revocation.
- “Wipe command accepted” không bảo đảm device offline đã xóa dữ liệu.
- “User disabled” không bảo đảm mọi token, local session và service principal đã bị xử lý.
- Một User có thể sở hữu nhiều devices; một device có thể liên kết nhiều identities.
- Chính sách phải phân biệt **chặn truy cập ngay** với **bảo toàn hoạt động safety-critical**.

## 26. Audit, evidence và khả năng truy vết

Audit của một sự cố device mất kiểm soát phải trả lời: **Thiết bị nào? Ai chịu trách nhiệm? Có đường truy cập gì? Phản ứng đã thực thi tới đâu? Và bằng chứng nào chứng minh không còn quyền trái phép?**

### Trường nên lưu

| Trường | Mục đích |
| --- | --- |
| incidentId, correlationId | Ghép hoạt động giữa MDM, IdP, PKI, PAM, Resource Server. |
| deviceRef, tenant, assetRef, enrollmentId | Xác định device đúng namespace, tránh nhầm thiết bị. |
| assignedHumanIdentityId / serviceOwnerId | Liên kết JML và ownership. |
| classification, evidenceSource, confidence | Phân biệt nghi ngờ, xác nhận, offline và noncompliant. |
| eventAt/detectedAt/observedAt | Phân tích độ trễ phát hiện và dữ liệu stale. |
| lifecycle sourceVersion/effectiveAt | Chặn race, phục dựng trạng thái tại thời điểm sự cố. |
| certificate serial/issuer/key ID | Truy vết credential được revoke/rotate, không lưu private key. |
| sessionRef/tokenRef (không raw secret) | Nhận diện những đường cần thu hồi. |
| resource/action/tenant scope | Tránh thu hồi ngoài phạm vi và biết mức ảnh hưởng. |
| containment action/command status | Phân biệt requested, acknowledged, applied và verified. |
| reviewer/approver, change/IR evidence | Chứng minh thẩm quyền hành động. |
| target readback, verification result/time | Đánh giá quyền hiệu lực. |
| recovery enrollment/attestation lineage | Biết thiết bị mới có thay thế an toàn thiết bị cũ chưa. |
| unresolved paths, owner/deadline | Quản lý PARTIAL_FAILURE. |

### Audit event minh họa

~~~json
{
  "eventType": "IAM_DEVICE_TRUST_REVOKE_VERIFICATION",
  "incidentId": "INC-DEVICE-2026-008",
  "deviceRef": "uem:tenant-b:dev-882",
  "assignedIdentityId": "IAM:ID-LAN-2041",
  "classification": "LOST_CONFIRMED",
  "deviceStateVersion": 43,
  "credentialRef": "pki:issuer-a:serial-5566",
  "action": "REVOKE_CERTIFICATE_AND_BLOCK_DEVICE_TRUST",
  "observedAt": "2026-12-01T09:45:00+07:00",
  "verification": {
    "issuerRevocation": "CONFIRMED",
    "gatewayNewHandshake": "DENIED",
    "existingAppSession": "PENDING_VERIFICATION"
  },
  "overallStatus": "PARTIAL_FAILURE",
  "correlationId": "device-882-inc-008"
}
~~~

**Các trường là schema bài học, không phải chuẩn chung.** Không ghi password, raw OAuth token, session cookie, seed MFA, private key, dữ liệu khách hàng nhạy cảm hoặc forensic content không cần thiết vào các event.

### Chất lượng bằng chứng và cấp xác minh

| Bằng chứng | Có thể chứng minh | Chưa chứng minh |
| --- | --- | --- |
| UEM báo QUARANTINED | Registry đã ghi trạng thái quarantine. | Device offline đã nhận lệnh, API khác đã chặn. |
| EDR isolation requested | Đã gửi yêu cầu cách ly. | Sensor đã thực thi và credential bên ngoài vô hiệu. |
| CA trả revoke accepted | CA ghi nhận lệnh thu hồi. | Mọi relying party đã kiểm trạng thái. |
| IdP báo device disabled | Đăng nhập mới qua IdP có thể bị chặn theo policy. | SaaS local sessions/PAT đã bị revoke. |
| Resource API test denied | Một action theo ngữ cảnh test đã bị chặn. | Tất cả đường, tenant, session không được test đều bị chặn. |
| Target inventory readback đầy đủ | Grant/ACL/token trạng thái hiện hành theo API. | Quyền hiệu lực qua đường khác nằm ngoài API ấy. |

### Privacy và thông tin thiết bị

Device telemetry có thể chứa vị trí, thông tin cá nhân, ứng dụng sử dụng và hoạt động người dùng. Chỉ thu thập dữ liệu **cần thiết cho bảo mật và xử lý sự cố**, giới hạn người xem, thời gian lưu, bảo vệ log và tuân thủ quy định/phân loại dữ liệu áp dụng.

## 27. Chỉ số giám sát quản lý thiết bị mất kiểm soát

| Chỉ số | Điều cần đo |
| --- | --- |
| **Time to detect device loss/compromise** | Từ event hoặc thời điểm có dấu hiệu tới detection. |
| **Time to block new device trust** | Từ incident tới khi IdP/gateway thực thi deny mới. |
| **Time to verified certificate revocation** | Từ revoke tới khi relying party liên quan từ chối. |
| **Residual session duration** | Session/token còn dùng được bao lâu sau trạng thái mất kiểm soát. |
| **Unmanaged/noncompliant device access count** | Bao nhiêu resource nhạy cảm vẫn chấp nhận thiết bị không đủ posture. |
| **Unknown owner devices** | Thiết bị hoạt động nhưng không có owner/sponsor được xác minh. |
| **Stale posture accepted** | Lần truy cập được Permit dựa trên posture quá freshness. |
| **Revocation coverage** | Tỷ lệ credential/access path trong scope đã được xử lý. |
| **Wipe/lock command acknowledgment lag** | Độ trễ từ lệnh tới ack, phân biệt thiết bị offline. |
| **Unverified incidents** | Sự cố đóng trên ticket nhưng chưa chứng minh mất quyền. |
| **Device re-enrollment failures/abuse** | Recovery/enrollment trái policy hoặc không đạt verification. |
| **Lost devices after Leaver** | Tài sản/credential còn liên kết với người đã nghỉ. |
| **Workload credential exposure count** | Service keys/tokens có khả năng lộ từ host bị compromise. |
| **Policy version/freshness drift** | IdP, gateway, PKI, API không đồng bộ rule/status. |
| **False-positive containment impact** | Workload/User hợp lệ bị chặn quá rộng do mapping sai. |

### Báo cáo số liệu phải thể hiện mẫu số

Ví dụ có 20 incident, trong đó 18 đã gửi revoke, 16 có target readback và 13 đã xác minh đủ access paths. Không được công bố **“90% đã khắc phục hoàn toàn”** chỉ vì 18/20 lệnh được gửi. Cần tách:

- Tỷ lệ phát lệnh containment/revocation.
- Tỷ lệ target acknowledgment.
- Tỷ lệ readback hoàn tất.
- Tỷ lệ effective access được kiểm tra và đạt.
- Các đường chưa thể xác minh, owner và deadline.

Không lấy **“mọi device đều compliant”** làm mục tiêu đơn lẻ: một device có trạng thái compliant nhưng certificate/key bị lộ vẫn là rủi ro; một device offline tạm thời chưa thể được kết luận đã compromise chỉ từ một heartbeat trễ.

## 28. Ma trận kiểm thử thiết bị mất kiểm soát

Kiểm thử phải bao phủ **phân loại sự cố, identity mapping, trust/revocation, JML, người và máy, offline behavior, phiên/token cũ, sự kiện đến muộn, recovery và audit**. Dùng test principals và môi trường được phê duyệt; không tự tạo malware, đánh cắp credential thật hoặc xóa dữ liệu production để kiểm tra.

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| MI-01 | Thiết bị trusted, owner hợp lệ, posture mới và role đúng. | Được truy cập đúng tài nguyên/action đã phê duyệt. |
| MI-02 | Device không được enroll, User vẫn đăng nhập hợp lệ. | Tài nguyên yêu cầu managed device từ chối hoặc yêu cầu enrollment. |
| MI-03 | MDM heartbeat quá freshness threshold nhưng chưa có bằng chứng compromise. | Áp chính sách stale/unknown, không tự gắn nhãn confirmed compromise. |
| MI-04 | Laptop bị owner xác minh LOST. | Chặn trust/device access mới, xử lý credential/session theo scope. |
| MI-05 | Device LOST đang offline khi gửi remote wipe. | Wipe PENDING/UNVERIFIED, không báo đã xóa dữ liệu. |
| MI-06 | Owner báo nhầm device ID thuộc nhân viên khác. | Mapping conflict, không thu hồi mù thiết bị không liên quan. |
| MI-07 | CA revoke certificate nhưng gateway chưa cập nhật CRL. | Phát hiện revocation enforcement gap; không VERIFIED. |
| MI-08 | Gateway dùng certificate revoked cho new mTLS handshake. | Từ chối theo revocation policy, ghi audit. |
| MI-09 | TLS session tồn tại trước khi cert revoke. | Kiểm tra session boundary và hành động còn dùng được. |
| MI-10 | Private key cert bị lộ, reissue cert với cùng key. | Recovery không được xác minh; tạo key mới theo policy. |
| MI-11 | Hai device dùng cùng credential trái enrollment policy. | Phát hiện clone/reuse, điều tra nguồn và khóa. |
| MI-12 | EDR báo compromise nhưng IdP posture cache còn COMPLIANT. | Không dùng cache để bỏ qua incident block, kiểm nguồn/freshness. |
| MI-13 | Device bị quarantine nhưng cần gọi endpoint cập nhật agent. | Chỉ cho phép remediation channel đã được duyệt. |
| MI-14 | User Lan có hai thiết bị, chỉ dev-882 bị mất. | Chặn dev-882; không tự khóa device khác khi chưa có evidence. |
| MI-15 | Laptop mất có refresh token và app cookie. | Xử lý token/session qua từng issuer/app, đo quyền tồn dư. |
| MI-16 | IdP disabled device, SaaS PAT còn được API chấp nhận. | Không VERIFIED; thu hồi PAT hoặc containment phù hợp. |
| MI-17 | Device certificate revoke nhưng SSH key riêng còn hoạt động. | Phát hiện đường SSH độc lập; không kết luận an toàn giả. |
| MI-18 | Joiner pre-enroll trước startAt. | Không truy cập business data trước activation. |
| MI-19 | Joiner bị HR hủy, enrollment job cũ retry. | Không tự mở lại device trust hoặc cấp quyền. |
| MI-20 | Mover chuyển device sang tenant khác. | Revoke trust/session tenant cũ, re-enroll đúng tenant mới. |
| MI-21 | Laptop bàn giao người mới còn cookie của owner cũ. | Quy trình reset/revoke ngăn truy cập account cũ. |
| MI-22 | Leaver đã disable User nhưng laptop không trả lại. | Xử lý device như unreturned/lost, chặn trust và credentials. |
| MI-23 | Leaver là owner server production đang chạy service hợp lệ. | Thu hồi human access, bàn giao service owner, không xóa mù workload. |
| MI-24 | Workload staging credential gọi production API. | Deny nếu trust/environment/audience không đúng. |
| MI-25 | Compromised CI host có khả năng phát token mới qua federation. | Revoke/giới hạn trust nguồn host, không chỉ revoke token cũ. |
| MI-26 | IoT device không check-in thường xuyên theo thiết kế. | Áp freshness policy đúng loại thiết bị, không auto wipe. |
| MI-27 | OT controller nghi compromise nhưng cô lập có thể gây safety impact. | Bắt buộc phối hợp OT/safety và runbook tương ứng. |
| MI-28 | Device đã revoke, bị re-enroll tự động qua account User còn hợp lệ. | Recovery proofing/policy ngăn đường tái lập trái phép. |
| MI-29 | Job Joiner version cũ tới sau revocation mới. | Không resurrect trust; superseded. |
| MI-30 | API revoke timeout sau khi target đã thay đổi. | Readback, retry idempotent, không sửa nhầm credential. |
| MI-31 | CA revoked nhưng relying party bỏ kiểm OCSP/CRL khi offline. | Ghi gap, deny/contain theo policy đã duyệt, không báo Verified. |
| MI-32 | Thiết bị recovery đã có key mới và posture đạt nhưng old PAT còn sống. | Recovery chưa hoàn toàn VERIFIED nếu PAT thuộc scope phải thu hồi. |
| MI-33 | Device bị mất, forensic evidence cần bảo toàn. | Phối hợp IR/forensic trước wipe phá chứng cứ khi khả thi. |
| MI-34 | Wipe ack thành công nhưng raw secret đã bị copy từ trước. | Không coi wipe đã xử lý credential exposure. |
| MI-35 | User account hợp lệ nhưng device trust bị REVOKED tại PEP. | Từ chối action yêu cầu trusted device. |
| MI-36 | Workload identity hợp lệ nhưng node host bị COMPROMISED. | Kiểm host/workload trust, isolate hoặc revoke theo risk policy. |
| MI-37 | Revoke Device A làm ngừng bất ngờ service chung Device B. | Phát hiện quá rộng, kiểm ownership/path và compensation. |
| MI-38 | Resource API trả 403 nhưng side effect vẫn được commit. | Test FAIL, authorization phải kiểm trước thao tác. |
| MI-39 | Inventory API thiếu trang, kết quả trả no devices. | Mark INCOMPLETE, không ghi “không còn thiết bị”. |
| MI-40 | Incident được đóng khi app-local session còn hoạt động. | PARTIAL_FAILURE/UNVERIFIED, có owner và deadline. |

### Kiểm thử Given–When–Then

~~~gherkin
Feature: A lost or compromised device cannot retain unauthorized access

  Scenario: The resource denies a lost trusted device
    Given a managed laptop was registered for Lan
    And the device is verified as LOST
    And the resource requires current trusted device posture
    When a session associated with that laptop requests sensitive data
    Then the request is denied according to the revocation policy
    And the denial is correlated with the device incident

  Scenario: A cached compliant posture cannot override revocation
    Given the device registry marks dev-882 as REVOKED
    And the IdP cache still contains a COMPLIANT posture
    When the device attempts a new privileged session
    Then the new session is denied
    And the outdated posture does not restore trusted status

  Scenario: A delayed Joiner job cannot re-enroll a revoked device
    Given an authorized security incident revoked dev-882
    And an older Joiner enrollment task remains in the queue
    When that task retries
    Then no device trust or certificate is reissued by the old task
    And the task is recorded as superseded

  Scenario: A Leaver does not silently keep device-based access
    Given a human worker has an enrolled corporate device
    And an authoritative Leaver event is effective
    When the old session requests a resource requiring an active worker
    Then access is denied under current lifecycle policy
    And local app sessions and tokens are reconciled

  Scenario: Workload recovery uses new credentials and keeps least privilege
    Given a production host with a workload identity is compromised
    And its affected credentials and trust paths were identified
    When the workload is rebuilt on a verified host
    Then newly authorized credentials are issued within approved scope
    And old affected credentials are denied where policy requires
    And unrelated workload identities are not revoked without cause

  Scenario: An offline wipe command is not proof of erasure
    Given a lost laptop has not connected to the UEM service
    When a remote wipe command is sent
    Then the wipe state remains pending or unverified
    And account and credential containment proceeds independently
~~~

### Kiểm thử phải xác minh hiệu lực

Nếu MDM/PKI/IdP trả thành công nhưng **API vẫn trả dữ liệu cho token cũ**, bài test phải báo không đạt policy revocation. Nếu xóa token rồi User hợp lệ vẫn truy cập được qua máy mới theo policy, đó có thể là **kết quả đúng**; không cần khóa mọi hoạt động của người dùng nếu chỉ một thiết bị bị mất.

Không sử dụng những action gây thiệt hại trên production để “chứng minh Deny”. Với permission xóa, chuyển tiền, deploy hoặc tắt hạ tầng, dùng sandbox, giả lập policy đáng tin hoặc test resource được phê duyệt, đồng thời ghi rõ giới hạn coverage.

## 29. Các tình huống thực hành

### Tình huống A — Laptop bị mất, IdP đã chặn nhưng SaaS còn cookie

**Bối cảnh:** Lan báo mất laptop công ty. Security gỡ đăng ký thiết bị và chặn sign-in mới ở IdP. Tuy nhiên ứng dụng Finance vẫn giữ cookie phiên cũ.

**Câu hỏi:** Có được báo “đã chặn mọi quyền” không?

**Gợi ý:** Không. Cần xử lý session ứng dụng, refresh/access tokens, PAT nếu có và kiểm tra tại Finance API. IdP blocked chỉ chứng minh phần đường truy cập thuộc IdP.

### Tình huống B — EDR mất kết nối 30 giờ

**Bối cảnh:** Thiết bị IoT gửi heartbeat mỗi 48 giờ theo thiết kế, nhưng một rule được sao chép từ laptop cho rằng quá 24 giờ là compromise.

**Câu hỏi:** Vấn đề ở đâu?

**Gợi ý:** Freshness policy không phù hợp loại thiết bị. Có thể áp hạn truy cập theo telemetry nhưng không gắn nhãn compromised hoặc wipe khi không có bằng chứng khác, nhất là nếu ảnh hưởng safety.

### Tình huống C — Chứng chỉ đã revoke nhưng mTLS vẫn vào được

**Bối cảnh:** CA đã revoke cert-1. Gateway vẫn chấp nhận certificate vì không kiểm CRL/OCSP trong một số trường hợp.

**Câu hỏi:** Lỗi thuộc về CA hay điểm thực thi?

**Gợi ý:** Cần kiểm toàn chuỗi. CA có thể đã ghi revoke đúng, nhưng relying party không enforce trạng thái. Ghi revocation enforcement gap và thực hiện containment ở gateway/API theo policy.

### Tình huống D — Thiết bị mới dùng lại private key đã lộ

**Bối cảnh:** Đội vận hành reimage máy bị compromise, rồi cấp certificate mới từ cùng private key để đỡ sửa cấu hình.

**Câu hỏi:** Có khôi phục trust an toàn không?

**Gợi ý:** Không nếu private key đã bị nghi compromise. Phải đánh giá tạo khóa mới trong môi trường đáng tin và thu hồi khóa/chứng chỉ cũ, revalidate enrollment.

### Tình huống E — Hợp đồng nhân viên kết thúc nhưng server vẫn chạy

**Bối cảnh:** Một nhân viên là owner của CI node production nghỉ việc. Workflow Leaver muốn xóa mọi device gắn identity người ấy.

**Câu hỏi:** Có nên xóa CI node ngay?

**Gợi ý:** Không tự động. Thu hồi human admin grants, chuyển service owner, kiểm tra secret/token người cũ có thể biết và thay trust, nhưng giữ continuity của workload hợp lệ qua quy trình thay thế.

### Tình huống F — Thiết bị bị mất nhưng người dùng còn điện thoại đáng tin

**Bối cảnh:** Lan mất laptop dev-882, còn điện thoại dev-311 đã đăng ký và không có dấu hiệu bị lộ.

**Câu hỏi:** Có bắt buộc khóa toàn bộ Human identity của Lan không?

**Gợi ý:** Tùy bằng chứng. Ít nhất chặn device dev-882 và các phiên liên quan. Có thể cần tăng mức bảo vệ account/reset nếu credential phơi lộ, nhưng không tự kết luận mọi thiết bị khác đã bị compromise.

### Tình huống G — Mover bàn giao laptop cho nhân viên khác

**Bối cảnh:** Device dev-882 được đổi owner trong CMDB từ Lan sang Minh, không wipe hoặc revoke session cũ.

**Câu hỏi:** Rủi ro chính?

**Gợi ý:** Người mới có thể thừa hưởng token, local user state, SSH key hoặc dữ liệu của người cũ. Cần secure reset/reimage theo policy, thu hồi cũ, re-enroll và cấp quyền theo identity mới.

### Tình huống H — Client certificate được lưu trong TPM

**Bối cảnh:** Device có khóa non-exportable trong TPM nhưng EDR phát hiện code độc hại chạy với quyền cao.

**Câu hỏi:** Có thể cho phép tiếp tục vì private key không export được không?

**Gợi ý:** Không. Attacker có thể sử dụng chính device/khóa khi điều khiển runtime. Cần đánh giá compromise, containment, revoke sessions/trust và khôi phục device.

### Tình huống I — Remote wipe chưa được thiết bị nhận

**Bối cảnh:** MDM API trả 202 và lệnh wipe queued; laptop offline nhiều ngày.

**Câu hỏi:** Báo trạng thái thế nào?

**Gợi ý:** WIPE_PENDING/UNVERIFIED, không khẳng định dữ liệu đã bị xóa. Tách containment tài khoản, certificate, token và risk assessment dữ liệu tại chỗ.

### Tình huống J — Host compromised nhưng có nhiều services

**Bối cảnh:** Node chạy Payments API, metrics collector và deploy agent. Một credential CI có quyền production nhưng các services khác chỉ đọc dữ liệu không nhạy cảm.

**Câu hỏi:** Nên xử lý tất cả cùng một cách?

**Gợi ý:** Đánh giá toàn bộ affected credentials theo graph và threat model, ưu tiên CI credential rủi ro cao, xác minh các quyền khác. Thực hiện rebuild/rotation phối hợp để không làm tê liệt các workload hợp lệ hoặc bỏ sót trust của node.

### Tình huống K — Device re-enroll sau khi bị revoke

**Bối cảnh:** Thiết bị mất được tìm lại. User đăng nhập và agent tự re-enroll, gateway lập tức Permit API sensitive.

**Câu hỏi:** Điều kiện còn thiếu?

**Gợi ý:** Cần chứng minh quyền sở hữu/chain of custody, xử lý risk, fresh key nếu cần, kiểm posture và credential cũ; tự re-enroll bằng User session không chứng minh thiết bị đáng tin trở lại.

### Tình huống L — OT device cần hoạt động liên tục

**Bối cảnh:** Một PLC bị nghi chạy firmware không đúng, nhưng ngắt mạng điều khiển lập tức có thể làm dừng dây chuyền và tăng rủi ro an toàn.

**Câu hỏi:** Có nên tự động áp EDR isolation giống laptop?

**Gợi ý:** Không. Cần runbook với safety engineer, owner OT và IR, đánh giá chế độ an toàn và phương án containment từng bước, không bỏ qua security nhưng cũng không tạo nguy hiểm vật lý.

### Tình huống M — Chứng cứ bị xóa trước điều tra

**Bối cảnh:** Máy chủ nghi compromise bị wipe ngay mà chưa lấy logs/memory/disk evidence dù quy trình yêu cầu.

**Câu hỏi:** Vấn đề?

**Gợi ý:** Có thể làm mất chứng cứ và giảm khả năng xác định phạm vi lộ secret. Cần cân bằng containment khẩn cấp với forensic preservation theo IR/legal policy.

### Tình huống N — Scanner báo không có device lạ

**Bối cảnh:** API inventory chỉ trả trang đầu nhưng báo cáo Security ghi “100% device accounted for”.

**Câu hỏi:** Sai ở đâu?

**Gợi ý:** Collection incomplete. Cần pagination, quyền đọc, nguồn và observedAt; không suy “không tồn tại” từ dữ liệu chưa thu đủ.

## 30. Những sai lầm thường gặp

1. **Đồng nhất không check-in với compromise.** Telemetry stale làm trust không xác định, không tự chứng minh bị tấn công.
2. **Chỉ khóa User mà bỏ qua device identity.** Certificate, token, local session hoặc workload key có thể độc lập.
3. **Chỉ gỡ device registration và tuyên bố thu hồi xong.** API vẫn có thể chấp nhận JWT/cookie cũ.
4. **Tin một trạng thái COMPLIANT trong cache hơn lệnh revoke mới có thẩm quyền.** Dẫn tới tái Permit khi thiết bị đã LOST.
5. **Thu hồi certificate nhưng không kiểm gateway.** Relying party có thể bỏ qua revocation hoặc dùng cache lỗi thời.
6. **Dùng lại private key bị nghi lộ khi cấp certificate mới.** Không khắc phục rủi ro nền tảng.
7. **Gửi remote wipe rồi coi dữ liệu đã xóa.** Device offline có thể chưa nhận lệnh.
8. **Dùng hostname/email làm khóa duy nhất.** Gây nhầm asset, User, tenant hoặc thiết bị được bàn giao.
9. **Revoke toàn bộ service accounts của người Leaver.** Có thể làm hỏng production trong khi vẫn chưa xử lý secret mà người ấy biết.
10. **Cho phép re-enroll tự động thiết bị đã compromised.** Attacker có thể khôi phục trust qua recovery yếu.
11. **Dùng posture của laptop cho IoT/OT.** Có thể gây false positive và safety impact.
12. **Xóa máy khi cần forensics mà không cân nhắc chứng cứ.** Khó điều tra phạm vi compromise.
13. **Không xét access path gián tiếp.** Local admin, PAT, SSH key, delegated cloud role và CI token bị bỏ sót.
14. **Không chặn retry của job cũ.** Joiner/Mover task có thể bật lại certificate/trust sau incident hoặc Leaver.
15. **Đóng ticket khi còn PARTIAL_FAILURE.** Số liệu xử lý không phản ánh quyền hiệu lực.
16. **Chỉ kiểm mỗi đăng nhập mới.** Không đo session, token và credential đã phát trước đó.
17. **Xem attestation/TPM là bảo đảm tuyệt đối không compromise.** Runtime bị chiếm vẫn có thể yêu cầu ký và thao tác hợp lệ về mặt mật mã.
18. **Không bảo vệ account recovery và enrollment.** Device bị chặn nhưng có thể tự đăng ký mới qua luồng yếu.

## 31. Câu hỏi tự kiểm tra

**1. “Thiết bị mất kiểm soát” có nhất thiết là thiết bị đã bị hacker chiếm không?**

Không. Nó có thể là thiết bị bị mất, không còn quản lý, posture không đạt, credential bị nghi lộ hoặc không thể chứng minh trust hiện hành. Cần phân loại mức bằng chứng.

**2. Vì sao một device offline không đương nhiên bị coi là compromised?**

Vì hết pin, mất mạng hoặc chu kỳ hoạt động dài có thể làm telemetry stale. Dù vậy chính sách có thể hạn chế quyền cho tới khi trạng thái được xác minh.

**3. Device identity khác human identity ở đâu?**

Human identity đại diện người; device identity đại diện thiết bị/instance được đăng ký. Một người có nhiều device; một device có nhiều User hoặc workload.

**4. Machine identity có phải lúc nào cũng là SCIM User không?**

Không. Workload principal, device certificate, cloud role, SSH identity và IoT credential có các mô hình riêng, không được SCIM User/Group bao phủ mặc định.

**5. MDM báo QUARANTINED có đủ chứng minh mọi cloud API đã chặn device không?**

Không. Cần kiểm enforcement ở IdP/gateway/API và token/session đang tồn tại.

**6. Tại sao revoke certificate ở CA chưa bảo đảm mTLS kết nối mới bị từ chối?**

Vì relying party phải kiểm revocation, freshness, chain và chính sách chấp nhận; một gateway có thể không cập nhật hoặc fail-open.

**7. Nếu private key được giữ trong TPM thì device có thể được xem là an toàn tuyệt đối không?**

Không. Runtime compromised có thể lợi dụng thiết bị và thao tác bằng khóa mà không xuất private key.

**8. Remote wipe đã gửi nhưng device offline: trạng thái đúng là gì?**

Pending hoặc unverified cho tới khi có evidence phù hợp. Không tuyên bố dữ liệu đã xóa.

**9. Thứ gì khiến token OAuth vẫn có thể dùng sau khi device registration bị xóa?**

Resource Server có thể chấp nhận access token tự chứa còn hạn mà không kiểm trạng thái device hiện hành, hoặc app có cookie/PAT độc lập.

**10. Vì sao phải phân biệt key rotation và certificate revocation?**

Revoke certificate cũ không xử lý private key bị lộ nếu tiếp tục dùng lại khóa ấy; cần đánh giá tạo khóa mới và thu hồi mọi đường sử dụng credential.

**11. Trong Joiner, thiết bị được enroll trước startAt có nên dùng ngay quyền nghiệp vụ không?**

Không mặc định. Pre-enrollment được phép chuẩn bị nhưng quyền phải theo ngày hiệu lực và policy.

**12. Trong Mover bàn giao laptop, chỉ đổi owner trong CMDB có đủ không?**

Không. Cần reset/re-enroll và thu hồi token/session/secret cũ để không mang quyền người trước sang người sau.

**13. Trong Leaver, có nên xóa toàn bộ production server do người nghỉ việc từng sở hữu không?**

Không. Thu hồi human privileges, bàn giao service ownership, rotate secrets bị ảnh hưởng và giữ workload hợp lệ theo kế hoạch.

**14. Workload identity federation có loại bỏ rủi ro host bị compromise không?**

Không. Host/workload bị điều khiển có thể xin token mới khi trust còn hợp lệ; cần kiểm identity source, claims, audience và revocation.

**15. Thế nào là device trust và session trust khác nhau?**

Device trust đánh giá thiết bị/credential/enrollment; session trust đánh giá phiên/tokens và các điều kiện truy cập. Revoke một lớp không mặc định ngắt mọi phiên lớp khác.

**16. Vì sao cần kiểm cả desired–observed–effective?**

Desired cho biết policy yêu cầu gì; observed cho biết cấu hình đích đã áp gì; effective cho biết hành động còn thực hiện được không. Ba lớp có thể lệch.

**17. Khi inventory API thiếu trang thì có thể báo không có device trái phép không?**

Không. Thiếu dữ liệu phải ghi incomplete/unknown, không được coi là verified empty.

**18. Một device đã revoke có được re-enroll tự động chỉ vì User còn ACTIVE không?**

Không mặc định. Cần recovery proofing, điều tra incident, enrollment có thẩm quyền, khóa/chứng chỉ mới khi cần và posture đủ tin.

**19. Với thiết bị OT, điều gì quan trọng ngoài confidentiality?**

Safety và availability, cũng như ảnh hưởng vật lý của việc ngắt kết nối/wipe; phải phối hợp owner OT/safety và runbook.

**20. Mức nào đủ để báo sự cố đã xử lý xong?**

Chỉ trong phạm vi các access paths bắt buộc đã được readback và kiểm chứng theo policy. Nếu có credential/session chưa thể xác minh, ghi PARTIAL_FAILURE/UNVERIFIED với owner và deadline.

## Ghi nhớ

- **Thiết bị mất kiểm soát** không chỉ là “máy offline”: có thể **thất lạc, mất quản lý, không đạt posture, bị xâm nhập hoặc lộ key/certificate**. Phải phân biệt nghi ngờ, xác nhận và trạng thái chưa biết.
- **Human identity, device identity, workload/service identity, credentials, sessions và entitlements** là các thực thể khác nhau. Khóa một User, thiết bị hoặc certificate **không tự xử lý mọi đường truy cập khác**.
- **Inventory có namespace/owner, chứng thực enrollment, key protection, attestation, MDM/UEM, EDR, PKI/mTLS, IdP/SSO, RBAC/ABAC/PBAC, PAM và PEP** cần phối hợp để kiểm soát machine identity.
- Phản ứng gồm **triage → containment → revoke/rotate → điều tra/bảo toàn chứng cứ → recovery/re-enrollment → readback và xác minh effective access**; không coi lệnh wipe, certificate revoke hoặc API 200/204 là đủ bằng chứng đã chặn mọi truy cập.
- **Joiner** phải enroll đúng device và ngày hiệu lực; **Mover** phải gỡ trust/session cũ trước bàn giao; **Leaver** phải thu hồi human access, device trust và credentials liên quan nhưng không xóa mù workload hợp lệ. Các job cũ không được tái cấp quyền sau revoke.
- Với **IoT/OT**, áp freshness/containment theo môi trường, có owner safety/availability; với **workload**, kiểm host-to-service-to-credential graph và trust federation thay vì chỉ nhìn một account.
- **Desired–observed–effective access, kiểm thử negative, kiểm tra phiên/token còn hạn, sourceVersion, audit, recovery proofing và đối soát quyền tồn dư** là điều kiện để khôi phục niềm tin vào machine identity trong toàn bộ vòng đời danh tính IAM.
