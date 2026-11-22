# Tự động nhân bản theo tải và các tín hiệu phù hợp

## 1. Mục tiêu bài học

Một dịch vụ xử lý tốt ở mức 100 request/giây chưa chắc chịu được 1.000 request/giây. Khi số người dùng, số message hoặc công việc nền thay đổi, quy mô cố định có thể khiến hệ thống quá tải hoặc lãng phí tài nguyên.

**Autoscaling** là quá trình tự điều chỉnh năng lực xử lý dựa trên tín hiệu tải và giới hạn vận hành. Trong Kubernetes, autoscaling thường liên quan số lượng Pod, kích thước tài nguyên của Pod và số node trong cluster.

Mục tiêu của autoscaling không chỉ là làm CPU thấp hơn. Mục tiêu thực tế là giữ **độ trễ, độ tin cậy và tính đúng đắn nghiệp vụ** trong mức chấp nhận được với chi phí hợp lý.

Sau bài này, người đọc cần biết:

- Phân biệt horizontal, vertical, node và event-driven scaling.
- Chọn tín hiệu phù hợp cho API CPU-bound, I/O-bound, worker queue và streaming.
- Hiểu cách HPA tính số replica từ resource, custom và external metrics.
- Cấu hình min/max replicas, scale up/down behavior, stabilization và readiness.
- Hiểu KEDA và khả năng scale-to-zero khi dùng queue hoặc nguồn event.
- Nhận diện những giới hạn không thể giải quyết chỉ bằng thêm Pod: database, quota, partition, lock và hot keys.
- Đọc dashboard HPA, giải thích Pod Pending hoặc scale oscillation và kiểm chứng bằng load test.

## 2. Một ví dụ động lực

Giả sử API đặt hàng đang chạy 4 Pod, mỗi Pod phục vụ ổn định khoảng 120 request/giây trong điều kiện benchmark đại diện.

~~~text
Lưu lượng bình thường:   200 RPS
Số Pod hiện tại:         4
Tải bình quân/Pod:       50 RPS

Khi flash sale:
Lưu lượng tăng:          800 RPS
Số Pod không đổi:        4
Tải bình quân/Pod:      200 RPS
Năng lực thử nghiệm:    120 RPS/Pod
~~~

Nếu tăng lên 8 Pod và traffic được chia đều, mỗi Pod nhận khoảng 100 RPS. Tuy nhiên năng lực 120 RPS/Pod không phải hằng số: cache hit, payload, loại request, connection pool và độ trễ dependency có thể làm capacity thực thay đổi.

Bài toán autoscaling là **xác định khi nào cần thêm năng lực, cần thêm bao nhiêu, và liệu năng lực mới có thực sự giúp yêu cầu hoàn tất đúng hạn không**.

## 3. Các tầng autoscaling

### 3.1. Horizontal scaling

Tăng hoặc giảm số instance đồng loại:

~~~text
Trước:  API-1  API-2  API-3
Sau:    API-1  API-2  API-3  API-4  API-5  API-6
~~~

Đây là mô hình thường gặp với Deployment trong Kubernetes. HPA có thể điều chỉnh số replica của workload mục tiêu.

Phù hợp với công việc độc lập, có thể chia tải; đặc biệt là ứng dụng stateless. Nếu mọi Pod phụ thuộc một database đã quá tải, tăng Pod có thể làm database nặng hơn.

### 3.2. Vertical scaling

Tăng hoặc giảm resources của từng instance, ví dụ CPU/memory requests. Vertical Pod Autoscaler (VPA) có thể đề xuất hoặc cập nhật requests theo cấu hình. Việc đổi cấu hình có thể dẫn tới thay Pod, và không phải mọi cluster đều hỗ trợ cùng cơ chế resize tại chỗ.

Vertical scaling có lợi khi mỗi công việc cần nhiều RAM/CPU hoặc mô hình không dễ song song hóa. Nhưng một Pod lớn vẫn bị giới hạn bởi kích thước node và có thể khó schedule.

### 3.3. Cluster/node scaling

Khi HPA muốn 20 Pod nhưng cluster chỉ đủ chỗ cho 12 Pod, 8 Pod còn lại có thể Pending. Node autoscaler sẽ bổ sung node nếu quy tắc, quota, capacity và nhà cung cấp hạ tầng cho phép.

~~~text
HPA desired replicas tăng
           |
           v
ReplicaSet tạo Pod
           |
           v
Scheduler tìm tài nguyên node
      /             \
    Có chỗ         Không có chỗ
      |                |
    Pod chạy      Pod Pending
                       |
                Node autoscaler
                       |
                Node mới có chỗ
                       |
                   Pod chạy
~~~

HPA không tự đảm bảo node đã có sẵn. Node provisioning, image pull và application startup đều tạo độ trễ cho khả năng đáp ứng tải.

### 3.4. Event-driven scaling

Worker thường cần scale theo số công việc trong queue, consumer lag hoặc lịch xử lý. Công cụ như KEDA có thể cung cấp scaler cho những nguồn sự kiện và metrics ngoài Kubernetes, kể cả tình huống scale từ 0 ở workload phù hợp.

HPA, node autoscaler, VPA và KEDA có thể bổ trợ nhau, nhưng phải có một chính sách quản lý resource rõ để tránh các bộ điều khiển cấu hình xung đột.

## 4. Thế nào là một tín hiệu scale phù hợp?

Tín hiệu tốt cần thỏa mãn phần lớn các điều kiện:

1. **Phản ánh nhu cầu thực:** khi công việc đến nhanh hơn khả năng xử lý, metric phải thay đổi theo hướng nhận biết được.
2. **Có thể tác động bằng số replica:** thêm Pod cần làm mức tải/Pod hoặc hàng đợi giảm trong giới hạn hiện có.
3. **Đến đủ sớm:** thời gian thu thập + tính toán + startup không để request trễ quá lâu mới có capacity.
4. **Đơn vị dễ hiểu:** CPU%, requests/giây/Pod, concurrent requests, messages, tuổi message, lag.
5. **Đủ ổn định:** không dao động quá nhanh hoặc bị một mẫu cực đoan chi phối.
6. **Phân phạm vi đúng:** theo service, queue, consumer group, region, route hay loại công việc nếu cần.
7. **Có ngưỡng từ thực nghiệm:** target dựa trên load test, throughput, saturation và SLO.
8. **Có cơ chế dừng:** max replicas, resource quota, giới hạn chi phí và năng lực dependency.

Không dùng một metric chỉ vì nó có sẵn trên dashboard. Ví dụ p99 latency tăng khi provider bên ngoài lỗi có thể khiến scale thêm Pod nhưng không làm provider nhanh hơn.

## 5. Chọn tín hiệu theo loại workload

| Workload | Tín hiệu thường hữu ích | Rủi ro nếu chọn sai |
|---|---|---|
| API CPU-bound | CPU utilization, RPS/Pod, CPU throttling | Dùng memory không phản ánh nhu cầu tính toán |
| API I/O-bound | In-flight requests, concurrency, RPS/Pod, queue wait | CPU thấp dù đang chờ hàng nghìn request |
| WebSocket/SSE | Active connections/Pod, memory/concurrency | RPS thấp không nói connection ít |
| Worker queue | Queue depth, backlog age, arrival/processing rate | Chỉ nhìn CPU khi worker chờ external I/O |
| Kafka consumer | Consumer lag, lag per partition, throughput | Tăng Pod vượt khả năng partition |
| Batch theo deadline | Remaining jobs, worker throughput, time-to-deadline | Queue count không xét hạn hoàn thành |
| Memory-bound | Memory pressure, eviction, per-job footprint | Cache/JVM heap cao cả khi tải đã giảm |
| Stream processor | Lag, checkpoint/processing rate, partition ownership | Scale ảnh hưởng state/rebalance |
| Scheduled peak | Lịch dự báo kết hợp metric thực | Chờ tải tăng rồi mới bắt đầu khởi động Pod |
| Dịch vụ giới hạn quota | Budget/concurrency/quota, queue | Scale demand vô hạn khiến upstream bị 429 |

Có thể dùng nhiều chỉ số, nhưng mỗi chỉ số cần giải thích được: khi metric vượt target và thêm một replica, điều gì được kỳ vọng cải thiện?

## 6. CPU utilization và resource requests

CPU là một tín hiệu đơn giản, thường hiệu quả cho các service CPU-bound. Với HPA dùng resource CPU utilization, tỷ lệ được tính dựa trên **CPU request** của workload.

Ví dụ:

~~~text
CPU request của Pod: 500m
CPU usage thực đo:   350m
Utilization:         350/500 = 70%
~~~

Nếu request được đổi từ 500m thành 1000m trong khi usage vẫn 350m, utilization thành 35%. HPA sẽ nhìn hai tình huống khác nhau, dù lượng CPU thực dùng giống nhau.

Nên đặt CPU requests sau khi profiling và load test, không thay requests chỉ để làm HPA tạo nhiều hoặc ít Pod hơn.

CPU phù hợp khi:

- Mỗi request cần nhiều tính toán.
- Throughput tăng tương đối tỷ lệ với mức CPU sử dụng.
- Tải phân bố đều giữa các Pod.
- Không có dependency chung giới hạn trước CPU.

CPU dễ đánh lừa khi:

- Dịch vụ đang chờ database/API bên ngoài: CPU thấp nhưng latency cao.
- CPU limit gây throttling làm tail latency tăng.
- Pod có nhiều request nhưng đều nằm ở thread/connection pool chờ.
- CPU average che giấu Pod bị nóng do sticky session hoặc key skew.
- Các bản deploy có requests khác nhau.

Dùng CPU cùng latency, error rate, concurrency và dependency metrics để đánh giá hành vi toàn diện.

## 7. Memory utilization và đặc tính JVM/cache

Memory không phải tín hiệu tải tuyến tính trong mọi ứng dụng. JVM heap, runtime allocator hoặc cache có thể giữ memory cao sau khi workload giảm. Nếu chỉ scale theo memory, hệ thống dễ scale lên nhưng rất khó tự scale xuống.

Memory có ích khi số concurrent jobs, active sessions hoặc mỗi request giữ một phần bộ nhớ tương đối ổn định. Trước khi dùng memory HPA, cần biết:

- Working set/RSS và heap có ý nghĩa gì trong ứng dụng.
- Mức memory requests, limits và nguy cơ OOMKill.
- Cache có xu hướng nóng lên theo thời gian không.
- Tỷ lệ memory/connection hoặc memory/job có tương đối ổn định không.
- Thêm Pod có phân bổ bớt memory của Pod đang nóng không.

Memory leak cần được xử lý ở code; tăng Pod chỉ kéo dài thời gian tới khi lỗi xuất hiện.

## 8. Requests per second trên mỗi Pod

Nếu API có chi phí request ổn định, có thể chọn target RPS/Pod dựa trên ngưỡng giữ được SLO.

Công thức trực giác:

~~~text
desiredReplicas = ceil(totalIncomingRPS / safeTargetRPSPerPod)
~~~

Ví dụ:

~~~text
Incoming: 850 requests/second
Mỗi Pod phục vụ ổn định: 100 requests/second
Desired = ceil(850/100) = 9
~~~

Đây là phép tính gần đúng. Request đọc đơn giản có chi phí khác request tìm kiếm nặng hoặc xử lý ảnh. Với nhiều loại request, nên đo theo route/cohort hoặc dùng weighted work units đã được benchmark, ví dụ một request search nặng tương đương bốn request đọc đơn giản theo chi phí CPU đo được.

Không đưa raw user ID, order ID hoặc URL chứa ID riêng vào metric label; điều đó làm cardinality tăng và có nguy cơ lộ dữ liệu.

RPS/Pod phản ánh lưu lượng mới, nhưng không tự phản ánh queue delay hoặc một dependency chung đang bị nghẽn.

## 9. In-flight requests và concurrency

API I/O-bound thường bị giới hạn bởi số kết nối và tác vụ đồng thời hơn là CPU. Một request có thể giữ memory, socket, future hoặc thread khi chờ kết quả từ bên ngoài.

Nếu service đã kiểm thử mức concurrent requests/Pod an toàn, có thể dùng:

~~~text
desiredReplicas = ceil(activeConcurrentRequests / targetPerPod)
~~~

Ví dụ:

~~~text
Active concurrent requests = 640
Mục tiêu an toàn mỗi Pod = 80
Desired = ceil(640/80) = 8
~~~

Cần thận trọng: nếu 640 request đồng thời là hậu quả database outage, thêm 8 Pod có thể tăng số request đang đợi cùng database. Sử dụng timeout, circuit breaker, bounded concurrency, rate limiting và backpressure để bảo vệ dependency.

### Little's Law

Trong hệ thống ổn định:

~~~text
L = lambda × W

L = số công việc trung bình hiện diện
lambda = throughput trung bình/giây
W = thời gian trung bình một công việc nằm trong hệ thống
~~~

Ví dụ 200 RPS với latency trung bình 0,2 giây dẫn tới khoảng 40 request hiện diện. Nếu dependency chậm và latency lên 2 giây trong khi throughput vẫn 200 RPS, số request hiện diện có thể tăng tới 400. Đây là lý do concurrency hữu ích, đồng thời cho thấy thêm Pod chỉ có tác dụng nếu nguyên nhân chậm có thể mở rộng.

## 10. Queue depth và tốc độ xử lý worker

Với worker queue, tổng số message đang chờ phải được đặt trong tương quan với tốc độ message đến và tốc độ xử lý.

Công thức lập kế hoạch:

~~~text
requiredThroughput =
  incomingMessagesPerSecond + backlog / desiredDrainSeconds

desiredWorkers =
  ceil(requiredThroughput / safeMessagesPerSecondPerWorker)
~~~

Ví dụ:

~~~text
Backlog:                 600 message
Incoming rate:            30 message/giây
Mục tiêu giải phóng queue: 30 giây
Capacity mỗi worker:      10 message/giây

Required throughput = 30 + 600/30 = 50 message/giây
Desired workers = ceil(50/10) = 5
~~~

Giả định mỗi worker có throughput tương đối ổn định, công việc độc lập và downstream không bị giới hạn chung. Nếu một payment provider chỉ cho phép tối đa 30 request/giây, 5 worker vẫn không đạt mục tiêu.

Bên cạnh queue length nên đo arrival rate, processing rate, retries/redeliveries, DLQ, message size, throughput per worker và business completion latency.

## 11. Tuổi message cũ nhất và deadline

Một queue chỉ có 10 message vẫn có thể có vấn đề nếu message cũ nhất đã đợi 20 phút.

**Oldest-message age** hoặc queue age là chỉ số quan trọng của khả năng hoàn thành đúng hạn. Tuy nhiên một poison message liên tục retry có thể khiến age tăng mãi; tăng hàng trăm worker vẫn không sửa được message đó.

Đối với batch deadline, cần ước tính lượng việc còn lại và tốc độ:

~~~text
Remaining jobs:             2.400
Mean time/job/worker:       4 giây
Deadline còn:              600 giây

Một worker có thể xử lý lý tưởng 600/4 = 150 job
Số worker tối thiểu lý tưởng = ceil(2400/150) = 16
~~~

Kết quả bỏ qua retry, variance, provisioning latency và giới hạn dependency. Production cần thêm headroom từ thực nghiệm. Không dừng worker đang chạy job dài nếu chưa có checkpoint/resume hoặc shutdown an toàn.

## 12. Kafka consumer lag và giới hạn partition

Kafka consumer lag biểu diễn số message chưa xử lý/commit theo semantics của consumer group và partition. Consumer lag có thể dùng scale khi lag phản ánh công việc có thể chia đều.

Tuy nhiên, với một consumer group thông thường, mỗi partition được gán cho tối đa một consumer trong group tại một thời điểm để xử lý theo cơ chế assignment. Nếu topic có 8 partition, tăng từ 8 lên 20 consumer không làm song song hóa thêm những partition đã được phân công; nhiều consumer có thể rảnh.

Cần xét:

- Tổng số partition và lag từng partition.
- Tốc độ message đến và throughput theo consumer.
- Hot key/hot partition.
- Rebalance khi tăng/giảm số consumer.
- Idempotency khi broker redeliver.
- Commit và checkpoint semantics.
- Consumer startup time và state restoration.
- Downstream DB/provider rate limit.

Nếu một partition chứa phần lớn tải, giải pháp có thể là đổi partitioning/key distribution, batch hoặc kiến trúc xử lý, chứ không phải chỉ thêm Pod.

## 13. HPA Kubernetes: công thức và hành vi

HorizontalPodAutoscaler (HPA) là controller định kỳ đọc metric và tính desired replicas cho workload mục tiêu.

Phép tính cơ bản:

~~~text
desiredReplicas =
  ceil(currentReplicas × currentMetricValue / desiredMetricValue)
~~~

Ví dụ:

~~~text
currentReplicas = 6
CPU trung bình = 90% theo requests
Target CPU = 60%

desiredReplicas = ceil(6 × 90/60) = 9
~~~

Controller thực tế còn tolerance, metric missing, Pod chưa ready, min/max replicas, stabilization và scale rate policy. Vì thế số replica thay đổi ở một thời điểm có thể không đúng bằng công thức lý tưởng.

Các loại metric phổ biến trong HPA autoscaling/v2:

- **Resource:** CPU, memory.
- **ContainerResource:** metric resource của container cụ thể nếu môi trường hỗ trợ.
- **Pods:** giá trị metric trung bình trên Pod.
- **Object:** metric của một đối tượng.
- **External:** queue depth, workload demand hoặc metric ngoài Kubernetes qua adapter.

Khi có nhiều metric, HPA thường tính đề xuất cho mỗi metric và chọn đề xuất cao nhất hợp lệ, trong các giới hạn controller. Metric lỗi hoặc thiếu có thể ngăn scale down nếu một metric khác đang đề xuất thu hẹp; cần xem HPA status/events.

## 14. Ví dụ HPA autoscaling/v2 theo CPU

Một API Checkout dùng 3–20 replica, target CPU utilization 65%:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: checkout-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: checkout-api
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0
      selectPolicy: Max
      policies:
        - type: Pods
          value: 4
          periodSeconds: 60
        - type: Percent
          value: 100
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      selectPolicy: Min
      policies:
        - type: Percent
          value: 25
          periodSeconds: 60
~~~

Ý nghĩa: HPA không hạ dưới 3 hoặc tăng quá 20 replica theo cấu hình; cố giữ CPU khoảng mục tiêu trong điều kiện workload mở rộng được. scaleUp policy giới hạn tốc độ tăng theo các cách được liệt kê; selectPolicy Max cho phép chọn mức thay đổi lớn hơn. scaleDown giữ cửa sổ lịch sử để tránh giảm vội và giới hạn số Pod bị giảm.

Các con số là ví dụ; không áp dụng mặc định cho mọi hệ thống. Target và policies cần dựa trên thực nghiệm về startup, capacity, SLO, dependency và chi phí.

### Deployment cần requests hợp lý

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: checkout-api
  template:
    metadata:
      labels:
        app: checkout-api
    spec:
      containers:
        - name: checkout-api
          image: registry.example.com/checkout-api:2.4.1
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: 300m
              memory: 256Mi
            limits:
              memory: 512Mi
          readinessProbe:
            httpGet:
              path: /readyz
              port: 8080
            periodSeconds: 5
            failureThreshold: 3
~~~

Image tag trong ví dụ cần được thay bằng artifact thực; production thường nên pin digest bất biến. Bổ sung startup/liveness probes, bảo mật, graceful shutdown và resource policy theo nền tảng. CPU limit không nhất thiết cần đặt giống requests; xem CPU throttling và yêu cầu chia sẻ node.

Khi sử dụng HPA, tránh để CI/CD hoặc GitOps liên tục viết đè trường replicas cố định, gây tranh chấp với HPA.

## 15. Kiểm tra HPA và nguồn metrics

Các lệnh đọc trạng thái thường dùng:

~~~bash
kubectl get hpa
kubectl describe hpa checkout-api-hpa
kubectl get deployment checkout-api
kubectl get pods -l app=checkout-api -o wide
kubectl top pods -l app=checkout-api
~~~

Nếu metrics-server hoặc metrics adapter không hoạt động, HPA có thể báo unknown metric, không tính được desired hoặc giữ nguyên số Pod. Đọc HPA conditions, events, metric targets và logs của controller/adapter khi cần.

Một Prometheus dashboard có metric chưa đủ để HPA dùng được nó. Custom/external metrics cần luồng cung cấp qua API/adapter phù hợp. Đặt tên metric, đơn vị, scope và labels nhất quán, đồng thời xử lý missing/stale data.

## 16. Scale-up nhanh và vấn đề cold start

Quyết định tăng Pod không đồng nghĩa tăng capacity tức thời.

~~~text
Tải tăng
  -> hệ thống thu metric
  -> adapter cung cấp metric
  -> HPA tính desired replicas
  -> ReplicaSet tạo Pod
  -> scheduler tìm node
  -> node autoscaler cấp node nếu cần
  -> pull image, khởi động ứng dụng
  -> warm-up, readiness success
  -> load balancer gửi traffic
~~~

Ví dụ tải tăng gấp 10 lần trong 20 giây nhưng Java service cần 90 giây startup; autoscaling chỉ theo CPU có thể phản ứng quá chậm. Một số hướng cải thiện:

- Duy trì minReplicas và capacity headroom theo traffic baseline.
- Tối ưu image pull, startup, cache warm-up và readiness.
- Provision node trước peak dự báo được.
- Scheduled/preemptive scaling trước flash sale.
- Chọn tín hiệu sớm hơn, như arrival rate, backlog, concurrency.
- Bảo vệ service bằng queueing, rate limiting và load shedding trong lúc chờ Pod.
- Đo time-to-ready thực tế chứ không chỉ thời gian HPA ra quyết định.

Một policy tốt phải tính tới tổng thời gian từ phát hiện tải đến Pod sẵn sàng, không chỉ mức target.

## 17. Stabilization, cooldown và flapping

Nếu RPS dao động 200 -> 900 -> 250 -> 850, việc scale Pod theo từng nhịp ngắn có thể gây:

- Start/stop Pod liên tục.
- Cache miss và kết nối mới.
- Message consumer rebalance nhiều lần.
- Tăng image pulls và tải scheduler.
- DB connections dao động.
- Chi phí tăng mà latency không ổn định.

Có thể giảm dao động bằng:

- **Stabilization window:** xét lịch sử đề xuất replica, đặc biệt trước khi scale down.
- **Rate policy:** giới hạn số Pod/percentage thay đổi trong một khoảng.
- **Cooldown:** tránh scale down tức thời sau đỉnh tải theo cơ chế controller đang dùng.
- **Hysteresis:** tách ngưỡng tăng và giảm để tránh bật/tắt quanh một mốc.
- **Smoothing:** chọn cửa sổ aggregation phù hợp cho metric.
- **Minimum replicas:** có headroom khi startup chậm.
- **Readiness và graceful shutdown:** không nhận request sớm hoặc cắt job đang chạy.

Không đặt cooldown quá dài chỉ để loại bỏ dao động, vì nó có thể giữ nhiều Pod vô ích. Cần hiểu nhịp traffic, startup và thời gian quay về tải bình thường.

## 18. KEDA và event-driven autoscaling

KEDA hỗ trợ scale workload theo nguồn event hoặc external metrics như queue length, Kafka lag, Prometheus query và nhiều nguồn tích hợp. Một mô hình:

~~~text
Queue/Prometheus/Kafka
         |
         v
KEDA Scaler
         |
         v
External metric / HPA
         |
         v
Deployment replicas
         |
         v
Worker Pods
~~~

Một ví dụ cấu hình tham khảo cho worker nhận RabbitMQ messages:

~~~yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: email-worker-scaler
spec:
  scaleTargetRef:
    name: email-worker
  pollingInterval: 30
  cooldownPeriod: 300
  minReplicaCount: 0
  maxReplicaCount: 20
  triggers:
    - type: rabbitmq
      metadata:
        queueName: email-jobs
        mode: QueueLength
        value: "100"
      authenticationRef:
        name: rabbitmq-auth
~~~

Cấu hình là minh họa cho các trường quan trọng; để chạy thật phải có KEDA phiên bản tương thích, connection/authentication/TriggerAuthentication hợp lệ, permission và queue thật. Cú pháp từng scaler cần đối chiếu với phiên bản KEDA đang cài.

**Scale-to-zero** hữu ích nếu không có message trong thời gian dài, nhưng có cold start khi queue có công việc mới. Không phù hợp nếu completion deadline quá ngắn hoặc trigger không đáng tin cậy. Có thể giữ minReplicaCount lớn hơn 0 để giảm độ trễ.

Phân biệt pollingInterval, cooldownPeriod và behavior của HPA: một tham số cooldown không nhất thiết kiểm soát mọi lần scale giữa các mức replica dương.

## 19. Nhiều tín hiệu scale cùng lúc

Với một API có cả tính toán CPU và request đang chờ I/O, có thể cân nhắc CPU và in-flight requests.

~~~text
Metric CPU đề xuất:          7 replica
Metric concurrency đề xuất: 11 replica
Đề xuất cao hơn hợp lệ:     11 replica
~~~

Kết quả thực vẫn chịu min/max, scale policy và availability của metrics. Chọn nhiều metric chỉ khi từng cái có lý do rõ ràng; metric nhiễu có thể làm scale bất thường, còn lỗi metric có thể khiến scale down bị trì hoãn.

Các tín hiệu như p99 latency, DB timeout hoặc business completion nên thường là **guardrails/diagnostics** trước khi được đưa vào vòng phản hồi điều khiển. Nếu latency tăng do DB outage, scale API vô giới hạn là sai hướng.

## 20. Autoscaling không sửa được dependency bị nghẽn

Giả sử Checkout tăng từ 5 lên 30 Pod, nhưng payment provider có quota chung 300 RPS trong khi Checkout nhận 900 RPS. Dù Pod của Checkout khỏe, tối đa khoảng 300 lời gọi tới provider qua quota nếu mỗi request đều cần một lời gọi và không có cơ chế khác.

Tương tự, database có thể chỉ chịu được một số connections/queries đồng thời. Nếu 30 Pod mỗi Pod có pool 40 connections, tiềm năng lên tới 1.200 connections; scale thêm có thể làm DB chậm hơn.

Cần kiểm tra:

- DB connection acquisition wait, lock wait, CPU, IOPS và query plans.
- Provider quota, rate limit và HTTP 429.
- Broker partition, hot keys và consumer group.
- Network connections, DNS/NAT ports và egress.
- Concurrency/connection pool tại mỗi service.
- Retry storm hoặc các request đồng thời tăng do upstream fan-out.
- Shared cache saturation.

Giới hạn maxReplicas theo capacity của hệ thống và dùng rate limiting, circuit breaker, backpressure, queue, batching hoặc cache để bảo vệ dependency. Một service autoscale tốt không được phá SLO của dịch vụ phía sau.

## 21. Scale-down an toàn

Scale down thường khó hơn scale up với công việc đang xử lý.

Quy trình mong muốn:

~~~text
Controller giảm desired replicas
       |
       v
Pod được chọn terminate
       |
       v
Rút khỏi routing nhận request mới
       |
       v
Hoàn tất/hủy có kiểm soát in-flight work
       |
       v
Commit/ack/checkpoint đúng semantics
       |
       v
Đóng tài nguyên và thoát
~~~

Với HTTP/gRPC/WebSocket cần graceful drain, connection behavior và thời gian shutdown phù hợp. Với worker queue, chỉ ack message sau khi xử lý hoàn thành theo contract; nếu dừng giữa job, phải có retry/redelivery và idempotency. Với batch dài, cần checkpoint/resume.

Nếu service có local state, leader election, partition assignment hoặc lưu trữ gắn Pod, không được coi scale-down như xóa một process stateless. StatefulSet và broker có yêu cầu riêng về consistency/quorum.

## 22. Quan hệ giữa HPA, rolling update và canary

Một deployment đang rolling update có thể có hai version Pod cùng lúc. HPA có thể thay desired replicas đúng khi version mới đang khởi động, tạo những hiệu ứng:

- Version mới dùng CPU cao vì regression, HPA tăng replica và che giấu vấn đề.
- Pod cũ bị drain, Pod mới chưa ready, capacity tạm giảm.
- Cấu hình CPU requests của hai version khác, average utilization khó so.
- maxSurge, maxUnavailable và HPA scale cùng lúc tạo áp lực lên node.
- Canary nhận một phần traffic, nhưng metrics tổng gộp làm khó thấy bản mới chậm.

Nên gắn service.version, deployment revision hoặc rollout stage vào traces/logs và metric phù hợp. So throughput/Pod, p95 latency, business success giữa các version để kiểm tra thay đổi hiệu quả.

Không coi "CPU thấp sau deploy" là bằng chứng tối ưu tốt nếu số Pod tăng gấp đôi; kiểm tra tổng chi phí/tác vụ và SLO.

## 23. Capacity planning theo nhiều tầng

Ví dụ API có 8 Pod, mỗi Pod xử lý an toàn 100 RPS, tổng danh nghĩa 800 RPS. Khi lưu lượng đạt 650 RPS, còn 150 RPS headroom cho peak ngắn.

Nếu HPA tăng từ 8 lên 16 Pod nhưng cluster chỉ chứa tối đa 10 Pod:

~~~text
Desired Pod:   16
Schedulable:   10
Pending:        6
~~~

Phải xác minh node autoscaler có thể bổ sung node, quota và tài nguyên cloud có đủ không. Thời gian tăng node cùng startup Pod quyết định latency trong spike.

Capacity planning còn cần:

- Số replica tối thiểu để chịu node/AZ failure.
- PodDisruptionBudget và topology spread.
- CPU/memory requests/limits và scheduler fragmentation.
- Tài nguyên được reserve cho system components.
- Giới hạn max pods/node và IP address.
- Kết nối DB/provider theo tổng số Pod.
- Chi phí lưu lượng egress, load balancer và logging.
- Khả năng scale-down node khi không còn cần.

Không chọn min/max replicas chỉ từ một biểu đồ CPU; phải gắn với nhu cầu và giới hạn toàn hệ thống.

## 24. Dashboard cần đo những gì?

| Nhóm | Các chỉ số quan trọng |
|---|---|
| Autoscaler | Current/desired replicas, target/current metrics, conditions, events |
| Pod | Ready/Available/Pending/Unhealthy, restarts, OOMKills |
| Node | Allocatable/capacity, pending reasons, provisioning duration |
| Traffic | Incoming RPS, concurrency, queue depth, lag, arrival rate |
| Performance | p50/p95/p99 latency, throughput per Pod |
| Reliability | 5xx, timeout, retry, DLQ, data correctness |
| Dependencies | DB pool wait, provider 429, broker lag, network saturation |
| Cost | CPU/memory requested và used, node hours, overprovisioning |
| Scale lifecycle | Time-to-detect, time-to-scale, time-to-ready |
| Business | Completion rate, processing deadline, transaction consistency |

Ví dụ timeline:

~~~text
14:00  RPS tăng
14:01  HPA desired từ 4 lên 12
14:01  4 Pod Pending vì thiếu node
14:03  Node mới ready
14:04  Các Pod ứng dụng ready
14:05  p95 latency giảm
~~~

HPA có thể đã ra quyết định hợp lý nhưng capacity đến quá muộn. Cần cải thiện headroom/provisioning hoặc dự báo tải, không chỉ thay CPU target.

## 25. Troubleshooting autoscaling

### 25.1. CPU cao nhưng HPA không tăng Pod

Kiểm tra scaleTargetRef, metrics availability, CPU requests, maxReplicas, HPA conditions/events, scaleUp policy và khả năng có công cụ khác ghi đè replicas.

### 25.2. HPA muốn tăng nhưng Pod Pending

Kiểm tra namespace ResourceQuota, Pod resource requests, scheduler events, node capacity, affinity/taints, image pull, PVC, PodSecurity/admission và node autoscaler.

### 25.3. Pod tăng nhưng p95 không giảm

Kiểm tra dependency saturation, DB connection pool, lock, provider quota, traffic skew, retry, cache misses và throughput thực/Pod. Thêm Pod không giải quyết bottleneck dùng chung.

### 25.4. Replica dao động liên tục

Kiểm tra metric interval, noise, stabilization, cooldown, requests quá thấp, startup/readiness delay và nhịp burst. Điều chỉnh scale rate phù hợp, không chỉ tăng cooldown tùy tiện.

### 25.5. Queue lag không giảm

Xem partition count, hot partition, dead-letter/poison messages, throughput/worker, consumer rebalance, DB/provider quota và trạng thái ack/retry.

### 25.6. Autoscaler không giảm replica

Kiểm tra minReplicas, stabilization window, stale metric, memory cache, metric ngoài có giá trị không giảm, và workload thực sự còn công việc.

### 25.7. Scale-to-zero không thức dậy

Kiểm tra scaler connection/auth, external metrics, polling, queue event, KEDA/controller logs, node capacity, Pod readiness và quyền truy cập. Không coi dữ liệu metric thiếu là queue rỗng nếu chưa có chính sách xử lý failure.

## 26. Load test để kiểm chứng

Một kịch bản kiểm thử thực tế gồm:

1. **Baseline:** traffic thấp, replicas nằm ở mức bình thường.
2. **Ramp-up:** tăng RPS dần, đo độ trễ từ tải tới desired replicas.
3. **Burst:** tăng tải đột ngột, đo SLO trong thời gian chờ capacity.
4. **Sustained peak:** giữ tải cao, kiểm tra throughput và dependency.
5. **Ramp-down:** giảm tải, kiểm tra stabilization và graceful shutdown.
6. **Oscillation:** thay đổi tải liên tục, tìm hiện tượng flapping.
7. **Metric failure:** dừng cung cấp metrics để kiểm tra trạng thái HPA.
8. **Node shortage:** để Pod Pending có kiểm soát, quan sát node autoscaler.
9. **Dependency degraded:** mô phỏng DB chậm/provider 429, xem autoscaler có tăng tải sai hướng không.
10. **Rolling update under load:** deploy một version mới khi HPA đang scale.
11. **Long-running queue job:** scale down khi worker có job, kiểm tra ack/checkpoint.
12. **Consumer rebalance:** quan sát downtime và lag khi đổi số Pod.

Đo không chỉ replica count mà cả request latency, retry, time-to-ready, Pod Pending duration, cost và business correctness. Nếu 20 Pod mới xuất hiện nhưng người dùng vẫn timeout, autoscaling chưa đạt mục tiêu.

## 27. Bài tập tính toán

### Bài 1: HPA CPU

Có 5 replicas, CPU trung bình 84%, target 60%. Bỏ qua tolerance và policies:

~~~text
desired = ceil(5 × 84 / 60) = ceil(7) = 7
~~~

Nếu maxReplicas=6, số replica không thể vượt 6 theo cấu hình. Tăng max cần đi kèm kiểm tra node/dependency capacity.

### Bài 2: RPS/Pod

Incoming 1.250 RPS, benchmark cho thấy 140 RPS/Pod giữ được SLO:

~~~text
desired = ceil(1250/140) = ceil(8,93) = 9
~~~

Có thể cần thêm headroom cho burst, node failure, rolling update và traffic phân phối không đều.

### Bài 3: Queue

Backlog 1.800 jobs, mỗi giây thêm 20 jobs; mỗi worker xử lý 10 jobs/giây. Muốn xóa backlog trong 60 giây:

~~~text
Arrival = 20 jobs/s
Drain = 1800/60 = 30 jobs/s
Required throughput = 50 jobs/s
Required workers = ceil(50/10) = 5
~~~

Nếu dependency chung chỉ chịu 30 jobs/s, kết quả lý tưởng này không khả thi. Phải xử lý quota hoặc thay đổi deadline.

### Bài 4: Kafka lag

Topic có 6 partition, consumer group hiện có 6 Pod và hầu hết lag nằm trong 1 partition. Scale lên 18 Pod có làm throughput gấp ba?

Không. Partition và hot-key distribution đang giới hạn xử lý song song. Cần kiểm tra key, partitioning và per-partition throughput.

### Bài 5: Memory

Một Java service giữ 70% memory suốt 30 phút sau khi RPS giảm gần 0 vì cache không giải phóng. Dùng memory HPA đơn lẻ có hạ replica hợp lý không?

Có thể không. Cần đo nhu cầu việc thực, memory pressure/eviction và đặc tính cache để chọn hoặc bổ sung tín hiệu tốt hơn.

### Bài 6: Little's Law

Throughput 300 RPS, latency trung bình 0,4 giây:

~~~text
L = 300 × 0,4 = 120 request hiện diện trung bình
~~~

Nếu latency tăng lên 2 giây do dependency và throughput vẫn 300 RPS, L có thể gần 600. Đây là tín hiệu đang chờ nhiều hơn, không tự chứng minh thêm replica API sẽ làm dependency nhanh hơn.

## 28. Checklist production

- [ ] Phân loại workload: CPU, I/O, queue, streaming, stateful.
- [ ] Đo throughput/Pod và startup/readiness time trong điều kiện đại diện.
- [ ] Chọn tín hiệu có thể giảm bằng thêm replica và có đơn vị rõ.
- [ ] Định nghĩa target, min/max replicas, scale up/down rates và stabilization.
- [ ] CPU/memory requests/limits được đặt theo profiling và chính sách cluster.
- [ ] Đủ node capacity hoặc có node autoscaler với kế hoạch headroom.
- [ ] Readiness, startup probes, draining, graceful shutdown hoạt động.
- [ ] HPA/custom/external metrics thực sự được adapter cung cấp.
- [ ] Không có công cụ GitOps/CI liên tục ghi đè replicas.
- [ ] Có giới hạn DB connections, provider quota và dependency concurrency.
- [ ] Queue worker hỗ trợ idempotency, ack/redelivery và checkpoint khi cần.
- [ ] Consumer group/partitioning giới hạn parallelism đã được tính.
- [ ] Metrics/logs/traces theo dõi scale events và SLO.
- [ ] Có dashboard desired/current/ready/Pending replicas.
- [ ] Đã thử load ramp, burst, scale-down, metric failure, node shortage.
- [ ] Đã kiểm chứng behavior khi rolling update/canary và dependency degraded.
- [ ] Có runbook khi HPA không tăng, Pod Pending, flapping hoặc queue lag không giảm.
- [ ] Chi phí và correctness được đánh giá cùng latency/availability.

## 29. Những sai lầm thường gặp

1. Gắn CPU 70% cho mọi service mà không hiểu tính chất workload.
2. Không đặt CPU requests, làm target CPU utilization thiếu cơ sở.
3. Scale chỉ theo latency khi bottleneck ở database hoặc provider.
4. Chờ CPU cao mới scale dù Pod cần vài phút khởi động.
5. Tăng maxReplicas không giới hạn, làm cạn DB connections.
6. Quên khả năng scale node, khiến desired replicas tăng nhưng Pod Pending.
7. Scale queue chỉ bằng số message, bỏ qua processing time và arrival rate.
8. Tăng Kafka consumers vượt partition hữu hiệu.
9. Dùng memory usage cho ứng dụng cache mà không hiểu hành vi giữ memory.
10. Không có stabilization/cooldown, gây flapping.
11. Scale down làm mất in-flight jobs hoặc tạo side effects trùng.
12. HPA và pipeline cùng quản lý replicas gây xung đột.
13. Không theo dõi business correctness, dù response vẫn trả HTTP 200.
14. Bỏ qua biến cố metric unavailable hoặc adapter lỗi.
15. Không phân biệt version khi rollout, khiến regression bị che bởi scale up.

## 30. Ghi nhớ

**Horizontal autoscaling** tăng/giảm số Pod, **vertical autoscaling** điều chỉnh tài nguyên của Pod, còn **node autoscaling** bổ sung hoặc thu hẹp năng lực cluster. Với tác vụ sự kiện, có thể dùng KEDA hoặc custom/external metrics để chuyển queue/lag thành quyết định scale.

CPU thường phù hợp với công việc CPU-bound; RPS/Pod và concurrency giúp nhìn áp lực API; queue depth, processing rate, backlog age và lag phù hợp hơn cho worker. Nhưng thêm Pod chỉ hiệu quả khi công việc thực sự chia nhỏ được và không bị dependency chung giới hạn trước.

Autoscaling có độ trễ: thu thập metrics, ra quyết định, scheduling, node provisioning, image pull, startup và readiness. Vì vậy cần headroom, stabilization, graceful shutdown, giới hạn chi phí và các cơ chế bảo vệ quá tải.

Thước đo cuối cùng phải là **SLO và kết quả nghiệp vụ**. Một hệ thống từ 5 tăng lên 50 Pod mà p99 vẫn cao, job vẫn trễ hoặc giao dịch bị lặp thì chưa thể gọi là autoscaling hiệu quả.

**Nguyên tắc cốt lõi: chọn tín hiệu phản ánh nhu cầu có thể mở rộng, chọn target từ năng lực thực đo, giới hạn quy mô an toàn và xác minh rằng thêm tài nguyên thật sự cải thiện kết quả người dùng.**