# Backup, phục hồi ứng dụng và dữ liệu AKS

Một ứng dụng chạy trên **Azure Kubernetes Service (AKS)** có thể được triển khai lại nhanh chóng từ container image và manifest. Nhưng nếu cơ sở dữ liệu bị xóa nhầm, PersistentVolume (PV) bị hỏng hoặc toàn bộ cluster không còn hoạt động, việc tạo pod mới **không đồng nghĩa khôi phục được dữ liệu và trạng thái nghiệp vụ**. Đây là lý do chiến lược backup AKS phải bao quát nhiều lớp: cấu hình Kubernetes, dữ liệu trên volume, dịch vụ dữ liệu bên ngoài cluster, hạ tầng Azure và quy trình kiểm chứng phục hồi.

Ví dụ, một hệ thống đặt hàng có API trong Deployment, PostgreSQL trong StatefulSet với PersistentVolumeClaim (PVC), bí mật tại Azure Key Vault và ảnh hóa đơn ở Blob Storage. Lưu riêng YAML của Deployment không khôi phục được bảng đơn hàng; snapshot đĩa PostgreSQL cũng không tự tạo lại Azure Load Balancer, DNS, private endpoint hay quyền workload identity. **Một kế hoạch phục hồi tốt phải giải thích rõ những gì được sao lưu, những gì được tái tạo và thứ tự khôi phục.**

Bài học thuộc chương **Vận hành AKS**, trong lộ trình Microsoft Azure từ subscription, resource group, Microsoft Entra ID, mạng ảo tới tính toán, lưu trữ, dữ liệu, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **backup**, **snapshot**, **replication**, **GitOps/IaC** và **disaster recovery (DR)**.
2. Phân loại những lớp cần bảo vệ: Kubernetes resources, persistent volumes, dịch vụ ngoài cluster và cấu hình Azure.
3. Xác định **RPO**, **RTO**, phạm vi mất dữ liệu chấp nhận được và mức độ ưu tiên phục hồi.
4. Hiểu cách tiếp cận của **Azure Backup for AKS**, CSI VolumeSnapshot và các công cụ backup Kubernetes.
5. Phân biệt tính nhất quán **crash-consistent**, **application-consistent** và khôi phục database theo thời điểm.
6. Thiết kế backup policy, thời hạn lưu, quyền truy cập, mã hóa, giám sát và xử lý lỗi.
7. Lập runbook phục hồi namespace, workload, PVC và các thành phần phụ thuộc.
8. Thực hiện diễn tập khôi phục có kiểm chứng trong môi trường thử nghiệm, không làm ảnh hưởng production.

## 1. Điều gì thực sự cần được backup trong AKS?

Một ứng dụng Kubernetes không nằm trong một file hay một đĩa. Hãy chia trạng thái thành các lớp:

| Lớp | Ví dụ | Cách bảo vệ chính |
|---|---|---|
| **Khai báo hạ tầng Azure** | AKS cluster, VNet, subnet, route, ACR, Key Vault, private endpoint | Bicep/Terraform/ARM, cấu hình được version hóa, quy trình tái tạo |
| **Kubernetes desired state** | Namespace, Deployment, StatefulSet, Service, Ingress, ConfigMap, RBAC, NetworkPolicy | GitOps, Helm, manifests và backup tài nguyên cluster khi cần |
| **Dữ liệu lưu trên PV/PVC** | Dữ liệu của database hoặc ứng dụng được mount lên volume | Snapshot/backup loại volume được hỗ trợ, cơ chế backup ứng dụng |
| **Dữ liệu ngoài cluster** | Azure Database for PostgreSQL, Azure SQL, Blob Storage, Cosmos DB | Backup/PITR/replication theo chính dịch vụ dữ liệu |
| **Bí mật và danh tính** | Key Vault, workload identity, managed identity, RBAC, chứng chỉ | Kiểm soát và sao lưu cấu hình hỗ trợ, kế hoạch khôi phục định danh/khóa |
| **Artifact** | Container image, Helm chart, migration package | ACR/registry và kho artifact được quản lý theo phiên bản |
| **Chứng cứ vận hành** | Logs, metrics, audit trail, backup reports | Azure Monitor/Log Analytics, retention riêng theo chính sách |

**Kubernetes manifests không chứa nội dung của PersistentVolume.** Ngược lại, khôi phục một volume không tự phục hồi Service, NetworkPolicy hay ConfigMap để workload dùng dữ liệu đó. Cả hai cần nhất quán với phiên bản ứng dụng.

### Control plane AKS không phải etcd do người dùng tự quản

AKS là dịch vụ Kubernetes được Azure quản lý. Người dùng thường quản trị cluster qua Kubernetes API, nhưng không nên lập kế hoạch tự truy cập trực tiếp và sao lưu etcd của AKS như với một cluster tự vận hành. Với AKS, phương án thực tế là bảo vệ các tài nguyên Kubernetes theo cơ chế được hỗ trợ, lưu desired state trong Git và backup dữ liệu bền vững.

Không dùng một bản export ngẫu nhiên của tài nguyên Kubernetes rồi gọi đó là **full-cluster backup** khi chưa kiểm tra CRD, volume, secret, đối tượng cluster-scoped và dữ liệu bên ngoài.

## 2. RPO và RTO: bắt đầu từ yêu cầu nghiệp vụ

**Recovery Point Objective (RPO)** là lượng dữ liệu tối đa có thể mất tính theo khoảng thời gian khi sự cố xảy ra. **Recovery Time Objective (RTO)** là khoảng thời gian mục tiêu để dịch vụ hoạt động trở lại ở mức được chấp thuận.

Ví dụ:

~~~text
Ứng dụng đặt hàng
RPO = 15 phút
RTO = 2 giờ

Sự cố xảy ra lúc 14:00
RPO đặt mục tiêu trạng thái dữ liệu khôi phục không cũ hơn 13:45
RTO đặt mục tiêu dịch vụ có thể hoạt động trở lại trước 16:00
~~~

Đây là **mục tiêu nghiệp vụ**, không phải lời bảo đảm chỉ vì bạn bật lịch backup mỗi 15 phút. Hệ thống phải có bản backup/transaction log khả dụng, hạ tầng phục hồi và diễn tập chứng minh có thể đạt mục tiêu.

### Chọn mục tiêu theo thành phần

| Thành phần | Rủi ro khi mất | Chiến lược gợi ý |
|---|---|---|
| Frontend stateless | Có thể tạo lại từ image/manifests | GitOps và registry; RTO ngắn |
| API stateless | Có thể tạo lại nếu phụ thuộc sẵn sàng | IaC, GitOps, secrets/identity |
| Database đơn hàng | Mất giao dịch, ảnh hưởng khách hàng | Backup database/PITR với RPO phù hợp |
| Tệp đính kèm | Mất tài liệu đã upload | Backup, versioning/replication tùy dịch vụ |
| Cache có thể tái tạo | Có thể làm mất hiệu năng, không nhất thiết mất dữ liệu gốc | Chiến lược warm-up/rebuild |
| Audit logs | Có thể ảnh hưởng kiểm toán | Retention/backup theo yêu cầu tuân thủ |

Một kiến trúc có nhiều mức ưu tiên thường cần **thứ tự khôi phục theo dependency**, thay vì phục hồi mọi pod cùng một lúc.

### Công thức tư duy về thời gian

~~~text
RTO thực tế có thể bao gồm:
  T_detect
  + T_approve / T_decide
  + T_provision_cluster_and_network
  + T_restore_resources
  + T_restore_data
  + T_validate
  + T_switch_traffic

RPO thực tế phụ thuộc:
  thời điểm bản backup/transaction log cuối cùng hợp lệ
  + lỗi/độ trễ của lịch backup
  + khả năng phục hồi dữ liệu tại thời điểm mong muốn
~~~

Không lấy mỗi thời gian chạy lệnh restore để công bố RTO. DNS propagation, kiểm tra dữ liệu, cutover và bước phê duyệt cũng tiêu tốn thời gian.

## 3. Backup, snapshot, replication và GitOps không giống nhau

| Cơ chế | Trả lời câu hỏi | Điểm yếu nếu dùng đơn lẻ |
|---|---|---|
| **Snapshot** | Có thể tạo điểm khôi phục trạng thái volume tại một thời điểm không? | Có thể chỉ crash-consistent; phụ thuộc storage/region/driver; không chứa toàn bộ ứng dụng |
| **Backup** | Có bản sao/điểm khôi phục được quản lý với retention và chính sách không? | Chưa chắc khôi phục được nếu không test hoặc thiếu dependencies |
| **Replication** | Dữ liệu có bản sao gần thời gian thực tại nơi khác không? | Lỗi/xóa/ghi sai có thể bị nhân bản sang bản sao |
| **GitOps/IaC** | Có thể tái tạo cấu hình đã khai báo không? | Không khôi phục dữ liệu phát sinh trong runtime |
| **PITR** | Có thể phục hồi database về thời điểm thích hợp không? | Phụ thuộc dịch vụ, log backup, giới hạn retention và bản backup |
| **Disaster recovery** | Có kế hoạch tái lập cả dịch vụ sau sự cố lớn không? | Cần nhiều thành phần, người phụ trách và diễn tập |

**Một snapshot không tự là backup có thể chống mất cả region.** Snapshot có thể nằm trong phạm vi lưu trữ hoặc region nhất định; phải kiểm tra backup tier, khả năng di chuyển/copy và điểm phục hồi độc lập với hệ thống gốc.

### Rủi ro replication không sửa được

Nếu ứng dụng vô tình xóa toàn bộ bản ghi và việc xóa được replicate, replica có thể giống nguồn đã lỗi. Để khôi phục lại trước thời điểm xóa, cần **điểm khôi phục lịch sử** như backup/PITR/versioning theo dịch vụ tương ứng.

## 4. Các kịch bản sự cố AKS cần chuẩn bị

| Kịch bản | Dấu hiệu | Cách tiếp cận |
|---|---|---|
| Xóa nhầm Deployment | Pod biến mất, dữ liệu chưa mất | Khôi phục manifests qua GitOps/Helm |
| Xóa nhầm PVC/PV | Workload không mount được dữ liệu | Restore volume từ điểm backup hoặc snapshot phù hợp |
| Database bị ghi sai | Pod vẫn chạy nhưng dữ liệu sai | PITR hoặc restore logical/physical backup theo DB |
| Node pool hỏng | Pod mất khả năng scheduling | Khôi phục năng lực node, reschedule và kiểm tra storage |
| Namespace bị xóa | Thiếu tài nguyên Kubernetes và có thể mất PVC | Restore namespace-scoped resources, volumes và dependencies |
| Cluster bị xóa hoặc không thể dùng | Kubernetes API/workloads không sẵn sàng | Tạo cluster đích bằng IaC, restore ứng dụng/dữ liệu |
| Mất region | Nhiều dịch vụ Azure cùng ảnh hưởng | DR sang region đã chuẩn bị, dữ liệu/bản backup phải khôi phục được ở region đích |
| Ransomware/tài khoản bị xâm nhập | Xóa/sửa dữ liệu hoặc xóa backup | Tách quyền, backup bất biến/offsite khi được hỗ trợ, kiểm tra sạch trước restore |
| Lỗi cập nhật ứng dụng | Image/config mới gây sự cố | Rollback phiên bản, phục hồi dữ liệu nếu schema migration có tác động |

Điểm chung: phục hồi phải diễn ra ở **đúng lớp gặp sự cố**. Tạo lại deployment sẽ không khắc phục database bị hỏng; restore toàn bộ volume có thể không cần thiết nếu chỉ một ConfigMap bị xóa.

## 5. Bản đồ kiến trúc backup AKS

Một mô hình tham chiếu:

~~~text
                        Azure Resource Manager
                       Bicep / Terraform / GitOps
                                  |
                                  v
                  AKS cluster (ứng dụng đang chạy)
                    |               |             |
                    v               v             v
             K8s resources     PVC/PV data     External services
             Namespace/CRD     Azure Disk      SQL/Blob/Key Vault
                    |               |             |
                    |               |             |
                    +---- Backup/restore ----+    +-- Backup/PITR riêng
                              |
                              v
                    Recovery points
                  + policy + retention
                              |
                              v
                Backup vault / backup storage
                (theo loại giải pháp đã chọn)
                              |
                              v
                     Cluster phục hồi
                              |
                              v
              Kiểm thử dữ liệu, auth, networking
                              |
                              v
                    Chuyển traffic có kiểm soát
~~~

**Không phải một công cụ duy nhất tự sao lưu mọi phần trong sơ đồ.** Azure Backup for AKS, snapshot của CSI driver, công cụ Kubernetes như Velero, database-managed backup và GitOps có những phạm vi khác nhau.

Trong thiết kế production, hãy làm một **backup coverage matrix** ghi rõ mỗi resource được bảo vệ bằng cơ chế nào, ai sở hữu và cách chứng minh restore thành công.

## 6. Azure Backup for AKS là gì?

**Azure Backup for AKS** là giải pháp Azure Backup được thiết kế để bảo vệ những thành phần của cụm AKS theo phạm vi tính năng và cấu hình được hỗ trợ. Nó dùng các tài nguyên Azure Backup như **Backup vault**, **backup policy**, **backup instance/recovery points** và thành phần tích hợp trong cluster, cùng cơ chế bảo vệ dữ liệu volume phù hợp.

Tùy phiên bản và phạm vi hỗ trợ, giải pháp có thể sao lưu các tài nguyên Kubernetes và dữ liệu PersistentVolume dựa trên loại lưu trữ được hỗ trợ, thường liên quan tới **Azure Disk CSI-backed persistent volumes** và snapshot. Những thành phần như Azure Files, các loại CSI driver khác, workload Windows, cluster mode đặc biệt, CRD hoặc dữ liệu ngoài cluster cần được kiểm tra riêng.

### Các thành phần cần nhận diện

| Thành phần | Vai trò |
|---|---|
| **Backup vault** | Quản lý backup instance, policy, recovery points và cơ chế bảo vệ theo dịch vụ |
| **Backup policy** | Định nghĩa lịch sao lưu, retention và các thiết lập được hỗ trợ |
| **AKS backup extension** | Thành phần triển khai trong cluster để phối hợp backup/restore theo thiết kế dịch vụ |
| **Trusted Access / role assignments** | Quan hệ truy cập, danh tính và quyền cần thiết giữa dịch vụ backup, cluster và tài nguyên Azure |
| **Storage account/backup storage** | Lưu phần artifact/cấu hình backup khi giải pháp yêu cầu |
| **Snapshot resource group** | Nơi quản lý snapshot cho volume theo cấu hình áp dụng |
| **Backup instance** | Đối tượng được bảo vệ và trạng thái lịch sử backup |
| **Recovery point** | Điểm dữ liệu/tài nguyên có thể dùng trong thao tác phục hồi được hỗ trợ |

Tên tài nguyên, trường cấu hình, loại retention và mô hình lưu recovery point có thể phát triển theo Azure Backup. Hãy đối chiếu **tài liệu hiện hành của tính năng AKS backup và ma trận hỗ trợ region/cluster/storage** trước khi triển khai.

### Những điều Azure Backup for AKS không tự làm

- Không tự sao lưu và phục hồi nội dung của **Azure SQL, PostgreSQL, Cosmos DB** hay Blob dữ liệu bên ngoài cluster.
- Không tự lưu đầy đủ **ARM configuration** của VNet, private endpoint, firewall, Azure Load Balancer, DNS hay identity ở mọi tình huống.
- Không đảm bảo ứng dụng đã nhất quán về transaction chỉ vì snapshot volume thành công.
- Không cam kết mọi loại PVC/CSI driver đều có thể restore như nhau.
- Không tự tạo lại external secrets hoặc bảo đảm khóa mã hóa/Workload Identity hoạt động.
- Không thay thế kiểm thử khôi phục định kỳ và runbook vận hành.

## 7. Phân biệt Backup vault và Recovery Services vault

Trong Azure, không phải mọi loại backup đều dùng cùng một vault hoặc cùng CLI/API. Ví dụ, backup VM truyền thống thường liên quan tới **Recovery Services vault**, còn những giải pháp Azure Data Protection như **Azure Backup for AKS** dùng **Backup vault** trong phạm vi hỗ trợ.

| Dịch vụ | Nơi quản lý backup thường gặp | Cần lưu ý |
|---|---|---|
| Azure Backup for AKS | Backup vault và thành phần backup tích hợp AKS | Lịch, retention, phạm vi K8s resources/PVs theo ma trận hỗ trợ |
| Azure VM backup | Recovery Services vault theo khả năng dịch vụ | Bảo vệ VM/disk theo mô hình Azure Backup VM |
| Azure Database for PostgreSQL/Azure SQL | Backup/PITR của dịch vụ dữ liệu hoặc giải pháp hỗ trợ | Khôi phục theo điều kiện DB riêng |
| Blob Storage | Versioning/soft delete/backup hoặc cơ chế riêng phù hợp | Không nằm mặc định trong một AKS backup |

Đừng nhầm việc có Recovery Services vault trong subscription là đã backup dữ liệu ứng dụng trên AKS. **Phải kiểm tra backup instance đúng đối tượng**.

## 8. PersistentVolume, PVC và CSI VolumeSnapshot

Trong Kubernetes:

- **PersistentVolume (PV)** đại diện cho dung lượng lưu trữ được cung cấp cho cluster.
- **PersistentVolumeClaim (PVC)** là yêu cầu sử dụng storage của workload.
- **StorageClass** mô tả cách provision volume.
- **CSI driver** kết nối Kubernetes với backend storage.
- **VolumeSnapshotClass**, **VolumeSnapshot** và **VolumeSnapshotContent** là các thành phần liên quan đến snapshot CSI nếu cluster/storage driver hỗ trợ.

~~~text
StatefulSet / Pod
      |
      v
     PVC
      |
      v
      PV
      |
      v
CSI storage driver
      |
      v
Azure Disk / loại storage được hỗ trợ

VolumeSnapshot -> SnapshotContent -> Backend snapshot
~~~

Một **VolumeSnapshot** Kubernetes là đối tượng khai báo yêu cầu snapshot và thông tin trạng thái. Nó không tự thay thế một chiến lược backup với lịch, retention, lưu trữ độc lập và khả năng phục hồi sau mất cluster.

### Kiểm tra môi trường có hỗ trợ snapshot không

~~~bash
kubectl get storageclass
kubectl get pv
kubectl get pvc --all-namespaces
kubectl get volumesnapshotclass
kubectl get volumesnapshot --all-namespaces
~~~

Những lệnh **get volumesnapshotclass/volumesnapshot** có thể trả lỗi nếu cluster không cài CRDs/CSI snapshot components; đây là dấu hiệu phải kiểm tra điều kiện hỗ trợ, không tự cài thêm thành phần trong production chỉ để chạy lab.

### PV reclaim policy

StorageClass/PV có chính sách **Retain** hoặc **Delete** và các thuộc tính reclaim liên quan. Nếu workload xóa PVC trong lúc PV dùng reclaim policy **Delete**, storage backend có thể bị xóa theo luồng provisioner. Chọn Retain cho mọi PV không phải giải pháp toàn diện: nó có thể tạo tài nguyên mồ côi và chi phí kéo dài.

Trước khi phục hồi, kiểm tra **reclaim policy, finalizers, binding mode, volume affinity, access mode và StorageClass**. Việc khôi phục dữ liệu vào PVC mới phải tránh vô tình ghi đè hoặc xóa nguồn còn dùng.

## 9. Ví dụ manifest CSI VolumeSnapshot

Đoạn YAML sau minh họa snapshot của PVC **orders-data** tại namespace **shop-data**. Chỉ sử dụng trong cluster lab khi CSI driver và snapshot class được hỗ trợ và đã xác minh.

~~~yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: orders-data-snap-lab
  namespace: shop-data
spec:
  volumeSnapshotClassName: "<SUPPORTED_SNAPSHOT_CLASS>"
  source:
    persistentVolumeClaimName: orders-data
~~~

Chuỗi placeholder trong ví dụ **không phải snapshot class hợp lệ**. Thay bằng tên được kiểm tra từ cluster. Thao tác tạo snapshot có thể phát sinh chi phí lưu trữ và cần quyền tương ứng.

### Kiểm tra trạng thái snapshot

~~~bash
kubectl get volumesnapshot -n shop-data
kubectl describe volumesnapshot -n shop-data orders-data-snap-lab
~~~

Trường status như **readyToUse** và liên kết **VolumeSnapshotContent** có thể giúp đánh giá snapshot đã sẵn sàng. Tuy nhiên, **readyToUse=true không chứng minh dữ liệu database nhất quán về nghiệp vụ**.

### Phục hồi ra PVC mới, không ghi đè tùy tiện

Ví dụ dùng VolumeSnapshot làm nguồn tạo PVC mới:

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: orders-data-restore-lab
  namespace: shop-data
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: "<SUPPORTED_STORAGE_CLASS>"
  resources:
    requests:
      storage: 64Gi
  dataSource:
    name: orders-data-snap-lab
    kind: VolumeSnapshot
    apiGroup: snapshot.storage.k8s.io
~~~

Đây là **mẫu minh họa**. Loại volume, kích thước, vùng/zone, snapshot class và StorageClass phải tương thích. Việc restore qua PVC mới phụ thuộc CSI driver và khả năng backend; không phải mọi tổ hợp cluster/region/zone đều hoạt động.

**Không mount cùng một PVC ReadWriteOnce trên nhiều node độc lập rồi giả định an toàn.** Quy tắc gắn đĩa và access modes cần được kiểm tra. Với cơ sở dữ liệu, nên phục hồi lên instance cô lập rồi xác minh trước khi chuyển traffic.

## 10. Crash-consistent và application-consistent khác nhau

**Crash-consistent snapshot** gần với trạng thái dữ liệu trên đĩa tại một thời điểm, giống khi hệ điều hành hoặc ứng dụng mất điện đột ngột. File system và database có thể cần replay journal/WAL khi khởi động lại.

**Application-consistent backup** phối hợp với ứng dụng để dữ liệu ở trạng thái phù hợp, ví dụ flush buffer, checkpoint, tạm dừng ghi hoặc sử dụng giao diện backup của database.

| Tính nhất quán | Bảo vệ gì | Giới hạn |
|---|---|---|
| Snapshot crash-consistent | Trạng thái block storage tại thời điểm snapshot | Không chắc giao dịch trên nhiều disk/service đã đồng bộ |
| Application-consistent | Dữ liệu sau thao tác phối hợp ứng dụng | Cần hooks/backup protocol được thiết kế đúng |
| Database-native backup/PITR | Dữ liệu logic/physical theo cơ chế database và log | Cần cấu hình, retention và quy trình restore riêng |
| Multi-service consistency | Tính đúng đắn giữa DB, queue, Blob, cache và ứng dụng | Cần điểm chốt nghiệp vụ, transaction hoặc quy trình đối chiếu |

### Vì sao snapshot ba đĩa không tự tạo một điểm giao dịch?

Một database có dữ liệu trên nhiều volume: volume dữ liệu, WAL và các file bổ sung. Nếu snapshot được tạo lần lượt, các snapshot có thể phản ánh những thời điểm khác nhau. Database có thể không phục hồi được hoặc cần xử lý thủ công.

Vì vậy:

1. Xác định ứng dụng có thể chịu crash-consistent restore không.
2. Nếu cần, dùng **database-native backup**, quiesce hooks hoặc cơ chế storage hỗ trợ application-consistent snapshot.
3. Với multi-volume, kiểm tra khả năng coordinated snapshot và trình tự nhất quán.
4. Luôn **test restore** và kiểm tra ràng buộc dữ liệu.

**Không tuyên bố mọi CSI snapshot của Azure Disk là application-consistent.** Điều này phụ thuộc cách ứng dụng phối hợp và tính năng cụ thể.

## 11. Database trong AKS: nên backup theo database hay đĩa?

Ví dụ PostgreSQL chạy trong StatefulSet. Có ít nhất ba lựa chọn:

| Chiến lược | Phạm vi | Phù hợp |
|---|---|---|
| CSI VolumeSnapshot | Dữ liệu trên disk tại thời điểm snapshot | Khôi phục nhanh volume khi crash-consistent được chấp nhận và đã test |
| Database logical backup | Schema/dữ liệu được export bằng công cụ như pg_dump | Migration/restore logic, DB vừa và nhỏ tùy yêu cầu |
| Physical backup + WAL/PITR | Bản backup vật lý kết hợp transaction log | RPO thấp, restore theo thời điểm với cấu hình phù hợp |

Một snapshot của volume PostgreSQL **không tự thay thế** WAL archiving khi yêu cầu RPO 5 phút và PITR. Ngược lại, pg_dump định kỳ mỗi ngày có thể không đáp ứng RPO 15 phút.

### Ví dụ kiểm tra backup logic PostgreSQL

Các lệnh sau chỉ minh họa **công cụ database**, không phải lệnh chạy trực tiếp trên AKS production:

~~~bash
# Trên môi trường quản trị được cấp quyền, cung cấp kết nối DB an toàn.
pg_dump --format=custom \
  --dbname="<POSTGRES_CONNECTION_DSN>" \
  --file="orders-2026-11-20.dump"

# Kiểm tra mục lục backup, không thực hiện restore.
pg_restore --list "orders-2026-11-20.dump"
~~~

Cần bảo vệ file dump như dữ liệu production: mã hóa, RBAC, retention, checksum và lưu ở nơi độc lập phù hợp. **Lệnh pg_restore --list không chứng minh restore thành công**; cần khôi phục vào database test và kiểm tra dữ liệu.

Không đặt password trong shell history, dòng lệnh lộ công khai hay log pipeline. Dùng cơ chế xác thực/secret delivery phù hợp.

### Dịch vụ database bên ngoài AKS

Nếu ứng dụng sử dụng **Azure Database for PostgreSQL Flexible Server**, **Azure SQL**, Cosmos DB hoặc một dịch vụ được quản lý, hãy dùng khả năng backup/PITR của **dịch vụ đó** theo điều kiện hỗ trợ. Việc backup namespace AKS thường không mang theo bản sao dữ liệu của database PaaS.

## 12. GitOps và IaC là phần không thể thiếu

Backup Kubernetes resources có ích, nhưng **desired state trong Git** giúp tái tạo và kiểm soát thay đổi:

- Bicep/Terraform mô tả AKS, VNet, subnet, ACR, Key Vault, private DNS và role assignments.
- Helm/Kustomize/YAML mô tả Deployments, StatefulSets, Services, ConfigMaps, NetworkPolicies, RBAC.
- Flux/Argo CD hoặc pipeline triển khai đưa desired state vào cluster.
- Registry lưu image theo **digest/tag bất biến phù hợp**.

### Tại sao không chỉ lưu kubectl get -o yaml?

Một bản export từ cluster có thể bao gồm **status, resourceVersion, UID, managedFields, địa chỉ IP runtime, secret values** và nhiều trường không phù hợp để áp lại. Nó cũng có thể thiếu CRDs, cluster-scoped resources hoặc cấu hình hạ tầng Azure.

Khi restore từ GitOps, hãy dùng manifest nguồn được quản lý và những giá trị môi trường thích hợp. Đối với backup công cụ, cần biết nó chọn loại resource nào và có loại trừ trường không phục hồi được không.

### Cẩn thận khi GitOps chạy trong lúc restore

Nếu GitOps controller đang tự động reconcile, nó có thể:

- Xóa tài nguyên vừa restore vì không có trong Git.
- Ghi đè image/config bằng phiên bản hiện tại.
- Scale workload trước khi PVC/data đã được khôi phục.
- Khởi động database và application migration quá sớm.

Runbook cần xác định **thời điểm tạm ngừng hoặc điều chỉnh reconcile có kiểm soát**, rồi bật lại sau khi dữ liệu và manifests đã sẵn sàng.

## 13. Bảo vệ Kubernetes Secrets và danh tính

Một bản backup có chứa Kubernetes **Secret** có thể chứa token, password hoặc chứng chỉ, dù giá trị Secret trong manifest thường được biểu diễn bằng base64. **Base64 không phải mã hóa bí mật.**

Khuyến nghị:

1. Ưu tiên **Azure Key Vault**, workload identity và External Secrets/Secrets Store CSI Driver theo kiến trúc được hỗ trợ.
2. Lưu manifest tham chiếu secret trong Git, **không commit secret value**.
3. Đánh giá liệu hệ thống backup có thực sự cần chứa bản sao Secret hay có thể tái tạo an toàn từ Key Vault.
4. Nếu backup chứa Secret, mã hóa dữ liệu backup, hạn chế quyền truy cập, theo dõi audit và kiểm tra quy trình rotate sau sự cố.
5. Khi tạo cluster mới, khôi phục **OIDC issuer/workload identity trust, managed identity, federated credentials và RBAC** phù hợp; những định danh/issuer có thể khác cluster cũ.
6. Bảo vệ khóa mã hóa/Key Vault trước khi cần giải mã backup hoặc volume.

**Không khôi phục mù toàn bộ ServiceAccount token hoặc cấu hình identity cũ** sang cluster mới rồi mong quyền sẽ hoạt động như trước. Cần kiểm tra trust và identity của cluster đích.

## 14. Các bước chuẩn bị Azure Backup for AKS

Quy trình dưới đây là **khung triển khai**, không phải hướng dẫn tạo tài nguyên có thể sao chép nguyên xi vào mọi subscription. Phiên bản, region, tier hỗ trợ và lệnh cấu hình có thể thay đổi.

### Bước 1: kiểm tra tính tương thích

Xác nhận:

- AKS cluster version, node pools, Kubernetes API và addon/network settings.
- Azure Disk CSI driver, StorageClass, loại PVC/PV và snapshot support nếu muốn backup PV.
- Số namespace và những resource type cần backup.
- Region của cluster/vault/storage/snapshot và khả năng restore trong region mong muốn.
- Quota, quyền tạo snapshots và chi phí.
- Chính sách backup/retention theo mức hỗ trợ và yêu cầu RPO.

Nếu PVC dùng loại storage không nằm trong ma trận hỗ trợ của giải pháp, **không được đánh dấu dữ liệu ấy đã được bảo vệ** chỉ vì backup Kubernetes manifests thành công.

### Bước 2: thiết kế tài nguyên Azure Backup

Chuẩn bị những thành phần theo tài liệu tương ứng:

1. **Backup vault** trong subscription/resource group được phê duyệt.
2. **Backup policy** với lịch và retention phù hợp.
3. **AKS backup extension** trên cluster, kèm yêu cầu kết nối.
4. **Trusted Access** và những role assignments cần thiết.
5. Storage account/container dành cho artifact backup khi tính năng yêu cầu.
6. Snapshot resource group hoặc nơi lưu snapshot được hỗ trợ.
7. Backup instance gắn với cluster/phạm vi cần bảo vệ.

Tách quyền quản trị backup khỏi quyền ứng dụng. Một administrator của namespace không nhất thiết nên có quyền xóa backup vault/recovery points.

### Bước 3: chọn phạm vi bảo vệ

Liệt kê:

- Namespace cần bảo vệ.
- Kubernetes objects: Deployment, StatefulSet, Service, ConfigMap, CRD/custom resource và những cluster-scoped resources theo khả năng.
- PVC/PV tương thích và khối lượng dữ liệu.
- Dữ liệu cần backup riêng ở PaaS.
- Những object có tính nhạy cảm như Secret hoặc admission configuration.

Tránh áp filter quá hẹp rồi bỏ sót PVC hoặc namespace quan trọng. Ngược lại, backup mọi namespace hệ thống không cần thiết có thể tăng độ phức tạp restore và quyền truy cập.

### Bước 4: bật policy và tạo điểm backup thử nghiệm

Trong **Azure portal**, mở Backup vault/AKS backup theo tính năng hiện có, cấu hình đối tượng được bảo vệ, tần suất và retention. Chờ backup job đạt trạng thái thành công; sau đó kiểm tra **recovery point có tồn tại và thuộc đúng cluster/namespace**.

**Backup job thành công chỉ là bước đầu.** Phải test restore ra namespace/cluster thử nghiệm để xác nhận manifest, volume và dữ liệu thực tế khôi phục được.

### Bước 5: lên lịch diễn tập

Tạo lịch diễn tập phục hồi, phân công người chịu trách nhiệm, chốt bằng chứng nghiệm thu và báo cáo những phần chưa được bảo vệ. Các bài DR cần được chạy định kỳ và sau thay đổi lớn của cluster, storage driver, database hoặc policy backup.

## 15. Lệnh Azure CLI/Kubernetes để quan sát trạng thái

Các lệnh dưới đây là **read-only** đối với tài nguyên Azure/Kubernetes và phù hợp để đối chiếu trước/sau backup. Yêu cầu CLI/extension đúng phiên bản và quyền đọc phù hợp.

### Kiểm tra cluster và cấu hình

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az aks show \
  --resource-group "<AKS_RESOURCE_GROUP>" \
  --name "<AKS_CLUSTER_NAME>" \
  --query "{name:name,location:location,kubernetesVersion:kubernetesVersion,provisioningState:provisioningState}" \
  --output json
~~~

### Kiểm tra Backup vault và backup instances

~~~bash
az dataprotection backup-vault list \
  --resource-group "<BACKUP_RESOURCE_GROUP>" \
  --output table

az dataprotection backup-instance list \
  --resource-group "<BACKUP_RESOURCE_GROUP>" \
  --vault-name "<BACKUP_VAULT_NAME>" \
  --output json
~~~

Nhóm lệnh **az dataprotection** có thể cần phiên bản Azure CLI/extension phù hợp. Nếu môi trường báo lệnh hoặc tham số không tồn tại, kiểm tra tài liệu CLI và help thay vì suy đoán backup không được cấu hình.

### Kiểm tra dữ liệu K8s

~~~bash
kubectl get namespaces
kubectl get deployments,statefulsets -A
kubectl get pvc -A
kubectl get pv
kubectl get storageclass
kubectl get volumesnapshot -A
~~~

Không dùng **kubectl get all** như bằng chứng liệt kê mọi tài nguyên: lệnh đó **không bao gồm** tất cả NetworkPolicies, PVC, Secrets, CRDs và các đối tượng khác.

### Kiểm tra một PVC và workload

~~~bash
kubectl describe pvc -n shop-data orders-data
kubectl get statefulset -n shop-data
kubectl get pods -n shop-data -o wide
kubectl get events -n shop-data --sort-by=.lastTimestamp
~~~

Cần quyền **kubeconfig** tới cluster mục tiêu. Lệnh lấy thông tin xác thực như **az aks get-credentials** thay đổi kubeconfig cục bộ, nên không được xem là lệnh đọc hoàn toàn không có tác động tới môi trường người dùng; chỉ chạy khi được cấp quyền và chỉ định context đúng.

### Cẩn thận với context

Trước mọi thao tác restore hoặc apply:

~~~bash
kubectl config current-context
kubectl cluster-info
~~~

Đây là kiểm tra an toàn cơ bản để không lỡ áp manifest lên production khi đang định khôi phục vào cluster lab.

## 16. Xây dựng backup policy có thể vận hành

Một chính sách nên có:

| Thuộc tính | Ví dụ cần ghi lại |
|---|---|
| Workload | orders-api / orders-db |
| Owner | Nhóm nền tảng và chủ sở hữu dữ liệu |
| Backup scope | Namespaces, K8s resources, volume và dữ liệu ngoài cluster |
| Schedule | Theo RPO đã phê duyệt, tính cả thời gian hoàn thành backup |
| Retention | Ngắn hạn/dài hạn theo yêu cầu nghiệp vụ/pháp lý |
| Recovery target | Restore tại cluster cũ, cluster mới, namespace khác hoặc region khác nếu hỗ trợ |
| Encryption | Dữ liệu backup, khóa và quyền giải mã |
| Isolation | Phân tách người quản lý workload với người xóa recovery points |
| Validation | Restore drill, checksum, query nghiệp vụ, health checks |
| Alerts | Backup failures, thiếu recovery point, retention bất thường |
| Budget | Chi phí storage, snapshot, vault, transfer, restore test |

### Ví dụ thiết kế hai lớp backup

Hệ thống có database nội bộ và tài liệu Blob:

- **Kubernetes backup:** mỗi ngày hoặc theo tần suất được phê duyệt cho manifests và PV đủ điều kiện.
- **Database PITR:** log và backup riêng để đạt RPO thấp hơn khoảng cách giữa các snapshot.
- **Blob Storage:** cơ chế versioning/soft delete/backup hoặc retention phù hợp với dữ liệu.
- **IaC/GitOps:** lưu và kiểm thử khả năng tái tạo cluster.
- **DR drill:** khôi phục dịch vụ đầy đủ theo lịch.

Không sao chép thời gian ấn định từ ví dụ sang production. RPO 15 phút yêu cầu thực sự có cơ chế đáp ứng 15 phút; backup PV mỗi 24 giờ rõ ràng không đủ nếu không có lớp log/PITR khác.

## 17. Quy trình phục hồi ứng dụng theo lớp

Một **restore runbook** cần bắt đầu bằng việc phân loại sự cố và xác định điểm khôi phục phù hợp.

### Giai đoạn A: đánh giá sự cố

1. Xác định sự cố là mất Kubernetes resources, mất volume, hỏng database hay mất cluster/region.
2. Xác định **thời điểm dữ liệu tốt cuối cùng** và nguy cơ phát tán sai lệch.
3. Dừng hoặc hạn chế hoạt động ghi vào hệ thống bị lỗi khi cần để tránh ghi chồng dữ liệu.
4. Chọn backup/recovery point có nguồn gốc rõ, retention còn hiệu lực và khả năng restore.
5. Xác định đích phục hồi: namespace riêng, cluster mới hay database mới.

Không restore thẳng vào production khi chưa biết backup có sạch trước ransomware hoặc không biết database đã bị ghi sai từ lúc nào.

### Giai đoạn B: chuẩn bị hạ tầng đích

1. Tạo hoặc xác nhận subscription/resource group và AKS cluster đích bằng IaC.
2. Bảo đảm Kubernetes version/API compatibility, node pools, CSI drivers, ingress/egress và StorageClass.
3. Chuẩn bị VNet, subnet, route, DNS, private endpoints, network policy và load balancing.
4. Cấu hình ACR image pull, Workload Identity, Key Vault, RBAC và certificates.
5. Cài CRDs/operators cần thiết **theo đúng phiên bản được hỗ trợ** trước khi restore custom resources.

Lỗi phổ biến là restore PVC trước khi cluster có StorageClass/CSI driver, hoặc restore CustomResource khi CRD/operator chưa tồn tại.

### Giai đoạn C: phục hồi dữ liệu

1. Xác nhận nguồn recovery point/snapshot/DB backup.
2. Khôi phục PV/PVC hoặc database vào nơi cô lập, tránh ghi đè dữ liệu nguồn có giá trị điều tra.
3. Kiểm tra mount, filesystem, permission, key mã hóa và điều kiện nhất quán.
4. Nếu là database, chạy quy trình WAL replay/PITR hoặc restore theo tài liệu database.
5. Kiểm tra integrity, số bản ghi, schema, dữ liệu tham chiếu và thời điểm phục hồi.

### Giai đoạn D: phục hồi ứng dụng

1. Áp manifests theo đúng thứ tự phụ thuộc.
2. Kiểm tra Secret references/Workload Identity.
3. Kết nối pod tới volume đã khôi phục và dịch vụ PaaS.
4. Cho workload khởi động với readiness/liveness/startup probes phù hợp.
5. Xác nhận NetworkPolicy, DNS và external services.
6. Đánh giá GitOps reconciliation trước khi bật tự động.

### Giai đoạn E: nghiệm thu và chuyển traffic

1. Kiểm thử API/transaction đọc và ghi trên môi trường phục hồi.
2. So sánh dữ liệu với recovery point, tính số giao dịch bị mất theo RPO.
3. Kiểm tra log, monitoring và khả năng xử lý backlog.
4. Chuyển lưu lượng qua DNS/gateway/load balancer theo kế hoạch.
5. Theo dõi lỗi sau cutover; duy trì kế hoạch quay lại khi điều kiện cho phép.
6. Ghi nhận thời gian khôi phục thực tế và những vấn đề phát sinh.

## 18. Thứ tự khôi phục cho ứng dụng có StatefulSet

Ví dụ một hệ thống đơn hàng gồm:

~~~text
AKS cluster
  |
  +-- orders-api Deployment
  +-- orders-db StatefulSet
  |     +-- PVC orders-data
  +-- orders-worker Deployment
  +-- ConfigMap / Secret references
  +-- Services / Ingress / NetworkPolicy
  |
  +-- Azure Key Vault
  +-- Azure Service Bus queue
  +-- Blob Storage
~~~

Một trình tự hợp lý:

1. Restore các hạ tầng nền: cluster, node pools, CSI, namespaces, CRDs/operators.
2. Khôi phục database và volume vào môi trường không phục vụ traffic công cộng.
3. Xác minh database khởi động và schema/records phù hợp.
4. Khôi phục Secrets/identity từ nguồn được tin cậy, không khôi phục credential đã bị lộ.
5. Tạo Services/NetworkPolicies và cho API kết nối thử tới database.
6. Chỉ bật worker tiêu thụ queue khi tránh xử lý lại job gây nhân đôi và khi database đã ổn định.
7. Kiểm thử end-to-end, sau đó mở ingress/chuyển traffic.

### Vì sao không khởi động worker đầu tiên?

Nếu worker đang tiêu thụ Service Bus message mà database vừa được restore về thời điểm cũ, nó có thể ghi lại dữ liệu, xử lý message trùng hoặc thực hiện side effect lần thứ hai. Cần một **reconciliation strategy** giữa message broker, job ledger và database.

Một số message có thể đã được complete trong broker nhưng DB restore về trạng thái trước lúc ghi kết quả; ngược lại, message còn trong queue nhưng side effect ở hệ thống ngoài đã thực hiện. Backup AKS không tự giải quyết distributed transaction này.

## 19. Phục hồi sang namespace khác hoặc cluster mới

**Restore in-place** và **restore to alternate location** phục vụ các mục tiêu khác nhau.

| Kiểu | Khi dùng | Rủi ro |
|---|---|---|
| Restore namespace gốc | Khôi phục sau xóa nhầm tài nguyên nhỏ | Có thể ghi đè object hoặc xung đột controller đang chạy |
| Restore namespace mới | Kiểm chứng backup mà không ảnh hưởng production | Hostnames, Secrets, Service names, PVC references cần chỉnh |
| Restore cluster mới cùng region | Test DR/mất cluster | Cần tái tạo hạ tầng, CSI, identity, DNS, ACR |
| Restore region khác | Kịch bản mất cả region | Cần bản backup phục hồi được ở region đích, networking và data replica |

Khả năng thay namespace, chọn resource, phục hồi volume hoặc đổi location **phụ thuộc công cụ backup và phiên bản tính năng**. Không mặc định Azure Backup for AKS cho phép mọi tổ hợp cross-region hoặc cross-subscription restore.

### Xử lý đụng độ tên tài nguyên

Một cluster thử nghiệm có thể đã tồn tại Service **orders-db**, PVC **orders-data** hoặc CRD trùng tên. Khi restore, phải chọn chính sách **skip/replace/map** phù hợp với công cụ và tránh ghi đè dữ liệu đang hoạt động.

Với PVC, lựa chọn an toàn thường là restore ra tên mới hoặc namespace mới rồi xác minh, thay vì cố thay volume đang được StatefulSet ghi dữ liệu.

## 20. Disaster recovery khi mất region

Mất region khác với một node pool hỏng. Những tài nguyên như cluster, VNet, private DNS resolver, storage, database và backup storage có thể cùng bị ảnh hưởng.

~~~text
Primary region
  AKS + DB + Storage + Backup policy
            |
            | Backup/replication phù hợp và được kiểm thử
            v
Secondary region
  Network + AKS template + image access
  DB recovery target + data restore
  Secrets/identity + DNS + traffic failover
~~~

### Những yêu cầu riêng của cross-region recovery

- Kiểm tra **backup tier, loại recovery point và khả năng restore xuyên region** của Azure Backup for AKS/volume storage.
- Kiểm tra nơi giữ snapshot hoặc artifact; snapshot tại region nguồn có thể không giúp nếu region đó không truy cập được.
- Có chiến lược **dữ liệu riêng** cho database PaaS, Blob và các hệ thống bên ngoài.
- Đảm bảo image trong ACR có thể được pull tại region đích, kể cả khi registry gốc bị ảnh hưởng; đánh giá geo-replication khi phù hợp.
- Chuẩn bị quota và năng lực AKS/node pools ở region đích.
- Cấu hình mới cho Workload Identity federation, DNS, Key Vault, private endpoint, certificates và địa chỉ backend.
- Thiết kế chuyển DNS/traffic; không coi Azure Traffic Manager/Front Door là cơ chế restore dữ liệu.
- Thử RTO/RPO trên kịch bản mất region, không chỉ restore cùng region.

**Không tuyên bố backup cùng region là DR xuyên region** khi chưa có bằng chứng bản dữ liệu có thể truy cập và phục hồi ở region thứ hai.

## 21. Diễn tập phục hồi (restore drill) như thế nào?

Một backup chỉ có giá trị khi bạn đã thử phục hồi trong điều kiện gần với sự cố thật. Nên có **restore drill** theo lịch và sau những thay đổi lớn.

### Bước 1: chọn dữ liệu thử và kịch bản

Ví dụ:

- Namespace **orders-dr-test**, không chứa dữ liệu khách hàng thật.
- Một PVC có dữ liệu mẫu và checksum.
- Một database test có bảng **orders** và một số bản ghi giả.
- Một ingress riêng không phục vụ người dùng sản xuất.

Chọn hai kịch bản: **khôi phục một namespace/PVC** và **khôi phục sang cluster mới**. Nếu yêu cầu DR liên vùng, thêm diễn tập ở region đích.

### Bước 2: ghi trạng thái gốc

Thu thập bằng chứng:

~~~text
Application release: v1.7.3 (minh họa)
Kubernetes version: theo cluster lab
Namespace: orders-dr-test
PVC: orders-data-test
Database:
  order_count = 1250
  last_order_id = TEST-1250
Sample file checksum: SHA-256 đã lưu trước backup
Backup recovery point: <RECOVERY_POINT_ID>
~~~

Không đưa connection string, account key, token hay dữ liệu cá nhân vào hồ sơ diễn tập.

### Bước 3: tạo/kiểm tra recovery point

Kiểm tra backup jobs, recovery points, retention và phạm vi volume/resources. Chỉ tiến hành thử restore khi đã xác định backup đúng nguồn và thuộc tập dữ liệu test.

### Bước 4: khôi phục an toàn

Restore tới namespace hoặc cluster **cô lập**. Không ngắt hệ thống production để kiểm tra bài lab. Đối với database test, dùng instance được phép phục hồi; không ghi đè dữ liệu phục vụ người dùng.

### Bước 5: kiểm thử tính đúng đắn

| Kiểm tra | Tiêu chí PASS |
|---|---|
| Resource restore | Deployment/StatefulSet/Service/PVC xuất hiện đúng phạm vi |
| PVC binding | PVC Bound, mount hoạt động |
| Dữ liệu tệp | File mẫu tồn tại, checksum trùng |
| Database | Schema hợp lệ, dữ liệu và ràng buộc phù hợp |
| Application health | Readiness và truy vấn nghiệp vụ thành công |
| Secrets/identity | Worker/API có quyền đúng, không dùng secrets cũ bị lộ |
| Network | DNS, NetworkPolicy, ingress/egress và private endpoints phù hợp |
| RPO | Mốc dữ liệu khôi phục đáp ứng RPO đã định |
| RTO | Tổng thời gian từ nhận biết sự cố tới dịch vụ dùng được đáp ứng RTO |
| Monitoring | Logs, metrics, alerts tiếp tục hoạt động |

### Bước 6: rút kinh nghiệm

Ghi lại thời gian từng bước, lỗi, thao tác thủ công, phụ thuộc không có trong tài liệu và biện pháp cải tiến. Một restore drill thất bại là **phát hiện hữu ích**; không sửa báo cáo thành công chỉ vì bước tạo pod đã chạy.

## 22. Kiểm tra quyền và bảo vệ backup khỏi bị xóa

### Nguyên tắc đặc quyền tối thiểu

Phân tách các nhóm:

| Nhóm | Quyền cần xem xét |
|---|---|
| Nhóm nền tảng | Quản trị AKS và hạ tầng theo phạm vi cần |
| Nhóm ứng dụng | Xem workload/triển khai, không tự ý xóa recovery points |
| Nhóm backup | Quản lý backup policy/instance và thực hiện restore theo phê duyệt |
| Nhóm bảo mật | Quản trị yêu cầu bảo vệ, giám sát thay đổi/vô hiệu hóa backup |
| Nhóm kiểm toán | Quyền xem báo cáo và bằng chứng, không có quyền sửa/xóa dữ liệu |

Azure RBAC, Kubernetes RBAC, managed identities và Trusted Access cần được thiết kế nhất quán. **Không cấp Owner trên toàn subscription chỉ để một extension tạo snapshot** nếu dịch vụ hỗ trợ phân quyền hẹp hơn.

### Rủi ro ransomware và credential compromise

Khi kẻ tấn công có quyền cao, họ có thể cố:

- Xóa hoặc vô hiệu hóa backup policy.
- Xóa recovery points hoặc tài nguyên snapshot.
- Thay khóa mã hóa, xóa Key Vault hoặc làm backup không thể giải mã.
- Ghi dữ liệu độc hại vào nguồn để backup kế tiếp chứa dữ liệu đã nhiễm.
- Tắt audit log, phá DNS/route hoặc thay identity.

Các kiểm soát cần đánh giá:

1. Quyền xóa/sửa backup tách khỏi quyền vận hành ứng dụng.
2. Bảo vệ việc xóa vault/recovery points bằng các tính năng như **soft delete, immutability, multi-user authorization** khi loại vault/datasource/region hỗ trợ.
3. Giữ bản sao/điểm khôi phục độc lập về failure domain theo yêu cầu DR.
4. Theo dõi Activity Log và cảnh báo thay đổi cấu hình bảo vệ.
5. Bảo vệ khóa/identity cần để restore và kiểm tra kế hoạch khôi phục khi tenant/credential bị xâm nhập.
6. Thử restore bằng danh tính/thiết bị vận hành dự phòng theo quy trình được phê duyệt.

**Không giả định mọi tính năng chống xóa của Azure Backup đều được hỗ trợ giống nhau cho AKS**. Phải xác minh chính sách và loại backup cụ thể.

## 23. Backup private cluster và networking

AKS private cluster, private endpoints cho Azure Storage hoặc vault, Azure Firewall và custom DNS làm kiến trúc an toàn hơn nhưng cũng khiến backup/restore phụ thuộc vào đường mạng.

Kiểm tra:

- Backup extension có được triển khai và hoạt động trong cluster?
- Agent/extension có quyền và đường kết nối tới các dịch vụ backup cần thiết?
- CSI driver có tạo được snapshot qua Azure control plane?
- Storage account chứa artifact backup có firewall/private endpoint và DNS đúng?
- Restore target có thể truy cập image registry, Key Vault, database và storage?
- NSG, UDR, outbound firewall có chặn endpoint cần thiết?
- Các workload dùng Workload Identity có cấu hình trust đúng sau khi thay cluster?

Không mở toàn bộ outbound Internet hoặc bật **Allow all networks** cho Storage chỉ vì backup job thất bại. Phải phân biệt lỗi **DNS, TCP/443, RBAC, Trusted Access, quota, CSI** và incompatibility.

### DNS sau khi khôi phục sang cluster mới

Một workload gọi Blob/Database qua hostname chuẩn có thể vẫn cần private DNS zone/VNet link/forwarder của region hoặc VNet đích. Việc container khởi động thành công không chứng minh nó có thể truy cập endpoint dữ liệu.

## 24. Monitoring và cảnh báo backup

Một chính sách hoạt động ổn định cần quan sát cả **backup** lẫn **restore**.

| Tín hiệu | Vì sao cần |
|---|---|
| Backup job success/failure | Phát hiện lịch backup chạy lỗi |
| Last successful recovery point | Xác minh RPO còn được đáp ứng |
| Recovery point age | Đo khoảng cách từ backup hợp lệ gần nhất tới hiện tại |
| PV coverage | Phát hiện volume chưa có bảo vệ |
| Snapshot failures | Xác định lỗi CSI/storage/quota/permissions |
| Backup storage growth | Theo dõi dung lượng và chi phí |
| Restore drill success | Đo tính khả dụng thực tế của backup |
| Restore time | So sánh với RTO mục tiêu |
| Policy/vault changes | Phát hiện thay đổi lịch/retention ngoài phê duyệt |
| Failed data validation | Phát hiện backup có tồn tại nhưng dữ liệu không hợp lệ |

### Kịch bản cảnh báo

- Không có backup thành công trong một khoảng thời gian vượt ngưỡng RPO.
- Backup job thất bại liên tục qua nhiều chu kỳ.
- Một PVC mới được tạo nhưng chưa vào danh sách backup.
- Backup extension hỏng sau khi nâng cấp AKS.
- Volume snapshot bị kẹt, chưa **readyToUse**.
- Thay đổi retention hoặc xóa backup instance trái quy trình.
- Restore drill gần nhất không đạt RTO/RPO.

Azure Monitor, Azure Backup Center, diagnostic settings và Activity Log có những công cụ quan sát phù hợp theo dịch vụ. Không mặc định mọi số liệu nghiệp vụ ở bảng trên đều có metric mặc định: một số cần dashboard/inventory riêng.

## 25. Xử lý lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Backup báo thành công nhưng mất dữ liệu database | Chỉ backup manifests hoặc snapshot không có nhất quán ứng dụng | Kiểm tra backup scope, PV, DB logs và restore drill |
| Không backup được PVC | CSI driver/volume type không hỗ trợ hoặc thiếu quyền snapshot | Xem StorageClass, PV, Backup compatibility và lỗi job |
| Snapshot stuck Pending | VolumeSnapshotClass sai, CSI snapshot controller/driver lỗi | Xem describe VolumeSnapshot và CSI events |
| Backup extension không chạy | Image pull, DNS, quyền hoặc compatibility version | Xem pods, events, identity và tài liệu tính năng |
| Backup job lỗi quyền | Thiếu role assignments/Trusted Access | Đối chiếu identity, resource scope và request ID |
| Không restore được sang cluster khác | Kubernetes/CSI/region/backup tier không tương thích | Kiểm tra support matrix, target config và recovery point |
| PVC restore không Bound | StorageClass sai, zone/volume affinity, quota hoặc snapshot không hợp lệ | Xem PVC/PV events và storage provisioning |
| Pod lên nhưng app không Ready | ConfigMap/Secrets, database, ingress hoặc image khác | Kiểm tra logs, probes, network và image digest |
| Database khởi động nhưng mất giao dịch gần nhất | RPO thực tế không đáp ứng hoặc PITR chưa hoạt động | Đối chiếu last recovery point và transaction log |
| Khôi phục Secret nhưng app lỗi 401/403 | Workload Identity/Key Vault trust chưa đúng, secret cũ hết hạn | Kiểm tra issuer, RBAC và secret rotation |
| GitOps xóa resource vừa restore | Manifest không có trong Git hoặc reconcile chạy sai thời điểm | Kiểm tra nguồn desired state và quy trình restore |
| Không thể xóa recovery points | Retention/soft delete/immutability hoặc policy khóa | Kiểm tra quyền và hạn chế bảo vệ, không tìm cách bypass |
| Backup làm tăng chi phí đột ngột | Snapshot nhiều, retention dài, DR drills hoặc log lớn | Xem usage/cost theo vault, storage và workload |
| Restore thành công nhưng traffic lỗi | DNS, gateway, certificate, ingress hoặc NetworkPolicy | Kiểm tra end-to-end và cutover route |

### Chẩn đoán theo từng lớp

1. **Backup configuration:** job có bảo vệ đúng namespace/resource/PV không?
2. **Storage:** volume type, snapshot status, size, zone, quota có hợp lệ không?
3. **Security:** identity/role/Trusted Access/Key Vault có đúng không?
4. **Kubernetes:** CRD/StorageClass/namespace/Deployment đã sẵn sàng chưa?
5. **Application:** database schema, log, HTTP health và business transaction có hợp lệ không?
6. **External services:** Blob/SQL/Service Bus/DNS/registry có đúng endpoint và trạng thái không?
7. **DR objectives:** thời gian và điểm dữ liệu phục hồi có đáp ứng RTO/RPO không?

Đừng chỉ sửa lỗi PVC Pending bằng cách đổi bừa reclaimPolicy hoặc xóa PV cũ: có thể làm mất dữ liệu còn khả năng khôi phục.

## 26. Backup và phục hồi queue, sự kiện và job nền

Đối với hệ thống event-driven chạy trên AKS, dữ liệu không chỉ nằm trong database:

- Service Bus Queue giữ công việc chưa xử lý.
- Blob Storage giữ input/output của pipeline.
- Job ledger ghi trạng thái xử lý.
- Azure Functions/worker có thể xử lý lại sau khi restore.

### Vấn đề không thể giải quyết bằng snapshot đơn lẻ

Giả sử job J đã gửi hóa đơn tới hệ thống đối tác và sau đó đánh dấu SUCCEEDED trong DB. Nếu DB được restore về trước thời điểm đánh dấu, worker có thể gửi lại hóa đơn, gây tác động trùng. Ngược lại, nếu queue message đã bị complete còn DB mất record, một phần công việc có thể không được tái tạo.

Giải pháp cần:

1. **Idempotency key** bền vững cho mỗi nghiệp vụ.
2. Transaction/outbox/inbox pattern khi phù hợp.
3. Reconciliation giữa nguồn sự kiện, queue, ledger và kết quả.
4. Thứ tự khởi động worker sau khi phục hồi DB.
5. Khả năng replay có kiểm soát, không phát lại hàng loạt mà không kiểm tra.
6. Chỉ mở traffic khi dữ liệu đã được đối chiếu.

**RPO trên một database không tự đồng nghĩa RPO của toàn pipeline** nếu Blob và queue được bảo vệ bởi cơ chế khác nhau.

## 27. Chi phí backup AKS

Các yếu tố chi phí cần dự toán:

- Dung lượng snapshot của Azure Disks hoặc storage backend.
- Dung lượng artifact Kubernetes/backup và thời hạn lưu.
- Azure Backup vault/backup instances và số recovery points theo biểu phí áp dụng.
- Backup tier lưu trữ, bản sao hoặc chuyển region theo hỗ trợ.
- Tài nguyên của backup extension/agent nếu tiêu thụ CPU/RAM.
- Dung lượng backup/PITR riêng của database PaaS và Blob Storage.
- Network/egress/cross-region transfer, ACR và dịch vụ phụ trợ.
- Azure Monitor/Log Analytics, retention của log.
- AKS cluster/node pools tạm thời dùng để test restore.

### Đánh đổi RPO và chi phí

Lịch backup càng dày có thể làm tăng số snapshot, operations và chi phí lưu. Nhưng một lịch quá thưa có thể không đáp ứng RPO. Đừng tối ưu chi phí chỉ bằng cách giảm số recovery points mà bỏ qua yêu cầu nghiệp vụ.

Ví dụ giả định:

~~~text
Tổng dung lượng cần bảo vệ: 500 GiB
Lịch snapshot: mỗi 4 giờ
Retention: theo chính sách đã phê duyệt
Data churn: phụ thuộc ứng dụng

Chi phí thực KHÔNG đơn giản bằng:
  500 GiB x 6 snapshots/ngày x số ngày

Vì snapshot và cơ chế backend có cách tính dung lượng/đổi dữ liệu khác nhau.
~~~

Phải xem bảng giá Azure theo region/tier/storage và **Cost Management** để đo chi phí thực. Gắn tag workload/owner, đặt budget và theo dõi backup storage tăng trưởng.

## 28. Bài tập tình huống: DR ứng dụng bán hàng

Một doanh nghiệp vận hành ứng dụng đặt hàng trên AKS:

- **orders-api** là Deployment stateless.
- **orders-worker** xử lý message từ Service Bus.
- **orders-db** là PostgreSQL StatefulSet dùng Azure Disk CSI-backed PVC.
- Hóa đơn PDF lưu tại Azure Blob Storage.
- Secrets tại Key Vault; workload dùng Microsoft Entra Workload ID.
- Mạng dùng private AKS, Private DNS và Azure Firewall.
- Doanh nghiệp đặt RPO cho đơn hàng **15 phút**, RTO **2 giờ**.
- Có yêu cầu khôi phục nếu mất cluster, và cần đánh giá DR khi mất toàn region.

### Nhiệm vụ

1. Liệt kê toàn bộ loại tài nguyên cần backup hoặc tái tạo.
2. Phân loại cái nào thuộc GitOps/IaC, Azure Backup for AKS, database backup và Blob backup.
3. Giải thích vì sao snapshot Azure Disk mỗi 24 giờ không đạt RPO 15 phút cho PostgreSQL.
4. Đề xuất cơ chế WAL/PITR hoặc giải pháp database đáp ứng RPO đã chọn.
5. Thiết kế các bước tạo cluster đích, cấu hình CSI/StorageClass và restore PVC.
6. Nêu thứ tự khôi phục Key Vault/workload identity, DB, API, worker và traffic.
7. Mô tả cách xử lý message ở Service Bus khi DB được restore về trạng thái cũ.
8. Giải thích vì sao bản snapshot chỉ có ở region nguồn chưa đủ cho DR region.
9. Thiết lập kiểm tra dữ liệu, health, RPO và RTO cho diễn tập.
10. Đề xuất RBAC, bảo vệ backup khỏi xóa, monitoring và chi phí.

### Gợi ý lời giải

Tách ít nhất ba luồng:

- **Hạ tầng + ứng dụng:** IaC/GitOps, image theo digest và configuration đã review.
- **PVC/PostgreSQL:** backup hỗ trợ và một phương án DB-native/PITR đáp ứng RPO 15 phút, không chỉ dựa vào snapshot ngày.
- **External data:** Blob/Service Bus/Key Vault được phục hồi hoặc tái tạo theo cơ chế dịch vụ và chính sách tương ứng.

Khi DR, khôi phục cluster và dependencies trước; sau đó database, kiểm tra dữ liệu, khởi động API, reconcile job ledger/queue rồi mới bật workers và chuyển traffic. Trạng thái **Backup completed** không thay thế báo cáo **restore drill passed**.

## 29. Checklist production

| Nhóm | Bằng chứng cần có |
|---|---|
| Mục tiêu | RPO/RTO theo ứng dụng và loại dữ liệu được phê duyệt |
| Scope | Danh sách namespaces, CRDs, PVC/PV, dịch vụ ngoài AKS |
| Compatibility | Phiên bản AKS, CSI driver, volume type, Backup feature/tier được hỗ trợ |
| Backup vault | Instance/policy/retention/recovery points được kiểm tra |
| Quyền | Trusted Access, Azure RBAC, Kubernetes RBAC và identities phù hợp |
| Dữ liệu | Có application-consistent/PITR nếu nghiệp vụ yêu cầu |
| GitOps/IaC | Cluster và manifests có thể tái tạo, image còn khả dụng |
| Security | Encryption, keys, secrets, quyền xóa backup tách biệt |
| Network | Private DNS, routing, firewall, ingress và egress phù hợp |
| DR region | Bản backup/data có thể truy cập từ region đích theo hỗ trợ |
| Restore | Đã thử về namespace/cluster cô lập, không ghi đè production |
| Validation | Database/schema/checksum, app health, giao dịch nghiệp vụ |
| Queue | Có reconciliation, replay/idempotency sau restore |
| Monitoring | Alert backup job, age recovery point, snapshot và policy changes |
| Chi phí | Budget vault/snapshot/DB/transfer/drill và gắn owner |
| Tài liệu | Runbook, owner, người phê duyệt, thời gian và rollback |

## 30. Câu hỏi tự kiểm tra

1. Tại sao backup Deployment YAML không phục hồi được dữ liệu trong PVC?
2. RPO và RTO khác nhau thế nào? Nếu RPO 15 phút thì backup mỗi ngày có đủ không?
3. Vì sao replication không thay thế backup lịch sử khi có xóa nhầm?
4. Những thành phần nào thuộc AKS nhưng không nhất thiết nằm trong backup của Kubernetes?
5. Azure Backup for AKS khác với việc backup một VM qua Recovery Services vault ở điểm nào?
6. Vì sao cần kiểm tra storage type và CSI driver trước khi khẳng định PVC được bảo vệ?
7. VolumeSnapshot khác backup có retention và khả năng DR như thế nào?
8. readyToUse=true của snapshot có chứng minh database application-consistent không?
9. Khi nào database-native backup và PITR quan trọng hơn snapshot volume?
10. Vì sao không được dùng kubectl get all làm danh sách đầy đủ mọi object?
11. Tại sao GitOps có thể ghi đè hoặc xóa tài nguyên vừa restore?
12. Khi chuyển sang AKS cluster mới, Workload Identity cần kiểm tra những gì?
13. Tại sao nên restore dữ liệu vào môi trường cô lập trước khi chuyển traffic?
14. Vì sao xóa cluster/namespace và mất cả region là hai kịch bản khác nhau?
15. Những yếu tố nào quyết định có thể restore backup ở region thứ hai?
16. Vì sao cần có runbook xử lý queue và job ledger sau khi restore DB?
17. Một backup job thành công có đủ bằng chứng đạt RTO và RPO không?
18. Làm thế nào xác minh checksum và dữ liệu nghiệp vụ của bản restore?
19. Những thay đổi nào trong Backup vault/policy cần cảnh báo bảo mật?
20. Bạn sẽ thiết kế một restore drill an toàn cho namespace có PVC như thế nào?
21. Vì sao không nên tự xóa PVC/PV đang có sự cố khi chưa hiểu reclaim policy?
22. Những khoản chi phí nào thường bị quên khi lập ngân sách DR cho AKS?

## Tài liệu tham khảo

- Microsoft Learn — *Azure Kubernetes Service backup overview*: https://learn.microsoft.com/azure/backup/azure-kubernetes-service-backup-overview
- Microsoft Learn — *Back up AKS using Azure Backup*: https://learn.microsoft.com/azure/backup/azure-kubernetes-service-backup-configure
- Microsoft Learn — *Restore AKS using Azure Backup*: https://learn.microsoft.com/azure/backup/azure-kubernetes-service-restore
- Microsoft Learn — *Azure Backup documentation*: https://learn.microsoft.com/azure/backup/
- Microsoft Learn — *Persistent volumes in AKS*: https://learn.microsoft.com/azure/aks/concepts-storage
- Microsoft Learn — *Azure Disk CSI driver for AKS*: https://learn.microsoft.com/azure/aks/azure-disk-csi
- Kubernetes — *Volume Snapshots*: https://kubernetes.io/docs/concepts/storage/volume-snapshots/
- Kubernetes — *Persistent Volumes*: https://kubernetes.io/docs/concepts/storage/persistent-volumes/
- Microsoft Learn — *Workload identity for AKS*: https://learn.microsoft.com/azure/aks/workload-identity-overview
- Microsoft Learn — *AKS best practices for business continuity and disaster recovery*: https://learn.microsoft.com/azure/aks/operator-best-practices-multi-region
