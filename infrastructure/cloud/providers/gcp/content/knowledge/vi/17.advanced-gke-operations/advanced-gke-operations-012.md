# Backup for GKE và khôi phục ứng dụng có trạng thái

> **Chương:** GKE nâng cao và vận hành  
> **Bài học:** Backup for GKE và khôi phục ứng dụng có trạng thái  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học đi từ quản trị project, IAM, VPC tới Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu, tự động hóa phát hành, giám sát độ tin cậy và chi phí. Với GKE, một Deployment có thể được tạo lại từ Git, nhưng **dữ liệu ghi trên PersistentVolume, cấu hình runtime và các phụ thuộc bên ngoài** cần quy trình khôi phục riêng.

**Backup for GKE** là dịch vụ được quản lý để sao lưu và khôi phục **workloads Kubernetes** cùng dữ liệu của **persistent disk volumes được hỗ trợ**. Điểm khó của hệ thống có trạng thái không phải chỉ tạo được một backup: phải xác định **RPO/RTO**, đảm bảo dữ liệu ứng dụng nhất quán, chọn chính sách restore an toàn, tái tạo được hạ tầng đích và **thử phục hồi từ đầu đến cuối**.

Bài học tập trung vào cách thiết kế, cấu hình, diễn tập và vận hành Backup for GKE. Các tên project, cluster, namespace và image đều là ví dụ. Lệnh tạo backup/restore có thể phát sinh phí hoặc thay đổi tài nguyên thật; chỉ chạy trong **sandbox được phê duyệt**, tuyệt đối không dùng lựa chọn restore phá hủy dữ liệu trên production khi chưa có change plan và bản sao an toàn.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt bản sao **Kubernetes manifests** với **volume data** và những tài nguyên Backup for GKE không bao phủ.
2. Giải thích `BackupPlan`, `Backup`, `RestorePlan`, `Restore` và agent chạy trong cluster.
3. Thiết kế phạm vi sao lưu theo **cluster, namespace hoặc ProtectedApplication**, lịch, retention và vị trí.
4. Chọn chiến lược phù hợp cho **Java StatefulSet dùng PVC**, database tự quản lý trên GKE và ứng dụng dùng Cloud SQL.
5. Phân biệt **crash-consistent** và **application-consistent**; biết khi nào cần hooks hoặc backup database-native.
6. Cấu hình chính sách **volume data restore** và xử lý xung đột resource mà không ghi đè dữ liệu sai chỗ.
7. Thực hành `gcloud beta container backup-restore`, `kubectl` và xác nhận restore trong cluster thử.
8. Xây dựng runbook, diễn tập RPO/RTO, IAM, giám sát, bảo mật và quản trị chi phí.

## 2. Backup for GKE bảo vệ cái gì?

Một bản backup có thể gồm **hai nhóm nội dung**, tùy phạm vi và cấu hình:

| Nhóm | Nội dung | Điểm cần nhớ |
|---|---|---|
| **Configuration backup** | Kubernetes resource manifests lấy từ API server, ví dụ Deployment, StatefulSet, ConfigMap, Service, PVC và resource thuộc phạm vi hỗ trợ | Phục hồi định nghĩa workload, **không** tự dựng GKE cluster |
| **Volume backup** | Bản sao dữ liệu của **PersistentVolume** thuộc loại được hỗ trợ và gắn với PVC được chọn | Phải bật **include volume data**; chỉ có PVC manifest không đủ phục hồi nội dung đĩa |

Backup for GKE hỗ trợ GKE **Standard** và **Autopilot** trong những giới hạn của dịch vụ. Một số nội dung cần phương án riêng:

| Không được backup đầy đủ bằng Backup for GKE | Phương án bổ sung |
|---|---|
| **Hạ tầng cluster:** node pools, machine types, VPC, subnet, routing, cluster flags và capacity | Terraform/IaC, cấu hình cluster chuẩn và runbook tạo cluster |
| **Container image bytes** | Giữ image/digest trong Artifact Registry và áp dụng retention phù hợp |
| **Cloud SQL, Cloud Storage, external load balancer, dịch vụ ngoài cluster** | Backup/PITR/versioning/DR của từng dịch vụ và phối hợp thời điểm |
| **Filestore/NFS, NetApp và non-Persistent-Disk volumes** theo đường volume backup mặc định | Backup riêng theo sản phẩm; Filestore có hướng dẫn hooks tích hợp chuyên biệt |
| **State nằm trên `emptyDir` hoặc filesystem tạm của container** | Không đặt dữ liệu cần phục hồi ở local ephemeral storage |
| **Secret** khi plan không chọn bao gồm secrets | Xem nguồn Secret Manager/GitOps, quy trình phục hồi khóa và chính sách include-secrets |

Một backup hiển thị **Succeeded** chưa chứng minh ứng dụng Java sau restore sẽ gọi được Cloud SQL, kéo được image, đọc được secret hoặc đạt SLO.

### 2.1. Kiến trúc dịch vụ

~~~mermaid
flowchart LR
  SRC["GKE nguồn<br/>namespace orders-stateful"]
  AG["Backup for GKE agent"]
  PLAN["BackupPlan<br/>scope + schedule + retention"]
  BACKUP["Backup<br/>manifests + PD volume data"]
  RESTORE["RestorePlan<br/>target + policies"]
  TARGET["GKE đích đã tồn tại"]
  VERIFY["Kiểm thử Java app<br/>dữ liệu + readiness"]
  SRC --> AG
  PLAN --> AG
  AG --> BACKUP
  BACKUP --> RESTORE
  RESTORE --> TARGET
  TARGET --> VERIFY
~~~

**BackupPlan** xác định nguồn, phạm vi, location và lịch. **Backup** là một điểm sao lưu cụ thể. **RestorePlan** xác định cluster đích, nội dung phục hồi, chính sách xung đột và volume. **Restore** là một lần thực hiện khôi phục theo plan.

Một BackupPlan có thể tạo nhiều Backup; một RestorePlan được tái sử dụng cho nhiều lần diễn tập. Target cluster phải **được tạo trước** và có Backup for GKE agent; khi tạo plan phù hợp, dịch vụ có thể cài agent trên cluster.

## 3. Đặt RPO/RTO trước khi cấu hình lịch

- **RPO (Recovery Point Objective):** chấp nhận mất tối đa bao nhiêu dữ liệu, tính từ thời điểm xảy ra sự cố về điểm khôi phục có thể dùng.
- **RTO (Recovery Time Objective):** sau sự cố, cần đưa dịch vụ trở lại trạng thái phục vụ hợp lệ trong bao lâu.
- **Retention:** giữ backup trong bao lâu; **không** đồng nghĩa RPO.
- **Recovery consistency:** dữ liệu sau phục hồi có nhất quán với giao dịch và phụ thuộc khác không.

| Yêu cầu giả định | Gợi ý phương án | Lưu ý |
|---|---|---|
| Namespace thử nghiệm, phục hồi sau một ngày chấp nhận được | Backup mỗi ngày, giữ ngắn | Giảm chi phí; thường không cần HA riêng |
| Java worker ghi checkpoint vào PVC; không mất nhiều tiến độ | Backup thường xuyên hơn và thử checkpoint recovery | Dữ liệu giữa các bản backup có thể mất |
| PostgreSQL tự quản lý trên GKE, yêu cầu mất dữ liệu rất thấp | Backup for GKE **kết hợp** WAL archive/PITR, replication DB | Volume snapshot một mình chưa đáp ứng mọi RPO |
| Lỗi **một node hoặc zone** phải phục vụ liên tục | Multi-zone architecture, replicas/HA | Backup phục vụ khôi phục, **không thay HA** |
| Lỗi cả region cần hồi phục | Backup ở region phù hợp, cluster đích và phụ thuộc DR | Xem data residency, storage access, egress, IAM |

**RPO của hệ thống được đo theo backup thành công và dữ liệu thực sự khôi phục được**, không theo một cron string. Ví dụ backup hằng giờ nhưng lần gần nhất thất bại thì khoảng mất dữ liệu có thể dài hơn dự kiến.

### 3.1. Crash-consistent khác application-consistent

Snapshot đĩa thường mô tả trạng thái block giống một thời điểm mất điện. Filesystem có thể replay journal, nhưng ứng dụng/database có thể cần recovery.

| Trạng thái | Bảo đảm thực tế |
|---|---|
| **Crash-consistent** | Phục hồi được trạng thái block tại thời điểm snapshot; ứng dụng cần tự recover như sau crash |
| **Application-consistent** | Trước snapshot có phối hợp flush/quiesce/transaction để trạng thái ứng dụng nhất quán theo quy trình |
| **Point-in-time database recovery (PITR)** | Phục hồi DB tới thời điểm đã được bảo vệ bằng backup + transaction logs; không mặc định có từ backup PVC |

Backup for GKE cung cấp **ProtectedApplication** và **execution hooks** để chạy các hành động trước/sau backup theo chiến lược được hỗ trợ. Ví dụ **pre-hook** làm ứng dụng tạm ngừng ghi và flush dữ liệu, **post-hook** cho phép ghi trở lại sau bước snapshot. Không dùng lệnh `kill -9` hoặc khóa database tùy tiện làm “hook chuẩn”; hành vi phải do chủ ứng dụng/database thiết kế và thử nghiệm.

## 4. Ví dụ workload Java có trạng thái

Giả sử `orders-worker` xử lý đơn hàng từ hàng đợi và lưu **checkpoint không được bỏ qua** trong `/var/lib/orders`. Image Java đã được build, lưu tại Artifact Registry và có quyền pull. Một StatefulSet một replica có PVC 20 GiB trên Persistent Disk.

**Điều kiện:** cluster có StorageClass `standard-rwo` tương thích với PD CSI driver; image ví dụ phải thật sự chạy ứng dụng và ghi checkpoint trong thư mục mount.

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-worker
  namespace: orders-stateful
spec:
  clusterIP: None
  selector:
    app: orders-worker
  ports:
  - name: http
    port: 8080
    targetPort: 8080
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: orders-worker
  namespace: orders-stateful
spec:
  serviceName: orders-worker
  replicas: 1
  selector:
    matchLabels:
      app: orders-worker
  template:
    metadata:
      labels:
        app: orders-worker
    spec:
      containers:
      - name: worker
        image: asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-worker:1.0.0
        ports:
        - containerPort: 8080
        volumeMounts:
        - name: data
          mountPath: /var/lib/orders
        resources:
          requests:
            cpu: "250m"
            memory: "512Mi"
          limits:
            memory: "1Gi"
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: standard-rwo
      resources:
        requests:
          storage: 20Gi
~~~

Để triển khai, tạo namespace `orders-stateful` trước. StatefulSet sinh PVC có tên tương tự `data-orders-worker-0`. Kiểm tra:

~~~bash
kubectl get statefulset,pods,pvc -n orders-stateful
kubectl get pv
kubectl describe pvc data-orders-worker-0 -n orders-stateful
kubectl get storageclass
~~~

Phải thấy PVC `Bound` với PV có driver/disk phù hợp. Nếu image không có thật, Pod có thể `ImagePullBackOff`; nếu thiếu zone capacity/StorageClass, PVC có thể chưa bind. **Không tạo dữ liệu production trong lab.**

**Một replica không phải HA.** Nếu Pod hoặc zone hỏng, việc chạy lại ứng dụng trên volume có thể cần chờ gắn đĩa và replay dữ liệu. Với ứng dụng Java stateless, thay vì lưu order vào PVC, nên lưu state trên Cloud SQL/Cloud Storage và để Pods tái tạo được.

## 5. Thiết kế BackupPlan: phạm vi, lịch, vị trí

### 5.1. Chọn phạm vi

| Phạm vi | Khi phù hợp | Rủi ro |
|---|---|---|
| **All namespaces** | Bảo vệ khối lượng lớn resources trong cluster | Nặng, có thể bao gồm workload không cần bảo vệ |
| **Selected namespaces** | Ứng dụng nhóm theo namespace rõ | Bỏ sót resource/phụ thuộc ở namespace khác |
| **ProtectedApplications** | Cần nhóm ứng dụng và dùng hooks/logic nhất quán | Phải định nghĩa resource group/hook đúng |
| **Selected objects khi restore** | Khôi phục mục tiêu hẹp theo khả năng restore | Có thể thiếu CRD, RBAC, StorageClass phụ thuộc |

Bảo vệ **Kubernetes Secrets** là một lựa chọn riêng. Nếu bật, backup chứa thông tin nhạy cảm; kiểm tra encryption, IAM, retention và quyền người dùng đọc/restore. Nếu không bật, target phải có **cơ chế tái tạo secrets** (Secret Manager + controller hoặc quy trình khác).

### 5.2. Lịch và retention

- **Smart scheduling:** chọn `target RPO`, dịch vụ tạo backup theo mục tiêu và giới hạn; không đồng thời đặt `cron schedule` trong cùng plan.
- **Cron scheduling:** chọn thời điểm backup cố định; cần giám sát kết quả, không chỉ trạng thái schedule.
- **Retention:** thời gian giữ bản backup; chọn theo nhu cầu truy hồi và chính sách pháp lý.
- **Delete lock:** ngăn xóa sớm trong khoảng tối thiểu; chỉ bật/khóa retention sau khi hiểu chi phí và hậu quả vận hành.
- **Backup location:** tài nguyên theo **region**, có thể khác region của source cluster theo hỗ trợ; cần tính network charges và yêu cầu cư trú dữ liệu.

Một cluster có thể có nhiều BackupPlan: backup thường xuyên cho ứng dụng quan trọng, backup ít thường xuyên hơn cho workload thử nghiệm, hoặc lưu backup ở nhiều region để đáp ứng DR.

## 6. Thực hành: tạo backup và kiểm tra

**Lưu ý:** các lệnh sau là ví dụ thay đổi tài nguyên Google Cloud, chỉ chạy trong sandbox với **Backup for GKE API**, quyền IAM, cluster hợp lệ và billing được phê duyệt. Thay placeholder trước khi thực thi. Ví dụ dùng region `asia-southeast1` và regional GKE cluster `CLUSTER_NAME`; xác minh region hỗ trợ dịch vụ.

### 6.1. Kiểm tra trước khi tạo

~~~bash
gcloud auth list
gcloud config get-value project

gcloud container clusters describe CLUSTER_NAME \
  --project=PROJECT_ID \
  --location=asia-southeast1

kubectl get ns orders-stateful
kubectl get pvc -n orders-stateful
~~~

Tài khoản quản trị plan có thể cần `roles/gkebackup.backupAdmin` cùng quyền truy cập GKE phù hợp. Không dùng `roles/owner` để xử lý lỗi thiếu quyền.

### 6.2. Tạo BackupPlan cho một namespace

~~~bash
gcloud beta container backup-restore backup-plans create orders-daily \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --cluster=projects/PROJECT_ID/locations/asia-southeast1/clusters/CLUSTER_NAME \
  --selected-namespaces=orders-stateful \
  --include-volume-data \
  --cron-schedule="0 2 * * *" \
  --backup-retain-days=14
~~~

Ở đây, plan bảo vệ namespace `orders-stateful`, **bao gồm volume data** và giữ backup 14 ngày. Lịch là ví dụ; kiểm tra cách diễn giải múi giờ của cron theo tài liệu chính thức và yêu cầu hệ thống. Nếu ứng dụng phụ thuộc Secret đã tạo thủ công mà target không có cách tái tạo, cân nhắc `--include-secrets` cùng phương án quản trị dữ liệu nhạy cảm.

### 6.3. Tạo một backup thủ công và quan sát

~~~bash
gcloud beta container backup-restore backups create orders-before-upgrade \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --backup-plan=orders-daily \
  --wait-for-completion

gcloud beta container backup-restore backups describe orders-before-upgrade \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --backup-plan=orders-daily
~~~

`--wait-for-completion` chờ thao tác hoàn tất theo API, nhưng vẫn phải **xem kết quả/thất bại và volume backups**; đừng mặc định lệnh trả về đồng nghĩa toàn bộ workload đã được bảo vệ.

~~~bash
gcloud beta container backup-restore backups list \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --backup-plan=orders-daily

gcloud beta container backup-restore volume-backups list \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --backup-plan=orders-daily \
  --backup=orders-before-upgrade
~~~

Đọc **backup status, thời điểm, index của resources, các volume được bảo vệ, lỗi/ cảnh báo**. Nếu resource cần thiết không nằm trong backup index hoặc volume backup thiếu, **không chuyển sang diễn tập restore và tuyên bố đã đáp ứng RPO** trước khi hiểu nguyên nhân.

## 7. Thiết kế RestorePlan an toàn

RestorePlan trả lời ba câu hỏi: **khôi phục vào đâu**, **tài nguyên nào** và **nếu resource/volume đã tồn tại thì làm gì**. Đây là bước có thể dẫn tới mất dữ liệu nhất nếu chọn sai.

### 7.1. Chính sách phục hồi volume data

| Volume policy | Ý nghĩa | Khi nào dùng |
|---|---|---|
| `restore-volume-data-from-backup` | Tạo PV mới từ volume backup được hỗ trợ | Diễn tập ở cluster đích **mới**, muốn kiểm tra dữ liệu đã backup |
| `reuse-volume-handle-from-backup` | Liên kết lại volume handle gốc | Chỉ khi biết rõ volume gốc vẫn hiện hữu và việc dùng lại an toàn |
| `no-volume-data-restoration` | Chỉ phục hồi PVC config; volume có thể được tạo rỗng hoặc bind tới PV có sẵn | Workload stateless, volume không được backup hoặc dữ liệu quản lý ngoài |

**Không nhầm:** restore PVC manifest không đồng nghĩa khôi phục dữ liệu. Nếu chọn “không phục hồi volume data” hoặc backup không chứa volume backup, ứng dụng có thể thấy một đĩa rỗng dù StatefulSet đã chạy.

### 7.2. Chính sách xung đột resource

| Xung đột | Phương án | Nguy cơ |
|---|---|---|
| **Namespace/protected app đã tồn tại** | `fail-on-conflict` | An toàn khi diễn tập: dừng thay vì ghi đè |
| **Merging** | `merge-skip-on-conflict` | Giữ resource có sẵn, có thể không đạt mục tiêu rollback |
| **Dữ liệu volume thay thế** | `merge-replace-volume-on-conflict` | Có thể ảnh hưởng PV cũ, phụ thuộc reclaim policy |
| **Resource và volume thay thế** | `merge-replace-on-conflict` | Có thể sửa/xóa resource và dữ liệu đang hoạt động |
| **Rollback nhóm namespace/app** | `delete-and-restore` | **Phá hủy** tài nguyên trong phạm vi để phục hồi lại từ backup |
| **Cluster-scoped resources trùng** | Giữ bản hiện tại hoặc thay bản theo policy | Thay **CRD** có thể kéo theo xóa toàn bộ Custom Resources của loại đó |

Khi chưa hiểu impact, **dùng cluster sandbox mới, namespace chưa tồn tại và `fail-on-conflict`**. Với cluster đang được GitOps/Operator quản lý, xét kỹ sự khác biệt giữa **restore dữ liệu** và **controller sẽ tự reconcile lại resource**.

## 8. Thực hành: restore vào cluster thử riêng

Giả sử đã có **cluster đích** `CLUSTER_RESTORE` trong cùng region, được tạo trước với Kubernetes version tương thích, node capacity, mạng, IAM, storage driver và image pull permission. **Không** restore thử lên namespace production đang ghi dữ liệu.

### 8.1. Tạo RestorePlan không ghi đè tài nguyên

~~~bash
gcloud beta container backup-restore restore-plans create orders-rehearsal \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --backup-plan=projects/PROJECT_ID/locations/asia-southeast1/backupPlans/orders-daily \
  --cluster=projects/PROJECT_ID/locations/asia-southeast1/clusters/CLUSTER_RESTORE \
  --selected-namespaces=orders-stateful \
  --namespaced-resource-restore-mode=fail-on-conflict \
  --cluster-resource-scope-no-group-kinds \
  --volume-data-restore-policy=restore-volume-data-from-backup
~~~

Plan chỉ phục hồi namespace đã chọn, không lấy cluster-scoped resources, và **dừng nếu namespace bị trùng**. Điều này an toàn hơn cho diễn tập nhưng có thể khiến ứng dụng không hoạt động nếu cần **StorageClass, CRD, RBAC hoặc operator** chưa có trên cluster đích. Các phần hạ tầng/phụ thuộc này phải được chuẩn bị bằng IaC hoặc quy trình riêng.

### 8.2. Thực hiện Restore

~~~bash
gcloud beta container backup-restore restores create orders-test-restore \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --restore-plan=orders-rehearsal \
  --backup=projects/PROJECT_ID/locations/asia-southeast1/backupPlans/orders-daily/backups/orders-before-upgrade \
  --wait-for-completion

gcloud beta container backup-restore restores describe orders-test-restore \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --restore-plan=orders-rehearsal
~~~

Nếu `Restore` báo hoàn thành, Kubernetes vẫn cần **reconcile và chạy ứng dụng**, vì vậy đừng dùng trạng thái Restore API làm tiêu chí nghiệm thu duy nhất.

### 8.3. Xác minh cluster sau restore

Kết nối **đúng cluster thử** trước khi chạy kubectl:

~~~bash
gcloud container clusters get-credentials CLUSTER_RESTORE \
  --project=PROJECT_ID \
  --location=asia-southeast1

kubectl config current-context
kubectl get ns orders-stateful
kubectl get statefulset,pods,pvc -n orders-stateful
kubectl get events -n orders-stateful --sort-by=.lastTimestamp
kubectl describe pvc data-orders-worker-0 -n orders-stateful
~~~

**Kiểm thử chức năng bắt buộc:** xác nhận ứng dụng Java nhận dữ liệu checkpoint từ backup, đọc được một số bản ghi thử đã biết, idempotency khi chạy lại job, kết nối được các dịch vụ cần thiết, readiness ổn định và không có lỗi trong logs. Đối với database, kiểm tra recovery/WAL và integrity theo cơ chế của database.

## 9. Runbook khôi phục ứng dụng có trạng thái

~~~mermaid
flowchart TD
    Incident["Phát hiện sự cố / yêu cầu restore"]
    Assess["Phân loại lỗi + phạm vi + RPO/RTO"]
    Pick["Chọn backup thành công<br/>xác minh index/volume"]
    Fence["Ngăn ghi hai phía<br/>quyết định maintenance"]
    Target["Tạo/xác minh cluster đích<br/>IAM, mạng, images, StorageClass"]
    Restore["Chạy RestorePlan an toàn"]
    Validate["Validate PV, Pods, DB recovery<br/>Java data + health + SLO"]
    Cut["Chuyển traffic khi đã đạt"]
    Monitor["Monitor + ghi bằng chứng + review"]
    Incident --> Assess --> Pick --> Fence --> Target --> Restore --> Validate --> Cut --> Monitor
~~~

**Trình tự vận hành:**

1. Xác nhận lỗi: rollout sai, file bị xóa, cluster lỗi hay region outage? Xác định **phạm vi và thời điểm cần phục hồi**.
2. Đóng băng ghi hoặc thiết kế **fencing**: tránh primary cũ và restored workload cùng ghi vào hệ thống ngoài (Cloud SQL, queue, API).
3. Chọn backup đã kiểm tra **success, resources và volume data**, không chỉ nhìn vào tên bản mới nhất.
4. Dựng hoặc xác minh cluster đích: version tương thích, StorageClass/CSI, CRD/Operator, service accounts, Workload Identity Federation for GKE, network và secrets.
5. Chọn RestorePlan theo mục tiêu: **cluster trống** hay **data-only/rollback**. Chỉ dùng chế độ phá hủy sau khi duyệt impact PV reclaim policy.
6. Theo dõi Restore và volume restores, kiểm tra Pods, PVC Bound, image pulls, container logs, health checks.
7. Kiểm tra **dữ liệu end-to-end**: số bản ghi, checkpoint, trạng thái job, giao dịch và permissions.
8. Khi đã đạt SLO và data integrity, mới chuyển traffic/DNS/load balancer theo runbook.
9. Ghi **RPO thực tế**, **RTO thực tế**, bằng chứng và bài học; chuẩn bị failback nếu cần.

**Không đưa cluster restore lên production ngay khi một Pod chuyển sang `Running`.** Một ứng dụng có thể chạy được nhưng sử dụng **dữ liệu cũ** hoặc đang trỏ vào production database trong lúc backup volume đã được rollback.

## 10. ProtectedApplication, hooks và tính nhất quán

Với các ứng dụng có trạng thái, chia workload thành ba loại:

| Workload | Cách bảo vệ hợp lý |
|---|---|
| Java API **stateless**, state ở Cloud SQL/Storage | Backup manifests nếu cần; **database/object backup riêng** |
| Java worker ghi file checkpoint/embedded DB trên PD PVC | Backup for GKE có **volume data**, quiesce/flush qua hooks nếu cần, restore test |
| PostgreSQL/MySQL tự quản lý trên GKE | Backup for GKE + database-native backup/WAL/PITR hoặc operator backup; kiểm tra crash/application consistency |

**ProtectedApplication** giúp nhóm các resources thuộc một app và cấu hình hooks theo chiến lược hỗ trợ. Một pattern tham khảo:

~~~text
Trước snapshot:
  1. Tạm ngừng nhận yêu cầu ghi/checkpoint update
  2. Flush dữ liệu xuống disk và giữ trạng thái nhất quán
Trong snapshot:
  3. Backup for GKE chụp volume data được hỗ trợ
Sau bước snapshot:
  4. Bỏ trạng thái quiesce, ứng dụng tiếp tục chạy
Khi restore:
  5. Mount volume mới, replay journal/WAL, kiểm tra dữ liệu
~~~

Không tự áp cùng pre/post hooks cho mọi database: MySQL, PostgreSQL, Cassandra, Redis và ứng dụng Java embedded storage có semantics khác nhau. Hooks cũng có thể **timeout** hoặc thất bại, khiến backup không đạt mục tiêu; phải theo dõi kết quả.

**Nếu ứng dụng dùng Cloud SQL**, Backup for GKE **không snapshot Cloud SQL**. Muốn điểm khôi phục nhất quán giữa manifests, PVC và Cloud SQL, cần thiết kế **quy trình phối hợp** và kiểm tra trên hệ thống thử; không mặc định chúng xảy ra tại cùng một thời điểm.

## 11. Khôi phục giữa cluster, project và region

Restore từ một GKE cluster sang cluster khác được hỗ trợ trong giới hạn dịch vụ. Tuy nhiên cần kiểm tra:

- **Cluster đích đã tồn tại** và Backup for GKE agent được bật/cài phù hợp.
- **Tương thích phiên bản:** tài liệu hiện hành giới hạn target Kubernetes minor từ version nguồn lúc backup đến tối đa **ba minor versions mới hơn**, tính cả hai đầu. Kiểm tra lại quy định nếu dịch vụ cập nhật.
- **Project:** cross-project backup/restore có cơ chế quyền và restore channel; không tự coi backup project có thể bị bất kỳ project khác restore.
- **Region:** vị trí BackupPlan quyết định nơi lưu backup. Nếu khác region nguồn/đích, có thể có phí truyền dữ liệu và yêu cầu residency.
- **Storage:** Disk/StorageClass, topology zone, reclaim policy, PV CSI capabilities và quota trên cluster đích.
- **Phụ thuộc:** load balancer, DNS, Artifact Registry image, secret, Cloud SQL, IAM và network phải có hoặc được tái tạo đúng.

### 11.1. Namespace rename và transformation rules

Backup for GKE hỗ trợ **transformation rules** để thay một số thuộc tính Kubernetes khi restore, chẳng hạn namespace/reference hoặc StorageClass theo quy tắc được hỗ trợ. Đây là công cụ di chuyển/thử nghiệm, nhưng cần kiểm tra references như:

- `ServiceAccount`, `RoleBinding`, namespace của ConfigMap/Secret.
- PVC và StorageClass tương thích.
- Endpoint database, project ID, region, workload identity.
- DNS/ingress, certificate và callback URLs.

**Không sửa namespace/StorageClass bằng search-and-replace mù** trong các manifest vì có thể làm mất security boundary hoặc trỏ sai dữ liệu.

## 12. IAM, bảo mật và khả năng chống xóa backup

### 12.1. Tách quyền backup khỏi restore

| Nhiệm vụ | Role tham khảo | Lý do |
|---|---|---|
| Tạo/quản trị BackupPlan và backups | `roles/gkebackup.backupAdmin` | Không tự cần quyền khôi phục phá hủy |
| Tạo/quản trị RestorePlan và restores | `roles/gkebackup.restoreAdmin` | Phân quyền DR có phê duyệt |
| Quản trị toàn bộ Backup for GKE | `roles/gkebackup.admin` | Chỉ cấp cho nhóm chịu trách nhiệm tổng thể |

Với cross-project/cluster, còn có các permission cho GKE, service agent, network, encryption và hoạt động đọc/ghi liên quan; role trên chỉ là một phần của thiết kế. Tránh cấp `roles/owner` để vượt `PERMISSION_DENIED`.

### 12.2. Dữ liệu backup cũng là dữ liệu nhạy cảm

- Cân nhắc **include-secrets**; backup Secrets cần IAM và retention chặt.
- Dùng **CMEK** cho BackupPlan nếu yêu cầu và dịch vụ/location hỗ trợ; bảo vệ key và quyền giải mã khi DR.
- Bật audit logs, hạn chế principal được xóa/restore backup; xem resource policies tổ chức.
- Xem **backup deletion lock và retention lock** khi cần chống xóa nhầm/ác ý; quyết định trước khi bật vì có thể hạn chế khả năng xóa và tăng chi phí.
- Giữ IaC, container images và external DB backups đủ lâu để **khôi phục thực sự**, không chỉ lưu PVC snapshots.

**Backup cùng project/region với production có thể cùng chịu rủi ro thao tác phá hoại/quyền sai**. Khi threat model cần cách ly, xét **backup cross-project/multi-region** theo tính năng hỗ trợ và IAM riêng.

## 13. Giám sát và xử lý lỗi

### 13.1. Bộ chỉ số vận hành

| Quan sát | Nếu bất thường, cần làm gì? |
|---|---|
| Last successful backup | Cảnh báo nếu đã quá khoảng RPO mong muốn |
| Backup/volume backup status | Xác định PVC hoặc resource thiếu, agent/CSI error |
| Agent/cluster accessibility | Kiểm tra API, in-cluster agent, IAM và network |
| Restore status và volume restores | Kiểm tra PV/PVC, StorageClass, quota và API errors |
| App recovery | Readiness, logs, dữ liệu checkpoint/DB, job replay |
| Retention/deletion lock | Tránh backup hết hạn trước nhu cầu rollback |
| Chi phí | Theo dõi backup storage, volume snapshots, chuyển vùng và restore |

Dùng Google Cloud Console **GKE → Backup for GKE**, Cloud Monitoring/Logging và `gcloud`; đặt alert dựa trên dữ liệu/metric thực sự có sẵn, không chỉ xem lịch backup đã bật.

### 13.2. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách chẩn đoán |
|---|---|---|
| Backup không chứa PVC data | Quên `--include-volume-data`, volume không được hỗ trợ | Kiểm tra BackupPlan, volume-backups list, CSI driver |
| Backup báo lỗi hook | Quiesce command sai/timeout hoặc thiếu quyền | Kiểm tra ProtectedApplication/hooks và logs |
| Không restore vào target | Target chưa tồn tại/agent thiếu, version lệch | Xem cluster, add-on, version compatibility |
| `fail-on-conflict` khiến restore dừng | Namespace/resource đã tồn tại | Dùng cluster thử trống, không đổi sang destructive mode tùy tiện |
| PVC sau restore `Pending` | Thiếu StorageClass/driver, topology/capacity/quota | `kubectl describe pvc` và events |
| Pod `ImagePullBackOff` | Backup không chứa image binaries | Kiểm tra Artifact Registry, node identity và digest |
| App chạy nhưng data rỗng | Không có volume backup hoặc chọn no-data policy | Xác minh volume restore policy, PV và path mount |
| Java app gọi sai Cloud SQL | Khôi phục cấu hình cũ trỏ database production | Xem Secret/config, VPC, IAM, database endpoint |
| Restore xóa nhầm PV/data | Dùng merge-replace/delete-and-restore, PV reclaim policy | Dừng thay đổi, xem backup hiện hữu và runbook ứng cứu |
| Không xóa được backup | Delete lock/retention giữ bản backup | Xem policy và thời hạn, không cố vượt lock |
| Chi phí tăng | Lịch quá dày, retention dài, multi-region, volumes lớn | Billing breakdown và phân nhóm plan |

**Thứ tự điều tra:** xác nhận bản backup → phạm vi/volume index → restore policy → cluster đích → PVC/Pod events → dữ liệu ứng dụng. Không “sửa” bằng cách xóa namespace production đang chạy hoặc xóa volume gốc.

## 14. Chi phí và ranh giới với HA

**Backup ≠ High Availability.** Backup giúp phục hồi sau lỗi/xóa nhầm/triển khai sai; HA giữ dịch vụ hoạt động trước những sự cố hạ tầng đã dự đoán. Một hệ thống quan trọng có thể cần cả hai.

| Chi phí / tài nguyên | Yếu tố ảnh hưởng |
|---|---|
| Backup for GKE | Backup management/storage theo SKU và dữ liệu được bảo vệ |
| Volume snapshots | Dung lượng data và storage snapshot liên quan |
| Region khác | Data transfer và lưu trữ tại vùng backup |
| Cluster diễn tập/DR | Node, control plane, disks, load balancer, IP |
| Security/logging | Cloud KMS/CMEK, logs/retention |
| Con người | Thời gian diễn tập, review, sửa sai consistency và runbook |

Không suy **retention 14 ngày = luôn có 14 bản backup**; số bản phụ thuộc lịch và thực tế hoàn tất. Đừng chỉ dự toán backup mà bỏ phí **cluster đích và data transfer**. Xem Cloud Billing cùng Google Cloud Pricing Calculator trước khi áp chính sách quy mô lớn.

## 15. Case study: phục hồi Orders Worker sau bản phát hành lỗi

**Bối cảnh giả định:** nhóm bán lẻ có `orders-worker` (Java StatefulSet) ghi checkpoint vào PD PVC. CI phát hành image mới; lỗi logic khiến checkpoint tiến quá xa, một số job chưa xử lý đầy đủ. Dịch vụ khác ghi dữ liệu giao dịch vào Cloud SQL.

**Mục tiêu:** khôi phục đúng checkpoint đã backup, không xử lý đơn hàng trùng và tránh chạm vào Cloud SQL production khi diễn tập.

**Quy trình đề xuất:**

1. **Chặn consumer mới** và ghi lại vị trí offset/checkpoint hiện tại; xác định những job đã side-effect thành công.
2. Đọc `Backup` thành công gần nhất, kiểm tra **VolumeBackup** thực sự chứa PVC dữ liệu.
3. Tạo GKE restore cluster riêng, cách ly network/IAM để không gửi lệnh ghi tới Cloud SQL/queue production.
4. Dùng `fail-on-conflict` và `restore-volume-data-from-backup`, chỉ namespace `orders-stateful`.
5. Validate checkpoint trên restored PVC, xem audit/job table để phân biệt **chưa xử lý** và **đã xử lý**.
6. Khôi phục bằng **idempotent replay/deduplication**; rollback code/image về version tương thích.
7. Khi đủ bằng chứng, lên kế hoạch đổi endpoint/traffic hoặc tái nạp state theo change window; không tự cho hai worker ghi đồng thời.
8. Ghi lại mất dữ liệu theo RPO và thời gian phục hồi theo RTO, cập nhật runbook.

**Bài học:** Volume backup có thể khôi phục file checkpoint, nhưng không tự “undo” các transaction đã xảy ra trong Cloud SQL, Pub/Sub hay hệ thống thanh toán. Tính đúng đắn cuối cùng phụ thuộc **mô hình giao dịch và idempotency của ứng dụng**.

## 16. Bài tập và câu hỏi tự đánh giá

### Bài 1 — Phạm vi backup

Một ứng dụng gồm Java Deployment, ConfigMap, Secret, PVC PD và Cloud SQL PostgreSQL. BackupPlan chỉ chọn namespace và **không** bật include-volume-data/include-secrets.

**Hỏi:** Có những gì trong backup? Những thứ nào phải được bảo vệ bằng cơ chế riêng?

**Gợi ý:** có một số manifests, nhưng không có PVC data và Secrets; Cloud SQL nằm ngoài scope.

### Bài 2 — RPO/RTO

Backup chạy mỗi ngày, retention 30 ngày. Sản phẩm yêu cầu RPO 15 phút và RTO 30 phút.

**Hỏi:** Kế hoạch hiện tại có đủ không? Đề xuất thêm gì?

**Gợi ý:** retention dài không làm RPO ngắn; cần lịch/CDC/PITR/app replication phù hợp và diễn tập thời gian phục hồi.

### Bài 3 — StorageClass và PV

Restore reports hoàn thành nhưng `data-orders-worker-0` ở `Pending`. Target cluster chưa có StorageClass `standard-rwo`.

**Hỏi:** Vì sao Restore API thành công chưa đủ? Cần kiểm tra/khôi phục tài nguyên nào?

**Gợi ý:** CSI driver/StorageClass, quota, zone topology, PV/PVC events và Pod lifecycle.

### Bài 4 — Conflict mode

Muốn diễn tập trên cluster đã có namespace `orders-stateful` chứa dữ liệu thử mới. Người vận hành chọn `delete-and-restore` để “chạy nhanh”.

**Hỏi:** Có rủi ro gì? Chính sách nào an toàn hơn cho lần đầu?

**Gợi ý:** có thể xóa resources/PV phụ thuộc reclaim policy; dùng target trống và `fail-on-conflict`.

### Bài 5 — Crash consistency

PostgreSQL trên PVC được backup khi đang có giao dịch. Không có quiesce hoặc WAL archiving.

**Hỏi:** Snapshot đó có bảo đảm phục hồi đúng mọi transaction không?

**Gợi ý:** chỉ có crash-consistency theo khả năng volume; cần PostgreSQL-native recovery, WAL/PITR, hooks và restore test.

### Bài 6 — Cross-region DR

Hai replica của ứng dụng và backup đều ở region A. Mục tiêu là chịu lỗi cả region A.

**Hỏi:** Các điều kiện về vị trí backup, cluster đích, container images, Cloud SQL và IAM cần thêm là gì?

**Gợi ý:** location backup phù hợp ở vùng độc lập, hạ tầng DR và backups ngoài GKE, khả năng mạng/keys/capacity ở vùng đích.

### Bài 7 — Operator và GitOps

Namespace được Flux/Argo CD và một database operator quản lý. RestorePlan chọn merge-replace trên cùng namespace.

**Hỏi:** Điều gì có thể xảy ra sau khi restore?

**Gợi ý:** controller reconcile làm thay manifests; xử lý conflicts CRD/CR, data volume riêng và phối hợp pause/resume với GitOps/operator.

### Bài 8 — Chứng minh backup dùng được

Một backup `Succeeded`, nhóm kết luận DR đã hoàn thiện.

**Hỏi:** Hãy đề xuất checklist kiểm thử ít nhất năm bước để chứng minh đáp ứng RPO/RTO.

**Gợi ý:** thử target cluster, PVC mount, app/data integrity, external dependencies, idempotent replay và đo thời gian.

## 17. Checklist production

- [ ] Có **owner, RPO/RTO, data classification** và phạm vi failure cụ thể.
- [ ] Đã kiểm kê Kubernetes manifests, PVC/PD, secrets, images, Cloud SQL/Storage và hạ tầng cluster.
- [ ] BackupPlan chọn đúng namespaces/app, **include-volume-data** khi cần và Secret policy phù hợp.
- [ ] Schedule và retention được chọn theo RPO, được giám sát trên **last successful backup**.
- [ ] Với database, đã có giải pháp application-consistency/backup-native và kiểm thử replay.
- [ ] Cluster DR có thể tạo lại bằng IaC, có đủ capacity, IAM, mạng, StorageClass và artifacts.
- [ ] RestorePlan có scope, **conflict policy** và **volume policy** được xét duyệt.
- [ ] Restore thử trên target tách biệt, kiểm tra PVC Bound, Pod health, data integrity và side effects.
- [ ] Cross-project/cross-region, KMS, Secrets và image access được kiểm chứng khi có nhu cầu DR.
- [ ] Quyền backup/restore/delete tách nhiệm vụ; retention/deletion lock theo threat model.
- [ ] Có dashboard/alert cho backup failure, missing volume backup, RPO breach và chi phí.
- [ ] Đã ghi RPO/RTO **đo được** sau diễn tập và cập nhật runbook.

## 18. Tài liệu chính thức

Tra phiên bản GKE, trạng thái tính năng, lệnh `gcloud beta` và giới hạn mới nhất khi triển khai thật:

- [Backup for GKE overview](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/concepts/backup-for-gke)
- [Plan a set of backups](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/backup-plan)
- [Back up your workloads](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/backup)
- [Plan a set of restores](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/restore-plan)
- [Restore a backup](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/restore)
- [Define volume data restore behavior](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/volume-data-restore-policy)
- [Handle resource conflicts during restore](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/resource-conflict)
- [ProtectedApplications and execution hooks](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/protected-application)
- [Backup for GKE locations](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/concepts/about-locations)
- [Kubernetes StatefulSet](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)
- [Kubernetes Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [GKE Backup pricing](https://cloud.google.com/kubernetes-engine/pricing)

**Điểm cần nhớ:** **Backup for GKE bảo vệ cấu hình Kubernetes và dữ liệu Persistent Disk được hỗ trợ, không phải toàn bộ hạ tầng và dịch vụ ngoài cluster.** Để khôi phục ứng dụng Java có trạng thái, cần **backup đúng volume, có tính nhất quán phù hợp, RestorePlan không phá hủy ngoài ý muốn, cluster đích sẵn sàng và kiểm thử end-to-end**. Chỉ khi đo được RPO/RTO và xác minh dữ liệu/side effects sau restore, tổ chức mới có cơ sở khẳng định kế hoạch DR hoạt động.
