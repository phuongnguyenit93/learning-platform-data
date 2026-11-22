# Private endpoint, firewall và bảo vệ kết nối database

Một dịch vụ đặt hàng chạy trên **Azure App Service** cần đọc/ghi dữ liệu trong **Azure SQL Database**. Đội phát triển đã tạo tài khoản database, bật HTTPS cho website và giới hạn IP ở ứng dụng, nhưng kết nối database vẫn đi đến endpoint công khai. Khi chuyển database sang mạng riêng, ứng dụng bất ngờ nhận lỗi timeout dù deployment vẫn `Healthy`. Ở một môi trường khác, nhóm vận hành đã tạo **Private Endpoint** nhưng DNS vẫn trả địa chỉ public; nhân viên mở firewall “Allow Azure services” để sửa nhanh, vô tình mở rộng đường truy cập hơn dự kiến.

Đây là vấn đề điển hình của bảo mật cơ sở dữ liệu trên cloud: **Private Endpoint**, **firewall**, **DNS**, **identity**, **TLS** và **quyền truy cập dữ liệu** là các lớp khác nhau. Tạo một tài nguyên Private Endpoint **không tự động chứng minh** ứng dụng đi qua mạng riêng, và có mạng riêng **không có nghĩa** một caller bất kỳ đã được phép đọc bảng dữ liệu.

Bài học nằm trong chương **Cơ sở dữ liệu quan hệ** thuộc module **CLOUD_PROVIDERS_AZURE**, kết nối với bức tranh Azure subscription, resource group, Microsoft Entra ID, virtual network, compute, storage và giám sát. Trọng tâm là triển khai, kiểm chứng và vận hành đường kết nối bảo mật cho **Azure SQL Database**, đồng thời hiểu các khác biệt quan trọng khi sử dụng **Azure SQL Managed Instance**, **Azure Database for PostgreSQL Flexible Server** và **Azure Database for MySQL Flexible Server**.

Sau bài học, bạn có thể:

- Phân biệt public endpoint, database firewall, service endpoint/VNet rule, **Private Link/Private Endpoint** và **VNet-injected private access**.
- Thiết kế luồng ứng dụng → VNet/DNS → private IP → Azure database, không nhầm network boundary với authentication.
- Chọn đúng Private DNS zone, kiểm tra FQDN và phân giải DNS từ **runtime thực** của ứng dụng.
- Thiết lập Private Endpoint cho Azure SQL logical server trong một lab được phép, rồi thử kết nối trước khi vô hiệu hóa public access.
- Bảo vệ kết nối bằng **TLS certificate validation** và **Microsoft Entra ID/managed identity** khi dịch vụ/driver hỗ trợ; áp dụng least-privilege SQL permissions.
- Nhận diện lỗi DNS, network, firewall, certificate, database login và quyền dữ liệu theo từng lớp.
- Lập kế hoạch cắt chuyển từ public sang private mà không khóa nhầm ứng dụng, xử lý HA/DR, quan sát, chi phí và cleanup.

## 1. Mô hình đe dọa: bảo vệ điều gì?

Một database quan hệ trong Azure lưu dữ liệu có giá trị: khách hàng, giao dịch, đơn hàng, thông tin nhân sự hoặc số dư. Mục tiêu bảo vệ thường gồm:

1. **Không để endpoint có đường truy cập public không cần thiết.**
2. **Chỉ các mạng và workload được phê duyệt** có thể kết nối đến database listener.
3. **Chỉ danh tính hợp lệ** được login và thực thi câu lệnh trong database.
4. **Dữ liệu truyền trên mạng được mã hóa và xác thực máy chủ**, chống nghe lén/giả mạo.
5. **Quyền SQL tối thiểu**: API đọc đơn hàng không tự được phép xóa mọi bảng.
6. **Có log/alert/khả năng phục hồi** khi endpoint, DNS, key, certificate hoặc policy thay đổi.

Các lớp này bổ sung cho nhau:

~~~mermaid
flowchart LR
    APP[Application / worker] --> EGRESS[Outbound route / VNet integration]
    EGRESS --> DNS[DNS resolves database FQDN]
    DNS --> PE[Private Endpoint IP or private VNet endpoint]
    PE --> DB[Managed relational database]
    APP -. TLS / certificate validation .-> DB
    APP -. Entra token or database credential .-> DB
    DB --> AUTHZ[Database roles / GRANT / row-level rules]
    MON[Monitor / audit / alert] -. Observe .-> APP
    MON -. Observe .-> DB
~~~

**Private Endpoint không phải database user.** Nếu app có network path nhưng sai token/password hoặc không được `GRANT SELECT`, truy vấn vẫn thất bại. Ngược lại, một principal có quyền database nhưng không có đường mạng sẽ không thể tạo kết nối qua listener.

### 1.1. Ba câu hỏi trước khi mở cổng

| Câu hỏi | Ví dụ trả lời | Lớp kiểm soát |
|---|---|---|
| **Ai là client?** | Managed identity của orders-api-prod | Identity + SQL roles |
| **Client từ đâu?** | Subnet App Service VNet Integration | Routing, firewall, Private Endpoint |
| **Client kết nối tới đâu?** | `orders-sql.database.windows.net:1433` | DNS, TLS hostname, port, database name |

**Không dùng “IP private” như bằng chứng duy nhất rằng kết nối an toàn.** Cần chứng minh hostname được phân giải đúng, đường đi được phép, TLS xác minh đúng certificate và principal chỉ có quyền cần thiết.

## 2. Những dịch vụ database Azure không có cùng mô hình network

Từ “database Azure” dễ làm người học suy ra mọi dịch vụ có một nút **Private Endpoint** giống nhau. Thực tế, mỗi sản phẩm có mô hình triển khai, listener, DNS và firewall khác nhau.

| Dịch vụ | Endpoint/mạng thường gặp | Phương án private | Cần nhớ |
|---|---|---|---|
| **Azure SQL Database** | Logical server `<server>.database.windows.net` | **Private Link/Private Endpoint** cho SQL logical server; firewall/public network settings | Database nằm dưới logical server; Private Endpoint không đồng nghĩa một endpoint riêng cho từng database |
| **Azure SQL Managed Instance** | Instance nằm trong subnet chuyên dụng của VNet | **VNet-native connectivity**; một số tính năng public endpoint/private endpoint tùy mô hình và hỗ trợ hiện hành | Không áp y nguyên `sqlServer` Private Endpoint của Azure SQL Database |
| **Azure Database for PostgreSQL Flexible Server** | `<server>.postgres.database.azure.com` | **Private access (VNet integration)** hoặc **Private Link** với server ở mô hình public-access phù hợp/tính năng hỗ trợ | Hai mô hình private khác nhau; không coi chúng là một lựa chọn cấu hình có thể đổi tùy ý sau khi tạo |
| **Azure Database for MySQL Flexible Server** | `<server>.mysql.database.azure.com` | **Private access (VNet integration)** hoặc **Private Link** theo network mode và khả năng dịch vụ | DNS/firewall và điều kiện đổi connectivity khác Azure SQL |

**Đừng trộn** các lệnh `az sql server ...` với `az postgres flexible-server ...` hoặc `az mysql flexible-server ...`. Cả tên Private DNS zone, subresource ID, cổng và chế độ xác thực đều khác.

### 2.1. Phân biệt logical server và database

Ở **Azure SQL Database**:

~~~text
Azure subscription
  Resource group: rg-data-prod
    Azure SQL logical server: orders-sql-prod
      Public DNS name: orders-sql-prod.database.windows.net
      Database: ordersdb
      Database: reportsdb
      Private Endpoint connection: pe-orders-sql
    VNet: vnet-app-prod
      Subnet for application integration
      Subnet for Private Endpoints
    Private DNS zone: privatelink.database.windows.net
~~~

Private Endpoint trên SQL logical server giúp client được ủy quyền về mạng truy cập các databases trên server qua private path. **Nó không tự hạn chế client chỉ được login một database**; database users/roles và authentication vẫn là hàng rào kiểm soát quyền theo database.

### 2.2. VNet-native private access khác Private Link

**Private Link/Private Endpoint** tạo một **network interface với private IP trong VNet của client** để truy cập một tài nguyên dịch vụ tương ứng. Tài nguyên database vẫn được dịch vụ quản lý; không được “chuyển database VM” vào subnet của bạn.

**VNet-injected private access** của một số Flexible Server dùng **subnet được ủy quyền/delegated** và private DNS riêng cho server ngay từ mô hình triển khai. Nó là **cách đặt đường truy cập của server trong VNet**, không phải chỉ thêm một NIC Private Endpoint vào server public. Quy tắc subnet, DNS, HA và khả năng chuyển mode có thể khác nhau.

**Azure SQL Managed Instance** được triển khai vào subnet VNet theo mô hình riêng; không tạo SQL Database logical server Private Endpoint rồi coi đó là Managed Instance.

### 2.3. Quyết định theo sản phẩm, không theo thói quen

Trước khi thiết kế:

1. Xác định chính xác **resource type/SKU**, region và engine.
2. Kiểm tra **networking mode lúc tạo** và tính năng Private Link/VNet integration được hỗ trợ.
3. Xác định nguồn kết nối: App Service, Functions, AKS, VM, on-premises hay CI agent.
4. Xác định DNS resolver/Private DNS zone được dùng ở từng nguồn.
5. Chọn policy public access, firewall và database authorization.
6. Lập kế hoạch DR/failover, monitoring và chi phí private networking.

## 3. Public endpoint, service endpoint và Private Endpoint khác nhau thế nào?

### 3.1. Public endpoint + database firewall

Với public endpoint, database listener có tên miền công khai và đường vào thường được kiểm soát bằng database server firewall hoặc network rules theo dịch vụ. Ví dụ client được cho phép theo **public egress IP** của ứng dụng. Đây có thể là một thiết kế hợp lệ trong một số môi trường, nếu TLS/auth/firewall đúng, nhưng phạm vi mạng có thể rộng hơn giải pháp private.

Rủi ro:

- Egress IP thay đổi khi scale hoặc thay kiến trúc NAT khiến kết nối đột ngột bị firewall chặn.
- Người vận hành mở dải IP lớn quá mức để sửa lỗi.
- Public endpoint tiếp tục có đường truy cập Internet dù người dùng nghĩ database đã “private”.
- Một principal có credential bị lộ có thể cố truy cập từ những địa chỉ được firewall cho phép.

### 3.2. Service endpoint và VNet firewall rule

Một số Azure services hỗ trợ **service endpoints/VNet rules** để nhận diện traffic từ subnet. Với mô hình này, nguồn/tài nguyên dịch vụ vẫn có semantics **public service endpoint** của Azure, không nhất thiết có một **private IP database endpoint** ở subnet của client.

Không dùng các thuật ngữ **service endpoint**, **private endpoint** và **VNet integration** thay thế nhau. Những tính năng này có mục đích và tính tương thích riêng theo dịch vụ; nhiều nền tảng hiện đại ưu tiên Private Link khi cần đóng public exposure.

### 3.3. Private Endpoint qua Azure Private Link

Private Endpoint đưa một private IP vào subnet đã chọn và gắn với dịch vụ đích qua một private connection cụ thể. Khi DNS của ứng dụng resolve hostname database về IP đó, traffic có thể đi qua private network/Private Link thay vì địa chỉ công khai.

~~~mermaid
flowchart LR
    APP[Orders API trong VNet hoặc connected network] --> RESOLVE[DNS for orders-sql.database.windows.net]
    RESOLVE --> PRIV[Private IP 10.20.2.4]
    PRIV --> NIC[Private Endpoint NIC in subnet]
    NIC --> PL[Azure Private Link]
    PL --> SQL[(Azure SQL logical server)]
    PUBLIC[Public network endpoint] -. Disable when cutover validated .-> SQL
~~~

**Mốc quan trọng:** tạo Private Endpoint **không tự tắt public network access** của Azure SQL. Hai đường có thể tồn tại song song trong giai đoạn migrate. Khi cần private-only, phải kiểm chứng mọi workload đã chuyển xong rồi **vô hiệu hóa public network access** theo policy của database.

### 3.4. Bảng so sánh

| Tiêu chí | Public + firewall | Service endpoint/VNet rule | Private Endpoint |
|---|---|---|---|
| Địa chỉ đích ở client | Thường public service IP | Public service endpoint semantics | **Private IP trong VNet** |
| Kiểm soát nguồn | Public IP/database firewall | Subnet/VNet rule theo dịch vụ | Private endpoint, route/NSG theo hỗ trợ + identity |
| Private DNS zone | Không nhất thiết | Không nhất thiết | Thường cần để client dùng FQDN chuẩn |
| Đóng public exposure | Không nếu còn public access | Không mặc nhiên | **Cần vô hiệu hóa public access riêng** khi được hỗ trợ |
| Kết nối từ on-premises | Qua Internet/egress và firewall | Phụ thuộc thiết kế | Qua VPN/ExpressRoute/route + DNS thích hợp |
| Tác động chi phí | Egress/firewall theo kiến trúc | Theo dịch vụ | Private Endpoint, data processing, DNS/network |

Không có phương án nào tự tạo database user hoặc thực hiện SQL `GRANT`. Đó vẫn là nhiệm vụ của **database security**.

## 4. DNS là điều kiện để Private Endpoint hoạt động đúng

Một ứng dụng thường kết nối bằng **FQDN**, không bằng địa chỉ IP. Private Link cần DNS trả **private endpoint IP** cho client đúng mạng. Nếu DNS sai, kết nối có thể:

- Đi tới public endpoint và bị từ chối sau khi tắt public access.
- Timeout do route đến public/private không phù hợp.
- Đến một Private Endpoint ở VNet/region khác mà client không route được.
- Bị lỗi TLS khi developer dùng private IP thay hostname có trong certificate.

### 4.1. Luồng DNS tham chiếu cho Azure SQL Database

Giả sử:

~~~text
SQL server FQDN: orders-sql-prod.database.windows.net
Private Endpoint IP: 10.20.2.4
Private DNS zone: privatelink.database.windows.net
Private DNS A record: orders-sql-prod → 10.20.2.4
~~~

Client vẫn sử dụng **tên kết nối chuẩn** `orders-sql-prod.database.windows.net`. Với cách cấu hình thông thường, hostname này có chuỗi phân giải liên quan `orders-sql-prod.privatelink.database.windows.net` và Private DNS zone trả private IP trong mạng phù hợp. **Không cần sửa connection string thành hostname privatelink hoặc IP** chỉ để dùng Private Endpoint.

~~~mermaid
flowchart TD
    CLIENT[App asks DNS: orders-sql-prod.database.windows.net] --> DNS[Recursive DNS / Private DNS Resolver]
    DNS --> CNAME[Service DNS chain to privatelink name]
    CNAME --> ZONE[Private DNS zone privatelink.database.windows.net]
    ZONE --> A[A record 10.20.2.4]
    A --> CONNECT[TCP 1433 to Private Endpoint]
    CONNECT --> TLS[TLS verify hostname orders-sql-prod.database.windows.net]
    TLS --> AUTH[Entra or SQL authentication]
~~~

Đây là **mô hình logic**; resolver có thể dùng Azure-provided DNS, custom DNS, Azure DNS Private Resolver hoặc forwarders trong hub network. Thứ tự CNAME/record thực tế tùy dịch vụ. Điều quan trọng là câu trả lời cuối **từ runtime ứng dụng** trỏ tới private IP có đường định tuyến.

### 4.2. Các tên DNS phổ biến cần phân biệt

| Dịch vụ / mô hình | FQDN client thường dùng | Private DNS zone minh họa |
|---|---|---|
| Azure SQL Database qua Private Link | `<server>.database.windows.net` | `privatelink.database.windows.net` |
| PostgreSQL Flexible Server qua **Private Link** | `<server>.postgres.database.azure.com` | `privatelink.postgres.database.azure.com` |
| MySQL Flexible Server qua **Private Link** | `<server>.mysql.database.azure.com` | `privatelink.mysql.database.azure.com` |
| PostgreSQL/MySQL Flexible Server qua **private access VNet injection** | Server FQDN chuẩn của engine | Private DNS zone theo điều kiện cấu hình mô hình private access, **không tự suy ra dùng cùng zone Private Link** |
| Azure SQL Managed Instance | Instance FQDN riêng theo service | Theo mô hình VNet-native/endpoint và DNS của MI, **khác SQL Database logical server** |

**Lưu ý:** tên zone và hỗ trợ Private Link cần xác minh theo **engine, networking mode, tier và thời điểm triển khai**. Đặc biệt Flexible Server private access (subnet delegated) có quy tắc private DNS khác với Private Link trên server public-access. Không copy một zone từ tutorial Azure SQL rồi dùng cho PostgreSQL/MySQL.

### 4.3. VNet links và custom DNS

Một Private DNS zone chỉ hữu dụng với những mạng mà quá trình phân giải DNS có thể truy cập record phù hợp:

- **VNet link** cho phép Azure Private DNS zone phục vụ các VNet được liên kết.
- **Hub-spoke** có thể dùng Azure DNS Private Resolver hoặc DNS forwarder để các spokes/on-premises hỏi được records.
- **VPN/ExpressRoute** mang traffic IP; để giải quyết hostname private, vẫn cần **DNS resolution** ở phía on-premises.
- Custom DNS trên VNet có thể cần forward conditional zones về Azure-resolvable DNS.
- Không lấy kết quả `nslookup` trên laptop ngoài VPN làm bằng chứng rằng Pod AKS trong private network đang dùng DNS đúng.

### 4.4. Kết quả từ hai nơi có thể khác nhau

~~~text
Laptop bên ngoài VNet:
  nslookup orders-sql-prod.database.windows.net
  → public address/chain theo DNS ngoài

VM/Pod trong VNet có Private DNS link:
  nslookup orders-sql-prod.database.windows.net
  → 10.20.2.4 (ví dụ)
~~~

**Đây là split-horizon DNS hợp lệ** khi được cấu hình đúng. Một hostname phục vụ các câu trả lời DNS khác nhau theo môi trường resolver; không nhất thiết là lỗi. Hãy kiểm chứng **đường mạng dự kiến của từng consumer**.

### 4.5. Không ép connection string sang private IP

Khi app kết nối trực tiếp `10.20.2.4` thay vì server FQDN:

- TLS certificate của dịch vụ thường được cấp cho hostname, không phải private IP.
- Driver có thể báo **hostname mismatch** nếu bật xác thực certificate.
- IP của Private Endpoint có thể thay đổi khi tái tạo tài nguyên/network.
- Failover, zone và connection policy của dịch vụ có thể yêu cầu hostname chuẩn.

**Giữ FQDN chuẩn, sửa DNS thay vì bỏ xác thực TLS.** Không dùng `TrustServerCertificate=true`, `sslmode=disable` hoặc tắt certificate validation chỉ để che lỗi DNS/hostname.

## 5. Firewall: nhiều lớp, không phải một công tắc

Khi database không kết nối được, người vận hành thường hỏi “mở port 1433 chưa?”. Thực tế có ít nhất bốn lớp cần kiểm chứng:

| Lớp | Mục tiêu | Ví dụ |
|---|---|---|
| **Azure database public network settings** | Cho/từ chối kết nối qua public endpoint | Azure SQL `Public network access: Disabled` |
| **Database firewall rules** | Giới hạn client public IP/VNet-rule theo dịch vụ | Cho phép một dải egress IP cụ thể |
| **VNet NSG/UDR/Azure Firewall** | Kiểm soát đường đi và cổng từ app tới endpoint | Cho phép app subnet tới private endpoint TCP 1433 |
| **Database login/SQL permissions** | Xác thực danh tính và quyền truy vấn | Entra principal được `GRANT SELECT` |

**Firewall không thay SQL authorization.** Một port TCP mở chỉ cho phép tiến đến bước handshake/login; không phải giấy phép đọc dữ liệu.

### 5.1. Public network access trên Azure SQL Database

Nếu có Private Endpoint và ứng dụng đã được kiểm chứng dùng private IP, có thể cấu hình **Disable public network access** theo yêu cầu private-only.

- Nó giới hạn đường vào public endpoint của **SQL logical server** theo khả năng dịch vụ.
- Nó không thay đổi database users, passwords, schema hay TLS requirements.
- Nó không tự làm DNS của ứng dụng chuyển về private IP.
- Nếu ứng dụng đang kết nối từ on-premises/laptop/CI qua public endpoint, nó có thể **mất kết nối ngay**.
- Cần kiểm tra cách Azure control-plane operations/diagnostics/automation tương tác với database khi public access bị tắt.

### 5.2. “Allow Azure services and resources to access this server”

Trên **Azure SQL logical server**, tùy cấu hình firewall, có lựa chọn cho phép **Azure services and resources** truy cập qua public endpoint, thường liên quan firewall rule cho Azure-origin traffic. Đây là **ngoại lệ rộng**, không phải “chỉ App Service của chính mình”.

Nguy cơ: mở đường từ nhiều Azure resources nằm ngoài VNet/ownership của bạn, trong khi authentication database vẫn là lớp bảo vệ còn lại. Không bật tùy tiện để xử lý 40615/timeout; ưu tiên **Private Endpoint**, egress IP được kiểm soát và phân quyền theo principal.

**Nguyên tắc:** nếu cần private-only, hãy review/tắt các đường public/ngoại lệ không còn cần, thay vì tạo Private Endpoint rồi giữ những ngoại lệ rộng vì “phòng hờ”.

### 5.3. NSG và UDR với Private Endpoint

Private Endpoint là NIC trong subnet, nhưng khả năng áp **NSG policies/route table policies trực tiếp cho traffic Private Endpoint** phụ thuộc cấu hình **private endpoint network policies** của subnet và quy tắc Azure đang được hỗ trợ.

- Đừng mặc định gán NSG vào subnet thì **mọi** traffic tới Private Endpoint đều bị filter y như VM NIC.
- Kiểm tra subnet setting `privateEndpointNetworkPolicies` và chính sách hỗ trợ trước khi dùng NSG/UDR để bắt traffic qua firewall.
- Với UDR/forced tunneling, phải bảo đảm route tới private endpoint IP hợp lệ, không tạo asymmetric routing.
- Azure Firewall/NVA filtering cần được kiểm thử bằng packet flow và logs thực tế.
- Network security không thay TLS authentication và SQL permissions.

### 5.4. Cổng và kết nối

| Engine/dịch vụ | Cổng thường gặp | Chú ý |
|---|---|---|
| Azure SQL Database | TCP **1433** cho kết nối SQL thông thường | Connection policy `Proxy`/`Redirect` và đường kết nối có thể phát sinh port/route requirements khác, kiểm tra Azure SQL connectivity docs |
| Azure SQL Managed Instance | TDS port theo MI endpoint/model | Cổng và DNS có thể khác SQL DB; không copy rule 1433 một cách mù quáng |
| PostgreSQL Flexible Server | TCP **5432** | TLS và auth theo PostgreSQL/Entra config |
| MySQL Flexible Server | TCP **3306** | TLS/auth theo MySQL service/driver |

**Mở TCP port chưa đủ:** DNS phải resolve đúng, VNet phải có route, firewall phải cho phép traffic, TLS/hostname certificate hợp lệ, và database phải chấp nhận principal. Các HTTP health probes của app không chứng minh các điều kiện đó.

## 6. Thiết kế mạng trước khi tạo tài nguyên

Một thiết kế private database thường có **subnet riêng cho ứng dụng** và **subnet chứa Private Endpoints**. Không đặt Private Endpoint vào subnet đã được **delegated** cho một dịch vụ không hỗ trợ trộn resource types. Trước khi provision, cần xác minh CIDR, peering, route, DNS và ownership.

### 6.1. Ví dụ kiến trúc VNet

~~~text
Subscription: app-production
Resource group: rg-orders-prod

VNet: vnet-orders-prod (10.20.0.0/16)
  subnet-app (10.20.1.0/24)
    App Service outbound VNet Integration / VM/AKS source

  subnet-private-endpoints (10.20.2.0/24)
    NIC of pe-orders-sql: 10.20.2.4

Private DNS zone:
  privatelink.database.windows.net
  A record orders-sql-prod → 10.20.2.4
  Linked to VNet(s) that should resolve privately

Azure SQL logical server:
  orders-sql-prod.database.windows.net
  Database: ordersdb
  Private Endpoint connection approved
  Public network access disabled AFTER testing
~~~

Ví dụ địa chỉ `10.20.2.4` chỉ minh họa. Khi dùng nhiều hub/spokes, không được chọn VNet ranges trùng on-premises hoặc mạng khác. Azure cấp private IP theo cấu hình của Private Endpoint/subnet; lấy IP thực từ tài nguyên thay vì tự đoán.

### 6.2. Chọn nguồn kết nối

| Workload | Đường outbound cần thiết để tới Private Endpoint |
|---|---|
| **Azure VM** trong VNet | NIC/route từ subnet VM tới private endpoint IP |
| **AKS** | DNS của Pod/node, VNet routes/NSG và node/Pod network topology |
| **App Service** | **VNet Integration outbound** theo plan/tính năng; App Service private endpoint inbound không thay thế |
| **Azure Functions** | VNet Integration/outbound theo hosting plan và tính năng; kiểm tra scaling/network |
| **Azure Container Apps** | Environment VNet integration, routing, DNS và egress phù hợp |
| **On-premises** | VPN/ExpressRoute hoặc connectivity riêng, DNS forwarding và route tới private IP |
| **CI/CD hosted runner** | Hosted agent public không tự có đường vào VNet; dùng private/self-hosted runner nếu cần data-plane deploy/test |

### 6.3. Hai Private Endpoints không tự kết nối với nhau

Một Private Endpoint phục vụ database chỉ cung cấp **địa chỉ đến database** trong subnet. Nó không tạo:

- Đường **outbound VNet** cho App Service/Functions nếu workload chưa tích hợp VNet.
- Peering/VPN/ExpressRoute giữa mạng ứng dụng và mạng database.
- DNS links/forwarding ở các VNet khác.
- Role database cho workload identity.
- Firewall rule tự động cho một workload bất kỳ.

Với kết nối từ spoke A qua Private Endpoint ở spoke B, phải có **routing và DNS** giữa hai mạng. VNet peering có thể cho traffic liên lạc khi cấu hình phù hợp, nhưng **peering không tự liên kết Private DNS zone**.

### 6.4. Quản lý nhiều private endpoints và DNS

Một database server có thể phục vụ nhiều mạng/ứng dụng nếu thiết kế phù hợp. Khi có nhiều Private Endpoints cho cùng hostname ở các VNet/region khác nhau, cần đặc biệt cẩn trọng với Private DNS A records: **một zone chia sẻ sai có thể trả IP private không route được từ một VNet khác**.

Giải pháp có thể dùng DNS topology theo vùng/VNet, Azure Private DNS Resolver, forwarding có điều kiện và records quản lý rõ. Đừng tạo thủ công nhiều A records cho cùng FQDN trong một zone chung rồi mặc định mỗi client “tự chọn endpoint gần nhất”. Hãy test resolver từ từng nguồn.

## 7. Lab Azure CLI: tạo Private Endpoint cho Azure SQL Database

Lab tập trung **Private Endpoint cho Azure SQL Database logical server**, không dành cho Azure SQL Managed Instance hay Flexible Server. **Chỉ dùng subscription/resource group thử nghiệm được phép**. Lệnh tạo VNet, subnet, Private Endpoint và Private DNS zone có thể phát sinh phí; không chạy trên production nếu chưa có change approval.

Để tránh tạo database mới ngoài phạm vi, giả sử đã có:

- Một **Azure SQL logical server** và database `ordersdb` trong lab.
- Một tài khoản/managed identity có **Azure RBAC** đủ để tạo network resources và Private Endpoint connection, cùng quyền được approve connection theo resource/ownership.
- Một workload **bên trong VNet** hoặc VM thử nghiệm có SQL client/DNS tools.
- Quyền login và database read test an toàn; không cần SQL sysadmin chỉ để kiểm tra DNS.
- Chưa vô hiệu hóa public access cho đến khi đường private **được xác minh end-to-end**.

### 7.1. Đặt biến và xác minh subscription

~~~bash
az login

SUBSCRIPTION_ID="<lab-subscription-id>"
RG="rg-sql-private-lab"
LOCATION="southeastasia"
SQL_SERVER="<existing-sql-logical-server-name>"
SQL_DB="ordersdb"

VNET="vnet-sql-private-lab"
SUBNET_APP="snet-app"
SUBNET_PE="snet-private-endpoints"
PE_NAME="pe-sql-orders"
DNS_ZONE="privatelink.database.windows.net"
DNS_LINK="link-vnet-sql-lab"
DNS_ZONE_GROUP="sql-zone-group"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{id:id,name:name,tenantId:tenantId}" -o table
~~~

Các giá trị `<...>` là placeholder; phải thay bằng tài nguyên lab thật. Đảm bảo resource group chứa SQL server có thể **khác** resource group network. Nếu khác, cần khai báo hai biến `RG_SQL` và `RG_NETWORK` thay vì giả định mọi thứ chung một resource group.

Kiểm tra server thực có trong RG:

~~~bash
az sql server show \
  --resource-group "$RG" \
  --name "$SQL_SERVER" \
  --query "{id:id,fullyQualifiedDomainName:fullyQualifiedDomainName,publicNetworkAccess:publicNetworkAccess}" \
  --output json

az sql db show \
  --resource-group "$RG" \
  --server "$SQL_SERVER" \
  --name "$SQL_DB" \
  --query "{name:name,status:status}" \
  --output json
~~~

Nếu command trả `ResourceNotFound`, **không tự tạo một database production khác**; kiểm tra subscription, logical server name và resource group được giao.

### 7.2. Tạo VNet và subnet cho lab

~~~bash
az network vnet create \
  --resource-group "$RG" \
  --name "$VNET" \
  --location "$LOCATION" \
  --address-prefixes 10.20.0.0/16 \
  --subnet-name "$SUBNET_APP" \
  --subnet-prefixes 10.20.1.0/24

az network vnet subnet create \
  --resource-group "$RG" \
  --vnet-name "$VNET" \
  --name "$SUBNET_PE" \
  --address-prefixes 10.20.2.0/24
~~~

Đây là **CIDR minh họa**. Không chạy trong VNet hiện hữu nếu prefix `10.20.0.0/16` đã được sử dụng/overlap. Nếu tổ chức quản lý VNet qua Bicep/Terraform, dùng pipeline IaC thay vì tạo tay. Subnet app có thể cần delegation/integration settings riêng theo runtime, nhưng subnet Private Endpoint **không tự được delegated cho App Service**.

### 7.3. Lấy resource ID và tạo Private Endpoint

~~~bash
SQL_SERVER_ID=$(az sql server show \
  --resource-group "$RG" \
  --name "$SQL_SERVER" \
  --query id -o tsv)

az network private-endpoint create \
  --resource-group "$RG" \
  --name "$PE_NAME" \
  --location "$LOCATION" \
  --vnet-name "$VNET" \
  --subnet "$SUBNET_PE" \
  --private-connection-resource-id "$SQL_SERVER_ID" \
  --group-id sqlServer \
  --connection-name "sql-private-connection"
~~~

Với **Azure SQL Database logical server**, group/subresource thường là `sqlServer`. Không copy `sqlServer` cho PostgreSQL/MySQL/Managed Instance; phải kiểm tra loại resource và `az network private-link-resource list` hoặc tài liệu dịch vụ tương ứng.

Private Endpoint có thể tạo trong trạng thái chờ phê duyệt, tùy quyền và mô hình. Trước khi làm tiếp, xác minh **connection state = Approved** theo resource owner. Nếu Pending/Rejected, không nên coi Private Endpoint đã hoạt động.

~~~bash
az network private-endpoint show \
  --resource-group "$RG" \
  --name "$PE_NAME" \
  --query "{id:id,ipConfigs:ipConfigurations,connections:privateLinkServiceConnections}" \
  --output json
~~~

Tùy CLI/API version, các thuộc tính IP/approval có thể nằm trong cấu trúc response khác; xem JSON đầy đủ nếu query rỗng. CLI flags có thể thay đổi theo phiên bản, nên kiểm tra `az network private-endpoint create --help` tại môi trường triển khai.

### 7.4. Tạo Private DNS zone và VNet link

~~~bash
az network private-dns zone create \
  --resource-group "$RG" \
  --name "$DNS_ZONE"

az network private-dns link vnet create \
  --resource-group "$RG" \
  --zone-name "$DNS_ZONE" \
  --name "$DNS_LINK" \
  --virtual-network "$VNET" \
  --registration-enabled false
~~~

Với Private Endpoint đến dịch vụ PaaS, DNS zone thường dùng **manual registration off** vì A record cần được tạo/đồng bộ theo Private Endpoint DNS zone group, không phải VM hostname autoregistration.

### 7.5. Gắn DNS zone group vào Private Endpoint

~~~bash
DNS_ZONE_ID=$(az network private-dns zone show \
  --resource-group "$RG" \
  --name "$DNS_ZONE" \
  --query id -o tsv)

az network private-endpoint dns-zone-group create \
  --resource-group "$RG" \
  --endpoint-name "$PE_NAME" \
  --name "$DNS_ZONE_GROUP" \
  --private-dns-zone "$DNS_ZONE_ID" \
  --zone-name "sql-zone-config"
~~~

DNS zone group giúp quản lý DNS records của Private Endpoint phù hợp dịch vụ. Nếu tổ chức dùng central DNS zone ở resource group khác, **không tạo zone trùng trong từng app RG** chỉ để lệnh chạy. Dùng chính xác zone đã được team DNS quản trị, có quyền và peering/link thích hợp.

### 7.6. Kiểm tra DNS từ đúng nguồn ứng dụng

Sau khi DNS đã cấu hình và connection approved, đăng nhập một VM/Pod/worker **trong VNet có đường tới Private Endpoint**, rồi:

~~~bash
nslookup "$SQL_SERVER.database.windows.net"

# Trên Linux có nc:
nc -vz "$SQL_SERVER.database.windows.net" 1433
~~~

Trên Windows PowerShell:

~~~powershell
Resolve-DnsName "<server>.database.windows.net"
Test-NetConnection "<server>.database.windows.net" -Port 1433
~~~

Kỳ vọng:

- Tên `<server>.database.windows.net` phân giải tới **private IP** được gắn với Private Endpoint trong topo của bạn.
- TCP tới cổng phù hợp thông qua đường private thành công.
- SQL client với TLS và credential hợp lệ **login/query test** thành công.

**`nc -vz` hoặc `Test-NetConnection` chỉ kiểm tra TCP, chưa kiểm tra TLS hostname hoặc SQL login.** Bước tiếp theo phải dùng driver/SQL client có certificate validation và authentication thật.

### 7.7. Chỉ sau khi test PASS mới vô hiệu hóa public access

Trong lab/private-only architecture được phê duyệt:

~~~bash
# Hành động có thể cắt kết nối các public clients hiện tại:
az sql server update \
  --resource-group "$RG" \
  --name "$SQL_SERVER" \
  --public-network-access Disabled

az sql server show \
  --resource-group "$RG" \
  --name "$SQL_SERVER" \
  --query "{name:name,publicNetworkAccess:publicNetworkAccess}" \
  -o json
~~~

Lệnh thay đổi cấu hình public network access có thể có option khác theo CLI/API version; xem `az sql server update --help`. **Không chạy chỉ vì DNS riêng resolve đúng ở một VM**. Trước khi disable, kiểm chứng **tất cả** clients: App Service/Functions/AKS, on-premises, báo cáo, data migration tools, monitoring và CI jobs cần data-plane.

### 7.8. Kiểm tra fail-closed

Sau khi tắt public access:

1. Test **từ app/runtime private**: DNS private, TLS login, query read phù hợp phải thành công.
2. Test **từ nguồn ngoài không có VPN/private route**: không truy cập data-plane như trước.
3. Kiểm tra monitoring và jobs theo lịch, không chỉ thử một request.
4. Xác minh firewall exceptions/public IP rules không bị giữ lại không cần thiết theo policy.
5. Ghi resource IDs, private IP/DNS zone/connection status, change ticket và rollback plan.

**Fail-closed** ở đây là kết nối ngoài đường được phép phải thất bại, không phải cố sửa lỗi bằng cách tắt TLS verification hoặc cấp SQL admin password cho ứng dụng.

## 8. Kiểm chứng kết nối từ ba lớp: DNS, TCP và login/query

Không có một lệnh duy nhất xác nhận mọi thứ. Một cách kiểm thử đáng tin cậy gồm:

### 8.1. Lớp 1: DNS trả địa chỉ nào?

~~~bash
nslookup <server>.database.windows.net
~~~

Hỏi từ **container/VM/worker runtime thực**, không chỉ từ Azure Cloud Shell hoặc laptop quản trị. Azure Cloud Shell thường không nằm trong private VNet của bạn trừ khi được cấu hình môi trường riêng phù hợp.

Nếu DNS trả public IP, kiểm tra:

- Private DNS zone có đúng tên và A record đúng private endpoint không?
- VNet của nguồn có link/private resolver/forwarder phù hợp không?
- Custom DNS server có conditional forward zone về resolver đúng không?
- Resolver/cache ở container đã nhận cấu hình mới chưa?
- Có nhiều Private Endpoints cùng hostname và record trỏ tới IP của VNet khác không?

### 8.2. Lớp 2: có TCP route tới listener không?

~~~bash
nc -vz <server>.database.windows.net 1433
~~~

Nếu timeout, kiểm tra VNet integration, peering, NSG/UDR, firewall/NVA, private endpoint approval và đúng port. **Một timeout TCP thường không phải lỗi SQL password** — quá trình login còn chưa bắt đầu.

### 8.3. Lớp 3: TLS/auth/database query

Ví dụ với bản `sqlcmd` hỗ trợ Microsoft Entra authentication:

~~~bash
sqlcmd \
  -S "tcp:<server>.database.windows.net,1433" \
  -d "ordersdb" \
  -G \
  -Q "SELECT DB_NAME() AS DatabaseName;"
~~~

Cú pháp `-G`, cách chọn identity và encryption flags khác nhau giữa bản `sqlcmd` mới và bản driver/OS. **Xem trợ giúp phiên bản sqlcmd đang dùng**, sử dụng token đúng tenant và đảm bảo principal đã được tạo user/quyền trong database. Không bỏ kiểm tra certificate để có kết quả 2xx.

Nếu SQL login bị từ chối, kiểm tra database principal, Microsoft Entra admin/config, token audience, expiry và SQL grants. Nếu login thành công nhưng `SELECT` từ bảng báo permission denied, **network/TLS đã thông**, còn thiếu quyền SQL cụ thể.

### 8.4. Kết quả theo tầng

| DNS | TCP | TLS + login | Diễn giải |
|---|---|---|---|
| Sai | Thường lỗi hoặc đi sai đích | Thường lỗi | Sửa DNS/resolver trước |
| Đúng private IP | Timeout | Chưa thử được | Route/NSG/approval/port hoặc server listener |
| Đúng private IP | Thành công | Certificate error | Hostname/certificate chain/TLS driver |
| Đúng private IP | Thành công | Login failed | Token/password/user/Entra/database config |
| Đúng private IP | Thành công | Login OK nhưng query permission denied | Thiếu database GRANT/role |
| Đúng private IP | Thành công | Query OK | Một đường test đạt; chưa thay thế kiểm thử full workload |

**Cần kiểm thử ở production runtime:** một pod AKS thành công không bảo đảm App Service Function, CI runner và on-premises app cũng kết nối được; chúng có thể dùng DNS và route khác.

## 9. TLS: đường private vẫn cần xác thực máy chủ

**Private Link không làm TLS trở nên thừa.** Một private IP chỉ mô tả đường mạng; kết nối giữa driver và database vẫn cần chống đọc trộm, giả mạo và thay đổi dữ liệu trên đường truyền.

### 9.1. Ba câu hỏi trong một TLS handshake

1. **Encryption:** client và server có chọn được phiên bản TLS/cipher phù hợp không?
2. **Certificate trust:** client có tin cậy CA/chain của certificate do server trình bày không?
3. **Hostname verification:** certificate có phù hợp **FQDN mà client định kết nối** không?

Nếu chuyển connection string từ FQDN sang Private Endpoint IP, bước 3 thường thất bại. **Không đặt driver bỏ qua certificate validation để “sửa” hostname mismatch**; hãy sửa DNS và giữ FQDN chuẩn.

### 9.2. Azure SQL connection string (mẫu)

~~~properties
# Dành cho ứng dụng Java dùng Microsoft JDBC Driver for SQL Server
jdbc:sqlserver://<server>.database.windows.net:1433;database=ordersdb;encrypt=true;trustServerCertificate=false;hostNameInCertificate=*.database.windows.net;loginTimeout=15;
~~~

Đây là ví dụ về **TLS settings**, chưa bao gồm authentication mode. Trong nhiều driver phiên bản mới, encryption có thể có default hoặc giá trị `strict`/`mandatory` theo hỗ trợ; hãy dùng driver phiên bản được phê duyệt và kiểm tra tương thích với Azure SQL. Không hardcode password trong JDBC URL.

Với Microsoft.Data.SqlClient/.NET, một ví dụ cấu hình:

~~~text
Server=tcp:<server>.database.windows.net,1433;
Database=ordersdb;
Encrypt=True;
TrustServerCertificate=False;
Connect Timeout=15;
~~~

Trong code, thêm authentication Entra/managed identity theo driver và runtime. `Encrypt=True` mà `TrustServerCertificate=True` không đạt mục tiêu xác thực máy chủ đúng nghĩa.

### 9.3. PostgreSQL TLS settings

~~~text
host=<server>.postgres.database.azure.com
port=5432
dbname=ordersdb
sslmode=verify-full
sslrootcert=/path/to/trusted-ca-bundle.pem
~~~

Với PostgreSQL driver/libpq, `sslmode=verify-full` yêu cầu chain tin cậy **và** hostname hợp lệ. `sslmode=require` mã hóa nhưng không luôn mang cùng semantics hostname validation như `verify-full`; phải kiểm tra driver và chính sách chứng chỉ của Azure Database for PostgreSQL Flexible Server.

Certificate roots/intermediates có thể thay đổi theo lịch của Azure. **Không pin một leaf certificate hoặc một CA duy nhất mà không có rotation plan.** Hãy cập nhật CA bundle/trust store theo chính sách và kiểm chứng trước khi rollover.

### 9.4. MySQL TLS settings

Ví dụ với MySQL CLI/driver hỗ trợ xác thực danh tính server:

~~~bash
mysql \
  --host="<server>.mysql.database.azure.com" \
  --port=3306 \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca="/path/to/trusted-ca-bundle.pem" \
  --user="<db-user>" \
  --database="ordersdb"
~~~

Không đưa password thật vào `--password=...` trong shell history. Việc xác thực MySQL user/password hoặc Entra token tùy tính năng server và driver. **Chỉ chọn `VERIFY_IDENTITY` nếu trust store/CA và hostname được cấu hình đúng**; đừng hạ xuống `DISABLED` để chạy được qua Private Endpoint.

### 9.5. Kiểm tra chain và thời điểm hết hạn

Một sự cố production có thể xảy ra vì client dùng runtime/CA bundle cũ sau khi Azure thay certificate chain:

- Theo dõi phiên bản JDBC/.NET/ODBC/libpq/MySQL connector.
- Theo dõi CA trust store và lộ trình TLS minimum version của database.
- Kiểm thử certificate rotation trong staging gần production.
- Không gửi bí mật hoặc chuỗi kết nối chứa password vào diagnostic collector tùy tiện.
- Nếu TLS handshake lỗi, xem thông báo **chain/trust, hostname, protocol version** trước khi sửa firewall.

## 10. Identity và database permissions: ai được login và đọc dữ liệu?

Network chỉ quyết định **có đến được listener không**. Authentication xác định **principal là ai**; database authorization xác định principal **được làm gì**. Một kiến trúc dùng Private Endpoint nhưng ứng dụng kết nối bằng SQL admin password để thao tác toàn database vẫn có blast radius lớn.

### 10.1. Phân biệt ba loại quyền

| Quyền | Ví dụ | Không có nghĩa là |
|---|---|---|
| **Azure RBAC control plane** | Contributor tạo database server/Private Endpoint, Network Contributor cấu hình subnet | Tự được `SELECT` mọi bảng |
| **Entra/workload identity authentication** | Managed identity được cấp access token cho Azure SQL | Tự có SQL user/grants trong mọi database |
| **Database authorization** | Database user được `GRANT SELECT` trên schema `sales` | Tự tạo được Azure Private Endpoint hoặc sửa public network access |

Phải quản lý riêng ba lớp, có audit người/ứng dụng nào đổi permissions ở mỗi lớp.

### 10.2. Microsoft Entra ID với Azure SQL

Với Azure SQL Database, có thể cấu hình **Microsoft Entra authentication** và dùng managed identity của App Service/Functions/AKS workload làm principal. Quy trình tổng quát:

1. Tạo hoặc bật managed identity cho ứng dụng theo runtime phù hợp.
2. Cấu hình **Microsoft Entra admin** trên Azure SQL logical server theo governance.
3. Kết nối bằng principal đủ quyền để tạo database users từ external provider.
4. Trong **đúng database** của ứng dụng, tạo user đại diện Entra principal và cấp quyền tối thiểu.
5. Ứng dụng lấy access token bằng Azure Identity/driver; không lưu SQL admin password.
6. Kiểm tra token audience, tenant, refresh/rotation và SQL permissions từ runtime thật.

Ví dụ SQL dùng để minh họa trong `ordersdb` (cần principal/permission hợp lệ):

~~~sql
-- Lệnh DBA chạy trong ordersdb, tên MI là ví dụ.
CREATE USER [mi-orders-api-prod] FROM EXTERNAL PROVIDER;

GRANT SELECT ON SCHEMA::sales TO [mi-orders-api-prod];
GRANT INSERT, UPDATE ON SCHEMA::sales TO [mi-orders-api-prod];
~~~

**Không cấp `db_owner` hoặc `sysadmin` cho runtime chỉ vì gặp lỗi permission.** Cấp `SELECT/INSERT/UPDATE/EXECUTE` đúng objects/scopes theo chức năng. Một API chỉ đọc báo cáo nên dùng identity chỉ đọc riêng; không chung managed identity với migration pipeline.

**Nuance:** cách tạo Entra principals có thể cần điều kiện về tên, object ID, khả năng phân giải danh tính của SQL server identity và permissions trên Entra. Với trùng display names/service principals hoặc multi-tenant, có thể cần cú pháp định danh nâng cao/`WITH OBJECT_ID` theo tính năng hỗ trợ; xác minh với Azure SQL đang dùng thay vì đoán.

### 10.3. Token audience và lifetime

Đối với Azure SQL, token thường được yêu cầu cho resource/scope SQL như:

~~~text
https://database.windows.net/.default
~~~

**Đó là scope xin token**, không phải database hostname private endpoint. Nếu app xin token cho Azure Resource Manager rồi dùng để login Azure SQL, token audience không phù hợp và login có thể thất bại.

Một ứng dụng lâu dài nên dùng driver/SDK có **token refresh**, connection pool và retry hợp lý. Không lấy một token khi start app rồi tái sử dụng vĩnh viễn; token có thời hạn.

### 10.4. Password authentication khi chưa dùng được Entra

Một số kết nối/engine/client cũ vẫn dùng database user/password. Khi đó:

- Tạo **account riêng từng workload**, không dùng administrator account.
- Lưu secret trong Key Vault/secret store được phép, không trong Git hay Dockerfile.
- Rotation định kỳ theo chính sách, hỗ trợ giai đoạn chuyển tiếp an toàn.
- Giới hạn database grants và network exposure.
- Bật TLS/certificate verification; mật khẩu qua mạng private không thay encryption.
- Theo dõi login failures và audit changes; cấm log password/connection string đầy đủ.

**Đừng dùng Private Endpoint như lý do để giữ password yếu.** Network isolation là lớp phòng thủ bổ sung, không thay authentication.

### 10.5. Application-level authorization

Giả sử managed identity của `orders-api` có `SELECT` ở bảng Orders. Backend vẫn cần kiểm tra:

- Tenant/user của request có quyền đọc đúng `orderId` không?
- Role nghiệp vụ nào được sửa/hủy đơn?
- Có dùng row-level security, views/stored procedures để giới hạn dữ liệu không?
- Có chống SQL injection bằng parameterized queries không?
- Có audit thao tác nhạy cảm và hạn chế exposure của query logs không?

**Network private và managed identity không đảm bảo isolation dữ liệu giữa customers** nếu application query thiếu điều kiện tenant/resource. Đây là trách nhiệm của thiết kế ứng dụng/database.

## 11. Ứng dụng Java/JDBC và connection pool an toàn

Một ứng dụng Java kết nối Azure SQL Database cần phối hợp **DNS private**, **TLS driver settings**, **authentication** và **SQL permissions**. Lệnh SQL chạy được trên laptop của DBA không chứng minh service account của Java app có quyền hoặc VNet route đúng.

### 11.1. Ví dụ Java với Microsoft Entra Default credential

Ví dụ dưới đây minh họa sử dụng **Microsoft JDBC Driver for SQL Server** phiên bản hỗ trợ `ActiveDirectoryDefault` và các thư viện Azure Identity cần thiết. Java process phải có một credential nguồn hợp lệ (managed identity ở Azure, cơ chế đăng nhập phát triển trên máy local):

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;

public class AzureSqlConnectivityCheck {
    public static void main(String[] args) throws Exception {
        String host = System.getenv("SQL_HOST");
        String database = System.getenv("SQL_DATABASE");
        if (host == null || database == null) {
            throw new IllegalStateException(
                "SQL_HOST and SQL_DATABASE must be configured");
        }

        String url = "jdbc:sqlserver://" + host + ":1433;"
            + "databaseName=" + database + ";"
            + "encrypt=true;"
            + "trustServerCertificate=false;"
            + "loginTimeout=15;"
            + "authentication=ActiveDirectoryDefault;";

        try (Connection connection = DriverManager.getConnection(url);
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery(
                 "SELECT DB_NAME() AS db_name")) {
            if (result.next()) {
                System.out.println("Database: " +
                    result.getString("db_name"));
            }
        }
    }
}
~~~

Biến ví dụ:

~~~bash
export SQL_HOST="<server>.database.windows.net"
export SQL_DATABASE="ordersdb"
~~~

**Lưu ý kỹ thuật:** `ActiveDirectoryDefault` không có sẵn ở mọi đời Microsoft JDBC Driver. Nó cần driver/version và dependencies hỗ trợ Azure Identity phù hợp; kiểm tra driver release notes, cấu hình managed identity và runtime trước khi dùng. Một user Entra đã login Azure Portal **không tự có database user**; phải tạo SQL user và grants như phần 10.

**Không log connection string khi nó chứa credentials.** Với kiểu xác thực bằng token, không log raw access token hoặc SQL exception details có chứa thông tin nhạy cảm ở nơi công khai.

### 11.2. Kết nối qua connection pool

Trong API production, tạo SQL connection trên mỗi request mà không pooling có thể gây:

- TCP/TLS handshake và authentication overhead.
- Tăng latency khi request volume cao.
- Mở quá nhiều sessions/connections khi scale.
- Database resource exhaustion và login throttling.

Hãy dùng pool như HikariCP qua Spring Boot/Micronaut hoặc driver/pool được hỗ trợ, nhưng vẫn phải:

1. Chọn **maximum pool size theo số app instances** và connection capacity database.
2. Dùng connection validation/timeout hợp lý, không giữ connection hỏng sau failover.
3. Theo dõi active/idle/pending connections và SQL connection failures.
4. Thiết kế retry theo loại lỗi, backoff và transaction idempotency.
5. Đảm bảo token/credential được refresh theo driver hỗ trợ; đừng pin một token cố định khi khởi động pool.
6. Không bật infinite retries khi database/network đang outage.

### 11.3. Tính tổng connection budget

Giả sử có **8 replicas**, mỗi replica cấu hình pool tối đa **20 connections**:

\[
8 \times 20 = 160\ \text{connections tiềm năng}.
\]

Nếu database hoặc các backend phụ khác không đủ headroom, scale-out ứng dụng có thể gây hàng trăm login/queries đồng thời. Private Endpoint chỉ thay **đường mạng**, không tăng CPU/IOPS/connection limits của database.

### 11.4. Thao tác đọc đơn hàng với parameterized query

~~~java
// Phần này thực hiện trên Connection đã xác thực.
String sql =
    "SELECT Id, Status FROM sales.Orders WHERE Id = ?";

try (var statement = connection.prepareStatement(sql)) {
    statement.setString(1, orderId);
    try (var result = statement.executeQuery()) {
        while (result.next()) {
            // Chỉ xử lý dữ liệu của order đã được authorize.
        }
    }
}
~~~

Chỉ có network private và `PreparedStatement` vẫn chưa đủ nếu ứng dụng quên **kiểm tra tenant/customer ownership** trước truy vấn hoặc không lọc theo quyền. Parameterization chống SQL injection; authorization bảo đảm người dùng được phép truy cập resource.

## 12. PostgreSQL và MySQL Flexible Server: không copy cách làm Azure SQL

**Azure Database for PostgreSQL Flexible Server** và **Azure Database for MySQL Flexible Server** có hai hướng private connectivity quan trọng:

1. **Private access với VNet integration**: lựa chọn thiết kế server trong subnet được delegated và dùng private DNS theo mô hình đó.
2. **Private Link/Private Endpoint**: server ở loại network mode có hỗ trợ Private Link, với Private Endpoint trong VNet client và Private DNS zone dạng `privatelink.*` phù hợp.

Khả năng tạo hoặc thay đổi mô hình mạng, điều kiện region/SKU và hỗ trợ Private Link có thể thay đổi theo dịch vụ và phiên bản. **Không giả định một Flexible Server đã tạo ở private access mode có thể bật Private Endpoint bằng một click giống Azure SQL Database**, hoặc chuyển public ↔ private access VNet injection mà không cần tái tạo/migration.

### 12.1. PostgreSQL Flexible Server

Trong mô hình **private access VNet injection**:

- Server được liên kết với subnet có delegation phù hợp (`Microsoft.DBforPostgreSQL/flexibleServers` theo yêu cầu).
- Private DNS zone được cấu hình theo quy tắc Flexible Server; tên zone có thể là domain riêng kết thúc bằng `postgres.database.azure.com` theo yêu cầu hiện hành.
- Client trong mạng có route/DNS phù hợp kết nối qua FQDN PostgreSQL thông thường.
- Không dùng `privatelink.postgres.database.azure.com` như zone mặc định cho **mọi** loại private access.

Trong mô hình **Private Link** (khi supported):

- Server đáp ứng networking mode và điều kiện cho phép tạo Private Endpoint.
- Dùng Private DNS zone chuyên biệt cho Private Link, thường là `privatelink.postgres.database.azure.com`.
- App kết nối theo `<server>.postgres.database.azure.com`, cổng 5432, TLS verify-full với CA trust phù hợp.
- Public access/firewall policies cần được xem riêng; Private Endpoint không tự bảo đảm public path đã đóng.

Các lệnh **chỉ đọc** giúp xác định trạng thái:

~~~bash
az postgres flexible-server show \
  --resource-group "<rg>" \
  --name "<postgres-flexible-server>" \
  --output json

az postgres flexible-server firewall-rule list \
  --resource-group "<rg>" \
  --name "<postgres-flexible-server>" \
  --output table
~~~

Đọc network model thực tế trước khi tìm lệnh tạo Private Endpoint. Nếu server đã nằm trong delegated subnet theo private access mode, hãy sử dụng đúng network topology, không áp quy trình `az network private-endpoint create --group-id sqlServer`.

### 12.2. MySQL Flexible Server

Với **private access VNet integration**, MySQL Flexible Server dùng subnet delegated và private DNS theo quy định của service. Với **Private Link**, khi networking mode/tính năng hỗ trợ, dùng Private Endpoint riêng và zone thường là `privatelink.mysql.database.azure.com`.

~~~bash
az mysql flexible-server show \
  --resource-group "<rg>" \
  --name "<mysql-flexible-server>" \
  --output json

az mysql flexible-server firewall-rule list \
  --resource-group "<rg>" \
  --name "<mysql-flexible-server>" \
  --output table
~~~

Đây là lệnh **quan sát**, không chỉnh network. Trước khi thay public access/firewall, xác minh server đang ở mô hình nào. Dùng hostname `<server>.mysql.database.azure.com`, port 3306 và TLS validation bằng driver được hỗ trợ.

### 12.3. PostgreSQL/MySQL authentication không giống SQL Server

| Engine | Authentication thường gặp | Cần kiểm chứng |
|---|---|---|
| **Azure SQL** | SQL authentication hoặc Entra token/managed identity | SQL contained user/role và token audience SQL |
| **PostgreSQL Flexible Server** | PostgreSQL user/password hoặc Microsoft Entra authentication theo cấu hình | Entra server setup, role mapping/GRANT trong PostgreSQL, token audience và driver |
| **MySQL Flexible Server** | MySQL user/password hoặc Microsoft Entra authentication theo hỗ trợ | MySQL user/GRANT, role/driver plugin và token setup |

Ví dụ PostgreSQL dùng `GRANT SELECT ON TABLE ...` theo cú pháp PostgreSQL, **không copy** `CREATE USER [...] FROM EXTERNAL PROVIDER` của Azure SQL. Mỗi engine có SQL dialect, role model, certificate requirements và authentication plugin khác nhau.

### 12.4. Database firewall cho Flexible Server

Với server còn cho **public access**, firewall IP rules là một phần bảo vệ nguồn public theo tính năng. Với server **private access VNet-injected**, bài toán được giải chủ yếu bằng VNet/subnet/DNS/routing/NSG và database authentication. Với **Private Link**, cần xác minh Private Endpoint approval, DNS zone và chính sách public network access của server.

Không áp “Allow Azure services and resources” từ **Azure SQL logical server** sang mọi PostgreSQL/MySQL server mà không kiểm tra thiết kế/tính năng riêng; nếu có ngoại lệ broad Azure IP, phải hiểu phạm vi trước khi bật.

### 12.5. Azure SQL Managed Instance

Azure SQL Managed Instance có mô hình **VNet-native** và listener/điều kiện network riêng:

- Instance đặt trong subnet được ủy quyền/đáp ứng yêu cầu của Managed Instance.
- Kết nối từ VNet khác hoặc on-premises cần peering/VPN/ExpressRoute/DNS/routing phù hợp.
- Public endpoint, private endpoint và port connectivity (nếu được cấu hình/hỗ trợ) khác Azure SQL Database logical server.
- Không áp mặc định Private DNS zone `privatelink.database.windows.net` và group ID `sqlServer` cho MI.
- Kiểm tra yêu cầu subnet delegation, route table, NSG, SQL connection policy và port listener theo MI deployment cụ thể.

**Nguyên tắc chung:** hãy xác định **engine và network model trước**, rồi mới chọn lệnh/zone/port. Một hướng dẫn SQL Database không phải hướng dẫn phổ quát cho mọi Azure relational database.

## 13. Ứng dụng kết nối database qua mạng riêng: các mô hình runtime

### 13.1. App Service → Azure SQL Private Endpoint

~~~mermaid
flowchart LR
    USER[Web browser] --> APP[Azure App Service]
    APP --> VNET[App Service outbound VNet Integration]
    VNET --> DNS[Private DNS zone / resolver]
    DNS --> PE[SQL Private Endpoint 10.20.2.4]
    PE --> SQL[(Azure SQL Database)]
    APP -. Managed Identity token .-> SQL
    APP -. TLS verification .-> SQL
~~~

**Điểm thường nhầm:** **Private Endpoint trên App Service** là đường **inbound** để client truy cập website/app qua private network; nó **không thay VNet Integration outbound** cho app gọi SQL Private Endpoint. Cần VNet Integration theo plan/tính năng và egress/DNS đúng.

Kiểm chứng nên thực hiện từ **runtime**: ứng dụng tạo query read test dưới managed identity thực, log correlation/latency nhưng không log secret.

### 13.2. AKS Pod → PostgreSQL Flexible Server

~~~mermaid
flowchart LR
    POD[AKS Pod / Workload ID] --> CORE[AKS DNS + network]
    CORE --> ZONE[Private DNS resolution]
    ZONE --> SERVER[(PostgreSQL Flexible Server)]
    POD -. TLS verify-full .-> SERVER
    POD -. DB role / Entra token when configured .-> SERVER
~~~

Phải phân biệt:

- **Pod DNS** và cluster DNS/CoreDNS forwarding thực tế.
- CNI/network policy/NSG, routes từ node/Pod subnet tới database.
- Server đang dùng **private access VNet injection** hay **Private Link**.
- **Kubernetes service account/workload identity** để xin token Azure, khác quyền SQL/PG role.
- Replica count và connection pool để tránh quá tải database.

**Đừng test bằng một Pod debug chạy trong namespace đặc quyền rồi kết luận production Pod sẽ thông.** NetworkPolicy, service account, environment và DNS config có thể khác.

### 13.3. Azure Functions → MySQL Flexible Server

Một Azure Function có thể chạy theo plan/hosting type với những giới hạn VNet Integration, scaling và cold start khác nhau. Cần kiểm tra khả năng networking của plan trước khi triển khai database private-only:

1. Functions runtime có VNet integration hợp lệ.
2. DNS resolver cho `<server>.mysql.database.azure.com` trả private IP.
3. TCP 3306 và TLS verify identity thành công.
4. Credentials/Entra identity đủ SQL grants.
5. Scaling/concurrency không làm connection pool bùng nổ.
6. Retry logic không gây duplicate business transaction.

### 13.4. On-premises → Azure SQL qua VPN/ExpressRoute

Khi một ứng dụng trong data center cần truy cập Azure SQL Private Endpoint:

- Có private route qua **VPN/ExpressRoute** đến VNet chứa Private Endpoint.
- On-premises DNS conditional forwarder chuyển câu hỏi liên quan private database zone qua resolver có quyền truy cập Azure Private DNS.
- Firewall on-premises/NSG/NVA cho phép TCP theo dịch vụ.
- App vẫn dùng **server FQDN chuẩn** và TLS hostname verification.
- Có kiểm thử failover và đường DNS dự phòng.

**VPN/ExpressRoute mang packet, không tự tạo DNS record.** Một đường IP đã thông có thể vẫn lỗi chỉ vì on-premises resolver trả public address.

## 14. Migration từ public endpoint sang private-only không gián đoạn ngoài ý muốn

Thao tác nguy hiểm nhất thường là **tắt public network access trước khi tất cả ứng dụng đã chuyển sang đường private**. Một database có thể được dùng bởi nhiều clients ngoài API chính: báo cáo, batch jobs, DBA tools, data pipelines, monitoring hoặc một đối tác. Nếu một client bị bỏ sót, nó sẽ mất kết nối sau cutover.

### 14.1. Quy trình theo giai đoạn

~~~mermaid
flowchart TD
    INV[Inventory all clients and connections] --> PLAN[Design VNet, Private Endpoint, DNS, RBAC]
    PLAN --> BUILD[Provision PE + approve + DNS zone/link]
    BUILD --> TEST[Validate DNS / TCP / TLS / login from each runtime]
    TEST --> READY{All critical clients pass?}
    READY -->|No| FIX[Fix network/DNS/identity; keep public path controlled]
    FIX --> TEST
    READY -->|Yes| CUT[Approved change: disable public network access]
    CUT --> CHECK[Verify private success and public fail-closed]
    CHECK --> MON[Monitor jobs, application SLO, security logs]
    MON --> CLOSE[Document architecture and retire unused firewall exceptions]
~~~

Không cần “big bang” nếu hệ thống lớn. Tạo Private Endpoint và DNS trước, chuyển các workloads theo từng nhóm, quan sát sự ổn định và **chỉ cuối cùng** đóng public endpoint khi không còn client phụ thuộc.

### 14.2. Bảng inventory client

| Consumer | Runtime/mạng | FQDN/port | Identity | Đã kiểm tra private? |
|---|---|---|---|---|
| Orders API | App Service VNet Integration | SQL FQDN / 1433 | Managed identity | Cần test từ app |
| Invoice worker | Azure Functions | SQL FQDN / 1433 | Managed identity | Cần test từ worker |
| Data ETL | VM hoặc pipeline private runner | SQL FQDN / 1433 | Managed identity/service principal | Cần test theo lịch job |
| DBA operations | VPN/ExpressRoute | SQL FQDN / 1433 | Entra DBA role | Cần test VPN + DNS |
| Reporting | Power BI/data gateway hoặc service phù hợp | SQL FQDN / 1433 | Identity riêng | Cần xác minh topology |
| External integration | Third-party client | Theo hợp đồng | Principal riêng | Có thể cần thiết kế gateway/alternative |

Đừng coi một lệnh `az sql server firewall-rule list` là danh sách đầy đủ consumers; firewall rules cho IP/ranges không chứng minh ai thực sự đang gọi. Kết hợp application inventory, database audit/connection metrics, logs và team ownership.

### 14.3. Chuẩn bị rollback mà không giảm bảo mật tùy tiện

Một rollback plan phải ghi:

- Điều kiện phát hiện cutover lỗi (ví dụ API 5xx tăng, job không thể ghi SQL).
- Consumer/network nào mất kết nối, FQDN/DNS/route đang lỗi.
- Có thể **sửa DNS/route/identity** và phục hồi private connectivity không?
- Nếu buộc phải mở lại public access, ai có quyền phê duyệt, dải IP được giới hạn thế nào, thời hạn là bao lâu?
- Cách lưu audit và đóng lại ngoại lệ ngay sau khi xử lý.

**Không ghi runbook “bật Allow Azure services ngay khi timeout”.** Đây có thể mở phạm vi lớn hơn cần thiết. Trong incident, sửa DNS route có thể an toàn hơn cấp một firewall exception rộng; nếu phải break-glass, dùng thay đổi tối thiểu, có owner và expiry.

### 14.4. Không chuyển đồng thời mọi thứ

Trong cùng một change window, nếu bạn vừa:

1. Đổi database admin password;
2. Bật Private Endpoint;
3. Đổi custom DNS;
4. Tắt public access;
5. Nâng version JDBC driver;
6. Đổi database schema;

thì khi lỗi xảy ra rất khó phân biệt nguyên nhân. Hãy tách thay đổi thành các giai đoạn có thể kiểm chứng độc lập, có versioned IaC và rollback evidence.

### 14.5. DNS caching và client reconnect

Sau khi DNS private được cập nhật, một số client vẫn giữ DNS cache hoặc connection pool dùng IP cũ. Để cutover:

- Kiểm tra resolver TTL và khả năng refresh của runtime/JVM/OS.
- Đảm bảo connections mới sử dụng DNS được giải đúng.
- Đánh giá graceful pool recycle/restart theo change window.
- Không xóa endpoint cũ nếu còn các connections/clients chưa chuyển đổi.
- Nếu cấu hình network thay đổi, theo dõi lỗi nối lại sau failover/scale-out.

**Một lệnh nslookup mới đúng không chứng minh một connection pool lâu đời đã tạo connections mới qua private path.** Cần kiểm tra connection behavior từ ứng dụng và response/diagnostics.

## 15. Troubleshooting: phân biệt DNS, TCP, TLS, firewall và permission

Khi database không kết nối được, hãy điều tra theo thứ tự **đích → DNS → route/port → TLS → login → database operation** thay vì đổi ngẫu nhiên firewall và mật khẩu.

### 15.1. Bảng triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| DNS trả public IP trong VNet | Thiếu Private DNS zone/link hoặc resolver forwarding | `nslookup` từ runtime, zone A records, VNet link |
| DNS không trả kết quả | DNS server/forwarder lỗi, zone sai, policy chặn | Resolver config, conditional forwarding, DNS logs |
| DNS trả private IP nhưng TCP timeout | NSG/UDR/Firewall, PE pending, VNet không route được | Port test, PE approval, effective routes, subnet policies |
| Kết nối từ VM trong VNet được nhưng App Service lỗi | App Service chưa VNet Integration outbound hoặc dùng DNS khác | App VNet Integration plan, route, DNS từ runtime |
| Kết nối từ AKS debug Pod được nhưng production Pod lỗi | NetworkPolicy, service account, Pod DNS khác | Namespace/Pod policy, node/Pod routes |
| SQL error về client IP not allowed/public access | Client đi qua public endpoint thay vì PE | DNS, actual destination IP, SQL network state |
| TLS hostname mismatch | Client dùng private IP/privatelink alias sai, hostname cert không trùng | FQDN chuẩn, driver hostname verification |
| TLS certificate chain untrusted | Driver trust store cũ, CA bundle thiếu | Update CA bundle/driver, kiểm tra chain và expiry |
| SQL login failed | Entra token sai audience/tenant, user chưa tạo, password sai | Principal, token source, SQL authentication config |
| PostgreSQL `no pg_hba.conf entry` hoặc SSL mismatch | Security/config/transport mode không khớp | PG Flexible Server logs/network/TLS/role |
| Query permission denied | SQL GRANT/role thiếu dù network và login thành công | Kiểm tra effective database permissions |
| Kết nối bị ngắt khi failover | Connection pool stale, DNS/route, retry không phù hợp | Pool health, transient retry, failover topology |
| Rất nhiều timeout sau scale-out | Pool kết nối quá lớn, DB quá tải, SNAT/route | Database metrics, connection pool, runtime scale |
| Private Endpoint đã tạo nhưng status Pending | Chưa được database resource owner approve | PE connection state/approval workflow |
| On-premises resolve public IP | DNS forwarder chưa hỏi được Azure Private DNS | Private DNS Resolver, conditional forwarding, VPN route |
| CI job deploy SQL schema không vào DB private | Hosted runner không ở private network | Self-hosted/private runner, approved network path |

### 15.2. Runbook theo lớp

**Lớp 0 — Xác nhận scope:**

~~~bash
az account show \
  --query "{id:id,name:name,tenantId:tenantId}" \
  -o table

az sql server show \
  --resource-group "$RG" \
  --name "$SQL_SERVER" \
  --output json
~~~

Xác nhận server FQDN, database name, public access setting và Private Endpoint đúng resource ID. Không lấy một server cùng tên trong subscription khác làm căn cứ.

**Lớp 1 — DNS:** từ runtime bị lỗi, chạy `nslookup`/`Resolve-DnsName`. Kết quả cuối có trỏ đúng private endpoint IP không? Có custom DNS/hub-spoke forwarding không?

**Lớp 2 — Network/port:** TCP 1433/5432/3306 có thông? VNet integration/peering/Private Endpoint approval đúng? NSG/UDR/firewall logs báo deny không?

**Lớp 3 — TLS:** driver báo certificate mismatch, trust chain hay protocol version? Dùng **FQDN chuẩn**, cập nhật CA/driver, giữ certificate validation.

**Lớp 4 — Authentication:** token audience/issuer/expiry, SQL/PG/MySQL user, Microsoft Entra admin và login config có đúng?

**Lớp 5 — Authorization:** query có bị `permission denied` không? Database user có grants đúng schema/operations không?

**Lớp 6 — Performance:** session/pool count, CPU/IO, blocking, deadlocks, service saturation và retries có tăng không?

**Lớp 7 — Recovery:** sửa đúng lớp lỗi, test request/transaction nghiệp vụ, ghi root cause và đồng bộ IaC/documentation.

### 15.3. Một ví dụ sai rất phổ biến

~~~text
App reports:
  Connection timeout to orders-sql-prod.database.windows.net:1433

Developer assumes:
  "SQL password wrong, open firewall to all Azure services."

Correct investigation:
  1. nslookup inside App Service runtime → PUBLIC IP
  2. Check App Service outbound VNet Integration → not configured
  3. Configure proper VNet Integration and private DNS resolution
  4. TCP now reaches private endpoint
  5. TLS + Entra SQL login succeeds
  6. No broad public firewall exception needed
~~~

**Thông báo timeout ở lớp TCP không đủ để suy ra sai SQL credential.** Mỗi bước cần kết quả đo độc lập.

### 15.4. Phân biệt lỗi 401/403 Azure control plane với database login

Một người có thể gặp **403 Azure RBAC** khi tạo Private Endpoint, **SQL error 18456** khi login Azure SQL hoặc **permission denied** khi truy vấn bảng; chúng thuộc ba mặt quản trị khác nhau.

- **403 tạo tài nguyên:** kiểm tra Azure RBAC, deny assignments, policies, provider registration và Private Endpoint approval permissions.
- **Login failed:** kiểm tra token/password, server, database principal, Entra settings và driver authentication.
- **SELECT denied:** kiểm tra database GRANT/role, row-level policy và app permissions.

Đừng cấp Owner subscription cho runtime chỉ vì query SELECT bị deny; nó **không tự tạo** database SQL grants và làm tăng rủi ro bảo mật.

## 16. Quan sát database private connectivity

Một dashboard chỉ cho thấy database CPU 20% có thể bỏ sót lỗi hàng loạt do DNS hoặc Private Endpoint connection state. Cần log/metrics cả **network plane và database/application plane**.

### 16.1. Nguồn dữ liệu

| Nguồn | Tín hiệu cần xem | Lưu ý |
|---|---|---|
| **Azure SQL / PostgreSQL / MySQL metrics** | Successful/failed connections, CPU/IO/storage, sessions, availability theo engine | Tên metric/dimension khác từng dịch vụ |
| **Database audit/diagnostic logs** | Login failures, query activity và permission changes theo tính năng | Phải bật cấu hình phù hợp và hạn chế PII |
| **Private Endpoint connection state** | Approved/Pending/Rejected, NIC/IP, zone group | Tạo PE không có nghĩa kết nối Approved |
| **Private DNS zones/resolver** | A records, VNet links, DNS queries/forwarding | Kiểm chứng từ đúng VNet/client |
| **NSG/Firewall/Network Watcher** | Traffic allow/deny, routes và reachability | Logs/troubleshooting support tùy cấu hình và vùng |
| **App Insights/OpenTelemetry** | Database dependency duration, exception, connection timeout | Instrumentation/sampling do app thực hiện |
| **Azure Activity Log** | Ai đổi public access/firewall/Private Endpoint/RBAC | Không thay database-level audit |
| **Azure Cost Management** | Private Endpoint, DNS resolver, network và database costs | Tách owner/environment/region |

Đừng mặc định tạo Log Analytics workspace thì mọi database login event đã tự được thu thập. Phải cấu hình diagnostic settings/audit và kiểm tra schema/retention đúng, nhất là với PostgreSQL/MySQL.

### 16.2. Chỉ số nên có

1. **Database connection error rate** theo app instance/engine.
2. **TCP connect time** và **TLS handshake/login latency** nếu instrumentation hỗ trợ.
3. **DNS resolution failures/private-vs-public answer** từ synthetic probe trong VNet.
4. **Successful business transaction rate**, ví dụ tạo đơn hàng/đọc hồ sơ.
5. **Database active sessions, CPU, IO, deadlocks, connection pool wait**.
6. **Private Endpoint state** và changes qua Activity Log.
7. **SQL/PG/MySQL failed logins** và thay đổi quyền user/role.
8. **Unexpected public connectivity** sau private-only cutover (negative test).
9. **TLS certificate trust failures** và driver/runtime exceptions.
10. **RPO/RTO/failover readiness** qua thử nghiệm DR định kỳ.

### 16.3. Alert có owner và runbook

| Cảnh báo | Tác động | Phản ứng |
|---|---|---|
| Private Endpoint connection không Approved | App có thể không tới database | Kiểm tra PE approval/resource ownership |
| DNS private probe trả public IP | Traffic có thể đi public/bị chặn | Kiểm tra DNS zone/link/forwarding |
| Connect timeout tăng sau deploy | Route/NSG/firewall hoặc database quá tải | Phân tầng network rồi database |
| Login failures tăng, TCP vẫn thành công | Token/identity/password/SQL user | Kiểm tra Entra/SQL roles/driver |
| Query denied tăng | Quản trị SQL permissions thay đổi | Audit role grants và application release |
| Pool exhaustion | App scale hoặc DB capacity không phù hợp | Limit concurrency, pool sizing, DB capacity |
| Public access bị bật ngoài change window | Nguy cơ exposure | Security incident review, Azure Policy/remediation |

**Cảnh báo “database unavailable” phải phân biệt đường private và database service health.** Nếu DNS private lỗi, nâng cấp compute database không giải quyết nguyên nhân. Nếu database CPU 100% và connection pool wait tăng, mở thêm Private Endpoint cũng không giải quyết.

### 16.4. Logging an toàn

Một ứng dụng có thể log:

~~~json
{
  "service": "orders-api",
  "environment": "production",
  "dbEngine": "azure-sql",
  "dbHost": "orders-sql-prod.database.windows.net",
  "networkPath": "private-endpoint",
  "operation": "GetOrder",
  "durationMs": 47,
  "success": true,
  "correlationId": "req-c4a91"
}
~~~

**Không log password, access token, connection string chứa secret, bảng dữ liệu khách hàng hay kết quả SQL đầy đủ.** Field `networkPath=private-endpoint` trong ví dụ chỉ là nhãn ứng dụng; nếu muốn chứng minh network path thật, phải đối chiếu DNS/route/Private Endpoint logs chứ không chỉ tự ghi một chuỗi text.

### 16.5. Synthetic test từ bên trong và bên ngoài

Một chiến lược tốt có **hai phép kiểm tra riêng**:

- **Positive test trong VNet**: resolve private IP, TCP thông, TLS/Entra login/query được phép thành công.
- **Negative test từ ngoài private network**: sau khi public network access bị tắt, data-plane connection không đi qua Internet được.

Không dùng chính production customer records để làm synthetic transaction; tạo dataset test hoặc query chỉ đọc vô hại với permission giới hạn. Synthetic probe cũng cần dùng danh tính riêng và tránh lưu password/token trong monitoring.

## 17. High Availability, failover và Disaster Recovery

Một database private không tự trở thành **highly available**. Private Endpoint giải quyết đường kết nối mạng; HA/DR còn phụ thuộc database service tier, replicas, backup, region failover, DNS và khả năng ứng dụng nối lại.

### 17.1. Bốn lớp phải sẵn sàng khi failover

~~~mermaid
flowchart TD
    DR[Database failover / disaster recovery] --> BACKEND[Database primary / secondary available]
    BACKEND --> DNS[Correct listener FQDN and DNS answers]
    DNS --> ROUTE[Private Endpoint + VNet routes reachable]
    ROUTE --> AUTH[TLS + identity + DB permissions valid]
    AUTH --> APP[App reconnects, retries safely, resumes business processing]
~~~

Nếu database replica mới đang khỏe nhưng ứng dụng vẫn trỏ private IP của một endpoint cũ, business traffic có thể tiếp tục lỗi. **Không hardcode private IP** trong connection string; dùng listener FQDN được dịch vụ hỗ trợ và thiết kế Private Link/DNS cho cả đường primary và đường DR.

### 17.2. Azure SQL Database failover group

Azure SQL Database có thể sử dụng cơ chế **failover group/geo-replication** theo tier và khả năng hỗ trợ. Khi dùng failover group:

- Ứng dụng nên dùng **failover group listener** hoặc hostname được hỗ trợ theo kiến trúc thay vì tên máy chủ chỉ đúng cho primary hiện tại.
- Cần xem listener DNS và cách kết nối Private Endpoint cho **các SQL logical servers liên quan**.
- Không cho rằng tạo Private Endpoint cho primary sẽ tự tạo Private Endpoint/Private DNS/route tới secondary ở region khác.
- Kiểm tra danh sách VNet links/resolvers trong cả primary/secondary region và cách client phân giải listener.
- Đảm bảo Entra auth/database permissions, TLS cert trust và app network policies hoạt động ở đường failover.
- Thử failover có kiểm soát và xác định **RPO/RTO thực tế**, không chỉ dựa trên sơ đồ.

**Không đổi thẳng connection string sang private IP của secondary** khi failover. Dùng cơ chế listener DNS phù hợp và quản lý Private Endpoint/private DNS cho cả hai vùng theo hướng dẫn của dịch vụ.

### 17.3. PostgreSQL/MySQL HA và DR

Flexible Server có các khả năng **high availability, backup/PITR, replication hoặc geo-redundancy** tùy engine, SKU và region. Các tính năng này **không đồng nghĩa** networking và DNS của replica/standby được sao chép hoàn toàn sang mọi VNet.

Trước khi triển khai DR:

1. Xác định liệu deployment là private access VNet injection hay Private Link.
2. Kiểm tra subnet/zone/region của secondary và private DNS phù hợp.
3. Xác định FQDN/failover semantics mà driver cần dùng.
4. Đánh giá replication lag, tính nhất quán dữ liệu, read replicas và backup restore.
5. Tạo runbook cắt traffic/app config có thể quay lại.
6. Kiểm tra database role/password/Entra authentication sau restore/failover.

Không xây hệ thống dựa trên giả định read replica có thể tự động được promote và cùng hostname trong mọi chế độ. Hãy xác minh theo engine và loại replication đang dùng.

### 17.4. Connection pool và retry sau failover

Một pool có thể giữ stale TCP connections khi database đổi primary. Với app:

- Phát hiện transient connection errors.
- Cho phép pool loại connections không còn hợp lệ.
- Retry có **backoff/jitter và deadline**, không loop vô hạn.
- Với write transactions, cần **idempotency** và xử lý trạng thái commit không chắc chắn.
- Kiểm tra token refresh, DNS caching và connection string listener.
- Theo dõi service error rate sau failover và khả năng xử lý message/batch jobs.

**Đừng retry cùng một thanh toán/đơn hàng không có idempotency key** chỉ vì failover trả timeout; transaction có thể đã commit trước khi response mất.

### 17.5. Bảng diễn tập DR

| Tình huống | Cần kiểm tra | Bằng chứng |
|---|---|---|
| Database zone outage | HA tự phục hồi theo tier | Recovery time, app error rate |
| Primary region outage | DB failover + Private Link/DNS secondary | Listener resolved, query success từ từng network |
| Private DNS zone/link bị xóa | Resolver fallback và khả năng restore IaC | Private probe fail, IaC recovery |
| Private Endpoint bị rejected/deleted | Recreate/approve, NIC/IP/DNS update | PE status và TCP/TLS/login |
| Entra credential/role bị revoke | Identity recovery/least-privilege | Login audit và service owner approval |
| CA/certificate rollover | Trust store/driver update | TLS handshake pass trên staging/prod |
| VPN/ExpressRoute mất | On-prem connectivity alternative | User-facing impact, route restoration |

Kết quả DR cần ghi **thời gian thực đo**, người quyết định, dữ liệu có thể mất và các bước khôi phục. Một kiến trúc “hai region” chưa thử nghiệm là một giả thuyết, không phải bằng chứng RTO.

## 18. Hiệu năng và chi phí của private database connectivity

Private Endpoint thường được chọn vì **giảm public exposure, quản trị đường mạng rõ ràng và tích hợp private network**, không phải vì lời hứa mọi query sẽ nhanh hơn public endpoint.

### 18.1. Các thành phần chi phí

| Thành phần | Nguồn phát sinh |
|---|---|
| **Private Endpoints** | Chi phí resource/giờ và data processing theo mô hình giá vùng |
| **Private DNS zones / Resolver** | DNS zones, queries/links, resolver endpoints/transactions theo dịch vụ |
| **VNet connectivity** | VPN Gateway, ExpressRoute, peering, NAT/Firewall, NVA và egress |
| **Database compute/storage** | SQL DB vCore/DTU, MI compute, PostgreSQL/MySQL vCores, backup/storage |
| **App compute** | App Service plan, Functions, Container Apps/AKS/VM instances |
| **Monitoring** | Log Analytics ingestion, Azure Monitor/App Insights, retention |
| **DR** | Secondary database/region, replication, private networking ở vùng dự phòng |

Mức giá phụ thuộc **SKU/region/time**; bài học không cố định chi phí USD/GB hay USD/giờ. Trước khi quyết định, dùng Azure Pricing/Cost Management và dự toán throughput/backup/DR thực tế.

### 18.2. Private Link không khắc phục query chậm

Một query mất 12 giây do table scan/lock contention thường không nhanh hơn đáng kể chỉ vì kết nối qua Private Endpoint. Cần theo dõi:

- SQL query plans, indexes, blocking, deadlocks.
- Database CPU/IO/storage limits.
- Connection pool waits và số client sessions.
- Latency network giữa app region và DB region.
- TLS handshake/reconnect overhead.
- Số lần retry trên cả app/database driver.

Đặt app và database gần nhau về region/availability, dùng pool đúng và tối ưu câu lệnh sẽ ảnh hưởng performance nhiều hơn việc thay IP công khai bằng private trong nhiều tình huống.

### 18.3. Sizing network và connection pools

Nếu dùng một Azure Firewall/NVA để inspection toàn bộ data-plane traffic, cần:

1. Định cỡ throughput/concurrent connections.
2. Kiểm tra route symmetry, SNAT/connection tracking và TLS policy.
3. Bảo đảm đường Private Link/endpoint không bị chặn ngoài dự kiến.
4. Theo dõi chi phí xử lý traffic và logging.
5. Cân nhắc HA của firewall/forwarders; đừng tạo một điểm hỏng tập trung.

**Không gắn thêm firewall/NAT chỉ vì muốn bảo mật hơn** nếu đã có network controls đáp ứng threat model; từng lớp thêm chi phí, latency và operational risk.

### 18.4. Giảm chi phí mà không hạ security

- Dùng topology hub-spoke DNS/Resolver có owner rõ để tránh duplicate resource không cần thiết, nhưng **không** gom sai DNS khiến mất kết nối.
- Không giữ Private Endpoints, lab VNets, VMs, gateways và DNS resolvers rác sau khi học.
- Chọn database SKU/capacity theo p95 load, backup/DR và workload growth.
- Giới hạn log retention/sampling có kiểm soát, không thu plaintext sensitive queries.
- Đặt tags `owner`, `application`, `environment`, `costCenter` cho tài nguyên thích hợp.
- Dùng budgets/alerts và định kỳ review chi phí network + database + app theo cùng nghiệp vụ.

**Budget alert không phải hard spending cap.** Tắt database compute hoặc xóa Private Endpoint chỉ để giảm chi phí có thể làm mất dữ liệu/đứt ứng dụng; cleanup phải theo owner/change approval.

## 19. Infrastructure as Code và policy guardrails

Network private và database security rất dễ bị **configuration drift** nếu tạo Private Endpoint trong Portal rồi quên ghi lại DNS zone link, public network access hoặc RBAC. Production nên có **IaC** và pipeline được review.

### 19.1. Phân chia nguồn sở hữu

~~~text
Platform IaC (Bicep/Terraform/ARM):
  VNet/subnets/Private Endpoint
  Private DNS zone/link/zone group
  Azure Firewall/NSG/UDR/Private DNS Resolver
  Database resource/network settings
  Microsoft Entra identities, role assignments
  Diagnostic settings, alerts, tags

Database migration pipeline / DBA:
  Schema changes
  SQL users/GRANT and role model
  Backup/restore and DR

Application CI/CD:
  Workload runtime, managed identity binding
  Connection FQDN/environment settings
  Driver versions, TLS validation, pool config
  Smoke tests and SLO monitoring
~~~

Không để hai pipeline độc lập cùng ghi `publicNetworkAccess` hoặc một Private DNS A record theo hai “nguồn sự thật” khác nhau. Trước khi apply Terraform/Bicep, review các changes dự kiến, đặc biệt những thao tác **destroy/recreate Private Endpoint hoặc DNS zone link**.

### 19.2. Bicep minh họa ý tưởng Private DNS zone

Đoạn sau chỉ mô tả một zone/link và **không phải triển khai hoàn chỉnh** cho production:

~~~bicep
@description('Resource ID của VNet đã được phê duyệt.')
param vnetResourceId string

resource sqlPrivateZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.database.windows.net'
  location: 'global'
}

resource vnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: sqlPrivateZone
  name: 'link-approved-vnet'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnetResourceId
    }
  }
}
~~~

**Không apply đoạn này vào môi trường có zone do platform team sở hữu** nếu không có quyền/change approval. Trong thiết kế thực, cần quản lý Private Endpoint, DNS zone group, roles, NSG/firewall policies, diagnostics và môi trường nhiều VNet theo đúng dependency. Bicep resource API version/tính năng nên được kiểm chứng với Azure deployment target.

### 19.3. Azure Policy và kiểm soát public exposure

Tổ chức có thể dùng **Azure Policy** theo định nghĩa hỗ trợ để audit/deny/remediate cấu hình database:

- Public network access enabled trái quy định.
- Database thiếu diagnostic settings/auditing.
- TLS minimum version quá thấp.
- Private Endpoint/approved network không đáp ứng chính sách.
- Storage/Key Vault liên quan có network exposure rộng.
- Tags ownership/costCenter còn thiếu.

Azure Policy có các hiệu ứng/điều kiện phụ thuộc service resource schema; **đừng tuyên bố một policy generic tự cấm mọi database public** nếu chưa test trên từng loại SQL/PostgreSQL/MySQL/MI. Policy cũng không thay database role review hoặc application authorization.

### 19.4. IaC pipeline có bước kiểm chứng

~~~mermaid
flowchart LR
    PR[PR: Network and DB configuration] --> PLAN[Validate Bicep/Terraform + security review]
    PLAN --> APPLY[Apply approved changes]
    APPLY --> PE[Check Private Endpoint Approved]
    PE --> DNS[Test DNS from intended VNet]
    DNS --> TCP[Test TCP and TLS + database login]
    TCP --> CUT[Disable public path after sign-off]
    CUT --> TEST[Positive/negative connectivity + SLO]
    TEST --> AUDIT[Record configuration and changes]
~~~

Không cho pipeline tự động **vô hiệu hóa public access ngay khi vừa tạo Private Endpoint** nếu chưa có cơ chế xác minh toàn bộ client và đường rollback. Các phép test cần được chạy từ **mạng tương đương production**, không chỉ Azure CLI runner public.

## 20. Case study: bảo vệ Azure SQL cho ứng dụng thương mại điện tử

**Bối cảnh giả định:** Một hệ thống đặt hàng chạy trên Azure App Service và Azure Container Apps. API gọi Azure SQL Database, worker xử lý Azure Service Bus messages và lưu hóa đơn vào Blob Storage. Phần lớn resource nằm trong một subscription production; đội security muốn **ngăn truy cập SQL từ Internet**, hạn chế người có thể query database và giữ khả năng DR. App đang dùng public SQL endpoint được phép từ egress IP của App Service.

Các yêu cầu:

- Mọi runtime production kết nối SQL qua **đường private**; không mở exception “Allow Azure services” rộng.
- App Service/Container Apps có managed identity riêng; database chỉ cấp SQL permissions cần thiết.
- TLS luôn kiểm chứng certificate/hostname.
- Có CI/private runner thực hiện migration schema, không cần mở public access tạm thời mỗi lần release.
- Có kiểm thử end-to-end, audit, alert, backup và kế hoạch failover.
- Đội on-call có runbook giải quyết DNS/route/TLS/login mà không tắt bảo mật tùy tiện.

### 20.1. Kiến trúc mục tiêu

~~~mermaid
flowchart TB
    CUSTOMER[Web / mobile] --> WEB[App Service: orders-api]
    BUS[(Azure Service Bus)] --> WORK[Container Apps: invoice-worker]
    WEB -->|VNet Integration outbound| VNET[VNet app subnet / routing]
    WORK -->|VNet environment outbound| VNET
    VNET --> DNS[Private DNS Resolver + privatelink.database.windows.net]
    DNS --> PE[Private Endpoint NIC 10.20.2.4]
    PE --> SQL[(Azure SQL Database: ordersdb)]
    WEB -. Managed identity + verified TLS .-> SQL
    WORK -. Managed identity + verified TLS .-> SQL
    WORK --> BLOB[(Azure Blob Storage)]
    DBA[DBA / migration runner via private network] --> VNET
    MON[Azure Monitor + App Insights] -. Diagnostics .-> SQL
    MON -. Connection failures / traces .-> WEB
    MON -. Connection failures / traces .-> WORK
~~~

**Bảo vệ Blob/Service Bus là bài toán networking/identity riêng.** Có SQL Private Endpoint không có nghĩa mọi service khác trong sơ đồ cũng đã private-only.

### 20.2. Các quyết định thiết kế

| Chủ đề | Quyết định minh họa | Vì sao |
|---|---|---|
| **Database service** | Azure SQL Database | Dùng Private Link logical server + TLS/Entra |
| **App runtime** | App Service VNet Integration | Cho app outbound đến SQL PE |
| **Worker runtime** | Container Apps VNet environment | Cho worker truy cập private SQL |
| **DNS** | Central zone `privatelink.database.windows.net` và links/forwarders phù hợp | Giữ FQDN chuẩn, tránh mỗi team tạo zone trùng |
| **Network** | Subnet app và PE riêng; route/NSG được phê duyệt | Quyền sở hữu, chia vùng và kiểm soát flow |
| **Authentication** | Separate managed identities cho API và worker | Giảm blast radius khi app bị xâm nhập |
| **SQL privileges** | API `SELECT/INSERT/UPDATE` đúng schema; worker chỉ permissions cần | Không dùng database admin runtime |
| **Encryption** | TLS verify hostname, CA trust do driver quản lý | Bảo vệ kết nối ngay trên private network |
| **Cutover** | Tạo PE/DNS, test từng consumer, cuối cùng disable public | Tránh cắt off legacy clients |
| **Monitoring** | Synthetic probes + app metrics + SQL logs | Phân biệt network với login/performance |
| **DR** | SQL failover/backup theo tier và private routing đã test | Không chỉ có một Private Endpoint và gọi là HA |

### 20.3. Plan migration thực tế

**Ngày thiết kế (không thay runtime):**

1. Inventory tất cả clients SQL: API, workers, reporting, CI migration, DBA, scheduled jobs.
2. Ghi nhận FQDN, DB name, current firewall rules, egress IPs và SQL principals.
3. Review VNet address space, integration support và central DNS ownership.
4. Xác định change/rollback approvals, network and DB SLO.

**Ngày chuẩn bị (public path vẫn được kiểm soát):**

5. Provision Private Endpoint và approve connection.
6. Tạo/liên kết DNS zone đúng, kiểm tra A record cho server.
7. Bật VNet integration cho app/worker theo runtime phù hợp.
8. Kiểm thử DNS, TCP, TLS, login và read-only query từ từng runtime.
9. Test migration runner và DBA VPN access qua private path.
10. Bật monitoring trước khi cutover; lưu baseline latency/error rates.

**Ngày cutover (có change window):**

11. Xác nhận không còn client dựa trên public path; có bằng chứng owner sign-off.
12. Disable public network access trên logical server.
13. Thử positive từ private runtimes, negative từ bên ngoài.
14. Quan sát API error rate, worker queues, SQL logins, DNS/route và job schedules.
15. Thu hồi firewall exceptions public không còn cần theo chính sách.

**Sau cutover:**

16. Diễn tập failover/restore và kiểm tra đường private secondary.
17. Review connection pool sizes, token refresh và CA/certificate update strategy.
18. Lưu IaC state/change ticket, sơ đồ DNS/routing và runbook on-call.

### 20.4. Sự cố 1: app chạy nhưng database timeout

Sau khi tắt public access, orders-api trả HTTP 503. Một VM debug trong VNet kết nối SQL thành công, nhưng App Service lỗi:

~~~text
VM debug:
  SQL FQDN → 10.20.2.4; TCP 1433 OK; SQL query OK

App Service:
  SQL FQDN → public IP; connect timeout

Likely cause:
  App Service outbound VNet Integration hoặc DNS context
  chưa được cấu hình đúng.
~~~

**Hướng xử lý:** không mở lại “Allow Azure services” trước khi điều tra. Kiểm tra VNet Integration/route/DNS từ App Service runtime; sau khi DNS trả private IP và TCP thông, thử TLS/Entra login. Nếu sự cố nghiêm trọng cần break-glass, chỉ mở đường có phạm vi nhỏ, thời hạn/approval rõ ràng rồi đóng lại.

### 20.5. Sự cố 2: private network OK nhưng SQL báo permission denied

Worker invoice-service dùng managed identity `mi-invoice-prod`, resolve/private TCP/TLS thành công, nhưng `INSERT` vào bảng `sales.Invoices` bị từ chối.

**Hướng xử lý:** kiểm tra SQL user/GRANT trong `ordersdb`, không đổi NSG/Private Endpoint vì tầng network đã thông. DBA chỉ cấp `INSERT` (và những quyền cần cho job) trên đối tượng/schema tương ứng, sau khi review; tránh gán `db_owner`.

### 20.6. Sự cố 3: failover SQL làm client không reconnect

Database failover sang region khác. Backend khỏe nhưng app JDBC pool giữ connections cũ, listener DNS/Private Endpoint cho secondary chưa được cấu hình. App báo timeout hoặc lỗi transient.

**Hướng xử lý:** dùng failover listener FQDN theo dịch vụ, thiết kế Private Endpoints/private DNS cho các logical servers liên quan, kiểm tra region route, DNS caching, pool health và retry có idempotency. Không hardcode IP của region cũ vào code/connection string.

### 20.7. Bài học từ case study

Một đường private **không phải** chỉ gồm một Private Endpoint. Nó là chuỗi có thể kiểm thử:

~~~text
Runtime → outbound VNet integration/route → private DNS
        → approved Private Endpoint → TLS verification
        → Entra/database login → SQL GRANT → business transaction
~~~

Nếu một mắt xích lỗi, phải sửa đúng lớp. “Disable public access” chỉ nên là bước **cuối của migration đã được kiểm chứng**, không phải bước đầu tiên.

## 21. Bài thực hành và câu hỏi tự đánh giá

**Đề bài:** Bạn nhận nhiệm vụ chuyển Azure SQL Database `inventorydb` từ public firewall-based connectivity sang private-only. Ba consumers là một App Service, một AKS worker và một công cụ báo cáo trong mạng on-premises. Database chứa hàng hóa và tồn kho; thao tác ghi sai có thể gây đơn hàng âm tồn.

### 21.1. Nhiệm vụ thiết kế

1. Vẽ kiến trúc App Service/AKS/on-premises, VNet, Private Endpoint, Private DNS Resolver, SQL database, Entra identity và Azure Monitor.
2. Giải thích Private Link/Private Endpoint khác **service endpoint** và public firewall rule như thế nào.
3. Xác định Private Endpoint đặt ở subnet nào, private IP do đâu cấp, và tại sao nó không tạo VNet Integration outbound cho App Service.
4. Chọn Private DNS zone đúng cho Azure SQL Database; mô tả cách resolver trên VNet và on-premises trả private IP.
5. Viết cách chứng minh client thực vẫn dùng FQDN chuẩn chứ không hardcode private IP.
6. Thiết kế kiểm soát firewall: public network access, Azure SQL “Allow Azure services”, NSG/UDR và DB role.
7. Phân biệt **Azure RBAC Contributor** với **SQL user và GRANT SELECT**.
8. Thiết kế managed identity riêng cho API chỉ đọc và worker có quyền cập nhật bảng inventory.
9. Chọn TLS settings cho Java/JDBC và giải thích `TrustServerCertificate=false`.
10. Liệt kê các bước Azure CLI để tạo Private Endpoint, DNS zone/link/zone group và xác nhận approval.
11. Lập matrix kiểm thử DNS/TCP/TLS/login/query cho từng consumer trước khi disable public access.
12. Đề xuất kế hoạch chuyển đổi từng giai đoạn, rollback có kiểm soát và owner approvals.
13. Nếu App Service resolve public IP sau cutover nhưng AKS resolve private IP, bạn kiểm tra những gì?
14. Nếu JDBC báo certificate hostname mismatch khi dùng `10.20.2.4`, xử lý ra sao?
15. Nếu TCP/TLS/login thành công nhưng SQL SELECT bị deny, cần thay gì?
16. Giải thích connection pools tối đa 15 connections/instance trên 12 app replicas tạo ra bao nhiêu sessions tiềm năng.
17. Đề xuất ít nhất sáu metrics/alerts cho private DB connectivity.
18. Mô tả cách tổ chức IaC, Azure Policy và diagnostic settings để tránh public access bị bật lại ngoài ý muốn.
19. Nếu SQL failover sang region secondary, những thành phần network/DNS/driver nào cần kiểm thử?
20. So sánh hướng private connectivity của Azure SQL với PostgreSQL Flexible Server dùng VNet-injected private access.

### 21.2. Thứ tự lab tham khảo

~~~text
PRECHECK
  - Confirm subscription, resource IDs, owner, DB engine/network mode
  - Collect all dependent clients, SQL credentials/identity and routes
  - Confirm private network ranges, DNS ownership, change plan

PREPARE
  - Create PE for Azure SQL logical server
  - Approve PE connection
  - Create/link private DNS zone and DNS zone group
  - Enable VNet egress for apps; connect on-prem VPN/DNS forwarder

TEST
  - nslookup SQL FQDN from each source → correct private IP
  - TCP port 1433 → success
  - TLS hostname/certificate verification → success
  - Entra login + least-privilege query → success

CUTOVER
  - Authorized change window
  - Disable public network access on SQL server
  - Positive test from private network
  - Negative test outside private network
  - Review application, database and security alerts

OPERATE
  - Save IaC and audit evidence
  - Rehearse DR and certificate/token rotation
  - Retire unused public firewall exceptions
~~~

### 21.3. Lời giải một số câu hỏi

**Câu 12 — vì sao cần inventory mọi consumer?** Nếu on-premises report vẫn dùng public SQL endpoint, disable public access sẽ làm báo cáo mất kết nối dù App Service/API vẫn hoạt động. Cần DNS forwarding/private route hoặc một cách tích hợp được duyệt.

**Câu 14 — xử lý lỗi TLS hostname mismatch?** Kết nối bằng `<server>.database.windows.net`, để DNS trả IP Private Endpoint; giữ certificate validation và cập nhật CA bundle/driver nếu cần. **Không** tắt hostname verification.

**Câu 15 — query permission denied?** Tầng network/TLS/login đã hoạt động; cần DBA review database user và `GRANT`, không mở NSG/firewall.

**Câu 16 — tổng pool potential:** 

\[
15\ \text{connections/replica} \times 12\ \text{replicas} = 180\ \text{connections}.
\]

Đây là giới hạn lý thuyết của pool theo cấu hình, chưa kể migration runners, admin sessions, background jobs. Cần thêm headroom, đo database sessions và tránh mở rộng app gây quá tải.

**Câu 20 — khác biệt engine:** Azure SQL Database logical server hỗ trợ Private Endpoint `sqlServer` + zone `privatelink.database.windows.net`. PostgreSQL Flexible Server trong mô hình private access VNet injection dùng **delegated subnet và private DNS riêng theo dịch vụ**, không phải cùng group ID/zone và không nhất thiết tạo Private Endpoint.

### 21.4. Bằng chứng thực hành cần có

| Bằng chứng | Ý nghĩa |
|---|---|
| Resource ID SQL logical server và PE | Đúng resource đích |
| PE connection Approved | Network link đã được duyệt |
| PE IP và Private DNS records/links | Resolver có dữ liệu private đúng |
| `nslookup` từ mỗi runtime | Client resolve đúng private IP |
| TCP test từ mỗi runtime | Có network reachability |
| TLS + Entra SQL query read test | Danh tính và kết nối an toàn hoạt động |
| Public negative test | Không còn đường public trái policy |
| Azure Activity Log/change ticket | Thay đổi public access có người/nguồn chịu trách nhiệm |
| App/business SLO | Ứng dụng vẫn phục vụ người dùng |
| Backup/DR evidence | Có khả năng phục hồi ngoài network path hiện tại |

Không lưu access tokens, passwords hoặc dữ liệu khách hàng thật trong báo cáo lab. Trường hợp test dùng synthetic data/SQL read-only phù hợp.

## 22. Checklist trước, trong và sau cutover database private

### 22.1. Trước triển khai

- [ ] Đã xác định chính xác engine: Azure SQL Database, Managed Instance, PostgreSQL Flexible Server hay MySQL Flexible Server.
- [ ] Đã xác minh SKU/networking mode/region hỗ trợ phương án private đã chọn.
- [ ] Có inventory **tất cả** ứng dụng, workers, DBA tools, reporting, CI và clients on-premises dùng database.
- [ ] Xác nhận subscription/resource group/resource IDs và ownership của database/network.
- [ ] CIDR VNet không overlap; có subnet phù hợp cho App Service/Functions/AKS và Private Endpoint hoặc delegated subnet.
- [ ] Private DNS zone được chọn đúng service/mode; không tạo zone trùng không cần thiết.
- [ ] Có kế hoạch VNet links, peering, hub-spoke DNS/Private Resolver và conditional forwarding.
- [ ] NSG/UDR/firewall rules có thiết kế được review, không mặc định PE traffic chịu chính sách giống VM NIC.
- [ ] Các danh tính Entra/managed identity và database principals/GRANT được tách theo workload.
- [ ] TLS driver configuration có hostname/certificate verification, trust store và rotation plan.
- [ ] Monitoring/diagnostics và synthetic test đã hoạt động trước khi thay public network access.
- [ ] Có change approval, rollback plan và DR/backup evidence.

### 22.2. Sau khi tạo Private Endpoint

- [ ] Private Endpoint connection **Approved**, không Pending/Rejected.
- [ ] Private Endpoint NIC/private IP đúng subnet và resource target.
- [ ] DNS zone A record/zone group/links đúng với topology của mỗi VNet.
- [ ] Runtime chính xác của từng consumer phân giải FQDN về private IP có route.
- [ ] TCP port đúng engine/connection policy thành công từ từng consumer.
- [ ] TLS certificate chain và hostname hợp lệ; không dùng `TrustServerCertificate=true` hay `sslmode=disable`.
- [ ] Entra/database user login thành công, permission đúng mức cần thiết.
- [ ] App end-to-end smoke/business tests đạt; p95/connection errors không xấu đi bất thường.
- [ ] CI/migration runner và DBA on-premises access đã được kiểm thử qua private network.

### 22.3. Khi vô hiệu hóa public access

- [ ] Có bằng chứng từng owner xác nhận không phụ thuộc public endpoint.
- [ ] Change window, person responsible và rollback criteria được ghi.
- [ ] Chỉ thay public access setting **trên resource đúng**, không đồng thời đổi database schema/cert/driver nếu tránh được.
- [ ] Positive test private query từ App Service/AKS/worker/DBA đạt.
- [ ] Negative test ngoài network private cho thấy data-plane public path không còn được phép.
- [ ] Các scheduled jobs/queues/reporting vẫn hoạt động.
- [ ] Không có broad firewall exceptions bị giữ lại ngoài policy.
- [ ] Monitoring alerts/dashboards hoạt động và có owner.
- [ ] IaC/source of truth đã ghi nhận trạng thái private-only, tránh drift.

### 22.4. Khi có sự cố

- [ ] Xác nhận đúng server FQDN/engine/networking mode/resource IDs.
- [ ] Kiểm tra DNS từ **runtime bị lỗi**, không chỉ máy cá nhân.
- [ ] Kiểm tra route/TCP trước khi chạm SQL credential.
- [ ] Kiểm tra TLS chain/hostname trước khi giảm security settings.
- [ ] Kiểm tra Entra token/user/SQL grants sau khi network đã thông.
- [ ] Kiểm tra database CPU/IO/pool capacity để phân biệt performance với network lỗi.
- [ ] Không bật “Allow Azure services” rộng hoặc cấp db_owner tùy tiện để sửa nhanh.
- [ ] Nếu break-glass thật sự cần, scope nhỏ, owner/expiry và audit đầy đủ.
- [ ] Sau recovery, xác minh business transactions và đóng ngoại lệ tạm.

## 23. Dọn dẹp lab và tránh phá hủy network/database đang dùng

Private Endpoint, Private DNS, VNet, VPN/Firewall/Resolver và database có thể tiếp tục phát sinh phí sau khi kết thúc lab. Tuy nhiên, **xóa nhầm một Private DNS zone hoặc Private Endpoint đang dùng chung** có thể khiến nhiều ứng dụng mất kết nối.

### 23.1. Trước khi dọn, kiểm kê tài nguyên

~~~bash
az account show --query "{id:id,name:name}" -o table

az resource list \
  --resource-group "$RG" \
  --output table

az network private-endpoint list \
  --resource-group "$RG" \
  --output table

az network private-dns zone list \
  --resource-group "$RG" \
  --output table

az sql server show \
  --resource-group "$RG" \
  --name "$SQL_SERVER" \
  --output json
~~~

Lệnh liệt kê ở trên **chỉ đọc**. Nếu private DNS zone được quản lý ở hub RG khác, nó sẽ không hiện trong danh sách lab RG; cần biết ownership/đường phụ thuộc trước khi xóa network resources. Cũng không dùng bất kỳ lệnh xóa nào với biến `RG` chưa được xác nhận.

### 23.2. Thứ tự quyết định cleanup

1. Xác nhận tất cả resources muốn dọn thuộc **lab disposable**, không có consumers thật.
2. Xác minh **database backup và dữ liệu test**; không xóa SQL logical server có database production.
3. Kiểm tra Private Endpoint nào thuộc riêng lab, zone nào là **shared central DNS**.
4. Kiểm tra VNet link nào được các VNet khác dùng; không xóa central zone/Private DNS Resolver do team platform sở hữu.
5. Nếu có CI/job/VM test, dừng consumer và chắc chắn không còn scheduled tasks dùng SQL.
6. Dọn đúng từng resource theo quy trình owner và quan sát rằng các môi trường khác không bị ảnh hưởng.
7. Review chi phí còn sót lại: database compute, PE hourly, DNS/Resolver, VPN/Firewall, monitoring/logs, backup.

Lệnh xóa **chỉ minh họa và được comment**:

~~~bash
# KHÔNG tự thực thi. Phải xác nhận đây là PE dành riêng cho lab.
# az network private-endpoint delete \
#   --resource-group "$RG" \
#   --name "$PE_NAME"

# Không xóa Private DNS zone nếu còn được VNet/PE khác dùng.
# Không xóa cả resource group nếu SQL/server hoặc network dùng chung.
# az group delete --name "$RG" --yes
~~~

**Không mặc định xóa Private Endpoint trước rồi database tự chuyển về public an toàn.** Nếu public access đã disabled, xóa PE có thể làm database mất đường kết nối duy nhất của các workloads. Phải có kế hoạch ngắt kết nối và resource ownership phù hợp.

## 24. Ghi nhớ

**Private endpoint, firewall và bảo vệ kết nối database** là một bài toán **nhiều lớp**. Private Endpoint đưa đường vào dịch vụ qua private IP; DNS giúp ứng dụng dùng đúng hostname; VNet routes/NSG/firewall kiểm soát đường mạng; TLS xác thực máy chủ và mã hóa; Entra/database login xác định principal; database GRANT/roles giới hạn thao tác trên dữ liệu.

Những nguyên tắc cần ghi nhớ:

1. **Đừng nhầm các kiểu private network:** Private Endpoint khác service endpoint và khác **VNet-injected private access**; Azure SQL, Managed Instance, PostgreSQL và MySQL có network models khác nhau.
2. **Giữ FQDN database chuẩn:** Private DNS phải trả private IP từ runtime cần kết nối; không hardcode Private Endpoint IP trong connection string.
3. **Private Endpoint không tự tắt public access:** trước tiên provision/approve/DNS/test, sau cùng mới disable public network access theo policy.
4. **Firewall có nhiều lớp:** public database firewall, NSG/UDR/network routing và SQL login/permissions không thay thế nhau.
5. **TLS vẫn bắt buộc:** verify CA chain và hostname, không tắt certificate validation để chữa lỗi DNS.
6. **Identity phải tối thiểu:** ưu tiên Microsoft Entra/managed identity khi hỗ trợ; Azure RBAC Contributor không đồng nghĩa SQL SELECT, và app runtime không nên dùng database admin.
7. **Kiểm thử từng tầng:** DNS → TCP → TLS → authentication → SQL authorization → business transaction.
8. **App runtime phải có đường outbound riêng:** App Service VNet Integration khác Private Endpoint inbound của App Service; AKS/Functions/on-premises có topology riêng.
9. **Chuẩn bị migration/DR:** inventory tất cả consumers, có cutover/rollback plan và kiểm tra failover listener/private networking secondary.
10. **Vận hành/FinOps:** theo dõi connection failures, DNS, SQL metrics, logs, network costs và source-of-truth IaC; không để broad public exceptions tồn tại vô thời hạn.

Một thiết kế database private chỉ được coi là hoàn tất khi có bằng chứng rằng **mọi workload được phép có thể resolve đúng FQDN, đi qua private route, xác minh TLS, login với đúng danh tính, thực hiện đúng quyền và phục hồi khi mạng/database thay đổi — còn những nguồn ngoài phạm vi bị chặn theo chính sách**.
