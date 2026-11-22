# Lưu trữ bền vững và trách nhiệm vận hành thành phần có trạng thái

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Container và điều phối.  
> **Mục tiêu:** hiểu giới hạn của vòng đời container/Pod, thiết kế lưu trữ bền vững phù hợp, phân biệt những gì Kubernetes bảo đảm với những gì database hoặc hệ thống phân tán phải tự bảo đảm, và phân định rõ người chịu trách nhiệm vận hành thành phần có trạng thái.

## 1. Vấn đề: container có thể biến mất, dữ liệu nghiệp vụ thì không

Trong hệ thống microservices, Order Service có thể được triển khai bằng nhiều container giống nhau. Nếu một Pod lỗi hoặc một node hỏng, bộ điều phối tạo Pod thay thế; miễn code và cấu hình còn đúng, service có thể tiếp tục phục vụ.

Nhưng **Order Database**, **message broker** và **object storage** chứa dữ liệu cần tồn tại sau khi process ngừng, node bị thay hoặc ứng dụng nâng phiên bản. Nếu đặt dữ liệu quan trọng trên filesystem ghi được của container, việc tạo container/Pod mới có thể làm mất dữ liệu đó.

Ví dụ Order Service ghi file **/app/orders.db** trong container. Lúc đầu API chạy đúng. Khi triển khai image mới, Pod cũ bị xóa và Pod mới được tạo. Dữ liệu có thể biến mất vì filesystem ghi được gắn với vòng đời container, không phải với vòng đời nghiệp vụ.

Một trường hợp khác: PostgreSQL chạy trong Pod, mount một PersistentVolume. Pod được tạo lại và gắn lại volume cũ, database vẫn đọc được dữ liệu. Tuy nhiên nếu vùng lưu trữ bị hỏng, người vận hành xóa nhầm volume, transaction log không được bảo vệ hoặc backup không thể restore, **PersistentVolume không tự cứu được dữ liệu**.

Cần phân biệt ba mục tiêu:

1. **Persistence:** dữ liệu vẫn tồn tại khi container hoặc Pod bị thay.
2. **Availability:** dịch vụ tiếp tục hoặc sớm phục hồi khi node, process hay một vùng lỗi.
3. **Durability và recoverability:** dữ liệu đã được cam kết không bị mất quá mức được chấp nhận, và có thể khôi phục sau sự cố, thao tác sai hoặc mất cả cụm.

Ba mục tiêu liên quan nhưng không tương đương. Có PVC không đồng nghĩa hệ thống có HA hoặc backup.

## 2. Phân biệt stateless và stateful workload

| Đặc điểm | Stateless service | Stateful component |
| --- | --- | --- |
| Dữ liệu chính | Lưu ở hệ thống bên ngoài | Thường sở hữu dữ liệu hoặc trạng thái bền vững |
| Bản sao | Có thể thay Pod tương đối dễ | Có thể cần node identity, replication, leader/follower |
| Restart | Không cần giữ local runtime state quan trọng | Cần khôi phục WAL, index, offset, membership hoặc dữ liệu |
| Scale | Thường thêm replica và cân bằng tải | Phụ thuộc sharding, quorum, consistency và khả năng lưu trữ |
| Storage | Config/ephemeral cache, tmp | PVC, database volume, object store hoặc dịch vụ lưu trữ quản lý |
| Lỗi node | Scheduling Pod mới thường đủ cho compute | Phải xét volume attach, fencing, replica health và recovery |
| Release | Rolling update thường đơn giản hơn | Cần lưu ý schema, protocol, quorum và thứ tự nâng cấp |

**Stateless không có nghĩa không dùng dữ liệu.** Order API vẫn đọc/ghi database, nhưng bản thân Pod Order không cần giữ bản sao database nội bộ để hoạt động. Ngược lại, PostgreSQL, Redis có persistence, Kafka broker, Elasticsearch node hoặc một service tự quản lý ledger là những thành phần có trạng thái.

**Một dịch vụ có thể có cả hai loại state:** ví dụ Inventory Service dùng database bên ngoài, còn local cache là state có thể tái tạo. Không nên buộc toàn bộ Pod thành stateful chỉ vì nó dùng cache; chỉ những dữ liệu thật sự cần sống qua vòng đời Pod mới cần cơ chế bền vững.

## 3. Phân loại dữ liệu trước khi chọn storage

| Loại dữ liệu | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Tạm thời, có thể mất** | File tạm, cache có thể nạp lại, scratch space | **emptyDir**, bộ nhớ hoặc ephemeral volume có giới hạn |
| **Trạng thái ứng dụng đã cam kết** | Order, payment ledger, inventory reservation | Database bền vững với backup/restore và integrity rules |
| **File được chia sẻ** | Ảnh upload, tài liệu, dữ liệu media | Object storage hoặc shared filesystem phù hợp workload |
| **Transaction log** | PostgreSQL WAL, database redo log | Storage có latency/durability phù hợp, bảo vệ PITR |
| **Message log/offset** | Kafka log, consumer state | Hệ thống broker có replication, lưu trữ và retention rõ |
| **Cấu hình** | Endpoint, timeout, feature flag snapshot | Config repository/control plane, không đặt vào database ứng dụng tùy tiện |
| **Bí mật** | DB password, signing key, credential | Secret manager hoặc Kubernetes Secret theo threat model, bảo vệ quyền và mã hóa |
| **Artifact/backup** | DB snapshot, logical dump, WAL archive | Kho backup tách failure domain và có chính sách retention |

Một bảng dữ liệu hay object cần được thiết kế theo **RPO**, **RTO**, tính bảo mật, dung lượng, tần suất đọc/ghi, latency và thời hạn lưu. Không chọn PersistentVolume cho mọi dữ liệu chỉ vì Kubernetes hỗ trợ nó.

Các câu hỏi đầu tiên:

- Mất dữ liệu này có ảnh hưởng đến tài chính, giao hàng hay tuân thủ không?
- Có nguồn khác để tái tạo không?
- Cần bao nhiêu IOPS/throughput, latency p95/p99 và dung lượng?
- Cần một writer hay nhiều writer?
- Có cần gắn volume trên node/zone khác sau sự cố?
- Dữ liệu nằm ở jurisdiction nào, mã hóa ra sao?
- Backup được giữ bao lâu và ai đã từng restore thử?

## 4. Vòng đời container, Pod, node và volume

Một vài ranh giới rất dễ nhầm:

- **Container filesystem:** lớp ghi của container không phải nơi đáng tin để lưu dữ liệu nghiệp vụ qua lần tái tạo.
- **emptyDir:** tồn tại cùng Pod và có thể được các container trong Pod chia sẻ. Dữ liệu mất khi Pod bị xóa khỏi node; restart riêng container trong cùng Pod thường vẫn giữ volume.
- **hostPath:** truy cập đường dẫn trên host; dữ liệu phụ thuộc node, tăng rủi ro bảo mật và không tạo storage di động giữa node. Tránh dùng làm giải pháp persistence mặc định cho ứng dụng phân tán.
- **PersistentVolume (PV):** tài nguyên lưu trữ trong cluster có vòng đời quản lý riêng với Pod.
- **PersistentVolumeClaim (PVC):** yêu cầu sử dụng storage theo dung lượng, access mode và những thuộc tính khác.
- **StorageClass:** chính sách/cơ chế cấp phát storage động, thường qua CSI driver.
- **CSI driver:** thành phần tích hợp nền tảng lưu trữ; hỗ trợ các khả năng như provision, attach, mount, expand hoặc snapshot tùy driver và môi trường.

Không phải PV nào cũng là disk gắn block; backend có thể là network block storage, distributed storage hoặc filesystem. **Access mode và topology** phụ thuộc driver. Kubernetes điều phối việc gắn storage theo API và khả năng hạ tầng, nhưng không tự đảm bảo dữ liệu database nhất quán.

~~~mermaid
flowchart LR
    P[Stateful Pod] --> V[PersistentVolumeClaim]
    V --> PV[PersistentVolume]
    SC[StorageClass] -->|Dynamic provisioning| PV
    PV --> CSI[CSI driver]
    CSI --> DISK[Storage backend]
    B[Backup process] --> OBJ[Backup storage / object store]
    P -.-> B
~~~

Sơ đồ thể hiện đường phụ thuộc, không ngụ ý backup tự được tạo khi cấp PVC.

## 5. PV, PVC và StorageClass: mô hình cấp phát

### 5.1. PersistentVolume (PV)

PV đại diện một tài nguyên storage có thể được cấp trước hoặc cấp động. PV có capacity, access modes, reclaim policy, storageClassName, volume mode và những thông tin backend khác.

**PV không trực tiếp là hợp đồng nghiệp vụ về backup.** Thời gian tồn tại của PV, độ bền backend, replication và khả năng restore cần được xác định riêng.

### 5.2. PersistentVolumeClaim (PVC)

Ứng dụng yêu cầu storage bằng PVC:

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: orders-data
  namespace: commerce
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: fast-rwo
  resources:
    requests:
      storage: 20Gi
~~~

**fast-rwo** là tên StorageClass minh họa; cluster thật phải có class phù hợp. PVC này đề nghị 20 GiB và ReadWriteOnce; việc được cấp và gắn thành công tùy StorageClass, CSI driver, quota và topology.

Nếu Pod khác mount cùng PVC, phải xét chế độ truy cập và bảo vệ ghi đồng thời; không được mặc định PVC là khóa phân tán.

### 5.3. StorageClass

StorageClass có thể định nghĩa provisioner, parameters, reclaimPolicy, volumeBindingMode và allowVolumeExpansion:

~~~yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-rwo
provisioner: example.csi.storage.provider
reclaimPolicy: Retain
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
parameters:
  tier: fast
~~~

**Đây là ví dụ cấu trúc, không thể áp dụng trực tiếp.** Tên provisioner và parameters phải lấy từ CSI driver thực; không có driver chung mang tên example.csi.storage.provider. Chỉ cluster administrator hoặc platform team nên tạo và quản lý StorageClass.

**WaitForFirstConsumer** có thể trì hoãn binding/provisioning đến khi scheduler biết Pod sẽ chạy ở đâu, giúp chọn storage phù hợp topology. Nó không giải quyết mọi trường hợp volume bị khóa vào zone hoặc node; điều kiện gắn lại vẫn phụ thuộc backend.

## 6. Access modes và vấn đề nhiều writer

Các access mode thường gặp:

| Access mode | Ý nghĩa ở tầng Kubernetes | Cần nhớ |
| --- | --- | --- |
| **ReadWriteOnce (RWO)** | Có thể mount đọc/ghi bởi một node | Nhiều Pod trên cùng node có thể cùng truy cập tùy backend; không tự bảo đảm chỉ một Pod ghi |
| **ReadOnlyMany (ROX)** | Nhiều node mount read-only khi driver hỗ trợ | Phù hợp dữ liệu chia sẻ chỉ đọc |
| **ReadWriteMany (RWX)** | Nhiều node có thể mount đọc/ghi khi driver hỗ trợ | Không tự giải quyết locking, transaction hoặc consistency của ứng dụng |
| **ReadWriteOncePod (RWOP)** | PVC chỉ được mount đọc/ghi bởi một Pod khi hỗ trợ | Phù hợp giảm nguy cơ nhiều Pod cùng ghi trên một PVC |

RWO không phải quyền sở hữu độc quyền theo Pod. RWOP chỉ được hỗ trợ trong các điều kiện driver/CSI thích hợp. Kiểm tra phiên bản cluster và CSI trước khi dùng.

Một database đơn instance không được “scale” bằng cách mount cùng thư mục dữ liệu qua RWX cho hai Pod rồi cho hai process ghi đồng thời. Điều này có thể làm hỏng dữ liệu. Muốn nhiều replica database, phải sử dụng **replication protocol, leader election, consensus hoặc cluster manager** của chính database.

Tương tự, **RWX filesystem** không tự cung cấp exactly-once processing hay distributed locking an toàn cho một ứng dụng bất kỳ.

## 7. Reclaim policy và vòng đời dữ liệu

Khi xóa PVC, điều gì xảy ra với backend storage phụ thuộc PV và reclaim policy:

- **Delete:** backend volume có thể bị xóa khi claim được giải phóng, theo driver và controller.
- **Retain:** PV/backend được giữ lại để người vận hành quyết định xử lý hoặc tái sử dụng; có thể cần thao tác thủ công.
- **Recycle:** là cơ chế cũ không còn phù hợp để sử dụng trong nhiều trường hợp hiện đại.

Reclaim policy không phải **backup strategy**. Retain giúp tránh việc backend storage bị xóa ngay khi claim biến mất, nhưng không bảo vệ khỏi corruption, tấn công, mất vùng lưu trữ hoặc thao tác xóa trực tiếp ở provider.

Với StatefulSet sử dụng **volumeClaimTemplates**, PVC thường được giữ qua việc xóa StatefulSet hoặc scale down theo hành vi và cấu hình retention policy; vẫn phải kiểm tra thiết lập thực tế, vì có chính sách tự động xóa PVC trong một số cấu hình.

Quy trình xóa một thành phần stateful cần xác định rõ:

1. Có giữ dữ liệu để khôi phục không?
2. PVC/PV/backend volume nào đang thuộc service?
3. Backup mới nhất đã verify có khả dụng không?
4. Có legal hold hoặc retention requirement không?
5. Có consumer, replica hoặc job nào còn sử dụng storage không?
6. Ai có quyền duyệt xóa dữ liệu vật lý?

Không gộp thao tác **xóa Deployment**, **xóa PVC** và **xóa backend disk** thành một hoạt động dọn dẹp không phân biệt.

## 8. StatefulSet cung cấp những bảo đảm gì?

**StatefulSet** là workload controller phù hợp cho các Pod cần danh tính ổn định hoặc storage gắn theo từng replica. Nó có các đặc điểm:

- **Tên Pod ổn định** theo ordinal, ví dụ postgres-0, postgres-1.
- **Stable network identity** thông qua headless Service và DNS khi cấu hình đúng.
- **volumeClaimTemplates** tạo PVC riêng cho mỗi replica, ví dụ data-postgres-0 và data-postgres-1.
- Có chính sách thứ tự tạo/xóa Pod và cập nhật theo chiến lược controller.
- Khi thay Pod cùng ordinal, mục tiêu là gắn lại PVC tương ứng, tùy storage driver và scheduler.

StatefulSet **không** tự:

- Sao chép database từ Pod 0 sang Pod 1.
- Thiết lập leader election, quorum hoặc fencing.
- Tạo backup/PITR.
- Bảo đảm một database luôn sẵn sàng khi zone bị mất.
- Nâng cấp schema hoặc protocol an toàn.
- Sửa dữ liệu corrupted.
- Bảo đảm mỗi write đã nhận được acknowledgment có độ bền theo business RPO.

Tạo **StatefulSet replicas: 3** cho một image PostgreSQL đơn lẻ không biến nó thành cụm PostgreSQL HA. Mỗi Pod có thể tạo một database độc lập trên PVC riêng, và nếu client gửi write vào nhiều Pod thì có thể tạo dữ liệu phân kỳ. Cần operator hoặc thiết kế cluster theo cơ chế replication chính thức.

## 9. Ví dụ Kubernetes: PostgreSQL một replica để học cơ chế persistence

Manifest dưới đây minh họa **headless Service + StatefulSet + volumeClaimTemplates**. Nó phù hợp để hiểu storage lifecycle trong môi trường học/test. **Đây không phải cấu hình PostgreSQL production HA**: chỉ có một DB instance, chưa có backup, TLS, network policy, monitoring, resource sizing, pod disruption budget hay quy trình nâng cấp.

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres-headless
  namespace: commerce
spec:
  clusterIP: None
  selector:
    app: orders-postgres
  ports:
    - name: postgres
      port: 5432
      targetPort: 5432
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: orders-postgres
  namespace: commerce
spec:
  serviceName: postgres-headless
  replicas: 1
  selector:
    matchLabels:
      app: orders-postgres
  template:
    metadata:
      labels:
        app: orders-postgres
    spec:
      containers:
        - name: postgres
          image: postgres:16
          ports:
            - name: postgres
              containerPort: 5432
          env:
            - name: POSTGRES_DB
              value: orders
            - name: POSTGRES_USER
              value: appuser
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: orders-db-credentials
                  key: password
            - name: PGDATA
              value: /var/lib/postgresql/data/pgdata
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
          resources:
            requests:
              cpu: "250m"
              memory: 512Mi
            limits:
              memory: 1Gi
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes:
          - ReadWriteOnce
        storageClassName: fast-rwo
        resources:
          requests:
            storage: 20Gi
~~~

Các điều kiện để thử nghiệm:

- Namespace **commerce** đã tồn tại.
- Secret **orders-db-credentials** đã được tạo an toàn, chứa key **password**. Không commit plaintext password vào repo.
- StorageClass **fast-rwo** tồn tại và hoạt động với node/zone phù hợp.
- Nền tảng cho phép image được pull; production nên pin image bằng **digest** và có quy trình quét/lưu trữ image.
- Có service hoặc client kiểm tra cơ sở dữ liệu; việc Pod chạy không tự chứng minh data bền vững.
- Để phục vụ client một cách ổn định, có thể cấu hình Service riêng cho endpoint writer/read-only tùy topology; headless Service chủ yếu hỗ trợ danh tính Pod.

Trong StatefulSet này, PVC thường có tên **data-orders-postgres-0**. Khi Pod orders-postgres-0 bị tái tạo, nó có thể mount lại PVC tương ứng, nếu backend volume còn nguyên và node/zone có thể gắn volume. Đừng thử xóa PVC khi muốn kiểm chứng Pod recreation.

Ví dụ dùng **postgres:16** để đơn giản hóa; trong production phải xem supported patch version, quyền process/container, storage performance, readiness/liveness/startup probes, TLS, secret rotation, update strategy và backup/restore. Các probes phải phản ánh hoạt động an toàn của database, tránh liveness probe quá nhạy khiến DB đang phục hồi cứ bị restart liên tục.

## 10. Kiểm chứng persistence mà không nhầm với durability

Một thử nghiệm nhỏ:

1. Tạo Pod/PVC và chờ database khởi động.
2. Tạo một bảng và ghi record thử nghiệm.
3. Xác định PVC đã được bind với PV phù hợp.
4. Xóa **chỉ Pod**, để StatefulSet tạo Pod cùng ordinal.
5. Đọc lại record từ Pod mới.
6. Ghi nhận PVC/PV cũ vẫn được sử dụng.

Nếu record còn tồn tại, thử nghiệm chứng minh dữ liệu đã sống qua **Pod recreation** trong tình huống đó. Nó **không chứng minh**:

- Backend chịu được mất hẳn storage zone.
- Dữ liệu chịu được đứt điện đúng thời điểm fsync.
- Backup có thể restore.
- Xóa nhầm PVC có thể khôi phục.
- Một replica khác có thể nhận quyền writer an toàn.
- RPO/RTO sản xuất được đáp ứng.

Để chứng minh durability và recoverability, cần fault injection ở những failure domain khác và diễn tập restore phù hợp với dữ liệu nghiệp vụ.

## 11. Khi nào nên dùng database managed, operator hoặc tự vận hành?

| Lựa chọn | Ưu điểm | Trách nhiệm còn lại |
| --- | --- | --- |
| **Managed database** | Nhà cung cấp xử lý một phần hạ tầng, backups, patching/replication theo dịch vụ đã mua | Schema, dữ liệu, quyền, connection, SLO, restore strategy, chi phí, kiểm thử phục hồi |
| **Database operator trong Kubernetes** | Có thể tự động hóa cluster lifecycle, failover và backups nếu operator hỗ trợ | Vận hành operator/CSI/storage, kiểm tra automation và kiểm soát phiên bản |
| **Tự triển khai StatefulSet thủ công** | Linh hoạt, học được internals | Tự chịu HA, failover, backup, fencing, upgrades, monitoring, recovery |
| **Lưu dữ liệu trong service qua managed external storage** | Stateless service dễ scale và rollout | Phụ thuộc network, latency, quotas, security và contract storage |

**Không có câu trả lời “mọi database phải chạy trong Kubernetes” hoặc “không database nào nên ở Kubernetes”.** Cân nhắc năng lực vận hành, RPO/RTO, failure domain, chi phí, yêu cầu dữ liệu, độ trễ và mức độ hỗ trợ của nhà cung cấp.

Với nhóm chưa có kinh nghiệm phục hồi database cluster, managed database thường giảm công sức vận hành hạ tầng. Nhưng không được suy luận managed service đã thay nhóm ứng dụng kiểm tra backup, logic migration, audit, quyền và khả năng khôi phục theo nhu cầu kinh doanh.

Nếu dùng operator, phải đọc contract của **operator cụ thể**: số replica, synchronous/asynchronous replication, failover, fence, backup, restore, upgrade version, split-brain prevention và yêu cầu storage. Không khẳng định mọi operator có cùng bảo đảm.

## 12. Replication, high availability và backup là ba cơ chế khác nhau

### 12.1. Replication

Sao chép trạng thái giữa các replica để tăng khả năng phục vụ và/hoặc mức độ bền dữ liệu theo cấu hình. Có thể là đồng bộ hoặc bất đồng bộ.

**Replication không phải backup**: nếu dữ liệu bị DELETE nhầm, corruption được ghi và replicate sang replica khác, hệ thống có thể mất dữ liệu ở tất cả replica.

### 12.2. High availability

Khả năng tiếp tục hoặc sớm phục hồi dịch vụ khi một thành phần lỗi. Với database, HA có thể yêu cầu:

- Leader/follower rõ ràng.
- Health và membership có cơ chế tránh false-positive.
- Replication state đủ tốt để promote.
- Fencing writer cũ trước khi writer mới nhận traffic.
- Quorum/consensus theo cơ chế của database/cluster manager.
- Routing client đến đúng endpoint hiện tại.
- Recovery sau network partition.

Chỉ tăng replica count không đủ để có HA.

### 12.3. Backup/restore

Giữ một bản sao có lịch sử và khả năng khôi phục ngoài runtime chính. Cần retention, bảo mật, kiểm tra integrity, lịch backup, PITR nếu cần và restore drill.

### 12.4. RPO và RTO

- **RPO — Recovery Point Objective:** khoảng mất dữ liệu tối đa nghiệp vụ chấp nhận, ví dụ 5 phút.
- **RTO — Recovery Time Objective:** thời gian mục tiêu để phục hồi dịch vụ sau sự cố, ví dụ 30 phút.

Hai con số là **yêu cầu**; việc có volume hoặc ba replica không tự chứng minh đáp ứng. Kiểm chứng bằng diễn tập fault/restore thực tế và đo thời gian.

Một database với replication async có thể failover nhanh nhưng vẫn mất các write mới nhất chưa đến replica. Synchronous replication có thể giảm cửa sổ mất dữ liệu nhưng ảnh hưởng latency và availability dưới network partition. Chính sách phải phản ánh ưu tiên của nghiệp vụ.

## 13. Lưu ý đặc biệt với quorum, split-brain và fencing

Trong hệ thống stateful phân tán, khi network partition xảy ra, hai nút có thể cùng tin rằng mình là leader nếu thiết kế không bảo vệ đúng.

**Split-brain** nguy hiểm khi hai writer đồng thời nhận update trên cùng logical data hoặc cùng storage. Hậu quả có thể là dữ liệu phân kỳ hoặc corruption.

Cần phân biệt:

- **Pod readiness:** Pod có báo sẵn sàng nhận traffic không?
- **Leader election:** ai được phép thực hiện thao tác ghi?
- **Quorum:** nhóm đủ phiếu để xác nhận trạng thái/membership?
- **Fencing/STONITH tương đương:** làm writer cũ không thể tiếp tục ghi sau khi mất quyền lãnh đạo?
- **Storage attachment fencing:** backend có ngăn hai node ghi nguy hiểm cùng một volume khi chuyển owner không?

StatefulSet và PVC không tự thực hiện toàn bộ chính sách trên. Nếu dùng PostgreSQL HA, Kafka, etcd hoặc Elasticsearch, phải dùng cơ chế cluster/manager được thiết kế riêng và hiểu tính chất consistency của chúng.

Một database có leader bị cô lập nhưng Pod vẫn “Running” không đồng nghĩa nó an toàn để nhận write. Endpoint và liveness check phải phù hợp vai trò leader/follower, tránh routing write sai và tránh restart cascade khi cluster đang phục hồi.

## 14. Storage topology: node, zone, region và scheduler

Một volume có thể chỉ gắn được trong một **availability zone**. Khi Pod từ zone A chuyển sang node ở zone B:

- Scheduler có thể không tìm được node phù hợp volume affinity.
- PVC đã bound với PV ở zone A.
- Backend không hỗ trợ attach xuyên zone.
- Pod có thể ở **Pending** dù cluster còn nhiều CPU/RAM.

**WaitForFirstConsumer** giúp việc cấp volume ban đầu phù hợp vị trí Pod, nhưng không biến một volume theo zone thành multi-zone storage.

Thiết kế topology:

1. Xác định storage hỗ trợ node/zone/region nào.
2. Đặt node affinity/anti-affinity/topology spread theo khả năng thực tế của DB cluster.
3. Nếu dùng replicas ở nhiều zone, các replica cần storage riêng và replication cấp ứng dụng phù hợp.
4. Chọn rõ failure domain của backup: backup cùng zone không bảo vệ khỏi mất zone.
5. Xem xét latency giữa replica và băng thông/chi phí cross-zone.
6. Có runbook xử lý Pod Pending do volume attach hoặc zone outage.

**PodDisruptionBudget (PDB)** có thể giới hạn một số cuộc gián đoạn tự nguyện như drain node, nhưng không ngăn mất node, hỏng storage hay mọi loại sự cố. PDB cũng không thay cluster manager xử lý failover.

## 15. Vận hành backup, snapshot và PITR

### 15.1. Snapshot storage chưa chắc là database-consistent backup

Một CSI **VolumeSnapshot** có thể chụp trạng thái volume theo khả năng driver. Snapshot ở tầng storage thường tạo ảnh chụp tại một thời điểm nhưng **không tự bảo đảm application consistency** khi DB đang có ghi.

Database có buffer, transaction log, nhiều volume và các quy tắc flush riêng. Snapshot khi database đang chạy có thể chỉ **crash-consistent**; cần hiểu cơ chế recovery của DB và công cụ snapshot.

Một phương án an toàn có thể sử dụng công cụ backup chính thức của database, hoặc phối hợp quiesce/checkpoint và snapshot theo quy trình hỗ trợ của DB. Không tự chạy **fsfreeze** hoặc stop writes trên production nếu chưa hiểu tác động đến availability.

### 15.2. Logical backup

Ví dụ PostgreSQL dùng **pg_dump** để xuất dữ liệu logic. Phù hợp một số nhu cầu backup, migration và restore chọn lọc; tốc độ, độ nhất quán và khả năng đáp ứng RPO tùy kích thước và lịch chạy.

Logical dump không thay toàn bộ chiến lược PITR có WAL khi yêu cầu khôi phục sát thời điểm.

### 15.3. Physical backup và WAL archive

Đối với PostgreSQL có thể dùng base backup cùng **WAL archiving** để phục hồi đến một thời điểm trong cửa sổ được hỗ trợ. Phải giữ liên tục WAL cần thiết; thiếu một đoạn có thể làm không thể replay đến mốc mong muốn.

Cần kiểm soát:

- Backup thành công theo lịch và checksum/integrity.
- Backup được lưu ngoài failure domain của database chính.
- WAL/archive retention đủ cho điểm phục hồi mục tiêu.
- Mã hóa, key management và quyền restore.
- Tốc độ tải dữ liệu khi disaster recovery.
- Khả năng khôi phục sau upgrade database version.
- Test restore, chạy query kiểm tra dữ liệu và bất biến domain.

### 15.4. Backup không nên phụ thuộc vào cùng cluster

Nếu cả database và backup job, backup index, object storage endpoint đều chỉ sống trong cùng cluster hoặc cùng tài khoản không được bảo vệ, cluster-wide outage hoặc tài khoản bị chiếm quyền có thể làm mất cả hai.

Áp dụng **phân tách failure domain**, bảo vệ quyền xóa, retention/immutability khi cần và có cách khôi phục credential ngoài môi trường sự cố.

### 15.5. Restore drill

Một diễn tập restore thực tế nên:

1. Chọn recovery point cụ thể và loại sự cố giả định.
2. Dựng môi trường phục hồi cô lập.
3. Restore backup/snapshot/WAL theo tài liệu hệ quản trị.
4. Kiểm tra database có thể startup và phục hồi transaction log.
5. Đối soát dữ liệu bằng checksum, row counts hoặc business invariants phù hợp.
6. Kiểm tra quyền, migration version, schema và ứng dụng tương thích.
7. Đo RTO thực tế, xác định RPO đạt được.
8. Ghi lỗi runbook và cải thiện quy trình.

**Backup job xanh chỉ chứng minh job báo thành công.** Để tin được dữ liệu, phải chứng minh có thể restore và sử dụng kết quả.

## 16. Ma trận lỗi: thành phần nào thực sự cứu được dữ liệu?

| Sự cố | PVC/PV | Replication/HA | Backup/restore |
| --- | --- | --- | --- |
| Container crash | Dữ liệu thường còn nếu trên volume phù hợp | Replica có thể phục vụ trong lúc restart | Thường không cần |
| Pod bị xóa | PVC có thể được mount lại | Có thể chuyển traffic | Thường không cần |
| Node mất tạm thời | Phụ thuộc attach/mount backend | Replica trên node khác có thể tiếp quản | Dùng nếu không phục hồi được |
| Mất một zone | Volume trong zone đó có thể unavailable | Multi-zone replication có thể hỗ trợ | Cần nếu mất dữ liệu hoặc không có replica phù hợp |
| Xóa nhầm PVC/backend volume | Có thể mất dữ liệu | Replication chưa chắc bảo vệ khỏi thao tác xóa | Backup/PITR có thể cần |
| DELETE dữ liệu do lỗi ứng dụng | PV vẫn hoạt động nhưng dữ liệu sai | Có thể replicate dữ liệu sai | PITR/repair/reconcile |
| Corruption trong DB | Không tự sửa | Corruption có thể lan | Backup sạch và kiểm tra tính toàn vẹn |
| Ransomware/credential bị chiếm | Cần IAM và isolation | Replica vẫn có thể bị ảnh hưởng | Bản backup được bảo vệ và quy trình recovery |
| Cluster bị mất toàn bộ | PVC/PV trong cluster chưa chắc tiếp cận được | DR bên ngoài cluster nếu có | Restore sang môi trường mới |
| Thao tác upgrade DB sai | Storage còn nhưng schema/data không tương thích | Replica có thể cùng bị ảnh hưởng | Roll forward/restore/repair theo trạng thái |

Không có cơ chế duy nhất xử lý mọi hàng trong bảng. Thiết kế tốt phối hợp **cô lập, nhân bản, backup và vận hành khôi phục**.

## 17. Những loại stateful component cần lưu ý riêng

### 17.1. Relational database

PostgreSQL/MySQL giữ transaction, index, WAL/redo log, replication state và schema. Cần quản lý transaction durability, recovery, backup, connection và migration.

Đừng cho nhiều Pod PostgreSQL độc lập ghi cùng một **PGDATA** chỉ vì storage cho phép RWX. Dùng replication/clustering được hỗ trợ và endpoint writer rõ.

### 17.2. Redis và cache

Redis có thể chỉ là cache **có thể tái tạo**, hoặc là data store dùng cho lock/session/workflow. Mức độ persistence cần khác nhau:

- **Cache thuần túy:** mất cache có thể chấp nhận, nhưng cần bảo vệ backend khỏi cache stampede.
- **Session store:** mất session có thể đăng xuất người dùng; xác định SLA.
- **Dữ liệu nghiệp vụ duy nhất:** Redis persistence/replication cần được đánh giá như hệ stateful thật.

Không dùng Redis volatile cache như source of truth cho payment hoặc inventory nếu chưa thiết kế durability và recovery phù hợp.

### 17.3. Kafka hoặc message broker

Broker có log/queue, retention, partition, replica placement và membership. Một PVC cho mỗi broker giúp giữ local log, nhưng **durability của message** còn phụ thuộc replication factor, in-sync replicas, ack policy, producer idempotence, retention và cluster operation.

Khi thay Pod broker, danh tính, storage và quorum controllers phải được quản lý theo cơ chế broker đang dùng. Không gắn replica của cùng partition vào một shared directory để “chia sẻ dữ liệu”.

### 17.4. Search index

Elasticsearch/OpenSearch hoặc search engine có index, replicas và snapshots. Index có thể tái tạo từ database/event source nếu nguồn đầy đủ; cần xác định thời gian rebuild. Nếu index chứa dữ liệu không tái tạo được, nó phải được bảo vệ như source of truth.

### 17.5. Object storage

Object storage quản lý object và metadata theo API riêng. Tránh lưu file upload quan trọng vào local disk của một API Pod. Cần lifecycle/retention, versioning khi phù hợp, encryption, access policy và backup/replication theo dữ liệu.

### 17.6. Work queue và scheduler

Một worker có thể không cần volume nhưng **trạng thái job** phải bền: queue, checkpoint, retry, idempotency và xử lý duplicate delivery. Dùng filesystem tạm của Pod làm hàng đợi duy nhất có thể mất job khi Pod bị xóa.

## 18. Data consistency giữa các microservice

Mỗi service sở hữu database riêng không có nghĩa hệ thống có một transaction ACID bao trùm tất cả.

Ví dụ Order và Payment giữ dữ liệu riêng:

- Order đặt **PAYMENT_PENDING**.
- Payment nhận charge và commit.
- Network timeout trước khi trả response.
- Order không biết charge đã thành công hay chưa.

Dù cả hai database được lưu trên PV tốt, trạng thái hai service vẫn có thể khác nhau trong thời gian ngắn. Cần:

- **Idempotency key** cho thao tác tạo side effect.
- **Outbox/inbox** hoặc event delivery có kiểm soát để giảm khoảng mất message.
- **Saga/compensation** cho workflow nhiều bước.
- **Reconciliation job** để sửa trạng thái không nhất quán.
- **State machine** rõ, phân biệt pending/unknown/failed/success.
- **Event versioning và schema compatibility** để consumer cũ còn xử lý được message tồn đọng.

Đây là phần **data correctness** nằm trên storage durability. PV không tạo atomic transaction xuyên Order và Payment.

## 19. Nâng cấp, migration và cửa sổ tương thích

Một service stateful không chỉ nâng image như stateless API. Khi nâng phiên bản:

1. Kiểm tra compatibility của data format, storage format, cluster protocol và plugin.
2. Kiểm tra hướng nâng cấp được hỗ trợ; có thể cần đi qua version trung gian.
3. Xác nhận backup và restore point trước các bước phá hủy.
4. Kiểm tra cách rolling restart ảnh hưởng leader/quorum.
5. Nếu có schema migration, dùng **expand–migrate–contract** khi nhiều phiên bản app chạy đồng thời.
6. Giữ đường đọc cũ đủ lâu nếu cần rollback app.
7. Theo dõi replication lag, backlog, latency và storage usage.
8. Sau nâng cấp, xác nhận dữ liệu và query quan trọng hoạt động đúng, không chỉ Pod Ready.

**Rollback image không nhất thiết rollback database format.** Một số database hoặc storage engine nâng format trên disk; phiên bản cũ có thể không đọc được. Phải tra cứu compatibility của chính database/phiên bản trước khi chọn rollback.

### 19.1. Migration mất dữ liệu

Các thao tác drop column, thay semantics, re-encode hoặc xóa record lịch sử có thể không đảo ngược. “Down migration” có thể phục hồi schema tên cột nhưng không khôi phục giá trị cũ. Cần backup/PITR hoặc plan roll-forward và repair.

### 19.2. Rolling upgrade và quorum

Với cluster có nhiều replica, thay từng Pod theo thứ tự đã được thiết kế, giữ quorum, bảo vệ leader và không để quá nhiều replica unavailable cùng lúc. **PodDisruptionBudget** có thể hỗ trợ giới hạn voluntary disruption; nó không thay thủ tục upgrade của database hoặc operator.

## 20. Quản trị trách nhiệm vận hành

Điểm khó của stateful microservices thường không phải chỉ là manifest, mà là **ai sở hữu từng loại rủi ro**.

Có thể phân định như sau:

| Trách nhiệm | Nhóm ứng dụng/service | Nhóm nền tảng/SRE | DBA hoặc managed provider |
| --- | --- | --- | --- |
| Quy tắc dữ liệu và business invariants | **Chịu trách nhiệm chính** | Hỗ trợ | Hỗ trợ |
| Schema migration, query và index design | **Chịu trách nhiệm cùng DBA** | Hạ tầng CI/CD | **Chuyên môn database** |
| Cấu hình StorageClass/CSI/PV backend | Nêu yêu cầu IOPS, durability, topology | **Sở hữu hạ tầng K8s/storage** | Provider quản lý phần contract |
| Cluster DB replication/failover | Hiểu rủi ro nghiệp vụ | Tùy mô hình vận hành | **Đơn vị sở hữu DB** |
| Backup policy/RPO/RTO | **Đặt yêu cầu nghiệp vụ, xác minh kết quả** | Triển khai vận hành | Công cụ và khả năng restore |
| Restore drill và data reconciliation | **Xác minh dữ liệu nghiệp vụ** | Điều phối/khôi phục hạ tầng | Phục hồi database |
| Security và truy cập dữ liệu | Quyền API, tenant, service account | RBAC/network/storage IAM | DB role/encryption/tooling |
| Capacity, latency và availability | SLO dịch vụ, connection/pool | Node, disk, network | DB/storage performance |
| Incident response | **On-call service, quyết định tác động nghiệp vụ** | **On-call platform, khôi phục hạ tầng** | Chuyên gia DB hoặc nhà cung cấp |
| Xóa data/retention | **Owner dữ liệu phê duyệt** | Thực thi hạ tầng theo quy trình | Snapshot/backup lifecycle |

Bảng là **ví dụ phân định**; tổ chức thực tế có thể phân vai khác. Điều quan trọng: **không được có vùng trách nhiệm bỏ trống**. Managed database có thể nhận trách nhiệm patching và một số backup, nhưng nhóm ứng dụng vẫn phải biết dữ liệu nào là chính, yêu cầu phục hồi và cách xác minh sau restore.

### 20.1. RACI tối thiểu

Với một thao tác như “xóa PVC production”, nên biết:

- **Responsible:** ai thao tác trực tiếp?
- **Accountable:** ai phê duyệt mất/giữ dữ liệu?
- **Consulted:** ai xác minh backup và consumer dependency?
- **Informed:** ai cần biết downtime và tác động?

Không xây quy trình phê duyệt phức tạp cho mọi restart Pod. Nhưng những thao tác có khả năng xóa dữ liệu hoặc đổi replication topology phải có ownership rõ, audit và cơ chế thao tác an toàn.

## 21. Những chỉ số cần quan sát

### 21.1. Storage-level metrics

- PVC/PV capacity và filesystem **used bytes/available bytes**.
- **Inodes** còn lại với filesystem có inode quota.
- IOPS, throughput, latency đọc/ghi và **fsync latency** khi được cung cấp.
- Disk queue depth, saturation và throttling.
- Storage errors, attach/mount errors và volume provisioning failures.
- Snapshot/backup size, thời gian tạo, thất bại và tuổi backup cuối.

### 21.2. Database/cluster-level metrics

- Database availability, readiness và error rate.
- Query p50/p95/p99 latency; long transactions và lock wait.
- Connection count, pool exhaustion và timeouts.
- Replication lag, WAL/archive lag và tình trạng đồng bộ.
- Leader/quorum state, failover count và thời gian chuyển đổi.
- Transaction commit/rollback rates.
- Dung lượng WAL, bloat và thời gian vacuum/compaction nếu hệ quản trị có.
- Slow queries, deadlocks và integrity alerts.

### 21.3. Business-level metrics

- Số order ở trạng thái không hợp lệ hoặc pending quá lâu.
- Số payment bị trùng hoặc cần đối soát.
- Số reservation bị treo sau khi order hủy.
- Backlog consumer, DLQ, lag theo topic hoặc partition.
- Độ trễ xây read model hoặc cập nhật search index.
- Số bản ghi không thể khôi phục/reconcile sau sự cố.

### 21.4. Metrics cho recovery

- **RPO đạt được** trong lần diễn tập hoặc sự cố.
- **RTO thực tế** theo loại sự cố.
- Tỷ lệ backup thành công và số bản backup có thể restore.
- Restore drill gần nhất và lỗi còn mở.
- Số lần failover, kết quả và ảnh hưởng đến write availability.

Đừng chỉ cảnh báo “disk sử dụng 90%” rồi coi như đủ. Một service có thể còn 30% dung lượng nhưng fsync latency tăng cao, transaction timeouts tăng hoặc replication lag vượt ngưỡng.

## 22. Capacity planning cho storage

### 22.1. Dung lượng không chỉ là kích thước database hiện tại

Ước lượng:

**Dung lượng cần = dữ liệu hiện tại + tăng trưởng + index + WAL/log + khoảng trống bảo trì + buffer cho sự cố.**

Ví dụ một database có 200 GiB data, index thêm 80 GiB, tăng 10 GiB/ngày và cần chịu 30 ngày không mở rộng storage:

- Phần data + index hiện tại: 280 GiB.
- Tăng trưởng 30 ngày: 300 GiB.
- Tổng trước WAL/bloat/maintenance buffer: khoảng 580 GiB.

Con số minh họa; retention, compaction, index rebuild và snapshot cơ chế backend có thể làm nhu cầu thực cao hơn. Không lấy đúng 580 GiB làm cấu hình production.

### 22.2. Storage expansion

Nếu StorageClass hỗ trợ **allowVolumeExpansion**, PVC có thể được yêu cầu tăng dung lượng theo quy trình driver. Nhưng:

- Không phải backend hỗ trợ expansion.
- Filesystem có thể cần resize, online/offline tùy driver và loại filesystem.
- Không phải hệ thống hỗ trợ **shrink** volume.
- Database có thể cần bước vận hành riêng.
- Tăng disk không tự giải quyết bottleneck IOPS hoặc phân vùng dữ liệu.

### 22.3. Chi phí và performance

Storage “nhanh” có thể tính tiền theo provisioned IOPS, throughput, capacity, snapshot và cross-zone transfer. Cần đặt yêu cầu thực tế từ workload:

- Transactional OLTP nhạy fsync latency.
- Analytics/search có nhu cầu throughput lớn.
- Broker cần xử lý write liên tục và retention.
- Backup cần băng thông để hoàn thành trong cửa sổ RTO/RPO.

Một storage class tiết kiệm nhưng quá chậm có thể làm Pod luôn Ready mà database không đáp ứng SLO.

## 23. Bảo mật của thành phần có trạng thái

### 23.1. Phân quyền và cô lập

- Namespace, ServiceAccount và Kubernetes RBAC phải theo **least privilege**.
- Ứng dụng thông thường không cần quyền tạo/xóa PVC hoặc thay StorageClass.
- NetworkPolicy hạn chế đường đi đến DB, nhưng phải xác minh network plugin thực thi chính sách.
- DB user có quyền theo chức năng, tách account migration/admin khỏi runtime app.
- Không mount cùng một PVC chứa dữ liệu nhạy cảm sang những Pod không có quyền.
- Hạn chế khả năng đọc secret và snapshot/backup.

### 23.2. Mã hóa

- Dùng TLS/mTLS khi truyền dữ liệu qua mạng theo threat model.
- Bật encryption at rest tại backend nếu cần; hiểu ai quản lý key.
- Backup và snapshot cũng phải được mã hóa và bảo vệ.
- Tránh lưu encryption key cùng vị trí duy nhất với dữ liệu được mã hóa.
- Có quy trình rotation và khôi phục key sau disaster recovery.

### 23.3. File permission và container user

Các volume có POSIX owner/group, file modes và bảo vệ từ CSI/backend. **securityContext**, **runAsUser**, **fsGroup** có thể hữu ích tùy image và driver; không copy cấu hình chung mà không kiểm tra quyền của database image và chính sách platform.

Đừng giải quyết lỗi permission bằng cách chạy tất cả Pod đặc quyền hoặc mở mode 0777 cho dữ liệu production. Cần kiểm tra điều kiện mount và identity process.

### 23.4. Bảo vệ khỏi xóa nhầm và rò rỉ

- Bật audit cho delete/attach/snapshot/restore theo khả năng nền tảng.
- Kiểm soát việc xóa backend disk và backup object.
- Dùng retention/immutability cho backup quan trọng theo nhu cầu.
- Không đưa plaintext password, connection string chứa secret hoặc dữ liệu nhạy cảm vào logs.
- Đặt cảnh báo cho thao tác delete PVC/PV bất thường, mất snapshot, thay key hoặc thay IAM policy.

## 24. Khôi phục sau sự cố xuyên nhiều service

Ví dụ Order Database được restore đến 10:00, trong khi Payment Database vẫn có giao dịch thành công lúc 10:05.

Lúc này:

- Order có thể không thấy bản ghi mới.
- Payment vẫn ghi nhận tiền đã thu.
- Inventory còn reservation đang giữ.
- Broker vẫn chứa các sự kiện phát sau 10:00.
- Notification đã gửi email xác nhận.

**Restore riêng Order Database không hoàn tác thế giới bên ngoài.**

Quy trình phục hồi cần:

1. Xác định recovery point của từng data source.
2. Xác định khoảng giao dịch bị mất hoặc trạng thái không còn nhất quán.
3. Đối chiếu Order với Payment ledger, Inventory reservations và events.
4. Dùng idempotency key, transaction ID và event ID để tránh tạo side effect trùng.
5. Repair hoặc compensation theo workflow nghiệp vụ được xác minh.
6. Kiểm tra read models/cache/search index nếu cần rebuild.
7. Ghi audit và xác nhận dữ liệu không còn vi phạm business invariants.

**Không phát lại mọi message một cách mù.** Consumer có thể đã xử lý trước khi database bị restore; replay không có deduplication có thể charge, gửi email hoặc ghi dữ liệu lần hai.

## 25. Quy trình vận hành hằng ngày của một StatefulSet/database

Các hoạt động “day 2” cần có người chịu trách nhiệm, lịch và runbook:

| Hoạt động | Điều cần biết |
| --- | --- |
| Khởi động lại Pod | Dữ liệu nằm ở đâu, có downtime không, volume attach mất bao lâu |
| Drain node | PDB, replication/quorum, leader và storage topology |
| Nâng image | Compatibility data format, backup và test rollback |
| Tăng storage | CSI expansion support, filesystem/database steps |
| Giảm replica | Những Pod/PVC nào bị giữ, replica/member nào cần remove |
| Đổi StorageClass | Không phải thay một field PVC là di chuyển backend; cần kế hoạch data migration |
| Di chuyển zone/region | Replica/backup, network latency, data residency và failover |
| Quay vòng secret | Dual credential window, DB connection refresh, không dùng lại key lộ |
| Chạy migration | Schema compatibility, backfill, checkpoint, rollback/roll-forward |
| Restore | Recovery point, staging rehearsal, data reconciliation, RPO/RTO |
| Xóa service | Data retention, PVC/PV reclaim policy, backup archival và quyền phê duyệt |

**GitOps** có thể quản lý StatefulSet/Service/StorageClass manifest, nhưng phần state ngoài declarative manifest vẫn cần quản lý: schema, user, replication membership, backups, secrets và dữ liệu nghiệp vụ.

Nếu GitOps liên tục áp lại desired state, một thao tác hotfix thủ công trên cluster có thể bị đảo ngược. Runbook phải xác định cách cập nhật source of truth.

## 26. Thiết kế thực hành cho hệ Order/Inventory/Payment

Một kiến trúc đơn giản về trách nhiệm:

~~~mermaid
flowchart TB
    C[Client] --> GW[API Gateway]
    GW --> O[Order API replicas]
    GW --> I[Inventory API replicas]
    O --> ODB[(Order DB)]
    I --> IDB[(Inventory DB)]
    O --> P[Payment API replicas]
    P --> PDB[(Payment DB)]
    O --> OB[Transactional outbox]
    OB --> BR[Message broker]
    BR --> N[Notification consumer]
    DBBACK[Backup / PITR storage] -.-> ODB
    DBBACK -.-> IDB
    DBBACK -.-> PDB
~~~

Giả sử:

- Order API, Inventory API, Payment API: **stateless Pods** có thể scale độc lập.
- Mỗi service sở hữu database/schema theo ranh giới nghiệp vụ.
- Database có thể là managed service hoặc cluster stateful có owner vận hành rõ.
- Broker là hệ thống có state, cần replication, retention và monitoring riêng.
- Outbox giúp phối hợp việc commit DB với ý định phát event.
- Backup phải ở failure domain thích hợp và được restore thử.
- Các luồng thanh toán/inventory dùng idempotency và reconciliation.

Thiết kế tốt không làm database biến thành stateless. Nó làm **ranh giới trạng thái rõ**, để ứng dụng có thể thay Pod mà không làm mất dữ liệu, đồng thời mọi thành phần có trạng thái có policy vận hành riêng.

## 27. Bài thực hành: quan sát sự khác nhau giữa emptyDir và PVC

**Bài A — dữ liệu tạm**

1. Tạo một Pod có volume **emptyDir** và ghi một file thử.
2. Restart container trong cùng Pod; quan sát file có thể còn.
3. Xóa Pod và tạo Pod mới; quan sát dữ liệu của emptyDir cũ không theo sang Pod mới.

**Bài B — dữ liệu bền qua Pod recreation**

1. Tạo PVC bằng StorageClass phù hợp và gắn vào StatefulSet một replica.
2. Ghi một record vào database thử nghiệm.
3. Xác định Pod/PVC/PV đang dùng.
4. Xóa Pod, để StatefulSet tái tạo theo ordinal.
5. Đọc record để kiểm chứng persistence.
6. Quan sát events trong khi detach/attach volume.

**Bài C — mô phỏng storage outage**

1. Trên môi trường cô lập, mô phỏng backend storage tạm không thể mount.
2. Quan sát Pod Pending/ContainerCreating và volume attachment errors.
3. Khôi phục backend hoặc chuyển về topology hỗ trợ.
4. Không xóa PVC/PV để “sửa nhanh” nếu dữ liệu cần giữ.
5. Ghi lại RTO thực tế.

**Bài D — khôi phục từ backup**

1. Tạo database test và ghi bộ dữ liệu có thể kiểm chứng.
2. Chụp backup bằng công cụ hỗ trợ của database.
3. Restore sang một instance/namespace cô lập.
4. Chạy checksum và các invariant kiểm tra.
5. Ghi thời gian restore, khả năng truy cập và dữ liệu mất theo mục tiêu.

Không tiến hành xóa disk, restore đè dữ liệu hoặc fault injection trên production chỉ để thực hành.

## 28. Câu hỏi kiểm tra kiến thức

**1. Nếu Pod bị xóa rồi tạo lại, dữ liệu trong emptyDir có sống sót không?**  
Không. emptyDir gắn với vòng đời Pod; restart container trong cùng Pod có thể giữ dữ liệu, nhưng Pod mới không nhận lại emptyDir cũ.

**2. Có PVC thì đã có backup chưa?**  
Chưa. PVC cung cấp cơ chế gắn và yêu cầu storage; backup và restore phải được thiết kế và vận hành riêng.

**3. StatefulSet có ba replica PostgreSQL có tự tạo cluster HA không?**  
Không. StatefulSet cấp danh tính, lifecycle và PVC per ordinal, nhưng replication, leader, quorum, failover và fencing cần cơ chế của database/operator.

**4. RWO có đảm bảo chỉ một Pod ghi cùng PVC không?**  
Không tuyệt đối. RWO là giới hạn theo node; nhiều Pod trên cùng node có thể dùng chung trong những điều kiện nhất định. Nếu cần ràng buộc mount cho một Pod, xem xét RWOP và hỗ trợ CSI, đồng thời giữ bảo vệ cấp ứng dụng.

**5. RWX có nghĩa database có thể chạy nhiều process ghi cùng một thư mục dữ liệu không?**  
Không. RWX nói về khả năng mount, không cung cấp locking/consistency của database.

**6. Tại sao replication không thay backup?**  
Vì lỗi xóa/corruption có thể được nhân bản sang mọi replica. Backup giữ khả năng khôi phục về trạng thái lịch sử phù hợp.

**7. Storage snapshot có luôn database-consistent không?**  
Không. Snapshot tầng storage có thể chỉ crash-consistent; cần cơ chế backup/checkpoint đúng với database và kiểm tra restore.

**8. Mất một zone thì Pod có tự gắn cùng volume sang zone khác không?**  
Tùy storage backend, topology và volume affinity. Một volume zonal thường không gắn được ở zone khác nếu backend không hỗ trợ.

**9. RPO bằng 5 phút và RTO bằng 30 phút nghĩa là gì?**  
Tổ chức chấp nhận tối đa khoảng 5 phút mất dữ liệu theo mục tiêu và đặt mục tiêu phục hồi dịch vụ trong 30 phút. Phải đo bằng diễn tập, không chỉ khai báo.

**10. Ai chịu trách nhiệm xác minh dữ liệu sau restore khi dùng managed database?**  
Nhóm sở hữu nghiệp vụ/dữ liệu phải xác minh business invariants và reconciliation; provider hoặc DBA có thể thực hiện khôi phục hạ tầng.

**11. Có thể rollback image database sau khi nâng format trên disk không?**  
Không được giả định. Phải kiểm tra backward compatibility của storage/data format; có thể cần roll forward hoặc restore được hỗ trợ.

**12. Sau khi restore Order DB về thời điểm cũ, tại sao phải đối soát Payment?**  
Payment có thể đã thu tiền trong khoảng mà Order bị đưa lùi lại, dẫn đến trạng thái xuyên service lệch và rủi ro retry tạo giao dịch trùng.

## 29. Bảng kiểm trước khi vận hành stateful component

### Storage và topology

- [ ] Dữ liệu nào là source of truth, dữ liệu nào tái tạo được?
- [ ] PVC/PV, StorageClass, CSI và access mode phù hợp.
- [ ] Đã kiểm tra zone affinity, attach/mount và capacity.
- [ ] Đã hiểu reclaim policy và PVC retention.
- [ ] Không có nhiều writer không được hỗ trợ cùng ghi một database directory.
- [ ] Có dự phòng hiệu năng/dung lượng phù hợp workload.

### Tính sẵn sàng và phục hồi

- [ ] Đã xác định replication topology, leader/quorum và fencing khi cần.
- [ ] Có RPO/RTO rõ theo dữ liệu nghiệp vụ.
- [ ] Backup ở failure domain thích hợp, retention và encryption phù hợp.
- [ ] Có restore drill và bằng chứng kiểm tra integrity.
- [ ] Đã kiểm tra các sự cố Pod, node, zone và backend storage.
- [ ] Có runbook failover, rollback/roll-forward và data reconciliation.

### Bảo mật và vận hành

- [ ] RBAC, ServiceAccount, DB roles và IAM theo least privilege.
- [ ] Secret/credential có owner, rotation và không bị commit vào code.
- [ ] Network/TLS/encryption-at-rest theo threat model.
- [ ] Có metrics disk/IOPS/latency, replication lag, backup age, business health.
- [ ] Có owner cho migration, backup, restore, patching, deletion và incident.
- [ ] Có quy trình phê duyệt xóa dữ liệu và retention.
- [ ] Đã kiểm tra mixed-version compatibility trong rolling release.

## 30. Tài liệu tham khảo

- Kubernetes — Persistent Volumes: https://kubernetes.io/docs/concepts/storage/persistent-volumes/
- Kubernetes — PersistentVolumeClaims: https://kubernetes.io/docs/concepts/storage/persistent-volumes/#persistentvolumeclaims
- Kubernetes — Storage Classes: https://kubernetes.io/docs/concepts/storage/storage-classes/
- Kubernetes — StatefulSets: https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/
- Kubernetes — Ephemeral Volumes: https://kubernetes.io/docs/concepts/storage/ephemeral-volumes/
- Kubernetes — Volume Snapshots: https://kubernetes.io/docs/concepts/storage/volume-snapshots/
- Kubernetes — Pod Disruption Budgets: https://kubernetes.io/docs/tasks/run-application/configure-pdb/
- Kubernetes — CSI drivers: https://kubernetes-csi.github.io/docs/
- PostgreSQL — Backup and Restore: https://www.postgresql.org/docs/current/backup.html
- PostgreSQL — Continuous Archiving and Point-in-Time Recovery: https://www.postgresql.org/docs/current/continuous-archiving.html
- PostgreSQL — High Availability, Load Balancing, and Replication: https://www.postgresql.org/docs/current/high-availability.html
- AWS Well-Architected — Reliability Pillar: https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html

**Ghi nhớ:** Kubernetes có thể cấp phát storage và giúp Pod có trạng thái giữ danh tính cùng PVC khi được tái tạo. **Khả năng dữ liệu sống sót trước lỗi, tính nhất quán, failover và phục hồi** vẫn phụ thuộc đặc tính backend, cơ chế database/broker, backup, lựa chọn kiến trúc và trách nhiệm vận hành được phân công rõ.
