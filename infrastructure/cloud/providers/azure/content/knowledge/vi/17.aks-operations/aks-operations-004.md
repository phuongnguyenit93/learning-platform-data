# Scheduling bằng affinity, taint và toleration

Trong Azure Kubernetes Service (AKS), một Deployment có ba replica không có nghĩa Kubernetes sẽ tự đặt ba Pod trên ba node khác nhau. Mặc định, bộ lập lịch Kubernetes (kube-scheduler) cố gắng tìm node có thể chạy Pod dựa trên tài nguyên, ràng buộc, điều kiện node và các chính sách đang áp dụng. Nếu không chủ động thiết kế quy tắc scheduling, workload quan trọng có thể cùng nằm trên một node, workload tốn CPU có thể cạnh tranh với dịch vụ nhạy cảm độ trễ, hoặc Pod có thể bị đưa lên một node pool không phù hợp.

Kubernetes cung cấp các công cụ để kiểm soát vấn đề này:

- **Node selector và node affinity:** Pod cần hoặc ưu tiên chạy trên những node có label phù hợp.
- **Pod affinity và pod anti-affinity:** Pod có xu hướng đặt gần hoặc tách xa những Pod khác theo nhãn và topology.
- **Taint và toleration:** Node có thể từ chối hoặc đẩy ra những Pod không chấp nhận điều kiện của node; Pod khai báo toleration để được xem xét trên node đó.
- **Topology spread constraints:** yêu cầu hoặc khuyến khích dàn trải replica giữa các miền topology như node hoặc availability zone.

Trong chương **Vận hành AKS** của mô-đun CLOUD_PROVIDERS_AZURE, chủ đề này liên kết trực tiếp với Azure VM Scale Sets/node pools, Availability Zones, network topology, Azure Monitor, quyền quản trị Kubernetes và chi phí vận hành. Các quy tắc scheduling giúp triển khai ứng dụng đúng nơi, nhưng phải kết hợp với **resource requests, số lượng node, khả năng mở rộng và giám sát**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả cách kube-scheduler lọc và xếp hạng node trước khi đặt một Pod.
2. Sử dụng nodeSelector và nodeAffinity ở chế độ required hoặc preferred.
3. Sử dụng podAffinity và podAntiAffinity để đồng vị trí hoặc phân tán các replica.
4. Phân biệt các taint effect NoSchedule, PreferNoSchedule và NoExecute.
5. Viết toleration đúng key, operator, value, effect và tolerationSeconds.
6. Kết hợp node taint và node affinity để tạo pool chuyên dụng trên AKS.
7. Áp dụng topologySpreadConstraints và đánh giá ảnh hưởng đến HA theo zone.
8. Cấu hình node labels và taints tại AKS node pool, hiểu tương tác với Cluster Autoscaler.
9. Phân tích Pod Pending qua kubectl describe, Events, labels, taints và resource requests.
10. Xây dựng checklist kiểm thử, kiểm soát chi phí và kế hoạch thay đổi an toàn cho production.

Kiến thức nền nên có: Kubernetes Pod, Deployment, node, namespace, labels/selectors, Azure Kubernetes Service, AKS node pools, kubectl, Azure CLI và khái niệm CPU/memory requests. Các ví dụ tạo node pool có thể phát sinh chi phí; chỉ thực hiện trên cluster lab được phép.

## 2. Kube-scheduler quyết định node như thế nào?

### 2.1. Một Pod được lập lịch qua những bước nào?

Khi Deployment controller tạo Pod mới, Pod ban đầu thường chưa có spec.nodeName. Scheduler tìm những node đủ điều kiện, so sánh các node khả thi và gán Pod vào một node.

~~~mermaid
flowchart TD
    P["Pod mới chưa có node"] --> F["Lọc node: có thể chạy không?"]
    F --> R{"Có node hợp lệ?"}
    R -->|Không| E["Pod Pending / FailedScheduling"]
    R -->|Có| S["Chấm điểm các node hợp lệ"]
    S --> B["Bind Pod vào node được chọn"]
    B --> K["Kubelet pull image, tạo container"]
    K --> H["Pod Running / Ready nếu thành công"]
~~~

Một node có thể bị loại vì:

- Không đủ CPU/memory **theo requests đã khai báo**.
- Node bị cordon (spec.unschedulable), chưa Ready hoặc không đạt điều kiện khác.
- Có taint NoSchedule mà Pod không có toleration phù hợp.
- Không đáp ứng nodeSelector hoặc required nodeAffinity.
- Vi phạm required podAntiAffinity hoặc topology spread đặt DoNotSchedule.
- Không đáp ứng ràng buộc volume, topology, port, runtime hoặc những plugin scheduler có hiệu lực.

Sau khi lọc, scheduler dùng nhiều thành phần chấm điểm, bao gồm preferred affinity, cân bằng tài nguyên và các chính sách khác. **Preferred không có nghĩa chắc chắn được chọn**: nó tác động điểm số trong tổng thể quyết định.

### 2.2. Scheduling khác với lúc container chạy

Cần phân biệt:

| Giai đoạn | Thành phần nổi bật | Câu hỏi |
|---|---|---|
| Scheduling | kube-scheduler | Pod sẽ được gắn vào node nào? |
| Pod admission/placement constraints | Scheduler và các chính sách được cấu hình | Node này có thỏa yêu cầu và được phép nhận Pod không? |
| Container startup | kubelet/container runtime | Có pull image, mount volume, chạy process được không? |
| Readiness | Kubelet và health probes | Pod đã sẵn sàng nhận traffic chưa? |
| Eviction/rescheduling | Controllers, node controller, scheduler và cơ chế eviction | Khi node lỗi hoặc taint thay đổi, Pod bị xử lý thế nào? |

Pod đã gắn node sẽ không tự di chuyển sang node khác chỉ vì một **preferred affinity** trở nên phù hợp hơn. Ngay cả dạng **requiredDuringSchedulingIgnoredDuringExecution** cũng có chữ IgnoredDuringExecution: nếu label node đổi sau khi Pod đã chạy, Kubernetes không mặc nhiên đuổi Pod khỏi node chỉ vì ràng buộc đó không còn khớp.

Ngược lại, taint có effect NoExecute có thể ảnh hưởng cả Pod đã chạy, theo toleration tương ứng. Không nhầm NoSchedule với eviction.

### 2.3. Scheduler không dựa trực tiếp vào CPU đang sử dụng tức thời

Scheduler thường tính khả năng chứa Pod dựa trên **resource requests**, allocatable capacity và những ràng buộc đang áp dụng; CPU usage hiện tại không thay thế requests.

Ví dụ:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "1"
    memory: "1Gi"
~~~

Pod này yêu cầu scheduler dự trù 0,5 vCPU và 512 MiB cho container. Nếu không khai báo requests hợp lý, việc phân bố và quyết định mở rộng node có thể sai với tải thực tế. Ngược lại, requests quá lớn khiến Pod Pending dù CPU thực tế còn rảnh.

Affinity và toleration **không tạo thêm CPU hoặc RAM**. Chúng chỉ tác động nơi Pod được phép hoặc ưu tiên chạy.

## 3. Labels và nodeSelector: nền tảng của scheduling

### 3.1. Label là metadata dạng key/value

Node có thể có labels mô tả đặc tính:

~~~text
kubernetes.io/os=linux
kubernetes.io/arch=amd64
topology.kubernetes.io/zone=southeastasia-1
kubernetes.azure.com/agentpool=batchpool
workload=batch
team=data
~~~

Các label trên chỉ là ví dụ. Label thuộc tiền tố do hệ thống quản lý không nên bị sửa tùy tiện; label custom như workload=batch cần có quy chuẩn tổ chức và quản lý qua quy trình AKS/node pool thích hợp.

Kiểm tra node và label:

~~~bash
kubectl get nodes --show-labels

kubectl get nodes \
  -L workload,topology.kubernetes.io/zone,kubernetes.azure.com/agentpool

kubectl describe node <NODE_NAME>
~~~

Không suy ra node đã được bảo vệ chỉ vì label đặt tên là secure hoặc dedicated. Label là dữ liệu phục vụ lập lịch và tổ chức, **không phải một cơ chế xác thực**.

### 3.2. nodeSelector: điều kiện bắt buộc đơn giản

Ví dụ Pod chỉ được đặt lên node có label workload=batch:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: batch-reader
  namespace: jobs
spec:
  nodeSelector:
    workload: batch
  containers:
    - name: worker
      image: nginx:1.27
      resources:
        requests:
          cpu: "100m"
          memory: "128Mi"
~~~

Scheduler chỉ xét những node khớp tất cả key/value được khai báo trong nodeSelector. Nếu không có node nào có workload=batch, Pod sẽ Pending.

nodeSelector không cho phép điều kiện mềm hoặc nhiều toán tử linh hoạt; để làm điều đó, dùng node affinity.

### 3.3. Khi nào nodeSelector là đủ?

Dùng nodeSelector khi ràng buộc đơn giản và bắt buộc, ví dụ:

- Workload chỉ chạy trên linux.
- Workload yêu cầu node pool có label workload=etl.
- Phần mềm được chứng nhận trên một loại CPU architecture.
- Pod chỉ chạy trên node được chuẩn bị với driver/thiết bị chuyên dụng.

Nếu cần "ưu tiên node pool A, nhưng có thể chạy B khi A đầy", nodeSelector không đủ; xét preferred node affinity và các ràng buộc khác.

## 4. Node affinity: required và preferred

### 4.1. Hai loại chính

| Loại | Tác dụng khi scheduler đặt Pod | Khi node đổi label sau đó |
|---|---|---|
| requiredDuringSchedulingIgnoredDuringExecution | Điều kiện cứng: node không khớp sẽ bị loại | Pod đang chạy không tự bị đuổi chỉ vì label đổi |
| preferredDuringSchedulingIgnoredDuringExecution | Điều kiện mềm: node khớp được cộng điểm theo weight | Không tự di chuyển Pod sau khi đã đặt |

Hầu hết workload không nên dùng ràng buộc cứng theo một label dễ thay đổi trừ khi có lý do thực sự, chẳng hạn node có thiết bị bắt buộc hoặc kiểm soát tuân thủ.

### 4.2. Required node affinity

Ví dụ chỉ chạy trên node Linux được gắn workload=payments:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payments-api
  namespace: payments
spec:
  replicas: 2
  selector:
    matchLabels:
      app: payments-api
  template:
    metadata:
      labels:
        app: payments-api
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: workload
                    operator: In
                    values: ["payments"]
                  - key: kubernetes.io/os
                    operator: In
                    values: ["linux"]
      containers:
        - name: api
          image: "<REGISTRY>/payments-api:<VERSION>"
          resources:
            requests:
              cpu: "300m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
~~~

Điều kiện trong **một** nodeSelectorTerm được kết hợp theo AND; các nodeSelectorTerms khác nhau được kết hợp theo OR. Do đó ví dụ yêu cầu workload=payments **và** os=linux.

Nếu không có node phù hợp, Pod **không** tự bỏ qua required rule để chạy tạm trên pool khác.

### 4.3. Các toán tử matchExpressions

| Operator | Ý nghĩa |
|---|---|
| In | Giá trị label thuộc danh sách values |
| NotIn | Giá trị không thuộc danh sách (và phù hợp semantics selector) |
| Exists | Label key tồn tại |
| DoesNotExist | Label key không tồn tại |
| Gt | So sánh số nguyên dạng chuỗi theo cơ chế selector |
| Lt | So sánh số nguyên dạng chuỗi theo cơ chế selector |

Ví dụ:

~~~yaml
nodeSelectorTerms:
  - matchExpressions:
      - key: disk
        operator: In
        values: ["ssd", "nvme"]
      - key: workload
        operator: Exists
  - matchExpressions:
      - key: workload
        operator: In
        values: ["fallback-batch"]
~~~

Đoạn trên chọn node thỏa (disk là ssd/nvme **và** có workload label) **hoặc** workload=fallback-batch. Chỉ dùng như một phần của trường requiredDuringSchedulingIgnoredDuringExecution, không phải manifest đầy đủ.

Toán tử NotIn không hoàn toàn giống việc chứng minh môi trường đã được xác thực; khi cần bảo đảm node thuộc nhóm tin cậy, dùng label được quản lý và bảo vệ phù hợp.

### 4.4. Preferred node affinity

Ví dụ ưu tiên node có nhãn performance=high hoặc workload=shared nhưng vẫn cho chạy node khác nếu cần:

~~~yaml
affinity:
  nodeAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 80
        preference:
          matchExpressions:
            - key: performance
              operator: In
              values: ["high"]
      - weight: 20
        preference:
          matchExpressions:
            - key: workload
              operator: In
              values: ["shared"]
~~~

weight thường nhận giá trị từ 1 đến 100 cho mỗi preferred term. Các node khớp term được cộng điểm trong plugin tương ứng; điểm này vẫn được kết hợp với các yếu tố scheduler khác.

**Không hiểu weight 80 là 80% Pod sẽ được đặt lên loại node đó**. Nó là trọng số chấm điểm, không phải tỷ lệ chia traffic hay xác suất định lượng.

### 4.5. nodeSelector và nodeAffinity có thể dùng cùng lúc

Nếu Pod có cả nodeSelector và required nodeAffinity, node phải thỏa **cả hai**. Những ràng buộc khác như taints, tài nguyên và topology vẫn áp dụng.

Ví dụ rất dễ tạo mâu thuẫn:

~~~yaml
nodeSelector:
  workload: payments
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: workload
              operator: In
              values: ["batch"]
~~~

Node không thể đồng thời có workload=payments và workload=batch cho cùng key, nên Pod sẽ Pending. Trước khi deploy, kiểm tra các điều kiện hard có mâu thuẫn hay không.

## 5. Pod affinity và pod anti-affinity

### 5.1. Khi cần đặt các Pod gần nhau

**Pod affinity** cho phép một Pod yêu cầu hoặc ưu tiên ở cùng miền topology với các Pod có label nhất định.

Ví dụ một workload xử lý batch muốn ở cùng node với cache helper đã được gắn label app=cache-local:

~~~yaml
affinity:
  podAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 80
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app: cache-local
          topologyKey: kubernetes.io/hostname
~~~

Ở đây miền topology là **node** (hostname). Với preferred rule, scheduler có thể chọn node khác nếu node gần cache không phù hợp. Để yêu cầu cứng, thay bằng requiredDuringSchedulingIgnoredDuringExecution với cấu trúc list của PodAffinityTerm theo Kubernetes schema.

Đặt Pod cùng node có thể giảm latency khi có lợi thế node-local, nhưng cũng tạo điểm lỗi chung: mất một node sẽ mất cả hai Pod. Cân nhắc đây có phải yêu cầu thực sự của hệ thống hay không.

### 5.2. Pod anti-affinity cho high availability

**Pod anti-affinity** cố tách các Pod có label giống nhau ra những miền topology khác nhau. Ví dụ hai replica orders-api không nên cùng một node.

~~~yaml
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app: orders-api
          topologyKey: kubernetes.io/hostname
~~~

Cấu hình trên **ưu tiên** không cùng node, nhưng vẫn cho chạy cùng node nếu cluster thiếu node hoặc có những ưu tiên khác. Nó hữu ích khi cần tránh Pod Pending trong môi trường nhỏ.

Cấu hình cứng:

~~~yaml
affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            app: orders-api
        topologyKey: kubernetes.io/hostname
~~~

Nếu có ba replica nhưng chỉ có hai node phù hợp và mỗi node đã chứa một replica, replica thứ ba có thể Pending. Đây là kết quả đúng với hard anti-affinity, không phải lỗi ngẫu nhiên của scheduler.

### 5.3. topologyKey và phạm vi Pod được so sánh

Các topologyKey thường gặp:

- **kubernetes.io/hostname:** theo node.
- **topology.kubernetes.io/zone:** theo Availability Zone khi node thực sự được gắn label phù hợp.
- **topology.kubernetes.io/region:** theo region, thường ít có ích trong một AKS cluster đơn region.

Pod affinity/anti-affinity có **labelSelector** để chọn Pod đối chiếu; phạm vi namespace của những Pod đó có thể được cấu hình bằng namespaces hoặc namespaceSelector theo nhu cầu và tính năng.

Nếu bỏ qua phạm vi namespace, semantics mặc định có thể chỉ xét namespace của Pod hiện tại. Khi cần tránh kết hợp Pod ở nhiều namespace, cần chủ động khai báo phạm vi, không kỳ vọng bộ lập lịch tự xét mọi namespace.

### 5.4. Không phải cứ required anti-affinity là HA tốt hơn

Ràng buộc cứng có thể giúp tách replica nhưng làm giảm khả năng phục hồi khi mất node. Ví dụ:

- Cluster chỉ còn một node vì sự cố.
- Required anti-affinity không cho replica thứ hai chạy trên node còn lại.
- Workload chỉ còn một replica Ready, tăng rủi ro nếu node tiếp tục quá tải.

Khi mục tiêu là "cố gắng phân tán" và vẫn ưu tiên availability, dùng **preferred anti-affinity** hoặc **topology spread constraints với chính sách thích hợp** thường linh hoạt hơn.

## 6. Taint và toleration: node từ chối, Pod chấp nhận

### 6.1. Taint đặt trên node

Taint là thuộc tính của node, thường biểu diễn như:

~~~text
key=value:Effect
~~~

Ví dụ:

~~~text
workload=payments:NoSchedule
dedicated=gpu:NoSchedule
maintenance=true:PreferNoSchedule
draining=true:NoExecute
~~~

Scheduler và các thành phần điều khiển xét taint khi quyết định Pod được vào hoặc tiếp tục ở node.

**Toleration nằm ở Pod**, khai báo Pod chấp nhận một taint cụ thể. Toleration **không phải yêu cầu placement**, không cấp thêm CPU và không tăng quyền bảo mật. Nó chỉ loại bỏ tác dụng ngăn cản của taint tương ứng đối với Pod đó.

### 6.2. Ba effect phải nhớ

| Effect | Pod không có toleration phù hợp | Tác dụng với Pod đã chạy |
|---|---|---|
| NoSchedule | Không được schedule mới lên node | Không tự evict Pod đang chạy chỉ vì vừa thêm NoSchedule |
| PreferNoSchedule | Scheduler cố tránh, nhưng có thể vẫn schedule khi cần | Không phải cơ chế eviction |
| NoExecute | Không được schedule mới và có thể bị evict | Có thể đẩy Pod hiện hữu ra nếu không tolerate |

Đặc biệt với NoExecute, thời gian và phương thức eviction còn chịu cơ chế quản lý node/taint và trạng thái runtime. Không đồng nhất mọi trường hợp evict với một thao tác dừng container tức thì hoặc bảo đảm graceful shutdown bất kể node có còn kết nối.

### 6.3. Toleration dạng Equal

Ví dụ Pod chấp nhận taint workload=payments:NoSchedule:

~~~yaml
tolerations:
  - key: workload
    operator: Equal
    value: payments
    effect: NoSchedule
~~~

Pod **có thể** được schedule lên node đó nếu các điều kiện khác đều thỏa. Nó cũng có thể chạy trên node **không có taint đó**, nếu không có ràng buộc placement khác.

Ví dụ phản chứng:

~~~text
Node A: workload=payments:NoSchedule
Node B: không có taint

Pod có toleration payments, không có nodeAffinity.
→ Pod có thể được đặt trên A hoặc B.
~~~

Kết luận: muốn dành riêng pool payments, thường phải kết hợp **taint trên pool + toleration trong Pod + required nodeAffinity/nodeSelector**.

### 6.4. Toleration với Exists

Một toleration không cần so sánh value có thể dùng Exists:

~~~yaml
tolerations:
  - key: dedicated
    operator: Exists
    effect: NoSchedule
~~~

Điều này cho phép Pod tolerate những NoSchedule taints có key dedicated, bất kể value. Phải hiểu rõ phạm vi trước khi dùng.

Một toleration quá rộng với operator Exists, không giới hạn key/effect, có thể khiến Pod bỏ qua nhiều taint không mong muốn và chạy ở node được dành riêng hoặc đang gặp sự cố. **Không dùng toleration wildcard rộng rãi cho ứng dụng production** trừ khi thực sự có lý do và đã đánh giá bảo mật/vận hành.

### 6.5. Nhiều taints phải được xét cùng nhau

Nếu node có:

~~~text
workload=payments:NoSchedule
compliance=restricted:NoSchedule
~~~

mà Pod chỉ tolerate workload=payments, node vẫn bị ngăn do compliance=restricted. Tất cả taint **có effect ngăn cản liên quan** phải được xử lý phù hợp để node trở thành ứng viên.

Không phải "Pod có ít nhất một toleration" là đủ: mỗi taint có thể tạo một rào cản riêng.

### 6.6. NoExecute và tolerationSeconds

NoExecute đặc biệt hữu ích để mô hình hóa trường hợp Pod không còn được phép **ở lại** node khi điều kiện thay đổi.

~~~yaml
tolerations:
  - key: node.kubernetes.io/not-ready
    operator: Exists
    effect: NoExecute
    tolerationSeconds: 120
~~~

Ý nghĩa: khi taint NotReady tương ứng được áp dụng, Pod có thể chịu đựng trong thời hạn chỉ định theo semantics của hệ thống; khi hết thời gian và điều kiện vẫn tồn tại, Pod có thể bị eviction.

Nếu Pod có NoExecute toleration phù hợp nhưng **không** có tolerationSeconds, về nguyên tắc nó có thể tolerate taint đó vô thời hạn. Điều này không đảm bảo Pod còn có thể phục vụ nếu node thực sự chết hoặc mất liên lạc.

Nhiều Pod thông thường nhận sẵn tolerations cho các tình trạng not-ready và unreachable thông qua cơ chế mặc định của Kubernetes; giá trị mặc định thường là khoảng 300 giây trong cấu hình phổ biến, nhưng admission/controller và workload đặc biệt có thể khác. Kiểm tra Pod thực tế:

~~~bash
kubectl get pod <POD_NAME> -n <NAMESPACE> \
  -o jsonpath='{.spec.tolerations}'
~~~

### 6.7. Taint không phải cơ chế bảo mật tuyệt đối

Một Pod mà người dùng có quyền chỉnh manifest có thể tự thêm toleration. Vì vậy chỉ dùng taint để **điều phối workload** là đúng; không xem taint thay thế RBAC, admission policy, NetworkPolicy, pod security, node isolation hoặc kiểm soát truy cập dữ liệu.

Với node chứa workload tuân thủ cao, cần bổ sung kiểm soát để người không được phép không thể tạo Pods với nhãn/affinity/toleration đưa chúng vào vùng riêng.

## 7. So sánh nodeAffinity, podAntiAffinity và taints

| Công cụ | Khai báo ở đâu? | Câu hỏi chính | Có bắt buộc không? |
|---|---|---|---|
| nodeSelector | Pod spec | Pod phải chạy trên node có label nào? | Có |
| required nodeAffinity | Pod spec | Những node nào hợp lệ theo biểu thức label? | Có |
| preferred nodeAffinity | Pod spec | Ưu tiên loại node nào? | Không |
| podAffinity | Pod spec | Pod nên/gặp điều kiện phải ở gần Pod nào? | Tùy required/preferred |
| podAntiAffinity | Pod spec | Pod nên/gặp điều kiện phải tránh ở gần Pod nào? | Tùy required/preferred |
| Node taint | Node / AKS node pool | Pod không phù hợp có nên bị ngăn hoặc evict? | Tùy effect |
| Pod toleration | Pod spec | Pod chấp nhận taint nào? | Không tự tạo yêu cầu đặt node |
| topologySpreadConstraints | Pod spec | Replica dàn trải giữa node/zone ra sao? | Tùy whenUnsatisfiable |

Ghi nhớ bằng một câu:

**Affinity thu hút hoặc ràng buộc Pod đến một nhóm node/Pod; taint đẩy Pod không phù hợp ra khỏi nhóm node; toleration chỉ cho phép vượt rào cản do taint tạo ra.**

## 8. AKS node pools: nơi quản trị labels và taints

### 8.1. System node pool và User node pool

AKS tổ chức các worker nodes thành **node pools**, thường được vận hành trên hạ tầng VM Scale Sets. Có những node pool ở mode System và User:

- **System pool:** dành để hỗ trợ các workload hệ thống thiết yếu của cluster theo nguyên tắc vận hành AKS.
- **User pool:** dành cho workloads ứng dụng; có thể tách theo CPU/memory/GPU, Spot hoặc yêu cầu bảo mật.

**Mode=System không phải ranh giới scheduling tuyệt đối.** Nếu không có taint/affinity tương ứng, các workload khác vẫn có thể được xét trên nodes tùy cấu hình cluster. Để bảo vệ workload hệ thống hoặc tạo pool chuyên dụng, cần xem labels, taints, resource requests và capacity.

Không gán bừa taint cho system pool mà chưa kiểm tra các add-ons, DaemonSets và workload hệ thống có toleration cần thiết hay không. Việc chặn Pod hệ thống có thể khiến DNS, network hoặc monitoring hoạt động sai.

### 8.2. Tạo User node pool có label và taint

Giả sử cluster lab aks-scheduling-lab tồn tại và có đủ quota. Ta muốn một pool riêng cho batch workers:

~~~bash
az account show --output table

az aks nodepool add \
  --resource-group rg-aks-lab \
  --cluster-name aks-scheduling-lab \
  --name batchpool \
  --mode User \
  --node-count 2 \
  --node-vm-size Standard_D4s_v5 \
  --labels workload=batch team=data \
  --node-taints workload=batch:NoSchedule
~~~

Tác dụng mong đợi:

- Nodes trong batchpool mang label workload=batch.
- Nodes có taint workload=batch:NoSchedule.
- Các Pods không tolerate taint sẽ tránh được việc schedule mới vào pool.
- Workload batch có toleration và node affinity tương ứng mới có khả năng vào pool, nếu đủ tài nguyên và các điều kiện khác.

Các tham số, quota, node pool name limit, VM size/region và khả năng taint/label khi thêm pool phải được kiểm tra theo Azure CLI/AKS hiện hành. Nếu production dùng autoscaler, chọn min/max count và autoscaling settings theo nhu cầu, không giữ một pool tốn phí chỉ vì ví dụ có node-count 2.

### 8.3. Vì sao nên cấu hình trên node pool?

Có thể thay đổi một node bằng kubectl:

~~~bash
kubectl label node <NODE_NAME> workload=batch --overwrite

kubectl taint node <NODE_NAME> workload=batch:NoSchedule
~~~

Nhưng với AKS, node có thể bị thay thế khi nâng cấp, autoscale hoặc repair. Nhãn/taint được gán thủ công chỉ lên một node có thể không được giữ như ý trên node thay thế. Vì vậy nên khai báo trong **AKS node pool configuration** hoặc cơ chế quản trị bền vững được hỗ trợ.

Trước khi đổi taint cho pool đang phục vụ production, cần kiểm tra rủi ro Pod Pending, DaemonSets, khả năng thay node/rolling operation và cách rollback. Không tự thêm NoExecute vào pool production chỉ để thử nghiệm.

### 8.4. Liệt kê node pools và labels

~~~bash
az aks nodepool list \
  --resource-group rg-aks-lab \
  --cluster-name aks-scheduling-lab \
  --output table

az aks nodepool show \
  --resource-group rg-aks-lab \
  --cluster-name aks-scheduling-lab \
  --name batchpool \
  --output json

kubectl get nodes \
  -L workload,kubernetes.azure.com/agentpool

kubectl describe node <NODE_NAME>
~~~

Xác minh từ cả **Azure node pool configuration** và **thực tế Kubernetes node objects**. Một task Azure báo Succeeded không bảo đảm toàn bộ nodes đã Ready hoặc Pod đã schedule đúng.

## 9. Thực hành: kết hợp affinity và toleration trên AKS

### 9.1. Bài toán

Một nhóm Data Engineering cần chạy Job/Deployment xử lý dữ liệu trên batchpool. Mục tiêu:

1. Các workload ứng dụng khác không được schedule mới vào batchpool nếu không được phép.
2. Pod batch phải được đặt **trên batchpool**, không chạy trên systempool.
3. Khi batchpool thiếu node/capacity, Pod được Pending để autoscaler hoặc người vận hành bổ sung tài nguyên; không âm thầm lấn sang pool sai.
4. Worker có CPU/memory requests rõ ràng để scheduler và autoscaler đánh giá.

Giả định node pool đã có:

~~~text
Label: workload=batch
Taint: workload=batch:NoSchedule
~~~

### 9.2. Deployment hoàn chỉnh

Ví dụ ứng dụng worker giả định có image đã tồn tại:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: batch-worker
  namespace: jobs
  labels:
    app: batch-worker
spec:
  replicas: 2
  selector:
    matchLabels:
      app: batch-worker
  template:
    metadata:
      labels:
        app: batch-worker
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: workload
                    operator: In
                    values: ["batch"]
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app: batch-worker
                topologyKey: kubernetes.io/hostname
      tolerations:
        - key: workload
          operator: Equal
          value: batch
          effect: NoSchedule
      containers:
        - name: worker
          image: "<REGISTRY>/batch-worker:<VERSION>"
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
~~~

Trước khi áp dụng, tạo namespace jobs theo quy trình có quyền, thay image bằng image hợp lệ và kiểm tra security context, config, secrets, probes và volume theo ứng dụng.

**Giải thích:**

- required nodeAffinity buộc Pod lên node workload=batch.
- toleration cho phép Pod đi qua NoSchedule taint workload=batch.
- preferred podAntiAffinity cố gắng đặt các replica khác node nhưng không chặn schedule khi chỉ còn một node có capacity.
- resources.requests giúp scheduler và autoscaler nhận diện nhu cầu của worker.

Nếu thiếu **toleration**, Pod có thể bị ngăn bởi taint dù label phù hợp.

Nếu thiếu **nodeAffinity**, Pod có thể chạy trên node thường không bị taint, trái yêu cầu dedicated pool.

Nếu chỉ có **podAntiAffinity**, Pod cố tách khỏi Pod cùng nhãn nhưng không đảm bảo dùng đúng node pool.

### 9.3. Triển khai và kiểm tra

Giả sử manifest đã được nhóm phát triển lưu thành batch-worker.yaml ở môi trường thử nghiệm:

~~~bash
kubectl apply -f batch-worker.yaml

kubectl get pods -n jobs -o wide

kubectl describe pod <POD_NAME> -n jobs

kubectl get nodes \
  -L workload,kubernetes.azure.com/agentpool
~~~

Cột NODE từ kubectl get pods -o wide cho biết node thực sự chạy Pod. So sánh label và taint của node đó với quy tắc trong Pod spec.

Trong production, nên quản lý manifest bằng GitOps hoặc pipeline có kiểm tra policy và approval, không thao tác thủ công không có audit trail.

### 9.4. Kiểm tra rủi ro placement sai

Tạo một Pod không có toleration nhưng có nodeSelector workload=batch trên lab. Kỳ vọng nó bị Pending nếu tất cả nodes khớp workload=batch đều có taint tương ứng.

Thông báo từ Events có thể có dạng:

~~~text
0/5 nodes are available:
2 node(s) had untolerated taint {workload: batch},
3 node(s) didn't match Pod's node affinity/selector.
~~~

Đây là ví dụ minh họa, không phải log thật của cluster. Nó cho thấy hai lý do loại node khác nhau; scheduler có thể tổng hợp nhiều lý do.

Không để Pod thử nghiệm Pending vô thời hạn trong production nếu monitoring và autoscaler có thể coi đây là workload cần bổ sung node.

## 10. Dàn trải replica với topology spread constraints

### 10.1. Vì sao cần topology spread?

Pod anti-affinity có thể giúp tránh đồng vị trí, nhưng với nhiều replica và nhiều availability zones, **topologySpreadConstraints** là công cụ được thiết kế riêng để kiểm soát độ lệch phân bổ.

Giả sử ba replica orders-api cần dàn trải giữa các zone của AKS cluster. Điều này hữu ích khi các zone và nodes tương ứng **thật sự tồn tại**, được scheduler nhìn thấy bằng labels.

### 10.2. Ý nghĩa của maxSkew và whenUnsatisfiable

| Trường | Ý nghĩa |
|---|---|
| topologyKey | Label node dùng làm miền phân bổ, ví dụ topology.kubernetes.io/zone |
| maxSkew | Giới hạn chênh lệch số Pod phù hợp giữa các miền theo semantics của scheduler |
| whenUnsatisfiable=DoNotSchedule | Từ chối schedule Pod nếu placement vi phạm điều kiện spread |
| whenUnsatisfiable=ScheduleAnyway | Vẫn cho phép schedule, dùng spread làm ưu tiên |
| labelSelector | Chọn tập Pod được tính trong phân bố |
| minDomains | Tùy chọn có semantics riêng khi miền hợp lệ ít hơn mức yêu cầu, dùng khi thật sự cần |

Đừng nhầm maxSkew=1 với "mỗi zone đúng một Pod" trong mọi trường hợp: kết quả phụ thuộc số replica, số miền hợp lệ, những Pods đang tồn tại, khả năng node nhận Pod và các điều kiện placement khác.

### 10.3. Ví dụ spread theo availability zone

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: orders-api
      containers:
        - name: api
          image: "<REGISTRY>/orders-api:<VERSION>"
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
~~~

Tình huống minh họa này giả định pool được cấu hình nhiều zone có node Ready và tài nguyên đủ. Nếu cụm chỉ một zone, cấu hình không tự tạo thêm vùng; HA đa zone cần node pools, zone support và capacity có thật.

Với những hệ thống ưu tiên phục vụ hơn là spread tuyệt đối, cân nhắc ScheduleAnyway và kết hợp podAntiAffinity preferred để giảm nguy cơ Pending khi một zone mất node.

### 10.4. Kết hợp spread theo zone và hostname

Có thể dùng nhiều constraints, ví dụ phân bố replica giữa zone và giữa node. Tuy nhiên, các ràng buộc **đều phải được thỏa** khi là DoNotSchedule, vì vậy kết hợp quá cứng có thể khiến cluster hết node hợp lệ.

Khi dùng những tùy chọn nâng cao như nodeAffinityPolicy và nodeTaintsPolicy, cần hiểu tập node đủ điều kiện được tính trong phép đo skew. Nếu taint và affinity loại bớt nodes/zones, việc nhìn số lượng Pods đơn thuần có thể không giải thích được quyết định scheduler.

### 10.5. Topology không phải bảo đảm tự khôi phục

Dàn trải Pod theo zone chưa đủ để ứng dụng HA nếu:

- Database chỉ có một instance/zone.
- PersistentVolume có zone affinity chỉ cho một vùng.
- Load balancer hoặc DNS/ingress không đạt yêu cầu HA.
- Pod không có readiness/liveness probes.
- Thiếu replica hoặc node capacity.
- Deployment rollout/PDB không cho phép thay thế Pod đúng kỳ vọng.

Scheduling là một phần của HA, không thay thế thiết kế dữ liệu và phụ thuộc dịch vụ.

## 11. Scheduling và AKS Cluster Autoscaler

### 11.1. Pod Pending có thể kích hoạt nhu cầu scale

AKS có thể dùng **Cluster Autoscaler** cho node pools được cấu hình hỗ trợ. Khi có Pod Pending vì không đủ node phù hợp, autoscaler đánh giá khả năng tăng số node ở các pool phù hợp với ràng buộc Pod.

Ví dụ:

~~~text
Pod yêu cầu:
  nodeAffinity: workload=batch
  toleration: workload=batch:NoSchedule
  cpu request: 500m

AKS batchpool:
  label: workload=batch
  taint: workload=batch:NoSchedule
  autoscaler: enabled, min=1, max=5
~~~

Khi pool đã đầy, autoscaler có thể cân nhắc tăng batchpool nếu quota, giới hạn max count, khả năng cấp phát VM và những điều kiện khác cho phép.

Nếu Pod yêu cầu label **không tồn tại ở bất kỳ pool có thể scale nào**, việc tăng systempool có thể không giúp; Pod vẫn Pending. Tương tự, Pod thiếu toleration phù hợp có thể không được autoscaler giải quyết chỉ bằng thêm nhiều node có cùng taint.

### 11.2. Các giới hạn cần hiểu

- Autoscaler không bảo đảm cấp node ngay lập tức; Azure VM provision cần thời gian.
- Max node count, subscription quota, region capacity và network IP có thể chặn scale.
- Scale-from-zero cần node pool template/labels/taints phù hợp để autoscaler biết Pod có thể chạy trên node mới.
- Một ràng buộc hard rất hẹp có thể khiến không pool nào là ứng viên.
- Workload có resource requests lớn hơn khả năng một node trong pool vẫn không schedule được dù thêm node.
- PVC có zone affinity hoặc node constraints có thể hạn chế lựa chọn pool.
- Drain/scale-down còn chịu tác động của PodDisruptionBudget, workload state và system Pods.

Đừng khắc phục một Pod Pending bằng cách tự động tăng maxCount trên mọi pool nếu yêu cầu placement đang sai.

### 11.3. HPA và Cluster Autoscaler làm việc ở hai cấp

| Cơ chế | Điều chỉnh | Điều cần có |
|---|---|---|
| Horizontal Pod Autoscaler (HPA) | Số replica Pod theo metric/policy | Metric, requests phù hợp và khả năng schedule Pod |
| Cluster Autoscaler | Số node trong pool để đáp ứng nhu cầu Pod | Pool có thể scale và Pod có placement constraints hợp lệ |
| Manual node pool scaling | Người vận hành thay đổi capacity | Quota, ngân sách, approval và quan sát |

Ví dụ HPA tăng orders-api từ 3 lên 9 replica. Nếu required anti-affinity đòi một Pod trên mỗi node nhưng chỉ có ba node và autoscaler không thể thêm node, các Pod mới sẽ Pending dù HPA hoạt động đúng.

### 11.4. Node Auto Provisioning

AKS có thể có các chế độ **Node Auto Provisioning** theo tính năng hỗ trợ, với cơ chế lựa chọn/provision capacity khác node pool autoscaling truyền thống. Khi sử dụng, kiểm tra tương thích của labels, taints, disruption và policy với hệ thống provisioner được triển khai. Không áp dụng nguyên xi tất cả tham số và giả định của Cluster Autoscaler vào một cluster dùng chế độ tự cấp node khác.

## 12. Spot node pools: tận dụng chi phí mà không đánh đổi workload quan trọng

AKS hỗ trợ các kịch bản **Spot node pool** theo VM availability và chính sách dịch vụ. Spot có chi phí hấp dẫn cho job chịu gián đoạn, nhưng có thể bị Azure thu hồi capacity.

### 12.1. Thiết kế để batch chấp nhận bị ngắt

Với batch/CI jobs không cần availability tuyệt đối:

- Dùng pool riêng có label nhận diện Spot và các taints do AKS quản lý hoặc do tổ chức thêm theo chính sách.
- Workload cần Spot có toleration phù hợp và affinity nếu muốn placement cứng.
- Job phải idempotent, có checkpoint/retry và lưu dữ liệu ra dịch vụ bền vững.
- Không phụ thuộc vào local ephemeral disk như nguồn dữ liệu duy nhất.
- Có pool on-demand fallback nếu nghiệp vụ yêu cầu, nhưng phải thiết kế ràng buộc mềm/cứng tương ứng.
- Giám sát eviction, completion rate và chi phí thực tế.

Một số cấu hình Spot node pool AKS có taint hệ thống như:

~~~text
kubernetes.azure.com/scalesetpriority=spot:NoSchedule
~~~

Không tự đổi/xóa taint do nền tảng quản lý. Kiểm tra giá trị thực tế bằng kubectl describe node và tài liệu AKS cho loại pool đang dùng.

### 12.2. Toleration không chống Spot eviction

Toleration của taint Spot chỉ cho phép Pod được đặt vào node Spot. **Nó không ngăn Azure thu hồi Spot VM vì capacity hoặc chính sách giá.** Pod có thể bị gián đoạn bất chấp toleration.

Với API thanh toán hoặc hệ thống giao dịch cần availability cao, không nên chọn Spot làm node duy nhất. Kết hợp on-demand pools và ưu tiên/HA theo yêu cầu.

### 12.3. Fallback không hoạt động nếu hard affinity khóa vào Spot

Ví dụ Pod có nodeSelector spot=true và toleration Spot. Khi Spot pool không còn node, Pod không thể chạy on-demand pool dù có tài nguyên.

Để cho phép fallback, cần cân nhắc preferred nodeAffinity và những điều kiện riêng của các pool; đồng thời bảo đảm Pod có thể nhận các taints thích hợp và chính sách cost/availability được kiểm soát. Preferred không đảm bảo scheduler sẽ chọn Spot trước trong mọi tình huống.

## 13. Priority, preemption và PodDisruptionBudget

### 13.1. PriorityClass và preemption

Kubernetes hỗ trợ Pod priority. Khi Pod priority cao không thể schedule vì tài nguyên, preemption có thể cho phép loại Pod priority thấp hơn trong một số tình huống.

Tuy nhiên, **preemption không giải quyết mọi ràng buộc**:

- Không khiến node sai label thỏa required nodeAffinity.
- Không tự thêm toleration cho Pod.
- Không tạo node trong zone chưa tồn tại.
- Không làm PVC có zone khác di chuyển được.
- Không vượt được network/permission policy.

Không lạm dụng PriorityClass cao cho mọi workload; một cluster nơi mọi Pod đều ưu tiên cao sẽ khó phân biệt tác vụ quan trọng.

### 13.2. PodDisruptionBudget (PDB)

PDB giúp hạn chế **voluntary disruptions** như những cuộc drain/evict được thực hiện qua quy trình hỗ trợ, để duy trì số Pod khả dụng nhất định.

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
  namespace: orders
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-api
~~~

PDB không biến scheduler thành hệ thống tự dàn trải Pod. Nó cũng không ngăn được mọi sự cố node bất ngờ, Spot VM eviction ở tầng hạ tầng hoặc crash ứng dụng. Khi có ba replica và minAvailable=2, cần kiểm tra khả năng drain node, readiness và thực tế phân bố replica.

Một PDB quá chặt trong cluster ít node có thể khiến bảo trì hoặc nâng cấp bị kẹt. Hãy thử kết hợp PDB, affinity và autoscaling thay vì cấu hình độc lập.

## 14. Bảo mật và governance cho scheduling

### 14.1. Ai được thay đổi taint, label hoặc affinity?

Các thao tác sau có thể ảnh hưởng lớn tới production:

- Thay đổi label/taint của node hoặc AKS node pool.
- Sửa Deployment/DaemonSet/Job và các điều kiện affinity.
- Gắn toleration rộng cho workload không được phép.
- Tạo Pod có priority rất cao.
- Tạo privileged Pod hoặc Pod có host access trên node chuyên dụng.

Phân quyền bằng Kubernetes RBAC và Azure RBAC ở phạm vi phù hợp. Không để mọi team ứng dụng có quyền sửa Node object hoặc AKS node pool production.

### 14.2. Label không phải lớp bảo mật cứng

Kubernetes có những cơ chế hạn chế việc kubelet tự sửa một số node labels với tiền tố được bảo vệ, chẳng hạn **node-restriction.kubernetes.io/** khi Node authorizer và NodeRestriction admission plugin được cấu hình đúng. Đây là lựa chọn cần xem khi các label được dùng cho **node isolation** tin cậy.

Trong môi trường AKS, kiểm tra những cơ chế nào được nền tảng quản lý và hỗ trợ; không tự giả định có thể đổi cấu hình control plane admission. Với node isolation có yêu cầu tuân thủ cao, cần kết hợp label được bảo vệ, policy admission, phân quyền node/pod, network segmentation và kiểm soát runtime.

Taint và affinity không che giấu secrets, không chặn network traffic giữa Pods và không thay thế Pod Security Admission hoặc Kubernetes NetworkPolicy.

### 14.3. Kiểm soát cấu hình bằng GitOps/IaC

Một mô hình đáng tin cậy:

1. AKS node pools, labels và taints được mô tả bằng Bicep/Terraform hoặc phương án quản trị được hỗ trợ.
2. Workloads khai báo affinity/tolerations trong Helm/Kustomize/YAML được review.
3. CI kiểm tra schema, policy, resource requests và khả năng tương thích giữa pool và workload.
4. Changes yêu cầu approval cho production.
5. Sau deploy, kiểm tra Pod distribution, Pending events, node health và ngân sách.
6. Theo dõi drift khi ai đó chỉnh node/pod thủ công.

Tách quyền thay đổi hạ tầng node pools khỏi quyền phát hành ứng dụng là cách giảm rủi ro thay đổi scheduling ngoài ý muốn.

## 15. Chẩn đoán Pod Pending và FailedScheduling

### 15.1. Bắt đầu từ đúng Pod

~~~bash
kubectl get pods -A -o wide

kubectl describe pod <POD_NAME> -n <NAMESPACE>

kubectl get events -n <NAMESPACE> \
  --sort-by=.metadata.creationTimestamp
~~~

Tìm các sự kiện có reason **FailedScheduling**, đọc thông báo của scheduler. Số node không khả dụng và những lý do loại node thường giúp tách lỗi resource, taint, affinity, topology và volume.

Ví dụ các thông báo mang tính minh họa:

~~~text
0/4 nodes are available:
2 node(s) had untolerated taint {dedicated: gpu},
2 node(s) didn't match Pod's node affinity/selector.

0/5 nodes are available:
3 Insufficient cpu,
2 Insufficient memory.

0/3 nodes are available:
3 node(s) didn't match pod topology spread constraints.

0/4 nodes are available:
2 node(s) had volume node affinity conflict.
~~~

Không sửa vội bằng cách xóa tất cả ràng buộc. Mỗi thông báo có nguyên nhân khác nhau.

### 15.2. Kiểm tra node labels và taints

~~~bash
kubectl get nodes -o wide

kubectl get nodes \
  -L workload,topology.kubernetes.io/zone,kubernetes.azure.com/agentpool

kubectl describe node <NODE_NAME>
~~~

Trong phần Taints và Labels, đối chiếu với Pod spec:

- Node có đúng label value không?
- Node có một hoặc nhiều taints mà Pod chưa tolerate?
- Node ở đúng zone và network segment không?
- Node có Ready và không bị cordon?
- Node allocatable resources và số requests đã chiếm là bao nhiêu?

### 15.3. Kiểm tra Pod spec thực tế

~~~bash
kubectl get pod <POD_NAME> -n <NAMESPACE> \
  -o yaml
~~~

Quan sát:

- spec.nodeSelector.
- spec.affinity.nodeAffinity, podAffinity, podAntiAffinity.
- spec.tolerations.
- spec.topologySpreadConstraints.
- spec.containers[].resources.
- spec.volumes và PVC.
- spec.priorityClassName.
- metadata labels dùng trong selector.

Manifest source có thể khác Pod thực tế sau admission/mutating webhook hoặc sau Helm templating. Khi điều tra, so sánh **manifest đã deploy** với Pod object thực tế, không chỉ file trong Git.

### 15.4. Kiểm tra nguồn capacity từ AKS

~~~bash
az aks nodepool list \
  --resource-group rg-aks-lab \
  --cluster-name aks-scheduling-lab \
  --output table

az aks nodepool show \
  --resource-group rg-aks-lab \
  --cluster-name aks-scheduling-lab \
  --name batchpool \
  --output json
~~~

Nếu autoscaler được bật, xem giới hạn min/max, node pool labels/taints, quota và events liên quan. Một Pod quá lớn cho bất kỳ VM SKU nào của pool sẽ không giải quyết được bằng thêm số lượng node.

### 15.5. Phân loại và xử lý

| Lỗi chính | Hướng xử lý hợp lý | Không nên làm |
|---|---|---|
| Untolerated taint | Xác nhận Pod có được phép vào pool không; thêm toleration cụ thể nếu đúng | Thêm Exists wildcard cho mọi Pod |
| No node matches affinity | Kiểm tra label/pool/zone; sửa rule hoặc tạo đúng capacity | Bỏ required policy khi nó thể hiện yêu cầu tuân thủ |
| Insufficient cpu/memory | Kiểm tra requests và node capacity; tối ưu workload hoặc scale pool | Giảm requests xuống mức không phản ánh nhu cầu |
| Pod anti-affinity quá chặt | Thêm node/zone hoặc dùng preferred nếu phù hợp mục tiêu HA | Xóa hoàn toàn cơ chế phân tán không đánh giá |
| Topology spread hard block | Kiểm tra domain labels, số node và skew; chỉnh whenUnsatisfiable/scale | Tự đặt zone label giả để qua rule |
| PVC zone conflict | Kiểm tra StorageClass, volume binding và zone topology | Cưỡng ép Pod sang zone không truy cập được dữ liệu |
| Nodes NotReady / cordoned | Khôi phục node/cluster operation; điều tra taints và kubelet | Cấp toleration cho mọi trạng thái node lỗi |
| Scale không xảy ra | Kiểm tra autoscaler limits, quota và node template | Tăng maxCount vô hạn hoặc tạo pool không kiểm soát |

## 16. Giám sát AKS scheduling trong thực tế

### 16.1. Nguồn quan sát

| Tín hiệu | Nguồn | Ý nghĩa |
|---|---|---|
| Pod Pending lâu | kubectl, Kubernetes Events, Container insights | Workload không có node hợp lệ hoặc lỗi scheduling |
| FailedScheduling | Kubernetes Events / diagnostic logs khi thu thập | Lý do node bị loại |
| Node Ready/NotReady | kubectl, Azure Monitor, AKS monitoring | Tình trạng capacity |
| Node pool count | Azure CLI, Azure Monitor metrics | Pool có đủ node/scale được không? |
| CPU/memory requests và usage | kubectl describe node, metrics server/Container insights | Rủi ro thiếu capacity hoặc overcommit |
| Pod distribution theo node/zone | kubectl get pods -o wide, labels/metrics | Rủi ro concentration và HA |
| Evictions/Spot interruptions | Events, AKS logs, Azure/VM signals | Đánh giá độ ổn định của workload trên Spot |
| Thay đổi taints/labels/Deployments | Kubernetes audit và Azure Activity Log theo phạm vi | Truy vết thay đổi scheduling policy |
| Chi phí node pools | Azure Cost Management | Dedicated/Spot/on-demand có hiệu quả kinh tế không? |

Kube-scheduler thuộc managed control plane AKS, vì vậy không nhất thiết có quyền truy cập trực tiếp vào mọi log của scheduler. Hãy dùng Kubernetes Events và những diagnostic categories được AKS hỗ trợ theo cấu hình thực tế.

### 16.2. KQL minh họa cho Kubernetes Events

Nếu Azure Monitor/Container insights gửi dữ liệu vào Log Analytics workspace có bảng KubeEvents:

~~~kusto
KubeEvents
| where TimeGenerated > ago(1h)
| where Reason == "FailedScheduling"
| summarize Events=count() by bin(TimeGenerated, 5m), Namespace
| order by TimeGenerated asc
~~~

Các tên bảng/cột phụ thuộc schema và cấu hình ingestion hiện hành. Hãy kiểm tra workspace thật trước khi sử dụng, và không coi query trả rỗng là bằng chứng cluster không có lỗi nếu chưa bật thu thập Events.

Một số nơi có thể cần lấy thông tin PodName, ObjectName hoặc thông điệp sự kiện từ các cột khác nhau tùy integration. Đừng viết alert dựa vào schema giả định mà chưa thử bằng sự kiện thật.

### 16.3. Alert nên đặt

- Pod Pending hơn ngưỡng chấp nhận theo SLA workload.
- FailedScheduling tăng nhanh sau một deployment.
- Pool dedicated hết capacity hoặc autoscaler chạm max count.
- Node NotReady, Spot evictions hoặc workload bị mất replica Ready.
- Pod distribution tập trung vào một zone/node ngoài thiết kế.
- Người dùng thay đổi node taints, node labels hoặc priority/affinity ngoài change window.
- Dedicated node pool tiêu thụ chi phí lớn nhưng sử dụng thấp kéo dài.

Giám sát nên liên kết **tín hiệu scheduling với ứng dụng**: một Pod Pending ít quan trọng có thể chấp nhận; một replica API thanh toán Pending khi đang mất zone khác có thể là sự cố nghiêm trọng.

## 17. Kịch bản thực tế: kết hợp API đơn hàng, batch và system workloads

Một doanh nghiệp vận hành AKS trên Azure với ba loại workload:

1. **System:** CoreDNS và các components cluster quan trọng.
2. **Orders API:** dịch vụ khách hàng, cần nhiều replica và sẵn sàng cao.
3. **Nightly batch:** xử lý báo cáo lớn, có thể chờ và chạy trên pool riêng để giảm tranh chấp tài nguyên.

### 17.1. Quy hoạch node pools

| Pool | Loại | Label/taint | Workload dự kiến |
|---|---|---|---|
| systempool | System | Các labels/taints được AKS quản lý và chính sách hệ thống đã kiểm tra | Add-ons và system components |
| apppool | User, on-demand, nhiều zone nếu hỗ trợ | workload=frontend, taint nếu muốn dành riêng | Orders API và các dịch vụ giao dịch |
| batchpool | User, on-demand hoặc Spot tùy workload | workload=batch; workload=batch:NoSchedule | Nightly batch workers |

Cần xác minh các system DaemonSets, monitoring/security agents có tolerations cần thiết trên cả các pool. Không tự chặn mọi system Pod khỏi user pools; một số DaemonSets phải chạy ở các node ứng dụng để cung cấp networking, storage hoặc monitoring.

### 17.2. Quy tắc đặt Orders API

Orders API có thể dùng:

- requests phù hợp.
- nodeAffinity required hoặc nodeSelector tới apppool nếu thiết kế cần dedicated placement.
- toleration tương ứng nếu apppool có taint.
- preferred podAntiAffinity theo hostname.
- topology spread theo zone nếu có ít nhất nhiều zone khả dụng.
- HPA theo metric được kiểm chứng và autoscaler cho apppool.
- PodDisruptionBudget để bảo vệ các thao tác voluntary disruptions.

Nếu apppool nằm một zone duy nhất, topology spread không thể tạo khả năng chịu lỗi mất zone. Nên chủ động thiết kế node pool đa zone theo region/SKU hỗ trợ.

### 17.3. Quy tắc đặt Batch

Batch workers:

- Chỉ được vào batchpool nhờ required nodeAffinity.
- Chấp nhận taint batch bằng toleration.
- Có CPU/memory requests phản ánh tải thực.
- Không tự xử lý dữ liệu production ngoài phạm vi quyền.
- Có retry/idempotency; Spot chỉ nếu job chịu gián đoạn.
- Có deadline/completion behavior, không dùng Deployment thường trực nếu nghiệp vụ là tác vụ một lần định kỳ — cân nhắc CronJob/Job.

### 17.4. Khi mất một zone

Giả sử zone A mất một số node:

1. Nodes chuyển NotReady hoặc có tín hiệu sự cố.
2. Những Pod bị ảnh hưởng có thể mất readiness hoặc bị evict theo cơ chế Kubernetes.
3. Deployment controller cố tạo replicas mới.
4. Scheduler xét affinity, taints, spread, PVC topology và resources ở các node còn lại.
5. Autoscaler có thể bổ sung nodes nếu pool phù hợp và có capacity.
6. Nếu hard rules quá chặt, một số Pods Pending; thời gian phục hồi tăng.
7. Hệ thống theo dõi p95 API latency, tỷ lệ lỗi, số Ready replicas và trạng thái ứng dụng.

Bài học vận hành: **sự phân tán tốt phải đi cùng khả năng phục hồi khi thiếu node**, chứ không chỉ đẹp trên dashboard lúc mọi zone đang khỏe.

## 18. Quy trình thay đổi và rollback scheduling policy

### 18.1. Trước khi thay node pool taint

1. Kiểm kê workload hiện đang chạy trên pool, kể cả DaemonSets.
2. Tìm Pods không có toleration phù hợp.
3. Đánh giá NoSchedule so với NoExecute; NoExecute có thể ảnh hưởng Pods hiện hữu.
4. Kiểm tra khả năng capacity khác và autoscaler giới hạn.
5. Áp dụng thử trên lab/staging hoặc một pool mới.
6. Chuẩn bị bản backup cấu hình IaC/manifests và kế hoạch rollback.
7. Đặt cảnh báo Pod Pending, Ready replicas và node health trong cửa sổ thay đổi.
8. Thực hiện theo change approval; không chỉnh nhiều constraints cùng lúc nếu không cần thiết.

### 18.2. Trước khi đổi affinity của Deployment

1. So sánh node labels hiện có và rule mới.
2. Kiểm tra replicas và số node/zone đủ điều kiện.
3. Ước lượng requests và khả năng pool nhận thêm Pod.
4. Nếu dùng rolling update, kiểm tra maxSurge/maxUnavailable và PDB.
5. Deploy thử một replica hoặc canary phù hợp.
6. Quan sát FailedScheduling, rollout status và ready Pods.
7. Nếu policy quá chặt, rollback manifest Deployment về rule trước đó.

Lưu ý: sửa Deployment Pod template thường tạo ReplicaSet mới; các Pods cũ không tự đổi node chỉ vì manifest mới có nodeAffinity khác. Cần xác minh rollout và trạng thái thực tế thay vì chỉ đọc YAML đã apply.

### 18.3. Cleanup lab

Sau khi thử nghiệm, chỉ xóa tài nguyên mà bạn chắc chắn được tạo cho lab và không chứa workload/data cần giữ. Trước khi xóa node pool, kiểm tra Pods đang chạy, khả năng drain và việc xóa có làm cluster mất capacity hệ thống không.

Đối với node pool dùng VM Scale Sets, xóa pool sẽ xóa nodes tương ứng. Đây là thao tác phá hủy tài nguyên, **không được thực hiện trong production chỉ để dọn dẹp bài tập**.

## 19. Checklist trước khi dùng ở production

### Thiết kế placement

- [ ] Phân loại workload theo SLA, dữ liệu, CPU/memory, GPU và khả năng chịu gián đoạn.
- [ ] Node pool System/User, on-demand/Spot và zones được thiết kế rõ.
- [ ] Labels có quy ước nhất quán, không sử dụng label dễ bị sửa để quyết định trust quan trọng.
- [ ] Đã phân biệt required và preferred affinity.
- [ ] Taints được dùng để ngăn Pod không phù hợp, tolerations chỉ cấp khi cần.
- [ ] Workloads cần dedicated placement có cả affinity và toleration tương ứng.
- [ ] HA replica dùng anti-affinity hoặc topology spread phù hợp.
- [ ] PVC, node storage/zone và network topology không mâu thuẫn placement.
- [ ] Resource requests/limits phản ánh tải, không dùng affinity để che thiếu resources.

### Kiểm thử

- [ ] Kiểm tra node labels/taints thật bằng kubectl.
- [ ] Kiểm tra sự kiện FailedScheduling khi deliberately thiếu toleration trong lab.
- [ ] Kiểm tra Pods thực sự nằm trên pool/zone mong đợi.
- [ ] Kiểm tra scale-out khi pool đầy, bao gồm quota và maxCount.
- [ ] Thử mất node/zone theo phương án có phê duyệt.
- [ ] Kiểm tra rollout/PDB/eviction và readiness của ứng dụng.
- [ ] Có cảnh báo khi Pod Pending hoặc node/pool không đủ capacity.
- [ ] Có rollback plan khi label/taint hoặc required affinity bị cấu hình sai.

### Vận hành và chi phí

- [ ] Có owner của node pool và manifest scheduling.
- [ ] Thay đổi taint/label/affinity qua IaC/GitOps và review.
- [ ] Phân quyền sửa node/nodes pools ở mức tối thiểu.
- [ ] Monitor Pod distribution và node pool utilization theo thời gian.
- [ ] Đặt ngân sách cho dedicated pools và autoscaler.
- [ ] Không dùng Spot cho workload không chịu eviction.
- [ ] Kiểm tra theo định kỳ các quy tắc hard gây Pending/overprovisioning.

## 20. Câu hỏi tự kiểm tra

1. **NodeSelector và nodeAffinity khác gì?** nodeSelector là điều kiện label bắt buộc đơn giản; nodeAffinity hỗ trợ biểu thức required hoặc preferred.
2. **requiredDuringSchedulingIgnoredDuringExecution nghĩa là gì?** Node phải thỏa khi schedule; Pod đang chạy không tự bị đuổi nếu label đổi sau đó.
3. **preferred affinity bảo đảm bao nhiêu phần trăm Pods vào node ưu tiên?** Không bảo đảm tỷ lệ; weight chỉ đóng góp điểm chấm trong scheduler.
4. **Trong một nodeSelectorTerm, matchExpressions kết hợp theo AND hay OR?** AND; các terms khác nhau là OR.
5. **PodAntiAffinity theo hostname giúp gì?** Ưu tiên/yêu cầu các Pods phù hợp không cùng node, tùy required hoặc preferred.
6. **Tại sao required anti-affinity có thể làm Pod Pending?** Vì không đủ miền topology/node riêng để đặt các replica.
7. **Taint là gì?** Là điều kiện gắn lên node nhằm ngăn, không ưu tiên hoặc evict Pods không tolerate.
8. **NoSchedule khác NoExecute ra sao?** NoSchedule ngăn schedule mới; NoExecute còn có thể evict Pods đang chạy không tolerate.
9. **Toleration có buộc Pod tới node có taint tương ứng không?** Không. Nó chỉ cho phép Pod được xét trên node đó.
10. **Muốn dedicated node pool thì nên kết hợp gì?** Pool labels + taints, Pod required nodeAffinity/nodeSelector + toleration, và kiểm soát quyền.
11. **NoExecute tolerationSeconds có ý nghĩa gì?** Thời gian Pod chấp nhận taint tương ứng trước khi có thể bị evict.
12. **Tại sao không nên dùng toleration Exists không giới hạn?** Có thể cho Pod đi vào những node hoặc trạng thái không mong muốn.
13. **TopologySpreadConstraints giúp gì?** Điều khiển chênh lệch replica giữa các miền như node/zone.
14. **DoNotSchedule và ScheduleAnyway khác gì?** Một bên là ràng buộc cứng, bên còn lại là ưu tiên mềm khi vi phạm spread.
15. **Node pool mode System có tự cách ly hoàn toàn khỏi user Pods không?** Không. Còn phụ thuộc các quy tắc scheduling/taints/affinity.
16. **Cluster Autoscaler có giải quyết Pod yêu cầu label không có ở mọi pool không?** Thường không; thêm node sai pool không thỏa required placement.
17. **Tại sao scheduler dựa vào requests thay vì chỉ đo CPU usage hiện tại?** Để dự trù tài nguyên cần thiết theo khai báo và tính toán placement.
18. **Spot toleration có chống được Spot VM bị thu hồi không?** Không. Spot capacity có thể bị thu hồi bởi hạ tầng.
19. **PodDisruptionBudget có bảo đảm Pod nằm ở hai zone không?** Không. Nó quản lý một số voluntary disruptions; placement là việc khác.
20. **Dấu hiệu đầu tiên để tìm nguyên nhân Pod Pending là gì?** kubectl describe pod và Events FailedScheduling, sau đó đối chiếu node labels/taints, requests, topology và volumes.
21. **Taint có phải ranh giới bảo mật chống mọi Pod trái phép không?** Không; Pod có quyền sửa spec có thể khai báo toleration, cần RBAC/admission/network controls.
22. **Sau khi đổi affinity trong Deployment, Pod đang chạy có tự chuyển node ngay không?** Không. Pod mới/rollout mới cần được tạo để scheduler áp quy tắc; Pod cũ không tự di chuyển chỉ vì label đổi.

## 21. Tài liệu tham khảo

- [Kubernetes: Assigning Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) — nodeSelector, node affinity, pod affinity và anti-affinity.
- [Kubernetes: Taints and Tolerations](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/) — NoSchedule, PreferNoSchedule, NoExecute và tolerationSeconds.
- [Kubernetes: Pod Topology Spread Constraints](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/) — maxSkew và whenUnsatisfiable.
- [Kubernetes: Scheduling Framework](https://kubernetes.io/docs/concepts/scheduling-eviction/scheduling-framework/) — filter/score và các extension points.
- [Kubernetes: Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/) — CPU/memory requests và limits.
- [Kubernetes: Pod Priority and Preemption](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/) — ưu tiên workload.
- [Kubernetes: Pod Disruption Budgets](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/) — voluntary disruptions và HA.
- [AKS: Node Pools](https://learn.microsoft.com/azure/aks/create-node-pools) — quản lý node pools, labels, taints và mode.
- [AKS: Use Availability Zones](https://learn.microsoft.com/azure/aks/availability-zones) — zone-aware node pools và thiết kế HA.
- [AKS: Cluster Autoscaler](https://learn.microsoft.com/azure/aks/cluster-autoscaler) — scale node theo Pods không schedule được.
- [AKS: Spot node pools](https://learn.microsoft.com/azure/aks/spot-node-pool) — điều kiện Spot và khả năng bị thu hồi.
- [Monitor AKS](https://learn.microsoft.com/azure/aks/monitor-aks) — Events, Container insights và Azure Monitor.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — kiểm soát chi phí node pools và hạ tầng.

**Kết luận:** scheduling tốt không đơn giản là "gắn Pod vào một node". Cần hiểu **nodeAffinity để chọn node**, **podAffinity/anti-affinity và topology spread để tổ chức replica**, **taint để giữ node pool theo mục đích**, và **toleration để Pod được xét vào pool đó**. Trong AKS, các quy tắc chỉ hiệu quả khi node pools, CPU/memory requests, zone capacity, autoscaler, storage topology và bảo mật cùng nhất quán. Hãy ưu tiên thiết kế rõ ràng, xác minh qua Kubernetes Events và kiểm thử failure scenarios trước khi áp lên production.
