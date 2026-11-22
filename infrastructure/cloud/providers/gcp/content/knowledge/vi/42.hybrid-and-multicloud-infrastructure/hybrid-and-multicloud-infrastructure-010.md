# Thực hành thiết kế tích hợp on-premises với dịch vụ GCP

Một doanh nghiệp hiếm khi chuyển toàn bộ hệ thống từ data center lên Google Cloud trong một lần. Sau khi triển khai API Java lên Cloud Run hoặc GKE, doanh nghiệp vẫn có thể giữ ERP, Active Directory, cơ sở dữ liệu cũ và các job batch tại chỗ. Nếu ứng dụng cloud không gọi được ERP, DNS phân giải sai hoặc các dải mạng chồng lấn, việc “triển khai thành công” không đồng nghĩa hệ thống đã hoạt động.

**Hybrid cloud integration** là thiết kế cho các hệ thống ở on-premises và Google Cloud trao đổi dữ liệu, xác thực, truy cập API và vận hành một cách có kiểm soát. Thiết kế cần giải quyết đồng thời **mạng, định tuyến, DNS, danh tính, dữ liệu, quan sát, bảo mật, khả năng phục hồi và chi phí**. Mục tiêu không chỉ là mở kết nối mà còn là chứng minh kết nối hoạt động đúng và có thể phục hồi khi một thành phần hỏng.

Bài này thuộc chương **Hạ tầng lai và đa đám mây** trong module **CLOUD_PROVIDERS_GCP**. Module giới thiệu Google Cloud từ tổ chức project, IAM, VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu; qua tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Chúng ta áp dụng kiến thức đó vào một thiết kế on-premises–GCP có thể đánh giá và kiểm thử.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Lập danh mục luồng tích hợp, owner, giao thức, lưu lượng và mục tiêu độ tin cậy.
- Phân biệt HA VPN, Cloud Interconnect, Cloud Router, VPC, Private Service Connect và private services access.
- Thiết kế CIDR, routing/BGP, DNS hai chiều và firewall cho hệ thống lai.
- Chọn phương thức truy cập phù hợp cho Cloud Run/GKE, Cloud SQL và Google APIs từ on-premises.
- Tách bảo mật mạng khỏi IAM, database permissions và application authentication.
- Dựng kiến trúc tham chiếu cùng routing matrix, port matrix và sơ đồ failure domains.
- Xây một lab theo từng bước, sử dụng lệnh `gcloud` và phép thử từ hai phía.
- Xác minh kết nối, độ trễ, phân giải tên, failover, bảo mật và cost baseline.
- Lập runbook cutover/rollback và checklist bàn giao cho nhóm mạng, DBA, SRE và ứng dụng.

## 1. Bài toán: hệ thống đơn hàng hoạt động ở hai môi trường

Giả sử doanh nghiệp có các thành phần sau:

| Thành phần | Vị trí hiện tại | Chức năng |
|---|---|---|
| ERP và master customer data | On-premises | Xử lý nghiệp vụ kế toán và đồng bộ khách hàng |
| Active Directory/LDAP | On-premises | Danh tính người dùng và hệ thống legacy |
| Java Spring Boot API | Dự kiến chuyển lên Google Cloud | Tiếp nhận và xử lý đơn hàng |
| Cloud SQL for PostgreSQL | Google Cloud | Dữ liệu đơn hàng mới |
| Cloud Storage | Google Cloud | File đính kèm, đối soát và export |
| Pub/Sub | Google Cloud | Sự kiện bất đồng bộ cho worker |
| Cloud Logging/Monitoring | Google Cloud | Log, metric, cảnh báo và điều tra |

Yêu cầu mẫu:

1. ERP tại chỗ gọi một endpoint nội bộ của Orders API bằng HTTPS, không phơi trực tiếp Internet.
2. Orders API ở GCP gọi một API nội bộ tại on-premises qua kết nối được kiểm soát.
3. Worker trên GCP truy cập database và Cloud Storage.
4. Một Java batch job tại chỗ có thể truy cập một dịch vụ GCP được phê duyệt, với IAM thích hợp.
5. Kết nối phải có dự phòng, quan sát và quy trình khắc phục sự cố.
6. Doanh nghiệp muốn di chuyển từng wave, giữ đường kết nối hybrid trong giai đoạn chuyển tiếp.

**Điều kiện quan trọng:** bảng dưới đây là dữ liệu giả định phục vụ đào tạo, không phải thông tin hệ thống thật. Region và địa chỉ thực tế phải được IPAM, Network và Security phê duyệt.

### Mục tiêu chấp nhận ví dụ

| Hạng mục | Mục tiêu thiết kế | Phương pháp xác minh |
|---|---|---|
| API từ ERP tới GCP | HTTPS qua private connectivity | DNS, route, TLS và API request |
| API từ GCP tới ERP | Chỉ đúng host/port đã cấp phép | Network path, firewall và app logs |
| Khả dụng WAN | Duy trì liên lạc khi một tunnel bị lỗi | Controlled failover rehearsal |
| Độ trễ | p95 không vượt ngưỡng do application owner đặt | Load test và tracing |
| Truy cập dữ liệu | Đúng IAM, DB role và chính sách dữ liệu | Negative/positive authorization tests |
| Khả năng phục hồi | Có runbook và rollback | Diễn tập được phê duyệt |
| FinOps | Xác định SKU và cost owner | Billing export và traffic measurements |

Không tự lấy “99,99% uptime” làm cam kết end-to-end; đó có thể là một SLA **có điều kiện** của riêng cấu hình HA VPN, không bao gồm ERP, DNS, ứng dụng và đối tác.

## 2. Kiến trúc tham chiếu đề xuất

Chọn một mô hình có network team quản lý Shared VPC, một project chạy ứng dụng và các tài nguyên dịch vụ GCP. Trong lab nhỏ có thể dùng một project duy nhất, nhưng vẫn nên tách quyền quản trị mạng khỏi quyền của workload.

~~~mermaid
flowchart LR
  subgraph DC["On-premises / Data center"]
    ERP[ERP / Java batch]
    DNSDC[Corporate DNS]
    FW[Firewall + VPN peer A/B]
    LDAP[IdP / AD]
    ERP --> FW
    DNSDC --> FW
    LDAP --> FW
  end
  subgraph GCP["Google Cloud / Hybrid VPC"]
    HA[HA VPN: hai interfaces và tunnels]
    CR[Cloud Router / BGP]
    DNSG[Cloud DNS private zones và forwarding]
    ILB[Regional internal Application Load Balancer]
    API[Orders API: Cloud Run / GKE]
    SQL[(Cloud SQL private IP)]
    GCS[Cloud Storage via Google APIs]
    OBS[Cloud Logging + Monitoring + Trace]
    HA --- CR
    HA --> ILB --> API
    HA --> DNSG
    API --> SQL
    API --> GCS
    API --> OBS
  end
  FW <--> HA
  ERP -. HTTPS private .-> ILB
  API -. HTTPS hybrid .-> FW
~~~

Sơ đồ thể hiện **logical data plane** và control plane. Cloud Router là dịch vụ quản lý BGP/routes; nó **không chuyển tiếp từng gói tin như một router appliance**. Gói tin thực tế đi theo Cloud VPN/VPC và các thành phần mạng tương ứng.

Trong một kịch bản Cloud Run khác, nguồn on-premises kết nối vào VPC qua Cloud VPN/Interconnect có thể được xem là internal đối với một số thiết lập ingress; tuy vậy, dùng **regional internal Application Load Balancer** với backend serverless NEG thường giúp có private VIP, DNS nội bộ và biên giới truy cập rõ ràng. Cần đối chiếu đúng loại load balancer và tài liệu Cloud Run hiện hành.

### Phân biệt ba luồng chính

1. **On-prem → GCP private workload:** ERP gọi `orders.gcp.corp.example` trỏ tới private VIP của internal load balancer.
2. **GCP workload → on-prem service:** API gọi `erp.corp.example` qua route BGP, firewall và DNS forwarding.
3. **On-prem → Google APIs:** Java batch gọi Cloud Storage/Secret Manager bằng endpoint được hỗ trợ qua **Private Google Access for on-premises hosts** hoặc lựa chọn được phê duyệt; đây **không** phải luồng đến private VIP của internal load balancer.

Cloud SQL private IP là đường thứ tư, có cơ chế kết nối riêng cần hiểu; không đưa Cloud SQL vào nhóm “Google API endpoint” khi thiết kế TCP 5432.

## 3. Lập bảng luồng ứng dụng trước khi cấu hình VPC

Cần liệt kê dependency có hướng và theo đúng ứng dụng thực tế. Ví dụ:

| Source | Destination | Protocol/port | Mục đích | Criticality | Owner |
|---|---|---|---|---|---|
| ERP on-prem | Orders API internal VIP | HTTPS 443 | Gửi đơn hàng | Critical | ERP team |
| Orders API | ERP on-prem | HTTPS 8443 | Xác thực / tra cứu mã | Critical | Integration team |
| Orders API | Cloud SQL | PostgreSQL 5432 | Đọc/ghi đơn hàng | Critical | DBA |
| Worker GCP | Cloud Storage | HTTPS 443 | Lưu file export | High | Data team |
| Batch on-prem | Cloud Storage API | HTTPS 443 | Upload file theo lịch | Medium | ETL team |
| GCP workload | Corporate DNS | UDP/TCP 53 qua forwarding | Phân giải tên legacy | High | Network |
| On-prem hosts | Cloud DNS inbound IP | UDP/TCP 53 | Phân giải private GCP FQDN | High | Network |
| App / infra | Cloud Monitoring | HTTPS 443 | Telemetry | High | SRE |

Bảng này **không phải danh sách firewall cuối cùng**. Cần bổ sung source CIDR, destination IP, identity, TLS mode, peak throughput, retries, maintenance window và evidence.

### Quy tắc tìm phụ thuộc

- Đọc config, DNS, firewall records, VPC Flow Logs và APM/traces.
- Xác nhận với application owner, DBA, Network và Security.
- Ghi các job chạy hằng đêm, cuối tháng hoặc chỉ lúc failover.
- Phân biệt “đã quan sát” với “đã được chủ hệ thống xác nhận”.
- Không xóa một dependency chỉ vì chưa có network flow trong vài ngày.

Nếu tích hợp cần đọc/ghi đồng bộ nhiều lần qua WAN, ưu tiên đánh giá **batching, caching, event-driven integration hoặc di chuyển database cùng application** trước khi mở rộng băng thông.

## 4. IP plan và DNS namespace

### Kế hoạch CIDR minh họa

| Vùng | CIDR / IP | Vai trò |
|---|---|---|
| On-prem user/app network | `10.60.0.0/16` | ERP, Java batch, nội bộ |
| On-prem DNS | `10.60.1.53` | DNS authoritative/recursive |
| Google Cloud VPC | `hybrid-vpc` | Mạng chính của ứng dụng |
| App subnet ở GCP | `10.80.10.0/24` | VM test và internal LB frontend |
| GKE Pod secondary range (nếu dùng) | `10.81.0.0/16` | Alias IP của GKE workloads |
| GKE Services secondary range (nếu dùng) | `10.82.0.0/20` | Kubernetes Service IP |
| Cloud SQL PSA allocation (ví dụ) | `10.90.0.0/16` | Dải dành cho service producer |
| Internal API VIP (ví dụ) | `10.80.10.50` | Frontend của internal LB |
| On-prem ASN | `65010` | BGP peer do doanh nghiệp quản lý |
| Cloud Router ASN | `64514` | BGP peer ở Google Cloud |

Các range là **ví dụ độc lập để học**. Khi triển khai thật:

1. Kiểm tra không trùng dải với on-premises, AWS/Azure, VPC, GKE secondary ranges, peer network hoặc site DR.
2. Dự phòng đủ địa chỉ cho GKE, subnet mới, service networking và growth.
3. Chọn Cloud Router ASN không xung đột với BGP thiết kế hiện có.
4. Xác nhận reserved/advertised prefixes ở tất cả đường VPN/Interconnect.
5. Không suy diễn rằng GCP VPC có một CIDR tổng hợp duy nhất: VPC là global, subnet là regional và các subnet/secondary ranges được gán cụ thể.
6. Khi có overlap, ưu tiên sửa IPAM hoặc thiết kế trung gian phù hợp, không mặc định NAT che mọi lỗi routing/DNS.

### Namespace DNS

Đề xuất phân quyền:

- `corp.example`: DNS server tại on-premises giữ quyền authoritative cho ERP và legacy services.
- `gcp.corp.example`: Cloud DNS private zone quản lý endpoint/định danh dịch vụ trong VPC.
- `orders.gcp.corp.example`: bản ghi A trỏ tới private VIP của internal load balancer.
- `erp.corp.example`: bản ghi A/CNAME trên on-prem DNS.
- `*.googleapis.com`: giải quyết theo phương án Google API private VIP khi cần, không trộn với domain nội bộ.

Tên `.example` được dùng để minh họa; trong production phải chọn zone nằm trong quyền quản trị DNS thực tế.

## 5. Chọn kết nối: HA VPN hay Cloud Interconnect?

| Tiêu chí | HA VPN | Dedicated / Partner Interconnect |
|---|---|---|
| Mạng vận chuyển | IPsec tunnel qua Internet | Kết nối mạng chuyên dụng hoặc qua nhà cung cấp |
| Khả dụng | Cần topology dự phòng phù hợp SLA | Cần redundancy thiết bị/attachment/location theo thiết kế |
| Cấp phát | Thường nhanh hơn nếu đã có peer | Cần phối hợp cross-connect hoặc partner |
| Khả năng mở rộng | Bị giới hạn bởi tunnel, peer, packet size và overhead | Phù hợp băng thông ổn định lớn |
| Bảo mật khi truyền | IPsec tích hợp | Không mặc định mã hóa end-to-end; xem HA VPN over Interconnect nếu cần |
| Routing | BGP động với Cloud Router | BGP động với Cloud Router |
| Chi phí | Tunnel hours, data transfer và liên quan | Port/VLAN attachment/provider/data transfer |
| Use case | Pilot, DR, lưu lượng vừa, triển khai sớm | Hybrid dài hạn, khối lượng dữ liệu lớn |

**HA VPN** được khuyến nghị khi cần kết nối IPsec có độ khả dụng cao. Hai interface/tunnel, peer redundancy và BGP configuration phải tuân thủ các topology được hỗ trợ để có mức SLA tương ứng; một tunnel đơn lẻ không tự được xem là 99,99%.

**Cloud Interconnect** là lựa chọn đáng giá khi cần băng thông hoặc latency ổn định hơn, nhưng vẫn phải thiết kế HA và bảo mật dữ liệu. Không gọi “private circuit” đồng nghĩa “tự động mã hóa”.

### Cách quyết định

- **Pilot 1–2 ứng dụng:** thường bắt đầu HA VPN, nếu peer và bandwidth đáp ứng.
- **Dữ liệu sao chép nhiều TB/ngày:** tính cả thời gian truyền, throughput và chi phí Interconnect.
- **Latency rất chặt giữa API và DB:** đo trước; nếu WAN RTT làm hỏng SLO, ưu tiên xem lại ranh giới ứng dụng/dữ liệu.
- **Multi-cloud:** cân nhắc Cross-Cloud Interconnect, Network Connectivity Center và kiến trúc routing phù hợp, không mặc định peering/VPN tự truyền transit qua mọi cloud.

Không chọn chỉ theo giá tunnel. Cần so sánh **cost + SLO + bandwidth + HA + vận hành + yêu cầu bảo mật**.

## 6. HA VPN, Cloud Router và BGP: thiết kế trước khi nhập lệnh

Trong kịch bản ví dụ, Google Cloud có HA VPN gateway với **hai interface**. Phía on-premises cũng cần thiết bị/peer được thiết kế dự phòng. Mỗi tunnel gắn với Cloud Router interface/BGP peer tương ứng.

~~~mermaid
flowchart LR
  subgraph DC["On-prem"]
    P0[Peer A / interface A]
    P1[Peer B / interface B]
  end
  subgraph GCP["Google Cloud"]
    I0[HA VPN interface 0]
    I1[HA VPN interface 1]
    R[Cloud Router: BGP route control]
    V[VPC 10.80.10.0/24]
  end
  P0 <--> |IPsec tunnel 0| I0
  P1 <--> |IPsec tunnel 1| I1
  I0 --- R
  I1 --- R
  I0 --> V
  I1 --> V
~~~

### Thiết kế BGP

- Google Cloud dùng ASN `64514`; on-premises dùng ASN `65010`.
- Hai tunnel có hai địa chỉ BGP link-local riêng; chẳng hạn `169.254.21.0/30` và `169.254.22.0/30`, nếu được phép và chưa sử dụng.
- Cloud Router có thể nhận route `10.60.0.0/16` từ on-premises.
- On-premises nhận prefix GCP được quảng bá phù hợp, ví dụ `10.80.10.0/24`.
- Các range Cloud SQL PSA, Cloud DNS forwarding hoặc Google API VIP cần **quảng bá bổ sung** trong trường hợp có yêu cầu, không nghĩ BGP mặc định tự biết.
- Khi dùng active-active hoặc active-passive, BGP priorities/MED và thông số của peer cần nhất quán theo topology đã chọn.

Cloud Router quản lý các BGP sessions và learned/advertised routes, **không có packet forwarding appliance của riêng nó**. Khi BGP báo `ESTABLISHED` vẫn cần kiểm tra traffic hai chiều, DNS, firewall và application TLS.

### Global vs regional routing

Cloud Router thuộc region; VPC có thể cấu hình dynamic routing mode regional hoặc global. Nếu workload trải nhiều region và on-premises cần truy cập qua tunnel ở một region, cần thiết kế dynamic route advertisement/learning, failover và latency theo topology. Global routing không có nghĩa HA tự xuất hiện hoặc mọi tuyến được tối ưu giống nhau.

## 7. Thực hành phần hạ tầng nền bằng gcloud

**Các lệnh sau là tài liệu hướng dẫn, không được chạy trên production nếu chưa có phê duyệt.** Thay `PROJECT_ID`, region và CIDR theo IPAM, kiểm tra chính sách tổ chức, billing và IAM. Để có kết nối on-premises thật, còn cần cấu hình thiết bị VPN đối tác, tunnel và BGP peer; ví dụ này **không tự hoàn tất VPN**.

### Bước 1: Chọn project và bật API

~~~bash
gcloud config set project PROJECT_ID
gcloud services enable compute.googleapis.com dns.googleapis.com
~~~

Quyền thực thi yêu cầu vai trò phù hợp như Compute Network Admin và quyền quản lý Cloud DNS. Không dùng Owner ở production chỉ để thao tác nhanh hơn.

### Bước 2: Tạo VPC custom và subnet

~~~bash
gcloud compute networks create hybrid-vpc \
  --subnet-mode=custom \
  --bgp-routing-mode=GLOBAL \
  --project=PROJECT_ID

gcloud compute networks subnets create hybrid-apps-sea1 \
  --network=hybrid-vpc \
  --region=asia-southeast1 \
  --range=10.80.10.0/24 \
  --project=PROJECT_ID
~~~

Ở ví dụ, global dynamic routing phục vụ kiến trúc có thể mở rộng đa region. Nếu hệ thống chỉ cần regional routing và muốn kiểm soát chặt route propagation, cân nhắc regional mode theo thiết kế đã duyệt.

Lệnh trên chưa tạo GKE secondary ranges hay proxy-only subnet. Đối với GKE VPC-native hoặc internal Application Load Balancer, cần chuẩn bị các subnet/range riêng theo mô hình đã chọn.

### Bước 3: Tạo Cloud Router và HA VPN gateway

~~~bash
gcloud compute routers create hybrid-router-sea1 \
  --network=hybrid-vpc \
  --region=asia-southeast1 \
  --asn=64514 \
  --project=PROJECT_ID

gcloud compute vpn-gateways create hybrid-ha-vpn \
  --network=hybrid-vpc \
  --region=asia-southeast1 \
  --stack-type=IPV4_ONLY \
  --project=PROJECT_ID
~~~

HA VPN gateway tạo hai external interface IP phù hợp. **Đây chưa phải tunnel hoạt động.** Tiếp theo Network team cần:

1. Tạo external VPN gateway resource mô tả peer on-premises.
2. Chọn hai peer interfaces/devices và hai Google HA VPN interfaces.
3. Tạo hai IPsec tunnels với shared secret được quản lý an toàn.
4. Tạo Cloud Router interface/BGP peer cho mỗi tunnel.
5. Cấu hình BGP, IPsec/IKE parameters, routes và firewall trên thiết bị on-premises.
6. Xem session state, received/advertised routes và failover behavior.

Các lệnh tạo tunnel/peer phụ thuộc vendor, peer IPs, key và BGP link-local, nên không đưa một bộ lệnh cứng có thể gây cấu hình sai vào lab chung. Dùng **HA VPN setup wizard** và tài liệu của nhà cung cấp thiết bị để hoàn tất.

### Bước 4: Kiểm tra trạng thái (read-only)

~~~bash
gcloud compute vpn-gateways describe hybrid-ha-vpn \
  --region=asia-southeast1 --project=PROJECT_ID

gcloud compute vpn-tunnels list --project=PROJECT_ID

gcloud compute routers get-status hybrid-router-sea1 \
  --region=asia-southeast1 --project=PROJECT_ID

gcloud compute routes list --project=PROJECT_ID
~~~

Kiểm tra cả phía on-premises bằng công cụ của thiết bị mạng: IPsec SAs, BGP state, learned routes, interface errors, bandwidth và failover. Không kết luận đạt chỉ vì GCP Console có hai tunnel resources.

## 8. Firewall: cho phép đúng luồng, không mở cả mạng

VPC firewall chỉ giải quyết một lớp trong đường đi. Thiết kế phải bao gồm on-prem firewall, route, DNS, TLS và auth.

Ví dụ cho phép một workload test trên Compute Engine nhận HTTPS **từ on-premises** theo tag:

~~~bash
gcloud compute firewall-rules create allow-erp-to-test-api \
  --network=hybrid-vpc \
  --direction=INGRESS \
  --source-ranges=10.60.0.0/16 \
  --allow=tcp:443 \
  --target-tags=hybrid-api \
  --project=PROJECT_ID
~~~

Đây là mẫu **VM firewall rule**, không phải cấu hình firewall đầy đủ cho internal Application Load Balancer hoặc Cloud Run. Nếu backend dùng regional internal Application Load Balancer, còn cần proxy-only subnet, backend allow rules và health check traffic theo đúng loại load balancer. Không áp dụng `target-tags` trực tiếp cho Cloud Run rồi nghĩ đã bảo vệ dịch vụ.

### Ma trận bảo mật tối thiểu

| Luồng | Source | Destination | Port | Kiểm soát |
|---|---|---|---|---|
| ERP → API | On-prem app subnet | Internal LB VIP | 443 | HTTPS, token/mTLS, route và firewall |
| API → ERP | GCP workload egress | ERP VIP | 8443 | Firewall hai phía, TLS và auth |
| App → DB | GCP subnet/identity | Cloud SQL private IP | 5432 | Private connectivity, DB role, TLS |
| On-prem batch → Google API | On-prem subnet | VIP private/restricted | 443 | DNS, route, IAM và service scope |
| Hybrid DNS | On-prem DNS / Cloud DNS | Respective DNS resolver | UDP/TCP 53 | ACL, forwarding, return route |
| Monitoring | Workload / agent | GCP telemetry APIs | 443 | IAM, egress policy, log hygiene |

**TLS và IAM không được thay bằng VPN:** IPsec bảo vệ tunnel, còn application endpoint cần TLS, danh tính và quyền truy cập riêng. Với Cloud SQL, database user và IAM/network permissions là các lớp khác nhau.

## 9. Hybrid DNS hai chiều

Hybrid thường thất bại ở DNS dù BGP và TCP đều hoạt động. Giải pháp là giữ authoritative zone ở đúng nơi và dùng forwarding có chủ đích.

### On-premises truy vấn tên GCP

- Cloud DNS có **private zone** `gcp.corp.example` gắn với `hybrid-vpc`.
- Bản ghi `orders.gcp.corp.example` trả về internal LB VIP.
- Tạo **Cloud DNS server policy với inbound forwarding** để có forwarding IP phù hợp.
- DNS on-premises dùng conditional forward `gcp.corp.example` tới IP inbound forwarding do Cloud DNS cấp trong region của đường hybrid.
- Firewall/routing cho phép truy vấn UDP và TCP 53 và đường phản hồi.

**Không** tự coi `169.254.169.254` là DNS server dùng được từ on-premises; đây là resolver metadata của môi trường GCP VM, không phải địa chỉ DNS forwarding công khai cho data center.

### GCP truy vấn tên on-premises

- Tạo Cloud DNS **forwarding zone** cho `corp.example` hoặc một subdomain cụ thể, trỏ tới DNS on-premises `10.60.1.53`.
- Không cấu hình vòng lặp: ví dụ GCP forward toàn `corp.example` về on-prem, rồi on-prem lại forward toàn bộ domain về GCP.
- Đối với forwarding target là DNS on-premises qua VPN/Interconnect, Cloud DNS thường phát truy vấn từ **`35.199.192.0/19`**, không từ IP VM đang gửi yêu cầu.
- On-prem firewall phải cho phép UDP/TCP 53 từ `35.199.192.0/19`.
- On-prem routing cần đường về `35.199.192.0/19` qua **cùng VPC network** được dùng để chuyển yêu cầu, thường bằng custom BGP advertisement từ Cloud Router.
- DNS target nhận query phải là máy gửi reply đúng theo điều kiện source address, không nhờ máy khác trả trực tiếp thay.

### Bảng kiểm tra DNS

| Nguồn | FQDN | Kết quả mong đợi |
|---|---|---|
| ERP on-prem | `orders.gcp.corp.example` | `10.80.10.50` (VIP mẫu) |
| GCP VM test | `erp.corp.example` | IP nội bộ ERP, ví dụ `10.60.20.20` |
| On-prem client | `storage.googleapis.com` | Endpoint phù hợp chính sách Private Google Access |
| GCP worker | `corp.example` | Dữ liệu đúng từ on-prem authoritative DNS |

Lệnh kiểm chứng:

~~~bash
# Chạy tại on-prem host
nslookup orders.gcp.corp.example
dig orders.gcp.corp.example

# Chạy trên GCP VM test
nslookup erp.corp.example
dig erp.corp.example
~~~

Nếu môi trường không cài `dig`, dùng `nslookup` hoặc công cụ DNS tương đương. Kiểm tra authoritative/recursive behavior, TTL và kết quả từng resolver; một câu lệnh thất bại không đủ để xác định lỗi ở IPsec hay Cloud DNS.

## 10. On-premises gọi Google APIs qua Private Google Access

Cloud Storage, Secret Manager và các API GCP khác thường được gọi qua domain `googleapis.com`. Khi client ở on-premises muốn truy cập API này qua Cloud VPN/Interconnect, có phương án **Private Google Access for on-premises hosts**, khác với việc bật Private Google Access trên một GCP subnet VM.

### Hai VIP quan trọng

| Domain | IPv4 VIP range | Phạm vi sử dụng |
|---|---|---|
| `private.googleapis.com` | `199.36.153.8/30` | Phần lớn Google APIs/services đủ điều kiện |
| `restricted.googleapis.com` | `199.36.153.4/30` | Các API hỗ trợ VPC Service Controls |

Hai dải này **không được định tuyến trên Internet công cộng**. Để on-premises sử dụng chúng:

1. Chọn domain tùy theo dịch vụ/kiểm soát dữ liệu.
2. Cấu hình DNS nội bộ ánh xạ các API domain liên quan sang VIP đúng.
3. Thiết lập BGP/route từ on-premises tới VIP qua tunnel hoặc VLAN attachment.
4. Trên GCP VPC, cần route tới VIP với next hop default Internet gateway; gói tin tới VIP vẫn đi trong mạng Google theo cơ chế được công bố.
5. Đảm bảo DNS/firewall/return routing phù hợp và kiểm thử API thực.
6. Cấp IAM và bật API tại project liên quan khi workload/project cần sử dụng.

Có thể dùng Cloud Router **custom advertisements** cho VIP range. Không quảng bá cả dải `0.0.0.0/0` từ Google Cloud về on-premises chỉ để truy cập Google APIs nếu chưa có thiết kế egress.

### Điều không được suy diễn

- **Không phải mọi domain** `*.googleapis.com` hoặc Google service đều hỗ trợ một VIP tùy chọn.
- `restricted.googleapis.com` cố ý **loại bỏ** nhiều API không thuộc phạm vi VPC Service Controls.
- VIP hỗ trợ HTTP-based protocols trên TCP (HTTP/HTTPS/HTTP2), không phải một mạng dành cho arbitrary TCP/UDP service.
- Private Google Access không tự cấp quyền IAM hoặc thay đổi chính sách dữ liệu.
- Private Google Access cho **on-premises hosts** không đòi hỏi bật subnet flag như VM trong VPC; đó là hai quy trình cấu hình riêng.

Một số domain như `*.run.app`, `*.pkg.dev` hoặc `storage.cloud.google.com` có quy tắc DNS riêng. Dùng bảng **Configure Private Google Access for on-premises hosts** để tránh override toàn bộ DNS khiến dịch vụ khác hỏng.

## 11. On-premises truy cập Cloud SQL private IP

Cloud SQL for PostgreSQL có phương án private IP sử dụng **private services access (PSA)** hoặc các tính năng kết nối riêng được hỗ trợ trong kịch bản khác. Với PSA, Cloud SQL đặt trong service producer network kết nối qua private services connection; đó **không phải** một VM nằm trực tiếp trong `10.80.10.0/24`.

### Luồng mẫu

~~~mermaid
flowchart LR
  A[Java batch on-prem] --> B[Cloud VPN / Interconnect]
  B --> C[Hybrid VPC]
  C --> D[Private services access connection]
  D --> E[(Cloud SQL PostgreSQL private IP)]
~~~

Đường đi thật phải có **cả chiều gửi và chiều trả lời**. Quy tắc quan trọng:

- Dành một allocated IP range (ví dụ `10.90.0.0/16`) không chồng lấn nguồn và GCP networks.
- Tạo private services access connection và gắn Cloud SQL vào network phù hợp.
- Cloud Router cần **quảng bá các prefix cần thiết của producer allocation tới on-premises**; không mặc định subnet advertisements bao gồm allocation từ service producer.
- Thiết kế **export custom routes** cho service producer peering để network producer biết đường trả về các prefix on-premises khi kịch bản yêu cầu.
- Cloud VPN/Interconnect phải kết thúc trong VPC có private services access connection liên quan; **VPC Network Peering không hỗ trợ transitive routing** chỉ vì nhiều VPC cùng peering với nhau.
- Kiểm tra route, TLS, DB credentials/roles, timeouts và giới hạn kết nối.

Tài liệu Cloud SQL cho phép nguồn on-premises đã kết nối tới VPC qua Cloud VPN/Interconnect truy cập instance bằng private IP khi cấu hình hoàn chỉnh. Nếu chọn **Private Service Connect endpoint cho Cloud SQL** thay cho PSA, hãy theo quy trình PSC riêng: endpoint IP, service attachment/service connection policy, DNS và khả năng truy cập của từng network; không copy các bước PSA sang PSC.

### Rủi ro latency

Một Java service tại chỗ đọc/ghi database Cloud SQL qua WAN có thể tạo hàng trăm round trip mỗi transaction. Mặc dù TCP 5432 thông, p95 latency và transaction timeout vẫn có thể vượt SLO. Khi trường hợp này xuất hiện:

- Tối ưu số lượng query, batching và connection pool.
- Tránh N+1 queries và thao tác chatty giữa app và DB.
- Đánh giá di chuyển app cùng DB theo wave hoặc dùng API tích hợp thay vì direct JDBC qua WAN.
- Thử nghiệm failover, connection reuse, transaction retry và data consistency.

**Không xem trực tiếp JDBC qua VPN là thiết kế mặc định dài hạn** khi một API/service boundary phù hợp hơn.

## 12. On-premises gọi Cloud Run hoặc GKE private API

Có nhiều cách để công bố một API nội bộ của Google Cloud:

| Backend | Mẫu phù hợp | Điều cần bổ sung |
|---|---|---|
| Compute Engine VM/instance group | Internal passthrough hoặc internal Application Load Balancer | Firewall, health check, TLS, backend pool |
| GKE workload | Internal LoadBalancer Service hoặc internal Application Load Balancer/Ingress/Gateway | Cluster network, NEGs, backend policies |
| Cloud Run | Internal Application Load Balancer với serverless NEG, hoặc đường internal được hỗ trợ | Cloud Run ingress, IAM auth, TLS và DNS |
| Managed service có PSC | PSC endpoint khi sản phẩm hỗ trợ | Endpoint IP, connection/consumer policies, quotas |

### Với Cloud Run

Đối với API chỉ dùng nội bộ, xem `ingress=internal` theo hướng dẫn Cloud Run. Tài liệu Cloud Run xếp request từ nguồn on-premises kết nối qua Cloud VPN/Interconnect vào một số nguồn **internal**, nhưng behavior phụ thuộc cách truy cập, VPC và điều kiện ingress được hỗ trợ.

Nếu sử dụng internal Application Load Balancer:

1. Tạo regional internal Application Load Balancer và serverless NEG phù hợp với Cloud Run service.
2. Đặt Cloud Run ingress để chỉ cho phép đường nội bộ thích hợp.
3. Cấp internal VIP và tên DNS `orders.gcp.corp.example`.
4. Cấu hình TLS certificate được client tin cậy; dùng chính sách mTLS hoặc xác thực ứng dụng nếu cần.
5. Cấp **run.invoker / IAM** cho caller theo mô hình auth của Cloud Run, hoặc có tầng proxy thực hiện auth đã được phê duyệt.
6. Kiểm chứng rằng request từ Internet công cộng không truy cập được backend ngoài ý muốn.

**Network ingress và IAM là hai cổng kiểm soát khác nhau.** Đặt ingress internal không có nghĩa mọi tài nguyên trên mạng được phép gọi API với quyền nghiệp vụ bất kỳ.

### Với GKE

GKE cần thêm:

- Pod/service CIDR và node subnet không trùng on-premises.
- Workload scheduling, service exposure và firewall.
- Internal load balancer phù hợp TCP/HTTP yêu cầu.
- Network policy, service account và workload identity.
- DNS resolution, readiness/health checks và rolling deployment.
- Cách IP của pods/services được route hoặc được ẩn sau load balancer; không giả định on-premises phải có route tới mọi Pod CIDR.

### Khi nào dùng API integration thay vì network-level DB access?

Nếu on-premises chỉ cần gọi một số nghiệp vụ đơn hàng, nên ưu tiên **HTTPS API có authentication, idempotency và retry** hơn việc cấp direct SQL access qua WAN. API boundary giới hạn quyền và giảm coupling giữa schema và các hệ thống khác nhau.

## 13. Identity, authentication và zero-trust

Kết nối IPsec/Interconnect không trả lời câu hỏi “ứng dụng nào có quyền đọc dữ liệu?”. Thiết kế nên chia ít nhất bốn tầng:

| Tầng | Biện pháp | Ví dụ |
|---|---|---|
| Network | Route, firewall, segmentation, private endpoint | Chỉ ERP subnet gọi API VIP:443 |
| Transport | TLS/mTLS và certificate validation | HTTPS với CA được tin cậy |
| Identity | Workload identity, OIDC hoặc service account | ERP client lấy JWT được cấp hợp lệ |
| Authorization | IAM, app roles và DB grants | Service chỉ đọc bucket hoặc DB schema được phép |

### On-premises workload cần Google Cloud IAM

Tránh nhúng **service account JSON key dài hạn** trong Java application, Docker image hoặc batch script. Khi đáp ứng điều kiện, dùng **Workload Identity Federation** cho nguồn bên ngoài Google Cloud để đổi credentials của IdP bên ngoài lấy token Google Cloud ngắn hạn. Kiểm tra provider/issuer, audience, attribute mapping và permission bindings.

Application Default Credentials là một cơ chế mà Google client libraries có thể sử dụng; trên on-premises, cần cấu hình credential source phù hợp (ví dụ federation), không mặc định giống GCE metadata server.

### Các dữ liệu cần bảo vệ

- API token, session cookie, DB password, certificate private keys và IPsec pre-shared secrets.
- Dữ liệu cá nhân, dữ liệu tài chính, mã khách hàng hoặc payload ERP.
- VPN peer public IPs và sơ đồ mạng thật trong báo cáo ngoài phạm vi nội bộ.
- Trace/log attributes không được chứa secret và thông tin không được phép.

**Nguyên tắc:** định tuyến xác định gói tin đi được tới đâu, identity/authz xác định bên nào được thực hiện hành động.

## 14. Observability end-to-end cho hybrid integration

Một hybrid connection có thể “UP” nhưng ứng dụng vẫn lỗi do DNS, certificate, database lock hoặc timeouts. Cần đo cả **network** lẫn **application**.

### Tầng network

Theo dõi:

- VPN tunnel status, bytes in/out, packet drops và retransmission.
- BGP session state, route count, route changes và failover.
- Cloud Router advertised/learned routes.
- Latency/packet loss và bandwidth theo tunnel/Interconnect.
- Cloud DNS query errors, latency và forwarding failures.
- Firewall denied traffic và route reachability tests.

### Tầng ứng dụng

- HTTP/gRPC request rate, p95/p99 latency và status codes.
- JDBC connection acquisition time, active/idle connections, SQL errors.
- Retry count, circuit breaker state, queue age và dead-letter.
- End-to-end transaction success (ví dụ ERP nhận order acknowledgment).
- Trace context qua ERP gateway, API Java và DB/integration worker khi có instrumentation.
- Batch completion time và data reconciliation drift.

### Monitoring và cảnh báo gợi ý

| Alert | Trigger theo nguyên tắc | Tác động |
|---|---|---|
| VPN tunnel down | Một tunnel mất trong topology dual-tunnel | Cảnh báo suy giảm dự phòng |
| All hybrid paths unreachable | Không còn đường khả dụng | P1/P0 tùy nghiệp vụ |
| BGP peer lost | BGP session không established | Nguy cơ mất route |
| DNS forwarding errors | Query thất bại kéo dài | Service discovery lỗi |
| API p95 latency tăng | Vượt SLO đủ thời gian | Điều tra WAN/app/db |
| Repeated auth errors | 401/403, TLS cert errors | Identity/cert policy sai |
| DB connections exhausted | Pool wait và lỗi kết nối tăng | Kiểm tra sizing và WAN retry |
| Cost increase | Hybrid egress/Interconnect SKU tăng | Điều tra workload hoặc batch |

Đặt alert theo **ngưỡng đã benchmark**, tránh lấy con số tùy tiện rồi gây nhiều false positives. Mỗi alert cần owner, đường link dashboard và runbook cụ thể.

### Công cụ điều tra

- Cloud Monitoring cho VPN, Cloud Router, load balancer và service metrics.
- Cloud Logging cho Cloud DNS/VPC firewall/ứng dụng nếu các loại log đó được bật.
- Network Intelligence Center Connectivity Tests để phân tích đường kết nối được hỗ trợ.
- VPC Flow Logs/Flow Analyzer để quan sát lưu lượng trong phạm vi có ghi nhận.
- Cloud Trace/OpenTelemetry để tìm bottleneck của request Java.

Flow Logs không luôn hiển thị mọi gói; sampling và aggregation có thể ảnh hưởng khả năng đối chiếu. Cần kết hợp với metric và log từ phía on-premises.

## 15. Runbook lab: kiểm chứng từ hai phía

**Lab đề xuất dùng sandbox và thiết bị VPN hoặc môi trường mô phỏng do tổ chức quản lý.** Không tự cấu hình peer production hoặc thay đổi routing/firewall thật mà chưa được phê duyệt.

### Bước 1: Chuẩn bị danh mục

1. Ghi project ID, region, VPC/subnet, IPAM và DNS zones.
2. Ghi on-prem CIDR, peer public IPs, vendor, BGP ASN và owner.
3. Ghi các endpoint thử nghiệm (không chứa secret).
4. Phê duyệt security/route/failover policy và thời gian lab.
5. Đặt budget và cleanup plan.

### Bước 2: Provision hạ tầng mạng nền

Làm theo phần 7 để tạo VPC, subnet, Cloud Router và HA VPN gateway. Hoàn tất tunnel/peer BGP dựa trên hướng dẫn sản phẩm và thiết bị doanh nghiệp.

### Bước 3: Tạo backend test độc lập

Để kiểm tra kết nối ban đầu mà chưa triển khai Cloud Run/SQL, dùng một **Compute Engine VM test với internal IP và HTTPS service được phê duyệt**, hoặc internal service có sẵn. Gắn firewall tag `hybrid-api` nếu dùng firewall rule minh họa, và triển khai certificate hợp lệ.

Không mở backend cho toàn Internet. Đặt dữ liệu mock, không dùng thông tin khách hàng thật.

### Bước 4: Kiểm tra route

Từ on-premises:

~~~bash
# Linux on-prem: chọn lệnh phù hợp OS
ip route get 10.80.10.50
traceroute 10.80.10.50

# Kết nối TCP; timeout không phải lúc nào do firewall
nc -vz 10.80.10.50 443
~~~

Từ GCP VM test:

~~~bash
ip route get 10.60.20.20
nc -vz 10.60.20.20 8443
~~~

`traceroute` qua VPN/đường private có thể thiếu hop do ICMP không được phản hồi. Đừng lấy việc không thấy hop làm bằng chứng không có route; ưu tiên BGP route table và phép thử TCP/HTTP thật.

### Bước 5: Kiểm tra DNS

~~~bash
# Từ on-premises:
nslookup orders.gcp.corp.example

# Từ GCP VM:
nslookup erp.corp.example
~~~

Đối chiếu IP trả về với IPAM, xác nhận không có response từ resolver ngoài ý muốn. Nếu DNS lỗi nhưng TCP theo IP đúng, điều tra forwarding zone, inbound DNS policy, return route và firewall UDP/TCP 53.

### Bước 6: Kiểm tra HTTPS và authentication

~~~bash
curl -v --connect-timeout 5 --max-time 15 \
  https://orders.gcp.corp.example/health
~~~

Phải dùng tên khớp TLS certificate. **Không dùng `curl -k` làm cách xác nhận bảo mật.** Nếu API yêu cầu token, bổ sung authentication phù hợp thay vì bỏ auth cho production. Đối chiếu HTTP status, certificate, latency và application logs.

### Bước 7: Kiểm tra Cloud SQL/private Google APIs (nếu thuộc scope)

- Với Cloud SQL: kiểm tra TCP 5432, TLS, database identity/permissions, query tối thiểu và transaction.
- Với Google APIs: kiểm tra DNS của `storage.googleapis.com`, VIP route, API response và IAM của caller.
- Không bắt đầu bằng thao tác ghi/xóa dữ liệu production; dùng môi trường thử nghiệm và nguyên tắc least privilege.

### Bước 8: Diễn tập failover có kiểm soát

1. Đo baseline: API p95, TCP errors, BGP routes và traffic phân phối qua tunnels.
2. Tắt **một** tunnel hoặc peer trong maintenance window của lab.
3. Xác minh route hội tụ và giao dịch tiếp tục theo tiêu chí đã đặt.
4. Đo gián đoạn thực tế; không suy theo SLA.
5. Khôi phục tunnel và xác minh trạng thái redundant.
6. Nếu có khả năng, kiểm tra tiếp lỗi DNS forwarding target hoặc mất một backend.
7. Ghi sự kiện, kết quả, vấn đề và quyết định kiến trúc.

Không thử cắt toàn bộ WAN production chỉ để đo HA VPN.

## 16. Java/Spring Boot integration với API nội bộ

Ứng dụng Java nên giao tiếp qua **FQDN ổn định** và có timeout, retry policy, idempotency và telemetry. Đừng hardcode private IP của một máy chủ vào source code.

### Ví dụ Java 17 HTTP client

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class HybridApiCheck {
    public static void main(String[] args) throws Exception {
        String endpoint = "https://orders.gcp.corp.example/health";

        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

        HttpRequest request = HttpRequest.newBuilder(URI.create(endpoint))
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        );

        System.out.println("HTTP status: " + response.statusCode());

        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                "Hybrid API did not pass health check"
            );
        }
    }
}
~~~

Đây là **smoke test** cho một endpoint health được phép truy cập. Trong hệ thống thật, yêu cầu token/OIDC hoặc mTLS, logging có cấu trúc và tracing; không in request body nhạy cảm hay token. `HttpClient` kiểm tra TLS theo trust store của JVM; cần cài CA của doanh nghiệp đúng chính sách, không vô hiệu hóa hostname verification.

### Cấu hình ứng dụng Spring

Ví dụ một phần cấu hình:

~~~yaml
hybrid:
  erp:
    base-url: "https://erp.corp.example:8443"
    connect-timeout-ms: 3000
    read-timeout-ms: 10000

spring:
  datasource:
    url: "jdbc:postgresql://CLOUD_SQL_PRIVATE_IP:5432/orders"
    username: "DB_USER"
    # Không đặt password thật trong source; đọc từ secret/environment phù hợp.
~~~

Ví dụ không đại diện cho mọi property của Spring Framework. Giá trị timeout cần cấu hình trên HTTP client/connection pool được ứng dụng dùng. Với Cloud SQL, cân nhắc Cloud SQL connectors/Auth Proxy theo kịch bản, identity, TLS và giới hạn connection của instance.

### Retry và circuit breaker

Trong kết nối hybrid, lỗi mạng tạm thời có thể xảy ra khi route hội tụ:

- Chỉ retry những thao tác an toàn/idempotent hoặc có idempotency key.
- Dùng exponential backoff với jitter, giới hạn retry budget.
- Không retry vô hạn khi network outage.
- Dùng circuit breaker hoặc queue để bảo vệ dependency.
- Log trace ID và loại lỗi, không log bearer token.
- Thực hiện canary và xác minh transaction semantics.

Thay đổi một timeout tùy tiện có thể tăng queue length và làm mất SLO. Cần đo p95/p99 và xác nhận timeout/retry không nhân traffic gây bão lỗi.

## 17. Phương án truyền dữ liệu và đồng bộ

Không phải mọi integration cần truy vấn đồng bộ qua WAN. Chọn cơ chế theo consistency, latency và RPO:

| Tình huống | Kiểu tích hợp gợi ý | Rủi ro cần quản lý |
|---|---|---|
| ERP cần phản hồi tức thời | HTTPS/gRPC đồng bộ | Latency WAN, timeout, auth |
| Đồng bộ trạng thái cuối ngày | Batch file/Cloud Storage có kiểm chứng | Scheduling, checksum, encryption |
| Sự kiện đơn hàng | Pub/Sub thông qua producer được cấp quyền | Duplicate/out-of-order, idempotency |
| Dữ liệu database đổi liên tục | CDC/migration/replication theo scenario | Lag, schema compatibility, RPO |
| Báo cáo/analytics | ETL/ELT theo lịch hoặc streaming pipeline | Chi phí truyền, schema evolution |
| Legacy file share | Transfer pipeline hoặc storage bridge phù hợp | File semantics, locks, permissions |

Với database, **Database Migration Service** có thể phục vụ các cặp nguồn–đích được hỗ trợ; không phải hệ thống đồng bộ hai chiều active-active mặc định. Nếu hai môi trường cùng ghi dữ liệu, thiết kế conflict resolution và ownership rõ ràng.

### Dữ liệu nhạy cảm

Mỗi luồng phải có:

- Data owner và classification.
- Vị trí lưu trữ và retention.
- Encryption in transit/at rest.
- IAM và application authorization.
- DLP/validation nếu cần.
- Reconciliation, retry và dead-letter plan.
- Số lượng dữ liệu/giờ, spike và giới hạn cost.

## 18. Độ tin cậy, RTO/RPO và failure domains

Một hệ thống hybrid có thêm phụ thuộc vào WAN, DNS và peer device. Thiết kế phải nêu rõ failure domain:

| Lỗi | Tác động | Phương án |
|---|---|---|
| Mất một VPN tunnel | Giảm redundancy/có thể giảm capacity | Tunnel còn lại và BGP convergence |
| Mất peer on-prem | Mất đường nếu peer single point of failure | Hai peer devices/locations |
| DNS on-prem lỗi | GCP không resolve legacy | Nhiều DNS targets/forwarders |
| Cloud DNS forwarding lỗi | Lookup fail, API không gọi được | Kiểm tra đường trả về và DNS ACL |
| Cloud SQL unavailable | Transaction thất bại | HA/backup/DR, retry hợp lý |
| Hybrid WAN chậm | API p95 tăng, DB timeout | Cache, queue, circuit breaker, boundary redesign |
| Region GCP không khả dụng | Internal LB/API/DB ảnh hưởng | Regional DR theo RTO/RPO đã xác nhận |
| Token issuer/IdP lỗi | Không lấy token mới | Thiết kế cache/token TTL và kế hoạch phục hồi |

HA VPN bảo vệ một phần kết nối, **không tự bảo vệ source ERP, DNS server hoặc một region**. Phải có error budget/SLO end-to-end và test failover thực.

### Region failover

Nếu ứng dụng có phương án DR ở region khác, cần:

1. VPC routing mode và BGP/Interconnect route phù hợp.
2. DNS failover hoặc traffic routing có TTL/thời gian hội tụ hợp lý.
3. Database replication/restore và RPO được kiểm chứng.
4. IAM, secrets, certificates và network policies đồng nhất.
5. Test các client on-premises có thể tới region dự phòng.
6. Chi phí vận hành đường dự phòng được tính từ đầu.

Không xem “Cloud Router global routing” là tự động cân bằng traffic đến một deployment ở region dự phòng khi chưa có service-level failover.

## 19. Cost model và FinOps cho kết nối hybrid

**Chi phí hybrid** không chỉ là phí VM hay VPN tunnel:

- HA VPN tunnel hours và data transfer charges.
- Cloud Interconnect ports/attachments/provider fees, nếu dùng.
- Traffic egress giữa GCP và on-premises.
- DNS queries/forwarding charges, nếu thuộc phạm vi billing.
- Internal Application Load Balancer data processing và resource charges.
- VPC Flow Logs/Cloud Logging và Monitoring telemetry.
- Cloud SQL, Cloud Storage và Pub/Sub operations/data transfer.
- Hạ tầng network on-premises, support và maintenance.
- Workload nhân bản trong thời gian migration/DR.

### Mẫu bảng ước tính

| Dòng chi phí | Lượng cần đo | Nguồn |
|---|---|---|
| VPN tunnel | Số tunnel × giờ chạy | Cloud Billing / VPN pricing |
| VPN data transfer | GiB theo chiều và region | Billing SKUs |
| Internal LB | Giờ/processing/traffic theo sản phẩm | Load balancing pricing |
| Cloud DNS | Query/zone/policy theo SKU | Cloud DNS pricing |
| Database | Instance size, storage, backup/HA | Cloud SQL pricing |
| Logging | GiB ingest/retention | Cloud Logging billing |
| Storage/API | Operations và transfer theo bucket location | Cloud Storage pricing |
| On-prem network | Port, thiết bị, circuit, support | Nhà cung cấp/mạng nội bộ |

Không tự đưa một số tiền cố định cho mọi region. Lấy giá đúng SKU và billing account ở thời điểm lập kế hoạch. Với ERP gọi API theo từng transaction, xem **cost per successful transaction**, không chỉ tổng GiB/tháng.

### Tối ưu có kiểm soát

- Giảm N+1 queries qua WAN bằng API boundary/batching.
- Cùng region cho service và database khi phù hợp data residency.
- Cache các dữ liệu đọc nhiều nhưng ít thay đổi.
- Tránh xuất/import toàn bộ dữ liệu nếu có delta/CDC phù hợp.
- Chuyển các tác vụ dài hạn khỏi tunnel nếu dùng data pipeline được phê duyệt.
- Không hi sinh HA chỉ để giảm một đường truyền.

## 20. Troubleshooting theo lớp

Khi integration hỏng, đi từ network đến application theo thứ tự có thể kiểm chứng.

| Triệu chứng | Nghi ngờ | Bước xác minh |
|---|---|---|
| IPsec tunnel DOWN | Peer IP, IKE/IPsec, key, firewall | Tunnel logs, peer logs, crypto policy |
| Tunnel UP, BGP DOWN | ASN, link-local, BGP MD5, timers | Cloud Router status và peer config |
| BGP UP, không ping/TCP | Prefix không quảng bá, route return thiếu, firewall | Routes hai phía, packet path, TCP |
| GCP không resolve ERP | Forwarding zone/DNS target không tới được | DNS ACL, 35.199.192.0/19 return route |
| On-prem không resolve GCP | Thiếu inbound Cloud DNS forwarding | Server policy/IP, conditional forwarding |
| On-prem gọi Storage API lỗi | DNS/VIP route hoặc IAM/API scope | VIP resolution, route, 401/403/timeout |
| Cloud SQL private IP timeout | PSA allocation/route thiếu, peering return hoặc firewall | VPC peering, Cloud Router advertisement |
| Cloud Run trả 403 | Ingress hoặc invoker IAM/app auth | Ingress config, caller identity, logs |
| Internal LB trả 502/503 | Backend/NEG/health check hoặc proxy firewall | Backend health, proxy-only subnet, logs |
| Lúc được lúc không | Tunnel asymmetry, DNS TTL, retry, route flap | BGP MED/priority, per-path tests |
| API chậm khi VPN UP | WAN RTT, packet loss, DB round trips | Traces, p95, retransmission, pool wait |
| Chuyển DR nhưng client vẫn gọi cũ | DNS caching, connection pools | TTL, JVM cache, deployment config |
| Bill tăng bất thường | Egress/log volume/batch lặp | Cloud Billing SKUs, flow attribution |

**Không dùng thay đổi firewall toàn mạng hoặc tắt TLS validation làm phương án chẩn đoán mặc định.** Nếu cần test ngoại lệ, tạo phạm vi hẹp có owner và thời hạn, sau đó gỡ bỏ.

## 21. Mẫu Architecture Decision Record (ADR)

Sau workshop, nhóm nên ghi lý do lựa chọn thay vì chỉ giữ một network diagram.

~~~yaml
adr_id: ADR-HYBRID-001
title: "ERP on-premises tích hợp Orders API trên Google Cloud"
status: proposed
context:
  source_cidr: "10.60.0.0/16"
  gcp_vpc: "hybrid-vpc"
  app_region: "asia-southeast1"
decision:
  connectivity: "HA VPN với hai tunnels và BGP"
  routing: "Cloud Router, prefixes được quảng bá có kiểm soát"
  dns: "Cloud DNS private zone + inbound/outbound forwarding"
  api: "Regional internal Application Load Balancer -> API"
  database: "Cloud SQL private IP, không công bố database trực tiếp nếu không cần"
  identity: "Workload identity / OIDC, TLS và least privilege"
alternatives:
  - "Dedicated / Partner Interconnect khi băng thông dài hạn lớn"
  - "Asynchronous Pub/Sub/file sync thay vì synchronous API"
risks:
  - "WAN latency và phụ thuộc DNS on-premises"
  - "Cloud SQL PSA return routes và cross-network dependencies"
acceptance:
  - "Positive/negative auth tests đạt"
  - "Hai phía DNS và TCP/HTTPS kiểm chứng"
  - "Failover rehearsal trong cửa sổ được phê duyệt"
owners:
  network: "network-team"
  security: "security-team"
  application: "orders-team"
  sre: "sre-team"
~~~

Đây là **mẫu ADR để thảo luận**, không phải file cấu hình Google Cloud có thể apply.

### Deliverables cần bàn giao

1. Network/data flow diagram kèm failure domains.
2. IPAM và DNS zone ownership.
3. BGP advertisements, expected routes và tunnel pairing.
4. Firewall/port matrix và IAM/auth matrix.
5. Cloud SQL/Cloud Run/private API connection decisions.
6. Monitoring dashboard và alert ownership.
7. Baseline hiệu năng, tải và chi phí.
8. Runbook cutover/rollback/failover.
9. Chứng cứ test và danh sách vấn đề mở.
10. ADR được phê duyệt bởi Network, Security, DBA, SRE và application owner.

## 22. Checklist nghiệm thu thực hành

- [ ] Có danh mục ứng dụng và luồng on-prem ↔ GCP, cả chiều request và response.
- [ ] On-prem/GCP/PSA/GKE CIDRs được IPAM phê duyệt, không trùng nhau.
- [ ] HA VPN/Interconnect thiết kế đúng topology và peer redundancy.
- [ ] Cloud Router BGP sessions đúng ASN, prefix và route priorities.
- [ ] Đã kiểm tra return routing và network-level firewall hai chiều.
- [ ] Inbound DNS forwarding cho tên GCP từ on-prem hoạt động.
- [ ] Outbound DNS forwarding cho tên ERP từ GCP hoạt động.
- [ ] Nếu dùng Cloud DNS outbound forwarding, DNS ACL và route `35.199.192.0/19` đúng.
- [ ] Google APIs từ on-prem dùng VIP/DNS/route và IAM đúng phương án.
- [ ] Cloud SQL private IP có producer allocation và route return phù hợp.
- [ ] Internal API chỉ cho phép ingress được phê duyệt, xác thực/mTLS/TLS hợp lệ.
- [ ] Java HTTP/JDBC timeout, retry, connection pooling được kiểm chứng.
- [ ] Có baseline p95 latency, throughput, error rate và traffic cost.
- [ ] Đã diễn tập failover ít nhất một tunnel và kiểm chứng recovery.
- [ ] Có dashboard, alerts, owners, on-call và runbook.
- [ ] Có kết quả kiểm tra bảo mật (positive và negative tests).
- [ ] Có bản vẽ, port matrix, ADR, cost model, cleanup và thay đổi được ghi lại.

## Câu hỏi ôn tập

1. Vì sao hai HA VPN tunnels và Cloud Router BGP vẫn chưa đủ để chứng minh application end-to-end khả dụng?
2. Cloud Router có thực hiện packet forwarding cho từng gói qua VPN không?
3. Vì sao không được dùng CIDR on-prem trùng với GKE Pod/Service secondary ranges?
4. Từ on-prem có thể gọi Cloud SQL private IP không? Điều kiện routing/PSA nào cần kiểm tra?
5. Với Cloud DNS forwarding từ GCP về DNS on-prem, vì sao cần xét `35.199.192.0/19`?
6. `private.googleapis.com` khác `restricted.googleapis.com` ở điểm nào?
7. Internal Application Load Balancer và Cloud Run IAM giải quyết những phần khác nhau của bảo mật thế nào?
8. VPN và Interconnect khác nhau thế nào về mã hóa dữ liệu mặc định?
9. Tại sao API Java gọi database trực tiếp qua WAN có thể gây lỗi latency dù TCP và BGP đều hoạt động?
10. Nếu một tunnel bị ngắt nhưng API vẫn chạy, cần kiểm tra thêm gì để đánh giá HA thực sự?
11. Điều gì khiến một DNS forwarding loop làm ứng dụng thất bại ngay cả khi route và firewall đúng?
12. Vì sao nên triển khai thử nghiệm có rollback và theo dõi chi phí trước khi mở rộng một integration hybrid?

## Kết luận

Thiết kế tích hợp on-premises với Google Cloud đòi hỏi **nhiều lớp bằng chứng**: đúng phụ thuộc ứng dụng, đúng IPAM và route, DNS hai chiều, endpoint riêng cho từng dịch vụ, xác thực và cấp quyền, telemetry, HA và chi phí. HA VPN cùng Cloud Router tạo nền tảng kết nối linh hoạt; Cloud DNS giải quyết phát hiện dịch vụ; internal load balancer, Cloud SQL private connectivity và Private Google Access phục vụ những đường kết nối **khác nhau**, không thể thay thế tùy tiện.

Khi có bảng luồng, ADR, runbook, các phép thử positive/negative, diễn tập failover và cost baseline, đội triển khai có thể chuyển dần API Java, dữ liệu và worker lên GCP mà vẫn vận hành an toàn với ERP và hệ thống legacy. Kết quả của bài thực hành không phải chỉ là “VPN đã UP”, mà là **một kiến trúc hybrid có thể kiểm chứng, có owner và có kế hoạch phục hồi rõ ràng**.

## Tài liệu tham khảo

- [Google Cloud — Hybrid and multicloud networking](https://cloud.google.com/architecture/hybrid-multicloud-networking)
- [Cloud VPN overview](https://cloud.google.com/network-connectivity/docs/vpn/concepts/overview)
- [HA VPN topologies](https://cloud.google.com/network-connectivity/docs/vpn/concepts/topologies)
- [Create HA VPN gateways to a peer gateway](https://cloud.google.com/network-connectivity/docs/vpn/how-to/creating-ha-vpn)
- [Cloud Router overview](https://cloud.google.com/network-connectivity/docs/router/concepts/overview)
- [Cloud Router best practices](https://cloud.google.com/network-connectivity/docs/router/concepts/best-practices)
- [Cloud Interconnect overview](https://cloud.google.com/network-connectivity/docs/interconnect/concepts/overview)
- [Cloud DNS best practices for hybrid environments](https://cloud.google.com/dns/docs/best-practices)
- [Cloud DNS forwarding zones](https://cloud.google.com/dns/docs/zones/forwarding-zones)
- [Cloud DNS server policies](https://cloud.google.com/dns/docs/policies)
- [Private Google Access for on-premises hosts](https://cloud.google.com/vpc/docs/private-google-access-hybrid)
- [Configure Private Google Access for on-premises hosts](https://cloud.google.com/vpc/docs/configure-private-google-access-hybrid)
- [Private services access configuration](https://cloud.google.com/vpc/docs/configure-private-services-access)
- [Cloud SQL for PostgreSQL private IP](https://cloud.google.com/sql/docs/postgres/configure-private-ip)
- [Cloud Run ingress restrictions](https://cloud.google.com/run/docs/securing/ingress)
- [Internal Application Load Balancer overview](https://cloud.google.com/load-balancing/docs/l7-internal)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Network Intelligence Center connectivity tests](https://cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview)
- [Cloud Billing export to BigQuery](https://cloud.google.com/billing/docs/how-to/export-data-bigquery)

