# Vận hành container/Kubernetes và lưu trữ bền vững theo điều kiện môi trường

> **Chương:** Tự động hóa vận hành  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Bối cảnh:** Apache Cassandra là cơ sở dữ liệu phân tán dạng wide-column, đặt dữ liệu theo partition key/token, replication factor và DC/rack. Khi chạy trong container hay Kubernetes, cần nối đúng topology, đĩa bền vững, consistency level, compaction/repair, backup và các ứng dụng Java dùng CQL.  
> **Trọng tâm:** Chọn cách triển khai và vận hành **phụ thuộc môi trường** (laptop, CI, staging, production; VM, local disk, cloud block storage, multi-zone), không giả định một manifest Kubernetes chạy đúng ở mọi cluster.

## 1. Tình huống: pod tự hồi phục nhưng dữ liệu có thật sự an toàn?

Một dịch vụ Java ghi sự kiện theo tenant vào Cassandra. Cụm được chuyển từ máy ảo sang Kubernetes. Sau một đợt cập nhật node pool:

- Các pod Cassandra bị hủy và được tạo lại, mỗi pod lại có IP mới.
- Một pod mới được gắn volume rỗng vì PVC không được tái sử dụng đúng.
- Hai replica còn lại tiếp tục đáp ứng **LOCAL_QUORUM** nên API chưa báo lỗi ngay.
- Operator tưởng Kubernetes đã “tự phục hồi” vì mọi pod lại ở trạng thái Running.
- Một ngày sau, có request timeout, repair/streaming tăng tải và thiếu dữ liệu được phát hiện ở một luồng đọc khác.

Lỗi gốc có thể không nằm ở CQL. Nó có thể nằm ở **identity của node, dữ liệu bền vững trên volume, topology/replica placement, quy trình node replacement hoặc automation cấp cluster**.

**Kubernetes quản lý vòng đời container, không tự bảo đảm toàn bộ ngữ nghĩa phân tán của Cassandra.** Một pod Running hoặc một PersistentVolume Bound không chứng minh token ownership, SSTable, commitlog, repair, CL, backup và data correctness đã đạt yêu cầu.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **container filesystem**, **emptyDir**, **PersistentVolume/PersistentVolumeClaim** và **backup ngoài miền lỗi**.
2. Chọn giữa **Docker/Compose cho lab**, **StatefulSet tự quản**, **Cassandra operator** và mô hình VM/bare metal.
3. Thiết kế **StorageClass/CSI, volume binding và topology (zone/rack/DC)** phù hợp với phần cứng và RPO/RTO.
4. Giữ ổn định **node identity, volume identity, seed/discovery, RF/DC/rack**, không thay Cassandra node như một pod stateless.
5. Định nghĩa **startup/readiness/liveness, PodDisruptionBudget, termination grace và rollout** không tạo restart storm/mất quorum.
6. Đặt **requests/limits, disk headroom, cgroup/JVM heap, off-heap, page cache và I/O telemetry** phù hợp.
7. Phân biệt **restart pod**, **replace node**, **rebuild/repair**, **snapshot** và **restore backup**.
8. Kết nối từ **Java Driver 4.x** bằng local DC, contact points, TLS/auth và CL đúng hợp đồng.
9. Thiết kế runbook cho PVC Pending, volume không mount được, pod CrashLoop, zone failure, disk full và upgrade.
10. Kiểm thử an toàn trên staging và ra quyết định GO/PAUSE/STOP bằng bằng chứng.

> **Cảnh báo vận hành:** Ví dụ lab chỉ nhằm giải thích cấu hình. Không áp dụng trực tiếp StatefulSet mẫu, xóa PVC/PV, scale Cassandra, force-delete pod, thay StorageClass/volume topology, chạy repair/rebuild hay đổi RF trong production. Những thao tác này cần Cassandra operator/runbook, owner, backup được kiểm chứng và change approval.

## 2. Ba tầng bền vững: Cassandra, Kubernetes và storage

~~~mermaid
flowchart TD
    A["Ứng dụng Java\nCQL + CL + routing key"] --> B["Cassandra node\ncoordinator / replica"]
    B --> C["Memtable + Commitlog"]
    B --> D["SSTables + compaction"]
    C --> E["Container mount"]
    D --> E
    E --> F{"Persistent storage?"}
    F -->|ephemeral| G["emptyDir/container layer\ncó thể mất khi pod bị thay"]
    F -->|PVC/PV/CSI| H["Volume gắn với node identity\nphụ thuộc storage backend"]
    H --> I["Storage fault domain\nnode / rack / zone / region"]
    H --> J["Snapshots + off-domain backup\nmanifest + restore drill"]
~~~

### 2.1. Mô hình dữ liệu Cassandra

Cassandra thường nhận mutation qua coordinator và phân phối tới các replica sở hữu token range theo partition key. Với **NetworkTopologyStrategy**, RF cấu hình theo DC; ví dụ **RF=3 trong dc1** và **LOCAL_QUORUM** thường cần phản hồi phù hợp từ **hai trong ba** replica local.

Một replica có SSTables và commitlog riêng. Thông tin placement/token, schema, repaired SSTables, compaction và trạng thái replication đều ảnh hưởng khôi phục. **RF=3 giúp dung thứ một số lỗi replica, nhưng không phải ba bản backup độc lập**.

### 2.2. Mô hình storage Kubernetes

- **Container writable layer:** tạm thời; thay container hoặc pod không phải một cơ chế lưu dữ liệu tin cậy.
- **emptyDir:** tồn tại cùng vòng đời **Pod**; có thể tồn tại qua container restart trong cùng Pod nhưng bị xóa khi Pod bị xóa/evicted.
- **PersistentVolume (PV):** tài nguyên volume được cấp hoặc quản lý trong cluster.
- **PersistentVolumeClaim (PVC):** yêu cầu lưu trữ của workload; PVC có thể được gắn với PV qua storage provisioning/binding.
- **StorageClass/CSI:** mô tả driver, cách provision, binding, expansion, reclaim và topology tùy backend.
- **VolumeSnapshot:** snapshot ở tầng storage khi CSI/snapshot controller hỗ trợ; **không tự chứng minh snapshot Cassandra nhất quán toàn cụm**.
- **Backup:** bản sao được xác minh, lưu ngoài fault domain phù hợp và có thể restore với RPO/RTO đã đo.

**Bound PVC không có nghĩa “dữ liệu sẽ không bao giờ mất”.** Backend có thể có lỗi volume, zone outage, provisioning sai, security/mount issue, silent corruption hoặc người vận hành xóa nhầm. Cần thiết kế fault domain và backup riêng.

### 2.3. Tập dữ liệu bắt buộc phải được giữ đúng

Trong một Cassandra image, đường dẫn data/config phụ thuộc packaging. Với **official Docker image** thường gặp thư mục dữ liệu **/var/lib/cassandra**; những bản dựng hoặc operator khác có thể dùng đường dẫn khác và tách data/commitlog/hints. Hãy xác minh bằng effective config thực tế:

| Loại dữ liệu | Vai trò | Sai lầm thường gặp |
|---|---|---|
| **SSTables / data directories** | Dữ liệu đã được flush | Mount PVC sai path để SSTables nằm ở container layer |
| **Commitlog** | Durability cho mutations gần đây | Để ở ephemeral storage mà không hiểu mất dữ liệu khi node crash |
| **Hints** | Ghi nhận một số mutation cần gửi tới replica sau | Nhầm hints với backup/repair hoàn chỉnh |
| **Saved caches** | Một số dữ liệu có thể được tái tạo | Dành quá nhiều dung lượng hoặc nghĩ có cache thì dữ liệu gốc an toàn |
| **Snapshots/incremental backups** | Recovery points theo cơ chế backup | Coi snapshot local là bản sao off-domain |
| **Config, certificates, secrets** | Node identity, DC/rack, TLS/auth | Đổi config khi image/pod thay mà không có kiểm soát |

Không áp dụng câu “mount một PVC là đủ” nếu image đã cấu hình data, commitlog và hints trên các đường dẫn khác nhau. Ngược lại, không tự tách nhiều volume khi chưa biết khả năng IOPS, mount/repair/restore của operator.

## 3. Môi trường quyết định giải pháp, không phải ngược lại

| Môi trường | Ưu tiên | Được chấp nhận | Không được tuyên bố |
|---|---|---|---|
| **Laptop/dev** | Lặp lại CQL/Java nhanh, dữ liệu tổng hợp | Docker/Compose single node, volume local hoặc ephemeral có chủ đích | Đã kiểm chứng RF3/HA/multi-zone |
| **CI integration** | Reproducible test, reset sạch | Testcontainers/container dùng dữ liệu ngắn hạn | Có backup/repair production-grade |
| **Staging** | Gần giống topology, disk/network, maintenance | Operator/StatefulSet, PVC/CSI, RF/DC, fault tests có approval | Production chắc chắn tương tự |
| **Production single-region** | HA theo zone/rack, recovery | Operator hỗ trợ Cassandra version, persistent disks và external backup | Kubernetes reschedule tự sửa mọi lỗi dữ liệu |
| **Production multi-DC** | Locality, WAN, data residency và DR | NTS RF per-DC, DC/rack placement, quy trình streaming/repair được kiểm soát | LOCAL_QUORUM một DC bảo đảm đã đồng bộ mọi DC |
| **VM/bare metal** | I/O tối ưu, quyền kiểm soát host/disk | SSD/NVMe và node lifecycle thủ công/automation phù hợp | Chạy Kubernetes luôn tốt hơn |

Một cluster nhỏ trên một máy duy nhất có thể dùng **RF=1** cho lab. Nhưng một bài test RF1 **không chứng minh** quorum, unavailable, repair hoặc lỗi zone. Không bê kết luận single-node sang production phân tán.

### 3.1. Bộ câu hỏi chọn môi trường

1. RPO/RTO và data retention được phê duyệt là gì?
2. Cassandra version, image/operator/CSI/Kubernetes version có tương thích không?
3. Có bao nhiêu **DC, rack/zone**, RF từng DC và mức lỗi phải chịu?
4. Data size, growth rate, hot partitions, read/write p99 và compaction backlog hiện tại?
5. Storage backend là **cloud block SSD**, local PV NVMe, SAN hay loại khác? Latency/IOPS và zone affinity?
6. Pod có được reschedule sang node/zone mới trong fault mà vẫn mount lại volume không?
7. Backup off-domain/restore drill và encryption/KMS đã hoạt động chưa?
8. Có giới hạn eviction, node drain, upgrade window, PodDisruptionBudget và change ownership?
9. Java Driver chạy cùng cluster, ngoài Kubernetes hay qua managed service/proxy?
10. Ai chịu trách nhiệm khi pod Running nhưng Cassandra chưa JOIN/NORMAL hoặc PVC Mount lỗi?

## 4. Docker và Compose: tốt cho học nhưng không thay production

### 4.1. Chạy lab với volume rõ ràng

Ví dụ Docker Compose một node với data directory phổ biến của official image:

~~~yaml
services:
  cassandra:
    image: cassandra:5.0 # Lab; production pin digest và version tương thích
    container_name: cassandra-lab
    environment:
      CASSANDRA_CLUSTER_NAME: cassandra-lab
      CASSANDRA_DC: dc1
      CASSANDRA_RACK: rack1
    ports:
      - "127.0.0.1:9042:9042"
    volumes:
      - cassandra_lab_data:/var/lib/cassandra
    restart: unless-stopped

volumes:
  cassandra_lab_data:
~~~

**Giải thích:**

- **Named volume** giữ dữ liệu qua container recreation nếu không bị xóa; đây vẫn là storage ở host Docker, không phải offsite backup.
- Bind port vào **127.0.0.1** cho lab, tránh mở native protocol ra toàn mạng.
- Environment variables phụ thuộc **image**. Không giả định image khác hỗ trợ cùng tên hoặc default.
- Không cấu hình authentication/TLS ở ví dụ để đơn giản hóa; **không dùng cấu hình này để cung cấp CQL cho môi trường không tin cậy**.
- Không dùng **docker compose down -v** nếu muốn giữ volume; cờ xóa volume có thể phá dữ liệu lab.
- Container health và startup Cassandra có thể mất thời gian; Running không đồng nghĩa CQL listener đã sẵn sàng.

### 4.2. Hỏng/khôi phục một container khác với mất node phân tán

- **Container restart:** container có thể dùng lại volume, Cassandra replay commitlog và phục hồi service.
- **Container remove + recreate:** nếu volume mount đúng, dữ liệu vẫn có thể được giữ; nếu dùng layer ephemeral, data mất.
- **Docker host mất disk:** named volume cùng host không bảo vệ khỏi lỗi vật lý host.
- **Compose multi-node trên một host:** có thể mô phỏng protocol/quorum nhất định, nhưng không mô phỏng rack/zone failure thật.
- **Docker Desktop/WSL filesystem:** I/O, memory cgroup và networking có thể khác Linux production đáng kể.

Thực hành Docker chỉ nên tạo **dữ liệu thử, bảng thử** và giả lập các trường hợp nhỏ. Với repair, node replacement, disk fault và HA cần staging cluster có tính đại diện.

## 5. Vì sao Cassandra cần StatefulSet hoặc operator?

Deployment stateless cho phép pod đổi danh tính dễ dàng. Cassandra cần node identity và data directory gắn với vị trí/replica ownership, nên Kubernetes thường dùng **StatefulSet** hoặc **Cassandra-aware operator**.

### 5.1. StatefulSet cung cấp gì?

- **Pod names cố định theo ordinal:** ví dụ cassandra-0, cassandra-1.
- **PVC riêng cho từng pod** thông qua volumeClaimTemplates.
- **Stable network identity** khi kết hợp headless Service.
- Có cơ chế rollout/update ordering và policy giữ/xóa PVC theo cấu hình/version.
- Kubernetes vẫn không tự hiểu **token ring, seed membership, RF, repair, rebuild hoặc safe node replacement**.

### 5.2. Operator bổ sung gì?

Một Cassandra-aware operator được hỗ trợ có thể điều phối bootstrap, topology, rack placement, rolling upgrade, scaling, backup integration, restore/replacement và repair hooks theo khả năng thực tế của sản phẩm. Nhưng **có operator không thay thế runbook và verification**.

| Tầng | Kubernetes/StatefulSet | Cassandra operator/runbook |
|---|---|---|
| Pod scheduling/PVC bind | Có cơ chế chuẩn Kubernetes | Có thể đặt policy theo zone/rack |
| Token ring, seed/discovery | Không hiểu ngữ nghĩa đầy đủ | Cần operator/config dành cho Cassandra |
| RF, DC/rack và CL | Không tự chọn | Phải được thiết kế và kiểm chứng |
| Node bootstrap/replace | Tạo container/PVC | Có logic phối hợp Cassandra theo version |
| Readiness/downtime | Probes và Pod status | Cần hiểu gossip/native protocol/topology |
| Safe scaling/upgrade | Rollout primitives | Cần thứ tự an toàn, streaming, repair, rollback |
| Backup/restore | Volume/storage primitives | Cần snapshot/manifest/commitlog và restore plan |
| Repair/tombstone coverage | Không tự làm anti-entropy | Operator/service có cơ chế riêng, phải xác minh |

**Khuyến nghị thiết kế:** Với production đa node, ưu tiên operator Cassandra được tổ chức hỗ trợ và kiểm thử theo ma trận **Kubernetes + CSI + Cassandra + JDK + Java Driver**. Dùng StatefulSet tự quản chỉ khi đội có năng lực vận hành Cassandra, runbook và nghiệm thu HA/backup/repair phù hợp.
## 6. Kubernetes lab: Headless Service và StatefulSet một node

Đoạn manifest sau **chỉ minh họa single-node lab**. Nó không tạo một cụm Cassandra an toàn cho production: thiếu authentication/TLS, topology multi-rack, backup, operator, HA, policy repair, và chưa kiểm tra tương thích CSI/image thực. Không tăng replicas lên 3 bằng cách đổi một con số rồi kết luận có cluster production.

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: cassandra-headless
  namespace: cassandra-lab
spec:
  clusterIP: None
  publishNotReadyAddresses: true
  selector:
    app: cassandra-lab
  ports:
    - name: cql
      port: 9042
      targetPort: 9042
    - name: internode
      port: 7000
      targetPort: 7000
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: cassandra
  namespace: cassandra-lab
spec:
  serviceName: cassandra-headless
  replicas: 1
  selector:
    matchLabels:
      app: cassandra-lab
  template:
    metadata:
      labels:
        app: cassandra-lab
    spec:
      terminationGracePeriodSeconds: 180
      containers:
        - name: cassandra
          image: cassandra:5.0 # Lab only; pin/verify exact version
          env:
            - name: CASSANDRA_CLUSTER_NAME
              value: cassandra-k8s-lab
            - name: CASSANDRA_DC
              value: dc1
            - name: CASSANDRA_RACK
              value: rack1
          ports:
            - containerPort: 9042
              name: cql
            - containerPort: 7000
              name: internode
          resources:
            requests:
              cpu: "1"
              memory: 3Gi
            limits:
              memory: 5Gi
          startupProbe:
            tcpSocket:
              port: cql
            periodSeconds: 10
            failureThreshold: 60
          readinessProbe:
            tcpSocket:
              port: cql
            periodSeconds: 10
            failureThreshold: 3
          volumeMounts:
            - name: data
              mountPath: /var/lib/cassandra
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes:
          - ReadWriteOnce
        storageClassName: cassandra-lab-ssd
        resources:
          requests:
            storage: 50Gi
~~~

**Các điểm phải hiểu trước khi dùng:**

1. Namespace **cassandra-lab** và StorageClass **cassandra-lab-ssd** phải được tạo bởi người có quyền, phù hợp CSI/backend; chúng là **tên ví dụ**, không giả định có sẵn.
2. StatefulSet một pod dùng PVC tên dạng **data-cassandra-0** (theo tên template/pod). Không đổi tên StatefulSet, ordinal hay volume template khi mong tái sử dụng dữ liệu mà không có kế hoạch migration.
3. **publishNotReadyAddresses** có thể hỗ trợ discovery trước khi Cassandra ready, nhưng không làm cluster khỏe. Phải hiểu DNS, địa chỉ broadcast/listen và service behavior.
4. **tcpSocket 9042** chỉ chứng minh một cổng nhận TCP, **không chứng minh CQL auth, schema agreement, node NORMAL hoặc dữ liệu đúng**.
5. Bài cố ý **không đặt livenessProbe** vì kiểu liveness dựa trên thời gian phản hồi CQL có thể gây restart storm khi GC/repair quá tải. Production phải thiết kế probes theo operator đã được kiểm chứng.
6. Memory/CPU/storage trong ví dụ là **giá trị thử**, không phải cấu hình Cassandra production. Kiểm tra JVM heap, offheap, page cache, disk growth và OOMKilled.
7. Image env variables và data path ở đây dành cho dạng image tham chiếu, phải xác minh **entrypoint/effective cassandra.yaml**.
8. Single-node phù hợp học StatefulSet/PVC nhưng chỉ nên dùng **RF=1** và CL tương ứng trong lab. Không test LOCAL_QUORUM RF3 trên một node.
9. Manifest chưa định nghĩa cluster networking hoàn chỉnh, authentication/TLS, NetworkPolicy, security context, backups, operator hooks hoặc cross-zone behavior.

### 6.1. Khi nào cần operator CR thay vì StatefulSet thủ công?

Một Cassandra operator thường triển khai CRD riêng (ví dụ họ CassandraDatacenter trong một số hệ sinh thái), với schema và options thay đổi theo operator/version. **Không tự viết manifest CRD tưởng tượng để chạy production.** Luôn lấy CR schema được cài trên cluster và tài liệu của operator đã chọn, kiểm tra:

- Số nodes/racks/DC và seed discovery.
- Storage mount path, PVC template/reclaim behavior.
- Resource requests/limits và JVM tuning.
- Rolling upgrades, node replacement/scale policy.
- TLS/auth secrets, bootstrap health và probes.
- Backup/restore, repair, monitoring, maintenance windows.

Nếu một tùy chọn không được operator hỗ trợ, **không chọc sửa StatefulSet do operator quản lý trực tiếp**; có thể bị reconcile đè lại hoặc phá invariant của controller.

## 7. PersistentVolume, PVC và StorageClass: chọn đúng storage

### 7.1. Những thuộc tính cần review

| Thành phần | Câu hỏi | Rủi ro nếu sai |
|---|---|---|
| **StorageClass provisioner** | CSI driver nào tạo volume, phiên bản đã kiểm thử? | Mount fail, snapshot/resize không hoạt động |
| **volumeBindingMode** | Immediate hay WaitForFirstConsumer? | PV cấp sai zone, pod Pending không schedule được |
| **reclaimPolicy** | Delete hay Retain? | PVC bị xóa kéo theo volume hoặc để lại volume orphan |
| **allowVolumeExpansion** | Backend có hỗ trợ tăng dung lượng online/offline? | Disk gần full nhưng PVC không thể mở rộng như dự kiến |
| **accessModes** | RWO/RWOP/RWX hỗ trợ thực tế? | Mount conflict/attach một volume cho nhiều pod |
| **topology constraints** | Volume theo zone/node nào? | Pod không chuyển sang zone khác được dù còn tài nguyên |
| **Performance profile** | IOPS, throughput, p99 I/O, queue, latency, burst credits? | CQL p99 tăng dù CPU thấp |
| **Snapshot/backup** | CSI VolumeSnapshot hỗ trợ nhất quán mức nào? | Có bản snapshot nhưng không restore được Cassandra |
| **Encryption** | Encryption at rest, key rotation và quản trị KMS? | Vi phạm chính sách hoặc không mount sau key issues |

### 7.2. WaitForFirstConsumer và topology

Một StorageClass có thể dùng **volumeBindingMode: WaitForFirstConsumer** để lựa chọn volume/backend cùng zone phù hợp với Pod scheduling. Ví dụ khái niệm:

~~~yaml
# CHỈ MINH HỌA schema; provisioner phải là tên CSI thực.
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: cassandra-lab-ssd
provisioner: example.csi.driver.invalid
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Retain
allowVolumeExpansion: true
parameters:
  storageTier: ssd
~~~

**Không apply** ví dụ này: provisioner và parameter **không có thật**. Nó chỉ minh họa những trường cần kiểm tra. StorageClass thật có thể không hỗ trợ một số tùy chọn hoặc yêu cầu key khác, tùy CSI/cloud.

**Immediate binding** có thể cấp volume trước khi scheduler biết Pod cần đặt ở đâu. Với volume zone-bound, nếu pod affinity/rack không khớp zone của volume, pod có thể Pending. **WaitForFirstConsumer** giúp gắn quyết định vào scheduling, nhưng **không làm một volume zone-A có thể tự di chuyển sang zone-B** sau khi đã được tạo.

### 7.3. Access modes: RWO không phải backup hay fencing

- **ReadWriteOnce (RWO):** cho phép volume mount đọc/ghi theo semantics của storage/Kubernetes, thường giới hạn theo node; **không phải distributed lock bảo vệ Cassandra node identity**. Có thể có nhiều pod trên một node cùng dùng RWO trong một số tình huống.
- **ReadWriteOncePod (RWOP):** bảo đảm một pod dùng PVC tại một thời điểm trong các điều kiện/version/CSI hỗ trợ; vẫn phải kiểm soát detach/attach và node replace.
- **ReadWriteMany (RWX):** nếu backend hỗ trợ, cũng **không có nghĩa nên cho nhiều Cassandra pods dùng chung một data directory**.
- **ReadOnlyMany:** không dùng như nơi ghi SSTables/commitlog.

**Mỗi Cassandra node phải sở hữu data directory phù hợp riêng.** Hai Cassandra processes ghi chung cùng thư mục dữ liệu có thể phá dữ liệu; RWX không biến Cassandra thành shared-disk database.

### 7.4. ReclaimPolicy và PVC retention

Khi người vận hành xóa StatefulSet, PVC có thể còn được giữ tùy cấu hình/default và version. Khi xóa **PVC**, PV có **reclaimPolicy: Delete** có thể khiến backend volume bị xóa. Với **Retain**, volume vẫn cần quy trình cleanup/mapping và có thể thành orphan.

Một số Kubernetes version hỗ trợ **persistentVolumeClaimRetentionPolicy** của StatefulSet để điều khiển giữ/xóa PVC theo scale/delete. **Không giả định default hoặc tính năng tồn tại giống nhau trên mọi cluster.**

Hành động nguy hiểm:

~~~text
kubectl delete pvc data-cassandra-0
# KHÔNG CHẠY trong production chỉ để "reset pod".
# Có thể làm mất data volume, phụ thuộc reclaim policy.
~~~

**Xóa Pod** khác **xóa PVC**; **scale down** khác **decommission Cassandra node**; **delete StatefulSet** khác **xóa cluster data**. Mỗi trường hợp phải xác minh chính sách giữ dữ liệu và recovery.

### 7.5. Local PV và cloud block disk

| Kiểu | Ưu điểm | Trade-off |
|---|---|---|
| **Local NVMe/PV** | IOPS/latency tốt, kiểm soát phần cứng | PV gắn node; node vật lý mất có thể mất dữ liệu cục bộ, cần replace/rebuild |
| **Cloud zonal block** | PVC có thể reattach trong cùng zone, có CSI snapshots | Volume zone-bound, attach latency và giới hạn IOPS/throughput, chi phí |
| **Network block/SAN** | Có backend replication tùy sản phẩm, abstraction tập trung | Tail latency/availability phụ thuộc mạng/storage service |
| **Object storage** | Thích hợp backup/manifest/archive | Không mặc định mount object bucket làm data directory Cassandra |
| **Container layer/emptyDir** | Nhanh cho lab, tự dọn | Không phù hợp lưu SSTables/commitlog bền vững |

**Storage volume replication** và **Cassandra RF** là hai lớp khác nhau; nếu cùng phụ thuộc một backend/zone, chúng có thể có **correlated failure**. Thiết kế zone/rack phải dựa vào fault domains thực, không chỉ số copies.

## 8. Topology: DC, rack, zone và placement

Trong Cassandra, **DC/rack** là khái niệm placement/replication; trong Kubernetes có **nodes, labels, zones, affinity, topology spread**. Phải nối chúng một cách đúng đắn.

~~~mermaid
flowchart LR
    A["Cassandra keyspace\nNTS dc1 RF3"] --> B["Replica A\nrack/zone-a"]
    A --> C["Replica B\nrack/zone-b"]
    A --> D["Replica C\nrack/zone-c"]
    B --> E["PVC/PV A\nstorage zone-a"]
    C --> F["PVC/PV B\nstorage zone-b"]
    D --> G["PVC/PV C\nstorage zone-c"]
~~~

### 8.1. Không chỉ dựa vào podAntiAffinity

Pod anti-affinity giúp tránh đặt cùng nhóm pod trên một node nhưng không tự bảo đảm Cassandra rack mapping, replica placement và storage topology. Nếu ba pods nằm ở ba worker nodes nhưng **cùng zone**, mất zone vẫn có thể làm cả cụm unavailable.

Cần kiểm tra:

- Node labels như topology.kubernetes.io/zone/region và chính sách scheduling thực tế.
- Cassandra DC/rack settings khớp topology failure domains được chọn.
- Có đủ **số zones/nodes** cho policy; hard anti-affinity có thể làm pod Pending nếu capacity không đủ.
- StorageClass/PV nodeAffinity có xung đột với placement không.
- Operator quản lý rack placement như thế nào và xử lý node replacement ra sao.

### 8.2. Một ví dụ ràng buộc scheduling

~~~yaml
# FRAGMENT minh họa; chưa phải cấu hình production hoàn chỉnh.
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app: cassandra-lab
          topologyKey: kubernetes.io/hostname
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: ScheduleAnyway
    labelSelector:
      matchLabels:
        app: cassandra-lab
~~~

**Preferred/ScheduleAnyway** không bảo đảm tách zone nếu resource thiếu. Nếu dùng **required/DoNotSchedule**, pod có thể Pending khi cluster không đủ zone. Trong production, policy phải cân bằng **hard fault-domain requirements, PVC availability và khả năng scheduler đặt Pod**.

### 8.3. Một lỗi zone không đồng nghĩa Kubernetes tự chữa dữ liệu

Với zonal PV, Pod gắn PV zone-A không thể đơn giản được schedule sang zone-B nếu volume không attach được. Nếu node/volume thật sự mất, việc tạo volume mới là **node replacement/rebuild** của Cassandra, có streaming và thay dữ liệu trên token ranges liên quan; không được xem là pod restart thường.

**RF3/LOCAL_QUORUM** có thể chịu một số lỗi replica nếu các replica khác đủ khỏe, nhưng nếu mỗi rack/zone không có đủ placement, một zone outage có thể làm mất quorum. Cần chạy test fault staging theo RF/DC thật và đo request p99/error, không chỉ test Pod Ready.

## 9. Network: stable names, discovery và CQL routing

Cassandra cần các địa chỉ và cổng khác nhau cho client CQL, internode communication và management. Các port phổ biến, **tùy version/cấu hình**, gồm:

| Kết nối | Cổng phổ biến | Lưu ý |
|---|---:|---|
| **CQL native transport** | 9042 | Java Driver, TLS/auth, service discovery |
| **Internode communication** | 7000 | Không suy TLS internode tự bật |
| **Internode TLS** | 7001 | Cách cấu hình có thể thay đổi theo version |
| **JMX management** | 7199 | Hạn chế truy cập nghiêm ngặt, có thể có remote auth/TLS |
| **Metrics/sidecar** | Tùy hệ thống | Không tự public trên internet |

**Không đưa internode/JMX ra một LoadBalancer công khai.** NetworkPolicy/firewall phải phản ánh đúng luồng Pod–Pod, app–CQL, operator–management và backup/monitoring. Nếu internode không giao tiếp được, nodetool/CQL health một node không chứng minh ring khỏe.

### 9.1. Headless Service không thay seed configuration

Headless Service tạo DNS identity dạng Pod/Service có thể hỗ trợ Cassandra discovery, nhưng Cassandra vẫn cần seed provider, broadcast/listen addresses và network topology đúng cấu hình image/operator.

- Seed nodes không nên được chọn tùy tiện theo Pod IP ngắn hạn.
- Không coi headless DNS là danh sách mọi replica đã tham gia ring.
- Đừng đặt **localhost** làm broadcast address trong cluster đa node.
- Đừng để hai pod có cùng node identity/host ID hoặc cùng data directory vì sửa YAML sao chép.
- Kiểm tra DNS propagation, TTL và address translation qua mạng khác (client outside cluster).
- Khi pod IP đổi nhưng identity/volume được giữ, phải xác minh node join/gossip theo quy trình hỗ trợ.

### 9.2. Các kiểu service trong Kubernetes

- **Headless Service:** thường phục vụ stable per-pod DNS và discovery nội bộ.
- **ClusterIP Service:** có thể cung cấp một entrypoint cho ứng dụng nội bộ; nhưng driver token-aware cần nhìn thấy topology/discovered node addresses hợp lệ để route tối ưu.
- **LoadBalancer/Ingress:** không tự phù hợp với native Cassandra protocol. TCP proxy/LB/cloud-managed Cassandra có mô hình discovery/TLS khác nhau; phải dùng giải pháp được hỗ trợ, không tự đặt HTTP Ingress trước cổng 9042.
- **External clients:** cần giải pháp private network/TLS/auth và address translation/proxy nếu các Pod IP không routable. Không giả định contact point qua LB là đủ cho mọi node được driver khám phá.

### 9.3. Khi có NetworkPolicy

Phân tách tối thiểu:

1. Java clients được phép kết nối CQL endpoints dự định.
2. Cassandra nodes được phép giao tiếp internode đúng chiều/cổng.
3. Operator/monitoring có quyền management/JMX cần thiết, giới hạn danh tính.
4. Backup có đường ra storage/KMS và DNS tương ứng.
5. Kubernetes DNS/headless lookups không bị chặn.
6. Không expose database trực tiếp ra mạng công cộng.

Nếu deployment mới gây **AllNodesFailedException**, cần kiểm tra từng lỗi node (DNS/TCP/TLS/auth) và local DC; không lập tức tăng Java Driver timeout hoặc chạy repair.
## 10. CPU, heap, off-heap, page cache và cgroup memory

Cassandra dùng **JVM heap**, **off-heap/native memory**, file-system page cache và tài nguyên kernel. Cấu hình container memory không thể lấy bằng đúng -Xmx hay “container 4 GiB thì heap 4 GiB”.

### 10.1. Bộ nhớ có nhiều thành phần

| Thành phần | Vai trò | Nguy cơ |
|---|---|---|
| **Java heap** | Objects, memtable/metadata và workload JVM | Heap quá lớn làm GC/pause, quá nhỏ gây pressure |
| **Off-heap/native** | Buffers, mmap/direct allocations, threads và native libs | RSS vượt heap, bị OOMKilled |
| **Page cache** | Cache SSTable file pages | Thiếu RAM ngoài heap làm tăng disk read |
| **Filesystem/kernel/cgroup** | I/O buffers, network, slab/cache accounting | OOM dù JVM heap chưa chạm limit |
| **Monitoring/sidecars** | Exporters, backup agents và proxy | Dùng thêm CPU/RAM, cạnh tranh I/O |

Một ngân sách **16 GiB** giả định có thể dự trù heap 6 GiB, native/off-heap 2 GiB, page cache 5 GiB và headroom 3 GiB. Đây không phải công thức áp dụng mọi version. Page cache được hạch toán theo container/cgroup/kernel ở nhiều môi trường; **không coi nó là miễn phí ngoài memory limit**. Cần đo RSS, memory.current, GC pauses, OOM events, page cache hit và read p99.

### 10.2. CPU limit và throttling

- **requests.cpu** ảnh hưởng scheduling/capacity; **limits.cpu** có thể gây CFS throttling dù node vật lý còn rảnh.
- JVM bị CPU throttling có thể tăng GC pause, compaction duration và p99 CQL.
- Không có CPU limit không có nghĩa được sử dụng vô hạn: vẫn có quotas, node capacity và workload cạnh tranh.
- Theo dõi CPU throttled time, CPU user/system, GC, node pressure và disk I/O.
- Tăng requests/limits phải kiểm tra số nodes/zones đủ chỗ để giữ rack/volume placement.

### 10.3. QoS và eviction

Kubernetes có QoS và eviction theo resource pressure. **Guaranteed QoS không bảo đảm pod không bao giờ bị evict/OOM**. Node-level disk pressure ở container filesystem/ephemeral-storage có thể xảy ra dù PVC data còn trống. PodDisruptionBudget không chặn mọi eviction hoặc node failure; khi Pod bị evict, PV zone/node affinity có thể khiến Pod không schedule lại được ngay.

## 11. Disk I/O và dung lượng: không chỉ SSTable

~~~text
Commitlog writes
Memtable flush -> SSTables
Compaction -> đọc SSTables + ghi SSTables mới
Repair validation & streaming
Bootstrap/rebuild streaming
Snapshots pinned SSTables + backup copy
Hints, temporary files và container logs
~~~

Một node chứa **700 GiB dữ liệu** không thể cấp một volume 710 GiB rồi hy vọng compaction/repair/snapshot luôn có chỗ. Tăng trưởng, SSTable rewrite và retention cần headroom.

### 11.1. Ví dụ capacity giả định

Volume usable 1 TiB, dữ liệu 650 GiB, tăng trưởng tới kỳ bảo trì 100 GiB, compaction/streaming peak 180 GiB, snapshot giữ thêm khoảng 80 GiB SSTables cũ:

~~~text
Peak nhu cầu = 650 + 100 + 180 + 80 = 1010 GiB.
Usable lý thuyết = 1024 GiB.
Margin ~14 GiB, chưa tính filesystem/metadata và sự cố.
=> NO-GO cho maintenance profile này nếu không cải thiện headroom.
~~~

Với hard links của snapshot, **không cộng toàn bộ snapshot size như file copy độc lập**; 80 GiB minh họa phần giữ thêm do các SSTables cũ không còn được thu hồi sau compaction. Phải đọc filesystem accounting, snapshot retention và tiến độ backup ngoài miền lỗi thật.

### 11.2. IOPS khác bandwidth

Disk SSD có throughput MiB/s cao vẫn có thể nghẽn random IOPS, queue depth hoặc p99 await. Theo dõi:

- Per-device read/write IOPS, throughput, await/latency, queue và free bytes.
- Provisioned IOPS/burst credits hoặc node-level attach limit của cloud storage.
- SSTable count, pending compaction, flush/commitlog latencies.
- Cache misses, GC, node/pod cgroup throttling.
- Hot partition/token ranges và phần read/write traffic dồn vào node đó.

Không dùng trung bình CPU của toàn cluster để suy chưa có disk bottleneck.

### 11.3. Có nên tách commitlog và data directory?

Tách volumes có thể giảm tranh I/O nếu đặt trên **thiết bị/backend thật sự độc lập**, nhưng phải được image/operator/config và backup/recovery hỗ trợ. Cần biết:

1. Hai volumes có cùng identity và được attach lại khi Pod restart không?
2. Commitlog có được bảo vệ khỏi mất dữ liệu trước flush?
3. Recovery khi một volume hỏng có kế hoạch rõ không?
4. CSI supports expansion/snapshot/restore cho tất cả volumes không?
5. Dự kiến throughput, IOPS và cost có thực sự tốt hơn?

**Không chuyển commitlog sang emptyDir** chỉ vì muốn giảm phí lưu trữ nếu dữ liệu phải bền vững. Đánh giá commitlog durability, CL và RPO của workload.

## 12. Startup, readiness và liveness probes

### 12.1. Ba probe khác nhau

| Probe | Câu hỏi | Sai lầm nguy hiểm |
|---|---|---|
| **startupProbe** | Đã qua giai đoạn startup/replay đủ để bắt đầu kiểm tra? | Kill node khi nó còn bootstrap hoặc replay |
| **readinessProbe** | Pod có nên nhận traffic qua Kubernetes Service? | TCP open bị hiểu thành CQL/CL/schema khỏe |
| **livenessProbe** | Process có thật sự dead/hung cần restart? | Quorum timeout làm restart storm |
| **Operator/Cassandra health** | Token/ring, node NORMAL, schema và CQL health | Chỉ nhìn Pod Ready thay node status |

**TCP 9042 open chỉ chứng minh có endpoint nhận TCP**, không xác nhận TLS/auth, schema agreement, node NORMAL hay latency. Một health check CQL ở LOCAL_QUORUM đặt làm liveness có thể fail vì replica khác chậm và khiến kubelet liên tục restart node khỏe về mặt process.

Nguyên tắc:

- Liveness bảo thủ, gắn với process dead/hung chứ không phải SLO của endpoint.
- Readiness có thể được gắn với readiness theo Cassandra-aware operator; không làm query nặng mọi giây.
- Startup probe cho phép đủ thời gian khởi động, commitlog replay, disk/GC trong môi trường thực.
- Khi thấy CrashLoopBackOff, OOMKilled, ProbeFailed hoặc Evicted, chẩn đoán từng lý do, không cùng tăng timeout vô hạn.
- Không cho probe kích hoạt repair, rebuild hoặc thay topology.

### 12.2. Termination và drain

Kubernetes có thể chạy **preStop hook**, gửi termination signal và áp **terminationGracePeriodSeconds**. Cassandra có drain/shutdown/flush semantics phụ thuộc version/operator.

- Termination grace phải đủ cho shutdown hợp lệ nhưng không bảo đảm tự hoàn tất.
- PreStop tiêu thụ một phần grace period; hook quá dài vẫn bị chặn theo Kubernetes.
- **nodetool drain** là thao tác vận hành có tác dụng, không thêm vào mọi YAML nếu chưa hiểu stop logic image/operator.
- Node maintenance và node replacement khác nhau; không phải mọi Pod termination đều nên decommission.
- Sau forced termination, Cassandra có thể replay commitlog; cần kiểm tra ring, disk, CL và data correctness.

Không đặt terminationGracePeriodSeconds=0, force delete hoặc kill -9 như phương án upgrade thường xuyên.
## 13. PodDisruptionBudget, node drain và rolling upgrades

### 13.1. PodDisruptionBudget không hiểu Cassandra quorum

PodDisruptionBudget (PDB) giới hạn một số voluntary disruptions qua **Kubernetes Eviction API**. Ví dụ staging ba pods:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-staging-pdb
  namespace: cassandra-staging
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: cassandra-staging
~~~

**Không dùng trực tiếp trên production.** minAvailable=2 không tự chứng minh rằng mỗi partition ở mỗi DC/rack còn đủ replica đáp ứng LOCAL_QUORUM. PDB không ngăn mọi Pod deletion, node failure, OOM, zone outage hoặc operator actions.

### 13.2. Runbook node drain trên Kubernetes

1. Xác định Cassandra pod, PVC/PV handles, node/zone affinity và operator owner.
2. Kiểm tra replica availability, RF/DC/CL và application error budget.
3. Xem PDB, eviction policy và maintenance window.
4. Để Cassandra-aware operator điều phối shutdown/relocation theo khả năng đã kiểm thử.
5. Theo dõi detach/attach PV, Pod restart, gossip và token ownership.
6. Ghi Java client successful RPS, p95/p99, timeouts, Unavailable.
7. Chỉ chuyển sang worker node tiếp theo khi health gates đạt.

**Node drain khác Cassandra decommission.** Một Pod có thể di chuyển với PVC/identity cũ; một node Cassandra rời ring thật sự phải decommission hoặc replace/rebuild với streaming và verification theo runbook.

### 13.3. Rolling upgrade theo phiên bản

- Đọc compatibility matrix và release notes của Cassandra, JDK, Java Driver, operator, CSI và Kubernetes.
- Có backup manifest/checksum, restore drill, kiểm tra khả năng rollback thực tế; downgrade sau thay SSTable/commitlog format **không mặc nhiên an toàn**.
- Thử staging/canary về CQL prepared statements, TLS/auth, RF/CL, LWT và disk/GC.
- Đổi **một Cassandra failure domain tại một thời điểm** theo runbook; không chạy rolling update mù rồi làm mất quorum.
- Xác minh Cassandra node UP/NORMAL, schema agreement, token placement, disk, compaction và application SLO trước bước tiếp.
- Tránh repair/backup/bootstrap nặng chồng lấp ngoài policy; có GO/PAUSE/STOP gates rõ.

StatefulSet RollingUpdate chỉ là primitive Kubernetes; nó **không tự hiểu** mọi yêu cầu Cassandra-safe về node identity, SSTable version và ring membership.

### 13.4. Cassandra không autoscale giống Java API

HPA tăng số pod Java có thể làm in-flight requests Cassandra tăng đột ngột. Tăng replicas Cassandra trong StatefulSet không tự bảo đảm bootstrap/token/streaming/rack placement; giảm replicas không tự decommission an toàn. Scale Cassandra cần **operator/DBA capacity plan**, PVC/zone, RF/DC, streaming, repair và rollback.

## 14. Node identity: Pod restart, node replacement và PVC

| Tình huống | Kết luận | Quy trình |
|---|---|---|
| **Pod restart cùng PVC và node identity** | Có thể tiếp tục node cũ nếu data lành | Replay/startup, verify ring/CQL |
| **Pod IP đổi, PVC/host ID giữ** | Có thể hợp lệ tùy discovery/broadcast config | Kiểm tra gossip, token ownership |
| **PVC gắn nhầm ordinal** | Nguy cơ identity/data corruption | STOP, bảo toàn evidence, DBA |
| **PVC mất/hỏng, dùng volume rỗng** | Cần node replacement/rebuild, không chỉ restart | Theo operator/version runbook |
| **PV zonal không attach được** | Không thể tự di chuyển disk sang zone khác | Storage recovery hoặc replacement |
| **Scale down Cassandra** | Không chỉ xóa Pod/PVC | Decommission với data movement |
| **Restore SSTables từ snapshot cũ** | Có nguy cơ mất writes mới hoặc hồi sinh dữ liệu đã xóa | DR và reconciliation |
| **Hai pod ghi cùng data directory** | Nguy cơ corruption | Chặn ngay, một writer/identity |

### 14.1. Ghi bằng chứng trước khi thao tác

~~~text
Kubernetes: namespace, Pod UID/name, StatefulSet ordinal
Scheduler : worker node, zone, taints và affinity
Storage   : PVC UID, PV name, CSI volume handle, mount path
Cassandra : host ID, tokens, DC/rack, node status
Recovery  : snapshot/backup manifest, operator run ID
~~~

Không đổi host ID bằng tay, sửa system tables, đổi tên data directory hoặc xóa PVC để thử. Một volume của node C không thành replica D hợp lệ chỉ vì pod mới Ready.

### 14.2. Ba tầng health phải cùng được xác nhận

~~~text
Kubernetes:
  Pod Running / Ready; PVC Bound / Mounted

Cassandra:
  Node UP/NORMAL; schema agreement; token ownership
  Streaming/repair/compaction; DC/rack

Application Java:
  CQL successful throughput; p95/p99; timeout/error rate
  Data correctness theo partition key và CL
~~~

Một tầng xanh không chứng minh toàn hệ an toàn. Tự động hóa nên kiểm tra chéo trước khi mở traffic, rolling bước kế tiếp hoặc xóa recovery point.
## 15. CQL: xác minh RF, bảng theo partition key và consistency

Một cluster **lab nhiều node**, RF=3 trong dc1 có thể dùng:

~~~sql
-- Chỉ cho lab có đủ replica trong dc1.
CREATE KEYSPACE IF NOT EXISTS k8s_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS k8s_lab.events_by_tenant_day (
  tenant_id uuid,
  event_day date,
  happened_at timestamp,
  event_id uuid,
  event_type text,
  payload text,
  PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (
  happened_at DESC, event_id ASC
);

INSERT INTO k8s_lab.events_by_tenant_day (
  tenant_id, event_day, happened_at, event_id, event_type, payload
) VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21',
  '2026-11-21T08:00:00Z',
  22222222-2222-4222-8222-222222222222,
  'LAB_WRITE',
  'synthetic'
);

SELECT happened_at, event_id, event_type
FROM k8s_lab.events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

**Thiết kế bảng:** Partition key **(tenant_id, event_day)** định vị dữ liệu theo tenant-ngày; clustering columns sắp những sự kiện mới nhất. Nếu một tenant/ngày quá nóng, cần bucketing/sharding theo query pattern. Không dùng **ALLOW FILTERING** hay table scan toàn cluster làm healthcheck thường xuyên.

**Quan trọng:** YAML single-node lab ở mục 6 không đáp ứng keyspace RF3 trong ví dụ. Trên một node lab dùng RF1 và CL tương ứng; một RF1 test chỉ chứng minh CQL cơ bản, không chứng minh HA hoặc quorum multi-node. Trong production không thay RF chỉ để làm test xanh.

### 15.1. Đọc schema options thay vì đoán

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'k8s_lab';

SELECT keyspace_name, table_name, gc_grace_seconds,
       default_time_to_live, compaction
FROM system_schema.tables
WHERE keyspace_name = 'k8s_lab';

SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'k8s_lab'
  AND table_name = 'events_by_tenant_day';
~~~

Một metadata snapshot từ một coordinator không tự chứng minh **schema agreement** trên mọi node. Khi topology/upgrade diễn ra, cần kiểm tra node/ring, pending schema migrations và effective keyspace settings.

### 15.2. RF/CL và khả năng phục vụ khi node biến động

| Điều kiện RF3 một DC | LOCAL_ONE | LOCAL_QUORUM |
|---|---|---|
| 3 replica khỏe | Có thể hoàn tất | Thường cần 2/3 replica local |
| 1 replica DOWN | Có thể hoàn tất | Có thể hoàn tất nếu hai replica khác đủ nhanh |
| 2 replica DOWN | Một số request vẫn có thể hoàn tất ở một replica | Có thể Unavailable/timeout |
| Nodes UP nhưng disk/GC bão hòa | Vẫn có thể timeout | Vẫn có thể timeout |

Đây là ví dụ đơn giản hóa cho khả năng replica đáp ứng CL, không phải cam kết từng request luôn thành công. Một local quorum ở dc1 **không chứng minh dữ liệu đã đồng bộ vào mọi DC khác**.

### 15.3. TTL, tombstone và sửa chữa sau Pod restart

Cassandra có thể cần commitlog replay, compaction hoặc streaming sau một lần restart/replace. **TTL expiration**, tombstone grace và repair coverage vẫn phải được tôn trọng; không chạy major compaction để “chắc chắn dữ liệu đúng”. Compaction khác anti-entropy repair, và repair không thay backup.

## 16. Java Driver 4.x: kết nối đúng DC và không che lỗi cluster

Service Java có thể chạy trong Kubernetes cùng namespace, namespace khác, VPC ngoài cluster hoặc qua managed Cassandra endpoint. Đường kết nối và address discovery phải phù hợp thực tế.

### 16.1. Ví dụ dùng một CqlSession có lifecycle rõ

~~~java
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class CassandraK8sReadProbe {
    public static void main(String[] args) {
        // LAB ONLY: configure TLS/auth/secrets for real deployments.
        // Contact point and DC must match environment and routing.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress(
                        "cassandra-headless.cassandra-lab.svc", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement select = session.prepare(
                "SELECT happened_at, event_id, event_type " +
                "FROM k8s_lab.events_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ? LIMIT ?");

            BoundStatement query = select.bind(
                    UUID.fromString(
                        "11111111-1111-4111-8111-111111111111"),
                    LocalDate.parse("2026-11-21"),
                    20)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true);

            Row first = session.execute(query).one();
            System.out.println(
                first == null ? "no row in this read" : "row observed");
        }
    }
}
~~~

**Cảnh báo quan trọng:** Trên lab một node, không dùng nguyên CL LOCAL_QUORUM với RF3 như thể nó có quorum đầy đủ. Ví dụ trên dành cho lab **multi-node RF3**. Với mạng ngoài cluster, headless DNS/pod addresses có thể không route được; cần contact points và driver node address translation/proxy được hỗ trợ.

### 16.2. Cấu hình Java Driver cần được review

| Cấu hình | Rủi ro |
|---|---|
| **contact points** | Service DNS/IP không route được, sai cluster hoặc sai port |
| **local datacenter** | Không khớp Cassandra DC, không có eligible nodes |
| **TLS/mTLS** | Truststore/hostname verification/client cert sai |
| **Authentication** | Secret rotation, role/permission không đúng |
| **Execution profiles** | CL, request timeout, serial consistency/LWT khác hợp đồng |
| **Connection pools** | In-flight requests tăng sau Java API scale-out |
| **Retry policy/speculation** | Retries khuếch đại khi disk/repair đang chậm |
| **Routing key/prepared statements** | Query thiếu partition key có thể không token-aware |
| **Session lifecycle** | Tạo CqlSession mỗi HTTP request gây connection churn |

Các class của Java Driver 4.x nằm trong **com.datastax.oss.driver.api**. Pin phiên bản và compile code theo dependency thực; đừng áp dụng ví dụ kết nối không TLS vào môi trường không tin cậy.

### 16.3. Phân loại lỗi thay vì coi mọi lỗi là no data

- **AllNodesFailedException:** kiểm tra những node driver đã thử và các nguyên nhân qua **getAllErrors()**; có thể là DNS/TLS/auth/port, không phải tất cả Cassandra replicas đều DOWN.
- **DriverTimeoutException:** driver không hoàn tất đúng deadline; không chứng minh mutation chưa ghi.
- **ReadTimeout/WriteTimeout/Unavailable:** xem coordinator/replica, RF/CL, node health, disk/GC và topology.
- **OverloadedException:** giảm tải, không retry tức thì vô hạn.
- **Connection reset sau write:** outcome có thể UNKNOWN, cần idempotency/reconciliation theo business key.

**Không bắt mọi exception rồi trả empty result**. Một query timeout khác với thành công nhưng không có row. Điều này đặc biệt quan trọng khi test migration/restore: nếu lỗi bị nuốt, dashboard có thể báo data missing giả.

### 16.4. Đo trước và sau bảo trì

Cần so **offered requests, successful RPS, p50/p95/p99, timeout/error rate, in-flight/retries và correctness** từ service Java. Đừng chỉ xem **Pod Ready** hay Cassandra throughput. Mỗi thay đổi PV/topology/repair nên có run ID và timestamps để tương quan metric.

## 17. Backup, snapshot và restore: PVC bền vững chưa đủ

### 17.1. Ba khái niệm không được đồng nhất

| Cơ chế | Bảo vệ khỏi điều gì | Không tự bảo vệ |
|---|---|---|
| **Cassandra RF** | Một số lỗi replica/node theo topology/CL | DELETE sai, mất cả fault domain, corruption lan truyền |
| **PVC/PV** | Mất container filesystem khi pod được thay, theo backend | Xóa PVC/PV, lỗi backend, mất zone/region |
| **Cassandra snapshot** | Recovery point SSTables theo phương pháp snapshot | Bản offsite tự động hoặc PITR đầy đủ |
| **CSI VolumeSnapshot** | Snapshot cấp volume nếu driver hỗ trợ | Logical consistency toàn cụm Cassandra |
| **Remote backup + manifest/restore drill** | Có thể phục hồi ngoài miền lỗi theo chính sách đã thử | RPO/RTO nếu chưa thực sự đo và đối soát |

Khi backup Cassandra, cần biết **snapshot SSTables, schema/topology, commitlog archiving nếu PITR, incremental backups, checksum/manifest và encryption/KMS**. Snapshot local thường sử dụng hard links và có thể giữ SSTables cũ khỏi được compaction thu hồi, tăng disk usage theo thời gian.

### 17.2. CSI VolumeSnapshot là block-level snapshot

VolumeSnapshot có thể cung cấp bản copy điểm thời gian của một PVC. Nhưng Cassandra đang ghi SSTable/commitlog đồng thời và dữ liệu có nhiều replica/volumes. Snapshot một volume riêng lẻ thường chỉ có mức **crash consistency** của backend; không tự chứng minh ứng dụng nhất quán theo CL trên toàn cluster.

Nếu DR yêu cầu snapshot consistency, cần công cụ Cassandra-aware hoặc workflow có khả năng điều phối data/commitlog/manifest đúng phiên bản, và **restore drill trên cluster cô lập**.

### 17.3. Tách backup khỏi cùng fault domain

- Backup chỉ nằm trên PVC của pod → vẫn phụ thuộc volume/node/zone.
- Backup upload qua network riêng tới object storage với IAM/KMS/retention → tốt hơn về miền lỗi, nhưng phải kiểm checksum và restore.
- Snapshot metadata không có schema/manifest → có thể khó restore đúng topology/version.
- Restore snapshot cũ có thể mang lại data đã DELETE hoặc bỏ các writes sau cutoff; cần **reconciliation**, đặc biệt khi có yêu cầu xóa dữ liệu nhạy cảm.

### 17.4. RPO và RTO phải được đo

- **RPO:** tuổi dữ liệu tối đa có thể mất trong sự cố.
- **RTO:** thời gian khôi phục khả năng phục vụ đáp ứng yêu cầu.

Đo RPO/RTO bằng **diễn tập khôi phục**, không ước lượng bằng tốc độ tạo snapshot. Bao gồm provision Kubernetes/CSI, copy SSTables, khôi phục schema, start nodes, repair/rebuild nếu cần, xác minh CQL, Java API và các dữ liệu đã bị xóa sau cutoff.

### 17.5. Không xóa PVC khi backup chưa được kiểm chứng

Trong incident, nếu volume Pending/mount lỗi, người vận hành có thể muốn “xóa PVC tạo lại”. Hành động này có thể kích hoạt reclaimPolicy Delete và mất recovery point. Phải xác minh mapping PVC→PV→CSI volume, storage health, backup manifest và DBA runbook trước bất kỳ thao tác destructive nào.
## 18. Bảo mật vận hành container và Kubernetes

Cassandra lưu dữ liệu và metadata có thể nhạy cảm; bản thân Pod/PVC/backup cũng có thể trở thành đường lộ dữ liệu. Thiết kế cần bao phủ cả **identity, network, image, storage và logs**.

### 18.1. Image và supply chain

- Pin image version/digest được phê duyệt; quét CVE và cập nhật theo compatibility matrix.
- Không dùng image latest không kiểm soát trong production; tag có thể đổi bytes giữa hai lần triển khai.
- Dùng private registry và imagePullSecrets nếu cần; phân tách quyền pull với quyền sửa cluster.
- Kiểm tra entrypoint/UID/GID, dữ liệu mount path, JVM version và thư viện native khi thay image.
- Không để container tự download file cấu hình/chứng chỉ từ nguồn không xác minh khi startup.
- Thử rolling upgrade trên staging có SSTables/commitlog thực, không chỉ Pod image pull thành công.

### 18.2. Runtime user và filesystem permissions

Một volume mới có thể có ownership/mode khác với UID/GID chạy Cassandra. Triệu chứng thường là Pod CrashLoop, startup báo không ghi được data/commitlog.

- Xem image chạy user nào và filesystem permissions cần thiết.
- **securityContext.runAsUser/fsGroup** chỉ cấu hình khi hiểu UID/GID của image, backend CSI và cách fsGroup được áp dụng.
- Không mặc định chown toàn bộ SSTables nhiều TB mỗi lần Pod restart: có thể tạo startup delay lớn hoặc thay owner sai.
- Không cho container chạy privileged chỉ để vượt lỗi mount; kiểm tra CSI, security policies và init permissions đúng.
- Root filesystem có thể đặt read-only nếu image và logging/temp paths đã được chuẩn bị; không bật bừa khiến Cassandra không thể ghi runtime files.
- Xác minh mount mode read/write và data directory thực sự nằm trên PVC.

### 18.3. TLS và secrets

| Loại đường truyền | Yêu cầu cần đánh giá |
|---|---|
| **Java client ↔ Cassandra** | TLS/mTLS, hostname/cert chain, auth role, quyền keyspace/table |
| **Internode** | Encryption, trust/rotation, seed/broadcast addresses đúng |
| **JMX/management** | Network isolation, auth/TLS tùy version, không expose public |
| **Backup/KMS/Object store** | IAM least privilege, encryption, retention và audit |
| **Kubernetes Secrets** | Namespace RBAC, encryption at rest, không log values, rotation |
| **Operator service account** | Chỉ các quyền cần cho Cassandra CR/PVC/pods, audit changes |

Kubernetes Secret base64 **không tương đương mã hóa tự thân**. Cần policy bảo vệ etcd, external secrets/KMS và quyền đọc Secrets. Không hardcode username/password, keystore private keys trong ConfigMap, Git YAML hoặc manifest lab đem dùng thật.

### 18.4. NetworkPolicy và security boundaries

NetworkPolicy phải cho phép luồng Cassandra internode, CQL app, operator/JMX, monitoring, backup và DNS, nhưng chặn truy cập từ workload không cần thiết. Một policy quá chặt có thể làm Pods Running nhưng CQL không thể kết nối; một policy quá rộng có thể mở đường truy cập không được phép.

Nếu nhận **AllNodesFailedException** từ Java sau khi thêm NetworkPolicy, kiểm tra causes từng node (DNS, TCP, TLS, auth), không tự coi dữ liệu Cassandra hỏng rồi chạy repair.

## 19. Quan sát: Kubernetes và Cassandra phải đối chiếu theo cùng thời gian

### 19.1. Lệnh Kubernetes có mục đích quan sát

Những lệnh sau là ví dụ **chỉ đọc** trên namespace lab và yêu cầu quyền xem tương ứng:

~~~bash
# Kiểm tra pods, node và nơi pods đang được schedule.
kubectl -n cassandra-lab get pods -o wide

# StatefulSet replica status và rollout info.
kubectl -n cassandra-lab get statefulset cassandra -o wide

# PVC bound/pending và storage class.
kubectl -n cassandra-lab get pvc -o wide

# Volume/PVC events và lỗi attach/mount.
kubectl -n cassandra-lab describe pvc data-cassandra-0

# Pod scheduling, probe, restart, OOM/eviction events.
kubectl -n cassandra-lab describe pod cassandra-0

# Pod logs; logs cần quyền và không xuất secret.
kubectl -n cassandra-lab logs cassandra-0 -c cassandra --tail=100

# Kiểm tra cấu hình bảo vệ voluntary disruptions.
kubectl -n cassandra-lab get pdb
~~~

**Lưu ý:** Pod/pvc names đúng khi dùng manifest ở mục 6; operator khác có thể đặt tên khác. Không copy commands và giả định đúng namespace production. Tránh dùng lệnh mutating (delete, patch, scale, rollout restart) trong giai đoạn quan sát.

### 19.2. Lệnh Cassandra đọc sức khỏe

Theo cú pháp và quyền của phiên bản đang chạy:

~~~bash
# Cassandra gossip/ring, DC/rack và node states.
nodetool status

# Node/resource information.
nodetool info

# Pending/dropped thread pool tasks.
nodetool tpstats

# Active compactions.
nodetool compactionstats

# Streaming/network sessions.
nodetool netstats

# Thống kê table.
nodetool tablestats k8s_lab.events_by_tenant_day

# Partition/row size distribution khi version hỗ trợ.
nodetool tablehistograms k8s_lab events_by_tenant_day

# Snapshot retention.
nodetool listsnapshots
~~~

**nodetool status UN không có nghĩa CQL latency tốt hoặc repair đầy đủ.** Nếu đang dùng Operator, có thể có metric/JMX/Prometheus endpoints đặc thù; metric names và availability khác theo version/exporter. Không invent metrics rồi coi chúng tồn tại ở cluster.

### 19.3. Metric matrix

| Tầng | Tín hiệu | Câu hỏi |
|---|---|---|
| **Kubernetes scheduling** | Pending, node affinity, zone spread, taints, events | Pod có chỗ để chạy không? |
| **Storage CSI** | PVC/PV status, attach/detach, mount errors, volume latency | Volume có bền và gắn đúng node không? |
| **Pod/container** | Restart count, OOMKilled, CPU throttle, memory RSS, disk ephemeral | Container có bị giới hạn hoặc kill không? |
| **Cassandra node** | Gossip status, host ID, token/DC/rack, CQL readiness | Identity/topology có hợp lệ? |
| **Cassandra storage** | SSTables, commitlog, compaction, disk free/await | Đọc ghi/repair có bị nghẽn I/O? |
| **Repair/streaming** | Active sessions, progress, failed ranges, bytes | Có đồng bộ đúng phạm vi? |
| **Ứng dụng Java** | Offered/success RPS, p95/p99, retries, failures | User thấy SLO thế nào? |
| **Correctness/DR** | Fixture reads/writes, backup manifest, restore RPO/RTO | Dữ liệu có đủ, có thể khôi phục? |

### 19.4. Timeline từ thay đổi đến ảnh hưởng

~~~text
T0: Baseline CQL p99, successful RPS và node health ổn định
T1: Change window bắt đầu; rollout Pod hoặc volume operation
T2: PVC attach/mount, Pod startup
T3: Cassandra node UP/NORMAL, token/rack kiểm chứng
T4: Streaming/repair/compaction phát sinh nếu có
T5: Ứng dụng Java p99/errors trở lại ngưỡng
T6: Backup/checksum và correctness verification complete
~~~

**Không kết luận hoàn tất ở T2** vì Pod Ready; cần data correctness và recovery window nếu có change ảnh hưởng storage/topology.

## 20. Runbook chẩn đoán theo triệu chứng Kubernetes/storage

### 20.1. Pod Pending, PVC Pending

**Dấu hiệu:** Pod không schedule được, PVC vẫn Pending hoặc volume provisioning bị từ chối.

Kiểm tra:

1. **kubectl describe pod/pvc**: events về provisioning, zone, quota, missing StorageClass, permissions.
2. StorageClass provisioner/CSI driver thật có tồn tại và khỏe không.
3. volumeBindingMode và zone/node affinity có phù hợp scheduler không.
4. Có đủ capacity/IOPS quota, volume count hoặc account permission không.
5. Có PVC stale/PV retained cần xử lý mapping sau sự cố trước không.

**Không xóa PVC** chỉ để thử lại khi chưa biết reclaim policy và dữ liệu gắn với nó. Nếu là PV cũ chứa data thật, tạo volume mới có thể biến một node restart thành node replacement.

### 20.2. Pod Pending do PV zone affinity

**Dấu hiệu:** PVC Bound nhưng Pod không chạy được ở một zone.

- Kiểm tra PV nodeAffinity/topology labels, worker node availability và pod affinity/anti-affinity.
- Xác minh PV là zonal/local, có thể reattach trong cùng zone hay không.
- Không “bỏ affinity” để ép mount volume khác zone nếu backend không hỗ trợ.
- Nếu zone mất vĩnh viễn, cần storage recovery/DBA node replace/rebuild; không làm như stateless move.

### 20.3. CrashLoopBackOff sau mount

**Dấu hiệu:** Container restart liên tục, logs báo permission denied hoặc corrupt startup files.

- Đọc startup logs và last termination reason, tránh chỉ xem dòng lỗi cuối.
- Kiểm tra actual mount path, UID/GID/fsGroup, filesystem permissions và disk free.
- Xem volume thật sự chứa SSTables/commitlog của node identity nào.
- Kiểm tra JVM heap/off-heap/OOMKilled khác với permission issue.
- Không đổi UID/chown toàn bộ data hoặc xóa system keyspaces bằng tay trước DBA approval.

### 20.4. Disk full dù PVC mới mở rộng

**Dấu hiệu:** PVC size tăng nhưng filesystem available bytes chưa tăng; hoặc snapshot/compaction giữ nhiều file.

- Xác minh CSI/backend hỗ trợ expansion và filesystem resize đã hoàn tất.
- Kiểm tra Pod/filesystem nhận capacity mới hay mount còn pending resize.
- Xem snapshot pinned SSTables, compaction backlog, commitlog và logs trên các filesystems riêng.
- Không dọn snapshot khi external backup chưa được xác minh.
- Không ép compaction khi disk gần full vì compaction cần temporary space.

### 20.5. AllNodesFailed/DriverTimeout sau đổi Service hoặc NetworkPolicy

**Dấu hiệu:** Java service không kết nối CQL hoặc có timeout sau Pod IP đổi.

- Kiểm tra contact points, DNS/headless service records, local DC và address discovery.
- Đọc per-node causes của **AllNodesFailedException.getAllErrors()**: ConnectException, TLS/PKIX, auth, init timeout...
- Xem Cassandra CQL listener, internode network và query plan/replica availability.
- Đối chiếu request timeout với pool/admission/GC và server read/write latencies.
- Không giảm CL hoặc tăng retries vô hạn để che lỗi đường kết nối.

### 20.6. Node UP nhưng Java read p99 tăng sau replace

- Kiểm tra streaming/repair/compaction đang chạy, disk queue, network và GC.
- Xem token/rack ownership của node mới, partition key distribution/hot partitions.
- Đo offered vs successful RPS, retry/speculative execution amplification.
- Điều tiết maintenance qua operator runbook và admission, giữ SLO gates.
- Không kết luận “thêm node là API nhanh ngay” vì bootstrap có thể tăng I/O tạm thời.

### 20.7. Suspected stale data khi volume cũ trở lại

Nếu một node/volume mất kết nối lâu hơn tombstone grace và trở lại với SSTables cũ, có nguy cơ zombie khi deletes bị bỏ lỡ và tombstone đã có thể bị purge.

- **PAUSE** tự đưa stale node vào phục vụ khi runbook yêu cầu.
- Kiểm tra **gc_grace_seconds**, repair coverage, downtime, compaction và mutation audit.
- Không mặc định repair một lần là khôi phục deletion đã mất.
- DBA xác định quarantine/rebuild/replace/reconciliation dựa trên nguồn sự thật nghiệp vụ.
- Giữ backup/incident evidence; tránh xóa dữ liệu mới hợp lệ do can thiệp vội.
## 21. Kịch bản kiểm thử theo điều kiện môi trường

### 21.1. Chia kiểm thử thành nhiều tầng

| Loại thử nghiệm | Mục tiêu | Không chứng minh |
|---|---|---|
| **Docker single-node** | Tính bền vững của named volume, CQL prepared statements, restart container | RF3, quorum, zone failure |
| **Kubernetes single-node lab** | PVC binding/mount, Pod recreation, Startup/Readiness | Node replacement và repair multi-replica |
| **Staging multi-node cùng zone** | Token-aware routing, RF/CL, bootstrap/repair theo operator | Fault tolerance khi mất cả zone |
| **Staging multi-zone** | Scheduling/PV topology, zone outage, quorum, operator failover | Multi-region WAN/DR nếu chỉ một region |
| **Multi-DC DR lab** | DC placement, local consistency, backup/restore/reconciliation | Production luôn có cùng latency/capacity |
| **Java end-to-end load** | HTTP/CQL p95/p99, retries, errors, correctness | Dữ liệu khôi phục được nếu chưa restore drill |

**Nguyên tắc:** Test mức dưới là điều kiện cần, không phải điều kiện đủ cho HA/DR. Kết quả phụ thuộc phiên bản image/operator/CSI/Kubernetes/Cassandra, DC/rack, RF/CL, data size và tải thực.

### 21.2. Test A — Tạo lại Pod, giữ nguyên PVC

Trên **single-node lab** có PVC và dữ liệu tổng hợp:

1. Preflight schema, PVC/PV name, Pod ordinal và volume handle.
2. Ghi row CQL có primary key xác định, đọc lại.
3. Dùng cơ chế restart Pod **được duyệt trong lab**; không xóa PVC.
4. Đợi Pod startup, xác minh mount **cùng PVC**, read logs và effective Cassandra data directory.
5. Đọc lại row theo cùng PK, ghi result và thời gian phục hồi.
6. Đọc node identity/host ID trước và sau nếu công cụ operator hỗ trợ.
7. Xác minh không có Pod khác cùng mount data directory.

**PASS scope:** chứng minh data sống qua Pod recreation với storage backend đó. Không chứng minh host/zone failure hay recovery sau corruption.

### 21.3. Test B — PVC/PV theo zone

Trên staging multi-zone:

1. Ghi zone label cho từng worker, StorageClass và PV nodeAffinity.
2. Kiểm tra Pod distribution và Cassandra rack placement.
3. Mô phỏng worker drain hoặc zone unavailability theo runbook, với rollback.
4. Xem Pod có giữ PVC tại zone cũ hoặc được operator thay thế hợp lệ không.
5. Đo quorum/CL, CQL errors, network/streaming và disk.
6. Không đổi PV nodeAffinity bằng tay để “làm Pod chạy được” trong fault.
7. Đánh giá **FAIL/NO-GO** nếu Pod Pending dài khiến quorum/SLO không đạt yêu cầu.

### 21.4. Test C — One replica lost, RF3/LOCAL_QUORUM

Trên cluster staging **RF3 thực**, giả lập mất một replica theo phương án fault injection được duyệt:

- Ghi CQL SELECT/INSERT theo partition key và CL.
- Đo successful RPS, p99 và lỗi.
- Xác nhận hai replica còn lại thật sự có mặt trong DC.
- Khôi phục replica, theo dõi streaming/repair và dữ liệu.
- Chạy repair qua operator nếu runbook yêu cầu, không tự chạy full repair vô hạn.
- Không tạo counter/list append side effects khi retry.

**PASS có điều kiện:** ứng dụng đạt SLO và correctness trong fault profile đã thử. Không khẳng định mọi topology hay hai replicas down cũng an toàn.

### 21.5. Test D — CSI VolumeSnapshot và restore drill

1. Tạo backup qua workflow được hỗ trợ, ghi manifest/schema/commitlog policy.
2. Xác minh snapshot/upload/checksum và quyền KMS.
3. Khôi phục trên cluster **cô lập**, đúng version/schema/RF plan.
4. Đọc sample queries theo partition key và kiểm tra duplicate/missing rows.
5. Đo RPO/RTO thực tế, gồm provision volumes, copy data, node startup và service readiness.
6. Xác minh **DELETE hợp lệ sau backup cutoff** sẽ được reconcile nếu workflow phục hồi production.
7. Không phục hồi snapshot cũ đè trực tiếp cluster đang phục vụ chỉ để kiểm thử.

### 21.6. Test E — Mở rộng PVC có kiểm soát

- Dùng volume lab, đọc StorageClass allowVolumeExpansion và CSI docs.
- Thay size bằng workflow đã duyệt, theo dõi PV/PVC conditions.
- Xác nhận filesystem/Pod nhìn thấy capacity mới.
- Kiểm tra I/O performance trước/sau, backup snapshots và disk free.
- Không giả định PVC lớn hơn làm IOPS tăng theo tỷ lệ nếu backend không có cam kết đó.
- Ghi rollback limitation; giảm kích thước PVC thường không phải thao tác được hỗ trợ đơn giản.

### 21.7. Test F — Probe dưới tải maintenance

Dùng Java load generator bounded concurrency và run repair/backup trên staging:

~~~text
Baseline:
  success RPS, p95/p99, errors, disk await và GC

Maintenance:
  repair/streaming or backup copy theo runbook

Probe check:
  startup không kill node đang replay
  readiness không trả positive giả
  liveness không restart node chỉ vì quorum chậm
  app error budget và disk headroom vẫn trong ngưỡng

Recovery:
  Node NORMAL, repair/compaction backlog ổn
  CQL correctness và p99 trở lại baseline
~~~

Nếu **liveness** gây restart storm, đánh dấu FAIL; sửa probe policy với operator trước khi tiếp tục. Không sửa SLO threshold trong lúc test chỉ để báo xanh.

## 22. Ra quyết định theo tình huống môi trường

### 22.1. StorageClass có dung lượng nhưng không có đủ zones

**Bối cảnh:** Muốn RF3, ba racks/zone khác nhau, cluster Kubernetes chỉ có hai zones.

**Rủi ro:** Một số Pod không schedule được nếu hard spread, hoặc nhiều replicas cùng zone nếu soft spread. Mất zone có thể khiến không đủ quorum.

**Hướng xử lý:** **NO-GO** với fault-domain requirement chưa đạt; bổ sung zone/capacity hoặc điều chỉnh thiết kế với approval. Không tự gỡ anti-affinity để “làm mọi Pod Running” rồi gọi là HA.

### 22.2. Local NVMe rất nhanh nhưng worker node hỏng

**Bối cảnh:** Cassandra dùng local PV NVMe, node vật lý mất vĩnh viễn; pod Pending vì PV nodeAffinity.

**Rủi ro:** Không thể reattach local disk sang worker khác như zonal network volume. Data directory trên node cũ có thể mất.

**Hướng xử lý:** RF/quorum và backup phải cung cấp đường phục hồi. DBA/operator chạy node replacement/rebuild theo version; không gắn PVC rỗng rồi coi như Pod restart. Đo streaming cost, data correctness và recovery time.

### 22.3. Cloud block volume còn sống nhưng pod không gắn được

**Bối cảnh:** Worker bị thay, PVC Bound, volume zonal vẫn khỏe nhưng attach kẹt.

**Rủi ro:** Multi-attach error, finalizer/CSI controller issue, scheduler đặt sai zone hoặc stale attachment.

**Hướng xử lý:** Thu PVC/PV/CSI events, node/zone, volume handle và operator logs. Phối hợp storage owner để detach/attach an toàn. Không force detach khi còn một writer hoạt động trên volume, không xóa PVC/volume.

### 22.4. CPU thấp nhưng đọc rất chậm

**Bối cảnh:** Pod CPU 30%, app p99 tăng gấp ba, disk await cao, compaction backlog lớn.

**Phân tích:** I/O mới là nút thắt; tăng Java heap hoặc số Pod API có thể làm tệ hơn. Xem StorageClass IOPS/throughput, tombstones, partition skew, compaction/repair và page cache.

**Hướng xử lý:** Điều tiết background jobs theo runbook, capacity I/O và data-model tuning; đo lại khi tải và CL không đổi.

### 22.5. Cùng PVC nhưng host ID thay đổi bất thường

**Bối cảnh:** Sau container image update, Pod mount PVC cũ nhưng Cassandra xuất hiện như một node mới trong ring.

**Rủi ro:** Image thay data directory, init script tạo system keyspaces mới ở container layer, hoặc mapping/identity configuration sai.

**Hướng xử lý:** STOP rollout tiếp; xác minh effective directories, PVC mounts, host ID/tokens, startup logs và backup. Không delete node cũ trong gossip hoặc sửa system tables theo cảm tính.

### 22.6. Snapshot local rất nhanh nhưng disk sắp đầy

**Bối cảnh:** Cron tạo snapshot mỗi ngày trên cùng PVC, backup upload đôi lúc fail, compaction tăng.

**Phân tích:** Snapshot hard links giữ SSTables cũ và làm không gian không được thu hồi. Backup chưa verified ở remote storage.

**Hướng xử lý:** Xác minh remote manifest/checksum, repair/upload job, đặt retention và alert disk free. Chỉ cleanup snapshot local khi policy/owner cho phép; không xóa recovery point cuối cùng.

### 22.7. Java pods scale-out làm Cassandra Overloaded

**Bối cảnh:** HPA tăng service API từ 10 lên 50 replicas; mỗi Pod mở nhiều connections và requests tới Cassandra.

**Rủi ro:** Load dồn, pool/in-flight và retries tăng, Overloaded/DriverTimeout xuất hiện dù Cassandra cluster không thay đổi.

**Hướng xử lý:** Admission, bounded concurrency/rate per tenant, driver session reuse, retry budget và capacity planning; không tự scale Cassandra 5 lần ngay vì bootstrap cũng dùng disk/network.

### 22.8. Pod Ready, query ở một DC vẫn bị Unavailable

**Bối cảnh:** Kubernetes dashboard xanh, ứng dụng Java chạy ở dc2, RF tại dc2 chưa đủ hoặc local DC cấu hình sai.

**Phân tích:** Kubernetes readiness khác CL/replica availability. Kiểm tra NTS replication, Cassandra node statuses theo DC, driver local DC, gossip và repair/streaming.

**Hướng xử lý:** Sửa topology/config được duyệt, giữ consistency contract; không hạ LOCAL_QUORUM để xóa lỗi khỏi dashboard.

## 23. Quy tắc GO / PAUSE / STOP / ESCALATE

### 23.1. Bảng gate cho rollout/maintenance

| Gate | GO khi | PAUSE/STOP khi |
|---|---|---|
| **Backup** | Có bản được xác minh/restore gần đây theo chính sách | Không có recovery point cho thay đổi rủi ro |
| **Topology** | DC/rack/replica health đạt điều kiện đã duyệt | Mất quorum, token placement mâu thuẫn |
| **Storage** | PVC đúng identity, disk/headroom/IOPS đủ | Mount nhầm, disk full, CSI attach lỗi |
| **Client SLO** | Successful RPS, p95/p99, errors trong ngưỡng | Error budget hoặc timeout vượt ngưỡng |
| **Repair/streaming** | Không có failed ranges/sessions chưa xử lý | Stale replicas, partial repair không rõ phạm vi |
| **Image/version** | Compatibility matrix và staging pass | Không có downgrade/rollback plan khi cần |
| **Security** | TLS/auth/RBAC/secret rotation đúng | TLS bị tắt hoặc secrets lộ ngoài phạm vi |
| **Correctness** | Dữ liệu fixture/các invariant kiểm chứng | Missing/duplicate data, suspected corruption |
| **Fault domain** | Volume/Pods/racks/zone placement hợp policy | Replica cùng một fault domain trái yêu cầu |

### 23.2. Ví dụ profile ngưỡng minh họa

~~~yaml
example_policy_not_production_defaults:
  api_read_p99_max_ms: 250
  logical_error_rate_max_percent: 1
  min_successful_rps: 900
  min_disk_free_percent: 20
  required_backup_restore_drill_passed: true
  no_unresolved_volume_identity_mismatch: true
  no_unverified_repair_failures: true
  rolling_max_nodes_per_failure_domain: 1
  require_topology_and_schema_agreement: true
~~~

Các ngưỡng **250 ms, 900 RPS, 20%** chỉ là ví dụ. Giá trị thực phải từ SLO và dự báo data/disk growth, RF/CL, storage backend. Một threshold phần trăm disk free không thay thế **dung lượng tuyệt đối** cần cho compaction/streaming.

### 23.3. Khi STOP không được xóa chứng cứ

- Dừng dispatch/rollout mới, không tự kill Cassandra hay xóa PVC/PV.
- Bảo toàn logs, PV mapping, host ID/token/replica state, backup manifests và metrics.
- Nếu cần can thiệp job đang chạy, dùng operator/version-approved procedure.
- Phân biệt **rollback config/image** với **khôi phục dữ liệu**; một rollback code không undo SSTables đã ghi lại.
- Chỉ tiếp tục khi owner đã phê duyệt kế hoạch khôi phục và verification criteria.
## 24. Bài tập tình huống và đáp án gợi ý

### Bài 1 — Có ba Docker containers là đã HA?

Một lập trình viên chạy ba Cassandra containers trên cùng laptop, RF3 và LOCAL_QUORUM đều trả kết quả.

**Hỏi:** Có chứng minh chịu được lỗi một zone thật không?

**Đáp án:** Không. Ba containers cùng host/disk/network vẫn có fault domain chung. Để kiểm chứng zone failure cần các worker nodes/volumes/zones thực sự độc lập và quy trình fault staging.

### Bài 2 — emptyDir qua container restart

Một Pod có emptyDir chứa SSTables. Container process crash rồi kubelet restart container trong **cùng Pod**; dữ liệu còn đó.

**Hỏi:** Có thể dùng emptyDir làm persistent storage production?

**Đáp án:** Không. emptyDir có thể sống qua container restart cùng Pod, nhưng bị xóa khi Pod bị xóa/evicted. Cần PVC/PV hoặc storage phù hợp và backup.

### Bài 3 — StatefulSet Pod Ready nhưng volume rỗng

Cassandra-1 được tạo lại sau upgrade. PVC không mount vào **/var/lib/cassandra** như trước; ứng dụng báo ít dữ liệu hơn.

**Hỏi:** Kiểm tra gì?

**Đáp án:** STOP rollout; kiểm tra effective data directories, volumeMounts/PVC UID/PV handle/host ID, startup logs và token placement. Không tạo table mới/xóa system keyspace để “lấp dữ liệu”. Đây có thể là identity/data path issue.

### Bài 4 — Cùng data directory cho hai pods

Một RWX volume được mount vào hai pods Cassandra, cả hai đều ghi vào cùng data directory.

**Hỏi:** Tại sao sai dù RWX cho phép mount?

**Đáp án:** Cassandra là share-nothing replica system; hai processes ghi cùng SSTable/commitlog/system files có nguy cơ corruption. Mỗi node phải có data directory/identity riêng, không coi RWX là distributed database locking.

### Bài 5 — StorageClass Immediate và PV sai zone

PVC được cấp ở zone-a khi Pod scheduler chỉ có worker zone-b hợp lệ. Pod Pending.

**Hỏi:** Cách phòng tránh?

**Đáp án:** Xem volumeBindingMode/WaitForFirstConsumer nếu CSI hỗ trợ, PV nodeAffinity và pod topology; thiết kế zone placement ngay từ đầu. Không sửa PV zone affinity tùy tiện.

### Bài 6 — PVC reclaimPolicy Delete

Pod bị lỗi, người vận hành muốn xóa PVC rồi để StatefulSet tạo lại. StorageClass/PV dùng reclaimPolicy Delete.

**Hỏi:** Rủi ro?

**Đáp án:** Xóa PVC có thể dẫn đến xóa backend volume, mất SSTables/commitlog. Kiểm tra PV/PVC mapping, backup, retention policy và recovery runbook trước thao tác destructive.

### Bài 7 — StatefulSet scale từ 3 xuống 2

Một đội tiết kiệm chi phí giảm replicas StatefulSet mà không chạy Cassandra decommission.

**Hỏi:** Vì sao không đúng?

**Đáp án:** Replica/token ownership và data movement của Cassandra cần quy trình riêng. Xóa Pod/PVC không tự chuyển ranges/restore RF, có thể gây Unavailable/mất dữ liệu. Dùng operator/decommission đã được duyệt.

### Bài 8 — PDB minAvailable 2

Cassandra có RF3, PDB minAvailable=2; một node đã DOWN vì disk, team tiếp tục drain một node khác vì PDB cho phép.

**Hỏi:** PDB có bảo đảm LOCAL_QUORUM còn đủ không?

**Đáp án:** Không. PDB không biết partition placement hay liveness Cassandra, và trạng thái Pod Ready có thể sai lệch. DBA phải xác minh replica/quorum của token ranges liên quan trước drain.

### Bài 9 — CPU chưa đầy, query rất chậm

CPU Pod chỉ 40% nhưng read p99=700ms, disk await cao, pending compaction tăng.

**Hỏi:** Có nên tăng CPU limit trước?

**Đáp án:** Chưa đủ căn cứ. Disk/compaction có thể là bottleneck; xem IOPS/throughput/queue, cache, tombstones/hot partitions. Thử thay storage/điều tiết maintenance trên staging và giữ query mix/CL.

### Bài 10 — Heap bằng memory limit

Pod limit 8 GiB, JVM -Xmx 8 GiB. Pod bị OOMKilled dù heap-used không đầy.

**Hỏi:** Tại sao?

**Đáp án:** Off-heap/direct buffers, stacks, native, cache/kernel/cgroup accounting có thể vượt tổng limit. Cần memory budget và đo RSS/GC/page cache; không đặt heap bằng toàn bộ limit.

### Bài 11 — Liveness SELECT LOCAL_QUORUM

LivenessProbe thực hiện SELECT ở LOCAL_QUORUM mỗi 5 giây. Một replica chậm khiến probe fail và kubelet restart Pod hiện đang khỏe.

**Hỏi:** Rủi ro?

**Đáp án:** Restart storm làm cluster mất thêm replica và availability. Liveness nên kiểm tra process dead/hung, startup đủ dài, readiness/operator health có semantics khác; đừng dùng request quorum làm liveness một cách mù.

### Bài 12 — Pod IP đổi

Pod Cassandra-0 bị reschedule, Pod IP đổi nhưng đúng PVC và host ID được giữ.

**Hỏi:** Có bắt buộc rebuild?

**Đáp án:** Không mặc nhiên. Cần xác minh seed/discovery, broadcast addresses, gossip/token ownership và CQL. Nếu identity/data đúng, có thể là restart hợp lệ; nếu host ID thay hoặc volume sai thì STOP.

### Bài 13 — Java Driver kết nối headless Service nhưng thất bại

Service Java chạy ngoài Kubernetes, contact point là DNS Pod nội bộ không route được; AllNodesFailed chứa ConnectTimeout.

**Hỏi:** Có sửa bằng tăng request timeout không?

**Đáp án:** Không. Cần endpoint/address translation/proxy/network route được hỗ trợ, TLS/auth và local DC. Per-node causes cho thấy transport issue, không sửa bằng repair Cassandra.

### Bài 14 — Một zone mất với RF3 trong hai zones

Ba replicas của một partition phân bố 2 ở zone-a và 1 ở zone-b. Zone-a mất.

**Hỏi:** LOCAL_QUORUM có khả dụng?

**Đáp án:** Với chỉ một replica zone-b còn phục vụ, **không đủ quorum 2/3** trong dc1. Số node total=3 không bảo đảm HA nếu placement/fault domains không đáp ứng yêu cầu.

### Bài 15 — Snapshot PVC là backup đủ?

CSI VolumeSnapshot được tạo cho một PVC, chưa có schema manifest, remote copy, commitlog policy hoặc restore drill.

**Hỏi:** Có đạt RPO/RTO không?

**Đáp án:** Chưa thể kết luận. Block snapshot không tự bảo đảm Cassandra consistency toàn cluster hoặc khôi phục được theo nghiệp vụ. Cần Cassandra-aware backup, manifest/checksum/restore test và RPO/RTO thực đo.

### Bài 16 — Xóa snapshot khi disk đầy

Node disk gần full, snapshot SSTables rất lớn, remote upload lại đang lỗi và chưa có backup mới verified.

**Hỏi:** Có nên xóa snapshot ngay?

**Đáp án:** Không tự ý. Có nguy cơ mất recovery point. DBA/backup owner phải đánh giá bản backup trước đó, disk headroom, retention, cách xử lý upload hoặc capacity theo incident runbook.

### Bài 17 — Commitlog trên emptyDir

Data directory nằm trên PVC, commitlog trên emptyDir. Một Pod bị xóa trước khi memtable flush.

**Hỏi:** Rủi ro?

**Đáp án:** Các mutations trong commitlog chưa flush có thể mất khi emptyDir bị xóa, ảnh hưởng durability/RPO. Cần xem commitlog/CL semantics và tách volume một cách có chủ đích, không tách chỉ để tối ưu chi phí.

### Bài 18 — Cassandra repair và Java p99 tăng

Repair đang stream nhiều SSTables, API read p99 từ 150 lên 400 ms, SLO là 250 ms.

**Hỏi:** Chạy thêm repair jobs để hoàn tất nhanh hơn có hợp lý?

**Đáp án:** Không nếu đã vi phạm SLO. Cần health/capacity gate, điều tiết maintenance theo operator, đo disk/network/compaction và thời gian phục hồi; đồng thời theo dõi repair coverage/deadline.

### Bài 19 — Cấu hình Local DC sai

Cluster Cassandra ở dc-east, Java Driver cấu hình withLocalDatacenter("dc1"), các Pods Cassandra đều UP.

**Hỏi:** Vì sao app vẫn có thể fail?

**Đáp án:** Load balancing/eligible nodes không khớp local DC. Phải sửa effective config cho đúng topology, không tự chuyển traffic sang DC khác nếu có data residency/CL constraints.

### Bài 20 — Khôi phục PVC từ snapshot cũ

Restore từ tuần trước đưa order đã DELETE tuần này trở lại, mặc dù cluster mới khởi động thành công.

**Hỏi:** Lỗi gì?

**Đáp án:** Snapshot cutoff cũ không bao gồm delete mới. DR phải replay/reconcile writes/deletions sau cutoff, kiểm tra business truth và privacy retention trước khi mở traffic; Pod Ready không chứng minh dữ liệu đúng.

### Bài 21 — Kubernetes CronJob điều khiển repair

Một CronJob bật repair định kỳ nhưng không kiểm tra phạm vi token/DC, repair mode và failed ranges. Pod Job status Completed.

**Hỏi:** Có thể kết luận tất cả replica đã được repair trước gc_grace_seconds không?

**Đáp án:** Không. Cần **coverage ledger** theo keyspace/table/range/replica/DC, last verified success, evidence và alert near-deadline. Cron trigger không thay repair verifier.

### Bài 22 — Tăng kích thước PVC và kỳ vọng IOPS gấp đôi

PVC tăng từ 500 GiB lên 1 TiB; backend dùng IOPS provisioned độc lập nên p99 không đổi.

**Hỏi:** Vì sao?

**Đáp án:** Dung lượng không nhất thiết kéo theo throughput/IOPS. Xem StorageClass/backend performance policy, disk queue, node attach limit, compaction và query shape; thử tải để chọn profile đúng.

### Bài 23 — Force-delete Pod để dọn node drain

Một Cassandra Pod termination lâu vì đang flush/replay. Team dùng force-delete liên tục để rollout tiến độ nhanh hơn.

**Hỏi:** Nguy cơ?

**Đáp án:** Có thể làm gián đoạn shutdown, tăng commitlog recovery, mất quorum và chồng node replacements. Cần xác minh Pod/Cassandra state, terminationGracePeriod và operator runbook; không force-delete như thủ tục thường.

### Bài 24 — Người dùng thấy dữ liệu thiếu trong khi SELECT lỗi

Java code catch mọi exception rồi trả danh sách rỗng. Sau upgrade/network change, ứng dụng báo không có events.

**Hỏi:** Có thể coi dữ liệu mất không?

**Đáp án:** Chưa. ReadTimeout/Unavailable/AllNodesFailed là **unknown read result**, không phải thành công với 0 rows. Sửa error handling, quan sát per-node causes/CL/partition key và kiểm tra Cassandra đúng nguồn.

## 25. Checklist vận hành theo môi trường

### 25.1. Data và storage

- [ ] Đã xác định đường dẫn SSTables, commitlog, hints và snapshot theo image/operator.
- [ ] Dữ liệu bền vững đặt trên PVC/PV phù hợp; không dựa vào container layer/emptyDir cho dữ liệu production cần giữ.
- [ ] PVC của mỗi node gắn đúng Pod ordinal/host ID; không dùng chung data directory.
- [ ] StorageClass/CSI driver, access modes, topology binding, reclaim policy và expansion đã được kiểm thử.
- [ ] Với local PV/zonal PV, có node replacement/zone recovery runbook rõ.
- [ ] Có disk headroom cho compaction, bootstrap, repair, snapshots và growth.
- [ ] Có backup ngoài fault domain, manifest/checksum, encryption/KMS và restore drill.
- [ ] Không xóa PVC/PV/snapshot hoặc thay reclaim policy trong incident khi chưa có approval.

### 25.2. Topology, lifecycle và HA

- [ ] Cassandra DC/rack mapping phù hợp Kubernetes zone/node topology.
- [ ] RF per DC và CL của Java clients được ghi rõ, có kiểm tra quorum khi node/zone lỗi.
- [ ] Seed discovery, broadcast addresses và internode networking theo operator/version.
- [ ] Startup/readiness/liveness đã được thử dưới GC/repair/bootstrap, không gây restart storm.
- [ ] terminationGracePeriodSeconds/preStop phù hợp shutdown version, không lạm dụng force delete.
- [ ] PDB được hiểu đúng phạm vi; không coi PDB là Cassandra quorum guarantee.
- [ ] Rolling upgrade/scale/replace do operator/runbook điều phối, có stop gates.
- [ ] Không dùng HPA tự ý scale Cassandra như stateless API.
- [ ] Repair coverage, gc_grace_seconds và node downtime được giám sát.

### 25.3. Java application và security

- [ ] Java Driver version tương thích Cassandra/JDK và được pin.
- [ ] Contact points có thể route, local DC đúng, topology/token discovery hoạt động.
- [ ] TLS/mTLS/auth, NetworkPolicy, management/JMX access và secrets được hạn chế phù hợp.
- [ ] CqlSession/prepared statements có lifecycle tái sử dụng; không tạo session trên mỗi request.
- [ ] Query theo partition key, không dùng ALLOW FILTERING như healthcheck.
- [ ] Client p95/p99, successful RPS, retries, errors và in-flight được quan sát.
- [ ] Timeout sau write có idempotency/reconciliation; không coi lỗi là mutation chưa áp dụng.
- [ ] Không có config/secret/payload nhạy cảm trong public logs hoặc YAML trong Git.

### 25.4. Nghiệm thu thay đổi

- [ ] Có baseline/approval cho environment, phiên bản và storage backend.
- [ ] Có staging tests cho Pod restart/PVC reattach/zone fault phù hợp fault domains.
- [ ] Có fault/recovery test ở RF/CL thực; single-node test không bị hiểu thành HA proof.
- [ ] K8s Pod Ready/PVC Bound được đối chiếu Cassandra node NORMAL/repair/streaming.
- [ ] Đã xác minh CQL fixture reads/writes và business data correctness sau change.
- [ ] Đã đo resource headroom, error budget, post-maintenance recovery window.
- [ ] RPO/RTO được đo qua restore drill, không chỉ có snapshot.
- [ ] Có báo cáo GO/PAUSE/STOP/ESCALATE, owner, evidence và những điều chưa kiểm chứng.
## 26. Mẫu báo cáo một lần thay đổi storage/topology

Sau mỗi change window, lưu một report có thể truy vết. Ví dụ sau **chỉ là dữ liệu mẫu**, không phải manifest Kubernetes/Cassandra hay kết quả đo thật:

~~~yaml
change:
  id: "cassandra-k8s-staging-storage-2026-11"
  environment: "staging-isolated"
  owner: "cassandra-platform"
  operation: "pod-restart-with-existing-pvc"
  approval: "<change-record>"
versions:
  kubernetes: "<exact-version>"
  csi_driver: "<exact-driver-version>"
  operator: "<name-and-version-or-none>"
  cassandra: "<exact-version>"
  jdk: "<exact-version>"
  java_driver: "<exact-version>"
topology:
  cluster: "staging-cassandra"
  dc: "dc1"
  racks_or_zones: ["zone-a", "zone-b", "zone-c"]
  rf_in_dc: 3
storage:
  storage_class: "<actual-class>"
  volume_binding_mode: "<observed>"
  access_mode: "<observed>"
  reclaim_policy: "<observed>"
  pvc_before: "<uid-and-volume-handle>"
  pvc_after: "<uid-and-volume-handle>"
  data_directory_verified: true
  same_node_identity_verified: true
baseline:
  cql_successful_rps: "<measured>"
  read_p99_ms: "<measured>"
  logical_error_percent: "<measured>"
maintenance:
  pod_restart_count: "<measured>"
  volume_attach_seconds: "<measured>"
  cassandra_startup_seconds: "<measured>"
  streaming_bytes: "<measured-if-applicable>"
  compaction_backlog_peak: "<measured>"
after_change:
  ring_and_token_placement_verified: true
  read_write_by_partition_key_verified: true
  repair_status: "<verified-coverage-or-not-applicable>"
  cql_successful_rps: "<measured>"
  read_p99_ms: "<measured>"
  recovery_window_minutes: "<measured>"
dr:
  off_domain_backup_verified: true
  restore_drill_reference: "<controlled-evidence>"
  rpo_measured: "<value-or-not-measured>"
  rto_measured: "<value-or-not-measured>"
decision:
  status: "GO | PAUSE | STOP | ESCALATE"
  unresolved_issues: []
  next_owner_action: "<approved-action>"
~~~

Nếu không đo được một metric, ghi **NOT_MEASURED**. Đừng suy đoán trạng thái identity/replication từ Pod Ready. Log/report nên lưu **node aliases, run IDs và volume handles được kiểm soát** thay vì tài khoản, certificate private keys, payload/tenant IDs thật.

### 26.1. Các câu hỏi nghiệm thu không được bỏ sót

1. Pod có khởi động lại bằng **đúng PVC** và đúng Cassandra host ID/token?
2. Dữ liệu trên PVC có thật được đọc lại bằng **partition key và CL** phù hợp?
3. Cassandra placement/DC/rack có phù hợp fault domains, không chỉ số pods bằng ba?
4. P99/error budget của service Java có trong ngưỡng trong và sau bảo trì?
5. Compaction, repair/streaming và disk headroom có trở lại mức ổn định?
6. Bản backup có độc lập với node/zone và **đã restore thử** chưa?
7. Nếu node/PV đã mất, có làm **replace/rebuild đúng quy trình**, không chỉ tạo Pod mới?
8. Có dữ liệu cần xóa sau backup cutoff phải reconcile khi khôi phục không?
9. Có người chịu trách nhiệm xử lý các rủi ro còn lại và một stop gate rõ không?
10. Mọi kết luận có bằng chứng theo version/operator/CSI và environment thực tế không?

## 27. Tổng kết

**Vận hành Apache Cassandra trong container/Kubernetes là bài toán bảo toàn identity, dữ liệu và topology phân tán**, không chỉ chuyển một tiến trình Java vào Pod. Kubernetes có thể tái tạo Pod, cấp PVC và điều phối scheduling; nhưng **không tự hiểu token ownership, replication factor, consistency level, compaction/repair, tombstone hay tính đúng của dữ liệu nghiệp vụ**.

Thiết kế đúng phải bắt đầu từ **điều kiện môi trường**: dev/CI có thể dùng Docker single-node và dữ liệu tạm; staging cần đại diện cho storage/zone/traffic; production cần **PV/PVC/CSI có performance, fault domain và retention được kiểm chứng**, Cassandra-aware operator hoặc runbook đủ năng lực, topology DC/rack phù hợp, graceful lifecycle/probes không gây restart storm, resource headroom và bảo mật end-to-end.

**Persistent volume không thay replication, replication không thay backup, CSI snapshot không chứng minh Cassandra-consistent restore, và Pod Ready không chứng minh data correctness.** Sau mọi restart, rollout, zone fault hay node replacement, phải đối chiếu **Cassandra ring/host ID/token, PVC identity, RF/CL, CQL theo partition key, Java API p99/errors, repair/compaction/streaming và khả năng phục hồi từ backup**.

Nguyên tắc vận hành cuối cùng là **đánh giá môi trường → triển khai có kiểm soát → quan sát cả Kubernetes lẫn Cassandra → kiểm chứng dữ liệu và SLO → giữ bằng chứng → GO/PAUSE/STOP theo runbook**. Chỉ khi những lớp này đều được kiểm tra, việc tự động hóa mới giúp Cassandra phục hồi đáng tin cậy thay vì chỉ tạo lại những container trông có vẻ khỏe.
