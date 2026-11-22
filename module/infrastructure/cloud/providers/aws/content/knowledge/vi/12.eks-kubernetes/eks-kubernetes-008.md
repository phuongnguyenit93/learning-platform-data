# EBS CSI, EFS CSI và lưu trữ cho workload Kubernetes trên Amazon EKS

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích cách **Kubernetes Pod** sử dụng lưu trữ qua **Volume, PersistentVolume (PV), PersistentVolumeClaim (PVC), StorageClass và Container Storage Interface (CSI)**.
- Phân biệt rõ **Amazon EBS CSI driver** và **Amazon EFS CSI driver** theo khả năng gắn ổ, chia sẻ dữ liệu, phạm vi Availability Zone, hiệu năng, độ bền và chi phí.
- Thiết lập **StorageClass và PVC** để cấp phát EBS gp3 cho workload stateful trên **EKS EC2 nodes**, sử dụng `WaitForFirstConsumer` để hạn chế lỗi lệch AZ.
- Thiết lập **EFS dynamic provisioning với access point**, hoặc **static provisioning** để nhiều Pod dùng chung hệ thống tệp; biết giới hạn liên quan **EKS Fargate**.
- Hiểu sự khác nhau giữa **EBS CSI thông thường (`ebs.csi.aws.com`)** và **EKS Auto Mode block storage (`ebs.csi.eks.amazonaws.com`)**.
- Thiết kế quyền **IAM Pod Identity hoặc IRSA**, AWS KMS, security group, mount target, DNS, POSIX permissions, snapshot và backup.
- Chẩn đoán PVC `Pending`, Pod `ContainerCreating`, lỗi `FailedAttachVolume`/`FailedMount`, dữ liệu không thể ghi, mount timeout và sai `accessModes`.
- Đưa ra lựa chọn lưu trữ cho ứng dụng Java, database, web uploads, analytics và batch theo tiêu chí **an toàn, quan sát được, phục hồi được và tiết kiệm chi phí**.

**Ngữ cảnh học phần:** Bài thuộc chương **Kubernetes với EKS**, trong module **CLOUD_PROVIDERS_AWS**. EKS cung cấp Kubernetes control plane được AWS quản lý, còn workload có thể chạy trên EC2 nodes, EKS Auto Mode nodes hoặc EKS Fargate tùy cấu hình. Cần kết hợp đúng các kiến thức **Region/AZ, IAM, VPC, EBS/EFS/S3, load balancing, database, serverless, giám sát, phục hồi và chi phí** để dữ liệu của Pod không mất khi container được thay thế.

> **Giới hạn ví dụ:** Các manifest bên dưới chủ yếu dành cho **Linux Pod trên EKS có EC2 nodes**, sử dụng StorageClass tiêu chuẩn và AWS CSI drivers. EKS Auto Mode/Fargate có các điều kiện khác được nêu riêng. Những ID `fs-...`, `vol-...`, tên cluster/Region/bucket đều là minh họa; hãy thay và kiểm tra trên cluster lab trước khi chạy.

## 1. Vì sao container cần lớp lưu trữ riêng?

Container cung cấp filesystem cho quá trình thực thi, nhưng **ghi vào writable layer của container không phải chiến lược lưu trữ dữ liệu bền vững**. Khi Pod bị xóa, reschedule, rollout phiên bản hoặc node gặp lỗi, dữ liệu trong lớp tạm có thể không còn.

Ví dụ:

- Java API tạo báo cáo PDF vào `/tmp/report.pdf` rồi container bị thay: file tạm có thể mất.
- PostgreSQL chạy trong Pod cần dữ liệu tại `/var/lib/postgresql/data` sống lâu hơn một lần chạy container.
- Hai replicas của ứng dụng web muốn cùng đọc file upload: cần một kho tệp hoặc object storage **dùng chung** theo yêu cầu.
- Worker giải mã file lớn cần vùng scratch: có thể **không cần** volume bền vững.

Kubernetes phân biệt:

| Nhu cầu | Giải pháp thường phù hợp | Lưu ý |
| --- | --- | --- |
| Cache/scratch trong vòng đời Pod | `emptyDir` hoặc ephemeral storage phù hợp | Mất khi Pod bị xóa; vẫn chịu giới hạn node |
| Filesystem bền vững cho **một workload gắn node** | **EBS CSI + PVC** | Block volume ở một AZ; phải quan tâm node placement |
| Shared POSIX file cho **nhiều Pod/nhiều AZ** | **EFS CSI + PVC** | NFS, cần mount targets, network, quyền POSIX |
| Object lớn, ảnh, hóa đơn, backup | **S3 API** | Không phải filesystem POSIX mặc định; thiết kế ứng dụng theo object |
| Database nghiệp vụ cần HA/DR quản lý | **RDS/Aurora/DynamoDB** hoặc DB tự quản có replica | Không chỉ cấp PV là tự có database HA |
| Hệ thống tệp chuyên dụng/HPC | **Amazon FSx** theo giao thức/hiệu năng | Phải xem driver, topology và tài nguyên phụ |

**Thông điệp:** EBS/EFS giải quyết khả năng cung cấp block/file storage cho Pod. **Kubernetes không tự biến mọi PV thành storage multi-AZ hoặc backup có thể khôi phục dữ liệu ứng dụng**.

## 2. Năm khái niệm Kubernetes phải nắm

### 2.1. Volume trong Pod

Một **volume** trong Pod là cách container thấy dữ liệu tại một mount path, ví dụ `/app/data`. Container khai báo `volumeMounts`, còn Pod khai báo `volumes`.

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: scratch-example
spec:
  containers:
    - name: worker
      image: busybox:1.36
      command: ["sh", "-c", "echo hello > /scratch/output.txt; sleep 3600"]
      volumeMounts:
        - name: work
          mountPath: /scratch
  volumes:
    - name: work
      emptyDir: {}
~~~

**`emptyDir` không phải PersistentVolume**. Nếu Pod được tái tạo trên node khác, dữ liệu đó không tự được phục hồi. Nó phù hợp với dữ liệu tạm, không phải dữ liệu đơn hàng.

### 2.2. PersistentVolume (PV)

**PV** là tài nguyên cấp cluster đại diện cho storage đã được cung cấp, có thể do quản trị viên tạo **static** hoặc do CSI provisioner tạo **dynamic**.

PV chứa thông tin như:

- capacity và `accessModes`;
- `storageClassName`;
- reclaim policy;
- thông tin driver/volume handle;
- `nodeAffinity` hoặc topology nếu có yêu cầu.

Ví dụ một EBS PV do CSI tạo có thể tham chiếu `volumeHandle: vol-...`; một EFS PV có thể tham chiếu file system/access point. PV là đối tượng API Kubernetes, **không phải bản thân ổ vật lý**.

### 2.3. PersistentVolumeClaim (PVC)

**PVC** là yêu cầu storage của một namespace: “Tôi cần 10 GiB, `ReadWriteOnce`, dùng StorageClass `ebs-gp3`”. Khi phù hợp, controller **bind** PVC với một PV.

~~~text
Namespace team-a
  └── PVC orders-data (10Gi, RWO)
        └── PV pvc-123... (bound)
              └── EBS volume vol-123... thuộc AZ A
~~~

Pod chỉ cần tham chiếu **PVC name**, không cần biết AWS EBS volume ID trong manifest ứng dụng. Cơ chế này giúp nhóm ứng dụng và nhóm hạ tầng phân tách trách nhiệm.

### 2.4. StorageClass

**StorageClass** là cấu hình của **provisioner** để tự cấp PV khi có PVC phù hợp. Với EKS, StorageClass có thể chỉ rõ:

- CSI provisioner `ebs.csi.aws.com` hoặc `efs.csi.aws.com`;
- thông số EBS như `type: gp3`, encryption, IOPS/throughput;
- thông số EFS như `fileSystemId`, `provisioningMode: efs-ap`;
- `volumeBindingMode`, `allowVolumeExpansion`, `reclaimPolicy`.

**Không có nghĩa một cluster chỉ được có một StorageClass.** Có thể tạo lớp `gp3` cho database, `efs-ap` cho shared files và lớp riêng cho EKS Auto Mode.

### 2.5. CSI driver

**Container Storage Interface (CSI)** là chuẩn tích hợp storage với Kubernetes. CSI driver kết nối yêu cầu Kubernetes với thao tác tạo, attach, mount hoặc tháo volume của hạ tầng.

~~~mermaid
flowchart LR
    App[Pod có volumeMount] --> PVC[PersistentVolumeClaim]
    PVC --> PV[PersistentVolume]
    PV --> SC[StorageClass / CSI driver]
    SC --> AWS{AWS storage}
    AWS --> EBS[Amazon EBS block]
    AWS --> EFS[Amazon EFS NFS]
    PV -. Metadata / volume handle .-> App
~~~

Sơ đồ mô tả quan hệ cấu hình; trong thực tế, khi dynamic provisioning, StorageClass được dùng để **tạo PV từ PVC** rồi CSI controller/node components thực hiện các bước cấp/gắn/mount. Không phải mỗi request I/O của ứng dụng đi qua Kubernetes API.

## 3. EBS CSI và EFS CSI: so sánh trọng tâm

| Tiêu chí | **EBS CSI** | **EFS CSI** |
| --- | --- | --- |
| Dịch vụ AWS | Amazon Elastic Block Store | Amazon Elastic File System |
| Kiểu storage | Block device; filesystem trên block | Shared file system, NFS |
| CSI provisioner tiêu chuẩn | `ebs.csi.aws.com` | `efs.csi.aws.com` |
| Phạm vi vị trí | **Một EBS volume thuộc một AZ** | File system EFS **Regional** có thể được mount từ nhiều AZ qua mount targets |
| Access mode phổ biến | **RWO** (ReadWriteOnce); RWOP theo driver/K8s hỗ trợ | **RWX** (ReadWriteMany) |
| Nhiều Pod dùng đồng thời | RWO giới hạn **một node** ghi theo semantics; không thay cluster filesystem | Nhiều nodes/Pods đọc-ghi cùng filesystem nếu network/quyền cho phép |
| Hiệu năng | gp3/io2, IOPS và throughput cấu hình theo loại volume, latency block thấp | NFS network filesystem, throughput/IO pattern, metadata và network latency |
| Dung lượng | Cấp trước theo PVC/StorageClass, điều chỉnh trong giới hạn | File system tự mở rộng; PVC `storage` không phải quota cứng |
| Hỗ trợ EKS Fargate | **Không mount EBS vào Fargate Pod** | Hỗ trợ **static PV**, không dynamic provisioning trên Fargate |
| Hỗ trợ EKS Auto Mode | Driver **riêng** `ebs.csi.eks.amazonaws.com` | Cần kiểm tra cấu hình/driver, network, workload type |
| Data recovery | CSI VolumeSnapshots/EBS snapshots; DB-aware backup | Backup/AWS Backup, EFS Replication theo thiết kế, bảo vệ dữ liệu file |
| Chi phí chính | GiB provisioned, IOPS/throughput provisioned, snapshot | Dung lượng, throughput/request tùy chế độ/tier, backup và truyền dữ liệu |

**Quy tắc chọn ngắn:** Nếu một Pod database cần block storage với I/O ngẫu nhiên và latency thấp, **EBS** đáng đánh giá. Nếu nhiều Pod trên các nodes/AZ khác nhau cần một thư mục chung theo chuẩn NFS/POSIX, **EFS** phù hợp hơn. Nếu ứng dụng lưu ảnh/video và không cần POSIX filesystem, nên đánh giá **S3**, vì filesystem NFS không phải lựa chọn bắt buộc.

### Access modes không tự cấp quyền bảo mật

Các access modes của Kubernetes mô tả **cách volume có thể được mount/claim**, không phải một danh sách quyền truy cập file:

- **ReadWriteOnce (RWO):** volume mount read-write bởi **một node** tại một thời điểm; nhiều Pod **trên cùng node** có thể có tình huống cùng sử dụng.
- **ReadWriteOncePod (RWOP):** giới hạn cho **một Pod** trong toàn cluster khi CSI/Kubernetes hỗ trợ; hữu ích khi cần một writer ở cấp Pod.
- **ReadWriteMany (RWX):** nhiều nodes có thể mount read-write, phù hợp với EFS.
- **ReadOnlyMany (ROX):** nhiều nodes mount chỉ đọc theo backend hỗ trợ.

**Không hiểu RWO = “chỉ một Pod duy nhất có thể đọc hoặc ghi trong mọi trường hợp”.** Đây là một nhầm lẫn phổ biến. Với EFS RWX, hai Pod vẫn có thể ghi đè cùng file hoặc gây race condition; cần cơ chế locking/transaction và quản lý quyền POSIX ở cấp ứng dụng.

## 4. Kiến trúc EKS với EBS và EFS qua nhiều AZ

Giả sử EKS cluster ở Region `ap-southeast-1`, có các EC2 nodes trải AZ A/B và API triển khai nhiều replicas:

~~~mermaid
flowchart TB
    LB[ALB / Ingress] --> API[Java API Deployment]
    API --> P1[API Pod AZ A]
    API --> P2[API Pod AZ B]

    subgraph AZA["AZ A"]
      P1 --> EA[(EBS volume: app cache/data A)]
      N1[EC2 Node A]
    end
    subgraph AZB["AZ B"]
      P2 --> EB[(EBS volume: app cache/data B)]
      N2[EC2 Node B]
    end

    P1 --> EFS[(EFS Regional: shared/uploads)]
    P2 --> EFS
    P1 --> DB[(RDS Multi-AZ / DynamoDB)]
    P2 --> DB
    Backup[Snapshots / AWS Backup] -. Bảo vệ dữ liệu .-> EA
    Backup -. Bảo vệ dữ liệu .-> EB
    Backup -. Bảo vệ dữ liệu .-> EFS
~~~

Mô hình trên minh họa **mỗi replica có EBS riêng**, còn **EFS là filesystem chung**. Điều này rất quan trọng:

- **Hai EBS volume độc lập không tự đồng bộ dữ liệu.** Nếu ứng dụng cần cùng thấy file, phải dùng EFS hoặc thiết kế replication ngoài.
- **EBS volume chỉ attach vào EC2 node cùng AZ**. Khi Pod chuyển sang AZ khác, scheduler không thể đơn giản mang volume sang AZ mới.
- **EFS Regional** có thể phục vụ Pod ở nhiều AZ, nhưng mỗi AZ cần mount path/network phù hợp; độ trễ mạng và throughput cần đo.
- **Database Multi-AZ** là cấu hình HA riêng của DB, không tự có từ việc Kubernetes replica count = 2.
- **Snapshots và backup** không thay thế cơ chế failover tức thời nếu RTO rất ngắn.

## 5. EBS CSI driver hoạt động như thế nào?

Với EBS CSI tiêu chuẩn:

1. Quản trị viên triển khai **Amazon EBS CSI driver** vào cluster, thường là **EKS add-on** `aws-ebs-csi-driver` trên EC2-backed cluster.
2. CSI controller được cấp **IAM permissions** để gọi các EC2/EBS API cấp phát/sửa/xóa/attach/snapshot theo phạm vi hỗ trợ.
3. Quản trị viên tạo StorageClass `provisioner: ebs.csi.aws.com`.
4. Ứng dụng tạo PVC theo StorageClass và Pod dùng PVC.
5. CSI controller cung cấp EBS volume; node plugin gắn, định dạng/mount volume theo lifecycle.
6. Khi Pod bị xóa/tạo lại, PVC có thể tiếp tục gắn tới **volume cũ**, miễn scheduling/AZ và chính sách giữ/xóa phù hợp.

~~~mermaid
sequenceDiagram
    participant Dev as kubectl / app owner
    participant API as Kubernetes API
    participant CSI as EBS CSI controller
    participant EC2 as AWS EC2/EBS API
    participant Node as Worker node / kubelet

    Dev->>API: Tạo StorageClass + PVC + Pod
    API->>CSI: PVC cần cấp volume theo StorageClass
    CSI->>EC2: CreateVolume (AZ, type, encryption)
    EC2-->>CSI: EBS volume ID
    CSI->>API: Tạo/bind PV
    API->>Node: Schedule Pod trên node phù hợp AZ
    Node->>CSI: Yêu cầu attach/mount qua CSI node plugin
    CSI->>EC2: Attach volume (khi phù hợp)
    Node-->>Dev: Pod có mount path, workload chạy
~~~

Thứ tự có thể khác khi dùng `WaitForFirstConsumer`: Kubernetes xác định Pod/node/topology trước rồi driver mới cấp volume. Sơ đồ minh họa trách nhiệm các thành phần, không phải trình tự API cố định cho mọi deployment.

### Controller và node plugin khác nhau

| Thành phần | Chức năng chính |
| --- | --- |
| **CSI controller** | Tạo/xóa volume qua AWS API, điều phối attachment và một số thao tác quản lý |
| **CSI node plugin** | Phối hợp kubelet để nhận volume/format/mount/unmount trên node |
| **Kubernetes scheduler** | Chọn node có tài nguyên, label/taint/topology tương thích PVC |
| **Kubernetes attach/detach controller và sidecars** | Điều phối metadata/trạng thái volume attachments theo cơ chế CSI |

Driver hoạt động đúng cần **cả IAM cho controller và node plugin trên các node tương ứng**. Trên EKS EC2 nodes, add-on driver có node components chạy dạng DaemonSet. Có thể chạy controller trên môi trường phù hợp nhưng **EBS node plugin không mount EBS lên EKS Fargate Pod**.

## 6. StorageClass EBS gp3: cấu hình nền tảng

Ví dụ triển khai **EBS CSI driver tiêu chuẩn** trên EC2 nodes. File `ebs-gp3-storageclass.yaml`:

~~~yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: ebs-gp3
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  encrypted: "true"
  csi.storage.k8s.io/fstype: ext4
reclaimPolicy: Retain
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer
~~~

**Ý nghĩa:**

- `provisioner`: EBS CSI driver tiêu chuẩn, không phải Auto Mode.
- `type: gp3`: loại ổ SSD đa dụng; baseline hiện hành của gp3 là **3.000 IOPS và 125 MiB/s** nếu không cấp hiệu năng cao hơn.
- `encrypted: "true"`: tạo volume được mã hóa EBS; nếu dùng customer managed KMS key, cần khai báo `kmsKeyId` và quyền KMS tương ứng.
- `reclaimPolicy: Retain`: khi PVC được xóa, PV/underlying EBS không bị tự động xóa theo chính sách reclaim này; người quản trị cần thao tác phục hồi/dọn đúng quy trình.
- `allowVolumeExpansion: true`: cho phép PVC yêu cầu tăng capacity khi driver/Kubernetes/filesystem hỗ trợ.
- `WaitForFirstConsumer`: chờ biết Pod đầu tiên và topology node thích hợp rồi mới cấp EBS volume.

**Thận trọng:** Không nên thêm annotation `is-default-class` chỉ để chạy lab trên cluster có nhiều StorageClass; đặt `storageClassName` tường minh trong PVC giúp tránh vô tình cấp volume sai loại/chi phí.

### Vì sao WaitForFirstConsumer gần như bắt buộc về mặt thiết kế?

Một EBS volume được tạo trong **một AZ cụ thể**. Nếu PVC được cấp volume ở AZ A trước khi có thông tin scheduler, nhưng Pod lại chỉ có thể chạy tại AZ B vì nodeSelector, affinity hoặc thiếu capacity, PVC/Pod có thể mắc kẹt.

~~~text
Immediate:
  PVC → volume tạo sớm ở AZ A
  Pod → scheduler yêu cầu node AZ B
  Kết quả: xung đột topology/AZ, Pod Pending hoặc FailedAttach

WaitForFirstConsumer:
  PVC chưa cấp volume ngay
  Pod → scheduler chọn node có topology hợp lệ AZ B
  CSI tạo volume phù hợp AZ B
  Kết quả: tránh cấp volume sai AZ trong lần đầu
~~~

**Không nên cố sửa bằng cách nới toàn bộ node affinity** nếu workload cần node ở AZ khác. Hãy kiểm tra nhu cầu dữ liệu, storage topology và khả năng scheduler trước.

### Các thông số gp3 nâng cao

Có thể thêm vào StorageClass theo driver/API và giới hạn hiện hành:

~~~yaml
parameters:
  type: gp3
  encrypted: "true"
  iops: "6000"
  throughput: "250"
~~~

Ví dụ cần nhiều IOPS/throughput hơn baseline cho database tải cao. Cả hai thành phần cấp thêm có thể **phát sinh phí**; trần hiệu năng còn phụ thuộc dung lượng, giới hạn instance và tài khoản. Đừng coi `iops: "6000"` sẽ được đạt trong mọi Pod nếu node có bottleneck EBS bandwidth.

## 7. PVC và Pod sử dụng EBS trên EC2 node

File `ebs-pvc.yaml`:

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
  namespace: default
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: ebs-gp3
  resources:
    requests:
      storage: 20Gi
~~~

File `ebs-demo-pod.yaml`:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: ebs-writer
  namespace: default
spec:
  containers:
    - name: writer
      image: busybox:1.36
      command:
        - sh
        - -c
        - |
          while true; do
            date -u >> /data/timestamps.txt
            sleep 15
          done
      volumeMounts:
        - name: persistent
          mountPath: /data
  volumes:
    - name: persistent
      persistentVolumeClaim:
        claimName: postgres-data
~~~

**File chỉ là ví dụ storage**, không thực sự chạy PostgreSQL; đặt tên PVC là `postgres-data` để hình dung workload. Trên production, database cần deployment StatefulSet, cấu hình backup/log/consistency và bảo vệ dữ liệu thích hợp.

Áp dụng trong cluster lab đã có EBS CSI driver:

~~~bash
kubectl apply -f ebs-gp3-storageclass.yaml
kubectl apply -f ebs-pvc.yaml
kubectl apply -f ebs-demo-pod.yaml

kubectl get sc
kubectl get pvc,pv
kubectl get pod ebs-writer -o wide
kubectl describe pvc postgres-data
kubectl describe pod ebs-writer
~~~

Vì `WaitForFirstConsumer`, PVC có thể tạm `Pending` khi **chưa có Pod** sử dụng; đó không phải lỗi nếu chỉ mới áp dụng PVC. Sau khi Pod được schedule và volume provision thành công, PVC thường chuyển `Bound`.

### Xác minh dữ liệu tồn tại qua vòng đời Pod

~~~bash
kubectl exec ebs-writer -- sh -c 'tail -n 3 /data/timestamps.txt'

kubectl delete pod ebs-writer
kubectl apply -f ebs-demo-pod.yaml

kubectl exec ebs-writer -- sh -c 'tail -n 3 /data/timestamps.txt'
~~~

Pod mới có thể được schedule tới node **khác nhưng cùng AZ** với volume và lại mount dữ liệu từ PVC cũ. Nếu không còn node phù hợp trong AZ đó, Pod có thể không lên được cho tới khi có capacity ở AZ cũ hoặc dữ liệu được **restore/migrate** sang volume mới ở AZ khác.

**Quan trọng:** Nếu ứng dụng thực sự cần consistency, dừng Pod đột ngột không bảo đảm file/database đang ghi ở trạng thái nhất quán. Mục lab chỉ xác minh **lifecycle của EBS PV**, không thay bài kiểm thử database backup.

## 8. StatefulSet và volumeClaimTemplates cho ứng dụng có trạng thái

**Deployment** thường phù hợp ứng dụng stateless có replicas thay thế tùy ý. Với workload stateful cần danh tính ổn định và volume riêng cho từng replica, **StatefulSet + volumeClaimTemplates** là mô hình Kubernetes cần biết.

Ví dụ rút gọn chạy BusyBox ghi dữ liệu vào volume riêng của từng replica:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: writer-headless
spec:
  clusterIP: None
  selector:
    app: stateful-writer
  ports:
    - port: 80
      name: placeholder
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: stateful-writer
spec:
  serviceName: writer-headless
  replicas: 2
  selector:
    matchLabels:
      app: stateful-writer
  template:
    metadata:
      labels:
        app: stateful-writer
    spec:
      containers:
        - name: writer
          image: busybox:1.36
          command: ["sh", "-c", "while true; do date -u >> /data/log.txt; sleep 30; done"]
          volumeMounts:
            - name: data
              mountPath: /data
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: ebs-gp3
        resources:
          requests:
            storage: 10Gi
~~~

Sau khi tạo, PVC thường có tên kiểu:

~~~text
data-stateful-writer-0 → EBS volume của replica 0
data-stateful-writer-1 → EBS volume của replica 1
~~~

**Mỗi Pod có volume riêng, không phải hai replicas cùng thấy dữ liệu.** Nếu đó là PostgreSQL cluster, replication giữa các bản sao phải do database/operator thực hiện; StatefulSet **không tự đồng bộ dữ liệu DB**.

Khi xóa StatefulSet hoặc scale down, PVC thường có cơ chế retention riêng; đừng giả định xóa StatefulSet sẽ xóa sạch dữ liệu. Kubernetes có chính sách retention đối với PVC của StatefulSet theo phiên bản/cấu hình; ngoài ra `reclaimPolicy` của PV vẫn tác động đến tài nguyên backend. Luôn kiểm tra cả hai trước khi chạy lệnh xóa.

### Khi nào EBS là lựa chọn tốt cho StatefulSet?

- Mỗi replica có **dataset riêng**, ví dụ node của một distributed database hoặc queue cluster.
- Workload random I/O cần block latency thấp.
- Ứng dụng có cơ chế replication, quorum, failover và backup **độc lập** với CSI.
- Có kế hoạch khi Pod bị reschedule nhưng EBS volume không thể đổi AZ trực tiếp.

Nếu tất cả replicas cần truy cập chung tệp tại một đường dẫn POSIX, đánh giá **EFS** hoặc một file service phù hợp hơn.

## 9. EBS CSI, EKS Auto Mode và EKS Fargate: ba mô hình khác nhau

### 9.1. EBS CSI driver tiêu chuẩn

- Provisioner: `ebs.csi.aws.com`.
- Dùng với các node EC2 tương thích, node plugin mount EBS vào node.
- Cài qua **Amazon EKS add-on `aws-ebs-csi-driver`** hoặc self-managed driver khi có lý do và khả năng tương thích.
- IAM cho controller: thường sử dụng **EKS Pod Identity hoặc IRSA** theo AWS guidance.
- EBS volume được gắn vào **node EC2 thuộc đúng AZ**.

### 9.2. EKS Auto Mode block storage

**EKS Auto Mode** tích hợp capability quản lý block storage; không bắt buộc cài EBS CSI controller tiêu chuẩn để dùng phần lưu trữ này. StorageClass cần sử dụng **một provisioner khác**:

~~~yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: auto-ebs-gp3
provisioner: ebs.csi.eks.amazonaws.com
parameters:
  type: gp3
  encrypted: "true"
volumeBindingMode: WaitForFirstConsumer
allowedTopologies:
  - matchLabelExpressions:
      - key: eks.amazonaws.com/compute-type
        values:
          - auto
reclaimPolicy: Retain
allowVolumeExpansion: true
~~~

Điều kiện `allowedTopologies` trong ví dụ giới hạn volume/workload vào loại node Auto Mode tương ứng ở cluster **hỗn hợp node types**. Auto Mode **không tự tạo StorageClass** chỉ vì cluster đã bật Auto Mode; cần định nghĩa lớp phù hợp.

**Đừng thay trực tiếp `ebs.csi.aws.com` thành `ebs.csi.eks.amazonaws.com` trên StorageClass của PVC đã có dữ liệu rồi xem đó là migration.** Đây là hai hệ thống provisioner quản lý volumes riêng; chuyển workload hiện có cần kế hoạch snapshot/restore hoặc quy trình migration được hỗ trợ, với kiểm chứng dữ liệu và downtime.

Với EKS Auto Mode dùng **customer managed KMS key**, quyền KMS có liên quan tới **EKS cluster role** theo tài liệu Auto Mode; **đừng sao chép nguyên mô hình controller Pod Identity/IRSA của EBS CSI tiêu chuẩn** cho phần capability do Auto Mode quản lý.

**Cập nhật lưu ý về hiệu năng sau khi tạo volume:** Tại EKS Auto Mode/Kubernetes đủ mới, việc thay loại EBS, IOPS và throughput có thể dùng **VolumeAttributesClass**; tài liệu AWS ghi rõ hướng chuyển khỏi dự án `volume-modifier-for-k8s` dựa trên annotations. Khi thay đổi volume thật, cần đối chiếu Kubernetes version và API được hỗ trợ, không dựa vào annotations cũ.

### 9.3. EKS Fargate

Với **EKS Fargate Pod**, **không thể mount EBS volume** như trên EC2 node. Fargate có ephemeral storage riêng, còn shared persistent file có thể tích hợp **Amazon EFS**.

**EFS trên EKS Fargate hỗ trợ static provisioning, không hỗ trợ dynamic provisioning cho PersistentVolumes**. Fargate có thành phần EFS mount tích hợp, không cần tự cài EFS CSI node DaemonSet trên Fargate nodes. Cần cấu hình file system, mount targets và PVC/PV tĩnh đúng cách. Đừng tạo PVC dynamic `efs-ap` rồi kỳ vọng Fargate tự cấp EFS access point.

| Tính năng | EC2 nodes + CSI chuẩn | EKS Auto Mode nodes | EKS Fargate |
| --- | --- | --- | --- |
| EBS persistent PV | Có, dùng EBS CSI | Có, dùng Auto Mode provisioner | **Không** |
| EFS persistent PV | Có, qua EFS CSI | Theo cấu hình driver/runtime tương ứng | Có, **static provisioning** |
| EBS CSI controller tự quản | Được cài qua add-on/self-managed | Không cần cho Auto Mode block storage | Có thể chạy controller ở môi trường tương thích, nhưng không có node mount EBS |
| Shared RWX file | EFS/FSx phù hợp | EFS/FSx theo khả năng cụ thể | EFS static |
| Ephemeral scratch | Node/Pod ephemeral volumes | Tùy node/workload | Fargate ephemeral storage |

## 10. EFS CSI: cấp shared filesystem cho nhiều Pod

**Amazon EFS** là network filesystem **NFS** dùng chung. Với EKS, **Amazon EFS CSI driver** cung cấp cách tạo PV hoặc mount filesystem/access point vào Pods.

Một EFS Regional file system có thể được truy cập bởi nhiều Pods trên nodes khác nhau khi:

- EFS file system có **mount targets** trong VPC/AZ phù hợp;
- node/task có network route, DNS và security group đến mount target trên **TCP 2049**;
- IAM/file system policy và POSIX permissions cho phép thao tác;
- CSI node plugin/mount helper hoạt động đúng trên môi trường tương ứng.

~~~mermaid
flowchart TB
    subgraph A["AZ A"]
      P1[Web Pod A] --> MT1[EFS mount target A]
      N1[EC2 Node A]
    end
    subgraph B["AZ B"]
      P2[Web Pod B] --> MT2[EFS mount target B]
      N2[EC2 Node B]
    end
    MT1 --> FS[(EFS Regional file system)]
    MT2 --> FS
    FS --> AP1[EFS Access Point /team-a]
    FS --> AP2[EFS Access Point /team-b]
~~~

**EFS access point** giúp ánh xạ root directory và POSIX user/group cho một ứng dụng hoặc nhóm dữ liệu. Các access points **không tự tạo một hệ thống tệp vật lý khác**; dữ liệu vẫn nằm trong cùng EFS file system trừ khi chủ động tách file systems.

### EFS có phù hợp database giao dịch không?

EFS cung cấp file semantics/NFS, không phải block EBS có latency tương đương. Một số phần mềm database có những yêu cầu filesystem/locking/fsync và độ trễ riêng; không chuyển database từ EBS sang EFS chỉ để “có nhiều Pod mount được”. Với database quan hệ, cân nhắc **RDS/Aurora** hoặc một operator/database cluster được chứng minh tương thích storage, durability và HA.

## 11. EFS dynamic provisioning với access point

Trên **EKS EC2 nodes** có EFS CSI driver phiên bản hỗ trợ, dynamic provisioning có thể tạo **EFS access point** mới khi một PVC yêu cầu storage. EFS file system phải **đã tồn tại** trước đó.

### Bước chuẩn bị

1. Tạo EFS Regional file system trong VPC phù hợp và chọn chế độ performance/throughput theo workload.
2. Tạo **mount target** ở những AZ có EKS worker nodes; gắn SG EFS cho phép inbound **TCP/2049 từ node SG**.
3. Bảo đảm DNS resolver và route trong VPC phân giải/đi đến mount targets.
4. Cài **Amazon EFS CSI driver** dưới dạng EKS add-on `aws-efs-csi-driver` cho EC2 nodes và cấp IAM quyền EFS API phù hợp cho controller qua Pod Identity/IRSA.
5. Xem EFS file system policy, encryption at rest, TLS in transit, access point và POSIX permissions.

### StorageClass tạo access point tự động

File `efs-ap-sc.yaml`:

~~~yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: efs-ap
provisioner: efs.csi.aws.com
parameters:
  provisioningMode: efs-ap
  fileSystemId: fs-0123456789abcdef0
  directoryPerms: "750"
  basePath: "/k8s-dynamic"
reclaimPolicy: Retain
volumeBindingMode: Immediate
mountOptions:
  - tls
~~~

Giải thích:

- `fileSystemId` trỏ **EFS đã tạo**; không tự tạo EFS file system.
- `provisioningMode: efs-ap` yêu cầu driver tạo **access point** theo PVC.
- `directoryPerms` chi phối permission khi driver tạo directory tương ứng trong tình huống hỗ trợ; **POSIX UID/GID và access point identity** vẫn cần kiểm tra.
- `mountOptions: [tls]` yêu cầu mã hóa khi truyền dữ liệu NFS theo helper/driver hỗ trợ.
- `reclaimPolicy: Retain` giữ PV/backend reference khi xóa PVC để tránh mất dữ liệu ngoài ý muốn; yêu cầu dọn thủ công khi không còn cần.

Với `reclaimPolicy: Delete`, dynamic provisioner thường sẽ dọn **access point** khi PV bị reclaim; **không mặc định toàn bộ file/directory dữ liệu cũ đã bị xóa khỏi EFS file system**. Phải xác minh storage cleanup và quyền để tránh bỏ lại dữ liệu nhạy cảm/chi phí.

### PVC RWX

File `efs-pvc.yaml`:

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: shared-upload
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: efs-ap
  resources:
    requests:
      storage: 5Gi
~~~

**`5Gi` ở PVC EFS không tự áp hạn ngạch 5 GiB lên file system.** EFS có dung lượng co giãn theo file đã lưu; muốn quota từng nhóm cần thiết kế riêng hoặc giới hạn ở lớp ứng dụng/giải pháp hỗ trợ.

### Hai Pod chia sẻ một PVC

File `efs-two-pods.yaml`:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: efs-writer-a
spec:
  containers:
    - name: writer
      image: busybox:1.36
      command:
        - sh
        - -c
        - |
          echo "writer A started" >> /shared/notes.txt
          sleep 3600
      volumeMounts:
        - name: shared
          mountPath: /shared
  volumes:
    - name: shared
      persistentVolumeClaim:
        claimName: shared-upload
---
apiVersion: v1
kind: Pod
metadata:
  name: efs-reader-b
spec:
  containers:
    - name: reader
      image: busybox:1.36
      command: ["sh", "-c", "sleep 3600"]
      volumeMounts:
        - name: shared
          mountPath: /shared
  volumes:
    - name: shared
      persistentVolumeClaim:
        claimName: shared-upload
~~~

Khi cả hai Pod `Running`, thử:

~~~bash
kubectl exec efs-writer-a -- cat /shared/notes.txt
kubectl exec efs-reader-b -- cat /shared/notes.txt
kubectl exec efs-reader-b -- sh -c 'echo writer-B >> /shared/notes.txt'
kubectl exec efs-writer-a -- cat /shared/notes.txt
~~~

Nếu xuất hiện `Permission denied`, đừng kết luận EFS không hỗ trợ RWX. Hãy kiểm tra access point POSIX UID/GID, `directoryPerms`, `runAsUser`, `fsGroup`, file system policy và trạng thái mount. **RWX là mô hình mount**, không phải quyền được phép ghi mọi file.

## 12. EFS static provisioning: giải pháp cho tài nguyên có sẵn và Fargate

Với static provisioning, quản trị viên **tạo PV chỉ vào một EFS file system hoặc access point đã tồn tại**. PVC được bind tới PV tương ứng.

Mẫu có **EFS access point đã tạo trước**:

~~~yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: efs-static-pv
spec:
  capacity:
    storage: 5Gi
  volumeMode: Filesystem
  accessModes:
    - ReadWriteMany
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ""
  csi:
    driver: efs.csi.aws.com
    volumeHandle: "fs-0123456789abcdef0::fsap-0123456789abcdef0"
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: efs-static-claim
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: ""
  volumeName: efs-static-pv
  resources:
    requests:
      storage: 5Gi
~~~

**`volumeHandle` trong ví dụ dùng định dạng EFS file system ID + EFS access point ID**. Phải có access point thật trước khi áp dụng, đúng filesystem và IAM/POSIX. `storageClassName: ""` chỉ rõ không sử dụng StorageClass dynamic mặc định; `volumeName` ràng buộc PVC vào PV tĩnh.

Ví dụ Pod mount claim:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: efs-static-reader
spec:
  containers:
    - name: reader
      image: busybox:1.36
      command: ["sh", "-c", "sleep 3600"]
      volumeMounts:
        - name: shared
          mountPath: /shared
  volumes:
    - name: shared
      persistentVolumeClaim:
        claimName: efs-static-claim
~~~

Đối với **EKS Fargate**, cần đảm bảo Pod được chọn bởi **Fargate profile**, filesystem có mount targets reachable từ network của Pod, và policy/permissions phù hợp. Fargate mounts EFS bằng cơ chế tích hợp, **không cài EFS CSI node DaemonSet thủ công lên Fargate**. Kiểm tra giới hạn/khả năng hỗ trợ của bản EKS và loại workload trước khi triển khai.

**Cẩn trọng dữ liệu:** PV/PVC capacity `5Gi` không có nghĩa EFS access point giới hạn đúng 5 GiB dữ liệu. Hệ thống quota/billing EFS hoạt động ở lớp file system theo đặc tính dịch vụ.

## 13. Storage topology, scheduling và lỗi khác AZ

EBS tạo trong **AZ A** nhưng node chạy Pod ở **AZ B** là một nguyên nhân phổ biến khiến Pod bị `Pending` hoặc `ContainerCreating`.

### 13.1. Khi PVC đã bound vào EBS cũ

Giả sử PVC trỏ tới `vol-aaaa` ở AZ A. Node selector mới yêu cầu AZ B:

~~~text
PVC → PV (vol-aaaa, AZ A)
Pod → nodeSelector / affinity yêu cầu AZ B
Scheduler → không có node đáp ứng cả PVC topology và node rules
Pod → Pending
~~~

**Không thể đổi AZ của một EBS volume đã có** bằng cách chỉnh `nodeAffinity` trên PV. Tạo volume mới ở AZ đích thường phải qua **snapshot/restore hoặc replication/application migration**. Sửa metadata cho qua validation khi underlying volume vẫn ở AZ A là không an toàn và không giải quyết vấn đề vật lý.

### 13.2. Pod reschedule và node autoscaling

Khi Karpenter/Cluster Autoscaler thêm node, cần tính:

- Nodes phải thuộc AZ tương thích với **PV đã bind**;
- capacity type/instance type hỗ trợ EBS/ENI/attachment limits;
- taints/tolerations, node affinity và topology spread constraints;
- thời gian node mới Ready, thời gian EBS detach khỏi node cũ rồi attach sang node mới;
- rollout/PodDisruptionBudget và yêu cầu HA của StatefulSet.

**PodDisruptionBudget** hỗ trợ hạn chế một số lần gián đoạn tự nguyện, nhưng không ngăn được outage hạ tầng hoặc mọi lệnh thao tác; PDB **không tự bảo vệ dữ liệu EBS khỏi mất AZ**.

### 13.3. EFS ít phụ thuộc AZ hơn nhưng không miễn phí topology

Với **EFS Regional**, hai Pod ở AZ khác nhau có thể đọc chung namespace thông qua mount targets; tuy nhiên nếu một AZ thiếu EFS mount target, client có thể dùng đường mạng khác, dẫn đến độ trễ/chi phí/phụ thuộc tăng. Thiết kế thông thường là có **mount targets ở các AZ chứa workload**, đo network latency và cách mount helper chọn địa chỉ.

Với **EFS One Zone**, dữ liệu chỉ nằm trong một AZ; không được coi loại này có mức chịu lỗi AZ giống EFS Regional. Chọn loại phù hợp RTO/RPO và mức mất dữ liệu chấp nhận được.

## 14. IAM: quyền CSI controller không phải quyền ứng dụng

Khi EBS CSI driver tạo volume, controller cần API quyền kiểu `ec2:CreateVolume`, `ec2:AttachVolume`, `ec2:DeleteVolume`, `ec2:CreateTags`, mô tả volume/snapshots và những hành động tương ứng. Với EFS dynamic, controller cần quyền như `elasticfilesystem:CreateAccessPoint`, `DeleteAccessPoint`, `DescribeFileSystems` theo IAM policy được AWS hướng dẫn.

**Đừng cấp toàn bộ các quyền này cho Java application Pod chỉ để app ghi file vào mount.** Có hai ranh giới:

| Principal | Cần quyền gì? | Ví dụ |
| --- | --- | --- |
| **EBS CSI controller** | API thao tác EBS/EC2 trong phạm vi quản lý PV | CreateVolume, AttachVolume, snapshot, modify theo chức năng |
| **EFS CSI controller** | API thao tác EFS access points/file system metadata khi dynamic | CreateAccessPoint, DeleteAccessPoint theo điều kiện |
| **Application Pod** | Thao tác file trên volume đã mount; AWS API khác nếu ứng dụng gọi | `s3:GetObject`, `sqs:SendMessage` thuộc app role |
| **Kubernetes user/admin** | Quyền K8s RBAC để tạo StorageClass, PVC, PV, Pod, snapshot | Không đồng nghĩa có quyền AWS API qua IAM |
| **EKS node / Fargate role** | Các hành động của hạ tầng runtime theo loại compute | Không nên dùng thay quyền CSI/app |

### IAM Pod Identity và IRSA

AWS hỗ trợ **EKS Pod Identity** và **IAM Roles for Service Accounts (IRSA)** cho phép workload/controller Pod nhận AWS credentials tạm thời theo danh tính ServiceAccount.

- **Pod Identity** dùng cơ chế EKS Pod Identity association và trust cho service principal `pods.eks.amazonaws.com`, ở các trường hợp hỗ trợ.
- **IRSA** dùng OIDC provider của EKS, token của Kubernetes ServiceAccount và trust policy `sts:AssumeRoleWithWebIdentity`.
- Driver IAM role cần được **gắn đúng ServiceAccount của CSI controller**, thường trong namespace `kube-system`.
- Trên EKS Auto Mode, block storage capability có cơ chế quyền khác driver truyền thống; xem hướng dẫn EKS Auto Mode và KMS cluster role.

Ví dụ kiểm tra EKS add-ons:

~~~bash
aws eks describe-addon \
  --cluster-name storage-lab \
  --addon-name aws-ebs-csi-driver \
  --region ap-southeast-1

aws eks describe-addon \
  --cluster-name storage-lab \
  --addon-name aws-efs-csi-driver \
  --region ap-southeast-1
~~~

Các lệnh trên chỉ kiểm tra **EKS managed add-ons**. Nếu driver được cài self-managed Helm hoặc bạn dùng Auto Mode, add-on có thể không xuất hiện và đó không tự chứng minh storage bị lỗi.

### Chọn managed IAM policies có kiểm soát

AWS cung cấp các chính sách quản lý cho CSI drivers (tên/phiên bản có thể thay đổi), ví dụ **AmazonEBSCSIDriverPolicyV2** hoặc lựa chọn phù hợp scope và **AmazonEFSCSIDriverPolicy**. Kiểm tra policy chính thức, điều kiện theo resource tags và tài khoản thay vì tự tạo `ec2:*`/`elasticfilesystem:*` trên `*`.

Khi dùng **customer managed KMS key** cho EBS, cần xem IAM + key policy/grants, `kms:CreateGrant` trong phạm vi cần thiết và key Region. Lỗi KMS có thể biểu hiện ở PVC provisioning hoặc attach dù Kubernetes RBAC hoàn toàn hợp lệ.

## 15. VPC, DNS, mount target và POSIX: bảo mật EFS

### 15.1. Luồng NFS qua TCP/2049

EFS mount cần đường mạng:

~~~mermaid
flowchart LR
    P[Pod] --> Node[EC2 Node hoặc Fargate networking]
    Node --> DNS[VPC DNS resolver / EFS DNS]
    DNS --> MT[EFS mount target IP]
    Node -->|TCP 2049 / TLS khi cấu hình| MT
    MT --> EFS[(EFS filesystem)]
~~~

**Security group điển hình:**

- SG của **EFS mount target**: inbound **TCP/2049** từ **node SG** hoặc SG mạng Pod theo thực tế.
- Node/Pod SG: outbound TCP/2049 tới EFS mount target SG/IP theo policy tổ chức.
- NACL (nếu khóa chặt) cho phép lưu lượng **cả hai chiều**, bao gồm return traffic theo yêu cầu stateless.
- Route/DNS giữa subnet của Pod và mount target hoạt động; DNS VPC phải có khả năng phân giải EFS hostname.

**Đừng mở NFS 2049 tới Internet** hoặc `0.0.0.0/0` chỉ vì Pod báo mount timeout. Hãy xác nhận đích IP, SG được gắn với interface nào và VPC networking của Pod.

### 15.2. Encryption at rest, in transit và KMS

- **EBS:** cấu hình encryption của EBS volume ở StorageClass/volume; customer managed KMS key cần quyền dùng khóa thích hợp. Số lần đọc/ghi file trong Pod không phải mỗi lần đều gọi KMS.
- **EFS at rest:** chọn mã hóa khi tạo filesystem; KMS key và quyền cần được quản lý đúng. Thay đổi mã hóa existing filesystem có giới hạn; kế hoạch migration nếu cần khác với việc chỉ đổi YAML.
- **EFS in transit:** dùng TLS mount theo tùy chọn CSI/driver; nếu cần IAM authorization cho EFS client, cần cấu hình mount option `iam`, access point/file system policy và IAM runtime theo hướng dẫn EFS.
- **POSIX:** `runAsUser`, `runAsGroup`, `fsGroup`, access point POSIX identity, file owner và mode quyết định file có thể được đọc/ghi hay không; mã hóa không thay POSIX permission.

**Tránh một nhầm lẫn:** IAM cho CSI controller **tạo access point** và IAM cho **client mount/access EFS** (nếu filesystem policy bắt buộc) là hai vấn đề khác nhau. Thao tác NFS file còn chịu POSIX ACL/mode chứ không đơn giản là `s3:GetObject`.

### 15.3. Access points để cô lập đường dẫn và người dùng

Một EFS file system có thể được dùng bởi nhiều nhóm. Có thể tạo:

~~~text
File system fs-example:
  Access Point A → /teams/team-a → POSIX uid/gid A
  Access Point B → /teams/team-b → POSIX uid/gid B
~~~

Mỗi PV/PVC được map tới access point riêng. Đây là cách giúp quản lý namespace/permissions, nhưng **không phải ranh giới cách ly hoàn toàn như account hoặc filesystem khác**. Kiểm tra quyền AWS/EFS file system policy và cách truy cập tránh bypass access point ngoài ý muốn.

## 16. Snapshot và phục hồi EBS CSI volumes

Kubernetes cung cấp **VolumeSnapshot**, **VolumeSnapshotClass** và **VolumeSnapshotContent** thông qua CSI snapshot APIs, khi các CRDs/controller cần thiết đã được cài. Với EBS CSI, snapshot backend tương ứng **EBS snapshot**.

### Điều kiện tiên quyết

1. EKS cluster có EBS CSI driver phù hợp.
2. Có **CSI external snapshot controller** và VolumeSnapshot CRDs (qua EKS add-on hoặc cài đặt tương thích).
3. EBS CSI controller có IAM quyền snapshot phù hợp và KMS grant/permission nếu volume mã hóa.
4. PVC nguồn đã tồn tại, workload có phương án nhất quán dữ liệu khi chụp snapshot.

**Nếu chỉ cài EBS CSI add-on mà không có snapshot controller/CRDs, VolumeSnapshot không mặc nhiên hoạt động.**

### VolumeSnapshotClass

File `ebs-snapshot-class.yaml`:

~~~yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshotClass
metadata:
  name: ebs-snapshot-retain
driver: ebs.csi.aws.com
deletionPolicy: Retain
~~~

### Tạo snapshot từ PVC

File `ebs-snapshot.yaml`:

~~~yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: postgres-data-snap
  namespace: default
spec:
  volumeSnapshotClassName: ebs-snapshot-retain
  source:
    persistentVolumeClaimName: postgres-data
~~~

Áp dụng và xem trạng thái:

~~~bash
kubectl apply -f ebs-snapshot-class.yaml
kubectl apply -f ebs-snapshot.yaml

kubectl get volumesnapshot -n default
kubectl describe volumesnapshot postgres-data-snap -n default
kubectl get volumesnapshotcontent
~~~

Đợi `readyToUse: true` theo API/status trước khi dựa vào snapshot như nguồn khôi phục. **`deletionPolicy: Retain`** của VolumeSnapshotClass là chính sách snapshot backend, khác với `reclaimPolicy` của StorageClass/PV.

### Tạo PVC mới từ snapshot

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: restored-data
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: ebs-gp3
  resources:
    requests:
      storage: 20Gi
  dataSource:
    name: postgres-data-snap
    kind: VolumeSnapshot
    apiGroup: snapshot.storage.k8s.io
~~~

PVC khôi phục cần có **dung lượng tối thiểu tương thích** snapshot. Với `WaitForFirstConsumer`, việc tạo EBS volume mới có thể đợi Pod đầu tiên, giúp chọn AZ phù hợp. Restore sang AZ khác trong cùng Region thường có thể thực hiện bằng **volume mới từ snapshot**, chứ không phải “chuyển AZ” của volume EBS cũ.

### Crash consistency khác application consistency

Snapshot EBS chụp dữ liệu block; với database đang ghi, nếu không quiesce ứng dụng hoặc dùng cơ chế backup của database, snapshot có thể chỉ **crash-consistent**. Để phục hồi PostgreSQL/MySQL tốt:

- Dùng database-aware backup, transaction/WAL/binlog và quy trình kiểm tra consistency;
- nếu dữ liệu trải nhiều PVC, cần chiến lược đồng bộ snapshot/application;
- **test restore** trên workload lab độc lập, kiểm tra dữ liệu/query và khởi động ứng dụng;
- đo thời gian từ khi xảy ra sự cố đến lúc phục vụ lại để đánh giá **RTO**, và điểm dữ liệu cuối cùng khôi phục được để đánh giá **RPO**.

**VolumeSnapshot không tự là DR đa Region:** EBS snapshot nằm theo Region, cross-Region cần copy và quy trình phục hồi khác. Với môi trường có yêu cầu phục hồi nghiêm ngặt, kết hợp AWS Backup hoặc chiến lược snapshot/replication phù hợp.

## 17. Backup cho EFS: tách snapshot EBS khỏi bảo vệ file

**EFS không phải EBS**. Không áp dụng nguyên VolumeSnapshotClass EBS vào PVC EFS và kỳ vọng có EBS snapshot cho NFS data.

Đối với EFS, những lựa chọn cần đánh giá:

- **AWS Backup** với lịch, retention và vault phù hợp, hỗ trợ backup/restore EFS theo quy trình AWS.
- **EFS replication** để tạo bản sao dữ liệu theo yêu cầu được hỗ trợ, kết hợp kiểm tra failover/khả năng ghi/khôi phục.
- **Ứng dụng tự tạo version hoặc backup logic** cho dữ liệu file quan trọng, có kiểm thử integrity.
- **S3** nếu dữ liệu thực chất là object; versioning/lifecycle/replication của S3 có mô hình khác EFS.

**EFS Regional khả dụng cao không đồng nghĩa miễn nhiễm với xóa nhầm hay ransomware.** Dữ liệu bị xóa bởi một Pod có quyền ghi có thể ảnh hưởng tất cả Pods cùng mount. Backup tách biệt với runtime permission, quản lý IAM và retention là cần thiết.

### Bảng chọn phương án khôi phục

| Sự cố | Với EBS PVC | Với EFS PVC |
| --- | --- | --- |
| Pod/container chết | Service/StatefulSet tạo Pod khác, reattach EBS cùng AZ | Pod mới mount lại EFS qua network |
| Node EC2 lỗi | Reschedule tới node còn hoạt động **trong AZ có EBS** | Reschedule tới node/AZ có mount target |
| AZ lỗi | Khôi phục volume mới từ snapshot hoặc app replication sang AZ khác | EFS Regional có thể còn hoạt động qua AZ khác; One Zone không tương đương |
| Xóa nhầm file | Snapshot/backup ứng dụng, restore/khôi phục file | AWS Backup hoặc backup file/version phù hợp |
| DB bị corrupt | DB-aware backup, point-in-time recovery nếu thiết kế | Không phải cứ dùng EFS là tránh corruption |
| Mất Region | Cross-Region snapshot copy/DB replication | EFS replication/cross-Region backup theo thiết kế |

## 18. Mở rộng volume và hiệu năng

### 18.1. Tăng dung lượng EBS PVC

Với StorageClass có `allowVolumeExpansion: true`, có thể **tăng** yêu cầu dung lượng PVC:

~~~bash
kubectl patch pvc postgres-data \
  -p '{"spec":{"resources":{"requests":{"storage":"30Gi"}}}}'

kubectl get pvc postgres-data
kubectl describe pvc postgres-data
~~~

Kubernetes/CSI driver sẽ điều phối resize EBS volume và filesystem khi được hỗ trợ. Một số filesystem/phiên bản/runtime cần Pod/node tham gia để hoàn tất; kiểm tra `FileSystemResizePending`, status/conditions và `df -h` trong container. Không kết luận resize xong chỉ vì AWS EBS size đã tăng.

**Không thể thu nhỏ EBS volume trực tiếp** bằng cách patch PVC từ 30Gi xuống 10Gi. Muốn giảm cần tạo PVC/volume mới nhỏ đủ chứa dữ liệu, thực hiện migrate/restore rồi chuyển ứng dụng.

### 18.2. Điều chỉnh IOPS/throughput khác resize capacity

Với gp3, cấp thêm IOPS/throughput là khía cạnh riêng với dung lượng. Có thể chọn khi tạo StorageClass hoặc theo tính năng volume modification hỗ trợ tại driver/version. **Không tự sửa StorageClass và kỳ vọng mọi volume đã cấp theo lớp đó tự thay hiệu năng**.

Trong EKS Auto Mode đủ mới, **VolumeAttributesClass** hỗ trợ điều chỉnh hiệu năng/type theo policy và Kubernetes version. Ví dụ chỉ để minh họa:

~~~yaml
apiVersion: storage.k8s.io/v1
kind: VolumeAttributesClass
metadata:
  name: auto-gp3-6000-250
driverName: ebs.csi.eks.amazonaws.com
parameters:
  type: gp3
  iops: "6000"
  throughput: "250"
~~~

Theo tài liệu AWS Auto Mode, trên Kubernetes phiên bản hỗ trợ (ví dụ 1.34+), PVC có thể tham chiếu VolumeAttributesClass để yêu cầu thay thuộc tính volume. **API và hỗ trợ có thể thay đổi**; kiểm tra trước khi áp dụng, nhất là ở cluster dùng EBS CSI tiêu chuẩn hoặc driver tự quản.

### 18.3. EBS, EFS và giới hạn thực tế

| Khía cạnh | EBS | EFS |
| --- | --- | --- |
| Cách tăng capacity | Tăng EBS volume/PVC theo điều kiện hỗ trợ | Filesystem co giãn theo dữ liệu; PVC request không là quota cứng |
| Bottleneck | IOPS, throughput/latency của volume và EC2 EBS bandwidth | Network, NFS ops, throughput mode, client count, metadata |
| Cần benchmark gì? | I/O size, random/sequential, queue depth, p95/p99 latency | NFS read/write, concurrent clients, metadata operations, throughput, latency |
| Chi phí của performance | gp3 provisioned IOPS/throughput vượt baseline, io2 | EFS throughput/storage classes/IO theo chế độ áp dụng |
| Cách khôi phục khi lỗi | Reattach cùng AZ, snapshot, app replication | Remount, multi-AZ mount targets, backup/replication |

**Không tối ưu bằng cách tăng EBS IOPS nếu Pod bị nghẽn CPU hoặc database lock**. Tương tự, không tăng EFS throughput khi lỗi thật là POSIX `Permission denied` hoặc không đi được TCP 2049.

## 19. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra trọng tâm |
| --- | --- | --- |
| PVC EBS `Pending`, chưa có Pod | `WaitForFirstConsumer` chưa có consumer | Kiểm tra StorageClass; tạo Pod để scheduler quyết định topology |
| PVC EBS `Pending` kéo dài dù có Pod | CSI driver chưa chạy, IAM `UnauthorizedOperation`, quota EBS, không có node phù hợp | `kubectl describe pvc/pod`, CSI controller logs, IAM role và AZ |
| Pod EBS `Pending` khi nodeSelector sang AZ khác | PV đã bound trong AZ cũ, topology conflict | PV `nodeAffinity`, node AZ labels, lập kế hoạch snapshot/restore |
| Pod `ContainerCreating` và `FailedAttachVolume` | EBS đang gắn node khác, lỗi detach/attach, thiếu IAM, volume state | `VolumeAttachment`, node events, EBS `describe-volumes` |
| EBS PVC `Bound` nhưng mount lỗi | CSI node plugin, filesystem/permission, device/format/mount | kubelet/CSI node logs, Pod events, filesystem mode |
| EBS mount vào Fargate không được | EKS Fargate không hỗ trợ EBS mount | Dùng EC2/Auto Mode nodes hoặc đánh giá EFS/S3 |
| EBS StorageClass trên Auto Mode không provision | Dùng sai provisioner `ebs.csi.aws.com` với capability Auto Mode | Dùng `ebs.csi.eks.amazonaws.com`, topology, quyền cluster role |
| EFS PVC dynamic `Pending` | Sai fileSystemId, thiếu `CreateAccessPoint`, IAM, quota AP, driver/controller lỗi | EFS CSI controller logs, PV events, filesystem/account/Region |
| EFS Pod `FailedMount` timeout | TCP 2049 bị SG/NACL/route chặn, mount target thiếu, DNS lỗi | Mount targets mỗi AZ, SG nguồn/đích, resolver, network test |
| EFS mount được nhưng không ghi được | Access point POSIX identity, directoryPerms, fsGroup/runAsUser sai hoặc EFS policy | `id`, `ls -ln`, mount option `iam`, access point |
| Một Pod thấy file, Pod khác không thấy | PVC khác/access points khác, mount path khác hoặc ứng dụng cache | PV `volumeHandle`, AP ID, namespace, path và consistency |
| PVC EFS ghi vượt 5Gi dù request 5Gi | PVC capacity không phải quota EFS filesystem | Thiết kế quota/giám sát theo dịch vụ/ứng dụng |
| HPA scale nhiều Pod nhưng volume EBS không attach | Một PVC RWO không phải shared RWX; nhiều node khác AZ | StatefulSet per-replica volume, EFS RWX hoặc object storage |
| PVC bị xóa rồi EBS biến mất | StorageClass `reclaimPolicy: Delete` | Kiểm tra PV/PVC trước khi xóa, backup/Retain |
| Snapshot tạo không được | Thiếu CSI snapshot controller/CRDs, IAM hoặc snapshot class sai driver | `kubectl get volumesnapshotclass`, logs, quyền EC2 |
| Volume đã expand nhưng filesystem chưa tăng | Chưa hoàn tất node filesystem resize | PVC conditions, `df -h`, CSI logs, Pod restart nếu quy trình đòi |
| EFS latency cao khi qua AZ | Thiếu mount target tại AZ, networking/throughput/caching | AZ placement, EFS CloudWatch metrics, NFS client load |
| Chi phí EBS/EFS tăng | PV/volume không được xóa, EFS dư dữ liệu, snapshot retention/IOPS | Billing, tags, PV reclaim policy, EFS lifecycle, Budget |

### Cách đọc sự cố theo lớp

~~~text
1. kubectl get pod,pvc,pv -A (xác định namespace và object chính xác)
2. kubectl describe pod <pod> -n <ns>
3. kubectl describe pvc <claim> -n <ns>
4. kubectl get sc; kubectl get csidrivers
5. Với EBS: xem driver, StorageClass provisioner, IAM, PV nodeAffinity,
   node AZ, VolumeAttachment, EBS volume state/KMS.
6. Với EFS: xem access point/PV volumeHandle, mount targets, DNS, TCP 2049,
   SG/NACL, POSIX UID/GID, EFS filesystem policy.
7. Đối chiếu AWS CloudTrail + controller/node logs + application logs.
8. Sửa nguyên nhân nhỏ nhất, thử mount/ghi/đọc thật và diễn tập recovery.
~~~

Không dùng `chmod -R 777`, nới SG `0.0.0.0/0`, cấp `AdministratorAccess` cho controller hoặc xóa PV/PVC đang chứa dữ liệu quan trọng chỉ để giải quyết lỗi tạm thời. Những cách này có thể tăng rủi ro mất dữ liệu hoặc mở quyền không cần thiết.

## 20. Thực hành chẩn đoán qua kubectl và AWS CLI

### 20.1. Kiểm tra danh tính cluster và add-ons

~~~bash
aws sts get-caller-identity
aws eks describe-cluster \
  --name storage-lab \
  --region ap-southeast-1 \
  --query 'cluster.{Name:name,Status:status,Version:version}'

kubectl get nodes -L topology.kubernetes.io/zone
kubectl get storageclass
kubectl get csidrivers
kubectl get pods -n kube-system
~~~

**Chú ý:** Nếu kubeconfig trỏ nhầm cluster/account, mọi biểu hiện điều tra sẽ gây hiểu sai. Xác nhận `kubectl config current-context`, namespace và AWS role trước khi thao tác.

### 20.2. Kiểm tra quyền và EBS volume từ PV

~~~bash
kubectl get pvc -A
kubectl get pv -o wide
kubectl describe pv <pv-name-thuc-te>
kubectl get volumeattachments
~~~

Ví dụ kiểm tra một EBS volume đã biết:

~~~bash
aws ec2 describe-volumes \
  --volume-ids vol-0123456789abcdef0 \
  --region ap-southeast-1 \
  --query 'Volumes[0].{AZ:AvailabilityZone,Type:VolumeType,Size:Size,State:State,Encrypted:Encrypted,Attachments:Attachments}'
~~~

Nếu lỗi cross-AZ, so `AvailabilityZone` của volume với `topology.kubernetes.io/zone` trên node được scheduler chọn, cùng PV nodeAffinity/constraints.

### 20.3. Kiểm tra EFS mount targets

~~~bash
aws efs describe-mount-targets \
  --file-system-id fs-0123456789abcdef0 \
  --region ap-southeast-1

aws efs describe-file-systems \
  --file-system-id fs-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Ghi lại mount target subnet/AZ và IP. Kiểm tra inbound SG TCP/2049 từ node/Pod đúng SG. Không có mount target phù hợp thì không thể kết luận chỉ từ một `kubectl get pvc Bound` rằng Pod mount được.

### 20.4. Xem logs CSI

Với EKS add-ons chạy ở `kube-system`, tên deployment/daemonset thực tế có thể khác nhau theo driver version:

~~~bash
kubectl get deploy,ds,pods -n kube-system | grep -E 'ebs|efs|csi'

kubectl logs -n kube-system deployment/ebs-csi-controller \
  --all-containers=true --tail=100
~~~

Lệnh EBS controller trên chỉ dùng khi deployment có đúng tên; kiểm tra từ `kubectl get` trước. Với EFS, tìm deployment/controller và các CSI node pods thực tế. **Không tìm secret/access key trong log và không xuất log chứa thông tin nhạy cảm ra nơi công khai.**

### 20.5. Kiểm tra dữ liệu thật và quyền

~~~bash
kubectl exec efs-writer-a -- sh -c 'id; ls -ln /shared'
kubectl exec efs-writer-a -- sh -c 'echo ok >> /shared/probe.txt'
kubectl exec efs-reader-b -- sh -c 'cat /shared/probe.txt'
~~~

Nếu Pod có quyền ghi vượt dự kiến, điều tra POSIX/access point và Kubernetes RBAC/ServiceAccount để bảo đảm isolation. Nếu chỉ cần một nơi ghi và nơi khác đọc, cân nhắc mount read-only hoặc dùng access point/policy riêng.

### Lưu ý các giá trị mẫu

Trong các lệnh minh họa, chuỗi như `<pv-name-thuc-te>` là **placeholder**, không được chạy nguyên văn trong shell vì `<` có thể bị shell hiểu là ký tự điều khiển chuyển hướng. Thay bằng tên resource thực. Tài nguyên `fs-0123456789abcdef0` và `vol-0123456789abcdef0` là ID minh họa, không phải storage đang tồn tại.

## 21. Giám sát lưu trữ EKS bằng CloudWatch và ứng dụng

### Các tín hiệu nên theo dõi

| Lớp | Chỉ số / sự kiện | Khi nào cảnh báo |
| --- | --- | --- |
| **Kubernetes** | PVC/PV phase, Pod Pending, FailedAttachVolume/FailedMount, VolumeAttachment | PVC không Bound/Pod mount không hoàn tất sau thời gian cho phép |
| **CSI controller** | CreateVolume/CreateAccessPoint lỗi, IAM Deny, rate limit, throttling | Provision/attach/resize/snapshot liên tục lỗi |
| **EBS** | Read/Write IOPS, throughput, queue length, latency/các metric được hỗ trợ | Gần giới hạn, latency p95/p99 tăng, queue dài |
| **EFS** | PercentIOLimit, throughput, client connections, burst/IO metric theo throughput mode | NFS latency/tải tăng, chạm performance limit |
| **EC2 nodes** | EBS bandwidth, ENI/volume attachment limits, CPU/memory và disk inode | Node quá tải, thiếu capacity/attachment |
| **Ứng dụng** | File read/write latency, error code, DB checkpoint/fsync, job retries | SLO người dùng xấu đi dù PVC Bound |
| **AWS CloudTrail** | API tạo/xóa EBS/EFS, thay key policy, IAM | Thay cấu hình bất thường hoặc xóa tài nguyên |
| **AWS Budgets/Cost Explorer** | EBS provisioned, snapshot, EFS storage/throughput/backup | Chi phí vượt ngưỡng theo team/service |

**PVC `Bound` không chứng minh ứng dụng hoạt động tốt**. Một EFS mount có thể bị latency cao, filesystem đầy quota phía ứng dụng hoặc permission sai; một EBS volume có thể đạt IOPS cap. Cần đo từ bên trong Pod, CloudWatch và traces/logs.

### Quản lý chi phí theo storage class

- **EBS gp3:** trả phí **capacity provisioned** ngay cả khi Pod không ghi nhiều; IOPS/throughput vượt baseline có thể tính phí riêng, snapshots tính riêng. PV giữ lại do `Retain` vẫn có thể còn EBS volume đang tính phí.
- **EFS:** dung lượng theo lượng file lưu thực, throughput/storage class/tier theo cấu hình và API; truy cập nhiều file nhỏ/metadata có tác động hiệu năng/chi phí khác workload streaming lớn.
- **Cross-AZ traffic:** EBS là tài nguyên cùng AZ với node; EFS giao tiếp NFS qua network, nên cần xem mount target placement và transfer pricing.
- **Data lifecycle:** Xóa PVC không nhất thiết xóa underlying dữ liệu; kiểm kê **orphaned volumes, access points, snapshots** và backup retention trước khi dọn.
- **KMS:** customer managed key có phí/quyền riêng; mã hóa không thay chính sách backup.

Tính tổng bằng **AWS Pricing Calculator**, **AWS Cost Explorer** và **AWS Budgets** theo Region, gắn tags/k8s labels thống nhất tới AWS resources trong khả năng CSI driver/capability hỗ trợ.

## 22. Bốn tình huống chọn storage

### Tình huống A — PostgreSQL tự quản trên EKS

**Yêu cầu:** Dữ liệu giao dịch, random I/O, latency thấp, Pod có thể restart; cần sao lưu và khả dụng qua AZ.

**Đánh giá:**

- Bắt đầu với **EBS gp3/io2** trên EC2 nodes theo benchmark IOPS/latency; mỗi replica/stateful Pod có PVC riêng.
- Dùng **StatefulSet/operator database** cho danh tính/replication/quorum, không mount một PVC RWO vào nhiều DB primary replicas.
- Thiết kế **WAL/backup/point-in-time restore**, snapshots crash consistency và failure test.
- Khi AZ A mất, không thể attach EBS AZ A vào node AZ B; phải **failover sang replica có volume riêng ở AZ B** hoặc restore volume mới từ snapshot.
- Nếu nhóm muốn giảm quản trị DB, khảo sát **Amazon RDS/Aurora Multi-AZ**, có đặc tính HA/backup được quản lý.

**Không chọn EFS chỉ vì RWX** để chạy nhiều PostgreSQL primaries trên chung một thư mục; điều đó có thể hủy dữ liệu.

### Tình huống B — Ứng dụng web Java có file uploads dùng chung

**Yêu cầu:** 4 replicas ở nhiều AZ, mỗi replica cần đọc file do replica khác ghi.

**Đánh giá:**

- Nếu ứng dụng cần **POSIX filesystem** với thao tác file/path, chọn **EFS Regional + RWX PVC**, access point và POSIX permissions phù hợp.
- Có mount targets nhiều AZ, TCP/2049, TLS và backup EFS.
- Nếu upload là ảnh/tài liệu/object tĩnh, đánh giá lại API/storage design và ưu tiên **S3** để tránh shared NFS và đơn giản hóa scaling.

### Tình huống C — Batch job xử lý dữ liệu lớn, có thể chạy lại

**Yêu cầu:** Nhiều Pods xử lý input từ S3, tạo file tạm rồi ghi kết quả về S3.

**Đánh giá:**

- Dùng `emptyDir`/ephemeral storage nếu dữ liệu trung gian có thể tái tạo; không cần mua EBS/EFS bền vững.
- Nếu Pod cần block I/O lớn, dùng EBS gp3 và PVC riêng, đo thời gian attach/provision và dọn storage.
- Hạn chế RWX EFS cho scratch tần suất ghi lớn nếu không có nhu cầu chia sẻ thật.

### Tình huống D — EKS Fargate service cần chia sẻ cấu hình/tệp

**Yêu cầu:** Team chọn Fargate để ít vận hành node; service cần đọc/ghi một số file chung.

**Đánh giá:**

- **Không thể dùng EBS PV trực tiếp cho Fargate Pod**.
- Dùng **EFS static PV/PVC** khi cần NFS, với access point, mount targets và SG chính xác.
- Nếu cần dynamic EFS access points từng PVC trên Fargate, phải thiết kế cơ chế **provision trước/ngoài Fargate** hoặc đổi compute sang EC2 nodes phù hợp; không giả định dynamic provisioning qua EFS CSI trên Fargate được hỗ trợ.
- Kiểm tra POSIX, TLS, IAM, latency và tổng chi phí của filesystem.

## 23. Checklist triển khai production

- [ ] Đã phân biệt **emptyDir**, **PV/PVC**, **StorageClass**, **CSI driver** và storage backend.
- [ ] Chọn EBS/EFS/S3/DB managed dựa trên access pattern, latency, RWX requirement, bền vững và tổng chi phí.
- [ ] Xác định loại compute **EC2 nodes, EKS Auto Mode hoặc Fargate** và provisioner/storage hỗ trợ tương ứng.
- [ ] EBS CSI tiêu chuẩn dùng `ebs.csi.aws.com`; EKS Auto Mode block dùng `ebs.csi.eks.amazonaws.com`, không đổi driver tùy tiện.
- [ ] Với EBS, StorageClass có `WaitForFirstConsumer`, đúng volume type, encryption, expansion và reclaim policy.
- [ ] Với EBS/PVC đã bind, node/pod placement đúng AZ; có kế hoạch di chuyển/restore khi mất AZ.
- [ ] Với EFS, file system/access point thật tồn tại, mount targets ở AZ phù hợp và network TCP/2049 được giới hạn đúng SG.
- [ ] EFS dynamic/static provisioning phù hợp workload; **Fargate EFS dùng static**, **Fargate không gắn EBS**.
- [ ] PVC access modes RWO/RWOP/RWX được hiểu đúng, có kiểm soát concurrency/locking ở cấp ứng dụng.
- [ ] IAM controller role qua Pod Identity/IRSA hoặc quyền Auto Mode tương ứng, KMS key policy/grants được kiểm tra.
- [ ] EBS at rest và EFS at rest/in transit có encryption phù hợp, không nhầm với quyền POSIX/application.
- [ ] Có snapshot controller/VolumeSnapshotClass khi cần EBS CSI snapshot, cùng quyền snapshot/restore.
- [ ] Có AWS Backup hoặc phương án bảo vệ EFS, database-aware backup, replication và diễn tập RTO/RPO.
- [ ] Có metric/alert PVC Pending, FailedMount, IOPS/throughput/latency, file system permissions và chi phí.
- [ ] Có kế hoạch resize EBS PVC (chỉ tăng), performance modification đúng driver/version và rollback.
- [ ] Kịch bản xóa Pod/StatefulSet/PVC/PV được review; không xóa dữ liệu production chỉ vì cleanup lab.
- [ ] Đã thử ứng dụng phục hồi khi Pod/node/AZ lỗi, kể cả restore dữ liệu và kết nối backend/DB.
- [ ] Tags, quotas, snapshots, orphaned PV/EBS/EFS access points và AWS Budgets được quản lý.

## 24. Bài tập và câu hỏi tự kiểm tra

### Bài tập 1 — EBS PVC qua hai AZ

**Đề bài:** EKS có nodes AZ A/B. StorageClass EBS đang dùng `volumeBindingMode: Immediate`; một PVC được cấp EBS ở AZ A. Pod có `nodeSelector` AZ B và `FailedAttachVolume`/Pending.

Hãy:

1. Giải thích vì sao EBS volume không thể attach vào EC2 node ở AZ B.
2. Đổi thiết kế **cho PVC mới** sang `WaitForFirstConsumer`.
3. Với PVC đã có dữ liệu, vạch kế hoạch snapshot/restore thành volume mới AZ B thay vì sửa PV nodeAffinity.
4. Thiết kế một bài thử phục hồi khi AZ A gặp sự cố, bao gồm RTO/RPO.

### Bài tập 2 — EFS RWX nhưng một Pod không ghi được

**Đề bài:** Hai Pods cùng mount PVC EFS `ReadWriteMany`; Pod A ghi thành công nhưng Pod B báo `Permission denied`.

Kiểm tra: `kubectl describe`, access point IDs, `runAsUser`, `runAsGroup`, `fsGroup`, file owner/mode, `directoryPerms`, EFS file system policy. Vì sao **RWX** không tự có nghĩa người dùng Linux của mọi Pod đều có quyền ghi mọi file?

### Bài tập 3 — CSI snapshot và backup database

**Đề bài:** PostgreSQL StatefulSet có hai PVC dữ liệu EBS và WAL, mục tiêu RPO 5 phút, RTO 30 phút.

Hãy mô tả:

- Các tài nguyên snapshot CRDs/controller cần cài.
- Cách có điểm khôi phục nhất quán giữa database files và WAL.
- Vì sao snapshot mỗi 12 giờ không đáp ứng RPO 5 phút.
- Cách tự động hóa backup/restore và kiểm tra startup tại AZ khác.
- Khi nào RDS/Aurora Multi-AZ là phương án ít vận hành hơn.

### Bài tập 4 — EKS Auto Mode migration

**Đề bài:** Cluster đang có PVC trên `ebs.csi.aws.com` và muốn chuyển sang EKS Auto Mode `ebs.csi.eks.amazonaws.com`.

Hãy nêu vì sao không nên sửa nguyên provisioner trên StorageClass hiện có; thiết kế luồng inventory PVC/PV, snapshot/restore, kiểm tra StorageClass Auto Mode, `allowedTopologies`, KMS, application downtime và xác minh dữ liệu sau migration.

### Bài tập 5 — Phân tích chi phí

Một workload dùng:

- 20 EBS gp3 volumes, mỗi volume 100 GiB, một số cần thêm IOPS/throughput.
- Một EFS Regional file system chứa 300 GiB dữ liệu dùng chung.
- EBS snapshots định kỳ và AWS Backup cho EFS.

Hãy lập bảng ước lượng chi phí theo Region: capacity/IOPS/throughput provisioned, snapshots, EFS tier/throughput, backup retention, KMS, cross-AZ transfer và logging. Đề xuất cách đo để tránh trả phí cho orphaned volumes và dữ liệu EFS không còn dùng.

### Câu hỏi ngắn

1. **PVC khác PV thế nào?** PVC là yêu cầu storage của ứng dụng; PV đại diện tài nguyên lưu trữ đã cấp/bind.
2. **EBS CSI driver tiêu chuẩn có provisioner gì?** `ebs.csi.aws.com`; EKS Auto Mode dùng `ebs.csi.eks.amazonaws.com`.
3. **Một EBS volume gắn trực tiếp vào hai nodes ở hai AZ được không?** Không; EBS volume gắn với một AZ. EBS Multi-Attach là khả năng chuyên biệt cùng AZ, không biến EBS CSI thành NFS thông thường.
4. **RWO có nghĩa đúng một Pod dùng không?** Không nhất thiết; RWO giới hạn ở mức một node. RWOP dành cho một Pod khi được hỗ trợ.
5. **EFS RWX có tự tránh race condition không?** Không. Ứng dụng cần locking/consistency và POSIX permissions đúng.
6. **EKS Fargate Pod có gắn EBS PV không?** Không.
7. **Fargate có dùng dynamic EFS access point PVC được không?** Không theo EFS CSI dynamic provisioning trên Fargate; dùng static PV.
8. **Đổi StorageClass `reclaimPolicy` có sửa trực tiếp reclaim của PV cũ không?** Không nên giả định; PV đã provision có reclaim policy riêng cần xem.
9. **EBS VolumeSnapshot có mặc nhiên là backup application-consistent không?** Không; cần DB-aware/quiesce và restore test.
10. **PVC EFS request 5Gi có chặn ghi file thứ 6 GiB không?** Không theo mặc định; EFS co giãn, PVC capacity không là quota cứng.

## 25. Tổng kết

Với Kubernetes trên EKS, **PV/PVC/StorageClass** giúp ứng dụng yêu cầu storage bằng API Kubernetes, còn **CSI driver** kết nối yêu cầu này tới AWS storage backend.

- **EBS CSI** phù hợp block storage bền vững, random I/O và StatefulSet có volume riêng; cần xử lý **AZ topology**, IAM, snapshot, resize và node failure.
- **EFS CSI** phù hợp shared NFS file cho nhiều Pods/nodes/AZ, cần quản lý **mount targets, TCP/2049, IAM/POSIX, TLS, access points** và backup.
- **EKS Auto Mode và EKS Fargate** có khả năng hỗ trợ riêng; **không thể tráo lẫn provisioners** hoặc suy luận Fargate dùng EBS như EC2 nodes.

Thiết kế storage đúng cần kết hợp **Region/AZ, IAM/KMS, VPC, ứng dụng Java/database, khả năng phục hồi, giám sát và ngân sách**. Một PVC `Bound` chỉ cho biết binding ở cấp Kubernetes; điều quan trọng hơn là **dữ liệu nhất quán, đọc/ghi đáp ứng SLO, có thể phục hồi và không bị lộ hoặc mất vì policy/lifecycle sai**.

### Tài liệu chính thức để đối chiếu

- [Amazon EKS – Use application data storage for your cluster](https://docs.aws.amazon.com/eks/latest/userguide/storage.html)
- [Use Kubernetes volume storage with Amazon EBS](https://docs.aws.amazon.com/eks/latest/userguide/ebs-csi.html)
- [Use elastic file system storage with Amazon EFS](https://docs.aws.amazon.com/eks/latest/userguide/efs-csi.html)
- [Amazon EKS Auto Mode – Create a storage class](https://docs.aws.amazon.com/eks/latest/userguide/create-storage-class.html)
- [Amazon EKS Auto Mode – Sample stateful workload](https://docs.aws.amazon.com/eks/latest/userguide/sample-storage-workload.html)
- [Amazon EKS Fargate storage considerations](https://docs.aws.amazon.com/eks/latest/userguide/fargate-pod-configuration.html)
- [Enable snapshot functionality for CSI volumes](https://docs.aws.amazon.com/eks/latest/userguide/csi-snapshot-controller.html)
- [Kubernetes Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [Kubernetes Storage Classes](https://kubernetes.io/docs/concepts/storage/storage-classes/)
- [Kubernetes Volume Snapshots](https://kubernetes.io/docs/concepts/storage/volume-snapshots/)
- [Amazon EBS volume types](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html)
- [Amazon EFS User Guide](https://docs.aws.amazon.com/efs/latest/ug/)
- [Amazon EBS pricing](https://aws.amazon.com/ebs/pricing/) và [Amazon EFS pricing](https://aws.amazon.com/efs/pricing/)

**Trước khi triển khai production:** kiểm tra khả năng hỗ trợ theo **cluster Kubernetes version, EKS platform, node type, CSI driver version, Region và IAM setup**, đo hiệu năng, thử backup/restore và xác nhận mô hình chi phí với tài khoản thực tế.
