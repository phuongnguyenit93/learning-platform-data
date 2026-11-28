# Chặn kết nối trực tiếp ra Internet: Thiết kế egress bắt buộc qua điểm kiểm soát

## 1. Vấn đề cần giải quyết

Trong một hệ thống doanh nghiệp, **egress** là lưu lượng đi từ một thiết bị, máy chủ, workload hoặc mạng được quản lý tới một đích khác, đặc biệt là Internet hay dịch vụ bên ngoài ranh giới tin cậy. Nhiều tổ chức chỉ chú trọng **inbound firewall** — ai có thể truy cập ứng dụng từ bên ngoài — nhưng bỏ qua câu hỏi quan trọng không kém: **ứng dụng nội bộ được phép kết nối ra ngoài tới đâu, bằng đường nào, với mục đích gì và ai có thể chứng minh điều đó?**

Hãy xét một máy chủ chứa dữ liệu tài chính. Dịch vụ chính của nó chỉ cần gọi API thanh toán qua một cổng proxy đã được phê duyệt. Nếu máy chủ vẫn có thể mở kết nối HTTPS trực tiếp tới **bất kỳ IP công cộng nào**, các cơ chế giám sát tại proxy có thể không thấy luồng đó. Một tiến trình lỗi, một thư viện phụ thuộc bị chiếm hoặc kẻ có quyền chạy mã trên máy có thể tạo kênh truyền dữ liệu ngoài đường đi đã định.

**Chặn kết nối trực tiếp ra Internet** không có nghĩa “cắt Internet với mọi thiết bị”. Mục tiêu là bảo đảm **mọi kết nối outbound thuộc phạm vi quản lý đều phải đi qua những tuyến và điểm thực thi được phê duyệt**; chỉ những đích, giao thức, danh tính và mục đích thực sự cần mới được cấp phép.

Trong chương **Kiểm soát egress và chống thất thoát dữ liệu**, thuộc học phần **SECURITY_NETWORK_SECURITY**, nội dung này kết hợp **phân đoạn, firewall, proxy, DNS security, IDS/IPS, VPN, xác thực kết nối, quan sát lưu lượng và hạ tầng cloud**. Egress control làm giảm cơ hội tạo kênh truyền không được phép, hỗ trợ ngăn thất thoát dữ liệu (*Data Loss Prevention — DLP*), nhưng **không tự phân loại nội dung hoặc chứng minh dữ liệu đã được bảo vệ hoàn toàn**.

### 1.1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **direct Internet access**, **approved proxy/gateway access**, **private service access** và **internal east–west traffic**.
2. Thiết kế mô hình **default-deny egress + allowlist có chủ đích + bắt buộc dùng proxy/egress gateway** theo lớp mạng và workload.
3. Giải thích ranh giới giữa **routing, NAT, firewall, DNS policy, explicit proxy, TLS inspection, DLP, IAM và application authorization**.
4. Áp dụng tư duy egress control cho **máy chủ, endpoint/VPN, cloud VPC/VNet và Kubernetes Pods** mà không nhầm các cơ chế thực thi.
5. Nhận diện các đường tránh kiểm soát do **IPv6, DNS thay thế/DoH, QUIC/UDP, alternate gateway, hostNetwork, secondary interface, direct public IP và tunnel/proxy khác**.
6. Lập ma trận **kết nối hợp lệ/bị chặn**, thực hiện kiểm thử âm tính có quyền và phân biệt lỗi DNS, route, firewall, proxy, TLS và ứng dụng.
7. Thu thập bằng chứng egress, gắn với danh tính workload theo thời điểm, theo dõi hiệu quả và xây quy trình ngoại lệ/rollback.

## 2. “Trực tiếp ra Internet” nghĩa chính xác là gì?

### 2.1. Phân loại đường kết nối

| Đường đi | Ví dụ | Có phải direct Internet? | Cách quản lý |
| --- | --- | --- | --- |
| **Direct public destination** | Server → public IP TCP/443 | **Có**, nếu không qua điểm kiểm soát bắt buộc | Chặn tại workload/subnet/firewall; chỉ cho lối được duyệt |
| **Explicit HTTP(S) proxy** | Server → proxy nội bộ → trang đối tác | **Không từ góc nhìn server**, nhưng proxy vẫn egress ra ngoài | Bảo vệ proxy và áp policy đích/identity tại proxy |
| **Egress firewall/gateway** | Pod → gateway kiểm soát → Internet | Qua điểm kiểm soát tập trung | Áp allow rules tại gateway, khóa đường thay thế |
| **Cloud NAT gateway** | Private VM → NAT → Internet | Vẫn là Internet egress; NAT không tự là policy lọc đủ sâu | Firewall/route policy trước và sau NAT theo dịch vụ |
| **Private endpoint** | Workload → dịch vụ cloud qua private connectivity | Thường **không qua public Internet path** theo kiến trúc tương ứng | IAM/resource policy, routes, DNS, SG/NSG vẫn cần |
| **East–west nội bộ** | Pod A → Pod B trong cluster | Không phải public Internet, nhưng vẫn có rủi ro | Segmentation, workload identity, mTLS, app authorization |
| **Outbound VPN/tunnel** | Máy nội bộ → điểm VPN bên ngoài | Có thể là **kênh egress ra Internet** nếu đích ngoài | Chỉ cho dịch vụ tunnel được duyệt, kiểm tra phạm vi |
| **SaaS qua browser/SWG** | User → Secure Web Gateway → SaaS | Egress được trung gian kiểm soát | SSO, app/tenant policy, DLP và giám sát thích hợp |

**NAT không đồng nghĩa firewall hoặc DLP.** Source NAT (SNAT) thay địa chỉ/cổng nguồn để cho nhiều workload ra ngoài qua một địa chỉ, nhưng nó không tự quyết định website nào được phép hay dữ liệu nào được phép tải lên.

Tương tự, **private subnet** không bảo đảm không có Internet egress. Một máy không có public IP vẫn có thể đi qua NAT gateway, internet egress proxy, VPN hoặc dịch vụ trung gian.

### 2.2. Ba câu hỏi cần trả lời

1. **Có đường đi không?** Route, default gateway, VPC peering, VPN, NAT, proxy hoặc overlay tạo reachability nào?
2. **Có được phép không?** Quy tắc firewall, SG/NSG, Kubernetes NetworkPolicy, proxy ACL, IAM hoặc ứng dụng nào thực thi quyền?
3. **Có thể quan sát và kiểm chứng không?** Bằng chứng từ flow, proxy, DNS, application, cloud audit và negative test nào xác nhận đúng hành vi?

Một sơ đồ có proxy ở giữa **chưa đủ** nếu máy chủ vẫn có route và firewall rule cho TCP/443 ra bất kỳ IP nào. **Đường đi thực của traffic** mới quyết định kiểm soát có hiệu lực.

## 3. Mô hình kiến trúc: Không cho egress trực tiếp

### 3.1. Trước khi siết egress

~~~mermaid
flowchart LR
    subgraph PRIVATE["Private application network"]
      APP["Application server"]
      DB["Database"]
    end
    APP -->|"Bất kỳ TCP/443 nếu không bị chặn"| NAT["Cloud/on-prem NAT"]
    NAT --> NET["Internet destinations"]
    APP -->|"Có thể trực tiếp truy cập"| DB
    APP -. "Không đi qua proxy" .-> PROXY["Approved proxy bị bỏ qua"]
~~~

Trong mô hình này, **proxy tồn tại** nhưng không được bắt buộc sử dụng. Ứng dụng có thể chọn tự mở socket tới public IP và đi theo default route. Nếu quy trình DLP/giám sát chỉ nằm ở proxy, luồng trực tiếp có thể nằm ngoài vùng quan sát.

### 3.2. Sau khi có điểm kiểm soát bắt buộc

~~~mermaid
flowchart LR
    APP["Private workload / server"] -->|"TCP đến approved proxy"| P["Explicit proxy / egress gateway"]
    APP -. "DENY direct public IP" .-> FW["Default-deny egress firewall"]
    P -->|"Allowed destinations/protocols"| NET["Internet services"]
    P -. "Deny unapproved destination" .-> X["Other public destinations"]
    DNS["Controlled DNS resolver"] <--> APP
    ID["Identity / policy context"] -. "Decision" .-> P
    LOG["Flow + proxy + DNS logs"] -. "Observability" .-> FW
    P -. "Proxy events" .-> LOG
~~~

Các thành phần có thể nằm ở nhiều nơi: firewall ở host, SG/NSG, VPC firewall, Kubernetes CNI, network gateway hoặc SWG. **Đây là thiết kế logic, không phải cấu hình sẵn của AWS/Azure/GCP hay một CNI cụ thể**.

### 3.3. Ba trụ cột

- **Path control:** workload không thể tự chọn một lối khác đi Internet ngoài kiến trúc.
- **Destination/policy control:** tại điểm ra ngoài, chỉ đích, giao thức, identity và mục đích được duyệt mới có quyền.
- **Observation and accountability:** có thể quy một flow về workload/thiết bị, policy version, thời điểm và kết quả mà không thu thập dữ liệu nhạy cảm quá mức.

Nếu chỉ có path control mà proxy tự cho **CONNECT tới mọi địa chỉ/cổng**, quyền egress vẫn có thể quá rộng. Nếu chỉ có proxy rules mà workload có **direct route** khác, chính sách cũng không khép kín.

## 4. Bắt đầu từ dữ liệu và nhu cầu nghiệp vụ

### 4.1. Lập dependency inventory

Trước khi bật default-deny, cần biết **dịch vụ nào thực sự cần outbound**:

| Workload | Kết nối cần thiết | Đích/phạm vi | Lý do |
| --- | --- | --- | --- |
| **Payment API** | HTTPS tới nhà cung cấp thanh toán | API hostname được duyệt | Giao dịch thanh toán |
| **Build runner** | Package/artifact repositories | Repo nội bộ hoặc các nguồn đã duyệt | CI/CD dependencies |
| **App server** | NTP hoặc đồng bộ thời gian theo thiết kế | Time source được kiểm soát | Đồng bộ clock/TLS |
| **Endpoint** | OS/EDR updates | Update proxy hoặc dịch vụ vendor phù hợp | Patch/endpoint health |
| **Service mesh workloads** | CA/certificate renewal và telemetry | Private PKI/observability services | Hoạt động mTLS |
| **Batch exporter** | Object storage private endpoint | Storage account/bucket được cấp | Xuất báo cáo theo chính sách |
| **DNS clients** | Resolver được chỉ định | CoreDNS/enterprise resolver | Name resolution |

Đừng mở **“Internet TCP/443 cho mọi app”** chỉ vì nhiều dependencies dùng HTTPS. Bề mặt quyền cần thể hiện **workload nào → đích nào → lý do gì → owner nào → trong bao lâu**.

### 4.2. Mẫu bảng yêu cầu egress

~~~text
Source identity:
  cluster/namespace/workload OR server group OR managed endpoint

Destination:
  named application / FQDN / approved IP range / private endpoint

Protocol and port:
  HTTPS TCP/443 (example)

Business purpose:
  fetch payment transaction status

Decision:
  permitted only through designated proxy

Owner and approval:
  team + change record + review deadline

Verification:
  permitted request succeeds
  direct public IP connection is denied
  other destination is denied

Logging:
  policy_id, workload identity, destination, decision, time
~~~

Các trường chỉ là **mẫu quản trị**, không phải policy file có thể apply cho cloud nào. Nếu chưa có owner hoặc không biết mục đích kết nối, nên điều tra thay vì cấp ngoại lệ vĩnh viễn.

### 4.3. Phân loại mức nhạy cảm

Một máy chủ dữ liệu tài chính có thể được yêu cầu **không có Internet egress** ngoài vài đích, còn một máy xây dựng phần mềm có thể cần kết nối tới nhiều repository nhưng phải qua artifact mirror/proxy. Các policy không nên đồng nhất:

- **Highly restricted:** database, secrets, regulated data, management plane — egress rất hạn chế.
- **Service-specific:** web/API server — chỉ dependency đã phê duyệt.
- **Controlled developer/build:** repositories, scanning/updates có nguồn tin cậy, có audit.
- **Managed user endpoint:** web browsing được qua SWG/proxy và device posture.
- **Guest/BYOD:** chính sách tách riêng khỏi enterprise workloads.

**Data classification và least privilege** phải quyết định chính sách; số cổng mở hoặc có NAT không phải thước đo đủ của mức an toàn.

## 5. Default-deny egress và “chỉ mở lối được duyệt”

### 5.1. Nguyên tắc

Đối với một vùng nguồn được bảo vệ, thiết kế egress có thể theo thứ tự ý định:

~~~text
ALLOW source workloads -> controlled DNS resolver
ALLOW source workloads -> designated proxy/egress gateway
ALLOW source workloads -> necessary private dependencies
ALLOW narrowly scoped operational exceptions
DENY  source workloads -> all other destinations

AT PROXY/GATEWAY:
  AUTHENTICATE source identity if supported
  ENFORCE destination/protocol/port/tenant policy
  LOG decision and errors
  DENY by default
~~~

Đây là **ma trận ý định, không phải quy tắc cú pháp của một firewall cụ thể**. SG/NACL/NSG, Linux firewall, CNI NetworkPolicy và proxy ACL có **khác biệt về stateful/stateless, thứ tự rules, implicit deny, phạm vi áp dụng, IPv6 và policy evaluation**.

### 5.2. Phải kiểm soát cả địa chỉ nguồn và đường về

Một kết nối được phép phải biết:

- **Nguồn:** app workload, subnet, service account/network identity hoặc host nào?
- **Đích:** proxy/gateway nào (địa chỉ hoặc service identity) và cổng nào?
- **Hướng:** egress từ workload, ingress vào proxy, egress từ proxy, ingress vào đích.
- **Return traffic:** firewall stateful cho phép established return hay stateless phải có rule chiều ngược?
- **Đường đi:** qua default route, NAT, egress gateway, proxy hay private endpoint nào?
- **Tính nhất quán:** IPv4, IPv6, các NICs, hostNetwork, overlay/secondary networks có nằm trong phạm vi không?

Một firewall cho phép app → proxy nhưng proxy không thể truy cập DNS/Internet có thể làm ứng dụng lỗi. Ngược lại, cho phép app → Internet nhằm “chữa lỗi proxy” có thể phá vỡ mục tiêu chặn trực tiếp.

### 5.3. Điểm thực thi không nhìn thấy luồng thì không chặn được

Nếu một VM có **hai NICs**, một Pod có **secondary interface** hoặc một laptop còn **split tunnel/alternate default route**, lưu lượng có thể không đi qua firewall trung tâm bạn đang cấu hình.

**Rule chỉ có ý nghĩa trên datapath mà packet thực sự đi qua.** Cần inventory routing, policy routing, NAT, VPN, IPv6, cloud network attachments và những đường bypass khác trước khi tuyên bố “mọi Internet egress đã bị chặn”.

## 6. Phân biệt route, NAT và firewall trong bài toán outbound

### 6.1. Route xác định lối đi, không tự là quyền

Một route như **0.0.0.0/0 → default gateway/NAT** cho biết đích mặc định của traffic IPv4 không có route cụ thể hơn. Nó **không tự chứng minh** firewall đang cho phép hoặc chặn, và không xác minh hostname/ứng dụng.

Để chặn direct Internet có thể kết hợp:

- Không tạo direct internet route cho vùng workload không cần Internet.
- Định tuyến các traffic được phép tới **proxy/gateway** đúng chỗ.
- Áp firewall deny ở **host/NIC/subnet/egress boundary**.
- Ràng buộc source chỉ được gọi proxy, không gọi các external destinations trực tiếp.
- Đảm bảo những nguồn đặc thù như Kubernetes host network hoặc transit/peering không có đường đi khác.

**Không xóa default route bừa bãi**: máy có thể cần route tới DNS, identity, cập nhật hoặc hệ thống điều khiển. Mạng private vẫn có thể dùng private endpoints để không phụ thuộc public Internet.

### 6.2. NAT làm ẩn nguồn gốc ở phía ngoài

Ví dụ một kết nối:

~~~text
Before source NAT:
  workload 10.50.2.17:51820 -> public service 203.0.113.40:443

After source NAT:
  gateway-public-IP:61042 -> 203.0.113.40:443
~~~

**203.0.113.40** thuộc dải IPv4 dành cho tài liệu theo RFC 5737, không phải máy chủ thật. Một NAT gateway có thể ghi tuple đã dịch nhưng **không tự biết Pod UID hoặc tiến trình tạo kết nối**. Để truy vết chính xác cần **original tuple, translated tuple, event time, source identity và điểm quan sát**.

Trong nhiều nền tảng, **NAT gateway không phải web filtering proxy**. Nó có thể cho phép TCP/443 tới mọi IP mà không đọc HTTP Host hay token của user. Muốn giới hạn đích, cần firewall/proxy/policy phù hợp tại nơi có đủ ngữ cảnh.

### 6.3. Security group, NSG và network ACL không có cùng semantics

| Lớp | Khả năng thường dùng | Điều cần kiểm chứng |
| --- | --- | --- |
| **Host firewall** | Chặn kết nối outbound theo IP, port, đôi khi process/user | Quản trị host, quyền sửa, IPv6, VPN interfaces |
| **Cloud security group** | Lọc traffic ở NIC/instance theo rules của provider | Stateful, rule semantics, source/dest identity và implicit deny |
| **Azure NSG hoặc tương đương** | Allow/deny và priority theo platform | Default rules, statefulness, association và effective security rules |
| **Subnet network ACL** | Bộ lọc phạm vi subnet theo cloud | Stateless return path, rule priority và subnet attachments |
| **Central network firewall** | L3/L4, stateful policy, đôi khi DNS/FQDN/L7 | Bắt buộc đi qua firewall, asymmetric routes, scale |
| **Kubernetes CNI NetworkPolicy** | Pods theo selectors/peers/ports | CNI support, egress isolation, host/secondary paths |
| **Explicit proxy** | HTTP request/CONNECT destination và user policy | Chỉ có tác dụng khi client dùng proxy hoặc direct path bị chặn |

**Không sao chép rules giữa sản phẩm**. Ví dụ nhiều cloud security groups chỉ có **allow rules** với implicit deny, trong khi các firewall khác có **explicit deny/priority**. Ngoài ra, vì nhiều controls stateful, return traffic không luôn cần rule độc lập; với stateless filters có thể cần.

### 6.4. Tránh nhầm outbound IP với đích thực tế

Một firewall rule kiểu **allow destination=proxy-IP TCP/3128** chỉ cho workload kết nối tới proxy. Nó không tự kiểm soát **proxy mở kết nối tới đích nào**. Cần policy riêng cho proxy → Internet.

Ngược lại, một proxy allowlist chính xác nhưng tất cả workloads cũng được **allow 0.0.0.0/0 TCP/443** sẽ không ngăn các client không tuân thủ cấu hình proxy dùng direct HTTPS.

### 6.5. Stateful flows, connection tracking và thay đổi policy

Khi thay rules, kết nối đã được thiết lập có thể được xử lý khác kết nối mới do **stateful firewall/conntrack behavior**. Cần kiểm tra:

1. Quy tắc mới có chặn các **new outbound connections** không?
2. **Existing connections** có được tiếp tục đến khi đóng/timeout không?
3. Thay firewall có tạo state bất đối xứng giữa các zones/nodes không?
4. Một ứng dụng có retry hoặc circuit breaker gây lưu lượng tăng sau chặn không?

**Một negative test mở socket mới** chưa chứng minh mọi kết nối cũ đã được ngắt. Khi incident response yêu cầu containment tức thì, cần runbook phù hợp để xử lý state và phiên mà không gây downtime ngoài dự kiến.

## 7. Explicit proxy và nguyên tắc “proxy bắt buộc”

### 7.1. Explicit web proxy là gì?

**Explicit proxy** là dịch vụ mà client được cấu hình gửi request đến, thay vì tự kết nối trực tiếp tới website đích. Với HTTP, client có thể gửi request dạng proxy. Với HTTPS, client thường yêu cầu **CONNECT** tới hostname:port rồi thiết lập TLS qua tunnel, hoặc theo cơ chế khác do proxy hỗ trợ.

~~~mermaid
sequenceDiagram
    participant C as Internal client
    participant FW as Egress firewall
    participant P as Authenticated proxy
    participant S as Approved remote service
    C->>FW: TCP tới proxy:3128
    FW->>P: Allowed connection
    C->>P: CONNECT api.partner.example:443
    P->>P: Authenticate source + enforce destination policy
    P-->>C: Tunnel permitted
    P->>S: Open approved outbound connection
    C-->>S: TLS protected application traffic qua proxy
    Note over C,S: Payload vẫn được mã hóa nếu proxy không TLS-inspect
~~~

**Cổng 3128 chỉ là ví dụ** hay dùng với proxy; không có cổng tiêu chuẩn bắt buộc cho mọi proxy. Sơ đồ là logic và bỏ qua nhiều chi tiết TCP/TLS. Nếu gateway không giải mã TLS, nó có thể kiểm soát **đích CONNECT và metadata**, nhưng không tự kiểm tra mọi HTTP request/body bên trong tunnel.

### 7.2. Tại sao cấu hình biến môi trường chưa đủ?

Ứng dụng có thể dùng:

~~~text
HTTPS_PROXY=http://proxy.internal.example:3128
HTTP_PROXY=http://proxy.internal.example:3128
NO_PROXY=localhost,127.0.0.1,.svc.cluster.local
~~~

Đây là **ví dụ cách client có thể chọn proxy**, không phải security enforcement. Quy tắc thực tế của từng thư viện có thể khác về chữ hoa/thường, tên biến và cách dùng **NO_PROXY**. Một ứng dụng có thể **bỏ qua proxy settings**, dùng socket trực tiếp hoặc có proxy riêng.

**Bắt buộc dùng proxy** nghĩa là **network firewall chặn đường trực tiếp**, không chỉ gửi một hướng dẫn “hãy dùng proxy” tới developers. NO_PROXY cần được review theo dependencies nội bộ để tránh đưa traffic riêng tư qua Internet proxy hoặc bỏ lọt external domains.

### 7.3. Policy cho proxy

Proxy có thể có các yêu cầu:

- Xác thực service/client hoặc chỉ chấp nhận nguồn mạng/identity được tin cậy.
- Deny mặc định với **CONNECT destinations không nằm trong allowlist**.
- Hạn chế **destination port/protocol**, ngăn yêu cầu tunnel tới các cổng không có nhu cầu nghiệp vụ.
- Bảo vệ khỏi việc proxy trở thành **open relay** được mọi Internet client dùng.
- Phân biệt rule cho **workload A, B, C** thay vì tất cả ứng dụng cùng một quyền.
- Log **normalized destination, decision, source identity, bytes, timestamp, policy version** theo phạm vi được phê duyệt.
- Giới hạn request/connection/concurrency, timeout, DNS resolution và fail behavior.
- Tích hợp DLP/URL filtering khi cần và khi proxy có **visibility** thích hợp.

**Proxy authentication không tự là authorization theo dữ liệu**. Một ứng dụng đã được phép gửi lên API đối tác vẫn có thể xuất quá nhiều thông tin; cần app-level policy, data classification và kiểm soát nội dung theo use case.

### 7.4. TLS qua proxy và giới hạn inspect

| Cách proxy xử lý HTTPS | Điều có thể biết | Điểm mù / trách nhiệm |
| --- | --- | --- |
| **CONNECT tunnel không decrypt** | CONNECT hostname/port, client, thời điểm, bytes | Không tự thấy HTTP URL/body sau TLS handshake |
| **TLS termination + inspection được phê duyệt** | Một số HTTP headers/routes/body tùy implementation | Quyền riêng tư, secrets, cert validation và ứng dụng pinning |
| **Application API proxy** | Request context/token/route cụ thể | Không bảo vệ TCP traffic không qua proxy |
| **Egress gateway L4** | IP/port/protocol, flow verdict | Thường không xác định HTTP content hoặc user |

TLS inspection là **thay đổi trust boundary lớn**: gateway có thể đọc plaintext của kết nối, cần cơ sở pháp lý/quy định, quản lý CA/private keys, kiểm soát dữ liệu và xử lý các ứng dụng không tương thích. **Không bắt buộc giải mã mọi traffic** để đạt mục tiêu **chặn đường Internet trực tiếp**.

### 7.5. Proxy có thể bị lạm dụng thành lối ra mới

Nếu proxy không giới hạn **CONNECT target** hoặc cho phép proxy chaining không kiểm soát, việc client buộc đi qua proxy không bảo đảm destination governance. Cần:

- Policy rõ ràng về đích/protocol/port và loại tài khoản được phép.
- Giới hạn proxy-to-proxy, VPN/tunnel services theo yêu cầu doanh nghiệp.
- Chặn **direct origin destinations** từ client, không chặn proxy một cách mù quáng.
- Giám sát đích mới, failures/denials và kết nối kéo dài bất thường.
- Có review exceptions thay vì một rule “allow all CONNECT” vĩnh viễn.

## 8. DNS trong kiến trúc egress: Có ích nhưng không đủ

### 8.1. DNS resolver được kiểm soát

Một mô hình thường dùng:

~~~text
Applications / endpoints
  -> approved enterprise DNS resolvers
  -> DNS filtering / logging / policy checks
  -> authorized recursive/upstream resolution

Applications
  -> approved proxy/gateway
  -> selected external destination
~~~

Doanh nghiệp có thể dùng DNS để phát hiện **domain mới, malicious domains, NXDOMAIN spikes và sai cấu hình**. Tuy vậy DNS policy không phải network deny tuyệt đối:

- Ứng dụng có thể kết nối **trực tiếp tới IP** mà không tra DNS.
- DNS cache có thể phục vụ kết quả mà resolver không thấy query mới.
- Một domain có thể dùng **CDN/đa địa chỉ IP**, TTL ngắn và địa chỉ chia sẻ.
- Một IP công cộng có thể phục vụ nhiều hostnames khác nhau; chỉ allow IP không đủ biết app được phép.
- DNS chỉ trả lời tên, không chứng minh endpoint TLS có danh tính hợp lệ.

**Chặn DNS truy vấn ra ngoài** bổ sung cho egress control; **chặn kết nối IP trực tiếp** vẫn phải do network enforcement.

### 8.2. DoH, DoT và resolver thay thế

Một workload có thể sử dụng **DNS over HTTPS (DoH)** hoặc **DNS over TLS (DoT)**, hoặc library tự định nghĩa resolver. Khi đó enterprise resolver không mặc nhiên thấy những tên được hỏi.

Biện pháp ở mức thiết kế:

- Chỉ cho workloads gọi **các resolver được duyệt**.
- Kiểm soát outbound TCP/UDP tới external resolvers và những dịch vụ DNS thay thế theo policy.
- Buộc HTTP(S) đi qua proxy có destination policy phù hợp.
- Giám sát **network flows** ngoài DNS logs để tránh điểm mù.
- Đối với endpoints managed, dùng device policy/agent phù hợp nếu cần khóa alternate DNS.

**Không suy ra mọi HTTPS tới port 443 là DoH**. Port 443 phục vụ nhiều loại ứng dụng; phát hiện cần context, destination và bằng chứng kỹ thuật phù hợp.

### 8.3. FQDN-based rules và DNS-to-IP mapping

Firewall/CNI/secure proxy có thể hỗ trợ allow FQDN hoặc dynamic DNS objects. Nhưng một chính sách **allow api.partner.example** phải xem:

1. Resolver/địa chỉ nào là nguồn dữ liệu DNS đáng tin?
2. Rule theo FQDN dựa trên **DNS answer/IP mapping, TLS SNI, HTTP Host** hay một cơ chế khác?
3. TTL, cache và khi IP thay đổi được xử lý ra sao?
4. Nếu IP dùng chung cho nhiều domains thì policy giới hạn đúng hostname không?
5. Có kiểm soát **IPv6 AAAA** và direct-IP connections không?
6. SNI có thể bị ẩn/không hiện rõ trong một số TLS deployments (ví dụ ECH); product xử lý thế nào?

**FQDN allowlist không tự xác thực server.** Client/gateway còn cần TLS certificate chain, hostname verification và authorization theo app nếu có.

### 8.4. DNS tunneling và dữ liệu thất thoát

DNS có thể bị lạm dụng để chuyển một lượng thông tin trong tên truy vấn hoặc đáp án, nhưng **không thể kết luận thất thoát** chỉ từ việc query nhiều hoặc có subdomain dài. Các dịch vụ telemetry, cache busting hoặc tracking hợp lệ cũng có thể sinh pattern như vậy.

Để giảm rủi ro:

- Giới hạn resolver path theo policy.
- Giám sát bất thường trên những workloads **không cần dynamic DNS**.
- Kết hợp query rate, record types, NXDOMAIN ratio, độ dài tên và baseline.
- Bảo vệ log vì QNAME có thể chứa dữ liệu nhạy cảm.
- Kết hợp egress network controls; không kỳ vọng DNS filter thấy mọi kênh truyền.

### 8.5. DNS cần được allow đúng trong Kubernetes

Khi default-deny egress Pods, DNS query tới **CoreDNS Service, NodeLocal DNSCache hoặc resolver khác** có thể bị chặn nếu không có allow phù hợp. Nguồn resolver và datapath có thể khác nhau, đặc biệt với NodeLocal DNSCache/hostNetwork và CNI mode.

**Không copy một rule mở UDP/53 cho mọi IP** rồi coi DNS đã được bảo vệ. Cần biết đúng DNS resolver, protocol **UDP và TCP** theo nhu cầu, các hoạt động cache và cách plugin thực thi NetworkPolicy.

## 9. IPv4, IPv6 và những đường Internet không đi qua proxy

### 9.1. Dual-stack phải được kiểm soát độc lập

Một network policy chỉ chặn IPv4 destinations **0.0.0.0/0** không mặc nhiên chặn IPv6 **::/0**. Trong hệ thống dual-stack, client có thể có:

- IPv4 default route qua một gateway được kiểm soát.
- IPv6 global/unicast route qua router hoặc nhà mạng khác.
- Nhiều network interfaces, cả physical và VPN.
- DNS A/AAAA records với các đường đi riêng.

Do đó, phải có **IPv4/IPv6 route and firewall inventory**, xác định proxy có hỗ trợ cả hai họ địa chỉ và dùng negative tests cho cả hai nếu hệ thống hỗ trợ.

### 9.2. Không hiểu “khóa IPv6” là xóa toàn bộ IPv6

Tắt IPv6 chỉ để tránh xây rule có thể gây lỗi hệ thống hoặc bỏ qua nhu cầu dùng IPv6 hợp lệ. Cách đúng là:

1. Xác định nơi IPv6 được bật, IP scopes và routes.
2. Áp egress allow/deny phù hợp giống mức bảo vệ IPv4.
3. Kiểm tra proxy/egress gateway có hỗ trợ IPv6 và logging không.
4. Nếu quyết định không dùng IPv6 ở một phân đoạn, áp chính sách hạ tầng được phê duyệt, kiểm chứng không ảnh hưởng dependencies.

**Đừng dựa vào mặc định “mạng này chỉ dùng IPv4”** khi endpoint OS, cloud VPC hoặc Kubernetes cluster có thể hỗ trợ IPv6.

### 9.3. QUIC/HTTP/3 và UDP

Nhiều thiết kế chỉ chặn direct TCP/80,443 nhưng quên **UDP/443** (có thể dùng cho QUIC/HTTP/3) hoặc các UDP outbound protocols khác. Nếu chính sách chỉ cho outbound qua explicit HTTP proxy/TCP, hãy xác định **những giao thức UDP nào cần chặn hoặc xử lý qua gateway hỗ trợ**.

Tuy nhiên **UDP/443 không đồng nghĩa luôn là QUIC**, và chặn UDP/443 có thể làm một số ứng dụng chuyển sang TCP hoặc giảm hiệu năng. Cần ghi rõ tác động và test của những ứng dụng hợp lệ, không suy đoán.

### 9.4. Các loại tunnel, alternate proxy và overlay

Người dùng hoặc phần mềm được cấp quyền hệ điều hành có thể có:

- VPN client/agent khác tạo interface hoặc default route.
- SOCKS/HTTP proxy ngoài danh sách được duyệt.
- Kênh remote support, remote desktop, SSH tunnel hoặc web relay.
- Overlay network với egress ở một node khác.
- Cloud private peering/transit đường tới một egress gateway khác.

Đây là **những đường cần inventory và kiểm soát**, không phải danh sách kỹ thuật để tìm cách vượt policy. Một tổ chức cần chặn những tunnel không được phê duyệt theo **destination, protocol, identity, endpoint posture và network enforcement**, đồng thời cung cấp những phương thức truy cập hợp lệ.

### 9.5. Không dùng “port 443” làm bằng chứng HTTPS hợp lệ

TCP/443 là một port phổ biến, không chứng minh:

- Destination thuộc đối tác được phê duyệt.
- TLS peer identity đã được xác minh.
- Traffic đúng là HTTP(S) và theo chính sách.
- Dữ liệu được gửi ra có được phép chia sẻ.

**Port allowlist là một lớp hẹp**, phải bổ sung proxy/gateway destination controls, trust validation và dữ liệu application business context khi cần.

## 10. Kiểm soát egress trong cloud VPC/VNet

### 10.1. Private subnet không đủ

Trong cloud, VM hoặc workload có thể không có public IP nhưng vẫn được SNAT qua **NAT gateway/NAT instance** để truy cập Internet. Một VPC/VNet có route tới Internet gateway, transit network, private link hoặc egress proxy tùy topology.

~~~mermaid
flowchart TB
    subgraph VPC["Cloud VPC / VNet"]
      APP["Private application subnet"]
      PROXY["Controlled egress proxy"]
      NAT["NAT or public egress"]
      FW["Firewall / egress policy"]
      APP -->|"Approved destinations only"| PROXY
      PROXY --> FW
      FW --> NAT
    end
    NAT --> PUBLIC["Internet services"]
    APP -. "DENY direct path to NAT/public" .-> NAT
    APP -->|"Private route, scoped"| EP["Cloud private service endpoint"]
    IAM["IAM/resource policy"] -. "Authorize" .-> EP
~~~

Lưu ý **NAT không phải lúc nào cũng đứng sau firewall theo đúng thứ tự này**; topology thực phụ thuộc cloud và routing. Sơ đồ là **mô hình logic**, mục tiêu là mọi luồng Internet của application subnet không thể bỏ qua điểm egress enforcement.

### 10.2. AWS: những lớp cần phân biệt

Với môi trường AWS, kiểm soát có thể dùng kết hợp:

- Route tables, internet gateway, NAT gateway.
- **Security Groups** cho network interfaces/instances với mô hình allow và tính stateful.
- Network ACLs tại subnet và network firewall/inspection endpoints theo thiết kế.
- VPC endpoints/PrivateLink hoặc gateway endpoints cho một số dịch vụ cloud.
- Proxy/SWG tự quản lý hoặc dịch vụ tương đương.
- VPC Flow Logs, Route 53 Resolver logging và CloudTrail cho các lớp quan sát khác nhau.

**Security Group không tự làm URL/category filtering**; NAT gateway không tự là DLP. Với gateway endpoint như S3, **IAM/bucket policy, endpoint policy và những điều kiện được hỗ trợ** cần được thiết kế riêng để hạn chế truy cập đúng resource.

### 10.3. Azure: những lớp cần phân biệt

Trong Azure, bài toán có thể dùng **UDR, NAT Gateway, NSG, Azure Firewall, proxy và Private Endpoints**. Cần xem:

- Effective routes và effective security rules.
- Default outbound behavior theo kiểu workload/subnet và phiên bản nền tảng.
- Firewall application rules/network rules, DNS proxy/FQDN handling nếu sử dụng.
- Private DNS zone/Private Endpoint có trỏ đúng service không.
- Flow logs, firewall logs và Azure activity/audit cho thay đổi control plane.

**Azure NAT Gateway** phục vụ outbound connectivity/SNAT, không tự thay toàn bộ policy và DLP. Một NSG outbound rule có thể chặn ở lớp network nhưng không tự biết business meaning của HTTP payload.

### 10.4. Google Cloud: những lớp cần phân biệt

Trong Google Cloud, các khái niệm thường liên quan gồm **VPC firewall rules/policies, Cloud NAT, Cloud Router/route configuration, Private Google Access/Private Service Connect** và proxy/egress gateway phù hợp.

**Cloud NAT** cung cấp network address translation, không mặc nhiên kiểm soát URL hoặc lọc dữ liệu upload. Sự có mặt của private connectivity chưa chứng minh resource IAM đã siết quyền. Cần xem firewall effective rules, VPC Flow Logs, DNS logs và cloud audit theo thiết kế sản phẩm.

### 10.5. Multi-account, multi-region và transit

Khi nhiều VPC/VNet hoặc accounts/projects được kết nối:

- Một workload có thể egress qua **central hub** hoặc shared network.
- Peering/transit có thể tạo route tới gateway không thuộc đội ứng dụng.
- Region dự phòng có thể chưa có cùng firewall/proxy policy.
- Một serverless/managed workload có egress path khác VM cùng dự án.
- Dịch vụ private endpoints có resource policies và DNS/routing riêng.

**Không chỉ kiểm tra một subnet route table** rồi kết luận mọi workload trong account/region đã bị giới hạn. Cần kiểm kê đường đi thực theo từng loại tài nguyên và runtime.

### 10.6. Resource IAM và data path

Cloud resource policy là một lớp rất quan trọng với DLP: có thể hạn chế **workload identity nào được ghi object vào bucket, gọi API nào và gửi dữ liệu tới account/project nào**.

Nhưng **IAM allow** không thay network egress kiểm soát tới những public APIs khác; ngược lại chặn Internet không tự ngăn dữ liệu bị sao chép vào **một resource cloud có private endpoint nhưng quyền quá rộng**.

**Phòng thủ gồm network path + cloud resource authorization + audit dữ liệu.**

## 11. Kubernetes: Default-deny egress không phải “Internet-only deny”

### 11.1. NetworkPolicy và phạm vi

Kubernetes **networking.k8s.io/v1 NetworkPolicy** cho phép chọn Pods và quy tắc ingress/egress theo selectors, CIDR và ports. Khi Pods bị egress-isolated, những luồng chỉ được phép nếu đáp ứng allow policies tương ứng theo API semantics và CNI thực thi.

**Default deny egress** trong namespace thường chặn **tất cả egress thuộc phạm vi áp dụng**, bao gồm **DNS, service-to-service, Kubernetes API, private database và Internet** — không chỉ Internet.

Ví dụ áp dụng trên **namespace egress-lab** do bạn quản trị:

~~~yaml
# Ví dụ giáo dục: không áp lên production chưa phân tích dependencies.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-egress
  namespace: egress-lab
spec:
  podSelector: {}
  policyTypes:
    - Egress
~~~

Manifest này chỉ có hiệu lực nếu CNI hỗ trợ NetworkPolicy. Nó **không phải global deny toàn cluster**, không tự cấm hostNetwork/node-originated traffic và không đảm bảo mọi secondary interfaces bị chặn.

### 11.2. Cho workload dùng proxy được phê duyệt

Giả sử namespace **egress-lab** có Pods gắn nhãn **app=report-worker**. Một proxy lab chạy trong namespace **security-egress-lab**, Pods gắn nhãn **app=approved-proxy**, lắng nghe TCP/3128:

~~~yaml
# Ví dụ NetworkPolicy chỉ cho report-worker tới approved proxy.
# Phải tồn tại đúng namespace/pod labels và CNI hỗ trợ trước khi thử.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: report-worker-to-proxy
  namespace: egress-lab
spec:
  podSelector:
    matchLabels:
      app: report-worker
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: security-egress-lab
          podSelector:
            matchLabels:
              app: approved-proxy
      ports:
        - protocol: TCP
          port: 3128
~~~

**Nhận xét quan trọng:**

- Hai selectors nằm trong **cùng phần tử** của danh sách **to**, do đó kết hợp theo AND. Tách thành hai phần tử có thể làm phạm vi rộng hơn.
- Rule trên chỉ mô tả **egress của report-worker tới proxy pods**. Proxy còn cần **ingress allow**, **egress control tới Internet** và chính sách đích/identity riêng.
- Một Pod không được policy này chọn **không tự bị cô lập** trừ khi có policy khác như default-deny namespace.
- Không có quy tắc về DNS ở đây; nếu client cần resolver, phải thiết kế allow đúng.
- Không chứng minh rằng direct Internet đã bị chặn nếu CNI không thực thi hoặc workload có host/secondary path khác.

### 11.3. DNS egress có nhiều kiểu thực thi

Một DNS resolver có thể là CoreDNS Pods ở namespace **kube-system**, CoreDNS Service ClusterIP hoặc NodeLocal DNSCache trên host/node IP. Policy theo selectors có thể phù hợp với một số đường đi, nhưng **service translation, hostNetwork, NodeLocal và CNI mode** có thể yêu cầu cấu hình khác.

Một mẫu **ý định**, không phải YAML có thể áp dụng chung:

~~~text
ALLOW report-worker -> approved cluster DNS resolver
  UDP/53 and TCP/53 according to actual resolver path

ALLOW report-worker -> approved proxy
  TCP/3128

DENY report-worker -> all other destinations
~~~

Thực thi và kiểm tra đúng **đường DNS đang dùng** thay vì sao chép dải IP ví dụ. Chặn nhầm DNS có thể khiến ứng dụng trông giống “mất Internet” dù proxy vẫn khỏe.

### 11.4. Egress policy theo FQDN là mở rộng

**Kubernetes NetworkPolicy chuẩn không cung cấp đầy đủ một trường FQDN allowlist phổ quát**. Những giải pháp CNI như Cilium/Calico hoặc egress gateways có thể cung cấp **CRDs, FQDN/DNS policies hoặc khả năng L7** tùy sản phẩm, phiên bản và cấu hình.

Không dùng một manifest vendor-specific như thể mọi cluster đều hỗ trợ. Khi thiết kế FQDN egress, cần kiểm tra DNS policy, caching, TTL, SNI/HTTP Host semantics, IPv6, direct-IP và **nguồn logging** của CNI.

### 11.5. Pod IP không phải danh tính bền vững

Pods có thể được reschedule, IP được tái sử dụng, còn Service VIP có thể được DNAT tới Pod endpoints. Để phân tích một flow egress qua NAT, nên liên kết:

~~~text
flow event time + cluster + node
source Pod UID + namespace + workload owner
original source IP:port
translated source IP:port (nếu có)
proxy/egress gateway identity
destination + protocol + policy verdict
~~~

Chỉ nhìn public NAT IP không đủ quy kết cho một workload. **Flow verdict FORWARDED tại một hook không chứng minh proxy hoặc application đã chấp nhận request ở tầng L7**.

### 11.6. hostNetwork, privileged Pods và secondary interfaces

Một số workloads dùng **hostNetwork**, Multus/SR-IOV hoặc networking trực tiếp qua node/secondary interface. Chúng có thể **không đi qua enforcement point** mà NetworkPolicy ở default pod network đang dùng.

Cần:

- Admission policies/RBAC giới hạn quyền tạo hostNetwork/privileged workloads.
- Inventory network attachments và interfaces của từng workload.
- Host/node firewall và cloud SG/NSG tương ứng.
- Negative tests cho data path có khả năng bỏ qua default CNI.
- Chỉ đặt label **“egress enforced”** khi có bằng chứng, không phải vì có một NetworkPolicy object.

### 11.7. Egress gateway: Vai trò trong Kubernetes

Một egress gateway có thể gán **source identity, stable egress IP hoặc central policy point** cho những Pods được chọn. Nhưng:

- Không phải mọi gateway tự có **DNS/FQDN filtering hoặc DLP**.
- Một số cung cấp SNAT, định tuyến hoặc L4 policy là chính.
- Egress gateway cần HA, capacity và certificate/identity quản lý phù hợp.
- Cần bảo đảm **workloads bị buộc qua gateway**, không có direct route khác.

**Egress gateway không đồng nghĩa proxy HTTP** và cũng không tự là giải pháp DLP hoàn chỉnh.

## 12. Máy tính người dùng, VPN và các điểm truy cập khác

### 12.1. Endpoint có thể có nhiều lối Internet

Máy tính doanh nghiệp có thể dùng:

- Mạng văn phòng.
- Wi-Fi công cộng hoặc mạng gia đình.
- VPN **full tunnel** hoặc **split tunnel**.
- Agent ZTNA/SWG.
- Network interface phụ như tethering/cellular.
- Một số ứng dụng kết nối qua proxy riêng, VPN client riêng hoặc browser networking stack.

Nếu chính sách doanh nghiệp yêu cầu **mọi web egress qua Secure Web Gateway**, chỉ cấu hình proxy trên LAN văn phòng không đủ khi máy rời mạng. Cần xác định **endpoint controls**, posture, agent routing, DNS/IPv6, firewall và hành vi khi mất kết nối.

### 12.2. Full tunnel và split tunnel

| Kiểu VPN | Đặc điểm | Câu hỏi egress |
| --- | --- | --- |
| **Full tunnel** | Phần lớn traffic của endpoint được chuyển qua VPN theo thiết kế | Gateway có lọc Internet outbound và áp cùng policies không? |
| **Split tunnel** | Chỉ một số prefixes/apps qua VPN, còn Internet traffic có thể đi trực tiếp | Đường Internet ngoài VPN có được SWG/endpoint firewall bảo vệ không? |
| **Per-app VPN/ZTNA** | Chỉ traffic đến tài nguyên/app được chọn đi qua agent/fabric | Các luồng khác có egress controls riêng hay không? |

Không có cấu hình **tuyệt đối tốt trong mọi trường hợp**. Full tunnel có thể tăng băng thông/latency cho gateway; split tunnel có thể hợp lý nếu endpoint có security controls phù hợp. Cần tách **quyền vào nội bộ** và **quyền duyệt Internet**.

### 12.3. Endpoint proxy settings không phải policy bất biến

Browser/system proxy/PAC file có thể giúp chọn lối đi, nhưng:

- Một chương trình không tuân theo PAC/system proxy vẫn có thể tạo socket trực tiếp nếu OS/network cho phép.
- PAC/NO_PROXY có thể có ngoại lệ quá rộng.
- Mất agent hoặc quyền administrator có thể làm thay đổi routing/firewall.
- Browser có thể có cấu hình DNS/proxy riêng.
- Một user dùng thiết bị ngoài quản lý có thể không chịu cùng chính sách.

**Cần một điểm thực thi mà client không thể tự ý bỏ qua trong phạm vi quyền hạn được thiết kế**, như endpoint firewall/agent được bảo vệ, access fabric hoặc network enforcement.

### 12.4. BYOD và quyền riêng tư

Đối với thiết bị cá nhân, tổ chức có thể không có quyền kiểm soát toàn bộ lưu lượng Internet. Lựa chọn hợp lý là:

- Cung cấp **browser-based application access** đã giới hạn dữ liệu.
- Tách managed corporate data khỏi traffic cá nhân.
- Có chính sách download/upload, session và DLP phù hợp với yêu cầu.
- Không thu thập toàn bộ lịch sử duyệt web cá nhân vượt nhu cầu.
- Giới hạn quyền theo app/tenant thay vì buộc mọi egress BYOD vào proxy giám sát.

Một tổ chức cần minh bạch về **phạm vi giám sát, cơ sở pháp lý, retention và quyền truy cập logs**.

## 13. Tác động của chặn direct Internet tới DLP

### 13.1. Network egress control và DLP giải quyết hai câu hỏi khác nhau

**Egress control** hỏi: **“Luồng mạng này có được mở tới đích qua đường này không?”**  
**DLP** hỏi: **“Thông tin này có được phép rời tổ chức, đến người nhận/kênh này, trong hoàn cảnh này không?”**

Ví dụ, firewall có thể chỉ cho **report-worker → approved storage gateway**, nhưng nếu ứng dụng được phép upload mọi file lên một bucket mà không kiểm tra nhãn dữ liệu và tenant, sự thất thoát dữ liệu vẫn có thể xảy ra qua đường **được phép**.

Ngược lại, DLP phân loại dữ liệu tốt nhưng client có thể đi trực tiếp tới Internet ngoài điểm DLP inspection sẽ có **coverage gap**.

### 13.2. Ba vị trí kiểm soát DLP phổ biến

| Điểm DLP | Có thể thấy/kiểm soát | Giới hạn |
| --- | --- | --- |
| **Endpoint DLP** | File/process/clipboard/upload trên thiết bị được quản lý theo product | Không phủ thiết bị unmanaged hoặc workload không cài agent |
| **Network/SWG/proxy DLP** | Traffic đi qua gateway, dữ liệu có thể inspect khi giải mã/hỗ trợ | Payload mã hóa, non-proxy traffic, app-specific protocols |
| **Cloud/SaaS/API DLP** | Dữ liệu/đối tượng lưu trong dịch vụ SaaS/cloud theo connector và permission | Không tự chặn mọi network path hoặc uploads realtime |
| **Application-level DLP** | Business object, tenant, nhãn dữ liệu, workflow | Chỉ các app được tích hợp, cần đúng app authorization |

Một chiến lược tốt có thể kết hợp theo use case. **Chặn direct Internet làm tăng khả năng traffic đi qua điểm kiểm soát**, nhưng không bảo đảm gateway nhìn thấy nội dung hoặc hiểu quyền chia sẻ nghiệp vụ.

### 13.3. TLS và giới hạn của việc kiểm tra nội dung

Nếu một proxy chỉ thấy **CONNECT destination**, dữ liệu HTTPS bên trong vẫn được mã hóa; DLP network sẽ không tự đọc body của mọi upload. Muốn nội dung inspection phải có **điểm plaintext** như:

- Gateway TLS termination/inspection được phê duyệt.
- Ứng dụng/API thực hiện kiểm tra trước khi xuất.
- Endpoint DLP ở nơi có file/content.
- SaaS security API tích hợp kiểm tra object theo khả năng.

**Không nên bật giải mã mọi kết nối chỉ để chứng minh chặn direct Internet**. TLS inspection có tác động lớn tới quyền riêng tư, certificate trust, performance, certificate pinning và bảo mật của chính gateway. Thiết kế phải tuân thủ chính sách, quy định và giới hạn của ứng dụng.

### 13.4. Dữ liệu được phép đi đúng đích vẫn có thể rò rỉ

| Kịch bản | Egress rule | Rủi ro còn lại |
| --- | --- | --- |
| App upload báo cáo tới storage chính thức | Cho phép HTTPS tới storage | Bucket/resource permissions sai hoặc nhầm tenant |
| Nhân viên gửi file qua sanctioned email | Cho mail service | Email recipient bên ngoài không được phép |
| Ứng dụng ghi log tới telemetry SaaS | Cho monitoring endpoint | Logs chứa token, PII hoặc secrets |
| Backend gọi LLM/SaaS API được duyệt | Cho vendor endpoint | Nội dung prompt/file vượt data handling policy |
| Build runner upload artifacts | Cho artifact registry | Artifact chứa credentials/keys nhúng |

Vì vậy cần **data classification, app-level policy, object/tenant authorization, redaction, retention, IAM và audit**. **Chặn Internet trực tiếp là điều kiện hỗ trợ**, không phải chứng minh DLP đã hoàn tất.

### 13.5. “Bytes out tăng” là tín hiệu, không phải kết luận exfiltration

Nhiều công việc hợp lệ như backup, software update, CDN upload và batch export có thể tạo lưu lượng lớn. Một alert nghi ngờ thất thoát nên kết hợp:

1. Workload/service owner và business schedule.
2. Đích public/provider và danh tính tài khoản nhận nếu có.
3. Chiều byte từ **đúng điểm quan sát**, tránh đếm đôi qua proxy/NAT/mesh.
4. Dữ liệu ứng dụng đã đọc/xuất và nhãn phân loại (khi có).
5. Change records, auth events, policy violations.
6. Mức chắc chắn của NAT/source attribution.

**Không kết luận “đã lấy cắp dữ liệu” từ một số byte trong flow log.** Nếu chưa biết nội dung đã truyền, cần ghi mức độ nghi vấn và bằng chứng còn thiếu.

## 14. SSRF, metadata endpoints và egress từ ứng dụng

### 14.1. Vì sao SSRF liên quan outbound control?

**Server-Side Request Forgery (SSRF)** xảy ra khi ứng dụng bị dẫn tới thực hiện request tới một đích ngoài ý định, ví dụ thông qua tính năng nhập URL, fetch webhook, tải ảnh hoặc tích hợp bên thứ ba. Một đường egress rộng khiến hậu quả có thể lớn hơn vì server có khả năng tiếp cận nhiều mạng hoặc services.

Một policy chặn direct Internet và chỉ cho những outbound destinations được duyệt có thể giảm khả năng server dùng làm **proxy đi tới đích không mong muốn**.

### 14.2. Egress internet deny chưa đủ cho SSRF nội bộ

SSRF không chỉ nhắm Internet công cộng. Một ứng dụng có thể có khả năng gọi:

- IP loopback hoặc localhost services.
- Metadata/identity endpoints của cloud.
- Internal management APIs, databases hoặc admin interfaces.
- Private IP ranges qua peering/transit/VPN.
- Kubernetes API và service endpoints.
- Link-local addresses hoặc các địa chỉ đặc biệt theo nền tảng.

**Chặn public Internet không tự chặn private/internal destinations.** Phải bổ sung **application URL validation, allowed destination policy, metadata protection, IAM least privilege và network segmentation**.

### 14.3. Các nguyên tắc bảo vệ

- Nếu một ứng dụng chỉ cần fetch từ một API đối tác, dùng **fixed allowlisted destinations** thay vì nhận arbitrary URL.
- Xác thực protocol/scheme, hostname/port, redirect destination và address resolution theo kiến trúc.
- Không cho parser đi theo redirects tới đích ngoài danh sách.
- Bảo vệ metadata endpoints theo cơ chế cloud provider/host runtime hỗ trợ.
- Giới hạn outbound của workload ở **network firewall**, không chỉ validation trong app.
- Tách quyền IAM/workload identity để ngay cả khi metadata bị truy cập cũng không có quyền quá rộng.
- Ghi log các request bị từ chối một cách có kiểm soát, không đưa secrets vào logs.

**Một IPBlock phủ mọi RFC1918 có thể làm hỏng ứng dụng** và không bao phủ mọi địa chỉ nội bộ như IPv6/link-local. Hãy dùng policy theo workload/service boundaries và sản phẩm thực tế.

### 14.4. DNS rebinding và địa chỉ thay đổi

Khi ứng dụng/proxy xác thực hostname rồi thực hiện DNS lookup tại thời điểm khác, địa chỉ có thể thay đổi. Nếu không kiểm tra **địa chỉ thực được kết nối** và redirects theo cơ chế phù hợp, hostname allowlist có thể không tương ứng intended destination.

Đây là một lý do cần **network egress enforcement độc lập với application validation**. Không coi kiểm tra chuỗi URL tại thời điểm nhận request là đủ để khóa mọi đường mạng.

### 14.5. Cloud instance metadata không giống mọi Internet endpoint

Các cloud có **metadata services, workload identity services** và cơ chế bảo vệ khác nhau. Một số chạy qua địa chỉ link-local hoặc giao thức riêng; **không được mở/khóa theo một địa chỉ giả định áp cho mọi cloud**.

Khi thiết kế, cần inventory:

- Workload nào thực sự cần metadata/identity tokens?
- Access có được hạn chế theo phương thức provider hỗ trợ không?
- Endpoint nào hostNetwork/container có thể truy cập?
- Nếu chặn direct Internet, metadata path còn hoạt động hay không?
- Sự kiện access đến metadata có được giám sát/audit phù hợp không?

**Quyền đọc credential/token nên được quản trị bằng identity và platform hardening**, không dựa duy nhất vào một firewall egress rule.

## 15. Ngoại lệ egress và vận hành hạ tầng

### 15.1. Những dependencies dễ bị quên

Một kế hoạch chặn outbound toàn mạng có thể vô tình làm lỗi:

- DNS name resolution hoặc split-horizon DNS.
- Đồng bộ thời gian; certificate validation và distributed systems phụ thuộc clock.
- OS security updates, antivirus/EDR signatures và agent telemetry.
- PKI certificate issuance/renewal, một số revocation/status checking.
- SSO/OIDC discovery/token endpoints và workload identity.
- Package managers, container registry, artifact storage và CI dependencies.
- Backup/monitoring/log shipping.
- SaaS webhooks, payment providers, email/SMS delivery.
- Kubernetes control plane, CNI/mesh CA hoặc internal service discovery.

**Không nên giải quyết bằng allow Internet all**. Hãy xác định đúng destination, protocol, source, owner và cân nhắc **internal mirrors, proxy, private endpoints** khi phù hợp.

### 15.2. Quy tắc cấp ngoại lệ

Một ngoại lệ có thể gồm:

~~~text
Exception ID:  egx-lab-004
Requester:     payments application owner
Source:        prod/payment-api workload identity
Destination:   api.payment-provider.example
Protocol:      HTTPS TCP/443 via egress proxy
Purpose:       transaction status lookup
Duration:      approved until next scheduled review
Risk controls: TLS hostname validation, quota, logs
Verification:  positive request + negative direct-IP test
Rollback:      remove narrow allow rule if dependency retired
~~~

Các tên/ID là **ví dụ**, không chứa chứng thư hay thông tin tài khoản thật. Một exception tốt phải có **ngày xem xét, owner, lý do, phạm vi và cách xác minh**, không chỉ một IP hoặc hostname trong firewall.

### 15.3. DNS/CIDR thay đổi theo thời gian

Các SaaS providers có thể dùng **CDN, nhiều A/AAAA records, load balancing, failover**. Hardcode một IP đo được tại một thời điểm có thể gây outage khi service di chuyển.

Những lựa chọn:

- Proxy policy theo **hostname/app identity** khi cơ chế kiểm tra hỗ trợ đúng.
- Provider-published address/service ranges qua quy trình cập nhật đáng tin.
- Private connectivity hoặc service endpoint nếu có.
- Bộ quản lý allowlist được version, audit và test.

Không “mở luôn cả cloud provider range” nếu điều đó cho nhiều dịch vụ không liên quan. Khi FQDN là shared hosting, cần đánh giá **host/TLS/client identity** để tránh quyền quá rộng.

### 15.4. Chọn fail behavior

Nếu proxy/gateway gặp sự cố:

- **Fail-open direct Internet** có thể phá vỡ chính sách dữ liệu.
- **Fail-closed** có thể khiến critical business app không gọi được đối tác.
- **Controlled failover** sang một proxy/egress gateway khác đã có policy tương đương thường phù hợp hơn.
- **Emergency access** cần approval, giới hạn thời gian, audit và scope hẹp; không mở all egress ngoài quy trình.

Chọn phương án dựa trên mức nhạy cảm dữ liệu và yêu cầu availability. **Một luồng payment quan trọng** có thể cần HA nhiều AZ/region, không phải một rule bypass Internet tự động khi proxy down.

## 16. Observability: Chứng minh kết nối trực tiếp bị chặn

### 16.1. Cần nhìn nhiều lớp

~~~mermaid
flowchart TD
    APP["App/runtime events"] --> JOIN["Event correlation"]
    DNS["Controlled DNS logs"] --> JOIN
    FW["Host/CNI/cloud firewall verdicts"] --> JOIN
    PROXY["Proxy allow/deny logs"] --> JOIN
    NAT["NAT / gateway flow mapping"] --> JOIN
    AUDIT["Policy and IAM change audit"] --> JOIN
    JOIN --> SIEM["SIEM / investigation"]
    JOIN --> METRICS["Coverage / availability / egress dashboards"]
~~~

Để trả lời “**đã chặn direct Internet chưa?**”, một nguồn proxy log không đủ: nếu workload đi thẳng Internet, proxy có thể **không thấy request**. Nguồn trọng tâm là **network deny/allow tại những điểm outbound**, cộng proxy log và inventory các lối egress.

### 16.2. Bảng dữ liệu cần có

| Data source | Câu hỏi có thể trả lời | Điểm mù |
| --- | --- | --- |
| **Host/endpoint firewall** | Tiến trình/thiết bị nào bị chặn khi mở kết nối? | Phụ thuộc OS/agent, quyền thu thập và interface |
| **CNI flow verdicts** | Pod/workload nào được forward/drop tại data plane? | Có thể không thấy hostNetwork/secondary interface |
| **Cloud VPC/VNet flow logs** | Network tuples giữa NIC/subnets/destinations | Có thể thiếu Pod UID hoặc data trước NAT |
| **Proxy access/CONNECT logs** | Client/identity yêu cầu đích nào và policy quyết định gì? | Không thấy luồng bỏ qua proxy, có thể không có payload HTTPS |
| **DNS resolver logs** | Tên miền nào được hỏi, trả kết quả gì? | IP direct, cache, DoH/DoT ngoài scope |
| **NAT/gateway logs** | Địa chỉ/cổng nguồn trước–sau translation | Mapping có thể bị mất/hết hạn, không có app identity |
| **Application logs** | API/business operation, status, data export | Không thấy network block trước ứng dụng |
| **Cloud/K8s control-plane audit** | Ai sửa routes/firewall/proxy policies? | Không tự chứng minh traffic đã bị chặn |
| **DLP alerts** | Nội dung/quy tắc dữ liệu nào bị cảnh báo theo coverage | Không phải mọi kênh đều inspect được |

### 16.3. Một record flow chuẩn hóa

~~~json
{
  "event_time_utc": "2026-11-28T09:00:00Z",
  "cluster_id": "egress-lab",
  "source_workload": "reports/report-worker",
  "source_pod_uid": "lab-pod-uid-001",
  "source_ip": "10.50.2.17",
  "destination_ip": "203.0.113.40",
  "destination_port": 443,
  "protocol": "TCP",
  "direction": "EGRESS",
  "observation_point": "cni-egress-hook",
  "policy_id": "deny-direct-internet-v3",
  "verdict": "DROPPED",
  "sensor_version": "lab-sensor-v1"
}
~~~

Đây là **dữ liệu minh họa**, không phải schema CNI nào có sẵn. Địa chỉ **203.0.113.40** là dải dành cho tài liệu. Trường **DROPPED** là quyết định tại một điểm thực thi; nó không tự chứng minh không còn đường egress thứ hai ở interface khác. Nếu không có Pod UID cần ghi **unknown** thay vì gán từ Pod IP hiện tại.

### 16.4. Correlation và NAT attribution

Một luồng có thể đi:

~~~text
Pod 10.50.2.17:53120
   -> node / gateway SNAT (source changes)
   -> proxy or cloud NAT
   -> external 203.0.113.40:443
~~~

Nên lưu:

- Timestamp tại nguồn và thời gian ingest.
- Pod UID/workload owner hoặc server/device identity.
- Source/destination 5-tuple ở từng observation point.
- NAT original/translated tuples khi dữ liệu có.
- Policy ID/revision, gateway/connector và decision.
- Request/session ID ở L7 nếu thực sự có correlation đáng tin.

**Không coi một TCP connection là một HTTP request**: keep-alive, HTTP/2 và gRPC có thể multiplex nhiều requests qua cùng socket; một request cũng có thể xuất hiện trong nhiều logs qua proxy/NAT.

### 16.5. Sức khỏe telemetry là điều kiện nghiệm thu

Nếu flow exporter chết, dashboard có thể hiển thị **0 blocked flows** dù traffic không còn được quan sát. Cần metrics cho:

| Indicator | Cần phát hiện |
| --- | --- |
| **Sensor/agent coverage** | Node/endpoint mới chưa được thu thập |
| **Event drop/sampling rate** | Không đủ dữ liệu phân tích |
| **Collector queue/export failures** | Log bị tồn hoặc mất |
| **Proxy log ingestion latency** | Incident không có sự kiện kịp thời |
| **NAT mapping gaps** | Không quy kết được nguồn |
| **Policy revision drift** | Data plane chưa áp policy mới |
| **DNS resolver coverage** | Workload đi alternate resolver |
| **Clock skew** | Timeline across hops sai |
| **Audit retention/log integrity** | Không tìm được nguồn thay đổi |

Một hệ thống giám sát đúng cần **known-good test events** trong lab/canary để kiểm tra rằng data path và log path đều hoạt động.

## 17. Detection engineering cho direct egress

### 17.1. Đừng bắt đầu bằng “mọi kết nối lạ là exfiltration”

Một detector chất lượng nên dựa trên **policy intent, workload identity và context**. Những use cases:

| Use case | Bằng chứng cần | Cách hiểu phù hợp |
| --- | --- | --- |
| **Direct public connection attempt** | Firewall/CNI DROP từ workload tới public IP không qua proxy | Có cố gắng egress ngoài đường được phép; chưa chắc là malicious |
| **Unexpected permitted direct flow** | Flow FORWARDED tới public destination ngoài allowlist | Có dấu hiệu gap enforcement hoặc exception cần rà soát |
| **Alternative egress path** | Traffic xuất hiện qua NAT/interface/gateway không nằm trong inventory | Cần kiểm tra routes/attachments và ownership |
| **New destination at proxy** | Proxy request tới domain/service chưa được duyệt | Kiểm tra change/dependency và deny policy |
| **Excessive denied egress** | Nhiều deny theo cùng workload hoặc nhiều dest/port | Có thể là retry loop, bug, scanner hoặc compromise |
| **DNS anomaly** | Tần suất/tên truy vấn thay đổi, NXDOMAIN tăng | Điều tra; không kết luận DNS exfil chỉ từ metadata |
| **Unexpected encrypted traffic** | New UDP/443/QUIC-like traffic ngoài route | Xem protocol support, policy và nguồn thực |
| **DLP hit at sanctioned destination** | Data classification rule + upload event | Có thể là sai nghiệp vụ hoặc false positive |
| **Metadata access anomaly** | Workload không cần metadata lại gọi endpoint | Xem SDK/identity path và quyền, không tự kết luận token lộ |
| **Policy relaxed during incident** | Audit thay firewall/routes/proxy ACL | Đánh giá actor, approval và hậu quả thực tế |

### 17.2. Pseudo-rule minh họa

~~~text
IF egress_flow.direction == "EGRESS"
   AND egress_flow.destination_class == "PUBLIC_INTERNET"
   AND egress_flow.source_workload IN restricted_workloads
   AND egress_flow.observation_point == protected_enforcement_hook
   AND egress_flow.verdict == "FORWARDED"
   AND destination NOT IN approved_exception_catalog
THEN:
   ALERT "Potential direct Internet egress gap"
   INCLUDE source workload identity, time, policy revision, gateway
   VERIFY routing/NAT mapping and telemetry coverage
~~~

Đây là **pseudocode detection**, không phải rule chạy trực tiếp. Giá trị **destination_class=PUBLIC_INTERNET** phải tính theo routing/địa chỉ thực, không đơn giản coi **mọi địa chỉ không thuộc RFC1918 là Internet**: còn IPv6, link-local, special-use, public IP của dịch vụ nội bộ, ranges do cloud định nghĩa và private connectivity.

### 17.3. False positives và false negatives

| Trường hợp | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| OS update vừa thêm hostname mới | FP “unapproved destination” | Change records và vendor endpoint inventory |
| Endpoint roaming sang Wi-Fi khác | FP hoặc actual gap | Device profile, agent status, network scope |
| Node SNAT che Pod IP | Misattribution | Original tuple + Pod UID/time |
| Client chỉ làm DNS cache hit | FN nếu detector chỉ dựa DNS | Kết hợp flow/gateway logs |
| QUIC direct nhưng chỉ giám sát TCP | FN | Dual protocol coverage |
| IPv6 route không qua firewall IPv4 | FN | IPv6 firewall/route/test parity |
| Application dùng private endpoint với quyền quá rộng | FN dữ liệu dù không có public egress | IAM/resource DLP/application audit |
| Proxy CONNECT tunnel không decrypt | FN content inspection | Endpoint/app/SaaS DLP khi cần |
| Collector quá tải và drop events | FN | Telemetry health metrics, sampling indicators |
| Backup hợp lệ tạo outbound spike | FP “exfil” | Baseline, schedule, authorized destination |

**False positive** gây mệt mỏi cảnh báo và có thể ảnh hưởng ứng dụng nếu dùng auto-block; **false negative** làm policy bypass bị bỏ sót. Cần test có nhãn, replay telemetry được phép và review incident outcomes.

### 17.4. Đo giảm bề mặt egress

Một vài KPI hữu ích:

- **Tỷ lệ workloads có deny-direct policy đã được xác minh**, không chỉ khai báo.
- **Số direct-public connections được allow** trong nhóm restricted (mục tiêu có thể gần 0, trừ ngoại lệ).
- **Số đường egress ngoài inventory**.
- **Tỷ lệ approved proxy traffic có source identity đầy đủ**.
- **Số ngoại lệ quá hạn** và thời gian review.
- **Thời gian phát hiện policy drift**.
- **Tỷ lệ positive/negative regression tests PASS**.
- **Độ trễ telemetry**, event loss và coverage.
- **Proxy availability/latency/cost** theo workload.

Không dùng chỉ số **“bao nhiêu byte đã bị chặn”** để tuyên bố đã ngăn được đúng ngần ấy byte dữ liệu nhạy cảm. Firewall drop log không biết nội dung đầy đủ của luồng đã bị từ chối.

## 18. Bảo vệ proxy/egress gateway và tránh single point of failure

### 18.1. Proxy phải được bảo vệ như hạ tầng đặc quyền

Một egress proxy có thể có:

- Khả năng nối tới Internet từ nhiều nguồn nhạy cảm.
- Log chứa names/IPs và các mẫu truy cập nội bộ.
- CA/private keys nếu có TLS inspection.
- Credentials/service identity dùng gọi upstream services.
- Quyền policy/allowlist làm thay đổi luồng dữ liệu ra ngoài.

Vì vậy cần **harden OS/containers**, least-privilege IAM/RBAC, MFA/JIT cho quản trị, change audit, host firewall, cert/key rotation, software updates và vulnerability response.

**Không để proxy trở thành open proxy:** chặn Internet inbound, hạn chế source tenants/groups và xác thực ứng dụng khi hỗ trợ.

### 18.2. High availability

Một proxy đơn lẻ có thể là SPOF cho các dịch vụ cập nhật, payment hoặc authentication. Một thiết kế HA có thể dùng:

- Nhiều proxy nodes/AZs với health checks.
- Load balancing tới những proxy instances có policy giống nhau.
- Thống nhất truststores, identity và allowlists giữa nodes/regions.
- Session/connection draining hợp lý.
- Giám sát queue, active connections, CPU/memory và DNS resolution.
- Runbook failover/rollback đã kiểm thử trong lab.

**HA không có nghĩa tạo direct Internet bypass** khi proxy chết. Dự phòng phải đi qua **lối đã được phê duyệt** với scope và logging tương đương.

### 18.3. Thứ tự phụ thuộc để tránh deadlock

Một proxy có thể cần DNS/PKI/updates; một DNS service có thể cần cloud identity; một agent kiểm soát egress có thể cần gọi control plane để lấy policy. Nếu chính sách chặn lẫn nhau, hệ thống có thể không khởi động hoặc không thể gia hạn certificate.

Thiết kế dependency graph:

~~~mermaid
flowchart LR
    APP["Protected workload"] --> P["Egress proxy"]
    APP --> DNS["Approved DNS"]
    P --> DNS
    P --> PKI["PKI / CA service"]
    P --> ID["Identity and policy services"]
    P --> NET["Approved Internet destinations"]
    APP -. "DENY direct" .-> NET
    MGMT["Managed control plane / updates"] --> P
~~~

Kiểm tra **bootstrap và recovery path**. Nếu certificate hết hạn và proxy không truy cập được CA do chính rule của nó, phải có quy trình khôi phục kiểm soát; không xây một “allow all while bootstrap” vĩnh viễn.

### 18.4. Năng lực và chi phí

Một proxy tập trung có thể chịu:

- HTTP CONNECT concurrency.
- TLS handshakes và session reuse.
- Log volume cao.
- File upload/download lớn hoặc streaming.
- CPU cho content inspection/DLP.
- Cloud egress fees và cross-region data transfer.

Chọn **rate/concurrency limits, autoscale, timeouts, circuit breakers và budget alerts** theo tải thực. Một app có thể dùng nhiều connection nhỏ, một app khác giữ stream dài; không áp một giới hạn cho mọi use case.

## 19. Thiết kế kiểm soát dữ liệu và quyền truy cập theo lớp

### 19.1. Matrix “điểm thực thi → mục tiêu”

| Control | Ngăn gì chủ yếu? | Điều nó không tự làm |
| --- | --- | --- |
| **No direct route/firewall deny** | Kết nối ra Internet không qua lối được duyệt | Kiểm tra nội dung upload qua lối cho phép |
| **Proxy destination allowlist** | Kết nối tới destination không phù hợp | Object-level authorization ở SaaS/app |
| **DNS filtering** | Một số tên miền được phân giải theo policy | Kết nối trực tiếp IP, DoH ngoài resolver |
| **TLS identity verification** | Kết nối tới endpoint không đúng danh tính | Xác định data classification |
| **Network DLP** | Một số mẫu nội dung ra ngoài khi inspect được | Encrypted/unsupported channels, app-specific semantics |
| **Endpoint DLP** | Các thao tác file/data trên thiết bị có agent | Workloads/thiết bị unmanaged |
| **Cloud IAM/resource policy** | Đọc/ghi tài nguyên cloud theo principal/resource | Mọi network destination khác |
| **Application authorization** | User/service có được export/share object không | Volumetric DDoS và route bypass |
| **SIEM/NDR/IDS/IPS** | Giám sát/phát hiện theo sensor coverage | Đảm bảo mọi traffic bị chặn nếu không có enforcement |

### 19.2. Không đồng nhất “có giám sát” với “đã thực thi”

Một proxy có thể hoạt động ở chế độ **log-only**, một firewall rule được tạo nhưng chưa gắn vào NIC/subnet, hoặc một NetworkPolicy tồn tại nhưng CNI không hỗ trợ. Mỗi control cần:

1. **Policy declared** — có trong source of truth.
2. **Policy deployed** — được gắn vào đúng resource.
3. **Policy enforced** — điểm thực thi xử lý traffic.
4. **Policy observed** — log/metrics phản ánh quyết định.
5. **Policy verified** — allow/deny tests với nguồn/đích thực chứng minh behavior.

**Đánh dấu PASS khi có bằng chứng**, không chỉ vì UI ghi “Enabled”.

## 20. Triển khai từng bước: Từ quan sát tới chặn trực tiếp

### Bước 1 — Xác định phạm vi và mục tiêu chặn

Phân vùng rõ ràng:

- Server workloads không cần Internet.
- Workloads chỉ cần vài dịch vụ external.
- Egress gateways/proxies có quyền ra ngoài.
- User endpoints cần web browsing, updates và business SaaS.
- Critical admin/DB/secret-management networks.
- Những đường egress qua IPv4, IPv6, cloud, VPN, Internet-facing NIC và Kubernetes.

Mục tiêu ghi thành **tiêu chí testable**: “workload reports không mở TCP/443 trực tiếp tới public IP ngoài allowlist, vẫn gọi được reporting API qua approved proxy”.

### Bước 2 — Inventory và lập bản đồ đường đi

Thu thập **routes, NAT, firewall/SG/NSG effective rules, network interfaces, DNS, proxy settings, Kubernetes/CNI, cloud endpoints và VPN split tunneling** trong phạm vi được phép.

Với mỗi nguồn, tìm **đường đi tới default Internet**, không chỉ đường đã vẽ trong sơ đồ tài liệu. Đặc biệt kiểm tra **public IP association, IPv6 gateways, alternate interface, Kubernetes hostNetwork/secondary NIC và shared transit**.

### Bước 3 — Xây baseline hợp lệ

Sử dụng proxy/cloud flow/DNS/app logs và trao đổi với service owners để phân biệt:

- Kết nối thực sự phục vụ nghiệp vụ.
- Kết nối do telemetry/updates/PKI/identity.
- Kết nối không rõ owner hoặc dường như dư thừa.
- Kết nối bị thiếu log do các điểm mù.

**Observed traffic không tự là approved traffic.** Malware và cấu hình sai cũng có thể xuất hiện trong baseline; phải xác minh mục đích trước khi cho phép.

### Bước 4 — Thiết lập sanctioned egress path

Chuẩn bị:

1. Proxy/gateway có HA theo nhu cầu.
2. DNS/private resolver path rõ ràng.
3. Firewall cho source → proxy và proxy → selected destinations.
4. Identity, certificates, app-specific policy và routing.
5. Access logs, metrics, telemetry loss alerts và audit policy changes.
6. Recovery/rollback qua lối an toàn.

Không di chuyển toàn bộ production traffic trước khi proxy có đủ **capacity, TLS/trust configuration, protocol support và log coverage**.

### Bước 5 — Đánh giá policy ở chế độ quan sát khi có thể

Nếu sản phẩm hỗ trợ **log-only/dry-run/monitor** với semantics rõ, sử dụng để tìm legitimate dependencies và đánh giá false positives. Tuy nhiên:

- Log-only **không chặn** direct Internet.
- Một số firewall/CNI không có dry-run chuẩn.
- Chế độ quan sát có thể không thấy một đường đi nằm ngoài sensor.
- Quy trình phải định rõ lúc nào chuyển sang **enforce**.

### Bước 6 — Canary theo workload, subnet hoặc namespace

Chọn nhóm có rủi ro đủ thấp và owner rõ. Áp deny-direct nhưng giữ các allow dependencies đã duyệt. Kiểm tra cả **positive tests** và **negative tests**; đo latency, errors, DNS, cert renewal và downstream services.

Không đồng thời thay quá nhiều yếu tố như **DNS resolver, proxy version, CNI mode và firewall** nếu không có lý do, vì rất khó xác định nguyên nhân khi outage.

### Bước 7 — Chặn direct Internet ở lớp thực thi phù hợp

Áp policy cho toàn bộ đường đi trong phạm vi:

~~~text
Source workload / device
  ALLOW -> approved DNS/private dependencies
  ALLOW -> approved proxy/egress gateway
  DENY  -> public Internet via any other path

Proxy / egress gateway
  ALLOW -> approved external destinations
  DENY  -> all others
~~~

Kiểm tra route/NAT/SG/NSG/CNI/endpoint settings **theo cloud/OS/plugin thực tế**, không áp cú pháp mẫu cho mọi nơi. Chỉ định owner cho mỗi enforcement point.

### Bước 8 — Nghiệm thu và mở rộng

Trước rollout rộng:

- Thành công của luồng hợp lệ qua proxy.
- Direct public IP bị từ chối cả IPv4/IPv6 theo phạm vi.
- Đích không có trong allowlist bị proxy/gateway deny.
- DNS DoH/alternate resolver paths được xử lý theo policy.
- Logs chỉ ra đúng workload, verdict và policy version.
- Các ngoại lệ đã có owner/expiry.
- HA/failover không tạo bypass không kiểm soát.

### Bước 9 — Vận hành liên tục

Sau deploy, cần kiểm tra:

- Khi bổ sung ứng dụng, vendor hoặc package repository.
- Khi cloud region, VPC/VNet route, subnet hoặc CNI thay đổi.
- Khi thiết bị chuyển network hoặc VPN posture.
- Khi DNS/proxy certificates/CA cập nhật.
- Khi egress IP của proxy thay đổi.
- Khi các logs/proxy agents ngừng hoạt động.
- Khi exception hết hạn hoặc owner chuyển nhóm.

**Egress control là một chu trình quản trị**, không phải một lần cấu hình duy nhất.

## 21. Lab được phép: Kiểm chứng proxy bắt buộc và chặn direct Internet

**An toàn:** chỉ thử trong **cluster, VM hoặc endpoint lab thuộc quyền quản trị**, dùng tên miền và dịch vụ giả lập/được phê duyệt. Không thực hiện port scanning diện rộng, stress test/flood, thử khai thác hay gửi dữ liệu nhạy cảm ra ngoài. Chỉ dùng **một vài kết nối bình thường**, kết hợp logs ở enforcement point.

### 21.1. Môi trường giả định

~~~text
Source:
  egress-lab / report-worker
  giả định podIP: 10.50.2.17

Controlled services:
  proxy.security-egress-lab.svc.cluster.local:3128
  DNS resolver của cluster theo cấu hình thực

Approved external destination:
  api.partner.example:443

Denied:
  direct destination 203.0.113.40:443
  unapproved.example:443 via proxy

Evidence:
  CNI/host/cloud flow verdict logs
  Proxy access/denial logs
  DNS and app request logs
~~~

**Địa chỉ 203.0.113.40 chỉ dùng cho tài liệu RFC 5737**, và các domain **.example là placeholder**. Không sử dụng như endpoint thật để kết luận kết nối thành công/thất bại. Trong một lab thực, owner cần chuẩn bị **test endpoint có listener và logs**, với mạng được cấp phép.

### 21.2. Ma trận kiểm thử

| Test | Nguồn → đích | Kết quả mong đợi | Bằng chứng cần |
| --- | --- | --- | --- |
| **Proxy reachable** | report-worker → proxy TCP/3128 | Được phép | CNI/SG allow và proxy connection |
| **Approved request** | report-worker → proxy → approved API | Thành công theo app policy | Proxy allow + app response |
| **Direct public TCP** | report-worker → external test endpoint TCP/443 | Bị từ chối bởi egress policy | CNI/firewall DROP, source identity |
| **Unapproved proxy target** | report-worker → proxy → unapproved test hostname | Proxy DENY | Proxy policy ID/action |
| **DNS authorized** | report-worker → approved resolver | Hoạt động | Resolver/flow record |
| **Alternate resolver** | report-worker → resolver ngoài phạm vi đã dựng lab | Bị chặn nếu policy yêu cầu | Firewall/flow deny; không probe Internet tùy ý |
| **IPv6 direct path** | Workload dual-stack → authorized IPv6 test target ngoài proxy | Bị từ chối nếu IPv6 nằm trong scope | IPv6 firewall/route evidence |
| **Private dependency** | report-worker → approved private database | Hoạt động đúng quyền | Network + application auth |
| **Other internal target** | report-worker → unrelated management app | Từ chối nếu ngoài policy | Segmentation enforcement |
| **Proxy outage** | Approved app qua proxy | Fail closed/failover được thiết kế | Proxy HA logs, không có bypass |
| **Policy change** | Narrow allow được canary trong lab | Đúng scope, audit đầy đủ | Before/after, applied revision |
| **Telemetry outage** | Agent log export bị ngắt trong lab | Pipeline alert | Sensor health metrics |

**Một timeout không đủ chứng minh DENY đúng lớp.** Nếu test endpoint không có listener hoặc DNS sai, request cũng thất bại dù firewall vẫn mở. Cần xác minh **flow verdict tại đúng hook và endpoint khỏe**.

### 21.3. Các lệnh quan sát Linux chỉ đọc

Trên một máy lab có các công cụ tương ứng:

~~~bash
# Xem địa chỉ và routes; không thay cấu hình.
ip -br address
ip -4 route show
ip -6 route show

# Kiểm tra DNS resolver và system proxy environment.
cat /etc/resolv.conf
env | grep -i '_proxy='

# Xem các kết nối TCP đang có của namespace này.
ss -tn
~~~

**Lưu ý:** các lệnh ở trên chỉ xem **current state**, không tự mô tả lịch sử routing/firewall. Chúng cũng không đủ để chứng minh proxy được bắt buộc sử dụng. Một số image container tối giản không có **ip, ss, grep**; thiếu công cụ không có nghĩa mạng lỗi.

### 21.4. Kiểm tra Kubernetes inventory chỉ đọc

~~~bash
kubectl get networkpolicies -n egress-lab
kubectl describe networkpolicy -n egress-lab
kubectl get pods -n egress-lab -o wide
kubectl get services -n security-egress-lab -o wide
kubectl get pods -n security-egress-lab --show-labels
~~~

**RBAC Forbidden là giới hạn quyền**, không chứng minh object không tồn tại. NetworkPolicy hiện trong API chưa chứng minh CNI enforcement; cần flow verdict/synthetic tests trong lab.

### 21.5. Dùng curl đúng mục đích

Ví dụ khi lab đã có **proxy và API endpoints thật**:

~~~bash
# Gửi một request hợp lệ qua explicit proxy lab.
curl --head --max-time 10 \
  --proxy http://proxy.security-egress-lab.svc.cluster.local:3128 \
  https://api.partner.example/

# Negative test: một request nhỏ không dùng proxy.
# Chỉ dùng hostname test endpoint đã được chủ lab cấp quyền.
curl --head --max-time 10 --noproxy '*' \
  https://direct-test.lab.example/
~~~

**Không chạy nguyên các placeholder .example và mong có phản hồi DNS thật**. Những lệnh này minh họa sự khác nhau giữa **yêu cầu qua proxy** và **không qua proxy**; để kết luận cần:

1. Đảm bảo proxy được cấu hình/route thật và endpoint test hoạt động.
2. Kiểm tra host OS/library có dùng proxy env/PAC khác ngoài ý định không.
3. Xem **proxy log** cho request đầu.
4. Xem **firewall/CNI deny** cho request thứ hai.
5. Kiểm tra IPv4/IPv6 nếu hệ thống hỗ trợ.

**Đừng thêm --insecure/-k** để coi TLS test thành công; phải giải quyết đúng certificate trust/hostname.

### 21.6. Không dùng PCAP rộng khi metadata đã đủ

Nếu flow verdict và proxy logs chứng minh DENY, thường **không cần ghi raw packet capture**. PCAP có thể chứa tên miền, headers và dữ liệu nhạy cảm. Chỉ capture trong phạm vi và quyền đã được phê duyệt, đặt giới hạn thời gian/số gói, snapshot nhỏ và bảo vệ dữ liệu sau thu thập.

## 22. Khắc phục sự cố khi siết egress

~~~mermaid
flowchart TD
    A["Outbound request fail sau thay policy"] --> B{"Đích là private dependency hay Internet?"}
    B -->|Private| C["Routing / segmentation / identity / app auth"]
    B -->|Internet| D{"DNS qua resolver được duyệt OK?"}
    D -->|Không| E["Resolver path / DNS policy / IPv6"]
    D -->|Có| F{"Client kết nối được proxy?"}
    F -->|Không| G["Proxy address, routing, source egress allow, proxy ingress"]
    F -->|Có| H{"Proxy cho phép destination?"}
    H -->|Không| I["Proxy ACL, identity, domain/port, exception approval"]
    H -->|Có| J{"Proxy tới remote và TLS thành công?"}
    J -->|Không| K["Proxy egress, DNS, cert/SNI, upstream/network"]
    J -->|Có| L["App response, auth, API limits, business dependency"]
    C --> M["Verify positive + negative test sau sửa"]
    E --> M
    G --> M
    I --> M
    K --> M
    L --> M
~~~

### 22.1. DNS bị lỗi sau default-deny

**Triệu chứng:** ứng dụng báo tên miền không phân giải được, nhưng proxy service vẫn chạy.

**Kiểm tra:** resolver trong /etc/resolv.conf hoặc client config, NodeLocal/CoreDNS nếu Kubernetes, DNS TCP/UDP/DoT tùy kiến trúc, NetworkPolicy/CNI flow denies. **Không mở UDP/53 tới mọi Internet DNS server**; xác định đúng resolver được duyệt.

### 22.2. Proxy connection timeout

**Triệu chứng:** TCP tới proxy không hoàn tất hoặc proxy không phản hồi.

**Kiểm tra:** DNS tên proxy, proxy listener/bind, pod/service endpoints, source egress allow tới proxy, proxy ingress firewall, load balancer/health. Đừng lập tức mở trực tiếp TCP/443 tới Internet để khắc phục.

### 22.3. Proxy trả 407 hoặc lỗi xác thực

**HTTP 407 Proxy Authentication Required** thường cho biết proxy yêu cầu authentication hoặc credentials hiện tại không hợp lệ. Xác minh client identity/auth configuration, token/credential lifecycle và proxy logs.

**Không nhầm 407 của proxy với 401 từ ứng dụng đích.** Cấp quyền proxy không tự có nghĩa app chấp nhận user.

### 22.4. Proxy trả 403 hoặc deny policy

**HTTP 403 tại proxy** có thể do source identity, destination domain/port, URL/category policy hoặc policy exception đã hết hạn. Kiểm tra **rule ID, action, hostname normalized, source identity và thời điểm**.

Đừng thêm **allow all CONNECT 443** cho một workload chỉ để vượt qua một hostname bị sai trong allowlist; xác định đúng dependency và owner.

### 22.5. TLS handshake thất bại

**Giả thuyết:** certificate trust chain, SAN/hostname, proxy interception CA, clock skew, TLS version/cipher mismatch hoặc certificate pinning.

**Cách xử lý:** xác định TLS terminate ở client→proxy hay proxy→origin, kiểm tra đúng truststores và chứng thư. Không giải quyết bằng cách **bỏ xác minh TLS** hoặc tin mọi certificate.

### 22.6. HTTP 502/503/504 qua proxy

Các mã có thể xuất phát từ proxy/edge/upstream hoặc app, với semantics tùy sản phẩm:

| Kết quả | Điều cần tìm |
| --- | --- |
| **502** | Upstream connect/protocol/TLS failure hoặc response không hợp lệ |
| **503** | Proxy/target unavailable, queue/capacity hoặc service outage |
| **504** | Upstream timeout, DNS/network/backend processing |

Đừng coi mọi 5xx là chứng minh firewall đã chặn; cần **proxy access logs + backend logs + flow** theo request ID/time.

### 22.7. Một số ứng dụng hoạt động, một số ứng dụng không

Kiểm tra **proxy support của thư viện**, NO_PROXY/PAC, UDP/QUIC, WebSocket, large file upload, HTTP CONNECT port policies, IPv6, DNS/SNI/HTTP Host và backend authentication. Một legacy application có thể cần **protocol-aware gateway** hoặc exception narrow thay vì proxy HTTP phổ thông.

### 22.8. Direct Internet vẫn thành công dù policy đã tạo

Điều tra như **policy enforcement gap**:

1. Workload/host có thực sự thuộc tập **selected sources**?
2. Rule đã gắn vào NIC/subnet/pod/endpoint đúng chỗ?
3. NetworkPolicy có CNI thực thi không?
4. Có firewall allow khác cộng dồn/priority cao hơn?
5. Traffic đi IPv4 hay IPv6, TCP hay UDP?
6. Có NAT, split tunnel, secondary interface, hostNetwork hoặc peering route?
7. Log sensor đang đo **đúng observation point** không?

**Không kết luận “proxy bị bypass” chỉ từ việc không thấy proxy log** nếu không xác minh client request thật đã chạy và telemetry pipeline khỏe; tuy nhiên đường direct thành công được chứng minh là điểm cần khắc phục.

### 22.9. Production outage do thay policy

Trong sự cố availability:

- Xác minh **change ID, policy revision, affected workload và CNI/firewall verdicts**.
- Giữ bằng chứng trước rollback khi tình huống cho phép.
- Khôi phục **allow rule hẹp cho dependency hợp lệ** hoặc revert change được review.
- Tránh tắt toàn bộ default-deny nếu có lựa chọn an toàn.
- Kiểm tra lại **positive và negative tests** sau sửa.
- Ghi owner và post-incident action để cập nhật dependency inventory.

**Rollback chỉ thành công khi data plane đã phản ánh trạng thái mới**, không phải chỉ khi manifest/IaC đã được merge ngược.

## 23. Tình huống tổng hợp: Report-worker được phép gọi đối tác nhưng không được ra Internet trực tiếp

### 23.1. Bối cảnh

Một công ty chạy ứng dụng **report-worker** trong Kubernetes trên cloud. Worker hàng giờ đọc dữ liệu báo cáo, lấy trạng thái giao dịch từ đối tác và ghi kết quả vào **private object storage**.

Yêu cầu:

- Không cho workload tự mở kết nối tới Internet ngoài điểm được duyệt.
- Cho phép **HTTPS tới API đối tác qua proxy**.
- Cho phép DNS resolver chuẩn, CA/identity services, internal database và private storage theo nhu cầu.
- Kiểm soát rò rỉ dữ liệu: dữ liệu nhạy cảm chỉ được export tới bucket/tài nguyên được phê duyệt.
- Có thể quy mọi outbound flow về **workload owner**, policy version và thời điểm.
- Không ảnh hưởng dịch vụ khi Pod autoscale hoặc một proxy instance lỗi.

### 23.2. Mô hình ban đầu

~~~text
report-worker Pod:
  source private IP: 10.50.2.17 (ví dụ)
  default route:    node -> cloud NAT -> Internet
  HTTP proxy env:   proxy.internal.example:3128

Observed:
  allowed request:  report-worker -> proxy -> partner API
  other request:    report-worker -> public destination TCP/443

Security issue:
  proxy configuration exists
  but direct Internet route remains reachable
~~~

**Tại sao nguy hiểm?** Một client/library không sử dụng proxy có thể tạo luồng trực tiếp ngoài proxy policy và ngoài network DLP/SWG observations. **Không khẳng định dữ liệu đã thất thoát** chỉ từ việc có đường egress; đó là **exposure** cần xử lý.

### 23.3. Kiến trúc sau cải tiến

~~~mermaid
flowchart LR
    subgraph WORKLOAD["Production workload zone"]
      R["report-worker Pods"]
      DB["Private database"]
      ST["Private object storage endpoint"]
    end
    R -->|"Approved internal path"| DB
    R -->|"Approved private connectivity + IAM"| ST
    R -->|"Only approved DNS"| DNS["DNS resolver"]
    R -->|"TCP/3128 allowed"| PX["Egress proxy pool"]
    PX -->|"Destination allowlist + audit"| API["Partner API HTTPS/443"]
    R -. "DENY direct TCP/443 + UDP/443 and other Internet" .-> FW["CNI/Cloud egress enforcement"]
    FW -. "Policy decision logs" .-> SOC["Observability/SOC"]
    PX -. "Proxy logs" .-> SOC
    IAM["Cloud IAM / bucket policy"] -. "Resource authorization" .-> ST
~~~

Mô hình này cần **network policy egress của report-worker**, **proxy ingress/egress policy**, **cloud firewall/routing** và **storage IAM/bucket/resource policy**. Không phải mọi Kubernetes CNI có thể thực thi cùng semantics trên mọi đường đi; cần kiểm tra plugin và topology.

### 23.4. Phân công kiểm soát

| Lớp | Chủ sở hữu | Điều cần thực thi | Bằng chứng |
| --- | --- | --- | --- |
| **Application** | Reports team | Chỉ gọi partner API được duyệt, kiểm soát dữ liệu xuất | App logs, business approvals |
| **CNI/NetworkPolicy** | Platform | report-worker chỉ egress tới DNS/proxy/dependencies | Policy verdicts, Pod UID |
| **Cloud routing/firewall** | Network/Cloud | Không có direct Internet từ nguồn restricted qua alternate path | Effective routes, flow deny |
| **Proxy** | Network/Security | Allow API partner, deny đích khác; source auth, limits | Proxy access/policy logs |
| **IAM/storage** | Cloud/Data | Worker chỉ ghi bucket/prefix/resource được cấp | Cloud audit, policy evaluation |
| **SOC** | Security | New destinations, bypass attempts, telemetry gap alerts | SIEM rules/tests |
| **SRE** | Reliability | Proxy HA, DNS, cert rotation, rollback | Metrics, controlled failover |

### 23.5. Một thay đổi gây lỗi

Sau khi bật **default-deny egress**, report-worker không phân giải được hostname API đối tác và kết nối đến proxy chập chờn. Nhóm platform quan sát:

| Thời điểm giả lập | Nguồn | Sự kiện |
| --- | --- | --- |
| 10:00 | GitOps/Kubernetes audit | Áp egress policy version 3 |
| 10:01 | CNI flow | report-worker → approved proxy TCP/3128 FORWARDED |
| 10:02 | CNI flow | report-worker → resolver UDP/53 DROPPED |
| 10:03 | App logs | Name resolution failure |
| 10:04 | Proxy logs | Không có request partner API mới |
| 10:05 | CNI flow | report-worker → public test IP TCP/443 DROPPED |

**Phân tích:** yêu cầu bảo mật direct-deny có vẻ hoạt động theo flow cụ thể đã đo, nhưng policy **quên đường DNS**. Proxy không có log partner request vì ứng dụng chưa phân giải tên/khởi tạo được request. Không cần nới outbound Internet để sửa.

### 23.6. Khắc phục

1. Xác minh resolver thực và CNI hook, gồm CoreDNS/NodeLocal nếu có.
2. Thêm **allow egress DNS hẹp** cho UDP/TCP theo đúng resolver path, không dùng any destination.
3. Kiểm tra proxy vẫn chỉ mở approved destination.
4. Kiểm tra request business hợp lệ qua proxy.
5. Kiểm tra direct public IP vẫn **DROPPED** cả IPv4/IPv6 theo scope.
6. Xem proxy resource/cert health và traffic sau deploy.
7. Ghi exception/owner/change event và cập nhật dependency documentation.

### 23.7. Biến thể: DLP vẫn chưa bảo vệ dữ liệu đúng

Giả sử worker đã đi qua proxy đúng cách nhưng có quyền cloud IAM quá rộng để ghi object vào **nhiều storage accounts/buckets** hoặc backend cho phép xuất dữ liệu khách A sang nơi nhận B. Network egress có thể PASS mà **data loss risk vẫn còn**.

Cần:

- IAM resource boundaries và application export authorization.
- Data classification/labeling và kiểm soát vùng lưu trữ.
- Cloud object audit, retention và approval cho exports nhạy cảm.
- DLP ở application/SaaS/endpoint nếu use case yêu cầu.

**Bài học:** kiểm soát đường ra là một trụ cột; bảo vệ nội dung và quyền dữ liệu là trụ cột khác.

### 23.8. Những câu hỏi phân tích case

1. Vì sao proxy env tồn tại nhưng không chứng minh direct Internet bị chặn?
2. NAT gateway có lọc website theo username và HTTP body mặc định không?
3. Khi chặn DNS, lỗi ứng dụng có thể bị nhầm thành lỗi gì?
4. Nếu proxy CONNECT tới partner được allow, nội dung HTTPS có tự được DLP kiểm tra không?
5. Vì sao chặn IPv4 mà quên IPv6 có thể tạo coverage gap?
6. Nếu public NAT IP được nhiều Pods chia sẻ, làm sao quy nguồn?
7. Tại sao flow DROPPED không tự chứng minh dữ liệu đã bị lấy cắp?
8. Cần kiểm tra kiểm soát gì với private object storage ngoài network egress?
9. Khi proxy outage, chính sách nên fail-open hay failover thế nào?
10. Một request PASS qua proxy có chứng minh toàn bộ datapath từ mọi node đều bị bắt buộc không?

**Gợi ý:** (1) thư viện có thể bỏ proxy nếu network route vẫn mở; (2) không, cần filtering riêng; (3) proxy/network/app outage; (4) không, nếu là tunnel chưa decrypt; (5) hai family có routes/rules khác nhau; (6) temporal NAT mapping + Pod UID; (7) chỉ chứng minh enforcement ở một hook; (8) IAM, tenant/object authorization và audit; (9) failover được duyệt cùng policy, không tự mở direct; (10) không, cần representative negative tests và route inventory.

## 24. Checklist nghiệm thu: Chặn kết nối trực tiếp ra Internet

### 24.1. Phạm vi và đường đi

| Hạng mục | Câu hỏi nghiệm thu | Bằng chứng mong đợi |
| --- | --- | --- |
| **Source inventory** | Workloads/endpoints nào thuộc policy? | Asset inventory theo environment/owner |
| **Approved destinations** | Tất cả exceptions có owner, lý do và expiry? | Versioned allowlist/exception register |
| **Default route** | Có alternate direct path từ source không? | Effective routing, NAT/peering inventory |
| **IPv4** | Direct public destinations bị từ chối? | IPv4 negative test và firewall log |
| **IPv6** | Có IPv6 route/rule tương đương nếu dùng? | IPv6 negative test và policy evidence |
| **UDP/QUIC** | Có xử lý UDP/443 và các UDP egress không cần thiết? | Protocol matrix và test |
| **VPN/split tunnel** | Endpoints đi ngoài gateway có policy không? | Device/agent routes và compliance logs |
| **Host/secondary interfaces** | hostNetwork, SR-IOV, multiple NICs có coverage? | Datapath inventory và tests |
| **Cloud route/SG/NSG** | Policies gắn đúng NIC/subnet/region/account? | Effective rules và audit |
| **Kubernetes CNI** | NetworkPolicy có được plugin thực thi? | CNI agent state, policy verdict |

### 24.2. Proxy, DNS và bảo vệ dữ liệu

| Hạng mục | Câu hỏi nghiệm thu | Bằng chứng mong đợi |
| --- | --- | --- |
| **Mandatory proxy** | Client chỉ kết nối được proxy cho public HTTP(S)? | Proxy allow và direct deny evidence |
| **Proxy authentication** | Có xác minh source/workload identity phù hợp? | Auth decision and logs |
| **Proxy destination rules** | Unapproved hostname/port bị deny? | Controlled test và rule ID |
| **Proxy not open relay** | Nguồn ngoài phạm vi không dùng được? | Network+auth deny |
| **DNS resolver** | DNS đi qua resolver chuẩn và ứng dụng vẫn hoạt động? | DNS logs, allow/deny tests |
| **Alternate DNS/DoH** | Có chính sách cho resolver không được duyệt? | Destination/protocol controls, observed flows |
| **TLS validation** | Client và proxy kiểm tra peer identity đúng? | Chain/SAN validation, negative cert test |
| **TLS inspection policy** | Nếu inspect, có quyền, CA/key và privacy controls? | Approved scope, DLP tests |
| **Private endpoints** | Storage/other cloud services có IAM/resource policy hẹp? | Cloud IAM tests và object audit |
| **Data classification/DLP** | Có kiểm tra nội dung ở đúng điểm nếu cần? | App/endpoint/SaaS DLP evidence |
| **SSRF/metadata** | Workload không tới internal/metadata targets ngoài quyền? | Network/identity guardrails |

### 24.3. Vận hành, giám sát và phục hồi

| Hạng mục | Câu hỏi nghiệm thu | Bằng chứng mong đợi |
| --- | --- | --- |
| **Policy owner** | Ai duyệt, sửa, thu hồi exception? | Change/approval records |
| **Negative tests** | Đã thử direct IP, wrong proxy target, alternate path? | Lab test matrix và deny logs |
| **Positive tests** | Các dependencies hợp lệ hoạt động? | App success, DNS/TLS checks |
| **Traffic attribution** | Có source workload/Pod UID và NAT mapping đúng thời gian? | Correlated flow records |
| **Proxy telemetry** | Có log source, destination, action, policy version? | Sample sanitized logs |
| **Telemetry health** | Có cảnh báo khi sensor/log sink mất dữ liệu? | Heartbeat/export metrics |
| **Policy drift** | IaC/actual rules và alternate gateways được kiểm tra? | Drift reports, audit |
| **Proxy HA** | Failover không tạo direct bypass? | Controlled fault exercise |
| **Performance** | Throughput, latency, queue đáp ứng nhu cầu? | p95/99, error/cost dashboards |
| **Privacy** | Log không chứa tokens, file content quá mức? | RBAC, retention, data review |
| **Incident response** | Có runbook xử lý egress gap và thất thoát nghi ngờ? | Approved playbook |
| **Rollback** | Có cách revert có kiểm soát giữ deny-direct? | Change version và retest |

**Nguyên tắc đánh dấu hoàn thành:** phải có **đường đi được xác minh và bằng chứng thực thi**, không chỉ thấy policy được tạo hoặc proxy đang chạy. Một proxy access log trống không chứng minh direct traffic đã bị ngăn.

## 25. Câu hỏi tự kiểm tra và đáp án

**1. Vì sao “không có public IP” không đồng nghĩa “không có Internet egress”?**

Vì một VM hoặc Pod private vẫn có thể dùng **NAT gateway, egress proxy, VPN, transit, private routing** để kết nối ra ngoài. Cần kiểm tra **route, NAT và effective firewall**, không chỉ network interface có public IP hay không.

**2. Tại sao cấu hình HTTPS_PROXY không đủ để bắt buộc mọi ứng dụng dùng proxy?**

Vì client có thể không đọc biến môi trường hoặc có đường direct socket khác. **Firewall/network enforcement phải chặn direct Internet** từ source được bảo vệ.

**3. NAT gateway có mặc nhiên chặn các website không thuộc allowlist không?**

Không. NAT chủ yếu thay địa chỉ/cổng; muốn destination filtering/URL policy cần firewall/proxy và cấu hình chuyên biệt.

**4. Vì sao một proxy có allowlist đúng nhưng nguồn còn route TCP/443 ra mọi public IP là chưa đạt mục tiêu?**

Vì client có thể **đi thẳng Internet**, không qua proxy. Proxy không có log cho traffic không đi qua nó.

**5. Nếu chỉ chặn direct IPv4 TCP/443, còn thiếu những gì?**

Có thể thiếu **IPv6, UDP/QUIC, non-443 traffic, alternate interfaces, tunnels, VPN split path** và internal/private paths được dùng sai mục đích.

**6. Port TCP/443 có chứng minh đích là HTTPS service được phép không?**

Không. Port không chứng minh **hostname, server identity, nội dung hoặc quyền nghiệp vụ**. Cần destination policy và TLS/application validation phù hợp.

**7. Bắt buộc DNS qua enterprise resolver có đủ chặn client tới external IP không?**

Không. Client có thể dùng cached IP hoặc gọi IP trực tiếp; network egress phải được kiểm soát riêng.

**8. DNS over HTTPS tạo điểm mù nào?**

DNS query có thể không đi tới resolver doanh nghiệp, nên resolver logs không thấy tên miền. Cần kiểm soát **alternate resolver/destination** và quan sát flows ngoài DNS.

**9. FQDN-based egress rule khác fixed IP rule thế nào?**

FQDN policy có thể theo DNS answer, SNI/Host hoặc proxy metadata tùy sản phẩm; IP rule chỉ theo addresses. Cần hiểu **TTL, shared IP/CDN, IPv6 và cách chính sách map tên–địa chỉ**.

**10. Vì sao TLS identity verification vẫn quan trọng nếu proxy đã allow đúng FQDN?**

Vì allow hostname không tự xác minh server đang giao tiếp là đúng chủ thể; client/proxy phải kiểm tra **certificate chain và hostname** theo thiết kế.

**11. HTTP CONNECT không decrypt có đọc được dữ liệu body HTTPS không?**

Thông thường không. Proxy có thể thấy CONNECT hostname/port, source, metadata và bytes, nhưng payload bên trong vẫn mã hóa.

**12. Bật TLS inspection đại trà có luôn tốt hơn cho DLP không?**

Không. Nó mở rộng quyền thấy plaintext, ảnh hưởng privacy, CA/key security, tương thích, hiệu năng và tuân thủ. Nên chọn **điểm kiểm tra phù hợp**, có phê duyệt.

**13. Chặn direct Internet có bảo đảm không có thất thoát dữ liệu không?**

Không. Data có thể bị gửi tới **dịch vụ đã được phép**, private cloud bucket sai quyền hoặc endpoint bên trong. Cần **DLP, IAM, application authorization và audit dữ liệu**.

**14. Default-deny egress NetworkPolicy trong Kubernetes chỉ chặn Internet phải không?**

Không. Nó có thể chặn **cả DNS, service-to-service, cloud APIs và private dependencies** theo semantics enforcement của CNI.

**15. NetworkPolicy object tồn tại là đủ để kết luận egress đã bị chặn?**

Không. Cần plugin thực thi, policy chọn đúng Pods, network paths nằm trong scope, CNI status và negative tests.

**16. Vì sao proxy chạy ở namespace khác cần cả ingress và egress policies?**

Source Pod chịu egress isolation có thể cần allow tới proxy; proxy Pod chịu ingress isolation cần allow từ source; proxy còn phải có egress phù hợp tới remote destinations.

**17. Hai selectors namespaceSelector và podSelector cùng một mục peer có ý nghĩa gì?**

Chúng kết hợp để chọn Pods phù hợp **trong namespaces phù hợp**. Tách thành hai mục riêng có thể tạo logic OR và mở phạm vi.

**18. HostNetwork/SR-IOV ảnh hưởng gì tới kiểm soát CNI?**

Traffic có thể đi qua host/secondary interfaces **ngoài default pod datapath**; cần host/cloud/secondary network controls và test cụ thể.

**19. “Egress gateway” có tự kiểm tra mọi URL/body không?**

Không. Một số gateway chỉ làm routing/SNAT hoặc L3/L4 filtering; kiểm tra L7/DLP cần tính năng và điểm plaintext phù hợp.

**20. Vì sao cloud private endpoint vẫn cần IAM/resource policy?**

Vì private connectivity chỉ mô tả đường mạng; principal vẫn có thể được cấp quyền sai tới object, bucket, account hoặc API.

**21. Tại sao SSRF cần cả internal segmentation, không chỉ chặn Internet?**

Vì SSRF có thể nhắm metadata, localhost, management APIs và internal services **không thuộc Internet public**.

**22. Một flow DROPPED chứng minh điều gì?**

Chỉ rằng **sensor/enforcement point cụ thể** đã từ chối luồng theo record. Không chứng minh mọi alternate paths đều bị chặn hoặc dữ liệu bị đánh cắp.

**23. Một direct egress flow FORWARDED tới public đích ngoài policy có thể gợi ý gì?**

Có thể là **enforcement gap, unexpected exception hoặc đường đi không nằm trong dự kiến**; cần xác minh source workload, observation point, NAT và approval.

**24. Tại sao public NAT IP không đủ xác định Pod gây outbound request?**

Nhiều Pods có thể dùng chung egress IP; cần original/translated tuples và **Pod UID/source identity theo thời điểm**.

**25. Nếu DNS lỗi ngay sau default-deny, nên làm gì trước?**

Kiểm tra resolver path/ports, CNI/firewall drops và allow DNS hẹp. Không mở **all Internet** để chữa tên miền không phân giải được.

**26. Khi proxy lỗi, nên tự động bật direct outbound cho ứng dụng không?**

Không nếu trái chính sách. Ưu tiên **HA/failover qua điểm có policy tương đương**; emergency exception phải có owner, thời hạn, phê duyệt và audit.

**27. Vì sao “proxy log không có request” chưa chứng minh traffic không xảy ra?**

Traffic có thể bypass proxy; logging/collector có thể lỗi; ứng dụng có thể không tạo request. Cần network flow và telemetry health để xác minh.

**28. Tại sao nhiều data exfil alerts là false positives?**

Backup, releases, telemetry, bulk upload và business jobs hợp lệ có thể tạo bytes spike. Phải kết hợp workload baseline, app data logs và destination.

**29. Nếu client dùng proxy được duyệt nhưng gửi dữ liệu nhạy cảm tới một SaaS hợp lệ sai tenant, lớp nào còn cần?**

**Application/SaaS DLP, tenant/resource authorization, approved recipients và cloud IAM**. Network path đúng không chứng minh data sharing đúng.

**30. Ba bằng chứng tối thiểu để nghiệm thu chính sách chặn direct Internet là gì?**

Một **positive test** tới đích hợp lệ qua proxy; một **negative test** kết nối trực tiếp tới external test endpoint bị firewall/CNI deny; và **nguồn log/identity** cho thấy source, policy/action, thời điểm đúng, đồng thời kiểm tra không có alternate path trong phạm vi.

## 26. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Private subnet nghĩa là không có Internet.” | NAT, proxy hoặc transit có thể cấp outbound. |
| “Cấu hình proxy trong app đã ép mọi egress qua proxy.” | Cần chặn direct path bằng network enforcement. |
| “NAT gateway tự lọc website.” | NAT translation khác firewall/proxy destination policy. |
| “Proxy đã có log nghĩa là proxy thấy mọi outbound.” | Traffic bypass không xuất hiện trong proxy log. |
| “Chỉ chặn TCP/443 là đã chặn Internet.” | Còn IPv6, UDP, ports khác, tunnels và alternate interfaces. |
| “IPv4 deny tự bao phủ IPv6.” | Hai họ địa chỉ thường có routes/rules riêng. |
| “UDP/443 luôn là hành vi độc hại.” | Có thể là QUIC/HTTP3 hợp lệ; cần xem protocol/approval. |
| “Port 443 luôn là HTTPS service đáng tin.” | Port không xác minh hostname, certificate hoặc nội dung. |
| “DNS filtering bảo đảm mọi outbound được kiểm soát.” | Direct IP, caches, alternate resolver và DoH có thể nằm ngoài scope. |
| “Không thấy DNS query nghĩa là không có Internet access.” | Client có thể dùng cache hoặc IP trực tiếp. |
| “FQDN allowlist luôn đúng khi CDN đổi IP.” | Còn phụ thuộc DNS/TTL, shared hosting và cơ chế firewall/proxy. |
| “TLS CONNECT proxy biết mọi nội dung upload.” | Không tự thấy HTTP body khi chỉ chuyển ciphertext. |
| “TLS inspection không cần kiểm soát privacy.” | Plaintext visibility tạo rủi ro dữ liệu, keys và tuân thủ. |
| “Đã chặn Internet nên DLP hoàn chỉnh.” | Data có thể rời qua sanctioned SaaS/private endpoints. |
| “Một allow rule trong NetworkPolicy tự cho Pod ra Internet.” | CNI, routing, source/destination, cloud firewall và proxy vẫn quyết định. |
| “Default-deny egress chỉ ảnh hưởng public Internet.” | Có thể chặn DNS, private services, CA, identity và updates. |
| “NetworkPolicy tồn tại là bằng chứng data plane đang chặn.” | Cần CNI thực thi và negative tests. |
| “Kubernetes Pod IP là identity bất biến.” | Pod IP có thể đổi/tái sử dụng; dùng UID và thời gian. |
| “HostNetwork và secondary NIC luôn theo default CNI policies.” | Phải kiểm tra coverage riêng. |
| “Egress gateway đương nhiên tích hợp DLP.” | Có thể chỉ xử lý L3/L4 hoặc SNAT. |
| “Cloud NAT và private endpoint có cùng chức năng.” | NAT là translation; private endpoint là private connectivity theo service. |
| “Private endpoint bảo đảm chỉ ghi đúng dữ liệu.” | IAM/app authorization vẫn cần. |
| “Chặn public Internet sẽ ngăn mọi SSRF.” | SSRF còn nhắm internal, localhost, metadata và link-local. |
| “Cho phép 0.0.0.0/0 TCP/443 là ngoại lệ hẹp.” | Đây là phạm vi đích rất rộng, thường trái least privilege. |
| “Proxy lỗi thì nên fail-open direct Internet.” | Nên có HA và recovery có kiểm soát. |
| “Flow FORWARDED có nghĩa app upload dữ liệu thành công.” | Network verdict không phải application transaction result. |
| “Firewall DROP bằng chứng đã có exfiltration.” | Nó phản ánh từ chối tại một hook, không biết dữ liệu bị lấy. |
| “Bytes out cao chắc chắn là data theft.” | Có thể là hoạt động hợp lệ; cần context/data audit. |
| “0 logs nghĩa là 0 flows.” | Collector hoặc sensor có thể mất dữ liệu. |
| “Có policy ở cloud thì mọi VPC/region đều được bảo vệ.” | Phải kiểm tra attachments, transit và policy parity. |
| “Mọi ứng dụng đều hoạt động với HTTP proxy.” | Legacy TCP/UDP/discovery có thể cần gateway khác. |
| “Chính sách chặn traffic là cách sửa mọi incident.” | Cần điều tra nguồn và giữ bằng chứng, tránh downtime trái ý định. |

## 27. Tổng kết

**Chặn kết nối trực tiếp ra Internet** là cách thu hẹp đường dữ liệu ra ngoài và bắt buộc các workloads, servers hoặc endpoints đi qua **proxy/egress gateway/đường kết nối được phê duyệt**, nơi có policy, authentication và observability tương ứng. Mục tiêu không phải chỉ “có proxy”, mà là **không còn đường Internet ngoài policy** trong phạm vi đã cam kết.

Những nguyên tắc cốt lõi:

1. **Default-deny trực tiếp:** nguồn restricted không được mở direct public connection; chỉ allow DNS, proxy và các dependencies cần thiết.
2. **Kiểm soát cả hai phía:** source → proxy phải được phép đúng scope; proxy → destination phải có allowlist/identity/protocol policy riêng.
3. **Không nhầm NAT, route, DNS và firewall:** NAT không lọc website, DNS filtering không chặn direct IP, routes không chứng minh authorization.
4. **Bao phủ mọi datapath:** IPv4/IPv6, TCP/UDP/QUIC, VPN/split tunnels, cloud transit, Kubernetes hostNetwork/secondary interface và alternate egress.
5. **Least privilege theo workload:** quản trị exceptions bằng purpose, owner, lifecycle, identity và review; không tự tin observed flows đều cần được mở.
6. **DLP theo dữ liệu:** network control giảm đường bypass, còn data classification, application authorization, IAM và content inspection ở điểm phù hợp mới xử lý nội dung nhạy cảm.
7. **Bảo vệ nội bộ và SSRF:** chặn public Internet không thay microsegmentation, metadata/identity safeguards và application URL validation.
8. **Vận hành có kiểm chứng:** proxy HA, DNS/PKI/updates dependencies, telemetry health, policy versioning, negative tests, incident triage và rollback hẹp.
9. **Đo đúng:** một flow deny là bằng chứng tại một điểm, không phải toàn hệ thống; một byte counter cao không phải bằng chứng thất thoát dữ liệu.

Trong **SECURITY_NETWORK_SECURITY**, egress control kết nối kiến thức về **firewall, phân đoạn, DNS, VPN, proxy, IDS/IPS, workload identity, cloud/Kubernetes network và giám sát** thành kiến trúc defense in depth. Chỉ khi **request hợp lệ đi được đúng tuyến** và **request trực tiếp/ngoài quyền bị từ chối ở đúng điểm thực thi**, doanh nghiệp mới có cơ sở nói rằng chính sách chặn direct Internet đang hoạt động.

### Tài liệu tham khảo và đọc thêm

- **NIST SP 800-207 — Zero Trust Architecture:** quyền truy cập theo tài nguyên/identity, giảm phụ thuộc vị trí mạng và phân vùng quyền.
- **NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy:** nguyên tắc thiết kế, vận hành firewall và policy.
- **NIST SP 800-53 Rev. 5 — Security and Privacy Controls:** các nhóm kiểm soát thông tin, truyền dữ liệu, logging, network và access control.
- **Kubernetes Documentation — Network Policies:** semantics của ingress/egress isolation, pod/namespace selectors, IPBlock và plugin enforcement.
- **Kubernetes Documentation — DNS for Services and Pods, Service/EndpointSlice:** đường DNS/service networking cần bảo vệ khi siết egress.
- **Container Network Interface (CNI) Specification và tài liệu CNI đang dùng:** xác minh policy scope, NAT, host networking, interfaces và flow visibility.
- **AWS VPC, Security Groups, Network ACLs, NAT Gateway, VPC Endpoints và Network Firewall Documentation:** công dụng riêng của routing, NAT, firewall và private services.
- **Microsoft Azure Virtual Network, NSG, Azure Firewall, NAT Gateway, Private Endpoint Documentation:** effective routes/rules và kiểm soát outbound.
- **Google Cloud VPC Firewall, Cloud NAT, Private Service Connect/Private Google Access Documentation:** cách quản lý network path và resource access.
- **RFC 9110 — HTTP Semantics:** proxy, HTTP CONNECT, status codes và request/response behavior.
- **RFC 8446 — TLS 1.3:** bảo vệ kênh TLS, server authentication và handshake.
- **RFC 8484 — DNS Queries over HTTPS (DoH):** DNS qua HTTPS và điểm quan sát.
- **RFC 7858 — DNS over TLS (DoT):** DNS qua kết nối TLS.
- **RFC 5737 — IPv4 Address Blocks Reserved for Documentation:** các địa chỉ ví dụ trong bài.
- **RFC 2606 — Reserved Top Level DNS Names:** tên miền .example trong tài liệu.
- **OWASP SSRF Prevention Cheat Sheet:** input/URL validation, redirect policies, network segmentation và metadata service protections.
- **OWASP Kubernetes Security Cheat Sheet:** Pod networking, egress policies và workload hardening.
- **OpenTelemetry Documentation và tài liệu SIEM/NDR của tổ chức:** logging, identity correlation, pipeline health và retention.
- **Tài liệu proxy/SWG/DLP/endpoint agent đang được triển khai:** xác minh rõ HTTPS/CONNECT/TLS inspection, FQDN handling, QUIC support, logging, privacy, HA và fail behavior theo đúng sản phẩm/phiên bản.
