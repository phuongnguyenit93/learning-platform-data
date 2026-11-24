# Requests, limits và cơ chế scheduler bố trí pod

Trong Kubernetes, **requests** và **limits** mô tả nhu cầu và giới hạn tài nguyên của container. Scheduler dùng requests cùng các ràng buộc của workload để chọn node phù hợp cho Pod. Sau khi Pod được gán vào node, kubelet và container runtime trên node mới thực hiện việc tạo container và áp dụng giới hạn tài nguyên.

Hiểu đúng cơ chế này giúp tránh hai tình huống phổ biến: Pod ở trạng thái Pending dù mức sử dụng tài nguyên hiện tại trên node có vẻ thấp, hoặc Pod được lập lịch thành công nhưng sau đó bị CPU throttling, OOMKilled hay eviction. Đây là phần nền tảng khi lựa chọn CPU, bộ nhớ, cấu hình mạng và khả năng mở rộng cho workload chạy trên đám mây.

## 1. Tài nguyên mà Kubernetes quản lý

Với workload thông thường, hai tài nguyên quan trọng nhất là:

- **CPU:** tài nguyên có thể chia sẻ theo thời gian. Kubernetes biểu diễn CPU bằng số core hoặc millicore; 1 CPU tương đương một core, còn 100m tương đương 0,1 CPU.
- **Memory:** bộ nhớ làm việc của container, thường được khai báo bằng đơn vị nhị phân như Mi và Gi. 1Gi tương đương 1024Mi.

Kubernetes cũng hỗ trợ khai báo tài nguyên như ephemeral storage và tài nguyên mở rộng do node cung cấp, chẳng hạn GPU. Mỗi loại có cách lập lịch và thực thi riêng; không nên giả định tất cả đều có hành vi giống CPU.

Tài nguyên được khai báo trong từng container. Khi lập lịch, scheduler xét nhu cầu tổng hợp của Pod, bao gồm các container chạy đồng thời, init container và Pod overhead nếu có. Vì vậy, cần đánh giá tài nguyên ở cấp Pod thay vì chỉ nhìn một container riêng lẻ.

## 2. Requests: nhu cầu dùng để lập lịch

Request là lượng tài nguyên mà container khai báo cần có. Scheduler dùng request để xác định node có đủ năng lực theo sổ sách tài nguyên hay không. Khi một Pod được gán vào node, request cũng tham gia vào cách hệ thống phân chia tài nguyên khi nhiều container cạnh tranh CPU.

Ví dụ:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
~~~

Cấu hình trên khai báo container cần 0,5 CPU và 512Mi bộ nhớ. Điều đó không có nghĩa container luôn tiêu thụ đúng lượng này. Ứng dụng có thể dùng CPU thấp hơn request khi ít tải; CPU có thể tăng cao hơn request nếu node còn tài nguyên và container không bị giới hạn bởi CPU limit.

Request ảnh hưởng trực tiếp đến quyết định bố trí Pod:

- Pod có request CPU 1 và memory 1Gi chỉ phù hợp với node còn đủ cả hai loại tài nguyên theo số liệu allocatable và requests đã được đặt chỗ.
- Node còn nhiều CPU nhưng thiếu memory theo request vẫn không phù hợp.
- Mức sử dụng thực tế thấp không tự làm giảm request đã khai báo.
- Request quá cao có thể làm Pod Pending dù ứng dụng hiếm khi dùng hết tài nguyên.
- Request quá thấp có thể khiến scheduler đặt quá nhiều Pod lên cùng node, làm tăng cạnh tranh và rủi ro khi tải tăng.

Request vì vậy cần phản ánh nhu cầu vận hành hợp lý. Nó là đầu vào của lập lịch và quản lý chia sẻ tài nguyên, không phải phép đo tức thời của ứng dụng.

## 3. Limits: giới hạn tài nguyên thực thi

Limit đặt mức tối đa mà container được phép sử dụng đối với tài nguyên có hỗ trợ giới hạn.

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "1"
    memory: "1Gi"
~~~

Với ví dụ này, container khai báo nhu cầu 0,5 CPU và 512Mi, đồng thời có giới hạn 1 CPU và 1Gi bộ nhớ.

CPU và memory có cách thực thi khác nhau:

| Tài nguyên | Tác dụng của request | Tác dụng của limit | Khi vượt limit |
|---|---|---|---|
| CPU | Dùng để lập lịch và xác định trọng số chia sẻ khi cạnh tranh | Đặt trần sử dụng CPU theo quota | Container bị throttling, thường vẫn chạy nhưng xử lý chậm hơn |
| Memory | Dùng để lập lịch và hỗ trợ đánh giá khi node chịu áp lực bộ nhớ | Đặt giới hạn bộ nhớ theo cgroup | Tiến trình có thể bị OOM kill; container thường được khởi động lại theo restart policy |
| Ephemeral storage | Dùng để tính nhu cầu dung lượng lưu trữ tạm khi lập lịch | Giới hạn mức sử dụng được khai báo và hỗ trợ phát hiện vượt ngưỡng | Pod có thể bị eviction khi vượt giới hạn hoặc node thiếu dung lượng |

CPU limit không giống memory limit. CPU là tài nguyên có thể chia sẻ theo thời gian nên vượt nhu cầu thường dẫn đến throttling. Memory không thể được chia sẻ theo cách tương tự; khi tiến trình vượt giới hạn cgroup, hệ điều hành có thể chấm dứt tiến trình để bảo vệ node.

Nếu không đặt CPU limit, container có thể dùng CPU trống vượt request khi node còn năng lực. Điều này hữu ích với một số dịch vụ nhạy với độ trễ, nhưng cần kiểm soát mức tiêu thụ bằng request phù hợp, quota và chính sách workload. Nếu không đặt memory limit, container có thể tiếp tục tăng bộ nhớ cho đến khi node chịu áp lực và kubelet có thể phải eviction Pod.

Một số quy tắc cần nhớ:

- Nếu chỉ khai báo limit mà bỏ request cho cùng tài nguyên, Kubernetes có thể mặc định request bằng limit khi admission policy không cung cấp giá trị khác.
- LimitRange trong namespace có thể cung cấp request/limit mặc định và áp dụng giới hạn tối thiểu hoặc tối đa.
- ResourceQuota kiểm soát tổng request, limit hoặc số lượng tài nguyên trong namespace.
- Request phải phù hợp với limit nếu cả hai cùng được khai báo; request lớn hơn limit không phải cấu hình hợp lệ.

## 4. Scheduler quyết định đặt Pod ở đâu

Kubernetes scheduler là thành phần control plane theo dõi các Pod chưa được gán node. Scheduler chọn một node phù hợp, sau đó ghi nhận việc gán Pod vào node đó. Kubelet trên node nhận Pod đã được gán và chịu trách nhiệm tạo, giám sát container.

Quy trình khái quát gồm các bước:

~~~mermaid
flowchart TD
    A["Pod chưa được gán node"] --> B["Scheduler nhận Pod"]
    B --> C["Filter: loại node không phù hợp"]
    C --> D{"Có node khả thi?"}
    D -- "Không" --> E["Pod tiếp tục Pending<br/>ghi sự kiện lý do"]
    D -- "Có" --> F["Score: xếp hạng node"]
    F --> G["Chọn node phù hợp nhất"]
    G --> H["Bind Pod vào node"]
    H --> I["Kubelet nhận Pod"]
    I --> J["Tạo container và kiểm tra trạng thái"]
~~~

### 4.1. Filter: xác định node khả thi

Scheduler loại những node không đáp ứng yêu cầu của Pod. Các điều kiện thường gặp gồm:

- **Resource fit:** node còn đủ CPU, memory, ephemeral storage hoặc tài nguyên mở rộng theo requests của Pod.
- **Node selector và node affinity:** Pod chỉ được đặt lên node có nhãn hoặc thuộc nhóm node thỏa điều kiện.
- **Taints và tolerations:** node có taint chỉ nhận Pod có toleration tương ứng.
- **Pod affinity và anti-affinity:** yêu cầu Pod được đặt gần hoặc tránh xa những Pod khác theo nhãn và phạm vi topology.
- **Topology spread constraints:** phân bố Pod qua các vùng hoặc node theo giới hạn chênh lệch đã khai báo.
- **Volume và thiết lập mạng:** một số PersistentVolume, topology của storage, host port hoặc ràng buộc khác có thể làm node không phù hợp.

Một node có đủ CPU và memory vẫn có thể bị loại vì taint, nhãn, vùng lưu trữ hoặc ràng buộc topology. Do đó, khi Pod Pending, không nên chỉ kiểm tra CPU và memory.

### 4.2. Score: xếp hạng các node còn lại

Sau bước Filter, scheduler chấm điểm các node khả thi bằng các plugin và chính sách đang được cấu hình. Điểm số có thể phản ánh mức cân bằng tài nguyên, affinity, topology spread, mức độ phù hợp với volume hoặc các mục tiêu lập lịch khác.

Node có điểm cao hơn được ưu tiên. Kết quả không có nghĩa scheduler luôn chọn node còn nhiều CPU nhất. Mục tiêu là thỏa các ràng buộc và tối ưu theo tập chính sách đang hoạt động trong cluster.

### 4.3. Bind và khởi chạy Pod

Sau khi chọn node, scheduler bind Pod vào node đó. Kubelet trên node thực hiện các bước tiếp theo như chuẩn bị volume, tải image, tạo container và theo dõi readiness/liveness probe.

Scheduler không trực tiếp khởi chạy tiến trình trong container. Pod đã có nodeName nhưng container vẫn có thể chưa chạy do image pull lỗi, thiếu secret, volume mount thất bại hoặc cấu hình runtime sai. Vì vậy, cần phân biệt lỗi lập lịch với lỗi khởi động sau khi lập lịch.

## 5. Scheduler tính tài nguyên Pod như thế nào?

Scheduler so sánh tổng nhu cầu tài nguyên của Pod với phần **allocatable** còn lại trên node. Với Pod có nhiều container ứng dụng chạy đồng thời, request của các container này được cộng lại theo từng loại tài nguyên.

Với init container kiểu chạy rồi kết thúc, request hiệu lực của Pod còn phải tính đến init container có nhu cầu lớn nhất so với tổng nhu cầu của các container ứng dụng chạy đồng thời. Pod overhead, nếu được khai báo, cũng được cộng vào phép tính. Các trường hợp init container có thể chạy lâu dài như sidecar có quy tắc tính riêng theo phiên bản và cấu hình Kubernetes.

Ví dụ một Pod có hai container ứng dụng:

| Container | CPU request | Memory request |
|---|---:|---:|
| API | 500m | 512Mi |
| Log sidecar | 100m | 128Mi |
| Tổng của hai container chạy đồng thời | 600m | 640Mi |

Scheduler cần tìm node còn ít nhất 600m CPU và 640Mi memory theo tài nguyên có thể lập lịch, trước khi xét các ràng buộc khác. Nếu Pod còn init container hoặc overhead, nhu cầu hiệu lực có thể cao hơn con số tổng đơn giản trong bảng.

### Allocatable khác Capacity

Node báo cáo hai khái niệm quan trọng:

- **Capacity:** tổng tài nguyên mà node có.
- **Allocatable:** phần tài nguyên node dành cho Pod sau khi trừ phần dành cho hệ điều hành, kubelet, runtime và các khoản dự phòng theo cấu hình.

Scheduler dựa vào allocatable để lập lịch. Ví dụ node có 8 CPU capacity nhưng chỉ 7 CPU allocatable thì Pod không thể yêu cầu đủ 7,5 CPU chỉ vì nhìn thấy capacity là 8.

Ngoài ra, scheduler theo dõi requests đã được gán trên node. Nó không chỉ nhìn mức dùng CPU hoặc memory tại thời điểm Pod mới được tạo. Đây là lý do node có thể hiển thị CPU usage thấp nhưng vẫn không nhận Pod mới: tổng requests đã chiếm phần allocatable còn lại.

## 6. Ví dụ: vì sao Pod vẫn Pending?

Giả sử một node có:

- CPU allocatable: 4 CPU.
- Memory allocatable: 8Gi.
- Các Pod đang được gán đã khai báo tổng request: 3,2 CPU và 6,5Gi memory.

Phần còn lại theo sổ sách lập lịch là 0,8 CPU và 1,5Gi memory. Một Pod mới yêu cầu 1 CPU và 1Gi memory. Dù memory còn đủ, CPU còn lại chỉ 0,8 nên node không đạt điều kiện resource fit. Pod sẽ không được đặt lên node đó.

~~~text
Node allocatable
CPU:    4.0 CPU
Memory: 8.0 Gi

Requests đã được đặt
CPU:    3.2 CPU
Memory: 6.5 Gi

Pod mới yêu cầu
CPU:    1.0 CPU
Memory: 1.0 Gi

Kết quả
CPU còn 0.8 CPU  -> không đủ
Memory còn 1.5 Gi -> đủ
Node bị loại ở bước Filter vì thiếu CPU
~~~

Nếu tất cả node đều không đủ CPU theo requests, Pod tiếp tục Pending và sự kiện thường có thông báo như **Insufficient cpu**. Giảm request chỉ để Pod được lập lịch có thể che giấu thiếu hụt thật. Trước khi điều chỉnh, cần xác định request có bị đặt quá cao, node có cần mở rộng, workload có thể scale hoặc cần chuyển sang node pool khác hay không.

## 7. Ví dụ cấu hình Pod có requests và limits

Manifest sau minh họa một API cần 0,5 CPU, 512Mi bộ nhớ và 1Gi dung lượng lưu trữ tạm. Limit cho phép CPU tăng tối đa 1 core, bộ nhớ tối đa 1Gi và lưu trữ tạm tối đa 2Gi.

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: checkout-api
  namespace: production
  labels:
    app: checkout-api
spec:
  containers:
    - name: api
      image: registry.example.com/checkout-api:v2
      ports:
        - name: http
          containerPort: 8080
      resources:
        requests:
          cpu: "500m"
          memory: "512Mi"
          ephemeral-storage: "1Gi"
        limits:
          cpu: "1"
          memory: "1Gi"
          ephemeral-storage: "2Gi"
~~~

Áp dụng manifest:

~~~bash
kubectl apply -f checkout-api-pod.yaml
kubectl get pod checkout-api -n production -o wide
kubectl describe pod checkout-api -n production
~~~

Trong môi trường thật, workload dài hạn thường được khai báo qua Deployment hoặc StatefulSet thay vì tạo Pod độc lập. Controller sẽ tạo các Pod theo số bản sao mong muốn; mỗi Pod vẫn mang requests và limits tương ứng để scheduler lập lịch.

Nếu muốn phân bố ba bản sao API qua các node hoặc vùng, có thể khai báo topology spread constraints trong Pod template. Cần chọn topology key, selector nhãn và hành vi khi không thể thỏa điều kiện. Ràng buộc càng chặt thì khả năng phân bố càng rõ, nhưng cũng có thể làm Pod Pending khi cluster thiếu node ở một vùng.

## 8. QoS class và hành vi khi node thiếu tài nguyên

Kubernetes phân Pod thành ba Quality of Service class dựa trên cấu hình tài nguyên của tất cả container:

| QoS class | Điều kiện cơ bản | Ý nghĩa vận hành |
|---|---|---|
| Guaranteed | Mỗi container khai báo CPU và memory request, limit; request bằng limit cho từng tài nguyên | Mức ưu tiên bảo vệ cao hơn trong một số tình huống node pressure |
| Burstable | Có ít nhất một request hoặc limit nhưng không đáp ứng điều kiện Guaranteed | Có thể dùng vượt request trong giới hạn cho phép |
| BestEffort | Không container nào khai báo CPU hoặc memory request/limit | Không có request tài nguyên để scheduler dựa vào cho CPU/memory |

QoS class ảnh hưởng đến cách kubelet xem xét Pod khi node chịu áp lực tài nguyên, nhưng không thay thế requests, limits, priority hoặc cấu hình lập lịch. Khi cần eviction, kubelet còn xét mức sử dụng so với request và Pod Priority. Không nên hiểu Guaranteed là bảo đảm Pod không bao giờ bị dừng.

Cần phân biệt hai tình huống:

- **OOMKilled:** container vượt memory limit và tiến trình bị hệ điều hành chấm dứt. Pod có thể vẫn ở trạng thái Running trong khi container được restart, tùy restart policy.
- **Evicted:** kubelet chấm dứt Pod để giải phóng tài nguyên khi node chịu áp lực như thiếu memory hoặc dung lượng đĩa. Pod do Deployment quản lý thường được controller tạo bản thay thế nếu còn đủ điều kiện.

Với workload quan trọng, hãy đặt request sát với nhu cầu vận hành, đặt memory limit có khoảng dự phòng phù hợp, cấu hình priority theo mức độ quan trọng và bảo đảm cluster có năng lực dự phòng.

## 9. Đánh đổi khi chọn requests và limits

**CPU request quá thấp** khiến scheduler có thể xếp nhiều Pod lên một node. Khi tải tăng, các container cạnh tranh CPU và độ trễ có thể tăng. **CPU request quá cao** làm giảm mật độ Pod và có thể khiến workload Pending dù CPU thực tế chưa dùng hết.

**CPU limit quá thấp** có thể gây throttling ngay cả khi node còn CPU trống. Với dịch vụ nhạy với độ trễ, một CPU limit chặt có thể làm tăng latency. Bỏ CPU limit có thể giảm throttling nhưng cần kiểm soát tổng requests, quota và mức độ tin cậy giữa các workload.

**Memory request quá thấp** làm scheduler đánh giá thấp nhu cầu của Pod và có thể xếp quá nhiều workload lên cùng node. Khi tải tăng, node dễ chịu memory pressure. **Memory limit quá thấp** khiến container bị OOMKilled; limit quá cao hoặc không có limit làm tăng rủi ro một workload tiêu thụ bộ nhớ ảnh hưởng các Pod khác.

**Ephemeral storage** cũng cần được theo dõi với workload ghi log, cache hoặc file tạm. Nếu không khai báo request/limit phù hợp, node có thể cạn dung lượng đĩa và kubelet phải eviction Pod.

Một số khuyến nghị khi sizing:

1. Đo CPU và memory trong điều kiện tải đại diện, gồm cả giờ cao điểm và tác vụ nền.
2. Dùng request CPU phản ánh nhu cầu bình thường và mức chia sẻ cần thiết; theo dõi throttling trước khi tăng limit.
3. Đặt memory request theo working set thực tế và memory limit có khoảng dự phòng cho burst hợp lý.
4. Kiểm tra mức sử dụng theo từng container, vì sidecar cũng tiêu thụ tài nguyên của Pod.
5. Xem xét HPA: mục tiêu CPU utilization theo phần trăm được tính tương quan với CPU request. Nếu thiếu request CPU cho container liên quan, autoscaling theo CPU có thể không tính được utilization mong muốn.
6. Đối chiếu requests với ResourceQuota, LimitRange và năng lực allocatable của node pool.
7. Với GPU hoặc tài nguyên mở rộng, kiểm tra node có quảng bá đúng resource name và số lượng thiết bị còn khả dụng.

## 10. Xác minh và xử lý sự cố lập lịch

Khi Pod Pending, bắt đầu bằng mô tả Pod để xem sự kiện và lý do scheduler từ chối node:

~~~bash
kubectl describe pod checkout-api -n production
kubectl get events -n production --sort-by=.metadata.creationTimestamp
~~~

Tìm các thông báo như **Insufficient cpu**, **Insufficient memory**, **node(s) had untolerated taint**, **didn't match Pod's node affinity/selector** hoặc lỗi liên quan đến volume. Mỗi thông báo dẫn đến một hướng kiểm tra khác nhau.

Xem tài nguyên node và requests đã được đặt:

~~~bash
kubectl describe node NODE_NAME
kubectl get nodes
~~~

Trong phần Allocated resources của lệnh describe node, đối chiếu tổng requests và limits với allocatable. Phần này giúp hiểu tại sao scheduler đánh giá node đã hết khả năng nhận thêm Pod.

Để xem mức dùng thực tế, có thể dùng Metrics Server:

~~~bash
kubectl top nodes
kubectl top pods -n production
kubectl top pod checkout-api -n production --containers
~~~

**kubectl top** phản ánh mức sử dụng tại thời điểm đo, không phải tổng requests mà scheduler đã đặt. Hãy kết hợp kết quả này với **kubectl describe node** và **kubectl describe pod** để phân biệt thiếu năng lực theo requests với tình trạng ứng dụng đang tiêu thụ nhiều tài nguyên.

Nếu container bị OOMKilled hoặc restart liên tục, kiểm tra trạng thái và log trước đó:

~~~bash
kubectl get pod checkout-api -n production
kubectl describe pod checkout-api -n production
kubectl logs checkout-api -n production --previous
~~~

Nếu Pod đã được gán node nhưng không khởi động, kiểm tra image pull, secret, volume mount, runtime event và probe. Đó là lỗi sau bước lập lịch; tăng CPU request không giải quyết được nguyên nhân này.

## 11. Checklist cấu hình và vận hành

- [ ] Đã khai báo CPU và memory request cho từng container theo số liệu đo được.
- [ ] Đã đặt CPU và memory limit theo yêu cầu độ trễ, độ ổn định và mức độ chia sẻ tài nguyên.
- [ ] Đã tính cả sidecar, init container và Pod overhead khi ước lượng nhu cầu Pod.
- [ ] Đã đối chiếu request với allocatable, không chỉ với capacity của node.
- [ ] Đã kiểm tra node selector, affinity, taints/tolerations, topology spread và ràng buộc volume.
- [ ] Đã xem xét LimitRange và ResourceQuota của namespace.
- [ ] Đã kiểm tra QoS class, Pod Priority và hành vi khi node chịu memory hoặc disk pressure.
- [ ] Đã đo mức sử dụng thực tế và phân biệt metric runtime với requests scheduler đang tính.
- [ ] Đã xác minh HPA có đủ CPU request để tính utilization nếu autoscaling theo CPU.
- [ ] Khi Pod Pending hoặc restart, đã đọc event, trạng thái container và log trước khi điều chỉnh tài nguyên.

Requests cho scheduler biết Pod cần bao nhiêu tài nguyên để được bố trí; limits kiểm soát mức sử dụng khi container chạy. Scheduler kết hợp requests với các ràng buộc về node, topology, volume và chính sách để chọn nơi đặt Pod. Cấu hình tốt cần phản ánh đúng nhu cầu ứng dụng, để cluster vừa tận dụng được năng lực tính toán vừa duy trì độ ổn định khi tải thay đổi.
