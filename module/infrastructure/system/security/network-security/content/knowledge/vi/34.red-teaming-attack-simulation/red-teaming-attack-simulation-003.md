# Mô phỏng reconnaissance có phê duyệt

Giả sử một tổ chức muốn kiểm chứng xem hệ thống giám sát có phát hiện được các hoạt động khám phá dịch vụ mạng trước một cuộc tấn công hay không. Nhóm red team nhận được yêu cầu “kiểm tra khả năng nhận diện reconnaissance”, nhưng tổ chức có hàng trăm subdomain, nhiều ứng dụng trên CDN, VPC cloud của đối tác, VPN cho nhân viên và một cụm Kubernetes đang phục vụ production.

Nếu nhóm bắt đầu quét tất cả địa chỉ liên quan tên miền công ty, họ có thể **gửi traffic tới hệ thống bên thứ ba không nằm trong phạm vi**, gây quá tải thiết bị cũ, làm tăng chi phí logging, vô tình lộ dữ liệu trong kết quả thu thập và tạo cảnh báo không phân biệt được với một sự cố thật. Ngược lại, nếu chỉ đọc danh sách tài sản và tuyên bố “red team đã mô phỏng reconnaissance”, bài kiểm thử có thể không đánh giá được **quy trình triage, độ phủ sensor hoặc khả năng phát hiện active network probes**.

**Mô phỏng reconnaissance có phê duyệt** là việc thực hiện các hoạt động thu thập thông tin về những tài sản được chỉ định nhằm kiểm tra giả thuyết an ninh, trong **phạm vi, thời gian, loại kỹ thuật, cường độ và điều kiện dừng đã được chủ sở hữu phê duyệt**. Mục tiêu là tạo **bằng chứng có thể đối chiếu với blue team** và đề xuất cải tiến; không phải thu thập càng nhiều dữ liệu, thăm dò càng nhiều mục tiêu hoặc tránh bị phát hiện bằng mọi giá.

Bài thuộc chương **Red team và mô phỏng tấn công mạng** của module **SECURITY_NETWORK_SECURITY**. Kiến thức liên quan tới phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, network access control, dịch vụ cloud, Kubernetes, TLS, packet capture, threat modeling và phát hiện xâm nhập.

**Quy tắc nền tảng:** **Có phạm vi, có người chịu trách nhiệm, có mục tiêu đo lường, có giới hạn tác động, có khả năng dừng và có chứng cứ.** Một hệ thống nhìn có vẻ thuộc cùng thương hiệu vẫn có thể **không nằm trong quyền thực hiện kiểm thử**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **reconnaissance, vulnerability assessment, penetration testing, red teaming, purple teaming** và asset inventory.
2. Soạn **Rules of Engagement (RoE)** cho một buổi mô phỏng reconnaissance, bao gồm phạm vi rõ ràng, out-of-scope, thời gian, nguồn, tốc độ, loại kiểm tra, người liên hệ và điều kiện dừng.
3. Phân loại **passive reconnaissance** và **active reconnaissance**, giải thích mức tương tác với mục tiêu và telemetry có thể tạo.
4. Phân tích các nguồn DNS, certificate metadata, cloud inventory, route/firewall logs, TLS và HTTP headers mà không quy kết quá mức từ một dấu vết.
5. Thiết kế các bài kiểm tra host/service discovery **có giới hạn trên lab/tài sản được cấp quyền**, không mở rộng sang quét bừa bãi hoặc kiểm thử khai thác.
6. Phân biệt **reachability, port states, service identity, application authorization và actual exposure**.
7. Dựng **test timeline** để đối chiếu red-team actions với firewall, IDS/IPS, EDR/NDR, DNS, SIEM và SOC case workflow.
8. Đánh giá các điểm mù do IPv6, NAT, load balancer, VPN, proxy, overlay tunnels, sensor sampling và DNS caching.
9. Thực hiện quản trị chứng cứ, privacy, retention, chống lộ thông tin nhạy cảm và emergency-stop khi có sự cố.
10. Báo cáo kết quả có **phân biệt quan sát và suy luận**, có false-positive/false-negative caveats và action items có thể kiểm tra.

## 2. Reconnaissance nằm ở đâu trong chuỗi tấn công?

**Reconnaissance** là giai đoạn khám phá tài sản, bề mặt tiếp xúc, cấu hình và những tín hiệu giúp hiểu một mục tiêu. Trong mô hình threat emulation, reconnaissance có thể xuất hiện **trước truy cập ban đầu** hoặc **bên trong mạng sau khi có một điểm đứng chân đã được mô phỏng**, nhưng hoạt động khảo sát không tự đồng nghĩa một cuộc xâm nhập.

~~~mermaid
flowchart LR
    A["Hypothesis & approval"] --> B["Inventory / passive observation"]
    B --> C["Scoped active verification"]
    C --> D["Red/blue evidence correlation"]
    D --> E["Coverage & control gaps"]
    E --> F["Remediation / purple-team replay"]
    SAFE["Safety, scope, stop rules, evidence handling"] -.-> B
    SAFE -.-> C
    SAFE -.-> D
~~~

**Sơ đồ là vòng đời bài kiểm thử**, không phải quy trình tấn công hay hướng dẫn đạt quyền truy cập. Mọi bước chủ động chỉ thực hiện trong phạm vi được phê duyệt.

### 2.1. Các khái niệm dễ nhầm

| Hoạt động | Câu hỏi chính | Sản phẩm đầu ra | Không tự đồng nghĩa |
|---|---|---|---|
| **Asset inventory** | Ta quản lý những tài sản nào? | CMDB, cloud inventory, owner mapping | Đã xác minh toàn bộ tài sản có thể truy cập |
| **Passive reconnaissance** | Dữ liệu có sẵn nói gì về tài sản? | DNS/cert/registry/config observations | Dịch vụ đang mở hoặc dễ khai thác |
| **Active reconnaissance** | Đích được phê duyệt trả lời gì khi có tương tác giới hạn? | DNS/HTTP/TCP observations | Có lỗ hổng hay đã bị xâm nhập |
| **Vulnerability assessment** | Cấu hình/phiên bản có rủi ro đã biết nào? | Triage findings và mức độ tin cậy | Có thể khai thác thành công trong thực tế |
| **Penetration testing** | Một phạm vi giả lập có thể bị vượt qua đến mức nào? | Technical evidence theo mục tiêu | Red-team campaign ở quy mô tổ chức |
| **Red team** | Khả năng phòng vệ trước hành vi đối thủ mô phỏng ra sao? | Detection/response/control outcomes | Có quyền làm mọi kỹ thuật/né giám sát |
| **Purple team** | Red và blue phối hợp cải tiến phát hiện như thế nào? | Detection rule, replay và acceptance evidence | Một bài kiểm thử chỉ đo sự bí mật |

### 2.2. Quan hệ với ATT&CK và threat modeling

MITRE ATT&CK có thể được dùng để **gắn nhãn hành vi và xây giả thuyết phát hiện**, nhưng cần kiểm tra đúng technique/sub-technique và mô tả được kiểm chứng từ taxonomy tổ chức sử dụng. Không nên gắn một mã ATT&CK chỉ vì một lệnh sử dụng port hoặc DNS.

Ví dụ một hypothesis tốt:

> “Nếu host thử kết nối TCP tới ba cổng dịch vụ trên hai server lab trong 60 giây, các log firewall và NDR có nhận diện được nguồn, đích, thời gian và loại tương tác không; SOC có tạo đúng case theo runbook không?”

Ví dụ hypothesis chưa đủ:

> “Thử xem hệ thống có chống được hacker hay không.”

Hypothesis cần **điểm bắt đầu, nguồn, đích, hành vi, giới hạn và điều kiện thành công**.

## 3. Các lớp phê duyệt và quyền không thể bỏ qua

### 3.1. “Được thuê kiểm thử” không tự cho phép mọi nơi

Một tổ chức có thể sở hữu tên miền `example.test` nhưng:

- Frontend nằm trên CDN hoặc SaaS với **điều khoản và chính sách test riêng**.
- Một subdomain CNAME tới **ứng dụng của đối tác**, không do tổ chức vận hành.
- IP được chia sẻ trên cloud/hosting với nhiều tenants.
- Network route/VPN dẫn đến hệ thống của khách hàng, nhà cung cấp hoặc production OT.
- Một endpoint chứa thông tin cá nhân/nhạy cảm, dù được truy cập công khai.

**Phải có phê duyệt của đúng chủ thể có thẩm quyền đối với từng tài sản và phạm vi**; khi quyền sở hữu/authorization chưa rõ, không gửi active probes.

### 3.2. Các lớp cần ghi nhận

| Lớp | Điều cần được phê duyệt | Ví dụ |
|---|---|---|
| **Business authorization** | Người sở hữu sản phẩm/chịu trách nhiệm chấp nhận rủi ro | Chủ dịch vụ chấp nhận kiểm thử |
| **Technical scope** | IP, CIDR, FQDN, ứng dụng, account/tenant, môi trường | Chỉ hai VM và một DNS zone lab |
| **Activity scope** | Passive-only, DNS queries, kết nối TCP, HTTP HEAD, banner checks | Không brute force, không exploit |
| **Temporal scope** | Thời gian bắt đầu/dừng và maintenance window | Cửa sổ kiểm thử được phê duyệt |
| **Rate/resource bounds** | Số request, concurrency, timeouts, resource budgets | Một probe tại một thời điểm |
| **Telemetry & deconfliction** | Nguồn test, log correlation, SOC biết hay không biết theo design | Có escrow với safety controller |
| **Data handling** | Những dữ liệu có thể thu, lưu, chia sẻ và xóa | Chỉ headers/metadata; không copy payload |
| **Emergency stop** | Người có quyền dừng ngay, số liên hệ và trigger | SLO xấu đi hoặc out-of-scope detected |
| **Third-party requirements** | Provider/partner approval, contract restrictions | Không quét shared CDN endpoint |

### 3.3. Bằng chứng phê duyệt phải kiểm tra được

Một tin nhắn “anh cứ test đi” không đủ nếu không biết **ai có thẩm quyền, đúng tài sản nào, được làm gì, trong thời gian nào**. Kênh xác nhận có thể là hệ thống change management, signed scope, work order hoặc ticket có owner/approval record, tùy chính sách của tổ chức.

**Authorization không được suy ngược từ việc một IP trả lời ping, một trang web công khai hoặc một cổng đang mở.**

## 4. Rules of Engagement (RoE): hợp đồng vận hành cho cuộc mô phỏng

RoE xác định **điểm dừng và các hành động cho phép**. Với reconnaissance, nên cụ thể hơn một câu “kiểm thử hạ tầng mạng”.

### 4.1. Mẫu RoE mang tính thiết kế

~~~yaml
# PSEUDO-RoE: mẫu tài liệu, KHÔNG phải lệnh thực thi.
exerciseId: "RED-RECON-LAB-003"
purpose: "Kiểm tra khả năng phát hiện reconnaissance trên lab network"
authorizedBy: "designated-lab-owner"
operator: "assigned-red-team-operator"
safetyController: "assigned-security-lead"
startUtc: "approved-window-start"
endUtc: "approved-window-end"
scope:
  sourceHosts:
    - "approved-lab-workstation"
  destinationHosts:
    - "lab-web-vm"
    - "lab-dns-vm"
  authorizedDnsZone:
    - "recon.example.test"
  approvedTcpPorts:
    - 80
    - 443
  approvedUdpQueries:
    - "DNS A/AAAA on lab resolver"
outOfScope:
  - "Internet hosts, production, partner/CDN/shared IPs"
  - "Employee devices, OT, third-party tenant networks"
  - "Credential guessing, exploitation, DoS or data extraction"
allowedActivities:
  - "Read existing inventory and lab evidence"
  - "Read-only DNS queries to authorized resolver"
  - "Low-rate TCP connection checks to two authorized hosts"
  - "HTTP HEAD only to lab endpoints when supported"
bounds:
  concurrency: 1
  requestBudget: "specified-by-lab-owner"
  timeout: "specified-by-lab-owner"
  retries: "disabled-or-explicitly-bounded"
communications:
  onCall: "authorized-exercise-contact"
  emergencyStopContact: "independent-safety-controller"
stopConditions:
  - "Out-of-scope destination observed"
  - "Service health or SLO regression"
  - "Owner/SOC requests stop"
  - "Unexpected sensitive data encountered"
evidence:
  storage: "restricted-lab-evidence-repository"
  collection: "timestamps, metadata and tool commands only"
  retention: "organization-approved-expiry"
successCriteria:
  - "Expected network observations correlated with telemetry"
  - "SOC response assessed against exercise objectives"
~~~

**Không chạy YAML này**: đây là hợp đồng/phạm vi minh họa, không phải schema cho scanner. Những giá trị placeholder như `approved-window-start` cần được điền bằng dữ liệu thật qua quy trình phê duyệt.

### 4.2. “In scope” phải được xác định hai lần

Một asset là **in-scope theo tên** chưa chắc là in-scope theo **IP thực tế ở thời điểm chạy**. Ví dụ:

~~~text
recon.example.test
  -> CNAME to shared.vendor.example
  -> A/AAAA shared CDN IP
~~~

Nếu RoE chỉ cho phép hạ tầng lab do tổ chức quản lý, khi hostname trỏ tới CDN/shared IP ngoài quyền, **dừng active test tại bước resolve**, không tự coi IP đó được cấp quyền vì bắt đầu từ một subdomain hợp lệ.

Ngược lại, IP được phép có thể là cloud VM vừa bị cấp lại cho bên khác. Phải kiểm tra asset ownership **gần thời điểm thực thi**, không chỉ một screenshot cũ trong ticket.

### 4.3. Approval không thay nguyên tắc an toàn

Ngay cả khi một kỹ thuật được phê duyệt:

- Không tăng cường độ sau khi thấy mục tiêu “chịu được” mà không có change approval.
- Không sử dụng kết quả để thử tài sản không nằm trong scope.
- Không giữ hoặc chia sẻ credentials/PII bất ngờ thu được.
- Không bỏ qua yêu cầu stop từ chủ dịch vụ hay safety controller.
- Không sửa log hoặc xóa chứng cứ để “red team trông bí mật”.

## 5. Vai trò và trách nhiệm trong một buổi mô phỏng

| Vai trò | Trách nhiệm |
|---|---|
| **Exercise sponsor** | Xác định mục tiêu, business constraints và phê duyệt nguồn lực |
| **Scope/asset owner** | Chứng thực quyền đối với host, DNS zone, tenant và testing impact |
| **Red lead/operator** | Thiết kế và vận hành test trong RoE, lưu action timeline |
| **White cell / safety controller** | Giám sát quy tắc, emergency stop, xử lý sự cố không dự kiến |
| **Blue team / SOC** | Phát hiện, phân tích, điều tra và phản hồi theo mode của exercise |
| **NOC/SRE** | Theo dõi sức khỏe dịch vụ, packet drops, traffic, service dependencies |
| **Evidence custodian** | Bảo vệ artifacts, audit truy cập, privacy/retention |
| **Independent reviewer** | Kiểm tra mapping giữa red actions, blue observations và findings |

Một bài kiểm thử nhỏ có thể ít người kiêm vai trò; nhưng **người có quyền dừng bài kiểm thử phải được xác định trước**. Không giả lập mất liên lạc với safety controller.

### 5.1. Hai chế độ tương tác với blue team

- **Declared/purple exercise:** blue team biết kịch bản/phạm vi để kiểm chứng log và tune detector; phù hợp học tập và xây coverage.
- **Blind/detection evaluation:** một phần blue team không biết thời điểm/kịch bản, nhưng **white cell và chủ tài sản vẫn biết/ủy quyền**, có deconfliction và stop procedure.

**Blind không có nghĩa được phép xóa audit, né sensor, che nguồn thật hoặc gây rủi ro vượt phạm vi.** Sự kín đáo trong thiết kế evaluation khác với né kiểm soát hoặc che giấu hoạt động trái phép.

## 6. Mô hình luồng dữ liệu và nơi có thể phát sinh telemetry

~~~mermaid
flowchart LR
    RED["Approved red host"] --> DNS["Lab DNS resolver"]
    RED --> FW["Firewall / ACL / NAT"]
    FW --> WEB["Lab web server"]
    DNS -.-> DL["DNS logs"]
    FW -.-> FL["Flow & firewall logs"]
    WEB -.-> AL["Web/server access logs"]
    RED -.-> RL["Red action ledger"]
    DL --> SIEM["SIEM / blue triage"]
    FL --> SIEM
    AL --> SIEM
    RL --> COR["Authorized post-exercise correlation"]
    SIEM --> COR
    SAFE["White cell / stop control"] -.-> RED
~~~

Một source/destination không xuất hiện trong SIEM **không tự chứng minh blue team không có năng lực phát hiện**: có thể sensor bị tắt, collector lag, routing đi đường khác, filter không khớp hoặc log retention hết hạn. Kết luận phải phân biệt **coverage, detector rule, alert routing và human response**.

## 7. Chuẩn bị tài sản lab và baseline

### 7.1. Inventory tối thiểu

| Thành phần | Ví dụ lab | Bằng chứng nên lưu |
|---|---|---|
| **Red source** | Một VM/workstation có IP cụ thể | Asset ID, source IP/IPv6, owner |
| **Web target** | Một VM phục vụ HTTP trên 80/443 | Hostname, IP, listening service và service owner |
| **DNS target** | Resolver/authoritative zone lab | Zone, record types, resolver view |
| **Firewall/router** | Một policy path tới web VM | Rule IDs, directions, NAT/route |
| **Blue telemetry** | Firewall logs, DNS, NDR, SIEM, server logs | Time sync, collection latency |
| **Test windows** | Một khoảng UTC được phê duyệt | T0/T1/T2, source of truth |
| **Recovery** | Snapshot/backup, emergency stop | Owner, rollback tests, status |

### 7.2. Chuẩn hóa thời gian và đường mạng

Ghi thời gian **UTC hoặc ISO 8601 có timezone**, thời điểm máy test gửi request và khi sensor nhận/log event. Clock offsets, log buffering và ingestion latency có thể khiến thứ tự log khác thứ tự thao tác.

Trước một active test, xác định:

- **Source IP thực tế** sau NAT hoặc VPN, cả IPv4 và IPv6.
- Target IP/hostname tại **vantage point đang được kiểm tra**.
- Có proxy/CDN, load balancer, Kubernetes Service hoặc overlay không?
- Firewall/IDS/IPS nhìn gói ở đoạn **trước hay sau NAT**, trước hay sau tunnel?
- Network devices có rule nào chặn legitimate test trước khi sensor mong muốn nhìn thấy?

Không mở thêm mạng production chỉ để scanner “nhìn thấy” một lab target. Ưu tiên lắp đặt/route kiểm thử thuộc lab và thay đổi hẹp đã được phê duyệt.

## 8. Passive reconnaissance: thu thập từ nguồn có sẵn

**Passive reconnaissance** trong bối cảnh bài này là phân tích thông tin đã tồn tại **mà không tạo tương tác mạng mới với hệ thống đích đang đánh giá**. Điều đó **không có nghĩa không có truy vấn tới hệ thống dữ liệu thứ ba**: việc đọc một cổng thông tin, dịch vụ CT hoặc API threat intelligence vẫn tạo request tới nhà cung cấp đó, có thể tiết lộ các hostname/queries đang điều tra.

### 8.1. Ưu tiên nguồn nội bộ khi có quyền

| Nguồn | Phát hiện có thể có | Giới hạn |
|---|---|---|
| **CMDB/asset inventory** | Hosts, IP ranges, owner, environment | Có thể stale, không phản ánh exposure hiện tại |
| **Cloud inventory** | VM, IP, security group, load balancer, route | Chỉ trong các accounts/projects được cấp quyền |
| **DNS zone export** | A/AAAA/CNAME/MX/TXT, subdomains đã đăng ký | Không tự biết service còn chạy hoặc client đã gọi |
| **DNS resolver logs** | Queries/answers có timestamp và source | Cache/DoH/DoT có thể không xuất hiện |
| **Certificate inventory** | SAN, issuer, validity, certificate rotation | Cert có thể chưa deploy hoặc nằm trên gateway khác |
| **Certificate Transparency (CT)** | Public certificate issuance/logging | Không chứng minh service đang live, không bao phủ private PKI |
| **Firewall rules/reachability model** | Allowed paths theo cấu hình | Session state, alternate paths, shadowing/HA cần verify |
| **Network flow/IDS logs** | Lịch sử 5-tuples, decisions, alerts | Vantage point, sampling, NAT và retention ảnh hưởng |
| **Application/service catalog** | API routes, owners, dependencies | Không tự có nghĩa endpoint public reachable |
| **Vulnerability/config findings đã có** | Các rủi ro từng được xác định | Có thể outdated, false positives hoặc đã remediate |

**Passive vẫn cần phân quyền và data minimization.** DNS/cert metadata có thể tiết lộ tên tài nguyên nội bộ, khách hàng, tenant hoặc môi trường đang chuẩn bị triển khai.

### 8.2. DNS record enumeration trong phạm vi cho phép

Các loại record có giá trị:

- **A/AAAA:** địa chỉ IPv4/IPv6 được trả ở một DNS view và một thời điểm.
- **CNAME:** alias tới tên khác, có thể dẫn tới provider/cloud/CDN.
- **MX:** mail exchange; không nhất thiết phản ánh hệ thống web.
- **TXT:** SPF, DKIM selector metadata, domain verification hoặc service annotations, không suy toàn bộ TXT là dữ liệu bí mật.
- **CAA:** chính sách cho phép CA cấp certificate ở một phạm vi DNS.
- **NS/SOA:** authoritative delegation và zone metadata.
- **HTTPS/SVCB:** service binding/parameters khi client/zone hỗ trợ.
- **PTR:** reverse DNS, không xác định chính xác virtual-host thực.

**Không tự thử DNS zone transfer (AXFR) lên hệ thống ngoài scope** hoặc brute-force subdomains chỉ vì có quyền truy cập Internet. Nếu bài kiểm thử được duyệt có kiểm tra cấu hình zone transfer, dùng **DNS server lab riêng** và quy trình kiểm thử đã nêu trong RoE.

### 8.3. Passive DNS và current lookup khác nhau

Một record từ passive DNS provider với `first_seen`/`last_seen` chỉ cho biết **khi provider đó quan sát**, không phải ngày chính xác record được tạo hay xóa.

Một kết quả `dig` hôm nay **không chứng minh** tại thời điểm sự cố trong quá khứ hostname có cùng IP. CDN, geo-DNS, split-horizon, cache, IPv6 và DNS failover làm câu trả lời thay đổi.

Vì vậy nên ghi cho mỗi observation:

~~~text
asset:
  api.recon.example.test
record:
  A 192.0.2.20
source:
  approved lab resolver / inventory / timestamped log
observedAt:
  UTC time
resolverView:
  lab-private
assumption:
  current answer, NOT historical proof
nextStep:
  confirm scope/ownership before active connection
~~~

### 8.4. Certificate inventory và CT

Một certificate mang SAN `api.recon.example.test` có thể tiết lộ tên dịch vụ, nhưng không chứng minh:

- Endpoint đó đang chạy.
- Client đã từng kết nối.
- Certificate đang được cài lên host nào.
- Mọi SAN thuộc một tenant/backend.
- Certificate còn hạn hoặc được client hiện tại trust theo chính sách.

Trong TLS 1.3, **server Certificate message được mã hóa** trong handshake. Một passive PCAP không có session keys/endpoint logs thông thường không cho phép trích xuất plaintext certificate như nhiều TLS 1.2 full handshakes. Với ECH, **inner SNI** có thể không quan sát được. Không mô tả những giới hạn này là “vượt qua mã hóa”.

### 8.5. Đánh giá provenance của nguồn thụ động

| Observation | Câu khẳng định hợp lý | Câu vượt quá chứng cứ |
|---|---|---|
| DNS zone có A record | Zone chứa record tại thời điểm đọc | Port 443 đang mở |
| CT có certificate SAN | Certificate được logged/issued theo nguồn | Server đích đã dùng certificate này |
| Cloud inventory thấy public IP | Tài nguyên đang được gán IP theo inventory | Internet có thể truy cập mọi port |
| Firewall allow rule tồn tại | Config có một allow predicate | Packet thực đã match và app có quyền |
| NDR logs có flow B:443 | Sensor thấy flow theo time/view | Hostname H đã được truy cập hoặc actor X thực hiện |
| ASN thuộc cloud provider | IP được announce/allocated trong một mạng | Provider là kẻ tấn công |

**Reconnaissance chỉ được coi là phát hiện exposure sau khi đủ điều kiện xác minh reachability/ownership**, không chỉ vì một chỉ báo thụ động.

## 9. Active reconnaissance: tương tác nhỏ có đo lường

**Active reconnaissance** là chủ động gửi DNS/network/application requests tới các endpoint được phép để xác minh **service presence, routing, response metadata và defensive visibility**.

### 9.1. Các cấp tương tác theo mức ảnh hưởng

| Cấp | Ví dụ trong lab | Rủi ro/điều kiện |
|---|---|---|
| **Đọc local state** | Xem route/interface hoặc file PCAP lab | Không tạo probes nhưng output có thể nhạy cảm |
| **DNS query được phép** | A/AAAA/CNAME tới resolver lab | Query tạo log, có thể lộ tên cần điều tra |
| **TCP connection check** | Thử connect 80/443 tới một VM lab | Tạo session/log, có thể gặp service legacy yếu |
| **HTTP HEAD/TLS handshake** | Đọc headers/certificate của server lab | Request/handshake có thể tốn tài nguyên, chứa metadata |
| **Version/service detection** | Metadata inference trên service test được duyệt | Có thể tạo nhiều request và gặp parser lỗi |
| **Aggressive scanning/exploitation** | Không nằm trong bài lab này | Cần RoE khác, risk review và approval riêng |

Với mục tiêu **đánh giá detection của reconnaissance**, không cần chứng minh khai thác một dịch vụ. Khả năng phân loại đúng **hành vi khám phá** đã là một kết quả.

### 9.2. Giới hạn không chỉ là “scan chậm”

Phải xác định:

- **Nguồn và đích cụ thể**, gồm IPv4/IPv6, protocol và ports.
- **Số lượng request tối đa**, concurrency và retries.
- **Thời gian tối đa** và cách dừng khi không có phản hồi.
- **Payload/HTTP methods** được phép, không chỉ port.
- **Thời điểm** trong change window, đối chiếu health checks.
- **Không có redirection ngoài scope**: URL có thể redirect tới domain/CDN đối tác.
- **Không tự theo link/API discovery** tới assets chưa được xác thực sở hữu.
- **Stop rules** khi application errors/SLO/packet drops tăng hoặc người có thẩm quyền yêu cầu.

Thử rất ít request vẫn có rủi ro trên một thiết bị legacy/OT hoặc một endpoint điều khiển có side effects. **Tác động phụ thuộc tài sản**, không chỉ tốc độ scanner.

### 9.3. Không đánh đồng port với dịch vụ

Một TCP port `443` trả lời **không chứng minh** có HTTPS hợp lệ; có thể là một TCP proxy hoặc protocol khác. Port `22` không tự là SSH; service có thể chạy ở cổng khác. Một scan cho kết quả “open” thường chỉ chứng minh **một hành vi mạng ở thời điểm thử**, cần protocol validation và asset owner context nếu muốn suy luận sâu hơn.

**Vulnerability inference từ banner** có thể sai do reverse proxy, patched/backported vendor versions, misleading headers hoặc middleboxes. Không nâng thành “confirmed exploitable” nếu chưa có validation nằm trong RoE riêng.

## 10. Thực hành A — Xác nhận phạm vi trước khi gửi probes

### 10.1. Danh sách kiểm tra tiền kiểm

~~~text
Exercise ID: RED-RECON-LAB-003
Target hostname: web.recon.example.test
Expected IP: 192.0.2.20 (documentation address; lab phải có mapping riêng)
Allowed source: one approved lab workstation
Allowed TCP destination ports: 80, 443
Allowed DNS resolver: 127.0.0.1 (nếu lab đã có DNS service)
Authorized window: approval record
Maximum active probes: approval record
Concurrent probes: 1
Stop contact: safety controller

CHECK:
  [ ] hostname thuộc lab zone?
  [ ] resolved A/AAAA trỏ assets thuộc quyền?
  [ ] có CNAME/redirect sang third party không?
  [ ] service owner xác nhận maintenance/rate bounds?
  [ ] blue/safety contact có thể nhận stop signal?
  [ ] đang trong authorized time window?
~~~

**`192.0.2.0/24` là dải địa chỉ dành cho tài liệu**, không phải địa chỉ “phải thử” ngoài lab. Khi lab dùng mạng riêng, chỉ thay bằng địa chỉ được chủ hệ thống chỉ định.

### 10.2. Đọc cấu hình mạng của source — không tạo probes

~~~bash
# Chỉ đọc trên Linux lab host, không thay routes/interfaces.
ip -br address
ip -4 route show
ip -6 route show
ip rule show
~~~

~~~powershell
# Chỉ đọc trên Windows lab host.
Get-NetIPConfiguration
Get-NetRoute | Select-Object DestinationPrefix, NextHop, InterfaceAlias, RouteMetric
Get-DnsClientServerAddress
Get-Date -Format o
~~~

Output có thể chứa IP nội bộ, interface, VPN và thông tin nhân sự; chỉ đưa vào evidence repository được cấp quyền.

### 10.3. DNS lookup có giới hạn trên resolver lab

~~~bash
# Active query tới resolver lab localhost. Không có service thì không có answer.
dig @127.0.0.1 web.recon.example.test A +noall +answer
dig @127.0.0.1 web.recon.example.test AAAA +noall +answer
dig @127.0.0.1 web.recon.example.test CNAME +noall +answer
~~~

Nếu kết quả là CNAME tới third party hoặc IP ngoài allowlist, **dừng**, cập nhật scope/approval; không tự theo chain rồi gửi kết nối sang tài sản đó.

## 11. Thực hành B — Một TCP connection check có bounds

### 11.1. Mô hình an toàn

Giả định lab owner đã xác nhận:

- Server lab nằm ở `192.0.2.20` và đang phục vụ TCP/80, TCP/443 theo setup.
- Source lab host được phép gửi **một phép thử vào mỗi cổng**.
- Không có thiết bị OT hoặc third-party shared hosting trên đường.
- Firewall và server logs được giữ để đối chiếu.

Một lệnh có thể dùng trong lab:

~~~bash
# CHỈ CHẠY trên host đích lab được ủy quyền; không chỉ định CIDR rộng.
# -sT: TCP connect scan; -Pn: bỏ bước host discovery ping riêng.
# -p: đúng hai cổng đã phê duyệt; concurrency/rate/retries/time bounded.
nmap -sT -Pn -p 80,443 \
  --max-rate 2 --max-retries 0 --host-timeout 30s \
  192.0.2.20
~~~

**Giới hạn thực tế:**

- `-Pn` **không làm hành động “ẩn”**; nó chỉ bỏ host-discovery phase, không đảm bảo không có network packets khác.
- `--max-rate` giới hạn tốc độ gửi probes theo công cụ nhưng không phải **cam kết chính xác số request** cho mọi trạng thái/network path; phải đo thực tế và review phiên bản.
- `--max-retries 0` tránh retry tăng ngoài ý định trong ví dụ; có thể giảm độ tin cậy khi packet loss. Không nới retries khi chưa approval.
- `--host-timeout` kiểm soát thời gian scanner trên mục tiêu nhưng không thay **external exercise stop procedure**.
- Một scanner có thể thêm hoạt động khác tùy options/version. **Không tự bật discovery rộng, service-version scan, NSE scripts hoặc OS fingerprinting** nếu chúng không nằm trong RoE.
- Nếu lab dùng IP khác hoặc service không chạy, kết quả không chứng minh lỗi bảo mật.

### 11.2. Các trạng thái port và diễn giải

| Quan sát | Có thể diễn giải | Không kết luận |
|---|---|---|
| **Open** | Dịch vụ/endpoint chấp nhận TCP connect tại thời điểm thử | Dịch vụ là gì hoặc có lỗ hổng |
| **Closed** | Đích/thiết bị trung gian có phản hồi cho thấy port không nghe theo kỹ thuật | Hệ thống không có dịch vụ tương tự ở cổng khác |
| **Filtered** | Công cụ không phân biệt rõ do lọc/không phản hồi | Chắc firewall chặn hoặc host không tồn tại |
| **Timeout** | Không nhận phản hồi trong cửa sổ | Mục tiêu không có traffic; có thể packet loss/routing |
| **Inconsistent result** | Khác nhau giữa các lần | Network variability, balancing, backend health, sensor noise |

Phân loại cụ thể có thể khác theo **protocol TCP/UDP, kỹ thuật probe, trạng thái trung gian và phiên bản công cụ**. Không copy trạng thái “open|filtered” của UDP sang một tuyên bố TCP.

### 11.3. Không chuyển kết quả reconnaissance thành exploit tự động

Ví dụ scan TCP/443 trả “open”; tiếp theo **không phải** mặc định chạy vulnerability exploit, password guessing hoặc enumerate application data. Để tìm cấu hình TLS hoặc HTTP headers, cần scope chủ dịch vụ phê duyệt **loại tương tác bổ sung** và privacy review.

## 12. Thực hành C — HTTP HEAD và TLS metadata trong lab

### 12.1. HTTP HEAD trên localhost

Với một web server **do bạn quản lý** đang chạy tại `127.0.0.1:8080`:

~~~bash
# Không theo redirects; bounded timeout; không gửi payload.
# HEAD vẫn là active request và được server ghi log.
curl --head --max-time 5 --retry 0 \
  http://127.0.0.1:8080/
~~~

HTTP `HEAD` thường yêu cầu chỉ headers, nhưng:

- Server có thể **không hỗ trợ HEAD** hoặc xử lý sai.
- Reverse proxy có thể trả headers không phải backend thực.
- Headers có thể chứa tokens, internal service names hoặc debugging metadata.
- Một URL có thể redirect tới domain ngoài scope; ví dụ không bật `--location` để tự theo redirect.
- Không dựa vào `Server` hoặc `X-Powered-By` làm xác minh phiên bản dễ khai thác.

### 12.2. TLS handshake với local lab CA

Nếu có TLS service do nhóm lab quản lý tại `127.0.0.1:8443` với certificate hostname `web.recon.example.test`, có thể kiểm tra:

~~~bash
# Cần CA lab được phê duyệt tại đường dẫn bên dưới.
# Không dùng -verify 0, -k hoặc --insecure để làm phép thử validation.
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername web.recon.example.test \
  -verify_hostname web.recon.example.test \
  -verify_return_error \
  -CAfile ./approved-lab-root-ca.pem \
  -brief < /dev/null
~~~

Lệnh cần **xác minh kết quả chain/hostname** theo chính sách lab. Một handshake thành công không tự chứng minh user/backend authorization hay service không có lỗ hổng.

**TLS 1.3 passive PCAP** thường không cho thấy certificate message ở dạng plaintext; nếu cần evidence certificate, dùng **client/TLS termination logs hoặc active TLS lab test được phê duyệt**, không thu session secrets ngoài RoE.

### 12.3. Đối chiếu active action với blue telemetry

| Action ID | Expected data source | Trường cần đối chiếu |
|---|---|---|
| R-DNS-01 | Resolver DNS log | QNAME/QTYPE, source client, response time |
| R-TCP-01 | Firewall/flow logs | Source IP/port, destination IP:80/443, allow/deny |
| R-TCP-02 | IDS/NDR | TCP connection pattern, source identity, severity/rule |
| R-HTTP-01 | Web access logs | Method HEAD, path "/", status, request ID nếu hỗ trợ |
| R-TLS-01 | TLS endpoint logs | TLS version, cert identity, verify result, SNI khi được ghi |
| R-OPS-01 | SRE/SOC monitoring | Server errors, CPU, packet drops, alert/case timestamps |

**Không thấy alert** có thể là kết quả đúng nếu detector chỉ được thiết kế để cảnh báo reconnaissance **vượt một ngưỡng**, không phải một TCP connect đơn lẻ. Trước khi đánh giá false negative, phải xác định **expected detection logic**.

## 13. Mô phỏng theo hypothesis thay vì tăng số lượng probes

Một bài reconnaissance có giá trị khi **đặt câu hỏi đúng và đo kết quả quan sát**, không phải khi dùng nhiều công cụ nhất. Có thể thiết kế theo các hypothesis:

| ID | Hypothesis | Hành động được phép trong lab | Blue outcome cần đo |
|---|---|---|---|
| H01 | DNS resolver có thể gắn hostname với source lab | Một A/AAAA query cho tên lab | Query/answer/source/time đúng |
| H02 | Firewall nhìn một TCP connect được duyệt | Một kết nối tới lab-web:443 | 5-tuple, NAT context, action |
| H03 | NDR phát hiện mẫu khám phá dịch vụ được định nghĩa | Chuỗi kết nối giới hạn do RoE quy định | Rule firing hoặc documented no-alert |
| H04 | Web access logs phân biệt request HEAD | Một HEAD tới lab path | Method/status/time/source |
| H05 | TLS endpoint logs hỗ trợ định danh server/cert | Một handshake TLS được phê duyệt | TLS version/SNI/cert status |
| H06 | SOC có thể nhận một alert đi qua pipeline | Synthetic alert hoặc sanctioned network test | Ingestion, routing, acknowledgement |
| H07 | Source ngoài allowlist bị từ chối tại segment | Một denied flow từ test source được phê duyệt | Firewall deny + positive healthy control |
| H08 | Hệ thống không tự mở scope khi DNS trỏ ngoài quyền | Resolve một hostname test có CNAME ngoài scope (chỉ khi lab owner cấu hình) | Operator stop và report |
| H09 | Emergency stop từ white cell có hiệu lực | Safety controller gửi stop trong tabletop | Operator dừng, evidence và confirmation |
| H10 | Red/blue correlation đúng source qua NAT | Test client đi qua NAT lab đã định | Mapping pre/post NAT đầy đủ |

**Không có yêu cầu tất cả hypothesis đều phải tạo security alert.** Hệ thống có thể được thiết kế để chỉ lưu flow logs ở mức low-risk và cảnh báo khi có nhiều dấu hiệu kết hợp. Kiểm tra phải so với **detection objective đã được owner phê duyệt**, không tự coi “không alert” là thất bại.

### 13.1. Ghi success criteria trước khi chạy

Ví dụ:

~~~yaml
# Exercise test case: metadata phục vụ điều phối, không phải scanner config.
testId: H02
intent: "Firewall flow visibility for a permitted TCP connection"
sourceAsset: red-lab-vm
targetAsset: web-lab-vm
destinationPort: 443
allowedProtocol: TCP
maxConnections: 1
authorizedWindow: "see-approved-RoE"
expectedNetworkBehavior: "allow-the-known-lab-flow"
expectedTelemetry:
  sourceIdentity: "red-lab-vm / translated address if NAT"
  destination: "web-lab-vm:443"
  action: "allow"
  timestamp: "within-defined-clock-uncertainty"
expectedSOCBehavior: "No mandatory high-severity alert for one benign test"
successCriterion: "Event searchable and correlated to action ledger"
stopIf: "Owner requests stop or lab health regresses"
~~~

Khi exercise kết thúc, đánh giá **event recorded**, **rule match**, **alert routed**, **analyst acknowledged**, **case created** như các trạng thái riêng. Không gộp tất cả thành một biến “detected: yes/no”.

## 14. Network perspective: nguồn, hướng và điểm quan sát

### 14.1. NAT làm khác source identity

~~~mermaid
flowchart LR
    RED["Red VM 10.10.1.10"] --> GW["Lab NAT / firewall"]
    GW -->|"SNAT 192.0.2.50"| APP["Lab service 192.0.2.20"]
    EN["Endpoint log / source identity"] -.-> RED
    NT["NAT translation log"] -.-> GW
    SV["Server sees translated address"] -.-> APP
    COR["Correlation: timestamp + source port + mapping"] -.-> NT
~~~

Nếu server log chỉ hiển thị `192.0.2.50`, kết luận “red host là 192.0.2.50” có thể sai. Một NAT IP đại diện nhiều clients. Phải dùng **translation timestamp/ports, host identity và log source** để đối chiếu.

### 14.2. Một chiều không đủ

Firewall hoặc sensor chỉ thấy SYN outbound nhưng không thấy SYN/ACK có thể vì:

- Phản hồi đi route khác.
- Capture filter chỉ giữ `dst port 443`, loại source port 443 ở chiều ngược.
- Service đang không trả lời, filter/network policy deny hoặc packet loss.
- Sensor nằm trước/sau NAT hoặc tunnel khác với suy đoán.
- SPAN/mirror port hoặc host NIC offload tạo thiếu khác biệt.

**Không kết luận server im lặng chỉ từ PCAP thiếu chiều trả lời.** Có thể dùng counters, endpoint logs và positive controls ở cùng vantage point.

### 14.3. IPv4 và IPv6

Một hostname lab có cả A và AAAA có thể làm client chọn IPv6 trong khi firewall log query chỉ xem IPv4. RoE phải ghi rõ **cả IPv4 và IPv6 có nằm trong scope không**, và lệnh kiểm tra phải đối chiếu kết quả resolution đúng thời điểm.

- IPv4 permission **không tự bao gồm IPv6**.
- Một IPv6 address public có thể trỏ tới endpoint khác so với A record.
- ICMPv6 đóng vai trò thiết yếu trong IPv6 (ND, PMTUD); không cố tắt toàn bộ chỉ để giảm background traffic.
- NAT64/DNS64 có thể thay đổi địa chỉ quan sát ở mỗi đầu.

### 14.4. Shared infrastructure và CDN

Nếu hostname `web.recon.example.test` trỏ đến CDN/shared IP:

1. Kiểm tra RoE có **thực sự bao gồm** CDN endpoint và tenant tương ứng không.
2. Không tự “xác minh” bằng quét IP CDN chung nếu provider/tenant permission thiếu.
3. Ưu tiên logs, synthetic staging endpoint hoặc asset inventory có quyền.
4. Ghi rõ một IP có thể phục vụ nhiều hostname/SNI, certificate và tenants.
5. Không nâng same-IP/certificate correlation thành actor attribution hoặc ownership.

## 15. Reconnaissance trong cloud và Kubernetes

### 15.1. Cloud “read-only inventory” khác kiểm thử external exposure

Một API cloud inventory có thể hiển thị VM có public IP hoặc security group cho TCP/443, nhưng **chưa chứng minh có đường mạng end-to-end từ Internet**:

- Route table, NACL, firewall, private endpoint hoặc provider policy có thể chặn.
- Destination có thể ngừng chạy hoặc chỉ cho TLS/app identities hợp lệ.
- Traffic tới load balancer có thể đi qua WAF/proxy/mesh trước workload.
- Một policy trên cloud account này không thể suy cho account khác.

Để kiểm chứng exposure, cần **effective reachability analysis** hoặc một **kiểm tra chủ động nhỏ trên endpoint sở hữu**, với external source thật được phê duyệt. Không tự quét toàn bộ public IP range của cloud account chỉ từ danh sách inventory.

### 15.2. Kubernetes: đừng nhầm namespace với network boundary

Kubernetes Namespaces giúp tổ chức tài nguyên/RBAC nhưng **không mặc định cô lập network**. NetworkPolicy chỉ enforce khi CNI hỗ trợ đúng và policy phù hợp. Một Pod có thể:

- Gửi traffic từ Pod IP hoặc sau SNAT bằng Node IP.
- Kết nối qua Service VIP/EndpointSlice/Ingress/LoadBalancer.
- Dùng service mesh sidecar/ambient gateway, tạo thêm tunnel/port.
- Dùng hostNetwork hoặc alternate CNI interfaces, có semantics khác Pod traffic.
- Được phép bởi **union của nhiều NetworkPolicies** cùng chọn Pod.

Với reconnaissance mô phỏng:

| Câu hỏi | Nguồn dữ liệu ít xâm lấn | Khi nào mới cần probe |
|---|---|---|
| Pod đang expose ports nào? | Deployment/Service/Pod specs và owner inventory | Khi cần chứng minh actual listener |
| NetworkPolicy chọn workload nào? | YAML policy, selectors, CNI observability | Khi cần verify effective deny/allow |
| Traffic đi qua Service VIP hay Pod IP? | CNI flow logs/EndpointSlices | Khi cần đo packet path thực tế |
| Service mesh xác thực workload? | mTLS proxy/access logs và trust domain config | Khi cần test control trên lab mesh |
| Pod có public exposure không? | Cloud LB/Ingress/SG/router audit | Khi cần external controlled reachability |

**Không tạo privileged Pods, mount host network, đọc Secrets hoặc exec vào workload production** chỉ để phục vụ bài reconnaissance nếu RoE không cho phép. Những hành động đó có thể vượt từ discovery sang thao tác nhạy cảm.

### 15.3. Ví dụ Kubernetes chỉ đọc

~~~bash
# Chỉ dùng trên cluster/namespace lab thuộc quyền.
kubectl config current-context
kubectl get namespaces
kubectl get services -n recon-lab
kubectl get endpointslices -n recon-lab
kubectl get networkpolicy -n recon-lab
kubectl get pods -n recon-lab -o wide
~~~

Các commands chỉ cung cấp **API view**, không chứng minh dataplane đang enforce. Việc liệt kê resources cũng vẫn phải tuân theo RBAC, confidentiality và audit; không đem output có nội dung hạ tầng nội bộ lên kênh chia sẻ rộng.

## 16. Khi nào một quan sát là exposure và khi nào chỉ là metadata?

| Bằng chứng | Kết luận hợp lý | Không được suy |
|---|---|---|
| Public DNS record trỏ tới IP | Tên được resolve trong view đó | Service đã reachable/compromised |
| Certificate SAN chứa hostname | Cert được cấp với tên đó theo nguồn | Hostname hiện đang phục vụ dữ liệu |
| TCP connect tới 443 thành công | Có kết nối TCP tại time/vantage point | HTTPS endpoint đã xác thực đúng và dễ khai thác |
| TLS validation PASS trong lab | Peer certificate khớp policy tại thời điểm kiểm tra | HTTP/API authorization hoặc business logic an toàn |
| HTTP HEAD trả 200 | Một request phù hợp được server/proxy trả lời | Dữ liệu nhạy cảm đã lộ hoặc app có lỗ hổng |
| Service header chứa version | Một banner/header tự khai version | Chắc chắn chạy binary chưa vá |
| Firewall deny trong log | Một flow bị deny tại enforcement point được ghi | Không có alternate path/VPN/IPv6 bypass |
| SIEM không tạo alert | Không có alert theo rule và observation window | Không có traffic hoặc không có năng lực phát hiện |
| NDR alert “scan-like” | Detector nhận dạng mẫu phù hợp | Source là attacker hoặc hành vi ngoài quyền |

### 16.1. Service exposure cần nhiều điều kiện

Một đánh giá exposure nghiêm túc thường xét:

1. Tài sản và service **đang tồn tại** tại thời điểm T.
2. Từ một source thuộc mô hình đe dọa, network path cho phép đến đích.
3. Ứng dụng nhận được tương tác và phản hồi tương ứng.
4. Identity/authentication/authorization controls có hiệu lực phù hợp.
5. Có lỗ hổng/configuration risk hay chỉ là bề mặt công khai đã chấp nhận?
6. Dữ liệu và chức năng nhạy cảm được bảo vệ thế nào?

Reconnaissance có thể xác nhận một phần (1–3) trong lab; **không tự xác nhận mục (4–6)** nếu không có test được phê duyệt khác.

## 17. Detection engineering: bài mô phỏng giúp blue team thấy gì?

### 17.1. Mô hình dữ liệu event hữu ích

~~~yaml
# Sự kiện giả lập để bàn về telemetry, không phải dữ liệu tổ chức thật.
eventType: network-connection-attempt
eventTimeUtc: "2026-11-28T10:15:22.034Z"
source:
  assetId: red-lab-vm
  privateIp: 10.10.1.10
  translatedIp: 192.0.2.50
destination:
  assetId: web-lab-vm
  ip: 192.0.2.20
  port: 443
transport: TCP
securityDecision:
  enforcementPoint: lab-firewall
  action: allow
sensor:
  name: lab-flow-collector
  captureScope: lab-segment-A
correlation:
  exerciseId: RED-RECON-LAB-003
  actionId: R-TCP-01
  sourceClockOffset: "documented-out-of-band"
privacy:
  rawPayloadCaptured: false
~~~

Đây là **mẫu tập huấn**, không phải schema chung. Trong logs thật, `translatedIp` hoặc `assetId` có thể không tồn tại; phải lấy từ NAT/IAM/CMDB/EDR phù hợp và ghi confidence khi nối.

### 17.2. Phân biệt các chặng phát hiện

~~~mermaid
flowchart TD
    ACT["Red executes approved test"] --> OBS["Sensor observes event"]
    OBS --> ING["Collector ingests and normalizes"]
    ING --> DET["Detection logic evaluates"]
    DET --> AL{"Alert expected by policy?"}
    AL -->|"Yes"| ROUTE["Alert routed to SOC queue"]
    AL -->|"No"| LOG["Event stored for hunt / baseline"]
    ROUTE --> TRI["Analyst triage"]
    TRI --> CASE["Case / containment decision per runbook"]
    LOG --> REV["Post-exercise evidence review"]
    CASE --> REV
~~~

Một bài kiểm thử có thể phát hiện:

- **Sensor gap:** không có event dù flow thực tới đúng sensor path.
- **Ingestion gap:** sensor ghi event nhưng SIEM không nhận.
- **Parsing gap:** SIEM không chuẩn hóa đúng source/dest/port.
- **Detection gap:** event tồn tại, logic đáng ra match nhưng không phát alert.
- **Routing gap:** alert có nhưng không vào đúng queue/on-call.
- **Triage gap:** analyst bỏ sót hoặc đánh giá sai.
- **Response gap:** SOC biết nhưng quyết định/chủ trách nhiệm hoặc hành động khôi phục không phù hợp.

Đây là các loại vấn đề **khác nhau**, cần action items riêng.

### 17.3. “Không bị phát hiện” không phải một mục tiêu an toàn

Trong một bài test blind, mục tiêu đo năng lực phòng vệ có thể yêu cầu không thông báo trước tới từng analyst. Nhưng hành động khám phá **vẫn phải nằm trong RoE và safety supervision**. Không dùng:

- Tampering hoặc xóa log để giấu dấu vết test.
- Source spoofing nhằm né scope, hoặc pivot sang tài sản không được phép.
- Traffic tunneling/encoding nhằm lách detector khi chưa có approval riêng.
- Dịch vụ của người thứ ba làm proxy để che nguồn.
- Thay đổi host/endpoint chính thức để SOC “không nhận ra”.

Nếu mục tiêu muốn mô phỏng những kỹ thuật đó, đó là **một bài tập khác**, cần threat/risk review, provider authorization, containment và stop controls riêng.

## 18. Deconfliction: phân biệt exercise với incident thật

Một bài reconnaissance chủ động có thể tạo alerts giống kẻ tấn công. Trong các mode blind, SOC không biết chi tiết, nhưng **white cell** phải có khả năng xác nhận an toàn:

- Exercise ID, approved source IP/asset, test windows và action ledger.
- Kênh xác minh 24/7 trong thời gian exercise hoặc đúng on-call window.
- Tín hiệu emergency stop được hai bên công nhận, **không phụ thuộc kênh duy nhất dễ mất**.
- Quy định nếu xuất hiện sự cố thật đồng thời: ai dừng test, ai bảo toàn evidence.
- Không xóa dữ liệu SOC để tránh ảnh hưởng detection metrics.
- Kết quả cuối phải đánh giá **SOC phản ứng hợp lý theo dữ liệu họ có**, không chỉ theo “đáp án” của red.

### 18.1. Khi có incident thật cùng thời điểm

Nếu SOC phát hiện host ngoài RoE bị truy cập hoặc service health suy giảm:

1. **Dừng ngay các active probes** thuộc exercise.
2. Liên hệ white cell/asset owner/incident commander.
3. Bảo toàn **test action ledger, timestamps và logs**, không sửa để phân biệt về sau.
4. Khai báo những hành động của red đã làm, không giấu vì sợ ảnh hưởng điểm số.
5. Tách activity đúng RoE khỏi evidence về incident thật theo source/time/technique.
6. Chỉ tiếp tục khi chủ thể có thẩm quyền tái cho phép.

**Safety luôn ưu tiên hơn tính bí mật hoặc điểm số của bài tập.**

## 19. Stop conditions và kill switch vận hành

### 19.1. Các dấu hiệu bắt buộc dừng hoặc pause

| Trigger | Hành động |
|---|---|
| DNS trỏ sang third-party/shared endpoint ngoài phạm vi | Không gửi active probe tới endpoint đó |
| Host owner hoặc safety controller ra lệnh dừng | Dừng active tools ngay và xác nhận |
| Service p95/p99 latency/5xx vượt ngưỡng đã thỏa thuận | Dừng, gửi trạng thái cho SRE và white cell |
| Thiết bị hoặc sensor có CPU/memory/session exhaustion | Dừng, hỗ trợ khôi phục theo owner |
| Có sensitive data/credentials ngoài dự kiến trong output | Ngừng mở rộng, cô lập dữ liệu và privacy escalation |
| Test traffic xuất hiện ở production hoặc partner network | Dừng; đánh giá scope breach |
| Người vận hành mất kênh liên lạc/emergency contact | Không tiếp tục active probes |
| Xuất hiện dấu hiệu tấn công thật hoặc outage độc lập | Dừng exercise, phối hợp incident response |
| Hết thời gian hoặc request budget | Dừng; không nới limit tự động |
| Tool hoạt động khác plan, tự redirect/sinh requests phụ | Dừng và review phiên bản/options |

### 19.2. “Kill switch” phải được thử trước

Trong bài mô phỏng, kill switch có thể đơn giản là:

- Operator dừng lệnh/probe đang chạy.
- White cell gọi hoặc gửi một mã dừng qua kênh đã định.
- Lab firewall/test orchestration ngăn tiếp requests từ nguồn exercise.

**Không phải kỹ thuật nào có thể bị thu hồi hoàn toàn ngay lập tức**: TCP/HTTP requests đã gửi có thể còn xử lý ở server; cloud logs có ingestion lag. Vì vậy **dừng gửi mới** và **xác minh hệ thống ổn định** là hai bước khác nhau.

### 19.3. Exercise stop record

~~~text
Exercise ID: RED-RECON-LAB-003
Stop requested by: safety controller / asset owner
Requested at: UTC
Operator acknowledgement at: UTC
Last active probe time: UTC
Background tool processes checked: Yes/No
Lab service health: verified/unverified
Unexpected data encountered: Yes/No
Incident escalation: ticket ID if applicable
Resume allowed: Only on renewed authorization
~~~

## 20. Evidence, privacy và chain of custody

Reconnaissance có thể thu về:

- IP và hostname nội bộ, network topology, certificate SANs.
- Web/server headers, reverse proxy identifiers, platform version hints.
- DNS queries/answers liên quan employees hoặc tenants.
- Firewall/IDS logs, source identity/NAT translation, user/device context.
- Trong một số trường hợp **accidental secrets** ở debug headers hoặc public metadata.

Ngay cả khi những dữ liệu này có vẻ “không phải payload”, chúng vẫn có thể là **confidential asset metadata**.

### 20.1. Những thứ cần lưu

| Artifact | Mục đích | Cách bảo vệ |
|---|---|---|
| **RoE/approval version** | Chứng minh action nằm trong scope | Restricted change repository |
| **Command/action ledger** | Biết red làm gì vào thời điểm nào | Audit, UTC timestamp |
| **Tool/version/options** | Có thể tái hiện hành vi trong lab | Versioned metadata, no secrets |
| **Result summary** | Đo reachability/headers/response states | Redact data ngoài mục đích |
| **Blue sensor/alert logs** | Đối chiếu detection pipeline | Need-to-know access, retention |
| **Health/SLO metrics** | Xác minh không gây gián đoạn | Correlation theo time window |
| **Evidence hashes** | Kiểm tra artifact integrity | Ghi rõ bytes được hash |
| **Findings/action items** | Sửa gaps và replay | Owner, acceptance tests, deadline |

### 20.2. Red action ledger

~~~text
Exercise: RED-RECON-LAB-003
T0: Operator receives renewed approval and checks scope.
T1: Authorized DNS A query to lab resolver for web.recon.example.test.
T2: Operator validates returned IP belongs to lab asset.
T3: One bounded TCP check to lab web server port 443.
T4: One HTTP HEAD to localhost lab service (if approved).
T5: Blue evidence snapshot and health verification.
T6: Stop and confirm no process continues sending probes.

For each entry:
  UTC time, action ID, operator, source, target, exact options,
  expected packets, actual outcome, evidence pointer, notes.
~~~

Ghi **cả actions tạo kết quả không thành công** và những action bị dừng trước khi chạy do scope review. Không bỏ chúng khỏi timeline để metrics đẹp hơn.

### 20.3. Giữ bản gốc nhưng không chia sẻ quá mức

- Hash raw artifacts (ví dụ SHA-256) để đối chiếu khi chuyển giao.
- Bảo quản bản gốc đúng quyền, phân tích trên bản sao.
- Không lấy hash làm thay thế encryption; file hash được nhưng vẫn lộ nội dung nếu lưu công khai.
- Không đưa raw tokens, cookies, private keys, customer payload vào ticket/chats.
- Khi cần redaction, ghi rõ trường nào bị ẩn và ảnh hưởng tới kết luận.
- Có thời hạn lưu, legal hold nếu áp dụng và kiểm tra các bản sao được xóa đúng policy.
- Với active scanning, log mạng có thể tạo ảnh hưởng tới khách hàng nếu thu thập sai nguồn; giữ asset IDs và timezone để tránh quy nhầm.

### 20.4. Cẩn trọng với screenshots và report attachments

Ảnh màn hình công cụ đôi khi chứa địa chỉ quản trị, nhân viên, tên project hoặc keys, ngay khi nội dung chính chỉ là một cổng mở. Ưu tiên **bảng kết quả đã được chọn và kiểm duyệt**, chỉ đính raw evidence khi người nhận có quyền tương ứng.

## 21. Các điểm mù khiến một bài reconnaissance bị đánh giá sai

### 21.1. “Không có alert” khác “không có observation”

Một detector thường có **threshold, aggregation window, suppression, allowlists và severity rules**. Một TCP connect từ host lab có thể:

- Được firewall ghi log nhưng không match IDS detection.
- Được IDS ghi telemetry nhưng chưa đạt threshold.
- Đạt threshold nhưng alert được suppress trong testing window.
- Tạo alert trong SIEM nhưng không được route tới đúng SOC queue.
- Được SOC triage là scheduled activity có xác nhận white cell.

**Expected result khác nhau theo giả thuyết.** Nếu RoE yêu cầu kiểm tra khả năng quan sát log, không thể gọi test fail chỉ vì không có alert.

### 21.2. Sensor bị thiếu hoặc đặt sai vị trí

| Điểm mù | Nguyên nhân có thể | Cần xác minh |
|---|---|---|
| Source IP không khớp | SNAT/VPN/proxy | Translation logs và session ID |
| Không thấy UDP/53 | DNS cache, DoH/DoT/DoQ | Endpoint/resolver context |
| TCP traffic không xuất hiện | Sai NIC/VRF hoặc route bất đối xứng | Vantage point, FIB, interface counters |
| Không thấy HTTP Host | HTTPS/TLS mã hóa | Authorized app/proxy logs |
| SNI không phản ánh target | ECH, proxy, no SNI | Client/endpoint logs, protocol details |
| Service TLS cert không thấy | TLS 1.3 encrypted handshake | TLS termination/cert inventory |
| Host sau NAT bị gán sai | Shared egress IP | 5-tuple, port/time mapping |
| K8s Pod không thấy ở NIC ngoài | Overlay/tunnel, eBPF datapath | CNI/Service/Node flow context |
| IPv6 flow không có trong report | IPv4-only collector | Dual-stack policy/telemetry |
| Firewall deny nhưng service vẫn reachable | Route bypass, alternate listener, session state | Effective path/control-point check |
| Sensor logs không vào SIEM | Pipeline failure, parsing, clock skew | Collector heartbeat và ingestion errors |

### 21.3. Detection không tự là response

Một analyst nhận diện đúng red-team activity nhưng không chặn vì traffic có approval hoặc chưa tới ngưỡng incident có thể **đang làm đúng quy trình**. Đánh giá phản hồi dựa vào **scope, risk tier, runbook và thông tin sẵn có tại thời điểm đó**, không ép SOC phải cách ly tài sản lab.

### 21.4. False negatives không thể đo từ những gì không quan sát

Nếu không có **ground truth của hành động red**, không thể biết hệ thống đã bỏ lỡ bao nhiêu. Tập test cần action ledger xác thực, time windows và kỹ thuật đã chạy thực sự, kể cả những actions bị hủy. Cũng phải biết collector có health và log retention đúng.

## 22. Threat model: 28 rủi ro trong mô phỏng reconnaissance

| ID | Rủi ro | Hậu quả | Kiểm soát/bằng chứng |
|---|---|---|---|
| R01 | **Không có authorization rõ** | Test ngoài quyền | Signed RoE, asset-owner approval |
| R02 | **Chỉ có tên miền, thiếu IP scope** | Probe CDN/third-party | Resolve + owner revalidation |
| R03 | **Asset/IP đã chuyển chủ** | Tương tác sai tenant | Current inventory and time-bounded scope |
| R04 | **CNAME ra ngoài scope** | Probes tới provider | Stop at DNS scope review |
| R05 | **Quét CIDR quá rộng** | Hệ thống ngoài danh sách bị chạm | Exact approved target list |
| R06 | **IPv6 bị quên trong RoE** | Vô tình tới endpoint khác | Explicit dual-stack constraints |
| R07 | **Retry/concurrency quá cao** | Resource exhaustion, outages | Rate/count/time bounds, monitoring |
| R08 | **Legacy/OT bị chạm** | Tác động an toàn vận hành | Out-of-scope safety assets |
| R09 | **HTTP redirect tự theo** | Gửi request ngoài scope | Disable automatic redirects, review target |
| R10 | **Script/plugin gửi probes phụ** | Thực thi kỹ thuật chưa phê duyệt | Tool version/options review |
| R11 | **Banner bị coi lỗ hổng chắc chắn** | False positive, xử lý sai | Owner/config validation |
| R12 | **Shared CDN IP bị quy actor** | Chặn nhầm tenants | App/Host/tenant evidence |
| R13 | **Chỉ nhìn TCP/443** | Bỏ qua UDP/443/QUIC có trong scope | Protocol-specific monitoring |
| R14 | **DNS hiện tại thay lịch sử** | Sai timeline | Timestamped DNS evidence |
| R15 | **SNAT gán sai red source** | Triage sai attribution | Pre/post NAT mapping |
| R16 | **VPN/proxy che vantage point** | Sensor gap bị hiểu là detection failure | Hop-by-hop diagram |
| R17 | **SIEM pipeline lag** | Alert trễ, đánh giá time sai | Event vs ingest timestamp |
| R18 | **Clock skew** | Correlation lệch | UTC/time synchronization/offsets |
| R19 | **Blind exercise không có white cell** | Nhầm incident thật, không dừng được | Safety controller/deconfliction |
| R20 | **Kéo dài quá test window** | Hoạt động ngoài authorization | External stop timer/operator oversight |
| R21 | **Không có stop contact** | Không xử lý nhanh tác động | Emergency escalation rehearsal |
| R22 | **Thu credentials/PII ngoài ý định** | Secondary data exposure | Minimize data, restricted evidence |
| R23 | **PCAP được chia sẻ quá rộng** | Lộ topology/secrets | Encryption, RBAC, retention |
| R24 | **Ẩn/xóa audit vì “blind”** | Hỏng traceability/incident response | Immutable action ledger |
| R25 | **Không có baseline** | Không phân biệt test với lỗi sẵn có | Before/after health and logs |
| R26 | **Không có positive control** | Timeout bị hiểu là policy deny | Healthy target and enforcement verdict |
| R27 | **Kết luận “không alert” = phòng vệ thất bại** | Đánh giá detector sai | Expected rule/threshold and event stages |
| R28 | **Không theo dõi remediation** | Bài kiểm thử chỉ còn báo cáo | Owner, due date, replay evidence |

### 22.1. Đánh giá theo blast radius

Một lệnh TCP connect nhỏ tới **PLC/OT controller** có thể nguy hiểm hơn nhiều request trên một web VM lab chịu tải tốt. Một DNS lookup cho hostname nhân sự có thể nhạy cảm dù không có port scan. Vì vậy **số packets thấp không tự bảo đảm rủi ro thấp**: cần xem loại tài sản, tác động, dữ liệu và quyền.

### 22.2. Attack simulation không phải cuộc thi “ẩn mình”

Trong exercise có approval, red team cần xác thực **detection/response objectives**, không phải đạt số lượng tài sản quét nhiều nhất. Nếu bài tập yêu cầu đánh giá blind response, chỉ **SOC analysts trong phạm vi được thiết kế** không biết lịch trình; white cell và asset owner luôn có thông tin và khả năng dừng.

## 23. Ma trận kiểm thử positive/negative của một exercise

Tất cả tình huống đều được chạy trong **lab đã phê duyệt** hoặc dùng data replay/synthetic evidence, không chuyển kỹ thuật sang production/third-party nếu chưa có RoE tương ứng.

| ID | Tình huống | Kết quả mong muốn | Evidence |
|---|---|---|---|
| P01 | RoE có nguồn, đích, thời gian và owner | Phạm vi kiểm chứng được | Approval record |
| N01 | Source ngoài danh sách thử khởi tạo exercise | Orchestration/review từ chối | Scope gate |
| N02 | Hostname resolve ra third-party/CDN ngoài RoE | Không gửi active probe | Resolver log + stop ledger |
| N03 | IP hiện thuộc tenant khác | Test dừng trước kết nối | Ownership check |
| P02 | Lab DNS A query đúng zone | Resolver nhìn QNAME/answer | DNS log + action ID |
| P03 | Lab DNS AAAA query đúng zone | IPv6 result được ghi đúng | Resolver/client logs |
| N04 | DNS resolver không hoạt động | Không kết luận “target không có hostname” | Known-good resolver health check |
| P04 | Bounded TCP connect tới lab port 443 | Firewall event xuất hiện | 5-tuple/time/verdict |
| N05 | Port ngoài approved list | Tool/reviewer không chạy probe | Plan enforcement |
| N06 | Bounded request budget hết | Operator dừng, không retry thêm | Action ledger + tool config |
| P05 | HTTP HEAD tới localhost lab | Server access log có method/status | Web logs |
| N07 | HTTP trả redirect ngoài scope | Client không tự theo | No-follow behavior + ledger |
| P06 | TLS lab peer validation PASS | Certificate/SNI/chain theo policy | Client validation event |
| N08 | TLS peer hostname sai | Verification fail, không tắt validation | Error log |
| P07 | Network route qua lab firewall | Source/dest match enforcement point | Flow/route evidence |
| N09 | NAT làm đổi source IP | Analyst không quy nhầm source host | NAT translation mapping |
| N10 | Firewall capture chỉ một chiều | Không suy server không trả lời | Reverse path/positive control |
| P08 | CNI flow logs trong cluster lab | Pod/namespace identity hiện khi được hỗ trợ | CNI and workload logs |
| N11 | Kubernetes API có NetworkPolicy nhưng CNI thiếu enforce | Không gọi segmentation PASS | Dataplane result |
| P09 | SIEM nhận event từ sensor | Event fields được parse chính xác | Event/ingestion IDs |
| N12 | Collector ngừng ingest | Health monitor phát hiện telemetry gap | Collector heartbeat |
| N13 | SIEM không alert cho phép thử dưới threshold | Đánh giá theo expected design | Rule threshold config |
| P10 | Synthetic alert vượt threshold đã duyệt | Alert vào đúng SOC queue | Detection/routing IDs |
| N14 | Alert route sai owner | Gap được phân loại routing, không phải sensor | Alert routing audit |
| P11 | Analyst triage đúng activity | Case được phân loại theo runbook | Case timeline |
| N15 | White cell xác nhận authorized exercise | Không cô lập hệ thống lab vô cớ | Deconfliction record |
| P12 | Safety controller yêu cầu stop | Probes dừng, có ack | Stop timestamp/process check |
| N16 | Mất kênh liên lạc với safety controller | Tạm ngừng active work | Operator record |
| N17 | App SLO xấu đi sau test | Dừng và escalate tới owner | Health and stop logs |
| N18 | Unexpected sensitive header/data | Ngừng lưu lan rộng và phân loại | Redacted evidence record |
| P13 | Evidence hash/custody PASS | Artifact intact và access restricted | SHA-256 + audit |
| N19 | Người không thuộc exercise cố xem raw logs | RBAC chặn | Access-denial audit |
| N20 | Clock lệch giữa red và SIEM | Timeline có offset, không suy nhầm | Raw/normalized time |
| N21 | Một IP shared với nhiều hostnames | Không gán actor hoặc tenant chỉ từ IP | CDN/Host context |
| N22 | Active check phát hiện source ngoài RoE | Stop, owner/IC escalation | Scope breach record |
| P14 | Purple-team replay sau detector tuning | Event/alert/case đạt objective | Before/after outcome |
| N23 | Finding không có owner/acceptance | Không coi remediation đã hoàn tất | Action tracker |
| N24 | Không thấy traffic do wrong vantage point | Không gọi “blue team không phát hiện” | Sensor placement + known-good control |

**Tổng cộng 38 ca mô phỏng trong ma trận**: 14 positive (P01–P14) và 24 negative (N01–N24). Không nhất thiết chạy cả 38 trong một buổi; chọn test theo hypothesis và RoE, và không nâng quy mô thiếu phê duyệt.

### 23.1. Vì sao negative tests có thể cho kết luận sai?

Ví dụ một source lab thử TCP connect tới port ngoài scope và nhận timeout. Có thể do:

- Source host chưa có route.
- Service không listening.
- Firewall chặn đúng.
- Sensor bị lỗi hoặc packet loss.
- Scope gate đã chặn lệnh trước khi gửi packet.

Mỗi nguyên nhân yêu cầu **bằng chứng khác nhau**. Không gọi “firewall deny PASS” khi chỉ biết timeout; cần đối chiếu firewall decision với destination healthy control nếu test thực sự chạy trong phạm vi.

## 24. Kịch bản xuyên suốt: một subdomain trỏ sang CDN ngoài scope

### 24.1. Bối cảnh giả định

Tổ chức có zone `recon.example.test` và hai lab VMs:

- `web-a.recon.example.test` → VM lab `192.0.2.20` do nội bộ quản lý.
- `dns-a.recon.example.test` → DNS server lab `192.0.2.53`.
- `old-api.recon.example.test` có CNAME tới một shared CDN domain mà tổ chức **không được phép active test**.
- Blue team đang giám sát firewall/SIEM và có on-call.

RoE cho phép passive review toàn zone lab, nhưng **active TCP/HTTP tests chỉ được gửi tới hai VMs lab**. Exercise owner muốn biết liệu operator có tuân thủ scope khi DNS thay đổi và liệu SOC có thể phân biệt behavior test đã phê duyệt.

### 24.2. Các bước hợp lệ

| Thứ tự | Hoạt động | Kết quả |
|---|---|---|
| 1 | Đọc RoE, source/target inventory, TTL/record ownership | Xác định chỉ lab VMs in scope |
| 2 | Đối chiếu zone records/CNAME từ log/authoritative lab | Nhận ra old-api hướng shared CDN |
| 3 | Dừng active testing với old-api, ghi scope caveat | Không chạm CDN |
| 4 | Chạy bounded DNS queries tới resolver lab | Có expected DNS telemetry |
| 5 | Thử TCP connect với web-a trên 80/443 theo RoE | Có network flow evidence |
| 6 | Gửi một HTTP HEAD nếu được phê duyệt | Web log có action |
| 7 | Kiểm tra blue events/health, điều phối white cell | Đánh giá coverage và safety |
| 8 | Báo cáo kết quả và action items | Không suy CDN đang exposed |

### 24.3. Một thay đổi DNS giữa exercise

Giả sử khi tới bước 5, DNS answer của `web-a.recon.example.test` đã đổi từ `192.0.2.20` sang IP ngoài allowlist do một deployment mới. Operator phải:

1. **Không tiếp tục dùng hostname đó như một target đã được phê duyệt**.
2. Dừng/kiểm tra change và hỏi asset owner/safety controller.
3. Đối chiếu cloud inventory/hosting ownership ở thời điểm hiện tại.
4. Chỉ thực hiện tiếp nếu RoE được cập nhật/approval mới hợp lệ.

**“Đó vẫn là hostname của công ty” không phải lý do bỏ qua target ownership.**

### 24.4. Kết luận mẫu có căn cứ

> “Trong exercise RED-RECON-LAB-003, các DNS requests và TCP connections tới hai lab VMs được phê duyệt đã tạo events phù hợp trong resolver/firewall logs. SIEM nhận events nhưng không phát high-severity alert cho các phép thử dưới ngưỡng cảnh báo đã được thiết kế; đây là kết quả phù hợp với hypothesis. Một CNAME của old-api trỏ ra shared CDN, nên operator dừng active verification do ngoài RoE. Chưa có bằng chứng về lỗ hổng, xâm nhập hay exposure của CDN endpoint.”

**Đó là một bài thực hành thành công về scope và observability**, dù không có lỗ hổng nào được khai thác.

## 25. Báo cáo findings theo từng bước xử lý

Một finding không chỉ là “port 443 open”. Nên ghi:

~~~text
FINDING-ID: RED-RECON-LAB-003-F01
Objective:
  Kiểm tra visibility của TCP connection tới lab web server
Authorization:
  RoE version, owner, approved source/target/window
Red action:
  Action ID, exact command/options, UTC timestamp
Target validation:
  Asset ID, IP ownership proof, DNS resolution at T
Observation:
  TCP connection state, tool version, response metadata
Blue evidence:
  Sensor event ID, firewall verdict, SIEM ingestion ID, case ID
Expected:
  Event searchable, no required high-severity alert
Actual:
  Event present; no alert, matching rule threshold
Assessment:
  PASS (for specified objective); no exposure conclusion
Gaps:
  NAT translation fields missing for some traffic
Risk:
  Source attribution ambiguity if NAT pool shared
Recommendation:
  Enable/reconcile NAT translation telemetry where justified
Owner / deadline / acceptance test:
  Assigned by relevant engineering team
Evidence:
  Restricted artifact pointers, hashes, collection timestamps
~~~

### 25.1. Một finding “không phát hiện” cần mô tả đầy đủ

| Phân loại | Ví dụ | Hướng khắc phục |
|---|---|---|
| **No observation** | Firewall không có event dù target được xác minh | Sensor path/config/traffic mirroring |
| **No ingestion** | Firewall log có, SIEM không có | Collector pipeline, parsing, retention |
| **No rule match** | SIEM event có, logic mong đợi không match | Detector design/tuning |
| **No alert route** | Detection match nhưng SOC queue không nhận | Alert routing/escalation |
| **No acknowledgement** | Alert vào queue nhưng không ai nhận đúng hạn | On-call/load/response process |
| **Expected silence** | Test dưới threshold theo policy | Không tự coi là finding; ghi rationale |

### 25.2. Không nên quy trách nhiệm cá nhân khi finding là lỗi hệ thống

Nếu analyst không phát hiện vì source IP bị NAT và logging không có mapping, vấn đề có thể là **telemetry design và observability ownership**, không phải đơn giản analyst “thiếu kỹ năng”. Ngược lại, một alert đáng lẽ cần được triage nhưng bị ignore có thể phản ánh load, suppression, quy trình hoặc training. Post-exercise review nên tập trung **systemic controls và acceptance criteria**.

## 26. KPI và phép đo kết quả không gây hiểu nhầm

| KPI | Ý nghĩa | Cách hiểu đúng |
|---|---|---|
| **Scope compliance** | % red actions trong RoE | Một breach nghiêm trọng không nên bị che bởi tỷ lệ tổng cao |
| **Authorized test completion** | Phần test cases đã thực sự chạy | Test bị hủy vì safety không nên ép chạy bằng mọi giá |
| **Sensor visibility coverage** | % actions mong đợi có events tại sensor | Cần ground truth và network path verification |
| **SIEM ingestion coverage** | % sensor events tới SIEM đủ trường | Không đồng nghĩa detector match |
| **Detection-rule match** | % events đúng pattern match rule | Đo theo threshold/intended logic |
| **Alert routing accuracy** | Alerts tới đúng queue/owner | Tách khỏi sensor và analyst performance |
| **Time to acknowledge** | Từ alert đến analyst nhận | Đồng hồ/timezones và SOC staffing quan trọng |
| **Time to classify** | Từ nhận alert đến phân loại đúng | Không khuyến khích phân loại nhanh thiếu căn cứ |
| **False positive / false negative** | Tương quan kết quả với ground truth | False negatives cần biết hành vi thực đã chạy |
| **Asset attribution accuracy** | Nối đúng NAT/VPN/host identity | IP alone không chứng minh principal |
| **Stop-response latency** | Thời gian từ stop signal tới dừng probes | Cần kiểm tra cả processes còn chạy |
| **Service impact** | Latency/errors/capacity/SLO từ bài test | Bảo đảm bài tập không tạo outage |
| **Remediation validation** | Findings đã có owner và replay PASS | “Đã sửa rule” chưa đủ |

### 26.1. Không chỉ đếm “số alerts”

Nhiều alerts hơn chưa chắc tốt hơn: một buổi reconnaissance lab với vài TCP connections có thể chỉ cần logs dễ truy tìm, trong khi cảnh báo high-severity hàng loạt gây **alert fatigue**. Mục tiêu là **precision, coverage và response phù hợp risk tier**, không tối đa hóa tiếng ồn.

### 26.2. Đo đúng thời gian

~~~text
T0 = red action sent (from operator ledger)
T1 = event observed at sensor
T2 = event ingested into SIEM
T3 = detector match/alert creation (nếu có)
T4 = alert routed to analyst queue
T5 = analyst acknowledgement
T6 = triage/response decision

Sensor delay   = T1 - T0 (ước lượng theo đồng hồ)
Ingestion      = T2 - T1
Detection      = T3 - T2 (nếu alert expected)
Routing        = T4 - T3
Acknowledgment = T5 - T4

Không cộng/báo thời gian nếu clocks không đồng bộ
hoặc source time và receive time bị nhầm.
~~~

Mọi phép đo cần chỉ rõ cách chuẩn hóa UTC và **uncertainty**. Không tính time-to-detect nếu chưa chứng minh sensor thực đã nhìn event trong phạm vi được đánh giá.

### 26.3. Cần quan tâm cả tác động kinh doanh

Mỗi exercise report nên chứa: service response time, application errors, interface packet loss, CPU/load, ticket noise và những yêu cầu dừng. **Một bài test phát hiện được reconnaissance nhưng làm gián đoạn production** vẫn có thể là kết quả triển khai thất bại cần RCA.

## 27. Quy trình thực hiện 12 bước

### Bước 1 — Chọn hypothesis và target phòng vệ

Xác định cụ thể kỹ thuật khám phá nào cần đo, lý do từ threat model và expected detection behavior (chỉ log hay alert/case).

### Bước 2 — Xác nhận tài sản và phê duyệt

Lấy quyền từ asset owners, xác minh IP/FQDN/tenants hiện tại, đối chiếu shared/CDN/third-party hosting; ghi out-of-scope.

### Bước 3 — Chốt RoE, white cell và emergency stop

Ghi source/target, windows, allowed activities, rate/count/time, data handling, kênh báo và authority dừng. Thử kênh liên lạc trước.

### Bước 4 — Thiết lập test inventory và baseline

Ghi lab service health, listening ports đã được owner xác nhận, firewall rules, DNS answers, sensor/collector health và clock offsets.

### Bước 5 — Review tool options và test plan

Chọn công cụ có khả năng giới hạn network traffic; xem chính xác command/options và những hoạt động phụ. Không tự bật plugins/scripts hoặc service enumeration ngoài scope.

### Bước 6 — Thu dữ liệu thụ động tối thiểu

Đọc CMDB, DNS/cert/cloud inventory hoặc logs đã được cấp quyền, lưu provenance và thời điểm. Không mở rộng theo tên miền/IP mới nếu chưa kiểm owner.

### Bước 7 — Kiểm tra scope một lần nữa tại T0

DNS/IP/tenant owner có thể thay. Nếu target resolve ngoài allowlist, không chạy active step và ghi lý do dừng.

### Bước 8 — Thực hiện active checks có giới hạn

Chỉ các DNS/TCP/HTTP/TLS checks đã phê duyệt, source và đích chính xác, concurrency thấp và deadline rõ. Quan sát health/stop conditions.

### Bước 9 — Xác minh không còn hoạt động ngoài cửa sổ

Dừng mọi processes liên quan, kiểm actual requests đã gửi, thông báo safety controller và ghi timestamp kết thúc.

### Bước 10 — Ghép action ledger với telemetry

So red events với firewall/NDR/DNS/server/SIEM, bao gồm NAT mapping, route view, timezone, ingestion lag, false negatives và intentional silence.

### Bước 11 — Đánh giá và đề xuất cải tiến

Phân loại gaps theo sensor/ingestion/detection/routing/triage/response, xác định owner và acceptance tests; không suy khai thác từ port/banner.

### Bước 12 — Purple-team replay và đóng evidence

Khi owner triển khai cải tiến, phát lại **cùng test đã được phê duyệt** hoặc synthetic event, xác nhận outcomes, bảo quản/xóa dữ liệu theo retention và báo cáo cho sponsor.

## 28. Bài tập tình huống và câu hỏi phỏng vấn

### 28.1. Câu hỏi

1. Vì sao kiểm thử một subdomain công ty có CNAME tới CDN ngoài scope có thể vi phạm RoE?
2. Phân biệt **passive inventory** và **active network probe** theo tương tác và tác động.
3. Một certificate có SAN chứa tên H có chứng minh website H đang mở cổng 443 không?
4. Vì sao **một port open** không chứng minh có lỗ hổng hoặc application authorization sai?
5. Dấu hiệu nào cho thấy một test passive đã vô tình chia sẻ hostname nhạy cảm với bên thứ ba?
6. Tại sao cường độ thấp không tự bảo đảm an toàn cho OT/legacy equipment?
7. Trong bài TCP connect, làm sao phân biệt **sensor không nhìn flow** với **detector không tạo alert**?
8. Nếu một flow log hiển thị NAT IP, những thông tin nào cần để quy về red VM?
9. Khi CNI overlay chỉ thấy outer UDP packets, nên lấy thông tin workload từ đâu?
10. Một kết quả `filtered` có chứng minh firewall đang deny hay không?
11. Nếu HTTP HEAD được redirect sang domain thứ ba, operator phải làm gì?
12. Vì sao không nên dùng `--insecure` để kiểm TLS identity trong bài học?
13. Khi TLS 1.3/ECH được sử dụng, passive observer có thể không thấy những gì?
14. Một bài dưới threshold không tạo alert có nhất thiết là SOC failure?
15. Blind exercise cần những ai biết phạm vi và cách dừng?
16. Điều gì xảy ra nếu SOC phát hiện incident thật trong lúc red đang thử nghiệm?
17. Thế nào là ground truth cho test detection? Điều gì xảy ra nếu action ledger thiếu?
18. Vì sao test timeout không đủ xác minh firewall policy deny?
19. Tính một ví dụ ingestion delay khi T1/T2 có clock offset; cần thông tin gì trước khi tính?
20. Đề xuất cách cải thiện triage khi analyst nhìn thấy shared NAT IP thay vì source workload.
21. Nếu một active probe vô tình thấy debug header chứa credential, thao tác nào là an toàn?
22. Nêu ít nhất năm trường cần có trong exercise report để có thể tái kiểm chứng.
23. Khi nào một red team finding cần chuyển sang incident response thay vì tiếp tục exercise?
24. Vì sao không nên coi số lượng alerts cao là KPI duy nhất?
25. Đề xuất hai positive và ba negative tests cho lab DNS–web–firewall có RoE cụ thể.

### 28.2. Gợi ý trả lời

- **Scope:** hostname hợp lệ về thương hiệu không cho phép active test third-party IP; DNS resolution và owner mapping phải được kiểm tại thời điểm chạy.
- **Bằng chứng:** certificate SAN và DNS records là metadata; actual flow, TLS validation, HTTP access và application AuthZ là các lớp khác.
- **Port open:** chỉ chứng minh reachability/handshake theo kỹ thuật và thời điểm; không phải exploitability.
- **Sensor/detection:** phải đo event observation → ingestion → rule match → alert routing → analyst handling tách biệt.
- **NAT:** dùng translation logs, source port/timestamp, endpoint/EDR/CNI identity.
- **Safety:** dừng khi có tác động, scope breach, unexpected data hoặc stop signal; giữ evidence và phối hợp owner.
- **TLS:** không tắt hostname/chain verification; ECH che inner SNI, TLS 1.3 mã hóa Certificate message.
- **False negative:** cần ground truth và coverage; nếu sensor không nhìn flow thì không đủ căn cứ để đánh giá rule không match.

### 28.3. Tabletop: yêu cầu “mở rộng cho đủ điểm”

**Tình huống giả định:** Sponsor thấy red team chỉ thu được vài DNS records và hai cổng mở. Sponsor đề nghị “quét thêm toàn bộ `203.0.113.0/24` và mọi subdomain, không cần thông báo để SOC bất ngờ”.

Các tình tiết mới:

- Cloud inventory chỉ xác nhận **một VM** thuộc dự án lab.
- Một số IP trong /24 có thể không thuộc tổ chức.
- Một subdomain dùng CDN shared infrastructure.
- SOC đang xử lý một incident thật trên production.
- SRE chưa sẵn sàng giám sát SLO cho test lớn hơn.

**Yêu cầu nhóm học viên:**

1. Chỉ ra chính xác phần nào của đề xuất vượt RoE.
2. Đưa ra **ba cách hợp lệ** để tăng giá trị exercise mà không mở rộng active probes: purple replay, synthetic events, phân tích inventory/logs có quyền.
3. Đề xuất một **change request mới** nếu sponsor thực sự cần mở phạm vi, có asset-owner/provider approvals, health gates và out-of-scope.
4. Nêu phương án dừng/khôi phục khi production incident vẫn đang diễn ra.
5. Viết thông điệp phản hồi sponsor dùng ngôn ngữ chuyên nghiệp, nêu điều kiện để tiếp tục.

**Đáp án định hướng:** không thực thi quét /24 hoặc CDN khi chưa đủ owner/provider permissions. Có thể đạt mục tiêu đo detection bằng **lab emulation và synthetic telemetry** trong khi đợi authorization; ưu tiên incident thật và safety controller. “Thêm điểm” không thay được RoE.

## 29. Checklist mô phỏng reconnaissance có phê duyệt

### 29.1. Trước exercise — Authorization và scope

- [ ] Có sponsor, asset owners, source operator, safety controller và blue contacts.
- [ ] RoE ghi rõ source, destination IP/FQDN, environment/tenant và protocol/port.
- [ ] Có **out-of-scope** về CDN/shared hosting, third parties, production, OT, employee devices.
- [ ] DNS resolution/ownership sẽ được kiểm lại sát thời điểm active test.
- [ ] Có phê duyệt loại kỹ thuật: passive, DNS, TCP connect, HTTP HEAD, TLS handshake.
- [ ] Không mặc định có quyền exploit, brute force, scan Internet hoặc thu payload.
- [ ] Có time window, request budget, concurrency, retries và stop deadline.
- [ ] Có SLO/availability baseline, owner và rollback/emergency-stop procedure.
- [ ] Mọi tool/options và hoạt động phụ đã được review theo lab/version.
- [ ] Có thiết kế declared/purple hay blind rõ, nhưng white cell luôn biết.
- [ ] Có kênh communication/deconfliction và backup contact.
- [ ] Có phương án data minimization, storage RBAC, encryption và retention.

### 29.2. Khi thu thập thụ động

- [ ] Ưu tiên internal CMDB, DNS/cloud/cert inventory, logs có quyền.
- [ ] Ghi provenance, timestamp và resolver/view cho các DNS records.
- [ ] Phân biệt DNS A/AAAA/CNAME/PTR, HTTP Host, SNI, certificate SAN.
- [ ] Không coi current DNS lookup thay historical DNS evidence.
- [ ] Không coi CT entry chứng minh cert được deploy hoặc service reachable.
- [ ] Không coi cùng CDN IP/ASN/cert issuer là cùng actor/tenant.
- [ ] Có privacy review trước khi gửi hostname nội bộ tới third-party enrichment service.
- [ ] Không tự mở rộng asset list từ một subdomain hoặc CIDR tìm thấy.

### 29.3. Khi chạy active checks

- [ ] Xác nhận đúng source VM, target ownership, time window và IP family.
- [ ] Không gửi probes nếu hostname resolve tới IP ngoài allowlist hoặc redirect ngoài scope.
- [ ] Chỉ dùng cổng/phương thức và rate/count/time đã được phép.
- [ ] Không dùng scanner scripts/exploit modules ngoài RoE.
- [ ] Không chạy credential guessing, DoS, stealth/evasion hoặc log tampering.
- [ ] Theo dõi firewall, app/SRE health, CPU, packet drops và stop signals.
- [ ] Biết TCP open/closed/filtered không tự chứng minh exploitability.
- [ ] Có positive controls và sensor health để phân biệt network deny với service down.
- [ ] Đã xét NAT/VPN/proxy, IPv4/IPv6, cloud/Kubernetes datapath.
- [ ] Nếu phát hiện secrets/PII không dự kiến, ngừng thu và escalates đúng người.
- [ ] Có action ledger/UTC timestamps, tool version/options và actual outcomes.
- [ ] Dừng tất cả active processes sau window hoặc theo emergency-stop request.

### 29.4. Đánh giá blue-team và kết thúc

- [ ] Đối chiếu mỗi red action với expected sensor/collector/detector pipeline.
- [ ] Phân biệt no observation, no ingestion, no rule match, no routing và no response.
- [ ] Không tự coi dưới threshold không có alert là security failure.
- [ ] Đã đối chiếu NAT source identity, traffic direction, routing/vantage và clock offsets.
- [ ] Không đánh giá false negative khi thiếu ground truth/positive control.
- [ ] Đã ghi rõ sự khác nhau giữa network reachability và app authorization.
- [ ] Đã tách authorized exercise khỏi incident thật bằng white-cell deconfliction.
- [ ] Raw artifacts có integrity check, access control và retention.
- [ ] Findings có evidence, confidence, impact, owner, due date và replay acceptance.
- [ ] Sponsor biết giới hạn kiểm thử: tài sản/ports/time/sensors không nằm trong phạm vi.
- [ ] Purple-team replay được thực hiện theo approval mới hoặc RoE vẫn còn hiệu lực.
- [ ] Mọi temporary exceptions/artefacts được đóng/xóa đúng quy trình.

**Ghi nhớ:** **Reconnaissance có phê duyệt là một bài kiểm tra kỹ thuật và kỷ luật vận hành**, không phải một cuộc quét không giới hạn. Giá trị nằm ở **scope chính xác, quyền hợp lệ, active probes có giới hạn, stop controls, ghi lại ground truth, đối chiếu với sensor/SIEM/SOC, bảo vệ dữ liệu và remediation có thể kiểm chứng**. Một hostname có CNAME tới CDN, một IP mở cổng hay một certificate SAN chỉ là **tín hiệu**, chưa tự chứng minh lỗ hổng hoặc trách nhiệm của chủ thể. Nếu thiếu authorization hoặc điều kiện an toàn, **dừng và quay về thiết kế lab/synthetic test** là kết quả đúng.
