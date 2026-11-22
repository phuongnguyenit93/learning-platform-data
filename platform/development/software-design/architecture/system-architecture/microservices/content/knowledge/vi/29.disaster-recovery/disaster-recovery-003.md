# Sao lưu, phục hồi và kiểm chứng tính sử dụng được của bản sao

> **Chủ đề:** Software Design · System Architecture · Microservices  
> **Nhóm kiến thức:** Khôi phục thảm họa (Disaster Recovery)  
> **Mục tiêu:** Thiết kế chiến lược backup và restore có thể kiểm chứng cho hệ thống nhiều dịch vụ, phân biệt rõ “đã tạo được bản sao” với “đã phục hồi được dịch vụ và dữ liệu nghiệp vụ trong RPO/RTO cam kết”.

## 1. Tại sao có backup chưa chắc đã khôi phục được?

Giả sử một nền tảng thương mại điện tử có **Order Service**, **Payment Service**, **Inventory Service**, **Notification Service**, PostgreSQL, Kafka, object storage và một Kubernetes cluster.

Một ngày, vùng triển khai chính gặp sự cố nghiêm trọng hoặc một tài khoản quản trị bị chiếm quyền. Tổ chức thấy dashboard ghi **backup_success=1** suốt 30 ngày, nhưng khi khôi phục thì phát hiện:

- File backup có tồn tại nhưng bị cắt cụt hoặc không đọc được.
- Bản sao database đã quá cũ; WAL/binlog cần thiết cho point-in-time recovery đã bị xóa.
- Backup được mã hóa, nhưng khóa giải mã nằm ở vùng đã mất.
- Có bản sao database nhưng thiếu object storage chứa hóa đơn/ảnh/tệp đính kèm.
- Restore PostgreSQL xong, ứng dụng mới không còn tương thích schema cũ.
- Các dịch vụ được khôi phục tại nhiều mốc thời gian không nhất quán; Order ghi đã thanh toán, Payment ghi chưa xác nhận.
- Kafka consumer chạy lại sự kiện đã xử lý và tạo email hoặc nghiệp vụ trùng.
- Bản sao được lưu cùng tài khoản/quyền quản trị với production, nên kẻ tấn công đã xóa cả backup.
- Restore thành công về mặt kỹ thuật nhưng không có DNS, secrets, certificates hoặc cấu hình để phục vụ traffic.

**Backup success chỉ nói rằng một bước tạo bản sao đã báo hoàn thành.** Nó không chứng minh bản sao còn nguyên vẹn, có thể giải mã, được hỗ trợ bởi phiên bản phần mềm hiện tại, khôi phục đúng nghiệp vụ hoặc đạt thời gian phục hồi cam kết.

> **Định nghĩa thực dụng:** Một bản sao có giá trị khi có thể dùng nó để dựng lại một trạng thái hệ thống được chấp nhận, trong thời gian và mức mất dữ liệu cho phép, bằng một quy trình đã thực hành và có bằng chứng kiểm tra.

## 2. Phân biệt backup, replication, high availability và disaster recovery

| Khái niệm | Giải quyết | Không bảo đảm |
|---|---|---|
| **Backup** | Giữ dữ liệu/định nghĩa hệ thống tại một hoặc nhiều thời điểm để phục hồi | Tự động failover hay khả năng restore nhanh |
| **Replication** | Sao chép thay đổi từ nguồn sang replica, giảm độ trễ dữ liệu | Chống xóa nhầm hoặc dữ liệu hỏng bị replicate sang |
| **High Availability (HA)** | Tiếp tục phục vụ khi một thành phần/node/zone lỗi | Phục hồi từ lỗi logic hoặc mất cả vùng theo RPO xác định |
| **Disaster Recovery (DR)** | Khôi phục năng lực nghiệp vụ sau sự cố diện rộng hoặc mất dữ liệu | Tự đảm bảo không mất dữ liệu nếu không thiết kế nhất quán |
| **Archive** | Lưu dữ liệu lâu dài vì phân tích/pháp lý | Dùng được để khôi phục trạng thái ứng dụng |
| **Snapshot** | Chụp trạng thái tài nguyên tại một thời điểm | Nhất quán ứng dụng hoặc khả năng chạy trên môi trường mới |

Ví dụ một PostgreSQL standby replication giúp failover khi node chính chết. Nhưng nếu một migration xóa nhầm 10.000 đơn hàng, lệnh xóa có thể lan sang standby gần như ngay lập tức. Cần **backup versioned/PITR** để quay về thời điểm trước thao tác lỗi.

Tương tự, nhiều bản sao object storage giữa vùng có thể tăng durability, nhưng nếu cơ chế replication cũng sao chép delete marker/ransomware-encrypted objects, chỉ replication không tạo một **điểm phục hồi độc lập**.

**Không đồng nhất replica đang chạy với bản backup có thể quay lại quá khứ.**

## 3. RPO và RTO là hợp đồng phục hồi

Hai chỉ số thiết kế bắt buộc:

- **RPO — Recovery Point Objective:** lượng dữ liệu tối đa tổ chức chấp nhận mất, đo bằng khoảng cách giữa trạng thái phục hồi được và thời điểm xảy ra sự cố. RPO 5 phút không đồng nghĩa chắc chắn sẽ chỉ mất 5 phút nếu hệ thống không chứng minh được chuỗi backup/replication.
- **RTO — Recovery Time Objective:** khoảng thời gian mục tiêu để khôi phục mức dịch vụ đã định nghĩa sau sự cố. RTO 1 giờ có thể là “API nhận được đơn mới” hoặc “toàn bộ báo cáo lịch sử hoạt động”; phải nói rõ tiêu chí.

Ví dụ:

~~~text
09:00  base backup hoàn thành
09:40  WAL cuối cùng được chuyển tới kho dự phòng
09:45  region chính mất hoàn toàn
10:30  khôi phục xong database, ứng dụng ready

Restore point:   09:40
Incident time:   09:45
Data loss window: khoảng 5 phút (RPO thực đo, giả định timeline rõ)
Recovery elapsed: khoảng 45 phút (RTO thực đo)
~~~

**Thời điểm backup bắt đầu, kết thúc và thời điểm dữ liệu cuối cùng được ghi bền vững** là những mốc khác nhau. Với backup đang chạy, không lấy thời điểm kết thúc job làm recovery point nếu loại backup không có tính nhất quán tại mốc đó.

### 3.1. Ví dụ phân tầng theo nghiệp vụ

| Thành phần | RPO mục tiêu minh họa | RTO mục tiêu minh họa | Lý do |
|---|---|---|---|
| Payment ledger và đối soát | RPO rất thấp theo quy định nghiệp vụ | Hồi phục luồng quan trọng sớm | Giao dịch tiền không dễ chấp nhận mất |
| Order database | Vài phút, tùy chính sách | Dưới vài giờ | Đơn hàng và trạng thái cần bền vững |
| Inventory | Phù hợp với reconciliation design | Theo khả năng đặt hàng | Có thể đối chiếu tồn kho từ nguồn khác trong một số mô hình |
| Product catalog | Có thể dài hơn nếu nguồn dữ liệu tái dựng được | Theo mức ưu tiên | Có thể dựng lại từ upstream source |
| Cache Redis | Có thể RPO dài hoặc tái tạo | Thường phục hồi qua cache warm-up | Nếu chỉ cache, không là nguồn sự thật |
| Search index | Có thể rebuild từ DB/event log | Phụ thuộc lượng dữ liệu | Index là dữ liệu dẫn xuất, trừ khi có state không tái dựng được |

Các con số trong bảng chỉ là **ví dụ phân tầng**, không phải tiêu chuẩn chung. RPO/RTO phải do owner nghiệp vụ phê duyệt cùng bộ phận vận hành, bảo mật và yêu cầu pháp lý.

### 3.2. RPO/RTO ở mức chuỗi phụ thuộc

Payment API có thể ready sau 10 phút nhưng không thể xử lý nếu database credentials, DNS hay ledger vẫn chưa phục hồi. **RTO nghiệp vụ** phải bao gồm dependency chain cần cho hành trình sử dụng thực tế, không chỉ thời gian một Pod chuyển trạng thái Running.

## 4. Lập danh mục “đâu là dữ liệu cần phục hồi”

Trước khi chọn công cụ backup, cần làm rõ tài sản và quan hệ:

~~~text
Order Service
  ├── PostgreSQL (orders, order_items, outbox)
  ├── Object storage (invoice PDF, attachments)
  ├── Kafka events / offsets / schemas
  ├── Secrets & encryption keys
  ├── Config & deployment manifests
  └── External payment provider references

Payment Service
  ├── Payment DB / ledger
  ├── Provider transaction IDs
  ├── Reconciliation state
  └── Idempotency records

Shared platform
  ├── Kubernetes manifests / cluster bootstrap
  ├── DNS, certificates, IAM, NetworkPolicies
  ├── Artifact registry / immutable images
  └── Monitoring, alerting, runbooks
~~~

Không phải mục nào cũng cần sao lưu theo cùng một cách:

- **Source of truth** như order/payment DB cần backup nhất quán, lịch sử và khả năng restore.
- **Derived data** như search index có thể rebuild nếu nguồn đủ và RTO cho phép.
- **Secrets/keys** phải có cơ chế sống sót sự cố, phân quyền và rotation.
- **Infrastructure definitions** thường được version trong Git/IaC nhưng phải bảo đảm có thể bootstrap khi Git/registry/SSO gặp sự cố.
- **External dependencies** như cổng thanh toán không thể “backup” từ phía mình; cần giữ provider transaction IDs và quy trình đối soát.

**Một bản backup của Order DB không tương đương backup toàn bộ khả năng đặt hàng.**

## 5. Phân loại kỹ thuật backup

### 5.1. Full backup

Tạo bản sao toàn bộ dữ liệu trong phạm vi được chọn. Dễ hiểu khi restore nhưng có thể tốn thời gian, I/O và dung lượng.

### 5.2. Incremental backup

Chỉ lưu thay đổi kể từ bản backup được tham chiếu gần nhất theo cơ chế công cụ. Ít dữ liệu mỗi lần, nhưng restore có thể cần nhiều đoạn/chains. Nếu một mắt xích hỏng, khả năng phục hồi bị ảnh hưởng.

### 5.3. Differential backup

Lưu thay đổi từ một full backup mốc. Thường restore cần full + một differential thích hợp; kích thước differential có thể tăng theo thời gian. Tên và semantics có thể khác nhau giữa vendor.

### 5.4. Logical backup

Xuất dữ liệu ở mức database object/SQL/logical records, ví dụ **pg_dump** với PostgreSQL. Phù hợp cho một số mục tiêu migration, restore schema/table có lựa chọn và kiểm tra dữ liệu. Nhưng trên DB lớn có thể mất thời gian, không bao gồm toàn bộ cấu hình hạ tầng/roles/tablespaces nếu không lập kế hoạch, và **không thay thế một chiến lược PITR vật lý có WAL**.

### 5.5. Physical backup

Sao chép dữ liệu và các thành phần cần thiết ở mức storage/DB engine, phối hợp với cơ chế consistency. Ví dụ **PostgreSQL base backup + WAL archives**. Phù hợp phục hồi cluster lớn, PITR tùy cấu hình, nhưng có yêu cầu tương thích phiên bản/engine và cách lưu dữ liệu chặt chẽ.

### 5.6. Storage snapshot

Snapshot volume/block có thể nhanh, nhưng một snapshot **crash-consistent** không tự đảm bảo ứng dụng đã flush buffer, transaction across disks hoặc nhiều database có cùng mốc logic. Cần dùng cơ chế quiesce/backup mode/application-aware snapshot theo hệ quản trị dữ liệu.

### 5.7. Continuous backup / log shipping

Dùng **WAL** (PostgreSQL), **binary log** (MySQL) hoặc change log phù hợp để có nhiều recovery points gần nhau. Nhưng chuỗi logs, base backup và metadata phải **đầy đủ và tương thích**; thiếu một đoạn có thể khiến không thể phục hồi tới mốc mong muốn.

**Chọn theo workload:** Kích thước dữ liệu, RPO, RTO, khả năng restore và chi phí lâu dài. Không chạy thêm snapshot hàng giờ rồi mặc định đã đáp ứng RPO 1 phút.

## 6. Backup có tính nhất quán: Một file đầy đủ chưa chắc là trạng thái hợp lệ

Có ít nhất ba cấp độ nhất quán cần phân biệt:

1. **Crash-consistent:** giống trạng thái hệ thống sau mất điện; DB engine có thể cần redo/recovery từ logs.
2. **Application-consistent:** ứng dụng/DB phối hợp để snapshot phản ánh trạng thái hợp lệ theo giao thức của nó.
3. **Business-consistent:** các quan hệ nghiệp vụ giữa nhiều dịch vụ/nguồn dữ liệu không mâu thuẫn hoặc có quy trình reconcile rõ ràng.

Ví dụ Order Service sử dụng **transactional outbox**:

~~~text
Transaction Order DB:
  INSERT orders(id=O1001, status=CONFIRMED)
  INSERT outbox(event=OrderConfirmed, aggregate_id=O1001)
COMMIT
~~~

Backup Order DB phải chứa **cùng một trạng thái transaction**: hoặc cả hai bản ghi, hoặc không bản ghi nào. Sao chép file dữ liệu khi PostgreSQL đang ghi mà không có backup protocol phù hợp có thể tạo bản sao không dùng được.

Ở cấp **Order DB vs Payment DB**, hai nguồn không thể tự nhiên có cùng một transaction chung. Nếu backup mỗi DB ở một mốc khác nhau, hệ thống phục hồi cần reconciliation workflow, idempotent event processing và kiểm tra payment provider status.

**Nhất quán đa dịch vụ là bài toán nghiệp vụ, không thể giải quyết chỉ bằng chọn cùng giờ backup cho mọi database.**

## 7. PostgreSQL: Logical backup và restore có kiểm tra

Ví dụ minh họa một database **shop_orders**. Dùng công cụ client tương thích PostgreSQL server và credential được cấp theo nguyên tắc least privilege.

~~~bash
# Backup dạng custom để có thể xem TOC và chọn mục khi restore.
pg_dump \
  --host=orders-db.internal.example \
  --username=backup_reader \
  --dbname=shop_orders \
  --format=custom \
  --file=shop_orders_2026-11-12.dump

# Kiểm tra phần mục lục/đối tượng có trong archive.
pg_restore --list shop_orders_2026-11-12.dump
~~~

**pg_restore --list chỉ chứng minh archive đọc được đến mức liệt kê cấu trúc**, không chứng minh dữ liệu đã restore thành công, có đầy đủ quan hệ hay ứng dụng có thể chạy.

Restore vào **database kiểm thử tách biệt**:

~~~bash
createdb \
  --host=restore-db.internal.example \
  --username=restore_operator \
  shop_orders_restore_test

pg_restore \
  --host=restore-db.internal.example \
  --username=restore_operator \
  --dbname=shop_orders_restore_test \
  --no-owner \
  --exit-on-error \
  shop_orders_2026-11-12.dump
~~~

**Lưu ý vận hành:**

- Các lệnh mô tả workflow; hostname, role, quyền, extensions và phiên bản DB phải được cấu hình đúng thực tế.
- Không chạy restore vào database production đang phục vụ nếu chưa có kế hoạch/phê duyệt và cửa sổ vận hành.
- Dữ liệu lớn có thể yêu cầu parallel restore, disk capacity, WAL space, maintenance hoặc tối ưu khác.
- Cần backup/restore **roles, privileges, extensions, ownership, tablespaces, sequences và các cấu hình ngoài một database** khi có yêu cầu; một file pg_dump của một DB không tự chứa mọi đối tượng cấp cluster.
- Dump đọc một snapshot nhất quán theo cơ chế PostgreSQL phù hợp, nhưng không bảo đảm nhất quán với object storage/Kafka/Payment DB tại cùng một business point.
- Dùng kết nối bảo mật, không hardcode password trong command line hoặc log.

Sau restore vẫn phải chạy **schema validation, query nghiệp vụ, integration tests và đối chiếu số lượng/quan hệ dữ liệu**.

## 8. PostgreSQL: Physical backup và Point-in-Time Recovery (PITR)

Đối với database lớn và RPO thấp, một chiến lược thường dùng:

~~~text
PostgreSQL primary
    |
    +--> Physical base backup (hợp lệ)
    |
    +--> WAL archiving / streaming archive
              |
              v
      Offsite protected backup store
              |
              v
Restore base backup + replay WAL to recovery target
              |
              v
Database ở thời điểm T được chọn
~~~

Ví dụ thao tác xóa nhầm xuất hiện lúc **10:22:15**. Nếu có base backup và WAL liên tục đủ để replay tới trước thời điểm đó, có thể lựa chọn recovery target như **10:22:14** theo khả năng engine và độ chính xác timeline. Không giả định mọi sự kiện trong cùng một giây đều tách biệt được bằng mốc thời gian; với recovery thực cần xác định transaction/timeline phù hợp.

Điều kiện cần thiết:

- Base backup hoàn chỉnh, được tạo bằng quy trình PostgreSQL hỗ trợ.
- WAL archives đủ và không có khoảng đứt.
- Ghi nhận system identifier, timeline, phiên bản PostgreSQL và backup metadata tương thích.
- Kho lưu backup độc lập, có tính toàn vẹn, quyền tối thiểu và retention phù hợp.
- Có bản hướng dẫn restore/version pin đã thử nghiệm; không dựa vào các option cũ từ phiên bản PostgreSQL khác.
- Dung lượng disk, CPU, I/O đủ để **restore + replay WAL** trong RTO.
- Khi phục hồi xong, phải kiểm tra dữ liệu và ứng dụng trước khi chuyển traffic.

**PITR không tự bảo đảm RPO bằng 0:** dữ liệu sau WAL cuối cùng lưu an toàn ngoài vùng lỗi có thể mất. Cần đo **WAL archive lag**, tuổi recovery point thực sự và số lần archive thất bại.

## 9. MySQL, SQL Server và hệ quản trị khác

Mỗi DBMS có cơ chế riêng:

- **MySQL/InnoDB:** logical dump phù hợp ở quy mô nhất định; physical backup và binlog có thể phục vụ PITR khi setup đúng. Cần kiểm tra consistency với tables có engine khác, replication, GTID, binary log retention và version compatibility.
- **SQL Server:** full/differential/log backups và recovery model quyết định khả năng phục hồi theo thời điểm; một log chain bị đứt ảnh hưởng mục tiêu restore.
- **MongoDB/NoSQL:** snapshot, oplog/continuous backup hoặc công cụ cloud-native theo đặc tính engine, shard/replica set; cần bảo đảm cluster-wide consistency theo phương thức hỗ trợ.
- **Managed databases:** có automated backup/PITR/snapshot do nhà cung cấp hỗ trợ, nhưng phải kiểm tra cấu hình thật về retention, off-region copy, quyền xóa, restoration endpoint và giới hạn account/region. **Bật managed backup không tự chứng minh khả năng khôi phục**.

Tránh sao chép hướng dẫn file-level restore của engine này sang engine khác. Backup format, point-in-time semantics, phiên bản và restore path đều khác nhau.

## 10. Object storage và tệp đính kèm

Một đơn hàng có thể ghi database row trỏ tới:

~~~text
orders.invoice_object_key = "invoices/2026/11/O1001.pdf"
~~~

Nếu chỉ restore database mà object storage đã mất, Order API có thể trả đúng metadata nhưng **hóa đơn không mở được**.

Kế hoạch backup object storage cần xác định:

- Bucket/prefix nào là source of truth, bucket nào chỉ chứa dữ liệu dẫn xuất.
- Versioning, retention, lifecycle và delete marker.
- Cross-region/account copy khi cần độc lập khỏi sự cố chung.
- Object Lock/immutability/WORM theo hỗ trợ của nhà cung cấp.
- Encryption keys và IAM permissions để đọc bản sao.
- Object metadata, content type, checksum, ACL/policy cần để ứng dụng sử dụng được.
- Cơ chế kiểm kê object count, tổng byte, checksum và missing keys.
- Quy trình restore khi database và object storage ở hai thời điểm khác nhau.

**Object replication không nhất thiết tương đương backup chống xóa nhầm.** Nếu delete cũng được replicate, phải có version history/immutable retention hoặc cơ chế độc lập khác để quay về trạng thái trước sự cố.

Một test tốt không chỉ liệt kê object: hãy restore một tập object, dùng credential của ứng dụng kiểm thử để mở nội dung, kiểm tra checksum và liên kết từ database.

## 11. Kafka và event-driven state

Kafka lưu log sự kiện; có thể dùng retention và replication, nhưng đây không tự động là một bản backup DR hoàn chỉnh cho toàn bộ hệ thống.

Cần xem riêng:

- **Topic data:** partition logs và chính sách retention/compaction.
- **Topic configuration:** partitions, replication factor, ACLs, retention, cleanup policies.
- **Schema contracts:** schema registry, subject/version và compatibility settings nếu dùng.
- **Consumer positions:** offsets/checkpoints và trạng thái business processing.
- **External side effects:** Payment/email/fulfillment đã xảy ra hay chưa.
- **Transactional outbox/inbox:** records gắn với DB và cơ chế replay.
- **Connectors:** configs và offsets riêng nếu dùng Kafka Connect.

Nếu Order DB restore về 10:20 nhưng Kafka còn sự kiện tới 10:40, consumer có thể tái xử lý events không còn khớp. Nếu Kafka restore về mốc cũ hơn DB, một số events có thể được gửi lại hoặc thiếu.

Các biện pháp:

1. Xác định **source of truth** cho mỗi thông tin.
2. Gắn **eventId**, aggregateId và idempotency records.
3. Có reconciliation sau phục hồi để tìm giao dịch/side effect lệch trạng thái.
4. Giữ schema versions đủ lâu để đọc event còn trong retention.
5. Quy định khi nào reset consumer offsets, backfill hoặc re-publish.
6. Không “replay mọi event” lên production mà không biết hậu quả side effect.

**Khả năng replay không thay thế test khôi phục theo hợp đồng nghiệp vụ.**

## 12. Redis/cache: Phân biệt cache và nguồn sự thật

Nếu Redis chỉ cache dữ liệu có thể tái dựng từ PostgreSQL, có thể chọn **không backup toàn bộ cache**, chấp nhận cache miss và warm-up có kiểm soát. Nhưng cần tính tải tăng đột ngột xuống database khi cache trống.

Nếu Redis chứa **session state, rate-limit counters, delayed jobs, locks hoặc dữ liệu nghiệp vụ chưa có nơi lưu khác**, cần xem từng loại có thể mất hay không và cách phục hồi/đồng bộ.

Lưu ý:

- Redis replication không tự bảo vệ khỏi logical deletion.
- RDB/AOF hoặc managed backups có các đặc tính durability/consistency khác nhau.
- Phục hồi session/token state có thể ảnh hưởng đăng nhập, logout, revocation và bảo mật.
- Một lock đã ghi trước thảm họa có thể không còn ý nghĩa sau restore; cần cơ chế lease/fencing token phù hợp.

**Không coi mọi key-value store là “chỉ cache” khi thực tế đang giữ trạng thái độc nhất.**

## 13. Kubernetes: Backup ứng dụng không đồng nghĩa backup cluster

Trong Kubernetes có nhiều tầng state:

~~~text
Git / IaC / Helm / manifests
        |
        v
Cluster control-plane objects
        |
        +--> Deployments, Services, ConfigMaps, RBAC...
        |
        +--> Secrets (bảo vệ riêng)
        |
        +--> PVCs / CSI volumes
        |
        +--> External databases, buckets, brokers
~~~

**Backup etcd** có thể giúp khôi phục control-plane state trong một số mô hình Kubernetes tự quản, nhưng không tự backup dữ liệu nằm trong **PersistentVolumes**, database bên ngoài hoặc object storage. Việc restore etcd là thao tác nhạy cảm, cần runbook phù hợp phiên bản/control plane và có thể gây hậu quả nếu áp vào cluster đang chạy.

Các công cụ kiểu **Velero** có thể backup Kubernetes resources và, với plugin/cơ chế hỗ trợ, backup volumes. **Không tự giả định “đã backup namespace” nghĩa là có toàn bộ bytes của mọi PVC**. Cần xác nhận snapshotter, CSI support, storage class, volumes được bao phủ và các objects nằm ngoài phạm vi.

Một chiến lược có thể kết hợp:

- **IaC/GitOps:** tái dựng cluster/network/IAM, đảm bảo có bản đã được review.
- **Kubernetes manifests:** ứng dụng, service, routing, RBAC, policy và các custom resources cần khôi phục.
- **Persistent storage:** database-aware backups hoặc volume snapshots nhất quán.
- **External services:** DB, broker, buckets có kế hoạch riêng.
- **Secrets/keys:** được provision từ nguồn độc lập có khả năng phục hồi.

RTO phải tính cả **thời gian dựng cluster mới**, cấp networking/certificates, khôi phục data, rollout ứng dụng và xác minh nghiệp vụ.

## 14. Secrets và khóa mã hóa là một phần của DR

Một bản backup đã mã hóa chỉ hữu dụng nếu có thể lấy đúng **decryption key** trong kịch bản thảm họa. Nhưng sao chép key không kiểm soát lại phá mục tiêu bảo mật.

Cần thiết kế:

- Key ownership, policy và danh sách danh tính có quyền decrypt.
- KMS/HSM hoặc key escrow theo yêu cầu tổ chức, có phương án nếu account/region ban đầu mất.
- Encryption-at-rest và encryption-in-transit phù hợp.
- Rotation và cách giải mã bản backup cũ sau khi key mới đã thay thế.
- Quyền backup writer tách khỏi quyền xóa/tắt immutability.
- Quyền restore operator theo **least privilege** và yêu cầu phê duyệt khi truy cập dữ liệu nhạy cảm.
- Không lưu secrets giải mã chung trong cùng thư mục backup hoặc trong CI logs.
- Kiểm thử restore bằng đúng danh tính/permission dùng cho tình huống DR, không chỉ bằng super-admin.

Một lỗi thường gặp là **backup database nằm ở vùng B nhưng khóa KMS chỉ ở vùng A** hoặc recovery account không được phép sử dụng khóa. Đây là vấn đề phải phát hiện trong restore drill, không đợi incident.

## 15. Bảo vệ backup khỏi ransomware và thao tác quản trị nhầm

Một chính sách phổ biến là **3-2-1**, hoặc biến thể **3-2-1-1-0**:

- **3:** có ít nhất ba bản/copy dữ liệu quan trọng, tính cả bản production theo cách định nghĩa.
- **2:** sử dụng từ hai môi trường/phương thức lưu độc lập ở mức phù hợp.
- **1:** có tối thiểu một copy ở vị trí ngoài failure domain chính.
- **1 bổ sung:** có một copy offline hoặc immutable/air-gapped theo threat model.
- **0:** hướng tới không còn lỗi chưa được phát hiện sau các bước verification và restore testing, **không có nghĩa tuyệt đối không thể xảy ra lỗi**.

Quan trọng hơn số đếm là **độc lập thực chất**. Hai bucket ở hai vùng nhưng cùng một credential có quyền xóa mọi version vẫn có failure mode chung. Cũng vậy, snapshot cùng account hoặc cùng control plane có thể cùng bị xóa khi account bị chiếm.

Biện pháp:

1. Backup đến account/project độc lập khi phù hợp.
2. IAM tách **write/append** khỏi **delete/alter retention**.
3. Dùng object immutability/WORM và retention lock có hỗ trợ, cấu hình đúng.
4. Giám sát những thay đổi policy, quyền xóa, lịch sử truy cập và thất bại backup.
5. Bảo vệ backup catalog, manifest, encryption keys và runbook.
6. Thử kịch bản mất quyền truy cập production account và restore bằng DR identity.
7. Có retention hợp lý: tránh mọi bản sao cùng được xóa bởi một cleanup job lỗi.

**Immutability cũng cần được thử nghiệm:** có thực sự không xóa được bản trong cửa sổ bảo vệ bằng tài khoản có quyền vận hành thường ngày không?

## 16. Quy trình tạo backup đáng tin cậy

Một pipeline mẫu:

~~~text
Define dataset + RPO + policy
          |
          v
Authenticate backup workload
          |
          v
Start backup / capture consistent point
          |
          v
Stream/copy to protected destination
          |
          v
Complete required logs/WAL and metadata
          |
          v
Validate integrity, sizes, checksums, catalog
          |
          v
Record immutable manifest + recovery point
          |
          v
Apply retention safely
          |
          v
Schedule restore verification
          |
          v
Alert on lag, gaps, corruption or missing evidence
~~~

Một backup job nên có **ID bất biến** và metadata gắn với source dataset, logical time, schema/software version, storage location, encryption key reference, size, checksum, retention và kết quả verification.

Không đặt trạng thái **COMPLETED** khi chỉ khởi động upload mà chưa xác minh việc ghi thực sự hoàn tất, nhất là với multipart uploads hoặc asynchronous snapshot APIs.

**Không đợi backup thành công mới nghĩ đến restore:** thời gian restore, số dependency và quyền truy cập phải được thiết kế từ đầu.

## 17. Backup manifest là bằng chứng cần thiết

Ví dụ mô tả manifest minh họa:

~~~json
{
  "backupId": "order-prod-2026-11-12T010000Z",
  "service": "order-service",
  "dataset": "orders-postgresql",
  "environment": "production",
  "region": "primary-region",
  "engine": "postgresql",
  "engineMajorVersion": 16,
  "backupType": "physical-base-plus-wal",
  "startedAt": "2026-11-12T01:00:00Z",
  "completedAt": "2026-11-12T01:18:00Z",
  "recoverableThrough": "2026-11-12T01:17:30Z",
  "storageLocation": "protected-offsite-store/example-backup-id",
  "integrityVerified": true,
  "restoreTestReference": "dr-test-2026-11-12-007",
  "encryptionKeyReference": "kms-key-alias-example"
}
~~~

**Tất cả giá trị ở đây chỉ là minh họa.** Một manifest tự khai **integrityVerified=true** không chứng minh gì nếu không gắn với kết quả công cụ kiểm tra, chữ ký/provenance hoặc job logs đáng tin. Đặc biệt **recoverableThrough** phải phản ánh mốc recovery thực sự dựa trên backup/WAL chain, không được tự lấy **completedAt**.

Có thể ghi thêm:

- Số object và tổng bytes.
- Hash/checksum đã xác minh nguồn–đích.
- Backup catalog version.
- Retention expiry và tính bất biến.
- Restore tool/client version đã dùng.
- Dataset snapshot/transaction ID nếu DB cung cấp.
- Kết quả logical checks và application smoke.
- Owner, ticket, runbook version và chi phí.

Manifest giúp trả lời **“bản nào?”, “ở đâu?”, “cần gì?”, “có thể khôi phục tới lúc nào?”, “đã được kiểm chứng chưa?”**.

## 18. Kiểm tra checksum là cần thiết nhưng chưa đủ

Các cấp kiểm tra có giá trị tăng dần:

| Cấp | Kiểm tra | Phát hiện | Chưa chứng minh |
|---|---|---|---|
| **0. Job signal** | Task backup báo success | Bước tạo bản sao không báo lỗi | Dữ liệu đầy đủ/khôi phục được |
| **1. Inventory** | File/object tồn tại, size hợp lý | Missing files, upload thiếu | File có đọc được không |
| **2. Integrity** | Checksums/hashes, backup catalog, format verify | Corruption hoặc mismatch đã kiểm | Giải mã và restore hoàn chỉnh |
| **3. Restore boot** | Dựng DB/volume từ backup trên môi trường cô lập | Backup đọc/khôi phục và DB engine khởi động được | Nghiệp vụ và liên kết liên dịch vụ đúng |
| **4. Data validation** | Constraints, row counts, sample checks, reconciliation | Mất/hỏng data hoặc sai quan hệ có thể quan sát | Toàn bộ API/workflow dùng được |
| **5. Application validation** | Deploy app phiên bản tương thích, smoke/integration | App khởi động, truy vấn và flow quan trọng hoạt động | Mức phục hồi RTO khi quy mô lớn |
| **6. Full DR exercise** | Diễn tập dựng hạ tầng, restore, DNS, traffic switch trong thời gian quy định | Khả năng phục hồi end-to-end và RTO/RPO thực đo | Bảo đảm tuyệt đối mọi sự cố tương lai |

Nếu chỉ chạy **pg_restore --list**, đó là kiểm tra một phần archive format; nó không thay restore drill. Tương tự, checksum trùng nhau có thể chứng minh copy không bị đổi nhưng **một bản backup vốn đã logic-inconsistent vẫn có checksum hợp lệ**.

## 19. Restore vào môi trường cô lập: Luồng chuẩn

Một restore test nên thực hiện với **tài nguyên tách biệt**, không ảnh hưởng production:

~~~text
Choose backup + desired recovery time
                  |
                  v
Provision isolated restore environment
                  |
                  v
Obtain decrypt rights and backup media
                  |
                  v
Restore DB/volumes/object data/log chain
                  |
                  v
Start database, complete recovery/replay
                  |
                  v
Validate schema + constraints + row samples
                  |
                  v
Deploy compatible application version
                  |
                  v
Run synthetic business workflows
                  |
                  v
Record RPO/RTO, evidence, failures
                  |
                  v
Destroy test environment and revoke access
~~~

**Cô lập không chỉ là namespace mới trong cùng cluster** nếu test chứa dữ liệu production nhạy cảm hoặc có nguy cơ gọi external provider thật. Một restored Payment Service vô tình kết nối cổng thanh toán production và gửi lại giao dịch là sự cố nghiêm trọng.

Các điều kiện:

- Network egress hạn chế, có allowlist hoặc fake provider.
- DNS/routes sandbox rõ ràng.
- Credentials riêng cho restore test, không cấp quyền ghi production.
- Mask/anonymize dữ liệu khi chính sách yêu cầu và kỹ thuật cho phép, nhưng phải giữ đặc tính dữ liệu đủ để xác minh.
- Không chạy scheduler/consumer tự động gây side effects trước khi kiểm tra.
- TTL và quy trình xóa sạch môi trường sau thử nghiệm.
- Có bằng chứng read/write permissions theo kịch bản DR thực tế.

## 20. Kiểm chứng ở mức database

Sau khi PostgreSQL restore xong, cần kiểm tra:

1. Database engine startup và recovery logs không báo lỗi nghiêm trọng.
2. Database catalog/schema phiên bản mong đợi.
3. Các extensions, roles, permissions và indexes thiết yếu tồn tại.
4. Primary/foreign key, unique constraints và check constraints theo thiết kế.
5. Các bảng quan trọng có số lượng và dữ liệu trong phạm vi hợp lý.
6. Một số record theo transaction ID/mốc thời gian có thể truy xuất.
7. Chuỗi sequence/identity, partition mappings và dữ liệu thời gian không bị lệch.
8. Query quan trọng có execution plan/latency chấp nhận được.
9. Ứng dụng với role production-like có thể truy cập các đối tượng cần thiết.
10. Không có dấu hiệu backup WAL chain bị thiếu hoặc dừng recovery sai mốc.

Ví dụ SQL kiểm tra invariant **giả định có schema tương ứng**:

~~~sql
-- Paid orders phải có thời gian xác nhận.
SELECT COUNT(*) AS inconsistent_paid_orders
FROM orders
WHERE status = 'PAID'
  AND paid_at IS NULL;

-- Payment success phải có tham chiếu nhà cung cấp.
SELECT COUNT(*) AS missing_provider_reference
FROM payment_transactions
WHERE status = 'SUCCEEDED'
  AND provider_reference IS NULL;

-- Outbox events tham chiếu đơn hàng phải có parent record.
SELECT COUNT(*) AS orphan_outbox_events
FROM outbox_events e
LEFT JOIN orders o ON e.aggregate_id = o.id
WHERE e.aggregate_type = 'ORDER'
  AND o.id IS NULL;
~~~

**Đây là SQL minh họa, không phải migration hay schema chuẩn cho mọi dự án.** Giá trị 0 của các invariant phù hợp chỉ kiểm được một số tính chất; vẫn cần reconcile với external services và dữ liệu gốc nếu có.

Kiểm tra row count tổng cũng có thể đánh lừa: một bản restore mất 100 bản ghi nhưng có 100 bản ghi trùng mới vẫn có row count giống nhau. Nên dùng **sample IDs, checksums theo partition/time range và business invariants**.

## 21. Application smoke test: Dữ liệu dùng được hay chưa?

Không nên kết luận restore thành công chỉ vì DB chấp nhận kết nối TCP. Một smoke suite cần thử các luồng thật nhưng an toàn:

- Đăng nhập/xác thực bằng identity sandbox phù hợp.
- Tìm một đơn theo ID và đọc được item/status/currency.
- Truy vấn một đơn có invoice object; mở được file và checksum hợp lệ.
- Tính tổng đơn, tax/discount theo quy tắc version đã phục hồi.
- Đọc một Payment record và provider reference; **không tự khởi tạo giao dịch thanh toán thật**.
- Inventory reconciliation với reservations và stock.
- Đọc event/outbox chưa gửi và xác định consumer resume position.
- Gửi một **synthetic message** đến broker sandbox và xác nhận handler idempotent.
- Kiểm tra API permissions, row ownership và tenant isolation.
- Kiểm tra response codes, latency cơ bản và không lộ secret/log nhạy cảm.

Dùng dataset/transaction markers đã được chuẩn bị trước để biết một số record phải có ở recovery point. Ví dụ mỗi giờ ghi một marker có timestamp, rồi đo từ marker cuối khôi phục được tới sự cố để đánh giá RPO.

Một API trả **HTTP 200** chưa đủ: nó có thể dùng cache cũ, gọi nhầm database hoặc thiếu quyền ghi. Cần kiểm tra cả **read**, **controlled write**, **rollback/cleanup** và dependency wiring theo policy.

## 22. Nhất quán sau khi phục hồi nhiều microservices

Trong saga hoặc event-driven flow, cùng một nghiệp vụ trải qua nhiều nguồn:

~~~text
Order DB                  Payment DB                 External provider
---------                 ----------                 -----------------
Order O1001 CREATED
                          Payment P901 STARTED
                                                     Charge AUTHORIZED
Order O1001 PAID
                          Payment P901 SUCCEEDED
~~~

Nếu Order DB restore đến 10:00, Payment DB đến 10:05 và provider giữ mọi giao dịch đến 10:15, một số bản ghi có thể lệch. Không dùng quy tắc “database nào cũng restore về 10:05 thì mọi thứ hợp lệ” nếu timestamps/transactions của các hệ thống khác nhau.

Cần **reconciliation** có kiểm soát:

1. Tạm dừng các consumer/worker có side effect không an toàn.
2. Xác định recovery point của từng dataset và data gaps.
3. Liệt kê nghiệp vụ trong khoảng rủi ro theo ID và thời gian.
4. Đối chiếu trạng thái bên ngoài dựa trên **provider transaction/reference IDs**.
5. Dùng idempotent commands để bù/hoàn tất các bước bị thiếu.
6. Không tự động gửi lại Payment authorize khi không biết kết quả trước đó.
7. Đối chiếu outbox/inbox, Kafka offsets, DLQ và duplicate suppression.
8. Ghi audit về dữ liệu đã sửa và người phê duyệt.

**Reconciliation khác replay mù.** Một sự kiện bị mất có thể cần phát lại, nhưng cùng một side effect thanh toán hoặc gửi email không nên được thực hiện trùng chỉ vì consumer offset bị khôi phục về quá khứ.

## 23. Xác minh tính tương thích với binary, schema và config

Restore một database năm trước vào phiên bản app hôm nay có thể thất bại vì đã có nhiều migration.

Cần lưu hoặc truy ra:

- Phiên bản DB engine/major và tool restore tương thích.
- Schema/migration version của backup.
- Application image digest được kiểm chứng phù hợp với schema đó.
- API/event contract versions liên quan.
- Các feature flags và cấu hình bắt buộc ở thời điểm phục hồi.
- Tài liệu nâng schema **theo từng bước** từ restore point đến release hiện hành.
- Secrets/keys và certificate chain cần thiết cho version tương ứng.
- Rollback/roll-forward strategy nếu thay đổi schema phá tương thích.

Ví dụ:

~~~text
Backup schema: v26
Current app requires schema: v31

Restore backup v26
   |
   +--> Deploy app tương thích v26 để kiểm tra khả năng dùng dữ liệu
   |
   +--> Apply migration v27..v31 trong môi trường thử nghiệm
   |
   +--> Validate data invariants & smoke app v31
~~~

Không tự chạy **Flyway repair**, **drop table** hoặc migration phá dữ liệu chỉ để vượt lỗi version. Mỗi migration cần kiểm tra dữ liệu thực tế và có chiến lược dừng/khôi phục khi lỗi.

Một **schema dump** hoặc Git manifest không đủ nếu artifact binary/dependencies đã bị xóa khỏi registry. Hệ thống DR cần **khả năng lấy lại artifact đã ký và dependency quan trọng**.

## 24. Phục hồi vùng/cluster mới: Hạ tầng là một phần RTO

Một DR runbook thường đi theo dependency order:

~~~text
1. Incident declaration + chọn recovery strategy
2. Xác nhận recovery target và nguồn backup tin cậy
3. Provision mạng, IAM, DNS, cluster/capacity ở DR region
4. Provision storage, DB engine, broker, object buckets
5. Khôi phục base backup + logs + objects
6. Khôi phục encryption keys/Secrets/config theo quyền
7. Deploy app images và hợp đồng compatible
8. Restore/điều chỉnh event consumers/offsets
9. Validate consistency, security, business workflows
10. Controlled traffic cutover
11. Monitor + reconcile data gap
12. Ghi lại RPO/RTO, quyết định và bằng chứng
~~~

Đây là ví dụ thứ tự. Một số bước có thể làm song song nếu không phá dependency; nhưng phải rõ **critical path** quyết định RTO. Ví dụ DB restore 40 phút, cluster provision 50 phút và Smoke 20 phút không nhất thiết cộng thành 110 phút nếu các bước độc lập được chạy song song.

Những phụ thuộc thường bị bỏ quên:

- Khả năng đăng nhập vào cloud/IAM khi SSO chính lỗi.
- DNS zone delegation và TTL đang cache ở client.
- Certificate issuance và secret decryption.
- Container registry và Helm chart version.
- Network routes/firewall/allowlist của Payment provider.
- Kafka topic configs, consumer group offsets.
- Email/SMS/webhook endpoints phải **disable** trước khi có chủ đích bật lại.
- Quota/capacity ở DR region, đặc biệt lúc nhiều tổ chức cùng failover.
- Observability khi monitoring stack chính cũng bị mất.

**RTO thực đo phải tính đến các bước phụ thuộc này**, không chỉ thời gian copy database.

## 25. Tính thời gian phục hồi thay vì chỉ nhìn kích thước backup

Khôi phục 2 TB dữ liệu có thể mất hàng giờ tùy tốc độ mạng, đọc/ghi storage, CPU và replay logs. Ước lượng thô:

~~~text
transfer_time ≈ data_bytes / effective_throughput_bytes_per_second

restore_time ≈ transfer
             + decrypt/decompress
             + database recovery/WAL replay
             + index/validation/application boot
             + cutover
~~~

Không cộng máy móc tất cả thời gian nếu có xử lý song song. **Effective throughput** thường thấp hơn băng thông danh nghĩa và có thể bị giới hạn bởi API quotas, storage IOPS hoặc công cụ restore.

Ví dụ 1 TB dữ liệu với throughput hữu hiệu 200 MB/s:

~~~text
1.000.000 MB / 200 MB/s ≈ 5.000 giây ≈ 83 phút
~~~

Đây chỉ là thời gian chuyển byte lý thuyết theo đơn vị thập phân. **Chưa gồm decompression, restore engine, WAL replay, validation hoặc cutover**; RTO 30 phút rõ ràng không thể đạt nếu quy trình bắt buộc phải tải toàn bộ 1 TB qua đường truyền đó.

Cần cân nhắc:

- Backup incremental và PITR restore chain.
- Snapshot/replica đã provision ở DR region.
- Restore song song khi engine/storage hỗ trợ.
- Dữ liệu cold/archive không cần phục vụ ngay.
- Khôi phục **minimum viable service** trước full historical reports.
- Provision sẵn hạ tầng cần thiết nếu yêu cầu RTO thấp.

**Không đánh đổi tính nhất quán dữ liệu lấy tốc độ một cách âm thầm.** Phân biệt rõ degraded service được phép với dữ liệu bắt buộc phải chính xác.

## 26. Quy tắc retention và vòng đời dữ liệu

Retention phải cân bằng:

- RPO và khả năng PITR: cần giữ base backups cùng WAL/log chain tương ứng.
- Khả năng quay lại trước lỗi logic phát hiện trễ nhiều ngày.
- Yêu cầu kiểm toán/pháp lý.
- Chi phí và thời gian restore.
- Rủi ro backup chứa dữ liệu cá nhân sau khi dữ liệu gốc đã bị xóa.
- Immutability và khả năng thay đổi retention theo quy trình được phê duyệt.
- Backups được tạo bằng schema/engine cũ có thể khó restore về sau.

Ví dụ chính sách **minh họa**:

| Loại | Retention ví dụ | Mục đích |
|---|---|---|
| Database base backups | Hằng ngày, giữ 14–30 ngày | Phục hồi lỗi gần |
| Continuous WAL/binlog | Giữ đầy đủ cho cửa sổ PITR mục tiêu | RPO thấp, khôi phục mốc |
| Weekly/monthly restore points | Theo chính sách pháp lý/nghiệp vụ | Phát hiện lỗi muộn |
| Immutable offsite copies | Khoảng đủ dài theo threat model | Chống xóa nhầm/ransomware |
| Audit records | Theo chính sách lưu trữ riêng | Kiểm toán/forensic |

Không áp con số trên nếu tổ chức có nghĩa vụ khác. **Retention không được làm đứt backup dependency chain**: xóa một base backup nhưng giữ WAL không đủ, hoặc ngược lại, có thể khiến một khoảng thời gian không thể phục hồi.

Khi có yêu cầu xóa dữ liệu cá nhân, cần xác định cách áp dụng trong backup lifecycle và restore: dữ liệu đã bị xóa trong production có thể xuất hiện lại khi khôi phục bản cũ. Cần chính sách re-apply deletion/tombstone và kiểm soát truy cập theo luật/chính sách phù hợp.

## 27. Tần suất backup phải xuất phát từ RPO đo được

Nếu chỉ có full backup mỗi 24 giờ thì, trong trường hợp mất toàn bộ dữ liệu kể từ bản gần nhất, **RPO thực tế có thể gần 24 giờ**, không phải “RPO 0 vì database có replication”.

Nếu có WAL archiving mỗi vài phút, cần đo:

- WAL archive success/failure.
- Last safely archived WAL location/time.
- Số phút giữa hiện tại và **recoverable-through** thực sự.
- WAL archive gaps và base backup compatibility.
- Log transport delay, queue backlog, bandwidth.
- Sự khác biệt giữa ack replication và durability ở nơi sống sót sau thảm họa.

**Đừng chỉ đo “backup job hôm nay thành công chưa?”.** RPO phụ thuộc điểm phục hồi gần nhất còn tồn tại và dùng được.

Một dashboard nên phản ánh **recovery-point age per dataset**. Có thể thiết lập alert khi vượt một phần ngân sách RPO để sửa sớm trước khi cửa sổ mất dữ liệu chạm ngưỡng.

## 28. Giám sát chính hệ thống backup

Những metrics hữu ích:

~~~text
backup_last_success_timestamp_seconds{dataset,environment}
backup_duration_seconds{dataset,type}
backup_bytes_written_total{dataset,type}
backup_failed_total{dataset,reason}
backup_recovery_point_age_seconds{dataset}
backup_integrity_check_failed_total{dataset}
backup_wal_archive_lag_seconds{dataset}
backup_restore_test_last_success_timestamp_seconds{dataset}
backup_restore_duration_seconds{dataset}
backup_restore_validation_failures_total{dataset,check_type}
backup_retention_expiry_risk{dataset}
~~~

Tên trên **là ví dụ instrumentation**, không khẳng định có sẵn trong mọi backup tool.

Cần xem thêm:

- Số restore tests đã chạy và tỉ lệ pass.
- Backup có bao nhiêu phiên bản khả dụng và thuộc failure domain nào.
- Object count/bytes, chi phí lưu trữ và API operations.
- Số lần mất kết nối nơi lưu backup.
- Backup encryption/decryption failures.
- Thay đổi IAM/KMS/retention và mọi nỗ lực xóa trái policy.
- Restore drill RPO/RTO thực đo so với mục tiêu.
- Số lượng **untested backups** và tuổi lần restore drill gần nhất.

Alert khi **backup missing, PITR chain gap, object checksum lỗi, restore test fail, key không giải mã được hoặc recovery-point age vượt ngưỡng**. Một dashboard xanh về upload không đủ nếu restore tests đã fail trong nhiều tuần.

## 29. Lập lịch restore drill và bằng chứng

Một chính sách kiểm thử có thể chia cấp:

| Cấp thử nghiệm | Chu kỳ minh họa | Đích |
|---|---|---|
| **Integrity validation** | Sau mỗi backup hoặc theo job | Checksum, catalog, đủ các phần |
| **Automated restore smoke** | Hằng ngày/hằng tuần theo chi phí và risk | Restore DB sandbox, query các invariant |
| **Application restore exercise** | Hằng tuần/hằng tháng | Dựng app và chạy synthetic flows |
| **Full DR rehearsal** | Hằng quý/nửa năm hoặc theo criticality | Khôi phục nhiều service, DNS/cutover, RPO/RTO |
| **Surprise drill/game day** | Theo chương trình resilience | Kiểm tra người trực, playbook, quyền và dependency |

Đây là **lịch minh họa**, không phải tần suất bắt buộc. Hệ thống tài chính trọng yếu có thể cần kiểm tra thường xuyên hơn; hệ không quan trọng có thể dùng lịch khác dựa vào tác động nghiệp vụ.

Mỗi drill nên xuất **evidence package**:

~~~text
DR Exercise ID: dr-2026-11-12-01
Dataset / service: order-service / shop_orders
Backup ID: order-prod-...
Restore target: isolated recovery environment
Target recovery point: timestamp/LSN...
Actual recoverable point: timestamp/LSN...
Target RPO / actual data loss window: ...
Target RTO / actual elapsed time: ...
Schema, invariant, app smoke: pass/fail + evidence
Object references / event reconciliation: pass/fail
Known limitations / remediation owner / due date: ...
~~~

Không ghi **“PASS” chỉ vì runbook đã được đọc hoặc backup archive mở được**. Pass phải có định nghĩa của cấp test và evidence tương ứng.

## 30. Kịch bản thử lỗi thường dễ bị bỏ quên

| Sự cố giả lập | Câu hỏi phải trả lời |
|---|---|
| Full backup thiếu một phần | Integrity/canary restore có phát hiện không? |
| WAL archive thiếu 15 phút | Dashboard nhận ra recovery-point age/gap không? |
| Key KMS ở region chính không dùng được | Recovery account có giải mã từ nơi độc lập không? |
| Storage bucket bị xóa nhầm | Có immutable/offsite copy thực sự độc lập không? |
| Ransomware xóa snapshots theo role chính | Backup writer có quyền delete quá rộng không? |
| PostgreSQL restore trên version sai | Runbook có tương thích tool/engine không? |
| DB restore nhưng object files thiếu | App smoke và reference validation có phát hiện không? |
| Order/Payment ở hai mốc khác nhau | Reconciliation có ngăn charge lặp không? |
| Kafka offset trở về quá khứ | Consumers có idempotent và replay plan không? |
| Database credentials cũ đã rotate | Secrets DR có cho phép app mới kết nối không? |
| App binary chỉ hỗ trợ schema mới | Có compatible artifact và migration path không? |
| DNS/Ingress/certificates chưa provision | RTO tính cả cutover và external reachability không? |
| Backup cả cụm Kubernetes nhưng thiếu PVC | Restore tool có báo scope gap không? |
| Object store replication copy cả delete | Có object versions/immutability ngoài replication không? |
| Recovery test vô tình gọi payment thật | Egress isolation có chặn được không? |
| Restore rất chậm dưới production-size | Đã đo băng thông/IOPS và thời gian replay chưa? |
| Nhân viên vận hành chính không có mặt | Runbook và quyền khẩn cấp có đủ để người khác thực hiện không? |
| API trả 200 nhưng dữ liệu sai | Có business invariants và synthetic workflows không? |

Cần mô phỏng **mất một node**, **mất region**, **mất account/credential**, **xóa logic**, **corruption âm thầm**, **ransomware** và **phục hồi từ bản rất cũ**; mỗi trường hợp kiểm tra một failure domain khác nhau.

## 31. Chọn chiến lược DR theo loại thảm họa

Không có một phương án cho mọi incident:

### Node/Pod failure

Thường dùng HA/replication, orchestrator restart hoặc failover tự động. Backup chỉ là lớp phòng vệ nếu dữ liệu cũng hỏng.

### Region outage

Cần môi trường khác vùng, bản sao dữ liệu, DNS/routing, identity, quota và kiểm chứng traffic switch. Nếu RTO rất thấp, có thể cần warm standby thay vì cold restore.

### Xóa nhầm dữ liệu hoặc migration lỗi

Cần **PITR/backup version trước thời điểm sai**, rồi reconcile các sự kiện hợp lệ xảy ra sau thời điểm đó. Không chỉ failover sang replica vốn đã nhận cùng thay đổi lỗi.

### Ransomware/account compromise

Cần bản backup **immutable/offline hoặc ở security boundary độc lập**, kiểm tra sạch/malware before restoration, rotate credentials và dựng lại trusted environment. Không restore vội hệ thống chưa xử lý nguồn bị xâm nhập.

### Corruption âm thầm nhiều ngày

Cần retention dài hơn thời gian phát hiện, kiểm tra checksum/business invariants, data lineage và chọn restore point sạch. Nếu mọi bản sao trong retention đều chứa corruption, phải có phương án rebuild/reconcile từ nguồn độc lập.

**Chọn theo threat model và mục tiêu nghiệp vụ**, không đơn giản chọn backup tool quen thuộc.

## 32. Warm standby, cold standby và trade-off chi phí

| Phương án | Mô tả | RTO tiềm năng | Chi phí/độ phức tạp |
|---|---|---|---|
| **Cold recovery** | Chỉ giữ backup và IaC, dựng môi trường khi cần | Dài, phụ thuộc restore/provision | Chi phí idle thấp hơn |
| **Warm standby** | Có hạ tầng tối thiểu, dữ liệu/replica cập nhật, có thể scale khi sự cố | Thường ngắn hơn cold | Chi phí chạy nền, cần kiểm tra lag |
| **Hot/active-passive** | Hệ dự phòng khá sẵn sàng, failover theo thiết kế | Có thể ngắn | Chi phí và orchestration lớn |
| **Active-active** | Nhiều vùng cùng phục vụ | Có thể giảm outage ở một vùng | Conflict resolution, consistency và dữ liệu phân tán rất phức tạp |

Không có bảo đảm “warm standby = RTO 5 phút” nếu traffic cutover, cache warm-up hoặc data reconciliation chưa được thử. Tương tự, active-active không tự giải quyết lỗi xóa nhầm được nhân rộng giữa các vùng.

**RPO và RTO phải được đo từ drill gần với sự cố mục tiêu**.

## 33. Runbook tối thiểu cho một sự cố phục hồi

Một runbook thực tế nên có:

1. **Trigger và severity:** tiêu chí khi nào tuyên bố DR, khi nào chỉ failover HA.
2. **Incident commander:** người quyết định recovery point, cutover và chấp nhận data loss.
3. **Data owners:** ai xác nhận Order, Payment, Inventory và object storage.
4. **Access:** nơi lấy quyền DR, KMS, backup catalog và môi trường độc lập.
5. **Backup selection:** cách chọn bản backup sạch, đủ WAL/chain và đúng dataset.
6. **Provision:** script/IaC version và thứ tự dựng network, DB, brokers, apps.
7. **Restore commands:** các bước version-specific được thử nghiệm; có checkpoint và cơ chế abort.
8. **Isolation:** đảm bảo không gửi side effects ngoài ý muốn khi kiểm thử.
9. **Validation:** dữ liệu, schema, API, security, consistency, RPO/RTO evidence.
10. **Cutover:** DNS/LB/Gateway, write freeze, old primary fencing, điều kiện mở traffic.
11. **Reconciliation:** xử lý data gaps, duplicate events, external transactions.
12. **Rollback/failback:** cách quay về khi DR site lỗi và cách quay về primary an toàn.
13. **Communications:** cập nhật cho business, support, đối tác, khách hàng theo policy.
14. **Postmortem:** đo thực tế, xác định gap và cập nhật backup/restore strategy.

**Old primary fencing** rất quan trọng: nếu hai site cùng nhận ghi vào cùng dữ liệu khi chưa có thiết kế active-active, có thể gây split-brain. Không chỉ đổi DNS rồi bỏ qua primary cũ đang hồi phục.

Cần giữ runbook **có thể truy cập khi hệ thống nội bộ chính mất** (bản bảo vệ độc lập), nhưng không để credential nhạy cảm plaintext trong tài liệu.

## 34. Ví dụ: Database restore thành công nhưng dữ liệu nghiệp vụ chưa an toàn

Một kịch bản:

~~~text
09:55  Payment Provider nhận authorization cho ORDER-900
09:56  Payment DB ghi status=SUCCEEDED
09:57  Order DB ghi status=PAID
10:00  Sự cố mất region

Khôi phục:
  Order DB:   tới 09:54
  Payment DB: tới 09:58
  Provider:   giữ trạng thái 09:55
~~~

Sau restore, Order có thể không còn ORDER-900 hoặc ghi trạng thái cũ, nhưng Payment/provider vẫn đã thực hiện charge. Một quy trình sai là cho user retry checkout và tạo charge lần nữa.

Quy trình đúng phải dựa trên **business IDs, provider references và idempotency**:

1. Xác định các payment records mới hơn Order recovery point.
2. Tra provider theo reference/idempotency key với quyền và rate limit hợp lệ.
3. Tạo lệnh reconcile hoặc sửa trạng thái theo domain invariant được phê duyệt.
4. Không tự động gửi lại authorization nếu kết quả lần đầu chưa được đối chiếu.
5. Ghi audit về điều chỉnh, thời điểm và căn cứ.
6. Khi trạng thái nhất quán, mới mở lại flow cần thiết.

Đây là lý do **“có thể query được database” không tương đương “hệ thống đã có thể nhận thanh toán an toàn”**.

## 35. Anti-pattern cần tránh

**1. Chỉ theo dõi backup job success.** Không đo recoverable-through, integrity, restore pass hoặc recovery time.

**2. Dùng replication thay backup.** Xóa nhầm/corruption có thể được replicate ngay.

**3. Backup database nhưng quên object storage, schema registry, keys và config.** App không chạy được hoặc dữ liệu bị thiếu.

**4. File copy DB đang chạy mà không có cơ chế consistency của engine.** Có thể tạo backup không thể phục hồi.

**5. Chỉ xem checksum/list archive, không restore thử.** Không chứng minh DB, ứng dụng và business flows dùng được.

**6. Chỉ thử restore trên máy dev nhỏ.** Không đo RTO khi khôi phục hàng TB và replay logs.

**7. Giữ backup cùng quyền xóa của tài khoản production.** Một sự cố tài khoản phá cả data và backup.

**8. Mã hóa backup nhưng không có DR key access.** Bản backup còn nhưng không giải mã được.

**9. Tự xóa backup dựa tuổi file không tính dependency chain.** Có thể đứt WAL/incremental chain.

**10. Khôi phục trực tiếp vào production trước khi xác minh.** Có thể ghi đè dữ liệu còn tốt hoặc kích hoạt side effects.

**11. Bật Kafka consumers ngay sau restore mà không hiểu offsets.** Replay tạo duplicate hoặc bỏ sót nghiệp vụ.

**12. Restore Order và Payment vào mốc khác nhau nhưng bỏ qua reconciliation.** Gây lệch ledger và đơn.

**13. Giả định Kubernetes namespace backup là backup toàn bộ PVC.** Cần xác minh volume/data scope.

**14. Chỉ thử API health=200.** Không kiểm tra quyền, đọc/ghi, object references hoặc business invariants.

**15. Không giữ artifact và toolchain version cũ.** Data restore thành công nhưng không thể chạy binary tương thích.

**16. Không tính DNS/IAM/cluster bootstrap vào RTO.** Báo cáo thời gian phục hồi thấp hơn thực tế.

**17. Không có ownership hay phê duyệt recovery point.** Lựa chọn mất dữ liệu trở thành quyết định kỹ thuật tự phát.

**18. Thử DR nhưng không ghi bằng chứng và remediation.** Sai sót lặp lại dù đã diễn tập nhiều lần.

## 36. Checklist thiết kế trước production

1. **Nguồn sự thật của mỗi service là gì?** Database, object store, external provider, broker hay dữ liệu dẫn xuất?
2. **RPO/RTO được business owner ký chấp thuận theo từng luồng chưa?** Có tiêu chí “đã phục hồi” rõ không?
3. **Backup có nhất quán theo DB engine không?** Có PITR/log chains khi RPO yêu cầu?
4. **Có backup tất cả thành phần cần thiết không?** DB, object files, schema, configs, secrets, keys, artifact registry.
5. **Bản sao có độc lập khỏi primary failure/security domain không?**
6. **Có immutability/offsite copy và quyền xóa tách biệt không?**
7. **Có kiểm tra checksum, completeness và backup catalog sau mỗi job không?**
8. **Có đo recovery-point age thực tế, không chỉ backup completion không?**
9. **Có runbook restore versioned, quyền khẩn cấp và key availability không?**
10. **Có tự động restore định kỳ vào môi trường an toàn không?**
11. **Restore test có kiểm tra dữ liệu, schema, app và business invariants không?**
12. **Có đối chiếu data cross-service sau PITR không?**
13. **Kafka offsets/events, retries và side effects có an toàn khi replay không?**
14. **Có kế hoạch compatibility/migrations khi backup cũ hơn binary đang chạy không?**
15. **Đã đo thời gian restore với data volume gần production chưa?**
16. **Có xử lý old primary fencing, DNS/LB cutover và split-brain risk không?**
17. **Có quan sát và cảnh báo khi backup/restore tests fail không?**
18. **Retention có đủ cho phát hiện corruption trễ và yêu cầu pháp lý không?**
19. **Restore có thể thực hiện khi region/account/SSO chính mất không?**
20. **Kết quả diễn tập có owner, evidence, remediation và thời hạn khắc phục không?**

## 37. Tóm tắt

**Sao lưu là một bước trong khả năng phục hồi, không phải bằng chứng khả năng phục hồi.**

Một kiến trúc DR đáng tin cần đồng thời có:

- **Backup đầy đủ và nhất quán:** biết chính xác nguồn dữ liệu, loại backup, recovery point và các dependency.
- **Bảo vệ bản sao:** tách failure domain, phân quyền, mã hóa, immutability và khả năng truy cập khi primary bị mất.
- **Restore có thể lặp lại:** runbook, công cụ, compatible binaries/schema, keys và hạ tầng được chuẩn bị.
- **Validation nhiều lớp:** integrity → database restore → dữ liệu/nghiệp vụ → ứng dụng → full DR drill.
- **Kiểm chứng RPO/RTO:** thực đo data loss window và thời gian phục hồi trong những kịch bản có ý nghĩa.
- **Reconciliation xuyên dịch vụ:** xử lý dữ liệu lệch mốc, sự kiện trùng và side effects bên ngoài.
- **Học từ drill:** giám sát, bằng chứng, ownership và sửa những khoảng trống đã phát hiện.

**Câu hỏi cốt lõi:** *Nếu cả region chính mất trong lúc một số giao dịch thanh toán đang xử lý, đội ngũ sẽ khôi phục Order, Payment, Kafka và tệp hóa đơn từ những bản nào, làm sao chứng minh dữ liệu không bị thiếu hoặc ghi trùng, và có hoàn tất trước RTO/RPO đã cam kết không?*

Chỉ khi có **một lần phục hồi thành công được kiểm chứng với dữ liệu và môi trường đại diện**, tổ chức mới có bằng chứng mạnh hơn lời khẳng định “backup của chúng ta vẫn chạy hằng ngày”.
