# Azure Database for MySQL Flexible Server

## 1. Vì sao chọn MySQL được quản lý trên Azure?

Ứng dụng Java có thể chạy trên Azure App Service, Azure Functions, Azure Kubernetes Service (AKS) hoặc VM. Những ứng dụng lưu đơn hàng, tài khoản, tồn kho và giao dịch thường cần cơ sở dữ liệu quan hệ có **SQL, transaction, index và ràng buộc dữ liệu**.

Có hai hướng triển khai MySQL:

- **Tự cài MySQL trên Azure VM:** nhóm vận hành quản lý hệ điều hành, MySQL process, backup, patch, replication, HA và monitoring.
- **Azure Database for MySQL Flexible Server:** Azure cung cấp dịch vụ MySQL managed; đội ứng dụng tập trung vào schema, truy vấn, quyền, kết nối, hiệu năng, backup/restore policy và khả năng phục hồi nghiệp vụ.

Đây là bài học thuộc chương **Cơ sở dữ liệu quan hệ** của module tìm hiểu hệ sinh thái Microsoft Azure, kết nối subscription, resource group, Microsoft Entra ID, mạng ảo, dịch vụ tính toán, bảo mật, giám sát và chi phí vào một kiến trúc ứng dụng có MySQL.

**MySQL managed không có nghĩa ứng dụng không cần thiết kế database.** Một query thiếu index vẫn có thể chậm, một transaction lỗi vẫn có thể làm sai dữ liệu và một kết nối không mã hóa vẫn có thể gây rủi ro bảo mật.

### Tình huống xuyên suốt

Giả sử hệ thống thương mại điện tử có:

- **orders-api**: Java API ghi và tra cứu đơn hàng.
- **catalog-api**: cung cấp thông tin sản phẩm.
- **orders-worker**: xử lý sự kiện từ Azure Service Bus.
- **Azure Database for MySQL Flexible Server**: lưu orders, products và dữ liệu quan hệ.
- **Azure Monitor**: theo dõi hiệu năng và sự cố.
- **Azure Key Vault/identity**: quản lý credentials hoặc phương thức xác thực được hỗ trợ.

Mục tiêu là chọn cấu hình MySQL phù hợp, không chỉ tạo được server.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Azure Database for MySQL Flexible Server và trách nhiệm của khách hàng.
2. So sánh Flexible Server với Azure SQL, PostgreSQL managed và MySQL tự quản lý.
3. Chọn compute tier, vCores, memory, storage và IOPS.
4. Phân biệt HA same-zone/zone-redundant, PITR và read replica.
5. Thiết kế backup, RPO/RTO và recovery drill.
6. Chọn public firewall hoặc private networking và cấu hình DNS phù hợp.
7. Dùng TLS và phân biệt Azure RBAC với MySQL authentication/authorization.
8. Thiết kế quyền MySQL tối thiểu và kết nối Java JDBC/HikariCP.
9. Tạo schema, transactions, indexes và phân tích EXPLAIN.
10. Giám sát performance, connections, slow queries và storage.
11. Lập kế hoạch maintenance, upgrades, migration và DR.
12. Hoàn thành lab có giới hạn chi phí và quy trình cleanup an toàn.

## 3. Kiến trúc Flexible Server

Flexible Server là một **Azure resource** cung cấp MySQL database endpoint và compute/storage được Azure quản lý. Người dùng cấu hình engine version, compute tier, storage, networking, authentication và các khả năng backup/HA.

~~~mermaid
flowchart TB
    APP[Java API trên AKS / App Service] --> NET[VNet / Firewall / Private DNS / TLS]
    NET --> DNS[MySQL Flexible Server FQDN]
    subgraph FLEX[Managed MySQL Flexible Server]
        P[(Primary MySQL)]
        DISK[(Managed storage)]
        HA[(Optional HA standby)]
        BK[(Automated backup / PITR)]
        P --> DISK
        P -. HA replication .-> HA
        P --> BK
    end
    DNS --> P
    P -. Async read replication .-> REP[(Optional read replica)]
    REPORT[Reporting worker] --> REP
    MON[Azure Monitor] --- FLEX
~~~

Sơ đồ này chỉ mô tả các thành phần logic. HA standby và read replica khác mục đích, truy cập và mô hình replication.

### 3.1. Resource và SQL databases

Ví dụ:

~~~text
Resource group: rg-shop-prod
└── MySQL Flexible Server: mysql-shop-prod
    ├── database: shopdb
    ├── database: reportingdb
    └── MySQL users / privileges
~~~

Một server có thể chứa nhiều databases; các tên schema, quyền và resource consumption vẫn cần được quản lý rõ.

### 3.2. Không có quyền OS root

Bạn không SSH vào host database để chỉnh sửa mọi file MySQL hay quản lý OS giống MySQL trên VM. Những server parameters được phép điều chỉnh qua dịch vụ managed; một số giới hạn khác thuộc trách nhiệm Azure.

## 4. Trách nhiệm chia sẻ

| Thành phần | Azure quản lý chính | Nhóm ứng dụng quản lý |
|---|---|---|
| Hạ tầng host | Provisioning, OS/service infrastructure | Region, SKU, scaling |
| Database runtime | Patching/maintenance theo dịch vụ | Version compatibility, upgrade validation |
| Storage | Storage platform | Capacity, IOPS, schema/index |
| HA | HA feature theo cấu hình | HA mode, app reconnect, thử failover |
| Backup | Automated backup theo chính sách | Retention, PITR drill, RPO/RTO |
| Networking | Tích hợp Azure network | Firewall, VNet, DNS, TLS |
| Identity | Tính năng auth được hỗ trợ | Users/grants, secrets/tokens, least privilege |
| SQL/data | MySQL engine | Schema, migration, transactions, indexes |
| Monitoring | Metrics/logging interfaces | Alerting, on-call, query tuning |
| Cost | Billing/metering | Resource sizing, budget và optimization |

**Azure RBAC quản lý server resource không tự động cấp quyền SELECT/INSERT bên trong MySQL.**

## 5. Khi nào chọn Flexible Server thay cho dịch vụ khác?

| Dịch vụ | Trường hợp phù hợp | Lưu ý |
|---|---|---|
| **Azure Database for MySQL Flexible Server** | Ứng dụng yêu cầu MySQL và muốn managed service | Giới hạn tính năng/parameters của managed MySQL |
| **Azure Database for PostgreSQL Flexible Server** | PostgreSQL ecosystem, extensions và data model | SQL dialect/driver không drop-in thay MySQL |
| **Azure SQL Database** | Ứng dụng thích hợp SQL Server/T-SQL | Engine/auth/queries khác MySQL |
| **MySQL on Azure VM** | Cần full OS/database control hoặc cấu hình managed chưa hỗ trợ | Tự quản lý HA, backup, patching và DR |
| **NoSQL database** | Mô hình document/key-value và access pattern phù hợp | Không thay thế trực tiếp relational constraints/joins |

Nếu ứng dụng đã dùng MySQL với stored procedures, triggers và các tính năng engine cụ thể, cần assessment compatibility trước khi chuyển nền tảng.

## 6. Những lựa chọn khi tạo server

Một Flexible Server cần xem đồng thời:

1. Subscription và resource group.
2. Region và data residency.
3. MySQL engine version đang được hỗ trợ.
4. Compute tier và VM/SKU.
5. vCores và memory.
6. Storage size, storage growth, IOPS.
7. HA mode nếu cần.
8. Backup retention và geo options khi hỗ trợ.
9. Networking mode, firewall/VNet/private DNS.
10. Authentication, SQL administrator và ứng dụng runtime users.
11. Maintenance window và monitoring.
12. Budget, tags và quy trình backup/cleanup.

**Đừng copy cấu hình dev/lab lên production** nếu SLO, dữ liệu và compliance khác nhau.

## 7. Compute tiers: Burstable, General Purpose, Memory Optimized

| Tier | Đặc tính | Phù hợp |
|---|---|---|
| **Burstable** | Compute có khả năng burst theo đặc tính SKU, thích hợp tải thấp/biến động | Lab, dev/test và workload nhỏ được đo |
| **General Purpose** | Cân bằng compute và memory | API CRUD, ứng dụng doanh nghiệp |
| **Memory Optimized** | Nhiều RAM trên mỗi vCore theo dòng SKU | Working set lớn, nhiều cache/reads |

Tên SKU, vCore range, khả năng bật HA, quotas và giá phụ thuộc region, phiên bản và thời điểm dịch vụ. Không nên dùng giá trị cứng từ một bảng giá cũ.

### 7.1. Khi nào Burstable không nên dùng?

- CPU thường xuyên cao liên tục.
- Batch jobs dài, báo cáo lớn.
- Latency production rất nhạy với thiếu CPU.
- Yêu cầu tính năng HA/capacity không có trên SKU đang chọn.

### 7.2. Khi nào Memory Optimized đáng chi phí?

Khi working set đọc thường xuyên đủ lớn để thêm InnoDB buffer pool giúp giảm disk reads. Nếu query quét bảng thiếu index hoặc bị locks, nhiều RAM không chắc là hướng sửa tối ưu.

## 8. Chọn vCores và memory bằng phép đo

Những yếu tố cần khảo sát:

- Peak queries/second và concurrent transactions.
- Read/write ratio.
- CPU, memory, active connections.
- Query p95/p99 và slow query samples.
- InnoDB buffer pool và disk reads.
- Batch jobs, reporting và maintenance windows.
- Dữ liệu tăng trong 3–12 tháng.
- Khả năng scale/restart và SLO.

Ví dụ orders-api đạt peak 300 HTTP requests/giây. Không thể từ đó suy trực tiếp số vCores MySQL vì một request có thể thực hiện 1 indexed SELECT hoặc 30 queries thiếu index.

**Benchmark với workload/dataset gần production** trước khi chốt cấu hình.

## 9. Storage, IOPS, throughput và autogrow

| Chỉ số | Vai trò | Dấu hiệu nghẽn |
|---|---|---|
| Provisioned storage | Không gian lưu dữ liệu/thành phần liên quan | Dung lượng sắp đầy |
| IOPS | Lượng thao tác đọc/ghi/giây | Nhiều queries chờ I/O |
| Throughput | Lượng dữ liệu đọc/ghi/giây | Full scans/batch I/O chậm |
| Read/write latency | Độ trễ storage operations | Transactions kéo dài |
| Autogrow | Tự tăng storage theo tính năng hỗ trợ | Giúp tránh hết capacity khi có ngưỡng |

### 9.1. Autogrow không thay thế capacity planning

Phải dự báo dung lượng, giám sát tăng trưởng và chi phí. **Không mặc định storage đã cấp phát có thể thu nhỏ trực tiếp khi xóa rows**; một số cấu hình chỉ cho phép tăng, cần migration/tạo server mới nếu muốn giảm kích thước provisioned.

### 9.2. Tối ưu trước khi tăng IOPS

Nếu SELECT quét toàn bảng thay vì dùng index, tăng IOPS có thể tốn tiền mà vẫn không giải quyết gốc. Kiểm tra EXPLAIN, schema và buffer pool.

## 10. High Availability trong Flexible Server

Flexible Server có các lựa chọn HA theo tính năng/region/SKU được hỗ trợ:

- **Same-zone HA:** primary và standby theo mô hình trong một Availability Zone.
- **Zone-redundant HA:** primary/standby được đặt ở các Availability Zones khác nhau trong cùng region nếu khả dụng.

~~~mermaid
flowchart LR
    API[Java app] --> DNS[MySQL FQDN]
    subgraph REGION[Azure region]
        subgraph ZONEA[Zone A]
            P[(Primary)]
        end
        subgraph ZONEB[Zone B]
            S[(HA standby)]
        end
        P -. Managed HA replication .-> S
    end
    DNS --> P
    S -. Failover .-> DNS
~~~

### 10.1. Standby có đọc được không?

**HA standby không phải read replica dùng cho báo cáo.** Chức năng chính là tăng khả năng phục hồi khi primary hoặc phần hạ tầng liên quan gặp sự cố.

### 10.2. Failover không đồng nghĩa zero downtime

Các kết nối có thể bị ngắt, in-flight transactions có thể thất bại, cần retry/reconnect và kiểm tra trạng thái commit. DNS endpoint nên được dùng thay vì hardcode IP.

### 10.3. HA không xử lý xóa nhầm

Nếu một câu SQL hợp lệ xóa nhầm đơn hàng, dữ liệu sai có thể xuất hiện ở cả primary/standby. Cần PITR hoặc cơ chế backup khác để phục hồi dữ liệu lịch sử.

## 11. Automated backups và Point-in-Time Restore

Flexible Server cung cấp automated backups và **Point-in-Time Restore (PITR)** theo retention/settings được hỗ trợ.

Các khái niệm:

- **Retention:** khoảng thời gian lịch sử đủ điều kiện khôi phục theo giới hạn dịch vụ.
- **PITR:** chọn thời điểm trước thao tác lỗi để dựng trạng thái dữ liệu tương ứng.
- **Restore target:** PITR thường tạo **một server mới** thay vì ghi đè ngay server đang hoạt động.
- **Geo-redundant backup/restore:** tùy region/tier/configuration; cần kiểm tra điều kiện và khả năng phục hồi liên vùng.

Ví dụ:

~~~text
09:00:00 Dữ liệu bình thường
09:20:00 Batch UPDATE chạy sai
09:21:00 Phát hiện vấn đề
09:23:00 Dừng job và tránh writes mới làm phức tạp phục hồi
09:30:00 Khôi phục ra server mới ở mốc trước 09:20
         Kiểm tra dữ liệu, rồi quyết định cutover hoặc trích xuất dữ liệu
~~~

**Không tự trỏ ứng dụng sang server restore chỉ vì server đã được tạo.** Cần xác minh schema, dữ liệu, users, network, DNS và những giao dịch sau mốc restore.

## 12. RPO và RTO: viết mục tiêu trước khi bật tính năng

- **RPO**: lượng dữ liệu theo thời gian tối đa có thể mất.
- **RTO**: thời gian tối đa chấp nhận để phục hồi dịch vụ.

Ví dụ một ứng dụng yêu cầu RPO 15 phút, RTO 60 phút. Chỉ bật backup không chứng minh đáp ứng yêu cầu, vì restore cần thời gian provision/copy, kiểm tra dữ liệu và cutover.

### 12.1. Runbook PITR

1. Ai được quyền tuyên bố sự cố?
2. Dừng hoặc hạn chế writes thế nào?
3. Mốc khôi phục được xác định từ log nào?
4. Restore server nằm ở đâu?
5. Quyền/MySQL users và network có được cấu hình phù hợp không?
6. So sánh row counts, transactions và business invariants thế nào?
7. Cập nhật ứng dụng trỏ sang endpoint mới bằng cách nào?
8. Có rollback nếu cutover không đạt không?
9. Ai xác nhận dữ liệu và kết thúc incident?

**Backup chưa từng được restore thử không phải bằng chứng đủ về năng lực phục hồi.**

## 13. HA, read replica, backup và DR khác nhau

| Cơ chế | Mục tiêu | Không thay thế |
|---|---|---|
| HA | Chịu một số lỗi instance/zone trong region | Backup lịch sử |
| PITR | Khôi phục dữ liệu theo mốc thời gian | Auto failover tức thì |
| Read replica | Tăng năng lực SELECT, một số kịch bản DR | Backup, HA tự động mặc định |
| Geo restore/DR topology | Phục hồi khi region gặp thảm họa | RPO=0 hoặc thao tác hoàn toàn tự động |
| App-level export/backup | Lưu dữ liệu theo yêu cầu riêng | Transaction consistency nếu cấu hình sai |

Một hệ thống quan trọng thường cần kết hợp HA + backup/restore test + DR plan đúng theo RPO/RTO.

## 14. Read replicas để mở rộng đọc

Read replica là server phụ nhận dữ liệu replicate từ primary, thường theo cơ chế **bất đồng bộ**, phục vụ các truy vấn đọc có thể chấp nhận data lag.

~~~mermaid
flowchart LR
    API[Orders API] --> PRIMARY[(Primary: reads + writes)]
    PRIMARY -. Async replication .-> REPLICA[(Read replica)]
    REPORT[Reporting worker] --> REPLICA
~~~

### 14.1. Ưu điểm

- Tách reporting khỏi primary.
- Tăng năng lực đọc của hệ thống.
- Tránh một số SELECT nặng làm tranh compute của primary.

### 14.2. Hạn chế

- Replica có thể đọc trạng thái cũ do **replication lag**.
- Không nên gửi writes thông thường tới read replica.
- Không tự động giải quyết write bottleneck.
- Không thể dùng làm PITR backup lịch sử.
- Không coi là giải pháp auto failover trừ khi đã thiết kế/tính năng hỗ trợ rõ.

### 14.3. Read-after-write

Sau khi user cập nhật đơn hàng, request tiếp theo cần thấy trạng thái vừa ghi nên cân nhắc đọc từ primary. Reporting dashboard có thể chấp nhận lag nếu SLO quy định rõ.

## 15. Networking: public access và private topology

Networking mode là một trong những lựa chọn nền tảng khi tạo Flexible Server.

### 15.1. Public access kèm firewall

Server có endpoint truy cập qua đường public theo cấu hình, nhưng Azure firewall rules giới hạn IP nguồn được phép.

~~~text
Developer workstation
        |
  Firewall allowlist + TLS
        |
mysql-lab.mysql.database.azure.com
~~~

Phù hợp cho một số lab hoặc mô hình được phê duyệt. Không nên mở toàn Internet chỉ để kết nối nhanh.

### 15.2. Private access / VNet integration

Trong topology hỗ trợ, Flexible Server có thể tích hợp mạng riêng qua delegated subnet và private DNS.

~~~text
AKS / App Service có VNet connectivity
             |
          Azure VNet
             |
         Private DNS
             |
       MySQL Flexible Server
~~~

Cần kiểm tra:

- VNet/subnet/delegation.
- IP space.
- Private DNS zone và VNet links.
- NSG/route/firewall.
- VPN/ExpressRoute nếu có on-prem.
- Nơi CI/CD, DBA, migration tools truy cập.

### 15.3. Private Endpoint khác VNet integration

Các khả năng **Private Link/Private Endpoint** phụ thuộc deployment mode và tính năng hiện hành của Flexible Server. Đừng giả định server ở mọi networking mode có thể chuyển sang private endpoint chỉ bằng một toggle.

### 15.4. Không hardcode IP

Dùng hostname của MySQL server. Failover/maintenance có thể làm endpoint định tuyến tới hạ tầng khác.

## 16. DNS và kết nối từ workload Azure

Endpoint ví dụ:

~~~text
mysql-shop-prod.mysql.database.azure.com
~~~

Từ máy hoặc Pod được phép:

~~~bash
nslookup mysql-shop-prod.mysql.database.azure.com
~~~

Kiểm tra cổng:

~~~bash
nc -vz mysql-shop-prod.mysql.database.azure.com 3306
~~~

Lệnh **nslookup** chỉ xác minh DNS resolution. Lệnh **nc** chỉ kiểm tra khả năng TCP connect, không xác nhận TLS/authentication hay quyền trên database.

### 16.1. Khi private DNS lỗi

- AKS Pod resolve sai IP.
- Máy trong VNet A kết nối được, VNet B không.
- On-prem có route nhưng DNS forwarding thiếu.
- App Service chưa có VNet integration hoặc outbound đúng.

Hãy kiểm tra DNS zone links, routing, private endpoint/delegated topology trước khi đổi firewall hoặc bỏ TLS.

## 17. TLS: mã hóa và xác minh MySQL server

Production nên yêu cầu TLS và **kiểm tra certificate identity** của server.

- **Không dùng TLS:** thiếu lớp mã hóa transport thích hợp.
- **TLS encryption only:** mã hóa kênh, nhưng có thể chưa xác minh đầy đủ hostname/certificate.
- **VERIFY_IDENTITY:** kiểm tra certificate chain và hostname khi client/truststore được cấu hình đúng.

Ví dụ MySQL CLI:

~~~bash
mysql \
  --host=mysql-shop-prod.mysql.database.azure.com \
  --port=3306 \
  --user=app_reader \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/secure/path/to/ca-bundle.pem \
  shopdb
~~~

**/secure/path/to/ca-bundle.pem** là placeholder. Chọn trust bundle được Azure/MySQL client chấp nhận và cập nhật khi certificate chain thay đổi. Trong lab một số client có thể dùng **REQUIRED** cho mã hóa, nhưng production nên xác minh server identity theo chính sách.

### 17.1. Certificate rotation

Không pin một certificate riêng lẻ mãi mãi khi dịch vụ có thể rotate. Quản lý truststore/JDK/Connector-J version và thử nghiệm trước khi certificate changes có hiệu lực.

## 18. MySQL authentication và Microsoft Entra ID

Các hình thức xác thực có thể gồm:

- **Native MySQL users/passwords:** cơ chế truyền thống.
- **Microsoft Entra authentication:** khi phiên bản, server configuration và client flow hỗ trợ.

Dùng Entra authentication có thể hỗ trợ passwordless trong một số thiết kế, nhưng phải cấu hình server administrator, Entra principal mapping, token acquisition/refresh và SQL grants phù hợp.

**Managed identity của AKS/App Service không tự tạo MySQL user hoặc quyền SELECT.** Azure Resource Manager role và SQL database authentication khác nhau.

### 18.1. Secret management

Nếu dùng native MySQL passwords:

- Đặt secrets trong Azure Key Vault hoặc secret store được phê duyệt.
- Không lưu trong Git, image, logs hay query strings.
- Rotate theo chính sách.
- Dùng tài khoản riêng từng workload/môi trường.
- Không dùng MySQL administrator cho application runtime.

## 19. Quyền Azure RBAC khác quyền MySQL

| Phạm vi | Ví dụ | Ý nghĩa |
|---|---|---|
| Azure resource management | Reader, Contributor trên Flexible Server | Quản lý metadata/resource configuration |
| MySQL login | user/password hoặc Entra principal mapping | Xác thực với database engine |
| MySQL grants | SELECT, INSERT, UPDATE, DELETE trên shopdb | Quyền thao tác bảng/schema |

Một nhân viên có **Azure Reader** không mặc nhiên được chạy SELECT từ shopdb; ngược lại, ứng dụng có tài khoản SQL không được phép thay đổi server SKU nếu không có Azure RBAC.

### 19.1. Least privilege

Tách **app_reader**, **app_writer** và admin. Không cấp DROP DATABASE, CREATE USER hoặc quyền global cho ứng dụng runtime chỉ để tránh lỗi permission.

## 20. SQL mẫu: tạo schema và index

Ví dụ MySQL 8.x trong database lab:

~~~sql
CREATE DATABASE IF NOT EXISTS shopdb
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE shopdb;

CREATE TABLE IF NOT EXISTS orders (
    order_id     VARCHAR(40) NOT NULL,
    customer_id  VARCHAR(40) NOT NULL,
    amount       DECIMAL(12,2) NOT NULL,
    status       VARCHAR(20) NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP NOT NULL
                 DEFAULT CURRENT_TIMESTAMP
                 ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    INDEX idx_customer_created (customer_id, created_at)
) ENGINE=InnoDB;
~~~

**utf8mb4_0900_ai_ci** là ví dụ collation theo phiên bản MySQL hỗ trợ; kiểm tra engine version trước khi áp dụng. Nếu không tương thích, chọn một utf8mb4 collation thích hợp.

### 20.1. DECIMAL cho số tiền

Dùng DECIMAL khi cần tiền tệ và phép tính chính xác trong phạm vi xác định, thay vì FLOAT/DOUBLE có sai số biểu diễn nhị phân.

### 20.2. InnoDB

InnoDB hỗ trợ transactions, row-level locking, foreign keys theo MySQL. Nó phù hợp với nhiều ứng dụng giao dịch.

### 20.3. Index không miễn phí

Index giúp đọc theo query pattern nhưng tốn storage và làm INSERT/UPDATE/DELETE cần thêm công việc.
## 21. Tạo MySQL users theo nguyên tắc least privilege

Ví dụ dưới đây chỉ là minh họa SQL và cần chạy bởi SQL administrator có quyền phù hợp:

~~~sql
CREATE USER 'shop_reader'@'%'
  IDENTIFIED BY 'REPLACE_WITH_SECURE_SECRET';

GRANT SELECT ON shopdb.*
  TO 'shop_reader'@'%';

CREATE USER 'shop_writer'@'%'
  IDENTIFIED BY 'REPLACE_WITH_ANOTHER_SECRET';

GRANT SELECT, INSERT, UPDATE, DELETE ON shopdb.*
  TO 'shop_writer'@'%';

SHOW GRANTS FOR 'shop_reader'@'%';
SHOW GRANTS FOR 'shop_writer'@'%';
~~~

**Không chạy placeholder như password thật và không commit SQL scripts chứa secrets vào Git.** Nếu tạo account bằng automation, credentials phải lấy từ hệ thống secrets được phê duyệt và không xuất ra logs.

### 21.1. Host wildcard và Azure firewall

Phần **'user'@'%'** là một biểu thức account host của MySQL. Nó không thay thế kiểm soát firewall/VNet ở Azure. Đồng thời, wildcard cũng không phải chính sách mạng chặt ở tầng SQL.

### 21.2. Không dùng admin cho Java application

Tài khoản ứng dụng thường không cần CREATE USER, GRANT, DROP DATABASE hay quyền global. Phân tách migration account, runtime writer và reporting reader theo mục đích.

## 22. Transactions và concurrency

Giả sử orders-api phải thêm một đơn và giảm tồn kho. Trong môi trường MySQL InnoDB, hai thao tác nên nằm trong một transaction nếu dữ liệu và nghiệp vụ đòi hỏi atomicity.

~~~sql
START TRANSACTION;

INSERT INTO orders (order_id, customer_id, amount, status)
VALUES ('ORD-1001', 'C-20', 125000.00, 'CREATED');

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 'P-100'
  AND quantity > 0;

-- Ứng dụng phải kiểm tra affected rows;
-- COMMIT chỉ khi mọi bước hợp lệ, nếu không ROLLBACK.
COMMIT;
~~~

**Lưu ý:** lệnh trên là minh họa logic, bảng inventory chưa được tạo ở mục trước. Trong code thật phải tạo bảng và kiểm tra số hàng UPDATE thành công; không COMMIT vô điều kiện nếu hàng tồn kho bằng 0.

### 22.1. ACID không loại bỏ deadlock

Concurrent transactions có thể gây deadlock, lock waits và retry. Thiết kế indexes, thứ tự update và transaction duration hợp lý, giảm thời gian giữ locks.

### 22.2. Optimistic concurrency

Khi bảng có cột version:

~~~sql
UPDATE products
SET price = 150000,
    version = version + 1
WHERE product_id = 'P-100'
  AND version = 7;
~~~

Nếu affected rows bằng 0, bản ghi có thể đã thay đổi. Ứng dụng cần xử lý conflict, không ghi đè mù.

### 22.3. Retry chỉ khi idempotent

Nếu connection chết ngay sau COMMIT nhưng trước response, client có thể không biết transaction đã thành công hay chưa. Retry nguyên lệnh INSERT với business key cố định và unique constraint an toàn hơn việc tạo orderId mới mỗi lần retry.

## 23. EXPLAIN và index: tối ưu trước khi tăng compute

Một API thường chạy:

~~~sql
SELECT order_id, amount, status, created_at
FROM orders
WHERE customer_id = 'C-20'
ORDER BY created_at DESC
LIMIT 20;
~~~

Index **(customer_id, created_at)** là một lựa chọn đáng kiểm tra vì query filter theo customer rồi sắp xếp theo created_at.

~~~sql
EXPLAIN
SELECT order_id, amount, status, created_at
FROM orders
WHERE customer_id = 'C-20'
ORDER BY created_at DESC
LIMIT 20;
~~~

Quan sát:

- Access method và key được dùng.
- Số rows optimizer ước tính.
- Có full scan hoặc extra sort không.
- Query có trả quá nhiều cột/dữ liệu không.
- Index selectivity có phù hợp dữ liệu thực không.

### 23.1. Index không phải luôn cải thiện mọi truy vấn

Index vừa tốn storage vừa làm INSERT/UPDATE phải cập nhật cấu trúc. Nếu dữ liệu nhỏ hoặc filter không chọn lọc, optimizer có thể không dùng index.

### 23.2. Tránh N+1

Nếu API lấy 100 orders rồi gọi 100 SELECT riêng để lấy khách hàng, tổng latency có thể cao dù từng query nhanh. Cần xem query count, JOIN/batch retrieval và caching có kiểm soát.

### 23.3. Không dùng EXPLAIN ANALYZE bừa bãi trên production

Một số chế độ phân tích có thể thực thi query và tạo overhead. Với câu lệnh thay đổi dữ liệu, cần hiểu rõ tác động trước khi chạy.

## 24. Kết nối Java với MySQL Connector/J và HikariCP

Ứng dụng Java dùng JDBC và connection pool để tái sử dụng connections. Một pool có cấu hình đúng giúp tránh tạo handshake/MySQL session mới trên mọi HTTP request.

Các dependency thường cần:

- **MySQL Connector/J** phù hợp MySQL/JDK version.
- **HikariCP** hoặc pool tương thích với framework.
- Logging/metrics để quan sát pool exhaustion.

### 24.1. JDBC URL qua TLS

Ví dụ cấu hình môi trường:

~~~text
DB_URL=jdbc:mysql://mysql-shop-prod.mysql.database.azure.com:3306/shopdb?sslMode=VERIFY_IDENTITY
DB_USER=shop_writer
DB_PASSWORD=<secret-provided-at-runtime>
~~~

DB_URL phải trỏ đến hostname thực; **VERIFY_IDENTITY** cần Java truststore và certificate chain tương thích. Password chỉ là placeholder, không nằm trong mã nguồn.

### 24.2. Java JDBC sample

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class OrdersRepository implements AutoCloseable {
    private final HikariDataSource pool;

    public OrdersRepository() {
        HikariConfig config = new HikariConfig();

        config.setJdbcUrl(requireEnv("DB_URL"));
        config.setUsername(requireEnv("DB_USER"));
        config.setPassword(requireEnv("DB_PASSWORD"));

        config.setMaximumPoolSize(5);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(5000);
        config.setPoolName("orders-db-pool");

        pool = new HikariDataSource(config);
    }

    public void createOrder(String orderId,
                            String customerId,
                            BigDecimal amount)
            throws SQLException {
        String sql =
            "INSERT INTO orders " +
            "(order_id, customer_id, amount, status) " +
            "VALUES (?, ?, ?, ?)";

        try (Connection conn = pool.getConnection();
             PreparedStatement statement =
                 conn.prepareStatement(sql)) {
            statement.setString(1, orderId);
            statement.setString(2, customerId);
            statement.setBigDecimal(3, amount);
            statement.setString(4, "CREATED");
            statement.executeUpdate();
        }
    }

    private static String requireEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing setting: " + key);
        }
        return value;
    }

    @Override
    public void close() {
        pool.close();
    }
}
~~~

Đây là ví dụ cơ bản; production cần error classification, transactions phù hợp, idempotency, request validation và metric pool usage.

### 24.3. PreparedStatement

PreparedStatement tránh ghép trực tiếp dữ liệu người dùng vào SQL và giúp giảm rủi ro SQL injection nếu dùng đúng. Không nối userInput trực tiếp thành WHERE clause string.

### 24.4. Đóng connection và đóng pool

Kết thúc try-with-resources trên connection lấy từ Hikari thường **trả connection vào pool**. Đóng HikariDataSource khi ứng dụng shutdown, không đóng cả pool sau mỗi request.

## 25. Connection pool và lỗi Too many connections

Giả sử có 20 AKS Pods, mỗi Pod cho phép tối đa 50 JDBC connections:

\[
20 \times 50 = 1.000\ \text{connections có thể mở}
\]

Tổng này có thể vượt giới hạn MySQL hoặc tốn bộ nhớ đáng kể.

### 25.1. Thiết kế pool thực tế

1. Đếm số Pods/instances tại peak.
2. Đo concurrent queries và query duration.
3. Chọn maximumPoolSize vừa đủ.
4. Đặt connection acquisition timeout.
5. Giám sát active/idle/waiting connections.
6. Dùng connection validation và retry phù hợp sau failover.
7. Tránh connection leaks và transactions kéo dài.
8. Không cố giữ quá nhiều idle connections.

### 25.2. Failover có thể gây connection storm

Khi primary đổi vai trò, nhiều connections cũ bị đóng. Nếu hàng trăm Pods retry cùng lúc, database có thể bị quá tải. Dùng backoff, jitter và retry budget có giới hạn.

### 25.3. Tăng max_connections không phải cách chữa mọi lỗi

Nếu nguyên nhân là pool bị leak hoặc cấu hình quá lớn, nâng server limits không giải quyết gốc. Cần tìm số connections thực, waiters và thời gian giữ mỗi connection.

## 26. Spring Boot và external configuration

Trong Spring Boot, thường để environment variables cấp các cấu hình mà không ghi password vào source.

Ví dụ biến môi trường:

~~~text
SPRING_DATASOURCE_URL=jdbc:mysql://mysql-shop-prod.mysql.database.azure.com:3306/shopdb?sslMode=VERIFY_IDENTITY
SPRING_DATASOURCE_USERNAME=shop_writer
SPRING_DATASOURCE_PASSWORD=<secret-from-approved-store>
SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE=5
~~~

Spring Boot hỗ trợ binding nhiều cấu hình từ environment variables theo quy tắc đặt tên của phiên bản framework. Kiểm tra cài đặt thực tế để chắc rằng pool size được áp dụng.

### 26.1. Không để ORM tự động sửa schema tùy tiện

Với production, nên sử dụng Flyway/Liquibase hoặc migration workflow có review và versioning, thay vì để ứng dụng tự DROP/CREATE schema ngoài kiểm soát.

### 26.2. Readiness và liveness

Nếu MySQL tạm không sẵn sàng, readiness có thể báo ứng dụng chưa thể nhận traffic. Không thiết kế liveness phụ thuộc trực tiếp database theo cách khiến toàn bộ Pods restart liên tục khi database chậm.

### 26.3. Passwordless cần cấu hình riêng

Nếu sử dụng Microsoft Entra authentication cho MySQL Flexible Server, client phải lấy/refresh token đúng flow và server phải có principal/grants thích hợp. Không chỉ bật managed identity mà kỳ vọng Connector/J tự động nhận token.

## 27. Azure Monitor và các tín hiệu hiệu năng

Một dashboard MySQL hữu ích:

| Tầng | Chỉ số | Tác dụng |
|---|---|---|
| Compute | CPU utilization, memory pressure | Xác định CPU/RAM bottleneck |
| Connections | Active/failed connections | Phát hiện pool limits/leaks |
| Storage | Used storage, growth | Dự báo đầy |
| I/O | IOPS, read/write latency | Xác định storage bottleneck |
| Query | Slow queries, p95/p99 query latency | Tìm SQL cần tối ưu |
| Transactions | Lock waits, deadlocks | Đánh giá contention |
| HA | Failover/availability events | Theo dõi gián đoạn kết nối |
| Replicas | Replication lag/health | Phát hiện reads lỗi thời |
| Backup/DR | Restore rehearsal outcomes | Chứng minh phục hồi |
| Billing | Compute, backup, storage, logs | Giữ ngân sách |

Không phải mọi giá trị đều là built-in Azure Monitor metric trong mọi SKU. Những metric như JDBC pool wait hay business query p99 thường cần **application instrumentation**.

### 27.1. Tracing end-to-end

~~~text
HTTP request
  -> Java application
  -> Chờ Hikari pool
  -> Gửi SQL
  -> MySQL xử lý
  -> Transaction commit
  -> HTTP response
~~~

Nếu p99 HTTP tăng, đối chiếu thời gian pool wait, query duration, network và MySQL CPU/IO thay vì quy toàn bộ lỗi cho database.

### 27.2. Logs chứa dữ liệu nhạy cảm

Slow query logs và query traces có thể chứa giá trị SQL hoặc IDs. Phải có retention/sampling, masking và role-based access phù hợp.

## 28. MySQL server parameters và slow query logs

Flexible Server cho phép chỉnh nhiều MySQL parameters qua Azure interfaces trong phạm vi hỗ trợ. Một số thay đổi dynamic, số khác yêu cầu restart.

Những nhóm cần biết:

- Character set/collation và SQL mode.
- Connection timeout/limits.
- Slow query logging.
- InnoDB/optimizer-related parameters trong phạm vi cho phép.
- Binary logging/replication-related behavior.
- Timezone và session settings theo hỗ trợ.

### 28.1. Quy trình thay parameter

1. Xác định vấn đề bằng số liệu.
2. Xem default và current value.
3. Đối chiếu MySQL version và Azure support.
4. Xác định thay đổi có gây restart không.
5. Thử staging.
6. Chọn maintenance window nếu cần.
7. Thay một nhóm nhỏ.
8. Đo lại p95/p99, errors, CPU/memory.
9. Có hướng phục hồi nếu làm xấu hiệu năng.

### 28.2. Azure CLI đọc parameters

~~~bash
az mysql flexible-server parameter list \
  --resource-group rg-shop-lab \
  --server-name mysql-shop-lab-unique \
  --output table
~~~

Đây là ví dụ sử dụng CLI cho môi trường lab; syntax/flags cần kiểm tra với phiên bản Azure CLI đang dùng.

## 29. Query tuning trước khi tăng SKU

Quy trình:

1. Nhận alert CPU hoặc latency tăng.
2. Xác định query pattern gây chậm.
3. Đo rows examined, số lần thực thi.
4. Dùng EXPLAIN trên môi trường cho phép.
5. Kiểm tra indexes, join order, filters.
6. Tìm N+1 queries từ ORM.
7. Tối ưu transactions và locks.
8. Load test lại.
9. Nếu vẫn thiếu compute/I/O, mới cân nhắc thay SKU.

### 29.1. Batch queries và caching

Batch queries có thể giảm round trips. Cache có thể giảm read load nhưng cần invalidation/TTL và không được dùng để trả dữ liệu đã stale khi nghiệp vụ yêu cầu mới nhất.

### 29.2. Đừng bật quá nhiều query logs

Logging mỗi truy vấn có thể tạo overhead, chi phí và rủi ro PII. Bật slow-query logging theo yêu cầu điều tra với retention phù hợp.

## 30. Maintenance, patching và major upgrades

Azure thực hiện những hoạt động bảo trì nền tảng, nhưng ứng dụng có thể gặp connection resets/restarts/failovers.

### 30.1. Maintenance window

Chọn giờ ít tải nếu dịch vụ hỗ trợ tùy chỉnh. Tránh lịch database maintenance trùng schema migration, batch settlement và deployment lớn.

### 30.2. Nâng cấp MySQL version

Major upgrade có thể ảnh hưởng:

- Reserved keywords/SQL syntax.
- Authentication plugins.
- Charset/collation.
- Query optimizer.
- Stored procedures/triggers.
- JDBC driver compatibility.
- Deprecated server parameters.
- Data migration và rollback path.

**Không mặc định Flexible Server cho phép downgrade trực tiếp sau major upgrade.** Cần kiểm tra supported versions và quy trình upgrade của dịch vụ tại thời điểm triển khai.

### 30.3. Checklist nâng cấp

1. Inventory schema, ứng dụng và drivers.
2. Đọc breaking changes.
3. Backup/restore rehearsal.
4. Dựng staging tương tự production.
5. Test CRUD, transactions, migrations và performance.
6. Có cutover/rollback plan.
7. Chọn maintenance window.
8. Theo dõi lỗi ứng dụng sau upgrade.

## 31. Mở rộng compute, storage và reads

Ba hướng chính:

- **Compute scale:** tăng/giảm vCores và memory theo SKU.
- **Storage/IOPS scale:** điều chỉnh dung lượng hoặc hiệu năng storage theo tính năng.
- **Read replica:** tách truy vấn SELECT chấp nhận stale data.

### 31.1. Thay compute có thể làm gián đoạn

Thay SKU hoặc scale compute có thể yêu cầu restart hoặc failover tùy hoàn cảnh. Ứng dụng cần reconnect và retry/idempotency.

### 31.2. Storage không dễ thu nhỏ

Không nên tăng storage vô hạn vì tưởng có thể giảm trở lại ngay sau khi xóa bảng. Dự toán chi phí lâu dài.

### 31.3. Read replica không chữa write lock

Nếu UPDATE inventory gây contention, tạo thêm read replica không làm giảm lock contention trên primary.

## 32. Disaster Recovery và sự cố liên vùng

RPO/RTO quyết định phương án DR.

| Sự cố | Cơ chế cần xem xét | Điều cần kiểm thử |
|---|---|---|
| Primary instance lỗi | HA failover | Reconnect và thời gian khôi phục |
| Zone failure | Zone-redundant HA nếu cấu hình hỗ trợ | Ứng dụng và mạng còn sẵn không |
| Xóa nhầm bảng | PITR restore | Dữ liệu, RPO/RTO, cutover |
| Region outage | Geo restore/DR architecture theo hỗ trợ | Region đích, data loss, networking |
| Reporting quá tải | Read replica | Lag và fallback |
| Connection storm | Pool limits/backoff | Peak scaling và failover |

### 32.1. HA trong region không bằng multi-region DR

Zone-redundant HA bảo vệ trước một số lỗi của zone trong region, không bảo vệ khỏi toàn bộ mất region.

### 32.2. Geo options cần kiểm tra trước

Các tính năng geo-redundant backups, cross-region replicas hoặc restore phụ thuộc tier/region, thời điểm và cấu hình. Không hứa RPO=0 hoặc tự động failover cross-region nếu chưa có giải pháp thực tế được kiểm chứng.

## 33. Migration từ MySQL tự quản lý

Migration nên bắt đầu bằng **assessment**, không phải lệnh copy đầu tiên.

### 33.1. Những thông tin cần kiểm tra

- MySQL engine/version/edition.
- DB/table sizes và growth.
- Charset/collation và timezone.
- Storage engine.
- Stored procedures, triggers, events.
- Users, grants, authentication plugins.
- Server parameters cần thiết.
- Queries có phụ thuộc quyền OS hoặc filesystem không.
- Downtime window và tốc độ thay đổi dữ liệu.
- Network/firewall/latency đến Azure.
- Binary logs/replication requirements nếu migration online.

### 33.2. Offline hay online?

| Hướng | Ưu điểm | Rủi ro |
|---|---|---|
| Offline dump/restore | Dễ giải thích và kiểm soát cho dataset nhỏ | Downtime theo thời gian dump/restore |
| Online/continuous replication migration | Giảm cutover downtime | Phức tạp consistency, log/replication và final sync |
| Dual-write ứng dụng | Có thể chuyển dần một số workload | Rủi ro lệch dữ liệu nếu không có protocol nghiêm ngặt |

Azure migration tools có thể hỗ trợ một số source/target configurations. Phải xác nhận đúng engine/version/topology thay vì khẳng định công cụ nào cũng tương thích.

## 34. Cutover runbook sang Flexible Server

1. Dừng schema changes trước window.
2. Xác nhận backup nguồn và restore thử.
3. Provision server đích, kiểm tra network/DNS/TLS.
4. Tạo users/roles theo quy trình.
5. Chạy migration và theo dõi progress.
6. So sánh row counts/checksums/business invariants.
7. Ngừng writes nguồn nếu plan đòi hỏi.
8. Đợi dữ liệu đích đồng bộ tới mốc cutover.
9. Cập nhật application secrets/connection config.
10. Chạy smoke tests CRUD, transaction, query latency.
11. Theo dõi error rate, slow queries, connection count.
12. Có điều kiện rollback và biết lúc nào rollback không còn an toàn.
13. Giữ nguồn trong thời gian đối soát trước khi xóa theo phê duyệt.

**Không xóa database nguồn khi mới chỉ thấy API trả HTTP 200**; phải xác minh dữ liệu và các giao dịch quan trọng.

## 35. Tạo Flexible Server lab trong Azure Portal

**Chỉ tạo tài nguyên trong subscription/resource group có quyền và ngân sách được phê duyệt.** Cách làm qua Portal cho phép nhìn cấu hình hiện hành của region/SKU thay vì phụ thuộc CLI flags theo phiên bản.

### 35.1. Chuẩn bị

- Resource group riêng như **rg-shop-lab**.
- Region phù hợp, ví dụ một region hỗ trợ MySQL Flexible Server.
- MySQL admin password được tạo/lưu an toàn.
- IP nguồn cố định hoặc VNet với đường vào private.
- Ngân sách và cleanup plan.

### 35.2. Các bước

1. Azure Portal → Create a resource.
2. Tìm **Azure Database for MySQL flexible server**.
3. Chọn subscription và resource group.
4. Chọn server name duy nhất và region.
5. Chọn MySQL engine version được hỗ trợ.
6. Chọn Burstable/compute nhỏ phù hợp lab nếu cấu hình hỗ trợ.
7. Chọn storage vừa đủ, xem IOPS/autogrow.
8. Với lab chưa cần HA, xem xét không bật HA để tránh chi phí; không áp dụng mặc định cho production.
9. Đặt backup retention hợp lệ theo lab.
10. Chọn networking:
    - Public access chỉ allowlist IP của máy lab; hoặc
    - Private topology khi đã có VNet/subnet/DNS.
11. Cấu hình administrator và secret.
12. Xem TLS policy, monitoring và tags.
13. Review + Create.
14. Ghi FQDN, tier, storage, network mode và chi phí dự kiến.

**Không mở firewall toàn Internet**, cũng không bật allow-all Azure services nếu chưa hiểu phạm vi.

### 35.3. Private access cần chuẩn bị trước

Một số mô hình private integration yêu cầu delegated subnet/private DNS và có hạn chế chuyển mode sau tạo. Kiểm tra khả năng hiện hành của Flexible Server trước khi chọn.

## 36. Azure CLI: kiểm tra server lab

Các lệnh read-only sau không đưa SQL password vào command line:

~~~bash
az login
az account set --subscription "<subscription-id>"

az mysql flexible-server show \
  --resource-group rg-shop-lab \
  --name mysql-shop-lab-unique \
  --output json

az mysql flexible-server list \
  --resource-group rg-shop-lab \
  --output table
~~~

Xem parameters:

~~~bash
az mysql flexible-server parameter list \
  --resource-group rg-shop-lab \
  --server-name mysql-shop-lab-unique \
  --output table
~~~

Với public-access lab có firewall:

~~~bash
az mysql flexible-server firewall-rule list \
  --resource-group rg-shop-lab \
  --name mysql-shop-lab-unique \
  --output table
~~~

**mysql-shop-lab-unique** là placeholder, không phải tài nguyên có thật. Cú pháp CLI, options và schema output có thể thay đổi; dùng trợ giúp CLI hiện hành để xác minh.

### 36.1. Vì sao không đưa password vào CLI create example?

Password đặt trong command-line dễ bị ghi vào shell history/process listing/CI logs. Nên provision bằng Portal, secure prompt hoặc cơ chế secrets/automation được chấp thuận.

## 37. Kết nối bằng MySQL CLI và xác minh session

Sau khi server, database, SQL account và certificate trust đã được thiết lập:

~~~bash
mysql \
  --host=mysql-shop-lab-unique.mysql.database.azure.com \
  --port=3306 \
  --user=shop_writer \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/secure/path/to/ca-bundle.pem \
  shopdb
~~~

Nếu login thành công:

~~~sql
SELECT VERSION();
SELECT DATABASE();
SELECT CURRENT_USER();
SHOW VARIABLES LIKE 'require_secure_transport';
SHOW STATUS LIKE 'Ssl_cipher';
~~~

**Các lệnh kiểm tra chỉ dùng trên server lab đã tạo**. Đường dẫn CA phải được thay bằng trust bundle đúng. Một số server/clients có tham số, hiển thị khác nhau theo MySQL version.

### 37.1. Kiểm tra bốn lớp

1. DNS resolution.
2. TCP/route/firewall.
3. TLS/hostname/certificate.
4. MySQL authentication và grants.

Nếu fail, xác định lớp lỗi cụ thể thay vì tắt TLS hoặc mở firewall rộng.

## 38. Bài thực hành SQL: schema, transactions, indexes

Trong database **shopdb** của lab:

~~~sql
CREATE TABLE IF NOT EXISTS products (
  product_id VARCHAR(40) NOT NULL,
  name VARCHAR(200) NOT NULL,
  price DECIMAL(12,2) NOT NULL,
  quantity INT NOT NULL,
  version INT NOT NULL DEFAULT 1,
  PRIMARY KEY (product_id),
  CHECK (quantity >= 0)
) ENGINE=InnoDB;

INSERT INTO products (product_id, name, price, quantity)
VALUES ('P-100', 'San pham demo', 125000.00, 10);

INSERT INTO orders (order_id, customer_id, amount, status)
VALUES ('ORD-1001', 'C-20', 125000.00, 'CREATED');

EXPLAIN
SELECT order_id, amount
FROM orders
WHERE customer_id='C-20'
ORDER BY created_at DESC
LIMIT 10;
~~~

Nếu chạy lại INSERT với cùng primary key có thể xảy ra duplicate key; đây là hành vi cần hiểu, không tự coi là lỗi dịch vụ.

### 38.1. Transaction demo

~~~sql
START TRANSACTION;

UPDATE products
SET quantity = quantity - 1,
    version = version + 1
WHERE product_id = 'P-100'
  AND quantity > 0;

SELECT ROW_COUNT() AS affected_rows;

-- Chỉ COMMIT nếu affected_rows=1 và các điều kiện khác hợp lệ.
-- Nếu không, phải ROLLBACK.
COMMIT;
~~~

Trong code ứng dụng phải **kiểm tra affected_rows và điều khiển COMMIT/ROLLBACK thực**, không chỉ chạy dòng COMMIT sau chú thích một cách vô điều kiện.

## 39. Lab kế hoạch HA, PITR và read replica

Các tính năng HA/replica/geo backup có thể phát sinh chi phí lớn. Có thể làm bài thiết kế trước, chỉ provision thêm khi có ngân sách/quyền.

### Phần A — HA

1. Xác định SKU/region có hỗ trợ same-zone hay zone-redundant HA không.
2. Vẽ primary và standby.
3. Mô tả những connections sẽ bị ảnh hưởng khi failover.
4. Viết retry/backoff và idempotency policy.
5. Không thử failover trên production.

### Phần B — PITR

1. Tạo bảng giả trong server lab.
2. Ghi lại mốc thời gian trước khi thay đổi dữ liệu.
3. Xác nhận retention còn hợp lệ.
4. Nếu ngân sách cho phép, restore **ra server mới**.
5. Xác minh row counts và nghiệp vụ.
6. Đo RTO thực tế.
7. Xóa server restore theo quy trình sau khi kết thúc.

### Phần C — Read replica

1. Xác định báo cáo có chấp nhận stale reads không.
2. Xem điều kiện read replica trong SKU/region.
3. Ước lượng chi phí compute/storage replica.
4. Lập kế hoạch replication lag monitoring.
5. Viết application routing: writes/critical reads về primary, reporting reads có thể sang replica.
6. Không bật replica chỉ để “có backup”.

## 40. Troubleshooting theo nhóm lỗi

### 40.1. DNS không resolve

Kiểm tra hostname đúng, private DNS zone, VNet links, DNS forwarding và endpoint topology.

### 40.2. TCP timeout port 3306

Kiểm tra firewall IP, NSG/routes, subnet, private endpoint/VNet integration, client outbound và VPN/ExpressRoute.

### 40.3. TLS/certificate failure

Kiểm tra Java truststore, CA chain, TLS mode, hostname và certificate rotation. Không sửa bằng cách tắt xác minh chứng chỉ trong production.

### 40.4. Access denied for user

Kiểm tra MySQL account host mapping, password/token, SQL grants và authentication mode. Azure RBAC Contributor không thay quyền SELECT.

### 40.5. Too many connections

Kiểm tra pool size nhân số Pods, connection leak, idle sessions, app retry storms và max connections. Không chỉ tăng server limit.

### 40.6. CPU cao

Phân tích slow queries, thiếu index, table scans, N+1, reporting và lock contention trước khi scale-up.

### 40.7. Storage gần đầy

Đo used storage, growth, autogrow, quota và temp files/logging. Xóa rows không tự thu nhỏ provisioned capacity.

### 40.8. Read replica lag

Xem write volume primary, replica workload, long transactions và replication status. Tránh stale reads cho dữ liệu cần consistency.

### 40.9. Failover làm API 5xx

Kiểm tra connection pool invalid connections, reconnect/backoff, transaction result uncertainty và application readiness.

### 40.10. PITR server mới chưa kết nối được

Kiểm tra VNet/firewall, DNS/FQDN, SQL user/grants, secrets, engine version và ứng dụng chưa đổi connection string.

## 41. Chi phí Flexible Server

| Hạng mục | Thành phần phát sinh |
|---|---|
| Compute | Tier, vCores/SKU, giờ chạy |
| Storage | Dung lượng provisioned, growth |
| IOPS/throughput | Cấu hình performance theo tính năng và mô hình giá |
| HA | Standby capacity và HA mode |
| Read replicas | Compute/storage của mỗi replica |
| Backup | Retention và dung lượng theo chính sách giá |
| Network | Private Link/egress/tài nguyên kết nối |
| Monitor | Logs/metrics ingestion, retention |
| DR | Geo backup/replication/restore rehearsal |

Không đưa một đơn giá cố định nếu chưa biết region, SKU, currency và thời điểm.

### 41.1. Tối ưu chi phí

- Chọn tier theo workload đo được.
- Sửa SQL/index trước khi tăng compute/IOPS.
- Đặt pool limits tránh connections dư thừa.
- Giám sát storage growth và backup retention.
- Không tạo read replica nếu không có workload đọc cần tách.
- Tạo budgets/tags trong Azure Cost Management.
- Dọn resource lab khi kết thúc.

### 41.2. Stop server lab có hết tính phí không?

Tính năng stop/start theo hỗ trợ có thể giảm compute cost trong một số điều kiện nhưng không làm mọi chi phí storage/backup biến mất; có giới hạn/điều kiện thời gian stop. Phải theo dõi tài nguyên và billing thực tế.

## 42. Kiến trúc ứng dụng Java production tham khảo

~~~mermaid
flowchart TB
    USER[Users] --> GW[Ingress / API Gateway]
    GW --> API[AKS orders-api Java]
    GW --> CAT[AKS catalog-api]
    API --> PRI[(MySQL primary)]
    CAT --> PRI
    PRI -. Async replication .-> READ[(Optional read replica)]
    REPORT[Reporting worker] --> READ
    API --> SEC[Key Vault / Identity integration]
    PRI --- HA[(Optional HA standby)]
    PRI --- BK[(Backup / PITR)]
    MON[Azure Monitor] --- PRI
    MON --- API
~~~

### Các quyết định

- Dùng private networking theo chính sách công ty khi phù hợp.
- Không hardcode IP hoặc SQL password trong container.
- Chọn pool size theo tổng Pods.
- Dùng read replica chỉ cho reads chấp nhận lag.
- Có HA/backup/DR đúng RPO/RTO.
- Giám sát connection errors, slow queries và storage.
- Quản lý schema migration bằng CI/CD có approval.

### MySQL + Service Bus outbox

Nếu app ghi MySQL rồi gửi message lên Service Bus, hai thao tác không tự nằm trong một ACID transaction xuyên dịch vụ. **Transactional outbox** là một mô hình giúp giảm nguy cơ DB commit thành công nhưng event send bị mất.

## 43. Bài thực hành tổng hợp

### A. Chuẩn bị

1. Subscription/resource group lab có quyền và ngân sách.
2. Chọn engine version/tier/storage/networking.
3. Đặt IP firewall riêng hoặc private VNet access.
4. Lưu secret an toàn, thiết lập TLS.
5. Xác định tiêu chí cleanup.

### B. Provision

1. Tạo MySQL Flexible Server qua Portal.
2. Ghi FQDN, tier, vCores, storage, backup retention.
3. Xác nhận DNS và TCP connectivity.
4. Kết nối MySQL CLI qua TLS.
5. Ghi trạng thái TLS/authentication.

### C. Database và security

1. Tạo shopdb và bảng orders.
2. Tạo role/users read-only và writer theo least privilege.
3. Kiểm tra SHOW GRANTS.
4. Chạy vài câu INSERT/SELECT mẫu.
5. Không để credentials trong Git.

### D. Java JDBC

1. Cấu hình MySQL Connector/J.
2. Sử dụng HikariCP pool nhỏ.
3. Chạy PreparedStatement để tạo order.
4. Kiểm tra duplicate key behavior.
5. Đo pool active/waiting connections.

### E. Tối ưu

1. Chạy EXPLAIN cho query theo customer.
2. So sánh với index phù hợp.
3. Theo dõi CPU/IO/query duration.
4. Không tăng SKU nếu chưa có bằng chứng.

### F. Phục hồi

1. Viết kịch bản xóa nhầm dữ liệu.
2. Chọn PITR time trước lỗi.
3. Nếu ngân sách cho phép, thực hiện restore ra server mới.
4. Kiểm tra dữ liệu và đo thời gian phục hồi.
5. Không cutover tự động khi chưa xác nhận tính đúng.

### G. Cleanup

1. Lưu báo cáo không chứa secrets.
2. Dừng ứng dụng lab.
3. Xác nhận server không chứa dữ liệu/tài nguyên dùng chung.
4. Xóa resource lab theo quyền và chính sách.
5. Kiểm tra Azure Cost Management.

**Bài thực hành hoàn thành khi bạn giải thích được lựa chọn tier/network, kết nối an toàn, thực hiện SQL/JDBC đúng và có bằng chứng về kế hoạch phục hồi.**

## 44. Checklist đưa Flexible Server vào production

- [ ] MySQL version được hỗ trợ và ứng dụng tương thích.
- [ ] Workload đã được đo để chọn tier/vCores/memory.
- [ ] Storage/IOPS/growth đã dự báo và có alerts.
- [ ] HA mode phù hợp SLO và hỗ trợ region/SKU.
- [ ] Backup retention đáp ứng business requirement.
- [ ] PITR restore đã được diễn tập và có RTO đo thực.
- [ ] Có DR plan cho region outage nếu cần.
- [ ] Không dùng read replica thay backup.
- [ ] Replication lag được theo dõi nếu có replicas.
- [ ] Firewall không mở Internet quá rộng.
- [ ] VNet/private DNS được kiểm tra từ workload thật.
- [ ] TLS với certificate verification được cấu hình đúng.
- [ ] Secrets không ở source/Git/logs.
- [ ] SQL users/grants theo least privilege.
- [ ] Azure RBAC và MySQL data-plane rights tách biệt.
- [ ] JDBC driver/HikariCP có limits/timeouts.
- [ ] App chịu được reconnect/failover và có idempotency.
- [ ] Schema migrations được review/versioned.
- [ ] Queries cốt lõi có EXPLAIN/index thích hợp.
- [ ] Slow query monitoring và logging retention được kiểm soát.
- [ ] Có metrics CPU, storage, connections, error rate.
- [ ] Có maintenance window và upgrade compatibility tests.
- [ ] Migration cutover có rollback/validation plan.
- [ ] Cost budget bao gồm HA, replicas, storage, monitoring.
- [ ] Có runbook incident và người chịu trách nhiệm.
- [ ] Không dùng SQL administrator làm account ứng dụng.
- [ ] Đã kiểm tra khả năng phục hồi sau xóa nhầm dữ liệu.

## 45. Câu hỏi tự kiểm tra

1. Flexible Server giảm những công việc MySQL nào cho đội vận hành?
2. Burstable, General Purpose và Memory Optimized phù hợp workload nào?
3. Vì sao CPU cao không phải lúc nào cần tăng vCores?
4. Storage autogrow có cho phép thu nhỏ storage sau xóa dữ liệu không?
5. Same-zone HA và zone-redundant HA khác nhau về failure domain?
6. HA standby có phải read replica dùng reporting?
7. HA có khôi phục được DELETE chạy nhầm không?
8. PITR thường tạo server khôi phục như thế nào?
9. RPO và RTO khác nhau ra sao?
10. Read replica có nhất quán tức thời với primary không?
11. Vì sao request sau write có thể cần read từ primary?
12. Public access/firewall khác private VNet integration như thế nào?
13. Vì sao private DNS và routing phải được thiết kế cùng nhau?
14. TLS REQUIRED khác VERIFY_IDENTITY?
15. Azure Contributor có tự được SELECT từ shopdb không?
16. Managed identity tự tạo MySQL user không?
17. Vì sao app_writer chỉ cần CRUD trên schema cụ thể?
18. PreparedStatement giải quyết rủi ro SQL injection như thế nào?
19. Pool 50 connections trên 20 Pods tạo nguy cơ gì?
20. Vì sao không dùng admin database account ở runtime?
21. EXPLAIN giúp phân tích điều gì?
22. Vì sao index vừa tăng read performance vừa tốn write overhead?
23. Slow query logs có thể chứa dữ liệu nhạy cảm nào?
24. Major upgrade cần kiểm tra SQL/driver/charset những gì?
25. Zone-redundant HA có thay thế DR multi-region không?
26. Migration online cần xác nhận consistency/cutover ra sao?
27. Vì sao server restore đã sẵn sàng nhưng app chưa chắc kết nối được?
28. Stop server lab có chấm dứt mọi chi phí không?
29. Vì sao restore drill quan trọng hơn chỉ thấy backup enabled?
30. Transactional outbox giúp gì khi ghi MySQL và gửi Service Bus event?

## 46. Tổng kết

**Azure Database for MySQL Flexible Server** là dịch vụ MySQL managed trên Azure, giảm công việc hạ tầng nhưng không thay thế thiết kế schema, security, performance tuning, backup/restore và quản trị ứng dụng.

Lựa chọn đúng phải cân nhắc **compute tier/vCores, memory, storage/IOPS, HA, automated backup/PITR, read replicas, networking, TLS và authentication**. Phân biệt rõ: **HA** xử lý một số lỗi hạ tầng; **PITR** phục hồi dữ liệu theo mốc; **read replicas** phục vụ reads có thể trễ; còn **DR** cần phương án ứng phó cả khi region bị ảnh hưởng.

Với ứng dụng Java, dùng **MySQL Connector/J, PreparedStatement, connection pooling giới hạn, secret/identity đúng cơ chế và idempotent retries**. Tối ưu bằng **EXPLAIN, indexes, transaction design và Azure Monitor** trước khi tăng compute hoặc IOPS. Một database vận hành tốt phải **phục hồi được, bảo vệ dữ liệu, giữ tính nhất quán, đáp ứng hiệu năng và kiểm soát chi phí Azure**.


