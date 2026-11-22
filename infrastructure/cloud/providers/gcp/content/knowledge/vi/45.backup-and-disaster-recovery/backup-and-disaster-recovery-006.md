# Thiết kế phục hồi VM, đĩa và dữ liệu tệp

## 1. Mục tiêu của thiết kế phục hồi

Một backup chỉ hữu ích khi có thể tìm đúng điểm khôi phục, dựng lại tài nguyên, xác minh dữ liệu và đưa dịch vụ trở về trạng thái hoạt động. Bài toán không kết thúc khi một lệnh sao lưu trả về thành công.

Trên Google Cloud, cần phân biệt ba đơn vị phục hồi:

- **VM:** Compute Engine instance, boot disk, data disks, machine type, hệ điều hành, network, IAM, service account, startup script và các phụ thuộc.
- **Đĩa:** Persistent Disk hoặc Hyperdisk chứa block data. Có thể khôi phục từ snapshot/backup để tạo disk mới, nhưng chưa chắc ứng dụng đã nhất quán.
- **Dữ liệu tệp:** file hoặc thư mục nằm trong filesystem trên VM, Filestore/NFS hoặc object của Cloud Storage. Phương án khôi phục một file có thể khác hoàn toàn phương án khôi phục cả file share.

Một VM bị xóa không thể tự dựng lại chỉ bằng snapshot của một data disk. Một file bị xóa nhầm không nhất thiết cần phục hồi toàn VM. Một sự cố region cần thêm network, DNS, KMS và quota chứ không chỉ bản sao dữ liệu.

Trong module **CLOUD_PROVIDERS_GCP**, bài này vận dụng các kiến thức Compute Engine, VPC, IAM, Cloud Storage, Filestore, Infrastructure as Code, giám sát độ tin cậy và tối ưu chi phí để lập thiết kế phục hồi có thể đo và kiểm chứng.

## 2. Thuật ngữ cốt lõi: RPO, RTO và recovery point

### 2.1. RPO: mức mất dữ liệu cho phép

**Recovery Point Objective (RPO)** là khoảng thời gian tối đa tổ chức chấp nhận mất dữ liệu khi xảy ra sự cố. Ví dụ:

- Một thư mục tài liệu xuất bản hằng ngày có thể có RPO 24 giờ.
- Một data disk xử lý hồ sơ liên tục có thể có RPO 4 giờ.
- Một cơ sở dữ liệu giao dịch có thể đòi RPO 15 phút hoặc thấp hơn.

Đây là các **mục tiêu minh họa**, không phải cam kết tự động của Google Cloud. Nếu snapshot chạy mỗi giờ nhưng ba job gần nhất thất bại, recovery point gần nhất có thể cách hiện tại nhiều giờ. RPO thực tế phải được đo bằng timestamp của dữ liệu thật sự có thể phục hồi.

Snapshot schedule đĩa hằng giờ không tự đáp ứng RPO 15 phút. Với các yêu cầu thấp hơn tần suất snapshot, cần cơ chế ở data layer như replication, transaction log hoặc point-in-time recovery phù hợp.

### 2.2. RTO: thời gian hệ thống ngừng phục vụ

**Recovery Time Objective (RTO)** là thời gian mục tiêu để dịch vụ sử dụng được trở lại. RTO thực tế bao gồm:

~~~text
Phát hiện sự cố
 + quyết định kích hoạt DR
 + xác định recovery point sạch
 + tạo lại VM/disk/file share
 + khôi phục network, IAM, KMS, DNS và phụ thuộc
 + xác minh hệ điều hành, filesystem, dữ liệu, ứng dụng
 + chuyển traffic và kiểm tra business flow
 = thời gian phục hồi
~~~

Chỉ đo thời gian `gcloud compute disks create` trả thành công sẽ báo cáo RTO thấp giả tạo. Một VM đã khởi động nhưng không kết nối được database vẫn chưa được xem là phục hồi dịch vụ.

### 2.3. Mục tiêu phải gắn với failure domain

| Loại sự cố | Đơn vị khôi phục | Mục tiêu kiểm tra |
|---|---|---|
| Một file bị xóa | File từ snapshot/backup | Giữ nguyên file khác và quyền truy cập |
| File bị sửa mã độc | Điểm sạch trước sự cố | Không phục hồi dữ liệu nhiễm |
| Disk bị hỏng hoặc xóa | Disk mới từ snapshot | Mount và đọc/ghi theo contract |
| Boot disk lỗi | Boot disk hoặc VM mới | OS và ứng dụng hoạt động |
| VM bị xóa | VM với cấu hình và disks | Network, IAM và dependencies |
| Zone outage | Resource ở zone khác | Quota, capacity và chuyển traffic |
| Region outage | Hạ tầng vùng khác | Backup location, KMS, DNS, RTO |
| Project/tài khoản bị chiếm | Backup được cô lập | Backup không bị xóa cùng production |

Một thiết kế tốt ghi rõ đối tượng phục hồi, người có trách nhiệm và mức độ dữ liệu mất chấp nhận được cho **từng workload**.

## 3. Kiểm kê trước khi chọn công nghệ

Với mỗi VM hoặc file share, lập danh mục:

1. Project, region, zone, resource ID và owner.
2. Machine type, OS image, boot disk, disk type/kích thước, filesystem và mount path.
3. Các data disks, chế độ attachment, LVM/RAID, encryption key.
4. Dữ liệu tạm trên Local SSD và dữ liệu bền vững trên Persistent Disk/Hyperdisk.
5. Filestore instance, tier, protocol NFS, file share, client mounts, IP-based access controls.
6. Cloud Storage buckets, soft-delete policy, versioning, retention, object ownership.
7. VPC, subnet, firewall, internal/external IP, private DNS và load balancer.
8. Service account, IAM bindings, OS Login, Secret Manager và KMS keys.
9. Nền tảng database, Pub/Sub, external API và hệ thống on-prem phụ thuộc.
10. Backup schedule, retention, vị trí lưu, khả năng restore, RPO/RTO và người xác nhận.

**Local SSD data không nằm trong machine image hoặc persistent disk snapshot.** Cache/RAM và dữ liệu chỉ nằm trên ephemeral local storage cần được tái tạo hoặc chuyển sang data store bền vững phù hợp nếu nghiệp vụ yêu cầu phục hồi.

### 3.1. Ví dụ phân loại dữ liệu

| Workload | Vị trí dữ liệu | Cách bảo vệ chính |
|---|---|---|
| Stateless frontend VM | Boot disk + IaC | Recreate VM và deploy code |
| Worker xử lý tài liệu | Boot + data disk | Snapshot schedule, backup và runbook |
| Shared reports | Filestore | Snapshot ngắn hạn + backup ngoài instance |
| PDF archive | Cloud Storage | Soft delete, versioning/retention khi cần |
| Transactional database | Cloud SQL hoặc DB trên VM | Native backup, logs/PITR và consistency workflow |

Việc một file tồn tại trên disk không có nghĩa disk snapshot là công cụ tốt nhất. Chọn kỹ thuật theo tính nhất quán và cách ứng dụng tiêu thụ dữ liệu.

## 4. Phân biệt HA, replication, snapshot và backup

| Cơ chế | Bảo vệ tốt nhất | Điều không bảo đảm |
|---|---|---|
| VM multi-zone hoặc regional disk | Một số sự cố cơ sở hạ tầng/zone | Phục hồi dữ liệu bị xóa hoặc ransomware |
| Replication | Độ trễ dữ liệu giữa bản sao | Phiên bản cũ khi xóa/sửa sai được sao chép |
| Disk snapshot | Điểm khôi phục block data của một disk | Đầy đủ cấu hình VM, app consistency đa disk |
| Machine image | Cấu hình VM và disk data | RAM, Local SSD data, mọi tài nguyên ngoài VM |
| Backup and DR vault | Backup được quản lý và retention chống xóa | DNS, network, IAM của ứng dụng được phục hồi tự động |
| Filestore snapshot | Rollback nhanh file/share trên một instance | Mất hoàn toàn instance |
| Filestore backup | Data nằm ngoài instance | Mọi tier đều hỗ trợ in-place restore |
| Cloud Storage soft delete | Object/bucket bị xóa trong thời hạn lưu | Khôi phục toàn workflow ứng dụng |

HA và replication giúp giảm downtime; backup và recovery points giúp quay về **thời điểm sạch**. Thường phải kết hợp nhiều lớp để xử lý các rủi ro khác nhau.

## 5. Kiến trúc bảo vệ nhiều lớp

~~~mermaid
flowchart TB
    APP[Compute Engine application] --> BOOT[Boot disk]
    APP --> DATA[Data disk]
    APP --> FILE[(Filestore share)]
    APP --> OBJ[(Cloud Storage objects)]
    BOOT --> MI[Machine image / reviewed IaC]
    DATA --> SCHEDULE[Disk snapshot schedule]
    BOOT --> VAULT[Backup and DR vault]
    DATA --> VAULT
    FILE --> FSNAP[Filestore snapshot]
    FILE --> FBACK[Filestore backup ngoài instance]
    OBJ --> SOFT[Soft delete / Object Versioning]
    MI --> REC[Recovery project / zone / region]
    SCHEDULE --> REC
    VAULT --> REC
    FBACK --> REC
    FSNAP --> VERIFY[File verification]
    SOFT --> VERIFY
    REC --> VERIFY
    VERIFY --> CUT[Approved cutover]
~~~

Sơ đồ thể hiện các lựa chọn thiết kế chứ không khẳng định mọi loại disk/Filestore tier hỗ trợ toàn bộ tính năng. Xác minh sản phẩm, vùng, loại mã hóa và giới hạn restore trước khi chọn.

## 6. Compute Engine snapshots

Snapshot tiêu chuẩn là bản ghi điểm dữ liệu từ Persistent Disk/Hyperdisk được hỗ trợ. **Incremental snapshots** quản lý dữ liệu thay đổi, giúp giảm dung lượng và thời gian trong nhiều trường hợp. Người vận hành không phải tự xây chuỗi full/incremental bằng file riêng.

Các nguyên tắc:

- Snapshot của **một disk** không tự khôi phục cấu hình VM.
- Snapshot có thể được tạo khi VM đang chạy, nhưng không tự có application consistency.
- Standard snapshots mặc định là global resources, có thể bị giới hạn restore/access location theo cấu hình.
- Snapshot storage location ảnh hưởng tính sẵn sàng khi region xảy ra sự cố, quy định lưu trữ dữ liệu và network costs.
- Restore từ snapshot thường **tạo disk mới**; không tự động ghi đè disk nguồn.
- Disk mới cần dung lượng tối thiểu bằng kích thước disk gốc theo yêu cầu restore.
- Thông tin snapshot READY và khả năng sử dụng cần được kiểm chứng định kỳ.

### 6.1. Standard hay archive snapshot?

Standard snapshot phù hợp khi cần khôi phục thường xuyên hoặc RTO ngắn hơn. Archive snapshot dành cho trường hợp ít truy xuất, retention dài và ưu tiên lưu trữ; cân nhắc thời gian, phí truy xuất và yêu cầu phục hồi. Không chọn archive chỉ dựa vào đơn giá lưu trữ/GB.

### 6.2. Tạo snapshot thủ công

~~~bash
gcloud compute snapshots create app-data-manual-001 \
  --project=PROJECT_ID \
  --source-disk=app-data \
  --source-disk-zone=asia-southeast1-b \
  --storage-location=asia-southeast2
~~~

Đây là ví dụ **chỉ của một disk**. Tạo trên project/đĩa thực yêu cầu IAM, quota, location support và phê duyệt chi phí. Với VM nhiều data disks, cần thiết kế thứ tự/quiesce để các recovery points nhất quán.

## 7. Snapshot schedules và retention

Snapshot schedule là Compute Engine resource policy gắn vào disk. Lịch có thể theo giờ, ngày hoặc tuần; thời gian khởi động chạy trong khung giờ đã thiết lập, không có nghĩa job chắc chắn hoàn tất đúng phút bắt đầu.

Ví dụ lịch mỗi ngày lúc 02:00 UTC và giữ snapshot tự động 14 ngày:

~~~bash
gcloud compute resource-policies create snapshot-schedule app-data-daily \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --daily-schedule \
  --start-time=02:00 \
  --max-retention-days=14 \
  --storage-location=asia-southeast2 \
  --on-source-disk-delete=apply-retention-policy

gcloud compute disks add-resource-policies app-data \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --resource-policies=app-data-daily
~~~

Lịch phải đặt ở region tương ứng với disk; kiểm tra tính tương thích theo loại disk. Các flags đáng chú ý:

- `--daily-schedule` không nhận một giá trị kèm theo.
- `--start-time` dùng UTC.
- `--max-retention-days` quy định thời gian giữ snapshots của schedule.
- `--storage-location` chọn vị trí lưu, cần đánh giá cross-region.
- `--on-source-disk-delete=apply-retention-policy` duy trì áp dụng retention khi disk bị xóa.
- `keep-auto-snapshots` giữ các snapshots sau khi disk nguồn bị xóa và cần quy trình cleanup riêng.

Không đặt retention quá ngắn nếu ransomware hoặc corruption có thể không được phát hiện kịp. Theo dõi **recovery point gần nhất thật sự thành công**, không chỉ event từ scheduler.

## 8. Crash-consistent và application-consistent snapshots

### 8.1. Crash consistency

Snapshot tạo khi VM đang ghi có thể tương đương trạng thái filesystem khi mất điện. Journal của filesystem có thể sửa một số lỗi metadata, nhưng không bảo đảm transaction ứng dụng đã commit nhất quán.

Ví dụ: ứng dụng đã cập nhật index nhưng dữ liệu file vẫn ở cache. Sau restore, index có thể trỏ tới file chưa hoàn chỉnh.

### 8.2. Application consistency

Muốn có point-in-time dữ liệu ứng dụng đáng tin cậy:

1. Dừng hoặc tạm hoãn yêu cầu ghi.
2. Flush application transactions và filesystem buffers.
3. Tạo snapshot/backup theo phương thức hỗ trợ.
4. Cho ứng dụng tiếp tục ghi sau khi đạt mốc an toàn.
5. Ghi nhận điểm thời gian/transaction marker.
6. Khi restore, chạy consistency check của workload.

Trên Linux dùng Persistent Disk có thể cấu hình **guest-flush** và pre/post snapshot scripts. Với Windows trên Persistent Disk có thể dùng VSS. **Hyperdisk không hỗ trợ guest-flush/VSS theo cơ chế này**; cần cách quiesce thủ công hoặc backup ứng dụng phù hợp.

Với nhiều disks chứa cùng một database hoặc filesystem logic, snapshot từng disk không mặc nhiên là một transaction-consistent set. Machine image có thể lấy disk data tại thời điểm nhất quán giữa các disks, nhưng vẫn cần OS/application participation để đạt application consistency.

### 8.3. Database không nên chỉ dựa vào block snapshot

Database giao dịch thường cần backup native, transaction logs và point-in-time recovery. Snapshot disk đơn thuần có thể không bảo đảm tính nhất quán, nhất là khi database ghi đồng thời trên nhiều disks. Hãy thiết kế database DR theo khả năng chuyên dụng của Cloud SQL/PostgreSQL/MySQL/SQL Server hoặc database engine thực tế.

## 9. Phục hồi một disk từ snapshot

Khi chỉ data disk bị lỗi, phục hồi một disk mới giảm ảnh hưởng lên phần khác.

**Quy trình:**

1. Chặn writes hoặc đưa ứng dụng vào maintenance mode khi cần.
2. Liệt kê snapshots, xác định recovery point trước lỗi và trạng thái READY.
3. Tạo **disk mới** từ snapshot, chọn zone, loại và dung lượng phù hợp.
4. Gắn disk vào recovery VM để kiểm tra; không xóa hoặc overwrite disk nguồn.
5. Kiểm tra partition, filesystem, owner, ACL, checksum và dữ liệu mẫu.
6. Chỉ cutover sau approval; giữ rollback path.
7. Ghi lại RPO/RTO đo được và cleanup resource test.

Ví dụ:

~~~bash
gcloud compute snapshots list --project=PROJECT_ID

gcloud compute disks create app-data-recovered \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --source-snapshot=SNAPSHOT_NAME \
  --type=pd-balanced

gcloud compute instances attach-disk recovery-vm \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --disk=app-data-recovered
~~~

Bên trong recovery VM Linux, **chỉ sau khi xác nhận thiết bị thực**:

~~~bash
lsblk -f
sudo blkid
sudo mkdir -p /mnt/recovery
# Thay DEVICE_PARTITION bằng đường dẫn được xác minh từ lsblk.
sudo mount -o ro /dev/DEVICE_PARTITION /mnt/recovery
find /mnt/recovery -maxdepth 2 -type f | head
~~~

Cần lưu ý các filesystem như XFS khi một clone có cùng UUID với disk đang mount; không tự mount read-write hoặc sửa UUID khi chưa đánh giá. Với yêu cầu chỉ một file, copy file từ disk clone read-only sang staging path, so sánh checksum và permissions rồi mới đưa vào chỗ cũ.

## 10. Phục hồi toàn VM: disk snapshots, machine images và IaC

### 10.1. VM cần nhiều hơn nội dung disk

Khi tạo lại VM, phải kiểm tra: machine type, CPU architecture, boot disk, data disks, OS startup, instance metadata, service account, IAM, firewall, VPC, subnet, DNS, load balancer, KMS và dependent services. Snapshot của disk không tự chứa các thành phần bên ngoài đó.

Dùng Terraform hoặc cấu hình IaC có version để tạo lại network/VM, nhưng nhớ **Terraform state không thay thế data backup**.

### 10.2. Machine image

Compute Engine **machine image** lưu phần lớn cấu hình instance, volume mapping và disk data, phù hợp khôi phục nhiều disks của một VM. Nó có thể giữ trạng thái nhất quán ở mức disk giữa các disks, nhưng không có đảm bảo application-level transaction consistency nếu app vẫn ghi.

Machine image **không bao gồm**:

- Nội dung RAM.
- Dữ liệu trên attached Local SSD (chỉ có thể giữ mapping thiết bị).
- Tất cả thuộc tính đặc thù instance như địa chỉ IP hoặc tên gốc một cách tuyệt đối.
- Những tài nguyên ngoài instance như IAM project policy, VPC, Cloud DNS, external secrets và KMS keys.

Sau khi restore machine image, cần kiểm tra boot integrity, disk mounts, OS permissions, service account, network và workload. Với Shielded VM, xem các yêu cầu liên quan đến secure boot/TPM khi dựng từ snapshot hoặc image.

### 10.3. Chọn chiến lược theo workload

| Workload | Phương án phục hồi |
|---|---|
| Stateless VM | Recreate bằng template/IaC và deploy image |
| Một data disk bị hỏng | Disk snapshot restore |
| VM với nhiều disks cần cùng recovery point | Machine image hoặc backup VM phù hợp |
| Đòi backup chống xóa/immutable | Backup and DR vault với enforced retention |
| RTO rất nhỏ | HA/warm standby/replication phối hợp backup |
| VM chạy DB giao dịch | Kết hợp VM/IaC và database-specific recovery |

## 11. Backup and DR Service và backup vault

Google Cloud Backup and DR Service có thể tạo backup plans, vaults và restore cho workloads được hỗ trợ, bao gồm các tình huống Compute Engine VM/disk.

~~~mermaid
flowchart LR
    VM[Compute Engine VM / disk] --> PLAN[Backup plan association]
    PLAN --> VAULT[Backup vault]
    VAULT --> POINT[Backup recovery points]
    POINT --> RESTORE[New VM / disk in recovery target]
    RESTORE --> VERIFY[OS + data + IAM + network checks]
~~~

**Backup vault** là nơi chứa backup được quản lý với khả năng cô lập và enforced retention. Với retention được bảo vệ, backup không bị xóa trước thời hạn áp dụng. Chọn retention quá dài có thể khiến phí lưu trữ không thể cắt giảm sớm.

Thiết kế cơ bản:

1. Bật Backup and DR API theo hướng dẫn trên project thích hợp.
2. Tạo vault tại location hỗ trợ workload.
3. Cấu hình minimum enforced retention hoặc policy lock sau review.
4. Tạo backup plan với schedule, backup window và retention.
5. Associate plan với VM/disk được bảo vệ.
6. Theo dõi job history và recovery point mới nhất.
7. Restore định kỳ sang project/zone thử nghiệm và xác minh.

### 11.1. Restore từ vault

Một VM có thể được khôi phục tới VM mới hoặc một disk riêng tùy phạm vi backup và tính năng được hỗ trợ. Dịch vụ cần quyền IAM trên backup project, target project, service agent, KMS và có thể Shared VPC host.

Ví dụ CLI từ tài liệu hướng dẫn Compute Engine backup vault:

~~~bash
gcloud backup-dr backups restore compute BACKUP_ID \
  --project=BACKUP_PROJECT_ID \
  --location=BACKUP_REGION \
  --backup-vault=VAULT_NAME \
  --data-source=DATA_SOURCE \
  --name=app-recovery-vm \
  --target-project=RECOVERY_PROJECT_ID \
  --target-zone=RECOVERY_ZONE
~~~

Các tham số là placeholder; phải xác minh backup ID, vault, data source, location và target. Người phục hồi có thể cần `roles/backupdr.restoreUser`, `roles/compute.viewer` và service agent cần `roles/backupdr.computeEngineOperator` theo tình huống. Không tự cấp Owner chỉ để bỏ qua lỗi IAM.

**Enforced retention bảo vệ backup**, không tự khôi phục VPC, DNS, secret hoặc business service. Vẫn cần runbook hoàn chỉnh.

## 12. Filestore: snapshot và backup là hai lớp khác nhau

Filestore phục vụ dữ liệu tệp qua NFS. Cần hiểu rõ vị trí lưu recovery point.

### 12.1. Filestore snapshot

Filestore snapshot nằm **trong instance nguồn** và giữ trạng thái share tại một thời điểm. Khi dữ liệu trên instance thay đổi, snapshot cần thêm capacity để bảo toàn phiên bản cũ.

Dùng khi:

- Một file/thư mục bị sửa hoặc xóa nhầm.
- Cần lấy lại phiên bản trong thời gian ngắn.
- Cần revert share sau thay đổi có kiểm soát.

Giới hạn:

- Snapshot không độc lập khỏi instance và không thay backup DR.
- Revert toàn share là thao tác **phá hủy dữ liệu mới hơn** snapshot.
- Snapshot dùng capacity trong instance.
- Tính năng snapshot được hỗ trợ ở các tiers **zonal, regional và enterprise**, không hỗ trợ ở **basic HDD/basic SSD** theo tài liệu hiện hành.

### 12.2. Filestore backup

Filestore backup là resource **ngoài instance**, có dung lượng riêng và có thể được lưu tại vùng khác theo hỗ trợ. Nó phù hợp DR khi mất instance/region, cloning và recovery file khi phải tạo share mới.

Bản backup chứa dữ liệu file và một phần metadata, nhưng **không** tự giữ nguyên VPC network, IP, IP-based access controls, file locks, lock state và snapshots của instance nguồn.

Giới hạn restore quan trọng:

- **Basic HDD/SSD** hỗ trợ các kịch bản restore về source/existing/new instance theo điều kiện được hỗ trợ.
- **Zonal/Regional/Enterprise** backup restore nói chung cần **new instance**, không nên chạy thao tác in-place với giả định giống basic tier.
- Target phải phù hợp service tier, dung lượng, protocol, region/location và encryption constraints.
- Một số backup không tương thích Filestore multishares.
- Sau restore, clients cần remount và ứng dụng có thể phải reconnect.

### 12.3. So sánh nhanh

| Thuộc tính | Filestore snapshot | Filestore backup |
|---|---|---|
| Vị trí | Trong instance | Ngoài instance |
| Khôi phục một file | Qua `.snapshot` nếu hỗ trợ | Restore instance hoặc share rồi copy |
| Mất toàn instance | Không bảo vệ độc lập | Dùng backup để tạo instance mới |
| Chi phí | Capacity trong instance | Backup storage riêng/cross-region transfer |
| Revert | Có thể phá hủy thay đổi mới | Tùy tier và target restore được hỗ trợ |
| Tác dụng chính | Operational recovery nhanh | Disaster recovery và sao lưu bền hơn |

## 13. Runbook phục hồi một file trên Filestore

Giả sử `/mnt/reports/summary.csv` bị xóa nhầm.

1. Xác minh owner, tên file và khoảng thời gian mất.
2. Kiểm tra Filestore instance tier và snapshot khả dụng.
3. Chọn snapshot sạch gần nhất trước lỗi.
4. Truy cập file qua thư mục `.snapshot` trong mounted share.
5. Copy file sang **đường dẫn tạm**, không ghi đè ngay.
6. Kiểm tra checksum, size, owner/group, quyền và nội dung.
7. Sau approval mới phục hồi tại đường dẫn live.
8. Ghi lại snapshot, thời gian thực tế và outcome.

Ví dụ đường dẫn biểu diễn:

~~~text
/mnt/reports/
  summary.csv
  .snapshot/
    before-upgrade/
      summary.csv
~~~

Nếu cả instance đã mất, phải khôi phục từ **Filestore backup ngoài instance**, tạo instance mới trong location được hỗ trợ, cấu hình lại network/exports/access controls, mount share và kiểm tra ứng dụng trước cutover.

Trước thao tác restore đè lên một basic-tier instance đang dùng, nên tạm dừng ghi và unmount clients theo tài liệu. Không phục hồi in-place chỉ để lấy một file nếu việc đó phá hủy nhiều dữ liệu mới.

## 14. Cloud Storage: file được lưu dưới dạng object

Cloud Storage dùng **object name + generation + metadata**, không phải block disk hoặc NFS share truyền thống. Cơ chế bảo vệ phù hợp gồm soft delete, object versioning và retention.

### 14.1. Soft delete

Soft delete giữ object hoặc bucket bị xóa/ghi đè trong khoảng thời gian cấu hình. Các bucket hỗ trợ thường có thời hạn mặc định hiện hành **7 ngày**, nhưng chính sách thực tế cần được kiểm tra thay vì giả định.

Object ở trạng thái soft-deleted không thể đọc như live object; phải thực hiện restore. Việc restore tạo **live object mới**, có thể ghi đè live object cùng tên hiện tại. Khi phục hồi, xác minh generation và liệu đang có phiên bản mới hơn mà nghiệp vụ muốn giữ.

### 14.2. Object Versioning

Object Versioning giữ các noncurrent generations khi object bị sửa/xóa. Hữu ích khi ứng dụng cần xem lại một phiên bản cụ thể, nhưng **không tự bảo vệ bucket bị xóa** và không ngăn privileged principal xóa vĩnh viễn noncurrent generations.

Google Cloud khuyến nghị soft delete khi mục tiêu là bảo vệ xóa nhầm/malicious deletion. Kết hợp versioning khi có use case truy cập lịch sử phiên bản và chính sách lifecycle phù hợp.

### 14.3. Retention và lock

Retention policy, Object Retention Lock hoặc Bucket Lock có thể dùng khi cần hạn chế xóa/sửa trong thời hạn. Một số kiểu lock không thể đảo ngược, nên cần review pháp lý, dữ liệu, chi phí và quy trình change management. Không khóa nhầm bucket chứa dữ liệu tạm nhiều ngày nếu dữ liệu này đáng lẽ phải được xóa.

## 15. Cross-zone và cross-region recovery

### 15.1. Zone outage

Dùng snapshot hoặc backup để tạo disk/VM ở zone khác thường cần kiểm tra:

- Quota CPU, memory, disk size/IOPS/throughput ở zone mới.
- OS image và machine type availability.
- Subnet, private IP, firewall, DNS và load balancer.
- IAM/service account, OS Login và API enablement.
- KMS key location và quyền service agent.
- Dependencies như Filestore, Cloud SQL và network riêng.

RTO nhỏ có thể yêu cầu **warm standby hoặc HA**. Chỉ backup định kỳ không có nghĩa dịch vụ sẽ failover nhanh.

### 15.2. Region outage

Recovery points phải nằm ở location có thể dùng nếu region nguồn gặp sự cố. Standard disk snapshots có khả năng restore sang vùng khác trong phạm vi location/access rules; cần tính phí transfer và những giới hạn áp dụng. Filestore backup ngoài instance có thể nằm tại region khác; phải tạo instance mới tại target location được hỗ trợ.

Với Backup and DR vault, đừng mặc định backup có thể restore ở mọi location hoặc project. Cần xác minh matrix workload, vault location, backup plan, KMS và restore access.

### 15.3. Failback

Sau khi workload chạy tại region phục hồi, dữ liệu mới sẽ tiếp tục phát sinh. Khi quay về region ban đầu, cần **reconcile dữ liệu** và lập kế hoạch cutover mới. Không phục hồi snapshot cũ đè lên production mới chỉ vì region ban đầu đã hoạt động lại.

## 16. IAM, KMS và bảo vệ khỏi xóa ác ý

### 16.1. Separation of duties

Phân tách:

- Backup configuration/plan administrator.
- Backup service identity chạy schedule.
- Restore operator có quyền xem và dùng backup được chỉ định.
- Compute/Filestore service agent dùng quyền kỹ thuật cần thiết.
- Security/compliance kiểm tra retention và audit.

Không dùng service account Owner cho job chỉ tạo snapshot. Không để người quản trị VM production mặc nhiên có quyền xóa mọi backup. Bật audit trên thay đổi policy, role và backup deletion theo khả năng logging của từng sản phẩm.

### 16.2. CMEK

Với disk, snapshot hoặc backup mã hóa bằng **customer-managed encryption key (CMEK)**:

- Đảm bảo KMS key còn tồn tại và enabled khi restore.
- Service agent và identity phục hồi có quyền sử dụng key.
- Key location và encryption compatibility đáp ứng resource đích.
- Có quy trình rotation, key disable, key deletion và break-glass rõ.
- Không xóa KMS key chỉ vì VM nguồn đã bị hủy.

Một backup còn tồn tại nhưng không thể giải mã là recovery point **không sử dụng được**. Kiểm thử cross-project/cross-region phải gồm cả quyền KMS.

### 16.3. Ransomware resilience

Nếu lo tài khoản bị chiếm quyền hoặc ransomware:

1. Tách backup vault/project/identity khỏi workload production.
2. Dùng enforced retention hoặc retention lock đúng mức rủi ro.
3. Giảm số principal có quyền thay retention hoặc xóa backup.
4. Theo dõi bất thường trong API/IAM và backup activity.
5. Restore trước hết vào môi trường cách ly, kiểm tra malware và dữ liệu.
6. Thu hồi credential bị lộ trước cutover.
7. Giữ bằng chứng audit và kế hoạch xử lý sự cố.

Không phục hồi dữ liệu sạch vào một VM còn bị kiểm soát bởi attacker.

## 17. Tự động hóa phục hồi bằng IaC và runbook

Terraform hoặc công cụ IaC có thể dựng network, IAM, instance templates, VM/disk và các resource policies được hỗ trợ. Nhưng **IaC là cấu hình, không phải data backup**.

Một runbook nên có những bước cố định:

~~~text
1. Xác nhận sự cố và phạm vi dữ liệu ảnh hưởng.
2. Chọn điểm khôi phục sạch, kiểm tra backup READY.
3. Xác minh RPO, retention, quyền, KMS, quota và target region.
4. Dừng hoặc cách ly nguồn nếu cần tránh ghi chồng.
5. Provision resource đích từ IaC/image/snapshot/backup.
6. Mount dữ liệu theo chế độ an toàn và kiểm tra consistency.
7. Chạy smoke test, permission check và business reconciliation.
8. Xin approval để chuyển DNS, load balancer hoặc mount target.
9. Theo dõi metrics/logs, chuẩn bị rollback và failback.
10. Ghi actual RPO/RTO, resource IDs, owner và chi phí.
~~~

Không tạo pipeline tự động xóa/ghi đè production khi chưa có checkpoint và approval. Thử nghiệm restore nên tạo **resource mới** thay vì sửa dữ liệu đang phục vụ.

## 18. Kiểm thử phục hồi định kỳ

Backup job xanh không chứng minh dữ liệu phục hồi tốt. Đặt lịch diễn tập **restore** ở sandbox.

| Bài thử | Tiêu chí |
|---|---|
| Một file Filestore từ snapshot | Đúng dữ liệu/owner/permissions, không mất file khác |
| Filestore instance từ backup | Mount được NFS, filesystem đúng và network hoạt động |
| Cloud Storage soft-deleted object | Đúng generation, không vô tình overwrite phiên bản mới |
| Data disk từ snapshot | Filesystem mount được, checksum và dữ liệu hợp lệ |
| Boot disk hoặc VM từ machine image | OS boot, service chạy, IAM/network đúng |
| Backup and DR vault restore | Đúng recovery point, không vướng service agent/KMS |
| Cross-region DR | Có quota, DNS, network, dependencies và cutover |
| Ransomware drill | Chọn point sạch, cách ly attacker và bảo vệ backup |

### 18.1. Chỉ số cần theo dõi

- `backup_success_rate` và `backup_failed_count`.
- `latest_recovery_point_age` cho từng workload.
- `restore_test_success_rate`.
- `restore_duration` tới khi app usable.
- RPO thực tế qua timestamp bản ghi cuối cùng.
- Chi phí backup/retention/cross-region và tài nguyên thử nghiệm.
- Số resource chưa có policy hoặc chưa được diễn tập trong kỳ.

Đừng chỉ restore bản backup mới nhất. Kiểm tra cả một recovery point cũ hơn để phát hiện vấn đề retention và chain.

## 19. Chi phí và đánh đổi

Chi phí bảo vệ/DR gồm:

~~~text
Snapshot hoặc backup storage
+ noncurrent/soft-deleted object storage
+ cross-region transfer
+ backup management, retrieval khi áp dụng
+ KMS và dependency resource
+ VM/Filestore thử nghiệm hoặc warm standby
+ công vận hành và diễn tập
~~~

Filestore snapshots dùng dung lượng trong instance và có thể làm giảm không gian thực dùng. Filestore backups dùng dung lượng ngoài instance. Cloud Storage soft delete/versioning giữ thêm data. Archive snapshots có đặc tính truy xuất/retention khác. Backup vault có enforced retention sẽ tiếp tục phát sinh phí đến khi hết hạn.

Tối ưu theo **chi phí downtime và mất dữ liệu**, không chỉ so đơn giá GB/tháng. Một kế hoạch rẻ nhưng không có khả năng đáp ứng RPO/RTO có thể đắt hơn thiệt hại khi sự cố thật.

## 20. Case study: dịch vụ xử lý tài liệu

Ứng dụng `document-worker-prod` chạy trên VM ở `asia-southeast1-b`:

- Boot disk chứa OS/agent và runtime.
- Data disk `documents-data` giữ các file trung gian.
- Filestore `shared-reports` chứa PDF nhiều workers dùng chung.
- Bucket Cloud Storage `documents-archive` chứa bản PDF cuối.
- Cloud SQL chứa metadata (được backup/PITR theo kế hoạch database riêng).

### 20.1. Mục tiêu tham khảo

| Tài nguyên | RPO ví dụ | RTO ví dụ | Giải pháp |
|---|---|---|---|
| VM stateless code | Có thể provision lại | 1 giờ | Image/template + IaC |
| Data disk | 4 giờ | 2 giờ | Disk schedule + backup theo rủi ro |
| Filestore | 24 giờ | 4 giờ | Snapshot ngắn hạn + backup ngoài instance |
| Cloud Storage PDFs | Tùy policy dữ liệu | 1 giờ cho file chọn lọc | Soft delete/versioning/retention |
| Cloud SQL metadata | Theo SLA DB | Theo SLA DB | Native backups/PITR |

Đây không phải SLA mặc định của GCP. Cần diễn tập thực tế và ghi ra phương án nếu recovery target mất quota hoặc KMS key không khả dụng.

### 20.2. Sự cố A: xóa nhầm báo cáo

1. Tìm Filestore snapshot trước thời điểm xóa.
2. Copy file cần lấy sang staging path.
3. Kiểm tra checksum, permissions, nội dung và owner.
4. Đưa file vào đúng chỗ sau approval.
5. Ghi thời gian phục hồi; **không** revert cả share.

### 20.3. Sự cố B: mất zone

1. Tìm recovery point sạch và xác minh status.
2. Dựng VM/disk tại zone khác bằng image/snapshot/backup và IaC.
3. Khôi phục Filestore share nếu file server không dùng được.
4. Khôi phục VPC/DNS/firewall/IAM/KMS và kết nối Cloud SQL.
5. Test upload → process → PDF → metadata reconciliation.
6. Chuyển traffic sau approval, giám sát rồi lập failback plan.

### 20.4. Sự cố C: ransomware

1. Cô lập máy và identity nghi nhiễm.
2. Chọn recovery point sạch trước thời điểm mã hóa.
3. Restore tại project/mạng cách ly, scan và checksum.
4. Vá cấu hình, rotate credential và kiểm tra quyền.
5. Chỉ cutover dữ liệu đã xác nhận an toàn.
6. Audit backup vault, retention và quyền xóa.

## 21. Những lỗi thiết kế thường gặp

| Sai lầm | Tác động | Cách khắc phục |
|---|---|---|
| Có disk snapshot nên coi đã có VM DR | Thiếu OS/network/IAM/dependency | Machine image/IaC + runbook |
| Snapshot hằng ngày, cam kết RPO 15 phút | Mất nhiều dữ liệu hơn mục tiêu | Dùng data-layer backup/log/replication |
| Snapshot khi DB đang ghi và coi là app-consistent | Dữ liệu có thể không nhất quán | Quiesce hoặc backup native |
| Chỉ giữ Filestore snapshots | Mất instance có thể mất recovery points | Backup ngoài instance |
| Dùng in-place restore sai Filestore tier | Bị từ chối hoặc ảnh hưởng share | Kiểm tra tier/restore matrix |
| Bật Object Versioning nhưng không bảo vệ bucket deletion | Mất cả bucket | Soft delete/retention đúng |
| Xóa CMEK key cùng nguồn | Không giải mã được backup | Bảo vệ key lifecycle |
| Restore đè ngay lên source | Mất dữ liệu mới và rollback khó | Restore resource mới và xác minh |
| Chỉ giám sát backup success | Không biết data có đọc được | Restore drills có checklist |
| Cấp quyền Owner cho backup job | Blast radius lớn | Least privilege, separation |
| Không tính cross-region transfer | Chi phí đột biến | Cost model và region selection |
| Chỉ đo thời gian tạo disk | RTO không chính xác | Đo đến khi app usable |

## 22. Checklist trước production

### Phạm vi và mục tiêu

- [ ] Có RPO/RTO được business owner phê duyệt.
- [ ] Đã phân loại VM, boot/data disks, Local SSD, Filestore, Cloud Storage và database.
- [ ] Đã phân tích sự cố file, disk, VM, zone, region, account compromise và ransomware.
- [ ] Có inventory IAM, KMS, quota, VPC, DNS và dependencies của recovery target.

### Backup và retention

- [ ] Data disks có snapshot/backup phù hợp tần suất thay đổi.
- [ ] Backup có location và access rules đáp ứng DR/residency.
- [ ] App có consistency workflow thay vì trông cậy crash-consistent snapshot.
- [ ] Filestore tier hỗ trợ các thao tác restore dự định.
- [ ] Có backup ngoài Filestore instance khi cần DR.
- [ ] Cloud Storage soft delete/versioning/retention đã chọn có chủ đích.
- [ ] Retention đủ dài để phát hiện corruption hoặc xóa ác ý.

### Security và vận hành

- [ ] Backup/restore identities có quyền tối thiểu và tách khỏi production admin.
- [ ] Đã xem xét Backup and DR enforced retention và việc khóa policy.
- [ ] KMS keys/service agents đã được kiểm tra khi restore.
- [ ] Có audit/alert cho backup failures, policy changes và deletion.
- [ ] Có runbook cách ly, phục hồi, kiểm chứng, cutover và failback.

### Diễn tập

- [ ] Đã restore thử một file, một disk và một VM.
- [ ] Đã restore Filestore backup vào instance mới.
- [ ] Đã thử Cloud Storage soft-deleted object restore.
- [ ] Đã đo RPO/RTO tới khi ứng dụng chạy và business data hợp lệ.
- [ ] Đã thử cross-region/project recovery theo mức độ rủi ro.
- [ ] Đã cleanup tài nguyên test và lưu báo cáo diễn tập.

## 23. Câu hỏi tự kiểm tra

1. Vì sao snapshot của một disk không đồng nghĩa với backup toàn VM?
2. RPO khác RTO ở điểm nào? Tại sao lịch chạy không bảo đảm RPO thực tế?
3. Khi nào nên dùng machine image thay vì snapshots riêng lẻ?
4. Snapshot khi VM đang chạy có luôn application-consistent không?
5. Với Hyperdisk, vì sao không thể giả định có guest-flush/VSS như Persistent Disk?
6. Khi nào cần native database backup thay vì disk snapshot?
7. Vì sao Filestore snapshot không thay thế backup ngoài instance?
8. Tại sao phục hồi một file không nên revert toàn share?
9. Soft delete và Object Versioning khác nhau ra sao khi bucket bị xóa?
10. Enforced retention của Backup and DR vault bảo vệ điều gì?
11. Vì sao KMS key bị xóa có thể làm backup vô dụng?
12. Restore cross-region cần những gì ngoài bản snapshot?
13. Vì sao nên mount disk mới read-only khi xác minh dữ liệu?
14. Những bước nào thuộc RTO ngoài thời gian tạo VM?
15. Một restore drill tốt phải đo và lưu bằng chứng gì?

## Tài liệu tham khảo

- [Compute Engine: About snapshots](https://docs.cloud.google.com/compute/docs/disks/snapshots)
- [Compute Engine: Create disk snapshots](https://docs.cloud.google.com/compute/docs/disks/create-snapshots)
- [Compute Engine: Snapshot schedules](https://docs.cloud.google.com/compute/docs/disks/scheduled-snapshots)
- [Compute Engine: Restore snapshots](https://docs.cloud.google.com/compute/docs/disks/restore-snapshot)
- [Compute Engine: Snapshot best practices](https://docs.cloud.google.com/compute/docs/disks/snapshot-best-practices)
- [Compute Engine: Application-consistent Linux snapshots](https://docs.cloud.google.com/compute/docs/disks/creating-linux-application-consistent-pd-snapshots)
- [Compute Engine: Machine images](https://docs.cloud.google.com/compute/docs/machine-images)
- [Backup and DR: Backup vaults](https://docs.cloud.google.com/backup-disaster-recovery/docs/concepts/backup-vault)
- [Backup and DR: Backup plans](https://docs.cloud.google.com/backup-disaster-recovery/docs/cloud-console/backup-plan)
- [Backup and DR: Restore Compute Engine instances](https://docs.cloud.google.com/backup-disaster-recovery/docs/cloud-console/compute/compute-instance-restore)
- [Filestore: Compare snapshots and backups](https://docs.cloud.google.com/filestore/docs/compare-snapshots-and-backups)
- [Filestore: Snapshots](https://docs.cloud.google.com/filestore/docs/snapshots)
- [Filestore: Backups](https://docs.cloud.google.com/filestore/docs/backups)
- [Filestore: Backup limitations](https://docs.cloud.google.com/filestore/docs/backups-limitations)
- [Cloud Storage: Soft delete](https://docs.cloud.google.com/storage/docs/soft-delete)
- [Cloud Storage: Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning)

