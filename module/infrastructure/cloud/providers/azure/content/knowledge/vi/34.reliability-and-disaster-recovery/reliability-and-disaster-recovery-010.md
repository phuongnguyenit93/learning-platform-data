# Thiết kế phục hồi dữ liệu phù hợp từng dịch vụ

Một ứng dụng thương mại điện tử trên Microsoft Azure có API chạy ở Azure App Service hoặc Azure Kubernetes Service (AKS), đơn hàng lưu trong Azure SQL Database, giỏ hàng trong Azure Cosmos DB, hóa đơn PDF trong Azure Blob Storage, tệp chia sẻ qua Azure Files, thông điệp trong Azure Service Bus và khóa bí mật trong Azure Key Vault. Khi một người vận hành xóa nhầm đơn hàng, khi mã độc sửa hàng nghìn tệp, hoặc khi toàn bộ region không sẵn sàng, **không có một nút “khôi phục Azure” duy nhất** đưa toàn bộ hệ thống trở lại trạng thái nhất quán.

Mỗi dịch vụ có mô hình lưu trữ, cơ chế sao lưu và cách phục hồi riêng. Với Azure SQL, bạn có thể cần point-in-time restore (PITR) tới một cơ sở dữ liệu mới; với Blob Storage có thể là versioning/soft delete, backup hoặc sao chép sang nơi khác; với Service Bus, khả năng khôi phục **message bodies** không tương đương khôi phục cấu hình namespace; với Redis cache, cách phù hợp đôi khi chỉ là tái dựng từ nguồn dữ liệu chính. **Thiết kế phục hồi dữ liệu phù hợp từng dịch vụ** có nghĩa là chọn một tập cơ chế, thứ tự, trách nhiệm và bằng chứng kiểm thử đáp ứng giá trị nghiệp vụ và những dạng sự cố thực tế.

Bài học thuộc chương **Độ tin cậy và khôi phục thảm họa** của mô-đun **CLOUD_PROVIDERS_AZURE**. Nội dung kết nối các kiến thức Azure từ subscription, resource group, Microsoft Entra ID, mạng ảo, compute, lưu trữ và cơ sở dữ liệu đến triển khai, giám sát, bảo vệ và chi phí. Phạm vi bao gồm thiết kế trên Azure, tình huống thực tế, lệnh kiểm tra/lab an toàn, runbook và tiêu chí diễn tập.

**Giới hạn:** mọi tên subscription, resource group, tài nguyên, số phút và chi phí trong ví dụ đều là giả định. Không chạy thao tác delete, restore, failover hoặc thay đổi chính sách backup trên production khi chưa có approval. Tính năng, retention, region, tier, SKU và Azure CLI thay đổi theo thời gian; trước khi triển khai phải kiểm tra tài liệu chính thức tương ứng với đúng dịch vụ, subscription và region.

## 1. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Phân biệt mất dữ liệu logic, xóa nhầm, corruption, ransomware, hỏng ứng dụng, hỏng zone, mất region và xâm nhập tài khoản.
2. Giải thích **RPO, RTO, RLO**, durability, availability, data consistency, backup retention và recovery point.
3. Phân biệt **backup, snapshot, versioning, soft delete, replication, failover, restore và replay**.
4. Phân loại dữ liệu thành nguồn sự thật (system of record), dữ liệu dẫn xuất, cache, event log và metadata cấu hình.
5. Lập **ma trận dịch vụ × dạng lỗi × cơ chế bảo vệ × RPO/RTO × giới hạn khôi phục**.
6. Thiết kế Azure SQL Database PITR, long-term retention, geo-restore và active geo-replication/failover groups đúng mục đích.
7. Phân biệt khôi phục Azure SQL Managed Instance, Managed Instance link/Failover group và khôi phục cấp database theo khả năng hỗ trợ.
8. Lựa chọn backup, zone-redundant HA, PITR và geo-restore cho Azure Database for PostgreSQL/MySQL Flexible Server.
9. Phân biệt backup **periodic** và **continuous** trong Azure Cosmos DB, multi-region replication và change feed.
10. Chọn Blob soft delete, versioning, container recovery, replication, operational/vaulted backup và immutability phù hợp.
11. Hiểu những ràng buộc riêng của **ADLS Gen2**, Azure Files snapshots/backup và Managed Disks/VM backup.
12. Bảo vệ stateful workloads trên AKS: manifests/IaC, volumes, databases bên ngoài và consistency.
13. Thiết kế phục hồi Azure Service Bus, Event Hubs, Azure Queue Storage theo khả năng tái tạo/replay dữ liệu thực.
14. Phục hồi cache Redis, Key Vault secrets/keys và Azure App Configuration khi bị thay đổi hoặc xóa nhầm.
15. Định nghĩa cách khôi phục dữ liệu trong ETL/data lake/Synapse/Databricks/Delta khi các bảng và nguồn có thời điểm khác nhau.
16. Thiết kế thứ tự phục hồi xuyên dịch vụ, bảo vệ identity/network/encryption keys, kiểm thử integrity và đối soát side effects.
17. Xây dựng runbook điều tra, khôi phục, rollback/failforward, diễn tập và bằng chứng RPO/RTO.
18. So sánh chi phí tăng retention/geo redundancy với rủi ro mất dữ liệu và thời gian ngừng phục vụ.

## 2. Xác định đúng loại sự cố trước khi chọn công cụ

### 2.1. Những nhóm sự cố khác nhau

| Sự cố | Điều xảy ra | Cơ chế ưu tiên cần đánh giá |
|---|---|---|
| Xóa nhầm một record | DELETE hoặc API lỗi | PITR/restore tách biệt, logical replay |
| Deploy phiên bản ghi sai dữ liệu | Corruption lan tới nhiều records | Backup trước lỗi, khôi phục chọn lọc và reconciliation |
| Xóa nhầm Blob/file | Object không còn ở active view | Soft delete, versions/snapshots, backup |
| Ghi đè object | Nội dung mới thay bản cũ | Versioning/snapshots, PITR nếu supported |
| Ransomware hoặc credential bị lộ | Dữ liệu và bản sao online có thể bị sửa/xóa | Immutability, isolated recovery copy, revoke credentials |
| Disk/VM hỏng | Mất hệ điều hành hoặc dữ liệu local | Disk snapshots, Azure Backup, image/IaC rebuild |
| Availability Zone lỗi | Một zone không hoạt động | Zone-redundant architecture/HA, failover có kiểm thử |
| Region outage | Service/region chính không truy cập được | Cross-region architecture, geo replication, geo backup/restore |
| Hỏng key/secret/config | App không giải mã hoặc không kết nối | Key Vault recovery, version history, config export/IaC |
| Broker namespace mất | Queue/topic không sẵn hoặc message state không còn | Service-specific DR, producers retry, durable event archive |
| Replication lag/silent corruption | Bản sao nhận dữ liệu sai từ primary | Independent restore point, phát hiện và isolate |
| Sai quyền mạng/Entra | Dữ liệu còn nhưng workload không đọc được | Restore IAM/DNS/VNet/identity, không restore DB vô ích |

**Một bản replica luôn đồng bộ hoặc gần đồng bộ có thể sao chép cả lệnh DELETE sai.** Vì vậy replica/HA xử lý availability không thay thế backup phục hồi về thời điểm trước lỗi.

### 2.2. Sơ đồ định hướng

~~~mermaid
flowchart TD
    A["Dữ liệu / dịch vụ có sự cố"] --> B{"Data bị mất/sai hay chỉ inaccessible?"}
    B -->|"Không truy cập"| C["Kiểm tra identity, DNS, network, HA, region"]
    B -->|"Bị xóa / sai"| D{"Có điểm khôi phục độc lập?"}
    D -->|"Có"| E["Restore cô lập + verify integrity"]
    D -->|"Không"| F["Replay nguồn tin cậy / recovery từ đối tác"]
    C --> G{"Primary trở lại kịp RTO?"}
    G -->|"Có"| H["Failback / sửa hạ tầng"]
    G -->|"Không"| I["Failover/geo-restore theo thiết kế"]
    E --> J["Reconcile trạng thái liên dịch vụ"]
    F --> J
    I --> J
    H --> J
    J --> K["Canary, kiểm tra business, mở traffic"]
~~~

Thứ tự quan trọng: **không restore cơ sở dữ liệu nếu vấn đề thực chỉ là Private DNS hoặc managed identity bị thu hồi**. Ngược lại, không failover sang replica khi replica đã sao chép dữ liệu bị corruption.

## 3. Những thuật ngữ bắt buộc phân biệt

### 3.1. Recovery Point Objective (RPO)

**RPO** là mức mất dữ liệu tối đa mà doanh nghiệp chấp nhận, tính theo khoảng cách giữa thời điểm sự cố và thời điểm dữ liệu được khôi phục.

~~~text
Sự cố xảy ra 10:00
Điểm dữ liệu có thể phục hồi gần nhất 09:55

Observed potential data loss window:
  10:00 - 09:55 = 5 phút

Nếu mục tiêu RPO = 15 phút:
  5 phút <= 15 phút → đạt mục tiêu RPO (riêng ví dụ này).
~~~

Không nhầm RPO với **backup schedule**: backup mỗi 15 phút không bảo đảm RPO đúng 15 phút trong mọi sự cố nếu backup bị lỗi, xuất hiện lag hoặc thời điểm khả dụng khác. Với asynchronous geo-replication, data loss sau forced failover phụ thuộc replication lag thực.

### 3.2. Recovery Time Objective (RTO)

**RTO** là thời gian mục tiêu để dịch vụ hoặc năng lực nghiệp vụ trở lại mức hoạt động đã thỏa thuận sau khi gián đoạn.

~~~text
Incident bắt đầu: 10:00
Thời điểm kiểm tra nghiệp vụ pass: 10:42
Observed recovery time = 42 phút

Nếu RTO mục tiêu = 60 phút:
  42 phút <= 60 phút → đạt trong buổi diễn tập.
~~~

Thời gian chạy lệnh restore xong **không phải lúc ứng dụng được phục hồi**. RTO phải tính thêm nhận diện sự cố, approval, khôi phục identity/network, deploy, warm-up, integrity checks và mở traffic.

### 3.3. Recovery Level Objective (RLO)

**RLO** biểu diễn mức dịch vụ tối thiểu cần khôi phục tại thời điểm RTO:
- Toàn bộ hệ thống như trước?
- Chỉ khả năng nhận đơn hàng, còn reports có thể chậm?
- Chỉ đọc được dữ liệu lịch sử, chưa chấp nhận writes?
- Có cần tính năng thanh toán hay tạm lưu orders để xử lý sau?

RTO 30 phút cho “API trả HTTP 200” không đồng nghĩa RTO 30 phút cho **người dùng đặt và thanh toán đơn hàng thành công**. Định nghĩa RLO giúp tránh tuyên bố đã DR thành công khi business capability còn hỏng.

### 3.4. Retention, frequency, granularity

- **Retention:** giữ bản phục hồi bao lâu (ví dụ 7 ngày, 35 ngày, 1 năm).
- **Recovery granularity:** mức cần lấy lại — toàn database, container, table, row, file, Blob, snapshot hay version.
- **Recovery point frequency:** các thời điểm thực tế có thể chọn hoặc mức liên tục được hỗ trợ.
- **Backup window:** thời gian tạo/ghi nhận bản sao.
- **Restore throughput:** tốc độ đọc bản backup, truyền dữ liệu và dựng tài nguyên đích.
- **Integrity:** dữ liệu khôi phục có hợp lệ/đầy đủ với nghiệp vụ không.
- **Isolation:** bản khôi phục có thể được tạo trong vùng sạch, tránh lây corruption/malware không.

### 3.5. RPO, RTO và tính nhất quán là ba mục tiêu khác nhau

Một cơ chế có RPO nhỏ không chắc có RTO nhỏ, và ngược lại:
- Geo-replica có thể cutover nhanh nhưng chứa dữ liệu sai đã replicated.
- Backup PITR có thể phục hồi đúng thời điểm trước lỗi nhưng mất lâu để dựng database lớn.
- Snapshot volume nhanh nhưng không đảm bảo transaction của database đã flush nếu không quiesce.
- Restore nhiều dịch vụ về cùng timestamp không tự động đảm bảo business transaction liên dịch vụ được committed đồng thời.

## 4. Backup, replication, snapshots, soft delete: so sánh rõ

| Cơ chế | Phục hồi xóa/sửa nhầm | Phục vụ lỗi region | Mức độc lập | Hạn chế điển hình |
|---|---|---|---|---|
| **Automatic managed backup/PITR** | Có theo retention/khả năng | Tùy geo-backup support | Recovery point trước lỗi | Restore duration, scope, retention |
| **Long-term retention backup** | Có ở những recovery points được giữ | Theo nơi lưu bản backup | Lưu lâu phục vụ compliance | Khoảng cách điểm khôi phục lớn hơn |
| **Snapshot** | Có, theo thời điểm | Tùy vùng/replication của snapshot | Snapshot-level | Có thể crash-consistent, không app-consistent |
| **Blob/file versioning** | Có cho object versions | Theo redundancy và feature hỗ trợ | Object-level | Không bảo vệ mọi container/account settings |
| **Soft delete** | Có trong retention window | Tùy loại resource/region | Khôi phục sau delete | Không phải backup cách ly hoàn chỉnh |
| **Zone redundancy/HA** | Thường không đối với logical delete | Zone failure, không phải full region | HA/replicas | Đồng bộ corruption |
| **Geo-replication** | Không nên xem là backup | Có, theo tier/lag | Replica còn phục vụ | Async data loss và failover complexity |
| **Continuous backup** | Có nếu PITR trong window | Theo dịch vụ, region/tier | Point-in-time | Restore scope/target/constraints |
| **Export/ETL replay** | Tùy sự kiện được lưu | Có nếu archive ở nơi khác | Independent event/data copy | RPO phụ thuộc archive và logic replay |
| **IaC/GitOps** | Với metadata/cấu hình | Có nếu artifacts/permissions sẵn | Code-defined state | Không phục hồi business data |

### 4.1. Quy tắc 3-2-1 nên hiểu như nguyên tắc, không phải tính năng mặc định

Một nguyên tắc quản trị thường được dùng: giữ nhiều bản sao độc lập, lưu ở các failure domains khác nhau và có ít nhất một bản được bảo vệ khỏi xóa/sửa của principal đang chạy production. Azure managed services có thể cung cấp nhiều bản sao nội bộ nhưng **không đồng nghĩa tổ chức tự động đạt một chiến lược 3-2-1 đầy đủ**. Cần đánh giá:
- Ai có quyền xóa tất cả bản?
- Khôi phục được nếu account/subscription bị chiếm quyền không?
- Có bản immutable/offline hoặc isolation tương đương theo yêu cầu không?
- Có thể phục hồi nếu key dùng để giải mã bị mất không?
- Bản sao có nằm cùng region hoặc cùng hệ thống kiểm soát quyền?
- Đã thử restore thực tế chưa?

### 4.2. Replication không thay backup

~~~mermaid
flowchart LR
    APP["Ứng dụng lỗi thực hiện DELETE"] --> PRIMARY["Primary database"]
    PRIMARY -->|"Replication"| SECONDARY["Geo replica"]
    PRIMARY -. "Delete đã replicate" .-> SECONDARY
    BACK["PITR / isolated backup"] -->|"Restore trước DELETE"| REC["Recovery database"]
~~~

Với availability failover, có thể chuyển tới secondary. Với corruption/delete, secondary nhiều khả năng cũng chứa dữ liệu lỗi. Một **restore point trước lỗi** hoặc archive độc lập mới là cứu cánh.

## 5. Lập data inventory và ma trận quyết định

### 5.1. Hỏi gì trước khi chọn giải pháp?

Với mỗi dataset, ghi:
1. **Business owner** và data classification.
2. Data source of truth hay derived/cache?
3. Azure resource, region, subscription, zone, SKU/tier?
4. Loại thao tác ghi, số writes/giây, kích thước và tăng trưởng?
5. RPO/RTO/RLO, bao gồm quy định pháp lý về lưu trữ?
6. Nguy cơ nổi bật: delete, overwrite, ransomware, region outage?
7. Retention và granularity mong muốn: row, table, object, database?
8. Cơ chế backups/HA/replication hiện có và ai có quyền thay?
9. Dependencies cần khôi phục trước: Key Vault, Entra, DNS, ACR, network?
10. Có tool, script, kiểm thử integrity và runbook được chứng minh chưa?

### 5.2. Ma trận một ứng dụng giả định

| Dữ liệu | Vai trò | Mục tiêu RPO | Mục tiêu RTO | Cơ chế ứng viên |
|---|---|---|---|---|
| Orders trong Azure SQL | System of record | 5 phút | 1 giờ | PITR + HA/geo options, replay đối soát |
| Cart trên Cosmos DB | Business state | 15 phút | 2 giờ | Continuous backup, multi-region theo tier |
| Invoice PDFs trên Blob | Chứng từ | 1 giờ | 4 giờ | Versioning, soft delete, backup, immutability |
| Shared documents Azure Files | Tài liệu nội bộ | 24 giờ | 8 giờ | Snapshots/Backup và restore kiểm thử |
| Service Bus commands | Công việc cần xử lý | Tùy event contract | 2 giờ | Outbox, replay source, DR service support |
| Redis cache | Derived state | Không áp RPO nghiệp vụ | 30 phút | Rebuild/warm, optionally persistence |
| Key Vault secrets/keys | Dependency của phục hồi | Không mất current và lịch sử cần thiết | 1 giờ | Soft delete/purge protection, IaC, recovery |
| AKS manifests | Runtime config | Bản Git gần nhất | 1 giờ | GitOps/IaC, image digests, cluster rebuild |
| Analytics aggregates | Derived/reporting | 24 giờ | 24 giờ | Data lake snapshots/Delta logs, replay ETL |

Các mục tiêu trên **chỉ là giả định để thực hành**, không phải SLA của Azure hay guarantee của từng cơ chế. Nếu RPO Orders=5 phút mà backup/replication thực tế không hỗ trợ hoặc khôi phục không đạt, phải **thay kiến trúc, giảm RPO kỳ vọng hoặc tái thương lượng SLO**.

### 5.3. Chọn nguồn phục hồi theo loại dữ liệu

- **Source of truth:** thường cần backup/PITR, protected copies và transaction integrity.
- **Derived data/materialized view:** có thể rebuild từ source nếu source còn đầy đủ và ETL deterministic.
- **Cache:** xóa cache + warm từ source là bình thường; đừng đối xử như database chính.
- **Event log/queue:** cần chiến lược replay, checkpoint, idempotency và event retention.
- **File/object:** cần versioning, deleted-object recovery và immutable retention nếu bắt buộc.
- **Config/identity:** phục hồi policy/IaC/keys, không chỉ dữ liệu.
- **Temporary/scratch data:** có thể chấp nhận mất hoàn toàn, miễn documented.



## 6. Redundancy theo zone và region trên Azure

### 6.1. Những failure domains

Một kiến trúc Azure cần xem:
- **Process/Pod/VM:** lỗi một đơn vị compute.
- **Availability Zone (AZ):** lỗi trung tâm dữ liệu/zone trong region hỗ trợ.
- **Region:** mất phần lớn dịch vụ trong một địa lý.
- **Subscription/account boundary:** xóa/sửa resource hoặc identity mất quyền.
- **Administrative/security boundary:** tài khoản người vận hành hay automation bị chiếm quyền.
- **Data corruption boundary:** cùng dữ liệu sai có thể được replicate khắp nơi.

Không phải mọi Azure region có cùng số Availability Zones hoặc mọi SKU hỗ trợ zone redundancy. Phải kiểm tra dịch vụ/region/tier cụ thể.

### 6.2. LRS, ZRS, GRS và RA-GRS cho Azure Storage

| Tùy chọn Storage | Mục tiêu | Điểm cần nhớ |
|---|---|---|
| **LRS** | Bản sao trong một physical location/region | Không bảo vệ hỏng toàn region |
| **ZRS** | Sao chép đồng bộ giữa các zones trong region hỗ trợ | Không phải cross-region DR |
| **GRS** | Lưu bản sao ở region phụ bằng asynchronous replication | Forced failover có nguy cơ mất dữ liệu chưa replicate |
| **RA-GRS** | Như GRS và cho phép đọc dữ liệu ở secondary theo giới hạn | Secondary thường read-only trước failover |
| **GZRS** | Zone redundancy primary + async geo copy | Khả năng và giá theo region/SKU |
| **RA-GZRS** | GZRS và quyền đọc secondary | Không phải synchronous cross-region writes |

Ví dụ một Blob bị xóa nhầm: deletion là thay đổi logic bình thường được replication; Storage GRS **không thay thế** soft delete/versioning/backup. Secondary có thể có replication lag; không thiết kế RPO=0 chỉ vì đã bật GRS.

### 6.3. Last Sync Time không phải cam kết zero data loss

Với geo-redundant Storage, các thông tin về trạng thái replication và **Last Sync Time** (nếu tài nguyên/loại redundancies cung cấp) giúp đánh giá mức dữ liệu có khả năng đã replicated. Một **customer-managed failover** trong tình huống primary không sẵn sàng có thể làm mất writes xảy ra sau thời điểm đồng bộ cuối. Secondary không mặc định writable trước khi được failover theo thủ tục.

Không gọi failover trước khi:
1. Xác định thực sự là region outage chứ không phải DNS/IAM.
2. Đo replication status/lag theo khả năng dịch vụ.
3. Xin xác nhận business về potential data loss.
4. Hiểu ảnh hưởng đến endpoint/account topology.
5. Chuẩn bị application reconnection và downstream consistency.
6. Có kế hoạch failback và vận hành sau failover.

### 6.4. Zone failover khác geo-restore

- **Zone-redundant HA** thường giảm gián đoạn hạ tầng cùng region.
- **Geo-replica/failover group** cung cấp khả năng chuyển traffic sang region khác, theo tính năng của dịch vụ.
- **Geo-restore từ backup** dựng dữ liệu tại nơi khác, thường mất nhiều thời gian hơn failover sang một replica đang nóng.
- **PITR/retention** nhắm vào sai dữ liệu logic, thường cần chọn recovery point trước lỗi.

Thiết kế có thể cần **cả HA, DR và backup**: ba mục tiêu khác nhau.

## 7. Các nguyên tắc backup chung cho Azure managed services

### 7.1. Phạm vi bảo vệ phải bao gồm cả metadata và dependencies

Backup của một database có thể giữ tables nhưng không giữ:
- Network/Private Endpoint/DNS.
- Microsoft Entra applications/role assignments.
- Managed identities/principals.
- Key Vault access/network policies.
- CI/CD artifacts và container image digest.
- API Management routes hoặc Front Door origin settings.
- Application configuration/feature flags.
- SQL server-level logins hoặc secrets bên ngoài database, tùy loại service.

**Recovery plan phải có Infrastructure as Code và runbook rebuild control plane**, đồng thời bảo vệ secrets/keys và cấp quyền tối thiểu.

### 7.2. Schedule và retention phải theo RPO

Cần tính riêng:
- Độ mới của recovery point.
- Backup successful hay chỉ đã schedule.
- Khoảng trễ backup/replication.
- Backup location và khả năng sẵn có khi primary region lỗi.
- Thời gian cần copy/dựng dữ liệu lớn.
- Retention và legal hold.
- Phục hồi chọn lọc một object/row được không?
- Restore có tạo **resource mới** hay ghi đè?
- Backup có bị principal production xóa/đổi retention được không?

Một backup hằng ngày không đáp ứng RPO 15 phút cho order database. Nhưng nó có thể đủ cho tệp hướng dẫn nhân sự thay đổi theo tuần.

### 7.3. Retention không đồng nghĩa immutability

- **Backup retention:** có thể chọn điểm khôi phục trong thời gian giữ.
- **Soft delete:** cho khoảng khôi phục trước khi xóa vĩnh viễn theo chính sách.
- **Immutability/WORM:** chống sửa/xóa bản đã bảo vệ trong retention theo chế độ khóa/chính sách.
- **Resource locks:** giúp tránh thao tác quản trị vô ý, không phải rào chắn toàn diện trước mọi quyền hoặc API data-plane.
- **RBAC/PIM/MFA:** giới hạn ai có thể delete, purge, disable backup hoặc thay retention.

Thiết kế chống ransomware nên tách quyền app (chỉ ghi business objects cần thiết) khỏi quyền backup admin, dùng immutable/isolated copies khi có hỗ trợ và diễn tập restore trong môi trường sạch.

### 7.4. Encryption và khóa

Backup được mã hóa không có nghĩa người phục hồi chắc chắn giải mã được. Nếu dùng customer-managed keys (CMK), Key Vault/HSM key bị mất hoặc bị purge có thể làm dữ liệu backup hoặc replica không đọc được tùy service.

Ghi rõ:
- Key identifier/version nào được sử dụng.
- Key Vault availability/geo design.
- Quyền đọc/unwarp của restore principal.
- Key rotation và retention strategy.
- Soft delete/purge protection/key backup khi khả năng hỗ trợ.
- Cách kiểm tra khôi phục khi primary identity/subscription bị lỗi.

Không lưu encryption key hoặc access token trong bài tập/recovery ticket.

### 7.5. Ghi nhận backup success và thử restore

Một bài kiểm tra đầy đủ không chỉ có “backup completed”:

~~~text
Backup succeeded → usable recovery point
  → Restore to isolated target
  → Validate object counts/checksums
  → Validate schema, indexes, constraints
  → Start app against restored data
  → Reconcile linked records/events
  → Measure RPO, RTO and observed data loss
  → Record PASS/FAIL and cleanup
~~~

Azure Monitor/Backup Center/Restore jobs là những nguồn trạng thái vận hành tùy dịch vụ. Một restore job “Succeeded” có thể vẫn chưa đạt tiêu chí nghiệp vụ như đủ tất cả hóa đơn của các orders đã thanh toán.

## 8. Azure SQL Database: PITR và khôi phục logic

### 8.1. Các cơ chế

**Azure SQL Database** có cơ chế tự động backups phục vụ point-in-time restore (PITR) trong thời gian giữ hỗ trợ. Dữ liệu backup cần thiết (full, differential, transaction log theo kiến trúc dịch vụ) được Azure quản lý. Các khả năng khác gồm:
- **Short-term retention (STR):** chọn recovery point gần hiện tại trong một khoảng ngày tùy tier/cấu hình, thường có giới hạn tối đa khoảng 35 ngày đối với nhiều service tiers.
- **Long-term retention (LTR):** giữ những bản backups được chọn theo tuần/tháng/năm, có thể tới nhiều năm khi dịch vụ hỗ trợ, nhằm compliance.
- **Geo-restore:** khôi phục từ geo-replicated backups vào region khác khi redundancy/capability và recovery point phù hợp.
- **Active geo-replication:** tạo readable geo-secondary asynchronous phục vụ region-level continuity.
- **Failover groups:** group databases/secondary và endpoint routing/failover management theo dịch vụ/tier.

Không phải tất cả tính năng/retention tùy chọn có mặt trên mọi database tier, deployment model hoặc region. Cần kiểm tra khả năng hiện hành trong Azure portal/CLI theo resource.

### 8.2. PITR là giải pháp chính cho DELETE nhầm

Tình huống:
- 09:40: application xóa 3.000 Orders do bug.
- 10:05: người vận hành phát hiện.
- Cần khôi phục Orders tại **09:39** để đọc dữ liệu trước lỗi.

Cách làm an toàn:
1. Giữ nguyên bản database hiện tại để không mất các giao dịch hợp lệ sau 09:40.
2. Chọn PITR **09:39 UTC**.
3. Restore sang **database mới** như orders_recovery_0939.
4. Hạn chế network/permission chỉ cho recovery operator.
5. So rows và business constraints giữa bản khôi phục và hiện tại.
6. Trích các records bị mất, **merge có kiểm soát** trở lại primary theo idempotency/transaction plan.
7. Kiểm tra foreign keys, payment and message state.
8. Không trỏ toàn bộ app production sang restored database nếu việc đó sẽ làm mất các orders hợp lệ từ 09:40 đến 10:05.
9. Ghi audit và postmortem.

**PITR trả về một database tại thời điểm trước**, không tự tạo một “UNDO DELETE 3.000 rows” trong production. Một recovery DB mới là nguồn đối soát.

### 8.3. Ví dụ Azure CLI xem metadata

Các lệnh sau không thực hiện restore:

~~~bash
RG="rg-orders-lab"
SERVER="sql-orders-lab"
DB="orders"

az sql db show \
  --resource-group "$RG" \
  --server "$SERVER" \
  --name "$DB" \
  --query "{name:name,status:status,edition:edition,backupStorageRedundancy:currentBackupStorageRedundancy}" \
  -o json

az sql db str-policy show \
  --resource-group "$RG" \
  --server "$SERVER" \
  --name "$DB" \
  -o json
~~~

CLI fields và command availability phụ thuộc Azure CLI version/API. Không in SQL admin password; viewer cần quyền ARM phù hợp, còn kết nối dữ liệu cần data-plane access.

### 8.4. PITR trong lab được phê duyệt

Giả định một SQL Database **lab**, có tên đích duy nhất chưa tồn tại:

~~~bash
RG="rg-orders-lab"
SERVER="sql-orders-lab"
SOURCE_DB="orders_lab"
RESTORED_DB="orders_lab_restore_20261120"

# Chỉ chạy ở LAB được phê duyệt; tạo database mới và phát sinh chi phí.
az sql db restore \
  --resource-group "$RG" \
  --server "$SERVER" \
  --name "$SOURCE_DB" \
  --dest-name "$RESTORED_DB" \
  --time "2026-11-20T09:30:00Z"
~~~

Recovery point phải nằm trong retention được hỗ trợ và trước sự cố. Lệnh tạo tài nguyên tính tiền; sau thử nghiệm cần cleanup đúng ownership. Không đặt restore destination trùng source database và không dùng production server làm lab khi chưa được phê duyệt. Restore duration phụ thuộc kích thước DB, tier, workload, log chain và dịch vụ.

### 8.5. Long-term retention (LTR) khác PITR

LTR hữu ích khi tổ chức phải khôi phục một bản dữ liệu sau 6–24 tháng hoặc lâu hơn; backup LTR thường là **các restore points rời rạc** theo chính sách, không cho phép chọn tùy ý từng giây trong nhiều năm. Muốn hồi phục một deletion xảy ra 09:40 sáng nay thì STR/PITR thường phù hợp hơn.

Cần test:
- LTR policy được cấu hình và đã sinh backup.
- Azure subscription/resource vẫn truy cập được backup.
- Đích restore region/server/tier phù hợp.
- Encryption/key access và identity đúng.
- Database không tạo rủi ro PII khi restore sang dev.
- Retention đáp ứng luật và chi phí.

### 8.6. Geo-replication/failover groups không thay PITR

Trong lỗi region, secondary đang sẵn có có thể giúp RTO thấp hơn geo-restore từ backup. Nhưng:
- Cross-region replication thường asynchronous, **RPO không mặc định bằng 0**.
- Forced failover có thể mất transaction chưa đến secondary.
- Delete/corruption có thể replicate sang secondary.
- Listeners/endpoints, app reconnection và firewall/Private DNS phải chuẩn bị.
- Các user/logins/server-level objects, jobs, alerts, configurations cần inventory và DR plan riêng theo deployment model.
- Sau failover phải verify dữ liệu đã commit/đối soát với logs, outbox, payment gateway.

Một cơ sở dữ liệu có active geo-replica nhưng không có tested PITR restore **vẫn có lỗ hổng trước lỗi logic**.

### 8.7. Temporal tables, CDC và audit logs

Một số ứng dụng dùng SQL temporal tables, change data capture (CDC), audit/event sourcing để khôi phục **mức row/table** nhanh hơn. Đây là các kỹ thuật ứng dụng/dữ liệu bổ sung, không thay backup:
- CDC retention có giới hạn.
- Temporal history có thể bị thay bởi principal đủ quyền.
- Audit logs thường không chứa đầy đủ dữ liệu để tự phục hồi.
- Replay phải idempotent và tuân thủ consistency constraints.
- SQL restore độc lập vẫn là phương án khi hệ thống bị xâm nhập sâu.

## 9. Azure SQL Managed Instance: lưu ý deployment model

**Azure SQL Managed Instance (MI)** có automatic backups/PITR và tùy chọn long-term retention/cross-region recovery theo khả năng. Nó có khác biệt với Azure SQL Database single/elastic pool:
- Tập tính năng SQL Server instance-level rộng hơn.
- VNet/private networking và DNS có thể quan trọng hơn cho failover.
- Instance provisioning và khôi phục backup kích thước lớn có thể mất nhiều thời gian.
- Failover groups/Managed Instance link khi khả năng hỗ trợ và SQL Server migration scenarios cần runbook riêng.
- SQL Agent jobs, logins, linked servers và instance-level settings có thể không đi cùng một database restore theo mong đợi.

### 9.1. Đánh giá phục hồi cấp database và cấp instance

| Nhu cầu | Cần xác minh |
|---|---|
| Xóa nhầm một table | PITR DB mới rồi merge, hoặc scripted recovery |
| MI instance outage | HA/service recovery theo tier/config |
| Region outage | Failover group/geo-restore, networking và endpoints |
| Instance config thất lạc | IaC/export metadata, jobs/logins scripting |
| Lỗi key/credential | Entra/SQL logins, Key Vault, TDE/CMK recovery |
| Di chuyển workload SQL Server | Support/limitations của MI link/backup restore model |

**Không áp trực tiếp CLI của Azure SQL Database single DB cho Managed Instance**; resource namespace và restore commands/permissions có khác. Dùng tài liệu MI chính thức theo version, và đo RTO bằng bài diễn tập cụ thể.

### 9.2. TDE, CMK và khôi phục

SQL TDE dùng service-managed keys hoặc CMK theo cấu hình. Nếu TDE protector/key không còn khả dụng, restore/geo-replica có thể gặp trở ngại. Backup key/soft delete/purge protection, cập nhật key access và test restore thuộc một thiết kế DR hoàn chỉnh.

## 10. PostgreSQL Flexible Server và MySQL Flexible Server

### 10.1. Khác biệt HA, PITR và backup

Đối với **Azure Database for PostgreSQL Flexible Server** và **Azure Database for MySQL Flexible Server**, các khả năng cần phân biệt:
- Automatic backups và retention window cho PITR.
- Restore thường tạo **server mới** tại recovery point theo service API, không đưa mọi kết nối production “quay ngược” ngay.
- **Zone-redundant HA** khi supported giúp hồi phục lỗi AZ, không thay PITR logic.
- **Read replicas** phục vụ đọc/DR tùy kiến trúc, có replication lag và có thể sao chép dữ liệu bị DELETE.
- **Geo-redundant backup/geo-restore** phụ thuộc tính năng, region/SKU và cấu hình/điều kiện tại thời điểm resource được tạo hoặc thay đổi.
- Bản sao cross-region có RPO/RTO khác local restore.

Không áp mặc định quy tắc của PostgreSQL cho MySQL hoặc ngược lại; retention, HA support, geo features và CLI có thể khác.

### 10.2. Ví dụ PostgreSQL đọc cấu hình

~~~bash
RG="rg-orders-lab"
PG="pg-orders-lab"

az postgres flexible-server show \
  --resource-group "$RG" \
  --name "$PG" \
  --query "{name:name,state:state,backup:backup,highAvailability:highAvailability,fullyQualifiedDomainName:fullyQualifiedDomainName}" \
  -o json
~~~

Backup metadata fields có thể được biểu diễn khác theo Azure CLI/API version. Đây là lệnh đọc; không xuất DB password hoặc connection string chứa secrets.

### 10.3. Một runbook PITR PostgreSQL

1. Xác định first bad write và chọn UTC recovery point.
2. Xác nhận điểm nằm trong backup retention.
3. Xác định target region, zone/HA, network/VNet và naming.
4. Tạo restored Flexible Server **mới**, không ghi đè source.
5. Restore firewall/Private DNS/roles/extensions/connection requirements theo deployment settings thực tế.
6. Kiểm tra schema, timezone, WAL/transaction consistency và dữ liệu.
7. Nếu cần, trích các tables/rows bị xóa và merge có kiểm soát.
8. Cập nhật application connection/Secrets nếu cutover toàn server.
9. Test connection pooling và sequence/identity values.
10. Theo dõi write correctness, replay/offset và dọn tài nguyên lab.

Một server được khôi phục là tài nguyên riêng; không tự gắn lại hoàn toàn DNS, monitoring, Private Endpoint, DB users, app secrets hoặc replication topology như ban đầu.

### 10.4. Đổi region và giới hạn khôi phục

Không giả định geo-redundant backups đã được bật vì server có HA. Một server có zone-redundant HA trong primary region vẫn có thể không có recovery copy ở region phụ. Ngược lại, có geo backups chưa chắc đạt RTO 15 phút nếu restore server lớn mất nhiều giờ.

Với MySQL Flexible Server, hãy kiểm tra riêng:
- Hỗ trợ backup redundancy và retention.
- Điểm khôi phục/time granularity.
- Geo restore capability và vùng tương thích.
- HA/replica topology và RPO lag.
- Engine version, database users/privileges và connection dependencies.

### 10.5. Database restore kiểm chứng bằng nghiệp vụ

Sau restore, ngoài row counts còn cần:
- Thử transaction read/write trên môi trường cô lập.
- Kiểm tra foreign keys, indexes, constraints, sequences.
- So các order/payment statuses.
- Kiểm tra replication/CDC/ETL connectors nếu đang dùng.
- Kiểm tra timezone, collation/charset, extensions.
- Xác minh credential/roles và performance.
- Không mở traffic production trước khi reconciliation.



## 11. Azure Cosmos DB: periodic backup, continuous backup và multi-region

### 11.1. Vì sao Cosmos DB cần thiết kế riêng?

Azure Cosmos DB có mô hình partitioned, globally distributed NoSQL, throughput RU/s, APIs và consistency. Backup/restore phụ thuộc **API, backup mode, tier và account configuration**. Một Cosmos DB account có multi-region replication không tự có khả năng khôi phục point-in-time theo ý muốn.

Câu hỏi cần trả lời:
- Account dùng API for NoSQL, MongoDB hoặc API khác?
- Backup mode là **Periodic** hay **Continuous**?
- Retention và granularity hỗ trợ cụ thể?
- Account có multi-region single-write hay multi-write?
- Có quyền restore resource cần thiết và recovery region được hỗ trợ?
- Container/partition keys, TTL, unique keys và indexes thế nào?
- Restore tạo **account mới** hay có scope đặc biệt theo API?
- Ứng dụng có logic đọc account mới và reconfigure connection không?

### 11.2. Periodic backup

**Periodic backup** giữ các recovery copies theo chu kỳ và retention đã cấu hình/dịch vụ hỗ trợ. Nó phù hợp với yêu cầu có thể chấp nhận khôi phục về một backup point rời rạc, không phải một timestamp tùy ý giữa các lần sao lưu.

Đặc điểm:
- Azure quản lý backup theo chính sách account.
- Backup frequency/retention có constraints.
- Restore flow/permissions không giống Azure SQL PITR.
- Có thể không khôi phục một document riêng trực tiếp từ portal; thường cần restore dữ liệu ra target khác và query/copy có kiểm soát.
- Backup đang tồn tại không nhất thiết có thể truy cập/đọc như một container bình thường.
- RPO tiềm năng phụ thuộc khoảng cách giữa successful backups.

### 11.3. Continuous backup và PITR

**Continuous backup** cho phép chọn một point-in-time trong retention window theo capabilities dịch vụ; với nhiều Cosmos DB API/account combinations có các tier retention như **7 hoặc 30 ngày** (cần xác minh options hiện hành theo API/tier).

Các lưu ý:
- Restore thường tạo **Cosmos DB account mới** thay vì đảo ngược nguyên account hiện tại.
- Có thể hỗ trợ khôi phục ở mức account/database/container tùy API, nhưng không phải "undo one JSON document" ở primary.
- Restore cần chọn timestamp hợp lệ, scope, target location và có thể cần account/resource identity mới.
- Hỗ trợ thay đổi backup mode, geographic location, unique keys và restore limitations phải được kiểm tra theo API/version cụ thể.
- Dữ liệu mới ghi sau timestamp chọn không tự hợp nhất vào account được restore.
- Thời gian dựng account/containers/indexes và RU capacity ảnh hưởng RTO/cost.

### 11.4. Ví dụ đọc backup policy

~~~bash
RG="rg-orders-lab"
ACCOUNT="cosmos-orders-lab"

az cosmosdb show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name,backupPolicy:backupPolicy,locations:locations,consistencyPolicy:consistencyPolicy}" \
  -o json
~~~

Lệnh đọc resource configuration; không in keys hoặc connection strings. Nếu backupPolicy bị rút gọn trong CLI, xem Azure portal/Terraform/ARM metadata trong phạm vi cho phép. Không thực hiện mode conversion nếu chưa đánh giá những hạn chế và irreversibility tương ứng.

### 11.5. Tình huống xóa nhầm container Cart

1. Application bug xóa toàn bộ carts vào 13:10.
2. Dừng tác nhân delete/sửa quyền trước khi restore.
3. Xác định recovery timestamp 13:09, backup mode và khả năng restore container.
4. Restore tới tài nguyên **cô lập** theo phương án Cosmos DB hỗ trợ.
5. Kiểm tra partition key paths, unique keys, indexes, TTL và counts.
6. Đối soát carts đã được khách cập nhật sau 13:10 qua event log nếu còn.
7. Tránh ghi đè carts hợp lệ bằng restore cũ.
8. Chuyển dữ liệu chọn lọc hoặc chuyển connection tới account mới theo approval.
9. Kiểm tra RU budget/throughput/capacity và consistency.
10. Theo dõi cart correctness, telemetry và đóng incident.

### 11.6. Multi-region consistency không phải backup

Cosmos DB hỗ trợ geo-distribution, read regions và một số mô hình multi-region writes. Tuy nhiên:
- Các thao tác delete/update sai có thể propagate sang các regions.
- Write conflict resolution khi multi-write có ảnh hưởng logic nghiệp vụ.
- Consistency levels (strong/bounded staleness/session/consistent prefix/eventual) là semantics đọc/ghi, không đảm bảo rollback deletes.
- Regional failover có thể thay latency, writes availability và consistency experience.
- RPO/RTO thực phụ thuộc architecture, failover policy, account mode và cross-region propagation.
- Không đưa giá trị dự kiến “zero data loss” nếu chưa có chứng minh theo setup cụ thể.

### 11.7. Change feed và replay

**Change feed** có thể hữu ích để:
- Duy trì read model/materialized view.
- Replay một số thay đổi cho downstream processor theo retention/mode.
- Xây audit/event log khi triển khai đúng.
- Phát hiện/cảnh báo thay đổi dữ liệu bất thường.

Nhưng **change feed không luôn chứa before-image hoặc mọi deletes** theo mọi mode, không thay continuous backup và không đủ để khôi phục arbitrary historical state nếu cần dữ liệu cũ. Cần hiểu mode, retention, checkpoint, TTL và loại thao tác được ghi.

### 11.8. Khi nào chọn Cosmos DB periodic hay continuous?

| Tình huống | Hướng cân nhắc |
|---|---|
| Cart state có thể rebuild, RPO 4 giờ | Periodic nếu đáp ứng SLA và chi phí |
| Orders document cần PITR gần timestamp xóa | Continuous backup khi API/region hỗ trợ |
| Chỉ cần tiếp tục sau region outage | Multi-region/failover phù hợp, **cộng backup độc lập** |
| Cần giữ 3 năm vì compliance | Xem requirements đặc thù lưu trữ/archive; continuous 7/30 ngày không đủ |
| Cần restore một document | Khôi phục tới target cô lập, truy vấn/merge document và liên kết |
| Cần repair bad mass update | PITR trước corruption, kiểm chứng và selective replay |

Không dùng backup mode duy nhất cho cả Cosmos DB account nếu dữ liệu thuộc nhiều business domains có RPO/retention khác nhau mà account mode không đáp ứng đồng thời; cân nhắc phân chia tài nguyên với chi phí phù hợp.

## 12. Azure Blob Storage: phiên bản, xóa mềm, backup và replication

### 12.1. Khác biệt giữa overwrite, delete, mất account và mất region

Một file PDF invoice ở Blob Storage có các dạng lỗi:
- **Overwrite:** blob name còn nhưng content sai.
- **Delete:** blob chuyển sang trạng thái deleted theo feature được bật.
- **Container deletion:** phạm vi lớn hơn từng blob.
- **Mass corruption:** hàng nghìn blobs bị mã độc thay đổi.
- **Storage account configuration lost:** RBAC, networking, lifecycle settings thay đổi.
- **Region outage:** endpoints không tới primary region.

Một tính năng đơn lẻ thường không giải quyết mọi dạng lỗi.

### 12.2. Blob versioning

Với account/loại Blob hỗ trợ, **Blob Versioning** giúp lưu các versions khi blob bị thay đổi/ghi đè; phục hồi có thể bằng cách chọn version cũ và copy/promote nội dung phù hợp.

Lưu ý:
- Tăng số phiên bản và storage cost.
- Lifecycle policies có thể xóa old versions; retention phải khớp SLA/compliance.
- Version ID cần được bảo vệ/audit nếu dùng làm evidence.
- Không tất cả Blob types và account configurations (nhất là HNS/ADLS Gen2) đều có feature set giống nhau.
- Versioning **không khóa immutable** nếu principal đủ quyền có thể xóa versions theo policy.
- Với concurrent writes, phải hiểu ETag/If-Match/conditional requests.

### 12.3. Blob soft delete và container soft delete

**Blob soft delete** giúp khôi phục deleted blobs/phiên bản theo retention khi bật trước sự cố. **Container soft delete** hỗ trợ phục hồi container đã xóa theo điều kiện của dịch vụ. Chúng có thể cần được cấu hình riêng.

| Tình huống | Kiểm tra |
|---|---|
| Một blob bị delete | Blob soft delete enabled/retention? |
| Một blob overwrite sai | Versioning/snapshot/Blob PITR? |
| Cả container bị delete | Container soft delete enabled/retention? |
| Hàng nghìn blobs lỗi logic | Operational/vaulted backup hoặc PITR/versions có khả năng restore hàng loạt? |
| Region outage | Storage redundancy/failover status và protected data |
| Attacker xóa versions | Immutable policy/isolated recovery copy? |

**Soft delete chỉ giúp nếu feature đã bật và thời điểm khôi phục còn trong retention.** Không bật nó *sau* sự cố rồi kỳ vọng dữ liệu trước đó tự trở lại.

### 12.4. Operational backup và vaulted backup cho blobs

Tùy loại account và dịch vụ/tier, **Azure Backup for Blobs** có những cách bảo vệ khác nhau:
- **Operational backup:** sử dụng những khả năng bảo vệ cục bộ của Storage account như point-in-time restore/soft delete/change feed/versioning theo supported matrix, không tương đương một bản sao độc lập trong Backup vault.
- **Vaulted backup:** lưu bản bảo vệ theo cơ chế Backup vault và policy hỗ trợ, tăng lựa chọn khôi phục/cách ly so với chỉ bảo vệ cục bộ.

Các tính năng cụ thể có hạn chế về account type, hierarchical namespace, regions, recovery granularity và restore location. Không tự gọi mọi Azure Blob backup là “snapshot trong vault” hoặc cho rằng vaulted backup có sẵn trên mọi HNS account.

### 12.5. Blob point-in-time restore và các điều kiện

Storage Blob point-in-time restore, khi account/Blob types hỗ trợ, giúp khôi phục trạng thái block blobs trong một khoảng thời gian nhất định. Nó thường phụ thuộc các tính năng dữ liệu hỗ trợ như versioning/change feed/soft delete và có điều kiện về account/tier/namespace.

Nếu một tài liệu nói “PITR 30 ngày” cần kiểm tra:
- Account đã bật các capabilities cần thiết từ trước khi xảy ra lỗi?
- Retention và earliest restorable timestamp hiện tại?
- Có objects unsupported không?
- Restore hoạt động trên tất cả blobs hay một tập/ranges?
- Trong khi restore, applications có phải dừng writes?
- Có cần bảo vệ last-known-good copy trước khi start restore không?
- Có đủ storage capacity và financial approval không?

### 12.6. Immutability/WORM đối với hóa đơn và compliance

Một số tài liệu kinh doanh phải được bảo vệ chống sửa/xóa trước retention date. **Azure Blob immutable storage** cung cấp time-based retention hoặc legal holds theo features hỗ trợ.

- Một policy đã lock có thể rất khó/không thể rút ngắn retention.
- Object bị ghi sai nhưng bị khóa có thể phải tạo **correction record mới**, không sửa bản gốc.
- Immutable storage có ràng buộc với versioning, container-level policies, HNS/account type.
- Không lock toàn bộ container test mà chưa có approval và hiểu khả năng xóa resource/cost.
- Encryption keys và IAM vẫn phải được bảo vệ.

**Immutability không bảo đảm dữ liệu đúng ngay khi ghi**; nếu ứng dụng ghi invoice sai và lock, cần quy trình rectification/offset records.

### 12.7. Ví dụ kiểm tra Storage account và blob protection

~~~bash
RG="rg-orders-lab"
SA="storderslab"

az storage account show \
  --resource-group "$RG" \
  --name "$SA" \
  --query "{name:name,sku:sku.name,kind:kind,isHnsEnabled:isHnsEnabled}" \
  -o json

az storage account blob-service-properties show \
  --resource-group "$RG" \
  --account-name "$SA" \
  --query "{blobDeleteRetention:deleteRetentionPolicy,containerDeleteRetention:containerDeleteRetentionPolicy,versioning:isVersioningEnabled,changeFeed:changeFeed}" \
  -o json
~~~

Lệnh chỉ đọc cấu hình; không liệt kê secret keys hay SAS. Các property names và CLI support có thể thay đổi theo CLI/API, nên xác minh output trên lab trước khi dùng logic tự động.

### 12.8. Khôi phục một invoice PDF bị ghi đè

1. Dừng process còn đang ghi sai.
2. Xác định blob URI, thời gian lỗi, ETag/version ID.
3. Xem versions/snapshots hoặc backup restore points còn hợp lệ.
4. Copy version cũ sang **tên mới trong container phục hồi** để kiểm tra trước.
5. Kiểm tra hash/size/metadata và PDF có thể mở được.
6. Đối chiếu invoice number, amount và order record.
7. Khi được phê duyệt, phục hồi vào đường dẫn chính hoặc update pointer trong DB.
8. Dùng conditional write để tránh ghi đè phiên bản hợp lệ đang tồn tại.
9. Kiểm tra CDN/cache/URL SAS nếu ứng dụng phân phối qua edge.
10. Ghi audit, alert và retention evidence.

Không tạo một **public SAS** để tải dữ liệu nhạy cảm chỉ để test restore. Nên dùng Entra/RBAC và quyền tối thiểu.

### 12.9. GRS failover không khôi phục dữ liệu sai

Một Storage account GRS có thể giúp recovery region-level theo capability và failover policy, nhưng delete/overwrite được replicate. Sau failover, account redundancy có thể bị thay đổi và cần tái cấu hình theo service guidance. Hãy lập DR procedure riêng cho data plane, backup, endpoints, DNS và billing.

## 13. ADLS Gen2: data lake và hierarchical namespace

### 13.1. ADLS Gen2 là Blob Storage có semantics khác

**Azure Data Lake Storage Gen2** dựa trên Azure Blob Storage với **hierarchical namespace (HNS)** cho paths/directories và filesystem operations. HNS ảnh hưởng cách đặt tên, rename/delete directories, ACLs và khả năng hỗ trợ một số data protection features.

Không sao chép checklist Blob GPv2 sang HNS account mà không kiểm tra:
- Versioning/soft delete/PITR có hỗ trợ cho **exact HNS configuration** không?
- Directory-level delete/rename được backup/restore như thế nào?
- POSIX-like ACLs/owner/group khôi phục cùng dữ liệu không?
- Azure Backup vaulted/operational backup hỗ trợ loại tài nguyên đó hay chưa?
- Event/Delta log/checkpoint files được giữ và liên kết cùng dữ liệu?
- Backup có bao phủ data lake access policies, network settings và container permissions?

### 13.2. Bronze–Silver–Gold và khả năng tái dựng

~~~mermaid
flowchart LR
    S["Sources / Event logs"] --> B["Bronze raw immutable"]
    B --> E["ETL / Spark"]
    E --> V["Silver curated"]
    V --> T["Aggregations"]
    T --> G["Gold serving tables"]
~~~

Nếu **Bronze raw** còn đầy đủ, Silver/Gold có thể tái dựng bằng pipeline code và versioned transformations — nhưng chỉ nếu:
- Source payload và schema versions còn lưu.
- Pipeline deterministic hoặc có ghi các external reference versions.
- Dữ liệu nhạy cảm/retention phù hợp.
- Có compute/capacity để replay trong RTO.
- Checkpoint, watermark và exactly-once assumptions được đánh giá.
- Tất cả secrets, catalogs, storage credentials và ACLs được tái dựng.

### 13.3. Delta Lake time travel khác backup

**Delta Lake** lưu transaction log và data files để đọc các versions trước theo retention. Tuy nhiên:
- VACUUM/retention cleanup có thể xóa files cần cho old versions.
- Nếu cả transaction logs hoặc underlying ADLS objects bị xóa/bị mã độc sửa, time travel có thể vô dụng.
- Time travel không bảo đảm khôi phục cross-region khi storage region mất.
- Một Delta table có thể khôi phục view cũ nhưng downstream systems đã dùng dữ liệu sai.
- Kiểm tra khả năng/giới hạn của version restoration trong platform dùng (Databricks, Synapse, OSS Delta).

Vì vậy cần **bảo vệ underlying storage + versioned pipeline code + checkpoints** chứ không chỉ phụ thuộc một câu lệnh time travel.

### 13.4. Restore ACLs và identities

Dữ liệu copy thành công nhưng ứng dụng không đọc được nếu:
- Entra principal object IDs thay đổi.
- ACLs của directories không được phục hồi.
- Private Endpoints/DNS chưa dựng.
- Managed identity/role assignments chưa sẵn.
- Filesystem/container paths hoặc external tables đổi.
- Customer-managed key không đọc được.

Recovery acceptance phải bao gồm **kết nối và quyền truy cập của workloads thật**, không chỉ total byte count.

## 14. Azure Files: snapshots, backup và SMB/NFS

### 14.1. Azure Files có mô hình sử dụng khác Blob

Azure Files cung cấp file shares truy cập qua **SMB** hoặc **NFS** theo tier/configuration. Một ứng dụng VM/AKS/desktop có thể mount share và ghi đồng thời.

Dạng lỗi thường gặp:
- Người dùng xóa thư mục/team share.
- Ransomware mã hóa nhiều file trên share.
- Share bị delete.
- Một ứng dụng ghi file sai khi users khác vẫn dùng.
- Mount mất do network/identity.
- Region outage.

### 14.2. Share snapshots

**Azure Files share snapshots** tạo recovery points của share theo tính năng được hỗ trợ. Có thể khôi phục từng file/directory hoặc restore toàn share theo tools/service.

Cần lưu ý:
- Snapshot **chỉ phản ánh trạng thái tại thời điểm chụp**.
- Snapshot không phải transaction-consistent với mọi app dùng file handles.
- Retention/limits/cost và policies ảnh hưởng bảo vệ.
- Không phải mọi protocol/tier/share type có cùng khả năng snapshot/restore.
- File locks, SMB ACLs/NFS permissions và mount clients cần kiểm chứng sau restore.

### 14.3. Azure Backup for Azure Files

Azure Backup có các mô hình **snapshot-based** và các khả năng vaulted backup được hỗ trợ tùy share type/tier/region/backup policy. Hãy kiểm tra:
- Recovery Services vault hoặc Backup vault được yêu cầu cho mode cụ thể.
- Share protocol SMB/NFS, Standard/Premium, provisioning model.
- Khả năng file-level vs share-level restore.
- Cross-region recovery availability và backup redundancy.
- Retention, soft delete, immutability support.
- Storage account IAM, firewall, private networking.
- RTO khi phục hồi hàng triệu files.

Không giả định “Azure Files đã bật Azure Backup” nghĩa là bản sao đã được lưu độc lập khỏi storage account ở region khác. **Snapshot backup** và **vaulted backup** có failure domain và protection semantics khác nhau.

### 14.4. Restore một folder do user xóa nhầm

1. Ngăn thao tác xóa/sửa tiếp.
2. Xác định share/path và thời điểm trước lỗi.
3. Xem available snapshot/backup recovery points.
4. Restore vào đường dẫn khác trước khi ghi đè live folder.
5. Kiểm tra file count, timestamps, ACLs, owners.
6. Thử đọc/ghi trên test client với đúng SMB/NFS identity.
7. Copy/merge vào live path theo approval.
8. Kiểm tra các ứng dụng có open file handles/cache.
9. Theo dõi lock conflicts và dữ liệu thay đổi sau thời điểm snapshot.
10. Ghi evidence, cleanup bản test và điều chỉnh policy.

### 14.5. Azure Files không thay database backup

Không dùng một SMB share snapshot để thay point-in-time restore của SQL Server/ PostgreSQL đặt file database trên share, trừ khi kiến trúc/công cụ hỗ trợ và có ứng dụng-consistent backup được chứng minh. **Storage snapshot đơn thuần có thể crash-consistent**, không bảo đảm DB transaction consistency.



## 15. Azure Managed Disks và Virtual Machines

### 15.1. VM backup, disk snapshot, Azure Site Recovery khác nhau

| Cơ chế | Mục tiêu | Không tự bảo đảm |
|---|---|---|
| **Managed Disk snapshot** | Chụp trạng thái disk ở một thời điểm, có incremental snapshot khi supported | Application-consistent multi-disk database transaction |
| **Azure Backup for VMs** | Backup VM/disks theo policy và recovery points, hỗ trợ workload-consistency tùy cấu hình | Mọi external database/network/identity được phục hồi |
| **Azure Site Recovery (ASR)** | Replicate, orchestrate failover/failback VM theo DR model | Backup độc lập để khôi phục trước ransomware/delete |
| **Golden image + IaC** | Recreate stateless VM nhanh | Local persistent data và runtime secrets |
| **Native DB backup** | Khôi phục transaction/log/data theo DB engine | Bản thân OS, network hoặc VM identity |

Trong ứng dụng cloud-native, ưu tiên **stateless compute** có thể rebuild; không lưu nguồn sự thật trên OS disk nếu có thể chuyển sang managed database/storage được bảo vệ tốt hơn.

### 15.2. Crash-consistent và application-consistent

- **Crash-consistent:** disk state giống một lần mất điện; database cần recovery journal/WAL khi khởi động.
- **Application-consistent:** phối hợp quiesce/flush ứng dụng/file-system/DB writers trước snapshot theo khả năng backup system.
- **Multi-disk consistency:** nếu DB data và log nằm trên nhiều disks, cần restore point nhất quán của cả nhóm disks.
- **Transaction consistency:** phải theo engine semantics và cấu hình backup app-aware, không mặc định mọi snapshot bảo đảm.

Với SQL Server trên Azure VM, sử dụng các cơ chế Azure Backup/SQL workload-aware hoặc native SQL backups phù hợp để đáp ứng RPO/RTO. Một VM-level restore có thể đưa OS lên nhưng database không đáp ứng consistency hoặc đang thiếu log backups.

### 15.3. Azure Backup VM restore

Một runbook thực tế nên kiểm tra:
1. Recovery Services vault hoặc Backup vault theo backup type.
2. VM backup policy, backup success và latest recovery point.
3. OS disks/data disks, encryption, key availability.
4. Có application-consistent recovery point khi cần không.
5. Khôi phục toàn VM, disks hoặc file restore theo hỗ trợ.
6. Target VNet/subnet, NSG, IP/DNS, load balancer registration.
7. VM extensions, managed identity, domain join, monitoring agents.
8. SQL/database services startup và consistency.
9. Data integrity/permissions.
10. Backup re-enrollment cho restored VM và dọn tài nguyên test.

**Restore VM không tự đưa Public IP, DNS, private endpoint và App Gateway backends trở lại cùng topology** nếu không có runbook/IaC.

### 15.4. ASR không thay backup phục hồi dữ liệu lịch sử

Azure Site Recovery hữu ích cho scenario VM/site/region outage, thử failover và failback. Nó cũng có recovery points theo hỗ trợ, nhưng một hệ thống chỉ dựa ASR chưa có bằng chứng bảo vệ trước malware/corruption kéo dài nếu replication đã sao chép dữ liệu sai. Kết hợp backup độc lập, access isolation, PIM và immutable retention theo yêu cầu.

### 15.5. Filesystem mount và dữ liệu ngoài VM

Một ứng dụng VM có thể dùng:
- Managed disk để ghi local data.
- Azure Files mount.
- Blob Storage.
- Azure SQL Database.
- Key Vault.
- Một external SaaS.

Nếu khôi phục VM về hôm qua nhưng database ngoài VM vẫn ở hôm nay, cần kiểm tra **app migrations, local queues và reprocessing**. Không chọn VM recovery point như thể nó đồng bộ hóa mọi dịch vụ bên ngoài.

## 16. AKS và dữ liệu của workloads có trạng thái

### 16.1. Không nhầm cluster state với application data

Một AKS cluster có:
- Kubernetes API objects: Deployments, Services, ConfigMaps, ServiceAccounts, CRDs.
- Workload manifests trong GitOps/IaC.
- PersistentVolumeClaims/PersistentVolumes.
- Azure Managed Disks hoặc Azure Files volumes.
- External Azure SQL, Cosmos DB, Storage, Service Bus, Redis.
- Secrets/identities/certificates, NetworkPolicy, Ingress/Gateway.

**Không nên coi backup Kubernetes control plane/etcd là backup mọi database hoặc Blob**. AKS là managed control plane, và đường backup của workloads phải tính tới volumes cũng như external services.

### 16.2. Hai lớp phục hồi

~~~mermaid
flowchart LR
    GIT["IaC / GitOps manifests"] --> AKS["Rebuild AKS cluster"]
    BAK["PV snapshots / AKS backup supported"] --> VOL["Restore persistent volumes"]
    DB["SQL/Cosmos backups"] --> D["Restore external data stores"]
    KV["Key Vault/identity recovery"] --> ID["Restore secrets and access"]
    AKS --> READY["App readiness"]
    VOL --> READY
    D --> READY
    ID --> READY
~~~

Lớp **control plane/workload configuration** và lớp **business data** có failure domains khác nhau. Một workload dùng managed database hoàn toàn có thể chỉ cần rebuild Pods/Services rồi kết nối tới database đã được restore hoặc failover riêng.

### 16.3. Azure Backup for AKS

**Azure Backup for AKS** (tùy khu vực, feature support và extension/Backup vault) có thể bảo vệ Kubernetes resources và persistent volumes theo policy/tập tài nguyên được hỗ trợ. Không mặc định:
- Tất cả storage drivers/CSI volumes được backup.
- External Azure SQL/Cosmos DB cũng được snapshot cùng.
- Mọi CRD/cluster-scoped resources đều được bảo vệ.
- Restore cross-region/cross-subscription được phép cho mọi tính năng.
- Volume snapshot consistent cho database bên trong Pod.
- Những secrets đã được externalized vẫn có trong Kubernetes backup.

Trước khi dùng cần kiểm tra supported AKS versions, backup extension, CSI drivers, regions, Backup vault, RBAC, Azure Disk/Files limitations và recovery granularity.

### 16.4. Backup PV/PVC không đủ cho stateful database

Ví dụ PostgreSQL chạy trong StatefulSet trên AKS:
1. Data và WAL có thể trên các volumes khác nhau.
2. Volume snapshot có thể được chụp khi DB đang ghi.
3. Nếu không quiesce/app-consistent strategy, restore có thể cần crash recovery hoặc bị lỗi.
4. Helm chart/CRD operator version có thể khác giữa backups.
5. PVC storage class/topology có thể không có ở target region.
6. Database credentials và encryption keys có thể nằm ngoài cluster.
7. Restore xong còn cần xác minh DB transactions, replication slots và users.

Với workloads quan trọng, cân nhắc dịch vụ database managed hoặc engine-aware backup như pgBackRest/WAL archiving theo thiết kế được kiểm chứng; đừng lấy snapshot Kubernetes thay thế một chiến lược DB backup đã được thử.

### 16.5. Velero hoặc công cụ cộng đồng

Các công cụ như Velero có thể backup Kubernetes resources và phối hợp volume snapshots/file-level backups tùy plugin/storage backend. Nhưng:
- Không phải dịch vụ managed backup Azure mặc định.
- Cần tự vận hành/version/plugin/credentials/backup storage.
- Restore CRD/controller order rất quan trọng.
- Có thể có sự khác biệt giữa source/target Kubernetes version.
- Backup bucket/account phải được tách quyền và bảo vệ khỏi xóa.
- Không tự sao lưu external managed databases.

Một giải pháp AKS disaster recovery tốt thường có **GitOps IaC + application-level backup + PV backup đúng loại + identity/network recovery**.

### 16.6. Runbook dựng AKS mới sau region outage

1. Chọn region đích và xác nhận capacity/quota của node SKUs.
2. Dùng IaC dựng VNet/subnets/private DNS/firewall.
3. Tạo cluster AKS với identity/OIDC/Workload ID phù hợp.
4. Khôi phục ingress/gateway, NetworkPolicies, monitoring và registry auth.
5. Deploy CRDs/controllers/storage classes theo thứ tự.
6. Restore Kubernetes objects/PV hoặc dùng GitOps sync khi thích hợp.
7. Khôi phục external databases/Blob/file shares theo riêng từng runbook.
8. Map secrets, user-assigned managed identities và RBAC.
9. Chạy readiness/smoke/business tests trước traffic cutover.
10. Cập nhật Front Door/DNS/routes; quan sát queues/data integrity.
11. Đảm bảo backup protection của cluster và services mới được bật.
12. Ghi observed RPO/RTO so với mục tiêu.

Không đưa tất cả Pods lên trước khi external databases và messaging phục hồi; nếu không, có thể tạo retry storm, message duplicates hoặc cache stampede.

## 17. Azure Service Bus, Event Hubs và Azure Queue Storage

### 17.1. Message broker không giống database backup

**Azure Service Bus** queue/topic/subscription có:
- Broker entity metadata và settings.
- Message bodies đang active.
- Scheduled messages.
- Dead-letter messages.
- Duplicate detection window, sessions, locks, transactions theo tier.
- Producers/consumers và checkpoint/processing state.

Một giải pháp "backup namespace configuration" có thể chỉ giữ **metadata**, không giữ từng message body. Vì vậy phải xác minh đúng **data-plane recovery** mà business yêu cầu.

### 17.2. Service Bus Geo-Disaster Recovery so với data geo-replication

Với mô hình **Geo-Disaster Recovery (Geo-DR) cổ điển dựa trên alias/metadata pairing**, khả năng chủ đạo là khôi phục **namespace/entity metadata**, **không tự replicate message data**. Sau failover, ứng dụng có thể kết nối namespace secondary nhưng các messages đang chờ trên primary không tự xuất hiện.

Service Bus cũng có những khả năng **Geo-Replication** khác theo tier/region và thời điểm, có thể bao gồm message data với đặc tính và giới hạn riêng. Không đánh đồng hai tính năng; trước khi chọn hãy kiểm tra:
- Basic/Standard/Premium tier hỗ trợ gì?
- Feature có khả dụng ở region/namespace configuration?
- Message bodies, sessions, scheduled/DLQ messages được replicate thế nào?
- Sync/async lag và forced failover RPO là bao nhiêu?
- Phải tạo lại client/connection string/alias nào?
- Có support producer/consumer failback không?
- Phí và capacity khi hai namespace hoạt động thế nào?

**Một DR plan chỉ ghi “bật Service Bus Geo-DR” chưa chứng minh RPO của messages đạt yêu cầu.**

### 17.3. Thiết kế phục hồi message qua outbox

Nếu Orders API ghi đơn vào Azure SQL và gửi Service Bus message, có thể dùng **transactional outbox** trong database:

~~~mermaid
flowchart LR
    API["Orders API"] --> TX["SQL transaction: Order + Outbox row"]
    TX --> PUBLISH["Outbox publisher"]
    PUBLISH --> SB["Service Bus"]
    SB --> WORKER["Worker idempotent"]
    WORKER --> DB["Invoice state"]
~~~

Khi Service Bus gặp sự cố:
- Order + Outbox row vẫn được commit cùng transaction trong SQL.
- Publisher có thể retry gửi message khi Service Bus hồi phục.
- Có thể xuất hiện duplicate delivery nếu ACK mất, nên consumer cần idempotency.
- Outbox retention/cleanup không được xóa unsent events quá sớm.
- Khi Orders DB restore về thời điểm cũ, phải đối soát những events đã gửi trước sự cố.

Outbox giúp replay business events, nhưng **không biến Service Bus thành exactly-once delivery system**.

### 17.4. Event Hubs khác Service Bus

**Azure Event Hubs** là event streaming ingestion với event retention theo partition, consumer offsets/checkpoints và replay trong retention. Cần bảo vệ:
- Event retention period và throughput/capacity.
- Consumer checkpoints (thường ở Azure Blob Storage theo SDK).
- Event schemas, partition keys và producer IDs.
- **Event Hubs Capture** khi được bật: lưu sự kiện tới Azure Blob Storage/ADLS theo policy và constraints.
- Azure Storage backup/immutability cho archive nếu cần retention dài.
- Cross-region DR/geo replication theo tier/capability.
- Replay tooling và idempotent consumers.

Nếu retention 7 ngày mà sự cố phát hiện sau 30 ngày, không thể tự động replay từ Event Hubs nếu event đã hết retention và không có Capture/archive. **Checkpoint là vị trí đã xử lý, không phải một bản backup nội dung events**.

### 17.5. Event Hubs Capture và replay từ archive

Một kế hoạch:
1. Bật Capture nếu business cần archive lâu hơn event retention và tính năng hỗ trợ.
2. Lưu vào Storage với redundancy/backup/immutable policy phù hợp.
3. Quản lý schema versions và thời gian lưu.
4. Khi downstream database corrupted, xác định last-good checkpoint.
5. Rebuild data store/counters từ captured events có idempotency.
6. Kiểm tra thứ tự trong partitions, duplicates, event-time vs processing-time.
7. Dùng durable state để đánh dấu replay progress.
8. So totals/checksums và billing records.
9. Chỉ đổi serving pointer sau validation.
10. Giữ source archive theo retention.

### 17.6. Azure Queue Storage

Azure Queue Storage không phải một transaction log vô hạn:
- Message có TTL/visibility semantics.
- Consumer xử lý có thể delete message sau success.
- Message đã bị xóa hoặc hết TTL thường không còn để replay trực tiếp.
- Storage geo redundancy không đồng nghĩa khôi phục một message đã xử lý sai.
- Nên ghi business intent vào database/outbox hoặc durable event archive.
- Nếu cần DLQ/topic/rich transactions nên đánh giá Service Bus theo yêu cầu.

### 17.7. Thế nào là RPO cho messaging?

RPO của message business có thể được định nghĩa:

~~~text
Một order đã được xác nhận không được mất
ý định tạo invoice khi broker không sẵn sàng.

Business source of truth = Orders + Outbox
Recovery requirement:
  No accepted order without recoverable invoice command
  (cho phép retry/duplicate, không cho phép mất intent).
~~~

Đây có thể đạt hiệu quả **không mất business intent** ngay cả khi broker ephemeral state bị mất, miễn database/outbox recovery đáp ứng RPO, publisher/worker đúng và reconciliation được kiểm chứng. Đừng gán RPO=0 cho Service Bus chỉ từ sự tồn tại của một topic.

## 18. Cache: Azure Managed Redis và các Redis deployments

### 18.1. Cache nên là dữ liệu dẫn xuất

Ví dụ cache giỏ hàng gần đây:
- Nếu giá trị cache có thể dựng lại từ Azure SQL/Cosmos DB và không chứa writes độc quyền, mất cache thường không phải mất dữ liệu nghiệp vụ.
- Khi cache failover, có thể để app read from source rồi warm.
- Cần chống **cache stampede**: hàng nghìn requests cùng query DB khi cache rỗng.
- TTL, warm strategy, circuit breaker và read-only fallback ảnh hưởng RTO.

Dù Azure Managed Redis hoặc Azure Cache for Redis có HA/persistence/replication features khác nhau tùy SKU/lifecycle, **không mặc định cache là nguồn dữ liệu lâu dài**.

### 18.2. Khi cache thật ra là source of truth

Nếu app lưu shopping carts **chỉ** trong Redis, mất cache chính là mất dữ liệu. Khi đó phải:
1. Chấp nhận RPO/RTO rất khác với cache tiêu chuẩn.
2. Xem persistence (RDB/AOF), backup/export và geo features đúng service/tier.
3. Kiểm tra snapshot frequency và failure domain.
4. Kiểm tra restore và failover, nhất là session/auth consistency.
5. Hoặc chuyển giỏ hàng tới Cosmos DB/SQL làm nguồn sự thật, Redis chỉ giữ derived data.

Không kết luận “Redis luôn không cần backup”: phụ thuộc nghiệp vụ đang sử dụng nó.

### 18.3. Cache recovery runbook

1. Xác định lỗi là network/auth hay dữ liệu cache mất.
2. Bảo đảm database source of truth healthy.
3. Giới hạn request rate/concurrency để không làm DB sập.
4. Bật fallback/TTL/cache warm policy.
5. Theo dõi cache hit ratio, DB CPU/RU, p95 latency.
6. Rebuild cache theo keys/pattern được phê duyệt.
7. Kiểm tra dữ liệu cache được invalidate đúng khi update.
8. Nếu cache chứa dữ liệu người dùng nhạy cảm, bảo vệ key/value và logs.
9. Tắt chế độ emergency sau khi hồi phục.
10. Ghi observed RTO và database cost spike.

## 19. Key Vault, identities và App Configuration trong DR

### 19.1. Không có keys, dữ liệu backup có thể vô dụng

Một database/file archive dùng CMK trong Key Vault có thể còn nguyên nhưng restore thất bại nếu:
- Key bị purge.
- Key Vault không reachable trong region DR.
- Identity restore không có unwrap/decrypt permissions.
- Private Endpoint/DNS không đúng.
- Key version được rotate và không còn giữ.
- Tenant/subscription IAM thay đổi.
- HSM migration/backup không đáp ứng yêu cầu.

**Key Vault phải được coi là một phần của dependency graph của phục hồi**, không phải cấu hình phụ ít quan trọng.

### 19.2. Key Vault soft delete và purge protection

Với Key Vault, **soft delete** và **purge protection** giúp tránh xóa mất key/secret/certificate/vault quá sớm theo retention/capabilities. Những điểm cần lưu ý:
- Soft delete bảo vệ trước xóa ngoài ý muốn trong retention.
- Purge protection hạn chế purge trước hết retention theo service rules.
- Không tự sao lưu secret values bằng cách export plaintext vào Git.
- Key Vault backup/restore operations có giới hạn đối tượng, vùng/tenant và loại tài nguyên; phải kiểm tra mô hình backup supported.
- Secrets rotate có thể tạo versions; khôi phục version không tự phục hồi password/token đã bị downstream revoke.
- Vault-level restore không tự dựng lại mọi RBAC/network/private DNS/managed identities nếu không có IaC.

### 19.3. Phân vai người phục hồi

| Principal | Nhiệm vụ | Quyền tối thiểu |
|---|---|---|
| Runtime identity | Đọc secret hoặc thực hiện crypto operation cần dùng | Data-plane role/hẹp |
| Backup operator | Xem jobs và chọn recovery point | Backup permissions theo scope |
| Restore operator | Tạo isolated restored resources | Restore permissions |
| Key admin | Quản lý key lifecycle/purge policies | Key management theo PIM |
| Identity admin | Khôi phục role/federation/principal configuration | Entra/Azure RBAC governance |
| Audit viewer | Đọc evidence | Read-only logs theo policy |

Không cấp subscription Owner lâu dài cho một application chỉ để nó tự làm DR. Trong incident, cần emergency access có MFA/PIM, dual control và audit theo tổ chức.

### 19.4. Azure App Configuration cũng là dữ liệu vận hành

App Configuration chứa key-values, feature flags, labels và có các khả năng như snapshots, revisions và soft delete theo tier/feature support. Ngoài ra có thể version/backup cấu hình quan trọng qua IaC/source control/export.

Nếu mất hoặc đổi nhầm feature flag:
- Có thể ảnh hưởng ngay đến business code path.
- Application có cache refresh, nên các instances không đồng thời nhìn thấy thay đổi.
- Khôi phục App Configuration value không tự rollback binary hoặc database.
- Multiple regions, App Configuration replicas/geo-replication features có availability khác backup logic.
- Connection/security setup phải được kiểm chứng ở region đích.

Tốt nhất là quản lý key-values quan trọng bằng **configuration-as-code và release audit**, còn secret values ở Key Vault. Mọi thay đổi emergency flag phải có owner và mốc thời gian.

### 19.5. IaC là bản backup của control plane, không phải data plane

Bicep/Terraform/GitOps có thể dựng lại:
- VNet/subnets/Private DNS/NSG.
- Azure resources, SKU, network rules.
- RBAC role assignments khi principal IDs hợp lệ.
- App Service/AKS/Container Apps config.
- Alert rules/diagnostic settings.
- Storage/DB settings, backup policies.
- Front Door/Traffic Manager routes.

Chúng **không tự phục hồi Orders rows, Blob contents hoặc Service Bus message bodies**. Ngược lại, database backup cũng không tự khôi phục IaC nếu repo đã mất. Bảo vệ cả Git repository, artifacts, state backend, key material và backup records.


## 20. Data Factory, Synapse, Databricks và nền tảng phân tích

### 20.1. Dữ liệu phân tích có nhiều lớp

Một nền tảng analytics thường gồm:
- Azure Data Factory pipelines hoặc Synapse pipelines.
- Azure Data Lake Storage Gen2 raw/bronze/silver/gold.
- Azure Databricks notebooks/jobs/Delta tables/Unity Catalog.
- Azure Synapse Analytics SQL pools/lake databases.
- Event Hubs/Event Hubs Capture và stream checkpoints.
- Azure SQL/Cosmos DB làm operational sources.
- BI semantic models/dashboards.
- Git repos, workspace definitions, secret scopes, identities và network.

Nếu mất một Gold aggregate thì có thể rebuild từ Bronze/Silver. Nếu mất raw event archive mà upstream retention đã hết, **không còn dữ liệu gốc để tái dựng**.

### 20.2. Phân biệt data recovery và pipeline recovery

| Đối tượng | Cơ chế chủ đạo | Rủi ro sau restore |
|---|---|---|
| Raw data in ADLS | Versioning/soft delete/backup/immutable archive đúng feature | Source event gaps, ACL/paths |
| Delta table | Transaction log/time travel + underlying object protection | VACUUM/log retention, corruption |
| Databricks notebooks/jobs | Git/CI/CD, workspace export/IaC | Runtime/library/compute config không khớp |
| Unity Catalog metastore/permissions | Chính sách backup/DR theo service support, IaC và catalog export phù hợp | External locations/credentials/owner mismatch |
| Data Factory pipelines/triggers | Git integration, ARM/Bicep, deployed artifact | Trigger disabled/enabled sai, linked service secrets |
| Synapse dedicated SQL pool | Built-in restore points/backups theo capability | Restore duration và DB objects/security |
| Synapse serverless SQL | Definitions/views/external tables từ code; data ở Storage | Nếu Storage mất thì query logic còn cũng vô ích |
| Streaming checkpoints | Checkpoint blobs/files và source retention | Offset cũ có thể replay trùng hoặc bị expire |
| Gold reports | Recompute từ nguồn + logic versioned | Có thể tốn hàng giờ/compute cost |

Không xem một snapshot ADLS đủ để khôi phục toàn bộ Synapse/Databricks workspace và hệ thống quyền.

### 20.3. Reprocessing phải đúng logic và thời gian

Khi rebuild một report:
1. Xác định exact source dataset/version.
2. Pin pipeline/SQL/notebook code version.
3. Đảm bảo timezone, watermark, event-time/processing-time semantics.
4. Rebuild vào **new table/path** để không phá báo cáo đang phục vụ.
5. Kiểm tra schema evolution, dedup, late arriving events.
6. So record counts và business aggregates với control totals.
7. Đánh giá consistency với operational data đang tiếp tục ghi.
8. Chỉ đổi catalog/pointer khi validated.
9. Ghi lineage, commit, data version và UTC timestamp.
10. Dọn artifacts theo retention, không xóa source archive.

### 20.4. Một ví dụ Delta time travel

Lệnh minh họa cú pháp trong môi trường Delta Lake hỗ trợ:

~~~sql
-- Đọc version trước để điều tra, không sửa table production.
SELECT *
FROM orders_gold VERSION AS OF 145;
~~~

Khả năng đọc version 145 phụ thuộc Delta transaction log và data files vẫn còn. Với workflow **RESTORE TABLE** hoặc overwrite, phải review trước vì đây là write operation gây tác động tới current state và downstream consumers. Không thực thi trên dữ liệu production khi chưa có approval.

### 20.5. Dữ liệu derived có thể có RTO dài hơn

Nếu Gold reports chỉ cập nhật mỗi ngày, việc rebuild trong 12 giờ có thể chấp nhận; còn Orders API cần dưới 1 giờ. Dùng **business impact** để ưu tiên capacity. Không tạo cross-region hot replica cho mọi bảng aggregate nếu chi phí cao mà nhu cầu chỉ là báo cáo sáng hôm sau.

## 21. Tính nhất quán khi phục hồi nhiều dịch vụ

### 21.1. Một business transaction có nhiều dữ liệu liên quan

Ví dụ checkout:
1. Orders API ghi order vào Azure SQL.
2. Cập nhật trạng thái Cart trong Cosmos DB.
3. Gửi InvoiceRequested qua Service Bus.
4. Worker tạo PDF trên Blob.
5. Gọi payment partner.
6. Phát email xác nhận.

Nếu SQL PITR về 09:55 nhưng Cosmos về 10:00, Blob về 09:50 và Service Bus namespace mới rỗng, **không có một ảnh chụp “toàn hệ thống 09:55”**. Các dịch vụ không có một transaction xuyên tất cả các bước.

### 21.2. Sơ đồ lệch recovery points

~~~mermaid
flowchart TD
    T["Sự cố 10:00"] --> SQL["SQL Orders restore 09:55"]
    T --> COS["Cosmos Cart restore 09:58"]
    T --> BL["Blob invoice version 09:50"]
    T --> SB["Service Bus metadata restored, messages unknown"]
    SQL --> REC["Reconciliation engine"]
    COS --> REC
    BL --> REC
    SB --> REC
    REC --> VALID["Business invariants + audit"]
~~~

Không chọn cùng một timestamp trong portal của từng dịch vụ rồi giả định tất cả đã consistent: thực tế snapshots/backup points, replication lag và event workflows khác nhau.

### 21.3. Xác định system of record cho từng giao dịch

Ví dụ:
- **Orders SQL** là nguồn sự thật trạng thái đã nhận đơn.
- **Payment provider** là nguồn sự thật cho thanh toán đã capture.
- **Outbox row** là nguồn sự thật về ý định phát sự kiện.
- **Invoice Blob** là chứng từ kết quả, có thể tái dựng nếu có đầy đủ data.
- **Cart Cosmos** chỉ thể hiện bước trước checkout, có thể bị xóa sau order success.

Khi restore:
- Không tự “thu tiền lại” vì Orders SQL PITR không có payment status.
- Query payment gateway theo stable payment transaction ID và approval.
- Nếu order hợp lệ nhưng thiếu invoice, tạo **compensating invoice generation job** idempotent.
- Nếu invoice đã tạo mà order không còn, reconcile trước khi xóa bất kỳ dữ liệu nào.

### 21.4. Business invariants

Một recovery phải đạt các bất biến:
- Mỗi orderId chỉ có một accepted order logic.
- Không capture cùng payment intent hai lần.
- Các order đã captured phải có hoặc được lên lịch tạo invoice.
- Hóa đơn đúng amount/currency/tax rules.
- Message replay không tạo duplicate side effects.
- Inventory reservations không âm hoặc bị giữ vô hạn.
- Mỗi tenant chỉ thấy dữ liệu thuộc mình.
- Trạng thái tài chính được đối soát với external ledger.

**Row count và HTTP 200 không đủ** để tuyên bố phục hồi thành công.

### 21.5. Dùng event sourcing/outbox đúng phạm vi

Một durable event log có schema versions, correlation IDs và idempotent processors giúp:
- Tái tạo read models.
- Bổ sung operations bị thiếu sau restore.
- Tính lại các counters.
- Phát hiện chênh lệch giữa hệ thống.

Nhưng muốn replay được cần:
- Event log giữ đủ thời gian.
- Không sửa/xóa lịch sử ngoài policy.
- Có deterministic handlers hoặc lưu external reference versions.
- Không replay side effects (capture payment/email) mà không có idempotency/compensation.
- Có replay checkpoint và cách dừng/resume.
- Có capacity/throughput để hoàn tất trong RTO.

### 21.6. Reconciliation checklist

~~~text
Reconciliation ID:
Incident start / detection UTC:
Source of truth per business entity:
Recovery point and restore target per service:
Known potentially lost writes:
Known duplicated messages/side effects:
Order-to-payment matches:
Order-to-invoice matches:
Inventory reservation checks:
Message/event checkpoint:
Failed/missing/duplicate record count:
Operator/DBA/business approval:
Final RPO/RTO/RLO measured:
~~~

Không đưa thẻ thanh toán, token, secret hoặc raw PII vào bản báo cáo công khai. Dùng record IDs và quyền truy cập theo data classification.

## 22. Xác định thứ tự khôi phục theo dependency graph

### 22.1. Không phục hồi theo thứ tự ngẫu nhiên

Một khôi phục đa dịch vụ cần thứ tự:

~~~mermaid
flowchart TD
    A["Incident declaration / freeze writes"] --> B["Identity, keys, subscription access"]
    B --> C["Network, DNS, private endpoints"]
    C --> D["Data restoration / region failover"]
    D --> E["Messaging / outbox / replay checkpoint"]
    E --> F["Compute/IaC apps in recovery environment"]
    F --> G["App integration and consistency tests"]
    G --> H["Traffic cutover / canary"]
    H --> I["Monitor, reconcile, close incident"]
~~~

Đây là thứ tự **tham khảo**; trong một số region outages phải dựng compute trước để chạy công cụ khôi phục, hoặc phải restore backup storage/network song song. Quan trọng là định nghĩa rõ dependencies và những bước có thể chạy đồng thời mà không phá consistency.

### 22.2. Phase 0: tuyên bố và khoanh vùng sự cố

1. Xác định incident severity, phạm vi services, region và tenant.
2. Dừng job/process đang ghi sai hoặc thông qua change freeze.
3. Ngăn delete/purge/rotation không cần thiết.
4. Giữ chứng cứ logs, access records và backup metadata.
5. Bật communication/on-call, business owner và emergency approvals.
6. Phân biệt outage/identity/network với true data loss.
7. Lấy snapshot/recovery point hiện tại nếu có lợi và an toàn.
8. Quyết định target RPO/RTO và mức data loss cho phép.
9. Chọn recovery region/subscription/isolation boundary.
10. Không thao tác destructive trước khi hiểu phương án.

### 22.3. Phase 1: khôi phục quyền và môi trường tối thiểu

- Entra tenant/principals, managed identity và RBAC.
- Key Vault CMKs/secrets, access policies/purge protection.
- VNet, routing, NSGs, Azure Firewall, Private DNS, endpoints.
- Backup operator identity và quyền restore.
- Artifact/image registry access.
- Restore location capacity/quotas theo service.
- Log Analytics/Monitoring và evidence chain.

Nếu primary tenant/identity bị nghi ngờ đã compromise, không dùng lại các service principals/tokens bị lộ để dựng recovery environment.

### 22.4. Phase 2: khôi phục nguồn sự thật

Ưu tiên:
1. SQL/primary DB.
2. Blob/Files chứng từ không thể tái tạo.
3. Cosmos/operational datasets.
4. Message/outbox archives và checkpoint state.
5. Các artifacts/cấu hình cần phục hồi.
6. Derived stores, caches và reports sau.

Tùy business, Blob có thể là system of record còn SQL chỉ index metadata; ma trận thực tế quyết định thứ tự.

### 22.5. Phase 3: mở ứng dụng có kiểm soát

- App API ở chế độ read-only/quiesced nếu cần reconciliation.
- Background consumers tạm dừng cho tới khi checkpoints hợp lệ.
- Bật limited canary cohort, kiểm tra transaction correctness.
- Thực hiện smoke/integration tests không tạo side effects ngoài ý muốn.
- Đo latency/5xx/authorization/quota.
- Mở writes dần và bật workers có idempotency.
- Theo dõi backlog, DLQ, invoices và payment reconciliation.
- Chỉ chuyển DNS/Front Door/global routes theo approved plan.
- Bật lại backup policies/monitoring ở target mới.
- Thông báo business stakeholders rằng recovery đã đạt RLO nào.

### 22.6. Phase 4: failback và cleanup

Sau region phục hồi hoặc main service được sửa:
- Xác định nguồn sự thật mới ở region DR.
- Không bật primary writes trở lại nếu sẽ split-brain.
- Thiết kế reverse replication/cutback theo khả năng dịch vụ.
- Đối soát records/offsets/new writes trong thời gian DR.
- Cutover traffic theo runbook và stop old writers.
- Re-enable monitoring, backup, IAM trên region chuẩn.
- Cleanup tài nguyên test có approval, giữ backups/evidence theo retention.
- Cập nhật IaC/config và drill report.

**Failback không phải đơn giản đảo ngược một CNAME** nếu hai regions đã ghi dữ liệu khác nhau.

## 23. Những mẫu kiến trúc DR theo RPO/RTO

### 23.1. Backup-and-restore

~~~text
Primary service
   → scheduled backup/restore points
   → independent protected retention
   → restore into new resource on incident
   → validate + route app
~~~

Phù hợp:
- Dữ liệu không yêu cầu RTO vài phút.
- Ngân sách có hạn.
- Có thể chấp nhận khôi phục hàng chục phút/giờ.
- Mức mất dữ liệu theo backup policy phù hợp.

Rủi ro: restore time dài và phụ thuộc setup mạng/identity/keys.

### 23.2. Pilot light / warm standby

~~~text
Primary region: full production
DR region: IaC, network, keys, some DB copies,
           minimal compute and standby configs
On incident: scale and route
~~~

Phù hợp với workload có RTO ngắn hơn cold restore nhưng không muốn chạy full capacity cả hai regions. Cần kiểm tra:
- DR database replica hoặc geo backup thật.
- ACR image availability và quotas.
- DNS/Front Door failover.
- Managed identity/Key Vault access.
- Server warm-up và cache.
- RPO asynchronous replication.

### 23.3. Active-passive regional design

- Primary xử lý writes.
- Secondary nóng hoặc ấm, sẵn network/compute.
- Database có geo-replica/other supported DR.
- Automatic/manual failover theo app/DB semantics.
- Tránh stale writes và split brain.
- Kèm PITR/backup độc lập cho corruption.

### 23.4. Active-active

Hai hoặc nhiều regions cùng nhận requests, có thể cùng ghi. Muốn an toàn cần:
- Dịch vụ dữ liệu hỗ trợ multi-region write/consistency phù hợp.
- Conflict resolution và business-level idempotency.
- Session/tenant routing.
- Replication lag và read consistency.
- Schema rollout compatible giữa regions.
- Distributed tracing/observability.
- Backup cho lỗi logic/compromise.
- Kế hoạch khi network partition tạo divergent updates.

**Active-active tăng độ phức tạp dữ liệu**; không nên chọn chỉ vì muốn RTO bằng 0 mà chưa đánh giá consistency và conflict semantics.

### 23.5. RPO/RTO trade-off matrix

| Kiến trúc | RPO khả dĩ | RTO khả dĩ | Chi phí/độ phức tạp |
|---|---|---|---|
| Backup định kỳ local | Theo khoảng backup | Từ phục hồi dài | Thấp–trung |
| Geo-backup restore | Theo backup/geo availability | Thường dài hơn hot standby | Trung |
| Warm standby + geo replica | Theo replication lag | Ngắn hơn restore từ lạnh | Trung–cao |
| Active-passive hot | Theo DB failover semantics | Có thể ngắn, cần test | Cao |
| Active-active multi-write | Theo consistency/conflict | Có thể rất ngắn với một số failure | Rất cao |
| Event replay/rebuild | Theo durable event retention | Theo dữ liệu và compute throughput | Tùy data volume |

Đây là **so sánh tương đối**, không phải RPO/RTO SLA hay cam kết tính năng của Azure. Phải đo với exact service SKU, volume và region thật.

## 24. Ransomware, xóa ác ý và bảo vệ bản phục hồi

### 24.1. Tư duy assume breach

Khi attacker có quyền application account hoặc subscription:
- Có thể delete/overwrite primary data.
- Có thể cố thay backup retention.
- Có thể xóa Blob versions nếu quyền quá rộng.
- Có thể compromise build pipeline/IaC và image.
- Có thể rotate/purge keys làm backup khó giải mã.
- Có thể xóa logs/audit nếu không được bảo vệ.

Bảo vệ chống accidental delete chưa đủ nếu cùng principal có thể xóa cả bản phục hồi.

### 24.2. Các lớp bảo vệ

1. Data-plane least privilege cho ứng dụng; không cấp delete/purge/admin bừa bãi.
2. Tách backup operator/restore operator khỏi runtime identity.
3. MFA, PIM, conditional access, break-glass governance.
4. Immutable/isolated copies theo service support.
5. Soft delete và purge protection cho Key Vault, backup vault/Storage theo khả năng.
6. Cross-region/cross-account copies khi business risk yêu cầu.
7. Encryption key lifecycle/availability phục vụ restore.
8. Backup policy audit và cảnh báo thay retention/disable backup.
9. Secret scanning/SBOM/CI security để ngăn supply-chain compromise.
10. Recovery drill trong môi trường sạch không tái sử dụng credential nghi bị lộ.

### 24.3. “Bản backup có sẵn” chưa chắc “sạch”

Nếu corruption bắt đầu từ ba tuần trước, restore bản của hôm qua có thể vẫn chứa records đã bị sửa. Cần:
- Xác định **first known bad change**.
- Chọn recovery point trước thời điểm đó, trong retention.
- So logs/event sources để phân biệt bad vs good writes.
- Quét/sandbox restored data nếu malware/file content có rủi ro.
- Không expose recovery database vào production network trước validation.
- Giữ evidence theo incident/forensics policy.

### 24.4. Bảo mật trong quy trình khôi phục

Một restored production database có PII không nên tự động được mở cho mọi developer tại region test. Recovery target phải:
- Có network isolation.
- Tối thiểu quyền truy cập.
- Encryption at rest/in transit.
- Logging/redaction phù hợp.
- Data retention và cleanup có approval.
- Key access được audit.
- Không xuất raw customer records vào ticket.
- Chỉ dùng synthetic data trong public demo.

### 24.5. Phân biệt business recovery và cyber recovery

Business DR có thể ưu tiên availability khi region outage. Cyber recovery có thể yêu cầu:
- Cô lập tài khoản/tokens bị compromise.
- Xác thực lại nguồn image/automation.
- Chọn clean backup trước infection.
- Rotating credentials và keys theo security incident policy.
- Forensic investigation.
- Chấp nhận RTO dài hơn vì cần giữ integrity và containment.

**Failover ngay sang replica nhiễm corruption có thể kéo dài sự cố** thay vì chữa nó.


## 25. Backup policy, IaC và evidence của recovery

### 25.1. Policy không chỉ là số ngày retention

Một backup policy có thể mô tả:

~~~yaml
# Ví dụ tài liệu nội bộ, KHÔNG phải manifest Azure Backup CLI.
dataClass: orders-critical
owner: orders-platform-team
systemOfRecord: azure-sql-database

objectives:
  rpo: "PT5M"
  rto: "PT1H"
  rlo: "accept-and-read-orders"

protection:
  type: "managed-pitr-plus-geo-strategy"
  shortTermRetention: "review per supported tier"
  longTermRetention: "business/compliance approved"
  geoRecovery: "verify enabled and test actual restore"
  immutableCopy: "evaluate where supported"

operations:
  backupSuccessAlert: true
  restoreDrillCadence: quarterly
  restoreTarget: isolated-recovery-environment
  dataIntegrityOwner: orders-business-owner
  securityApprovalRequired: true
~~~

Đây là **schema minh họa do tổ chức tự định nghĩa**, không phải Azure ARM/Bicep/Terraform resource có thể apply trực tiếp. Giá trị là tiêu chí chính sách; triển khai thành cấu hình đúng theo dịch vụ và IaC modules tương ứng.

### 25.2. Tách backup policy khỏi quyền ứng dụng

- App identity có thể cần đọc/ghi Orders, không cần thay backup retention.
- Backup policy owner quản lý retention/schedule.
- Restore operator có quyền tạo target backup restore trong vùng cô lập.
- Security owner kiểm tra immutability, purge protection và access anomalies.
- Auditor xem reports/traces, không cần xem secret values.
- Cost owner đánh giá retention dài, storage redundancy và duplicate backups.

Cần xem các Azure built-in roles và actions cụ thể theo resource/vault. Không gán subscription Owner cho automation chỉ để quản lý recovery points.

### 25.3. Infrastructure as Code cho DR

Một module IaC tốt sẽ mô tả:
- Region/secondary region và resource naming.
- Storage redundancy/backup policies khi supported.
- VNet/Private DNS/endpoint topology tại recovery region.
- Managed identities và RBAC.
- Key Vault/CMK protection/retention.
- Monitoring alerts và diagnostic settings.
- Application Deployment/ACR images/Front Door routing.
- Data resource SKUs/quota/capacity.
- Recovery environment tags, budgets, lifecycle.

**Không chứa plaintext backup decryption keys, SQL passwords hoặc Storage account keys trong IaC source.** Terraform state có thể chứa secrets dù source không chứa; bảo vệ backend/state và permissions.

### 25.4. Nguồn sự thật cho protection state

| Nguồn | Dùng để kiểm tra | Hạn chế |
|---|---|---|
| ARM/CLI configuration | Retention, redundancy, IAM, resource state | Config đúng chưa chứng minh job thành công |
| Azure Backup jobs/Backup Center | Backup success/failure và recovery points | Restore usability chưa được test |
| Azure Monitor Logs/Metrics | Alert backup gaps, error trends | Log ingestion/retention có thể lỗi |
| Application audit/outbox | Business operations đã commit | Không nhất thiết là full data archive |
| Test restore report | RPO/RTO, validation thực tế | Một lần test chưa bao phủ mọi loại lỗi |
| IaC/Git version | Dựng lại control plane | Không chứa data-plane records |

### 25.5. Backup policy drift

Ví dụ DB mới được tạo bởi pipeline nhưng backup redundancy không giống quy chuẩn. Tài nguyên có thể hoạt động tốt nhiều tháng trước khi xảy ra region outage.

Cách giảm rủi ro:
1. Policy-as-code cho SKU, redundancy và retention.
2. Azure Policy khi có alias/effect cho đúng thuộc tính.
3. Post-deployment readback.
4. Resource inventory định kỳ.
5. Alert khi backup bị disable/retention bị giảm.
6. Audit quyền thay đổi config.
7. Chặn deploy critical dataset nếu chưa có DR capability.
8. Restore drill sau thay đổi lớn.
9. Ghi exceptions có owner/expiry.
10. Update runbook và cost estimate.

Không coi một Azure Policy “compliant” là bằng chứng data restore 100%: Azure Policy phần lớn đánh giá cấu hình, không thực hiện business recovery test.

## 26. Giám sát backup và phục hồi trên Azure

### 26.1. Các tín hiệu cần có

| Tín hiệu | Câu hỏi vận hành |
|---|---|
| Last successful backup | Lần sao lưu cuối thành công khi nào? |
| Earliest/latest restorable timestamp | Khoảng dữ liệu có thể phục hồi thực tế? |
| Retention remaining | Recovery point trước lỗi có còn? |
| Geo replication lag | Region phụ có thể thiếu bao nhiêu dữ liệu? |
| Backup/restore job failure | Policy/bản sao đang có lỗi? |
| Restore duration | RTO đo được với kích thước hiện tại? |
| Recovery point integrity | Database/file thực dùng được không? |
| Secret/key availability | Có decrypt/unwrap được backup không? |
| DR resource readiness | Quota, DNS, VNet, identity sẵn chưa? |
| Outbox/queue backlog | Có business intent cần replay? |
| Data reconciliation failures | Có mất/duplicate records sau restore? |
| Changes to IAM/policy | Có ai giảm retention/tắt backup? |
| Monthly backup/storage spend | Ngân sách bảo vệ có còn phù hợp? |
| Restore drill cadence | Buổi diễn tập gần nhất và next due? |

### 26.2. Backup Center và Azure Monitor

Azure Backup Center/Azure Business Continuity Center hoặc các trải nghiệm Azure Backup/Monitor tương ứng có thể cung cấp tổng quan jobs, policies, protected instances và compliance theo hỗ trợ hiện hành.

Không phải mọi managed service (Cosmos DB/SQL/Postgres/Blob) đều phát backup job vào cùng **Recovery Services vault**. Ví dụ:
- Azure SQL Database automatic PITR không giống Azure Backup VM job.
- Azure Backup for Blobs có Backup vault/Storage protection mechanisms.
- Cosmos DB continuous backup là account-level service policy.
- Service Bus Geo-DR không phải backup job định kỳ.
- Event Hubs Capture là data archiving pipeline.

Vì vậy dashboard hợp nhất phải query **đúng data source của từng dịch vụ**, không lấy số Azure Backup jobs làm tổng số protected datasets.

### 26.3. KQL phát hiện ARM changes nhạy cảm

Nếu subscription đã export Azure Activity Logs tới Log Analytics và bảng **AzureActivity** có dữ liệu:

~~~kusto
AzureActivity
| where TimeGenerated > ago(24h)
| where OperationNameValue has_any (
    "delete", "write", "purge", "backup", "failover"
)
| project TimeGenerated, ResourceGroup,
    ResourceProviderValue, ResourceId,
    Caller, OperationNameValue, ActivityStatusValue
| order by TimeGenerated desc
~~~

Query này chỉ là **bộ lọc điều tra rộng**. OperationNameValue có thể chứa write hợp lệ; Activity Logs chủ yếu phản ánh management-plane operations, không thay Key Vault/Storage data-plane diagnostics. Cần tune per resource provider và role/action, tránh alert noise. Nếu không xuất logs vào workspace, query trống không chứng minh không có hành động.

### 26.4. Cảnh báo backup gaps

Ví dụ RPO target Orders=15 phút:
- Xem **latest restorable point**, không chỉ job count.
- Alert nếu khoảng cách với current UTC vượt threshold có buffer hợp lý.
- Phân biệt backup lag tạm thời và sự cố kéo dài.
- Có owner/on-call và escalation path.
- Gắn recovery objective vào dashboard.
- Bảo đảm system clock/timezone và timestamp UTC chính xác.
- Khi alert, xác minh recovery points bằng tool/portal, không chỉ metadata cache.

Đừng cam kết alert có thể phát hiện mọi corrupt backup; cần thêm restore drills và integrity checks.

### 26.5. Theo dõi RTO thực từ diễn tập

Một timeline lab:

~~~text
09:00  Incident declared
09:10  Scope + root cause isolated
09:20  Recovery point approved
09:45  Restored resource created
10:05  Data validation finished
10:15  App canary passing
10:25  Traffic fully served

Observed RTO: 85 phút, từ 09:00 tới 10:25
~~~

Nếu mục tiêu RTO=60 phút, bài diễn tập **FAIL**, dù restore job đã completed lúc 09:45. Cần nêu rõ hành động cải thiện: warm standby, index restore, reduce backup size, pre-provision network, automate tests hay thay objective.

### 26.6. Audit restoration operation

Một restore job cần giữ:
- Incident/ticket ID và approvals.
- Resource ID/source/target, owner/region.
- Backup policy và recovery point timestamp UTC.
- Restore job ID, start/end times.
- Principal thực hiện, role và emergency access.
- Data validation results, row/file checksums.
- RPO/RTO đo được.
- Business reconciliation và exceptions.
- Cleanup/retain target decision.
- Evidence links có RBAC.

Không ghi secret values, database passwords hay user payment details trong work item.

## 27. Chi phí và tối ưu ngân sách phục hồi dữ liệu

### 27.1. Những loại chi phí

~~~text
Tổng chi phí data recovery architecture =
    Backup storage và transactions
  + Long-term retention capacity
  + Geo-redundant storage/replication
  + Warm standby hoặc cross-region compute
  + Recovery Services/Backup vault services nếu có phí
  + Encryption key management
  + Logging/diagnostic ingestion and retention
  + Network/egress/cross-region data transfer
  + Restore drill compute/storage/requests
  + Automation, monitoring và incident operations
~~~

Giá thực tế thay đổi theo region, SKU, redundancy, retention, data size, churn rate và Azure billing model. Dùng Azure Pricing Calculator, Azure Cost Management và service-specific pricing hiện hành; không sao chép giá cố định từ một bài học thành ngân sách.

### 27.2. Dữ liệu thay đổi nhiều làm tăng backup storage

Giả sử Blob source 5 TiB với nhiều phiên bản; retention 30 ngày không đơn giản là **5 TiB × 30** vì Storage có cơ chế snapshot/copy-on-write, change rate, data block granularity và tier/billing khác nhau. Ngược lại, retention versions có thể tăng đáng kể khi ứng dụng ghi đè các objects lớn hằng giờ.

Cần đo:
- Tổng protected capacity.
- Daily change rate và full vs incremental backup semantics.
- Number of versions/snapshots.
- Geo redundancy factor/egress.
- Backup operation frequency.
- Restore target storage temporary cost.
- Compression/dedup behavior nếu service hỗ trợ.
- Lifecycle rules và không được xóa sớm hơn compliance.

### 27.3. Hot standby hay cold restore?

| Tiêu chí | Cold restore | Warm/hot standby |
|---|---|---|
| Compute thường trực | Ít hoặc không | Có chi phí giữ sẵn |
| RTO thường gặp | Lâu hơn | Có thể ngắn hơn |
| RPO | Backup cadence/geo backup | Replication lag/consistency |
| Độ phức tạp | Restore workflow | Replication/failover/failback |
| Phù hợp | Reports, ít thay đổi, RTO dài | Orders/payments, RTO ngắn |
| Bảo vệ lỗi logic | Có nếu backup trước lỗi | Vẫn cần PITR backup riêng |
| Kiểm thử | Restore drill | Failover + restore drill |

Không mua active-active chỉ để bảo vệ một file hướng dẫn không quan trọng; nhưng cũng không chọn nightly backup cho ledger tài chính RPO 5 phút nếu không có event log phục hồi.

### 27.4. Tối ưu theo data tiers

- **Tier 0:** financial/system-of-record; PITR/geo, guarded backup, frequent drills.
- **Tier 1:** operational state quan trọng; backup/restore nhanh, retention phù hợp.
- **Tier 2:** business documents; versioning, soft delete, immutable retention theo policy.
- **Tier 3:** derived analytics; ưu tiên source archive và rebuild.
- **Tier 4:** ephemeral cache/temp; rebuild, có thể không backup.

Các tiers chỉ là **mô hình quản trị ví dụ**; phải gắn với RPO/RTO/RLO thật của business, không là Azure SKU tiers.

### 27.5. Thêm chi phí của kiểm thử, không bỏ nó

Một DR plan rẻ trên giấy nhưng chưa từng thử restore có rủi ro rất cao. Chừa ngân sách cho:
- Lab restore tài nguyên mới.
- Chạy integrity queries.
- Quota/compute vùng dự phòng.
- Kết nối VNet/Private DNS.
- Replay event archives.
- Kiểm tra Key Vault/CMK.
- Load testing sau failover.
- Cleanup có kiểm soát.

Một bài diễn tập hàng quý có thể phát hiện sớm backup gap hoặc key loss trước khi sự cố thật xảy ra.

## 28. Lab A: khôi phục SQL và Blob trong môi trường cô lập

### 28.1. Mục đích

Một đơn hàng cần khôi phục từ SQL PITR và một hóa đơn PDF bị ghi đè từ Blob version/snapshot. Lab chứng minh:
- Backup/recovery point đã có từ **trước sự cố**.
- Restore không ghi đè nguồn.
- Đọc và xác minh dữ liệu.
- So nghiệp vụ giữa hai services.
- RPO/RTO được đo.
- Chỉ cleanup khi owner phê duyệt.

### 28.2. Điều kiện an toàn

- Subscription/resource group **lab riêng**; budget và thời gian giữ.
- Một Azure SQL Database lab có sample Orders với dữ liệu giả.
- Một Blob Storage account lab đã bật các protection features được hỗ trợ từ trước khi tạo test data.
- Azure CLI/JDK client hoặc SQL client được cấp quyền tối thiểu.
- Không kết nối payment, email hoặc API production.
- Key Vault/CMK/Private DNS ở lab có thể dùng được.
- Có recovery timestamp nằm trong retention.
- Không sử dụng restore target trùng tên database/Blob source.

### 28.3. Bước 1: đọc cấu hình và lấy timestamp UTC

~~~bash
RG="rg-recovery-lab"
SQL_SERVER="sql-recovery-lab"
SOURCE_DB="orders_lab"
STORAGE="strecoverylab"

az account show --query "{subscription:id,tenant:tenantId}" -o json

az sql db show \
  --resource-group "$RG" \
  --server "$SQL_SERVER" \
  --name "$SOURCE_DB" \
  --query "{name:name,status:status}" \
  -o json

az sql db str-policy show \
  --resource-group "$RG" \
  --server "$SQL_SERVER" \
  --name "$SOURCE_DB" \
  -o json

az storage account blob-service-properties show \
  --resource-group "$RG" \
  --account-name "$STORAGE" \
  --query "{versioning:isVersioningEnabled,blobDelete:deleteRetentionPolicy,containerDelete:containerDeleteRetentionPolicy}" \
  -o json
~~~

Không chạy tạo/delete/restore nếu resource không thuộc lab đã phê duyệt.

### 28.4. Bước 2: tạo lỗi giả

Trong lab:
1. Tạo vài bản ghi Orders giả.
2. Upload invoice giả.
3. Ghi lại UTC timestamp trước khi gây lỗi.
4. Xóa một Order giả trong DB lab hoặc overwrite một Blob giả.
5. Ghi error UTC timestamp.
6. Bảo đảm không có user thật, data privacy issue hoặc hidden dependencies.

Không gây corruption giả trên production chỉ để thử backup.

### 28.5. Bước 3: SQL PITR thành DB mới

~~~bash
RESTORED_DB="orders_lab_restore_exercise"
RESTORE_TIME="2026-11-20T09:30:00Z"  # Thay bằng UTC lab hợp lệ

# Tạo database mới, có chi phí. Chỉ trong lab/approval.
az sql db restore \
  --resource-group "$RG" \
  --server "$SQL_SERVER" \
  --name "$SOURCE_DB" \
  --dest-name "$RESTORED_DB" \
  --time "$RESTORE_TIME"

az sql db show \
  --resource-group "$RG" \
  --server "$SQL_SERVER" \
  --name "$RESTORED_DB" \
  --query "{name:name,status:status}" \
  -o json
~~~

Lệnh không restore dữ liệu vào source DB. Chờ provisioning/restore hoàn tất, đăng nhập bằng Entra/SQL identity lab phù hợp và chạy SQL verification. Không suy đoán một recovery timestamp có dữ liệu nếu thời điểm đó nằm ngoài retention.

### 28.6. Bước 4: so dữ liệu SQL

Ví dụ T-SQL **đọc-only** trên restored DB và source DB:

~~~sql
SELECT COUNT(*) AS OrderCount
FROM dbo.Orders;

SELECT OrderId, Status, TotalMinorUnits
FROM dbo.Orders
WHERE OrderId IN ('demo-001', 'demo-002');
~~~

Sau đó kiểm tra:
- Order demo bị xóa có xuất hiện ở restored DB không?
- Orders hợp lệ được tạo sau lỗi có trong source DB không?
- Primary keys/foreign keys/unique constraints đúng?
- Payment/invoice IDs có khớp?
- Restore status và response time đủ tiêu chí?

Đừng copy toàn bộ restored database chồng lên source; lập kế hoạch **selective recovery** cho records cần khôi phục theo unique key và giao dịch được bảo vệ.

### 28.7. Bước 5: Blob version/snapshot

Với blob account đã cấu hình versioning/snapshots và dữ liệu giả:
1. Liệt kê versions của blob giả bằng portal/SDK hoặc Azure CLI phù hợp.
2. Xác định version ID trước overwrite.
3. Sao chép version cũ sang **recovery container/path**.
4. Kiểm tra kích thước/hash/PDF content.
5. Đối chiếu invoice number/amount với restored SQL Orders.
6. Không ghi đè current Blob nếu chưa có approval.
7. Chỉ chọn restore/promote đúng content bằng conditional ETag update.

CLI cụ thể để copy một historical version phụ thuộc auth mode, version ID, Blob type, API và tool version, nên cần đối chiếu cú pháp thực tế và dùng **tài khoản lab**; bài không mặc định một lệnh copy áp dụng được cho mọi HNS/account mode.

### 28.8. Bước 6: kết luận lab bằng số đo

~~~text
Incident simulated:         10:00 UTC
Restorable SQL point:       09:58 UTC
SQL data loss window:       2 phút
Blob recovered version:     09:59 UTC
Business verification:      10:48 UTC

Observed RPO SQL:           2 phút
Observed RTO to verified:   48 phút

Goal SQL RPO:               5 phút → PASS
Goal business RTO:          60 phút → PASS
~~~

Các số ở bảng là ví dụ. Người học phải dùng timestamps có thật từ lab, không ghi PASS chỉ vì mẫu minh họa nói vậy.

### 28.9. Cleanup

- Restore target database và Blob recovery container có thể tính phí; cleanup sau evidence/approval.
- Không xóa source data đang dùng bởi lab chung.
- Không purge vault/backup history hay keys.
- Không vô hiệu hóa backup chỉ để tiết kiệm phí mà không báo owner.
- Ghi teardown IDs, chi phí quan sát được và lessons learned.



## 29. Lab B: tabletop phục hồi Cosmos DB, queue và analytics

### 29.1. Tình huống

Một nhóm phát hiện:
- 13:00: ứng dụng Cosmos DB ghi sai trường cartTotal cho một số giỏ hàng.
- 13:05: Azure Service Bus chứa nhiều lệnh InvoiceRequested chưa xử lý.
- 13:10: các bảng Gold reports từ Databricks đã bị tính sai.
- 13:20: Incident được xác nhận.
- Orders SQL vẫn đúng và payment provider không mất dữ liệu.

Mục tiêu không phải xóa toàn bộ cloud resources, mà là lập **recovery map** và chứng minh có thể tránh double charge, duplicate invoice, bỏ sót Cart và báo cáo sai.

### 29.2. Quyết định trước restore

Trả lời:

1. Cosmos DB account đang dùng periodic hay continuous backup?
2. Earliest restorable time và recovery granularity là gì?
3. Có thể restore 12:59 sang account cô lập không?
4. Những carts hợp lệ được cập nhật sau 13:00 sẽ xử lý thế nào?
5. Service Bus Geo-DR hiện tại bảo vệ **message bodies** hay chỉ metadata?
6. Orders SQL có outbox rows đủ để tái phát missing InvoiceRequested không?
7. Worker đã tạo invoices nào và có idempotency key không?
8. Gold tables có thể rebuild từ Bronze raw không?
9. Event Hubs/Capture retention có đủ để replay?
10. Mất bao lâu để phục hồi các nghiệp vụ chính theo RLO?

### 29.3. Data mapping

| Nguồn | Giữ hay khôi phục? | Hành động đề xuất |
|---|---|---|
| Orders SQL đúng | Giữ | Không PITR/overwrite |
| Payment provider đúng | Giữ | Read-only reconciliation |
| Cosmos Cart sai từ 13:00 | Restore cô lập trước lỗi | Merge chọn lọc theo cartId/version |
| Service Bus active messages | Giữ/khảo sát | Không xóa queue, hạn chế consumers tạm thời |
| SQL Outbox | Nguồn phát lại | Replay event còn thiếu, idempotent |
| Invoice Blob | Kiểm tra | Không regenerate nếu đã có invoice hợp lệ |
| Gold analytics sai | Rebuild | Từ Bronze/Silver đã được xác minh |
| Key Vault/identities còn tốt | Giữ | Không rotate không cần thiết |

Không restore mọi dịch vụ về 12:59 chỉ vì một bảng sai. **Giữ nguyên dữ liệu tốt** là thành phần quan trọng của recovery correctness.

### 29.4. Kế hoạch thực thi

~~~mermaid
flowchart TD
    A["Freeze faulty Cart writer"] --> B["Restore Cosmos to isolated target"]
    B --> C["Identify corrupted cart records"]
    C --> D["Merge validated records, preserve good updates"]
    A --> Q["Pause unsafe invoice consumers"]
    Q --> O["Compare SQL Outbox and invoice state"]
    O --> R["Replay only missing intents"]
    D --> V["Business checks"]
    R --> V
    V --> G["Rebuild analytics Gold"]
    G --> Z["Resume traffic and monitor"]
~~~

Cần nêu rõ ai thực hiện từng bước, approvals, dữ liệu dùng để so sánh và rollback của chính hành động recovery.

### 29.5. Giữ lịch sử thay vì xóa dấu vết

Không xóa các Cart sai ở primary trước khi export forensic evidence và có plan phục hồi; việc xóa ngay có thể:
- Làm mất dấu thời gian đầu tiên bị lỗi.
- Tạo thêm change feed/delete events.
- Làm dữ liệu sai replicate.
- Khiến đối soát payments/orders phức tạp.
- Làm hỏng khả năng kiểm tra nguyên nhân.

Có thể đóng băng write paths, copy data/logs được phân quyền và tiến hành sửa chọn lọc. Khi có PII, áp retention/forensics policy.

### 29.6. Tiêu chí PASS

- Cosmos data đã sửa đúng những records bị ảnh hưởng.
- Không rollback carts hợp lệ cập nhật sau 13:00 ngoài ý muốn.
- Orders SQL và payment provider không bị sửa sai.
- Outbox/message reconciliation không bỏ sót hoặc gửi trùng side effects.
- Invoice PDFs và ledger totals hợp lệ.
- Gold reports được rebuild từ source records tin cậy.
- App có thể xử lý carts mới.
- RPO/RTO được đo và so với mục tiêu.
- Không có sensitive data trong public logs.
- Evidence và owner approval được lưu.

## 30. Runbook theo từng dạng sự cố

### 30.1. Runbook A: một nhóm Orders bị DELETE nhầm trong Azure SQL

1. Phát hiện qua alert/audit/business check; xác định incident UTC.
2. Dừng job/ứng dụng tạo DELETE sai, bảo vệ logs.
3. Xác định first bad transaction từ DB/audit logs.
4. Kiểm tra PITR retention và latest restorable time.
5. Phê duyệt timestamp trước lỗi và target DB cô lập.
6. Restore tới **database mới**, không overwrite source.
7. Xác minh row counts, keys, foreign keys, constraints.
8. Phân tích good writes sau timestamp để tránh mất dữ liệu hợp lệ.
9. Tạo script selective merge có transaction/rollback.
10. Dry run trên staging/recovery copy, có DBA review.
11. Áp vào primary khi được phê duyệt.
12. Kiểm tra Orders–Payments–Invoices và outbox events.
13. Quan sát p95/5xx/SQL health, mở lại writer.
14. Ghi RPO/RTO và nguyên nhân, tránh lặp incident.

### 30.2. Runbook B: xóa hoặc ransomware trên Blob/Files

1. Cô lập principal/process đang xóa/ghi dữ liệu.
2. Giữ diagnostic logs, audit, affected object inventory.
3. Kiểm tra versioning/soft delete/snapshots/backup policy **đã bật từ trước**.
4. Tìm earliest bad overwrite/delete.
5. Chọn versions/snapshot trước lỗi.
6. Nếu nghi bị xâm nhập, restore vào account/container/share **cô lập**.
7. Kiểm tra file count, hashes, ACLs, metadata và malware.
8. So với SQL records, không lấy một invoice cũ sai làm chứng từ đúng.
9. Restore chọn lọc hoặc tạo correction record phù hợp immutability.
10. Kiểm tra app pointers, caching/CDN, SAS expiration.
11. Chỉ mở lại access khi không còn principal bị compromise.
12. Rotate tokens/keys tại nguồn nếu cần, ghi audit và tăng bảo vệ.

### 30.3. Runbook C: region outage

1. Phân biệt Azure region outage với DNS/IAM/app deployment issue.
2. Kích hoạt DR plan theo owner và business impact.
3. Kiểm tra sức khỏe secondary region, quotas, capacity, network.
4. Đo replication lag/last sync để ước lượng potential RPO.
5. Chọn **failover hot replica** hay **geo-restore backup** theo data integrity.
6. Phê duyệt chấp nhận mất dữ liệu nếu forced failover có rủi ro.
7. Dựng/restore Key Vault/identity/Private DNS và app runtime theo dependency graph.
8. Ngăn split-brain writers; tắt producers/consumers nếu cần.
9. Verify DB/Blob/message source state.
10. Bật một canary cohort hoặc read-only mode.
11. Reconcile Orders/outbox/payments và worker offsets.
12. Chuyển Front Door/DNS/app endpoints có kiểm soát.
13. Theo dõi RLO/RPO/RTO và chi phí DR.
14. Không failback vội khi primary trở lại; lập kế hoạch đồng bộ hai hướng.

### 30.4. Runbook D: Cosmos DB corrupted vì mass update

1. Dừng faulty job và các writes gây lỗi.
2. Xác định account API, backup mode và retention.
3. Tìm timestamp trước bad update.
4. Restore to isolated target theo supported API.
5. Kiểm tra container configs, partition key, indexing, TTL.
6. Phân biệt records bị sửa sai và updates hợp lệ trong incident window.
7. Thiết kế merge với ETag/conditional writes hoặc idempotency.
8. Thử trên sample/staging và monitor RU throttling.
9. Chạy repair từng batch, ghi tiến độ.
10. Verify cart/customer invariants, multi-region consistency và change feed.
11. Re-enable writes, giữ target backup để audit có thời hạn.
12. Đánh giá backup mode/permissions nhằm giảm blast radius.

### 30.5. Runbook E: Service Bus namespace mất hoặc message backlog biến mất

1. Xác nhận namespace outage hay application consumer errors.
2. Xác định tier và DR mode thực: alias metadata-only hay data geo-replication.
3. Kiểm tra primary/secondary messaging state, active messages, DLQ.
4. Dừng senders/consumers gây duplicate trong khi chuyển.
5. Chọn namespace/alias/failover theo playbook được hỗ trợ.
6. Nếu messages không được replicated, dùng **SQL Outbox/immutable event archive** phục hồi intent.
7. Replay theo stable message ID, idempotent handlers.
8. Kiểm tra scheduled messages, sessions và locks theo service semantics.
9. So Orders accepted vs invoices produced và queue backlog.
10. Test chính sách DLQ/retry/poison messages.
11. Khôi phục traffic theo rate limits và monitor errors.
12. Ghi known missing/duplicated messages, RPO và root cause.

### 30.6. Runbook F: mất Key Vault CMK hoặc secret

1. Đánh giá xóa nhầm, policy denial, network outage hay compromise.
2. Dừng purge/delete/rotation tiếp theo.
3. Kiểm tra soft deleted object/vault, retention và purge protection.
4. Khôi phục key/secret/certificate đúng object nếu supported.
5. Khôi phục role/access policy, Private DNS và identity permissions.
6. Xác minh key version/protector association.
7. Test decrypt/unwrapping trên resource phục hồi cô lập.
8. Nếu downstream credential đã bị revoke, phát hành/rotate lại hợp lệ.
9. Kiểm tra các databases/storage encryption dependencies.
10. Audit người thực hiện, logs và thay đổi IAM.
11. Nếu key không khôi phục được, đánh giá backup/recovery khác; không hứa vẫn giải mã được.
12. Update key lifecycle và DR drill.

### 30.7. Runbook G: một restore job thành công nhưng app vẫn lỗi

1. Kiểm tra app đang trỏ đúng recovery endpoint/database chưa.
2. Kiểm tra schema/engine version, DB users và firewall.
3. Kiểm tra Entra identity, Key Vault secrets và CMK.
4. Kiểm tra VNet/Private Endpoint/DNS theo region target.
5. Kiểm tra App Configuration, feature flags và old app binary compatibility.
6. Kiểm tra missing dependent Blob/queue/caches.
7. Kiểm tra data corruption/row-level invariants.
8. Xem SDK timeout, 401/403/429, DB connections.
9. Thử read-only business smoke test có kiểm soát.
10. Nếu dữ liệu sai, rollback cutover hoặc tiếp tục repair; không khai báo DR PASS.

### 30.8. Runbook H: ransomware và compromised production identity

1. Kích hoạt security incident response; phân quyền Incident Commander.
2. Ngăn tiếp tục ghi/xóa, cô lập credentials và workloads theo security policy.
3. Bảo vệ evidence/logs/backup inventories.
4. Xác định earliest compromise/bad data timestamp.
5. Chọn recovery points **clean** trước infection.
6. Dựng recovery environment tách quyền/identities.
7. Verify image provenance, patch/vulnerability baseline.
8. Restore dữ liệu và kiểm tra malware/corruption.
9. Rotate exposed secrets/keys theo service guidance, không vô hiệu hóa key cần giải mã trước khi tạo recovery path.
10. Kiểm tra business integrity và user access control.
11. Canary traffic, monitor suspicious behavior.
12. Ghi legal/compliance notifications, postmortem và thay đổi guardrails.

### 30.9. Failback runbook sau cross-region DR

1. Xác định region DR hiện là source of truth.
2. Không cho primary cũ nhận writes tự động.
3. Đánh giá lag và divergent data ở primary.
4. Chọn re-seed/reverse replication/backup restore theo dịch vụ.
5. Khôi phục network/keys/identities hai vùng.
6. Thực hiện reconciliation trên dữ liệu mới trong thời gian DR.
7. Test load và business transactions ở primary được dựng lại.
8. Đóng băng hoặc hạn chế writes đúng thời điểm cutback nếu cần.
9. Chuyển traffic sau approval và health checks.
10. Theo dõi replication, SQL/Cosmos/Storage/queues.
11. Bật lại backup policies/geo redundancy.
12. Ghi actual RPO/RTO và lessons learned.

### 30.10. Khi không có bản phục hồi phù hợp

Đôi khi backup bị thiếu, đã hết retention hoặc CMK không còn. Khi đó:
- **Không bịa rằng Azure sẽ phục hồi chắc chắn được.**
- Ghi rõ missing recovery point, thời điểm và data classes bị ảnh hưởng.
- Tìm các nguồn hợp pháp như immutable archive, payment ledger, outbox, exported reports hoặc partner records.
- Đánh giá khả năng rebuild bằng business event replay.
- Tránh tự ý dùng production transaction logs theo cách không được engine hỗ trợ.
- Thông báo business risk và pháp lý theo quy trình.
- Chỉ áp data repair/reconciliation được phê duyệt.
- Cập nhật backup architecture và giám sát để tránh tái diễn.

## 31. Diễn tập DR: từ tabletop đến full restore

### 31.1. Mức độ diễn tập

| Mức | Hành động | Mục đích |
|---|---|---|
| **L0: review** | Review ma trận, policies, owners | Phát hiện tài liệu thiếu |
| **L1: tabletop** | Mô phỏng mất DB/region, không thay tài nguyên | Xác định decisions/dependencies |
| **L2: isolated restore** | Restore DB/Blob/VM vào target test | Kiểm chứng recovery point |
| **L3: workload validation** | Chạy app test trên dữ liệu phục hồi | Đo consistency và RTO |
| **L4: failover exercise** | Chuyển một phạm vi traffic được duyệt | Test routing và capacity |
| **L5: full business DR drill** | End-to-end theo governance | Đo RPO/RTO/RLO toàn nghiệp vụ |

Không tự làm L4/L5 trên production vì một người muốn “thử failover”; cần planned change, approvals và rollback plan riêng.

### 31.2. Kế hoạch buổi diễn tập

~~~text
DR drill ID: DR-ORDERS-LAB-001
Scope: Orders SQL + Invoice Blob + outbox replay
Recovery environment: isolated lab subscription
Start UTC: <approved timestamp>
Data sensitivity: synthetic
Target RPO: <= 15 minutes
Target RTO: <= 120 minutes
Target RLO: read/create test order and verify invoice
Incident commander: assigned owner
Database owner: assigned owner
Security approver: assigned owner
Rollback/cleanup plan: documented
Evidence: monitoring, job IDs, counts, checksums
~~~

Đây là template, không phải Azure API schema. Buổi diễn tập tốt có người quan sát độc lập và ghi nhận những thao tác bất ngờ, chứ không sửa report cho khớp SLA.

### 31.3. Checklist thực hiện

1. Xác minh permissions/quotas trước thời điểm diễn tập.
2. Chụp trạng thái backup retention và recovery points.
3. Đặt timestamp UTC, freeze test writes.
4. Chọn một lỗi giả có tính đại diện.
5. Tạo restored resources vào vùng cô lập.
6. Khôi phục Key Vault/identity/network dependencies nếu kịch bản yêu cầu.
7. Mở app bằng credentials/test data đúng.
8. Reconcile DB/outbox/Blob/messages.
9. Chạy smoke, integration và security tests.
10. Đo observed data loss window và business recovery time.
11. So với RPO/RTO/RLO mục tiêu.
12. Ghi failed steps, human errors và cải tiến.
13. Cleanup sau approval; bảo toàn backup policies.
14. Lập lịch repeat sau thay đổi kiến trúc lớn.

### 31.4. Những lỗi diễn tập thường phát hiện

- Backup retention thấp hơn hợp đồng RPO.
- Source account có feature chưa bật, không thể phục hồi deletion cũ.
- DR region không có đủ quota VM/DB.
- Storage backups phụ thuộc key đã bị purge.
- Restore DB xong nhưng App Service không vào được Private Endpoint.
- Service Bus Geo-DR chỉ chuyển metadata, mất business messages.
- Consumer chạy trước data reconciliation, làm invoice trùng.
- SQL schema mới không tương thích app image cũ.
- Restore target được đặt nhầm trong resource group production.
- Runbook dùng service principal hết hạn.
- Pipeline GitOps tự ghi đè trạng thái restore/cutover.
- Log Analytics dữ liệu quá ít để giải thích RPO/RTO.

### 31.5. Đánh giá theo điểm quan sát được

Để kết luận:
- **Recovery point verified:** PASS/FAIL.
- **Data integrity verified:** PASS/FAIL.
- **App/service readiness:** PASS/FAIL.
- **Business invariants:** PASS/FAIL.
- **RPO objective:** PASS/FAIL theo timestamp thực.
- **RTO objective:** PASS/FAIL theo business recovery time.
- **Security/isolation:** PASS/FAIL.
- **Observability/audit:** PASS/FAIL.
- **Cleanup/owner sign-off:** PASS/FAIL.

Một buổi DR drill có thể fail một tiêu chí và vẫn có giá trị lớn — đó là kết quả cần sửa kiến trúc, không phải lý do thay số đo để được “PASS”.



## 32. Case study: phục hồi hệ thống bán hàng trên Azure

### 32.1. Kiến trúc và phân loại dữ liệu

Một công ty có:
- **Azure Front Door:** định tuyến traffic.
- **Spring Boot trên AKS:** Orders API, Payment Integration, Invoice Worker.
- **Azure SQL Database:** đơn hàng và SQL Outbox, nguồn sự thật của accepted orders.
- **Azure Cosmos DB:** carts và product recommendations.
- **Azure Service Bus:** InvoiceRequested command delivery.
- **Azure Blob Storage:** invoice PDFs và một bản archive riêng theo chính sách.
- **Azure Key Vault:** partner payment token/CMK.
- **Azure Data Lake Storage Gen2 + Databricks:** reports.
- **Azure Managed Redis:** cache dữ liệu giá/hàng hóa.
- **Azure Monitor/Application Insights:** giám sát và incident evidence.

~~~mermaid
flowchart LR
    U["Customers"] --> FD["Azure Front Door"]
    FD --> API["Orders API / AKS"]
    API --> SQL["Azure SQL + Outbox"]
    API --> COS["Cosmos DB Carts"]
    API --> KV["Key Vault"]
    SQL --> P["Outbox Publisher"]
    P --> SB["Service Bus"]
    SB --> W["Invoice Worker"]
    W --> B["Blob invoices"]
    SQL --> ETL["Data pipelines"]
    B --> ETL
    ETL --> LAKE["ADLS / Delta / Reports"]
    API --> RED["Redis cache"]
    API -. "Telemetry" .-> MON["Azure Monitor"]
    W -. "Telemetry" .-> MON
~~~

### 32.2. Business objectives

| Nghiệp vụ | RPO mục tiêu | RTO mục tiêu | RLO trong giai đoạn đầu |
|---|---|---|---|
| Xác nhận orders | 5 phút | 60 phút | Đọc và tạo orders hợp lệ |
| Thanh toán | Không double-charge, đối soát 100% intent | 90 phút | Nhận status/không capture trùng |
| Invoice PDF | 60 phút hoặc regenerate từ data hợp lệ | 4 giờ | Tra cứu chứng từ cũ |
| Carts | 15 phút | 2 giờ | Khách có thể xem/sửa cart |
| Product cache | Có thể mất | 30 phút | API hoạt động qua DB fallback |
| Reporting | 24 giờ | 24 giờ | Báo cáo có cảnh báo dữ liệu chưa mới |

**RPO 5 phút cho Orders không tự đảm bảo từ một region backup configuration bất kỳ**. Nhóm phải chứng minh cơ chế SQL backup/replication/replay phù hợp. Payment objective thiên về **business invariant** hơn timestamp, vì không được tự capture lại một payment chỉ vì local restore thiếu record.

### 32.3. Sự cố chính

Giả lập:
- 09:40: release lỗi gây mass DELETE trên Orders SQL.
- 09:43: application phát một số InvoiceRequested qua outbox cho orders mới.
- 09:45: cảnh báo SQL rows giảm bất thường.
- 09:50: incident commander ngăn faulty writer và pause invoice worker.
- 09:55: xác định cần PITR trước 09:40, nhưng không được bỏ giao dịch hợp lệ từ 09:40–09:50.
- 10:00: Azure SQL restore tới database cô lập đang được tạo.
- 10:30: DB được restore, bắt đầu reconcile.
- 10:55: selective merge hoàn tất và worker có thể chạy lại.
- 11:05: business smoke tests pass, traffic được mở.

### 32.4. Vì sao không restore tất cả về 09:39?

| Thành phần | Trạng thái sau lỗi | Quyết định |
|---|---|---|
| Orders SQL | Bị xóa một nhóm records | Restore **bản sao 09:39**, merge chọn lọc |
| Cosmos DB Carts | Không bị ảnh hưởng | Giữ nguyên |
| Payment provider | Đã capture hợp lệ | Giữ nguyên, dùng reconciliation API |
| Service Bus | Có một số messages đã gửi | Giữ, không xóa namespace |
| SQL Outbox | Có rows mới hợp lệ | Đối soát/replay thiếu, không drop |
| Blob invoice | Có một số PDFs mới hợp lệ | Giữ, kiểm tra references |
| Redis cache | Có thể chứa trạng thái cũ | Invalidate/rebuild |
| Analytics Gold | Có thể bị lệch do SQL DELETE | Rebuild sau SQL repair |
| Key Vault | Hoạt động bình thường | Không rotate không cần thiết |

Đổi tất cả về 09:39 có thể làm mất các payment/orders đã thành công trong 10 phút sau đó. **Khôi phục chọn lọc và reconcile** là yêu cầu thiết kế, không phải một biến thể của complete rollback đơn giản.

### 32.5. Recovery timeline và phép đo

Trong giả định trên:
- Incident bắt đầu 09:40.
- First known good SQL recovery point chọn 09:39.
- Nếu chỉ xét PITR image, khoảng cách dữ liệu tiềm năng **1 phút** tại thời điểm lỗi; nhưng các writes từ 09:39–09:50 cần selective recovery/replay.
- Detection: 09:45, 5 phút sau lỗi.
- Containment: 09:50, 10 phút sau lỗi.
- SQL restore có thể dùng lúc 10:30.
- Business RLO đạt lúc 11:05.
- **Observed business recovery time = 85 phút** từ 09:40 đến 11:05.

Nếu mục tiêu Orders RTO=60 phút, **buổi diễn tập FAIL về RTO**, dù database restore job đã hoàn tất trong 50 phút và dữ liệu đã được đối soát. Nhóm có thể cải thiện bằng:
- Automation xác định affected rows.
- Truy vấn audit/CDC/temporal history có governance.
- Phân luồng restore và business verification chạy song song an toàn.
- Tối ưu target compute/DB restore size.
- Tăng cảnh báo về suspicious deletes.
- Giảm thời gian human approvals cho emergency restore theo policy.

### 32.6. Những rủi ro cần xử lý thêm

- SQL restore DB đã tạo ra nhưng identity ứng dụng không có quyền.
- Blob invoice do worker mới tạo không có order record tương ứng sau SQL recovery.
- Outbox replay gửi duplicate Service Bus commands.
- Payment provider đã charge nhưng local order status bị mất.
- AKS app old version không tương thích schema sau migration.
- Key Vault token đã rotate trong lúc incident.
- Redis cache giữ dữ liệu sai dù DB đã sửa.
- Gold report chưa rebuild nhưng user thấy số doanh thu sai.

Mỗi rủi ro có owner, validation test và phép đo phục hồi riêng.

### 32.7. Nâng cấp thiết kế sau sự cố

Nhóm quyết định:
1. Thêm cảnh báo theo business metric khi SQL row count giảm bất thường.
2. Tách quyền DELETE của runtime khỏi operations không cần thiết.
3. Xây temporal/audit history hợp lệ cho entity quan trọng.
4. Diễn tập PITR vào recovery DB theo quý.
5. Dùng SQL Outbox stable IDs và idempotent consumers.
6. Giữ invoice Blob versions và backup phù hợp.
7. Tạo automated reconciliation Orders–Payments–Invoices.
8. Bổ sung dry-run recovery scripts và manual approvals cho merge.
9. Kích hoạt Key Vault soft delete/purge protection theo policy.
10. Ghi mục tiêu RPO/RTO và cách đo thực trong release governance.

### 32.8. Một sự cố khác: region outage

Nếu cả Azure SQL primary và AKS region chính mất:
- Không thể chỉ PITR SQL vào cùng region đang outage.
- Phải dùng geo-capable DB recovery/failover theo cấu hình thực.
- Dựng AKS/network/identity tại region DR.
- Xem Storage redundancy/Blob recovery và Service Bus DR mode.
- Kiểm tra geo-replication lag trước forced failover.
- Chặn split-brain writes và xác nhận new source of truth.
- Mở traffic dần qua Front Door khi business data đã coherent.

Đây là **một đường recovery khác** so với việc một application xóa nhầm records. Không dùng một runbook duy nhất cho mọi nguyên nhân.

## 33. Những sai lầm phổ biến và cách tránh

| Sai lầm | Hệ quả | Cách làm phù hợp |
|---|---|---|
| Đồng nhất LRS/ZRS/GRS với backup | Delete lỗi replicated, không có recovery point | Backup/PITR/versioning độc lập |
| Coi soft delete là immutable backup | Attacker vẫn có thể thao tác tùy quyền | Least privilege + immutable/isolated copies |
| Chỉ tính RTO của restore job | App vẫn chưa hoạt động | Đo tới business smoke PASS |
| Chỉ chọn backup frequency theo RPO | Backup failure/lag làm mất dữ liệu quá mức | Latest restorable point + alerts |
| Coi read replica là snapshot cũ | Corruption replicated | PITR trước bad write |
| Restore SQL đè primary ngay | Mất legitimate writes sau sự cố | Restore DB mới và selective merge |
| Đổi toàn bộ Cosmos DB account mà không reconcile | Mất cart updates hợp lệ | Restore cô lập, merge, kiểm tra TTL/ETag |
| Tin Cosmos multi-region giải quyết DELETE nhầm | Delete replicate | Continuous/periodic backup đúng nhu cầu |
| Không kiểm tra Cosmos backup mode | Không có PITR cần thiết | Inventory API/tier/retention |
| Blob GRS nhưng không versioning | Overwrite không có version cũ | Bật versioning/soft delete/backup |
| Bật soft delete sau khi dữ liệu đã bị xóa | Không thể quay lại dữ liệu chưa từng bảo vệ | Preconfigure + thử restore |
| Xóa Blob versions vì lifecycle quá ngắn | Không còn điểm khôi phục | Retention policy theo data class |
| Khóa WORM cho dữ liệu chưa kiểm tra | Bị giữ dữ liệu sai không sửa được | Validation trước immutability |
| Áp Blob checklist sang ADLS HNS | Feature incompatible, missing ACLs | Kiểm tra HNS support matrix |
| Coi Azure Files snapshot là DB transaction backup | Restore database không nhất quán | Engine-aware backup/quiesce |
| Coi AKS etcd backup là mọi state | External DB/PV mất | Backup theo data path riêng |
| Coi ASR là backup ransomware | Corruption được replicate | Independent clean recovery copy |
| Coi Service Bus metadata Geo-DR là message replication | Messages mất sau failover | Xác minh DR mode + Outbox/archive |
| Coi checkpoint Event Hubs là event backup | Hết retention không replay được | Capture/archive và retention |
| Redis là nguồn duy nhất nhưng không persistence | Mất carts/sessions | Managed DB hoặc backup phù hợp |
| Rotate/purge CMK trước khi restore | Backup không giải mã được | Key lifecycle/recovery plan |
| Backup có nhưng DR region thiếu quota | RTO không đạt | Preflight capacity và diễn tập |
| Copy production DB sang dev công khai | Lộ PII/secret | Recovery environment cô lập |
| Chọn cùng UTC timestamp cho mọi service và coi nhất quán | Business state lệch | Reconciliation và invariants |
| Chạy queue workers trước DB recovery | Duplicate/lost side effects | Restore order/worker draining |
| Traffic rollback thay data restore | State sai vẫn còn | Plan business correction |
| Giữ only latest image tag | Không redeploy stable | Immutable digest/artifact retention |
| Dừng monitoring trong DR để tiết kiệm | Không có evidence | DR telemetry budget |
| Không diễn tập failback | Split-brain sau primary trở lại | Explicit reverse sync/cutback |
| Báo DR PASS khi API 200 | Payments/invoices chưa đúng | RLO/business acceptance |

### 33.1. Một quy tắc tổng hợp

**Mỗi dạng lỗi cần một câu trả lời riêng:**
- Lỗi **availability** → HA/replica/failover.
- Lỗi **logic/corruption** → backup/PITR/versioning/reconciliation.
- Lỗi **security compromise** → isolation/immutable clean copies/key rotation.
- Lỗi **metadata/config** → IaC/Git/identity recovery.
- Lỗi **event loss** → durable outbox/event archive/replay.
- Lỗi **derived state** → rebuild từ source.

Nếu một đề xuất chỉ có một ô “replicated = yes” cho tất cả các loại sự cố, thiết kế chưa đủ.

## 34. Checklist thiết kế phục hồi dữ liệu trước production

### 34.1. Business objectives

- [ ] Đã phân loại mỗi dataset là source of truth, derived, cache, archive hay messaging.
- [ ] Có business owner và data classification.
- [ ] RPO theo phút/giờ được phê duyệt, không suy ra từ backup cadence.
- [ ] RTO đo đến business capability chứ không chỉ restore job success.
- [ ] RLO rõ: read-only, accept writes, payments hoặc full service.
- [ ] RTO/RPO được đánh giá cho accidental delete, ransomware và region outage riêng.
- [ ] Có legal retention/data residency/PII constraints.
- [ ] Có danh sách dependencies/critical path và restore order.

### 34.2. Azure SQL/Postgres/MySQL/Cosmos

- [ ] Azure SQL STR/LTR và backup redundancy/geo support đã kiểm tra.
- [ ] SQL PITR tạo DB mới và selective merge được diễn tập.
- [ ] SQL geo-replica/failover group không bị coi là backup corruption.
- [ ] Managed Instance instance-level config/SQL Agent/jobs có DR plan.
- [ ] PostgreSQL/MySQL Flexible Server backup retention/geo options đúng SKU.
- [ ] Restore Flexible Server mới, identities/network/roles được kiểm thử.
- [ ] Cosmos DB backup mode periodic/continuous đúng API/tier.
- [ ] Cosmos PITR, TTL, unique keys, partitioning và restore target được hiểu.
- [ ] Multi-region replication/conflict policy đã được kiểm chứng.
- [ ] Có query/checksum/business integrity tests sau restore.

### 34.3. Blob/ADLS/Files/VM/AKS

- [ ] Blob soft delete, container soft delete và versioning theo object/account hỗ trợ.
- [ ] Blob operational/vaulted backup và immutability được chọn theo nhu cầu.
- [ ] Storage GRS/RA-GRS và replication lag được đánh giá.
- [ ] HNS/ADLS Gen2 feature support, ACLs và Delta logs được bảo vệ.
- [ ] Azure Files snapshots/backup hỗ trợ exact SMB/NFS/tier.
- [ ] Azure Files recovery kiểm tra SMB/NFS permissions và file handles.
- [ ] VM backup chọn app-consistent strategy khi cần.
- [ ] ASR không được thay thế backup clean recovery point.
- [ ] AKS GitOps/IaC, CSI volumes và external DB backups được phân tách.
- [ ] Kubernetes restore đã thử CRD/identity/network order.
- [ ] Storage account/backup data không thể bị runtime principal xóa bừa bãi.

### 34.4. Messaging, cache và analytics

- [ ] Service Bus Geo-DR mode bảo vệ metadata hay message bodies đã xác nhận.
- [ ] Có Outbox/idempotency và replay plan cho accepted business intents.
- [ ] Azure Event Hubs retention, Capture, checkpoint và archive policy hợp lệ.
- [ ] Message schema version và DLQ recovery được kiểm thử.
- [ ] Azure Queue Storage không bị dùng như lịch sử events vô hạn.
- [ ] Redis cache có thể rebuild hoặc có persistence/backup đúng nghiệp vụ.
- [ ] ADLS Bronze raw và Databricks/Synapse/ADF pipeline code được giữ.
- [ ] Delta time travel retention/VACUUM không bị gọi là backup hoàn chỉnh.
- [ ] Analytics rebuild workload/compute đủ để đạt RTO.

### 34.5. Security, access và operations

- [ ] Key Vault CMKs/versions và purge protection theo yêu cầu.
- [ ] Managed identities/Entra RBAC và break-glass plan được chuẩn bị.
- [ ] Private DNS/VNet/NSG/Firewall cho recovery region đã được thử.
- [ ] DR region có quota/capacity/network endpoints thực.
- [ ] Recovery target được cô lập, PII/credentials có controls.
- [ ] Azure Monitor alerts cho backup gaps, failures, policy drift và unusual delete.
- [ ] Backup/restore jobs có owners, retention và audit trail.
- [ ] Có immutable/independent clean copy khi cyber threats yêu cầu.
- [ ] Có approval trước failover/delete/purge/data merge.
- [ ] Không dùng plaintext secrets trong IaC/ticket/scripts.
- [ ] RPO/RTO/RLO được đo trong restore drills.
- [ ] Có runbooks, on-call, release gate và cleanup plan.

### 34.6. Cost, review và governance

- [ ] Storage backup retention/copy size/geo cost được dự trù.
- [ ] Có budget cho restore drill và recovery target resources.
- [ ] Phân loại dữ liệu theo criticality để tránh over-protect cache.
- [ ] Có Cost Management tags/alerts và chi phí monitoring.
- [ ] Backup policies/SLAs được review sau khi tăng data volume.
- [ ] Đã diễn tập region outage và accidental delete riêng.
- [ ] Có failback plan và split-brain prevention.
- [ ] Có evidence rằng restored app thực sự xử lý được giao dịch.
- [ ] Thời hạn giữ stable artifact/keys/backup hợp lý.
- [ ] Các exceptions được owner phê duyệt và có deadline.



## 35. Câu hỏi tự kiểm tra

1. **RPO là gì?** Mức mất dữ liệu tối đa được chấp nhận, đo theo thời gian giữa sự cố và điểm phục hồi.
2. **RTO là gì?** Thời gian mục tiêu để năng lực nghiệp vụ/dịch vụ được khôi phục.
3. **RLO có ý nghĩa gì?** Mức dịch vụ phải trở lại khi đạt RTO, ví dụ chỉ đọc hay xử lý thanh toán đầy đủ.
4. **Backup retention khác backup frequency ở đâu?** Retention là thời gian giữ; frequency là khoảng cách tạo các điểm sao lưu.
5. **Vì sao backup mỗi 15 phút không bảo đảm RPO 15 phút?** Backup có thể lỗi/lag hoặc recovery point chưa usable.
6. **Một restore job completed có đồng nghĩa RTO đạt không?** Không, còn xác minh và khôi phục ứng dụng.
7. **Zone redundancy bảo vệ trước điều gì?** Lỗi một availability zone trong region hỗ trợ.
8. **ZRS có giải quyết mất cả region không?** Không.
9. **GRS có replication đến vùng phụ đồng bộ tuyệt đối không?** Không, cross-region thường asynchronous.
10. **RA-GRS có cho phép đọc secondary theo hỗ trợ không?** Có, trước failover theo semantics read access của Storage.
11. **GRS có cứu được Blob bị DELETE sai không?** Không mặc định; deletion có thể replicate, cần soft delete/versioning/backup.
12. **Replica có thay backup PITR không?** Không, corruption có thể được replicate.
13. **Immutability khác soft delete thế nào?** Immutability hạn chế sửa/xóa trong retention theo policy, soft delete giúp khôi phục deleted objects trong window.
14. **Resource lock có thay immutable backup không?** Không.
15. **System of record là gì?** Nguồn dữ liệu có thẩm quyền để quyết định trạng thái nghiệp vụ.
16. **Derived analytics data có thể phục hồi bằng gì?** Rebuild từ nguồn gốc và versioned ETL nếu còn đầy đủ.
17. **Cache Redis có cần RPO như Orders SQL không?** Không nếu chỉ là dữ liệu dẫn xuất; có nếu chứa state duy nhất.
18. **Azure SQL PITR giải quyết tình huống gì tốt nhất?** Phục hồi DB về thời điểm trước delete/corruption trong retention.
19. **Azure SQL PITR có mặc định undo một hàng ở DB hiện tại không?** Không, thường restore thành database mới rồi merge chọn lọc.
20. **Vì sao không restore đè toàn Orders DB khi chỉ mất 100 rows?** Sẽ mất những writes hợp lệ xảy ra sau timestamp chọn.
21. **Azure SQL LTR phục vụ mục tiêu gì?** Lưu recovery copies dài hạn/compliance theo policy và hỗ trợ.
22. **LTR có giống PITR từng giây trong nhiều năm không?** Không, LTR thường có restore points rời rạc.
23. **SQL active geo-replication có bảo vệ trước UPDATE sai không?** Không, UPDATE có thể replicate.
24. **Forced geo-failover có nguy cơ mất dữ liệu không?** Có, theo replication lag và dịch vụ.
25. **SQL Managed Instance có giống SQL Database single DB ở mọi restore API không?** Không.
26. **Zone-redundant HA PostgreSQL có đồng nghĩa geo backup không?** Không.
27. **PostgreSQL/MySQL Flexible Server PITR thường tạo server mới không?** Thường có, theo service restore flow.
28. **Một read replica có thay backup không?** Không.
29. **Cosmos DB Periodic backup khác Continuous thế nào?** Periodic có backup points rời rạc; Continuous hỗ trợ PITR trong retention theo capability.
30. **Cosmos DB multi-region có tự cứu container bị DELETE sai không?** Không.
31. **Cosmos DB continuous backup có chắc restore từng document vào primary ngay không?** Không, scope/target có ràng buộc.
32. **Cosmos DB change feed có luôn giữ before-image và mọi delete không?** Không, tùy mode/configuration.
33. **Blob versioning giải quyết lỗi gì?** Khôi phục content trước overwrite/change khi supported.
34. **Blob soft delete và container soft delete có cùng mục đích không?** Không, bảo vệ phạm vi object/container khác nhau.
35. **Nếu bật soft delete sau khi xóa thì có khôi phục được object đã xóa trước đó không?** Không.
36. **Operational backup for Blobs có luôn là bản sao độc lập trong Backup vault không?** Không.
37. **Vaulted backup for Blobs có luôn hỗ trợ mọi HNS account không?** Không được giả định, phải kiểm tra support matrix.
38. **Blob immutability có làm hóa đơn sai thành đúng không?** Không, chỉ bảo vệ khỏi sửa/xóa theo policy.
39. **ADLS Gen2 khác Blob GPv2 tiêu chuẩn ở điểm nào?** HNS, ACL/path semantics và giới hạn tính năng bảo vệ khác nhau.
40. **Delta time travel có thay backup không?** Không nếu files/logs đã bị xóa hoặc retention hết.
41. **Azure Files snapshot có là database-aware backup không?** Không mặc định.
42. **SMB/NFS File restore cần kiểm tra gì ngoài nội dung?** ACL/permissions, file handles và mount behavior.
43. **VM disk snapshot có luôn transaction-consistent không?** Không, có thể chỉ crash-consistent.
44. **Azure Site Recovery có thay backup chống ransomware không?** Không.
45. **AKS resource manifests có tự backup external SQL/Cosmos không?** Không.
46. **Khi backup AKS PVC cần chú ý điều gì?** CSI/volume support, application consistency, storage class và restore topology.
47. **Service Bus Geo-DR alias kiểu metadata-only có giữ message bodies không?** Không.
48. **Vì sao cần phân biệt Service Bus Geo-DR với Geo-Replication?** Feature support và khả năng bảo vệ message data khác nhau.
49. **Transactional Outbox giải quyết gì?** Lưu business intent cùng transaction DB để replay gửi message khi broker lỗi.
50. **Outbox có đảm bảo consumer chạy đúng một lần không?** Không, cần idempotency.
51. **Event Hubs checkpoint có phải backup event payload không?** Không, chỉ lưu processing position.
52. **Event Hubs Capture giúp gì?** Lưu event archive vào Storage/ADLS để dùng lâu hơn retention/replay khi được cấu hình đúng.
53. **Azure Queue Storage đã xóa message có tự phục hồi từ GRS không?** Không mặc định.
54. **Nếu Redis cache rỗng, rủi ro hiệu năng gì?** Cache stampede đẩy tải sang DB.
55. **Key Vault CMK bị purge có nguy hiểm cho backup không?** Có thể khiến dữ liệu không giải mã được.
56. **Key Vault soft delete/purge protection bảo vệ điều gì?** Giảm rủi ro xóa/purge keys/secrets/vault theo retention/rules.
57. **App Configuration snapshots có khôi phục data-plane Orders rows không?** Không, chỉ phục vụ cấu hình.
58. **IaC có thay SQL/Blob backup không?** Không, IaC dựng control plane chứ không giữ business data.
59. **Để restore 3 dịch vụ ở cùng timestamp có chắc consistency không?** Không, cần business-level reconciliation.
60. **Vì sao payment phải đối soát với gateway ngoài DB?** Payment có thể đã capture nhưng local DB restore mất record.
61. **Idempotency trong replay giúp gì?** Tránh duplicate side effects.
62. **Đọc report sau restore có thể vẫn sai vì sao?** Derived Gold/ETL chưa rebuild từ source chính xác.
63. **Tại sao cần restore identity/network trước app?** App không thể đọc data/decrypt/connect nếu dependencies mất.
64. **Failback có thể tạo split brain khi nào?** Primary cũ nhận writes trước khi đồng bộ với DR source of truth.
65. **Cyber recovery khác region failover ở đâu?** Cần containment, clean backup và identity/image attestation.
66. **RPO nhỏ có đồng nghĩa RTO nhỏ không?** Không.
67. **No backup gap alert có chứng minh backup restore được không?** Không, phải test restore/integrity.
68. **Một DR drill PASS cần gì?** Recovery point, data integrity, app/business RLO và RPO/RTO trong mục tiêu.
69. **Chi phí DR phụ thuộc điều gì?** Protected data size/churn, retention, redundancy, warm replicas, monitoring và tests.
70. **Một thiết kế phục hồi dữ liệu tốt nhất có đặc điểm gì?** Phân loại từng service/data, chọn cơ chế theo lỗi và SLO, bảo vệ keys/rights, có reconcile, backup độc lập, diễn tập và giám sát.

## 36. Tài liệu tham khảo

Các nguồn sau là điểm bắt đầu tra cứu **chính thức**. Trước khi cấu hình hoặc chạy lệnh phục hồi, hãy kiểm tra lại SKU, region, tier, feature availability, mức retention và tài liệu theo phiên bản dịch vụ hiện hành. Bài học không đưa ra SLA Azure cố định thay cho hợp đồng dịch vụ.

### Azure reliability, redundancy, backup và chi phí

- [Azure Well-Architected Framework – Reliability](https://learn.microsoft.com/en-us/azure/well-architected/reliability/) — reliability, disaster recovery, failure modes.
- [Azure Storage redundancy](https://learn.microsoft.com/en-us/azure/storage/common/storage-redundancy) — LRS/ZRS/GRS/RA-GRS/GZRS/RA-GZRS.
- [Azure Backup documentation](https://learn.microsoft.com/en-us/azure/backup/) — backup policies, vaults, restore scenarios.
- [Azure Site Recovery overview](https://learn.microsoft.com/en-us/azure/site-recovery/site-recovery-overview) — VM/site disaster recovery.
- [Azure Monitor documentation](https://learn.microsoft.com/en-us/azure/azure-monitor/) — metrics, logs, alerts.
- [Azure Cost Management](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/) — budgets, cost attribution, usage.
- [Azure Pricing Calculator](https://azure.microsoft.com/en-us/pricing/calculator/) — ước tính chi phí theo region/SKU.

### Cơ sở dữ liệu

- [Azure SQL Database recovery from backups](https://learn.microsoft.com/en-us/azure/azure-sql/database/recovery-using-backups) — PITR, deleted database restore, geo-restore concepts.
- [Azure SQL Database long-term backup retention](https://learn.microsoft.com/en-us/azure/azure-sql/database/long-term-retention-overview) — backup retention nhiều năm.
- [Azure SQL Database active geo-replication](https://learn.microsoft.com/en-us/azure/azure-sql/database/active-geo-replication-overview) — geo-secondary và failover.
- [Azure SQL failover groups](https://learn.microsoft.com/en-us/azure/azure-sql/database/failover-group-sql-db) — group failover/endpoint behavior.
- [Azure SQL Managed Instance](https://learn.microsoft.com/en-us/azure/azure-sql/managed-instance/) — deployment model và restore/HA guidance.
- [PostgreSQL Flexible Server backup and restore](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore) — automatic backups, PITR, geo options.
- [MySQL Flexible Server backup and restore](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/concepts-backup-restore) — retention, restore points và regional capabilities.
- [Azure Cosmos DB backup and restore](https://learn.microsoft.com/en-us/azure/cosmos-db/online-backup-and-restore) — periodic backup mode.
- [Azure Cosmos DB continuous backup introduction](https://learn.microsoft.com/en-us/azure/cosmos-db/continuous-backup-restore-introduction) — PITR, support matrix và limits.
- [Azure Cosmos DB multi-region writes](https://learn.microsoft.com/en-us/azure/cosmos-db/multi-region-writes) — distributed write consistency/conflicts.

### Storage, file, AKS, messaging và cache

- [Azure Blob Storage data protection](https://learn.microsoft.com/en-us/azure/storage/blobs/data-protection-overview) — soft delete/versioning/point-in-time restore.
- [Azure Backup for Blobs overview](https://learn.microsoft.com/en-us/azure/backup/blob-backup-overview) — operational và vaulted protection theo khả năng.
- [Immutable storage for Azure Blob](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-storage-overview) — WORM và legal hold.
- [ADLS Gen2 overview](https://learn.microsoft.com/en-us/azure/storage/blobs/data-lake-storage-introduction) — HNS, filesystem behavior.
- [Azure Files snapshots](https://learn.microsoft.com/en-us/azure/storage/files/storage-snapshots-files) — share snapshots và file recovery.
- [Azure Files backup](https://learn.microsoft.com/en-us/azure/backup/azure-file-share-backup-overview) — snapshot/vaulted backup theo share/tier.
- [Azure VM backup overview](https://learn.microsoft.com/en-us/azure/backup/backup-azure-vms-introduction) — VM recovery points.
- [Azure Backup for AKS](https://learn.microsoft.com/en-us/azure/backup/azure-kubernetes-service-backup-overview) — supported Kubernetes resources/volumes.
- [Azure Service Bus Geo-DR](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-geo-dr) — namespace metadata DR.
- [Azure Service Bus documentation](https://learn.microsoft.com/en-us/azure/service-bus-messaging/) — messaging, geo replication options, DLQ/transactions.
- [Azure Event Hubs Capture](https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-capture-overview) — event archive to Storage/ADLS.
- [Azure Queue Storage documentation](https://learn.microsoft.com/en-us/azure/storage/queues/) — message lifecycle/visibility/TTL.
- [Azure Managed Redis documentation](https://learn.microsoft.com/en-us/azure/redis/) — cache, HA, persistence theo tier.

### Identity, config, analytics và vận hành

- [Azure Key Vault soft-delete overview](https://learn.microsoft.com/en-us/azure/key-vault/general/soft-delete-overview) — xóa mềm và purge protection.
- [Azure Key Vault RBAC](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide) — data-plane roles.
- [Azure App Configuration snapshots](https://learn.microsoft.com/en-us/azure/azure-app-configuration/concept-snapshots) — versioned immutable configuration snapshots.
- [Azure Databricks Delta history](https://learn.microsoft.com/en-us/azure/databricks/delta/history) — table versions/time travel và retention.
- [Azure Data Factory documentation](https://learn.microsoft.com/en-us/azure/data-factory/) — source/pipeline/trigger orchestration.
- [Azure Synapse Analytics documentation](https://learn.microsoft.com/en-us/azure/synapse-analytics/) — SQL pools/lake analytics recovery context.
- [Azure Well-Architected operational excellence](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/) — runbooks, drills, incidents và evidence.

**Kết luận:** thiết kế phục hồi dữ liệu trên Azure phải bắt đầu từ **business RPO, RTO, RLO và vai trò của mỗi dataset**, không phải từ câu hỏi “dịch vụ này có backup hay chưa?”. Azure SQL, PostgreSQL/MySQL, Cosmos DB, Blob/ADLS, Azure Files, VM/AKS, Service Bus/Event Hubs, Redis, Key Vault và analytics đều có **failure modes, backup/restore granularity và region capabilities khác nhau**. **Replication giúp availability nhưng không luôn cứu logical corruption; snapshot/soft delete giúp một số thao tác xóa/ghi đè nhưng không thay backup cách ly; restore dữ liệu không tự phục hồi identity, DNS, encryption keys hay tính nhất quán giao dịch xuyên hệ thống**. Một thiết kế đủ tin cậy cần phân loại dữ liệu, bảo vệ nguồn sự thật, backup/PITR/versioning/archives đúng loại, quyền tối thiểu, immutable/clean recovery copies khi cần, **restore cô lập, kiểm tra integrity và reconciliation**, cùng runbook thứ tự khôi phục, capacity/budget, monitoring và diễn tập đo RPO/RTO thực. Chỉ tuyên bố phục hồi thành công khi ứng dụng thực hiện được năng lực nghiệp vụ đã cam kết và dữ liệu được xác minh đúng.

