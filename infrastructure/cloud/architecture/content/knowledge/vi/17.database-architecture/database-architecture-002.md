# Chọn dịch vụ được quản lý và xác định trách nhiệm còn lại

Khi triển khai cơ sở dữ liệu trên cloud, đội ngũ có thể tự cài database trên máy ảo, dùng nền tảng database được quản lý hoặc chọn một dịch vụ dữ liệu chuyên biệt. Dịch vụ càng được quản lý nhiều thì nhà cung cấp thường đảm nhiệm thêm các công việc như cấp phát hạ tầng, thay thế phần cứng, sao lưu, vá nền tảng hoặc chuyển đổi dự phòng. Tuy nhiên, **managed database không có nghĩa là nhà cung cấp chịu trách nhiệm cho toàn bộ dữ liệu và độ tin cậy của ứng dụng**.

Đội ngũ vẫn phải chọn cấu hình, mô hình dữ liệu, quyền truy cập, chính sách retention, mức sẵn sàng, mục tiêu phục hồi, chiến lược chi phí và cách kiểm chứng. Một database có tính năng backup nhưng chưa từng thử restore vẫn có thể khiến doanh nghiệp mất nhiều giờ khi sự cố xảy ra. Một database bật mã hóa mặc định vẫn có thể bị lộ dữ liệu vì quyền ứng dụng quá rộng hoặc snapshot được chia sẻ sai.

Bài học thuộc phần **Kiến trúc cơ sở dữ liệu** của học phần thiết kế kiến trúc đám mây. Trọng tâm là chọn mức dịch vụ được quản lý phù hợp và làm rõ ranh giới trách nhiệm giữa nhà cung cấp cloud với đội phát triển/vận hành. Các quyết định phải gắn với yêu cầu nghiệp vụ và đánh đổi về độ tin cậy, bảo mật, hiệu năng, mở rộng, chi phí và vận hành theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt database tự quản trên IaaS, nền tảng managed database và dịch vụ database cloud-native.
- Xác định phần việc nhà cung cấp đảm nhiệm và phần việc khách hàng vẫn phải thực hiện.
- Đánh giá trách nhiệm về HA, backup/restore, DR, patching, version, bảo mật và quyền dữ liệu.
- Chọn cấu hình dịch vụ theo workload, RPO/RTO, hiệu năng, region và ngân sách.
- Thiết kế giám sát, kiểm thử phục hồi, quản lý thay đổi và quy trình ứng cứu.
- So sánh tổng chi phí và rủi ro phụ thuộc nhà cung cấp.
- Lập checklist và ma trận trách nhiệm để đưa managed database vào production.

## 1. Managed database là gì?

Một database luôn cần compute, memory, storage, network, hệ điều hành hoặc runtime, engine, backup, monitoring và quy trình phục hồi. Khác biệt giữa các mô hình chủ yếu nằm ở **ai cung cấp, ai vận hành và ai ra quyết định** cho từng lớp.

Trong mô hình tự quản trên VM, đội ngũ thường cài và cấu hình database, quản trị hệ điều hành, patch, replication, backup, monitoring và failover. Với managed database, nhà cung cấp nhận thêm một phần công việc nền tảng qua API/console và SLA dịch vụ. Đội vẫn phải quản trị schema, truy vấn, quyền dữ liệu, cấu hình workload và xác minh rằng mục tiêu nghiệp vụ được đáp ứng.

### Các mức quản lý phổ biến

| Mô hình | Nhà cung cấp thường quản lý | Khách hàng thường quản lý |
| --- | --- | --- |
| **Database tự quản trên VM (IaaS)** | Hạ tầng vật lý, hypervisor, một phần mạng/ổ đĩa/VM theo dịch vụ | OS, database engine, patch, replication, backup, restore, HA, monitoring và dữ liệu |
| **Managed database trên cloud (DBaaS)** | Provisioning, OS/runtime nền, một phần patch, backup/HA và thay thế hạ tầng theo tính năng/SKU | Schema, query, index, user/role, network exposure, encryption policy, retention, cấu hình HA/DR, test restore và chi phí |
| **Database serverless/elastic managed** | Nền tảng cấp phát và co giãn compute/storage theo semantics dịch vụ | Data model, quota/capacity guardrail, concurrency, cost control, access, consistency, backup/restore policy và kiểm thử |
| **Database SaaS chuyên biệt** | Phần lớn nền tảng và vận hành sản phẩm | Tenant, data lifecycle, quyền, kết nối, cấu hình, tích hợp và trách nhiệm tuân thủ của doanh nghiệp |

Đây là cách phân loại khái quát. Ranh giới thực tế phụ thuộc nhà cung cấp, loại engine, phiên bản, region, tier/SKU và hợp đồng. Có dịch vụ managed nhưng khách hàng vẫn phải lên lịch maintenance; có dịch vụ tự động backup nhưng PITR chỉ khả dụng sau khi bật tùy chọn hoặc chọn retention phù hợp.

### Managed không đồng nghĩa serverless

**Managed** mô tả mức nhà cung cấp đảm nhiệm vận hành. **Serverless** mô tả cách dịch vụ cấp phát/định giá compute hoặc cách người dùng tiêu thụ năng lực mà không quản lý instance theo kiểu truyền thống. Một database có thể managed nhưng luôn chạy trên cấu hình capacity cố định; một dịch vụ serverless cũng vẫn có quota, giới hạn, độ trễ khởi tạo và chi phí theo mức dùng.

Không nên chọn dịch vụ chỉ vì tên có chữ managed hoặc serverless. Hãy xác định công việc vận hành nào muốn chuyển giao, khả năng nào cần có và trách nhiệm nào vẫn nằm ở tổ chức.

## 2. Mô hình trách nhiệm chia sẻ

Cloud hoạt động theo mô hình **shared responsibility**: nhà cung cấp bảo vệ hạ tầng và những lớp được nêu trong dịch vụ; khách hàng bảo vệ workload, dữ liệu, danh tính và cấu hình trong phạm vi của mình. Với dịch vụ managed, ranh giới có thể dịch lên tầng database engine, nhưng trách nhiệm dữ liệu của khách hàng vẫn còn.

~~~mermaid
flowchart TD
    subgraph CSP["Nhà cung cấp cloud — phần phụ thuộc dịch vụ"]
        PHY["Datacenter / phần cứng"]
        HYP["Hypervisor / hạ tầng ảo hóa"]
        BASE["Hệ điều hành / runtime nền<br/>theo phạm vi DBaaS"]
        ENGINE["Vận hành engine / patch nền<br/>theo cấu hình dịch vụ"]
        PHY --> HYP --> BASE --> ENGINE
    end
    subgraph CUSTOMER["Khách hàng — trách nhiệm workload và dữ liệu"]
        ID["Danh tính, IAM, secrets"]
        NET["Network, private access, firewall"]
        DATA["Schema, dữ liệu, classification"]
        CFG["Cấu hình, HA/DR, retention"]
        APP["Ứng dụng, query, connection pool"]
        TEST["Kiểm thử restore, runbook, cost"]
    end
    ENGINE --> DATA
    ID --> APP
    NET --> APP
    DATA --> CFG
    CFG --> TEST
~~~

Sơ đồ mang tính khái niệm, không phải hợp đồng trách nhiệm cho một SKU cụ thể. Nhà cung cấp có thể quản lý database patch và backup service, nhưng khách hàng vẫn phải chọn cửa sổ bảo trì, retention, quyền truy cập, phiên bản được hỗ trợ và xác nhận restore đáp ứng nghiệp vụ.

### 2.1. Trách nhiệm không biến mất khi chuyển sang managed service

Một dịch vụ managed có thể giảm công cài đặt, nhưng đội ngũ vẫn chịu trách nhiệm:

- Xác định dữ liệu được lưu, phân loại dữ liệu nhạy cảm và thời gian giữ.
- Thiết kế bảng, khóa, transaction, index, partition và query.
- Quản lý user, role, service identity, secret và quyền ở cấp database.
- Chỉ mở kết nối từ network/identity được phép.
- Chọn region, tier, cấu hình storage, HA và backup.
- Thiết lập monitoring, alert, log access và audit.
- Thử restore, failover, nâng cấp và khôi phục sau lỗi theo RTO/RPO.
- Kiểm soát chi phí, quota, tăng trưởng dữ liệu và egress.
- Có kế hoạch migration, export và xử lý khi dịch vụ/engine hết vòng đời.

### 2.2. Ma trận trách nhiệm mẫu

| Công việc | Nhà cung cấp thường đảm nhiệm | Khách hàng cần xác nhận/thực hiện |
| --- | --- | --- |
| Datacenter, nguồn điện, phần cứng | Vận hành và thay thế theo SLA | Chọn region/zone phù hợp, hiểu phạm vi SLA |
| Hạ tầng VM/host | Provisioning và bảo trì nền tảng | Chọn tier/capacity, đặt quota và ngân sách |
| OS/runtime nền | Patch/quản lý khi DBaaS bao gồm | Xem maintenance policy, thông báo và tác động |
| Database engine | Cài đặt, backup/patch hoặc failover theo tính năng | Chọn engine/version/parameter, tương thích ứng dụng |
| Schema và dữ liệu | Cung cấp khả năng lưu trữ | Thiết kế, phân loại, migration, retention và integrity |
| IAM và database roles | Cung cấp cơ chế identity/access | Cấp least privilege, rotation, review và revoke |
| Network | Cung cấp VPC/private endpoint/firewall primitives | Cấu hình route, subnet, source, TLS và segmentation |
| Backup service | Chạy backup theo cấu hình | Bật/chọn retention, PITR, encryption, cross-region copy nếu cần và thử restore |
| HA/failover | Cung cấp cơ chế và hạ tầng hỗ trợ | Chọn topology, kiểm tra client retry, đo downtime và dependency |
| DR | Cung cấp replication/backup options | Định nghĩa RTO/RPO, runbook, diễn tập và failback |
| Monitoring nền tảng | Metrics/service health theo dịch vụ | Dashboard theo workload, alert, query performance và business SLI |
| Chi phí | Công bố cách tính theo dịch vụ | Sizing, budget, egress, storage growth và cost allocation |
| Incident | Khắc phục phần nền tảng thuộc nhà cung cấp | Phát hiện tác động, liên hệ support, quyết định failover và truyền thông |

Các cột không phải ranh giới cứng. Ví dụ backup do nhà cung cấp thực hiện nhưng **khả năng phục hồi** là kết quả chung: nhà cung cấp phải cung cấp chức năng đáng tin cậy, khách hàng phải cấu hình và thử quy trình khôi phục.

## 3. Chọn dịch vụ managed theo yêu cầu workload

Đừng bắt đầu bằng danh sách sản phẩm. Hãy bắt đầu bằng workload và dữ liệu:

1. Dữ liệu quan hệ hay key-value/document/time-series/graph?
2. Read/write ratio, transaction, consistency và access pattern?
3. Dung lượng ban đầu, tốc độ tăng, burst và peak concurrency?
4. Latency p95/p99, throughput và các truy vấn quan trọng?
5. SLO, RTO, RPO, maintenance window và phạm vi người dùng?
6. Yêu cầu data residency, encryption, audit và compliance?
7. Kỹ năng đội ngũ, mức độ tự quản chấp nhận được và ngân sách?
8. Khả năng export, restore, đổi engine hoặc chuyển nhà cung cấp?

### Bản đồ lựa chọn khái quát

| Nhu cầu | Loại database có thể phù hợp | Nội dung cần kiểm tra |
| --- | --- | --- |
| Quan hệ, transaction, join và constraint | Managed relational (PostgreSQL/MySQL/SQL Server hoặc engine phù hợp) | Isolation level, connection, extension, replica, failover, backup |
| Key-value/document với access pattern xác định | Managed NoSQL | Partition key, consistency, transaction scope, hot partition, index, TTL |
| Cache/session ngắn hạn | Managed in-memory cache | Persistence, eviction, replication, failover, private access |
| Phân tích dữ liệu lớn | Data warehouse/lakehouse service | Ingestion, query concurrency, storage/compute separation, cost per query |
| Time-series/metrics | Managed time-series database hoặc nền tảng tương ứng | Retention, downsampling, cardinality, compression |
| Graph traversal | Managed graph database | Query pattern, throughput, graph size và portability |

Managed database không tự làm data model trở nên phù hợp. Chọn NoSQL để “scale” nhưng vẫn cần join tùy ý, transaction xuyên nhiều aggregate và truy vấn ad hoc có thể chuyển chi phí từ vận hành hạ tầng sang độ phức tạp ứng dụng.

### Tiêu chí loại bỏ sớm

Loại dịch vụ khỏi shortlist khi có một yêu cầu bắt buộc không đáp ứng, ví dụ:

- Engine/region không đáp ứng data residency hoặc hợp đồng.
- Không hỗ trợ extension, collation hoặc tính năng SQL thiết yếu.
- RPO/RTO cao hơn mục tiêu đã cam kết.
- Không thể dùng network/private access theo policy.
- Thiếu khả năng export/restore cần cho kế hoạch thoát.
- Quota hoặc giới hạn kết nối không đáp ứng peak đã đo.
- Chi phí ở tải thực tế vượt ngân sách được duyệt.

## 4. HA, backup, restore và DR: ai làm gì?

Đây là nơi dễ hiểu sai nhất khi dùng managed database. Nhà cung cấp có thể quản lý replication hoặc snapshot, nhưng không tự biết doanh nghiệp cần phục hồi đến thời điểm nào, dữ liệu nào cần giữ và ứng dụng có tiếp tục phục vụ sau failover hay không.

### 4.1. High Availability

HA nhằm giảm gián đoạn khi một thành phần hoặc failure domain bị lỗi. Dịch vụ có thể hỗ trợ standby, multi-AZ, replication hoặc tự động failover. Khách hàng cần:

- Chọn cấu hình HA phù hợp, hiểu phạm vi lỗi được bảo vệ.
- Đặt ứng dụng ở nhiều zone và cấu hình network/connection tương thích.
- Xử lý DNS/endpoint thay đổi, connection reset và retry an toàn.
- Theo dõi replication lag, health, failover event và thời gian phục hồi.
- Thử failover và đo tác động tới transaction đang chạy.

**HA không thay thế backup.** Replication có thể sao chép cả thao tác xóa nhầm hoặc dữ liệu bị sửa sai sang replica. Khi cần quay về thời điểm trước lỗi logic, backup/PITR có vai trò riêng.

### 4.2. Backup và point-in-time recovery

Nhà cung cấp có thể chạy snapshot hoặc backup liên tục theo gói dịch vụ. Khách hàng vẫn phải quyết định:

- Retention bao nhiêu ngày/tháng theo nghiệp vụ và quy định?
- Có cần point-in-time recovery (PITR) không?
- Backup có được mã hóa bằng key phù hợp không?
- Snapshot có được copy sang account/region khác không?
- Ai được phép restore, copy hoặc xóa backup?
- Khi restore, ứng dụng sẽ chuyển endpoint và đối soát dữ liệu ra sao?

Backup thành công không đồng nghĩa restore thành công. Hãy diễn tập restore vào môi trường cô lập, đo thời gian, kiểm tra dữ liệu và ghi nhận các bước cutover.

### 4.3. RTO và RPO

- **RTO (Recovery Time Objective):** thời gian gián đoạn tối đa doanh nghiệp chấp nhận để khôi phục dịch vụ.
- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất, biểu diễn bằng khoảng thời gian dữ liệu.

Ví dụ một workload đặt lịch yêu cầu RTO 60 phút và RPO 5 phút. Điều này cần được chứng minh qua topology, backup/replication, quy trình restore/failover, quyền truy cập và thời gian ứng dụng trở lại phục vụ. Chọn dịch vụ có tính năng multi-AZ không tự chứng minh RTO 60 phút; cấu hình và failure mode phải được thử.

### 4.4. Disaster Recovery

DR xử lý sự cố vượt phạm vi HA thông thường, ví dụ mất region, lỗi tài khoản, xóa dữ liệu diện rộng hoặc compromise. Các mô hình thường gặp:

| Mô hình | Tài nguyên dự phòng | Đánh đổi |
| --- | --- | --- |
| Backup and restore | Backup ở vị trí khác, tạo hạ tầng khi cần | Chi phí nền thấp hơn, RTO thường dài hơn |
| Pilot light | Một phần hạ tầng/dữ liệu sẵn sàng | Cần mở rộng và cutover khi thảm họa |
| Warm standby | Hệ thống thu nhỏ nhưng đang chạy ở vùng dự phòng | Chi phí cao hơn, phục hồi nhanh hơn nếu đã diễn tập |
| Active-active | Nhiều vùng cùng phục vụ | Phức tạp về ghi dữ liệu, conflict, consistency và chi phí |

Managed database có thể cung cấp cross-region replica hoặc backup copy nhưng khách hàng phải xác định replication mode, failover authority, data residency, failback và cách ứng dụng xử lý ghi ở hai nơi.

## 5. Patching, phiên bản và maintenance

Managed database thường giảm công quản trị hệ điều hành và một phần database patching. Nhưng lịch bảo trì, version support và thay đổi engine vẫn có tác động đến ứng dụng.

Nhóm cần làm rõ:

- Nhà cung cấp tự động patch phần nào: host, OS, engine, minor version hay major version?
- Maintenance window có được đặt trước không? Có thông báo và tùy chọn hoãn không?
- Failover/restart có xảy ra trong bảo trì?
- Phiên bản sắp hết hỗ trợ có chính sách extended support và chi phí bổ sung?
- Parameter/extension nào không được hỗ trợ hoặc bị thay đổi?
- Có môi trường staging để thử nâng cấp trước production?
- Backup/snapshot trước thay đổi có đủ để rollback, và restore mất bao lâu?

### Minor và major upgrade

Minor update thường tập trung bản vá hoặc cải thiện tương thích trong cùng nhánh version, nhưng vẫn cần đọc release note và thử ứng dụng. Major upgrade có thể đổi behavior, extension, query planner, replication hoặc protocol; cần migration plan, compatibility test và window.

**Không mặc định rollback version đơn giản như rollback application.** Một database sau khi ghi bằng schema hoặc format mới có thể không tương thích version cũ. Kế hoạch nâng cấp cần backward-compatible migration hoặc restore sang môi trường mới rồi cutover.

### Quy trình maintenance gợi ý

1. Theo dõi lịch hỗ trợ và thông báo nhà cung cấp.
2. Đọc release note, CVE và thay đổi behavior liên quan.
3. Clone/snapshot dữ liệu phù hợp vào môi trường test đã bảo vệ.
4. Chạy integration, load, query plan và failover test.
5. Chốt cửa sổ, owner, kế hoạch backup và rollback/recovery.
6. Thực hiện theo rollout được hỗ trợ, theo dõi metric và lỗi.
7. Đối soát sau maintenance và cập nhật runbook/version inventory.

## 6. Bảo mật: managed database không tự bảo vệ dữ liệu khỏi cấu hình sai

Nhà cung cấp có thể bảo vệ datacenter, host, hypervisor và các lớp nền tảng của DBaaS. Khách hàng vẫn phải kiểm soát danh tính, quyền dữ liệu, mạng, encryption policy, secret, audit và vòng đời thông tin.

### 6.1. Identity và least privilege

- Dùng service identity/managed identity thay cho credential dài hạn khi có thể.
- Tách quyền migration, runtime application, read-only analytics và DBA.
- Không dùng tài khoản admin cho connection pool của ứng dụng.
- Thu hồi quyền và rotate secret theo quy trình.
- Bảo vệ quyền tạo snapshot, export, restore, đổi encryption key và chia sẻ backup.
- Audit thay đổi role, policy, parameter và endpoint.

### 6.2. Network boundary

- Ưu tiên private endpoint/private subnet khi phù hợp.
- Không mở database public cho mọi IP chỉ để tiện kết nối.
- Giới hạn source security group/firewall, port và route.
- Xác thực TLS từ client đến database; xác minh server identity theo driver/engine.
- Có đường kết nối quản trị riêng, logging và access approval.
- Cân nhắc DNS, NAT, private link và egress trong môi trường nhiều account/VPC.

### 6.3. Encryption và key management

Phân biệt mã hóa at rest và in transit. Nhà cung cấp có thể mã hóa storage theo mặc định, nhưng khách hàng phải xác định key ownership, rotation, quyền dùng KMS/key manager, snapshot copy và hành vi khi key bị disable hoặc xóa.

Nếu dùng customer-managed key, thu hồi key quá sớm có thể khiến database/backup không đọc được. Key policy và quy trình phục hồi phải là một phần của DR plan.

### 6.4. Data lifecycle và audit

Nhóm phải xác định retention, deletion, masking, tokenization, backup retention và quyền xuất dữ liệu. Xóa bản ghi trong database không nhất thiết xóa bản sao trong snapshot hoặc export ngay lập tức. Cần hiểu lifecycle và deletion semantics của dịch vụ.

Audit log có thể ghi truy cập hoặc thay đổi nhưng không nên bật vô hạn mà không xét chi phí, retention và dữ liệu nhạy cảm. Cần chuyển log tới nơi được bảo vệ độc lập khi yêu cầu điều tra.

## 7. Hiệu năng, scaling và giới hạn dịch vụ

Managed database giảm việc vận hành phần cứng nhưng không loại bỏ bottleneck của query, index, lock, connection hoặc storage.

### Những giới hạn cần xác minh

| Nhóm | Ví dụ giới hạn | Trách nhiệm khách hàng |
| --- | --- | --- |
| Compute | CPU, memory, serverless capacity, burst credit | Sizing, autoscaling guardrail, test peak |
| Connection | Max connection, pool, proxy capacity | Pool sizing, concurrency limit và connection reuse |
| Storage | Dung lượng, IOPS, throughput, auto-grow limit | Forecast, alert, retention, performance test |
| Query | Transaction duration, lock, query concurrency, timeout | Index, query plan, isolation level, workload tuning |
| Replication | Lag, read replica limits, failover semantics | Định nghĩa consistency và read-after-write behavior |
| API/control plane | Provisioning rate, quota, number of instances/replicas | Quản lý quota và quy trình scale |
| Network | Throughput, connection path, cross-zone transfer | Network design, latency và data transfer cost |

### Read replica không tự làm query nhanh

Read replica có thể phân tải truy vấn đọc, nhưng:

- Replication lag khiến dữ liệu chưa cập nhật xuất hiện ở read path.
- Query nặng vẫn có thể bão hòa replica.
- Một số hệ thống không cho đọc replica dùng mọi loại query hoặc transaction semantics.
- Failover/promote replica có thể thay đổi endpoint và vai trò.
- Replica tạo thêm chi phí compute/storage/network.

Ứng dụng cần phân loại query nào chấp nhận eventual consistency và query nào cần đọc từ writer. Không chuyển mọi SELECT sang replica chỉ vì có endpoint.

### Connection pool và autoscaling

Giả sử ứng dụng có 12 instance và mỗi instance mở pool tối đa 20 kết nối, tổng tiềm năng là 240 connections. Nếu autoscaler tăng lên 40 instance, cấu hình cũ có thể tạo nhu cầu 800 connections. Database có thể không đủ sức dù CPU ứng dụng còn dư.

Hãy tính:

~~~text
Potential connections
  = max application replicas × pool maximum per replica
  + worker connections
  + admin/monitoring/migration connections
~~~

Giảm pool, dùng proxy khi phù hợp và giới hạn max replicas/concurrency có thể bảo vệ database. Proxy không xóa giới hạn query concurrency hoặc tài nguyên DB; nó chỉ thay đổi cách quản lý kết nối.

### Capacity planning theo workload

Benchmark cần mô phỏng:

- Tỷ lệ read/write và loại query thật.
- Transaction duration, lock contention và số kết nối.
- Payload, index, partition và tăng trưởng storage.
- Peak burst và thời gian duy trì tải.
- Failover/replica lag và load khi một node/zone mất.
- Background job, backup, vacuum/maintenance và analytics cùng chạy.

Chỉ đo CPU trung bình hoặc RPS tổng không đủ để chọn cấu hình. Theo dõi p95/p99 query latency, connection saturation, lock waits, IOPS, cache hit, replication lag và error rate.

## 8. Monitoring và observability: ai theo dõi điều gì?

Nhà cung cấp thường cung cấp service health và metric nền tảng. Đội ngũ ứng dụng phải kết hợp chúng với metric query, connection, business operation và SLO.

### Metric nền tảng

- Instance/compute utilization và memory.
- Storage utilization, IOPS và latency.
- Connection count và connection errors.
- Replication lag và replica health.
- Backup success, backup age và restore events.
- Failover, restart, maintenance và throttling events.
- Quota/service limit gần đạt ngưỡng.

### Metric ở cấp ứng dụng

- Query latency theo nhóm operation và percentile.
- Transaction duration, deadlock, lock wait và retry.
- Pool active/idle/waiting, timeout và connection acquisition duration.
- Error rate theo SQLSTATE/driver/provider.
- SLI nghiệp vụ như booking commit success, payment reconciliation và dữ liệu bị stale.
- Chi phí theo workload/tenant nếu có thể phân bổ.

### Logging và audit

Không ghi toàn bộ SQL parameter hoặc payload nhạy cảm vào log mặc định. Dùng query fingerprint, duration, error code và trace/correlation ID để điều tra. Quyền xem query log và audit log cần được giới hạn, có retention và giám sát truy cập.

### Cảnh báo theo rủi ro

| Cảnh báo | Vì sao cần |
| --- | --- |
| Backup thất bại hoặc backup age vượt ngưỡng | Rủi ro không đạt RPO |
| Storage sắp đầy | Ghi dữ liệu có thể lỗi hoặc dịch vụ bị gián đoạn |
| Connection pool gần cạn | API timeout dù database CPU có thể chưa cao |
| Replication lag vượt ngưỡng | Read path stale hoặc DR không đạt mục tiêu |
| Failover/restart bất thường | Kiểm tra downtime và lỗi ứng dụng |
| Query p95/p99 tăng | Phát hiện bottleneck trước khi SLO vỡ |
| Quota/cost tăng đột biến | Ngăn scale hoặc phí ngoài dự kiến |
| Access denied bất thường | Dấu hiệu policy sai hoặc hành vi đáng ngờ |

## 9. Chi phí thực của managed database

Giá niêm yết của instance chỉ là một phần. Hãy dự toán tổng chi phí sở hữu:

- Compute/base capacity và standby/HA replica.
- Storage provisioned hoặc consumed, IOPS và throughput.
- Backup storage, snapshot copy, PITR log và retention.
- Read replica, cross-region replication và data transfer.
- Proxy, private endpoint, NAT, monitoring, audit và log ingestion.
- License/engine/extended support hoặc tính năng nâng cao.
- Chi phí migration, test, môi trường staging và DR drill.
- Thời gian nhân sự quản trị query, access, incident, schema và compliance.

### Managed và self-managed

Managed database có thể đắt hơn VM ở hóa đơn hạ tầng nhưng giảm công patching, backup operation và HA maintenance. VM có thể rẻ trên hóa đơn cơ sở nhưng tổng chi phí tăng khi tính người trực, automation, downtime risk, storage và failover test.

So sánh theo **TCO**:

~~~text
TCO =
  compute + storage + IOPS + backup + replication
  + network/egress + support/license
  + monitoring/security
  + migration/DR/staging
  + operational labor
  + expected incident/recovery cost
~~~

Không phải mọi yếu tố đều dễ quy ra tiền; hãy ghi rõ giả định. TCO nên xét tải cơ sở, cao điểm, tăng trưởng 12–36 tháng và failure scenario.

### Serverless/elastic pricing

Mô hình tính phí theo request/capacity/compute tiêu thụ có thể hiệu quả khi tải không đều. Nhưng workload liên tục hoặc query nặng có thể đắt hơn cấu hình provisioned. Đo theo pattern thật và đặt budget alert, quota hoặc capacity cap.

## 10. Portability và rủi ro phụ thuộc nhà cung cấp

Managed database thường có API quản trị, extension, backup format, replication và tính năng riêng của cloud. Dùng tính năng đặc thù có thể tăng giá trị hiện tại nhưng làm migration khó hơn.

Không cần tránh mọi dịch vụ độc quyền. Hãy hiểu **chi phí thoát và khả năng phục hồi chiến lược**:

- Có thể export schema, data, index, role và sequence không?
- Backup có restore được ngoài dịch vụ/region đó hay chỉ dùng trong cùng engine?
- Extension hoặc stored procedure nào phụ thuộc nhà cung cấp?
- Data type, collation, transaction isolation và SQL dialect có portability không?
- CDC/replication có thể đồng bộ sang engine khác không?
- DNS, connection string, secret, IAM và network có phụ thuộc API riêng?
- Migration downtime, data validation và rollback được xử lý ra sao?
- Có chi phí egress hoặc thời gian export rất lớn?

### Các chiến lược portability

1. **Dùng chuẩn phổ biến nơi hợp lý:** SQL, driver, schema migration và giao thức hỗ trợ rộng.
2. **Đóng gói adapter:** giảm việc ứng dụng phụ thuộc trực tiếp vào API quản trị riêng.
3. **Giữ export/restore runbook:** thực hiện định kỳ, không chỉ ghi trên tài liệu.
4. **Quản lý data contract:** version schema và event; tránh phụ thuộc vào implicit behavior.
5. **Chấp nhận proprietary có chủ đích:** ghi rõ lợi ích, chi phí thoát và trigger xem lại trong ADR.

Portability không phải mục tiêu bằng mọi giá. Nếu một dịch vụ cloud-native đáp ứng yêu cầu quan trọng mà engine portable không đáp ứng, chọn proprietary có thể hợp lý khi rủi ro được chấp nhận và có kế hoạch giảm phụ thuộc.

## 11. Migration vào managed database

Chuyển từ database tự quản hoặc dịch vụ khác sang DBaaS cần một quy trình kiểm soát dữ liệu và thời gian gián đoạn.

### Các bước chính

1. **Inventory:** engine/version, extension, schema, volume dữ liệu, role, job, trigger, stored procedure, connection và query.
2. **Compatibility assessment:** kiểm tra type, collation, SQL dialect, feature, driver, isolation và limit.
3. **Target design:** region, network, identity, HA, backup, encryption, parameter, quota và sizing.
4. **Data migration:** snapshot/export-import, logical replication hoặc công cụ migration phù hợp.
5. **Validation:** row counts, checksums, constraints, nulls, sequence, query results và business reconciliation.
6. **Performance test:** workload đại diện, index, connection pool, query plan và peak.
7. **Cutover:** freeze hoặc dual-write/CDC theo kế hoạch; đổi endpoint/secret; theo dõi lỗi.
8. **Rollback window:** quy định điều kiện quay lại, hướng đồng bộ ngược và thời điểm kết thúc.
9. **Decommission:** xóa dữ liệu theo policy sau khi xác nhận backup, audit và phê duyệt.

### Tránh dual-write không kiểm soát

Ghi đồng thời vào source và target từ ứng dụng có thể khiến hai database lệch nhau nếu một bên commit, một bên fail. Dùng CDC/logical replication hoặc migration strategy có checkpoint và reconciliation; nếu bắt buộc dual-write, phải có idempotency, ordering và cách sửa sai.

Không tắt database nguồn ngay sau khi đổi DNS. Giữ trong khoảng rollback được phê duyệt, có quyền hạn chế và kế hoạch đồng bộ dữ liệu phát sinh sau cutover.

## 12. Lập ma trận lựa chọn managed database

Một cách đánh giá có thể tái sử dụng:

| Tiêu chí | Câu hỏi | Mức bằng chứng |
| --- | --- | --- |
| Fit nghiệp vụ | Engine có đáp ứng transaction, consistency và access pattern? | Schema/PoC/test |
| Reliability | HA, backup, restore, failover và DR đạt RTO/RPO? | Failure/restore drill |
| Security | Private access, IAM, encryption, audit, key control? | Threat model và access test |
| Performance | p95/p99, throughput, concurrency, replica lag? | Benchmark theo workload |
| Operability | Maintenance, upgrades, alerts, support và runbook? | Runbook exercise |
| Cost | TCO cơ sở/đỉnh/tăng trưởng/DR? | Estimate + billing model |
| Portability | Export, restore, migration, dependency? | Restore/export test |
| Compliance | Region, retention, deletion, audit evidence? | Policy/contract validation |

### Chấm điểm có trọng số

Có thể dùng điểm 1–5, nhưng các yêu cầu bắt buộc nên là **gates** trước khi tính tổng điểm. Ví dụ dịch vụ không đạt data residency thì không thể bù bằng điểm cost thấp.

Ví dụ trọng số minh họa:

| Tiêu chí | Trọng số giả định |
| --- | ---: |
| Business/data fit | 20% |
| Reliability/restore | 20% |
| Security/compliance | 20% |
| Performance/scale | 15% |
| Operations | 10% |
| TCO | 10% |
| Portability | 5% |

Trọng số phải do người chịu trách nhiệm nghiệp vụ và kỹ thuật thống nhất. Nếu hai dịch vụ chênh nhau ít điểm hoặc dữ liệu ước lượng còn yếu, hãy chạy thêm PoC thay vì tuyên bố có một đáp án khách quan.

## 13. Ví dụ thực tế: chọn managed relational database cho Booking Service

**Bối cảnh giả định:** Một nền tảng đặt lịch có Booking Service và Payment Service. Booking Service cần transaction để không đặt trùng một khung giờ; đội phát triển có sáu kỹ sư và không có DBA chuyên trách trực 24/7. Mục tiêu nội bộ là RTO 60 phút, RPO 5 phút, p95 truy vấn đọc phổ biến dưới 100 ms ở tải dự kiến. Đây là yêu cầu luyện tập, chưa phải cam kết đã kiểm chứng.

### Các phương án

| Phương án | Lợi ích | Đánh đổi |
| --- | --- | --- |
| PostgreSQL tự quản trên VM | Kiểm soát sâu, tùy chỉnh và extension rộng | Đội tự vận hành OS, patch, backup, replication, failover và trực sự cố |
| Managed relational DB tương thích PostgreSQL | Giảm công quản lý nền tảng, có lựa chọn HA/backup theo dịch vụ | Phụ thuộc version/extension/limits, cần cấu hình và test restore, chi phí managed |
| Managed NoSQL | Có thể scale tốt theo access pattern key-based | Cần xem lại mô hình transaction, uniqueness, relation và query; không tự phù hợp bài toán |

### Quyết định đề xuất

Chọn **managed relational database** cho Booking Service nếu PoC xác nhận engine/extension và tính năng cần thiết. Dùng transaction và constraint để bảo vệ quy tắc chống đặt trùng; triển khai HA theo cấu hình được dịch vụ hỗ trợ; bật backup/PITR với retention phù hợp. Private connectivity và service identity được cấu hình theo least privilege.

### Trách nhiệm được phân chia

| Chủ thể | Việc chịu trách nhiệm |
| --- | --- |
| Nhà cung cấp | Hạ tầng database managed, bảo trì các lớp thuộc phạm vi dịch vụ, backup/HA primitives theo cấu hình đã chọn |
| Platform team | Region/tier, VPC/private route, security policy, parameter, monitoring nền tảng, budget và quota |
| Backend team | Schema, constraint, migration, query, transaction, connection pool, retry và idempotency |
| Security | Role review, secret/key policy, audit, data classification và access review |
| SRE/Operations | Dashboard, alert, runbook, restore drill, failover exercise và incident response |
| Product/Data owner | Retention, RTO/RPO, downtime window, deletion và mức chấp nhận mất dữ liệu |

### Điều kiện trước production

- Test concurrent booking chứng minh chỉ một giao dịch thành công cho slot duy nhất.
- Restore drill chứng minh thời gian và dữ liệu phục hồi đáp ứng mục tiêu đã chốt.
- Failover test xác minh ứng dụng kết nối lại và không tạo giao dịch trùng.
- Load test chứng minh query latency/connection pool ở tải dự kiến.
- Access test chứng minh backend không truy cập được từ mạng trái phép.
- Cost estimate có storage, backup, HA replica, network, logs và nhân lực vận hành.
- Export/restore test cho thấy dữ liệu có thể trích xuất theo kế hoạch portability.

## 14. Bài thực hành: xác định ranh giới trách nhiệm cho DBaaS

**Tình huống:** Một ứng dụng thương mại điện tử hiện chạy PostgreSQL tự quản trên VM. Đội muốn chuyển sang managed database để giảm công vận hành. Workload có 2.000 giao dịch/giờ trong giờ cao điểm, 70% read/30% write; dữ liệu 1,5 TB và tăng khoảng 5% mỗi tháng. Mục tiêu RTO 45 phút, RPO 5 phút. Dữ liệu khách hàng phải truy cập private; audit cần lưu 12 tháng. Đây là dữ kiện mô phỏng.

### Nhiệm vụ 1 — Xác định yêu cầu

Viết danh sách yêu cầu bắt buộc: engine/version/extension, data residency, private access, TLS, IAM, HA, backup/PITR, RTO/RPO, query latency, connection, storage growth và ngân sách.

### Nhiệm vụ 2 — Lập ma trận trách nhiệm

Với từng hạng mục, gán rõ:

- Nhà cung cấp thực hiện.
- Platform team cấu hình.
- Database/backend team kiểm chứng.
- Security phê duyệt.
- Data owner chịu trách nhiệm chính sách.

Không để các mục như “backup”, “security” hoặc “monitoring” chỉ có một ô chung chung; tách khả năng nhà cung cấp cung cấp và công việc khách hàng phải thực hiện.

### Nhiệm vụ 3 — Thiết kế HA/DR

Chọn topology phù hợp, nêu cách failover, backup/PITR, cross-region copy nếu cần và các bước phục hồi. Mô tả cách thử RTO/RPO. Xác định sự cố nào HA xử lý, sự cố nào cần restore hoặc DR.

### Nhiệm vụ 4 — Xây kế hoạch maintenance

Định nghĩa version policy, maintenance window, staging test, backup trước nâng cấp, theo dõi và rollback/recovery.

### Nhiệm vụ 5 — Tính TCO

Liệt kê compute, storage, IOPS, backup 12 tháng, replication, egress, monitoring, support/license, staging/DR và công vận hành. So sánh VM tự quản với managed DBaaS theo tải cơ sở và tải cao điểm.

### Nhiệm vụ 6 — Kiểm thử portability

Export schema/data, role và các đối tượng database; thử restore sang môi trường độc lập hoặc phiên bản tương thích khác. Liệt kê extension, SQL behavior và công cụ nào tạo lock-in.

### Deliverables

| Đầu ra | Nội dung |
| --- | --- |
| Service shortlist | 2–3 lựa chọn, các gate loại bỏ và lý do |
| Responsibility matrix | Owner/RACI theo từng lớp |
| HA/DR plan | Sơ đồ, RTO/RPO và failure scenarios |
| Security plan | IAM, network, TLS, key, audit, retention |
| Maintenance plan | Version, patch, test, approval và recovery |
| Cost model | TCO 12–36 tháng, giả định và độ nhạy |
| Validation plan | Load, failover, restore, access và export test |
| ADR | Bối cảnh, phương án, quyết định, hệ quả và trigger review |

## 15. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi cho managed database |
| --- | --- |
| **Operational Excellence** | Có owner, runbook, maintenance plan, version inventory, IaC, cảnh báo và restore drill không? |
| **Security** | Ranh giới provider/customer rõ? IAM least privilege, private network, TLS, key, audit và retention đúng không? |
| **Reliability** | HA, backup, restore, RTO/RPO, failover, quota và dependency đã được thử? |
| **Performance Efficiency** | Engine fit workload, query/index/connection/IOPS được đo ở peak và replica lag được kiểm soát? |
| **Cost Optimization** | TCO gồm standby, backup, egress, logs, support, staging và labor? Có cảnh báo tăng trưởng? |
| **Sustainability** | Sizing phù hợp, retention hợp lý, tránh replica/backup thừa và query kém hiệu quả không? |

## 16. Những sai lầm thường gặp

**Cho rằng managed nghĩa là không cần DBA hoặc owner dữ liệu.** Vẫn cần người thiết kế schema, query, access, backup policy và phục hồi.

**Cho rằng backup do nhà cung cấp chạy là đủ.** Phải chọn retention, encryption, quyền restore và thực hiện restore drill.

**Đồng nhất HA với DR.** HA xử lý một số lỗi thành phần/zone; DR giải quyết sự cố lớn hơn như mất region hoặc dữ liệu bị hỏng diện rộng.

**Không đọc version và maintenance policy.** Dịch vụ có thể thay đổi engine, giới hạn hoặc ngừng hỗ trợ version; ứng dụng cần compatibility test.

**Mở public access cho tiện.** Private network, identity và TLS cần được cấu hình theo ranh giới tin cậy.

**Dùng quyền admin cho ứng dụng.** Tài khoản runtime nên có quyền tối thiểu theo operation.

**Scale ứng dụng mà không tính connection.** Nhiều replica có thể làm cạn max connection của database.

**Dùng read replica mà không xem replication lag.** Query cần dữ liệu mới nhất có thể đọc stale data.

**So sánh giá chỉ bằng compute/hour.** Backup, HA, IOPS, egress, support và nhân công có thể đổi kết quả TCO.

**Không có kế hoạch thoát.** Khi cần đổi engine/region, extension, backup format và egress có thể tạo chi phí lớn.

**Không thử failover/restore.** Tính năng trong console không chứng minh ứng dụng hoạt động khi sự cố xảy ra.

## 17. Checklist trước khi đưa managed database vào production

- [ ] Workload, engine, consistency, transaction và access pattern được xác định.
- [ ] Nhà cung cấp, tier/SKU, region, version và quota đáp ứng yêu cầu bắt buộc.
- [ ] Ma trận trách nhiệm tách rõ provider, platform, application, security và data owner.
- [ ] IAM/service identity và database roles theo least privilege; secret có rotation.
- [ ] Database private, firewall/route/TLS và truy cập quản trị được kiểm soát.
- [ ] Encryption at rest/in transit, key ownership, backup encryption và audit được xác nhận.
- [ ] HA topology, failover behavior và capacity còn lại sau lỗi đã được thử.
- [ ] Backup, PITR, retention, cross-account/region copy và restore runbook đã được thiết lập.
- [ ] RTO/RPO được đo bằng restore/failover drill; không chỉ dựa trên mô tả dịch vụ.
- [ ] Version/patch/maintenance window, compatibility test và recovery plan được ghi.
- [ ] Connection pool, query, index, IOPS, storage growth, replication lag và quota được giám sát.
- [ ] Dashboard/alert bao gồm service metric, application metric và business SLI.
- [ ] TCO tính compute, storage, backup, replica, egress, monitoring, support và labor.
- [ ] Export/restore, portability và vendor lock-in được đánh giá.
- [ ] Migration/cutover/rollback có validation và reconciliation.
- [ ] Có owner, runbook, support path, ADR và điều kiện review định kỳ.

Managed database chuyển giao một phần công việc nền tảng cho nhà cung cấp, giúp đội ngũ tập trung hơn vào sản phẩm và dữ liệu. Nhưng **trách nhiệm về tính đúng đắn, quyền truy cập, phục hồi, hiệu năng, chi phí và tuân thủ vẫn cần được quản lý ở phía khách hàng**. Lựa chọn tốt không chỉ là dịch vụ có nhiều tính năng, mà là dịch vụ có ranh giới trách nhiệm rõ, phù hợp workload và được kiểm chứng bằng những bài thử thực tế: truy cập, tải, failover, restore, maintenance và export dữ liệu.
