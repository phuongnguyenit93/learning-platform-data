# SQL Server trên Azure Virtual Machines

Một doanh nghiệp đang vận hành hệ thống kế toán trên **Microsoft SQL Server**, với stored procedures, SQL Server Agent jobs, linked servers, yêu cầu kiểm soát phiên bản hệ điều hành và các ứng dụng Java/.NET truy cập qua mạng riêng. Nhóm muốn chuyển cơ sở dữ liệu lên Azure nhưng chưa thể thay đổi ngay các tính năng cấp instance hoặc quy trình vận hành truyền thống. **SQL Server trên Azure Virtual Machines (SQL Server on Azure VMs)** là phương án đưa SQL Server lên máy ảo Azure theo mô hình **Infrastructure as a Service (IaaS)**, giữ mức kiểm soát lớn đối với Windows/Linux, SQL Server instance, cấu hình storage, kết nối và cơ chế high availability.

Lợi ích là có thể tận dụng kinh nghiệm SQL Server hiện có và nhiều tính năng cấp instance. Đánh đổi: **Azure quản lý hạ tầng vật lý**, còn nhóm vận hành vẫn chịu trách nhiệm đáng kể về cài đặt, database, sao lưu, cấu hình an toàn, cập nhật bản vá, hiệu năng, HA/DR và chi phí license. Tạo một VM có SQL Server chạy được **không đồng nghĩa đã có hệ thống database production sẵn sàng**.

Bài thuộc chương **Cơ sở dữ liệu quan hệ**, module **CLOUD_PROVIDERS_AZURE**: tìm hiểu Azure từ subscription, resource group, Microsoft Entra ID, mạng ảo tới compute, storage, bảo vệ dữ liệu, giám sát và quản lý chi phí. Bài học tập trung lựa chọn kiến trúc, triển khai và vận hành SQL Server trên Azure VM; ví dụ dùng Windows Server/SQL Server phổ biến nhưng nhiều nguyên tắc cũng áp dụng cho SQL Server trên Linux khi tính năng tương ứng được hỗ trợ.

> **Phạm vi kỹ thuật:** Azure và SQL Server cập nhật thường xuyên. Tổ hợp phiên bản SQL Server, Windows/Linux, VM SKU, disk SKU, Availability Zone, Azure Backup, SQL IaaS Agent extension và HA feature có giới hạn hỗ trợ riêng. Các lệnh minh họa không phải kịch bản triển khai production nguyên vẹn: trước khi chạy, xác minh subscription, quyền, region, edition, license, compatibility matrix và tài liệu hiện hành của cấu hình được chọn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt SQL Server trên Azure VM với **Azure SQL Database** và **Azure SQL Managed Instance**.
2. Giải thích ranh giới trách nhiệm **IaaS** giữa Azure và đội quản trị SQL.
3. Lựa chọn image, edition, phiên bản, CPU/RAM, license và SQL IaaS Agent extension.
4. Thiết kế managed disks cho **data, transaction log, tempdb, backup**, IOPS, throughput và latency.
5. Thiết kế private networking, DNS, NSG, danh tính và mã hóa để giảm rủi ro truy cập trái phép.
6. Lập kế hoạch backup/restore, RPO/RTO và kiểm tra phục hồi thực tế.
7. So sánh **Always On Availability Groups**, **Failover Cluster Instances**, Availability Zones và disaster recovery.
8. Sử dụng Azure CLI và T-SQL/DMV để xác minh hiện trạng, hiệu năng và cấu hình.
9. Thiết lập giám sát, cảnh báo, maintenance runbook, patching và tối ưu chi phí.
10. Đánh giá quy trình migration và những tiêu chí cho biết khi nào nên dùng PaaS thay vì VM.

## 2. Định vị SQL Server trên Azure VM trong hệ sinh thái Azure

Ba lựa chọn quan trọng:

| Tiêu chí | SQL Server trên Azure VM | Azure SQL Managed Instance | Azure SQL Database |
|---|---|---|---|
| Mô hình | **IaaS** với SQL Server do khách hàng quản lý | **PaaS** tương thích nhiều đặc tính SQL Server instance | **PaaS** tối ưu database |
| Kiểm soát hệ điều hành | Cao: VM, OS và SQL configuration | Không quản lý OS trực tiếp | Không quản lý OS/instance |
| SQL Server Agent / cấp instance | Dùng theo edition và cấu hình hỗ trợ | Có nhiều tính năng cấp instance, có khác biệt | Không tương đương SQL Server Agent truyền thống |
| Bản vá OS/SQL | Khách hàng lập kế hoạch, thực thi và kiểm tra, có công cụ Azure hỗ trợ | Nền tảng quản lý phần đáng kể | Nền tảng quản lý phần đáng kể |
| Backup/restore | Khách hàng thiết kế và kiểm thử, có dịch vụ hỗ trợ | Built-in backups theo chính sách dịch vụ | Built-in backups theo chính sách dịch vụ |
| High availability | Khách hàng thiết kế AG/FCI hoặc cơ chế phù hợp | HA do dịch vụ quản lý theo SLA | HA do dịch vụ quản lý theo SLA |
| Instance-level dependencies | Nhiều khả năng tương thích hơn với SQL Server tự quản lý | Cần kiểm tra feature gaps | Có nhiều khác biệt cấp instance |
| Đơn vị chi phí | VM + disks + network + SQL license + vận hành | Compute/storage theo mô hình PaaS | Compute/storage theo mô hình PaaS |

**Chọn VM** khi yêu cầu hệ điều hành, SQL Server engine/edition, phần mềm tích hợp, SQL Server instance features hoặc migration compatibility không phù hợp các lựa chọn PaaS. **Chọn PaaS** khi ứng dụng có thể thích ứng và muốn giảm trách nhiệm OS/SQL patching, backup/HA.

Không quyết định chỉ vì "Azure VM giống máy chủ cũ": đội ngũ cần so sánh **tổng chi phí sở hữu (TCO)**, bảo mật, quy trình recovery, downtime khi bảo trì và năng lực vận hành.

## 3. Kiến trúc tham chiếu cho một SQL Server VM

~~~mermaid
flowchart TD
  C["Java / .NET API trên AKS, VM hoặc Container Apps"] --> DNS["Private DNS / SQL listener FQDN"]
  DNS --> SQL["SQL Server trên Azure VM (private IP)"]
  SQL --> DAT["Managed disks: data files"]
  SQL --> LOG["Managed disks: transaction logs"]
  SQL --> TMP["tempdb: disk phù hợp"]
  SQL --> BK["Backup vào vault / Blob theo phương án"]
  SQL --> OBS["Azure Monitor + SQL telemetry"]
  OPS["Quản trị qua Bastion / mạng quản trị"] --> SQL
  ID["AD / Entra và quyền SQL phù hợp"] -.-> SQL
~~~

Mô hình đơn VM giúp học các thành phần, **không phải thiết kế HA**. Nếu VM hỏng hoặc Availability Zone gặp sự cố, ứng dụng có thể mất database cho tới khi VM hoặc backup được phục hồi. Production quan trọng thường cần xem xét ít nhất hai SQL replicas/instances, DNS/listener, bảo vệ dữ liệu và khả năng failover.

### Những ranh giới cần phân biệt

- **VM:** compute instance, có CPU/RAM, NIC và hệ điều hành.
- **Managed disk:** tài nguyên block storage gắn VM; không phải Azure Blob container.
- **SQL Server:** dịch vụ database chạy trên VM và quản lý files, log, memory, connections.
- **SQL virtual machine resource:** một resource quản trị Azure liên kết VM có SQL Server với khả năng quản lý chuyên biệt thông qua SQL IaaS Agent extension khi được hỗ trợ; không phải VM thứ hai.
- **Azure SQL Database:** dịch vụ PaaS khác; không nên dùng firewall/Private Endpoint hướng dẫn dành cho PaaS để thay thế cấu hình SQL trên VM.

## 4. Mô hình trách nhiệm chia sẻ

| Thành phần | Trách nhiệm chính |
|---|---|
| Datacenter, phần cứng vật lý, hypervisor nền | Azure |
| Chọn region, zone, VM SKU, disk SKU và availability | Khách hàng thiết kế; Azure cung cấp khả năng dịch vụ |
| Guest OS, hardening, accounts, patching/reboot | Khách hàng, có công cụ Azure hỗ trợ |
| SQL Server version, setup, edition, options, agent jobs | Khách hàng |
| Database schema, indexes, logins, query tuning | Khách hàng |
| Backup policies, retention, restore testing | Khách hàng quyết định và kiểm tra; Azure có dịch vụ thực thi hỗ trợ |
| HA/DR, RPO/RTO, failover procedure | Khách hàng thiết kế và kiểm thử |
| VNet, NSG, DNS, private access, TLS | Khách hàng cấu hình trên nền tảng Azure |
| Monitor, alerts, audit logs, security response | Khách hàng cấu hình và vận hành, có dịch vụ Azure cung cấp dữ liệu |

Một VM dùng image SQL Server từ Azure Marketplace có thể có cài đặt SQL sẵn. Điều này **không chuyển trách nhiệm quản lý database và backup sang Azure SQL Database**.

## 5. Chọn image SQL Server và cách triển khai

Có ba cách tiếp cận thông dụng:

1. **Marketplace SQL Server image:** chọn image chứa Windows Server và SQL Server phiên bản/edition được cung cấp; thích hợp khi muốn cấu hình nhanh, tuân theo license model và khả năng SQL VM integration.
2. **Tự cài SQL Server trên Azure VM:** tạo VM OS trước, sau đó cài SQL Server bằng media/license được phép; cần đăng ký/quản lý như SQL VM khi điều kiện áp dụng.
3. **Di chuyển VM hoặc database có sẵn:** sử dụng công cụ Azure Migrate, backup/restore, log shipping, AG seeding hoặc cách chuyển dữ liệu phù hợp; cần đánh giá license, driver và version tương thích.

**Không nên chọn VM image "mới nhất" theo cảm tính.** Xác minh phiên bản SQL Server được ứng dụng hỗ trợ, database compatibility level, OS lifecycle, licensing, SQL features và kế hoạch patching.

### Windows và Linux

SQL Server trên Linux hỗ trợ nhiều tính năng quan trọng, nhưng cách quản trị, scripts, HA, authentication và extensions có thể khác Windows. Nếu ứng dụng phụ thuộc Windows authentication, COM, SSIS hoặc phần mềm chỉ có trên Windows, cần kiểm tra tương thích thay vì giả định Linux là thay thế trực tiếp.

### Hai loại tài nguyên Azure

Ví dụ có thể có:

~~~text
Microsoft.Compute/virtualMachines          vm-sql-prod-01
Microsoft.SqlVirtualMachine/sqlVirtualMachines  vm-sql-prod-01
~~~

Tài nguyên SQL VM bổ sung quản lý cấp Azure thông qua SQL IaaS Agent extension và registration theo hỗ trợ hiện hành. Nó **không thay thế SQL Server process** và không tự làm ứng dụng dùng Managed Instance. Khi quản lý VM bằng IaC, theo dõi cả VM resource và SQL VM registration.

## 6. SQL IaaS Agent extension và quản lý SQL VM

**SQL IaaS Agent extension** hỗ trợ một số khả năng quản trị SQL Server trên Azure VM như đăng ký SQL VM, inventory/trạng thái, license management và những tính năng quản lý tự động theo OS/SQL version và phương thức triển khai.

Các khả năng có thể bao gồm:

- Khai báo/chuyển đổi license type trong giới hạn đủ điều kiện.
- Cấu hình một số tính năng storage/SQL VM management khi được hỗ trợ.
- Automated backup hoặc patching trong những cấu hình tương thích.
- Tích hợp hiển thị metadata SQL Server trong Azure Portal.
- Hỗ trợ một số tác vụ quản trị SQL Server VM chuyên biệt.

**Không mặc định mọi phiên bản SQL Server, OS và extension mode đều hỗ trợ toàn bộ tính năng.** Automated backup trong SQL IaaS extension khác một backup policy do Azure Backup for SQL Server in Azure VM quản lý; lựa chọn cơ chế rõ ràng, tránh hai hệ thống backup chồng lịch, tranh băng thông hoặc tạo chuỗi backup không như dự định.

### Kiểm tra registration

Các lệnh đọc ví dụ, giả sử resource đã tồn tại và Azure CLI có nhóm lệnh SQL VM thích hợp:

~~~bash
RG="rg-sql-lab"
VM="vm-sql-lab-01"

az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --query "{id:id,name:name,location:location,vmSize:hardwareProfile.vmSize}" \
  --output json

az sql vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --output json
~~~

Nếu lệnh thứ hai không tìm thấy, **chưa đủ cơ sở** kết luận SQL Server không cài trên VM: có thể VM chưa đăng ký SQL VM resource, CLI extension chưa sẵn sàng hoặc tài khoản thiếu quyền. Kiểm tra theo quy trình quản trị, không tạo resource mới khi chưa xác định licensing và quyền.

## 7. SQL Server licensing trên Azure VM

SQL Server license là một phần lớn trong TCO. Hai hướng thường gặp:

| Hướng | Ý nghĩa | Điều cần kiểm tra |
|---|---|---|
| **Pay-as-you-go (PAYG)** | Chi phí SQL Server license có thể được tính qua mô hình image/SQL VM phù hợp | Edition, license meter, số vCPU, VM size, cấu hình resource |
| **Azure Hybrid Benefit (AHB)** | Dùng giấy phép SQL Server đủ điều kiện theo chính sách Microsoft để giảm chi phí license trên Azure | Entitlement, Software Assurance/subscription, quyền sử dụng, core count và compliance |

Một số mô hình license khác có thể tồn tại theo chương trình hợp đồng và điều kiện cụ thể. **Không tự chuyển licenseType sang AHB khi doanh nghiệp chưa có quyền sử dụng hợp lệ**, và không giả định chỉ nhìn một tag trên VM là đã giải quyết toàn bộ compliance.

Chi phí Windows Server licensing, SQL Server licensing, VM compute và managed disks có thể được thể hiện theo mô hình billing khác nhau; dự toán cần kiểm tra giá thực tế theo region, OS, VM SKU và license.

### Tối ưu license và compute

- Chọn edition vừa đủ cho nhu cầu HA, performance và tính năng.
- Đánh giá VM có số vCPU/RAM đúng tải, không overprovision vCPU chỉ để tăng bộ nhớ nếu có SKU phù hợp hơn.
- Với SQL Server license tính theo cores và mô hình VM cụ thể, kiểm tra minimum/core rules cùng chính sách hợp đồng trước khi đổi VM size.
- Kiểm tra quyền với HA passive replicas, disaster recovery replicas và trạng thái standby; các quyền miễn phí/giảm phí **có điều kiện**, không tự áp dụng cho mọi topology.
- Xem tổng chi phí trước khi chọn Always On topology nhiều node.

## 8. Chọn VM SKU: CPU, memory và network

### CPU

SQL Server thường chịu tải từ query execution, parallelism, compression, index maintenance và encryption. CPU vừa thiếu làm tăng latency, vừa dư làm tăng chi phí compute/license.

Đánh giá:

- Peak CPU và thời gian CPU đạt ngưỡng cao.
- Số query concurrency, mức parallelism, waits.
- Các job ETL, maintenance và batch chạy cùng giờ giao dịch.
- VM series và giới hạn disk/network throughput của SKU.
- VM SKU có hỗ trợ accelerated networking, zone, Ultra/Premium SSD v2 hay không.

### Memory

SQL Server dùng RAM cho buffer pool, plan cache và các thành phần engine. Chọn VM theo **working set của database**, không chỉ kích thước toàn bộ data files.

Phải dành RAM cho:

- Guest OS và các agents: Defender, backup, Azure Monitor.
- SQL Server non-buffer-pool memory, CLR/linked servers nếu có.
- Các dịch vụ phụ hoặc driver chạy cùng VM.
- Peak queries và maintenance jobs.

**max server memory (MB)** giúp giới hạn một phần lớn bộ nhớ SQL Server, nhưng không thay thế giám sát tổng memory. Không đặt SQL Server chiếm toàn bộ VM RAM; cần headroom để OS và agent không bị paging/OOM.

### Network

SQL Server có thể cần nhiều băng thông cho AG replication, backup to URL, client queries và ETL. Kiểm tra **network bandwidth của VM SKU**, latency giữa các zone/region và chính sách egress. Một SQL VM dùng disk rất nhanh nhưng VM network/storage throughput cap thấp vẫn có thể bị nghẽn.

## 9. Thiết kế managed disks cho SQL Server

Một cơ sở dữ liệu thường có các nhóm I/O khác nhau:

| Thành phần | Mẫu I/O thường gặp | Gợi ý thiết kế |
|---|---|---|
| **Data files (.mdf/.ndf)** | Đọc ngẫu nhiên, ghi theo checkpoint/page operations | Disk/pool cho latency thấp và IOPS phù hợp |
| **Transaction log (.ldf)** | Ghi tuần tự, cực kỳ nhạy với latency | Disk riêng hoặc bố trí ưu tiên write latency; host caching theo khuyến nghị |
| **tempdb** | I/O tạm, sort/hash/version store | Storage nhanh; có thể cân nhắc local temporary disk nếu SKU hỗ trợ và quy trình tạo lại an toàn |
| **Backup files** | Đọc/ghi tuần tự khối lượng lớn | Blob/backup service với bandwidth, retention và bảo mật phù hợp |
| **OS disk** | OS, agent và file hệ thống | Tránh đặt data/log production chung OS disk vì khó dự báo contention |

### Disk SKU và thông lượng

Các lớp storage có thể gồm Standard SSD, Premium SSD, Premium SSD v2, Ultra Disk hoặc tùy chọn phù hợp. **Khả năng cung cấp IOPS/throughput, caching, zone support, snapshot, resize và hỗ trợ VM size khác nhau theo SKU/region**.

Không chọn Ultra chỉ vì tên "cao cấp". Cần đo **IOPS, MB/s, độ trễ** của workload và so sánh với khả năng của từng disk/VM SKU.

### Bốn giới hạn song song

Tốc độ I/O thực không vượt được giới hạn thấp nhất trong đường đi:

~~~text
Application/SQL workload
    -> SQL engine + file layout
    -> Guest filesystem / storage stack
    -> Azure managed disk IOPS + throughput
    -> VM-level disk IOPS + throughput caps
~~~

Nếu disk provision 40.000 IOPS nhưng VM chỉ cung cấp 20.000 IOPS theo loại workload, hiệu năng thực có thể bị giới hạn bởi VM. Nếu request size là 64 KiB, 10.000 IOPS tương ứng xấp xỉ 625 MiB/s về mặt lý thuyết; throughput cap thấp hơn có thể giới hạn kết quả.

### Host caching

Với cấu hình disk/VM hỗ trợ và được SQL Server best practices khuyến nghị:

- Data disk đôi khi dùng **ReadOnly host caching** nếu workload phù hợp.
- Transaction log thường **None** (không host caching) để tránh hành vi không phù hợp đối với ghi log.
- **Premium SSD v2/Ultra Disk không có cùng hỗ trợ host caching như mọi Premium SSD thông thường**; kiểm tra giới hạn SKU.
- Không bật caching theo thói quen trên mọi disk, đặc biệt với shared disks/HA.

Thay disk caching hoặc storage layout production có thể đòi reboot/downtime; phải kiểm thử và thực hiện theo change window.

## 10. Data/log separation, file layout và tempdb

### Tại sao tách data và log?

Transaction log được ghi theo thứ tự phục vụ durability/recovery; data files có thể tạo nhiều I/O ngẫu nhiên. Khi cùng chia một disk, burst đọc dữ liệu hoặc index maintenance có thể ảnh hưởng latency ghi log.

Phương án phổ biến:

~~~text
C:  OS, SQL binaries
F:  SQL data files
G:  SQL transaction log files
T:  tempdb (disk phù hợp, có thể temporary local)
Backup -> Azure Backup / Blob theo thiết kế
~~~

Các ký tự ổ đĩa chỉ để minh họa, không phải quy ước bắt buộc.

### Nhiều disk và Storage Spaces

Khi một managed disk không đủ IOPS/throughput, có thể ghép nhiều disk thành storage pool/volume theo cấu hình Windows hoặc Linux hỗ trợ. Việc striping cần hiểu:

- Số disk, size, performance tier và VM-level limits.
- Stripe/interleave và filesystem allocation size phù hợp workload.
- Khả năng snapshot/backup/recovery toàn bộ volume.
- Thứ tự mount/khôi phục disk khi failover hoặc restore.
- Shared disk compatibility nếu dùng FCI.

**Không tự tạo striping nhiều disk chỉ vì muốn có nhiều drive letters**. Dùng kiểm thử I/O thực, theo dõi latency và quy trình khôi phục.

### tempdb trên local temporary storage

Một số Azure VM SKU có **temporary/local SSD hoặc NVMe** tốc độ cao. tempdb có thể được cấu hình trên đó ở môi trường được hỗ trợ vì dữ liệu tempdb được tạo lại khi SQL Server khởi động.

Nhưng local temporary disk **không bền vững** qua các sự kiện như deallocate/redeploy/host maintenance. Do đó:

1. Không đặt **user database data/log files hoặc backups duy nhất** trên temporary disk.
2. Phải đảm bảo directory, ACL và mount path của tempdb được tạo lại trước khi SQL Server start.
3. Kiểm tra SKU có thực sự cung cấp temporary disk và dung lượng phù hợp.
4. Kiểm tra điều kiện upgrade/stop/start để SQL Server không lỗi khởi động khi đường dẫn tempdb biến mất.
5. Nếu workload/version/VM SKU không hỗ trợ, dùng managed disk bền vững phù hợp.

### tempdb tuning

Số tempdb data files, kích thước ban đầu và autogrowth phụ thuộc concurrency/version/contension. Không áp dụng máy móc "mỗi CPU một tempdb file" cho VM hàng chục core. Đo PAGELATCH/metadata contention và tuân theo hướng dẫn version SQL Server tương ứng.

## 11. Thiết kế VNet, NSG và DNS

SQL Server trên VM thường nên dùng **private IP trong Azure VNet** và chỉ cho những ứng dụng/nhóm quản trị được phép kết nối.

~~~mermaid
flowchart LR
  APP["Ứng dụng - subnet-app"] --> NSG["NSG / Firewall policy"]
  NSG --> SQL["SQL VM private IP: SQL TCP endpoint"]
  SQL --> DISK["Managed disks"]
  OPS["VPN / ExpressRoute / Bastion"] --> ADMIN["Quản trị VM"]
  ADMIN --> SQL
  SQL --> BK["Backup / Azure services theo outbound rules"]
~~~

### Không mở SQL port ra Internet

Port TCP **1433** thường được dùng cho default instance **khi đã cấu hình lắng nghe trên port đó**. Named instance có thể dùng port động hoặc port khác; SQL Browser/UDP 1434 có vai trò riêng. Không giả định mọi SQL VM lắng nghe TCP 1433.

Khuyến nghị:

- Không gắn public IP trực tiếp cho SQL VM nếu không có nhu cầu đặc biệt được phê duyệt.
- NSG chỉ cho phép **application subnet, jump subnet hoặc nguồn cụ thể** truy cập đúng port SQL.
- Không dùng inbound rule `0.0.0.0/0:1433`.
- Quản trị Windows qua **Azure Bastion**, VPN/ExpressRoute hoặc đường quản trị được cho phép; hạn chế RDP 3389.
- Dùng Azure Firewall/NVA khi cần inspection/central egress và logging.
- Kiểm tra guest OS firewall, không chỉ NSG.
- Nếu có AG listener/FCI, client dùng **listener DNS name**, không ghim node private IP.

### Không nhầm Private Endpoint của Azure SQL Database

SQL Server cài trên VM có **NIC/private IP của VM** hoặc listener/ILB theo topology. Nó **không tự sử dụng Azure SQL Database Private Endpoint** chỉ vì engine cùng là SQL. Private Endpoint có thể dùng cho Storage, Key Vault và những dịch vụ Azure PaaS hỗ trợ mà SQL VM gọi tới.

### DNS và connection strings

Kết nối ứng dụng nên tham chiếu DNS name ổn định:

~~~text
sql-orders.internal.example:1433
~~~

Nếu AG multi-subnet, JDBC/driver hỗ trợ và topology có thể cần tùy chọn như `multiSubnetFailover=true` để tăng khả năng kết nối khi failover. Kiểm tra listener, DNS TTL, IP, driver version và môi trường mạng thực. Không tự thêm multiSubnetFailover nếu ứng dụng không dùng multi-subnet listener.

## 12. Authentication, authorization và TLS

### Các cách xác thực

Tùy phiên bản SQL Server, Windows/Linux và môi trường doanh nghiệp:

- **Windows/Active Directory authentication** qua domain và service accounts phù hợp.
- **SQL Server authentication** với login/password theo chính sách và rotation.
- **Microsoft Entra authentication** với SQL Server trên VM trong một số phiên bản/cấu hình được hỗ trợ; không mặc định mọi bản SQL Server đều dùng Entra giống Azure SQL Database.

**Managed identity trên VM** giúp ứng dụng hoặc tác vụ tương tác với dịch vụ Azure hỗ trợ Entra, nhưng **không tự trở thành login SQL Server hợp lệ** ở mọi bản SQL Server. SQL database authentication vẫn phải thiết kế và cấu hình đúng.

### Least privilege

- Tách tài khoản DBA, SQL Server Agent, ứng dụng và backup.
- Ứng dụng chỉ được quyền cần thiết ở database/schema.
- Tránh dùng `sa`, `sysadmin` hoặc `db_owner` cho connection string của API.
- Giữ bí mật trong Key Vault hoặc nguồn secrets được phê duyệt; tránh trong source code, image, Terraform state/log hoặc file cấu hình không được bảo vệ.
- Ghi audit những thay đổi quyền, login bất thường, schema và dữ liệu nhạy cảm.

### TLS khi kết nối

Dùng TLS với certificate hợp lệ và FQDN phù hợp. Ví dụ JDBC URL khi SQL lắng nghe cổng tĩnh và có certificate tin cậy:

~~~properties
spring.datasource.url=jdbc:sqlserver://sql-orders.internal.example:1433;databaseName=Orders;encrypt=true;trustServerCertificate=false;loginTimeout=30
~~~

Đây là cấu hình đường dẫn **không chứa mật khẩu**; cấu hình username/password hoặc mechanism xác thực riêng theo chính sách ứng dụng. `trustServerCertificate=false` yêu cầu kiểm tra chứng chỉ; đừng chuyển sang `true` chỉ để bỏ qua lỗi certificate production. Với driver mới, cách đặt `encrypt` và hostname validation có thể khác theo version; kiểm thử thực tế.

## 13. Encryption at rest và quản lý khóa

Phân biệt ba lớp:

| Lớp | Công dụng | Điều cần quản lý |
|---|---|---|
| Azure managed disk encryption | Bảo vệ dữ liệu ở lớp lưu trữ Azure theo cơ chế nền tảng | Platform-managed keys hoặc customer-managed keys tùy nhu cầu/tính năng |
| SQL Server TDE | Mã hóa database files và transaction logs ở lớp SQL | Certificate/asymmetric key, backup key, rotate và restore |
| TLS | Mã hóa dữ liệu khi client kết nối SQL Server | Certificate, trust chain, hostname và expiry |

**Mã hóa đĩa Azure không thay thế TDE nếu tổ chức cần SQL-level encryption**; ngược lại, TDE không tự kiểm soát việc ai được kết nối query dữ liệu đã được giải mã trong engine.

### TDE backup/restore

Một cơ sở dữ liệu có TDE cần **certificate/key và private key phù hợp** để restore ở instance khác, theo cách cấu hình TDE. Sao lưu các khóa này ở nơi an toàn theo quy trình, tách khỏi database backup và kiểm thử phục hồi. Không chuyển backup TDE sang môi trường khác rồi mới phát hiện thiếu certificate.

### Key Vault

Azure Key Vault có thể được dùng trong giải pháp quản lý secrets/keys khi cấu hình, phiên bản và integration phù hợp. Không ghi secret hoặc key trực tiếp vào script SQL IaC. Kiểm soát RBAC, private network/DNS, audit và kế hoạch key rotation.

## 14. Backup không phải là snapshot đơn thuần

Backup phải giúp khôi phục **database có tính nhất quán**, không chỉ sao chép một số block disk.

| Cơ chế | Dùng cho | Giới hạn cần hiểu |
|---|---|---|
| **Native SQL BACKUP DATABASE/LOG** | Full, differential, log backups theo recovery model | Khách hàng lên lịch, lưu giữ, checksum và restore testing |
| **Azure Backup for SQL Server in Azure VM** | Workload-aware backup/restore theo chính sách dịch vụ, cấu hình hỗ trợ | Cần đăng ký/bảo vệ instance, policy, vault, quyền và xác minh khôi phục |
| **SQL VM automated backup** | Khả năng qua SQL IaaS Agent extension trong các trường hợp được hỗ trợ | Không đồng nghĩa mọi loại SQL/OS đều có; tránh chồng backup policy |
| **Managed disk snapshots** | Bảo vệ cấp disk, một số mục tiêu VM/storage | Không mặc nhiên là SQL-consistent backup/point-in-time restore |
| **Availability Group replica** | High availability/disaster recovery replica | **Không phải backup**; lỗi xóa dữ liệu có thể replicate |

Một disk snapshot tạo riêng lẻ lúc SQL Server đang ghi **không đảm bảo consistency của nhiều disk/data/log**. Muốn dùng VM snapshot/backup cho SQL, phải có cơ chế app-consistent/VSS hoặc giải pháp có bảo đảm phù hợp và được kiểm thử. **Không lấy snapshot thay toàn bộ log backup chain** khi yêu cầu point-in-time recovery.

## 15. Recovery model, log backup và RPO

SQL Server recovery model ảnh hưởng chiến lược khôi phục.

| Recovery model | Mục đích | Giới hạn |
|---|---|---|
| **FULL** | Hỗ trợ log backup và point-in-time restore khi chuỗi backup hợp lệ | Phải **thực sự chạy log backups**; chỉ đổi model sang FULL không tự tạo backup |
| **SIMPLE** | Tái sử dụng log theo cơ chế engine; thích hợp khi không cần log backup/PITR theo mô hình đó | Không hỗ trợ chuỗi transaction log backups để PITR như FULL |
| **BULK_LOGGED** | Có thể giảm mức log cho một số bulk operations | Có ràng buộc PITR với log backup chứa minimally logged operations |

### Full, differential và transaction log

Một chính sách minh họa:

~~~text
Full backup:          Chủ nhật 01:00
Differential backup:  Mỗi ngày 01:00
Log backup:           Mỗi 10 phút
Retention:            Theo RPO/RTO, compliance, chi phí
Restore drill:        Theo lịch đã phê duyệt
~~~

Nếu mất database lúc 14:07 và log backup gần nhất là 14:00, khi không có tail-log backup khả dụng, điểm khôi phục mới nhất có thể là 14:00; RPO mất dữ liệu **có thể gần 7 phút hoặc lớn hơn**, tùy backup thành công và tail-log availability. Đây là ví dụ, không phải bảo đảm RPO 10 phút trong mọi lỗi.

**Log backups phải liên tục và recoverable.** Bất kỳ gap, file bị xóa, credential hết hạn hoặc storage không truy cập được có thể làm point-in-time restore thất bại.

### RPO và RTO khác nhau

- **RPO:** mức mất dữ liệu tối đa chấp nhận được so với sự cố.
- **RTO:** thời gian tối đa từ lúc gián đoạn tới khi dịch vụ được phục hồi.

Backup mỗi 10 phút có thể đáp ứng một phần RPO nhưng không đảm bảo RTO 10 phút nếu restore hàng TB mất hàng giờ. Cần đo **thời gian restore toàn chuỗi backup, tạo VM mới, DNS cutover và ứng dụng reconnect**.

## 16. Ví dụ T-SQL cho backup/restore — minh họa có kiểm soát

Xem database recovery model:

~~~sql
SELECT name, recovery_model_desc, state_desc, compatibility_level
FROM sys.databases
WHERE name NOT IN ('master', 'model', 'msdb', 'tempdb')
ORDER BY name;
~~~

Ví dụ cú pháp **native backup to URL** cho một database lab đã có credential/authorization đúng để SQL Server ghi vào Blob:

~~~sql
BACKUP DATABASE [OrdersLab]
TO URL = 'https://<STORAGE_ACCOUNT>.blob.core.windows.net/sql-backups/OrdersLab_full_001.bak'
WITH COPY_ONLY, COMPRESSION, CHECKSUM, STATS = 10;
~~~

Đoạn lệnh **không tự chạy được** nếu chưa thay placeholder, cấu hình credential/SAS hoặc phương pháp authentication được SQL Server version hỗ trợ, cấp quyền SQL và mạng tới Blob. **COPY_ONLY** giúp không ảnh hưởng differential base trong một số quy trình full backup; policy production phải xác định có dùng hay không.

Kiểm tra cấu trúc của bản backup là một bước:

~~~sql
RESTORE VERIFYONLY
FROM URL = 'https://<STORAGE_ACCOUNT>.blob.core.windows.net/sql-backups/OrdersLab_full_001.bak'
WITH CHECKSUM;
~~~

**RESTORE VERIFYONLY không bằng một restore drill hoàn chỉnh.** Cần định kỳ restore vào instance độc lập, kiểm tra database online, consistency và thử truy vấn nghiệp vụ. Với TDE, phải có khóa/certificate tương ứng. Không restore đè database production khi chỉ muốn thử backup.

### Retention và immutability

Bản backup phục vụ ransomware recovery cần quyền độc lập, retention và khả năng chống xóa/sửa theo chính sách. Cân nhắc vault protections, soft delete, immutability hoặc storage controls được dịch vụ hỗ trợ; kiểm tra chi phí và thời hạn pháp lý. Không giữ bản backup duy nhất trên cùng VM/data disk với database.

## 17. High availability: Availability Zones không đủ nếu chỉ một VM

Các Availability Zones giúp phân tán compute/storage theo vùng lỗi vật lý độc lập trong một Azure region được hỗ trợ. **Một SQL VM nằm trong một zone** vẫn là điểm lỗi đơn nếu không có replica hoặc cơ chế failover.

### Always On Availability Groups (AG)

AG thường gồm:

- **Primary replica:** nhận read/write cho database trong availability group.
- **Secondary replicas:** nhận dữ liệu đồng bộ hoặc bất đồng bộ theo cấu hình, có thể dùng cho read-only/backup trong điều kiện phù hợp.
- **Windows Server Failover Cluster (WSFC)** cho nhiều cấu hình AG trên Windows.
- **Listener:** tên kết nối logic giúp ứng dụng trỏ tới primary phù hợp.
- **Quorum/witness:** cơ chế tránh split-brain theo cluster topology.

~~~mermaid
flowchart LR
  APP["Ứng dụng qua listener DNS"] --> L["AG listener"]
  L --> P["SQL VM A - Zone 1 - Primary"]
  P -->|Synchronous commit (khi phù hợp)| S["SQL VM B - Zone 2 - Secondary"]
  P -->|Async commit cho DR (ví dụ)| DR["SQL VM C - Region khác"]
  W["Cluster quorum / witness"] -.-> P
  W -.-> S
~~~

Sơ đồ là thiết kế khái niệm; topology thật cần xác minh hỗ trợ zone/region, edition, networking, endpoint, WSFC, listener, quorum và failover behavior.

### Đồng bộ và bất đồng bộ

- **Synchronous commit** có thể giảm mất dữ liệu khi failover trong điều kiện replicas khỏe và cấu hình phù hợp, nhưng có **latency trade-off** qua zone.
- **Asynchronous commit** giảm phụ thuộc latency tại thời điểm commit, phù hợp một số DR topology, nhưng có **khả năng mất các transactions chưa gửi/redo** khi failover.
- **Automatic failover** chỉ được hỗ trợ trong những tổ hợp availability mode/failover mode/health/quorum phù hợp; không mặc định mọi secondary đều tự động nhận quyền primary.

Ngay cả AG khỏe không thay database backup: lỗi dữ liệu do application, lệnh DELETE nhầm hoặc ransomware có thể replicate.

## 18. Failover Cluster Instance (FCI) và storage chia sẻ

**SQL Server Failover Cluster Instance (FCI)** là phương án HA ở cấp SQL Server instance thay vì chọn nhóm user databases như AG. Một FCI điển hình có:

- Nhiều node Windows/SQL Server theo cấu hình hỗ trợ.
- Failover cluster resources.
- Shared storage hoặc giải pháp storage tương đương được SQL Server/Windows/Azure hỗ trợ.
- Tên/endpoint SQL instance ổn định.
- Quy tắc quorum, witness và failover.

Trên Azure có các cấu hình FCI dùng **Azure shared disks hoặc giải pháp được hỗ trợ khác**, nhưng không phải mọi managed disk SKU, zone/region topology và clustering mode đều tương thích. Cần kiểm tra **danh sách chính thức về SQL Server FCI trên Azure VMs, disk type, host caching, multi-writer support và witness** trước khi thiết kế.

### AG hay FCI?

| Tiêu chí | Always On AG | FCI |
|---|---|---|
| Phạm vi HA | Nhóm database được tham gia AG | SQL instance theo thiết kế FCI |
| Cơ chế dữ liệu | Các replicas có bản sao database | Cần shared storage/clustered storage phù hợp |
| Readable secondary | Có ở một số edition/config | Không có bản secondary database độc lập theo FCI truyền thống |
| Storage failure considerations | Mỗi replica có storage riêng | Phải đánh giá shared storage failure domain |
| Cấu hình | AG endpoints, listener, replicas, quorum | Cluster disks/resources, instance failover, quorum |
| Migration/operations | Logins/jobs ngoài AG có thể cần đồng bộ | Instance-level failover nhưng vẫn cần kiểm tra dependencies |

Không chọn AG hay FCI chỉ theo số VM. Cần kiểm tra feature edition/version, RPO/RTO, DBA runbooks, licensing và ứng dụng có hỗ trợ reconnect sau failover không.

## 19. Quorum, witness và listener trong Azure

### Quorum

WSFC cần quorum để quyết định cluster còn quyền quản lý resources và tránh split-brain. Với hai SQL nodes, thường phải thiết kế **witness** phù hợp (ví dụ cloud witness trong điều kiện hỗ trợ), quản trị identity/secret/network và failure domains.

Một witness hỏng không nhất thiết làm SQL database dừng ngay, nhưng có thể làm mất khả năng failover khi xảy ra lỗi kế tiếp. Kiểm tra quorum health như một tín hiệu vận hành, không chỉ kiểm tra SQL Server service chạy.

### Listener

AG listener có thể dùng private virtual IP và cấu hình **Azure Internal Load Balancer** trong một số topology, hoặc những phương án listener DNS/DNN phù hợp SQL Server/Windows và môi trường hỗ trợ. Cấu hình khác nhau giữa single-subnet, multi-subnet, AG/FCI và SQL versions.

Nếu dùng Internal Load Balancer:

- Đảm bảo health probe, backend pool, NSG và port theo hướng dẫn cho topology.
- Không dùng public LB để expose SQL Server nếu không có thiết kế đặc biệt được phê duyệt.
- Kiểm tra listener IP không xung đột trong VNet.
- Test failover: kết nối cũ đứt, app pool phải reconnect; việc TCP session được giữ nguyên không được bảo đảm.

Nếu ứng dụng dùng JDBC:

~~~properties
jdbc:sqlserver://sql-ag-listener.internal.example:1433;databaseName=Orders;encrypt=true;trustServerCertificate=false;multiSubnetFailover=true;loginTimeout=30
~~~

Đây là ví dụ **khi listener/driver multi-subnet hỗ trợ và được cấu hình đúng**. Cần kiểm thử chính xác SQL Server JDBC driver version và đặt connection pool validation/retry phù hợp, thay vì giả định một property tự giải quyết toàn bộ failover.

## 20. Disaster recovery: lỗi region khác lỗi node

HA trong một region giúp giảm downtime khi VM hoặc zone có sự cố nhưng chưa chắc đáp ứng mục tiêu khi **cả region** mất dịch vụ.

Phương án DR cần chọn theo yêu cầu dữ liệu và ngân sách:

- AG asynchronous replica ở region thứ hai khi topology/edition cho phép.
- Log shipping hoặc backup/restore sang nơi khác trong mô hình phù hợp.
- Cross-region backup replication theo khả năng của Azure Backup/storage policy.
- Replication hoặc migration công cụ chuyên biệt đã được kiểm thử.
- Tầng application/DNS traffic cutover và connection strings ở region dự phòng.

### RPO/RTO phải đo

| Tình huống | HA/DR kỳ vọng | Rủi ro |
|---|---|---|
| SQL Server process restart | Tự hồi phục hoặc failover nếu có HA | Connection reset, in-flight transaction |
| VM/node failure | AG/FCI hoặc restore | Failover delay, quorum/storage |
| Availability Zone outage | Replica sang zone khác | Capacity, cross-zone sync latency |
| Region outage | DR region | Async data loss, DNS/app cutover |
| Database corruption/ransomware | Backup/restore an toàn | Lỗi có thể replicate tới secondary |
| Human error: DROP/DELETE | Point-in-time restore theo backup chain | Recovery point, restore time, dependencies |

**Failover drill** không chỉ là đổi primary: phải xác nhận app endpoints, DNS, TLS, logins, Agent jobs, linked servers, backup policy, data consistency và khả năng quay về sau failover (failback). Lập runbook và quyền khẩn cấp trước khi xảy ra sự cố.

## 21. Performance tuning: đo SQL Server trước khi tăng VM

Khi API chậm, phản ứng sai phổ biến là **nâng VM size ngay lập tức**. Thay vào đó, cần phân loại bottleneck:

- CPU-bound: query plans, excessive parallelism, scalar computations.
- I/O-bound: data disk read/write latency, log write stalls, tempdb contention.
- Memory pressure: buffer churn, paging, excessive memory grants.
- Locking/blocking: transaction dài, index phù hợp hay isolation level.
- Network/connection: DNS/TLS, connection pool exhaustion, packet loss.
- Application: N+1 queries, thiếu batching, retry loops hoặc lỗi ORM.
- HA/replication: synchronous commit waits, secondary lag.

### Indexes và Query Store

**Query Store** cho phép phân tích lịch sử query plans/runtime khi được cấu hình và version hỗ trợ. Có thể dùng nó để xác định regression sau deploy, so sánh execution plans và đánh giá lựa chọn tuning. Đừng tự tạo hàng loạt indexes chỉ vì một query chậm; cần xem write overhead, storage cost và plan stability.

### max server memory và MAXDOP

`max server memory` nên được chọn theo RAM thực, phần còn lại cần cho OS/agents và workloads khác. `MAXDOP`, cost threshold for parallelism và tempdb cấu hình theo SQL version, NUMA, core count và pattern queries; không lấy một giá trị "tối ưu" cố định cho mọi VM.

## 22. T-SQL: kiểm tra phiên bản, database và file layout

Chạy trong SQL Server Management Studio, Azure Data Studio (nếu công cụ còn được hỗ trợ ở môi trường) hoặc client SQL được phê duyệt, bằng tài khoản có quyền cần thiết.

### Phiên bản và edition

~~~sql
SELECT
    @@SERVERNAME AS SqlInstance,
    SERVERPROPERTY('ProductVersion') AS ProductVersion,
    SERVERPROPERTY('ProductLevel') AS ProductLevel,
    SERVERPROPERTY('Edition') AS Edition,
    SERVERPROPERTY('EngineEdition') AS EngineEdition;
~~~

Kết quả giúp đối chiếu patch level, edition và những tính năng được hỗ trợ. Edition name không tự chứng minh license entitlement đã đúng.

### Database health

~~~sql
SELECT
    name,
    state_desc,
    recovery_model_desc,
    compatibility_level,
    is_read_only
FROM sys.databases
ORDER BY name;
~~~

### Data/log files

~~~sql
SELECT
    DB_NAME(database_id) AS DatabaseName,
    name AS LogicalFileName,
    type_desc,
    physical_name,
    size * 8.0 / 1024 AS SizeMiB,
    growth,
    is_percent_growth
FROM sys.master_files
ORDER BY database_id, file_id;
~~~

Giá trị `size` là các trang 8 KiB; `growth` có ý nghĩa khác nhau tùy `is_percent_growth`. Các drive letters/paths giúp kiểm tra data/log có tách như thiết kế không. Thay đổi autogrowth production phải xem dung lượng thực và policy trước.

### I/O latency từ DMV

~~~sql
SELECT
    DB_NAME(v.database_id) AS DatabaseName,
    mf.name AS LogicalFileName,
    mf.type_desc AS FileType,
    v.num_of_reads,
    v.num_of_writes,
    CASE WHEN v.num_of_reads > 0
         THEN 1.0 * v.io_stall_read_ms / v.num_of_reads END AS AvgReadMs,
    CASE WHEN v.num_of_writes > 0
         THEN 1.0 * v.io_stall_write_ms / v.num_of_writes END AS AvgWriteMs
FROM sys.dm_io_virtual_file_stats(NULL, NULL) AS v
JOIN sys.master_files AS mf
  ON mf.database_id = v.database_id
 AND mf.file_id = v.file_id
ORDER BY DatabaseName, LogicalFileName;
~~~

**DMV là cumulative counters** từ khi SQL Server/đối tượng được khởi tạo theo semantics của DMV; không nên nhìn một giá trị lifetime rồi kết luận latency trong 5 phút vừa qua. Lấy hai mẫu và tính chênh lệch trong cửa sổ phù hợp. Các DMV có thể yêu cầu quyền server-state/performance-state thay đổi theo phiên bản SQL Server.

## 23. T-SQL: wait statistics và blocking

### Top waits

~~~sql
SELECT TOP (15)
    wait_type,
    waiting_tasks_count,
    wait_time_ms,
    signal_wait_time_ms
FROM sys.dm_os_wait_stats
ORDER BY wait_time_ms DESC;
~~~

Đây chỉ là danh sách **cumulative wait time**. Một số waits là bình thường/background và không trực tiếp chỉ ra bottleneck. Cần phân tích wait categories, query plans, file latency, time window và số transaction trước khi tuning. Không "fix" một wait chỉ vì nó đứng đầu danh sách.

### Requests đang chạy

~~~sql
SELECT
    session_id,
    status,
    command,
    blocking_session_id,
    wait_type,
    wait_time,
    total_elapsed_time,
    cpu_time
FROM sys.dm_exec_requests
WHERE session_id <> @@SPID
ORDER BY total_elapsed_time DESC;
~~~

`blocking_session_id` giúp bắt đầu điều tra lock contention; không tự động `KILL` session production chỉ vì một transaction chạy lâu. Xác minh owner, thời gian commit, mức lock và hậu quả rollback.

### Tempdb, transaction log và free space

Ngoài DMV, cần xem log reuse wait, kích thước log, SQL error log và PerfMon counters theo version. Các cảnh báo quan trọng:

- Transaction log gần đầy / backup chain lỗi.
- Storage volume sắp hết dung lượng.
- Tempdb autogrowth liên tục.
- Deadlocks hoặc long blocking.
- SQL Agent backup jobs thất bại.
- AG replication queue/send/redo lag cao.
- Database corruption/checkdb báo lỗi.

## 24. Giám sát bằng Azure Monitor và SQL telemetry

### Mức Azure VM

Azure Monitor có thể thu thập những metric nền tảng như:

- CPU Percentage.
- VM disk read/write operations và bytes theo khả năng metric.
- Network in/out.
- VM availability/health và sự kiện hạ tầng được công bố.

Metric này hữu ích nhưng **không biết một SQL query có bị deadlock hay không**. Bổ sung guest OS counters, SQL DMVs, Query Store, SQL Server error log và các diagnostic/monitoring integrations phù hợp.

### Mức guest OS

Dùng Azure Monitor Agent (AMA) cùng Data Collection Rules (DCR) hoặc pipeline được phép để thu Windows Event Logs, PerfMon counters hay Linux syslog/performance theo yêu cầu.

Các chỉ số thường cần:

| Tín hiệu | Mục tiêu |
|---|---|
| CPU và runnable tasks | Có thiếu compute không? |
| Available memory và paging | OS có chịu áp lực memory không? |
| Disk avg sec/read/write, queue length | I/O latency có vượt baseline không? |
| SQL batch requests/sec | Workload tăng/giảm? |
| SQL user connections | Connection pool có bất thường? |
| Page life expectancy / buffer metrics | Có memory pressure không? Cần kết hợp nhiều tín hiệu |
| Log flush waits/latency | Log disk có giới hạn commit? |
| Backup success + last log backup age | Recovery objective có được bảo vệ? |
| AG health/send/redo queue | Replica có theo kịp và failover được? |

Tên counter, phương pháp ingest và khả năng hiển thị khác nhau theo Windows/SQL versions và agent. Không tạo alert dựa vào counter không tồn tại trong workspace.

### Mức ứng dụng

Application Insights/OpenTelemetry trong Java/.NET giúp nối **API latency** tới SQL dependency. Ví dụ trace:

~~~text
POST /checkout (3.2s)
  -> SQL query CreateOrder (2.7s)
     -> wait: WRITELOG / lock? cần xác minh bằng SQL telemetry
  -> HTTP return (0.2s)
~~~

Trace dependency lâu là điểm khởi đầu, không tự xác định nguyên nhân engine. Cần đối chiếu SQL DMVs, Query Store, I/O latency và change timeline.

## 25. Azure CLI: kiểm tra VM, disks và platform metrics

Lệnh chỉ đọc dưới đây phù hợp Azure Cloud Shell Bash khi người dùng có quyền xem các tài nguyên. Thay các giá trị placeholder trước khi áp dụng:

~~~bash
az account show \
  --query "{subscription:name,id:id,tenant:tenantId}" \
  --output table

RG="rg-sql-lab"
VM="vm-sql-lab-01"

VM_ID=$(az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --query id --output tsv)

az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --query "{name:name,size:hardwareProfile.vmSize,location:location,storage:storageProfile}" \
  --output json
~~~

Xem các data disk IDs/LUNs:

~~~bash
az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --query "storageProfile.dataDisks[].{name:name,lun:lun,diskId:managedDisk.id}" \
  --output table
~~~

Xem platform metric CPU:

~~~bash
az monitor metrics list \
  --resource "$VM_ID" \
  --metric "Percentage CPU" \
  --interval PT5M \
  --output json
~~~

Nếu lệnh metric không có dữ liệu, kiểm tra thời gian query, quyền, VM state, metric definitions và resource ID. Không tự suy ra CPU=0 khi không có telemetry.

Xem diagnostic settings:

~~~bash
az monitor diagnostic-settings list \
  --resource "$VM_ID" \
  --output json
~~~

**Diagnostic settings trên VM resource không tự thay cho AMA/DCR** thu guest logs hoặc SQL-specific metrics. Ngoài ra, `az vm show` thể hiện disk attachment chứ không cho biết tất cả filesystem layout/SQL file mappings; đối chiếu T-SQL từ phần trước.

## 26. Lịch bảo trì, patching và thay đổi có kiểm soát

Một SQL VM production cần **maintenance plan** cho OS, SQL cumulative updates/security fixes, driver, SQL IaaS Agent extension, backup agent và antimalware.

Runbook:

1. Ghi hiện trạng VM/SQL versions, AG/FCI topology, health và restore points.
2. Kiểm tra release notes, compatibility ứng dụng, SQL features và drivers.
3. Xác nhận backup mới nhất, log chain và restore drill gần nhất.
4. Kiểm tra AZ/region capacity, quota, disk space và secondary health.
5. Thực hiện staging test hoặc node thứ cấp trước.
6. Với HA, lên kế hoạch failover/rolling maintenance theo cấu hình hỗ trợ.
7. Thực thi patching/SQL service restart có phê duyệt; có thể có downtime hoặc connection reset.
8. Kiểm tra SQL service, database ONLINE, AG sync, listener và Agent jobs.
9. Chạy smoke tests từ ứng dụng, kiểm tra query latency, error rate và backup.
10. Ghi kết quả, rollback/forward-fix plan và post-change notes.

**Azure Update Manager** hoặc các tính năng patching được Azure/SQL VM hỗ trợ có thể hỗ trợ orchestration nhưng không biết tự động mọi ràng buộc nghiệp vụ, DB failover và ứng dụng. Không bật auto-reboot trên primary SQL production theo lịch bất kỳ nếu không có kế hoạch HA/cutover.

### SQL Agent jobs

Các jobs backup, ETL, cleanup, statistics/index maintenance hoặc external integration cần được kiểm kê. Với AG, một số instance-level objects như **logins, SQL Agent jobs, linked servers** không tự đồng bộ theo database replication. Phải có cách quản lý chúng trên secondary khi failover và kiểm tra run-once logic, tránh job chạy trùng.

## 27. Tối ưu chi phí và quản trị tài nguyên

Chi phí SQL Server trên Azure VM thường bao gồm:

~~~text
VM compute
+ Windows / SQL licensing theo mô hình áp dụng
+ managed disks (capacity / performance)
+ backup vault / Blob capacity / operations
+ network transfer, Load Balancer, Firewall, Bastion
+ monitoring/log retention
+ HA/DR replicas và dữ liệu replication
+ công vận hành / hỗ trợ / compliance
~~~

### Những quyết định ảnh hưởng lớn

- Edition/license và số vCPU.
- VM instance size và giờ chạy.
- Premium SSD/Ultra/Premium SSD v2 IOPS/throughput provisioning.
- Số replica AG/FCI/DR và region/zone placement.
- Backup retention và immutable copies.
- Log Analytics ingestion/retention.
- Dedicated networking và transfer cross-zone/cross-region.

### Rightsizing

Không resize production VM chỉ dựa trên CPU trung bình. Cần xem:

- Peak CPU theo thời điểm giao dịch.
- Memory pressure/working set.
- Disk latency/IOPS/throughput và caps mới.
- VM network limits.
- License cost theo cores.
- Downtime và HA khi thay SKU.
- SKU mới có hỗ trợ disk/features và zone hiện tại không.

### Reserved Instances, Savings Plans và licensing

Các ưu đãi compute và license áp dụng tùy SKU, hợp đồng, vùng và chính sách. Phải kiểm tra loại chi phí được giảm, cam kết thời hạn, quyền sử dụng và tính linh hoạt trước khi chọn. **Đừng kết luận Reserved Instance đã bao gồm SQL Server licensing trong mọi trường hợp.**

### Dọn môi trường lab

Dừng VM chưa chắc xóa disks, snapshots, backup vault, NIC/Public IP hoặc SQL VM resource. **Deallocate** có thể giảm một số compute charges, nhưng disk/storage và các tài nguyên khác có thể tiếp tục tính phí. Khi dọn lab, liệt kê đúng những resource thuộc lab, xác nhận không xóa hạ tầng dùng chung.

## 28. Quy trình migration từ SQL Server on-premises

### Discovery

Thu thập:

- SQL Server version/edition/patch và feature inventory.
- Database sizes, filegroups, transaction log growth.
- CPU/RAM/IOPS/latency theo giờ và đỉnh.
- Logins, SQL Agent jobs, linked servers, SSIS/SSRS/SSAS dependencies.
- Collation, compatibility level, encryption/TDE certificates.
- Network dependencies, IP allowlist, TLS/driver versions.
- RPO/RTO, maintenance window, HA/DR hiện tại.
- License entitlement và compliance.

### Chọn cách chuyển dữ liệu

| Phương án | Khi phù hợp | Đánh đổi |
|---|---|---|
| Backup/restore | Database có thể offline theo maintenance window | Downtime phụ thuộc backup/transfer/restore |
| Full + differential + log chain | Muốn giảm dữ liệu thay đổi tại cutover | Quản lý log chain và thời điểm cutover |
| AG/log shipping migration | Có khả năng đồng bộ trước để giảm downtime | Cần compatible versions/topology và runbook |
| Rehost VM | Phần mềm phụ thuộc OS/instance nhiều | Vẫn phải đánh giá sizing, network, performance, licensing |
| PaaS migration sau assessment | Muốn giảm quản trị IaaS khi tương thích | Kiểm tra feature gaps và app changes |

### Cutover checklist

1. Có migration runbook và rollback decision point.
2. Backup/restore thử trên Azure VM staging.
3. Chuyển logins, jobs, certificates và dependencies theo quy trình.
4. Kiểm tra app connectivity/TLS/DNS, query plans và performance.
5. Đồng bộ phần dữ liệu còn lại và xác minh consistency.
6. Chặn/điều phối writes tại nguồn khi cutover theo phương án được chọn.
7. Chuyển connection string/DNS và mở traffic có kiểm soát.
8. Kiểm tra business transactions, không chỉ `SELECT 1`.
9. Xem monitoring, backup/DR policy và alert mới.
10. Giữ phương án rollback/failback khả thi trước khi ngừng môi trường cũ.

Không nâng major SQL version, thay database compatibility, đổi collation, migration dữ liệu và chuyển sang Kubernetes đồng thời nếu không có kế hoạch thử nghiệm đủ mạnh: nhiều thay đổi cùng lúc khiến root cause khó xác định.

## 29. Chẩn đoán sự cố SQL VM theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Client timeout/kết nối thất bại | NSG/Windows Firewall, TCP port, DNS, TLS, listener, service down | Private path, listener, SQL service, error log |
| Đăng nhập thất bại | SQL/Windows/Entra auth, disabled login, password, Kerberos/SPN | SQL error number, auth mode, identity |
| JDBC báo chứng chỉ | Sai FQDN, CA trust, certificate hết hạn | SQL TLS configuration, server cert, driver |
| Transaction chậm | Log write latency, blocking, CPU, lock escalation | DMV waits, file latency, Query Store |
| Read I/O cao | Query scan/index thiếu, RAM pressure, disk cap | Plans, buffer, storage metrics |
| tempdb đầy | Query spills, version store, size/volume không đủ | tempdb files, waits, active transactions |
| SQL log đầy | Log backup lỗi, long transaction, AG/replication lag | Log reuse wait, backup jobs, log capacity |
| VM CPU thấp nhưng API chậm | SQL waits, lock, network hoặc downstream | Dependency trace + SQL DMV |
| AG failover không được | Quorum, replica state, endpoint/network, listener | WSFC/quorum logs, AG health, DNS/LB |
| Secondary không theo kịp | Network latency, log send/redo queue, disk I/O | AG DMVs, network/IO telemetry |
| Backup xanh nhưng restore fail | Thiếu TDE key, backup chain, corruption hoặc permission | Restore drill, CHECKSUM, certificates |
| Storage hết chỗ | Growth không kiểm soát, log/tempdb/index | Filesystem, SQL files, retention |
| Sau patch app lỗi | Driver/compatibility, TLS change, login, SQL plan regression | Version/change logs, Query Store, smoke tests |
| Chi phí đột biến | VM/SQL license, disks provisioned, DR/backup/logging | Cost Management breakdown, tags |

### Thứ tự điều tra

1. Xác định **ứng dụng và nghiệp vụ nào bị ảnh hưởng**: latency, 500/503, timeout hay data corruption.
2. Xác định **thời điểm và thay đổi gần nhất**: patch, deployment, failover, storage resize.
3. Kiểm tra VM/SQL service/network trước khi đổ lỗi database query.
4. Xem SQL error logs, backup status, DMVs, waits và Query Store.
5. Xem Azure platform metrics, disk caps, subnet/NSG/firewall.
6. Nếu HA, xem replica health, quorum, listener và failover events.
7. Chọn mitigation có rollback: điều chỉnh queries, giảm concurrency, chuyển traffic hoặc failover theo runbook.
8. Xác minh phục hồi bằng **business success**, không chỉ VM ở trạng thái Running.

Không thử nghiệm lệnh `KILL`, `DBCC` sửa dữ liệu, rebuild index toàn DB hoặc thay AG quorum trên production chỉ để "xem có hết lỗi không".

## 30. Case study: hệ thống đơn hàng cần chuyển lên Azure

### Bối cảnh

Một công ty có SQL Server 2019, database Orders 1,2 TiB và hệ thống API Java. Workload gồm:

- Khoảng 1.000 transactions/s tại đỉnh (giả định để lập kế hoạch, không phải benchmark Azure).
- Các query OLTP nhiều đọc ngẫu nhiên, transaction log ghi liên tục.
- Báo cáo đêm tạo I/O burst.
- Ứng dụng hiện dùng SQL Agent jobs và Windows authentication.
- RPO mong muốn tối đa 15 phút; RTO dưới 1 giờ.
- Đang dùng backup full hàng ngày nhưng chưa có restore drill gần đây.

### Đánh giá phương án

**PaaS:** xem Azure SQL Managed Instance có đáp ứng đầy đủ Agent jobs, linked servers, authentication và compatibility không. Nếu đạt, PaaS có thể giảm công quản lý patch/HA. Nếu không đạt hoặc deadline migration quá gấp, SQL Server Azure VM có thể là bước chuyển tiếp hợp lý.

**Sizing:** đo CPU, memory, Query Store và disk latency ở nguồn; chọn VM có headroom cho peak và storage IOPS/throughput phù hợp. Không chọn VM theo database size duy nhất.

**Storage:** data và log phân tách; tempdb disk nhanh với kiểm soát lifecycle; backup độc lập ra vault/Blob.

**Network:** SQL VM private subnet, Java API truy cập qua DNS và TLS; chỉ mở đúng port từ app subnet. DBA đi qua Bastion/VPN.

**Backup:** FULL recovery + log backups, thực hành restore 1,2 TiB để chứng minh RTO. Nếu restore quá chậm, cần HA/DR bổ sung và/hoặc mục tiêu kinh doanh khác.

**HA:** nếu RTO một giờ và yêu cầu khi VM hỏng, cân nhắc AG replicas ở zone khác, listener/quorum và failover drill. So sánh chi phí thêm VM/license với mức mất doanh thu dự kiến.

**Vận hành:** Azure Monitor, SQL DMVs, Query Store, alerts backup age, disk latency, AG health, Cost Management.

### Kịch bản mất node

~~~mermaid
flowchart TD
  A["Alert: SQL endpoint unavailable"] --> B["Kiểm tra VM / SQL service / network"]
  B --> C{"AG/FCI còn quorum, secondary healthy?"}
  C -->|Có| D["Failover theo policy/runbook"]
  C -->|Không| E["Đánh giá restore/DR từ backup"]
  D --> F["Kiểm tra listener DNS, app reconnect"]
  E --> F
  F --> G["Test giao dịch và data consistency"]
  G --> H["Đối chiếu RPO/RTO, báo cáo incident"]
~~~

Failover không đồng nghĩa mọi transaction và connection luôn được giữ; client cần reconnect/retry **idempotent** theo nghiệp vụ. Nếu AG asynchronous, xác định mức data loss trước khi kích hoạt DR.

## 31. Bài thực hành có hướng dẫn

> **An toàn:** chỉ thực hiện trên resource group/VM lab được phép và có ngân sách. Các thao tác tạo VM, SQL install, backup, disk resize, HA setup có thể phát sinh chi phí hoặc gây downtime. Bài không yêu cầu chạy lệnh thay đổi production.

### Phần A — Thiết kế kiến trúc

Lập mô hình cho API Java cần SQL Server:

1. Xác định vì sao cần SQL VM thay vì Azure SQL Database/Managed Instance.
2. Chọn Windows/Linux, SQL version/edition và cách license theo entitlement thực.
3. Vẽ VNet: app subnet, SQL VM private subnet, admin access, Storage/Key Vault connectivity.
4. Chọn VM size dựa trên peak CPU/RAM, VM-level I/O caps, HA target.
5. Tách data/log/tempdb và chọn disk performance tiers.
6. Thiết kế backup policy với RPO/RTO, retention và lịch restore drill.
7. Chọn HA/DR cần thiết, listener/quorum và failure domains.
8. Xác định monitoring alerts, ownership và cost tags.

### Phần B — Kiểm tra Azure VM đã có

1. Dùng `az account show` xác nhận subscription.
2. Dùng `az vm show` xem VM size, location, storage profile.
3. Dùng `az sql vm show` kiểm tra SQL VM registration khi có.
4. Xác định NSG và mạng private bằng Portal/CLI được tổ chức cho phép.
5. Xem VM CPU metric và đảm bảo không lộ secrets trong output.
6. Kiểm tra disk SKU, LUN, host caching và disk capacity theo quyền read-only.
7. Kiểm tra automated backup/Azure Backup protection policy hiện được sử dụng.

### Phần C — Kiểm tra bằng T-SQL

1. Xem SQL version/edition, danh sách databases và recovery models.
2. Liệt kê data/log files và đường dẫn vật lý.
3. Chạy DMV I/O latency, lấy mẫu hai lần để tính delta.
4. Xem wait stats trong cửa sổ phù hợp; phân biệt log waits, CPU, blocking.
5. Kiểm tra Query Store hoặc execution plan cho một query chậm trong lab.
6. Kiểm tra login/application permissions và TLS certificate theo policy.
7. Xem lịch sử backup, last successful full/diff/log backup.
8. Chạy restore verification/restore drill trên instance lab độc lập nếu có đủ quyền.

### Phần D — Mô phỏng sự cố

Trong lab không có dữ liệu sản xuất:

1. Cố tình làm một ứng dụng client không kết nối được vì sai port/hostname; phân biệt DNS với auth failure.
2. Thử một query thiếu index và đo latency; xem plan trước khi thêm index.
3. Mô phỏng backup job lỗi, quan sát alert và recovery gap.
4. Nếu có cluster lab HA, thực hiện failover theo runbook và đo downtime/reconnect.
5. Kiểm tra TDE certificate/backup dependency trong môi trường thử nghiệm nếu dùng TDE.
6. So sánh VM/disk cost với dự toán và dọn lab theo quyền cho phép.

### Câu hỏi tự kiểm tra

**Câu 1.** Khác biệt lớn nhất về trách nhiệm vận hành giữa SQL Server trên Azure VM và Azure SQL Managed Instance là gì?

**Câu 2.** SQL IaaS Agent extension và resource SQL virtual machine có phải một SQL Server instance thứ hai không?

**Câu 3.** Vì sao VM SKU IOPS cap có thể giới hạn performance dù managed disk được provision IOPS rất cao?

**Câu 4.** Vì sao transaction log thường cần disk latency thấp và nên đánh giá tách khỏi data files?

**Câu 5.** Có nên đặt user database và bản backup duy nhất trên temporary local SSD không? Vì sao?

**Câu 6.** Một SQL VM có private IP trong VNet có tự được bảo vệ khi application account dùng quyền sysadmin không?

**Câu 7.** Sự khác nhau giữa Azure managed disk encryption, SQL TDE và TLS?

**Câu 8.** FULL recovery model có tự tạo log backups và đảm bảo point-in-time restore không?

**Câu 9.** Vì sao `RESTORE VERIFYONLY` chưa đủ để chứng minh RTO và dữ liệu sau restore hoàn chỉnh?

**Câu 10.** Availability Zone khác gì một SQL Always On Availability Group hai replicas?

**Câu 11.** AG và FCI khác nhau về storage và phạm vi failover như thế nào?

**Câu 12.** Khi AG failover, những đối tượng nào ngoài database (logins, jobs, linked servers, app DNS) cần kiểm tra?

**Câu 13.** Async AG replica có bảo đảm RPO=0 khi region primary gặp sự cố không?

**Câu 14.** Vì sao SQL Server DMVs về file I/O phải được đọc theo delta thay vì chỉ so một giá trị cumulative?

**Câu 15.** VM CPU thấp nhưng API SQL chậm; có thể do những nhóm nguyên nhân nào?

**Câu 16.** Tại sao Azure Hybrid Benefit phải được xác minh theo entitlement thay vì đổi tag/licenseType theo ý muốn?

**Câu 17.** Một SQL VM dùng TLS với `trustServerCertificate=false` gặp lỗi chứng chỉ; cách sửa đúng là gì?

**Câu 18.** Một hệ thống yêu cầu RTO 10 phút nhưng database backup restore mất 90 phút; cần đánh giá giải pháp nào?

**Câu 19.** Những khoản phí nào còn phát sinh sau khi deallocate VM lab?

**Câu 20.** Khi nào nên khuyến nghị chuyển từ SQL VM lên Azure SQL Managed Instance/Database?

**Tiêu chí hoàn thành:** người học lập được quyết định IaaS/PaaS, sơ đồ SQL VM có storage/network/identity phù hợp, runbook backup-restore/HA, dùng Azure CLI + T-SQL để quan sát hệ thống, biết giới hạn hiệu năng/giấy phép và đánh giá bảo mật/chi phí.

## Kết luận

**SQL Server trên Azure Virtual Machines** là lựa chọn IaaS phù hợp khi cần **kiểm soát SQL Server instance và hệ điều hành**, duy trì tính tương thích với hệ thống hiện hữu hoặc thực hiện migration theo giai đoạn. Nó mở ra khả năng tận dụng Azure VM, managed disks, Availability Zones, private networking, Azure Monitor, Azure Backup và các mô hình license phù hợp.

Tuy nhiên, một SQL Server chạy trên Azure VM vẫn cần **đội vận hành chịu trách nhiệm chủ động** về sizing, data/log layout, SQL patching, identity/TLS/TDE, backup và restore drill, Always On/FCI, DR, theo dõi I/O/SQL waits, incident response và tối ưu tổng chi phí. Nền tảng đáng tin cậy được tạo nên bởi **RPO/RTO đo được, nhiều lớp phòng vệ, kiểm thử failover/restore và monitoring gắn với kết quả nghiệp vụ** — không chỉ bởi trạng thái VM `Running` trong Azure Portal.

