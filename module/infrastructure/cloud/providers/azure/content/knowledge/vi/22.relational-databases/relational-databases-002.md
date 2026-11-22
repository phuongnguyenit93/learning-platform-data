# Azure SQL Database và mô hình triển khai dữ liệu

Một ứng dụng Java chạy trên Azure App Service, Azure Kubernetes Service hoặc Azure Functions thường cần lưu khách hàng, đơn hàng, thanh toán và trạng thái giao dịch. Các dữ liệu này có quan hệ, ràng buộc toàn vẹn và yêu cầu giao dịch nhất quán. Nếu quản lý máy chủ SQL thủ công, nhóm vận hành phải lo cài đặt hệ điều hành, vá SQL Server, triển khai tính sẵn sàng cao, backup và cấp phát lưu trữ. **Azure SQL Database** cung cấp cơ sở dữ liệu quan hệ theo mô hình **Platform as a Service (PaaS)**, giúp tập trung hơn vào thiết kế schema, truy vấn, kết nối và chất lượng dữ liệu.

Tuy nhiên, chọn Azure SQL Database không chỉ là tạo một database trên Portal. Bạn còn phải quyết định **một database hay elastic pool, mỗi tenant một database hay dùng chung, mức compute và storage, mô hình dự phòng, cách triển khai migration, quyền truy cập mạng/danh tính và chi phí**. Sai lầm ở những quyết định này có thể khiến hệ thống chậm khi tăng tải, khó cô lập khách hàng, khó phục hồi dữ liệu hoặc không thể rollback an toàn.

Bài thuộc chương **Cơ sở dữ liệu quan hệ** trong module **CLOUD_PROVIDERS_AZURE**. Module khám phá Microsoft Azure từ subscription, resource group và Microsoft Entra ID tới mạng ảo, compute, lưu trữ và dữ liệu; học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng. Ở đây, Azure SQL Database được đặt trong kiến trúc ứng dụng thực tế và quy trình triển khai dữ liệu từ môi trường phát triển tới production.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **Azure SQL Database**, **Azure SQL Managed Instance** và **SQL Server trên Azure VM**.
- Giải thích **logical server**, single database, elastic pool, database replica và cách kết nối.
- So sánh **DTU/vCore**, General Purpose, Business Critical, Hyperscale, provisioned và serverless compute theo điều kiện hỗ trợ.
- Lựa chọn mô hình dữ liệu cho một ứng dụng, nhiều ứng dụng và **SaaS multi-tenant**.
- Thiết kế bảng quan hệ, khóa chính/ngoại, unique constraints, index và giao dịch.
- Kết nối Java tới Azure SQL bằng **Microsoft Entra ID/managed identity** hoặc phương thức phù hợp.
- Thiết kế **Private Endpoint, DNS, firewall, TLS, RBAC, database permissions, auditing** và bảo vệ dữ liệu.
- Phân biệt **zone redundancy**, backup/PITR, geo-replication và failover groups.
- Triển khai **schema migrations** bằng cơ chế có version, thử nghiệm và rollback kế hoạch.
- Theo dõi performance/cost, xử lý lỗi kết nối, deadlocks, throttling và khôi phục.

## 2. Azure SQL Database là gì?

**Azure SQL Database** là dịch vụ cơ sở dữ liệu quan hệ được Azure quản lý dựa trên công nghệ SQL Server, có ngôn ngữ truy vấn **T-SQL**, cơ chế giao dịch, chỉ mục, ràng buộc dữ liệu và nhiều tính năng bảo mật/khả dụng. Azure đảm trách nhiều hoạt động hạ tầng như hệ điều hành, triển khai bản vá dịch vụ, cấu phần high availability và backup tự động theo dịch vụ.

~~~text
Client / Java API
       |
       | TDS qua TLS, port 1433 theo đường mạng phù hợp
       v
Azure SQL logical server endpoint
<SERVER_NAME>.database.windows.net
       |
       +-- Database: orders-dev
       |
       +-- Database: orders-staging
       |
       +-- Database: orders-prod
       |
       +-- Elastic pool (nếu dùng)
             +-- tenant-a-db
             +-- tenant-b-db
~~~

Sơ đồ chỉ minh họa **địa chỉ logic và cách tổ chức**, không biểu diễn máy vật lý hoặc khuyến nghị đặt dev/staging/prod cùng một logical server. Với yêu cầu cô lập nghiêm ngặt, cần tách logical servers, resource groups, subscriptions, identity và network.

### Azure quản lý gì và bạn vẫn phải quản lý gì?

| Azure quản lý theo mô hình dịch vụ | Nhóm ứng dụng/vận hành phải quản lý |
|---|---|
| Hạ tầng database PaaS, phần lớn vá nền tảng | Schema, constraints, index và kế hoạch migrations |
| Nhiều cơ chế HA/backup được cung cấp | Chọn tier/region/zone redundancy và DR objectives |
| Kết nối dịch vụ SQL ở endpoint logic | Firewall, Private Endpoint, DNS, network egress |
| Encryption at rest mặc định theo tính năng | Phân quyền dữ liệu, key management bổ sung, audit |
| Telemetry/monitoring capabilities | Alerts, query optimization, capacity và ngân sách |
| Scale options của service tier | Connection pooling, retry, workload isolation |

**PaaS không đồng nghĩa Azure chịu trách nhiệm sửa truy vấn chậm, dữ liệu bị xóa do ứng dụng, mật khẩu lộ hoặc migration phá tương thích.** Đây vẫn là trách nhiệm thiết kế và vận hành của bạn.

## 3. Chọn Azure SQL Database, Managed Instance hay SQL Server VM?

Ba dịch vụ cùng có nền tảng SQL Server nhưng mức quản lý và khả năng tương thích khác nhau.

| Tiêu chí | Azure SQL Database | Azure SQL Managed Instance | SQL Server trên Azure VM |
|---|---|---|---|
| Mô hình | PaaS ở mức database | PaaS gần mức SQL Server instance | IaaS, tự quản SQL Server/OS nhiều hơn |
| Phù hợp | Ứng dụng cloud, DB độc lập, SaaS nhiều DB | Workload migrate cần nhiều khả năng instance-level | Cần kiểm soát OS/SQL instance hoặc feature đặc thù |
| Công việc vận hành | Nhẹ hơn ở tầng máy chủ | Quản lý bớt nhiều tầng hạ tầng | Nhiều trách nhiệm patch, backup, HA, licensing |
| Tính năng instance-level | Một số tính năng có giới hạn/khác SQL Server đầy đủ | Tương thích instance hơn, vẫn có khác biệt | Nhiều quyền cấu hình nhất theo edition |
| Mạng | Logical server + endpoints, private/public theo cấu hình | Thiết kế network riêng theo MI | VM NIC, NSG, SQL listener, HA/network |
| Thay đổi schema | Do ứng dụng/DBA quản lý | Do ứng dụng/DBA quản lý | Do ứng dụng/DBA quản lý |

Chọn **Azure SQL Database** khi ứng dụng thiết kế cloud-friendly, chủ yếu dùng các đối tượng ở cấp database và cần giảm vận hành hạ tầng. Chọn **Managed Instance** nếu hệ thống migrate cần tính tương thích instance-level đáng kể. Chọn **SQL Server trên VM** khi cần kiểm soát máy chủ, OS hoặc tích hợp mà các mô hình PaaS không đáp ứng.

**Không mặc định mọi tính năng T-SQL hoặc SQL Server Agent job trong hệ thống on-premises đều hoạt động y hệt trên Azure SQL Database.** Trước migration, lập bảng so sánh compatibility, kiểm tra các tính năng xuyên database, jobs, authentication và extensions.

## 4. Logical server không phải một SQL VM

Khi tạo Azure SQL Database, bạn thường tạo hoặc chọn một **Azure SQL logical server**. Logical server cung cấp **tên DNS/điểm quản trị**, phạm vi cấu hình firewall/authentication và nơi tổ chức databases.

~~~text
Subscription
   |
   +-- Resource group: rg-orders-prod
          |
          +-- Logical server: sql-orders-prod
          |     FQDN: sql-orders-prod.database.windows.net
          |     |
          |     +-- orders-db  (single database)
          |     +-- reports-db
          |
          +-- App Service / AKS workloads
          +-- Private Endpoint / Private DNS
          +-- Azure Monitor diagnostics
~~~

**Logical server không phải VM mà bạn SSH/RDP vào để cài SQL Server.** Không có quyền quản trị hệ điều hành ở mô hình này. Cấu hình về backup retention, availability và compute/storage có thể đặt theo **database/service tier** chứ không phải mặc định cùng một cấu hình cho toàn bộ logical server.

### Tên kết nối

Ví dụ endpoint:

~~~text
sql-orders-prod.database.windows.net
~~~

Với hầu hết cách kết nối TCP trực tiếp, client dùng **port 1433** theo cấu hình network. Nhưng kết nối thành công còn phụ thuộc DNS, firewall, connection policy, TLS, user/token và database name. Không suy luận mở NSG port 1433 là đủ để kết nối vào một Azure SQL Database private.

### Môi trường quản trị

Phân biệt ba lớp:

1. **Azure RBAC (management plane):** ai được tạo/sửa logical server, database, Private Endpoint, auditing?
2. **SQL authentication/database permissions (data plane):** user nào được SELECT/INSERT/ALTER?
3. **Network restrictions:** client từ VNet/IP nào có thể đi tới endpoint?

Có quyền **Contributor** trên resource group không đồng nghĩa có quyền SELECT mọi bảng. Có user database đúng chưa chắc đi được qua firewall.

## 5. Mô hình single database

**Single database** là một database có tài nguyên tính toán/lưu trữ và service objective được chọn riêng theo tier, phù hợp một workload hoặc một đơn vị quản trị rõ ràng.

~~~text
Orders Java API
      |
      v
Azure SQL Database: orders-prod
  +-- Customers
  +-- Orders
  +-- OrderItems
  +-- Payments
~~~

Lợi ích:

- Dễ quản trị lifecycle, schema, restore và phân quyền theo database.
- Có thể thay đổi tier/compute độc lập cho database.
- Dễ gắn monitoring và ownership với một ứng dụng.
- Thích hợp microservice có data ownership rõ hoặc một sản phẩm nội bộ.

Giới hạn:

- Nếu đặt nhiều tenants cùng database, phải kiểm soát **isolation logic** ở mọi truy vấn.
- Nếu có nhiều database, compute có thể lãng phí khi các DB ít hoạt động.
- Không phải mọi thao tác SQL đa database có thể dùng như trên SQL Server VM.
- Quy mô ghi/đọc và yêu cầu latency có thể buộc chọn tier/scale design khác.

### Khi nên bắt đầu bằng single database

Một API đơn hàng có dữ liệu không quá lớn, traffic tương đối dự đoán được và một đội sở hữu schema thường bắt đầu tốt với **single database** ở tier phù hợp. Sau khi có số liệu CPU, I/O, memory, connections, latency và chi phí mới nên quyết định nâng compute, thêm read replicas hoặc chia dữ liệu.

## 6. Elastic pool: nhiều database chia sẻ tài nguyên

**Elastic pool** cho phép nhiều Azure SQL databases chia sẻ một quỹ tài nguyên tính toán theo mô hình được tier hỗ trợ. Nó hữu ích khi nhiều database có **mức sử dụng không đồng thời**, ví dụ hàng chục tenants hoạt động vào những giờ khác nhau.

~~~text
Azure SQL Elastic Pool
  Shared compute capacity
        |
        +-- tenant-a-db -> cao điểm buổi sáng
        +-- tenant-b-db -> cao điểm buổi chiều
        +-- tenant-c-db -> ít truy cập
        +-- tenant-d-db -> thỉnh thoảng chạy báo cáo
~~~

### Khi pool có lợi

- Có nhiều database hoạt động không đều.
- Tổng capacity dùng đồng thời thường thấp hơn tổng peak của từng DB.
- Muốn quản lý cost/capacity theo pool và theo dõi per-database usage.
- SaaS dùng database-per-tenant nhưng cần tối ưu chi phí.

### Khi pool không có lợi

- Chỉ có một vài DB đều sử dụng CPU/I/O cao cùng lúc.
- Một tenant có truy vấn nặng gây cạnh tranh tài nguyên trong pool.
- Nhu cầu isolation performance quá cao, cần dedicated capacity.
- Một số DB cần service tier/region/tính năng không tương thích pool đã chọn.

**Elastic pool không trộn dữ liệu của các database vào một schema.** Database vẫn là đơn vị logic tách biệt; chia sẻ chủ yếu ở tầng tài nguyên pool. Việc pool quá đông có thể tạo **noisy-neighbor performance effects**, cần theo dõi pool utilization và đặt giới hạn min/max theo database khi tính năng hỗ trợ.

### So sánh nhanh

| Khía cạnh | Single DB | Elastic pool |
|---|---|---|
| Capacity | Cấp riêng cho DB | Chia sẻ theo pool |
| Tài nguyên nhàn rỗi | Có thể lãng phí ở DB ít tải | Có thể tận dụng giữa DBs |
| Ảnh hưởng workload khác | Ít chia sẻ tài nguyên trực tiếp | Có thể cạnh tranh trong pool |
| Vận hành | Đơn giản với một vài DB | Tốt khi nhiều DB nhưng cần giám sát |
| Use case | Một API/ứng dụng quan trọng | SaaS nhiều tenants/database nhỏ |

## 7. Mô hình tài nguyên DTU và vCore

Azure SQL Database có các mô hình mua tài nguyên như **DTU-based** và **vCore-based** tùy tier/offer. Phải xem service objective đang chọn, không chỉ tên database.

### DTU

**Database Transaction Unit (DTU)** là đơn vị kết hợp CPU, memory và I/O theo service objective. Các lớp lịch sử gồm Basic, Standard và Premium, với hạn mức khác nhau.

- Dễ bắt đầu khi thích một mức tài nguyên tổng hợp.
- Khó đối chiếu trực tiếp số core/memory với yêu cầu của workload chuyên sâu.
- Các tier/tính năng mới và lựa chọn compute có thể ưu tiên vCore.

### vCore

Mô hình **vCore** bộc lộ rõ hơn lựa chọn số virtual cores, hardware generation, service tier và một số yếu tố lưu trữ. Có thể phù hợp cho sizing dựa trên workload và các cơ chế license savings được Azure hỗ trợ.

| Quyết định | Câu hỏi cần trả lời |
|---|---|
| Service tier | General Purpose, Business Critical hay Hyperscale? |
| Compute | Bao nhiêu vCores, loại hardware nào còn khả dụng? |
| Provisioning | Provisioned hay serverless với khả năng hỗ trợ? |
| Storage | Dung lượng, growth, I/O latency, backup storage |
| Availability | Zone redundancy, replicas và geo-DR |
| Billing | Compute, storage, backup, network và các ưu đãi license nếu hợp lệ |

**Không chuyển DTU sang vCore bằng công thức một-một tuyệt đối.** Cần đo throughput, p95 latency, CPU, I/O, log write pressure và kiểm thử tải sau khi đổi service objective.

## 8. General Purpose, Business Critical và Hyperscale

Trong mô hình vCore, ba service tiers thường được cân nhắc:

| Tier | Đặc điểm kiến trúc tổng quát | Phù hợp |
|---|---|---|
| **General Purpose** | Compute và storage theo kiến trúc dịch vụ tối ưu chi phí/hiệu năng cân bằng | API doanh nghiệp thông thường, latency không quá nghiêm ngặt |
| **Business Critical** | Thiết kế ưu tiên I/O latency thấp và HA với các replicas theo khả năng tier | OLTP nhạy latency, yêu cầu I/O cao và HA |
| **Hyperscale** | Kiến trúc lưu trữ/phục vụ tách mở rộng, phục vụ DB lớn và khả năng scale theo tier | Dữ liệu lớn, tăng trưởng mạnh, bài toán backup/restore/scale đặc thù |

Mỗi tier có giới hạn về kích thước, service objectives, read scale, replica topology và zone/geo settings. **Không tự khẳng định mọi tier đều hỗ trợ mọi kết hợp serverless, read replicas hoặc zone redundancy ở tất cả regions.**

### Nhận diện trade-off

- **General Purpose:** thường phù hợp điểm xuất phát nếu các phép đo không yêu cầu I/O cực thấp.
- **Business Critical:** có thể trả chi phí cao hơn đổi lấy ưu thế về latency/I/O/HA; phải chứng minh bằng workload.
- **Hyperscale:** hữu ích khi kích thước DB/backup/scale vượt thiết kế thông thường; không phải mặc định luôn nhanh hơn hoặc rẻ hơn cho DB nhỏ.

Một database chỉ vài GiB, ít giao dịch nhưng được đặt Business Critical cao cấp có thể là lựa chọn tốn kém không cần thiết. Ngược lại, một workload tài chính cần p99 write latency thấp không nên chọn tier chỉ vì giá rẻ mà không kiểm thử.

## 9. Provisioned compute và serverless compute

**Provisioned compute** giữ capacity theo lựa chọn trong thời gian được cấp phát; phù hợp workload ổn định, liên tục và yêu cầu latency khởi động dự đoán được.

**Serverless compute** trong Azure SQL Database có thể **tự scale compute trong khoảng min/max** và, trên các cấu hình hỗ trợ, **tự pause/resume** khi database thực sự đáp ứng điều kiện idle.

~~~text
Workload theo thời gian

00h ---- 06h ---- 09h ---- 15h ---- 20h ---- 24h
        idle     burst    light     burst

Provisioned:
  capacity luôn được cấp phát theo mức cấu hình

Serverless:
  scale trong ngưỡng min/max;
  có thể auto-pause khi đủ điều kiện;
  resume có thể tăng độ trễ request đầu tiên
~~~

### Khi serverless thích hợp

- Dev/test, proof of concept, workloads có khoảng không hoạt động dài.
- API dùng không thường xuyên, chấp nhận độ trễ khi database resume.
- Tải thay đổi mạnh và tính năng auto scaling hữu ích.

### Khi không nên giả định tiết kiệm

- Ứng dụng có health checks, monitoring hoặc connection pool **liên tục giữ DB hoạt động**.
- Background jobs, CDC hoặc tính năng khác ngăn auto-pause theo điều kiện dịch vụ.
- SLA không chấp nhận cold-resume latency.
- Tier/region/feature của workload không hỗ trợ cấu hình serverless/auto-pause mong muốn.

**Serverless không có nghĩa database miễn phí khi không có truy vấn.** Storage và những thành phần khác vẫn có thể tính phí, và auto-pause không luôn xảy ra. Xem điều kiện/giới hạn của service tier và tính toán trên mức sử dụng thực.

## 10. Mô hình triển khai dữ liệu theo ứng dụng và tenant

Một quyết định nền tảng là **dữ liệu của khách hàng/tenant nằm ở đâu**. Ba mô hình chính:

~~~text
(A) Shared database, shared schema
    orders-shared
      Customers(TenantId,...)
      Orders(TenantId,...)

(B) Shared database, separate schemas
    orders-shared
      tenant_a.Orders
      tenant_b.Orders

(C) Database per tenant
    tenant-a-db / tenant-b-db / tenant-c-db
~~~

| Mô hình | Cách cô lập | Ưu điểm | Rủi ro/chi phí |
|---|---|---|---|
| **Shared DB + shared schema** | TenantId và ứng dụng/RLS | Tiết kiệm tài nguyên, vận hành đơn giản hơn khi ít khác biệt | Rò rỉ dữ liệu nếu lọc tenant sai, noisy neighbor, migration chung |
| **Shared DB + separate schemas** | Schema và phân quyền trong DB | Tổ chức objects theo tenant, linh hoạt một mức | Nhiều schema gây drift, không cô lập compute/backup theo tenant |
| **Database per tenant** | Mỗi tenant một DB và danh tính/connection phù hợp | Restore, thay tier, ownership riêng | Nhiều DB, migrations hàng loạt, chi phí/ops phức tạp |
| **Sharded databases** | Chia dữ liệu qua nhiều DB theo shard key | Scale dữ liệu và phân tải | Routing, resharding, giao dịch/joins xuyên shard khó |

Không có mô hình nào phù hợp cho mọi SaaS. Phải xét số tenants, khối lượng dữ liệu, SLA, dữ liệu nhạy cảm, backup/restore theo tenant, yêu cầu residency và chi phí.

### Ví dụ quyết định

- SaaS nhỏ, 20 tenants, dữ liệu vài GiB: shared schema với tenant isolation được kiểm chứng có thể phù hợp.
- SaaS 500 tenants có lưu lượng không đồng thời: database-per-tenant kết hợp elastic pool có thể có lợi.
- Một vài tenant rất lớn: đưa riêng vào single DB/high-capacity pool hoặc shard riêng.
- Khách hàng yêu cầu restore/cô lập theo hợp đồng: DB riêng có thể dễ quản trị hơn shared schema.

**Multi-tenant isolation không chỉ là thêm cột TenantId.** Phải kiểm tra mọi query, join, unique key, cache key, background job, export/backup và authorization.

## 11. Thiết kế schema quan hệ cho một ứng dụng đặt hàng

Giả sử ứng dụng **Orders API** có khách hàng và đơn hàng. Yêu cầu:

- Mỗi order thuộc một khách hàng và một tenant.
- Email không trùng trong phạm vi tenant theo collation/quy tắc nghiệp vụ được chọn.
- Một request gửi lặp cùng **ExternalOrderId** không tạo hai order.
- Tổng tiền không âm, trạng thái chỉ thuộc tập được phép.
- Có index phục vụ truy vấn các orders gần đây theo tenant.

### DDL minh họa

~~~sql
CREATE TABLE dbo.Customers (
    TenantId UNIQUEIDENTIFIER NOT NULL,
    CustomerId BIGINT IDENTITY(1,1) NOT NULL,
    Email NVARCHAR(320) NOT NULL,
    CreatedAt DATETIME2(3) NOT NULL
        CONSTRAINT DF_Customers_CreatedAt DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_Customers
        PRIMARY KEY (TenantId, CustomerId),
    CONSTRAINT UQ_Customers_Tenant_Email
        UNIQUE (TenantId, Email)
);

CREATE TABLE dbo.Orders (
    TenantId UNIQUEIDENTIFIER NOT NULL,
    OrderId BIGINT IDENTITY(1,1) NOT NULL,
    CustomerId BIGINT NOT NULL,
    ExternalOrderId NVARCHAR(80) NOT NULL,
    Status VARCHAR(20) NOT NULL
        CONSTRAINT DF_Orders_Status DEFAULT 'PENDING',
    TotalAmount DECIMAL(18,2) NOT NULL,
    CreatedAt DATETIME2(3) NOT NULL
        CONSTRAINT DF_Orders_CreatedAt DEFAULT SYSUTCDATETIME(),
    RowVer ROWVERSION NOT NULL,
    CONSTRAINT PK_Orders PRIMARY KEY (TenantId, OrderId),
    CONSTRAINT FK_Orders_Customers
        FOREIGN KEY (TenantId, CustomerId)
        REFERENCES dbo.Customers(TenantId, CustomerId),
    CONSTRAINT UQ_Orders_Tenant_ExternalOrder
        UNIQUE (TenantId, ExternalOrderId),
    CONSTRAINT CK_Orders_TotalAmount CHECK (TotalAmount >= 0),
    CONSTRAINT CK_Orders_Status
        CHECK (Status IN ('PENDING', 'CONFIRMED', 'CANCELLED'))
);

CREATE INDEX IX_Orders_Tenant_CreatedAt
    ON dbo.Orders (TenantId, CreatedAt DESC)
    INCLUDE (Status, TotalAmount);
~~~

**Chỉ chạy DDL trên database lab rỗng và được cấp quyền.** Ví dụ dùng hai bảng để dạy quan hệ và constraint; một hệ thống đơn hàng thực tế có thể còn OrderItems, Payments, Currency, Taxes, event outbox, audit, retention và chính sách dữ liệu.

### Vì sao dùng composite key có TenantId?

Khóa ngoại **(TenantId, CustomerId)** ngăn việc liên kết một order của tenant A với customer thuộc tenant B, với điều kiện mọi thao tác dùng schema đúng. Unique constraint **(TenantId, ExternalOrderId)** hỗ trợ xử lý idempotent theo tenant. Cả hai là lớp **data integrity**, không thay thế xác thực người dùng hoặc phân quyền tenant.

**IDENTITY** tạo các số thứ tự phục vụ định danh, không bảo đảm liên tục tuyệt đối hoặc trật tự thời gian. **ROWVERSION** là token nhị phân phục vụ phát hiện thay đổi, **không phải ngày giờ**; nên dùng CreatedAt/UpdatedAt rõ ràng cho thời gian.

### Tính đúng đắn của kiểu dữ liệu

- **DECIMAL(18,2)** cho số tiền nếu scale phù hợp; không dùng FLOAT để tính tiền cần chính xác.
- **DATETIME2** và **UTC** cho timestamp; quy đổi múi giờ ở lớp hiển thị.
- **NVARCHAR** khi cần Unicode.
- **BIGINT/UNIQUEIDENTIFIER** theo chiến lược định danh và kích thước dữ liệu.
- **VARCHAR** cho enum trạng thái nếu tập giá trị đã có ràng buộc CHECK hoặc lookup table.
- **NULL/NOT NULL** và defaults phản ánh rõ hợp đồng dữ liệu.

Với tiền tệ, **DECIMAL(18,2)** chưa đủ cho mọi loại currency hoặc nghiệp vụ; cần thêm **CurrencyCode**, quy tắc làm tròn và độ chính xác theo sản phẩm.

## 12. Quan hệ, chuẩn hóa và truy vấn an toàn

Database quan hệ dùng:

- **Primary key:** định danh duy nhất một bản ghi theo phạm vi được chọn.
- **Foreign key:** ràng buộc tham chiếu, ngăn orphan relationships.
- **Unique constraint:** bảo vệ các giá trị không trùng như external order ID.
- **Check constraint:** ngăn trạng thái/tổng tiền không hợp lệ.
- **Index:** tăng tốc tìm kiếm/join/order nhưng làm tăng chi phí ghi và lưu trữ.
- **Transaction:** nhóm các thay đổi cần atomicity.

### Truy vấn đơn hàng theo tenant

~~~sql
SELECT TOP (20)
    o.OrderId,
    o.ExternalOrderId,
    o.Status,
    o.TotalAmount,
    o.CreatedAt,
    c.Email
FROM dbo.Orders AS o
INNER JOIN dbo.Customers AS c
    ON c.TenantId = o.TenantId
   AND c.CustomerId = o.CustomerId
WHERE o.TenantId = @TenantId
ORDER BY o.CreatedAt DESC, o.OrderId DESC;
~~~

**@TenantId** ở đây là tham số do API cung cấp từ **principal/tenant authorization đã xác minh**, không phải một query parameter bất kỳ mà client tự đặt. Dùng **parameterized queries/prepared statements**, không nối chuỗi SQL với input của người dùng.

Nếu dữ liệu Orders có hàng triệu rows, index cần được thiết kế theo pattern truy vấn, selectivity, execution plan và số records thực tế. **Có index không đảm bảo mọi query đều dùng index**, và thêm index có thể làm INSERT/UPDATE chậm hơn.

### N+1 queries từ ORM

Với Java Spring Data/JPA, một API lấy 100 orders rồi chạy 100 truy vấn riêng để lấy customers có thể tạo **N+1 problem** và tăng DB round trips. Giải pháp có thể là:

- Join/fetch phù hợp với access pattern.
- Batch fetching theo giới hạn hợp lý.
- Projection chỉ lấy các trường cần thiết.
- Cache có kiểm soát, không làm mất tính nhất quán nghiệp vụ.

Không cố eager-load mọi quan hệ ở mọi endpoint, vì có thể tạo join phình to. Dùng query plan/metrics để kiểm tra trước.

## 13. ACID transactions và optimistic concurrency

Ứng dụng tạo order và trừ tồn kho cần đảm bảo trạng thái hợp lệ dù request bị retry hoặc hai người cùng cập nhật.

**ACID** trong hệ quản trị quan hệ gồm:

- **Atomicity:** toàn bộ thay đổi trong transaction cùng commit hoặc rollback.
- **Consistency:** constraints và quy tắc dữ liệu được bảo vệ.
- **Isolation:** các transaction đồng thời được cô lập theo isolation level.
- **Durability:** dữ liệu đã commit được lưu bền vững theo cam kết dịch vụ.

### Transaction trong phạm vi một database

Ví dụ trong một stored procedure nhận tham số:

~~~sql
CREATE OR ALTER PROCEDURE dbo.ConfirmOrder
    @TenantId UNIQUEIDENTIFIER,
    @OrderId BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE dbo.Orders
           SET Status = 'CONFIRMED'
         WHERE TenantId = @TenantId
           AND OrderId = @OrderId
           AND Status = 'PENDING';

        IF @@ROWCOUNT <> 1
            THROW 50001, 'Order not found or not pending', 1;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;
~~~

Ví dụ thể hiện **một thay đổi trạng thái có điều kiện**. Nó **chưa** kiểm tra quyền người dùng, tồn kho, payment authorization, event notification hoặc idempotency toàn bộ quy trình. Chạy DDL này chỉ trong lab của bạn; mọi stored procedure cần được security review khi đưa production.

### Optimistic concurrency bằng rowversion

Hai clients đọc cùng order, một client cập nhật trước. Client thứ hai cần phát hiện giá trị đã thay:

~~~sql
UPDATE dbo.Orders
SET Status = 'CANCELLED'
WHERE TenantId = @TenantId
  AND OrderId = @OrderId
  AND RowVer = @ExpectedRowVersion
  AND Status = 'PENDING';
~~~

Nếu **@@ROWCOUNT = 0**, có thể order không tồn tại, trạng thái đã thay hoặc rowversion đã đổi. API có thể trả **409 Conflict** sau khi xác minh nguyên nhân theo hợp đồng. Những tham số **@...** được ràng buộc bởi ứng dụng/stored procedure; không chạy trực tiếp khi chưa khai báo.

### Retry phải hiểu tính idempotent

Với lỗi mạng, client có thể không biết transaction đã commit chưa. Retry mù một **INSERT** có thể tạo bản ghi trùng. Cần idempotency key như **(TenantId, ExternalOrderId)** và logic xử lý unique violation theo hợp đồng API.

**Không coi retry mọi lỗi SQL là an toàn**: deadlock, connection reset và timeout có cơ chế xử lý khác nhau; phân biệt lỗi transient với lỗi dữ liệu/constraint/authorization không thể tự hồi phục.

## 14. Isolation levels, blocking và deadlocks

Azure SQL Database hỗ trợ cơ chế transaction isolation của SQL Server theo cấu hình dịch vụ/database. **READ COMMITTED** với row versioning ở các cấu hình thích hợp có thể giảm nhiều tình huống reader/writer blocking; nhưng vẫn phải hiểu locks và update conflicts.

| Hiện tượng | Ví dụ | Hướng xử lý |
|---|---|---|
| **Blocking** | Transaction A giữ lock, B chờ | Giảm thời gian transaction, index, chia batch |
| **Deadlock** | A/B giữ tài nguyên khác thứ tự rồi chờ nhau | Thiết kế thứ tự cập nhật nhất quán, retry có kiểm soát |
| **Optimistic conflict** | Rowversion không còn khớp | Đọc lại và trả conflict/retry nghiệp vụ |
| **Long-running transaction** | Batch sửa hàng triệu rows | Xử lý batch, kiểm tra log và locking |
| **Stale reads** | Replica bất đồng bộ chưa có bản ghi mới | Chọn nơi đọc/consistency theo nhu cầu |

Một giao dịch ngân hàng có yêu cầu nhất quán khác với dashboard thống kê. Không bật isolation nghiêm ngặt nhất cho tất cả truy vấn mà chưa đánh giá throughput/lock contention.

## 15. Row-Level Security và mô hình shared database

Với nhiều tenants cùng một database, **Row-Level Security (RLS)** của SQL Database có thể giúp áp dụng bộ lọc dữ liệu tại tầng database.

~~~text
API validates user/tenant claims
          |
          v
Open pooled DB connection
          |
          v
Set verified tenant context safely
          |
          v
Execute parameterized SQL
          |
          v
RLS security policy filters TenantId rows
~~~

### RLS là defense in depth, không phải phép màu

Một mẫu thiết kế có thể dùng **SESSION_CONTEXT** để truyền TenantId đã được xác minh, rồi dùng predicate function trong RLS. Tuy nhiên:

- Ứng dụng phải thiết lập/kiểm tra context cho **mỗi request và mỗi connection checkout**.
- Connection pool tái sử dụng sessions: cần reset/kiểm soát context, không cho request B dùng tenant context của request A.
- Không cấp người dùng cuối quyền SQL trực tiếp hoặc quyền thay đổi security policy tùy ý.
- Thiết kế cơ chế truyền tenant đáng tin; **SESSION_CONTEXT tự nó không xác thực JWT**.
- Kiểm thử query SELECT/UPDATE/DELETE, stored procedures, background jobs và migration với nhiều tenants.

Nếu backend dùng chung một privileged DB login và có lỗi SQL injection, RLS chỉ dựa vào context do ứng dụng tùy ý đặt có thể bị vượt qua. Cần kết hợp **least-privilege SQL permissions, query parameters, application authorization, RLS và negative tests**.

### Đối chứng tối thiểu

| Test | Kỳ vọng |
|---|---|
| Tenant A đọc Order A | Thành công |
| Tenant A đọc Order B | Không trả dữ liệu |
| Tenant A sửa Order B | Không thay dữ liệu |
| Tenant B dùng pooled connection sau A | Không bị rò context A |
| Background job không có tenant context | Được kiểm soát rõ theo role/design |
| SQL principal ít quyền | Không thể vô hiệu RLS/security policy |

Không lấy việc một câu SELECT có WHERE TenantId làm bằng chứng đã bảo vệ **toàn bộ API**.

## 16. Sharding và điều phối nhiều databases

Khi lượng dữ liệu/giao dịch vượt khả năng hoặc mục tiêu cô lập của một database, có thể chia thành **shards**. Mỗi shard là một database chứa phần dữ liệu theo shard key.

~~~text
API / Tenant routing service
            |
    shard map (tenant -> database)
        /        |         \
       v         v          v
  sql-db-01  sql-db-02   sql-db-03
  tenants A-E tenants F-J tenants K-N
~~~

### Chọn shard key

Ví dụ **TenantId**:

- Một tenant được định tuyến nhất quán tới database xác định.
- Dễ cô lập/di chuyển tenant nếu dữ liệu chủ yếu ở phạm vi tenant.
- Tránh join/transaction xuyên shard đối với giao dịch cùng tenant.

Nhưng nếu một tenant quá lớn, shard theo tenant không chia nhỏ được riêng tenant đó. Nếu chọn **OrderId** hoặc hash key, truy vấn toàn bộ dữ liệu tenant có thể cần fan-out nhiều shards.

### Những công việc tăng lên

1. Lưu và bảo vệ **shard map/routing metadata**.
2. Kiểm tra version schema nhất quán giữa các shards.
3. Reshard/di chuyển tenant có checkpoint, data verification và rollback.
4. Giám sát sức khỏe từng database, tránh một shard vượt capacity.
5. Giải quyết truy vấn analytics xuyên shards bằng giải pháp đọc/batch thích hợp.
6. Tránh kỳ vọng distributed transaction/foreign key xuyên databases hoạt động như trong một database.

**Sharding không phải lựa chọn khởi đầu mặc định**. Hãy chứng minh bottleneck thật, tối ưu schema/index/tier/pool trước, rồi đánh giá chi phí vận hành phân mảnh.

## 17. Ứng dụng Java kết nối Azure SQL Database

Với ứng dụng Java/Spring Boot, có thể dùng **Microsoft JDBC Driver for SQL Server** cùng connection pool như HikariCP. Trong môi trường Azure, ưu tiên **Microsoft Entra authentication/managed identity** theo phiên bản JDBC và nền tảng hỗ trợ; tránh lưu SQL username/password trong Git.

### Cấu hình JDBC dùng Entra ID

Ví dụ connection string (thay placeholders bằng thông tin đã được cấp):

~~~properties
spring.datasource.url=jdbc:sqlserver://<SERVER_NAME>.database.windows.net:1433;databaseName=<DATABASE_NAME>;encrypt=true;trustServerCertificate=false;hostNameInCertificate=*.database.windows.net;loginTimeout=30;authentication=ActiveDirectoryDefault
spring.datasource.driver-class-name=com.microsoft.sqlserver.jdbc.SQLServerDriver
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.minimum-idle=2
spring.datasource.hikari.connection-timeout=30000
~~~

**ActiveDirectoryDefault** là phương thức Microsoft JDBC driver hỗ trợ trong các phiên bản phù hợp, có thể sử dụng Azure identity chain (managed identity trong Azure, developer credentials ở local) khi các thư viện cần thiết được cài. Kiểm tra **Microsoft JDBC driver version, azure-identity dependencies, Java version, hostname và hỗ trợ cách xác thực** trước khi áp dụng. Đây là đoạn cấu hình minh họa, không phải cấu hình đã được kiểm thử trên một subscription thực.

### Maven dependencies cần chuẩn bị

~~~xml
<dependencies>
    <dependency>
        <groupId>com.microsoft.sqlserver</groupId>
        <artifactId>mssql-jdbc</artifactId>
        <version>DRIVER_VERSION_DA_KIEM_TRA</version>
    </dependency>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-identity</artifactId>
        <version>AZURE_IDENTITY_VERSION_DA_KIEM_TRA</version>
    </dependency>
</dependencies>
~~~

Đây là **trích đoạn**, phải thay bằng các versions được BOM/phát hành chính thức hỗ trợ và bổ sung framework dependencies. Các placeholders không build được nguyên trạng. Với user-assigned managed identity, cần cấu hình client ID/cách chọn identity phù hợp theo driver/SDK, không mặc định chain luôn chọn đúng principal.

### Phần SQL cần làm cho managed identity

Một Function App/App Service/AKS workload có managed identity **chưa tự có user trong database**. Người có quyền phù hợp trong Azure SQL phải:

1. Cấu hình **Microsoft Entra administrator** hoặc cơ chế server identity/Entra auth được hỗ trợ.
2. Tạo database user cho identity đã được xác minh.
3. Gán **least-privilege database permissions**.
4. Đảm bảo network từ workload tới SQL hoạt động.
5. Kiểm thử kết nối dưới chính identity của workload.

Ví dụ T-SQL mang tính hướng dẫn, thực hiện bởi principal có quyền:

~~~sql
CREATE USER [orders-api-mi] FROM EXTERNAL PROVIDER;
-- Tùy workload, cấp các quyền đúng bảng/schema:
GRANT SELECT, INSERT, UPDATE ON OBJECT::dbo.Orders TO [orders-api-mi];
GRANT SELECT ON OBJECT::dbo.Customers TO [orders-api-mi];
~~~

**Tên principal** phải khớp managed identity/Entra object thực tế, và quyền cấp trên hai bảng chỉ là ví dụ. Nếu workload dùng stored procedures, có thể cấp EXECUTE thay vì DML trực tiếp. **Không cấp db_owner hoặc server admin** chỉ để sửa lỗi đăng nhập. Trên một số cấu hình Entra/SQL, thao tác CREATE USER có tiền đề/giới hạn về directory permissions, không xử lý bằng cách dùng SQL admin password trong pipeline.

### Connection pool và concurrency

Nếu 50 AKS pods × 20 connections/pod, hệ thống có thể mở tới **1.000 database connections** trước khi tính batch jobs. Azure SQL tier có giới hạn worker/session/concurrent workload; cần sizing:

~~~text
Tổng kết nối tiềm năng
= Số instance * maximumPoolSize
+ các clients/queues/migrations khác
~~~

- Chọn pool size dựa trên concurrency/query latency, không theo số CPU core một cách máy móc.
- Đặt timeout/retry có jitter cho lỗi transient; không retry lỗi credential hoặc SQL constraint.
- Đóng ResultSet/Statement/Connection theo pattern đảm bảo trả connection về pool.
- Khi scale-out app, kiểm tra database capacity, DTU/vCore utilization, workers và connection limits.
- Với Azure Functions có scale burst, tránh tạo connection mới cho **mỗi invocation** nếu runtime/SDK có mô hình pooling phù hợp.

## 18. Authentication và authorization: Azure RBAC khác SQL permissions

Một user có quyền tạo database trong Azure Portal không nhất thiết có quyền đọc dữ liệu trong dbo.Orders. Có hai mảng quyền khác nhau:

| Mảng | Chủ thể | Ví dụ |
|---|---|---|
| **Azure management plane** | IAM trên subscription/resource group/server/database | Azure SQL DB Contributor có thể quản lý resource theo role definition |
| **SQL data plane** | Contained database user/SQL login/Entra principal | SELECT/INSERT/EXECUTE, roles như db_datareader khi phù hợp |
| **Network layer** | IP/VNet/Private Endpoint/Firewall | Client có đường TCP/TLS tới logical server |

### Ưu tiên Entra ID với managed identity

- Giảm secret tĩnh trong deployment.
- Thuận tiện audit principal/role theo workload.
- Có thể tách quyền ứng dụng và migration runner.
- Hỗ trợ thu hồi quyền theo identity lifecycle.

SQL authentication vẫn có use cases được hỗ trợ; nếu dùng, lưu credential trong secret manager, xoay vòng và không nhúng password trong JDBC URL được commit.

### Tách runtime và migration permissions

| Identity | Quyền nên có |
|---|---|
| **Java API runtime** | SELECT/INSERT/UPDATE/EXECUTE trong schema/bảng cần thiết |
| **Schema migration runner** | Quyền DDL có kiểm soát trong thời điểm deploy |
| **Read-only reporter** | SELECT theo dữ liệu cho phép; có thể dùng read endpoint riêng |
| **DB administrator** | Thay đổi cấu hình, khôi phục và troubleshooting có phê duyệt |

Đừng cấp quyền **ALTER TABLE/DROP** cho API runtime chỉ vì Flyway cần chạy. Đưa migrations vào pipeline dùng identity tách biệt và ghi audit.

## 19. Public network, SQL firewall và Private Endpoint

Azure SQL logical server có các lựa chọn truy cập mạng tùy cấu hình:

- **Public endpoint** với firewall rules và public network access policy.
- **Private Endpoint (Private Link)** trong VNet/subnet với private IP.
- Các cơ chế kiểm soát bổ sung như VNet rules/service endpoints theo khả năng dịch vụ và mô hình đang sử dụng.

**Firewall được mở không cấp quyền dữ liệu.** Một client vẫn cần xác thực hợp lệ và được SQL GRANT quyền.

### Kiến trúc mạng riêng

~~~text
AKS / App Service / Functions
     |
     | VNet Integration / AKS node network
     v
Private VNet/subnet + DNS Resolver
     |
     | Private Endpoint IP
     v
Azure SQL logical server
  <SERVER>.database.windows.net
     |
     +-- Azure SQL database
~~~

Private Endpoint là một network interface trong VNet, **không phải database replica**. Để kết nối, client vẫn dùng tên server SQL theo thiết kế; DNS được cấu hình để trỏ đúng đường private.

### Private DNS

Private Link cho Azure SQL thường liên quan DNS zone:

~~~text
privatelink.database.windows.net
~~~

Khi dùng Private Endpoint, cần cấu hình Private DNS zone/records, zone links hoặc DNS forwarding phù hợp để **<SERVER>.database.windows.net** phân giải tới private IP theo cơ chế của Azure. **Không hard-code private IP vào connection string** làm bỏ qua DNS/TLS hostname verification; IP có thể thay đổi khi sửa endpoint.

### Những bẫy networking

1. AKS có VNet nhưng Private DNS zone chưa link tới node VNet.
2. App Service/Functions chưa được cấu hình **VNet Integration/egress** phù hợp.
3. Firewall/NSG/DNS resolver chặn kết nối ở path thực tế.
4. SQL public access bị tắt trước khi chuẩn bị đường private cho migration runner.
5. Kết nối có DNS đúng nhưng Entra token/SQL user chưa được cấp quyền.

**Chỉ tắt public network access sau khi** đã kiểm thử app, migrations, monitoring, admin emergency path và DR region qua đường private được phê duyệt. Thao tác khóa network có thể ngừng toàn bộ dịch vụ.

## 20. Bảo vệ dữ liệu: TLS, TDE, Always Encrypted, audit

Azure SQL Database hỗ trợ nhiều lớp bảo vệ với mục tiêu khác nhau:

| Cơ chế | Bảo vệ | Điều không thay thế |
|---|---|---|
| **TLS/encrypted connection** | Dữ liệu trên đường truyền client–service | SQL user permissions |
| **Transparent Data Encryption (TDE)** | Encryption at rest ở tầng database/storage theo cơ chế dịch vụ | Bảo vệ cột khỏi principal đã có quyền đọc |
| **Customer-managed key** | Tùy nhu cầu kiểm soát khóa TDE và dịch vụ hỗ trợ | Query-level authorization, rotation plan |
| **Always Encrypted** | Cột nhạy cảm với khả năng quản trị khóa phía client theo cấu hình | Query flexibility, app auth hoặc network |
| **Dynamic data masking** | Hiển thị dữ liệu được mask ở những ngữ cảnh phù hợp | Security boundary cho dữ liệu thực |
| **Auditing/Defender** | Quan sát hoạt động, anomaly/vulnerability protection theo tính năng | Ngăn toàn bộ SQL injection tự động |
| **RLS** | Bộ lọc hàng theo security predicate | Xác thực tenant và quản lý quyền đầy đủ |

### Dữ liệu nhạy cảm và privacy

- Chỉ lưu dữ liệu thật sự cần cho nghiệp vụ.
- Mã hóa/ẩn thông tin PII theo classification, retention và pháp lý tổ chức.
- Không log JDBC connection string có password hoặc access token.
- Cấu hình audit sink, retention, RBAC và cảnh báo khi permission/schema bị thay.
- Kiểm tra ảnh hưởng của key rotation, backup restore và encrypted columns.

**Always Encrypted** cần thiết kế driver, encryption metadata và client-side key management; nó không phải một checkbox có thể bật cho mọi cột mà không ảnh hưởng ứng dụng. Không nhầm Always Encrypted với TDE.

## 21. Tính sẵn sàng cao trong một region

Azure SQL Database cung cấp cơ chế high availability được quản lý theo service tier, giúp xử lý một số lỗi phần cứng/phần mềm mà không cần tự cài SQL Server Always On trên máy ảo.

Nhưng **HA không đồng nghĩa tuyệt đối không bao giờ có gián đoạn**. Khi failover trong region, các kết nối TCP đang mở có thể bị ngắt; ứng dụng cần xử lý lỗi transient, reconnect, retry có kiểm soát và phục hồi transaction idempotently.

### Zone redundancy

Ở các service tiers/regions được hỗ trợ, **zone-redundant configuration** phân bố các thành phần HA trên nhiều **Availability Zones** của region để giảm phụ thuộc vào một zone.

| Kịch bản | HA mặc định/theo tier | Zone redundancy |
|---|---|---|
| SQL process/node lỗi | Cơ chế failover managed hỗ trợ | Hỗ trợ theo cấu hình |
| Một Availability Zone mất | Không mặc định mọi cấu hình chịu được | Giúp giảm rủi ro theo thiết kế được hỗ trợ |
| Toàn region mất | Không đủ | Không đủ |
| Ứng dụng không reconnect được | Không được sửa bằng HA DB | Phải sửa app retry/connection |

**Không bật zone redundancy chỉ bằng tên cấu hình trong tài liệu**: kiểm tra region, tier, SKU, quota, availability và chi phí cụ thể. Một số mô hình có tính năng zone redundancy khác nhau theo service objective/hardware.

### Health check và connection pool

Sau failover nội vùng, Java JDBC pool có thể giữ connections lỗi. Pool validation, retry policy và transaction boundary phải được thử. Đừng cấu hình retry vô hạn cho mọi câu lệnh write; có thể gây duplicate actions khi commit outcome chưa rõ.

## 22. Backup tự động, PITR và long-term retention

Azure SQL Database có cơ chế **automated backups** và **point-in-time restore (PITR)** theo retention của service tier. Dịch vụ quản lý backup chain; người vận hành lựa chọn retention/backup storage redundancy theo tính năng có sẵn và yêu cầu compliance.

Các khái niệm:

| Cơ chế | Mục tiêu | Giới hạn cần hiểu |
|---|---|---|
| **PITR** | Khôi phục database tới một thời điểm trong retention window | Thường tạo một database mới, không đơn giản nút undo một bảng |
| **Long-term retention (LTR)** | Giữ backups theo lịch tuần/tháng/năm cho tuân thủ | Chính sách/range/giá và cách restore phụ thuộc cấu hình |
| **Geo-restore** | Khôi phục từ backup geo-redundant khi vùng chính không khả dụng | RTO/RPO phụ thuộc backup replication và khôi phục, không phải failover tức thì |
| **Active geo-replication** | Duy trì readable secondary qua async replication | Không thay thế PITR sau lỗi logic/xóa dữ liệu |
| **Failover group** | Điều phối failover cho nhóm database và endpoint | Không thay backup/archive/restore quy trình riêng |

### Trường hợp PITR đúng

Lúc 13:20, một migration lỗi đã cập nhật sai 80.000 đơn hàng. Hệ thống phát hiện lúc 13:30. Bạn có thể khôi phục database từ một thời điểm **trước lỗi**, rồi so sánh dữ liệu/đưa trạng thái đúng trở lại theo runbook.

**PITR thường khôi phục ra database khác**, cần thời gian và tài nguyên; không bấm restore trực tiếp lên database production mà không hiểu hệ quả. Nếu production vẫn ghi dữ liệu từ 13:20 đến 13:30, chuyển toàn bộ sang bản restore có thể mất các giao dịch hợp lệ trong khoảng đó. Có thể cần **reconciliation**, export một phần dữ liệu hoặc quy trình đổi tên/cutover được kiểm chứng.

### Backup retention và luật dữ liệu

- Chọn PITR retention theo RPO, khả năng khôi phục và chi phí.
- Cấu hình LTR khi yêu cầu giữ dài hạn.
- Kiểm tra backup storage redundancy, vùng lưu và data residency.
- Thử restore định kỳ vào môi trường cô lập, đo thời gian và xác minh dữ liệu.
- Hạn chế quyền restore/export, vì một bản sao database có thể chứa toàn bộ dữ liệu nhạy cảm.

**Backup tồn tại không có nghĩa restore đã được thử thành công.** Một kế hoạch DR cần bằng chứng thực hành với quyền, mạng, encryption key và ứng dụng.

## 23. Active geo-replication và failover groups

Azure SQL Database có khả năng **active geo-replication** để tạo secondary database ở region khác theo mô hình hỗ trợ. Replication giữa các region là **bất đồng bộ**, vì vậy có thể có **replication lag và nguy cơ mất các transaction gần thời điểm sự cố**.

~~~text
Azure Region A                          Azure Region B
  App A                                   App B / Standby
    |                                        |
    v                                        v
  Primary Azure SQL Database -----> Readable secondary
                        async replication
~~~

### Active geo-replication không phải multi-primary

Trong kiến trúc truyền thống, **primary là nơi xử lý writes**; secondary thường phục vụ reads và khả năng promote. **Không suy luận secondary tự chấp nhận ghi nghiệp vụ đồng thời vào cùng dữ liệu**. Nếu ứng dụng có read-after-write consistency nghiêm ngặt, đọc từ geo-secondary vừa replicate có thể trả dữ liệu cũ.

### Failover groups

**Failover group** quản lý một tập database cùng chiến lược geo-failover giữa các logical servers theo khả năng dịch vụ. Nó cung cấp những điểm truy cập logic (listeners) để giảm yêu cầu hard-code server primary trong ứng dụng.

~~~text
Java API connection config
     |
     | Failover group read-write listener
     v
Current primary region
     |
     | Async replication
     v
Secondary region

Sau failover:
  Listener được cập nhật để trỏ primary mới
  App mở lại connections và xử lý retries
~~~

**Listener DNS không làm connection đang mở tự động di chuyển không gián đoạn**. Ứng dụng phải reconnect và tuân thủ DNS TTL, driver behavior và failover runbook. Một số ứng dụng còn có listener cho mục đích read-only; cần phân biệt write endpoint và read-only/read-scale endpoint theo tài liệu.

### Failover group không sao chép mọi thứ

Khi đưa ứng dụng sang region B, bạn vẫn phải chuẩn bị:

- Logical server secondary, quyền quản trị và server-level settings cần tương thích.
- Private Endpoint, Private DNS, VNet integration, firewall rules ở vùng dự phòng.
- Managed identity/Entra admin và SQL database users theo mô hình hỗ trợ.
- Backend services, APIs, secrets, monitoring, Key Vault, CI runner và app config.
- DR data cho những dịch vụ **ngoài SQL** như Blob, Redis, messaging.
- Cơ chế tạm dừng writes/fencing và tránh lỗi split-brain theo tình huống.

Nếu vùng A mất hoàn toàn, **geo-failover có thể mất dữ liệu chưa được replicate**. Đừng tuyên bố RPO=0 chỉ vì có secondary. Đặt RTO/RPO dựa trên phép đo và cam kết dịch vụ.

## 24. RTO/RPO và quyết định kiến trúc DR

**Recovery Time Objective (RTO):** khoảng thời gian chấp nhận được để dịch vụ hoạt động lại. **Recovery Point Objective (RPO):** lượng dữ liệu theo thời gian tối đa có thể mất sau một sự cố.

Ví dụ hệ thống đặt hàng:

~~~text
Sự cố toàn region bắt đầu lúc 10:00
Secondary xác nhận dữ liệu tới 09:59:45
Ứng dụng nhận traffic lại lúc 10:18

RPO thực đo giả định: 15 giây dữ liệu chưa chắc có ở secondary
RTO thực đo giả định: 18 phút
~~~

Số liệu **chỉ minh họa**, không phải SLO hoặc cam kết của Azure SQL. Bài toán RPO phải tính cả các transactions chưa đồng bộ, DB ngoài Azure SQL và các side effects như thanh toán/email.

### Bảng chọn phương án

| Mục tiêu | Khả năng/cấu hình cần cân nhắc |
|---|---|
| Lỗi node hoặc failover nội region | Managed HA + retry/JDBC pool |
| Lỗi Availability Zone | Zone redundancy nếu region/tier hỗ trợ |
| Xóa/cập nhật sai dữ liệu | PITR/LTR + reconciliation |
| Mất cả region | Geo-replication/failover group hoặc geo-restore theo RTO/RPO |
| Đọc dữ liệu ở region khác | Geo-secondary/read routing, chấp nhận replica lag |
| Bảo vệ khỏi credential bị đánh cắp | Identity/RBAC, network, auditing, key rotation |

**Một biện pháp không thay thế tất cả.** Geo-replication có thể sao chép cả DELETE sai tới secondary; PITR và audit vẫn cần thiết.

## 25. Triển khai schema: migration khác deploy ứng dụng

Ứng dụng Java có thể phát hành bằng container image/JAR, nhưng database schema là **trạng thái bền vững**. Thay đổi schema phải được áp dụng có phiên bản và xét khả năng tương thích ứng dụng đang chạy.

Các công cụ phổ biến:

| Công cụ/cách | Mô hình | Điều cần quản lý |
|---|---|---|
| **Flyway** | SQL migrations có version trong repository | Lịch sử migrations, thứ tự, checksum, rollback strategy |
| **Liquibase** | Changelog và changesets | Labels/contexts, review, rollback nếu hỗ trợ |
| **SQL Database Projects / DACPAC / SqlPackage** | State-based schema deployment với diff và deployment plan | Drift, schema compare, destructive changes review |
| **Manual T-SQL scripts có quản trị** | Cần thiết ở một số hệ thống | Approval, idempotency, audit và khả năng tái lập |
| **Data migration tools** | Di chuyển dữ liệu từ hệ cũ | Cutover, consistency, validation và network |

**Không chạy automatic Hibernate ddl-auto=update trong production rồi coi đó là chiến lược migration.** Nó khó bảo đảm review, rollback, quản lý dữ liệu và multi-environment consistency.

### Mẫu versioned SQL migrations

~~~text
db/migration/
  V001__create_customers.sql
  V002__create_orders.sql
  V003__add_order_note.sql
  V004__index_orders_by_created_at.sql
~~~

Khi Flyway/Liquibase chạy từ migration identity, công cụ duy trì schema history theo khả năng của nó. **Ứng dụng runtime không nên có quyền ALTER/DROP bảng** chỉ vì pipeline cần DDL.

### Quản lý schema version trong multi-tenant databases

Với **database-per-tenant**, một release có thể cần cập nhật hàng trăm DB:

- Dùng schema version tracking theo database.
- Deploy theo waves/rings (canary tenants → nhóm nhỏ → toàn bộ).
- Giới hạn concurrency migration, tránh tạo spike vCore/I/O.
- Dừng rollout nếu phát hiện failure và ghi tenant nào đang ở version nào.
- Hỗ trợ ứng dụng chạy khi một số databases tạm ở version trước theo compatibility policy.

**Không giả định tất cả tenants đã migrate chỉ vì pipeline xử lý xong resource group đầu tiên.**

## 26. Expand-and-contract để triển khai ít gián đoạn

Mẫu **expand → migrate/backfill → switch → contract** giúp code cũ và code mới cùng chạy trong thời gian rolling update.

### Bước 1: Expand

Ứng dụng cần trường ghi chú đơn hàng. Thay vì xóa hoặc đổi kiểu cột hiện có, thêm cột nullable:

~~~sql
ALTER TABLE dbo.Orders
ADD CustomerNote NVARCHAR(500) NULL;
~~~

Code cũ không dùng cột mới vẫn có thể hoạt động. Migrations cần được thử với dữ liệu/khối lượng tương tự production và kiểm tra locking, thời gian chạy, tier capacity.

### Bước 2: Deploy code tương thích

Triển khai Java API v2 có thể đọc/ghi CustomerNote, nhưng vẫn xử lý records có NULL từ code cũ. Trong rolling update hoặc nhiều region, có thể cùng lúc chạy v1 và v2.

### Bước 3: Backfill an toàn

Nếu muốn điền giá trị default cho dữ liệu cũ, chạy **theo batch có checkpoint** và kiểm tra logs/locks. Không chạy một UPDATE toàn bảng rất lớn trong giờ cao điểm mà không đo I/O, log generation và lock duration.

### Bước 4: Switch traffic/feature

Sau khi xác minh v2 đã hoạt động, bật feature flag và quan sát errors/latency. Ứng dụng v1 còn có thể chạy hay rollback được cho tới khi thay đổi contract breaking được tiến hành.

### Bước 5: Contract

Chỉ khi đã xác minh không còn consumers dùng schema cũ, mới cân nhắc:

- Đổi constraint NULL → NOT NULL khi dữ liệu đã đầy đủ.
- Xóa cột/đối tượng đã deprecated.
- Dọn compatibility code và indexes dư thừa.

**Contract là bước rủi ro phá tương thích và có thể không rollback được bằng lệnh đơn giản.** Cần backup/PITR, review và thời điểm thực thi phù hợp. Trong một hệ thống nhiều services, giữ compatibility window đủ dài cho mọi consumer, kể cả batch jobs.

## 27. Triển khai data migration từ SQL Server cũ

Nếu hệ thống đã chạy SQL Server on-premises/VM, việc đưa lên Azure SQL Database không phải chỉ export BACPAC rồi import.

### Những câu hỏi preflight

1. App đang dùng những features của SQL Server (Agent, CLR, cross-database queries, linked servers...) có phù hợp Azure SQL Database?
2. Database size, throughput, peak writes và latency yêu cầu?
3. Có cần near-zero downtime hay có maintenance window?
4. Mức dữ liệu có thể mất trong cutover?
5. Authentication/connection strings có thay sang Entra/managed identity?
6. Network path từ migration worker tới nguồn/đích?
7. Cơ chế migration nào phù hợp: bulk copy/BACPAC, Azure Database Migration Service, Data Factory, replication hoặc công cụ được hỗ trợ?
8. Ai xác nhận application-level data correctness sau cutover?

### Các pha

~~~text
Inventory + compatibility assessment
          |
          v
Target SQL Database sizing/security
          |
          v
Initial schema + data load
          |
          v
Validation: row counts, checksums,
constraints, indexes, sample business workflows
          |
          v
Incremental synchronization (nếu cần)
          |
          v
Maintenance/cutover with write fencing
          |
          v
Application connection switch + smoke tests
          |
          v
Monitor, rollback window, decommission later
~~~

**BACPAC** là gói export/import schema và data phù hợp một số kịch bản, **không phải cơ chế online HA/DR hoặc giữ mọi state instance-level**. Với database lớn hoặc uptime nghiêm ngặt, cần đánh giá migration pipeline/cutover chi tiết hơn.

### Kiểm chứng dữ liệu sau di chuyển

- Số lượng bản ghi theo bảng/tenant.
- Các primary/foreign keys và unique constraints.
- Decimal, datetime, collation và Unicode.
- Indexes, stored procedures, functions và permissions.
- Các business invariants như tổng tiền/trạng thái orders.
- Queries quan trọng và p95 latency.
- Không có ứng dụng còn ghi song song vào nguồn cũ ngoài thiết kế.

Đừng xóa nguồn ngay sau khi một câu **SELECT COUNT(*)** trùng khớp. Cutover cần người chịu trách nhiệm và rollback strategy đã thử.

## 28. Tạo và xem SQL Database trên Azure Portal

Với một subscription lab có quyền tạo tài nguyên và ngân sách được phê duyệt:

1. Mở [Azure Portal](https://portal.azure.com), chọn **Azure SQL** hoặc **SQL databases**.
2. Chọn **Create SQL database**, đúng subscription/resource group và tên database.
3. Chọn **logical server** đã có hoặc tạo server mới. Tên server phải tuân thủ quy tắc và duy nhất theo dịch vụ.
4. Chọn region phù hợp với workload/residency.
5. Chọn **compute + storage tier**, service objective, storage size và provisioned/serverless (nếu hỗ trợ).
6. Cấu hình backup storage redundancy, zone redundancy và các tính năng liên quan theo policy/SKU.
7. Chọn authentication, ưu tiên Entra ID với quy trình quản trị phù hợp; nếu dùng SQL auth lab, quản lý credential an toàn.
8. Trong Networking, xác định public endpoint/firewall hay **Private Endpoint** theo topology.
9. Kiểm tra auditing, Defender/monitoring và tags.
10. Review giá ước tính/cấu hình rồi mới tạo.

**Tạo SQL Database có thể phát sinh chi phí ngay khi provision**, ngay cả lúc chưa có dữ liệu. Nếu chưa được cấp lab subscription, có thể thực hành read-only trên database mẫu được quản trị viên cung cấp, hoặc lập thiết kế trên giấy.

### Tránh lỗi lúc mới tạo

- Không chọn Business Critical/Hyperscale quá lớn chỉ vì một mặc định GUI.
- Không bật **Allow Azure services and resources to access this server** một cách vô thức: tùy cơ chế, tùy chọn này có thể mở đường public cho nhiều Azure resources hơn mong muốn.
- Không cấu hình server admin/password trong tài liệu chia sẻ.
- Không tắt public access trước khi migration runner/ứng dụng có đường private.
- Không dùng database production làm nơi chạy thử DDL.
- Không tạo dev/staging/prod dùng chung secret hoặc identity admin.

## 29. Azure CLI: kiểm tra cấu hình an toàn

Các lệnh dưới dùng **Azure CLI trong Bash/Azure Cloud Shell**, chủ yếu chỉ đọc metadata. Các placeholder cần được thay bằng tài nguyên mà bạn được cấp quyền:

~~~bash
az login
az account list --output table
az account set --subscription "<LAB_SUBSCRIPTION_ID>"
az account show --output table

RG="<SQL_RESOURCE_GROUP>"
SERVER="<AZURE_SQL_LOGICAL_SERVER_NAME>"
DB="<DATABASE_NAME>"

az sql server show \
  --resource-group "$RG" \
  --name "$SERVER" \
  --query "{name:name,location:location,publicNetworkAccess:publicNetworkAccess}" \
  --output json

az sql db show \
  --resource-group "$RG" \
  --server "$SERVER" \
  --name "$DB" \
  --query "{name:name,status:status,sku:sku.name,tier:sku.tier,capacity:sku.capacity,zoneRedundant:zoneRedundant}" \
  --output json
~~~

Danh sách databases trong logical server:

~~~bash
az sql db list \
  --resource-group "$RG" \
  --server "$SERVER" \
  --query "[].{name:name,status:status,sku:sku.name}" \
  --output table
~~~

Kiểm tra firewall rules:

~~~bash
az sql server firewall-rule list \
  --resource-group "$RG" \
  --server "$SERVER" \
  --output table
~~~

Các lệnh **show/list** không chứng minh client Java có thể kết nối hay user có quyền SELECT. Chúng cũng không thay kiểm tra Private Endpoint, DNS, Entra token và SQL permissions.

### Không thay cấu hình server trên tài nguyên chung để học

Các lệnh như **az sql db create/update/delete**, **az sql server firewall-rule create**, đổi **public-network-access** hoặc failover có thể làm phát sinh chi phí hoặc gây gián đoạn. Trước khi thực hiện, cần:

1. Xác minh resource names, subscription và môi trường.
2. Đọc **az sql db create --help** và tính tương thích của service objective với region.
3. Có approval, budget và phương án rollback.
4. Thử trên lab trước.

Ví dụ một **lệnh tạo database** trong lab trên logical server đã tồn tại:

~~~bash
az sql db create \
  --resource-group "$RG" \
  --server "$SERVER" \
  --name "orders-sandbox" \
  --service-objective "S0"
~~~

Lệnh chọn **S0** là service objective kiểu DTU Standard truyền thống, dùng để minh họa CLI. Tính khả dụng, quota và giá phải được xác minh trước; **không xem S0 là khuyến nghị mặc định cho ứng dụng production**. Nếu mục tiêu bài tập là vCore/GP/BC/Hyperscale, hãy chọn SKU bằng Portal hoặc các tham số CLI được kiểm tra cho region/tier thực.

## 30. Kết nối và truy vấn T-SQL trong lab

Khi có database test và principal được cấp quyền, dùng SSMS, VS Code/SQL tooling phù hợp, JDBC hoặc **sqlcmd** có hỗ trợ phương thức xác thực bạn sử dụng.

### Kiểm tra read-only

~~~sql
SELECT
    DB_NAME() AS DatabaseName,
    SUSER_SNAME() AS CurrentLogin,
    ORIGINAL_LOGIN() AS OriginalLogin,
    SYSUTCDATETIME() AS CheckedAtUtc;
~~~

Kiểm tra service objective ở context database theo schema DMV mà tài khoản được phép xem:

~~~sql
SELECT
    edition,
    service_objective,
    elastic_pool_name
FROM sys.database_service_objectives;
~~~

Tùy role/engine compatibility, một số metadata/DMVs cần quyền phù hợp hoặc có column names khác theo phiên bản. Khi query không hoạt động, xác minh tài liệu schema và quyền thay vì cấp db_owner ngay.

### Query tài nguyên gần đây

Azure SQL Database có các DMV/resource statistics như **sys.dm_db_resource_stats** phục vụ quan sát CPU, I/O và worker/resource usage theo khả năng của dịch vụ:

~~~sql
SELECT TOP (20)
    end_time,
    avg_cpu_percent,
    avg_data_io_percent,
    avg_log_write_percent
FROM sys.dm_db_resource_stats
ORDER BY end_time DESC;
~~~

Số liệu là **tỷ lệ so với giới hạn resource tier/database** theo metric, không phải phần trăm của toàn máy vật lý. Cần xem timeframe, dữ liệu có sẵn và kết hợp Azure Monitor metrics cho bức tranh đầy đủ.

### Phân tích query chậm

- Bật/kiểm tra **Query Store** theo cấu hình dịch vụ và retention.
- Xem top queries theo duration, CPU, logical reads, regression.
- Đọc actual/estimated execution plan trong môi trường được cấp phép.
- Kiểm tra parameter sniffing, statistics, blocking và missing/unused indexes.
- Đánh giá tác động của truy vấn lên các tenants khác.

Không tự tạo index cho mọi đề xuất "missing index" mà chưa đo write overhead, index overlap và workload.

## 31. Giám sát sức khỏe và tối ưu hiệu năng

Một database production cần giám sát cả **SQL-level** và **application-level** signals.

| Nhóm | Tín hiệu | Câu hỏi cần trả lời |
|---|---|---|
| Compute | CPU %, DTU/vCore utilization | DB đang bão hòa compute không? |
| I/O | Data IO %, log write %, storage latency | Query hay log ghi đang nghẽn? |
| Storage | Data size, allocated space, growth | Khi nào chạm quota, cần retention? |
| Concurrency | Sessions, workers, blocking, deadlocks | Scale app có tạo quá nhiều kết nối? |
| Queries | Query Store duration, CPU, plan regressions | Bản schema/code nào gây chậm? |
| Application | Connection pool, p95/p99 DB call, retry count | Người dùng bị ảnh hưởng thế nào? |
| DR | Replica lag, failover state, backup status | Có đáp ứng RPO/RTO không? |
| Security | Login failures, audit anomalies, access changes | Credential/permissions có bị lạm dụng? |
| Cost | Compute, storage, backups, networking | DB có đúng kích thước chi phí không? |

### Alerting có hành động rõ ràng

Ví dụ:

- CPU hoặc data IO gần ngưỡng trong nhiều phút **và** p95 latency tăng.
- Free storage/allocated capacity gần giới hạn.
- Deadlock rate hoặc error retries tăng đột ngột.
- Replication lag vượt RPO mục tiêu.
- Không có successful connections hoặc business transactions trong một khoảng bất thường.

**Không chỉ alert theo một metric CPU>70%** mà không biết ai nhận, quy trình ứng cứu và tác động ứng dụng. Trong serverless, CPU/resume pattern có thể khác provisioned; thresholds nên xét kiểu compute.

### Performance tuning trước scale-up

1. Xác định slow SQL statements và execution plans.
2. Kiểm tra indexes, filter theo TenantId, statistics và pagination.
3. Giảm N+1 hoặc quá nhiều round trips.
4. Kiểm tra transaction duration, lock contention và DB connection pool.
5. Tối ưu query trước khi thêm vCores khi bottleneck nằm ở thiết kế.
6. Nếu vấn đề thật sự là capacity, đổi tier/vCores hoặc chia workloads theo bài toán.

**Scale-up database có thể không sửa deadlock hoặc một query scan thiếu điều kiện tenant.** Sau thay đổi service objective cần đo lại latency, throughput và chi phí.

## 32. Cost Management cho Azure SQL Database

Chi phí SQL PaaS không chỉ là số database.

| Thành phần | Có thể phát sinh chi phí |
|---|---|
| **Compute** | DTU/vCore, provisioned hoặc serverless usage theo tier |
| **Storage** | Database data storage, allocated/provisioned space |
| **Backups** | PITR vượt allowance, LTR, redundancy theo model giá |
| **Replicas** | Geo-secondary/read replicas, service tier và vùng |
| **Network** | Private Endpoint, DNS resolver, NAT, egress, data transfer |
| **Monitoring/security** | Azure Monitor logs, auditing storage, Defender plans |
| **App/CI** | AKS/App Service/Functions, migration runners |
| **License savings** | Azure Hybrid Benefit/reserved capacity nếu điều kiện áp dụng |

Không chốt một giá cố định mà không biết **region, tier, vCore/DTU, storage, compute model và uptime**. Sử dụng Azure Pricing Calculator, Cost Management, Azure Advisor và dashboard resource usage.

### Ví dụ quyết định dựa trên chi phí

Ba databases dev/test thường idle từ 20:00–08:00. Serverless auto-pause **có thể tiết kiệm** nếu chúng thực sự đáp ứng điều kiện pause, nhưng background jobs/health probes có thể ngăn pause. Đừng tự kết luận tiết kiệm 50% compute nếu chưa đo trạng thái auto-pause và billing.

Một elastic pool có thể giảm chi phí 100 tenant databases ít hoạt động, nhưng nếu tất cả tenants cùng chạy báo cáo lúc 9:00, pool cần capacity lớn hoặc cơ chế lịch biểu/cô lập.

### Tags, budget và cleanup

- Gán tags **environment**, **owner**, **application**, **costCenter** theo policy.
- Đặt budget alerts theo resource group/subscription.
- Review tier hàng tháng; đổi tier có kế hoạch, kiểm thử performance.
- Xóa những database lab không còn cần sau khi đã export/backup dữ liệu theo chính sách.
- **Không xóa logical server/resource group dùng chung** chỉ để kết thúc bài thực hành.

**Budget alert không tự dừng tính phí**. DB provisioned có thể tiếp tục tính chi phí khi không có request.

## 33. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Bước kiểm tra |
|---|---|---|
| Client timeout, không connect SQL | DNS, Private Endpoint, firewall, route/proxy, SQL unavailable | DNS từ app VNet, network policy, SQL health |
| Login failed / 18456 | Principal/token/password sai, DB user chưa được tạo | Entra principal, DB user, auth configuration |
| **Cannot open server** do firewall | Public endpoint chưa allow IP hoặc public network bị tắt | Firewall rule, actual egress, private DNS |
| **403** từ Key Vault khi DB connection config lấy secret | Identity/Key Vault RBAC/network sai | Managed identity, vault logs, reference status |
| **40613/40197** hoặc kết nối đứt tạm thời | DB/service unavailable/failover, transient faults | Azure status, retry/backoff, failover events |
| **40501** hoặc resource limit errors | Service busy/compute giới hạn | Metrics, concurrency, service objective |
| **1205 deadlock** | Transactions cập nhật tài nguyên chéo | Deadlock graphs, transaction design, bounded retry |
| **2627/2601** duplicate key | Unique/idempotency conflict | Unique constraints, external request ID, client behavior |
| **547** foreign key conflict | Dữ liệu không thỏa quan hệ | FK design, transaction ordering |
| **Query timeout** | Chậm, blocking, network hoặc threshold thấp | Query Store, execution plan, pool timeout |
| CPU cao nhưng requests thấp | Query scan, background batch, missing index | Query Store, DMVs, regression |
| Elastic pool chậm giờ cao điểm | Nhiều DB tranh shared resources | Pool metrics, split workload, min/max |
| Geo-secondary đọc thiếu data mới | Async replication lag | Read routing, lag metrics, consistency expectations |
| Function/AKS scale-out làm DB quá tải | Nhiều connection pools tăng cùng instances | Max pool sizes, worker/session limits |
| Migrations bị treo | DDL lock, large table scan, long transactions | Blocking sessions, batch plan, maintenance |
| Restore xong app vẫn không chạy | DNS/identity/config/DB name khác | Connection string, SQL user, schema, permissions |

Không dùng **SQL admin account** để chữa mọi lỗi login hoặc firewall. Tách lỗi **network → authentication → authorization → query/runtime** theo từng phép kiểm tra.

## 34. Tình huống A: API Java gặp lỗi kết nối sau khi tắt public access

**Bối cảnh:** Orders API trên App Service chạy bình thường qua SQL public endpoint. Nhóm bảo mật tắt public network access sau khi tạo Private Endpoint. Ngay sau đó API trả 500 và JDBC timeout.

### Phân tích

Có Private Endpoint không đồng nghĩa App Service đang đi qua nó. Có thể App Service chưa bật VNet Integration, subnet/DNS không đúng hoặc đường egress vẫn tới public endpoint.

### Runbook

1. Xác định app instance/region và time of change.
2. Kiểm tra App Service VNet Integration/AKS VNet, routing và resolver.
3. Phân giải **<SERVER>.database.windows.net** từ đúng network của workload.
4. Xác minh private IP/Private DNS zone link, NSG và connection policy.
5. Kiểm tra managed identity/SQL user sau khi có đường mạng.
6. Test kết nối bằng identity và database tương ứng, không phải admin từ laptop.
7. Khôi phục cấu hình mạng theo change record nếu outage kéo dài; không bật Allow all Azure services một cách thiếu kiểm soát.
8. Ghi RCA và bổ sung negative/positive connectivity tests vào CI/CD infrastructure.

### Bài học

Trước khi khóa public network phải xác minh đường kết nối từ **app, CI migration runner, monitoring và vị trí DR**. Private Endpoint là một phần kiến trúc, không tự hoàn thành network migration.

## 35. Tình huống B: Java scale-out làm elastic pool bão hòa

**Bối cảnh:** ứng dụng SaaS có 50 tenants trên elastic pool. Khi một batch invoice chạy, 20 AKS pods tăng thành 60 pods, đồng thời DB CPU/log I/O đạt giới hạn; nhiều requests timeout.

### Chẩn đoán

1. Xem **pool-level và per-database metrics** để tìm tenant gây tải.
2. Tính tổng kết nối tiềm năng: **60 pods × pool size**.
3. Xem Query Store top consumers/lock waits và batch schedule.
4. Xem retries có đang tạo retry storm và tải tăng thêm không.
5. Kiểm tra HPA/app scaling: thêm pods có thể khiến database bottleneck nặng hơn.

### Biện pháp

- Giới hạn concurrency và pool size hợp lý.
- Batch với kích thước giới hạn, tránh transaction dài.
- Tối ưu query/index và retry with jitter.
- Dời báo cáo nặng khỏi giờ cao điểm, hoặc cô lập database tenant lớn.
- Tăng pool capacity khi dữ liệu đo chứng minh cần.
- Đặt workload-aware alerts cho CPU, log write %, latency và timeouts.

**Đừng chỉ tăng vCores/replicas theo phản xạ.** Nếu code tạo N+1 queries hoặc một transaction giữ lock lâu, có thể tiếp tục gặp sự cố ở tier cao hơn.

## 36. Tình huống C: migration xóa cột làm API cũ lỗi

**Bối cảnh:** pipeline v2 xóa cột **LegacyCode** trước khi AKS v1 pods kết thúc rolling update. Một số requests từ pods cũ thất bại vì SQL query vẫn cần cột đó.

### Nguyên nhân

Migrations đã chạy theo kiểu **contract-before-expand** mà không xét coexistence của ứng dụng v1/v2. Rollback code về v1 cũng có thể không chạy vì cột đã bị xóa.

### Runbook

1. Dừng rollout làm thay đổi dữ liệu thêm nếu có thể và xác định ảnh hưởng.
2. Dùng migration tương thích hoặc hotfix thêm lại contract dữ liệu theo thiết kế được kiểm chứng; tránh đoán kiểu/cấu trúc cột cũ.
3. Nếu dữ liệu đã bị mất, đánh giá PITR restore ở DB riêng và phương án reconciliation.
4. Kiểm tra mọi consumers: API pods, background jobs, reporting, Functions và queues.
5. Chạy lại smoke/business tests rồi mới mở traffic đầy đủ.
6. Thay đổi pipeline theo mô hình **expand → deploy compatible code → backfill → contract** ở các release tách nhau.

**Khôi phục schema không tự khôi phục nội dung của cột đã xóa**. Một số sự cố yêu cầu backup restore/data recovery chứ không chỉ CREATE/ALTER TABLE.

## 37. Tình huống D: failover region và nguy cơ mất transaction

**Bối cảnh:** primary Azure SQL ở region A bị outage. Secondary region B vẫn online nhưng có replication lag. Đội vận hành dự định promote B ngay để khôi phục Orders API.

### Quy trình điều phối

1. Xác nhận sự cố và xác định trạng thái ứng dụng/DB/geo-replication.
2. Đánh giá **RPO hiện thực** và các transaction có thể chưa replicate.
3. Nếu có thể, chặn writes cũ, kiểm soát việc primary quay lại để tránh hai điểm ghi mâu thuẫn.
4. Thực hiện failover theo loại cấu hình/ủy quyền được phê duyệt.
5. Xác minh listener DNS, Private Endpoint, SQL auth/permissions và app connections ở B.
6. Chạy smoke tests bằng dữ liệu không phá hoại; đối soát đơn hàng/payment/message backlog.
7. Cảnh báo kinh doanh nếu có nguy cơ thiếu các orders gần thời điểm outage.
8. Lập kế hoạch failback có kiểm soát sau khi A phục hồi.

**Không bảo đảm RPO=0 với async geo-replication.** Giao dịch đã được client thông báo thành công nhưng chưa replicate có thể cần quy trình đối soát từ event log/outbox/payment processor nếu nền tảng thiết kế cho việc đó.

## 38. Bài thực hành an toàn: thiết kế Azure SQL cho Orders API

### Bối cảnh

Một SaaS Java API chạy trên AKS/App Service có:

- 40 tenants, mỗi tenant từ vài trăm đến vài triệu orders.
- Hai tenants lớn chiếm 60% traffic.
- Transaction tạo order cần nhất quán, có idempotency key.
- Production ở region A, cần phương án DR tại region B.
- Chỉ truy cập SQL từ mạng ứng dụng/private migration runner.
- Có môi trường dev/staging/prod; không dùng dữ liệu nhạy cảm thật trong lab.

### Phần A: lựa chọn mô hình

So sánh ba phương án:

1. Một **shared database + TenantId + RLS**.
2. **Database per tenant + elastic pool**.
3. Mô hình kết hợp: tenants lớn dùng DB riêng, tenants nhỏ dùng pool.

Lập bảng:

| Tiêu chí | Shared DB | DB per tenant/pool | Hybrid |
|---|---|---|---|
| Chi phí ở tải nhỏ | Thường thuận lợi | Quản lý nhiều DB hơn | Linh hoạt |
| Cô lập restore theo tenant | Khó hơn | Dễ hơn ở DB riêng | Tùy tenant |
| Cô lập performance | Có noisy-neighbor | Pool vẫn có cạnh tranh | Có thể dành compute riêng |
| Schema migrations | Một DB | Hàng chục DB | Hai loại vòng đời |
| Authorization | TenantId/RLS cực kỳ quan trọng | DB principal/routing | Cả hai |
| Scale tenant lớn | Có thể gây hot spot | Chuyển riêng được | Dễ bố trí riêng |
| Complexity vận hành | Thấp hơn lúc đầu | Tăng theo số DB | Cao nhất |

Chọn một phương án và giải thích dựa trên SLO, RPO/RTO, quy mô, residency và năng lực vận hành. Không chọn giải pháp chỉ theo tên tier.

### Phần B: kiểm tra metadata (read-only)

Nếu được cấp một Azure SQL logical server/database lab:

~~~bash
az login
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

RG="<LAB_RESOURCE_GROUP>"
SERVER="<LAB_SQL_SERVER>"
DB="<LAB_SQL_DATABASE>"

az sql server show \
  --resource-group "$RG" \
  --name "$SERVER" \
  --query "{name:name,location:location,publicNetworkAccess:publicNetworkAccess}" \
  --output json

az sql db show \
  --resource-group "$RG" \
  --server "$SERVER" \
  --name "$DB" \
  --query "{name:name,sku:sku.name,status:status,zoneRedundant:zoneRedundant}" \
  --output json
~~~

Không cần tạo DB mới hoặc mở firewall nếu chỉ có quyền Reader. Ghi lại **service tier, compute, network mode, backup policy và identity approach** theo những metadata mà bạn được phép xem.

### Phần C: SQL schema trong database sandbox riêng

Nếu DBA cho phép tạo objects ở sandbox:

1. Tạo **Customers**, **Orders** và index theo mục 11.
2. Thêm ít nhất hai tenants với dữ liệu giả.
3. Kiểm thử FK/unique constraints: order không thể tham chiếu customer tenant khác.
4. Kiểm tra duplicate ExternalOrderId trong cùng tenant bị unique constraint chặn.
5. Chạy truy vấn mục 12 với tham số TenantId đã xác định.
6. Đo execution plan trước/sau thêm index nếu có dữ liệu đủ để quan sát.
7. Thử mô phỏng optimistic concurrency bằng RowVer với hai clients.

**Không chạy DDL trên production**, và không lưu email/thông tin cá nhân thật trong bài tập.

### Phần D: thiết kế kết nối Java

Viết cấu hình JDBC dùng:

- Logical server FQDN.
- Database name đúng môi trường.
- TLS với certificate validation.
- Managed identity/Entra authentication nếu runtime/driver hỗ trợ.
- SQL user chỉ có quyền cần thiết.
- Connection pool có giới hạn theo số replicas.

Kiểm tra kiến trúc Private Endpoint/Private DNS trên giấy nếu không có đường lab. Không hard-code admin password vào application.properties rồi commit.

### Phần E: mô phỏng deployment schema v2

1. Thêm CustomerNote nullable bằng migration có version.
2. Xác minh code v1 vẫn đọc dữ liệu bình thường.
3. Triển khai v2 hiểu cột mới, chạy integration tests.
4. Backfill theo batch nếu cần.
5. Chỉ contract ở một release khác sau khi mọi consumers đã chuyển.
6. Viết kế hoạch rollback nếu migration làm hỏng dữ liệu.

### Phần F: kế hoạch HA/DR

Đặt RTO/RPO giả định của doanh nghiệp, chọn:

- Zone redundancy trong region A nếu tier/region hỗ trợ.
- PITR retention/LTR theo yêu cầu.
- Failover group hoặc geo-restore cho region B theo mức RTO/RPO.
- App/network/Entra/private DNS/CI runner ở B.
- Quy trình đối soát transactions có thể chưa replicate.

**Không tạo sự cố giả bằng cách failover production hoặc xóa DB thật**. Dùng tabletop exercise/runbook và restore vào sandbox khi được phê duyệt.

### Bảng bằng chứng cần nộp

| Nội dung | Bằng chứng |
|---|---|
| Azure SQL lựa chọn | Logical server, single DB/elastic pool, tier và compute model |
| Data model | DDL, PK/FK/unique/check, index và lý do |
| Multi-tenancy | Shared vs DB-per-tenant vs hybrid decision |
| Java | JDBC auth/TLS, connection pool và least-privilege |
| Network | Public firewall hoặc Private Endpoint/DNS |
| Schema migration | Expand-contract plan, version và negative tests |
| Resilience | HA/zone, PITR, geo-DR, RTO/RPO |
| Observability | Queries, CPU/I/O/latency/connection metrics |
| Cost | Ước tính tier/storage/backup/replicas và cleanup |
| Security | Không secrets/data thật trong tài liệu |

## 39. Checklist triển khai production

- [ ] Azure SQL Database được chọn sau khi đánh giá MI/SQL Server VM và compatibility.
- [ ] Logical server, region, resource group và data residency rõ ràng.
- [ ] Single DB/elastic pool/tenant model có lý do về capacity, isolation và chi phí.
- [ ] DTU/vCore, GP/BC/Hyperscale, provisioned/serverless dựa trên workload đo được.
- [ ] Schema có PK/FK/unique/check, indexes và retention policy phù hợp.
- [ ] Tenant authorization/RLS/pooling đã test với nhiều users/tenants.
- [ ] T-SQL dùng parameterized queries và transaction/optimistic concurrency đúng.
- [ ] Java JDBC dùng TLS, xác thực an toàn và pool size được giới hạn.
- [ ] SQL users/managed identities có least-privilege; migration identity tách runtime.
- [ ] Public firewall/Private Endpoint/DNS được kiểm thử từ app, runner và vùng DR.
- [ ] TDE/auditing/defender/key policies đáp ứng nhu cầu dữ liệu.
- [ ] Query Store, Azure Monitor/alerts và logging không lộ secrets.
- [ ] Có PITR/LTR phù hợp và restore drill vào DB cô lập.
- [ ] HA/zone redundancy được kiểm tra theo SKU/region.
- [ ] Geo-DR/failover group có kịch bản RTO/RPO và app/network ở vùng dự phòng.
- [ ] Migrations versioned, có expand-contract và compatibility tests.
- [ ] Multi-DB/tenant migration có canary/ring rollout và tracking.
- [ ] Có runbook cho transient errors, deadlocks, throttling và schema failure.
- [ ] Cost Management/budget/tags và quy trình review tier thường kỳ.
- [ ] Đã thực hiện load test, DR tabletop và kiểm thử negative access.

## 40. Câu hỏi tự kiểm tra

1. Azure SQL Database khác Managed Instance và SQL Server VM ở trách nhiệm vận hành nào?
2. Logical server có phải một VM chứa các database không?
3. Vì sao Azure RBAC Contributor không tự cấp quyền SELECT dữ liệu?
4. Khi nào single database tốt hơn elastic pool?
5. Elastic pool cô lập dữ liệu tenants và CPU như thế nào?
6. DTU và vCore khác nhau trong sizing/tính giá ra sao?
7. General Purpose, Business Critical, Hyperscale giải quyết những nhu cầu khác nhau nào?
8. Khi nào serverless auto-pause không xảy ra và có thể gây bất lợi?
9. Shared database/shared schema có rủi ro gì khi thiếu TenantId filter?
10. Database-per-tenant có ưu/nhược gì khi có 1.000 tenants?
11. Composite FK (TenantId, CustomerId) ngăn loại lỗi dữ liệu nào?
12. Vì sao UNIQUE (TenantId, ExternalOrderId) hỗ trợ idempotency?
13. Rowversion khác timestamp thế nào và được dùng ở đâu?
14. RLS có tự xác thực JWT/tenant không? Connection pooling có rủi ro gì?
15. Sharding có tăng độ phức tạp query và transaction như thế nào?
16. Java runtime identity và database migration identity nên khác nhau vì sao?
17. Có Private Endpoint nhưng app không kết nối được: cần kiểm tra lớp nào?
18. TLS, TDE và Always Encrypted bảo vệ các mối đe dọa khác nhau ra sao?
19. Zone redundancy khác geo-replication và backup PITR ở điểm nào?
20. Geo-secondary có thể mất những giao dịch nào sau outage region?
21. Failover group DNS listener giúp gì và không giúp gì?
22. Restore PITR database có tự khôi phục các writes hợp lệ sau thời điểm restore không?
23. Vì sao schema migration dùng expand-and-contract an toàn hơn DROP trực tiếp?
24. Flyway/Liquibase khác phương pháp DACPAC theo kiểu quản lý schema nào?
25. Một SaaS 500 database cần làm gì để kiểm soát rollout schema?
26. Query Store và sys.dm_db_resource_stats giúp chẩn đoán vấn đề gì?
27. Khi AKS HPA tăng replicas, database connections có thể tăng thế nào?
28. Tại sao CPU cao không luôn được sửa bằng việc tăng vCores?
29. Một backup còn tồn tại có đồng nghĩa DR plan đã đạt RTO/RPO không?
30. Khi chọn tier rẻ nhất, những rủi ro SLO và chi phí nào cần cân nhắc?

## 41. Tài liệu tham khảo

- [Azure SQL Database overview](https://learn.microsoft.com/azure/azure-sql/database/sql-database-paas-overview) — bản chất PaaS và các mô hình Azure SQL.
- [Choose between Azure SQL products](https://learn.microsoft.com/azure/azure-sql/azure-sql-iaas-vs-paas-what-is-overview) — SQL Database, Managed Instance, SQL Server VM.
- [Azure SQL Database purchasing models](https://learn.microsoft.com/azure/azure-sql/database/purchasing-models) — DTU và vCore.
- [Service tiers in the vCore model](https://learn.microsoft.com/azure/azure-sql/database/service-tiers-sql-database-vcore) — General Purpose, Business Critical, Hyperscale.
- [Azure SQL Database serverless](https://learn.microsoft.com/azure/azure-sql/database/serverless-tier-overview) — auto-scaling, auto-pause và giới hạn.
- [Elastic pools](https://learn.microsoft.com/azure/azure-sql/database/elastic-pool-overview) — chia sẻ compute giữa databases.
- [Multi-tenant SaaS tenancy patterns](https://learn.microsoft.com/azure/azure-sql/database/saas-tenancy-app-design-patterns) — shared DB, DB per tenant và sharding.
- [Connect and query Azure SQL Database](https://learn.microsoft.com/azure/azure-sql/database/connect-query-content-reference-guide) — công cụ và kết nối.
- [Microsoft Entra authentication to Azure SQL](https://learn.microsoft.com/azure/azure-sql/database/authentication-aad-overview) — danh tính và SQL users.
- [Private Link for Azure SQL](https://learn.microsoft.com/azure/azure-sql/database/private-endpoint-overview) — Private Endpoint/DNS.
- [SQL Database security overview](https://learn.microsoft.com/azure/azure-sql/database/security-overview) — firewall, encryption, auditing và data protection.
- [Automated backups in Azure SQL Database](https://learn.microsoft.com/azure/azure-sql/database/automated-backups-overview) — PITR/LTR và retention.
- [Active geo-replication for Azure SQL Database](https://learn.microsoft.com/azure/azure-sql/database/active-geo-replication-overview) — secondary bất đồng bộ.
- [Failover groups for Azure SQL Database](https://learn.microsoft.com/azure/azure-sql/database/failover-group-sql-db) — geo-failover và listeners.
- [Query Store](https://learn.microsoft.com/sql/relational-databases/performance/monitoring-performance-by-using-the-query-store) — query tuning và regression.
- [Microsoft JDBC Driver for SQL Server](https://learn.microsoft.com/sql/connect/jdbc/microsoft-jdbc-driver-for-sql-server) — Java JDBC/TLS/authentication.
- [Azure SQL database migration guidance](https://learn.microsoft.com/azure/azure-sql/migration-guides/database/sql-server-to-sql-database-overview) — assessment và migration.
- [Azure CLI: az sql db](https://learn.microsoft.com/cli/azure/sql/db) — tạo, xem và cấu hình databases.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — ước tính chi phí.

**Kết luận:** Azure SQL Database giúp giảm công việc vận hành hạ tầng SQL Server, nhưng kiến trúc dữ liệu an toàn vẫn cần quyết định **single database hay elastic pool, mô hình tenant và schema, DTU/vCore cùng service tier, bảo mật mạng và danh tính, backup/HA/DR, migrations và hiệu năng truy vấn**. Hãy thiết kế dữ liệu theo giao dịch và ownership, triển khai schema có version và khả năng tương thích, thử restore/failover, giám sát từ SQL tới ứng dụng Java và điều chỉnh chi phí bằng số liệu thực thay vì phỏng đoán.
