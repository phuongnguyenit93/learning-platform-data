# PodDisruptionBudget, drain và nâng cấp node an toàn

## Mục tiêu bài học

Kubernetes thường phải di chuyển hoặc kết thúc Pod khi bảo trì node, nâng cấp hệ điều hành, thay đổi phiên bản kubelet, thu hồi máy Spot hoặc cân bằng lại tài nguyên. Một Pod bị xóa có thể được controller tạo lại, nhưng Pod thay thế cần thời gian để được schedule, tải image, khởi động và vượt qua readiness probe. Nếu nhiều Pod của cùng một ứng dụng bị gián đoạn cùng lúc, dịch vụ có thể mất khả năng đáp ứng dù cluster vẫn còn node hoạt động.

PodDisruptionBudget (PDB) giúp giới hạn số Pod khỏe mạnh có thể bị gián đoạn bởi các thao tác chủ động thông qua Kubernetes Eviction API. Kết hợp PDB với drain đúng cách, graceful shutdown, topology và capacity dự phòng giúp bảo trì node có kiểm soát.

Sau bài học này, bạn có thể:

- Phân biệt voluntary disruption và involuntary disruption.
- Giải thích PDB, minAvailable, maxUnavailable và trạng thái disruptionsAllowed.
- Tạo PDB phù hợp với Deployment hoặc StatefulSet.
- Hiểu cách kubectl cordon và kubectl drain hoạt động.
- Nhận biết trường hợp drain bị PDB chặn và cách xử lý an toàn.
- Thiết kế readiness, graceful termination và topology để giữ availability.
- Lập quy trình nâng cấp node pool theo từng bước.
- Theo dõi và kiểm thử quá trình bảo trì mà không vượt quá ngân sách gián đoạn.

## 1. Vì sao cần kiểm soát gián đoạn Pod?

Pod có vòng đời ngắn. Kubernetes có thể tạo Pod mới để duy trì số replica mong muốn, nhưng việc thay thế không tức thời. Trong thời gian Pod cũ rời đi và Pod mới trở nên Ready, số replica phục vụ được traffic có thể giảm.

Các nguyên nhân phổ biến khiến Pod bị gián đoạn:

- Quản trị viên drain node để bảo trì hoặc nâng cấp.
- Managed node group thay thế node theo chiến lược rolling update.
- Cluster autoscaler loại node sau khi dồn workload sang node khác.
- Node pool thay đổi instance type hoặc image hệ điều hành.
- Node cần reboot để cài bản vá kernel.
- Một workload bị di chuyển khỏi node để tái cân bằng tài nguyên.
- Pod bị xóa chủ động bởi automation hoặc công cụ vận hành.

Nếu một ứng dụng có ba replica nhưng cả ba cùng nằm trên một node, drain node đó có thể làm mất toàn bộ capacity phục vụ cùng lúc. Deployment có thể tạo ba Pod mới, nhưng chúng vẫn cần node đủ CPU/RAM, image pull, volume attach và thời gian startup.

PDB là một phần của kế hoạch availability. Nó cần đi cùng số replica phù hợp, readiness probe, phân bố Pod qua nhiều failure domain, capacity dự phòng và ứng dụng có khả năng dừng an toàn.

## 2. Voluntary và involuntary disruption

Kubernetes phân biệt hai nhóm gián đoạn.

**Voluntary disruption** là gián đoạn do một hành động chủ động của người vận hành hoặc controller, ví dụ:

- kubectl drain sử dụng Eviction API.
- Một số thao tác bảo trì node hoặc công cụ quản lý node dùng eviction.
- Một automation chủ động evict Pod qua API.

**Involuntary disruption** là gián đoạn ngoài ý muốn của controller hoặc người vận hành, ví dụ:

- Node mất điện hoặc host gặp lỗi.
- Kernel panic hoặc node mất kết nối.
- Pod bị OOM kill.
- Node chịu memory/disk pressure và kubelet evict Pod.
- Lỗi phần cứng hoặc sự cố hạ tầng làm process dừng.

PDB chủ yếu kiểm soát voluntary disruption thông qua Eviction API. PDB không ngăn node bị hỏng, không giữ Pod sống khi kernel dừng và không bảo đảm chống OOM. Involuntary disruption có thể làm số Pod khỏe mạnh thấp hơn ngân sách đã đặt; khi đó PDB thường ngăn thêm voluntary eviction cho tới khi workload phục hồi.

| Loại gián đoạn | Ví dụ | PDB có kiểm soát trực tiếp không? |
|---|---|---|
| Voluntary qua Eviction API | kubectl drain | Có |
| Voluntary qua công cụ dùng Eviction API | Node maintenance controller | Có, nếu công cụ tôn trọng API |
| Xóa Pod trực tiếp | kubectl delete pod | Không nhất thiết; thao tác xóa trực tiếp không dùng Eviction API |
| Node/host failure | Mất máy hoặc mất nguồn | Không |
| OOM hoặc node pressure | Kernel/kubelet kết thúc Pod | Không bảo vệ khỏi nguyên nhân này |
| Deployment rolling update | Controller thay Pod theo strategy của workload | PDB không phải cơ chế điều khiển rollout này |

Không nên xem PDB là một firewall ngăn mọi Pod bị xóa. Nó là ngân sách cho một loại hành động cụ thể trong quy trình eviction.

## 3. PodDisruptionBudget hoạt động như thế nào?

PodDisruptionBudget là tài nguyên thuộc API group policy/v1, đặt trong namespace của workload. PDB chọn một nhóm Pod bằng label selector và xác định số lượng hoặc tỷ lệ Pod phải duy trì khỏe mạnh khi có voluntary disruption.

PDB hỗ trợ hai cách khai báo chính:

- **minAvailable:** số lượng hoặc tỷ lệ Pod tối thiểu phải healthy.
- **maxUnavailable:** số lượng hoặc tỷ lệ Pod tối đa được phép unavailable.

Chỉ khai báo một trong hai trường. Không đặt cả minAvailable và maxUnavailable trong cùng một PDB.

Khi một client yêu cầu eviction, Kubernetes kiểm tra PDB tương ứng. Nếu việc evict Pod làm số Pod healthy thấp hơn ngân sách, API có thể từ chối yêu cầu và trả lỗi Too Many Requests. Công cụ drain sẽ chờ hoặc retry theo hành vi của nó; người vận hành cần khôi phục budget hoặc chờ Pod khác healthy trước khi tiếp tục.

~~~mermaid
flowchart TD
    A["Yêu cầu Eviction Pod"] --> B["Tìm PDB khớp selector"]
    B --> C["Đọc healthy và desired healthy"]
    C --> D{"disruptionsAllowed > 0?"}
    D -->|Có| E["Cho phép eviction"]
    D -->|Không| F["Từ chối / chờ"]
    E --> G["Pod kết thúc có kiểm soát"]
    F --> H["Khôi phục replica hoặc capacity"]
    H --> C
~~~

### 3.1. PDB tính ngân sách dựa trên trạng thái workload

PDB theo dõi số Pod dự kiến và số Pod healthy. Một số trường trạng thái thường thấy:

| Trường status | Ý nghĩa |
|---|---|
| currentHealthy | Số Pod hiện đang được xem là healthy |
| desiredHealthy | Số Pod healthy tối thiểu cần duy trì |
| disruptionsAllowed | Số voluntary disruption còn được phép |
| expectedPods | Số Pod dự kiến theo scale của workload |
| disruptedPods | Pod đã được ghi nhận đang trong quá trình disruption |

Giá trị disruptionsAllowed là thông tin vận hành quan trọng. Nếu bằng 0, thao tác drain có thể bị chặn khi cố evict Pod thuộc PDB đó.

PDB cần có selector khớp đúng các Pod cần bảo vệ. Nếu selector không khớp, PDB không bảo vệ workload dự kiến. Nếu selector quá rộng, PDB có thể gom Pod của nhiều thành phần có vòng đời khác nhau vào một ngân sách và làm maintenance khó thực hiện.

### 3.2. Ví dụ minAvailable

Một Deployment có ba replica và cần giữ tối thiểu hai Pod healthy trong lúc bảo trì node:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
  namespace: production
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-api
~~~

PDB trên cho phép tối đa một Pod thuộc nhóm bị voluntary disruption tại một thời điểm, nếu cả ba Pod đều healthy và các điều kiện khác vẫn thỏa mãn.

Nếu chỉ còn hai Pod healthy, disruptionsAllowed có thể giảm về 0. Khi đó drain phải chờ cho tới khi workload phục hồi hoặc ngân sách được điều chỉnh theo kế hoạch đã được đánh giá.

### 3.3. Ví dụ maxUnavailable

Một cách viết tương đương về ý nghĩa cho workload có bốn replica là cho phép tối đa một Pod unavailable:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: catalog-pdb
  namespace: production
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: catalog
~~~

maxUnavailable phù hợp khi muốn giới hạn số Pod unavailable thay vì đặt số Pod tối thiểu. Với workload có số replica thay đổi, giá trị số nguyên và tỷ lệ phần trăm có thể hữu ích hơn một ngưỡng cố định.

### 3.4. Dùng tỷ lệ phần trăm

PDB cho phép dùng giá trị phần trăm cho minAvailable hoặc maxUnavailable. Khi tính số Pod, Kubernetes làm tròn lên cho các giá trị phần trăm.

Ví dụ với năm replica:

- minAvailable: 80% yêu cầu ít nhất bốn Pod healthy.
- maxUnavailable: 20% cho phép tối đa một Pod unavailable.
- maxUnavailable: 30% được làm tròn lên thành hai Pod.

Cần tính rõ số Pod thực tế ở mức replica tối thiểu, bình thường và peak. Một PDB theo phần trăm có thể tạo ra số disruption khác nhau khi replica thay đổi.

## 4. Chọn PDB theo số replica và SLO

Không có một giá trị PDB đúng cho mọi ứng dụng. Cần dựa trên mức availability, khả năng chịu lỗi, thời gian khởi động Pod thay thế và capacity cluster.

| Số replica | PDB minh họa | Tác động |
|---:|---|---|
| 1 | minAvailable: 1 | Chặn voluntary eviction; cần kế hoạch downtime hoặc tăng replica trước |
| 2 | minAvailable: 1 | Cho phép một Pod bị gián đoạn nếu cả hai đang healthy |
| 3 | minAvailable: 2 | Cho phép tối đa một Pod bị gián đoạn |
| 4 | maxUnavailable: 1 | Cho phép một Pod unavailable |
| 5 | minAvailable: 80% | Cần ít nhất bốn Pod healthy |

Với ứng dụng chỉ có một replica, PDB minAvailable: 1 có thể khiến drain không thể hoàn tất. Điều này không phải lỗi của Kubernetes; PDB đang thực hiện đúng chính sách không cho voluntary disruption. Muốn bảo trì không downtime, cần tăng replica, có cơ chế failover hoặc chấp nhận một cửa sổ downtime được phê duyệt.

PDB không tự tạo thêm replica. Nó chỉ giới hạn việc evict. Nếu workload thiếu replica, cần khôi phục workload trước khi tiếp tục bảo trì.

### 4.1. Tính đến thời gian phục hồi

Giả sử một Pod cần 90 giây để schedule, pull image, khởi động và qua readiness. Nếu drain nhiều node liên tiếp mà không chờ Pod mới healthy, budget có thể nhanh chóng về 0 hoặc số replica phục vụ có thể thấp hơn yêu cầu.

Kế hoạch maintenance nên chờ:

- Pod thay thế được schedule.
- Container đã khởi động.
- Readiness probe thành công.
- Endpoint được cập nhật.
- Application latency và error rate ổn định.
- PDB disruptionsAllowed được khôi phục trước đợt tiếp theo.

Đối với ứng dụng có warmup dài, readiness pass cần phản ánh khả năng phục vụ thực tế. Không dùng health check quá nông chỉ để drain nhanh.

## 5. PDB và Deployment/StatefulSet rollout là hai cơ chế khác nhau

Một nhầm lẫn thường gặp là nghĩ PDB điều khiển số Pod được thay trong Deployment rolling update. Trên thực tế, rollout của Deployment được kiểm soát bởi strategy của Deployment, chẳng hạn maxUnavailable và maxSurge.

PDB điều khiển voluntary eviction thông qua Eviction API. Nó không thay thế rolling update strategy của Deployment.

Ví dụ Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: registry.example.com/orders-api:2.4.1
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8080
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Trong ví dụ, Deployment cố gắng tạo Pod mới trước khi giảm số Pod cũ, và không cho rollout làm số replica unavailable vượt quá strategy đã đặt. Cấu hình này cần capacity để chạy Pod surge; nếu cluster không có tài nguyên, rollout có thể bị chậm hoặc Pod mới Pending.

PDB vẫn hữu ích trong lúc node drain, nhưng không phải công cụ thay thế maxUnavailable/maxSurge. Cần thiết kế cả hai để rollout ứng dụng và bảo trì hạ tầng không tạo ra gián đoạn vượt SLO.

### 5.1. StatefulSet và quorum

Với StatefulSet, PDB có thể hạn chế eviction chủ động, nhưng không bảo đảm quorum hoặc nhất quán dữ liệu. Hãy kiểm tra:

- Số replica và quorum của database/cluster.
- Pod nào là leader hoặc primary.
- Thứ tự failover và thời gian bầu leader.
- PersistentVolume gắn với AZ nào.
- Pod replacement có thể được schedule ở đâu.
- Ứng dụng có hỗ trợ graceful shutdown và rejoin cluster không.

Không drain nhiều node chứa các thành viên quorum cùng lúc. PDB cần phản ánh giới hạn gián đoạn của workload, nhưng quy trình nâng cấp vẫn phải hiểu topology và giao thức phân tán.

## 6. Thiết kế selector chính xác

PDB sử dụng label selector để xác định Pod thuộc budget. Selector cần giống với label mà controller gắn lên đúng workload.

Ví dụ:

~~~yaml
selector:
  matchLabels:
    app: orders-api
    component: backend
~~~

Trước khi áp dụng PDB, kiểm tra danh sách Pod thực tế:

~~~bash
kubectl get pods -n production -l app=orders-api,component=backend --show-labels
~~~

Các lỗi thường gặp:

- Selector không khớp Pod nào.
- Selector khớp cả worker, API và migration job trong cùng namespace.
- Nhiều PDB có selector chồng lấn lên cùng Pod.
- Label bị thay đổi trong quá trình release nhưng PDB chưa cập nhật.
- PDB đặt ở namespace khác với Pod.

Thiết kế mỗi budget cho một nhóm Pod có cùng yêu cầu availability và cùng cách bảo trì. Tránh dùng selector quá chung như app=platform nếu nhóm đó chứa nhiều thành phần độc lập.

## 7. Cordon và drain khác nhau thế nào?

Hai thao tác thường đi cùng nhau khi bảo trì node, nhưng mục đích khác nhau.

**Cordon** đánh dấu node là unschedulable. Scheduler sẽ không đặt Pod mới thông thường lên node đó, nhưng các Pod hiện tại vẫn tiếp tục chạy.

**Drain** yêu cầu di chuyển workload ra khỏi node. Công cụ drain thường cordon node trước, sau đó evict các Pod phù hợp thông qua Eviction API, chờ Pod kết thúc và kiểm tra các điều kiện liên quan.

| Lệnh | Tác động | Pod đang chạy |
|---|---|---|
| kubectl cordon | Ngăn schedule Pod mới lên node | Tiếp tục chạy |
| kubectl drain | Cordon và evict workload có thể di chuyển | Bị kết thúc có kiểm soát theo eviction/grace period |
| kubectl uncordon | Cho phép schedule trở lại | Không tự khởi động lại Pod cũ đã bị evict |

Cordon không phải drain. Nếu chỉ cordon, Pod cũ vẫn chạy và node chưa sẵn sàng để nâng cấp an toàn. Nếu drain, Pod controller-managed thường được tạo lại trên node khác khi đủ tài nguyên.

## 8. kubectl drain và Eviction API

kubectl drain là công cụ phổ biến để chuẩn bị node cho bảo trì. Nó tìm Pod trên node và xử lý chúng theo quy tắc của Kubernetes.

Một quy trình cơ bản:

~~~bash
# Xem node và workload hiện tại
kubectl get nodes -o wide
kubectl get pods -A -o wide --field-selector spec.nodeName=node-a

# Đánh dấu node không nhận Pod mới
kubectl cordon node-a

# Drain node, giữ DaemonSet và xác nhận xóa dữ liệu emptyDir
kubectl drain node-a \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --timeout=20m
~~~

Lệnh trên là ví dụ; phải xác minh node name, workload và dữ liệu trước khi chạy trong môi trường thật.

Các điểm cần hiểu:

- drain dùng Eviction API để evict Pod và tôn trọng PDB nếu không vô hiệu hóa eviction.
- Pod do DaemonSet quản lý thường được giữ lại; dùng ignore-daemonsets để drain tiếp tục.
- Mirror Pod/static Pod không thể được xóa theo cách thông thường bởi drain.
- Pod không được controller quản lý có thể yêu cầu force và có nguy cơ mất workload.
- Pod dùng emptyDir có thể bị mất dữ liệu cục bộ khi bị xóa; delete-emptydir-data là xác nhận chấp nhận rủi ro đó.
- Pod gắn local storage hoặc volume có ràng buộc có thể khiến drain không thể hoàn tất như dự kiến.
- Drain có thể chờ nếu PDB không cho phép eviction.

Không dùng disable-eviction như cách xử lý mặc định khi drain bị chặn. Tùy chọn này bỏ qua Eviction API và có thể vượt qua bảo vệ PDB. Chỉ xem xét khi có đánh giá rủi ro, phương án duy trì dịch vụ và phê duyệt vận hành riêng.

### 8.1. Drain bị PDB chặn

Thông báo thường gặp là không còn disruption allowance hoặc eviction bị từ chối do budget. Trước khi làm gì tiếp theo, kiểm tra:

~~~bash
kubectl get pdb -A
kubectl describe pdb orders-api-pdb -n production
kubectl get pods -n production -l app=orders-api -o wide
kubectl get deploy orders-api -n production
kubectl get nodes
~~~

Đọc currentHealthy, desiredHealthy và disruptionsAllowed. Sau đó xác định:

- Có Pod nào NotReady hoặc đang crash không?
- Deployment đã đạt đủ replicas chưa?
- Pod thay thế có Pending do thiếu CPU/RAM hoặc affinity không?
- Có node khác đủ tài nguyên không?
- Một eviction trước đó có đang diễn ra không?
- PDB selector có chọn nhầm workload không?
- Có nhiều node đang được drain song song không?

Hãy khôi phục replica healthy hoặc bổ sung capacity trước khi tiếp tục. Nếu budget được cấu hình không phù hợp với yêu cầu availability, cần điều chỉnh theo change review và kiểm thử, không sửa nóng chỉ để lệnh drain chạy qua.

## 9. Những Pod cần xử lý đặc biệt khi drain

Không phải mọi Pod đều có thể được di chuyển như nhau.

| Loại Pod | Điều cần kiểm tra |
|---|---|
| Deployment/ReplicaSet | Controller có thể tạo Pod thay thế; cần capacity và readiness |
| StatefulSet | Ordinal, quorum, volume topology và thứ tự khởi động |
| DaemonSet | Thường ở lại node; node replacement sẽ tạo Pod DaemonSet trên node mới |
| Static/mirror Pod | Được kubelet quản lý từ manifest trên node; drain không xóa theo cách thông thường |
| Pod không có controller | Có thể không được tạo lại; cần kiểm tra trước khi force |
| Job/CronJob | Xác định job có thể chạy lại và trạng thái dữ liệu |
| Pod dùng emptyDir | Dữ liệu cục bộ sẽ mất khi Pod bị xóa |
| Pod dùng local PersistentVolume | Có ràng buộc node; không thể đơn giản chuyển sang node khác |
| Pod có extended resource/GPU | Node thay thế phải có accelerator tương thích |

Trước khi drain, kiểm tra các Pod không có owner reference, local volume, hostPath, GPU và workload có state cục bộ. Không mặc định mọi Pod sẽ được controller phục hồi an toàn.

## 10. Graceful termination và thời gian kết thúc Pod

Khi Pod bị eviction, Kubernetes đặt deletion timestamp và bắt đầu quy trình kết thúc. Container có thể chạy preStop hook, sau đó nhận tín hiệu dừng như SIGTERM. Khi hết terminationGracePeriodSeconds, runtime có thể buộc dừng process.

Thời gian grace là ngân sách hữu hạn cho toàn bộ quá trình kết thúc. Nếu preStop kéo dài, phần thời gian còn lại cho ứng dụng xử lý SIGTERM sẽ giảm.

Ứng dụng nên:

1. Chuyển readiness sang false hoặc ngừng nhận traffic mới.
2. Dừng nhận message hoặc job mới.
3. Chờ request đang xử lý hoàn tất trong giới hạn.
4. Commit transaction hoặc checkpoint.
5. Đóng connection pool và consumer.
6. Flush log/metric cần thiết.
7. Thoát trước khi grace period kết thúc.

Readiness, EndpointSlice và load balancer có thể cần thời gian để cập nhật. Ứng dụng cần có cơ chế drain request và xử lý kết nối keep-alive/long-lived connection phù hợp.

### 10.1. Ví dụ cấu hình termination

~~~yaml
spec:
  terminationGracePeriodSeconds: 90
  containers:
    - name: app
      image: registry.example.com/orders-api:2.4.1
      lifecycle:
        preStop:
          exec:
            command: ["/app/bin/begin-drain"]
~~~

Lệnh begin-drain phải tồn tại trong image, có thể chạy lặp an toàn và kết thúc nhanh. Ứng dụng vẫn cần xử lý SIGTERM; preStop không thay thế signal handler.

Không đặt grace period rất dài mà không cân nhắc thời gian drain của node và thời gian nâng cấp. Ngược lại, grace quá ngắn có thể làm request bị cắt hoặc message phải xử lý lại.

## 11. Bảo đảm Pod thay thế có nơi để chạy

PDB có thể cho phép evict một Pod, nhưng không đảm bảo scheduler tìm được node phù hợp cho Pod mới. Nếu cluster không có headroom, Pod thay thế có thể Pending trong thời gian dài.

Trước maintenance, kiểm tra:

- Tổng CPU và memory requests của Pod trên node sắp drain.
- Tài nguyên còn trống ở các node khác.
- Node selector, node affinity và taint/toleration.
- Topology spread và pod anti-affinity.
- GPU, local storage và extended resources.
- Quota namespace và giới hạn của cloud provider.
- Khả năng scale-up node pool và thời gian tạo node.
- PodDisruptionBudget và replica count.

Nên có capacity dự phòng đủ để hấp thụ workload của node đang drain. Với node pool lớn, nâng cấp theo từng batch nhỏ giúp workload được reschedule và xác minh trước khi tiếp tục.

### 11.1. Topology spread

Nếu tất cả replica nằm cùng một zone hoặc node, PDB vẫn có thể cho phép một disruption nhưng ứng dụng vẫn dễ mất availability khi failure domain đó gặp sự cố.

Topology spread constraint giúp phân bố Pod qua các zone hoặc node:

~~~yaml
spec:
  topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: topology.kubernetes.io/zone
      whenUnsatisfiable: DoNotSchedule
      labelSelector:
        matchLabels:
          app: orders-api
~~~

DoNotSchedule buộc scheduler tuân thủ mức phân tán, nhưng Pod có thể Pending nếu không có đủ zone hoặc capacity. Nếu chọn ScheduleAnyway, scheduler ưu tiên phân tán nhưng có thể đặt Pod lệch khi thiếu tài nguyên. Chọn theo SLO và khả năng cung cấp node ở từng zone.

### 11.2. Pod anti-affinity

Pod anti-affinity có thể tránh đặt nhiều replica của cùng ứng dụng lên cùng node hoặc cùng zone. Đây là một cách tăng khả năng chịu lỗi, nhưng rule bắt buộc quá chặt có thể làm Pod không schedule được khi cluster thiếu node.

Cân bằng giữa hard constraint và soft preference. Đối với workload quan trọng, phải kiểm thử tình huống mất một node hoặc zone để xác nhận replica còn lại vẫn đủ phục vụ.

## 12. Quy trình nâng cấp node an toàn

Nâng cấp node thường bao gồm thay đổi image hệ điều hành, kernel, kubelet, container runtime hoặc cấu hình node. Một quy trình an toàn nên chia thành các bước nhỏ, có điểm dừng để kiểm tra.

~~~mermaid
flowchart TD
    A["Lập kế hoạch và kiểm tra PDB"] --> B["Xác minh capacity thay thế"]
    B --> C["Chọn một node / batch nhỏ"]
    C --> D["Cordon node"]
    D --> E["Drain qua Eviction API"]
    E --> F{"Pod đã rời node an toàn?"}
    F -->|Không| G["Điều tra PDB, readiness, storage, capacity"]
    G --> E
    F -->|Có| H["Upgrade hoặc thay node"]
    H --> I["Node Ready và kiểm tra runtime"]
    I --> J["Uncordon nếu tái sử dụng node"]
    J --> K["Xác minh workload và SLO"]
    K --> L{"Tiếp tục batch?"}
    L -->|Có| C
    L -->|Không| M["Kết thúc maintenance"]
~~~

### 12.1. Trước khi nâng cấp

- Xác định node pool, phiên bản đích và phương án rollback.
- Kiểm tra tương thích Kubernetes version, kubelet và container runtime.
- Kiểm tra PDB trong tất cả namespace liên quan.
- Kiểm tra Deployment/StatefulSet replicas và readiness.
- Kiểm tra Pod có local data, local PV, hostPath hoặc GPU.
- Xác minh capacity ở các node còn lại.
- Xác minh quota, subnet IP, instance capacity và image pull.
- Kiểm tra backup, replication và quorum của stateful service.
- Chọn maintenance window và thông báo nhóm vận hành liên quan.
- Thiết lập dashboard và ngưỡng dừng nâng cấp.

### 12.2. Nâng cấp một node

Với node được quản lý thủ công hoặc quy trình thay thế node:

~~~bash
# Xác minh node và workload
kubectl get node node-a
kubectl get pods -A -o wide --field-selector spec.nodeName=node-a

# Cordon
kubectl cordon node-a

# Drain, tôn trọng PDB
kubectl drain node-a \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --timeout=20m
~~~

Sau khi drain hoàn tất, thực hiện nâng cấp hoặc thay thế node theo quy trình của nền tảng. Nếu node được tái sử dụng, kiểm tra kubelet, runtime, CNI, CSI, node condition và version trước khi uncordon.

~~~bash
# Khi node đã được xác minh Ready và đủ điều kiện nhận workload
kubectl get node node-a
kubectl uncordon node-a
~~~

Với managed node group, nhà cung cấp có thể tự tạo node mới, cordon/drain node cũ và thay thế theo rolling strategy. Cần xác minh công cụ managed upgrade có tôn trọng PDB, giới hạn số node unavailable và xử lý Pod disruption như thế nào.

### 12.3. Nâng cấp theo batch

Không drain toàn bộ node pool cùng lúc trừ khi kiến trúc và maintenance plan được thiết kế rõ cho việc đó.

Một chiến lược thường dùng:

1. Thử trên một node canary.
2. Xác minh Pod đã reschedule và SLO ổn định.
3. Nâng cấp một batch nhỏ.
4. Chờ PDB disruptionsAllowed và healthy replicas phục hồi.
5. Xác minh capacity và node health.
6. Tiếp tục batch kế tiếp.
7. Dừng rollout nếu xuất hiện lỗi readiness, Pending Pod, PDB block hoặc latency tăng.

Kích thước batch cần phù hợp với PDB, số replica, capacity dự phòng và thời gian startup của workload.

## 13. Managed node pool, surge và maxUnavailable

Các dịch vụ managed Kubernetes thường có chiến lược nâng cấp node pool riêng. Tên gọi có thể là surge, maxUnavailable, maxSurge hoặc rolling replacement.

- **Surge:** tạo thêm node mới trước khi loại node cũ, giúp duy trì capacity trong quá trình nâng cấp.
- **MaxUnavailable:** giới hạn số node có thể unavailable đồng thời.
- **MaxSurge:** giới hạn số node bổ sung vượt desired size trong quá trình thay thế.
- **Batch size:** số node xử lý trong một đợt.
- **Upgrade strategy:** cách provider thay node, drain workload và xác minh node mới.

Cần phân biệt maxUnavailable của node pool với maxUnavailable trong Deployment hoặc PDB. Chúng điều khiển các lớp khác nhau:

| Cấu hình | Đối tượng điều khiển |
|---|---|
| PDB minAvailable/maxUnavailable | Voluntary eviction của Pod |
| Deployment maxUnavailable/maxSurge | Rolling update của ReplicaSet/Pod |
| Node pool maxUnavailable/maxSurge | Số node bị thay hoặc bổ sung trong upgrade |
| Topology spread | Phân bố Pod qua failure domain |

Một node pool có maxUnavailable lớn hơn khả năng chịu gián đoạn của workload có thể khiến nhiều PDB cùng bị chặn. Ngược lại, maxUnavailable quá thấp có thể kéo dài maintenance. Phải phối hợp cả ba lớp.

### 13.1. Không mặc định provider drain giống nhau

Một số managed service dùng Eviction API và tôn trọng PDB; một số quy trình có thể có timeout, retry hoặc hành vi đặc thù khi PDB không cho phép eviction. Đọc tài liệu của provider và thử trên node pool staging.

Nếu provider cho phép cấu hình timeout hoặc cách xử lý PDB block, đặt theo SLO và quy trình ứng phó. Không dựa vào việc provider sẽ tự bỏ qua PDB khi maintenance kéo dài.

## 14. PDB và Cluster Autoscaler/node autoscaler

Node autoscaler có thể cần loại node khi workload đã được dồn sang nơi khác. Nếu việc loại node cần evict Pod, PDB có thể ngăn hoặc trì hoãn scale-down.

Điều này giúp bảo vệ availability, nhưng cũng có thể khiến node không thể scale-in. Theo dõi:

- Node bị đánh dấu unneeded nhưng không bị xóa.
- PDB disruptionsAllowed bằng 0.
- Pod không thể chuyển do local storage hoặc affinity.
- Pod có priority/daemon behavior đặc biệt.
- Node drain timeout.
- Chi phí node dư thừa do scale-down bị chặn.

Nếu PDB chặn scale-down liên tục, xem lại replica count, selector, workload topology và nhu cầu availability. Không hạ PDB chỉ để tiết kiệm compute khi chưa đánh giá rủi ro dịch vụ.

## 15. Quan sát và chẩn đoán trong maintenance

Các lệnh hữu ích:

~~~bash
# Danh sách PDB trên toàn cluster
kubectl get pdb -A

# Chi tiết một PDB
kubectl describe pdb orders-api-pdb -n production

# Xem Pod theo node
kubectl get pods -A -o wide

# Xem node condition và taint
kubectl describe node node-a

# Theo dõi rollout Deployment
kubectl rollout status deployment/orders-api -n production

# Xem event trong namespace
kubectl get events -n production --sort-by=.lastTimestamp

# Xem Pod Pending/NotReady
kubectl get pods -n production
~~~

Dashboard nên theo dõi:

- PDB currentHealthy, desiredHealthy và disruptionsAllowed.
- Replica desired, ready và available.
- Pod Pending, NotReady và restart count.
- Node Ready/NotReady, cordoned và unschedulable.
- CPU/memory requests, allocatable và headroom.
- Volume attach/detach và mount errors.
- Image pull duration và application startup time.
- Request rate, p95/p99 latency và error rate.
- Queue backlog, active connection và job retry.
- Số node đang upgrade và số node unavailable.

Trong maintenance, quan sát cả hạ tầng lẫn SLO ứng dụng. Node có thể Ready trong khi workload chưa sẵn sàng; Pod có thể Running nhưng readiness fail; PDB có thể được thỏa mãn nhưng latency vẫn tăng do capacity còn lại quá tải.

## 16. Những lỗi thường gặp

**Đặt minAvailable bằng 100% cho workload ít replica:** drain có thể bị chặn hoàn toàn. Tính PDB theo số replica và phương án downtime/failover.

**Dùng PDB như bảo vệ khỏi mọi sự cố:** PDB không ngăn node failure, OOM hoặc xóa trực tiếp. Dùng replica, topology và recovery.

**Drain nhiều node cùng lúc:** nhiều Pod của một workload có thể bị evict trước khi Pod thay thế healthy. Giới hạn batch và chờ budget phục hồi.

**Dùng disable-eviction để vượt PDB:** thao tác có thể làm mất nhiều Pod cùng lúc. Chỉ xem xét theo quy trình ngoại lệ đã đánh giá rủi ro.

**Selector sai:** PDB không bảo vệ Pod hoặc gom nhầm nhiều workload. Kiểm tra label selector trước maintenance.

**Không có capacity để reschedule:** Pod bị evict nhưng Pending. Kiểm tra requests, affinity, quota, node pool và storage.

**Nhầm PDB với Deployment rollout strategy:** PDB không thay thế maxUnavailable/maxSurge của Deployment. Cấu hình cả hai.

**Liveness phụ thuộc database:** lỗi dependency làm container restart hàng loạt. Tách liveness và readiness.

**Grace period quá ngắn:** request hoặc transaction chưa hoàn tất đã bị SIGKILL. Thiết kế graceful shutdown và thời gian drain phù hợp.

**Quên emptyDir và local volume:** dữ liệu tạm có thể mất hoặc Pod không thể chuyển node. Kiểm tra storage trước khi drain.

**Cho rằng PDB ngăn provider thu hồi node:** PDB không thể giữ host đang bị provider dừng. Dùng nhiều replica, zone và capacity thay thế.

**Không theo dõi disruptionsAllowed:** maintenance bắt đầu khi budget đã bằng 0 và bị kẹt. Kiểm tra trạng thái trước mỗi batch.

## 17. Quy trình kiểm thử PDB và node drain

Trước khi áp dụng production, tạo một môi trường staging có số replica, topology và resource request gần với thực tế.

### 17.1. Kiểm thử PDB

1. Tạo workload với số replica dự kiến.
2. Áp dụng readiness probe và PDB.
3. Kiểm tra selector chọn đúng Pod.
4. Xem currentHealthy, desiredHealthy và disruptionsAllowed.
5. Thử eviction một Pod trong môi trường staging.
6. Xác nhận eviction bị từ chối khi budget không còn.
7. Tăng replica hoặc khôi phục Pod healthy.
8. Xác nhận budget phục hồi và eviction tiếp tục được phép.

### 17.2. Kiểm thử drain

1. Chọn một node có workload đại diện.
2. Xem Pod, owner, volume và local data.
3. Cordon node.
4. Drain với timeout phù hợp và không tắt eviction.
5. Theo dõi Pod replacement, PDB và readiness.
6. Xác minh traffic vẫn được phục vụ.
7. Kiểm tra graceful shutdown và log của Pod cũ.
8. Uncordon nếu node được tái sử dụng.
9. Xác minh workload trở lại trạng thái ổn định.

### 17.3. Kiểm thử failure

Mô phỏng trong phạm vi an toàn:

- Một Pod NotReady trước khi drain.
- Một node mất kết nối đột ngột.
- Một Pod có volume gắn theo zone.
- Cluster thiếu CPU/RAM để schedule Pod mới.
- PDB selector không khớp.
- Hai node được yêu cầu drain gần nhau.
- Pod shutdown kéo dài quá grace period.

Đánh giá không chỉ lệnh drain có hoàn tất hay không, mà còn request error, latency, queue backlog, dữ liệu và thời gian phục hồi.

## 18. Checklist nâng cấp node an toàn

- [ ] PDB được tạo trong đúng namespace và selector khớp workload.
- [ ] minAvailable hoặc maxUnavailable phản ánh SLO và số replica.
- [ ] disruptionsAllowed được kiểm tra trước mỗi batch.
- [ ] Deployment rolling strategy được cấu hình riêng với PDB.
- [ ] Stateful workload đã xác minh quorum, leader và volume topology.
- [ ] Pod không có controller, emptyDir, hostPath và local PV đã được kiểm tra.
- [ ] Readiness probe phản ánh khả năng phục vụ thực tế.
- [ ] Ứng dụng xử lý SIGTERM và graceful shutdown.
- [ ] terminationGracePeriodSeconds đủ cho drain request/job.
- [ ] Capacity còn lại đủ schedule Pod sau khi node bị drain.
- [ ] Affinity, taint, topology spread và GPU/storage constraint đã được kiểm tra.
- [ ] Node pool upgrade có maxUnavailable/maxSurge phù hợp.
- [ ] Managed provider drain semantics và timeout đã được xác minh.
- [ ] Maintenance thực hiện theo canary và batch nhỏ.
- [ ] Không dùng disable-eviction để bỏ qua PDB trong quy trình thường lệ.
- [ ] Có dashboard PDB, Pod readiness, node health, capacity và SLO.
- [ ] Có tiêu chí dừng/rollback khi Pod Pending, budget cạn hoặc SLO vi phạm.
- [ ] Đã kiểm thử drain và node replacement trong staging.

PDB đặt giới hạn cho voluntary disruption qua Eviction API; cordon ngăn Pod mới được schedule lên node; drain di chuyển workload ra khỏi node; còn node pool upgrade thay thế hạ tầng theo từng đợt. Muốn bảo trì an toàn, cần phối hợp các cơ chế này với readiness, graceful shutdown, topology và capacity dự phòng. Kiểm tra disruptionsAllowed trước mỗi lần drain, chờ Pod thay thế healthy và xác minh SLO sau từng batch sẽ giúp nâng cấp node có kiểm soát mà vẫn giữ dịch vụ hoạt động ổn định.
