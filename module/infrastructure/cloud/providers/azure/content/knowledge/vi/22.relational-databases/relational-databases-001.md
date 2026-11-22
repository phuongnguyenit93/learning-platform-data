# Lựa chọn Azure SQL và cơ sở dữ liệu quan hệ được quản lý

Một ứng dụng bán hàng có đơn hàng, tồn kho, khách hàng và thanh toán cần dữ liệu nhất quán, giao dịch có thể rollback, truy vấn SQL và phương án khôi phục khi hệ thống gặp sự cố. Khi đưa ứng dụng lên Microsoft Azure, câu hỏi không chỉ là “chạy SQL ở đâu” mà là **chọn database engine, mức dịch vụ được quản lý, kiến trúc hiệu năng, bảo mật, HA/DR và chi phí phù hợp**.

Azure có nhiều dịch vụ cho dữ liệu quan hệ: **Azure SQL Database**, **Azure SQL Managed Instance**, **SQL Server on Azure Virtual Machines**, **Azure Database for PostgreSQL – Flexible Server** và **Azure Database for MySQL – Flexible Server**. Chúng đều hỗ trợ dữ liệu có cấu trúc, nhưng không cùng engine, khả năng tương thích, mô hình tính phí hoặc trách nhiệm quản trị.

Bài học thuộc chương **Cơ sở dữ liệu quan hệ** của mô-đun **CLOUD_PROVIDERS_AZURE**. Kiến thức liên kết với Azure subscription, resource group, Microsoft Entra ID, VNet, Private Endpoint, App Service, Azure Functions, AKS, Azure Monitor, bảo mật và kiểm soát chi phí một ứng dụng trên Azure.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nhận biết các workload quan hệ phù hợp với SQL, transaction, khóa ngoại và ACID.
2. Phân biệt database PaaS và SQL Server on Azure VM (IaaS), bao gồm trách nhiệm bảo trì/backup.
3. So sánh Azure SQL Database single database, elastic pool, serverless và Hyperscale.
4. Xác định khi nào nên dùng Azure SQL Managed Instance để di chuyển SQL Server hiện hữu.
5. Nhận biết các yêu cầu buộc phải chọn SQL Server trên VM.
6. Chọn PostgreSQL/MySQL Flexible Server khi ứng dụng dùng engine tương ứng.
7. So sánh service tiers DTU/vCore, General Purpose, Business Critical và Hyperscale.
8. Thiết kế yêu cầu backup, PITR, LTR, zone redundancy, geo-replication và RPO/RTO.
9. Hiểu Microsoft Entra authentication, managed identity, SQL database permissions và private networking.
10. Thực hành kiểm tra/tạo một Azure SQL Database và chạy các câu lệnh T-SQL mẫu.
11. Lập kế hoạch migration, benchmark, vận hành, monitoring và tối ưu TCO.
12. Đưa ra lựa chọn có căn cứ bằng ma trận yêu cầu, tình huống thực tế và checklist production.

**Lưu ý:** tên service tiers, regions, SKU, giới hạn và khả năng thay đổi theo thời gian. Ví dụ Azure CLI/SQL chỉ dùng cho lab được cấp phép, không tự thực thi. Trước khi đưa lên production, kiểm tra khả năng của phiên bản engine, vùng Azure và mô hình giá đang được hỗ trợ.

## 2. Vì sao cơ sở dữ liệu quan hệ quan trọng?

### 2.1. Dữ liệu có ràng buộc giữa các bảng

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : places
    ORDERS ||--|{ ORDER_ITEMS : contains
    CUSTOMERS {
        uniqueidentifier customer_id PK
        string name
    }
    ORDERS {
        uniqueidentifier order_id PK
        uniqueidentifier customer_id FK
        string status
    }
    ORDER_ITEMS {
        uniqueidentifier order_id FK
        string sku
        int quantity
    }
~~~

Các hệ quản trị dữ liệu quan hệ hỗ trợ:

- **Schema:** bảng, kiểu dữ liệu, constraints.
- **Primary key và foreign key:** đảm bảo các bản ghi tham chiếu hợp lệ.
- **Indexes:** tăng tốc truy vấn theo điều kiện truy cập.
- **SQL:** lọc, join, aggregate, update và transaction.
- **Transaction:** nhiều thay đổi được commit hoặc rollback theo các bảo đảm của engine.
- **Concurrency control:** isolation levels, locking hoặc MVCC tùy hệ quản trị.

Một hệ thống đặt hàng cần chống tình huống đơn hàng được tạo nhưng dòng hàng không tồn tại hoặc tổng số lượng kho bị cập nhật không nhất quán.

### 2.2. ACID giải quyết gì?

| Thuộc tính | Ý nghĩa | Minh họa |
|---|---|---|
| Atomicity | Các thao tác trong một transaction commit/rollback thành một đơn vị | Tạo Order và OrderItem cùng commit |
| Consistency | Dữ liệu tuân thủ constraints và quy tắc do thiết kế áp dụng | Foreign key không trỏ vào khách hàng không tồn tại |
| Isolation | Các transaction đồng thời không nhìn thấy những trạng thái sai theo isolation level | Hai người đặt món hàng cuối cùng |
| Durability | Commit được lưu theo cơ chế đảm bảo của dịch vụ/engine | Dữ liệu commit không chỉ nằm trong bộ nhớ process |

ACID **không tự chữa lỗi business logic**, không bảo đảm không xảy ra deadlock, và không có nghĩa geo-secondary bất đồng bộ sẽ mất 0 giao dịch khi cả region hỏng.

### 2.3. OLTP, analytics và workload hỗn hợp

- **OLTP:** nhiều giao dịch ngắn, truy vấn được index, cần p95 latency tốt.
- **Analytics/OLAP:** đọc/scan dữ liệu lớn, group/aggregate, báo cáo.
- **Mixed:** cùng một database phục vụ API transaction và báo cáo nặng.

Không chọn tier chỉ dựa vào dung lượng GB. DB 20 GB có hàng nghìn TPS có thể đòi hỏi nhiều compute hơn DB 1 TB ít được truy cập. Nếu báo cáo gây nghẽn giao dịch, có thể cần read replica, ETL/warehouse hoặc kiến trúc analytics chuyên dụng.

## 3. Shared responsibility: PaaS và IaaS khác nhau

### 3.1. Những lớp khách hàng và Azure quản lý

~~~mermaid
flowchart LR
    U["Ứng dụng / API"] --> P["Managed SQL PaaS"]
    U --> V["SQL Server trên Azure VM"]
    P --> M["Azure quản lý OS/engine infrastructure, patching, backups theo service"]
    V --> O["Khách hàng quản lý OS, SQL instance, backups, HA"]
    M --> D["Khách hàng vẫn chịu trách nhiệm dữ liệu, schema, quyền, query"]
    O --> D
~~~

**PaaS không có nghĩa không cần DBA.** Azure xử lý nhiều hạ tầng, nhưng khách hàng vẫn quản lý schema, quyền database, truy vấn, application connection pooling, compliance, phục hồi dữ liệu nghiệp vụ và lựa chọn HA/DR.

### 3.2. Ma trận trách nhiệm

| Công việc | Azure SQL Database | Azure SQL Managed Instance | SQL Server VM |
|---|---|---|---|
| Hệ điều hành và hạ tầng DB cơ bản | Azure | Azure | Chủ yếu khách hàng |
| SQL engine servicing/patching | Dịch vụ Azure | Dịch vụ Azure | Khách hàng phối hợp triển khai |
| Automated backups | Dịch vụ quản lý theo policy | Dịch vụ quản lý theo policy | Khách hàng thiết kế hoặc dùng công cụ hỗ trợ |
| HA cơ sở của dịch vụ | Theo service tier | Theo service tier | Phải thiết kế/quản trị |
| Backup retention và DR objectives | Khách hàng quyết định | Khách hàng quyết định | Khách hàng quyết định |
| Index/query/schema | Khách hàng | Khách hàng | Khách hàng |
| SQL data permissions | Khách hàng | Khách hàng | Khách hàng |
| Truy cập OS | Không | Không | Có |
| Trách nhiệm licensing | Theo mô hình PaaS | Theo mô hình PaaS | Theo VM/SQL licensing |

Một bản backup đã được dịch vụ tạo **không thay thế việc thử restore** và đối soát dữ liệu. Một PaaS được vá tự động **không thay thế việc quản lý driver và SQL injection trong ứng dụng**.

## 4. Tổng quan các lựa chọn trên Azure

| Dịch vụ | Engine | Kiểu quản lý | Thường phù hợp |
|---|---|---|---|
| **Azure SQL Database** | Microsoft SQL/T-SQL ở cấp database | PaaS | App cloud-native, microservices, SaaS DB-per-tenant |
| **Azure SQL Managed Instance** | SQL Server-compatible ở cấp instance | PaaS | Migration SQL Server cần nhiều tính năng cấp instance |
| **SQL Server on Azure VM** | SQL Server do doanh nghiệp quản lý | IaaS | Legacy, vendor requirements, OS/full instance control |
| **PostgreSQL Flexible Server** | PostgreSQL | PaaS | App PostgreSQL, JSONB, ecosystem/extensions hỗ trợ |
| **MySQL Flexible Server** | MySQL | PaaS | Ứng dụng MySQL, web/CMS/e-commerce |

### 4.1. Cây quyết định ban đầu

~~~mermaid
flowchart TD
    Q["Engine đang dùng hoặc được chọn?"] --> E{"Đã có engine?"}
    E -->|PostgreSQL| PG["Azure Database for PostgreSQL Flexible Server"]
    E -->|MySQL| MY["Azure Database for MySQL Flexible Server"]
    E -->|SQL Server/T-SQL| S{"Cần instance-level features?"}
    E -->|Chưa| X["Đánh giá ecosystem, SQL features, skills, TCO"]
    X --> E
    S -->|Không| DB["Azure SQL Database"]
    S -->|Có, MI hỗ trợ| MI["Azure SQL Managed Instance"]
    S -->|Cần OS/full control| VM["SQL Server Azure VM"]
    DB --> C{"Nhiều DB tải lệch nhau?"}
    C -->|Có| EP["Elastic pool"]
    C -->|Không| SD["Single DB / tier phù hợp"]
~~~

Đây chỉ là **bộ lọc**, không phải kết luận kiến trúc. Các yêu cầu bắt buộc về compliance, latency, licensing, HA/DR và migration compatibility phải được xác minh trước khi quyết định.

### 4.2. Azure SQL không phải tên chung cho mọi SQL engine

Một ứng dụng sử dụng PostgreSQL extensions, PL/pgSQL, PostGIS hoặc JSONB không thể chạy trên Azure SQL Database bằng việc đổi connection string. Một ứng dụng MySQL phụ thuộc charset, storage engine hoặc stored programs cũng vậy. Tương tự, SQL Server Agent jobs và T-SQL stored procedures không tự chạy trên MySQL/PostgreSQL.

## 5. Azure SQL Database: dịch vụ PaaS ở cấp database

### 5.1. Logical server không phải SQL Server VM

~~~mermaid
flowchart LR
    A["App Service / Functions / AKS"] --> L["Azure SQL logical server endpoint"]
    L --> D1["Database orders"]
    L --> D2["Database inventory"]
    L --> D3["Database payments"]
    D1 --> B["Automated backups / PaaS HA"]
    D2 --> B
    D3 --> B
~~~

**Logical server** là resource quản lý chứa các SQL databases và một số cấu hình networking/authentication. Nó không phải một VM để người dùng RDP vào SQL Server OS. Compute/scale của database hoặc elastic pool được quản lý theo mô hình chọn.

### 5.2. Single database

Phù hợp khi một ứng dụng có một database hoặc vài DB có workload riêng:

- Muốn billing và performance sizing ở từng DB.
- Không cần SQL Server Agent, OS-level control hoặc instance features không được hỗ trợ.
- Muốn giảm vận hành OS/engine.
- Muốn autoscale hoặc chọn service tier theo khả năng sản phẩm.

Ví dụ API Orders trên App Service kết nối một SQL Database ordersdb qua Microsoft Entra identity và Private Endpoint.

### 5.3. Elastic pool

Elastic pool cho phép nhiều Azure SQL databases chia sẻ một pool tài nguyên compute phù hợp. Ví dụ SaaS có 100 khách hàng, mỗi khách hàng một DB, peak sử dụng lệch nhau theo giờ.

~~~text
09:00 Tenant A, B nhiều giao dịch.
12:00 Tenant C, D nhiều giao dịch.
18:00 Tenant E xử lý batch.
Các database còn lại tải thấp.
~~~

Thay vì provision dư tài nguyên cho từng single DB, elastic pool có thể mang lại hiệu quả. Nhưng nếu các tenant cùng cao điểm hoặc một tenant tiêu thụ I/O lớn, pool vẫn có thể nghẽn. Cần xem:

- Tổng và peak CPU/IO/log throughput.
- Per-database min/max limits theo tier.
- Peak concurrency giữa các tenants.
- Storage và tốc độ tăng dữ liệu.
- Khả năng cô lập những tenants có yêu cầu đặc biệt.
- Chi phí pool so với tập single databases thực tế.

**Elastic pool không phải auto-sharding** và không tạo schema/data isolation đúng thay ứng dụng; mỗi tenant DB vẫn cần security, backup và vận hành.

### 5.4. Serverless compute

Ở những tổ hợp Azure SQL Database tier/compute được hỗ trợ, serverless có thể:

- Tự điều chỉnh compute trong giới hạn min/max đã cấu hình.
- Có thể auto-pause/auto-resume khi thỏa điều kiện cụ thể.
- Vẫn tính phí storage và các khoản khác ngay cả khi compute pause.
- Có resume latency khi ứng dụng kết nối lại.
- Không auto-pause nếu luôn có kết nối hoặc tác vụ nền ngăn pause.

**Serverless không luôn rẻ hơn provisioned**. Với ứng dụng 24/7 hoặc SLA yêu cầu phản hồi ngay sau thời gian idle, phải đo chi phí thật và cold-resume latency. Một số tiers/hardware/regions có giới hạn và tính năng khác nhau.

### 5.5. Hyperscale

Hyperscale là một service tier của Azure SQL Database dùng kiến trúc storage/compute khác các tiers phổ biến, có thể phù hợp khi:

- Database lớn hoặc tăng trưởng nhanh.
- Cần các khả năng backup/restore và scaling/storage của Hyperscale.
- Có workload đọc phù hợp với các lựa chọn replicas được hỗ trợ.
- Đã benchmark performance và tổng chi phí.

Không mặc định Hyperscale luôn nhanh nhất hoặc tốt nhất. Cần đối chiếu supported features, service limits, region, khả năng zone redundancy, compute model và yêu cầu migration/rollback.

### 5.6. Giới hạn với SQL Server truyền thống

Azure SQL Database không hỗ trợ mọi tính năng SQL Server ở cấp instance theo cách y hệt SQL Server VM. Khi migration, kiểm tra:

- SQL Server Agent và job scheduling.
- Linked servers/instance-level objects.
- Cross-database queries/transactions.
- SQL CLR và extended server features.
- File-system/OS integration.
- Server-level settings và security model.
- T-SQL syntax và compatibility level.
- Third-party driver/extension requirements.

Nếu ứng dụng không thể thay thế tính năng cấp instance, tiếp tục đánh giá Managed Instance hoặc SQL Server VM.

## 6. Azure SQL Managed Instance

### 6.1. Mục tiêu sản phẩm

Azure SQL Managed Instance (MI) phục vụ nhiều workload SQL Server cần tính tương thích **instance-level** rộng hơn SQL Database nhưng muốn Azure quản lý phần lớn infrastructure. Ví dụ hệ thống ERP cũ có SQL Agent jobs, nhiều databases và stored procedures phức tạp.

### 6.2. Điểm nổi bật

- Managed instance chứa và quản lý nhiều databases.
- Hỗ trợ nhiều SQL Server instance features hơn Azure SQL Database.
- Có các service tiers/capacity options và HA/backup PaaS theo cấu hình.
- Có mô hình network, subnet và DNS đặc thù.
- Có thể giảm chỉnh sửa code trong một số migration SQL Server so với SQL Database.
- **Vẫn có những tính năng không được hỗ trợ/khác biệt** so với SQL Server on VM.

Managed Instance **không cấp quyền RDP vào OS**, không cho tùy ý cài OS-level drivers, agents hoặc SQL Server binaries. Những phụ thuộc loại đó cần được đánh giá riêng.

### 6.3. VNet và subnet dành cho MI

MI triển khai vào cấu hình mạng được tích hợp VNet theo mô hình riêng. Các yêu cầu về subnet delegation, CIDR, route, NSG, kết nối hybrid và DNS cần được chuẩn bị theo tài liệu MI trước provisioning.

Không lấy hướng dẫn Private Endpoint của Azure SQL Database rồi áp trực tiếp mọi bước cho MI. Network model, endpoint, port và kiểm soát bảo mật không hoàn toàn giống nhau.

### 6.4. Khi nào không cần MI?

- Chỉ có một DB mới, không cần instance features.
- Muốn serverless compute phù hợp tải không đều tại DB level.
- Muốn elastic pool cho nhiều tenant databases.
- Ứng dụng dùng PostgreSQL/MySQL.
- Chi phí provisioned MI không phù hợp tải nhỏ.
- Cần quyền OS/full SQL binaries không có trên MI.

**Migration compatibility assessment vẫn bắt buộc**, dù ứng dụng nguồn đang chạy Microsoft SQL Server.

## 7. SQL Server on Azure Virtual Machines

### 7.1. Khi cần full control

SQL Server trên Azure VM phù hợp nếu:

- Vendor chỉ chứng nhận SQL Server chạy trên một phiên bản Windows/Linux/VM setup cụ thể.
- Cần OS-level access, SQL Server version, drivers hoặc agents.
- Cần tính năng SQL Server chưa có trên SQL Database/MI.
- Đang lift-and-shift hệ thống legacy và chưa thể rewrite.
- Có đội DBA/SRE đủ năng lực vận hành patch, backup, HA/DR.

### 7.2. Trách nhiệm đi kèm

| Hạng mục | Việc cần thực hiện |
|---|---|
| OS | Patch/hardening, disk encryption, EDR, firewall |
| SQL Server | Instance/version/CU, engine configuration |
| Disk I/O | Data/log/tempdb layout, IOPS/throughput/caching |
| Backup | Lịch, retention, encryption, offsite backup, thử restore |
| HA | Availability Groups/replicas, listener/quorum theo thiết kế |
| DR | Secondary region, runbook failover/failback |
| Monitoring | OS và SQL metrics, deadlocks, query waits |
| Capacity | VM CPU/RAM, disks, peak/auto-scaling strategy |
| Licensing | SQL Server license và Azure Hybrid Benefit nếu đủ điều kiện |

Azure cung cấp các công cụ/extension trợ giúp SQL VM và Azure Backup ở những kịch bản được hỗ trợ, nhưng không biến VM thành SQL PaaS.

### 7.3. VM chưa chắc rẻ hơn PaaS

Khi so chi phí, cộng cả license, disks, backup, HA replicas, secondary region, DBA on-call, patching và thời gian xử lý sự cố. Chỉ so một VM/giờ với một database vCore/giờ thường là phép so không công bằng.

## 8. PostgreSQL và MySQL Flexible Server

### 8.1. PostgreSQL Flexible Server

Phù hợp khi ứng dụng dựa trên PostgreSQL:

- Driver psycopg/Npgsql/JDBC PostgreSQL.
- PostgreSQL SQL dialect, PL/pgSQL, JSON/JSONB.
- Các extensions được Azure hỗ trợ theo version và khu vực.
- Workloads cần PostgreSQL-compatible relational engine.
- Muốn Azure quản lý phần lớn OS/engine servicing/backup.

Nếu ứng dụng phụ thuộc PostGIS hoặc extension khác, hãy kiểm tra **extension cụ thể** và version được Flexible Server hỗ trợ, không chỉ đọc tên sản phẩm PostgreSQL.

### 8.2. MySQL Flexible Server

Phù hợp khi ứng dụng chạy MySQL:

- Website, CMS và ứng dụng giao dịch sử dụng MySQL drivers.
- MySQL schema, InnoDB, stored programs và collation.
- Cần PaaS HA, backup, quản lý compute/storage theo khả năng dịch vụ.

Kiểm tra chính xác engine version, charset, collations, SQL modes, plugins và migration support.

### 8.3. Không trộn ba SQL dialects

| Mục | Azure SQL / SQL Server | PostgreSQL | MySQL |
|---|---|---|---|
| SQL dialect | T-SQL | PostgreSQL SQL, PL/pgSQL | MySQL SQL |
| SDK/driver thường dùng | Microsoft.Data.SqlClient, JDBC SQL Server | Npgsql, psycopg, JDBC PG | MySQL Connector/J |
| JSON | JSON features theo phiên bản SQL engine | JSON/JSONB | JSON theo version MySQL |
| Stored procedures | T-SQL và feature matrix | PL/pgSQL / languages | MySQL stored programs |
| Engine-specific extensions | SQL Server features | PostgreSQL extensions được hỗ trợ | MySQL plugins/features được hỗ trợ |

Đổi engine cần schema conversion, sửa SQL/stored code và test dữ liệu. Không thể chỉ đổi connection string.

### 8.4. Network và HA không giống Azure SQL

PostgreSQL/MySQL Flexible Server có các lựa chọn private/public connectivity, VNet integration/Private Link, backup, HA, read replicas tùy engine, tier, region và chế độ tạo server. Một số chuyển đổi network mode có ràng buộc; **phải xác định networking lúc thiết kế**, không đến migration xong mới quyết định.

## 9. Service tiers và compute purchasing models

### 9.1. DTU và vCore

**DTU-based** là cách biểu diễn tài nguyên tổng hợp CPU/memory/I/O trong những service objectives. **vCore-based** cung cấp cách chọn compute theo vCores, hardware family, storage và tier.

Không có phép quy đổi 1 DTU = X vCore chính xác cho mọi workload. Khi đổi mô hình tính giá, phải benchmark CPU, memory, read/write IO, log rate, transaction latency và cost.

### 9.2. General Purpose, Business Critical và Hyperscale

| Tier | Hướng sử dụng | Cần đo |
|---|---|---|
| General Purpose | Cân bằng giá/hiệu năng cho nhiều workload | CPU, latency, log rate, I/O limits |
| Business Critical | OLTP cần latency/availability characteristics cao hơn theo cấu hình | Compute/storage overhead, cost, replica support |
| Hyperscale | Database rất lớn, kiến trúc storage/compute mở rộng | Tăng trưởng, backup/restore, supported features |
| DTU Basic/Standard/Premium | Tiers theo DTU service objectives | DTU usage, limits và cost |

Tính năng zone redundancy, read replicas, serverless compute, failover hoặc hardware families **không giống nhau ở mọi tier**. Kiểm tra feature matrix theo SKU và region trước khi coi một tính năng là sẵn có.

### 9.3. Chọn capacity từ metrics

Thu thập:

1. CPU trung bình/đỉnh theo giờ, tuần, cuối tháng.
2. Memory working set và cache behavior.
3. Data size, growth rate và storage constraints.
4. Reads/writes, IOPS, latency và log generation rate.
5. Transactions/second, concurrent users/connections.
6. p95/p99 query durations và service latency.
7. Query execution plans, expensive queries, deadlocks.
8. Backup/restore times, HA/DR requirements.
9. Expected peak sau khi App Service/AKS/Functions scale-out.
10. Budget và headroom.

**Nâng tier không sửa được ứng dụng có N+1 queries**, index sai hoặc transaction giữ lock quá lâu.

### 9.4. Provisioned hay serverless?

| Tiêu chí | Serverless nếu hỗ trợ | Provisioned |
|---|---|---|
| Tải gián đoạn | Có thể lợi | Compute idle vẫn có chi phí |
| Tải ổn định 24/7 | Không chắc tiết kiệm | Dễ dự toán |
| Auto-pause/resume | Có điều kiện | Thường không theo cùng mô hình |
| Resume latency | Cần kiểm tra | Không có auto-resume từ pause |
| Compute config | Min/max theo mô hình | Chọn provisioned capacity |
| Storage cost | Vẫn tính | Vẫn tính |

Không giả định một DB có job định kỳ, monitoring hoặc connection pool đang mở sẽ pause đúng thời gian dự kiến. Chỉ quyết định sau quan sát idle periods và benchmark.

## 10. High availability, backup và disaster recovery

### 10.1. Phân biệt cơ chế

| Cơ chế | Giải quyết | Không tự giải quyết |
|---|---|---|
| Service HA | Hỏng node/hạ tầng trong phạm vi service tier | Mất toàn region trong mọi trường hợp |
| Zone redundancy | Một số lỗi Availability Zone | Xóa nhầm dữ liệu |
| Automated backups | Phục hồi dữ liệu theo retention | RTO tức thì |
| PITR (point-in-time restore) | Khôi phục tại mốc thời gian được hỗ trợ | Tự rollback production trong một lệnh |
| LTR (long-term retention) | Lưu các bản backup dài hạn theo policy | Retention vô hạn mặc định |
| Geo-replication / failover groups | DR giữa regions theo cấu hình | RPO=0 trong mọi failure |
| App retry/reconnect | Transient failover errors | Sửa được transaction logic sai |

Azure SQL Database/MI có automated backups theo dịch vụ. Khách hàng phải quản lý retention, geo-backup strategy, restoration process và đáp ứng yêu cầu nghiệp vụ.

### 10.2. RPO và RTO

- **RPO:** tối đa dữ liệu chấp nhận mất nếu có sự cố, đo theo thời gian.
- **RTO:** tối đa thời gian mục tiêu để khôi phục dịch vụ.

Ví dụ một nghiệp vụ xác định mục tiêu:

~~~text
RPO <= 5 phút
RTO <= 60 phút
~~~

Đây là **mục tiêu nội bộ**, không phải cam kết mọi Azure SQL tier tự đáp ứng. Geo-replication có thể bất đồng bộ nên secondary có replication lag. Failover còn phụ thuộc DNS/listener, drivers, app reconnection và kiểm tra dữ liệu.

### 10.3. Point-in-time restore

Quy trình khôi phục một database bị xóa nhầm bản ghi:

1. Tìm mốc thời gian cuối cùng dữ liệu còn đúng.
2. Xác nhận PITR retention của database.
3. Restore tới mốc hợp lệ; trong các kịch bản SQL Database thường tạo **database phục hồi mới**.
4. Xác minh dữ liệu/permissions và tính toàn vẹn.
5. Đối soát giao dịch phát sinh sau mốc restore.
6. Chọn cách merge dữ liệu hoặc cutover ứng dụng có approval.
7. Theo dõi sau phục hồi và lưu bằng chứng UTC.

**Không cho rằng restore tương đương undo an toàn mọi transaction sau thời điểm X.** Các đơn hàng đúng có thể được tạo sau mốc khôi phục.

### 10.4. LTR và backup policy

Khi compliance yêu cầu giữ bản backup lâu dài:

- Xác định retention weekly/monthly/yearly theo khả năng sản phẩm.
- Chọn region và data residency phù hợp.
- Kiểm tra storage encryption/CMK nếu cần.
- Diễn tập restore từ bản LTR, đo RTO thực.
- Tính phí lưu backup và network.
- Quản lý quyền xóa policy và phá dữ liệu.
- Ghi owner/legal/privacy requirements.

Không tự chọn LTR nhiều năm chỉ vì “phòng xa”; cần cân đối nghĩa vụ pháp lý, quyền xóa dữ liệu và chi phí.

### 10.5. Geo-replication và failover

Với sản phẩm/tier hỗ trợ:

- Đánh giá topology primary/secondary và replication lag.
- Xác định automatic/manual failover theo policy.
- Kiểm tra read-write/read-only listener và application routing.
- Xác nhận DNS, firewall, Private Endpoint và identity ở vùng secondary.
- Thử reconnect/retry sau failover; có thể phải làm mới pooled connections.
- Đo RPO/RTO và kế hoạch failback.
- Cân nhắc dữ liệu mất nếu failover xảy ra trước khi secondary nhận đủ transaction logs.

**Read replica không phải backup chống lỗi logic**: việc xóa nhầm dữ liệu có thể được replicate.

### 10.6. Flexible Server có cơ chế riêng

PostgreSQL/MySQL Flexible Server hỗ trợ backup, PITR, HA/read replicas theo engine và configuration. Không áp sơ đồ SQL Database failover group cho PostgreSQL/MySQL nếu chưa xác minh service-specific HA/DR behavior.

## 11. Networking: kết nối database an toàn

### 11.1. Kiến trúc khái niệm

~~~mermaid
flowchart LR
    C["Clients"] --> API["APIM / Front Door"]
    API --> APP["App Service / Azure Functions / AKS"]
    APP --> V["VNet integration / AKS network"]
    V --> DNS["Private DNS"]
    DNS --> PE["Private connectivity"]
    PE --> SQL["Managed relational database"]
    APP --> ID["Managed Identity / Entra token"]
    ID -. "Auth token" .-> SQL
    APP --> MON["Application Insights"]
    SQL --> MON
~~~

Một mạng riêng không tự tạo quyền SELECT. Cần đủ **DNS, route/TCP, TLS, authentication và database authorization**.

### 11.2. Azure SQL Database connectivity

Các mô hình có thể gồm:

- Public endpoint cùng firewall/IP rules.
- VNet service endpoint rules ở cấu hình hỗ trợ.
- **Private Endpoint / Azure Private Link**.
- Chặn public network access khi private path đã được kiểm thử.

Một SQL logical server có hostname ví dụ:

~~~text
sqlorderslab.database.windows.net
~~~

Khi dùng Private Endpoint, client thường tiếp tục dùng hostname SQL canonical trong driver; DNS thông qua zone liên quan **privatelink.database.windows.net** sẽ trỏ tới private IP khi được cấu hình đúng.

**Không hard-code private IP** để “chữa DNS”: sẽ gây rủi ro certificate hostname verification, failover và thay đổi endpoint. Kiểm tra DNS từ chính workload runtime:

~~~bash
nslookup sqlorderslab.database.windows.net
~~~

Kết quả trên laptop không chứng minh Pod AKS hoặc Azure Function có cùng route/DNS.

### 11.3. Đừng mở mạng quá rộng

Tùy chọn Azure SQL “Allow Azure services and resources to access this server” có phạm vi rộng hơn một ứng dụng riêng. Không bật nó chỉ để xử lý một lỗi connection timeout khi chưa hiểu security boundary. Thay vào đó, xác định subnet, VNet integration, Private Endpoint, DNS resolver, firewall và NSG theo thiết kế.

### 11.4. Managed Instance và Flexible Server

- **Managed Instance:** yêu cầu subnet/VNet networking và các điều kiện riêng của MI; cần xem port, delegation, route, private/hybrid access theo tài liệu.
- **PostgreSQL/MySQL Flexible Server:** có networking models khác SQL Database; việc chọn private/public mode lúc provisioning có thể ảnh hưởng khả năng chuyển đổi sau này.
- **SQL Server VM:** dùng VM NIC, NSG, route và SQL listener/port theo instance configuration; khách hàng trực tiếp harden network và OS.

### 11.5. Phân lớp khi điều tra connection

1. **DNS:** server hostname phân giải được không?
2. **TCP/network:** traffic tới đúng port, subnet, endpoint không?
3. **TLS:** driver xác minh certificate/hostname không?
4. **Authentication:** SQL login/Entra token có hợp lệ không?
5. **Authorization:** principal có CONNECT/SELECT/EXECUTE đúng DB/schema không?
6. **Query/runtime:** có timeout, deadlock hoặc throttling không?

Không cấp quyền db_owner để sửa DNS lỗi; không mở public firewall chỉ vì thiếu SQL permissions.

## 12. Identity, SQL permissions và bảo mật

### 12.1. Management plane khác data plane

| Lớp | Ví dụ | Kiểm soát |
|---|---|---|
| Azure RBAC | Reader/Contributor trên Azure SQL resource | Tạo/sửa/xóa resource, management operations |
| Microsoft Entra ID | User/group/managed identity | Danh tính login/token |
| SQL data-plane rights | CONNECT, SELECT, INSERT, EXECUTE, GRANT | Quyền thao tác trong database |
| Network | Firewall/Private Endpoint/VNet | Đường kết nối |
| Application authorization | User A được xem đơn hàng nào | Quyền nghiệp vụ |

Một Azure Contributor trên resource group **không mặc định có SQL SELECT**. Một Azure Function vừa bật managed identity **không tự có user trong database**.

### 12.2. Microsoft Entra và managed identity

~~~mermaid
sequenceDiagram
    participant A as App Service / Function
    participant M as Managed Identity Endpoint
    participant E as Microsoft Entra ID
    participant S as Azure SQL Database
    A->>M: Xin token cho SQL
    M->>E: Xác thực identity nền tảng
    E-->>M: Access token
    M-->>A: Token
    A->>S: Kết nối TLS với token
    S->>S: Kiểm tra DB user và quyền
    S-->>A: Kết quả hoặc lỗi permission
~~~

Managed identity giảm nhu cầu lưu SQL password, nhưng vẫn phải tạo database principal và cấp quyền theo engine. Phải tách runtime app identity, migration identity và DBA/break-glass identity.

### 12.3. T-SQL minh họa cấp quyền tối thiểu

Khi đã cấu hình Microsoft Entra admin và đăng nhập vào **đúng database** bằng principal có quyền, ví dụ:

~~~sql
-- Tên principal phải khớp Microsoft Entra identity phù hợp.
CREATE USER [mi-orders-api] FROM EXTERNAL PROVIDER;

-- Chỉ đọc schema sales đã tồn tại.
GRANT SELECT ON SCHEMA::sales TO [mi-orders-api];
~~~

Tên hiển thị có thể trùng; cần xác minh Entra principal/object ID và cú pháp hỗ trợ ở sản phẩm. Không giả định tên bất kỳ luôn resolve đúng object. Với ứng dụng cần ghi, chỉ cấp GRANT cụ thể cho bảng/schema/procedure cần thiết; tránh db_owner thường trực.

### 12.4. .NET connection string mẫu

Với Microsoft.Data.SqlClient phiên bản hỗ trợ Active Directory Default:

~~~text
Server=tcp:sqlorderslab.database.windows.net,1433;
Database=ordersdb;
Encrypt=True;
TrustServerCertificate=False;
Authentication=Active Directory Default;
~~~

Đây là ví dụ trình bày nhiều dòng. Cần kiểm tra driver, credential selection và Entra permissions. Với user-assigned identity, lựa chọn client ID theo hướng dẫn SDK/driver tương ứng; **client ID khác principal/object ID**.

### 12.5. SQL authentication khi bắt buộc

Nếu ứng dụng cũ dùng SQL username/password:

- Không đưa password thật vào source, Dockerfile, IaC plain text hoặc logs.
- Dùng Key Vault/secret manager được phê duyệt.
- Xoay secret theo lịch và sau khi lộ.
- Giới hạn quyền SQL user.
- Tách credentials từng môi trường.
- Dùng TLS và certificate verification.
- Có kế hoạch chuyển sang Entra identity khi khả thi.

### 12.6. Encryption và auditing

- **TLS:** mã hóa trong quá trình truyền dữ liệu.
- **TDE:** encryption at rest được dịch vụ hỗ trợ, không ngăn người có SELECT hợp lệ đọc plaintext.
- **Customer-managed key:** dùng khi có yêu cầu kiểm soát key, với Key Vault/HSM, rotation và recovery.
- **Always Encrypted:** client-side encryption cho một số columns theo engine/driver hỗ trợ, có ảnh hưởng query.
- **Auditing:** ghi nhận sự kiện theo chính sách, bảo vệ logs và retention.
- **Defender for SQL/Defender for Cloud:** phát hiện posture/threat theo gói đã bật.
- **Data classification/masking:** hỗ trợ governance; không thay database authorization.

Runtime identity không nên có quyền DDL/database admin. Một lỗ hổng injection cùng quyền DROP/ALTER có thể phá dữ liệu nhiều hơn một tài khoản chỉ có SELECT/INSERT theo nghiệp vụ. Dùng parameterized queries và secure coding độc lập với quyền DB.

## 13. Hiệu năng: chọn tier sau khi hiểu ứng dụng

### 13.1. Vì sao query chậm?

Một SQL query chậm có thể do:

- Không có index phù hợp với điều kiện lọc hoặc join.
- Execution plan sử dụng scan hoặc join strategy không phù hợp.
- Query trả quá nhiều rows/cột; SELECT * không cần thiết.
- ORM tạo N+1 queries và quá nhiều network round trips.
- Transaction giữ lock lâu, contention hoặc deadlocks.
- CPU, memory, log throughput hoặc I/O đạt giới hạn tier.
- Connection pool exhaustion; mở connection mỗi HTTP request.
- Statistics cũ, parameter-sensitive plans hoặc index fragmentation trong tình huống phù hợp.
- Thay đổi schema/tối ưu hóa có regression.
- Database/network ở region khác với application gây latency.

**Nâng compute vCore không tự sửa query N+1**, transaction lock dài hoặc SQL injection. Hãy đo và xử lý đúng bottleneck.

### 13.2. Những metrics nên xem

| Metric | Câu hỏi | Hành động có thể |
|---|---|---|
| CPU utilization | DB compute đã chạm giới hạn? | Tối ưu query rồi cân nhắc scale |
| Data I/O | Đọc/ghi data pages quá mức? | Index/query, tier/storage assessment |
| Log write rate | Transactions ghi log là bottleneck? | Giảm batch/transaction overhead, chọn capacity |
| Memory pressure | Working set/plan cache có đủ? | Index/query/memory tier |
| Sessions/connections | Có connection leak hoặc burst? | Pooling và app-side concurrency |
| Query duration p95/p99 | Ảnh hưởng trải nghiệm người dùng? | So baseline, Query Store |
| Deadlocks | Tranh chấp lock do thiết kế? | Lock ordering, transaction scope, retry |
| Storage usage | Tốc độ tăng data/index? | Capacity forecast và retention |
| Replication lag | DR/replica có stale data? | Kiểm tra topology và RPO |
| Failed connections | Lỗi network/auth/capacity? | Điều tra từng lớp |

Query Store và các công cụ performance insights của Azure SQL giúp quan sát queries/plans và regressions theo tính năng engine. Không bật automatic tuning không có chủ đích nếu môi trường yêu cầu phê duyệt thay đổi schema/index.

### 13.3. Connection pooling đặc biệt quan trọng với cloud autoscaling

Giả sử Azure Functions scale lên 80 instances, mỗi instance được cấu hình SQL connection pool tối đa 40 connections. Nếu cùng đồng loạt sử dụng tối đa, về mặt lý thuyết có thể có **3.200 connections**. Đây là phép nhân minh họa; thực tế driver/instances có thể không mở hết pool, nhưng rủi ro connection storm là có thật.

Một chiến lược tốt:

1. Mở connection gần lúc chạy query và đóng/trả về pool đúng cách.
2. Không giữ transaction trong lúc chờ HTTP API bên ngoài.
3. Dùng parameterized SQL và tránh query N+1.
4. Giới hạn pool size và concurrency theo SKU/DB limits.
5. Theo dõi p95 DB dependency latency khi HPA/Functions scale.
6. Sử dụng retry transient có backoff và thời hạn rõ ràng.
7. Không retry toàn bộ transaction có side effect nếu chưa bảo đảm idempotency.
8. Cân nhắc Queue/Service Bus làm bộ đệm khi có workload burst.

### 13.4. Read replica và workload báo cáo

Các lựa chọn read replica/read-only routing khác nhau theo SQL service tier hoặc Flexible Server engine. Khi dùng:

- Kiểm tra tính năng và điều kiện replica được hỗ trợ.
- Tách reporting queries khỏi OLTP chính nếu có lợi.
- Hiểu replication lag, consistency và read-after-write behavior.
- Không chuyển truy vấn nghiệp vụ đòi dữ liệu vừa commit sang replica stale.
- Đo chi phí/throughput của replica.
- Không coi replica là backup chống xóa dữ liệu nghiệp vụ.

## 14. Thực hành: Azure SQL Database và schema quan hệ

### 14.1. Phạm vi lab

Trong bài, giả định Azure SQL **logical server đã tồn tại** do nhóm hạ tầng tạo và cấu hình theo chính sách bảo mật. Ta tạo một database mới và chạy T-SQL minh họa.

~~~text
Subscription: <SUBSCRIPTION_ID>
Resource group: rg-sql-lab
Logical SQL server: sqlorderslab
Database: ordersdb
Region: theo server đã tạo
Compute: General Purpose vCore objective có hỗ trợ
~~~

Không tự chạy các lệnh tạo database production. Việc provision database phát sinh chi phí, và tên logical server trong ví dụ có thể chưa tồn tại.

### 14.2. Xác định subscription và đọc cấu hình server

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"

az sql server show \
  --resource-group rg-sql-lab \
  --name sqlorderslab \
  --query "{name:name,location:location,fullyQualifiedDomainName:fullyQualifiedDomainName}" \
  --output json
~~~

Nếu logical server chưa tồn tại, cần provisioning qua Portal hoặc IaC theo quy trình identity/networking/admin của tổ chức. Bài này không hướng dẫn truyền SQL administrator password thật qua command line để tránh nguy cơ lộ trong shell history, process inspection hoặc CI logs.

### 14.3. Tạo một database

Giả sử SKU/hardware trong region cho phép service objective minh họa:

~~~bash
az sql db create \
  --resource-group rg-sql-lab \
  --server sqlorderslab \
  --name ordersdb \
  --service-objective GP_Gen5_2
~~~

**GP_Gen5_2 chỉ là service objective ví dụ**. Kiểm tra SKU availability, giới hạn storage, tier và region trước khi chạy. Không mặc định đây là cấu hình tối ưu cho production.

Kiểm tra sau khi tạo:

~~~bash
az sql db show \
  --resource-group rg-sql-lab \
  --server sqlorderslab \
  --name ordersdb \
  --query "{name:name,status:status,edition:edition,sku:sku,location:location}" \
  --output json

az sql db list \
  --resource-group rg-sql-lab \
  --server sqlorderslab \
  --output table
~~~

Các lệnh này dùng **Azure management plane**, không chứng minh SQL login/data-plane permissions đã hoạt động.

### 14.4. Kết nối với Microsoft Entra authentication

Trước khi truy vấn:

1. DBA đã cấu hình Entra admin/permissions cho SQL logical server và database.
2. Máy có route, firewall/Private Endpoint, DNS và TLS đúng.
3. Người chạy có quyền SQL CONNECT và các quyền bảng.
4. SQL client/driver hỗ trợ kiểu Entra authentication dự định.

Ví dụ với sqlcmd version có hỗ trợ tùy chọn Entra authentication:

~~~bash
sqlcmd \
  -S sqlorderslab.database.windows.net \
  -d ordersdb \
  -G \
  -Q "SELECT DB_NAME() AS CurrentDatabase;"
~~~

Phiên bản sqlcmd/ODBC có cách cấu hình TLS/auth khác nhau; kiểm tra sqlcmd --help và tài liệu driver thực tế. Không bật TrustServerCertificate hoặc bỏ TLS hostname verification để chữa lỗi kết nối.

### 14.5. Tạo bảng và constraints

Chạy T-SQL trong **ordersdb** bằng principal có quyền DDL ở lab:

~~~sql
CREATE SCHEMA sales;
GO

CREATE TABLE sales.Customers
(
    CustomerId uniqueidentifier NOT NULL
        CONSTRAINT PK_Customers PRIMARY KEY,
    DisplayName nvarchar(200) NOT NULL,
    CreatedAtUtc datetime2(3) NOT NULL
        CONSTRAINT DF_Customers_CreatedAtUtc DEFAULT SYSUTCDATETIME()
);
GO

CREATE TABLE sales.Orders
(
    OrderId uniqueidentifier NOT NULL
        CONSTRAINT PK_Orders PRIMARY KEY,
    CustomerId uniqueidentifier NOT NULL,
    Amount decimal(18, 2) NOT NULL,
    Status varchar(20) NOT NULL,
    CreatedAtUtc datetime2(3) NOT NULL
        CONSTRAINT DF_Orders_CreatedAtUtc DEFAULT SYSUTCDATETIME(),

    CONSTRAINT FK_Orders_Customers
        FOREIGN KEY (CustomerId)
        REFERENCES sales.Customers(CustomerId),

    CONSTRAINT CK_Orders_Amount
        CHECK (Amount >= 0),

    CONSTRAINT CK_Orders_Status
        CHECK (Status IN ('pending', 'paid', 'canceled'))
);
GO

CREATE INDEX IX_Orders_CustomerId_CreatedAtUtc
    ON sales.Orders(CustomerId, CreatedAtUtc DESC);
GO
~~~

Giải thích:

- **uniqueidentifier** là lựa chọn ID minh họa, không mặc định tốt cho mọi table/index.
- **decimal(18,2)** phù hợp hơn float đối với nhiều giá trị tiền tệ cố định, nhưng cần quy định currency/tax/rounding.
- Foreign key ngăn tạo Orders với CustomerId không tồn tại.
- CHECK ngăn amount âm và status ngoài tập hợp minh họa.
- Index theo CustomerId và CreatedAtUtc hỗ trợ một nhóm query cụ thể nhưng có chi phí storage/write.

### 14.6. Transaction commit hoặc rollback

~~~sql
DECLARE @CustomerId uniqueidentifier = NEWID();
DECLARE @OrderId uniqueidentifier = NEWID();

BEGIN TRY
    BEGIN TRANSACTION;

    INSERT INTO sales.Customers (CustomerId, DisplayName)
    VALUES (@CustomerId, N'Khách hàng thử nghiệm');

    INSERT INTO sales.Orders (OrderId, CustomerId, Amount, Status)
    VALUES (@OrderId, @CustomerId, 150000.00, 'pending');

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
~~~

Đây là T-SQL, **không phải PostgreSQL/MySQL syntax**. Trong ứng dụng thực, mỗi Order phải tham chiếu khách hàng đã có nếu nghiệp vụ yêu cầu; tạo Customer mới trong cùng transaction chỉ để minh họa atomicity.

Truy vấn:

~~~sql
SELECT TOP (10)
    o.OrderId,
    c.DisplayName,
    o.Amount,
    o.Status,
    o.CreatedAtUtc
FROM sales.Orders AS o
JOIN sales.Customers AS c
  ON c.CustomerId = o.CustomerId
ORDER BY o.CreatedAtUtc DESC;
GO
~~~

### 14.7. Kiểm thử least privilege

Tại database, có thể tạo principal chỉ đọc cho Entra managed identity ứng dụng:

~~~sql
-- Chỉ chạy khi Entra admin, principal và schema đã được chuẩn bị.
CREATE USER [mi-orders-reader] FROM EXTERNAL PROVIDER;
GRANT SELECT ON SCHEMA::sales TO [mi-orders-reader];
GO
~~~

Một số môi trường cần cấu hình ánh xạ identity hoặc kiểm tra quyền cụ thể; không mặc định tên display luôn ánh xạ duy nhất. Kiểm chứng bằng **chính app identity**, không phải login DBA. Người đọc không cần quyền ALTER/DROP/CONTROL.

### 14.8. Kết thúc lab và chi phí

Azure SQL Database provisioned có thể tiếp tục tính phí. Chỉ xóa những resource lab được xác định chắc chắn không còn được dùng hoặc có data cần giữ. Không chạy lệnh xóa SQL server chứa nhiều databases chỉ để cleanup một bài học; theo dõi Azure Cost Management và budget.

## 15. Kết nối ứng dụng cloud-native tới database

### 15.1. Kiến trúc mẫu

~~~mermaid
flowchart LR
    C["Client"] --> F["Front Door / API Management"]
    F --> APP["App Service / Azure Functions"]
    APP --> VN["VNet integration"]
    VN --> PE["Private Endpoint + Private DNS"]
    PE --> DB["Azure SQL Database"]
    APP --> MI["Managed Identity / Entra ID"]
    MI -. "Token" .-> DB
    APP --> MON["Application Insights"]
    DB --> MON
~~~

Trong mô hình này:

- API ingress/gateway xử lý request, không mang database admin password.
- Managed identity giúp app lấy token SQL.
- Private Endpoint hạn chế network path.
- SQL principal có quyền dữ liệu tối thiểu.
- Backup/PITR và DR thiết kế theo business SLA.
- Monitoring theo dõi cả application và database.

### 15.2. Azure Functions và database scale

Azure Functions có thể scale out đột ngột. Nếu mỗi Function instance mở nhiều SQL connections, DB có thể bị connection storm:

- Đặt giới hạn pool và concurrency.
- Sử dụng async I/O hợp lý với driver.
- Không giữ transaction mở khi gọi API bên ngoài.
- Thử load với burst và cold start.
- Không dựa vào SQL serverless auto-resume khi SLA yêu cầu latency rất thấp.
- Dùng queue để đệm và điều tiết tốc độ ghi.
- Kiểm tra transient retry và idempotency.

### 15.3. AKS và database

Một AKS deployment có 30 Pods, mỗi Pod có nhiều workers và connection pools. Cần tính tổng capacity, không chỉ số Pod. Kết nối riêng cần VNet DNS/routing; Microsoft Entra Workload ID có thể cấp danh tính cho Pods theo cơ chế được hỗ trợ.

**Kubernetes RBAC không phải database SQL permissions.** Một ServiceAccount có quyền read Pod không vì thế được SELECT bảng Orders.

## 16. Di chuyển dữ liệu sang Azure: assessment trước cutover

### 16.1. Chọn landing zone theo compatibility

~~~mermaid
flowchart TD
    S["SQL Server hiện hữu"] --> A["Inventory + Assessment"]
    A --> Q{"Có phụ thuộc instance-level / OS?"}
    Q -->|Không| DB["Candidate: Azure SQL Database"]
    Q -->|Có, MI hỗ trợ| MI["Candidate: SQL Managed Instance"]
    Q -->|Cần OS/full SQL control| VM["Candidate: SQL Server VM"]
    DB --> T["Migration pilot + performance tests"]
    MI --> T
    VM --> T
    T --> C["Cutover + validation + fallback"]
~~~

Với database nguồn là PostgreSQL/MySQL, phải dùng assessment và migration plan riêng cho engine. Không dùng một công cụ SQL Server migration cho mọi database quan hệ.

### 16.2. Inventory trước migration

Ghi nhận:

- Engine/version/edition và trạng thái end-of-support.
- Số databases, size, growth rate, file layout.
- Stored procedures, triggers, functions, views.
- SQL Agent, linked servers, integration services, cross-database queries.
- SQL CLR, custom plugins, OS dependencies.
- Collation, case sensitivity, timezone, encoding.
- Logins/users, permissions, Entra integration, encryption.
- Throughput, CPU, memory, I/O, connections, query latency.
- Backup schedule, restore testing, RPO/RTO.
- Dependencies từ ứng dụng, drivers, config, hard-coded hostnames.
- Downtime budget, data residency, cutover window.

### 16.3. Công cụ và phương pháp

Có thể đánh giá các giải pháp migration/assessment được Microsoft hỗ trợ như Azure Database Migration Service, Azure SQL migration guidance/tools, backup/restore, schema conversion và replication theo **đúng source/target/version**.

Online migration và offline migration có trade-offs:

| Phương án | Ưu điểm | Rủi ro |
|---|---|---|
| Offline/cutover theo downtime | Luồng đơn giản hơn | Cần downtime theo dung lượng và tốc độ |
| Online/replication | Giảm downtime khi được hỗ trợ | Replication lag, cutover complexity, data validation |
| Lift-and-shift VM | Ít thay đổi engine/OS bước đầu | Giữ gánh nặng vận hành |
| Replatform MI | PaaS với tương thích SQL Server rộng hơn | Feature/network/sizing assessment |
| Modernize SQL Database | Kiến trúc cloud-native database-level | Thay đổi code/instance features có thể lớn |
| Re-engine đổi engine | Chuẩn hóa theo PostgreSQL/MySQL hoặc khác | Chi phí chuyển schema/code và rủi ro cao |

Support matrix thay đổi; không hứa migration online “zero downtime” cho mọi engine hoặc database size.

### 16.4. Quy trình 12 bước

1. **Discover:** liệt kê database và dependencies.
2. **Assess:** phân tích unsupported features.
3. **Design:** chọn engine/tier/network/identity/HA/DR.
4. **Provision:** tạo target theo IaC, tags, monitoring và security.
5. **Prepare:** migration tooling, backup và rollback plan.
6. **Convert:** chỉnh schema/SQL/features nếu cần.
7. **Pilot:** migrate subset, test queries và dữ liệu.
8. **Benchmark:** so latency, throughput, CPU, lock behavior.
9. **Rehearse:** thử cutover/failback và data reconciliation.
10. **Cutover:** đóng băng writes hoặc điều phối theo cơ chế migration.
11. **Validate:** row counts, checksums, business invariants, end-to-end tests.
12. **Monitor/decommission:** theo dõi và chỉ tắt nguồn cũ khi đã sign-off.

Đổi connection string **không phải toàn bộ migration**. Phải xác minh SQL users, network, TLS, collation, application retry, jobs, data correctness và backup policy.

### 16.5. Dữ liệu sau migration

Một checksum tổng hợp có thể giúp phát hiện sai lệch, nhưng không đủ bảo đảm mọi business invariant. Ví dụ:

- Tổng số OrderItems phải khớp.
- Orders không có customer tham chiếu sai.
- Tổng tiền đơn trong khoảng thời gian được đối soát.
- Trạng thái payment/fulfillment nhất quán.
- Các row changes trong cutover window được ghi nhận.
- Không có duplicate hoặc missing transactions.

Dữ liệu thử nghiệm cần được ẩn danh hóa và tuân thủ chính sách, không sao chép PII production vào môi trường lab không kiểm soát.

## 17. Chi phí và Total Cost of Ownership

### 17.1. Các cấu phần chi phí

~~~text
TCO =
  Compute / database service capacity
+ Data storage / log / IOPS theo product model
+ Backup retention / LTR / geo-backup
+ HA, read replicas, geo-secondary / DR
+ Network/private connectivity/egress
+ Monitoring, audits, Defender
+ Licensing / Azure Hybrid Benefit nếu đủ điều kiện
+ DBA/SRE operations, patching, migration, testing
+ Risk buffer cho peak workload và incident recovery
~~~

Công thức là khung phân tích, không phải công thức giá thống nhất của mọi SKU. Mỗi tier/region/service tính phí khác nhau.

### 17.2. Những đòn bẩy tiết kiệm

- Chọn đúng engine từ đầu, tránh rewrite vô ích.
- Chọn single DB cho ứng dụng độc lập.
- Xem elastic pool với nhiều databases có peak lệch nhau.
- Xem serverless với idle thực tế và SLA chịu resume latency.
- Right-size vCores/storage dựa trên metrics và benchmark.
- Đánh giá Reserved capacity/Azure Hybrid Benefit nếu đủ điều kiện.
- Giữ backup/LTR/geo-replica theo business requirements, không quá mức.
- Quản lý Log Analytics retention và sampling nhưng giữ audit thiết yếu.
- Đặt budget/tag cho môi trường dev/test/production.
- Thử release/rollback theo checklist để giảm incident cost.

### 17.3. Ví dụ elastic pool có thể tiết kiệm

Một SaaS có 20 tenants, mỗi tenant dùng một database. Trong phần lớn ngày, chỉ 2–3 DB có tải cao; những DB khác rất thấp. Elastic pool có thể tăng hiệu quả chia tài nguyên.

Nhưng phải kiểm tra **đỉnh đồng thời**, không chỉ trung bình theo ngày. Nếu cả 20 tenants cùng kết sổ cuối tháng thì pool có thể bị chạm CPU/log I/O. Kế hoạch tốt:

1. Thu thập metrics theo DB qua một chu kỳ nghiệp vụ.
2. Xây tải tổng đồng thời theo khoảng thời gian ngắn.
3. Xác định per-DB và pool limits.
4. Load test cuối tháng/campaign.
5. So chi phí và SLA giữa pool với single DBs.
6. Tách tenants lớn khỏi pool khi gây noisy-neighbor.

### 17.4. Đừng bỏ qua operations cost của SQL VM

SQL Server VM có thể phù hợp ràng buộc kỹ thuật, nhưng tổng chi phí còn gồm OS patching, SQL licensing, disk tuning, monitoring, backup infrastructure, HA secondaries, DBA on-call và DR exercise. Không lấy giá VM compute so trực tiếp với giá PaaS mà bỏ những phần trên.

## 18. Case studies: chọn dịch vụ theo bài toán

### 18.1. API đơn hàng mới

**Đầu bài:** .NET API trên App Service, SQL/T-SQL quen thuộc, một DB, giao dịch OLTP, team nhỏ.

**Ứng viên đầu tiên:** Azure SQL Database single database.

**Lý do:** PaaS giảm vận hành engine, có quản lý backup, hỗ trợ Entra identity/private connectivity theo thiết kế. Chọn General Purpose hoặc tier khác sau load test; không mặc định Business Critical.

**Cần xác minh:** p95 latency, query plans, connection pooling, PITR, HA/DR và cost.

### 18.2. SaaS 500 tenants

**Đầu bài:** mỗi tenant một database, phần lớn tải thấp, peak lệch giờ.

**Ứng viên:** Azure SQL Database elastic pool cho nhóm nhỏ/vừa, single database riêng cho tenant lớn hoặc có isolation đặc biệt.

**Cần xác minh:** pool peak, per-tenant metrics, noisy neighbor, backup/tenant lifecycle, security boundary và auto-provisioning.

### 18.3. ERP SQL Server 15 năm

**Đầu bài:** nhiều databases, SQL Agent, stored procedures, migration downtime hạn chế, muốn giảm OS management.

**Ứng viên:** Azure SQL Managed Instance sau feature assessment.

Nếu phụ thuộc một OS driver/feature không có MI, dùng SQL Server on Azure VM như lựa chọn chuyển tiếp.

### 18.4. Vendor app cần Windows-level agent

**Đầu bài:** vendor chỉ chứng nhận SQL Server cài trên Windows Server với agent tùy chỉnh.

**Ứng viên:** SQL Server on Azure VM.

**Điều kiện:** có DBA/SRE, license, HA/backup, patching và DR runbook. Không giả định VM tự được PaaS backup.

### 18.5. Ứng dụng GIS dùng PostgreSQL/PostGIS

**Đầu bài:** PostgreSQL drivers, JSONB, PostGIS.

**Ứng viên:** Azure Database for PostgreSQL Flexible Server nếu extension/engine version được hỗ trợ.

### 18.6. Trang web CMS dùng MySQL

**Đầu bài:** web application đang chạy MySQL và plugin ecosystem tương ứng.

**Ứng viên:** Azure Database for MySQL Flexible Server; kiểm tra charset, SQL mode, engine version, backup, private networking và pricing.

**Kết luận tình huống:** sáu workload quan hệ không nhất thiết nên chọn cùng một Azure database service.

## 19. Ma trận quyết định có trọng số

Nhóm kiến trúc có thể chọn một ma trận ví dụ:

| Tiêu chí | Trọng số minh họa | Câu hỏi |
|---|---:|---|
| Engine/feature compatibility | 30% | SQL dialect, features, extensions chạy được không? |
| HA/DR/availability | 20% | Có đáp ứng RPO/RTO và regional requirements? |
| Operations/skills | 15% | Team có thể quản lý OS/DB engine không? |
| Performance/scalability | 15% | TPS, connections, I/O, data growth, latency? |
| Security/network/compliance | 10% | Entra, VNet, audit, data residency? |
| TCO | 10% | Compute, storage, backup, license, DBA cost? |

Trọng số chỉ là phương pháp, **không phải Azure best practice bắt buộc**. Nếu có hard constraint như dữ liệu phải ở một region được chỉ định hoặc cần PostGIS/SQL Server Agent, loại dịch vụ không đáp ứng trước khi chấm điểm tổng.

### 19.1. Architecture Decision Record (ADR)

~~~text
Decision: Azure SQL Database - single database
Context: .NET OLTP app, one database, no SQL Agent dependency
Alternatives: SQL Managed Instance, SQL Server VM, PostgreSQL
Rationale:
  - SQL Server-compatible data model
  - PaaS operations match team capacity
  - Entra identity + private networking
  - Backup/HA/DR plan meets validated requirements
Risks:
  - Connection storm during Functions scale-out
  - Uncertain peak sizing
Mitigations:
  - Connection pooling and cap concurrency
  - Load test p95 latency and log throughput
  - Practice PITR restore and failover
Review trigger:
  - SQL instance-level features required
  - Unexpected data growth or latency regression
  - Region/compliance requirement changes
~~~

ADR là ghi chép giả định và lý do; không thay thế thử nghiệm hoặc security review.

## 20. Monitoring và vận hành

### 20.1. Những nguồn telemetry

- **Azure Monitor metrics:** CPU, memory/IO/log utilization, storage, connections theo service.
- **Query Store/SQL performance tooling:** slow queries, execution plans, regressions.
- **Database auditing:** hoạt động dữ liệu và privileged events theo cấu hình.
- **Azure Activity Log:** resource changes, firewall, SKU, identities.
- **Application Insights:** SQL dependency latency/errors từ ứng dụng.
- **Defender for Cloud/SQL:** security assessments/alerts nếu bật.
- **Azure Cost Management:** compute, storage, backup, replicas, log costs.
- **Business metrics:** checkout success, orders/minute, payment consistency.

**Azure Activity Log không ghi mọi SELECT/INSERT**; muốn audit data plane phải bật nguồn log phù hợp.

### 20.2. KQL minh họa

Nếu Application Insights workspace gửi dependency data vào AppDependencies:

~~~kusto
AppDependencies
| where TimeGenerated > ago(1h)
| where Type has "SQL"
| summarize Requests=count(),
            Failed=countif(Success == false),
            P95ms=percentile(DurationMs, 95)
    by bin(TimeGenerated, 5m), Target
| order by TimeGenerated asc
~~~

Tên bảng/cột thay đổi theo telemetry schema và ingestion. Query trả rỗng không chứng minh DB không có lỗi nếu instrumentation/logging chưa bật.

### 20.3. Alert nên thiết kế

| Alert | Tình huống |
|---|---|
| CPU/log IO cao kéo dài | Có thể chạm limits |
| Storage gần đầy | Rủi ro gián đoạn ghi |
| p95 SQL dependency tăng | Ảnh hưởng SLA |
| Connection timeout tăng | Network/pooling/capacity |
| Deadlocks tăng | Transaction conflict/regression |
| Failover/restart bất thường | Availability issue |
| Backup/retention policy đổi | Recovery risk |
| SQL firewall/public access đổi | Security change |
| Privileged role/user đổi | Risk of data abuse |
| Replication lag vượt RPO | DR risk |
| Cost tăng ngoài baseline | Overprovision/abnormal load |

Không tạo alert không có owner. Mỗi alert nên kèm runbook, baseline và mức severity.

## 21. Xử lý sự cố

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Hostname không resolve | Private DNS/custom resolver | Kiểm tra zone/link và DNS path |
| TCP timeout | Route/NSG/firewall/private endpoint | Kiểm tra từ đúng app runtime |
| TLS certificate error | Hostname, driver, trust chain | Dùng canonical hostname, kiểm tra CA |
| SQL login failed | Sai Entra identity/token hoặc SQL auth | Xác định principal và tenant |
| Permission denied SELECT | SQL GRANT không đủ | Xem schema/role/data permissions |
| Azure Contributor nhưng không đọc được dữ liệu | Nhầm Azure RBAC và DB SQL quyền | Tạo DB user/GRANT thích hợp |
| CPU cao | Heavy queries/underprovision | Query Store, plan/index, sizing |
| Data/log I/O bão hòa | Storage limits hoặc write pattern | Metrics và tier |
| Too many connections | Pool leak/burst | Giới hạn pool × replicas |
| Deadlocks | Transaction locking/concurrency | Thứ tự lock, giảm transaction scope |
| Query chậm sau migration | Collation, plan, stats, feature khác | Benchmark và SQL assessment |
| Auto-pause không xảy ra | Workload/background activities | Xem serverless eligibility |
| Resume latency lớn | Serverless cold resume | Chọn compute model theo SLA |
| Failover xong app lỗi | Pool reconnect/DNS/listener | Driver retry và routing |
| PITR sai mốc | UTC/retention hoặc data reconciliation | Restore runbook |
| Geo-secondary stale | Asynchronous replication lag | Xem lag, RPO policy |
| Cost vượt ngân sách | Overprovision/replicas/backups/logs | Azure Cost Management |
| Missing feature sau migration | Unsupported SQL feature | Đánh giá MI/VM hoặc refactor |

### 21.1. Quy trình chẩn đoán theo lớp

1. Xác định dịch vụ và engine thực tế (SQL DB, MI, VM, PostgreSQL, MySQL).
2. Kiểm tra subscription, resource, region, timestamps UTC.
3. Kiểm tra DNS/network/TLS từ **đúng workload**.
4. Xác định identity và SQL data-plane permissions.
5. Xem resource utilization, Query Store, wait stats/slow queries.
6. Đối chiếu application dependency logs và correlation IDs.
7. Kiểm tra thay đổi gần đây: code, schema, index, role, firewall, tier.
8. Đánh giá data safety và backup/restore nếu rủi ro mất dữ liệu.
9. Apply rollback/recovery được phê duyệt.
10. Lưu root cause và preventive action.

**Đừng sửa lỗi DNS bằng db_owner. Đừng sửa SQL 403 bằng mở public network. Đừng chữa query N+1 bằng tier đắt nhất mà không đo.**

## 22. Checklist trước production

### Lựa chọn sản phẩm

- [ ] Có danh sách engine version và features nguồn.
- [ ] Đã đánh giá T-SQL, SQL Agent, cross-database, extensions.
- [ ] Chọn PaaS hoặc IaaS theo trách nhiệm vận hành.
- [ ] Có hard requirements và migration compatibility assessment.
- [ ] Có proof of concept/load test, không chỉ dựa vào bảng tính giá.
- [ ] Có ADR, rủi ro và điều kiện xem xét lại.

### Mạng và danh tính

- [ ] Subscription/resource group/region và tags đúng.
- [ ] Private Endpoint/VNet/DNS và egress được kiểm tra.
- [ ] Public network không mở ngoài yêu cầu.
- [ ] Microsoft Entra identity, SQL users/GRANT theo least privilege.
- [ ] DBA/migration identity tách runtime identity.
- [ ] Secrets còn lại được bảo vệ trong Key Vault.
- [ ] TLS encryption và certificate verification được bật.

### Data, backup và DR

- [ ] Schema/constraints/indexes được review.
- [ ] PITR và retention đáp ứng business policy.
- [ ] Có backup/LTR khi compliance yêu cầu.
- [ ] Restore đã được diễn tập, biết RTO đo thực tế.
- [ ] Geo-DR/failover theo mục tiêu RPO/RTO.
- [ ] Replication lag và data residency được xét.
- [ ] Schema migration và rollback tương thích các phiên bản ứng dụng.
- [ ] Audit/security logs có retention và owner.

### Hiệu năng và chi phí

- [ ] Tài nguyên DB size từ CPU, IO, log rate, latency, concurrency.
- [ ] Connection pools và retry đã load test.
- [ ] Functions/AKS scale không vượt DB capacity.
- [ ] Elastic pool/serverless có căn cứ tải thực.
- [ ] App Insights, Query Store và alerts theo SLA.
- [ ] Dự toán compute/storage/backup/secondary/license/ops.
- [ ] Budget/tag/Cost Management được cấu hình.

### Vận hành

- [ ] Có owner DBA/SRE và on-call.
- [ ] Runbook DNS/network/auth/deadlock/restore/failover.
- [ ] Có change approval cho firewall, tier, roles, database schema.
- [ ] Có quy trình deprecation, end-of-support engine version.
- [ ] Có kế hoạch migration cutover, reconciliation và decommission.
- [ ] Có lịch diễn tập DR tiếp theo.

## 23. Câu hỏi tự kiểm tra

1. **Khi nào dữ liệu quan hệ là lựa chọn tốt?** Khi cần SQL joins, schema, constraints và giao dịch nhất quán.
2. **Azure SQL Database có phải SQL Server VM không?** Không; nó là database PaaS.
3. **Managed database có thay DBA/query tuning không?** Không.
4. **Single DB phù hợp khi nào?** Ứng dụng có một DB độc lập, ít dependencies cấp instance.
5. **Elastic pool phù hợp khi nào?** Nhiều DB có tải lệch nhau và dùng chung compute hiệu quả.
6. **Elastic pool có tự chia dữ liệu tenant thành sharding không?** Không.
7. **Serverless có được miễn phí toàn bộ khi pause không?** Không, còn storage và chi phí khác.
8. **Vì sao serverless có thể không auto-pause?** Persistent connection, background activity hoặc tính năng không hỗ trợ.
9. **Hyperscale có mặc định là tier rẻ/nhanh nhất không?** Không.
10. **Managed Instance giúp migration SQL Server kiểu nào?** Workloads cần instance features và compatibility rộng hơn SQL Database.
11. **MI có cho người dùng RDP vào OS không?** Không.
12. **Khi nào SQL Server VM hợp lý?** Cần OS/full SQL control hoặc vendor/feature constraints.
13. **PostgreSQL có đổi connection string để chạy trên Azure SQL DB không?** Không.
14. **Vì sao phải kiểm tra PostgreSQL extensions?** Flexible Server chỉ hỗ trợ những extensions/versions nhất định.
15. **Nguồn MySQL nên đánh giá dịch vụ nào đầu tiên?** MySQL Flexible Server nếu requirements phù hợp.
16. **DTU có quy đổi chính xác thành vCore bằng hệ số duy nhất không?** Không.
17. **General Purpose và Business Critical khác nhau ở đâu?** Hướng hiệu năng/availability/storage theo service tier.
18. **RPO nghĩa là gì?** Dữ liệu tối đa chấp nhận mất, tính theo thời gian.
19. **RTO nghĩa là gì?** Mục tiêu thời gian khôi phục.
20. **HA có thay thế PITR khi xóa nhầm dữ liệu không?** Không.
21. **Geo-replication có bảo đảm zero data loss không?** Không khi replication bất đồng bộ.
22. **Private Endpoint có tự cấp SQL SELECT không?** Không.
23. **Azure Contributor có tự được SELECT database không?** Không.
24. **Managed identity có cần database permissions không?** Có.
25. **Vì sao không hard-code Private Endpoint IP?** TLS hostname/DNS/failover có thể hỏng.
26. **TDE có ngăn người có SELECT đọc plaintext không?** Không.
27. **Vì sao connection pooling quan trọng khi AKS scale-out?** Để tránh DB connection storm.
28. **Nâng tier có chữa N+1 queries không?** Không chắc; phải tối ưu code/query.
29. **Migration có thể làm lỗi gì dù dữ liệu đã copy đủ?** SQL features, jobs, permissions, collation, DNS, driver, performance.
30. **TCO gồm những gì ngoài compute?** Storage, backups, replicas/DR, license, network, monitoring và nhân lực.
31. **Khi nào chọn MI thay VM?** Khi MI đáp ứng feature requirements và đội muốn giảm OS/engine ops.
32. **Một lựa chọn database tốt cần được chứng minh bằng gì?** Compatibility, network/security, performance tests, restore/DR exercise và tổng chi phí.

## 24. Tài liệu tham khảo

- [Azure SQL documentation](https://learn.microsoft.com/azure/azure-sql/) — họ sản phẩm và mô hình triển khai Azure SQL.
- [Azure SQL Database overview](https://learn.microsoft.com/azure/azure-sql/database/sql-database-paas-overview) — PaaS database.
- [Azure SQL Managed Instance overview](https://learn.microsoft.com/azure/azure-sql/managed-instance/sql-managed-instance-paas-overview) — instance features và compatibility.
- [SQL Server on Azure VMs](https://learn.microsoft.com/azure/azure-sql/virtual-machines/) — SQL Server IaaS.
- [Azure SQL service tiers](https://learn.microsoft.com/azure/azure-sql/database/service-tiers-sql-database-vcore) — vCore, General Purpose, Business Critical, Hyperscale.
- [DTU-based service tiers](https://learn.microsoft.com/azure/azure-sql/database/service-tiers-dtu) — DTU objectives.
- [Azure SQL elastic pools](https://learn.microsoft.com/azure/azure-sql/database/elastic-pool-overview) — shared compute for DBs.
- [Azure SQL serverless](https://learn.microsoft.com/azure/azure-sql/database/serverless-tier-overview) — compute scaling và pause.
- [Azure SQL Hyperscale](https://learn.microsoft.com/azure/azure-sql/database/service-tier-hyperscale) — storage/compute architecture.
- [Azure SQL security](https://learn.microsoft.com/azure/azure-sql/database/security-overview) — identity, auditing và encryption.
- [Azure SQL Private Endpoint](https://learn.microsoft.com/azure/azure-sql/database/private-endpoint-overview) — networking và DNS.
- [Azure SQL automated backups](https://learn.microsoft.com/azure/azure-sql/database/automated-backups-overview) — PITR và LTR.
- [Active geo-replication](https://learn.microsoft.com/azure/azure-sql/database/active-geo-replication-overview) — geo-secondary.
- [Azure SQL failover groups](https://learn.microsoft.com/azure/azure-sql/database/failover-group-sql-db) — DR và failover.
- [PostgreSQL Flexible Server overview](https://learn.microsoft.com/azure/postgresql/flexible-server/overview) — PostgreSQL PaaS.
- [MySQL Flexible Server overview](https://learn.microsoft.com/azure/mysql/flexible-server/overview) — MySQL PaaS.
- [Azure Database Migration Service](https://learn.microsoft.com/azure/dms/dms-overview) — migration scenarios.
- [Monitoring and performance tuning in Azure SQL](https://learn.microsoft.com/azure/azure-sql/database/monitoring-tuning-index) — metrics/Query Store.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — dự toán theo SKU/region.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — budgets, tags và cost analysis.

**Kết luận:** lựa chọn cơ sở dữ liệu quan hệ trên Azure phải bắt đầu bằng **engine/feature compatibility**, sau đó đến **mức độ quản trị**, **mẫu tải/tier**, **private networking và identity**, **backup/HA/DR** và **total cost of ownership**. Azure SQL Database phù hợp nhiều ứng dụng SQL Server-compatible cloud-native; Managed Instance hỗ trợ nhiều kịch bản migration có phụ thuộc cấp instance; SQL Server on Azure VM phù hợp khi cần quyền OS/full engine control; PostgreSQL/MySQL Flexible Server dành cho những ecosystem tương ứng. Chỉ chốt phương án sau khi thử feature compatibility, đo hiệu năng, thử khôi phục và có trách nhiệm vận hành rõ ràng.


