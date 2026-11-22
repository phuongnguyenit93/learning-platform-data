# Triển khai trên Kubernetes: định danh ổn định, lưu trữ và phân bố nút

## Mục tiêu bài học

Kafka là hệ thống stateful: mỗi broker quản lý partition replicas và ghi dữ liệu vào log trên disk; trong KRaft, các node còn lưu metadata log của cluster. Khi chạy trên Kubernetes, pod có thể bị reschedule hoặc thay thế, worker node có thể bảo trì, và storage có thể được provision ở một availability zone cụ thể. Nếu chỉ coi Kafka như một Deployment stateless, cluster có thể mất dữ liệu, thay đổi node identity ngoài ý muốn hoặc đặt nhiều replica trên cùng failure domain.

Bài học giải thích cách triển khai Kafka trên Kubernetes bằng Strimzi Operator ở chế độ KRaft. Trọng tâm là phân biệt Kafka node ID với pod ordinal, giữ persistent volume gắn đúng node, tổ chức broker/controller node pools, và phân bố pod cùng partition replicas qua Kubernetes nodes và availability zones.

Sau bài học, người học có thể:

- Giải thích vì sao Kafka cần định danh node ổn định và persistent storage.
- Phân biệt Kafka cluster ID, node ID, pod name, pool name, PVC và PV.
- Hiểu vai trò của KafkaNodePool trong Strimzi KRaft.
- Chọn persistent-claim, JBOD và StorageClass phù hợp.
- Bảo đảm PVC được giữ khi pod restart hoặc reschedule.
- Phân bố broker/controller pods qua node và availability zone.
- Kết hợp Kubernetes topology spread với Kafka rack awareness.
- Thiết kế controller quorum và broker pools có failure domain rõ ràng.
- Lập kế hoạch scale, thay broker, di chuyển storage và rolling update.
- Kiểm tra readiness, PVC binding, replica health và KRaft metadata trước/sau thay đổi.

## 1. Vì sao Kafka cần định danh và storage ổn định?

Một Kafka broker không chỉ là một process nhận request. Nó sở hữu các partition replicas, lưu log segments, tham gia replication và có một định danh node trong cluster. Trong KRaft, node còn có thể giữ vai trò controller và lưu metadata log.

Nếu pod bị xóa rồi tạo lại, Kubernetes có thể tạo pod mới trên worker node khác. Đây là hoạt động bình thường. Điều quan trọng là Kafka phải khởi động với đúng identity và dữ liệu của node đó, hoặc được thay thế theo một quy trình có kiểm soát.

~~~mermaid
flowchart TB
    K["Kafka cluster"] --> N1["Broker node 0"]
    K --> N2["Broker node 1"]
    K --> N3["Broker node 2"]
    N1 --> P1["Pod / broker-0"]
    N2 --> P2["Pod / broker-1"]
    N3 --> P3["Pod / broker-2"]
    P1 --> V1["PVC / PV 0"]
    P2 --> V2["PVC / PV 1"]
    P3 --> V3["PVC / PV 2"]
    V1 --> D1["Partition logs"]
    V2 --> D2["Partition logs"]
    V3 --> D3["Partition logs"]
~~~

Kubernetes quản lý vòng đời pod và volume attachment. Kafka quản lý node identity, partition leadership, replicas và metadata. Operator như Strimzi phối hợp hai lớp đó để triển khai và reconcile cluster.

### 1.1. Pod stateless và Kafka broker khác nhau

Với ứng dụng stateless, nếu pod bị xóa, pod mới có thể khởi động từ image và lấy trạng thái từ database hoặc service bên ngoài. Với Kafka broker, dữ liệu partition thường nằm trên volume cục bộ của broker. Nếu pod mới khởi động với volume trống mà vẫn được xem là broker cũ, cluster cần phục hồi replicas từ các broker còn lại; việc này tiêu thụ network, disk và thời gian.

Persistent volume giúp dữ liệu sống lâu hơn vòng đời của pod. Tuy nhiên, volume chỉ là một phần của identity: broker còn cần đúng cluster metadata, node ID, log directory và cấu hình tương thích.

### 1.2. Hai loại định danh cần phân biệt

| Định danh | Ý nghĩa | Vòng đời |
|---|---|---|
| Kafka cluster ID | Định danh logical Kafka cluster | Ổn định trong vòng đời cluster |
| Kafka node ID | Định danh một broker/controller node trong cluster | Phải ổn định khi node được restart với cùng identity |
| Pod name/ordinal | Định danh workload instance trong Kubernetes | Do operator/controller quản lý |
| Node pool name | Nhóm Kafka nodes có role và cấu hình chung | Có thể tồn tại lâu dài; đổi tên thường là migration |
| PVC name | Claim lưu trữ được gắn với node/volume | Phải được giữ khi cần giữ dữ liệu |
| PV identity | Persistent volume thực tế do storage system cấp | Tồn tại theo reclaim policy và lifecycle của storage |

Không mặc định pod ordinal luôn bằng Kafka node ID. Với Strimzi KafkaNodePool, node IDs được quản lý trên toàn cluster; chúng có thể không chạy liên tiếp trong một pool. Xem danh sách node IDs trong status của KafkaNodePool thay vì suy ra từ tên pod.

## 2. Kubernetes workload identity và Kafka node identity

### 2.1. StatefulSet trong Kubernetes

StatefulSet cung cấp danh tính ổn định cho pod qua ordinal, network identity và volume claim templates. Ví dụ các pod có tên:

~~~text
orders-kafka-0
orders-kafka-1
orders-kafka-2
~~~

Khi pod orders-kafka-1 được tạo lại, StatefulSet có thể tạo lại cùng ordinal và gắn lại PVC tương ứng nếu PVC/PV còn tồn tại và có thể attach trên node mới.

Headless Service cung cấp DNS ổn định cho các pod thuộc StatefulSet. PersistentVolumeClaim được tạo từ volumeClaimTemplates thường có tên gắn với StatefulSet và ordinal.

### 2.2. Strimzi quản lý Kafka pods bằng operator

Không nên tự tạo một StatefulSet song song để quản lý các broker mà Strimzi đang sở hữu. Trong các phiên bản Strimzi hiện hành, KafkaNodePool được quản lý bằng StrimziPodSet và Cluster Operator; operator tạo pod, service, secret, config map và PVC theo node pool.

Với Strimzi, tên pod và PVC có quy ước theo cluster, pool và pod/node index. Ví dụ:

~~~text
Pod: my-cluster-brokers-0
PVC: data-my-cluster-brokers-0
~~~

Tên thực tế phụ thuộc tên cluster, node pool và loại storage. Với JBOD, PVC còn chứa volume ID trong tên.

Điểm cần nhớ:

- StrimziPodSet/Cluster Operator là chủ sở hữu vòng đời pod Kafka.
- KafkaNodePool mô tả số node, roles, storage và pod template.
- Kafka resource mô tả cấu hình cluster và broker chung.
- PVC là tài nguyên lưu trữ gắn với Kafka node.
- Không sửa pod, PVC hoặc config do operator quản lý bằng tay nếu thao tác đó không nằm trong quy trình Strimzi hỗ trợ.

### 2.3. Node ID được Strimzi phân bổ

Node ID được gán tuần tự trên toàn Kafka cluster theo quy tắc operator. Khi cluster có nhiều node pools, node ID trong một pool không nhất thiết liên tiếp. Khi scale up/down, operator chọn node ID theo chính sách mặc định hoặc theo annotation quản lý ID được hỗ trợ ở phiên bản Strimzi đang chạy.

KafkaNodePool status có trường nodeIds để hiển thị các ID đang được pool sử dụng. Kiểm tra trường này trước khi:

- Thêm hoặc xóa broker.
- Chuyển node giữa các pools.
- Thay đổi role broker/controller.
- Di chuyển partition replicas.
- Cập nhật hệ thống monitoring hoặc automation có tham chiếu node ID.

Không tái sử dụng node ID cho một process có data directory của node khác. Không tự thay node.id trong file cấu hình do operator sinh.

### 2.4. KRaft cluster identity

KRaft dùng cluster ID và node ID để xác định node tham gia cluster. Mỗi node có metadata log; controller quorum sử dụng metadata log để đồng bộ cấu hình topic, partition, broker, replica và trạng thái cluster.

Khi một node restart với cùng PVC và identity, nó có thể tiếp tục từ metadata/data hiện có. Nếu volume bị mất và node được tạo lại với storage trống, operator/Kafka cần khởi tạo node theo quy trình được hỗ trợ và replicas phải được phục hồi từ cluster. Không tự chạy lệnh format storage hoặc thay cluster ID trên một cluster đang hoạt động.

## 3. KRaft node pools: broker và controller

Trong KRaft, mỗi node có một hoặc nhiều roles:

- Broker: nhận produce/fetch, lưu partition replicas và phục vụ client.
- Controller: tham gia quorum quản lý metadata cluster.
- Dual-role: cùng thực hiện broker và controller duties.

Strimzi sử dụng Kafka resource kết hợp KafkaNodePool resources để định nghĩa KRaft cluster. Node pool có tên, số replicas, roles, storage, resource requests/limits và pod scheduling template.

### 3.1. Tách controller và broker pools

Ở production, có thể tách controller-only pool và broker-only pool để cô lập tài nguyên control plane và data plane:

~~~mermaid
flowchart TB
    subgraph C["Controller pool"]
        C0["Controller 0"]
        C1["Controller 1"]
        C2["Controller 2"]
    end
    subgraph B["Broker pool"]
        B0["Broker 0"]
        B1["Broker 1"]
        B2["Broker 2"]
    end
    C0 <--> C1
    C1 <--> C2
    C2 <--> C0
    B0 <--> B1
    B1 <--> B2
    B2 <--> B0
    C0 -. "KRaft metadata quorum" .-> B0
    C1 -. "metadata replication" .-> B1
    C2 -. "metadata replication" .-> B2
~~~

Ba controller nodes thường được dùng để có quorum chịu được một node failure. Controller quorum cần số node phù hợp với cơ chế majority; hai controller không thể tiếp tục quorum nếu một node mất.

Broker pool có thể có nhiều nodes hơn controller pool vì lưu lượng data plane và dung lượng partition replicas thường tăng theo tải. Không cần scale controller cùng tỷ lệ với broker.

### 3.2. Controller quorum là thành phần nhạy cảm

Khả năng scale controller phụ thuộc Kafka version, quorum mode và operator version. Strimzi có các giới hạn riêng cho controller node pools; tài liệu phiên bản hiện hành có thể yêu cầu static quorum và không cho phép scale hoặc đổi role controller pool như broker-only pool.

Với Strimzi 1.3.0, tài liệu operator mô tả việc dùng static controller quorum cho các deployment KRaft; do đó controller node pools không thể scale theo cách broker-only pool được scale. Đây là giới hạn của operator/quorum mode ở phiên bản đó, không phải quy tắc chung cho mọi Kafka distribution hoặc mọi phiên bản tương lai.

Trước khi thay đổi controller replicas, role hoặc node pool:

- Xác định Kafka version và Strimzi version thực tế.
- Xác định controller quorum mode.
- Đọc giới hạn scale/migration của đúng phiên bản operator.
- Kiểm tra quorum health và controller membership.
- Không xóa đồng thời nhiều controller pods/PVCs.

Không áp dụng quy trình scale broker-only pool cho controller pool.

### 3.3. Ví dụ KafkaNodePool cho controller

Ví dụ dưới đây minh họa controller-only pool ba node, dùng persistent claim:

~~~yaml
apiVersion: kafka.strimzi.io/v1
kind: KafkaNodePool
metadata:
  name: controllers
  labels:
    strimzi.io/cluster: my-cluster
spec:
  replicas: 3
  roles:
    - controller
  storage:
    type: persistent-claim
    size: 20Gi
    class: fast-block
    deleteClaim: false
  resources:
    requests:
      cpu: "1"
      memory: 4Gi
    limits:
      cpu: "2"
      memory: 4Gi
~~~

Dung lượng 20Gi và tài nguyên CPU/memory chỉ là ví dụ. Hãy sizing controller metadata log theo số lượng topic/partition, tốc độ metadata changes, retention và khuyến nghị của phiên bản Kafka/operator.

### 3.4. Ví dụ KafkaNodePool cho broker

~~~yaml
apiVersion: kafka.strimzi.io/v1
kind: KafkaNodePool
metadata:
  name: brokers
  labels:
    strimzi.io/cluster: my-cluster
spec:
  replicas: 3
  roles:
    - broker
  storage:
    type: persistent-claim
    size: 1Ti
    class: fast-block
    deleteClaim: false
  resources:
    requests:
      cpu: "4"
      memory: 16Gi
    limits:
      cpu: "8"
      memory: 16Gi
~~~

Đây là cấu hình minh họa; số broker và dung lượng phải được tính từ partition count, replication factor, retention, message size, throughput, compaction và growth forecast. Không dùng 1Ti hoặc 4 CPU làm mặc định cho mọi cluster.

## 4. Persistent storage: PVC, PV và StorageClass

Kafka ghi dữ liệu vào log directories. Trên Kubernetes, persistent storage thường được yêu cầu qua PersistentVolumeClaim (PVC), sau đó PVC được bind với PersistentVolume (PV) do storage provisioner cung cấp.

~~~mermaid
flowchart LR
    K["KafkaNodePool storage"] --> C["PersistentVolumeClaim"]
    C --> S["StorageClass / provisioner"]
    S --> V["PersistentVolume"]
    V --> D["Broker log directory"]
    D --> R["Partition replicas"]
~~~

### 4.1. Ephemeral storage

Ephemeral storage thường dựa trên emptyDir. Dữ liệu sống cùng pod lifecycle hoặc node local lifecycle tùy loại volume. Khi pod bị thay thế, dữ liệu có thể mất.

Ephemeral storage phù hợp cho lab hoặc workload có thể rebuild hoàn toàn từ replicas khác. Nó không phù hợp cho production Kafka cần giữ dữ liệu cục bộ lâu dài, đặc biệt topic có replication factor 1.

### 4.2. Persistent claim

Persistent-claim tạo PVC cho mỗi Kafka node. Khi pod restart hoặc được reschedule, operator/Kubernetes có thể attach lại volume cũ để node tiếp tục dùng dữ liệu đã lưu.

Các điểm cần kiểm tra:

- StorageClass có provisioner và topology phù hợp.
- PVC đã Bound.
- PV có đủ capacity và access mode.
- Volume có thể attach ở node/zone nơi pod được schedule.
- Disk có IOPS/throughput phù hợp.
- Filesystem và block storage được operator hỗ trợ.
- Reclaim policy và deleteClaim có đúng ý định giữ/xóa dữ liệu.

Strimzi khuyến nghị block storage và chỉ kiểm thử chính thức với block storage theo tài liệu operator. Không mặc định mọi NFS/shared filesystem đều phù hợp với Kafka log directories.

### 4.3. JBOD

JBOD cho phép một broker sử dụng nhiều volume. Kafka có thể đặt log directories trên nhiều disk và phân bố partition replicas giữa các volume. JBOD hữu ích khi một volume không đủ capacity hoặc cần phân tách storage tiers.

Ví dụ:

~~~yaml
storage:
  type: jbod
  volumes:
    - id: 0
      type: persistent-claim
      size: 500Gi
      class: fast-block
    - id: 1
      type: persistent-claim
      size: 500Gi
      class: fast-block
~~~

Volume ID là định danh của disk trong JBOD. Không đổi ID volume đã sử dụng. Khi thêm lại một volume ID từng bị xóa, cần kiểm tra PVC cũ đã được xử lý theo quy trình operator trước khi sử dụng lại.

### 4.4. StorageClass và volume binding

StorageClass mô tả cách provision PV: loại disk, performance tier, encryption, topology và reclaim behavior tùy provisioner.

Với zonal storage, volume có thể chỉ attach được trong một availability zone. Cấu hình volumeBindingMode: WaitForFirstConsumer cho phép scheduler chọn node trước, rồi provisioner tạo volume phù hợp topology của node được chọn.

Ví dụ StorageClass minh họa:

~~~yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-block
provisioner: csi.example.com
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
reclaimPolicy: Retain
parameters:
  tier: premium-ssd
~~~

Tên provisioner và parameters là placeholder, phải thay bằng CSI driver thực tế. WaitForFirstConsumer không tự tạo rack awareness; nó chỉ phối hợp thời điểm provision volume với scheduling.

### 4.5. PVC retention và deleteClaim

Trong Strimzi PersistentClaimStorage, deleteClaim quyết định PVC có bị xóa khi Kafka node bị xóa hay không. Tài liệu API hiện hành nêu mặc định là false; đặt true có nghĩa operator có thể xóa PVC khi node bị xóa theo lifecycle tương ứng.

Đối với broker data:

- Giữ deleteClaim: false nếu muốn PVC tiếp tục tồn tại khi node/pod bị thay thế theo quy trình operator.
- Chỉ đặt true khi hiểu rõ lifecycle và chủ đích xóa claim.
- Kiểm tra reclaimPolicy của StorageClass/PV.
- Retain giữ PV sau khi claim bị xóa, nhưng không thay thế backup hoặc quy trình recovery.
- Delete có thể khiến storage backend xóa volume sau khi PVC/PV được giải phóng.

Không xem deleteClaim: false là backup. PVC/PV vẫn có thể hỏng, bị xóa thủ công hoặc mất cùng storage backend.

## 5. Lưu trữ KRaft metadata log

KRaft sử dụng metadata log nội bộ để lưu thay đổi cấu hình cluster. Mỗi node KRaft giữ bản sao metadata log theo vai trò và thiết kế cluster. Trong Strimzi, metadata log được lưu trên một volume của node; mặc định là volume có ID thấp nhất trong JBOD, trừ khi chỉ định volume bằng thuộc tính kraftMetadata.

### 5.1. Broker và controller-only node

Broker-only node có thể dùng cùng volume cho metadata log và partition replica data. Nếu dùng JBOD, một volume được chọn cho metadata log; các volume khác phục vụ partition data.

Controller-only node chỉ lưu metadata log. Vì metadata log nằm trên một volume, việc cấu hình JBOD nhiều volume cho controller-only node không làm tăng dung lượng metadata log hay tăng performance bằng cách chia metadata giữa nhiều disk.

### 5.2. Chọn volume cho metadata

Ví dụ chọn volume ID 1 cho KRaft metadata trong JBOD:

~~~yaml
storage:
  type: jbod
  volumes:
    - id: 0
      type: persistent-claim
      size: 500Gi
      class: fast-block
    - id: 1
      type: persistent-claim
      size: 100Gi
      class: fast-block
      kraftMetadata: shared
~~~

Chỉ một volume được đánh dấu kraftMetadata: shared. Thay đổi volume lưu metadata có thể yêu cầu rolling update và tạo lại metadata log ở vị trí mới theo quy trình operator. Không đổi thuộc tính này tùy tiện trên cluster đang hoạt động.

## 6. Bố trí pod qua node và availability zone

Kubernetes scheduler quyết định pod chạy trên worker node nào. Nếu không có quy tắc, nhiều Kafka pods có thể cùng nằm trên một worker node hoặc một availability zone. Khi node/zone đó gặp sự cố, nhiều broker hoặc controller có thể cùng mất.

Mục tiêu placement:

- Không đặt các broker replicas của cùng partition vào cùng failure domain.
- Không đặt đa số controller quorum vào một node hoặc zone.
- Tránh tranh chấp CPU, memory, disk và network với workload nặng khác.
- Đảm bảo pod có thể được schedule lại khi node bảo trì.
- Giữ volume topology tương thích với node được chọn.

### 6.1. Node affinity

Node affinity chọn worker node theo label. Có thể dùng label zone, loại disk, instance type hoặc node pool riêng.

Ví dụ node affinity chỉ chọn node có disk tier:

~~~yaml
template:
  pod:
    affinity:
      nodeAffinity:
        requiredDuringSchedulingIgnoredDuringExecution:
          nodeSelectorTerms:
            - matchExpressions:
                - key: storage-tier
                  operator: In
                  values:
                    - kafka-ssd
~~~

requiredDuringSchedulingIgnoredDuringExecution là điều kiện bắt buộc khi schedule. Nếu không có node phù hợp, pod ở trạng thái Pending. Với rule mềm, dùng preferredDuringSchedulingIgnoredDuringExecution và cân nhắc weight.

### 6.2. Pod anti-affinity

Pod anti-affinity giúp tránh đặt broker pods trên cùng Kubernetes worker node. Ví dụ:

~~~yaml
template:
  pod:
    affinity:
      podAntiAffinity:
        preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              topologyKey: kubernetes.io/hostname
              labelSelector:
                matchLabels:
                  strimzi.io/cluster: my-cluster
                  strimzi.io/broker-role: "true"
~~~

Rule preferred cố gắng tách broker nhưng vẫn cho phép scheduler đặt pod nếu cluster thiếu node. Nếu dùng required, mỗi broker cần worker node riêng phù hợp selector; thiếu node thì broker không schedule được.

Anti-affinity trên hostname chỉ tách pod theo worker node. Nó không bảo đảm các node nằm ở availability zone khác nhau.

### 6.3. Topology spread constraints

Topology spread constraints phân bố pod cân bằng qua các topology domains như hostname hoặc zone.

Ví dụ broker pods được spread qua zones:

~~~yaml
template:
  pod:
    topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: topology.kubernetes.io/zone
        whenUnsatisfiable: DoNotSchedule
        labelSelector:
          matchLabels:
            strimzi.io/cluster: my-cluster
            strimzi.io/broker-role: "true"
~~~

maxSkew: 1 yêu cầu số pod giữa các zone thỏa điều kiện lệch tối đa theo quy tắc scheduler. DoNotSchedule ưu tiên bảo đảm phân bố nhưng có thể để pod Pending nếu zone không còn capacity. ScheduleAnyway cho phép pod chạy khi không thể đạt phân bố lý tưởng, đổi lại mức bảo vệ yếu hơn.

Hãy kiểm tra label selector khớp đúng pod của pool cần spread. Nếu selector bao gồm controller và broker cùng lúc, scheduler có thể phân bố tổng pods thay vì phân bố từng role riêng.

### 6.4. Dedicated worker nodes

Kafka broker có thể cần disk/network/CPU ổn định. Có thể dành worker nodes riêng cho Kafka bằng taints và tolerations kết hợp node affinity:

~~~bash
kubectl taint nodes worker-kafka-1 dedicated=kafka:NoSchedule
kubectl label nodes worker-kafka-1 workload=kafka
~~~

Pod cần toleration để được schedule lên node đã taint và node affinity để chọn đúng label. Taint không tự di chuyển pods đang chạy; cần rollout/scheduling phù hợp.

Dedicated nodes giúp giảm noisy-neighbor nhưng làm giảm tính linh hoạt khi capacity thiếu. Cần có node dự phòng để pod có thể reschedule khi worker hỏng.

## 7. Kafka rack awareness và Kubernetes topology

Kubernetes placement và Kafka rack awareness là hai lớp khác nhau:

- Kubernetes topology spread/affinity quyết định pod chạy trên worker node/zone nào.
- Kafka rack awareness giúp broker nhận biết rack/zone của mình để Kafka phân bố partition replicas qua các rack khác nhau.

Chỉ cấu hình một trong hai chưa đủ để bảo đảm fault tolerance theo zone.

### 7.1. Cấu hình rack awareness bằng node label

Strimzi có thể đọc topology label của Kubernetes worker node và cấu hình broker.rack cho mỗi broker:

~~~yaml
spec:
  kafka:
    rack:
      type: topology-label
      topologyKey: topology.kubernetes.io/zone
~~~

Khi broker.rack được cấu hình, Kafka cố gắng phân bố partition replicas qua nhiều rack khác nhau nhất có thể. Với topologyKey là zone, rack tương ứng với availability zone của worker node.

Rack awareness không tự đặt pods lên các zone khác nhau. Cần kết hợp topologySpreadConstraints hoặc affinity để bảo đảm broker pods thực sự được schedule qua các zone.

### 7.2. Ví dụ ba zone

Giả sử cluster có ba availability zones:

~~~text
zone-a: broker-0, controller-0
zone-b: broker-1, controller-1
zone-c: broker-2, controller-2
~~~

Với topic replication factor 3 và rack awareness, Kafka có thể phân bố ba replicas của partition qua ba zone khác nhau nếu số broker/rack và assignment capacity cho phép.

Không có bảo đảm mọi partition luôn có đúng một replica mỗi zone nếu:

- Có ít hơn ba rack/zone khả dụng.
- Một zone thiếu broker hoặc broker không đủ capacity.
- Replication factor lớn hơn số rack khả dụng.
- Replica assignment cũ chưa được cân bằng lại sau thay đổi topology.
- Broker.rack không phản ánh đúng failure domain thực tế.

Sau khi thay đổi placement/rack config, kiểm tra partition assignments và dùng công cụ reassignment phù hợp nếu cần.

## 8. PodDisruptionBudget và rolling operations

PodDisruptionBudget (PDB) giới hạn số pod có thể bị voluntary disruption đồng thời qua các thao tác như drain node. PDB không ngăn được node failure, process crash hoặc mọi loại involuntary disruption.

Với Kafka:

- Controller quorum phải giữ được majority trong lúc bảo trì.
- Broker availability phụ thuộc replica placement, ISR và min.insync.replicas.
- PDB không thay thế replication factor hoặc rack awareness.
- Operator có thể quản lý PDB theo cách riêng; kiểm tra tài nguyên thực tế trước khi tạo PDB trùng hoặc xung đột.

### 8.1. Trước khi drain worker node

1. Kiểm tra broker/controller pods đang chạy trên node.
2. Kiểm tra KRaft quorum và controller health.
3. Kiểm tra partition leaders, ISR và under-replicated partitions.
4. Xác minh replicas của cùng partition không tập trung trên node/zone sắp drain.
5. Kiểm tra PDB và capacity trên các worker nodes còn lại.
6. Thực hiện drain từng node, không drain đồng thời nhiều failure domains.
7. Chờ pod reschedule, volume attach và Kafka node phục hồi.
8. Xác minh ISR/leader và controller quorum trở lại bình thường trước khi tiếp tục.

### 8.2. Rolling update

Operator có thể thực hiện rolling update khi cấu hình broker, image, certificate hoặc storage thay đổi. Trong rolling update:

- Một node được restart theo thứ tự và chính sách operator.
- Replica leaders có thể chuyển sang broker khác.
- Client có thể gặp retry/latency spike ngắn.
- Controller quorum phải tiếp tục có majority.
- Broker cần đủ replica/ISR để đáp ứng min.insync.replicas.

Không tự restart tất cả broker pods cùng lúc. Dùng operator reconciliation và quan sát trạng thái từng node.

## 9. Storage expansion và migration

### 9.1. Tăng dung lượng persistent volume

Nếu StorageClass/CSI driver hỗ trợ volume expansion, có thể tăng size của persistent-claim theo quy trình operator. Kubernetes không hỗ trợ giảm kích thước PVC thông thường.

Sau khi thay đổi storage size:

- Kiểm tra StorageClass có allowVolumeExpansion.
- Xác minh CSI driver và backend hỗ trợ resize.
- Theo dõi PVC conditions và PV capacity.
- Chờ filesystem expansion hoàn tất.
- Theo dõi operator rolling restart nếu phiên bản triển khai yêu cầu.
- Xác minh broker log directories nhận dung lượng mới.

Không chỉnh trực tiếp PV capacity hoặc xóa PVC để ép resize.

### 9.2. Đổi StorageClass

Trong Strimzi 1.3.0, storage property của KafkaNodePool là cấu hình không thể cập nhật trực tiếp. Để đổi StorageClass hoặc storage layout của broker-only pool, quy trình phổ biến là:

1. Tạo broker-only node pool mới với StorageClass mới.
2. Chờ pods và PVC mới Bound/Ready.
3. Xác minh broker mới tham gia cluster.
4. Dùng Cruise Control hoặc quy trình partition reassignment để di chuyển replicas khỏi broker cũ.
5. Chờ reassignment hoàn tất và ISR khỏe.
6. Xóa node pool cũ theo operator procedure.
7. Kiểm tra PVC/PV cũ và reclaim policy trước khi cleanup.

Đây là migration dữ liệu, không chỉ là thay YAML. Cần tính network bandwidth, disk capacity, throttling và thời gian catch-up.

### 9.3. Thêm hoặc bỏ JBOD volume

Khi thêm/bỏ volume:

- Giữ ổn định volume IDs đã dùng.
- Xác định partition replicas nằm trên volume nào.
- Dùng công cụ reassignment/intra-broker disk balancing phù hợp.
- Chỉ bỏ volume sau khi đã di chuyển hết dữ liệu cần thiết.
- Kiểm tra metadata volume nếu volume được chọn lưu KRaft metadata.

Không xóa PVC của volume còn chứa log segments cần thiết.

## 10. Scale broker và node pools

### 10.1. Scale up broker-only pool

Thêm broker không tự động làm partition replicas được phân bố lại tối ưu. Node mới có thể tham gia cluster nhưng ban đầu ít hoặc không có partition replicas.

Quy trình:

1. Tăng replicas của broker-only KafkaNodePool theo operator-supported workflow.
2. Chờ pod/PVC/volume sẵn sàng.
3. Kiểm tra node ID được cấp trong KafkaNodePool status.
4. Xác minh broker đăng ký trong cluster.
5. Lập kế hoạch reassignment partition replicas.
6. Giám sát network, disk I/O, replication lag và ISR.
7. Kiểm tra phân bố leader/replicas sau reassignment.

### 10.2. Scale down broker-only pool

Không chỉ giảm replicas và hy vọng operator tự di chuyển dữ liệu. Trước khi xóa broker:

- Chọn broker sẽ loại bỏ.
- Di chuyển partition replicas khỏi broker đó bằng Cruise Control hoặc reassignment plan.
- Chờ reassignment hoàn tất.
- Kiểm tra ISR và partition availability.
- Xác minh dependencies có tham chiếu node ID.
- Sau đó mới giảm node pool theo quy trình operator.

Node ID của broker chứa partition replicas có thể thay đổi khi thay broker hoặc reassignment. Cập nhật automation, monitoring và inventory phụ thuộc node ID.

### 10.3. Node IDs trong nhiều pools

Ví dụ cluster có controller pool và hai broker pools:

~~~text
controllers: node IDs [0, 1, 2]
brokers-a:   node IDs [3, 4, 5]
brokers-b:   node IDs [6, 7, 8]
~~~

Đây chỉ là ví dụ. Khi scale hoặc xóa node, ID có thể có gap và không liên tiếp trong từng pool. Không viết automation giả định node ID = pool ordinal hoặc ID luôn tăng theo đúng thứ tự pod.

Strimzi hỗ trợ annotation quản lý node ID trong một số thao tác nâng cao. Chỉ sử dụng khi đã xác minh đúng cú pháp và khả năng hỗ trợ của phiên bản operator; mặc định nên để operator quản lý.

## 11. Phục hồi pod, node và storage

### 11.1. Pod bị restart nhưng PVC còn

Đây là tình huống thường gặp:

1. Kubernetes tạo lại pod.
2. PVC cũ được attach vào worker node phù hợp.
3. Kafka process khởi động với node identity và log data hiện có.
4. Broker kiểm tra log/metadata và phục hồi trạng thái.
5. Replicas catch up và ISR được khôi phục.

Theo dõi thời gian volume attach, broker startup, log recovery và replica catch-up. Pod Running chưa chắc broker đã sẵn sàng phục vụ toàn bộ partition.

### 11.2. Worker node mất nhưng volume có thể attach lại

Với network block storage hỗ trợ multi-node failover theo policy, PVC có thể được attach sang worker node khác sau khi volume được detach khỏi node cũ. Thời gian failover phụ thuộc cloud/storage provider.

Không ép attach cùng một volume read-write vào hai broker process cùng lúc. Điều này có thể làm hỏng log data.

### 11.3. PVC hoặc PV không khả dụng

Kiểm tra:

- Pod events và PVC events.
- PV phase, reclaim policy và node/zone affinity.
- StorageClass/provisioner/CSI controller.
- Volume attachment object và trạng thái detach.
- Disk full, I/O errors và filesystem errors.
- Broker log về log directory failure.

Ưu tiên khôi phục volume cũ và dữ liệu gốc nếu có thể. Không xóa PVC để giải quyết lỗi mount trước khi hiểu tác động dữ liệu.

### 11.4. Broker mất storage hoàn toàn

Nếu không thể phục hồi storage:

1. Xác định partition replicas nào bị ảnh hưởng.
2. Xác minh các replicas còn lại có đủ dữ liệu và ISR.
3. Kiểm tra min.insync.replicas và availability của từng partition.
4. Dùng quy trình thay broker được operator hỗ trợ.
5. Khởi tạo node replacement với identity/storage đúng quy trình.
6. Reassign hoặc replicate partition data từ broker còn khỏe.
7. Theo dõi under-replicated partitions và disk/network load.

Nếu topic có replication factor 1 và broker mất volume, không có replica khác để phục hồi dữ liệu. Đây là lý do không dùng ephemeral storage cho dữ liệu cần durability và không dùng replication factor 1 cho production quan trọng.

### 11.5. Controller storage failure

Controller-only node lưu KRaft metadata log. Mất một controller có thể được quorum chịu đựng nếu vẫn còn majority khỏe. Mất majority khiến cluster không thể thực hiện các metadata operations bình thường và có thể ảnh hưởng hoạt động quản trị.

Không xóa đồng thời controller PVCs. Phục hồi từng node theo hướng dẫn Kafka/Strimzi đúng version, xác minh metadata log replication và quorum health trước khi tiếp tục.

## 12. Cấu hình tổng hợp: broker placement và rack awareness

Ví dụ dưới đây chỉ minh họa các phần quan trọng của Kafka custom resource và broker node pool. Listener, TLS, authentication, resource sizing và các cấu hình khác phải được bổ sung theo môi trường.

### 12.1. Kafka resource

~~~yaml
apiVersion: kafka.strimzi.io/v1
kind: Kafka
metadata:
  name: my-cluster
spec:
  kafka:
    rack:
      type: topology-label
      topologyKey: topology.kubernetes.io/zone
    config:
      default.replication.factor: 3
      min.insync.replicas: 2
  # Bổ sung listeners, authorization, logging và các phần cluster khác.
~~~

### 12.2. Broker node pool với zone spread

~~~yaml
apiVersion: kafka.strimzi.io/v1
kind: KafkaNodePool
metadata:
  name: brokers
  labels:
    strimzi.io/cluster: my-cluster
spec:
  replicas: 3
  roles:
    - broker
  storage:
    type: persistent-claim
    size: 1Ti
    class: fast-block
    deleteClaim: false
  template:
    pod:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              strimzi.io/cluster: my-cluster
              strimzi.io/broker-role: "true"
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                topologyKey: kubernetes.io/hostname
                labelSelector:
                  matchLabels:
                    strimzi.io/cluster: my-cluster
                    strimzi.io/broker-role: "true"
~~~

Các selector/labels cần được kiểm tra trên pod do operator tạo ra trong phiên bản đang dùng. Nếu labels thực tế khác, selector có thể không match và topology rule không có tác dụng.

### 12.3. Kiểm tra node pools và pods

~~~bash
kubectl get kafkanodepool
kubectl describe kafkanodepool brokers
kubectl get pods -o wide
kubectl get nodes -L topology.kubernetes.io/zone
kubectl get pvc
kubectl get pv
kubectl get storageclass
~~~

Đối chiếu:

- KafkaNodePool status: roles, replicas, nodeIds và conditions.
- Pod: node, zone, readiness, restart count và events.
- PVC: status Bound, capacity, storage class và volume.
- PV: claimRef, node affinity và reclaim policy.
- Broker: node ID, rack ID, listener và partition assignment.

## 13. Kiểm tra phân bố partition replicas

Kubernetes cho biết broker pod đang ở node/zone nào. Kafka cho biết partition replicas và leader đang ở broker nào. Cần kiểm tra cả hai lớp.

### 13.1. Liệt kê topic partition assignments

~~~bash
kafka-topics.sh \
  --bootstrap-server my-cluster-kafka-bootstrap:9092 \
  --describe \
  --topic orders
~~~

Kết quả có leader, replicas và ISR theo partition. Đối chiếu broker ID với rack/zone tương ứng.

### 13.2. Kiểm tra under-replicated partitions

Dùng metrics broker hoặc công cụ quản trị để theo dõi under-replicated partitions. Sau rolling update, node restart hoặc reassignment, chỉ tiếp tục thay đổi tiếp theo khi replica health trở lại mức mong đợi.

### 13.3. Rack-aware reassignment

Rack awareness ảnh hưởng cách Kafka chọn replica placement, nhưng partition replicas đã tồn tại có thể chưa được phân bố lại sau khi thay rack configuration. Dùng Cruise Control RackAwareGoal hoặc reassignment plan phù hợp để cân bằng lại.

Không chạy reassignment lớn đồng thời với rolling restart hoặc storage migration nếu chưa đánh giá network/disk capacity.

## 14. Readiness, liveness và graceful shutdown

Kubernetes probes kiểm tra process/container, còn Kafka health cần thêm trạng thái broker/controller và replication.

### 14.1. Readiness

Readiness nên phản ánh node đã khởi động và có thể phục vụ theo tiêu chí operator hỗ trợ. Không tự tạo probe chỉ kiểm tra TCP port rồi kết luận toàn cluster khỏe.

### 14.2. Liveness

Liveness dùng để phát hiện process bị treo. Nếu đặt timeout quá ngắn, GC pause hoặc I/O chậm có thể khiến Kubernetes restart broker không cần thiết, làm tăng recovery/rebalance.

### 14.3. Graceful shutdown

Khi drain node hoặc rollout:

- Cho broker thời gian shutdown đúng quy trình.
- Tránh kill -9 hoặc force delete pod khi không cần thiết.
- Theo dõi leader movement và ISR.
- Bảo đảm controller quorum vẫn có majority.
- Không xóa PVC như một phần của restart thông thường.

## 15. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách tránh |
|---|---|---|
| Dùng Deployment stateless cho broker mà không quản lý identity/storage | Pod replacement có thể mất log data | Dùng operator/stateful workload với persistent storage |
| Nhầm pod ordinal với node ID | Automation tham chiếu sai broker | Đọc KafkaNodePool status nodeIds |
| Dùng ephemeral storage cho production data | Mất local replica khi pod/node mất | Persistent block storage |
| Xóa PVC khi chỉ cần restart pod | Mất dữ liệu broker | Restart pod theo operator, giữ claim |
| Đặt mọi broker trong một zone | Một zone failure làm mất nhiều replicas | Topology spread và rack awareness |
| Chỉ cấu hình rack awareness | Pod vẫn có thể tập trung trên một zone | Kết hợp Kubernetes scheduling rules |
| Dùng required anti-affinity nhưng thiếu worker nodes | Pod Pending, không thể phục hồi | Sizing node capacity hoặc chọn preferred |
| Scale controller pool như broker pool | Có thể làm mất KRaft quorum | Tuân thủ giới hạn controller quorum |
| Scale down broker trước khi di chuyển replicas | Partition mất replica hoặc availability | Reassign trước, scale sau |
| Thay StorageClass trực tiếp trên node pool | Operator/API từ chối hoặc storage không được migrate | Tạo broker-only pool mới và di chuyển dữ liệu |
| Dùng JBOD nhưng xóa volume còn dữ liệu | Mất partition log segments | Reassign dữ liệu trước khi bỏ volume |
| Chỉ kiểm tra pod Running | Bỏ sót ISR/quorum unhealthy | Kiểm tra Kafka metadata và replication health |

## 16. Checklist trước khi đưa lên production

- Kafka chạy KRaft và KafkaNodePool roles được thiết kế rõ.
- Kafka cluster ID và node IDs được operator quản lý ổn định.
- Controller quorum có số node và placement phù hợp.
- Broker-only pool có capacity và khả năng scale riêng.
- Broker data dùng persistent block storage.
- StorageClass có topology, expansion và reclaim policy đã được kiểm tra.
- PVC deleteClaim được đặt theo chính sách giữ dữ liệu.
- KRaft metadata log có volume được chọn rõ nếu dùng JBOD.
- Broker pods được spread qua worker nodes và availability zones.
- Rack awareness sử dụng topology label đúng với failure domain.
- Replication factor và min.insync.replicas phù hợp số broker/zone.
- Pod anti-affinity không làm cluster thiếu khả năng reschedule.
- Taint/toleration/node affinity không khóa pod vào một node duy nhất.
- PDB và rolling update không làm mất controller majority hoặc ISR.
- Có quy trình drain node và storage recovery.
- Có quy trình broker replacement và partition reassignment.
- Có kiểm tra nodeIds, PVC/PV, rack ID, ISR và under-replicated partitions.
- Có backup/recovery plan cho metadata và dữ liệu nghiệp vụ quan trọng.

## 17. Bài tập thực hành

### Bài tập 1: Quan sát identity

1. Triển khai một Kafka KRaft cluster bằng Strimzi với hai KafkaNodePools.
2. Liệt kê KafkaNodePool và xem status nodeIds.
3. Liệt kê pod names và PVC names.
4. Đối chiếu node ID, pod name, pool name và PVC.
5. Giải thích vì sao không được giả định pod ordinal luôn là node ID.

### Bài tập 2: Kiểm tra persistence

1. Gửi record vào topic có replication factor 3.
2. Ghi nhận PVC/PV của một broker.
3. Restart pod broker theo cách operator hỗ trợ.
4. Xác minh PVC cũ được gắn lại.
5. Kiểm tra broker log recovery và ISR.

Không xóa PVC trong bài tập này.

### Bài tập 3: Phân bố qua zones

1. Chuẩn bị worker nodes có topology.kubernetes.io/zone.
2. Cấu hình topologySpreadConstraints cho broker pool.
3. Bật rack awareness theo zone label.
4. Xác minh broker pods nằm trên các zones khác nhau.
5. Kiểm tra partition replicas bằng kafka-topics --describe.
6. So sánh pod placement với replica placement.

### Bài tập 4: Drain một worker node

1. Xác minh controller quorum, ISR và PDB.
2. Chọn worker node đang chạy một broker.
3. Drain node theo kế hoạch lab.
4. Theo dõi pod reschedule và volume attach.
5. Xác minh broker phục hồi, ISR và partition leaders.
6. Giải thích vì sao PDB không bảo vệ khỏi mọi node failure.

### Bài tập 5: Di chuyển broker storage

1. Tạo broker-only node pool mới với StorageClass khác.
2. Chờ broker mới Ready.
3. Tạo KafkaRebalance remove-brokers hoặc reassignment plan tương ứng.
4. Theo dõi replica movement và network/disk load.
5. Xác minh broker cũ không còn replicas cần giữ.
6. Xóa node pool cũ theo operator workflow.

## 18. Câu hỏi tự kiểm tra

1. Vì sao Kafka broker cần identity ổn định?
2. Kafka cluster ID khác node ID như thế nào?
3. Vì sao pod ordinal không luôn bằng Kafka node ID?
4. StatefulSet cung cấp những thuộc tính identity nào?
5. Strimzi dùng thành phần nào để quản lý Kafka pods trong các phiên bản hiện hành?
6. KafkaNodePool mô tả những thuộc tính nào?
7. Vì sao KRaft controller quorum cần placement riêng?
8. Ephemeral storage khác persistent-claim ra sao?
9. PVC, PV và StorageClass có quan hệ thế nào?
10. deleteClaim ảnh hưởng lifecycle PVC như thế nào?
11. JBOD dùng volume IDs để làm gì?
12. KRaft metadata log được lưu trên volume nào?
13. Topology spread khác rack awareness như thế nào?
14. Vì sao anti-affinity required có thể khiến pod Pending?
15. Vì sao rack awareness không tự phân bố Kubernetes pods qua zones?
16. Vì sao phải reassign partition replicas trước khi scale down broker?
17. Điều gì có thể xảy ra nếu xóa PVC của broker?
18. PDB bảo vệ được những tình huống nào và không bảo vệ được tình huống nào?
19. Vì sao không scale controller pool như broker-only pool?
20. Những trạng thái nào cần xác minh trước và sau rolling update?

## Tài liệu tham khảo

- [Strimzi 1.3.0 – Deploying and Managing Kafka](https://strimzi.io/docs/operators/1.3.0/deploying)
- [Strimzi 1.3.0 – Configuring Kafka and KafkaNodePool](https://strimzi.io/docs/operators/1.3.0/configuring)
- [Strimzi – Rack awareness and pod scheduling](https://strimzi.io/docs/operators/latest/configuring.html)
- [Kubernetes – StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)
- [Kubernetes – Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [Kubernetes – Storage Classes](https://kubernetes.io/docs/concepts/storage/storage-classes/)
- [Kubernetes – Pod Topology Spread Constraints](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/)
- [Kubernetes – Assigning Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)

Triển khai Kafka trên Kubernetes cần giữ đúng cả Kafka identity lẫn storage identity. Persistent PVC giúp dữ liệu tồn tại qua vòng đời pod; node pools giúp quản lý broker/controller roles; topology spread quyết định pod nằm ở đâu; rack awareness giúp Kafka phân bố partition replicas theo failure domain. Khi bốn lớp này được thiết kế cùng nhau, cluster có thể chịu được restart, reschedule và bảo trì node với rủi ro dữ liệu được kiểm soát.
