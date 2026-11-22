# Thiết kế workload có trạng thái và lưu trữ bền vững

Container được tạo ra để chạy ứng dụng trong một môi trường đóng gói có thể thay thế. Khi container hoặc pod bị xóa, khởi động lại hay chuyển sang node khác, filesystem ghi bên trong container thường không phải nơi lưu dữ liệu lâu dài. Đây là điểm cần đặc biệt chú ý với **workload có trạng thái (stateful workload)** như database, message broker, hệ thống tìm kiếm, registry, nền tảng xử lý luồng và các ứng dụng duy trì dữ liệu phiên.

Thiết kế stateful container cần trả lời một câu hỏi quan trọng: **làm thế nào để vòng đời của compute có thể thay đổi mà dữ liệu vẫn bền vững, nhất quán, an toàn và khôi phục được?** Việc gắn một volume vào pod mới chỉ là bước đầu. Còn phải chọn loại storage, xác định quyền sở hữu dữ liệu, topology, cơ chế ghi/đọc, replication, backup, restore, quyền truy cập và quy trình xử lý khi node hoặc zone gặp lỗi.

Trong module **CLOUD_ARCHITECTURE**, chủ đề này kết nối kiến trúc container với lựa chọn dữ liệu, mạng, compute và vận hành theo các mục tiêu Well-Architected: độ tin cậy, bảo mật, hiệu năng, tối ưu chi phí và khả năng vận hành.

## 1. Stateless và stateful: khác nhau ở vòng đời dữ liệu

**Stateless workload** không giữ trạng thái nghiệp vụ duy nhất trong filesystem hoặc bộ nhớ cục bộ của một replica giữa các request. Replica có thể được thay thế và request tiếp theo được xử lý bởi replica khác, miễn là dữ liệu cần thiết nằm ở dịch vụ bên ngoài hoặc có thể được tái tạo.

**Stateful workload** phải giữ một phần dữ liệu hoặc danh tính ổn định qua vòng đời của process/container. Một database cần giữ các trang dữ liệu; một message broker cần giữ message chưa được xác nhận; một search node cần giữ index shard hoặc có cơ chế tái tạo; một hệ thống có session local cần bảo vệ trạng thái phiên khỏi việc pod bị thay thế.

| Đặc điểm | Stateless | Stateful |
| --- | --- | --- |
| Dữ liệu chính | Lưu ở database/cache/object storage hoặc có thể tái tạo | Có dữ liệu cần bảo toàn gắn với ứng dụng hoặc volume |
| Thay thế replica | Thường tương đối đơn giản | Phải gắn lại đúng dữ liệu và đảm bảo không có writer xung đột |
| Scale ngang | Thêm/bớt replica theo tải | Phải xử lý shard, replication, quorum, partition hoặc giới hạn ghi |
| Scheduling | Replica có thể chạy trên node phù hợp bất kỳ | Placement phải xét volume topology và node/zone |
| Phục hồi | Khởi tạo replica mới và nạp cấu hình | Có thể cần attach volume, recovery log, rebuild hoặc failover |
| Kiểm thử | Health check, rollout, load test | Thêm corruption, detach/attach, node loss, restore, split-brain |

Ví dụ một ứng dụng web container hóa nên đưa session ra cache/shared session store và dữ liệu nghiệp vụ vào database quản lý độc lập. Khi đó API pod có thể stateless. Nhưng database hoặc broker phía sau vẫn là workload có trạng thái và cần chiến lược lưu trữ riêng.

### Trạng thái không chỉ nằm trong file

Một workload có thể giữ trạng thái trong:

- **Filesystem:** file dữ liệu, index, log giao dịch, checkpoint.
- **Bộ nhớ:** session, cache, leader state, queue chưa ghi bền.
- **Danh tính mạng:** hostname ổn định, địa chỉ endpoint hoặc membership.
- **Danh tính logic:** node ID, broker ID, shard/partition identity.
- **Metadata điều phối:** vị trí volume, replica role, trạng thái failover.

Không phải tất cả đều cần persistent volume. Tuy nhiên, phải xác định rõ phần nào **có thể tái tạo**, phần nào cần **persist**, và phần nào có thể phục hồi từ replica hoặc nguồn dữ liệu khác.

## 2. Filesystem của container và vì sao cần persistent storage

Container image thường được triển khai qua các lớp filesystem bất biến (read-only image layers) cùng một lớp ghi cho container (writable layer). Lớp ghi này gắn với vòng đời container; khi container được tạo mới, lớp ghi cũ không tự động trở thành dữ liệu của container mới. Một pod được thay thế cũng có thể nhận filesystem ghi mới.

~~~mermaid
flowchart TB
    subgraph CONTAINER["Container filesystem"]
      IMG["Image layers (read-only)"]
      WRITE["Writable layer (ephemeral)"]
      IMG --> WRITE
    end
    subgraph POD["Pod"]
      APP["Application process"]
      TMP["Temporary / cache files"]
      APP --> TMP
    end
    PV["Persistent volume"]
    APP -->|Mount path| PV
~~~

Hình minh họa phân biệt image, writable layer và volume. Một số đường dẫn tạm có thể được mount từ emptyDir hoặc filesystem tạm của node; chúng vẫn không phải nơi lưu dữ liệu bền vững qua mọi tình huống pod/node failure. Persistent volume có vòng đời được quản lý riêng theo cơ chế nền tảng và storage provider.

### Khi nào dùng ephemeral storage?

Ephemeral storage phù hợp với:

- File tạm trong lúc xử lý một request/job.
- Cache có thể tái tạo và không phải nguồn sự thật.
- Scratch space để giải nén, sắp xếp hoặc chuyển đổi dữ liệu.
- Shared temporary files giữa container trong cùng pod khi vòng đời pod được chấp nhận.

Không dùng ephemeral storage làm nơi duy nhất lưu database, file người dùng, message chưa xử lý hoặc checkpoint duy nhất của batch dài. Nếu node lỗi hoặc pod bị thay thế, dữ liệu có thể mất.

### Khi nào cần persistent volume?

Volume bền vững phù hợp khi ứng dụng cần dữ liệu tồn tại độc lập với container/pod, như:

- Database lưu data files và transaction logs.
- Message broker lưu segment/queue metadata.
- Search engine lưu index khi index không thể hoặc không muốn rebuild nhanh từ nguồn.
- Registry/artifact service lưu blobs và metadata.
- Stateful analytics hoặc streaming engine lưu checkpoint/state store.

Tuy nhiên, persistent volume chỉ đảm bảo **một phần lớp lưu trữ**. Nó không tự tạo backup, replication, transaction consistency, database failover, chống ransomware hay bảo đảm ứng dụng phục hồi đúng.

## 3. Các mô hình storage: block, file và object

Chọn storage theo kiểu truy cập của ứng dụng, không chỉ theo tên dịch vụ.

| Loại storage | Cách ứng dụng truy cập | Use case thường gặp | Đánh đổi |
| --- | --- | --- | --- |
| **Block storage** | Thiết bị block được gắn vào node/VM; filesystem hoặc database quản lý cấu trúc trên đó | Database data directory, broker disk, workload cần IOPS/latency có kiểm soát | Ràng buộc attach/topology; cần filesystem và concurrency phù hợp |
| **File storage** | Nhiều client truy cập namespace file/thư mục qua giao thức như NFS/SMB hoặc dịch vụ tương đương | Shared content, file exchange, home directory, công cụ cũ cần shared filesystem | Hiệu năng phụ thuộc metadata/throughput/locking; semantics khác local disk |
| **Object storage** | Truy cập object qua API, key/bucket/container; không phải filesystem POSIX thông thường | Media, backup, log archive, static asset, data lake | Không phù hợp làm disk block cho database thông thường; consistency/API semantics cần hiểu rõ |

### Block storage

Block volume cung cấp thiết bị lưu trữ cho một node hoặc instance. Hệ điều hành/ứng dụng tạo filesystem hoặc dùng raw device. Database thường thích hợp với block storage có latency và IOPS dự đoán được, nhưng phải kiểm tra:

- IOPS, throughput và latency tại kích thước I/O thực tế.
- Tỉ lệ đọc/ghi ngẫu nhiên, sequential workload và burst credit nếu có.
- Durability và replication nội bộ của dịch vụ storage.
- Cơ chế multi-attach có hỗ trợ hay không và điều kiện sử dụng.
- Backup/snapshot, encryption, resize và thời gian attach/detach.

Không mount cùng một filesystem block trên nhiều node chỉ vì storage driver cho phép attach nhiều nơi. Multi-writer cần filesystem/distributed locking và ứng dụng được thiết kế cho semantics tương ứng; database thông thường không an toàn khi hai node cùng mở cùng một data directory nếu không có cơ chế cluster được hỗ trợ.

### File storage

File storage cung cấp không gian thư mục được truy cập qua mạng. Nó hữu ích khi nhiều pod cần đọc/ghi cùng bộ file, hoặc ứng dụng cũ yêu cầu file share. Cần xem xét:

- Hỗ trợ đồng thời nhiều client, file locking và semantics rename/permission.
- Throughput, IOPS metadata, giới hạn file handle và số kết nối.
- Hiệu năng khi nhiều pod truy cập thư mục nóng hoặc tạo nhiều file nhỏ.
- Cơ chế mount, network path, private endpoint và failover.
- Backup, quota, retention và chi phí dung lượng/throughput.

File storage không tự giải quyết tranh chấp logic ở ứng dụng. Hai pod cùng sửa một file phải có cơ chế khóa hoặc giao thức ghi an toàn; nếu không, file có thể bị ghi đè hoặc hỏng logic.

### Object storage

Object storage được thiết kế để lưu các object có key và metadata, truy cập qua API. Đây là lựa chọn phù hợp cho ảnh, video, backup, log và dữ liệu phi cấu trúc quy mô lớn. Một số containerized application dùng object storage thay persistent volume để giữ media, nhưng không nên giả định object store có mọi semantics của filesystem (lock, seek, atomic rename, POSIX permissions).

Với object storage cần thiết kế:

- Key naming, metadata, versioning và chính sách overwrite.
- Multipart upload, checksum và xác minh tính toàn vẹn.
- Lifecycle sang tier lạnh, retention và xóa theo yêu cầu.
- Quyền truy cập theo workload identity, bucket/container policy và encryption.
- Event notification, duplicate, retry và xử lý object chưa hoàn tất.

### Chọn nhanh theo kiểu dữ liệu

| Dữ liệu | Lựa chọn thường được cân nhắc | Lưu ý |
| --- | --- | --- |
| Database transaction files | Block volume hoặc managed database storage | Phải theo hướng dẫn của database engine |
| File người dùng/ảnh/video | Object storage | Metadata và lifecycle riêng |
| Shared folder cho ứng dụng cũ | File storage | Kiểm tra file locking và throughput |
| Cache có thể tái tạo | Memory cache hoặc ephemeral disk | Không coi là nguồn dữ liệu bền |
| Backup và archive | Object storage hoặc dịch vụ backup | Tách quyền, retention và restore test |
| Log/checkpoint của engine | Block hoặc storage chuyên dụng theo engine | Không xóa trước khi engine xác nhận an toàn |

## 4. Persistent storage trong Kubernetes: PV, PVC, StorageClass và CSI

Trong Kubernetes, ứng dụng thường yêu cầu storage thông qua **PersistentVolumeClaim (PVC)**. PVC mô tả dung lượng, access mode và storage class cần có. Một **PersistentVolume (PV)** biểu diễn tài nguyên lưu trữ được cluster quản lý; PV có thể được tạo sẵn (static provisioning) hoặc được cấp động từ StorageClass. Volume plugin/CSI driver kết nối Kubernetes với hệ thống lưu trữ ở bên dưới.

~~~mermaid
flowchart TB
    POD["Pod"]
    PVC["PersistentVolumeClaim"]
    SC["StorageClass"]
    PV["PersistentVolume"]
    CSI["CSI driver"]
    BACKEND["Cloud block/file storage"]
    POD -->|Mount PVC| PVC
    PVC -->|Yêu cầu cấp phát| SC
    SC -->|Provision / bind| PV
    PV --> CSI
    CSI --> BACKEND
~~~

Sơ đồ mô tả đường khái niệm; thứ tự provisioning và binding thực tế có thể phụ thuộc volume binding mode, controller, CSI driver và scheduler.

### Các thành phần

| Thành phần | Trách nhiệm |
| --- | --- |
| **PVC** | Yêu cầu storage của workload: dung lượng, access mode, storage class |
| **PV** | Đại diện volume đã được cấp phát và các thuộc tính tương ứng |
| **StorageClass** | Chính sách cấp phát: provisioner, loại storage, tham số, reclaim policy, binding mode |
| **CSI (Container Storage Interface)** | Chuẩn giao tiếp để storage provider tích hợp thao tác provisioning, attach, mount, snapshot và resize theo tính năng driver |
| **Volume snapshot** | Đại diện snapshot volume theo API/hỗ trợ driver; cần quy trình nhất quán dữ liệu của ứng dụng |

### Ví dụ PVC yêu cầu block volume

Ví dụ sau minh họa PVC yêu cầu 100 GiB và một access mode. Tên StorageClass là placeholder, phải thay bằng loại do cluster cung cấp:

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: database-data
  namespace: production
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: standard-block
  resources:
    requests:
      storage: 100Gi
~~~

Ví dụ này **chỉ yêu cầu cấp storage**, chưa tạo database, credential, backup hay HA. Access mode là điều kiện gắn volume theo semantics Kubernetes và driver, không thay thế cơ chế khóa hoặc replication ở database. Ý nghĩa attach thực tế còn tùy CSI provider và nền tảng.

### Gắn PVC vào Pod

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: storage-check
  namespace: production
spec:
  containers:
    - name: app
      image: example.registry.local/storage-app:v1
      volumeMounts:
        - name: data
          mountPath: /var/lib/app
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: database-data
~~~

Pod có volume mount tại đường dẫn đã khai báo. Khi pod bị thay thế, controller có thể tạo pod mới và gắn lại PVC theo topology, trạng thái detach/attach và khả năng của storage provider. Trong môi trường thực, cần kiểm tra mount options, filesystem ownership, security context, image và namespace.

### Access mode không phải cơ chế đồng thời của ứng dụng

| Access mode | Ý nghĩa khái quát |
| --- | --- |
| **ReadWriteOnce (RWO)** | Volume có thể được mount read-write bởi một node tại một thời điểm theo semantics của volume/plugin; nhiều pod trên cùng node có thể cùng sử dụng tùy nền tảng |
| **ReadOnlyMany (ROX)** | Có thể được mount read-only bởi nhiều node nếu driver hỗ trợ |
| **ReadWriteMany (RWX)** | Có thể được mount read-write bởi nhiều node nếu driver hỗ trợ |
| **ReadWriteOncePod (RWOP)** | Giới hạn volume chỉ được mount read-write bởi một pod trong cluster, khi CSI driver và Kubernetes hỗ trợ |

Không nên diễn giải RWO thành “chỉ một pod” hoặc RWX thành “mọi ứng dụng ghi an toàn”. RWO thường ràng buộc theo node, trong khi RWOP có mục tiêu giới hạn theo pod. Nhiều writer vẫn cần ứng dụng/filesystem/database quản lý đồng thời. Một số storage class không hỗ trợ mọi access mode; kiểm tra tài liệu driver và kiểm thử thực tế.

### StorageClass và binding topology

StorageClass có thể chọn loại disk (performance tier), provisioner, encryption, reclaim policy và binding mode. Hai thiết lập cần chú ý:

- **Immediate:** volume có thể được provision/bind ngay khi PVC tạo, trước khi scheduler chọn node; trong hệ thống storage có giới hạn vùng, pod về sau có thể bị kẹt vì volume nằm sai topology.
- **WaitForFirstConsumer:** trì hoãn provisioning/binding tới khi có consumer, cho phép scheduler xét yêu cầu placement của pod cùng topology storage.

Ví dụ, block volume là tài nguyên zonal. Nếu PVC được tạo ở zone A nhưng StatefulSet pod được scheduling ở zone B, pod có thể Pending do volume không attach được. Dùng binding mode phù hợp và storage topology để giảm lỗi này. WaitForFirstConsumer không tự giải quyết bài toán replica đa zone; cần thiết kế từng replica và storage placement.

### Reclaim policy và vòng đời dữ liệu

Sau khi PVC bị xóa, PV có thể tuân theo reclaim policy như **Retain** hoặc **Delete** tùy loại tài nguyên và cấu hình. Delete có thể làm backend volume bị xóa theo quy trình; Retain giữ tài nguyên để người quản trị xử lý thủ công hoặc tái sử dụng. Không giả định xóa PVC luôn chỉ gỡ mount hay luôn xóa dữ liệu. Trước khi đổi chart/manifests hoặc dọn namespace, phải hiểu:

- Ai sở hữu volume và dữ liệu?
- PVC/PV được tạo tĩnh hay động?
- Reclaim policy hiện tại là gì?
- Có snapshot/backup đã kiểm chứng chưa?
- Có quy trình phục hồi hoặc tái bind khi PVC được tạo lại không?

## 5. StatefulSet và danh tính ổn định cho replica

Kubernetes **Deployment** thích hợp với nhóm replica có thể hoán đổi và thường không cần danh tính/volume riêng. **StatefulSet** được thiết kế cho workload cần danh tính mạng ổn định, thứ tự tạo/xóa hoặc volume riêng cho từng replica.

StatefulSet thường cung cấp:

- **Ordinal ổn định:** các pod có tên theo chỉ số, ví dụ database-0, database-1.
- **Network identity ổn định:** kết hợp headless Service để tạo danh tính DNS của từng pod.
- **Stable storage association:** volume claim template tạo PVC riêng cho từng ordinal.
- **Controlled rollout/scaling:** thứ tự start/stop/update theo policy của StatefulSet.

StatefulSet không tự tạo cluster database, replication, leader election, quorum, backup hoặc failover an toàn. Nó chỉ cung cấp cơ chế điều phối pod và identity; ứng dụng vẫn phải có protocol cluster phù hợp.

### Ví dụ StatefulSet ba replica

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: ledger
  namespace: production
spec:
  clusterIP: None
  selector:
    app: ledger
  ports:
    - name: client
      port: 8080
    - name: peer
      port: 7000
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: ledger
  namespace: production
spec:
  serviceName: ledger
  replicas: 3
  selector:
    matchLabels:
      app: ledger
  template:
    metadata:
      labels:
        app: ledger
    spec:
      containers:
        - name: node
          image: example.registry.local/ledger-node:v1
          ports:
            - name: client
              containerPort: 8080
            - name: peer
              containerPort: 7000
          volumeMounts:
            - name: data
              mountPath: /var/lib/ledger
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes:
          - ReadWriteOnce
        storageClassName: zonal-ssd
        resources:
          requests:
            storage: 50Gi
~~~

Đây là skeleton minh họa; image, peer discovery, authentication, probes, resource requests/limits, backup, security context và storage class phải được thiết kế cho engine cụ thể. Không nên triển khai một StatefulSet database thực tế chỉ bằng manifest rút gọn này.

Ví dụ ordinal đầu tiên có thể có PVC riêng tương ứng với claim template và tên pod. Khi pod bị tạo lại, PVC đó thường được giữ để pod mới sử dụng lại theo chính sách và topology. Việc scale StatefulSet xuống không mặc nhiên xóa PVC theo mọi cấu hình, nhưng **không nên dựa vào giả định vòng đời**; phải xác nhận hành vi/version của Kubernetes, retention policy, chart/operator và quy trình xóa tài nguyên.

### Scheduling và phân tán replica

Nếu ba replica database cùng được xếp trên một node hoặc một AZ, node/AZ đó lỗi có thể làm mất quorum. Cần xét:

- **Pod anti-affinity hoặc topology spread constraints** để phân bố replica theo node/AZ.
- **PodDisruptionBudget (PDB)** để giới hạn gián đoạn do một số thao tác bảo trì tự nguyện; PDB không ngăn node chết, không thay thế HA.
- **Node affinity/taints/tolerations** và khả năng storage attach ở node/zone tương ứng.
- **Resource requests/limits** để scheduler đặt pod đủ tài nguyên và tránh tranh chấp.
- **Startup/readiness/liveness probes** phù hợp tiến trình recovery của ứng dụng.

Việc buộc spread ba replica qua ba AZ chỉ có ích nếu storage, mạng, quorum và ứng dụng cũng hỗ trợ topology đó. Pod có thể Pending nếu storage zonal không nằm đúng AZ, hoặc nếu không còn node đủ tài nguyên.

## 6. Stateful workload cần ứng dụng hiểu về cluster

Gắn nhiều pod cùng một PVC không tự làm ứng dụng thành distributed system. Một database cluster, broker cluster hoặc search cluster thường có protocol riêng để bầu leader, phân shard, đồng bộ dữ liệu, xác nhận commit và xử lý node mất kết nối.

Trước khi triển khai, cần đọc hướng dẫn của engine:

- Số replica tối thiểu và quy tắc quorum.
- Node identity, cluster membership và peer discovery.
- Cơ chế replication đồng bộ/bất đồng bộ; lag và xác nhận ghi.
- Leader election, fencing và cách ngăn hai writer cùng hoạt động.
- Hành vi khi pod restart, volume attach lại, node khởi động chậm.
- Quy trình thêm/bớt replica và thay đổi capacity.
- Recovery sau crash, upgrade protocol và rollback version.

**Operator** có thể tự động hóa lifecycle cho một ứng dụng stateful: tạo cluster, cấu hình replica, nâng cấp, backup hoặc failover theo logic của engine. Tuy vậy, operator chỉ hữu ích nếu được hỗ trợ, cấu hình đúng, quyền hạn phù hợp và có runbook. CRD/operator không biến storage yếu thành storage bền vững, cũng không thay việc kiểm tra backup và phục hồi.

### Quorum và số replica

Nhiều hệ thống consensus dùng quorum đa số. Với \(N\) voting members, majority thường là:

\[
Q=\left\lfloor\frac{N}{2}\right\rfloor+1.
\]

Với ba voting members, quorum là hai; hệ thống có thể chịu mất một member nếu hai member còn lại vẫn liên lạc và dữ liệu đáp ứng điều kiện của giao thức. Với hai voting members, quorum là hai nên mất một member có thể khiến cluster không thể tiếp tục quyết định. Đây là mô hình phổ biến nhưng **không áp dụng tự động cho mọi database/broker**; có hệ thống dùng witness, voter/non-voter, replica role hoặc consensus khác.

Không nên đặt ba replica trong ba AZ chỉ để “đủ ba pod”. Phải bảo đảm:

- Các voter nằm ở failure domain thực sự độc lập.
- Đường network giữa chúng ổn định và policy cho phép đúng peer traffic.
- Storage từng replica đáp ứng latency và durability.
- Quorum không bị phá khi bảo trì đồng thời hoặc nâng cấp.
- Ứng dụng/client biết endpoint writer/leader và xử lý chuyển đổi.

### StatefulSet không phải cơ chế replication

StatefulSet tạo danh tính ordinal như node-0/node-1/node-2 và volume claim riêng theo template. Nó không tự sao chép dữ liệu giữa các volume. Nếu database cluster cần replication, database engine hoặc operator phải thực hiện; nếu một PVC bị mất, không thể dựa vào StatefulSet để tự khôi phục dữ liệu.

## 7. Durability, replication, snapshot và backup là các lớp khác nhau

Một volume có durability cao giúp dữ liệu trên thiết bị ít bị mất do một số sự cố phần cứng, nhưng không bảo vệ được mọi tình huống:

| Cơ chế | Mục đích | Không giải quyết thay cho |
| --- | --- | --- |
| Storage durability/replication nội bộ | Chống mất phần cứng theo thiết kế của storage service | Xóa nhầm, ghi sai logic, ransomware, lỗi ứng dụng |
| Database replication | Duy trì bản sao dữ liệu và khả năng failover/đọc | Backup lịch sử độc lập hoặc khôi phục về trước lỗi |
| Volume snapshot | Chụp trạng thái block/file ở một thời điểm theo semantics storage | Ứng dụng-aware consistency, retention dài hạn, restore test |
| Database-native backup | Lưu bản sao theo logic engine, có thể gồm log/metadata | Khả năng truy cập backup nếu quyền hoặc region dùng chung bị xâm phạm |
| Point-in-time recovery (PITR) | Khôi phục về thời điểm trước một lỗi logic trong khoảng retention | Thời gian phục hồi bằng 0 hoặc mọi loại corruption đều giải quyết tự động |

### Crash consistency và application consistency

Snapshot storage có thể chỉ bảo đảm trạng thái nhất quán ở mức block/crash-consistent theo cách dịch vụ hỗ trợ. Database đang ghi có thể có page trong memory chưa flush, transaction log chưa checkpoint hoặc nhiều volume phải được chụp đồng bộ. Một snapshot của volume đơn lẻ không mặc nhiên là **application-consistent**.

Để tạo bản sao nhất quán:

1. Dùng backup tool hoặc API snapshot tích hợp với database/engine khi có.
2. Nếu cần, flush/quiesce hoặc tạm dừng ghi theo quy trình được hỗ trợ.
3. Với engine hỗ trợ online backup, ghi nhận checkpoint/LSN và log cần thiết.
4. Nếu dữ liệu nằm trên nhiều volume, dùng nhóm snapshot consistency hoặc quy trình phối hợp.
5. Kiểm tra checksum, metadata, retention và quyền truy cập sau khi backup.

Không tự ý pause process hoặc đóng băng filesystem khi chưa hiểu cơ chế engine. Quy trình backup sai có thể tạo ảnh chụp không dùng được hoặc làm gián đoạn hệ thống.

### RPO, RTO và chính sách backup

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa theo thời gian mà tổ chức có thể chấp nhận mất trong kịch bản xác định.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ có thể sử dụng sau sự cố.
- **Retention:** thời gian giữ backup/snapshot; cần phù hợp quy định và khả năng phục hồi.
- **Backup isolation:** backup cần có quyền, tài khoản hoặc vị trí tách biệt phù hợp để lỗi/xâm phạm production không dễ xóa luôn bản sao.
- **Restore validation:** kiểm tra định kỳ có thể phục hồi dữ liệu và ứng dụng thực sự mở/đọc/ghi được.

Ví dụ policy minh họa cho một database giao dịch: snapshot hằng ngày giữ 14 ngày, backup logic hằng ngày giữ 30 ngày và log liên tục cho PITR giữ 7 ngày, bản sao định kỳ được lưu ở vùng khác. Các khoảng thời gian này không phải khuyến nghị chung; cần tính theo RPO/RTO, kích thước dữ liệu, tốc độ thay đổi, yêu cầu pháp lý và chi phí.

### Snapshot không đồng nghĩa backup

Snapshot có thể được quản lý cùng account, cùng quyền hoặc cùng vùng với volume nguồn. Một người dùng có quyền xóa volume có thể cũng xóa snapshot nếu policy không tách. Đối với dữ liệu quan trọng, cần xem xét bản backup độc lập, immutable retention hoặc vault riêng nếu dịch vụ hỗ trợ. Quan trọng nhất là diễn tập restore và đo thời gian.

## 8. Topology storage và đa availability zone

Cloud block volume thường có **phạm vi vùng/AZ** cụ thể. Một volume ở AZ A thường chỉ attach được vào node có khả năng truy cập volume đó theo dịch vụ/driver; pod không thể tự do chuyển sang AZ B nếu volume không thể attach ở đó. File storage có thể phục vụ nhiều AZ hoặc có topology riêng; object storage thường là dịch vụ qua API với durability/replication theo region/zone do provider công bố. Phải kiểm tra mô hình thực tế của từng loại.

### Hai mô hình phổ biến

**Một volume zonal cho mỗi replica:** StatefulSet có một PVC riêng cho mỗi pod, volume được provision tại zone tương ứng. Database engine replication dữ liệu qua các replica ở nhiều AZ. Khi mất một AZ, replica ở AZ còn lại tiếp tục theo cơ chế failover của engine. Đây là cách phổ biến để đặt stateful cluster, nhưng phải tính quorum và replication lag.

**Một shared file system nhiều node:** nhiều pod hoặc node mount cùng file share khi ứng dụng và file protocol hỗ trợ multi-client. Cần xác định lock, concurrency, throughput và failover. Shared filesystem không thay thế database replication hoặc transaction nếu ứng dụng cần bất biến dữ liệu.

~~~mermaid
flowchart TB
    subgraph AZA["Availability Zone A"]
      P0["Pod database-0"]
      V0["PVC/PV A"]
      P0 --> V0
    end
    subgraph AZB["Availability Zone B"]
      P1["Pod database-1"]
      V1["PVC/PV B"]
      P1 --> V1
    end
    subgraph AZC["Availability Zone C"]
      P2["Pod database-2"]
      V2["PVC/PV C"]
      P2 --> V2
    end
    P0 <-->|"Database replication"| P1
    P1 <-->|"Database replication"| P2
    P0 <-->|"Database replication"| P2
~~~

Hình mô tả các replica có volume riêng và replication ở tầng database. Nó **không** mô tả một volume được mount đồng thời ở ba AZ. Mỗi node phải có danh tính và dữ liệu đúng theo engine; volume attach riêng không đồng nghĩa dữ liệu tự đồng bộ.

### Điều gì xảy ra khi AZ chứa volume bị lỗi?

Cần phân biệt:

1. **Pod lỗi nhưng volume còn sẵn:** controller tạo lại pod, scheduler tìm node có thể attach volume và engine recovery.
2. **Node lỗi nhưng volume vẫn tồn tại:** detach/attach có thể cần chờ xác nhận node cũ không còn ghi; fencing hoặc thao tác detach an toàn phụ thuộc cloud provider/CSI.
3. **AZ mất:** volume zonal có thể không truy cập được trong thời gian sự cố. Pod thay thế ở AZ khác có thể không attach volume đó; database phải failover sang replica với volume riêng ở AZ khỏe.
4. **Volume hỏng hoặc dữ liệu hỏng:** cần replica hoặc restore backup; tạo pod mới và mount cùng volume hỏng không khôi phục dữ liệu.

Không ép pod sang một zone không thể truy cập dữ liệu chỉ để scheduler thấy pod chạy. **Tính đúng đắn dữ liệu và quyền sở hữu writer quan trọng hơn trạng thái Running.**

## 9. Chọn storage performance và sizing

Dung lượng không phải thông số duy nhất. Cần định lượng:

- **IOPS:** số thao tác I/O mỗi giây.
- **Throughput:** byte đọc/ghi mỗi giây.
- **Latency:** thời gian hoàn tất I/O, nên xét p95/p99.
- **I/O size và pattern:** 4 KiB random, 256 KiB sequential hoặc pattern thực của engine.
- **Read/write ratio:** tỉ lệ đọc và ghi, sync write, fsync và checkpoint.
- **Burst behavior:** throughput/IOPS burst có giới hạn hoặc credit hay không.
- **Capacity growth:** dữ liệu tăng, index, WAL/log, temporary space và backup.

Ví dụ một database có workload 8.000 IOPS, đọc 70%, ghi 30%, kích thước I/O trung bình 16 KiB. Throughput thô ước lượng:

\[
8.000\times16\text{ KiB}=128.000\text{ KiB/s}\approx125\text{ MiB/s}.
\]

Đây chỉ là phép nhân số I/O với kích thước giả định, chưa phản ánh write amplification, metadata, latency, cache, filesystem overhead hoặc engine batching. Storage phải được benchmark với workload thực và cấu hình durability đồng nhất với production.

### Sizing dung lượng

Một công thức lập kế hoạch đơn giản:

\[
\text{Dung lượng cần}
= \text{Dữ liệu hiện tại}
+ \text{Tăng trưởng trong kỳ}
+ \text{Index/log/temp}
+ \text{Headroom}.
\]

Ví dụ dữ liệu tăng 8 GiB/tuần, hiện có 200 GiB, cần dự trù 26 tuần, cộng 25% cho index/log/temp và 20% headroom:

\[
(200+8\times26)\times1{,}25\times1{,}20
=612\text{ GiB}.
\]

Phép tính này giả định tăng trưởng đều và các hệ số được chọn để minh họa; thực tế cần đo database growth, retention, log rotation, vacuum/compaction, snapshot và cách storage billing tính provisioned capacity. Không cấp đúng bằng dung lượng đang dùng vì có thể hết chỗ khi checkpoint/compaction hoặc recovery cần temporary space.

### Khi tăng size hoặc thay StorageClass

Việc mở rộng volume thường có các giới hạn và điều kiện:

- StorageClass/CSI driver có cho phép volume expansion không?
- Filesystem cần resize online hay phải thao tác trên node?
- Có thể giảm volume size hay chỉ tăng?
- Có rủi ro downtime, attach/detach hoặc thay đổi topology?
- Storage performance thay đổi theo provisioned size hay cấu hình độc lập?
- Backup/snapshot trước resize có cần thiết theo quy trình?

Không chỉnh PVC/storage class trong production mà chưa hiểu quá trình reconcile của controller và khả năng hỗ trợ resize. Với database quan trọng, lập kế hoạch capacity trước khi chạm ngưỡng.

## 10. Bảo mật persistent storage

Persistent volume giữ dữ liệu sau khi pod bị thay thế, vì vậy vòng đời và quyền truy cập dữ liệu cần được quản lý như một tài sản độc lập.

### Encryption at rest và in transit

- Mã hóa volume/snapshot bằng khóa được quản lý phù hợp; xác định quyền tạo, sử dụng, xoay vòng và thu hồi khóa.
- Mã hóa traffic giữa ứng dụng với database/file service, giữa các replica và từ CSI/node đến dịch vụ storage khi nền tảng yêu cầu.
- Backup và bản sao ở region khác cũng phải được mã hóa, kiểm soát quyền và kiểm tra khả năng giải mã trong khôi phục.
- Phân biệt encryption do storage provider cung cấp với mã hóa ở tầng database/application; hai lớp có mục đích và mô hình khóa khác nhau.

### Quyền tối thiểu và cách ly

1. Chỉ service account/workload identity cần thiết được phép dùng PVC, snapshot hoặc storage API.
2. Không cấp quyền tạo snapshot/clone hoặc xóa volume cho mọi namespace/team.
3. Dùng namespace, cloud account/project, storage policy và key policy để tách production với non-production.
4. Tránh lưu secret database, key mã hóa hoặc credential dài hạn trong image và manifest dạng plain text.
5. Nếu cần chia sẻ file, cấp quyền theo thư mục/identity; không mở RWX toàn cluster khi chỉ một workload cần ghi.
6. Audit create/attach/detach/resize/snapshot/delete và thao tác backup/restore; cảnh báo khi volume production bị xóa ngoài kế hoạch.

### Security context và quyền filesystem

Container có thể chạy bằng non-root user, filesystem read-only và mount volume với quyền tối thiểu nếu ứng dụng hỗ trợ. Kiểm tra UID/GID, fsGroup, ownership, SELinux/AppArmor hoặc cơ chế tương đương của nền tảng. Không giải quyết lỗi permission bằng chmod 777 diện rộng; cách đó làm mọi process có thể ghi và tăng rủi ro phá dữ liệu.

Với workload nhạy cảm, cần xem xét ai có quyền exec vào pod, node và host; quyền snapshot có thể làm lộ dữ liệu ngay cả khi người dùng không được truy cập database trực tiếp. Dữ liệu backup phải có access control riêng.

## 11. Vòng đời volume: provision, attach, mount, detach và reclaim

Storage có lifecycle độc lập với pod:

~~~mermaid
stateDiagram-v2
    [*] --> Requested: PVC tạo
    Requested --> Provisioned: PV được provision
    Provisioned --> Bound: PVC/PV binding
    Bound --> Attached: Gắn vào node
    Attached --> Mounted: Mount vào pod
    Mounted --> Detached: Pod/node dừng
    Detached --> Attached: Pod thay thế
    Detached --> Retained: PVC xóa / Retain
    Detached --> Deleted: PVC xóa / Delete
    Retained --> Bound: Reclaim / bind theo quy trình
    Deleted --> [*]
~~~

Sơ đồ là vòng đời khái quát. Thực tế controller có thể thực hiện nhiều bước song song; detach có thể bị trì hoãn khi node không phản hồi và chính sách storage có thể giữ tài nguyên ở trạng thái trung gian.

### Các thao tác cần quản trị

| Thao tác | Câu hỏi vận hành |
| --- | --- |
| Provision | Quota còn đủ không? StorageClass và AZ có đúng không? |
| Bind | PVC có gắn với đúng PV và thuộc tính mong muốn không? |
| Attach | Volume đã được detach khỏi node cũ an toàn chưa? Có giới hạn attach/node không? |
| Mount | Filesystem, quyền user và mount option có phù hợp không? |
| Expand | Driver/filesystem có hỗ trợ tăng dung lượng không? |
| Snapshot | Ứng dụng đã quiesce/checkpoint nếu cần chưa? Snapshot retention và consistency ra sao? |
| Detach | Pod có flush dữ liệu và đóng file handle? Node có còn ghi không? |
| Reclaim/delete | Xóa PVC có làm mất volume production hoặc backup không? |
| Restore | Có thể khôi phục vào môi trường độc lập và xác minh dữ liệu không? |

### Tránh split-brain khi volume được gắn lại

Nếu node cũ mất liên lạc nhưng vẫn có thể ghi vào storage, việc gắn cùng volume cho node mới mà không fencing có thể dẫn tới **hai writer đồng thời**. Nền tảng thường có cơ chế attach/detach và fencing riêng, nhưng hành vi phụ thuộc driver/cloud. Không tự ép force detach/reattach nếu chưa xác nhận node cũ không còn ghi và quy trình recovery của nhà cung cấp/engine cho phép.

Trong một số lỗi, chờ hoàn tất detach an toàn mất nhiều thời gian nhưng tốt hơn cho tính toàn vẹn dữ liệu. Runbook cần mô tả điều kiện khi nào được thao tác thủ công, ai phê duyệt và cách xác minh filesystem/database sau đó.

## 12. Quan sát và xử lý sự cố stateful workload

Ứng dụng stateless thường có thể thay pod nhanh; stateful workload phải theo dõi cả **process, pod, storage, node, replication và dữ liệu**.

| Lớp | Chỉ số/tín hiệu nên quan sát | Dấu hiệu rủi ro |
| --- | --- | --- |
| Pod/process | Restart count, OOMKilled, Pending, readiness, startup duration | Crash loop, thiếu tài nguyên, volume mount chậm |
| Storage | Used capacity, free space, IOPS, throughput, latency, queue depth | Gần đầy, throttling, p99 I/O tăng |
| CSI/node | Attach/detach error, mount timeout, node condition, driver health | Pod Pending, volume stuck, lỗi node plugin |
| Database/engine | Replication lag, quorum, leader changes, WAL/log growth, recovery time | Replica stale, split-brain, không commit được |
| Backup | Last successful backup, snapshot age, PITR log continuity, restore test | RPO bị vượt, backup không đọc/giải mã được |
| Queue/broker | Disk usage, unacked messages, segment retention, consumer lag | Message bị chặn, disk đầy, backlog tăng |

### Một số tình huống và cách phản ứng

**PVC Pending:** kiểm tra StorageClass, quota, CSI provisioner, binding mode, CIDR/zone topology và node selector. Đừng đổi storage class ngẫu nhiên vì có thể provision volume ở vị trí sai.

**Pod không mount được volume:** kiểm tra attach state, node plugin, quyền volume/filesystem, zone và event của PVC/PV. Không force mount khi node cũ có khả năng vẫn ghi.

**Volume gần đầy:** xác định dữ liệu tăng do log, WAL, index, temporary file hay retention; thực hiện cleanup theo hướng dẫn engine và mở rộng volume theo quy trình. Không xóa file dữ liệu/transaction log trực tiếp khi database đang chạy.

**I/O latency tăng:** kiểm tra queue depth, IOPS/throughput quota, kích thước I/O, burst credit, noisy neighbor, compaction và database query pattern. Tăng size volume chỉ có ích nếu performance tier gắn với size và đúng nút thắt.

**Replica lag hoặc mất quorum:** bảo vệ writer, xác định node còn sống, trạng thái WAL/log và dữ liệu đã xác nhận. Làm theo runbook của database/operator; không khởi động nhiều replica với dữ liệu cũ cùng vai trò writer.

**Backup lỗi liên tục:** kiểm tra quyền snapshot, storage quota, network, khóa mã hóa, log chain/PITR và trạng thái volume. Một backup job báo lỗi cần được xử lý trước khi chính sách RPO không còn được đáp ứng.

## 13. Quy trình backup và restore có thể diễn tập

Một chính sách backup tốt phải chuyển thành quy trình thao tác và bằng chứng phục hồi.

### Trước khi backup

1. Phân loại dữ liệu và xác định mức quan trọng, chủ sở hữu, RPO/RTO.
2. Xác định backup ở tầng storage, database-native hay kết hợp; đọc khuyến nghị của engine.
3. Xác định thời điểm checkpoint/quiesce hoặc log position nếu cần consistency.
4. Xác nhận dung lượng, quyền snapshot, key/encryption, retention và vị trí lưu.
5. Thiết kế cách phát hiện backup thất bại và cảnh báo nếu quá hạn.

### Khi restore

1. Tạo môi trường phục hồi tách biệt; không restore ghi đè production khi chưa có phê duyệt.
2. Chọn snapshot/backup và log phù hợp thời điểm mong muốn.
3. Provision volume hoặc database target, gắn đúng quyền và encryption key.
4. Thực hiện recovery theo engine: replay log, kiểm tra cluster metadata và khôi phục thứ tự.
5. Kiểm tra schema, checksum/integrity, số bản ghi, dữ liệu nghiệp vụ và khả năng đọc/ghi.
6. Đo thời gian phục hồi và lượng dữ liệu bị mất so với RTO/RPO.
7. Ghi kết quả, cập nhật runbook và khắc phục những bước không đạt.

### Restore test quan trọng hơn chỉ đếm backup thành công

Backup có thể tồn tại nhưng không restore được do key bị thu hồi, metadata thiếu, log chain đứt, phiên bản engine không tương thích hoặc quyền truy cập sai. Vì thế, cần diễn tập restore định kỳ và kiểm tra **ứng dụng sử dụng được dữ liệu**, không chỉ xác nhận volume đã tạo.

## 14. Nâng cấp stateful workload và schema dữ liệu

Container image mới có thể thay thế pod nhanh, nhưng database schema và format trên disk có thể **không tương thích ngược**. Rolling update một StatefulSet trong khi các node dùng version khác nhau có nguy cơ gây lỗi cluster hoặc không thể rollback.

Trước khi nâng cấp:

- Đọc compatibility matrix giữa engine version, operator, CSI driver và storage format.
- Backup và diễn tập restore theo phiên bản đích.
- Xác minh replication protocol và upgrade order của leader/follower.
- Dành thời gian cho migration hoặc compaction; không mặc định chỉ restart pod.
- Cấu hình update strategy phù hợp; có thể cần partitioned rollout hoặc quy trình do operator điều phối.
- Kiểm tra health, quorum, lag và dữ liệu sau từng bước.

### Expand–migrate–contract cho schema

1. **Expand:** thêm trường/index/cấu trúc mới mà version hiện tại còn tương thích.
2. **Migrate:** cập nhật ứng dụng để đọc/ghi theo cấu trúc chuyển tiếp; backfill từng lô.
3. **Validate:** đối soát dữ liệu và đo lỗi.
4. **Contract:** bỏ cấu trúc cũ sau khi không còn consumer/phiên bản cũ dùng.

Đây là cách giảm rủi ro deploy đồng thời khi nhiều pod còn chạy phiên bản khác nhau. Nhưng migration dữ liệu lớn có thể làm tăng I/O và thời gian lock; cần benchmark trên dữ liệu gần production.

## 15. Case study: database PostgreSQL containerized cho ứng dụng đặt lịch

Giả sử một nền tảng đặt lịch cần lưu booking và payment reference. Nhóm vận hành muốn chạy PostgreSQL trong Kubernetes để tiêu chuẩn hóa nền tảng; yêu cầu minh họa:

- Tải đọc/ghi tương đối ổn định; có các burst theo chiến dịch.
- Mục tiêu RPO gần 0 cho các giao dịch đã xác nhận trong phạm vi sự cố AZ được chọn.
- Có thể phục hồi ở region khác theo RTO/RPO đã thống nhất.
- Database cần block storage có IOPS ổn định.
- Không cho application pod truy cập volume trực tiếp; ứng dụng truy cập qua database protocol.

### Lựa chọn cấu trúc

Một phương án gồm ba database member, mỗi member có PVC block volume riêng; pod được phân bố qua ba AZ nếu cluster và region hỗ trợ; headless service phục vụ peer discovery, service riêng cung cấp endpoint writer/read theo vai trò. Database engine hoặc operator quản lý replication, leader election và failover. Backup logic/PITR được lưu ở vùng storage riêng và có bản sao theo yêu cầu DR.

Sơ đồ:

~~~mermaid
flowchart TB
    APP["Booking API pods"]
    WRITER["Writer endpoint / Service"]
    subgraph AZ1["AZ A"]
        DB0["PostgreSQL member 0"]
        VOL0["Block volume A"]
        DB0 --- VOL0
    end
    subgraph AZ2["AZ B"]
        DB1["PostgreSQL member 1"]
        VOL1["Block volume B"]
        DB1 --- VOL1
    end
    subgraph AZ3["AZ C"]
        DB2["PostgreSQL member 2"]
        VOL2["Block volume C"]
        DB2 --- VOL2
    end
    APP --> WRITER
    WRITER --> DB0
    DB0 <-->|"Replication protocol"| DB1
    DB1 <-->|"Replication protocol"| DB2
    DB0 <-->|"Replication protocol"| DB2
    BACKUP["Backup / PITR archive"]
    DB0 --> BACKUP
~~~

Sơ đồ là cấu trúc minh họa, **không phải cấu hình production-ready**. PostgreSQL tự thân không được triển khai thành ba pod chỉ bằng StatefulSet rồi mặc định có HA; cần phương án cluster/operator cụ thể, replication mode, witness/quorum, fencing, connection routing, backup và khả năng failover được kiểm thử. Với yêu cầu nghiêm ngặt, một managed database service có thể cung cấp các chức năng này với trách nhiệm vận hành thấp hơn; cần so sánh trước khi tự vận hành.

### Luồng ghi booking

Ứng dụng gọi writer endpoint bằng TLS và credential/identity có quyền tối thiểu. Database commit transaction theo durability setting phù hợp. Nếu dùng synchronous replication, cần xác định commit acknowledgement chờ replica nào và hành vi khi mất quorum; nếu asynchronous, phải định lượng replication lag và mất dữ liệu có thể xảy ra khi failover. API dùng idempotency key để xử lý request retry sau timeout.

### Khi mất pod writer

Operator hoặc database cluster manager phát hiện lỗi, đánh giá member còn lại và bầu/promote leader theo protocol. Service/endpoint writer đổi sang member mới; connection pool của API cần reconnect. Kiểm thử phải đo thời gian tới khi API ghi booking thành công và xác minh giao dịch đã xác nhận không mất hoặc bị nhân đôi.

### Khi mất AZ chứa volume của writer

Volume zonal ở AZ hỏng có thể không attach sang AZ khác. Cluster phải chọn replica còn đủ dữ liệu ở AZ khác, promote theo quy tắc, còn pod cũ phải được fencing để tránh writer cũ quay lại ghi. RPO thực tế phụ thuộc replication mode và commit acknowledgement. Volume mới không thể thay thế database replication.

### Khi hỏng dữ liệu logic hoặc xóa nhầm

Replica có thể sao chép thao tác xóa ngay lập tức. Đội vận hành chọn backup/PITR về thời điểm trước lỗi, restore vào cluster riêng, kiểm chứng giao dịch hợp lệ và xác định cách đối soát các giao dịch phát sinh sau điểm phục hồi. Đây là lý do replication và backup phải được thiết kế độc lập.

### Quyết định có nên tự chạy database trong Kubernetes?

Nên so sánh với managed database:

| Tiêu chí | Database tự vận hành trong Kubernetes | Managed database |
| --- | --- | --- |
| Quyền kiểm soát | Cao hơn về engine, extension, scheduling và storage layout | Phụ thuộc tính năng/giới hạn sản phẩm |
| Vận hành | Đội chịu trách nhiệm operator, version, backup, failover và on-call | Provider quản lý nhiều tác vụ hạ tầng; khách hàng vẫn quản lý schema, quyền và dữ liệu |
| Storage | Tự chọn CSI, topology, volume và policy | Storage/HA tích hợp theo dịch vụ |
| Tính linh hoạt | Có thể tùy biến sâu | Có thể giới hạn version, extension và quyền host |
| Rủi ro | Sai operator, PVC, quorum, restore hoặc upgrade có thể làm mất khả năng phục hồi | Phụ thuộc SLA, giới hạn, API và quy trình của provider |
| Tổng chi phí | Compute + storage + engineering/on-call + monitoring + backup | Service price + storage + transfer + backup + giới hạn phụ trợ |

Nếu đội chưa có kinh nghiệm vận hành database cluster, lợi ích dùng chung Kubernetes có thể không bù được rủi ro dữ liệu. Managed database thường đáng cân nhắc cho dữ liệu giao dịch quan trọng; tự vận hành phù hợp khi có yêu cầu kiểm soát đặc thù và năng lực chịu trách nhiệm end-to-end.

## 16. Di chuyển workload có trạng thái vào container

Container hóa stateful application phức tạp hơn đóng gói một API stateless vì dữ liệu, identity, networking và storage topology có thể gắn với host cũ.

### Bước 1 — Kiểm kê dữ liệu và dependency

Ghi lại data directory, log, cache, temp file, file cấu hình, secret, cổng mạng, volume hiện có, replication, backup và các cron/job tác động dữ liệu. Phân loại:

- Dữ liệu nghiệp vụ phải giữ.
- Dữ liệu có thể rebuild từ nguồn khác.
- Cache và file tạm có thể bỏ.
- Log cần retention hoặc chuyển sang logging platform.
- Metadata cluster/identity cần quy trình chuyển đổi riêng.

Không mount nguyên thư mục của máy chủ cũ vào container nếu chưa xác định ownership, quyền, mount option và filesystem semantics.

### Bước 2 — Chọn mô hình vận hành

Đánh giá managed database, operator được hỗ trợ hoặc self-managed StatefulSet. Xem xét SLA, extension, version, network, compliance, khả năng sao lưu, người trực, thời gian nâng cấp và kỹ năng cluster. StatefulSet không nên được coi là lựa chọn bắt buộc chỉ vì workload đang chạy trên Kubernetes.

### Bước 3 — Chuẩn hóa storage và security

Chọn block/file/object theo engine; cấu hình StorageClass, encryption, reclaim policy, topology, quota và volume size. Thiết lập service account, secret, security context, ingress/egress và backup target tách biệt.

### Bước 4 — Tạo môi trường kiểm thử gần production

Nạp dữ liệu đại diện, kiểm tra IOPS, throughput, latency, quyền truy cập, restart pod, node drain, reschedule, volume detach/attach, backup và restore. Xác nhận ứng dụng chạy cùng version engine và schema thực.

### Bước 5 — Đồng bộ dữ liệu và chuyển đổi

Phương án có thể là backup/restore, replication giữa nguồn cũ và mới hoặc migration theo batch. Định nghĩa cutover window, freeze write nếu cần, kiểm tra replication lag, đối soát số lượng/checksum và tiêu chí rollback. Đối với dữ liệu giao dịch, phải xác định nguồn sự thật trong từng giai đoạn và cách xử lý giao dịch trong cửa sổ chuyển đổi.

### Bước 6 — Cutover có thể quay lui

Chuyển traffic theo đợt hoặc cửa sổ kiểm soát, xác minh đọc/ghi và metric. Không cho phép hai nơi cùng nhận ghi trừ khi hệ thống được thiết kế multi-writer. Giữ nguồn cũ ở trạng thái có thể đối soát theo kế hoạch nhưng tránh tiếp tục nhận traffic ngoài ý muốn.

### Bước 7 — Vận hành sau chuyển đổi

Theo dõi storage, replica lag, quorum, backup, restore, latency, capacity và chi phí trong giai đoạn tăng cường quan sát. Cập nhật runbook, lịch trực, quy trình patch/upgrade và ownership.

## 17. Well-Architected: đánh giá theo nhiều trụ cột

| Trụ cột | Câu hỏi với stateful container | Bằng chứng cần có |
| --- | --- | --- |
| **Độ tin cậy** | Pod/node/AZ lỗi thì dữ liệu và writer được phục hồi thế nào? | Replication, fencing, RTO/RPO, restore/failover test |
| **Bảo mật** | Ai có quyền đọc volume, snapshot, backup và key? | IAM, encryption, audit, network policy, secret rotation |
| **Hiệu năng** | Storage có đáp ứng IOPS/throughput/p99 khi compaction và peak không? | Benchmark, storage telemetry, load test |
| **Tối ưu chi phí** | Volume provisioned, snapshot, replica, backup và egress có phù hợp không? | Cost per GB/IOPS/job, retention, capacity forecast |
| **Vận hành xuất sắc** | Ai chịu trách nhiệm patch, upgrade, backup, restore và xử lý volume stuck? | Runbook, alert, automation, owner, diễn tập |
| **Tính bền vững** | Dung lượng và replica có được sử dụng hiệu quả, tránh provision quá mức không? | Utilization, lifecycle, right-sizing và chính sách xóa an toàn |

Một kiến trúc có ba replica trên ba AZ không đủ nếu backup không restore được. Một volume IOPS cao không có ý nghĩa nếu database cấu hình sai fsync. Một operator tự động failover không đảm bảo tránh split-brain nếu cơ chế fencing chưa được kiểm chứng. Cần đánh giá **đầu cuối** từ ứng dụng tới dữ liệu và quy trình vận hành.

## 18. Những lỗi thường gặp

1. **Lưu dữ liệu chính trong writable layer của container:** container thay thế có thể làm mất dữ liệu.
2. **Cho rằng PVC đồng nghĩa backup:** volume còn bền nhưng vẫn có thể bị xóa nhầm, corruption hoặc ransomware.
3. **Cho rằng StatefulSet tự replication:** StatefulSet chỉ điều phối identity/storage association; engine/operator phải đảm nhiệm protocol dữ liệu.
4. **Nhầm RWO với một pod:** semantics thường là một node; phải phân biệt với RWOP và kiểm tra CSI.
5. **Coi RWX là nhiều writer an toàn:** file locking và logic đồng thời vẫn do ứng dụng/filesystem xử lý.
6. **Đặt volume zonal sai vị trí:** pod được scheduler đặt ở AZ không thể attach volume.
7. **Cùng một block volume cho nhiều database replica:** có thể gây split-brain và corruption nếu không có kiến trúc cluster/filesystem hỗ trợ.
8. **Scale pod mà không tính storage/network:** thêm replica làm tăng IOPS, connection, replication traffic và chi phí.
9. **Không đo latency storage:** thiếu IOPS hoặc tăng queue depth có thể kéo p99 database lên dù CPU thấp.
10. **Chụp snapshot khi database không nhất quán:** snapshot tồn tại nhưng database không recovery được.
11. **Xóa PVC để dọn tài nguyên:** có thể kích hoạt reclaim policy xóa luôn backend volume.
12. **Force detach khi node cũ chưa được fencing:** hai writer có thể truy cập cùng dữ liệu.
13. **Không diễn tập restore:** backup job xanh chưa chứng minh dữ liệu khôi phục được.
14. **Nâng cấp engine cùng lúc với thay storage:** thay nhiều biến trong một release làm khó rollback và tìm nguyên nhân.

## 19. Bài tập thực hành và đáp án định hướng

Một nhóm triển khai Redis và PostgreSQL trên Kubernetes:

- PostgreSQL có 500 GiB dữ liệu, yêu cầu ghi bền vững và RPO tối đa 5 phút trong kịch bản mất một AZ.
- Redis được dùng làm cache có thể tái tạo, dữ liệu cache không phải nguồn sự thật.
- PostgreSQL cần tối thiểu 8.000 IOPS và độ trễ ghi thấp.
- Có ba AZ; đội ứng dụng muốn tạo ba replica database với StatefulSet.
- Backup phải giữ 30 ngày và có thể khôi phục trong 60 phút.

### Câu 1 — Cái nào cần persistent volume?

**Đáp án định hướng:** PostgreSQL cần storage bền vững, thường là block volume hoặc managed database storage theo hướng dẫn engine. Redis cache có thể dùng ephemeral memory nếu chấp nhận mất cache và có thể rebuild; nếu Redis chứa queue/session/dữ liệu không thể tái tạo thì phải thiết kế persistence/HA riêng theo vai trò thực tế.

### Câu 2 — Có thể gắn một PVC RWO cho cả ba PostgreSQL pod không?

**Đáp án:** Không nên. Thiết kế thông thường là mỗi database member có storage riêng, sau đó engine replication dữ liệu giữa các member. RWO không phải cơ chế phân phối bản ghi và không làm database tự đồng bộ.

### Câu 3 — Ba pod StatefulSet đã bảo đảm RPO 5 phút chưa?

**Đáp án:** Chưa. Phải chọn replication mode và commit acknowledgement phù hợp, kiểm tra replication lag, quorum, failover, fencing và dữ liệu đã xác nhận. Cần thử mất AZ và đo mức mất dữ liệu. StatefulSet chỉ cung cấp điều phối pod/volume identity.

### Câu 4 — Storage tối thiểu phải benchmark gì?

**Đáp án:** 8.000 IOPS tại kích thước I/O đại diện, throughput, latency p95/p99, read/write ratio, fsync, queue depth, burst behavior và hiệu năng khi backup/compaction đồng thời. Cần kiểm tra capacity và headroom cho WAL, index, temporary space.

### Câu 5 — Snapshot volume mỗi ngày đã đáp ứng retention 30 ngày và restore trong 60 phút chưa?

**Đáp án:** Chưa thể kết luận. Cần xác định snapshot consistency, số bản giữ, log/PITR cần thiết, vùng lưu, key, dung lượng restore và thời gian dựng database/kiểm tra. Có thể cần database-native backup hoặc phối hợp snapshot và log; phải diễn tập restore đo thực tế.

### Câu 6 — Pod PostgreSQL-0 bị lỗi node, scheduler muốn tạo pod ở AZ khác. Cần kiểm tra điều gì?

**Đáp án:** Volume có topology zonal hay không, node cũ đã fencing/detach an toàn chưa, volume có attach được ở AZ mới không, PVC binding mode và scheduler constraints. Nếu volume không thể di chuyển, cluster cần failover sang replica có volume riêng ở AZ khác theo protocol của engine.

### Câu 7 — Xóa PVC có an toàn để làm sạch môi trường staging không?

**Đáp án:** Phải kiểm tra reclaim policy, PV/backend volume, ownerReference, snapshot và mục đích dữ liệu. Nếu policy Delete, xóa PVC có thể dẫn đến xóa backend. Dữ liệu cần giữ phải backup hoặc chuyển giao theo quy trình trước khi xóa.

### Câu 8 — Khi nào nên chọn managed database thay vì chạy PostgreSQL bằng StatefulSet?

**Đáp án định hướng:** Khi tổ chức không có năng lực trực vận hành database cluster, yêu cầu HA/backup/restore cao và managed service đáp ứng engine/version/network/compliance, managed database có thể giảm rủi ro và công sức. Self-managed có thể phù hợp nếu có yêu cầu tùy chỉnh sâu và đội đã chứng minh năng lực vận hành end-to-end.

## 20. Checklist review trước khi đưa stateful container vào production

- Đã xác định rõ dữ liệu nào ephemeral, dữ liệu nào persistent và nguồn sự thật nằm ở đâu?
- Loại storage block/file/object phù hợp với access pattern và engine chưa?
- PV/PVC/StorageClass/CSI driver có đáp ứng access mode, topology, resize và quota không?
- StatefulSet/operator có cung cấp đúng identity và protocol; đã kiểm thử quorum/fencing chưa?
- Pod/volume có được phân bố theo failure domain và năng lực còn lại khi mất AZ không?
- IOPS, throughput, latency, capacity growth và headroom đã benchmark chưa?
- Encryption, key policy, workload identity, security context và audit đã được cấu hình chưa?
- Backup, snapshot, retention, PITR và restore test đáp ứng RPO/RTO chưa?
- Có runbook cho PVC Pending, attach/detach stuck, volume full, replica lag và restore không?
- Upgrade, schema migration, rollback và cutover đã được thử nghiệm chưa?
- Chi phí volume provisioned, replica, snapshot, backup, transfer và vận hành đã được tính chưa?
- Có owner, dashboard, cảnh báo và lịch diễn tập định kỳ không?

Một thiết kế stateful container tốt không chỉ chứng minh pod chạy và volume mount thành công. Nó phải chứng minh dữ liệu **đúng, bền vững, được bảo vệ, phục hồi được trong mục tiêu và có thể vận hành qua các tình huống lỗi thực tế**.
