# Segmentation theo environment: cô lập Dev, Test, Staging và Production

## 1. Segmentation theo environment là gì?

**Segmentation theo environment** là cách phân chia hệ thống thành những **môi trường vận hành có ranh giới kiểm soát truy cập riêng**: ví dụ Development (Dev), Testing/QA, Staging/Pre-production, Production (Prod), Disaster Recovery (DR) và các dịch vụ dùng chung. Mục đích là để một thiết bị, tài khoản, workload hoặc sai sót trong môi trường này **không mặc nhiên có đường truy cập** tới môi trường khác.

Trong học phần **SECURITY_NETWORK_SECURITY**, thiết kế này là nền tảng để kết hợp **phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, Wi-Fi và hạ tầng đám mây**. Khi phân tích lưu lượng hay mô hình hóa mối đe dọa, ta cần biết dữ liệu đang đi **từ environment nào đến environment nào**, qua ranh giới tin cậy nào, và ai đã cấp quyền đi qua ranh giới đó.

**Ví dụ:** Một lập trình viên đang thử dịch vụ mới tại Dev. Nếu Dev sử dụng chung mạng, chung thông tin xác thực và chung kết nối cơ sở dữ liệu với Prod, một máy Dev bị chiếm quyền có thể trở thành điểm khởi đầu của **lateral movement** (di chuyển ngang) tới dữ liệu khách hàng thật. Nếu có phân đoạn hiệu quả, Dev chỉ truy cập tài nguyên được phép phục vụ phát triển; đường tới Prod bị chặn hoặc đòi hỏi một quy trình triển khai đã xác thực và được cấp quyền rõ ràng.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **environment**, **security zone**, **subnet/VLAN** và **trust boundary**.
2. Vẽ luồng dữ liệu giữa Dev, Test, Staging, Prod, DR và Shared Services; thiết kế ma trận truy cập mặc định từ chối.
3. Chọn cơ chế phân đoạn phù hợp cho on-premises, cloud, Kubernetes và mô hình hybrid.
4. Thiết kế các ngoại lệ phục vụ CI/CD, DNS, giám sát, sao lưu và quản trị mà không mở đường xuyên environment quá rộng.
5. Đề xuất kiểm tra kỹ thuật để chứng minh chính sách **ALLOW đúng nhu cầu** và **DENY đúng ranh giới**.
6. Nhận diện giới hạn của VLAN, firewall, NetworkPolicy và cách kết hợp với xác thực danh tính, bảo vệ dữ liệu, quản lý secrets.

## 2. Environment khác VLAN và security zone như thế nào?

| Khái niệm | Bản chất | Ví dụ | Điều cần lưu ý |
| --- | --- | --- | --- |
| **Environment** | Phạm vi triển khai/vận hành có mục tiêu và mức tin cậy nhất định | dev, qa, staging, prod | Có thể gồm nhiều subnet, tài khoản cloud, cụm Kubernetes và dịch vụ |
| **Security zone** | Nhóm tài sản chịu cùng một chính sách kiểm soát lưu lượng | untrusted, app, database, management | Một environment có thể gồm nhiều zone; cùng zone chưa chắc cùng environment |
| **VLAN** | Phân tách miền broadcast ở tầng 2 (Ethernet) | VLAN 110 Dev, VLAN 310 Prod | VLAN **không tự mã hóa hoặc ngăn mọi lưu lượng L3**; inter-VLAN routing có thể nối các VLAN |
| **Subnet** | Phạm vi địa chỉ IP/định tuyến | 10.10.0.0/16, 10.30.0.0/16 | Subnet khác nhau không đồng nghĩa có firewall giữa chúng |
| **VPC/VNet** | Ranh giới mạng logic trong các nền tảng cloud | VPC riêng cho Prod | Peering, gateway, transit routing và chia sẻ tài nguyên vẫn có thể mở đường truy cập |
| **Cluster/namespace** | Phạm vi tổ chức workload container | Kubernetes cluster prod, namespace staging | Namespace đơn lẻ **không phải** ranh giới bảo mật mạng hoàn chỉnh |
| **Trust boundary** | Vị trí các giả định về quyền, danh tính và khả năng truy cập thay đổi | Staging → Prod, user → admin API | Có thể nằm ở tầng mạng, API gateway, IAM, secrets hoặc control plane |

Ví dụ: Prod có thể dùng **ba zone** Web, App và Database, mỗi zone gồm nhiều subnet. Đồng thời các tài nguyên Prod nên được vận hành với quyền cloud, tài khoản dịch vụ, kho bí mật, hệ thống triển khai và chính sách mạng tách biệt khỏi Dev.

**Ý nghĩa bảo mật:** “Dev và Prod khác VLAN” là một mô tả cấu hình tầng 2. Phát biểu “Dev không thể kết nối tới cơ sở dữ liệu Prod” chỉ đúng nếu **đường định tuyến thực tế, firewall/ACL, quyền cloud và các đường truy cập gián tiếp** đều đã được kiểm soát.

## 3. Chọn ranh giới phù hợp cho từng môi trường

| Environment | Mục đích | Kiểu dữ liệu nên sử dụng | Rủi ro nổi bật | Kỳ vọng phân đoạn |
| --- | --- | --- | --- | --- |
| **Sandbox/Dev** | Thử nghiệm nhanh, phát triển và debug | Dữ liệu giả lập/tổng hợp | Công cụ thử nghiệm, gói phụ thuộc mới, quyền rộng để phát triển | Cô lập khỏi Prod; giới hạn Internet egress và secrets |
| **Test/QA** | Kiểm thử chức năng, tích hợp, tự động hóa | Dữ liệu test, bản sao đã khử định danh nếu được phê duyệt | Tài khoản test yếu, test script có quyền cao | Chỉ mở các phụ thuộc test cần thiết |
| **Staging/Pre-prod** | Xác minh bản phát hành và hành vi gần giống Prod | Dữ liệu tổng hợp hoặc đã được xử lý theo chính sách | Dễ bị coi nhầm là Prod; có thể bật tính năng quản trị/debug | Mô phỏng topology và policy cần thiết, nhưng không dùng chung bí mật/DB Prod |
| **Production** | Phục vụ người dùng và nghiệp vụ thật | Dữ liệu thật theo phân loại | Thiệt hại về tính sẵn sàng, bí mật và toàn vẹn | Ranh giới mạnh, quyền tối thiểu, audit đầy đủ |
| **DR/Backup** | Khôi phục dịch vụ và dữ liệu | Bản sao/backup nhạy cảm của Prod | Ransomware lan sang bản sao, lạm dụng kênh replication | Kênh sao chép giới hạn; quyền và tài khoản độc lập theo mô hình khôi phục |
| **Shared Services** | DNS, NTP, identity, monitoring, artifact registry... | Tùy dịch vụ | Trở thành đường bắc cầu giữa môi trường | Phân quyền theo environment, tách endpoint/tenant khi cần |
| **Management** | Quản trị thiết bị, control plane, CI/CD, bastion | Secrets, log và quyền đặc quyền | Một quyền admin có thể tác động nhiều environment | Truy cập qua danh tính mạnh, đường quản trị riêng, giám sát |

**Staging giống Prod về hành vi cần kiểm chứng, nhưng không nhất thiết giống Prod về quyền.** Mục tiêu là đủ tương đồng để kiểm thử trước phát hành, trong khi vẫn giảm khả năng ảnh hưởng hệ thống thật.

Nếu cần kiểm thử với dữ liệu thật, phải qua quy trình phê duyệt và kiểm soát dữ liệu thích hợp; ưu tiên **dữ liệu tổng hợp hoặc được khử định danh đúng kỹ thuật**, không mặc định copy database Production sang Dev.

## 4. Kiến trúc tham chiếu và đường đi qua ranh giới

Một thiết kế đơn giản có các miền tách nhau và một nhóm dịch vụ dùng chung được quản lý:

~~~mermaid
flowchart TB
    U["Người dùng Internet"] --> W["Public ingress / WAF"]
    W --> P["Production: Web / API"]
    P --> PD[("Production DB")]
    DEV["Development"] --> DDB[("Dev DB giả lập")]
    STG["Staging"] --> SDB[("Staging DB thử nghiệm")]
    CI["CI/CD control plane"] -->|"Triển khai được cấp quyền"| P
    CI -->|"Triển khai bản thử nghiệm"| STG
    SH["Shared: DNS / Metrics / Registry"]
    DEV -. "Chỉ các dịch vụ được phép" .-> SH
    STG -. "Chỉ các dịch vụ được phép" .-> SH
    P -. "Chỉ các dịch vụ được phép" .-> SH
    DR["DR / Backup"] <-. "Replication có kiểm soát" .-> PD
~~~

Các đường nét trong sơ đồ **không tự thể hiện quyền**; chúng cho biết luồng cần có trong một thiết kế ví dụ. **Không có đường Dev → Production DB hoặc Staging → Production DB** vì không có nhu cầu kinh doanh đã được phê duyệt.

### 4.1. Ba kiểu luồng cần xét

**North–south:** Lưu lượng vào/ra hệ thống, chẳng hạn người dùng Internet → public API Prod hoặc Dev → Internet tải dependency. Cần kiểm tra WAF, firewall, egress proxy, DNS, TLS và chính sách public exposure.

**East–west trong một environment:** Lưu lượng giữa frontend → API → database thuộc Prod hoặc Dev. Cần tách zone theo chức năng, chỉ mở cổng cần thiết và kiểm tra xác thực dịch vụ.

**Cross-environment:** Dev → Staging, Staging → Prod, CI/CD → Prod, Prod → Shared hoặc Prod → DR. Đây là những luồng cần **giải trình riêng** vì chúng vượt ranh giới tin cậy.

### 4.2. Phân đoạn có nhiều lớp

~~~text
Ranh giới tổ chức / tài khoản cloud / cluster
                 ↓
Định tuyến: VLAN / subnet / VPC / VNet / VRF
                 ↓
Chính sách: firewall / ACL / SG / NSG / NetworkPolicy
                 ↓
Danh tính: IAM / mTLS / workload identity / 802.1X
                 ↓
Ứng dụng: authorization / scope / tenant / API policy
                 ↓
Dữ liệu: secrets / encryption / backup / audit
~~~

Lớp mạng giúp **giảm nơi có thể kết nối**, còn xác thực và phân quyền quyết định **bên nào được thực hiện hành động gì**. Ví dụ, cho phép Staging gọi một API trung gian được kiểm soát **không đồng nghĩa** cấp Staging quyền đọc mọi bảng trong Production.

## 5. Bắt đầu bằng data flow và ma trận truy cập

Không nên triển khai VLAN hoặc Security Group trước khi biết dịch vụ cần trao đổi dữ liệu gì. Một phiên thiết kế nên ghi:

1. **Tài sản và owner:** Workload, database, vault, CI/CD runner, DNS, monitoring, backup, các endpoint công khai.
2. **Phân loại:** Environment, mức nhạy cảm dữ liệu, định danh dịch vụ, zone và mức độ quan trọng.
3. **Luồng cần thiết:** Ai khởi tạo kết nối, tới đích nào, dùng protocol/port/API, tần suất và mục đích.
4. **Đường thực tế:** DNS, route table, peering/transit gateway, NAT, service mesh, load balancer, proxy, VPN hoặc kết nối giữa các site.
5. **Điểm thực thi policy:** Firewall, ACL, security group, network policy, gateway, identity policy; nguồn nào quyết định cho phép/từ chối?
6. **Kiểm chứng:** Cách chứng minh các luồng được duyệt vẫn hoạt động và những luồng không được duyệt bị chặn.

### 5.1. Ma trận policy ví dụ

Giả định doanh nghiệp chỉ cần các luồng sau:

| Source | Destination | Protocol / chức năng | Chính sách | Điều kiện đi kèm |
| --- | --- | --- | --- | --- |
| Internet | Public ingress của Prod | HTTPS/443 | **ALLOW có điều kiện** | TLS đúng cấu hình, WAF/rate limit khi thích hợp |
| Prod frontend | Prod API | HTTPS/8443 | **ALLOW** | Xác thực workload, giới hạn service |
| Prod API | Prod DB | TCP/5432 | **ALLOW** | Chỉ DB role cần thiết; không cho frontend trực tiếp |
| Staging frontend | Staging API | HTTPS/8443 | **ALLOW** | Chỉ định danh/cổng Staging |
| Staging API | Staging DB | TCP/5432 | **ALLOW** | Tài khoản và dữ liệu Staging |
| Dev | Production DB | TCP/5432 | **DENY** | Không có đường truy cập trực tiếp |
| Staging | Production API/DB | Mọi cổng | **DENY mặc định** | Ngoại lệ chỉ theo quy trình được duyệt, nếu thực sự cần |
| Prod/Dev/Staging | Shared DNS | UDP/TCP 53 hoặc cơ chế DNS được dùng | **ALLOW có giới hạn** | Resolver được phê duyệt, ngăn DNS bypass khi cần |
| Prod workloads | Monitoring collector | Agent/HTTPS theo thiết kế | **ALLOW có giới hạn** | Danh tính, đích và dữ liệu log được kiểm soát |
| CI/CD đã xác thực | Prod deployment API | HTTPS/API cụ thể | **ALLOW có điều kiện** | Quyền triển khai hạn chế, approval và audit |
| Prod DB/backup agent | Kho backup/DR | Kênh backup được phê duyệt | **ALLOW có giới hạn** | Khóa, retention, isolation và kiểm thử restore |
| Tất cả các luồng khác | Không thuộc allowlist | Mọi protocol | **DENY mặc định** | Theo dõi nhu cầu bị từ chối và cập nhật có kiểm soát |

**Đây là ma trận mục tiêu, chưa phải cấu hình áp dụng trực tiếp.** Tùy nền tảng, một hàng có thể cần nhiều rule cho chiều ingress/egress, zone, luồng trả về hoặc DNS. Trên firewall **stateful**, các gói thuộc phiên được cho phép có thể được xử lý bởi connection tracking; trên cơ chế **stateless**, phải cấu hình chiều trả về và dải cổng tương ứng.

### 5.2. Nguyên tắc default deny và ngoại lệ có điều kiện

Đầu tiên xác định những luồng được phép **thật sự cần thiết**. Sau đó chặn mọi luồng cross-environment khác. Rule ngoại lệ cần có **lý do, owner, source/destination cụ thể, service/port, thời hạn nếu tạm thời, dữ liệu được phép và kế hoạch thu hồi**.

Đừng viết “Staging được truy cập toàn bộ Prod vì hai môi trường giống nhau”. Hãy thay bằng “pipeline kiểm thử đã xác thực được gọi **endpoint kiểm thử riêng** qua HTTPS với quyền đọc giới hạn và dữ liệu giả lập”, nếu đó thật sự là yêu cầu.

## 6. Thiết kế on-premises: VLAN, VRF và firewall

### 6.1. Ví dụ ánh xạ mạng

~~~text
VLAN 110  / 10.10.0.0/16  / DEV
VLAN 210  / 10.20.0.0/16  / STAGING
VLAN 310  / 10.30.0.0/16  / PROD
VLAN 410  / 10.40.0.0/16  / SHARED
VLAN 510  / 10.50.0.0/16  / MANAGEMENT
~~~

Đây chỉ là **địa chỉ minh họa**, không phải đề xuất cấp một VLAN với subnet /16 trong mọi mạng. Thiết kế thực phải xét quy mô, IPAM, nhu cầu broadcast, định tuyến, HA và phương án chuyển đổi.

VLAN phân tách **layer 2**. Để kiểm soát luồng giữa VLAN, các mạng có thể được đưa qua firewall hoặc gateway có chính sách tương ứng. **VRF** có thể tách bảng định tuyến, nhưng khi cấu hình route leaking, peering hoặc chuyển tiếp qua shared firewall, lưu lượng vẫn có thể đi qua ranh giới đã thiết lập.

### 6.2. Sai lầm thường gặp

**Sai lầm 1 – Trên switch đã có VLAN riêng nên mặc định an toàn.** Nếu Layer-3 switch cho inter-VLAN routing trực tiếp với ACL quá rộng, Dev vẫn đi đến Prod.

**Sai lầm 2 – Một rule “allow internal networks” áp dụng cả các environment.** Rule này vô hiệu hóa ý định cô lập khi tất cả các dải nằm trong address group chung.

**Sai lầm 3 – Chỉ xét đường đi một chiều.** VPN, NAT, policy-based routing, các đường dự phòng và firewall nhiều vị trí có thể tạo **đường vòng** không được đưa vào kiểm thử.

**Sai lầm 4 – Tin vào thông tin nguồn IP như danh tính.** IP có thể động hoặc bị ảnh hưởng bởi NAT. Đối với quản trị, cần kết hợp kiểm soát thiết bị, xác thực người dùng, quyền của service và kiểm toán.

### 6.3. Vai trò của NAC và truy cập quản trị

**802.1X/NAC** có thể kiểm soát thiết bị nào được nối vào mạng và gán vai trò/VLAN theo chính sách. Tuy nhiên, một máy đã vào VLAN hợp lệ **không tự có quyền** quản trị Prod. Tác vụ quản trị nên qua điểm truy cập được kiểm soát (bastion, VPN/ZTNA, privileged access workflow) với MFA, tài khoản đặc quyền riêng, phiên truy cập được ghi nhận và quyền tối thiểu.

## 7. Thiết kế cloud: account, VPC/VNet và đường kết nối

Trong cloud, mô hình thường mạnh hơn khi tách **tài khoản/subscription/project theo environment**, cùng với mạng, IAM, secrets, monitoring và hạn mức/quota riêng. Ví dụ:

~~~text
Organization / Management Group
├── Account/Project: dev
│   ├── Dev VPC/VNet
│   ├── Dev identity + secrets
│   └── Dev workloads
├── Account/Project: staging
│   ├── Staging VPC/VNet
│   └── Staging workloads
├── Account/Project: prod
│   ├── Prod VPC/VNet
│   ├── Prod keys + secrets
│   └── Prod workloads
└── Account/Project: shared-security
    ├── Audit/monitoring
    └── DNS / approved shared services
~~~

Trong AWS, Azure hoặc Google Cloud, các **cơ chế tương đương không hoàn toàn giống nhau**. Cần đọc mô hình thực thi của security groups, NSG, firewall rules, network policy, IAM và routing của chính nền tảng đang sử dụng.

### 7.1. Đường mạng và đường quyền

- **VPC peering / VNet peering / transit hub:** Một kết nối có thể tạo đường định tuyến giữa environment. Route table, attachment, route propagation và firewall đặt tại đúng điểm phải cùng thực thi yêu cầu cô lập.
- **Private endpoint / PrivateLink và dịch vụ được chia sẻ:** Truy cập một service cụ thể có thể ít mở quyền hơn kết nối toàn bộ CIDR, nhưng vẫn phải xét quyền service, endpoint policy và DNS.
- **Security Group / NSG / firewall:** Giới hạn IP, port và đích. Trên một số nền tảng, **security group chỉ tổng hợp allow**, trong khi ACL/NSG có priority và deny; không áp dụng một thuật toán shadowing như nhau cho mọi loại policy.
- **IAM/workload identity:** Một workload Dev có thể bị chặn ở network nhưng vẫn có quyền gọi **cloud control API** hoặc đọc secret của Prod nếu phân quyền sai. Phải tách cả quyền tạo, sửa, đọc, triển khai và lấy secrets.
- **Egress:** NAT gateway và Internet egress là đường ra, không tự cung cấp allowlist đích. Dùng egress policy, proxy, DNS policy và giám sát khi cần kiểm soát dữ liệu ra ngoài.

### 7.2. Cảnh báo cho hub-and-spoke

Mô hình **hub-and-spoke** thuận tiện dùng chung firewall, DNS, WAN hoặc proxy, nhưng hub có thể vô tình trở thành **đường đi ngang** giữa Dev và Prod. Hãy kiểm tra tính cách ly trên **bảng định tuyến, firewall trước/sau NAT, traffic selector, route propagation và quyền tạo kết nối mới**.

Đường Dev → shared monitoring và Prod → shared monitoring có thể đều được phép, nhưng **không có nghĩa shared monitoring được phép kết nối tùy ý từ Dev sang Prod**. Dịch vụ dùng chung cần cô lập tenant, role và dữ liệu theo từng environment.

## 8. Kubernetes: namespace là tổ chức, NetworkPolicy là một lớp kiểm soát

Trong Kubernetes, nhiều workload có thể nằm trong các **namespace** khác nhau nhưng cùng chia sẻ hạ tầng cluster, API server, node network và một số dịch vụ nền. Namespace giúp tổ chức tài nguyên và áp dụng RBAC/quota, song **không tự tạo firewall giữa các Pod**.

**Kubernetes NetworkPolicy** chuẩn thường định nghĩa điều kiện ingress/egress dựa trên pod/namespace selector, IPBlock, protocol và port ở tầng 3/4. Nó yêu cầu **CNI/network plugin có hỗ trợ thực thi**; chỉ tạo YAML mà plugin không thực thi sẽ không đảm bảo chặn lưu lượng.

### 8.1. Mẫu default deny trong một namespace

Ví dụ staging có hai workload gắn nhãn **app=frontend** và **app=api** trong namespace **staging**. Trước tiên mặc định từ chối ingress và egress của tất cả pod trong namespace:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: staging-default-deny
  namespace: staging
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

Policy trên dùng selector rỗng để chọn **mọi Pod trong namespace staging**. Trong mô hình NetworkPolicy chuẩn, nếu không có các rule cho phép tương ứng từ bất kỳ policy áp dụng nào, luồng mới vào/ra Pod bị hạn chế theo hai hướng đã chọn.

Tiếp theo, cho **frontend → API** qua TCP/8443 theo hai chiều cần thiết: ingress vào API và egress khỏi frontend.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: staging-api-from-frontend
  namespace: staging
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: frontend
      ports:
        - protocol: TCP
          port: 8443
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: staging-frontend-to-api
  namespace: staging
spec:
  podSelector:
    matchLabels:
      app: frontend
  policyTypes:
    - Egress
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: api
      ports:
        - protocol: TCP
          port: 8443
~~~

Vì **podSelector trong ingress/egress không đi cùng namespaceSelector**, hai selector trên chỉ khớp Pod trong **cùng namespace staging**. Như vậy, chính sách này không trực tiếp mở quyền cho Pod Prod. Nó cũng không cho phép mọi kết nối của frontend tới Internet hoặc cơ sở dữ liệu.

### 8.2. Cho phép DNS có kiểm soát

Nếu đã default deny egress, Pod có thể không phân giải DNS được. Ví dụ sau cho phép kết nối tới các Pod DNS được gắn **k8s-app=kube-dns** trong namespace **kube-system**. Phải kiểm tra **nhãn thực tế và đường đi DNS** trong cluster (ví dụ NodeLocal DNSCache có thể có đường đi khác):

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: staging-allow-dns
  namespace: staging
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
~~~

Ở cùng một mục **to**, namespaceSelector và podSelector là điều kiện **AND**: chỉ chọn Pod có nhãn tương ứng trong namespace đã chọn. Trong ví dụ, DNS được cho phép cho mọi Pod staging; khi cần, có thể thu hẹp phạm vi Pod gửi.

**Giới hạn cần nhớ:**

- NetworkPolicy là lớp **L3/L4**; nó không tự xác minh JWT, tên người dùng, quyền truy vấn database hoặc nội dung HTTP.
- NetworkPolicy thường là **allowlist cộng gộp**: nhiều policy áp dụng cùng Pod sẽ **hợp** những luồng được phép; không có “deny rule ưu tiên cao hơn” theo semantics chuẩn.
- NetworkPolicy phụ thuộc plugin mạng, cách dịch Service IP, DNS, node traffic, hostNetwork và giới hạn của nền tảng; phải kiểm chứng thực tế.
- Nếu Dev và Prod có mức tin cậy khác biệt lớn, **tách cluster**, node pool, account và quyền quản trị có thể cần thiết. NetworkPolicy trong cùng cluster không tự tạo ranh giới control plane/host mạnh như tách hạ tầng.
- Những ví dụ YAML trên là **mẫu để học**, chỉ được áp dụng vào lab/staging sau khi xác nhận Pod label, CNI và các luồng bắt buộc; không tự triển khai vào hệ thống đang hoạt động.

## 9. Các ngoại lệ thường bị bỏ sót

### 9.1. DNS, thời gian và dịch vụ nền

Nhiều hệ thống phải dùng DNS, NTP, CA/certificate validation, metadata service, service discovery, load balancer health check hoặc cloud control endpoints. Khi bật default deny, cần **liệt kê rõ** các dịch vụ nền phải hoạt động. Không nên giải quyết bằng một rule **ALLOW 0.0.0.0/0 any port** vì nó có thể tạo đường ra ngoài rộng hơn dự kiến.

Đối với DNS, chọn resolver được quản lý; nếu chính sách yêu cầu, ngăn truy vấn qua resolver không được phê duyệt và kiểm soát DoH/DoT phù hợp. Nhưng **chặn DNS không tương đương chặn mọi đường kết nối bằng IP**.

### 9.2. CI/CD, artifact registry và nhà cung cấp bên thứ ba

Một quy trình triển khai tốt có thể **build và kiểm thử ở môi trường ít tin cậy**, sau đó **promote artifact đã xác minh** sang Prod bằng pipeline được cấp quyền. Không cần cấp cho Pod Dev quyền truy cập database Prod chỉ để “đẩy bản phát hành”.

- Dùng artifact registry được kiểm soát, ký artifact hoặc xác minh provenance khi phù hợp.
- Tách **deploy credentials, secrets và role** theo environment; dùng thông tin xác thực ngắn hạn nếu được hỗ trợ.
- Giới hạn quyền pipeline Prod theo service và hành động; có thể yêu cầu phê duyệt cho thay đổi nhạy cảm.
- Không mặc định runner xây dựng từ pull request không tin cậy có quyền deploy vào Prod.
- Kiểm soát luồng tới package registry, container registry và API bên thứ ba; xác định cơ chế egress hoặc proxy.

### 9.3. Quan sát, sao lưu và khôi phục thảm họa

Central logging/monitoring thường nhận dữ liệu từ nhiều environment. Hãy phân tách tenant, index, quyền đọc, retention và cảnh báo để log của Prod không bị người Dev đọc tự do. Nếu collector có quyền kết nối ngược tới toàn bộ agent, phải đánh giá lại nguy cơ lateral movement.

Kết nối backup/DR cần quyền theo **mục tiêu cụ thể**. Bản sao bất biến/không thể bị sửa bằng cùng thông tin xác thực từ Prod, chính sách giữ bản sao, quyền khôi phục độc lập và kiểm thử restore giúp hạn chế thiệt hại nếu Prod bị ransomware. Phân đoạn không thay thế các kiểm soát backup này.

### 9.4. Dữ liệu giữa môi trường

Sao chép dữ liệu Prod sang Staging/Dev là **luồng dữ liệu xuyên environment**, dù có thể không được thực hiện qua kết nối mạng trực tiếp (ví dụ thông qua backup/snapshot). Cần phân loại và xét:

1. Có được dùng dữ liệu thật cho mục tiêu kiểm thử không?
2. Có quy trình **masking, tokenization, data minimization** phù hợp không?
3. Secrets, access token, private key, thông tin tài khoản có được loại khỏi snapshot không?
4. Ai được tải và giải mã dữ liệu ở môi trường thấp hơn?
5. Nhật ký, backup phụ và thời gian lưu của Staging có được kiểm soát không?

Một môi trường đã tách mạng nhưng chứa **bản sao đầy đủ dữ liệu Prod với quyền truy cập yếu** vẫn tạo rủi ro nghiêm trọng.

## 10. Mô hình hóa mối đe dọa xuyên environment

Phân đoạn phải xuất phát từ **đường tấn công có thể xảy ra**, không chỉ từ sơ đồ subnet.

| Threat scenario | Điều kiện ban đầu | Đường lây lan / tác động | Phòng vệ đề xuất |
| --- | --- | --- | --- |
| **Dev bị chiếm quyền → Prod DB** | Dev có route và ACL/SG mở trực tiếp sang Prod | Đọc/sửa dữ liệu thật | Chặn cross-env mặc định, tách mạng và DB role, kiểm tra bằng chứng deny |
| **Staging dùng chung secret với Prod** | Secret hoặc service account tái sử dụng giữa môi trường | Tài khoản lộ ở Staging có thể gọi API/DB Prod | Secret store, workload identity và quyền riêng cho từng env; xoay khóa |
| **Pipeline CI/CD bị lạm dụng** | Runner/build không tin cậy giữ quyền triển khai Prod | Triển khai artifact độc hại hoặc sửa cấu hình | Build/deploy tách quyền, artifact provenance, phê duyệt, audit |
| **Shared service làm cầu nối** | Shared monitoring/proxy có kết nối và quyền hai chiều đến mọi env | Từ tài khoản shared bị chiếm quyền truy cập nhiều môi trường | Chia role/tenant, hạn chế hướng kết nối, kiểm soát egress và quản trị |
| **Hub routing mở nhầm** | Transit gateway/VRF route leak khiến Dev nhìn thấy Prod | Vượt phân đoạn dù có subnet khác | Kiểm tra effective routes, policy ở choke point, regression test |
| **Staging public thiếu kiểm soát** | Endpoint thử nghiệm mở Internet, auth yếu | Bị khai thác rồi tìm cách tới dịch vụ chung | Hạn chế public exposure, auth mạnh, policy egress và asset inventory |
| **Prod tới kho backup không cô lập** | Credentials Prod có quyền xóa/sửa mọi backup | Ransomware phá cả bản sao | Tách quyền backup, phiên bản bất biến, restore test, MFA/quy trình riêng |
| **IPv6 hoặc đường VPN bị bỏ sót** | Chỉ áp firewall IPv4 hoặc chỉ test đường nội bộ | Xuất hiện đường đi không được kiểm soát | Kiểm kê dual-stack, VPN, route, endpoint và kiểm thử cả hai họ địa chỉ |

### 10.1. Trust boundary là điểm đổi khả năng

Khi vẽ threat model, với mỗi luồng **Dev → Shared** hoặc **Staging → Prod**, ghi:

~~~text
Tài sản cần bảo vệ:    Production data / deployment API / secrets
Tác nhân có thể bị lộ: Developer workstation / CI runner / test Pod
Điểm ranh giới:        Dev VPC -> Transit firewall -> Prod VPC
Chức năng được phép:   Không có, trừ ngoại lệ đã phê duyệt
Kiểm soát mạng:        Routing + firewall/SG/ACL + egress policy
Kiểm soát danh tính:   IAM/mTLS/service authorization
Đường đi khác:         Cloud API, shared services, VPN, NAT, IPv6
Bằng chứng yêu cầu:    Policy export + route inspection + denied-flow test
Rủi ro còn lại:        Quyền quản trị, control plane hoặc secrets bị lộ
~~~

**Network segmentation giảm khả năng tiếp cận**, nhưng không ngăn một service Dev **được cấp nhầm quyền IAM** sửa tài nguyên Prod qua API cloud nếu quyền đó vẫn tồn tại. Kiểm tra **data plane lẫn control plane**.

## 11. Case study: Staging vô tình đọc được cơ sở dữ liệu Production

**Bối cảnh lab giả định:** Công ty tách ba mạng:

~~~text
Dev       10.10.0.0/16
Staging   10.20.0.0/16
Prod      10.30.0.0/16
Shared    10.40.0.0/16

Staging API:    10.20.20.10
Staging DB:     10.20.30.10:5432
Production DB: 10.30.30.10:5432
~~~

Một developer phát hiện ứng dụng Staging kết nối được **10.30.30.10:5432** và tài khoản database dùng trên Staging cũng được Prod chấp nhận.

### 11.1. Phân tích nguyên nhân

1. **Mạng:** Có route từ Staging sang Prod qua một transit hub; firewall đang cho phép rule **10.0.0.0/8 → TCP/5432**, vô tình bao gồm cả Prod DB.
2. **Danh tính:** Tài khoản database được tái sử dụng giữa hai môi trường; chỉ tách subnet không ngăn đăng nhập nếu mạng đã cho qua.
3. **Dữ liệu:** Staging mang quyền đọc dữ liệu thật, trái mục tiêu dùng dữ liệu giả lập.
4. **Giám sát:** Chưa có cảnh báo cross-env mới; flow logs cho thấy kết nối được chấp nhận nhưng không được phân loại là bất thường.

### 11.2. Thiết kế mục tiêu

- Chỉ cho phép **Staging API → Staging DB** trên TCP/5432.
- Chỉ cho phép **Prod API → Prod DB** trên TCP/5432.
- Từ chối **Staging → Prod DB** và **Dev → Prod DB** ở điểm kiểm soát phù hợp; bỏ allow nguồn **10.0.0.0/8** quá rộng.
- Tách credential, database role và secrets theo môi trường; kiểm tra cả quyền trên cloud control plane.
- Cập nhật inventory và tạo cảnh báo với những truy cập Prod có source environment ngoài danh sách.

### 11.3. Kiểm chứng

| Test ID | Source → Destination | Kết quả mong đợi |
| --- | --- | --- |
| ENV-01 | Staging API → Staging DB TCP/5432 | **ALLOW** theo policy và DB role hợp lệ |
| ENV-02 | Staging API → Prod DB TCP/5432 | **DENY** ở lớp mạng |
| ENV-03 | Dev workload → Prod DB TCP/5432 | **DENY** ở lớp mạng |
| ENV-04 | Prod API → Prod DB TCP/5432 | **ALLOW** theo policy và DB role hợp lệ |
| ENV-05 | Staging → Shared DNS qua resolver đã duyệt | **ALLOW** |
| ENV-06 | Staging → máy chủ DNS Internet không duyệt | **DENY** nếu chính sách cấm DNS bypass |
| ENV-07 | CI/CD identity Dev → Prod secrets API | **DENY** theo IAM |
| ENV-08 | Deploy identity Prod → endpoint triển khai được duyệt | **ALLOW có điều kiện**, ghi audit |

**Lưu ý:** Thành công của TCP handshake **không có nghĩa** quyền truy vấn database hợp lệ. Ngược lại, kết nối thất bại có thể do route, firewall, service dừng, DNS hoặc TLS; xác minh cần kết hợp logs ở điểm thực thi policy và ứng dụng.

## 12. Thực hành phân tích policy bằng dữ liệu mô phỏng

Đoạn Python sau mô phỏng **allowlist theo nguồn, đích và cổng** cho các environment. Nó **không chạm vào mạng**, không thay firewall và không mô phỏng NAT, routing hoặc identity. Mục đích là chuyển ma trận kiểm soát thành các ca kiểm thử rõ ràng.

~~~python
# Bộ chính sách minh họa: tập quan hệ (source, destination, TCP port)
allowed = {
    ("staging-api", "staging-db", 5432),
    ("prod-api", "prod-db", 5432),
    ("staging-api", "shared-dns-tcp", 53),
    ("prod-api", "shared-monitor", 443),
}


def permitted(source: str, destination: str, tcp_port: int) -> bool:
    # Những luồng không được liệt kê là DENY trong mô hình đơn giản.
    return (source, destination, tcp_port) in allowed


tests = [
    ("staging-api", "staging-db", 5432, True),
    ("staging-api", "prod-db", 5432, False),
    ("dev-api", "prod-db", 5432, False),
    ("prod-api", "prod-db", 5432, True),
    ("staging-api", "shared-dns-tcp", 53, True),
    ("prod-api", "shared-monitor", 443, True),
    ("dev-api", "shared-monitor", 443, False),
]

for source, destination, port, expected in tests:
    actual = permitted(source, destination, port)
    assert actual == expected, (source, destination, port)
    print(f"{source} -> {destination}:{port}: "
          f"{'ALLOW' if actual else 'DENY'}")
~~~

Kết quả minh họa:

~~~text
staging-api -> staging-db:5432: ALLOW
staging-api -> prod-db:5432: DENY
dev-api -> prod-db:5432: DENY
prod-api -> prod-db:5432: ALLOW
staging-api -> shared-dns-tcp:53: ALLOW
prod-api -> shared-monitor:443: ALLOW
dev-api -> shared-monitor:443: DENY
~~~

**Ý nghĩa và giới hạn:** Test này xác nhận **logic của một policy mẫu**, không chứng minh hạ tầng thật tuân thủ. Để kiểm chứng thực tế, cần đối chiếu service inventory với IP/CIDR, labels, VPC/VRF, policy engine, security group, network policy, đường đi/chiều về, IAM và cấu hình được triển khai. Nếu source có thể giả mạo danh tính hoặc gán nhãn sai, bản thân tên "staging-api" không phải bằng chứng tin cậy.

## 13. Triển khai segmentation theo từng bước

Một môi trường hiện hữu có thể chứa nhiều kết nối ngầm. Bật default deny ngay lập tức mà chưa khảo sát có thể làm ngừng DNS, monitoring, health check hoặc kết nối ứng dụng. Quy trình nên chuyển dần từ **quan sát → mô hình chính sách → kiểm thử → áp dụng có kiểm soát**.

### Bước 1. Lập inventory và chuẩn hóa nhãn

Gắn metadata cho mọi tài nguyên quan trọng:

~~~text
environment: prod | staging | dev | ...
application:  billing-service
owner:        team-payments
data-class:   confidential
criticality:  high
network-zone: app
exposure:     internal
~~~

Phải có cơ chế ngăn workload tự gắn nhãn “prod-trusted” để được cấp quyền cao hơn. Label/tag là **dữ liệu điều kiện của chính sách**, nên quyền sửa chúng cũng là một phần của mô hình bảo mật.

### Bước 2. Quan sát kết nối đang được sử dụng

Thu thập flow logs/NetFlow/VPC flow logs, proxy logs, firewall counters, DNS logs và tracing ứng dụng theo quyền đã được phê duyệt. Phân loại luồng theo owner, nhu cầu và mức nhạy cảm; đặc biệt tìm kết nối **Staging ↔ Prod**, **Dev ↔ Prod**, đường tới shared services và egress Internet.

Log kết nối không chứng minh một luồng cần được phép: kết nối đã xảy ra có thể do cấu hình sai hoặc hoạt động không được phê duyệt.

### Bước 3. Chốt ma trận yêu cầu và trust boundary

Xác định chủ tài sản và phê duyệt luồng cần thiết. Chọn cách thực thi theo tuyến đường thực tế; đừng dựa vào một firewall ở ranh giới khi có **đường đi khác** qua private endpoint, service mesh, transit gateway hoặc cloud API.

### Bước 4. Thiết kế cơ chế và cấu hình dưới dạng mã

Ưu tiên policy-as-code/IaC có review, kiểm tra cú pháp, lint, kiểm tra phát sinh allow rộng và quản lý phiên bản. Tránh để Dev và Prod cùng dùng một service account hoặc cùng vault policy chỉ vì mẫu IaC được sao chép.

### Bước 5. Mô phỏng và áp dụng theo đợt

Trong môi trường hỗ trợ, dùng **report-only/dry-run/audit mode** hoặc kiểm tra chính sách trên cấu hình dự kiến. Sau đó thử trên môi trường ít rủi ro, các đường đi representative và nhóm nhỏ trước khi thực thi toàn bộ. Không phải firewall hay NetworkPolicy nào cũng có audit-only mode: phải chọn đúng khả năng của nền tảng.

### Bước 6. Kiểm chứng cả ALLOW lẫn DENY

Kiểm tra các luồng nghiệp vụ, luồng bị chặn, kết nối qua DNS/tên dịch vụ, NAT, IPv6 và chiều về. Phân biệt **policy decision** với **khả năng ứng dụng hoạt động**. Ghi lại rule ID, nguồn/đích, environment, thời điểm, số phiên bản cấu hình và bằng chứng.

### Bước 7. Theo dõi và điều chỉnh

Đặt cảnh báo khi policy giữa environment mở rộng bất thường, khi đường Dev → Prod có traffic, khi service account Dev được cấp quyền Prod hoặc khi cấu hình route/peering thay đổi. Duy trì quy trình exception có thời hạn, owner và xét duyệt lại định kỳ.

### Bước 8. Chuẩn bị rollback

Trước triển khai, lưu phiên bản cấu hình đã xác minh, quy định tiêu chí dừng, người chịu trách nhiệm và cách hoàn nguyên; lưu ý rollback không được vô tình khôi phục các allow quá rộng vốn là nguyên nhân rủi ro.

## 14. Giám sát và xử lý sự cố phân đoạn

| Tín hiệu | Nguồn quan sát | Cách diễn giải |
| --- | --- | --- |
| Kết nối Dev/Staging → Prod bị firewall từ chối | Firewall/NSG/flow logs | Có thể là policy hoạt động đúng, cấu hình ứng dụng sai hoặc dấu hiệu dò tìm |
| Luồng cross-env bất ngờ được cho phép | Firewall/session logs, flow logs | Kiểm tra route, rule, NAT, identity và lý do nghiệp vụ |
| Route/peering/SG/ACL/NetworkPolicy thay đổi | Cloud audit, IaC diff, config repository | Xác định thay đổi được phê duyệt, phạm vi thực thi và drift |
| Dịch vụ Prod bị gián đoạn sau rollout | Application logs, traces, policy hits, DNS/health checks | Tìm luồng hợp lệ bị chặn và nguyên nhân cụ thể |
| Secret/token của Staging được dùng gọi Prod | IAM logs, vault audit, service authorization | Ưu tiên điều tra tách quyền và nguy cơ lộ credential |
| Lưu lượng egress tăng bất thường | Proxy/egress firewall/NDR | Xem có kết nối ra Internet ngoài allowlist hoặc di chuyển dữ liệu không |
| Lỗi phân giải DNS tại Pod | CoreDNS logs, CNI/policy logs, probe được phép | Kiểm tra allow tới resolver, label, namespace và đường Service DNS |
| Backup/replication ngừng chạy | Backup controller, DR health | Xác định cổng/đích/identity cần thiết mà không mở tất cả traffic |

### Quy trình điều tra ngắn

1. **Định vị luồng:** ai khởi tạo, từ environment/identity nào, đến service/port nào, lúc nào?
2. **Xác minh đường đi:** route, DNS, NAT, firewall, security group, CNI và private endpoint có thể đang được dùng.
3. **Xác minh chính sách:** rule nào quyết định, policy được gắn ở đâu, source/destination được dịch như thế nào?
4. **Đối chiếu yêu cầu:** luồng có được duyệt và cần thiết không? Đây là lỗi false block hay rò rỉ quyền?
5. **Khắc phục có kiểm soát:** sửa rule nhỏ nhất đủ giải quyết, áp dụng qua thay đổi được quản lý và kiểm chứng lại cả luồng cần cho phép lẫn luồng cần chặn.
6. **Lưu bằng chứng:** không ghi secrets, credential hoặc dữ liệu cá nhân vào log điều tra; lưu các trường kỹ thuật cần thiết cho việc rà soát.

**IDS/IPS/NDR** có thể phát hiện hành vi bất thường giữa môi trường, nhưng không tự chứng minh chính sách phân đoạn đúng. Cần kết hợp **đánh giá policy tĩnh, quan sát thực thi và thử nghiệm được cho phép**.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Dev và Prod có IP khác nhau nên đã cô lập.” | Nếu routing và rule cho phép, hai dải IP vẫn có thể kết nối. |
| “Tách VLAN nghĩa là không thể đi ngang.” | Inter-VLAN routing, trunk và sai chính sách có thể tạo đường đi xuyên VLAN. |
| “Mọi luồng từ mạng nội bộ đều đáng tin.” | Mạng nội bộ vẫn có endpoint bị xâm nhập; cần xác thực danh tính và quyền. |
| “Có NetworkPolicy là mọi Pod tự động bị cô lập.” | Phải có plugin hỗ trợ và các policy thực sự chọn đúng Pod/hướng; policy chuẩn mang tính allowlist cộng gộp. |
| “Namespace prod và dev đủ để thay cluster riêng.” | Namespace không cô lập hoàn toàn control plane, node, runtime hoặc quyền quản trị. |
| “Tách mạng thì không cần tách secrets.” | Secret và IAM sai có thể vượt ranh giới mạng qua các API hoặc đường truy cập hợp lệ. |
| “Staging phải dùng dữ liệu Prod mới gọi là giống Prod.” | Có thể mô phỏng cấu trúc/tải với dữ liệu tổng hợp hoặc đã khử định danh đúng quy trình. |
| “Central monitoring được quyền đọc mọi dữ liệu của mọi env.” | Shared service phải phân quyền và cô lập dữ liệu theo environment/nhóm. |
| “Mặc định DENY có nghĩa ứng dụng chắc chắn an toàn.” | Vẫn cần xác minh đường vòng, IAM, ứng dụng, lỗi cấu hình và dữ liệu. |
| “Kết nối TCP bị chặn chứng minh không có rủi ro lộ dữ liệu.” | Có thể tồn tại đường qua API cloud, object storage, snapshot, queue hoặc tài khoản chia sẻ. |
| “Prod không thể bị ảnh hưởng từ Dev nếu chỉ deploy qua pipeline.” | Pipeline bị chiếm quyền hoặc quyền promote artifact sai vẫn có thể ảnh hưởng Prod. |
| “Không thấy denied logs là policy đúng.” | Log có thể thiếu hoặc sampling; cần policy inspection và test xác minh. |

## 16. Câu hỏi tự kiểm tra và bài tập kiến trúc

1. **Segmentation theo environment bảo vệ điều gì?** Giảm khả năng môi trường ít tin cậy ảnh hưởng dữ liệu, workload và quyền trong môi trường nhạy cảm hơn; giới hạn phạm vi sự cố.
2. **VLAN, subnet và trust boundary có đồng nghĩa không?** Không. VLAN là phân đoạn L2; subnet là cấu trúc L3; trust boundary là nơi yêu cầu về quyền và độ tin cậy thay đổi.
3. **Vì sao Dev không nên kết nối trực tiếp Prod DB?** Dev thường có thay đổi thường xuyên và quyền debug rộng; đường trực tiếp tăng nguy cơ xâm nhập, lộ hoặc sửa dữ liệu thật.
4. **Staging cần giống Prod ở những khía cạnh nào?** Hành vi, cấu hình và topology cần kiểm thử; không nhất thiết dùng chung dữ liệu, secrets và quyền Prod.
5. **Default deny ảnh hưởng gì tới DNS?** Nếu chặn egress mà chưa có rule tới resolver, Pod/workload có thể không phân giải được tên. Cần mở DNS đúng nguồn/đích/port.
6. **Kubernetes namespace có mặc định chặn Pod khác namespace không?** Không. Phải kiểm tra NetworkPolicy, CNI và những cơ chế khác.
7. **Vì sao shared service có thể trở thành điểm rủi ro?** Nó kết nối và xử lý dữ liệu của nhiều environment; một danh tính hoặc kết nối bị cấp quyền rộng có thể lan truyền tác động.
8. **Một VPC Prod bị tách nhưng IAM role Dev có quyền đọc Prod secrets. Thiết kế đã an toàn chưa?** Chưa. Control plane/IAM là một đường vượt ranh giới cần chặn.
9. **Nếu test kết nối tới Prod DB thất bại, đã chứng minh firewall DENY chưa?** Chưa. Cần đối chiếu rule decision/flow logs và trạng thái service/route/DNS.
10. **Cần những bằng chứng nào để kết luận segmentation đạt yêu cầu?** Inventory, data flow, ma trận duyệt, policy/route hiệu lực, kết quả ALLOW/DENY, kiểm tra IAM/secrets và log giám sát.

### Bài tập tình huống

Một tổ chức có **Dev, Staging, Prod** và cụm **Shared Services**. Hệ thống Staging cần gọi một dịch vụ kiểm thử thanh toán, CI/CD cần triển khai bản phát hành lên Prod, Prod cần gửi log về Shared và Dev cần tải package từ Internet.

Hãy:

1. Vẽ DFD và xác định ít nhất **bốn trust boundary**.
2. Xây dựng ma trận source → destination → protocol/port → purpose → owner → action.
3. Đề xuất điểm thực thi chính sách tại cloud/VPC, Kubernetes và service identity.
4. Mô tả cách ngăn Staging dùng credential hoặc data Prod nhưng vẫn kiểm thử tương thích API.
5. Lập ít nhất **sáu test**, gồm ba luồng ALLOW và ba luồng DENY, có bằng chứng quan sát được.
6. Nêu phương án xử lý khi bật default deny khiến DNS hoặc health check ngừng hoạt động mà không mở toàn bộ egress.

**Gợi ý:** Dùng dịch vụ thanh toán sandbox/test chuyên biệt hoặc mock; dùng pipeline có quyền triển khai Prod tách khỏi quyền build Dev; cho log đi tới collector với danh tính và dữ liệu được kiểm soát; đưa tải package qua egress proxy hoặc nguồn được phê duyệt.

## 17. Checklist để review một thiết kế segmentation

- [ ] Có danh mục tài sản và owner gắn với đúng environment?
- [ ] Có bản đồ luồng **north–south, east–west và cross-environment**?
- [ ] Có ma trận source/destination/identity/service/port đã được duyệt?
- [ ] Mặc định chặn cross-environment ngoài các ngoại lệ cần thiết?
- [ ] Có đường đi vòng qua transit hub, peering, VPN, NAT, IPv6, private endpoint hay shared service không?
- [ ] Account/project, IAM, secrets và quyền control plane có phân tách theo môi trường?
- [ ] DB, backup, object storage, logs và dữ liệu thử nghiệm có tách quyền?
- [ ] DNS, NTP, registry, monitoring, health checks và DR có rule đủ hẹp để hoạt động?
- [ ] Có xác minh thực tế hoạt động của firewall/SG/NSG/ACL/CNI NetworkPolicy?
- [ ] Có test ALLOW **và** DENY, gồm kiểm thử qua API, IAM và đường dữ liệu?
- [ ] Mọi ngoại lệ có owner, lý do, ngày rà soát và đường thu hồi?
- [ ] Có giám sát thay đổi policy/route, hành vi bất thường và quy trình rollback?

**Kết luận:** Segmentation theo environment thành công khi **mỗi môi trường chỉ có những kết nối và quyền thật sự cần thiết**, ranh giới được thực thi ở **mạng, danh tính, ứng dụng và dữ liệu**, đồng thời có bằng chứng kiểm thử cho cả luồng được phép lẫn luồng bị chặn. Cấu trúc VLAN/VPC/namespace là điểm khởi đầu; **policy chính xác và việc vận hành liên tục** mới quyết định mức cô lập thực tế.
