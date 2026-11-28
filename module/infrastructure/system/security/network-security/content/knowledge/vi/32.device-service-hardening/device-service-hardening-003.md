# Đổi credential mặc định của thiết bị

**Đổi credential mặc định của thiết bị** (*removing or replacing default device credentials*) là một yêu cầu hardening nền tảng nhưng dễ bị thực hiện thiếu: thiết bị mạng, thiết bị quản trị hạ tầng hoặc thiết bị IoT có thể được bàn giao với tài khoản, mật khẩu, community string, khóa hoặc quyền truy cập cấu hình sẵn. Nếu các thông tin này **dùng chung giữa nhiều thiết bị, dễ đoán, được công bố rộng hoặc không được quản lý theo vòng đời**, một người có thể truy cập **management plane** mà không cần khai thác lỗ hổng phần mềm. Mặt khác, đổi mật khẩu vội vàng mà không kiểm kê dependencies, đường quản trị dự phòng và trạng thái high availability (HA) có thể khiến tổ chức **mất quyền quản trị, mất telemetry hoặc gián đoạn dịch vụ**.

Bài thuộc chương **Hardening thiết bị và dịch vụ mạng** của module **SECURITY_NETWORK_SECURITY**. Nó kết nối kiến thức về firewall, router/switch, phân đoạn mạng, VPN, IDS/IPS, bảo vệ DNS, quản trị thiết bị không dây, cloud/network appliances và giám sát mạng để giải quyết một câu hỏi thực tế: **làm thế nào chứng minh mọi credential mặc định có rủi ro đã được thay hoặc vô hiệu hóa, các tích hợp vẫn hoạt động đúng, và không còn đường đăng nhập trái phép?**

> **An toàn và phạm vi:** chỉ kiểm tra, cấu hình và thử nghiệm trên **thiết bị thuộc quyền quản trị và trong khung thay đổi được duyệt**. Không dùng danh sách mật khẩu nhà sản xuất để thử trên thiết bị bên thứ ba, không tự động dò đăng nhập hàng loạt, không gửi mật khẩu thật vào log/ticket/chat, không thay đổi thiết bị sản xuất khi chưa có **backup, recovery path, approval và kế hoạch rollback**. Ví dụ trong bài sử dụng tài khoản, địa chỉ và bí mật **giả lập**, không phải chỉ thị áp trực tiếp lên một dòng thiết bị cụ thể. Lệnh CLI/API phải được đối chiếu tài liệu của đúng phiên bản firmware/vendor.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **factory default credential, vendor-published credential, shared initial password, service credential, recovery identity, SSH key, certificate/private key, API token và SNMP community**.
2. Kiểm kê thiết bị, giao diện quản trị, account, credential usage, owner, dependency, HA/DR và vòng đời trước khi thay đổi.
3. Nhận diện rủi ro khi **default account vẫn enabled, mật khẩu trùng trên nhiều thiết bị, hardcoded secret trong automation hoặc quyền admin quá rộng**.
4. Thiết kế chính sách **unique, high-entropy, device-specific credential**, lưu tại vault và phân phối theo least privilege.
5. Phân biệt **đổi mật khẩu, đổi khóa, revoke token, thay SNMP community, rotate TLS certificate và tắt dịch vụ quản trị không cần thiết**.
6. Lựa chọn **local account, TACACS+/RADIUS, directory/SSO, MFA/PAM và break-glass account** theo khả năng nền tảng mà không gây khóa quản trị.
7. Xây quy trình **preflight → staged rotation → verify → revoke old access → evidence → rollback/recertify** cho một thiết bị và cho fleet.
8. Xử lý credential phụ thuộc vào **monitoring, config backup, NMS, automation, HA peers, VPN/Wi-Fi, IPMI/BMC và remote access**.
9. Xác minh sự thay đổi bằng **readback, login/negative tests hợp lệ, audit logs, management access policy và health/SLO checks**.
10. Xử lý tình huống **mất quyền đăng nhập, credential leak, factory reset, firmware migration, zero-touch provisioning (ZTP) và DR restore**.
11. Tạo mô hình đe dọa, monitoring rules, checklist nghiệm thu và kế hoạch remediation có owner/expiry.
12. Thực hành trên **lab offline dùng synthetic inventory, credential references và events**, không cần gửi secret thật hoặc thay production.

## 2. Credential mặc định: hiểu đúng đối tượng cần đổi

### 2.1. Default credential là gì?

Một **default credential** là thông tin xác thực được gán sẵn, dùng chung hoặc khởi tạo theo quy trình của nhà sản xuất/tích hợp, trước khi được thay thế bằng **credential do chủ sở hữu hệ thống kiểm soát**. Có nhiều trường hợp:

- **Factory-wide shared password:** nhiều thiết bị cùng model/firmware có cùng tài khoản/mật khẩu.
- **Installer/integrator default:** nhà triển khai gán cùng một mật khẩu để cấu hình hàng loạt.
- **First-login bootstrap account:** tài khoản ban đầu buộc đổi mật khẩu khi onboard.
- **Per-device unique initial secret:** có thể được in trên nhãn hoặc cung cấp bằng kênh riêng; **không mặc nhiên là shared factory password**.
- **Service account:** credential cho agent, NMS, backup, API integration hoặc provisioning.
- **Recovery/maintenance access:** phương thức quản trị dự phòng theo vendor (có thể không đổi được như mật khẩu thường).
- **Default trust material:** certificate/private key, shared SNMP community, VPN PSK hoặc API token cấu hình mẫu.

**Không phải tất cả đều dùng cùng thao tác “change password”.** Một certificate chứa public key và private key có cơ chế vòng đời khác password; SNMPv3 dùng authentication/privacy keys theo user model; OAuth token có issuer/expiry/revocation; phần cứng có immutable recovery mechanism cần bảo vệ bằng physical access hoặc vendor workflow.

### 2.2. Shared default khác unique per-device initial credential

| Loại | Rủi ro điển hình | Xử lý |
| --- | --- | --- |
| **Shared factory credential** | Biết một credential có thể truy cập nhiều thiết bị | Thay/vô hiệu hóa ngay trong onboarding có kiểm soát |
| **Shared installer password** | Lộ từ dự án khác hoặc từ người triển khai | Cấp unique per-device/account, thu hồi quyền installer |
| **Per-device printed secret** | Có thể lộ qua ảnh nhãn, vận chuyển, asset records | Đổi khi chính sách yêu cầu, hạn chế access, ghi vault reference; đánh giá tính unique |
| **Forced-change bootstrap** | Chỉ an toàn nếu forced change thật sự enforce | Xác minh login mặc định không còn hợp lệ sau enroll |
| **Undocumented service account** | Đường quản trị/agent phụ vẫn tồn tại | Kiểm vendor support, owner/dependency và kiểm soát quyền |
| **Default/weak SNMP community** | Đọc thông tin mạng hoặc ghi cấu hình tùy cấp quyền | Tắt SNMPv1/v2c khi có thể, chuyển SNMPv3 authPriv |
| **Sample API token/PSK** | Truy cập quản trị/integration hoặc tunnel | Revoke/replace; scope, rotate và audit |
| **Default self-signed TLS certificate** | Có thể không xác minh được danh tính endpoint | Triển khai PKI được quản lý và validate peer |

**Unique per-device secret** không tự bảo đảm toàn bộ thiết bị an toàn: nếu in trên nhãn dễ tiếp cận, xuất hiện trong inventory không giới hạn quyền hoặc còn hoạt động sau chuyển chủ, vẫn phải xử lý.

### 2.3. Authentication, authorization và management reachability

Ba câu hỏi độc lập:

1. **Reachability:** từ network nào có thể đến management interface?
2. **Authentication:** principal nào có thể đăng nhập bằng password, key, token, client certificate hoặc AAA?
3. **Authorization:** sau khi xác thực, principal được phép xem/chỉnh những chức năng nào?

Đổi mật khẩu giải quyết một phần **authentication**, nhưng **không đóng một Web UI đang public Internet**, không tự sửa **admin RBAC** hoặc vô hiệu hóa API token khác. Một kiến trúc bảo vệ cần đồng thời **management VLAN/OOB, ACL/firewall, TLS/SSH, MFA/PAM, least privilege và auditing**.

~~~mermaid
flowchart LR
  U["Authorized operator"] --> PAM["PAM / MFA / identity"]
  PAM --> J["Management network\nbastion or OOB"]
  J --> IF["Device management interface\nHTTPS/SSH/console"]
  IF --> AU["Authentication\nlocal or AAA"]
  AU --> RB["Authorization\nscoped role/privilege"]
  RB --> D["Router / switch / firewall\nor managed device"]
  V["Secret vault"] -. "Scoped, audited checkout" .-> PAM
  SIEM["Audit / SIEM"] -. "Login and config events" .-> IF
  SIEM -. "Health and change correlation" .-> D
~~~

Sơ đồ minh họa cấu trúc, không giả định mọi thiết bị hỗ trợ đồng thời PAM, MFA, OOB, centralized AAA hoặc RBAC chi tiết.

### 2.4. Những thiết bị thường gặp

| Nhóm | Bề mặt quản trị | Credential cần lưu ý |
| --- | --- | --- |
| Router/switch | Console, SSH, HTTPS, SNMP, NETCONF/RESTCONF | Local admin, AAA, API/service users, SNMP, automation |
| Firewall/UTM/VPN | UI/API/SSH, VPN portal, CLI, HA | Admin, break-glass, VPN PSK/cert, API keys, HA trust |
| Wireless AP/controller | Web/controller, SSH, cloud enrollment | Local AP login, controller admin, provisioning tokens, wireless keys |
| NAS/storage | HTTPS/SSH/SMB/agent API | Admin/service accounts, backup credentials, share permissions |
| Camera/NVR/printer/IoT | Web/app/cloud onboarding, RTSP, API | Local/cloud credentials, stream accounts, installer access |
| BMC/IPMI/out-of-band | Dedicated management NIC, remote console | Local admin, directory users, virtual media, remote management |
| Hypervisor/appliance | Console/UI/SSH/API | root/admin, automation, recovery users, cluster secrets |
| DNS/DHCP/NTP appliance | Web/API/CLI, monitoring | Local admin, DNS update keys, SNMP, backup integration |
| Industrial/OT gateway | Vendor console, remote maintenance, fieldbus gateways | Service/recovery identities, remote-access credentials |
| Cloud-managed virtual appliance | SSH/API, cloud IAM, bootstrap | Appliance admin plus IAM/metadata/service principals |

**Không ép một thao tác giống nhau lên mọi sản phẩm**: một số hệ thống có per-device initial password, một số dùng controller-only login, một số không cho vô hiệu tài khoản cứu hộ. Cần đọc **vendor-specific hardening guidance** và kiểm firmware/feature trước change.

## 3. Mô hình đe dọa: một credential yếu tạo những đường nào?

### 3.1. Rủi ro khi credential chưa đổi

Một credential mặc định/được chia sẻ có thể gây:

- **Unauthorized management login** từ mạng có reachability.
- **Configuration tampering:** sửa firewall rules, NAT, VLAN, DNS, routing hoặc logging.
- **Telemetry suppression:** tắt syslog/SNMP/IDS hoặc đổi nơi gửi audit.
- **Service disruption:** reboot, disable interface, reset device, sửa authentication.
- **Lateral movement:** từ switch/AP/BMC sang các mạng hoặc hosts khác nếu quyền cho phép.
- **Exposure of sensitive configurations:** VPN keys, Wi-Fi credentials, network topology, backup settings.
- **Fleet-scale impact:** cùng credential trên nhiều thiết bị khiến một lần lộ ảnh hưởng nhiều targets.
- **Persistence/re-entry:** một account mặc định vẫn còn, dù đổi một account admin khác.
- **Supply-chain/integrator exposure:** bên thứ ba biết credential đã dùng lúc triển khai.

Khả năng khai thác phụ thuộc **reachability, firmware behavior, privileges, rate limiting, MFA, network segmentation và các kiểm soát khác**. Không kết luận thiết bị đã bị truy cập trái phép chỉ vì phát hiện một tài khoản ban đầu còn enabled; nhưng đây vẫn là **misconfiguration có thể nghiêm trọng**.

### 3.2. STRIDE ở management plane

| STRIDE | Tình huống | Biện pháp |
| --- | --- | --- |
| **Spoofing** | Người không được phép dùng shared admin password | Unique credential, MFA/PAM, AAA và management ACL |
| **Tampering** | Chỉnh policy/VLAN/DNS/config sau khi đăng nhập | Least privilege, config change review, tamper-evident audit |
| **Repudiation** | Shared admin account không quy người thực hiện | Named identities, PAM session mapping, immutable logs |
| **Information disclosure** | API/web admin đọc config chứa VPN PSK hoặc topology | Reduce rights, encrypted vault/backups, admin network isolation |
| **Denial of service** | Credential rotation khóa mất operator hoặc admin lạm dụng reboot | OOB/recovery, staged changes, approval và positive tests |
| **Elevation of privilege** | Service account có quyền full admin, default account tồn tại | Granular RBAC, command authorization, revoke unused identities |

### 3.3. Attack path nhìn từ phòng vệ

~~~mermaid
flowchart TD
  A["Management interface reachable"] --> B{"Strong identity and access controls?"}
  B -- "No / shared credential" --> R["Unauthorized access risk"]
  B -- "Yes" --> C["Named MFA/PAM or scoped local identity"]
  C --> D{"Authorized role and change?"}
  D -- "No" --> E["Deny / alert / investigate"]
  D -- "Yes" --> F["Audited configuration operation"]
  R --> G["Config/route/secret/availability impact"]
  H["Controls"] --> I["OOB/management segmentation\nunique vault secrets\nAAA and audit"]
  I -. "Reduce exposure" .-> A
  I -. "Reduce risk" .-> R
~~~

Mục đích sơ đồ là xác định **điểm kiểm soát và bằng chứng**, không hướng dẫn thử đăng nhập trái phép.

### 3.4. Mức độ ưu tiên theo tài sản

| Tài sản | Ví dụ ảnh hưởng | Thứ tự xử lý gợi ý |
| --- | --- | --- |
| Firewall/VPN Internet-facing | Thay đổi trust boundary và remote access | Rất cao |
| BMC/hypervisor/identity management | Điều khiển host/boot/virtual media, quyền sâu | Rất cao |
| Router/switch lõi và DNS/DHCP appliance | Gián đoạn nhiều services, traffic steering | Cao |
| Wireless controller/AP nhiều client | Tác động wireless access và segmentation | Cao |
| NAS/backup systems | Dữ liệu, ransomware recovery | Cao |
| Printers/cameras/IoT | Lateral movement/privacy, thường ít patch | Theo exposure, quyền và vị trí mạng |
| Thiết bị lab cô lập | Impact thấp hơn nhưng vẫn cần tiêu chuẩn | Theo chính sách lab và inventory |

Đây không phải bảng xếp hạng cứng: **một camera trực tiếp public Internet** có thể được ưu tiên hơn switch lab, hoặc một máy in kết nối mạng mật có rủi ro cao hơn network appliance cô lập.

## 4. Quy trình khám phá và kiểm kê an toàn

### 4.1. Inventory trước khi thay đổi

Tối thiểu mỗi asset cần:

| Nhóm dữ liệu | Ví dụ trường | Vì sao cần |
| --- | --- | --- |
| Danh tính tài sản | Asset ID, serial ref, model, firmware, location/zone | Tránh sửa nhầm thiết bị |
| Quản trị | Owner/team, support contract, maintenance window | Xác nhận quyền và dependency |
| Bề mặt | Management IPv4/IPv6, FQDN, console/OOB, web/SSH/API | Lập kế hoạch access/recovery |
| Credential references | Vault item IDs, account name, purpose, privilege | Không ghi raw secret trong bảng |
| Credential trạng thái | Default suspected/verified, local/AAA, enabled, last rotated | Prioritize và đo coverage |
| Hệ thống phụ thuộc | NMS, backup, config manager, automation, HA cluster | Tránh outage khi rotate |
| Security posture | MFA/AAA, ACL, TLS/SSH, SNMP, firmware, logging | Defense in depth |
| Recovery | OOB tested, backup verified, vendor procedure, rollback owner | Giảm nguy cơ lockout |
| Evidence | Change ID, auth audit refs, readback/check results | Nghiệm thu và tái kiểm |

**Vault reference** không phải credential value. Một bảng CSV/CMDB gửi khắp công ty không nên chứa mật khẩu hoặc private key.

### 4.2. Ưu tiên discovery không xâm lấn

Các nguồn đầu tiên:

1. **CMDB/asset inventory** và bàn giao triển khai.
2. **NMS/controller/cloud management** đã được tổ chức phê duyệt.
3. **Config backups/read-only API** trong phạm vi có quyền.
4. **Network topology/management VLAN mapping** và firewall inventories.
5. **PAM/secret vault records** về credential rotations.
6. **Change tickets, device onboarding records**, serial/firmware/version.
7. **Security assessment** được phê duyệt và vendor recommendations.

Không chủ động chạy **Internet-wide discovery, credential spraying, mass login checks hoặc scans từ mạng không thuộc quyền**. Nếu cần scan tài sản nội bộ, phải có **scope, thời điểm, rate limits và phương án xử lý lockout**. Phát hiện qua asset inventory vẫn cần được đối chiếu trên chính thiết bị bởi người có quyền.

### 4.3. Chỉ phân loại, không thử các mật khẩu mặc định

Một tài khoản có tên quen thuộc hoặc username phổ biến **không chứng minh password còn là default**. Ngược lại, đổi username mà giữ password yếu cũng không giải quyết rủi ro. Evidence có thể gồm:

- Onboarding record **chưa có bước rotation**.
- Vendor-managed state báo **initial credential unchanged** (nếu có chức năng).
- Approved device configuration audit/secret vault cho biết lifecycle chưa hoàn tất.
- Account vẫn enabled và không có owner hay policy phù hợp.
- Credential dùng chung trên nhiều asset theo inventory của tổ chức.

**Không cần đăng nhập thử bằng mật khẩu mặc định được đăng trên Internet**. Cách an toàn hơn là thực hiện rotation dưới phiên quản trị đã ủy quyền rồi xác minh **credential cũ không còn hợp lệ** trong quy trình test được duyệt và có giới hạn.

### 4.4. Bảng phân loại trạng thái

| Status | Ý nghĩa | Hành động |
| --- | --- | --- |
| **UNASSESSED** | Chưa biết trạng thái credential | Assign owner/discovery |
| **DEFAULT_CONFIRMED** | Nhà sản xuất/record xác nhận credential khởi tạo còn dùng | Remediate có kế hoạch |
| **SHARED_OR_WEAK** | Không nhất thiết default nhưng không đạt unique policy | Rotate và giảm scope |
| **ROTATION_PLANNED** | Có ticket, backup, OOB/recovery | Execute staged change |
| **ROTATED_UNVERIFIED** | Đã đổi nhưng chưa kiểm login/dependency/old-access | Chưa được nghiệm thu |
| **VERIFIED** | New authorized access hoạt động, old access vô hiệu theo scope | Đóng finding có evidence |
| **EXCEPTION_APPROVED** | Không thể đổi ngay vì vendor/OT limitations | Segmentation, compensating controls, expiry |
| **FAILED_LOCKOUT** | Đổi gây mất quyền/functional regression | Recover theo runbook, IR/change escalation |

Phân biệt **UNKNOWN** với **PASS**: không có trường last-changed trong CMDB không phải bằng chứng password đã thay.

## 5. Tạo credential mới: unique, đủ mạnh và có thể vận hành

### 5.1. Không thay mặc định bằng một mật khẩu dùng chung khác

Một lỗi phổ biến là đổi tất cả thiết bị từ mật khẩu nhà sản xuất sang cùng một **“mật khẩu chuẩn công ty”**. Điều này chỉ chuyển từ **vendor-shared secret** sang **organization-shared secret**, vẫn có:

- **Blast radius lớn:** rò một secret có thể ảnh hưởng cả fleet.
- **Khó quy trách nhiệm:** nhiều người và automation dùng chung một account.
- **Rotation tốn kém:** thay trên hàng trăm thiết bị đồng thời.
- **Lộ qua tích hợp:** password được nhân bản trong NMS, CI, scripts và tài liệu.
- **Khó offboard:** nhân viên/nhà thầu rời tổ chức vẫn từng biết shared secret.

Ưu tiên **per-device, per-account, per-environment unique credentials**. Khi nhiều thiết bị được quản lý bằng centralized AAA, nên dùng **named human accounts** và quyền tập trung; local break-glass passwords vẫn cần unique/scope chặt.

### 5.2. Randomness và độ dài

Credential là secret cấp quyền; nên được tạo từ **cryptographically secure random number generator (CSPRNG)** của hệ thống hoặc **enterprise password vault** có generator đáng tin. Tránh:

- Tên thiết bị, serial, model, địa điểm, hostname, tên admin.
- Ngày sinh, tên công ty, pattern lặp dễ đoán.
- Template **Company@Year!Device01**, tăng số đếm theo device.
- Copy password từ spreadsheet/clipboard history/command line logs.
- Dùng pseudo-random generator không phù hợp cho security.

Một mật khẩu **thực sự ngẫu nhiên** dài 20 ký tự từ tập 64 ký tự có không gian \(64^{20}=2^{120}\) khả năng nếu mỗi ký tự được chọn **độc lập và đều**. Đây chỉ là **minh họa entropy lý thuyết**, không bảo đảm mật khẩu do con người đặt đạt 120 bit. Một số firmware có giới hạn độ dài/ký tự và hashing yếu, nên cần **xác minh support của thiết bị và policy**.

Định hướng:

1. Tạo **unique high-entropy credential** trong vault; dùng độ dài/tập ký tự lớn nhất thiết bị hỗ trợ đáng tin.
2. Nếu phải nhập thủ công thường xuyên, cân nhắc passphrase **ngẫu nhiên** được vault sinh, không phải câu tự đặt dễ đoán.
3. Không tự giảm mạnh để “tương thích” nếu thiết bị có bug: đánh giá **firmware update, supported characters, AAA/MFA/segmentation**.
4. Ưu tiên **named identities + MFA/PAM** cho con người; mật khẩu máy quản lý qua secret store.
5. Kiểm tra **character normalization/truncation** và độ dài tối đa của firmware; tránh key bị âm thầm cắt.
6. Không đưa **generated value** vào log, ticket, repository, diagnostic dumps hay chat.

### 5.3. Password hashing của firmware không phải lúc nào cũng do admin lựa chọn

Trên thiết bị, cách lưu password có thể do vendor quyết định: hashed/salted, encrypted/reversible hoặc cơ chế riêng. Người quản trị nên:

- Chọn firmware và cấu hình hỗ trợ **không lưu plaintext** khi có lựa chọn.
- Không coi một chuỗi **obfuscated trong config** là bí mật an toàn tuyệt đối.
- Giới hạn quyền vào **running/startup configuration và backup**.
- Review vendor hardening guidance cho thuật toán/feature, không tự thay salt/hashing tại CLI không hỗ trợ.
- Bảo vệ vault và mã hóa backup độc lập với cách thiết bị lưu secret.

Một masked field trên UI không chứng minh config backup/API export không chứa secret ở dạng dùng lại được.

### 5.4. Không chia sẻ secret bằng các kênh thiếu kiểm soát

Ví dụ không nên:

~~~text
Incident chat:
  "All switches now use password = [REAL_PASSWORD]"

Deployment ticket:
  "Please paste the new firewall admin password here."

Automation command:
  cli-tool --password=[REAL_PASSWORD]
~~~

Các ví dụ chỉ có marker giả lập. **Command-line arguments** có thể bị thu qua process listings/EDR/CI logs; shell history/verbose logs còn tạo bản sao. Dùng **secret injection** qua công cụ/vendor API/vault được review, hạn chế tiết lộ giá trị cho operator và chỉ hiển thị **vault reference, rotation event ID, thành công/thất bại**.

### 5.5. Secrets manager/vault là nguồn quản lý

Một vault record nên có:

~~~yaml
device_credential_record:
  asset_id: fw-prod-east-01
  principal: local-breakglass
  secret_ref: vault://network-devices/fw-prod-east-01/local-breakglass
  secret_value_in_document: false
  purpose: emergency-console-only
  owner: network-security
  scope: device-specific
  last_rotation: "2026-11-28T05:00:00Z"
  next_review: "2027-02-28"
  checkout: just-in-time-with-approval
  auditing: enabled
  recovery_envelope: restricted
  synthetic: true
~~~

**Vault URI giả lập** và không chứa giá trị thật. Trong hệ thống thực, thiết lập **RBAC/ABAC, MFA, approvals, checkout/session audit, retention, backup/DR của vault và quyền break-glass**. Secret management thiếu recovery path có thể trở thành **single point of failure** khi mạng hoặc IdP gặp sự cố.

### 5.6. Rotate không chỉ có “thay một chuỗi”

| Loại | Vòng đời | Xác minh |
| --- | --- | --- |
| Local admin password | Change/set + login test | New authorized login works; old auth invalid |
| API token | Create scoped new → migrate client → revoke old | API permissions least privilege, old token rejected |
| SSH authorized key | Add approved key → verify → remove old key | Authorized key access, old key removed from policy |
| SSH host key | Regenerate/re-enroll **nếu rủi ro/key exposure** | Verified host identity/trust, clients updated securely |
| VPN PSK | Coordinate peer cutover + revoke old | Tunnel/auth established with new trust, old not accepted |
| SNMPv2c community | Replace and migrate monitoring, prefer SNMPv3 | Read-only monitoring works, old community rejected |
| SNMPv3 auth/privacy | Rotate user keys/passwords via supported workflow | AuthPriv succeeds, old auth no longer valid |
| TLS cert/private key | Issue/deploy/validate/revoke when needed | SAN/chain/expiry/client trust verified |
| Cloud enrollment token | Reissue/revoke through controller | Device registration correctly bound and old token invalid |

**Đổi device login password không thay SSH host key**, và thay TLS server cert không tự revoke API token. Xác định credential **đúng loại, đúng chủ thể, đúng người nhận**.

## 6. Management plane hardening đi cùng rotation

### 6.1. Mặt phẳng quản trị phải bị giới hạn đường vào

Trong kiến trúc an toàn:

~~~mermaid
flowchart LR
  OPS["Operator\nnamed identity"] --> P["PAM + MFA"]
  P --> B["Bastion / OOB\napproved management"]
  B --> ACL{"Management ACL\nsource/port"}
  ACL -- "Approved" --> D["Device UI/API/SSH\nTLS/host verification"]
  ACL -- "Unapproved" --> DENY["Deny + audit"]
  D --> RB["Role and command\nauthorization"]
  RB --> CONF["Configuration operations\nand change audit"]
  PUB["Untrusted Internet/user LAN"] -. "Blocked" .-> ACL
~~~

OOB management giúp khôi phục khi data plane bị lỗi nhưng **không tự an toàn**: vẫn phải có segmentation, identity controls và logging phù hợp.

### 6.2. Tắt dịch vụ quản trị không cần thiết

Với thiết bị hỗ trợ:

- Ưu tiên **SSH/HTTPS** có xác thực peer đúng; tắt **Telnet/HTTP plaintext** trừ ngoại lệ không thể thay thế có controls tương ứng.
- Giới hạn **web management, REST API, SSH, SNMP** chỉ trên management VLAN/OOB/bastion hoặc endpoints được duyệt.
- Tắt/khóa **demo/guest/installer accounts** sau onboarding khi vendor cho phép.
- Hạn chế **UPnP/automatic remote management, cloud-connect remote support** không cần thiết.
- Giới hạn quản trị **từ Wi-Fi client/guest VLAN** tới AP/controller.
- Tắt **network discovery protocols/service broadcasts** ở những nơi không cần, theo risk và tác động vận hành.
- Cập nhật firmware để khắc phục **authentication bypass, default credential vulnerabilities và quản lý TLS/SSH yếu**.

**Đừng thay mọi port quản trị bằng số lạ rồi coi như đã harden.** Port nonstandard có thể giảm noise nhưng không thay **authentication, ACL, TLS và patching**.

### 6.3. MFA có nơi thực thi khác nhau

Một số network devices không hỗ trợ MFA trực tiếp. Có thể thực hiện MFA tại **SSO/PAM/bastion/VPN** trước khi tới thiết bị, đồng thời dùng local break-glass account chỉ qua console/OOB khi cần. Phải xác minh:

- Remote login thực sự bị chặn nếu **PAM/IdP/MFA chưa đạt**, không có local bypass ngoài chính sách.
- MFA enforcement bao phủ **API, CLI, web UI và remote support paths** phù hợp.
- **Recovery/MFA reset** có kiểm soát để không trở thành đường yếu hơn.
- Session/account attribution theo **từng người**, không chỉ shared admin identity.

Không tự khẳng định “MFA enabled” cho device CLI khi thực tế MFA chỉ bảo vệ VPN trước đó và local device password vẫn dùng được qua một route khác.

### 6.4. Centralized AAA: TACACS+, RADIUS và local fallback

Một thiết bị có thể hỗ trợ **TACACS+ hoặc RADIUS** và cơ chế **local authentication**. Các quyết định:

| Vấn đề | Điều cần đánh giá |
| --- | --- |
| Identity | Named users, group mappings, account lifecycle |
| Authorization | TACACS+ command authorization hoặc role mapping theo vendor |
| Accounting | User/session/command audit và central log retention |
| Transport | Bảo vệ traffic AAA, shared secrets, source restrictions; phiên bản/transport theo platform |
| Availability | AAA servers redundant, routing/DNS/time sync |
| Fallback | Khi nào local fallback được phép, role/privilege nào |
| Break-glass | Vault-stored unique local credential, OOB/console scope |
| Testing | AAA success/failure, offline fallback under approved conditions |

**TACACS+ / RADIUS không đồng nghĩa mọi kết nối đều được mã hóa end-to-end theo cách nhau**; cần kiểm **vendor-specific transport/security features**, TLS-protected variants khi hỗ trợ, và policy tại management network. Một số thiết bị chỉ hỗ trợ **local fallback** khi AAA unreachable, không khi explicit reject; thiết kế phải test theo firmware thay vì tự giả định.

### 6.5. Role-based access không thay password uniqueness

Một account có quyền **read-only monitor** và một account **configuration-admin** nên tách:

- Human operators: named principal, least privilege, MFA/PAM.
- Automation: scoped API/service identity, no human shared login.
- Monitoring: read-only SNMPv3/API where possible.
- Backup/restore: đủ quyền theo chức năng, không mặc định full admin trên mọi devices.
- Break-glass: unique per-device, restricted checkout, monitored, only emergency.

Không dùng **một credential full-admin** cho backup agent, NMS polling, automation config push và operator interactive logins. Nếu credential đó lộ, blast radius rất lớn.

### 6.6. SSH/TLS peer identity cũng phải kiểm

Đổi password không đủ nếu operator không xác minh **đúng thiết bị**:

- SSH client phải validate **host key** hoặc trust management theo phương án được duyệt; không mặc định accept unknown key trong automation.
- HTTPS management cần **certificate chain/hostname** phù hợp và TLS version/cipher policy theo khả năng thiết bị.
- Nếu thiết bị dùng **self-signed certificate**, đánh giá PKI nội bộ/pinned trust có quản trị; đừng dùng **verify=false** lâu dài.
- API clients phải giới hạn **redirects và destinations**, không forward credentials sang host khác.
- Firmware upgrades có thể đổi certificate/SSH host key, cần **re-enrollment có xác minh**, không tắt verification.

**Authentication của operator và authentication của server/device là hai chiều khác nhau**; cả hai cần bảo vệ khi truyền secret qua mạng.

## 7. Preflight trước khi đổi credential: điều kiện không thể bỏ qua

### 7.1. Lập phiếu thay đổi cụ thể

~~~text
Change ID: CHG-NET-CRED-003
Assets: fw-prod-east-01, fw-prod-east-02
Credential category: local emergency administrator
Current state: initial credential still enabled (verified by asset audit)
Approved target: unique per-device vaulted credential
Management path: dedicated OOB + named PAM access
Owner: Network Security
Approver: Infrastructure Security and NOC
Window: approved maintenance interval
Dependencies: HA sync, NMS, config backup, remote support
Backup: validated and encrypted; no plaintext sharing
Recovery: console/OOB + vendor-approved process
Rollback: restricted emergency recovery, not restoring default password
Acceptance: new access works, old account/secret rejected,
            HA/session/monitoring/business traffic unaffected
~~~

Đây là phiếu ví dụ, **không chứa raw secret**. Mục tiêu rollback là **khôi phục truy cập bằng phương án an toàn**, không mặc định quay lại mật khẩu factory đã biết rộng rãi.

### 7.2. Checklist trước khi bấm Apply

1. **Xác nhận asset ID/model/firmware** đúng, interface/device name/serial không trùng.
2. **Xác nhận scope** và đang ở môi trường/thiết bị được duyệt.
3. Có **cấu hình backup đã kiểm khôi phục**, mã hóa và giới hạn quyền.
4. Có **console/OOB recovery path đã thử**; biết cách liên hệ vendor/support khi thiết bị lockout.
5. Biết **account nào sẽ thay**, có quyền nào, fallback nào, account không thể đổi/xóa nào.
6. Có **credential mới unique** trong vault, chưa ghi ngoài kênh an toàn.
7. Đã kiểm **password length/characters, vendor CLI/API behavior và firmware caveats**.
8. Biết **AAA/MFA/PAM dependencies** và active sessions.
9. Đã kiểm **NMS, SNMP, backup, automation, VPN peers, monitoring and HA** sử dụng secret nào.
10. Có **person on-call và rollback owner**, thời gian/capacity xử lý thất bại.
11. Có baseline **management reachability, log export, device health, traffic/SLO**.
12. Có test plan phân biệt **new credential works** và **old access disabled**, được phép theo lockout policy.

Nếu không có recovery path và device là single point of failure, **không thực hiện rotation bằng một phiên remote duy nhất** chỉ vì compliance deadline; phải thiết kế khôi phục/maintenance trước.

### 7.3. Thiết bị HA và cluster

Một cặp firewall hoặc wireless controllers có thể **đồng bộ cấu hình nhưng không đồng bộ local admins/passwords theo cách giống nhau**. Cần hỏi:

- Credential có **node-specific** hay **cluster-shared**?
- AAA/management access hoạt động trên **active và standby** thế nào?
- Các HA members có cùng firmware/version/role không?
- Rotation của member A có **replicate sang B** không; nếu có, được vendor chứng minh?
- OOB access đến từng member có hoạt động?
- Failover có làm một password/credential cũ được dùng lại không?
- Có **audit per-node** và readback sau thay đổi?

Không chỉ đăng nhập được active member rồi báo cả HA pair đã harden. Đặc biệt với **unique local break-glass**, phải kiểm **từng member/identity domain** theo semantics vendor.

### 7.4. Credential dependencies cần inventory

~~~mermaid
flowchart TB
  C["Device credential planned for rotation"] --> N["NMS polling / SNMP"]
  C --> B["Configuration backup"]
  C --> A["Automation / IaC controller"]
  C --> S["SIEM/syslog and telemetry"]
  C --> V["VPN / Wi-Fi / authentication peer"]
  C --> H["HA peer / DR restore"]
  C --> R["Remote support / OOB"]
  N --> T["Update scoped refs and test"]
  B --> T
  A --> T
  S --> T
  V --> T
  H --> T
  R --> T
  T --> X["Revoke old credential and verify"]
~~~

**Không phải mọi nhánh luôn sử dụng cùng secret**. Sơ đồ nhắc phải kiểm dependency; không khuyến nghị gộp tất cả hệ thống về một password mới.

### 7.5. Khi nào không thể đổi ngay?

Đối với thiết bị legacy/OT, có thể gặp:

- Vendor firmware không hỗ trợ đổi credential theo phương pháp an toàn.
- Credential dùng cho **safety-critical control** hoặc remote maintenance đã ràng buộc hợp đồng.
- Nhà cung cấp phải tham gia để đổi mà không gây gián đoạn.
- Thiết bị không có OOB/console recovery khả thi.
- Hệ thống cần firmware upgrade/replacement trước khi hỗ trợ local accounts.

Khi đó ghi **exception có phê duyệt, asset owner, expiry, compensating controls và roadmap replacement**, ví dụ management isolation, jump host/MFA, strict ACL, monitoring, physical lock, deny Internet access. **Exception không được ghi là “credential đã đổi”**.

## 8. Quy trình đổi credential an toàn trên một thiết bị

### 8.1. Tổng quan hai giai đoạn: duy trì quản trị, rồi thu hồi quyền cũ

~~~mermaid
flowchart TD
  A["Preflight: asset + backup + OOB + dependencies"] --> B["Create unique new secret\ninside approved vault"]
  B --> C{"Platform supports safe\nparallel credential transition?"}
  C -- "Có" --> D["Enroll new scoped account/key/token"]
  C -- "Không" --> E["Controlled atomic change\nwith recovery operator ready"]
  D --> F["Verify new authorized access\nand correct device/role"]
  E --> F
  F --> G{"New credential + services\nvalidated?"}
  G -- "Không" --> R["Stop rollout, diagnose and\nrecover via approved method"]
  G -- "Có" --> H["Migrate integrations\nNMS, backup, automation"]
  H --> I["Disable/revoke old account,\npassword/token/key"]
  I --> J["Verify old access rejected\nwithout unsafe lockout testing"]
  J --> K["Readback + audit + HA/OOB\nand SLO verification"]
  K --> L["Close change, retain evidence\nand review schedule"]
~~~

**Nhánh chuyển đổi song song chỉ dùng khi vendor hỗ trợ an toàn**: nếu thiết bị không cho tồn tại đồng thời hai credential, quy trình cần đổi atomically/console recovery, không tự tạo thêm admin account không có chính sách. Có thiết bị buộc đổi password của account đang dùng và invalidate session tức thời; không kỳ vọng remote session luôn sống đến cuối.

### 8.2. Bước 1 — Đảm bảo đúng thiết bị và phiên quản trị

Trước khi thay đổi:

1. Truy cập qua **management path đã phê duyệt**, tránh mạng guest/public.
2. Xác minh **host key/TLS certificate**, asset ID, serial/model, firmware và management context.
3. Xác nhận **device configuration revision** và thời gian gần nhất lưu backup.
4. Xem **local/AAA admin inventory** theo quyền read-only.
5. Kiểm khóa chức năng **account lockout, password policy, active sessions, CLI command authorization**.
6. Biết liệu thay đổi có làm ảnh hưởng **HA sync, restart management daemon hoặc reload services**.
7. Bật **central audit/session recording** mà không log secret.

Nếu thấy **identity/certificate không khớp inventory**, dừng thay đổi và xác minh out-of-band; không tiếp tục gửi password mới tới một endpoint chưa được xác thực.

### 8.3. Bước 2 — Chuẩn bị credential trong vault

Hệ thống vault hoặc password manager tạo **secret unique** gắn với **device ID, principal, privilege và environment**. Phần metadata cần có:

~~~text
Vault ref: network/prod/fw-east-01/local-admin
Secret class: device administrator password
Scope: one device / one administrative identity
Generated by: approved CSPRNG vault generator
Owner: network-security
Read access: PAM checkout with approvals
Rotation job: approved change ID
Value in ticket/logs: NEVER
~~~

Nếu vendor yêu cầu quy tắc password khác thường, ghi **ràng buộc ký tự/độ dài** nhưng không ghi nội dung secret. Không copy secret vào file tạm không mã hóa hoặc set env global kéo dài trên jump host; tuân thủ cơ chế injection được tổ chức review.

### 8.4. Bước 3 — Áp thay đổi theo phương pháp vendor hỗ trợ

Trình tự phụ thuộc thiết bị:

- **Local password đổi trực tiếp:** dùng UI/CLI/API được vendor hỗ trợ, xác nhận hành động đã persist vào running/startup config nếu phù hợp.
- **Named admin migration:** tạo identity mới với quyền cần thiết, kiểm thành công, sau đó disable/revoke account cũ theo policy.
- **API token rotation:** tạo token scoped, cập nhật clients, smoke test, revoke old token và verify rejection.
- **SNMPv3 key migration:** phối hợp NMS polling/trap endpoints, authenticate/privacy config và rollback.
- **Controller-managed credentials:** thay trong controller/vault; xác nhận subordinate devices/HA members đã nhận và không còn dùng initial credential.

Không sử dụng một đoạn **vendor CLI universal** để đổi password trên mọi thiết bị: syntax, privilege, commit/save behavior và khả năng backup khác đáng kể. Trong production cần bám **runbook cho model/firmware** đã thử tại lab cùng nguồn tin cậy.

### 8.5. Bước 4 — Positive authentication test

Sau thay:

- Dùng **phiên mới** được ủy quyền qua **đúng management interface**; không dựa vào session cũ.
- Xác nhận credential/account mới hoạt động, role đúng, không bị cấp full admin ngoài thiết kế.
- Xác minh **TLS/SSH peer identity** không bị bỏ qua.
- Kiểm **MFA/PAM/AAA policy** nếu đăng nhập qua hệ thống tập trung.
- Nếu có OOB/console riêng, xác nhận phương án recovery có thể dùng khi cần mà không lộ secret.
- Xem device audit ghi đúng **named principal/change ID** và không in password.

Một UI trả HTTP 200 không chứng minh account mới có đúng quyền quản trị; cần thử **hành động read-only/authorized** đúng mức trong test plan.

### 8.6. Bước 5 — Migrate phụ thuộc

Kiểm từng consumer:

| Consumer | Kiểm chứng sau rotation |
| --- | --- |
| NMS/monitoring | Poll/agent status, SNMP auth, timestamps, expected metrics |
| Configuration backup | Backup job hoạt động, encrypted result, success logs |
| Network automation/IaC | Read-only diff/plan và controlled operation trên target lab |
| SIEM/syslog | Authentication/config events vẫn đến collector |
| HA/cluster peers | Mỗi node/account state đúng, management access qua path riêng |
| VPN/Wi-Fi integration | Tunnel/client auth/handover theo service dependency |
| Remote support | Nhà cung cấp không còn dùng installer credential, support access theo approval |
| DR | Recovery vault/break-glass và restored image không tái sử dụng default |

**Không chỉ lấy kết quả “service UP”**: NMS có thể mất polling mà data-plane traffic vẫn chạy, backup thất bại có thể chưa tạo alarm tức thời và HA standby có thể chưa được kiểm chứng.

### 8.7. Bước 6 — Revoke quyền cũ, không chỉ đổi tên account

Sau khi đường mới được xác nhận:

1. **Disable/remove initial/installer account** nếu vendor cho phép; nếu chỉ đổi password thì account cũ vẫn tồn tại nhưng phải không còn chấp nhận secret ban đầu.
2. **Revoke old API tokens, authorized keys, SNMP communities, VPN PSK** tùy credential category.
3. Xem **active sessions/remembered tokens**: thay password có thể không chấm dứt mọi session.
4. Xóa/cập nhật **secret references trong scripts, NMS, CI, config files** theo pipeline được duyệt.
5. Đánh dấu **old vault version retired**, giới hạn retention/access theo chính sách; không giữ clipboard/file cũ.
6. Xác minh **không còn factory/installer remote access route** vô chủ.
7. Theo dõi **attempt dùng identity/secret cũ** qua audit, không tự replay hàng loạt mật khẩu cũ.

Với một account **hard-coded/immutable**, phải áp compensating controls thay vì giả vờ đã disable. Với cloud token/certificate, biết **provider revocation/TTL behavior**; có nền tảng chỉ vô hiệu token mới và session cũ còn đến khi hết hạn.

### 8.8. Bước 7 — Negative authentication test an toàn

Negative test có thể chứng minh old access bị chặn nhưng tiềm ẩn **account lockout, rate limiting, SIEM alert và audit noise**. Phương án:

- Nếu vendor hỗ trợ **readback trạng thái password changed/revoked token/account disabled**, dùng evidence này trước.
- Nếu bắt buộc thử old credential, chỉ **một phiên kiểm thử được duyệt** trên đúng asset/management path, đủ để xác minh failure mà không tạo spray/lockout.
- Không kiểm old password từ bên ngoài Internet hoặc trên các thiết bị không nằm trong scope.
- Đánh dấu test event trong SIEM bằng **change ID**, không làm nhiễu detection.
- Phân biệt **wrong password** với **network deny**: một connection timeout không chứng minh auth backend đã từ chối old credential.
- Không lưu raw old/new secret trong test report; ghi **expected denial reason, source, time, evidence ID**.

**Một thiết bị tự khóa account sau nhiều attempts** cần policy khác; có thể chỉ dùng **configuration/issuer readback và không thử password cũ trực tiếp**. Kiểm chứng theo vendor guide và risk.

### 8.9. Bước 8 — Save, readback, verify backup và audit

Sau thay:

- Readback **account enabled/status, privilege, AAA source, password policy** mà không đọc secret giá trị.
- Xác minh thay đổi được **persist qua restart/config save** theo product semantics; không reboot nếu không được phép.
- Kiểm **startup vs running config** không lệch nếu nền tảng có phân biệt.
- Xác nhận **central audit/syslog** ghi action, actor, target, result, timestamp.
- Đồng bộ inventory/vault metadata và **change ticket**.
- Nếu rotate trong HA, xác minh **per-node state**.
- Kiểm tính phục hồi của vault/backup, nhưng không export plaintext chỉ để chứng minh.

### 8.10. Rollback và recovery khi mất quyền truy cập

Mục tiêu rollback là **khôi phục quản trị mà không tái đưa credential mặc định vào sử dụng thường xuyên**:

1. **Dừng rollout** ngay khi test/monitoring fail; không tiếp tục sang fleet khác.
2. Xác minh là lỗi **identity/password**, AAA outage, network ACL, TLS trust hay controller sync.
3. Sử dụng **console/OOB/break-glass** đã chuẩn bị; không thử các default password trên thiết bị không thuộc scope.
4. Theo **vendor-supported recovery** và incident/change process; tránh factory reset nếu có thể vì có thể xóa config.
5. Nếu cần **reset device**, xác định backup integrity, downtime, HA impact, secrets/certificate loss, post-reset hardening và approval.
6. Tạo **một credential mới an toàn**, cập nhật vault/consumers; không mở rộng network management để “vào cho dễ”.
7. Chạy lại positive/negative tests, health và central audit.
8. Document failure root cause, owner và lessons learned.

Một rollback an toàn có thể là **khôi phục một version vault đã kiểm soát tạm thời** theo chính sách khẩn, nhưng không được tái dùng shared factory password lâu dài hoặc không lưu audit. Nếu không có recovery path, **escalate** chứ không brute-force.

### 8.11. Thay theo fleet: canary và blast-radius control

Không đổi hàng trăm thiết bị cùng lúc:

~~~text
Wave 0: staging / representative model and firmware
Wave 1: one low-risk production device with OOB recovery
Wave 2: one device per model/firmware/AAA profile
Wave 3: grouped rollout by site, maintenance window and dependency
Wave 4: exceptions/legacy devices with compensating controls
Wave 5: post-rollout re-audit, inventory and negative tests
~~~

Cho mỗi wave có **success criteria, fail threshold, rollback owner và monitoring window**. Đối với **HA peers**, bảo đảm rollout không mất quyền trên cả cặp cùng thời điểm. Nếu một wave tạo unexpected login failures, **dừng các waves tiếp theo** và điều tra, không tự đổi credential lần nữa hàng loạt.

## 9. Credential phụ thuộc vào hệ thống giám sát và automation

### 9.1. NMS và SNMP

NMS có thể dùng SNMPv1/v2c community hoặc SNMPv3 users để lấy metrics. Đổi credential mà không cập nhật NMS có thể khiến:

- Mất polling của interface/CPU/memory.
- Mất trap/inform notifications hoặc authentication fail.
- SIEM tưởng device offline, trong khi traffic data plane vẫn bình thường.
- NMS tự retry gây rate limiting/AAA logs lớn.
- Device load tăng do retries và auth failures.

Quy trình: phân loại **read-only vs read-write**, ưu tiên **SNMPv3 authPriv** khi hỗ trợ và phù hợp, tạo user/keys unique, cập nhật collector, kiểm metrics/traps từ nguồn được ủy quyền, thu hồi community cũ, ghi monitoring window.

**SNMPv3 authNoPriv không bảo vệ confidentiality như authPriv**. SNMPv1/v2c community strings không được truyền bảo mật mặc định, nên quản lý qua management network và migration plan; không coi chỉ “community dài” là bảo vệ tương đương.

### 9.2. Backup/config management

Config backup có thể sử dụng SSH, NETCONF, RESTCONF hoặc vendor API. Khi rotate:

- Đảm bảo **backup job principal** không cần full admin ngoài phạm vi.
- Cập nhật **vault reference** thay vì dán password vào script.
- Kiểm **scheduled run + manual safe test** có tạo backup đầy đủ đã mã hóa.
- Giữ backup trước/ sau đúng **policy scope và retention**.
- Không gửi backup chứa VPN PSK/SNMP secret vào hệ thống artifact không được phép.
- Nếu tool dùng SSH host key pinning, sửa trust khi có **device identity change được chứng thực**, không disable verification.

### 9.3. Network automation controllers

Automation có thể giữ thông tin xác thực ở nhiều nơi: inventory vars, controller credential store, runbook parameters, CI environment, vault, caches. Cần:

1. Inventory từng **consumer + credential reference**.
2. Update **secret store**, không sửa thủ công hàng trăm playbooks chứa plaintext.
3. Dùng **least-privilege automation role** và management network ACL.
4. Giới hạn **parallelism/retry** tránh lockout khi credential rotation race.
5. Chạy read-only **inventory/health validation** trước config push.
6. Kiểm **error logs** không in password.
7. Thu hồi old credential chỉ khi các clients đã migrate, trừ trường hợp secret bị lộ cần khẩn cấp.

**Automation thành công với cached session cũ chưa chứng minh credential mới hoạt động**. Phải thử **fresh authentication** bằng đúng reference mới.

### 9.4. Wi-Fi controllers, AP enrollment và PSK

Phân biệt:

- **Management administrator login:** account vào controller/AP UI.
- **Wireless client PSK (WPA2/WPA3-Personal):** key cho client kết nối SSID; đổi có thể làm ngắt hàng loạt clients.
- **Enterprise Wi-Fi identity (802.1X/EAP):** danh tính users/devices, RADIUS/PKI lifecycle.
- **Controller–AP adoption/enrollment token/certificate:** thiết bị join hệ thống quản lý.
- **Guest portal/admin/operator accounts:** quyền cấu hình/portal.

Đề bài này tập trung **credential mặc định của thiết bị**, không tự quyết định đổi mọi Wi-Fi client PSK trong cùng cửa sổ. Nếu phát hiện **default/shared PSK**, phải làm **separate controlled rotation** với client migration, site survey và rollback.

### 9.5. VPN, HA và site-to-site peer secrets

Thiết bị firewall/VPN có thể dùng:

- Admin local/AAA account.
- VPN user account/certificate.
- Site-to-site **pre-shared key** hoặc certificates.
- HA peer trust/authentication.
- API tokens cho controller/monitoring.

Những secrets này có **peer dependencies**. Một VPN PSK phải phối hợp hai đầu; đổi một đầu có thể làm tunnel down. Một HA credential có thể cần đồng bộ theo vendor; không tự áp quy trình local admin password cho VPN/HA secret.

### 9.6. Camera, printer, NAS và service protocols

Trong IoT/appliance:

- Có thể tồn tại **account cho web UI, RTSP, SMB, ONVIF, FTP, vendor cloud**, mỗi loại có quyền khác.
- Camera video stream account có thể được NVR và VMS sử dụng.
- NAS backup credential khác console admin; NAS shares và snapshots có access scope riêng.
- Printer scan-to-email/SMB credentials có thể lỗi nếu đổi mà không cập nhật.
- Vendor remote support/cloud app có **separate enrollment and tenant identity**.

Kiểm toàn bộ **protocol-specific users**; chỉ đổi web admin password không chứng minh RTSP/SMB/other API accounts đã an toàn. Hạn chế services không cần dùng và network segments.

### 9.7. BMC/IPMI và hạ tầng out-of-band

BMC là mặt phẳng quản trị có thể điều khiển **power, remote console, virtual media và firmware**, do đó credential mặc định đặc biệt rủi ro:

- BMC nên nằm trên **OOB network riêng, chặn Internet và user LAN**.
- Thay unique local credentials và named directory integration nếu có.
- Tắt những **legacy cipher/auth modes** không cần theo vendor guidance.
- Kiểm user inventory, privilege, session và virtual media permissions.
- Rotate credentials khi bàn giao ownership, thay mainboard hoặc factory reset.
- Đảm bảo **firmware update** và recovery process, không tự tắt OOB mà mất đường chữa sự cố.

**OS login trên host và BMC login là hai domain khác nhau**. Thay root password trong Linux không bảo vệ BMC mặc định.

### 9.8. OT/ICS và thiết bị legacy

Môi trường công nghiệp có ràng buộc **an toàn vật lý, uptime, vendor certification và support lifecycle**. Nếu không thể rotate ngay:

- Đánh giá **safety impact** và hợp tác owner/vender theo site procedure.
- Cô lập management network, thiết lập **jump host/MFA** và restricted maintenance access.
- Chặn unsolicited Internet/VPN access, giám sát out-of-band.
- Giữ approved backup/recovery, inventory firmware/hardware.
- Lập exception/compensating controls có thời hạn, hướng thay thế.
- Không tự thực hiện factory reset/firmware upgrade trên dây chuyền.

**Cần giữ nguyên hoạt động an toàn**: một thiết bị legacy có default credential không phải lý do để thay mật khẩu ngay trong lúc vận hành safety-critical mà không có quy trình.

## 10. Tích hợp đổi credential vào vòng đời thiết bị

### 10.1. Credential management không chỉ diễn ra một lần

Một fleet an toàn cần quy trình **procurement → receiving → provisioning → operational maintenance → incident response → transfer/RMA → decommissioning**. Mỗi giai đoạn có rủi ro và bằng chứng khác:

| Giai đoạn | Nguy cơ | Kiểm soát |
| --- | --- | --- |
| Mua/bàn giao | Vendor/installer còn shared secret | Vendor requirements, unique initial credentials, contract |
| Nhận thiết bị | Tem/serial/QR secret bị chụp hoặc lưu trong email | Chain of custody, restricted inventory |
| Provisioning/ZTP | Thiết bị dùng bootstrap account và management route rộng | Isolated staging, secure bootstrap, attest identity |
| First production login | Password default chưa được thay hoặc login từ user VLAN | Enforced change and management ACL |
| Vận hành | Credential shared/copy vào NMS scripts, owner thay đổi | Vault, PAM, role separation, auditing |
| Firmware upgrade | Account/auth behavior thay hoặc reset về initial settings | Staged testing, config/credential readback |
| HA member replacement | Node mới dùng credential khác hoặc initial | Per-member onboarding and verification |
| Incident / suspected leak | Shared secret vẫn còn, sessions hoạt động | Scoped containment, revoke/rotate, impact assessment |
| DR restore | Backup cũ chứa password/keys chưa rotate | Secure restore, post-restore credential audit |
| RMA/transfer | Thiết bị gửi vendor hoặc chuyển đơn vị với secret cũ | Secure sanitization, token/cert revocation, physical process |
| Decommission | Credentials và cloud enrolment vẫn có hiệu lực | Revoke access, delete vault references under policy, disposal record |

**Không đánh dấu một thiết bị là VERIFIED vĩnh viễn** nếu sau **factory reset, firmware recovery, controller re-enrollment hoặc DR restore** trạng thái có thể trở lại initial credential.

### 10.2. Secure bootstrap và zero-touch provisioning

Zero-touch provisioning (**ZTP**) giúp onboard nhiều thiết bị nhưng có bề mặt cần bảo vệ:

- Thiết bị kết nối mạng nào khi **chưa được cấu hình**?
- Nó xác thực **provisioning server** qua cơ chế nào?
- Bootstrap credential/token có **được cấp riêng, giới hạn scope/TTL** không?
- Firmware/image/template có **provenance/signature** theo vendor không?
- Có bảo vệ chống **rogue DHCP/DNS/provisioning endpoint** trong staging?
- Kênh triển khai có **mã hóa và xác minh peer**, không chỉ HTTPS chung chung?
- Sau bootstrap, **initial access** đã được revoke/rotate và OOB/AAA quản trị đã được cấu hình chưa?
- Logs có xác nhận **device identity, owner và final config version** không?

~~~mermaid
flowchart LR
  RECEIVE["Receive device\nasset and serial check"] --> STAGE["Isolated onboarding\nnetwork"]
  STAGE --> ATTEST["Verify provisioning endpoint\nand device identity"]
  ATTEST --> BOOT["Bootstrap from approved\nimage and config"]
  BOOT --> ROT["Generate unique credential\nstore vault reference"]
  ROT --> HARD["AAA/MFA + management ACL\nTLS/SSH + logging"]
  HARD --> V["Readback and tests\nold access removed"]
  V --> PROD["Production enrollment\nowner and lifecycle review"]
~~~

Không đặt thiết bị vừa reset có credential factory lên cùng mạng với users hoặc Internet rồi hy vọng sẽ kịp đổi nhanh. **Staging isolation** giúp ngăn truy cập trái quyền trước khi hardening hoàn tất.

### 10.3. Firmware upgrade và factory reset

Sau upgrade/reset có thể thay:

- **Password policy và chiều dài ký tự**.
- Behavior của **local admin/AAA fallback**.
- **SSH host keys/TLS certificates** và trust cần xác minh.
- Default enabled services/ports.
- Management ACL, logging, SNMP hoặc API tokens.
- Quy trình save/commit/HA sync.

Checklist sau khi thiết bị trở lại:

1. Xác minh **device identity**, firmware/version và trusted recovery source.
2. Đọc lại account inventory và trạng thái **initial/default**.
3. Đảm bảo **unique vaulted credential** và quyền đúng.
4. Bật lại MFA/PAM/AAA, ACL và peer verification.
5. Kiểm NMS/backup/automation, health và traffic.
6. Đánh dấu lại **rotation verification evidence** trong asset registry.

**Factory reset thường có thể đưa thiết bị về cấu hình mở hoặc default management access**. Chỉ thực hiện khi có vendor runbook, backup, business authorization và isolated setup.

### 10.4. RMA, thay phần cứng và chuyển chủ

Khi một appliance được trả bảo hành hoặc chuyển sở hữu:

- Bảo vệ dữ liệu/cấu hình có thể còn trong **flash/SSD/NVRAM/TPM-like storage**.
- Thực hiện **vendor-supported sanitization** theo policy, xác nhận serial/asset lifecycle.
- Revoke **cloud enrollment, device certificate, API token, VPN keys, admin account references**.
- Thu hồi asset khỏi NMS/PAM/AAA/monitoring allowlists.
- Cập nhật inventory/CMDB và link evidence, không để vault secret cũ được tái cấp cho thiết bị khác.
- Thiết bị thay thế phải **onboard mới**; không dùng chung local password chỉ vì replacement có cùng hostname.

Một **password device-specific** cũng phải được rút khỏi vòng đời khi thiết bị không còn thuộc tổ chức; không chỉ “đổi tên thiết bị trong bảng”.

### 10.5. Đánh giá lại theo risk và sự kiện

Rotation cần cả **event-driven** và **policy-based review**:

- Suspected credential disclosure, lost device, unauthorized admin access.
- Nhân sự/quản trị viên/nhà thầu rời khỏi nhóm có quyền biết secret.
- Chuyển ownership, service/vendor integration thay đổi.
- Firmware upgrade/reset/DR restore.
- Phát hiện **shared/duplicate initial credential** trên fleet.
- API token/service account quá quyền hoặc không có owner.
- Security assessment cho thấy vault access quá rộng.
- Các kỳ review/rotation theo rủi ro và chuẩn của tổ chức.

**Không khuyến nghị thay mật khẩu quá thường xuyên bằng các biến thể dễ đoán**. Với passwords được quản lý, ưu tiên **high-entropy unique secrets, MFA và event-driven rotation**; nếu tổ chức áp chính sách chu kỳ hoặc thiết bị bắt buộc, thực hiện bằng automation/vault mà không làm giảm entropy.

## 11. Xác minh sau đổi: đúng người, đúng secret, đúng đường và đúng dịch vụ

### 11.1. Xây ma trận nghiệm thu

| Lớp | Cần xác minh | Evidence |
| --- | --- | --- |
| **Asset/identity** | Đúng device và management endpoint | Device ID/serial/cert/host key |
| **Credential** | New unique secret hoạt động; old default/installer no longer accepted | Auth tests/readback/revocation event |
| **Privilege** | Account chỉ có role cần thiết | RBAC/AAA role readback, approved read-only operation |
| **Management route** | Chỉ bastion/OOB/admin VLAN được đến device | ACL/firewall/SG, positive/negative network tests |
| **Peer security** | SSH/HTTPS server identity verified | Host key/TLS certificate checks |
| **AAA/MFA/PAM** | Named identity/approval/session audit hoạt động | IdP/PAM logs, AAA responses |
| **Dependents** | NMS, backup, automation, HA/VPN/Wi-Fi vẫn hoạt động | Health, polling, backup result, peer sync |
| **Audit** | Authentication/config changes được ghi, không lộ secret | Central logs/synthetic markers |
| **Durability** | Cấu hình persist qua save/reboot/restore khi có test an toàn | Readback/startup revision/approved validation |
| **Recovery** | OOB/break-glass còn khả dụng | Recovery test theo approval |
| **Ownership** | CMDB/vault references và last-rotated đã cập nhật | Asset record/change ID |

**Một lần login thành công với secret mới chỉ kiểm một ô**, chưa nói gì về old account, monitoring, HA hoặc remote bypass.

### 11.2. Positive tests

Ví dụ:

~~~text
P01  Operator named account + PAM/MFA -> device SSH      EXPECT ALLOW
P02  Local emergency account via approved OOB            EXPECT ALLOW
P03  NMS read-only SNMPv3 poll                            EXPECT ALLOW
P04  Config backup through vault reference               EXPECT SUCCESS
P05  Automation read-only inventory/plan                 EXPECT SUCCESS
P06  HA standby management using intended account        EXPECT SUCCESS
P07  Central audit/identity events                       EXPECT RECEIVED
P08  Production data-plane business flow                 EXPECT UNCHANGED
P09  Management TLS/SSH host verification                EXPECT PASS
P10  Controlled post-restart readback (when authorized)  EXPECT PERSISTED
~~~

**P02 không yêu cầu đăng nhập OOB bằng một password shared qua mọi device**. P10 không được tự khởi động lại thiết bị production nếu chưa có change approval.

### 11.3. Negative tests

~~~text
N01  Old initial/installer credential                 EXPECT REJECTED
N02  Disabled default account                          EXPECT REJECTED
N03  Unauthorized device-management source network     EXPECT DENIED
N04  Read-only service account attempts config action  EXPECT DENIED
N05  Revoked API token                                 EXPECT REJECTED
N06  SNMP old community after migration                EXPECT REJECTED
N07  Admin login without required MFA/PAM               EXPECT DENIED
N08  Management through guest/client Wi-Fi segment      EXPECT DENIED
N09  API redirect to untrusted hostname                 EXPECT NO CREDENTIAL FORWARD
N10  Unverified SSH host key/TLS peer                    EXPECT BLOCK/REVIEW
~~~

**Không chạy N01/N02/N05/N06 thật trên production** khi có nguy cơ lockout/rate-limit hoặc khi chưa có quyền. Có thể thay bằng **issuer/account readback, test credential giả lập, vendor state API và non-invasive authorized checks**. Một **timeout** trước authentication không chứng minh password cũ bị từ chối; phân lớp **network deny vs authentication reject** trong evidence.

### 11.4. Kiểm tra persistence của cấu hình

Một số thiết bị có **running configuration, startup configuration, saved configuration hoặc controller desired state** khác nhau. Cần:

- Sau thay, **save/commit** đúng syntax vendor và verify response.
- Đọc lại account/AAA config **trên target**.
- Với controller-managed device, xem **actual delivered state** chứ không chỉ controller intent.
- Nếu firmware rollback/HA failover, xác minh initial credential **không được phục hồi**.
- Nếu cấu hình được import từ backup cũ, kiểm **credential/version drift**.
- Khi cần test restart, làm trong **maintenance/sandbox** có kế hoạch.

Một **GitOps source of truth** chứa credential reference không chứng minh thiết bị đã thực nhận key mới; cần device-specific readback và fresh auth.

### 11.5. Kiểm tra negative path ở mạng

Tạo một ma trận:

| Source | Destination | Protocol | Kỳ vọng |
| --- | --- | --- | --- |
| Bastion/OOB | Device management IP | SSH/HTTPS | Allow + authorized identity |
| NMS | Device SNMP management | SNMPv3 | Allow read-only |
| User VLAN | Device management | SSH/HTTPS | Deny |
| Guest Wi-Fi | Controller/AP management | HTTPS/SSH | Deny |
| Public Internet | Device management | Any management port | Deny |
| Unknown partner VPN | Device management | SSH/HTTPS | Deny |
| Approved CI runner | API management | Scoped TLS/API | Allow only required roles |
| IPv6 user subnet | Device IPv6 management | SSH/HTTPS | Deny unless approved |

Test phải dùng **approved vantage points** và devices thuộc quyền. Nếu device không có management IPv6, không cần ép tạo traffic; ghi feature/scope. Nếu firewall upstream deny, chỉ kết luận **end-to-end reachability denied**, không gán device local ACL đã match khi thiếu evidence.

### 11.6. Kiểm tra audit không chứa secret

Một event phù hợp:

~~~json
{
  "event_id": "device-rotation-synthetic-001",
  "event_time": "2026-11-28T05:00:00Z",
  "asset_id": "sw-core-01",
  "change_id": "CHG-NET-CRED-003",
  "principal": "network-operator-17",
  "credential_reference": "vault-ref-001",
  "operation": "local-admin-credential-rotated",
  "result": "success",
  "scope": "device-only",
  "new_login_verified": true,
  "old_auth_revoked": true,
  "monitoring_healthy": true,
  "raw_secret_logged": false,
  "synthetic": true
}
~~~

Không tự điền **old_auth_revoked=true** dựa vào **rotation requested**. Trường này cần vendor state, issuer revocation hoặc controlled negative test evidence. Cũng không nên log password hash có thể dùng offline để dò trong SIEM thông thường.

### 11.7. Tách hiệu lực credential với active session

Một số thiết bị giữ **existing interactive sessions/API tokens/cookies** sau khi password đổi:

- New password có hiệu lực cho **fresh logins**.
- Existing session có thể **vẫn còn** cho tới timeout hoặc admin revoke.
- Old API token có thể **tiếp tục hoạt động** nếu chưa explicit revoke.
- AAA cache/ticket có thể có **provider-specific expiry**.
- CLI line/vty sessions có thể cần **session revocation** theo runbook.

Trong incident, phải quyết định **có cần chấm dứt sessions hiện có ngay**. Đừng assume password rotation tức thời logout toàn bộ admin; nhưng cũng không clear toàn phiên một cách mù quáng trên device hạ tầng quan trọng.

### 11.8. Khi evidence chưa đủ

Trạng thái:

~~~text
Rotation applied: yes
New login: verified
Old local account: still enabled (status unknown)
NMS: lost polling
HA peer B: not reachable for readback
Old API token: unreviewed

Decision: NOT VERIFIED
Next action: restore safe monitoring, readback peer B,
             identify and revoke stale access.
~~~

**Đừng đóng finding** bằng một dòng “đã thay mật khẩu” nếu phụ thuộc hoặc re-entry path chưa kiểm. Có thể **giữ service vận hành tạm thời** với compensating controls và escalation, nhưng phải ghi residual risk.

## 12. Giám sát và phát hiện credential mặc định sau hardening

### 12.1. Nguồn telemetry

| Nguồn | Sự kiện hữu ích | Giới hạn |
| --- | --- | --- |
| Device AAA/auth logs | Login success/fail, account, source, protocol | Shared login attribution yếu, thời gian lệch |
| PAM/SSO/MFA | Operator, approval, session, failure | Không thấy direct local bypass ngoài PAM |
| Config change audit | Account/AAA/ACL/SSH/SNMP changes | Không tự chứng minh auth mới hoạt động |
| Secret vault | Generation/checkout/rotation/revocation refs | Không thấy device runtime nếu thiếu readback |
| NMS/SNMP | Poll failures, device reachability, metrics | NMS status có thể chậm hoặc cache |
| Backup automation | Config archive success/fail | Backup thành công không chứng minh secret cũ invalid |
| Network firewall/flow | Management network reachability/attempts | Không thấy password value/auth result |
| EDR/host logging | Runner/management client activity | Không bao phủ mọi appliance |
| Cloud/controller audit | Enrollment/API/admin account changes | Eventual consistency và policy attachment |
| CMDB/inventory | Asset owner and verification status | Có thể stale, cần correlation |

Không lưu raw credential trong SIEM để làm detection. **Vault metadata + device account state + audited change result** thường là bằng chứng có ích hơn snapshot plaintext.

### 12.2. Detection rules

| ID | Detection | Context cần |
| --- | --- | --- |
| DC-01 | New device enrolled but no credential rotation record | Asset onboarding time, policy |
| DC-02 | Default/installer account enabled past onboarding SLA | Device model, vendor support, exception |
| DC-03 | Credential reference shared among unrelated devices | Vault/inventory, HA semantics |
| DC-04 | Same privileged account across fleet without individual attribution | PAM/AAA logs |
| DC-05 | Rotation marked success, new-login test missing | Device readback/test evidence |
| DC-06 | Password rotated but old account still enabled unexpectedly | Vendor status/approval |
| DC-07 | API token continues being used after planned revocation | API/device audit and client owner |
| DC-08 | NMS SNMP auth failures immediately after rotation | Change time, NMS health |
| DC-09 | Backup job stops working after credential change | Backup automation and config |
| DC-10 | High-risk management login from unexpected source | Firewall/PAM/device auth |
| DC-11 | Login attempted outside maintenance window with stale identity | Device/PAM session logs |
| DC-12 | Device management exposed to public Internet or guest segment | Routing/firewall scan under authority |
| DC-13 | MFA/PAM disabled or local bypass expanded | AAA/config change audit |
| DC-14 | Account privilege escalated after rotation | RBAC/role audit |
| DC-15 | SNMPv1/v2c community enabled where policy forbids | Config inventory |
| DC-16 | Unknown local admin/service account appears | Per-device account diff |
| DC-17 | HA member credential status diverges | Per-member readback |
| DC-18 | Factory reset / firmware recovery restores default state | Device event + onboarding policy |
| DC-19 | Vault checkout unusual in time/scope | Vault/PAM/change ticket |
| DC-20 | Same old credential appears in CI logs/config repository | Authorized secret scanner |
| DC-21 | Remote support enrollment/token active after contract ends | Controller/vendor management audit |
| DC-22 | Device admin password expiry/rotation exception overdue | Registry/review cycle |
| DC-23 | SSH/TLS peer verification disabled in automation | Config/repo review |
| DC-24 | Logging disabled at same time as credential change | Independent audit/heartbeat |
| DC-25 | Default account reappears after DR restore | DR snapshot and post-restore audit |

**Không giả định mọi detection là compromise.** NMS failed authentication sau rotation thường là config dependency; cảnh báo cần phân biệt **availability regression** với **unauthorized login attempt**, nhưng cả hai đều cần xử lý.

### 12.3. Tương quan rotation với thất bại chức năng

~~~mermaid
flowchart LR
  A["Rotation event\nchange ID + asset"] --> C["Correlate by device,\nprincipal and time"]
  B["Vault / PAM\ncheckout + tests"] --> C
  D["NMS / backup / CI\nhealth + failure"] --> C
  E["Device auth + AAA\nand config audit"] --> C
  C --> F{"Impact and risk?"}
  F -- "Correct + all deps healthy" --> OK["Verify and close"]
  F -- "Auth denial / lockout" --> RE["Stop rollout and recover"]
  F -- "Old credential used" --> IR["Investigate stale client\nor misuse"]
  F -- "Coverage missing" --> GAP["Record unknown,\nrestore independent logging"]
~~~

Một dashboard báo 0 unauthorized logins **không có ý nghĩa** nếu device AAA logs chưa ingest hoặc firmware không gửi log. Đo **coverage** và heartbeats.

### 12.4. Metrics/SLO

- **Credential coverage:** số tài sản đã xác minh / số tài sản trong scope.
- **Unique secret coverage:** số admin credential refs thực sự per-device / số admin identities cần.
- **Overdue default accounts:** số thiết bị chưa thay ngoài onboarding window.
- **Successful rotation rate:** % changes có đầy đủ new-login/old-revoke/dependency verification.
- **Lockout/availability incidents:** số lần rotate gây mất quản trị hoặc gián đoạn.
- **Time to rotate after exposure:** từ confirmed leak tới revoke/verified new access.
- **Break-glass audit rate:** % use có incident/approval/session evidence.
- **Vault secrets without owner:** số secret records không có owner/expiry/review.
- **AAA/PAM coverage:** % human admin paths có named identity/MFA, trừ approved exceptions.
- **Monitoring health:** % devices có audit/NMS/backup sau rotation.

**Không dùng “100% passwords changed”** nếu fleet inventory thiếu IoT/BMC, credentials chia sẻ vẫn tồn tại hoặc các trường VERIFIED thiếu evidence.

### 12.5. Negative evidence có ý nghĩa khi có log source

Nếu sau rotation không còn old login attempts:

- Điều đó không tự chứng minh old secret đã invalid vì có thể chưa ai thử.
- Nếu readback cho thấy old account disabled/token revoked, confidence tăng.
- Nếu các nguồn AAA/IdP/PAM/device logs **healthy** trong time window, absence of attempts có ý nghĩa vận hành nhưng vẫn không thay verification of revocation.
- Nếu factory reset/DR restore xảy ra sau T2, trạng thái **cần kiểm lại**.

Phân biệt **không thấy hành vi lạm dụng** và **không còn cơ chế xác thực cũ**.

## 13. Lab offline: lập kế hoạch và xác minh đổi credential cho fleet giả lập

### 13.1. Mục tiêu và giới hạn

Lab tập trung vào **tư duy quản trị, điều kiện an toàn và bằng chứng**, không dùng default credentials thật:

- Tạo **inventory** và phân loại credential theo thiết bị/account.
- Xây **dependency graph** và rollout waves an toàn.
- Chỉ ra các trường hợp **đổi password xong nhưng chưa hoàn tất remediation**.
- Xác định **positive/negative tests** theo credential category.
- Tương quan **vault/checkpoint/device audit/NMS/HA**.
- Phân biệt **credential rotation applied** với **credential old access revoked**.
- Viết **runbook cho lockout, unsupported device và DR restore**.
- Nêu tình huống phải **HOLD_APPROVAL**, không “làm cho xong” bằng thay trên production.

Toàn bộ dữ liệu là **synthetic**. Không tạo tài khoản có tên phổ biến kèm password factory, không đăng nhập vào thiết bị Internet, không lưu password thật trong bài hoặc worksheet.

### 13.2. Topology mô phỏng

~~~mermaid
flowchart TB
  P["Operator + MFA/PAM"] --> O["OOB/Bastion management"]
  O --> FW["Firewall HA\nfw-east-a, fw-east-b"]
  O --> SW["Core switch\nsw-core-01"]
  O --> WL["Wireless controller\nwlc-lab-01"]
  O --> BM["Server BMC\nbmc-lab-01"]
  O --> IOT["Camera/IoT\ncam-lab-01"]
  V["Secret vault\nrefs only"] -. "Credentials per asset" .-> O
  N["NMS + config backup\nread-only integration"] --> SW
  N --> FW
  CI["Automation controller\nscoped service role"] --> FW
  SIEM["Device auth / network flow / audit"] -. "Evidence" .-> O
  SIEM -. "Evidence" .-> N
~~~

**Không mô phỏng bằng cách kết nối thiết bị thật**. Bài có thể giải trên Markdown/worksheet và tạo synthetic events offline.

### 13.3. Dữ liệu inventory

~~~yaml
lab_id: DEVICE-CRED-HARDENING-003
environment: training
devices:
  - asset_id: fw-east-a
    type: firewall
    tier: critical
    ha_group: fw-east
    credential_class: local-breakglass
    credential_status: DEFAULT_CONFIRMED
    recovery: oob-verified
    vault_ref: null
    dependencies: [ha-peer, pam, audit]
  - asset_id: fw-east-b
    type: firewall
    tier: critical
    ha_group: fw-east
    credential_class: local-breakglass
    credential_status: UNASSESSED
    recovery: oob-unknown
    vault_ref: null
    dependencies: [ha-peer, pam, audit]
  - asset_id: sw-core-01
    type: switch
    tier: high
    credential_class: snmpv2c-community
    credential_status: SHARED_OR_WEAK
    recovery: console-verified
    vault_ref: vault://lab/sw-core-01/snmp-ref
    dependencies: [nms, config-backup]
  - asset_id: wlc-lab-01
    type: wireless-controller
    tier: high
    credential_class: controller-local-admin
    credential_status: ROTATION_PLANNED
    recovery: console-verified
    vault_ref: vault://lab/wlc-lab-01/admin-ref
    dependencies: [ap-enrollment, guest-portal, audit]
  - asset_id: bmc-lab-01
    type: bmc
    tier: critical
    credential_class: local-admin
    credential_status: DEFAULT_CONFIRMED
    recovery: physical-verified
    vault_ref: null
    dependencies: [remote-console, hardware-team]
  - asset_id: cam-lab-01
    type: iot-camera
    tier: medium
    credential_class: web-ui-and-stream
    credential_status: UNASSESSED
    recovery: unknown
    vault_ref: null
    dependencies: [nvr, vms]
notes:
  - All assets and vault references are fictitious.
  - Secret values are intentionally absent.
~~~

**Không dùng vault_ref=null làm bằng chứng có default password.** Nó chỉ cho thấy inventory thiếu reference; trạng thái DEFAULT_CONFIRMED trong lab là giả định đã có nguồn đáng tin từ onboarding audit.

### 13.4. Dữ liệu change events

~~~json
[
  {"id":"L01","time":"2026-11-28T01:00:00Z","asset":"fw-east-a","event":"rotation_requested","change_id":"CHG-201","approved":true,"status":"planned"},
  {"id":"L02","time":"2026-11-28T01:05:00Z","asset":"fw-east-a","event":"local_password_changed","change_id":"CHG-201","status":"device_commit_success"},
  {"id":"L03","time":"2026-11-28T01:10:00Z","asset":"fw-east-a","event":"fresh_authorized_login","principal":"local-breakglass","result":"success"},
  {"id":"L04","time":"2026-11-28T01:12:00Z","asset":"fw-east-b","event":"rotation_skipped","reason":"oob_recovery_unverified"},
  {"id":"L05","time":"2026-11-28T01:15:00Z","asset":"sw-core-01","event":"new_snmpv3_user_configured","status":"committed"},
  {"id":"L06","time":"2026-11-28T01:20:00Z","asset":"sw-core-01","event":"nms_poll","credential":"new_snmpv3","result":"success"},
  {"id":"L07","time":"2026-11-28T01:22:00Z","asset":"sw-core-01","event":"old_snmpv2c_community","status":"still_enabled"},
  {"id":"L08","time":"2026-11-28T01:25:00Z","asset":"bmc-lab-01","event":"new_vault_secret_generated","secret_value_in_event":false},
  {"id":"L09","time":"2026-11-28T01:30:00Z","asset":"bmc-lab-01","event":"password_change_failed","reason":"unsupported_character","no_lockout":true},
  {"id":"L10","time":"2026-11-28T01:35:00Z","asset":"bmc-lab-01","event":"rotation_halted","reason":"platform_policy_review_required"},
  {"id":"L11","time":"2026-11-28T01:40:00Z","asset":"wlc-lab-01","event":"controller_admin_rotated","status":"commit_success"},
  {"id":"L12","time":"2026-11-28T01:45:00Z","asset":"wlc-lab-01","event":"ap_controller_adoption","result":"success"},
  {"id":"L13","time":"2026-11-28T01:50:00Z","asset":"cam-lab-01","event":"web_ui_password_rotated","status":"success"},
  {"id":"L14","time":"2026-11-28T01:55:00Z","asset":"cam-lab-01","event":"rtsp_service_account","status":"initial_credential_still_enabled"},
  {"id":"L15","time":"2026-11-28T02:00:00Z","asset":"fw-east-a","event":"pam_session_review","status":"old_session_not_verified"},
  {"id":"L16","time":"2026-11-28T02:05:00Z","asset":"fw-east-a","event":"config_backup_after_rotation","result":"success","secret_in_log":false},
  {"id":"L17","time":"2026-11-28T02:10:00Z","asset":"sw-core-01","event":"old_community_disabled","status":"readback_confirmed"},
  {"id":"L18","time":"2026-11-28T02:15:00Z","asset":"wlc-lab-01","event":"guest_portal_account","status":"shared_initial_credential_still_active"},
  {"id":"L19","time":"2026-11-28T02:20:00Z","asset":"fw-east-b","event":"ha_config_snapshot","credential_state":"unknown","sync_status":"healthy"},
  {"id":"L20","time":"2026-11-28T02:30:00Z","asset":"cam-lab-01","event":"nvr_stream_auth","result":"success_with_old_stream_account"},
  {"id":"L21","time":"2026-11-28T02:40:00Z","asset":"bmc-lab-01","event":"oob_management_acl","result":"restricted_to_admin_network"},
  {"id":"L22","time":"2026-11-28T02:50:00Z","asset":"fw-east-a","event":"device_audit","status":"rotation_recorded_without_plaintext"}
]
~~~

Đây là **log giả lập**, không phải output từ các sản phẩm. **L02 là commit**, L03 là fresh auth, L07 cho thấy old SNMP still enabled trước L17, còn L19 không xác nhận local credential HA node.

### 13.5. Bài tập phân loại L01–L22

| Asset | Thành công đã quan sát | Còn thiếu/không đạt | Trạng thái đề xuất |
| --- | --- | --- | --- |
| **fw-east-a** | Commit, fresh login, config backup, audit | Old session/revocation và HA peer B chưa verified | ROTATED_UNVERIFIED |
| **fw-east-b** | HA sync hiển thị healthy | OOB recovery, account credential state chưa biết | UNASSESSED / HOLD |
| **sw-core-01** | SNMPv3 + NMS polling, old community disabled readback | Kiểm SNMPv3 authPriv/role và other uses | Conditionally VERIFIED |
| **wlc-lab-01** | Controller admin đổi, AP adoption OK | Guest portal shared initial credential | PARTIAL |
| **bmc-lab-01** | New secret generated, ACL restricted | Password change failed, platform review | FAILED / EXCEPTION PENDING |
| **cam-lab-01** | Web admin đổi | RTSP/stream initial account vẫn active | PARTIAL / NOT VERIFIED |

**HA sync=healthy không tự chứng minh local admin credentials giống nhau**. **Web UI password rotated** không chứng minh camera stream account đã an toàn. **NMS poll success** không chứng minh old SNMP community đã tắt cho tới L17.

### 13.6. Thiết kế remediation wave

Giả lập:

~~~text
Wave 0 (preflight):
  Validate all assets, owners, vault, OOB and vendor limitations.

Wave 1 (low risk):
  sw-core-01: SNMPv3 authPriv migration/readback;
              old SNMPv2c community removal.

Wave 2 (application integrations):
  wlc-lab-01: identify separate guest portal account.
  cam-lab-01: migrate NVR/VMS RTSP account safely.

Wave 3 (critical):
  fw-east-a/b: verify per-member OOB and credential model;
               do not rotate both without staged recovery.

Wave 4 (vendor exception):
  bmc-lab-01: compatibility fix/firmware plan and
              compensating controls, no unsafe password retries.
~~~

Trong tổ chức thực, priority cũng phụ thuộc **Internet exposure và confirmed compromised credentials**. Một BMC default còn reachable từ Internet có thể đòi **containment ngay** dù rotation phải chờ vendor.

### 13.7. Pseudocode policy gate

~~~text
function evaluateDeviceRotation(asset, change, evidence):
    if not asset.isOwnedAndAuthorized:
        return BLOCK("ownership/scope unknown")

    if not change.hasApprovedWindowAndRecoveryOwner:
        return HOLD("change approval or recovery incomplete")

    if not evidence.backupVerified or not evidence.oobOrRecoveryPlanVerified:
        return HOLD("lockout risk not controlled")

    if not evidence.uniqueVaultSecretForAsset:
        return HOLD("new credential not unique or not secured")

    if not evidence.deviceChangeCommitted:
        return PENDING("rotation not applied")

    if not evidence.newFreshLoginVerified:
        return PENDING("new authentication not verified")

    if evidence.oldAccessStillEnabledOrUnreviewed:
        return PENDING("previous access not revoked")

    if not evidence.dependencyHealthPassed:
        return PENDING("NMS, backup, API or business impact")

    if not evidence.managementACLAndAAAValidated:
        return PENDING("management route or identity coverage")

    if not evidence.haAndDRScopeValidated:
        return PENDING("not all target devices checked")

    return VERIFIED("credential lifecycle evidence complete")
~~~

Đây là **pseudocode giáo dục**, không thay đổi thiết bị. Một triển khai thực phải phân biệt **vendor-specific readback, active sessions, HA/non-HA, user vs service identity, audit integrity và asynchronous propagation**. Không mặc định old access đã được thu hồi chỉ vì trường kiểm tra chưa có log.

### 13.8. Bộ 40 phép thử

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| T01 | Inventory asset không có owner | HOLD, assign owner |
| T02 | Credential factory còn enabled | Finding, remediation plan |
| T03 | Per-device initial secret chưa đổi | Review policy, không đánh đồng shared factory |
| T04 | Một password mới dùng cho 30 devices | Reject fleet-shared design |
| T05 | Unique vault-generated credential per device | PASS generation policy |
| T06 | Secret giá trị thật dán vào ticket | Reject; security incident/data handling |
| T07 | Device model không hỗ trợ ký tự được tạo | Adjust supported policy after review, no mass retries |
| T08 | Password change commit thành công, chưa new login | ROTATED_UNVERIFIED |
| T09 | New fresh authorized login OK | Positive test PASS |
| T10 | Old account vẫn enabled | Finding/revoke or approved exception |
| T11 | Old auth rejected sau controlled test | Evidence PASS theo layer |
| T12 | Network timeout trước auth | Không coi là old password rejection |
| T13 | Privileged shared admin vẫn dùng qua NMS | Separate service identity and least privilege |
| T14 | SNMPv3 authPriv OK, SNMPv2c vẫn enabled | Partial, revoke legacy access |
| T15 | NMS polling failed sau rotation | Stop rollout and restore dependency |
| T16 | Config backup job dùng secret cũ | Migrate vault ref; test backup |
| T17 | CI job log chứa password | Remove from logs, rotate and review exposure |
| T18 | API token mới hoạt động, token cũ còn valid | PENDING revoke |
| T19 | Local password changed, old session persists | Review session revocation policy |
| T20 | Device SSH host key không được verify | Block/review endpoint identity |
| T21 | Management UI reachable from guest Wi-Fi | Network hardening finding |
| T22 | Management access only via bastion/OOB | Positive/negative network tests |
| T23 | AAA/MFA enabled nhưng direct local bypass mở | Review access routes |
| T24 | AAA server offline, fallback behavior chưa biết | Test in sandbox, HOLD risky cutover |
| T25 | HA active admin changed, standby unverified | HOLD whole HA verification |
| T26 | HA sync healthy nhưng local accounts differ | Verify per-node separately |
| T27 | One device locked out, no OOB | Stop fleet rollout and escalate |
| T28 | Recovery dùng factory reset | Re-provision in isolated staging with vendor runbook |
| T29 | Factory reset restores default identity | Re-onboard, do not mark pre-reset status valid |
| T30 | BMC password mặc định nhưng OOB isolated | Still remediate/exception, isolation is defense |
| T31 | Camera web account đổi, RTSP account cũ | Partial, migrate stream credentials |
| T32 | Wireless controller admin đổi, SSID PSK không liên quan | Do not change PSK without separate scope |
| T33 | VPN PSK đổi một đầu, tunnel down | Planned coordinated peer recovery |
| T34 | Remote support vendor account still enabled | Scope/approval/expiry review |
| T35 | Device password rotated nhưng config startup chưa save | Verify persistence safely |
| T36 | Post-restore backup reintroduces credential cũ | Re-audit, rotate and verify |
| T37 | Read-only monitoring account has full admin | Least-privilege finding |
| T38 | Device auth collector silent during rotation | Coverage gap, no automatic PASS |
| T39 | Old secret spotted in copied inventory spreadsheet | Handle exposure; rotate, remove copies |
| T40 | All new/old/HA/dependency/ACL/audit checks pass | VERIFIED with references and owner |

Các tình huống T11/T24/T28/T33/T35 phải **mô phỏng hoặc thử tại thiết bị thuộc quyền trong maintenance đã phê duyệt**; không thực hiện credential spraying, forced lockout hoặc factory reset trên production chỉ để hoàn thành lab.

### 13.9. Mẫu evidence report

~~~json
{
  "case": "CHG-NET-CRED-003",
  "asset": "fw-east-a",
  "credential_class": "local-breakglass",
  "default_status_before": "confirmed-by-onboarding-audit",
  "new_secret_reference": "vault-ref-fw-a",
  "raw_credential_in_report": false,
  "change_event": "L02",
  "new_login_evidence": "L03",
  "old_access_rejected": "unverified",
  "ha_peer_state": "unverified",
  "backup_health": "passed",
  "audit_health": "passed",
  "status": "ROTATED_UNVERIFIED",
  "next_action": "check sessions, revoke old access and verify fw-east-b",
  "owner": "network-security",
  "synthetic": true
}
~~~

Định dạng này tập trung **reference và trạng thái kiểm chứng**. Không tự gắn **VERIFIED** khi còn old access, dependency, HA hoặc management path unknown.

### 13.10. Câu hỏi thảo luận sau lab

1. Tại sao **fw-east-a** chưa thể được nghiệm thu dù password đã đổi và login mới thành công?
2. Vì sao **fw-east-b** có HA sync healthy mà vẫn không thể coi local credential an toàn?
3. **sw-core-01** có thể được coi đã hoàn tất SNMP remediation ở mức nào, còn thiếu gì?
4. Bản **cam-lab-01** cho thấy sự khác biệt giữa **web UI admin** và **RTSP/service credential** ra sao?
5. Vì sao tạo password mới cho **bmc-lab-01** chưa đủ khi device không chấp nhận?
6. Khi NMS lỗi sau rotation, nên làm gì trước khi thay credential cho devices khác?
7. Trong báo cáo không chứa secret, bằng chứng nào chứng minh **old token revoked**?
8. Vì sao nên dùng **per-device vault references** thay vì một shared secret trong một spreadsheet?
9. Hai loại **negative tests** nào có thể làm an toàn trên network mà không cần replay factory password?
10. Khi DR restore đưa initial credential trở lại, những evidence nào phải được làm mới?

## 14. Incident response: khi credential mặc định bị lộ hoặc đã bị lạm dụng

### 14.1. Phân biệt tình trạng cấu hình và bằng chứng xâm nhập

| Mức phát hiện | Ví dụ | Kết luận có thể đưa |
| --- | --- | --- |
| **Exposure condition** | Shared factory account còn enabled, UI reachable | Có rủi ro cao; chưa có evidence bị sử dụng |
| **Suspected credential disclosure** | Password/config bị gửi vào email/CI log | Cần containment/rotation và đánh giá copies |
| **Authentication anomaly** | Login attempts từ IP không thuộc management network | Đáng điều tra, chưa chắc đăng nhập thành công |
| **Confirmed unauthorized login** | Device/PAM audit thấy principal không được phép đăng nhập thành công | Incident identity/control-plane access |
| **Confirmed unauthorized change** | Firewall/DNS/VLAN/route config thay ngoài approval | Scope/impact investigation và containment |
| **Confirmed misuse/data impact** | Resource audit chứng minh đọc secrets/exfil/traffic steering trái quyền | Full IR theo tài sản/dữ liệu bị ảnh hưởng |
| **Unknown due to telemetry gap** | Auth logs bị tắt hoặc collector mất dữ liệu | Chưa đủ evidence, không báo “không có compromise” |

Một default credential chưa đổi có thể cần remediation ưu tiên cao **ngay cả khi không có login success**; nhưng phân loại **misconfiguration** và **confirmed intrusion** phải dựa trên chứng cứ.

### 14.2. Runbook khi phát hiện thiết bị đang dùng credential mặc định

1. **Xác nhận asset ownership và phạm vi:** model, firmware, management interfaces, zones, account.
2. **Đánh giá exposure:** Internet/user VLAN/partner VPN, privilege, remote services, HA, data sensitivity.
3. **Hạn chế đường truy cập** nếu rủi ro cao: management ACL/bastion/OOB, giảm external exposure theo IR/change authority.
4. **Bảo toàn evidence** cần thiết: device/AAA/PAM logs, config snapshots đã redact, identity/route changes, event time.
5. **Xác định các credential liên quan**: local admin, installer, SNMP, API, VPN, cloud support và service accounts.
6. **Chuẩn bị vault unique secret, backup, OOB/recovery, dependencies**.
7. **Rotate/revoke** đúng loại credential qua vendor-supported flow.
8. **Kiểm fresh authorized login, old access disabled, NMS/backup/HA/business health**.
9. **Đánh giá khả năng bị sử dụng** trong exposure window bằng logs và config diff.
10. **Tăng theo dõi sau remediation**, ghi owner/risk/expiry và kết luận evidence-based.

Không dùng một đợt Internet-wide password guessing để “đánh giá exposure”; điều đó có thể không hợp pháp, gây lockout hoặc tạo hoạt động xâm nhập không cần thiết.

### 14.3. Runbook khi secret lộ trong chat/repository/log

Nếu một **active device admin password** xuất hiện ngoài secret vault:

~~~mermaid
flowchart TD
  A["Credential exposure reported"] --> B["Confirm scope/owner\nwithout copying raw secret"]
  B --> C["Restrict access / contain\nwhere risk warrants"]
  C --> D["Preserve source references\nand who could access"]
  D --> E["Generate unique replacement\nin approved vault"]
  E --> F["Rotate on affected assets\nusing approved recovery plan"]
  F --> G["Update consumers and\nrevoke old secret/sessions"]
  G --> H["Audit logins and changes\nduring exposure window"]
  H --> I["Remediate source leak\nrepo/chat/CI/backup retention"]
  I --> J["Positive/negative tests,\nmonitoring and sign-off"]
~~~

**Không paste credential vào incident ticket** để chứng minh nó đã lộ. Ghi **asset, secret class, reference, location/recipient, exposure window**, audit quyền truy cập. Việc xóa một đoạn chat hoặc log **không đảm bảo backup/index/forward copies đã xóa**; rotate/revoke là hành động cốt lõi để vô hiệu credential đã lộ.

### 14.4. Nếu phát hiện unauthorized login thành công

Một login trái phép vào management plane có thể dẫn đến thay đổi ngoài credential itself. Ngoài rotate:

- Xác định **actor/session/source/entry point** và time window.
- Kiểm **admin accounts/keys/API tokens**, local and AAA group membership.
- So **running/startup configuration** với approved baseline.
- Kiểm **firewall/NAT/DNS/VLAN/routing/VPN/ACL** thay đổi.
- Kiểm **SNMP/telemetry/exporter** không bị vô hiệu hoặc chuyển sink.
- Đánh giá **config backup, device certificates/keys, shared secrets** mà tài khoản admin có thể đọc.
- Với privileged access nghi compromise, cân nhắc **vendor-supported firmware/config recovery hoặc device re-provisioning** thay vì chỉ thay một password.
- Tìm **lateral impact** qua các thiết bị dùng shared credentials.
- Rà NMS/backup/automation/CI credentials đã từng có thể bị đọc.

**Đổi password không tự xóa một NAT rule trái phép, API token mới hoặc local admin thứ hai** được tạo trước đó. Do đó incident response phải có **config integrity verification**.

### 14.5. Blast radius khi secret chia sẻ giữa fleet

Nếu cùng installer/admin credential dùng trên nhiều devices:

1. Xác định **đúng tập assets** nhận credential đó, có owner và sensitivity.
2. **Contain high-risk management exposure** trước hoặc đồng thời với rotation.
3. Chia rollout waves theo **model, firmware, OOB readiness, HA/DR dependency**.
4. Tạo **unique replacement per device**, không thay bằng shared password khác.
5. Theo dõi **credential usage** từ NMS/backup, phân biệt legitimate clients và suspicious sources.
6. Sau rotation, kiểm **old shared credential không còn accepted** theo safe vendor controls.
7. Kiểm **factory restore/RMA/staging** không vô tình đưa lại secret cũ.
8. Audit **device config changes** trong exposure period.
9. Cập nhật CMDB/vault và offboarding of installer/vendor accounts.

Không nhất thiết **đổi tất cả devices trong cùng phút**: điều phối risk/availability và nếu confirmed exploitation cần **emergency containment** của các paths nguy hiểm trước khi cleanup hoàn tất.

### 14.6. Recovery khi đổi credential gây lockout

Một số triệu chứng:

- **Password mới bị từ chối** do giới hạn ký tự, case/encoding, truncation hoặc commit/save thất bại.
- **AAA fallback** không xảy ra như giả định.
- ACL chỉ cho phép quản trị qua một route vừa bị thay.
- PAM/MFA enrollment lỗi.
- **HA standby** không nhận cấu hình account.
- Automation retry old password khiến account bị khóa.
- Console/OOB không có nhân sự đủ quyền.

Phân biệt lỗi:

| Lớp | Dấu hiệu | Bước xác minh an toàn |
| --- | --- | --- |
| Network reachability | TCP timeout/route denied | Management ACL/route/HA/OOB status |
| Server identity | TLS/SSH host verification fails | Certificate/key/device identity, không bỏ verify |
| Authentication | Explicit login rejection | Account enabled, AAA source/password policy |
| Authorization | Login OK nhưng lệnh bị deny | Role/privilege/command authorization |
| Account lockout | Temporary auth rejection sau retries | Vendor lockout status, stop retries |
| Controller sync | Active works, standby fails | Per-member credential/readback |
| Dependency | NMS/backup fails sau rotation | Consumer vault reference and logs |

**Dừng thử password liên tục** khi nghi lockout. Không dùng factory reset làm biện pháp đầu tiên trên thiết bị lõi; **OOB/vendor recovery và change authority** phải dẫn dắt hành động.

### 14.7. Khi nào cần device re-provision thay vì chỉ password change?

Xem xét nếu:

- Privileged management access bị attacker xác nhận.
- Firmware/config integrity không còn đáng tin.
- Có unknown admin account/API key/route và không giải thích được.
- Credential mặc định nằm trong thành phần không thể đổi bằng cấu hình thường.
- Factory restore/DR backup có nguy cơ đưa lại cấu hình nhiễm.
- Security control logging bị tắt/giả mạo trong thời gian dài.
- Nhiều hệ thống cùng dùng shared secret và cannot scope blast radius.

Re-provision phải dùng **trusted firmware/image, sanitized config, unique credentials, regenerated/revoked keys theo scope, secure bootstrap và full network validation**. Không chỉ import nguyên backup cũ mà không review.

### 14.8. Evidence và attribution

Một báo cáo incident nên có:

~~~text
Case: IR-DEV-CRED-SYNTHETIC
Asset/firmware/management context: ...
Credential class (no value): local administrator
Detection: shared initial credential confirmed
Exposure: management UI reachable from a partner network
Identity events: ... (known/unknown)
Configuration changes: ... (baseline diff reference)
Containment: management ACL narrowed
Rotation: unique vault ref assigned and applied
Old access: revoked/verified/unknown
Active sessions: reviewed/unknown
Dependent services: NMS, backup, HA status ...
Security impact: confirmed/suspected/not observed
Residual risks: ... owner and due date
Recovery evidence/approver: ...
~~~

Không gọi **“attacker used the password”** chỉ vì thiết bị có default account. Khi logs thiếu, ghi **unknown** thay vì kết luận không có lạm dụng.

### 14.9. Khi nào kết thúc incident hoặc finding?

Tối thiểu:

1. **Default/shared credential không còn hiệu lực** theo vendor/account scope.
2. **Known unauthorized access paths** đã đóng hoặc được giới hạn.
3. Các **other admin accounts/tokens/keys** đã được rà nếu có evidence exposure.
4. Config integrity/unauthorized changes được đánh giá nếu cần.
5. New authorized access và **business dependencies** PASS.
6. HA/OOB/recovery được xác nhận.
7. NMS/AAA/PAM/config/audit logs có coverage.
8. Residual vendor/OT exceptions có **risk owner, expiry và compensating controls**.
9. Đặt **reopen triggers**: old credential accepted, new unauthorized account, logging disabled, factory reset, unexpected cloud remote support login.

**Finding có thể được đóng dưới trạng thái exception có phê duyệt**, nhưng trạng thái vẫn phải ghi rõ **credential chưa đổi** chứ không được báo VERIFIED.

## 15. Governance, phân quyền và chương trình hardening dài hạn

### 15.1. RACI và phân quyền trách nhiệm

| Vai trò | Trách nhiệm |
| --- | --- |
| **Device owner** | Quyết định availability, business scope, approved access |
| **Network/platform operator** | Thực thi vendor-supported change và đọc lại trạng thái |
| **Security architect/assessor** | Risk tier, IAM/MFA/PAM, segmentation và policy checks |
| **Secrets/PAM team** | Vault generation, checkout approvals, lifecycle/revocation |
| **NOC/monitoring** | NMS/backup/HA/traffic health và on-call |
| **Identity/AAA team** | TACACS+/RADIUS/SSO integration, sessions và fallback |
| **Change manager** | Maintenance window, approvals, rollback evidence |
| **Incident commander** | Emergency containment/risk acceptance khi credential lộ |
| **Vendor/OT engineer** | Safe recovery/firmware limitations khi platform đặc thù |

Một nhân sự có thể làm nhiều vai trò ở tổ chức nhỏ, nhưng **high-risk changes phải được review độc lập khi chính sách yêu cầu** và có audit đủ để quy trách nhiệm.

### 15.2. Policy theo trạng thái thay vì dựa vào lời xác nhận

Ví dụ kiểm soát:

~~~text
Policy:
  No network device enters production unless:
    owner assigned
    factory/installer identity lifecycle reviewed
    unique credential or approved central AAA is configured
    management interfaces are segmented
    recovery path documented
    vault reference exists when local secret is required
    fresh auth + old access + dependent health are validated
    logs and firmware baseline are checked

Exceptions:
    recorded with risk owner, compensating controls,
    expiry, vendor limitation and replacement plan
~~~

**Không chỉ yêu cầu tick “password changed”**; triển khai admission/provisioning gate có evidence và độc lập xác minh.

### 15.3. Tách credential domains

Mô hình:

~~~text
Human management:
  named PAM/SSO/MFA identities + scoped role

Local emergency:
  unique per-device vaulted break-glass account

Monitoring:
  read-only SNMPv3 / API identity, restricted source

Backup:
  scoped config access + encrypted backup storage

Automation:
  service credential / token with least privilege, managed TTL

Remote support:
  time-bound vendor access, explicit approval, audit

Device-to-device:
  HA/VPN/controller trust material, rotated per peer workflow
~~~

Không dùng **một root password** cho tất cả các domains. Các secrets **khác purpose** có thể cần cơ chế rotation khác và owner riêng.

### 15.4. Maturity stages

| Mức | Đặc điểm | Bước tiến |
| --- | --- | --- |
| **0 — Unknown** | Thiết bị, accounts, owner không có inventory | Asset/management discovery |
| **1 — Manual** | Đổi factory passwords khi onboard, quản lý bằng người | Vault và checklist có evidence |
| **2 — Managed** | Unique per device, CMDB, OOB và staged rotation | Dependency mapping, AAA/PAM |
| **3 — Audited** | SIEM, config readback, old-account verification | Automated drift/risk reporting |
| **4 — Lifecycle** | Event-driven rotation, ZTP/DR/RMA gates, exceptions managed | Continuous validation và asset coverage |

Mức maturity không phải certification; một fleet **IoT legacy** có thể vẫn cần ngoại lệ ở một số assets, nhưng phải có **segmentation, owner và remediation roadmap**.

### 15.5. KPI và báo cáo ban quản trị

| Chỉ số | Định nghĩa | Diễn giải đúng |
| --- | --- | --- |
| **Inventory coverage** | Số devices có owner/model/management path / tổng devices | Phụ thuộc denominator CMDB |
| **Default-credential remediation** | Số credentials default đã VERIFIED / tổng default findings | Không đếm ROTATED_UNVERIFIED |
| **Unique-secret adoption** | Số local credential refs unique / số local accounts cần | Không có plaintext trong report |
| **AAA/PAM/MFA coverage** | Named privileged sessions được kiểm soát / tổng paths | Bao gồm direct local bypass |
| **Recovery readiness** | Assets có OOB/recovery verified / critical assets | Không chỉ có tài liệu OOB |
| **Dependency success rate** | Rotations có NMS/backup/API check PASS / total | Đo availability regression |
| **Mean remediation time** | Từ finding đến verified old-access revocation | Đo theo risk class |
| **Open exceptions** | Số vendor/OT exceptions còn hạn hoặc overdue | Có owner, expiry |
| **Credential leak response time** | From disclosure to effective revocation | Cần provider-level evidence |
| **Post-reset revalidation** | Restored devices có auth audit mới / restored devices | Ngăn default quay lại |

**Không gộp "đã đổi" và "đã xác minh"**. Một thiết bị có secret mới nhưng NMS hỏng và local account cũ vẫn active chưa đạt hardening acceptance.

### 15.6. Periodic recertification

Định kỳ theo policy/tier và khi có sự kiện:

1. So **device inventory + vault refs + active admin accounts**.
2. Review **AAA local fallback, PAM/MFA path, remote support**.
3. Đối chiếu asset owner, nhân sự đã rời nhóm và access approvals.
4. Kiểm **firmware, reset/DR restore/RMA events**.
5. Xem logs về unauthorized login/account changes.
6. Đánh giá **shared secrets, stale tokens, old SNMP communities**.
7. Thử OOB/recovery theo kế hoạch được duyệt.
8. Đóng hoặc gia hạn exceptions có approval; không tự extend vĩnh viễn.

### 15.7. Tránh gây lockout hàng loạt bởi automation

Một bộ quay mật khẩu tự động phải có:

- **Per-model/firmware compatibility tests** trước.
- Rate limits, bounded retries và **stop-on-error**.
- **Staged waves** và concurrency phù hợp với HA/site.
- Không lưu password trong task args/logs.
- **Idempotency** dựa trên evidence/reference state, không resend stale secret.
- Thực thi **privilege least scope**, không dùng global admin nếu không cần.
- Human-approved fallback khi device không hỗ trợ safe dual transition.
- Device and dependent service health gates.
- Recovery/incident escalation khi partial execution.

Nếu automation mất đồng bộ giữa **vault value và device accepted secret**, cần dừng, xác minh bằng **approved recovery path**, không thử đoán nhiều candidate passwords.

## 16. Tình huống vận hành: hardening đúng nhưng không làm hỏng hệ thống

### Tình huống A — Đổi toàn bộ switch sang một password “chuẩn công ty”

Sau audit, kỹ sư thay shared factory password của 200 switch bằng một password duy nhất do nhóm đặt, rồi báo đã khắc phục 100%.

**Phân tích:** đã giảm phụ thuộc vào factory value nhưng vẫn có **fleet-shared secret**; rò một device/config hoặc một người biết secret có thể ảnh hưởng toàn bộ fleet. Cần **unique per-device or per-principal credentials** trong vault, named AAA accounts, role separation và audit. Báo **partial remediation**, không VERIFIED.

### Tình huống B — Thiết bị không có owner

Một access point tại kho vẫn hoạt động, không ai biết đội nào quản lý và không có bản ghi credential. Hệ thống inventory gắn cờ “default suspected”.

**Phân tích:** **suspected** không phải confirmed. Thu thập CMDB/controller/physical label và owner theo quy trình; cô lập management path nếu chưa rõ, tìm vendor model/firmware, lên onboarding mới. Không tự thử password phổ biến hoặc reset đang phục vụ người dùng khi không có approval.

### Tình huống C — Password mới không tương thích firmware

Vault tạo một secret đủ mạnh nhưng giao diện thiết bị legacy từ chối ký tự đặc biệt hoặc âm thầm cắt chuỗi dài. Operator tưởng commit thành công nhưng login mới thất bại.

**Phân tích:** trước rollout phải test **vendor-supported character/length behavior** trên model/firmware tương ứng. Dừng wave, dùng OOB/recovery và tạo secret mới với entropy phù hợp trong tập ký tự cho phép. Không giảm thành mật khẩu ngắn hoặc ghi secret vào ticket để “debug”.

### Tình huống D — Firewall active đổi, standby vẫn mặc định

Một firewall HA pair hoạt động bình thường nhưng local admin password mới chỉ xác nhận trên active node; standby không có console test.

**Phân tích:** **HA sync health không chứng minh local accounts được đồng bộ**, tùy firmware. Chưa nghiệm thu toàn HA. Kiểm per-member readback và OOB recovery; tránh failover production khi chưa lên lịch.

### Tình huống E — AAA bị mất kết nối khi đang rotate

Một router sử dụng centralized TACACS+ và local fallback. Trong maintenance, AAA server offline; cả named accounts và local account dự phòng không đăng nhập được như dự kiến.

**Phân tích:** xác định vendor behavior **unreachable vs explicit reject**, AAA server priorities, management ACL và break-glass. Phải thử fallback ở lab, không giả định mọi device tự fallback trong mọi lỗi. Khôi phục bằng OOB/vendor runbook, không tạo shared admin password mới.

### Tình huống F — NMS ngừng giám sát sau chuyển SNMPv3

Switch chuyển SNMPv2c sang SNMPv3 nhưng NMS vẫn dùng community cũ; monitoring dashboard báo thiết bị offline.

**Phân tích:** data plane có thể vẫn hoạt động, nhưng **telemetry coverage đã giảm**. Cập nhật NMS vault credential và SNMPv3 authPriv, xác minh polls/traps; sau đó revoke community cũ và audit. Không mở SNMPv2c ra mọi subnet để “lấy lại dữ liệu”.

### Tình huống G — SNMP community cũ còn hoạt động

Sau khi SNMPv3 poll chạy tốt, nhóm quên disable SNMPv2c community. Compliance ghi “migrated to SNMPv3”.

**Phân tích:** migration chưa đầy đủ: old access path vẫn còn. Xác minh readback và controlled retirement of legacy community; giới hạn SNMP source ACL trong khi khắc phục. Ghi trạng thái **ROTATED_UNVERIFIED** hoặc **PARTIAL**.

### Tình huống H — Thiết bị dùng chung web-admin và API token

Một NAS đã đổi UI admin password, nhưng backup integration dùng một API token chưa được review và có quyền ghi/xóa toàn bộ dữ liệu.

**Phân tích:** UI login và API token có **issuer/permission/lifecycle khác nhau**. Inventory token owner, scope, usage và rotate/revoke nếu default/shared/compromised. Không kết luận all credentials secure chỉ vì một password đã thay.

### Tình huống I — Camera đổi web login nhưng RTSP vẫn dùng credential ban đầu

Operator cập nhật web UI cho camera nhưng VMS/NVR vẫn đăng nhập stream bằng account installer. Streams tiếp tục hoạt động bình thường.

**Phân tích:** cần phân loại **web/RTSP/ONVIF/cloud enrollment** và tích hợp. Thay/thu hồi account stream có điều phối với VMS/NVR, kiểm business recording và management ACL; không tắt camera đột ngột khi đang phục vụ hệ thống an ninh vật lý.

### Tình huống J — BMC local admin mặc định nhưng OS root password đã đổi

Đội máy chủ tuyên bố đã hoàn tất hardening sau khi thay root trên Linux. BMC/iDRAC/IPMI vẫn có initial management identity qua mạng OOB.

**Phân tích:** OS và BMC là **hai control planes riêng**. BMC có quyền reboot, virtual media và console, nên cần unique credential, giới hạn OOB, firmware hardening, vault/PAM và audit. Thay OS password không đủ.

### Tình huống K — Cloud-managed AP vẫn còn local fallback

Access points được quản lý qua cloud SSO/MFA, nhưng mỗi AP có local rescue login không đổi và client VLAN có thể tới web UI.

**Phân tích:** cloud MFA không bảo vệ **direct local management route**. Giới hạn management ACL, thay unique local credentials nếu vendor hỗ trợ, kiểm cloud enrollment/tenant và recovery path.

### Tình huống L — Wi-Fi client PSK bị đổi nhầm scope

Ticket chỉ yêu cầu đổi controller admin password. Automation lại thay Wi-Fi client PSK đang được nhiều thiết bị IoT sử dụng, gây mất kết nối.

**Phân tích:** phân biệt **device administrator credentials** với **wireless client authentication keys**. Thay client PSK cần kế hoạch riêng, phân nhóm SSID, client migration/rollback và risk assessment.

### Tình huống M — VPN site-to-site tunnel down sau đổi PSK một đầu

Một firewall PSK bị lộ. Operator rotate phía local rồi quên phía peer, khiến tunnel phục vụ DR và monitoring bị mất.

**Phân tích:** PSK là **shared peer secret**, không giống local login password. Cần phối hợp peer owner và cutover/window, lưu vault an toàn, xác minh tunnel/auth và data-plane route, revoke old material. Nếu lộ nghiêm trọng, containment có thể cần ngay nhưng phải theo IR authority.

### Tình huống N — Password rotation không revoke phiên đang mở

Device admin local password được đổi; một remote support session đã mở từ trước vẫn giữ quyền admin đến khi timeout.

**Phân tích:** xác định session invalidation của firmware và chính sách **kill/revoke active sessions** khi suspected compromise. Phải có bằng chứng về sessions/remote support, không chỉ new password.

### Tình huống O — Break-glass account được lưu bằng giấy không kiểm soát

Nhóm vận hành duy trì emergency password chung trong phong bì mở được bởi nhiều nhân viên, không có audit ai sử dụng.

**Phân tích:** fallback vẫn cần, nhưng **unique per-device, seal/access logging, dual control/MFA/PAM khi thích hợp, periodic audit/rotation** quan trọng. Nếu vận hành OOB không có online vault, thiết kế **offline emergency access process** được phê duyệt, không biến nó thành shared secret vô chủ.

### Tình huống P — Remote support vendor account không hết hạn

Nhà cung cấp bàn giao hệ thống nhưng giữ installer account để hỗ trợ; sau khi hợp đồng kết thúc account vẫn enabled và portal từ Internet reachable.

**Phân tích:** xác minh support contract, owner, **time-bound privileged access**, account disable/revoke, network ACL và historical login/config audit. Không giữ quyền vendor không kiểm soát chỉ vì “có thể cần bảo hành”.

### Tình huống Q — Camera reset về mặc định sau mất điện

Một IoT appliance có lỗi firmware khôi phục cấu hình factory sau reboot, account initial hoạt động trở lại. Inventory vẫn ghi VERIFIED từ nhiều tháng trước.

**Phân tích:** kiểm **config persistence**, firmware/reset events, device enrollment và auto-remediation. Sau reset phải **re-onboard trong segment an toàn**, xác minh credential và dịch vụ quản trị. Status VERIFIED phải gắn với **last verified revision/time**, không vĩnh viễn.

### Tình huống R — Factory reset để khắc phục login fail

Operator mất quyền từ xa và quyết định reset firewall lõi ngay để lấy lại default login, không có backup/recovery window.

**Phân tích:** có thể xóa route, VPN, NAT, HA và logs, gây outage lớn. Dừng thay đổi và dùng **approved OOB/vendor recovery**. Factory reset chỉ là phương án được đánh giá đầy đủ về config/data loss, backup, downtime và post-reset hardening.

### Tình huống S — API automation dùng session cũ nên test giả thành công

Password vault đã rotate nhưng automation client còn token/session cached từ trước; integration test vẫn PASS. Khi session hết hạn, batch config backup thất bại.

**Phân tích:** test phải sử dụng **fresh auth** với new credential reference, không chỉ re-use session. Kiểm token/session lifetime và stale clients trước old access revocation.

### Tình huống T — Một người rời công ty nhưng biết shared admin

Tài khoản cá nhân đã bị offboard khỏi SSO, nhưng nhiều thiết bị vẫn có một shared local admin password cũ từng được operator biết.

**Phân tích:** offboarding phải review **shared secrets và direct local access**. Rotate unique per device với vault/PAM, chặn direct network path, chuyển sang named accounts. SSO disable không làm password local mất hiệu lực.

### Tình huống U — Device backup đưa mật khẩu vào log của CI

Config automation export backup chứa shared VPN PSK và local credential representations vào CI artifact công khai trong nội bộ.

**Phân tích:** đây là **secondary credential exposure** do security workflow. Hạn chế artifact access, xử lý retention và copies, rotate secrets liên quan theo risk, chuyển backup vào encrypted restricted vault và chỉ export redacted metadata tới SIEM.

### Tình huống V — Operator bỏ certificate verification khi script lỗi

Sau firmware update, management API certificate đổi. Script bị TLS verification error; operator đổi sang “ignore certificate validation” để rotation chạy.

**Phân tích:** có nguy cơ gửi new credential tới peer giả. Xác minh device identity, certificate chain/SAN/PKI và update trust theo quy trình. Không tắt verify để đạt ticket deadline.

### Tình huống W — Password mới trùng serial/model

Một script tạo passwords bằng cách ghép tên site, serial và năm, rồi gọi đó là unique.

**Phân tích:** unique về chuỗi **không đồng nghĩa khó đoán**. Dữ liệu serial/model có thể thu thập từ nhãn/inventory. Dùng CSPRNG/vault generator độc lập với public asset attributes.

### Tình huống X — Thiết bị OT không hỗ trợ thay credential an toàn

Thiết bị điều khiển dây chuyền yêu cầu vendor service account và đổi mật khẩu có thể ảnh hưởng an toàn hoặc chứng nhận vận hành.

**Phân tích:** không tự sửa trên production. Dùng **network isolation, tightly controlled vendor maintenance access, physical controls, monitoring, signed exception và replacement plan** với OT/safety owner. Ghi **exception approved** thay vì giả vờ đã rotate.

### Tình huống Y — HA failover kích hoạt management credential cũ

Active controller đã đổi password, standby giữ cấu hình cũ; khi failover, một admin account ban đầu có hiệu lực trở lại.

**Phân tích:** bài kiểm cần xác minh **per-device credential state và failover policy parity**, không chỉ cluster health. Test trong maintenance/DR game day; giám sát reappearance sau recovery.

### Tình huống Z — Password đã thay nhưng Web UI vẫn public Internet

Một router ở văn phòng nhỏ được cấp password rất mạnh, nhưng HTTPS management vẫn lộ trực tiếp ra Internet và firmware chưa vá lỗi nghiêm trọng.

**Phân tích:** rotation là **một lớp**. Chặn public management, dùng VPN/bastion/MFA/OOB phù hợp, cập nhật firmware và audit remote support. Password mạnh không sửa lỗ hổng authentication bypass hoặc exposed management endpoint.

### Tình huống AA — Network rule đổi khiến monitoring test báo sai

Sau rotation, NMS không nhận SNMP phản hồi vì firewall ACL vừa thu hẹp. Đội vận hành cho rằng SNMP password mới sai.

**Phân tích:** phân biệt **network reachability** với authentication. Kiểm flow/ACL/route, SNMP auth response và NMS client identity. Không mở management ACL any-any để debug; sửa đúng source/port.

### Tình huống AB — Giám sát thấy login thất bại từ automation ngay sau rotate

SIEM có hundreds of failed logins từ IP automation controller đã đăng ký, bắt đầu ngay khi operator rotate admin password.

**Phân tích:** có thể **stale credentials/config** chứ không phải brute force external; nhưng vẫn gây lockout và telemetry noise. Stop job retries, fix vault reference, validate new auth, rồi revoke old. Dùng correlation với change ID và không tự bỏ qua tất cả automation IP events.

### Tình huống AC — Device được bán/chuyển chủ nhưng vẫn gắn controller

Một AP cũ được chuyển sang đơn vị khác; credential local đã được đổi nhưng enrollment token/certificate và cloud controller tenant vẫn còn gắn với tổ chức cũ.

**Phân tích:** device transfer cần **sanitization/revocation of enrollment/trust material**, đổi owner/CMDB/vault và re-onboard dưới tenant mới. Password change đơn lẻ không đủ.

### Tình huống AD — Dashboard báo 100% vì loại thiết bị không có vault records

Báo cáo chỉ tính routers/switches có vault records, bỏ qua cameras, BMC và printers, nên hiển thị all credentials rotated.

**Phân tích:** denominator sai. Metrics phải dựa trên **inventory devices và credential types** thuộc phạm vi, báo **UNKNOWN/unassessed** và exceptions. Không dùng absence of records làm bằng chứng hoàn tất.

## 17. Checklist kiểm soát và nghiệm thu credential mặc định

### 17.1. Trước khi triển khai

- [ ] Có **asset ID, model, firmware, owner, zone, location và quản trị interface**.
- [ ] Xác minh **account/credential category**: local, AAA, SNMP, API, SSH key, VPN, certificate, remote support.
- [ ] Phân biệt **shared factory default, per-device initial, installer shared, service identity và break-glass**.
- [ ] Ghi trạng thái **confirmed/suspected/unassessed**, không tự kết luận từ username.
- [ ] Đã có **change approval, maintenance window và recovery owner**.
- [ ] Backup **đầy đủ, được bảo vệ và đã xác minh có thể dùng khôi phục**.
- [ ] Có **OOB/console/break-glass path** đủ an toàn; biết vendor recovery procedure.
- [ ] Đã kiểm **HA/DR** và semantics local credential sync.
- [ ] Đã inventory các **NMS, SNMP, backup, automation, wireless, VPN, cloud vendor, API** dependencies.
- [ ] Biết password length/character policy và firmware limitations.
- [ ] Không thực hiện internet-wide credential tests, login spraying hoặc reset không được duyệt.

### 17.2. Sinh và lưu credential mới

- [ ] Secret mới dùng **CSPRNG/vault generator**, không dựa serial/hostname/person.
- [ ] Secret **unique per-device/per-account** hoặc dùng named centralized AAA theo policy.
- [ ] Phù hợp **vendor password policy** mà vẫn đủ entropy theo tiêu chuẩn.
- [ ] Có **vault reference, owner, privilege, purpose, environment và rotation record**.
- [ ] Human admins dùng **named identity, MFA/PAM và RBAC** khi có thể.
- [ ] Monitoring/automation dùng **least-privilege service credential**, không dùng full-admin shared login.
- [ ] Local break-glass account được **giới hạn/ghi audit**, kiểm recovery và unique theo asset.
- [ ] Không đưa **secret value** vào ticket, chat, email, CI logs, scripts hoặc source repo.
- [ ] Vault có **RBAC, approvals, checkout/session logging, backup/DR** theo risk.
- [ ] Password, API token, SNMP keys, SSH keys, certs có **lifecycle riêng** và đúng owner.

### 17.3. Management plane hardening

- [ ] Device management chỉ qua **management VLAN/OOB/bastion** theo thiết kế.
- [ ] **Guest/user/public Internet** không có direct management reachability ngoài exception được duyệt.
- [ ] SSH/HTTPS được ưu tiên; **Telnet/HTTP plaintext** không được bật nếu không có lý do/controls.
- [ ] Device **TLS/SSH peer identity** được xác minh, không có verify=false lâu dài.
- [ ] **AAA/TACACS+/RADIUS** và local fallback được cấu hình theo vendor support.
- [ ] MFA/PAM thực thi ở **tất cả human admin paths được yêu cầu**, không có bypass ngoài policy.
- [ ] Local/AAA accounts có role đúng và **least privilege**.
- [ ] API/admin source allowlists giới hạn theo source/protocol/port.
- [ ] SNMPv3 authPriv được ưu tiên, SNMPv1/v2c bị loại bỏ khi có thể.
- [ ] Firmware/authentication features được review và vá theo lifecycle.
- [ ] Central audit và config change logging hoạt động, không log raw credentials.

### 17.4. Trong khi thay

- [ ] Xác minh **đúng device/firmware/HA member/account** trước hành động.
- [ ] New credential được áp bằng **vendor-supported UI/API/CLI**, trong scope approval.
- [ ] Cấu hình được **save/commit đúng cách**; event change được audit.
- [ ] Có **fresh authorized authentication** với credential mới.
- [ ] Role/authorization của principal mới đúng, không full admin bất thường.
- [ ] Automation/NMS/backup/VPN/other integrations được chuyển sang reference mới theo đúng dependencies.
- [ ] **Old account/token/key/community** được disable/revoke khi phù hợp, không chỉ đổi display name.
- [ ] Existing sessions và provider revocation/TTL được review theo incident/risk.
- [ ] Không thực hiện mass retries khi login fail, tránh lockout.
- [ ] Rollout có **canary/waves, stop-on-error** và người chịu trách nhiệm.

### 17.5. Sau khi thay

- [ ] New fresh login từ **management path được duyệt** PASS.
- [ ] Old initial/default access bị từ chối bằng **safe vendor readback/controlled test**.
- [ ] Không còn installer/guest/hidden service account trái policy.
- [ ] Local break-glass/OOB access được xác nhận trong phạm vi cần.
- [ ] NMS/SNMP polling, syslog, config backups và automation hoạt động đúng.
- [ ] Data-plane traffic, HA sync/failover readiness, Wi-Fi/VPN/other dependencies không suy giảm.
- [ ] Management ACL denial/positive tests PASS ở IPv4/IPv6 nếu trong scope.
- [ ] Running/startup/controller configuration đã được đọc lại; không còn default state.
- [ ] Vault metadata/CMDB/change record đã được cập nhật, **không raw secret**.
- [ ] Không có secret bị lộ qua automation log/config backups.
- [ ] Nếu partial/unverified, **không ghi VERIFIED**, lập action với owner/expiry.

### 17.6. Incident/exception handling

- [ ] Suspected/confirmed credential leak được đánh giá exposure window và nơi có bản sao.
- [ ] Có **containment of unauthorized management paths** khi risk cao.
- [ ] Mọi device dùng chung secret bị lộ đã được kiểm kê và xử lý theo blast radius.
- [ ] Unauthorized successful login được điều tra **config integrity, accounts, tokens, NAT/DNS/route changes**.
- [ ] Active sessions/token issuer và dependent service identities được rà.
- [ ] Nếu integrity không bảo đảm, có kế hoạch **trusted vendor re-provisioning**.
- [ ] Legacy/OT device không thể rotate có **exception, compensating controls, replacement plan và safety owner**.
- [ ] Factory reset/firmware recovery/DR restore kích hoạt **credential revalidation**.
- [ ] Mọi partial failure và lockout có **runbook, evidence, owner, recovery action**.
- [ ] Có **reopen triggers** cho old access accepted, unexpected account, vault leak, reset/re-enrollment.

### 17.7. Ma trận nghiệm thu

| Control | Evidence bắt buộc | PASS khi |
| --- | --- | --- |
| **Inventory** | Asset owner, model, account types, management surfaces | Không có credential class bị bỏ quên trong scope |
| **Uniqueness** | Vault-generated per-device refs + policy check | Không dùng shared predictable secret |
| **New identity** | Fresh authorized login và correct role | Credential mới có quyền đúng |
| **Old identity** | Disabled account/revoked token/vendor state/test | Không còn dùng default/shared old access |
| **Transport** | TLS/SSH peer, no plaintext management | Secret chỉ đi đúng verified endpoint |
| **Network isolation** | Bastion/OOB/ACL and negative tests | Unauthorized management path denied |
| **AAA/PAM/MFA** | Identity/session logs + fallback tests | Named human access có kiểm soát |
| **Dependencies** | NMS/backup/automation/VPN/Wi-Fi tests | Không gây mất monitoring/business service |
| **HA/DR** | Per-member/restore readback | Không tái hiện default khi failover/restore |
| **Auditing** | Device/Vault/PAM/CI events without secrets | Có traceability và no secondary exposure |
| **Recovery** | OOB/console, backup, vendor procedure | Có thể xử lý lockout an toàn |
| **Governance** | Change ID, owner, exception expiry, metrics | Scope/approval và follow-up rõ |

**Không được coi một dòng PASS thay cho các dòng khác**: đổi password thành công nhưng public UI còn lộ hoặc local installer account còn dùng thì hardening chưa đầy đủ. Một thiết bị legacy có exception vẫn có thể được chấp nhận rủi ro cho vận hành, nhưng report phải phân loại **EXCEPTION_APPROVED**, không ghi VERIFIED.

### 17.8. Biên bản nghiệm thu tối thiểu

~~~yaml
change_id: CHG-NET-CRED-003
asset_id: fw-east-a
credential_category: local-breakglass
change_approved: true
secret_reference: vault-ref-fw-a
raw_secret_stored_here: false
new_access_test: PASS
old_access_revoke: PENDING
session_revoke_review: PENDING
management_acl_test: PASS
ha_peer_readback: PENDING
nms_backup_health: PASS
audit_logging: PASS
overall_status: ROTATED_UNVERIFIED
owner: network-security
required_follow_up:
  - verify old sessions no longer authorize
  - verify standby credential status and recovery
synthetic: true
~~~

**Mẫu cố ý chưa VERIFIED**: nếu old access và HA còn pending, change chưa đóng về mặt security dù service không bị gián đoạn.

## 18. Bài tập thiết kế và câu hỏi ôn tập

### 18.1. Bài tập thiết kế: chương trình thay default credentials toàn tổ chức

Giả sử doanh nghiệp có:

~~~text
Production:
  10 HA firewall pairs (remote admin + VPN + API)
  80 switches/routers (SNMP, SSH, config backup)
  120 APs under 3 wireless controllers
  60 BMC management interfaces
  200 IoT cameras and 15 NVRs
  12 NAS/backup appliances
  8 isolated OT/legacy gateways

Identity and management:
  Central SSO/PAM with MFA and TACACS+/RADIUS
  Dedicated OOB/bastion network
  Vault (passwords and API token references)
  Central NMS, config backup and IaC automation
  CI and central syslog/SIEM

Current problems:
  Some devices still use installer credentials
  One shared local admin password spans multiple sites
  Several API tokens and SNMP communities have no owner
  Standby HA nodes have not been checked
  OT equipment cannot be restarted in business hours
  Camera streams rely on undocumented service accounts
~~~

**Yêu cầu thiết kế:**

1. Xây inventory có **asset owner, model/firmware, management surface, credential type, last-rotation status, dependencies và OOB**.
2. Tách **shared factory defaults, installer accounts, unique per-device initial secrets và unknowns**.
3. Đánh giá thứ tự xử lý theo **exposure, privilege, blast radius và availability**.
4. Đề xuất kiến trúc **vault/PAM/MFA/AAA + unique local emergency credentials**.
5. Thiết kế **staged rollout** theo site/model/HA pair, có stop-on-error.
6. Xây **dependency graph** SNMP/NMS/backup/automation/Wi-Fi/VPN/NVR.
7. Chọn chính sách CSPRNG/secret constraints theo vendor, tránh passwords dựa serial.
8. Nêu cách xử lý **local account vs centralized AAA** và test fallback.
9. Viết **per-device verification checklist**, không sử dụng shared test passwords.
10. Thiết kế **management ACL/segmentation**, bao gồm guest Wi-Fi, IPv4/IPv6 và OOB.
11. Đề xuất **configuration and secret backup protection** có readback/recovery.
12. Xây kế hoạch **SNMPv2c → SNMPv3 authPriv** có NMS validation.
13. Tách **controller admin** và **Wi-Fi client PSK/802.1X** thành workflows riêng.
14. Đưa kế hoạch cho **BMC/OT legacy** có vendor limitation và exception expiry.
15. Đánh giá **HA standby, DR restore, RMA/factory reset** gây default reappearance.
16. Thiết kế **SIEM monitoring** cho authentication, account changes, old token use và missing telemetry.
17. Viết **incident runbook** cho credential leak/shared secret blast radius.
18. Chọn KPI công bằng theo **toàn bộ inventory**, tách VERIFIED/PARTIAL/EXCEPTION.
19. Viết **change acceptance record** dùng references, không raw credentials.
20. Mô tả **khi nào HOLD_APPROVAL, khi nào conditional accept và khi nào VERIFIED**.

**Tiêu chí đạt:** có thể chứng minh credential mới **unique, đủ mạnh và được quản lý**, old access vô hiệu, **human/machine identities phân quyền**, management path được giới hạn, dependencies và HA/DR ổn định, có evidence không lộ secret. Không lấy “mật khẩu dài” thay cho policy toàn diện.

### 18.2. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao credential mặc định của thiết bị là rủi ro?

*Gợi ý:* Thường được chia sẻ/biết rộng, có thể mở quyền quản trị nếu interface reachable.

**Câu 2.** Factory shared password khác per-device initial secret thế nào?

*Gợi ý:* Shared có blast radius nhiều devices; per-device unique có risk về distribution/label/lifecycle nhưng không tự là shared password.

**Câu 3.** Đổi mọi thiết bị sang một password dùng chung đã đạt hardening chưa?

*Gợi ý:* Chưa. Vẫn có fleet-wide blast radius, khó quy trách nhiệm và offboarding.

**Câu 4.** CSPRNG và entropy quan trọng vì sao?

*Gợi ý:* Giảm nguy cơ đoán, không dựa tên site/serial/public attributes.

**Câu 5.** Một chuỗi unique chứa hostname và năm có thật sự khó đoán?

*Gợi ý:* Không, cấu trúc dự đoán được dù mỗi device có giá trị khác.

**Câu 6.** Vì sao password không nên được đưa vào CLI argument hay CI logs?

*Gợi ý:* Có thể lộ qua process list/shell history/artifacts/monitoring.

**Câu 7.** Vault record nên có trường gì ngoài secret value?

*Gợi ý:* Asset ID, principal, purpose, scope, owner, privilege, rotation/audit/checkout và references.

**Câu 8.** Password login, SSH host key và TLS server certificate có giống nhau?

*Gợi ý:* Không. Chúng xác thực các thực thể/chiều kết nối khác nhau, có lifecycle riêng.

**Câu 9.** SNMPv2c community có rủi ro gì?

*Gợi ý:* Không có bảo vệ confidentiality mặc định, có thể bị lạm dụng tùy quyền/community.

**Câu 10.** SNMPv3 authPriv hơn authNoPriv ở đâu?

*Gợi ý:* AuthPriv có cả xác thực và privacy/encryption phù hợp, tùy thuật toán/implementation.

**Câu 11.** Đổi web UI admin password có đủ cho camera không?

*Gợi ý:* Có thể còn RTSP/ONVIF/NVR/vendor cloud/service accounts.

**Câu 12.** BMC admin có giống OS root không?

*Gợi ý:* Không. BMC là management plane riêng có quyền điều khiển host.

**Câu 13.** Local break-glass account nên có vai trò gì?

*Gợi ý:* Truy cập emergency/recovery khi AAA lỗi, unique/scoped/controlled, không dùng hàng ngày.

**Câu 14.** Vì sao không đổi credential firewall HA pair bằng một thao tác hàng loạt khi chưa thử?

*Gợi ý:* Local credential sync/OOB/AAA có thể khác, mất quyền cả hai members.

**Câu 15.** AAA/PAM/MFA có tự bảo vệ direct local device login không?

*Gợi ý:* Chỉ khi mọi đường access được kiểm soát; direct bypass cần ACL/disable/monitor.

**Câu 16.** Đổi password có tự hủy existing admin sessions không?

*Gợi ý:* Không nhất thiết; phụ thuộc firmware/provider/session invalidation.

**Câu 17.** Vì sao một fresh login mới cần trong nghiệm thu?

*Gợi ý:* Session cũ/cached token có thể tạo thành công giả.

**Câu 18.** Old credential bị từ chối ở firewall upstream có chứng minh authentication backend reject không?

*Gợi ý:* Không. Network deny khác authentication rejection.

**Câu 19.** Negative login test cần thận trọng điều gì?

*Gợi ý:* Lockout, rate limit, SIEM noise, scope/authority, không thử hàng loạt.

**Câu 20.** Vì sao backup/OOB recovery cần trước rotation?

*Gợi ý:* Nếu login fail có đường khôi phục không cần factory reset/outage.

**Câu 21.** NMS offline sau đổi SNMP keys có phải device data plane down không?

*Gợi ý:* Chưa chắc. Có thể monitoring authentication/ACL lỗi.

**Câu 22.** Sau khi SNMPv3 hoạt động, SNMPv2c community còn enabled thì tình trạng gì?

*Gợi ý:* Chưa hoàn tất security migration, legacy path còn.

**Câu 23.** API token khác login password ở vòng đời ra sao?

*Gợi ý:* Scope/issuer/TTL/revoke riêng, có thể tồn tại song song với password.

**Câu 24.** Tại sao HTTPS management với verify=false vẫn nguy hiểm?

*Gợi ý:* Không xác thực đúng peer, secret có thể gửi tới server giả.

**Câu 25.** Vì sao thay device password không tự loại bỏ public management exposure?

*Gợi ý:* Reachability/network ACL và firmware auth bypass là lớp riêng.

**Câu 26.** Một thiết bị có account name phổ biến đã chứng minh password default chưa?

*Gợi ý:* Không; cần onboarding/vendor state/credential lifecycle evidence.

**Câu 27.** HA sync healthy có đồng nghĩa local password đã sync không?

*Gợi ý:* Không chắc; cần kiểm semantics vendor và per-node readback.

**Câu 28.** Vì sao IoT/OT legacy cần exception thay vì ép rotation lúc đang hoạt động?

*Gợi ý:* Safety/uptime/vendor certification/recovery limits; compensate và plan thay thế.

**Câu 29.** Factory reset có thể làm gì với hardening?

*Gợi ý:* Khôi phục default credential/ports/logging/ACL và xóa network config.

**Câu 30.** ZTP/secure bootstrap cần kiểm những gì?

*Gợi ý:* Device/endpoint identity, isolated staging, token scope/TTL, trusted image, credential revocation.

**Câu 31.** Nếu NMS/backup vẫn dùng password cũ, kết luận rotation thế nào?

*Gợi ý:* Dependency chưa migrate, old access có thể còn; chưa VERIFIED.

**Câu 32.** Vì sao offboarding user khỏi SSO không đủ nếu biết shared local admin?

*Gợi ý:* Local password tồn tại ngoài IdP; cần unique rotate và management ACL.

**Câu 33.** Khi phát hiện default credential, có thể kết luận attacker đã dùng nó không?

*Gợi ý:* Không. Misconfiguration/exposure khác confirmed successful unauthorized login.

**Câu 34.** Khi device admin account bị dùng trái phép, cần xem gì ngoài rotate?

*Gợi ý:* Config integrity, accounts/API tokens, routing/NAT/DNS, audit/logging và shared blast radius.

**Câu 35.** Vì sao không nên log toàn bộ device config vào SIEM?

*Gợi ý:* Có thể chứa VPN PSK, token, password hashes, keys và topology nhạy cảm.

**Câu 36.** Kết quả “0 failed login alerts” có ý nghĩa khi collector offline không?

*Gợi ý:* Không. Zero events lúc mất logging là coverage gap.

**Câu 37.** KPI nào đúng hơn “số password đã thay”?

*Gợi ý:* VERIFIED per scoped credential + old revocation + dependency/HA validation, với denominator inventory.

**Câu 38.** Đổi device credential trước khi bàn giao bảo hành đủ chưa?

*Gợi ý:* Cần sanitization, revoke enrollment/token/cert, remove from controller/vault, chain of custody.

**Câu 39.** Khi automation gây lockout nhiều thiết bị, bước đầu tiên?

*Gợi ý:* Stop rollout/retries, bảo toàn state và sử dụng approved recovery paths, không brute force.

**Câu 40.** Khi nào có thể đánh dấu device credential là VERIFIED?

*Gợi ý:* Unique/new authorized access confirmed, old access revoked, privilege/network controls, dependencies/HA/recovery/audit PASS và evidence đủ.

### 18.3. Bài tập phân tích audit sau rotation

~~~text
08:00  CHG-501 approved for fw-ha pair local emergency credentials
08:10  vault: unique replacement generated for fw-a
08:12  fw-a: local account password change committed
08:15  fw-a: fresh authorized login succeeds from OOB
08:17  fw-b: HA sync shows healthy, local account state unknown
08:20  NMS: polls to fw-a successful
08:22  backup: config backup successful, secret value not in logs
08:30  PAM: old privileged session remains open on fw-a
08:40  fw-a: management HTTPS reachable from guest segment
08:45  automation: still using a separate privileged API token
08:50  SIEM: central log collector receives 0 events, heartbeat offline
09:00  Change owner requests VERIFIED and closure
~~~

**Yêu cầu:**

1. Ghi **ba bằng chứng** cho thấy một phần rotation đã thành công.
2. Giải thích vì sao **HA healthy** không đủ để kết luận fw-b đã đổi local secret.
3. Phân loại **old privileged session** còn mở theo security exposure và vendor revocation behavior.
4. Vì sao **guest-segment management HTTPS reachable** vẫn là finding dù password mạnh?
5. Có cần migrate API token ở 08:45 không nếu ticket chỉ gồm local emergency credential? Khi nào cần mở rộng scope?
6. Tình trạng SIEM heartbeat 08:50 thay đổi **evidence confidence** thế nào?
7. Phân biệt **ROTATED_UNVERIFIED** và **VERIFIED** ở 09:00.
8. Xây plan ba bước có owner/approval để đóng các gaps mà không gây HA lockout.
9. Đề xuất positive/negative tests **không dùng password factory trên mạng ngoài quyền**.
10. Viết báo cáo ngắn gồm **facts, remaining risks, next actions và expected acceptance evidence**.

**Đáp án định hướng:** credential mới của fw-a đã được apply và fresh login thành công; NMS và backup PASS. Tuy nhiên **fw-b local account chưa được xác minh, old session còn, guest-network management exposure, privileged API token chưa được kiểm scope và SIEM offline**. Không thể đánh dấu toàn HA **VERIFIED**. Cần **per-member readback, session/management ACL review, API access classification, restored logging** rồi re-test.

### 18.4. Bài tập so sánh hai kế hoạch remediation

**Phương án 1:** tạo một password rất dài nhưng dùng chung tất cả switches, chạy một script rotate toàn bộ vào ban đêm, không có OOB recovery, NMS vẫn dùng account admin, đánh dấu success khi CLI trả 0.

**Phương án 2:** inventory assets và consumers, tạo vault secrets riêng, chạy theo models/waves, kiểm OOB/backup, rotate qua vendor-supported procedure, dùng named AAA/PAM cho human admins, tách NMS role, đọc lại device/HA state, migrate automation, revoke old access, kiểm business flow và audit.

Phân tích theo **blast radius, traceability, entropy, recovery, dependency, approval, verification và residual risk**. Phương án 2 có chi phí chuẩn bị cao hơn nhưng cho **security outcome kiểm chứng được**, giảm nguy cơ lockout hàng loạt và giúp kiểm soát vòng đời. Không phải mọi tính năng AAA/MFA đều hiện hữu trên tất cả thiết bị; cần **documented exceptions/compensating controls**.

## 19. Tổng kết

- **Đổi credential mặc định là bước hardening bắt buộc theo rủi ro**, nhưng không đồng nghĩa chỉ đổi một mật khẩu. Phải hiểu **factory shared, per-device initial, installer, service, API token, SNMP, SSH key, VPN PSK, TLS/cert và recovery identities** với vòng đời riêng.
- **Shared default password không nên được thay bằng shared company password**. Ưu tiên **unique high-entropy secrets được tạo bằng CSPRNG, lưu trong vault**, gắn owner, scope, audit và rotation record.
- **Authentication, authorization và network reachability là ba lớp khác nhau**: password mạnh không đóng public management interface, không sửa admin privilege và không tự cập nhật firmware có auth bypass.
- **Management VLAN/OOB/bastion, MFA/PAM, named AAA identities, least privilege, SSH/TLS peer validation, logging và segmentation** giúp bảo vệ trước và sau rotation.
- **Đổi an toàn phải có preflight:** đúng device/firmware, backup, OOB/recovery, rollback owner, window, HA behavior và dependency inventory; nếu thiếu recovery path, **không đổi mù trên production**.
- **Staged rotation** bắt đầu bằng unique vault credential, áp qua vendor-supported method, xác minh **fresh authorized login**, migrate NMS/backup/API/Wi-Fi/VPN integrations và **revoke old accounts/tokens/sessions** theo support của nền tảng.
- **Positive test không thay negative test**. Một login mới thành công không chứng minh old credential đã vô hiệu; một network timeout trước authentication cũng không chứng minh password cũ đã bị backend từ chối.
- **HA/DR và reset/re-provisioning** phải được kiểm tra per-device: standby, factory restore, firmware upgrade, zero-touch provisioning và vendor support có thể đưa credential ban đầu trở lại.
- **IoT, BMC và OT** thường có mặt phẳng quản trị/credential phụ khác hoặc ràng buộc an toàn; cần inventory web/RTSP/controller/BMC, có vendor workflow và exception được duyệt nếu không thể thay ngay.
- **Credential leak hoặc unauthorized management login** cần đánh giá **config integrity, routing/NAT/DNS/firewall changes, các account/keys khác và shared fleet blast radius**, không chỉ reset password.
- **Giám sát sau rotation** phải kết hợp **device auth/config audit, PAM, vault, NMS, backup, management firewall và collector health**; không thấy alert khi collector offline không phải an toàn.
- **Nghiệm thu cần evidence per credential/asset**: đã loại bỏ default access, new access hoạt động, quyền/management routes đúng, phụ thuộc không lỗi, OOB/HA khả dụng, có audit và owner. Những mục chưa kiểm phải giữ **ROTATED_UNVERIFIED hoặc EXCEPTION_APPROVED**, không tô thành VERIFIED.
- Mục tiêu cuối cùng không phải **“100% đã bấm nút đổi password”** mà là **không còn cơ chế truy cập quản trị ban đầu không được phép, credential có quản lý và thu hồi được, cấu hình hạ tầng không mất khả dụng, và trạng thái bảo mật luôn kiểm chứng được qua suốt vòng đời thiết bị**.
