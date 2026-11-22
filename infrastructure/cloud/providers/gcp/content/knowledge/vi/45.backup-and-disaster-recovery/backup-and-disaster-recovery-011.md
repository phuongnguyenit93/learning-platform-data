# Kiểm chứng bản sao lưu và diễn tập phục hồi định kỳ

Một hệ thống có lịch sao lưu chạy hằng ngày chưa chắc đã có khả năng phục hồi khi xảy ra sự cố. Bản sao lưu có thể bị thiếu dữ liệu, không nhất quán với giao dịch, không còn quyền giải mã, lưu cùng vùng lỗi với hệ thống chính hoặc không thể khôi phục trong thời hạn nghiệp vụ yêu cầu. Ngay cả khi dữ liệu khôi phục thành công, ứng dụng vẫn có thể ngừng hoạt động vì thiếu secret, cấu hình mạng, schema, artifact hoặc quyền IAM.

**Kiểm chứng backup** là quá trình xác nhận bản sao có thể đọc được, đủ dữ liệu, nhất quán và sử dụng được để khôi phục. **Diễn tập phục hồi định kỳ** là thực hành chạy quy trình khôi phục trong môi trường được kiểm soát, đo thời gian, độ mất dữ liệu và hành vi của ứng dụng khi quay lại phục vụ. Kết quả phải là bằng chứng có thể kiểm tra, không chỉ là trạng thái SUCCESS của một job tạo backup.

Bài học thuộc chương **Sao lưu và phục hồi thảm họa** của module **CLOUD_PROVIDERS_GCP**. Module giúp người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Ở đây, chúng ta áp dụng các kiến thức đó để thiết kế bài kiểm tra và diễn tập phục hồi cho ứng dụng Java/Spring cùng các dịch vụ dữ liệu Google Cloud.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt backup, snapshot, replication, high availability và disaster recovery.
- Dùng RPO và RTO để xác định các bài kiểm chứng phải thực hiện.
- Thiết kế bài kiểm tra ở các mức: tồn tại, toàn vẹn, khôi phục dữ liệu, phục hồi ứng dụng và phục hồi nghiệp vụ.
- Xây dựng bộ tiêu chí kiểm tra sau restore: số lượng, checksum, transaction, schema, chức năng và quyền.
- Chọn cách kiểm chứng phù hợp cho Cloud SQL, Compute Engine, Cloud Storage, Firestore, Spanner, BigQuery và GKE.
- Tổ chức diễn tập khôi phục vào môi trường cô lập, tránh tác động production.
- Tự động hóa lịch chạy, lưu bằng chứng, theo dõi chi phí và dọn tài nguyên sau diễn tập.
- Viết runbook, đo RTO/RPO thực tế và chuyển kết quả diễn tập thành action items.

## 1. Backup thành công không có nghĩa restore thành công

Hãy phân biệt một số cơ chế thường gặp:

| Cơ chế | Mục tiêu chính | Điều không tự bảo đảm |
|---|---|---|
| Backup | Lưu bản sao dữ liệu để phục hồi tại một thời điểm | Có thể restore trong thời hạn yêu cầu |
| Snapshot | Ghi lại trạng thái tài nguyên tại một điểm thời gian theo khả năng dịch vụ | Tính nhất quán của mọi ứng dụng/phụ thuộc |
| Replication | Duy trì bản sao liên tục hoặc gần liên tục | Khôi phục được sau xóa nhầm hoặc ghi sai dữ liệu |
| High availability (HA) | Giảm thời gian ngừng khi thành phần hỏng | Lấy lại bản ghi bị xóa do lỗi logic |
| Disaster recovery (DR) | Khôi phục dịch vụ/nghiệp vụ sau tình huống nghiêm trọng | Thành công nếu chưa có runbook và diễn tập |
| Point-in-time recovery (PITR) | Trở về một mốc trong cửa sổ phục hồi được hỗ trợ | Cứu dữ liệu ngoài cửa sổ retention hoặc không có log phù hợp |

Ví dụ, replica database thường nhận cả một lệnh DELETE sai. Failover sang replica có thể giúp chịu lỗi host nhưng không khôi phục bản ghi đã bị xóa. Cần backup, PITR hoặc một cơ chế bảo vệ dữ liệu phù hợp.

Một bản snapshot disk có thể được tạo thành công nhưng ứng dụng đang ghi nhiều file và transaction cùng lúc. Nếu dịch vụ không cung cấp bảo đảm application-consistent snapshot, bạn cần phối hợp ứng dụng hoặc database để bảo đảm trạng thái có thể phục hồi; đừng giả định mọi snapshot luôn nhất quán ở mức nghiệp vụ.

### Ba câu hỏi trước khi tin tưởng một bản backup

1. **Có gì được bảo vệ?** Dữ liệu nào, cấu hình nào, phiên bản schema nào và những dependency nào?
2. **Có thể phục hồi bằng cách nào?** Restore vào đâu, cần quyền gì, có cần key/secret, thời gian và thao tác thủ công?
3. **Làm sao chứng minh đã phục hồi đúng?** Kiểm tra dữ liệu, chức năng, tính toàn vẹn, thời hạn và giám sát bằng bằng chứng gì?

## 2. RTO, RPO, phạm vi phục hồi và tiêu chí chấp nhận

### Recovery Point Objective (RPO)

**RPO** là lượng dữ liệu tối đa được phép mất trong sự cố, thường đo bằng khoảng thời gian kể từ điểm dữ liệu nhất quán cuối cùng có thể khôi phục. RPO 15 phút không có nghĩa cứ 15 phút chụp snapshot thì hệ thống chắc chắn đạt RPO: còn phụ thuộc thời điểm backup hoàn tất, transaction logs, lỗi replication và thời gian phát hiện vấn đề.

### Recovery Time Objective (RTO)

**RTO** là khoảng thời gian tối đa để phục hồi dịch vụ/nghiệp vụ đến trạng thái được thống nhất. RTO không chỉ gồm thời gian tải backup:

~~~text
Recovery elapsed time
  = detect and declare
  + authorize the recovery path
  + provision target infrastructure
  + restore data and configuration
  + validate consistency and application behavior
  + switch traffic and confirm service
~~~

Ví dụ, restore Cloud SQL mất 12 phút nhưng cần thêm 25 phút dựng mạng, 15 phút cập nhật secret và 10 phút smoke test thì không thể báo RTO là 12 phút.

### Bảng mục tiêu minh họa

| Workload | RPO mục tiêu | RTO mục tiêu | Bài diễn tập cần chứng minh |
|---|---:|---:|---|
| Orders DB | 15 phút | 60 phút | Restore DB + API tạo/đọc đơn hàng |
| Báo cáo cuối ngày | 24 giờ | 8 giờ | Restore input dataset và chạy lại job |
| Cấu hình ứng dụng | Bản phát hành đã được phê duyệt | 30 phút | Tái dựng service từ IaC và artifact |
| Object upload | 1 giờ | 4 giờ | Lấy lại phiên bản object và kiểm tra checksum |

Đây chỉ là ví dụ, không phải SLA hay giới hạn mặc định của Google Cloud. Với hệ thống thực, RPO/RTO cần do owner nghiệp vụ chấp nhận dựa trên tác động tài chính, dữ liệu và khách hàng.

### Ranh giới đo lường

Trước khi diễn tập, thống nhất:

- **T0:** thời điểm sự cố bắt đầu, được mô phỏng hoặc xác nhận.
- **T_detect:** thời điểm alert/nhóm trực phát hiện và ghi nhận.
- **T_recovery_start:** thời điểm cho phép thực hiện khôi phục.
- **T_data_ready:** dữ liệu đã restore và kiểm tra nhất quán.
- **T_service_ready:** luồng nghiệp vụ trọng yếu hoạt động qua endpoint phù hợp.
- **T_close:** thời điểm quyết định đóng diễn tập, dọn resource và hoàn thành báo cáo.

Mốc RTO thường nên tính đến T_service_ready theo định nghĩa SLO/DR của tổ chức, không tính đến lúc một lệnh restore trả về OK. Phải lưu từng mốc theo UTC và giải thích rõ khi thời gian sự cố là mô phỏng.

## 3. Năm mức kiểm chứng bản sao lưu

Một chiến lược tốt tăng dần độ tin cậy bằng các mức kiểm chứng:

| Mức | Kiểm tra | Bằng chứng | Điều chưa chứng minh |
|---|---|---|---|
| 1. Inventory | Backup có tồn tại và nằm trong retention | Backup ID, timestamp, size/status | Restore hoạt động |
| 2. Integrity | Dữ liệu có thể đọc, checksum/metadata hợp lệ | Hash, manifest, kiểm tra file/object | Ứng dụng đọc được dữ liệu |
| 3. Restore | Khôi phục vào môi trường cô lập | Restore job và target ID | Hệ thống nghiệp vụ hoạt động |
| 4. Application | Schema, API, transaction, quyền và kết nối hợp lệ | SQL checks, smoke tests, logs | RTO/RPO trong kịch bản thảm họa đầy đủ |
| 5. DR exercise | Tái dựng hạ tầng, traffic và vận hành với thời gian đo | Timeline, RTO/RPO, runbook, biên bản | Tất cả kịch bản lỗi chưa được diễn tập |

Không nên thay kiểm thử mức 3–5 bằng một thông báo từ backup scheduler. Một bản backup có nhãn SUCCESS vẫn có thể không bao gồm bảng dữ liệu quan trọng hoặc thiếu khóa giải mã trong môi trường đích.

### Tiêu chí PASS/FAIL cần xác định trước

- Backup phù hợp về tuổi và retention.
- Restore hoàn thành trong giới hạn thời gian được phê duyệt.
- Schema, index, ràng buộc và số liệu dữ liệu quan trọng hợp lệ.
- Không có transaction lỗi hoặc sai lệch business invariant vượt ngưỡng cho phép.
- Ứng dụng phục hồi có thể khởi động, kết nối và thực hiện giao dịch kiểm tra.
- IAM, network, Secret Manager, KMS và DNS phục hồi theo phương án.
- RPO và RTO đo được không vượt các mục tiêu.
- Đã lưu evidence, log, chi phí và cleanup đầy đủ.

**Bản restore có dữ liệu nhưng không đạt điều kiện nghiệp vụ phải được đánh dấu FAIL hoặc PARTIAL**, không được báo hoàn thành vì job đã kết thúc thành công.

## 4. Lập danh mục những gì phải phục hồi

Một hệ thống Spring Boot có thể gồm API Cloud Run, Cloud SQL PostgreSQL, bucket Cloud Storage, Pub/Sub, Secret Manager, artifact image và cấu hình IAM/VPC. Nếu chỉ backup database, hệ thống chưa chắc có thể phục hồi.

~~~mermaid
flowchart TD
    A["Đơn hàng hoạt động"]
    A --> B["Orders API / worker"]
    A --> C["Cloud SQL và transaction data"]
    A --> D["Object / tài liệu trong Cloud Storage"]
    B --> E["Artifact Registry image + deployment config"]
    B --> F["Service identity + IAM"]
    B --> G["Secret Manager và key access"]
    B --> H["VPC, DNS, ingress/egress"]
    B --> I["Pub/Sub topics, subscriptions, retry/DLQ"]
    C --> J["Backup/PITR và database restore"]
    D --> K["Object versions/soft delete/backup"]
~~~

### Bảng dependency và owner

| Thành phần | Nguồn phục hồi | Owner | Cách xác minh |
|---|---|---|---|
| PostgreSQL | Cloud SQL backup + PITR theo cấu hình | Database/SRE team | Query, constraints, counts, transaction |
| Object Storage | Versioning/soft delete, backup/export phù hợp | Data owner | Object count, generation, checksum/content |
| Container image | Artifact Registry và provenance | Release team | Digest, image pull, startup |
| Service configuration | IaC, Git hoặc bản export được quản lý | Platform team | Terraform plan/manifest review, smoke test |
| Secret | Secret Manager và quy trình khôi phục riêng | Security/app team | Runtime identity đọc secret đúng phiên bản |
| KMS key | Key policy, IAM, lifecycle theo DR plan | Security | Khả năng decrypt bản backup trong phạm vi được phép |
| IAM/network | Infrastructure as Code và policies | Platform/Security | Access test, private connectivity, deny tests |
| Queue/subscription | IaC + event replay/runbook | Application team | Message routing, idempotency, DLQ |
| Monitoring | IaC, dashboard/alert definitions | SRE | Synthetic test và alert routing |

Lưu ý: một số thành phần không có “backup” theo nghĩa snapshot. Ví dụ, Pub/Sub message không được bảo vệ vô hạn chỉ vì topic còn tồn tại; retention, snapshot/seek khi được hỗ trợ và logic replay phải được thiết kế cụ thể. Infrastructure as Code cũng chỉ giúp tái dựng cấu hình nếu source, quyền và công cụ thực thi vẫn sẵn sàng khi sự cố xảy ra.

## 5. Chọn mẫu diễn tập và mức độ an toàn

Diễn tập backup/DR phải có phạm vi rõ để tránh gây outage hoặc làm sai dữ liệu thật.

| Kiểu diễn tập | Mục đích | Tác động production | Mức rủi ro |
|---|---|---|---|
| Tabletop | Đọc runbook, mô phỏng quyết định và escalation | Không thay production | Thấp |
| Backup inventory | Kiểm tra danh mục, tuổi, quyền, retention | Chủ yếu read-only | Thấp |
| Isolated restore | Phục hồi backup vào target test riêng | Không chuyển production traffic | Thấp đến trung bình |
| Application validation | Dựng app với dữ liệu phục hồi, chặn side effects | Trên môi trường thử nghiệm | Trung bình |
| Controlled failover | Chuyển đường phục vụ hoặc mô phỏng lỗi có kế hoạch | Có thể tác động production nếu chọn sai phạm vi | Cao |
| Full DR drill | Phục hồi quy trình nghiệp vụ trong site/region dự phòng | Tác động tùy thiết kế và cửa sổ thử | Cao |

**Bắt đầu từ isolated restore** để kiểm tra khả năng đọc dữ liệu và runbook. Chỉ tiến đến controlled failover/full DR khi có approval, incident commander, rollback path, người vận hành và cơ chế chặn tác động ngoài ý muốn.

### Nguyên tắc môi trường cô lập

1. Dùng project, network và database target dành riêng cho recovery test khi dịch vụ hỗ trợ.
2. Không restore đè lên database production và không cập nhật production traffic trong bài test thông thường.
3. Không cho test app gửi email, charge payment, webhook hay message thật đến đối tác.
4. Chặn hoặc thay thế external side effects bằng fake/stub, endpoint sandbox hoặc policy egress.
5. Dùng service account có quyền tối thiểu và được cấp trong thời gian có giới hạn.
6. Đặt giới hạn chi phí, expiration tags, run ID và cleanup owner.
7. Phân loại dữ liệu production được phục hồi: môi trường test vẫn phải có bảo mật, logging và retention phù hợp.

Không coi việc đặt tên project chứa chữ test là biện pháp bảo mật đủ. Phải xác nhận project ID và các ranh giới IAM/network trước khi thực thi.

## 6. Cloud SQL: kiểm chứng backup, PITR và giao dịch

Cloud SQL thường chứa dữ liệu quan hệ quan trọng: đơn hàng, khách hàng và trạng thái thanh toán. Với database, mục tiêu không chỉ là tái tạo các file dữ liệu mà còn phải có trạng thái transactionally consistent, schema phù hợp và khả năng cho ứng dụng kết nối lại.

### Các nguồn phục hồi

- **Automated backups:** bản backup do Cloud SQL quản lý theo cấu hình.
- **On-demand backups:** backup được tạo theo nhu cầu, ví dụ trước thay đổi lớn.
- **Point-in-time recovery:** dùng backup và logs theo khả năng cấu hình/cửa sổ phục hồi của engine và dịch vụ.
- **HA/failover:** hỗ trợ khả năng chịu lỗi instance/zone theo cấu hình, nhưng không thay thế backup khi dữ liệu bị sửa sai.

Phải xác minh backup, PITR, retention, vị trí lưu và điều kiện restore theo engine (PostgreSQL/MySQL/SQL Server), edition, version và cấu hình thực tế. Đừng tự suy ra rằng một instance mới có PITR hoặc retention đúng mục tiêu chỉ vì nó đang chạy trên Cloud SQL.

### Bước 1: inventory read-only

Ví dụ thao tác quan sát, không khởi tạo restore:

~~~bash
export PROJECT_ID="example-recovery-project"
export INSTANCE_ID="orders-db"

gcloud sql backups list \
  --instance="$INSTANCE_ID" \
  --project="$PROJECT_ID"

gcloud sql instances describe "$INSTANCE_ID" \
  --project="$PROJECT_ID" \
  --format="yaml(name,region,databaseVersion,settings.backupConfiguration)"
~~~

Hãy ghi backup ID, thời điểm bắt đầu/kết thúc, trạng thái, source instance và chính sách giữ bản sao. Lệnh list trả về backup không đủ để kết luận bản backup có thể khôi phục hay đáp ứng RPO.

### Bước 2: restore vào target cô lập

Tùy engine và quy trình được hỗ trợ, hãy dùng Console/API/gcloud theo hướng dẫn Cloud SQL để khôi phục **một bản backup cụ thể hoặc một mốc PITR cụ thể** vào target dành cho diễn tập. Không chạy lệnh restore trực tiếp trên production trong bài thực hành. Trước thao tác, ghi rõ:

- Source project, instance, backup ID và thời điểm restore.
- Target project/instance được phép, cấu hình máy, network và encryption/key access.
- Quyền của operator và automation để thực hiện restore.
- Cửa sổ thời gian kiểm thử, ngân sách và cleanup policy.
- Trạng thái expected của ứng dụng tại thời điểm được chọn.

Một số phương thức restore có ràng buộc về source/target, engine và project. Chọn workflow đúng phiên bản dịch vụ; nếu tính năng không hỗ trợ khôi phục trực tiếp vào một target nhất định, điều chỉnh kế hoạch và **không tìm cách lách giới hạn bằng thao tác trên instance production**.

### Bước 3: kiểm tra schema và dữ liệu

Sau khi target phục hồi, thực hiện truy vấn read-only bằng account test phù hợp:

~~~sql
-- Schema ở đây là ví dụ cho một ứng dụng Orders.
SELECT COUNT(*) AS total_orders
FROM orders;

SELECT status, COUNT(*) AS order_count
FROM orders
GROUP BY status
ORDER BY status;

SELECT MAX(created_at) AS newest_order_time
FROM orders;

SELECT COUNT(*) AS invalid_amounts
FROM orders
WHERE total_amount < 0;
~~~

So sánh với **manifest kỳ vọng** tại thời điểm backup, không nhất thiết so với database production đang tiếp tục thay đổi. Với dữ liệu lớn, có thể kiểm tra theo partition, sample có chủ đích, số lượng, tổng tiền, khóa ngoại và checksum trên dữ liệu chuẩn hóa. Nếu dùng phép hash theo nhiều dòng, phải cố định thứ tự dòng, encoding và canonical representation; đừng so hash file vật lý của hai database rồi kết luận dữ liệu khác nhau.

### Bước 4: kiểm tra ứng dụng

- Dùng một phiên bản Spring Boot tương thích với schema ở điểm restore.
- Chạy smoke tests đọc đơn hàng, tính tổng tiền, truy vấn theo khóa và phân trang.
- Nếu cần thử ghi, hãy chạy trong target cô lập và có snapshot/cleanup riêng.
- Xác minh JDBC URL, SSL/TLS, IAM/database user, Secret Manager và network.
- Đo thời gian từ yêu cầu restore đến lúc API thực sự xử lý được luồng nghiệp vụ.

Lỗi thường gặp: database restore hoàn thành nhưng ứng dụng không chạy vì schema thuộc release mới hơn/xa hơn image được dùng, hoặc secret database đã được xoay vòng. Bài diễn tập cần kiểm tra **khả năng kết hợp giữa dữ liệu, mã nguồn và cấu hình**.

### Ví dụ đánh giá PITR

Giả sử một thao tác sai xảy ra lúc 10:20 UTC, nhưng phát hiện lúc 10:35. Nếu có PITR hỗ trợ mốc 10:19:59 với logs hợp lệ, target có thể được khôi phục gần mốc trước lỗi. Cần xác minh dữ liệu được khôi phục đến đúng điểm và tìm cách xử lý các giao dịch hợp lệ sau 10:20 (nếu nghiệp vụ cho phép) bằng reconciliation.

**Không lấy việc restore được mốc 10:19:59 làm bằng chứng đã đạt RPO 0.** Các giao dịch hợp lệ phát sinh sau mốc đó có thể bị mất trong bản khôi phục; nhóm phải đo/ước lượng và xử lý đúng theo yêu cầu nghiệp vụ.

## 7. Compute Engine: snapshot disk và phục hồi instance

Với VM, bài kiểm chứng cần xét cả boot disk, data disk, cấu hình guest OS và quy trình thay instance. Snapshot disk thường là nguồn phục hồi dữ liệu phù hợp, nhưng không tự cung cấp cấu hình IAM, firewall, external dependencies hoặc tính nhất quán ứng dụng.

### Quy trình kiểm chứng

1. Inventory snapshots: disk nguồn, timestamp, zone/region, retention, encryption key và backup chain theo mô hình dịch vụ.
2. Xác minh phương án tạo snapshot phù hợp workload. Với database hoặc filesystem đang ghi, dùng cơ chế quiesce/flush/application-consistency nếu được hỗ trợ và cần thiết.
3. Tạo **disk mới** từ snapshot tại project/test scope được phê duyệt.
4. Gắn disk vào VM test cách ly, hoặc dùng snapshot boot disk để thử khởi động VM riêng.
5. Kiểm tra filesystem integrity, cấu trúc file, service config và dữ liệu nghiệp vụ.
6. Đo thời gian dựng disk/VM, khôi phục process và health checks.
7. Dọn disk/VM test, không xóa snapshot nguồn đang nằm trong chính sách retention.

### Các điểm dễ bỏ sót

- Snapshot của một disk không bảo đảm atomic consistency giữa nhiều disk nếu ứng dụng cần giao dịch chéo.
- VM được khôi phục có thể không có network tags, service account, firewall rules hoặc địa chỉ IP cũ.
- Một startup script có thể phụ thuộc artifact hoặc package repository không còn truy cập được.
- License, OS patch, architecture và image version có thể ảnh hưởng khả năng khởi động lại.
- Secret và certificate được load từ nơi khác cần tồn tại trong DR environment.

Với managed instance groups, diễn tập cũng nên kiểm tra khả năng tạo instance mới từ template/image đã được quản lý và health check qua load balancer. Snapshot dữ liệu và khả năng tái dựng compute là hai phần của cùng runbook, không thay thế nhau.

## 8. Cloud Storage: checksum, versioning, soft delete và retention

Object Storage thường giữ tài liệu, ảnh, export hoặc dữ liệu đầu vào xử lý batch. Có thể cần kết hợp nhiều cơ chế:

- **Object Versioning** khi được bật: lưu các generation của object theo cấu hình và vòng đời.
- **Soft delete** theo chính sách: có thể khôi phục object bị xóa trong một cửa sổ phù hợp.
- **Retention policy/Bucket Lock** khi yêu cầu: ngăn xóa sớm theo ràng buộc đã cấu hình.
- **Backup/export sang vị trí khác:** để tránh một số lỗi chung hoặc hỗ trợ chiến lược phục hồi bổ sung.
- **Replication hoặc dual/multi-region storage:** phục vụ nhu cầu availability/durability theo cấu hình, nhưng không tự thay thế versioned recovery.

Hãy kiểm tra cơ chế nào đang bật, thời hạn giữ và tương tác giữa chúng. Retention lock có thể tạo ràng buộc không thể gỡ bỏ dễ dàng; không bật lock chỉ để thử một bài lab.

### Kiểm tra đối tượng sau phục hồi

Một manifest có thể lưu:

| Thuộc tính | Ý nghĩa |
|---|---|
| Bucket và object name | Xác định đối tượng |
| Generation | Xác định bản ghi dữ liệu của object |
| Size | Kiểm tra thiếu hoặc cắt dữ liệu |
| CRC32C/MD5 metadata khi có | Kiểm tra nội dung theo checksum được hỗ trợ |
| Content-Type và metadata | Kiểm tra cách ứng dụng sử dụng object |
| Created/updated timestamp | Đối chiếu retention và nguồn phục hồi |
| Run ID / business key | Liên hệ với bài kiểm tra nghiệp vụ |

CRC32C được Cloud Storage sử dụng để kiểm tra toàn vẹn dữ liệu; MD5 không hiện diện cho mọi object/tình huống. Không dựa vào ETag như một MD5 chắc chắn. Khi tải về để so sánh, dùng cơ chế checksum có hỗ trợ hoặc tự tính hash nội dung theo quy ước đã thống nhất.

Ví dụ các lệnh read-only để kiểm tra bucket test:

~~~bash
gcloud storage ls gs://example-backup-verify/
gcloud storage objects describe \
  gs://example-backup-verify/fixtures/order-001.json
~~~

Để kiểm tra phục hồi, khôi phục một generation hoặc object đã xóa **trong vùng thử nghiệm và theo tính năng được bật**, tải xuống đọc thử, so sánh nội dung và metadata. Không overwrite object production khi chỉ cần kiểm chứng.

### Tác động của retention và chi phí

Giữ nhiều phiên bản giúp phục hồi xóa nhầm nhưng làm tăng dung lượng và chi phí lưu trữ. Lifecycle rules có thể dọn các version cũ nhưng nếu quá ngắn có thể loại bỏ điểm khôi phục cần thiết. Cần thiết kế retention theo phân loại dữ liệu, RPO, yêu cầu pháp lý và khối lượng tăng trưởng.

## 9. Firestore, Spanner, BigQuery và Backup for GKE

Không áp dụng một kiểu backup chung cho mọi hệ thống dữ liệu. Tính năng và cửa sổ phục hồi tùy dịch vụ, version và cấu hình.

### Firestore

Firestore hỗ trợ các cơ chế backup/restore hoặc export/import và tính năng PITR theo khả năng/cấu hình của database. Một bài diễn tập nên:

1. Xác định database, collection/document cần bảo vệ, backup/export location và chính sách retention.
2. Chọn source backup hoặc mốc PITR hợp lệ theo khả năng dịch vụ.
3. Restore/import vào database test riêng hoặc vùng dữ liệu thử nghiệm đã phê duyệt.
4. Kiểm tra document count, document IDs, subcollections, dữ liệu nghiệp vụ và indexes/queries cần thiết.
5. Xác nhận security rules/IAM, index configuration và ứng dụng kết nối được sau phục hồi.

Không nhầm xóa document cha với xóa mọi subcollection. Export/import dữ liệu và tái tạo cấu hình security/index có thể là các bước riêng; cần kiểm chứng những thành phần không được bản export bao phủ.

### Spanner

Cloud Spanner cung cấp backup và restore theo các phương án dịch vụ hỗ trợ. Với dữ liệu giao dịch:

- Ghi backup ID, database, timestamp, retention và key/region.
- Restore vào database kiểm thử được phép.
- Kiểm tra schema, row counts, indexes và ràng buộc dữ liệu nghiệp vụ.
- Thực hiện transaction kiểm thử với account test phù hợp.
- Đo thời gian database có thể được ứng dụng sử dụng.

Nếu kiến trúc multi-region được chọn vì availability, bài diễn tập vẫn phải đo thời gian khôi phục sau logical corruption hoặc xóa nhầm, không chỉ kiểm tra khả năng chịu lỗi hạ tầng.

### BigQuery

BigQuery có các khả năng như table snapshots, time travel và table copies theo giới hạn thời gian/tính năng được hỗ trợ. Chúng phục vụ các trường hợp khôi phục khác nhau; time travel có cửa sổ giới hạn và không nên được coi là backup dài hạn cho mọi dataset.

Một bài diễn tập BigQuery nên:

- Kiểm tra dataset/table được bảo vệ và retention tương ứng.
- Khôi phục một bảng bị ghi đè vào bảng test mới.
- So sánh row count, schema, partitions, key metrics và query results.
- Kiểm tra policy tag, dataset/table access controls, authorized views và data lineage cần thiết.
- Kiểm tra chi phí query/restore và tránh chạy full scan lớn ngoài ngân sách.

### Backup for GKE

Backup for GKE có thể bảo vệ cấu hình Kubernetes và dữ liệu PersistentVolume theo backup plan/restore plan tương ứng. Tuy nhiên, không nên mặc định mọi external database, secret, artifact và service phụ trợ nằm trong bản backup GKE.

Trong diễn tập:

1. Xác nhận namespace/resource/PersistentVolume được chọn trong backup plan.
2. Chọn restore plan vào cluster/namespace thử nghiệm được phê duyệt.
3. Kiểm tra Deployment, Service, ConfigMap, PVC/PV và trạng thái Pod.
4. Xác minh quyền truy cập image, KSA/Workload Identity, Secret Manager và network.
5. Kết nối workload với dữ liệu đã được phục hồi qua quy trình riêng.
6. Chạy smoke tests và kiểm tra không gửi event hoặc lệnh ghi đến production.

**Không coi restore resource Kubernetes hoàn thành là hệ thống đã được phục hồi** nếu dữ liệu ở Cloud SQL, Spanner hoặc Cloud Storage chưa sẵn sàng.

## 10. Cloud Run và ứng dụng Java/Spring: phục hồi tính khả dụng, không chỉ dữ liệu

Cloud Run services thường được thiết kế stateless. Việc dựng lại service có thể dựa vào container image trong Artifact Registry và cấu hình hạ tầng qua Infrastructure as Code. Nhưng cần bảo đảm cả các phụ thuộc:

- Image digest hoặc build artifact đáng tin cậy vẫn truy cập được.
- Service account, IAM invoker, Secret Manager và KMS key còn hợp lệ.
- Environment variables, min/max instances, CPU/memory, concurrency đúng.
- VPC egress, database connectivity, ingress, DNS/custom domain được cấu hình.
- Thứ tự triển khai phù hợp với database migration và schema version.
- Alerts, logs và traces hoạt động để theo dõi quá trình restore.

### Spring Boot smoke test sau phục hồi

| Kiểm tra | Bằng chứng | Lưu ý |
|---|---|---|
| Readiness | /actuator/health/readiness trả trạng thái mong đợi | Không expose thông tin nhạy cảm công khai |
| Database | Query read-only và một transaction test cô lập | Không tạo giao dịch thật |
| Storage | Đọc object phục hồi theo fixture ID | Kiểm tra đúng generation/content |
| Pub/Sub | Gửi message sandbox có correlation ID | Không publish tới topic production |
| Authentication | Test account hợp lệ được chấp nhận | Đồng thời kiểm tra unauthorized bị từ chối |
| Monitoring | Metrics/logs/trace nhận được test event | Không chứa credential/PII |

Các health endpoints của Spring Boot cần được bật/config phù hợp; tên path trong bảng là ví dụ thường gặp, không phải mọi ứng dụng đều có sẵn.

### Không để restore phát sinh side effects

Ứng dụng sau khi restore dữ liệu production có thể chứa đơn hàng PENDING. Nếu khởi động worker bình thường, nó có thể gửi lại email, charge payment hoặc publish duplicate messages. Trong isolated restore:

- Bật chế độ DR_TEST hoặc cấu hình tương đương để tắt external side effects.
- Dùng test credentials/sandbox endpoints cho đối tác.
- Tách Pub/Sub topics/subscriptions và bucket output thử nghiệm.
- Kiểm tra idempotency/replay; không dùng dữ liệu thật để thực hiện thanh toán.
- Chỉ mở traffic sau khi có quyết định phục hồi theo runbook production.

## 11. Runbook diễn tập phục hồi có thể thực hiện lại

Runbook phải đủ rõ để một thành viên khác người thiết kế vẫn có thể thực hiện, đo và dừng an toàn. Một tài liệu mô tả “restore database rồi kiểm tra” là chưa đủ.

### Chuẩn bị trước diễn tập

| Thành phần | Cần chuẩn bị |
|---|---|
| Phạm vi | Workload, backup ID, resource, data classification, target test |
| Người phụ trách | Exercise lead, database operator, application owner, security reviewer |
| Quyền | Service accounts, IAM bindings tạm, KMS/secret access |
| Công cụ | Runbook, CLI/API versions, IaC, artifact, query/health check |
| Network | Project, subnet, ingress/egress, DNS và private connectivity |
| An toàn | Không dùng production target, chặn side effects, xác nhận allowlist |
| Ngân sách | Machine size, storage, network, timeout, cleanup deadline |
| Bằng chứng | Nơi lưu log, timestamps, dashboards và mẫu báo cáo |
| Thoát an toàn | Điều kiện abort và người quyết định dừng |

Một buổi tabletop nên thực hiện trước khi thử restore quan trọng lần đầu. Tabletop giúp phát hiện thiếu quyền, thiếu owner, xung đột runbook và giả định về cách tái tạo dependency.

### Các pha thực thi

~~~mermaid
flowchart TD
    A["Phê duyệt scope và target test"]
    B["Safety preflight + budget/quota"]
    C["Chọn backup và ghi recovery point"]
    D["Provision target cô lập"]
    E["Restore dữ liệu/config"]
    F["Kiểm tra integrity và business invariants"]
    G["Khởi động API/worker test"]
    H["Smoke test + đo RTO/RPO"]
    I{"Đạt acceptance criteria?"}
    J["PASS + lưu bằng chứng"]
    K["FAIL/PARTIAL + phân tích blocker"]
    L["Cleanup + xác minh đã dọn"]
    A --> B --> C --> D --> E --> F --> G --> H --> I
    I -->|"Có"| J --> L
    I -->|"Không"| K --> L
~~~

Nếu phát hiện target sai hoặc có khả năng ghi vào production, **dừng ngay trước khi restore hoặc khởi động application**. Không tiếp tục chỉ để hoàn thành lịch diễn tập.

### Ví dụ safety preflight trong shell

Đây là ví dụ chỉ xác minh **cấu hình target**, không tự tạo hay xóa tài nguyên:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

TARGET_PROJECT="$(printenv TARGET_PROJECT || true)"
RUN_ID="$(printenv RUN_ID || true)"

test -n "$TARGET_PROJECT" || { echo "Missing target project" >&2; exit 2; }
test -n "$RUN_ID" || { echo "Missing run ID" >&2; exit 2; }

case "$TARGET_PROJECT" in
  example-dr-test-1|example-dr-test-2) ;;
  *) echo "Refusing unapproved target" >&2; exit 2 ;;
esac

case "$RUN_ID" in
  dr-*) ;;
  *) echo "RUN_ID must begin with dr-" >&2; exit 2 ;;
esac

echo "Approved target project: $TARGET_PROJECT"
echo "Exercise run: $RUN_ID"
echo "Preflight only: no restore or delete operation performed"
~~~

Trong automation thực, hãy dùng danh sách project được quản lý tập trung thay vì copy hard-code giữa nhiều script. Cần kiểm tra thêm danh tính đang thực thi, resource labels/TTL, network và trạng thái phê duyệt. Điều kiện trên không tự bảo đảm an toàn nếu một principal vẫn có quyền ghi production rộng.

### Ai có quyền ra quyết định?

- Exercise lead: bắt đầu/dừng diễn tập và ghi timeline.
- Data owner: chọn recovery point và đánh giá data loss.
- Infrastructure operator: thực hiện restore/provision đúng phạm vi.
- Security representative: xem xét quyền, key, dữ liệu và điều kiện cách ly.
- Application owner: đánh giá chức năng nghiệp vụ.
- SRE/on-call: xác minh monitoring, incident workflow và RTO.

Tùy quy mô tổ chức, một người có thể đảm nhận nhiều vai trò; nhưng trách nhiệm và việc phê duyệt thao tác rủi ro phải được ghi rõ.

## 12. Tự động hóa verification và diễn tập theo lịch

Manual drill vẫn cần thiết cho phối hợp con người, nhưng nhiều kiểm tra lặp lại có thể tự động hóa:

- Hằng ngày: inventory backup và phát hiện backup job thất bại hoặc quá hạn.
- Hằng tuần: kiểm tra metadata, trạng thái, age và một tập con checksum nếu phù hợp.
- Hằng tháng: isolated restore mẫu vào target dùng cho kiểm thử.
- Hằng quý: end-to-end application restore, kiểm tra IAM/network và đo RTO/RPO.
- Theo chu kỳ rủi ro cao hơn: tabletop/full DR drill, key recovery và region failure exercise.

Các tần suất trên là **ví dụ**; lựa chọn lịch theo criticality, RTO/RPO, compliance và ngân sách thực tế. Hệ thống giao dịch trọng yếu có thể cần kiểm chứng thường xuyên hơn; một kho lưu trữ ít thay đổi có thể dùng lịch khác.

### Mẫu kiến trúc automation

~~~mermaid
flowchart LR
    SCH["Cloud Scheduler"]
    WF["Workflows / orchestrator"]
    INV["Inventory + backup metadata"]
    REST["Isolated restore action"]
    VALID["Validation job"]
    REP["Evidence + result store"]
    CLEAN["Cleanup job"]
    ALERT["Monitoring / notification"]
    SCH --> WF
    WF --> INV
    INV --> REST
    REST --> VALID
    VALID --> REP
    REP --> CLEAN
    CLEAN --> ALERT
~~~

Cloud Scheduler có thể kích hoạt Workflows hoặc Cloud Run Jobs theo quyền được cấu hình. Workflows điều phối các bước có thời gian chờ dài; Cloud Run Jobs có thể chạy kiểm tra SQL/API và tạo báo cáo. Nếu restore API tạo long-running operation, orchestrator cần poll theo deadline và phân biệt trạng thái đang xử lý với thành công/thất bại.

Automation nên có các thuộc tính:

1. **Idempotent:** chạy lại cùng run ID không xóa hoặc tạo trùng tài nguyên ngoài phạm vi.
2. **Scoped:** chỉ truy cập source backup và target test đã được cho phép.
3. **Deadline:** giới hạn thời gian restore, validation và cleanup.
4. **Re-entrant:** có thể tiếp tục hoặc xử lý an toàn sau timeout/mất kết nối.
5. **Observable:** có correlation ID, step status và timestamps.
6. **Fail closed:** nếu kiểm tra target/permission/approval không đạt, không thực hiện restore.
7. **Cost bounded:** số target tối đa, machine size, TTL, cleanup sweeper.

### Kiểm tra sớm trước khi tạo resource

Một verification job có thể thực hiện read-only steps:

- Đọc danh sách backup và lọc bản hoàn tất thành công.
- Kiểm tra backup nằm trong recovery window mong muốn.
- Kiểm tra backup source, project, region, data classification.
- Xác minh target test đã được approve và không trùng production.
- Xác minh danh tính job có quyền read backup và provision target theo scope.
- Ghi lại trạng thái trước khi bắt đầu bước có chi phí.

Sau khi preflight đạt mới chuyển sang restore. Không để một job được trigger bởi người dùng không tin cậy nhận tùy ý project ID rồi có thể restore hoặc xóa bất kỳ resource nào.

## 13. Dữ liệu kiểm tra, manifest và đối chiếu tính toàn vẹn

Một bản backup không dễ kiểm chứng nếu không biết trạng thái kỳ vọng. Nên có **manifest kiểm chứng** hoặc các business invariants bất biến theo mốc dữ liệu.

### Manifest mức dataset

Ví dụ định dạng JSON có thể được tạo bởi một job tin cậy tại thời điểm kiểm chứng:

~~~json
{
  "manifest_version": 1,
  "source": {
    "service": "orders-db",
    "project": "example-prod-project",
    "recovery_point_utc": "2026-11-19T02:00:00Z"
  },
  "datasets": [
    {
      "name": "orders",
      "checks": {
        "row_count": 125000,
        "negative_totals": 0,
        "invalid_status_values": 0
      }
    }
  ],
  "verification": {
    "method": "read-only SQL queries",
    "expected_schema_version": "V42"
  }
}
~~~

Các giá trị trong JSON hoàn toàn minh họa. Khi tạo manifest thật, nguồn dữ liệu, timestamp, schema version và phương pháp đếm phải được lưu cùng nhau. Nếu bản backup và manifest được tạo ở hai thời điểm khác nhau, đừng giả định số đếm sẽ khớp tuyệt đối.

### So sánh sau restore

**Kiểm tra cấu trúc:**

- Database có đúng schema, table, index, constraint và migration level.
- Object có đúng content type, metadata và số generation cần thiết.
- Kubernetes/VM config có đúng resource, runtime identity và endpoint.

**Kiểm tra dữ liệu:**

- Số dòng/đối tượng theo partition quan trọng.
- Min/max timestamp ở từng bảng.
- Tổng tiền, số giao dịch theo trạng thái và các business invariants.
- Hash trên tập dữ liệu được canonical hóa hoặc sample có chủ đích.
- Referential integrity và uniqueness.

**Kiểm tra vận hành:**

- Application startup và readiness.
- Authn/authz đúng với principal test.
- Kết nối dependencies không bị route nhầm sang production.
- Query/API latency và error rate trong phạm vi chấp nhận.

**Không dùng các bảng đếm đơn giản như bằng chứng toàn vẹn tuyệt đối.** Hai dữ liệu khác nhau vẫn có thể có cùng row count. Hãy kết hợp checksums, constraints, sample queries và kiểm thử nghiệp vụ theo mức độ rủi ro.

### Canary records có nên được dùng?

Có thể tạo các bản ghi kiểm tra không nhạy cảm với ID cố định để dễ xác minh recovery point. Tuy nhiên, bài DR không nên phụ thuộc chỉ vào một canary record; nó có thể tồn tại trong backup trong khi phần lớn dữ liệu bị hỏng. Kết hợp canary với checks thực tế trên dữ liệu, transaction boundary và schema.

## 14. Lưu bằng chứng và phân loại kết quả

Mỗi diễn tập cần tạo báo cáo có thể truy vết, kể cả khi FAIL. Không đưa secret hoặc dữ liệu khách hàng đầy đủ vào báo cáo.

| Trường | Ý nghĩa |
|---|---|
| drill_id / run_id | ID duy nhất của lần diễn tập |
| source_backup_id | Bản sao lưu/mốc PITR được sử dụng |
| source_recovery_point | Điểm dữ liệu dự kiến |
| target_project/resource | Nơi phục hồi thử nghiệm |
| scenario | Sự cố mô phỏng: xóa nhầm, mất zone, mất region... |
| start/detect/restore/ready timestamps | Dùng đo RTO theo định nghĩa |
| observed_RPO / observed_RTO | Kết quả thực đo và phương pháp tính |
| integrity_checks | Kết quả số liệu, checksum, constraint, schema |
| application_checks | Readiness, API, auth, business flow |
| security_checks | IAM, KMS, secret và network isolation |
| cleanup_status | Target đã được dọn hay còn pending |
| cost_estimate / actual | Chi phí tạo target, lưu dữ liệu và chạy test |
| owner và approval | Ai thực hiện, phê duyệt và xác nhận |

### Trạng thái kết quả

- **PASS:** mọi acceptance criterion bắt buộc đã đạt và có bằng chứng.
- **PARTIAL:** phục hồi được một phần nhưng thiếu kiểm chứng hoặc còn mục tiêu chưa đạt.
- **FAIL:** dữ liệu, application hoặc RPO/RTO không đạt tiêu chí.
- **BLOCKED:** chưa thể thực hiện vì thiếu quyền, tính năng, nguồn backup hoặc target an toàn.
- **CANCELLED:** diễn tập dừng theo điều kiện an toàn; ghi rõ nguyên nhân.

Không đổi PARTIAL thành PASS chỉ vì bước khó nhất đã hoàn thành. Một bài test bị BLOCKED có thể chỉ ra rủi ro DR rất thực tế, ví dụ không có ai còn quyền khôi phục key hoặc database.

## 15. Tính thời gian RTO/RPO từ một lần diễn tập

Giả sử diễn tập mô phỏng sự cố Orders API tại **10:00 UTC**:

| Mốc UTC | Sự kiện |
|---|---|
| 09:55 | Điểm dữ liệu nhất quán cuối cùng được chọn để restore |
| 10:00 | T0: sự cố mô phỏng bắt đầu |
| 10:04 | Alert hoặc người trực phát hiện |
| 10:10 | Điều phối viên phê duyệt restore |
| 10:14 | Bắt đầu provision và khôi phục target |
| 10:34 | Database sẵn sàng, bắt đầu integrity checks |
| 10:43 | Spring Boot ứng dụng thử nghiệm Ready, chạy business tests |
| 10:49 | T_service_ready: luồng nghiệp vụ trọng yếu đạt tiêu chí |
| 11:03 | Cleanup test resources và lưu báo cáo hoàn tất |

Theo quy ước bài tập:

~~~text
Observed RPO = T0 - last consistent recovery point
             = 10:00 - 09:55 = 5 phút

Observed RTO = T_service_ready - T0
             = 10:49 - 10:00 = 49 phút
~~~

Nếu mục tiêu RPO không quá 15 phút và RTO không quá 60 phút, kịch bản **đạt các ngưỡng thời gian**. Tuy nhiên, chỉ nên ghi kết quả tổng là PASS khi tất cả integrity, business, security và cleanup checks cũng đạt.

Đây là thời điểm và dữ liệu **giả định**. Một lần diễn tập đạt RPO 5 phút không chứng minh hệ thống sẽ luôn đạt RPO 5 phút trong mọi sự cố. Cần kiểm tra lịch backup, log retention, khả năng restore ở thời điểm khác và tình huống lỗi đồng thời.

### Đo thời gian chính xác

- Lưu UTC và múi giờ nhất quán.
- Dùng timestamp từ hệ thống và nhật ký điều phối, không chỉ trí nhớ.
- Phân biệt time to detect, time to authorize, data restore time và application recovery time.
- Không loại bỏ các bước chờ IAM, quota, DNS hoặc approval khỏi RTO chỉ để con số đẹp hơn.
- Nếu diễn tập chủ động được báo trước, ghi rõ việc chuẩn bị sẵn nhân sự có thể khiến RTO nhanh hơn tình huống thật.
- Nếu hệ thống cần phục hồi cả worker/replay backlog, tiêu chí T_service_ready phải bao gồm chức năng nghiệp vụ thực sự cần thiết.

## 16. Tách quyền backup, restore và kiểm chứng

Backup là mục tiêu nhạy cảm của ransomware và thao tác xóa nhầm. Không để một identity có toàn quyền tạo, đọc, sửa, xóa mọi backup, KMS key và production data nếu không có nhu cầu được phê duyệt.

| Vai trò chức năng | Quyền cần thiết về nguyên tắc | Điều nên hạn chế |
|---|---|---|
| Backup operator | Tạo và xem backup theo schedule | Không được xóa bản sao được bảo vệ tùy tiện |
| Restore operator | Đọc backup và restore vào target được cấp phép | Không restore đè production ngoài quy trình |
| Verification job | Đọc manifest, query target test, ghi kết quả | Không thay đổi nguồn production |
| Security/key administrator | Quản lý policy và key theo trách nhiệm | Không thực hiện thao tác dữ liệu nghiệp vụ khi không cần |
| Auditor | Đọc logs/status/evidence phù hợp | Không có quyền xóa backup |
| Cleanup sweeper | Dọn resource thử quá hạn | Không được xóa backup/instance production |

Tên IAM role cụ thể thay đổi theo dịch vụ và thao tác. Hãy xác định quyền tối thiểu từ documentation của Cloud SQL, Compute Engine, Backup and DR hoặc Backup for GKE tương ứng; không dùng Owner/Editor mặc định cho automation.

### Bảo vệ backup trước xóa nhầm hoặc tấn công

- Dùng chính sách retention và immutability/backup vault khi dịch vụ hỗ trợ và phù hợp.
- Tách phạm vi quản trị bản backup khỏi workload production để giảm common-mode failure.
- Bảo vệ service account, CI/CD triggers và credential của backup job.
- Dùng IAM deny/organization policies khi thích hợp, kiểm tra hiệu ứng trong môi trường thử trước.
- Đảm bảo KMS key và quyền decrypt vẫn có thể được khôi phục trong kịch bản DR.
- Theo dõi backup deletion, retention changes, permission changes và audit logs.
- Giới hạn vị trí dữ liệu để không vi phạm data residency.

Một backup được khóa retention mạnh có thể khó dọn trong test; phải hiểu hệ quả và phí lưu trữ trước khi bật trên bucket hay vault. Không thực hiện thử nghiệm khóa không thể đảo ngược trên tài nguyên production.

## 17. Cleanup, chi phí và tài nguyên bị bỏ lại sau diễn tập

Khôi phục một database, disk hoặc cluster thử nghiệm có thể phát sinh chi phí ngay cả khi không có traffic. Một bài diễn tập chỉ kết thúc về mặt vận hành khi tài nguyên dùng tạm đã được xử lý theo chính sách.

### Phân loại tài nguyên trước khi cleanup

| Nhóm | Ví dụ | Được xóa bởi job? |
|---|---|---|
| Source backup được bảo vệ | Cloud SQL backup, snapshot nguồn, backup vault | Không, trừ quy trình retention riêng |
| Target cô lập của drill | Test database, disk, VM, namespace, object tạm | Có, sau khi xác minh run ID và approval |
| Dữ liệu/evidence báo cáo | Timeline, checksum summary, RTO/RPO, logs | Giữ theo retention được phê duyệt |
| Cấu hình hạ tầng dùng chung | Shared VPC, DNS, bucket logs, repository | Không |
| Credentials tạm | Short-lived test IAM binding hoặc secret version test | Thu hồi theo quy trình phù hợp |

### Cleanup theo thứ tự

1. Dừng workload test và chặn job/consumer tạo thêm dữ liệu.
2. Lưu evidence cần thiết, không copy payload nhạy cảm quá mức.
3. Xác nhận target thực sự mang run ID/owner label của bài diễn tập.
4. Xóa resource con như test subscriptions, Pods, disks hoặc objects theo dependency.
5. Xóa test service/instance/namespace chỉ khi đã xác nhận không dùng chung.
6. Thu hồi quyền truy cập tạm và test secrets.
7. Xác minh không còn resource tính phí thuộc run.
8. Ghi cleanup status, chi phí cuối và exception cần xử lý.

### Fallback sweeper

Primary cleanup ở bước cuối không đủ khi CI runner bị kill hoặc job timeout. Dùng một sweeper được cấp quyền giới hạn, chạy theo lịch, kiểm tra resource owner/run ID, created_at/expires_at và trạng thái run. Nó phải có dry-run, allowlist project, giới hạn số lượng xóa và audit logs.

**Không xóa theo tiền tố rỗng hoặc quy tắc rộng** như mọi VM của project test, vì project có thể đang được dùng bởi diễn tập hoặc nhóm khác. Nếu có nghi ngờ về ownership, đánh dấu cleanup pending và yêu cầu người có trách nhiệm xem xét.

### Quản lý chi phí bài diễn tập

- Chọn máy/instance đủ nhỏ để kiểm tra nhưng đủ đại diện cho RTO khi cần.
- Giới hạn thời gian hoạt động của target và đặt cảnh báo ngân sách.
- Đo bytes dữ liệu restore, disk/storage, network transfer và thời gian chạy instance.
- Tách **chi phí verification hằng tháng** khỏi **chi phí triển khai DR thật**.
- Không dùng môi trường quá nhỏ để kết luận RTO production chắc chắn đạt; kích thước dữ liệu, throughput, quota và network khác nhau.

Một bài restore mẫu với dataset nhỏ có thể chứng minh workflow hoạt động, nhưng không chứng minh có thể khôi phục cơ sở dữ liệu nhiều terabyte trong cùng khoảng thời gian. Cần bổ sung rehearsal full-size hoặc extrapolation đã được kiểm chứng.

## 18. Lỗi phổ biến khi backup verification và DR drill

| Hiện tượng | Nguyên nhân thường gặp | Cách phòng tránh/kiểm tra |
|---|---|---|
| Có backup nhưng restore thất bại | Backup bị lỗi hoặc method/target không tương thích | Test restore định kỳ theo đúng engine/version |
| Restore thành công nhưng app lỗi | Schema không khớp, secret/connection thiếu | Chạy smoke test theo release tương ứng |
| Không truy cập được target | IAM, VPC, DNS hoặc private endpoint sai | Safety preflight và network diagnostics |
| Dữ liệu sai dù số dòng đúng | Bản backup khác thời điểm, lỗi logic, hash chưa chuẩn | Manifest theo recovery point, invariants và checksums |
| RPO không đạt | Lịch backup thưa, PITR không bật, logs không đủ | Kiểm tra retention/window và quan sát lag |
| RTO không đạt | Chờ phê duyệt, quota, restore throughput, thao tác thủ công | Đo từng pha và tự động hóa bước an toàn |
| Replication cũng chứa dữ liệu sai | Logical corruption lan sang bản sao | Backup/PITR tách khỏi replication |
| Thiếu quyền decrypt | KMS key bị vô hiệu hóa hoặc IAM key sai | Diễn tập kiểm tra quyền key, bảo vệ key lifecycle |
| Worker gửi lại giao dịch thật | Môi trường DR không cô lập side effects | Sandbox APIs, fake endpoints, egress controls |
| Báo cáo PASS quá sớm | Chỉ dựa vào trạng thái restore job | Acceptance criteria bao gồm app và nghiệp vụ |
| Dữ liệu nhạy cảm lộ trong test project | Sao chép production sang môi trường bảo vệ yếu | Data classification, IAM, encryption, retention |
| Diễn tập làm tăng hóa đơn kéo dài | Target không được dọn sau runner crash | TTL, cleanup job, owner và budget alert |
| Runbook không ai dùng được | Kiến thức nằm ở một người, lệnh hết hạn | Tabletop, cross-training và versioned runbook |
| DR có nhiều region nhưng cùng một key lỗi | Common-mode failure trong IAM/KMS/control plane | Dependency mapping và fault-injection có kiểm soát |

### Khi backup bị thiếu hoặc không thể restore

Không được xóa bằng chứng rồi chạy lại để báo kết quả đẹp hơn. Hãy:

1. Ghi lại backup ID, trạng thái và mã lỗi không chứa payload nhạy cảm.
2. Xác định còn bản backup hoặc PITR hợp lệ nào khác không.
3. Đánh giá RPO/RTO rủi ro và báo đúng owner.
4. Tạo incident hoặc risk item nếu đã mất năng lực khôi phục cần thiết.
5. Sửa cấu hình, quyền hoặc quy trình, rồi **diễn tập lại** trước khi đóng vấn đề.

Lỗi khi diễn tập là thông tin có giá trị nếu được ghi trung thực. Một báo cáo PASS không có bằng chứng còn nguy hiểm hơn báo cáo FAIL dẫn đến cải tiến thực.

## 19. Ví dụ hoàn chỉnh: diễn tập phục hồi Orders API

Giả sử ứng dụng Orders có Spring Boot trên Cloud Run, PostgreSQL trên Cloud SQL, tài liệu trên Cloud Storage và worker xử lý event từ Pub/Sub. Mục tiêu diễn tập là xác nhận một kịch bản xóa nhầm dữ liệu có thể phục hồi trong giới hạn đã được thỏa thuận.

### Yêu cầu giả định

- RPO: không quá 15 phút.
- RTO: không quá 60 phút tính từ lúc sự cố giả định bắt đầu đến khi luồng tra cứu/tạo đơn hàng thử nghiệm hoạt động.
- Không gửi email, tạo thanh toán hoặc ghi Pub/Sub event đến môi trường production.
- Mọi resource thử ở project DR test đã được phê duyệt.
- Bản backup nguồn phải giữ nguyên; cleanup chỉ xóa target do drill tạo.

### Kịch bản và kế hoạch

| Pha | Hành động | Bằng chứng |
|---|---|---|
| Preflight | Xác minh owner, target, IAM/KMS, budget và isolation | Approval, allowlist, identity |
| Inventory | Chọn Cloud SQL backup/PITR và object generation | Backup IDs, timestamps |
| Restore | Khôi phục database và các object thử vào target | Operation IDs, restore results |
| Rebuild app | Dựng revision Cloud Run test bằng image digest phù hợp | Revision, config, IAM |
| Data validation | Query số đơn hàng, total, constraints, object hashes | SQL và checksum report |
| Business checks | Đọc/tạo đơn hàng sandbox, tránh side effects | Test response, correlation ID |
| Measure | Ghi T0, recovery point, service ready | RPO/RTO computation |
| Cleanup | Xóa target và thu hồi IAM tạm, giữ evidence | Resource inventory sau cleanup |

### Các assertion nghiệp vụ

1. Khách hàng thử có thể tra cứu một đơn hàng thuộc recovery point.
2. Tổng giá trị đơn hàng và trạng thái thanh toán khớp manifest mong đợi.
3. Không có đơn hàng âm tiền hoặc trạng thái không hợp lệ.
4. Một request tạo đơn hàng trong sandbox không tạo duplicate khi retry.
5. Object chứng từ có đúng content và metadata.
6. Các request chưa xác thực bị từ chối như trước.
7. Log/trace có correlation ID nhưng không chứa password hoặc dữ liệu nhạy cảm.

### Kết luận mẫu

Một biên bản có thể ghi: “Restore DB và object đạt, API hoạt động sau 49 phút, RPO thực đo 5 phút, nhưng phát hiện runbook không ghi cách gắn runtime service account ở target”. Nếu bước gắn IAM chưa tự động hóa, kết quả vẫn có thể đạt các ngưỡng thời gian nhưng cần action item giảm phụ thuộc thao tác thủ công. Nếu một business assertion chưa được thực hiện, kết quả nên ghi PARTIAL thay vì PASS.

### Action items sau bài diễn tập

| Action | Mục tiêu | Owner | Cách xác minh |
|---|---|---|---|
| Đưa cấu hình Cloud Run/IAM vào IaC | Giảm thời gian tái dựng | Platform | Tạo target từ IaC trong drill tiếp theo |
| Bổ sung manifest integrity theo recovery point | Tránh false PASS | Data team | So sánh được counts/constraints/hash |
| Bật cảnh báo backup quá hạn | Phát hiện mất coverage sớm | SRE | Giả lập sự kiện không có backup mới |
| Diễn tập xoay quyền KMS trong môi trường thử | Phát hiện key dependency | Security | Restore thành công sau policy change test |
| Tự động cleanup target theo run ID | Giảm phí và rủi ro | Platform | Sweeper không ảnh hưởng resource khác |

Action item cần có hạn hoàn thành và mức ưu tiên cụ thể trong hệ thống theo dõi của tổ chức. Không để kế hoạch chỉ ở trang postmortem mà không có người nhận trách nhiệm.

## 20. Bài tập thực hành: kiểm chứng backup và chạy một DR drill an toàn

Bối cảnh: bạn là thành viên SRE phụ trách orders-api. Ứng dụng được triển khai trên Cloud Run, dữ liệu chính nằm trong Cloud SQL PostgreSQL và tài liệu trong Cloud Storage. Hãy chứng minh nhóm có thể khôi phục dữ liệu và luồng nghiệp vụ với **RPO 30 phút** và **RTO 90 phút**. Đây là bài lab trên môi trường thử nghiệm có backup được tạo từ dữ liệu tổng hợp; không được dùng credentials hoặc dữ liệu khách hàng thật.

### Phần A — Phân tích yêu cầu

1. Ghi rõ ý nghĩa SLI, RTO, RPO và thời điểm bắt đầu/kết thúc đo.
2. Vẽ dependency map gồm API, database, bucket, image, IAM, secret, KMS và network.
3. Lập danh mục resource có thể backup và những cấu hình cần tái dựng bằng IaC.
4. Chọn ít nhất một failure scenario: mất database, xóa nhầm bản ghi hoặc VM/disk hỏng.
5. Đề xuất tiêu chí PASS cho dữ liệu, ứng dụng, IAM và cleanup.

### Phần B — Tạo fixture và backup thử nghiệm

1. Dùng project GCP thử nghiệm được phê duyệt.
2. Tạo dữ liệu tổng hợp: 20 đơn hàng với trạng thái và tổng tiền cố định.
3. Tạo một số object JSON nhỏ trong bucket riêng.
4. Ghi recovery point và manifest có row counts, checksums và schema version.
5. Tạo backup theo khả năng dịch vụ test được sử dụng hoặc chọn backup hợp lệ có sẵn.
6. Xác nhận job hoàn tất và inventory ghi đúng backup ID.

### Phần C — Restore cô lập

1. Chạy safety preflight xác nhận project target và run ID.
2. Kiểm tra service account và quyền cần thiết, không cấp Owner cho cả pipeline.
3. Restore database/object vào **target test riêng** bằng workflow được hỗ trợ.
4. Ghi thời điểm bắt đầu, kết thúc restore và operation ID.
5. Kiểm tra schema, business invariants, row counts và checksums.
6. Chạy một revision ứng dụng với DR_TEST mode và các external endpoints sandbox.
7. Thực hiện smoke tests đọc đơn hàng và transaction test không ảnh hưởng production.
8. Tính RPO/RTO quan sát được, nêu rõ giả định.

### Phần D — Thất bại có kiểm soát

Trong target test, thử một trong các tình huống:

- Một backup/version không hợp lệ.
- Một service account test không có quyền đọc secret.
- Một object bị thiếu trong tập dữ liệu kiểm chứng.
- Một schema không tương thích với image ứng dụng.

Đánh dấu bài test FAIL hoặc BLOCKED đúng nguyên nhân. Xác nhận log có resource ID và mã lỗi nhưng không có payload secret. Không tạo sự cố trên production để thực hiện bài tập.

### Phần E — Cleanup và báo cáo

1. Đóng workload thử nghiệm và dừng subscriber/worker test.
2. Xóa đúng resource có run ID; giữ nguyên backup nguồn.
3. Thu hồi IAM binding hoặc secret tạm nếu có.
4. Kiểm tra còn tài nguyên tính phí nào thuộc run không.
5. Ghi báo cáo với timeline, acceptance criteria, RPO/RTO, chi phí và status cleanup.
6. Viết ít nhất ba action items có owner, mức ưu tiên, deadline và verification.

### Tiêu chí hoàn thành

| Mục | Kết quả mong đợi |
|---|---|
| Safety | Không chỉnh sửa nguồn production hoặc xóa backup nguồn |
| Recovery target | Tài nguyên test được đặt tên/owner rõ ràng |
| Data integrity | Counts, invariants và sample/hash khớp manifest |
| App recovery | Spring Boot đọc dữ liệu và thực hiện smoke test phù hợp |
| Time targets | Observed RPO ≤ 30 phút, observed RTO ≤ 90 phút |
| Security | IAM, secret, network và KMS được kiểm tra |
| Evidence | Có run ID, backup ID, timestamps và kiểm chứng |
| Cleanup | Target đã dọn và không còn phí ngoài dự kiến |

## 21. Checklist kiểm chứng bản sao lưu và diễn tập định kỳ

- [ ] Đã xác định workload và owner của từng dữ liệu/tài nguyên.
- [ ] Đã thống nhất RPO, RTO và điều kiện PASS/FAIL.
- [ ] Đã phân biệt backup, replication, HA và PITR.
- [ ] Đã xác nhận loại backup, retention và recovery window.
- [ ] Đã kiểm tra backup ID, source resource, status và timestamp.
- [ ] Đã xác định version schema, image digest và cấu hình tương ứng.
- [ ] Đã có bản đồ phụ thuộc app, data, IAM, key, network và event queue.
- [ ] Đã có target DR test an toàn, với allowlist và phê duyệt.
- [ ] Đã chặn email, payment, webhook và message side effects thật.
- [ ] Đã chọn restore point nhất quán và ghi manifest kỳ vọng.
- [ ] Đã restore vào target test bằng workflow dịch vụ hỗ trợ.
- [ ] Đã kiểm tra số dòng/object, checksum, schema và business invariants.
- [ ] Đã kiểm tra startup, readiness, authentication và API nghiệp vụ.
- [ ] Đã đo thời gian từ T0 đến service ready, không chỉ thời gian restore job.
- [ ] Đã tính observed RPO bằng recovery point thực tế.
- [ ] Đã kiểm tra quyền runtime, Secret Manager và KMS decrypt.
- [ ] Đã kiểm tra log, alert, dashboard và đường escalation.
- [ ] Đã ghi PASS/PARTIAL/FAIL/BLOCKED trung thực.
- [ ] Đã có runbook và người chịu trách nhiệm cho từng bước.
- [ ] Đã lập lịch drill tiếp theo dựa trên mức độ quan trọng.
- [ ] Đã đặt time limit, budget alerts và cleanup deadline.
- [ ] Đã dọn resource test, thu hồi quyền tạm và giữ evidence phù hợp.
- [ ] Đã tạo action items và theo dõi đến khi được xác minh hoàn thành.

## Câu hỏi tự kiểm tra

**1. Vì sao trạng thái SUCCESS của backup job chưa đủ để chứng minh khả năng phục hồi?**

Vì backup có thể không đầy đủ, không nhất quán, thiếu quyền decrypt hoặc không dùng được với phiên bản ứng dụng khi restore. Cần ít nhất một bài restore và kiểm chứng dữ liệu/chức năng.

**2. RTO và RPO khác nhau như thế nào?**

RTO đo giới hạn thời gian phục hồi dịch vụ theo kịch bản; RPO đo lượng dữ liệu tối đa được phép mất tính từ recovery point. Khôi phục nhanh không tự bảo đảm mất ít dữ liệu và ngược lại.

**3. Tại sao replica của database không thay thế backup?**

Vì lệnh xóa sai hoặc cập nhật dữ liệu hỏng có thể được nhân bản sang replica. Backup/PITR cung cấp điểm phục hồi về trước lỗi nếu nằm trong cửa sổ hỗ trợ.

**4. Vì sao restore phải được thử trong môi trường cô lập?**

Để tránh ghi đè production, không gửi side effects thật và giới hạn quyền, network, ngân sách. Dữ liệu production nếu được dùng để kiểm chứng vẫn phải được bảo vệ đúng phân loại.

**5. Vì sao cần manifest gắn với thời điểm backup?**

Vì database đang thay đổi. Nếu so số dòng ở thời điểm hiện tại với một bản backup cũ, khác biệt có thể là hoạt động bình thường chứ không phải lỗi restore.

**6. Checksum của một object Cloud Storage có thể xác minh điều gì?**

Nó giúp kiểm tra nội dung object không bị thay đổi ngoài ý muốn theo thuật toán và phạm vi checksum được hỗ trợ. Nó không chứng minh ứng dụng xử lý đúng hoặc tất cả object cần thiết đều tồn tại.

**7. Tại sao full DR drill cần khôi phục cả IAM, secret và network?**

Vì ứng dụng chỉ hoạt động khi có identity, quyền truy cập, routing, DNS và các dependency cần thiết. Database restore xong nhưng API không truy cập được vẫn chưa đạt phục hồi nghiệp vụ.

**8. Khi nào dùng FAIL, PARTIAL hoặc BLOCKED?**

FAIL khi tiêu chí bắt buộc không đạt; PARTIAL khi phục hồi một phần nhưng thiếu xác minh; BLOCKED khi chưa thể diễn tập vì thiếu điều kiện như quyền, source backup hoặc target an toàn.

**9. Vì sao diễn tập nên có fallback cleanup?**

Vì finally/teardown của test có thể không chạy khi runner chết hoặc mất kết nối. Sweeper theo owner/run ID và TTL giúp phát hiện resource tạm bị bỏ lại.

**10. Nếu bài diễn tập đạt RPO 5 phút và RTO 49 phút một lần, có thể cam kết luôn đạt các con số đó không?**

Không. Cần thử nhiều recovery points, quy mô dữ liệu, kịch bản lỗi, điều kiện tải và dependency để đánh giá độ tin cậy của các mục tiêu trong điều kiện thực tế.

## Tài liệu tham khảo

- [Google Cloud Architecture Framework: Reliability](https://docs.cloud.google.com/architecture/framework/reliability)
- [Google Cloud: Disaster recovery planning guide](https://docs.cloud.google.com/architecture/dr-scenarios-planning-guide)
- [Cloud SQL: Backups overview](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/backups)
- [Cloud SQL: Point-in-time recovery](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/pitr)
- [Compute Engine: Snapshots overview](https://docs.cloud.google.com/compute/docs/disks/snapshots)
- [Cloud Storage: Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
- [Cloud Storage: Soft delete](https://docs.cloud.google.com/storage/docs/soft-delete)
- [Cloud Storage: Object integrity](https://docs.cloud.google.com/storage/docs/data-validation)
- [Firestore: Backups](https://docs.cloud.google.com/firestore/native/docs/backups)
- [Firestore: Export and import](https://docs.cloud.google.com/firestore/native/docs/manage-data/export-import)
- [Spanner: Back up and restore databases](https://docs.cloud.google.com/spanner/docs/backup)
- [BigQuery: Time travel and fail-safe](https://docs.cloud.google.com/bigquery/docs/time-travel)
- [BigQuery: Table snapshots](https://docs.cloud.google.com/bigquery/docs/table-snapshots-intro)
- [Backup for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/concepts/backup-for-gke)
- [Cloud Run Jobs](https://docs.cloud.google.com/run/docs/create-jobs)
- [Google Cloud Workflows](https://docs.cloud.google.com/workflows/docs/overview)
- [Cloud Scheduler](https://docs.cloud.google.com/scheduler/docs/overview)
- [Secret Manager overview](https://docs.cloud.google.com/secret-manager/docs/overview)

## Kết luận

**Backup chỉ có giá trị khi có thể khôi phục một cách kiểm chứng được.** Việc tạo bản sao lưu thành công là điểm khởi đầu; khả năng phục hồi thực tế phụ thuộc vào tính nhất quán dữ liệu, quyền truy cập backup/key, các phiên bản schema và ứng dụng, mạng, secret, khả năng dựng hạ tầng và quy trình xử lý sự cố. Kiểm chứng theo nhiều mức — từ inventory và checksum đến isolated restore, smoke test và full DR drill — giúp phát hiện lỗ hổng trước khi thảm họa thật xảy ra.

Hãy định nghĩa RTO/RPO theo nghiệp vụ, bảo vệ nguồn backup, diễn tập trong môi trường cô lập, ghi bằng chứng theo run ID và đo đến khi **luồng nghiệp vụ** thực sự sẵn sàng. Lịch kiểm chứng và cleanup tự động làm cho quy trình có thể lặp lại; tabletop, controlled failover và action items đảm bảo đội ngũ không chỉ có backup mà còn có **năng lực phục hồi**.
