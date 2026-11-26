# Đánh giá tính sẵn sàng, khả năng mở rộng và chi phí vận hành

## Mục tiêu và phạm vi

Trong chương **Discovery Server** của module **SPRING_CLOUD_KUBERNETES**, việc đưa một server discovery vào hệ thống cần được đánh giá như một quyết định vận hành. Nó tập trung đường đọc Kubernetes API và cung cấp dữ liệu qua HTTP, đồng thời tạo thêm một thành phần mà ứng dụng có thể phụ thuộc.

Bài này giúp bạn:

- Xác định thế nào là discovery hoạt động đúng, ngoài việc Pod đang Running.
- Thiết kế và kiểm chứng khả năng chịu lỗi của nhiều replica.
- Ước lượng tải HTTP, bộ nhớ, tải Kubernetes API và tài nguyên dự phòng.
- Tính các nhóm chi phí để quyết định có cần Discovery Server hay không.

Mọi số liệu dung lượng, độ trễ và tài nguyên trong bài đều là **giả định phục vụ tính toán**, không phải benchmark, mặc định sản phẩm hay cam kết hiệu năng. Ví dụ dùng Discovery Server sau Kubernetes Service `kubernetes-discovery` trong namespace `platform`, phục vụ các ứng dụng cần khám phá dịch vụ trong namespace `demo`.

## 1. Xác định đúng thành phần đang được đánh giá

Discovery Server cung cấp các endpoint HTTP như `/apps` và `/apps/{name}`. Nó sử dụng Kubernetes API để lấy dữ liệu discovery và cần quyền đọc phù hợp. Ứng dụng dùng HTTP DiscoveryClient có thể lấy thông tin qua server này. [Tài liệu Spring Cloud Kubernetes Discovery Server](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-discoveryserver.html)

~~~mermaid
flowchart LR
    A[Ứng dụng và HTTP DiscoveryClient] --> B[Kubernetes Service]
    B --> C[Discovery Server Pod A]
    B --> D[Discovery Server Pod B]
    C --> E[Kubernetes API và dữ liệu endpoint]
    D --> E
    A --> F[Instance nghiệp vụ được chọn]
~~~

Hai đường cần đánh giá riêng:

~~~text
Đường discovery:
ứng dụng -> Service của Discovery Server -> dữ liệu discovery

Đường nghiệp vụ:
ứng dụng -> instance hoặc Service nghiệp vụ
~~~

Discovery Server không mặc nhiên proxy các request nghiệp vụ. Việc server vẫn trả danh mục không chứng minh ứng dụng gọi được mọi địa chỉ trong đó. Ngược lại, một kết nối nghiệp vụ đang hoạt động có thể tiếp tục phục vụ một thời gian dù lần cập nhật discovery mới bị lỗi.

Vì vậy, cần đo cả chất lượng discovery và tác động của nó lên ứng dụng sử dụng, thay vì đồng nhất mọi lỗi nghiệp vụ với lỗi server discovery.

## 2. Định nghĩa tính sẵn sàng theo dữ liệu dùng được

Một Pod Running mới cho biết trạng thái tiến trình ở mức Kubernetes. Một HTTP 200 mới cho biết request có phản hồi thành công ở tầng HTTP. Với discovery, còn cần dữ liệu đúng cấu trúc, đúng phạm vi và đủ mới cho mục đích sử dụng.

| Chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| Tỷ lệ request discovery thành công | Client có lấy được phản hồi hợp lệ không? |
| Độ trễ p95/p99 | Phần đuôi phân phối có làm ứng dụng chờ quá lâu không? |
| Độ trễ cập nhật endpoint | Thay đổi nguồn mất bao lâu để tới server và ứng dụng? |
| Mức lệch dữ liệu giữa các replica | Hai Pod server có đưa ra tập đích khác nhau quá lâu không? |
| Tuổi dữ liệu khi phục vụ dự phòng | Client đang dùng dữ liệu cũ trong giới hạn nào? |
| Thời gian phục hồi | Sau sự cố, khi nào danh mục và ứng dụng trở lại hành vi chấp nhận được? |

Ví dụ một nhóm tự đặt mục tiêu thử nghiệm:

~~~text
Cửa sổ đánh giá:                    30 ngày
Tỷ lệ request discovery đạt yêu cầu: >= 99,9%
Ngưỡng độ trễ cho request đó:        <= 300 ms
Ngưỡng hội tụ sau thay đổi endpoint: <= 60 giây
~~~

Các ngưỡng trên phải được chọn theo nhu cầu ứng dụng và dữ liệu đo. Nếu tính theo request, ngân sách lỗi là tối đa `0,1%` số request trong cửa sổ, không tự động tương đương một số phút gián đoạn cố định.

Nếu dùng thước đo theo thời gian, `99,9%` của một tháng đúng 30 ngày tương ứng khoảng `43,2 phút` không đạt yêu cầu. Đây là một cách đo khác; phải ghi rõ cách tính trước khi báo cáo.

Không coi danh sách rỗng luôn là lỗi. Một Service có thể hợp lệ nhưng chưa có backend, hoặc phạm vi discovery có thể thật sự không có dịch vụ. Với dịch vụ kiểm tra đã được biết trước là phải có instance, việc đột ngột không thấy instance mới là tín hiệu cần điều tra.

### Độ mới không chỉ là thời gian nhận HTTP

Client vừa nhận phản hồi không có nghĩa dữ liệu Kubernetes bên trong vừa được xác nhận là mới. Server có thể trả cache cũ khi đường đồng bộ nguồn gặp lỗi.

Cũng không nên báo dữ liệu cũ chỉ vì đã lâu không có sự kiện endpoint: hệ thống ổn định có thể không thay đổi trong nhiều giờ. Cần kết hợp trạng thái đồng bộ nguồn, lỗi kết nối/watch và phép đo hội tụ từ thay đổi có kiểm soát.

Các chỉ số về độ mới có thể cần bổ sung instrumentation hoặc phép kiểm tra bên ngoài; không mặc định image server đã xuất sẵn mọi metric trong bảng.

## 3. Phân tích các miền lỗi trước khi tăng replica

| Sự cố | Nhiều Pod có thể giúp gì? | Phần còn phải xử lý |
| --- | --- | --- |
| Một tiến trình server chết | Pod khác có thể tiếp tục phục vụ | Phát hiện lỗi, rút endpoint và năng lực Pod còn lại |
| Một node mất kết nối | Có ích nếu còn Pod ở node khác | Placement thực tế và tài nguyên trên node khác |
| Một zone bị gián đoạn | Có ích nếu các replica và phụ thuộc được phân bố phù hợp | DNS, mạng, capacity và đường tới Kubernetes API |
| Kubernetes API tạm không truy cập được | Dữ liệu đã có có thể giúp duy trì một phần hoạt động | Giới hạn độ cũ và việc đồng bộ trở lại |
| RBAC hoặc bộ lọc cấu hình sai | Các replica có thể cùng sai | Sửa cấu hình/quyền và xác minh dữ liệu nguồn |
| Tải HTTP tăng đột biến | Có thể chia tải | Quota, khởi động, phân phối kết nối và giới hạn chung |
| Một phiên bản mới gây lỗi | Replica cũ có thể giúp nếu rollout còn giữ chúng | Phát hiện lỗi sớm và cách quay lại phiên bản trước |

Hai Pod trên cùng node không bảo vệ được trước việc node đó mất. Hai Pod khác node nhưng cùng zone vẫn có miền lỗi chung ở cấp zone. [Tài liệu topology spread của Kubernetes](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/)

Mọi replica cùng dùng một cấu hình sai hoặc cùng mất quyền đọc API có thể phục vụ kết quả sai giống nhau. Đây là lý do không thể tính tính sẵn sàng của toàn hệ thống chỉ bằng số Pod.

Trong một mô hình toán học rất đơn giản, nếu mỗi replica có độ sẵn sàng `A` và lỗi độc lập hoàn toàn, một cụm hai replica còn ít nhất một replica hoạt động với xác suất:

~~~text
A_hai_replica = 1 - (1 - A)^2
~~~

Nếu `A = 0,99`, công thức cho `0,9999`. Kết quả chỉ minh họa lợi ích của dự phòng độc lập; nó bỏ qua mọi phụ thuộc chung, dữ liệu cũ và thiếu năng lực. Không dùng con số đó thay cho SLO đã đo từ phía client.

## 4. Thiết kế nhiều replica phải đi cùng hành vi khởi động và cập nhật

### 4.1. Một Service ổn định trước nhiều Pod

Client nên có một địa chỉ bootstrap ổn định, chẳng hạn:

~~~text
http://kubernetes-discovery.platform.svc.cluster.local:80
~~~

Service chọn những Pod server đủ điều kiện làm backend. Không cấu hình client gắn cố định vào IP của một Pod server nếu mục tiêu là chịu được việc Pod được thay thế.

Các replica cần nhất quán về namespace, bộ lọc, chính sách readiness của endpoint và phiên bản tương thích với client. Tuy vậy, không mặc định cache của các replica luôn có cùng trạng thái ở mọi thời điểm.

Khi client có connection pool hoặc giữ kết nối lâu, các request có thể phân phối không đều giữa Pod. Đánh giá số request và độ trễ theo từng replica, không chỉ nhìn trung bình toàn Deployment.

### 4.2. Probe cần phản ánh đúng trách nhiệm

Kubernetes phân biệt startup, readiness và liveness probe. Startup probe bảo vệ thời gian khởi động; readiness quyết định khả năng tham gia phục vụ; liveness có thể dẫn tới khởi động lại container khi lỗi kéo dài. [Tài liệu probe của Kubernetes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)

Đối với Discovery Server:

- **Startup:** cho Java và quá trình khởi tạo đủ thời gian trước khi các probe khác can thiệp.
- **Readiness:** không nhận traffic khi thành phần chưa đủ điều kiện phục vụ theo chính sách đã chọn.
- **Liveness:** phát hiện tiến trình cần khởi động lại, tránh gắn trực tiếp mọi lỗi phụ thuộc tạm thời vào điều kiện này.

Không mặc định endpoint health readiness có sẵn đã chứng minh cache discovery đủ mới. Phải kiểm tra các health contributor thực tế của image và cấu hình đang dùng; nếu muốn readiness phụ thuộc đồng bộ dữ liệu, cần thiết kế và đo riêng điều kiện đó.

Nếu cứ mất Kubernetes API là liveness fail, toàn bộ replica có thể cùng bị restart, làm mất dữ liệu đã nạp và tạo thêm tải khởi tạo. Restart cũng không sửa được quyền RBAC sai.

### 4.3. Rolling update và gián đoạn tự nguyện

Deployment quản lý số Pod có thể unavailable và số Pod tăng thêm trong rolling update qua `maxUnavailable` và `maxSurge`. [Tài liệu Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#rolling-update-deployment)

PodDisruptionBudget giúp giới hạn gián đoạn qua những thao tác tôn trọng Eviction API, như một số trường hợp drain node. Nó không chặn được node hỏng, không bảo vệ mọi thao tác xóa trực tiếp và không thay thế chiến lược rolling update của Deployment. [Tài liệu disruptions và PDB](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/)

Giữ một Pod available chưa chắc đủ đáp ứng tải. Nếu một Pod chỉ phục vụ được một nửa tải yêu cầu, PDB cho phép còn một Pod vẫn có thể dẫn tới vi phạm SLO.

## 5. Ví dụ cấu hình để thảo luận khả năng chịu lỗi

Manifest dưới đây minh họa hai replica, probe, tài nguyên, Service và PDB. Nó **chưa phải cấu hình hoàn chỉnh để triển khai nguyên trạng**: image là giá trị thay thế; ServiceAccount cùng RBAC phải tồn tại, namespace phải được chuẩn bị và các endpoint health phải phù hợp với image được chọn.

Các tài nguyên CPU, bộ nhớ và thời gian probe chỉ là điểm bắt đầu cho phép đo.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kubernetes-discovery
  namespace: platform
spec:
  replicas: 2
  minReadySeconds: 10
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: kubernetes-discovery
  template:
    metadata:
      labels:
        app: kubernetes-discovery
    spec:
      serviceAccountName: discovery-reader
      terminationGracePeriodSeconds: 30
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: kubernetes-discovery
      containers:
        - name: discovery-server
          image: registry.example.com/platform/discovery-server:approved-version
          ports:
            - name: http
              containerPort: 8761
          env:
            - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_ALL_NAMESPACES
              value: "false"
            - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_NAMESPACES_0
              value: "demo"
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 1Gi
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
---
apiVersion: v1
kind: Service
metadata:
  name: kubernetes-discovery
  namespace: platform
spec:
  selector:
    app: kubernetes-discovery
  ports:
    - name: http
      port: 80
      targetPort: http
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: kubernetes-discovery
  namespace: platform
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: kubernetes-discovery
~~~

Những điểm cần diễn giải đúng:

- `replicas: 2` là ví dụ cơ chế, không phải kết luận hai Pod đủ cho mọi tải.
- Topology spread phụ thuộc các node/domain đủ điều kiện. Cụm chỉ có một node không tự xuất hiện node thứ hai; phải xác minh placement thực tế.
- Nếu yêu cầu bắt buộc mỗi Pod ở node khác nhau, cần xét thêm ràng buộc placement phù hợp và tác động tới scheduling/rollout.
- `maxSurge: 1` cần chỗ cho Pod tăng thêm, kể cả CPU, bộ nhớ và thời gian nạp dữ liệu.
- `terminationGracePeriodSeconds` không tự cấu hình graceful shutdown của ứng dụng. Cần kiểm tra hành vi shutdown, rút endpoint và kết nối đang phục vụ.
- ServiceAccount ở `platform` phải được cấp quyền phù hợp để đọc dữ liệu `demo`. Namespace cấu hình không tự cấp quyền.

Không chỉ kiểm tra YAML hợp lệ; mục tiêu là Pod còn lại thực sự phục vụ được trong khi một Pod khác khởi động, dừng hoặc mất kết nối.

## 6. Mô hình hóa tải trước khi chọn số replica

### 6.1. Tải HTTP từ ứng dụng

Một mô hình đơn giản:

~~~text
Q_http = N / T + L

N: số client lấy toàn danh mục định kỳ
T: chu kỳ lấy danh mục, tính bằng giây
L: số request tra từng dịch vụ mỗi giây phát sinh thêm
~~~

Ví dụ giả định:

~~~text
N = 200 client
T = 30 giây
L = 40 request/giây

Q_http = 200 / 30 + 40
       ≈ 46,67 request/giây
~~~

Công thức chưa tính retry, watcher, tải kiểm tra sức khỏe, khởi động đồng loạt hoặc các request khác. Nó cũng giả định chu kỳ được trải đều. Nếu 200 client cùng làm mới vào đầu mỗi chu kỳ, đỉnh tải có thể lớn hơn nhiều so với giá trị trung bình.

Có thể giảm tải không cần thiết bằng cách chỉ truy vấn dịch vụ cần dùng, chọn cơ chế cache phù hợp và tránh làm mới đồng loạt. Không tự tăng chu kỳ nếu điều đó làm vượt giới hạn độ mới mà ứng dụng chấp nhận.

### 6.2. Số request không phản ánh hết kích thước phản hồi

Giả sử:

~~~text
Phản hồi /apps:               250 kB
Phản hồi /apps/catalog-api:     5 kB
Quy ước:                      1 kB = 1.000 byte
~~~

Với tải ở trên:

~~~text
Băng thông body trung bình
    ≈ (200 / 30) × 250 + 40 × 5
    ≈ 1.866,67 kB/giây
    ≈ 1,87 MB/giây
~~~

Đây là lượng body chưa tính header, TLS, nén, retry và khác biệt thực tế giữa dịch vụ. Không đổi trực tiếp con số này thành phí egress: traffic trong node, qua node, qua zone hoặc ra ngoài cụm có cách hạch toán khác nhau.

Một vài request toàn danh mục lớn có thể tốn CPU serialize JSON, heap và mạng nhiều hơn rất nhiều request tra một dịch vụ nhỏ.

### 6.3. Chọn năng lực còn lại khi có lỗi

Gọi `C_slo` là số request/giây một Pod có thể phục vụ mà vẫn đạt SLO, với đúng dạng dữ liệu và tài nguyên đã đo. Gọi `F` là số Pod dự kiến có thể mất đồng thời.

Điều kiện dung lượng sơ bộ:

~~~text
(R - F) × C_slo >= Q_peak
~~~

Hay:

~~~text
R >= ceil(Q_peak / C_slo) + F
~~~

Ví dụ một phép đo giả định cho `C_slo = 120 request/giây` và cần chịu `Q_peak = 300 request/giây` khi mất một Pod:

~~~text
R >= ceil(300 / 120) + 1
R >= 4
~~~

Trong ví dụ này, hai replica của manifest trước không đủ để đạt yêu cầu ở đỉnh tải đã nêu. Phải điều chỉnh số replica nền, tài nguyên hoặc nhu cầu tải trước khi coi thiết kế đạt yêu cầu.

Phép tính giả định tải được chia tương đối đều và không có nút thắt chung khác. Với kết nối lệch tải, payload khác nhau hoặc Kubernetes API gặp vấn đề, cần đo lại thay vì chỉ áp dụng công thức.

## 7. Mở rộng ngang có giới hạn và có chi phí nhân bản dữ liệu

Thêm Pod có thể giúp chia tải HTTP, nhưng mỗi replica có thể cần giữ dữ liệu discovery của cùng phạm vi. Vì vậy, bộ nhớ toàn hệ thống thường không giảm theo cách chia đều số endpoint cho số replica.

Một mô hình dung lượng sơ bộ:

~~~text
M_mỗi_Pod ≈ M_nền_JVM + M_danh_mục + M_xử_lý_request

M_toàn_bộ ≈ R × M_mỗi_Pod
~~~

Đây là mô hình lập kế hoạch, không phải công thức nội bộ của Spring Cloud Kubernetes. Cần đo heap, bộ nhớ ngoài heap, connection buffer và hành vi GC theo image thực tế.

Các replica cũng có thể tạo thêm công việc đọc/đồng bộ Kubernetes API. Không mặc định cứ một request `/apps` là một request tới API, và cũng không mặc định tăng gấp đôi Pod không ảnh hưởng API server.

Những hướng tối ưu có tác động khác nhau:

| Điều chỉnh | Lợi ích có thể có | Điều phải đánh đổi |
| --- | --- | --- |
| Thu hẹp namespace hoặc tập Service | Giảm dữ liệu cần khám phá và phục vụ | Client chỉ thấy phạm vi được chọn |
| Thêm replica | Chia tải HTTP, thêm dự phòng | Thêm JVM, cache, kết nối và công việc khởi tạo |
| Tăng CPU/bộ nhớ mỗi Pod | Giảm nghẽn xử lý hoặc áp lực GC nếu đúng nguyên nhân | Tăng tài nguyên và thời gian cấp phát |
| Cache phía client | Giảm request lặp lại | Dữ liệu có thể cũ lâu hơn |
| Giới hạn retry và thêm khoảng chờ | Giảm khuếch đại tải khi lỗi | Một số thao tác có thể thất bại sớm hơn |
| Giảm metadata không cần dùng | Có thể giảm payload | Phải giữ metadata mà client cần |

Với HTTP discovery, phạm vi namespace và lọc dữ liệu cần cấu hình tại Discovery Server, nơi đọc Kubernetes API. [Cấu hình Kubernetes DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html)

### Ví dụ HPA

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: kubernetes-discovery
  namespace: platform
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: kubernetes-discovery
  minReplicas: 2
  maxReplicas: 6
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60
~~~

HPA dùng CPU utilization cần resource request phù hợp và hạ tầng metrics hoạt động. Mốc `60%` được tính tương ứng với CPU request, không phải mặc nhiên 60% của CPU limit hay cả node. [Tài liệu HPA](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/)

Ví dụ HPA vẫn dùng min hai Pod để minh họa. Nếu yêu cầu đã tính cần bốn Pod có sẵn ngay khi đỉnh tải đến, không thể giữ `minReplicas: 2` rồi coi HPA bảo đảm không vi phạm SLO. Phải tính cả thời gian phát hiện tải, scheduling, khởi động JVM và đồng bộ dữ liệu.

CPU cũng có thể không phải nút thắt: bộ nhớ chứa danh mục, độ trễ nguồn hoặc connection pool có thể chi phối trước. Chọn metric bổ sung chỉ khi có phép đo và hạ tầng metric tương ứng.

Khi HPA quản lý số replica, tránh để công cụ triển khai liên tục ghi đè `spec.replicas` về một con số cố định. Giới hạn `maxReplicas` phải phù hợp quota, node capacity và tải tăng thêm lên Kubernetes API.

## 8. Tính chi phí vận hành theo nhiều lớp

### 8.1. Chi phí tài nguyên dành cho server

Giả sử trung bình chạy ba replica trong 30 ngày, mỗi Pod request `0,25 vCPU` và `0,5 GiB`:

~~~text
Số giờ trong kỳ = 30 × 24 = 720 giờ

Pod-giờ         = 3 × 720        = 2.160
vCPU-giờ request = 3 × 0,25 × 720 = 540
GiB-giờ request  = 3 × 0,5 × 720  = 1.080
~~~

Các đại lượng này giúp phân bổ hoặc so sánh tài nguyên. Chúng không tự bằng hóa đơn thực tế. Hệ thống có thể tính phí theo node, theo tài nguyên container hoặc theo cơ chế khác.

Không cộng đồng thời toàn bộ phí node và toàn bộ chi phí CPU/RAM quy đổi như hai khoản độc lập nếu chúng đại diện cho cùng tài nguyên. Cũng không coi resource limit là lượng tài nguyên luôn được sử dụng hoặc luôn bị tính phí.

Cần dự trù thêm phần dư để chịu lỗi, Pod surge khi rollout và vùng tài nguyên chưa dùng đủ vì yêu cầu placement. Phần dư là chi phí của mục tiêu sẵn sàng.

### 8.2. Chi phí mạng và quan sát

Những khoản dễ bị bỏ sót:

- Traffic danh mục lớn và request lặp lại.
- Traffic qua zone hoặc ra ngoài cụm nếu kiến trúc có các đường đó.
- Lưu trữ log, metrics, trace và thời gian giữ dữ liệu.
- Dữ liệu trùng khi retry hoặc khi nhiều client cùng làm mới.
- Giới hạn và công việc quản lý truy cập Kubernetes API.

Không log toàn bộ body danh mục cho mọi request chỉ để đo tải. Thông thường chỉ cần status, độ trễ, kích thước, số lượng đối tượng và thông tin chẩn đoán có chọn lọc; body lớn làm tăng chi phí quan sát và che khuất tín hiệu hữu ích.

### 8.3. Chi phí con người và thay đổi

| Công việc | Vì sao phát sinh |
| --- | --- |
| Nâng cấp image và căn chỉnh client/server | Tránh lệch schema hoặc hành vi tính năng |
| Quản lý namespace và RBAC | Phạm vi đọc dữ liệu thay đổi theo hệ thống |
| Quản lý TLS/danh tính nếu có | Đường HTTP cần vận hành như một phụ thuộc mạng |
| Điều chỉnh capacity | Số dịch vụ, endpoint, client và payload tăng |
| Trực và xử lý cảnh báo | Phải phân biệt lỗi server, nguồn dữ liệu và client |
| Thử phục hồi và rollout | Xác nhận dự phòng vẫn hiệu quả sau thay đổi |

Một mô hình hạch toán tổng quát:

~~~text
C_tổng =
    C_compute_đã_phân_bổ
  + C_mạng
  + C_quan_sát
  + C_vận_hành_con_người
  + C_phụ_thuộc_chưa_được_tính_ở_trên
~~~

Đơn giá phải lấy từ môi trường thực tế; bài không giả định giá nhà cung cấp. So sánh trên cùng phạm vi và cùng SLO để tránh phương án rẻ hơn chỉ vì đã bỏ bớt yêu cầu chịu lỗi.

## 9. Kế hoạch đo để kết luận thay vì suy đoán

Thực hiện trong môi trường thử nghiệm có cấu hình gần với triển khai mục tiêu. Phép đo cần giữ lại dạng tải, phiên bản, phạm vi namespace và kích thước dữ liệu.

| Kịch bản | Quan sát | Dấu hiệu đạt yêu cầu |
| --- | --- | --- |
| Tải nền và tải đỉnh | p95/p99, lỗi, CPU, bộ nhớ, GC, phân phối theo Pod | Đạt SLO và còn dự phòng phù hợp |
| Mất một Pod server | Lỗi client, thời gian phục hồi, tải Pod còn lại | Không vượt ngân sách lỗi đã đặt |
| Mất một node | Placement và capacity còn lại | Không mất toàn bộ backend discovery |
| Rolling update | Số Pod phục vụ, cold start, dữ liệu từng phiên bản | Dữ liệu hợp lệ trong khi chuyển đổi |
| Đường tới Kubernetes API bị gián đoạn | HTTP, tuổi dữ liệu, retry, log nguồn | Hành vi suy giảm đúng chính sách |
| Endpoint nghiệp vụ thay đổi | Thời điểm thay đổi tới từng lớp | Hội tụ trong giới hạn đã chọn |
| Client cùng làm mới/retry | Đỉnh tải và hàng đợi | Không tạo vòng quá tải kéo dài |
| Quy mô danh mục tăng | Heap, payload, GC, thời gian nạp dữ liệu | Không chỉ đạt khi tập dữ liệu nhỏ |

Đối với độ trễ cập nhật, ghi các mốc:

~~~text
t0: thay đổi được xác nhận trong dữ liệu Kubernetes cần quan sát
t1: từng replica server phản ánh thay đổi
t2: client nhận và sử dụng danh sách mới

Độ trễ server = t1 - t0
Độ trễ đầu cuối = t2 - t0
~~~

Các mốc phải có cách xác định nhất quán và đồng hồ đủ đồng bộ. Không lấy thời điểm gửi lệnh thay đổi thay cho thời điểm trạng thái nguồn đã thực sự đổi mà không ghi rõ sai số.

Khi so sánh replica, chuẩn hóa dữ liệu theo namespace, serviceId, host và port; không coi khác thứ tự mảng là khác tập đích. Chỉ cảnh báo mức lệch vượt giới hạn đã định, tránh báo động cho mỗi khoảng chuyển tiếp ngắn hợp lệ.

Có thể kiểm tra tài nguyên trên cụm thử nghiệm bằng các lệnh đọc:

~~~sh
kubectl -n platform get deployment kubernetes-discovery
kubectl -n platform get pods -l app=kubernetes-discovery -o wide
kubectl -n platform get endpointslices -l kubernetes.io/service-name=kubernetes-discovery
kubectl -n platform get pdb kubernetes-discovery
kubectl -n platform get hpa kubernetes-discovery
kubectl -n platform top pods -l app=kubernetes-discovery
~~~

`kubectl top` cần nguồn resource metrics phù hợp. Các lệnh trên không thay thế phép đo từ client; một HPA hoặc Deployment có trạng thái tốt vẫn có thể đi kèm dữ liệu discovery không đáp ứng yêu cầu.

## 10. So sánh Discovery Server với những lựa chọn đơn giản hơn

| Phương án | Điều đáp ứng tốt | Phần vận hành cần đánh giá |
| --- | --- | --- |
| DNS Kubernetes và Service | Gọi một API qua tên Service khi không cần danh mục instance trong ứng dụng | DNS, Service, mạng và sức khỏe backend |
| DiscoveryClient trực tiếp Kubernetes API | Ứng dụng cần endpoint/metadata và tự đọc nguồn discovery | Danh tính, RBAC, kết nối và tài nguyên ở từng ứng dụng |
| HTTP DiscoveryClient qua Discovery Server | Tập trung đường đọc API, cung cấp discovery qua HTTP | Server dự phòng, độ mới, HTTP, capacity và phiên bản hai phía |

Tập trung việc đọc API có thể giảm số ứng dụng phải trực tiếp quản lý Kubernetes access, nhưng không mặc nhiên giảm mọi loại chi phí. Một server có phạm vi quá rộng và nhiều client lấy toàn danh mục vẫn có thể tốn tài nguyên hơn phương án đơn giản đáp ứng đúng nhu cầu.

Nếu chỉ cần gọi `catalog-api.demo.svc.cluster.local`, hãy xác định lý do cụ thể trước khi thêm server discovery. Nếu cần lựa chọn instance theo metadata, tích hợp với Spring Cloud LoadBalancer hoặc cung cấp discovery qua HTTP cho nhiều ứng dụng, giá trị của lớp trung gian có thể rõ hơn.

Phân chia nhiều server theo nhóm namespace hoặc miền quản lý có thể giảm phạm vi ảnh hưởng và kích thước dữ liệu, nhưng tạo thêm deployment, cấu hình, giám sát và lựa chọn URL của client. Chỉ coi đó là tối ưu khi lợi ích đã được đo và chi phí vận hành bổ sung được chấp nhận.

## 11. Ghi quyết định triển khai bằng các bằng chứng cụ thể

Một bản đánh giá ngắn nhưng đủ dùng nên ghi:

| Mục | Nội dung cần chốt |
| --- | --- |
| Nhu cầu | Vì sao ứng dụng cần discovery qua HTTP |
| Phạm vi dữ liệu | Namespace, Service và metadata cần thiết |
| Mục tiêu | SLO request, độ trễ, độ mới và thời gian phục hồi |
| Miền lỗi | Cần chịu mất Pod, node hay zone nào |
| Năng lực | Tải nền/đỉnh, C_slo đã đo, replica nền và giới hạn mở rộng |
| Chính sách suy giảm | Khi nguồn hoặc server lỗi, client chờ, thất bại hay dùng dữ liệu cũ đến đâu |
| Chi phí | Compute, phần dư, mạng, quan sát và công vận hành |
| Điều kiện đánh giá lại | Khi quy mô, SLO, phiên bản hoặc phạm vi namespace thay đổi |

Trong phạm vi Spring Cloud Kubernetes, ConfigMap, Secret và Configuration Watcher có thể tham gia cung cấp hoặc cập nhật cấu hình, nhưng không thay thế dự phòng server, đo capacity và kiểm tra độ mới của danh mục. Nếu một thay đổi cấu hình khiến mọi replica cùng sai, tăng số Pod không giải quyết được nguyên nhân đó.

Một thiết kế được xem là có cơ sở khi chứng minh được ba điều cùng lúc: **client lấy được dữ liệu discovery đạt yêu cầu khi có sự cố dự kiến, hệ thống chịu được tải mục tiêu sau khi mất phần năng lực đã dự phòng, và tổng chi phí phù hợp với giá trị mà discovery qua HTTP mang lại**.
