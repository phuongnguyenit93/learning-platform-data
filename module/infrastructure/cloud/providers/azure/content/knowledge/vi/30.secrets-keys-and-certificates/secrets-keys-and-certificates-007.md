# Private endpoint và giới hạn truy cập Key Vault

Trong module **CLOUD_PROVIDERS_AZURE**, người học khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Mục tiêu cuối cùng là triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure. Thuộc chương **Secret, khóa và chứng chỉ**, bài học này giải thích cách giới hạn đường truy cập đến **Azure Key Vault** bằng **Private Endpoint/Private Link**, Azure Virtual Network, DNS riêng và các chính sách mạng, đồng thời kết hợp đúng với xác thực và phân quyền.

Ví dụ xuyên suốt: một ứng dụng Java Spring Boot chạy trên **Azure Kubernetes Service (AKS)** cần đọc secret `orders-db-password` từ Key Vault. Chính sách bảo mật yêu cầu không thể lấy secret từ Internet công cộng, kể cả người có tài khoản Azure đăng nhập hợp lệ; chỉ workloads trong mạng riêng được cấp quyền mới được đọc. Đội vận hành cũng cần triển khai cấu hình mà không tự khóa đường quản trị, xử lý private DNS, cho phép CI chạy kiểm thử có kiểm soát và quan sát những truy cập bị từ chối.

Sau bài học, bạn có thể:

- Phân biệt **Key Vault control plane, data plane, network authorization và identity authorization**.
- Chọn đúng giữa **public endpoint + firewall/IP allowlist**, **Virtual Network service endpoint** và **Private Endpoint**; hiểu giới hạn của **trusted Microsoft services bypass**.
- Thiết kế **Private Link**, private DNS zone `privatelink.vaultcore.azure.net`, VNet links và kết nối hybrid qua VPN/ExpressRoute.
- Triển khai và kiểm tra cấu hình bằng **Azure Portal, Azure CLI**, DNS/TLS probes, Key Vault REST/SDK và **Java Azure SDK**.
- Thiết lập **Microsoft Entra ID, managed/workload identity, Azure RBAC hoặc access policies** đúng data plane, không nhầm mạng riêng với quyền đọc secret.
- Hiểu trình tự chuyển đổi từ public sang private mà không gây outage, cách xử lý `403 Forbidden`, DNS sai, private endpoint chưa approved, SSL errors, RBAC propagation và route/firewall issues.
- Kiểm tra chính sách bằng **negative tests**, ghi audit logs, thiết lập alerts, rollback và tối ưu chi phí vận hành.

## 1. Key Vault bảo vệ những gì?

**Azure Key Vault** là dịch vụ được quản lý để lưu trữ và truy cập:

| Loại đối tượng | Mục đích | Ví dụ |
|---|---|---|
| **Secret** | Chuỗi/giá trị bí mật và phiên bản | Password, API key, connection secret |
| **Key** | Khóa mật mã và thao tác cryptographic theo chính sách | RSA key dùng sign/verify, wrap/unwrap |
| **Certificate** | Quản lý vòng đời chứng chỉ và metadata liên quan | TLS certificate, policy/renewal |

Không phải mọi thao tác certificate đều là một lần đọc secret thông thường: certificate có các đối tượng liên quan, và khi cần lấy **private-key-bearing certificate material** có thể cần quyền truy cập secret tương ứng. Chọn data-plane roles theo đúng loại thao tác thực tế.

### 1.1. Bốn điều kiện cho một lần đọc secret

Một request lấy secret phải đi qua nhiều lớp:

```text
Java application
      |
      v
1. DNS resolves <vault>.vault.azure.net
      |
      v
2. Network path and Key Vault network policy
   (public firewall OR approved private endpoint)
      |
      v
3. Microsoft Entra authentication
   (token, audience, identity)
      |
      v
4. Data-plane authorization
   (Azure RBAC or vault access policies)
      |
      v
Key Vault returns secret value over TLS
```

**Private Endpoint chỉ xử lý lớp đường mạng.** Nó không tự cấp `secrets/get`. Ngược lại, một identity có quyền `Key Vault Secrets User` không tự vượt được firewall của Key Vault. Muốn đọc thành công, **cả mạng lẫn identity/authorization** phải hợp lệ.

### 1.2. Bảo mật “hai khóa”

Có thể nhớ:

```text
ALLOW_ACCESS =
  NETWORK_PATH_ALLOWED
  AND AUTHENTICATED_IDENTITY
  AND DATA_PLANE_PERMISSION
  AND APPLICATION_POLICY_ALLOWED
```

Đây là **mô hình suy nghĩ**, không phải một Azure Policy expression thực thi. Ngoài cloud policy, ứng dụng vẫn cần authorization nghiệp vụ để tránh client hợp lệ đọc secret không liên quan.

### 1.3. Key Vault không phải kho dữ liệu ứng dụng tốc độ cao

Không gọi Key Vault trên **mọi request** của web app chỉ để lấy cùng một secret. Bên cạnh chi phí/latency và throttling, cách này làm Key Vault thành dependency synchronous ở hot path. Nên dùng credential cache/secret cache với TTL/rotation policy phù hợp, hạn chế log secret value, và đảm bảo revocation/rotation không bị cache quá lâu.

## 2. Phân biệt control plane và data plane

**Control plane** dùng Azure Resource Manager (ARM) để tạo/sửa tài nguyên Key Vault, cấu hình mạng, phân quyền, diagnostics và policy. **Data plane** dùng endpoint của vault để `get/list/set/delete` secret, sign/verify key, thao tác certificate...

| Mặt phẳng | Endpoint/luồng khái niệm | Ví dụ hoạt động | Hệ quả bảo mật |
|---|---|---|---|
| **Control plane (ARM)** | Azure Resource Manager APIs | `az keyvault create/update/show`, cấu hình network ACL | Quyền ARM/RBAC quản trị phải được giới hạn |
| **Data plane (vault)** | `https://<vault>.vault.azure.net` | `SecretClient.getSecret("orders-db-password")` | Chịu network access rules và data-plane authorization |
| **Identity plane** | Microsoft Entra ID token endpoint | Managed identity lấy access token | Token audience/tenant/principal phải đúng |
| **Application layer** | API/worker do doanh nghiệp sở hữu | App quyết định ai được gọi logic dùng secret | Không thay bằng network allowlist |

### 2.1. Bẫy quan trọng: tắt public access không khóa mọi thao tác quản trị

`publicNetworkAccess: Disabled` chủ yếu bảo vệ **đường truy cập data plane Key Vault qua endpoint công khai**. Nó **không phải một lệnh vô hiệu hóa toàn bộ Azure Resource Manager control plane**. Người có quyền quản trị phù hợp vẫn có thể thay đổi cấu hình vault qua ARM từ con đường quản trị được phép. Vì vậy phải bảo vệ **quyền ARM**, dùng Azure Policy, PIM, approvals, activity logs và các cơ chế quản trị khi cần; không chỉ tạo private endpoint.

### 2.2. Quyền quản lý vault không đồng nghĩa quyền đọc secret

Nếu vault dùng **Azure RBAC data-plane model**, một principal có quyền ARM quản lý tài nguyên không tự động có quyền đọc giá trị secret chỉ vì có quyền “Contributor”. Ngược lại, quyền ARM cao có thể cho phép **thay role assignments hoặc network settings** khi role/permissions cho phép, dẫn đến đường leo thang quyền; phải đánh giá blast radius. Với **legacy access policy model**, các quyền quản lý/access policies có mô hình quản trị khác. Chọn một mô hình rõ ràng, quản lý qua IaC và kiểm tra quyền thực tế bằng request.

## 3. Những cách giới hạn truy cập mạng

Key Vault có thể được bảo vệ theo các mô hình mạng:

| Mô hình | Đường dữ liệu | Quy tắc | Ưu điểm | Hạn chế |
|---|---|---|---|---|
| **Public endpoint mặc định** | Internet → public vault FQDN | Có thể cho phép từ mọi mạng tùy cài đặt | Dễ bắt đầu | Bề mặt mạng rộng nếu không hạn chế |
| **Public endpoint + firewall/IP rules** | Public endpoint | Chỉ IPv4 public/CIDR allowlist hợp lệ | Phù hợp nguồn có egress IP cố định | IP thay đổi/NAT, vẫn qua public endpoint |
| **Virtual Network service endpoint** | Service endpoint tới dịch vụ, endpoint logic vẫn public | Key Vault network ACL cho phép subnet | Hạn chế từ VNet/subnet phù hợp | Không có private IP cho vault, cần subnet/service endpoint cấu hình đúng |
| **Private Endpoint** | VNet → private IP → Private Link → vault | Approved private endpoint + DNS + quyền | Truy cập riêng tư, có thể tắt public data-plane access | DNS/hybrid/peering, phê duyệt, monitoring và chi phí phức tạp hơn |

Các lựa chọn cụ thể còn phụ thuộc **Key Vault loại nào, vùng, yêu cầu tuân thủ và cấu hình Azure hiện hành**. **Managed HSM** có mô hình endpoint/network/permissions khác; bài học tập trung vào **Azure Key Vault vault** chứa secrets/keys/certificates thông thường, không mặc định áp toàn bộ lệnh cho Managed HSM.

### 3.1. Giữ public endpoint nhưng dùng allowlist có đủ không?

Đôi khi đủ cho một workload nhỏ có egress IPv4 cố định và yêu cầu bảo mật cho phép. Nhưng với AKS/App Service, egress IP có thể thay đổi theo kiến trúc/NAT/scale; cấu hình IP rules bị drift và ngoài ý muốn. **Một IP được phép không xác thực ứng dụng**: mọi principal có token/quyền data plane phù hợp từ IP đó đều có thể thử gọi, nên identity vẫn là lớp độc lập.

### 3.2. Service endpoint khác Private Endpoint thế nào?

Với **Virtual Network service endpoint**, mạng Azure nhận diện traffic từ subnet được cấp phép tới Key Vault service. Vault vẫn sử dụng FQDN công khai; bạn cấu hình **service endpoint cho `Microsoft.KeyVault`** trên subnet và **network rule cho subnet** trên vault. Không có một NIC private IP riêng cho mỗi vault như Private Endpoint. Với Private Endpoint, DNS thường đưa FQDN vault về **private IP của endpoint trong VNet**.

### 3.3. Public network access, default action và bypass là ba khái niệm khác

- **`publicNetworkAccess`** điều khiển khả năng truy cập data plane qua mạng công khai theo model/tính năng hiện hành.
- **`networkAcls.defaultAction`** (Allow/Deny) là default của firewall rules áp dụng cho đường công khai khi được bật.
- **`networkAcls.ipRules`/`virtualNetworkRules`** là các exceptions allowlist khi model đó được dùng.
- **`networkAcls.bypass`** có thể cho phép một tập **trusted Microsoft services** hữu hạn trong những cấu hình được hỗ trợ; không có nghĩa mọi Azure resource được miễn firewall.

**Không trông chờ IP allowlist hay “trusted services” bypass như đường cứu hộ sau khi tắt public network access**, nếu chính sách/feature đó không còn cho phép đường công khai. Hãy kiểm tra hành vi chính xác của resource API/tier và thiết kế **private management/test access** trước khi đóng public access.

## 4. Private Link và Private Endpoint hoạt động ra sao?

**Azure Private Link** cho phép truy cập một dịch vụ được hỗ trợ qua **Private Endpoint** – một network interface/private IP trong VNet của bạn gắn với một target resource/subresource. Với Key Vault thông thường, subresource/group ID dùng cho private endpoint là **`vault`**.

```text
Azure subscription A                         Azure-managed service
  +--------------------------------+         +---------------------+
  | VNet vnet-app-prod              |         | Azure Key Vault     |
  |                                |         | kv-orders-prod      |
  |  AKS / VM / private app         |         |                     |
  |       |                        |         | Data plane          |
  |       | TLS to vault FQDN      |         |                     |
  |       v                        |         +-----------+---------+
  |  Private DNS resolution        |                     ^
  |       |                        |                     |
  |       v                        |           Private Link service
  |  10.42.5.4  (private endpoint) +---------------------+
  |                                |
  +--------------------------------+

Client URL stays: https://kv-orders-prod.vault.azure.net/
DNS inside VNet: resolves to PE private IP (example 10.42.5.4)
```

**Địa chỉ 10.42.5.4 là ví dụ.** Không lấy địa chỉ IP được minh họa để cấu hình thật. Private Endpoint phải được tạo trong subnet hợp lệ của VNet và trạng thái kết nối được **Approved** bởi owner có quyền. Nếu target vault và VNet ở các subscription/tenant khác nhau, cần quyền/phê duyệt theo mô hình kết nối thực tế.

### 4.1. Private Endpoint thuộc VNet, không thuộc Pod

AKS pods/VMs dùng tuyến mạng đến IP private endpoint; bạn không phải tạo một Private Endpoint trên từng Pod. Một endpoint có thể được nhiều workloads trong những mạng **có route và DNS phù hợp** sử dụng, nhưng cần xem policy tenant isolation/network segmentation. Nếu các VNets không có connectivity hợp lệ, không có chuyện “cùng subscription là tự truy cập được”.

### 4.2. Private Endpoint không biến vault thành một VM nội bộ

Key Vault vẫn là dịch vụ được Microsoft quản lý. Private Endpoint là **điểm vào riêng tư**; bạn không có shell trên Key Vault, không kiểm soát OS/keys trên server như một máy ảo. Các managed service quotas, API permissions, auditing và Key Vault data-plane behaviors vẫn tồn tại.

### 4.3. Cấu hình endpoint không tự bật mã hóa bí mật

Private Link hạn chế đường truyền trên mạng Azure, nhưng vẫn phải dùng **HTTPS/TLS với hostname validation** và authentication. Không đổi URL SDK sang `https://10.42.5.4` để “đi thẳng IP”: TLS certificate và HTTP host name thường gắn với **`<vault>.vault.azure.net`**. Hãy giữ **tên vault công khai hợp lệ** trong SDK, để DNS chọn private route.

## 5. Private DNS: phần quyết định lưu lượng có đi qua endpoint hay không

Private Endpoint không đủ nếu DNS của ứng dụng vẫn trả public IP. Với Azure Key Vault thông thường, private DNS zone tiêu chuẩn là:

```text
privatelink.vaultcore.azure.net
```

Client vẫn gọi:

```text
https://<vault-name>.vault.azure.net
```

Ở mô hình Private Link được cấu hình đúng, DNS chain thường như sau:

```text
kv-orders-prod.vault.azure.net
       CNAME
kv-orders-prod.privatelink.vaultcore.azure.net
       A record (private DNS linked to VNet)
10.42.5.4   <-- example PE private IP
```

CNAME/details của public DNS chain có thể có thêm lớp hoặc thay đổi theo Azure; **điều cần xác minh là hostname vault khi được resolve từ workload VNet dẫn đến đúng private endpoint IP**, chứ không hard-code toàn bộ chuỗi CNAME.

### 5.1. Vì sao dùng zone `privatelink.vaultcore.azure.net`?

Microsoft khuyến nghị domain private-link phù hợp để private endpoint và private DNS hoạt động thống nhất. **Không tạo private zone `vault.azure.net` bừa bãi**: nó có thể shadow các bản ghi công khai cho những vault khác và gây sự cố phân giải DNS. Cũng không đặt endpoint vào một địa chỉ hard-coded trong file `hosts` production: không chịu được failover/thay IP và khó audit.

### 5.2. Các thành phần DNS

| Thành phần | Vai trò | Lỗi phổ biến |
|---|---|---|
| Private DNS zone | Chứa A record private link cho vault | Tạo sai tên zone |
| A record | Map vault alias → PE IP | Record trỏ IP cũ |
| Virtual Network link | Cho VNet dùng private zone resolution | Quên link VNet của AKS/VM |
| Private Endpoint DNS zone group | Tích hợp quản lý DNS cho endpoint | Zone group thiếu hoặc trỏ sai zone |
| Custom DNS forwarder/resolver | Phục vụ enterprise/hybrid name resolution | Không forward đúng zone/private DNS |
| Workload DNS cache | JVM/OS/CoreDNS cache kết quả DNS | Vẫn dùng IP cũ sau cutover |

### 5.3. Cần kiểm tra từ chính workload

Chạy `nslookup`/`dig` bên trong đúng AKS Pod, VM hoặc runner/VNet tương ứng; **Azure Cloud Shell mặc định không ở trong VNet ứng dụng**, nên việc Cloud Shell resolve public IP **không chứng minh Private Endpoint của app sai**. Đừng chỉ kiểm tra từ laptop cá nhân khi VPN/DNS path khác AKS.

### 5.4. Một vault nhiều private endpoints

Một vault có thể có nhiều Private Endpoint trong những mạng/vùng phù hợp. Quản lý **một private DNS zone và các links/records** cần xét cách Azure tạo A records, resolver context và có thể có nhiều IP tương ứng. Một Private DNS zone dùng chung cho nhiều endpoints của **cùng vault** qua các VNets có thể dẫn workload về endpoint khác dự kiến; cần thiết kế **DNS zones/resolution scopes** theo topology, không tự gắn cùng zone group cho mọi PE rồi nghĩ nó luôn chọn IP gần nhất.

## 6. Thiết kế cho AKS, App Service, VM và on-premises

### 6.1. AKS

```text
AKS Pod -> CoreDNS / node DNS -> private DNS resolution
        -> VNet route / firewall / NSG
        -> Private Endpoint IP -> Key Vault data plane
        -> Entra workload identity -> Key Vault RBAC
```

Kiểm tra cả **DNS** và **identity**. Một Pod có đúng federated identity nhưng DNS trỏ public IP sẽ gặp network denial. Một Pod resolve private IP đúng nhưng thiếu `Key Vault Secrets User` vẫn nhận authorization denial.

### 6.2. App Service / Azure Functions

App Service/Functions thường cần **VNet Integration** (với plan và tính năng hỗ trợ) để outbound traffic từ app đi vào VNet tới Private Endpoint. **Private Endpoint cho inbound traffic của App Service** là một tính năng/đối tượng khác – không tự đồng nghĩa app có **outbound** đến Key Vault. Xác nhận outbound routing, DNS configuration và pricing/plan constraints.

### 6.3. Azure VM

VM trong VNet liên kết DNS zone, route được đến private IP và có managed identity/RBAC phù hợp có thể lấy secret qua vault FQDN. Khi VM dùng custom DNS, đừng giả định link private zone tự khắc được custom DNS sử dụng; cần forwarder/resolver.

### 6.4. On-premises qua VPN/ExpressRoute

Một máy on-prem không tự truy cập `10.42.5.4` chỉ vì vault có Private Endpoint. Cần **kết nối mạng riêng** (site-to-site VPN/ExpressRoute hoặc giải pháp tương đương), route, firewall và DNS giải được alias vault thành private IP. Thường cần **Azure DNS Private Resolver inbound endpoint** hoặc DNS forwarder trong VNet để phục vụ truy vấn từ on-prem; **Azure-provided DNS virtual IP 168.63.129.16 không phải DNS resolver trực tiếp có thể dùng từ bất kỳ máy on-prem nào**.

### 6.5. Peering/hub-spoke

VNet peering không tự gắn private DNS link cho mọi spoke. Nếu app chạy ở spoke, xác minh DNS forwarding và private zone visibility từ spoke, cùng UDR/firewall/NSG. Trong hub-spoke dùng custom DNS, có thể link zone vào DNS resolver/hub VNet và forward đúng; trong mô hình Azure-provided DNS, cần link các VNets liên quan theo thiết kế.

## 7. Lựa chọn chiến lược bảo vệ Key Vault

Không có một cấu hình “an toàn nhất” dùng vô điều kiện cho mọi workload. Cần đối chiếu **phạm vi mạng được phép, cách vận hành, tính di động của developer/CI, mức tuân thủ và chi phí**.

### 7.1. Bảng quyết định

| Nhu cầu | Phương án cân nhắc | Điều kiện |
|---|---|---|
| Demo/dev sandbox, không chứa secret thật | Public endpoint với RBAC và firewall nếu cần | Quản lý vòng đời, không nhúng secret trong source |
| CI có egress IP cố định và chưa có VNet | Public firewall/IP rules riêng cho test vault | Có policy cho phép và IP quản lý được |
| VM trong subnet được tin cậy, public endpoint cho phép | Service endpoint + VNet rules | Chấp nhận endpoint logic công khai |
| Production cần data plane private-only | **Private Endpoint + public network access Disabled** | DNS/routing/identity chuẩn bị trước |
| Hybrid datacenter cần đọc Vault | Private Endpoint + VPN/ExpressRoute + DNS resolver | Route và DNS on-prem phải được thử |
| AKS dùng workload identity | Private Endpoint + private DNS + federated identity/RBAC | Network và identity là hai công việc riêng |
| Nhiều VNets/regions, DR | Private endpoints/resolver/DNS riêng theo topology | Thiết kế DNS/failover/cost và kiểm thử từng region |

### 7.2. Threat model tối thiểu

Những rủi ro:

1. **Internet-exposed data plane:** client có token hợp lệ có thể thử đọc từ mạng ngoài khi public access mở.
2. **Credential compromise:** một principal có quyền quá rộng bị lộ token/key.
3. **DNS misrouting:** workload nghĩ đi private nhưng resolve ra public IP, fail hoặc đi đường không như mong muốn.
4. **Control-plane privilege escalation:** kẻ có quyền đổi RBAC hoặc bật public access có thể thay đổi security posture.
5. **Shared network blast radius:** mọi workload trong VNet có route tới PE nhưng không phải workload nào cũng cần đọc secret.
6. **Secret exfiltration qua logs:** SDK/application logging vô tình ghi `KeyVaultSecret.getValue()`.
7. **Single dependency outage:** DNS resolver, firewall, private endpoint hoặc identity down khiến startup không lấy được secret.

Private Endpoint giúp giảm **bề mặt truy cập mạng**, nhưng vẫn cần least privilege, governance, audit, token lifecycle, hạn chế egress và phân tách môi trường.

### 7.3. Bảo vệ cả thao tác “bật lại public access”

Từ góc nhìn compliance, yêu cầu thường không chỉ “hôm nay vault private”. Cần **Azure Policy** kiểm tra hoặc ngăn cấu hình không phù hợp, phân quyền thay đổi network settings, yêu cầu review/PIM và alert khi `publicNetworkAccess` bị bật lại. Một resource lock có thể ngăn delete/sửa tùy loại lock và ARM operation, nhưng không thay **Policy + IAM** cho mọi thay đổi cấu hình.

## 8. Chuẩn bị trước khi tạo Private Endpoint

Trước khi triển khai, thống nhất topology:

```text
Subscription: non-prod hoặc production đã phê duyệt
Resource group Key Vault: rg-security-...
Resource group network: rg-network-...
Key Vault: kv-orders-...
VNet: vnet-orders-...
Subnet PE: snet-private-endpoints
Private Endpoint: pe-kv-orders-...
Private DNS zone: privatelink.vaultcore.azure.net
Test workload: VM/AKS Pod trong VNet thích hợp
Identity: managed/workload identity được cấp data-plane role
```

### 8.1. Các quyết định bắt buộc

- **Vault đã tồn tại hay tạo mới?** Nếu tồn tại, ai đang đọc secret bằng public access? Cần inventory consumers và migration plan.
- **Key Vault RBAC hay access policy model?** Chọn một model và biết cách cấp quyền.
- **VNet/subnet nào?** Có chính sách subnet, route tables, NSGs, private endpoint network policies?
- **DNS resolver nào?** Azure-provided DNS, custom DNS appliance, Azure DNS Private Resolver hay on-prem forwarder?
- **Mạng hybrid/peered VNets nào?** Những paths nào phải được thử.
- **Rollback thế nào?** Nếu tắt public trước rồi DNS lỗi, ai có quyền khôi phục theo change window?
- **Chủ sở hữu và tags:** network owner, security owner, application owner, run ID, cost center.

### 8.2. Permissions để triển khai

Vai trò tạo **Private Endpoint**, sửa VNet/subnet, tạo private DNS zone/link/zone group, phê duyệt target Key Vault connection và cấp Key Vault RBAC có thể cần **nhiều quyền/scope khác nhau**. Không mặc định một principal có quyền Key Vault Secrets User có thể tạo PE, hay Network Contributor có quyền đọc secret.

### 8.3. Chọn subnet

Subnet private endpoint phải đủ địa chỉ IP và tuân thủ policy; Private Endpoint tiêu thụ private IP và NIC trong VNet. Azure có các tùy chọn **network policies for Private Endpoints** để áp NSG/UDR theo mô hình được hỗ trợ; không tự kết luận “NSG không bao giờ tác động private endpoint” hoặc “mọi UDR tự hoạt động”. Xác minh đúng subnet setting, effective routes, NSG rules và platform behavior.

### 8.4. Định nghĩa kết quả thành công trước thay đổi

Một migration “private-only” đạt yêu cầu khi:

1. Private Endpoint connection **Approved**.
2. Workload trong VNet resolve vault FQDN về đúng **private IP**.
3. Workload gọi HTTPS/TLS port 443 thành công.
4. Identity được cấp data-plane permission và đọc test secret thành công.
5. Một principal có quyền đọc secret nhưng đứng **ngoài network được phép** không thể gọi data plane qua public endpoint.
6. Dashboard/alerts không còn phụ thuộc egress public không được phê duyệt.
7. CI/deployment/rotation/monitoring paths vẫn hoạt động.

## 9. Azure Portal: triển khai Private Endpoint có kiểm soát

Giao diện Portal có thể thay đổi; đây là luồng logic:

1. Mở **Key Vault → Networking** và ghi nhận **public network access, firewall rules, private endpoint connections** hiện tại.
2. Tạo hoặc chọn **Private Endpoint** từ phần Networking/Private endpoint connections hoặc từ Private Link Center.
3. Chọn đúng subscription, resource group, region, VNet, subnet.
4. Chọn target **Microsoft.KeyVault/vaults**, vault đúng và subresource **`vault`**.
5. Cấu hình **Integrate with private DNS zone** là zone `privatelink.vaultcore.azure.net` phù hợp mô hình.
6. Xác minh endpoint và NIC private IP đã tạo; nếu approval thủ công, yêu cầu chủ vault **Approve**.
7. Kiểm tra zone A record và VNet link tới nơi workload phân giải DNS.
8. Từ **VM/Pod/App Service VNet-integrated**, thử resolve FQDN và gọi secret với identity thử nghiệm.
9. **Sau khi private-path test PASS**, mới tắt public network access theo change window.
10. Thử positive + negative tests, ghi lại cấu hình/Azure Activity Log và cập nhật runbook.

**Đừng tắt public access ở bước 1 trước khi có đường truy cập private được kiểm chứng**, nhất là vault đang dùng cho deployment pipeline, startup hoặc certificate rotation. Nếu chính sách bắt buộc private-only ngay từ lúc tạo mới, đặt test workload/management path trước, rồi triển khai vault theo IaC có kiểm tra dependencies.

### 9.1. Private Endpoint approval

Khi private endpoint thuộc bên quản lý khác, kết nối có thể ở trạng thái **Pending** cho đến khi owner vault phê duyệt. Không nhầm PE resource được tạo thành công với service connection đã Approved. Endpoint bị Rejected/Disconnected sẽ không phục vụ data-plane như mong đợi dù DNS/IP còn tồn tại.

### 9.2. DNS zone group

Private DNS Zone Group liên kết PE với một hoặc nhiều private zones được hỗ trợ để quản lý records. Với Key Vault, hãy xác minh record cho đúng **vault alias/private IP** sau khi zone group có hiệu lực. Khi di chuyển PE hoặc thay IP, kiểm tra zone group/records được cập nhật; không giữ stale A record do sửa tay từ lần trước.

## 10. Azure CLI: tạo môi trường Key Vault lab

Ví dụ dưới đây dùng **Bash/Azure Cloud Shell** để tạo tài nguyên trong subscription thử nghiệm. **Không chạy trên production trừ khi có change review**. Các lệnh tạo Azure resources có thể tính phí; phải chọn tên hợp lệ, độc nhất toàn cầu và thay placeholders. **Cloud Shell chỉ là nơi gọi ARM APIs; bước kiểm tra data-plane private phải chạy từ mạng VNet tương ứng.**

### 10.1. Khởi tạo biến và chọn subscription

```bash
az login
az account set --subscription "<non-production-subscription-id>"
az account show --output table

REGION="southeastasia"
RG="rg-kv-private-lab"
VNET="vnet-kv-private-lab"
SUBNET="snet-private-endpoints"
VAULT="<globally-unique-key-vault-name>"
PE="pe-kv-lab"
CONN="conn-kv-lab"
ZONE="privatelink.vaultcore.azure.net"
LINK="link-vnet-kv-lab"
```

Không nhúng các giá trị private keys, secret values hoặc Azure account tokens vào shell command history/CI logs. Dùng các tên khác giữa dev/staging/prod và confirm account/subscription trước mỗi thao tác phá hủy.

### 10.2. Tạo resource group và VNet/subnet

```bash
az group create \
  --name "$RG" \
  --location "$REGION" \
  --tags environment=lab purpose=keyvault-private-endpoint

az network vnet create \
  --resource-group "$RG" \
  --name "$VNET" \
  --location "$REGION" \
  --address-prefixes 10.42.0.0/16 \
  --subnet-name "$SUBNET" \
  --subnet-prefixes 10.42.5.0/24
```

CIDRs trong lab là ví dụ; **không dùng dải trùng VNet/on-prem khi có peering/VPN**. Cấu hình NSG/UDR/private endpoint network policies theo topology thực và không bỏ qua review subnet.

### 10.3. Tạo Key Vault dùng Azure RBAC data plane

```bash
az keyvault create \
  --resource-group "$RG" \
  --name "$VAULT" \
  --location "$REGION" \
  --enable-rbac-authorization true

VAULT_ID=$(az keyvault show \
  --resource-group "$RG" \
  --name "$VAULT" \
  --query id -o tsv)

echo "Target vault resource ID:"
echo "$VAULT_ID"
```

**Lab giữ nguyên cấu hình network ban đầu để thiết lập PE trước**, không suy rằng vault vừa tạo đã private-only. Key Vault mặc định có soft delete; production thường cần purge protection và policy được duyệt. **Purge protection không thể tùy ý tắt khi đã bật và có thể ảnh hưởng cleanup/lifecycle của vault test**: thiết kế retention/cleanup trước khi dùng.

### 10.4. Xác minh Vault ID và config

```bash
az keyvault show \
  --resource-group "$RG" \
  --name "$VAULT" \
  --query "{id:id,publicNetworkAccess:properties.publicNetworkAccess,networkAcls:properties.networkAcls,enableRbacAuthorization:properties.enableRbacAuthorization}" \
  --output json
```

Các field CLI/REST có thể thay đổi theo Azure CLI/API version; nếu trường không hiển thị, kiểm tra `az keyvault show --help` và ARM resource properties thay vì tự suy giá trị. Cần kiểm tra **trạng thái thực tế** trước khi chỉnh network.

## 11. Azure CLI: tạo Private Endpoint cho Key Vault

### 11.1. Tạo PE hướng đến subresource `vault`

```bash
az network private-endpoint create \
  --resource-group "$RG" \
  --name "$PE" \
  --location "$REGION" \
  --vnet-name "$VNET" \
  --subnet "$SUBNET" \
  --private-connection-resource-id "$VAULT_ID" \
  --group-id vault \
  --connection-name "$CONN"
```

Lệnh cần các quyền Network/Key Vault tương ứng. **Tên connection** là đối tượng kết nối PE với vault, không phải secret; không dùng `--group-id managedHSM` cho Key Vault thường.

### 11.2. Kiểm tra trạng thái kết nối

```bash
az network private-endpoint show \
  --resource-group "$RG" \
  --name "$PE" \
  --query "{id:id,connections:privateLinkServiceConnections,manualConnections:manualPrivateLinkServiceConnections}" \
  --output json
```

Đọc các trường `privateLinkServiceConnectionState.status` nếu có. Kỳ vọng **Approved** trước khi bắt đầu DNS/TLS validation. Nếu connection pending do owner khác, yêu cầu approval qua Key Vault → Networking/Private endpoint connections hoặc API quản lý tương ứng; không ép approval khi thiếu quyền.

### 11.3. Kiểm tra private IP

```bash
az network private-endpoint show \
  --resource-group "$RG" \
  --name "$PE" \
  --query "customDnsConfigs" \
  --output json
```

Một số properties chứa `ipAddresses`/FQDN theo API version. Có thể xem **network interface** của PE trong Portal/CLI để đối chiếu IP thực tế. **Không hard-code IP output vào Java SDK** – dùng private DNS.

## 12. Azure CLI: tạo Private DNS zone, VNet link và zone group

### 12.1. Tạo zone và link VNet

```bash
az network private-dns zone create \
  --resource-group "$RG" \
  --name "$ZONE"

VNET_ID=$(az network vnet show \
  --resource-group "$RG" \
  --name "$VNET" \
  --query id -o tsv)

az network private-dns link vnet create \
  --resource-group "$RG" \
  --zone-name "$ZONE" \
  --name "$LINK" \
  --virtual-network "$VNET_ID" \
  --registration-enabled false
```

Private DNS link cho VNet ứng dụng **không nhất thiết tự xuất hiện ở mọi VNet được peer**. Với hub-spoke/custom DNS, xác định đúng DNS query path và tạo các links/forwarding cần thiết.

### 12.2. Tạo DNS zone group cho endpoint

```bash
ZONE_ID=$(az network private-dns zone show \
  --resource-group "$RG" \
  --name "$ZONE" \
  --query id -o tsv)

az network private-endpoint dns-zone-group create \
  --resource-group "$RG" \
  --endpoint-name "$PE" \
  --name "default" \
  --private-dns-zone "$ZONE_ID" \
  --zone-name "keyvault-private-zone"
```

Đây là cú pháp Azure CLI cho **PE DNS zone group** trên phiên bản phù hợp; kiểm tra `--help` nếu API CLI đổi. Zone group nên tự quản lý A records; đừng tạo record thủ công trùng nếu zone group đã đảm nhiệm.

### 12.3. Kiểm tra A record và zone link

```bash
az network private-dns record-set a list \
  --resource-group "$RG" \
  --zone-name "$ZONE" \
  --output table

az network private-dns link vnet list \
  --resource-group "$RG" \
  --zone-name "$ZONE" \
  --output table
```

Thấy A record chưa đủ; còn phải **resolve từ workload** vì custom DNS/NAT/VNet peering/forwarders có thể không dùng zone này. Chỉ sau khi có positive test mới nên tắt public access.

## 13. Chuyển sang “private-only” và cấu hình firewall

Khi PE connection Approved, DNS private resolves đúng và workload đã đọc một test secret với identity được phép, mới chuyển network access theo chính sách:

```bash
az keyvault update \
  --resource-group "$RG" \
  --name "$VAULT" \
  --public-network-access Disabled

az keyvault show \
  --resource-group "$RG" \
  --name "$VAULT" \
  --query "properties.publicNetworkAccess" \
  --output tsv
```

**Không chạy trên vault production trước khi có runbook rollback và danh sách consumers.** Public network disabled hạn chế data plane public route; application phải dùng đường riêng được cho phép. Azure Resource Manager management access vẫn cần bảo vệ bằng IAM/Policy.

### 13.1. Firewall defaultAction Deny khi public access còn Enabled

Nếu chính sách không yêu cầu private-only mà dùng **public endpoint với allowlist**, một mẫu là:

```bash
# Chỉ chọn mô hình này khi public access thực sự được cho phép.
az keyvault update \
  --resource-group "$RG" \
  --name "$VAULT" \
  --public-network-access Enabled \
  --default-action Deny \
  --bypass None

# Trong môi trường được phép, có thể thêm IPv4 public/CIDR
# hoặc VNet service-endpoint rules bằng lệnh tương ứng.
```

Hai mẫu “public allowed by firewall” và “private-only” là **hai modes khác nhau**. Không copy lệnh `Enabled` vào script production private-only để “khắc phục nhanh” mà không có phê duyệt.

### 13.2. IP allowlist là IPv4 public hợp lệ

Network ACL IP rules của Key Vault hướng tới các **public IPv4 ranges được hỗ trợ** và có giới hạn về số rules; không đưa **RFC1918 private IP** của Pod/VM vào IP allowlist và kỳ vọng thay được Private Endpoint. Với client sau NAT/firewall, phải xác định **egress public IP thực** nếu chọn public allowlist. Nếu egress thay đổi, rule dễ trở nên stale.

### 13.3. Service endpoints chỉ là một lựa chọn khác

Để dùng **Microsoft.KeyVault service endpoint**, cần bật service endpoint trên subnet và thêm **VNet rule** vào Key Vault network ACL khi chế độ firewall áp dụng. Không nhầm đây là bước tạo Private Endpoint hoặc cho rằng service endpoint tự động tạo A record private.

### 13.4. Trusted Microsoft services bypass

Tùy mode mạng, Key Vault có setting `bypass AzureServices` cho một tập **trusted Microsoft services** được Microsoft định nghĩa; **không phải mọi Azure service** (bao gồm mọi App Service/AKS/CI runner) đều nằm trong danh sách. Không cho rằng Azure DevOps hosted agent hoặc Cloud Shell luôn được miễn firewall. Khi **public network access Disabled**, cần kiểm tra các ngoại lệ được nền tảng hỗ trợ và **không xây phụ thuộc vào một bypass công khai không được xác minh**.

### 13.5. Quy trình không tự khóa mình

Trước cutover cần có:

- Một **bastion/test VM hoặc workload trong VNet** đã xác minh DNS/route/TLS/RBAC.
- Một account/principal quản trị qua ARM được phê duyệt để xử lý rollback.
- Monitoring và secret rotation systems đã đi qua private path.
- CI/CD runner có VNet access hoặc một deployment workflow được thiết kế riêng.
- Change window, validation script và decision maker rõ ràng.

Sau cutover, thử cả **positive request** (trong VNet với right identity) và **negative request** (ngoài mạng nhưng identity có secret read permission). Negative test mới chứng minh firewall chặn ngay cả khi token đủ quyền.

## 14. Microsoft Entra ID và Key Vault authorization

Key Vault nhận **Microsoft Entra access token** theo identity của workload/service. Khi ứng dụng chạy trên AKS, App Service, VM, Azure Functions hoặc CI, nên ưu tiên **managed identity/workload identity** khi môi trường và SDK hỗ trợ. Không cần nhúng vault access key hay client secret dài hạn vào source code.

### 14.1. Hai mô hình data-plane permission

| Mô hình | Cách cấp quyền | Lưu ý |
|---|---|---|
| **Azure RBAC authorization** | Gán built-in/custom data-plane roles ở scope thích hợp | Quản lý tập trung bằng Azure RBAC, role propagation có thể trễ |
| **Vault access policies** | Cấp permissions cho principal trực tiếp trên Key Vault theo legacy model | Governance khác, tránh quyền ARM cho phép tự nâng access policy |

Mỗi vault sử dụng **mô hình permission được cấu hình**. Nếu `enableRbacAuthorization=true`, không kỳ vọng một `access policy get` legacy là bằng chứng hiệu lực cho request. Việc đổi giữa hai mô hình trên production có thể ngắt các ứng dụng đang chạy; phải audit quyền trước, lên kế hoạch chuyển đổi và dùng IaC/change control.

### 14.2. Vai trò built-in phổ biến

| Role | Dùng cho | Không nên suy |
|---|---|---|
| **Key Vault Secrets User** | Workload cần đọc giá trị secret theo scope | Không có toàn quyền quản trị vault |
| **Key Vault Secrets Officer** | Quản lý secret data plane (thêm/sửa/xóa) | Không mặc định cần cho app chỉ đọc |
| **Key Vault Crypto User** | Thao tác mật mã với keys theo role definitions | Không mặc định được đọc mọi secret |
| **Key Vault Certificates Officer** | Quản lý certificates theo quyền được định nghĩa | Không đồng nghĩa mọi thao tác lấy private certificate bytes đều được |
| **Key Vault Reader** | Đọc thông tin/metadata theo role | Không cấp quyền xem giá trị secret |
| **Key Vault Administrator** | Quản lý data plane rộng | Không trao cho workload thông thường |

Role definitions và quyền cụ thể có thể thay đổi hoặc có custom roles. Đừng suy role chỉ từ tên; xác minh **dataActions** và kiểm tra positive/negative tests trên vault test.

### 14.3. Gán quyền đọc secret cho workload

```bash
# Object ID của managed identity / service principal thử nghiệm.
# Không dùng user email khi script cần chính xác principal object.
PRINCIPAL_OBJECT_ID="<test-workload-principal-object-id>"

az role assignment create \
  --assignee-object-id "$PRINCIPAL_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$VAULT_ID"
```

**Role assignment không thay private DNS hay network firewall.** Nó chỉ đáp ứng authorization cho principal. Nếu assignment mới chưa có hiệu lực do propagation/cache, chờ có deadline và quan sát lỗi; đừng cấp thêm `Owner` hay `Key Vault Administrator` để vượt lỗi 403.

### 14.4. Least privilege ở mức vault hay secret?

Có thể cấp role ở scope vault hoặc các child-resource scope được hỗ trợ. Hãy chọn scope **nhỏ nhất phù hợp** nhưng vẫn dễ vận hành. Với vài ứng dụng có secrets độc lập và nhu cầu boundary nghiêm ngặt, cân nhắc **vault riêng cho từng ứng dụng/environment** thay vì nhồi mọi secret vào một vault rồi cấp broad role. Phân tách mạng, identity, lifecycle và audit có thể quan trọng hơn chỉ tổ chức tên secrets.

### 14.5. Managed Identity không tự làm phép màu

Ứng dụng phải nhận token từ đúng identity. Với **system-assigned managed identity**, identity gắn resource lifecycle; với **user-assigned managed identity**, cần cấu hình client ID/assignment theo runtime. Trên AKS Workload Identity, còn có federated credential và Kubernetes service account. Một pod có identity token hợp lệ nhưng **chưa được cấp role trên đúng Key Vault** vẫn thất bại.

## 15. Kiểm tra đường private bằng DNS, TCP và HTTPS

Thứ tự điều tra hiệu quả nhất là **DNS → route/connectivity → TLS → token → Key Vault authorization**. Không bắt đầu bằng đổi RBAC khi DNS vẫn trỏ public IP.

### 15.1. Lệnh cơ bản từ Linux container/VM trong VNet

```bash
VAULT="<globally-unique-key-vault-name>"
FQDN="$VAULT.vault.azure.net"

# Nếu image có dnsutils/bind-tools:
nslookup "$FQDN"

# Hoặc kiểm tra resolver hệ điều hành:
getent hosts "$FQDN"

# Kiểm tra TLS/HTTP, không gửi bearer token/secret vào output:
curl --connect-timeout 5 --max-time 15 -v \
  "https://$FQDN/" \
  -o /dev/null
```

Một HTTP `401`, `403` hoặc `404` ở root path vẫn có thể chứng tỏ DNS/TCP/TLS tới một HTTP endpoint đã hoạt động; nó **không chứng minh secret GET authorized**. Với đường TLS, kiểm tra hostname/certificate chain, connection target và không log credentials.

### 15.2. PowerShell từ test VM/Windows

```powershell
$vault = "<globally-unique-key-vault-name>"
$hostName = "$vault.vault.azure.net"

Resolve-DnsName -Name $hostName
Test-NetConnection -ComputerName $hostName -Port 443
```

Đọc `RemoteAddress` trong TCP test: kỳ vọng **private endpoint IP** với workload private-only. Nhưng nếu có proxy HTTP/TLS bắt buộc, OS/browser/curl và Java có thể đi qua proxy khác nhau; kiểm tra đường kết nối của **process ứng dụng thật**.

### 15.3. Kiểm tra DNS theo từng điểm

| Điểm thử | Kỳ vọng khi private DNS đúng | Nếu sai |
|---|---|---|
| VM cùng VNet với PE | FQDN phân giải về private IP | Zone link/record/resolver |
| AKS Pod | FQDN → private IP theo CoreDNS/forwarding | CoreDNS stub domains, custom DNS |
| App Service VNet-integrated | FQDN → private IP, outbound tới PE | VNet integration và DNS/routing |
| On-prem qua VPN | FQDN → private IP, route private qua VPN | DNS forwarder/Private Resolver, routing |
| Laptop ngoài VPN | Có thể thấy public endpoint hoặc không route private | Kỳ vọng không gọi được data plane nếu public disabled |

Không dùng `ping` ICMP như điều kiện duy nhất: nhiều managed service endpoints không trả ping, còn HTTPS 443 mới là giao thức liên quan.

### 15.4. DNS cache trong JVM và containers

Sau cutover, OS/CoreDNS/JVM hoặc HTTP client connection pool có thể giữ DNS/connection cũ trong một khoảng thời gian. Đánh giá TTL/resolver policy, restart ứng dụng **có kiểm soát** nếu cần, không tắt DNS cache toàn hệ thống hoặc rollout restart toàn bộ production pods ngay lập tức. Cần đo downtime và connection churn.

## 16. Kiểm thử Key Vault data plane thực sự

Một DNS test không xác minh token/RBAC. Sau khi `nslookup` trả private IP:

```bash
# Chạy ở VM/Pod/runner trong VNet và login bằng identity có quyền.
az keyvault secret show \
  --vault-name "$VAULT" \
  --name "orders-db-password" \
  --query id \
  --output tsv
```

Lệnh `secret show` **thực sự gọi data plane** và đọc metadata/secret response; query `id` giới hạn output để tránh in secret value ra terminal. Chỉ thực hiện khi identity được cấp role và secret đã tồn tại. Đừng dùng secret production cho lab; tạo fixture **synthetic**, an toàn.

### 16.1. Phân biệt test roles và network

Thiết kế ma trận:

| Địa điểm/identity | Kết nối DNS/route | Data-plane role | Kỳ vọng |
|---|---|---|---|
| VM VNet + test reader | Private IP reachable | Secrets User | **Allow** |
| VM VNet + no-role identity | Private IP reachable | Không có | **Deny authorization** |
| Laptop outside VNet + reader | Public path (private-only vault) | Secrets User | **Deny network** |
| VM VNet + wrong tenant token | Private IP reachable | Không hợp lệ | **Deny auth** |
| App Service thiếu VNet integration + reader | Không có private path | Secrets User | **Deny network/connection** |
| Admin qua ARM bên ngoài VNet | ARM API được kiểm soát riêng | ARM permission | Có thể quản lý cấu hình tùy IAM/Policy |

**Negative test mạng nên dùng principal đã có quyền read trong một vault test**; nếu cũng thiếu role, 403 không phân biệt firewall đúng hay không. Không chuyển token/secret thật giữa máy không tin cậy để chạy test này; có thể tạo test identities độc lập và dùng môi trường được kiểm soát.

### 16.2. Test không tiết lộ secret

Một test nên assert **giá trị fixture đã biết** trong bộ nhớ hoặc dùng length/checksum, nhưng **không log raw secret**. CI artifacts có thể bị nhiều người đọc; đừng in JSON của `az keyvault secret show` mặc định vì nó có thể chứa value. Trong production, lấy secret theo id có thể bị ghi vào tracing; cần redact.

### 16.3. Nếu secret chưa tồn tại

`404 SecretNotFound` khi mạng/auth đã hoạt động là một tín hiệu **khác** `403 ForbiddenByFirewall`. Không tạo secret mới bằng quyền Officer chỉ để biến một test read thành pass nếu mục tiêu là xác minh least privilege. Tách **fixture setup identity** (có quyền write) khỏi **application read identity** (chỉ get).

## 17. Java Azure SDK: đọc secret qua Private Endpoint

Với **Azure SDK for Java**, một client đọc secret sử dụng **`SecretClient`** từ thư viện `azure-security-keyvault-secrets` và một `TokenCredential` từ `azure-identity`. URL trong SDK **vẫn là tên vault public FQDN**, DNS của runtime quyết định private route.

### 17.1. Maven dependencies

```xml
<!-- POM fragment; khai báo phiên bản BOM phù hợp dự án. -->
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-sdk-bom</artifactId>
      <version>${azure.sdk.bom.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-security-keyvault-secrets</artifactId>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
  </dependency>
</dependencies>
```

`${azure.sdk.bom.version}` là **Maven property cần khai báo**, không phải một version đã được xác nhận. Pin Azure SDK BOM theo dependency management, kiểm tra runtime/JDK compatibility và release notes trước khi nâng.

### 17.2. Java code đọc secret

```java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

import java.net.URI;
import java.util.Objects;

public final class KeyVaultSecretReader {
    public static void main(String[] args) {
        String vaultUrl = Objects.requireNonNull(
                System.getenv("AZURE_KEY_VAULT_URL"),
                "AZURE_KEY_VAULT_URL is required");

        // Giữ https://<vault>.vault.azure.net; không dùng IP PE.
        URI uri = URI.create(vaultUrl);
        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || !uri.getHost().endsWith(".vault.azure.net")) {
            throw new IllegalArgumentException("Unexpected vault URL");
        }

        SecretClient client = new SecretClientBuilder()
                .vaultUrl(vaultUrl)
                .credential(new DefaultAzureCredentialBuilder().build())
                .buildClient();

        KeyVaultSecret secret = client.getSecret("orders-db-password");

        // Chỉ dùng secret value trong memory cho mục đích ứng dụng.
        String value = secret.getValue();
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Secret value is missing");
        }
        System.out.println("Secret retrieved successfully");
        // Tuyệt đối không print(value), không ghi vào trace/log/metric.
    }
}
```

Đây là **chương trình minh họa**. Việc kiểm tra suffix hostname chỉ là guard chống nhầm dạng URL, **chưa phải vault allowlist hay chống mọi loại host abuse**: production cần validate **exact expected vault resource/FQDN** từ cấu hình tin cậy. SDK không cần nhận private endpoint IP hay private DNS zone name trực tiếp.

### 17.3. Local developer và Azure identity có thể khác nhau

`DefaultAzureCredential` là một chuỗi credential providers. Trên developer laptop, nó có thể lấy credential từ Azure CLI/IDE/environment; trên AKS/App Service/VM, nó có thể sử dụng workload/managed identity theo cấu hình được hỗ trợ. **Một lần chạy thành công ở laptop không xác minh identity và network trong pod production**. Trên môi trường yêu cầu identity chính xác, cấu hình credential provider/client ID rõ ràng, kiểm tra principal/tenant/scope không bí mật.

### 17.4. Kết nối SDK với network

Nếu code này chạy trong AKS Pod, nó có thể:

1. Resolve vault FQDN qua CoreDNS đến PE private IP.
2. Mở TLS 443 với hostname hợp lệ.
3. Lấy Microsoft Entra token theo workload identity.
4. Gửi `GET secret` kèm bearer token đến vault.
5. Bị trả `403` nếu thiếu data-plane role dù DNS đúng.

Chính vì các bước độc lập, Java exception cần được phân loại; **không** bắt mọi lỗi rồi “thử lại với public endpoint”.

## 18. Xử lý lỗi SDK Java không làm lộ secret

Trong ứng dụng thật, nên phân biệt:

| Lỗi | Khả năng | Hướng xử lý |
|---|---|---|
| `UnknownHostException` | DNS không resolve | Kiểm tra private DNS zone/link/CoreDNS |
| `ConnectTimeoutException` | Route/NSG/firewall/PE chưa reachable | Kiểm tra TCP 443 từ runtime |
| `SSLHandshakeException` | Truststore/hostname/proxy TLS | Không tắt certificate verification |
| `ClientAuthenticationException` | Không lấy token/hết hạn/tenant sai | Kiểm tra managed identity/federation |
| `403 ForbiddenByFirewall` | Network ACL/public-disabled/không qua PE | Kiểm tra private route, không tự cấp role rộng |
| `403 Forbidden/AccessDenied` | RBAC/access policy không đủ | Kiểm tra principal, dataActions, propagation |
| `404 SecretNotFound` | Tên/version/đích vault sai hoặc secret chưa có | Kiểm tra fixture/version/soft-delete |
| `429 TooManyRequests` | Throttling | SDK backoff/retry có giới hạn, caching |
| `5xx/transient` | Service/network tạm lỗi | Bounded retry, circuit breaker theo nhu cầu |

Tên exception và các mã error cụ thể thay đổi theo Azure SDK/version và service response. **Một `403` không đủ để kết luận mạng hay IAM**; phải đọc **sanitized error code/inner status** và kiểm tra riêng DNS/IP/identity.

### 18.1. Java snippet phân loại HTTP errors

```java
import com.azure.core.exception.HttpResponseException;
import com.azure.core.exception.ResourceNotFoundException;
import com.azure.identity.CredentialUnavailableException;
import com.azure.core.exception.ClientAuthenticationException;

try {
    var secret = client.getSecret("orders-db-password");
    // Dùng secret.getValue() trong luồng nghiệp vụ được phép, không log.
} catch (ResourceNotFoundException ex) {
    System.err.println("Requested secret does not exist");
} catch (ClientAuthenticationException ex) {
    System.err.println("Entra credential authentication failed");
} catch (CredentialUnavailableException ex) {
    System.err.println("No supported credential available");
} catch (HttpResponseException ex) {
    int status = ex.getResponse().getStatusCode();
    System.err.println("Key Vault HTTP status=" + status);
    // Không log full response body nếu có nguy cơ lộ secret/PII.
    throw ex;
}
```

Đây là **snippet trong method**, `client` được tạo từ phần 17. Cấu trúc exception hierarchy/các specialized exceptions phải đối chiếu SDK version và thứ tự catch tương thích Java compiler. Azure SDK có thể wrap network exceptions; ứng dụng nên dùng **structured error classification** có tests thay vì parse tùy tiện chuỗi message.

### 18.2. Retry không sửa DNS hay RBAC sai

Nếu vault trả 403 đều do network deny, retry 100 lần chỉ tăng tải. Nếu DNS trỏ public IP, một retry SDK cũng không tự tạo private zone link. **Phân loại permanent configuration errors** và transient 429/5xx; dùng backoff, hạn mức và theo dõi retry count. Đừng fallback sang public network để “tự chữa” lỗi private connection.

### 18.3. Cache secret và rotation

Một secret read có thể thành công rồi được cache trong JVM. Khi rotation, workload cần refresh theo TTL/version policy; khi vault tạm unreachable có thể cần chính sách **stale credential** trong thời gian giới hạn, được security owner chấp thuận. Không kéo dài cache vô hạn hoặc lưu plaintext secret trong disk/log để tránh phụ thuộc Key Vault.

## 19. AKS Workload Identity + Key Vault Private Endpoint

Một thiết kế production phổ biến:

```text
AKS namespace: orders-prod
       |
Kubernetes ServiceAccount (workload identity annotation)
       |
Pod with projected service account token
       |
       +--> Microsoft Entra token exchange
       |    (federated identity credential)
       |
       +--> Azure DNS / CoreDNS -> PE private IP
       |
       v
Key Vault SecretClient.getSecret()
       |
       +--> Data plane authorization: Key Vault Secrets User
       |
       v
Application receives secret over HTTPS/TLS
```

### 19.1. Những điều kiện cần đủ

| Thành phần | Phải xác minh |
|---|---|
| AKS/OIDC issuer | Workload Identity được bật/cấu hình đúng |
| Federated credential | Issuer, subject, audience khớp service account và identity |
| Workload Pod | ServiceAccount/labels/env theo integration SDK được hỗ trợ |
| Identity | Azure client ID/tenant và đúng principal |
| Key Vault | RBAC model + dataActions đúng và scope phù hợp |
| VNet | Route từ Pod/node tới Private Endpoint |
| DNS | FQDN vault từ Pod resolve về private IP |
| Policy | Network/identity/tenant boundaries và logs an toàn |

**Một Pod được gắn Kubernetes ServiceAccount không tự nhận quyền Key Vault.** Federated identity và data-plane RBAC phải được cấu hình riêng.

### 19.2. Probe ở trong Pod, không chỉ từ jumpbox

Một jumpbox trong VNet có thể resolve DNS đúng, nhưng CoreDNS trong AKS dùng custom forwarder khác. Kiểm tra bằng một **ephemeral debug Pod** trong namespace/network policy phù hợp, hoặc qua application telemetry được kiểm soát. Không mount production service account token vào Pod debug không tin cậy.

### 19.3. Azure Key Vault Secrets Store CSI Driver

Trên AKS, **Secrets Store CSI Driver + Azure provider** có thể mount/đồng bộ secret vào Pod theo tính năng được hỗ trợ, dùng workload/managed identity. Khi đó:

- Network path **từ node/provider component** tới private endpoint phải hoạt động.
- Identity được provider sử dụng phải có quyền get/list tương ứng.
- Secret được mount vào Pod có lifecycle/permissions/rotation semantics riêng.
- Một số cấu hình có thể sync thành Kubernetes Secret, từ đó kéo theo **quyền RBAC trên Kubernetes, etcd encryption và trách nhiệm xóa/rotation**.

Không giả định một secret mount được refresh tức thời chỉ vì Key Vault value đã rotate. Phải kiểm tra **refresh interval, app reload behavior và lỗi mount/update** theo CSI driver/provider version.

### 19.4. Split-horizon DNS trong nhiều clusters

Nếu cluster A và B ở hai VNets khác nhau cùng dùng một vault, Private Endpoints có thể khác IP. Thiết kế **DNS zone linking/resolution scopes** theo cluster/vùng; không tạo một record cố định áp mọi môi trường. Chạy positive/negative tests từ **mỗi cluster** sau khi thay DNS.

## 20. App Service và Azure Functions Key Vault references

App Service/Functions có khả năng **Key Vault references** trong application settings theo hỗ trợ plan/runtime. Reference trỏ tới secret ID/URI thay vì nhúng value trong cấu hình; nền tảng sẽ giải quyết reference bằng identity được cấu hình.

### 20.1. Một ví dụ reference trong app setting

```text
DB_PASSWORD=@Microsoft.KeyVault(SecretUri=https://kv-orders-prod.vault.azure.net/secrets/orders-db-password/)
```

Đây là syntax minh họa cho **Key Vault reference** của App Service/Functions – không phải một cú pháp Java property chung. Chọn URI/version, refresh và cache behavior theo platform documentation đang sử dụng.

### 20.2. Tại sao reference có thể fail khi vault private-only?

Khi App Service chưa có outbound VNet Integration hoặc DNS không đưa hostname vault về private endpoint, nền tảng không lấy được secret. Dù app có managed identity và Key Vault role đúng, response có thể bị firewall chặn. Kiểm tra:

1. App Service plan hỗ trợ VNet Integration cho outbound.
2. VNet/subnet integration của app và route đến PE.
3. Private DNS zone/link và custom DNS settings.
4. Key Vault reference identity (system-assigned/user-assigned theo cấu hình).
5. RBAC/data-plane permission và secret/version có tồn tại.
6. Platform reference refresh/cache và application restart behavior.

### 20.3. Inbound PE của App Service là một câu chuyện khác

Một private endpoint **để gọi vào App Service** bảo vệ inbound HTTP traffic tới app. Nó **không tự thay thế** outbound VNet Integration cần để app đọc Key Vault. Hai đường mạng phải được thiết kế riêng:

```text
Client -> App Service private inbound endpoint
                    |
             App Service runtime
                    |
          outbound VNet Integration
                    |
          Key Vault private endpoint
```

### 20.4. Deployment slots và môi trường

Staging slot có thể sử dụng identity, app settings, Key Vault references và VNet setup khác production slot. Khi swap, kiểm tra **slot-specific settings/identity/config** để không vô tình khiến staging đọc secret production hoặc application switchover mất secret. Không dùng chung vault secret giá trị production cho dev test chỉ vì URI dễ tái sử dụng.

## 21. Azure DevOps/GitHub Actions và đường mạng deployment

CI có thể cần truy cập Key Vault để lấy secret, certificate hoặc deploy app. **Hosted runners không mặc định nằm trong VNet của bạn**. Nếu vault private-only, một pipeline chạy từ môi trường không có private connectivity có thể nhận `ForbiddenByFirewall` dù OIDC/service principal có quyền.

### 21.1. Các phương án

| CI executor | Private Key Vault access | Lưu ý |
|---|---|---|
| Hosted runner công khai mặc định | Thường không có path PE trực tiếp | Không dựa vào IP public allowlist khi vault private-only |
| Self-hosted runner trong VNet | Có thể qua PE | Bảo vệ runner, DNS, identity, egress |
| Managed runner có private-network integration nếu được hỗ trợ | Có thể | Xác minh service/plan/feature và routing |
| Job chạy trong AKS/private VM | Có thể | Least privilege cho service account/managed identity |
| Cloud Shell thông thường | Không phải chứng minh private path | Dùng ARM operations nhưng data-plane có thể bị chặn |

### 21.2. Tách deploy configuration và secret retrieval

Một pipeline deploy resource qua **ARM** không nhất thiết cần đọc secret value; nếu app có **managed identity** và Key Vault reference/SDK, có thể chỉ cấp pipeline quyền cập nhật infra mà không cấp secret read. Giảm số principals cần vào private data-plane network. Chỉ pipeline thực sự cần xuất/chèn secret mới yêu cầu data-plane access, được phê duyệt riêng.

### 21.3. OIDC federation là bảo mật danh tính, không phải VNet

OIDC-based CI credential giúp giảm client secrets dài hạn, nhưng **không mở đường mạng** đến PE. Một pipeline có token đúng vẫn fail nếu DNS/network path sai. Cần thiết kế hai lớp độc lập và test riêng.

## 22. Kiểm soát firewall, NSG và route tới Private Endpoint

Private Endpoint gắn một private IP vào VNet. Các NSG/UDR/network appliance có thể tham gia đường đi theo network policy và topology. Với subnet chứa PE hoặc subnet nguồn, cần biết **effective routes**, VNet peering, firewall inspection và policy cụ thể.

### 22.1. Kiểm tra route và ACL

Khi TCP 443 timeout nhưng DNS đúng:

1. Xem **PE connection Approved** và NIC private IP.
2. Kiểm tra source IP/subnet của workload.
3. Kiểm tra **route table/UDR**, firewall/NVA và return path.
4. Kiểm tra **NSG rules** ở những subnet/NIC có tác dụng theo thiết lập network policies.
5. Kiểm tra peering/VPN nếu cross-VNet/on-prem.
6. Kiểm tra outbound proxy; một HTTP proxy có thể đưa request sang internet thay vì PE.
7. Xác minh không có IP overlap với on-prem/VNets.
8. Tách lỗi DNS (wrong IP) khỏi lỗi network (right IP nhưng không connect).

### 22.2. Không mở mọi đường vì test fail

Một cách sửa nguy hiểm là bỏ toàn bộ NSG/firewall rules hoặc bật public network access để “hết 403”. Điều đó có thể vi phạm compliance và che nguyên nhân. Thay vào đó, mở **đường kết nối tối thiểu** đúng source, destination private IP, port 443, route và identity.

### 22.3. Nguồn từ nhiều khu vực

Một PE trong VNet ở region A có thể được gọi từ VNet B qua kết nối phù hợp, nhưng latency, network cost và failure domains khác. Với DR, cân nhắc private endpoint/DNS/topology tại region dự phòng và kiểm thử cả failover. **Key Vault DNS không tự định tuyến workload đến “private endpoint gần nhất” chỉ vì bạn tạo nhiều PE.**

## 23. Public firewall IP rules và service endpoint: ví dụ và bẫy

### 23.1. IP rule minh họa

Nếu được phép public endpoint với firewall:

```bash
# Ví dụ chỉ cho public IPv4 egress cố định của một test runner.
# Thay bằng IP/CIDR được đội network xác minh.
az keyvault network-rule add \
  --resource-group "$RG" \
  --name "$VAULT" \
  --ip-address "<approved-public-ipv4-or-cidr>"
```

Không nhập private IP thuộc `10.0.0.0/8`, `172.16.0.0/12` hay `192.168.0.0/16` vào đây; Azure Key Vault firewall rules được thiết kế cho public IPv4 addresses/ranges. Nếu client có NAT, dùng **địa chỉ public egress thực**, không phải private source IP.

### 23.2. Service endpoint trên subnet

Một mẫu khái niệm:

```bash
# Chỉ khi dùng mô hình service endpoint/firewall (không phải PE-only).
az network vnet subnet update \
  --resource-group "$RG" \
  --vnet-name "$VNET" \
  --name "<application-subnet>" \
  --service-endpoints Microsoft.KeyVault

APP_SUBNET_ID="<full-application-subnet-resource-id>"
az keyvault network-rule add \
  --resource-group "$RG" \
  --name "$VAULT" \
  --subnet "$APP_SUBNET_ID"
```

Giá trị `--subnet` là **ARM resource ID**, lấy từ `az network vnet subnet show --query id` sau khi thay tên subnet thực. Service endpoint trên **application subnet** khác việc tạo **Private Endpoint** trên subnet của nó; trong mô hình private-only, hãy sử dụng PE path được phê duyệt thay vì xem service endpoint là đường cứu hộ tùy ý.

### 23.3. Bypass trusted services không phải cloud service allow-all

Nếu chính sách yêu cầu hạn chế public traffic, chỉ dùng bypass danh sách trusted services khi **đúng tính năng/permission**. Một app chạy trong Azure VM hoặc third-party SaaS chưa chắc thuộc danh sách trusted services; nhà cung cấp thay đổi danh sách theo service. Kiểm tra tài liệu chính thức cho từng integration khi thiết kế, tránh phụ thuộc bypass mà không test.

### 23.4. Azure Network Security Perimeter (nếu có)

Một số tài nguyên Azure hỗ trợ mô hình **Network Security Perimeter (NSP)** theo tính năng/region/tier. NSP không phải tên khác của Private Endpoint, và tương tác giữa public network access, private endpoints và perimeter rules cần đánh giá riêng. Bài học tập trung vào **Key Vault firewall và Private Link**; đừng copy hướng dẫn NSP của một service khác nếu API/config không tương thích.

## 24. Giữ secret được bảo vệ khi vận hành

Không có mạng riêng nào giúp được nếu chính application gửi giá trị secret vào logs, traces hoặc public error responses.

### 24.1. Không log giá trị

Anti-pattern:

```java
var secret = client.getSecret("orders-db-password");
System.out.println("DB password: " + secret.getValue()); // KHÔNG làm
```

Thay bằng:

```java
var secret = client.getSecret("orders-db-password");
System.out.println("Key Vault secret retrieved; name=" + secret.getName());
// Chỉ truyền value tới thành phần được phép trong memory.
```

Ngay cả tên secret có thể tiết lộ nội dung vận hành; log có classification/retention và kiểm soát người đọc. Không đẩy full exception bodies, tokens hoặc authorization headers vào log công khai.

### 24.2. Quyền tối thiểu theo workload

Một web API chỉ cần get `orders-db-password` không cần quyền `set/delete/purge` toàn vault. Một certificate rotation service có scope/role khác; đừng dùng shared identity giữa deployment pipeline, Java API và security administrators.

### 24.3. Bảo vệ control-plane changes

Với yêu cầu private-only:

- Azure Policy audit/deny vault cấu hình public access không phù hợp.
- PIM/approvals cho người có quyền sửa network/RBAC.
- Azure Activity Log theo dõi `Microsoft.KeyVault/vaults/write`, role assignments và private endpoint changes.
- Không cho CI thông thường sửa `publicNetworkAccess` nếu không cần.
- Deploy configuration bằng IaC, review diff và drift detection.

### 24.4. Rotation và private access

Một secret rotation workflow có thể chạy từ Azure Automation/Functions/Logic Apps hoặc một service khác. Nếu vault private-only, workflow phải có **đường mạng riêng hợp lệ hoặc integration được chính thức hỗ trợ**, cộng quyền data plane để cập nhật secret. Không mặc định “Azure-managed service” luôn bypass network. Khi network bị thay, kiểm thử cả **quy trình rotate**, không chỉ app read.

### 24.5. Không để backup hoặc test mở lỗ hổng

Một script backup secrets/keys có thể chạy từ laptop/CI ngoài VNet và fail sau private cutover. Đừng bật public access tạm thời trong cron job mà không audit. Di chuyển backup/restore operations sang VNet-connected runner, hoặc thiết kế phương án quản lý backup hợp lệ với policy. Lưu ý một số Key Vault backup/restore operations có **region/subscription/permission limitations** và dữ liệu backup cũng là sensitive artifact.

## 25. Azure Monitor: audit mạng, quyền và hành vi Key Vault

Key Vault production cần theo dõi **dữ liệu truy cập (data plane), thay đổi cấu hình (control plane), kết nối mạng và ứng dụng tiêu thụ**. Một số chỉ số đến từ Azure Monitor/Activity Log, một số phải được ứng dụng tự instrument.

### 25.1. Phân loại nguồn giám sát

| Nguồn | Ví dụ thông tin | Không đủ để chứng minh |
|---|---|---|
| **Key Vault platform metrics** | API latency, availability/request activity/throttling theo metric được hỗ trợ | Không tự cho biết app dùng secret đúng nghiệp vụ |
| **Key Vault diagnostic logs** | Audit operation, kết quả/identity metadata trong categories được bật | Không lưu mọi logic decision của Java app |
| **Azure Activity Log** | Thay đổi vault resource/network/RBAC/PE qua management operations | Không thay thế toàn bộ data-plane audit |
| **Private Endpoint/network diagnostics** | Connection state, IP, network reachability | Không chứng minh RBAC Secrets User |
| **DNS/VM/AKS/App Service telemetry** | Resolver responses, TLS/connection latency/errors | Không chứng minh secret tồn tại |
| **Application metrics** | Secret fetch success, 403/429, cache age, rotation refresh | Không nên chứa giá trị secret |

### 25.2. Khám phá metric definitions thay vì đoán

```bash
az monitor metrics list-definitions \
  --resource "$VAULT_ID" \
  --output table

az monitor diagnostic-settings categories list \
  --resource "$VAULT_ID" \
  --output table

az monitor diagnostic-settings list \
  --resource "$VAULT_ID" \
  --output json
```

Tên metrics, log categories và Log Analytics tables phụ thuộc cấu hình/phiên bản dịch vụ. **Không viết KQL dựa trên một table chưa tồn tại rồi kết luận không có audit log**. Diagnostic settings phải được cấu hình đến đích Log Analytics/Storage/Event Hubs đúng quyền.

### 25.3. Diagnostic settings mẫu

Khi resource xác nhận category `AuditEvent` có sẵn, một lệnh mẫu:

```bash
LAW_ID="<approved-log-analytics-workspace-resource-id>"

az monitor diagnostic-settings create \
  --name "diag-kv-audit" \
  --resource "$VAULT_ID" \
  --workspace "$LAW_ID" \
  --logs '[{"category":"AuditEvent","enabled":true}]'
```

Ví dụ cần kiểm tra **category compatibility, destination/log table mode, retention và chi phí ingest** trước khi chạy. Không dùng Log Analytics workspace public/shared không được phép vì audit có thể chứa caller identities, network metadata và tên secrets. Lệnh cấu hình diagnostics cần control-plane permissions riêng.

### 25.4. KQL minh họa

Trong workspace **đã dùng AzureDiagnostics legacy table** và thực sự có Key Vault audit logs:

```kusto
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where ResourceProvider =~ "MICROSOFT.KEYVAULT"
| where Category == "AuditEvent"
| summarize Events=count() by ResultType, OperationName
| order by Events desc
```

Đây là **mẫu tùy table schema**, không phải bảo đảm Log Analytics luôn dùng `AzureDiagnostics` hoặc có đúng `ResultType`/`OperationName`. Với resource-specific tables, cần truy vấn đúng table/cột thực tế được xuất theo cấu hình. **Không tạo alert security trên query chưa thử với dữ liệu thật.**

### 25.5. Những alerts nên có

1. **Data-plane forbidden rate** tăng bất thường sau đổi DNS/RBAC.
2. **Throttling/429** hoặc service latency tăng làm ứng dụng không lấy được secret.
3. **Private Endpoint connection** chuyển Pending/Rejected/Disconnected.
4. **Public network access** bị bật lại hoặc firewall rule thay đổi trái policy.
5. **Role assignments/data-plane access policy** thay đổi không có change ticket.
6. **Ứng dụng secret-fetch failure** hoặc cache quá hạn rotation.
7. **DNS resolution không ra private IP** theo synthetic probe trong workload network.
8. **Certificate/secret expiry** sắp tới và rotation job failure.

Một alert chỉ dựa trên “403 > 0” có thể gây noise từ các **negative security tests hợp lệ**. Dùng threshold/cửa sổ, principal/source environment và tag planned test; nhưng không bỏ qua mọi 403 vì có thể che exfiltration attempts.

### 25.6. Không log secret value trong synthetic probe

Synthetic monitoring có thể gọi `getSecret("health-test")` bằng một identity chỉ đọc fixture secret riêng. Assertion nên dựa trên **success/status/version** chứ không đưa value vào logs. Nếu value bị rotatable, test phải cập nhật expected logic đúng cách; không dùng production database password làm health probe.

## 26. Đánh giá chính sách bằng positive và negative tests

Một vault được gọi là **private-only** khi có bằng chứng **cho phép đúng người ở đúng mạng**, đồng thời **chặn được đường sai**.

### 26.1. Ma trận nghiệm thu

| Test | DNS | Identity | Kỳ vọng |
|---|---|---|---|
| Workload trong VNet, reader đúng | FQDN → PE private IP | Secrets User | GET secret fixture thành công |
| Workload trong VNet, no-role principal | FQDN → PE private IP | Không có data role | GET bị từ chối do authorization |
| Ngoài VNet, reader hợp lệ | Public path, vault public disabled | Secrets User | Không lấy được secret qua public route |
| Private network, secret sai tên | Private IP | Reader đúng | `404 SecretNotFound` (khi auth/network pass) |
| Private network, expired/wrong tenant token | Private IP | Credential không hợp lệ | Authentication failure |
| Private network, DNS broken | Không resolve hoặc ra IP sai | Reader đúng | DNS/connectivity/network error |
| App Service chưa VNet integration | Không có private path | Managed identity đúng | Không đọc được vault private-only |
| Control plane administrator ngoài VNet | ARM endpoint | ARM permission thích hợp | Thao tác ARM theo IAM/Policy, data plane vẫn có thể bị chặn |

### 26.2. Tách lỗi có cùng HTTP status

Tình huống A: Một principal **có role** ở ngoài mạng bị `ForbiddenByFirewall` → network policy đang chặn.

Tình huống B: Một principal **không role** ở trong mạng nhận `ForbiddenByRbac`/permission denial → network có thể hoạt động nhưng authorization thiếu.

Tình huống C: Caller không lấy được token → lỗi identity, chưa gọi Key Vault.

Không xác nhận hai lớp bằng **một test 403 duy nhất**. Đảm bảo test dùng principal/route **đã được biết trạng thái** và không tiết lộ secret thật.

### 26.3. Test từ nhiều zones/regions

Nếu AKS có nhiều node pools, subnets hoặc regions, test mỗi network path quan trọng. Một test VM sát PE không chứng minh tất cả Pod subnets/peered spokes có route/DNS đúng. Đặt dashboard **success rate theo app/cluster/region**, tránh bình quân che một cluster lỗi.

### 26.4. Test automation

Một CI/staging test có thể:

```text
Provision known test secret & reader identity
       |
       v
Check private endpoint Approved
       |
       v
Probe DNS FQDN -> allowed private IP set
       |
       v
Probe TLS 443 / certificate hostname
       |
       v
GET secret by expected workload identity
       |
       v
GET with no-role identity -> denied
       |
       v
GET from unauthorized network -> denied
       |
       v
Record result, sanitized error code, cleanup
```

Do not run **destructive firewall negative tests** by switching production config mid-traffic; dùng runner ở nguồn mạng khác hoặc test vault để có expected deny mà không làm gián đoạn ứng dụng.

## 27. Runbook 1: Key Vault trả 403 dù đã có Private Endpoint

**Triệu chứng:** Java `getSecret` thất bại với HTTP 403 sau khi đội network tạo PE.

### 27.1. Kiểm tra theo trình tự

1. **Đúng vault?** Đối chiếu Key Vault resource ID, subscription, tenant, URL `<vault>.vault.azure.net`.
2. **PE approved?** Xem connection state và endpoint resource association.
3. **DNS thực tế?** Từ **Pod/VM** resolve vault FQDN; IP có đúng private IP của PE?
4. **Network path?** TCP 443/TLS đến private IP có kết nối được?
5. **Auth token?** Identity trong runtime có đúng tenant/client/object ID không?
6. **Vault permission model?** Azure RBAC hay access policies?
7. **Role/dataActions?** Principal được phép `secrets/get` đúng scope/secret?
8. **Role propagation?** Assignment vừa được tạo có hết thời gian propagation?
9. **Log error code?** Phân biệt network restriction và authorization denial.
10. **Post-fix:** chạy lại positive và negative tests; ghi incident timeline.

### 27.2. Nhìn triệu chứng để phân biệt

| Dấu hiệu | Khả năng | Cách xử lý |
|---|---|---|
| FQDN ra public IP, public disabled | Private DNS chưa áp dụng | Sửa zone/link/custom DNS/CoreDNS |
| FQDN ra PE IP, TLS 443 thông | IAM/token/data role hoặc chính sách khác | Kiểm tra principal/RBAC/audit |
| DNS private đúng nhưng 443 timeout | NSG/UDR/Firewall/PE state | Điều tra route và connection |
| Azure CLI user chạy được, AKS pod không | Hai principal/network paths khác | Test đúng pod identity và DNS |
| Lỗi xuất hiện ngay sau rotation | Secret version/credential/cache/permission thay | Kiểm tra rotation contract |

### 27.3. Điều không nên làm

- Không cấp Subscription Owner cho ứng dụng để chữa `403`.
- Không tắt firewall/bật public access trên production “cho nhanh”.
- Không chuyển URL Java SDK sang private IP.
- Không vô hiệu hóa TLS verification.
- Không đổi cùng lúc DNS, roles, NSG và SDK config rồi mất dấu nguyên nhân.

### 27.4. Tiêu chí khôi phục

Workload lấy được secret fixture bằng intended identity qua private IP; app health/startup đã phục hồi; external positive-role negative-network test vẫn **bị chặn**; audit không còn traffic ngoài policy.

## 28. Runbook 2: DNS trỏ public IP hoặc không resolve

**Triệu chứng:** vault private endpoint Approved nhưng lệnh `nslookup` từ AKS trả public IP, NXDOMAIN hoặc timeout.

### 28.1. Các bước kiểm tra

1. Xác định resolver mà **workload** dùng (`/etc/resolv.conf`, CoreDNS, custom DNS) và source network.
2. Xem Private DNS zone có tên **`privatelink.vaultcore.azure.net`** đúng.
3. Kiểm tra A record alias vault và private endpoint IP.
4. Kiểm tra VNet link với VNet của workload hoặc VNet resolver.
5. Nếu peering/hub-spoke, xác nhận DNS queries đi tới resolver biết zone.
6. Nếu on-prem, xác nhận conditional forwarding qua **Private Resolver inbound endpoint** hoặc forwarder trong Azure VNet, cùng VPN/ExpressRoute.
7. Kiểm tra DNS split-horizon, negative cache và stale records sau PE recreate.
8. Test lại FQDN từ Pod/VM; thử TCP 443 và Key Vault GET.
9. Kiểm tra các vault khác có bị shadow DNS zone sai không.
10. Ghi DNS query paths và thay đổi vào architecture/runbook.

### 28.2. Không sửa DNS bằng file hosts production

Gán `kv-prod.vault.azure.net=10.42.5.4` trong hosts file có thể làm một test nhanh pass nhưng tạo **drift và failure khi PE IP đổi**. Dùng Private DNS zone, zone group và resolver topology chuẩn, quản lý bằng IaC.

### 28.3. Trường hợp nhiều private endpoints

Nếu một vault có PE trong nhiều VNets nhưng cùng zone bị ghi records gây phân giải sai khu vực, thiết kế zone strategy theo **DNS resolution scope**. Đừng trông vào round-robin A records khi ứng dụng cần route riêng và không chắc mọi IP đều reachable từ mọi spoke.

## 29. Runbook 3: DNS private đúng nhưng TCP/TLS không vào được

**Triệu chứng:** `nslookup` trả `10.42.5.4` nhưng `curl` hoặc `SecretClient` timeout/SSL fail.

### 29.1. Phân loại

- **Connect timeout:** route/NSG/firewall/UDR, peering, proxy, PE status.
- **Connection reset:** middlebox/proxy/network flaps hoặc service-side close.
- **TLS handshake failure:** truststore/CA/hostname mismatch, TLS interception/proxy.
- **HTTP 401/403:** đã có HTTP response; tiếp tục auth/network ACL diagnosis theo code.

### 29.2. Quy trình

1. Xác minh PE Approved và NIC IP vẫn đúng DNS.
2. Kiểm tra source subnet, effective NSG/route và firewall logs.
3. Kiểm tra DNS trả IP phù hợp từ chính runtime.
4. Kiểm tra proxy variables `HTTPS_PROXY`, `NO_PROXY` và Java JVM proxy config.
5. Test TCP 443 đến FQDN và xem TLS certificate hostname.
6. Nếu có TLS inspection, yêu cầu security/network review; **không tắt verification**.
7. Điều tra peering/VPN/return route nếu source ở mạng khác.
8. So sánh từ một VM reference trong VNet để khoanh vùng Pod vs network.
9. Sau sửa, thử `SecretClient.getSecret` bằng identity fixture.
10. Test negative path ngoài VNet vẫn deny.

### 29.3. Không mở inbound port trên Key Vault

Không có VM/SSH listener bên trong Key Vault để mở NSG inbound kiểu app server. Kết nối hợp lệ là client HTTPS tới **private endpoint IP port 443** trên network path được hỗ trợ; service target được Azure quản lý.

## 30. Runbook 4: App Service/CI hoặc rotation ngừng hoạt động sau private cutover

**Triệu chứng:** AKS API vẫn đọc được secret, nhưng Azure Functions refresh thất bại, CI pipeline không deploy được hoặc certificate rotation job báo lỗi.

### 30.1. Tìm mọi consumer

Lập inventory:

```text
AKS workloads / CSI provider
App Service Key Vault references
Azure Functions / Logic Apps / Automation
CI/CD runners / scripts / Terraform or Bicep provisioning
VMs / jumpboxes / batch jobs
Certificate renewal / backup & recovery operations
Monitoring / synthetic probes
Hybrid/on-prem apps
```

Không giả định mọi consumer gọi Key Vault cùng identity hoặc network path. Một số chỉ dùng ARM để cấu hình, một số phải gọi data plane.

### 30.2. Cách xử lý

1. Xác định consumer nào thực sự bị ảnh hưởng và thời điểm cutover.
2. Kiểm tra VNet Integration/private path của consumer đó; không dùng kết quả AKS thay thế.
3. Kiểm tra DNS và Private Endpoint accessibility từ runtime.
4. Kiểm tra identity used by reference/SDK và data-plane role.
5. Kiểm tra platform cache/refresh behavior của Key Vault reference.
6. Với hosted CI, chuyển sang VNet-connected runner hoặc xây flow không cần secret retrieval.
7. Với rotation job, bố trí network path và write permission phù hợp.
8. Chạy end-to-end test sau khắc phục và theo dõi expiry.
9. Nếu cần rollback public network, chỉ theo **emergency change plan được phê duyệt** với kiểm soát tạm thời; có thời hạn và audit.
10. Cập nhật dependency inventory để cutover lần sau không sót consumer.

### 30.3. Không dùng “trusted services bypass” như công tắc cứu hộ

Bypass không bảo đảm hosted runner hay mọi Azure app được miễn firewall. Khi policy private-only, giải pháp bền vững là **đặt consumer trên mạng có thể đi PE** hoặc thay đổi kiến trúc secret flow, không mở public access vô thời hạn.

## 31. Disaster recovery, nhiều region và vòng đời Private Endpoint

Một Key Vault được kết nối bằng private endpoint không tự tạo một kế hoạch DR hoàn chỉnh cho ứng dụng.

### 31.1. Phân biệt HA của Vault và availability của network path

Bạn có thể có một Key Vault managed service vẫn healthy, nhưng Java app không lấy được secret vì:

- Private DNS Resolver trong hub VNet bị lỗi.
- Peering/VPN/ExpressRoute mất đường.
- Firewall chặn TCP 443 giữa AKS và PE.
- Private Endpoint connection bị thay/đang Pending.
- App Service thiếu outbound VNet integration sau scale/redeployment.
- Identity token không lấy được do federation/tenant policy.

**RTO của ứng dụng** là thời điểm ứng dụng lấy được secret và phục hồi chức năng, không chỉ khi resource Key Vault báo healthy.

### 31.2. Region dự phòng cần những gì?

```text
Region A
  App A -> DNS A -> Private Endpoint A -> Key Vault
  Local identity/RBAC and connectivity tested

Region B
  App B -> DNS B -> Private Endpoint B -> Key Vault
  Local identity/RBAC and connectivity tested
```

Đây là sơ đồ **khái niệm**. Khả năng region placement của private endpoint, disaster recovery của vault, replication/failover và client route cần xác minh theo Azure service model đang áp dụng. Một “vault Geo-Redundant” không tự cấp private DNS, endpoint và network route trong region B.

### 31.3. Có nên dùng một vault hay hai vault?

| Mô hình | Lợi ích | Thách thức |
|---|---|---|
| Một vault được mọi workload truy cập | Dễ quản lý một nguồn secret/version | Network/identity phụ thuộc cùng vault, latency/DR |
| Vault riêng theo environment/app | Boundary truy cập nhỏ, ít blast radius | Rotation/sync và inventory nhiều hơn |
| Vault riêng theo region | Hỗ trợ regional autonomy/DR nếu thiết kế đúng | Đồng bộ secrets/certificates, version drift, cost |

Không mặc định secret versions và certificates được tự động đồng bộ giữa **hai vault độc lập**; nếu chọn regional vaults, phải có **secret synchronization/rotation strategy** an toàn với change audit và tránh log plaintext.

### 31.4. Sau khi xóa/tạo lại Private Endpoint

Private Endpoint có thể lấy IP mới; DNS zone group và A record cần cập nhật. Workload có thể giữ DNS cache cũ; kiểm tra:

1. PE connection Approved và NIC IP mới.
2. DNS zone A record đúng IP và VNet link.
3. DNS resolver cache và Java HTTP connection pool.
4. NSG/UDR/firewall rules không hard-code địa chỉ cũ.
5. App workloads ở mọi subnet/region đọc được secret.
6. Negative tests ngoài mạng tiếp tục bị chặn.

### 31.5. Khả năng khôi phục khi Vault bị xóa nhầm

Key Vault có **soft delete** và tùy cấu hình **purge protection** để giảm rủi ro xóa/purge. Cần hiểu retention/restore limitations, backup/restore permissions và tên resource; không tự purge một vault để “giải phóng tên” nếu nó chứa dữ liệu có nghĩa vụ giữ lại. **Private Endpoint/DNS dependencies có thể cần được dựng/kiểm tra lại** sau các thao tác recovery.

## 32. Cách chuyển một Vault production từ public sang private mà ít gián đoạn

Đây là **migration runbook** cho vault đang được nhiều workloads dùng; chạy theo change management của tổ chức, không phải một script bật/tắt duy nhất.

### 32.1. Giai đoạn A — Inventory

1. Liệt kê các clients **data plane**: AKS Pods, VM services, App Service refs, Functions, CI/rotation jobs, on-prem.
2. Liệt kê principal identities và roles/access policies theo workload.
3. Xác định Azure resources/app settings lưu vault URI/secret names.
4. Thống kê QPS, secret caching, rotation cadence và peak deploy traffic.
5. Ghi public firewall/VNet rules và diagnostic settings hiện tại.
6. Xác định owner của PE, DNS zone, VNet links, custom DNS/forwarders.
7. Chốt tiêu chí nghiệm thu và rollback.

### 32.2. Giai đoạn B — Chuẩn bị private network

1. Provision PE tới đúng Key Vault và subresource `vault`.
2. Chờ approval và kiểm tra PE IP.
3. Cấu hình Private DNS zone `privatelink.vaultcore.azure.net`.
4. Link/forward DNS tới mọi VNets/regions/hybrid consumers cần thiết.
5. Bố trí VNet Integration cho App Service/Functions và runner cho CI.
6. Kiểm tra route/NSG/firewall/private DNS từ **mỗi lớp workload**.
7. Thử secret fixture GET với đúng workload identity.

### 32.3. Giai đoạn C — Canary

Chọn một dịch vụ ít rủi ro:

```text
Canary (10% traffic hoặc một deployment test)
    |
    +-- Check FQDN resolves PE IP
    +-- Check secret GET p95/error rate
    +-- Check application health/startup
    +-- Check rotation/ref refresh path
    +-- Check no public dependency
    |
    v
Approve broader rollout
```

**Canary chỉ hiệu quả nếu nó dùng cùng network/DNS/identity pattern production**; một VM test từ VNet khác không thay việc kiểm tra App Service/AKS network.

### 32.4. Giai đoạn D — Đóng public

Trong change window:

1. Snapshot cấu hình mạng/IaC và lưu change ticket.
2. Đặt `publicNetworkAccess Disabled` nếu yêu cầu.
3. Kiểm tra ứng dụng tiếp tục đọc secret qua private path.
4. Thử negative request từ mạng công khai với test reader hợp lệ.
5. Kiểm tra alerts, diagnostic logs, app health và secret rotation.
6. Quan sát qua ít nhất một chu kỳ startup/refresh phù hợp với business SLA.
7. Xác nhận security owner sign-off.

### 32.5. Giai đoạn E — Rollback (chỉ khi được phép)

Nếu toàn bộ ứng dụng lỗi do DNS/route và thời gian khôi phục vượt RTO, **đánh giá rollback theo plan phê duyệt**. Một tùy chọn kỹ thuật có thể là bật lại public access **tạm** cùng firewall allowlist nghiêm ngặt; nhưng chỉ nếu **security/compliance policy cho phép**. Nếu không được phép, dùng private break-glass network path được chuẩn bị trước. Mỗi rollback phải có:

- Người có quyền/phê duyệt.
- Scope/thời hạn ngoại lệ.
- Logging/alert khi public access thay đổi.
- Quy trình quay lại private-only sau khi DNS/PE được sửa.
- Root-cause và action items.

**Không tự mở public endpoint vô thời hạn** để phục hồi ứng dụng nhanh rồi quên cấu hình.

### 32.6. Giai đoạn F — Quản lý drift

Sau migration, đưa PE, DNS zone/link, network ACL, role assignments và diagnostic settings vào **IaC**. Áp **Azure Policy** và scheduled review để phát hiện cấu hình bị đổi ngoài kế hoạch.

## 33. IaC và cấu hình bảo mật theo môi trường

Một bản thiết kế IaC nên bao gồm:

```yaml
# Pseudocode kiến trúc: KHÔNG phải template Terraform/Bicep thực thi.
environment: production
keyVault:
  name: kv-orders-prod
  publicNetworkAccess: Disabled
  authorizationMode: AzureRBAC
  secretReaders:
    - identity: orders-api-workload-identity
      role: KeyVaultSecretsUser
privateEndpoint:
  subresource: vault
  subnet: /subscriptions/.../subnets/snet-private-endpoints
  requireApprovedConnection: true
privateDns:
  zone: privatelink.vaultcore.azure.net
  linkedVirtualNetworks:
    - vnet-orders-prod
    - vnet-shared-dns-hub
logging:
  keyVaultAudit: enabled
  activityLogSecurityAlerts: enabled
validation:
  dnsMustResolveToPrivateIp: true
  allowedIdentityCanReadFixture: true
  publicReaderDenied: true
```

Các field này là **contract kiến trúc/học tập**, không phải ARM/Bicep/Terraform schema. Khi triển khai thật, cần dùng API versions/role IDs, cấu hình Private DNS zone group, RBAC, VNet links và identities đúng IaC provider version.

### 33.1. Vì sao IaC phải chứa DNS?

Một template chỉ tạo vault và PE nhưng quên zone group/VNet links vẫn có thể báo deployment succeeded. Application lại resolve public endpoint và fail. Cần coi **DNS là một dependency cùng mức ưu tiên** với PE và Key Vault resource.

### 33.2. Thứ tự dependency trong deployment

```text
VNet/Subnet + Key Vault
         |
         v
Private Endpoint resource
         |
         v
Connection Approved
         |
         v
Private DNS zone/links/zone group
         |
         v
VNet-connected workload + identity/role
         |
         v
Positive secret GET + negative public test
         |
         v
Public network access Disabled / compliance sign-off
```

Với production fresh deployment có policy private-only ngay từ đầu, có thể chọn trình tự khác và sử dụng ARM control plane, nhưng vẫn phải đảm bảo **network readiness trước workload startup**. Không lấy một thứ tự minh họa làm guarantee mọi resource provider sẽ provision đồng bộ.

### 33.3. Policy-as-code và đánh giá tuân thủ

Azure Policy có thể audit/deny vaults không đúng network configuration, nhưng policy **không tự chứng minh DNS/route** đã hoạt động. Kết hợp:

- Static checks: public network disabled, PE exists, RBAC model đúng.
- Dynamic tests: DNS/443/GET từ intended runtime, public deny.
- Operational monitors: network/role drift, failed secret reads, certificate expiry.

### 33.4. Không quản lý secrets bằng plaintext IaC

Không đưa secret values vào template parameters hoặc Terraform state mà không có kiểm soát. Terraform state/CI artifact có thể lưu sensitive data dù output bị masked; chọn **managed identity, runtime secret references, secure parameters và state backend được bảo vệ**. PE/network IaC không cần xuất mọi secret value.

## 34. Chi phí và khả năng vận hành

Private Endpoint mang lại lợi ích bảo mật nhưng có chi phí hạ tầng và vận hành. Các khoản có thể gồm:

| Thành phần | Chi phí có thể có | Hướng tối ưu |
|---|---|---|
| Private Endpoint | Giờ endpoint và lượng dữ liệu xử lý theo giá dịch vụ/region | Chỉ tạo PE cần thiết, dùng network architecture rõ |
| Azure Private DNS | Zone/queries theo mô hình tính phí hiện hành | Zone/link có mục đích, tránh duplicate DNS |
| Azure DNS Private Resolver | Inbound/outbound endpoints và query/usage | Dùng cho hybrid/custom DNS khi cần, sizing hợp lý |
| VNet peering/VPN/ExpressRoute | Data transfer, gateway/connectivity | Thiết kế locality và shared networking |
| Key Vault | Secret/key/certificate operations, transactions | Cache theo security policy, batch phù hợp |
| Azure Monitor/Log Analytics | Log ingestion/retention/alerts | Thu categories cần thiết, redact |
| CI/private runners | Runner compute/network | Schedule, auto-stop, scope access |
| Operations | DNS incidents, cert rotation, change reviews | IaC, runbooks và synthetic probes |

### 34.1. Đừng đưa đơn giá cố định

Giá Private Link, DNS Resolver, Key Vault operations và logging thay đổi theo **region, SKU, volume và pricing model**. Hãy dùng **Azure Pricing Calculator, Cost Management và bill thực**. Không suy rằng “private access miễn phí” chỉ vì traffic ở trong Azure.

### 34.2. Chi phí vì retry/quota

Nếu Java service gọi `getSecret` trên mọi request API và DNS/firewall mới khiến 50% requests lỗi, retry có thể tăng Key Vault transactions, thread contention và log volume. **Caching, startup orchestration và bounded retries** có thể giảm tải; nhưng tránh cache vô hạn làm chậm thu hồi secret khi rotate/revoke.

### 34.3. Một vault chia sẻ nhiều ứng dụng có lợi và hại

Tập trung vault có thể giảm số PE và overhead quản trị, nhưng cũng tăng blast radius và khó tách quyền/mạng/rotation. Vault riêng theo application/environment có thể tăng chi phí nhưng **dễ định nghĩa security boundary** hơn. Đánh giá theo threat model và TCO, không chỉ số resource.

### 34.4. Availability và dependency budget

Ứng dụng cần secret tại startup nên có strategy nếu Key Vault/DNS tạm unavailable: bounded startup retry, health/restart policy, credential rotation window và caching nếu được phép. Không để mọi pod cùng khởi động lại/lấy secret đồng thời tạo **thundering herd**. Một restart loop có thể khiến sự cố Key Vault lan thành outage toàn app.

## 35. Case study: bảo vệ Key Vault cho nền tảng đặt hàng Java

### 35.1. Bối cảnh

Nền tảng có:

- Ứng dụng **`orders-api`** Java 17/Spring Boot trên **AKS** trong VNet production.
- Worker xử lý hàng đợi trên **Azure Functions**.
- **Azure SQL Database** lưu đơn hàng; Key Vault chứa database password, signing key reference và certificate metadata.
- **Azure DevOps/GitHub Actions** triển khai ứng dụng qua OIDC.
- Kết nối on-prem phục vụ incident response.
- Yêu cầu: không đọc secret từ public Internet; Azure RBAC least privilege; secret rotation tự động; audit và alert.

### 35.2. Kiến trúc mục tiêu

```text
                  Azure Control Plane / IaC
                           |
                  Policy + PIM + audit
                           |
                           v
                   Key Vault resource
                   public access = Disabled
                           ^
                           |
                Azure Private Link data plane
                           |
                    PE private IP
                           ^
                           |
            Private DNS zone/link + resolver
               /           |           \
              /            |            \
    AKS orders-api    Functions worker   On-prem management
       workload ID    VNet integration   VPN + DNS forwarder
              \            |            /
               +-----------+-----------+
                           |
                   Entra token + RBAC
                           |
                   Audited secret access

CI: deploy ARM resources; only private runner may perform
    Key Vault data-plane tests/secrets operations.
```

### 35.3. Chia quyền

| Principal | Quyền cần | Không cần |
|---|---|---|
| AKS orders-api workload identity | Get secret/certificate/key operation cụ thể theo thiết kế | Set/delete/purge mọi secrets |
| Functions rotation identity | Quản lý secret cần rotate | Network Contributor toàn VNet |
| CI IaC identity | Deploy infra/role changes qua approval | Đọc mọi secret value |
| CI private integration identity | Đọc test secret fixture | Sửa secret production |
| Security administrators | Policy/IAM/audit theo approval | Dùng chung credential của app |
| Developer laptop | Read metadata docs/đẩy code | Public data-plane access vào vault production |

### 35.4. Lịch cutover minh họa

```text
Day -7: Inventory data-plane consumers and identities
Day -5: Deploy PE, private DNS zone, VNet links
Day -4: Test AKS pod and Functions outbound access
Day -3: Move CI secret-reading step to VNet-connected runner
Day -2: Test secret rotation + monitoring + hybrid DNS
Day -1: Canary access, verify data plane RBAC allow/deny
Day  0: Disable public network access in approved window
Day +1: Watch secret-fetch errors, rotation and API health
```

Đây là timeline **để minh họa quy trình**, không phải thời gian triển khai bắt buộc hay SLA Azure.

### 35.5. Một sự cố thường xảy ra

Sau cutover, AKS vẫn hoạt động nhưng Azure Functions báo không resolve được Key Vault reference. Đội network có PE trong VNet của AKS, nhưng Functions app chưa có **outbound VNet Integration** hoặc custom DNS không thấy private zone.

Hướng sửa:

1. Không bật public access ngay.
2. Kiểm tra Functions hosting plan và VNet Integration.
3. Kiểm tra DNS FQDN từ Functions runtime.
4. Kiểm tra identity của Key Vault reference và Secrets User role.
5. Test một secret fixture; kiểm tra refresh timing.
6. Cập nhật dependency inventory và synthetic probe cho Functions.

**Bài học:** một workload thành công không chứng minh toàn bộ fleet có private connectivity.

### 35.6. Một sự cố DNS hybrid khác

On-prem management client dùng DNS nội bộ không forward `privatelink.vaultcore.azure.net` qua Private Resolver. FQDN vault resolve public IP và bị từ chối. Đội vận hành kiểm tra route VPN vẫn OK nhưng nghĩ Key Vault hỏng.

Hướng sửa:

- Thiết lập conditional forwarding tới Azure DNS Private Resolver inbound endpoint theo topology.
- Xác minh response từ client on-prem trả private IP.
- Kiểm tra route/firewall TCP 443 tới PE.
- Test token và Key Vault data-plane role sau khi DNS hoạt động.

### 35.7. Chỉ số nghiệm thu

```text
Network:
  AKS, Functions and authorized on-prem resolve PE IP.
  Outside VNet public path cannot read test secret.

Identity:
  Intended principals can get exactly required secret.
  No-role principal is denied inside VNet.

Operations:
  Key Vault reference and rotation workflows work.
  Audit logs and alerts received in approved workspace.
  Rollback/DR path documented and rehearsed.

Application:
  Secret fetch p95/error within SLO.
  No secret value in logs.
  No unexpected outage after startup/scale/deploy.
```

## 36. Bài tập thực hành

### Bài tập A — Phân biệt hai tầng bảo vệ

Một VM trong VNet có DNS private đúng và TCP 443 tới PE thành công, nhưng `SecretClient.getSecret()` vẫn trả 403.

**Nhiệm vụ:** nêu năm bước điều tra theo thứ tự, phân biệt `ForbiddenByFirewall` với thiếu `Key Vault Secrets User`.

**Hướng giải:** kiểm tra resource ID, PE status, DNS/route/TLS, token principal/tenant, RBAC model/dataActions và sanitized error code. Không bật public access hay cấp Owner.

### Bài tập B — Kết nối từ AKS

Tạo kiến trúc một AKS Pod dùng Workload Identity đọc secret từ vault private-only. Lập sơ đồ service account → OIDC federation → Entra token → private DNS → PE → Key Vault.

**Nhiệm vụ:** xác định ít nhất ba lỗi cấu hình có thể khiến Pod fail nhưng jumpbox VM pass.

**Hướng giải:** CoreDNS/custom DNS của Pod khác VM, missing federated credential/client ID, Pod network policy/outbound route, wrong Key Vault role/scope.

### Bài tập C — Private DNS

PE được tạo với IP `10.42.5.4`, VNet link có từ `vnet-app`, nhưng on-prem `nslookup kv-prod.vault.azure.net` ra IP public.

**Nhiệm vụ:** thiết kế đường DNS Private Resolver và route qua VPN, chỉ ra vì sao chỉ tạo A record trong Azure không đủ cho on-prem.

**Hướng giải:** on-prem DNS phải forward đúng private-link zone/queries tới resolver có quyền thấy Azure Private DNS; route tới PE và network firewall phải hoạt động.

### Bài tập D — Public endpoint firewall hay PE?

Một partner có fixed public IPv4, chỉ gọi Key Vault vài lần/ngày. Policy công ty yêu cầu không có public data-plane access production.

**Nhiệm vụ:** so sánh IP allowlist, service endpoint và Private Endpoint, chọn giải pháp phù hợp policy và nêu mạng cần bổ sung.

**Hướng giải:** IP allowlist không đáp ứng yêu cầu private-only; cần private connectivity/identity integration hoặc thiết kế partner không gọi Key Vault data plane trực tiếp.

### Bài tập E — Kiểm tra IAM negative test

Nhóm security muốn chứng minh người có `Key Vault Secrets User` ngoài mạng không thể đọc secret.

**Nhiệm vụ:** thiết kế test an toàn bằng test principal/fixture, phân biệt network deny với auth deny, ngăn lộ secret qua CLI logs.

**Hướng giải:** giữ role được biết trên test vault; chạy từ external authorized test environment và từ private workload, chỉ output secret id/status, không echo value.

### Bài tập F — Chuyển đổi không downtime

Một vault hiện được dùng bởi AKS, App Service, CI và on-prem. Hãy lập **migration checklist** gồm inventory, DNS/VNet, identity, staged validation, public disable, negative tests và rollback.

**Hướng giải:** không tắt public trước khi mọi data-plane consumer được xác minh, Cloud Shell/hosted CI không mặc định có private path.

### Bài tập G — Java SDK và TLS

Developer thay URL `https://kv-prod.vault.azure.net` thành `https://10.42.5.4` để “ép private path”; ứng dụng báo `SSLHandshakeException`.

**Nhiệm vụ:** chỉ ra lý do hostname mismatch và cách khắc phục đúng.

**Hướng giải:** giữ vault FQDN trong `SecretClientBuilder.vaultUrl`, cấu hình DNS để resolve private IP; không disable certificate validation.

### Bài tập H — Azure Key Vault references

App Service đã cấu hình Key Vault reference và managed identity nhưng setting không resolve sau khi vault private-only.

**Nhiệm vụ:** phân biệt inbound App Service PE với outbound VNet Integration, kiểm tra private DNS, identity, RBAC và reference cache.

**Hướng giải:** tạo đúng outbound private route, test từ runtime/plan hỗ trợ, kiểm tra reference identity và secret version/refresh.

### Bài tập I — Multiple private endpoints

Hai VNets ở hai khu vực có hai PEs tới một vault. Sau khi dùng chung Private DNS zone, một số clients ở region B nhận IP PE của region A mà không route được.

**Nhiệm vụ:** thiết kế cách tổ chức zone/link/resolver scopes và đo lường khi cutover.

**Hướng giải:** DNS phải trả endpoint reachable phù hợp từng mạng; review zone groups/A records và conditional forwarding, test từng VNet/region.

### Bài tập J — KQL và alert

Yêu cầu tạo alerts khi (1) Key Vault forbidden rate tăng, (2) public access bật trở lại, (3) rotation job fail.

**Nhiệm vụ:** xác định nguồn Azure Monitor/Activity Log/application metrics, cấu hình diagnostics, viết một KQL dựa trên **table/field đã có thật**, xác định owner/window/runbook.

**Hướng giải:** data-plane audit và control-plane activity là hai nguồn riêng; synthetic secret-fetch telemetry giúp đo ảnh hưởng ứng dụng.

### Bài tập K — Cost và caching

Một ứng dụng Java có 3.000 requests/s, mỗi request gọi Key Vault 1 lần. Đội muốn giảm Key Vault QPS nhưng cần rotation lấy hiệu lực trong thời gian giới hạn.

**Nhiệm vụ:** thiết kế cache TTL/refresh, failure policy, không log secret, và đo cost/latency/retry behavior.

**Hướng giải:** dùng cache theo security policy; explicit rotation invalidation hoặc bounded refresh, không để stale secret tồn tại vô hạn.

### Bài tập L — DR và mất resolver

Key Vault platform báo healthy nhưng một vùng không lấy được secret vì DNS resolver hub lỗi.

**Nhiệm vụ:** viết runbook phân biệt Key Vault outage và network/DNS outage; mô tả failover resolver/private path và điều kiện xác nhận app RTO.

**Hướng giải:** platform health không đủ; cần DNS probe, TCP, token/RBAC, application secret-get and health SLO, negative public test.

## 37. Câu hỏi tự kiểm tra

**1. Private Endpoint có tự cấp quyền đọc secret không?** Không. Nó cung cấp đường truy cập riêng; identity phải được xác thực bằng Microsoft Entra ID và có quyền data plane.

**2. Key Vault có hai mặt phẳng chính nào?** ARM **control plane** quản lý resource/config; **data plane** đọc/sửa secrets, keys và certificates qua vault endpoint.

**3. Đặt `publicNetworkAccess Disabled` có chặn toàn bộ ARM control plane không?** Không; quyền ARM/quản trị cần bảo vệ riêng qua RBAC, Azure Policy và change controls.

**4. Client Java có phải dùng private IP của PE trong `vaultUrl` không?** Không. Dùng `https://<vault>.vault.azure.net` và để DNS trả private IP.

**5. Private DNS zone chuẩn cho Key Vault vault là gì?** `privatelink.vaultcore.azure.net`.

**6. Vì sao không tạo private DNS zone `vault.azure.net` tùy tiện?** Có thể shadow các public DNS records hợp lệ và làm hỏng resolution tới các vault khác.

**7. Private Endpoint connection cần trạng thái gì trước khi kiểm thử?** **Approved**, cùng DNS/route/permissions đúng.

**8. Một PE approved có chứng minh application sẽ resolve private IP không?** Không. Còn private DNS zone group, A record, VNet links và DNS forwarders.

**9. Azure Cloud Shell mặc định có phải ở cùng VNet với AKS không?** Không. Test network private phải chạy từ workload/VNet phù hợp.

**10. Service endpoint và private endpoint khác nhau thế nào?** Service endpoint dùng route/ACL subnet tới dịch vụ qua endpoint logic công khai; private endpoint cấp private IP trong VNet qua Private Link.

**11. IP firewall allowlist có dùng private IP của VM/Pod không?** Không phải mô hình thay thế PE; Key Vault public IP rules hướng tới public IPv4/CIDRs được hỗ trợ.

**12. Trusted Microsoft services bypass có bao gồm mọi Azure resource không?** Không. Danh sách trusted services hữu hạn theo tính năng, không phải công tắc allow-all.

**13. Một workload có `Key Vault Secrets User` nhưng DNS trỏ public IP sẽ ra sao với private-only vault?** Không được đọc data plane qua public route; có thể gặp firewall error.

**14. Một workload resolve private IP đúng nhưng thiếu Secrets User sẽ ra sao?** Có kết nối mạng nhưng không đủ data-plane authorization, có thể bị 403.

**15. `Key Vault Reader` có mặc định được đọc plaintext secret values không?** Không; role metadata và secret-value permissions khác nhau.

**16. Khi vault dùng Azure RBAC mode, legacy access policy get có đủ không?** Không tự đủ; kiểm tra authorization model đang bật.

**17. Một service principal có ARM Contributor có chắc lấy được secret?** Không; cần quyền data plane. Quyền quản trị quá rộng vẫn là rủi ro đổi cấu hình/escalation.

**18. Workload Identity trên AKS cần gì ngoài service account?** OIDC issuer/federated credential đúng, Azure identity, data-plane RBAC, DNS và route tới PE.

**19. Inbound Private Endpoint của App Service có cấp outbound tới Key Vault không?** Không. Outbound VNet Integration là thiết kế riêng.

**20. OIDC cho CI có tự cấp private network path không?** Không. Identity federation và network connectivity là hai lớp khác nhau.

**21. Vì sao on-prem có VPN nhưng DNS vẫn sai?** Private DNS zone không tự được resolver on-prem nhìn thấy; cần conditional forwarding qua DNS resolver/forwarder trong Azure.

**22. Có thể forward DNS trực tiếp từ mọi on-prem resolver tới Azure-provided DNS 168.63.129.16 không?** Không giả định được; dùng Azure DNS Private Resolver inbound endpoint hoặc giải pháp DNS forwarder trong VNet thích hợp.

**23. Vì sao `curl https://vault.vault.azure.net/` trả 401 không tự chứng minh RBAC lỗi?** Root path có thể không phải secret API; TCP/TLS đã hoạt động nhưng authorization/request semantics chưa được kiểm tra.

**24. HTTP 403 luôn có nghĩa thiếu role?** Không. Network ACL, firewall, data-plane policy hoặc principal có thể gây 403; cần sanitized error code và DNS/identity diagnostics.

**25. Nếu DNS private đúng nhưng 443 timeout, bắt đầu ở đâu?** PE connection/NIC IP, NSG/UDR/firewall/route, peering/VPN, proxy, source subnet.

**26. Nếu `SSLHandshakeException` sau khi dùng IP PE thay hostname, giải pháp?** Khôi phục vault FQDN và private DNS; không tắt certificate verification.

**27. Vì sao cần negative test từ ngoài network với identity có quyền đọc?** Để chứng minh **network restriction** hoạt động độc lập với RBAC; nếu identity cũng thiếu role thì denial không đủ bằng chứng.

**28. Khi thay public access, những consumers nào thường bị quên?** CI runners, App Service/Functions Key Vault references, rotation/backup jobs, on-prem, monitoring probes và slots.

**29. Có nên chạy `getSecret` trên mỗi HTTP request?** Thường không; cần caching/refresh và rotation policy theo bảo mật/latency/quota.

**30. Private Endpoint có đồng nghĩa Key Vault không thể bị exfiltrate qua application logs?** Không. App vẫn có thể log secret value hoặc trả lộ ra API.

**31. Key Vault audit logs và Activity Log khác nhau ra sao?** Audit data-plane operations vs control-plane resource/config changes, với schemas/categories cụ thể.

**32. Cần monitor gì ngoài Key Vault health?** DNS/PE connectivity, workload secret-get error/latency, rotation, RBAC drift và public access config changes.

**33. Nhiều PEs của một vault có tự dùng endpoint gần nhất không?** Không. DNS/resolution và route phải được thiết kế riêng cho VNets/regions.

**34. Có nên tắt public access trước khi dựng private DNS?** Không với vault đang phục vụ workloads trừ khi thiết kế fresh deployment/rollback đáp ứng policy; phải bảo đảm private path sẵn sàng.

**35. Nếu App Service reference không resolve, có nên cấp Owner cho app?** Không. Kiểm tra outbound VNet Integration, DNS, reference identity, role scope và refresh.

**36. Purge protection có thể ảnh hưởng lab cleanup như thế nào?** Sau khi bật, không thể tùy tiện purge/disable trong retention window, có thể giữ tên vault và thay đổi lifecycle test.

**37. Azure Policy có tự chứng minh DNS hoạt động không?** Không. Static compliance configuration phải kết hợp dynamic network/secret-fetch tests.

**38. Một rollback bật lại public access nên cần gì?** Phê duyệt bảo mật/compliance, allowlist nghiêm ngặt, timebox, audit và kế hoạch quay về private-only.

**39. Vì sao secret rotation phải được test sau cutover?** Rotation service cũng là data-plane consumer cần network/private DNS/identity/write permission riêng.

**40. Đâu là tiêu chí private-only hoàn chỉnh?** Private IP DNS/route/TLS hoạt động, đúng identity đọc được fixture, no-role denied, ngoài mạng với read role bị chặn, rotation/CI/monitoring hoạt động và config được quản trị/audit.

## 38. Checklist triển khai production

### 38.1. Phạm vi, threat model và IAM

- [ ] Đã xác định đúng **Azure Key Vault vault** và phân biệt Managed HSM nếu có.
- [ ] Đã phân loại secrets, keys, certificates và permissions thật sự cần.
- [ ] Đã xác định resource/subscription/tenant/region và business owners.
- [ ] Có threat model cho public exposure, credential compromise, IAM escalation và DNS misrouting.
- [ ] Vault dùng RBAC hoặc access policy model có chủ đích; không trộn giả định.
- [ ] App chỉ có data-plane roles tối thiểu, không dùng Key Vault Administrator/Owner quá rộng.
- [ ] Managed/Workload identities đúng principal/object ID/tenant; không dùng shared password lâu dài.
- [ ] Control-plane network/RBAC changes có PIM/approvals/Policy và audit.
- [ ] Developer/CI không được tự bật lại public access ngoài quy trình.

### 38.2. Private Endpoint và DNS

- [ ] PE target là đúng Key Vault resource ID và subresource `vault`.
- [ ] PE connection state **Approved**, NIC private IP được xác minh.
- [ ] Private DNS zone `privatelink.vaultcore.azure.net` đúng.
- [ ] PE DNS zone group/A record quản lý đúng vault alias/IP.
- [ ] VNets, spokes, hub resolvers được link/forward theo topology.
- [ ] AKS Pods/VMs/App Service runtime/hybrid resolve vault FQDN về private IP.
- [ ] Đã test route TCP 443/TLS certificate hostname từ đúng runtime.
- [ ] NSG, UDR, firewall, proxy, peering/VPN/ExpressRoute được kiểm tra.
- [ ] Không hard-code private IP hoặc thay SDK URL bằng IP.
- [ ] Có thiết kế cho nhiều PE/regions, tránh DNS trả IP không reachable.

### 38.3. Network policies

- [ ] Public network access Disabled khi policy yêu cầu private-only.
- [ ] Nếu dùng firewall public mode, defaultAction, IP/VNet rules và bypass được duyệt.
- [ ] Không dùng private RFC1918 addresses làm public IP allowlist.
- [ ] Trusted-services bypass được hiểu đúng giới hạn, không dùng như allow-all.
- [ ] Có positive secret-get test từ private network với identity được phép.
- [ ] Có negative auth test từ private network với identity không quyền.
- [ ] Có negative network test từ ngoài private network với identity có quyền.
- [ ] Các tests không làm lộ secret value/credentials.
- [ ] Azure ARM control plane/IAM vẫn được bảo vệ độc lập với data plane.

### 38.4. Ứng dụng Java, AKS và App Service

- [ ] Java SecretClient dùng `https://<vault>.vault.azure.net` và Entra credential.
- [ ] Client/token lifecycle/SDK version được quản lý, không tạo client mỗi request.
- [ ] Secrets không xuất hiện trong application logs, traces, exceptions hoặc CI artifacts.
- [ ] Có error classification cho DNS, network, TLS, auth, 403, 404, 429, 5xx.
- [ ] SDK retries có deadline, backoff và không bypass security.
- [ ] Secret caching có TTL/rotation/refresh policy và không giữ plaintext vô hạn.
- [ ] AKS OIDC/federated credential/data role/VNet DNS đã test trong Pod.
- [ ] CSI driver/secret mounts có refresh và Kubernetes permissions được kiểm chứng nếu dùng.
- [ ] App Service/Functions có outbound VNet Integration khi cần.
- [ ] Key Vault references có đúng identity, URL, version/refresh và slot configuration.
- [ ] CI data-plane jobs chạy từ approved private network nếu vault private-only.
- [ ] Certificate rotation/backup/monitoring consumers không bị bỏ sót.

### 38.5. Vận hành, giám sát và phục hồi

- [ ] Azure Monitor metric definitions/diagnostic categories đã được khám phá từ vault thật.
- [ ] Diagnostic settings gửi data-plane audit đến destination an toàn và retention hợp lý.
- [ ] Azure Activity Log/Policy alerts theo dõi public access, PE và RBAC drift.
- [ ] Có synthetic probe DNS/TLS/secret GET từ từng workload region.
- [ ] Có alert secret-fetch error rate, latency/throttling và secret/certificate expiry.
- [ ] Có runbooks cho 403, wrong DNS, 443 timeout và reference/CI failure.
- [ ] Có inventory data-plane consumers trước khi thay network.
- [ ] Có change window/canary, rollback private-first và security sign-off.
- [ ] DR/failover đánh giá Private DNS Resolver, network/identity và app RTO.
- [ ] Cleanup lab không tự purge vault được bảo vệ hoặc xóa tài nguyên người khác.
- [ ] Private Endpoint, DNS Resolver, Logs và Key Vault operation costs có owner/budget.
- [ ] Infrastructure as Code + Policy-as-code bảo vệ config và phát hiện drift.

## 39. Kết luận

**Private endpoint và giới hạn truy cập Key Vault** là bài toán **kết hợp network, DNS, identity, authorization và vận hành**. Private Endpoint đưa Key Vault data-plane traffic qua private IP trong VNet, nhưng chỉ hoạt động đúng khi connection được Approved, **private DNS zone `privatelink.vaultcore.azure.net`**, VNet links/forwarders và route TCP/TLS từ workloads được cấu hình chuẩn. Với yêu cầu không truy cập công khai, chỉ chuyển `publicNetworkAccess` sang `Disabled` sau khi mọi consumer quan trọng đã được thử nghiệm; **Key Vault firewall/IP allowlist, service endpoint và trusted Microsoft services bypass không phải các từ đồng nghĩa của Private Endpoint**.

Về phân quyền, **Microsoft Entra ID, managed/workload identity và Key Vault data-plane RBAC/access policies** vẫn là điều kiện độc lập với đường mạng. Java SDK tiếp tục dùng **vault FQDN** và HTTPS/TLS, không gọi trực tiếp private IP. Muốn an toàn production cần **positive/negative tests, DNS/443 probes, audit logs, Azure Policy, runbooks cho 403/DNS/route và kế hoạch rollback/DR**. Khi triển khai đúng, ứng dụng trên AKS, App Service, Functions hoặc on-prem có thể sử dụng secrets/keys/certificates qua đường riêng tư, được kiểm soát quyền, có thể theo dõi, tuân thủ và vận hành bền vững trên Microsoft Azure.
