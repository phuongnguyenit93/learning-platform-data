# Triển khai ứng dụng có trạng thái và quản lý danh tính máy ổn định

Ứng dụng có trạng thái (stateful application) lưu hoặc duy trì trạng thái cần thiết để tiếp tục xử lý, ví dụ dữ liệu giao dịch, session, index, log, checkpoint, metadata hoặc trạng thái thành viên của một cụm. Khi triển khai ứng dụng trên cloud, cần bảo đảm trạng thái tồn tại qua restart và thay thế compute, đồng thời xác định máy hoặc workload nào được phép truy cập dữ liệu và giao tiếp với các thành viên khác.

Một VM có thể bị thay thế, IP có thể đổi, container có thể được reschedule và Pod có thể được tạo lại. Vì vậy, kiến trúc cần tách **danh tính logic**, **danh tính xác thực**, **địa chỉ mạng** và **vòng đời dữ liệu**. Một dịch vụ có thể giữ tên hoặc ordinal ổn định cho thành viên stateful, nhưng vẫn cấp credential mới cho compute instance sau khi thay máy. Điều này giúp ứng dụng khôi phục đúng dữ liệu và duy trì trust boundary khi hạ tầng thay đổi.

Trong module CLOUD_CORE_SERVICES_COMPUTE, bài học kết nối lựa chọn VM, container, Kubernetes, storage, network và security identity với cách triển khai workload stateful. Trọng tâm là hiểu state nằm ở đâu, máy mới kế thừa vai trò nào, credential được cấp ra sao, và làm thế nào để tránh split-brain, mất dữ liệu hoặc nhân bản danh tính khi scale và failover.

Sau bài học, bạn có thể:

- Phân biệt ứng dụng stateful, stateful compute và workload stateless.
- Chọn nơi lưu dữ liệu phù hợp với vòng đời VM, container hoặc Pod.
- Phân biệt resource ID, logical identity, workload identity và network identity.
- Thiết kế danh tính máy ổn định bằng managed identity, service account hoặc certificate có vòng đời rõ.
- Triển khai ứng dụng stateful trên VM, container và Kubernetes StatefulSet.
- Dùng persistent volume, stable DNS, membership, quorum, leader election và fencing đúng mục đích.
- Thực hiện bootstrap, thay máy, rotate credential và failover an toàn.
- Lập kế hoạch backup, restore, scale, rollout và kiểm thử tính toàn vẹn dữ liệu.

## 1. Stateful application là gì?

Một ứng dụng stateful duy trì thông tin cần thiết giữa các request hoặc qua nhiều lần xử lý. Trạng thái có thể nằm trong database, file, volume, cache, log, message offset, index hoặc bộ nhớ tiến trình.

Ví dụ:

- Cơ sở dữ liệu lưu record và transaction log.
- Hệ thống tìm kiếm lưu index và metadata shard.
- Message broker lưu message, offset và trạng thái replication.
- Ứng dụng cộng tác lưu document, revision và lock.
- Stateful worker lưu checkpoint của một job dài.
- Ứng dụng web lưu session hoặc giỏ hàng giữa các request.

Stateful không đồng nghĩa mọi dữ liệu phải nằm trên máy đang chạy ứng dụng. Một API stateless có thể đọc/ghi database stateful dùng chung. Ngược lại, một ứng dụng stateful có thể giữ cache trong RAM nhưng dữ liệu gốc nằm ở storage bền vững.

### Phân biệt stateful application và stateful compute

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Stateful application | Ứng dụng duy trì trạng thái nghiệp vụ hoặc trạng thái xử lý | Database, broker, search cluster |
| Stateful compute | Compute instance có local state hoặc identity/membership gắn với vòng đời máy | VM giữ data disk, node cluster có member ID |
| Stateless compute | Instance có thể thay thế mà không cần chuyển trạng thái cục bộ | API replica, worker có thể retry |
| Externalized state | Trạng thái nằm trong dịch vụ có vòng đời độc lập với compute | Managed database, object storage, shared cache |
| Stateful workload orchestration | Platform duy trì identity/order/storage cho từng replica | Kubernetes StatefulSet |

Một hệ thống có thể kết hợp nhiều loại. Ví dụ API tier stateless chạy trên VM scale set, database tier stateful dùng persistent storage và replication, còn batch worker xử lý queue có thể bị thu hồi.

## 2. Kiểm kê state trước khi triển khai

Trước khi chọn VM hoặc controller, hãy lập danh sách dữ liệu và trạng thái mà ứng dụng cần.

| State | Ví dụ | Nơi lưu thường phù hợp | Yêu cầu chính |
|---|---|---|---|
| Business records | Đơn hàng, tài khoản, giao dịch | Database | Transaction, backup, consistency |
| Binary/file data | Ảnh, tài liệu, artifact | Object storage hoặc shared file storage | Durability, versioning, access control |
| Database files | Data pages, WAL/redo log | Persistent block storage hoặc managed database | Ordering, fsync, recovery, IOPS |
| Search/index data | Index shard, segment | Persistent volume hoặc managed search service | Replication, rebuild, snapshot |
| Session | Login, workflow state | Shared session store hoặc protected token | TTL, security, failover |
| Queue state | Message, offset, consumer position | Durable broker hoặc managed queue | Delivery semantics, replay |
| Local cache | Query cache, compiled artifact | RAM hoặc ephemeral disk | Có thể tái tạo |
| Cluster membership | Node ID, term, shard assignment | Metadata store/cluster consensus | Identity uniqueness, fencing |
| Runtime checkpoint | Job cursor, model state | Database/object storage | Atomic commit, resume |
| Machine credentials | Certificate, key reference | Secret manager/TPM-backed store | Confidentiality, rotation, revocation |

Với mỗi loại state, cần trả lời:

1. Source of truth nằm ở đâu?
2. Dữ liệu có thể tái tạo hay phải bảo toàn?
3. Dữ liệu có cần consistency giữa nhiều file hoặc volume không?
4. Ai được phép đọc/ghi?
5. Khi VM hoặc Pod bị xóa, dữ liệu còn tồn tại không?
6. RPO và RTO là bao nhiêu?
7. Có backup, replication và restore test không?
8. Có thể truy cập từ compute instance thay thế không?

Nếu chưa biết state nằm ở đâu, không thể đánh giá đúng rủi ro khi deploy, scale-in hoặc thay máy.

## 3. Vòng đời dữ liệu phải độc lập với vòng đời compute

Compute instance thường có thể được tạo mới hoặc xóa. Dữ liệu quan trọng cần một vòng đời phù hợp với yêu cầu nghiệp vụ.

### Các lựa chọn lưu trữ

| Storage | Đặc tính | Trường hợp phù hợp | Điểm cần kiểm tra |
|---|---|---|---|
| Instance local/ephemeral disk | Gắn với instance hoặc node; có thể mất khi thay host | Cache, scratch, temporary data | Không dùng làm bản duy nhất của dữ liệu quan trọng |
| Persistent block volume | Volume có thể tồn tại qua restart và attach lại theo điều kiện dịch vụ | Database, index, stateful service | Attachment, zone, filesystem, snapshot, IOPS |
| Shared file storage | Nhiều compute có thể truy cập cùng filesystem theo semantics hỗ trợ | Shared content, application files | Locking, consistency, throughput, mount behavior |
| Object storage | Truy cập qua API, phù hợp object bất biến hoặc có version | File, backup, artifact, checkpoint | Versioning, consistency, retention, request rate |
| Managed database | Provider quản lý nhiều phần vận hành dữ liệu | Transactional data | Backup, failover, endpoint, replica lag, connection limit |
| Distributed data service | Dữ liệu phân tán qua node/shard/replica | Search, broker, distributed database | Quorum, membership, replication, repair |

### Persistent volume không thay thế backup

Một persistent volume có thể sống lâu hơn VM hoặc Pod, nhưng vẫn có thể bị xóa, hỏng logic, mã hóa bởi ransomware hoặc ghi sai dữ liệu. Snapshot và backup cần được thiết kế riêng, có retention và restore test.

### Data durability và availability khác nhau

- Durability nói về khả năng dữ liệu không bị mất.
- Availability nói về khả năng truy cập dịch vụ tại thời điểm cần.
- Consistency nói về trạng thái đọc/ghi quan sát được.
- Recoverability nói về khả năng phục hồi sau sự cố.

Một volume có durability cao nhưng chỉ attach được ở một zone vẫn có thể làm workload gián đoạn khi zone mất. Replication tăng availability nhưng nếu replicate thao tác xóa hoặc corruption, vẫn cần backup có point-in-time recovery.

## 4. Danh tính máy ổn định là gì?

“Danh tính máy” thường bị nhầm với hostname, IP hoặc instance ID. Các giá trị đó có thể hữu ích để định vị resource, nhưng không nhất thiết là credential hoặc định danh logic bền vững.

Cần tách bốn lớp:

| Loại identity | Trả lời câu hỏi | Ví dụ | Có thể thay đổi khi thay máy? |
|---|---|---|---|
| Resource identity | Cloud đang quản lý resource nào? | VM instance ID, container ID, node resource ID | Thường có |
| Logical identity | Đây là thành viên/vai trò nào trong hệ thống? | db-replica-2, shard-03, StatefulSet ordinal | Có thể giữ ổn định |
| Authentication identity | Principal nào đang chứng minh danh tính để được cấp quyền? | Managed identity, service account, X.509 certificate, SPIFFE ID | Có thể được cấp lại/rotate |
| Network identity | Client tìm và kết nối đến endpoint nào? | DNS name, service name, private IP, load balancer | IP có thể đổi; tên có thể ổn định |

Một kiến trúc tốt không dựa vào một địa chỉ IP cố định để xác thực máy. DNS hoặc service discovery cung cấp endpoint; identity provider chứng minh principal; authorization quyết định principal được làm gì; persistent storage giữ state.

### Ví dụ

Một database replica có logical name **orders-db-2**. VM hiện tại có instance ID **i-abc123**, private IP **10.10.2.15** và certificate serial **cert-91**. Khi VM bị thay thế:

- Logical role vẫn là **orders-db-2**.
- Instance ID mới là **i-def456**.
- IP có thể là **10.10.2.27**.
- Certificate mới được cấp và có serial khác.
- Data volume được attach lại theo quy trình an toàn.
- Cluster membership xác minh node mới đang tiếp quản đúng member identity.

Không nên sao chép certificate private key của VM cũ sang image hoặc VM mới chỉ để giữ nguyên serial. Giữ logical identity và cấp authentication credential mới thường an toàn hơn.

## 5. Stable identity không có nghĩa dùng IP tĩnh

IP tĩnh đôi khi cần cho allow-list hoặc giao tiếp với hệ thống cũ, nhưng không nên là cơ chế xác thực duy nhất.

### Hostname

Hostname có thể được giữ qua rebuild nếu quy trình cấu hình đặt tên theo logical role. Tuy nhiên hostname có thể bị giả mạo hoặc trùng nếu bootstrap sai; nó không tự chứng minh máy được tin cậy.

### Private IP

Private IP có thể thay đổi khi instance thay thế, subnet đổi hoặc network interface được tạo lại. Một số dịch vụ hỗ trợ gắn IP tĩnh hoặc secondary IP, nhưng IP đó là thuộc tính mạng và có lifecycle riêng.

### DNS/service discovery

DNS name hoặc service registry giúp client tìm endpoint mà không cần biết IP cụ thể. DNS có thể cập nhật khi failover hoặc replacement. Cần quản lý TTL, health, split-horizon và cache.

### Identity-based access

Dùng workload identity, managed identity, instance role, service account hoặc certificate để chứng minh principal. Policy gắn quyền vào identity thay vì phụ thuộc địa chỉ mạng.

Có thể kết hợp DNS, private IP và identity-based authorization, nhưng mỗi thành phần phải giữ đúng vai trò của nó.

## 6. Các mô hình cấp machine identity

Cloud và platform có nhiều cách cấp danh tính cho compute.

### Instance profile hoặc managed identity

VM được gắn role/managed identity. Ứng dụng lấy token ngắn hạn từ metadata/identity endpoint theo cơ chế provider. Không cần bake access key dài hạn vào image.

Ưu điểm:

- Credential được cấp tự động theo vòng đời instance.
- Có thể thu hồi hoặc điều chỉnh quyền ở control plane.
- Token ngắn hạn giảm rủi ro lộ credential lâu dài.
- Có thể tách quyền theo workload role.

Điểm cần bảo vệ:

- Chặn truy cập metadata từ workload không được phép.
- Dùng metadata service mode an toàn theo provider.
- Giới hạn IAM permission theo least privilege.
- Không log token hoặc credential.
- Kiểm tra token audience, expiry và rotation.
- Tách role giữa API, worker, backup agent và admin task.

### Kubernetes ServiceAccount và Workload Identity

Pod có thể dùng ServiceAccount để nhận identity. Managed Kubernetes thường hỗ trợ liên kết ServiceAccount với cloud IAM principal hoặc workload identity federation. Khi Pod được tạo lại, identity logic có thể giữ theo ServiceAccount, còn token được cấp mới và có thời hạn.

Không dùng một node role quá rộng cho mọi Pod. Tách quyền ở cấp workload giúp giới hạn blast radius.

### X.509 certificate và mutual TLS

Machine hoặc workload có thể dùng certificate để xác thực qua TLS/mTLS. Certificate có subject/SAN hoặc URI identity gắn với machine/workload. Private key cần được bảo vệ bằng secret manager, secure enclave hoặc TPM khi có yêu cầu.

Cần có quy trình:

- Enrollment và xác minh danh tính ban đầu.
- Cấp certificate theo policy.
- Rotation trước expiry.
- Thu hồi khi máy bị xâm nhập hoặc loại bỏ.
- Trust bundle distribution.
- Audit việc cấp và sử dụng certificate.

### SPIFFE/SPIRE và workload identity framework

Một số hệ thống dùng SPIFFE ID hoặc cơ chế tương tự để biểu diễn danh tính workload độc lập với IP. Workload nhận SVID (thường là X.509 hoặc JWT) từ identity control plane sau khi được attestation. Đây là mô hình phù hợp khi có nhiều service, môi trường và cluster cần mTLS nhất quán.

Cần phân biệt identity của workload với identity của host. Host có thể chứng minh node/VM đáng tin cậy; workload identity xác định process hoặc service đang chạy trên host đó.

### TPM và attestation

TPM hoặc hardware-backed security có thể giữ key không xuất được và cung cấp bằng chứng về trạng thái boot/hardware. Attestation cho phép identity service kiểm tra máy có đáp ứng baseline trước khi cấp credential.

Không phải mọi cloud VM hoặc serverless runtime đều cho phép khách hàng dùng trực tiếp TPM/attestation. Kiểm tra loại instance, confidential computing feature và dịch vụ identity thực tế.

## 7. Phân biệt identity theo role với identity riêng từng instance

Hai cách thiết kế phổ biến:

**Role-based identity:** mọi replica của một workload nhận principal/role có cùng bộ quyền, nhưng mỗi instance có token ngắn hạn riêng. Phù hợp với API stateless hoặc worker pool đồng nhất.

**Per-instance identity:** mỗi VM/node có principal hoặc certificate riêng. Phù hợp khi cần audit, revoke từng máy, mTLS peer identity hoặc policy theo member.

Với stateful cluster, thường cần cả hai lớp:

- Logical member ID xác định vị trí/role của replica.
- Per-instance authentication identity xác minh compute instance hiện tại.
- Cluster membership hoặc consensus xác nhận replica có quyền tham gia.
- Fencing/version ngăn instance cũ ghi sau khi đã bị thay thế.

Không nên dùng một credential tĩnh được copy sang tất cả node nếu hệ thống cần phân biệt từng member.

### Ma trận lựa chọn

| Nhu cầu | Identity thường phù hợp |
|---|---|
| Nhiều API replica cùng quyền truy cập database | Role/managed identity theo workload |
| Audit và revoke từng VM | Per-instance certificate hoặc instance principal |
| Kubernetes Pod truy cập cloud service | ServiceAccount liên kết workload identity |
| mTLS giữa các service | X.509/SPIFFE identity |
| Kiểm tra integrity của host trước khi cấp secret | Hardware-backed attestation nếu nền tảng hỗ trợ |
| Stateful member cần ordinal ổn định | Logical member ID + credential riêng được cấp lại |

## 8. Triển khai stateful application trên VM

VM phù hợp khi ứng dụng cần OS, kernel, disk layout hoặc phần mềm đặc thù. Với stateful workload, cần tách boot disk và data disk.

### Boot disk và data disk

- Boot disk chứa OS và phần mềm có thể tái tạo từ image.
- Data disk chứa database files, index hoặc state cần tồn tại.
- Backup/snapshot bảo vệ data disk theo consistency requirement.
- VM replacement có thể tạo từ image mới rồi attach data disk theo quy trình.
- Filesystem mount và application recovery phải được kiểm tra trước khi mở traffic.

Không đặt toàn bộ dữ liệu duy nhất trên boot disk nếu chiến lược thay máy cần rebuild OS. Nếu data disk được attach vào VM mới, phải đảm bảo VM cũ đã bị fencing hoặc detached an toàn trước khi mount ghi trên máy mới.

### Bootstrap

Quy trình tạo VM stateful:

1. Tạo VM từ image đã version hóa.
2. Gắn managed identity/instance role.
3. Nhận logical role hoặc member assignment từ control plane.
4. Lấy certificate/secret theo identity.
5. Attach hoặc discover persistent data volume.
6. Kiểm tra volume ID, filesystem, encryption key và mount state.
7. Chạy application recovery (journal/WAL/redo replay nếu cần).
8. Xác minh cluster membership và replication status.
9. Chỉ nhận traffic khi readiness và consistency check đạt.

### Không clone identity từ golden image

Golden image chỉ nên chứa phần mềm và cấu hình nền. Không chứa machine private key, unique node ID, host certificate hoặc secret của một instance đã chạy. Nếu clone một image có cùng machine identity sang nhiều VM, hệ thống có thể gặp duplicate identity, mTLS conflict hoặc ghi đè audit.

### VM identity flow

~~~mermaid
flowchart TD
    A[Provision VM từ image] --> B[Cloud cấp resource ID mới]
    B --> C[Attach managed identity/instance role]
    C --> D[Bootstrap nhận logical role]
    D --> E[Enrollment cấp certificate mới]
    E --> F[Attach persistent data volume]
    F --> G[Kiểm tra dữ liệu và membership]
    G --> H[Readiness thành công]
    H --> I[Đưa vào service traffic]
~~~

## 9. Triển khai stateful application bằng container

Container giúp đóng gói runtime và dependencies, nhưng container filesystem thường không phải nơi lưu dữ liệu bền vững.

Các nguyên tắc:

- Image bất biến và được version hóa.
- Data đặt trên persistent volume hoặc external service.
- Container identity lấy từ service account/workload identity.
- Không bake certificate private key hoặc credential vào image.
- Có readiness/liveness/startup probe.
- Graceful shutdown và drain trước khi terminate.
- Kiểm soát UID/GID, filesystem permission và securityContext.

### Container replacement

Khi container bị restart, container ID mới có thể được tạo. Pod có thể giữ nguyên hoặc bị thay thế tùy nguyên nhân. Dữ liệu trong writable layer không nên được coi là bền vững. Volume mount có thể giữ dữ liệu qua container restart, nhưng vòng đời volume và khả năng attach lại phụ thuộc storage driver.

### Một container hay nhiều container?

Ứng dụng stateful có thể dùng sidecar cho backup agent, log collector hoặc proxy. Sidecar trong cùng Pod chia sẻ một số tài nguyên và vòng đời; nếu backup agent làm chậm hoặc giữ file lock, cần đánh giá tác động lên ứng dụng.

Không đóng gói database, backup agent và nhiều ứng dụng độc lập vào một container chỉ để giảm số Pod. Mỗi thành phần nên có lifecycle và failure handling rõ.

## 10. StatefulSet và stable identity trong Kubernetes

Kubernetes StatefulSet được thiết kế cho workload cần identity ổn định theo ordinal, thứ tự triển khai/scale và storage riêng cho từng Pod.

Ví dụ StatefulSet có 3 replica tạo tên Pod:

- orders-db-0
- orders-db-1
- orders-db-2

Ordinal của Pod giữ ổn định khi Pod được thay thế trong StatefulSet. Với headless Service, mỗi Pod có thể có DNS ổn định theo tên Pod và service. Volume claim template có thể tạo PVC riêng theo ordinal.

### StatefulSet không tự biến ứng dụng thành distributed database

StatefulSet cung cấp primitive về identity, ordering và volume association. Ứng dụng vẫn phải tự xử lý:

- Replication và consistency.
- Leader election hoặc primary/replica role.
- Quorum và membership.
- Backup/restore.
- Failover và fencing.
- Schema/data migration.
- Recovery khi volume hỏng hoặc zone mất.

Không nên dùng StatefulSet chỉ vì ứng dụng “có database” nếu managed database hoặc Deployment + external state phù hợp hơn.

### Ví dụ headless Service và StatefulSet

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-db
spec:
  clusterIP: None
  selector:
    app: orders-db
  ports:
    - name: database
      port: 5432
      targetPort: 5432
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: orders-db
spec:
  serviceName: orders-db
  replicas: 3
  selector:
    matchLabels:
      app: orders-db
  template:
    metadata:
      labels:
        app: orders-db
    spec:
      serviceAccountName: orders-db
      containers:
        - name: database
          image: registry.example/orders-db:16.2
          ports:
            - name: database
              containerPort: 5432
          volumeMounts:
            - name: data
              mountPath: /var/lib/database
          resources:
            requests:
              cpu: "1"
              memory: "2Gi"
            limits:
              cpu: "2"
              memory: "4Gi"
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: fast-block
        resources:
          requests:
            storage: 100Gi
~~~

Đây là manifest minh họa cấu trúc Kubernetes, không phải cấu hình production cho một database cụ thể. Cần image chính thức, storage class phù hợp, securityContext, probes, backup agent/operator, anti-affinity/topology spread, PodDisruptionBudget, secret injection và quy trình bootstrap/replication đúng với database.

### Stable DNS

Với headless Service và StatefulSet, Pod có thể được phân giải theo dạng:

~~~text
<statefulset-pod>.<headless-service>.<namespace>.svc.cluster.local
~~~

Ví dụ orders-db-0.orders-db.production.svc.cluster.local. DNS giúp định vị member ổn định; nó không chứng minh member có quyền làm primary hoặc được phép ghi dữ liệu. Ứng dụng vẫn phải xác minh role và membership.

### PVC lifecycle

PVC do StatefulSet tạo thường tồn tại qua Pod replacement. Xóa StatefulSet không nhất thiết xóa PVC theo mọi policy; cần kiểm tra retention policy và storage reclaim policy của cluster. Không giả định PVC luôn được giữ hoặc luôn bị xóa. Backup và restore phải được quản lý độc lập.

## 11. Cluster membership, quorum và leader election

Ứng dụng phân tán thường cần biết node nào là thành viên, node nào có quyền ghi và khi nào có thể bầu leader.

### Membership

Membership có thể lưu:

- Member ID hoặc ordinal.
- Endpoint/DNS name.
- Role (voter, learner, replica, observer).
- Generation/term.
- Health/heartbeat.
- Replication position.
- Version và compatibility metadata.

Membership phải được cập nhật theo giao thức của ứng dụng. Không chỉ dựa vào việc một Pod tồn tại hoặc DNS resolve thành công.

### Quorum

Một số hệ thống consensus yêu cầu quorum để chấp nhận thay đổi. Với N voting member, quorum đa số thường là:

\[
Q = \left\lfloor \frac{N}{2} \right\rfloor + 1
\]

Ví dụ cụm 3 voter cần 2 voter để đạt majority; cụm 5 voter cần 3. Mất quorum có thể khiến hệ thống dừng ghi để bảo vệ consistency.

Không tăng số replica tùy tiện mà không hiểu membership protocol. Một replica mới có thể cần bootstrap từ snapshot, catch up log và chỉ sau đó mới được nâng thành voter.

### Leader election

Leader election chọn một member điều phối ghi hoặc công việc nền. Cần có:

- Lease/term có timeout.
- Heartbeat.
- Cơ chế chống hai leader cùng hoạt động.
- Fencing token hoặc epoch tăng dần.
- Quy trình xử lý network partition.
- Observability cho election churn.

Một worker cũ có thể tiếp tục chạy sau khi lease hết hạn do pause hoặc network partition. Storage hoặc downstream system cần từ chối ghi từ epoch cũ.

### Fencing

Fencing ngăn member đã mất quyền tiếp tục ghi. Ví dụ:

- Node A có term 12.
- A bị cô lập mạng.
- Node B được bầu với term 13.
- B bắt đầu ghi.
- A hồi phục và gửi write với term 12.
- Storage/consensus layer từ chối write của A.

Chỉ đặt lock hoặc DNS record không đủ nếu client cũ vẫn có thể ghi vào storage. Fencing phải được áp dụng tại nơi có thể kiểm soát side effect.

## 12. Persistent volume, attach/detach và single-writer safety

Với block volume, cần hiểu attachment semantics và access mode. Một số volume chỉ cho phép attach/mount ghi từ một node tại một thời điểm; một số storage hỗ trợ multi-attach nhưng không tự cung cấp distributed locking hoặc consistency cho filesystem.

### Quy trình chuyển volume sang compute mới

1. Đánh dấu member cũ không nhận write mới.
2. Fencing hoặc xác nhận member cũ đã dừng.
3. Flush dữ liệu và detach volume nếu máy cũ còn hoạt động.
4. Nếu máy cũ mất đột ngột, dùng quy trình force detach theo hướng dẫn storage/provider và xác minh không còn writer.
5. Attach volume vào máy/Pod mới.
6. Kiểm tra encryption key, filesystem và volume identity.
7. Chạy recovery tool của ứng dụng/database.
8. Xác minh consistency và replication position.
9. Đưa member mới vào cluster theo membership protocol.

Không attach cùng một filesystem ghi trên hai máy nếu storage/filesystem không hỗ trợ. Có thể gây corruption dù cả hai VM đều healthy.

### Volume topology

Persistent disk có thể bị giới hạn zone. Pod có PVC gắn với volume ở zone A có thể không chạy trên node zone B. StorageClass topology, volume binding mode và scheduler cần được cấu hình phù hợp.

Nếu cần zone failover, chọn storage/replication architecture hỗ trợ yêu cầu đó. Một volume zonal không tự chuyển sang zone khác chỉ vì StatefulSet tạo Pod mới.

## 13. Network identity và endpoint ổn định

Stateful cluster thường cần cả endpoint client ổn định và endpoint member ổn định.

### Client endpoint

Client thường kết nối đến:

- Load balancer hoặc Service.
- DNS alias cho primary/leader.
- Managed database endpoint.
- Gateway hoặc proxy có khả năng chọn backend.

Endpoint client có thể trỏ đến primary hiện tại sau failover. Cần TTL, health check và client retry phù hợp.

### Member endpoint

Mỗi member có thể cần hostname ổn định để trao đổi replication hoặc heartbeat. StatefulSet headless DNS hoặc private DNS record có thể hỗ trợ. Nhưng DNS chỉ ánh xạ tên sang địa chỉ; cluster protocol vẫn phải xác thực member.

### Không dùng IP làm member ID

Nếu member ID được suy ra từ IP, thay subnet hoặc recreate node có thể làm thay đổi membership ngoài dự kiến. Dùng logical ID được quản lý trong metadata/StatefulSet ordinal hoặc database cluster config; dùng network endpoint riêng để kết nối.

### DNS cache và failover

Client có thể cache DNS hoặc giữ connection pool lâu hơn TTL. Sau failover, cần:

- Đóng/refresh connection đến endpoint cũ.
- Retry với backoff.
- Xác minh role primary mới trước khi ghi.
- Dùng transaction/idempotency để xử lý kết quả không xác định.
- Tránh ghi đồng thời vào cả primary cũ và mới.

## 14. Bootstrap và enrollment an toàn

Một máy mới cần chứng minh danh tính trước khi nhận secret hoặc tham gia stateful cluster.

### Bootstrap sequence

~~~mermaid
sequenceDiagram
    participant P as Provisioner
    participant VM as New compute
    participant ID as Identity service
    participant SM as Secret manager
    participant CL as Cluster control
    P->>VM: Create from trusted image
    VM->>ID: Present instance identity/attestation
    ID-->>VM: Short-lived workload credential
    VM->>SM: Request scoped secret/certificate
    SM-->>VM: Certificate/config
    VM->>CL: Register logical member and generation
    CL-->>VM: Membership/role decision
    VM->>VM: Attach data and recover state
    VM->>CL: Report readiness and replication status
~~~

### Nguyên tắc

- Image phải được build từ pipeline tin cậy và có version.
- Không bake unique machine credential vào image.
- Identity provider phải xác minh resource hoặc workload trước khi cấp quyền.
- Credential ngắn hạn và có rotation.
- Secret manager chỉ trả secret đúng scope.
- Logical member assignment phải được cấp hoặc xác minh qua control plane.
- Node mới không được ghi trước khi hoàn tất fencing/recovery.
- Audit enrollment, certificate issuance, secret access và membership change.

### Cloud-init và bootstrap script

Bootstrap nên idempotent và có thể chạy lại. Không ghi đè data volume, reset database hoặc tạo member ID mới nếu thao tác đang chạy dở. Dùng trạng thái/marker có version và kiểm tra điều kiện trước khi thực hiện destructive operation.

## 15. Credential rotation và thu hồi danh tính

Credential cần được rotate định kỳ và khi có sự cố. Rotation không nên làm gián đoạn toàn bộ cluster.

Một quy trình certificate rotation có thể gồm:

1. Cấp certificate mới cho instance/workload.
2. Cập nhật trust bundle để chấp nhận cả certificate cũ và mới trong giai đoạn chuyển tiếp.
3. Reload service hoặc khởi tạo connection mới.
4. Xác minh mTLS với peer.
5. Thu hồi certificate cũ sau khi không còn được dùng.
6. Audit và xác nhận không còn client dùng credential cũ.

Với managed identity, rotation token thường được platform quản lý; ứng dụng vẫn cần xử lý token expiry và refresh.

Khi VM bị nghi xâm nhập:

- Thu hồi hoặc disable principal/certificate.
- Cô lập network.
- Fencing member khỏi quyền ghi.
- Thay compute từ image tin cậy.
- Cấp credential mới.
- Restore hoặc xác minh data volume.
- Kiểm tra audit log và secret access.
- Chỉ tái gia nhập cluster sau khi kiểm tra integrity.

Không xóa identity cũ trước khi xác định dependency và audit cần thiết, nhưng phải chặn quyền truy cập nguy hiểm ngay theo incident procedure.

## 16. Scale stateful workload

Scale stateful workload phức tạp hơn tăng replica stateless vì mỗi replica có thể có dữ liệu, identity và vai trò riêng.

### Vertical scaling

Tăng CPU/RAM/storage throughput cho member hiện tại. Có thể phù hợp khi:

- Database chưa cần sharding.
- Một shard cần memory lớn.
- Workload có giới hạn parallelism.
- Scale ngang làm tăng coordination quá nhiều.

Cần kiểm tra downtime, resize support, volume IOPS và license.

### Horizontal scaling

Có thể gồm:

- Read replica để tăng read throughput.
- Sharding/partitioning để phân chia dữ liệu.
- Broker partition để phân phối consumer.
- Search shard/replica để mở rộng index.
- StatefulSet replica để duy trì member identity.

Tăng replica không đồng nghĩa tăng write capacity. Nếu tất cả member cùng ghi vào một leader, leader vẫn là bottleneck.

### Scale-in

Trước khi giảm replica:

- Xác định member có shard/partition/leader role nào.
- Rebalance hoặc migrate dữ liệu.
- Drain client/connection.
- Remove member qua protocol chính thức.
- Xác nhận replication và quorum còn đủ.
- Sau đó mới detach/delete storage hoặc compute.

Xóa Pod/VM trực tiếp có thể làm cluster mất quorum hoặc phải rebuild shard tốn thời gian.

### Autoscaling

Autoscaler không hiểu đầy đủ mọi semantics stateful của ứng dụng. Cần controller/operator hoặc quy trình riêng để scale member, rebalance, join/leave và bảo đảm quorum. Không áp dụng HPA tăng replica cho database cluster nếu database không hỗ trợ dynamic membership.

## 17. Triển khai, upgrade và rolling replacement

Stateful app cần tương thích giữa phiên bản ứng dụng, schema, data format và cluster protocol.

### Rolling update

Thay từng member theo thứ tự được ứng dụng hỗ trợ:

1. Xác minh cluster khỏe và replication lag thấp.
2. Chọn member có thể restart theo protocol.
3. Drain traffic hoặc chuyển role.
4. Backup/checkpoint theo yêu cầu.
5. Thay compute hoặc image.
6. Cấp identity/certificate và attach data.
7. Khởi động, recover và catch up replication.
8. Kiểm tra health, version và membership.
9. Tiếp tục member kế tiếp.

Không restart nhiều voter cùng lúc nếu có nguy cơ mất quorum.

### Expand-and-contract migration

Khi schema hoặc data format thay đổi:

- Thêm cấu trúc mới tương thích phiên bản cũ.
- Deploy phiên bản đọc/ghi cả hai hoặc có compatibility.
- Backfill dữ liệu.
- Chuyển consumer sang cấu trúc mới.
- Xác minh không còn member cũ.
- Loại bỏ cấu trúc cũ trong release sau.

### Image rollback không rollback dữ liệu

Rollback VM/container image không tự đảo ngược schema hoặc dữ liệu đã ghi bởi phiên bản mới. Cần có compatibility window, backup và migration/compensation strategy.

## 18. Availability, backup và recovery

Stateful workload cần kế hoạch bảo vệ dữ liệu và phục hồi thành viên.

### Backup

- Database backup có application consistency và point-in-time recovery khi cần.
- Snapshot volume theo lịch và theo yêu cầu consistency.
- Object versioning/retention.
- Backup encryption key và kiểm soát quyền restore.
- Backup metadata/configuration/identity policy cần để dựng lại.
- Tách quyền xóa backup khỏi quyền vận hành workload.
- Kiểm thử restore định kỳ.

### Replication

Replication giúp giảm RPO và hỗ trợ failover, nhưng có thể replicate corruption hoặc deletion. Cần kết hợp backup bất biến và point-in-time restore.

### RPO/RTO

Xác định theo workload:

- RPO: lượng dữ liệu có thể mất.
- RTO: thời gian khôi phục dịch vụ.
- Failover time: thời gian phát hiện, quyết định, promote và chuyển traffic.
- Rebuild time: thời gian tạo compute, attach storage, recover và catch up.

### Recovery sequence

1. Xác định sự cố và recovery point.
2. Fencing member cũ hoặc writer cũ.
3. Khôi phục storage/replica.
4. Tạo compute mới từ image đã kiểm thử.
5. Cấp identity/certificate.
6. Attach volume và chạy recovery.
7. Rejoin membership/quorum.
8. Xác minh consistency và transaction.
9. Cập nhật DNS/endpoint và chuyển traffic.
10. Theo dõi SLO, replication và audit.

## 19. Ví dụ kiến trúc: dịch vụ lưu trữ đơn hàng có stateful members

Một hệ thống đơn hàng có API, database cluster ba member và worker xử lý event.

~~~mermaid
flowchart TD
    U[Client] --> LB[Load balancer / stable DNS]
    LB --> API1[Stateless API A]
    LB --> API2[Stateless API B]
    API1 --> DBP[(Database primary)]
    API2 --> DBP
    DBP --> DBR1[(Replica 1)]
    DBP --> DBR2[(Replica 2)]
    API1 --> Q[(Durable queue)]
    API2 --> Q
    Q --> W[Idempotent workers]
    W --> OS[(Object storage)]
    subgraph Identity
      WI[Workload identity]
      CA[Certificate authority]
      SM[Secret manager]
    end
    API1 -.-> WI
    API2 -.-> WI
    DBP -.-> CA
    DBR1 -.-> CA
    DBR2 -.-> CA
    WI --> SM
~~~

Thiết kế:

- API stateless chạy nhiều replica; mỗi Pod/VM dùng role orders-api với quyền tối thiểu.
- Database members có logical identity riêng và certificate riêng.
- Database data nằm trên persistent volume hoặc managed database service.
- DNS/service endpoint cho client trỏ đến writer hiện tại.
- Replication và consensus/database protocol quản lý member state.
- Worker xử lý queue có idempotency và checkpoint.
- Backup được lưu ở storage độc lập và có retention.
- Monitoring theo dõi replication lag, quorum, connection, storage latency và certificate expiry.

### Khi primary bị lỗi

1. Cluster phát hiện primary không còn khỏe.
2. Cơ chế consensus/election xác định member có quyền tiếp quản.
3. Fencing ngăn primary cũ ghi nếu nó hồi phục muộn.
4. Replica được promote theo protocol database.
5. DNS/proxy/load balancer cập nhật writer endpoint.
6. API reconnect và retry an toàn bằng transaction/idempotency.
7. Compute cũ được cô lập, credential thu hồi hoặc rotate.
8. Node thay thế được tạo và rejoin theo quy trình.

Không tự động đổi DNS sang một replica chỉ vì health check TCP thành công. Endpoint writer phải được xác định bởi database role hoặc control plane có authority.

## 20. Ví dụ identity policy theo workload

Một policy minh họa:

| Principal | Được phép | Không nên được cấp |
|---|---|---|
| orders-api | Đọc secret DB, kết nối DB theo role ứng dụng, publish order event | Quản trị cluster, xóa backup, rotate CA |
| orders-db-member | Đọc certificate riêng, trao đổi replication với peer, truy cập volume của member | Đọc secret của API hoặc quản trị toàn cloud account |
| orders-worker | Consume queue, đọc object input, ghi output và cập nhật job status | Ghi trực tiếp vào bảng quản trị database không cần thiết |
| backup-agent | Đọc dữ liệu theo backup policy và ghi backup vault | Xóa backup retention lock hoặc cấp quyền admin workload |
| platform-operator | Thực hiện tác vụ vận hành qua quy trình được audit | Dùng chung credential runtime của ứng dụng |

Tách role giúp khi một worker bị xâm nhập, attacker không có quyền quản trị database hoặc xóa backup. Với per-instance identity, có thể thu hồi đúng certificate hoặc principal của member lỗi.

## 21. Bảo mật state và machine identity

### Data at rest

- Mã hóa boot/data volume và object storage.
- Dùng customer-managed key khi yêu cầu kiểm soát.
- Phân quyền key riêng cho workload và backup.
- Không để credential nằm trong snapshot/image không bảo vệ.
- Quản lý retention và secure deletion theo chính sách.

### Data in transit

- TLS/mTLS giữa member và service.
- Xác minh hostname/SAN và trust chain.
- Rotate certificate có overlap.
- Không tắt verification khi gặp lỗi certificate.
- Dùng private network và segmentation theo workload.

### Runtime hardening

- Patch OS, kernel, container runtime và application.
- Chạy non-root và least privilege.
- Bảo vệ metadata endpoint.
- Tắt port quản trị không cần.
- Audit SSH/remote access và API control plane.
- Gửi log ra ngoài compute để không mất khi instance bị xóa.

### Clone và snapshot

Snapshot có thể chứa machine-specific state như host key, certificate, node ID, local account hoặc secret cache. Trước khi dùng snapshot để tạo máy mới, xác định thành phần nào cần regenerate và thành phần nào là stateful data phải giữ nguyên.

Không clone nguyên data volume của một cluster member để tạo hai writer độc lập. Nếu cần tạo replica, dùng cơ chế clone/bootstrap được database hoặc distributed system hỗ trợ.

## 22. Quan sát và vận hành

Theo dõi cả compute, storage, identity và cluster protocol.

### Compute

- CPU, memory, disk pressure và network throughput.
- Restart, eviction, node health và boot time.
- Container/VM version và image drift.
- Startup/readiness duration.

### State and storage

- Volume attach/detach errors.
- IOPS, throughput, latency và queue depth.
- Database transaction log/WAL growth.
- Replication lag và recovery time.
- Backup success, restore test và retention.
- Checkpoint age và job resume status.

### Identity

- Token issuance/refresh failures.
- Certificate expiry, rotation và revocation.
- Authentication/authorization failure.
- Duplicate logical identity hoặc instance identity.
- Metadata endpoint access anomalies.
- Secret manager access audit.

### Cluster

- Member count, quorum status và leader changes.
- Election churn và fencing rejection.
- Split-brain suspicion.
- Node join/leave duration.
- Client reconnect, DNS update và endpoint change.
- Version skew và schema compatibility.

Không đưa token, private key, password hoặc raw certificate private material vào log. Ghi identity reference, certificate serial/fingerprint và correlation ID ở mức an toàn.

## 23. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Máy mới không lấy được secret | Managed identity/role chưa gắn, trust policy sai hoặc token endpoint lỗi | Instance profile, service account binding, IAM audit |
| Certificate bị từ chối | SAN/identity không khớp, trust bundle cũ hoặc certificate hết hạn | Issuance, expiry, SAN, CA bundle, clock |
| Pod có tên ổn định nhưng không join cluster | DNS/Service đúng nhưng membership hoặc credential sai | Cluster member registry, mTLS identity, join protocol |
| Volume attach thất bại | Volume còn attach ở máy cũ, zone mismatch hoặc key không dùng được | Attachment state, fencing, topology, KMS |
| Hai member cùng ghi | Split-brain hoặc fencing không hoạt động | Leader term, quorum, writer lease, storage enforcement |
| StatefulSet Pod Pending | PVC topology, storage capacity, taint/affinity hoặc quota | Events, PVC/PV, StorageClass, node capacity |
| Pod mới khởi động nhưng dữ liệu sai | Gắn nhầm volume, restore point cũ hoặc schema không tương thích | Volume ID, backup timestamp, schema/version |
| Failover thành công nhưng client vẫn lỗi | DNS cache, connection pool cũ hoặc endpoint chưa cập nhật | DNS TTL, client reconnect, proxy/Service endpoints |
| Scale-in làm mất quorum | Loại voter trước khi reconfigure membership | Membership state, PDB, quorum policy |
| Clone VM gây duplicate identity | Image chứa host key/certificate/member ID | Image build, bootstrap regeneration, identity audit |

### Quy trình điều tra

1. Xác định logical member ID và resource ID hiện tại.
2. Xác minh authentication identity và certificate.
3. Kiểm tra endpoint/DNS và route.
4. Kiểm tra volume ID, attachment, encryption key và filesystem.
5. Đọc cluster membership, term, quorum và replication lag.
6. Xác minh không có writer cũ.
7. Chạy consistency/health check của ứng dụng.
8. Chỉ mở traffic hoặc cho phép write sau khi trạng thái đã rõ.

## 24. Kiểm thử replacement, failover và identity lifecycle

Một thiết kế stateful cần được kiểm thử bằng tình huống compute thực sự bị thay thế.

| Kịch bản | Cách thử | Kết quả mong đợi |
|---|---|---|
| VM reboot | Reboot một member theo quy trình | Data volume và identity được khôi phục đúng |
| VM replacement | Tạo VM mới từ image, attach volume theo runbook | Instance ID mới, logical role đúng, credential mới |
| Container restart | Restart container trong Pod | Persistent data giữ nguyên, process recover đúng |
| StatefulSet Pod replacement | Xóa một Pod có kiểm soát | Pod ordinal/DNS/PVC đúng, cluster rejoin an toàn |
| Certificate rotation | Cấp certificate mới và thu hồi cũ | Peer trust chuyển tiếp không gián đoạn |
| Identity revocation | Thu hồi principal/certificate của member thử nghiệm | Member bị chặn, không thể tiếp tục truy cập |
| Node/zone failure | Làm một node hoặc zone không khả dụng trong staging | Quorum và availability theo thiết kế |
| Split-brain simulation | Cô lập network của member cũ | Fencing ngăn member cũ ghi |
| Volume recovery | Restore snapshot vào môi trường cô lập | Integrity check và application recovery thành công |
| Scale-in | Remove member theo protocol | Quorum, replication và data placement vẫn đúng |
| Rolling upgrade | Nâng từng member | Version/schema compatibility được giữ |
| Restore from backup | Khôi phục cluster vào môi trường mới | Dữ liệu, identity và endpoint được tái tạo có kiểm soát |

Chỉ thử fault injection trong môi trường và phạm vi được phép. Với production, dùng change window, người giám sát, điều kiện dừng và kế hoạch rollback.

## 25. Checklist triển khai ứng dụng stateful và machine identity

### State và storage

- [ ] Đã kiểm kê state, source of truth và retention.
- [ ] Dữ liệu quan trọng nằm trên storage có vòng đời phù hợp.
- [ ] Ephemeral disk chỉ chứa dữ liệu có thể tái tạo.
- [ ] Persistent volume có attachment/topology semantics rõ.
- [ ] Backup, snapshot, replication và restore test đáp ứng RPO/RTO.
- [ ] Có kiểm tra consistency sau recovery.

### Machine/workload identity

- [ ] Đã phân biệt resource ID, logical identity, authentication identity và network identity.
- [ ] Không dùng IP hoặc hostname làm credential duy nhất.
- [ ] Image không chứa private key, unique machine ID hoặc secret.
- [ ] Workload dùng managed identity/service account/certificate phù hợp.
- [ ] Quyền theo least privilege và tách theo workload role.
- [ ] Credential có expiry, rotation và revocation.
- [ ] Enrollment và identity issuance được audit.
- [ ] Clone/restore có quy trình regenerate identity phù hợp.

### Cluster và lifecycle

- [ ] Member ID, ordinal, membership và endpoint được xác định.
- [ ] Quorum, leader election và fencing được hiểu rõ.
- [ ] Volume chỉ có writer theo semantics storage/application.
- [ ] Scale-in có remove/rebalance member trước khi xóa compute.
- [ ] StatefulSet/PVC/headless Service có retention policy rõ.
- [ ] Rolling upgrade có schema/version compatibility.
- [ ] Failover/failback được diễn tập.

### Network, security và operations

- [ ] DNS/service discovery cung cấp endpoint ổn định.
- [ ] mTLS/TLS và certificate validation hoạt động.
- [ ] Network segmentation và firewall theo least privilege.
- [ ] Metadata endpoint và node access được bảo vệ.
- [ ] Metrics cho storage, replication, quorum, identity và certificate expiry.
- [ ] Log/audit được lưu ngoài instance.
- [ ] Có runbook thay máy, revoke identity, restore volume và rejoin cluster.

## 26. Tự kiểm tra

1. Stateful application khác stateful compute như thế nào?
2. Vì sao persistent volume không thay thế backup?
3. Phân biệt resource identity, logical identity, authentication identity và network identity.
4. Vì sao không nên dùng private IP làm machine identity?
5. Khi thay VM, những thành phần nào cần giữ ổn định và những credential nào nên được cấp mới?
6. Managed identity và per-instance certificate giải quyết các nhu cầu khác nhau nào?
7. StatefulSet cung cấp stable identity và storage association ra sao, và nó không tự giải quyết điều gì?
8. Vì sao stable DNS name không chứng minh member có quyền làm primary?
9. Quorum và fencing giúp ngăn lỗi nào khi network partition?
10. Vì sao không được attach cùng một block filesystem để ghi từ hai node nếu storage không hỗ trợ?
11. Khi scale-in một database cluster, cần thực hiện những bước nào trước khi xóa member?
12. Làm thế nào kiểm thử replacement để xác minh data, identity và membership được khôi phục đúng?

Triển khai stateful application an toàn cần đồng bộ ba vòng đời: compute có thể được thay thế, dữ liệu phải được bảo vệ theo yêu cầu nghiệp vụ, và danh tính phải xác định rõ ai đang truy cập hoặc tham gia cluster. Logical identity và endpoint có thể giữ ổn định để hệ thống tiếp tục nhận diện member; authentication credential nên được cấp và xoay vòng theo vòng đời tin cậy của compute. Khi kết hợp persistent storage, membership, quorum, fencing, workload identity, backup và kiểm thử replacement, ứng dụng có thể phục hồi có kiểm soát mà không phụ thuộc vào một VM hoặc container duy nhất.
