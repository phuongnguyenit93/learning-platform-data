# Zonal clusters, regional clusters và thiết kế khả dụng

Một ứng dụng có thể chạy trên Kubernetes với ba Pod và vẫn ngừng phục vụ khi một zone của Google Cloud gặp sự cố: cả ba Pod có thể đã được scheduler đặt trên các node ở cùng zone. Ngược lại, một cluster có node trải rộng nhiều zone vẫn có thể không tạo, cập nhật hoặc lên lịch Pod mới nếu **control plane chỉ nằm ở zone vừa gặp sự cố**. Đây là lý do thiết kế tính khả dụng của Google Kubernetes Engine (**GKE**) phải xét **hai vấn đề riêng biệt**: vị trí của **control plane** và vị trí của **worker nodes/workloads**.

Trong chương **GKE cơ bản** của module **CLOUD_PROVIDERS_GCP**, bài học này phân tích sự khác nhau giữa **zonal clusters** và **regional clusters**, cách phân tán node/Pod giữa các zone, ảnh hưởng của mất một zone, khả dụng của dữ liệu và đường truy cập mạng. Các quyết định đó kết nối trực tiếp với kiến thức project, IAM, VPC, Compute Engine, Cloud Storage, database, tự động hóa phát hành, giám sát độ tin cậy và tối ưu chi phí trên Google Cloud.

**Sau bài học, bạn có thể:**

1. Giải thích cấu trúc control plane và node pools của GKE Standard zonal, GKE Standard regional và GKE Autopilot.
2. Phân biệt **cluster zonal** với **node pool một zone** và **cluster regional** với **node pool nhiều zone**.
3. Đánh giá tình huống lỗi của control plane, node, zone, region, load balancer, mạng và lưu trữ.
4. Chọn cấu hình đáp ứng mục tiêu **SLO, RTO, RPO** của dịch vụ thay vì chỉ chọn nhãn “regional”.
5. Dùng Deployment replicas, topology spread constraints, PodDisruptionBudget, probes và autoscaling để tăng khả dụng cho ứng dụng phù hợp.
6. Tạo và kiểm tra một cluster Standard regional trong môi trường lab, đối chiếu với cách tạo zonal và dọn tài nguyên an toàn.
7. Tính đến quota, chi phí node theo zone, lưu lượng liên zone, cơ chế bảo mật và khả năng phục hồi dữ liệu.

## 1. Hai lớp quan trọng: control plane và worker nodes

Một cluster GKE gồm những thành phần logic sau:

- **Control plane:** vận hành Kubernetes API, trạng thái và thành phần điều khiển cần thiết để theo dõi cluster, ra quyết định scheduling và điều phối desired state. GKE quản lý hạ tầng control plane.
- **Worker nodes:** các VM Compute Engine hoặc hạ tầng node được GKE quản lý, thực thi container trong Pod và kết nối mạng/lưu trữ theo cấu hình.
- **Node pool:** nhóm node có cấu hình liên quan (đối với Standard), ví dụ machine type, image, kích thước pool, vị trí zone, autoscaling.
- **Kubernetes workload:** Deployment, StatefulSet, DaemonSet, Job và các đối tượng tạo Pod trên các node đủ điều kiện.
- **Service và Ingress/Gateway:** tổ chức khám phá dịch vụ và phân phối traffic đến các endpoint sẵn sàng; tùy loại, GKE có thể tích hợp Google Cloud load balancing.

~~~mermaid
flowchart TB
    USERS["Người dùng"] --> LB["Load balancer / Gateway"]
    subgraph CP["Control plane do GKE quản lý"]
      API["Kubernetes API và controllers"]
    end
    subgraph NODES["Worker nodes trong node pools"]
      N1["Node zone A<br/>Pod API replica 1"]
      N2["Node zone B<br/>Pod API replica 2"]
      N3["Node zone C<br/>Pod API replica 3"]
    end
    API -. "Desired state / scheduling" .-> N1
    API -.-> N2
    API -.-> N3
    LB --> N1
    LB --> N2
    LB --> N3
~~~

Control plane không phải đường truyền dữ liệu HTTP bắt buộc giữa người dùng và một Pod đang chạy. Khi Kubernetes API tạm không sẵn sàng, **Pod hiện có trên các node còn sống có thể tiếp tục xử lý traffic**, nhưng những hoạt động như tạo/sửa tài nguyên, scheduling, xử lý node mới và điều phối phục hồi có thể bị ảnh hưởng. Khả năng ứng dụng tiếp tục phục vụ còn phụ thuộc sức khỏe node, load balancer, cấu hình ứng dụng và dữ liệu.

### 1.1. Phạm vi region và zone trong Google Cloud

- **Region**: khu vực địa lý chứa một hoặc nhiều zone; ví dụ `asia-southeast1`.
- **Zone**: miền lỗi riêng trong region, ví dụ `asia-southeast1-a`, `asia-southeast1-b` và `asia-southeast1-c`.
- **VPC network**: tài nguyên global; subnet của VPC lại có phạm vi **regional**, cho phép các VM/node trong những zone thuộc cùng region sử dụng subnet theo cấu hình.
- **GKE cluster location**: khi tạo Standard zonal, chọn một **zone** cho control plane; khi tạo regional, chọn một **region** cho control plane.

**VPC global không tự làm Pod, node hoặc dữ liệu thành multi-zone.** Một cluster vẫn có thể chỉ đặt node tại một zone. Việc truy cập qua private IP trong cùng VPC cũng không tự tạo quy trình phục hồi sau sự cố zone.

## 2. Zonal clusters, regional clusters và vị trí node

Hai trục lựa chọn cần luôn được ghi trong kiến trúc:

1. **Control plane ở đâu?** Một zone hay nhiều replica trên các zone của một region?
2. **Node pools chạy ở đâu?** Một zone hay nhiều zone trong cùng region?

Với **GKE Standard**, hai trục có thể kết hợp theo nhiều cách. Với **GKE Autopilot cluster**, control plane luôn là **regional** và GKE quản lý nhiều lựa chọn vị trí/tài nguyên node dựa trên cấu hình workload.

### 2.1. GKE Standard zonal cluster

**Zonal cluster** có **một control plane tại một zone**. Mặc định khi tạo zonal cluster, các node cũng ở một zone, nhưng người vận hành **có thể cấu hình node locations ở nhiều zone trong cùng region**. Cấu hình thứ hai thường được gọi là *multi-zonal zonal cluster*.

~~~mermaid
flowchart TB
    subgraph REGION["Region"]
      subgraph ZA["Zone A"]
        CPA["Control plane duy nhất"]
        NA["Node/Pod A"]
      end
      subgraph ZB["Zone B"]
        NB["Node/Pod B"]
      end
      subgraph ZC["Zone C"]
        NC["Node/Pod C"]
      end
    end
    CPA -. "Quản lý node khi control plane sẵn sàng" .-> NA
    CPA -.-> NB
    CPA -.-> NC
~~~

Nếu **zone A** (nơi đặt control plane) không sẵn sàng:

- Kubernetes API/control plane có thể không truy cập được; thay đổi cluster, lịch scheduling và một số cơ chế điều phối không hoạt động bình thường cho đến khi control plane phục hồi.
- Node và Pod đang chạy ở zone B/C **có thể tiếp tục phục vụ** khi các thành phần phụ thuộc còn hoạt động.
- Pod/VM/volume ở zone A bị ảnh hưởng theo phạm vi sự cố; số replica ở B/C quyết định năng lực phục vụ còn lại.

Nếu cluster zonal chỉ có node ở zone A, sự cố zone A có thể khiến **toàn bộ workload** mất khả dụng. Nếu node trải nhiều zone, đường phục vụ dữ liệu có thể còn, nhưng **control plane vẫn là điểm phụ thuộc tại một zone**.

Zonal cluster thường phù hợp **môi trường dev/test**, đào tạo hoặc workload có ngân sách và mục tiêu khả dụng cho phép. Đừng chọn zonal control plane cho production quan trọng chỉ vì đã tạo ba node ở một zone.

### 2.2. GKE Standard regional cluster

**Regional cluster** có nhiều replica của control plane ở nhiều zone trong **một region**, giúp Kubernetes API bền vững hơn khi một zone lỗi và trong những giai đoạn bảo trì/nâng cấp. Mặc định với Standard, node pool được phân bổ trên **ba zone** thuộc region (khi được hỗ trợ); có thể chọn ít zone hơn hoặc chỉ **một zone** cho node pool theo nhu cầu.

~~~mermaid
flowchart TB
    subgraph REGION["GKE Standard regional cluster"]
      subgraph A["Zone A"]
        CPA["Control plane replica A"]
        NA["Node + Pod A"]
      end
      subgraph B["Zone B"]
        CPB["Control plane replica B"]
        NB["Node + Pod B"]
      end
      subgraph C["Zone C"]
        CPC["Control plane replica C"]
        NC["Node + Pod C"]
      end
    end
    CPA <--> CPB
    CPB <--> CPC
    CPA <--> CPC
~~~

Với control plane được GKE quản lý theo cơ chế regional, mất một zone **thông thường không làm mất khả năng truy cập Kubernetes API**. Tuy vậy, ứng dụng chỉ chịu lỗi zone nếu **có node đủ năng lực và Pod sẵn sàng ở những zone còn lại**.

Một regional cluster với node pool **chỉ ở zone A** vẫn có control plane HA nhưng workload có thể ngừng hoàn toàn khi zone A lỗi. Do đó:

> **Regional control plane ≠ multi-zone workload ≠ multi-region application.**

Sau khi tạo cluster, **không thể đổi loại control plane từ zonal sang regional hoặc ngược lại** bằng một lệnh update thông thường. Muốn thay đổi loại này cần kế hoạch tạo cluster mới và migrate workload; trong khi đó, node locations của Standard cluster có thể được điều chỉnh theo khả năng hỗ trợ, và việc thay đổi có thể thêm/xóa node gây gián đoạn.

### 2.3. Bảng so sánh bốn tổ hợp Standard

| Control plane | Node locations | Chịu lỗi một zone của control plane? | Chịu lỗi một zone của workload? | Ứng dụng |
| --- | --- | --- | --- | --- |
| **Zonal** | Một zone | **Không** bảo đảm Kubernetes API tiếp tục phục vụ | **Không**, nếu mọi node ở zone lỗi | Lab/dev/test |
| **Zonal** | Nhiều zone | **Không**; API vẫn phụ thuộc một zone | **Có thể**, nếu Pod đủ replica trên những zone còn lại | Workload cần data plane trải zone nhưng chấp nhận điểm yếu control plane |
| **Regional** | Một zone | **Có khả năng** chịu lỗi một zone theo thiết kế control plane | **Không**, nếu zone duy nhất chứa node lỗi | Dev/test cần control plane HA nhưng tối ưu chi phí node |
| **Regional** | Nhiều zone | **Có khả năng** chịu lỗi một zone theo thiết kế control plane | **Có thể**, nếu scheduling, replica, storage, traffic được thiết kế đúng | Mặc định nên cân nhắc cho production quan trọng |

Từ “có thể” là cố ý. Một cluster node multi-zone nhưng ứng dụng chỉ có **một replica**, hoặc ba replica đều rơi vào zone A, **không** tự động bảo vệ dịch vụ khi zone A lỗi. Bảng nói về đặc tính hạ tầng, không phải SLA ứng dụng.

### 2.4. Autopilot và Standard khác gì trong lựa chọn khả dụng?

**GKE Autopilot clusters luôn regional**: control plane được nhân bản qua nhiều zone trong region. Google Cloud quản lý phần lớn cấu hình node, autoscaling, bảo mật và hoạt động cơ sở hạ tầng; người dùng khai báo Pod resources, scheduling requirements và chính sách workload.

**GKE Standard** cho phép chọn zonal hoặc regional, machine type, node pool location và nhiều cấu hình quản trị node hơn. Một số Standard clusters cũng có thể chạy **Autopilot workloads** theo tính năng và version hỗ trợ; điều đó không làm thay đổi loại control plane của cluster gốc.

| Chủ đề | Autopilot cluster | Standard cluster |
| --- | --- | --- |
| Control plane | Luôn regional | Chọn zonal hoặc regional khi tạo |
| Node management | Phần lớn do GKE quản lý | Người vận hành tạo/quản lý node pools và cấu hình nâng cao |
| Vị trí workload | GKE quản lý khả năng cấp node theo region và ràng buộc Pod | Tùy node locations, capacity, autoscaler và scheduling constraints |
| Tối ưu chi phí | Mô hình tính phí và tài nguyên theo cách Autopilot | Tính phí node/cluster và tài nguyên theo cấu hình Standard |
| Phù hợp | Muốn giảm công việc quản trị node và dùng cơ chế managed | Cần kiểm soát máy, zone, node pool và tùy chỉnh sâu |

Autopilot **không bảo đảm** ứng dụng có replica ở mọi zone nếu cấu hình Pod hoặc số replica không phù hợp. Vẫn cần kiểm tra Pod placement, requests, data persistence, readiness và load balancing.

## 3. Phân tích miền lỗi: node, zone, control plane và region

Không có kiến trúc nào “high availability” chỉ vì chứa nhiều thành phần. Hãy liệt kê **failure domain** và hậu quả với hệ thống thật.

### 3.1. Ma trận lỗi và kỳ vọng phục vụ

| Sự cố | Zonal control plane | Regional control plane | Điều kiện để ứng dụng còn phục vụ |
| --- | --- | --- | --- |
| Một Pod crash | Control plane thường vẫn quản lý cluster | Tương tự | Có replica khác, probes và khả năng khởi tạo lại Pod |
| Một node hỏng | Scheduler/controller cần hoạt động để bù replica | Tương tự | Các node khác có CPU/RAM/IP, storage và quota phù hợp |
| Zone **chứa control plane** bị lỗi | Kubernetes API có thể gián đoạn; dữ liệu ứng dụng ở zone khác vẫn có thể hoạt động | Control plane thường duy trì khả dụng qua các replica khác | Node/Pod ngoài zone lỗi, dịch vụ và dữ liệu đủ sống |
| Zone **chỉ chứa worker nodes** bị lỗi | API còn nếu control plane ở zone khác | API còn theo trạng thái cluster | Replica ngoài zone lỗi và traffic được chuyển đúng |
| Tất cả node thuộc một zone lỗi | Phụ thuộc control plane location | Control plane có thể còn, nhưng workload ngừng | Cần có node và Pod ở zone khác |
| Cả **region** gặp sự cố | Mất nhiều/tất cả thành phần region | Các replica control plane cũng ở **cùng region** | Cần cluster và dữ liệu dự phòng tại region khác |
| Dependency ngoài GKE bị lỗi | Không được cluster type tự giải quyết | Không được cluster type tự giải quyết | Database, DNS, load balancer, network, IAM và các backend có phương án riêng |

Đối với một **zonal cluster nhiều node ở các zone**, đừng nhầm “API không truy cập được” với “mọi container đã dừng”. Pod còn chạy có thể phục vụ dữ liệu; nhưng nếu một node nữa hỏng trong thời gian API gián đoạn, controller/scheduler không thể bù replica như bình thường.

Đối với **regional cluster**, cũng không suy rằng mạng, client và database chắc chắn hoạt động khi một zone lỗi. Tính khả dụng đầu-cuối cần bao gồm đường yêu cầu của người dùng và tất cả dependency có khả năng gây gián đoạn.

### 3.2. Khả dụng của Kubernetes API khác khả dụng của API ứng dụng

Giả sử một API bán hàng có ba replica, được cân bằng tải qua Service:

- Khi **Kubernetes API** tạm unavailable, replica ở node đang sống có thể tiếp tục nhận HTTP request.
- Khi **toàn bộ node chứa replica** unavailable, không có backend ứng dụng dù Kubernetes API vẫn hoạt động.
- Khi database đặt tại một zone bị lỗi, HTTP frontend vẫn có thể trả lỗi dù cả ba API replica còn chạy.
- Khi health check báo replica `NotReady`, Kubernetes hoặc hệ thống cân bằng tải có thể loại Pod khỏi endpoints; request có thể thất bại nếu không còn đủ replica khỏe.

Vì vậy, giám sát tách:

1. **Control plane/API availability:** có truy cập và thao tác quản trị cluster được không?
2. **Workload availability:** số replica `Ready`, endpoint, latency HTTP p95/p99, error rate.
3. **Data availability:** truy vấn database, độ trễ ghi/đọc, replica/backup và tính nhất quán.
4. **Network availability:** DNS, load balancing, firewall, VPC, egress và kết nối đến dependency.

### 3.3. SLO, RTO và RPO

| Khái niệm | Câu hỏi thiết kế | Ví dụ minh họa |
| --- | --- | --- |
| **SLO (Service Level Objective)** | Trong một kỳ đo, dịch vụ phải phục vụ đạt chất lượng nào? | 99,9% request thành công trong tháng, theo định nghĩa đo. |
| **RTO (Recovery Time Objective)** | Nếu xảy ra sự cố, cho phép mất bao lâu để khôi phục? | Phục vụ lại trong 30 phút. |
| **RPO (Recovery Point Objective)** | Chấp nhận mất bao nhiêu dữ liệu phát sinh trước sự cố? | Mất tối đa 5 phút dữ liệu. |
| **Error budget** | Trong kỳ SLO, mức suy giảm cho phép là bao nhiêu? | Dùng để cân nhắc tốc độ release và rủi ro vận hành. |

Ví dụ mục tiêu **99,9% availability** trong tháng 30 ngày tương đương khoảng **43,2 phút** downtime theo mô hình liên tục đơn giản. Đó là cách quy đổi toán học, **không phải SLA bảo đảm bởi việc tạo regional cluster**. Một ứng dụng có database một zone hoặc deploy lỗi vẫn có thể vượt error budget.

## 4. Đảm bảo Pod thực sự nằm trên nhiều zone

Control plane regional chỉ là lớp nền. Để nâng tính khả dụng của **stateless workload**, hãy kiểm soát số replica, vị trí Pod, sức khỏe ứng dụng, khả năng thêm node và chiến lược cập nhật.

### 4.1. Deployment replicas chưa nói lên phân tán zone

Một Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      containers:
        - name: app
          image: nginx:stable-alpine
          ports:
            - containerPort: 80
~~~

YAML trên yêu cầu ba Pod nhưng **không buộc mỗi Pod ở một zone**. Scheduler có thể đặt các Pod ở các node/zone đáp ứng điều kiện theo tài nguyên và trạng thái cluster. Không thể dùng riêng `replicas: 3` để chứng minh khả năng chịu lỗi một zone.

### 4.2. Topology spread constraints theo zone

Kubernetes cung cấp `topologySpreadConstraints` để hướng dẫn scheduler phân tán Pod theo nhãn topology. Mỗi GKE node thường có nhãn zone `topology.kubernetes.io/zone`.

Ví dụ một Deployment với **ba replica** và yêu cầu lệch số Pod giữa các zone đủ điều kiện không quá một:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-ha
  labels:
    app: catalog-ha
spec:
  replicas: 3
  revisionHistoryLimit: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: catalog-ha
  template:
    metadata:
      labels:
        app: catalog-ha
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: catalog-ha
      containers:
        - name: web
          image: nginx:stable-alpine
          ports:
            - containerPort: 80
          resources:
            requests:
              cpu: 100m
              memory: 64Mi
            limits:
              memory: 128Mi
          readinessProbe:
            httpGet:
              path: /
              port: 80
            initialDelaySeconds: 2
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /
              port: 80
            initialDelaySeconds: 10
            periodSeconds: 10
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: catalog-ha-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: catalog-ha
~~~

**Chỉ dùng mẫu này cho workload stateless** và điều chỉnh cho ứng dụng của bạn. `nginx:stable-alpine` phù hợp demo; production nên cố định image version/digest, cấu hình tài nguyên theo thử tải và giới hạn quyền container.

Ý nghĩa:

- `replicas: 3`: Kubernetes hướng tới ba replica.
- `topologyKey: topology.kubernetes.io/zone`: dùng zone làm miền phân tán.
- `maxSkew: 1`: chênh lệch số Pod được xét giữa các miền phù hợp theo cơ chế scheduler không vượt một.
- `whenUnsatisfiable: DoNotSchedule`: nếu không thể đáp ứng ràng buộc, Pod có thể **Pending** thay vì bị gom hết vào một zone.
- `readinessProbe`: chỉ để Pod nhận traffic khi kiểm tra sẵn sàng thành công.
- `livenessProbe`: khởi động lại container không khỏe theo điều kiện, **không thay thế startup probe** cho ứng dụng khởi động chậm.
- `maxUnavailable: 0`, `maxSurge: 1`: trong một rolling update có đủ tài nguyên, giữ các Pod mong muốn không bị giảm do chiến lược update thông thường; không bảo đảm chống zone failure.
- `PodDisruptionBudget minAvailable: 2`: hạn chế **voluntary evictions** qua cơ chế phù hợp, như `kubectl drain`; không ngăn được VM hỏng hoặc zone outage.

### 4.3. Điều kiện để topology spread thực sự hoạt động

1. Phải có **node đủ điều kiện tại nhiều zone**. Cluster regional với node chỉ ở zone A không thể tạo Pod vật lý ở zone B/C bằng YAML.
2. Nguồn CPU/RAM/IP và quota tại mỗi zone phải đủ. Hết capacity có thể làm Pod `Pending`.
3. Node selectors, affinity, taints/tolerations, GPU availability, PVC topology hoặc ràng buộc khác có thể giảm số zone khả dụng.
4. `topologySpreadConstraints` điều khiển scheduling theo các miền đủ điều kiện, **không bảo đảm đúng một Pod mỗi zone trong mọi trạng thái**. Để xác minh, phải xem thực tế Pod đang chạy trên node thuộc zone nào.
5. Khi mất một zone, số replica phục vụ còn lại có thể giảm. Autoscaler, quota và ràng buộc Pod quyết định khả năng bù replica ở zone còn sống.
6. Nếu ứng dụng yêu cầu tối thiểu hai/ba zone **bằng mọi giá**, cần thiết kế thêm điều kiện topology, số node, policy và alert; một spread rule cơ bản chưa bảo đảm mục tiêu ở mọi trạng thái cluster.

### 4.4. Pod anti-affinity và khác biệt so với spread

**Pod anti-affinity** có thể giúp ngăn các Pod giống nhau cùng nằm trên một node, thậm chí trên cùng zone theo nhãn topology. Tuy nhiên, quy tắc `requiredDuringSchedulingIgnoredDuringExecution` quá chặt có thể làm Pod không schedule được khi capacity thiếu.

Trong nhiều trường hợp, topology spread constraints diễn đạt mục tiêu “phân bố cân bằng” dễ hơn, còn pod anti-affinity phù hợp khi muốn **tránh đồng vị trí** rõ ràng giữa replica. Có thể kết hợp khi cần nhưng phải thử với tình huống thiếu node và rollout.

### 4.5. Replica, HPA, Cluster Autoscaler và PodDisruptionBudget không thay thế nhau

| Cơ chế | Kiểm soát điều gì? | Không tự giải quyết |
| --- | --- | --- |
| **Deployment replicas** | Số Pod mong muốn. | Vị trí zone, readiness, dữ liệu và quota. |
| **Topology spread / affinity** | Quy tắc scheduler chọn node/zone. | Tạo node khi không có capacity. |
| **Horizontal Pod Autoscaler (HPA)** | Điều chỉnh số Pod theo metric/điều kiện. | Tạo VM nếu thiếu node. |
| **Cluster Autoscaler / node auto-provisioning** | Thêm/bớt node hoặc pool theo khả năng/quy tắc GKE. | Luôn tìm được capacity trong zone, bảo đảm Pod trải đều tuyệt đối. |
| **PodDisruptionBudget** | Giới hạn một số tình huống eviction tự nguyện. | Sự cố node/zone không tự nguyện hoặc lỗi ứng dụng. |
| **Readiness/liveness/startup probes** | Xác định điều kiện phục vụ và khôi phục container. | Tự tạo replica ở zone khác hoặc cứu database. |
| **Rolling update / surge** | Cách cập nhật replica trong điều kiện có tài nguyên. | Bảo vệ khỏi mọi lỗi image hoặc cấu hình mới. |

Để chịu lỗi zone, cần **headroom**: khi một phần node mất, những zone còn lại có đủ năng lực phục vụ ít nhất mức tải thiết yếu hoặc có thể scale-up kịp theo RTO. Cluster Autoscaler cần thời gian cấp VM và có thể gặp quota/capacity; không nên coi nó là cơ chế phục hồi tức thời.

## 5. Stateful workload: nơi lưu dữ liệu cũng là failure domain

Một Deployment stateless có thể tái tạo Pod từ container image. Nhưng với workload dùng **PersistentVolumeClaim (PVC)**, việc khởi động Pod ở zone khác còn phụ thuộc volume có attach, mount và bảo toàn dữ liệu được không. Đặt database trong cluster regional **không tự biến dữ liệu từ zonal thành regional**.

### 5.1. Zonal Persistent Disk và Pod placement

Ví dụ một StatefulSet dùng PVC backed by **zonal Persistent Disk** được provision tại zone A. Khi Pod bị chuyển sang node ở zone B, volume zonal có thể **không attach được** vì giới hạn vị trí. Kubernetes scheduler sẽ xét topology của PV, nhưng sau zone outage không thể giả định volume ở zone A trở nên sẵn sàng tại zone B.

~~~mermaid
flowchart LR
    A["Zone A<br/>Stateful Pod + zonal disk"] -->|Zone A mất| X["Không thể gắn zonal disk<br/>tự động tại zone B"]
    B["Zone B<br/>Node còn sống"] -. "Cần volume/replica phù hợp" .-> C["Stateful Pod có thể phục hồi"]
~~~

Kiểm tra:

- StorageClass, CSI driver, `volumeBindingMode`, access mode và topology.
- Vị trí vật lý của persistent volume và node Pod được schedule.
- Cơ chế recovery khi node/zone gặp sự cố; không ép attach/mount trái quy tắc.
- Backup và các bước khôi phục nhất quán ứng dụng.

### 5.2. Regional Persistent Disk và những lựa chọn khác

**Regional Persistent Disk** nhân bản dữ liệu giữa hai zone trong một region theo khả năng sản phẩm. Với GKE và những cấu hình được hỗ trợ, nó giúp kiến trúc stateful tăng khả năng phục hồi khi một zone lỗi. Tuy nhiên:

- Vẫn cần cấu hình **StorageClass/CSI topology, quyền attach và failover** phù hợp.
- Một volume có dữ liệu không tự đảm bảo **database process** sẽ chạy lại hoặc chuyển vai trò an toàn.
- Cần xét khả năng RPO/RTO khi mất liên kết/replica hoặc volume ở trạng thái suy giảm.
- Nếu cả region lỗi, regional PD cũng không tự giải quyết khôi phục cross-region.

Với một số workload được hỗ trợ, Google Cloud có các khả năng như **Stateful HA Operator** và loại storage phù hợp để quản lý một phần cơ chế khôi phục; phải đọc điều kiện sản phẩm và thử thực tế trước khi dùng.

| Loại dữ liệu | Phương án nên đánh giá | Điều kiện chính |
| --- | --- | --- |
| API stateless | Không lưu trạng thái lâu dài trên filesystem Pod | Request có thể xử lý ở nhiều replica/zone. |
| Upload/video/tệp lớn | Cloud Storage với bucket location và chính sách phù hợp | App tránh giữ tệp duy nhất trên local disk node. |
| Database dùng managed service | Cloud SQL HA hoặc dịch vụ dữ liệu managed theo yêu cầu | Multi-zone HA, kết nối, backup và failover cần cấu hình/kiểm thử. |
| Database chạy trong Kubernetes | StatefulSet + phù hợp storage/replication/operator | Consistency, leader election, failover và backup do ứng dụng/công cụ quản lý. |
| Cache có thể tái tạo | Redis/cache theo mô hình cluster hoặc managed | Xác định cache miss khi zone lỗi có được chấp nhận không. |
| Shared filesystem | Filestore hoặc giải pháp file storage hỗ trợ | NFS và miền lỗi của dịch vụ lưu trữ khác với PD. |

### 5.3. Readiness và graceful shutdown khi rolling upgrade

Một Pod không nên nhận traffic ngay khi container đã khởi động nhưng database connection pool, config và cache chưa sẵn sàng. **Readiness probe** nên phản ánh điều kiện Pod có thể phục vụ; **startup probe** có thể bảo vệ ứng dụng khởi động lâu khỏi bị liveness kill quá sớm.

Trong rolling update, đặt `terminationGracePeriodSeconds` và xử lý `SIGTERM` để ứng dụng ngừng nhận yêu cầu mới, hoàn tất request đang chạy rồi thoát có kiểm soát. Với database writer, cần xét transaction và leader handoff.

**PDB giúp hạn chế những lần eviction tự nguyện nhưng không thay thế** readiness, graceful shutdown, backup hoặc replication.

## 6. Kết nối, load balancing và những dependency bên ngoài cluster

### 6.1. VPC/subnet regional trong cluster nhiều zone

GKE node chạy trên hạ tầng mạng Google Cloud. Với cluster **VPC-native**, Pod IP được quản lý qua các dải địa chỉ phụ của subnet theo cấu hình GKE. Vì subnet regional, các node nằm tại zone khác nhau của **cùng region** có thể dùng mạng/subnet phù hợp theo thiết kế cluster.

Tuy nhiên:

- Pod IP ranges phải đủ khi scale hoặc khi cluster cần bù node sau lỗi zone.
- Firewall rules, NetworkPolicy và những cơ chế Dataplane có thể ảnh hưởng giao tiếp Pod–Pod, Pod–service và Pod–database.
- Nút GPU/accelerator có thể chỉ sẵn ở một số zone; cấu hình node locations phải khớp vị trí phần cứng thực.
- **Control plane location** không đồng nghĩa mọi kết nối từ client đi qua zone điều khiển; traffic ứng dụng có đường riêng.

### 6.2. Kiểm tra đường đi của người dùng

Một ứng dụng HTTP nhiều zone có thể được truy cập qua External Application Load Balancer/GKE Gateway hoặc Ingress theo cấu hình. Thiết kế cần đảm bảo:

1. Load balancer nhận traffic và có cơ chế health check phù hợp.
2. Backend/NEG hoặc nhóm endpoint chứa **Pod đang Ready** tại các zone sẵn sàng.
3. Khi zone mất, endpoint lỗi được loại khỏi tuyến phục vụ sau khoảng hội tụ/health check.
4. Những zone còn lại đủ năng lực xử lý traffic chuyển sang.
5. HTTPS/certificate, Cloud Armor và truy cập bí mật không bị phụ thuộc một VM/proxy tự vận hành ở zone lỗi.

Không nên tự kết luận “GKE Service loại LoadBalancer” đủ cho mọi mô hình HTTP và DR. Cần lựa chọn đúng loại load balancer và scope dựa trên giao thức, ingress pattern, bảo mật và nhu cầu nhiều backend.

### 6.3. Sự phụ thuộc vào database

Ví dụ ba replica API đều ở các zone khác nhau nhưng kết nối **một Cloud SQL instance không có HA** tại zone A. Nếu database ngừng hoạt động theo sự cố zone, cả ba API có thể trả lỗi hoặc chỉ phục vụ các thao tác không phụ thuộc DB. Cluster regional không tự nâng khả dụng của Cloud SQL.

Với Cloud SQL, cần chọn khả năng **high availability/regional** phù hợp, thiết kế kết nối an toàn, retry với backoff, idempotent transaction và cơ chế backup/PITR theo sản phẩm. Nếu database replication có lag, phải tính RPO và kiểm tra ứng dụng chấp nhận độ trễ dữ liệu nào.

### 6.4. Phân biệt multi-zone và multi-region

**Regional cluster** có control plane được nhân bản **trong cùng một region**. Nếu toàn bộ region bị gián đoạn, bạn không có cluster regional thứ hai chỉ vì tên cluster là “regional”.

Muốn chịu lỗi **toàn region**, cân nhắc thiết kế **nhiều cluster ở nhiều region**, mỗi cluster và dữ liệu có khả năng phục vụ độc lập:

~~~mermaid
flowchart TB
    USER["Người dùng"] --> G["Global traffic routing / load balancing"]
    G --> CL1["Cluster A<br/>region 1, nhiều zone"]
    G --> CL2["Cluster B<br/>region 2, nhiều zone"]
    CL1 --> DATA1[("Dữ liệu vùng 1")]
    CL2 --> DATA2[("Dữ liệu vùng 2")]
    DATA1 <-.->|"Replication / backup có RPO"| DATA2
~~~

Kiến trúc multi-region còn cần xác định:

- **Traffic failover:** load balancer/Gateway/DNS, health check và thời gian hội tụ thực.
- **Dữ liệu:** đồng bộ/bất đồng bộ, xung đột ghi, leader, khôi phục, backup/PITR.
- **Triển khai:** cả hai cluster có image, manifest, IAM, secret và cấu hình nhất quán.
- **Bảo mật:** VPC, firewall, Workload Identity Federation for GKE, service accounts và quyền riêng từng môi trường.
- **Quota/capacity:** region dự phòng đủ tài nguyên trong lúc region chính không phục vụ.
- **Chi phí và residency:** lưu lượng cross-region, storage, logs, backup và giới hạn vị trí dữ liệu.
- **Diễn tập:** test failover/failback và đo RTO/RPO thực tế, không chỉ có sơ đồ kiến trúc.

Đây là bài toán **disaster recovery** rộng hơn việc chọn zonal hoặc regional cho một cluster.

## 7. Chi phí, quota, capacity và an toàn vận hành

### 7.1. Một flag có thể làm số node tăng gấp nhiều lần

Với một GKE Standard **regional cluster có node pool trải ba zone**, giá trị `--num-nodes` tại lúc tạo pool thường là **số node mỗi zone**, không phải tổng số node trong cả region.

Ví dụ:

| Node locations | `--num-nodes` | Tổng node ban đầu trong ví dụ |
| --- | ---: | ---: |
| Một zone | 1 | 1 |
| Hai zone | 2 | 4 |
| Ba zone | 1 | 3 |
| Ba zone | 3 | 9 |

Điều này giải thích vì sao regional Standard cluster với cấu hình mặc định có thể tạo **9 nodes (3 node/zone × 3 zones)** khi không thay đổi số node. Nếu chỉ cần lab, hãy **chủ động đặt số node** và kiểm tra tổng VM/quota/chi phí.

Với node pool **autoscaling**, cần phân biệt các giới hạn tính **theo zone** và tính **tổng node**, ví dụ các lựa chọn `--min-nodes`/`--max-nodes` so với `--total-min-nodes`/`--total-max-nodes` theo cấu hình được hỗ trợ. Đừng lấy 3 làm tổng autoscaler capacity khi thực tế bạn đã đặt 3 mỗi zone.

### 7.2. Các hạng mục chi phí

| Hạng mục | Điều cần đo hoặc dự toán |
| --- | --- |
| Cluster management | Phí quản lý GKE theo chế độ/cấu hình và chính sách free tier hiện hành. |
| Worker node | Compute Engine vCPU/RAM, boot disk, máy tăng thêm theo zone và thời gian hoạt động. |
| Lưu lượng | Pod/VM liên zone, egress Internet, cross-region nếu gọi dependency xa. |
| Load balancing | Quy tắc, khả năng xử lý request, backend, health check, IP theo bảng giá. |
| Lưu trữ | PVC/Persistent Disk, regional disk, snapshot/backup, dữ liệu giữa các zone. |
| Logging/Monitoring | Lượng log, metric, retention, alerting và các backend quan sát được bật. |
| Vận hành/DR | Cluster dự phòng, image registry, secret, CI/CD, quỹ capacity khi zone lỗi. |

**Không coi regional cluster luôn đắt gấp ba zonal cluster chỉ vì control plane có nhiều replica**: chi phí thực tế phụ thuộc số lượng node, cách quản lý cluster, dịch vụ mạng và dữ liệu. Ngược lại, node ở ba zone thường tạo chi phí cao hơn nếu tổng số node tăng và có traffic qua ranh giới zone.

### 7.3. Quota và khả năng cấp phát khi sự cố

Regional cluster sử dụng quota Compute Engine và tài nguyên khu vực theo cấu hình; cluster có node ở nhiều zone có thể cần nhiều địa chỉ IP public/in-use quota, vCPU, disk và IP trong subnet. GPU/TPU có thể không sẵn tại mọi zone.

Trước khi chọn thiết kế chịu lỗi zone, kiểm tra:

1. **Quota tổng và quota liên quan vùng/zone** đủ cho cả bình thường và khi phải bù node.
2. **Subnet primary/secondary IP ranges** đủ cho node/Pod mới.
3. **Node auto-provisioning và Cluster Autoscaler** có thể chọn được zone/machine series phù hợp.
4. **Image registry và mạng egress** vẫn truy cập được khi thêm node.
5. Các ứng dụng có **resource requests** gần đúng với tải thật để scheduler và autoscaler không ra quyết định sai.
6. Còn **dung lượng dự phòng** hoặc kế hoạch giảm tải có kiểm soát khi một zone không còn.

Với cluster regional Standard, GKE khuyến nghị sử dụng node pools nhiều zone để tăng tính khả dụng, nhưng autoscaler **không bảo đảm** node luôn phân bổ đều giữa các zone ở mọi thời điểm.

### 7.4. Nâng cấp và bảo trì

Control plane regional giúp duy trì Kubernetes API tốt hơn trong những đợt upgrade/resizing so với zonal, nhưng **node pool upgrade vẫn có thể gây gián đoạn Pod**. Để giới hạn rủi ro:

- Chọn release channel, maintenance window/exclusion theo quy trình tổ chức.
- Dùng **surge hoặc blue-green upgrades** của node pool theo khả năng sản phẩm.
- Đặt PodDisruptionBudget hợp lý, đủ replica và resource headroom.
- Kiểm tra workload readiness, graceful termination và dependency.
- Thực hiện canary, kiểm tra SLO và có kế hoạch rollback khi release ứng dụng gây lỗi.

Một PDB quá chặt kết hợp với số replica thấp có thể khiến hoạt động bảo trì khó thực hiện. Rủi ro cần được đánh giá trước, không giải quyết bằng cách vô hiệu hóa mọi cơ chế bảo vệ lúc update.

## 8. Thực hành: tạo Standard regional cluster với node ở ba zone

**Mục tiêu:** tạo một cluster Standard **regional** trong project thử nghiệm, mỗi zone ban đầu một node, triển khai ba Pod mẫu, kiểm tra vị trí thực tế và dọn tài nguyên. Phần lab tập trung **quan sát** chứ **không gây sự cố zone thật**.

> **Cảnh báo chi phí và quyền:** các lệnh trong mục này có thể tạo cluster, VM Compute Engine, disk, network và log **có tính phí**. Chỉ chạy trong project lab có Cloud Billing và ngân sách được phê duyệt. Không dùng project production hoặc chia sẻ cluster của nhóm khác. Việc đọc Markdown không tự chạy lệnh.

### 8.1. Chuẩn bị và xác định phạm vi

Cần:

- Project lab có quyền bật Kubernetes Engine/Compute Engine API, tạo VPC, subnet, service account, IAM binding và GKE cluster.
- `gcloud` và `kubectl` đã cài, đăng nhập đúng account; ví dụ chạy trong **Bash/Cloud Shell**.
- Region có tối thiểu ba zone phù hợp và machine type `e2-standard-2` sẵn trong các zone chọn.
- Quota vCPU, in-use IP, disk, secondary IP range và các yêu cầu mạng đủ cho **ba node cùng lúc**.
- Dải `10.90.0.0/20`, `10.91.0.0/16`, `10.92.0.0/20` chưa trùng với mạng khác trong VPC hoặc các kết nối hybrid/peering.
- Chính sách tổ chức cho phép cấu hình cluster/node network, node image pull, quyền kết nối control plane và Google Cloud APIs. Trong môi trường bắt buộc private nodes, cần thiết kế riêng egress/Cloud NAT hoặc các đường API được hỗ trợ.

Định nghĩa biến trong Bash:

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export REGION="asia-southeast1"
export ZONE_A="asia-southeast1-a"
export ZONE_B="asia-southeast1-b"
export ZONE_C="asia-southeast1-c"
export NETWORK="gke-ha-lab-vpc"
export SUBNET="gke-ha-lab-subnet"
export CLUSTER="gke-regional-ha-lab"
export NODE_SA="gke-ha-node-lab@$PROJECT_ID.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project

# Chỉ đọc: xác minh region/zone, machine type và quota liên quan
gcloud compute zones list --filter="region:$REGION"
gcloud compute machine-types describe e2-standard-2 --zone="$ZONE_A"
gcloud compute machine-types describe e2-standard-2 --zone="$ZONE_B"
gcloud compute machine-types describe e2-standard-2 --zone="$ZONE_C"
~~~

Nếu region/zone hoặc machine type không tồn tại, hãy chọn lại theo vị trí mà tổ chức cho phép, không đoán tên zone. Ba zone Singapore chỉ là **ví dụ**, không phải khuyến nghị về vị trí lưu trú dữ liệu cho mọi doanh nghiệp.

### 8.2. Bật API và tạo service account node tối thiểu

Chỉ người có quyền thực hiện trong project lab:

~~~bash
gcloud services enable \
  container.googleapis.com \
  compute.googleapis.com \
  iam.googleapis.com

# Node service account riêng, không sử dụng một tài khoản quản trị chung
gcloud iam service-accounts create gke-ha-node-lab \
  --display-name="GKE HA lab node"

# Vai trò tối thiểu phục vụ logging/monitoring system tasks của GKE node
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$NODE_SA" \
  --role="roles/container.defaultNodeServiceAccount"
~~~

`roles/container.defaultNodeServiceAccount` là role GKE khuyến nghị cho những tác vụ hệ thống cơ bản của node. Tùy nơi lưu image và yêu cầu workload, cần xem **quyền đọc Artifact Registry**, quota project, chính sách logging và quyền bổ sung *cụ thể*. Không gán Owner/Editor toàn project chỉ để tránh lỗi kéo image.

Node service account khác **Kubernetes ServiceAccount** của ứng dụng. Để Pod gọi Google Cloud APIs, ưu tiên **Workload Identity Federation for GKE** và cấp IAM theo workload, không mặc định trao quyền database hoặc Secret Manager cho toàn bộ node.

### 8.3. Tạo VPC custom và subnet theo region

Lab sử dụng một VPC riêng với primary IP range cho node và secondary ranges cho Pod/Service:

~~~bash
gcloud compute networks create "$NETWORK" \
  --subnet-mode=custom

gcloud compute networks subnets create "$SUBNET" \
  --network="$NETWORK" \
  --region="$REGION" \
  --range=10.90.0.0/20 \
  --secondary-range=gke-ha-pods=10.91.0.0/16,gke-ha-services=10.92.0.0/20

gcloud compute networks subnets describe "$SUBNET" \
  --region="$REGION" \
  --format="yaml(name,region,ipCidrRange,secondaryIpRanges)"
~~~

Subnet là tài nguyên **regional**: cùng subnet có thể phục vụ node ở ba zone thuộc region. Secondary ranges đã được cấp cho GKE dùng IP alias của Pod/Service. Không dùng dải có thể xung đột với on-premises hoặc mạng kết nối khác.

### 8.4. Tạo regional cluster với một node mỗi zone

~~~bash
gcloud container clusters create "$CLUSTER" \
  --region="$REGION" \
  --node-locations="$ZONE_A,$ZONE_B,$ZONE_C" \
  --num-nodes=1 \
  --machine-type=e2-standard-2 \
  --enable-ip-alias \
  --network="$NETWORK" \
  --subnetwork="$SUBNET" \
  --cluster-secondary-range-name=gke-ha-pods \
  --services-secondary-range-name=gke-ha-services \
  --release-channel=regular \
  --service-account="$NODE_SA"
~~~

Giải thích:

- `--region` chọn **regional control plane**; khác `--zone` của zonal cluster.
- `--node-locations` chỉ định ba zone có node, đều thuộc **cùng region**.
- `--num-nodes=1` nghĩa là **một node tại mỗi zone** trong cấu hình ban đầu này; tổng là **3 nodes**.
- `--enable-ip-alias` và secondary range names xác định mô hình IP VPC-native.
- `--service-account` gắn danh tính node được tạo riêng; không phải quyền để Pod ứng dụng tự động đọc mọi dịch vụ.
- `--release-channel=regular` chọn kênh phát hành; quản trị production còn cần maintenance window, bảo mật và quản lý phiên bản.

Lệnh tạo có thể cần nhiều quyền và thời gian; nếu thất bại, đọc chi tiết lỗi rồi xử lý **quota, network, IAM hoặc node capacity**. Không đổi sang zone/region khác hoặc nâng quyền lên Owner nếu chưa xác định nguyên nhân.

### 8.5. Xác minh control plane và node locations

~~~bash
gcloud container clusters describe "$CLUSTER" \
  --region="$REGION" \
  --format="yaml(name,location,locations,status,nodePools)"

gcloud container clusters get-credentials "$CLUSTER" \
  --region="$REGION" \
  --project="$PROJECT_ID"

# Gắn zone label vào kết quả đọc node
kubectl get nodes -L topology.kubernetes.io/zone

# Thông tin tổng quan cluster/node pools
kubectl cluster-info
kubectl get nodes -o wide
~~~

Với ba zone có capacity và việc tạo cluster thành công, bạn kỳ vọng thấy **3 nodes**, tương ứng các zone A/B/C. Kiểm tra cột label thực tế thay vì chỉ dựa trên tên VM. Nếu chỉ có hai node hoặc một node chưa Ready, cần đọc sự kiện, quota, trạng thái node pool và thời điểm tạo node.

`gcloud container clusters describe` cho biết cluster location ở **mức region**; `kubectl get nodes -L topology.kubernetes.io/zone` cho biết các node thực sự hiện diện ở những zone nào.

### 8.6. So sánh với câu lệnh tạo zonal cluster

**Không chạy lệnh dưới đây cùng lúc với lab regional** trừ khi bạn đã phê duyệt thêm tài nguyên và chi phí. Đây chỉ là **ví dụ đối chiếu** loại control plane:

~~~bash
# CHỈ MINH HỌA: zonal control plane tại zone A, node ở A/B/C
gcloud container clusters create gke-zonal-multizone-example \
  --zone="$ZONE_A" \
  --node-locations="$ZONE_A,$ZONE_B,$ZONE_C" \
  --num-nodes=1 \
  --machine-type=e2-standard-2 \
  --enable-ip-alias \
  --network="$NETWORK" \
  --subnetwork="$SUBNET" \
  --release-channel=regular \
  --service-account="$NODE_SA"
~~~

Khác biệt trọng tâm là **`--zone="$ZONE_A"`**: control plane chỉ ở zone A, mặc dù node có thể trải ba zone. Với môi trường dùng secondary ranges đã được regional cluster khác sử dụng, cần **dải riêng phù hợp** cho cluster khác; vì thế không sao chép trực tiếp ví dụ đối chiếu để tạo cluster thứ hai trong cùng subnet khi chưa thiết kế IP. Muốn chạy thật phải chuẩn bị thêm range, quota và cleanup riêng.

Nếu mục tiêu là **zonal cluster chỉ một zone**, bỏ `--node-locations` hoặc chỉ giữ zone A; khi đó cả control plane và node mặc định đều thuộc zone A.

### 8.7. Triển khai workload thử và PodDisruptionBudget

Trên shell đã kết nối `kubectl` với **đúng cluster lab**, thực hiện:

~~~bash
kubectl create namespace gke-ha-lab

kubectl apply -n gke-ha-lab -f - <<'YAML'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ha-demo
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ha-demo
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: ha-demo
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: ha-demo
      containers:
        - name: nginx
          image: nginx:stable-alpine
          ports:
            - containerPort: 80
          resources:
            requests:
              cpu: 100m
              memory: 64Mi
            limits:
              memory: 128Mi
          readinessProbe:
            httpGet:
              path: /
              port: 80
            initialDelaySeconds: 2
            periodSeconds: 5
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: ha-demo-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: ha-demo
YAML

kubectl rollout status deployment/ha-demo -n gke-ha-lab
kubectl get pods -n gke-ha-lab -l app=ha-demo -o wide
kubectl get pdb -n gke-ha-lab
~~~

Khi ba node tại ba zone đều đủ điều kiện và Pod đã Ready, bạn **kỳ vọng** mỗi Pod được đặt tại một zone. Nếu một Pod ở trạng thái `Pending`, dùng lệnh:

~~~bash
kubectl describe pod -n gke-ha-lab \
  "$(kubectl get pods -n gke-ha-lab -l app=ha-demo \
     -o jsonpath='{.items[0].metadata.name}')"

kubectl get events -n gke-ha-lab \
  --sort-by=.lastTimestamp
~~~

Đây là lệnh chẩn đoán một Pod mẫu, không được lấy một trường hợp duy nhất làm kết luận toàn bộ cluster. Để lập bằng chứng, đối chiếu từng Pod trong kết quả `-o wide` với node và nhãn zone từ `kubectl get nodes -L topology.kubernetes.io/zone`.

### 8.8. Thử rolling update an toàn trong lab

Thay vì gây sự cố zone thật, thử một thao tác **tự nguyện** và quan sát khả năng duy trì replica:

~~~bash
# Chỉ thực hiện trong namespace / cluster thử nghiệm
kubectl rollout restart deployment/ha-demo -n gke-ha-lab
kubectl rollout status deployment/ha-demo -n gke-ha-lab

kubectl get pods -n gke-ha-lab -l app=ha-demo -o wide
kubectl get pdb -n gke-ha-lab
~~~

Phép thử chỉ kiểm tra ứng xử khi cập nhật Deployment, **không tương đương với kiểm thử mất zone**. PDB quản lý những yêu cầu eviction phù hợp; rolling update Deployment chủ yếu tuân theo strategy `maxUnavailable`/`maxSurge` của Deployment, nên không dùng kết quả này để khẳng định PDB đã bảo vệ khỏi outage.

Để kiểm tra khả năng chịu lỗi zone thật, cần **bài thử resilience/chaos** được phê duyệt trong môi trường cô lập, có kế hoạch quay lại trạng thái ban đầu, giám sát data plane và dependency. Không xóa node/zone hoặc phá kết nối production để thử một ví dụ lý thuyết.

### 8.9. Kiểm tra chất lượng phân tán, không chỉ số Pod

| Phép kiểm tra | Lệnh hoặc nguồn | Đạt khi |
| --- | --- | --- |
| Cluster type | `gcloud container clusters describe` | `location` là region, đúng cluster được tạo. |
| Node zones | `kubectl get nodes -L topology.kubernetes.io/zone` | Có node Ready ở A/B/C như mong đợi. |
| Pod zones | `kubectl get pods -o wide` kết hợp nhãn node | Ba replica được phân bố trên zone theo thiết kế. |
| Pod readiness | `kubectl get pods`, `kubectl describe pod` | Tất cả replica mong muốn Ready, không CrashLoopBackOff. |
| PDB | `kubectl get pdb` | `minAvailable` và số disruptions allowed phù hợp sau rollout. |
| Deployment rollout | `kubectl rollout status` | Cập nhật hoàn thành, không thiếu capacity. |
| Quota/IP và node capacity | Cloud Console, `gcloud`, cluster events | Dư địa đủ cho thay node hoặc bổ sung replica. |
| Ứng dụng thực tế | Health checks, SLO dashboard | p95/p99, error rate và khả năng kết nối dependency đạt mục tiêu. |

Nếu thiếu node/Pod, không “sửa” bằng cách bỏ topology constraints ngay. Trước tiên xác định vùng nào thiếu CPU/RAM/IP, ràng buộc scheduling hoặc quotas nào đang chặn; sau đó quyết định nên tăng capacity, thay zone hoặc điều chỉnh ràng buộc theo mức khả dụng được phê duyệt.

### 8.10. Dọn toàn bộ tài nguyên lab

Từ **đúng kubecontext và project**, xác nhận namespace/cluster trước khi xóa:

~~~bash
kubectl config current-context
gcloud config get-value project
gcloud container clusters list --filter="name=$CLUSTER"

# Xóa đúng namespace thử nghiệm; không dùng namespace chung
kubectl delete namespace gke-ha-lab

# Xóa đúng cluster regional của lab
gcloud container clusters delete "$CLUSTER" \
  --region="$REGION" \
  --quiet
~~~

Chờ thao tác xóa cluster hoàn tất. Sau đó **kiểm tra tài nguyên mạng không còn phụ thuộc cluster**, rồi dọn đúng subnet/VPC được tạo trong bài:

~~~bash
gcloud container clusters list --filter="name=$CLUSTER"
gcloud compute networks subnets describe "$SUBNET" \
  --region="$REGION"

gcloud compute networks subnets delete "$SUBNET" \
  --region="$REGION" --quiet

gcloud compute networks delete "$NETWORK" --quiet
~~~

Chỉ xóa service account và IAM binding khi không còn workload khác sử dụng:

~~~bash
gcloud projects remove-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$NODE_SA" \
  --role="roles/container.defaultNodeServiceAccount"

gcloud iam service-accounts delete "$NODE_SA" --quiet
~~~

**Không xóa API khỏi project, không xóa các mạng/namespace khác và không xóa project dùng chung.** Nếu subnet/VPC vẫn có dependency, đọc lỗi và xác định tài nguyên thuộc lab; không xóa cưỡng bức những thành phần không do mình tạo. Kiểm tra các disk, external IP, log và dịch vụ bổ sung nếu bạn đã mở rộng lab ngoài ví dụ.

GKE control plane, node Compute Engine và những tài nguyên còn tồn tại có thể tiếp tục tính phí. Báo cáo Cloud Billing có thể ghi nhận chi phí trễ; không dựa vào việc đóng Cloud Shell để coi lab đã được dọn.

## 9. Chẩn đoán sự cố khả dụng của GKE

Khi khách hàng báo lỗi, cần phân loại sự cố thuộc **control plane, worker/data plane, ứng dụng, network, dữ liệu hoặc quota**. Không nên kết luận cluster regional đã “mất tính HA” chỉ vì một request HTTP thất bại.

### 9.1. Bắt đầu từ đúng cluster

Từ phiên gcloud đã đăng nhập:

~~~bash
# Chỉ đọc: xác nhận project và cluster
gcloud config get-value project
gcloud container clusters list

# Chọn đúng cluster/location cần điều tra
gcloud container clusters get-credentials "$CLUSTER" \
  --region="$REGION" \
  --project="$PROJECT_ID"

kubectl config current-context
kubectl get nodes -L topology.kubernetes.io/zone
kubectl get pods -A -o wide
~~~

Ví dụ dùng biến bài lab. Khi áp dụng thật, phải xác minh project/cluster/location và chỉ xem namespace/dữ liệu được phân quyền. `kubectl get pods -A` có thể lộ thông tin hạ tầng nhiều nhóm; không chia sẻ output ngoài phạm vi.

### 9.2. Triệu chứng và hướng điều tra

| Triệu chứng | Nguyên nhân có thể | Hướng xác minh |
| --- | --- | --- |
| `kubectl` không truy cập Kubernetes API | Zonal control plane gặp sự cố; endpoint/IAM/RBAC/DNS/certificate lỗi | Kiểm tra cluster type, endpoint, API status và quyền; không tự suy tất cả node đã chết. |
| `kubectl` được nhưng ứng dụng trả 5xx | Pod chưa Ready, lỗi load balancer, database hoặc code mới | Xem Deployment, endpoint, health check, dependency và app logs. |
| Mất zone, Pod không bù ở zone khác | Thiếu node/CPU/RAM/IP/quota; PVC zonal; topology/affinity sai | Kiểm tra `Pending` events, PV topology, autoscaler và node pool locations. |
| Regional cluster nhưng các Pod cùng zone | Node pool một zone hoặc scheduler không được ràng buộc | Xem node zone label, Pod placement, topology spread. |
| Cluster tạo nhiều VM ngoài dự toán | `--num-nodes` là số node **mỗi zone** | Đọc node locations, pool size, quota và billing. |
| Upgrade tạo 503 | Quá ít replica, readiness sai, thiếu surge capacity | Xem Deployment strategy, PDB, events và yêu cầu về headroom. |
| Pod `Pending` sau khi scale | Không có node đủ tài nguyên hoặc vướng taints/PVC/scheduling | `kubectl describe pod`, events, quota, autoscaler. |
| Node `NotReady` | VM/network, node service account, thành phần GKE hoặc zone capacity | Xem node conditions, GKE node pool, IAM của node, Logs. |
| HPA tăng replicas nhưng API vẫn chậm | Cluster Autoscaler chưa thêm node hoặc database/CPU là nút thắt | Xem HPA, node capacity, p99, queue và dependency. |
| Pod đa zone nhưng dữ liệu lỗi | Database/PV chỉ một zone và không có HA | Kiểm tra StorageClass, database replication, backup và failover. |
| Traffic bên ngoài không vào | DNS, LB, Cloud Armor, VPC/firewall, certificate | Điều tra từng hop; không giả định lỗi control plane. |

### 9.3. Những lệnh chỉ đọc để điều tra

~~~bash
kubectl get deploy,rs,pods -n gke-ha-lab -o wide
kubectl get pdb -n gke-ha-lab
kubectl describe deployment ha-demo -n gke-ha-lab
kubectl get events -n gke-ha-lab --sort-by=.lastTimestamp
kubectl describe nodes

gcloud container clusters describe "$CLUSTER" \
  --region="$REGION"
gcloud container node-pools list \
  --cluster="$CLUSTER" --region="$REGION"
~~~

Các lệnh trên đọc cấu hình/trạng thái, không chỉnh tài nguyên. Nếu kết nối API không hoạt động, có thể sử dụng Cloud Console, Cloud Monitoring, GKE operations/logs và dữ liệu hạ tầng để phân tích mà không phụ thuộc `kubectl`.

### 9.4. Cây quyết định

~~~mermaid
flowchart TD
    INC["SLO xấu / request lỗi"] --> API{"Kubernetes API truy cập được?"}
    API -->|Không| CP["Kiểm tra control plane,<br/>location, endpoint, IAM, network"]
    API -->|Có| POD{"Pod và endpoints Ready?"}
    POD -->|Không| NODE["Xem events, node zones,<br/>quota, PVC và autoscaler"]
    POD -->|Có| DEP["Kiểm tra LB, DNS, database,<br/>secret và ứng dụng"]
    CP --> TEST["Đối chiếu miền lỗi;<br/>không sửa theo phỏng đoán"]
    NODE --> TEST
    DEP --> TEST
    TEST --> REC["Khôi phục theo runbook;<br/>đo lại SLO/RTO/RPO"]
~~~

**Quy tắc:** chỉ thay đổi khi biết nó khắc phục lớp nào. Tăng replica lên 10 không giúp khi cả 10 Pod `Pending` vì thiếu capacity. Tạo thêm một control plane regional cũng không khôi phục được database hỏng.

## 10. Tình huống thiết kế: nền tảng bán khóa học trực tuyến

Một doanh nghiệp cung cấp khóa học Java triển khai API thanh toán, danh sách bài học và tiến độ học tập trên GKE. Người học chủ yếu ở Đông Nam Á; hệ thống có database giao dịch và Cloud Storage chứa video. Nhóm cân nhắc:

- **A:** Standard zonal cluster với control plane và node tại zone A.
- **B:** Standard zonal cluster với control plane tại A, node ở A/B/C.
- **C:** Standard regional cluster với control plane đa zone và node ở A/B/C.

### 10.1. Đánh giá các lựa chọn

| Yêu cầu | A | B | C |
| --- | --- | --- | --- |
| Tiết kiệm chi phí cho lab/dev nhỏ | Phù hợp | Có thể tăng node | Có thể dùng node pool ít zone |
| Kubernetes API không phụ thuộc một zone | Không | Không | Phù hợp hơn |
| Pod có thể phục vụ khi một zone mất | Không nếu mọi node ở một zone | Có thể nếu replica phân tán | Có thể nếu replica phân tán |
| Sẵn khả năng chịu lỗi toàn region | Không | Không | **Không** |
| Có HA cho database | Phải thiết kế riêng | Phải thiết kế riêng | Phải thiết kế riêng |
| Có thể thay đổi node locations | Có theo điều kiện Standard | Có | Có |
| Có thể đổi trực tiếp loại control plane | Không | Không | Không |

**Định hướng:** chọn C cho production quan trọng trong **một region**, nếu tổ chức bảo đảm đủ node ở nhiều zone, Pod placement, dependency và đường traffic. Chọn A cho dev/test có ngân sách và mức chịu downtime phù hợp. B chỉ cải thiện khả năng duy trì workload tại zone khác nhưng vẫn có rủi ro Kubernetes API phụ thuộc một zone.

### 10.2. Bản ghi quyết định kiến trúc

~~~yaml
service: course-platform
environment: production
gke:
  mode: Standard
  control_plane: regional
  region: "<region-duoc-phe-duyet>"
  node_locations:
    - "<zone-a>"
    - "<zone-b>"
    - "<zone-c>"
  workload:
    replicas: 3
    topology_spread_by: topology.kubernetes.io/zone
    readiness_probe: true
    pdb_min_available: 2
  scaling:
    enabled: true
    capacity_after_one_zone_loss: "<tai-phai-duy-tri>"
dependencies:
  database: "<co-che-HA-duoc-duyet>"
  objects: "<bucket-va-location>"
  traffic: "<load-balancer-health-check>"
reliability:
  availability_slo: "<muc-tieu>"
  rto: "<muc-tieu>"
  rpo: "<muc-tieu>"
security:
  node_service_account: "<it-quyen>"
  workload_identity: "<theo-chinh-sach>"
observability:
  - ready_replicas_by_zone
  - request_error_rate
  - latency_p99
  - database_availability
~~~

Mẫu trên là tài liệu ra quyết định, **không phải manifest triển khai**. Các placeholder cần được thay bằng dữ liệu có căn cứ, owner và ngày phê duyệt; không tự suy SLO/RTO/RPO từ loại cluster.

### 10.3. Diễn tập giả định mất zone A

Ban đầu có ba API Pod tại A/B/C, tất cả `Ready`. Khi zone A lỗi:

1. Node và Pod tại A có thể không còn phục vụ.
2. Regional control plane có khả năng duy trì Kubernetes API nhờ replica ở zone khác.
3. Endpoint và health check cần loại Pod không khỏe khỏi đường traffic sau thời gian hội tụ.
4. Nếu Pod còn lại chỉ đủ xử lý 60% lưu lượng peak, người dùng vẫn gặp lỗi hoặc p99 cao dù service chưa mất hoàn toàn.
5. Cluster Autoscaler có thể thêm node ở B/C **nếu có quota/capacity/IP và đủ thời gian**; đây không phải cơ chế tức thời.
6. Nếu database chỉ ở A, API có thể trả lỗi mọi thao tác phụ thuộc dữ liệu.
7. Khi phục hồi, cần kiểm tra rebalance, dữ liệu, billing và làm postmortem.

**Bài học:** regional control plane là một lớp bảo vệ, nhưng **capacity sau sự cố và sự sống còn của dependency** mới quyết định SLO end-to-end.

### 10.4. Bài tập định lượng

Giả định API cần tối thiểu **6 vCPU allocatable cho workload** trong giờ cao điểm. Mỗi node là máy **2 vCPU danh nghĩa**, nhưng hệ điều hành, các thành phần Kubernetes và quota tài nguyên cần một phần dung lượng.

Hãy trả lời:

1. Ba node, mỗi zone một node, có đủ phục vụ giờ cao điểm sau khi mất một zone không?
2. Muốn còn ít nhất 6 vCPU **allocatable** sau lỗi một zone, bạn cần thêm bao nhiêu node/CPU dự phòng ở hai zone còn sống?
3. Dùng Cluster Autoscaler thì thời gian cấp VM có đáp ứng RTO không?
4. Giữa dự phòng sẵn và mở rộng sau sự cố, phương án nào phù hợp chi phí/error budget?

**Gợi ý:** không lấy `2 node × 2 vCPU` rồi khẳng định có 6 vCPU. Phải đo `allocatable`, resource requests, tải thực và khả năng mở rộng khi sự cố.

## 11. Câu hỏi tự kiểm tra

**1. Zonal cluster có bắt buộc tất cả node nằm một zone không?**  
Không. Standard zonal có control plane một zone, còn node có thể ở nhiều zone trong region.

**2. Regional cluster có bắt buộc node pool trải ba zone không?**  
Không. Control plane regional có replica đa zone; Standard node pool có thể đặt ở một hoặc nhiều zone, mặc định thường ba.

**3. Có đổi control plane từ zonal sang regional bằng update không?**  
Không. Phải tạo cluster khác và di chuyển workload theo kế hoạch.

**4. Autopilot clusters có zonal control plane không?**  
Không. GKE Autopilot clusters là regional.

**5. Ba Pod trong Deployment luôn tự được chia thành ba zone?**  
Không. Phải có node locations, capacity và scheduling constraints phù hợp, rồi kiểm tra placement thực.

**6. PodDisruptionBudget ngăn sự cố zone hay VM bất ngờ không?**  
Không. PDB giới hạn những voluntary evictions phù hợp, không chặn lỗi hạ tầng.

**7. Vì sao Kubernetes API down nhưng website vẫn có thể hoạt động?**  
Node và Pod đang chạy ở zone còn sống có thể tiếp tục nhận traffic; nhưng điều phối, scheduling và cập nhật cluster bị ảnh hưởng.

**8. Regional cluster có giúp một zonal Persistent Disk chạy ngay ở zone khác không?**  
Không. Phải dùng storage/replication/topology và quy trình recovery phù hợp.

**9. Với ba zone, `--num-nodes=2` thường tạo bao nhiêu node ở regional Standard pool ban đầu?**  
Sáu node: hai mỗi zone × ba zone, khi lệnh được chấp nhận và không có cấu hình khác làm thay đổi số node.

**10. Một regional cluster có tự chịu lỗi toàn region không?**  
Không. Cần cluster, dữ liệu và traffic dự phòng ở region khác.

**11. Vì sao tăng HPA replicas vẫn có thể không cải thiện?**  
HPA chỉ yêu cầu thêm Pod; nếu thiếu node/quota hoặc bị PVC/affinity hạn chế thì Pod chưa chạy.

**12. Vì sao phải giám sát p99 và database availability cùng với Pod Ready?**  
Pod Ready chưa chứng minh giao dịch end-to-end thành công; mạng, load balancer, database và logic ứng dụng cũng ảnh hưởng.

## 12. Tài liệu Google Cloud và Kubernetes tham khảo

- [GKE cluster configuration choices](https://cloud.google.com/kubernetes-engine/docs/concepts/configuration-overview) — vị trí control plane/node và các tùy chọn không đổi sau tạo.
- [Regional clusters](https://cloud.google.com/kubernetes-engine/docs/concepts/regional-clusters) — control plane, node zones, quota và lưu trữ.
- [Creating a regional Standard cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/creating-a-regional-cluster) — `--num-nodes`, `--node-locations` và thiết lập.
- [Creating a zonal Standard cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/creating-a-zonal-cluster) — zonal và multi-zonal.
- [Creating an Autopilot cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/creating-an-autopilot-cluster) — regional control plane của Autopilot.
- [Managing GKE clusters](https://cloud.google.com/kubernetes-engine/docs/how-to/managing-clusters) — đổi node locations và hệ quả với node đang chạy.
- [GKE scalability best practices](https://cloud.google.com/kubernetes-engine/docs/concepts/planning-scalability) — capacity và hoạt động multi-zone.
- [Create a VPC-native cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/alias-ips) — subnet/secondary ranges của node/Pod/Service.
- [Service accounts in GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/service-accounts) — danh tính node và workload.
- [Configure GKE node service accounts](https://cloud.google.com/kubernetes-engine/security/configure-node-service-accounts) — role `roles/container.defaultNodeServiceAccount`.
- [GKE persistent volumes](https://cloud.google.com/kubernetes-engine/docs/concepts/persistent-volumes) — PVC, StorageClass và topology dữ liệu.
- [Kubernetes topology spread constraints](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/) — phân tán Pod giữa zone/node.
- [Kubernetes PodDisruptionBudgets](https://kubernetes.io/docs/tasks/run-application/configure-pdb/) — voluntary evictions.
- [Kubernetes liveness, readiness and startup probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/) — phản ánh sức khỏe Pod.
- [GKE pricing](https://cloud.google.com/kubernetes-engine/pricing) — cấu trúc giá hiện hành.
- [Google Cloud disaster recovery planning](https://cloud.google.com/architecture/disaster-recovery) — RTO, RPO và phục hồi nhiều vùng.

Loại cluster, phiên bản GKE, giá, quota và cách cấp phát node có thể thay đổi. Trước khi tạo production cluster, hãy đối chiếu tài liệu với **mode, region, zone, machine type, network và workload** thực tế. Tính khả dụng không đến từ nhãn “regional” đơn lẻ: **control plane, Pod placement, node capacity, dữ liệu, load balancing, bảo mật và runbook phục hồi** phải hoạt động như một hệ thống.
