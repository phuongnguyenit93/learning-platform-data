# Nâng cấp nền tảng, thay thế node và khả năng di chuyển workload

## 1. Vì sao cần thiết kế khả năng nâng cấp và di chuyển?

Nền tảng container không đứng yên sau khi triển khai. Kubernetes hoặc container platform cần được cập nhật; worker node cần thay khi hệ điều hành hết vòng đời, có bản vá, cần đổi loại máy hoặc gặp lỗi; workload có thể phải chuyển sang node pool, Availability Zone (AZ), region hoặc cluster khác. Các thao tác này tác động tới **tính sẵn sàng, dữ liệu, bảo mật, hiệu năng, chi phí và vận hành**.

Trong module **CLOUD_ARCHITECTURE**, kiến trúc được thiết kế từ yêu cầu nghiệp vụ đến mạng, compute, dữ liệu và mô hình triển khai, sau đó đánh giá theo tư duy **Well-Architected**. Một nền tảng container tốt cần trả lời cả cách chạy ứng dụng lẫn cách cập nhật hạ tầng mà không làm mất dữ liệu hay phá vỡ dịch vụ.

Sau bài này, bạn có thể phân biệt nâng cấp control plane, thay node và di chuyển workload; lập compatibility matrix; hiểu cordon, drain, eviction và PodDisruptionBudget (PDB); xử lý workload stateful; chọn rolling, surge, blue-green hoặc canary; và xây dựng kế hoạch rollback có bằng chứng.

## 2. Phân biệt ba loại thay đổi

| Thay đổi | Thành phần chính | Mục tiêu | Rủi ro tiêu biểu |
|---|---|---|---|
| **Nâng cấp nền tảng** | API server, scheduler, controller, etcd hoặc managed control plane | Bản vá, tính năng, phiên bản được hỗ trợ | API bị loại bỏ, version skew, CRD/controller không tương thích |
| **Thay thế node** | Worker VM, node pool, OS image, kubelet, runtime, kernel | Thay node cũ, cập nhật image hoặc compute | Thiếu capacity, Pod không drain/schedule được, local state mất |
| **Di chuyển workload** | Deployment, StatefulSet, Job, service, volume, secret, network, traffic | Chuyển ứng dụng sang pool/cluster/zone/region khác | Mất dữ liệu, split-brain, sai DNS/traffic, thiếu dependency hoặc quyền |

Ba việc có liên quan nhưng không đồng nghĩa. Nâng control plane không tự thay hết node; thay node không đảm bảo workload tương thích với phiên bản mới; tạo cluster mới không tự chuyển PVC, secret, certificate, DNS hay dữ liệu.

### 2.1. Bối cảnh minh họa

BookingCloud chạy trên Kubernetes với API stateless nhiều replica, worker bất đồng bộ, PostgreSQL managed bên ngoài cluster, ingress/load balancer HTTPS và một số PVC cho workload stateful. Database nghiệp vụ không lưu trên worker node.

| Yêu cầu giả định | Hệ quả thiết kế |
|---|---|
| API cốt lõi có mục tiêu availability 99,9%/tháng | Drain và rollout không làm mất toàn bộ replica |
| Mất một node không làm mất booking đã commit | Dữ liệu nghiệp vụ phải nằm trong storage bền vững |
| Worker có thể chuyển sang node pool mới | Image, config, identity, queue và checkpoint không phụ thuộc node cũ |
| Có thể khôi phục khi nâng cấp thất bại | Backup, runbook và recovery path được thử trước |
| Đội vận hành nhỏ | Tự động hóa, thay đổi từng bước, giám sát và owner rõ ràng |

Các mục tiêu trên là giả định cho bài học, không phải SLA thực tế. RTO/RPO phải được xác định theo phạm vi sự cố và đo bằng diễn tập.

## 3. Kiểm tra tương thích trước khi nâng cấp

Một cluster là tập hợp nhiều thành phần có quan hệ tương thích. Kiểm tra **phiên bản hiện tại, phiên bản đích, thứ tự nâng và version skew** theo tài liệu của provider hoặc nền tảng đang dùng.

| Thành phần | Câu hỏi cần xác minh |
|---|---|
| Control plane | Phiên bản đích và đường nâng cấp có được hỗ trợ không? |
| Worker/kubelet | Phiên bản kubelet có nằm trong chính sách version skew so với API server không? |
| Runtime | Container runtime/CRI có tương thích OS, kernel và kubelet mới không? |
| CNI | Network plugin, IPAM, NetworkPolicy, eBPF và dataplane có tương thích không? |
| CSI | Storage driver hỗ trợ attach/mount, snapshot, expansion và topology mới không? |
| Ingress/controller | Manifest có dùng API đã deprecated/removed không? |
| CRD/operator | Schema, served/storage version, conversion webhook và controller version có tương thích không? |
| Service mesh | Sidecar, proxy, certificate rotation và policy có hoạt động không? |
| Security/observability agent | DaemonSet, kernel/eBPF, runtime security và log pipeline có hỗ trợ OS mới không? |
| Helm/IaC | Chart, provider plugin, schema và automation có thay đổi không? |

### 3.1. API deprecation và CRD

Trước khi nâng Kubernetes minor version:

1. Liệt kê API version đang được workload, Helm chart, operator và automation sử dụng.
2. Kiểm tra API deprecated hoặc bị loại bỏ trong phiên bản đích.
3. Sửa manifest sang API còn được hỗ trợ và kiểm tra schema bằng server-side dry-run hoặc công cụ tương ứng.
4. Kiểm tra CRD: phiên bản served, storage, conversion webhook và dữ liệu custom resource đang lưu.
5. Nâng controller/operator theo thứ tự tương thích được dự án/provider hỗ trợ.
6. Theo dõi deprecation warning trước maintenance window.

Đổi manifest không tự động chuyển dữ liệu custom resource đã lưu. Nếu CRD dùng conversion webhook, phải xác nhận webhook và dữ liệu được đọc/ghi đúng qua các phiên bản.

### 3.2. OS, architecture và node agent

Kiểm tra OS image, kernel, CPU architecture (x86_64/ARM), runtime, instance type, disk/network, accelerator, labels, taints, zone và security profile. Image ứng dụng phải hỗ trợ architecture của pool mới. Workload GPU cần driver/device plugin tương thích; nếu thiếu, Pod có thể Pending dù CPU/RAM còn.

## 4. Nâng cấp nền tảng theo từng lớp

Quy trình chính xác phụ thuộc Kubernetes managed hay self-managed. Managed control plane thường do provider điều phối và có giới hạn version skew riêng. Self-managed cần quản trị API server, etcd, quorum, backup và từng control-plane component. Không áp dụng một thứ tự chung khi chưa kiểm tra tài liệu của nền tảng.

~~~mermaid
flowchart TD
    A["Inventory phiên bản và dependency"] --> B["Kiểm tra deprecation / compatibility"]
    B --> C["Backup và diễn tập restore"]
    C --> D["Nâng control plane theo supported path"]
    D --> E["Kiểm tra API, CRD, webhook, CNI/CSI"]
    E --> F["Tạo node pool phiên bản mới"]
    F --> G["Di chuyển workload theo nhóm"]
    G --> H["Soak test và theo dõi SLO"]
    H --> I{"Đạt tiêu chí?"}
    I -->|"Không"| R["Dừng rollout / recovery theo runbook"]
    I -->|"Có"| J["Gỡ pool cũ có kiểm soát"]
~~~

Trước khi triển khai, ghi rõ phiên bản control plane và node trước/sau; version skew được phép; node pool cũ có thể tạm chạy sau khi control plane đổi hay không; provider có hỗ trợ surge upgrade hoặc blue-green node pool không; thời điểm nâng CNI/CSI/ingress/operator/service mesh; và recovery nếu downgrade không được hỗ trợ.

Sau từng bước cần kiểm tra API discovery, node readiness, controller reconcile, webhook, CRD, network/DNS, ingress, PVC mount, IAM/workload identity và observability. Không chờ đến cuối mới chạy smoke test.

## 5. Thay node bằng node pool mới

Thay node theo hướng **tạo pool mới → kiểm tra → chuyển tải → drain pool cũ → xóa pool cũ** giúp tách rủi ro OS/runtime khỏi node đang chạy workload.

~~~mermaid
flowchart TB
    subgraph OLD["Blue: pool cũ"]
      O1["Node old-1"]
      O2["Node old-2"]
    end
    subgraph NEW["Green: pool mới"]
      N1["Node new-1"]
      N2["Node new-2"]
    end
    S["Scheduler"] --> N1
    S --> N2
    N1 --> W["Workloads"]
    N2 --> W
    N1 --> CHECK["Health / metrics / soak test"]
    N2 --> CHECK
    CHECK -->|"Đạt tiêu chí"| DRAIN["Cordon + drain pool cũ"]
    DRAIN --> O1
    DRAIN --> O2
~~~

Các bước:

1. Tạo pool mới bằng IaC/managed node group với OS image, kubelet, runtime, labels, taints, security group và IAM đã được xác nhận.
2. Xác minh node Ready, CNI/CSI/daemon agent hoạt động, pull được image và mount được volume cần thiết.
3. Kiểm tra quota VM, subnet IP, Pod IP, CPU/RAM, ephemeral storage và headroom cho surge.
4. Đảm bảo affinity, taint, topology spread và node selector cho phép workload chạy ở pool mới.
5. Chuyển một nhóm workload ít rủi ro; quan sát readiness, errors, latency, restart và resource pressure.
6. Cordon node cũ để scheduler không đặt Pod mới lên đó.
7. Drain từng node theo batch nhỏ và PDB; xác minh Pod replacement healthy.
8. Giữ pool mới qua soak period đủ đại diện cho tải.
9. Xóa pool cũ sau khi xác nhận không còn Pod, volume attachment hay dependency.

### 5.1. Rolling, surge và autoscaling

Rolling thay từng node hoặc một tỷ lệ nhỏ. Surge tạo thêm node mới trước khi loại node cũ. Cả hai cần tính surge capacity, max unavailable, tương tác với cluster autoscaler, quota và subnet IP, topology của Pod/volume, và chi phí tạm thời khi hai pool chạy song song.

### 5.2. Cordon, drain, eviction và PDB

- **Cordon** đánh dấu node không nhận Pod mới qua scheduler.
- **Drain** yêu cầu di dời Pod qua eviction API; một số Pod hoặc loại resource có quy tắc xử lý riêng.
- **Graceful termination** cho process thời gian dừng: xử lý SIGTERM, preStop, ngừng nhận traffic/task và đóng kết nối an toàn.
- **PodDisruptionBudget (PDB)** giới hạn voluntary disruption qua eviction API theo budget được cấu hình.

PDB không bảo vệ khỏi node chết đột ngột, kernel panic, mất zone hay mọi force delete. PDB không tự tạo replica và không chứng minh ứng dụng khỏe nếu readiness probe sai.

Ví dụ PDB có minAvailable bằng 2 chỉ cho phép eviction khi còn đủ Pod healthy theo cách Kubernetes tính. Nếu Deployment có hai replica nhưng một replica đã NotReady, drain có thể bị chặn. Kiểm tra replica, readiness, topology và PDB trước bảo trì; không sửa PDB chỉ để ép drain khi chưa chấp nhận rõ rủi ro.

Lệnh minh họa, thay node và namespace theo cluster:

~~~bash
kubectl get nodes -o wide
kubectl get pods -A -o wide
kubectl get pdb -A
kubectl describe pdb -n booking booking-api

# Không cho scheduler đặt Pod mới lên node này
kubectl cordon worker-old-01

# Evict Pod theo chính sách; kiểm tra PDB và DaemonSet trước
kubectl drain worker-old-01 --ignore-daemonsets --delete-emptydir-data

# Xác minh Pod đã chuyển và node không còn workload cần giữ
kubectl get pods -A -o wide
~~~

Tham số delete-emptydir-data đồng nghĩa dữ liệu emptyDir của Pod bị xóa khi Pod rời node. Chỉ dùng khi dữ liệu là tạm thời hoặc đã được lưu an toàn. Drain có thể bị PDB từ chối; không tự thêm cờ force/disable-eviction để vượt qua khi chưa hiểu tác động.

## 6. Stateful workload: storage, identity và quorum

Di chuyển Deployment stateless thường dễ hơn StatefulSet hoặc database vì Pod có thể tạo lại từ image, config và nguồn dữ liệu bên ngoài. Stateful workload giữ định danh, volume và consistency constraints.

### 6.1. Persistent volume và topology

PV/PVC có thể bị ràng buộc với Availability Zone. Disk ở zone A không thể mặc định attach vào node zone B nếu storage driver không hỗ trợ. Kiểm tra StorageClass, CSI driver, volume topology, access mode, attach limit, snapshot/resize, detach/re-attach sau node crash, quyền dùng encryption key và khả năng restore snapshot sang zone/region khác.

Không xóa node/cluster cũ nếu volume còn attachment, snapshot hoặc finalizer.

### 6.2. StatefulSet, leader và quorum

StatefulSet giữ ordinal, network identity và PVC theo quy tắc riêng. Khi di chuyển, giữ đúng thứ tự bootstrap/join; tránh hai instance cùng identity; xác định quorum/leader; kiểm tra replication lag và consistency; chỉ xóa member cũ khi member mới đã join và cluster healthy.

Với etcd, Kafka, database tự quản lý hoặc distributed cache, tạo Pod mới mà không theo quy trình membership có thể gây split-brain hoặc mất quorum. Cân nhắc managed service hoặc tách state ra khỏi cluster nếu phù hợp.

### 6.3. Phân loại local state

| Loại dữ liệu | Xử lý trước drain |
|---|---|
| Cache có thể tái tạo | Chấp nhận xóa, có warm-up và rate limit |
| File tạm của request | Chờ hoàn tất hoặc retry an toàn |
| Checkpoint/batch progress | Đồng bộ storage bền vững và xác minh checksum/trạng thái |
| Session người dùng | Externalize sang session store hoặc dùng stateless session phù hợp |
| Dữ liệu nghiệp vụ duy nhất | Không lưu local; ghi vào DB/object storage bền vững |

emptyDir, writable container layer và local ephemeral disk có thể mất khi Pod/node bị thay. Không để dữ liệu duy nhất hoặc checkpoint cần khôi phục ở đó.

## 7. Di chuyển workload giữa node pool hoặc cluster

### 7.1. Điều kiện để workload portable

Image nằm ở registry cluster đích truy cập được và hỗ trợ CPU architecture phù hợp; config/secret được quản lý ngoài node; IAM/workload identity được thiết lập cho môi trường đích; network policy/DNS/egress được tạo bằng IaC; dữ liệu nằm ở DB/object storage có thể truy cập; PVC có chiến lược snapshot/replication; admission policy, CRD, ingress, service mesh, security agent và observability tương thích; autoscaling/affinity/topology không khóa workload vào pool cũ.

### 7.2. Chuyển node pool so với chuyển cluster

| Khía cạnh | Đổi node pool trong cluster | Chuyển sang cluster khác |
|---|---|---|
| Control plane/API | Giữ nguyên | Có thể khác version và CRD |
| Network/service discovery | Service DNS thường giữ nguyên | CIDR, DNS, peering, ingress và endpoint có thể đổi |
| Identity | Có thể giữ config trong cluster | Phải thiết lập trust/role cho cluster đích |
| Config/secret | Object có thể giữ nguyên | Cần đồng bộ từ source of truth |
| Storage | PVC có thể giữ nếu topology/driver cho phép | Có thể cần snapshot/replication/restore |
| Traffic | Service endpoints cập nhật khi Pod Ready | Cần routing/cutover, DNS hoặc gateway |
| Rollback | Có thể schedule về pool cũ | Có thể cần chuyển traffic và dữ liệu ngược lại |

Cluster mới không tự kế thừa RBAC, network policy, CRD, admission controller, secret, certificate, storage class, ingress và observability. Tạo và kiểm tra các dependency đó trước khi chuyển workload.

### 7.3. Quy trình migrate sang cluster mới

~~~mermaid
flowchart TD
    S["Inventory workload + dependency"] --> T["Provision cluster đích bằng IaC"]
    T --> V["Cài CNI/CSI/ingress/CRD/observability/security"]
    V --> D["Kiểm tra DNS, IAM, secret, storage và connectivity"]
    D --> P["Deploy workload đích chưa nhận traffic chính"]
    P --> H["Smoke test / synthetic test / data validation"]
    H --> C{"Sẵn sàng cutover?"}
    C -->|"Chưa"| F["Sửa cấu hình hoặc hủy đợt migrate"]
    F --> P
    C -->|"Có"| M["Chuyển traffic theo đợt"]
    M --> O["Theo dõi SLO, lỗi, dữ liệu và backlog"]
    O --> R{"Đạt ngưỡng?"}
    R -->|"Không"| RB["Rollback traffic theo runbook"]
    R -->|"Có"| X["Soak period, gỡ cluster cũ có kiểm soát"]
~~~

Các chiến lược cutover:

- **Recreate:** tạo ở đích, dừng nguồn rồi chuyển traffic; đơn giản nhưng có downtime.
- **Rolling:** chuyển từng replica/node; cần hai phía tương thích và có thể dùng chung data source.
- **Blue-green:** dựng môi trường đích hoàn chỉnh rồi đổi traffic; cần capacity chạy song song và kế hoạch dữ liệu.
- **Canary/weighted routing:** chuyển một phần traffic trước, tăng dần theo metric; cần xử lý session và write consistency.
- **Active-active:** hai phía cùng nhận request; phải thiết kế quyền ghi, đồng bộ dữ liệu, deduplication và conflict resolution. Không mặc định đây là lựa chọn an toàn cho DB nghiệp vụ.

### 7.4. Database và cutover dữ liệu

Nếu cluster cũ/mới cùng dùng managed database, xác minh schema tương thích cả hai phiên bản ứng dụng; network path, IAM, DNS, TLS và connection pool hoạt động ở cluster mới; CronJob/consumer không chạy hai lần; migration schema không phá vỡ rollback.

Nếu database cũng chuyển, quy trình có thể gồm snapshot/restore, logical replication, initial copy + incremental sync, freeze writes, validate count/checksum và đổi writer. Xác định thời điểm **nguồn dữ liệu có thẩm quyền** chuyển từ cũ sang mới. Tránh để hai cluster cùng ghi độc lập nếu chưa thiết kế multi-writer và xử lý xung đột.

## 8. Rollback và phục hồi

Không phải mọi platform upgrade đều hỗ trợ downgrade. Sau khi thay stored API object, etcd schema hoặc dữ liệu CRD, quay control plane về bản cũ có thể không được hỗ trợ. Recovery có thể gồm dừng rollout; giữ pool cũ nếu còn tương thích; chuyển traffic/workload về nguồn; restore dữ liệu nếu migration đã thay đổi state; tạo cluster mới theo phiên bản ổn định rồi restore/migrate; hoặc forward fix khi schema/data đã qua migration một chiều.

### 8.1. Tài sản cần backup

| Tài sản | Biện pháp bảo vệ |
|---|---|
| Manifest/IaC/Helm | Version control, review, artifact pin version |
| Cluster object và CRD | Công cụ backup được hỗ trợ; dump YAML không thay thế backup etcd |
| etcd self-managed | Snapshot theo tài liệu, mã hóa, lưu ngoài failure domain và thử restore |
| Database nghiệp vụ | Backup/PITR, restore test, kiểm tra quyền key |
| Persistent volume | Snapshot/replication theo CSI/storage provider, kiểm tra consistency |
| Secret/key | Secret manager/KMS/HSM và quy trình recovery; không dump vào repository |
| DNS/Ingress/Certificate | IaC/inventory, certificate automation, owner và rollback record |

Backup chưa từng restore thử không phải bằng chứng phục hồi. Diễn tập restore trong môi trường tách biệt và xác minh dữ liệu cùng ứng dụng hoạt động thật.

### 8.2. Tiêu chí go/no-go

| Tiêu chí | Go | No-go |
|---|---|---|
| Node readiness | Pool đích Ready, agent khỏe | Node NotReady, CNI/CSI lỗi |
| API health | Error rate/p95 trong ngưỡng | Regression vượt ngưỡng hoặc kéo dài |
| Disruption | Không vượt budget, PDB/quorum được giữ | Thiếu replica hoặc mất quorum |
| Data | Booking consistency, volume và queue state hợp lệ | Duplicate/lost data hoặc replication lag vượt giới hạn |
| Security | RBAC, IAM, network policy, secret access đạt | Thiếu quyền hoặc đường truy cập không bảo vệ |
| Operations | Dashboard, alert, runbook, on-call sẵn sàng | Không quan sát được hoặc không có owner |

Khi xuất hiện điều kiện no-go, dừng rollout theo runbook; không tiếp tục chỉ vì phần lớn công việc đã hoàn thành.

## 9. Vận hành theo change window

**Trước thay đổi:** xác nhận owner/approver/on-call; pin image/chart/plugin/version; chạy compatibility scan và IaC plan; review resource replacement/destruction; xác minh backup, restore, quota và surge capacity; kiểm tra replica, PDB, readiness/liveness, termination grace, preStop, topology spread và stateful dependency; điều phối CronJob/consumer tránh chạy trùng.

**Trong triển khai:** làm theo batch nhỏ; quan sát scheduler events, Pod Pending, eviction failures, volume attach, CNI errors và node pressure; theo dõi SLI đầu cuối chứ không chỉ CPU node; bảo đảm IaC desired state không tạo lại pool cũ; ghi log mọi bước chuyển.

**Sau triển khai:** chạy soak test đại diện peak/steady load; synthetic business transaction; đối chiếu error rate, latency, restarts, saturation, cost và event backlog; xác nhận backup/restore; chỉ xóa pool/cluster cũ sau khi không còn dependency và hết thời gian giữ an toàn; cập nhật sơ đồ, inventory, ADR và runbook.

## 10. Ví dụ node rotation cho BookingCloud

Giả sử API có 6 replica ở 3 AZ và PDB yêu cầu tối thiểu 4 Pod khả dụng; worker có 4 replica, có thể retry; DB là managed service ngoài cluster. Pool hiện tại dùng OS image cũ cần thay.

| Giai đoạn | Thao tác | Điều kiện chuyển bước |
|---|---|---|
| Prepare | Kiểm tra version, image, plugin, quota, IP và PDB | Có capacity ở pool/zone mới |
| Create | Tạo pool mới, áp labels/taints/role | Node Ready, network/storage/security agents khỏe |
| Canary | Chuyển một API replica và một worker | Readiness, p95, error, DB connectivity, queue processing đạt |
| Expand | Chuyển dần workload sang pool mới | Topology/PDB/capacity không có regression |
| Cordon | Cordon node cũ theo batch | Scheduler không đặt Pod mới vào pool cũ |
| Drain | Drain từng node | Pod replacement healthy, volume/quorum an toàn |
| Soak | Giữ pool mới qua tải đại diện | SLI/SLO, chi phí và cảnh báo ổn định |
| Retire | Xóa pool cũ, cập nhật IaC/catalog | Không còn workload, volume hay dependency |

Con số 6 replica, PDB 4 và 3 AZ chỉ minh họa. PDB không bảo đảm mỗi AZ còn Pod nếu topology không cấu hình; muốn phân tán thật cần topology spread/anti-affinity. Nếu một AZ đã mất trước drain, Pod healthy có thể không đủ và kế hoạch cần đổi.

Worker có thể drain nhanh hơn khi queue lease, checkpoint và idempotency đã được xác minh. API cần readiness đúng, connection draining và xử lý request đang chạy trước khi Pod dừng.

## 11. Lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách phòng tránh |
|---|---|---|
| Nâng control plane rồi mới phát hiện API bị loại bỏ | Controller/manifest không tạo hoặc đọc được resource | Quét deprecation và sửa trước |
| Xem node replacement là vô hại | Pod không schedule do thiếu quota/taint/IP/storage | Tạo pool mới và xác minh capacity |
| Drain toàn pool cùng lúc | Mất replica hoặc vượt disruption budget | Batch nhỏ, kiểm tra PDB/topology/SLO |
| Nghĩ PDB chống node chết | Vẫn mất Pod khi instance/AZ lỗi | Replica, topology, readiness và HA riêng |
| Xóa node khi chưa kiểm tra PV | Volume còn attachment hoặc không mount được | Kiểm tra PVC/PV/CSI topology và restore |
| Dùng local disk làm checkpoint duy nhất | Mất tiến độ | Storage bền vững |
| Chạy CronJob/consumer ở cả hai cluster | Side effect lặp | Ownership/lease/idempotency |
| Hai cluster cùng ghi DB | Conflict hoặc split-brain | Một writer có thẩm quyền hoặc thiết kế multi-writer thực sự |
| Giả định downgrade luôn khả thi | Control plane hoặc stored data không tương thích | Recovery qua restore/cluster mới |
| Xóa cluster cũ ngay sau cutover | Mất đường rollback | Soak period và tiêu chí retire |
| Chỉ kiểm tra Pod Ready | Nghiệp vụ vẫn có thể lỗi | Synthetic business test và SLI đầu cuối |

## 12. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi review | Bằng chứng |
|---|---|---|
| **Operational Excellence** | Ai điều phối upgrade, drain, rollback? | Change plan, owner, runbook, audit, diễn tập |
| **Security** | Image/runtime mới có bản vá và quyền tối thiểu? | Image scan, IAM/RBAC, network policy, patch status |
| **Reliability** | Mất node/zone hoặc upgrade thất bại có giữ dữ liệu/SLO? | PDB, topology, HA test, backup/restore, RTO/RPO |
| **Performance Efficiency** | Node mới đủ CPU/memory/network/storage cho peak? | Load test, saturation, p95/p99, backlog |
| **Cost Optimization** | Surge và hai pool/cluster chạy song song tốn bao nhiêu? | Cost forecast, utilization, thời điểm retire |
| **Sustainability** | Có tránh compute dư thừa và migration lặp? | Lifecycle, capacity metrics, node utilization |

Managed Kubernetes giảm một phần gánh nặng control plane, nhưng không tự chịu trách nhiệm về compatibility workload, backup dữ liệu, PDB, policy hay quyết định cutover.

## 13. Bài thực hành: nâng cấp cluster và thay node pool

Một hệ thống có ba pool: system-pool chạy CoreDNS/CNI/CSI/ingress/observability; api-pool chạy stateless API 8 replica; worker-pool chạy queue worker với task dài tối đa 20 phút. Cluster cần nâng Kubernetes minor version và đổi OS image. Một số PVC của StatefulSet nằm ở zone A. Nhóm muốn hoàn tất trong một maintenance window.

**Bài 1 — Compatibility:** tạo version matrix cho control plane, kubelet, runtime, CNI, CSI, ingress, CRD và chart. Nêu thứ tự nâng theo provider support matrix.

**Bài 2 — Node replacement:** thiết kế blue-green/rolling cho từng pool. Làm sao giữ DNS, network, storage và observability hoạt động khi thay system-pool?

**Bài 3 — Disruption:** đề xuất PDB, replica, topology spread và drain batch. Phân tích khi một API replica đã NotReady trước khi drain.

**Bài 4 — Worker state:** giải thích dừng polling, checkpoint task dài, ack/release lease và chống xử lý trùng khi Pod bị evict.

**Bài 5 — PVC:** vì sao PVC ở zone A không mặc định mount tại zone B? Đưa ra snapshot/restore hoặc storage migration và kiểm tra consistency.

**Bài 6 — Rollback:** nêu tiêu chí go/no-go, soak duration, ngưỡng dừng, dữ liệu cần backup và recovery khi control plane không downgrade được.

**Bài 7 — Well-Architected:** lập bảng tác động tới availability, security, p95, chi phí surge và năng lực vận hành; đề xuất phép thử trước production.

### Mẫu runbook rút gọn

~~~text
Change: Rotate api-pool from old-image to new-image
Owner: team-booking
Approver: platform-on-call

Pre-check:
  - compatibility matrix reviewed
  - quota/IP/capacity available in target zones
  - PDB/readiness/replicas healthy
  - database and persistent data backup verified
  - dashboards, alerts, rollback path ready

Execution:
  1. create new node pool
  2. validate node agents and network/storage
  3. move one canary replica
  4. verify business synthetic test and SLI
  5. cordon/drain old nodes in small batches
  6. repeat until target pool serves all workload

Abort when:
  - business error rate or latency exceeds agreed threshold
  - PDB blocks expected safe drain
  - volume/network/security agent fails
  - data inconsistency or duplicate side effect occurs

Close:
  - soak test passed
  - old pool has no dependency
  - inventory/IaC/ADR/runbook updated
~~~

Runbook thực tế phải thay ngưỡng, lệnh, tên resource và người trực theo provider/cluster. Checklist chung không thay thế maintenance procedure cụ thể.

## 14. Checklist trước khi phê duyệt nâng cấp hoặc di chuyển

- [ ] Phân biệt rõ control plane upgrade, node replacement và workload migration.
- [ ] Có compatibility matrix cho Kubernetes, kubelet, runtime, OS, CNI, CSI, CRD và controller.
- [ ] Đã kiểm tra API deprecation, webhook, chart/IaC và stored resource conversion.
- [ ] Backup/restore đã thử; xác định downgrade được hỗ trợ hay recovery phải qua cluster mới.
- [ ] Pool mới có quota, IP, capacity, zone, storage và IAM.
- [ ] Pod có readiness/liveness, graceful shutdown, termination budget và retry đúng.
- [ ] PDB/topology/replicas phù hợp; hiểu PDB không bảo vệ khỏi involuntary disruption.
- [ ] Inventory PVC/PV, volume attachment, local state, StatefulSet identity và quorum.
- [ ] CronJob, consumer và side effect có ownership/idempotency khi hai môi trường cùng tồn tại.
- [ ] Cluster đích có DNS, ingress, certificate, secret, network policy, observability và security agent.
- [ ] Có canary/soak, SLO, go/no-go, abort condition và rollback owner.
- [ ] Không xóa node/pool/cluster cũ trước khi hết dependency và đường phục hồi được phê duyệt.
- [ ] IaC, inventory, ADR, sơ đồ và runbook được cập nhật.

Nâng cấp nền tảng, thay node và di chuyển workload an toàn hơn khi chúng là **quy trình thay đổi có thể kiểm chứng**: hiểu tương thích, tạo capacity thay thế trước, chuyển tải có kiểm soát, bảo toàn dữ liệu, đo SLO và giữ đường phục hồi. Khi đó tổ chức có thể cập nhật container platform thường xuyên mà không để vòng đời node quyết định vòng đời dữ liệu hay tính liên tục của dịch vụ.
