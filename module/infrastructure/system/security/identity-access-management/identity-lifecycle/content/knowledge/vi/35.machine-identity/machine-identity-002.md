# Device registration trong Machine Identity: đăng ký, xác minh và quản lý vòng đời danh tính thiết bị

## 1. Device registration là gì?

**Device registration** (đăng ký thiết bị) là quá trình đưa một thiết bị vật lý hoặc thiết bị được quản lý vào **hệ thống nhận diện và kiểm soát tin cậy của tổ chức**, tạo một **bản ghi danh tính thiết bị** và liên kết nó với các bằng chứng, người hoặc hệ thống sở hữu, trạng thái vòng đời, chính sách truy cập cùng những thông tin cần thiết để quản trị.

Trong **Machine Identity**, thiết bị là một chủ thể kỹ thuật có thể được nhận diện độc lập với người đăng nhập: laptop doanh nghiệp, điện thoại được phép dùng cho công việc, máy chủ, thiết bị IoT, kiosk, máy quét kho, gateway, thiết bị mạng hoặc thiết bị vận hành công nghiệp. Một thiết bị có thể sử dụng **khóa bất đối xứng, chứng chỉ, managed device identity hoặc credential do nền tảng phát hành** để chứng minh nó đang nắm giữ danh tính đã đăng ký.

Đăng ký thành công **không tự chứng minh thiết bị an toàn, tuân thủ chính sách hoặc được phép truy cập mọi tài nguyên**. Đó là nền tảng để tổ chức đưa ra các quyết định tiếp theo: thiết bị có thật không, có đúng tổ chức không, đã được xác minh tới mức nào, ai chịu trách nhiệm, có bị mất hoặc thu hồi không, và chính sách **RBAC/ABAC/PBAC** có cho phép hành động hiện tại không.

Ví dụ, một laptop mới được giao cho nhân viên Lan có thể được gắn:

~~~text
Device ID:          dev-org-a-000482
Device type:        MANAGED_LAPTOP
Organization:       org-a
Custodian:          iam-lan-482
Asset reference:    asset-serial-lookup-482
Trust state:        REGISTERED_VERIFIED
Management state:   ENROLLED
Posture:            COMPLIANT_AT_2026-11-23T09:00+07:00
Key credential:     key-ref-tpm-482
Access scope:       đánh giá riêng theo user, device, resource, policy
~~~

Những giá trị trên là **dữ liệu minh họa**, không phải schema bắt buộc của IdP hay MDM. Bản ghi thiết bị có thể được tạo trước khi giao cho người dùng, và mối quan hệ với người sử dụng có thể thay đổi mà **deviceId vẫn được giữ ổn định** theo chính sách quản lý tài sản.

### Mục tiêu học tập

Sau bài này, người học có thể: phân biệt đăng ký thiết bị với các nghiệp vụ lân cận; thiết kế quy trình xác minh nguồn gốc và chứng minh sở hữu khóa; liên kết device–asset–owner–user–tenant; quản lý khóa/chứng chỉ và posture; đưa trạng thái thiết bị vào chính sách truy cập; xử lý **Joiner–Mover–Leaver (JML)** và thiết bị mất/thu hồi; đối soát, kiểm toán và kiểm thử các đường truy cập tồn dư.

## 2. Tại sao Device registration thuộc IAM Identity Lifecycle?

Mô hình IAM theo **Joiner–Mover–Leaver** thường bắt đầu từ con người, nhưng quyền truy cập hiện đại có thể phụ thuộc cả **danh tính người dùng** và **danh tính thiết bị**. Hai thực thể có vòng đời khác nhau:

| Thành phần | Ví dụ | Ai quản lý? | Sự kiện vòng đời |
| --- | --- | --- | --- |
| **Person/worker** | Lan | HRIS/nguồn bảo trợ | Joiner, Mover, Leaver |
| **IAM user identity** | iam-lan-482 | IAM/IdP | Tạo, kích hoạt, khóa, xóa theo policy |
| **Device identity** | dev-org-a-000482 | Device registry/IdP/MDM/PKI | Đăng ký, xác minh, quản lý, suspend, retire |
| **Asset** | laptop tài sản A-482 | IT asset/CMDB | Mua, nhập kho, bàn giao, sửa chữa, thanh lý |
| **Credential** | Device key/certificate K-482 | TPM/keystore/CA/PKI | Sinh, kích hoạt, rotate, revoke, expire |
| **Device–user binding** | Lan đang giữ laptop A-482 | IT/MDM/asset assignment | Giao, đổi người sử dụng, thu hồi |
| **Access entitlement** | Quyền xem báo cáo Atlas | IAM/IGA/app owner | Cấp, rà soát, thu hồi |

Khi Lan **Mover** sang dự án mới, thiết bị có thể giữ nguyên nhưng quyền dữ liệu phải tính lại theo vai trò. Khi Lan **Leaver**, laptop phải được thu hồi/chuyển giao và user session bị vô hiệu theo chính sách, nhưng không nhất thiết cần xóa vĩnh viễn device identity trước khi IT thực hiện **wipe, reset và re-enrollment** cho người mới.

Thiết kế tốt tránh dùng một trường duy nhất như **employeeStatus** để thay thế trạng thái của toàn bộ thiết bị: thiết bị có thể còn là tài sản hợp lệ sau khi người dùng cũ rời công ty.

## 3. Phân biệt registration, enrollment, provisioning, join và authentication

Đây là nhóm thuật ngữ dễ bị dùng lẫn nhau nhất.

| Khái niệm | Câu hỏi chính | Kết quả điển hình |
| --- | --- | --- |
| **Device discovery/inventory** | Tổ chức quan sát thấy thiết bị nào? | Một bản ghi tài sản hoặc thiết bị chưa xác minh |
| **Device registration** | Thiết bị nào được tổ chức nhận diện, thuộc phạm vi nào và đã có bằng chứng gì? | Device identity record, registration state |
| **MDM/UEM enrollment** | Thiết bị đã tham gia quản lý cấu hình và bảo mật từ xa chưa? | Management agent/profile, khả năng áp policy |
| **Directory join/association** | Thiết bị đã liên kết với directory hoặc miền quản trị chưa? | Trust relationship theo sản phẩm |
| **Credential provisioning** | Thiết bị nhận khóa/chứng chỉ/credential nào? | Device credential có vòng đời và binding |
| **Device authentication** | Bên đang kết nối có chứng minh được sở hữu credential hợp lệ không? | Kết quả challenge-response/mTLS hoặc verifier decision |
| **Device attestation** | Có bằng chứng về khóa/hardware/boot state từ nguồn đáng tin không? | Attestation evidence và kết quả kiểm chứng |
| **Device compliance/posture** | Thiết bị hiện có đáp ứng baseline không? | COMPLIANT, NONCOMPLIANT hoặc UNKNOWN tại một thời điểm |
| **Device authorization** | Thiết bị này, cùng user và ngữ cảnh, được phép làm gì? | Permit/Deny ở API, VPN, ZTNA hoặc tài nguyên |

Một thiết bị có thể **REGISTERED** nhưng **chưa ENROLLED**; đã enrollment nhưng **NONCOMPLIANT**; có chứng chỉ hợp lệ nhưng **người dùng đã Leaver**; hoặc được quản lý hợp lệ nhưng **không có quyền đọc dữ liệu của tenant khác**.

**Không coi các trạng thái này là tương đương.** Sản phẩm cụ thể có thể tự kết hợp nhiều bước vào một workflow, nhưng khi thiết kế IAM cần giữ rõ ý nghĩa và bằng chứng của từng bước.

## 4. Device registration không phải OAuth Device Authorization Grant

Trong OAuth 2.0 có **Device Authorization Grant** (thường liên quan các thiết bị nhập liệu hạn chế như TV hoặc console). Nó là **luồng ủy quyền OAuth** cho client để người dùng sử dụng một thiết bị khác có trình duyệt nhập mã và đồng ý, chứ không tự động là **đăng ký danh tính phần cứng vào tổ chức**.

| Chủ đề | Device registration trong IAM | OAuth 2.0 Device Authorization Grant |
| --- | --- | --- |
| Mục tiêu | Quản lý danh tính, ownership, trust và vòng đời thiết bị | Nhận authorization/token cho OAuth client trên thiết bị hạn chế nhập liệu |
| Đối tượng chính | Device record/credential/hardware/owner | OAuth client, user authorization và token |
| Bằng chứng | Asset provenance, khóa, attestation, MDM/directory binding | User authorization flow và token grant |
| Kết quả | DeviceId, trust/compliance/lifecycle state | Access token/refresh token tùy grant và policy |
| Có tự chứng minh thiết bị thuộc doanh nghiệp? | Không nếu chưa xác minh nguồn/thẩm quyền | **Không** |
| Có tự cấp quyền nghiệp vụ? | **Không** | **Không**, token còn chịu resource authorization |

Tương tự, **OAuth Dynamic Client Registration** là đăng ký OAuth client với authorization server, **không phải một chuẩn chung để khai báo phần cứng đã được tổ chức quản lý**.

Khi thiết kế, nên đặt tên API/record rõ như **deviceRegistry.register**, **oauthDeviceAuthorization** hoặc **clientRegistration**, tránh nhầm một mã user_code với device identity ổn định.

## 5. Những loại thiết bị cần được đăng ký

| Loại | Ví dụ | Đặc điểm quản trị |
| --- | --- | --- |
| **Corporate laptop/desktop** | Máy nhân viên, máy on-call | Asset tracking, MDM/endpoint posture, user binding |
| **Mobile device** | Điện thoại công ty hoặc BYOD | Ownership, work profile, quyền riêng tư |
| **Shared/kiosk device** | Máy quét kho, kiosk lễ tân | Nhiều người dùng, user session phải tách riêng |
| **Server/bare metal** | Máy chủ nội bộ | Hardware/host identity, CMDB, PKI, service owner |
| **Virtual machine** | VM trong cloud/private cloud | Ephemeral lifecycle, cloud instance metadata, workload identity |
| **IoT/OT device** | Sensor, gateway, PLC | Hạn chế tài nguyên, bootstrap và offline, firmware |
| **Network appliance** | Router, switch, firewall | Device certificates, management-plane access |
| **Specialized appliance** | Backup vault, HSM client, recovery terminal | Độ nhạy cao, chủ quản và quy trình khẩn cấp |

**Không phải thiết bị nào cũng có TPM, MDM agent hoặc cùng một phương thức attestation**. Với thiết bị đời cũ/IoT, cần mô hình trust thấp hơn và **biện pháp bù trừ** như network segmentation, gateway enrollment, credential ngắn hạn hay giám sát traffic.

Một container hoặc function thường là **workload instance**, không phải thiết bị vật lý; có thể cần workload identity thay cho một device record mang ý nghĩa tài sản. Tránh ép mọi workload vào khái niệm “laptop được đăng ký”.

## 6. Xác định ranh giới tin cậy và mục tiêu bảo mật

Đăng ký thiết bị phải đáp ứng những câu hỏi:

1. **Provenance:** thiết bị đến từ nguồn nào, có nằm trong danh sách được phép không?
2. **Uniqueness:** có ID ổn định trong namespace phù hợp, tránh trùng record?
3. **Proof of possession:** bên đăng ký có nắm private key tương ứng public key không?
4. **Hardware/boot assurance:** có attestation đáng tin hay chỉ lời khai của agent?
5. **Ownership/custody:** tổ chức hay người dùng sở hữu; hiện ai chịu trách nhiệm?
6. **Tenant binding:** device thuộc tổ chức/không gian nào, có chuyển tenant được không?
7. **Credential lifecycle:** khóa/chứng chỉ có hạn, rotate, revoke và chống sao chép thế nào?
8. **Management/posture:** chính sách quản lý và trạng thái bảo mật có đủ mới không?
9. **Authorization:** device state được dùng cùng user/resource/action ở đâu?
10. **Exit control:** khi mất thiết bị, Leaver hoặc decommission, có thể chặn đúng đường truy cập không?

**Một deviceId chỉ do client tự gửi không có giá trị chứng minh trust**. Device record phải được liên kết với bằng chứng do verifier/management system có thẩm quyền thu thập, và các quyền phát sinh cần được kiểm tra tại backend/PEP.

## 7. Những hệ thống tham gia quy trình đăng ký

| Hệ thống | Vai trò | Cần tránh suy diễn |
| --- | --- | --- |
| **Asset inventory/CMDB** | Serial, model, owner, lifecycle tài sản | Asset có record không tự chứng minh device đang kết nối đúng là asset đó |
| **HRIS/sponsor directory** | Người, hợp đồng, bộ phận và ngày hiệu lực | Người ACTIVE không chứng minh thiết bị compliant |
| **IAM/IGA** | Role/policy, approval và quản lý vòng đời quyền | Quyền được duyệt không chứng minh device đã enroll |
| **IdP/device directory** | User/device identity, trust association, login policy | Directory registration không đồng nghĩa endpoint health |
| **MDM/UEM/EDR** | Enrollment, inventory endpoint, compliance và posture | Agent báo compliant vẫn cần dữ liệu đủ mới và nguồn tin cậy |
| **PKI/CA/KMS/HSM** | Credential, certificate issuance, protection, revocation | Chứng chỉ hợp lệ không tự cấp quyền vào mọi API |
| **Attestation verifier** | Kiểm tra evidence từ TPM/TEE/secure boot khi hỗ trợ | Attestation chỉ có nghĩa trong phạm vi claims đo được |
| **PDP/PEP/ZTNA/VPN** | Ra quyết định và thực thi truy cập theo ngữ cảnh | Permit cache có thể cũ khi device bị revoke |
| **SCIM/target SaaS** | Provision User/Group khi ứng dụng hỗ trợ | SCIM core không phải device registration API chuẩn |
| **SIEM/audit** | Theo dõi registration, credential, posture, access | Log thành công không chứng minh target đã Deny sau revoke |

**Authority theo từng thuộc tính** cần được xác định trước: CMDB có thể quyết định asset ownership, HRIS quyết định employment, MDM quyết định enrollment/compliance, CA quyết định certificate status, còn IAM quyết định policy và identity linking.

## 8. Mô hình dữ liệu tối thiểu của device identity

Một device record nên phân biệt **device ID, asset ID, key ID, account và user assignment**:

| Trường | Ví dụ | Ghi chú |
| --- | --- | --- |
| **deviceId** | dev-org-a-000482 | ID nội bộ ổn định, có tenant namespace |
| **organizationId** | org-a | Tenant quản trị hiện hành |
| **deviceClass** | CORPORATE_LAPTOP | Loại để áp policy |
| **assetRef** | asset-482 | Liên kết tài sản, có thể không có với BYOD |
| **ownershipType** | CORPORATE, BYOD, SHARED | Chính sách quyền riêng tư và quản trị |
| **custodianIdentityRef** | iam-lan-482 | Người giữ thiết bị, không nhất thiết owner pháp lý |
| **serviceOwnerRef** | platform-team-a | Dành cho server/IoT/shared device |
| **registrationState** | VERIFIED | Kết quả xác minh đăng ký |
| **managementState** | ENROLLED | Trạng thái quản lý, độc lập trust |
| **postureState** | COMPLIANT | Phải có assessedAt và nguồn |
| **credentialRefs** | device-cert-482 | Không lưu private key |
| **attestationEvidenceRef** | attestation-924 | Bằng chứng được bảo vệ, có hạn |
| **registeredAt/lastSeenAt** | Instant có offset | Phân biệt lịch sử và quan sát gần đây |
| **sourceVersion** | registry-v13 | Chống event cũ ghi đè |
| **retiredAt/revokedAt** | Timestamp hoặc null | Có nghĩa theo event/state |

Một số thuộc tính như serial, MAC address, IMEI và hostname có thể đổi, bị giả mạo, thiếu hoặc trùng. Chúng hữu ích cho kiểm kê nhưng **không nên dùng riêng lẻ làm chứng cứ cryptographic của một thiết bị cụ thể**.

## 9. Mô hình thực thể: asset, device, user, workload và credential

~~~mermaid
flowchart TD
    P["Person / employment relation"] -->|"Custody/assignment có hạn"| D["Device identity: deviceId"]
    A["CMDB asset record"] -->|"Asset association"| D
    O["Organization / tenant"] -->|"Registration authority"| D
    S["Service owner / workload"] -->|"Managed host / machine purpose"| D
    D --> K["Key references / device certificates"]
    D --> M["MDM enrollment & posture evidence"]
    D --> E["Attestation evidence & trust state"]
    P --> U["Human IAM identity / IdP account"]
    U --> Z["Session / OAuth token"]
    K --> G["Device authentication result"]
    E --> R["PDP authorization decision"]
    M --> R
    G --> R
    U --> R
    R --> X["PEP / API / VPN / ZTNA"]
~~~

Quan hệ **user–device** là quan hệ **có thời gian**: cùng thiết bị có thể được bàn giao, tái cấp phát hoặc dùng chung. Một user cũng có nhiều thiết bị. Với thiết bị kiosk, một deviceId vẫn duy trì nhưng mỗi phiên đăng nhập phải gắn **userIdentityId riêng**, không quy mọi hoạt động cho “kiosk-user” mà bỏ actor thật.

**Credential cũng có vòng đời riêng**: một thiết bị có thể có nhiều chứng chỉ cùng lúc khi rotate; một key bị revoke không đồng nghĩa asset bị thanh lý; một user Leaver không đồng nghĩa mọi device do họ từng sử dụng đều phải bị xóa record.

## 10. Chọn trust state và trạng thái vòng đời rõ ràng

Có thể tách các lớp trạng thái:

| Lớp | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Registration** | DISCOVERED, PENDING_PROOF, VERIFIED, REJECTED | Đã xác minh được danh tính thiết bị chưa |
| **Management** | NOT_ENROLLED, ENROLLED, UNMANAGED, LOST | Có được quản lý thiết bị không |
| **Posture** | COMPLIANT, NONCOMPLIANT, UNKNOWN, STALE | Mức tuân thủ tại thời điểm đánh giá |
| **Credential** | ACTIVE, EXPIRING, REVOKED, EXPIRED | Khóa/chứng chỉ còn được verifier chấp nhận không |
| **Lifecycle** | IN_STOCK, ASSIGNED, REPAIR, SUSPENDED, RETIRED | Trạng thái tài sản/thiết bị theo nghiệp vụ |
| **Access** | ALLOW, DENY, NOT_APPLICABLE, INDETERMINATE | Quyết định theo ngữ cảnh của request |

Không nên gom thành cờ **trusted=true** vĩnh viễn. **Device VERIFIED từ một năm trước** có thể đã mất, bị root/jailbreak hoặc đổi người sử dụng; **COMPLIANT một giờ trước** có thể không còn đủ mới với API rất nhạy cảm.

Khi chưa có dữ liệu posture, ghi **UNKNOWN/STALE**; không tự coi là COMPLIANT. Với tài nguyên rủi ro cao, policy có thể **Deny hoặc yêu cầu xác minh lại**. Với chức năng đăng ký/phục hồi hạn chế, có thể cho một luồng **remediation-only access** đã phê duyệt riêng.

## 11. Luồng Device registration đầu cuối

~~~mermaid
flowchart TD
    A["Asset được ghi nhận / Chủ thể yêu cầu đăng ký"] --> B["Kiểm tra source authority, tenant, owner"]
    B --> C{"Đủ eligibility để bắt đầu?"}
    C -->|"Không"| X["Reject / review identity & asset"]
    C -->|"Có"| D["Khởi tạo registration challenge và policy"]
    D --> E["Sinh hoặc chọn key pair được bảo vệ"]
    E --> F["Proof of possession + attestation nếu yêu cầu"]
    F --> G{"Verifier kiểm tra evidence?"}
    G -->|"Không/UNKNOWN"| Y["PENDING_PROOF / hạn chế quyền"]
    G -->|"Có"| H["Gắn deviceId, keyRef, tenant, owner"]
    H --> I["Cấp credential/CA theo profile phù hợp"]
    I --> J["MDM/UEM enrollment & posture (nếu policy yêu cầu)"]
    J --> K["Kiểm tra trust, expiry, duplicates, risk"]
    K --> L{"Điều kiện activation đạt?"}
    L -->|"Không"| Y
    L -->|"Có"| M["Mark REGISTERED_VERIFIED / publish lifecycle event"]
    M --> N["PDP/PEP đánh giá device + user + resource"]
    N --> O["Audit, readback, periodic reconciliation"]
~~~

Đây là **quy trình tham chiếu**, không phải một sequence duy nhất cho mọi sản phẩm. Có nền tảng **MDM enrollment trước rồi nhận device identity**, nền tảng khác **đăng ký với IdP trước rồi enroll**, và thiết bị IoT có thể bootstrap bằng **factory credential**. Cần thiết kế sao cho mọi đường đều đi qua các kiểm tra trust và có bằng chứng.

## 12. Giai đoạn bootstrap: tin ai trước khi có danh tính thiết bị?

Vấn đề gốc của đăng ký là **chicken-and-egg**: thiết bị chưa có identity tổ chức thì làm sao chứng minh được nó thuộc về tổ chức?

Các lựa chọn bootstrap, tùy nền tảng:

| Nguồn trust ban đầu | Ví dụ | Cần kiểm tra |
| --- | --- | --- |
| **Procurement/asset record** | Mua qua kênh được ủy quyền, serial trong CMDB | Record không bị sửa/giả, kết nối đúng thiết bị |
| **Factory-provisioned identity** | Key/chứng chỉ từ nhà sản xuất | Chain of trust, manufacturer/serial binding, revocation |
| **One-time enrollment token** | Mã chỉ dùng một lần từ IT | Hạn, audience, binding với asset/user, chống replay |
| **Out-of-band verification** | IT xác minh trực tiếp thiết bị | Người xác minh, bằng chứng, phạm vi và log |
| **MDM automated enrollment** | Phân phối profile bởi nền tảng có trust riêng | Tài sản có quyền enroll, tránh thiết bị ngoài luồng |
| **Hardware attestation** | TPM/TEE chứng minh key/hardware state | Nonce, signature, trust anchor, claims và thời hạn |
| **Cloud instance identity** | Metadata/chứng thực instance do cloud cung cấp | Issuer, account/project, instance lifecycle và workload owner |

Không coi **serial number hoặc MAC address** là credential đủ mạnh; chúng dễ quan sát hoặc giả mạo. Nếu dùng one-time token, phải lưu **trạng thái đã sử dụng** và ràng buộc đúng tenant/role để một token rò rỉ không enroll hàng loạt máy lạ.

Đăng ký **không nên yêu cầu private key bị xuất ra để gửi lên server**. Mô hình an toàn thông thường là sinh khóa tại thiết bị hoặc phần cứng bảo vệ, chỉ gửi public key/CSR và **chứng minh sở hữu private key**.

## 13. Proof of Possession (PoP): thiết bị chứng minh đang giữ khóa

**Proof of Possession** là bước kiểm tra bên đăng ký có thể thực hiện thao tác mật mã với **private key tương ứng public key đã công bố**, thay vì chỉ copy một public key từ thiết bị khác.

Luồng minh họa:

~~~text
1. Registration server -> device:
       nonce = random challenge
       audience = registry.example.invalid
       expiresAt = short-lived instant

2. Device:
       signature = Sign(privateDeviceKey, canonical(nonce + audience + deviceContext))

3. Device -> server:
       publicKeyRef, signature, nonceRef, deviceContext

4. Server:
       verify signature, nonce not reused, audience correct,
       challenge not expired, asset/tenant/policy constraints,
       then bind key reference to device identity
~~~

Đây là **mã giả giao thức**, không phải wire protocol chuẩn; khi triển khai nên ưu tiên giao thức/thư viện đã được kiểm chứng thay vì tự sáng chế định dạng challenge.

PoP chứng minh **quyền điều khiển khóa tại thời điểm kiểm tra**, **không tự chứng minh khóa nằm trong TPM, hệ điều hành sạch hoặc thiết bị chính hãng**. Nếu private key đã bị sao chép, attacker cũng có thể ký challenge. Muốn biết đặc tính khóa/hardware cần evidence và verifier phù hợp.

## 14. TPM, Secure Enclave, keystore và non-exportable key

Khóa thiết bị có thể được bảo vệ bởi:

- **Trusted Platform Module (TPM)** trên một số máy tính.
- **Secure Enclave/TEE hoặc hardware-backed keystore** trên một số thiết bị.
- **HSM** hoặc hardware key riêng trên máy chủ/appliance.
- **OS keystore/software keystore** khi không có hardware protection.
- **Factory secure element** trên IoT phù hợp.

| Thuộc tính bảo vệ | Lợi ích | Không được suy diễn |
| --- | --- | --- |
| **Non-exportable private key** | Hạn chế lộ khóa từ giao diện chuẩn | Không bảo đảm máy không bị điều khiển để ký |
| **Hardware-backed key** | Giảm rủi ro sao chép so với key ở file | Chưa chứng minh ứng dụng gọi API là đáng tin |
| **Secure boot / measured boot** | Có thể cung cấp bằng chứng trạng thái khởi động | Không phản ánh mọi lỗ hổng runtime |
| **Device attestation** | Kết nối trust với hardware/measurement claims | Chỉ đúng trong phạm vi evidence và trust policy |
| **Key rotation** | Giảm phụ thuộc lâu dài vào một credential | Không tự thu hồi mọi session phát hành trước |

Không phải mọi hệ điều hành/hardware cho phép kiểm chứng cùng một bộ claims. **Khai báo “TPM present” từ client không đủ**; verifier cần kiểm tra signature, chain/certificate khi phù hợp, nonce, policy về phần cứng và định dạng evidence.

## 15. Device attestation: xác minh đến mức nào?

**Attestation** là bằng chứng ký hoặc được bảo vệ bằng cơ chế tin cậy để nói về **khóa, môi trường, thiết bị hoặc trạng thái thực thi**. Đối với device registration, mục tiêu có thể là xác minh **khóa đăng ký được tạo/bảo vệ ở phần cứng được tin cậy** hoặc đo trạng thái boot.

Một verifier cần xét:

1. **Trust anchor/attestation key** đến từ đâu, có chấp nhận được không?
2. **Nonce/freshness** ngăn dùng lại bằng chứng cũ.
3. **Subject/key binding**: evidence có gắn đúng key đang đăng ký không?
4. **Measurement claims** có ý nghĩa gì: hardware model, OS state, boot measurement?
5. **Policy version**: tổ chức yêu cầu mức assurance nào cho từng tài nguyên?
6. **Revocation/trust list**: issuer hoặc thiết bị có bị thu hồi không?
7. **Privacy**: evidence có tiết lộ serial/unique hardware identifier vượt nhu cầu không?
8. **Failure handling**: UNKNOWN khác FAIL và khác VERIFIED.

**Attestation không có nghĩa thiết bị miễn nhiễm malware, không thể bị chiếm quyền, hoặc mọi ứng dụng đều đáng tin**. Đó là một đầu vào cho quyết định trust và posture, cần đánh giá lại khi context thay đổi.

## 16. Chứng chỉ thiết bị và vòng đời PKI

Một kiến trúc có thể phát hành **X.509 certificate** cho device key. Chứng chỉ liên kết public key với subject hoặc định danh thiết bị theo **certificate profile** đã được kiểm soát.

Vòng đời thường có:

~~~text
Bootstrap trust -> CSR / PoP -> Approval / enrollment policy
    -> Certificate issuance -> Install/bind key
    -> mTLS/device authentication -> Renewal/rotation
    -> Suspension/revocation/expiry -> Readback and retirement
~~~

Một số giao thức/trường hợp:

| Cơ chế | Vai trò | Lưu ý |
| --- | --- | --- |
| **EST** | Enrollment over Secure Transport cho chứng chỉ trong hạ tầng phù hợp | Cần xác thực bootstrap và policy CA |
| **SCEP** | Giao thức cấp chứng chỉ trong một số hệ sinh thái/legacy | Cần kiểm tra profile/giới hạn an toàn của triển khai |
| **ACME** | Tự động quản lý chứng chỉ cho những trường hợp phù hợp | Không tự biến mọi ACME flow thành device attestation |
| **mTLS** | Hai phía TLS xác thực certificate được chấp nhận | Xác thực thiết bị không tự quyết định role trên từng API |
| **CRL/OCSP hoặc status service** | Xác minh chứng chỉ bị revoke theo kiến trúc | Cache, downtime và freshness phải có policy |

**X.509 không quy định một chuẩn IAM duy nhất về asset ownership, MDM compliance hoặc người sử dụng**. Chứng chỉ xác thực một khóa/subject theo trust chain; authorization vẫn phải áp dụng tenant, resource và context.

## 17. Thiết kế Certificate Subject, SAN và namespace

Định danh trong chứng chỉ phải rõ **issuer, tenant, deviceRef và phạm vi sử dụng**. Không dùng common name/hostname mơ hồ để quyết định tenant.

Ví dụ một mô hình nội bộ:

~~~text
Certificate issuer:  Org-A Device CA
Subject/SAN profile: organization-specific device identifier
Device registry ID:  dev-org-a-000482
Credential record:   device-credential-482-v2
Key usage/EKU:       phù hợp mục đích xác thực đã duyệt
NotBefore/NotAfter:  thời hạn ngắn theo risk policy
Revocation linkage:  CA and device registry
~~~

Server mTLS nên kiểm tra **trust chain, validity, intended key usage/EKU khi áp dụng, revocation theo chính sách và mapping subject → verified deviceId/tenant**. Chỉ kiểm tra chứng chỉ do “một CA nội bộ nào đó” ký có thể khiến chứng chỉ từ tenant khác được chấp nhận sai.

**Hostname, deviceId, SAN URI, thumbprint** có quy tắc riêng; mọi map phải được thiết kế phù hợp sản phẩm và chuẩn certificate profile, không suy rằng mọi chứng chỉ có cùng trường.

## 18. MDM/UEM enrollment: đăng ký không tự đạt compliance

**Mobile Device Management (MDM)** hoặc **Unified Endpoint Management (UEM)** có thể quản lý baseline như:

- Encryption at rest và screen lock.
- OS/security patch level theo chính sách.
- Endpoint protection/EDR state.
- Firewall, boot integrity hoặc device configuration.
- Work profile/managed applications.
- Tình trạng compromised/rooted/jailbroken khi nền tảng hỗ trợ đánh giá.
- Cấu hình device certificate, VPN/ZTNA, Wi-Fi và remote wipe.

**Enrollment là trạng thái quản lý**, còn **compliance là kết quả đánh giá tại một thời điểm**. Một thiết bị mới enroll nhưng chưa nhận đủ policy có thể là **PENDING_COMPLIANCE**, không được tự cấp quyền nhạy cảm.

Device policy cần có **posture assessedAt, source/version, freshness threshold và error state**. Một đánh giá COMPLIANT của tuần trước có thể không đủ cho một thao tác production nhạy cảm hôm nay.

## 19. Ownership: Corporate, BYOD, Shared và Server

Quyền quản lý và thu thập thông tin thay đổi theo loại ownership:

| Ownership | Bằng chứng cần có | Ràng buộc đặc biệt |
| --- | --- | --- |
| **Corporate-owned** | Asset record, purchase/provisioning, assignment | Thu hồi tài sản, reset/wipe trước reissue |
| **BYOD** | Consent/acceptance phù hợp, work profile, device assurance | Tối thiểu dữ liệu cá nhân; không tự kiểm soát toàn bộ đời sống thiết bị |
| **Shared/kiosk** | Owner location/team, shared device policy | Tách user session; thiết bị không chứng minh ai đã thao tác |
| **Server/infra** | Host asset/instance identity, platform owner | Service identity và machine credential lifecycle |
| **IoT/OT** | Manufacturer/plant/asset/firmware identity | Offline, firmware lifecycle, network segmentation |

**BYOD registration không tự cho phép doanh nghiệp wipe toàn bộ thiết bị cá nhân**. Phải tuân thủ chính sách đã thông báo, sự đồng ý/căn cứ hợp lệ và khả năng của nền tảng; khi offboarding có thể ưu tiên **selective wipe/work profile removal** nếu phù hợp.

Một **shared device** có thể đăng ký bằng device certificate cho kênh mạng, nhưng API nghiệp vụ vẫn cần nhận dạng user/operator để kiểm soát hành động nhạy cảm.

## 20. Zero Trust và Conditional Access: thiết bị là một tín hiệu, không phải vé thông hành

Trong mô hình **Zero Trust**, việc thiết bị được đăng ký giúp tăng dữ liệu quyết định truy cập, nhưng không tạo “trusted network forever”.

Ví dụ một quyết định:

~~~text
ALLOW READ(report) IF:
    user.identityVerified
    AND user.employmentActiveFor(report.organizationId)
    AND user.hasEntitlement("REPORT_READ", report.projectId)
    AND session.authenticationMeetsRequiredAssurance
    AND device.registrationState == VERIFIED
    AND device.managementState == ENROLLED
    AND device.postureState == COMPLIANT
    AND device.postureAssessedAt is sufficiently fresh
    AND device.notSuspendedOrRevoked
    AND report.organizationId == request.tenantId
    AND noHigherPriorityDeny
~~~

**Đây là mã giả policy**, không phải ngôn ngữ triển khai bắt buộc. Có tài nguyên cho phép truy cập từ thiết bị unmanaged trong phạm vi hạn chế; có tài nguyên yêu cầu hardware-backed key và attestation; các ngưỡng phải được xác định từ **risk policy**.

**MFA xác minh người không thay xác minh thiết bị**, và **device mTLS không thay authorization của người**. Nếu chỉ biết một laptop compliant mà không biết người đang dùng là ai, API không nên cho phép đọc dữ liệu theo role của người được bàn giao trước.

## 21. Device authentication và authorization theo từng lớp

Một luồng truy cập có thể gồm:

1. **User authentication:** IdP/SSO/OIDC xác minh người và session/MFA.
2. **Device authentication:** verifier kiểm tra key/certificate hoặc trust assertion của device.
3. **Device posture/attestation:** MDM/verifier cung cấp trạng thái có thời hạn.
4. **Token issuance/conditional access:** policy có thể giới hạn token hoặc yêu cầu step-up.
5. **Resource authorization:** API kiểm tra user, device, role, tenant, action và resource.
6. **Continuous/periodic re-evaluation:** xử lý revoke, session expiry, posture stale.

Các hệ thống có thể đặt PEP ở gateway, reverse proxy, ZTNA, VPN hoặc từng API; **một bước Permit ở gateway không tự chứng minh mọi object-level action được cho phép**. Backend cần áp dụng authorization riêng theo ngữ cảnh nghiệp vụ.

Đối với một số hệ thống, token có thể được **sender-constrained** bằng mTLS hoặc DPoP để hạn chế việc dùng token bị đánh cắp; nhưng khả năng sử dụng và mức bảo vệ phụ thuộc giao thức, client và resource server. **DPoP hoặc mTLS token binding không tự thay cho MDM enrollment hay device attestation**.

## 22. SCIM và Device registration: giới hạn cần nhớ

**SCIM 2.0** (System for Cross-domain Identity Management) thường chuẩn hóa hoạt động provisioning **User** và **Group** qua Service Provider. Nó **không mặc nhiên cung cấp chuẩn Device resource** dùng cho mọi MDM hay device directory.

Một tổ chức có thể:

- Dùng SCIM để cấp user/group cho SaaS sau khi người dùng đủ điều kiện.
- Dùng API riêng của IdP/MDM/device platform để đăng ký hoặc vô hiệu device.
- Dùng IAM/IGA để quản lý quan hệ user–device/owner và approval.
- Dùng certificate enrollment hoặc cloud provider identity service cho device credential.
- Dùng PDP/PEP kiểm tra device trust và user entitlement trên request.

**SCIM User active=false không tự revoke device certificate, PAT, VPN session hay local device identity.** Ngược lại, xóa device khỏi MDM không tự vô hiệu mọi tài khoản và grant mà người đó đã được cấp.

Nếu một sản phẩm có extension hỗ trợ device objects, đó là **contract cụ thể của sản phẩm**, cần đọc schema/mapping của hệ thống đó thay vì giả định tất cả SCIM servers đều xử lý cùng một device lifecycle.

## 23. Joiner: đăng ký thiết bị khi nhân viên hoặc đối tác bắt đầu

Với **Joiner**, người mới thường được cấp laptop hoặc thiết bị di động trước hoặc trong ngày bắt đầu. Quy trình nên tách **chuẩn bị tài sản** khỏi **kích hoạt quyền sử dụng dữ liệu**.

1. **HRIS/sponsor** xác nhận person, employmentRelation, organization, start date và người quản lý.
2. **IT/asset registry** ghi nhận thiết bị, assetId, ownership, đơn vị chịu trách nhiệm và kế hoạch bàn giao.
3. **Device registration service** xác minh thiết bị theo enrollment policy, cấp deviceId và liên kết key/credential.
4. **MDM/UEM** enrollment, áp cấu hình và đánh giá posture; không giả định máy đã sẵn sàng ngay khi có record.
5. **IdP/IAM** liên kết user–device bằng stable IDs và phạm vi tenant đúng.
6. **SSO/MFA** xác minh người dùng khi đăng nhập, không chỉ tin device certificate.
7. **RBAC/ABAC/PBAC** tính access theo nhiệm vụ và trạng thái thiết bị; có thể chặn hành động trước start date.
8. **Readback/positive và negative test** xác minh thiết bị truy cập đúng tài nguyên nhưng không vượt scope.

### Những lỗi dễ xuất hiện ở Joiner

| Dấu hiệu | Nguy cơ | Kiểm tra |
| --- | --- | --- |
| Thiết bị giao nhầm người | Nhầm custody hoặc thông tin phiên cũ | Asset assignment và first login |
| Máy đã enroll nhưng còn account người cũ | Lộ dữ liệu/tokens | Wipe/reset/re-enroll theo policy |
| Người chưa tới ngày bắt đầu đã có access | Truy cập sớm | effectiveFrom và PEP enforcement |
| Máy được cấp certificate nhưng không có MDM | Posture không xác minh | Điều kiện access theo risk |
| Device record trùng ở hai tenant | Cross-tenant mix-up | Namespace/correlation/issuer |
| MDM enrollment thành công nhưng khóa không chứng minh PoP | Identity spoofing | Challenge/evidence tại verifier |

**Không dùng sự kiện “device registered” để tự suy ra user đã được duyệt mọi entitlement**. Joiner có thể đạt cổng thiết bị sẵn sàng nhưng quyền nghiệp vụ vẫn phải đi qua access request/approval riêng.

## 24. Mover: đổi người giữ thiết bị, tổ chức hoặc trách nhiệm

**Mover** có thể là chuyển dự án nhưng giữ laptop, chuyển bộ phận, đổi nơi làm việc hoặc bàn giao thiết bị sang người khác.

| Kịch bản | Device identity | Việc bắt buộc đánh giá |
| --- | --- | --- |
| Nhân viên đổi project, giữ laptop | Có thể giữ nguyên | User entitlement, ABAC project scope, cached sessions |
| Chuyển giữa hai team cùng tenant | Có thể giữ nguyên | Custodian, quản lý chính sách, nhóm cấp quyền |
| Chuyển sang tenant khác | Phụ thuộc chính sách | Có cần unregister/re-enroll và rotate device credential? |
| Bàn giao máy cho người mới | Có thể giữ assetId; có thể cấp mới device identity | Reset/wipe, user binding, session, local keys |
| Đổi laptop mới | DeviceId mới cho thiết bị mới | Revoke old credential, chuyển dữ liệu có kiểm soát |
| Service host chuyển owner team | Có thể giữ host ID | Cập nhật owner, certificate scope, workload entitlement |

**Một device certificate ràng buộc với tenant org-a không được tự trở thành credential của org-b**. Nếu tổ chức cho phép chuyển tenant, cần có authority, kiểm tra key/ownership, revoke hoặc rotate và cập nhật mọi policy/ACL liên quan.

Người dùng **Mover khỏi đội on-call** có thể vẫn sở hữu laptop compliant nhưng không được tiếp tục dùng emergency access. Thiết bị xác thực được **không khôi phục quyền nghiệp vụ đã hết căn cứ**.

## 25. Leaver: user rời tổ chức nhưng tài sản và khóa còn tồn tại

**Leaver** cần có luồng chấm dứt quyền dựa trên sự kiện HRIS hoặc sponsor, không chờ đợt kiểm tra định kỳ. Các việc chính:

1. Xác định **employment relation nào đã kết thúc**, tránh khóa quyền của quan hệ độc lập khác nếu không có căn cứ.
2. Thu hồi hoặc vô hiệu **user sessions, refresh grants, app tokens và user entitlements** theo policy.
3. Xác định mọi thiết bị được giao, ghi nhiệm vụ **thu hồi, selective wipe/full wipe hoặc kiểm tra pháp lý** tùy ownership.
4. Gỡ liên kết **user–device custody** khi bàn giao hoàn tất, không tự ghi người khác là custodian trước khi xác minh.
5. **Revoke/rotate device credential** khi có nguy cơ thiết bị còn do người cũ kiểm soát; với corporate asset tái cấp phát, thực hiện reset/re-enrollment theo chính sách.
6. Xử lý **PAT, SSH key, VPN credential, local account, service credential** có thể đã lưu trên thiết bị.
7. Ngăn **Joiner/Mover retry cũ** cấp lại role, device trust hoặc session cho người đã Leaver.
8. Kiểm tra **effective deny** với những đường truy cập cần cắt, lưu bằng chứng và các mục chưa xác minh.

**Khóa user ở IdP không nhất thiết khóa ngay chứng chỉ mTLS trên thiết bị hoặc token JWT đã phát hành**, đặc biệt nếu API chỉ kiểm tra chuỗi chứng chỉ và expiry offline. Resource server phải có chiến lược revocation/policy freshness phù hợp.

Thiết bị **không thu hồi được** sau Leaver cần được đưa vào trạng thái **LOST/AT_RISK/SUSPENDED** theo policy, chặn các đường truy cập liên quan, không đánh dấu “đã bàn giao” chỉ vì ticket IT đóng.

## 26. Mất, bị đánh cắp hoặc không kiểm soát được thiết bị

Khi một thiết bị **lost/stolen**, phản ứng phụ thuộc độ nhạy và khả năng quản lý:

~~~mermaid
flowchart TD
    A["Báo mất / anomaly / device risk signal"] --> B["Xác minh deviceId, asset, owner và các credential"]
    B --> C["Đánh dấu SUSPENDED/LOST có event/version"]
    C --> D["Block conditional access, revoke applicable credentials"]
    D --> E["Revoke sessions/grants/tokens theo policy"]
    E --> F["MDM remote lock/wipe nếu có thẩm quyền và khả thi"]
    F --> G["Kiểm tra local accounts, VPN, API và target session"]
    G --> H["Readback + negative tests + ghi phạm vi kiểm chứng"]
    H --> I{"Có đầy đủ bằng chứng?"}
    I -->|"Có"| J["Review sự cố, owner, kết quả xử lý"]
    I -->|"Không"| K["UNVERIFIED / escalation / theo dõi"]
    K --> G
~~~

Một lệnh **remote wipe requested** không đồng nghĩa wipe đã thực thi: thiết bị có thể offline. Cần ghi **command accepted, delivered, executed, verified** theo contract sản phẩm. Nếu không thể xác minh, trạng thái vẫn là **PENDING/UNKNOWN**.

**Không tự coi “đã revoke certificate” là chặn ngay mọi session/token**; phải xét TLS session đã mở, token tự chứa, cache và những service chỉ kiểm tra certificate chain tại lần bắt tay trước.

## 27. Credential rotation và renewal không làm mất danh tính thiết bị

Để giảm rủi ro khóa dài hạn, tổ chức cần **rotation/renewal** theo thời hạn và mức rủi ro.

| Sự kiện | Hành động | Bằng chứng |
| --- | --- | --- |
| Chứng chỉ gần hết hạn | Cấp mới theo policy, PoP hoặc authentication phù hợp | Certificate mới được liên kết đúng device |
| Khóa cũ bị nghi lộ | Rotate sang key mới, revoke key/cert cũ | Các endpoint từ chối credential cũ |
| MDM re-enroll | Gắn management record mới với device/asset đáng tin | Không giữ mapping cũ mồ côi |
| Thiết bị factory reset | Tái bootstrap và xác minh trước khi cấp lại quyền | Credential cũ bị vô hiệu nếu cần |
| Thiết bị chuyển tenant | Thiết lập trust mới và loại trust cũ | Không còn allow ở tenant cũ |
| Thiết bị decommission | Hủy certificate/grant và ghi trạng thái retired | Negative tests/revocation record |

Một số hệ thống cho phép **overlap window** ngắn để chuyển từ chứng chỉ cũ sang mới; phải có giới hạn và không tạo hai khóa cùng được chấp nhận vô thời hạn. Ngược lại, đổi credential **không nên tự đổi deviceId** nếu cùng một device/asset còn hợp lệ và kiến trúc có khả năng correlation an toàn.

**Cấp lại chứng chỉ dựa trên khóa cũ bị lộ** có thể không an toàn. Khi có dấu hiệu compromise, quy trình cần trust bootstrap/attestation mới và approval theo mức rủi ro, không tự gia hạn bằng chính credential nghi đã bị đánh cắp.

## 28. Thiết bị offline, IoT/OT và việc đánh giá trạng thái bị cũ

Thiết bị IoT/OT có thể không kết nối liên tục, không có agent hiện đại hoặc không hỗ trợ rotation dễ dàng. Một máy đo ở nhà máy có thể chỉ đồng bộ khi gateway hoạt động.

Các lựa chọn cần phân tích:

- **Short-lived credential** khi có thể cấp/rotate ổn định.
- **Network segmentation** và gateway kiểm tra identity thay vì cấp access rộng tới toàn mạng.
- **Limited-scope local policy** cho nhiệm vụ thiết yếu khi không kết nối.
- **Offline revocation strategy** có thời hạn tối đa đã định nghĩa, tránh chấp nhận vô hạn.
- **Heartbeat/lastSeenAt** và tình trạng thiếu telemetry được hiển thị rõ.
- **Firmware lifecycle** và thay thiết bị khi không còn hỗ trợ bảo mật.
- **Service owner** chịu trách nhiệm nếu không có người dùng gắn trực tiếp.
- **Audit buffer** và nạp lại log khi kết nối, có khả năng phát hiện gap.

Không áp một quy tắc “mọi thiết bị phải gửi posture mỗi 5 phút” lên hệ thống OT có yêu cầu an toàn vận hành khác mà chưa đánh giá tác động. **Offline chưa tự là compromise**, nhưng policy cần giới hạn chức năng và đặt mức trust phù hợp sự thiếu dữ liệu mới.

## 29. Thiết bị chia sẻ: cần tách device identity khỏi human actor

Ví dụ một kiosk kho đã đăng ký hợp lệ bằng device certificate, nhưng nhiều nhân viên đăng nhập để kiểm kê.

~~~text
Device authentication:
    deviceId = warehouse-kiosk-008
    key/cert = verified

User session A:
    actor = worker-201
    action = READ_INVENTORY

User session B:
    actor = worker-202
    action = ADJUST_INVENTORY

Authorization:
    evaluate actor role + device policy + warehouse scope
~~~

Nếu log chỉ ghi **warehouse-kiosk-008** mà không có verified operator identity, tổ chức không thể quy kết ai đã sửa dữ liệu. Nên yêu cầu **per-user authentication/session** hoặc cơ chế nhận diện operator đã được phê duyệt, phù hợp điều kiện làm việc.

Thiết bị chia sẻ cần kiểm soát **đăng xuất, xóa session cũ, credential cache, local file/clipboard** khi đổi người. Một user đăng nhập sau không được hưởng quyền của user trước dù thiết bị vẫn COMPLIANT.

## 30. Phát hiện thiết bị đăng ký trùng hoặc giả mạo

Các tín hiệu:

| Tín hiệu | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| Một serial xuất hiện ở nhiều deviceId | Re-enroll hợp lệ hoặc giả mạo asset metadata | Kiểm tra reset/reissue events và key/attestation |
| Một public key gắn hai tenant | Mapping lỗi hoặc credential dùng chung không an toàn | Xác minh authority, thu hồi và tách trust |
| Một deviceId ở hai vị trí bất khả thi cùng thời điểm | Clone/sao chép credential hoặc clock/location sai | Chứng thực session, geo accuracy, key protection |
| Device attestation nonce bị replay | Evidence cũ bị tái sử dụng | Nonce store, freshness và signature verification |
| BYOD đột ngột chuyển ownership | Thay đổi hợp lệ hoặc account takeover | Owner/sponsor review, device binding |
| Agent gửi COMPLIANT không có nguồn được tin | Posture spoofing | Verifier/management channel và source signature |
| MDM record active nhưng asset đã retired | Lifecycle drift | Reconciliation và revoke |

Không khẳng định **clone** chỉ từ IP/địa lý bất thường: VPN, proxy, NAT, đồng hồ lệch và mạng di động có thể gây sai số. Cần tập hợp bằng chứng từ **key proof, enrollment, token, attestation và target logs**.

**Duplicate handling** phải tránh xóa tự động một thiết bị hợp lệ khi mapping mơ hồ. Với quyền nhạy cảm, có thể đặt trust state **SUSPENDED_PENDING_REVIEW** và điều tra theo playbook đã được ủy quyền.

## 31. API registration phải kiểm soát input và chống replay

Một API nội bộ đăng ký thiết bị có thể nhận:

~~~http
POST /device-registry/v1/registrations HTTP/1.1
Content-Type: application/json
Authorization: Bearer ENROLLMENT_TOKEN_PLACEHOLDER
Idempotency-Key: registration-request-2026-482

{
  "requestedTenant": "org-a",
  "assetRef": "asset-482",
  "publicKeyRef": "key-request-482",
  "challengeRef": "nonce-session-482",
  "proofRef": "signed-proof-482",
  "deviceClass": "CORPORATE_LAPTOP"
}
~~~

Đây là **API giả định**. Không phải schema SCIM/OAuth/EST chuẩn, và **proofRef** chỉ có nghĩa khi server kiểm tra challenge/PoP đáng tin. Backend phải:

1. Xác minh **enrollment token/actor** với issuer, audience, hạn, trạng thái one-time và tenant.
2. Không tin **requestedTenant, assetRef, ownerId, deviceClass hoặc posture** chỉ từ client.
3. Kiểm tra challenge **nonce, signature, expiry, request binding** và chống replay.
4. Xác thực asset/provenance và policy về số thiết bị/người/tenant.
5. Phân biệt device đã đăng ký với request trùng do retry, chống duplicate/squat.
6. Dùng **rate limit, quota và chống enumeration** theo risk.
7. Tạo device record với **state/version**, không tự đánh dấu VERIFIED khi chưa đủ bằng chứng.
8. Chỉ cấp certificate/credential phù hợp **key, purpose, tenant và lifetime**.
9. Ghi event/audit không chứa token hay private key.
10. Khi timeout, **readback** record và credential đã phát hành trước khi retry tạo thêm.

**Idempotency key do client gửi không tự là bằng chứng thẩm quyền**. Nó chỉ hỗ trợ tránh xử lý một ý định lặp; server vẫn phải gắn key với actor, scope và dữ liệu request đã xác thực.

## 32. Ví dụ JSON của Device registration record

~~~json
{
  "deviceId": "dev-org-a-000482",
  "organizationId": "org-a",
  "deviceClass": "CORPORATE_LAPTOP",
  "ownershipType": "CORPORATE",
  "assetRef": "asset-482",
  "custodianIdentityRef": "iam-lan-482",
  "employmentRelationRef": "emp-org-a-482",
  "registration": {
    "state": "VERIFIED",
    "method": "MANAGED_BOOTSTRAP_WITH_KEY_PROOF",
    "registeredAt": "2026-11-23T09:00:00+07:00",
    "lastVerifiedAt": "2026-11-23T09:03:00+07:00",
    "policyVersion": "device-registration-v8"
  },
  "management": {
    "source": "mdm-primary",
    "state": "ENROLLED",
    "compliance": "COMPLIANT",
    "assessedAt": "2026-11-23T09:05:00+07:00",
    "policyVersion": "endpoint-baseline-v12"
  },
  "deviceCredentialRefs": [
    "device-cert-482-v2"
  ],
  "attestationEvidenceRef": "attestation-482-20261123",
  "lifecycleState": "ASSIGNED",
  "sourceVersion": 17,
  "lastSeenAt": "2026-11-23T09:06:00+07:00",
  "suspendedAt": null,
  "retiredAt": null
}
~~~

Đây là **record thiết kế minh họa**, không phải yêu cầu chuẩn cho mọi MDM/IdP. Một trường **lastSeenAt** không chứng minh toàn bộ trạng thái an toàn tại thời điểm đó; một trường **attestationEvidenceRef** chưa tự nói verifier đã xác nhận claims nào.

Thông tin tài sản, thiết bị và employee có thể liên quan dữ liệu cá nhân; cần kiểm soát **quyền đọc record, retention và mục đích sử dụng**. **Không lưu private key, OAuth token, password hoặc toàn bộ HR profile**.

## 33. State machine của Device registration

~~~mermaid
stateDiagram-v2
    [*] --> DISCOVERED
    DISCOVERED --> PENDING_PROOF: Có yêu cầu và asset/sponsor
    PENDING_PROOF --> VERIFIED: PoP và trust checks đạt
    PENDING_PROOF --> REJECTED: Policy/identity checks không đạt
    VERIFIED --> ACTIVE: Credential + management/policy đáp ứng
    VERIFIED --> SUSPENDED: Thiếu assurance hoặc rủi ro
    ACTIVE --> SUSPENDED: Lost / compromised / posture high risk
    ACTIVE --> REENROLLMENT_REQUIRED: Reset / tenant transfer / key rollover
    REENROLLMENT_REQUIRED --> PENDING_PROOF: Bootstrap mới
    SUSPENDED --> REENROLLMENT_REQUIRED: Recovery được phép
    SUSPENDED --> REVOKING: Revoke hoặc retire
    ACTIVE --> REVOKING: Lifecycle end
    REVOKING --> REVOKED_UNVERIFIED: Đã gửi thay đổi
    REVOKED_UNVERIFIED --> RETIRED: Credential và access được kiểm chứng
    REVOKED_UNVERIFIED --> BLOCKED: Chưa xác minh target
    BLOCKED --> REVOKED_UNVERIFIED: Reconciliation/retry
    REJECTED --> [*]
    RETIRED --> [*]
~~~

Sơ đồ này là **một state machine tham khảo**. Thực tế nên giữ **registration, management, posture, credential và lifecycle state độc lập** như mục 10. Đặc biệt, chuyển ACTIVE → SUSPENDED không nhất thiết đồng nghĩa asset phải RETIRED hoặc chứng chỉ đã bị CA revoke; phải thực thi các bước cần thiết theo policy.

Một thiết bị có thể **re-enroll sau sửa chữa** nhưng cần quy trình tin cậy mới; không cho một record RETIRED tự trở lại ACTIVE chỉ vì event cũ từ MDM gửi tới muộn.

## 34. Mã giả: đăng ký thiết bị có kiểm soát

~~~text
registerDevice(enrollmentRequest, authenticatedRequester, now):
    requireAuthorizedEnrollmentRequester(authenticatedRequester)

    policy = loadCurrentDeviceRegistrationPolicy()
    tenant = resolveTrustedTenant(enrollmentRequest, authenticatedRequester)
    asset = loadAuthoritativeAssetOrSponsorRecord(enrollmentRequest.assetRef)

    if not asset.eligibleFor(tenant, enrollmentRequest.deviceClass):
        return INELIGIBLE_ASSET_OR_TENANT

    if duplicateOrAmbiguousDeviceIdentity(asset, tenant):
        return REVIEW_DUPLICATE_LINK

    challenge = loadOneTimeChallenge(enrollmentRequest.challengeRef)
    if not challenge.validFor(tenant, now):
        return INVALID_OR_EXPIRED_CHALLENGE

    keyProof = verifyProofOfPossession(
        challenge,
        enrollmentRequest.publicKeyMaterial,
        enrollmentRequest.signature
    )
    if not keyProof.valid:
        return PROOF_FAILED

    if policy.requiresAttestation(asset.deviceClass):
        attestation = verifyAttestationWithTrustedRoot(
            enrollmentRequest.attestationEvidence,
            challenge,
            enrollmentRequest.publicKeyMaterial
        )
        if not attestation.meetsPolicy:
            return ATTESTATION_NOT_ACCEPTED

    record = atomicallyCreateVersionedDeviceRecord(
        tenant, asset, keyProof.keyReference, status=VERIFIED
    )
    recordAuditEvent("DEVICE_REGISTERED_VERIFIED", record)
    return PENDING_CREDENTIAL_AND_MANAGEMENT_CHECKS
~~~

Mã giả **không tự cấp quyền nghiệp vụ**. Cần có mô hình nhất quán khi challenge bị sử dụng đồng thời hoặc khi phát hành chứng chỉ và tạo registry record nằm ở hai dịch vụ độc lập. Một transaction nội bộ không tự bảo đảm CA và MDM cùng cập nhật thành công; cần **idempotency và reconciliation**.

## 35. Mã giả: authorization có xét cả user lẫn device

~~~text
authorizeSensitiveRead(session, deviceProof, resource, now):
    user = verifyUserSessionAndAssurance(session)
    device = verifyDeviceCredentialAndRegistryMapping(deviceProof)

    if user.unverified or device.unverified:
        return DENY_OR_INDETERMINATE_PER_POLICY

    employment = authoritativeRelationFor(user, resource.organizationId)
    if not employment.activeAt(now):
        return DENY

    if device.organizationId != resource.organizationId:
        return DENY_CROSS_TENANT

    if device.registrationState != VERIFIED:
        return DENY
    if device.lifecycleState in [LOST, SUSPENDED, RETIRED]:
        return DENY
    if device.credentialState != ACTIVE:
        return DENY

    posture = getTrustedPosture(device.deviceId)
    if posture.unknownOrTooOldFor(resource.classification):
        return DENY_OR_REQUIRE_DEVICE_REMEDIATION

    if not user.hasExpectedEntitlement("REPORT_READ", resource.projectId):
        return DENY

    if not evaluateCurrentResourcePolicy(user, device, resource, now):
        return DENY

    return PERMIT_WITH_AUDIT
~~~

Không dùng code này như cấu hình production mà chưa đánh giá chính sách. Có tình huống tài nguyên không yêu cầu managed device, hoặc emergency access có quy trình riêng được kiểm soát. **Trạng thái PIP/PDP không lấy được không đồng nghĩa Permit**. Quyền nên được quyết định tại **backend/resource server**, không chỉ dựa nút hiển thị trên frontend.

## 36. Đối soát: registry, MDM, IdP, CA và resource server

**Reconciliation** phát hiện khi trạng thái đã được quyết định ở nguồn quản trị khác với trạng thái có thể sử dụng thật.

| Trạng thái nguồn | Trạng thái target | Phát hiện |
| --- | --- | --- |
| Device registry SUSPENDED | VPN vẫn cho mTLS | Revocation/policy enforcement chưa đầy đủ |
| MDM NONCOMPLIANT | SaaS vẫn cho export nhạy cảm | Conditional access không áp đúng |
| CA cert REVOKED | Gateway chấp nhận certificate cũ | Revocation checking/cache/fail-open cần kiểm tra |
| User Leaver | Local admin/PAT trên device vẫn active | Quyền tồn dư theo người |
| Device RETIRED | Cloud/IAM role của host còn | Workload/device access tồn dư |
| Asset đã bàn giao người B | Directory vẫn gắn người A | Custody/identity linking sai |
| Device mới enroll | Registry có hai key record ACTIVE không chủ đích | Duplicate credential/rotation failure |
| Workload service đổi owner | Certificate policy vẫn thuộc owner cũ | Governance drift |

**Một API call cập nhật thành công không chứng minh mọi đích đã áp dụng.** Cần đọc lại record tại các nguồn phù hợp và kiểm tra **effective access** trên đường bị hạn chế.

Tổ chức nên định nghĩa **SLA/safety threshold** cho propagation và revocation theo mức rủi ro; giá trị phụ thuộc hạ tầng, không có con số chuẩn cho mọi device.

## 37. Event ordering, idempotency và tránh cấp lại trust cũ

Trong hệ thống phân tán có thể xảy ra:

~~~text
09:00  Device ACTIVE theo registry version 10
09:01  Thiết bị bị báo LOST -> version 11, revoke requested
09:02  Queue phát lại MDM enrollment event của version 9
09:03  Nếu handler không kiểm tra version, device bị bật ACTIVE lại
09:04  Token/device cert cũ có thể tiếp tục truy cập
~~~

Kiểm soát cần có:

1. Lưu **deviceId, tenant, eventId, sourceVersion, effectiveAt và lifecycleVersion**.
2. Không để event cũ **ghi đè** trạng thái mới hơn từ nguồn có thẩm quyền.
3. Tách **re-enrollment flow có phê duyệt** khỏi replay event enrollment cũ.
4. Dùng **idempotency key** với đăng ký/cấp chứng chỉ/revoke và retry.
5. Không cấp thêm certificate vô hạn chỉ vì connector timeout.
6. Khi có **lost/compromised/Leaver**, chặn đường privilege phát sinh từ session/grant cũ theo policy.
7. Đối soát định kỳ cả **credential mà CA biết** nhưng registry không còn chủ sở hữu.

Không phải nguồn nào cũng có version toàn cục tương thích. Khi kết hợp HRIS, registry, MDM, CA và SaaS, cần giữ **source authority theo thuộc tính** và quy tắc cập nhật; không chỉ chọn bản ghi **updatedAt mới nhất** từ mọi nơi.

## 38. Bảo mật và quyền riêng tư của Device registration

Thiết bị có thể phát lộ thông tin nhạy cảm: serial, vị trí, network path, lịch sử dùng, ứng dụng cài đặt, số hiệu phần cứng hoặc thông tin cá nhân của người sở hữu BYOD.

| Rủi ro | Kiểm soát phù hợp |
| --- | --- |
| **Device tracking quá mức** | Thu thập theo mục đích, minh bạch và giới hạn retention |
| **Unique identifier bị lộ** | Phân quyền xem, không public asset/serial mapping |
| **Token/credential bị log** | Field allowlist và redaction |
| **Enrollment token bị đánh cắp** | TTL ngắn, one-time, audience/tenant binding |
| **Device spoofing/clone** | PoP, attestation khi cần, rotate/revoke, anomaly detection |
| **API enumeration** | Authorization, rate limit, không lộ sự tồn tại deviceId tùy tiện |
| **Cross-tenant data leak** | Kiểm tra tenant tại API và phân quyền asset registry |
| **Insider self-registration** | SoD giữa requester, asset verifier và privileged approver |
| **Unmanaged/BYOD privacy** | Work profile/managed container, mức thu thập tối thiểu |
| **Stale compliance** | Freshness/SLA và deny/step-up theo mức rủi ro |

**Đăng ký thiết bị có thể là một điểm tập trung dữ liệu nhân sự và tài sản**. Người xem device catalog không tự có quyền truy cập mọi dữ liệu posture hoặc vị trí; cần áp dụng RBAC/ABAC cho chính registry và log.

Không đặt mục tiêu **định vị mọi thiết bị liên tục** nếu không có căn cứ pháp lý, chính sách và nhu cầu bảo mật tương xứng.

## 39. Audit: ghi gì cho toàn bộ vòng đời Device registration?

Các event đáng có:

| Event | Dữ liệu cần giữ |
| --- | --- |
| **DEVICE_REGISTRATION_REQUESTED** | Requester, device/assetRef, tenant, enrollment policy |
| **DEVICE_PROOF_VERIFIED/FAILED** | ChallengeRef, method, verifier/policy version, không log private key |
| **ATTESTATION_EVALUATED** | Result, evidenceRef, claims summary được phép |
| **DEVICE_REGISTERED** | deviceId, trust state, source/version, timestamp |
| **DEVICE_CREDENTIAL_ISSUED** | credentialRef, issuer, purpose, validity, subject mapping |
| **DEVICE_MDM_ENROLLED** | management source, enrollment state/time |
| **DEVICE_POSTURE_CHANGED** | before/after, assessedAt, policy and source |
| **DEVICE_CUSTODY_CHANGED** | old/new custodianRef, approval, reason |
| **DEVICE_SUSPENDED/LOST** | actor, incident, effectiveAt và immediate restrictions |
| **DEVICE_CREDENTIAL_REVOKED** | credentialRef, issuer outcome và propagation |
| **DEVICE_UNREGISTERED/RETIRED** | lifecycle reason, owner, cleanup status |
| **DEVICE_ACCESS_DENIED/ALLOWED** | Verified subject/device/resource/action/policy and outcome |
| **DEVICE_RECONCILIATION_FINDING** | Expected vs observed state và owner |

Ví dụ audit:

~~~json
{
  "eventId": "device-audit-2026-0082",
  "eventType": "DEVICE_SUSPENDED",
  "deviceId": "dev-org-a-000482",
  "tenantId": "org-a",
  "assetRef": "asset-482",
  "actorIdentityRef": "iam-security-21",
  "incidentRef": "INC-2026-102",
  "reasonCode": "REPORTED_LOST",
  "sourceVersion": 18,
  "policyVersion": "device-security-v12",
  "occurredAt": "2026-11-23T10:05:00+07:00",
  "credentialRevocationState": "PENDING",
  "idpSessionRevocationState": "REQUESTED",
  "mdmWipeState": "UNKNOWN_OFFLINE_DEVICE",
  "verifiedTargetDenyAt": null,
  "correlationId": "lost-device-asset-482"
}
~~~

**PENDING/UNKNOWN** phải được giữ đúng nghĩa. Record này **chưa chứng minh đã thu hồi hoàn tất**. Cần link tới remediation và readback; không thay trường UNKNOWN bằng SUCCESS cho đẹp báo cáo.

**Không ghi secret, token, full PII hoặc certificate private key** trong audit. Có thể cần bảo vệ log khỏi sửa/xóa bởi chính người quản trị thiết bị.

## 40. Monitoring, detection và KPI

| Chỉ số/tín hiệu | Cách sử dụng | Cảnh báo diễn giải |
| --- | --- | --- |
| **Registration completion rate** | Đăng ký có bằng chứng hợp lệ | Không chỉ đếm record đã tạo |
| **Unverified device ratio** | Thiết bị có record nhưng thiếu PoP/owner | Phân loại theo mục đích và risk |
| **Managed device coverage** | Tỷ lệ thiết bị thuộc policy cần MDM đã enroll | BYOD/OT có policy khác |
| **Posture freshness** | Độ tuổi đánh giá compliance | UNKNOWN khác COMPLIANT |
| **Certificate expiring count** | Dự báo lỗi authentication do expiry | Đặt cảnh báo theo lịch renewal thực tế |
| **Revoked devices still allowed** | Quyền còn dùng được sau revoke | Kiểm tra tại PEP, ưu tiên theo rủi ro |
| **Lost-device response time** | Từ báo mất tới khi chặn quyền được chứng minh | Không chỉ tới lúc gửi lệnh wipe |
| **Orphaned device identity** | Device không có owner hoặc không có asset/source | Có thể là workload/shared hợp lệ cần phân loại |
| **Duplicate device/key anomalies** | Credential mapping trùng đáng ngờ | Tránh kết luận clone từ tên/IP |
| **Leaver assigned devices** | Tài sản và credential còn gắn người đã rời | Phân biệt thu hồi asset và quyền |
| **Unmanaged sensitive access** | API nhạy cảm từ thiết bị không đạt policy | Xem exemption hợp lệ |
| **Registration/MDM/CA drift** | Nguồn không khớp về trust/lifecycle | Cần reconciliation và owner |

Các ngưỡng KPI cần dựa trên **SLA, khả năng offline của thiết bị, mức nhạy cảm hệ thống và năng lực quan sát**. Số lượng thiết bị đăng ký tăng không tự đồng nghĩa mức bảo mật tăng nếu số device mồ côi/khóa chưa thu hồi cũng tăng.

## 41. Test cases cho Device registration

| Test | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| T01 | Device corporate hợp lệ, PoP và policy đạt | Tạo deviceId VERIFIED đúng tenant |
| T02 | Chỉ biết serial nhưng không có proof | Không đánh VERIFIED |
| T03 | Challenge nonce đã dùng lại | Reject replay |
| T04 | Signature không khớp public key | Registration failed |
| T05 | Attestation claim bị sửa hoặc thiếu trust anchor | Không chấp nhận evidence |
| T06 | Attestation hợp lệ nhưng posture không đạt | Không cấp quyền nhạy cảm |
| T07 | Registry có record, MDM chưa enroll | Phân biệt REGISTERED và ENROLLED |
| T08 | Thiết bị mang certificate org-a xin vào org-b | Deny nếu không có trust cross-tenant được phép |
| T09 | User MFA hợp lệ nhưng device revoked | Device gate Deny theo policy |
| T10 | Device compliant nhưng user Leaver | User/resource authorization Deny |
| T11 | Device được bàn giao người mới | Reset/rotate/rebind, session cũ không dùng được |
| T12 | Asset được báo LOST và offline | Suspend và ghi wipe UNKNOWN, không tuyên bố wiped |
| T13 | Chứng chỉ bị revoke, API còn nhận do cache | Finding residual, không VERIFIED_CLOSED |
| T14 | Certificate renewal theo kỳ | Credential mới đúng deviceId, khóa cũ xử lý theo policy |
| T15 | Hai request enroll retry sau timeout | Idempotent, không tạo identity/credential trùng |
| T16 | Event MDM version cũ tới sau LOST | Không tái kích hoạt device |
| T17 | Một kiosk nhiều người sử dụng | Audit giữ device và user actor riêng |
| T18 | Workload/server không có human custodian | Có service owner và machine policy phù hợp |
| T19 | IoT offline lâu quá freshness threshold | Quyền được giới hạn/đánh giá theo policy |
| T20 | SCIM User deactivated nhưng certificate còn active | Không coi deprovision hoàn tất |
| T21 | Device enrollment token dùng sai audience | Deny |
| T22 | Client tự gửi compliance=true | Không tin nếu không qua source tin cậy |
| T23 | API registration bị brute-force/enum | Rate limit và không lộ mapping nhạy cảm |
| T24 | Lost-device recovery không có proof mới | Không tự ACTIVE |
| T25 | DeviceId trùng across orgs | Namespace và tenant validation không trộn |
| T26 | API nghiệp vụ chỉ kiểm tra group, bỏ device policy | Integration test phát hiện bypass |
| T27 | Token device-bound bị replay trên device khác | Không được chấp nhận nếu verifier hỗ trợ binding |
| T28 | Certificate expired nhưng device record ACTIVE | Authentication/PEP không chấp nhận credential |
| T29 | BYOD offboarding | Selective removal theo policy, không tự full wipe |
| T30 | Revoke đã gửi nhưng target không đọc được | Giữ UNVERIFIED với owner/deadline |

**Unit tests** cho rule và state machine cần đi cùng **integration tests** với MDM, IdP, PKI, VPN/ZTNA và API thực thi. Khi thử nghiệm mất thiết bị, revoke hay wipe, chỉ dùng **test device/tenant được ủy quyền**, không thao tác phá hủy thiết bị thật ngoài quy trình.

## 42. Tình huống thực hành: Joiner, Mover, mất thiết bị và offboarding

**Bối cảnh:** Công ty quản lý dữ liệu báo cáo ở **org-a**. Nhân viên Lan tham gia nhóm Atlas và được giao laptop doanh nghiệp. Sau đó Lan chuyển sang Nova, rồi mất laptop trong lúc công tác.

### Giai đoạn A — Joiner và đăng ký

IT ghi asset **asset-482** vào CMDB và giao cho Lan. Device registration xác minh enrollment token, key proof trên thiết bị, gắn **dev-org-a-000482** với assetRef; sau đó MDM enroll và đánh giá posture. IdP xác minh Lan bằng SSO/MFA, IAM cấp **Atlas ReportViewer** theo nhiệm vụ.

Những kết quả cần kiểm:

~~~text
Device registry: dev-org-a-000482 -> VERIFIED
Management: ENROLLED
Posture: COMPLIANT at assessedAt
User relation: Lan ACTIVE in org-a / Atlas
READ Atlas report -> ALLOW
EDIT Atlas report -> DENY
READ Nova report -> DENY
~~~

### Giai đoạn B — Mover sang Nova

HRIS/project registry xác nhận Lan rời Atlas sang Nova. Laptop vẫn thuộc org-a, vẫn dùng cùng deviceId nếu không có yêu cầu đổi; IAM rút quyền Atlas và cấp quyền Nova đúng phê duyệt. Kết quả:

~~~text
Device identity -> vẫn VERIFIED nếu các điều kiện trust còn hiệu lực
User READ Atlas -> DENY
User READ Nova -> ALLOW sau khi entitlement mới có hiệu lực
~~~

**Không xóa device record chỉ vì người dùng đổi dự án**. Device identity và job role là các thực thể khác nhau.

### Giai đoạn C — Báo mất laptop

Lan thông báo asset-482 bị thất lạc. Security đánh dấu **device LOST/SUSPENDED**, yêu cầu revoke device credential, session/token liên quan và gửi lệnh remote wipe theo policy.

| Tín hiệu | Kết quả | Diễn giải |
| --- | --- | --- |
| Registry state | SUSPENDED | Không còn được coi ACTIVE |
| CA revoke | ACCEPTED | Cần xét propagation và cache |
| MDM remote wipe | PENDING_OFFLINE | Chưa được tuyên bố hoàn tất |
| VPN mTLS kiểm tra test device credential cũ | DENY | Bằng chứng tại đường VPN đã kiểm |
| SaaS access token cũ ở API | DENY sau biện pháp phù hợp | Bằng chứng tại endpoint đã kiểm |
| Asset physically recovered | NO | Tiếp tục theo dõi asset |

Nếu app vẫn ALLOW một access token tự chứa đã cấp trước sự kiện, finding phải giữ **REMEDIATION_PENDING**. Không dùng trạng thái SUSPENDED ở registry để kết luận mọi session thực tế đã bị chặn.

### Giai đoạn D — Cấp thiết bị thay thế

IT cấp laptop mới với **deviceId mới** và quy trình bootstrap/registration riêng. Không tái sử dụng chứng chỉ hoặc private key của thiết bị bị mất để “tiết kiệm thời gian”. Lan có quyền hợp lệ trên Nova sau khi user/device policy đạt.

### Giai đoạn E — Leaver

Khi Lan nghỉ việc, HRIS kích hoạt Leaver. IAM rút user entitlement, token/session và liên kết custody của laptop mới; IT thu hồi tài sản. Device có thể được reset và giao người khác theo quy trình, nhưng **quyền của Lan không được hồi sinh** khi device re-enroll.

### Câu hỏi thực hành

**1. Vì sao có device certificate không chứng minh Lan được đọc mọi báo cáo?**

Vì certificate chỉ giúp xác thực một thiết bị/khóa trong trust domain. API còn phải kiểm tra **user entitlement, tenant, resource, session và policy**.

**2. Device record đã VERIFIED, nhưng MDM báo NONCOMPLIANT; có nên ALLOW truy cập production nhạy cảm không?**

Không tự động. Quyết định phải theo policy; với tài nguyên yêu cầu compliance, cần Deny hoặc remediation-only flow.

**3. MDM đã gửi wipe SUCCESS ở mức “command queued”, có thể kết luận dữ liệu đã xóa không?**

Không. Cần biết thiết bị đã nhận và thực thi lệnh chưa, nhất là khi offline.

**4. Sau Mover, thiết bị có cần đổi deviceId không?**

Không nhất thiết. DeviceId có thể giữ nguyên khi cùng thiết bị/tenant; cần đổi user entitlement và association theo policy.

**5. Người dùng Leaver, nhưng laptop được giao nhân viên mới; giữ nguyên certificate cũ có ổn không?**

Không mặc định. Phải thực hiện reset/re-enroll/rotate credential theo chính sách để chặn session, khóa và dữ liệu thuộc người cũ. Có thể giữ assetId, nhưng trust/credential phải được tái xác minh.

## 43. Checklist triển khai Device registration

| Câu hỏi | Bằng chứng hoặc kiểm soát cần có |
| --- | --- |
| Đã phân biệt device registration với MDM enrollment và authentication? | State model, policy và event contract riêng |
| Có phân biệt OAuth Device Authorization Grant? | Giao thức và đối tượng đăng ký được gọi tên rõ |
| Có xác minh asset/tenant và source authority? | CMDB, sponsor, registration policy |
| Có liên kết đúng người, asset, device và workload? | Stable IDs theo namespace; không chỉ email/serial |
| Có bootstrapping đáng tin? | Enrollment token, factory credential, MDM authority hoặc kiểm tra OOB |
| Có PoP? | Nonce, signature, binding, anti-replay |
| Có attestation phù hợp khi cần? | Evidence/trust anchor, claims và freshness |
| Có private key được bảo vệ? | Hardware-backed key khi hỗ trợ, không xuất secret |
| Có vòng đời certificate/credential? | Issuance, expiry, rotation, revocation |
| Có trust state độc lập với posture/compliance? | VERIFIED vs ENROLLED vs COMPLIANT |
| Có độ mới của posture? | assessedAt, sourceVersion, freshness policy |
| Có policy cho BYOD/shared/IoT? | Privacy, ownership, user session, offline |
| Có tenant/resource binding? | Không chấp nhận role/device của org khác không được phép |
| Có kiểm tra user và device tại backend? | RBAC/ABAC/PBAC, IdP/SSO/MFA, PEP/API |
| Có chống replay hoặc đăng ký trùng? | Challenge state, idempotency, unique device/key mapping |
| Joiner có tạo đúng device và cấp quyền riêng? | Asset handoff, enrollment, entitlement approval |
| Mover có giữ/tái gắn thiết bị đúng? | Custody, role delta, token/session và target readback |
| Leaver có thu hồi user và xử lý asset? | Employment cutoff, revoke, device return/wipe/reissue |
| Mất thiết bị có quy trình chặn ngay? | SUSPEND, revoke, credential/session review |
| Revoke có chống event cũ tái cấp quyền? | Source versions, lifecycle state, retry guards |
| Device registry có audit? | Registration/credential/owner/posture/lifecycle events |
| Có kiểm soát quyền riêng tư? | Data minimization, log access và retention |
| Có giám sát thiết bị mồ côi và trạng thái lệch? | CMDB vs MDM vs IdP vs CA reconciliation |
| Có xác minh quyền thực tế sau revoke? | Target readback và negative authorization tests |
| Có trạng thái UNKNOWN/UNVERIFIED? | Không báo hoàn tất nếu thiếu chứng cứ |
| Có KPI và người chịu trách nhiệm? | Risk-based SLA, detection, response, owner |

## 44. Tổng kết

**Device registration** là quá trình thiết lập **danh tính thiết bị được quản trị** cùng bằng chứng về nguồn gốc, khóa, người/đơn vị chịu trách nhiệm, tenant và trạng thái vòng đời. Nó **khác** với MDM enrollment, directory join, OAuth Device Authorization Grant, user authentication và resource authorization. Một device record hay certificate hợp lệ **không tự chứng minh thiết bị compliant hoặc người dùng được phép truy cập dữ liệu**.

Trong quản lý vòng đời danh tính **Joiner–Mover–Leaver**, **HRIS/nguồn bảo trợ** cung cấp quan hệ công việc; **asset/MDM/device registry** quản lý tài sản, enrollment và posture; **IdP/SSO/MFA** xác thực người dùng; **PKI/TPM/attestation** hỗ trợ danh tính máy và chứng minh khóa; **SCIM** quản lý User/Group ở những ứng dụng hỗ trợ; **RBAC/ABAC/PBAC và PEP** quyết định quyền theo user, device, tenant, resource và thời điểm. **Workload/server/IoT identities** cần owner và vòng đời credential phù hợp môi trường riêng.

Một triển khai an toàn phải **bootstrap trust đúng nguồn, xác minh proof-of-possession, quản lý certificate/credential, giữ posture đủ mới, bảo vệ quyền riêng tư, xử lý lost/retired/reissued, chống replay và event cũ**, đồng thời **đọc lại trạng thái ở các hệ thống đích để xác nhận quyền đã bị chặn**. Kết quả là thiết bị có thể được nhận diện và quản trị xuyên suốt vòng đời mà không làm phát sinh **đặc quyền thừa hoặc quyền truy cập tồn dư** khi người, máy hoặc nhiệm vụ thay đổi.
