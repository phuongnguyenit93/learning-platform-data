# Lập lịch, phân bố workload và chống tập trung vào một miền lỗi

## 1. Vì sao đặt container ở đâu quan trọng?

Một ứng dụng container có thể có nhiều bản sao (replicas), nhưng số lượng bản sao lớn **không tự động đồng nghĩa với độ sẵn sàng cao**. Nếu tất cả bản sao cùng nằm trên một node, một rack hoặc một availability zone, một sự cố tại miền đó có thể làm mất toàn bộ dịch vụ. Ngay cả khi chúng được phân bố đều, ứng dụng vẫn có thể ngừng hoạt động nếu các bản sao cùng phụ thuộc vào một database, storage volume, network gateway hoặc control plane duy nhất.

**Lập lịch workload (workload scheduling)** quyết định workload được đặt trên tài nguyên tính toán nào. **Phân bố workload (workload placement/spreading)** quyết định các bản sao được phân bổ giữa các node, zone hoặc miền lỗi ra sao. Thiết kế đúng phải kết hợp cả hai để cân bằng:

- Đáp ứng tài nguyên CPU, memory, GPU, storage và network.
- Độ sẵn sàng, khả năng chịu lỗi node/zone và thời gian phục hồi.
- Độ trễ giữa workload với dữ liệu hoặc dịch vụ phụ thuộc.
- Mức sử dụng tài nguyên, chi phí và khả năng mở rộng.
- Chính sách bảo mật, tuân thủ, vận hành và vòng đời triển khai.

Trong module **CLOUD_ARCHITECTURE**, lựa chọn compute và mô hình triển khai container cần xuất phát từ yêu cầu nghiệp vụ, sau đó kiểm chứng đánh đổi giữa **độ tin cậy, bảo mật, hiệu năng, khả năng mở rộng, chi phí và vận hành** theo tư duy Well-Architected.

Ví dụ xuyên suốt: nền tảng đặt chỗ gồm web, search, booking, worker và database. Một đợt khuyến mãi làm tăng tải tìm kiếm; cùng lúc nhóm cần nâng cấp node hoặc một availability zone bị mất. Mục tiêu là vẫn phục vụ được các hành trình cần thiết, không để một miền lỗi duy nhất làm tất cả bản sao ngừng hoạt động và không tạo thêm rủi ro cho dữ liệu giao dịch.

## 2. Những khái niệm cần thống nhất

### 2.1. Workload, replica và scheduler

- **Workload** là đơn vị công việc được triển khai, ví dụ Deployment, StatefulSet, Job hoặc một dịch vụ container.
- **Replica** là một bản sao của workload. Replica có thể chạy trên node khác nhau, nhưng không mặc nhiên có dữ liệu độc lập hoặc khả năng phục vụ nếu thành phần dùng chung bị lỗi.
- **Node** là máy tính (VM hoặc máy vật lý) mà nền tảng container dùng để chạy pod/container.
- **Scheduler** chọn node phù hợp cho workload chưa được gán node dựa trên tài nguyên, ràng buộc, chính sách và trạng thái cluster.
- **Placement policy** là tập quy tắc hướng dẫn hoặc bắt buộc cách workload được đặt và phân bố.

Trong Kubernetes, kube-scheduler đánh giá các node khả thi qua các điều kiện lọc (filtering) và xếp hạng (scoring), sau đó gán Pod vào một node. Scheduler tiêu chuẩn không tự biết toàn bộ ý nghĩa nghiệp vụ; người thiết kế phải mô tả tài nguyên và ràng buộc cần thiết bằng cấu hình, nhãn node, affinity, topology spread và các cơ chế liên quan.

### 2.2. Miền lỗi (failure domain)

**Miền lỗi** là phạm vi tài nguyên có thể bị ảnh hưởng đồng thời bởi cùng một sự cố hoặc nguyên nhân chung.

| Miền | Ví dụ | Sự cố có thể ảnh hưởng |
| --- | --- | --- |
| Container/process | Một container hoặc tiến trình | Tiến trình crash, lỗi bộ nhớ, lỗi ứng dụng |
| Pod | Một đơn vị triển khai trên Kubernetes | Pod bị xóa, node drain, readiness fail |
| Node | Một VM hoặc máy vật lý | Kernel panic, mất VM, hết tài nguyên, lỗi NIC |
| Rack/host group | Nhóm máy chia sẻ nguồn điện, switch hoặc hạ tầng | Mất điện, lỗi switch, bảo trì chung |
| Availability zone | Một zone trong region | Sự cố điện, mạng, hạ tầng hoặc dịch vụ vùng |
| Region | Một khu vực địa lý cloud | Sự cố phạm vi vùng, lỗi điều khiển diện rộng |
| Phụ thuộc dùng chung | Database, DNS, identity, storage, load balancer | Nhiều replica cùng mất khả năng phục vụ dù compute vẫn còn |

Không phải nhà cung cấp nào cũng công bố chi tiết rack/host group, và một zone có thể gồm nhiều miền lỗi vật lý bên trong. Phải dựa trên **phạm vi cô lập và bảo đảm thực tế của nền tảng**, không tự suy rằng hai VM khác tên luôn nằm trên hai nguồn điện hay switch độc lập.

### 2.3. Spread, pack và mức ràng buộc

- **Spread (phân tán):** ưu tiên hoặc yêu cầu các bản sao nằm trên nhiều miền lỗi khác nhau để giảm tác động sự cố chung.
- **Pack (gom nhóm):** đặt workload gần nhau để tiết kiệm tài nguyên, giảm độ trễ giữa các thành phần hoặc dành node cho mục tiêu chuyên biệt.
- **Hard constraint:** điều kiện bắt buộc; nếu không có node đáp ứng, workload ở trạng thái Pending hoặc không được lập lịch.
- **Soft preference:** ưu tiên; scheduler cố gắng thỏa mãn nhưng có thể vi phạm khi tài nguyên/điều kiện không cho phép.

Kiến trúc tin cậy thường cần **kết hợp**: phân tán các bản sao cần chịu lỗi, nhưng vẫn có thể gom một số workload gần dữ liệu hoặc phần cứng chuyên dụng. Cần ghi rõ yêu cầu nào bắt buộc, yêu cầu nào có thể nới lỏng khi thiếu tài nguyên.

## 3. Scheduler đưa ra quyết định như thế nào?

Ở mức khái niệm, scheduler chọn một node khả thi cho mỗi workload, thỏa mãn tài nguyên và ràng buộc, sau đó tối ưu các mục tiêu như cân bằng tải, phân tán, mức sử dụng hoặc vị trí dữ liệu. Scheduler không thay kiến trúc sư quyết định mục tiêu; các chính sách đặt workload mới mô tả mục tiêu đó.

| Nhóm tín hiệu | Ví dụ | Hệ quả khi khai báo sai |
| --- | --- | --- |
| CPU/memory requests | Tài nguyên cần để lập lịch và tính khả năng chứa Pod | Quá thấp gây overcommit; quá cao làm Pod Pending và lãng phí |
| Limits | Trần CPU/memory container theo cấu hình runtime | CPU limit thấp gây throttling; memory vượt limit có thể OOM kill |
| Node selector/affinity | Chọn node theo label, loại máy hoặc đặc tính | Rule quá chặt làm giảm số node khả thi |
| Taints/tolerations | Loại node khỏi workload không được phép hoặc dành node chuyên biệt | Toleration quá rộng khiến workload chạy nhầm node |
| Pod affinity/anti-affinity | Đặt workload gần hoặc tách khỏi workload khác | Ràng buộc cứng không khả thi khi thiếu node |
| Topology spread | Cân bằng số Pod qua node/zone/topology domain | Selector hoặc topology key sai làm phân bố sai |
| Volume và thiết bị | Zone của persistent volume, GPU, local disk | Pod không chạy được trên node không truy cập được storage/thiết bị |
| Priority/preemption | Ưu tiên workload quan trọng hơn | Có thể đẩy workload khác ra khỏi node và gây gián đoạn |

### 3.1. Requests khác với limits

Trong Kubernetes, resources.requests được scheduler sử dụng để tính nhu cầu của Pod. resources.limits đặt giới hạn thực thi của container theo cơ chế runtime và loại tài nguyên. Hai giá trị có ý nghĩa khác nhau:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "1"
    memory: "1Gi"
~~~

Ví dụ khai báo này yêu cầu scheduler tính Pod cần 0,5 CPU và 512 MiB memory; container bị giới hạn tối đa 1 CPU và 1 GiB memory theo cấu hình. Nếu requests thấp hơn đáng kể mức dùng thực tế, nhiều Pod có thể được xếp vào cùng node và tạo tranh chấp tài nguyên. Nếu requests quá cao, cluster có thể không sử dụng được dung lượng còn trống.

**CPU và memory không có hành vi giống nhau khi chạm limit.** CPU thường bị giới hạn/throttling theo cơ chế cgroup; memory không thể throttling theo cùng cách và vượt giới hạn có thể dẫn đến OOM kill. Phải quan sát usage, throttling, OOM, eviction và latency để điều chỉnh.

### 3.2. Tài nguyên toàn Pod và overhead

Scheduler xét tổng requests của các container trong Pod cùng một số overhead và đặc tính cấu hình. Sidecar proxy, agent bảo mật, log collector hoặc init container có thể làm tổng tài nguyên lớn hơn ước tính từ application container đơn lẻ. Khi thiết kế service mesh hoặc sidecar injection, cần tính cả phần này vào capacity planning.

Ngoài CPU/memory, cluster còn có giới hạn số Pod trên node, ephemeral storage, IP của CNI, volume attach, GPU và quota ở cấp cloud. Một node còn CPU và memory vẫn có thể không nhận thêm Pod vì thiếu IP hoặc giới hạn khác.

## 4. Phân bố bản sao qua node và availability zone

Nếu một dịch vụ có nhiều replicas, mục tiêu cơ bản là tránh để tất cả bản sao nằm trong cùng một miền lỗi. Có thể thực hiện ở nhiều cấp:

1. **Khác node:** giảm tác động khi một node hỏng hoặc được bảo trì.
2. **Khác rack/host group:** giảm rủi ro sự cố vật lý chung nếu nền tảng cung cấp topology tương ứng.
3. **Khác availability zone:** chịu được một số sự cố ở phạm vi zone, đồng thời cần xử lý network latency và phụ thuộc dữ liệu liên zone.
4. **Khác region:** tăng phạm vi chịu lỗi địa lý nhưng làm phức tạp dữ liệu, định tuyến, failover, chi phí và RTO/RPO.

~~~mermaid
flowchart TB
    SVC["Booking Service: 6 replicas"]
    SVC --> Z1
    SVC --> Z2
    SVC --> Z3
    subgraph Z1["Availability Zone A"]
      A1["Node A1: 2 replicas"]
    end
    subgraph Z2["Availability Zone B"]
      B1["Node B1: 2 replicas"]
    end
    subgraph Z3["Availability Zone C"]
      C1["Node C1: 2 replicas"]
    end
~~~

Sơ đồ mô tả mục tiêu phân bố 2–2–2. Nó chỉ đạt được khi các zone có đủ tài nguyên, scheduler nhận biết topology chính xác, node thuộc đúng zone, các ràng buộc khác không mâu thuẫn và dịch vụ dữ liệu hỗ trợ tình huống tương ứng. **Sáu replica trên ba zone không có nghĩa database cũng đã có ba bản sao có thể ghi độc lập.**

### 4.1. Vì sao anti-affinity theo node vẫn chưa đủ?

Nếu chỉ đặt quy tắc không đặt hai Pod cùng nhãn trên một node, scheduler có thể phân bố chúng qua nhiều node nhưng tất cả node vẫn thuộc một zone. Khi zone mất, mọi bản sao đều mất theo. Vì vậy cần xác định topology key và miền phân tán phù hợp: hostname, zone, rack hoặc miền khác mà nền tảng thực sự cung cấp.

Ngược lại, bắt buộc mọi replica nằm ở zone khác nhau có thể khiến Pod Pending nếu số zone khả dụng ít hơn số replica hoặc thiếu capacity. Cần lựa chọn giữa phân bố lý tưởng, số replica tối thiểu phải chạy và hành vi khi một miền lỗi không còn khả dụng.

### 4.2. Topology spread constraints

Kubernetes hỗ trợ topologySpreadConstraints để điều khiển chênh lệch số Pod giữa các topology domain. Ví dụ sau ưu tiên phân tán replica của ứng dụng booking-api theo zone và node:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: booking-api
spec:
  replicas: 6
  selector:
    matchLabels:
      app: booking-api
  template:
    metadata:
      labels:
        app: booking-api
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: booking-api
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: booking-api
      containers:
        - name: api
          image: example.invalid/booking-api:v1
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
~~~

Giải thích:

- topology.kubernetes.io/zone yêu cầu cân bằng theo zone; maxSkew bằng 1 đặt mức chênh lệch cho phép giữa domain theo cách tính của scheduler.
- DoNotSchedule khiến Pod không được xếp lịch nếu không thể thỏa điều kiện spread cho rule này.
- Rule theo hostname đặt ScheduleAnyway: scheduler cố gắng phân bố qua node nhưng có thể vi phạm khi không còn lựa chọn phù hợp.
- labelSelector xác định nhóm Pod được tính vào phân bố. Selector phải khớp đúng workload cần kiểm soát và cần xem xét các Pod khác cùng nhãn trong topology.

Đây là cấu hình minh họa, chưa phải manifest production. Cần kiểm tra số zone/node khả dụng, label topology có đầy đủ và đúng thực tế, cách tính Pod đang tồn tại, phiên bản cluster và hành vi khi một zone thiếu tài nguyên. Khi cần ưu tiên khả năng chạy tối thiểu trong điều kiện lỗi, có thể phải điều chỉnh whenUnsatisfiable và các ràng buộc theo yêu cầu nghiệp vụ.

## 5. Pod affinity và anti-affinity

Topology spread cân bằng số lượng bản sao qua domain. **Pod affinity/anti-affinity** diễn đạt quan hệ gần hoặc tránh gần giữa các nhóm Pod.

| Cơ chế | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| podAffinity | Đặt Pod gần Pod khác theo topology key | Đặt worker gần cache nếu giảm độ trễ quan trọng và rủi ro tập trung được chấp nhận |
| podAntiAffinity | Tránh đặt Pod cùng nhóm gần nhau theo topology key | Tách hai replica API khỏi cùng node hoặc zone |
| requiredDuringSchedulingIgnoredDuringExecution | Quy tắc bắt buộc khi lập lịch, không tự di chuyển Pod đã chạy nếu topology đổi | Không để hai replica booking cùng hostname |
| preferredDuringSchedulingIgnoredDuringExecution | Ưu tiên khi lập lịch nhưng có thể không thỏa nếu không khả thi | Cố gắng tách replica qua node |

Ví dụ hard anti-affinity theo node:

~~~yaml
affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            app: booking-api
        topologyKey: kubernetes.io/hostname
~~~

Rule trên không cho hai Pod mang nhãn app: booking-api được xếp trên cùng một node theo hostname topology. Nếu số node khả dụng nhỏ hơn số replica hoặc các node không có tài nguyên phù hợp, Pod có thể Pending. Trong nhiều hệ thống, topology spread với maxSkew linh hoạt hơn hard anti-affinity khi muốn chạy nhiều replica trên số node giới hạn.

**Không nên áp dụng anti-affinity cứng chỉ vì nghe có vẻ an toàn.** Với workload ít quan trọng hoặc môi trường dev, ràng buộc ưu tiên có thể đủ. Với workload critical, cần phân bố theo zone, nhưng phải biết rõ mức dịch vụ sẽ suy giảm thế nào khi mất một zone.

## 6. Node affinity, taints và tolerations

Phân bố workload không chỉ để chống lỗi; đôi khi cần đặt đúng workload vào đúng loại node:

- Node có GPU dành cho inference/training.
- Node có bộ nhớ lớn cho cache hoặc analytics.
- Node chuyên dụng cho workload có yêu cầu tuân thủ.
- Node system dành cho thành phần hạ tầng/daemon.
- Node có thiết bị local hoặc kiến trúc CPU phù hợp.

### 6.1. Node labels và node affinity

Node label mô tả đặc tính node. nodeSelector hoặc node affinity chọn node dựa trên label. Ví dụ:

~~~yaml
nodeSelector:
  node-pool: general-purpose
~~~

Hoặc dùng affinity khi cần điều kiện phức tạp và mức ưu tiên:

~~~yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: node-pool
              operator: In
              values:
                - general-purpose
                - memory-optimized
~~~

Các label do nền tảng quản lý (như zone, region, hostname) cần được phân biệt với label tùy chỉnh do người dùng đặt. Với nhãn dùng làm ranh giới bảo mật, cần bảo vệ quyền chỉnh sửa label và cân nhắc cơ chế bảo đảm nhãn không bị node không đáng tin tự ý giả mạo.

### 6.2. Taints và tolerations

**Taint** trên node khiến Pod không được xếp lên node đó nếu Pod không có toleration phù hợp (với effect tương ứng). **Toleration** chỉ thể hiện Pod chấp nhận taint; nó không tự chọn node. Muốn đặt Pod lên node chuyên biệt thường cần kết hợp taint/toleration với node affinity/selector.

Ví dụ, node GPU có taint workload=gpu:NoSchedule. Chỉ Pod cần GPU và được phép chạy tại đó mới khai báo toleration tương ứng, đồng thời chọn node có label GPU. Cách này ngăn Pod thông thường lấp đầy tài nguyên dành cho workload chuyên biệt.

Các effect thường gặp:

- NoSchedule: không lập lịch Pod mới nếu không toleration.
- PreferNoSchedule: ưu tiên tránh node nhưng có thể vẫn xếp nếu cần.
- NoExecute: có thể ảnh hưởng cả Pod đang chạy không toleration, tùy thời gian và cấu hình.

Không thêm toleration quá rộng cho mọi workload; điều đó làm mất hiệu quả cô lập node. Cần kiểm tra DaemonSet, system Pod, node condition và quy trình drain vì các taint có thể thay đổi hành vi vận hành.

## 7. PodDisruptionBudget và bảo trì có kiểm soát

Phân bố bản sao mới chỉ xử lý vị trí; trong vận hành, nhóm còn phải thay node, nâng cấp cluster hoặc vá hệ điều hành. Nếu cùng lúc xóa quá nhiều Pod khỏe, dịch vụ có thể mất khả năng phục vụ dù cluster vẫn còn đủ node.

**PodDisruptionBudget (PDB)** đặt giới hạn gián đoạn tự nguyện đối với một nhóm Pod, thường bằng minAvailable hoặc maxUnavailable. PDB được dùng trong các tình huống disruption mà Kubernetes hỗ trợ như thao tác drain node qua eviction API. Nó không phải bảo đảm rằng số Pod luôn khỏe, không bảo vệ trước mọi lỗi đột ngột và không thay thế readiness probe hay replica count.

Ví dụ:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: booking-api-pdb
spec:
  minAvailable: 4
  selector:
    matchLabels:
      app: booking-api
~~~

Với nhóm Pod khớp selector, mục tiêu là giữ ít nhất bốn Pod sẵn sàng trong các voluntary disruptions được PDB điều phối. Nếu chỉ có bốn Pod và minAvailable là bốn, thao tác drain có thể bị chặn cho tới khi có Pod thay thế hoặc policy thay đổi. Điều đó có thể làm chậm bảo trì; không nên đặt minAvailable theo cảm tính.

| Cơ chế | Giải quyết điều gì? | Không giải quyết điều gì? |
| --- | --- | --- |
| Replicas | Số bản sao mong muốn | Không bảo đảm bản sao nằm trên miền lỗi độc lập |
| Topology spread/anti-affinity | Phân bố vị trí | Không bảo đảm Pod mới khởi động nhanh hoặc app sẵn sàng |
| Readiness probe | Quyết định Pod có nhận traffic hay không | Không giữ đủ số replica khi node bị mất |
| Liveness/startup probe | Phát hiện tiến trình cần khởi động lại hoặc chưa khởi động xong | Không thay cơ chế chịu lỗi giữa node/zone |
| PDB | Giới hạn voluntary disruption đồng thời | Không ngăn lỗi bất ngờ, mất zone hoặc OOM đồng loạt |
| Deployment strategy | Điều khiển rolling update theo thông số rollout | Không tự bảo đảm còn capacity nếu requests/quota không đủ |

Phải xem PDB cùng rolling update, cluster autoscaler, node drain, capacity headroom và topology spread. Một PDB quá chặt cộng với hard anti-affinity và thiếu tài nguyên có thể làm cả nâng cấp lẫn tự phục hồi bị đình trệ.

## 8. Kết hợp scheduler với autoscaling và capacity planning

Scheduler chỉ có thể đặt Pod lên tài nguyên hiện có hoặc tài nguyên được bổ sung sau đó. **Autoscaling không sửa được một placement policy không khả thi**; ngược lại, placement policy có thể khiến autoscaler phải tạo thêm node pool hoặc mở rộng ở zone phù hợp.

### 8.1. Ba lớp scaling

- **Horizontal Pod Autoscaler (HPA):** tăng/giảm số Pod dựa trên metric như CPU/memory hoặc custom/external metrics.
- **Cluster Autoscaler hoặc cơ chế node autoscaling của nền tảng:** tăng/giảm node khi có Pod chưa được lập lịch hoặc tài nguyên dư, trong phạm vi cấu hình node pool và quota.
- **Vertical Pod Autoscaler (VPA):** đề xuất hoặc điều chỉnh requests/limits theo cách triển khai; việc áp dụng có thể cần restart Pod và phải phối hợp với HPA.

Không nên chạy HPA theo CPU nếu CPU requests không phản ánh mức tải phù hợp; phần trăm CPU được tính dựa trên requests. Với dịch vụ tìm kiếm, số request/giây, queue depth, độ trễ hoặc số tác vụ đang xử lý có thể là tín hiệu hữu ích hơn, nếu metric được định nghĩa và vận hành đáng tin cậy.

### 8.2. Headroom và năng lực khi mất một zone

Giả sử ứng dụng có 9 Pod để đáp ứng tải bình thường, mỗi Pod cần 1 vCPU request. Nếu chia đều 3 zone, mỗi zone có 3 Pod. Khi mất một zone, 6 Pod còn lại có thể không đủ tải nếu không có dự phòng.

Nếu mục tiêu là vẫn chạy đủ tải sau mất một zone, cần tính capacity trên **số zone còn lại**, thay vì chỉ cộng một tỷ lệ dự phòng tùy ý. Ví dụ với mục tiêu 9 Pod phục vụ toàn tải và 3 zone đồng đều, để chịu mất một zone mà không giảm số Pod phục vụ, nhóm có thể cần đặt tổng 12 Pod (4 mỗi zone): khi mất một zone còn 8, vẫn chưa đủ 9. Muốn còn ít nhất 9 Pod sau mất một trong 3 zone, phân bố cần ít nhất 5 Pod mỗi zone (tổng 15), nếu không xét các giới hạn khác. Đây là minh họa số học đơn giản; capacity thật phải dựa trên throughput đo được, tài nguyên node và hành vi ứng dụng.

### 8.3. Tính khả thi của Pod Pending

Khi Pod Pending, cần điều tra lý do thay vì chỉ tăng số node:

- Không node nào đủ CPU/memory requests hoặc ephemeral storage.
- Hard node affinity, taint/toleration, anti-affinity hoặc topology spread không thỏa.
- Zone thiếu tài nguyên, quota cloud đã chạm hoặc chưa có capacity cho loại instance.
- Không đủ IP, volume attach, GPU hoặc tài nguyên thiết bị.
- PersistentVolume có topology ràng buộc với zone khác.
- Priority/preemption không thể giải phóng đủ tài nguyên hoặc làm gián đoạn workload quan trọng khác.

Scheduler events và trạng thái Pod thường chỉ ra lý do như Insufficient cpu, Insufficient memory, volume node affinity conflict hoặc node affinity mismatch. Nhóm phải kết hợp các tín hiệu đó với node metrics, quota cloud và trạng thái autoscaler.

## 9. Workload có trạng thái và ràng buộc lưu trữ

Phân bố Pod stateless thường đơn giản hơn Stateful workload. Database, broker, cache có persistence hoặc hệ thống xử lý file có thể phụ thuộc vào **persistent volume, zone, replica protocol và danh tính dữ liệu**.

### 9.1. Storage topology ảnh hưởng placement

Một persistent volume có thể chỉ attach hoặc truy cập được từ một zone hoặc node theo loại storage. Khi Pod được lên lịch ở zone khác, volume topology có thể làm Pod Pending. Với volume nhiều zone hoặc filesystem dùng chung, cũng cần kiểm tra giới hạn attach, semantics đồng thời và độ trễ.

Trước khi chọn placement cho StatefulSet, cần biết:

1. Storage class tạo volume theo zone nào và binding diễn ra lúc nào?
2. Một volume có thể attach đồng thời ở bao nhiêu node và mode truy cập nào?
3. Khi zone mất, volume có thể phục hồi/replicate sang zone khác theo cơ chế gì và mất bao lâu?
4. Database/broker tự sao chép dữ liệu ở tầng ứng dụng hay dựa vào storage replication?
5. Quorum, leader election, split-brain và thứ tự phục hồi được xử lý thế nào?

**Không đặt nhiều replica ứng dụng ở nhiều zone rồi coi stateful tier đã chịu lỗi.** Nếu mọi replica đều ghi vào một database đơn lẻ trong zone mất kết nối, API vẫn có thể không hoạt động dù các Pod còn sống.

### 9.2. Tách placement của application và data

Với nền tảng đặt chỗ, có thể phân bố API stateless qua ba zone, trong khi database dùng mô hình primary/standby hoặc cluster có quorum theo khả năng dịch vụ dữ liệu cung cấp. Cần đo:

- Độ trễ từ API đến database và ảnh hưởng của giao tiếp liên zone.
- Cơ chế failover database, thời gian phát hiện và thời gian client tái kết nối.
- RPO, tính nhất quán, transaction in-flight và việc đối soát khi chuyển primary.
- Backup có nằm độc lập khỏi miền lỗi chính không và có thử restore định kỳ không.

Một primary/standby cross-zone có thể tăng độ tin cậy nhưng vẫn có thể bị ảnh hưởng bởi lỗi cấu hình, identity, DNS, storage hoặc control plane dùng chung. Cần nhìn toàn bộ dependency graph.

## 10. Chống tập trung vào miền lỗi dùng chung

Phân bố replicas chỉ có ý nghĩa nếu những điểm phụ thuộc có tác động chung cũng được xem xét. Những thành phần dễ trở thành **single point of failure** gồm:

- Một ingress controller, load balancer hoặc gateway duy nhất mà không có dự phòng theo phạm vi yêu cầu.
- Một DNS resolver, identity provider hoặc secret service mà mọi Pod cần gọi khi khởi động.
- Một message broker, storage endpoint hoặc database không có mô hình chịu lỗi phù hợp.
- Một node pool duy nhất dành cho mọi workload critical; hoặc toàn bộ replicas cùng bị dồn vào node có cùng host failure.
- Một pipeline triển khai hoặc control plane dùng chung khiến không thể thay đổi khi có sự cố.

### 10.1. Vẽ dependency graph theo hành trình

~~~mermaid
flowchart TD
    CLIENT["Client"]
    LB["Load Balancer"]
    API["Booking API replicas ở 3 zone"]
    DB["Database primary/replica"]
    ID["Identity provider"]
    DNS["DNS"]
    SECRET["Secret manager"]
    QUEUE["Message broker"]
    CLIENT --> LB --> API
    API --> DB
    API --> ID
    API --> DNS
    API --> SECRET
    API --> QUEUE
~~~

Sơ đồ cần mở rộng để ghi vị trí và miền lỗi thực của từng dependency, đường truy cập lúc runtime và lúc khởi động. Ví dụ, nếu toàn bộ API replica khởi động lại cùng lúc và phải gọi một secret service đang lỗi, chúng có thể không khởi động dù node/zone còn đủ capacity.

### 10.2. Phân tích blast radius

| Sự cố giả định | Thành phần bị ảnh hưởng | Câu hỏi cần trả lời |
| --- | --- | --- |
| Mất một node | Pod trên node đó | Pod được tạo lại ở đâu, còn đủ node và IP không? |
| Mất một zone | Node, volume hoặc endpoint zone đó | Số Pod còn lại có đủ tải, database có failover không? |
| Một node pool hết capacity | Workload phụ thuộc pool đó | Có pool thay thế và tương thích CPU/GPU/storage không? |
| DNS/identity/secret chậm | Nhiều ứng dụng cùng phụ thuộc | Có cache an toàn, timeout, retry và degraded mode không? |
| Cạn quota cloud | Autoscaler/rollout/DR | Quota đã tính cả đỉnh, nâng cấp và khôi phục chưa? |
| Triển khai lỗi đồng loạt | Nhiều replica cùng version | Có rollout giới hạn, canary, rollback và compatibility không? |

Không phải mọi dependency đều cần multi-region active-active. Có thể chọn dự phòng theo mức độ critical, nhưng cần ghi nhận khoảng thời gian gián đoạn và quy trình phục hồi được nghiệp vụ chấp nhận.

## 11. Anti-concentration và chiến lược phân bố thực tế

Chống tập trung không đơn giản là "mỗi node một Pod". Có nhiều cách phân bố và mỗi cách phục vụ mục tiêu khác nhau:

| Chiến lược | Cách thực hiện | Phù hợp khi | Rủi ro/đánh đổi |
| --- | --- | --- | --- |
| Spread theo node | Anti-affinity hoặc topology spread theo hostname | Chống mất một node, rolling maintenance | Có thể vẫn tập trung trong một zone |
| Spread theo zone | Topology spread theo zone | Chịu mất một zone | Tốn tài nguyên và có thể tăng latency/traffic cost liên zone |
| Spread theo region | Nhiều cluster/region và global routing | Yêu cầu khôi phục địa lý | Dữ liệu, consistency, failover và vận hành phức tạp |
| Spread theo rack/host group | Topology label do hạ tầng cung cấp | Hệ thống có yêu cầu tách failure vật lý sâu hơn | Không phải nền tảng nào cũng expose topology chi tiết |
| Spread theo tenant/workload | Tách node pool, namespace, quota hoặc cluster theo khách hàng/nhóm | Multi-tenant, isolation và noisy-neighbor | Tăng chi phí và phân mảnh công suất |

### 11.1. Khi nào nên pack?

Gom workload gần nhau có thể hợp lý nếu:

- Một nhóm tác vụ trao đổi dữ liệu lớn và nhạy độ trễ.
- Có node chuyên dụng hoặc GPU cần được sử dụng hiệu quả.
- Batch/worker được phép chạy ở pool có thể co giãn và không cần mức cô lập giống API production.
- Cache/compute cần locality với dữ liệu để giảm network transfer.

Tuy nhiên, pack các bản sao của một dịch vụ critical vào cùng miền lỗi sẽ làm tăng blast radius. Có thể pack **trong một zone nhưng spread giữa các zone**, hoặc gom các worker ít quan trọng trong node pool riêng trong khi API giữ chính sách phân tán nghiêm ngặt.

### 11.2. Tách workload theo class

Một mô hình đơn giản:

| Class | Ví dụ | Placement | Chính sách tài nguyên |
| --- | --- | --- | --- |
| Critical stateless | Booking API | Spread qua node và zone, PDB phù hợp | Requests đo được, autoscaling, ưu tiên triển khai |
| Read-heavy | Search API | Spread, có cache/read replica gần | Scale theo throughput/latency và giới hạn DB |
| Async worker | Email, analytics jobs | Có thể pack trong pool riêng, queue hữu hạn | Giới hạn concurrency, scale theo backlog |
| Stateful | Database, broker | Theo topology/storage/quorum do dịch vụ hỗ trợ | Capacity ổn định, quy trình backup/restore |
| System/management | DNS, monitoring, ingress, agent | Dự phòng theo failure domain thích hợp | Không để workload user chiếm tài nguyên hạ tầng |

## 12. Quan sát và kiểm tra placement sau khi triển khai

Không thể chỉ nhìn manifest để biết workload đang thực sự phân bố ra sao. Phải quan sát **trạng thái scheduler, vị trí Pod và mức sử dụng node** theo thời gian.

| Nhóm quan sát | Chỉ số hoặc sự kiện | Ý nghĩa |
| --- | --- | --- |
| Scheduling | Pod Pending, unschedulable reason, scheduling latency | Ràng buộc hoặc capacity nào đang chặn Pod? |
| Placement | Số Pod theo node/zone/node pool, topology skew | Các replicas có đang tập trung vào một miền không? |
| Node health | Ready condition, pressure, restart, node pool capacity | Miền lỗi hoặc node nào đang có nguy cơ? |
| Resource | CPU/memory requests so usage, throttling, OOM, ephemeral storage | Requests/limits có phù hợp thực tế không? |
| Availability | Ready replicas, PDB disruptionsAllowed, availability theo zone | Có đủ Pod phục vụ khi bảo trì hoặc lỗi không? |
| Data | DB connection, replication lag, failover, storage latency | Compute còn sống nhưng data tier có đáp ứng được không? |
| Cost | Node utilization, idle capacity, cross-zone traffic | Độ tin cậy tăng thêm có chi phí hợp lý không? |

Có thể dùng Kubernetes API/metrics, scheduler events, node labels và dashboard của nền tảng cloud để tổng hợp. Một dashboard tốt nên thể hiện **replica mong muốn, replica sẵn sàng và số replica theo từng zone**, không chỉ tổng số Pod.

### 12.1. Phát hiện lệch phân bố

Giả sử Deployment yêu cầu 6 replica nhưng dashboard cho thấy 5 Pod ở zone A và 1 Pod ở zone B. Trước khi kết luận scheduler lỗi, hãy kiểm tra:

- Zone C có node Ready và label topology chính xác không?
- Các Pod đã tồn tại trước khi áp topology rule hay được tạo sau đó?
- Node affinity, taint, volume topology hoặc resource requests có loại các node khác không?
- Pod có selector phù hợp và scheduler có nhận diện đúng topology domain?
- Zone B/A còn quota và cloud capacity không?
- Có Pod thuộc workload khác cùng label selector làm sai kết quả tính skew không?

Điều chỉnh topology rule mà không hiểu nguyên nhân có thể chỉ chuyển Pod Pending từ zone này sang zone khác. Phải giữ bằng chứng trước/sau và xác nhận số Pod thực sự sẵn sàng.

## 13. Diễn tập sự cố và nâng cấp cluster

Phân bố tốt cần được kiểm chứng bằng failure test trong môi trường được cho phép và có kiểm soát.

| Kịch bản thử | Kết quả cần xác nhận |
| --- | --- |
| Drain một node | PDB cho phép đúng số Pod gián đoạn, Pod thay thế được scheduler đặt lên node khác, SLO không bị vi phạm ngoài ngưỡng |
| Một node bất ngờ NotReady | Replica được tạo lại, readiness và routing cập nhật, không có lỗi kéo dài do storage |
| Một zone không thể nhận Pod mới | Placement rule hoạt động như thiết kế, còn đủ capacity hay degraded mode được kích hoạt |
| Node pool cạn CPU/memory | Autoscaler tăng pool phù hợp hoặc phát cảnh báo có giải thích; không tạo vòng lặp mở rộng vô hạn |
| Database failover | API xử lý reconnect, transaction in-flight và retry có idempotency |
| Zone hồi phục | Workload tái cân bằng có kiểm soát, tránh evict/di chuyển hàng loạt |
| Rolling deployment | Còn đủ replica Ready, không phá placement và không vượt capacity/quota |

### 13.1. Quy trình drain/maintenance

1. Kiểm tra trạng thái zone/node, số Pod Ready, PDB và công suất còn lại.
2. Xác nhận node thay thế đã có hoặc autoscaler có thể cấp đúng loại node và quota.
3. Drain theo từng nhóm nhỏ; theo dõi Pod eviction, scheduling và SLO.
4. Tạm dừng nếu PDB không cho phép, Pod Pending tăng hoặc latency/error vượt ngưỡng.
5. Sau khi node mới Ready và workload ổn định, tiếp tục bảo trì phần còn lại.
6. Kiểm tra lại phân bố replicas, database connectivity, cache/queue và dashboard.

Không giảm PDB chỉ để hoàn tất bảo trì mà chưa đánh giá khả năng chịu lỗi và chưa có phê duyệt phù hợp. PDB nên phản ánh **mức gián đoạn tự nguyện chấp nhận được**, không phải một con số chọn để lệnh drain luôn thành công.

## 14. Ví dụ thiết kế placement cho nền tảng đặt chỗ

Giả sử cluster có ba zone, mỗi zone hai node ứng dụng và một node pool riêng cho workload đặc biệt. Booking API cần 6 replicas để phục vụ tải đỉnh; search có 9 replicas và có thể mở rộng; worker xử lý email/analytics không cần độ trễ thấp. Database được cung cấp như dịch vụ managed đa zone hoặc cụm stateful có quy trình failover riêng.

### 14.1. Mục tiêu phân bố

| Workload | Số replica ban đầu | Phân bố mong muốn | Lý do |
| --- | ---: | --- | --- |
| Booking API | 6 | 2 mỗi zone, tách node nếu đủ capacity | Giữ khả năng xác nhận giao dịch khi mất node/zone |
| Search API | 9 | 3 mỗi zone, scale theo nhu cầu | Giữ khả năng đọc và hấp thụ tải tăng |
| Worker | 6 | Cân bằng theo node pool; có thể pack trong pool riêng | Tối ưu tài nguyên, dùng queue để điều tiết |
| Ingress controller | Theo sizing/HA của nền tảng | Tách node và zone phù hợp | Tránh một node lỗi làm mất toàn bộ đường vào |
| Monitoring agents | DaemonSet hoặc mô hình được hỗ trợ | Có mặt trên node cần giám sát | Thu thập dữ liệu từng node; tính cả overhead |

### 14.2. Tính khả năng chịu lỗi zone

Nếu 6 Pod Booking API phân bố đều 2–2–2, khi mất một zone sẽ còn 4 Pod. Câu hỏi không chỉ là "còn Pod không?" mà là **4 Pod có đủ công suất phục vụ tải mà doanh nghiệp yêu cầu trong thời gian vùng bị mất không?**

Giả sử load test cho thấy một Pod xử lý bền vững 50 request/giây ở SLO mục tiêu; tải đỉnh cần 180 request/giây:

~~~text
Nhu cầu số Pod cho tải đỉnh = ceil(180 / 50) = 4
Số Pod còn lại sau khi mất một zone (phân bố 2-2-2) = 4
Headroom sau sự cố = 0 Pod
~~~

Về phép chia lý thuyết, 4 Pod còn lại vừa đủ tải. Nhưng không có headroom để xử lý biến động, startup chậm hoặc Pod bị lỗi khác. Nếu muốn còn 5 Pod sau khi mất zone, mỗi zone cần ít nhất 3 Pod để hai zone còn lại cung cấp 6 Pod, tổng cộng 9 Pod. Đây mới là điểm khởi đầu; còn phải tính requests, node capacity, autoscaling delay, database throughput và quota.

**Không dùng phép tính tổng replicas thay cho kiểm thử**. Throughput thực tế phụ thuộc CPU, memory, kết nối DB, cache, giới hạn downstream, kích thước request và độ trễ liên zone. Hãy đo ở tải toàn hành trình và thử trong tình trạng suy giảm có kiểm soát.

### 14.3. Quyết định pack/spread cho từng workload

- Booking API: ưu tiên spread qua zone và node; PDB giữ số Pod đủ cho hành trình nghiệp vụ; requests phản ánh mức tải thực.
- Search API: spread qua zone; cache và read replica đặt gần nơi phục vụ; có thể giảm chất lượng tìm kiếm nâng cao nếu cần bảo vệ DB.
- Worker: queue hữu hạn, giới hạn số consumer đồng thời; cho phép pack ở pool riêng để tiết kiệm, miễn backlog và thời gian xử lý vẫn trong SLO.
- Database: placement theo topology và cơ chế HA của dịch vụ dữ liệu; không cố điều khiển Pod database bằng rule của ứng dụng stateless nếu chưa hiểu quorum/storage.
- Ingress và monitoring: dành capacity riêng, không để workload ứng dụng chiếm hết node hoặc tài nguyên khiến lớp quản lý không hoạt động.

## 15. Ma trận lựa chọn placement policy

Trước khi thêm affinity hay spread rule, hãy đi qua ma trận:

| Câu hỏi | Nếu trả lời "có" | Hướng thiết kế |
| --- | --- | --- |
| Mất một node có làm mất toàn bộ replicas của một dịch vụ không? | Cần giảm tương quan lỗi node | Spread theo hostname hoặc anti-affinity phù hợp |
| Mất một zone có vượt quá downtime cho phép không? | Cần chịu lỗi zone | Spread theo zone, capacity ở hai zone còn lại và data failover |
| Workload phụ thuộc thiết bị/hardware đặc biệt không? | Chỉ một nhóm node đáp ứng được | Node affinity + taints/tolerations và dự phòng node pool |
| Dữ liệu được gắn với zone/volume cụ thể không? | Scheduler có thể chọn node không tương thích | Thiết kế storage topology và volume binding |
| Chỉ có ít node hơn số replica? | Hard anti-affinity có thể khiến Pod Pending | Dùng soft preference/topology spread hoặc bổ sung capacity |
| Tải của tenant có thể gây noisy-neighbor? | Tách nhóm tài nguyên hoặc giới hạn theo tenant | Node pool, quota, namespace/resource quota và scheduling policy |
| Workload có cần chạy gần cache/database? | Locality có lợi cho latency/transfer | Cân nhắc affinity/placement gần dữ liệu nhưng vẫn giữ spread miền lỗi |
| Cần bảo trì mà không giảm dưới số replica tối thiểu? | Phải giới hạn disruption | PDB, rollout strategy, headroom và runbook drain |

Placement tốt là một **quyết định có ngữ cảnh**, không phải bật tất cả rule chống tập trung cùng lúc. Một hard rule ở mỗi tầng có thể làm scheduler không tìm thấy node nào thỏa tất cả điều kiện.

## 16. Đánh giá theo Well-Architected

| Trụ cột/góc nhìn | Câu hỏi về lập lịch và phân bố |
| --- | --- |
| **Operational Excellence** | Có xem được vị trí replica, Pod Pending, lý do scheduling, node drain và quy trình thay đổi không? |
| **Security** | Workload nhạy cảm có được cô lập bằng node pool, identity, network policy và quyền sửa label phù hợp không? |
| **Reliability** | Replica có phân tán qua đúng miền lỗi; PDB, storage, DNS, LB và database có chịu lỗi tương ứng không? |
| **Performance Efficiency** | Requests/limits phản ánh tải đo; locality, autoscaling, sidecar và network latency có được tính không? |
| **Cost Optimization** | Headroom có hợp lý; pack workload không critical có giúp giảm node rỗi mà vẫn không tạo điểm lỗi chung không? |
| **Sustainability** | Tài nguyên cấp phát có theo nhu cầu, tránh overprovision kéo dài và scale down an toàn không? |

### Các đánh đổi phải ghi trong ADR

- **Tăng replica và spread:** tăng khả năng chịu lỗi, nhưng tăng chi phí compute, network liên zone và có thể tăng dung lượng database.
- **Hard anti-affinity:** cô lập tốt, nhưng giảm khả năng lấp đầy node và có thể làm Pod Pending.
- **Pack:** cải thiện utilization/cost hoặc locality, nhưng tăng số workload cùng chịu ảnh hưởng khi node/zone lỗi.
- **PDB chặt:** hạn chế voluntary disruptions, nhưng kéo dài bảo trì và rollout.
- **Autoscaling nhanh:** đáp ứng đỉnh tốt hơn, nhưng có thể tạo áp lực lên quota, image registry, IP, database và chi phí.
- **Spread qua region:** tăng phạm vi chịu lỗi, nhưng phức tạp về dữ liệu, consistency, routing, quyền và kiểm thử DR.

Một ADR nên ghi bối cảnh và SLO, failure domain cần chịu, topology đã chọn, rule cứng/mềm, capacity theo tải bình thường và lúc lỗi, ảnh hưởng chi phí, phương án bị loại và điều kiện xem lại.

## 17. Bài thực hành: lập lịch và phân bố dịch vụ đặt chỗ

**Bối cảnh giả định:** cluster Kubernetes chạy trên ba availability zone. Booking API có 6 replicas, Search API có 9 replicas, Worker có 6 replicas. Mỗi node ứng dụng có 4 vCPU và 16 GiB memory. Load test cho thấy một Pod Booking API cần 500m CPU request và 512 MiB memory request; một Pod Search cần 700m CPU và 1 GiB memory. Một zone có thể bị mất trong kịch bản phục hồi. Các số liệu chỉ dùng để thực hành.

### Nhiệm vụ

1. **Vẽ sơ đồ topology:** ba zone, node pool, số node, Pod placement, storage và database; ghi rõ miền lỗi nào nhà cung cấp thật sự bảo đảm.
2. **Tính requests:** tổng CPU/memory request của Booking và Search theo số replica; tính capacity tối thiểu ở trạng thái bình thường và khi mất một zone. Bổ sung overhead cho sidecar/agent nếu có.
3. **Thiết kế scheduler rules:** chọn node affinity/selector, topology spread, anti-affinity và taints/tolerations; nêu rule nào hard, rule nào soft.
4. **Thiết kế disruption:** chọn PDB và rolling update strategy; giải thích cách drain một node mà không giảm dưới mức phục vụ đã phê duyệt.
5. **Đánh giá autoscaling:** xác định metric HPA, node autoscaling, quota cloud và thời gian cấp node; nêu nguy cơ khi Pod Pending do anti-affinity hoặc thiếu storage.
6. **Đánh giá stateful dependency:** database/queue nằm ở đâu, storage topology gì, failover và RPO/RTO được kiểm chứng ra sao?
7. **Diễn tập lỗi:** drain node, giả lập mất zone, hết quota hoặc DB failover trong môi trường thử nghiệm được phép. Ghi p95, error rate, số replicas Ready, Pod Pending và thời gian phục hồi.
8. **Viết ADR ngắn:** giải thích vì sao chọn spread/pack, hard/soft constraints, chi phí và phương án nếu một zone không có capacity.

### Tiêu chí hoàn thành

| Tiêu chí | Dấu hiệu đạt |
| --- | --- |
| Tính toán capacity | Tổng requests và headroom được tính cả trạng thái bình thường, rollout và mất zone |
| Placement khả thi | Số node/zone, label topology, affinity và storage cùng tương thích; không tạo hard rule bất khả thi |
| Chịu lỗi thực tế | Có số Pod phục vụ đủ tải sau sự cố, không chỉ đếm Pod tồn tại |
| Vận hành | PDB, drain, autoscaling, quota và runbook có thể thực thi |
| Dữ liệu | Database/storage có mô hình HA/backup độc lập và RTO/RPO được thử |
| Bằng chứng | Có kết quả load/failure test và quyết định được ghi lại |

## 18. Checklist trước khi đưa workload container vào production

- [ ] Đã định nghĩa failure domain cần chịu: container, Pod, node, rack, zone, region và dependency dùng chung.
- [ ] Đã đo CPU/memory requests/limits và tính sidecar, init container, ephemeral storage cùng tài nguyên phụ thuộc.
- [ ] Đã xác định workload nào cần spread, workload nào có thể pack và lý do nghiệp vụ.
- [ ] Đã kiểm tra topology labels chính xác ở các node và khả năng phân bố qua zone.
- [ ] Đã kiểm tra topologySpreadConstraints, affinity/anti-affinity và selector để tránh hard rule không khả thi.
- [ ] Đã rà soát taint/toleration, node pool, thiết bị chuyên dụng và quyền chỉnh sửa node labels.
- [ ] Đã kết hợp PDB, readiness/liveness/startup probes, rollout strategy và quy trình drain.
- [ ] Đã tính capacity khi mất một zone, bao gồm quota, IP, volume attach, DB, queue và thời gian autoscaling.
- [ ] Đã phân tích topology của persistent volume, database, broker và khả năng khôi phục dữ liệu.
- [ ] Đã quan sát replicas theo node/zone, Pod Pending, scheduling events, throttling, OOM và PDB disruptionsAllowed.
- [ ] Đã diễn tập lỗi node/zone, bảo trì, rolling deployment và dependency failover.
- [ ] Đã ghi ADR về reliability, performance, security, cost và operational trade-offs.

**Điểm cốt lõi:** scheduler quyết định Pod chạy ở đâu dựa trên tài nguyên và ràng buộc; topology spread/affinity điều khiển cách replicas phân bố; PDB và quy trình vận hành hạn chế gián đoạn tự nguyện. Độ tin cậy thực sự chỉ đạt được khi **compute, mạng, storage, database, quota và các dependency dùng chung** cùng được thiết kế theo failure domain và kiểm chứng bằng diễn tập thực tế.
