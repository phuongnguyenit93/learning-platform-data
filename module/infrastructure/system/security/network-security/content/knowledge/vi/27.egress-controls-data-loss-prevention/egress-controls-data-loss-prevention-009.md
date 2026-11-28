# Phân tách đường đi quản trị và đường đi dữ liệu: kiến trúc mạng an toàn, giảm di chuyển ngang và thất thoát dữ liệu

Hãy hình dung một hệ thống thương mại điện tử có các API tiếp nhận đơn hàng, database xử lý giao dịch và những máy chủ do đội vận hành điều khiển qua SSH, API quản trị hoặc giao diện điều khiển cloud. **Dữ liệu giao dịch** cần đi giữa các dịch vụ nghiệp vụ; trong khi đó, **lệnh quản trị** có thể thay đổi route, mở firewall, đọc log, sao lưu dữ liệu, cấp tài khoản hoặc tắt một máy chủ. Nếu hai loại lưu lượng dùng cùng đường truy cập, cùng mạng tin cậy và cùng các quyền mạng rộng, một ứng dụng web bị xâm nhập có thể trở thành điểm khởi đầu để tiếp cận giao diện quản trị, thay đổi chính sách egress hoặc tạo đường truyền dữ liệu trái phép.

**Phân tách đường đi quản trị và đường đi dữ liệu** là thiết kế các **vùng tin cậy, tuyến kết nối, điểm thực thi chính sách và danh tính** sao cho lưu lượng quản trị có đường truy cập được kiểm soát độc lập với lưu lượng xử lý dữ liệu của ứng dụng. Cách ly có thể được thực hiện bằng **mạng vật lý, VLAN, VRF, firewall, private endpoints, bastion/PAM, VPN/ZTNA, workload identity và chính sách truy cập theo ứng dụng**. Mức độ cách ly phụ thuộc threat model: phân tách logic có thể đủ cho một số hệ thống; hạ tầng có yêu cầu đặc biệt có thể cần **out-of-band management** dùng thiết bị/mạng độc lập.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, bài thuộc chương **Kiểm soát egress và chống thất thoát dữ liệu**. Chủ đề kết nối phân đoạn mạng, firewall, VPN, NAC, DNS, IDS/IPS, bảo mật cloud, container, Kubernetes, TLS/mTLS và Zero Trust. Trọng tâm không chỉ là “đặt SSH ở subnet khác”, mà là **chứng minh dữ liệu nghiệp vụ không có đường tự do tới giao diện quản trị, quản trị viên không dùng kênh không kiểm soát để truyền dữ liệu, và mọi ngoại lệ đều có chủ sở hữu, danh tính, thời hạn cùng bằng chứng kiểm thử**.

> **Nguyên tắc thiết kế:** Tách đường đi là điều kiện cần để giảm blast radius, nhưng **khác subnet hoặc VLAN không tự tạo ra một ranh giới bảo mật** nếu routing/firewall, identity, quyền quản trị hay các đường dự phòng vẫn cho phép vượt qua. Ngược lại, “quản trị” không tự là traffic an toàn: console, backup, log, API cloud và phiên hỗ trợ kỹ thuật đều có thể mang dữ liệu nhạy cảm ra ngoài nếu không được giám sát.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **data plane, control plane, management plane** và nhận ra chỗ chúng có thể cùng dùng hạ tầng.
2. Phân loại **application data, admin commands, orchestration control, telemetry, backup và break-glass traffic** theo ranh giới tin cậy.
3. So sánh **in-band management** với **out-of-band (OOB) management**; xác định tình huống cần tách vật lý và giới hạn của từng mô hình.
4. Lập sơ đồ **trust zones, VLAN, VRF, subnets, routes, security groups và firewall rules** cho một hệ thống thực tế.
5. Thiết kế đường quản trị qua **bastion/PAM/ZTNA, MFA, device posture, just-in-time access và session audit**.
6. Phân tích rủi ro **BMC/iDRAC/iLO, hypervisor, storage consoles, cloud control APIs, Kubernetes API server, kubelet và CNI**.
7. Ngăn **workload/data network tiếp cận management endpoints** qua đường trực tiếp, NAT, peering, VPN, dual-stack hoặc một đường dự phòng không kiểm soát.
8. Bảo vệ các luồng **DNS, NTP, PKI, logging, secrets, monitoring, backups** mà không mở mạng quá mức.
9. Kết hợp phân tách đường với **egress filtering, DLP, identity-aware authorization và observability**.
10. Thiết kế **high availability, fail-closed/break-glass, change management, negative tests, incident runbook** mà vẫn duy trì khả năng vận hành.

## 2. Data plane, control plane và management plane: ba khái niệm khác nhau

Ba thuật ngữ thường bị dùng lẫn nhau, nhưng chúng trả lời những câu hỏi khác nhau:

| Plane | Nhiệm vụ chính | Ví dụ |
|---|---|---|
| **Data plane** | Chuyển tiếp gói hoặc xử lý dữ liệu đang phục vụ workload/người dùng | API request, SQL, application payload, packet forwarding, storage I/O |
| **Control plane** | Quyết định/điều phối trạng thái hệ thống để data plane hoạt động | Routing protocols, Kubernetes scheduler/controllers, SDN controllers, service discovery/config |
| **Management plane** | Quản trị, cấu hình, cập nhật, vận hành và giám sát hạ tầng | SSH/API admin, cloud console/API, BMC, hypervisor manager, switch/firewall configuration, PAM |

Một hệ thống thực có thể đặt nhiều chức năng trên **cùng node, NIC, mạng hoặc API**. Ví dụ một Kubernetes API server phục vụ thao tác của administrator và controller, nên có thể xuất hiện ở cả **control** và **management workflows**; phân loại theo **mục đích flow và quyền được thực thi**, không theo một nhãn tuyệt đối.

### Minh họa chức năng

~~~text
          MANAGEMENT PLANE
  Operator --> Bastion/PAM --> Admin API
                |               |
                | change/config |
                v               v
          CONTROL PLANE
       Controllers / Routing / Policy
                |
                | programmed state
                v
            DATA PLANE
       Client --> App --> Database
~~~

**Một thay đổi từ management plane có thể ảnh hưởng đến toàn bộ data plane**: ví dụ sửa route 0.0.0.0/0, thay ACL hoặc cấp quyền đọc database. Do đó các cổng quản trị cần **mức bảo vệ mạnh hơn một cổng nghiệp vụ thông thường**, chứ không chỉ chuyển từ TCP/22 sang một số cổng khác.

## 3. “Đường đi” gồm nhiều thứ hơn dây cáp và CIDR

Trong bài này, một **đường đi truy cập** bao gồm:

1. **Principal/source:** user, workload, thiết bị, service account hoặc agent nào tạo kết nối.
2. **Entry point:** ZTNA broker, VPN, bastion, gateway, load balancer, proxy hay trực tiếp.
3. **Network path:** NIC, subnet, VLAN, VRF, route, peering, tunnel, firewall và NAT.
4. **Destination/asset:** server, switch, firewall, BMC, database, cloud API, Kubernetes API hoặc storage.
5. **Transport/application protocol:** TCP/22 SSH, TCP/443 HTTPS API, TCP/3389 RDP, SNMP, gRPC, SQL, TLS, v.v.
6. **Authentication/authorization:** MFA, mTLS, SSH certificate, PAM, RBAC, API scopes, database roles.
7. **Data exchanged:** commands, secrets, payload nghiệp vụ, logs, backups, telemetry hay configuration.
8. **Control and evidence:** allow/deny decision, session recording, audit event, anomaly alert và revocation.

Hai subnet tách nhau mà có route **any-to-any** giữa chúng vẫn có thể tạo cùng một đường tin cậy rộng. Một VPN riêng nhưng cùng một tài khoản admin chia sẻ với tất cả ứng dụng cũng không đạt nguyên tắc least privilege.

### Nguyên lý kiểm soát

~~~text
User/Workload
    |
    v
Authenticate identity + endpoint posture
    |
    v
Authorize requested asset + action
    |
    v
Enforce exact route/protocol/port
    |
    v
Target verifies peer + operation rights
    |
    v
Audit event / session / data movement
~~~

**Đường được định tuyến không đồng nghĩa được cấp quyền.** Một cổng TCP mở không chứng minh endpoint ở đó đã xác thực caller hay hạn quyền câu lệnh.

## 4. Vì sao phải phân tách: threat model và blast radius

Hãy giả định một API public bị xâm nhập. Nếu mạng ứng dụng có route tới **switch management, hypervisor, BMC hoặc cloud credential endpoint**, tác nhân có thể tìm cách chuyển từ quyền trên application sang quyền quản trị hạ tầng. Mặt khác, nếu quản trị viên có khả năng copy data trực tiếp ra Internet qua máy bastion không có kiểm soát, chính đường quản trị trở thành kênh xuất dữ liệu ngoài chính sách DLP.

| Kịch bản | Điểm yếu nếu trộn đường đi | Mục tiêu phân tách |
|---|---|---|
| **Web API bị compromise** | App subnet gọi trực tiếp SSH/BMC/admin API | Chặn app→management, tách identity và endpoints |
| **Ransomware ở laptop admin** | Máy admin có route mọi server và storage | ZTNA/PAM/MFA/JIT, admin workstation chuyên dụng |
| **Credential admin bị lộ** | Một key dùng trên nhiều thiết bị | Individual identities, short-lived credentials, per-asset authorization |
| **Admin console public** | Internet có đường tới control-plane API | Private access paths, source restrictions, authentication |
| **Malicious backup/export** | Backup traffic đi cùng public egress | Dedicated backup endpoints, encryption, RBAC, DLP/audit |
| **Route hoặc SG bị sửa sai** | Management traffic đi qua data Internet gateway | VRF/route guardrails, change review, monitoring |
| **Workload gửi dữ liệu qua SSH tunnel** | Outbound SSH từ app subnet tới mọi IP | Block unapproved admin protocols and proxy bypass |
| **Data-plane DDoS** | Cùng NIC/queue bị nghẽn, mất khả năng quản trị | OOB hoặc dedicated capacity/path khi cần |
| **Monitoring/log agent bị chiếm quyền** | Telemetry path có quyền tới nhiều hệ thống | Constrain collection APIs, one-way ingestion và privilege |

**Không coi management plane “sạch” theo mặc định.** Nó có quyền cao hơn và có thể bị tấn công từ laptop admin, CI/CD, vendor access, token/cloud IAM hoặc phần mềm quản trị.

## 5. In-band management và out-of-band management

**In-band management** dùng chung một phần hạ tầng mạng với dữ liệu ứng dụng. Nó vẫn có thể phân tách về **VLAN/VRF/firewall và IAM**, nhưng thường chia sẻ ít nhất một tập NIC, switch, tuyến hoặc băng thông.

**Out-of-band management (OOB)** dùng **đường mạng/thiết bị riêng** dành cho quản trị, có thể hoạt động khi data network bị lỗi. Một OOB đáng tin có thể bao gồm management switch, dedicated NIC/BMC, console server, bảo vệ bằng firewall, AAA và đường khôi phục.

~~~text
IN-BAND
App Network ------ Shared Switch/Network ------ Server
                       |
                    Mgmt VLAN
                       |
                   Admin Proxy

OUT-OF-BAND (simplified)
Admin / Break-glass
         |
   Secure Mgmt Gateway
         |
   Dedicated Mgmt Switch
         |
      BMC / Console
      (separate link)

Data network uses independent production ports.
~~~

### So sánh

| Tiêu chí | In-band được phân đoạn | OOB có hạ tầng độc lập |
|---|---|---|
| **Chi phí/độ phức tạp** | Thường thấp hơn | Thường cao hơn, cần thiết bị và vận hành riêng |
| **Khả năng phục hồi khi data network lỗi** | Có thể bị ảnh hưởng do phần chia sẻ | Tốt hơn nếu tách đúng và không chung failure domain |
| **Ranh giới bảo mật** | Phụ thuộc routing, VLAN/VRF, firewall, IAM | Thêm đường vật lý riêng nhưng vẫn cần firewall/IAM |
| **Rủi ro chung switch/NIC** | Có thể còn | Giảm nếu đã tách thiết bị/cấp nguồn/path |
| **BMC/console reachability** | Có thể chạy trên mgmt VLAN | Thường hợp lý cho dedicated OOB |
| **Giám sát và vận hành** | Cần kiểm soát policy drift | Cần quản lý credentials, vật lý, HA của OOB |

**OOB không đồng nghĩa “cắm cổng BMC là xong”.** Nếu OOB gateway được public, BMC dùng default password hoặc admin VPN có full mesh route, ranh giới bảo mật vẫn có thể bị phá vỡ. “Separate NIC” cũng chưa chắc là **separate switch, power và route domain**.

## 6. Phân tách logic: VLAN, subnet, VRF và firewall

Các cơ chế thường dùng có vai trò khác nhau:

| Cơ chế | Làm được | Không tự bảo đảm |
|---|---|---|
| **VLAN** | Tách miền L2/broadcast theo cấu hình switch | Mọi traffic L3 giữa VLAN bị cấm |
| **Subnet/CIDR** | Xác định miền địa chỉ IP và routing | Phân quyền user/workload ở ứng dụng |
| **VRF** | Tách bảng định tuyến và miền routing logic | Không còn route-leak, inter-VRF gateways hoặc quyền admin sai |
| **Network firewall/ACL** | Kiểm soát nguồn/đích/port/protocol và state theo sản phẩm | User identity hay nội dung file nếu chỉ L3/L4 |
| **SG/host firewall** | Hạn kết nối tới NIC/host/workload | Mọi đường qua proxy/overlay khác |
| **VPN/IPsec** | Bảo vệ tunnel giữa điểm kết nối được xác thực | Quản trị viên được phép làm gì trên endpoint |
| **ZTNA/PAM** | Quyết định quyền truy cập ứng dụng/tài sản/phiên | Tự đóng mọi route nếu backend vẫn public |
| **Service mesh/mTLS** | Peer workload identity, mã hóa traffic mesh | End-user/object authorization |

### VRF và nguy cơ route leaking

~~~text
VRF DATA                         VRF MANAGEMENT
10.20.0.0/16                     10.250.0.0/16
   |                                  |
   +---- L3 firewall / controlled ----+
        inter-VRF route (if needed)

Default expectation:
  DATA -> MANAGEMENT: DENY
  ADMIN GATEWAY -> MANAGEMENT: limited ALLOW
~~~

Nếu cấu hình route leak hoặc một firewall cho **data subnet→management subnet any/any**, việc tách VRF không còn bảo vệ được điều tổ chức mong muốn. Test **effective route plus effective ACL** từ nguồn thực, không chỉ nhìn sơ đồ.

## 7. Reference architecture: tách data, control, management và backup

Mô hình sau dùng các dải địa chỉ **RFC 1918 giả định** để minh họa, không phải thiết kế triển khai sẵn.

~~~text
                      Enterprise IdP / PAM
                              |
                Managed Admin Workstation
                              |
                   ZTNA / Admin VPN
                              |
                  Management Bastion / PEP
                              |
                     Firewall Mgmt Zone
                              |
               +--------------+---------------+
               |              |               |
         Network Devices   Server Admin    Cloud / K8s APIs
           Management      SSH/RDP/API       (private endpoints)
          10.250.10/24    10.250.20/24      10.250.30/24
               |
        Dedicated OOB optional

  ----------------------------------------------------------------
                  Controlled inter-zone boundaries
  ----------------------------------------------------------------

 External Clients
       |
  Public Ingress / WAF
       |
     App Zone               Data Zone
    10.20.10/24 --SQL----> 10.20.20/24
       |
       +-- approved DNS / PKI / telemetry via constrained routes
       |
       X-- no direct SSH/BMC/hypervisor/network admin endpoints

 Backup / Recovery Zone (10.240.0/16)
       ^
       | restricted service identity + data movement policy
       +-- approved backup agents / replication
~~~

### Vì sao không gộp backup vào management zone?

Backup vừa có **chức năng quản trị** vừa vận chuyển **lượng lớn dữ liệu nhạy cảm**. Nếu đặt backup service có toàn quyền đọc database và toàn quyền điều khiển BMC trong cùng trust domain mà không tách policy, một incident có thể ảnh hưởng cả khả năng phục hồi. Vì vậy nhiều hệ thống tách **backup/recovery zone** hoặc kiểm soát theo luồng độc lập với management command plane.

### Tối thiểu cần bốn ranh giới

1. **User/Internet → public application ingress**.
2. **Application → database/internal data services**.
3. **Admin identity → privileged management interfaces**.
4. **Workload/backup → external/private data destinations** với DLP/egress controls.

Không mở tương tác **giữa tất cả các zone** chỉ vì một ứng dụng có dependency đặc biệt. Từng ngoại lệ phải mô tả **đúng source, destination, protocol, identity, business purpose và expiry**.

## 8. Lập inventory tài sản quản trị và dữ liệu

Một thiết kế phân tách thất bại phổ biến khi chỉ liệt kê server IP nhưng quên **console, monitoring, hypervisor, firmware, API cloud, secret store và emergency access**.

| Nhóm tài sản | Data path | Management path cần xác định |
|---|---|---|
| **Web/API server** | HTTPS/API tới client/backend | SSH/WinRM/agent/admin API qua bastion/PAM |
| **Database** | SQL/replication từ app/DB peers | DBA console, privileged commands, backup control |
| **Network switch/router** | Chuyển tiếp traffic production | SSH/HTTPS API, NETCONF/gNMI, SNMPv3, console |
| **Firewall/VPN gateway** | Chuyển tiếp/lọc traffic | Config API/SSH, logging, policy deploy |
| **Hypervisor/VM platform** | VM vNIC traffic, storage I/O | Hypervisor management API/console |
| **BMC/iDRAC/iLO** | Không phải ứng dụng data endpoint | Power cycle, firmware, remote console/media |
| **Kubernetes cluster** | Pod↔Service, ingress/egress | API server, admission/controllers, kubelet/node access |
| **Cloud workloads** | VPC/VNet traffic, object storage | IAM/control-plane APIs, instance/SG/route operations |
| **Storage/backup** | Data backup/restore/replication | Snapshot/export/key/admin consoles |
| **Telemetry** | App metrics, logs, traces | Collector/config/control UI, privileged search/export |
| **PKI/secrets** | Token/cert issuance and distribution | CA admin/HSM/secret store privileged operations |

### Mỗi record cần có

**Asset ID, owner, environment, trust zone, criticality, data classification, admin interface/ports, service identity, route, required source list, authentication method, recovery owner và negative tests**. Với cloud-managed services, không giả định **API endpoint public** có thể thay bằng private endpoint trên mọi sản phẩm; hãy kiểm tra provider capability và chính sách IAM.

## 9. Mô hình luồng được phép: chính sách từ source tới destination

Giả sử có bốn vùng: **APP**, **DATA**, **MGMT** và **BACKUP**, cộng **ADMIN-ACCESS** và **DNS/LOGGING**. Một flow hợp lệ phải có source/destination **và** danh tính/chính sách được phép.

| Flow ID | Nguồn | Đích | Giao thức/port minh họa | Kết quả |
|---|---|---|---|---|
| **FL-01** | Public ingress gateway | App web | TCP/8443 | ALLOW được giới hạn |
| **FL-02** | App workload | Database service | TCP/5432 | ALLOW từ workload được duyệt |
| **FL-03** | Managed admin device | ZTNA/PAM gateway | HTTPS TCP/443 | ALLOW sau MFA/posture |
| **FL-04** | Bastion/PAM identity | Server admin interface | SSH TCP/22 | ALLOW đúng host, JIT |
| **FL-05** | Dedicated OOB gateway | BMC/console | Theo device HTTPS/SSH | ALLOW giới hạn |
| **FL-06** | Backup agent | Backup repository | Giao thức và port thật | ALLOW theo service identity |
| **FL-07** | App workload | Management subnet | TCP/22, TCP/443, TCP/3389 hoặc any | DENY theo default |
| **FL-08** | Public Internet | BMC/hypervisor admin | Any | DENY |
| **FL-09** | Untrusted vendor VPN | Entire management subnet | Any | DENY |
| **FL-10** | App workload | Approved resolver/logging | UDP/TCP 53, telemetry port | ALLOW có giới hạn |
| **FL-11** | Management bastion | Arbitrary Internet storage | Any | DENY nếu ngoài quyền |
| **FL-12** | Backup controller | Production DB restore operation | Privileged API | Chỉ ALLOW với approval |

**Các cổng là ví dụ, không phải danh sách mở sẵn**. Nhiều admin APIs dùng TCP/443, trùng với HTTPS nghiệp vụ; policy phải phân biệt **đích/danh tính**, không thể nói “chặn port quản trị bằng cách chặn toàn bộ 443”.

## 10. Stateful vs stateless và gói phản hồi

Một request quản trị từ bastion tới SSH server:

~~~text
Outbound:
  bastion 10.250.1.10:53124
    -> server-admin 10.250.20.20:22 TCP

Return:
  server-admin 10.250.20.20:22
    -> bastion 10.250.1.10:53124 TCP
~~~

Với **stateful firewall/security group**, response hợp lệ thường được cho qua nhờ tracking connection. Với **stateless ACL**, phải xét cả chiều phản hồi và ephemeral destination port theo boundary/provider. **Không mở inbound any tới server** để “đảm bảo SSH trả lời”: nhận diện hướng request/response và nơi áp policy mới là trọng tâm.

### Ưu tiên effective path

Một flow có thể đi qua **host firewall → CNI/SG → subnet NACL → transit firewall → VRF gateway → target host firewall**. Chỉ một lớp cho phép không chứng minh cuối đường kết nối được. Ngược lại, một lớp bỏ chặn có thể vô tình tạo bypass nếu các lớp khác đang quá rộng.

**Chính sách mạng phải bảo vệ đúng cả các flow hợp lệ và flow ngoài quyền**; kiểm thử với source/port thực tế, không suy từ sơ đồ lý tưởng.

## 11. Tách danh tính quản trị khỏi danh tính sử dụng ứng dụng

Đường mạng riêng không đủ nếu một credential dùng được cả trong app và management. **Privileged identities** cần được quản trị riêng và có vòng đời khác tài khoản người dùng thông thường.

| Loại identity | Phạm vi | Nguyên tắc |
|---|---|---|
| **End-user identity** | Ứng dụng nghiệp vụ | MFA/SSO theo risk và app authorization |
| **Workload/service identity** | Gọi API, database, telemetry | Short-lived creds, mTLS/OAuth/IAM scope |
| **Administrative identity** | Cấu hình server/network/cloud | MFA chống phishing khi phù hợp, JIT/PAM, audit |
| **Automation/deployment identity** | IaC/CI/CD thay cấu hình | Service principal hẹp, approval, rotation |
| **Break-glass identity** | Khôi phục khi hệ thống quản trị lỗi | Dual control, vault, TTL, review sau dùng |
| **Vendor support identity** | Tài sản được chỉ định | Hạn thời gian/thiết bị/route, session recording |

**Đừng dùng cùng SSH private key hoặc cloud admin API key cho toàn bộ ứng dụng và CI jobs.** Nếu một Pod mang credential có quyền sửa SG/VPN/firewall, phân đoạn mạng có thể bị vô hiệu bởi chính workload bị xâm nhập.

### Danh tính đường truy cập không phải quyền dữ liệu

Một operator có quyền mở SSH tới host **không tự có quyền tải mọi database export về máy cá nhân**. Cần tách **host access, privileged command, dữ liệu đọc/ghi và kênh transfer**, có phê duyệt và log tùy độ nhạy.

## 12. Đường truy cập quản trị chuẩn: ZTNA/VPN + bastion + PAM

~~~text
Managed Admin Workstation
  (user identity + device posture)
           |
           | phishing-resistant MFA / approved auth
           v
     ZTNA / Admin VPN
           |
           v
     PAM / Bastion / PEP
           |  - JIT asset grant
           |  - session/account controls
           |  - command/file-transfer policy
           |  - audit/recording as applicable
           v
     Host / Network / K8s Admin Endpoint
           |
           X no direct broad route from user LAN
~~~

### Lưu ý thiết kế

1. **Administrator workstation** có posture và quyền phù hợp, không dùng chung thiết bị chưa quản lý nếu policy không cho.
2. **MFA** không tự ngăn session hijack; có thể cần device binding, session limit, phishing-resistant factors.
3. **ZTNA/PAM policy** chọn đúng **asset, action, role và thời hạn**, không cấp một subnet/VRF rộng cho mọi người.
4. Bastion chỉ có route/port cần thiết tới đúng management targets; không làm “pivot host” với internet egress tùy ý.
5. Endpoint xác minh **SSH host key, TLS SAN, mTLS identity hoặc cơ chế tương ứng**, không tin chỉ vì request đến từ bastion.
6. **PAM session recording** có giới hạn bảo mật và quyền riêng tư; không lưu password, secrets hoặc nội dung nhạy cảm nếu không cần thiết/phù hợp.
7. Lộ credential bastion phải có khả năng **revoke và điều tra** nhanh; session đang mở cần chính sách termination rõ.

**Một bastion có nhiều đường mạng** có thể thành cầu nối giữa data và management nếu không có host firewall, egress ACL và quyền truy cập phù hợp. Bastion cần được harden, cập nhật, giám sát và kiểm thử chính đường bypass của nó.

## 13. Quản trị SSH/WinRM/RDP: cổng đúng không đồng nghĩa quyền đúng

Đường quản trị thường dùng **SSH (TCP/22), RDP (TCP/3389), WinRM HTTP/HTTPS (mặc định TCP/5985/5986)** hoặc API HTTPS trên TCP/443. Đây là những **cổng thường gặp**, không phải chuẩn bất biến cho mọi hệ thống. Một thiết bị có thể đặt giao diện quản trị trên cổng tùy chỉnh; ngược lại, một web console quản trị dùng TCP/443 không được xem là ứng dụng web thông thường.

| Kiểm soát | SSH/Linux | RDP/Windows | HTTPS Admin API |
|---|---|---|---|
| **Xác thực đích** | SSH host key/certificate | TLS/host identity và cơ chế RDP phù hợp | TLS certificate/hostname/SAN |
| **Xác thực người dùng** | Short-lived SSH cert, PAM/JIT, MFA qua gateway | AD/IdP/MFA/gateway theo thiết kế | OIDC/OAuth/mTLS/API identity |
| **Giới hạn quyền** | Sudo/command/account policy | Privileged groups/JEA/PAM theo khả năng | API role/action scope |
| **Giới hạn đích** | Host allowlist, bastion egress | RDP broker/approved targets | Admin endpoint/resource IDs |
| **Audit** | Auth/session/privileged commands | Login/session/privilege changes | Control-plane audit events |
| **Chặn đường vòng** | Không cho app subnet SSH trực tiếp | Không public RDP | Không public console/IP ngoài policy |

### SSH forwarding và file transfer

SSH không chỉ chạy interactive shell. Nó có thể hỗ trợ **SFTP/SCP, local/remote/dynamic port forwarding**, tùy cấu hình. Nếu quản trị viên được SSH tới bastion rồi dùng nó làm **proxy tùy ý** tới Internet hoặc database, egress boundary có thể bị vượt qua mặc dù network policy tại laptop trông chặt. Chính sách phải xác định **có được forward port/truyền file hay không**, cùng host-level restrictions và theo dõi phù hợp.

**Không nên cố chặn mọi SSH để giải quyết DLP** nếu nó là đường vận hành được phê duyệt. Thay vào đó, hạn **principal, asset, port, command, session và data transfer**, rồi kiểm tra các đường khác ngoài bastion.

## 14. PAM, just-in-time access và phiên quản trị có thời hạn

**Privileged Access Management (PAM)** không đơn giản là nơi lưu mật khẩu. Trong một mô hình hoàn chỉnh, nó có thể quản lý **request/approval, cấp quyền tạm, credential brokering, session recording, credential rotation và revocation**.

### Vòng đời phiên quản trị

~~~text
Admin identifies maintenance task
              |
        Request approval
              |
       Validate admin identity
       + device posture + MFA
              |
       JIT grant (asset, action, TTL)
              |
        Bastion/session broker
              |
       Perform approved operation
              |
       Audit + command/change evidence
              |
       Session end + permission revoke
~~~

### Các ràng buộc quan trọng

- Quyền **root/domain admin/cloud owner** không nên cấp thường trực chỉ vì người đó thường trực vận hành.
- **JIT** cần định nghĩa rõ grant expiry và hành vi với **phiên đang mở**; TTL hết hạn không tự chứng minh session đã bị ngắt.
- **Just-enough-administration** hạn hành động/công cụ, không chỉ thời gian.
- Với vendor, khóa quyền vào **đúng thiết bị, ngày/hợp đồng và change ticket**, có quy trình kết thúc.
- Phân tách **requester, approver và executor** cho những hành động rủi ro cao khi tổ chức cần.
- Không coi **video session recording** là giải pháp duy nhất nếu file transfer/API automation không được audit.
- Credentials do PAM dùng để đăng nhập endpoint phải có **quyền đúng scope, rotation, protection và access logs**.

Một nhà vận hành hợp lệ vẫn có thể gửi dữ liệu ra ngoài trái quy định nếu chỉ kiểm tra “có được login vào máy hay không”. Vì vậy **đường chuyển file, cloud object export, database dump và egress của bastion** cần kiểm soát riêng.

## 15. BMC, iDRAC/iLO, IPMI và console: tài sản quản trị đặc biệt nhạy cảm

**Baseboard Management Controller (BMC)** và các cơ chế lights-out management có khả năng điều khiển máy chủ ngay cả khi hệ điều hành production lỗi. Tùy thiết bị, quyền này có thể bao gồm **power cycle, virtual console, firmware, virtual media và thay đổi boot settings**.

~~~text
Production OS NIC --------> Data Network

Dedicated BMC NIC --------> OOB Management Network
                               |
                        OOB Firewall/Gateway
                               |
                       Authorized Admin via PAM
~~~

### Threat model của BMC

| Rủi ro | Nguyên nhân thường gặp | Kiểm soát |
|---|---|---|
| **BMC reachable từ app subnet** | VLAN/VRF route leak, firewall allow quá rộng | OOB segregation + explicit deny |
| **BMC public exposure** | Port-forward/LB/cấu hình ngoài ý định | Không public, access qua secure gateway |
| **Default/shared credential** | Onboarding thiếu kiểm soát | Unique credentials, vault/rotation, MFA ở gateway |
| **Firmware lạc hậu** | Quản trị lifecycle bỏ sót | Inventory, signed updates, change validation |
| **Remote console lộ dữ liệu** | Session rộng, virtual media/file transfer | JIT permission, session controls và audit |
| **OOB vẫn cùng failure domain** | Chung switch/uplink/power | Kiểm tra mức tách vật lý thực tế |

**IPMI over LAN và một số protocol legacy có đặc tính bảo mật kém hơn HTTPS/SSH hiện đại**. Không mở IPMI/Redfish/console ra Internet chỉ vì “dễ hỗ trợ”, và phải theo khuyến nghị nhà sản xuất/phiên bản, hạn port cụ thể theo triển khai.

### Console không phải đường DLP miễn trừ

Virtual media và console có thể được dùng để **đọc dữ liệu, thay boot image hoặc truy xuất credential** nếu admin bị compromise. Những thao tác này cần approval và audit tương xứng; không phải “ngoài băng” là “ngoài chính sách bảo mật”.

## 16. Thiết bị mạng: SSH, SNMP, NETCONF/gNMI và AAA

Switch/router/firewall có thể vận hành data plane hàng chục Gbps, nhưng management plane chỉ nên nhận traffic từ một **tập management sources rõ ràng**.

### Bề mặt quản trị

| Giao thức/điểm | Mục đích | Ràng buộc |
|---|---|---|
| **SSH / HTTPS admin** | Đăng nhập hoặc cấu hình | Chỉ bastion/NMS được duyệt, AAA và audit |
| **SNMPv3** | Monitoring và đôi khi quản lý | Authentication/privacy, read-only mặc định khi phù hợp |
| **NETCONF over SSH** | Điều khiển cấu hình theo API | Principal/service credential, RBAC và commit audit |
| **RESTCONF/HTTPS** | Cấu hình qua HTTPS API | TLS verification, API roles, control path |
| **gNMI/gRPC** | Streaming telemetry/config | mTLS/credential, port và quyền update rõ |
| **Syslog/telemetry export** | Gửi sự kiện/tình trạng | Destination logs được duyệt, TLS nếu hỗ trợ |
| **TACACS+/RADIUS** | AAA tập trung | HA, trust, quyền tách biệt và audit |
| **Console server** | Recovery out-of-band | Access brokerage, không public |

**SNMPv1/v2c community strings không phải bảo vệ tốt cho đường quản trị nhạy cảm**; ưu tiên SNMPv3 với security phù hợp nếu hạ tầng hỗ trợ. Cũng không nên cho monitoring collector có quyền **write/config** khi chức năng chỉ là đọc trạng thái.

### Đừng nhầm protocol quản trị và routing control

BGP/OSPF có thể mang **control-plane traffic** giữa các router qua những interface phục vụ routing, không nhất thiết qua management VLAN. Việc đưa toàn bộ BGP/OSPF vào OOB chỉ vì “control plane” thường không đúng topology. Ngược lại, **API cấu hình BGP/route policy** nên bị hạn ở management access path. Cần phân biệt **lưu lượng định tuyến vận hành mạng** với **lệnh cấu hình router**.

## 17. Hypervisor, virtualization manager và SDN controller

Trong hạ tầng ảo hóa, một control/management API có thể tạo VM mới, kết nối virtual NIC, sửa virtual switch, snapshot disk hoặc mount virtual media. Những quyền này ảnh hưởng trực tiếp tới **dữ liệu và khả năng cô lập network**.

~~~text
Admin/PAM
   |
   v
Virtualization / SDN Manager
   |  - create/update VMs
   |  - attach vNIC / port groups
   |  - push routing/firewall policy
   v
Hypervisor hosts
   |
   +-- Production virtual network (data path)
   +-- Management network (admin/control APIs)
   +-- Storage/replication network (as designed)
~~~

### Ranh giới cần kiểm chứng

- **Virtualization manager** không public không cần thiết; chỉ admin principals được gọi API.
- Host management interfaces phải được tách khỏi **tenant VM virtual networks**.
- Quyền tạo vNIC hoặc gắn VM vào privileged port group có **admission/policy** và audit.
- Không cho automation workload không được duyệt **thay virtual router/firewall** thông qua token lưu trên VM.
- **Snapshot/export/migrate** có thể mang dữ liệu nhạy cảm; kiểm tra destination và quyền, không coi đó là flow cấu hình vô hại.
- Với NSX/SDN tương tự, phân biệt **controller management, overlay tunnel data, policy distribution và tenant access**.

**Một VM nằm trong data VLAN vẫn có thể gây ảnh hưởng management plane** nếu service account trên VM có API token sửa SDN/cluster. Mạng phân tách nhưng IAM bị phá vỡ vẫn là một đường leo thang đặc quyền.

## 18. Cloud control plane và data plane: công cụ riêng, API riêng

Trong cloud, **data plane** là những thao tác workload như đọc object, gọi API ứng dụng, query database hoặc gửi packet qua network interface. **Management/control API** có thể tạo tài nguyên, thay IAM policy, sửa security group, route table hoặc kích hoạt snapshot/export. Một số managed services dùng **chung FQDN, TLS/443 hoặc service endpoint** cho các hoạt động có ranh giới quyền khác nhau.

### Không nên chỉ lọc theo TCP/443

~~~text
App workload
  |
  +-- HTTPS :443 -> Partner payment API      [data flow]
  |
  +-- HTTPS :443 -> Cloud resource API       [management action]
  |
  +-- HTTPS :443 -> Object storage endpoint  [data export]

Port identical; principal and action differ.
~~~

### Các lớp cần có

1. **Cloud IAM**: workload role không được sửa route/SG/privileged IAM policies nếu không có business need.
2. **Private/approved API access paths** nơi provider hỗ trợ, với DNS/endpoint policy rõ ràng.
3. **Network egress**: chỉ đúng service endpoints, account/project/tenant và proxy nếu cần.
4. **Cloud audit events**: phát hiện thay đổi control-plane như mở outbound all, tạo access key, export snapshot.
5. **Organizational guardrails**: permission boundaries, service control policies/organization policy hoặc tương đương theo cloud.
6. **JIT human access**: administrator login riêng, MFA, device posture và audit.

**Private endpoint không tự chứng minh tài nguyên thuộc đúng account/tenant**. Một yêu cầu object storage đi qua private connectivity vẫn cần **IAM, bucket/resource policy, authorization theo account và phân loại dữ liệu**.

### Quyền thay network quan trọng hơn port

Nếu một Pod có credential quyền **modify network interface/security group**, nó có thể làm thay đổi chính ranh giới egress đang bảo vệ tổ chức. Trước khi chọn firewall rule, hãy hỏi: **ai có thể sửa rule? credential đó nằm ở đâu?**.

## 19. Kubernetes API server, kubelet và cluster management paths

Kubernetes có nhiều đường khác nhau:

~~~text
Human operator / CI
      |
   ZTNA / VPN / IAM / RBAC
      |
      v
 Kubernetes API Server (control/admin API)
      |
      +-- Scheduler / Controllers
      |
      +-- Kubelet / Node agents
      |
      v
 Pod workloads ---Service/Pod network---> Databases
      |
      X no arbitrary access to API admin, node SSH
        or cloud management endpoints
~~~

### Các yêu cầu an ninh

| Đường | Nguy cơ | Kiểm soát |
|---|---|---|
| **Operator → Kubernetes API** | Stolen kubeconfig, overly broad ClusterRole | IdP/RBAC, MFA, private API endpoint, audit |
| **CI controller → Kubernetes API** | Automation token có cluster-admin | Short-lived workload identity, scoped RBAC/approval |
| **Pod → Kubernetes API** | ServiceAccount token bị lạm dụng | Minimized RBAC, disable automount nếu không cần, admission |
| **Pod → kubelet/node management** | Node endpoint có quyền nhạy cảm | Host firewall, kubelet authn/authz, no public ports |
| **Admin → node SSH** | Pivot tới workload secrets/storage | JIT bastion/approved break-glass |
| **CNI/metrics/logging agents** | Cần host/control privileges | Service-specific role, origin/path policies |
| **Pod→Pod app traffic** | Tenant/data access | NetworkPolicy, mTLS, app authorization |

### Kubernetes API không phải dữ liệu ứng dụng

Ngay cả khi API server và application ingress cùng **TCP/443**, ranh giới quyền khác hẳn. **Không cho mọi namespace mặc nhiên gọi Kubernetes API** chỉ vì mọi app cần HTTPS ra ngoài. Nếu một Pod thật sự cần API (ví dụ controller), cấp **ServiceAccount hẹp** và network egress đúng destination; quyền RBAC mới quyết định có được **list Secrets/change NetworkPolicy** không.

### Các đường đặc biệt

**Control plane ↔ kubelet, admission webhook, cloud controllers, CNI/CSI, NodeLocal DNSCache và hostNetwork** có đường khác traffic Pod thông thường. Một NetworkPolicy default-deny không bảo đảm chặn được mọi node/host path và có thể làm hỏng cluster nếu chưa kiểm kê dependency. Đừng đưa các đường này vào một policy chung mà chưa kiểm tra implementation/CNI.

## 20. Ví dụ Kubernetes NetworkPolicy hạn app gọi quản trị

Giả sử namespace **shop-prod** chứa Pod **app=checkout**. Mục tiêu: checkout chỉ có egress tới **inventory API trong catalog-prod** TCP/8080 và DNS resolver thật đã được xác minh. Bước đầu cho allow workload-to-workload:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: checkout-allow-inventory
  namespace: shop-prod
spec:
  podSelector:
    matchLabels:
      app: checkout
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: catalog-prod
          podSelector:
            matchLabels:
              app: inventory
      ports:
        - protocol: TCP
          port: 8080
~~~

### Điều cần hiểu trước khi dùng

- Đây là **ví dụ có điều kiện**, chỉ hiệu lực khi CNI **thực thi NetworkPolicy** và selectors/ports khớp workload thực.
- **namespaceSelector AND podSelector** trong cùng một phần tử; tách thành hai phần tử là **OR**, có thể mở rộng quyền ngoài ý định.
- Kubernetes NetworkPolicy chuẩn có **additive allow semantics**: một policy egress allow-all khác chọn cùng Pod sẽ khiến policy này **không thu hẹp được quyền**.
- Chưa có allow DNS: nếu Pod đang egress isolated theo policy trên, **DNS có thể thất bại**; phải kiểm tra resolver topology và thêm rule được duyệt.
- Destination Pod ingress policy, Service readiness và cloud firewall cũng có thể chặn.
- **NetworkPolicy không tự cấm quyền gọi control-plane API nếu có network allow khác hoặc đường host đặc biệt**; cần RBAC/SG/host controls.
- NetworkPolicy này không kiểm tra **user, tenant hoặc HTTP method**; cần application authorization.

### Ví dụ baseline default-deny toàn namespace

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-egress
  namespace: shop-prod
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress: []
~~~

**Không triển khai nguyên mẫu lên production khi chưa có dependency inventory và negative tests**. Một baseline default-deny mới không xóa được quyền đã có từ policy allow-all khác. Cần quản trị **effective union của mọi policies**, đặc biệt chính sách tạo bởi Helm/operator/CNI extensions.

## 21. DNS, NTP, PKI, logging và monitoring: các dependency xuyên ranh giới

Một ứng dụng tách management/data path vẫn cần một số dịch vụ **hạ tầng chung**. Không nên chặn chúng một cách cơ học cũng không mở nguyên management subnet cho mọi Pod chỉ để dùng DNS/log.

| Dịch vụ | Luồng hợp lệ có thể có | Rủi ro |
|---|---|---|
| **DNS** | Workload → approved resolver UDP/TCP 53 hoặc mode khác | DoH/DoT ngoài quyền, DNS exfil, direct resolver |
| **NTP/time sync** | Host/node → approved time source | TLS/cert failures nếu clock sai |
| **PKI/CA** | Authorized agent → enrollment/renewal endpoint | CA admin endpoint bị lộ với workload thường |
| **Secrets/identity** | Workload → scoped token/secret service | Token issuance/privileged APIs quá rộng |
| **Logs/metrics/tracing** | Agents → collector/ingestion endpoint | Dữ liệu nhạy cảm trong logs, unauthorized query/export |
| **Health/readiness** | Approved probes → service ports | Probe source khác với Pod source, false positives |
| **Updates/repositories** | Controlled update agent → signed repos | Supply chain/unauthorized software |
| **Backup/restore** | Backup agent → repository, approved restore | Lượng dữ liệu lớn, thay đổi retention/immutability |

### Phân biệt ingestion với administration

~~~text
App/Node ---> Telemetry Ingestion Endpoint
                         |
                         v
                 Logging Storage
                         ^
                         |
              Operator Query/Admin UI
              (separate role and path)
~~~

Một logging agent chỉ cần **send-only** tới collector không nên có quyền mở **admin UI** của SIEM, xóa logs hoặc export mọi dữ liệu. Nếu cùng một endpoint TCP/443 phục vụ ingest và management, API authorization phải tách rõ methods/scopes; nếu có thể, thiết kế endpoints và firewall scopes độc lập.

### DNS hỏng không có nghĩa firewall data plane lỗi

Khi default-deny egress, một Pod có thể thất bại **trước cả bước gọi TCP tới inventory** vì resolver bị chặn. Cần kiểm tra **CoreDNS, NodeLocal DNSCache, managed resolver và host paths**, không copy nhãn CoreDNS từ cluster khác. Thực hiện test DNS rồi test application; hai kết quả không tương đương.

## 22. Backup, snapshot, restore: dữ liệu lớn trên kênh có quyền cao

Backup/recovery có thể đọc gần như toàn bộ database, file system hoặc VM disk. Vì vậy luồng này là **data movement có độ nhạy cao**, dù hành động được kích hoạt từ management plane.

### Đường hợp lý

~~~text
Approved Backup Controller (management action)
            |
            | task authentication/approval
            v
Backup Agent / DB Snapshot Service
            |
            | encrypted data flow
            v
Restricted Backup Repository
            |
         Immutable/retention controls
~~~

### Những lớp cần tách

1. **Ai được tạo lịch/khởi động backup?** — management authorization.
2. **Agent nào có quyền đọc dữ liệu?** — workload/DB permissions.
3. **Backup được ghi tới đâu?** — destination/account/bucket/tenant allowlist.
4. **Dữ liệu có được mã hóa in transit và at rest?** — TLS/mTLS, key management.
5. **Ai có quyền xóa, export hoặc restore?** — privileged actions và separation of duties.
6. **Repo có chống ransomware?** — immutability/retention/air-gap phù hợp.
7. **Phục hồi có kiểm thử nhưng không lộ dữ liệu production vào staging không?** — test data sanitization.

**Đừng đặt toàn bộ đường backup vào “management subnet” rồi cho phép mọi outbound HTTPS**. Một backup job có thể gửi rất nhiều dữ liệu qua TCP/443 và vẫn hợp lệ theo L3/L4 firewall; cần **đúng repository/account và DLP/data governance**.

## 23. Đường quản trị không được trở thành kênh DLP bypass

Một phân tách chỉ bảo vệ chiều **app→management** mà bỏ qua chiều **management→Internet** có thể khiến bastion, monitoring hoặc backup trở thành điểm chuyển dữ liệu ngoài chính sách.

### Các đường cần xem

| Điểm | Rủi ro dữ liệu rời vùng bảo vệ | Kiểm soát |
|---|---|---|
| **Bastion SSH/SFTP** | Copy logs/database dump qua session admin | File-transfer policy, JIT, audit, destination allowlist |
| **Remote desktop clipboard** | Copy/paste dữ liệu ra endpoint | Clipboard/drive redirection policy theo rủi ro |
| **BMC virtual media** | Mount ISO/virtual storage hoặc đọc console nhạy cảm | BMC access restrictions, session audit |
| **Cloud console/export API** | Snapshot/object copy tới account ngoài quyền | IAM organization policies, account allowlist, audit |
| **Backup agent/repository** | Restore/export data sang region/tenant sai | RBAC, repository policy, encryption/immutability |
| **SIEM/log search** | Export logs chứa PII/secrets | Query/export permission, masking, retention |
| **CI/CD deploy pipeline** | Upload artifacts chứa secret/config | Signing, secret scans, destination controls |

### Session recording không thay data controls

Có video ghi lại admin thao tác không đồng nghĩa hệ thống đã **ngăn file transfer hoặc API export**. Nếu có nhu cầu truyền tệp hợp lệ, cần **quy trình phê duyệt, lưu lượng tới điểm nhận được duyệt và kiểm tra nội dung theo luật/chính sách**, không mở cổng bất kỳ rồi chỉ hy vọng audit hậu kiểm.

**Mọi kênh “được tin cậy vì là quản trị” có thể mang dữ liệu.** Phải phân loại dữ liệu trên đường quản trị và test quyền transfer/export độc lập với quyền login.

## 24. TLS, mTLS, SSH và chứng thực từng đầu mối

Tách mạng làm giảm **khả năng tiếp cận**, nhưng không chứng minh **đúng thiết bị hoặc đúng service ở đầu kia**. Trên management path cần xác thực cả nguồn/người quản trị và đích quản trị theo protocol.

### Ma trận xác thực

| Đường | Đích cần được xác minh | Caller cần được xác minh |
|---|---|---|
| **Admin→bastion HTTPS** | TLS hostname/SAN, CA/trust phù hợp | IdP/MFA/device posture |
| **Bastion→host SSH** | SSH host key hoặc host certificate | SSH principal/JIT short-lived credential |
| **Automation→cloud API** | HTTPS server identity/endpoint | Scoped cloud workload identity/token |
| **NMS→switch gNMI** | TLS server/service identity | mTLS client/workload credential |
| **Management agent→PKI** | Issuer/CA service identity | Workload attestation/token/mTLS |
| **Backup agent→repository** | Repository TLS/service identity | Backup agent identity/authorized write |

**Đừng bỏ xác minh SSH host key hay tắt TLS certificate validation chỉ vì management VRF là private.** Một route, DNS hoặc proxy sai có thể đưa kết nối đến endpoint không mong muốn.

### Nguyên tắc certificate/key

- Hạn **thời hạn chứng thư** theo vận hành được; theo dõi renewal, expiry và clock.
- Dùng **trust bundle/CA** có nguồn gốc rõ; không tự tin CA lạ để khắc phục lỗi.
- Không để automation key hoặc SSH private key dài hạn nằm trong image/log/source repo.
- Tách **certificate identity** khỏi **authorization**: một client có mTLS hợp lệ vẫn có thể không được sửa firewall.
- Trong chuyển đổi CA/PKI, test **existing sessions và new handshakes**; cả hai có thể khác kết quả.
- Khi nghi lộ credential, **revoke/JIT termination, rotation và incident response**, không chỉ chờ hết hạn.

### Quản trị đường truyền qua VPN

IPsec/VPN có thể mã hóa **đường giữa điểm kết nối**, nhưng tunnel hợp lệ không tự xác thực từng **human administrator** hay quyền của từng workload trên target. Nên kết hợp VPN với PAM, firewall theo tài sản và xác thực endpoint.

## 25. ZTNA/private access vs VPN cho quản trị

Hai mô hình đều có thể an toàn khi cấu hình đúng. Khác biệt chính là **phạm vi quyền và cách ràng buộc identity vào kết nối**.

| Phương án | Cách sử dụng | Rủi ro cần quản trị |
|---|---|---|
| **Admin VPN toàn mạng** | Đưa laptop vào management CIDR | Lateral reachability nếu ACL/identity chưa hẹp |
| **VPN + firewall/PAM** | Tunnel vào zone rồi chỉ tới bastion/targets cụ thể | Policy drift, route leak, shared credential |
| **ZTNA app/asset proxy** | Cấp quyền tới console/SSH target theo identity/session | Origin bypass, broker/connector privilege |
| **OOB gateway** | Truy cập BMC/console khi production path lỗi | OOB internet exposure và shared admin identity |
| **PAM bastion** | Broker sessions, JIT/sudo/recording | File transfer/pivot, compromise của bastion |

### Phương án kết hợp

~~~text
Managed Admin Device
         |
      MFA + ZTNA
         |
       PAM Broker
         |
    Restricted Management VRF
         |
     SSH/API Targets
         |
    Optional OOB for recovery
~~~

**ZTNA broker không tự cô lập origin** nếu console vẫn có public IP, VPN route cũ hoặc direct management VLAN path. Với SSH, RDP hoặc API, kiểm tra **đúng giao thức, session lifetime và capability của sản phẩm**, không giả định proxy HTTP bảo vệ mọi loại kết nối.

## 26. Multi-site, hybrid cloud và đường quản trị qua transit

Hệ thống thường nằm ở nhiều vùng: on-prem data center, cloud VPC/VNet, chi nhánh, vendor site, DR region. Nếu **management và data networks** chia sẻ VPN/peering/transit mà không tách routes/policies, một site bị compromise có thể mở rộng quyền tới site khác.

~~~text
On-prem Data VRF --------- VPN/Transit -------- Cloud Data VPC
      |                                          |
  Application                                 Application

On-prem Mgmt VRF ------ Restricted Mgmt VPN ---- Cloud Mgmt Zone
      |                                          |
   Bastion/PAM -------------------------> Approved Admin APIs

Cross-plane routes:
  Default DENY unless a precise exception is approved.
~~~

### Các quyết định cần thống nhất

1. **CIDR planning:** quản trị và dữ liệu có trùng CIDR giữa các site không?
2. **VRF/route propagation:** BGP route advertisements có vô tình leak management prefixes sang data VRF không?
3. **VPN identity:** peer/tunnel được xác thực; ai được dùng route bên trong tunnel?
4. **Cloud IAM/SG:** admin API và workload data được cho đúng principals nào?
5. **Transit/peering:** đường nào kết nối mạng vendor và management, đâu là firewall enforcement point?
6. **DNS/split horizon:** management hostnames có resolve từ data network ngoài ý định không? Không dùng DNS làm firewall.
7. **Failover:** DR route/backup circuit có chính sách tương đương đường active không?
8. **Evidence:** có flow logs, route snapshots và policy version từ cả hai đầu không?

### Không “hợp nhất management” chỉ bằng một route

Một hub quản trị tập trung có thể giúp chính sách nhất quán, nhưng **hub compromise** có blast radius lớn. Cần segmentation nội bộ theo tenant/site, least privilege, session controls và HA. Dù đường truyền là private link/VPN, nó vẫn có thể vận chuyển **snapshot/exports** tới vùng ngoài quyền nếu không có data governance.

## 27. IPv4, IPv6, NAT và đường ngoài thiết kế

Khi tách subnet quản trị **chỉ bằng IPv4 firewall**, phải kiểm tra xem thiết bị có **IPv6** hoặc DNS AAAA records tạo đường khác không.

~~~text
Data workload:
  IPv4 route -> security firewall -> MGMT IPv4 DENY
  IPv6 route -> alternate gateway  -> MGMT IPv6 ???
~~~

**::/0** và **0.0.0.0/0** thuộc hai address families khác nhau; một rule IPv4 không tự chặn mọi IPv6 flow. Với môi trường dual-stack:

- Ghi **v4/v6 addresses, routes, firewall rules, NAT64/DNS64 và CNI** theo từng plane.
- Xác minh **BMC, admin API, control endpoints** có IPv6 reachable ngoài ý định không.
- Kiểm tra **ICMPv6** theo type/code cần thiết cho hoạt động IPv6, không chặn tất cả.
- Xác định NAT/proxy có thay **source identity/IP** ở điểm đánh giá policy không.
- Test flow **DATA→MGMT DENY** và **BASTION→MGMT ALLOW** ở cả hai families nếu triển khai.
- Với private DNS, không suy việc hostname không resolve từ data zone nghĩa IP không thể reachable.

**Bật IPv6 hoặc thay NAT/route** là một sự kiện cần security review lại, không chỉ một thay đổi “network optimization”.

## 28. Routing security và lỗi route leak giữa các plane

Phân tách VRF/subnet có thể bị phá bởi **route leaking, route redistribution sai, default route không mong muốn, static route tạm và cloud transit attachments**.

### Ví dụ minh họa

~~~text
Desired:
  DATA VRF: route to app subnets only
  MGMT VRF: route to management devices
  Inter-VRF: only admin proxy -> specific mgmt targets

Unexpected change:
  Management 10.250.0.0/16 advertised into DATA VRF
  Existing broad ACL permits traffic

Result:
  Data workloads may reach privileged endpoints
~~~

### Kiểm soát

| Tầng | Biện pháp |
|---|---|
| **Route policy** | Prefix filters, route tags/communities, approved import/export |
| **VRF separation** | Chỉ leak những prefixes có lý do, qua firewall nếu cần |
| **Firewall** | Explicit DATA→MGMT DENY ngay cả khi route bất ngờ tồn tại |
| **Change review** | Phê duyệt route propagation, transit, peering và VPN changes |
| **Monitoring** | Cảnh báo management prefixes xuất hiện ở data route tables |
| **Validation** | Test từ data source và từ bastion sau routing changes |

**Route hiện diện là điều kiện cần của network reachability nhưng không có nghĩa kết nối được phép**. Thiết kế tốt có **defense in depth**: không chỉ tin VRF, mà còn firewall, endpoint identity và admin authorization.

## 29. Nguồn phụ trợ và đường monitoring cần hạn riêng

Một hệ thống monitoring có thể được cho phép thu thập metrics/logs từ cả data và management zones. Nếu collector có quyền **đọc cấu hình nhạy cảm hoặc thực hiện remote commands**, nó có thể trở thành một điểm pivot khi bị compromise.

~~~text
Data Agents -----------\
                        >---- Telemetry Ingest Gateway
Mgmt Agents -----------/                |
                                        v
                                 Log/Metric Storage
                                        ^
                                        |
                                  Query/Search UI
                                   (PAM/RBAC)
~~~

### Tách ba loại traffic monitoring

1. **Push telemetry:** agent gửi events/metrics/traces tới ingestion endpoint, chỉ quyền gửi.
2. **Pull monitoring:** collector kết nối tới target trên port hẹp, chỉ quyền đọc.
3. **Control/management of monitoring:** operator sửa agent config, rules, queries, retention hoặc export; cần management policy riêng.

### Những dữ liệu nhạy cảm trong telemetry

Logs có thể chứa **access token, IP addresses, usernames, request bodies, stack traces, database queries hoặc customer IDs**. Bảo vệ ingestion không đủ nếu mọi operator đều có quyền **search/export**. Cần:

- Masking/redaction tại nguồn và collector.
- Identity/tenant-aware access cho query/export.
- Giới hạn retention và truyền dữ liệu tới đúng vùng/account.
- Audit mọi quyền thay đổi agent/collector và tải log.
- Không cấp monitoring agent **cluster-admin** nếu chỉ cần đọc một tập metrics.

**Đường monitoring thường kết nối nhiều zones; phải kiểm soát như một integration có rủi ro**, không dùng quy tắc blanket “monitoring trusted any/any”.

## 30. Egress/DLP policy cho cả data plane và management plane

Một hệ thống chỉ chặn **data subnet → Internet** mà cho **bastion → Internet any** có thể còn đường thất thoát thông qua phiên quản trị hoặc automation.

| Nguồn | Loại dữ liệu | Đích được phép | Chặn gì? |
|---|---|---|---|
| **Application workload** | Transaction/API payload | Approved partner/payment APIs | Arbitrary SaaS, unapproved DNS/DoH |
| **DB backup agent** | Database snapshots | Approved immutable repository/account | External bucket, personal SaaS |
| **Admin bastion** | Commands/log files nhỏ | Target management endpoints, approved update repos | Arbitrary file-sharing, unmanaged SSH forwarding |
| **Logging agent** | Logs/traces | Approved telemetry ingest endpoint | Internet collection endpoints ngoài quyền |
| **SIEM operator** | Search results/export | Approved investigation process | Unapproved export recipients |
| **Cloud deployment automation** | Config/artifacts | Approved control APIs/artifact repos | Unapproved cloud account/region |
| **BMC gateway** | Control/virtual media | Approved BMC endpoints and update service | General application subnets/Internet |

### Port-only không đủ

Cả **database export, management API và file-sharing SaaS** có thể chạy trên **TCP/443**. Chặn hoặc mở một cổng chỉ phân biệt một phần transport. Để ngăn data loss, cần **destination/tenant/resource authorization, proxy/DLP theo khả năng, application policy và cloud IAM**.

### TLS inspection có giới hạn và ràng buộc

Một HTTPS proxy không terminate traffic thường không xem được payload; nếu terminate TLS để DLP phải có **phạm vi pháp lý/riêng tư, CA key protection, certificate validation, ranh giới logs, protocol coverage và exceptions** rõ ràng. Không cài CA trái phép hoặc tắt TLS verification. Với data plane mã hóa end-to-end, content-aware DLP có thể phù hợp hơn ở **ứng dụng/endpoint**.

## 31. Mạng quản trị cần HA nhưng không được fail open

Một management plane tách biệt mà không có **đường khôi phục** có thể khiến đội vận hành không sửa được sự cố. Ngược lại, tự động mở đường từ production data zone khi bastion hỏng có thể làm mất tất cả giá trị phân tách.

### Failure domains

| Failure | Nguy cơ | Thiết kế dự phòng |
|---|---|---|
| **Bastion/PAM instance hỏng** | Admin không vào được host | HA bastion, session brokering redundancy |
| **Admin IdP/MFA lỗi** | Không cấp phiên mới | Resilient IdP và break-glass được phê duyệt |
| **OOB switch/uplink lỗi** | Không tới BMC | Redundant OOB path theo mức yêu cầu |
| **Management DNS/PKI lỗi** | Admin TLS/SSH/cert fail | Protected resolvers/issuers, short-lived cache có giới hạn |
| **VRF/firewall rule lỗi** | Lockout hoặc route leak | Tested rollback/console access |
| **Cloud region hỏng** | Console/API hoặc collector không ở đúng vùng | Regional failover, DR admin path |
| **Log collector down** | Mất khả năng audit/forensic | Buffer/backpressure/alert, policy cho privileged actions |
| **Ransomware data plane** | Không thể dùng đường in-band bình thường | OOB được cô lập và tested recovery |

### Fail closed

Nếu **policy decision, user identity hoặc device posture không xác minh được**, hệ thống quản trị nhạy cảm nên **không tự cấp quyền mới**, nhưng phải có cách khôi phục đã được lên kế hoạch. **Fail closed không đồng nghĩa cắt vĩnh viễn khả năng quản trị**; nó yêu cầu HA, hỗ trợ recovery và break-glass chính danh.

### Không tạo kênh bypass cố định

Một đường “emergency SSH from any corporate subnet” tồn tại mọi ngày có thể là lỗ hổng vĩnh viễn. Nếu thật sự cần khôi phục khẩn, dùng **dedicated OOB, limited source, sealed credential/dual approval và audit**.

## 32. Break-glass: lối cứu hộ cũng phải có ranh giới

**Break-glass access** là phương án có kiểm soát để lấy lại quyền vận hành khi danh tính/PAM/network bình thường thất bại.

~~~text
Incident declared
       |
  Approved emergency authority
       |
  Dual control / vault access
       |
  Dedicated OOB / local console
       |
  Target-specific privileged action
       |
  Record evidence + revoke/rotate
       |
  Post-incident review
~~~

### Quy tắc thực tế

1. Ai có quyền **kích hoạt**, ai phê duyệt và thời hạn tối đa?
2. Truy cập **tài sản nào**, chỉ các thao tác nào được phép?
3. Kênh truy cập có **độc lập với sự cố chung** (IdP, data network, power, DNS) đủ mức không?
4. Credential/khóa khẩn cấp được **lưu ký** ở đâu và theo cơ chế nào?
5. Có thể **audit offline hoặc lưu bản ghi sau khi phục hồi** mà không lộ secret không?
6. Sau sự cố, có **rotate/revoke**, xóa temporary routes/firewall grants và kiểm thử không còn bypass không?
7. Có diễn tập recovery được phê duyệt với **test environment** không?

Không giữ public management interface luôn mở như một dạng break-glass. Và không ghi credential nhạy cảm vào runbook chia sẻ chung. **Nếu sử dụng tài khoản khẩn, hậu kiểm và khôi phục policy chuẩn là một phần bắt buộc của hoàn tất incident**.

## 33. Policy as Code, quyền sửa cấu hình và drift

Phân tách management/data chỉ đáng tin khi **desired policy** và **effective runtime policy** trùng nhau, và người có quyền sửa chúng không quá rộng.

### Mẫu security intent (không phải syntax triển khai)

~~~yaml
policy_id: segregate-mgmt-data-v1
environment: staging
owner: network-security
zones:
  data:
    cidrs: ["10.20.0.0/16"]
  management:
    cidrs: ["10.250.0.0/16"]
  admin_entry:
    cidrs: ["10.251.0.0/24"]
baseline:
  data_to_management: deny
  internet_to_management: deny
  admin_to_management: deny_except_explicit
allow_flows:
  - id: admin-ssh
    source_identity: approved-bastion
    destination: approved-linux-admin-hosts
    protocol: tcp
    destination_port: 22
    requires: ["mfa", "jit", "session_audit"]
  - id: app-db
    source_identity: approved-app
    destination: approved-db
    protocol: tcp
    destination_port: 5432
exceptions:
  require_owner: true
  require_expiry: true
validation:
  positive_tests: required
  negative_tests: required
  ipv6_review: required
~~~

Đây là **schema học tập**, không phải file để nạp trực tiếp vào cloud provider, CNI hay firewall. Những trường **source_identity** và **requires** chỉ có tác dụng nếu có enforcement point thực sự triển khai logic tương ứng.

### Những trường hợp CI/security review phải phát hiện

| Dấu hiệu | Rủi ro |
|---|---|
| **DATA→MGMT any/any** | Phá vỡ segmentation |
| **Management default route đi Internet không kiểm soát** | Admin egress/DLP bypass |
| **Unrestricted VPN route to OOB** | Vendor/laptop di chuyển ngang |
| **Wide ClusterRole/Cloud IAM for app** | App có thể sửa ranh giới của chính nó |
| **Overlapping CIDRs/route redistribution** | VRF leak, wrong destination |
| **IPv6 policy missing** | Data zone có đường v6 chưa kiểm soát |
| **Temporary rule không có expiry** | Exception thành quyền thường trực |
| **Unmanaged BMC/console** | Mất asset inventory và truy cập không audit |
| **Certificate/SSH key reuse** | Một credential mở nhiều planes |
| **Missing negative tests** | Không chứng minh direct management path bị chặn |

### Change control

Những thay đổi **route, VRF import/export, SG/NACL, Kubernetes NetworkPolicy, cloud IAM, BMC connectivity, PAM roles, TLS trust và DNS** đều có thể làm thay đổi ranh giới thực tế. Policy phải có **owner, reviewer, canary/staging tests, impact analysis, rollback và cảnh báo drift**.

Không auto-revert một quy tắc đang được kích hoạt theo **incident response** nếu chưa kiểm tra ticket/owner. Nhưng sau khẩn cấp phải có quy trình **gỡ quyền tạm và retest**.

## 34. Telemetry: chứng minh ai đi đường nào

Quan sát phải trả lời được: **ai đã truy cập gì, từ đường nào, quyền nào cho phép, có đổi cấu hình hay xuất dữ liệu không?**

### Các loại bằng chứng

| Nguồn | Có thể chứng minh | Giới hạn |
|---|---|---|
| **Switch/router route/VRF config** | Bảng định tuyến, interfaces, import/export | Không cho biết user danh tính trên API |
| **Firewall/SG/NACL logs** | Một số flow/decision ở boundary | Thiếu content/tenant và có thể sampling |
| **Bastion/PAM audit** | User/asset/session/JIT grants | Không bao phủ direct bypass hoặc automation không qua bastion |
| **Cloud API audit** | Principal sửa SG/IAM/instance/snapshot | Không thấy mọi data-plane packet |
| **Kubernetes API audit** | Principal thay Pod/NetworkPolicy/Secret/Role | Không chứng minh Pod-to-Pod policy enforced |
| **BMC/console audit** | Đăng nhập/power/virtual media theo khả năng | Tùy vendor; có thể thiếu bối cảnh user từ PAM |
| **DNS/PKI logs** | Resolver queries và certificate issuance | Chưa chứng minh ứng dụng được phép gửi dữ liệu |
| **Proxy/SSE/DLP events** | Destination/tenant/upload policy khi hỗ trợ | Không nhìn traffic bypass hoặc opaque protocols |
| **App/DB audit** | Business action, export/snapshot/query | Không tự chỉ ra network route |

### Log giả lập đã hạn dữ liệu

~~~text
timestamp=2026-11-28T16:00:00+07:00
environment=staging
policy_version=mgmt-data-seg-v1
source_zone=DATA
source_workload=checkout-api
destination_zone=MANAGEMENT
destination_asset=server-admin-02
destination_port=22
transport=tcp
enforcement_point=vrf-firewall
decision=DENY
reason=source_zone_not_authorized
request_id=example-req-037
private_key=[NOT_COLLECTED]
user_session_token=[NOT_COLLECTED]
payload=[NOT_COLLECTED]
~~~

Đây là **log minh họa**, không đại diện format của thiết bị thật. DLP log có thể cần bổ sung **data classification/recipient tenant/action**, nhưng không được thu thập toàn bộ payload nhạy cảm chỉ để phục vụ dashboard.

### Cảnh báo thiết yếu

- New route cho **management prefix** xuất hiện trong data VRF.
- App workload phát sinh **TCP/22, TCP/3389 hoặc HTTPS tới admin endpoint** không thuộc inventory.
- Cloud IAM/service principal của workload được gán quyền **modify firewall/routes**.
- Bastion bắt đầu kết nối **unapproved Internet/SaaS destinations**.
- BMC nhận phiên ngoài khung thời gian/vùng nguồn cho phép.
- Backup/export dữ liệu tới **account/tenant/repository ngoài danh mục**.
- Kết nối từ **dual-stack IPv6 path** bỏ qua điểm kiểm soát v4.
- JIT grant hết hạn nhưng session chưa đóng hoặc tài khoản vẫn còn quyền.
- Security control configuration drift/disabled audit logs.

**Không thấy log không phải bằng chứng không có đường truy cập.** Trước khi tuyên bố ranh giới an toàn, kiểm tra coverage của sensors và negative tests từ từng nguồn thích hợp.

## 35. Runbook khi quản trị bị lỗi hoặc nghi có đường bypass

### Bước 1 — Phân loại

1. Tài sản liên quan: **app, DB, hypervisor, network device, BMC, Kubernetes API, cloud API hay backup**?
2. Source **principal/device/workload**, zone, interface, IPv4/IPv6 và vị trí network?
3. Destination IP/FQDN/asset, protocol/port, TLS/SSH identity và expected access?
4. Lỗi là **DNS, TCP timeout/refused, authentication failure, authorization DENY, backend 5xx hay policy misroute**?
5. Có vừa thay đổi route/VRF/firewall/IAM/PAM/PKI/agent, site VPN hay cloud transit không?

### Bước 2 — Xác định có đúng đường quản trị hay không

~~~text
Admin cannot reach target
              |
      Identity/JIT valid?
        /             \
       No             Yes
       |               |
     IdP/PAM       DNS/address correct?
                       /        \
                      No        Yes
                      |          |
                   DNS zone    Network route?
                                 /        \
                                No        Yes
                                |          |
                             VRF/VPN     Firewall allows?
                                          /       \
                                         No       Yes
                                         |         |
                                    SG/ACL/CNI   TLS/SSH/target auth?
                                                  /         \
                                                 No         Yes
                                                 |           |
                                             Cert/AAA     Target/app issue
~~~

### Bước 3 — Nếu phát hiện data→management traffic trái quyền

- Xác định **source workload/identity, dest asset, source/route after NAT, control API**.
- Kiểm tra **effective route and firewall policy** ở đúng enforcement point, không chỉ policy file.
- Nếu có quyền quản trị bị lạm dụng, bảo vệ **forensic evidence**, cô lập source theo incident playbook và thu hồi credential.
- Tìm **đường tương đương**: IPv6, VPN/peering, NodePort/hostNetwork, legacy admin endpoint, OOB shared network.
- Nếu bị route leak, phối hợp network owner khôi phục **VRF route policy + firewall guardrails** có rollback.
- Theo dõi **data movement/export events** từ management/backup consoles; không chỉ đếm SSH attempts.

### Bước 4 — Nếu admin bị khóa khỏi hệ thống hợp lệ

Không mở **DATA→MGMT any/any** để khôi phục nhanh. Xác định liệu có thể sửa qua **HA bastion, console/secure OOB, break-glass được phê duyệt hoặc rollback management policy**. Đảm bảo ghi lại ai mở quyền tạm, TTL và hậu kiểm negative tests.

### Bước 5 — Nghiệm thu

Một sự cố chỉ được coi là xử lý ổn khi:

1. **Authorized admin→target ALLOW** qua đường có identity/JIT/authorization đúng.
2. **Data workload→management target DENY** từ nguồn đại diện.
3. **Internet/vendor→BMC/console DENY** ngoài các ngoại lệ đã duyệt.
4. **Application data path và backups hợp lệ vẫn hoạt động**.
5. **Management egress/file export** không có đường DLP bypass.
6. Các đường **HA/DR, IPv4/IPv6, proxy và VPN** được đối chiếu trong phạm vi triển khai.
7. **Temporary exceptions** đã được thu hồi hoặc có expiry/owner rõ.

## 36. Case study 1: App bị compromise vẫn đến được BMC qua route leak

**Bối cảnh giả định:** Một data center phân tách các server application vào **VRF DATA** và các thiết bị BMC vào **VRF MGMT**. Sau thay đổi routing phục vụ bảo trì, một prefix management bị quảng bá từ MGMT sang DATA. Firewall inter-VRF đang có một rule rộng “allow internal corporate networks TCP/443” tạo trước đó.

### Trước khi sai

~~~text
APP Zone 10.20.10.0/24
      |
      X no route/authorized flow to
      |
MGMT BMC 10.250.10.0/24 TCP/443
~~~

### Sau khi sai

~~~text
APP Zone
      |
      | Inter-VRF route to MGMT appears
      |
      | Broad firewall "corporate TCP/443 ALLOW"
      v
MGMT BMC Admin HTTPS
~~~

**Tác động:** Một workload bị chiếm quyền có thể có khả năng kết nối đến endpoint BMC/console vốn không được phép tiếp cận. Việc biết TCP/443 reachable **không tự chứng minh attacker có quyền BMC**, nhưng bề mặt tấn công và cơ hội dò thử xác thực đã tăng đáng kể.

### Phân tích nguyên nhân

1. Chỉ tin **VRF route separation** mà thiếu explicit deny tại boundary.
2. Rule TCP/443 mở theo “corporate CIDR” bao gồm source data zone.
3. Monitoring route policy không cảnh báo **MGMT prefixes xuất hiện trong DATA VRF**.
4. Negative test **DATA→BMC DENY** không chạy sau change.

### Sửa theo lớp

- Khôi phục **VRF route import/export policy** và loại route không được duyệt.
- Đặt **DATA→MGMT explicit DENY** phù hợp ngay cả khi route lộ.
- Hạn **MGMT HTTPS/BMC** chỉ từ approved bastion/OOB gateway với authentication và MFA/PAM.
- Kiểm tra BMC credentials, firmware và access logs trong khoảng thời gian có route leak.
- Test **admin→BMC ALLOW** và **app→BMC DENY** từ nguồn thực, cả IPv4/IPv6 nếu có.
- Thêm alert route-drift và bắt buộc security review khi thay prefix export.

**Bài học:** Phân tách VRF cần đi kèm **firewall, endpoint authentication và giám sát route leak**. Một rule “443 nội bộ” có thể vô tình mở **giao diện quản trị** chứ không chỉ web ứng dụng.

## 37. Case study 2: Cloud workload có IAM quyền sửa firewall dù mạng đã tách

**Bối cảnh giả định:** Một cloud VPC có subnet ứng dụng và subnet quản trị tách bằng SG. Deployment automation sử dụng một role được gắn nhầm cho **application Pod**, cho phép thao tác sửa một tập network policies/security groups.

### Tình trạng thiết kế

~~~text
Cloud Data Subnet
  checkout-api Pod
  egress ACL: no management subnet access

Cloud Control API
  accessible via authorized HTTPS endpoint

Workload identity:
  granted permission to change selected SG rules
  (not needed for business logic)
~~~

Một kẻ tấn công đã có quyền thực thi trong workload có thể **sử dụng credential mà workload được cấp để yêu cầu control-plane thay firewall**. Đường DATA→MGMT bị hạn ở L3/L4 không tự giải quyết nguy cơ **control-plane privilege escalation** này.

### Phân tích nguyên nhân

- Workload và deployment automation **dùng chung hoặc cấp thừa cloud role**.
- Policy chỉ theo CIDR/port, không xét **caller permissions trên cloud APIs**.
- Cloud control API được coi là “HTTPS 443 hợp lệ” mà thiếu service/action scoping.
- Không có alert khi một application principal thay SG/route.

### Thiết kế khắc phục

1. Tách **runtime workload role** khỏi **deployment/change role**.
2. Loại quyền **modify SG/routes/IAM** khỏi ứng dụng nếu không cần.
3. Dùng short-lived credentials, permission boundaries/organization guardrails và approval cho thay network.
4. Log control-plane actions với **principal, resource, event, policy version, change ticket**.
5. Đặt egress controls tới cloud management APIs phù hợp, nhưng **IAM vẫn là lớp quyết định quan trọng**.
6. Thực hiện test **runtime role không có quyền modify firewall** bằng công cụ quyền đọc hoặc môi trường lab đã được phê duyệt.

**Bài học:** Đường API quản trị có thể dùng **TCP/443 như một dịch vụ bình thường**; tách network không thay thế least privilege cho cloud control-plane IAM.

## 38. Case study 3: Bastion được quản trị an toàn nhưng thành đường xuất dữ liệu

**Bối cảnh giả định:** Tất cả SSH tới server phải qua bastion/PAM có MFA. Tuy nhiên, bastion có outbound Internet TCP/443 và SSH port forwarding/file transfer không hạn chế. Một phiên bảo trì hợp lệ được cấp quyền đọc logs chứa dữ liệu nhạy cảm.

### Đường không mong muốn

~~~text
Operator
   |
   | MFA / JIT
   v
Bastion
   |
   +-- SSH to server (approved)
   |
   +-- file-transfer / tunnel to arbitrary external target
       (not separately governed)
~~~

Không nhất thiết có hành vi tấn công: một kỹ sư cũng có thể **vô tình** xuất log chứa PII sang nơi chia sẻ không được duyệt. Mạng quản trị có đúng MFA nhưng **luồng dữ liệu xuất ra** chưa có DLP.

### Các nguyên nhân

- Chính sách chỉ kiểm tra **ai được login**.
- Không kiểm soát **file transfer, clipboard, proxy forwarding hoặc API export**.
- Bastion có thể đi ra **mọi SaaS TCP/443**, không destination allowlist.
- PAM session recording có nhưng không có phân loại dữ liệu/recipient policy.

### Khắc phục

- Hạn egress của bastion tới **management targets và approved artifact/log destinations**.
- Quy định file transfer theo **business need, approval, data class và retention**.
- Giảm quyền truy cập logs cho những người không cần; redact secrets/PII tại nguồn.
- Đánh giá SSH forwarding/remote clipboard, có policy/giám sát khi cần.
- Kết hợp PAM audit với **proxy/DLP/app logs**, tránh tải payload thật vào nơi điều tra không cần thiết.
- Test **SSH admin ALLOW** và **unapproved file-sharing destination DENY** bằng dữ liệu giả ở staging.

**Bài học:** Management plane cũng là **đường dữ liệu**, nên cần quản trị egress và DLP như data plane, đôi khi nghiêm hơn vì có quyền nhạy cảm.

## 39. Case study 4: OOB có dây riêng nhưng trùng credential và cùng mạng VPN

**Bối cảnh giả định:** Một doanh nghiệp lắp dedicated BMC NIC và OOB switches. Tuy nhiên, VPN nhân viên có route mặc định tới toàn **10.250.0.0/16** gồm OOB, tất cả BMC dùng cùng credential quản trị được chia sẻ.

### Vì sao đây chưa phải OOB an toàn?

~~~text
Employee Laptop
       |
      VPN
       |
 Management / OOB 10.250.0.0/16
       |
  BMC A / BMC B / BMC C
  (shared credentials)
~~~

Tách NIC giúp tránh một số failure domain của production network nhưng **không tạo ranh giới identity hoặc source access** nếu VPN cho mọi laptop đi vào OOB.

### Biện pháp

1. Chỉ **dedicated OOB gateway/PAM** có route tới BMC; user VPN không được full reachability.
2. Mỗi BMC có **unique credential/certificate**, vault/rotation, không sử dụng default passwords.
3. Bật MFA/AAA ở access gateway và JIT quyền cho thiết bị cụ thể.
4. Áp **management firewall/default deny** theo source/destination và API endpoints.
5. Kiểm tra **firmware, audit, virtual media và console session recording** phù hợp.
6. Test từ **workstation, VPN client, app subnet** đều DENY tới BMC; chỉ gateway hợp lệ ALLOW.

**Bài học:** **Tách vật lý** giảm rủi ro nhưng **credential reuse và broad VPN routes** vẫn có thể mở toàn bộ management plane.

## 40. Case study 5: Backup repository nằm ngoài trust boundary

**Bối cảnh giả định:** Một backup controller được xem là “hạ tầng quản trị tin cậy”. Agent từ production database được cho phép upload snapshots tới object storage qua private endpoint. Nhưng policy chỉ kiểm tra **đúng service endpoint TCP/443**, không giới hạn account/bucket/tenant của destination.

### Dòng dữ liệu

~~~text
Production database
      |
  Backup agent
      |
  Private object-storage endpoint TCP/443
      |
      +-- Corporate backup account (approved)
      |
      +-- External/incorrect account (not approved)
~~~

Private connectivity không có nghĩa dữ liệu nằm trong account/tenant của công ty. Nếu credential hoặc backup job configuration bị lạm dụng, tổ chức có thể **mất dữ liệu qua đường “backup hợp lệ”** mà firewall vẫn ghi ACCEPT.

### Thiết kế đúng

- IAM/policy ràng buộc **đúng account, bucket, region và object operations**.
- Backup identity chỉ có quyền cần thiết, hạn restore/delete/export.
- Mã hóa in transit/at rest, key management và immutability.
- Ghi **destination tenant/resource ID** trong backup audit khi khả năng cho phép.
- Tách **backup controller management path** với **backup payload path** và kiểm tra data movement.
- Test **approved repository ALLOW**, **cross-account destination DENY** bằng test bucket và test data.

**Bài học:** Phân tách management/data không nên xếp mọi backup traffic vào “control trusted”; **data destination authorization** quyết định phòng chống thất thoát.

## 41. Case study 6: Đường dự phòng DR mở quản trị từ data zone

**Bối cảnh giả định:** Đường quản trị chính tới data center dùng một VPN riêng, firewall hạn nguồn từ PAM. Khi VPN chính ngắt, một static route dự phòng được kích hoạt qua **đường transit chung với data traffic**. Firewall trên đường DR thiếu cùng bộ policy, vô tình cho data subnet gọi management HTTPS.

### Khi đường chính khỏe

~~~text
Admin -> PAM -> Mgmt VPN -> Firewall -> Mgmt targets
App subnet ---------------------------X
~~~

### Khi failover

~~~text
Admin -> Transit Shared -> DR Router -> Mgmt targets
App subnet -> Transit Shared -------?-> Mgmt targets

Unverified backup path can change reachability.
~~~

### Điều tra và khắc phục

1. Xác định **active next hop và route priorities** khi failover.
2. Đối chiếu effective **SG/ACL/firewall/VRF import/export** ở cả primary/secondary paths.
3. Không tạo rule “internal any/any” tạm kéo dài trên DR gateway.
4. Có **mã cấu hình thống nhất** và kiểm tra drift giữa hai vùng, không giả định cùng tên policy là cùng semantics.
5. Diễn tập **failover ALLOW admin JIT + DENY app→management**, có stop conditions và rollback.
6. Ghi incident ticket, rule owner và làm rõ khả năng fallback khi IdP/PAM cũng lỗi.

**Bài học:** Ranh giới an ninh phải được giữ khi **HA, DR, failover và maintenance** chứ không chỉ trong trạng thái hoạt động bình thường.

## 42. Bài thực hành an toàn: vẽ ranh giới và xác minh route/ACL

Bài lab có thể làm **trên giấy** hoặc trong hệ thống **staging/isolated lab được chủ sở hữu cấp quyền**. Chỉ dùng các thao tác đọc cấu hình hoặc kết nối synthetic test được phê duyệt; không truy cập BMC/SSH/admin endpoint ngoài quyền, không tạo lưu lượng scan, không disable firewall và không thay route của production.

### 42.1. Mô hình lab

~~~text
DATA Zone:
  namespace/shop-prod
  app checkout-api         10.20.10.20
  data-db                  10.20.20.30

MGMT Zone:
  bastion                  10.250.1.10
  server-admin             10.250.20.20
  BMC / OOB device         10.250.10.50

BACKUP Zone:
  approved repository      10.240.10.10

Admin:
  managed workstation ---> ZTNA/PAM ---> bastion

Expected:
  checkout -> data-db TCP/5432           ALLOW
  bastion -> server-admin TCP/22         ALLOW after JIT
  checkout -> server-admin TCP/22        DENY
  checkout -> BMC TCP/443                DENY
  general workstation -> BMC            DENY
  approved backup agent -> repository   ALLOW by role
  backup -> unknown tenant              DENY
~~~

Các địa chỉ là **minh họa RFC 1918**. Nếu thực hiện lab E2E, phải đổi thành endpoint thuộc môi trường được phê duyệt và có owner; **không xem việc một kết nối timeout là bằng chứng duy nhất firewall đã chặn đúng**.

### 42.2. Đánh giá logic từ bảng

| Test nguồn | Đích | Dự kiến | Lý do |
|---|---|---|---|
| App checkout | Database TCP/5432 | ALLOW | Dependency nghiệp vụ |
| App checkout | SSH server-admin TCP/22 | DENY | Data không được đi management |
| App checkout | BMC HTTPS TCP/443 | DENY | 443 không phải luôn app HTTPS |
| Bastion JIT identity | SSH server-admin TCP/22 | ALLOW | Đường quản trị được duyệt |
| Workstation VPN thường | SSH server-admin TCP/22 trực tiếp | DENY | Phải qua ZTNA/PAM |
| Bastion | Arbitrary file-sharing HTTPS | DENY | Tránh egress/DLP bypass |
| Backup agent | Approved backup repository | ALLOW | Data movement theo scope |
| Backup agent | External cloud tenant | DENY | Không đủ quyền tài nguyên |

### 42.3. Lệnh xem route/interface Linux (chỉ đọc)

~~~bash
# Chỉ chạy trên host lab được phê duyệt.
ip address show
ip route show
ip -6 route show
ip rule show

# Route lookup không tự gửi packet đến đích:
ip route get 10.250.20.20
~~~

Các lệnh này cho biết **địa chỉ, route/rule cục bộ** và next hop dự kiến cho một địa chỉ. Chúng **không thể xác nhận toàn bộ inter-VRF firewall, VPN/SDN path hoặc host-side authorization**. Với VRF thực, xem route table/VRF bằng công cụ của platform được cấp quyền; không giả định lệnh trên phản ánh mọi flow.

### 42.4. Lệnh đọc Kubernetes (nếu lab triển khai trên K8s)

~~~bash
kubectl config current-context
kubectl get namespaces --show-labels
kubectl -n shop-prod get pods -o wide --show-labels
kubectl -n shop-prod get networkpolicy
kubectl -n shop-prod get networkpolicy -o yaml
kubectl get serviceaccounts -n shop-prod

# Không xuất Secret values hoặc token ra log.
kubectl auth can-i create networkpolicies -n shop-prod
kubectl auth can-i get secrets -n shop-prod
~~~

**kubectl get** kiểm tra resource trong Kubernetes API; không chứng minh CNI đang thực thi policy. **kubectl auth can-i** hỗ trợ đánh giá authorization theo identity/context hiện tại, không thay phép thử admission, network reachability hay mọi quy tắc khác.

### 42.5. Xem AWS VPC ACL/SG/route khi có quyền đọc

~~~bash
# ID dưới đây là placeholder, không phải tài nguyên thật.
# Thay bằng ID thuộc tài khoản lab khi đã được cho phép.
aws ec2 describe-security-groups \
  --group-ids sg-0123456789abcdef0 \
  --region ap-southeast-1

aws ec2 describe-network-acls \
  --network-acl-ids acl-0123456789abcdef0 \
  --region ap-southeast-1

aws ec2 describe-route-tables \
  --route-table-ids rtb-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Đọc các trường **outbound/inbound, protocol, port, source/destination CIDR, target attachment, route, NACL ordered rules và resource associations**. Đừng chỉ tìm một ALLOW rồi kết luận toàn path đã cho traffic.

### 42.6. Kiểm thử kết nối có phép

Nếu chủ dịch vụ có **test SSH/HTTPS endpoint** ở lab, dùng một công cụ probe được cấp quyền với giới hạn **một kết nối ngắn, không gửi credential, không thay đổi trạng thái** để xác nhận đường **admin ALLOW/data DENY**. Không có lệnh “curl tất cả IP management” trong lab này.

Một phép kiểm thử **chỉ đọc** với host public test app được phê duyệt có thể là:

~~~bash
# Chỉ chạy sau khi thay URL bằng endpoint thuộc lab có phép.
# Không dùng --insecure để bỏ TLS certificate verification.
curl --head --connect-timeout 3 --max-time 8 \
  --silent --show-error \
  https://approved-admin-test.example.test/
~~~

**Đây là ví dụ về thao tác HTTP read-only**, không phải bằng chứng chắc chắn của ranh giới SSH/BMC. Với đích management, test **đúng source, exact destination và enforcement point**, không dùng random public IP hoặc dò quét.

### 42.7. Phiếu nghiệm thu

~~~text
Lab ID:                MGMT-DATA-SEG-001
Timestamp/timezone:    [time]
Environment:           [authorized staging/lab]
Source principal:      [pseudonymous ID/service identity]
Source zone/host:      [DATA/ADMIN/OTHER]
Source interface/IP:   [verified]
Destination asset:     [asset ID and owner]
Destination zone/IP:   [verified]
Protocol/port:         [TCP/UDP/ICMP as applicable]
Expected route:        [VRF/next hop/firewall]
Observed route:        [read-only evidence]
Firewall decision:     [policy rule ID/ALLOW/DENY/UNKNOWN]
Identity policy:       [MFA/JIT/RBAC/mTLS if required]
Expected result:       [ALLOW/DENY]
Observed result:       [source and error/response]
Data movement:         [class/recipient/policy decision]
Backup/HA path:        [tested/not tested]
IPv4/IPv6:             [coverage]
Evidence:              [logs/trace, redacted]
Verdict:               [PASS/FAIL/INCONCLUSIVE]
Owner/change record:   [team/ticket]
~~~

**Nếu route không tồn tại**, kết quả không chứng minh firewall DENY; nó chỉ cho thấy đường không reachable trong trạng thái thử. Để nghiệm thu tường minh chính sách, nên có **cấu hình và telemetry của đúng enforcement point**, cộng thử ALLOW từ nguồn được phép và kiểm tra negative test tương ứng.

## 43. Ma trận nghiệm thu phân tách đường quản trị và đường dữ liệu

Bảng sau dùng **SEC-01 đến SEC-56** để kiểm tra cả chức năng, độ bền ranh giới và DLP. Một test có thể thuộc diện **NOT_APPLICABLE** nếu sản phẩm/kiến trúc không có thành phần đó; cần ghi lý do, không âm thầm bỏ qua.

| Test ID | Tình huống | Kỳ vọng |
|---|---|---|
| **SEC-01** | Application client gọi app qua public ingress | ALLOW theo ingress/app policy |
| **SEC-02** | App workload gọi DB theo contract | ALLOW theo service/DB identity |
| **SEC-03** | App workload gọi SSH management target | DENY tại đúng network boundary |
| **SEC-04** | App workload gọi BMC admin HTTPS TCP/443 | DENY dù cùng cổng HTTPS |
| **SEC-05** | Internet nguồn bất kỳ gọi BMC/console | DENY |
| **SEC-06** | Workstation thường gọi server-admin trực tiếp | DENY nếu policy bắt buộc bastion |
| **SEC-07** | Managed admin device vào ZTNA/PAM | ALLOW sau policy identity/MFA/posture |
| **SEC-08** | Admin thiếu JIT tới một host | DENY target/session |
| **SEC-09** | Admin có JIT tới đúng host | ALLOW chỉ trong grant scope |
| **SEC-10** | JIT grant hết hạn khi session còn mở | Thu hồi/terminate theo SLO |
| **SEC-11** | Admin thử host ngoài approval | DENY dù có bastion session |
| **SEC-12** | Bastion→server SSH host key mismatch | Reject wrong host identity |
| **SEC-13** | Bastion→admin HTTPS certificate invalid | TLS validation DENY |
| **SEC-14** | Vendor access ngoài khung thời gian | DENY theo TTL/approval |
| **SEC-15** | Vendor VPN có route tới toàn MGMT zone | Phát hiện và hạn scope |
| **SEC-16** | App VLAN có inter-VLAN route ngoài ý định | Firewall DATA→MGMT vẫn DENY |
| **SEC-17** | VRF DATA nhận nhầm MGMT prefix | Route-leak alert và negative test |
| **SEC-18** | Management route failover qua DR circuit | Same source/identity/ACL constraints |
| **SEC-19** | Mgmt IPv4 có policy đúng nhưng v6 đang mở | Phát hiện và đóng v6 bypass |
| **SEC-20** | ICMPv6/PMTUD cần thiết trên mgmt VPN | Lọc đúng type/code, không gây outage |
| **SEC-21** | BMC dùng credential mặc định/chia sẻ | Bị policy phát hiện và khắc phục |
| **SEC-22** | BMC có dedicated NIC nhưng OOB route rộng | Không kết luận đã isolated |
| **SEC-23** | OOB gateway mới được cấp quyền tới đúng BMC | ALLOW với MFA/JIT/audit |
| **SEC-24** | Virtual media/console operation ngoài phê duyệt | DENY hoặc cảnh báo theo policy |
| **SEC-25** | NMS đọc metrics switch qua approved protocol | ALLOW read-only |
| **SEC-26** | Monitoring credential thử sửa switch config | DENY |
| **SEC-27** | Router BGP/OSPF cần control traffic hợp lệ | Không chặn nhầm do nhầm control và management |
| **SEC-28** | Hypervisor management accessible từ VM tenant | DENY |
| **SEC-29** | VM runtime identity thử thay virtual switch/port group | DENY theo RBAC/IAM |
| **SEC-30** | Cloud app role thử modify SG/route | DENY nếu không thuộc business need |
| **SEC-31** | Cloud change role có approval sửa SG đúng scope | ALLOW và có audit |
| **SEC-32** | Private endpoint object storage trỏ sai account | IAM/resource policy DENY |
| **SEC-33** | Human operator dùng API management public ngoài policy | DENY hoặc brokered access đúng |
| **SEC-34** | Kubernetes Pod không phải controller gọi privileged API | Không có RBAC rights/thừa egress |
| **SEC-35** | K8s node kubelet/admin endpoint exposed to data Pod | DENY theo host/control protections |
| **SEC-36** | NetworkPolicy vừa được tạo nhưng CNI không enforce | Không kết luận PASS giả |
| **SEC-37** | Two NetworkPolicies cộng allow-all vào app Pod | Phát hiện additive union/mở quyền |
| **SEC-38** | Kubernetes default-deny chặn DNS dependency | Phát hiện đúng resolver path và sửa hẹp |
| **SEC-39** | BMC/host firewall sau DNAT/SNAT đổi source | Policy xác minh đúng effective source |
| **SEC-40** | Bastion thử Internet HTTPS không có business need | DENY qua egress policy |
| **SEC-41** | Bastion SSH forwarding tới unapproved destination | DENY/giám sát theo approved policy |
| **SEC-42** | Session copy file chứa synthetic restricted marker | DLP/action policy phù hợp |
| **SEC-43** | Remote desktop clipboard/drive redirection ngoài quyền | DENY/giới hạn |
| **SEC-44** | Backup agent ghi approved repository | ALLOW và repository identity đúng |
| **SEC-45** | Backup agent ghi external tenant/bucket | DENY theo cloud IAM/data policy |
| **SEC-46** | Backup restore/delete cần quyền cao | JIT/dual approval khi policy yêu cầu |
| **SEC-47** | Log ingestion từ app và mgmt agents | ALLOW đúng collector |
| **SEC-48** | Telemetry agent thử dùng admin log-search API | DENY |
| **SEC-49** | SIEM operator export logs ngoài approved workflow | DENY/audit theo data policy |
| **SEC-50** | User IdP/PAM outage | Fail closed new privileged grants; recovery tested |
| **SEC-51** | OOB gateway HA/failover | Khôi phục quản trị không mở data bypass |
| **SEC-52** | Break-glass activate và kết thúc | Dual control, TTL, audit, rotate/revoke |
| **SEC-53** | Temporary route/firewall exception hết hạn | Thu hồi, retest âm tính |
| **SEC-54** | Logs bị tắt/sampling không đủ | Coverage UNKNOWN, không kết luận safe |
| **SEC-55** | Policy IaC và runtime route/firewall khác nhau | Drift alert, owner review và remediation |
| **SEC-56** | Production change hậu kiểm primary/DR | Business ALLOW + forbidden access DENY |

### Tiêu chí phân loại

- **PASS:** đúng nguồn, đúng route/enforcement point và identity; luồng hợp lệ chạy, luồng ngoài quyền bị chặn và data movement theo chính sách.
- **FAIL:** một data workload vào được management endpoint ngoài quyền, admin không thể vào đường hợp lệ, hoặc có đường export/snapshot trái phép.
- **INCONCLUSIVE:** chưa biết effective route/firewall state, telemetry thiếu, CNI/host exception chưa xác minh, hoặc probe thất bại vì endpoint không hoạt động.
- **NOT_APPLICABLE:** sản phẩm/kiến trúc không có phần đó (ví dụ không dùng BMC riêng hoặc IPv6), đã được kiểm chứng và ghi bằng chứng.

**Mục tiêu là bảo vệ cả hai chiều:** **data path không biến thành admin path**, **admin path không biến thành kênh dữ liệu không được kiểm soát**. Tỷ lệ test ALLOW cao không đại diện chất lượng phân tách nếu không có negative tests.

## 44. Những hiểu nhầm và sai sót thường gặp

| Hiểu nhầm | Vì sao sai hoặc thiếu | Cách tiếp cận |
|---|---|---|
| “Data plane và control plane là một” | Chức năng truyền dữ liệu khác chức năng điều phối trạng thái | Phân loại theo vai trò từng flow |
| “Management plane luôn là control plane” | Nhiều admin API phục vụ vận hành/điều khiển; có thể giao nhau nhưng không đồng nhất | Xác định consumer và hành động |
| “Khác subnet là đã bảo mật” | Routing/firewall có thể cho any-to-any | Explicit zone ACL, identity, tests |
| “VLAN tạo firewall giữa mọi VLAN” | L3 routing có thể kết nối các VLAN | Inter-VLAN firewall và controls |
| “VRF không bao giờ leak route” | Import/export, BGP/static/transit có thể sai | Prefix filters + route monitoring |
| “Mọi control traffic phải chạy trên OOB” | BGP/OSPF hoạt động trên data/routing interfaces theo thiết kế | Phân biệt routing control với admin access |
| “Dedicated NIC là OOB an toàn” | Có thể chung switch/VPN/credentials | Tách failure domain và policy |
| “Mạng OOB không cần MFA vì không public” | Có thể có đường từ laptop/VPN/insider | Gateway MFA/JIT, credential hygiene |
| “BMC ít quan trọng hơn máy chủ production” | Có quyền power/console/firmware/virtual media | Bảo vệ BMC như tài sản đặc quyền |
| “Đổi cổng SSH là đã cách ly quản trị” | Port number không thay authentication/reachability | Source restrictions, PAM, host key verification |
| “HTTPS TCP/443 chỉ là web app” | Admin console/cloud API cũng dùng 443 | Destination identity, policy theo asset |
| “Một bastion là đủ, không cần host firewall” | Bastion compromise có thể pivot tới nhiều đích | Bastion egress ACL và target allowlists |
| “MFA lần đầu đảm bảo session luôn an toàn” | Session hijack/expiry/posture changes còn | JIT TTL, session revocation |
| “PAM session recording tự chặn data loss” | File transfer/export có thể vẫn diễn ra | DLP/data transfer policy riêng |
| “Có JIT quyền login thì được phép download mọi file” | Login permission khác data/action permission | App/DB/object-level authorization |
| “Vendor VPN có toàn management route cũng được vì có hợp đồng” | Source rộng gây lateral reachability | Asset-specific JIT and expiry |
| “VPN tunnel mã hóa rồi không cần xác thực host” | VPN identity khác endpoint identity | SSH/TLS/mTLS verification |
| “Mạng private cho phép bỏ SSH host key validation” | DNS/route/proxy sai có thể dẫn tới sai đích | Verify host identity đúng |
| “Monitoring là trusted nên cần any/any” | Collector có kết nối xuyên zones | Ingest/pull/admin roles tách biệt |
| “Syslog agent cần quyền query SIEM” | Push ingest khác search/export | Send-only identity |
| “Kubernetes namespace tự tách mạng quản trị” | Namespace là resource scope, không phải firewall | CNI NetworkPolicy + RBAC/host controls |
| “NetworkPolicy YAML là đã chặn packet” | CNI có thể không enforce hoặc hostNetwork bypass | Test actual enforcement |
| “Default-deny policy ghi đè mọi allow cũ” | NetworkPolicy chuẩn có additive semantics | Tính union mọi allow |
| “Pod chỉ cần gọi HTTPS nên cho TCP/443 mọi đích” | Cloud control APIs cũng chạy trên 443 | Destination/identity/actions |
| “K8s API server là một service bình thường” | Quyền thay resources/secrets/netpol rất nhạy cảm | API RBAC/IAM/control path riêng |
| “Cloud app role có thể chỉnh SG để tự khắc phục lỗi” | App compromise có thể mở policy boundary | Separate deployment/admin identity |
| “Private endpoint đồng nghĩa data thuộc đúng tenant” | Account/resource IAM vẫn có thể sai | Account/bucket/tenant authorization |
| “Backup là traffic quản trị nên không cần DLP” | Snapshot chứa nhiều dữ liệu nhạy cảm | Dedicated repository/data governance |
| “OOB data transfer không cần kiểm soát” | Virtual media/console có thể mang dữ liệu | Session/transfer controls |
| “Chỉ cần chặn traffic từ DATA vào MGMT” | Bastion/backup có thể xuất dữ liệu ra ngoài | Egress DLP trên management zone |
| “Admin được login host tức có quyền xuất DB” | Host access khác business/data authorization | Least privilege đến object/action |
| “Security Group cho 443 nghĩa kết nối chạy được” | Còn routes, NACL, host firewall, TLS | End-to-end flow validation |
| “Stateful và stateless return rules như nhau” | NACL stateless cần xét chiều phản hồi | Theo semantics từng firewall |
| “Đã chặn IPv4 thì IPv6 không thể bypass” | Các routes/address families độc lập | Dual-stack review/test |
| “DNS không resolve management hostname nghĩa không đến IP” | IP direct path có thể còn | Route/firewall independent of DNS |
| “Primary path an toàn thì failover cũng an toàn” | DR gateway/transit policy có thể khác | Test HA/DR negative flows |
| “Chặn tất cả admin routes sẽ tăng an toàn” | Có thể gây lockout không cứu được sự cố | HA/OOB/break-glass được duyệt |
| “Break-glass là public admin console luôn bật” | Tạo bypass thường trực | Dual approval, limited OOB, TTL |
| “Policy-as-code validate YAML là đủ” | Runtime drift và enforcement gaps còn | Review effective configurations |
| “Không thấy BMC log nghĩa không ai truy cập” | Log coverage/vendor features có thể thiếu | Combined PAM/firewall/device audit |
| “Một timeout tới BMC chứng minh firewall chặn” | Route không tồn tại/BMC tắt cũng timeout | Rule/flow evidence và positive test |
| “Một nguồn test đủ đại diện cả network” | AZ/region/VRF/DR paths khác nhau | Test mỗi loại đường quan trọng |
| “Cùng account admin cho mọi server dễ kiểm toán” | Shared identity mất attribution/rotation | Individual short-lived identities |
| “Đổi mật khẩu admin sau sự cố là hoàn tất” | Route leak/tokens/data copy còn | Credential + boundary + data audit review |
| “Logs càng nhiều payload càng tốt” | Có thể tạo kho dữ liệu nhạy cảm mới | Data minimization, redaction, retention |

## 45. Câu hỏi tự kiểm tra

1. Phân biệt **data plane, control plane và management plane** bằng ba ví dụ trong một trung tâm dữ liệu.
2. Vì sao một Kubernetes API server có thể liên quan cả control và management workflows?
3. Một management path gồm những yếu tố nào ngoài NIC, VLAN và IP?
4. Vì sao một dữ liệu nghiệp vụ truyền qua mạng private vẫn có thể là **data egress qua trust boundary**?
5. In-band management khác OOB management như thế nào về mạng, khả năng phục hồi và chi phí?
6. Dedicated BMC NIC có tự bảo đảm không có đường từ VPN client tới BMC không? Vì sao?
7. VLAN, subnet và VRF giải quyết các tầng khác nhau như thế nào?
8. Khi nào VRF route leaking có thể làm mất phân tách? Firewall bổ sung ra sao?
9. Vì sao cổng TCP/443 không đủ phân biệt app HTTPS với cloud admin console?
10. Một reference architecture cần tối thiểu những trust zones nào?
11. Làm sao lập flow inventory cho ứng dụng, database, bastion, BMC và backup?
12. Tại sao phải test **data→management DENY** bên cạnh **bastion→management ALLOW**?
13. Stateful firewall khác stateless NACL khi nhận gói phản hồi SSH như thế nào?
14. Sử dụng **SSH host key** nhằm xác minh điều gì mà VPN không tự làm?
15. PAM, JIT và MFA có trách nhiệm khác nhau thế nào?
16. Vì sao JIT hết hạn chưa chắc đã đóng một phiên đang chạy?
17. Một bastion có thể trở thành pivot host trong những trường hợp nào?
18. Vì sao SSH forwarding/SFTP và clipboard trên remote desktop có liên quan đến DLP?
19. Những quyền nào của BMC khiến nó là tài sản bảo mật đặc biệt nhạy cảm?
20. IPMI/Redfish/virtual media cần quản trị nguồn kết nối và credential ra sao?
21. SNMPv3 read-only và network config API cần phân quyền khác nhau thế nào?
22. Vì sao **BGP/OSPF control traffic** không nhất thiết chạy qua management VRF?
23. Virtualization manager và SDN controller có thể ảnh hưởng data plane bằng những hành động nào?
24. Nếu VM runtime role có quyền thay virtual switch, mạng VLAN tách biệt còn ý nghĩa gì?
25. Cloud API dùng HTTPS/443 có thể thay route hoặc firewall như thế nào?
26. Private cloud endpoint cần IAM/account restriction ra sao để giảm data loss?
27. Một Kubernetes Pod không cần gọi API server nên có ServiceAccount/RBAC/egress như thế nào?
28. Điều gì xảy ra nếu CNI không thực thi NetworkPolicy đã được tạo?
29. Vì sao một default-deny egress mới không vô hiệu hóa policy allow-all khác?
30. CoreDNS và NodeLocal DNSCache làm thay đổi cách thiết kế DNS egress ra sao?
31. Logging ingestion khác quyền search/export của SIEM như thế nào?
32. Tại sao backup cần tách control request khỏi payload transfer?
33. Làm sao xác minh một backup chỉ đi tới approved repository/account/tenant?
34. Những dữ liệu nào trong logs cần che hoặc giới hạn lưu trữ?
35. Phân tách management/data trên VPN hybrid phải xem BGP/route propagation ở đâu?
36. IPv6 và NAT64 có thể làm thay đổi egress path đã được kiểm toán v4 ra sao?
37. Primary và DR path cần kiểm thử điều gì trước khi kết luận bảo mật tương đương?
38. Lúc IdP/PAM outage, **fail closed** và **break-glass** phải phối hợp ra sao?
39. Vì sao không thể dùng đường SSH mở từ mọi corporate subnet như một giải pháp break-glass thường trực?
40. Ai được sửa firewall/NetworkPolicy/cloud IAM và vì sao quyền đó ảnh hưởng trực tiếp tới segmentation?
41. Một management prefix xuất hiện trong DATA VRF nên tạo cảnh báo và kiểm thử gì?
42. Trong case study 1, vì sao chỉ có route leak chưa đủ để kết luận endpoint BMC bị chiếm?
43. Trong case study 2, vì sao quyền cloud IAM của application phá ranh giới dù traffic L3/L4 bị tách?
44. Trong case study 3, tại sao PAM recording không ngăn tất cả file export?
45. Trong case study 4, tách BMC NIC nhưng giữ shared credentials gây rủi ro gì?
46. Trong case study 5, vì sao private object-storage endpoint chưa chắc giữ backup ở cùng tenant?
47. Trong case study 6, phải kiểm chứng backup/DR route ra sao để tránh management access từ data zone?
48. Khi một admin SSH timeout, làm sao phân biệt lỗi route, firewall, TLS/SSH identity và authorization?
49. Để tuyên bố segmentation **PASS**, cần những bằng chứng từ firewall, identity, routing và DLP?
50. Hãy thiết kế ma trận **ALLOW/DENY** cho ba nguồn: App Pod, Admin workstation và PAM bastion tới ba đích: DB, server-admin và BMC.

## 46. Ghi nhớ trọng tâm

**Phân tách đường đi quản trị và đường đi dữ liệu** nhằm ngăn một sự cố trên ứng dụng/data network lan sang những **giao diện có quyền cấu hình, vận hành hoặc sao chép hạ tầng**. Phải phân biệt **data plane** (vận chuyển/xử lý dữ liệu), **control plane** (điều phối trạng thái) và **management plane** (truy cập quản trị), nhưng cũng phải nhận ra một số API/thiết bị phục vụ nhiều chức năng. **VLAN, VRF, subnet, dedicated OOB** có thể tạo phân cách logic/vật lý; chúng chỉ đáng tin khi đi cùng **route policies, firewall, identity, thiết bị quản trị và negative tests**.

Đường quản trị thông thường nên đi qua **managed admin workstation → MFA/ZTNA hoặc admin VPN → PAM/bastion/JIT → target-specific SSH/HTTPS/API**, với **server identity verification, RBAC và audit**. Các giao diện **BMC, network device, hypervisor, cloud admin API và Kubernetes API/kubelet** cần kiểm soát riêng; không public và không để data workloads có cloud/cluster credentials sửa ranh giới bảo mật. **Management path không đồng nghĩa an toàn tự động**: nếu bastion, SIEM, remote desktop hoặc backup có quyền export dữ liệu tùy ý, chúng có thể trở thành đường thất thoát qua HTTPS/SSH dù đã tách mạng.

Thiết kế hoàn chỉnh cần kiểm soát **cả data→management reachability lẫn management→unapproved data destinations**, đồng thời cho phép các dependencies hợp lệ như **DNS, NTP, PKI, monitoring, backups, software updates** theo policy có owner. Ranh giới phải hoạt động trên **IPv4/IPv6, VPN/peering, cloud private endpoints, container/Kubernetes, hybrid cloud, primary/DR/failover**. Với sự cố, dùng **HA OOB/bastion và break-glass có phê duyệt, TTL, audit** thay vì tạo một public admin bypass cố định.

Nghiệm thu không dựa vào một sơ đồ đẹp hay việc một subnet không thể ping được. Cần đối chiếu **effective routes/VRFs, firewall/SG/NACL/NetworkPolicy enforcement, identity permissions, TLS/SSH verification, PAM sessions, destination/tenant data policy và runtime logs**. Chỉ tuyên bố phân tách thành công khi **admin có quyền truy cập được đúng tài sản, workloads/data clients không chạm được management endpoints, backup/logging vẫn hoạt động đúng và không có đường xuất dữ liệu trái phép qua kênh quản trị**.
