# Lập kế hoạch DNS, kết nối và đồng bộ danh tính khi di chuyển

## 1. Tại sao phải lập kế hoạch ba lớp này cùng lúc?

Khi di chuyển ứng dụng từ trung tâm dữ liệu nội bộ (*on-premises*) lên Microsoft Azure, việc tạo máy ảo, cơ sở dữ liệu hay container thường chỉ là một phần công việc. Ứng dụng có thể khởi động tốt nhưng vẫn không hoạt động nếu tên miền trỏ sai IP, đường mạng không tới được dependency hoặc người dùng không đăng nhập được bằng danh tính hiện có.

Bài học thuộc chương **Hybrid cloud và di chuyển lên Azure** của module `CLOUD_PROVIDERS_AZURE`. Nó nối các kiến thức về subscription, resource group, Microsoft Entra ID, mạng ảo, compute, storage, database, giám sát, bảo mật và chi phí vào một kế hoạch migration có thể thực thi.

Ba lớp phải được thiết kế **liên kết với nhau**:

1. **DNS:** Tên nào phải phân giải tới đâu trước, trong và sau khi chuyển ứng dụng? Ai là authoritative DNS và ai là recursive resolver? Các client nội bộ/công khai có cùng câu trả lời không?
2. **Kết nối:** Request đi theo tuyến nào giữa người dùng, Azure VNet, trung tâm dữ liệu, dịch vụ PaaS và mạng quản trị? Có đủ băng thông, quyền mạng, route và độ trễ không?
3. **Danh tính:** Tài khoản người dùng và dịch vụ được xác thực ở đâu, các thuộc tính nào phải đồng bộ, hệ thống nào là *source of authority*, và điều gì xảy ra nếu kết nối về on-premises gián đoạn?

Ví dụ: hệ thống `orders` đang dùng Active Directory Domain Services (AD DS) nội bộ, DNS `corp.example.com` và cơ sở dữ liệu on-premises. Khi API chuyển lên Azure App Service, tên database cũ có thể vẫn phân giải về datacenter; workload Azure cần route và quyền mạng tới đó. Nhân viên đăng nhập qua Microsoft Entra ID, còn một tác vụ legacy vẫn dùng Kerberos AD DS. Thay đổi DNS trước khi kết nối và danh tính sẵn sàng sẽ gây sự cố dù phần mềm không có lỗi.

**Mục tiêu học tập:** Sau bài này, bạn có thể lập bản kiểm kê dependency, thiết kế DNS hybrid, chọn phương án kết nối, hoạch định Microsoft Entra Connect Sync/Cloud Sync, thực hiện cutover có tiêu chí rõ ràng và xây checklist xác minh/rollback.

## 2. Phạm vi, giả định và tiêu chí thành công

Xem hệ thống mẫu sau. Các tên miền thuộc `example.com`, địa chỉ IP, tên resource group và giá trị SLA là **giả định để học**, phải thay bằng dữ liệu thực tế khi triển khai.

| Thành phần | Trước migration | Sau migration dự kiến |
| --- | --- | --- |
| Người dùng | Truy cập `orders.example.com` từ Internet; nhân viên dùng SSO nội bộ | Frontend/API trên Azure, danh tính nhân viên qua Microsoft Entra ID |
| Ứng dụng | Máy ảo on-premises | Azure App Service hoặc VM/AKS tùy workload |
| Cơ sở dữ liệu | SQL nội bộ tại `sql01.corp.example.com` | Giai đoạn đầu vẫn on-premises; sau đó chuyển sang dịch vụ dữ liệu Azure phù hợp |
| DNS nội bộ | AD-integrated DNS trong `corp.example.com` | DNS hybrid; một số tên vẫn do AD DNS quản lý |
| DNS public | Authoritative DNS của `example.com` | Giữ hoặc chuyển nhà cung cấp; `orders.example.com` đổi đích khi cutover |
| Mạng | LAN/datacenter | Hub-spoke Azure, Site-to-Site VPN hoặc ExpressRoute |
| Danh tính | AD DS là nguồn user/group nội bộ | Microsoft Entra ID đồng bộ một phần danh tính từ AD DS |
| Bí mật/workload identity | Service accounts, secret được quản lý nội bộ | Managed Identity/Key Vault khi ứng dụng hỗ trợ; giữ account legacy cần thiết |
| Giám sát | Log và monitoring riêng | Azure Monitor/Application Insights kết hợp công cụ hiện tại |

**Tiêu chí nghiệm thu** nên gắn với hành trình nghiệp vụ:

- Người dùng truy cập đúng frontend bằng FQDN cũ, chứng chỉ TLS hợp lệ.
- API Azure truy cập được database ở giai đoạn hybrid và các service endpoint đúng private/public policy.
- Đăng nhập người dùng thử nghiệm, nhóm quyền và các ứng dụng legacy đạt kết quả dự kiến.
- DNS trả đúng record theo nguồn truy vấn; không phát sinh vòng lặp forwarder hoặc rò rỉ tên miền nội bộ.
- Thời gian chuyển đổi, gián đoạn dịch vụ và mức dữ liệu mất (nếu có) nằm trong RTO/RPO đã được thỏa thuận.
- Có khả năng đo, phát hiện lỗi và quay lại trạng thái an toàn theo runbook.

## 3. Bắt đầu bằng bản đồ dependency

Đừng bắt đầu từ thao tác đổi bản ghi DNS. Hãy lập danh sách **tên, địa chỉ, giao thức, quyền và chủ sở hữu** của các liên kết trước.

~~~mermaid
flowchart TB
    U["Khách hàng / nhân viên"] --> PUB["Public DNS: orders.example.com"]
    PUB --> IN["Azure ingress / ứng dụng"]
    IN --> VM["Azure API / worker"]
    VM --> PRIV["Private DNS: database và dịch vụ Azure"]
    VM --> ID["Microsoft Entra ID / Managed Identity"]
    VM --> HYB["Kết nối VPN hoặc ExpressRoute"]
    HYB --> AD["On-prem AD DS + DNS"]
    HYB --> SQL["On-prem SQL / hệ thống legacy"]
    PRIV --> PEP["Private Endpoint của PaaS"]
    MON["Azure Monitor / Logs"] -.-> IN
    MON -.-> VM
    MON -.-> HYB
~~~

Tạo một bảng kiểm kê dùng trong quá trình chuyển đổi:

| Dependency | FQDN/IP và port | Hiện do ai quản lý? | Dự kiến sau migration | Cách kiểm thử |
| --- | --- | --- | --- | --- |
| Public web | `orders.example.com`:443 | Public authoritative DNS | Trỏ ingress Azure khi cutover | DNS ngoài mạng + HTTPS synthetic |
| Domain controllers | `dc01.corp.example.com`; DNS/Kerberos/LDAP theo nhu cầu | AD DS / DNS team | Truy cập qua hybrid network hoặc DC tại Azure | SRV lookup, domain join/logon |
| On-prem SQL | `sql01.corp.example.com`:1433 (ví dụ) | Database team | Giữ qua mạng hybrid trong wave 1 | TCP reachability + truy vấn ứng dụng |
| Storage PaaS | `stordersdemo001.blob.core.windows.net`:443 | Azure Storage | Private Endpoint + DNS phù hợp | Resolve private IP, TLS và auth |
| Authentication | Microsoft Entra sign-in endpoints | Identity team | Cloud authentication/SSO theo phương án | Login MFA/Conditional Access |
| Secrets | Key Vault endpoint | Security/platform | Managed Identity + Private Endpoint nếu chọn | Lấy secret bằng quyền tối thiểu |
| Monitoring | Endpoint ingest, workspace | SRE | Gửi telemetry ở môi trường mới | Kiểm tra traces, logs, alerts |

**Đừng chỉ liệt kê HTTP/443.** AD DS có thể dùng DNS 53, Kerberos 88, LDAP/LDAPS 389/636, SMB 445, RPC endpoint mapper 135 và cổng RPC động tùy tác vụ. Đúng tập cổng cần dựa trên hoạt động cụ thể và policy, không mở nguyên dải một cách không kiểm soát.

Ghi thêm **đường phản hồi (return path)**, dependency của batch job, email, queue, certificate validation, update repositories và các tác vụ quản trị. Từ đó đánh dấu:

- Những kết nối phải hoạt động trong lúc chạy song song.
- Những tên FQDN phải giữ nguyên qua migration.
- Những phụ thuộc được di chuyển ở wave sau.
- Những quyền và chứng chỉ cần sẵn sàng trước khi bật traffic thật.

## 4. Hiểu vai trò của DNS trong môi trường hybrid

DNS có hai nhiệm vụ tách biệt:

1. **Authoritative DNS** giữ bản ghi chính thức cho một zone, ví dụ public `example.com` hoặc zone AD DS `corp.example.com`.
2. **Recursive resolver** nhận truy vấn từ client, thực hiện hoặc chuyển tiếp truy vấn để tìm câu trả lời, có thể cache theo TTL.

Một DNS server AD DS có thể làm cả hai nhiệm vụ cho các zone khác nhau, nhưng **không nên nhầm một bản ghi tồn tại trong zone với việc mọi client đều sử dụng cùng resolver**.

### 4.1. Public DNS, private DNS và split-horizon

| Kiểu | Ví dụ | Ai nên truy cập? | Rủi ro khi sai |
| --- | --- | --- | --- |
| **Public DNS** | `orders.example.com` | Khách hàng Internet và client nội bộ nếu dùng public endpoint | Cutover sai làm người dùng đến môi trường cũ hoặc mất TLS |
| **AD-integrated DNS** | `corp.example.com` và record SRV của domain | Thiết bị và workload được phép dùng AD | Domain logon, Kerberos, service discovery lỗi |
| **Azure Private DNS Zone** | `privatelink.blob.core.windows.net` | VNet được link và resolver hybrid được cấu hình | Private Endpoint phân giải sai IP hoặc không phân giải |
| **Split-horizon/split-brain DNS** | Cùng FQDN nhưng trả public/private IP tùy client | Theo chính sách truy cập | Khó debug nếu truy vấn qua resolver không mong đợi |

Không cần chuyển mọi zone DNS về Azure chỉ vì ứng dụng chuyển sang Azure. Một chiến lược tốt là giữ **quyền sở hữu zone** rõ ràng và chỉ thiết lập forwarding/liên kết cần thiết.

### 4.2. TTL và cache trong thời điểm cutover

**TTL (Time to Live)** là thời gian resolver có thể cache một câu trả lời DNS. Giảm TTL của bản ghi public trước cutover có thể rút ngắn thời gian client còn dùng địa chỉ cũ, nhưng:

- TTL mới chỉ giúp khi cache cũ đã hết hạn; giảm TTL vài phút trước cutover **không xóa** cache đã tồn tại.
- DNS resolver, trình duyệt, ứng dụng, connection pool và proxy có thể giữ kết quả hoặc kết nối theo cách riêng.
- Negative caching (`NXDOMAIN`), chuỗi CNAME và tầng CDN/ingress đều có thể ảnh hưởng.
- Thay đổi authoritative DNS/NS delegation có thể đòi hỏi chuẩn bị khác thay một bản ghi A/CNAME.

Ví dụ chính sách: giảm TTL từ 3600 giây xuống 300 giây **trước ít nhất một khoảng đủ cho TTL cũ hết hạn**, sau đó kiểm tra bằng nhiều recursive resolver. Đây là con số minh họa; thời gian và policy thực tế phụ thuộc dịch vụ.

**Không dùng TTL thấp làm cam kết “toàn bộ traffic sẽ đổi trong đúng 5 phút”.** Sau cutover, nên giữ endpoint cũ ở chế độ phù hợp trong giai đoạn quan sát và có kế hoạch xử lý request còn đến đó.

### 4.3. Không quên record ngoài A/CNAME

Với tên miền public, đánh giá record `AAAA`, `CNAME`, `TXT` xác thực domain, `CAA`, `MX`, `SRV` và các record liên quan hệ thống. Nếu thay **authoritative DNS provider**, xác minh DNSSEC/DS tại registrar và đầy đủ zone records. Không để chuyển website vô tình ảnh hưởng mail hoặc xác thực domain.

Với AD DS, các bản ghi `_ldap._tcp` và `_kerberos._tcp` (cùng cấu trúc SRV liên quan) phục vụ định vị domain controller. Thay DNS client bằng public resolver có thể khiến VM không thể tìm thấy domain controller dù route đến IP vẫn tồn tại.

## 5. Kiến trúc phân giải DNS hybrid được đề xuất

Azure có **Azure DNS Private Resolver** để giải quyết DNS từ mạng hybrid mà không phải tự duy trì toàn bộ DNS forwarder VM cho nhu cầu phù hợp. Nó cung cấp:

- **Inbound endpoint:** địa chỉ IP trong VNet để nguồn được phép (ví dụ DNS nội bộ qua VPN/ExpressRoute) gửi truy vấn cần phân giải theo khả năng của Azure.
- **Outbound endpoint:** dùng cùng DNS forwarding ruleset để chuyển những truy vấn phù hợp từ Azure tới DNS server bên ngoài, như on-premises DNS.
- **DNS forwarding ruleset:** quy tắc cho các domain suffix và DNS target tương ứng; có thể liên kết tới VNet được hỗ trợ.

Các endpoint yêu cầu subnet chuyên dụng và cấu hình mạng đúng theo quy định của dịch vụ; dùng subnet, region và cấu hình hỗ trợ được xác minh trước triển khai.

~~~mermaid
flowchart LR
    ON["On-prem client"] --> ODNS["On-prem DNS"]
    ODNS -->|"Forward Azure-related suffix"| IN["Private Resolver inbound endpoint"]
    IN --> AZDNS["Azure DNS / private zone"]
    AZCLIENT["Azure VM / workload"] --> RULE["DNS forwarding ruleset liên kết VNet"]
    RULE --> OUT["Private Resolver outbound endpoint"]
    OUT -->|"Forward corp.example.com"| ODNS
    AZDNS --> PZ["Private DNS zone linked VNet"]
~~~

Đường trên mô tả hai hướng truy vấn. Việc liên kết VNet, chọn suffix và hướng forward phải tránh **vòng lặp truy vấn**:

- Với `corp.example.com` do on-premises authoritative DNS quản lý, Azure có thể forward các truy vấn tên miền đó qua outbound endpoint về DNS nội bộ.
- Với tên Azure Private Endpoint, on-premises có thể gửi truy vấn suffix được quy hoạch đến inbound endpoint để Azure phân giải qua private zone/VNet link thích hợp.
- Nếu on-prem DNS lại forward chính `corp.example.com` sang Azure và Azure forward ngược về on-prem, truy vấn sẽ xoay vòng rồi timeout.

### 5.1. Quy tắc forwarding và client DNS

Trong sơ đồ hybrid, cần ghi rõ **client dùng DNS nào**. Azure VM có thể sử dụng DNS mặc định của VNet, hoặc custom DNS server đã được cấu hình. Nếu dùng custom DNS, server đó phải biết chuyển tiếp phù hợp tới Private Resolver/Azure DNS; việc link Private DNS Zone vào VNet **không tự bảo đảm custom DNS sẽ trả lời đúng nếu nó không forward**.

Azure-provided DNS có địa chỉ đặc biệt `168.63.129.16` trong ngữ cảnh được Azure hỗ trợ. Không coi đây là máy chủ DNS có thể truy vấn trực tiếp từ mạng on-premises xuyên VPN/ExpressRoute. Đối với on-premises, dùng **Private Resolver inbound endpoint** hoặc DNS forwarder phù hợp trong Azure.

Cần kiểm tra thứ tự DNS servers, forward zones, fallback khi target không phản hồi, policy allow-list và subnet route. Nếu Azure workloads vẫn domain-joined vào AD DS, DNS chọn cho VM phải phân giải được tên và SRV của domain, đồng thời phục vụ tên Azure PaaS theo thiết kế.

### 5.2. Private Endpoint của Azure Storage: ví dụ phân giải

Giả sử storage account `stordersdemo001` được truy cập qua Private Endpoint cho dịch vụ Blob.

~~~text
Client truy cập:
stordersdemo001.blob.core.windows.net

CNAME trong cơ chế DNS dịch vụ:
stordersdemo001.privatelink.blob.core.windows.net

Private DNS zone trong Azure:
privatelink.blob.core.windows.net

Private A record tương ứng:
stordersdemo001 -> 10.42.2.10  (IP minh họa)
~~~

Client vẫn dùng **FQDN dịch vụ chuẩn** `stordersdemo001.blob.core.windows.net` để TLS/SNI và SDK hoạt động bình thường. DNS chain dẫn đến IP Private Endpoint khi client ở đường phân giải riêng đã cấu hình đúng. Không yêu cầu ứng dụng đổi URL sang `privatelink` chỉ để kết nối.

Để on-premises resolve, Microsoft thường khuyến nghị cấu hình conditional forwarding cho **public DNS zone suffix của dịch vụ** (ví dụ `blob.core.windows.net`) về Azure DNS Private Resolver inbound endpoint trong mẫu kiến trúc tương ứng. Cần kiểm tra sự tương tác với các storage account **không có Private Endpoint** và các private DNS zones trong hệ thống; không forward mù toàn bộ namespace nếu việc đó làm hỏng phân giải public resources.

**Lưu ý:** Tạo Private Endpoint không đồng nghĩa tự động tắt public network access cho dịch vụ. Chính sách chặn public access và network controls phải được cấu hình riêng theo từng dịch vụ.

### 5.3. Liên kết Private DNS Zone với VNet

Ví dụ Bicep dưới đây chỉ minh họa **virtual network link** từ Private DNS Zone có sẵn tới một VNet. Giả định Private DNS Zone nằm trong resource group nhận deployment và VNet ID hợp lệ; deployment identity có quyền tương ứng.

~~~bicep
targetScope = 'resourceGroup'

@description('Resource ID của VNet cần phân giải Private DNS zone.')
param vnetResourceId string

@description('Tên link cần tạo.')
param dnsLinkName string = 'link-orders-spoke'

resource privateZone 'Microsoft.Network/privateDnsZones@2020-06-01' existing = {
  name: 'privatelink.blob.core.windows.net'
}

resource vnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: privateZone
  name: dnsLinkName
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnetResourceId
    }
    registrationEnabled: false
  }
}

output linkId string = vnetLink.id
~~~

Đối với Private Endpoint, auto-registration thường không phải nhu cầu của zone `privatelink`. Việc tạo record cho Private Endpoint có thể được quản lý thông qua **private DNS zone group** khi cấu hình phù hợp. Đoạn code trên không tạo Private Endpoint, record A, inbound/outbound resolver hoặc cross-subscription permission; mỗi phần cần được kiểm tra riêng.

**Quy tắc an toàn:** Chỉ chỉnh link/bản ghi trong zone được nhóm DNS chịu trách nhiệm quản lý, và kiểm tra tác động tới các dịch vụ dùng cùng zone trước khi thay đổi.

## 6. Thiết kế kết nối mạng: Site-to-Site VPN hay ExpressRoute?

Trong giai đoạn hybrid, API trên Azure có thể cần gọi AD DS, SQL hoặc ứng dụng legacy nội bộ. Các lựa chọn thường gặp gồm **Site-to-Site VPN** qua IPsec/IKE và **Azure ExpressRoute** qua kết nối riêng do nhà cung cấp hỗ trợ. Chúng khác nhau về kết nối, hành vi tuyến, chi phí, khả năng vận hành và yêu cầu HA.

| Tiêu chí | Site-to-Site VPN | ExpressRoute |
| --- | --- | --- |
| Đường kết nối | Tunnel mã hóa IPsec qua Internet hoặc đường truyền hỗ trợ | Kết nối riêng qua provider/peering theo mô hình dịch vụ |
| Bảo mật đường truyền | IPsec mã hóa tunnel | Kết nối riêng **không đồng nghĩa tự mã hóa end-to-end**; có thể cần cơ chế mã hóa riêng theo chính sách |
| Thiết lập | Thường phù hợp pilot hoặc nhu cầu hybrid vừa phải | Thường phù hợp yêu cầu băng thông/độ ổn định và kiến trúc doanh nghiệp |
| Băng thông, độ trễ | Phụ thuộc tunnel, thiết bị on-prem, ISP và gateway SKU | Phụ thuộc circuit, provider, peering, gateway và route |
| Redundancy | Cần thiết kế tunnel/gateway/thiết bị dự phòng | Thiết kế circuit/peering/provider/đường đi dự phòng phù hợp |
| Chi phí | Gateway, dữ liệu, thiết bị, vận hành | Circuit/provider, gateway, dữ liệu và các khoản liên quan |
| Thay thế Internet public | Không mặc định; tùy route và kiến trúc | Không tự cho phép mọi endpoint public đi qua private peering |

**ExpressRoute không tự giải quyết DNS hoặc đồng bộ Entra ID.** Ngược lại, một VPN hoạt động không chứng minh application protocol, port, TLS và quyền IAM đều đã chính xác.

### 6.1. Địa chỉ IP và tuyến phải được quyết định trước

Ví dụ quy hoạch:

~~~text
On-premises datacenter : 10.10.0.0/16
Azure hub VNet         : 10.40.0.0/16
Azure app spoke VNet   : 10.41.0.0/16
Azure data spoke VNet  : 10.42.0.0/16

Hybrid routing:
Azure app -> VNet peering / hub -> VPN hoặc ExpressRoute -> On-prem SQL
On-prem client -> VPN/ExpressRoute -> Azure Private Endpoint
~~~

Đây là địa chỉ minh họa; **không thể dùng nguyên mẫu nếu CIDR thực tế trùng lặp**. Rà toàn bộ datacenter, branch office, cloud khác, VNet/spoke, cluster pod/service CIDR khi cần, và mạng đối tác. Nếu xảy ra overlap, routing có thể mơ hồ; NAT hoặc thay đổi address plan có thể là phương án nhưng tạo thêm giới hạn DNS, audit và tính minh bạch địa chỉ.

Đầu ra thiết kế gồm:

- CIDR/subnet, vùng và vai trò của từng subnet.
- Route quảng bá từ on-premises và Azure; BGP nếu dùng, route propagation, default route.
- Thiết kế hub/spoke peering, khả năng gateway transit và quyền sử dụng remote gateway khi được hỗ trợ.
- Route table/UDR, Azure Firewall/NVA và return path; tránh bất đối xứng qua stateful firewall.
- NSG rules và firewall rules **theo đúng source, destination, protocol, port**.
- MTU/MSS, timeout, long-lived connection và khả năng khôi phục tunnel.
- Giới hạn băng thông/throughput, độ trễ mạng, dự phòng đường, chi phí transfer.
- DNS resolver endpoint IP và chính sách truy cập từ nguồn được phép.

Đừng coi trạng thái `Connected` trên gateway là bằng chứng ứng dụng hoạt động. Một tunnel có thể lên nhưng route, DNS, NSG, firewall hay database permissions sai.

### 6.2. Hub-and-spoke và phân đoạn bảo mật

Mô hình hub chứa connectivity, firewall/inspection, private resolver hoặc dịch vụ chia sẻ; spokes chứa workload app/data. Lợi ích là quản trị rõ ràng, nhưng cần xác minh:

- VNet peering không tự có tính bắc cầu; các tuyến hub-spoke cần cơ chế gateway/transit/NVA phù hợp.
- Với UDR qua firewall, đảm bảo gói trả về cũng theo tuyến phù hợp.
- Kết nối đến Private Endpoint thường dùng **private IP của endpoint**; DNS và route phải nhất quán.
- NSG chỉ cho phép port cần thiết; service tags và endpoint policies phải được dùng theo hỗ trợ dịch vụ.
- Tách quyền deploy, vận hành mạng và quản lý identity bằng RBAC và quy trình change.

### 6.3. Khả năng sẵn sàng của đường hybrid

Một line duy nhất có thể trở thành điểm lỗi chung. Tùy mục tiêu RTO, ứng dụng có thể cần nhiều tunnel, thiết bị on-premises dự phòng hoặc ExpressRoute kèm phương án kết nối dự phòng, đồng thời diễn tập chuyển route. Cũng cần tự hỏi **nếu datacenter không kết nối được**, workload Azure có hoạt động ở chế độ suy giảm hay ngừng hoàn toàn?

Một kế hoạch migration tốt thường giảm dần phụ thuộc vào kết nối hybrid theo từng wave. Chừng nào database/AD legacy còn on-premises, RTO của Azure workload có thể bị chi phối bởi khả năng kết nối datacenter.

## 7. Kiểm tra kết nối từ góc nhìn DNS → route → TCP → ứng dụng

Trình tự debug giúp tránh kết luận sai:

~~~mermaid
flowchart TD
    F["Client gọi API/DB bằng FQDN"] --> D{"DNS đúng IP và DNS source?"}
    D -->|"Không"| DR["Kiểm tra resolver, zone, forwarder, TTL"]
    D -->|"Có"| R{"Có route và return path?"}
    R -->|"Không"| RR["Kiểm tra VNet, gateway, BGP, UDR"]
    R -->|"Có"| T{"TCP/TLS tới port đích?"}
    T -->|"Không"| TR["NSG, firewall, MTU, cert, listener"]
    T -->|"Có"| A{"Auth và giao dịch nghiệp vụ?"}
    A -->|"Không"| AR["Kiểm tra token, RBAC, Kerberos, DB permission"]
    A -->|"Có"| OK["Ghi evidence + đánh giá độ trễ và HA"]
~~~

### 7.1. Lệnh kiểm tra DNS và port

Từ máy khách Windows được phép truy vấn:

~~~powershell
# Xác nhận DNS server thực sự được client sử dụng.
Get-DnsClientServerAddress

# So sánh câu trả lời từ resolver nội bộ và Private Resolver inbound.
Resolve-DnsName -Name "sql01.corp.example.com" -Type A
Resolve-DnsName -Name "sql01.corp.example.com" -Type A -Server "10.10.1.10"

# Kiểm tra FQDN dịch vụ Azure qua DNS đúng đường riêng.
Resolve-DnsName -Name "stordersdemo001.blob.core.windows.net" -Type A

# Thử mở TCP tới cổng yêu cầu; chưa chứng minh đăng nhập thành công.
Test-NetConnection -ComputerName "sql01.corp.example.com" -Port 1433
Test-NetConnection -ComputerName "stordersdemo001.blob.core.windows.net" -Port 443
~~~

Từ một máy Linux có công cụ `dig` và `curl`:

~~~bash
dig sql01.corp.example.com A
dig @10.10.1.10 sql01.corp.example.com A

dig stordersdemo001.blob.core.windows.net A
dig stordersdemo001.blob.core.windows.net CNAME

curl -I --connect-timeout 5 https://stordersdemo001.blob.core.windows.net/
~~~

Lệnh `curl -I` tới storage có thể trả **403/400** nếu không kèm credential hoặc không đúng operation, nhưng vẫn giúp kiểm tra một phần DNS, TCP, TLS và response path. Không coi HTTP 403 là bằng chứng mạng bị chặn: cần xem nguồn phát response và kiểm tra request có quyền hợp lệ. Các lệnh trên là **đo tại client cụ thể**, phải thử ở cả on-premises và Azure để so sánh.

### 7.2. Azure CLI hỗ trợ kiểm kê read-only

~~~bash
# Xác định subscription/tenant trước khi phân tích.
az account show --query "{subscription:id,tenant:tenantId}" -o json

# Xem vùng địa chỉ VNet được phép kiểm tra.
az network vnet show \
  --resource-group rg-network-hub \
  --name vnet-hub \
  --query "{name:name,location:location,addressSpace:addressSpace.addressPrefixes}" \
  -o json

# Kiểm tra các liên kết VNet của một Private DNS Zone đã có.
az network private-dns link vnet list \
  --resource-group rg-network-dns \
  --zone-name privatelink.blob.core.windows.net \
  -o table
~~~

Các resource group/VNet và private zone trong ví dụ phải tồn tại và người thực hiện cần quyền đọc. Để kiểm tra tuyến/NSG từ một Azure VM, có thể dùng **Network Watcher** (effective routes, effective security rules, connection troubleshoot) theo tính năng và quyền được hỗ trợ. Kết quả của một probe phải được ghép với log ứng dụng và firewall để kết luận nguyên nhân.

## 8. Đồng bộ danh tính: AD DS khác Microsoft Entra ID như thế nào?

**Active Directory Domain Services (AD DS)** là dịch vụ directory/domain truyền thống hỗ trợ domain controller, LDAP, Kerberos, Group Policy, domain join và DNS gắn với AD. **Microsoft Entra ID** là dịch vụ danh tính đám mây hỗ trợ xác thực hiện đại, OAuth 2.0/OpenID Connect, ứng dụng doanh nghiệp, Conditional Access và quản lý danh tính phù hợp.

Đồng bộ user/group từ AD DS lên Entra ID **không biến Entra ID thành domain controller**. Ứng dụng chỉ hỗ trợ LDAP/Kerberos hoặc cần Group Policy sẽ tiếp tục cần thiết kế AD DS tương ứng, hoặc được hiện đại hóa để dùng chuẩn xác thực phù hợp.

| Nhu cầu | Hướng lựa chọn |
| --- | --- |
| Nhân viên truy cập SaaS/app hiện đại qua SSO | Entra ID; OIDC/SAML theo ứng dụng |
| User/group vẫn do AD DS nội bộ tạo và quản lý | Đồng bộ danh tính sang Entra ID theo công cụ hỗ trợ |
| VM/ứng dụng legacy cần domain join, LDAP/Kerberos | AD DS có khả năng kết nối hoặc phương án domain service được hỗ trợ |
| Workload Azure gọi PaaS và Azure APIs | Managed Identity và RBAC/data-plane permissions khi hỗ trợ |
| Đối tác dùng danh tính ngoài tổ chức | Entra External ID/B2B theo chính sách |
| App cần thuộc tính custom hoặc provisioning riêng | Kiểm tra khả năng đồng bộ/provisioning, transformation và hạn chế connector |

### 8.1. Entra Connect Sync và Entra Cloud Sync

Microsoft cung cấp những phương án đồng bộ danh tính từ AD DS lên Entra ID, bao gồm **Microsoft Entra Connect Sync** và **Microsoft Entra Cloud Sync**. Chúng có tập tính năng, kiến trúc agent/engine, yêu cầu cấu hình và giới hạn khác nhau.

Một kế hoạch chọn công cụ cần xác định:

1. Có bao nhiêu forest/domain, topology và trust?
2. Có cần đồng bộ thuộc tính, object types, writeback hay tính năng hybrid đặc biệt nào?
3. Có yêu cầu high availability, staging hoặc agent redundancy không?
4. Có thể dùng **Cloud Sync** cho đầy đủ requirement hiện tại hay cần **Connect Sync**?
5. Quy tắc scope theo OU/group và cách lọc có rõ chưa?
6. Có cần kiểm tra version, licensing và supportability ở thời điểm triển khai không?

**Không xem hai sản phẩm là thay thế một-một trong mọi tình huống.** Trước khi chọn, đối chiếu matrix hỗ trợ tính năng, phiên bản và điều kiện triển khai cho tổ chức.

### 8.2. Source of authority và thuộc tính định danh

Quyết định **hệ thống nào có quyền tạo và sửa thuộc tính** (source of authority) cho từng nhóm đối tượng trước khi bật sync. Với user đồng bộ từ AD DS, nhiều thuộc tính được quản lý ở AD DS và đồng bộ lên cloud; sửa phía Entra ID có thể bị ghi đè hoặc bị hạn chế theo tính năng.

Các thuộc tính/cấu trúc cần kiểm tra:

- **UPN (User Principal Name):** tên đăng nhập có dùng suffix domain được Entra ID xác minh, phù hợp trải nghiệm người dùng không?
- **mail/proxyAddresses:** tránh trùng alias, email sai hoặc xung đột với object đã có trong Entra ID.
- **Source anchor/immutable identifier:** liên kết ổn định giữa object on-prem và cloud; thay đổi tùy tiện có thể gây duplicate hoặc mismatch.
- **Object ID và quan hệ group:** ứng dụng có đang lưu ID user/group làm khóa không? Migration có thay identity reference không?
- **Disabled/deleted accounts:** chính sách nghỉ việc, xóa đối tượng và restore cần được thống nhất.
- **OU/group scoping:** pilot giới hạn đúng đối tượng; không đồng bộ toàn bộ dữ liệu nhạy cảm không cần thiết.

**Nguy cơ thường gặp:** Đã có cloud-only user `user@example.com` rồi bật sync từ AD DS tạo đối tượng trùng. Matching và soft/hard match cần được lên kế hoạch theo cơ chế Microsoft hỗ trợ; thao tác chỉnh immutable ID/match sai có thể dẫn đến mất liên kết, quyền hoặc gián đoạn đăng nhập. Nên test trên nhóm pilot và ghi trạng thái trước khi thay đổi hàng loạt.

## 9. Xác thực khi hybrid: Password Hash Sync, PTA và federation

Đồng bộ directory và phương án **xác thực** là hai quyết định liên quan nhưng khác nhau.

| Phương án | Nguyên tắc khái quát | Điều cần cân nhắc khi migration |
| --- | --- | --- |
| **Password Hash Synchronization (PHS)** | Đồng bộ dạng dẫn xuất của password hash từ AD DS sang Entra ID theo cơ chế dịch vụ | Có thể giảm phụ thuộc xác thực trực tiếp tới on-premises; kiểm tra chính sách và tính năng |
| **Pass-through Authentication (PTA)** | Entra ID chuyển việc xác minh password qua agent liên quan AD DS | Phụ thuộc agent/AD connectivity; cần HA và kiểm thử khi datacenter lỗi |
| **Federation** | Dùng nhà cung cấp danh tính liên kết qua giao thức hỗ trợ | Phụ thuộc IdP, chứng chỉ, DNS, mạng, policy, vòng đời và khả năng HA |

PHS **không đồng bộ mật khẩu dạng plaintext**; cơ chế và bảo mật chi tiết phải được tuân thủ theo dịch vụ. Việc chọn PHS/PTA/federation ảnh hưởng trực tiếp tới khả năng đăng nhập khi on-premises ngừng kết nối. Cần đánh giá MFA, Conditional Access, credential reset, password writeback (nếu được hỗ trợ/cấp phép) và thời gian hội tụ thay đổi.

### 9.1. Các bài test danh tính bắt buộc

Một ma trận nghiệm thu cho nhóm pilot:

| Bài test | Điều kỳ vọng | Điều cần ghi |
| --- | --- | --- |
| Đăng nhập user đồng bộ | UPN chính xác, MFA/Conditional Access theo chính sách | Thời điểm, phương án auth, sign-in logs |
| User mới được tạo trong OU pilot | Đối tượng xuất hiện đúng ở Entra ID | Sync latency, thuộc tính được phép |
| Đổi tên/UPN có kiểm soát | Quyền và đăng nhập liên tục theo kế hoạch | App dependency vào tên cũ |
| Vô hiệu hóa user | Quyền truy cập bị thu hồi theo mục tiêu chính sách | Token/session lifetime, độ trễ đồng bộ |
| Group membership đổi | Authorization cập nhật đúng | Claims, token renewal, ứng dụng cache |
| On-prem connectivity bị ngắt trong bài tập | Hành vi theo PHS/PTA/federation được thiết kế | Người dùng mới/cũ có đăng nhập được không |
| Break-glass cloud accounts | Có thể truy cập khẩn cấp theo chính sách khi sync/IdP lỗi | Logging, protection và quyền giám sát |

**Không xem “sync success” là đã xong migration identity.** User phải đăng nhập được và được cấp đúng quyền đối với ứng dụng. Một số thay đổi có thể chỉ có hiệu lực khi token mới được phát hành hoặc sau khi cache hết hạn.

### 9.2. Tài khoản khẩn cấp và tránh khóa chính tổ chức

Trước cutover, thiết lập quy trình **emergency access/break-glass** cho Entra ID có bảo vệ, giám sát và kiểm thử riêng. Không đặt mọi phương án đăng nhập quản trị phụ thuộc vào một IdP on-premises sắp di chuyển. Danh sách người có quyền, quy trình sử dụng, bằng chứng và cảnh báo phải được nhóm an ninh phê duyệt.

Không ghi password, token, recovery codes hoặc thông tin xác thực khẩn cấp vào tài liệu migration, script kiểm thử hay log.

## 10. Danh tính workload và ứng dụng legacy trong giai đoạn song song

Đồng bộ user không tự xử lý quyền truy cập giữa dịch vụ. Khi một API chuyển lên Azure:

- Đối với Azure Storage, Key Vault, Azure SQL và Azure APIs hỗ trợ, ưu tiên **Managed Identity** và phân quyền Azure RBAC hoặc database permission phù hợp, tránh giữ secret lâu dài.
- Đối với workload không hỗ trợ Managed Identity, dùng service principal/federated credentials và hệ thống quản lý secret theo chính sách.
- Nếu app vẫn dùng **Kerberos/Windows Integrated Authentication**, phải đảm bảo domain controller/KDC, DNS SRV lookup, SPN, thời gian đồng hồ và port truy cập hoạt động. Chỉ “có tài khoản giống tên trong Entra ID” không đủ.
- Khi dùng LDAPS hoặc ứng dụng dựa vào chứng chỉ, xác minh chain, hostname và lifecycle chứng chỉ trong Azure.
- Nếu ứng dụng đăng nhập vào database qua AD DS hoặc managed identity, phải xác minh cấu hình và hình thức xác thực được hỗ trợ của **dịch vụ database cụ thể**.

Một lựa chọn cho ứng dụng legacy là đặt AD DS domain controllers trên Azure VMs (có thiết kế site/replication/DNS, bảo mật và DR thích hợp) hoặc xem xét Microsoft Entra Domain Services khi nhu cầu/phạm vi hỗ trợ phù hợp. **Entra Domain Services không thay thế tất cả chức năng của AD DS tự quản lý**; cần đánh giá tính năng và giới hạn trước khi chọn.

### 10.1. Tính nhất quán giữa DNS, mạng và identity

Ví dụ VM Azure domain-joined:

1. VM phân giải `_ldap._tcp.dc._msdcs.corp.example.com` ra các DC phù hợp nhờ DNS/forwarders.
2. Route từ subnet VM đến DC đúng; NSG/firewall cho phép các giao thức cần thiết.
3. Đồng hồ hệ thống đồng bộ để Kerberos không lỗi do time skew.
4. User/máy có quyền AD DS hợp lệ; Group Policy và SPN đúng.
5. Khi tunnel chính lỗi, quy trình mạng dự phòng không làm mất hoàn toàn khả năng xác thực.

Từng lớp phải được kiểm tra độc lập; DNS resolve thành công **chưa chứng minh** Kerberos hoạt động, còn ping thành công **chưa chứng minh** quyền đăng nhập.

## 11. Quy hoạch migration theo wave, không cutover mọi thứ một lần

Một phương án dễ vận hành là chia thành các giai đoạn:

| Wave | Mục tiêu | DNS | Kết nối | Danh tính |
| --- | --- | --- | --- | --- |
| **0 – Discovery** | Kiểm kê phụ thuộc, owner, RTO/RPO và baseline | Record, zone, TTL, forwarder | IP/CIDR, ports, latency, routes | Users/groups, app auth, source of authority |
| **1 – Landing zone** | Tạo nền Azure | Private DNS Zone, Resolver, test FQDN | Hub/spoke, VPN/ER, NSG, monitoring | Tenant, RBAC, sync pilot và break-glass |
| **2 – Pilot** | Chạy bản ứng dụng cô lập | Test record hoặc subdomain | Kiểm tra từng dependency | Test login, token, LDAP/Kerberos nếu có |
| **3 – Hybrid production** | Chạy ứng dụng tại Azure khi database còn on-prem | Chuẩn bị TTL/record cutover | Đường đi production và HA | Đồng bộ user, quyền và workload identity |
| **4 – Data migration** | Chuyển dữ liệu/dependency về Azure | Đổi tên đích nội bộ theo kế hoạch | Chuyển đường database/queue | Cập nhật auth và permission tương ứng |
| **5 – Cutover/optimization** | Chuyển traffic và giảm phụ thuộc legacy | Thay record/ingress, giám sát cache | Giảm đường nối không còn dùng | Ngừng thành phần auth cũ khi đủ bằng chứng |
| **6 – Decommission** | Loại bỏ hạ tầng cũ an toàn | Dọn record lỗi thời | Thu hồi tunnel/route không còn dùng | Dọn account/SPN/secret theo quy trình |

Wave được sắp theo **dependency**, không nhất thiết theo loại tài nguyên. Ví dụ không thể bỏ đường mạng hybrid trước khi hoàn tất chuyển database và các tác vụ còn dùng Kerberos on-premises.

### 11.1. Điều kiện Go / No-Go cho mỗi wave

Chỉ đưa workload sang wave tiếp theo khi:

- Có owner, scope và vùng tác động được xác nhận.
- Baseline hiện tại, metric, tracing và alert hoạt động.
- DNS resolution qua các nhóm client quan trọng đã đạt.
- Route hai chiều, TLS, firewall và các dependency ports đã đạt.
- User pilot, admin và workload identity đã xác thực được.
- Dữ liệu đã được đồng bộ theo cách bảo vệ tính nhất quán; có test read/write.
- Có **rollback** rõ, người phê duyệt, tiêu chí dừng và cách đo RTO/RPO.

Nếu điều kiện không đạt, tạo blocker cụ thể và đánh giá lại kiến trúc; không bù bằng cách mở quá rộng firewall hoặc cho phép ẩn danh để “vượt qua” bài test.

## 12. Quy trình cutover DNS và traffic có kiểm soát

Giả sử `orders.example.com` hiện trỏ vào ingress on-premises và sẽ trỏ sang ingress Azure. Trình tự nên chuẩn bị kỹ hơn một lệnh sửa A/CNAME.

### Trước ngày chuyển đổi

1. Xác minh quyền kiểm soát public authoritative zone và thay đổi bản ghi; ghi snapshot A/AAAA/CNAME, TTL, DNSSEC/DS nếu liên quan.
2. Xác nhận TLS certificate, SNI/hostname bindings, WAF, CDN hoặc Front Door/backend health ở Azure, tránh chuyển traffic vào đích không sẵn sàng.
3. Giảm TTL **đủ sớm** để cache cũ hết hạn, không chỉ trước vài phút.
4. Xác nhận DNS private cho database/Key Vault/Storage và các client hybrid; không trộn public record với private endpoint record.
5. Chuẩn bị kiểm tra người dùng bằng test hostname hoặc host-specific route mà không ảnh hưởng production (và bảo đảm TLS/Host header đúng).
6. Chạy load test có kiểm soát, đo SLI/SLO và khả năng phục hồi.
7. Đánh giá **data ownership**: nguồn nào có quyền ghi và trạng thái dữ liệu khi chuyển traffic? Tránh hai nơi cùng ghi không có cơ chế giải quyết xung đột.

### Trong cutover

~~~mermaid
sequenceDiagram
    participant IC as Incident/Change Lead
    participant DNS as Authoritative DNS
    participant OLD as Ingress cũ
    participant NEW as Azure ingress
    participant MON as Monitoring
    IC->>MON: Bắt đầu timestamp UTC và baseline
    IC->>NEW: Kiểm tra health, TLS và giao dịch synthetic
    IC->>DNS: Thay record theo change đã duyệt
    DNS-->>IC: Record cập nhật
    MON->>NEW: Synthetic request từ nhiều vị trí
    MON->>OLD: Theo dõi request còn về đích cũ
    NEW-->>MON: Success, latency, dependency status
    IC->>MON: Đối chiếu SLO và trạng thái dữ liệu
    Note over IC,MON: Go / rollback theo tiêu chí định trước
~~~

Đối với ứng dụng có thể dùng traffic management trọng số, blue/green hoặc reverse proxy, chuyển dần một phần request có thể an toàn hơn cutover DNS một bước. Dù dùng cơ chế nào, cần theo dõi **người dùng thật** và synthetic test; chứng minh DNS trả IP mới chưa đủ.

### Sau cutover

- Kiểm tra phân giải từ DNS công khai, on-premises và Azure theo cùng FQDN; ghi resolver và timestamp.
- Theo dõi request vẫn đến môi trường cũ, connection lâu sống và DNS cache.
- Kiểm tra sign-in logs, MFA, token, domain-joined app, claims/group permissions.
- Kiểm tra database write consistency, queue backlog, log ingestion, backup và cảnh báo.
- Giữ read-only hoặc rollback window ở môi trường cũ khi có thể; không xóa ngay tài nguyên.
- Chỉ tăng TTL trở lại khi đường mới ổn định và chính sách thay đổi cho phép.

## 13. Rollback không chỉ là sửa lại DNS

**Rollback DNS** có thể hướng **request mới** về ingress cũ, nhưng không tự đồng bộ dữ liệu đã ghi tại Azure và không hủy các token/session hoặc kết nối đã mở. Với hệ thống stateful, cần xác định **đâu là nguồn dữ liệu authoritative** trong từng pha.

| Tình huống | Rủi ro | Phương án phải định nghĩa trước |
| --- | --- | --- |
| Azure frontend lỗi, database vẫn on-prem | Ít thay đổi dữ liệu giữa hai nơi nếu cùng ghi vào DB cũ | Chuyển ingress lại, kiểm tra request đang xử lý |
| Database đã promote tại Azure rồi rollback app | Hai nguồn dữ liệu cùng được ghi, split-brain | Fence writer, đồng bộ/replay có kiểm soát và quy trình data owner |
| User đổi mật khẩu trong giai đoạn song song | Password/hash sync, auth policy và thời gian hội tụ khác nhau | Quy định source of authority và kiểm tra login sau rollback |
| DNS private đổi sai | Client kết nối nhầm public endpoint hoặc sai IP | Snapshot zone/records, rollback link/forwarding và kiểm tra từ các VNet |
| VPN/ER lỗi giữa cutover | Workload Azure không truy cập hệ thống on-prem | Route dự phòng, degrade-mode hoặc dừng chuyển dịch vụ |
| TTL/caching kéo dài | Client chia traffic giữa hai ingress | Giữ compatibility của cả hai đích, monitoring/traffic draining |

**Tiêu chí rollback** nên cụ thể: tỷ lệ lỗi nghiệp vụ vượt ngưỡng trong một cửa sổ quan sát, mất kết nối tới DB, lỗi đăng nhập nghiêm trọng hoặc nguy cơ mất dữ liệu. Người có quyền rollback phải được xác định sẵn, cùng mốc thời gian, cách xác minh và quy tắc thông báo.

Không giảm bảo mật để cứu một cutover lỗi nếu chưa được phê duyệt. Cách khôi phục an toàn có thể là **dừng ghi tạm thời**, giữ dịch vụ ở chế độ chỉ đọc và ưu tiên bảo toàn dữ liệu.

## 14. Quan sát và diễn tập lỗi khi hybrid

Kết hợp Azure Monitor, Application Insights, Log Analytics, Network Watcher, các metric gateway và log danh tính (Microsoft Entra sign-in/provisioning/synchronization theo khả năng thu thập) với công cụ vận hành on-premises.

Các tín hiệu tối thiểu:

| Tầng | Chỉ số | Lý do |
| --- | --- | --- |
| DNS | Tỷ lệ resolve thành công, IP trả về, query latency, failures/loops | Phát hiện tên sai hoặc nguồn phân giải không mong đợi |
| Hybrid network | Tunnel/circuit state, BGP routes, bytes, errors, latency và packet loss | Phân biệt mất tuyến với lỗi app |
| Compute/API | Success rate, p95/p99 latency, dependency failures | Đo tác động người dùng thực |
| Dữ liệu | DB connection success, transaction errors, replication lag, queue backlog | Phát hiện data dependency bị lỗi |
| Identity | Sign-in errors, sync failures, MFA/CA outcomes, agent health | Phát hiện khóa tài khoản và quyền không khớp |
| Security | NSG/firewall denies, Key Vault access failures, certificate expiry | Phát hiện đường bị chặn hoặc quyền bị thiếu |
| FinOps | Egress, VPN/ER/Resolver costs, logging ingest | Kiểm soát chi phí song song và sau migration |

### 14.1. Diễn tập lỗi cần thử trước cutover

- **DNS resolver lỗi:** Một server forwarder không phản hồi; client có dùng đường dự phòng đúng hay timeout?
- **Sai private DNS link:** Azure workload ở spoke thứ hai còn phân giải đúng Private Endpoint không?
- **Mất tunnel chính:** Route/BGP và DNS đến on-prem có hoạt động qua đường dự phòng?
- **AD sync tạm ngừng:** User đã đồng bộ có đăng nhập theo thiết kế được không; người dùng mới được cập nhật khi nào?
- **Mất một phương thức xác thực on-prem:** Ứng dụng đã dùng PHS/PTA/federation như dự kiến và có emergency access không?
- **DB network latency tăng:** Connection timeout/retry/backoff có làm quá tải app không?
- **Rollback sau một phần traffic chuyển:** Session, ghi dữ liệu và cache có được xử lý an toàn không?

Thực hiện trong môi trường test hoặc phạm vi được phê duyệt, có synthetic data, quan sát và điều kiện dừng. Không cố gây sự cố diện rộng trên production chỉ để “thử cho đủ”.

## 15. Tài liệu bàn giao và ma trận phụ trách

Một migration cần nhiều nhóm: network, DNS, identity, application, database, security và FinOps. Nếu không có owner rõ, sự cố dễ bị đẩy qua lại giữa các nhóm.

| Hạng mục | Người chịu trách nhiệm chính | Bằng chứng bàn giao |
| --- | --- | --- |
| Public DNS/registrar/TTL | DNS/platform team | Bản ghi trước/sau, authority, quyền rollback |
| Private DNS/Resolver | Azure networking | Zone links, rulesets, target IP, query test |
| VPN/ExpressRoute/routing | Network team | Route table, failover test, bandwidth/latency |
| AD DS/Entra sync | Identity team | Source mapping, sync status, UPN/attribute tests |
| Auth và application permissions | App + security | Sign-in logs, RBAC, Managed Identity, tests |
| Database và data migration | Data team | Sync/checksum, write ownership, rollback/failback |
| Monitoring và incident response | SRE | SLI/SLO dashboard, alerts, runbook |
| Chi phí và quota | FinOps/platform | Dự báo VPN/ER, Resolver, egress, capacity, budget |
| Điều phối cutover | Change/incident lead | Go/No-Go, timeline UTC, stakeholder updates |

Mỗi hạng mục nên có **người thay thế (backup owner)**, mốc hoàn thành và liên kết tới tài liệu/cấu hình đã review. DNS và identity là tài nguyên hạ tầng dùng chung: thay đổi cần được đánh giá tới **mọi workload phụ thuộc**, không chỉ ứng dụng đang di chuyển.

## 16. Bài thực hành: thiết kế migration cho ứng dụng đặt hàng

**Bối cảnh:** Doanh nghiệp có datacenter `10.10.0.0/16`, AD DS ở `corp.example.com` và ứng dụng `orders.example.com` trên VM. SQL Server `sql01.corp.example.com` vẫn ở on-premises trong giai đoạn đầu. Doanh nghiệp xây Azure hub `10.40.0.0/16`, app spoke `10.41.0.0/16`, data spoke `10.42.0.0/16`. Ứng dụng Azure cần Storage private endpoint; nhân viên dùng Entra ID SSO, còn một batch worker cần Kerberos tới AD DS. Số liệu/tên là giả định để thực hành.

### Nhiệm vụ A — Vẽ sơ đồ DNS và networking

1. Xác định authoritative server cho `example.com`, `corp.example.com` và `privatelink.blob.core.windows.net`.
2. Thiết kế DNS query path từ **on-prem client**, **Azure VM** và **app trong spoke** tới database và Storage Private Endpoint.
3. Vẽ VPN hoặc ExpressRoute, hub/spoke routes, firewall/NSG rules cần thiết, return path.
4. Tìm ít nhất hai điểm lỗi đơn và phương án giám sát/dự phòng.

**Đáp án định hướng:** On-prem authoritative DNS quản lý `corp.example.com`, private DNS zone gắn với Azure và resolver có inbound/outbound phù hợp. Azure không được forward vòng ngược về chính nó. Azure workload truy cập on-prem SQL qua hybrid route; client Azure nhận private IP khi gọi FQDN storage qua đúng DNS path.

### Nhiệm vụ B — Thiết kế identity synchronization

1. Lập danh sách user/group pilot, UPN và source anchor; xác minh cloud-only object trùng tên.
2. Đề xuất Connect Sync hoặc Cloud Sync theo yêu cầu; ghi rõ tính năng phải kiểm chứng trước khi chọn.
3. Chọn PHS/PTA/federation theo mục tiêu availability của doanh nghiệp; phân tích tác động khi datacenter mất kết nối.
4. Tách quyền **user SSO** và **batch Kerberos**; đề xuất cách giữ AD DS cho legacy hoặc kế hoạch hiện đại hóa.
5. Thiết kế emergency access, Conditional Access/MFA, rollback và các phép kiểm tra sign-in.

**Đáp án định hướng:** Đồng bộ object và xác thực là hai lớp khác nhau. Entra ID không trực tiếp thay AD DS cho Kerberos/LDAP; batch worker vẫn cần DNS/route/DC hoặc phải được sửa. Pilot phải kiểm tra đăng nhập, group claims và quyền truy cập thực tế.

### Nhiệm vụ C — Lập kế hoạch cutover

Điền bảng:

| Thời điểm | Thao tác | Ai duyệt | Bằng chứng đạt | Điều kiện rollback |
| --- | --- | --- | --- | --- |
| T−vài ngày | Giảm public TTL; kiểm kê DNS | DNS owner | Câu trả lời mới/old TTL đã được quan sát | DNS record không nhất quán |
| T−1 ngày | Probe đường hybrid, DNS, identity, DB | Network + identity + app | Test matrix đạt | Một dependency quan trọng thất bại |
| T0 | Chốt data writer và bật Azure ingress | Change lead + data owner | SLI và dữ liệu đúng | Rủi ro split-brain hoặc DB lỗi |
| T+giám sát | Đổi public DNS hoặc routing weight | DNS/change lead | Request mới đến đích đúng | 5xx/latency/đăng nhập vượt ngưỡng |
| T+ổn định | Theo dõi cache, backlog, telemetry | SRE | SLO đạt liên tục | Bất thường dữ liệu |
| Sau kỳ bảo lưu | Thu hồi hạ tầng cũ có kiểm soát | App + data + security | Không còn dependency | Chưa có đủ bằng chứng |

Không đưa ngày giả định thành lịch sản xuất. Mốc và người phê duyệt phải được tổ chức chấp thuận.

### Nhiệm vụ D — Soạn checklist xác minh

Tạo checklist từ cả ba nơi: on-premises, Azure VM, máy bên ngoài. Với mỗi nguồn, kiểm tra DNS A/CNAME/SRV, TCP/TLS, truy vấn nghiệp vụ, user login, quyền worker, telemetry, cost/latency và đường rollback. Báo cáo **kết quả thực đo**, không chỉ kết quả lệnh trả exit code 0.

### Tiêu chí đạt của bài thực hành

- Sơ đồ thể hiện DNS ownership, resolver paths và không có forwarding loop.
- Quy hoạch CIDR không trùng, có route hai chiều và firewall tối thiểu cho SQL/AD/Storage.
- Có identity source of authority, scope sync, mô hình auth và test account pilot rõ ràng.
- Có lịch wave migration, Go/No-Go, rollback/data ownership và tiêu chí SLI/RTO/RPO.
- Có bằng chứng đo từ nhiều vị trí, owner và sự thống nhất giữa DNS, mạng và danh tính.

## 17. Lỗi phổ biến và cách khắc phục

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
| --- | --- | --- |
| VM Azure không tìm được domain controller | DNS client dùng public resolver; thiếu forward zone/SRV hoặc route tới AD DNS | Kiểm tra DNS servers, SRV lookup, route và port |
| Private Endpoint vẫn phân giải về public IP | Zone link thiếu, custom DNS không forward, sai namespace hoặc record | Kiểm tra CNAME chain, private A record, VNet links và inbound endpoint |
| On-premises không resolve tên PaaS private | Forwarder không trỏ tới Azure resolver/không có đường đi | Thử query trực tiếp tại on-prem DNS và inbound endpoint |
| DNS timeout tăng cao | Forwarding loop hoặc target DNS không reachable | Kiểm tra quy tắc hai chiều, logs và health của resolver |
| Tunnel “Connected” nhưng SQL không truy cập được | UDR/BGP, NSG, firewall, return path hoặc DB listener sai | Kiểm tra từ IP source thật theo từng lớp |
| API TLS lỗi sau cutover | Certificate/hostname/SNI không phù hợp | Kiểm tra binding của ingress và FQDN ứng dụng |
| User đồng bộ nhưng không đăng nhập được | UPN, Conditional Access/MFA, phương án auth hoặc object matching | Sign-in logs, sync logs, pilot mapping |
| User trùng hoặc mất quyền | Trùng UPN/alias, source anchor mapping hoặc group changes | Tạm dừng scope mở rộng, xác minh liên kết và khôi phục theo quy trình identity |
| Kerberos/LDAP lỗi dù Entra sign-in tốt | AD DS dependency chưa được di chuyển/không reach được | Kiểm tra DC, DNS, time sync, SPN và các cổng cần thiết |
| Rollback DNS xong nhưng dữ liệu không đúng | Hai phía đã cùng ghi, chưa có replication/reconciliation | Data owner kiểm tra authoritative writer và phục hồi dữ liệu |
| Cost tăng bất ngờ sau cutover | Egress xuyên region, Resolver, VPN/ER, log retention hoặc traffic đúp | Cost Analysis theo scope, meter, service và thời điểm |

## 18. Những nguyên tắc cần nhớ

1. **DNS quyết định đích theo tên, routing quyết định đường tới IP, identity quyết định ai được truy cập.** Cả ba phải đạt trước khi công bố migration thành công.
2. **DNS private cần đường truy vấn đúng.** Azure Private DNS Zone, VNet links, Private Resolver, conditional forwarders và DNS của client phải nhất quán; tránh forward loops.
3. **Kết nối hybrid là một hệ thống mạng thực sự.** VPN/ExpressRoute cần address plan không chồng lấn, routing hai chiều, bảo mật, HA và kiểm thử ứng dụng, không chỉ trạng thái gateway.
4. **Đồng bộ danh tính không đồng nghĩa thay AD DS.** Entra ID, AD DS, Connect Sync/Cloud Sync, phương án PHS/PTA/federation và Kerberos/LDAP có vai trò riêng.
5. **Pilot trước, cutover theo wave.** Giảm TTL đủ sớm, thử nhiều vị trí, xác nhận chứng chỉ/đăng nhập/dữ liệu rồi mới chuyển traffic sản xuất.
6. **Rollback cần kế hoạch dữ liệu và xác thực.** Đổi DNS về đích cũ chưa giải quyết token, session, database writes và khả năng split-brain.
7. **Phải đo từ góc nhìn người dùng.** DNS query đúng, VPN connected hay sync status success đều chưa chứng minh giao dịch hoàn chỉnh hoạt động.
8. **Chọn chủ sở hữu và giữ tài liệu cập nhật.** Networking, DNS, identity, application, data và FinOps cần phối hợp trên cùng runbook.

Khi lập kế hoạch DNS, kết nối và đồng bộ danh tính như **một thiết kế tổng thể**, doanh nghiệp có thể chuyển ứng dụng lên Azure theo từng giai đoạn, duy trì khả năng phục vụ trong thời kỳ hybrid, bảo vệ danh tính và dữ liệu, đồng thời giảm rủi ro phát sinh khi cắt chuyển và thu hồi hạ tầng cũ.
