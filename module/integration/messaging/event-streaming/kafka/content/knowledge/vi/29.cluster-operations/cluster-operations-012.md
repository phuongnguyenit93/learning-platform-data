# Tự vận hành, operator và dịch vụ quản lý sẵn

Khi đưa Apache Kafka vào production, đội ngũ phải chọn cách triển khai và cách chịu trách nhiệm vận hành cluster. Có ba mô hình phổ biến:

- **Tự vận hành (self-managed):** đội ngũ tự provision máy/VM hoặc Kubernetes, cài Kafka, quản lý KRaft, storage, network, security, nâng cấp, mở rộng, giám sát và phục hồi.
- **Dùng Kubernetes operator:** đội ngũ khai báo trạng thái mong muốn bằng Custom Resource (CR); operator theo dõi và reconcile tài nguyên Kubernetes cùng các thành phần Kafka mà sản phẩm hỗ trợ.
- **Dịch vụ Kafka quản lý sẵn (managed service):** nhà cung cấp vận hành phần lớn hoặc toàn bộ hạ tầng broker và control plane; đội ngũ tập trung vào topic, client, dữ liệu, quyền truy cập và tích hợp ứng dụng.

Không có mô hình tốt nhất cho mọi tổ chức. Lựa chọn phụ thuộc vào năng lực SRE/Kafka, yêu cầu kiểm soát, môi trường triển khai, tuân thủ, độ sẵn sàng, chi phí và mức độ khác biệt giữa Kafka cần dùng với những gì nền tảng cung cấp.

Trong module KAFKA, người học cần hiểu topic, partition, offset, producer, consumer group, replication và KRaft để có thể đánh giá từng mô hình. Dù chọn cách nào, chất lượng vận hành cuối cùng vẫn phụ thuộc vào thiết kế partition, replication factor, min.insync.replicas, producer acks, consumer behavior, data contract, security và kế hoạch phục hồi.

## 1. Ba mô hình triển khai

### 1.1. Tự vận hành Kafka

Với self-managed, đội ngũ kiểm soát toàn bộ stack. Kafka có thể chạy trên bare metal, VM hoặc Kubernetes mà không có operator chuyên dụng.

Đội ngũ chịu trách nhiệm:
- Chọn phần cứng, CPU, RAM, disk và network.
- Cài đặt Kafka, cấu hình KRaft roles và metadata quorum.
- Provision broker, listener, advertised listener và storage.
- Cấu hình TLS, SASL, ACL, quotas và audit.
- Thiết kế replication, rack awareness và partition placement.
- Theo dõi broker, controller, ISR, request latency, disk, GC và consumer lag.
- Nâng cấp Kafka/JDK, rolling restart và thay đổi cấu hình.
- Mở rộng broker, reassignment partition và cân bằng tải.
- Backup cấu hình, replication sang cluster DR và kiểm thử failover.
- Xử lý incident, capacity planning và trực on-call.

Self-managed phù hợp khi tổ chức cần quyền kiểm soát sâu, có yêu cầu đặc biệt về phần cứng/network, muốn tùy chỉnh broker hoặc đã có đội ngũ vận hành Kafka đủ kinh nghiệm.

Chi phí hạ tầng có thể thấp hơn nếu tổ chức tận dụng được phần cứng và nhân lực hiện có. Tuy nhiên, phải tính chi phí kỹ sư, trực 24/7, nâng cấp, bảo mật, giám sát, DR, thay disk và thời gian xử lý incident.

### 1.2. Kubernetes operator

Kubernetes operator là một ứng dụng điều khiển cluster thông qua Kubernetes API. Operator thường đi kèm Custom Resource Definitions (CRDs) để người dùng mô tả Kafka cluster, node pool, topic, user hoặc connector theo dạng khai báo.

Một số ví dụ:
- **Strimzi:** operator mã nguồn mở cho Apache Kafka trên Kubernetes; cung cấp các tài nguyên quản lý Kafka, Kafka Connect, topic, user, MirrorMaker 2 và các thành phần liên quan tùy phiên bản.
- **Confluent for Kubernetes (CFK):** operator cho Confluent Platform, quản lý Kafka, KRaft controllers và các thành phần Confluent theo custom resources.

Operator không phải dịch vụ managed bên ngoài Kubernetes. Đội ngũ vẫn phải vận hành Kubernetes cluster, node, CNI, CSI, storage class, ingress/load balancer, secrets, RBAC, network policy và chính operator.

Operator giúp tự động hóa nhiều tác vụ Day-1 và Day-2:
- Khởi tạo Stateful workloads, Services, ConfigMaps, Secrets và PersistentVolumeClaims.
- Theo dõi trạng thái thực tế so với trạng thái khai báo.
- Thực hiện rolling update khi cấu hình hoặc image thay đổi.
- Tạo listener, certificate hoặc user/topic resource theo khả năng của operator.
- Quản lý node pool và hỗ trợ các thao tác scale theo quy trình của sản phẩm.
- Cung cấp status/conditions để người vận hành quan sát tiến trình reconcile.

Operator giảm thao tác thủ công và chuẩn hóa quy trình, nhưng không thay thế kiến thức Kafka. Một CR sai có thể gây restart hoặc thay đổi cluster ngoài dự kiến; operator cũng có thể bị lỗi, thiếu quyền, mất kết nối Kubernetes API hoặc không hỗ trợ một thao tác ở phiên bản đang dùng.

### 1.3. Dịch vụ Kafka quản lý sẵn

Managed service cung cấp cluster Kafka qua cloud provider hoặc nhà cung cấp streaming platform. Người dùng tạo cluster, chọn region/cluster type và cấu hình client access qua console, API hoặc IaC.

Ví dụ trên thị trường:
- **Amazon MSK:** dịch vụ managed cho Kafka, gồm các kiểu triển khai và tính năng phụ thuộc lựa chọn MSK Provisioned hoặc Serverless.
- **Confluent Cloud:** dịch vụ streaming managed với Kafka-compatible engine và các thành phần streaming đi kèm tùy gói/cluster type.
- Các nhà cung cấp managed Kafka khác có thể cung cấp mức kiểm soát, tính tương thích và SLA khác nhau.

Nhà cung cấp thường quản lý phần lớn công việc hạ tầng như provision broker, thay thế máy lỗi, vá hệ điều hành, vận hành control plane và một phần nâng cấp/khả năng mở rộng. Phạm vi cụ thể khác nhau theo sản phẩm, tier, region và hợp đồng.

Đội ngũ sử dụng vẫn chịu trách nhiệm:
- Thiết kế topic, partition, retention và replication policy trong phạm vi dịch vụ cho phép.
- Quản lý schema, data contract, producer/consumer và application retry.
- Cấp quyền client, xác thực và phân quyền theo mô hình của nhà cung cấp.
- Theo dõi consumer lag, throughput, quota, request errors và chi phí.
- Quản lý connector, stream processing và tích hợp downstream.
- Thiết kế DR, cross-region replication và kiểm thử ứng dụng khi failover.
- Hiểu giới hạn API, version compatibility, feature availability và SLA.

Managed service giảm phần việc vận hành broker, nhưng không loại bỏ trách nhiệm về dữ liệu, ứng dụng, security của client, quota và disaster recovery.

## 2. Operator hoạt động như thế nào?

Operator triển khai mô hình control loop. Người dùng khai báo desired state trong custom resource. Operator đọc desired state, quan sát actual state của Kubernetes/Kafka, tính phần khác biệt rồi thực hiện hành động để đưa hệ thống về trạng thái mong muốn.

~~~mermaid
flowchart TD
    U[Platform engineer cập nhật Kafka CR] --> API[Kubernetes API server]
    API --> STORE[CRD object: desired state]
    STORE --> OP[Kafka Operator]
    OP --> OBS[Đọc actual state: Pods, PVCs, Services, Kafka status]
    OBS --> DIFF[So sánh desired và actual state]
    DIFF --> ACT[Reconcile: create, update, restart, scale]
    ACT --> K8S[Kubernetes resources]
    K8S --> BROKERS[Kafka brokers và KRaft controllers]
    BROKERS --> STATUS[Cập nhật status / conditions]
    STATUS --> OP
    STATUS --> U
~~~

### 2.1. Desired state và actual state

Ví dụ người vận hành muốn cluster có ba broker, listener TLS, storage persistent và replication factor phù hợp. Họ cập nhật CR thay vì tự tạo từng StatefulSet, Service và Secret.

Operator đọc CR và tạo/cập nhật các resource tương ứng. Nếu một Pod bị xóa ngoài ý muốn, Kubernetes controller và operator có thể tạo lại workload theo cấu hình đã khai báo.

Cần phân biệt:
- **Desired state:** cấu hình trong CR, Helm values hoặc manifest.
- **Actual state:** Pod, PVC, Service, Kafka process và cluster state đang thực sự chạy.
- **Status/conditions:** trạng thái reconcile, lỗi hoặc điều kiện chưa đạt.

Lệnh kubectl apply thành công chỉ cho biết API server nhận manifest. Nó không chứng minh broker đã sẵn sàng, partition đã cân bằng hoặc producer/consumer đã hoạt động.

### 2.2. Reconciliation là vòng lặp liên tục

Operator thường reconcile khi:
- CR được tạo hoặc cập nhật.
- Resource được watch thay đổi.
- Có sự kiện restart hoặc lỗi.
- Đến chu kỳ reconcile định kỳ.
- Một thao tác trước đó chưa hoàn tất và cần tiếp tục.

Một thay đổi nhỏ trong CR có thể dẫn đến rolling restart nếu thay đổi đó tác động đến Pod template hoặc cấu hình cần restart. Hãy đọc tài liệu operator/version để biết trường nào có thể thay đổi động và trường nào yêu cầu restart.

Không chỉnh sửa trực tiếp tài nguyên do operator quản lý nếu không có hướng dẫn. Operator có thể ghi đè thay đổi thủ công ở vòng reconcile tiếp theo.

### 2.3. Operator không tự động hóa mọi thao tác Kafka

Operator có thể tạo broker và xử lý lifecycle Pod, nhưng một số thao tác vẫn cần quyết định của người vận hành:
- Chọn replication factor và min.insync.replicas.
- Quyết định khi nào thêm hoặc bỏ broker.
- Kiểm soát tốc độ partition reassignment.
- Đánh giá ISR và capacity trước rolling update.
- Thiết kế retention, compaction và quota.
- Đặt chính sách ACL, schema compatibility và data ownership.
- Lập kế hoạch DR và xác định RPO/RTO.
- Điều tra consumer lag hoặc application bug.

Một số operator tích hợp Cruise Control hoặc công cụ cân bằng partition, nhưng phải bật và cấu hình đúng. Không giả định mọi operator tự động di chuyển dữ liệu hoặc cân bằng partition chỉ vì số broker đã tăng.

## 3. So sánh trách nhiệm vận hành

Bảng dưới đây mô tả xu hướng chung. Phạm vi thực tế phải đối chiếu với operator hoặc managed service cụ thể.

| Công việc | Self-managed | Kubernetes operator | Managed service |
|---|---|---|---|
| Phần cứng/VM | Đội ngũ | Đội ngũ/Kubernetes platform | Nhà cung cấp |
| Kubernetes cluster | Nếu dùng K8s thì đội ngũ | Đội ngũ | Thường không lộ ra cho khách hàng |
| Cài Kafka broker | Đội ngũ | Operator hỗ trợ | Nhà cung cấp |
| KRaft controller lifecycle | Đội ngũ | Operator hỗ trợ theo phiên bản | Nhà cung cấp |
| OS patching | Đội ngũ | Đội ngũ quản lý node; operator quản lý workload | Nhà cung cấp |
| Kafka upgrade | Đội ngũ | Đội ngũ chọn phiên bản, operator thực hiện theo quy trình | Nhà cung cấp hoặc theo maintenance policy |
| Disk/PVC | Đội ngũ | Đội ngũ + CSI/operator | Nhà cung cấp |
| Topic/partition | Đội ngũ | Có thể khai báo qua Topic Operator/API | Người dùng qua API/console trong giới hạn dịch vụ |
| Client/schema | Đội ngũ | Đội ngũ | Đội ngũ |
| ACL/identity | Đội ngũ | Đội ngũ, operator có thể hỗ trợ user/cert | Người dùng theo IAM/ACL của dịch vụ |
| Monitoring broker | Đội ngũ | Đội ngũ; operator cung cấp status/metrics integration | Nhà cung cấp metrics + người dùng theo dõi workload |
| Consumer lag | Đội ngũ | Đội ngũ | Đội ngũ |
| Capacity planning | Đội ngũ | Đội ngũ | Chia sẻ với nhà cung cấp |
| Backup/DR | Đội ngũ | Đội ngũ | Chia sẻ; phụ thuộc dịch vụ |
| Incident application | Đội ngũ | Đội ngũ | Đội ngũ |
| Broker infrastructure incident | Đội ngũ | Đội ngũ và operator/Kubernetes | Nhà cung cấp |

### 3.1. Shared responsibility

Một lỗi thường gặp là nghĩ rằng managed service hoặc operator sẽ chịu trách nhiệm cho toàn bộ hệ thống event streaming.

Ví dụ:
- Provider có thể thay broker lỗi, nhưng consumer vẫn có thể xử lý chậm và lag tăng.
- Operator có thể tạo lại Pod, nhưng PVC có thể không mount được do CSI hoặc storage backend.
- Provider có thể bảo đảm SLA của control plane, nhưng ứng dụng vẫn có thể mất event do cấu hình producer/consumer sai.
- Operator có thể tạo KafkaUser, nhưng quyền ACL cấp ra có thể quá rộng nếu manifest được thiết kế sai.
- Managed service có thể có replication ở nhiều AZ, nhưng điều đó không tự động tạo DR ở region khác.

Cần có ma trận ownership và escalation path giữa application team, platform team, security, cloud provider và vendor support.

## 4. Khi nào nên chọn self-managed?

Self-managed thường phù hợp khi có một hoặc nhiều điều kiện:

- Cần kiểm soát sâu cấu hình broker, OS, storage, network hoặc rack placement.
- Có phần cứng/on-premises hoặc yêu cầu triển khai trong datacenter riêng.
- Có quy định dữ liệu hoặc network không cho phép dùng dịch vụ cloud bên ngoài.
- Workload lớn và ổn định, tổ chức có khả năng tối ưu chi phí hạ tầng.
- Đã có đội Kafka/SRE vận hành cluster, on-call và DR.
- Cần thử nghiệm hoặc tích hợp thành phần mà managed service chưa hỗ trợ.
- Muốn tự kiểm soát lịch nâng cấp, bảo trì và vòng đời broker.

Self-managed không phù hợp nếu cluster quan trọng nhưng không có người trực, không có quy trình nâng cấp, không theo dõi ISR/disk hoặc không kiểm thử phục hồi. Một cluster tự host có thể chạy tốt trong demo nhưng trở thành rủi ro vận hành khi tải và số team sử dụng tăng.

### 4.1. Những chi phí thường bị bỏ sót

Không chỉ tính VM và disk. Tổng chi phí còn gồm:
- Kỹ sư platform/SRE và thời gian on-call.
- Monitoring, logging, tracing và alerting.
- Backup, replication sang DR và storage dự phòng.
- Network load balancer, cross-AZ traffic và data transfer.
- Patch, vulnerability management và certificate rotation.
- Test nâng cấp, capacity test và chaos/failure test.
- Chi phí incident, downtime và cơ hội bị mất.

Nếu không tính các khoản này, self-managed có thể trông rẻ hơn nhiều so với thực tế.

## 5. Khi nào nên chọn Kubernetes operator?

Operator phù hợp khi tổ chức đã chuẩn hóa Kubernetes và muốn Kafka trở thành một platform service có thể quản lý bằng GitOps hoặc quy trình declarative.

Điều kiện nên có:
- Kubernetes platform production với node pool, CNI, CSI và RBAC ổn định.
- Persistent storage có performance và durability phù hợp cho Kafka.
- Đội ngũ hiểu StatefulSet, PodDisruptionBudget, scheduling và network policy.
- Có quy trình quản lý CRD/operator version.
- Có kiểm thử rolling update và storage recovery.
- Có người chịu trách nhiệm Kafka semantics bên cạnh Kubernetes platform.

### 5.1. Lợi ích

- Cấu hình cluster được version-control trong Git.
- Tái tạo môi trường dev/staging/prod có tính nhất quán.
- Tự động tạo resource Kubernetes và hỗ trợ lifecycle.
- Có thể quản lý topic/user theo manifest nếu operator hỗ trợ.
- Tích hợp sẵn với secret, certificate và RBAC của Kubernetes.
- Dễ chuẩn hóa quy trình provisioning và change review.

### 5.2. Rủi ro và giới hạn

- Kafka phụ thuộc chất lượng Kubernetes control plane, node và storage.
- Pod restart hoặc rescheduling không đồng nghĩa broker đã phục hồi dữ liệu và ISR.
- PVC và storage class có thể giới hạn khả năng di chuyển hoặc mở rộng.
- Operator/CRD upgrade có compatibility matrix riêng.
- CR sai hoặc rollout không kiểm soát có thể restart nhiều broker.
- Debug cần hiểu đồng thời Kafka, Kubernetes, CNI, CSI và operator.
- Một số thay đổi yêu cầu restart hoặc migration có thứ tự cụ thể.

### 5.3. Thiết kế Kubernetes cho Kafka

Các điểm cần kiểm tra:

**Node placement**
- Dùng anti-affinity hoặc topology spread để tránh đặt nhiều broker trên cùng node/rack khi mục tiêu là fault isolation.
- Tách broker và KRaft controller nếu topology và tải yêu cầu.
- Tránh để broker cùng replica set tập trung trên một availability zone.
- Đảm bảo node có CPU/RAM và network headroom.

**Storage**
- Dùng persistent volume có latency/throughput ổn định.
- Kiểm tra reclaim policy, volume expansion và snapshot behavior.
- Không dùng ephemeral container filesystem làm nơi lưu log production.
- Đánh giá IOPS, throughput, burst limit và network storage latency.
- Kiểm thử Pod reschedule và volume reattach.

**Disruption**
- Cấu hình PodDisruptionBudget phù hợp.
- Tránh drain đồng thời nhiều node có broker replica của cùng partition.
- Thực hiện bảo trì node theo từng bước và quan sát ISR.
- Đảm bảo rolling restart không làm mất quorum controller.

**Network**
- Kiểm tra advertised listeners có thể truy cập từ client ngoài cluster.
- Cấu hình load balancer/bootstrap và per-broker endpoint phù hợp.
- NetworkPolicy phải cho phép broker, controller, metrics, operator và client traffic cần thiết.
- Kiểm tra DNS, TLS SAN và đường đi cross-zone.

## 6. Khi nào nên chọn managed Kafka service?

Managed service phù hợp khi tổ chức muốn giảm trách nhiệm vận hành broker và tập trung nguồn lực vào ứng dụng, dữ liệu và sản phẩm.

Các trường hợp thường phù hợp:
- Đội ngũ nhỏ chưa có Kafka SRE/on-call.
- Muốn triển khai nhanh trên cloud.
- Workload cần khả năng tăng/giảm theo dịch vụ cung cấp.
- Muốn tích hợp IAM, VPC, monitoring và billing cloud.
- Không cần custom broker-level behavior ngoài phạm vi dịch vụ.
- Chấp nhận service limits, version support và maintenance policy của provider.

### 6.1. Lợi ích

- Không phải tự mua, cài và thay máy broker.
- Provider quản lý phần lớn việc patching và broker infrastructure.
- Có thể tích hợp private networking, IAM và monitoring cloud.
- Có mô hình pricing theo cluster, capacity hoặc throughput tùy dịch vụ.
- Có support/escalation path theo hợp đồng.
- Một số dịch vụ cung cấp Kafka Connect, Schema Registry, replication hoặc stream processing như thành phần tích hợp.

### 6.2. Giới hạn cần đánh giá

- Không phải mọi Kafka API, config hoặc feature đều được expose giống self-managed.
- Quota, partition count, message size, connection và throughput có thể có giới hạn.
- Một số thao tác broker-level không cho phép khách hàng thực hiện.
- Chi phí data transfer, cross-region và storage có thể tăng nhanh.
- Region, cloud provider và network topology có thể tạo lock-in.
- Maintenance, upgrade và scaling có thể theo lịch/quy trình provider.
- SLA của dịch vụ không thay thế SLA của ứng dụng hoặc data pipeline.

### 6.3. Đọc kỹ compatibility trước khi chọn

Không chỉ hỏi “dịch vụ có Kafka API không?”. Cần kiểm tra:
- Kafka protocol/API compatibility và version support.
- Producer/consumer client version được khuyến nghị.
- Transactions và idempotent producer.
- Compression codecs và message size limits.
- Consumer group behavior và offset management.
- ACL, IAM, OAuth/SASL và certificate requirements.
- Topic configs, retention, compaction và quotas.
- Kafka Connect connector availability.
- MirrorMaker 2, Cluster Linking hoặc cơ chế replication tương đương.
- Metrics, audit log, schema registry và governance.
- Export/egress path nếu cần chuyển dữ liệu sang nhà cung cấp khác.

Một ứng dụng chạy được với Kafka client không có nghĩa mọi tính năng vận hành Kafka đều có sẵn.

## 7. So sánh tổng thể

| Tiêu chí | Self-managed | Kubernetes operator | Managed service |
|---|---|---|---|
| Quyền kiểm soát broker | Cao nhất | Cao, trong phạm vi operator | Thấp hơn |
| Công sức vận hành broker | Rất cao | Trung bình đến cao | Thấp hơn |
| Phụ thuộc Kubernetes | Không bắt buộc | Bắt buộc | Thường không |
| Tự quản lý OS/hardware | Có | Có ở tầng Kubernetes/node | Provider |
| Tự quản lý Kafka upgrade | Có quyết định và thực thi | Có quyết định; operator hỗ trợ thực thi | Provider hoặc theo quy trình dịch vụ |
| Tự quản lý storage | Có | Có, gồm CSI/PVC | Provider |
| Customization broker | Rộng | Phụ thuộc CRD/operator | Theo giới hạn dịch vụ |
| Time-to-market | Chậm hơn nếu chưa có platform | Nhanh khi K8s đã chuẩn hóa | Thường nhanh |
| Chi phí trực tiếp | Hạ tầng và nhân lực | K8s + Kafka + nhân lực | Phí dịch vụ và data transfer |
| Lock-in | Thấp hơn nếu dùng Apache Kafka chuẩn | Có thêm dependency operator/CRD | Phụ thuộc API và dịch vụ |
| Phù hợp | Đội Kafka/SRE mạnh, cần kiểm soát | Nền tảng Kubernetes trưởng thành | Muốn giảm vận hành broker |

### 7.1. Cây quyết định đơn giản

~~~mermaid
flowchart TD
    A[Chọn mô hình Kafka] --> B{Có đội ngũ vận hành Kafka 24/7?}
    B -->|Không| C{Managed service đáp ứng compliance và feature?}
    C -->|Có| M[Managed Kafka]
    C -->|Không| D{Có Kubernetes platform production?}
    D -->|Có| O[Operator + platform SRE]
    D -->|Không| E[Đầu tư platform/SRE hoặc thiết kế lại yêu cầu]
    B -->|Có| F{Cần kiểm soát broker/OS/storage sâu?}
    F -->|Có| S[Self-managed]
    F -->|Không| G{Đã chuẩn hóa Kubernetes?}
    G -->|Có| O
    G -->|Không| M
~~~

Đây là bộ lọc ban đầu. Trước khi quyết định, cần kiểm tra workload, data residency, compatibility, DR, network, cost và support contract.

## 8. Quản lý vòng đời cluster

Dù triển khai theo mô hình nào, Kafka có các hoạt động lifecycle cần được quản lý theo quy trình.

### 8.1. Provisioning

Trước khi tạo cluster:
1. Ước lượng throughput ingress/egress và peak burst.
2. Tính partition count, replication factor và retention.
3. Xác định số broker, controller quorum và fault domains.
4. Chọn storage capacity, IOPS, throughput và growth headroom.
5. Thiết kế listener, TLS, SASL/IAM và ACL.
6. Xác định topic naming, ownership, quotas và data contract.
7. Thiết kế metrics, logs, alert và on-call.
8. Lập RPO/RTO và DR topology.
9. Xác định version Kafka, JDK/client compatibility.
10. Tạo môi trường staging có cấu hình gần production để kiểm thử.

### 8.2. KRaft và controller quorum

Trong KRaft, metadata cluster được quản lý bởi controller quorum. Khi chọn mô hình triển khai:
- Xác định controller roles và broker roles.
- Với cluster production, xem xét tách controller và broker nếu yêu cầu tải/availability phù hợp.
- Bảo đảm controller quorum có số node và failure-domain placement hợp lý.
- Theo dõi metadata quorum lag, leader và trạng thái controller.
- Bảo vệ metadata log directory và quy trình thay controller.
- Không coi việc khởi động lại broker là thao tác tương đương khởi động controller.

Operator có thể quản lý lifecycle controller theo version. Managed service có thể ẩn topology controller khỏi người dùng. Self-managed yêu cầu đội ngũ tự hiểu và vận hành quorum.

### 8.3. Upgrade Kafka

Upgrade cần kế hoạch cho broker, controller, protocol/metadata version, client và các thành phần tích hợp.

Checklist trước upgrade:
- Đọc upgrade guide của đúng Kafka release và operator/provider.
- Kiểm tra version hiện tại, version đích và upgrade path được hỗ trợ.
- Kiểm tra không có offline partition và under-replicated partition chưa xử lý.
- Xác minh ISR đủ an toàn cho rolling restart.
- Kiểm tra disk, CPU, memory và network headroom.
- Kiểm tra producer/consumer/Connect/Streams client compatibility.
- Xác nhận backup/DR và phương án rollback.
- Thực hiện staging upgrade trước production.
- Chọn maintenance window và thông báo owner.

Trong rolling upgrade:
1. Thực hiện theo thứ tự được tài liệu phiên bản yêu cầu.
2. Restart hoặc upgrade từng broker/controller theo batch được hỗ trợ.
3. Chờ node quay lại và replica bắt kịp.
4. Kiểm tra ISR, offline partition, request latency và consumer lag.
5. Dừng rollout nếu cluster mất quorum, ISR giảm hoặc latency vượt ngưỡng.
6. Chỉ tiếp tục khi health gate đạt.

Không gộp nhiều thay đổi lớn vào cùng một lần upgrade. Ví dụ, đổi Kafka version, thay storage class, thay TLS CA và scale broker cùng lúc sẽ làm khó xác định nguyên nhân nếu cluster không ổn định.

### 8.4. Operator upgrade và Kafka upgrade là hai lớp khác nhau

Với operator, cần phân biệt:
- Phiên bản operator/CRD.
- Phiên bản Kafka broker/controller.
- Phiên bản các thành phần như Connect, Schema Registry, MirrorMaker.
- Phiên bản Kubernetes, CNI và CSI.

Nâng operator có thể thay đổi CRD, reconciliation behavior, init container hoặc Pod template và dẫn đến rolling restart. Nâng Kafka component có upgrade path riêng. Phải đọc tài liệu compatibility matrix và thứ tự nâng cấp của từng sản phẩm.

### 8.5. Managed service maintenance

Với managed service, provider có thể chủ động quản lý maintenance và broker upgrade. Người dùng cần:
- Theo dõi thông báo maintenance và version lifecycle.
- Biết cluster có auto-upgrade hay cần chọn phiên bản.
- Kiểm tra client compatibility và deprecation.
- Hiểu maintenance window, failover và connection reset behavior.
- Kiểm thử retry/reconnect của client.
- Xác minh service SLA, support plan và escalation process.

Provider thực hiện thay đổi hạ tầng không có nghĩa ứng dụng không cần kiểm thử.

## 9. Mở rộng cluster và cân bằng dữ liệu

### 9.1. Scale up và scale out

- **Scale up:** tăng CPU, RAM hoặc storage của node/broker hiện có, nếu nền tảng cho phép.
- **Scale out:** thêm broker/node để tăng capacity hoặc phân tán tải.
- **Partition reassignment:** di chuyển replica/leader giữa broker để phân bố dữ liệu.
- **Topic partition expansion:** tăng số partition của topic, ảnh hưởng key mapping và ordering assumptions.

Thêm broker không tự động làm mọi partition được phân bố đều. Cần reassignment hoặc cơ chế cân bằng tương ứng. Tăng partition của topic cũng không tự động tăng throughput nếu consumer, key distribution hoặc downstream là bottleneck.

### 9.2. Scale bằng operator

Operator có thể hỗ trợ thêm/bớt node pool hoặc broker replica theo API của sản phẩm. Một số operator tích hợp Cruise Control để tạo proposal cân bằng partition.

Trước khi scale:
- Kiểm tra capacity mục tiêu và broker utilization.
- Kiểm tra replica placement và rack awareness.
- Xác định tốc độ di chuyển dữ liệu cho phép.
- Giới hạn reassignment để không gây network/disk saturation.
- Theo dõi ISR và leader movement.
- Xác minh volume/PVC đã được cấp phát đúng.
- Đánh giá khả năng rollback nếu scale operation bị gián đoạn.

Khi scale down, phải di chuyển replica ra khỏi broker trước khi xóa node. Xóa Pod hoặc PVC trực tiếp không thay thế quy trình decommission broker.

### 9.3. Scale trên managed service

Managed service có thể cho phép tăng broker count, capacity units, storage hoặc throughput tier. Cách scale phụ thuộc loại cluster và provider.

Người dùng cần xác minh:
- Thay đổi có rolling restart hay connection reset không.
- Có tự động partition reassignment không.
- Khi nào capacity mới có hiệu lực.
- Có quota giới hạn số broker/partition không.
- Chi phí tăng theo broker, storage, throughput hay data transfer.
- Scale down có làm giảm redundancy hoặc gây rebalance không.

## 10. Storage, durability và phục hồi

### 10.1. Persistent storage là một phần của thiết kế

Kafka ghi log lên disk và sử dụng OS page cache. Khi self-managed hoặc chạy trên Kubernetes:
- Dùng storage ổn định với latency/throughput phù hợp.
- Theo dõi disk usage, disk latency, queue depth và filesystem health.
- Đảm bảo disk capacity có headroom cho retention, compaction và reassignment.
- Lập kế hoạch thay disk và khôi phục broker.
- Tránh để log data dùng chung volume với workload I/O không kiểm soát.
- Kiểm thử mount/reattach và recovery khi node mất.

Với operator, PVC có lifecycle riêng. Cần biết khi xóa Kafka CR thì PVC có bị giữ hay xóa, reclaim policy ra sao, và operator có hỗ trợ resize storage hay không. Không giả định thay đổi size trong manifest luôn làm volume mở rộng được; phụ thuộc storage class, CSI và operator.

### 10.2. Replication không phải backup

Kafka replication bảo vệ dữ liệu khi broker lỗi trong cùng cluster theo replication factor và ISR policy. Nó không bảo vệ trước mọi tình huống:
- Người dùng xóa topic nhầm.
- Ứng dụng ghi dữ liệu sai.
- Retention xóa dữ liệu theo policy.
- ACL/config sai trên toàn cluster.
- Mất cả region hoặc cloud account.
- Corruption logic được replicate sang replica khác.

Cần có chiến lược backup/restore hoặc replication sang cluster khác. Với streaming platform, DR thường dùng MirrorMaker 2, Cluster Linking hoặc dịch vụ replication tương đương, tùy compatibility và vendor.

### 10.3. DR phải bao gồm cả metadata và hệ sinh thái

Một kế hoạch DR chỉ copy record là chưa đủ. Cần tính:
- Topic và partition configuration.
- ACL, users, service identities và quotas.
- Schema Registry subjects và compatibility policy.
- Kafka Connect connector config và offsets.
- Kafka Streams application state/changelog và reset/rebuild plan.
- Consumer group offsets nếu quy trình failover cần tiếp tục từ vị trí phù hợp.
- Secrets, certificates và network/DNS endpoints.
- Runbook chuyển producer/consumer sang cluster đích.
- Quy trình quay lại cluster chính sau khi phục hồi.

Cần xác định rõ RPO, RTO, data loss window và cách tránh split-brain ở tầng ứng dụng khi chuyển vùng.

### 10.4. Kiểm thử DR

Một DR plan chỉ có giá trị khi được diễn tập:
1. Chọn một kịch bản mất broker, mất AZ hoặc mất region.
2. Đo thời gian phát hiện và quyết định failover.
3. Kiểm tra replication lag trước thời điểm failover.
4. Chuyển producer/consumer và xác minh auth/ACL.
5. Đối chiếu số record, key ordering và consumer offsets.
6. Kiểm tra Connect/Streams và schema dependencies.
7. Đo RPO/RTO thực tế.
8. Ghi lại bước thủ công và tự động hóa phần lặp lại.
9. Diễn tập failback riêng.

## 11. Security và governance theo mô hình triển khai

### 11.1. Self-managed

Đội ngũ chịu trách nhiệm:
- TLS certificate issuance/rotation.
- SASL mechanism và credential provisioning.
- ACL authorizer và principal mapping.
- Broker listener/network exposure.
- Secret storage và file permission.
- Audit log, vulnerability patching và access review.

### 11.2. Kubernetes operator

Ngoài Kafka security, phải bảo vệ Kubernetes control plane:
- RBAC cho ai có quyền sửa Kafka CR.
- Namespace isolation và network policy.
- Secret encryption at rest và secret access.
- Operator service account và least privilege.
- Admission policy cho image, resource limit và security context.
- Quy trình thay đổi CR qua Git review.
- Certificate rotation và kiểm tra operator có restart workload hay không.

Một người có quyền sửa Kafka CR có thể gián tiếp thay đổi broker image, listener, storage hoặc ACL. Vì vậy, quyền Kubernetes API có thể là quyền quản trị Kafka trên thực tế.

### 11.3. Managed service

Kiểm tra:
- IAM/RBAC và API key ownership.
- Private endpoint/VPC peering/PrivateLink tương ứng.
- TLS và SASL/IAM authentication.
- ACL và cluster-level roles.
- Audit logs và access history.
- Data residency và encryption at rest.
- Key management và certificate rotation.
- Vendor support access và compliance scope.

Managed service giảm trách nhiệm patch OS/broker, nhưng người dùng vẫn phải bảo vệ client credentials, application secrets, schema và quyền topic.

## 12. Monitoring và incident response

Dù mô hình nào, dashboard Kafka cần theo dõi tối thiểu:

| Nhóm | Tín hiệu |
|---|---|
| Broker availability | Broker up/down, request errors, network connections |
| KRaft | Controller leader, quorum health, metadata lag |
| Replication | Under-replicated partitions, offline partitions, ISR shrink/expand |
| Storage | Disk usage, disk latency, disk errors, log directory failures |
| JVM | Heap, GC pause, CPU, thread count |
| Requests | Produce/Fetch latency, request queue, handler idle |
| Consumer | Consumer lag, rebalance, commit failures |
| Capacity | Bytes in/out, messages/sec, partition count, connection count |
| Security | Authentication failure, authorization denied, certificate expiry |
| Platform | Pod restarts, PVC mount, node pressure, operator reconcile errors |

Operator status và provider health dashboard là một phần của monitoring. Chúng không thay thế Kafka-level metrics và application metrics.

### 12.1. Runbook khi operator reconcile thất bại

1. Đọc status/conditions của CR.
2. Kiểm tra operator Pod, log và quyền RBAC.
3. Kiểm tra CRD version, schema validation và event của Kubernetes.
4. Kiểm tra Pod status, init container, image pull và readiness probe.
5. Kiểm tra PVC/PV, storage class, attach/mount và capacity.
6. Kiểm tra DNS, Services, listener và certificate.
7. Đối chiếu Kafka broker/controller logs.
8. Không xóa PVC hoặc force delete Pod trước khi hiểu trạng thái broker và dữ liệu.

### 12.2. Runbook khi managed service có sự cố

1. Kiểm tra provider service health và region status.
2. Kiểm tra metrics cluster và quota.
3. Kiểm tra client connection, DNS, TLS, auth và API errors.
4. Xác định ảnh hưởng theo topic, partition, producer và consumer group.
5. Kiểm tra consumer lag và retry storm.
6. Mở ticket theo support plan nếu có dấu hiệu provider-side.
7. Thực hiện failover theo DR plan nếu RTO yêu cầu.
8. Sau incident, đối chiếu dữ liệu và consumer offsets.

### 12.3. Runbook khi self-managed broker lỗi

1. Xác định broker/controller nào bị lỗi và thời điểm bắt đầu.
2. Kiểm tra KRaft quorum trước khi restart nhiều node.
3. Kiểm tra disk, filesystem, memory, GC, CPU và network.
4. Kiểm tra offline/under-replicated partitions và ISR.
5. Kiểm tra log directory và broker logs.
6. Phục hồi từng node theo runbook.
7. Chờ replica catch-up trước khi tiếp tục thay đổi.
8. Ghi nhận nguyên nhân gốc và cập nhật capacity/alert.

## 13. Chi phí và tổng chi phí sở hữu (TCO)

Không so sánh chỉ bằng giá VM với giá managed cluster. Cần đưa các thành phần vào cùng kỳ tính toán.

| Thành phần | Self-managed | Operator | Managed service |
|---|---|---|---|
| Compute/broker | VM hoặc bare metal | Node/Pod capacity | Phí cluster hoặc capacity |
| Storage | Disk, RAID, volume | PVC, CSI, storage backend | Storage theo pricing service |
| Network | Load balancer, cross-AZ | Kubernetes networking, LB | Data transfer, private connectivity |
| Platform | OS, monitoring, automation | Kubernetes control plane, CNI/CSI | Thường nằm trong dịch vụ |
| Engineering | Kafka SRE và on-call | Kafka + Kubernetes SRE | Platform/app integration |
| Support | Nội bộ hoặc vendor | Kubernetes và operator support | Service support plan |
| DR | Cluster phụ, replication | Cluster phụ và storage/network | Region phụ, replication add-on |
| Lock-in | Thấp hơn nếu dùng Apache Kafka chuẩn | CRD/operator dependency | Provider API, quotas và feature |

Cần đưa workload profile vào mô hình chi phí:
- Throughput trung bình và peak.
- Retention và storage growth.
- Egress/cross-region traffic.
- Số partition và connection.
- Compression và replication factor.
- Số môi trường dev/test/staging/prod.
- Mức SLA, RPO/RTO và support response time.

Managed service có thể có phí trực tiếp cao hơn nhưng giảm chi phí nhân lực/on-call. Self-managed có thể rẻ hơn ở quy mô lớn nếu có đội vận hành và hạ tầng phù hợp. Operator thường nằm giữa hai lựa chọn: tự quản lý platform nhưng tự động hóa một phần Kafka lifecycle.

## 14. Quy trình đánh giá trước khi quyết định

### 14.1. Thu thập yêu cầu

Ghi rõ:
- Workload throughput, peak và growth forecast.
- Message size, retention, partition count và replication.
- Producer/consumer concurrency và client libraries.
- Transactions, compaction, tiered storage hoặc feature đặc biệt.
- Security, data residency, audit và compliance.
- Availability, RPO/RTO và multi-region.
- Network location của producer/consumer.
- Skillset, on-call coverage và support expectations.
- Budget compute/storage/network/engineering.

### 14.2. Kiểm chứng bằng proof of concept

Chạy cùng một workload đại diện trên hai hoặc ba mô hình ứng viên:
- Provisioning và thời gian triển khai.
- Throughput và p95/p99 latency.
- Broker/client metrics và consumer lag.
- Rolling restart/upgrade behavior.
- Scale out và partition reassignment.
- Broker/node/AZ failure.
- TLS/SASL/ACL và credential rotation.
- DR/failover/failback.
- Billing và data transfer cost.
- Khả năng export dữ liệu/cấu hình khi rời nền tảng.

Không chỉ kiểm thử produce/consume happy path. Phải kiểm thử lỗi, maintenance và recovery.

### 14.3. Scorecard quyết định

Có thể chấm điểm 1–5, sau đó nhân trọng số theo ưu tiên tổ chức:

| Tiêu chí | Trọng số gợi ý | Câu hỏi |
|---|---:|---|
| Control/customization | 15% | Có cần broker-level config hoặc hardware control? |
| Operational capability | 20% | Đội ngũ có thể trực và phục hồi cluster không? |
| Reliability/DR | 20% | RPO/RTO có đạt qua failure test? |
| Compatibility | 15% | Feature/client/API có được hỗ trợ đầy đủ? |
| Security/compliance | 10% | Network, identity, residency và audit có đáp ứng? |
| TCO | 15% | Tổng chi phí 3 năm gồm nhân lực và data transfer là bao nhiêu? |
| Portability | 5% | Có thể chuyển cluster hoặc export dữ liệu không? |

Trọng số chỉ là ví dụ. Với hệ thống có dữ liệu nhạy cảm hoặc yêu cầu kiểm soát đặc biệt, security/compliance có thể là tiêu chí loại trừ thay vì điểm số.

## 15. Các anti-pattern thường gặp

- **Chọn self-managed vì giá VM thấp:** không tính on-call, upgrade, DR và engineering cost.
- **Chọn operator vì nghĩ không cần Kafka SRE:** operator vẫn cần người hiểu Kafka và Kubernetes.
- **Chọn managed service mà không test compatibility:** một số API/config/feature có thể không được hỗ trợ giống cluster tự host.
- **Cho rằng provider quản lý consumer lag:** provider quản lý hạ tầng, application team vẫn quản lý consumer behavior.
- **Xóa Pod/PVC để xử lý lỗi:** có thể làm gián đoạn hoặc mất dữ liệu nếu không hiểu lifecycle.
- **Sửa trực tiếp resource do operator quản lý:** reconcile có thể ghi đè thay đổi.
- **Upgrade operator và Kafka cùng lúc không theo hướng dẫn:** có thể tạo rolling restart ngoài dự kiến.
- **Scale broker nhưng không reassignment:** broker mới có thể nhàn rỗi trong khi broker cũ vẫn quá tải.
- **Coi replication là backup:** xóa nhầm hoặc dữ liệu sai có thể lan sang replica.
- **Không kiểm thử failover:** RPO/RTO trên giấy có thể khác xa thực tế.
- **Bỏ qua egress cost:** replication cross-region hoặc consumer ở cloud khác có thể làm hóa đơn tăng mạnh.
- **Không quản lý vendor lock-in:** phụ thuộc API, schema, IAM hoặc connector riêng khiến migration khó khăn.

## 16. Checklist production theo mô hình

### Self-managed
- [ ] Có owner và on-call cho broker, controller và storage.
- [ ] Có automation cho provisioning, config và upgrade.
- [ ] Có capacity plan và disk replacement runbook.
- [ ] Có monitoring ISR, KRaft quorum, request latency và consumer lag.
- [ ] Có TLS/SASL/ACL, secret rotation và audit.
- [ ] Có DR cluster, replication và failover test.
- [ ] Có version matrix cho Kafka, JDK và client.

### Kubernetes operator
- [ ] Kubernetes, CNI, CSI và storage class đã được kiểm thử cho stateful workload.
- [ ] Operator và CRD version nằm trong compatibility matrix.
- [ ] Có GitOps/review cho Kafka CR và RBAC chặt chẽ.
- [ ] Broker/controller placement qua fault domains.
- [ ] PVC retention/resize/recovery được hiểu rõ.
- [ ] Có quy trình rolling update và health gates.
- [ ] Có monitoring Kafka metrics cùng operator status.
- [ ] Có test khi operator hoặc Kubernetes control plane tạm thời unavailable.

### Managed service
- [ ] Feature/API compatibility được xác minh.
- [ ] Region, AZ, network path và data residency phù hợp.
- [ ] IAM/ACL, TLS và secret lifecycle được thiết kế.
- [ ] Quota, message size, partition và throughput limits đã được biết.
- [ ] Maintenance, upgrade và service SLA được hiểu.
- [ ] Metrics, audit log và support escalation được cấu hình.
- [ ] Egress, cross-region và storage cost đã được ước lượng.
- [ ] DR/failover/failback được diễn tập.

## 17. Kết luận

Self-managed mang lại quyền kiểm soát cao nhất nhưng đòi hỏi đội ngũ chịu trách nhiệm từ OS, storage và KRaft đến upgrade, security, monitoring và DR. Kubernetes operator biến nhiều thao tác lifecycle thành khai báo và reconciliation, nhưng tổ chức vẫn phải vận hành Kubernetes, storage, network và hiểu Kafka. Managed service giảm phần việc broker infrastructure, song ứng dụng vẫn phải quản lý topic, data contract, client, ACL, consumer lag, quota, cost và DR.

Hãy chọn mô hình theo năng lực vận hành, mức kiểm soát cần thiết, feature compatibility, compliance và tổng chi phí sở hữu. Dù chọn mô hình nào, hãy kiểm chứng bằng workload production-like, rolling maintenance, broker/AZ failure và DR exercise trước khi đưa dữ liệu quan trọng vào cluster.

## Tài liệu tham khảo

- Apache Kafka 4.4 — Operations: https://kafka.apache.org/44/operations/
- Apache Kafka 4.4 — KRaft: https://kafka.apache.org/44/operations/kraft/
- Strimzi 0.45.2 — Deploying and Managing: https://strimzi.io/docs/operators/0.45.2/deploying
- Confluent for Kubernetes — Upgrade overview: https://docs.confluent.io/operator/current/co-upgrade-overview.html
- Confluent Cloud — Create a Kafka cluster: https://docs.confluent.io/cloud/current/clusters/create-cluster.html
- Confluent Cloud — Overview: https://docs.confluent.io/cloud/current/overview.html
- Amazon MSK — How it works: https://docs.aws.amazon.com/msk/latest/developerguide/msk-cluster-management.html
