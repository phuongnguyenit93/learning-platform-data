# Đánh giá Kubernetes và hệ lưu trữ trước khi triển khai có trạng thái

Kubernetes rất hiệu quả khi quản lý ứng dụng có thể khởi tạo lại ở bất kỳ node nào. Tuy nhiên, **Neo4j là một hệ quản trị cơ sở dữ liệu có trạng thái**: dữ liệu node, relationship, property, index và transaction log phải được giữ nhất quán dù container, node hoặc cụm Kubernetes gặp sự cố. Một pod tự khởi động lại thành công không chứng minh dữ liệu còn nguyên, index sẵn sàng hay giao dịch đã được phục hồi chính xác.

Bài thuộc chương **Triển khai** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Neo4j sử dụng **property graph** để lưu dữ liệu liên kết, truy vấn bằng Cypher, tối ưu bằng index/constraint và tích hợp Java Driver hoặc Spring Data Neo4j. Khi đưa hệ thống này lên Kubernetes, các quyết định về **StatefulSet, PersistentVolume, StorageClass, CSI, topology, sao lưu, tài nguyên, giám sát và khôi phục** tác động trực tiếp đến độ bền giao dịch và khả năng phục vụ của ứng dụng.

Mục tiêu không phải khẳng định “Neo4j chạy được trong Kubernetes”, mà là đánh giá **một hạ tầng cụ thể có đáp ứng yêu cầu của database hay không**. Sau bài học, bạn có thể:

- So sánh Kubernetes với VM/bare metal và dịch vụ Neo4j được quản lý như Aura theo nhu cầu nghiệp vụ.
- Giải thích vì sao StatefulSet, PVC/PV và quy tắc **mỗi Neo4j server có vùng dữ liệu riêng** là nền tảng triển khai an toàn.
- Đánh giá StorageClass/CSI về durability, `fsync`, latency, topology, quyền truy cập, resize và cách thu hồi volume.
- Phân biệt **nhiều pod** với **Neo4j cluster thực sự** có discovery, routing, đồng thuận và quorum.
- Lên kế hoạch tài nguyên, probe, backup/restore, nâng cấp, bảo mật và kiểm thử lỗi.
- Dựng checklist chấp nhận hoặc từ chối triển khai dựa trên RPO/RTO và bằng chứng vận hành.

> **Giới hạn phiên bản:** Tên setting Neo4j, biểu đồ Helm, khả năng clustering, backup và cấu hình dịch vụ phụ thuộc phiên bản/edition/gói triển khai. Mọi YAML minh họa đều cần điều chỉnh theo chart/operator, image và CSI đã được tổ chức kiểm chứng. Không coi ví dụ một pod ở dưới là cấu hình production có tính sẵn sàng cao.

## 1. Câu hỏi đầu tiên: Có nên dùng Kubernetes không?

**Kubernetes không tự làm database bền vững hơn.** Nó giúp triển khai, sắp lịch, giám sát pod và thay thế tiến trình thất bại. Nhưng việc dữ liệu có sống sót sau lỗi máy hay không vẫn do **Neo4j, hệ lưu trữ và quy trình khôi phục** quyết định.

| Lựa chọn | Thuận lợi | Đánh đổi | Phù hợp khi |
| --- | --- | --- | --- |
| **Neo4j trên VM/bare metal** | Kiểm soát đường đi I/O, filesystem, backup và nguồn lực rõ; ít lớp điều phối hơn. | Đội vận hành phải tự quản lý VM, triển khai, failover, patch, monitor. | Có đội DBA/SRE và cần kiểm soát storage chi tiết. |
| **Neo4j self-managed trên Kubernetes** | Tích hợp GitOps, tài nguyên, secret, giám sát, scheduling và quy trình triển khai của nền tảng. | Thêm CSI/PVC, scheduler, network, probe, sự kiện rescheduling, quyền và rủi ro operator/chart. | Đã có nền tảng Kubernetes trưởng thành và vận hành stateful workload được. |
| **Dịch vụ Neo4j được quản lý** | Nhà cung cấp xử lý nhiều công việc hạ tầng, backup/HA theo gói dịch vụ. | Giới hạn vùng, gói, khả năng cấu hình, chi phí và quyền truy cập hạ tầng. | Muốn tập trung vào ứng dụng và chấp nhận tính năng/SLA của dịch vụ. |

Các câu hỏi cần trả lời **trước** khi viết manifest:

1. Hệ thống chấp nhận mất bao nhiêu dữ liệu (**RPO**) và ngừng phục vụ trong bao lâu (**RTO**)?
2. Mất một pod, một node, một availability zone hay toàn cluster Kubernetes có nằm trong phạm vi bắt buộc khôi phục?
3. Có cần Neo4j Enterprise/cluster, backup online, công cụ quản lý role hay tính năng khác không?
4. Đội vận hành có đủ khả năng kiểm chứng hiệu năng CSI, khôi phục backup, xử lý PV/PVC và cập nhật Neo4j không?
5. Có yêu cầu vị trí dữ liệu, mã hóa, mạng riêng, audit, phân quyền tenant và giới hạn ngân sách nào?
6. Chi phí vận hành Kubernetes có được bù bằng lợi ích chuẩn hóa triển khai không?

Nếu chưa có câu trả lời cho **RPO, RTO và phục hồi storage**, việc viết StatefulSet nên được coi là thử nghiệm kỹ thuật, chưa phải phê duyệt production.

## 2. Xác định đúng ranh giới trạng thái

Một hệ thống Neo4j trong Kubernetes thường có các lớp:

~~~text
Client Java Driver / Spring Data Neo4j
              |
           Service
              |
          Pod Neo4j
              |
      +-------+-------+
      |               |
   Data store       Neo4j process
   indexes          heap/page cache
   metadata         transactions
      |
   /data mount
      |
 PersistentVolumeClaim (PVC)
      |
 PersistentVolume (PV)
      |
 StorageClass / CSI / volume vật lý
~~~

| Lớp | Được Kubernetes đảm bảo gì? | Không tự đảm bảo gì? |
| --- | --- | --- |
| Pod/container | Tạo lại tiến trình theo controller và policy. | Dữ liệu trong filesystem tạm không được bảo toàn. |
| StatefulSet | Identity/ordinal và cơ chế quản lý pod, volume claim theo template. | Không tự biến nhiều tiến trình thành một Neo4j cluster. |
| PVC/PV | Ràng buộc claim tới volume theo cơ chế StorageClass/CSI. | Không tự chứng minh database nhất quán hoặc volume có `fsync` bền vững. |
| CSI/storage backend | Cấp phát, gắn và tháo volume theo driver. | Không phải mọi backend có cùng độ trễ, semantics hoặc failure domain. |
| Neo4j | Quản lý transaction, store, index và phục hồi theo engine. | Không bảo vệ được dữ liệu nếu storage mất hoặc dùng sai cách. |
| Backup độc lập | Cung cấp đường phục hồi khi dữ liệu gốc bị hỏng/mất. | Không có giá trị nếu chưa kiểm thử restore và tính nhất quán. |

### 2.1. Dữ liệu không nên ở ephemeral volume

`emptyDir`, lớp filesystem ghi tạm của container hay volume chỉ tồn tại theo vòng đời pod **không phải chỗ lưu bền vững cho Neo4j production**. Khi pod bị thay mới, dữ liệu có thể biến mất. Chỉ sử dụng ephemeral storage cho tệp tạm được phép mất và đã có đường tái tạo.

Neo4j thường dùng thư mục `/data` trong container image chính thức để giữ dữ liệu. Trong manifest minh họa, PVC phải được mount đến thư mục dữ liệu phù hợp với image và phiên bản thật. Không giả định mount ở `/logs` hoặc `/import` có thể thay cho dữ liệu giao dịch.

### 2.2. Một volume dữ liệu không phải nơi nhiều server đồng thời ghi

**Không mount cùng một thư mục store Neo4j để hai pod độc lập ghi đồng thời**, kể cả StorageClass cho phép `ReadWriteMany`. Filesystem chia sẻ không tự biến store thành database đa tiến trình; nó có thể gây lock conflict hoặc hỏng dữ liệu.

Trong một Neo4j cluster đúng nghĩa, **mỗi server có một local store riêng trên PVC riêng**, còn việc nhân bản và đồng thuận được Neo4j thực hiện qua protocol cluster. Kubernetes chỉ cung cấp scheduling, network và các volume bền vững để từng server duy trì trạng thái.

## 3. Phân tích yêu cầu lưu trữ từ tải nghiệp vụ

Hãy xuất phát từ những truy vấn Cypher và luồng ghi thực tế:

| Workload | Yêu cầu storage đáng chú ý |
| --- | --- |
| Tra cứu node bằng index với độ trễ thấp | Truy cập ngẫu nhiên, p95/p99 latency, page-cache hit và IOPS. |
| Duyệt relationship bậc cao/nhiều bước | Working set lớn, page cache, I/O khi miss cache. |
| Ghi transaction nhỏ liên tục | Độ trễ ghi đồng bộ và khả năng flush bền vững. |
| Import/batch cập nhật nhiều node | Throughput ghi, transaction log, temporary headroom, tốc độ index update. |
| Tạo lại index/full-text/vector index | CPU, I/O, dung lượng index và đỉnh sử dụng đĩa. |
| Backup/restore | Băng thông đọc/ghi lớn, vị trí lưu bản sao độc lập và thời gian phục hồi. |
| GDS projection | Chủ yếu tốn RAM và CPU; vẫn ảnh hưởng toàn hệ thống khi chia sẻ node. |

Storage backend phải có semantics phù hợp cho database: **ghi, đồng bộ dữ liệu xuống môi trường lưu trữ và báo thành công đúng lúc**. Không chỉ dùng benchmark throughput tuần tự rồi coi đó là bằng chứng phù hợp. Với durability, phải xác minh khả năng bảo toàn dữ liệu khi process, node hoặc volume gặp sự cố theo cam kết của nhà cung cấp và driver.

### 3.1. Bảng tiêu chí kiểm chứng với nhà cung cấp CSI

| Tiêu chí | Câu hỏi cần xác minh | Bằng chứng cần có |
| --- | --- | --- |
| Durability và `fsync`/flush | Sau khi thao tác đồng bộ báo thành công, dữ liệu có được bảo vệ đúng mức khi node chết không? | Tài liệu storage, hỗ trợ vendor và thử lỗi có kiểm soát. |
| Latency | p50/p95/p99 của đọc/ghi ngẫu nhiên và đồng bộ ghi ở tải đại diện? | Benchmark staging và metric production thử nghiệm. |
| IOPS/throughput | Volume có giới hạn theo loại disk, dung lượng hoặc node không? | Thông số hạ tầng và đo lúc cao điểm. |
| Access mode | CSI hỗ trợ `ReadWriteOnce` hay `ReadWriteOncePod`? | StorageClass/CSI driver, kết quả thử mount. |
| Topology | Volume gắn với zone nào, pod có thể chạy ở đâu? | PV node affinity và thử reschedule. |
| Attach/detach | Khi node cũ mất kết nối, thời gian chuyển volume sang node mới là bao lâu? | Chaos test và event từ CSI. |
| Volume expansion | Có hỗ trợ mở rộng online/offline và filesystem resize không? | StorageClass + thử nghiệm PVC. |
| Snapshot | Có VolumeSnapshot và semantics phù hợp không? | CSI capability và kiểm thử restore nhất quán. |
| Reclaim | Xóa PVC có xóa luôn volume vật lý không? | `reclaimPolicy`/PVC retention, diễn tập xóa. |
| Encryption | Có mã hóa at rest/in transit và quản lý khóa phù hợp không? | Hồ sơ nhà cung cấp và kiểm tra vận hành. |

Không dùng một dòng marketing “SSD nhanh” để thay cho phép thử **crash recovery và độ bền sau commit**.

## 4. StorageClass, PVC và access mode

### 4.1. Đọc thông tin trước khi cấp phát

Các lệnh Kubernetes chỉ để **quan sát**, không sửa dữ liệu:

~~~bash
kubectl get storageclass
kubectl describe storageclass fast-csi-rwo
kubectl get csidrivers
kubectl get nodes -L topology.kubernetes.io/zone
~~~

`fast-csi-rwo` chỉ là **tên giả định**. Nếu cluster không có StorageClass đó, thay bằng tên đã được đội hạ tầng xác minh. Đối với một StorageClass, xem `provisioner`, `volumeBindingMode`, `allowVolumeExpansion`, `reclaimPolicy` và topology/các tham số của driver. Không suy diễn chất lượng thực tế chỉ từ tên.

### 4.2. Chọn access mode đúng mục đích

| Access mode | Ý nghĩa ở mức PVC/Kubernetes | Lưu ý cho Neo4j |
| --- | --- | --- |
| `ReadWriteOnce` (RWO) | Volume có thể được gắn đọc/ghi theo giới hạn ở cấp **node**. | Phổ biến với block volume; không tự ngăn nhiều pod trên cùng một node dùng chung volume. |
| `ReadWriteOncePod` (RWOP) | Chỉ một pod được sử dụng volume read/write trong phạm vi cluster, khi driver/cấp Kubernetes hỗ trợ. | Có thể giúp thực thi “một pod giữ một PVC”, nhưng không thay thế an toàn transaction/Neo4j cluster. |
| `ReadWriteMany` (RWX) | Nhiều node/pod có thể mount đọc/ghi theo khả năng driver. | **Không** được dùng để hai Neo4j server ghi chung cùng store. |
| `ReadOnlyMany` (ROX) | Nhiều node có thể mount chỉ đọc. | Không phù hợp cho data directory của Neo4j đang cần ghi. |

Khả năng mode cụ thể tùy CSI driver và loại volume. `RWOP` chỉ có trên những điều kiện phiên bản Kubernetes/CSI hỗ trợ; cần xác minh thực tế. `RWO` và `RWOP` cũng không đảm bảo failover nhanh nếu volume bị ràng buộc bởi zone hoặc node không thể detach.

### 4.3. Reclaim policy là quyết định về mất dữ liệu

Với PV cấp phát động, `reclaimPolicy: Delete` có thể dẫn tới **xóa volume vật lý khi PVC được xóa**. `Retain` giữ PV sau khi claim được giải phóng nhưng đòi quy trình thu hồi, làm sạch và tái sử dụng do người quản trị kiểm soát.

Không coi `Retain` là backup; volume vẫn có thể hỏng hoặc bị xóa qua hệ thống storage. Trước khi áp dụng manifest phải kiểm tra:

- StorageClass mặc định dùng `Delete` hay `Retain`.
- StatefulSet sử dụng cơ chế lưu/thu hồi PVC nào khi scale down hoặc xóa controller.
- Backup độc lập có tồn tại và đã restore được chưa.
- Quy trình xóa namespace, GitOps prune và teardown có được bảo vệ khỏi việc xóa dữ liệu thật không.

Đừng tin rằng “xóa StatefulSet không bao giờ xóa PVC” trong mọi cấu hình: phiên bản Kubernetes và `persistentVolumeClaimRetentionPolicy` có thể thay đổi hành vi. Hãy kiểm chứng policy của chính tài nguyên sẽ triển khai.

## 5. Chọn topology: local PV, block volume theo zone hay network storage?

| Loại lưu trữ | Điểm mạnh | Rủi ro cần xét | Nhận định |
| --- | --- | --- | --- |
| **Local SSD/NVMe qua local PV** | Latency/IOPS thường tốt, ít lớp mạng. | Volume gắn với máy; node hỏng có thể khiến dữ liệu không attach lại được nơi khác. | Cần nhân bản Neo4j/backup và kế hoạch thay node; không tự phù hợp HA. |
| **Block volume bền vững theo zone** | Có thể attach lại tới node khác trong cùng zone, hỗ trợ snapshot/resize tùy cloud. | Ràng buộc zone, attach/detach delay, IOPS giới hạn bởi tier. | Thường đáng đánh giá cho stateful workload nếu đạt thử nghiệm. |
| **Network filesystem/RWX** | Thuận tiện chia sẻ file và mở rộng quyền mount. | Latency, locking, flush semantics, throughput và hành vi lúc network partition có thể không hợp yêu cầu database. | Chỉ chọn khi **Neo4j và backend cụ thể được hỗ trợ/kiểm chứng**; không dùng chia sẻ store cho nhiều server. |
| **Dịch vụ managed storage/DB** | Ít công tự quản lý node/volume. | Phụ thuộc SLA, version, khu vực, quyền và giá. | So sánh theo RPO/RTO và chi phí vận hành tổng thể. |

Không có đáp án “network storage luôn chậm” hoặc “local SSD luôn tốt”: workload, caching, IOPS, khu vực và tầng provisioner khác nhau. Tuy nhiên, độ trễ đuôi và semantics ghi bền vững là **điều kiện bắt buộc phải đo**, không thể phán đoán bằng tên loại storage.

### 5.1. VolumeBindingMode và ràng buộc zone

`WaitForFirstConsumer` cho phép việc bind/provision volume xét đến vị trí dự kiến của pod trong các triển khai hỗ trợ. Điều này có thể giảm trường hợp PVC cấp phát ở zone mà pod không thể chạy. Nhưng sau khi volume đã được cấp phát trong một zone, **không có nghĩa pod và dữ liệu tự chuyển sang mọi zone khác được**.

Khi node hỏng:

1. StatefulSet cố đưa pod trở lại theo khả năng scheduler.
2. Scheduler phải tìm node phù hợp với **PV topology và affinity**.
3. CSI phải hoàn tất detach/attach an toàn.
4. Neo4j mở store, chạy recovery cần thiết rồi mới thực sự sẵn sàng.

Nếu không có node phù hợp ở cùng zone, pod có thể ở trạng thái `Pending` dù toàn cluster Kubernetes vẫn dư CPU/RAM. **Sẵn sàng ở cấp Kubernetes không đồng nghĩa volume có thể di chuyển xuyên zone.**

## 6. Dự trù dung lượng và I/O trước ngày triển khai

Đừng lấy kích thước dữ liệu nguồn (CSV, JSON, bảng RDBMS) làm dung lượng Neo4j chính xác. Cùng một dữ liệu có thể được biểu diễn bằng rất nhiều node, relationship, property và index khác nhau.

Một bảng ngân sách mẫu:

| Thành phần | Vì sao cần chừa chỗ? | Nguồn ước lượng |
| --- | --- | --- |
| Node/relationship/property store | Dữ liệu bền vững và metadata Neo4j. | Import thử trên bản dữ liệu đại diện. |
| Index và constraint-backed index | Tra cứu property/lookup/full-text/vector. | Đo sau build trên dữ liệu thử đúng schema. |
| Transaction logs | Ghi, import, checkpoint/recovery theo chính sách. | Write rate và retention/catch-up đã thiết kế. |
| Đỉnh lúc migrate/index rebuild | Công việc tạm thời cần không gian bổ sung. | Rehearsal nâng cấp/index population. |
| Logs khác và file tạm | Ứng dụng, server log, import, staging. | Vị trí mount và retention thật. |
| Backup/snapshot | Khôi phục độc lập và dung lượng lưu bản sao. | Công cụ backup và object store; tránh dùng chung volume. |
| Headroom | Sự cố, volume expansion, maintenance, tăng trưởng bất thường. | RPO/RTO, tốc độ tăng và thời gian phản ứng. |

### 6.1. Ví dụ tính ngân sách

Giả sử một bản import đại diện cho kết quả:

- Store: **220 GiB**.
- Index: **55 GiB**, giả định **chưa nằm trong số store** đã đo.
- Transaction logs tại đỉnh bulk import: **80 GiB**.
- Các file/tệp vận hành khác: **15 GiB**.
- Headroom được phê duyệt: **30%** trên tổng nhu cầu trước headroom.

Khi các phần **không chồng lấp nguồn đo**, nhu cầu trước headroom là `220 + 55 + 80 + 15 = 370 GiB`; thêm dự phòng 30% cho kết quả `481 GiB`. Đây là **ví dụ minh họa**, không phải dung lượng khuyến nghị cho mọi Neo4j.

Nếu metric “store size” đã bao gồm index, cộng thêm 55 GiB sẽ **đếm trùng**. Nếu data và transaction log nằm trên **hai PVC khác nhau**, phải lập ngân sách/headroom theo từng volume; 481 GiB tổng không bảo đảm từng volume đủ chỗ.

### 6.2. Đo I/O và fsync trên đúng StorageClass

Đề xuất thử ở staging trên một volume riêng giống production:

1. Đo random read/write và latency p50/p95/p99 dưới tải đọc/ghi hỗn hợp.
2. Đo commit latency của Neo4j khi có concurrent transactions, không chỉ benchmark thông lượng tệp.
3. Chạy import thử, cập nhật property và tạo index để xem peak storage/log size.
4. Tạo lỗi có kiểm soát cho pod/node **trong môi trường thử** rồi xác minh dữ liệu đã commit.
5. Đo thời gian attach volume, khởi động lại, store recovery và phục hồi hoạt động đọc/ghi.
6. Lặp lại khi volume gần mức sử dụng cao, vì hiệu năng có thể khác lúc còn rất trống.

Không chạy benchmark ghi phá hủy dữ liệu như `fio --filename=<đường dẫn store Neo4j>` trên volume production đang phục vụ; đo trên volume staging độc lập. Ưu tiên benchmark **đi từ ứng dụng → Neo4j** để kiểm chứng cả driver, transaction và index.

## 7. Manifest đơn node: đọc để hiểu cấu trúc, không coi là HA

Đoạn YAML minh họa một **StatefulSet chỉ có một Neo4j server**, với một PVC gắn vào `/data`. Nó thích hợp để hiểu ý tưởng và thử ở môi trường riêng sau khi có secret, namespace, StorageClass phù hợp.

~~~yaml
# Yêu cầu namespace graph-demo, Secret neo4j-demo-auth
# và StorageClass fast-csi-rwo đã tồn tại.
# image neo4j:5.26.0 chỉ là ví dụ phiên bản cố định;
# chọn lại image và patch level đã được kiểm thử/hỗ trợ.
apiVersion: v1
kind: Service
metadata:
  name: neo4j-demo-headless
  namespace: graph-demo
spec:
  clusterIP: None
  selector:
    app: neo4j-demo
  ports:
    - name: bolt
      port: 7687
      targetPort: 7687
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: neo4j-demo
  namespace: graph-demo
spec:
  serviceName: neo4j-demo-headless
  replicas: 1
  selector:
    matchLabels:
      app: neo4j-demo
  template:
    metadata:
      labels:
        app: neo4j-demo
    spec:
      terminationGracePeriodSeconds: 180
      containers:
        - name: neo4j
          image: neo4j:5.26.0
          ports:
            - name: bolt
              containerPort: 7687
          env:
            - name: NEO4J_AUTH
              valueFrom:
                secretKeyRef:
                  name: neo4j-demo-auth
                  key: neo4jAuth
            - name: NEO4J_server_memory_heap_initial__size
              value: "2G"
            - name: NEO4J_server_memory_heap_max__size
              value: "2G"
            - name: NEO4J_server_memory_pagecache_size
              value: "3G"
          resources:
            requests:
              cpu: "2"
              memory: "8Gi"
            limits:
              memory: "8Gi"
          volumeMounts:
            - name: data
              mountPath: /data
          startupProbe:
            tcpSocket:
              port: 7687
            periodSeconds: 10
            failureThreshold: 60
          readinessProbe:
            tcpSocket:
              port: 7687
            periodSeconds: 10
            failureThreshold: 3
          livenessProbe:
            tcpSocket:
              port: 7687
            periodSeconds: 20
            failureThreshold: 6
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes:
          - ReadWriteOnce
        storageClassName: fast-csi-rwo
        resources:
          requests:
            storage: 100Gi
~~~

**Những giới hạn phải hiểu trước khi áp dụng:**

- `neo4j:5.26.0` là tag minh họa, không phải khuyến nghị phiên bản mới nhất. Production nên pin image/version đã kiểm thử, kiểm tra tương thích server/driver/edition và có chính sách vá lỗ hổng, có thể dùng digest theo quy trình supply-chain.
- Secret `neo4j-demo-auth` chứa key `neo4jAuth` có giá trị phù hợp với quy ước `NEO4J_AUTH` của image (ví dụ dạng `neo4j/<password>` khi khởi tạo mới). **Không nhúng password thật vào manifest/Git.** Trên store đã khởi tạo, thay đổi biến môi trường này không tự thay password đã lưu.
- Các setting heap/page cache trên **đúng image/version** phải được kiểm tra; memory request/limit 8 GiB chỉ là ví dụ. Ngoài heap và page cache còn có off-heap/native memory, transaction/query memory và OS overhead.
- TCP probe chỉ xác minh cổng có nhận kết nối, **không chứng minh Cypher giao dịch thành công, database online hoàn toàn hoặc node sẵn sàng tham gia cluster**. Hệ thống thật cần health/readiness phù hợp khả năng driver/version.
- PVC 100 GiB có thể không đủ nếu store, index, transaction logs cùng nằm ở đó; đừng dùng con số này cho một workload có yêu cầu lớn.
- Service headless phục vụ danh tính DNS nội bộ của StatefulSet, **không tự cấu hình routing/advertised addresses hay external TLS**.
- `replicas: 1` nghĩa là không có Neo4j HA. Việc đổi thành `replicas: 3` **không** tự tạo Neo4j cluster và có thể sinh nhiều Neo4j standalone độc lập với dữ liệu khác nhau.

### 7.1. Quan sát pod và PVC sau khi triển khai ở staging

~~~bash
kubectl -n graph-demo get statefulsets
kubectl -n graph-demo get pods -o wide
kubectl -n graph-demo get pvc
kubectl get pv
kubectl -n graph-demo describe pod neo4j-demo-0
kubectl -n graph-demo get events --sort-by=.lastTimestamp
~~~

Các lệnh đọc trạng thái; cần quyền Kubernetes RBAC tương ứng. Hãy kiểm tra `PVC Bound`, PV/zone, sự kiện CSI, container restarts và pod readiness. Không vội xoá PVC `Pending` để “thử lại” nếu nó đã chứa dữ liệu hay đang gắn với một volume cần giữ.

## 8. StatefulSet mang identity ổn định, không thay thế database clustering

StatefulSet quản lý pod có tên theo ordinal và volume claim theo template:

~~~text
neo4j-demo-0
   |
   +--> data-neo4j-demo-0 (PVC)
              |
              +--> PV / storage backend
~~~

Khi pod bị thay thế, Kubernetes cố gắn lại PVC đã ràng buộc và giữ identity; quá trình này vẫn phụ thuộc **khả năng attach/detach, topology, quy tắc scheduling và an toàn tiến trình cũ đã ngừng ghi**.

Ở cluster Neo4j đúng nghĩa:

~~~text
       Neo4j cluster
     (quorum/consensus)

neo4j-server-A   neo4j-server-B   neo4j-server-C
      |                 |                 |
     PVC-A             PVC-B             PVC-C
      |                 |                 |
    PV-A              PV-B              PV-C
~~~

Mỗi server có **store độc lập** và có cấu hình cluster tương thích. Kubernetes cung cấp network/volume/process; Neo4j chịu trách nhiệm replication, leader/primary role, consensus và phục vụ query theo khả năng edition/version.

### 8.1. Điều kiện của Neo4j cluster

Đối với kiến trúc cần chịu lỗi một server, hãy đánh giá:

- Edition và phiên bản Neo4j có hỗ trợ cluster/backup cần thiết không.
- Số primary/secondary và **majority/quorum** theo cơ chế cluster của phiên bản đó; thường cần ít nhất ba primary phân bố lỗi độc lập để duy trì quorum sau khi mất một primary.
- Discovery và địa chỉ quảng bá (*advertised addresses*) ổn định, phân giải được giữa các pod và từ client liên quan.
- Mạng nội bộ, TLS, chứng chỉ/DNS, cổng cần thiết và chính sách network.
- Từng server có PVC riêng đủ dung lượng và hiệu năng, không share store.
- Sắp lịch trải rộng node/zone, không gom toàn bộ primary lên cùng một máy.
- Chiến lược rolling upgrade, backup, scale up/down và thay thế server theo tài liệu đúng version.

**Không đồng nhất replicas của Kubernetes với số bản sao dữ liệu nhất quán.** Một lệnh scale pod chỉ là thao tác controller; thêm/bỏ thành viên database phải đi qua quy trình Neo4j cluster được hỗ trợ.

### 8.2. Những lớp sẵn sàng cao khác nhau

| Lỗi | Kubernetes có thể xử lý | Neo4j/storage vẫn phải đáp ứng |
| --- | --- | --- |
| Container crash | Restart container hoặc thay pod. | Store recovery và query readiness. |
| Node worker chết | Reschedule pod nếu có node phù hợp. | Reattach volume an toàn hoặc database failover qua server khác. |
| Mất một zone | Scheduler có thể đặt workload ở zone khác nếu resource phù hợp. | Volume zonal có thể không di chuyển; cần cluster/backup phù hợp. |
| Một Neo4j server không trả lời | Pod/readiness có thể phát hiện mức độ nào đó. | Quorum, leader election/routing và transaction semantics. |
| Hỏng store/volume vật lý | Kubernetes không tự tái tạo dữ liệu đã mất. | Replication hợp lệ, backup/restore và quy trình tái dựng. |
| Xóa nhầm database/PVC | Controller có thể phản ứng theo chính sách nhưng không “undo” logic. | Backup, retention, audit và bảo vệ thao tác phá hủy. |
| Mất toàn Kubernetes cluster | Không còn scheduler/cấu hình trong cluster đó. | Bản sao dữ liệu độc lập và diễn tập disaster recovery. |

Trong một số kịch bản failover, **client phải retry các transaction phù hợp** và dùng URI/routing mode, driver version và địa chỉ quảng bá đúng. Sử dụng `neo4j://` không tự sửa DNS, TLS, quyền mạng hay routing topology cấu hình sai.

## 9. Scheduling, anti-affinity và PodDisruptionBudget

Một cluster có ba Neo4j server đặt trên một worker Kubernetes không chịu được lỗi worker đó. Khi thiết kế HA:

1. Dùng `podAntiAffinity` hoặc `topologySpreadConstraints` thích hợp để phân bố pod qua hostname và zone khả dụng.
2. Xem **PV node affinity** để đảm bảo volume có thể gắn tới vị trí scheduler chọn.
3. Dùng `PodDisruptionBudget` (PDB) để giảm nguy cơ các **voluntary eviction** cùng lúc làm mất quorum.
4. Xem `priorityClassName`, tài nguyên đảm bảo và capacity dự phòng để tránh pod quan trọng bị đẩy khỏi node khi có áp lực.
5. Kiểm tra hành vi autoscaler và node drain: PVC có thể cần thời gian detach/attach, Neo4j có thể cần recovery lâu.

**PDB không ngăn được node chết đột ngột**, mất zone hoặc lỗi mạng; nó chỉ tác động tới một số eviction có chủ ý qua Kubernetes eviction API. Đừng đặt PDB quá chặt khiến node maintenance không thể hoàn tất, nhưng cũng đừng để một lần drain làm rơi toàn bộ primary cần quorum.

Nếu có ít zone hơn số pod cần trải rộng, một `DoNotSchedule` không phù hợp có thể để pod chờ mãi. Chọn ràng buộc phù hợp với SLA và thực tế cluster, rồi diễn tập pod restart, node drain và zone failure.

## 10. Readiness, startup và liveness không được gây lỗi dây chuyền

Neo4j có thể mất nhiều thời gian khởi động do:

- Volume attach chậm, I/O bị giới hạn.
- Store recovery sau crash hoặc replay transaction logs.
- Index population/rebuild sau bảo trì hoặc restore.
- Quorum/discovery của cluster chưa ổn định.
- Page cache cần được làm ấm và query service chưa đạt SLO.

| Probe | Mục tiêu | Sai lầm thường gặp |
| --- | --- | --- |
| **startupProbe** | Cho phép giai đoạn khởi động dài mà chưa dùng liveness để giết container. | Cấu hình timeout quá thấp khiến DB bị restart liên tục lúc recovery. |
| **readinessProbe** | Quyết định pod có nhận traffic qua Service hay không. | Chỉ check TCP và coi DB đã xử lý transaction/query bình thường. |
| **livenessProbe** | Phát hiện tiến trình kẹt cần restart. | Dùng một Cypher nặng/đôi khi timeout làm restart database đang bận. |

Probe phải **nhẹ, an toàn, có quyền tối thiểu và không rò rỉ credential**. Đừng truyền password trực tiếp trong command line probe nếu nó có thể xuất hiện trong log/describe/process list. Đánh giá các health procedure hoặc endpoint được image/chart hỗ trợ theo phiên bản.

Nếu một liveness probe khởi động lại pod trong khi Neo4j đang recovery lâu, nó có thể kéo dài downtime vô hạn. Hãy đo thời gian startup/recovery thật để đặt failure threshold và termination grace period.

### 10.1. Graceful shutdown

Khi Kubernetes muốn thay pod, nó gửi tín hiệu shutdown theo vòng đời container; Neo4j cần thời gian dừng an toàn. Cấu hình `terminationGracePeriodSeconds` quá ngắn có thể khiến process bị kill giữa công việc còn dang dở và tăng thời gian recovery ở lần khởi động sau.

Đặt thời gian phù hợp với tải/transaction thực tế. Kubernetes vẫn có thể mất node đột ngột không có graceful shutdown, nên **đường crash recovery** phải được thử, không chỉ happy-path rolling restart.

## 11. Tài nguyên CPU, RAM, page cache và cgroup

Neo4j không chỉ dùng Java heap. Ngân sách RAM của pod cần xét:

| Nhóm | Vai trò |
| --- | --- |
| Java heap | Đối tượng Java và bộ nhớ runtime/GC. |
| Neo4j page cache | Cache các trang store/index được truy cập thường xuyên. |
| Native/off-heap memory | Transaction/query, driver/native structures và các hoạt động khác. |
| Bộ nhớ hệ điều hành/container | Stack, buffers và overhead. |
| GDS nếu chạy | Projection/algorithm có thể cần RAM lớn ngoài ngân sách query bình thường. |

Nếu pod có `memory limit: 8Gi` nhưng heap 6Gi và page cache 4Gi, tổng dự trù đã vượt limit trước khi cộng các khoản khác. Kubernetes có thể OOM-kill pod, khiến database restart và phải recovery. **Không dùng `requests.memory` như một giới hạn tiêu thụ**: limit mới ảnh hưởng trực tiếp tới OOM theo cgroup.

CPU:

- Đặt request phù hợp để pod được scheduler cấp nguồn lực ổn định.
- Cân nhắc CPU limits: throttling có thể làm tăng tail latency; phải đo theo chính sách hạ tầng.
- Dự trù CPU cho index population, backup, GC, GDS và failover, không chỉ query trung bình.

I/O:

- Đo disk latency và queue depth ở hạ tầng.
- Xem Neo4j page cache hit/miss, transaction latency và thời gian log flush khi có metrics phù hợp.
- Với volume phụ thuộc giới hạn IOPS theo dung lượng, mở rộng storage có thể ảnh hưởng đồng thời throughput và chi phí.

Không sử dụng cùng một biểu đồ memory để kết luận “Neo4j còn dư page cache” nếu metric chỉ thể hiện heap JVM. Quan sát phải phân loại nguồn.

## 12. Backup và restore: điều kiện không thể bỏ qua

**PVC bền vững không phải backup. Neo4j cluster không phải backup. CSI snapshot cũng không tự là backup nhất quán của một database đang ghi.**

Những sự kiện như xóa nhầm dữ liệu bằng Cypher, lỗi ứng dụng cập nhật hàng loạt hay credential bị chiếm quyền có thể làm **mọi bản sao cluster** mang cùng dữ liệu sai. Cần bản sao độc lập, thời điểm phù hợp và khả năng restore có kiểm chứng.

### 12.1. Chọn cơ chế backup theo edition và phiên bản

Với Neo4j self-managed, hãy kiểm tra các công cụ **online/offline backup và restore** được hỗ trợ trên đúng edition/version. Trong một số phiên bản, các thao tác backup có thể cần kết nối dịch vụ/port riêng và có điều kiện cho database/cluster. Với Aura, dùng chính sách snapshot/backup do gói dịch vụ cung cấp.

Một backup plan phải ghi rõ:

- **RPO:** chấp nhận mất bao nhiêu phút/giờ dữ liệu khi khôi phục?
- **RTO:** tổng thời gian phát hiện, chuẩn bị môi trường, restore, chạy recovery, xây index, xác thực dữ liệu và mở traffic là bao lâu?
- **Retention:** giữ bao nhiêu điểm backup, ở vị trí/khóa nào, và có bản sao ngoài failure domain chính không?
- **Integrity:** có checksum/xác minh tệp và khả năng giải mã bản sao không?
- **Restore drill:** có chạy phục hồi tới một môi trường khác và kiểm tra node/relationship/constraint/Cypher không?
- **Quy trình cấp lại quyền:** secret, certificate, địa chỉ cluster và DNS sau restore xử lý ra sao?

### 12.2. CSI VolumeSnapshot: hữu ích nhưng không mặc định application-consistent

Một snapshot ở tầng volume thường chỉ cho biết trạng thái tại thời điểm snapshot theo cơ chế storage. Với database đang ghi, nó có thể tương đương **crash-consistent** thay vì **application-consistent**. Khi Neo4j dùng nhiều volume cho store và transaction logs, snapshot riêng lẻ không có nghĩa các phần được chụp tại cùng một điểm nhất quán.

Do đó:

1. Xác minh Neo4j và storage vendor có **quy trình snapshot nhất quán được hỗ trợ** hay không.
2. Nếu cần, quiesce/backup theo đúng hướng dẫn và ghi nhận transaction boundary; không tự đóng băng file system tùy tiện.
3. Bảo vệ snapshot khỏi xóa cùng namespace/cluster và thử restore độc lập.
4. Kiểm tra khả năng phục hồi cùng **transaction log/metadata** phù hợp và điểm dữ liệu khôi phục được.

Không dùng một lần `kubectl get volumesnapshots` báo `ReadyToUse` làm bằng chứng database có thể restore bằng Neo4j và đáp ứng RPO/RTO.

### 12.3. Diễn tập restore một cách có tiêu chí

Một lần restore đạt cần chứng minh:

| Kiểm tra | Bằng chứng |
| --- | --- |
| Backup giải mã/đọc được | Tool restore/backup báo thành công với log đã kiểm tra. |
| Database khởi động | Neo4j báo ONLINE và có thể kết nối được từ client test. |
| Dữ liệu đúng | Các fixture khóa, số node/relationship, constraint và query Cypher trả đúng. |
| Ghi mới an toàn | Có thể commit, restart rồi đọc lại giao dịch vừa ghi. |
| Quyền đúng | Tài khoản read/write và ranh giới tenant được tái lập phù hợp. |
| RPO/RTO đạt | Ghi timestamp cuối được phục hồi và tổng thời gian khôi phục thực tế. |
| Không phụ thuộc nguồn đã hỏng | Vùng restore sử dụng bản sao và secret ở failure domain thích hợp. |

Nếu một bước không thể kiểm chứng, trạng thái phải là **backup tồn tại nhưng restore chưa được chứng minh**, không phải “DR sẵn sàng”.

## 13. Nâng cấp, scale và thay đổi storage

### 13.1. Nâng cấp image không phải rolling restart thông thường

Neo4j có yêu cầu tương thích giữa phiên bản engine, định dạng store, protocol cluster, plugin GDS/APOC và Java Driver. Những nâng cấp major/minor hoặc migration store có thể cần thứ tự và công cụ riêng.

Trước khi thay image:

1. Kiểm tra ma trận tương thích được hỗ trợ cho version mới và edition.
2. Sao lưu, thử restore, chạy migration trong staging với bản dữ liệu đại diện.
3. Kiểm tra chart/operator values, setting deprecation và image entrypoint.
4. Lên lịch cập nhật server Neo4j cluster theo trình tự được hỗ trợ, không đồng thời restart tất cả.
5. Kiểm tra Cypher, index, constraint, Java Driver, Spring Data Neo4j và plugin sau nâng cấp.
6. Định nghĩa rollback thực tế: **không chắc có thể khởi động lại phiên bản cũ trên store đã nâng cấp**; có thể cần restore backup.

Không dùng image tag `latest` khi triển khai có trạng thái. GitOps/Helm có thể khiến image mới được kéo mà không có thay đổi cụ thể được xét duyệt.

### 13.2. Scale up storage

Kiểm tra StorageClass có `allowVolumeExpansion`, CSI có hỗ trợ tăng volume/filesystem và các điều kiện restart. Nếu có, mở rộng **PVC được hỗ trợ**; không sửa trực tiếp file PV/đường dẫn host hay hạ kích thước volume. Volume expansion có thể là thao tác không dễ rollback.

Quy trình nên gồm:

- Đo headroom hiện tại và peak dự kiến.
- Xác nhận quota/giới hạn storage và availability zone.
- Backup và phương án dừng thao tác khi lỗi.
- Mở rộng một môi trường/instance thử, quan sát resize ở Kubernetes và filesystem.
- Chạy query/transaction kiểm chứng sau khi volume báo kích thước mới.

**Scale down storage** thường không được hỗ trợ như tăng kích thước; nếu cần giảm dữ liệu vật lý, lên kế hoạch tái dựng/restore trên volume mới theo quy trình được hỗ trợ. Xóa node trong Neo4j không bảo đảm tệp store trên filesystem sẽ tự thu nhỏ ngay.

### 13.3. Scale server hoặc di chuyển volume

Thêm một Neo4j server cluster phải xét discovery, quyền, role, tài nguyên PVC mới, routing và đồng thuận. Bỏ một server cũng phải theo quy trình cluster; không chỉ `kubectl scale --replicas 2` từ 3 rồi cho rằng luôn an toàn.

Di chuyển PVC giữa storage tier/zone cần tính cách Neo4j chịu downtime, tính nhất quán dữ liệu và khả năng rollback. Một `kubectl apply` thay StorageClass trong claim đang dùng **không** tự di chuyển dữ liệu sang backend mới; có thể cần tạo PVC mới và dùng công cụ migration/restore được hỗ trợ.

## 14. Bảo mật Kubernetes và đường kết nối Neo4j

Neo4j chứa dữ liệu và quan hệ có thể rất nhạy cảm. Hãy bảo vệ từ Kubernetes control plane đến database:

| Vấn đề | Yêu cầu |
| --- | --- |
| Secret | Không ghi password/token vào Git, image hay log; dùng Secret/secret manager với RBAC, encryption at rest và chính sách rotation. |
| Service account | Pod và CI/CD chỉ có quyền Kubernetes cần thiết; không mặc định mount token Kubernetes nếu không dùng. |
| NetworkPolicy | Giới hạn chiều vào Bolt/HTTP/admin và các cổng cluster; phân biệt client, member, backup và metrics. |
| TLS | Mã hóa kết nối client–Neo4j và server–server theo yêu cầu, kiểm tra certificate/hostname. |
| Storage encryption | Mã hóa volume, snapshot, backup và quản lý khóa; đánh giá điểm lộ PII từ relationship. |
| Container privileges | Chạy với quyền tối thiểu, UID/GID và `fsGroup` phù hợp CSI; tránh privileged container nếu không có lý do. |
| Image provenance | Pin version/digest, scan image, kiểm soát registry và plugin được nạp vào Neo4j. |
| Neo4j privileges | Tách tài khoản ứng dụng read/write, backup, monitor, admin; dùng RBAC chi tiết theo edition. |
| Exposure | Không mở Bolt/HTTP ra internet công khai nếu không cần; kiểm soát ingress/load balancer và audit truy cập. |

Kubernetes Secret **chỉ là cơ chế quản lý dữ liệu nhạy cảm**, không phải bảo đảm bí mật tuyệt đối nếu etcd không được mã hóa hoặc RBAC cấp quyền đọc secret quá rộng. Trong manifest ví dụ, biến `NEO4J_AUTH` trong môi trường container vẫn có thể bị lộ cho người có đặc quyền debug pod; production cần đánh giá ranh giới quyền và khả năng xoay vòng password thật.

Nếu dùng `neo4j://` với routing cluster, client phải phân giải và kết nối được đến các địa chỉ Neo4j quảng bá. Một Service IP ổn định chưa đủ nếu driver nhận topology chứa hostname nội bộ mà client ngoài cluster không tới được.

## 15. Giám sát để biết database thật sự khỏe

Một dashboard đủ dùng cần **hai lớp đo**:

**Kubernetes/storage:**

- Pod phase, restart, OOMKilled, Ready/NotReady.
- PVC/PV status, VolumeAttachment error, free disk bytes, volume growth.
- CSI latency, IOPS, throughput, attach/detach duration và filesystem errors.
- Node condition, CPU throttling, memory cgroup và các sự kiện eviction.
- Tình trạng scheduler Pending do topology, quota hay thiếu resource.

**Neo4j/ứng dụng:**

- Database ONLINE/availability, cluster membership/quorum/catch-up theo tính năng hỗ trợ.
- Transaction commit/rollback rate, latency p95/p99 và query errors.
- Store/index/transaction-log size, index state `ONLINE/POPULATING/FAILED`.
- Page cache, heap/GC, off-heap/transaction/query memory khi metric có sẵn.
- Backup success/age, restore drill, import/CDC lag.
- Latency Cypher thật trong Java Driver/Spring Data Neo4j và tỷ lệ retry.

Không đồng nhất `Pod Ready` với `Neo4j healthy`. Pod có thể trả TCP, nhưng query Cypher chậm, cluster mất quorum hoặc storage gần đầy. Ngược lại, một probe quá nhạy có thể đánh rớt pod vẫn đang thực hiện recovery hợp lệ.

**Cảnh báo thiếu metric** là bắt buộc: không có dữ liệu do collector ngừng không có nghĩa disk usage bằng 0. Ngoài tỷ lệ phần trăm, cảnh báo disk phải xét **số GiB còn lại và dự báo thời gian đến quỹ dự phòng**.

## 16. Kiểm thử trước khi quyết định GO/NO-GO

Lập môi trường thử với **Kubernetes version, CSI/storage tier, topology và Neo4j image** sát production; dùng dữ liệu đại diện, không chỉ vài node.

| ID | Tình huống | Bằng chứng đạt |
| --- | --- | --- |
| K01 | Import dữ liệu đại diện và tạo index. | Kích thước store/index/log đo được, không thiếu headroom. |
| K02 | Đọc/ghi Cypher có tải đồng thời. | p95/p99, IOPS/latency và CPU/RAM phù hợp SLO. |
| K03 | Restart container có kiểm soát. | Dữ liệu đã commit còn nguyên, Neo4j tự recovery và sẵn sàng. |
| K04 | Xóa pod để controller tạo lại. | PVC đúng được gắn lại, không tạo database mới rỗng. |
| K05 | Drain node theo thủ tục. | Thời gian detach/attach và recovery trong RTO. |
| K06 | Mất node đột ngột ở staging. | Không có hai writer cùng dùng store; recovery/failover theo thiết kế. |
| K07 | Một zone mất khả dụng. | Kiến trúc cluster/backup đáp ứng phạm vi HA đã cam kết, hoặc tài liệu hóa giới hạn. |
| K08 | PVC không attach được/khác zone. | Cảnh báo rõ, pod Pending không bị coi là khỏe; có runbook khôi phục. |
| K09 | CSI/storage latency tăng. | Cảnh báo tail latency, timeout/throughput được đo ở Neo4j và hạ tầng. |
| K10 | Dung lượng gần ngưỡng dự phòng. | Cảnh báo sớm, không cần xóa tệp database để khắc phục. |
| K11 | Index POPULATING/FAILED trong bài test. | Quan sát được state, tác động query và nguyên nhân. |
| K12 | Backup và restore sang namespace/cluster khác. | Dữ liệu, constraint, quyền và Cypher đúng, RPO/RTO đo thật. |
| K13 | Client Java mất kết nối/failover. | Routing và retry transaction phù hợp, không nhân đôi side effect nghiệp vụ. |
| K14 | Upgrade version được hỗ trợ trên dữ liệu thử. | Store/driver/plugin tương thích, không mất dữ liệu, có đường phục hồi. |
| K15 | Hạn chế quyền/mạng và secrets. | Pod không được phép không đọc được dữ liệu/secret; TLS được xác minh. |
| K16 | Xóa nhầm StatefulSet trong staging. | PVC/reclaim behavior đúng chính sách; không mất volume ngoài ý muốn. |
| K17 | Mất metrics/collector. | Cảnh báo mất telemetry, không kết luận sai là database ổn định. |
| K18 | Quorum bị mất trong cluster thử. | Hệ thống xử lý đúng giới hạn write availability, có kế hoạch trở lại phục vụ. |

### 16.1. Kiểm thử dữ liệu đã commit qua một lần restart

Trong database test, tạo dữ liệu có khóa ổn định:

~~~cypher
CREATE CONSTRAINT deploy_demo_id IF NOT EXISTS
FOR (n:DeployDemoRecord)
REQUIRE n.recordId IS UNIQUE;
~~~

~~~cypher
MERGE (n:DeployDemoRecord {recordId: 'restart-test-001'})
SET n.expectedValue = 'persisted',
    n.updatedAt = datetime()
RETURN n.recordId AS recordId, n.expectedValue AS value;
~~~

Chỉ khi lệnh ghi đã **commit thành công**, thực hiện restart/kill pod theo kịch bản test có kiểm soát. Sau khi Neo4j phục hồi:

~~~cypher
MATCH (n:DeployDemoRecord {recordId: 'restart-test-001'})
RETURN n.expectedValue AS value;
~~~

Kỳ vọng `value = 'persisted'`. Đây là bài test tối thiểu để phát hiện triển khai đang lưu dữ liệu ở filesystem tạm. Nó **không** chứng minh crash consistency của mọi pattern ghi hay bảo đảm 0 data loss trên tất cả lỗi storage; phải kết hợp với test nhiều transaction và verify backup.

### 16.2. Không làm chaos test phá hủy dữ liệu production

Chỉ chạy test kill node/zone, lỗi network, detach volume hoặc thiếu dung lượng **trong môi trường cô lập với dữ liệu tổng hợp** và đã có kế hoạch khôi phục. Không dùng dữ liệu thật để thử một điều kiện gây mất dữ liệu chỉ nhằm “xem có hoạt động không”.

## 17. Runbook sự cố thường gặp

### 17.1. Pod Pending, PVC không bind

**Dấu hiệu:** `StatefulSet` tạo pod nhưng pod ở `Pending`, `PVC Pending` hoặc có event `FailedScheduling`.

Quy trình:

1. Xem `kubectl describe pod`, `kubectl get pvc/pv` và event của PVC.
2. Kiểm tra StorageClass tồn tại, quota, access mode, `WaitForFirstConsumer`, provisioner CSI.
3. Xác minh topology zone/node affinity và khả năng attach ở vị trí pod cần chạy.
4. Giữ nguyên PVC/PV đã có dữ liệu, không xóa rồi để provisioner cấp volume rỗng.
5. Điều chỉnh quota/node capacity/topology theo kế hoạch; kiểm tra pod mount đúng dữ liệu sau khi hồi phục.

### 17.2. Pod CrashLoopBackOff hoặc OOMKilled

**Dấu hiệu:** container restart liên tục, query thất bại hoặc readiness lặp lại.

Quy trình:

1. Phân biệt OOM, lỗi quyền trên `/data`, cấu hình Neo4j không hợp lệ, image/plugin sai phiên bản và recovery lâu.
2. Kiểm tra event/log được phép truy cập; bảo vệ secret và thông tin nhạy cảm.
3. Nếu do probe, kiểm tra `startupProbe`/liveness và thời gian recovery thật, không vô hiệu hóa mọi probe một cách mù quáng.
4. Nếu do memory, đo heap, page cache và native memory so với cgroup limit.
5. Sau sửa, xác minh dữ liệu đã commit còn nguyên và query đọc/ghi hoạt động.

### 17.3. Volume đầy hoặc transaction log tăng mạnh

**Dấu hiệu:** free disk giảm, transaction commit lỗi, index bị ảnh hưởng, transaction logs lớn bất thường.

Quy trình:

1. Xác định PVC/volume bị đầy và thành phần tăng: store, index, transaction logs hay logs khác.
2. Kiểm tra import, transaction lớn, retry loop, index build, retention/pruning và trạng thái cluster/backup.
3. Ưu tiên thêm headroom hoặc điều tiết job ghi không thiết yếu theo runbook đã phê duyệt.
4. **Không xóa file store/index/transaction log thủ công**. Rotation/retention có cơ chế riêng của Neo4j.
5. Sau khi có không gian an toàn, kiểm tra consistency/availability, backup và tiến trình cluster.

### 17.4. Mất một thành viên Neo4j cluster

**Dấu hiệu:** client báo lỗi routing/leader, một server bị NotReady hoặc topology không ổn định.

Quy trình:

1. Đánh giá database còn quorum và phục vụ đọc/ghi ở mức nào, không chỉ xem pod count.
2. Kiểm tra DNS/advertised addresses, chứng chỉ, mạng cluster và trạng thái server.
3. Xác minh PVC của server lỗi vẫn còn nguyên, attach an toàn và node phù hợp zone.
4. Theo quy trình Neo4j cluster đúng version, phục hồi server/catch-up hoặc tái dựng thành viên từ nguồn đáng tin; không thay đổi membership bằng cách xóa PVC tùy tiện.
5. Kiểm tra Java Driver routing, transaction retry, các sự kiện ghi trong giai đoạn failover và health/backup sau khi ổn định.

## 18. Bảng quyết định GO / NO-GO

| Tiêu chí | GO khi | NO-GO hoặc cần thiết kế lại khi |
| --- | --- | --- |
| RPO/RTO | Có mục tiêu, kiến trúc đáp ứng và restore drill đo được. | Chỉ dựa vào lời hứa “Kubernetes tự restart”. |
| Storage durability | CSI/backend và ghi bền vững được hỗ trợ/kiểm chứng. | Storage không bảo đảm flush/durability cần thiết. |
| PVC lifecycle | Quy tắc reclaim/retention rõ; có ngăn xóa nhầm. | Xóa controller/namespace có nguy cơ làm mất data không có backup. |
| Topology | Pod có thể phục hồi đúng zone/failure domain; cluster đúng thiết kế. | PV bị kẹt zone trong khi SLA đòi chịu mất zone mà không có phương án. |
| Database cluster | Edition, quorum, discovery, TLS, routing và từng server PVC riêng được test. | Chỉ tăng `replicas` StatefulSet mà không cấu hình Neo4j clustering. |
| Capacity | Import, index, tx log, backup và headroom đều có số liệu đại diện. | Chỉ đo CSV source size và chọn PVC theo cảm tính. |
| Hiệu năng | Đo p95/p99 query/commit và I/O trên đúng CSI tier. | Không có thử nghiệm commit latency và load peak. |
| Security | Secret, RBAC, network, TLS, data at rest và audit theo yêu cầu. | Database công khai/secret hard-code/quyền quá rộng. |
| Backup/DR | Có bản sao độc lập, restore test, kiểm tra dữ liệu/constraint. | Chỉ có CSI snapshot chưa xác minh consistency. |
| Operations | Có monitor, alert, owner, on-call và runbook cho PVC/cluster. | Không ai có quyền/năng lực xử lý volume attach hoặc restore. |

Quyết định **GO có thể kèm điều kiện**, ví dụ chấp nhận Neo4j đơn node cho môi trường development hoặc ứng dụng nội bộ có RTO dài, nhưng **không** được gọi đó là triển khai chịu được lỗi zone hoặc cam kết zero downtime.

## 19. Bài tập thực hành

**Bài 1 — Chọn nền tảng.** Một nhóm có hai kỹ sư backend, chưa có SRE, đòi RPO tối đa 5 phút và khôi phục sau lỗi zone trong 30 phút. So sánh Neo4j trên VM, Kubernetes self-managed và dịch vụ quản lý. Xác định bằng chứng nào cần có trước khi chọn.

**Bài 2 — Đọc StorageClass.** Có hai StorageClass: A là local NVMe với `WaitForFirstConsumer`, B là block volume theo zone với `ReadWriteOnce` và hỗ trợ resize. Hãy lập bảng khả năng sống sót khi pod restart, node chết và zone chết. Không suy luận B hỗ trợ di chuyển xuyên zone chỉ vì nó là PVC.

**Bài 3 — Access mode.** Một đội đề xuất `ReadWriteMany` để ba pod Neo4j dùng cùng một `/data`, cho rằng đó là “cluster đơn giản”. Giải thích vì sao cấu trúc này sai, và phác thảo ba PVC riêng cho ba server Neo4j cluster.

**Bài 4 — Tính dung lượng.** Sau import thử, store 300 GiB, index 60 GiB không nằm trong store, tx log peak 90 GiB, tệp khác 20 GiB. Với headroom 25%, tính nhu cầu tổng. Nếu index đã nằm trong store, sửa cách tính; nếu transaction logs nằm trên PVC khác, lập hai ngân sách riêng.

**Bài 5 — Độ sẵn sàng thật.** Kubernetes có ba pod đều Ready qua TCP probe nhưng Neo4j mất quorum. Vì sao dashboard pod count sai? Thiết kế thêm health check/metric để phát hiện tình trạng không phục vụ write.

**Bài 6 — Probes.** Một Neo4j mất 4 phút để recovery, nhưng liveness giết container sau 30 giây không thấy Bolt mở. Chỉ ra nguyên nhân CrashLoop và thiết kế lại startup/readiness/liveness dựa trên kết quả đo thật.

**Bài 7 — PVC lifecycle.** Một GitOps job xóa namespace test có StatefulSet và PVC. Hãy chỉ ra khi nào xóa namespace dẫn đến xóa volume vật lý, sự khác nhau giữa `Delete` và `Retain`, và lý do `Retain` không thay thế backup.

**Bài 8 — CSI snapshot.** Store Neo4j và transaction log nằm trên hai PVC; snapshot được tạo cách nhau 30 giây trong lúc database đang ghi. Có thể coi bộ snapshot là một backup ứng dụng nhất quán không? Đề xuất quy trình dùng cơ chế backup/restore được Neo4j hỗ trợ rồi kiểm thử.

**Bài 9 — Sự cố Pod Pending.** Một Neo4j pod bị thay nhưng PVC chỉ gắn được ở zone A, trong khi node còn chỗ chỉ ở zone B. Hãy giải thích PV topology, lựa chọn an toàn và lý do không xóa PVC để tạo volume mới rỗng.

**Bài 10 — Thử nghiệm quyết định GO.** Tự định nghĩa mục tiêu p95 query, commit latency, RPO, RTO, dung lượng và thời gian backup/restore. Xây ma trận test K01–K18 rút gọn cho một hệ thống cụ thể, chỉ rõ tiêu chí nào nếu không đạt thì **NO-GO**.

## 20. Checklist triển khai có trạng thái

1. **Đã chọn đúng mô hình vận hành:** self-managed Kubernetes, VM hay dịch vụ quản lý dựa trên nhu cầu thật, không theo xu hướng.
2. **Có RPO/RTO được phê duyệt:** phạm vi lỗi pod, node, zone và toàn cluster đã được mô tả.
3. **CSI/storage đáp ứng:** `fsync`/durability, IOPS, latency, topology, attach/detach, resize, snapshot và encryption được xác minh.
4. **Không dùng ephemeral data:** Neo4j store đặt trên PVC phù hợp; mỗi Neo4j server có vùng dữ liệu riêng.
5. **Hiểu StatefulSet:** ổn định pod/claim không có nghĩa clustering; số replica Neo4j được cấu hình theo quy trình database.
6. **Lập ngân sách đúng:** node, relationship, property, index, transaction logs, import peak và headroom không bị đếm trùng.
7. **Có lịch bảo trì:** image/version được pin, tương thích driver/plugin, rolling upgrade và rollback được diễn tập.
8. **Probe hợp lý:** startup/recovery lâu không bị liveness giết lặp; readiness có ý nghĩa với khả năng phục vụ.
9. **HA có failure domain:** placement, quorum, PV topology, PDB và client routing được kiểm thử, không chỉ dựa vào pod count.
10. **Backup độc lập và restore thật:** không đánh đồng PVC, replica hay VolumeSnapshot với bảo đảm phục hồi.
11. **Bảo mật xuyên lớp:** Secret/RBAC, NetworkPolicy, TLS, encryption at rest, image provenance và Neo4j privileges.
12. **Quan sát đủ lớp:** Kubernetes + CSI/storage + Neo4j + Java Driver/Spring Data Neo4j, có cảnh báo thiếu metric.
13. **Runbook có chủ sở hữu:** xử lý PVC Pending, CrashLoop, hết đĩa, mất quorum và restore với quyền được cấp rõ.
14. **Thử nghiệm lỗi có kiểm soát:** pod restart, node fail, zone fail, backup restore, upgrade, volume expansion và kiểm tra giao dịch.
15. **Chỉ GO khi có bằng chứng:** một bài demo tạo pod thành công không thay thế thử tải, phục hồi và bảo toàn dữ liệu.

**Kết luận:** Kubernetes chỉ phù hợp để chạy Neo4j có trạng thái khi **hệ lưu trữ thực sự bền vững, topology và quyền truy cập được thiết kế đúng, từng server có PVC riêng, Neo4j clustering được cấu hình đúng và quy trình backup/restore đã qua thử nghiệm**. StatefulSet giúp duy trì identity của pod; StorageClass/CSI quyết định nơi và cách dữ liệu tồn tại; Neo4j quyết định tính nhất quán của giao dịch và cluster. Hãy chấp nhận triển khai dựa trên **SLO, RPO/RTO, số liệu I/O và kết quả diễn tập sự cố**, không chỉ dựa trên trạng thái `Running` trong Kubernetes.
