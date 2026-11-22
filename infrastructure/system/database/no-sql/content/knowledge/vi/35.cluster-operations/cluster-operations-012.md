# Dịch vụ quản lý sẵn và ranh giới trách nhiệm với nhà cung cấp

Khi triển khai NoSQL, một đội kỹ thuật có thể tự vận hành cluster trên máy ảo hoặc sử dụng một dịch vụ quản lý sẵn (*managed service*). Dịch vụ managed giúp giảm công việc cài đặt database, giám sát máy chủ, vá lỗi hệ điều hành, thay node và tự động hóa một phần sao lưu, mở rộng hoặc phục hồi. Tuy nhiên, **giảm khối lượng vận hành không có nghĩa chuyển toàn bộ trách nhiệm bảo mật, độ tin cậy và tính đúng đắn dữ liệu cho nhà cung cấp**.

Hãy hình dung một ứng dụng cho thuê đang chạy Booking API trên Java. Nhóm quyết định chuyển từ cluster NoSQL tự quản lý sang một dịch vụ managed. Sau chuyển đổi, nhà cung cấp có thể chịu trách nhiệm cập nhật phiên bản database và vận hành replication infrastructure. Nhưng ai chọn partition key, cấp quyền cho ứng dụng, bật PITR, kiểm tra bản backup có restore được, định nghĩa RPO/RTO, xử lý truy vấn tạo hot partition, tính dữ liệu khách hàng phải nằm trong vùng pháp lý nào, hoặc lập phương án khi cả region gặp sự cố?

Đó là nội dung của **ranh giới trách nhiệm** (*responsibility boundary*). Bài học thuộc chương **Vận hành cụm** trong module **Database No SQL**, trình bày mô hình *shared responsibility*, phân chia control plane/data plane, các quyết định vẫn thuộc ứng dụng, vận hành backup/DR, availability/SLA, bảo mật, observability, giới hạn tài nguyên, chi phí, rủi ro phụ thuộc nhà cung cấp và quy trình đánh giá một dịch vụ managed trước khi đưa lên production.

> **Thông điệp trung tâm:** *Managed* là cam kết về **những việc nhà cung cấp làm và những khả năng họ cung cấp**; không phải lời hứa rằng mọi cấu hình, truy vấn, dữ liệu, quyền truy cập và quy trình phục hồi của khách hàng tự động đúng.

## 1. Managed NoSQL là gì?

**Managed NoSQL** là dịch vụ cung cấp khả năng lưu trữ/truy vấn NoSQL trong đó nhà cung cấp đảm nhận một phần đáng kể công việc quản lý nền tảng. Mức độ quản lý rất khác nhau:

~~~text
Tự quản lý
  |
  | Install DB, upgrade, patch, monitor, backup, repair
  v
Database trên VM/cloud IaaS
  |
  v
Managed database cluster
  |
  | Provider handles many database-host operations
  v
Serverless / API-oriented managed NoSQL
  |
  | Node/VM internals largely abstracted from customer
  v
Khách hàng vẫn phải quản lý dữ liệu, truy cập, workload
và các yêu cầu chất lượng nghiệp vụ.
~~~

Ví dụ các họ dịch vụ được gặp trong thực tế: MongoDB Atlas, Amazon DynamoDB, Azure Cosmos DB, Google Cloud Firestore/Bigtable, các offering Cassandra managed, Redis managed và search services. **Không coi mọi tên sản phẩm là tương đương**: database API, mô hình consistency, backup, quyền truy cập, cơ chế mạng, định giá và phạm vi người dùng phải quản lý có thể khác nhau theo nhà cung cấp, sản phẩm, phiên bản, khu vực và gói dịch vụ.

## 2. Một ma trận trách nhiệm có ích hơn câu “nhà cung cấp lo hết”

| Lớp/hạng mục | Nhà cung cấp thường làm | Khách hàng vẫn phải quyết định/kiểm tra |
| --- | --- | --- |
| Datacenter, hardware | Vận hành hạ tầng vật lý | Chọn region, yêu cầu compliance |
| Host/VM/OS | Với nhiều gói managed, vận hành/patch | Hiểu lịch bảo trì và tác động |
| Database software | Cài đặt/nâng cấp trong phạm vi gói | Chọn phiên bản tính năng, kiểm tương thích |
| Replication | Cung cấp và vận hành cơ chế | Chọn topology/consistency/failover policy nếu cấu hình được |
| Backup/PITR | Cung cấp tính năng, có thể tự động | Bật đúng, retention, restore test, quyền truy cập |
| Network | Cung cấp endpoint/VPC integration | Chặn public exposure, route, firewall, TLS |
| Identity | Cung cấp IAM/roles/ACL primitives | Thiết kế least privilege, credentials và reviews |
| Encryption | Cung cấp at-rest/in-transit mechanisms | Bật đúng mode, quản lý key khi customer-managed |
| Schema/keys/indexes | Cung cấp công cụ và giới hạn | Data modeling, index, partition key, TTL |
| Queries | Thực thi theo engine contract | Tối ưu queries, giới hạn scans/hot partitions |
| Application | Không sở hữu code nghiệp vụ | Idempotency, validation, transactions, retries |
| Availability/SLA | Cam kết theo hợp đồng | SLO end-to-end, topology, synthetic probes |
| Monitoring | Phơi bày metrics/logs/events | Xây alert, ownership, runbook và phản ứng |
| Chi phí | Đưa mô hình billing/quota | Budget, forecast, chargeback và ngăn bill shock |
| Data governance | Cung cấp controls theo hợp đồng | Phân loại dữ liệu, residency, retention, deletion |

Từ “thường” là chủ ý: **ranh giới hợp đồng thực tế phải đọc trong tài liệu/gói dịch vụ cụ thể**. Có tính năng khách hàng phải bật; có tính năng provider vận hành nhưng khách hàng phải trả tiền riêng; có loại hỏng hóc nằm ngoài SLA.

## 3. Mô hình shared responsibility không phải chia đôi trách nhiệm

~~~text
                       PROVIDER
              Physical infra / service
              Control plane / database engine
                         |
                    SHARED LAYER
       Service config / topology / encryption / observability
                         |
                       CUSTOMER
        Data, identities, access, business rules, workloads
~~~

Không phải mỗi bên chịu đúng 50%. Ví dụ provider thực hiện backup job nhưng khách hàng phải chọn retention, bảo đảm backup thuộc đúng tài khoản, định nghĩa ai được restore và **thử phục hồi đúng RTO**.

### Phân biệt ba loại nghĩa vụ

1. **Operate:** ai thực hiện công việc hằng ngày?
2. **Configure:** ai chọn và thay đổi chính sách?
3. **Assure:** ai chịu trách nhiệm chứng minh kết quả đáp ứng nhu cầu?

Một tính năng có thể được provider **operate**, customer **configure**, và cả hai cùng tham gia **assure** thông qua logs, tests và SLA/support process.

## 4. Ví dụ xuyên suốt: Booking API chuyển sang managed NoSQL

~~~text
Users
  |
  v
Java Booking API
  |   ├── validate user & tenant
  |   ├── enforce booking invariant
  |   └── retry with idempotency key
  |
  v
Managed NoSQL endpoint
  |   ├── provider-operated database engine
  |   ├── managed replication
  |   └── backup / monitoring features
  |
  +--> Change stream / CDC --> Search projection
                                    |
                                    v
                               User search
~~~

Một ngày, giá trị đặt chỗ bị ghi hai lần do retry dùng hai business IDs. Database vẫn ghi đúng theo request nhận được và tất cả hạ tầng provider đều khỏe. Đây chủ yếu là **lỗi hợp đồng nghiệp vụ/ứng dụng**, không thể kết luận là provider outage.

Một ngày khác, database endpoint có sự cố hạ tầng. Nhà cung cấp cần thực hiện phần họ cam kết; ứng dụng vẫn phải có timeouts, retry có kiểm soát, degraded-mode policy và incident communication.

## 5. Control plane khác data plane

**Control plane** thường quản lý:

- Tạo/xóa instance, table, cluster hoặc database.
- Thay tier/capacity, network policy, IAM/roles.
- Cấu hình backup, restore, encryption key.
- Mở rộng hoặc thay đổi topology.
- Bản vá/nâng cấp và một số administrative actions.

**Data plane** phục vụ requests:

- Put/Get/Query/Update/Delete.
- Read/write consistency.
- Các transaction hoặc conditional writes được hỗ trợ.
- Stream/change capture và query execution.

~~~text
         Operator / IaC
                |
                v
          Control plane
                |
          Configuration
                v
Java API ----> Data plane ----> Data storage
~~~

Một số dịch vụ có thể tiếp tục phục vụ existing data requests khi control-plane API bị lỗi; dịch vụ khác có dependency chặt hơn. **Không giả định độc lập hoàn toàn** nếu chưa xác nhận qua tài liệu và bài kiểm thử.

## 6. Khi control plane không khả dụng

Giả sử mọi reads/writes đang tốt, nhưng API tạo bảng/mở rộng capacity không hoạt động:

~~~text
Data plane:     currently HEALTHY
Control plane:  CREATE/UPDATE operations unavailable
Peak forecast:  capacity needed within 20 minutes
~~~

Hệ vẫn có thể gặp incident vì không thể scale kịp. Kế hoạch vận hành phải tính:

- Headroom trước peak.
- Quota và thời gian provision.
- Khả năng scale thủ công/auto trong control-plane failure.
- Runbook khi không thể bật backup hoặc thay network rules.
- SLO nào còn bảo đảm, SLO nào đã có rủi ro.

**Control-plane availability là một dependency vận hành**, không chỉ phục vụ người quản trị.

## 7. Các kiểu offering managed và tác động đến quyết định

| Kiểu offering | Khách hàng có thể nhìn thấy | Điều cần hỏi |
| --- | --- | --- |
| Managed cluster với node sizes | CPU/RAM/disk, shards/replicas | Upgrade, patch, placement, failover |
| Serverless request-based | API, consumed capacity, quotas | Burst, hot partition, cost per request |
| Dedicated database service | Private endpoint, storage/capacity tier | Replica guarantees, backups, maintenance |
| Managed cache | Memory, eviction, replication, durability options | Cache recovery, persistence, TTL |
| Managed search | Shards/replicas hoặc capacity abstractions | Indexing vs query performance, merges |
| Managed document database | Document API, indexes, query plans | Transaction scope, storage/index costs |

**“Serverless” không có nghĩa “không giới hạn”.** Vẫn có quotas, per-partition limits, concurrency, request/response size và throttling behaviors.

## 8. Ranh giới của SLA: đọc hợp đồng chứ không suy từ tên sản phẩm

Nhà cung cấp có thể có một SLA cho **database service availability** trong điều kiện nhất định. Ứng dụng của bạn lại có:

~~~text
User → DNS → API gateway → Java service
                         → Managed NoSQL
                         → Search projection
                         → Payment provider
~~~

**SLA database không bằng SLO ứng dụng**. Provider không bảo đảm Java code, DNS riêng, cache, payment processor và quy tắc booking.

### Cần kiểm trong SLA

- Dịch vụ/tier/region nào được bao phủ?
- Điều kiện đủ để áp SLA (ví dụ cấu hình HA bắt buộc)?
- Chỉ số được tính như thế nào?
- Bảo trì có ngoại lệ không?
- Quota/throttling có được tính là outage không?
- Cách mở support case và giới hạn thời gian khiếu nại?
- Biện pháp đền bù có phải chỉ là service credits?
- Data loss/durability có được bảo đảm bằng điều khoản riêng không?

Không tự đưa số “99,99%” vào tài liệu kiến trúc nếu chưa tra đúng SLA cho tier và điều kiện hiện hành.

## 9. Availability percentage và số phút tương ứng

Với một cửa sổ **30 ngày = 43.200 phút**, nếu xét availability đơn giản:

\[
AllowedDowntime=(1-A)\times43{,}200
\]

| Mục tiêu minh họa | Khoảng downtime trong 30 ngày |
| --- | ---: |
| 99,0% | 432 phút |
| 99,9% | 43,2 phút |
| 99,95% | 21,6 phút |
| 99,99% | 4,32 phút |

Đây là phép toán minh họa, **không phải SLA thực tế của các nhà cung cấp**. SLA có thể định nghĩa nhiều khoảng đo, loại request, excluded downtime và điều kiện khác.

### Chuỗi dependencies

Nếu một user action phải qua nhiều dịch vụ, availability end-to-end có thể thấp hơn availability của từng thành phần. Không nên nhân các tỷ lệ đơn giản để dự báo thực tế khi failures có tương quan. Cần **đo SLO ở biên người dùng** và fault-test dependency chains.

## 10. SLA, SLO, SLI và trách nhiệm phản ứng

| Thước đo | Ai định nghĩa? | Ai phải quan sát? |
| --- | --- | --- |
| Provider SLA | Nhà cung cấp/hợp đồng | Provider + customer |
| Application SLO | Product/service owner | Customer |
| Request SLI | Team ứng dụng | Customer |
| Replication/restore contract | Provider + config customer | Cả hai theo boundary |
| Business correctness | Customer/domain authority | Customer |

Ví dụ provider đáp ứng SLA nhưng ứng dụng có 10% request timeout vì pool kết nối quá nhỏ. Customer vẫn phải sửa cấu hình app. Ngược lại, ứng dụng dùng đúng SDK nhưng provider data plane lỗi: liên hệ support để xử lý phần provider, đồng thời kích hoạt mitigation phía app.

## 11. Durability khác availability

- **Availability:** có thể truy cập/ghi/đọc trong điều kiện và thời gian nào?
- **Durability:** dữ liệu đã được acknowledge có được giữ bền theo guarantee nào?
- **Consistency:** các lịch sử đọc/ghi nào được phép quan sát?
- **Freshness:** bản sao/search index mới tới đâu?
- **Recoverability:** có thể trở về trạng thái mong muốn sau lỗi/human mistake không?

Một dịch vụ có availability cao vẫn có thể trả dữ liệu eventual/stale. Một hệ có nhiều replicas vẫn có thể lan truyền lệnh xóa sai hoặc corruption do ứng dụng.

**Đừng dùng một chỉ số uptime để chứng minh durability, consistency hay khả năng restore.**

## 12. Chọn consistency level: quyền và trách nhiệm của ứng dụng

Nhà cung cấp có thể cung cấp các mức consistency, conditional writes hoặc transactions tùy sản phẩm. Ứng dụng phải chọn đúng theo **business invariant**:

~~~text
Search listing:
  Có thể chấp nhận dữ liệu chậm vài giây.

Inventory reservation:
  Không được oversell do hai writers cùng đọc cached availability.

Payment ledger:
  Cần idempotency và authority rõ ràng.
~~~

Ngay cả khi provider bảo đảm một conditional write là atomic trong phạm vi key/item, ứng dụng phải dùng đúng key, đúng condition và định nghĩa retry semantics. Chọn eventual read cho một quyết định cần linearizable/transactional state có thể gây lỗi dù provider hoạt động đúng contract.

## 13. Data model, partition key và index vẫn thuộc ứng dụng

Managed service thực thi queries nhưng thường **không chịu trách nhiệm chọn data model tốt thay bạn**.

Ví dụ:

~~~text
Table: booking_events
Partition key: date

All writes today → one hot logical partition
~~~

Nhà cung cấp có thể có auto-scaling, nhưng một phân bố key quá lệch vẫn có thể gặp throttling/latency.

Các quyết định cần kiểm:

- Partition/shard key theo access patterns.
- Item/document size và maximum limits.
- Secondary indexes và write amplification.
- TTL/retention.
- Query fan-out và scans.
- Transactions/conditional-update scope.
- Read/write consistency theo nghiệp vụ.

**Mua tier đắt hơn không tự sửa sai partition key hoặc query thực hiện full scans.**

## 14. Các tình huống lỗi nằm ở phía khách hàng dù database khỏe

| Hiện tượng | Vì sao DB vẫn có thể đúng? |
| --- | --- |
| Hai booking cùng tồn kho | App không dùng atomic conditional write |
| Latency cao vì scan | Query shape/index không phù hợp |
| Throttling ở hot key | Phân phối partition key lệch |
| Mất dữ liệu sau DELETE | Ứng dụng xóa hợp lệ theo credentials |
| Search hiện bản cũ | CDC consumer lag/index freshness |
| Lộ dữ liệu tenant B | App thiếu per-resource authorization |
| Bill tăng mạnh | Query scan/cross-region transfer quá lớn |
| Restore quá lâu | Chưa chọn/kiểm restore strategy |

Điều này không miễn trách nhiệm provider đối với bug của engine hoặc lời hứa đã vi phạm. Muốn xác định root cause, cần **evidence về request, config, metrics và hợp đồng** thay vì gán lỗi theo cảm tính.

## 15. Identity: ai xác thực ở đâu?

~~~text
End user
  | user session / OIDC access token
  v
Booking API
  | validates user and ownership
  | workload/service identity
  v
Managed NoSQL
  | IAM/DB user/role authorization
  v
Records
~~~

Provider có thể vận hành IAM/ACL mechanism, nhưng khách hàng phải:

1. Thiết kế principals riêng cho từng service.
2. Gán quyền tối thiểu.
3. Giữ secrets/tokens an toàn.
4. Xoay vòng và thu hồi credentials.
5. Kiểm tra tenant isolation.
6. Giám sát truy cập bất thường.

**Database service role không thay được việc xác thực người dùng và kiểm quyền trên từng booking.**

## 16. Mô hình least privilege

| Principal | Quyền cần | Quyền không nên có |
| --- | --- | --- |
| Listing reader | Read published listings | Delete toàn cluster |
| Booking writer | Conditional read/write booking | Manage database admins |
| CDC connector | Read stream/change feed | Drop collections/tables |
| Analytics ETL | Read/append đúng datasets | Modify booking authority |
| Backup automation | Backup/restore theo policy | Read tất cả secrets |
| Operator | Admin qua approval/SSO | Dùng admin identity trong code app |

Mỗi identity nên tách **production/staging**, tách service và có owner/audit. Một credential admin dùng chung cho toàn bộ Java services làm tăng blast radius nghiêm trọng.

## 17. Network boundaries: private không tự động

Một managed database thường có endpoint và các lựa chọn network access. Khách hàng phải xác định:

- Public endpoint có cần hay phải vô hiệu?
- Có private endpoint/VPC integration không?
- Firewall/security groups/IP allowlist?
- TLS và server certificate verification?
- DNS/failover/region routing?
- Egress path và proxy?
- Có khả năng bypass API để gọi database trực tiếp không?

~~~text
Public internet
      |
   API gateway
      |
   Private app network
      |
   Private managed DB endpoint
~~~

**Không mở database port ra toàn Internet chỉ vì dịch vụ có authentication.** AuthN và network segmentation là các lớp phòng vệ bổ sung, không thay nhau.

## 18. TLS và mã hóa dữ liệu

Phân biệt:

- **In transit:** TLS cho kết nối app→DB, replica/backup/cross-region theo hợp đồng.
- **At rest:** mã hóa dữ liệu trên storage/backup.
- **Customer-managed key (CMK/BYOK):** khách hàng có thêm quyền/điều kiện về key lifecycle trong mô hình được hỗ trợ.
- **Application-level encryption:** che nội dung trước khi DB nhận, nhưng ảnh hưởng query/index.

### Customer-managed keys có thêm trách nhiệm

Nếu khách hàng vô tình disable/delete key hoặc revoke quyền KMS, database/backup có thể trở nên không truy cập được dù database engine vẫn hoạt động tốt.

Phải có:

- Key owner và approval.
- Rotation policy phù hợp.
- KMS availability/quotas.
- Backup/restore key dependencies.
- Khả năng khôi phục và xử lý accidental key disable.
- Audit logs cho key access.

**“Encryption enabled” chưa chứng minh dữ liệu được bảo vệ đúng threat model** nếu credentials, application logs hoặc decrypted exports bị lộ.

## 19. Trách nhiệm về dữ liệu nhạy cảm và residency

Nhà cung cấp có thể đưa ra region selection, data protection options và chứng nhận theo hợp đồng. Khách hàng phải:

1. Phân loại dữ liệu: PII, tài chính, tokens, logs.
2. Chọn regions được phép lưu/xử lý.
3. Xem replication, backups, diagnostics và support access có tạo dữ liệu ngoài region không.
4. Định nghĩa retention, deletion và quyền truy cập.
5. Xem logging/telemetry có chứa sensitive payload không.
6. Xác nhận legal/compliance requirements với bộ phận chuyên trách.
7. Có cơ chế xuất/di chuyển/xóa dữ liệu khi chấm dứt hợp đồng.

Chọn “region A” trong console **không tự chứng minh mọi bản sao, support dump và backup đều đáp ứng data residency**; phải đọc đúng product terms.

## 20. Backup, snapshot và PITR: ai thực sự làm gì?

Một dịch vụ managed có thể cung cấp:

- Scheduled snapshots.
- Continuous/PITR recovery.
- Backup policies và retention.
- Cross-region copy.
- Restore to new database/cluster.
- Export ra object storage.

Nhưng khách hàng cần xác định:

| Câu hỏi | Trách nhiệm thực tế |
| --- | --- |
| Feature đã bật chưa? | Khách hàng phải xác minh |
| Retention bao lâu? | Cấu hình/chính sách cần đúng |
| Ai có quyền xóa backup? | IAM/ACL do khách hàng kiểm |
| Encryption key nào cần khi restore? | Customer/provider tùy key model |
| Restore mất bao lâu? | Phải đo bằng diễn tập |
| Restore có giữ roles/network settings? | Phải kiểm product semantics |
| Backup có phục hồi lỗi xóa logic? | Có thể, nếu đủ recovery points |
| Backup có đáp ứng RPO/RTO? | Chỉ biết sau test và tính dependency |

**Có mục “Backup: Enabled” trên console không tương đương “đã chứng minh khôi phục thành công”.**

## 21. Replication không thay thế backup

~~~text
Application accidentally deletes 500,000 records
           |
           v
Managed NoSQL primary
           |
           +→ Replica A receives deletion
           +→ Replica B receives deletion
~~~

Replication có thể lan truyền một lệnh xóa hợp lệ rất nhanh. Backup/PITR có thể giúp phục hồi tại mốc trước lỗi, tùy retention và restore semantics.

Phân biệt:

- **Replica:** phục vụ availability/fault tolerance theo design.
- **Backup:** có thể giúp quay lại trạng thái cũ.
- **Archive:** giữ lâu dài theo yêu cầu pháp lý/chi phí.
- **CDC/change log:** phục vụ propagation/replay theo retention, không luôn là backup.

Không dùng một replica ở region khác làm luận cứ duy nhất cho khả năng phục hồi accidental deletion/ransomware.

## 22. RPO và RTO phải đo

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa được phép mất, thường tính bằng thời gian giữa trạng thái hiện tại và điểm phục hồi.
- **RTO (Recovery Time Objective):** thời gian tối đa để khôi phục dịch vụ theo mục tiêu.

Giả sử:

~~~text
Booking authority:
  RPO target: near-zero or explicit bound
  RTO target: 30 minutes

Analytics projection:
  RPO: rebuild from source/CDC
  RTO: several hours may be acceptable
~~~

Hai hệ có nhu cầu khác nhau. Các con số trên chỉ là giả định thảo luận, không phải khuyến nghị mặc định.

### Restore gồm nhiều bước

~~~text
Detect incident
  → Decide recovery point
  → Provision restore target
  → Restore data
  → Validate consistency and permissions
  → Reconnect Java services
  → Replay/reconcile events
  → Resume traffic
~~~

**RTO end-to-end phải tính cả phát hiện, quyết định, restore, kiểm dữ liệu và cutover**, không chỉ thời gian provider báo “restore completed”.

## 23. Ví dụ lịch phục hồi và RTO

~~~text
10:00  Wrong deletion detected
10:07  Incident commander chooses recovery point
10:12  Restore job started
10:34  New dataset available
10:43  Validation and replay completed
10:48  Traffic cut over
~~~

Kết quả thực tế của ví dụ: khoảng **48 phút** từ khi phát hiện đến khi khôi phục dịch vụ, chưa tính thời gian lỗi xảy ra trước khi phát hiện. Nếu RTO mục tiêu 30 phút, quy trình **chưa đạt**, mặc dù provider restore job chỉ kéo dài 22 phút.

### Cần ghi trong drill

- Size của dữ liệu được restore.
- Cross-region transfer.
- Snapshot/PITR timestamp.
- Index build và cache warm-up.
- Auth/roles/network checks.
- SDK endpoint updates.
- CDC catch-up và correctness verification.

## 24. Cross-region và multi-region không phải tính năng tự hiểu

Một offering có thể hỗ trợ:

- Read replicas.
- Cross-region replication.
- Active-passive failover.
- Multi-region active-active theo mô hình riêng.
- Asynchronous hoặc có các consistency tradeoffs.

### Phải hỏi

1. Writes được ACK ở đâu và durability contract gì?
2. RPO thực tế khi mất region?
3. DNS/service endpoint failover tự động hay thủ công?
4. Replication lag được đo ra sao?
5. Có conflict resolution cho concurrent writes?
6. Client có thể đọc dữ liệu cũ sau failover không?
7. Data residency cho cả backup/replica?
8. Cross-region cost?

**Provider quảng bá “multi-region” không đủ để bảo đảm RPO=0 hoặc RTO nhỏ hơn một phút cho mọi workload.**

## 25. Quorum, failover và consistency dưới lỗi

Một cluster có thể dùng replication factor, quorum, leader election hoặc consensus. Dù managed, ứng dụng cần hiểu:

~~~text
Normal:
  Reads and writes accepted.

AZ failure:
  Leader may move.
  A replica may be unavailable.
  Latency can rise during recovery.

Region failure:
  Failover policy and data freshness matter.
~~~

Nếu business yêu cầu không double-booking, không tự hạ consistency/conditional checks để tránh timeout khi failure. Cần chỉ rõ những write operations còn đúng invariant và những loại request phải trả lỗi/degrade.

### Failure domain

- Node.
- Rack/availability zone.
- Region.
- Account/project/IAM/KMS.
- Network/private endpoint.
- Control plane.

**Một hệ được replicate qua AZ vẫn có thể bị ảnh hưởng bởi lỗi IAM/KMS hoặc ứng dụng gửi sai requests**, vì đó là fault domain khác.

## 26. Scaling: nhà cung cấp cho primitive, khách hàng có workload

Managed service có thể hỗ trợ:

- Autoscaling capacity.
- Thay tier/node class.
- Thêm shards/replicas.
- Storage autoscaling.
- Request-based pricing và throttling.

Nhưng cần kiểm:

- Scaling trigger và độ trễ phản ứng.
- Quota/tốc độ scale tối đa.
- Hot partition behavior.
- Rebalance/resharding overhead.
- Cửa sổ bảo trì/gián đoạn.
- Cách rollback tier.
- Tác động đến kết nối/endpoint của Java.
- Cost khi scale lên và scale xuống.

**Autoscaling không có nghĩa vô hạn và không tức thời**. Một peak tăng trong hai phút có thể tới nhanh hơn thời gian capacity được cấp phát/rebalanced.

## 27. Kiểm capacity bằng giới hạn nhỏ nhất

Một workload có:

~~~text
API needs:             8,000 operations/s
Provisioned capacity: 10,000 nominal ops/s
Hot partition limit:   2,000 ops/s for one tenant
~~~

Tổng capacity có vẻ đủ nhưng tenant dồn về một key vẫn bị throttling.

Một hình dung:

\[
ActualThroughput\le
\min(CPU,IOPS,Network,Quota,PartitionLimit,\ldots)
\]

Đây là cách suy nghĩ về bottleneck, không phải phương trình dự đoán chính xác khi resources tương tác.

### Năng lực khách hàng phải duy trì

- Baseline theo read/write/query shape.
- Hot key detection.
- Index/partition-design review.
- Benchmark representative datasets.
- Thử sustained peak, burst, cache cold start.
- SLO error rate và p95/p99.
- Capacity/quotas alerts.

## 28. Throttling: khác outage của nhà cung cấp

Một managed DB có thể chủ động trả throttling khi vượt giới hạn hợp đồng:

~~~text
Client request
    |
    v
Service capacity/partition limit reached
    |
    +→ Throttling response
~~~

Throttling có thể là **hành vi thiết kế**, không phải sự cố provider. Cần:

1. Phân loại error/reason chính xác.
2. Retry có exponential backoff và jitter nếu operation an toàn.
3. Giới hạn attempts/overall deadline.
4. Không nhân đôi business effects (stable idempotency key).
5. Thêm rate limiting/admission control.
6. Kiểm hot partition và quota.
7. Quan sát SDK retry count và end-to-end latency.

**Retry vô hạn là một dạng tăng tải tự gây ra**, không phải phương án đảm bảo reliability.

## 29. Java SDK: để credentials được cấp từ workload identity

Với một API managed dùng IAM, tránh hardcode access keys trong source. Ví dụ **AWS SDK for Java v2** và DynamoDB:

~~~java
import java.util.Map;
import software.amazon.awssdk.auth.credentials
        .DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model
        .AttributeValue;
import software.amazon.awssdk.services.dynamodb.model
        .GetItemRequest;
import software.amazon.awssdk.services.dynamodb.model
        .GetItemResponse;

public final class ManagedDbAccess {
    public static void main(String[] args) {
        try (DynamoDbClient client =
                DynamoDbClient.builder()
                    .region(Region.AP_SOUTHEAST_1)
                    .credentialsProvider(
                        DefaultCredentialsProvider.create())
                    .build()) {

            GetItemRequest request = GetItemRequest.builder()
                    .tableName("Listings")
                    .key(Map.of(
                        "pk", AttributeValue.builder()
                            .s("LISTING#L42").build(),
                        "sk", AttributeValue.builder()
                            .s("PROFILE").build()))
                    .build();

            GetItemResponse result = client.getItem(request);
            System.out.println("Found=" + result.hasItem());
        }
    }
}
~~~

### Vì sao đây là managed-friendly?

- Application yêu cầu API bằng **SDK** thay vì mở socket tới DB process tự dựng.
- Credentials provider có thể lấy temporary credentials từ vai trò/workload identity phù hợp.
- Region và table là lựa chọn thuộc client/deployment.
- IAM permissions phải được giới hạn đúng table/operations.

### Các giới hạn

Ví dụ giả định project đã có SDK dependencies, table/key schema đúng và IAM cho phép `GetItem`. `DefaultCredentialsProvider` cũng có thể đọc nguồn static credentials nếu môi trường cấu hình sai; production cần thiết kế trust/role và kiểm không vô tình sử dụng static keys.

Code chỉ minh họa kết nối/read path; production còn phải có timeouts, retries, telemetry, authorization, data modeling và error handling. **Không suy từ việc dùng SDK rằng mọi security/reliability requirement đã được đáp ứng.**

## 30. Client retries và tính đúng đắn dữ liệu

Một API booking:

~~~text
1. Client sends Reserve(reservationId=R42).
2. Managed DB commits write.
3. Network drops response.
4. Java service sees timeout.
5. Client retries Reserve.
~~~

Nếu mỗi retry tạo một reservation mới, hệ có thể đặt hai lần dù provider không hề mất dữ liệu.

### Bảo vệ phía khách hàng

- Stable business idempotency key.
- Conditional write/transaction trong phạm vi DB hỗ trợ.
- Query status khi outcome unknown.
- Retry budget/backoff.
- Reconciliation cho operations có external side effects.

Một retry sau timeout có thể thành công, bị condition conflict hoặc phản ánh write đã commit. **Timeout không chứng minh dữ liệu chưa được ghi.**

## 31. Thay đổi phiên bản và maintenance: ai kiểm tương thích?

Provider có thể patch runtime, database engine hoặc networking theo chính sách gói dịch vụ. Khách hàng cần:

1. Theo dõi maintenance notifications.
2. Biết những thay đổi nào có thể gây failover/reconnect.
3. Đọc release notes và API compatibility.
4. Test driver, query plans, TLS/certificates.
5. Thử retry/reconnect và connection pool behavior.
6. Có upgrade/cutover/rollback plan trong phạm vi được phép.
7. Định nghĩa change freeze quanh event kinh doanh quan trọng khi hỗ trợ.

**Managed không đồng nghĩa “nâng cấp không bao giờ làm gián đoạn”**. SLO phải phản ánh maintenance semantics và application resilience.

## 32. API/SDK compatibility và feature gaps

Một database managed có thể nói “tương thích” với một giao thức hay database engine nhưng:

- Không hỗ trợ đủ commands/extensions.
- Có giới hạn trên transactions, indexes, aggregation.
- Consistency semantics khác.
- Error codes/retries khác.
- Change stream/CDC khác.
- Version lag hoặc proprietary API.

### Cách đánh giá

Lập một **feature-usage matrix**:

| Tính năng ứng dụng cần | Có trong product/tier? | Bài kiểm |
| --- | --- | --- |
| Conditional writes | Cần xác nhận | Concurrent update test |
| Multi-document transaction | Nếu nghiệp vụ cần | Atomicity under crash |
| Secondary indexes | Theo query shape | Explain/latency |
| CDC/change stream | For projection | Resume/duplicate test |
| Backup/PITR | Theo RPO | Restore drill |
| IAM/private networking | Theo security policy | Deny/allow tests |

**Không kết luận tính tương thích chỉ từ cách viết query giống nhau**.

## 33. Observability: provider metrics và application metrics

Provider thường phơi bày một số metrics về requests, errors, capacity, storage và health. Khách hàng cần nối chúng với metrics bên ứng dụng:

~~~text
API:
  Good request ratio, p95/p99, retry count
  |
  v
SDK:
  Client-side latency, auth failures, throttling
  |
  v
Managed NoSQL:
  Provider request latency, capacity, storage, replica lag
  |
  v
CDC / Search:
  Backlog age, visible freshness, apply errors
~~~

Đừng dùng provider server latency làm thước đo duy nhất: một request Java có thể mất thời gian ở connection pool, DNS, network, retry và deserialization.

## 34. Truy vết một incident xuyên ranh giới

Một log có thể nối:

~~~text
correlationId: req-801
operation: reserve
region: region-A
logicalAttempt: 1
sdkAttemptCount: 3
dbRequestId: provider-reference
businessKey: reservation:R42
status: THROTTLED_THEN_SUCCESS
endToEndLatency: 800ms
~~~

### Bảo vệ dữ liệu trong telemetry

- Không log access keys, DB passwords hoặc bearer tokens.
- Không đưa raw PII trong metrics tags.
- Giới hạn sampling và retention.
- Dùng query fingerprint và correlation IDs.
- Tôn trọng audit/security policy.

Một nhà cung cấp có thể yêu cầu **provider request ID, thời gian, region và thông báo lỗi** để điều tra. Chuẩn bị những trường đó trước khi có incident giúp support case được xử lý hiệu quả.

## 35. Who owns the alert?

| Alert | Owner đầu tiên thường phù hợp | Khi nào escalate provider? |
| --- | --- | --- |
| App p99 latency tăng | Application on-call | Khi evidence chỉ tới managed DB |
| IAM AccessDenied sau deploy | Application/security | Nếu policy service có lỗi xác định |
| Hot partition throttling | Data/platform team | Khi vượt behavior/tài liệu công bố |
| Managed endpoint unavailable | Platform/on-call | Ngay khi xác định provider-side issue |
| Backup job failure | Data/platform team | Khi managed backup mechanism lỗi |
| PITR restore failure | Incident commander/platform | Support theo mức khẩn |
| Provider maintenance | Platform change owner | Khi vi phạm thông báo/contract |
| Data residency violation | Security/legal/data owner | Theo incident và hợp đồng |

Một alert phải có **người chịu trách nhiệm triage**, ngay cả khi root cause có thể thuộc provider. Không chờ provider tự phát hiện mọi ảnh hưởng tới API của bạn.

## 36. Incident management: ranh giới của support

Provider support có thể điều tra nền tảng và hướng dẫn các thao tác nằm trong sản phẩm. Customer vẫn phải vận hành incident response:

1. Xác định ảnh hưởng user/SLO.
2. Thu evidence (metrics, error codes, request IDs).
3. Phân loại application/configuration/provider problem.
4. Bật mitigation an toàn.
5. Liên hệ provider theo severity/support plan.
6. Giao tiếp nội bộ/khách hàng theo quy trình.
7. Theo dõi restoration và eventual consistency/freshness.
8. Đối soát dữ liệu nếu cần.
9. Postmortem và corrective actions.

### Đừng gộp trách nhiệm

Nhà cung cấp có thể khôi phục data plane nhưng không biết business flow đã tạo booking duplicate vì retries; **customer phải kiểm dữ liệu nghiệp vụ**, không chỉ đợi status page chuyển xanh.

## 37. Phân loại lỗi trước khi mở support case

| Tín hiệu | Giả thuyết cần kiểm |
| --- | --- |
| `AccessDenied` | IAM/ACL, role trust, resource scope |
| `InvalidCredentials` | Secret rotation, token expiry, authSource |
| `Throttling` | Quota, hot key, capacity mode |
| `Timeout` | Network, client deadline, retries, DB service |
| `Connection refused` | Endpoint, routing/firewall, service health |
| `ConditionalCheckFailed` | Business conflict có thể hợp lệ |
| `InvalidQuery` | Unsupported API/query/index |
| High CDC lag | Consumer, queue, source/target throughput |

Không sửa mọi lỗi bằng cách cấp `admin`, nâng timeout lên vài phút hoặc tăng capacity. Chẩn đoán đúng loại lỗi trước.

## 38. Runbook: nghi ngờ managed DB data plane outage

~~~text
1. Confirm user SLO impact.
2. Compare region/service/tenant scope.
3. Check telemetry is not missing.
4. Inspect SDK errors and provider request IDs.
5. Test minimal known-safe read from authorized identity.
6. Check network/private endpoint/DNS/IAM.
7. Check provider health/advisories and open support case.
8. Apply bounded retry/load shedding/degraded mode.
9. Do not bypass business correctness checks.
10. Reconcile writes with unknown outcomes after recovery.
~~~

Một synthetic read có thể thành công trong khi conditional write path lỗi; kiểm **đúng operation và consistency scope** thay vì một ping đơn giản.

## 39. Runbook: PITR restore / accidental deletion

1. Xác nhận phạm vi xóa sai và thời điểm sớm nhất có thể.
2. Tạm dừng hoặc cô lập tác vụ tiếp tục gây lỗi.
3. Chọn recovery point và dữ liệu nào sẽ bị mất theo RPO.
4. Tạo restore target cô lập, không ghi đè authority đang chạy nếu chưa đánh giá.
5. Kiểm encryption keys/IAM/network.
6. Restore và xác nhận bản ghi/relationships/invariants.
7. Lập cách merge/replay legitimate writes sau recovery point.
8. Rebuild search/cache/CDC projections và đối soát IDs.
9. Cutover theo runbook, kiểm p99/error/freshness.
10. Ghi RTO thực tế, cảnh báo, dữ liệu cần sửa và bài học.

**Restore toàn bộ snapshot có thể làm mất các writes hợp lệ sau recovery point**. Không vội thay production dataset bằng backup cũ nếu chưa có kế hoạch reconcile.

## 40. Runbook: region failover

Trước incident:

- Có mapping primary/secondary endpoints.
- Biết RPO/RTO và replication mode.
- Có DNS/traffic routing mechanism.
- Có data integrity/conflict policy.
- Đã diễn tập trong môi trường an toàn.
- Có khả năng khóa writes ở old primary khi cần.

Trong incident:

~~~text
Detect primary-region failure
   |
   v
Verify secondary readiness and data position
   |
   v
Make authorized failover decision
   |
   v
Route clients + refresh connections
   |
   v
Verify write safety, SLO and data freshness
   |
   v
Reconcile after old region returns
~~~

Nếu hai regions cùng nhận writes mà không có conflict discipline, có thể xảy ra split-brain hoặc duplicated business effects. Failover phải tôn trọng **database consistency protocol và business invariants**, không chỉ DNS.

## 41. Chi phí: managed không phải “trả một mức cố định”

Tùy product, bill có thể gồm:

- Compute/node/tier.
- Provisioned/consumed capacity hoặc request units.
- Storage theo GB/tháng.
- Secondary indexes.
- Backup/snapshot/PITR storage.
- Cross-AZ/cross-region transfer, data egress.
- CDC/streams, exports.
- Monitoring/audit logs.
- Support plan.
- Restore, data migration, search/indexing.

### Cost model sơ bộ

\[
MonthlyCost\approx
Compute+Requests+StoredData+Backup+
Network+Streams+Observability+Support
\]

Đây là mô hình để tìm **cost drivers**, không phải phép định giá chuẩn. Giá/quota phụ thuộc nhà cung cấp, region, currency, tier và thời điểm; cần đọc bảng giá/contract hiện hành khi lập ngân sách thật.

## 42. Ví dụ read amplification và bill shock

Giả sử `searchListings` chạy một full scan thay vì index-targeted query:

~~~text
API request count: 1,000 / minute
Requested result: 20 items each
Actual scanned: 100,000 items per query
~~~

Provider có thể tính chi phí theo consumed reads, CPU/capacity, I/O, egress hoặc tier. Dù người dùng chỉ nhận vài KB, workload bên database có thể rất lớn.

Khách hàng phải:

- Dùng query explain/plans khi được hỗ trợ.
- Theo dõi scanned vs returned.
- Đặt cost budgets/anomaly alerts.
- Kiểm index/partition keys.
- Rate-limit dangerous admin/export paths.

**Provider không thể biết một query “hợp lệ nhưng đắt” có trái ý định nghiệp vụ của bạn hay không.**

## 43. TCO: tính cả chi phí con người và rủi ro

So self-managed và managed không chỉ so VM storage price:

| Chi phí | Self-managed | Managed |
| --- | --- | --- |
 DB setup/upgrade | Team vận hành trực tiếp | Có thể giảm |
 On-call/repair | Team chịu nhiều khâu | Provider thực hiện một phần |
 Cloud compute/storage | Trả theo infra | Có trong gói hoặc tính riêng |
 Backup/DR | Tự xây/diễn tập | Feature sẵn, vẫn phải diễn tập |
 Monitoring | Tự triển khai sâu | Một số metrics có sẵn, vẫn cần SLO |
 Compliance/audits | Team sở hữu | Provider chứng nhận một phần |
 Custom tuning/control | Chủ động nhiều | Có thể giới hạn |
 Provider dependency | Ít phụ thuộc API managed | Vendor-specific APIs/contract |
 Migration/exit | Có công vận hành | Có thể có egress/format conversion |

**Managed có thể giảm rủi ro vận hành thông thường nhưng tăng rủi ro dependency hoặc chi phí chuyển đổi**. Quyết định cần tính cả time-to-market, tính năng, nhân sự, khả năng phục hồi và tổng chi phí sở hữu.

## 44. Quota, rate limit và service limits

Các giới hạn có thể áp dụng:

~~~text
Max item/document size
Max request/transaction size
Max index count
Max partitions/collection/table count
Max request units or throughput
Max connections/in-flight requests
Max backup/restore jobs
Max stream retention/consumer throughput
Max regional capacity/scale rate
~~~

Với workload có burst, cần:

1. Liệt kê **hard/soft limits** áp dụng cho region/tier.
2. Đánh dấu có thể xin tăng quota hay không.
3. Thiết lập alerts đủ sớm.
4. Xem thời gian provider duyệt/tăng capacity.
5. Load test gần giới hạn trong môi trường an toàn.
6. Có graceful degradation thay vì retry storm.

Đừng đợi 95% quota mới yêu cầu tăng nếu lead time kéo dài hơn thời gian tăng trưởng dự báo.

## 45. Shared monitoring: không chỉ dashboard provider

Một bộ quan sát nên có:

| Lớp | SLIs/metrics |
| --- | --- |
| User/API | Availability, end-to-end p95/p99, error budget |
| SDK | Attempt count, timeout, throttling, client latency |
| DB | Operation latency, capacity, storage, replica health |
| Query model | Index usage, scanned/returned, hot partitions |
| Backup | Last successful backup, retention, restore drill date |
| Security | Auth failures, privileged changes, key/cert expiry |
| CDC | Source-to-visible lag, retry, DLQ, backlog |
| Cost | Requests, storage, egress, forecast/anomaly |
| Dependencies | IAM/KMS/DNS/endpoint/control plane health |

Một alert provider “database available” không cho biết ứng dụng có đang trả **đúng booking** hay không.

## 46. Cảnh báo có hành động

Không page chỉ vì CPU hoặc consumed capacity cao nếu đã dự kiến. Ngược lại, một risk quan trọng có thể cần báo **trước khi user bị ảnh hưởng**:

~~~text
PAGE:
  SLO fast burn, write outage, imminent quorum/data risk.

TICKET:
  Index regression, approaching quota,
  growth above forecast.

RUNBOOK:
  Owner, impact, scope, evidence, mitigation, escalation.
~~~

Các alerts với managed NoSQL phải cho biết **khi nào team tự xử lý**, khi nào liên hệ nhà cung cấp và cần gửi bằng chứng gì.

## 47. Runbook: throttling sau khi traffic tăng

1. Xác định operation, table/index/collection, region và tenant.
2. Kiểm throughput/capacity, request size, partition skew.
3. Phân biệt throttle với timeout/network error.
4. Kiểm SDK retries/backoff và request deadline.
5. Xem việc tăng capacity có nhanh/khả thi không.
6. Kiểm index/query/partition key gây chi phí cao.
7. Có thể giảm batch concurrency, rate-limit hot tenant, queue writes an toàn.
8. Không làm lỏng business constraints chỉ để tăng throughput.
9. Ghi cost implication và quota.
10. Xác nhận SLO, backlog và p99 phục hồi.

### Khi nên escalate?

Khi đã có bằng chứng requests nằm trong published limits/contract nhưng service vẫn throttling bất thường, hoặc provider telemetry và client behavior không nhất quán, mở support case kèm request IDs, timestamps, region và metrics.

## 48. Change management và Infrastructure as Code

Managed service được cấu hình bằng console/API/IaC. Những cấu hình này có thể ảnh hưởng nghiêm trọng:

- Public access/private endpoint.
- IAM users/roles/policies.
- Encryption key.
- Backup retention và PITR.
- Region/replica topology.
- Capacity mode/tier.
- TTL/indexes.
- Deletion protection.
- Audit/logging.

### Quy trình

~~~text
Change proposal
   |
   v
Review security + reliability + cost
   |
   v
Plan / diff / staging test
   |
   v
Apply with controlled identity
   |
   v
Observe SLOs and alerts
   |
   v
Record change / rollback or follow-up
~~~

**IaC chỉ giúp thay đổi có thể xem xét/tái hiện**; một template IaC sai vẫn có thể tắt backup hoặc mở DB ra Internet. Các guardrails như policy-as-code, approvals và drift detection phải gắn với trách nhiệm cụ thể.

## 49. Mẫu hợp đồng vận hành nội bộ

~~~yaml
service: "booking-managed-nosql"
environment: "production"
dataClassification: "sensitive customer data"
businessOwner: "booking"
technicalOwner: "data-platform"
providerSupportOwner: "cloud-platform"
managedProduct:
  family: "managed NoSQL"
  region: "approved-region"
  tier: "to-be-validated"
responsibilities:
  provider:
    - "underlying service operation per contract"
    - "managed engine maintenance within service scope"
  customer:
    - "schema and partition design"
    - "IAM, networking, application authorization"
    - "SLO monitoring and incident response"
    - "restore verification and data reconciliation"
security:
  workloadIdentity: "per-service least-privilege role"
  privateConnectivity: "required by policy"
  keyPolicy: "reviewed with security"
reliability:
  availabilitySlo: "team-defined"
  rpo: "team-defined"
  rto: "team-defined"
  backupRetention: "team-defined"
  failoverDrill: "scheduled"
capacity:
  loadProfile: "peak, burst, background"
  quotaAlerts: true
operations:
  runbooks:
    - "db outage"
    - "throttling"
    - "restore"
    - "region failover"
  escalationPath: "internal oncall then provider support"
exit:
  exportFormat: "to-be-tested"
  migrationRunbook: "required"
~~~

**Đây là tài liệu minh họa**, không phải YAML mà bất kỳ managed provider nào tự hiểu. Các trường `team-defined` và `to-be-validated` phải được đội sở hữu điền bằng quyết định đã phê duyệt trước khi đưa thành contract vận hành.

## 50. Phân quyền tác vụ quản trị và separation of duties

Một operator đọc metrics không nhất thiết cần quyền:

- Xóa cluster.
- Disable backups.
- Thay KMS key.
- Mở public endpoint.
- Export mọi records.

### Mô hình roles

| Role | Công việc | Giới hạn |
| --- | --- | --- |
| Observer | Read dashboards/config | Không mutate |
| Application deployer | Deploy app, config được duyệt | Không xóa data |
| DB operator | Scale, restore theo approval | Không tự thay quyền security |
| Security admin | IAM, keys, audit | Không tùy ý sửa business records |
| Break-glass | Emergency privileged actions | Audit/approval và rotation riêng |

**Audit trail phải phân biệt provider actions, customer operators và service identities** nếu sản phẩm có thông tin đó. Không dùng một root account cho automation, dev laptops và incident response.

## 51. Rủi ro vendor lock-in

Các nguồn phụ thuộc:

1. Proprietary query/transaction APIs.
2. Provider SDK-specific exceptions/retries.
3. Partition/index semantics.
4. IAM/roles và encryption key model.
5. CDC format/resume tokens.
6. Backup/export formats.
7. Managed network integration.
8. Observability/quota/billing APIs.
9. Cross-region replication behavior.
10. Contract/egress/pricing.

Lock-in không luôn xấu: một managed feature có thể mang lại giá trị lớn. Quan trọng là **nhận diện và quản lý chi phí thay đổi**, không tự hứa có thể thay database bằng sửa một connection string.

## 52. Portable architecture: tách domain khỏi SDK

~~~text
BookingService
      |
      v
BookingRepository (domain interface)
      |
      +--> ManagedProviderAAdapter
      |
      +--> FutureMigrationAdapter
~~~

Một interface ổn định có thể che API chi tiết nhưng không tự xóa semantic differences:

- Transaction scope.
- Conditional-write guarantees.
- Consistency levels.
- Query/index capabilities.
- Pagination/ordering behavior.
- Error/retry semantics.

### Ví dụ interface Java

~~~java
public interface BookingRepository {
    /**
     * Creates a booking only if the inventory condition
     * still holds. Implementations must preserve this
     * domain invariant, not just issue an unconditional put.
     */
    ReserveResult reserve(ReserveCommand command);
}

record ReserveCommand(
        String reservationId,
        String listingId,
        String idempotencyKey) {}

record ReserveResult(
        boolean committed,
        String status) {}
~~~

Interface này **chưa phải một implementation** và không mô tả mọi kiểu transaction. Nó đặt invariant để mỗi adapter phải chứng minh đúng thông qua tests.

## 53. Exit strategy: phải thử trước khi có khủng hoảng

Một phương án thoát provider tối thiểu phải trả lời:

- Export toàn bộ dữ liệu bằng cách nào?
- Có thể export theo bản nhất quán không?
- Dùng snapshot + CDC để giảm downtime được không?
- Ai có quyền đọc/export và chịu chi phí egress?
- Format có giữ indexes, timestamps, versions và TTL không?
- Target DB có cùng semantics về transactions/consistency không?
- Dữ liệu thay đổi trong lúc migration được bắt kịp thế nào?
- Có rollback/cutover/reconciliation?
- Backup cũ, credentials, logs có được xóa theo policy?
- Mất bao lâu ở data size production?

Không nên đợi tới lúc tranh chấp hợp đồng hoặc bị hạn chế quota mới phát hiện export throughput không đủ để rời hệ.

## 54. Migration hai pha: snapshot rồi CDC

~~~text
Old managed NoSQL (authority)
       |
       +---- Snapshot at known watermark --> New target
       |
       +---- CDC changes after watermark --> New target
                                                |
                                           Validate/reconcile
                                                |
                                           Controlled cutover
~~~

Các điểm phải thiết kế:

- Source snapshot boundary và CDC resume position.
- Duplicate/out-of-order changes.
- Idempotent apply.
- Version/sequence guard.
- TTL/deletes/tombstones.
- Target index rebuild.
- Bi-directional writes có cần không và tránh split-brain thế nào?
- Kiểm row/key counts, business identities và checksums.

**“Copy số bản ghi bằng nhau” không chứng minh state tương đương** nếu một record bị trùng và một record khác bị mất.

## 55. Hợp đồng dữ liệu: portability không chỉ export JSON

Một JSON document:

~~~json
{
  "reservationId": "R42",
  "amountMinor": 125000,
  "currency": "VND",
  "expiresAt": "2026-12-31T23:59:59Z",
  "version": 12
}
~~~

Khi chuyển database cần bảo toàn:

- Số nguyên và độ chính xác tiền tệ.
- Timestamp/timezone.
- Null/missing fields.
- Uniqueness/conditional write semantics.
- Sorting/collation.
- TTL/expiry.
- Change capture/order.
- Idempotency/business keys.

Ngay cả khi JSON serialize được giống nhau, **query semantics và concurrency correctness** vẫn có thể khác.

## 56. Đánh giá nhà cung cấp bằng RACI

**RACI** gán:

- **R (Responsible):** người thực thi.
- **A (Accountable):** người chịu trách nhiệm cuối cho kết quả.
- **C (Consulted):** bên cần tham vấn.
- **I (Informed):** bên cần được thông báo.

Ví dụ nội bộ (không thay hợp đồng pháp lý):

| Hoạt động | Platform team | App team | Security | Provider |
| --- | --- | --- | --- | --- |
| Chọn partition key | C | A/R | I | C |
| Set IAM policies | R | C | A | I/C |
| Cluster patch theo gói managed | C/I | I | I | R theo contract |
| Định nghĩa app SLO | C | A/R | C | I |
| Bật backup/PITR | R | A/C | C | C/R theo service |
| Restore drill | R | A/C | C | C |
| Điều tra provider outage | R | A/C cho app impact | I | R cho phần provider |
| Data residency review | C | A/C | R | C |

Không có một ma trận RACI đúng cho mọi công ty. Điều quan trọng là **không để một công việc quan trọng không có owner** vì cả hai phía cùng nghĩ bên kia sẽ làm.

## 57. Supplier due diligence trước khi chọn dịch vụ

Một checklist đánh giá:

1. Database API/feature compatibility.
2. Consistency/transaction/conditional-write guarantees.
3. Regions/AZ topology và failover contract.
4. SLA và tất cả điều kiện áp dụng.
5. Backup/PITR và restore throughput thực tế.
6. Data residency, compliance, subprocessors/support access.
7. IAM, network private access, TLS, CMK.
8. Metrics/audit logs và export.
9. Capacity limits, hot partitions, autoscaling lag.
10. Quota increase process và lead time.
11. Change/maintenance notifications.
12. Support plan, severity, escalation.
13. Billing, egress, backup/network/monitoring fees.
14. Export/migration options.
15. Long-term lifecycle/deprecation policy.
16. Testability và fault-injection boundaries.

Thay mọi câu “vendor hỗ trợ” thành **“hỗ trợ trên gói/region nào, được cấu hình ra sao và đã xác minh thế nào?”**.

## 58. Proof of concept phải kiểm sản phẩm thật

Một PoC managed NoSQL tối thiểu:

~~~text
Representative data model
        |
        v
Production-like dataset
        |
        v
Application SDK + IAM + private networking
        |
        v
Read/write/scan peak test
        |
        v
Replica failure / restore / key rotation
        |
        v
SLO, cost and responsibility evaluation
~~~

### Các kịch bản cần có

- Peak/burst với realistic key skew.
- Query index performance.
- Concurrent conditional writes.
- SDK timeouts/retries.
- Throttling và scale reaction.
- Backup/PITR restore.
- Maintenance/failover (theo khả năng môi trường test).
- CDC lag và replay.
- IAM deny tests và network isolation.
- Cost projection/observability.

Không phá hoại hoặc tiêm lỗi trực tiếp trên production nếu chưa có phê duyệt và phương án an toàn. Provider-managed failure testing có thể bị giới hạn trong chính sách dịch vụ.

## 59. Ví dụ so sánh một lựa chọn self-managed và managed

### Tình huống

Một nhóm có ba kỹ sư vận hành một Cassandra cluster. Họ phải xử lý repair, node replacement, backup, disk saturation và nâng cấp. Một managed offering có thể giảm công việc đó.

### Bảng cân nhắc

| Tiêu chí | Self-managed | Managed |
| --- | --- | --- |
| Control storage engine | Rộng | Hạn chế tùy gói |
| Đội chịu patch OS/engine | Nội bộ | Provider trong scope |
| Khả năng custom tuning | Cao | Có thể thấp hơn |
| Repair/rebalance effort | Nội bộ | Có thể được provider quản lý |
| Bảo đảm query model | App team | Vẫn app team |
| Audit/IAM | Nội bộ cấu hình | Provider primitives, app config |
| Backup restore test | Nội bộ | Vẫn phải test |
| Chi phí vận hành | Labor + infra | Service fees + remaining labor |
| Chuyển sang vendor khác | Có công việc | Có thể phức tạp theo APIs |

**Quyết định không thể dựa chỉ vào “managed có ít nút bấm hơn”.** Phải cân tính năng, SLO, nhân sự, chi phí, dữ liệu và khả năng kiểm soát.

## 60. Case study: nhà cung cấp khỏe, ứng dụng mất dữ liệu logic

### Bối cảnh

Booking API nhận cùng một yêu cầu hai lần sau timeout. Mỗi lần ứng dụng tự sinh một `reservationId` mới. Managed database chấp nhận cả hai writes vì keys khác nhau.

### Kết quả

~~~text
Request intent: book one night once
First write:  R100 committed
Response:     lost
Retry write:  R101 committed
Outcome:      duplicate booking
~~~

### Phân tích trách nhiệm

Provider thực thi writes hợp lệ theo API. Ứng dụng chịu trách nhiệm **stable idempotency key**, conditional uniqueness và reconciliation. Nếu provider có bug vi phạm documented atomicity guarantee, đó lại là vấn đề khác và cần evidence/support.

### Bài học

**Managed availability không thay business transaction design.**

## 61. Case study: backup có nhưng không restore đúng hạn

### Bối cảnh

Team bật daily backup và tin tưởng “backup managed đã an toàn”. Khi accidental delete xảy ra, phải restore 2 TiB và rebuild indexes, sau đó replay CDC.

### Kết quả giả định

~~~text
Provider restore job: 2 hours
Index rebuild:         1 hour
CDC catch-up:          45 minutes
Validation/cutover:    30 minutes
Total:                 4 hours 15 minutes
Business RTO target:   1 hour
~~~

### Phân tích

Backup có thể hoàn toàn đúng theo hợp đồng, nhưng **RTO ứng dụng không đạt** vì chưa diễn tập và tối ưu recovery workflow. Cần phân tầng hot/critical data, snapshot strategy, recovery sizing, runbook và mục tiêu đã cam kết.

## 62. Case study: CMK bị disable

### Bối cảnh

Nhóm bảo mật quản lý customer-managed encryption key. Một policy change vô tình disable key hoặc rút quyền database service sử dụng key.

### Hệ quả khả dĩ

Tùy product và key-caching semantics, reads/writes, backups hoặc restores có thể gặp lỗi. Nhà cung cấp không nhất thiết có quyền tự bật lại customer key.

### Bài học

Key rotation/revocation là **dependency của database availability/recoverability**. Team phải có owner, change control, rollback chính sách an toàn và fault test phù hợp.

## 63. Case study: chi phí tăng khi query scan

Một release thay query targeted read thành scan/filter, làm số records đọc vật lý tăng hàng nghìn lần. Managed DB vẫn trả response, nhưng latency và consumed capacity/cost tăng.

### Hướng xử lý

1. So query fingerprints trước/sau.
2. Đo scanned/returned và consumed capacity.
3. Kiểm index/key design.
4. Rollback release nếu cần.
5. Đặt budget/quota alerts.
6. Test query cost trong CI/performance staging.

**Cost optimization cũng là trách nhiệm kỹ thuật ứng dụng**, không chỉ trách nhiệm procurement.

## 64. Ma trận fault injection

| Test | Sự cố giả lập | Điều cần chứng minh |
| --- | --- | --- |
| F1 | SDK timeout sau write commit | Retry không tạo duplicate effect |
| F2 | IAM permission bị từ chối | Không tự tăng quyền |
| F3 | Secret hết hạn | Credential refresh/alerts |
| F4 | Private endpoint/DNS lỗi | Fail closed, triage network |
| F5 | Throttling dưới peak | Backoff, rate limit và SLO |
| F6 | Hot partition | Per-key visibility và data model mitigation |
| F7 | Control-plane scale API unavailable | Headroom/degraded-mode plan |
| F8 | Managed DB endpoint unavailable | Escalation + app resilience |
| F9 | Restore từ PITR point | RPO/RTO, key/roles, consistency |
| F10 | CDC consumer pause | Freshness/backlog alerts |
| F11 | Provider maintenance/failover simulation | Connections/retries/SLI behavior |
| F12 | Region failover drill | Data positions, routing, conflict safety |
| F13 | CMK unavailable (trong môi trường test) | Key dependency/runbook |
| F14 | Backup deletion attempt | IAM deny/delete protection |
| F15 | Query scan regression | Cost/performance detection |
| F16 | Export/exit rehearsal | Data portability và throughput |

**Mỗi fault test phải nêu environment, permission và rollback conditions**. Không dùng production data thật trong destructive experiments nếu không có biện pháp an toàn đã duyệt.

## 65. Bài tập thực hành

### Bài 1 — Bảng shared responsibility

Cho một Booking API dùng NoSQL managed, lập ma trận 15 nhiệm vụ và gán nhà cung cấp hoặc khách hàng cho **operate, configure, assure**.

**Gợi ý:** backup feature có thể do provider operate nhưng customer configure/restore-test.

### Bài 2 — Managed không phải “zero ops”

Nêu năm công việc còn thuộc đội application dù provider tự patch database.

**Gợi ý:** index, partition key, IAM, SLO, business invariant.

### Bài 3 — Control plane

Data plane còn chạy, control-plane scaling API lỗi trong lúc peak tăng. Vì sao đây vẫn có thể thành incident? Nêu mitigation.

### Bài 4 — SLA

Tính downtime tương ứng 99,9% và 99,99% trong 30 ngày. Vì sao kết quả không chứng minh downtime thực tế của app?

**Gợi ý:** 43,2 và 4,32 phút; end-to-end dependencies.

### Bài 5 — Availability vs durability

Một database có availability cao nhưng ứng dụng xóa nhầm một collection. Vì sao cần backup/PITR?

### Bài 6 — RPO/RTO

Restore job 22 phút, detect/decision/validation/cutover cộng thêm 26 phút. RTO thực tế từ khi phát hiện là bao nhiêu?

**Gợi ý:** 48 phút.

### Bài 7 — PITR

Bạn restore dữ liệu về 10:00 nhưng từ 10:00 tới 10:15 có nhiều writes hợp lệ. Thiết kế cách reconcile thay vì thay production database một cách mù quáng.

### Bài 8 — Backups và keys

Backup được mã hóa bằng customer-managed key đã disable. Ai phải khôi phục quyền key và cần kiểm gì trước restore?

### Bài 9 — Multi-region

Provider hỗ trợ cross-region replication không đồng nghĩa RPO=0. Hãy giải thích asynchronous lag và failover.

### Bài 10 — IAM

Booking API dùng role có quyền xóa mọi tables. Thiết kế role giới hạn đúng actions/resources.

### Bài 11 — Tenant isolation

Service DB role truy cập toàn bảng bookings. User U1 có thể đọc booking U2 không? Nêu lớp kiểm quyền bắt buộc.

### Bài 12 — Network

Database có password mạnh nhưng public endpoint mở mọi IP. Thiết kế phương án giảm exposure.

### Bài 13 — Encryption

Phân biệt at-rest, in-transit, CMK và application-level encryption. Khi nào CMK làm tăng trách nhiệm vận hành?

### Bài 14 — Data residency

Region chính đã được chọn đúng quốc gia. Nêu bốn đường khác vẫn có thể làm dữ liệu hoặc metadata nằm ngoài vùng mong muốn.

### Bài 15 — Hot partition

Một tenant tạo 80% writes vào một partition key. Vì sao autoscaling aggregate chưa chắc giải quyết? Đề xuất đổi data model.

### Bài 16 — Throttling

Managed DB trả throttling. Thiết kế bounded exponential backoff, idempotency và rate limit.

### Bài 17 — Java SDK

Thay static access key bằng workload IAM role và SDK credentials provider. Cần kiểm những trust boundaries nào?

### Bài 18 — Unknown outcome

Database đã commit booking nhưng response mất. Tại sao timeout không cho phép tự tạo booking ID khác khi retry?

### Bài 19 — Version compatibility

Một managed service chỉ hỗ trợ một phần MongoDB protocol. Thiết kế feature-usage matrix và tests trước migration.

### Bài 20 — Maintenance

Provider thông báo nâng cấp trong tuần lễ cao điểm. Đội ứng dụng phải kiểm driver, failover, retry và điều khoản nào?

### Bài 21 — Observability

Vẽ monitoring path từ API latency tới SDK retry, provider throttle, database storage và CDC lag.

### Bài 22 — Support case

Nhà cung cấp yêu cầu evidence. Chọn các fields cần ghi mà không lộ token hoặc PII.

### Bài 23 — Root cause ownership

Latency tăng vì một index bị ứng dụng xóa, không có provider outage. Ai chịu trách nhiệm sửa và cần evidence gì?

### Bài 24 — Backup restore drill

Thiết kế test PITR cho dữ liệu 1 TiB, có index rebuild và CDC catch-up. Đặt pass/fail theo RPO/RTO.

### Bài 25 — Cost

Một query mới scan 100.000 records để trả 20. Nêu các cost drivers và thay đổi query/index cần đo.

### Bài 26 — Quota

Một soft limit cần provider duyệt tăng trước 5 ngày, traffic dự báo vượt limit trong 3 ngày. Thiết kế headroom và escalation.

### Bài 27 — IaC

Thiết kế review policy cho thay đổi database bật public endpoint và tắt backups. Những controls nào nên chặn?

### Bài 28 — RACI

Viết RACI cho patch, backup/PITR, IAM, app SLO, incident triage và provider escalation.

### Bài 29 — Vendor lock-in

Kể năm loại dependency ngoài query language khi chuyển khỏi managed NoSQL.

### Bài 30 — Domain adapter

Interface `BookingRepository.reserve` có thể che SDK API nhưng không tự đảm bảo atomic conditional write. Viết các contract tests cần thiết.

### Bài 31 — Export

Thiết kế exit rehearsal với dataset lớn: snapshot watermark, CDC catch-up, reconciliation và network egress.

### Bài 32 — Search freshness

Managed source DB khỏe nhưng index/search chậm 30 phút. Ai phải chịu trách nhiệm với user-facing freshness SLO?

### Bài 33 — Case study CMK

Security team disable key khi database đang chạy. Thiết kế role owner và khôi phục theo trust boundary.

### Bài 34 — Self-managed vs managed

So TCO cho hai phương án cùng SLO, gồm compute/storage, on-call, repair, backup, support, network và migration costs.

### Bài 35 — Managed PoC

Lập một PoC với workload peak, hot key, index regression, SDK retries, IAM deny, backup restore, provider maintenance và cost tracking.

### Bài 36 — Data-plane outage

Java application nhận timeout hàng loạt. Tạo checklist phân biệt mạng/IAM/client bug với provider outage.

### Bài 37 — Failure mode

Một AZ hỏng nhưng replica placement còn quorum. Vì sao vẫn cần kiểm p99, cache warm-up, failover và capacity?

### Bài 38 — Security incident

Credential của CDC worker bị lộ. Liệt kê các bước revoke/rotate, audit và kiểm quyền trong managed service.

### Bài 39 — Combined failure

Control plane down trong lúc disk capacity tăng và một node mất. Đề xuất hành động mà customer có thể thực hiện ngay, cùng câu hỏi cần hỏi provider.

### Bài 40 — Bài tập tổng hợp

Một ứng dụng cho thuê triển khai Booking API (Java) trên managed NoSQL, Redis managed cache, CDC và managed search. Hãy tạo bản thiết kế sản xuất bao gồm:

1. Ma trận operate/configure/assure và RACI.
2. SLI/SLO user-facing, provider SLA assumptions.
3. Quy tắc consistency/idempotency để không double-booking.
4. IAM/private network/TLS/encryption/key ownership.
5. Backup/PITR và RPO/RTO cùng restore drill.
6. Multi-AZ/region failover và data reconciliation.
7. Quota/autoscaling/hot partition/cost controls.
8. Metrics/alerts/runbooks/escalation tới provider.
9. Feature-compatibility và maintenance testing.
10. Exit strategy bằng snapshot+CDC với validation.

**Gợi ý:** mọi câu “provider sẽ lo” phải được chuyển thành một bằng chứng hợp đồng, một cấu hình có owner hoặc một bài kiểm thử có thể lặp lại.

## 66. Checklist quyết định sử dụng managed NoSQL

1. Đã xác định rõ sản phẩm, tier, region và giới hạn nào được áp dụng chưa?
2. Có bảng trách nhiệm theo vận hành/cấu hình/kiểm chứng không?
3. Có owner của application SLO và provider escalation không?
4. SLA đã được đọc kèm exclusions, support process và điều kiện eligibility chưa?
5. Có phân biệt control-plane và data-plane dependencies không?
6. Data model/partition keys/indexes đã benchmark với workload thật chưa?
7. Transactions/conditional writes đáp ứng business invariants chưa?
8. Có kế hoạch xử lý timeout outcome unknown và idempotency chưa?
9. IAM roles/service identities có least privilege không?
10. Private networking/TLS đã được kiểm tra cấu hình thực tế chưa?
11. Encryption và key lifecycle có owner rõ không?
12. Data residency/retention/deletion/backup locations đã được xác minh chưa?
13. Backup/PITR có được bật và retention hợp RPO không?
14. Đã restore-test với dataset đủ lớn và đo RTO toàn luồng chưa?
15. Có hiểu cross-region replication/lag/failover/conflicts không?
16. Có kiểm consistency/quorum behavior trong failure scenarios không?
17. Capacity planning đã xét quotas, hot partitions và scale lag chưa?
18. SDK retries có backoff, jitter, deadline và idempotency không?
19. Có theo dõi request SLO ngoài provider metrics không?
20. Có theo dõi CDC/source-to-visible freshness không?
21. Có thể lấy provider request IDs để điều tra incident không?
22. On-call biết khi nào tự xử lý và khi nào mở provider support case không?
23. Có runbooks cho outage, throttling, restore, failover và IAM/KMS failure không?
24. Maintenance/version compatibility đã được kiểm thử chưa?
25. IaC changes có review, guardrails, drift detection không?
26. Có billing alerts cho requests, storage, backups, egress và streams không?
27. Vendor lock-in đã được lượng hóa theo API/consistency/export không?
28. Có exit rehearsal để đo data migration throughput chưa?
29. Có test riêng cho tenant isolation và business correctness không?
30. Có lịch review ma trận trách nhiệm khi thay gói/provider/tier không?

## 67. Tổng kết

1. **Managed NoSQL giảm công việc vận hành, không xóa trách nhiệm sản phẩm.** Nhà cung cấp vận hành phần nền tảng theo hợp đồng; khách hàng vẫn sở hữu dữ liệu, quyền truy cập, workload và mục tiêu người dùng.
2. **Shared responsibility có nhiều lớp:** ai *operate*, ai *configure*, ai *assure*. Một backup do provider thực hiện vẫn cần customer kiểm restore/RTO.
3. **Control plane và data plane là hai phụ thuộc khác nhau.** App có thể đang khỏe nhưng không scale được, hoặc control plane bình thường trong khi user queries lỗi.
4. **SLA provider không bằng SLO end-to-end.** Cần đo ở biên ứng dụng, biết exclusions và support paths.
5. **Availability, durability, consistency, freshness và recoverability là các thuộc tính riêng.** Replication không thay backup, provider uptime không ngăn business duplicate.
6. **IAM, network, TLS, encryption, data classification và residency cần cấu hình đúng.** Không xem việc provider có feature là bằng chứng security đã đạt.
7. **Data model, key distribution, queries và idempotency vẫn do khách hàng quyết định.** Throttling/hot partition có thể xảy ra ngay cả khi service đáp ứng hợp đồng.
8. **Backup/PITR, RPO/RTO và region failover phải diễn tập.** Provider restore hoàn thành chưa chứng minh ứng dụng đã phục hồi và reconciled.
9. **Vận hành managed vẫn cần metrics, alerts, runbooks, change management và incident commander.** Đội nội bộ phải thu evidence để phối hợp provider.
10. **Chi phí, quotas, bảo trì, compatibility và vendor lock-in là một phần kiến trúc**, không phải vấn đề chỉ xử lý sau khi triển khai.
11. **Đánh giá provider bằng PoC/fault tests và responsibility matrix**, không chỉ bảng tính năng tiếp thị.
12. **Có exit plan từ sớm** giúp kiểm soát rủi ro về dữ liệu, chi phí chuyển đổi và quyền thương lượng.

**Nguyên tắc thực hành:** trước khi chuyển một NoSQL cluster sang dịch vụ managed, đừng chỉ hỏi **“nhà cung cấp làm được những gì?”**. Hãy hỏi thêm **“một yêu cầu nghiệp vụ sai ai ngăn?”, “mất region ai quyết định failover?”, “mất dữ liệu logic ai khôi phục?”, “SLO người dùng ai chứng minh?”, “khi provider trục trặc ai xử lý bước đầu?”, và “nếu cần rời dịch vụ ai có khả năng đưa dữ liệu ra an toàn?”**. Khi mọi câu trả lời có owner, cấu hình, bằng chứng và runbook, ranh giới trách nhiệm mới đủ rõ để vận hành managed NoSQL đáng tin cậy.
