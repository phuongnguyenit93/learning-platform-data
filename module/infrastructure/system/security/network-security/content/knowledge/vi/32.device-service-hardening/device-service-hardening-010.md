# Kiểm soát thay đổi trên router và firewall

Một doanh nghiệp cần mở kết nối từ ứng dụng đặt trong VLAN ứng dụng tới một database trong vùng dữ liệu. Kỹ sư mạng nhận yêu cầu “cho API truy cập database”, rồi thêm một rule **allow toàn bộ VLAN ứng dụng đến cả subnet database** để xử lý nhanh. Kết nối bắt đầu hoạt động, ticket được đóng. Vài ngày sau, đội bảo mật phát hiện một máy thuộc VLAN ứng dụng có thể quét cổng và truy cập nhiều dịch vụ quản trị database không liên quan. Rule mới đã giải quyết yêu cầu kinh doanh, nhưng đồng thời tạo **đường lateral movement ngoài phạm vi cho phép**.

Một trường hợp khác: kỹ sư thay route ưu tiên trên router biên để chuyển traffic tới nhà cung cấp Internet mới. Sau khi áp dụng, đường SSH quản trị đi qua chính router đó cũng đổi, làm mất kết nối của kỹ sư; dịch vụ quan trọng bị blackhole, nhưng không còn kênh quản trị để rollback. **Thay đổi hợp lệ về mặt cú pháp vẫn có thể làm mất an toàn hoặc tính sẵn sàng**.

**Kiểm soát thay đổi trên router và firewall** là quy trình quản trị toàn bộ vòng đời của một thay đổi cấu hình: **đề xuất → phân tích rủi ro/phụ thuộc → xét duyệt → chuẩn bị và sao lưu → xác minh → triển khai có kiểm soát → kiểm tra thực tế → hoàn tác nếu cần → lưu bằng chứng và rà soát**. Không phải mọi thay đổi đều cần quy trình nặng như nhau, nhưng mọi thay đổi có thể ảnh hưởng production phải có **người chịu trách nhiệm, mục đích, phạm vi, tiêu chí thành công và phương án phục hồi** tương xứng.

Bài thuộc chương **Hardening thiết bị và dịch vụ mạng** trong module **SECURITY_NETWORK_SECURITY**. Nội dung gắn với phân đoạn mạng, firewall, routing, VPN, IDS/IPS, DNS, network access control, zero trust, cloud networking, giám sát và ứng phó sự cố.

> **Nguyên tắc xuyên suốt:** Một thay đổi không thành công chỉ vì câu lệnh được thiết bị chấp nhận hoặc ứng dụng trả HTTP 200. Nó chỉ đạt yêu cầu khi **các luồng phải hoạt động vẫn hoạt động, các đường phải bị chặn vẫn bị chặn, trạng thái thực tế khớp thiết kế và có thể chứng minh/hoàn tác kết quả**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân loại **standard/normal/emergency changes**, xác định tác động và yêu cầu phê duyệt theo rủi ro.
2. Phân biệt **intended configuration, running configuration, committed configuration, effective policy và forwarding behavior**.
3. Lập **change request** mô tả source, destination, application/protocol, identity/zone, owner, window, risk và expected results.
4. Phân tích rủi ro trước thay đổi đối với **ACL/security policy, NAT, route, BGP, OSPF, VPN, HA, IPv4/IPv6 và management plane**.
5. Sử dụng **least privilege, separation of duties, MFA, RBAC, version control, peer review, config backup và integrity/audit logs**.
6. Thiết kế **pre-change baseline, canary, positive/negative test matrix và rollback triggers**.
7. Giải thích giới hạn của **commit-confirmed, candidate configuration, staging/commit, HA sync và automation pipelines** giữa các nhà sản xuất.
8. Tổ chức **thay đổi khẩn cấp** không biến emergency exception thành cửa hậu tồn tại vô hạn.
9. Phát hiện **policy drift, shadowed/overlapping rules, route asymmetry, NAT mismatch, mất đường quản trị và service dependencies**.
10. Viết playbook có thể kiểm toán, kèm timeline, owner, verification evidence và cải tiến sau thay đổi.

## 2. Vì sao router/firewall change là một security boundary?

Một router có thể quyết định traffic được chuyển đến đâu, đường ưu tiên, điểm NAT, mạng nào được quảng bá hoặc dùng để quản trị hạ tầng. Một firewall có thể kiểm soát giao tiếp giữa vùng tin cậy khác nhau, nhưng **rule policy, object group, NAT, zones, session state và route** cùng quyết định hành vi thực.

~~~mermaid
flowchart LR
    U["User / workload zone"] --> FW["Firewall + NAT + state"]
    FW --> R["Router / routing decision"]
    R --> D["Application / data zone"]
    ADM["Management / control plane"] -.->|"Policy & route updates"| FW
    ADM -.-> R
    AUD["Change approval, versioning & audit"] -.-> ADM
    TEST["Traffic verification"] -.-> FW
    TEST -.-> R
~~~

**Các lớp khác nhau có thể phủ quyết hoặc cho phép luồng**. Firewall allow TCP/5432 không có nghĩa DB reachable nếu route sai, service down hoặc TLS/DB authorization thất bại. Ngược lại, network connection thành công không chứng minh quyền database theo từng user hoặc object là đúng.

### 2.1. Hai mục tiêu đôi khi xung đột

| Mục tiêu | Ví dụ | Rủi ro khi chỉ tối ưu một chiều |
|---|---|---|
| **Confidentiality / Integrity** | Chỉ cấp API→DB TCP/5432 | Deny quá rộng làm đứt dịch vụ |
| **Availability / Resilience** | Chuyển traffic sang uplink còn khỏe | Mở route/ACL quá rộng làm lộ management/data zone |
| **Least privilege** | Giới hạn một service identity hoặc host | Hệ thống legacy/DNS/NAT làm mapping khó |
| **Change velocity** | Triển khai cấu hình nhanh | Không có peer review, tests, backup |
| **Forensic integrity** | Lưu logs/config diff để điều tra | Debug/copy dữ liệu nhạy cảm vượt nhu cầu |

**Một thay đổi tốt** được thiết kế để vừa đáp ứng business requirement vừa duy trì security invariants và có phương án cứu hộ.

### 2.2. Cái gì thực sự thay đổi?

Không chỉ có dòng `permit/deny`. Những đối tượng cấu hình ảnh hưởng tới security boundary gồm:

- **Firewall rules/ACLs:** source/destination, services, applications, users, zones, action, logging.
- **Network objects:** address groups, FQDN objects, dynamic tags, port groups.
- **NAT/PAT:** source NAT, destination NAT, port translation, policy NAT, exemptions.
- **Routing:** static routes, default route, PBR, VRFs, OSPF/BGP neighbors, filters, route redistribution.
- **VPN/remote access:** IPsec parameters, crypto identity, routing selectors, split/full tunnel.
- **HA/clustering:** active/standby, sync, session failover, routing advertisements.
- **Management plane:** admin accounts, TACACS+/RADIUS, MFA, SSH/API access, SNMP, syslog, NTP, backup.
- **Cloud equivalents:** virtual firewall, cloud route tables, security groups, NACLs, transit gateways, VPC peering.
- **Policy automation:** IaC templates, GitOps controller, secret/config stores và API roles.

**Một thay đổi object group có thể ảnh hưởng hàng chục rule** dù ticket ghi chỉ “sửa một địa chỉ”. Review phải xét **tham chiếu/effective scope**, không chỉ số dòng được chỉnh.

## 3. Phân biệt các trạng thái cấu hình và đường đi

| Trạng thái | Ý nghĩa | Không bảo đảm |
|---|---|---|
| **Desired state** | Cấu hình/đường đi được thiết kế, đã được owner phê duyệt | Chắc đã deploy hay mọi thiết bị khớp |
| **Candidate configuration** | Bản chuẩn bị thay đổi trên một số nền tảng | Chắc đã active; có thể còn lỗi commit |
| **Running/effective config** | Cấu hình thiết bị đang áp theo cơ chế nền tảng | Traffic thực đã match đúng rule |
| **Saved/startup config** | Cấu hình dùng sau reboot theo nền tảng | Giống running config ngay lúc đó |
| **Control-plane state** | Routing neighbors, RIB, policy distribution, cluster sync | FIB/hardware đã nhận đúng |
| **Data-plane state** | Forwarding table/hardware ACL, conntrack/session state | App/tenant authorization đúng |
| **Observed traffic** | Packet/flow/log tại một điểm quan sát | Mọi luồng hoặc mọi network path đều giống |

**Với firewall stateful**, connection có thể được tạo trước khi rule mới triển khai và còn tồn tại trong session table. Vì vậy **effective policy mới** chưa chắc làm mọi **phiên đang mở** bị ngắt theo cùng semantics trên mọi vendor.

### 3.1. Bẫy “chạy lệnh thành công”

Một platform CLI/API trả **success** có thể chỉ xác nhận cấu hình đã:

1. Được parse và nhận bởi management service.
2. Được commit vào candidate/running config.
3. Được sync tới một số nodes.
4. Chưa chắc đã được apply ở mọi data-plane devices hoặc gateways.

Do đó cần kiểm tra **applied version, rule hit/verdict, route/FIB, HA sync và test traffic**.

### 3.2. Change không đồng nghĩa một lệnh

~~~text
Change request:
  Cho phép Orders API zone tới DB TCP/5432

Dependencies:
  DNS resolution → Service/host IP
  Source/Destination address after NAT
  Router/VRF route cả hai chiều
  Firewall zone/rule/order/object group
  TLS/DB user authorization
  Logging, HA, monitoring, backup

Acceptance:
  Allowed source kết nối DB thành công
  Unapproved source không kết nối được qua policy
  Monitoring và đường quản trị vẫn hoạt động
  Rollback đã được kiểm tra
~~~

## 4. Phân loại và đánh giá rủi ro thay đổi

Một tổ chức có thể dùng ba nhóm thay đổi phổ biến, nhưng **tên/quy trình cụ thể phụ thuộc ITSM và chính sách nội bộ**:

| Loại | Đặc điểm | Kiểm soát tối thiểu |
|---|---|---|
| **Standard change** | Lặp lại, rủi ro thấp, có mẫu/playbook đã tiền phê duyệt | Script versioned, validation và log audit |
| **Normal change** | Thay đổi mới hoặc rủi ro vừa/cao, lên lịch | Review kỹ thuật/bảo mật, change window, test, rollback |
| **Emergency change** | Cần hành động nhanh để giảm incident nghiêm trọng | Delegated authority, scope nhỏ, ghi lý do, review hậu kiểm và expiry |

**Emergency không đồng nghĩa miễn audit**. Nếu phải thực thi trước hội đồng change, vẫn cần decision record, người phê duyệt trong phạm vi quyền, ghi lại config và review hậu kiểm.

### 4.1. Thang rủi ro gợi ý

| Trục | Câu hỏi |
|---|---|
| **Exposure** | Có mở Internet→management/DB hoặc crossing trust boundary? |
| **Blast radius** | Một host, subnet, region, tenant, toàn data center hay cả control plane? |
| **Availability** | Có đụng default route, BGP neighbor, DNS/IdP/monitoring flow? |
| **Complexity** | Có NAT+route+stateful policy+HA cùng lúc? |
| **Rollbackability** | Có OOB access, versioned config, commit-confirmed hoặc tested revert? |
| **Observability** | Có logs/hit counters/flow probes từ cả hai phía không? |
| **Timing** | Giờ cao điểm, change freeze, concurrent rollout, incident ongoing? |
| **Sensitivity** | Có customer data, production secrets, OT/safety-critical workloads? |

Đừng gán một mức rủi ro chỉ vì thay đổi “một dòng”: `0.0.0.0/0`, default route hoặc management-plane ACL đôi khi có **blast radius lớn hơn hàng trăm rule riêng lẻ**.

### 4.2. Quy tắc quyết định

Mức rủi ro cao hơn nên dẫn tới **phê duyệt cao hơn, test sâu hơn, rollout hẹp hơn, monitoring chặt hơn và khả năng rollback mạnh hơn**. Trường hợp thiếu OOB/recovery path hoặc không xác định critical flows, có thể cần **dừng thay đổi** cho tới khi rủi ro được giải quyết, trừ tình huống khẩn theo delegated authority.

## 5. Phân quyền và trách nhiệm của các bên

| Vai trò | Công việc | Nguyên tắc |
|---|---|---|
| **Requester / app owner** | Nêu mục đích, đúng flow, business acceptance | Không yêu cầu allow-all chung chung |
| **Network architect** | Phân tích topology, routing, NAT, HA và interdependencies | Nhìn end-to-end |
| **Firewall/security engineer** | Review least privilege, trust boundaries, logging và abuse cases | Không chỉ xét connectivity |
| **Implementer** | Thực hiện cấu hình đã phê duyệt, ghi version và thời điểm | Không mở rộng scope tùy ý |
| **Independent reviewer** | Kiểm tra change plan/diff, bất biến bảo mật, test/rollback | Four-eyes khi cần |
| **SRE/NOC** | Theo dõi SLO, packet loss, routing convergence, failover | Biết health và blast radius |
| **SOC / IAM** | Kiểm tra audit, account, policy drift, emergency access | Xác minh thay đổi có đúng quyền |
| **Change approver / IC** | Quyết định theo rủi ro hoặc tình trạng khẩn | Accountability và documented approval |
| **Evidence/audit owner** | Lưu config/diff/hashes/logs đúng chính sách | Không lộ secrets |

Trong nhóm nhỏ một người có thể giữ nhiều nhiệm vụ, nhưng cần **tránh người tạo thay đổi rủi ro cao tự duyệt, tự triển khai và tự tuyên bố kiểm thử PASS** mà không có độc lập kiểm tra tương xứng.

### 5.1. RACI và điểm dừng

Ví dụ:

~~~text
Change: route + firewall policy cho DB production
Requester:  App owner
Responsible: Network + Firewall engineers
Accountable: Change authority / incident commander nếu emergency
Consulted: SRE, DB owner, Security
Informed: SOC, NOC, affected users/stakeholders

STOP:
  - Không có quyền và approval phù hợp
  - Không có rollback/management access khả thi
  - Không có sơ đồ source/destination/route đáng tin
  - Test security negative hoặc business positive không được thiết kế
  - Config diff chứa thay đổi ngoài scope chưa giải thích
~~~

Không có RACI chung bắt buộc cho mọi công ty; mục tiêu là **không để trách nhiệm rơi vào khoảng trống**.

## 6. Biểu mẫu change request: chỉ cần dữ liệu phục vụ quyết định

~~~yaml
# PSEUDO-CHANGE-REQUEST: minh họa thiết kế, KHÔNG phải schema deploy cho firewall/router.
changeId: "NET-CHG-EXAMPLE-010"
environment: production
requester: orders-app-owner
businessReason: "Orders API cần truy cập PostgreSQL"
requestedFlow:
  sourceZone: application
  sourcePrincipalOrAsset: orders-api-workloads
  destinationZone: data
  destinationAsset: orders-db
  protocol: TCP
  destinationPort: 5432
  direction: application-to-data
  duration: "per-approved-business-need"
trustBoundaryCrossed: true
assumptions:
  - "App và DB assets đã đăng ký inventory"
  - "NAT/SNAT và return route đã được review"
changeType: normal
riskLevel: high
approvers:
  - network-owner
  - security-owner
  - database-owner
implementation:
  platform: "vendor-specific; supply actual plan separately"
  changeWindow: "scheduled-and-approved"
  configVersionBefore: "recorded"
  configVersionAfter: "candidate-reviewed"
  rollbackArtifact: "encrypted-verified-config-backup"
  outOfBandAccess: "validated"
acceptance:
  positiveControl: "Orders API reaches DB via approved path"
  negativeControl: "Non-entitled source is denied by intended enforcement point"
  securityInvariants:
    - "No Internet ingress to DB"
    - "No unapproved management plane exposure"
  monitoring:
    - "App error rate and DB connection success"
    - "Route/HA health"
    - "Firewall rule hit and deny logs"
postChange:
  temporaryExceptionExpiry: "not-applicable"
  evidenceOwner: network-operations
  peerReview: required
~~~

**Ví dụ chỉ mô tả yêu cầu.** Thiết bị thực tế có các thứ tự đánh giá NAT/policy và cú pháp khác nhau; không copy YAML này thành rule production. Thời gian và người phê duyệt phải được điền theo hệ thống change management thật.

## 7. Pre-change baseline: những thứ phải biết trước khi chạm cấu hình

Một baseline có ích không chỉ là file cấu hình. Nó gồm **trạng thái đường truyền và luồng ứng dụng**, vì rollback về cùng dòng cấu hình không luôn trả mọi **session, routing adjacency hoặc HA state** về trạng thái cũ ngay.

### 7.1. Kiểm kê trước thay đổi

| Nhóm | Bằng chứng cần có | Tại sao |
|---|---|---|
| **Device & topology** | Device ID, firmware/software, serial (lưu hạn chế), zone, VRF, HA pair, upstream/downstream | Tránh thao tác sai thiết bị hoặc tenant |
| **Config version** | Running/candidate/startup state, commit ID, policy package, object refs | So diff chính xác |
| **Management path** | OOB console/management network, AAA dependencies, break-glass status | Không tự khóa khả năng sửa lỗi |
| **Routing** | RIB/FIB, default route, BGP/OSPF neighbors, route filters, PBR | Biết đường đi trước khi chuyển |
| **Firewall/NAT** | Effective rules/order, zones, object groups, SNAT/DNAT, session tables | Tìm shadowing, asymmetric state |
| **Service health** | Request success, p95/p99 latency, DB connection, DNS/IdP/monitoring | Biết lỗi có từ trước hay do change |
| **HA health** | Active node, sync version, failover state, session synchronization | Tránh triển khai vào cụm đang bất ổn |
| **Capacity** | Interfaces, CPU, memory, session table, route scale, drops | Dự đoán load khi failover |
| **Logs & clocks** | Syslog/SIEM reachable, audit ID, NTP/time, sampling/drop caveats | Khôi phục timeline đáng tin |
| **Recovery** | Verified backup, rollback owner, console/OOB, recovery deadline | Có phương án khi mất in-band connectivity |

### 7.2. Backup phải có khả năng khôi phục, không chỉ tồn tại

Khi xuất configuration backup cần:

1. **Đúng phiên bản và đúng device/cluster**; ghi thời điểm/config commit ID.
2. Lưu file ở kho **mã hóa, giới hạn RBAC**, có integrity digest và lịch sử version.
3. Không nhúng plaintext shared secrets, passwords, private keys hoặc VPN pre-shared keys vào ticket/chat.
4. Biết backup có chứa **cả certificates/keys, external objects, dynamic feeds và policy package** cần để restore không.
5. Kiểm thử **restore procedure trong lab/staging hoặc maintenance được phê duyệt**, tránh đến lúc outage mới phát hiện backup không tương thích firmware.
6. Biết khác biệt giữa **config rollback** và **state rollback** (NAT sessions, BGP convergence, HA sync).
7. Có kênh quản trị **không phụ thuộc chính route/ACL đang định sửa**.

**File backup chứa bí mật là tài sản nhạy cảm**: một bản sao đầy đủ cấu hình firewall có thể tiết lộ topology, peer identities, endpoints, admin access và secrets.

### 7.3. Baseline positive và negative

~~~text
Trước thay đổi (T-before):
  P1: Orders API → DB TCP/5432          DENY vì rule chưa mở
  P2: Orders API → DNS resolver UDP/TCP53 ALLOW
  P3: Monitoring → router/syslog endpoint ALLOW
  N1: Guest subnet → DB TCP/5432         DENY
  N2: Internet → DB TCP/5432             DENY
  N3: User subnet → management SSH       DENY

Sau thay đổi (T-after):
  P1: Orders API → DB TCP/5432           ALLOW
  P2/P3: Vẫn ALLOW
  N1/N2/N3: Vẫn DENY
~~~

Kết quả **DENY** phải có bằng chứng tại **đúng enforcement point** hoặc một đối chứng đáng tin; timeout tới database đang chết không chứng minh firewall đã deny.

## 8. Quản trị management plane và quyền thay đổi

Nếu bất cứ account nào dùng được SSH/API của firewall/router có quyền sửa rules/default route, **management plane** trở thành target đặc biệt nhạy cảm. Hardening không chỉ là policy data-plane.

### 8.1. Những kiểm soát cần có

- **MFA/phishing-resistant authentication** và danh tính cá nhân cho quản trị tương tác khi nền tảng hỗ trợ.
- **AAA tập trung** (RADIUS/TACACS+/IdP/PAM phù hợp) với RBAC/command authorization ở thiết bị hoặc gateway quản trị.
- Giới hạn management network, OOB, bastion, host allowlist và VPN/ZTNA theo identity.
- Tắt/giới hạn giao thức quản trị không mã hóa, ưu tiên SSH/HTTPS bảo mật; quản lý TLS certificates và host keys.
- Giới hạn quyền API/service account và dùng **short-lived scoped credentials** khi khả dụng.
- Audit mọi commit, login, privilege escalation và policy change; đồng bộ thời gian, bảo vệ syslog từ xóa/sửa.
- Bảo vệ backup/config repository, CI credentials, SSH keys, cloud role credentials và signing keys.
- Review account mồ côi, vendor maintenance access, shared admin accounts và break-glass validity.

### 8.2. Đừng để break-glass trở thành bypass thường trực

Một account quản trị khẩn cấp có thể cần **độc lập khỏi IdP/VPN đang bị lỗi**, nhưng phải:

- Có owner, scope và lý do sử dụng rõ.
- Được lưu/bảo vệ theo chính sách secrets, có khả năng audit và kiểm soát sự sử dụng.
- Chỉ dùng trong sự cố/diễn tập được duyệt; rotate/reseal sau sử dụng.
- Có kiểm tra định kỳ rằng **đường cứu hộ vẫn hoạt động** mà không phơi management plane ra Internet.
- Không biến nó thành tài khoản dùng hằng ngày để bỏ MFA hoặc peer review.

### 8.3. Phân tách quyền implement và approve

Với thay đổi rủi ro cao, một kỹ sư không nên có khả năng **chỉnh Git policy, tự approve, tự chạy deploy và xóa audit log** mà không có detection. Dùng branch protection, signed/audited commits khi có, change approver độc lập và phân quyền automation.

**Separation of duties không bắt buộc phải dùng hai thiết bị khác nhau**, nhưng hệ thống phải chứng minh người duyệt và người thực thi được quản trị theo chính sách, đặc biệt với emergency exceptions.

## 9. Peer review: xem ý nghĩa, không chỉ cú pháp

Một config diff có thể:

~~~diff
- rule_42: allow application-zone -> db-host tcp/5432
+ rule_42: allow application-zone -> db-subnet any
~~~

Diff chỉ một dòng nhưng phạm vi đã thay từ **một host/một port** sang **toàn subnet/mọi protocol**. Reviewer phải hỏi:

1. Source/destination là **literal IP, object group, dynamic tag hay FQDN**? Nó resolve ra gì và khi nào?
2. Policy được match theo **zone, ingress interface, route, user identity, application-ID** hay chỉ IP/port?
3. Có **rule phía trên** shadow/override rule mới không? Các vendor khác nhau có first-match/last-match, implicit deny hoặc layers khác.
4. Có **NAT translation** trước/sau policy matching không? Phải xác minh theo sản phẩm.
5. IPv6 có bị bỏ qua hay mở thêm ngoài ý định?
6. Có rule logging/IDS/IPS inspection tiếp tục hoạt động ở flow mới không?
7. Hành vi hiện hữu đã được bao phủ bởi stateful session, HA sync, PBR, VPN hoặc proxy không?
8. Sau khi đổi source/destination object, **bao nhiêu policy khác** cũng bị ảnh hưởng?

### 9.1. Shadowing, overlap và redundancy

| Hiện tượng | Giải thích | Rủi ro |
|---|---|---|
| **Shadowed rule** | Rule không được đánh tới vì policy trước đã quyết định | Người vận hành tưởng mới mở/đóng quyền |
| **Overlapping allow** | Rule rộng và rule hẹp bao phủ cùng traffic | Tưởng xóa rule hẹp là deny được trong khi rule rộng còn |
| **Redundant rule** | Nhiều rules có hiệu ứng tương đương | Tăng complexity/dễ drift |
| **Conflicting intents** | Hai owner yêu cầu trái nhau nhưng nền tảng giải quyết theo thứ tự/semantics | Không rõ policy thực có đúng được phê duyệt |
| **Unused object** | Object tạo mới nhưng chưa tham chiếu | Không có tác dụng dù ticket được coi hoàn thành |
| **Orphan exception** | Temporary allow không được thu hồi | Tạo cửa hậu kéo dài |

**Rule hit count bằng 0** chưa chắc rule vô dụng: có thể traffic hiếm, log counters reset, stateless path khác hoặc HA node chưa nhận. Cần đối chiếu các điều kiện và validation.

### 9.2. Những thay đổi “không phải firewall rule” cũng có thể mở quyền

- Đổi default route đi qua firewall ít kiểm soát hơn.
- Chuyển VRF leak/route redistribution giữa management và application networks.
- Thay IPAM address group hoặc DNS-based object làm matcher rộng thêm.
- Đổi cloud security group attachment hoặc interface zone.
- Bật NAT exemption khiến destination/source identity khác với policy match ban đầu.
- Sửa user/identity group membership để nhiều user cùng hưởng firewall rule.
- Disable security profile/IPS cho application “để giảm latency”.

Vì vậy, review phải xét **effective reachability**, không chỉ so tên file cấu hình.

## 10. Firewall policy change: least privilege theo luồng

### 10.1. Thiết kế một rule tối thiểu

Một chính sách có thể mô tả:

~~~yaml
# MÔ HÌNH CHÍNH SÁCH, không phải cú pháp firewall vendor.
policyId: "orders-api-to-orders-db"
source:
  zone: application
  assets:
    - orders-api-workloads
destination:
  zone: data
  assets:
    - orders-db
protocol: TCP
destinationPorts:
  - 5432
action: allow
logging: enabled-according-to-security-policy
identityOrTagVerification: required-if-platform-supports
owner: orders-platform-team
purpose: postgres-application-connection
reviewDate: "defined-by-change-governance"
denyByDefaultForNonMatching: required
~~~

Không triển khai mẫu này trực tiếp. Với các nền tảng, rule có thể gắn application IDs, service objects, security profiles, schedule, ingress/egress zones và logging khác nhau.

### 10.2. Source/destination thực tế phải được chuẩn hóa

Ví dụ một workload ở Kubernetes:

- Source Pod IP có thể **thay khi reschedule**.
- Source sau SNAT có thể là node/NAT gateway IP.
- Destination là **DB hostname, Service VIP, load balancer IP hoặc private endpoint**.
- Source/destination IDs trong firewall policy có thể là **zone/tag/network objects** thay IP tĩnh.
- Nếu DB là SaaS/cloud service, IP có thể thay theo provider và không phù hợp static allowlist.

Đừng copy một IP thấy trong flow logs rồi biến thành permanent rule mà không kiểm tra **ownership và lifecycle**.

### 10.3. Default deny không có nghĩa chặn được mọi thứ

Một policy deny ở một firewall không có hiệu lực với:

- Đường **bypass firewall** qua peering, alternate route, direct Internet link.
- Traffic nằm trong **overlay/tunnel** không được giải mã/inspected như thiết kế.
- IPv6 nếu firewall path hoặc rule chỉ áp IPv4.
- Trường hợp policy được bypass bởi **hardware acceleration/offload** hoặc misconfigured datapath.
- Stateful sessions đã tạo trước rule change, tùy hành vi sản phẩm.

**Hãy test từ nguồn không được phép** và đối chiếu verdict tại đúng policy enforcement point.

### 10.4. IDS/IPS/WAF và firewall không thay thế nhau

Firewall thường làm L3/L4 hoặc application-aware filtering theo khả năng thiết bị. IDS/IPS kiểm tra traffic/signatures/behaviors trong phạm vi observation. WAF kiểm tra HTTP requests trong đường triển khai được hỗ trợ. Mở một network path có thể cho traffic **không còn đi qua lớp inspection** nếu route thay đổi.

Change review phải xác định **security inspection path** có còn hoạt động và có rủi ro false positive làm chặn traffic thật không.

## 11. NAT change: nhiều thứ đổi dù tên đích không đổi

### 11.1. Các loại NAT liên quan

| Loại | Ý nghĩa | Rủi ro |
|---|---|---|
| **SNAT/PAT** | Đổi source IP hoặc port outbound | Shared egress IP, attribution, return path |
| **DNAT/port-forward** | Đổi destination IP/port inbound | Phơi service nội bộ, bypass ingress |
| **Policy NAT** | Chọn translation theo source/dest/protocol/zone | Rule match khác do điều kiện phức tạp |
| **NAT exemption/no-NAT** | Một luồng được loại khỏi translation | VPN selectors, asymmetric routing, leak |
| **Twice NAT** | Dịch đồng thời source và destination trong một số thiết kế | Điều tra source/dest sau translation khó hơn |

### 11.2. Thứ tự NAT và policy phải tra đúng nền tảng

Không có một quy tắc **“firewall luôn match post-NAT destination”** áp cho mọi vendor/engine. Thứ tự **route lookup, NAT, policy, zone selection, connection tracking** khác nhau theo sản phẩm, chế độ và phiên bản.

Khi review:

1. Vẽ **5-tuple trước NAT** và **5-tuple sau NAT** cho cả hai chiều.
2. Ghi rule được thực thi tại **ingress interface/zone nào**.
3. Xem platform documentation/testing để biết **NAT/policy evaluation order**.
4. Kiểm tra return traffic, session creation, duplicate port translations và overlapping pool.
5. Test một flow hợp lệ và một flow bị deny **bằng logs ở cả hai phía nếu được phép**.

~~~text
Before SNAT:
  10.2.1.7:51024 -> 198.51.100.20:443

After SNAT (minh họa):
  203.0.113.50:62001 -> 198.51.100.20:443

Firewall/proxy logs ở từng điểm có thể thấy source khác nhau.
Không gán toàn bộ 203.0.113.50 cho một Pod.
~~~

### 11.3. NAT không phải authorization

Kết nối thông qua một NAT gateway vẫn cần **outbound policy, identity/application authorization và logging**. NAT có thể giảm số địa chỉ public được dùng, nhưng không tự kiểm soát ai được phép gọi database hoặc host nào có thể truy cập từ Internet.

## 12. Route change: đường đi hai chiều và blast radius

Với router, một thay đổi nhìn nhỏ có thể ảnh hưởng cả **forwarding** lẫn **đường quản trị**. Các trường cần review:

- **Destination prefix và mask**: có vô tình bao trùm vùng khác hay không?
- **Next hop và interface**: reachable không, có ARP/ND, VRF đúng không?
- **Route preference / administrative distance / metric**: route nào thắng theo nền tảng?
- **ECMP / PBR**: lưu lượng có bị chia nhiều đường, các đường có cùng security controls không?
- **Route propagation**: VRF leak, static redistribution, BGP/OSPF advertisement, aggregate routes.
- **Return path**: phản hồi có đi qua cùng stateful firewall hay về đường khác?
- **Convergence / failover**: sau flap có blackhole, loop hoặc route churn không?
- **Management access**: thay default route có phá SSH/API/NTP/SIEM/OOB không?

### 12.1. RIB khác FIB

**RIB** (Routing Information Base) thể hiện các route candidate/đường được chọn trong control plane; **FIB** (Forwarding Information Base) là dữ liệu dùng để chuyển tiếp packet trong data plane, có thể được cài trên ASIC/TCAM hoặc kernel.

| Quan sát | Ý nghĩa | Cần kiểm tra tiếp |
|---|---|---|
| BGP neighbor Established | Phiên BGP đã thiết lập | Prefix được accept/export và forwarding đúng chưa? |
| OSPF neighbor Full | Adjacency đồng bộ trong phạm vi liên quan | LSDB/routes/FIB cho prefix đích có đúng? |
| Route có trong RIB | Control plane có route | Route đã được cài vào FIB/hardware? |
| Ping next hop thành công | Một IP có thể phản hồi ICMP | App TCP/UDP, NAT/firewall/return path vẫn có thể lỗi |
| Traceroute thấy hop | Một số phản hồi TTL/hop quan sát được | Không phải toàn bộ path hoặc policy; ECMP/tunnels làm khác |

**BGP/OSPF khỏe không chứng minh ứng dụng khỏe**; một ứng dụng không kết nối được có thể do security policy, DNS, TLS, service hoặc route về.

### 12.2. Ví dụ thay static route

~~~text
Đề xuất:
  10.40.0.0/16 qua next-hop A → next-hop B

Review:
  - Next-hop B có reachability không?
  - B có route về source subnets?
  - Security gateway trên path B có policy/NAT tương đương?
  - Management subnet có thuộc prefix ảnh hưởng?
  - VPN/VRF/overlay nào phụ thuộc path A?
  - Đo packet loss/convergence và backout trigger nào?

Không áp chỉ vì "ping next-hop B" thành công.
~~~

Nếu một route đích đi sang đường khác không qua firewall bắt buộc, ta có thể vừa **phục hồi availability** vừa vô tình **mở đường bypass security inspection**. Cần review đường đi của traffic ở cả hai chiều và policy enforcement.

## 13. BGP, OSPF và route filtering: thay đổi phải có scope

### 13.1. BGP: những điểm review trọng yếu

| Thay đổi | Rủi ro | Bằng chứng xác nhận |
|---|---|---|
| Thêm BGP neighbor | Thiết lập control-plane adjacency ngoài ý định | Neighbor identity, ACL/MD5/TCP-AO theo khả năng, policy |
| Thay import/export policy | Nhận/quảng bá prefix không được phép | Prefix-list/route-map effective, advertised/received routes |
| Sửa local preference | Traffic chuyển đường, đổi security controls/latency | Path selection, service flows |
| Sửa AS-path/community policy | Route ưu tiên/bị lọc khác dự kiến | Per-prefix selected path và policy simulation |
| Bật default-originate | Downstream có thể gửi nhiều traffic qua thiết bị | Scope, capacity, blackhole tests |
| Bật redistribution | Leak giữa protocols/VRFs hoặc routing loop | Explicit allowlists và route feedback checks |
| Thay maximum-prefix/limits | Session bị reset hoặc nhận quá nhiều routes | Route counts, alarm, rollback |
| Withdraw/aggregate prefix | Blackhole/loop/đường phụ không phù hợp | Reachability từng prefix, FIB và owner |

**Không thay BGP bằng cách nhập lệnh tùy hứng từ tài liệu chung.** Route filtering, neighbor authentication và trình tự commit khác nhau theo vendor/OS. Thử nghiệm trong lab/route policy simulator tương thích và chuẩn bị out-of-band access.

### 13.2. OSPF/IGP: độ ổn định và segmentation

Review:

- Router ID, area design, network types, adjacency authentication/segmentation.
- Interface cost, timers và metric changes; tránh tạo churn.
- Stub/NSSA/summary và redistribution giữa areas/VRFs.
- Default route injection, LSA flooding/load và scale.
- Protection of management/control plane against unauthenticated neighbors khi triển khai phù hợp.

Một thay đổi cost có thể khiến đường đi **không còn đi qua firewall stateful ở cả hai chiều**. Vì vậy, routing team và security team cần cùng xem forward/return paths.

### 13.3. Các kiểm soát bổ sung ở Internet edge

Khi thay đổi BGP ở public edge, cần xem:

- Chỉ quảng bá/nhận những prefix đúng **ownership và routing policy**.
- Prefix-length limits và anti-bogon/filtering theo yêu cầu/upstream.
- Resource Public Key Infrastructure (**RPKI**) origin validation khi được tổ chức/provider triển khai phù hợp.
- Max-prefix, peer policy và community controls.
- Phối hợp ISP/upstream/peers khi có khả năng leak/hijack.
- Lưu RIB, advertised routes và audit trước/sau.

**RPKI origin validation** giúp đánh giá tính hợp lệ của prefix origin theo ROA, **không xác thực đầy đủ mọi AS-path hoặc bảo đảm route không bị thao túng**.

### 13.4. Các thay đổi nên được tách giai đoạn

Không nên cùng lúc:

1. Thay BGP neighbor.
2. Đổi default route.
3. Mở firewall allow rộng.
4. Thay NAT pool.
5. Chuyển HA role.

nếu không có orchestration và test plan rõ. **Tách nhỏ giúp xác định nguyên nhân và rollback chính xác**. Một số migration buộc phải phối hợp nguyên tử, nhưng cần dependency graph, rehearsal và sequencing được phê duyệt.

## 14. VPN, tunnel và IPv6: hai đường thường bị bỏ sót

### 14.1. VPN/IPsec change

Một VPN rule có thể gồm:

- Peer identity, PSK/certificate, authentication và key rotation.
- Phase-1/Phase-2/IKE proposals, lifetimes, PFS.
- Traffic selectors, encryption domains, route-based vs policy-based design.
- NAT traversal, MTU/MSS, DPD/rekey và tunnel health.
- Routing qua tunnel và security policy phía hai đầu.
- Split/full tunnel của remote-access clients.

Nếu thay selectors hoặc route mà chỉ test **tunnel up**, có thể bỏ qua chuyện **luồng nghiệp vụ không đi qua tunnel**, hoặc một mạng không nên nối lại được quảng bá.

### 14.2. IPv4/IPv6 dual stack

Một yêu cầu “chặn Internet vào management subnet” cần xét:

- Địa chỉ IPv4 và IPv6 public/private.
- Routes và neighbor discovery (ND), ICMPv6 cần thiết.
- IPv6-specific firewall/ACLs, VPN policies và cloud SG/NACL.
- DNS A/AAAA và các ứng dụng chọn IPv6 theo Happy Eyeballs.
- NAT64/DNS64 trong một số môi trường.

**Chặn IPv4 không tự chặn IPv6.** Ngược lại, chặn toàn bộ ICMPv6 có thể làm hỏng Path MTU Discovery/ND và gây connectivity failure.

### 14.3. Đường management/VPN rescue

Một kỹ sư đang kết nối qua VPN tới thiết bị cần đổi firewall rule của VPN ấy có thể **tự khóa phiên quản trị**. Trước thay đổi:

1. Thử **out-of-band management** hoặc console path độc lập.
2. Xác nhận quyền rollback nếu session admin mất.
3. Chỉ định người thứ hai theo dõi availability và approval.
4. Dùng **commit confirmed** hoặc timed rollback khi platform thực sự hỗ trợ và đã test.
5. Không sửa default route của management network cùng lúc nếu không cần.

## 15. High availability (HA): một cluster không tự an toàn sau commit

Một firewall HA pair hoặc router redundancy group có thể chạy:

- Active/standby hoặc active/active traffic forwarding.
- State/session synchronization, config synchronization và health checks.
- Floating/virtual IPs, VRRP/HSRP hoặc cloud failover mechanisms.
- BGP advertisements/route tracking trên mỗi node.

### 15.1. Trước khi thay đổi phải xác minh

| Yếu tố | Lý do |
|---|---|
| Both nodes software/firmware compatibility | Một node khác version có thể không sync config đúng |
| HA roles và session ownership | Biết node nào đang chuyển tiếp traffic |
| Sync status và config version | Tránh drift/commit vào nhầm node |
| Health of heartbeat/state links | Không làm split brain/unsynchronized failover |
| Failover behavior | Session drops, NAT translations, route convergence có thể khác |
| Capacity của remaining node | Khi failover, node còn lại đủ throughput/session table không? |
| Logging/telemetry của cả hai nodes | Sau failover vẫn có evidence? |
| Management access tới cả hai nodes | Có thể rollback nếu active node mất? |

### 15.2. Rollout HA không giống canary ứng dụng

Một số platform sync policy ngay từ active sang standby; một số hỗ trợ staged deployment hoặc per-device commit. Nếu policy sai **được đồng bộ tới cả hai**, việc failover không khôi phục chính sách cũ.

**Không giả định “standby là bản backup cấu hình”.** Phải có backup config độc lập và rollback plan được test, đúng semantics vendor.

### 15.3. Test failover có thể gây outage

Không ép HA failover trên production chỉ để kiểm tra một rule đơn giản nếu chưa có change window và impact assessment. Có thể kiểm tra sync/health trước, sau đó failover **ở maintenance được duyệt** hoặc trên lab nếu cần.

## 16. Commit, commit-confirmed và timed rollback

Một số nền tảng quản lý cấu hình theo **candidate + commit**, một số thay running config ngay, một số cần lưu startup config hoặc dùng orchestration/API. **Các lệnh và rollback semantics không giống nhau**.

### 16.1. Cơ chế commit-confirmed (khái niệm)

~~~mermaid
flowchart TD
    REV["Reviewed candidate config"] --> STAGE["Stage / validate"]
    STAGE --> APPLY["Apply with timed rollback nếu hỗ trợ"]
    APPLY --> OBS["Observe management + app + security tests"]
    OBS --> OK{"All acceptance gates PASS?"}
    OK -->|"Có"| CONF["Confirm commit before deadline"]
    OK -->|"Không"| RB["Rollback / timed rollback / restore"]
    CONF --> AUD["Audit exact committed version"]
    RB --> CHECK["Revalidate routing, sessions, HA and security"]
~~~

Ý tưởng: nếu người vận hành **không xác nhận** trước một khoảng thời gian, nền tảng có thể revert candidate change theo chức năng cụ thể. Nhưng:

- Không phải mọi router/firewall hỗ trợ tính năng này.
- Một số thay đổi/routing side effects có thể **không quay lại ngay** khi config revert.
- External cloud resources, VPN peers hoặc automation ngoài thiết bị có thể không rollback cùng.
- Device reboot/failover/sync có thể thay semantics và timer.
- Khi operator xác nhận quá sớm, tính năng không còn bảo vệ khỏi lỗi phát hiện muộn.

**Phải đọc tài liệu vendor/version và thử cơ chế rollback trong môi trường được phép.** Không tự đưa một câu lệnh “commit confirmed” chung cho mọi OS.

### 16.2. Rollback khác redo

**Rollback** trở về trạng thái trước một change ID cụ thể, sau khi kiểm tra changes nào đã được apply. **Redo** là thực hiện thêm một thay đổi mới; nếu không biết session state và dependent systems, nó có thể tạo trạng thái không giống ban đầu.

Ví dụ:

~~~text
T0: Rule 40 = deny guest -> DB
T1: Change A sửa object group "app-networks"
T2: Change B mở exception cho batch job
T3: Change A bị xác định lỗi

Không được:
  Blindly restore toàn bộ firewall snapshot T0,
  vì sẽ vô tình xóa Change B nếu B hợp lệ và đã có approval.

Cần:
  Kiểm kê changes concurrent, thiết kế targeted revert,
  review dependency, xác minh effective policy và log.
~~~

### 16.3. Kịch bản mất kết nối quản trị

Nếu SSH/API bị ngắt ngay sau thay route:

1. Không lặp lại các lệnh cấu hình mù quáng.
2. Xác minh tình trạng service/management qua kênh độc lập.
3. Nếu có commit-confirmed/timed revert, theo dõi deadline và behavior được thiết kế.
4. Dùng OOB console/bastion rescue đã được phê duyệt để restore/rollback.
5. Kiểm tra config restored trên **cả active và standby** nếu có.
6. Validate routes, ACL/NAT, sessions, business flows và negative security controls.
7. Ghi root cause và cập nhật runbook, không chỉ “thiết bị đã lên”.

**Một rollback thành công về cú pháp chưa đủ kết luận restoration hoàn tất**: cần đối chiếu dataplane và ứng dụng.

## 17. Infrastructure as Code (IaC) và GitOps: tự động hóa không xóa trách nhiệm

Thay vì chỉnh thủ công mọi thiết bị, tổ chức có thể quản lý firewall/router policy như mã, dùng pipeline để validate, review và deploy. Tự động hóa giúp giảm lỗi lặp lại nhưng **một thay đổi sai được rollout đồng loạt có thể tăng blast radius rất nhanh**.

### 17.1. Pipeline tham chiếu

~~~mermaid
flowchart LR
    REQ["Change request + owner"] --> PR["Versioned change / pull request"]
    PR --> LINT["Syntax, schema & policy lint"]
    LINT --> SIM["Route/policy reachability model + diff"]
    SIM --> REV["Independent approval"]
    REV --> CAN["Deploy canary / subset"]
    CAN --> TEST["Business + security tests"]
    TEST --> G{"Pass gates?"}
    G -->|"Có"| ROLL["Phased rollout"]
    G -->|"Không"| BACK["Rollback + incident escalation"]
    ROLL --> AUD["Effective config and audit evidence"]
~~~

**Pipeline này là thiết kế chung**, không phải yêu cầu sử dụng GitHub/GitLab/Terraform/Ansible cụ thể. Từng nền tảng có semantics về transaction, eventual consistency, drift và rollback khác nhau.

### 17.2. Những kiểm soát nên tự động hóa

- **Schema/syntax validation:** cấu hình hợp lệ với version đúng của thiết bị.
- **Semantic diff:** xem changed objects, rules, routes, advertised prefixes và **effective reachability delta**.
- **Policy guardrails:** cảnh báo public ingress tới management/DB, wildcard allow, missing logging, IPv6 uncovered.
- **Identity/authorization:** chỉ deploy automation identity được phép tới scope/destination đã đăng ký.
- **Approval gates:** peer review độc lập và security owner với trust boundary nhạy cảm.
- **Secret scanning:** tránh commit admin passwords, PSKs, keys, SNMP communities hoặc backup không mã hóa.
- **Drift detection:** so desired state với running/effective config và biết ai thay manual.
- **Artifact integrity:** versioned signed releases hoặc integrity check, kiểm toán nguồn pipeline.
- **Canary/rollback automation:** chỉ trong phạm vi vendor hỗ trợ; có human stop và OOB recovery.
- **Post-deploy verification:** so reachability/hit counters/logs/SLO, không chỉ “API 200”.

### 17.3. Không coi test config parser là đủ

Một rule có thể pass YAML schema nhưng **mở Internet→database**; một route có thể hợp cú pháp nhưng **gây blackhole**. Vì vậy:

\[
\text{Validation đủ dùng} =
\text{Syntax} + \text{Policy semantics} + \text{End-to-end observations}
\]

Biểu thức là **khung tư duy**, không phải công thức tính điểm. Thiếu một lớp có thể làm change không đạt mục tiêu.

### 17.4. State drift và emergency edit

Trong incident, kỹ sư có thể cần sửa trực tiếp firewall bằng quyền khẩn cấp. Khi khôi phục:

1. Export **running/effective state** cùng timestamp và actor.
2. Tạo change record bổ sung, đánh dấu emergency exception và expiry.
3. Đối chiếu với source of truth Git/IaC; không chạy automation overwrite state mà chưa hiểu.
4. Quyết định giữ thay đổi như baseline hay rollback.
5. Cập nhật source of truth và re-run pipeline tests.

**GitOps không tự ngăn một người có quyền thiết bị thao tác ngoài Git**; cần AAA, audit, drift alerts và quy trình reconcile.

## 18. Pre-deploy tests: test “allow” và “deny” cùng nhau

Một change có thể làm business request hoạt động nhưng phá security invariant. Do đó phải có **positive và negative tests**, với **đối chứng tại đúng lớp**.

### 18.1. Test matrix ứng dụng–firewall

| ID | Luồng | Expected | Cách xác minh |
|---|---|---|---|
| P01 | Orders API→DB TCP/5432 | ALLOW sau change | App/DB logs + firewall allow verdict |
| P02 | Orders API→DNS resolver UDP/TCP 53 | ALLOW không thay đổi | Resolver log + network verdict |
| P03 | Monitoring→syslog/SIEM | ALLOW không thay đổi | Log ingestion heartbeat |
| P04 | SRE bastion→router SSH/HTTPS | ALLOW theo RBAC | Login audit, management reachability |
| N01 | Guest subnet→DB TCP/5432 | DENY | Firewall deny verdict, DB healthy positive control |
| N02 | Internet→DB TCP/5432 | DENY | Approved external test + cloud/edge logs |
| N03 | Orders API→DB TCP/22 | DENY nếu không có nghiệp vụ | Rule verdict, scoped test |
| N04 | Orders API→DB TCP/5433 | DENY | Rule verdict |
| N05 | Unapproved app host→DB/5432 | DENY | Asset identity/zone + policy verdict |
| N06 | User workstation→router management | DENY | Management ACL/AAA evidence |
| N07 | IPv6 source ngoài scope→DB | DENY | Dual-stack policy verification |
| N08 | Alternate VPN/peering path→DB | DENY nếu bypass PEP/zone | Route and firewall control |

Không cần **tạo traffic nguy hiểm hoặc quét rộng** để chạy negative tests. Dùng test identities/sources, lab hoặc approved service probes có **đích đã phê duyệt**, có rate/timeout và logs.

### 18.2. Lỗi thường gặp khi test

**“Connection refused”** có thể là server đang không listen, không nhất thiết firewall deny. **TCP timeout** có thể do service down, route blackhole hoặc ACL. **HTTP 403** có thể đến từ WAF/app, không phải network firewall. Một **successful ping** không chứng minh TCP/5432 hoặc TLS/DB authorization hoạt động.

Test tốt có:

1. Positive control cho chính destination/service **đang khỏe**.
2. Negative source thực sự khác principal/zone, không chỉ cùng máy với IP giả.
3. Firewall/route/flow evidence chỉ đúng **rule/decision**.
4. Timestamp và correlation ID.
5. Kết quả business/app-level riêng với network-level.

### 18.3. Test route và resiliency

| Test | Mục đích | Lưu ý |
|---|---|---|
| Route lookup tại đúng VRF | Đích sẽ đi qua next hop nào | Control plane chưa chắc giống data plane |
| Reverse route/return path | Stateful firewall thấy flow hai chiều | NAT và ECMP có thể làm khác |
| BGP advertised/received prefixes | Không leak mạng ngoài scope | Ghi policy/peer cụ thể |
| Convergence after policy update | Dịch vụ không blackhole quá SLO | Có thể cần chờ đúng timers/platform |
| HA sync and health | Nodes nhận config đúng | Không ép failover nếu chưa được duyệt |
| VPN route/selector | Subnet cần thiết đi qua tunnel | Tunnel-up không đủ |
| DNS A/AAAA | Client chọn đúng endpoint | Resolver view/cache khác nhau |
| ICMP/ICMPv6 PMTUD | MTU/MSS không gây stalls | Không block toàn bộ ICMPv6 |

## 19. Deploy theo giai đoạn: canary, waves và cửa sổ quan sát

### 19.1. Có thể canary kiểu gì?

| Cách canary | Hợp với | Rủi ro |
|---|---|---|
| Một firewall/cluster không production | Thử syntax/capability | Không đại diện đầy đủ traffic thật |
| Một subnet/VRF/team | Phân đoạn, ACL, policy change | Shared routes/objects có thể ảnh hưởng ngoài scope |
| Một app/source group | Least-privilege allow change | Dynamic IP/labels có thể thay đổi |
| Một region/site | Cloud/hybrid rollout | Cross-region dependencies, DNS geo routing |
| Route preference một prefix hẹp | BGP/route migration có điều kiện | Policy leak/convergence ảnh hưởng shared edges |
| Đường dự phòng ít traffic | HA/upstream changes | Không luôn mô phỏng peak failover load |

**Không phải thay đổi nào canary tách được hoàn toàn**, ví dụ sửa default route ở một edge chung hoặc trust bundle dùng toàn cụm. Những trường hợp này đòi hỏi kế hoạch maintenance, prechecks, rollback/OOB mạnh hơn.

### 19.2. Một change window có cấu trúc

~~~text
T-30m:  Peer review, backups, HA/OOB/sensor health
T-15m:  Baseline traffic/routing/policy, freeze concurrent changes
T0:     Apply scoped change trên candidate/canary
T+2m:   Verify management path + device/control-plane status
T+5m:   Positive business flows + negative security flows
T+10m:  Review service SLO, drops, NAT sessions, route convergence
T+15m:  Decision: confirm / expand / rollback
T+30m:  Monitor, evidence capture, ownership handover

Thời gian chỉ minh họa; áp dụng theo khả năng platform và risk/SLO.
~~~

**Đừng xác nhận commit chỉ vì control plane đang OK trước khi data-plane/business tests hoàn tất**, nếu cách xác nhận sớm làm mất cơ hội tự động rollback.

### 19.3. Rollout gates

Để mở rộng từ canary sang toàn mạng, cần:

- Policy diff và commit/config version đúng.
- Management/OOB vẫn có đường vào.
- Routing neighbors ổn định, FIB và return paths đúng.
- NAT translations và stateful session behavior được chấp nhận.
- Positive tests PASS, negative tests PASS trên representative segments.
- Application latency/error rates trong SLO, IDS/IPS/WAF logs không có regression.
- HA sync/capacity khỏe và telemetry đang ingest.
- Có explicit approval để mở rộng, hoặc pipeline policy đã tiền phê duyệt.

## 20. Monitoring sau change: đừng chỉ xem “link up”

| Nhóm | Metrics/alerts cần quan sát | Giới hạn |
|---|---|---|
| **Link/physical** | Link state, error CRC, discards, utilization | Link-up chưa chắc route/app khỏe |
| **Routing** | BGP/OSPF state, prefix counts, RIB/FIB, next hop, convergence | Neighbor up chưa chắc forwarding đúng |
| **Firewall** | Policy hits, allow/deny verdicts, session count, resource pressure | Hit count thiếu context khi có stateful sessions |
| **NAT** | Pool/port utilization, translation failures, session resets | Một public IP đại diện nhiều workloads |
| **VPN** | Tunnel negotiation, selectors, DPD/rekey, byte counters | Tunnel-up không chứng minh all protected flows |
| **HA** | Config sync, cluster state, heartbeat, session failover | Standby có thể có config sai như active |
| **App** | Success/error rate, p95/p99, retries, DB connection pool | App 200 không tự chứng minh security |
| **Security** | IDS/IPS/WAF verdict, unexpected new flows, exposed management | Sensor gaps hoặc route bypass làm logs im lặng |
| **Audit** | Actor, approval, config version, exception expiry, changes ngoài window | Logging pipeline có thể mất dữ liệu |

### 20.1. Before/after phải cùng điều kiện so sánh

So sánh:

- Traffic cùng khung giờ/load nếu có thể; chú ý seasonality.
- Cùng source/app/region/VRF và destination được bảo vệ.
- Cùng vantage point (trước/sau NAT) và IP family.
- Số liệu đến từ **node active đúng** hoặc từ cả HA pair.
- Thời điểm event khác ingestion time và clock skew.

Không kết luận change giúp giảm drops từ một đồ thị sau change nếu tải hệ thống cũng giảm cùng lúc.

### 20.2. Packet capture chỉ khi cần

Khi logs chưa đủ, một **bounded PCAP** có thể giúp xác minh SYN/SYN-ACK/RST, ICMP PMTUD hoặc TLS handshake. Nhưng:

- BPF filter có thể loại chiều trả lời, NAT hoặc overlay inner packets.
- Snaplen ngắn có thể bỏ headers cần thiết và vẫn chứa dữ liệu nhạy cảm.
- PCAP ở host có thể khác wire do offloading, và SPAN mirror có thể mất gói.
- Full payload có thể chứa tokens, PII và topology; cần approval, encryption, retention.

**Không bật capture toàn mạng vô hạn** để kiểm chứng một rule; ưu tiên flow verdicts, counters và ứng dụng.

## 21. Rollback trigger và định nghĩa thành công

Một rollback trigger cần có:

| Trigger | Ví dụ minh họa | Quyết định |
|---|---|---|
| **Mất management access** | Không vào active node qua in-band sau change | Dùng OOB/timed rollback theo runbook |
| **Critical service errors** | API 5xx vượt ngưỡng được owner đặt | Dừng rollout, target rollback |
| **Security regression** | Guest subnet vào được DB | Rollback/cô lập ngay theo delegated authority |
| **Route leak** | Prefix ngoài policy được advertise | Withdraw/revert theo routing runbook |
| **NAT exhaustion** | New outbound sessions thất bại | Restore previous pool/policy có kiểm chứng |
| **HA drift** | Nodes không đồng bộ và risk failover | Dừng change, khôi phục HA safety |
| **Telemetry outage** | SIEM/syslog ngừng nhận device logs | Không tuyên bố acceptance complete |
| **Unexpected source impact** | Partner/VPN flows bị deny ngoài dự kiến | Scope/review/dependency checks |

### 21.1. Quyết định rollback có thể phải nhanh hơn full RCA

Khi security exposure/availability impact rõ và root cause chưa biết, IC/change owner có thể cần **rollback về safe last-known-good state trước**, rồi điều tra trên evidence. Nhưng rollback mù có thể xóa changes hợp lệ phát sinh sau T0; cần reconcile concurrent changes.

### 21.2. Post-rollback validation

Không kết thúc chỉ vì CLI/automation báo “revert success”. Kiểm tra:

1. Cấu hình/commit ID trở lại đúng expected version.
2. RIB/FIB/VRF, NAT và session behavior nhất quán.
3. HA nodes sync và logs không bị mất.
4. Business critical flows hoạt động.
5. Untrusted/unauthorized flows vẫn bị deny.
6. Management/OOB access và backups còn an toàn.
7. Incident ticket được cập nhật với impact, timeframe và corrective actions.

## 22. Emergency change: giảm thiệt hại nhưng không mở cửa hậu

Sự cố DDoS, malware lateral movement hoặc lỗi route gây outage có thể buộc đội vận hành thay firewall/router **trước lịch maintenance thông thường**. Khi đó, trì hoãn đến hết tất cả bước phê duyệt normal change có thể tăng thiệt hại. Tuy nhiên, emergency authority phải được **định nghĩa trước** để tránh quyền tùy tiện.

### 22.1. Quy trình 7 bước

1. **Declare:** mở incident/change record, ghi severity và chủ thể có quyền ra quyết định.
2. **Assess harm:** xác minh active threat/availability impact, chọn nhỏ nhất có thể giảm thiệt hại.
3. **Authorize:** IC hoặc delegated change authority phê duyệt theo policy; ghi rõ scope/rationale.
4. **Preserve:** giữ config snapshot, relevant logs và volatile evidence nếu không gây nguy cơ lớn hơn.
5. **Execute:** dùng approved access, một implementer và independent observer khi có thể.
6. **Verify:** kiểm tra security deny và business allow; quyết định giữ/quay lại, ghi effective change.
7. **Close exception:** expiry, post-change review, source-of-truth reconciliation và corrective action.

### 22.2. Mẫu emergency isolation

~~~yaml
# PSEUDO-INCIDENT-CHANGE, KHÔNG DÙNG NHƯ FIREWALL MANIFEST.
incidentId: "NET-IR-EXAMPLE-77"
changeId: "NET-EMERG-EXAMPLE-7"
trigger: "Confirmed compromised workload with ongoing unauthorized egress"
decisionOwner: incident-commander
implementer: firewall-oncall
enforcementPoint: egress-firewall
ruleScope:
  source: affected-workload-group
  destination: confirmed-malicious-indicator
  protocol: TCP
  port: 443
expectedImpact:
  security: "Unauthorized egress flow denied"
  business: "Normal API-to-DB and DNS remain operational"
rollback:
  method: "revert-the-specific-change-by-approved-process"
  authority: incident-commander
expiry: "explicitly-reviewed-temporary-window"
evidence:
  - before-and-after-policy-version
  - source-specific-flow-verdicts
  - application-and-monitoring-health
~~~

**Không nên tin hoàn toàn một IP IOC trên shared CDN**: có thể chặn nhiều tenants hợp lệ. Khi dùng IP block tạm, cần đánh giá thời gian IOC, source/destination, các business dependencies và alternative paths.

### 22.3. Không “emergency” hóa mọi thay đổi

Nếu các thay đổi được gọi khẩn cấp lặp đi lặp lại vì thiếu kế hoạch, đó là **rủi ro governance**. Theo dõi số emergency changes, tỷ lệ có retroactive review và expiry, nguyên nhân lặp lại. Khi ổn định, đưa yêu cầu vào normal/standard change với automated tests.

## 23. Change collision: nhiều người cùng thao tác trong một incident

Với outage phức tạp, SOC có thể đang chặn egress, NOC rollback route, SRE đổi load balancer và app team triển khai lại Pods. Những hành động đồng thời có thể:

- Làm **khó xác định thay đổi nào** khắc phục hoặc gây thêm lỗi.
- Ghi đè candidate config/rollback của nhóm khác.
- Tạo **policy drift** giữa firewall active/standby hoặc giữa các regions.
- Thay route trong khi người khác đổi NAT rule dựa vào route cũ.
- Xóa/không ghi lại evidence cần cho RCA.

### 23.1. Một kênh điều phối và change freeze có kiểm soát

Không nhất thiết cấm mọi thay đổi khi incident, nhưng nên:

1. IC chỉ định **change coordinator** và mỗi bước có owner.
2. Ghi **transaction/change ID, artifact version, scope** trước khi apply.
3. Dừng những changes không cần thiết ảnh hưởng cùng failure domain.
4. Với concurrent changes bắt buộc, ghi dependency/sequence rõ.
5. Mỗi bước xong cần **baseline checkpoint** và acceptance gates.
6. Rollback phải xét những thay đổi **đã xảy ra sau snapshot**, không dùng snapshot cũ mù quáng.

### 23.2. Timeline ví dụ

~~~text
T0: NOC detects DB timeout and route anomaly.
T+3m: Firewall team proposes allow rule for temporary mitigation.
T+5m: SRE reports DB now reachable from a separate route.
T+7m: IC pauses firewall change pending route investigation.
T+10m: Routing team reverts wrong PBR entry.
T+12m: Positive DB test and negative guest-zone test pass.
T+15m: Firewall allow exception is no longer needed.

Giả định: cùng một mục tiêu business, nhưng tránh mở thừa quyền.
~~~

## 24. Quan sát trạng thái bằng lệnh chỉ đọc

Không có một CLI chung trên mọi router/firewall. Cisco IOS/NX-OS, Junos, FortiOS, PAN-OS, VyOS, FRRouting, cloud platforms và thiết bị khác **có tên lệnh, RBAC, semantics config khác nhau**. Dưới đây là nhóm thao tác **read-only khái niệm** và ví dụ từ host Linux/Windows; không cần chạy trên thiết bị production để hiểu bài.

### 24.1. Danh sách cần xem trên thiết bị (vendor-specific)

| Mục tiêu | Lệnh/cách quan sát tương đương tùy thiết bị | Lưu ý |
|---|---|---|
| Config state | Show running/candidate/committed config, configuration history | Không in secrets ra ticket |
| Policy | Show effective rules, objects, shadowing, hit counters | Cần biết session state và rule evaluation |
| NAT | Show translations/session table, pre/post NAT flow | Phải xác minh hướng/VRF |
| Routing | Show route table, FIB, BGP/OSPF neighbors, prefix filters | RIB không đồng nhất FIB |
| HA | Show sync state, roles, heartbeat, version | Node standby có thể không chứa version cũ |
| Management | Show active admin sessions, RBAC, AAA/syslog health | Hạn chế tiết lộ thông tin quản trị |
| Interfaces | Link, errors, discards, utilization, MTU | Link up ≠ app healthy |
| Logs | Audit commits, deny/allow verdict, cluster events | Event time khác ingest time |

**Không copy bất kỳ “show” command nào từ một vendor sang vendor khác**. Một số công cụ management có subcommands vừa đọc vừa thay đổi; đọc tài liệu và áp role chỉ đọc.

### 24.2. Linux host: chỉ đọc routing

~~~bash
# Chỉ chạy trên host/lab được phép quan sát; không thay route.
ip -br address
ip -4 route show
ip -6 route show
ip rule show
ip -s link show

# Route resolution theo kernel trên host hiện tại, địa chỉ lab/documentation:
ip -4 route get 198.51.100.20
ip -6 route get 2001:db8:20::20

# Chỉ đọc trạng thái TCP sockets:
ss -tan
~~~

**Kết quả từ host Linux không tự đại diện router/FIB/firewall policy ở thiết bị mạng khác**. Nếu source ở Pod/container, namespace/routing table của host có thể khác workload.

### 24.3. Windows workstation: chỉ đọc

~~~powershell
# Quan sát địa chỉ, routing, DNS và kết nối có quyền hợp lệ.
Get-NetIPConfiguration
Get-NetRoute | Select-Object DestinationPrefix, NextHop, InterfaceAlias, RouteMetric
Get-DnsClientServerAddress
Get-NetTCPConnection | Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, State
Get-Date -Format o
~~~

### 24.4. Cloud/Kubernetes: xem chính sách theo phạm vi

Trong cloud, dùng các thao tác **read/list/describe/audit** được phân quyền để lấy:

- Route tables, next hops, peering/transit attachments.
- Security groups/NACLs/virtual firewall policies và effective attachments.
- NAT gateway allocations/logs, egress access rules.
- VPC flow logs và cloud audit của actor/policy change.
- Kubernetes NetworkPolicy, CNI policy verdicts, namespaces/workload identity.

Ví dụ chỉ đọc trên cluster được phép:

~~~bash
# Không sửa NetworkPolicy hay Pods.
kubectl config current-context
kubectl get networkpolicy -n orders
kubectl get pods -n orders -o wide
kubectl get services -n orders
kubectl get endpointslices -n orders
kubectl get events -n orders --sort-by=.lastTimestamp
~~~

**Kubernetes NetworkPolicy** thông thường dùng mô hình cộng dồn allow khi nhiều policies chọn cùng Pod; chuẩn NetworkPolicy không định nghĩa explicit deny rule theo priority. Manifest được API chấp nhận **không chứng minh CNI thực thi**. Các sản phẩm CNI có chính sách mở rộng riêng thì phải đọc đúng semantics/version.

### 24.5. Không tự ý thay đổi trong lúc kiểm tra

Không:

- Chạy `write memory`, `commit`, `configure terminal`, `route add/delete`, thay SG/NACL hoặc `kubectl apply` chỉ để lấy evidence.
- Bật debug mức cao liên tục trên router production khi chưa tính CPU/traffic overhead.
- Tắt IDS/IPS/TLS verification để chứng minh một flow “kết nối được”.
- Export config đầy đủ chứa passwords, VPN PSKs hay keys ra kênh công khai.
- Kích hoạt BGP/HA failover trực tiếp không có maintenance/risk approval.

Nếu cần packet-level proof, dùng sensor/flow logs được phép và bounded capture, không bắt toàn bộ traffic của nhiều tenant.

## 25. Những thay đổi cần dừng ngay dù “test connectivity” đã PASS

**Đường kết nối hoạt động** không đủ nếu đồng thời phát hiện:

1. **Internet hoặc guest network** có thể truy cập DB/management endpoint trước đây bị deny.
2. Policy mới tắt IPS/inspection cho traffic nhạy cảm hoặc route bypass thiết bị.
3. Một cloud public IP, NodePort, VPN peering hoặc IPv6 path tạo direct origin bypass.
4. Đường remote management không còn MFA/AAA audit hoặc được mở cho broad CIDR.
5. NAT mới làm source attribution không thể truy vết theo log yêu cầu.
6. BGP xuất một prefix chưa được phê duyệt, hoặc default route leak giữa VRFs.
7. HA standby không sync hoặc platform không có khả năng rollback đáng tin.
8. Security negative tests không chạy được vì environment thiếu source/monitoring đối chứng.
9. Application đạt SLO nhưng logs/SIEM không nhận new policy verdicts.
10. Temporary allow được triển khai mà không có owner/expiry.

Trong trường hợp này, **không nên tuyên bố change “đã đạt” chỉ vì P01 PASS**. Escalate, đưa change vào trạng thái lỗi/đang xem xét và rollback/contain theo delegated authority.

## 26. Threat model: 28 tình huống khi thay router/firewall

| ID | Rủi ro | Hệ quả | Kiểm soát và bằng chứng |
|---|---|---|---|
| C01 | **Rule any-any** | Trust boundary bị xóa, lateral movement | Narrow src/dst/service, review |
| C02 | **Object group quá rộng** | Một object change mở nhiều rules | Dependency map, effective diff |
| C03 | **Rule shadowing** | Allow/deny mới không có hiệu lực | Policy ordering, matching tests |
| C04 | **NAT evaluation hiểu sai** | Mở nhầm source/dest sau translation | Vendor-specific flow simulation |
| C05 | **Bypass qua route mới** | Firewall không còn nằm trên đường | End-to-end path, positive/negative tests |
| C06 | **Mất return route** | Stateful connection timeout | Reverse path & RIB/FIB |
| C07 | **BGP prefix leak** | Public/private routes bị quảng bá ngoài scope | Export filters, prefix controls |
| C08 | **OSPF redistribution sai** | Route loop/blackhole giữa domains | LSDB and route import tests |
| C09 | **Default route sai** | Outage hoặc traffic đi đường thiếu kiểm soát | Canary + OOB rollback |
| C10 | **PBR/ECMP asymmetry** | Phiên bị drop, visibility không đầy đủ | Bidirectional path probes |
| C11 | **IPv6 chưa kiểm soát** | Bypass IPv4 rules | Dual-stack policy, A/AAAA tests |
| C12 | **VPN selector/NAT exemption sai** | Mở/trượt tunnel subnet trái ý định | VPN flow/route validation |
| C13 | **Management ACL tự khóa** | Không rollback được từ in-band | OOB, timed rollback |
| C14 | **AAA/MFA bị bỏ** | Compromised admin credential dễ sửa policy | RBAC/MFA/bastion audit |
| C15 | **API token automation quá quyền** | Một CI compromise sửa toàn fleet | Short-lived identity, scoped deployment |
| C16 | **Config backup lộ secrets** | Credential/topology compromise | Encryption, restricted vault |
| C17 | **Config backup không restore được** | Outage kéo dài | Lab restoration drills |
| C18 | **Concurrent changes** | Revert đè thay đổi của đội khác | Change freeze, transaction ID |
| C19 | **HA sync lỗi** | Active/standby khác policy | Cluster version/health validation |
| C20 | **Failover làm cạn capacity** | Traffic outage sau đổi node | Capacity and failover plan |
| C21 | **Stateful sessions vẫn mở** | Rule deny mới không cắt connection cũ | Session handling/revoke tests |
| C22 | **Allow đúng nhưng mất IDS/IPS path** | Giảm khả năng phát hiện xâm nhập | Inspection path and alert tests |
| C23 | **Emergency exception sống vô hạn** | Cửa hậu kéo dài | TTL/owner/cleanup audit |
| C24 | **Không test negative flow** | Unauthorized traffic vẫn reachable | Per-boundary deny tests |
| C25 | **Sai device/tenant** | Thay policy ở môi trường khác | Inventory, context and approval checks |
| C26 | **Logs mất/clock lệch** | RCA/audit không đáng tin | Syslog/NTP/collector health |
| C27 | **Rollback về version quá cũ** | Xóa changes hợp lệ mới phát sinh | Versioned targeted revert/reconcile |
| C28 | **Change success chỉ tính CLI** | App/security failure vẫn bị bỏ qua | Runtime traffic, SLO and audit gates |

### 26.1. Ưu tiên xử lý theo blast radius

Một rule lộ database cho Internet có thể cần rollback khẩn ngay cả khi API hoạt động bình thường. Một route leak Internet có thể tác động các tổ chức khác; một SNAT change có thể gây mất logging identity và làm điều tra sau này khó. Đánh giá theo **exposure, active impact, các luồng bị ảnh hưởng, khả năng đảo ngược và evidence quality**, không chỉ số lines changed.

## 27. Ma trận kiểm thử thay đổi trên router/firewall

Các test sau chỉ chạy trên **lab, canary hoặc nguồn/đích được chủ hệ thống ủy quyền**. Chọn các nguồn test theo đúng zone/identity và giới hạn tần suất; không scan public IP/third-party networks tùy tiện.

| ID | Loại | Trường hợp | Kỳ vọng | Bằng chứng |
|---|---|---|---|---|
| P01 | Positive | App A→DB B TCP/5432 được phê duyệt | ALLOW | Application success + firewall verdict |
| P02 | Positive | App A→DNS corporate resolver | ALLOW như baseline | Resolver log + connectivity |
| P03 | Positive | Monitoring→syslog/SIEM | Log vẫn ingest | Collector heartbeat |
| P04 | Positive | Admin bastion→management port theo MFA/RBAC | ALLOW đúng principal | AAA/management audit |
| P05 | Positive | BGP approved neighbor và prefix | Established, right import/export | Neighbor/route evidence |
| P06 | Positive | OSPF path cho allowed subnet | Route/FIB đúng | LSDB, FIB, application flow |
| P07 | Positive | SNAT policy cho workload được phép | Đúng translated IP/port | NAT + egress logs |
| P08 | Positive | VPN approved source→approved service | Kết nối đúng selector | VPN/session logs |
| P09 | Positive | Một canary region/app | SLO và security tests PASS | Health + policy/flow |
| P10 | Positive | Device HA config sync | Cùng effective config version | HA status cả nodes |
| P11 | Positive | Backup/restore trong lab | Restore khả thi và data plane đúng | Version/hash/functional tests |
| P12 | Positive | Rollback change lỗi trong staging | Trở lại safe state | Version/RIB/FIB/flows |
| P13 | Positive | Emergency rule tạm có owner/TTL | Tự hết hạn/review theo chính sách | Audit, expiry |
| P14 | Positive | Ứng dụng HTTP/3 hoặc IPv6 hợp lệ | Đường liên quan vẫn theo policy | UDP/443/IPv6 logs và test |
| N01 | Negative | Guest subnet→DB TCP/5432 | DENY tại đúng firewall | Deny verdict, healthy DB control |
| N02 | Negative | Internet→DB TCP/5432 | DENY | Approved outside test + edge logs |
| N03 | Negative | Workstation→router management SSH | DENY | Management ACL + AAA |
| N04 | Negative | App A→DB TCP/22 | DENY nếu không có entitlement | Rule verdict |
| N05 | Negative | Non-approved workload→DB/5432 | DENY | Source identity/zone |
| N06 | Negative | IPv6 unauthorized→DB/5432 | DENY | IPv6 policy + route logs |
| N07 | Negative | Alternate peering/VPN→DB bypass path | Không bypass security boundary | End-to-end path evidence |
| N08 | Negative | Object group mở thêm subnet ngoài scope | Pipeline/review chặn | Semantic diff |
| N09 | Negative | Rule bị shadow bởi allow/deny cũ | Review/test phát hiện | Effective rule matching |
| N10 | Negative | Một NAT exemption tạo unintended path | Không cho phép/không triển khai | NAT simulation + flow tests |
| N11 | Negative | Wrong return route sau change | Canary phát hiện trước mở rộng | Reverse path/FIB |
| N12 | Negative | BGP export thêm unauthorized prefix | Gate dừng, không quảng bá ra ngoài | Route policy simulation |
| N13 | Negative | OSPF cost gây asymmetry qua stateful firewall | Test phát hiện | Two-direction route/session logs |
| N14 | Negative | Management default route bị mất | Timed rollback/OOB được kích hoạt | OOB reachability/commit history |
| N15 | Negative | Automation token ngoài scope sửa policy | Unauthorized action bị từ chối | API/IAM audit |
| N16 | Negative | Implementer tự duyệt high-risk change | Protected approval gate từ chối | PR/change audit |
| N17 | Negative | Candidate parser PASS nhưng broad allow | Semantic policy gate fail | Effective reachability analysis |
| N18 | Negative | HA standby config cũ | Không mở rộng rollout | HA version mismatch alert |
| N19 | Negative | Firewall rule deny nhưng session cũ còn | Gap được nhận diện/handled | Active connection check |
| N20 | Negative | IDS/IPS inspection path bị bypass | Change bị reject/rollback | Security sensor path check |
| N21 | Negative | Emergency exception quá hạn | Detected and removed/reviewed | Owner/expiry audit |
| N22 | Negative | Concurrent unrelated change sau baseline | Targeted rollback không xóa change khác | Config diff/reconciliation |
| N23 | Negative | Log pipeline/NTP offline | Acceptance không PASS | SIEM heartbeat/time sync |
| N24 | Negative | Rule chỉ IPv4 trên dual-stack app | Detected coverage gap | A/AAAA and IPv6 tests |
| N25 | Negative | NAT source IP dùng chung bị gán sai app | Attribution check phát hiện | NAT/CNI/flow mapping |
| N26 | Negative | Cert validation bị tắt để “fix” TLS | Security review reject | Trust validation logs |
| N27 | Negative | Revert xong nhưng DB vẫn timeout | Chưa close change | App/FIB/flow tests |
| N28 | Negative | Security negative test timeout vì DB chết | Không gọi policy DENY PASS | Service healthy positive control |

**42 test scenarios trong ma trận**: 14 positive (P01–P14) và 28 negative (N01–N28). Không bắt buộc chạy mọi test trên mọi thay đổi; chọn subset dựa trên **dependency/risk matrix**, nhưng không bỏ **critical invariants**.

### 27.1. Một negative test không thể chỉ dựa trên timeout

Ví dụ source không được phép thử kết nối DB và nhận timeout:

- **DB down:** tất cả clients timeout, không chứng minh firewall chặn.
- **DNS sai:** client không biết đích thật, không chứng minh ACL.
- **Route blackhole:** packet không đến firewall, không chứng minh policy của firewall.
- **TLS/DB auth failure:** network path có thể vẫn ALLOW.
- **Firewall deny:** muốn khẳng định phải xem rule verdict/counters/logs hoặc evidence mạnh từ đúng enforcement point.

Do đó test cần **đích khỏe + một nguồn hợp lệ có thể kết nối + nguồn không hợp lệ bị chính kiểm soát mong muốn từ chối**.

### 27.2. Security invariants cần được viết thành câu

~~~text
Invariant 1: Internet không truy cập trực tiếp DB.
Invariant 2: Chỉ Orders API workloads được tới DB TCP/5432.
Invariant 3: Management plane chỉ được dùng qua approved bastion/MFA.
Invariant 4: Critical DNS/IdP/NTP/SIEM paths vẫn hoạt động.
Invariant 5: Cả IPv4 và IPv6 paths đều được kiểm soát.
Invariant 6: Route mới không bypass stateful firewall/inspection.
Invariant 7: Emergency exceptions có owner, expiry, audit.

Mỗi invariant phải có owner và evidence test cụ thể.
~~~

## 28. Ba runbook mẫu theo tình huống

### 28.1. Runbook A — Mở quyền API→database

**Nhu cầu:** ứng dụng Orders cần kết nối PostgreSQL, không cần SSH hoặc truy cập cả database subnet.

**Preflight:**

1. Xác định app identity/zone, IP sau SNAT, DB asset, port 5432, TLS/DB role.
2. Xem đường đi, firewall rule order, object groups và return path.
3. Chuẩn bị diff chính sách hẹp và snapshot; kiểm tra OOB/HA.
4. Lập positive/negative test, gồm source hợp lệ, guest/unapproved app, IPv6.

**Deploy:**

1. Stage candidate với scoped rule và logging phù hợp.
2. Peer review impact của object groups/NAT.
3. Commit/canary theo cơ chế nền tảng, ghi change ID.
4. Đo app/DB connection, firewall verdict, monitoring và unauthorized sources.

**Rollback triggers:** DB errors tăng, guest/public source vào được DB, log/inspection path mất, route thay đổi ngoài scope.

**Sau change:** lưu config version, evidence, owner, rule review date và xác nhận không có temporary exception còn tồn tại.

### 28.2. Runbook B — Chuyển default route hoặc BGP upstream

**Nhu cầu:** chuyển Internet egress hoặc disaster recovery sang uplink khác.

**Preflight:**

- Tính capacity/HA/failover của uplink mới, provider escalation contacts.
- Kiểm kê default/aggregate prefixes, BGP export/import, RPKI origin validation theo khả năng.
- Xác định management/OOB path **không đi qua uplink đang đổi**.
- Đánh giá SNAT/public IP thay đổi, outbound allowlists của đối tác, DNS latency, TLS/proxy behavior.
- Chuẩn bị canary prefix/traffic steer nếu kiến trúc hỗ trợ; thống nhất change freeze.

**Deploy/observe:**

- Ghi RIB/FIB/BGP neighbor state trước/sau, policy match và quảng bá prefixes.
- Giám sát packet loss, jitter, ECMP, route flaps, SYN retransmits, app SLO.
- Check đường về/symmetric stateful firewall, NAT identity và security inspection.
- Confirm chỉ khi acceptance gates và recovery path còn đạt.

**Rollback triggers:** prefix leak, blackhole, route loop, manager access loss, service SLO regression, non-approved path bypass.

**Không nên** test chính sách BGP bằng cách cố tình leak real public prefix; dùng route simulation/lab hoặc controlled policy verification.

### 28.3. Runbook C — Khóa egress khi nghi malware

**Nhu cầu:** nghi một workload gửi traffic tới C2 endpoint trong lúc incident.

**Preflight khẩn:**

- Có evidence xác định source identity/process và destination; kiểm tra shared CDN/false positive.
- Xác định các business dependencies của workload; chọn block nhỏ nhất đủ giảm active harm.
- IC/delegated authority phê duyệt scope và thời gian.
- Bảo toàn logs, config version và dữ liệu forensic hợp pháp.

**Thực thi:**

- Enforce deny theo source/destination/port/identity ở đúng egress boundary.
- Verify malicious flow bị deny và app-critical flows vẫn khỏe.
- Kết hợp EDR/workload isolation và credential revocation nếu compromise được xác minh.
- Không coi việc chặn IP là đã diệt malware/eradicated toàn bộ incident.

**Hậu kiểm:** expiry/revoke temporary rule, fix root cause, positive/negative tests sau recovery, incident report và config source-of-truth update.

## 29. Case study: một rule mới làm lộ database và phá route quản trị

### 29.1. Bối cảnh giả định

Một tổ chức có topology:

~~~mermaid
flowchart LR
    WEB["Internet users"] --> EDGE["Edge router"]
    EDGE --> FW["HA firewall"]
    APP["Orders API / VLAN 20"] --> FW
    GUEST["Guest / VLAN 50"] --> FW
    FW --> DB["Orders DB / VLAN 30 TCP/5432"]
    BASTION["Management bastion / isolated VRF"] -.-> EDGE
    BASTION -.-> FW
    SOC["SOC / NOC monitoring"] -.-> FW
~~~

Vì thiếu dependency mapping, kỹ sư thực hiện hai thay đổi trong cùng maintenance:

1. Thay **address group** từ chỉ `orders-api` sang toàn subnet `VLAN 20` và thêm `allow any` tới `VLAN 30`.
2. Thay default route ưu tiên trên edge router qua uplink B, vô tình làm đường management traffic không còn quay về bastion.

Sau commit, Orders API kết nối được DB, nhưng một source không được phép cũng vào được DB/22; đồng thời quản trị từ bastion ngắt kết nối. Hệ thống vẫn trả HTTP 200 với vài endpoints nên một người định đóng ticket.

### 29.2. Phân tích lỗi theo lớp

| Vấn đề | Kiểm soát bị thiếu | Tác động |
|---|---|---|
| Address group rộng | Semantic diff và least-privilege review | Nhiều hosts có quyền hơn |
| `allow any` | Positive/negative test cho port/source | DB/SSH phơi cho app zone |
| Default route không kiểm return path | RIB/FIB, management dependency diagram | Mất SSH/API management |
| Không có OOB | Recovery preparedness | Không rollback nhanh |
| Thay hai hệ thống cùng lúc | Change sequencing và ownership | RCA/rollback phức tạp |
| Chỉ xem HTTP 200 | Business + security acceptance matrix | Tưởng thay đổi đã đạt |

### 29.3. Cách xử lý phù hợp

1. **Dừng rollout** và liên hệ change/incident authority, ghi evidence và phạm vi.
2. Nếu đang có exposure DB thực, **contain/rollback** rule rộng theo delegated authority, giữ ứng dụng quan trọng nếu có phương án hẹp.
3. Dùng OOB/timed rollback đã chuẩn bị để restore route, không gõ lệnh mù.
4. Kiểm tra rule/order/object group/NAT và routes đối với cả hai chiều.
5. Áp lại một rule **source Orders API cụ thể → DB TCP/5432**, không sửa rộng hơn mục đích.
6. Test từ Orders API (positive) và từ guest/unapproved app/Internet (negative); xác minh firewall logs.
7. Test management bastion, syslog, DNS và failover health.
8. Cập nhật Git/IaC, ticket, config snapshots và RCA; không để broad emergency exception.

### 29.4. Ghi nhận sự thật và giả thuyết

**Đã chứng minh** trong tình huống: rule mới cho flow trái ý định và route management bị mất theo evidence. **Chưa được khẳng định**: có attacker lợi dụng hay dữ liệu đã bị đánh cắp, nếu chưa có app/DB/audit evidence.

**Không đánh đồng khả năng truy cập trái phép với bằng chứng compromise đã xảy ra.** Tuy nhiên, exposure đó vẫn có thể cần incident escalation và impact assessment.

## 30. KPI cho một chương trình kiểm soát thay đổi

| KPI | Đo lường | Cảnh báo khi diễn giải |
|---|---|---|
| **Change success rate** | Changes đạt cả business/security gates | Không chỉ tính API/CLI success |
| **Failed change / rollback rate** | Thay đổi phải quay lại vì sự cố | Con số thấp không có nghĩa không có regression chưa phát hiện |
| **Security regression rate** | Số changes làm mở path ngoài policy | Cần negative tests có coverage |
| **Mean/p95 recovery time** | Từ phát hiện failure đến restoration | Phải định nghĩa rõ mốc bắt đầu/kết thúc |
| **Unauthorized effective changes** | Config drift không có approval | Phân biệt emergency edits hợp lệ |
| **Emergency exception overdue** | Rules quá hạn chưa review/gỡ | Theo owner và business dependencies |
| **Backup restore success** | Khả năng khôi phục trong drill | “File tồn tại” khác “restore PASS” |
| **Coverage of critical flows** | % flows có positive/negative tests | Quan tâm vùng không có telemetry |
| **Peer review quality** | High-risk changes có semantic/policy review | Chữ ký approval không chứng minh reviewer đã thấy impact |
| **OOB availability** | Kênh cứu hộ hoạt động tại thời điểm drill | Không thử gây outage ngoài window |
| **Audit completeness** | Actor/time/commit ID/config diff/logs có đủ | Pipeline logs có thể mất/clock lệch |
| **Customer/service impact** | Latency, errors, availability, lost transactions | Quan trọng hơn số dòng cấu hình thay |

### 30.1. Phân tích những chỉ số có thể bị “gaming”

Nếu mục tiêu duy nhất là **0 rollback**, đội có thể ngại rollback dù thấy security regression, hoặc gọi changes lỗi là “completed”. Nếu mục tiêu là “triển khai thật nhanh”, đội có thể bỏ negative tests. Cần **balanced scorecard** với SLO, security invariants, evidence quality và mức độ giảm rủi ro.

### 30.2. Học từ thay đổi thất bại

Post-change review nên hỏi:

- Requirement có đủ cụ thể theo source/destination/protocol/identity không?
- Topology/asset inventory có sai không, lỗi ở NAT hay return path?
- Peer review có nhìn **effective reachability**, không chỉ syntax?
- Pipeline test có cover IPv6, VPN, shared object và HA/route không?
- Rollback/OOB có hoạt động đúng và tác động trong SLO không?
- Có policy exceptions nào cần expiry không?
- Cần cập nhật runbook, route simulation hoặc monitoring checks gì để tránh lặp lại?

Tập trung vào **systemic causes và corrective actions có thể kiểm chứng**, không chỉ đổ lỗi cho người nhấn commit.

## 31. Bài tập vận dụng và câu hỏi phỏng vấn

### 31.1. Câu hỏi tự đánh giá

1. Vì sao **một dòng allow** có thể tạo rủi ro cao hơn một thay đổi gồm hàng chục rule?
2. Phân biệt **desired, candidate, running, saved/committed** và **effective data-plane policy**.
3. Trước khi mở Orders API→DB/5432, cần thông tin gì về **SNAT và reverse route**?
4. Vì sao **rule hit count = 0** không tự chứng minh rule không dùng?
5. Khi rule hẹp bị shadowed bởi rule allow rộng, test nào chứng minh chính sách thực bị sai?
6. Một source không được phép nhận TCP timeout tới database. Tại sao chưa thể gọi “firewall deny PASS”?
7. Vì sao **BGP Established** hoặc **OSPF Full** chưa đủ để ký acceptance?
8. Nếu một default route mới cắt luôn đường SSH admin, cơ chế nào giúp rollback an toàn hơn?
9. Vì sao **commit-confirmed** không thay thế được OOB access và backup config?
10. Nêu khác nhau giữa **config revert** và **forwarding/session-state restoration**.
11. Tại sao HA standby không nhất thiết là bản cấu hình trước change?
12. NAT policy thay source IP ảnh hưởng điều tra forensic và firewall logging như thế nào?
13. Khi cloud có IPv6, những negative tests nào cần bổ sung?
14. Vì sao không nên gộp NAT+route+BGP+ACL vào một lần change không có sequencing?
15. Làm sao xác minh một route mới không bypass IDS/IPS hoặc firewall đang kiểm soát?
16. Nếu một change là emergency, có thể bỏ hoàn toàn authorization/audit không?
17. Khi hai nhóm thay policy đồng thời, rollback một change cần lưu ý điều gì?
18. Đề xuất cách kiểm tra backup **khôi phục được** mà không thử trên production ngoài maintenance.
19. Với GitOps pipeline, vì sao lệnh deploy thành công không chứng minh security invariant vẫn đúng?
20. Nêu ba trường hợp kết nối business ALLOW nhưng change phải bị rollback vì security regression.
21. Những dữ liệu nào **không được** sao chép nguyên văn từ firewall backup vào ticket?
22. Viết các bước xác minh security policy sau khi Kubernetes CNI vừa được nâng cấp.
23. Khi một firewall đang có stateful sessions tồn tại, rule deny mới có lập tức cắt chúng không?
24. Trong một change window, ai xác nhận **quyền truy cập phải deny** và ai xác nhận **business flow phải allow**?
25. Viết tiêu chí dừng rollout/rollback khi p95 latency tăng, nhưng routing neighbors vẫn khỏe.

### 31.2. Gợi ý trả lời

- **Policy semantics:** change một object group có thể ảnh hưởng hàng loạt rules; phải xét references và effective reachability.
- **NAT/routing:** xác định 5-tuple trước/sau NAT, source zone, VRF, rule match, route cả hai chiều và platform NAT/policy ordering.
- **BGP/OSPF:** adjacency là control plane; cần kiểm RIB/FIB, prefixes và application data plane.
- **Security negative test:** cần source trái quyền, healthy destination đối chứng và evidence tại đúng enforcement point.
- **Commit-confirmed:** giúp một số failure modes, nhưng không rollback mọi external state/HA/session/concurrent changes.
- **HA:** config sync có thể phát tán cả rule sai; backup cần độc lập với active/standby.
- **GitOps:** schema PASS không chứng minh không có public DB exposure, route bypass hoặc auth regression.
- **Incident emergency:** hành động theo delegated authority, ghi scope/owner/expiry/validation, hậu kiểm sau ổn định.
- **Rollback:** chọn targeted revert và reconcile mọi change xảy ra sau baseline, sau đó kiểm tra cả allow/deny.

### 31.3. Bài tập thiết kế policy hẹp

**Đầu vào:**

~~~text
Source app:
  10.20.5.0/24 (VLAN application có nhiều workloads)
  Chỉ service "orders-api" cần DB
Destination:
  orders-db 10.30.8.15
Service:
  PostgreSQL TCP/5432
Existing:
  Default deny giữa app và data zone
  Guest 10.50.0.0/16 không có quyền DB
  DB hostname có thể được resolve theo private DNS
  Egress SNAT chỉ áp khi đi qua một cloud gateway
~~~

**Yêu cầu:**

1. Nêu hai cách represent source cụ thể hơn **cả VLAN** trong chính sách firewall, và giới hạn của từng cách khi Pod IP thay.
2. Vẽ đường app→firewall→DB và đường về, xác định NAT có xảy ra ở từng hop không.
3. Viết một yêu cầu allow logic theo **resource/port** không mở SSH hoặc subnet DB.
4. Tạo **hai positive tests và bốn negative tests**, ghi rõ enforcement point.
5. Chỉ ra điều kiện làm test không tin cậy: DB down, source sai zone, DNS sai, firewall không ở path.
6. Đề xuất rollback và những security invariants không được phá.

**Gợi ý:** có thể dùng managed firewall object dựa vào VM tags/identity hoặc danh sách IP endpoints do automation quản lý theo platform; nếu không hỗ trợ identity-aware policy, phải đảm bảo IP set được cập nhật và ownership rõ. Không chọn “allow source VLAN /24” chỉ để tránh theo dõi Pod IP khi có rủi ro đáng kể.

### 31.4. Tabletop: mất đường quản trị sau route change

~~~text
Inject 1: Router BGP session Established sau change.
Inject 2: SSH admin tới router chính bị timeout.
Inject 3: Application traffic có HTTP 5xx tăng nhanh.
Inject 4: HA standby đã sync bản config mới.
Inject 5: OOB console vẫn sẵn sàng, config backup đã verify.

Participants:
  IC / Change Authority
  Network Engineer
  Firewall/Security Engineer
  SRE/NOC
  Evidence/Audit Owner

Expected:
  - Dừng mở rộng rollout.
  - Không xác nhận commit khi acceptance chưa PASS.
  - Dùng OOB/timed rollback theo design, không lệnh mù.
  - Kiểm tra running/committed config cả HA nodes.
  - Verify application flows + negative network access.
  - Ghi timeline, RCA và corrective actions.
~~~

Thực hành nên làm bằng **mô phỏng/lab hoặc staging**. Không gây routing outage lên production để kiểm tra một nguyên tắc lý thuyết.

## 32. Checklist kiểm soát thay đổi router và firewall

### 32.1. Trước khi phê duyệt — Scope và risk

- [ ] Có change ID, requester, business owner, device/zone/VRF/tenant scope.
- [ ] Đã phân loại standard/normal/emergency và mức rủi ro theo chính sách.
- [ ] Mục tiêu được ghi theo **source → destination → protocol/port/action**, không phải “mở mạng”.
- [ ] Có data-flow diagram, asset inventory, NAT/route/HA/management dependencies.
- [ ] Biết policy matching theo vendor/version; không suy một NAT/policy order chung.
- [ ] Kiểm kê IPv4, IPv6, VPN, peering, overlay, cloud routes và alternate paths.
- [ ] Review security zones, management plane exposure, logging, IDS/IPS inspection path.
- [ ] Nếu object group/dynamic tag thay, đã kiểm **toàn bộ rules tham chiếu**.
- [ ] Đã xét shadowed/overlapping rules, default action và session-state behavior.
- [ ] Với BGP/OSPF, đã review import/export, prefix limits, redistribution và return path.
- [ ] Với NAT, đã ghi rõ trước/sau translation và connection tracking.
- [ ] Có approval bởi owner phù hợp; four-eyes review với trust boundary nhạy cảm.
- [ ] Đã kiểm tra user/automation identity được phép, MFA/RBAC và audit.
- [ ] Không nhúng secrets/private keys hoặc passwords vào change ticket/Git.

### 32.2. Chuẩn bị triển khai — Baseline và rollback

- [ ] Có version/snapshot của running/committed/startup config đúng device.
- [ ] Backup nằm trong kho mã hóa, RBAC và có integrity check.
- [ ] Đã kiểm restore procedure trong lab/staging tương thích platform.
- [ ] Có management OOB/bastion recovery path độc lập khỏi route cần đổi.
- [ ] Biết commit-confirmed/timed rollback có thực sự được hỗ trợ và tested.
- [ ] Có change freeze/coordination với những nhóm đang deploy cùng hệ thống.
- [ ] Có owner thực thi, observer, rollback authority và escalation contacts.
- [ ] Đã ghi baseline RIB/FIB/VRF, NAT, firewall policy, HA, metrics và log pipeline.
- [ ] Có positive tests cho critical flows và negative tests cho security invariants.
- [ ] Có canary/phased rollout hoặc maintenance window mạnh tương ứng blast radius.
- [ ] Có rollback triggers và tiêu chí quyết định với SRE/SOC/DB/app owners.

### 32.3. Trong change window — Thực thi an toàn

- [ ] Xác nhận đúng device/cluster/environment/tenant trước mỗi thao tác.
- [ ] Không thực thi lệnh ngoài phạm vi đã review mà không cập nhật approval.
- [ ] Dùng candidate/staging/commit transaction khi platform hỗ trợ.
- [ ] Ghi actor, time, change ID, before/after effective config version.
- [ ] Kiểm tra management/OOB sau bước ảnh hưởng route/ACL/AAA.
- [ ] Xác minh routing adjacencies, prefix import/export, RIB/FIB và reverse paths.
- [ ] Kiểm NAT, session table, firewall rule verdict và security inspection.
- [ ] Xác minh HA sync/roles và capacity; không coi standby là backup cũ.
- [ ] Positive tests PASS đối với ứng dụng, DNS, IdP, syslog, backup và management.
- [ ] Negative tests PASS với guest/Internet/unauthorized workload, kể cả IPv6.
- [ ] Không dùng timeout của service down làm bằng chứng firewall deny.
- [ ] Có monitoring SLO, drop rates, latency, config drift, log ingestion.
- [ ] Dừng/rollback nếu security regression hoặc blast radius ngoài ý định.
- [ ] Chỉ confirm commit khi acceptance gates đạt trong cửa sổ được duyệt.

### 32.4. Sau triển khai — Kiểm tra, audit và dọn dẹp

- [ ] Đã verify running/effective config sau commit trên đúng thiết bị/nodes.
- [ ] App/business owner xác nhận chức năng và SLO từ nguồn đại diện.
- [ ] Security reviewer xác nhận negative tests, scope và không có đường bypass.
- [ ] Đã đối chiếu NAT/RIB/FIB/HA/session state và telemetry trong monitoring window.
- [ ] Backups/version control/source of truth được cập nhật và reconcile drift.
- [ ] Audit logs lưu người duyệt, người thực hiện, timestamp, change ID và evidence.
- [ ] Không có temporary broad allow/emergency rule thiếu owner, expiry và cleanup.
- [ ] Đã ghi các caveats: non-tested regions, missing IPv6 source, sensor gaps.
- [ ] Có kế hoạch kiểm thử HA/failover theo maintenance nếu cần, không tự ép failover.
- [ ] Đã đóng hoặc chuyển follow-up các accepted risks có owner và thời hạn.
- [ ] Nếu rollback, đã verify cả service health **và** security invariants sau rollback.
- [ ] Post-change review tập trung root cause và corrective actions có thể kiểm chứng.

**Ghi nhớ:** **Kiểm soát thay đổi trên router và firewall là một quy trình bảo vệ trust boundary, không phải thao tác nhập cấu hình.** Trước thay đổi cần **inventory, risk review, least privilege, peer approval, config backup có thể restore và OOB recovery**; khi triển khai cần **đúng device, đúng policy semantics, canary/transaction, monitoring và positive/negative tests**; sau đó phải **xác minh effective data plane, HA/routing/NAT/session state, audit và cleanup exceptions**. Một đường mạng hoạt động nhưng đồng thời mở quyền ngoài ý định **không phải thay đổi thành công**, và một rollback chỉ đáng tin khi **dịch vụ lẫn kiểm soát bảo mật** đều được kiểm chứng.
