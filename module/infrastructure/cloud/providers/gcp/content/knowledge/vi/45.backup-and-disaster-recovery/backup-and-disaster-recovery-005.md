# Chiến lược sao lưu xuyên project và phân tách quyền

Giả sử một ứng dụng Java/Spring Boot chạy trên GKE và Cloud SQL ở project production. Một tài khoản triển khai bị chiếm quyền, sau đó kẻ tấn công xóa database, thay đổi lịch backup và cố xóa luôn bản sao lưu. Nếu toàn bộ workload, bản backup và quyền quản trị cùng nằm trong một project với các quyền rộng, việc có lịch snapshot hằng ngày chưa đủ để bảo đảm khôi phục được hệ thống.

**Sao lưu xuyên project (cross-project backup)** là một cách tạo ranh giới quản trị: ứng dụng chạy trong project nguồn, bản sao lưu và chính sách bảo vệ được quản lý ở project khác, còn việc khôi phục được diễn tập trong project đích độc lập. **Phân tách quyền (separation of duties)** đảm bảo người được triển khai ứng dụng không mặc nhiên sửa chính sách retention, xóa backup, quản lý khóa mã hóa hoặc tự phê duyệt việc restore dữ liệu nhạy cảm.

Trong chương **Sao lưu và phục hồi thảm họa** của module **CLOUD_PROVIDERS_GCP**, bài học liên hệ project, IAM, VPC, Compute Engine, GKE, Cloud Run, các dịch vụ cơ sở dữ liệu, Cloud Storage, mã hóa, tự động hóa, observability và kiểm soát chi phí. Mục tiêu là thiết kế một đường khôi phục có thể kiểm chứng, không chỉ tạo ra các file backup mà chưa từng thử restore.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt backup, snapshot, replica, archive và cơ chế chống xóa bằng retention.
- Tách project nguồn, project backup và project khôi phục; xác định ranh giới IAM và trust.
- Chọn Backup and DR backup vault, Backup for GKE, Cloud SQL export, Cloud Storage hoặc Compute Engine snapshot theo hỗ trợ thực tế.
- Thiết kế service agent và quyền ghi/đọc/khôi phục theo nguyên tắc ít quyền nhất.
- Sử dụng enforced retention, Bucket Lock, object versioning và CMEK mà không đánh mất khả năng restore.
- Đo RPO/RTO, bảo vệ dữ liệu trước ransomware và thực hiện restore drill có đối soát.

## 1. Trước hết: backup khác replica, snapshot và archive

| Cơ chế | Công dụng | Giới hạn cần nhớ |
|---|---|---|
| High availability replica | Chuyển dịch vụ nhanh khi lỗi instance/zone | Có thể sao chép cả thao tác xóa nhầm hoặc dữ liệu bị mã hóa độc hại |
| Cross-region read replica | DR, đọc ở nơi khác, giảm thời gian tái tạo dữ liệu | Replication bất đồng bộ có thể có lag; không phải bản backup độc lập |
| Disk snapshot | Ghi lại trạng thái disk ở một thời điểm | Không tự bảo đảm tính nhất quán của transaction database hay tách biệt project |
| Database-managed backup/PITR | Khôi phục database theo thời điểm được hỗ trợ | Retention và phạm vi quyền thường gắn với hệ quản lý database; phải kiểm tra khả năng khôi phục sang môi trường độc lập |
| Backup vault / bản sao độc lập | Tạo điểm khôi phục theo chính sách, tách vòng đời dữ liệu | Phải xác định loại workload được hỗ trợ, access restriction và cách restore |
| Export sang Cloud Storage | Tạo bản sao có thể chuyển project hoặc hệ thống | Có thể thiếu WAL/binlog, quyền, schema ngoài phạm vi export hoặc point-in-time recovery |
| Archive dài hạn | Đáp ứng lưu trữ pháp lý và kiểm toán | Đọc/khôi phục có thể chậm, chi phí thao tác và retention có ràng buộc |

Một bản backup tốt phải có **khả năng tồn tại độc lập với lỗi hoặc quyền quản trị của hệ thống nguồn**, có metadata để tìm đúng thời điểm, có dữ liệu đủ nhất quán để restore và có quyền/khóa mã hóa cần thiết khi thảm họa xảy ra.

### Quy tắc 3-2-1-1-0 trong thực tế cloud

Một nguyên tắc tham khảo là giữ nhiều bản sao dữ liệu, có ít nhất một bản ở failure domain riêng, một bản **immutable hoặc offline/air-gapped theo khả năng của giải pháp**, và mục tiêu **không có lỗi chưa phát hiện trong kiểm tra restore**. Đừng áp dụng số lượng bản sao một cách máy móc: hai backup cùng project và cùng danh tính có thể vẫn chịu chung một blast radius. Đánh giá tính độc lập của project, IAM, organization, KMS key, location, service agent và mạng.

## 2. Bắt đầu từ RPO, RTO và phân loại dữ liệu

Trước khi xây project backup, xác định **dữ liệu nào**, **ai là chủ dữ liệu**, **điểm khôi phục bao xa** và **ứng dụng phải hoạt động lại nhanh đến đâu**.

| Nhóm dữ liệu | Ví dụ minh họa | RPO tham khảo | RTO tham khảo | Hướng backup |
|---|---|---|---|---|
| Transactional | Đơn hàng, thanh toán, sổ cái | 5–15 phút hoặc chặt hơn | Dưới vài giờ | PITR/backup định kỳ, DR replica và restore được kiểm thử |
| Cấu hình cluster | Kubernetes Deployment, ConfigMap, policy | Theo nhịp phát hành | Dưới vài giờ | GitOps/IaC cùng Backup for GKE cho phần cần bảo vệ |
| Dữ liệu volume | PVC, file chia sẻ, media | Theo tần suất thay đổi | Tùy dung lượng | Backup for GKE / Backup and DR / object copy |
| Logs/audit | Cloud Logging export, lịch sử vận hành | Theo nghĩa vụ tuân thủ | Theo yêu cầu điều tra | Sink tới project lưu trữ, retention và quyền riêng |
| Secrets, khóa và định danh | Secret Manager, KMS key, IAM policy | Phụ thuộc RTO/RPO ứng dụng | Phải sẵn trước khi restore | Chính sách riêng về khôi phục danh tính, khóa và cấu hình |

Các con số trên chỉ là **ví dụ hoạch định**, không phải SLA của Google Cloud. Với ứng dụng ghi liên tục, lịch backup mỗi ngày không thể mặc nhiên đáp ứng RPO năm phút. Nếu business yêu cầu RPO chặt, cần kết hợp PITR, log shipping, CDC hoặc replication có kiểm soát và vẫn giữ bản backup độc lập để chống lỗi logic.

### Recovery point khác recovery readiness

Backup hoàn tất lúc 02:00 chưa đủ để kết luận có thể phục hồi trong 30 phút. Cần thời gian provision project đích, quota, instance, network, firewall, IAM, KMS, chuyển DNS, chạy DB migrations, tải image và kiểm thử nghiệp vụ. Nhiều hệ thống có RPO tốt nhưng **RTO tệ** vì chưa chuẩn bị runbook và quyền phục hồi.

## 3. Topology ba project: nguồn, backup và khôi phục

Một sơ đồ tham khảo:

~~~mermaid
flowchart LR
  subgraph SRC["Project A: app-prod"]
    APP[Spring Boot / GKE / Compute Engine]
    DB[(Cloud SQL / disks)]
    OPS[CI/CD và app operators]
    APP --> DB
  end
  subgraph BAK["Project B: backup-security"]
    VAULT[Backup and DR vault hoặc Backup for GKE]
    GCS[Storage archive có retention]
    AUDIT[Audit logs và alerts]
    KMS[Key project hoặc key được kiểm soát]
  end
  subgraph REC["Project C: isolated-restore"]
    REST[Restore/test cluster hoặc VM]
    VALID[Integrity và smoke tests]
    REST --> VALID
  end
  DB -->|backup với danh tính được cấp quyền| VAULT
  APP -->|backup theo dịch vụ| VAULT
  DB -. export có kiểm soát .-> GCS
  VAULT -->|recovery authorization| REST
  GCS -->|restore drill| REST
  KMS -. decrypt đúng policy .-> REST
  VAULT --> AUDIT
~~~

Ba project là ranh giới **Google Cloud resource và IAM**, không tự động là ba vùng bảo mật hoàn toàn độc lập. Cấp quyền rộng tại organization/folder, service account impersonation không kiểm soát hoặc quyền quản lý KMS từ một nhóm duy nhất có thể xuyên qua các project. Vùng backup nên có nhóm quản trị, danh tính automation, policy, logging và luồng phê duyệt riêng so với production.

| Project | Nội dung | Chủ sở hữu/định hướng IAM |
|---|---|---|
| A – nguồn | Workload, database, disk, app config, source-level backup connector | Application/platform team có quyền vận hành; không có quyền xóa backup vault B |
| B – backup | Backup vault, backup/restore policy, object archive, monitoring backup | Backup/security team; tách người cấu hình retention và người phê duyệt xóa |
| C – restore | Sandbox DR, cluster/VM/database đích, isolation network | Recovery team nhận quyền theo thời hạn và approval |
| Key/security project (tùy chọn) | Cloud KMS keys, IAM federation, audit sink | Security/key custodians, hạn chế người tạo backup tự hủy key |

**Tách project không mặc nhiên tách region.** Backup nằm ở project B nhưng cùng region A vẫn có thể chịu chung sự cố địa lý. Hãy chọn location theo data residency, service support, mục tiêu RPO/RTO và chi phí chuyển dữ liệu. Với backup vault, location là thuộc tính của vault và phải phù hợp với workload/recovery support.

## 4. Mô hình trách nhiệm và phân tách quyền

Các vai trò quản trị nên được thiết kế theo **khả năng gây hậu quả**, không chỉ theo tên nhóm.

| Vai trò tổ chức | Được phép | Không nên mặc nhiên được phép |
|---|---|---|
| Application operator | Deploy/restart app, quan sát backup status, yêu cầu restore | Giảm retention, xóa vault, cấp quyền KMS cho chính mình |
| Backup policy admin | Tạo backup plan, chọn lịch, giám sát coverage | Sửa dữ liệu production hoặc tự duyệt restore dữ liệu nhạy cảm |
| Vault custodian | Quản lý vault/retention và ranh giới project | Triển khai app hoặc thực hiện khôi phục vào prod không qua approval |
| Security/key custodian | Cấp/thu hồi quyền key theo chính sách, điều tra audit | Mặc định đọc toàn bộ dữ liệu ứng dụng qua restore |
| Restore operator | Khôi phục vào project C đã phê duyệt | Ghi đè production hoặc tắt backup protection tùy ý |
| Auditor | Đọc metadata backup jobs, policy và logs | Đọc payload backup, thay đổi IAM hoặc khôi phục dữ liệu |
| Incident commander/approver | Quyết định DR, duyệt break-glass | Tự mình thực hiện mọi bước với account quản trị thường trực |

Thực hành **four-eyes**: yêu cầu thay đổi retention/backup deletion, IAM cấp quyền restore và truy cập bản backup chứa dữ liệu nhạy cảm nên có reviewer độc lập. Dùng nhóm IAM, quyền theo resource scope, temporary elevated access và Privileged Access Manager (PAM) khi phù hợp. Break-glass account phải có audit, thời hạn, điều kiện sử dụng và định kỳ được diễn tập.

### Kiểm soát rủi ro từ quyền cấp ở cấp tổ chức

Người có khả năng thay đổi organization policy, tạo role bindings trên folder, impersonate service agent hoặc quản lý Cloud KMS có thể làm mất hiệu lực tường ngăn logic giữa project A/B/C. Vì vậy, nhóm security phải kiểm tra **effective IAM** (kể cả inherited permissions), service account key creation, domain-restricted sharing, tổ chức project và policy constraints. Không chỉ nhìn IAM tab của project B rồi khẳng định backup đã độc lập.

## 5. Backup and DR backup vault: quản lý tập trung và chống xóa

**Backup and DR** có mô hình **centralized**: đặt backup vault và backup plans trong một project quản trị, bảo vệ Compute Engine, Cloud SQL, Filestore, AlloyDB và các loại workload được hỗ trợ ở service projects khác. Còn mô hình **decentralized** tạo vault/plan riêng cho từng project để các nhóm độc lập quản lý. Với chiến lược chống chiếm quyền project nguồn, mô hình tập trung thường phù hợp hơn nếu IAM được tách chặt.

Backup vault là một tài nguyên regional do Google quản lý, cung cấp isolation và **enforced retention**. Danh sách workload hỗ trợ khác nhau theo đường quản trị Google Cloud console hoặc backup/recovery appliance; phải chọn theo service và loại instance, không giả định vault lưu mọi file bất kỳ.

### Enforced retention và project deletion protection

- Khi vault có **minimum enforced retention**, các backup được bảo vệ không thể bị xóa thủ công trước hạn. Retention của backup plan phải tương thích mức tối thiểu vault.
- Vault có thể áp dụng retention theo rule backup và có lựa chọn **khóa cấu hình retention** theo thời điểm hiệu lực. Sau khi khóa có hiệu lực, không được giảm hoặc loại bỏ mức bảo vệ theo tính năng.
- Enforced retention có chi phí: dữ liệu được giữ đến hết thời hạn dù ứng dụng không còn cần. Chọn chính sách dựa trên yêu cầu nghiệp vụ, pháp lý và chi phí.
- Theo tài liệu cập nhật, **từ ngày 1/11/2026** Backup and DR tự động áp dụng project-level lien cho project có backup vault chứa backups được bảo vệ bằng enforced retention. Đây là cơ chế bổ sung chống xóa project; vẫn cần kiểm tra quyền tháo lien và quy trình phê duyệt.
- **Backup vault access restriction** giới hạn nguồn/đích project hoặc organization của thao tác backup/restore. Lựa chọn access restriction có thể là cấu hình không đổi được sau tạo, nên phải xác minh mô hình tổ chức từ trước.

**Không dùng quyền admin để kiểm chứng bằng cách thử xóa backup thật.** Kiểm tra qua cấu hình retention, IAM, audit logs, API dry-run/permission test phù hợp và môi trường sandbox. Khi chuẩn bị thay đổi retention hay khóa vĩnh viễn, cần change approval vì có lựa chọn không thể đảo ngược.

### Service agent của backup vault

Mỗi backup vault có một **service agent riêng** để thực hiện một số tác vụ thay mặt dịch vụ. Ví dụ để vault ở project B bảo vệ Compute Engine VM ở project A, cần cấp cho vault service agent quyền **Backup and DR Compute Engine Operator** (roles/backupdr.computeEngineOperator) trên project A. Khi restore VM vào project C, cấp role tương ứng cho service agent trên project C theo hướng dẫn dịch vụ. Đây là quan hệ tin cậy có phạm vi, không phải lý do cấp Owner trên toàn organization.

~~~bash
# Ví dụ IAM tối thiểu theo tài liệu cho vault service agent truy cập VM source.
# Thay placeholder bằng service agent email lấy từ vault đã tạo.
gcloud projects add-iam-policy-binding APP_PROD_PROJECT \
  --member="serviceAccount:VAULT_SERVICE_AGENT_EMAIL" \
  --role="roles/backupdr.computeEngineOperator"

# Cho phép restore Compute Engine sang project đích đã duyệt.
gcloud projects add-iam-policy-binding ISOLATED_RESTORE_PROJECT \
  --member="serviceAccount:VAULT_SERVICE_AGENT_EMAIL" \
  --role="roles/backupdr.computeEngineOperator"
~~~

Đây là lệnh **minh họa để review**, không chạy trước khi security phê duyệt. Quyền của vault service agent, quyền người tạo backup plan và quyền người restore là những thứ **khác nhau**. Với Cloud SQL, Filestore, AlloyDB hay appliance-managed workloads, kiểm tra ma trận quyền theo loại resource; không dùng cùng role Compute Engine cho tất cả.

## 6. Backup for GKE: backup và restore thực sự xuyên project

**Backup for GKE** có tính năng cross-project backup/restore (GA từ tháng 8/2025): cluster nguồn ở project A, backup plan và backup ở project B, cluster restore ở project C. Đây là tính năng **khác** Backup and DR backup vault, dù chúng đều phục vụ recovery và separation of duties.

Backup for GKE bảo vệ **Kubernetes resource configuration** và có thể bảo vệ **persistent volume data** theo backup plan. Không mặc định bảo vệ database bên ngoài cluster (như Cloud SQL), registry image, external secret store, DNS, OAuth provider hoặc toàn bộ tài nguyên VPC. Với một ứng dụng Spring Boot, cluster restore thành công nhưng Cloud SQL chưa sẵn sàng vẫn chưa được coi là phục hồi nghiệp vụ.

### Quan hệ giữa các project và resource

| Resource | Nơi tạo | Vai trò |
|---|---|---|
| GKE source cluster | Project A | Workload cần backup |
| Backup channel | Project A, cùng region với cluster | Cho phép chuyển backup tới project B |
| Backup plan và Backup resources | Project B | Lịch backup, dữ liệu backup và IAM độc lập khỏi cluster |
| Restore channel | Project B, cùng project/region với backup | Chỉ định project C được phép nhận restore |
| Restore plan/Restore resources | Project C | Quy tắc khôi phục Kubernetes resources/PVC vào cluster C |
| GKE restore cluster | Project C | Môi trường thử phục hồi hoặc DR |

Đây là đường quản trị đáng ưu tiên khi cần tách **vòng đời backup khỏi project cluster**, thay vì chỉ xuất các YAML manifest từ một CI job. Trước khi cấu hình, enable đúng API tại các project, bật Backup for GKE add-on trên các cluster cần thiết, và xác minh service agents có thể làm việc xuyên project.

### Ví dụ tạo backup channel

Theo tài liệu Backup for GKE, tạo backup channel trong project chứa cluster, cùng region với cluster:

~~~bash
# PROJECT_B_NUMBER là numeric project number, KHÔNG phải project ID.
gcloud beta container backup-restore backup-channels create orders-backup-channel \
  --project=APP_PROD_PROJECT \
  --location=asia-southeast1 \
  --destination-project=projects/PROJECT_B_NUMBER
~~~

Sau đó tạo **backup plan trong project B** qua Cloud Console, chọn cấu hình cross-project backups, chỉ định source cluster ở project A và backup channel tương ứng. Xác định scope namespace/PVC, tần suất, retention và nơi lưu trước khi bật. Không tạo backup plan mới trực tiếp trong A nếu mục tiêu là tách độc lập dữ liệu trong B.

### Cross-project restore

Khi restore từ backup ở B sang cluster ở C, tạo **restore channel tại project B** và **restore plan tại project C**. Ví dụ:

~~~bash
gcloud beta container backup-restore restore-channels create orders-restore-channel \
  --project=BACKUP_SECURITY_PROJECT \
  --location=BACKUP_REGION \
  --destination-project=projects/PROJECT_C_NUMBER
~~~

Người quản trị restore project cần tạo restore plan dùng backup plan nằm ở B và cluster đích tại C, thiết lập conflict policy cho namespaced và cluster-scoped resources, cũng như volume data restore policy. **Restore có thể thay thế tài nguyên đang tồn tại**, vì vậy sử dụng cluster thử nghiệm tách biệt trước, kiểm tra namespace transformations và trạng thái PVC. Nếu GKE version giữa source/destination khác nhau, phải kiểm tra giới hạn version skew của Backup for GKE.

### Phân tách IAM/service agents cho GKE

- Người quản lý lịch backup cần quyền theo **Backup for GKE Backup Admin** (roles/gkebackup.backupAdmin) hoặc custom role phù hợp trên đúng project/resource.
- Người quản lý restore chỉ cần quyền để lập restore plan và khôi phục vào project C; không cấp quyền vô hạn trên B.
- Service agent của Backup for GKE dùng các principal Google-managed riêng. Tài liệu cross-project backup yêu cầu các binding giữa project A và B, bao gồm **roles/gkebackup.serviceAgent** tại phía cluster cho service agent của backup project và **roles/gkebackup.crossProjectServiceAgent** tại backup project cho principal GKE robot của source project.
- Cross-project restore cần IAM cấp cho principal liên quan giữa B/C và restore channel. Phải **lấy project number chính xác** vì service agent email thường dùng project number, không phải project ID.
- Không cấp roles/gkebackup.serviceAgent cho user thường; service agent roles được thiết kế cho principal dịch vụ.

Chỉ cấu hình theo đúng bước và role ở tài liệu chính thức của phiên bản dịch vụ, không tự đoán service agent email. Sự khác biệt project ID và project number là lỗi rất thường gặp, khiến backup channel tạo được nhưng backup/restore thực tế trả 403.

### Những giới hạn cần đưa vào runbook

- Không thể chuyển các backup plans hoặc restore plans **đã có** sang chế độ cross-project bằng một thao tác sửa đơn giản; cần tạo cấu hình mới theo hướng dẫn.
- Backup for GKE chỉ là một thành phần của chiến lược: Cloud SQL bên ngoài cluster và object storage cần luồng bảo vệ riêng.
- Dữ liệu được backup theo plan có thể bao gồm Kubernetes Secrets và resource manifest; hãy kiểm tra cách mã hóa, IAM, khả năng truy cập nội dung và retention.
- Khôi phục một Deployment cần image còn tồn tại ở Artifact Registry và runtime identity được cấp quyền; GKE backup không thay thế khôi phục registry/secret/config dependencies.

## 7. Cloud SQL: nguồn trong project A, backup/export ở project B

Cloud SQL có automated backups và PITR theo engine/edition/cấu hình; đó là phương tiện khôi phục database gắn với dịch vụ. Khi muốn bảo vệ độc lập ở project khác, cần xem **Backup and DR** có hỗ trợ loại Cloud SQL instance và cấu hình backup plan cross-project mong muốn, hoặc **xuất bản dữ liệu có kiểm soát sang Cloud Storage bucket thuộc project B**.

### Export không phải PITR

Ví dụ export SQL/CSV hoặc logical dump ra bucket project B có thể giúp giữ một bản sao độc lập và khôi phục vào database mới. Tuy nhiên:

- Một export logic thường là **ảnh chụp dữ liệu theo thời điểm**, không tự bao gồm transaction logs để khôi phục đến một thời điểm bất kỳ.
- Giới hạn schema, stored routines, triggers, users/grants và extensions phụ thuộc engine/loại export.
- Nếu export không hỗ trợ snapshot consistency theo nhu cầu giao dịch, cần chọn cơ chế phù hợp hoặc tạm dừng ghi khi cần; kiểm chứng thay vì giả định.
- Với DB lớn, export và import có thể kéo dài, làm RTO vượt mức yêu cầu.
- Backup/export chứa dữ liệu nhạy cảm; quyền tải file để restore có thể tương đương quyền đọc toàn database.

### IAM ví dụ cho export sang bucket project khác

Cloud SQL instance có **service account do dịch vụ quản lý** thực hiện thao tác với Cloud Storage. Đối với export sang bucket trong B, tài liệu troubleshooting chỉ rõ principal này cần ít nhất **roles/storage.objectCreator** ở bucket để tạo object export; nếu import hoặc cần đọc/ghi rộng hơn, quyền cần thay đổi theo operation và engine. Người dùng khởi tạo export cũng cần quyền Cloud SQL export trên instance.

~~~bash
# Cho service account của Cloud SQL instance quyền tạo object trong bucket B.
# CLOUD_SQL_INSTANCE_SA lấy từ Cloud SQL instance details, không tự đoán.
gcloud storage buckets add-iam-policy-binding gs://org-orders-db-backup \
  --member="serviceAccount:CLOUD_SQL_INSTANCE_SA" \
  --role="roles/storage.objectCreator"

# Ví dụ PostgreSQL logical export đến bucket nằm trong project B.
# Cú pháp/flags phải được kiểm tra theo engine/version khi chạy thật.
gcloud sql export sql orders-pg \
  gs://org-orders-db-backup/orders/2026-11-19/orders.sql.gz \
  --database=orders \
  --project=APP_PROD_PROJECT
~~~

Lệnh mang tính minh họa. Chỉ có **objectCreator** không cho principal liệt kê/tải/xóa object hiện có; vẫn cần bucket IAM, retention, monitoring và quy trình loại bỏ các file lỗi. Đừng cấp **roles/storage.admin** cho service account Cloud SQL chỉ để thao tác export.

Một bản export hoạt động không đồng nghĩa có thể restore thành công. Runbook phải tạo Cloud SQL instance ở C, cấu hình private networking/IAM, chuẩn bị version/extension, cấp quyền **đọc** object backup cho principal khôi phục, thực hiện import, kiểm tra row counts/checksums hoặc business invariants và chạy smoke test của Spring Boot service.

### Tính nhất quán nhiều database

Nếu orders API ghi Cloud SQL và đồng thời phát Pub/Sub event, export DB không tự tạo một điểm khôi phục đồng bộ với Pub/Sub backlog. Cần đánh dấu checkpoint, outbox, consumer offset, timestamp, hoặc cơ chế tái phát sự kiện an toàn. Một snapshot nhất quán ở cấp disk cũng không phải một distributed transaction xuyên database và queue.

## 8. Compute Engine: snapshot schedules có giới hạn project

**Scheduled snapshots** của Compute Engine được quản lý bởi resource policy **trong chính project chứa disk**. Tài liệu Google Cloud nêu rõ snapshot schedule không dùng chéo project/organization. Có thể chọn location lưu snapshot theo khả năng của dịch vụ, nhưng **khác location không đồng nghĩa khác ranh giới quản trị IAM**.

Do đó, nếu yêu cầu là “backup không thể bị operator của project A xóa”, đừng chỉ đưa snapshot schedule vào project A rồi gọi nó là cross-project backup. Hãy đánh giá **Backup and DR backup vault ở project B** cho Compute Engine workload được hỗ trợ, với vault service agent có quyền hạn thích hợp tại A.

Trước khi dùng snapshot để backup application:

- Xác nhận disk scope, snapshot type, encryption key và location.
- Với filesystem/database, kiểm tra **application consistency**: guest flush, VSS hoặc quiesce theo workload, không chỉ crash-consistent snapshot.
- Snapshot schedule có retention, nhưng retention của schedule không mặc nhiên là **immutable WORM**.
- Đặt cảnh báo khi lịch snapshot thất bại và diễn tập tạo disk/VM từ snapshot.
- Sau khi restore, xác minh boot, network, firewall, IAM và application transaction recovery.

## 9. Cloud Storage project B: retention, versioning và chống ghi đè

Khi dùng Cloud Storage làm backup destination hoặc kho archive riêng, cấu hình bảo vệ cần có **nhiều lớp**:

| Tính năng | Tác dụng | Không làm được điều gì? |
|---|---|---|
| Uniform bucket-level access | Quản lý quyền chủ yếu qua bucket IAM | Không tự khiến object immutable |
| Public Access Prevention | Ngăn public exposure qua quyền công khai | Không ngăn người quản trị nội bộ có quyền rộng |
| Object Versioning | Giữ các generation khi object thay đổi/xóa theo cơ chế versioning | Không tự cấm xóa vĩnh viễn generation cũ |
| Soft delete | Cho phép phục hồi object đã xóa trong retention window | Không tương đương retention lock không thể giảm |
| Bucket retention policy | Giữ object tối thiểu trong khoảng đã đặt | Nếu chưa lock, người có quyền có thể thay đổi policy |
| Bucket Lock | Khóa retention policy **vĩnh viễn** để không thể giảm/xóa | Không làm object bất tử sau khi hết retention |
| Object Retention Lock | Có thể khóa retention trên từng object | Cần bật hỗ trợ và tuân thủ đặc tính không thể đảo ngược |
| CMEK | Tổ chức kiểm soát khóa dùng mã hóa dữ liệu | Không giúp restore nếu key version bị mất hoặc không còn quyền decrypt |

**Bucket Lock là thao tác không thể đảo ngược.** Khi đã khóa, không thể loại bỏ hoặc giảm retention period; có thể tăng theo quy tắc dịch vụ. Google Cloud cũng áp dụng project lien khi khóa bucket retention policy. Vì vậy phải kiểm tra trách nhiệm pháp lý, chi phí retention và thời gian cần giữ trước khi thực hiện.

### IAM ghi backup theo nguyên tắc append-only

Đối với một exporter đơn giản, có thể cho service account ở project A quyền **roles/storage.objectCreator** **trên đúng bucket B**, không cấp Object Viewer, Object Admin hoặc Storage Admin. Nó có thể tạo object mới mà không đọc/xóa những object đã tồn tại. Tuy nhiên:

- Một tài khoản tạo object không nên là tài khoản cấp phát IAM, đặt retention, thay đổi KMS hoặc quản lý project B.
- Quyền objectCreator chỉ phù hợp khi phần mềm backup **không cần liệt kê/đọc/ghi đè** object cũ; một số backup tool cần quyền khác để tạo catalog hoặc incremental chain.
- Dùng tên object độc nhất theo workload/time/backup ID để tránh collision; nếu có thể, dùng request precondition như generation-match=0 cho API upload.
- IAM chỉ giới hạn hành động của principal; **retention lock** mới bổ sung bảo đảm không xóa trước hạn ngay cả với operator có quyền rộng phù hợp.
- Theo dõi object age, checksum, creation timestamp, lifecycle và restore ability; tránh giả định upload success đồng nghĩa dữ liệu có thể sử dụng.

Nếu data residency yêu cầu chỉ giữ backup trong một khu vực, chọn bucket location/replication phù hợp. Một bucket ở project B không nhất thiết nằm ở region B; nếu mục tiêu bao gồm cả regional DR, phải thiết kế thêm location/failure domain.

### Ví dụ bucket policy ở dạng cấu hình minh họa

~~~yaml
backup_repository:
  owning_project: backup-security
  bucket: org-orders-db-backup
  storage_location: approved-region
  uniform_bucket_level_access: true
  public_access_prevention: enforced
  object_versioning: enabled
  retention:
    minimum_days: 35
    lock_requires_security_approval: true
  writers:
    - cloud-sql-instance-service-account
  readers:
    - time-bound-restore-service-account
  forbidden_for_app_team:
    - delete_backup
    - update_bucket_iam
    - reduce_retention
    - destroy_kms_key
~~~

Đây là **mẫu tài liệu thiết kế**, không phải manifest được Google Cloud API nhận trực tiếp. Quyết định lock thực tế phải thực hiện bằng công cụ/quy trình được security phê duyệt. Đừng áp dụng policy test khóa vĩnh viễn lên bucket dùng chung khi chưa thống nhất chi phí và lifecycle.

## 10. KMS/CMEK: backup không thể restore nếu mất key

Trong chiến lược bảo vệ chống ransomware, mã hóa có hai mặt. Nó bảo vệ backup khỏi việc bị đọc trái phép, nhưng **hủy hoặc vô hiệu hóa nhầm key version** cũng có thể làm backup không thể giải mã. Với dữ liệu được mã hóa bằng CMEK, phải quản lý vòng đời key song song với retention của bản backup.

Thiết kế cần ghi rõ:

1. **Ai sở hữu key?** Nên có key custodian thuộc nhóm security, khác với team triển khai app và backup operator.
2. **Key ở đâu?** Location của key, bucket và dịch vụ backup phải tương thích theo yêu cầu sản phẩm.
3. **Ai encrypt/decrypt?** Cấp quyền đúng **service agent** của dịch vụ thực hiện backup/restore, không cấp Cloud KMS Admin cho application.
4. **Nếu key bị disable/destroy thì sao?** Có runbook phục hồi key version/restore permissions theo đặc tính của Cloud KMS, nhưng không dựa vào việc có thể khôi phục key đã bị hủy vĩnh viễn.
5. **Retention dài hơn vòng đời key?** Không phá hủy key version còn cần để đọc một bản backup đang được giữ theo policy.
6. **Có break-glass access không?** Phải được logging, kiểm soát thời gian và phê duyệt độc lập.

Không xem **CMEK là một bản backup thứ hai**. Một key bị chiếm quyền hoặc bị thu hồi có thể làm mọi bản mã hóa phụ thuộc cùng key không thể đọc. Nên đánh giá việc dùng key riêng cho domain backup, phân quyền độc lập, giám sát thao tác disable/destroy và backup catalog lưu key reference cần thiết.

### Phân biệt danh tính

Service account của CI/CD, service agent của Backup and DR vault, Backup for GKE agents, Cloud SQL instance service account và Cloud Storage service agent có **vai trò khác nhau**. Đừng sử dụng cùng một principal có Editor/Owner trên A, B, C và key project. Trong bảng quyền, ghi đầy đủ principal email/resource ID, chính xác IAM role, cấp tại project/bucket/key nào, lý do cấp và điều kiện thu hồi.

## 11. Ma trận quyền tối thiểu và quy trình phê duyệt

Một mô hình separation of duties phải kiểm soát được cả **tạo backup**, **xóa backup**, **đọc dữ liệu backup** và **restore đè dữ liệu production**.

| Hành động | Project/resource | Người hoặc principal hợp lệ | Kiểm soát bổ sung |
|---|---|---|---|
| Deploy ứng dụng | Project A | CI/app operator | Không có quyền sửa vault B |
| Tạo bản backup tự động | A → B | Service agent/source backup runner | Chỉ quyền cần thiết tại A/B; không cấp Owner |
| Tạo hoặc đổi backup plan | Project B | Backup policy admin | PR/change approval; cảnh báo khi thay lịch |
| Thay retention/vault settings | Project B | Vault custodian | Multi-party approval, PAM, audit |
| Đọc bản backup nhạy cảm | Project B | Restore service account được duyệt | JIT access, data handling, không tải về laptop |
| Tạo restore cluster/VM/database | Project C | Recovery operator | Separate budget/quota/network và logs |
| Restore vào production | Project A | DR lead + restore operator sau phê duyệt | Quy trình change/incident, checkpoint, kiểm tra consistency |
| Quản lý KMS key | Key/security project | Key custodian | Tách quyền decrypt và quyền quản trị key |
| Review logs và compliance | Audit/backup project | Auditor | Read-only, không quyền đọc payload khi không cần |
| Xóa project/vault hoặc tháo lien | Governance/security scope | Người được ủy quyền đặc biệt | Break-glass, nhiều người xác nhận, audit độc lập |

Các role cụ thể phụ thuộc loại dịch vụ; **không có một role backup operator chung** áp dụng chính xác cho mọi GCP workload. Ví dụ roles/backupdr.backupvaultAdmin là role mạnh để quản lý vault; roles/gkebackup.backupAdmin quản lý backup GKE; roles/backupdr.computeEngineOperator dành cho backup vault service agent tương tác Compute Engine. Nên dùng predefined roles làm cơ sở hiểu permission, sau đó thu hẹp phạm vi hoặc custom roles khi phù hợp và được hỗ trợ.

### Những đường cấp quyền tiềm ẩn

- Quyền **iam.serviceAccountTokenCreator** hoặc serviceAccountUser có thể tạo đường impersonate principal đang được cấp quyền truy cập backup; cần kiểm tra effective permissions.
- Quyền **resourcemanager.projects.setIamPolicy** ở project B có thể cho phép người dùng cấp thêm quyền rộng cho chính họ, trừ khi có kiểm soát governance phù hợp.
- Quyền quản lý group membership của một IAM group backup-admin cũng là quyền có ảnh hưởng đến backup.
- Quyền sửa organization policies, security perimeter hoặc tháo project liens có thể mở đường xóa/vô hiệu hóa backup.
- Quyền ghi thay đổi CI/IaC ở project B có thể làm thay đổi retention policy hoặc backup schedule ngay cả khi người đó không đăng nhập console.

Vì vậy security review cần xét **toàn bộ đường đi quyền** qua organization/folder/project, service account, repository, CI runner và KMS, không chỉ một danh sách role gán trực tiếp.

## 12. Giảm rủi ro ransomware và xóa dữ liệu ác ý

Ransomware trên cloud không nhất thiết mã hóa file bằng phần mềm bên trong VM; một attacker có thể dùng API để xóa snapshot, hạ backup retention, sửa backup plan, ngắt logging, thu hồi key hoặc tạo backup sai nội dung sau khi ứng dụng đã bị chiếm quyền.

Thiết kế phòng thủ theo lớp:

1. **Prevent:** IAM ít quyền nhất, MFA và federation, không dùng user-managed service account keys dài hạn nếu có phương án an toàn hơn, giới hạn IAM changes và delete operations.
2. **Isolate:** backup project độc lập với application project, khác người quản trị, khác CI credentials và phù hợp data residency.
3. **Immutability:** backup vault enforced retention hoặc Bucket Lock/object retention phù hợp; kiểm soát thay đổi bất khả đảo ngược.
4. **Protect project/key:** project lien, PAM, Cloud KMS IAM, cảnh báo disable/destroy key, giới hạn ai được tháo protection.
5. **Detect:** audit logs và alerts cho thay đổi plan, quyền backup, tắt logging, xóa backup, xóa project, restore bất thường.
6. **Recover:** chuẩn bị project C, runbook, quyền tạm thời, các điểm khôi phục **trước thời điểm xâm nhập**, kiểm tra dữ liệu sạch.
7. **Prove:** restore drill và đo kiểm integrity, thời gian phục hồi cùng trạng thái secret/identity sau restore.

**Một backup mới nhất chưa chắc là backup sạch.** Malware hoặc sai logic có thể đã thay đổi database nhiều ngày trước khi phát hiện. Cần retention đủ dài để có các recovery points trước thời điểm compromise và phương pháp tìm bản sạch; có thể phải cô lập bản restore khỏi production để điều tra trước khi kết nối lại.

### Không tuyệt đối hóa “immutable”

Immutability có ý nghĩa trong phạm vi dịch vụ và cấu hình đã chọn. Nếu backup plan không chạy, key không thể giải mã, backup bị tạo từ dữ liệu hỏng, project nguồn mất IAM hoặc org bị chiếm quyền, việc có immutable backup vẫn có thể không đáp ứng RTO. Chỉ công bố “recoverable” sau khi **thử restore đầy đủ và kiểm tra nghiệp vụ**.

## 13. Tính nhất quán ứng dụng và thứ tự khôi phục

Một ứng dụng Spring Boot có thể phụ thuộc GKE, Cloud SQL, Secret Manager, Artifact Registry, Pub/Sub, Cloud Storage và hệ thống xác thực ngoài GCP. Khi chỉ restore Kubernetes Deployment và PersistentVolume nhưng bỏ sót database/secret, service có thể báo Ready nhưng không xử lý được order.

### Dependency order tham khảo

~~~mermaid
flowchart TB
  ID[IAM, KMS, secret và identity] --> NET[VPC, DNS, firewall và private connectivity]
  NET --> DATA[Restore Cloud SQL / transactional data]
  DATA --> OBJ[Object storage và event checkpoint]
  OBJ --> APP[GKE/VM runtime và image]
  APP --> CHECK[Smoke test + integrity check]
  CHECK --> GO[Chuyển traffic có kiểm soát]
~~~

Thứ tự có thể khác theo workload nhưng phải được ghi trong runbook. Vấn đề thường gặp:

- **Database version/extension:** DB đích cần tương thích với backup. Một backup logic có thể không chứa role/grant hoặc extension giống nguồn.
- **Identity và secret:** app cần đúng danh tính runtime và version secret; key cũ cần tồn tại để giải mã dữ liệu.
- **Kubernetes resources:** Backup for GKE khôi phục manifests và PVC theo plan; external DB, image và firewall không tự được khôi phục.
- **Distributed workflows:** outbox, Pub/Sub subscription/backlog, idempotency state và cron scheduler có thể không cùng một checkpoint.
- **Data re-exposure:** restore sandbox không được kết nối tới payment production hay gửi email thật trước khi kiểm thử.
- **Object dependencies:** file hóa đơn hoặc ảnh liên quan đến record DB phải còn tồn tại ở recovery point phù hợp.

Khi restore bản backup từ trước sự cố, cần quyết định xử lý những giao dịch xảy ra sau recovery point. RPO được chấp nhận về mặt kỹ thuật chưa nói lên cách hoàn tiền, thông báo khách hàng hoặc tái phát event; business owner cần phê duyệt reconciliation.

## 14. Restore drill trong project C: kiểm thử mà không làm hỏng production

Đặt lịch **diễn tập khôi phục định kỳ** với project C độc lập, network cách ly và data test/sanitization phù hợp. Với dữ liệu khách hàng nhạy cảm, quyền đọc backup và khả năng truy cập sau restore phải được kiểm soát giống production; sandbox không phải môi trường được phép bỏ qua phân loại dữ liệu.

### Trước diễn tập

1. Chọn workload mẫu, backup ID, thời điểm tạo, region/project và checksum/catalog metadata được hỗ trợ.
2. Lấy change approval, chọn recovery point dự kiến và tiêu chí RTO/RPO.
3. Kiểm tra project C có quota, API, IAM, service agents, KMS decrypt, VPC, DNS, image, cluster/VM/database version.
4. Cấp quyền restore **tạm thời** cho service account; không cấp project Owner cho người triển khai.
5. Cấm egress đến những integration production không cần thiết; gắn nhãn tài nguyên, budget và lịch xóa thử nghiệm.

### Trong diễn tập

1. Restore vào namespace/cluster/VM/database mới, không ghi đè nguồn.
2. Xác nhận manifest/PVC hoặc disk/DB có thể đọc, phiên bản ứng dụng tương thích.
3. Đối chiếu row counts, hashes/checksums, business transaction IDs, dữ liệu quan trọng và quyền truy cập.
4. Chạy smoke/integration tests: login test, tạo đơn giả lập, đọc hóa đơn, kiểm tra queue (không publish event thật ra production).
5. Đo thời gian tạo hạ tầng, restore bytes, restart app, kiểm tra consistency và đạt trạng thái phục vụ.
6. Thu logs bằng chứng, đánh giá RPO từ checkpoint cuối đã xác nhận và RTO từ mốc sự cố giả định.

### Sau diễn tập

Thu hồi quyền restore/JIT, đóng network tạm, dọn resource theo retention, cập nhật runbook, ghi chủ sở hữu action item. Không xóa **backup production** chỉ vì xóa môi trường test. Với lock/retention, tránh tạo dữ liệu thử nghiệm được giữ vĩnh viễn ngoài ý muốn.

### Các tiêu chí nghiệm thu

| Kiểm tra | Điều kiện PASS mẫu |
|---|---|
| Backup catalog | Tìm được bản backup phù hợp cùng timestamp và source identity |
| Permissions | Chỉ người/SA trong approved role thực hiện restore; app operator không xóa backup |
| KMS | Restore đọc được dữ liệu mà không cần cấp quyền quản trị key |
| Integrity | Dữ liệu/row count/transaction IDs khớp checkpoint kỳ vọng |
| Application | API và job quan trọng qua smoke tests, không kết nối production ngoài dự kiến |
| RTO/RPO | Hai số liệu đo thực tế nằm trong mục tiêu đã được phê duyệt |
| Audit | Có log cho việc thay role, truy cập backup, thao tác restore và kết quả |
| Cleanup | Thu hồi quyền và xóa resource test đúng lịch; không chạm retention của backup thật |

Điều kiện PASS cần sửa cho từng nghiệp vụ. Với một hệ thống payment, kiểm tra “HTTP 200” không đủ: phải kiểm tra ledger, idempotency và phản ứng của API khi bản restore thiếu một số event sau recovery point.

## 15. Monitoring, audit và cảnh báo

Backup chỉ đáng tin khi được theo dõi liên tục. Một job “SUCCESS” vẫn có thể thiếu volume, bỏ qua namespace hoặc tạo bản backup lỗi logic. Xây dashboard theo **workload × source project × backup project × recovery point × policy**.

| Tín hiệu | Ý nghĩa hành động |
|---|---|
 Backup job success/failure | Cảnh báo nếu nhiều lần liên tiếp thất bại hoặc bị bỏ lịch |
 Last successful backup age | Phát hiện RPO thực tế vượt mức, kể cả khi schedule vẫn tồn tại |
 Protected asset coverage | Tìm VM/database/namespace/PVC chưa được bảo vệ |
 Backup storage growth và retention | Kiểm soát chi phí, tránh vô tình giữ dữ liệu quá lâu |
 Changes to vault/backup plan/retention | Phát hiện thay đổi chính sách bất thường |
 IAM/service-agent changes | Cảnh báo thêm Owner, cấp quyền xóa hoặc cross-project access lạ |
 KMS key disable/destroy/permission errors | Phát hiện nguy cơ không thể giải mã khi cần restore |
 Cloud Storage deletion/access attempts | Điều tra xóa/tải backup, hoạt động ransomware |
 Restore operation frequency | Cảnh báo restore trái phép hoặc bất thường |
 Restore drill success và RTO/RPO đo được | Đánh giá khả năng phục hồi thực tế thay vì chỉ tạo bản sao |

Cloud Audit Logs cần được cấu hình theo loại hoạt động và service. Admin Activity logs hỗ trợ theo dõi nhiều thao tác quản trị; **Data Access logs có thể cần bật riêng và có chi phí**, đặc biệt khi muốn giám sát đọc backup/object. Nên chuyển logs bảo mật đến project logging/audit độc lập có retention và IAM riêng. Với môi trường nhiều project, dùng Log Router sink ở cấp folder/organization nếu phù hợp; bảo đảm sink writer identity có quyền ghi đúng destination.

Không ghi nội dung backup, credential, database export payload hoặc secret vào log/alert chỉ để tiện vận hành. Dashboard cho backup operators nên xem metadata và trạng thái; payload restore chỉ được truy cập trong quy trình đã phê duyệt.

## 16. Chính sách retention và chi phí

Tách chiến lược **khôi phục vận hành** khỏi **lưu trữ pháp lý**. RPO ngắn có thể cần backup thường xuyên và PITR; giữ dữ liệu bảy năm có thể cần archive với chính sách immutability và dữ liệu hóa đơn/hợp đồng được bảo vệ đặc biệt.

| Lớp backup | Mục đích | Chính sách ví dụ để thảo luận |
|---|---|---|
| Ngắn hạn | Khôi phục lỗi triển khai, thao tác xóa nhầm | Các recovery points thường xuyên, giữ theo RPO |
| Trung hạn | Phát hiện dữ liệu bị hỏng/mã hóa nhiều ngày trước | Daily/weekly generations đủ dài để điều tra |
| Dài hạn | Compliance, audit, lịch sử dữ liệu | Monthly/yearly có phân loại và retention riêng |
| Restore test | Kiểm chứng RTO/RPO | Bản thử ngắn hạn trong project C, tự động cleanup |

Chi phí phải gồm: storage của backups và noncurrent object versions, vaulted backup retention, backup/restore operations, compute tạm khi diễn tập, network transfer giữa region, CMEK/KMS, logging, monitoring và egress. **Enforced retention có thể buộc trả tiền cho dữ liệu đến hết thời hạn** ngay cả khi workload bị xóa; đây là đặc tính của thiết kế tuân thủ, không phải một lỗi billing.

Backup for GKE cross-project có mô hình thanh toán liên quan tới project backup; chi phí data transfer có thể phát sinh theo vị trí cluster, backup và restore. Trước khi triển khai, kiểm tra giá hiện hành theo region, loại volume và số GB, không đặt con số cố định trong kiến trúc.

### Mẫu policy hồ sơ workload

~~~yaml
workload_id: orders-prod
source_project: app-prod
backup_project: backup-security
restore_project: isolated-restore
business_owner: commerce
data_owner: finance
classification: confidential
objectives:
  rpo_minutes: 15
  rto_minutes: 120
recovery_dependencies:
  - cloud-sql
  - gke
  - secret-manager
  - artifact-registry
  - dns-networking
backup_mechanisms:
  database: backup-and-dr-or-managed-backup-plus-independent-export
  k8s: backup-for-gke-cross-project
  objects: cross-project-storage-with-retention
restore_test:
  cadence: quarterly
  destination: isolated-restore
approvals:
  policy_change: backup-admin-plus-security
  production_restore: incident-commander-plus-data-owner
~~~

Đây là **workload backup passport** do doanh nghiệp tự thiết kế, không phải resource manifest của Google Cloud. Các giá trị RPO/RTO, cadence và retention phải được owner duyệt, không phải default của sản phẩm.

## 17. Những sai lầm thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Cùng một nhóm có Owner cả A, B, C | Ranh giới project chỉ còn mang tính hình thức | Tách IAM theo nhiệm vụ, approval và rà soát quyền kế thừa |
| Đặt snapshot schedule trong project A rồi gọi là cross-project backup | Snapshot vẫn thuộc cùng phạm vi quản trị nguồn | Dùng Backup and DR vault ở B hoặc giải pháp hỗ trợ tách project |
| Coi cross-region replica là bản backup chống ransomware | Xóa/hỏng dữ liệu logic có thể replicate | Giữ recovery points độc lập, immutable khi cần |
| Bật versioning nhưng không có retention lock | Người có quyền vẫn có thể xóa generation cũ | Dùng retention policy/Bucket Lock theo yêu cầu và kiểm thử |
| Cấp Storage Admin cho application exporter | Bản backup có thể bị tải, sửa/xóa ngoài mục tiêu | Chỉ cấp objectCreator hoặc quyền phù hợp với tool ở bucket B |
| Cho team app tự giảm backup retention | Có thể vô hiệu hóa khả năng khôi phục trước khi tấn công | Tách backup policy admin và approval |
| Khóa retention quá dài mà chưa review | Chi phí không thể hủy và nguy cơ không đáp ứng chính sách dữ liệu | Thẩm định pháp lý, tài chính, dữ liệu và thử trên sandbox |
| Dùng CMEK nhưng không bảo vệ key | Không thể decrypt backup khi key bị hủy/disable | Phân tách key custodians và theo dõi vòng đời key |
| Backup GKE nhưng bỏ Cloud SQL/Artifact Registry | Restore workload vẫn không chạy được | Lập dependency passport và thử restore end-to-end |
| Sao lưu DB và queue ở thời điểm khác nhau không có checkpoint | Có thể xử lý lại/thiếu event | Outbox, idempotency, reconciliation |
| Restore drill dùng mạng mở đến production | Gửi email, thanh toán, webhook hoặc ghi dữ liệu thật từ sandbox | Isolated network và mock integration |
| Chỉ đo backup success mà không thử restore | Không biết backup hỏng hoặc thiếu permission | Restore drill, integrity tests và RTO/RPO thực tế |
| Giữ mọi bản sao trong một region | Project nguồn bị tách nhưng vẫn chịu lỗi toàn region | Tính thêm địa lý/location theo RTO, RPO và residency |
| Quên audit IAM/service agent | Không phát hiện privilege escalation hoặc thay đổi lịch | Log sink, alert và periodic access review |

## 18. Tình huống: bảo vệ nền tảng đặt hàng đa project

Một hệ thống đặt hàng Spring Boot gồm:

- Project A: GKE cluster vận hành API/worker, Cloud SQL PostgreSQL, kết nối Pub/Sub, một số Cloud Storage objects.
- Project B: backup-security với Backup for GKE, Backup and DR vault, bucket chứa logical DB export, dashboard và backup policy.
- Project C: isolated-restore có GKE cluster, database mới và VPC không thể gửi giao dịch đến dịch vụ thanh toán thật.
- Security/key project: quản lý key và policy, có người duyệt độc lập.

Giả định business đặt mục tiêu RPO 15 phút cho đơn hàng và RTO 2 giờ trong tình huống xóa nhầm; đồng thời cần giữ khả năng khôi phục về thời điểm trước cuộc tấn công ransomware được phát hiện muộn.

### Quyết định kiến trúc

1. **GKE:** sử dụng Backup for GKE cross-project, backup plan ở B, backup channel ở A, restore channel từ B đến C; lựa chọn namespace/PVC thực sự quan trọng và loại trừ dữ liệu cache có thể tái tạo.
2. **Cloud SQL:** bật cơ chế managed backup/PITR được hỗ trợ và có thêm bản bảo vệ độc lập thông qua Backup and DR vault hoặc periodic export sang bucket B. Chứng minh từng cơ chế đáp ứng phần nào của RPO/RTO; không coi export hằng đêm là đủ cho RPO 15 phút.
3. **Bucket object:** sử dụng quyền xuất từ A có phạm vi bucket, naming duy nhất, retention phù hợp và policy để không operator của A xóa được backup.
4. **IAM:** CI ở A có quyền deploy; Backup administrator ở B tạo/chỉnh plan; restore operator ở C có quyền tạm thời; key custodian độc lập.
5. **Immutability:** chọn enforced retention hoặc Bucket Lock theo dịch vụ và đánh giá rủi ro thay đổi không thể đảo ngược.
6. **Monitoring:** theo dõi backup age, backup size bất thường, thất bại liên tục, IAM/retention changes, KMS activity và restore drill.
7. **Recovery:** test khôi phục GKE resources/PVC và Cloud SQL từ các recovery points tương ứng, khởi động app ở C với test credentials.

### Kịch bản thảm họa

Tài khoản CI ở A bị đánh cắp và kẻ tấn công xóa Deployment, xóa một bảng PostgreSQL rồi thử xóa tất cả backup.

**Kỳ vọng:** người đó không thể quản lý vault/retention/backup bucket B; backup độc lập vẫn tồn tại, audit phát hiện thao tác IAM/data bất thường. Security khoanh vùng compromise và tắt credential bị lộ. Recovery team chọn recovery point sạch từ trước khi bảng bị xóa, restore vào C, chạy so khớp dữ liệu, xác minh order IDs và quyết định cách xử lý giao dịch xảy ra sau recovery point. Chỉ sau approval mới chuyển traffic hoặc import phục hồi production.

**Nếu thiếu quyền decrypt hoặc quota project C:** RTO có thể thất bại dù bản backup không bị xóa. Bởi vậy IAM/Key rotation drill và quota/capacity verification là phần bắt buộc của bài kiểm thử, không phải công việc có thể bỏ qua.

### Báo cáo nghiệm thu mẫu

| Chỉ số | Mục tiêu giả định | Cách chứng minh |
|---|---|---|
 Backup isolation | Operator A không thể xóa/đổi retention ở B | IAM effective review và kiểm thử quyền không phá hủy |
 Recovery point | Không vượt RPO nghiệp vụ | So khớp transaction ID, PITR timestamp, backup catalog |
 Service recovery | GKE/DB/API khôi phục trong RTO | Timestamp end-to-end từ DR declaration đến smoke test |
 Data correctness | Không thiếu/trùng order ngoài giới hạn đã duyệt | Consistency/invariant test, reconciliation |
 Compromised credential | Không thể truy cập backup payload hoặc key | Service account scope, audit và access review |
 Compliance | Retention và residency phù hợp | Security/legal sign-off, cấu hình storage/vault |

## 19. Bài tập thực hành trong sandbox

Thực hiện trên các **project sandbox** được cấp phép; không tạo khóa retention vĩnh viễn hoặc backup chứa dữ liệu khách hàng thật.

1. Tạo sơ đồ project A/B/C và tùy chọn key project; liệt kê tất cả principals có quyền rộng qua organization/folder.
2. Viết consistency và backup passport cho một ứng dụng Spring Boot với database và persistent volume.
3. Chọn một workload Compute Engine hoặc GKE có hỗ trợ, thiết kế backup vault hoặc Backup for GKE cross-project path.
4. Đối với GKE, xác định đúng vị trí backup channel, backup plan, restore channel và restore plan; lập IAM/service agent matrix, không tự đoán email.
5. Đối với Cloud SQL, thiết kế export sang bucket B với objectCreator và phương án restore độc lập. Giải thích vì sao logical export không tương đương PITR.
6. Cấu hình một bucket thử nghiệm có uniform bucket-level access, public access prevention, object versioning và retention **chưa lock**; đánh giá tác động nếu lock trước khi có approval.
7. Tạo một service account chỉ có quyền ghi backup; xác minh nó không được đọc/xóa object đã có bằng kiểm thử quyền hợp lệ.
8. Mô phỏng mất quyền decrypt trong kiểm thử **không phá hủy key thật** để quan sát thông báo lỗi và hoàn thiện runbook.
9. Restore workload vào project C và chạy smoke/integrity tests; đo RTO thực tế và dữ liệu có thể mất theo recovery point.
10. Xây cảnh báo khi backup quá tuổi RPO, IAM thay đổi hoặc restore chạy ngoài lịch. Ghi rõ người chịu trách nhiệm nhận cảnh báo.
11. Viết biên bản: kiến trúc đã đáp ứng mục tiêu nào, những dependency chưa bảo vệ, chi phí retention và hành động cải thiện.

Không dùng privileged access hay lệnh xóa backup trên production để chứng minh isolation; làm việc qua IAM policy review và sandbox. Sau diễn tập, thu hồi quyền và chỉ xóa tài nguyên tạm đúng theo policy.

## 20. Checklist trước khi phê duyệt chiến lược

- [ ] Tất cả workload và dữ liệu có business/data owner, phân loại và RPO/RTO rõ ràng.
- [ ] Phân biệt HA replica, snapshot, PITR, backup độc lập và archive.
- [ ] Ranh giới project A/B/C và đường tin cậy IAM được vẽ, có inventory service agents.
- [ ] Nhóm ứng dụng không có quyền giảm retention, xóa vault/bucket hoặc tự cấp quyền backup.
- [ ] Effective IAM qua folder/organization, service account impersonation và CI/CD đã được review.
- [ ] Backup and DR vault có loại resource hỗ trợ, location/access restriction/retention đúng yêu cầu.
- [ ] Backup for GKE cross-project có backup/restore channels, plan và service agent permissions phù hợp.
- [ ] Cloud SQL có managed backup/PITR hoặc chiến lược database backup độc lập được thử nghiệm.
- [ ] Compute snapshot schedule không bị nhận nhầm là giải pháp cross-project isolation.
- [ ] Cloud Storage bucket có scope IAM phù hợp, bảo vệ public access và retention cần thiết.
- [ ] Bucket Lock/enforced retention đã được security/legal/finance xem xét trước khi khóa.
- [ ] Backup và key có vòng đời tương thích; không phá hủy key version khi backup vẫn cần.
- [ ] Có project lien và quy trình bảo vệ/tháo lien đúng thẩm quyền khi dịch vụ áp dụng.
- [ ] Backup metadata, payload và audit logs được phân quyền khác nhau.
- [ ] Alert cho job thất bại, stale backup, IAM/KMS/retention changes và restore bất thường.
- [ ] Có isolated restore project với quota, VPC, identity, image và mock integrations.
- [ ] Restore drill định kỳ chứng minh RTO/RPO và tính nhất quán nghiệp vụ.
- [ ] Có runbook ransomware để chọn recovery point sạch và kiểm soát tái nhiễm.
- [ ] Chi phí bản sao, retention, network transfer, logging và test được dự toán.
- [ ] Đã kiểm chứng khả năng phục hồi project/region theo failure domains thực tế.

## 21. Kết luận

**Sao lưu xuyên project và phân tách quyền là chiến lược bảo vệ khả năng khôi phục, không chỉ là vị trí đặt file backup.** Project nguồn có thể bị lỗi hoặc bị chiếm quyền, nhưng không nên làm mất đồng thời các recovery points, policy retention, audit evidence và khóa giải mã. Trên Google Cloud, Backup and DR backup vault hỗ trợ quản trị tập trung với enforced retention; Backup for GKE hỗ trợ bảo vệ và restore giữa các project; Cloud SQL export, Compute Engine snapshots và Cloud Storage cung cấp những cơ chế bổ sung với giới hạn khác nhau. Muốn thiết kế hiệu quả, cần hiểu đúng từng sản phẩm, tách identity/service agent, có kiểm soát thay đổi IAM/KMS, chuẩn bị project restore độc lập và **thường xuyên chứng minh backup có thể khôi phục thành hệ thống đúng về mặt nghiệp vụ** trong RTO/RPO đã duyệt.

## Tài liệu tham khảo

- [Google Cloud Backup and DR — Backup vaults for immutable and indelible backups](https://docs.cloud.google.com/backup-disaster-recovery/docs/concepts/backup-vault)
- [Backup and DR — Create and manage a backup vault](https://docs.cloud.google.com/backup-disaster-recovery/docs/cloud-console/backup-vault-create)
- [Backup and DR — Backup plans](https://docs.cloud.google.com/backup-disaster-recovery/docs/concepts/backup-plan)
- [Backup for GKE — Overview](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/concepts/backup-for-gke)
- [Backup for GKE — Perform cross-project backups](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/cross-project-backups)
- [Backup for GKE — Perform cross-project restores](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/cross-project-restores)
- [Backup for GKE — Plan a set of restores](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/restore-plan)
- [Backup for GKE — Cross-project pricing](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/concepts/about-pricing)
- [Compute Engine — About snapshot schedules](https://docs.cloud.google.com/compute/docs/disks/about-snapshot-schedules)
- [Compute Engine — Create snapshot schedules](https://docs.cloud.google.com/compute/docs/disks/scheduled-snapshots)
- [Cloud SQL — Roles and permissions for import/export](https://docs.cloud.google.com/sql/docs/mysql/roles-and-permissions)
- [Cloud Storage — Bucket Lock](https://docs.cloud.google.com/storage/docs/bucket-lock)
- [Cloud Storage — Use and lock bucket retention policies](https://docs.cloud.google.com/storage/docs/using-bucket-lock)
- [Cloud Storage — Object Retention Lock](https://docs.cloud.google.com/storage/docs/using-object-lock)
- [Cloud Storage — Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
- [Cloud Storage — Public Access Prevention](https://docs.cloud.google.com/storage/docs/public-access-prevention)
- [Cloud KMS — Key management](https://docs.cloud.google.com/kms/docs/key-management-service)
- [Google Cloud — IAM best practices](https://docs.cloud.google.com/iam/docs/using-iam-securely)
- [Google Cloud — Privileged Access Manager](https://docs.cloud.google.com/privileged-access-manager/docs/overview)
- [Google Cloud — Audit Logs overview](https://docs.cloud.google.com/logging/docs/audit)
- [Google Cloud Architecture Center — Disaster recovery](https://docs.cloud.google.com/architecture/disaster-recovery)
