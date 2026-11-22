# Azure Database for PostgreSQL Flexible Server

> **Chương:** Cơ sở dữ liệu quan hệ  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

## Mục tiêu bài học

Sau bài học, bạn có thể:

1. Giải thích **Azure Database for PostgreSQL Flexible Server** là gì, phạm vi trách nhiệm của Azure và của nhóm phát triển/vận hành.
2. Phân biệt **Flexible Server**, PostgreSQL tự quản lý trên Azure VM và các lựa chọn database quan hệ khác theo yêu cầu ứng dụng.
3. Lựa chọn **compute tier, vCores, storage, IOPS, backup retention, availability zone** và cân nhắc chi phí.
4. Thiết kế **public/private network access**, VNet integration, Private DNS, firewall, TLS và xác thực bằng PostgreSQL hoặc Microsoft Entra ID.
5. Tạo và kiểm tra một server thử nghiệm theo quy trình được phép; kết nối bằng **psql** và **Java/JDBC**, tạo database, role, schema và giao dịch minh họa.
6. Hiểu **high availability (HA)**, zone-redundant/same-zone standby, read replica, backup, **point-in-time restore (PITR)** và giới hạn của từng cơ chế.
7. Vận hành PostgreSQL với metrics, logs, `pg_stat_statements`, index/query tuning, connection pooling, VACUUM, bảo trì và cảnh báo.
8. Chẩn đoán các lỗi DNS, TLS, firewall, RBAC, `max_connections`, replication lag, storage pressure và query chậm.
9. Thiết kế checklist production và bài thực hành bảo vệ dữ liệu, hiệu năng, sẵn sàng cao và ngân sách.

## 1. Bối cảnh: cần PostgreSQL được quản lý nhưng vẫn dùng SQL chuẩn

Một nhóm xây ứng dụng đặt hàng trên **Azure App Service** hoặc **AKS**, gồm API viết bằng Java/Spring Boot và cơ sở dữ liệu quan hệ:

- Dữ liệu `customers`, `orders`, `order_items` có quan hệ và cần giao dịch nhất quán.
- API cần truy vấn bằng **SQL**, index, foreign key và transaction.
- Khi ứng dụng tăng từ vài trăm lên hàng nghìn request/giây, DBA/SRE phải giám sát CPU, IO, số kết nối và query chậm.
- Dữ liệu cần backup, khôi phục tại thời điểm xác định, giới hạn truy cập mạng và bảo vệ thông tin đăng nhập.
- Doanh nghiệp muốn giảm công việc vá OS, cấu hình VM, xây lại server hỏng và tự vận hành toàn bộ PostgreSQL cluster.

**Azure Database for PostgreSQL Flexible Server** là dịch vụ PostgreSQL quan hệ được Azure quản lý, cho phép chọn tài nguyên compute/storage, phiên bản PostgreSQL được hỗ trợ và mô hình kết nối, cùng khả năng backup, HA và monitoring.

~~~mermaid
flowchart LR
    U["Người dùng"]
    G["Front Door / App Gateway\nnếu có"]
    APP["Ứng dụng Java\nApp Service hoặc AKS"]
    DNS["Private DNS\nđịnh tuyến mạng riêng"]
    PG["PostgreSQL Flexible Server\nprimary"]
    HA["HA standby\nkhi được bật"]
    B["Automated backups\nPITR"]
    MON["Azure Monitor\nLogs / Alerts"]
    U --> G --> APP
    APP --> DNS --> PG
    PG -.->|"HA replication"| HA
    PG -.-> B
    PG -.-> MON
~~~

Sơ đồ là **kiến trúc logic**, không ngầm khẳng định mọi server có HA standby hoặc mạng riêng sẵn. Khi không bật HA, không có standby HA tương ứng. Đường đi thực tế phụ thuộc public/private access, DNS, routing và network security.

### Khi nào phù hợp?

| Nhu cầu | Flexible Server có phù hợp? | Lý do |
| --- | --- | --- |
| Ứng dụng quan hệ cần PostgreSQL chuẩn | Thường phù hợp | SQL, transaction, indexes, extensions được hỗ trợ |
| Muốn Azure quản lý backup/patching | Phù hợp | Giảm việc tự vận hành máy chủ và storage nền |
| Muốn kiểm soát maintenance window, sizing, HA | Phù hợp theo cấu hình/tier/region | Linh hoạt hơn mô hình DB hoàn toàn cố định |
| Cần toàn quyền root/OS và mọi extension tùy biến | Không phải mặc định | PaaS giới hạn superuser, extension và filesystem |
| PostgreSQL cần logical replication/CDC | Cân nhắc | Phải kiểm tra phiên bản, cấu hình WAL/slot, quyền, limits |
| Rất nhiều kết nối ngắn từ serverless | Có thể phù hợp khi có pool | Cần PgBouncer/connection pooling và giới hạn connections |
| Hệ thống cần tương thích một phiên bản PostgreSQL cũ | Phải kiểm tra support matrix | Dịch vụ chỉ hỗ trợ các phiên bản theo lifecycle |
| Workload phân tích cực lớn, nhiều truy vấn quét | Cân nhắc chuyên dụng | Kiểm tra phân tích dữ liệu, replica và kiến trúc HTAP/warehouse |

**Managed database không có nghĩa ứng dụng tự an toàn, không cần backup test hoặc không thể gặp outage.** Cần thiết kế HA, kết nối, truy vấn và khôi phục theo RTO/RPO của nghiệp vụ.

## 2. Phân biệt Flexible Server với các mô hình PostgreSQL khác

### 2.1. Flexible Server và PostgreSQL trên Azure VM

| Tiêu chí | PostgreSQL Flexible Server | Tự cài PostgreSQL trên VM |
| --- | --- | --- |
| Hệ điều hành và PostgreSQL patching | Azure quản lý lớp dịch vụ theo lịch/chính sách | Đội vận hành tự quản lý |
| Backup/PITR | Tích hợp theo khả năng service/tier | Tự xây backup/WAL archiving/restore |
| HA | Có lựa chọn HA được dịch vụ quản lý | Tự thiết kế replication/quorum/failover |
| PostgreSQL superuser/OS root | Bị giới hạn theo managed service | Có thể tự toàn quyền |
| Compute/storage | Chọn tier/SKU/storage khả dụng | Chọn VM, disk, storage stack |
| Kết nối mạng | Public/private models của dịch vụ | VNet, NSG, OS firewall do đội quản lý |
| Extensions | Chỉ extensions được Azure cho phép/hỗ trợ | Linh hoạt hơn nhưng phải tự bảo trì |
| Monitoring | Azure Monitor + PostgreSQL tools | Azure VM metrics + PostgreSQL tools tự tích hợp |
| Khả năng tinh chỉnh kernel/OS | Hạn chế | Rộng hơn |
| Trách nhiệm vận hành | Shared responsibility | Nhiều trách nhiệm nằm ở đội vận hành |

### 2.2. Không nhầm Flexible Server với Azure SQL Database

- **Azure SQL Database** cung cấp hệ sinh thái SQL Server/T-SQL, drivers và tính năng tương ứng.
- **Azure Database for PostgreSQL Flexible Server** chạy PostgreSQL, dùng SQL/datatypes/extensions/driver PostgreSQL.
- API và mức tương thích của chúng khác nhau; không thể chỉ đổi hostname mà ứng dụng T-SQL tự chạy trên PostgreSQL.

### 2.3. Về thế hệ sản phẩm

Tài liệu cũ có thể nhắc **Azure Database for PostgreSQL Single Server**. Khi xây hệ thống mới, cần tập trung mô hình **Flexible Server** và lộ trình/migration của sản phẩm hiện hành; không dùng cấu hình Single Server cũ như mô hình chuẩn mới.

### 2.4. Shared responsibility

**Azure quản lý:** phần lớn hạ tầng nền, dịch vụ compute/storage, cập nhật phần mềm dịch vụ, cơ chế backup/HA khi cấu hình.

**Khách hàng quản lý:** thiết kế schema, indexes, query, ứng dụng, credentials/identity, networking rules, encryption choices, monitoring/alerts, chi phí, test khôi phục, quyền người dùng và quản trị dữ liệu.

~~~mermaid
flowchart TD
    R["PostgreSQL workload"]
    AZ["Azure-managed:\nservice infrastructure, routine maintenance,\nbackup/HA mechanisms by configuration"]
    U["Customer-managed:\nSQL/schema, IAM, firewall, client TLS,\nconnection pooling, restore drill, SLO"]
    R --> AZ
    R --> U
~~~

Một lần query chậm do thiếu index hoặc transaction giữ lock lâu **không được Azure tự sửa** chỉ vì dùng PaaS.

## 3. Các thành phần của Flexible Server

### 3.1. Server, database, schema, role

~~~text
Azure subscription
  Resource group
    Flexible Server: pg-orders-lab
      PostgreSQL version: 16 (ví dụ, kiểm tra support)
      Host: pg-orders-lab.postgres.database.azure.com
      Port: 5432
      Databases:
        postgres
        ordersdb
          Schemas:
            public
            sales
          Roles:
            app_owner
            app_runtime
            readonly_analyst
~~~

- **Flexible Server** là tài nguyên Azure quản lý một PostgreSQL server instance/endpoint.
- **Database** là cơ sở dữ liệu logic bên trong server, có thể có nhiều databases.
- **Schema** là namespace chứa tables/views/functions trong một database.
- **Role** là principal của PostgreSQL, có thể mang quyền login hoặc quyền nhóm.
- **PostgreSQL administrator** dùng để cấu hình ban đầu, **không nên dùng làm tài khoản truy vấn cho ứng dụng production**.
- **PostgreSQL port** thường là **5432**.
- **FQDN** dạng `<server-name>.postgres.database.azure.com`, cần hostname thực của server.

### 3.2. Compute, storage và backup là những lựa chọn khác nhau

Flexible Server cho phép chọn compute tier/SKU, vCores, RAM theo SKU, storage provisioned, storage performance và tính năng availability/backup phù hợp.

| Tài nguyên | Tác động chính | Câu hỏi khi sizing |
| --- | --- | --- |
| vCores/CPU | Xử lý queries, parallelism, nền | Có CPU saturation không? |
| RAM/cache | Buffer cache, sorting, sessions | Query có spill disk hoặc cache miss nhiều? |
| Data storage | Dung lượng dữ liệu, indexes, WAL và growth | Có kế hoạch tăng trưởng/retention? |
| IOPS | Số thao tác I/O mỗi giây | Có workload đọc/ghi random nhiều? |
| Throughput | Số bytes/giây | Có quét bảng hoặc bulk load lớn? |
| Connections | Số kết nối đồng thời | App instances và pool sizing thế nào? |
| Backup retention | Cửa sổ PITR | Có đáp ứng mục tiêu recovery/compliance? |
| HA | RTO khi node/zone gặp lỗi | Cần standby và failover hay không? |
| Read replica | Tăng năng lực đọc, workload tách biệt | Chấp nhận replication lag? |

**Không giải thích IOPS = requests/giây của API.** Một request có thể đọc nhiều pages, tạo nhiều I/O hoặc được trả từ RAM cache.

### 3.3. Các compute tiers phổ biến

| Tier | Định hướng | Cảnh báo |
| --- | --- | --- |
| **Burstable** | Dev/test, workload nhỏ hoặc tải ngắt quãng | CPU credits/throttle và khả năng HA không giống tier khác |
| **General Purpose** | Phần lớn production OLTP | Cân bằng CPU/RAM, cost và hiệu năng |
| **Memory Optimized** | Workload cần RAM/cache lớn | Giá cao hơn, cần chứng minh bằng metrics |

**SKU/tier/version và khả năng HA, storage, availability zone thay đổi theo region/thời điểm.** Không dùng tên VM SKU cũ làm giả định tuyệt đối. Hãy tra danh sách SKU khả dụng trong subscription/region khi triển khai.

### 3.4. Thay đổi tài nguyên có thể gây gián đoạn

Scale vCore/tier, đổi storage/IOPS, bật HA hoặc thay network/parameter có thể cần **restart, failover hoặc giai đoạn gián đoạn** tùy thao tác. Cần thực hiện theo maintenance window và runbook, không coi mọi lựa chọn là dynamic/zero downtime.

Storage được cấp tăng lên theo policy/capacity nhưng **không nên giả định giảm storage provisioned trực tiếp sau khi tăng**. Tối ưu dữ liệu bằng VACUUM cũng không đồng nghĩa Azure sẽ tự giảm storage đã provisioned và hóa đơn.

## 4. Kiến trúc mạng: public access và private access

### 4.1. Public access với firewall rules

Flexible Server có mô hình truy cập công khai được **kiểm soát bằng firewall rules**. Server sử dụng FQDN; client ngoài VNet có thể kết nối khi public access được bật, nguồn nằm trong phạm vi được phép và PostgreSQL authentication/TLS hợp lệ.

~~~mermaid
flowchart LR
    D["Developer laptop / CI"]
    IP["Public client IP"]
    FW["Azure PostgreSQL\nfirewall rule"]
    PG["Flexible Server\npublic endpoint :5432"]
    D --> IP --> FW --> PG
~~~

**Firewall allowlist không thay cho authentication.** Không cấp dải toàn Internet chỉ để tiện test. Khi client dùng NAT/VPN, IP thấy ở dịch vụ có thể là **public egress IP**, khác IP private của máy.

Lưu ý một tùy chọn Azure có tên gần nghĩa “allow access from Azure services” ở một số mô hình firewall có thể mở quyền kết nối cho **rất nhiều nguồn từ Azure**, không chỉ subscription/tài nguyên của bạn. Không bật đại trà khi yêu cầu bảo mật chặt.

### 4.2. Private access qua VNet integration

Trong mô hình **private access (VNet integration)**, Flexible Server được tạo vào subnet đã **delegated** cho dịch vụ, cùng Private DNS Zone phù hợp.

~~~mermaid
flowchart LR
    APP["AKS / App Service\nVNet-integrated"]
    VNET["VNet + routing"]
    DNS["Private DNS Zone\nhostname resolution"]
    SUBNET["Delegated subnet\nMicrosoft.DBforPostgreSQL/flexibleServers"]
    PG["Flexible Server\nprivate access"]
    APP --> VNET --> DNS
    VNET --> SUBNET --> PG
~~~

Điều kiện quan trọng:

- Subnet được delegated đúng cho `Microsoft.DBforPostgreSQL/flexibleServers` và tuân thủ kích thước/điều kiện của dịch vụ.
- Private DNS Zone được gắn/liên kết với VNet đúng.
- Client app có route đến subnet server qua VNet, peering hoặc hybrid connectivity khi được hỗ trợ.
- NSG/UDR/firewall không chặn luồng cần thiết; có thể cần kiểm tra cả DNS và traffic quản trị của nền tảng.
- **Private DNS không tự cấp quyền đăng nhập PostgreSQL.** Vẫn phải có user/token và TLS.
- Không mặc định có thể đổi một server public thành private VNet integration **in-place**; quyết định network mode ngay từ thiết kế và kiểm tra tính năng migration/cutover được hỗ trợ.

### 4.3. Private Endpoint (Private Link) khác VNet integration

Một số cấu hình Flexible Server hỗ trợ **Private Endpoint/Private Link** theo mô hình public networking/điều kiện sản phẩm và thời điểm. Đây là **cách kết nối riêng khác** với việc tạo server trong delegated subnet.

Không gộp hai cách thành “cứ có Private DNS Zone là private”. Cần xác định server đang dùng **VNet-integrated private access** hay **public access có Private Endpoint hỗ trợ**, những giới hạn kết hợp giữa hai cơ chế, DNS zone, firewall và đường đi thực tế.

### 4.4. Private AKS không tự làm PostgreSQL private

Một cluster AKS có API server private **không bảo đảm** mọi outbound path đến PostgreSQL đều private. Ngược lại, một API server public vẫn có thể chạy Pods kết nối tới PostgreSQL qua VNet/private endpoint. Phải kiểm tra **data plane routing và DNS** của ứng dụng, không suy từ chế độ control plane AKS.

### 4.5. Chọn network model

| Yêu cầu | Hướng lựa chọn |
| --- | --- |
| Dev/test từ laptop đã biết egress IP | Public access + firewall IP cụ thể + TLS/auth |
| Production API và DB trong mạng doanh nghiệp | Private access/VNet hoặc Private Link được hỗ trợ |
| Truy cập từ on-premises | VPN/ExpressRoute, DNS forwarding và private routing |
| Không cho Internet tới DB | Private-only data path, kiểm tra public access disable/không dùng |
| Multi-VNet hoặc nhiều consumers | Peering/hub-spoke/DNS/routing, giới hạn theo phương án |
| Triển khai PaaS App Service/Functions | VNet integration của **client app** khi DB private |
| Cần kiểm toán truy cập | Firewall, identity, network logs, PostgreSQL audit/logging |

**Network access chỉ là một lớp** trong defense in depth: tiếp tục dùng TLS, role/privilege tối thiểu và monitoring.

## 5. Chuẩn bị môi trường và giới hạn an toàn cho lab

### 5.1. Tiền điều kiện

- Azure subscription và resource group **được phép tạo/sửa tài nguyên có tính phí**.
- Azure CLI `az` có extension/command group PostgreSQL Flexible Server tương thích.
- Công cụ `psql` và PostgreSQL client libraries.
- Kiểm tra region, supported PostgreSQL version và SKU.
- Chọn public IP allowlist hoặc subnet/DNS private theo yêu cầu.
- App identity/DB roles, TLS root CA và cách quản lý secrets.
- Dự toán chi phí compute/storage/backups/networking/monitoring.
- Kế hoạch dọn lab, không dùng resource group production chung.

### 5.2. Xác nhận Azure context

~~~bash
az login

az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Chỉ chuyển sang subscription đã được phân công.
az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-pg-flex-lab"
LOCATION="southeastasia"
PGSERVER="pg-orders-unique-lab"
ADMIN="pgadminlab"

az postgres flexible-server --help
az postgres flexible-server create --help
~~~

Không đặt tên server `pg-orders-unique-lab` nguyên văn nếu trùng; tên public DNS phải hợp lệ và duy nhất theo yêu cầu dịch vụ.

### 5.3. Bảo vệ credentials

Trong lab, nếu dùng PostgreSQL admin password:

- Sinh mật khẩu mạnh bằng công cụ quản lý bí mật và lưu tại vault.
- Không nhúng password vào Bash history, Git, Dockerfile hoặc ứng dụng.
- Khi có thể, dùng interactive input/secret injection; không dùng `--admin-password "password123"` trong tài liệu production.
- Sau khi server tạo, dùng app role riêng thay vì đăng nhập admin ở runtime.
- Đừng dán chuỗi kết nối/CA private key hoặc output chứa secrets lên ticket công khai.

**Bài học không tự chạy lệnh tạo hoặc xóa Azure resources.** Mọi command ghi bên dưới chỉ áp dụng trong môi trường được phép và có thể làm phát sinh phí.


## 6. Tạo Flexible Server và đọc lại cấu hình

### 6.1. Chọn đúng phương án

Ứng dụng production cần cách ly Internet thường phù hợp **private access** trong VNet đã được chuẩn bị. Với lab từ laptop có public egress IP cố định, có thể chọn **public access + firewall một IP** cùng TLS và user riêng.

Không mặc định mở `0.0.0.0/0` hoặc tùy chọn cho tất cả Azure services vào server. Cũng không tạo mới server có tính phí trước khi nhận được phê duyệt.

### 6.2. Azure CLI: ví dụ server public chỉ cho IP lab

~~~bash
az login
az account show --query "{name:name, id:id}" --output json
az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-pg-flex-lab"
LOCATION="southeastasia"
PGSERVER="pg-orders-unique-lab"
ADMIN="pgadminlab"
CLIENT_IP="<APPROVED_PUBLIC_EGRESS_IP>"

# Có thể phát sinh phí; chỉ chạy trên subscription/RG lab được duyệt.
az group create --name "$RG" --location "$LOCATION"

# CLI có thể hỏi mật khẩu tương tác nếu version hỗ trợ.
az postgres flexible-server create \
  --resource-group "$RG" \
  --name "$PGSERVER" \
  --location "$LOCATION" \
  --admin-user "$ADMIN" \
  --tier GeneralPurpose \
  --sku-name Standard_D2s_v3 \
  --version 16 \
  --storage-size 128 \
  --public-access "$CLIENT_IP"
~~~

**Mẫu lệnh cần đối chiếu trước khi chạy:** tên server phải duy nhất; SKU `Standard_D2s_v3` và PostgreSQL 16 chỉ dùng nếu region/subscription hỗ trợ. Xem `az postgres flexible-server create --help` và các giới hạn tier/version/storage. Nếu CLI không hỗ trợ prompt mật khẩu, dùng secret manager/portal theo chính sách; đừng đưa password vào command-line history.

**Không dùng lệnh trên để tạo database production private-only.** Public firewall allowlist không phải một lớp kiểm soát user identity thay cho PostgreSQL authentication.

### 6.3. Tạo server private VNet integration

Một quy trình:

1. Tạo/chọn VNet và subnet dành riêng Flexible Server.
2. Delegate subnet cho `Microsoft.DBforPostgreSQL/flexibleServers`; kiểm tra IP capacity và ràng buộc không dùng chung subnet sai mục đích.
3. Chuẩn bị Private DNS Zone và link với VNet theo yêu cầu dịch vụ.
4. Tạo Flexible Server với private network mode và lựa chọn đúng subnet/DNS.
5. Kiểm tra FQDN phân giải thành địa chỉ private từ client thật.
6. Kiểm tra TCP 5432, auth/TLS và không còn đường public trái thiết kế.

Ví dụ dạng tham số, **không tự chạy khi mạng chưa chuẩn bị**:

~~~bash
VNET="vnet-app-lab"
DELEGATED_SUBNET="snet-postgres"
PRIVATE_DNS_ZONE="private.postgres.database.azure.com"

az postgres flexible-server create \
  --resource-group "$RG" \
  --name "$PGSERVER" \
  --location "$LOCATION" \
  --admin-user "$ADMIN" \
  --tier GeneralPurpose \
  --sku-name Standard_D2s_v3 \
  --version 16 \
  --vnet "$VNET" \
  --subnet "$DELEGATED_SUBNET" \
  --private-dns-zone "$PRIVATE_DNS_ZONE"
~~~

**Đây là lựa chọn thay thế**, không phải lệnh thứ hai chạy lên server đã tạo public. Cú pháp CLI và prerequisites VNet/Private DNS có thể khác giữa các CLI versions. Cần xác minh trước deployment và tính năng Private Link/VNet integration của cấu hình.

### 6.4. Đọc lại server cấu hình

~~~bash
az postgres flexible-server show \
  --resource-group "$RG" \
  --name "$PGSERVER" \
  --query "{name:name, location:location, version:version, state:state, sku:sku, storage:storage, backup:backup, highAvailability:highAvailability}" \
  --output json

az postgres flexible-server db list \
  --resource-group "$RG" \
  --server-name "$PGSERVER" \
  --output table
~~~

Các lệnh `show` và `db list` là read-only. Lưu thông tin **resource ID, tier/SKU, region, zone, networking mode, backup window, HA status, owner và budget** trong runbook; không lưu password.

## 7. Kết nối bằng psql với TLS

### 7.1. DNS và TCP

~~~bash
PGHOST="${PGSERVER}.postgres.database.azure.com"

nslookup "$PGHOST"
nc -vz "$PGHOST" 5432
~~~

Trong private mode, chạy lệnh từ máy/VM/Pod có route và DNS đến private server. **DNS đúng không có nghĩa firewall, TLS và PostgreSQL role đều hợp lệ.**

### 7.2. TLS và xác minh server

- `sslmode=require` yêu cầu TLS mã hóa, nhưng mức xác minh server identity phụ thuộc client và CA configuration.
- `sslmode=verify-ca` xác minh CA/trust chain.
- `sslmode=verify-full` xác minh cả CA/trust chain lẫn **hostname FQDN**.
- `sslmode=disable` không phù hợp production và có thể bị server từ chối khi TLS enforcement bật.

Với root CA file đã được tổ chức phê duyệt:

~~~bash
CAFILE="/secure/certs/postgres-root-ca.pem"

# Password nhập tương tác hoặc từ secret provider phù hợp.
psql "host=$PGHOST port=5432 dbname=postgres user=$ADMIN \
sslmode=verify-full sslrootcert=$CAFILE"
~~~

Path `/secure/certs/postgres-root-ca.pem` là placeholder, không phải file được bài tạo sẵn. Không chuyển sang `sslmode=disable` để che lỗi CA/SNI.

### 7.3. Username của Flexible Server

Với PostgreSQL authentication, tên admin thường là **tên đã tạo**, ví dụ `pgadminlab`. Không mặc định dùng `pgadminlab@server` theo cách từ một số hướng dẫn **Single Server** cũ. Microsoft Entra authentication có cách cấp token/role riêng.

### 7.4. Kiểm tra session

Trong psql:

~~~sql
SELECT current_database(), current_user, version();
SHOW ssl;
SHOW max_connections;
SHOW TimeZone;

SELECT pid, usename, client_addr, state
FROM pg_stat_activity
WHERE pid = pg_backend_pid();
~~~

Lệnh riêng của psql:

~~~text
\conninfo
~~~

**Không in toàn bộ environment variables** để debug vì có thể chứa secrets.

## 8. Bài thực hành PostgreSQL: schema, SQL và roles

### 8.1. Tạo database

Đăng nhập bằng PostgreSQL admin có quyền tạo database:

~~~sql
CREATE DATABASE ordersdb;
~~~

Trong `psql`, chuyển database:

~~~text
\c ordersdb
~~~

Production nên triển khai thay đổi schema qua **Flyway/Liquibase** hoặc migration tool được review, không tùy tiện chạy DDL trong giờ cao điểm.

### 8.2. Bảng đơn hàng và indexes

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.orders (
    id            bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    external_id   text NOT NULL UNIQUE,
    customer_id   bigint NOT NULL,
    amount_minor  bigint NOT NULL CHECK (amount_minor >= 0),
    currency      char(3) NOT NULL DEFAULT 'VND',
    status        text NOT NULL
                  CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_orders_customer_created
    ON sales.orders (customer_id, created_at DESC);

CREATE INDEX idx_orders_status_created
    ON sales.orders (status, created_at DESC);
~~~

- `external_id UNIQUE` giúp **idempotency** khi cùng order event bị xử lý lại.
- `timestamptz` phù hợp lưu mốc thời gian, ứng dụng nên chuẩn hóa UTC.
- `amount_minor` lưu số tiền theo **đơn vị nhỏ nhất** trong hợp đồng; có thể dùng `numeric(p,s)` khi yêu cầu độ chính xác thập phân.
- Các indexes giúp một số truy vấn nhanh hơn nhưng tiêu tốn storage và chi phí ghi.

### 8.3. Một transaction minh họa

~~~sql
BEGIN;

INSERT INTO sales.orders (
    external_id, customer_id, amount_minor, currency, status
)
VALUES ('ORD-1001', 21, 12500000, 'VND', 'NEW')
ON CONFLICT (external_id) DO NOTHING
RETURNING id;

COMMIT;
~~~

Nếu lần gửi lại không trả `id` do unique conflict, code phải đối chiếu trạng thái nghiệp vụ trước khi coi là thành công. **Transaction PostgreSQL không bao gồm** side effect của Service Bus, Kafka publish, HTTP payment hoặc email. Có thể cần transactional outbox/idempotent consumer.

### 8.4. Tài khoản runtime quyền tối thiểu

Tạo role ứng dụng riêng, **không dùng admin trong ứng dụng**:

~~~sql
CREATE ROLE app_runtime LOGIN;

GRANT CONNECT ON DATABASE ordersdb TO app_runtime;
GRANT USAGE ON SCHEMA sales TO app_runtime;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA sales TO app_runtime;

GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA sales TO app_runtime;
~~~

Trong `psql`, đặt mật khẩu tương tác:

~~~text
\password app_runtime
~~~

Để grants áp dụng cho các bảng/sequence tạo trong tương lai bởi **role chạy lệnh**:

~~~sql
ALTER DEFAULT PRIVILEGES IN SCHEMA sales
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_runtime;

ALTER DEFAULT PRIVILEGES IN SCHEMA sales
    GRANT USAGE, SELECT ON SEQUENCES TO app_runtime;
~~~

**ALTER DEFAULT PRIVILEGES không tự sửa objects đã có và không áp dụng cho mọi owner roles.** Nên dùng migration owner có quyền rõ, và không cấp `CREATEROLE`, `CREATE DATABASE` hoặc superuser cho app_runtime.

### 8.5. EXPLAIN và indexes

~~~sql
SELECT id, external_id, status, amount_minor, created_at
FROM sales.orders
WHERE customer_id = 21
ORDER BY created_at DESC
LIMIT 20;

EXPLAIN
SELECT id, external_id, status, amount_minor, created_at
FROM sales.orders
WHERE customer_id = 21
ORDER BY created_at DESC
LIMIT 20;
~~~

`EXPLAIN (ANALYZE, BUFFERS)` thực thi query để đo thực tế. Cần thận trọng với lệnh ghi hoặc truy vấn nặng trên production; không tự chạy load tests lớn mà chưa được phê duyệt.

## 9. Kết nối Java/JDBC và connection pooling

### 9.1. JDBC URL có TLS

~~~text
jdbc:postgresql://pg-orders-unique-lab.postgres.database.azure.com:5432/ordersdb?sslmode=verify-full&sslrootcert=/secure/certs/postgres-root-ca.pem
~~~

Path CA phải tồn tại trong runtime/container và được PostgreSQL JDBC driver chấp nhận. Khi dùng truststore của JVM, thiết kế chứng chỉ/driver config phải được kiểm chứng, không giả định mọi image đã tin cậy server CA.

### 9.2. Spring Boot application.yml

~~~yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 30000
      max-lifetime: 1800000
  jpa:
    open-in-view: false
~~~

Các biến `DB_JDBC_URL`, `DB_USERNAME`, `DB_PASSWORD` phải được cấp qua environment/configuration/secret manager và tránh lộ trong Git/logs. Những con số Hikari là **khởi điểm minh họa**, không phải chuẩn mọi ứng dụng.

### 9.3. Java JDBC dùng PreparedStatement

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public final class OrdersReader {
    public static void main(String[] args) throws Exception {
        String url = System.getenv("DB_JDBC_URL");
        String username = System.getenv("DB_USERNAME");
        String password = System.getenv("DB_PASSWORD");
        if (url == null || username == null || password == null) {
            throw new IllegalStateException("Missing DB configuration");
        }

        String sql = "SELECT external_id, status, amount_minor " +
                     "FROM sales.orders WHERE customer_id = ? " +
                     "ORDER BY created_at DESC LIMIT ?";

        try (Connection conn =
                 DriverManager.getConnection(url, username, password);
             PreparedStatement stmt = conn.prepareStatement(sql)) {
            stmt.setLong(1, 21L);
            stmt.setInt(2, 20);
            try (ResultSet rows = stmt.executeQuery()) {
                while (rows.next()) {
                    System.out.printf(
                        "%s %s %d%n",
                        rows.getString("external_id"),
                        rows.getString("status"),
                        rows.getLong("amount_minor")
                    );
                }
            }
        }
    }
}
~~~

Yêu cầu dependency `org.postgresql:postgresql` tương thích với Java/driver đang sử dụng. Mẫu dùng `DriverManager` cho demo; ứng dụng web nên dùng `DataSource` và connection pooling.

### 9.4. Tính pool size theo số replicas

~~~text
AKS replicas:              12
Hikari maxPoolSize:        10
Potential app DB sessions: 12 × 10 = 120
~~~

Ngoài 120 sessions còn có worker, admin, migration và monitoring. Không đặt tổng connections sát `max_connections`; cần headroom khi failover/reconnect.

### 9.5. PgBouncer

**PgBouncer** giúp giảm số PostgreSQL backend connections khi có nhiều clients ngắn hạn. Flexible Server có tích hợp hoặc phương án sử dụng PgBouncer trong một số tier/cấu hình, nhưng phải kiểm tra **hỗ trợ/port/phiên bản và quyền** trước.

- **Session pooling:** ít thay đổi session semantics hơn, hiệu quả multiplexing có thể thấp hơn.
- **Transaction pooling:** tối ưu những transaction ngắn; cần kiểm tra tính tương thích với session variables, temp tables, advisory locks và prepared statements tùy driver/config.
- Pooler không giải quyết SQL chậm, thiếu index, deadlock hoặc thiếu IOPS.
- Không tự chuyển JDBC endpoint sang PgBouncer port khi chưa kiểm tra TLS, identity và ứng dụng.


## 10. High Availability: primary, standby và failover

### 10.1. Vì sao một primary có thể gián đoạn?

Flexible Server primary có thể bị ảnh hưởng bởi lỗi phần cứng, sự cố instance, bảo trì/restart và lỗi availability zone. Nếu mọi request đều đi tới primary, ứng dụng cần kế hoạch kết nối lại và xử lý transaction chưa hoàn tất.

Ở các tier/region hỗ trợ, Azure cung cấp **high availability (HA)** để giảm downtime. Cần bật và cấu hình HA; **không mặc định mọi server đều có standby**.

### 10.2. Same-zone và zone-redundant HA

| Cấu hình | Đặc điểm | Điều cần hiểu |
| --- | --- | --- |
| Không bật HA | Primary theo cấu hình cơ bản | Chịu ảnh hưởng khi instance/zone lỗi hoặc bảo trì |
| Same-zone HA | Standby trong cùng zone, khi hỗ trợ | Bảo vệ một số lỗi instance nhưng không phải outage toàn zone |
| Zone-redundant HA | Standby ở zone khác, khi hỗ trợ | Tách failure domain cấp zone; vẫn cùng region |

~~~mermaid
flowchart LR
    APP["Java API + HikariCP"]
    DNS["PostgreSQL server FQDN"]
    P["Primary\nZone 1"]
    S["HA standby\nZone 2 khi hỗ trợ"]
    MON["Azure Monitor"]
    APP --> DNS --> P
    P -.->|"HA replication"| S
    P -.-> MON
    S -.->|"Failover role"| DNS
~~~

HA có thể dùng **synchronous replication** theo service design để bảo vệ các transactions đã được xác nhận. Tuy nhiên **RPO/RTO, failover duration và mức hỗ trợ** phải được đối chiếu với SLA/tier/region; không viết cam kết vô điều kiện rằng “mọi sự cố RPO=0 và RTO=0”.

### 10.3. Failover tác động đến ứng dụng

Trong failover, các connections cũ có thể bị đóng. HikariCP phải loại connections hỏng, ứng dụng kết nối lại qua hostname chuẩn và xử lý transient exceptions.

Một tình huống khó: client gửi `COMMIT` nhưng mất kết nối trước khi nhận kết quả. **Không thể luôn biết transaction đã commit hay chưa** chỉ từ exception. Dùng `external_id UNIQUE` và idempotency key để retry an toàn.

Không tự bấm **force failover** trên production để kiểm chứng. Thử trong staging theo change approval, đo request error rate và thời gian phục hồi, xác minh connections, DNS, transaction state và logs.

### 10.4. HA không tự cung cấp read scale hoặc disaster recovery

Standby HA được dành cho availability, **không mặc định là read replica cho API gửi SELECT**. Với lỗi ảnh hưởng **cả region**, primary và HA standby có thể cùng bị mất. Hệ thống có yêu cầu DR cross-region cần kiến trúc khác và phục hồi được diễn tập.

## 11. Backup, PITR và Disaster Recovery

### 11.1. Automated backups

Flexible Server có khả năng backup được dịch vụ quản lý, kết hợp dữ liệu và log cần thiết cho các phương thức restore được hỗ trợ. **Backup và HA phục vụ mục tiêu khác nhau**:

- **HA:** phục hồi dịch vụ từ lỗi instance/zone theo cấu hình.
- **Backup/PITR:** khôi phục dữ liệu về mốc thời gian trong retention được hỗ trợ.
- **DR:** phục hồi khi lỗi vùng hoặc sự cố lớn hơn domain của HA.

Backup retention, geo-redundancy, chi phí lưu trữ và giới hạn restore khác nhau theo tier/region/configuration. Không dùng một số ngày mặc định từ tutorial cũ làm tiêu chuẩn production.

### 11.2. Point-in-time restore

Giả sử migration sai xảy ra lúc 10:25 UTC, dữ liệu đúng đến 10:23 UTC. Nếu backup window/WAL cho phép, yêu cầu **PITR về 10:23 UTC**.

~~~mermaid
flowchart LR
    BACK["Backup baseline"]
    WAL["Change logs / WAL"]
    POINT["Restore point\n10:23 UTC"]
    NEW["Restored Flexible Server\nendpoint mới"]
    CUT["Validate dữ liệu\nvà cutover"]
    BACK --> WAL --> POINT --> NEW --> CUT
~~~

PITR thường tạo **server mới**, không tự tua ngược primary hiện tại trong-place. Điều này ảnh hưởng:

- FQDN/connection strings, firewall/Private DNS.
- Compute/storage của restored server và chi phí phát sinh.
- Role/extension/configuration cần kiểm chứng.
- Cơ chế cắt traffic và tránh ghi vào cả hai server.
- Quy trình xác minh dữ liệu và rollback.

### 11.3. Restore runbook

1. Ngăn process hoặc migration tiếp tục gây hỏng dữ liệu.
2. Ghi thời gian UTC của lỗi và mốc khôi phục mong muốn.
3. Xác nhận restore point nằm trong retention.
4. Tạo restored server theo phương án Azure hỗ trợ, vào mạng/khu vực đúng.
5. Kiểm tra rows, constraints, extensions, users, grants và application behavior.
6. Chạy smoke tests không tạo side effects production.
7. Cutover database endpoint/secret/app config theo change window.
8. Theo dõi 5xx, transaction failures, connections và p95 latency.
9. Dọn server cũ/restored không dùng **chỉ khi đã được phê duyệt**.

**Không xóa primary rồi hy vọng backup tự khôi phục.** Với database lỗi dữ liệu, đôi khi cần khôi phục chọn lọc từ restored copy thay vì chuyển toàn ứng dụng.

### 11.4. Geo-restore, cross-region và RPO/RTO

Một số cấu hình hỗ trợ geo-redundant backup/geo-restore theo tier/region. Replication/backup xuyên vùng có thể **không đồng bộ**, nên không mặc định zero data loss. RTO còn gồm provisioning restored server, DNS/connection updates và validation.

Tham số thiết kế cần khai báo:

- **RPO (Recovery Point Objective):** mức mất dữ liệu theo thời gian chấp nhận được.
- **RTO (Recovery Time Objective):** thời gian gián đoạn tối đa mục tiêu.
- Phạm vi sự cố: process/VM, zone hay region.
- Data residency và compliance.
- Backup retention, frequency of restore drills.
- Owners và runbook cutover/rollback.

### 11.5. pg_dump và backup dịch vụ khác nhau

| Cách sao lưu/khôi phục | Mục tiêu |
| --- | --- |
| Automated backup/PITR | Khôi phục server theo thời điểm |
| `pg_dump` + `pg_restore` | Xuất/nhập dữ liệu/schema chọn lọc, migration |
| Read replica | Tăng throughput đọc, không sửa xóa nhầm |
| HA standby | Failover availability, không thay PITR |
| Cross-region recovery | DR theo hỗ trợ, có lag và RPO/RTO riêng |

`pg_dump` không tự cung cấp PITR; với database lớn cần xác minh version, network, storage, thời lượng backup/restore và consistency.

## 12. Read replicas, replication lag và CDC

### 12.1. Read-only replica

Một primary phục vụ giao dịch đặt hàng có thể bị báo cáo phân tích chiếm CPU/IO. **Read replica** ở các cấu hình hỗ trợ giúp đưa SELECT/reporting sang instance khác.

~~~mermaid
flowchart LR
    APP["Order write API"]
    P["Primary PostgreSQL\nRead / Write"]
    R1["Read replica\nReports"]
    R2["Read replica\nAnalytics"]
    REP["Reporting API"]
    ANAL["Analytics worker"]
    APP --> P
    P -.->|"Async replication"| R1 --> REP
    P -.->|"Async replication"| R2 --> ANAL
~~~

**Replica không phải endpoint ghi thứ hai.** App phải route writes tới primary và reads phù hợp tới read-only replica, có kế hoạch khi replica lag hoặc không khả dụng.

### 12.2. Read-after-write consistency

Sau `INSERT` trên primary, ứng dụng đọc ngay từ replica có thể chưa thấy row mới. Điều này là hệ quả của **asynchronous replication**, không nhất thiết là lỗi API.

Cách xử lý:

- Các requests cần **read-your-writes** đọc primary.
- Reporting/analytics chịu được độ trễ có thể đọc replica.
- Monitor replication lag và định nghĩa SLO.
- Nếu phải fallback về primary, kiểm soát tải tránh primary bị overload.
- Không chia một nghiệp vụ giao dịch cần nhất quán thành nhiều kết nối primary/replica tùy tiện.

### 12.3. Replica lag do đâu?

- Primary ghi WAL quá nhanh.
- Replica không đủ CPU, RAM, IOPS.
- Network/region latency.
- Query đọc nặng giữ tài nguyên trên replica.
- Những giới hạn replication, maintenance hoặc restart.

Tăng số replica không tự chữa query SQL chậm. Bảo vệ primary khi replica có sự cố bằng capacity budget và graceful fallback.

### 12.4. HA standby không giống read replica

| Thuộc tính | HA standby | Read replica |
| --- | --- | --- |
| Mục tiêu | Availability/failover | Scale SELECT và isolation báo cáo |
| Dạng replication | HA theo service | Thường async |
| Endpoint đọc ứng dụng | Không mặc định | Có read-only endpoint |
| Tự động failover | Theo HA mechanism | Phải kiểm tra cơ chế promotion/cutover riêng |
| Consistency | Theo HA SLA | Có thể stale theo lag |
| Có thay backup? | Không | Không |

### 12.5. Logical replication / CDC

PostgreSQL có **logical replication** và WAL decoding để tích hợp Change Data Capture. Trên managed Flexible Server, cần kiểm tra:

- PostgreSQL version/extension allowlist.
- Server parameters liên quan logical replication/WAL.
- Quyền cho replication user/publications/slots.
- Storage growth nếu replication slot không tiến bộ.
- Initial snapshot và xử lý schema changes.

**Logical replication không đồng nghĩa read replica vật lý hoặc HA.** Không bật logical slot thử nghiệm rồi bỏ mặc vì WAL có thể tích tụ.

## 13. Authentication: PostgreSQL roles, Microsoft Entra ID và secrets

### 13.1. Password authentication

Tài khoản PostgreSQL như `app_runtime` có quyền từ GRANT trên database/schema/tables/sequences. Nên:

- Tách admin, migration, runtime và readonly roles.
- Lưu passwords trong Key Vault/secret store.
- Rotate theo kế hoạch tương thích connection pool.
- Không đưa secret vào source, CLI history, Dockerfile hoặc log.
- Giới hạn log queries chứa literal dữ liệu nhạy cảm.

### 13.2. Microsoft Entra authentication

Flexible Server hỗ trợ **Microsoft Entra authentication** theo điều kiện service. Với ứng dụng Azure, managed identity/workload identity có thể giúp tránh mật khẩu PostgreSQL dài hạn.

Luồng khái quát:

1. Cấu hình Entra authentication và Entra administrator theo quy trình.
2. Map user/group/principal vào PostgreSQL role theo phương thức hỗ trợ.
3. Cấp PostgreSQL privileges đúng schema/tables.
4. Client lấy access token với audience/scope phù hợp.
5. Token được cung cấp cho driver theo auth flow hỗ trợ.
6. Thiết kế refresh token cho pool/reconnect; không giữ token hết hạn vô hạn.
7. Vẫn xác minh network, FQDN và TLS độc lập.

**Azure RBAC Contributor trên PostgreSQL Azure resource không tự cấp quyền SELECT trong PostgreSQL.** Azure control plane và PostgreSQL data plane là hai phạm vi phân quyền khác nhau.

### 13.3. Identity, network và TLS phải đồng thời đúng

| Lớp | Câu hỏi |
| --- | --- |
| Azure RBAC | Ai được tạo/sửa Azure server hoặc network? |
| Entra/PostgreSQL login | Principal có được server nhận diện để đăng nhập? |
| PostgreSQL GRANT | Có SELECT/INSERT vào đúng schema/table? |
| DNS/route/firewall | Client có đường tới cổng 5432? |
| TLS certificate | Hostname và CA có được xác minh? |
| Secret lifecycle | Credentials/token có rotation/refresh an toàn? |

Không sửa lỗi authorization bằng cách mở firewall rộng hoặc cấp admin role. Phải phân loại nguyên nhân trước.

## 14. Query tuning, indexes, VACUUM và thống kê

### 14.1. Các tín hiệu PostgreSQL quan trọng

- CPU, memory, IOPS, storage throughput và disk space.
- Active/idle connections, pool wait time, connection failures.
- Transactions/sec, lock waits, deadlocks.
- Query p95/p99, temp files, long transactions.
- Table/index bloat, autovacuum/analyze activity.
- Replica lag, WAL retention và failover events.

Một server chậm có thể do **SQL plan, lock, CPU, I/O hoặc connection storm**; không nên scale SKU trước khi đọc các chỉ số.

### 14.2. Truy vấn đọc thống kê

~~~sql
SELECT datname, numbackends, xact_commit, xact_rollback,
       blks_read, blks_hit
FROM pg_stat_database
WHERE datname = current_database();

SELECT pid, usename, state, wait_event_type, wait_event,
       now() - query_start AS elapsed,
       left(query, 120) AS statement_preview
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY elapsed DESC NULLS LAST
LIMIT 20;
~~~

`pg_stat_activity.query` có thể chứa literal dữ liệu, nên không đẩy toàn bộ query text lên ticket không được bảo mật. Quyền xem các trường thống kê phụ thuộc roles.

### 14.3. EXPLAIN và execution plan

~~~sql
EXPLAIN
SELECT external_id, status
FROM sales.orders
WHERE customer_id = 21
ORDER BY created_at DESC
LIMIT 20;

-- Chỉ chạy khi được phép: thực sự thực thi SELECT để đo.
EXPLAIN (ANALYZE, BUFFERS)
SELECT external_id, status
FROM sales.orders
WHERE customer_id = 21
ORDER BY created_at DESC
LIMIT 20;
~~~

Cần xem index vs sequential scan, estimated/actual rows, sorts, temp files và số buffer reads. `EXPLAIN ANALYZE` với SQL ghi có thể gây thay đổi dữ liệu; không tự chạy `EXPLAIN (ANALYZE) UPDATE/DELETE` ở production.

### 14.4. pg_stat_statements và performance insights

Flexible Server có thể cung cấp query performance insights và hỗ trợ `pg_stat_statements` theo phiên bản/extension allowlist. Trước khi bật, kiểm tra preloading, server parameters, quyền và khả năng cần restart.

~~~sql
-- Chỉ khi extension và quyền được server hỗ trợ.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

Không coi `CREATE EXTENSION` là lệnh chắc chắn thành công trên mọi server. Query statistics có thể chứa thông tin nhạy cảm; áp dụng retention và quyền xem phù hợp.

### 14.5. Autovacuum và table bloat

PostgreSQL MVCC giữ dead tuples sau UPDATE/DELETE cho tới khi vacuum dọn. Nếu autovacuum không theo kịp hoặc có long-running transactions, bloat và disk pressure có thể tăng.

~~~sql
SELECT schemaname, relname, n_live_tup, n_dead_tup,
       last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
~~~

Giải pháp:

- Theo dõi dead tuples, long transactions và disk growth.
- Điều chỉnh autovacuum/analyze trong giới hạn managed server hỗ trợ.
- Dùng `VACUUM ANALYZE` phù hợp vào thời điểm cho phép.
- Tránh `VACUUM FULL` ngoài maintenance window vì locking và disk requirements.
- Xóa rows hoặc VACUUM không đồng nghĩa giảm được kích thước storage đã provisioned và hóa đơn Azure ngay.

### 14.6. N+1, batching và transactions

Với Java/Spring Data JPA:

- Tránh **N+1 queries** do lazy loading sai chỗ.
- Dùng prepared statements, batch inserts/updates và transactions ngắn.
- Index theo query patterns thực, không theo cảm tính.
- Đặt statement timeout và pool wait timeout theo SLO.
- Không dùng `SELECT *` với bảng lớn khi chỉ cần vài columns.
- Đánh giá keyset pagination thay `OFFSET` rất lớn.
- Dùng `COPY` cho bulk import nếu đã kiểm tra tài nguyên/quyền.


## 15. Azure Monitor, logs, alerts và SLO

### 15.1. Giám sát theo hai lớp

Azure Monitor phản ánh tình trạng **tài nguyên được quản lý**: CPU, memory, storage, IO, connections, availability, replication và các metric khác theo tính năng/tier. PostgreSQL dynamic views/logs phản ánh **ngữ cảnh SQL và sessions**.

| Nguồn | Tín hiệu | Câu hỏi |
| --- | --- | --- |
| Azure Monitor metrics | CPU, memory, IOPS, storage percentage | Compute/storage có nghẽn? |
| PostgreSQL connection metrics | Active/succeeded/failed connections | App pool sizing và auth có ổn? |
| PostgreSQL `pg_stat_activity` | Queries, wait events, states | Query/lock nào đang chặn? |
| Query insights / `pg_stat_statements` | Query frequency, total time, mean time | SQL nào tốn tài nguyên? |
| PostgreSQL logs | Authentication errors, errors, slow queries | Lỗi ở DB hay client? |
| Azure Activity Log | Server/parameter/network changes | Ai vừa thay cấu hình Azure? |
| HA/replica metrics | Failover events, replica lag khi có | Availability/replcation có đạt SLO? |
| App Service/AKS/App Insights | API p95/p99, pool timeouts | Lỗi có thật sự ảnh hưởng người dùng? |
| Cost Management | Compute/storage/backup/network charges | Ngân sách có đang bị vượt? |

Không mặc định mọi metric có sẵn ở mọi tier/version. Hãy liệt kê **metric definitions** của resource thật trước khi chọn tên/dimensions.

### 15.2. Lệnh Azure CLI chỉ đọc

~~~bash
PG_RESOURCE_ID=$(az postgres flexible-server show \
  --resource-group "$RG" \
  --name "$PGSERVER" \
  --query id \
  --output tsv)

az monitor metrics list-definitions \
  --resource "$PG_RESOURCE_ID" \
  --output table

az monitor metrics list \
  --resource "$PG_RESOURCE_ID" \
  --output json
~~~

Lệnh cuối trả metrics theo defaults/cấu hình hiện có; trong một dashboard thực phải chỉ định metric name, granularity, timeframe và dimensions phù hợp. Không dùng một snapshot CPU duy nhất để quyết định tăng compute.

### 15.3. Diagnostic settings và query logs

Cần cấu hình theo chính sách:

- Diagnostic settings gửi logs/metrics được hỗ trợ tới Log Analytics, Storage hoặc Event Hubs.
- PostgreSQL server parameters liên quan logging/slow query theo tính năng hỗ trợ.
- Retention và workspace access controls.
- Masking/giảm dữ liệu nhạy cảm trong SQL text.
- Correlation ID từ Java request qua DB connection/tracing nếu có thể.

**Kích hoạt log tất cả SQL statements** có thể làm tăng chi phí, ảnh hưởng hiệu năng và lộ giá trị đầu vào; phải đánh giá policy trước. Đối với dữ liệu cá nhân, giới hạn người đọc logs.

### 15.4. Các cảnh báo nên có

- CPU/IOPS/throughput hoặc memory áp sát giới hạn kéo dài.
- Storage usage tăng nhanh, gần giới hạn provisioned.
- Failed connections/auth failures tăng.
- Active connections gần `max_connections` hoặc pool wait time tăng.
- Query p95/p99 vượt SLO, long transactions, deadlocks.
- Availability/failover hoặc HA state bất thường.
- Replica lag vượt mức read staleness được phép.
- Backup/restore failures theo telemetry có hỗ trợ.
- Chi phí tăng bất thường hoặc resource bị scale ngoài change window.

Alert phải gắn **owner, severity, ngưỡng, thời gian duy trì và runbook**. CPU tăng một phút theo batch đã biết có thể chấp nhận; CPU saturation kéo dài kèm API 5xx cần xử lý ngay.

### 15.5. SLO toàn chuỗi

Ví dụ một SLO nghiệp vụ:

~~~text
POST /orders:
  p95 end-to-end latency < 300 ms
  success rate             >= 99.9% theo cửa sổ đã định
  Không tạo đơn trùng khi retry

GET /orders/{id} từ replica:
  p95 latency              < 150 ms
  Read staleness           <= 5 giây (mục tiêu nghiệp vụ)
~~~

Đây là **mục tiêu minh họa của ứng dụng**, không phải SLA được Azure cam kết. DB availability là một thành phần, không bảo đảm API SLO khi lỗi code, pool hoặc network.

## 16. Bảo trì, nâng cấp và quản trị tham số server

### 16.1. Maintenance window

Flexible Server thực hiện routine maintenance/patching theo lịch và chính sách dịch vụ. Một số thao tác có thể gây restart/failover hoặc thay đổi kết nối tạm thời.

Thiết kế:

1. Chọn maintenance window phù hợp hoạt động kinh doanh khi dịch vụ cho phép.
2. Thông báo nhóm API, SRE, DBA và owner workloads.
3. Giữ metrics/cảnh báo, runbook khôi phục và escalation.
4. Xác minh retry/idempotency của client trước maintenance.
5. Sau maintenance đo API latency, failed connections và replication health.

Không nhầm maintenance window với thời gian chắc chắn **không bao giờ có sự cố** ngoài cửa sổ; incident/failover bất ngờ vẫn có thể xảy ra.

### 16.2. PostgreSQL minor vs major upgrade

- **Minor version/patch:** vá lỗi/tính bảo mật trong cùng major version theo lịch hỗ trợ.
- **Major version upgrade:** có thể thay đổi extension compatibility, planner, SQL behavior, client driver và yêu cầu migration/cutover.

Quy trình major upgrade:

1. Kiểm tra phiên bản nguồn/đích và feature eligibility.
2. Rà soát extensions, server parameters, reserved keywords, queries và JDBC versions.
3. Backup/PITR plan và có môi trường staging tương đương.
4. Thử schema migrations, restore, performance regression và failover.
5. Đánh giá đường nâng cấp **in-place hay migration** được hỗ trợ theo service/tier.
6. Lập cutover/rollback; chú ý đôi khi rollback major upgrade không chỉ là đổi một tham số.
7. Theo dõi sau nâng cấp và làm sạch cấu hình không còn dùng.

### 16.3. Server parameters

PostgreSQL có nhiều parameters như `max_connections`, `work_mem`, `shared_buffers`, `log_min_duration_statement`, `statement_timeout`, `autovacuum_*`. Trên managed Flexible Server:

- Một số parameters **read-only hoặc Azure-managed**.
- Một số parameters có thể thay đổi qua Azure portal/CLI nhưng **cần restart**.
- Một số chỉ hỗ trợ trong giới hạn/tier cụ thể.
- Tăng `work_mem`/`max_connections` có thể tăng memory pressure và OOM risk.
- Bật logical replication làm thay đổi WAL/slot behavior.

Ví dụ chỉ đọc danh sách parameters:

~~~bash
az postgres flexible-server parameter list \
  --resource-group "$RG" \
  --server-name "$PGSERVER" \
  --output table
~~~

Trước khi `parameter set`, kiểm tra giá trị mặc định/giới hạn, restart requirement và test tại staging. Không thay 20 parameters cùng lúc vì sẽ khó phân biệt nguyên nhân.

### 16.4. Stop/start và tiết kiệm chi phí lab

Một số cấu hình có **stop/start** để giảm chi phí compute khi lab không dùng. Tuy nhiên:

- Stop không đồng nghĩa mọi phí storage/backup/networking biến mất.
- Có giới hạn/điều kiện thời gian stop và auto-start tùy dịch vụ/tier.
- HA, replica, compute hoặc network settings có thể ảnh hưởng tính năng stop.
- Không áp dụng stop như kế hoạch production HA.
- Khi restart, cần kiểm tra connectivity, app pools và scheduled workloads.

Chỉ sử dụng stop sau khi xác nhận hỗ trợ của server và có quyền; không để script tự dừng database production.

## 17. Bảo mật production: dữ liệu, mạng, roles và audit

### 17.1. Defense in depth

~~~mermaid
flowchart LR
    APP["Application identity"]
    NET["VNet / Private DNS\nNSG / Firewall"]
    TLS["TLS verify-full"]
    AUTH["PostgreSQL / Entra auth"]
    RBAC["DB GRANT + Row policy"]
    DATA["PostgreSQL tables"]
    LOG["Audit / Monitoring"]
    APP --> NET --> TLS --> AUTH --> RBAC --> DATA
    AUTH -.-> LOG
    DATA -.-> LOG
~~~

Mọi lớp đều có ý nghĩa:

- **Network:** giảm bề mặt truy cập và chặn nguồn không được phép.
- **TLS:** mã hóa trên đường truyền và xác minh server.
- **Authentication:** xác định principal đăng nhập.
- **Authorization:** hạn chế database/schema/table/row actions.
- **Audit/Monitor:** phát hiện cấu hình sai và truy cập bất thường.

### 17.2. Trách nhiệm mã hóa

Azure-managed database có cơ chế mã hóa dữ liệu lưu trữ theo chính sách nền tảng. Một số cấu hình hỗ trợ tùy chọn **customer-managed keys (CMK)** với Key Vault/managed identity theo tier/feature eligibility. Nếu cần CMK:

- Xác định compliance yêu cầu và quyền quản trị Key Vault.
- Kiểm tra Key Vault availability, key rotation, soft delete/purge protection theo chính sách.
- Đánh giá hậu quả nếu key bị thu hồi/hết quyền.
- Thử recovery/restore trong cấu hình encryption tương ứng.
- Không tự assume mọi server/HA/replica đều đổi encryption option được in-place.

**Encryption at rest không thay TLS in transit** và không làm SQL data tự được phân quyền.

### 17.3. Không lưu PII trong connection logs

Tránh:

- In JDBC URL nếu chứa username/password hoặc token.
- Log toàn bộ SQL values, credit-card data hoặc access tokens.
- Xuất `pg_stat_activity.query` nguyên vẹn ra ticket công khai.
- Lưu database dump vào bucket không có quyền truy cập.
- Dùng admin login cho app runtime.

Khi có yêu cầu audit, chọn extension/logging features được Azure hỗ trợ và quản lý retention/quyền xem. Không chạy audit extension chưa được cho phép trên Flexible Server.

### 17.4. Row-Level Security (RLS) cho nhiều tenants

Khi một database chứa nhiều tenants, PostgreSQL **Row-Level Security** có thể bổ sung giới hạn truy cập theo row, nhưng:

- Cần thiết kế roles, policy, table ownership và session context đúng.
- App không được tự ý đặt `tenant_id` từ đầu vào không đáng tin.
- Với connection pooling/transaction pooling, không được giả định session state được giữ giữa requests.
- RLS **không thay** mạng, auth, schema review và authorization trong ứng dụng.
- Phải có tests bảo đảm tenant A không đọc/ghi rows của tenant B.

Ví dụ conceptual policy, **không phải thiết kế production hoàn chỉnh**:

~~~sql
-- Minh họa chỉ khi bảng có tenant_id và role/policy phù hợp.
-- ALTER TABLE sales.orders ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY tenant_filter ON sales.orders
-- USING (tenant_id = current_setting('app.tenant_id')::text);
~~~

Không áp dụng comment này nguyên văn lên schema lab (bảng chưa có `tenant_id`). Xây mô hình tin cậy rõ ràng và kiểm thử với các PostgreSQL roles khác nhau trước khi bật.

### 17.5. Network security review

- Rà soát public firewall rules định kỳ và loại IP không còn dùng.
- Kiểm tra Private DNS Zone links, peering, UDR, NSG.
- Hạn chế outbound database access từ workloads không cần thiết.
- Quản lý private endpoint/VNet integration theo nguồn kết nối thực.
- Tách Dev/Staging/Prod DBs và credentials khi cần.
- Dùng principle of least privilege cho Azure roles và PostgreSQL roles.
- Bảo đảm backup/restored copies cũng tuân thủ vùng dữ liệu/quyền.

## 18. Chi phí và capacity planning

### 18.1. Thành phần chi phí

| Thành phần | Các yếu tố quyết định |
| --- | --- |
| Compute | Tier, vCores, SKU, HA/standby và thời gian provision |
| Storage | GiB provisioned, auto-grow, storage performance/IOPS |
| Backup | Retention, additional storage, redundancy theo billing policy |
| Read replica | Compute/storage cho từng replica và network |
| Network | Egress, Private Endpoint, NAT, data movement |
| Monitoring | Log Analytics ingestion, retention, alerts |
| Key Vault | Access operations/keys theo cấu hình |
| Môi trường DR | Warm/cold standby, test restored servers |
| Ứng dụng | App Service/AKS instances, CPU, connection pool/traffic |

**Giá thay đổi theo region/SKU/tier/thời gian và chính sách hợp đồng.** Không đưa mức USD cố định như cam kết. Dùng Azure Pricing Calculator và Cost Management với lựa chọn thực.

### 18.2. Sizing theo workload

Một hệ thống nhận 400 API requests/giây, mỗi request thực hiện trung bình hai SQL queries:

~~~text
Request rate       = 400 req/s
SQL per request    = 2
SQL query rate     ≈ 800 queries/s
~~~

Nhưng 800 queries/s **không đủ** để chọn vCores/IOPS. Một `SELECT` đọc 1 row từ cache khác với query quét 10 triệu rows. Cần load test và đo:

- p50/p95/p99 query latency.
- CPU/memory, cache hit, IOPS/throughput.
- Index access, locks, temp spill.
- Concurrent transactions và connections.
- Peak traffic, growth forecast và retention.
- Downstream/retry behaviors khi failover.

### 18.3. Từ Hikari pool đến max_connections

Ví dụ:

~~~text
App instances:                    16
Pool max per instance:            12
Potential DB sessions:            192

Background worker sessions:        20
Monitoring/migrations reserve:     10
Total potential:                   222
~~~

Nếu server chỉ có budget kết nối thấp hơn, cần giảm pool sizes hoặc dùng pooling architecture, không tăng `max_connections` một cách mù quáng. Connections tiêu tốn memory, nhất là khi có nhiều concurrent queries/`work_mem`.

### 18.4. Bảo đảm capacity khi failover

Tải có thể tăng tạm thời sau failover do tất cả application instances cùng retry/reconnect:

- Dùng exponential backoff với jitter.
- Đặt max retry time và circuit breaker.
- Hạn chế pool creation bursts.
- Lưu idempotency keys để tránh duplicate transactions.
- Theo dõi `remaining connection slots`/CPU và HTTP 5xx.
- Có plan giảm tải nếu DB chưa warm cache.

### 18.5. FinOps

- Dùng General Purpose khi đáp ứng SLO thay vì mặc định Memory Optimized.
- Scale dựa trên metrics, không chỉ cảm nhận.
- Dọn replica/lab/restored server không dùng theo change approval.
- Đánh giá backup retention và chi phí lưu trữ tăng trưởng.
- Giảm log spam, giữ audit bắt buộc.
- Bật budgets/alerts, gắn resource tags và owner rõ ràng.
- Tối ưu queries/indexes trước khi tăng compute/IOPS nếu nguyên nhân là SQL.


## 19. Runbook chẩn đoán Flexible Server: kết nối, hiệu năng và availability

### 19.1. Bảng khoanh vùng nhanh

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra |
| --- | --- | --- |
| `could not translate host name` | DNS sai, private zone/link lỗi | `nslookup` từ đúng client/network |
| TCP timeout port 5432 | Firewall, NSG/UDR, VPN, routing | `nc -vz host 5432`, network access mode |
| `no pg_hba.conf entry` hoặc lỗi tương tự | Nguồn mạng/TLS/auth policy bị từ chối | Firewall/network mode/TLS, không tự sửa OS pg_hba |
| `password authentication failed` | Sai user/password, role, secret rotation | User đúng Flexible Server, credentials, logs |
| Entra token không đăng nhập | Audience/token hết hạn, principal chưa map role | Entra config, PostgreSQL role, refresh |
| TLS certificate verify failed | CA trust, SAN/hostname, certificate chain | `sslmode=verify-full`, CA/FQDN |
| `too many connections` | App replicas × pool size vượt budget | `pg_stat_activity`, Hikari active/idle |
| HTTP API 500/timeout, CPU DB thấp | Pool wait, locks, network hoặc SQL exception | Hikari metrics, DB logs, query waits |
| CPU DB 95% kéo dài | SQL nặng, burst, tier nhỏ | Query insights, indexes, concurrency |
| IOPS/storage pressure | Table scan, WAL, bloat, storage growth | Azure metrics, `pg_stat_user_tables` |
| Query bị chặn | Long transaction/row lock/deadlock | `pg_stat_activity` wait events |
| Có bảng nhưng role không SELECT được | Grants/schema USAGE thiếu | `\dp`/`\dn+` trong psql, GRANT |
| App không thấy row vừa ghi | Đọc từ async replica bị lag | Đọc primary hoặc theo dõi replica lag |
| Lỗi ngắt kết nối khi failover | Pool giữ connections cũ | Reconnect/backoff/idempotency |
| PITR restore không thấy một số rows | Mốc thời gian chọn trước commit | Xác minh UTC/commit/restore point |
| Maintenance gây 5xx | Restart, failover, retry quá nhanh | Runbook, app traces, DB activity |
| Chi phí tăng dù dev ít dùng | SKU, HA/replica/restored server, storage | Cost Management, resource inventory |

**Không cố sửa mọi lỗi bằng cách mở firewall toàn Internet hoặc tăng vCores.** Bắt đầu từ bằng chứng đúng lớp.

### 19.2. Bước 1 — Xác định đích Azure

Ghi lại server name, FQDN, subscription, RG, region, tier, network mode và mốc UTC. Các lệnh sau chỉ đọc:

~~~bash
az account show --output json

az postgres flexible-server show \
  --resource-group "$RG" \
  --name "$PGSERVER" \
  --query "{name:name,state:state,version:version,sku:sku,storage:storage,highAvailability:highAvailability}" \
  --output json
~~~

Nếu app đang kết nối FQDN staging nhưng môi trường cấu hình production, đừng đổi firewall/role trên production để chữa triệu chứng.

### 19.3. Bước 2 — DNS và network

Từ **chính container/VM/runner chạy ứng dụng**:

~~~bash
nslookup "$PGHOST"
nc -vz "$PGHOST" 5432
~~~

Nếu public mode: kiểm tra đúng **public egress IP** và firewall rule. Nếu private mode: kiểm tra subnet delegation, Private DNS links, peering, VNet integration của client và NSG/UDR.

**Không dùng thành công từ laptop để kết luận AKS Pod có route tương đương.** Mỗi nguồn có DNS/egress path khác nhau.

### 19.4. Bước 3 — TLS và authentication

Từ mạng hợp lệ:

~~~bash
psql "host=$PGHOST port=5432 dbname=postgres user=$ADMIN \
sslmode=verify-full sslrootcert=$CAFILE"
~~~

Đọc lỗi:

- Certificate/hostname → kiểm tra FQDN, CA chain và client trust.
- Password → secret, username, role và rotation.
- Entra token → principal mapping, token lifetime/refresh và audience.
- Permission denied trên table → PostgreSQL grants, không phải Azure firewall.

Đừng đưa credentials vào công cụ hỗ trợ chưa được phê duyệt hoặc dùng `sslmode=disable` làm workaround.

### 19.5. Bước 4 — Connections và query waits

~~~sql
SELECT count(*) AS total_connections
FROM pg_stat_activity;

SELECT usename, state, count(*) AS sessions
FROM pg_stat_activity
GROUP BY usename, state
ORDER BY sessions DESC;

SELECT pid, usename, wait_event_type, wait_event,
       now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY transaction_age DESC NULLS LAST
LIMIT 20;
~~~

Những truy vấn này thường là read-only, nhưng quyền xem chi tiết có thể bị giới hạn. Đừng terminate sessions của ứng dụng bằng `pg_terminate_backend` trước khi xác định owner và hậu quả.

Nếu connections nhiều nhưng queries không chạy, kiểm tra **idle sessions** và Hikari maximumPoolSize × number of replicas. Nếu có long transactions/locks, xác định code path và query gây giữ transaction.

### 19.6. Bước 5 — Performance theo bottleneck

- **CPU cao + query chậm:** xem query plan, missing index, joins, JPA N+1.
- **IOPS cao:** xem sequential scans, bloat, caching, bulk jobs.
- **Storage tăng:** phân biệt dữ liệu thật, indexes, temp files, WAL/replication slots.
- **Pool wait tăng nhưng CPU thấp:** pool limit, connection leak, network hoặc lock waits.
- **Replica lag:** đo primary write rate, replica capacity và read workload.
- **App tăng 5xx sau failover:** kiểm tra connection pool recovery và retry storm.

Thu bằng chứng trước khi scale hoặc thay tham số nhiều lần. Nếu cần load test, dùng staging với dữ liệu đại diện và quyền rõ ràng.

### 19.7. Bước 6 — Kiểm tra backup/restore và failover

Nếu server không khả dụng:

1. Phân loại single instance/zone/region incident.
2. Xem server/HA status và Azure Monitor health signals.
3. Không tự force failover hoặc xóa resources trong lúc chưa rõ hậu quả.
4. Đánh giá RTO/RPO và phương án dự phòng đã định.
5. Nếu cần PITR, chọn thời điểm UTC hợp lệ và tạo restored server riêng.
6. Xác minh dữ liệu, quyền, network, TLS trước khi cutover.
7. Theo dõi ứng dụng sau phục hồi, ghi incident timeline.

### 19.8. Bước 7 — Xác minh sửa lỗi

Sau thay đổi:

- FQDN/TLS/identity đăng nhập đúng.
- PostgreSQL role chỉ có privileges cần thiết.
- Connection pool không còn exhaustion.
- p95 API/DB latency và error rate đạt SLO.
- Storage/IO metrics ổn định.
- HA/replica lag phù hợp và restore plan khả thi.
- Không mở public access trái chính sách.
- Chi phí không vượt budget; alert tiếp tục hoạt động.

## 20. Bài thực hành tổng hợp

### 20.1. Bài toán

Công ty triển khai Java Order API trên AKS, lưu dữ liệu ở PostgreSQL Flexible Server.

Yêu cầu:

- **Không public database** ra Internet khi triển khai production.
- DB truy cập được từ AKS qua VNet/private DNS.
- Có **HA zone-redundant** nếu region/tier hỗ trợ và được phê duyệt.
- Hỗ trợ **PITR** và backup retention theo tiêu chuẩn công ty.
- Tài khoản `app_runtime` chỉ có CRUD trên schema `sales`.
- Ứng dụng dùng JDBC TLS verify-full và HikariCP.
- Có dashboard CPU, connections, storage, query latency, replica lag nếu tạo replica.
- Có ngân sách và alert.
- Dữ liệu đơn hàng phải idempotent khi API retry.

### 20.2. Checklist nghiệm thu

| Bước | Thao tác | Bằng chứng |
| --- | --- | --- |
| 1 | Chọn subscription/RG/region | `az account show` đúng |
| 2 | Dự toán giá tier/HA/storage | Có bảng cost estimate |
| 3 | Tạo/kiểm tra VNet + delegated subnet và Private DNS | DNS zone/link đúng, đường private |
| 4 | Tạo Flexible Server private | FQDN có route phù hợp trong VNet |
| 5 | Đặt backup retention và HA theo yêu cầu | Server show/portal xác nhận |
| 6 | Kết nối psql qua TLS verify-full | CA/hostname hợp lệ |
| 7 | Tạo `ordersdb`, schema/tables/indexes | SQL queries thành công |
| 8 | Tạo `app_runtime`, kiểm tra grants | SELECT/INSERT được, DDL bị từ chối |
| 9 | Triển khai Java JDBC/HikariCP | App test INSERT/SELECT, không log secrets |
| 10 | Giám sát CPU, IO, connections và query plan | Azure Monitor + PostgreSQL stats |
| 11 | Thử PITR ở môi trường được phép | Restored server có rows đúng |
| 12 | Thử failover ở staging có approval | Reconnect và idempotency đúng |
| 13 | Rà soát firewall/public exposure | Không có public path ngoài ý định |
| 14 | Đặt alert/budget và runbook | Owner, thresholds và escalation |
| 15 | Dọn lab theo phê duyệt | Không xóa resource dùng chung |

### 20.3. Tình huống A — Server có private IP nhưng API timeout

App Service/AKS không giải được hostname PostgreSQL hoặc nhận private IP không thể route.

**Chẩn đoán:** xem Private DNS Zone link/forwarding, VNet integration của client, VNet peering/UDR/NSG, subnet delegation và TCP 5432. Không mở public firewall để “khỏi phải sửa DNS”.

### 20.4. Tình huống B — TLS kết nối được nhưng login bị từ chối

`psql` báo lỗi password auth hoặc Entra token. `nc -vz` thành công.

**Chẩn đoán:** network đã thông, tập trung username/password hoặc Entra role/token mapping, grants và secret rotation. Không nới firewall.

### 20.5. Tình huống C — Java API tăng từ 4 lên 20 replicas

Mỗi replica có Hikari max pool size 15.

\[
20\times15=300\text{ potential sessions}
\]

Nếu database có giới hạn connections an toàn thấp hơn 300 sau trừ admin/headroom, scaling API có thể làm DB thiếu sessions dù CPU còn thấp.

**Hướng xử lý:** giảm pool, dùng PgBouncer khi tương thích, kiểm tra Hikari wait/leaks, DB max_connections và transaction concurrency; không tự tăng số connections nếu memory không đủ.

### 20.6. Tình huống D — Transaction bị lỗi giữa COMMIT và phản hồi

App gửi yêu cầu tạo `ORD-1001`, mất kết nối trong failover và client retry.

**Hướng xử lý:** dùng `external_id UNIQUE`/idempotency key, query xác nhận trạng thái nghiệp vụ, không tạo một order mới khác ID. Retry phải có giới hạn và backoff.

### 20.7. Tình huống E — Replica đọc thiếu đơn mới

API vừa INSERT `ORD-1001` trên primary, GET qua replica không thấy row.

**Hướng xử lý:** nhận diện replication lag; route read-your-writes về primary hoặc chờ theo consistency policy. Không coi replica là đồng bộ tuyệt đối.

### 20.8. Tình huống F — Migration xóa sai dữ liệu

Một migration lúc 14:05 UTC xóa nhầm bảng `orders`.

**Hướng xử lý:** dừng write/migration gây lỗi, xác định restore point trước 14:05, tạo restored server bằng PITR, so sánh dữ liệu và cutover theo runbook. Không cố “đổi giờ trên primary” hoặc xoá server gốc ngay.

### 20.9. Tình huống G — CPU cao nhưng chỉ một truy vấn

Một query JPA đọc tất cả orders của mỗi customer và join nhiều bảng; p95 tăng 4 giây.

**Hướng xử lý:** `EXPLAIN`/`EXPLAIN ANALYZE` có kiểm soát, check N+1, indexes, statistics, pagination, locks và pool; scale compute chỉ khi có bằng chứng phù hợp.

### 20.10. Tình huống H — Chi phí DB tăng mạnh

Có một server HA, hai read replicas, một PITR restored server từ hôm trước và Log Analytics ingestion tăng.

**Hướng xử lý:** kiểm kê tài nguyên, xác định owner và tình trạng sử dụng; dọn restored server chỉ sau approval, điều chỉnh logs/retention và cân đối replica/SLO. Không tắt HA chỉ để giảm giá mà chưa xem rủi ro RTO.

## 21. Dọn dẹp môi trường lab an toàn

### 21.1. Kiểm tra tài nguyên trong RG

~~~bash
az resource list \
  --resource-group "$RG" \
  --output table
~~~

**Không xóa RG khi có resources dùng chung hoặc production.** Flexible Server, backup và read replicas có thể còn phục vụ nhiều ứng dụng dù chỉ một team nhìn thấy.

### 21.2. Chỉ xóa RG dành riêng cho lab

~~~bash
# THAO TÁC PHÁ HỦY.
# Chỉ chạy sau phê duyệt và xác minh RG hoàn toàn thuộc lab.
az group delete \
  --name "$RG" \
  --yes
~~~

Lệnh có thể xóa database, tài nguyên mạng, backups hoặc tài nguyên phụ thuộc trong RG; không thể đơn giản hoàn tác. Nếu VNet/Private DNS là tài nguyên dùng chung, chỉ xóa từng resource lab đã định danh, theo change approval.

### 21.3. Hậu kiểm

- Không còn server/replica/restored instance lab phát sinh phí.
- Database dump/log secrets được quản lý theo chính sách.
- Role assignments, Private DNS records và firewall rules lab được rà soát.
- Backup/retention requirements không bị vi phạm.
- Azure Cost Management và alerts không có nguồn chi phí bất thường sau dọn.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Flexible Server khác PostgreSQL cài trên VM ở điểm nào?

**Trả lời:** Azure quản lý nhiều hạ tầng dịch vụ, backup/maintenance/HA theo cấu hình; khách hàng vẫn quản lý SQL, schema, quyền, kết nối, performance và recovery drills. VM cho nhiều quyền OS hơn nhưng cần tự vận hành nhiều thành phần hơn.

**Câu 2.** Flexible Server có tự sinh HA standby khi tạo không?

**Trả lời:** Không mặc định. Cần chọn HA mode theo tier/region và xác minh cấu hình thật.

**Câu 3.** Same-zone HA và zone-redundant HA khác gì?

**Trả lời:** Same-zone standby nằm trong cùng zone, còn zone-redundant sử dụng zone khác khi hỗ trợ; zone-redundant giảm rủi ro hỏng toàn một zone nhưng không thay DR cross-region.

**Câu 4.** Read replica có thay PITR backup không?

**Trả lời:** Không. Xóa nhầm dữ liệu trên primary có thể được replicate sang replica. PITR tạo bản dữ liệu ở thời điểm trước lỗi trong backup window.

**Câu 5.** Vì sao backup restore thường cần FQDN mới?

**Trả lời:** PITR thường tạo một restored server riêng; ứng dụng cần xác minh rồi cutover theo runbook thay vì tự đổi primary.

**Câu 6.** Một Private DNS Zone có đủ để đảm bảo database an toàn không?

**Trả lời:** Không. Cần route/network policy, TLS, authentication, PostgreSQL grants và kiểm soát secret.

**Câu 7.** Dùng `sslmode=require` có giống `sslmode=verify-full` không?

**Trả lời:** Không. `verify-full` xác minh cả chain CA và hostname server, phù hợp mục tiêu bảo mật production.

**Câu 8.** Azure RBAC Contributor có mặc định SELECT trên bảng PostgreSQL không?

**Trả lời:** Không. Azure resource permissions và PostgreSQL data-plane privileges khác nhau.

**Câu 9.** Khi API tăng từ 10 lên 20 replicas, điều gì xảy ra với connection pool budget?

**Trả lời:** Số connections tiềm năng có thể tăng gấp đôi nếu mỗi replica có pool size không đổi, dễ vượt max_connections hoặc làm DB thiếu RAM.

**Câu 10.** Tại sao ứng dụng cần idempotency khi failover?

**Trả lời:** Mất kết nối sau COMMIT có thể khiến client không biết transaction đã thành công chưa; retry thiếu idempotency tạo duplicate side effects.

**Câu 11.** `EXPLAIN ANALYZE` khác `EXPLAIN` thế nào?

**Trả lời:** `EXPLAIN ANALYZE` thực thi query để đo thực tế; phải tránh chạy lệnh ghi nặng trên production khi chưa có kiểm soát.

**Câu 12.** `VACUUM FULL` có nên dùng thường xuyên để giảm hóa đơn storage không?

**Trả lời:** Không. Nó có thể gây lock/IO lớn, không bảo đảm giảm storage đã provisioned trên Azure và chỉ nên cân nhắc theo runbook.

**Câu 13.** Tại sao GET qua replica đôi khi không thấy đơn vừa INSERT?

**Trả lời:** Vì asynchronous replication có lag; các luồng cần read-after-write phải đọc primary hoặc có consistency strategy.

**Câu 14.** Tại sao tăng vCores không chữa được một SQL deadlock?

**Trả lời:** Deadlock phụ thuộc transaction/lock order trong ứng dụng và dữ liệu; cần sửa code/transaction logic.

**Câu 15.** Chọn Burstable, General Purpose hay Memory Optimized dựa vào đâu?

**Trả lời:** Workload CPU/RAM pattern, SLO, HA/feature availability, cost và kết quả benchmark; không chỉ nhìn giá thấp nhất.

**Câu 16.** Nếu database đang public-access và tổ chức yêu cầu private-only, có thể chỉ sửa DNS thành private là đủ không?

**Trả lời:** Không. Cần triển khai một network access model được dịch vụ hỗ trợ (VNet integration hoặc Private Link tùy loại server), DNS, routing/firewall và quy trình migration/cutover hợp lệ.

**Câu 17.** `pg_stat_statements` tự hoạt động trên mọi Flexible Server sau một câu `CREATE EXTENSION` không?

**Trả lời:** Không chắc. Cần kiểm tra extension allowlist, version, parameters/preload/restart và quyền.

**Câu 18.** Khi dọn lab, có nên xóa resource group bằng một lệnh mà không kiểm tra không?

**Trả lời:** Không. Chỉ xóa RG đã xác minh hoàn toàn là lab và có phê duyệt, vì lệnh là thao tác phá hủy có thể ảnh hưởng dữ liệu/nguồn dùng chung.

## Ghi nhớ

- **Azure Database for PostgreSQL Flexible Server** là dịch vụ PostgreSQL quan hệ được quản lý, nhưng bạn vẫn chịu trách nhiệm về **SQL, schema, roles, networking, bảo mật, SLO và chi phí**.
- **Compute tier, SKU, storage/IOPS, backup và HA** phải được chọn theo workload, region/feature support và ngân sách.
- **Public firewall allowlist** và **private VNet/Private Link** là lựa chọn kết nối khác nhau; DNS, route, TLS và authentication phải được kiểm tra riêng.
- Với client PostgreSQL/JDBC, nên hướng đến **TLS verify-full**, role quyền tối thiểu, secret management và connection pooling có budget.
- **HA standby** bảo vệ availability theo mô hình; **read replica** giúp scale reads nhưng có lag; **PITR** hỗ trợ phục hồi dữ liệu và thường tạo server mới.
- **Bảo vệ giao dịch** cần PostgreSQL constraints, transactions ngắn, idempotency và retry có giới hạn khi mất kết nối/failover.
- Giám sát đồng thời **Azure Monitor metrics** và **PostgreSQL statistics/query plans** để sửa đúng CPU/IO/lock/connections.
- Đưa database vào production chỉ khi đã có **monitoring, backup restore drill, HA/DR plan, security review, cost budget và runbook xử lý sự cố**.
