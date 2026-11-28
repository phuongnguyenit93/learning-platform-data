# Migrate từ VPN truyền thống sang ZTNA

**Chuyển đổi từ VPN truyền thống sang Zero Trust Network Access (ZTNA)** là quá trình thay đổi cách cấp quyền truy cập từ xa: thay vì mặc định đưa thiết bị vào một vùng mạng qua đường hầm rồi dựa nhiều vào địa chỉ IP, route và firewall, tổ chức hướng tới **cấp quyền theo danh tính, ngữ cảnh và từng ứng dụng/tài nguyên được phê duyệt**. Mục tiêu không chỉ là thay một phần mềm VPN bằng một phần mềm ZTNA; phải thiết kế lại **điểm thực thi chính sách, danh mục ứng dụng, tài khoản, trạng thái thiết bị, giám sát và khả năng thu hồi truy cập**.

Ví dụ một nhà thầu chỉ cần truy cập cổng quản trị đơn hàng. Với VPN kiểu truy cập mạng, thiết bị có thể nhận route đến cả subnet chứa cổng quản trị, database và các máy khác, dù firewall vẫn có thể giới hạn thêm. Với ZTNA được thiết kế đúng, chính sách có thể chỉ cho **nhà thầu đã xác thực mạnh, dùng thiết bị đáp ứng yêu cầu, truy cập ứng dụng quản trị đã chỉ định** trong khoảng thời gian được phê duyệt. Những cổng khác không tự trở nên có thể truy cập chỉ vì người này đã đăng nhập.

Tuy nhiên **ZTNA không phải giải pháp thần kỳ**. Một phiên đã được cấp quyền vẫn có thể bị lạm dụng; ứng dụng cũ dùng UDP broadcast, SMB đa cổng, Kerberos hay IP hardcode có thể không phù hợp với một connector ZTNA chỉ proxy HTTP/TCP. Truy cập từ máy chủ đến máy chủ, quản trị hạ tầng, ứng cứu khi IdP gặp sự cố và yêu cầu hoạt động ngoại tuyến có thể cần mô hình riêng hoặc duy trì VPN/IPsec trong giai đoạn dài.

Trong chương **Zero Trust Network Access** của module **SECURITY_NETWORK_SECURITY**, bài học này liên kết với phân đoạn mạng, VPN, firewall, TLS/PKI, DNS, IAM, bảo vệ cloud/Kubernetes và IDS/IPS. Nội dung tập trung vào **kiến trúc, lộ trình migration, phương pháp kiểm chứng và giảm rủi ro**, không giới thiệu một sản phẩm làm đáp án cho mọi hệ thống.

> **Nguyên tắc cốt lõi:** **Được kết nối không đồng nghĩa được phép truy cập tất cả.** Quyền phải được quyết định theo **chủ thể – thiết bị – ứng dụng – hành động – ngữ cảnh – thời điểm**, được thực thi ở điểm có thể kiểm soát và được kiểm tra lại trong suốt vòng đời truy cập theo năng lực hệ thống.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **VPN kết nối mạng**, VPN có phân đoạn chặt và **ZTNA theo ứng dụng**, không coi mọi VPN đều tự động là flat network.
2. Giải thích mô hình **Policy Engine (PE), Policy Administrator (PA), Policy Enforcement Point (PEP)** trong kiến trúc Zero Trust và cách các vai trò này được hiện thực bằng broker, gateway, agent hoặc connector.
3. Kiểm kê **user groups, thiết bị, VPN routes, DNS, ứng dụng, protocol, dependencies** và các đường truy cập đặc quyền trước khi migration.
4. Thiết kế policy theo **least privilege**, định danh nguồn, trạng thái thiết bị, MFA, rủi ro, ứng dụng, port và thời hạn.
5. Phân biệt **access broker, endpoint agent, clientless browser access, private application connector**, direct path và relay/proxy path.
6. Đánh giá các hạn chế với **SSH/RDP, database, SMB, VoIP/UDP, Kerberos, LDAP, ứng dụng có IP hardcode** và ứng dụng nhiều cổng động.
7. Giải quyết **DNS split-horizon, private zones, certificate hostname, TLS validation, proxy và route bypass** trong giai đoạn VPN và ZTNA cùng tồn tại.
8. Thiết kế **identity lifecycle, workload/service identities, posture signals, session revocation, break-glass access** và quy trình ứng cứu.
9. Triển khai **pilot, canary, wave migration, rollback** có tiêu chí rõ ràng, không cắt VPN trước khi đo được luồng nghiệp vụ quan trọng.
10. Xây dựng **log correlation, kiểm thử positive/negative, chỉ số hiệu quả và runbook** khi chuyển đổi gây outage hoặc lộ truy cập.

## 2. VPN và ZTNA giải quyết bài toán khác nhau ở đâu?

### 2.1. VPN truyền thống

**Virtual Private Network (VPN)** tạo kết nối bảo vệ lưu lượng giữa các điểm, ví dụ thiết bị nhân viên và VPN gateway, bằng các giao thức/cơ chế như IPsec hoặc TLS-based VPN tùy sản phẩm. Sau khi kết nối, client thường được cấp **địa chỉ ảo, route và DNS settings** hoặc khả năng gửi traffic qua gateway. Khả năng truy cập đến từng hệ thống tiếp tục do **firewall, ACL, chính sách VPN, xác thực hệ thống đích và ứng dụng** quyết định.

Không nên phát biểu **“VPN luôn cấp toàn bộ mạng”**. Nhiều VPN có thể dùng **per-user ACL, segmented pools, MFA, posture checks, microsegmentation và application-specific portal**. Điều cần đánh giá là **effective reachability**, không phải nhãn sản phẩm.

### 2.2. ZTNA

**ZTNA** là cách tổ chức quyền truy cập tới **ứng dụng hoặc dịch vụ được xác định**, dựa trên chính sách Zero Trust. Người dùng không nhất thiết được đưa vào cùng subnet với ứng dụng; một điểm thực thi có thể chỉ chuyển tiếp kết nối tới **đúng FQDN, service/port hoặc ứng dụng** được phép.

ZTNA thường có:

- **Identity provider (IdP)** và xác thực mạnh.
- **Policy decision** dựa trên user, group, thiết bị, ứng dụng và bối cảnh.
- **Policy enforcement** tại endpoint, broker, gateway hoặc connector theo triển khai.
- **Private application connectors** mở đường đến backend theo phạm vi hẹp, có thể thiết lập kết nối outbound tới broker.
- **Observability và access review** để đánh giá ai truy cập tài nguyên nào.

**Không có cam kết chung rằng mọi sản phẩm ZTNA đều hỗ trợ mọi protocol, kiểm tra quyền theo object, thu hồi session tức thời hoặc ngăn mọi traffic direct IP.** Những thuộc tính đó phải được kiểm chứng.

### 2.3. So sánh theo thuộc tính

| Thuộc tính | VPN truy cập mạng thường gặp | ZTNA theo ứng dụng thường gặp |
| --- | --- | --- |
| Đơn vị truy cập | Mạng, subnet, route, gateway ACL | App/resource/service/port và policy |
| Thiết lập phiên | Thiết lập tunnel trước rồi đi tới đích theo route | Truy cập tới ứng dụng được broker/PEP cho phép |
| Danh tính | VPN credentials/cert/MFA, cộng với kiểm soát đích | IdP, context, device posture, app policy |
| Vị trí kiểm tra | VPN gateway và các firewall/ứng dụng sau gateway | PEP ở đường ứng dụng, endpoint và/hoặc connector |
| Phơi bày địa chỉ | Client có thể có route tới nhiều IP | Có thể che IP/backend, nhưng tùy proxy và client |
| Legacy protocols | Thường hỗ trợ IP protocol linh hoạt hơn | Phụ thuộc ZTNA sản phẩm, agent và protocol support |
| Truy cập từ thiết bị không quản lý | Khó hoặc kiểm soát bằng VPN portal | Một số sản phẩm có browser-only access giới hạn |
| Chính sách liên tục | Tùy VPN/NAC/IdP integration | Thường hướng tới re-evaluate; thực tế tùy sản phẩm |
| Rủi ro cấu hình | Route/ACL rộng, split tunnel, credential leak | Broker/connector bypass, policy quá rộng, posture giả/thiếu |
| Khả năng thay thế lẫn nhau | Hợp cho network-level access, site-to-site, một số legacy use cases | Hợp cho private app access đã kiểm kê và policy hóa |

### 2.4. Ba mục tiêu migration

1. **Giảm lateral movement:** người dùng chỉ có đường tới ứng dụng cần thiết, không tự scan hoặc gọi các hosts khác cùng subnet.
2. **Nâng chất lượng quyết định truy cập:** identity/MFA, trạng thái thiết bị, thời điểm, role, risk và resource ownership được kiểm tra đồng nhất.
3. **Tăng khả năng kiểm toán và thu hồi:** biết ai có quyền vào ứng dụng nào, bằng thiết bị nào, phiên nào và thu hồi trong SLA đã định.

Không dùng mục tiêu **“bỏ VPN càng nhanh càng tốt”** nếu điều này tạo ngoại lệ lớn, tắt MFA hoặc mở cổng quản trị công khai.

## 3. Kiến trúc Zero Trust và các điểm quyết định

Trong cách mô tả Zero Trust của NIST SP 800-207, có thể phân biệt các vai trò logic:

| Vai trò | Ý nghĩa | Biểu hiện thực tế có thể có |
| --- | --- | --- |
| **Policy Engine (PE)** | Đưa ra quyết định cho phép/từ chối theo chính sách và tín hiệu tin cậy | Access decision service, authorization engine |
| **Policy Administrator (PA)** | Thiết lập/điều phối việc cho phép hay ngắt kết nối theo quyết định | Control plane broker, session orchestrator |
| **Policy Enforcement Point (PEP)** | Thực thi quyết định ở đường kết nối | Endpoint agent, proxy, app gateway, private connector |
| **Identity source** | Cung cấp user/workload identity và thuộc tính | IdP, directory, workload PKI |
| **Device posture source** | Cung cấp tín hiệu tình trạng thiết bị | MDM, EDR, certificate inventory |
| **Resource/application** | Dịch vụ đích được bảo vệ | Web app, SSH/RDP host, database, internal API |
| **Telemetry/threat signals** | Ngữ cảnh để đưa ra và xem lại quyết định | SIEM, EDR alerts, network events, risk engine |

**PE, PA và PEP là vai trò kiến trúc, không bắt buộc ba máy chủ hay ba sản phẩm độc lập.** Nhiều nền tảng kết hợp chúng trong một dịch vụ SaaS hoặc proxy cluster.

### 3.1. Control plane và data plane

- **Control plane**: đăng ký thiết bị/ứng dụng, IdP integration, policy distribution, session authorization, certificate/key lifecycle.
- **Data plane**: thực sự chuyển traffic giữa client và ứng dụng sau quyết định.

**Không suy nếu control plane của nhà cung cấp ở nước ngoài thì mọi byte dữ liệu ứng dụng phải qua cùng vị trí**, hoặc ngược lại. Data path có thể relay qua PoP, đi trực tiếp theo cơ chế broker, hoặc nằm trong VPC riêng tùy giải pháp. Cần xác minh topology, data residency và log handling.

### 3.2. Luồng điển hình

~~~mermaid
flowchart LR
    U["Nhân viên / thiết bị"] -->|"Đăng nhập + MFA"| IDP["IdP"]
    U -->|"Yêu cầu ứng dụng"| PEP["ZTNA PEP / broker hoặc endpoint agent"]
    IDP -. "Identity assertions" .-> PE["Policy Engine"]
    POST["MDM / EDR posture"] -. "Device signals" .-> PE
    RISK["Risk, time, group, app catalog"] -. "Policy context" .-> PE
    PE -->|"Allow/Deny + conditions"| PA["Policy Administrator"]
    PA -->|"Session authorization"| PEP
    PEP -->|"Chỉ ứng dụng được phép"| CONN["Private application connector"]
    CONN --> APP["Private application"]
    APP --> AUTH["App/DB authorization"]
    PEP -. "Access telemetry" .-> SOC["SOC / SIEM"]
    APP -. "Business audit" .-> SOC
~~~

**Sơ đồ logic không mặc nhiên đòi data traffic chảy qua PE hoặc PA.** Một số kết nối có thể được cho phép trước rồi duy trì tại data plane; phải đo **thời gian áp chính sách mới và thu hồi phiên**.

### 3.3. “Không tin mạng nội bộ” không có nghĩa bỏ firewall

Zero Trust từ chối việc **vị trí mạng** tự là bằng chứng đủ để cấp quyền. Nó vẫn cần:

- Segment và cloud/network firewalls để giảm blast radius.
- TLS/mTLS để bảo vệ và xác thực endpoints.
- DNS để tìm đúng dịch vụ.
- IAM và resource authorization ở ứng dụng.
- Monitoring/IDS/IPS để phát hiện traffic bất thường.

ZTNA có thể là lớp kiểm soát truy cập từ xa, **không thay toàn bộ chính sách mạng và bảo mật dữ liệu**.

## 4. Threat model trước khi chuyển đổi

### 4.1. Các mối đe dọa của VPN và remote access

- **Credential phishing/session theft**: tài khoản VPN hoặc IdP bị lộ.
- **Thiết bị bị nhiễm mã độc**: sau khi được kết nối, malware thử di chuyển ngang.
- **Route/ACL quá rộng**: user có thể truy cập nhiều hosts ngoài nhu cầu công việc.
- **Split tunnel không kiểm soát**: đường Internet và mạng riêng đồng thời tạo bề mặt thoát dữ liệu.
- **DNS resolver thay đổi**: client phân giải sai private hosts hoặc tiết lộ tên nội bộ.
- **Lateral movement qua RDP/SMB/SSH**: đặc biệt trong các subnet quản trị.
- **Vendor accounts tồn tại quá hạn**: người ngoài đã kết thúc hợp đồng vẫn có quyền.
- **VPN gateway appliance compromise**: gateway/remote access service là tài sản có quyền lớn.

### 4.2. Rủi ro mới hoặc còn tồn tại với ZTNA

- **IdP hoặc access broker bị cấu hình sai** làm cấp quyền rộng hơn dự kiến.
- **MFA fatigue/session hijack** dù mật khẩu không bị lộ.
- **Posture signals stale** hoặc bị giảm tin cậy khi thiết bị không quản lý.
- **Connector đặt trong mạng quá rộng**, tự có route/privilege tới nhiều backend.
- **Ứng dụng vẫn public qua route cũ**, bypass ZTNA.
- **Nhầm FQDN, port hoặc DNS policy**, dẫn request tới endpoint ngoài ý định.
- **Policy thiếu tenant/object authorization** ở backend.
- **Thiếu session revocation và break-glass runbook** khi broker/IdP outage.
- **SaaS/data-path visibility và quyền riêng tư** khi proxy/inspection bởi bên thứ ba.

### 4.3. Mối đe dọa → lớp bảo vệ

| Mối đe dọa | Lớp giảm thiểu chính |
| --- | --- |
| Phishing đăng nhập | Phishing-resistant MFA như FIDO2/WebAuthn khi khả thi; IdP hardening |
| Mã độc trên thiết bị hợp lệ | MDM/EDR posture, least privilege, continuous monitoring, app isolation |
| Scan/lateral movement | App-scoped PEP, firewall/microsegmentation, connector egress restrictions |
| Token/session bị lộ | TLS, session binding khi hỗ trợ, TTL, risk-driven revocation |
| Truy cập vendor quá hạn | Time-bound identity and policy, owner approval, deprovisioning |
| Backend bypass broker | Private exposure, network ACL, application auth, direct-path negative tests |
| Sử dụng sai dữ liệu | Object/tenant authorization và data auditing |
| DNS/proxy bypass | Managed resolver policy, route governance, IPv4/IPv6 egress controls |
| IdP/broker outage | HA, documented fail mode, limited break-glass, tested rollback |

### 4.4. Xác định mục tiêu an toàn đo được

Không dùng tiêu chí đơn giản **“nhân viên đăng nhập ZTNA được”**. Một bộ mục tiêu mạnh hơn:

1. User A chỉ truy cập được app X, không có route tới app Y.
2. User bị gỡ khỏi group hoặc tài khoản bị khóa sẽ mất quyền theo **SLA đã công bố**.
3. Thiết bị không đáp ứng posture không được gọi ứng dụng nhạy cảm, dù IdP login thành công.
4. Backend không truy cập được bằng direct IP/port từ nguồn ngoài luồng được phê duyệt.
5. Mọi yêu cầu quyền cao có **owner, expiration, MFA và audit**.
6. Ứng dụng hợp lệ vẫn hoạt động trong rollout và có fallback được kiểm soát.

## 5. Từ network-centric đến application-centric

Một VPN client có thể nhận route:

~~~text
VPN assigned address: 10.77.0.42
Pushed routes:
  10.20.0.0/16  -> VPN gateway
  10.30.0.0/16  -> VPN gateway
Resolver: corporate DNS
~~~

Đây là **cấu hình giả lập**, chưa đủ để kết luận client có thể truy cập mọi host vì còn firewall/ACL. Khi chuyển sang ZTNA, nên thiết kế **catalog ứng dụng và dependency**:

| App | Người dùng hợp lệ | Resource được cấp | Cần kiểm tra thêm |
| --- | --- | --- | --- |
| Orders portal | Sales employees | orders.internal.example.test:443 | JWT, role/order ownership |
| HR portal | HR staff | hr.internal.example.test:443 | Device compliant, step-up MFA |
| Bastion SSH | Operations on-call | bastion.internal.example.test:22 | PAM/JIT, command/session audit |
| Reporting database | BI workload/team | reporting-db.internal.example.test:5432 | DB auth, approved client device |
| Vendor support portal | Vendor group trong thời hạn | support.internal.example.test:443 | Sponsor approval, expiry |
| Domain controller services | IT admin/legacy clients | Nhiều service/port theo inventory | Không mặc nhiên phù hợp web-only ZTNA |

### 5.1. Đơn vị cấp quyền phải rõ

“Cho truy cập subnet 10.20.0.0/16” có thể cần thay bằng **app name + FQDN/service ID + port + user/group + device condition + expiry**. Tuy vậy, **FQDN không phải danh tính mật mã**; phải xác minh DNS và TLS/certificate ở mỗi kết nối phù hợp.

### 5.2. Lưu ý network reachability còn cần phía connector

Dù client chỉ thấy một ứng dụng, private connector có thể có route tới cả subnet nếu được cấu hình rộng. **Least privilege phải áp cả ở client policy, ZTNA broker và connector→backend firewall**, không chỉ ở giao diện danh mục ứng dụng.

### 5.3. Quyền nghiệp vụ không được suy từ kết nối

ZTNA có thể cho quyền mở HTTPS tới **Orders API**, nhưng việc user được đọc **đơn hàng nào, tenant nào, hành động gì** phải được backend kiểm tra. Một authorization failure ở ứng dụng không được sửa bằng mở thêm network access.

## 6. Pre-migration discovery: kiểm kê VPN đang thực sự phục vụ những gì?

Sai lầm lớn nhất là **chỉ nhìn danh sách tài khoản VPN** rồi cho rằng đã biết hết ứng dụng cần migrate. Thực tế một tunnel VPN có thể mang hàng chục luồng nền: Kerberos, DNS, NTP, certificate enrollment, file shares, RDP dynamic channels, monitoring agents, software update và truy cập tới các hệ thống chưa có owner.

### 6.1. Sáu nhóm inventory cần thu thập

| Nhóm | Thu thập | Rủi ro nếu thiếu |
| --- | --- | --- |
| **Identity** | Users, groups, contractors, service accounts, sponsors, dormant accounts | Cấp nhầm quyền hoặc bỏ sót người cần hỗ trợ |
| **Endpoint** | OS, managed/unmanaged, MDM/EDR, certificates, mobile, BYOD | Posture policy loại nhầm thiết bị hợp lệ |
| **Application** | URL/FQDN, owner, tier, auth, business criticality, data class | Không có resource catalog đáng tin |
| **Protocol** | TCP/UDP, ports, DNS discovery, redirects, callback, Kerberos/SMB/RDP | Một ứng dụng chỉ chạy một phần qua ZTNA |
| **Network** | Client pools, routes, NAT, split tunnel, internal DNS, firewall ACLs | Bypass hoặc disruption khi đổi đường |
| **Operational** | Peak concurrency, latency, certificates, break-glass, incident runbook | Outage khi cắt VPN hoặc vendor service lỗi |

### 6.2. Nguồn dữ liệu phải đối chiếu

Một quy trình có thể dùng những nguồn **được phép truy cập**:

1. VPN gateway logs: principal, device profile, assigned IP, session time.
2. Firewall/flow logs trong các vùng mạng: **destination IP/port/protocol và NAT context**.
3. DNS resolver logs: FQDN được truy vấn, private zones và sự khác nhau khi ngoài VPN.
4. CMDB/service catalog và ứng dụng mà các đội nghiệp vụ khai báo.
5. IdP/MDM/EDR: group, identity lifecycle, device compliance.
6. Endpoint/user interviews: nhu cầu thật, workflows, thời gian peak.
7. Application/server logs: authentication, dependencies, service access.

**Flow logs không tự chỉ ra hostname hoặc chủ thể nghiệp vụ**, vì NAT, DNS cache và shared sessions. Cần correlation theo timestamp, source, assigned VPN IP và identity khi chính sách riêng tư cho phép.

### 6.3. Ứng dụng “ẩn” trong subnet

Ví dụ một nhân viên báo chỉ dùng **hr.internal.example.test**, nhưng flow logs cho thấy client còn kết nối:

~~~text
10.30.10.20:443  HR web portal
10.30.10.51:88   Kerberos authentication
10.30.10.52:389  Directory lookup
10.30.10.91:445  Document share
10.30.10.99:123  Time service dependency
~~~

Đây là **dữ liệu lab giả lập**. Các luồng thực tế tùy hệ thống: không phải mọi ứng dụng web đều dùng client-side Kerberos, LDAP/SMB hoặc NTP qua VPN. Cần xác minh **ứng dụng server-side hay thiết bị client** mới là nguồn các dependencies, vì hai trường hợp sẽ có kiến trúc ZTNA khác nhau.

### 6.4. Không biến discovery thành giám sát tùy tiện

Thu thập telemetry phải phù hợp quyền và mục đích, đặc biệt với **URL nội bộ, tên thiết bị, địa chỉ người dùng hoặc dữ liệu nhạy cảm trong DNS logs**. Chọn retention, redaction và RBAC. Không cần lưu credential/token để biết một kết nối đang phục vụ ứng dụng nào.

## 7. Xây dựng application catalog và phân loại migration

Mỗi ứng dụng được gán **owner và security classification** trước khi chuyển:

| Thuộc tính | Ví dụ | Tại sao quan trọng |
| --- | --- | --- |
| App ID | app-orders-portal | Identity ổn định khi hostname đổi |
| Owner/sponsor | sales-platform | Ai phê duyệt quyền và sự cố |
| Resource | orders.internal.example.test:443 | Điểm đích thực sự |
| Protocol | HTTPS/TCP | Chọn đúng ZTNA access mode |
| Dependencies | IdP, DB, internal DNS | Tránh chuyển một nửa ứng dụng |
| Authentication | SAML/OIDC, integrated auth, local login | Tránh double-login và auth bypass |
| Data classification | Internal/Restricted | Yêu cầu posture/MFA, logs và DLP |
| Access population | Sales staff, 24/7 vendor | Pilot nhóm và thời gian |
| Availability objective | Critical / tolerate short outage | Canaries và rollback |
| Current VPN policy | Source group → subnet/port | Cơ sở giảm quyền |
| Proposed ZTNA policy | Group/role → named app + conditions | Target design |
| Success evidence | Allow/deny tests, SLO, owner sign-off | Không chỉ dựa login success |

### 7.1. Phân nhóm ứng dụng

**Nhóm A – Web phù hợp:** HTTPS nội bộ, hostname rõ, có auth chuẩn, ít dependency phía client. Thường phù hợp pilot **browser-based hoặc agent-based ZTNA** tùy sản phẩm.

**Nhóm B – TCP có cấu trúc:** SSH, RDP, PostgreSQL, Git over SSH. Có thể phù hợp **agent-based / TCP-aware ZTNA**, bastion hoặc proxy, nhưng phải kiểm tra client identity và audit.

**Nhóm C – Legacy/phức tạp:** SMB, AD join/GPO, Kerberos delegation, discovery/broadcast, VoIP/UDP, dynamic ports, thick clients hoặc IP hardcode. Cần lab riêng, thiết kế bù và có thể giữ **segmented VPN**.

**Nhóm D – Workload/system access:** backup, monitoring, batch jobs, machine-to-machine. Không nên đưa tất cả vào human ZTNA agent; có thể dùng **mTLS, workload identity, private network connectivity và policy cho service accounts**.

**Nhóm E – Admin/break-glass:** domain controllers, hypervisors, gateways, network devices. Cần **PAM/JIT, session recording khi phù hợp, out-of-band recovery** và không phụ thuộc hoàn toàn vào một IdP/browser path.

### 7.2. Điều kiện Ready for Migration

Chỉ đánh dấu một app “ready” khi:

1. Owner xác nhận flows và danh sách authorized users.
2. Protocol thực sự được ZTNA product/support mode phục vụ.
3. FQDN/DNS/certificate và dependencies kiểm thử từ client thực.
4. Connector có route **và firewall tối thiểu** tới backend.
5. AuthN/AuthZ tại backend giữ hoặc cải thiện.
6. Đã có allow/deny test, rollback và telemetry.
7. Hệ thống trợ giúp người dùng biết cách xử lý lỗi đăng nhập/thiết bị.

## 8. Phân loại đối tượng truy cập và use cases

ZTNA policy không thể dựa trên một nhóm tên **employees** cho mọi người:

| Persona | Nhu cầu | Điều kiện truy cập gợi ý |
| --- | --- | --- |
| Nhân viên toàn thời gian | Các portal thường ngày | SSO/MFA, managed device nếu dữ liệu nhạy cảm |
| Nhân viên từ thiết bị cá nhân | Một số web apps | Browser-only mode, hạn chế download/clipboard theo sản phẩm |
| Nhà thầu ngắn hạn | Một app hoặc workflow cụ thể | Sponsor, expiry, limited hours, MFA |
| Đối tác vận hành | Support portal hoặc API | Federated identity/client certificate, role cụ thể |
| IT administrator | SSH/RDP/bastion/console | Privileged identity, PAM/JIT, step-up MFA, audit |
| Mobile workforce | Ứng dụng di động | OS/MDM support, app identity, network roaming |
| Service account/workload | Job/API/backend | Workload certificate/identity và network/service policy |
| Ứng cứu khẩn cấp | Recovery khi IdP/broker down | Break-glass riêng, nhiều bước phê duyệt và audit |

### 8.1. Thiết bị được quản lý và không được quản lý

Một nền tảng có thể đưa ra **browser/clientless access** cho app web trên thiết bị BYOD, nhưng điều đó **không đồng nghĩa thiết bị được phép dùng thick client, tải dữ liệu về hoặc truy cập database**. Nếu có tính năng hạn chế copy/paste/download, cần test **tính hiệu lực và khả năng bypass**, không tuyên bố phòng chống rò rỉ tuyệt đối.

### 8.2. Danh tính người dùng và danh tính ứng dụng

Một thiết bị do nhân viên sở hữu có thể chạy nhiều ứng dụng. Quyết định **user được quyền vào HR** khác với quyết định **một batch service được quyền gọi HR API**. Không cấp permanent machine credentials chỉ để né ZTNA user MFA, và không yêu cầu service không tương tác thực hiện human login theo cách không thực tế.

### 8.3. Vòng đời người ngoài

Với contractors/vendors, policy nên có:

- Sponsor và resource owner phê duyệt.
- Thời điểm bắt đầu/kết thúc, group membership expiry.
- MFA và device requirements rõ ràng.
- Chỉ các apps/ports cụ thể.
- Log và re-certification định kỳ.
- Thu hồi mọi credential/session/connector-specific permission khi kết thúc.

## 9. Identity foundation: IdP, MFA, provisioning và revocation

### 9.1. IdP là điểm tin cậy quan trọng

ZTNA thường dựa vào **enterprise IdP** để xác thực users qua OIDC/SAML hoặc cơ chế tích hợp khác. Các lỗi ở **federation trust, application registration, redirect URIs, group mappings, token audience** có thể làm quyền truy cập sai ngay cả khi network policy đúng.

**Không nên mặc định một successful SSO login cho quyền truy cập mọi ứng dụng ZTNA.** Access broker phải kiểm tra app assignment và conditions cụ thể.

### 9.2. Phishing-resistant MFA

Ưu tiên những phương thức như **FIDO2/WebAuthn/passkey hoặc hardware security key** khi phù hợp với risk/profile. SMS/OTP/push có thể còn được dùng trong một số môi trường nhưng cần hiểu giới hạn trước phishing, session theft và push fatigue.

Đối với admin access, nên có **step-up MFA, privileged role, JIT access và session auditing** theo chính sách.

### 9.3. Provisioning và deprovisioning

IAM lifecycle phải được thiết kế:

1. **Joiner:** tạo user qua nguồn nhân sự/tổ chức, cấp nhóm có owner.
2. **Mover:** đổi role, loại quyền cũ và cấp quyền mới theo duyệt.
3. **Leaver:** disable IdP/session/token, thu hồi app access và endpoint credentials trong SLA.
4. **Contractor:** tự hết quyền theo expiry, không dựa vào nhân viên nhớ xóa.
5. **Privileged:** phân tách admin identity và user identity, tránh permanent privilege.

**Disable user ở IdP chưa bảo đảm mọi data-plane connection đang mở sẽ ngắt tức thời.** Broker, connectors, auth caching, OAuth token TTL và long-lived TCP sessions có thể làm hiệu quả thu hồi khác nhau.

### 9.4. Nhóm user phải được quản trị

Nếu policy dựa trên group **ZTNA-Finance-Admins**, ai có quyền thêm thành viên vào group cũng có thể ảnh hưởng quyền truy cập. Dùng owner approval, audit, periodic access review và bảo vệ nguồn attributes; không coi group string là đảm bảo độc lập với governance.

## 10. Device posture và điểm tin cậy của thiết bị

**Device posture** cung cấp tín hiệu để đánh giá rủi ro từ endpoint: enrollment, tình trạng hệ điều hành, bảo vệ ổ đĩa, EDR/AV, certificates, screen lock hoặc chính sách MDM. Nhưng posture chỉ hữu ích khi **nguồn tín hiệu tin cậy, cập nhật đủ nhanh và phù hợp mức độ nhạy cảm**.

### 10.1. Những tín hiệu điển hình

| Signal | Câu hỏi | Giới hạn |
| --- | --- | --- |
| Managed device enrollment | Thiết bị có thuộc danh mục đã đăng ký? | Chưa chứng minh không có mã độc |
| Endpoint certificate | Thiết bị sở hữu key/hồ sơ đã cấp? | Phải bảo vệ key và chính sách revocation |
| MDM compliance | OS, disk encryption, lock, update đạt policy? | Có thể stale, phụ thuộc sync |
| EDR health | Agent healthy, alert/risk status? | Không phát hiện 100% tấn công |
| OS/security updates | Đáp ứng baseline patch? | Phiên bản mới không tự xóa mọi lỗ hổng |
| Device risk score | Mức độ rủi ro tổng hợp | Cần minh bạch ngưỡng và false positives |
| Location/time | Truy cập từ đâu, lúc nào? | Geo/IP không chứng minh user identity |
| Client/browser mode | Agent kiểm soát được gì? | Browser-only có giới hạn visibility |

### 10.2. Kiểm tra posture khi nào?

- Trước khi cấp session.
- Khi phiên có dấu hiệu rủi ro hoặc access level thay đổi.
- Định kỳ hoặc nhận event từ MDM/EDR theo năng lực sản phẩm.
- Trước privileged operations nếu policy yêu cầu.

**Continuous verification** là mục tiêu kiến trúc, không tự có trong mọi ZTNA product. Phải xác minh **tần suất posture refresh, session revocation và hành vi khi posture source không khả dụng**.

### 10.3. Thiết kế fail mode

Khi MDM/EDR mất kết nối, chính sách cho app thường ngày có thể khác app quản trị tài chính. Một lựa chọn là **deny sensitive access**, còn với app ít nhạy cảm có thể cho phép theo cache còn hiệu lực/exception ngắn hạn nếu được phê duyệt. Không xây dựng **“posture service down ⇒ allow all”** làm mặc định.

### 10.4. Quyền riêng tư và BYOD

Người dùng thiết bị cá nhân cần biết **tín hiệu nào được thu thập, mục đích, retention, quyền truy cập, mức theo dõi**. Không yêu cầu thu toàn bộ ứng dụng/cá nhân nếu chỉ cần một số posture signals; có thể cung cấp browser-based limited access hoặc thiết bị được quản lý cho trường hợp cần dữ liệu nhạy cảm.

## 11. ZTNA access modes: browser, agent và network-level alternatives

### 11.1. Browser-based/clientless access

Trong một số sản phẩm, người dùng vào **web portal hoặc reverse-proxy access**, xác thực với IdP và truy cập ứng dụng nội bộ mà không cài VPN agent. Đây có thể là lựa chọn phù hợp cho **HTTPS web apps**, đối tác hoặc BYOD.

Giới hạn thường phải kiểm tra:

- App có **absolute URLs, redirects, WebSockets, cookie domains, CSP, SSO callback hoặc client-side APIs** cần rewrite không?
- Web app có dùng **integrated Windows authentication/Kerberos** mà proxy không thể chuyển ngữ cảnh phù hợp?
- Upload/download/copy/paste có bị hạn chế thật, và ảnh hưởng nghiệp vụ thế nào?
- Có supporting feature cho **gRPC, HTTP/2, custom TCP/UDP** không, hay chỉ một tập HTTP(S)?
- Trình duyệt của user có certificate/key requirements hoặc third-party cookies limitations không?

### 11.2. Agent-based/private-app access

Một client agent có thể intercept traffic tới **FQDN/IP/service** được công bố trong catalog, đưa nó vào kênh ZTNA và kết nối tới PEP/connector. Phương thức routing có thể dựa trên DNS rewriting, virtual IP, local proxy, packet interception hoặc tunnel được giới hạn theo app.

**Agent-based ZTNA không mặc nhiên không có tunnel**. Một số triển khai sử dụng cơ chế tunneling ở data plane nhưng **quyền truy cập được giới hạn theo ứng dụng/policy**. Cần đánh giá **địa chỉ/port được expose và những route có thể bị dùng ngoài quyền**, không kết luận từ thuật ngữ “tunnel-less”.

### 11.3. Direct access và brokered access

Một số giải pháp chuyển dữ liệu qua **cloud PoP/relay**, số khác có thể tạo **direct connection qua policy broker** khi điều kiện mạng cho phép. Hệ quả khác nhau:

| Thuộc tính | Relay/proxy path | Direct path được broker cho phép |
| --- | --- | --- |
| Data plane | Có thể đi qua PoP/proxy của nhà cung cấp | Có thể đi trực tiếp giữa client và private edge |
| Latency | Phụ thuộc PoP/route và inspection | Phụ thuộc peering/NAT/path trực tiếp |
| Data residency | Cần xem vị trí PoP và lưu lượng được xử lý | Cần xem path và telemetry location |
| Firewall | Connector thường outbound tới service/PoP | Có thể cần những luồng/ports riêng |
| Bypass controls | Phải kiểm tra cả connector/direct backend | Phải chứng minh direct path vẫn enforce policy |

Không suy từ “direct path” là không có policy, hoặc “proxy path” là nội dung TLS luôn bị giải mã. Hãy kiểm tra **TLS endpoints, session authorization, cipher/key custody và packet path**.

### 11.4. Chọn access mode theo ứng dụng

| Loại ứng dụng | Chế độ có thể phù hợp | Điều phải thử |
| --- | --- | --- |
| Web portal chuẩn HTTPS | Clientless hoặc agent | Auth redirects, cookies, CSP, uploads |
| Thick client qua TCP cố định | Agent/TCP forwarding | DNS, certificate pinning, port mapping |
| SSH/RDP | Agent, bastion/proxy hoặc PAM | MFA/JIT, file transfer, clipboard, session audit |
| Database client | App-aware TCP access, DB proxy | JDBC/ODBC, TLS hostname, DB auth |
| UDP/VoIP/real-time | Chỉ nếu sản phẩm hỗ trợ; hoặc VPN riêng | Loss/jitter, NAT traversal, media flows |
| SMB/AD/GPO | Legacy-specific thiết kế, có thể segmented VPN | Dynamic ports, Kerberos, DNS, discovery |
| Site-to-site/machine workloads | IPsec/private network, workload identity/mTLS | Không ép human ZTNA agent cho máy chủ |

## 12. Private application connector: thiết kế và giới hạn quyền

**Private application connector** thường được đặt ở data center/VPC/VNet gần ứng dụng; tùy sản phẩm nó tạo kết nối outbound tới một broker/cloud service, cho phép người dùng đã được policy duyệt truy cập mà không cần đưa backend trực tiếp ra Internet.

### 12.1. Một topology mẫu

~~~mermaid
flowchart TB
    USER["Remote user / device"] -->|"IdP + MFA, ZTNA request"| BROKER["ZTNA policy broker / PEP"]
    BROKER -->|"Authorized session"| CONN["Private connector pool"]
    CONN -->|"Only FQDN/port in approved app catalog"| APP["Orders web / SSH / DB service"]
    IDP["IdP + MDM/EDR"] -. "Identity + posture" .-> BROKER
    FW["Connector egress firewall"] -. "Limits app destinations" .-> CONN
    USER -. "No general subnet route" .-> BLOCK["Other internal resources denied"]
    APP -. "App auth + audit" .-> AUDIT["SIEM / Data logs"]
    BROKER -. "Access logs" .-> AUDIT
~~~

Sơ đồ không khẳng định broker xử lý mọi packet hoặc connector bắt buộc mở một public listener. Cần xem **kiến trúc và port requirements chính xác của sản phẩm được chọn**.

### 12.2. Vì sao connector là tài sản có độ tin cậy cao?

Connector có thể truy cập **nhiều backend nội bộ**. Nếu bị chiếm quyền hoặc bị policy cấp quá rộng, nó trở thành điểm có thể di chuyển ngang. Vì vậy:

1. Chạy connector trong **subnet/zone riêng** với egress rules tối thiểu đến apps cụ thể.
2. Hạn chế **service account, local admin/root, secret và API permissions**.
3. Chỉ cho connector dùng những **broker/PoP/IdP endpoints** được phê duyệt.
4. Dùng **mTLS/TLS, certificate rotation**, bảo vệ bootstrap secrets và private keys.
5. Cấu hình **HA nhiều connectors**, health check, capacity và đặt ở nhiều zones khi cần.
6. Cập nhật runtime/agent, kiểm soát image supply chain, log changes và network flows.
7. Không cho user ZTNA có quyền truy cập trực tiếp **SSH vào connector** chỉ vì họ có quyền một app phía sau nó.

### 12.3. Connector nào phục vụ ứng dụng nào?

Phân chia connector pools theo **trust zone, dữ liệu và độ nhạy cảm**:

| Pool | Có route đến | Không nên có route đến |
| --- | --- | --- |
| Corporate-web | HR/portal HTTPS theo catalog | Core database administration |
| Finance-restricted | Financial apps và exact ports | Dev/testing subnets |
| Vendor-support | Support apps đã phê duyệt | AD domain controllers toàn mạng |
| Privileged-admin | Bastion/PAM endpoints | Public unmanaged access |
| Cloud-prod | App endpoints trong VPC production | Shared connector admin/management plane |

**Tách pool chỉ hữu ích khi firewall, IAM và policy thật sự giới hạn mỗi pool**, không chỉ đổi tên connector group.

### 12.4. Khả dụng của connector

Phải đánh giá **connector failure, cloud PoP outage, TLS certificate expiry, DNS upstream failure và network route changes**. Nếu connector pool hết capacity, không sửa bằng cách mở một public LB trực tiếp vào backend. Thay vào đó dùng canary, scaling, HA/health routing và fallback đã định nghĩa.

### 12.5. Khi connector kết nối outbound

Một số sản phẩm yêu cầu connector **khởi tạo outbound TLS** tới dịch vụ điều khiển/relay. Điều này có thể giảm nhu cầu mở inbound từ Internet, nhưng:

- Không bảo đảm mọi backend tự được khóa inbound từ nơi khác.
- Không loại bỏ nhu cầu **egress allowlist, DNS governance và TLS verification** của connector.
- Không tự ngăn các workloads trong cùng VPC truy cập thẳng ứng dụng.

## 13. DNS và FQDN khi VPN/ZTNA cùng tồn tại

Với VPN, endpoint thường nhận **corporate DNS servers và split-DNS search suffixes**. Với ZTNA, một client có thể dùng **local DNS interception, virtual IP, resolver rules hoặc public hostname mapping**, tùy agent và sản phẩm.

### 13.1. Các vấn đề thường gặp

- **App FQDN** chỉ resolve khi VPN đang kết nối.
- Private zone như **corp.internal.example.test** chưa được ZTNA client/connector xử lý.
- IdP login/SSO redirect dùng hostname khác với ZTNA published app.
- App dùng absolute URL dẫn sang một host chưa được đăng ký trong catalog.
- TLS certificate chỉ hợp lệ cho một tên cũ, trong khi ZTNA proxy thay đổi origin/Host/SNI.
- Client cache DNS hoặc giữ TCP connections khi chuyển giữa VPN và ZTNA.
- Split DNS có **A/AAAA khác nhau**, IPv6 route ngoài ZTNA.
- Containerized/private app cần forward DNS giữa cloud/on-prem.

### 13.2. Quy trình thiết kế phân giải tên

1. Liệt kê **tên mà user/app thực sự dùng**, không chỉ primary portal.
2. Phân loại **public authoritative DNS, private zones, conditional forwarding, search domains**.
3. Xác định resolver trên **client**, **ZTNA broker/agent** và **connector**.
4. Xác định IP/endpoint mà **connector thật sự kết nối**, bao gồm backend TLS hostname.
5. Test client **ngoài VPN**, **VPN-only**, **ZTNA-only** và **coexistence**.
6. Kiểm tra A/AAAA/IPv6 và cả những hostname do redirect/iframe/API gọi tiếp.
7. Xác minh certificate SAN/SNI/trust và application redirects.

### 13.3. Ví dụ hai namespace DNS

~~~text
Remote user:
  orders.internal.example.test -> mapping dành cho ZTNA client

Private connector trong VPC:
  orders.internal.example.test -> 10.20.10.15 (private backend)

Public Internet DNS:
  orders.internal.example.test -> không nhất thiết có public record
~~~

Các mappings chỉ minh họa. **Hai phía dùng cùng một hostname nhưng giải nghĩa theo đường khác nhau** không phải lỗi nếu được thiết kế, giám sát và TLS verify đúng. Phải đảm bảo không có **DNS loop hoặc đích public ngoài dự kiến**.

### 13.4. DNS không cấp quyền

Ngay cả khi client resolve được hostname nội bộ, **PEP phải từ chối resource không được cấp quyền**, connector firewall phải giới hạn đường đến backend, và backend kiểm tra application auth. Không dùng **giấu DNS record** làm biện pháp thay thế firewall.

### 13.5. Trạng thái kết nối với split tunnel

Khi VPN và ZTNA agent cùng điều chỉnh DNS, route hoặc proxy PAC, có thể xảy ra **race/conflict**. Phải có compatibility test với những endpoint agents khác (EDR, SWG, DNS security, VPN, MDM) theo OS/version. Không cài đồng thời hai agents rồi mặc định chúng phối hợp tốt.

## 14. TLS, certificates, proxies và xác thực đích

ZTNA thường bảo vệ transport bằng TLS/mTLS hoặc cơ chế tunnel khác, nhưng **số chặng TLS và nơi terminate** phải được ghi rõ:

~~~mermaid
flowchart LR
    CLIENT["Client app/browser"] -->|"Client→ZTNA PEP TLS"| PEP["ZTNA PEP"]
    PEP -->|"Authenticated transport"| CONN["Private connector"]
    CONN -->|"TLS hoặc mTLS upstream theo thiết kế"| API["Private application"]
    API -->|"Application authorization"| DATA[("Data")]
~~~

### 14.1. Tránh nhầm tunnel encryption với TLS server identity

ZTNA client có thể thiết lập kênh mã hóa tới broker, nhưng nếu connector mở HTTPS tới backend và **không xác minh certificate/hostname**, attacker ở mạng nội bộ vẫn có thể thực hiện man-in-the-middle tại chặng đó trong những điều kiện phù hợp. Cần xác minh **cả tunnel trust và upstream server identity**.

### 14.2. Certificate pinning và ứng dụng cũ

Một ứng dụng dùng **certificate pinning, mutual TLS hoặc native protocol encryption** có thể không chấp nhận traffic inspection hoặc TLS termination tại proxy. Đây không phải lý do tắt hostname verification; cần chọn **TCP passthrough/agent mode** phù hợp hoặc thiết kế proxy không can thiệp TLS của ứng dụng.

### 14.3. HTTP reverse-proxy rewriting

Nếu proxy công bố **https://ztna.example.test/orders** thay cho **https://orders.internal.example.test**, có thể xuất hiện:

- Callback/redirect URL mismatch trong OIDC/SAML.
- Cookie Domain, Secure/SameSite hoặc CORS/CSP policy không phù hợp.
- WebSockets không đi qua path rewrite.
- Absolute resource URLs/embedded assets trả hostname cũ.
- HTTP Host/SNI không được đưa đúng tới backend.

Trong nhiều trường hợp, giữ nguyên **ứng dụng hostname gốc** với published app policy phù hợp giúp tránh thay đổi code hơn, nhưng vẫn phải đánh giá certificate và DNS.

### 14.4. Ngăn proxy header spoofing

Nếu backend tin các headers như **X-Authenticated-User, X-Forwarded-User, X-Device-Compliant**, gateway phải **loại bỏ giá trị do client tự gửi**, tái tạo từ dữ liệu đã xác minh và chỉ chuyển trên đường được bảo vệ. Backend không nên bỏ auth chỉ vì request tới từ connector IP.

### 14.5. TLS client certificate và browser-based access

Ứng dụng yêu cầu **client mTLS certificate** có thể cần proxy hỗ trợ client certificate propagation/identity mapping hoặc kết nối passthrough theo thiết kế. **Một chứng thư của connector không tự đại diện user**, trừ khi có cơ chế identity binding đáng tin và backend authorize đúng chủ thể.

## 15. Các giao thức legacy và khả năng tương thích

### 15.1. SSH

SSH thường là TCP 22, nhưng an toàn đòi hỏi:

- IdP/role authorization, có thể **PAM/JIT**.
- Host key verification, không tắt để dùng tunnel.
- Hạn chế tới đúng hostname/port/target.
- Phân tách admin và user principals.
- SSH agent forwarding, file transfer, port forwarding, tunnels phải được review theo policy.
- Audit command/session khi phù hợp, không lộ secrets.

Một ZTNA TCP tunnel chỉ vận chuyển SSH; **SSH authentication và host authorization vẫn bắt buộc**.

### 15.2. RDP

RDP sử dụng các kênh/chế độ hỗ trợ khác nhau, có thể liên quan TCP và UDP theo client/server/config. Trước migration, kiểm tra:

- NLA và authentication của Windows host.
- Dynamic virtual channels, clipboard, printer/drive redirection.
- MFA/PAM/JIT và record session theo nhu cầu.
- Latency, reconnect sau sleep/roaming và multi-monitor.
- Quyền máy đích và firewall nội bộ.

Không cấp toàn bộ **Windows server subnet** chỉ vì một nhóm IT cần RDP vào hai hosts.

### 15.3. SMB và domain services

SMB thường dùng TCP 445, nhưng workflow Windows enterprise có thể còn phụ thuộc **Kerberos, LDAP, DNS SRV, RPC dynamic ports, domain controllers và GPO**. Đường TCP 445 chạy được **không bảo đảm file share và domain logon hoạt động đầy đủ**.

Nên cân nhắc:

1. Chuyển file workflows sang **web/SaaS portal** có authorization phù hợp nếu khả thi.
2. Dùng **VDI/remote desktop** cho ứng dụng legacy không thể đưa trực tiếp qua ZTNA.
3. Dùng **segmented VPN** với ACL hẹp trong khi hiện đại hóa.
4. Thiết kế protocol-aware ZTNA cho tập máy/cổng đã xác minh, nếu sản phẩm hỗ trợ.

### 15.4. Database clients

BI/admin tools có thể dùng JDBC/ODBC/TDS/PostgreSQL protocols. Cần kiểm tra:

- Cổng và địa chỉ **ổn định**, TLS server hostname/SNI.
- Connection pooling, keepalive, failover và multi-host connection strings.
- DB role/least privilege, service credentials và audit.
- Phân biệt **network access được phép** với **quyền SELECT/DDL**.

Đối với privileged database operations, có thể cần **database proxy/PAM/JIT** thay vì chỉ mở TCP trong ZTNA.

### 15.5. UDP và real-time traffic

Không phải mọi ZTNA proxy hỗ trợ UDP. Những ứng dụng như VoIP, video, telemetry, một số gaming/OT protocols hoặc các luồng real-time có thể chịu ảnh hưởng **latency, jitter, loss, MTU và NAT**. Cần giữ VPN/private connectivity cho use cases chưa được giải quyết, với phân đoạn và giám sát tương ứng.

### 15.6. Các protocol không được đưa qua web proxy bằng suy đoán

Tài liệu sản phẩm phải nêu rõ khả năng cho **ICMP, UDP, TCP multi-ports, port ranges, server-initiated connections, broadcast/multicast và discovery**. Không “sửa” bằng cách công bố cả subnet như một ứng dụng nếu điều đó đánh mất mục tiêu giảm lateral movement.

## 16. VPN và ZTNA cùng tồn tại: route, DNS, proxy và rollback

**Coexistence** là giai đoạn nhiều rủi ro nhất: cùng một endpoint có thể chạy VPN và ZTNA agent, nhận **hai nguồn DNS/route/proxy settings** và có thể truy cập ứng dụng bằng hai đường khác nhau. Nếu giữ VPN allow-all trong suốt pilot, một ca kiểm thử ZTNA thành công **không chứng minh rằng ZTNA đã thực sự cấp quyền**.

### 16.1. Bốn mô hình coexistence

| Mô hình | Cách dùng | Rủi ro/kiểm tra |
| --- | --- | --- |
| **User-group split** | Pilot users dùng ZTNA; nhóm khác vẫn VPN | Đảm bảo pilot không còn quyền VPN tới app đang đánh giá |
| **App split** | Web apps chuyển ZTNA; legacy apps vẫn VPN | DNS/route overlap và quyền tới backend qua cả hai |
| **Device split** | Managed laptops dùng agent; BYOD vào browser portal | Khác biệt posture và dữ liệu được tải về |
| **Dual access** | Cùng app có cả VPN và ZTNA một thời gian ngắn | Khó chứng minh deny, nguy cơ policy không nhất quán |

### 16.2. Lập bản đồ đường kết nối

~~~mermaid
flowchart TD
    CLIENT["Pilot laptop"] -->|"ZTNA policy"| Z["ZTNA client/broker"]
    CLIENT -->|"Legacy tunnel nếu còn"| VPN["VPN gateway"]
    Z -->|"Approved connector"| APP["Orders application"]
    VPN -->|"Old VPN ACL/route"| APP
    VPN --> OTHER["Legacy network resources"]
    CONTROL["Migration gates"] -. "Đóng dần VPN route tới app đã chuyển" .-> VPN
    CONTROL -. "Kiểm tra ZTNA deny độc lập" .-> Z
~~~

Trong bài kiểm thử **ZTNA deny**, phải ngăn đường VPN cũ **vượt qua kết quả ZTNA**. Điều này không nhất thiết đòi ngắt toàn bộ VPN ngay: có thể áp **ACL theo pilot user/group tới đúng app** và dùng client/test path được cô lập với bằng chứng routing.

### 16.3. Full tunnel, split tunnel và application steering

- **VPN full tunnel:** nhiều traffic Internet/corporate được đưa qua VPN gateway theo chính sách.
- **VPN split tunnel:** chỉ traffic tới những prefixes/corporate destinations đi trong VPN, còn phần khác theo mạng thường.
- **ZTNA app steering:** client chỉ gửi những luồng tới applications trong catalog qua ZTNA path, theo cơ chế sản phẩm.

Không được suy **“ZTNA thay VPN ⇒ mọi Internet traffic được lọc”**. Nếu cần secure web gateway, DNS protection, CASB/SSE hoặc DLP, phải triển khai **chúng như các kiểm soát riêng**.

### 16.4. Xung đột ở endpoint

Các lỗi phổ biến:

1. DNS search suffix của VPN ghi đè ZTNA resolver interception.
2. ZTNA đặt virtual IP/FQDN mapping nhưng VPN route đưa traffic đến nơi khác.
3. PAC/HTTP_PROXY/NO_PROXY và endpoint security agents làm ứng dụng chọn đường sai.
4. IPv6 traffic đi ngoài policy vì chỉ xét IPv4.
5. On-prem apps dùng split DNS khác cloud private zones.
6. Sleep/resume/roaming tạo cached routes hoặc stale sessions.
7. OS update hoặc agent upgrade thay network filter order.

Phải có **matrix theo OS, agent version, network type, app mode** và kiểm thử trước rollout diện rộng.

### 16.5. Hủy VPN không phải một nút bấm

Không xóa gateway/route/certificate khi chưa xử lý:

- Site-to-site/IPsec tunnels cho hệ thống máy-máy.
- Applications còn trong nhóm legacy.
- Emergency administration/break-glass.
- VPN DNS, NTP, certificate enrollment hoặc monitoring dependencies.
- Luồng phục hồi DR và hệ thống ở chi nhánh.

**Thành công là loại bỏ những quyền network-wide không cần thiết**, không nhất thiết xóa mọi kết nối VPN trong tổ chức.

## 17. Thiết kế policy ZTNA theo least privilege

### 17.1. Mô hình quyết định theo ngữ cảnh

Một access decision nên xét tối thiểu:

~~~text
Subject       = user/workload identity đã xác minh
Device        = posture và mức tin cậy của thiết bị
Resource      = ứng dụng/service/FQDN/port được duyệt
Action        = kết nối; method/operation khi enforcement hỗ trợ
Context       = MFA strength, risk, location, time, sponsor
Session       = TTL, re-evaluation, revocation và policy version
Enforcement   = PEP + connector/network policy + app auth
~~~

Mỗi tín hiệu phải có **nguồn tin cậy và cách cập nhật**. Ví dụ đánh giá trạng thái EDR từ một HTTP header do client tự gửi là không an toàn. Cũng không nên gắn quá nhiều “risk scores” mơ hồ mà không hiểu dữ liệu và hành vi khi chúng bị thiếu.

### 17.2. Ma trận chính sách minh họa

| Policy | Subject | Device condition | Resource | Ngữ cảnh | Kết quả |
| --- | --- | --- | --- | --- | --- |
| P-01 | sales-staff | Managed + compliant | Orders portal HTTPS | MFA | Allow |
| P-02 | hr-staff | Managed + compliant | HR portal HTTPS | Step-up khi rủi ro cao | Allow có điều kiện |
| P-03 | finance-admin | Managed + healthy EDR | Finance admin portal | JIT + strong MFA | Allow có thời hạn |
| P-04 | external-vendor | Approved/browser-limited | Vendor support portal | Sponsor + expiry | Allow hạn chế |
| P-05 | contractor | Unmanaged | Production DB SSH/RDP | Bất kỳ | Deny |
| P-06 | sales-staff | Bất kỳ | Hypervisor management port | Bất kỳ | Deny |
| P-07 | former-employee | Bất kỳ | Mọi nội bộ | Disabled account | Deny |
| P-08 | workload-service | mTLS/workload identity | Approved API | Scope/audience | Service policy riêng |

### 17.3. Least privilege theo cả chiều kết nối

Phải hạn chế ít nhất:

1. **Ai được yêu cầu ứng dụng?** Group/role/identity policy.
2. **Kết nối đến resource nào?** Named app, FQDN/IP/port, connector assignment.
3. **Connector được đi tới đâu?** Firewall/route ACL giữa connector và backend.
4. **Backend chấp nhận ai?** TLS/client/service identity và application authorization.
5. **Access kéo dài bao lâu?** Expiry, revalidation, revocation SLA.

Nếu user bị từ chối ở broker nhưng vẫn có route **VPN tới cùng backend**, phải sửa **đường bypass** trước khi khẳng định deny có hiệu lực.

### 17.4. Deny mặc định nhưng không ngắt dependency nền

Default-deny giúp giới hạn quyền, nhưng các luồng **IdP, DNS, NTP, certificate issuance, health, broker/connector control** phải được kiểm kê. Một policy quá chặt có thể làm client không xác thực được hoặc connector không nhận cập nhật. Không dùng sự cố này làm lý do mở **0.0.0.0/0:any**.

### 17.5. Quyền theo từng hành động

ZTNA network PEP có thể chỉ biết **connect to HTTPS app**; quyền **GET vs POST**, **read vs write**, **object owner/tenant** thường phải được API/app hoặc một L7 PEP hỗ trợ quyết định. Không ghi **“chỉ read”** vào policy mạng L4 rồi cho rằng DB/API sẽ tự biết quyền.

## 18. PAM, just-in-time và truy cập khẩn cấp

Truy cập quản trị có blast radius lớn hơn ordinary apps. Ví dụ SSH tới bastion được dùng để quản lý database hoặc Kubernetes cluster; một kết nối được ZTNA cho phép có thể dẫn đến quyền sâu hơn nếu PAM/host authorization yếu.

### 18.1. Mô hình quyền đặc biệt

| Kiểm soát | Mục đích |
| --- | --- |
| Separate privileged account | Không dùng chung danh tính admin và user thường |
| Phishing-resistant MFA | Giảm rủi ro chiếm quyền từ login phishing |
| Just-in-time (JIT) | Chỉ mở quyền trong khung thời gian/ticket |
| Privileged Access Management (PAM) | Quản lý đặc quyền, secret checkout, approval/session |
| Bastion/session proxy | Hạn chế direct SSH/RDP tới mọi host |
| Endpoint posture | Chỉ thiết bị admin được quản lý và kiểm tra |
| Command/session audit | Điều tra thao tác nhạy cảm theo chính sách riêng tư |
| Backend RBAC | Admin chỉ được thao tác trên hệ thống được cấp |

### 18.2. Không dùng ZTNA làm substitute cho privileged identities

Quyền **kết nối SSH TCP 22** không tự cấp quyền **root**. Cần host key verification, SSH certificate/key rotation, tài khoản host, sudo/RBAC và kiểm soát session. Tương tự, quyền kết nối **Kubernetes API** không thay RBAC/admission của cluster.

### 18.3. Break-glass khi IdP/ZTNA unavailable

Thiết kế **khả năng khôi phục có giới hạn**, không đặt một bypass public vĩnh viễn:

1. Định nghĩa **kịch bản kích hoạt** và người phê duyệt.
2. Chuẩn bị **đường quản trị độc lập** theo khả năng hạ tầng (out-of-band, console, segmented emergency VPN).
3. Có chứng thực mạnh, credential cất giữ an toàn, owner và logging.
4. Giới hạn đúng **hosts/service/ports**, thời hạn và audit.
5. Thử định kỳ trong lab/DR exercise.
6. Thu hồi quyền tạm và đối chiếu logs sau sự cố.

**Break-glass phải được thử ngay cả khi IdP, endpoint agent hoặc ZTNA cloud service không truy cập được.** Một tài khoản “emergency” vẫn phụ thuộc đúng IdP đang lỗi không đủ là đường phục hồi.

### 18.4. Không đưa data-plane fail-open làm mặc định

Nếu ZTNA broker mất kết nối, một số session đang hoạt động có thể tiếp tục tồn tại theo cơ chế sản phẩm. Phải ghi rõ **fail mode, session TTL, revocation limitations và monitoring**; không cho broker tự chấp nhận kết nối mới mà chưa xác thực chỉ để tăng availability.

## 19. Cloud, Kubernetes, service mesh và machine-to-machine access

### 19.1. ZTNA cho ứng dụng cloud

Ứng dụng ở VPC/VNet có thể nằm sau private load balancer, container service hoặc Kubernetes Service. Connector đặt trong cloud phải có **private route và firewall** đến app, tránh công bố public LB ngoài ZTNA không được kiểm soát.

Lớp bảo vệ:

1. **ZTNA user policy** cấp quyền tới app.
2. **Cloud security group/network firewall** chỉ cho connector/broker path được duyệt.
3. **Kubernetes NetworkPolicy** giới hạn ingress tới backend Pods nếu CNI thực thi.
4. **Service mesh mTLS/AuthorizationPolicy** xác thực workload peers khi triển khai.
5. **Application/API authorization** kiểm tra JWT/audience/scope/tenant.

### 19.2. Không xem ZTNA như Kubernetes NetworkPolicy

ZTNA có thể giới hạn **người dùng từ xa tới private app**, nhưng một Pod bị xâm nhập trong cùng cluster vẫn có thể gọi backend trực tiếp nếu network/mesh policy rộng. Cần **east–west microsegmentation** riêng.

### 19.3. Truy cập máy-máy

Nếu hệ thống backup on-prem cần ghi dữ liệu vào storage cloud, một **site-to-site VPN/IPsec, private interconnect, service mesh mTLS hoặc workload identity** có thể thích hợp hơn một user-facing ZTNA. Dùng **service principals và resource authorization**; không tự đặt thông tin đăng nhập user lên batch servers để giữ kết nối.

### 19.4. API gateway và access token

Một client ZTNA được phép kết nối API vẫn cần **access token đúng issuer/audience và scope**, backend cần object/tenant authorization. Đường ZTNA không tự biến một ID token thành API access token hoặc bỏ qua application authentication.

### 19.5. Multi-cloud/multi-region

Nếu connector ở nhiều regions:

- Thiết kế policy/trust đồng nhất nhưng giới hạn dữ liệu theo region.
- Test DNS, latency, PoP routing và certificate chain.
- Kiểm tra compliance/data residency của **broker data plane**.
- Giới hạn cross-region failover vào những backends được duyệt.
- Ghi correlation logs xuyên regions theo quyền và retention.

### 19.6. Zero Trust và nội bộ văn phòng

Migration chỉ user remote nhưng vẫn cho phép nhân viên **ở LAN công ty truy cập thẳng** mọi app nhạy cảm có thể tạo posture inconsistent. Tùy mô hình, có thể áp **ZTNA same-access policy bất kể user location** hoặc kết hợp NAC/microsegmentation; không coi việc cắm vào văn phòng là bằng chứng user đã được phép.

## 20. Observability: đo hiệu quả thay vì chỉ đếm login thành công

### 20.1. Nguồn telemetry

| Nguồn | Thông tin có thể cung cấp | Giới hạn |
| --- | --- | --- |
| **ZTNA broker/PEP logs** | Identity, resource, session, policy decision, device state | Không biết mọi object/backend data access |
| **IdP logs** | MFA, token/session issuance, risky sign-ins | Không tự chứng minh đường mạng đã được giới hạn |
| **MDM/EDR** | Device compliance, detections, risk updates | Posture có thể stale |
| **Connector logs/health** | App connection, transport errors, PoP/relay, backend reachability | Không luôn thấy user identity chi tiết |
| **VPN gateway** | User/assigned IP/routes/legacy connections | Không tự chứng minh app-level authorization |
| **Cloud firewall/flow logs** | CIDR/port/NAT/allow-deny ở ranh giới cloud | Không thấy mọi payload/user identity |
| **DNS resolver logs** | FQDN và lỗi phân giải | Không chứng minh mọi kết nối dùng resolver này |
| **App/API/database logs** | Operation, user/tenant, authorization verdict | Không thấy packet bị chặn trước app |
| **PAM/session audit** | Privileged access actions | Chỉ các phiên qua PAM được instrumented |

### 20.2. Các KPI/KRI có ý nghĩa

| Chỉ số | Ý nghĩa |
| --- | --- |
| % ứng dụng có owner và dependency inventory | Mức độ sẵn sàng migration |
| % remote users truy cập đúng app mà không cần VPN route rộng | Kết quả chuyển đổi quyền |
| Số subnet/ports reachable từ user sau migration | Bề mặt lateral movement còn lại |
| % apps có policy theo named resource và conditional access | Mức độ least privilege |
| Số connector có egress allow-all | Rủi ro connector overprivilege |
| Session revocation latency sau disable user/posture failure | Hiệu lực thu hồi |
| ZTNA allow/deny by app, role, posture | Tình trạng sử dụng chính sách |
| Application success rate/latency p95/p99 | Tác động người dùng |
| Number of DNS/SSO/agent conflicts | Vấn đề coexistence |
| Direct-backend bypass findings | Khả năng bảo vệ ngoài broker |
| VPN exceptions quá hạn | Technical debt còn lại |
| MTTR và support tickets theo app/device | Độ ổn định triển khai |

### 20.3. Quyền riêng tư và tối thiểu hóa logs

Logs ZTNA có thể tiết lộ **user, location/IP, lịch sử truy cập app, posture và thông tin thiết bị**. Cần:

- Mục đích sử dụng và retention minh bạch.
- RBAC cho SOC/help desk/application owner theo nhu cầu.
- Pseudonymization/redaction khi phân tích tập trung.
- Tránh lưu **Bearer token, private keys, cookies, nội dung nhạy cảm**.
- Audit người đã truy cập hoặc xuất logs.

### 20.4. Log giả lập: access bị từ chối vì posture

~~~json
{
  "timestamp": "2026-11-28T14:15:00+07:00",
  "dataset": "synthetic-training-event",
  "event_type": "ztna_access_decision",
  "subject_ref": "user-lab-0042",
  "identity_provider": "enterprise-idp-lab",
  "resource_id": "app-hr-portal",
  "requested_fqdn": "hr.internal.example.test",
  "protocol": "HTTPS",
  "device_ref": "managed-laptop-lab-17",
  "device_compliance": "non_compliant",
  "mfa_result": "pass",
  "decision": "deny",
  "reason": "device_posture_requirement_not_met",
  "policy_version": "ztna-policy-lab-07",
  "session_created": false,
  "request_id": "req-ztna-lab-042"
}
~~~

**MFA hợp lệ nhưng posture không đạt ⇒ vẫn có thể deny.** Đây là schema tự xây dựng cho lab, không phải log chuẩn của một vendor.

### 20.5. Log giả lập: phát hiện VPN route bypass

~~~json
{
  "timestamp": "2026-11-28T14:20:00+07:00",
  "dataset": "synthetic-training-event",
  "event_type": "access_path_discrepancy",
  "subject_ref": "pilot-user-lab-011",
  "resource_id": "app-orders-portal",
  "ztna_decision": "deny",
  "ztna_reason": "resource_not_assigned",
  "legacy_vpn_connected": true,
  "legacy_path_to_resource": "reachable",
  "network_source": "10.77.0.42",
  "network_destination": "10.20.10.15",
  "risk": "deny_bypassed_by_remaining_vpn_access",
  "recommended_action": "restrict_legacy_acl_before_claiming_ztna_enforcement"
}
~~~

Đây là tình huống giả lập cho thấy **policy ZTNA deny chưa phải bảo vệ thực sự** nếu ứng dụng vẫn có đường VPN khác. Cần phối hợp route/firewall logs để chứng minh path thật và tác động.

## 21. Mô hình chính sách ZTNA trung lập với sản phẩm

YAML dưới đây mô tả **ý định bảo mật, điều kiện phê duyệt và bằng chứng kiểm thử**. Nó **không phải cấu hình áp trực tiếp** vào một dịch vụ ZTNA, firewall, VPN, IdP hoặc Kubernetes:

~~~yaml
ztnaMigrationPolicy:
  name: remote-access-modernization
  environment: isolated-training
  ownership:
    sponsor: security-architecture
    identityTeam: identity-platform
    networkTeam: network-operations
    applicationOwner: orders-team
    serviceDesk: employee-it
  sourceOfTruth:
    identities: approved-enterprise-idp
    devicePosture: approved-mdm-and-edr
    applications: owned-application-catalog
    changeApproval: controlled-ticket-workflow
  policyDefaults:
    unauthenticated: deny
    unassignedApplication: deny
    missingRequiredDeviceSignal: deny-sensitive-access
    directBackendBypass: deny
    unknownConnectorDestination: deny
    requireTlsIdentityValidation: true
    requireApplicationAuthorization: true
  applications:
    - id: app-orders-portal
      destination:
        hostname: orders.internal.example.test
        protocol: HTTPS
        port: 443
      allowedSubjects:
        - sales-staff
      controls:
        mfa: required
        device: managed-and-compliant
        maxSessionAge: according-to-risk-policy
        actionScope: app-connect-only
      connectorPool: corporate-web
      backend:
        allowedSource: corporate-web-connectors-only
        enforceApplicationTokenAndObjectRights: true
      legacyVpn:
        mode: phased-disable
        denyLegacyPathAfterAcceptance: true
    - id: app-hr-portal
      destination:
        hostname: hr.internal.example.test
        protocol: HTTPS
        port: 443
      allowedSubjects:
        - hr-staff
      controls:
        mfa: phishing-resistant-preferred
        device: managed-and-compliant
        stepUpForSensitiveActions: true
      connectorPool: restricted-hr
      backend:
        allowedSource: restricted-hr-connectors-only
        applicationAuthorization: mandatory
    - id: admin-bastion
      destination:
        hostname: bastion.internal.example.test
        protocol: SSH
        port: 22
      allowedSubjects:
        - approved-operations-oncall
      controls:
        mfa: phishing-resistant-required
        device: privileged-managed-device
        pamApproval: required
        justInTimeAccess: required
        sessionAudit: according-to-policy
      connectorPool: privileged-admin
      backend:
        hostIdentityValidation: mandatory
        privilegedAuthorization: separate
  connectorControls:
    splitPoolsByTrustZone: true
    restrictConnectorEgressToApprovedApps: true
    restrictBrokerOutboundDestinations: true
    rotateConnectorIdentity: true
    avoidUnapprovedPublicInboundListeners: true
    requireHighAvailabilityForCriticalApps: true
  coexistence:
    prohibitUnreviewedVpnRoutesIntoMigratedApps: true
    testDualClientDnsAndProxyBehavior: true
    keepLegacyProtocolExceptionsWithExpiry: true
    requireNegativeTestsWithoutAlternateVpnPath: true
  monitoring:
    correlateIdpZtnaConnectorVpnAndAppEvents: true
    trackSessionRevocationLatency: true
    detectDirectBackendExposure: true
    logPolicyVersionAndDecisionReason: true
    redactSecretsAndSensitiveDeviceData: true
  governance:
    deployViaReviewedChangeControl: true
    requireApplicationOwnerSignOff: true
    requirePilotSuccessAndRollbackTest: true
    expireContractorAndTemporaryAccess: true
    maintainBreakGlassAccess: true
~~~

### 21.1. Phạm vi thực thi của YAML

Một trường như **denyLegacyPathAfterAcceptance: true** không tự tắt VPN route. Cần mapping yêu cầu sang **VPN gateway ACL, firewall, identity group và application publishing policy** của sản phẩm thực. Tương tự, **maxSessionAge** hoặc **sessionAudit** phải được gán giá trị do security policy phê duyệt, không được coi string mô tả là cấu hình đã enforce.

### 21.2. Phải kiểm tra nguồn dữ liệu đầu vào

Policy chỉ đáng tin khi:

- IdP group không bị thêm thành viên trái phép.
- Device posture đến từ agent/cert/MDM được xác minh.
- App resource trong catalog có owner và endpoint xác định.
- Connector group/pool thực sự giới hạn network reachability.
- Policy version và audit records được bảo vệ khỏi chỉnh sửa tùy tiện.

### 21.3. Policy có thể là app connect, không phải business action

Nếu PEP chỉ hỗ trợ **TCP connect** tới HTTPS service, nó không tự phân biệt **read/write/export** bên trong API. **Authorization theo operation và object thuộc application hoặc L7 gateway có khả năng thực thi thật**. Đừng dùng một YAML intent để bỏ qua kiểm tra ở backend.

## 22. Pseudocode của quyết định truy cập và thu hồi phiên

Ví dụ logic **phòng vệ**; không phải mã của vendor và không chứa cơ chế bypass:

~~~text
evaluateAccess(request):
    subject = verifyIdentityProviderAssertion(request.identity)
    if subject is invalid or disabled:
        return DENY("invalid_identity")

    resource = resolveApprovedApplication(request.resourceId)
    if resource does not exist:
        return DENY("unknown_application")

    if not isAssigned(subject, resource):
        return DENY("resource_not_assigned")

    if not hasRequiredAuthenticationStrength(subject, resource):
        return REQUIRE_STEP_UP("mfa_required")

    device = verifyTrustedDevicePosture(request.deviceEvidence)
    if resource.requiresManagedDevice and not device.isTrustedCompliant:
        return DENY("device_posture_noncompliant")

    if riskPolicyRequiresReview(subject, device, resource, request.context):
        return DENY_OR_REVIEW("context_risk")

    if resource.expiryReached or grantExpired(subject, resource):
        return DENY("grant_expired")

    return ALLOW_SESSION(
        resource=resource.approvedFqdnAndPort,
        policyVersion=activePolicyVersion,
        maxLifetime=approvedSessionTtl,
        monitorPostureAndIdentityChanges=true
    )

enforceConnection(session, actualDestination):
    assert session.authorized
    assert destinationMatchesApprovedResource(actualDestination, session.resource)
    assert protectedTransportAndEndpointIdentity(actualDestination)
    assert connectorNetworkPolicyAllowsOnlyApprovedBackend(actualDestination)
    forwardOnlyAuthorizedApplicationTraffic()

onIdentityDisabledOrDeviceNonCompliant(event):
    invalidateApplicableNewAccessGrants()
    revokeOrTerminateExistingSessionsWithinApprovedSla()
    verifyAtDataPlaneThatRevocationTookEffect()
    emitRedactedAuditEvent()
~~~

### 22.1. Tính liên tục không phải khẩu hiệu

**monitorPostureAndIdentityChanges=true** là một mong muốn; triển khai phải nêu:

- Hệ thống nhận events từ IdP/MDM/EDR qua cơ chế nào?
- Tần suất poll và cache TTL?
- Phiên TCP/WebSocket/SSH đang mở có bị đóng không?
- Nếu event source unavailable, policy xử lý thế nào?
- **Revocation SLA** được đo từ khi nào tới khi nào?

Đừng ghi **“continuous authorization”** chỉ vì người dùng phải đăng nhập mỗi ngày một lần.

### 22.2. Tránh fail-open khi đánh giá policy lỗi

Một missing attribute, timeout từ IdP hoặc invalid device attestation không được tự biến thành **Allow** chỉ để giữ availability. Phải định nghĩa **policy-specific fail mode**, exception có owner, expiry, logging và kế hoạch khôi phục.

### 22.3. PEP phải gắn session với đúng resource

Nếu người dùng được cấp **HR portal HTTPS**, PEP/connector không nên chấp nhận một request tùy ý tới **HR database:5432** chỉ vì chúng cùng subnet. Mapping FQDN/DNS/virtual IP cần được ràng buộc với **approved destination/port và actual backend connection**, bao gồm redirect/alternate addresses.

### 22.4. Resource identity độc lập địa chỉ IP

IP có thể thay do cloud autoscaling. Tuy dùng FQDN/app ID linh hoạt, vẫn cần **DNS integrity, TLS server identity, connector routing** và cơ chế hạn chế app catalog để không chuyển quyền nhầm đích.

## 23. Lộ trình migration theo giai đoạn

### Giai đoạn 0 – Sponsor, scope và tiêu chí thành công

Trước khi mua/cài sản phẩm, xác định:

- Phạm vi: remote human access, partner access, admin access hay cả workload connectivity?
- Apps đầu tiên và apps bị loại trừ.
- Tài sản nhạy cảm cần bảo vệ; trust zones, compliance và data residency.
- Ai là **service owner, identity owner, network owner, SOC owner** và sponsor.
- Mục tiêu về **latency, availability, revoke SLA, help desk tickets, security exposure**.
- Cơ chế rollback/break-glass.

### Giai đoạn 1 – Khám phá và baseline

1. Inventory VPN routes, users, groups, DNS, apps, protocols, dependencies.
2. Đọc firewall/flow/DNS logs được phép và xác minh với application owners.
3. Ghi **current exposure** theo user group và subnet/service.
4. Xây app catalog và phân nhóm **A/B/C/D/E** ở mục 7.
5. Thu thập latency, session rates, failures, peak user counts.
6. Ghi các exceptions VPN hiện có với owner và reason.

### Giai đoạn 2 – Identity, posture và connector foundation

1. Kiểm tra IdP federation, MFA, group ownership và lifecycle.
2. Thiết lập MDM/EDR posture source và exception process.
3. Triển khai connector pools ở trust zones phù hợp.
4. Giới hạn connector egress tới đúng resources, không route all subnets.
5. Cấu hình DNS/private zones, TLS trust và certificate rotation.
6. Bật logs/correlation và health metrics.
7. Kiểm thử HA, broker/control-plane outage mode.

### Giai đoạn 3 – Pilot web apps ít rủi ro

- Chọn app web có owner, HTTPS chuẩn, redirect dễ kiểm soát.
- Dùng nhóm người dùng **đại diện cho các OS/location/identity profiles**.
- Chạy positive tests cho use cases nghiệp vụ và **negative tests** cho app không được quyền.
- Đảm bảo những kết nối pilot không được cấp quyền qua đường VPN cũ tới app đang thử.
- Đo latency, support cases, UX và certificate errors.

### Giai đoạn 4 – Mở rộng theo wave

Chuyển từng nhóm:

1. Standard employee portals.
2. Restricted business apps có posture/JWT.
3. Partner/vendor apps có expiry và sponsor.
4. SSH/RDP/database clients với PAM/JIT.
5. Legacy apps sau khi xử lý dependencies hoặc giữ segmented VPN có kiểm soát.

**Không xếp theo số lượng user đơn thuần**; ứng dụng có ngưỡng rủi ro cao cần thời gian kiểm thử dài hơn dù có ít user.

### Giai đoạn 5 – Giảm quyền VPN

Sau khi một app đạt acceptance:

- Thu hẹp **VPN ACL/route** theo pilot group hoặc tất cả users đã migrate.
- Rà soát direct IP, alternate public LB và LAN-based bypass.
- Xóa group VPN được cấp theo thói quen, không cần nữa.
- Giữ **site-to-site/legacy/emergency paths** đã được phê duyệt riêng.
- Re-run negative tests để chứng minh nguồn ngoài quyền không còn reachability.

### Giai đoạn 6 – Tối ưu và vận hành thường xuyên

- Periodic entitlement reviews, deprovisioning audits.
- Connector pool hardening, upgrades, certificate rotation.
- Incident/runbook drills và break-glass testing.
- Access telemetry và policy drift detection.
- Review chi phí/băng thông/latency/availability cùng owner.

## 24. Canary, change gates, rollback và cutover

### 24.1. Không chuyển cả mạng một lần

Một migration hiệu quả dùng **waves nhỏ** và giới hạn blast radius. Ví dụ kế hoạch minh họa:

| Wave | Workload | Điều kiện mở rộng |
| --- | --- | --- |
| W0 | Lab/staging | Auth, DNS, TLS, protocol tests và deny đều pass |
| W1 | Một app web, pilot users | Owners ký nghiệm thu, tickets/latency trong ngưỡng |
| W2 | Nhiều portal nội bộ | Connector capacity, HA và app mapping ổn định |
| W3 | Sensitive apps | Managed device, strong MFA, resource authz, revoke SLA pass |
| W4 | SSH/RDP/DB qua privileged controls | PAM/JIT, audit, protocol compatibility pass |
| W5 | Legacy/remaining VPN paths | Có thiết kế thay thế hoặc exception time-bound |

### 24.2. Change gates

Mỗi app chỉ được cutover nếu:

1. **Resource owner sign-off**, app catalog và port/dependency coverage xác nhận.
2. IdP/MFA/posture/risk policy được test trên device types mục tiêu.
3. Client DNS/TLS/app auth hoạt động **không dùng VPN rộng**.
4. Connector/backend firewall giới hạn đúng nguồn/đích.
5. Negative test chặn **user không được phép, device non-compliant, direct backend IP và VPN bypass**.
6. App success rate, latency và support tickets trong SLO đã duyệt.
7. Session revocation và break-glass được kiểm tra.
8. Có telemetry, rollback, incident owner và communication plan.

### 24.3. Rollback theo ứng dụng, không mở rộng đường mạng vô hạn

Nếu cần rollback, ưu tiên:

- Khôi phục **một app/group specific VPN ACL** trong thời gian giới hạn.
- Tái áp dụng MFA và source/device restrictions tối thiểu.
- Giữ connector policy/route không bị xóa nhầm.
- Theo dõi lưu lượng quay về VPN và ghi ticket expiry.
- Sau khi sửa, chạy lại **ZTNA allow/deny + VPN bypass** trước khi đóng exception.

**Không dùng rollback “allow entire RFC1918”** hoặc bỏ MFA cho mọi users. Nếu không còn cách duy trì dịch vụ mà không vi phạm policy, báo owner/security để có quyết định ngoại lệ có thời hạn.

### 24.4. Security invariants

Các điều kiện không được thay đổi dù rollout hay rollback:

| Bất biến | Cách xác minh |
| --- | --- |
| Admin endpoints không public | Cloud firewall/asset inventory + negative tests |
| Former users không được vào app | IdP/PEP effective deny và session revoke |
| Device trái posture không vào app nhạy cảm | Decision logs + client test |
| Connector chỉ tới đúng backend | Firewall/effective routes + flow logs |
| App kiểm tra tenant/object | Backend authorization tests |
| Không mở route VPN rộng ngoài exception | VPN ACL/route review và network reachability |
| Credential không lộ trong logs | Log sampling/audit |

### 24.5. Trạng thái “migrate xong”

Một app được coi là **migrated** khi user đúng quyền dùng nó ổn định qua ZTNA, source không đúng quyền bị chặn, **đường legacy VPN đã được thu hồi hoặc có exception rõ**, application authorization vẫn thực thi và owner đã chấp thuận kết quả. **Không dựa duy nhất vào dashboard báo số lượt ZTNA login.**

## 25. Ma trận kiểm thử migration trong lab an toàn

**Phạm vi:** chỉ dùng users, endpoints, tenant data, VPN gateways, IdP và ứng dụng **giả lập hoặc được cho phép kiểm thử**. Không sử dụng credential của người khác, không quét subnet bên thứ ba, không thử bypass production ngoài phạm vi được phê duyệt, không thực hiện DoS và không tạo dữ liệu nhạy cảm trong log. Những phép thử thay đổi account/group/route phải chạy trong **lab có rollback**.

### 25.1. Positive và negative tests

| Mã | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| T-01 | Nhân viên sales đã xác thực mạnh, thiết bị compliant, vào Orders portal | Allow đúng HTTPS app |
| T-02 | Cùng nhân viên truy cập HR portal không được gán | Deny tại PEP, không kết nối backend |
| T-03 | Chỉ có password, thiếu MFA yêu cầu | Deny hoặc require step-up theo policy |
| T-04 | IdP assertion giả lập sai issuer/audience/profile | Từ chối, không tạo session |
| T-05 | User disabled ở IdP trước khi đăng nhập | Deny cấp session mới |
| T-06 | User bị disable khi session đã mở | Thu hồi theo SLA đã phê duyệt và kiểm chứng data plane |
| T-07 | User bị gỡ khỏi group có quyền app | Quyền mới bị từ chối, phiên cũ xử lý theo revoke policy |
| T-08 | Contractor có quyền với Support portal trước expiry | Allow theo phạm vi, MFA và device policy |
| T-09 | Contractor hết thời hạn quyền | Deny; không giữ VPN legacy đường khác |
| T-10 | Thiết bị managed, posture đạt baseline | Cho app theo policy tương ứng |
| T-11 | Thiết bị non-compliant nhưng MFA pass | Deny app nhạy cảm theo posture policy |
| T-12 | Posture signal stale/missing trong lab | Fail mode theo resource sensitivity; không auto allow-all |
| T-13 | Thiết bị BYOD truy cập web clientless được phép | Chỉ các tính năng giới hạn đã phê duyệt |
| T-14 | BYOD cố dùng thick client/protocol ngoài policy | Deny theo catalog/mode |
| T-15 | User dùng URL/FQDN ứng dụng đã publish | Resolve/route đúng và TLS verification thành công |
| T-16 | User thử direct private IP tới app không được gán | Không có đường/được PEP hoặc firewall chặn |
| T-17 | User thử FQDN không thuộc catalog | Deny hoặc không route theo policy |
| T-18 | VPN pilot group vẫn có route tới app bị ZTNA deny | Test phát hiện bypass; migration gate phải fail |
| T-19 | VPN ACL của app đã chuyển bị thu hồi cho pilot user | Không còn alternate VPN path tới app |
| T-20 | VPN còn cần cho legacy app độc lập | Chỉ đúng legacy app/subnet/ports được phép |
| T-21 | Kết nối VPN và ZTNA clients đồng thời trong lab | Không có DNS/route/PAC conflict ngoài thiết kế |
| T-22 | ZTNA client reconnect sau sleep/roaming | Session và DNS chính sách hoạt động, không bypass |
| T-23 | DNS private zone được connector resolve đúng | Backend private IP và TLS hostname đúng |
| T-24 | A record đúng nhưng AAAA đi ngoài ZTNA path | Detect/deny IPv6 bypass |
| T-25 | Proxy callback/redirect sang FQDN thứ hai | Chỉ route được duyệt, không mở wildcard ngoài ý |
| T-26 | App HTTPS có TLS cert sai hostname hoặc chain | Client/connector từ chối, không skip verification |
| T-27 | Backend nhận header X-Authenticated-User giả từ client | Không tin unverified header |
| T-28 | Connector corporate-web chỉ được reach Orders/HR ports | Unauthorized backend/DB destination bị chặn |
| T-29 | Connector muốn mở SSH tới database admin ngoài danh mục | Deny bởi firewall/effective policy |
| T-30 | Connector pool mất một node/AZ trong lab | Failover theo SLO, policy và logs giữ nguyên |
| T-31 | Broker/IdP temporarily unavailable trong lab | Fail mode đã duyệt, không cấp quyền mới trái chính sách |
| T-32 | Connector certificate/key xoay hợp lệ | Kết nối mới tiếp tục được xác thực, không log private key |
| T-33 | SSH qua privileged ZTNA path, host key hợp lệ | Kết nối đúng bastion, PAM/JIT và host auth hoạt động |
| T-34 | SSH cố truy cập host không được cấp | Deny dù cùng subnet với bastion |
| T-35 | RDP client cần channel/UDP theo thiết kế | Compatibility được xác minh; không tự mở toàn mạng |
| T-36 | SMB/AD legacy app trong lab | Những dependencies cần thiết được ghi/đánh giá; không giả tương thích |
| T-37 | Database client giữ pooled connection sau expiry | Session/revoke behavior và DB authorization được đo |
| T-38 | App Orders nhận access token sai audience | Backend/API deny dù ZTNA network allow |
| T-39 | Token đúng nhưng user truy cập object thuộc tenant khác | Backend deny object authorization |
| T-40 | Machine workload cố dùng human ZTNA grant | Từ chối hoặc yêu cầu workload-specific identity |
| T-41 | Admin JIT grant hết thời gian | Không tạo được phiên mới; phiên cũ theo revoke SLA |
| T-42 | Break-glass drill khi IdP unavailable trong lab | Đường phục hồi có owner/MFA/audit, không mở all-network |
| T-43 | App chỉ được qua ZTNA nhưng vẫn có public backend LB | Detect, gate fail và containment |
| T-44 | App đang dùng ZTNA nhưng người dùng ở LAN gọi trực tiếp | Phân tích theo expected internal policy, không mặc định an toàn |
| T-45 | IAM/connector/firewall rule bị đổi ngoài IaC | Drift/audit alert, change control xử lý |
| T-46 | ZTNA policy rollout canary rồi rollback | Allow/deny và security invariants vẫn giữ |
| T-47 | Client không được phép thử app ngoài catalog bằng port khác | Deny hoặc không có route theo policy |
| T-48 | Kiểm tra application latency p95/p99 sau migration | Trong SLO và user owner nghiệm thu |

### 25.2. Bằng chứng tối thiểu cho mỗi ca

1. **Environment và giấy phép kiểm thử**, subject/device refs đã che dữ liệu cá nhân.
2. **Resource ID, FQDN, port, protocol**, app owner và policy version.
3. Identity evidence **dạng kết quả xác minh**, không lưu token/password/cert private key.
4. Posture signal source, snapshot age và quyết định theo policy.
5. **ZTNA broker/PEP decision** và session created/denied/revoked.
6. **VPN legacy route/ACL status** và actual data path khi thử deny.
7. **Connector→backend firewall evidence**, DNS/TLS/server identity.
8. **Application authorization outcome** độc lập network.
9. Thời điểm, request ID, latency, flow logs và **nguồn tạo evidence**.
10. Tác động tới client hợp lệ và rollback ticket nếu có thay đổi.

### 25.3. Vì sao chỉ thấy “Access denied” chưa đủ?

Một lỗi UI **Access denied** có thể do IdP, ZTNA policy, posture, connector DNS, upstream TLS, backend 403 hoặc client không có route. Để kết luận **ZTNA resource policy đã deny đúng**, cần thấy **PEP decision từ chối**, không có connector→backend flow được phép, và **không tồn tại path khác** qua VPN/Internet/LAN theo phạm vi cần bảo vệ.

### 25.4. Vì sao một kết nối thành công chưa đủ?

Nếu một pilot user gọi Orders thành công, có thể request **đi qua VPN cũ** vì DNS/route precedence thay vì ZTNA. Cần kiểm tra **PEP session ID, connector flow, application logs và đường legacy VPN**. Tương tự, backend HTTP 200 không cho biết thiết bị đã qua posture check.

### 25.5. Thử thu hồi phiên đúng nghĩa

Một ca hiệu quả:

1. Đăng nhập user lab được cấp quyền và mở kết nối hợp lệ tới app.
2. Ghi thời điểm session active và policy version.
3. Disable user hoặc làm posture non-compliant trong lab theo quyền.
4. Theo dõi **khi nào kết nối mới bị chặn**.
5. Theo dõi **khi nào session đang mở ngừng được sử dụng**.
6. So sánh với SLA/TTL và tìm cache/long-lived session limitations.
7. Đối chiếu application logs, không chỉ nhìn trạng thái portal.

**Không giả định tất cả giao thức TCP hoặc phiên đã thiết lập bị đóng cùng một thời điểm.** Kết quả phải phản ánh đúng năng lực và fail mode thực của sản phẩm.

## 26. Runbook: user không truy cập được ứng dụng sau cutover

**Tình huống:** Nhân viên thuộc nhóm sales được chuyển từ VPN sang ZTNA. Sau cutover, một số người không vào được Orders portal; những người khác vẫn hoạt động. Phản hồi support là **“ZTNA không chạy”** nhưng chưa xác định lớp gây lỗi.

### Giai đoạn 1 – Phân loại triệu chứng

| Triệu chứng | Nhóm nguyên nhân cần xem |
| --- | --- |
| Không vào được portal đăng nhập | DNS/proxy/Internet reachability, IdP outage |
| MFA loop hoặc redirect error | IdP federation, cookies/callback, time skew |
| “Device not compliant” | MDM/EDR sync, enrollment, posture policy |
| “Application not assigned” | Group membership, catalog, user role |
| DNS NXDOMAIN/private hostname sai | Client ZTNA DNS mapping, split DNS, resolver |
| Connection timeout sau khi PEP allow | Connector health, route/firewall, backend listener |
| HTTPS certificate/hostname error | TLS SAN/SNI, connector upstream trust |
| HTTP 401/403 | API authentication/authorization, user/tenant rights |
| Chỉ Windows/Mac/mobile lỗi | Agent compatibility, OS DNS/network filters |
| Chỉ ngoài văn phòng lỗi | Network path, captive portal, Internet/PoP |
| Chỉ sau sleep/resume lỗi | Cached DNS/route/session, agent reconnection |
| Chỉ một region lỗi | Connector pool/PoP routing/zone availability |

### Giai đoạn 2 – Thu thập sự kiện không lộ bí mật

Ghi **app ID, thời điểm, request ID, client OS/agent version, user ref, device compliance state, location loại mạng, IdP result, PEP decision, connector health, backend status**. **Không yêu cầu user gửi mật khẩu, token, private key hoặc screenshot chứa secrets**.

### Giai đoạn 3 – Đi theo chuỗi kiểm tra

1. **Identity:** IdP login/MFA có thành công và token/assertion thuộc đúng app không?
2. **Assignment:** User/group có quyền app đúng policy version không?
3. **Device posture:** endpoint đủ điều kiện và signal có còn hiệu lực không?
4. **Client DNS/routing:** FQDN đi qua ZTNA path hay trôi vào VPN/ISP resolver?
5. **Broker/PEP:** request có decision gì, session đã được tạo không?
6. **Connector:** healthy, đúng pool/region và có route tới backend không?
7. **Backend TLS:** certificate/hostname/chain đúng không?
8. **Application:** có listener, health và quyền user/tenant không?
9. **Alternatives:** app có đường Internet/VPN/LAN không được dự kiến không?
10. **Evidence:** correlate logs cùng timestamps/request IDs.

### Giai đoạn 4 – Khắc phục phạm vi hẹp

- Sai group assignment: xác minh **owner approval** trước sửa, không cấp all-apps.
- Posture stale: xử lý MDM/EDR health, không tự vô hiệu hóa posture cho toàn tổ chức.
- DNS sai: sửa private DNS/agent config, không gán public resolver tùy tiện.
- Connector lỗi: thay pool/repair network/cert theo runbook, không công bố backend public.
- App 401/403: chuyển tới app owner kiểm tra token/resource rights, không nới network ACL.
- Legacy protocol không hỗ trợ: dùng **segmented VPN exception có hạn**, không đánh đồng với migration thành công.

### Giai đoạn 5 – Rollback nếu cần

Nếu ảnh hưởng vượt SLO, kích hoạt rollback **chỉ app/wave bị lỗi**. Giữ identity/MFA và ACL giới hạn. Ghi owner, expiry, user impact và time window; sau sửa phải chạy lại cả allow/deny và kiểm tra VPN bypass.

### 26.1. Sự cố ZTNA deny nhưng VPN cũ vẫn cho phép

Nếu pilot user bị broker deny nhưng ứng dụng vẫn reachable qua VPN:

1. Xác định route và **effective VPN ACL** tại đúng gateway.
2. Đối chiếu destination IP/NAT và flow log backend.
3. Khoanh vùng legacy ACL tới app/nhóm cần thiết, không thu hồi toàn bộ tunnel không liên quan.
4. Kiểm tra không có direct public/IPv6 path.
5. Chạy negative test lại khi VPN path đã bị ràng buộc.
6. Đánh dấu **security acceptance failed** cho đến khi nguồn không được cấp không còn đường vào.

### 26.2. Sự cố thu hồi phiên không hiệu lực

Khi user đã bị disable nhưng một kết nối cũ còn dùng được, cần kiểm tra:

- Session/token TTL, active session binding và broker revocation mechanism.
- IdP group sync interval, connector/access policy cache.
- Long-lived SSH/RDP/WebSocket/TCP sessions.
- Backend có tự kiểm tra user authorization hay chỉ tin kết nối lúc bắt đầu?
- Revocation SLA có áp riêng cho **new sessions** và **existing sessions**?

Nếu quyền dữ liệu nhạy cảm bị ảnh hưởng, phối hợp **app/API/token revocation và network containment** theo quy trình incident, không trông chờ chỉ một sự kiện IdP.

## 27. Tình huống tổng hợp: chuyển HR portal sang ZTNA nhưng giữ VPN và mạng cũ

**Bối cảnh:** Doanh nghiệp có 800 nhân viên, 60 nhà thầu, hai VPC cloud và trung tâm dữ liệu. HR portal nằm tại **hr.internal.example.test**, dùng HTTPS. Trước migration, nhân viên kết nối VPN nhận route tới **10.30.0.0/16**. Firewall cho phép truy cập HR portal và nhiều dịch vụ vận hành khác từ VPN client pool.

Đội dự án chọn một nhóm pilot 40 người, cấu hình ZTNA connector gần HR portal, áp IdP MFA, posture managed device và policy **hr-staff → HR app:443**. Kết quả pilot: mọi người vào được HR portal, dashboard ZTNA báo 100% request thành công. Nhóm dự án định cắt VPN ngay.

### 27.1. Các vấn đề chưa được nhận diện

1. **Tất cả pilot users vẫn có VPN route/ACL cũ** tới 10.30.0.0/16. Một số ứng dụng có thể đi theo VPN thay vì connector khi hai agents hoạt động.
2. **Connector subnet được phép tới cả 10.30.0.0/16**, thay vì chỉ HR frontend/backend destinations.
3. HR portal còn gọi **document share qua SMB** từ một thick client tool dùng trong quy trình payroll, chưa được app catalog liệt kê.
4. Một nhóm nhà thầu có account được tạo trực tiếp trong HR portal, **không thuộc IdP group governance**.
5. HR backend có **NodePort/public LB cũ ở cloud DR** mà edge inventory chưa ghi.
6. Endpoint dùng browser đúng nhưng **application object-level RBAC** chưa phân biệt HR staff toàn công ty và HR manager của từng đơn vị.

### 27.2. Tại sao số liệu đăng nhập không đủ?

Số liệu 100% ZTNA login chỉ chứng minh **những bước xác thực được quan sát**. Chúng không chứng minh:

- Traffic thực sự đi qua connector trong mọi use case.
- Subnet không còn reachable theo VPN cũ.
- Connector không thể dùng để gọi các backend khác.
- Payroll file workflow hoạt động sau khi VPN bị cắt.
- Nhà thầu đã được cấp quyền đúng/hết hạn.
- HR application không trả hồ sơ người khác.

### 27.3. Kế hoạch sửa từng lớp

| Vấn đề | Hành động | Bằng chứng |
| --- | --- | --- |
| VPN path vẫn tới HR | Thu hẹp route/ACL cho pilot tới app đã chuyển, giữ legacy khác riêng | Negative tests + VPN/backend flows |
| Connector đi cả subnet | Chỉ cho connector đến HR endpoints/ports được duyệt | Effective firewall + denied destinations |
| Payroll SMB chưa catalog | Tách workflow/VDI hoặc segmented VPN exception | End-to-end payroll test |
| Contractor local accounts | Đồng bộ identity governance/sponsor/expiry hoặc thu hồi | App/IdP user reconciliation |
| DR public LB | Inventory, khóa origin, xét IPv6/NodePort | External reachability tests |
| HR role quá rộng | App RBAC/tenant-object policy và audit | Cross-role negative tests |

### 27.4. Diễn giải kiến trúc sau khi sửa

~~~mermaid
flowchart TB
    H["HR employee / managed compliant device"] -->|"IdP MFA + app assignment"| Z["ZTNA broker/PEP"]
    Z -->|"Approved session"| C["Restricted HR connector"]
    C -->|"HTTPS 443, backend allowlist"| HR["HR portal"]
    HR -->|"HR role + record authorization"| D[("Personnel records")]
    V["Legacy VPN client"] -. "Không còn route tới HR qua nhóm đã migrate" .-> HR
    C -. "Không được scan/access các hệ thống khác" .-> O["Other subnet resources"]
    L["Payroll legacy workflow"] -->|"Temporary segmented access"| S["SMB/VDI path"]
    DR["Old DR public LB"] -. "Blocked/removed" .-> HR
    SOC["SOC"] -. "Review logs, exceptions, revocation" .-> Z
    SOC -. "Network and app audit" .-> HR
~~~

### 27.5. Quyết định cuối cùng

Không cắt toàn bộ VPN vào một thời điểm nếu payroll/DR/legacy admin workflows còn phụ thuộc. Cắt **theo app và nhóm** khi:

1. Mọi đường access đã được inventory.
2. Luồng HR được cấp quyền đi đúng ZTNA path.
3. Người ngoài HR và thiết bị trái posture không vào HR.
4. VPN/client legacy path đã bị thu hẹp.
5. Connector chỉ tới đúng HR backend.
6. Application HR role/tenant authorization được kiểm tra.
7. Có fallback có hạn và logs đầy đủ.

**Bài học:** migration không đạt chỉ nhờ thay cổng đăng nhập; cần chứng minh **reachability đã giảm, quyền dữ liệu vẫn được bảo vệ và các dependency legacy không bị bỏ quên**.

## 28. Những sai lầm phổ biến khi migrate VPN sang ZTNA

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| “VPN luôn cho toàn mạng, ZTNA luôn an toàn hơn” | So sánh theo nhãn thay vì effective access | Đo routes, ACL, app reachability và policy enforcement thực |
| “Mục tiêu là bỏ VPN bằng mọi giá” | Legacy/DR/site-to-site flows hỏng hoặc mở exception rộng | Migrate theo app, giữ segmented VPN được duyệt khi cần |
| “ZTNA không dùng tunnel” | Hiểu sai dataplane, direct/relay, firewall needs | Xác minh sản phẩm thực sự chuyển traffic thế nào |
| “IdP login thành công là được vào mọi app” | Quên resource assignment/authorization | Policy per app, group/role, device và expiry |
| “MFA là đủ để cấp quyền admin” | Device bị nhiễm hoặc user không có JIT role vẫn vào | Posture, PAM/JIT và backend admin auth |
| “MDM compliant nghĩa là endpoint không thể bị xâm nhập” | Tin tuyệt đối vào signal cũ | EDR, risk signals, least privilege, revocation |
| “Device signal mất thì allow để khỏi gián đoạn” | Fail-open app nhạy cảm | Fail mode theo risk, exception hạn chế |
| “Application catalog chỉ cần hostname đầu tiên” | Redirect/API/SMB/SSO dependencies bị bỏ sót | Dependency mapping và end-to-end flow testing |
| “Proxy web thay được mọi VPN protocol” | RDP/SMB/UDP và thick clients không chạy | Chọn access mode theo protocol support |
| “Bật ZTNA rồi giữ VPN broad route vĩnh viễn” | Chính sách deny bị bypass | Thu hẹp VPN ACL theo waves và negative tests |
| “Cùng một app qua VPN và ZTNA không cần test path” | Không biết traffic đi qua đâu | Correlate PEP session, connector flows, VPN logs |
| “FQDN resolve đúng là người dùng có quyền” | DNS không phải authentication/authorization | TLS, PEP resource policy và backend auth |
| “App ở private subnet là không có public path” | NodePort/LB/IPv6/origin bypass | Asset inventory, firewall và direct-path tests |
| “Connector outbound nên không cần hardening” | Connector thành lateral movement pivot | Egress least privilege, IAM, certificate, HA |
| “Mở connector tới cả subnet để khỏi thiếu port” | Tái tạo quyền VPN quá rộng ở phía connector | Exact backend FQDN/IP/port và dependency list |
| “Ztna agent và VPN agent chắc chắn tương thích” | Route/DNS/proxy conflicts | OS/client coexistence matrix |
| “Browser-based access có DLP tuyệt đối” | Có thể tải/chụp/sao chép theo các cách khác | Test limitations, app controls, device governance |
| “SSL inspection luôn chạy với mọi TLS application” | Pinning/mTLS/QUIC không tương thích | Chọn passthrough hoặc mô hình TLS phù hợp |
| “ZTNA TLS tunnel thay app certificate verification” | Connector→backend có thể không xác minh đúng server | Upstream TLS verification và identity |
| “X-Authenticated-User do client gửi có thể tin” | Identity header spoofing | Strip/replace ở trusted proxy; backend auth |
| “ZTNA xác thực network thì API khỏi kiểm tra tenant” | BOLA/cross-tenant access | Object/business authorization |
| “Disable user IdP là mọi SSH session ngắt tức thời” | Revocation không đạt SLA | Đo active-session termination và app controls |
| “Break-glass nằm trên cùng IdP là đủ” | IdP outage làm mất đường khôi phục | Đường phục hồi độc lập có hạn và audit |
| “Có ZTNA access logs là không cần VPN/app logs” | Không chứng minh data path và quyền resource | Correlate IdP, connector, firewall, app |
| “Network firewall không còn cần thiết” | East-west và non-ZTNA paths không được bảo vệ | Segmentation, IDS/IPS, DNS, TLS cùng hoạt động |
| “Site-to-site VPN nên chuyển sang human agent” | Workload không có human identity flow hợp lý | Workload identity/mTLS, IPsec/private routes |
| “Không thể kết nối tức là đã bị ZTNA deny” | Lỗi DNS/TLS/route/availability bị nhầm | PEP decision và network/backend evidence |
| “HTTP 200 sau migration chứng minh least privilege” | Chỉ chứng minh allow case | Negative resource/device/VPN-bypass tests |
| “Rollback nghĩa là mở lại tất cả routes” | Rủi ro quay về flat access rộng | App-specific time-limited rollback |
| “Không có log deny nghĩa là không có đường bypass” | Coverage gaps/alternate paths | Đo observability và route inventory |
| “Đã áp MFA một lần thì session vô hạn vẫn an toàn” | Session theft/role change kéo dài | Session TTL, step-up, event-driven reevaluation |
| “ZTNA vendor HA có nghĩa app/connector HA” | Connector pool hoặc DNS là điểm lỗi đơn | HA end-to-end, failover/DR drills |

## 29. Câu hỏi ôn tập và bài tập thiết kế

### Câu hỏi 1 – ZTNA khác VPN ở đơn vị cấp quyền ra sao?

**Gợi ý:** VPN thường cung cấp network connectivity rồi dùng ACL; ZTNA hướng tới quyền theo app/resource và ngữ cảnh. Cả hai vẫn cần backend authorization.

### Câu hỏi 2 – Vì sao một VPN được phân đoạn tốt không thể bị gọi tự động là flat network?

**Gợi ý:** effective route/ACL, firewall, posture và MFA có thể giảm phạm vi; phải so theo kết quả truy cập thật.

### Câu hỏi 3 – PE, PA và PEP khác nhau về vai trò nào?

**Gợi ý:** PE đưa ra quyết định, PA điều phối thiết lập/ngắt phiên, PEP thực thi ở đường kết nối; chúng không bắt buộc là ba server.

### Câu hỏi 4 – Một user có MFA thành công nhưng thiết bị không compliant nên được xử lý ra sao?

**Gợi ý:** quyền phụ thuộc app risk và posture policy; ứng dụng nhạy cảm có thể deny, không auto allow-all.

### Câu hỏi 5 – Khi user bị disable, tại sao phiên SSH/RDP đang mở có thể chưa ngắt?

**Gợi ý:** session/token TTL, policy cache, broker data plane và backend connections; phải đo revoke SLA.

### Câu hỏi 6 – Vì sao connector cần firewall egress hẹp dù user chỉ thấy một app?

**Gợi ý:** connector có thể có route rộng tới subnet; policy theo user không tự giới hạn network reachability của connector.

### Câu hỏi 7 – Tại sao không nên dùng direct IP hoặc FQDN giải được làm bằng chứng quyền truy cập?

**Gợi ý:** DNS và routing chỉ định vị/chuyển packet; TLS/server identity, PEP policy và application auth khác nhau.

### Câu hỏi 8 – Một portal HTTPS làm sao biết cần SMB/Kerberos khi chuyển VPN?

**Gợi ý:** inventory client/server dependency flows và workflow end-to-end, không chỉ cổng web chính.

### Câu hỏi 9 – Browser-based ZTNA có phù hợp mọi SSH/RDP/UDP/VoIP app không?

**Gợi ý:** Không; cần protocol support thực, agent/PAM/VDI/VPN thay thế được kiểm chứng.

### Câu hỏi 10 – Vì sao pilot 100% success có thể không chứng minh ZTNA path đang được dùng?

**Gợi ý:** VPN cũ vẫn có route/DNS precedence; cần PEP session và connector + VPN path evidence.

### Câu hỏi 11 – Hệ thống có ZTNA cho nhân viên từ xa nhưng LAN office mở rộng thì đã Zero Trust hoàn toàn chưa?

**Gợi ý:** Chưa; on-network users có thể bypass điều kiện, cần segmentation/identity/policy nhất quán.

### Câu hỏi 12 – ZTNA network allow đến Orders API có cho user đọc mọi order không?

**Gợi ý:** Không. Access token issuer/audience/scope và object/tenant authorization của Orders vẫn bắt buộc.

### Câu hỏi 13 – Device posture và application authorization có thể thay nhau không?

**Gợi ý:** Không. Posture đánh giá thiết bị, app auth kiểm tra người gọi và quyền thao tác lên dữ liệu.

### Câu hỏi 14 – Tại sao IdP outage cần break-glass path độc lập?

**Gợi ý:** Nếu recovery tiếp tục yêu cầu IdP đang lỗi, tổ chức không thể quản trị hạ tầng để khôi phục; quyền khẩn cấp vẫn phải tối thiểu và có audit.

### Câu hỏi 15 – Chuyển VPN site-to-site sang human ZTNA agent có hợp lý không?

**Gợi ý:** Không nhất thiết; service-to-service cần workload identity, mTLS/IPsec/private connectivity theo use case.

### Câu hỏi 16 – Những phép thử nào phải pass trước khi thu hồi VPN route của HR?

**Gợi ý:** Allow cho user HR đúng policy, deny ngoài group/posture, không direct/backend/VPN bypass, login dependencies, revocation và rollback.

### Câu hỏi 17 – Vì sao ZTNA broker logs không đủ kết luận dữ liệu chưa bị truy cập?

**Gợi ý:** Có thể có direct VPN/Internet/LAN paths hoặc backend authorization thiếu; cần firewall/app/DB logs.

### Câu hỏi 18 – Vì sao browser DLP controls không tự ngăn mọi rò rỉ thông tin?

**Gợi ý:** Một số hạn chế UI không chặn được mọi hành vi sao chép/ghi hình hoặc kênh ngoài browser; cần kết hợp data policy/device controls.

### Câu hỏi 19 – Khi agent ZTNA và VPN đồng thời làm DNS resolution sai, bắt đầu ở đâu?

**Gợi ý:** /etc/resolv.conf hoặc OS DNS config phù hợp, search/split DNS, routing, proxy settings, phiên bản agents và FQDN thực tế.

### Câu hỏi 20 – Thế nào là một app “đã migrate” về mặt bảo mật?

**Gợi ý:** App đúng quyền hoạt động, nguồn ngoài quyền bị deny, connector đúng scope, VPN path được thu hồi/exception có hạn, app authorization và telemetry đạt tiêu chí.

### Bài tập thiết kế kiến trúc tổng hợp

Một công ty có **1.200 nhân viên, 150 nhà thầu**, VPN hiện cấp hai routes **10.20.0.0/16** (app/data center) và **10.30.0.0/16** (cloud). Các dịch vụ gồm:

- **Orders web** và **HR web** qua HTTPS nội bộ.
- **ERP thick client** kết nối TCP nhiều cổng, dùng Kerberos/SMB phụ trợ.
- **PostgreSQL reporting** cho BI qua TLS.
- **SSH bastion** cho nhóm on-call.
- **Partner support portal** truy cập từ thiết bị ngoài tổ chức.
- **Kubernetes workload APIs** và site-to-site backup jobs.

Hãy thực hiện:

1. Vẽ kiến trúc **VPN hiện tại**, phân tích những subnet/port nào từng nhóm có thể đến theo effective ACL, không suy từ pushed route đơn thuần.
2. Xây **application catalog** với owner, FQDN, port/protocol, authentication, data sensitivity và dependencies.
3. Phân nhóm **web, TCP, legacy, workload, privileged/break-glass** và giải thích loại ZTNA mode/VPN exception nào phù hợp.
4. Vẽ kiến trúc mục tiêu: **IdP → Policy Engine/Administrator → PEP → private connectors → apps**, đặt connector pools theo trust zones.
5. Định nghĩa **sales, HR, BI, IT admin, contractor** policies với MFA, posture, role, expiry và resource.
6. Viết rule **connector→backend firewall** hạn chế cổng/đích, không cho connector pool chung đi mọi subnets.
7. Thiết kế split DNS/private zone, backend TLS hostname validation và bước kiểm tra IPv4/IPv6.
8. Mô tả integrated auth, OIDC redirects, file share/SMB và cách xử lý **ERP không tương thích** mà không mở VPN toàn mạng.
9. Lập kế hoạch **pilot/waves/cutover** và phân rõ thời điểm thu hồi quyền VPN đối với apps đã migrate.
10. Thiết kế **JIT/PAM, SSH host auth và emergency break-glass** khi IdP/ZTNA outage.
11. Thiết kế policies cho **service-to-service/Kubernetes workloads** tách khỏi human ZTNA.
12. Thiết kế log correlation **IdP, MDM/EDR, PEP, connector, VPN, firewall, DNS và app/database logs**.
13. Đưa ra ít nhất **15 positive/negative test cases**, gồm wrong group, missing MFA, posture failure, direct IP, VPN bypass, cross-tenant, active session revocation, DNS conflict và connector HA.
14. Đặt các **security invariants** phải giữ khi rollback, cùng owner/ticket/expiry của exception.
15. Xác định **SLO/KRI**: availability, p95 latency, session revoke SLA, số VPN paths đã thu hồi, connector overprivilege và stale contractor grants.
16. Viết runbook khi một app đã migrate qua ZTNA nhưng vẫn reachable từ VPN hoặc IPv6 public backend.

**Tiêu chí đạt:** một ứng dụng chỉ có thể truy cập qua **những đường được phê duyệt**, user/device không đủ điều kiện bị từ chối, quyền connector không rộng hơn app catalog, backend vẫn xác minh quyền dữ liệu, legacy workflows có phương án riêng và rollback không tái tạo network-wide access không kiểm soát.

## 30. Những điều cần ghi nhớ

- **VPN bảo vệ đường kết nối; ZTNA hướng tới quyền theo danh tính, ngữ cảnh và từng ứng dụng.** Một VPN phân đoạn tốt không đồng nghĩa flat network, và ZTNA chưa cấu hình đúng không tự an toàn.
- **Migration là thay đổi kiến trúc quyền truy cập**, không chỉ thay VPN client bằng ZTNA agent hoặc chuyển màn hình đăng nhập.
- **Policy Engine, Policy Administrator và Policy Enforcement Point** là vai trò logic; cần biết quyết định được thực thi ở đâu, trong bao lâu và cách thu hồi phiên.
- **Kiểm kê users, VPN routes, DNS, ứng dụng, ports, protocols và dependencies** trước khi chọn access mode; ứng dụng cũ có thể cần VDI/PAM hoặc segmented VPN.
- **IdP, phishing-resistant MFA, device posture, group lifecycle, contractor expiry và access review** quyết định độ tin cậy đầu vào của ZTNA policy.
- **Connector là tài sản có quyền cao**; phải giới hạn egress tới đúng backend, bảo vệ keys/identity và thiết kế HA theo zone.
- **DNS/FQDN, TLS certificate hostname, client proxy/route precedence và IPv4/IPv6** là những nguyên nhân phổ biến khiến pilot chạy nhưng cutover thất bại hoặc tạo bypass.
- **ZTNA broker allow không thay application/API authorization**; token audience/scope và object/tenant rights vẫn cần kiểm tra ở backend.
- **VPN và ZTNA coexistence phải có thời hạn và đường kiểm chứng rõ**; một ZTNA deny bị bypass bởi VPN route cũ nghĩa là yêu cầu least privilege chưa đạt.
- **Site-to-site, machine-to-machine, legacy UDP/SMB và emergency administration** có thể tiếp tục cần kết nối riêng với segmentation, identity và audit phù hợp.
- **Session revocation phải được đo**, không suy user disable ở IdP sẽ đóng mọi kết nối đang mở tức thời.
- **Rollout theo app và wave**, có owner sign-off, positive/negative tests, đo latency/availability và rollback giới hạn theo phạm vi.
- **Không có log deny hoặc một dashboard báo 100% login thành công không chứng minh an toàn**; cần correlation từ PEP, VPN, connector, firewall, DNS và application logs.
- **Mục tiêu cuối cùng là giảm effective reachability và lateral movement**, bảo vệ danh tính/quyền dữ liệu và duy trì khả năng phục hồi khi hệ thống truy cập từ xa gặp sự cố.
