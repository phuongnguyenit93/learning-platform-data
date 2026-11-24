# Horizontal Pod Autoscaler, Vertical Pod Autoscaler và co giãn node

Trong Kubernetes, khả năng phục vụ của ứng dụng phụ thuộc đồng thời vào số lượng Pod, tài nguyên mà mỗi Pod cần và số node có thể chạy các Pod đó. Horizontal Pod Autoscaler (HPA) điều chỉnh số replica theo tải; Vertical Pod Autoscaler (VPA) đề xuất hoặc cập nhật CPU và bộ nhớ cho container; node autoscaler bổ sung hoặc loại node để cụm có đủ năng lực lập lịch. Ba cơ chế giải quyết ba cấp độ khác nhau và cần phối hợp để tránh tình trạng Pod tăng nhưng không có node, hoặc request tài nguyên thay đổi khiến chính sách scale phản ứng ngoài dự kiến.

HPA phù hợp khi ứng dụng có thể mở rộng theo chiều ngang, chẳng hạn API stateless hoặc worker. VPA hữu ích khi mức tiêu thụ CPU và memory của container chưa được ước lượng đúng hoặc thay đổi theo thời gian. Node autoscaler giải quyết capacity của hạ tầng bên dưới khi Pod không thể được schedule do thiếu tài nguyên hoặc khi node đang dư thừa. Không cơ chế nào tự sửa được một ứng dụng không thể chia tải, một request sai lệch nghiêm trọng hay một dependency đã bão hòa.

Bài học này giải thích cách ba lớp autoscaling hoạt động, cách chọn metric, cách cấu hình và kiểm thử, cùng các tương tác quan trọng giữa HPA, VPA, scheduler và node pool. Sau bài học, bạn có thể:

- Phân biệt scale Pod theo chiều ngang, điều chỉnh tài nguyên từng Pod và scale node.
- Giải thích cách HPA tính số replica từ metric và resource requests.
- Hiểu VPA recommender, updater, admission controller và các chế độ cập nhật.
- Nhận diện xung đột khi HPA và VPA cùng điều khiển CPU hoặc memory.
- Hiểu node autoscaler phản ứng với Pod Pending và điều kiện scale-in.
- Thiết kế requests/limits, metric, policy và giới hạn capacity phù hợp với SLO.
- Kiểm thử scale-up, scale-down, rescheduling, disruption và chi phí trên cụm thực tế.

## 1. Ba lớp co giãn trong Kubernetes

Kubernetes có nhiều thành phần tham gia điều chỉnh capacity. Cần phân biệt đối tượng mà mỗi cơ chế thay đổi:

| Cơ chế | Đối tượng thay đổi | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|---|
| HPA | Số replica của workload | Cần bao nhiêu Pod để xử lý tải hiện tại? | Tăng API từ 3 lên 10 Pod |
| VPA | CPU/memory requests và có thể cả limits theo policy | Mỗi Pod nên được cấp bao nhiêu tài nguyên? | Điều chỉnh memory request từ 512 MiB lên 1 GiB |
| Node autoscaler | Số node hoặc node pool | Cụm cần thêm hoặc bớt máy để chạy Pod không? | Thêm node khi Pod Pending vì thiếu CPU |

~~~mermaid
flowchart TD
    M["Metrics và trạng thái workload"] --> H["HPA"]
    H --> P["Số Pod / replicas"]
    P --> S["Kubernetes scheduler"]
    V["VPA recommender / policy"] --> R["CPU và memory requests"]
    R --> S
    S --> Q{"Pod có thể schedule?"}
    Q -- "Có" --> N["Node hiện có"]
    Q -- "Không" --> C["Node autoscaler"]
    C --> X["Thêm node / node pool"]
    X --> S
    N --> W["Ứng dụng chạy và xuất metrics"]
    W --> M
~~~

HPA và VPA tác động lên Pod template hoặc Pod spec; node autoscaler tác động lên hạ tầng cụm. HPA có thể tạo thêm Pod, nhưng không tự cấp thêm node. Node autoscaler có thể thêm node, nhưng không tự tăng replica của ứng dụng. VPA có thể tăng request cho Pod, khiến Pod hiện tại cần được tạo lại hoặc cập nhật tại chỗ tùy khả năng cụm; request mới cũng có thể làm Pod khó schedule hơn.

### Điều kiện nền tảng

Trước khi triển khai autoscaling, cần có:

- Workload được quản lý bởi Deployment, StatefulSet hoặc controller phù hợp.
- Resource requests được khai báo cho container; limits được chọn theo chính sách và đặc điểm ứng dụng.
- Metrics pipeline hoạt động và có dữ liệu đủ mới.
- Readiness/liveness probes phản ánh đúng trạng thái ứng dụng.
- Node pool có khả năng tăng capacity, quota và loại instance phù hợp.
- Pod có thể khởi động lại hoặc di chuyển theo chính sách dữ liệu và availability.

Autoscaling không thay thế thiết kế high availability. Ứng dụng cần đủ replica, phân tán qua failure domain và có dependency phía sau chịu được tải tăng.

## 2. Resource requests và limits là nền tảng của scheduling

Kubernetes scheduler dùng resource requests để quyết định Pod có thể được đặt lên node nào. CPU request thường biểu thị lượng CPU cần được đảm bảo trong kế hoạch scheduling; memory request biểu thị lượng bộ nhớ cần dành chỗ trên node. Requests không phải giới hạn cứng của mức sử dụng.

Limits xác định giới hạn sử dụng mà runtime áp dụng:

- CPU limit thường được thực thi bằng throttling khi container cố sử dụng vượt quota.
- Memory limit là giới hạn cứng hơn; container có thể bị OOMKilled nếu vượt mức.

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

Container yêu cầu 0,5 CPU và 512 MiB để scheduler tính capacity. Nó có thể dùng tối đa 1 CPU theo quota và tối đa 1 GiB memory trước khi có nguy cơ bị OOM kill. Cấu hình thực tế cần dựa trên phân phối tải và hành vi peak.

### Requests ảnh hưởng HPA như thế nào?

Khi HPA dùng CPU utilization theo phần trăm request, mức sử dụng CPU được so với CPU request của Pod. Ví dụ, container có request 500m và đang dùng trung bình 250m thì CPU utilization là khoảng 50% request. Nếu request tăng lên 1 CPU nhưng mức dùng vẫn 250m, utilization trở thành khoảng 25%.

Vì vậy, thay đổi CPU request bởi VPA có thể làm thay đổi tín hiệu mà HPA quan sát, dù tải ứng dụng không đổi. Đây là lý do quan trọng cần cân nhắc khi HPA và VPA cùng quản lý CPU.

### Requests quá thấp hoặc quá cao

Requests quá thấp làm scheduler đóng gói quá nhiều Pod lên một node, tăng tranh chấp CPU/memory và khiến HPA hoặc node autoscaler nhận tín hiệu sai lệch. Requests quá cao làm giảm mật độ Pod, tăng số node cần thiết và có thể khiến Pod Pending dù mức sử dụng thực tế thấp.

Nên bắt đầu bằng đo lường dưới workload đại diện, theo dõi usage theo phân vị và kiểm tra peak. Với memory, cần quan tâm mức sử dụng đỉnh và hành vi leak; với CPU, cần xem cả throttling, latency và concurrency.

## 3. Horizontal Pod Autoscaler (HPA)

HPA là controller theo dõi metric của một workload và thay đổi số replica của scale target, thường là Deployment hoặc StatefulSet. HPA thường được cấu hình qua API autoscaling/v2.

### Cách HPA tính số replica

Với một metric có giá trị hiện tại và giá trị mục tiêu, phép tính cơ bản là:

\[
desiredReplicas =
\left\lceil currentReplicas \times
\frac{currentMetricValue}{desiredMetricValue} \right\rceil
\]

Ví dụ, Deployment đang có 4 Pod. CPU utilization trung bình là 90%, trong khi target là 60%:

\[
\left\lceil 4 \times \frac{90}{60} \right\rceil
= \lceil 6 \rceil = 6
\]

HPA sẽ đề xuất 6 replica trước khi áp dụng các giới hạn, tolerance và behavior policy. Công thức thực tế còn xét metric thiếu, Pod đang khởi động, readiness, scale stabilization và các điều kiện an toàn.

Với nhiều metric, HPA tính replica mong muốn theo từng metric rồi thường chọn kết quả lớn nhất để tránh một metric thấp che mất nhu cầu do metric khác báo hiệu.

### Các loại metric của HPA

| Loại metric | Nguồn | Ví dụ sử dụng |
|---|---|---|
| Resource | Metrics API | CPU hoặc memory utilization/average value |
| Container resource | Metrics API theo container | CPU của container ứng dụng, bỏ qua sidecar nếu phù hợp |
| Pods metric | Custom metrics adapter | Request đang xử lý trung bình trên mỗi Pod |
| Object metric | Custom metrics adapter | Metric của một object Kubernetes như ingress hoặc queue proxy |
| External metric | External metrics adapter | Queue backlog, message age hoặc metric từ hệ thống ngoài cụm |

CPU là metric dễ bắt đầu nhưng không phù hợp với mọi workload. Worker có thể cần scale theo queue age; API có thể cần request per Pod; hệ thống streaming có thể cần số kết nối hoặc lag. Metric phải có quan hệ với năng lực xử lý và cập nhật đủ nhanh.

### Metrics Server và Custom Metrics

Metrics Server cung cấp resource metrics như CPU và memory cho Kubernetes Metrics API. Nó thường được dùng cho HPA dựa trên resource utilization và lệnh kubectl top. Metrics Server không phải hệ thống lưu trữ lịch sử metrics hay nền tảng quan sát đầy đủ.

Đối với custom/external metrics, cụm cần adapter tương ứng để đưa metric vào API mà HPA có thể truy vấn. Ví dụ, Prometheus Adapter có thể ánh xạ metric từ Prometheus thành custom metrics. Cần kiểm tra tên metric, label, đơn vị, aggregation và quyền truy cập API.

Nếu HPA báo thiếu metrics hoặc không thể lấy giá trị, hãy kiểm tra APIService, adapter, metrics pipeline, quyền RBAC và trạng thái endpoint trước khi thay đổi target.

## 4. Cấu hình HPA với autoscaling/v2

Ví dụ Deployment API có CPU request và HPA giữ CPU utilization trung bình quanh 60%, với số replica từ 2 đến 20:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
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
      containers:
        - name: api
          image: registry.example.com/orders-api:1.4.0
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            periodSeconds: 5
            failureThreshold: 3
~~~

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  minReplicas: 2
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 60
        - type: Pods
          value: 4
          periodSeconds: 60
      selectPolicy: Max
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 25
          periodSeconds: 60
      selectPolicy: Max
~~~

Trong ví dụ, HPA có thể tăng replica nhanh hơn và giảm chậm hơn. Scale-down giữ một cửa sổ ổn định 5 phút và giới hạn tỷ lệ giảm để tránh cắt capacity ngay khi metric giảm tạm thời. Các giá trị là minh họa; phải hiệu chỉnh theo thời gian khởi động Pod, SLO, tải và khả năng node pool.

### Kiểm tra HPA

~~~bash
kubectl get hpa
kubectl describe hpa orders-api
kubectl get deployment orders-api
kubectl get pods -l app=orders-api
kubectl top pods -l app=orders-api
~~~

Trường TARGETS hiển thị metric hiện tại so với target khi metric có sẵn. Nếu thấy UNKNOWN hoặc dấu hiệu không lấy được metric, xem Events và trạng thái Metrics API/adapter.

## 5. Hành vi scale-up và scale-down của HPA

HPA có behavior policy để điều chỉnh tốc độ thay đổi replica. Các thuộc tính thường dùng:

- stabilizationWindowSeconds: cửa sổ quan sát để tránh phản ứng với biến động ngắn.
- policies: giới hạn thay đổi theo số Pod hoặc phần trăm trong một khoảng thời gian.
- selectPolicy: chọn mức thay đổi lớn nhất, nhỏ nhất hoặc tắt hành động theo cấu hình.

Scale-up thường cần nhanh để hấp thụ tải tăng. Scale-down thường nên thận trọng vì Pod mới khởi động có thể mất thời gian warm-up, còn việc giảm replica có thể làm tăng tải trên những Pod còn lại.

### Readiness và startup

Pod chưa ready không nên nhận traffic từ Service. Nếu readiness probe quá sớm hoặc quá nhạy, Pod có thể liên tục bị thêm/bớt khỏi endpoints. Startup probe hữu ích cho ứng dụng khởi động lâu vì nó cho phép container có thời gian khởi động trước khi liveness/readiness được đánh giá theo cách thông thường.

HPA có các xử lý đặc biệt cho Pod đang khởi động hoặc chưa có metric để tránh tính toán quá lạc quan. Tuy vậy, ứng dụng cần probe chính xác và thời gian startup thực tế được đo.

### HPA không thể scale vượt giới hạn

Nếu replica đạt maxReplicas mà metric vẫn cao, HPA không thể tạo thêm Pod. Cần cảnh báo khi đạt max và xem xét:

- Tăng max nếu node pool, quota và dependency đủ capacity.
- Tối ưu ứng dụng hoặc giảm chi phí xử lý mỗi request.
- Dùng queue/backpressure/rate limiting để kiểm soát tải.
- Kiểm tra metric có phản ánh đúng tải hay không.
- Kiểm tra Pod có Pending vì thiếu node, quota hoặc constraint không.

## 6. Vertical Pod Autoscaler (VPA)

VPA phân tích lịch sử và mức sử dụng tài nguyên của container để đưa ra khuyến nghị CPU/memory requests. Tùy chế độ cập nhật và phiên bản VPA, nó có thể áp dụng khuyến nghị khi Pod được tạo mới, yêu cầu thay thế Pod hoặc cập nhật tài nguyên tại chỗ nếu nền tảng hỗ trợ.

VPA thường được cài như một thành phần bổ sung cho Kubernetes, không phải controller mặc định trong mọi cụm. Một triển khai VPA thường có:

- **Recommender:** thu thập usage và tính toán khuyến nghị tài nguyên.
- **Updater:** xác định Pod cần cập nhật và có thể evict Pod theo policy.
- **Admission controller:** áp dụng request được khuyến nghị khi Pod được tạo.

Các thành phần này có thể được triển khai bằng manifest hoặc Helm chart tùy bản phân phối. Cần kiểm tra phiên bản VPA tương thích với Kubernetes cluster.

### VPA đưa ra khuyến nghị gì?

VPA có thể cung cấp các giá trị như:

- target: mức request được khuyến nghị.
- lowerBound: biên dưới của khoảng tài nguyên hợp lý.
- upperBound: biên trên.
- uncappedTarget: khuyến nghị trước khi áp dụng giới hạn resource policy.

Các giá trị được tính từ lịch sử sử dụng, mô hình thống kê và policy. Chúng là đầu vào để điều chỉnh, không thay thế việc kiểm tra SLO, peak và giới hạn node.

### Các chế độ update phổ biến

Tên và khả năng của update mode phụ thuộc phiên bản VPA:

| Chế độ | Hành vi |
|---|---|
| Off | Chỉ đưa ra khuyến nghị; không tự áp dụng vào Pod |
| Initial | Áp dụng khuyến nghị khi Pod được tạo; không tự cập nhật Pod đang chạy |
| Recreate | Có thể evict và tạo lại Pod để áp dụng tài nguyên mới |
| InPlaceOrRecreate | Ưu tiên cập nhật tại chỗ nếu Kubernetes/runtime hỗ trợ, nếu không có thể dùng recreate |

Không phải cluster nào cũng hỗ trợ mọi mode. Hãy kiểm tra CRD và release VPA đang cài. Khi mới triển khai, mode Off thường là lựa chọn an toàn để quan sát recommendation trước khi cho phép thay đổi tự động.

## 7. Cấu hình VPA ở chế độ khuyến nghị

Ví dụ VPA theo dõi Deployment orders-api và chỉ đưa ra khuyến nghị:

~~~yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: orders-api
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  updatePolicy:
    updateMode: "Off"
  resourcePolicy:
    containerPolicies:
      - containerName: api
        controlledResources:
          - cpu
          - memory
        minAllowed:
          cpu: "100m"
          memory: "128Mi"
        maxAllowed:
          cpu: "2"
          memory: "4Gi"
        controlledValues: RequestsOnly
~~~

Policy giới hạn khoảng request mà VPA có thể đề xuất và chỉ điều khiển requests trong ví dụ. Tên field và giá trị hợp lệ cần được xác minh theo CRD của phiên bản VPA cài đặt. Không áp dụng manifest trước khi kiểm tra CRD tồn tại.

### Quan sát recommendation

~~~bash
kubectl get vpa
kubectl describe vpa orders-api
kubectl get vpa orders-api -o yaml
~~~

Kiểm tra recommendation theo từng container, so sánh với request hiện tại, peak usage, OOM events và throttling. Nếu VPA đề xuất memory quá cao hoặc CPU quá thấp, cần kiểm tra lịch sử metric, thời gian quan sát và workload có đại diện hay không.

### Khi nào nên để VPA chỉ khuyến nghị?

- Cụm mới cài VPA và chưa hiểu phân phối recommendation.
- Workload có SLO nghiêm ngặt hoặc Pod khó khởi động lại.
- Ứng dụng có state local, cache lớn hoặc startup warm-up dài.
- Cần review thay đổi resource trước khi rollout.
- Muốn dùng recommendation để chuẩn hóa requests trong manifest GitOps.

Chế độ khuyến nghị giúp đội vận hành đánh giá và cập nhật cấu hình có kiểm soát mà không để VPA tự evict Pod.

## 8. VPA tự áp dụng tài nguyên và ảnh hưởng tới Pod

Khi dùng mode có cập nhật, VPA có thể thay đổi requests của container. Với recreate, Pod có thể bị evict rồi controller tạo Pod mới với request được cập nhật. Điều này tạo gián đoạn ngắn nếu replica ít hoặc ứng dụng không có khả năng phục hồi phiên.

Trước khi bật cập nhật tự động:

- Có đủ replica và PodDisruptionBudget phù hợp.
- Readiness probe chỉ đánh dấu ready khi ứng dụng thực sự phục vụ được.
- Dữ liệu stateful được lưu bền vững và có cơ chế detach/attach phù hợp.
- Node pool có đủ capacity để schedule Pod mới với request tăng.
- ResourceQuota và LimitRange cho phép giá trị mới.
- Có quan sát về OOM, throttling, restart và latency.
- Có kế hoạch rollback nếu recommendation sai.

VPA không thể làm một node nhỏ chứa được Pod có request lớn hơn allocatable capacity. Nếu request tăng, Pod mới có thể Pending cho tới khi node autoscaler thêm node hoặc workload được điều chỉnh.

### Giới hạn tài nguyên và QoS

Thay đổi request/limit có thể ảnh hưởng QoS class:

- Guaranteed thường yêu cầu CPU và memory requests bằng limits cho mọi container trong Pod.
- Burstable áp dụng khi có requests/limits nhưng không đáp ứng điều kiện Guaranteed.
- BestEffort áp dụng khi không khai báo CPU/memory requests và limits.

QoS class ảnh hưởng cách kubelet xử lý áp lực tài nguyên và eviction. Không nên thay đổi requests/limits mà không hiểu tác động tới QoS, scheduling và eviction priority.

## 9. Xung đột khi kết hợp HPA và VPA

Một tương tác quan trọng: HPA có thể dùng CPU utilization tính theo phần trăm CPU request, trong khi VPA lại thay đổi CPU request. Nếu cả hai cùng điều khiển CPU, mẫu số của metric HPA thay đổi ngay cả khi lượng CPU ứng dụng tiêu thụ không đổi.

Ví dụ:

- Pod request 500m, dùng 300m CPU: utilization 60%.
- VPA tăng request lên 1 CPU, usage vẫn 300m: utilization còn 30%.
- HPA có thể thấy utilization giảm và scale-down, dù tải thực tế không giảm.

Ngược lại, VPA giảm request có thể làm utilization tăng và khiến HPA scale-out. Điều này tạo vòng phản hồi khó dự đoán.

### Các cách kết hợp an toàn hơn

1. **HPA theo CPU, VPA chỉ khuyến nghị:** dùng recommendation để review request, không để VPA tự thay đổi khi HPA đang phụ thuộc CPU utilization.
2. **HPA theo custom/external metric, VPA quản lý CPU và memory:** HPA dựa trên request rate, queue depth hoặc metric workload không bị thay đổi bởi VPA.
3. **Tách tài nguyên được điều khiển:** tùy workload và phiên bản, HPA có thể dùng CPU trong khi VPA chỉ quản lý memory; vẫn cần kiểm tra các tác động gián tiếp.
4. **Tách workload hoặc controller:** nếu ứng dụng có thành phần cần scaling khác nhau, chia thành Deployment/worker riêng với policy rõ ràng.

Không nên bật HPA CPU utilization và VPA tự cập nhật CPU requests cho cùng container mà không đánh giá tương tác. Một số cấu hình có thể bị giới hạn hoặc khuyến cáo không kết hợp theo cách đó.

## 10. Node autoscaling hoạt động như thế nào?

Node autoscaler điều chỉnh số node hoặc số máy trong node pool để cụm có đủ tài nguyên chạy Pod. Một trường hợp phổ biến là Pod đã được tạo nhưng scheduler không tìm thấy node phù hợp do thiếu CPU, memory, GPU hoặc constraint placement. Pod ở trạng thái Pending/Unschedulable có thể kích hoạt node autoscaler yêu cầu thêm node phù hợp.

Các giải pháp thường gặp:

- **Cluster Autoscaler:** theo dõi Pod không thể schedule và node có thể thu nhỏ; tăng/giảm node group theo khả năng của cloud provider.
- **Node auto-provisioning hoặc Karpenter-style provisioner:** có thể chọn loại instance và tạo node pool linh hoạt dựa trên yêu cầu Pod, tùy controller và nền tảng.
- **Managed node pool autoscaling:** nhà cung cấp quản lý node group và điều chỉnh min/max hoặc desired node count theo tích hợp cụm.

Không phải mọi nền tảng dùng cùng thuật toán hoặc cấu hình. Hãy xác định controller cụ thể, cloud provider integration, node group và loại capacity được phép dùng.

### Vì sao Pod Pending có thể không kích hoạt scale-up?

Node autoscaler chỉ thêm node nếu nó tin rằng một node mới trong các pool được cấu hình có thể chạy Pod đó. Pod có thể không schedule được do:

- Node selector hoặc node affinity không khớp bất kỳ node pool nào.
- Taint không có toleration tương ứng.
- PVC yêu cầu zone hoặc topology không tương thích.
- Pod yêu cầu GPU hoặc thiết bị không có trong node pool.
- ResourceQuota, admission policy hoặc giới hạn namespace ngăn tạo Pod.
- Pod request vượt khả năng tối đa của loại node được cấu hình.
- Node group đã chạm max size hoặc cloud quota.

Nếu không có node phù hợp, thêm node một cách mù quáng không giải quyết được vấn đề.

## 11. Scale-up và scale-down node

### Scale-up

Luồng thường gặp:

1. HPA tăng số Pod hoặc workload mới được tạo.
2. Scheduler thử đặt Pod lên node hiện có.
3. Một số Pod không schedule được và nhận trạng thái Unschedulable.
4. Node autoscaler tìm node group hoặc loại instance có thể chạy Pod.
5. Cloud provider cấp phát máy mới.
6. Node khởi động, kết nối control plane và đăng ký Ready.
7. Scheduler đặt Pod lên node mới.
8. Pod khởi động và vượt readiness trước khi nhận traffic.

Thời gian từ lúc HPA quyết định scale tới lúc ứng dụng có capacity có thể gồm thời gian lấy metrics, tạo Pod, phát hiện Pending, cấp máy, boot node, tải image và warm-up ứng dụng. Nếu peak đến nhanh hơn chu trình này, cần giữ baseline capacity hoặc dùng scheduled scaling.

### Scale-down

Node autoscaler có thể loại node trống hoặc node ít sử dụng nếu các Pod trên đó có thể được chuyển sang node khác. Trước khi xóa node, controller cần đánh giá:

- Pod có thể được evict an toàn không?
- PodDisruptionBudget có cho phép disruption không?
- Có Pod dùng local storage hoặc dữ liệu gắn với node không?
- Pod có affinity/anti-affinity hoặc topology constraint khiến không thể di chuyển không?
- Node có daemonset, system pod hoặc workload không thể chuyển không?
- Node có scale-down disabled hoặc bị đánh dấu không được loại không?

Scale-down thường chậm và thận trọng hơn scale-up để tránh disruption liên tục. Cần quan sát số node bị drain, thời gian drain và Pod bị pending sau khi node bị loại.

## 12. Cấu hình và kiểm tra node autoscaler

Cluster Autoscaler thường được cấu hình với min/max size cho từng node group và tích hợp cloud provider. Các tham số chính xác phụ thuộc nền tảng; không nên sao chép flags từ môi trường khác mà không kiểm tra phiên bản.

Thông tin cần xác minh:

- Node group nào được phép scale và min/max size của từng nhóm.
- Loại instance, kiến trúc CPU, GPU, vùng và capacity type.
- Cloud quota, subnet IP và khả năng cấp phát.
- Tài nguyên allocatable của node sau khi trừ system/daemonset overhead.
- Labels, taints và topology của từng node pool.
- Quy tắc scale-down, thời gian unneeded và giới hạn disruption.

Lệnh kiểm tra cơ bản:

~~~bash
kubectl get nodes -o wide
kubectl describe node <node-name>
kubectl get pods -A --field-selector=status.phase=Pending
kubectl describe pod <pod-name>
kubectl get events -A --sort-by=.lastTimestamp
~~~

Với Cluster Autoscaler, xem log của controller và event liên quan tới scale-up/scale-down. Với provisioner khác, kiểm tra log, object cấu hình và event của controller đó. Đừng kết luận node autoscaler lỗi chỉ từ trạng thái Pending; đọc scheduler event để biết lý do chính xác.

## 13. Kết hợp HPA, VPA và node autoscaler

Một chuỗi phối hợp thường gặp:

1. Request rate tăng.
2. HPA tăng replica.
3. Scheduler tìm chỗ đặt Pod mới.
4. Nếu thiếu capacity, node autoscaler thêm node.
5. Pod được schedule, khởi động và ready.
6. VPA tiếp tục phân tích usage để đề xuất request phù hợp.

~~~mermaid
sequenceDiagram
    participant Load as Tải ứng dụng
    participant HPA as HPA
    participant S as Scheduler
    participant NA as Node autoscaler
    participant Cloud as Cloud provider
    participant VPA as VPA
    Load->>HPA: Metric tăng
    HPA->>S: Tăng số Pod
    S-->>NA: Pod không schedule được
    NA->>Cloud: Yêu cầu node phù hợp
    Cloud-->>NA: Node mới được cấp
    NA-->>S: Node Ready
    S->>S: Schedule Pod
    VPA->>VPA: Quan sát usage và cập nhật recommendation
~~~

HPA có thể scale nhanh hơn node autoscaler cấp node. Vì vậy, Pod Pending trong vài phút có thể là trạng thái tạm thời nhưng vẫn cần theo dõi. Nếu thời gian chờ vượt SLO, hãy giữ sẵn capacity hoặc giảm thời gian khởi động node.

### VPA và node capacity

Khi VPA tăng request, Pod có thể không còn phù hợp với node hiện tại. Nếu VPA dùng recreate, Pod mới với request lớn hơn có thể Pending và kích hoạt node autoscaler. Ngược lại, VPA giảm request có thể giúp scheduler đóng gói Pod hiệu quả hơn, tạo điều kiện scale-down node.

Đây là lợi ích tiềm năng nhưng cũng có thể gây churn nếu recommendation thay đổi thường xuyên. Cần giới hạn minAllowed/maxAllowed, kiểm tra resource policy và giữ cửa sổ ổn định trước khi áp dụng.

### Tránh tạo vòng lặp khó kiểm soát

- HPA scale Pod theo CPU utilization.
- VPA tăng CPU request.
- CPU utilization giảm dù usage không đổi.
- HPA scale-down.
- Pod giảm khiến tải trên mỗi Pod tăng.
- HPA lại scale-up.

Để tránh, dùng HPA metric độc lập với request mà VPA thay đổi hoặc để VPA ở chế độ recommendation-only khi HPA dựa trên CPU utilization.

## 14. PodDisruptionBudget và khả năng di chuyển Pod

Node scale-down, VPA recreate và bảo trì node đều có thể gây eviction. PodDisruptionBudget (PDB) giới hạn số Pod có thể bị gián đoạn tự nguyện tại một thời điểm.

Ví dụ:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-api
~~~

PDB yêu cầu duy trì ít nhất hai Pod available khi xảy ra voluntary disruption. Nó không ngăn mọi loại sự cố bất ngờ, không bảo đảm Pod mới schedule được và không thay thế replica, readiness hay thiết kế stateful. Nếu PDB quá chặt, node autoscaler có thể không scale-down được.

Với workload có local storage, StatefulSet, single replica hoặc anti-affinity nghiêm ngặt, cần kiểm tra đường di chuyển trước khi bật scale-in tự động.

## 15. Thiết kế resource requests và giới hạn cho nhiều lớp autoscaling

Requests là đầu vào chung của scheduler, HPA utilization và VPA. Vì vậy, cần quản lý chúng như một phần của hợp đồng capacity.

### Một quy trình thực tế

1. Đo CPU/memory theo từng container dưới tải nền và peak.
2. Xác định request ban đầu đủ để scheduler đặt Pod và HPA tính utilization hợp lý.
3. Đặt limit theo chính sách và khả năng chịu tải; tránh CPU limit quá thấp gây throttling.
4. Chạy VPA ở mode Off để quan sát recommendation.
5. So sánh recommendation với usage, OOM, throttling và SLO.
6. Cập nhật manifest qua GitOps hoặc thử nghiệm update mode có kiểm soát.
7. Kiểm tra Pod mới có thể schedule trên node pool hiện có không.
8. Xác minh node autoscaler có thể tạo node phù hợp khi thiếu capacity.

### Memory cần thận trọng

Memory không thể nén hoặc mượn linh hoạt giống CPU trong mọi trường hợp. Khi container vượt memory limit, kernel có thể OOM kill container. Requests memory quá thấp có thể làm scheduler overcommit node; khi node chịu áp lực, kubelet có thể eviction Pod theo QoS và mức ưu tiên.

VPA recommendation cho memory nên xem xét peak working set, startup spike, cache, heap và thời gian quan sát. Không dùng trung bình thấp để đặt request cho ứng dụng có peak đột biến.

### CPU throttling

CPU limit có thể làm container bị throttling ngay cả khi node còn CPU capacity, tùy cấu hình CFS quota. Nếu latency cao nhưng CPU usage không chạm node capacity, kiểm tra throttling metrics trước khi tăng replica. Tăng Pod count có thể che dấu vấn đề CPU limit và làm tăng overhead.

## 16. Ví dụ end-to-end: API tăng tải trên cụm Kubernetes

Một API có tải nền 100 request/giây, giờ cao điểm đạt 600 request/giây. Benchmark cho thấy mỗi Pod xử lý an toàn khoảng 100 request/giây với p95 dưới 200 ms. Mỗi Pod yêu cầu 500m CPU và 512 MiB memory. Node pool có node allocatable 4 CPU và 16 GiB memory sau khi trừ system overhead.

### Thiết kế ban đầu

- HPA minReplicas = 2, maxReplicas = 12.
- HPA dùng request per Pod hoặc CPU utilization đã benchmark.
- VPA chạy mode Off trong giai đoạn quan sát để đề xuất request.
- Node autoscaler quản lý node pool với min/max phù hợp quota.
- PDB giữ tối thiểu số Pod cần thiết trong quá trình drain.
- Readiness probe chỉ cho traffic vào Pod sau khi API warm-up hoàn tất.

Ở tải đỉnh 600 request/giây, phép tính thuần theo capacity là 6 Pod. Nhóm có thể giữ thêm headroom để chịu một Pod lỗi và biến động request. Trên node 4 CPU, lý thuyết có thể đặt tối đa 8 Pod theo CPU request 500m, nhưng còn phải tính memory, daemonset, topology, anti-affinity và các workload khác. Không nên chỉ chia allocatable CPU cho request rồi kết luận node chắc chắn chứa được số Pod đó.

### Khi tải tăng

1. Request per Pod hoặc CPU tăng.
2. HPA tăng desired replicas.
3. Scheduler đặt Pod mới nếu node còn chỗ.
4. Nếu Pod Pending do thiếu CPU/memory, node autoscaler thêm node phù hợp.
5. Pod mới vượt startup/readiness rồi bắt đầu nhận traffic.
6. VPA tiếp tục thu thập usage và đưa ra recommendation để nhóm xem xét.

### Khi tải giảm

1. HPA giữ metric trong stabilization window trước khi scale-down.
2. Replica giảm dần theo policy.
3. Pod kết thúc graceful và ngừng nhận request mới.
4. Node autoscaler đánh giá node dư, drain Pod có thể di chuyển.
5. Node chỉ bị xóa khi PDB, local storage, affinity và capacity còn lại cho phép.

Ví dụ cho thấy HPA, VPA và node autoscaler không thay thế nhau. HPA điều chỉnh số Pod; VPA cải thiện request của từng Pod; node autoscaler bảo đảm hạ tầng đủ để schedule chúng.

## 17. Troubleshooting autoscaling

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| HPA không tăng replica | Metric thiếu, target sai, HPA maxReplicas hoặc controller lỗi | describe HPA, Events, Metrics API, adapter |
| HPA tăng Pod nhưng Pod Pending | Thiếu node, quota, selector/taint hoặc request quá lớn | describe Pod, scheduler events, node pool |
| CPU HPA dao động sau VPA update | CPU request thay đổi làm utilization đổi | VPA update history, requests hiện tại và HPA metric |
| VPA không có recommendation | Recommender chưa có dữ liệu, targetRef sai hoặc component lỗi | VPA status, recommender logs, CRD và selector |
| VPA recreate gây gián đoạn | Replica/PDB/probe không phù hợp | Pod events, PDB status, readiness và update mode |
| Node autoscaler không scale-up | Không có node group phù hợp, max/quota hoặc Pod constraint | Controller logs, unschedulable reason, cloud quota |
| Node không scale-down | Pod không evict được, PDB, local storage hoặc affinity | describe node/pod, PDB, scale-down events |
| Node mới Ready nhưng Pod vẫn Pending | Node label/taint, allocatable hoặc topology không khớp | describe node và Pod scheduling events |
| Memory OOM dù VPA tăng request | Limit vẫn thấp, peak chưa được quan sát hoặc memory leak | container limits, OOM events, working set |
| CPU cao nhưng latency không giảm sau scale | Dependency bão hòa hoặc bottleneck không nằm ở Pod | DB, queue, network, downstream metrics |

### Lệnh kiểm tra thường dùng

~~~bash
kubectl get hpa,vpa
kubectl describe hpa <hpa-name>
kubectl describe vpa <vpa-name>
kubectl get nodes
kubectl get pods -A -o wide
kubectl get events -A --sort-by=.lastTimestamp
kubectl top nodes
kubectl top pods -A
~~~

VPA resource và CRD có thể không được cài trên cluster; lệnh get vpa chỉ hoạt động khi API VPA đã được đăng ký. Node autoscaler cũng có log và resource riêng theo implementation.

## 18. Quan sát, SLO và chi phí

Để đánh giá autoscaling, cần theo dõi cả quyết định điều khiển và kết quả thực tế.

| Lớp | Metric nên theo dõi |
|---|---|
| Ứng dụng | p50/p95/p99 latency, throughput thành công, error rate |
| HPA | Desired/current replicas, metric current/target, scaling events |
| VPA | Target/lowerBound/upperBound, requests hiện tại, update/eviction events |
| Pod | Pending, startup time, readiness, restart, OOMKilled, throttling |
| Node | Node count, allocatable, utilization, Pending duration, scale activity |
| Dependency | DB connections, queue age, cache, storage và network |
| Chi phí | Node-hours, chi phí trên request/job, idle capacity và chi phí warm-up |

Một policy có thể đạt mục tiêu CPU nhưng vẫn vi phạm SLO do database chậm. Ngược lại, CPU thấp không có nghĩa cần scale-down nếu workload cần giữ capacity để hấp thụ burst hoặc duy trì availability khi một zone lỗi.

### Đặt giới hạn và bảo vệ ngân sách

- Giới hạn maxReplicas của HPA.
- Giới hạn min/max node count và loại instance trong node pool.
- Thiết lập ResourceQuota theo namespace và LimitRange theo workload.
- Cảnh báo khi HPA chạm max, Pod Pending lâu hoặc node autoscaler chạm quota.
- Theo dõi số lần evict/recreate do VPA.
- Kiểm tra chi phí cross-zone, storage và IP khi node pool mở rộng.

Autoscaling nên được tối ưu theo chi phí trên đơn vị công việc hoàn thành trong khi vẫn đáp ứng SLO, thay vì chỉ giảm số node.

## 19. Các sai lầm thường gặp

1. **Coi HPA là node autoscaler:** tăng replica nhưng không có node để schedule.
2. **Không khai báo requests:** HPA CPU utilization không thể tính đúng và scheduler không có cơ sở capacity.
3. **Dùng VPA tự cập nhật CPU cùng HPA CPU utilization:** thay đổi mẫu số khiến HPA phản ứng ngoài dự kiến.
4. **Bật VPA update mode quá sớm:** Pod bị evict trước khi hiểu recommendation.
5. **Chỉ dựa vào CPU:** workload có thể bị giới hạn bởi queue, memory, I/O hoặc GPU.
6. **Đặt requests quá cao:** Pod Pending và node autoscaler tạo nhiều máy hơn cần thiết.
7. **Đặt requests quá thấp:** node bị overcommit, eviction và latency tăng.
8. **Bỏ qua PDB:** VPA hoặc node scale-down có thể làm gián đoạn quá nhiều Pod.
9. **Không kiểm tra max/quota:** HPA hoặc node autoscaler không thể mở rộng khi cần.
10. **Không đo startup/readiness:** node và Pod mới chưa tạo ra capacity hữu ích đúng lúc.
11. **Không bảo vệ downstream:** thêm Pod làm database hoặc service phụ thuộc quá tải.
12. **Không kiểm thử scale-in:** Pod stateful hoặc job dài bị evict không an toàn.

## 20. Checklist triển khai HPA, VPA và node autoscaling

- [ ] Workload có thể scale ngang và có replica phù hợp.
- [ ] CPU/memory requests được khai báo và đo bằng workload đại diện.
- [ ] Metrics Server hoạt động cho resource metrics.
- [ ] Custom/external metrics adapter được cấu hình nếu HPA cần metric ngoài.
- [ ] HPA dùng đúng metric, target, min/max và behavior policy.
- [ ] VPA CRD/controller tương thích với phiên bản Kubernetes.
- [ ] VPA bắt đầu ở chế độ recommendation-only để quan sát.
- [ ] Không có xung đột HPA/VPA trên cùng CPU utilization metric.
- [ ] Resource policy có minAllowed/maxAllowed và controlledResources phù hợp.
- [ ] Node autoscaler có node pool tương thích với Pod requests, labels và taints.
- [ ] Cloud quota, subnet IP và giới hạn instance đủ cho max capacity.
- [ ] PodDisruptionBudget, readiness và graceful shutdown đã được kiểm tra.
- [ ] Stateful/local storage và topology được xem xét trước scale-in.
- [ ] Có cảnh báo cho Pending Pod, maxReplicas, node quota và scale failure.
- [ ] Đã thử scale-up, scale-down, VPA recommendation/update và node drain.
- [ ] Đã theo dõi SLO, dependency và chi phí trong thời gian đủ dài.

## 21. Bài tập vận dụng

Một Deployment xử lý API có 4 Pod. Mỗi Pod khai báo CPU request 500m và memory request 512 MiB. HPA đặt target CPU utilization 60%, maxReplicas 20. VPA đang chạy ở chế độ tự cập nhật và đề xuất tăng CPU request lên 1 CPU. Cùng lúc, traffic tăng khiến CPU thực tế trung bình đạt 300m mỗi Pod. Cụm chỉ còn ít CPU allocatable nên các Pod mới ở trạng thái Pending.

1. Trước khi VPA thay đổi request, CPU utilization của Pod là bao nhiêu phần trăm?
2. Sau khi CPU request tăng lên 1 CPU nhưng usage vẫn 300m, utilization thay đổi thế nào?
3. HPA có thể thay đổi quyết định scale ra sao khi utilization giảm?
4. Vì sao HPA tạo thêm Pod nhưng node autoscaler mới là thành phần cần bổ sung node?
5. Đề xuất cách phối hợp HPA, VPA và node autoscaler để tránh vòng phản hồi không mong muốn.
6. Cần kiểm tra những event và metric nào để xác định vì sao Pod Pending?

Gợi ý: trước cập nhật, 300m trên request 500m tương đương 60%; sau khi request tăng lên 1 CPU, usage 300m tương đương 30%. Nếu HPA dựa trên CPU utilization, tín hiệu giảm có thể làm giảm replica mong muốn dù traffic không giảm. Có thể để VPA ở mode Off để review recommendation hoặc chuyển HPA sang metric độc lập như request per Pod. HPA điều chỉnh replica; scheduler phát hiện thiếu capacity; node autoscaler cần node pool phù hợp để chạy Pod Pending. Kiểm tra describe Pod, scheduler events, node allocatable, taint/affinity, node pool max và cloud quota.

## Kết luận

HPA điều chỉnh số Pod theo metric, VPA đề xuất hoặc cập nhật tài nguyên cho từng container, còn node autoscaler bổ sung hoặc loại node để đáp ứng nhu cầu scheduling. Ba cơ chế cần phối hợp qua resource requests, metrics, readiness, PDB, node pool và giới hạn quota. Bắt đầu bằng đo workload và quan sát VPA recommendation, chọn HPA metric liên hệ với capacity, giữ headroom cho scale-up và kiểm thử scale-in. Khi theo dõi đồng thời SLO, Pod Pending, node capacity, dependency và chi phí, autoscaling mới giúp cụm Kubernetes duy trì hiệu năng mà không tạo ra dao động hoặc capacity dư thừa.
