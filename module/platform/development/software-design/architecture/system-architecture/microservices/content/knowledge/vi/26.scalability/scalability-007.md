# Tự động mở rộng có độ trễ và chuẩn bị trước cho tải tăng trong Microservices

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Khả năng mở rộng.
>
> **Câu hỏi trung tâm:** Autoscaling có thể bổ sung replica hoặc hạ tầng, nhưng không làm việc tức thời. Làm sao bảo đảm dịch vụ vẫn đáp ứng khi tải tăng nhanh hơn tốc độ phát hiện và cấp phát tài nguyên? Khi nào cần dự trữ công suất nóng, mở rộng theo lịch, dự đoán nhu cầu, làm ấm tài nguyên hoặc giới hạn tải?

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa **reactive autoscaling**, **scheduled/predictive scaling**, **provisioned headroom** và **overload protection**.
2. Phân tích từng thành phần của độ trễ scale-up: thời gian thu thập metric, cửa sổ tính toán, vòng điều khiển, scheduler, node provisioning, image pull, khởi động ứng dụng, warm-up và cập nhật endpoint.
3. Ước lượng số replica cần cho tải nền, đỉnh tải và tình huống mất node/AZ; xác định thời điểm phải bắt đầu scale trước đỉnh.
4. Chọn tín hiệu HPA/KEDA hoặc metric tùy chỉnh phù hợp: CPU, memory, requests in flight, RPS, queue age, backlog và processing latency.
5. Thiết kế chiến lược pre-scaling có giới hạn, tự hoàn nguyên, đo được hiệu quả và không làm dịch vụ phụ thuộc hoàn toàn vào dự báo.
6. Kết hợp autoscaling với rate limiting, backpressure, bounded queues, retries, circuit breakers và graceful degradation.
7. Kiểm tra khả năng mở rộng bằng load test có mô hình **ramp, spike, burst, steady peak và recovery**, không chỉ theo dõi replica count.
8. Nhận diện các trường hợp autoscaling thất bại dù controller vẫn hoạt động: Pod Pending, thiếu quota, DB quá tải, metric trễ, readiness sai, connection storm và giới hạn node pool.
9. Thiết lập dashboard/SLO, playbook và checklist triển khai cho dịch vụ có tải theo mùa, chiến dịch bán hàng hoặc tăng đột ngột.

Các ngưỡng và cấu hình sau đây là **ví dụ có điều kiện**. Năng lực mỗi Pod, chu kỳ metric, đặc tính HPA, quyền node provisioner, startup behavior và các phiên bản Kubernetes phải được xác nhận trong hệ thống thực tế.

## 2. Tình huống: traffic tăng nhanh, HPA phản ứng chậm

Giả sử Order Service phục vụ trung bình 500 requests/second (RPS), nhưng khi bắt đầu chương trình khuyến mãi lưu lượng tăng lên 3.000 RPS trong 30 giây.

~~~text
Traffic
3.000 RPS │              ╭──────────────────────────
          │             ╱
          │            ╱
  500 RPS ├───────────╯
          └─────────────────────────────────────► thời gian
                        T0: bắt đầu flash sale

Số Pod Ready
       30 │                               ╭──────
          │                          ╭────╯
       10 ├──────────────────────────╯
          └─────────────────────────────────────► thời gian
                        ↑ lag trước khi capacity tăng
~~~

Autoscaler nhìn thấy CPU tăng, nhưng cần thời gian để:

1. Metric pipeline ghi nhận CPU và truyền dữ liệu đến controller.
2. Autoscaler tính desired replicas và cập nhật Deployment.
3. Scheduler tìm node có đủ tài nguyên.
4. Node pool tạo VM nếu cluster thiếu chỗ.
5. Container runtime kéo image.
6. Ứng dụng Spring Boot/JVM khởi động.
7. App kết nối dependency, khởi tạo cache/connection pool, hoàn thành startup/readiness.
8. Endpoint/service mesh/load balancer nhận biết Pod mới đủ điều kiện.
9. Traffic thực tế được phân phối đến Pod mới.

Trong khoảng ấy, Pod cũ có thể bão hòa: p95/p99 tăng, request xếp hàng, timeout và retry làm tăng tải ngược lại. Nếu chỉ kiểm tra sau đỉnh và thấy HPA đã đạt 30 replicas, ta có thể bỏ qua thời gian hàng nghìn khách hàng đã bị lỗi.

**Kết luận:** autoscaler là **bộ điều khiển có phản hồi và độ trễ**, không phải nguồn công suất tức thời. Phải thiết kế để **chịu được giai đoạn chờ scale** hoặc **bổ sung công suất trước khi tải đến**.

## 3. Các lớp mở rộng và thời điểm capacity thật sự xuất hiện

### 3.1. Application replica scaling

Horizontal Pod Autoscaler (HPA) hoặc controller tương tự tăng số bản chạy của một service. Nếu node đã có CPU/memory/IP rảnh và image cached, Pod mới có thể Ready tương đối nhanh. Nếu app JVM mất thời gian khởi động và warm-up, độ trễ vẫn có thể đáng kể.

### 3.2. Node/cluster scaling

Cluster Autoscaler, node auto-provisioner hoặc hệ thống hạ tầng tương ứng bổ sung máy khi Pod không được schedule. Bước này có thể bao gồm tạo VM, boot OS, đăng ký node, cấu hình networking, daemonsets, storage/CSI và kéo image. Thường chậm hơn đơn thuần tạo Pod trên node có sẵn.

### 3.3. Database và dependency scaling

Thêm 20 Order Pods làm tăng số connection và downstream requests. Database, Redis, broker, Inventory hay Payment API không mặc định tăng công suất cùng lúc. Nếu DB là bottleneck thì thêm app Pod có thể làm DB quá tải nặng hơn.

### 3.4. Global/region/AZ capacity

Một số workload cần thêm node ở Availability Zone (AZ) còn khỏe, hoặc mở rộng region trước chiến dịch. Quota, loại VM, subnet IP và quota cloud có thể ngăn provisioning dù autoscaler đã yêu cầu đúng.

### 3.5. Mốc “đã scale” đúng nghĩa

Phân biệt:

- **Desired:** controller đã muốn thêm replica.
- **Scheduled:** Pod có node được chọn.
- **Running:** container/process đã chạy.
- **Ready:** Pod được phép nhận traffic theo readiness.
- **Serving:** Pod thực sự xử lý request.
- **Warm and productive:** Pod đã đủ cache/JIT/connections và xử lý ở throughput/latency mục tiêu.

Đối với SLO của khách hàng, chỉ số quan trọng nhất là **năng lực phục vụ hữu ích**, không phải desired replicas hay số container Running.

## 4. Phân rã độ trễ scale-up

Có thể mô tả đơn giản:

~~~text
T_total = T_signal + T_decision + T_schedule
        + T_provision + T_startup + T_warmup
        + T_route
~~~

Trong thực tế các pha có thể **chồng lấn**, nên tổng trên là mô hình ước lượng theo đường găng, không phải đẳng thức bắt buộc. Cách chính xác hơn là đo timestamp từ **tải bắt đầu tăng** tới lúc **capacity bổ sung có hiệu lực**.

| Thành phần | Dấu hiệu | Nguyên nhân thường gặp | Cách giảm |
| --- | --- | --- | --- |
| Thu thập tín hiệu | RPS/CPU tăng trước khi metrics phản ánh | Scrape interval, metric window, pipeline lag | Chọn metric và window phù hợp, đo age của sample |
| Quyết định scale | Metric đã cao nhưng desired chưa tăng | Sync loop, tolerance, stabilization/policy | Tuning HPA behavior có kiểm soát |
| Scheduling | Pod mới ở Pending | Thiếu node, affinity, spread, quota | Dự trữ node/IP, xem scheduler events |
| Node provisioning | Node chưa xuất hiện | Capacity cloud, quota, boot/registration | Warm nodes, min node pool, quota preparation |
| Image pull | Pod chờ pull | Image lớn, registry chậm, auth | Slim image, registry locality, pre-pull phù hợp |
| App startup | Container Running nhưng chưa Ready | JVM boot, migration, startup probes | Tối ưu boot, tách migration, kiểm tra startup |
| Warm-up | Ready nhưng latency xấu | Cache lạnh, JIT, DB pool, TLS | Controlled warm-up và readiness đúng |
| Route propagation | Pod Ready nhưng RPS bằng 0 | Service endpoints, ingress/mesh cache, LB | Đo endpoint propagation và policy routing |

**Không phỏng đoán tất cả các pha đều cộng tuần tự.** Thời gian node boot có thể bắt đầu khi nhiều Pod đã Pending; image có thể cache sẵn; traffic routing ở một số nền tảng gần như ngay sau readiness. Đo timing theo sự kiện là nguồn đúng cho chính hệ thống.

### 4.1. Ví dụ timeline

Một sự cố giả định:

~~~text
T+00s  Traffic tăng đột ngột.
T+20s  CPU/RPS metric phản ánh áp lực.
T+35s  HPA tăng desired từ 10 → 24.
T+40s  8 Pod schedule trên node có sẵn; 6 Pod Pending.
T+65s  8 Pod mới Running; một phần đã Ready.
T+90s  Node bổ sung join cluster.
T+115s  6 Pod còn lại được schedule và start.
T+135s  Toàn bộ Pod mới Ready.
T+155s  Cache/connection warm-up và routing ổn định.
~~~

**Scale-up lag vận hành khoảng 155 giây** trong ví dụ này. Nếu spike chỉ kéo 45 giây, việc scale có thể chỉ đến sau đỉnh; HPA vẫn giúp phục hồi sau đó nhưng không bảo vệ người dùng trong khoảng tăng đột biến.

## 5. Reactive autoscaling và proactive scaling

| Cách tiếp cận | Dựa vào | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **Reactive** | CPU, queue, RPS, custom metric hiện tại | Tự điều chỉnh với tải không biết trước | Có độ trễ; có thể phản ứng sau khi lỗi xảy ra |
| **Scheduled** | Lịch chiến dịch, batch, giờ cao điểm | Tạo capacity trước sự kiện đã biết | Sai lịch/không có chiến dịch vẫn tốn chi phí |
| **Predictive** | Dự báo từ thời gian, tính mùa vụ, xu hướng | Chủ động trước tải lặp lại | Sai dự báo, concept drift, dữ liệu thiếu |
| **Static headroom** | Dự trữ Pod/node chạy sẵn | Hấp thụ burst tức thì trong phạm vi dự trữ | Trả phí khi chưa sử dụng |
| **Warm pool / warm nodes** | Hạ tầng được chuẩn bị sẵn hoặc gần sẵn | Giảm provisioning lag | Không phải zero lag; có chi phí vận hành |
| **Traffic shaping** | Giới hạn admitted load | Bảo vệ core service khi thiếu capacity | Có request bị trì hoãn hoặc từ chối |

Kiến trúc thực tế thường kết hợp: **headroom nền + autoscaling động + scheduled pre-scale cho đỉnh dự kiến + overload protection cho tình huống vượt dự báo**.

### 5.1. Scheduled không có nghĩa bỏ reactive HPA

Nếu dự kiến sale lúc 20:00, có thể nâng minReplicas lúc 19:55 hoặc sớm hơn theo lead time đo được. Khi sale có traffic lớn hơn dự báo, HPA vẫn tăng tiếp trong maxReplicas; nếu sale nhỏ hơn, còn có cơ chế hạ minReplicas sau sự kiện.

Scheduled pre-scaling tốt là **giới hạn nền tối thiểu trong khoảng thời gian xác định**, không khóa số replica tuyệt đối làm vô hiệu điều chỉnh theo tải.

### 5.2. Predictive scaling cần fallback

Một mô hình forecast có thể nhận diện tải tăng mỗi tối hoặc mỗi thứ hai. Nhưng sự kiện flash sale bất ngờ, quảng cáo viral, outage vùng khác hoặc retry storm có thể khác dữ liệu lịch sử. Phải giữ reactive control, load shedding và an toàn quota.

## 6. Nhu cầu đến và khả năng phục vụ

### 6.1. Offered, admitted và completed traffic

Dùng các khái niệm:

- **Offered load (λ):** tốc độ yêu cầu từ client hoặc producer đến hệ thống.
- **Admitted load:** phần hệ thống quyết định tiếp nhận.
- **Completed throughput (μ):** tốc độ xử lý xong với kết quả xác định.
- **Rejected/throttled:** phần không được tiếp nhận vì policy hoặc quá tải.
- **Backlog:** số yêu cầu/job đang chờ trong hàng đợi có giới hạn.

Nếu λ tăng nhưng μ không tăng kịp, backlog và thời gian chờ có xu hướng tăng cho tới khi capacity bổ sung hoặc hệ thống áp dụng giới hạn tải.

### 6.2. Ví dụ queue tăng trong lúc chờ scale

Giả sử producer gửi 1.000 messages/giây, trong khi worker chỉ hoàn thành 700 messages/giây. Nếu không drop và tốc độ giữ nguyên trong 120 giây:

~~~text
Backlog growth = (1.000 − 700) × 120 = 36.000 messages.
~~~

Nếu mỗi message phải hoàn thành trong 30 giây, chờ autoscaling 120 giây có thể không phù hợp dù backlog được xử lý hết sau đó. Cần **deadline SLO**, tăng baseline worker, giới hạn đầu vào hoặc xử lý ưu tiên.

Queue length không tự nói vấn đề nghiêm trọng đến mức nào; cần cả **oldest message age, throughput, retry/DLQ và giới hạn hoàn tất nghiệp vụ**.

### 6.3. Little's Law và concurrency

Trong hệ thống tương đối ổn định:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số công việc trong hệ thống trung bình.
- \(\lambda\): throughput trung bình.
- \(W\): thời gian trung bình mỗi công việc ở trong hệ thống.

Nếu service hoàn thành 500 RPS, mean latency 0,2 giây:

\[
L = 500 \times 0.2 = 100.
\]

Nếu latency tăng lên 0,8 giây nhưng throughput vẫn 500 RPS, concurrency kỳ vọng tăng lên khoảng 400. Khi thread/connection pool chỉ đủ 150, pending work và timeout có thể tăng nhanh.

Công thức chỉ phản ánh **trung bình trong điều kiện ổn định**. Burst ngắn, retry, drop, queue vô hạn và response time tail cần quan sát thêm.

## 7. Lập kế hoạch capacity dựa trên SLO, không dựa vào CPU tối đa

Ví dụ Order Service đã load test:

- Một Pod có thể hoàn thành **200 RPS** trước khi p95 latency bắt đầu vượt mục tiêu.
- Đội vận hành chọn mức sử dụng mục tiêu **70%** để có headroom.
- Do đó công suất lập kế hoạch của một Pod là \(200 \times 0,70 = 140\) RPS.
- Tải nền dự kiến 800 RPS, đỉnh dự kiến 2.000 RPS.

### 7.1. Số Pod ở tải nền

\[
N_{\mathrm{base}}=\left\lceil \frac{800}{140} \right\rceil=6.
\]

### 7.2. Số Pod cho đỉnh dự kiến

\[
N_{\mathrm{peak}}=\left\lceil\frac{2.000}{140}\right\rceil=15.
\]

Như vậy nếu giữ đúng tải nền 6 Pod mà scale chỉ bắt đầu tại đỉnh, phải chờ bổ sung ít nhất 9 Pod trong thời gian service có thể bị bão hòa.

### 7.3. Headroom cần thiết để chịu burst

Giả sử phải hấp thụ ngay một burst 1.500 RPS mà chưa có Pod mới Ready:

\[
N_{\mathrm{warm}}=\left\lceil\frac{1.500}{140}\right\rceil=11.
\]

Giữ 11 Pod nóng giúp có khả năng đáp ứng burst ví dụ; HPA tăng lên 15+ khi tải tiếp tục cao. Nhưng cần xác nhận dependency đủ công suất, traffic không dồn bất thường, node capacity và điều kiện lỗi AZ.

### 7.4. Kịch bản mất một AZ

Nếu muốn phục vụ 2.000 RPS **ngay khi mất AZ lớn nhất** và mỗi Pod an toàn 140 RPS, cần ít nhất 15 Pod còn lại. Với ba AZ phân bố đều 8 Pod mỗi AZ:

~~~text
Total pods = 24
Largest AZ = 8 pods
After one AZ fails = 16 pods
Safe capacity = 16 × 140 = 2.240 RPS
~~~

Đây chỉ là capacity của tầng Order theo giả định. DB, broker, ingress, Inventory và Payment cũng phải đáp ứng 2.000 RPS trong mô hình AZ failure. Không đồng nhất công suất Pod với công suất toàn chuỗi checkout.

### 7.5. Đừng tính capacity từ CPU 100%

Một Pod có thể chạm p95 latency SLO ở CPU 55% vì DB lock, remote call hay GC. Lấy throughput đo ở điều kiện **đạt SLO end-to-end và mức bền vững lâu dài**, không chỉ throughput tối đa khi latency/timeout đã xấu.

## 8. Chọn thời điểm pre-scale dựa trên lead time

Giả sử flash sale bắt đầu lúc 20:00. Quan sát thực tế:

| Pha | Thời gian ví dụ |
| --- | ---: |
| HPA nhận biết và ra quyết định | 25 giây |
| Schedule khi node còn chỗ | 10 giây |
| Tạo node mới khi thiếu chỗ | 90 giây |
| Khởi động app/container | 35 giây |
| Warm-up cache/JIT/connection | 40 giây |
| Propagation/route ổn định | 10 giây |

Một số bước chồng lấn, nhưng giả sử đo từ “scale requested” đến “Pod mới phục vụ ổn định” có thể đạt **120–180 giây** trong hoàn cảnh cần node mới. Pre-scaling nên bắt đầu **sớm hơn độ trễ đo được**, cộng thêm biên an toàn cho variance:

~~~text
T_pre_scale_start
    ≤ T_expected_peak_start − (T_lead_p95 + T_safety_margin)
~~~

Ví dụ \(T_{\mathrm{lead,p95}}=150s\), biên an toàn 90s: khởi động pre-scale muộn nhất **19:56** nếu peak đến 20:00.

**Không tự lấy mốc 19:56 cho mọi sự kiện.** Cần đo p95/p99 lead time từ telemetry của môi trường thật, và nhận diện dependency/quota từng AZ.

### 8.1. Thời gian làm ấm là một phần của kế hoạch

Một Pod Ready sau 20 giây nhưng cần 90 giây để cache và JVM đạt hiệu suất ổn định. Nếu pre-scale quá sát giờ, số replica có vẻ đúng nhưng p95 vẫn xấu. Warm-up có thể gồm:

- Nạp cache an toàn với tần suất có giới hạn.
- Khởi tạo connection pool/HTTP client.
- Chạy các request nội bộ có kiểm soát cho đường nóng.
- Hoàn thành initialization/migrations hoặc configuration load.
- Bảo đảm app có thể trả request nghiệp vụ theo SLO trước khi nhận full traffic.

Tránh “warm-up đồng loạt” làm DB/cache bị stampede. Readiness chỉ bật khi khả năng phục vụ cơ bản đạt, nhưng không yêu cầu tất cả cache phải đầy nếu như vậy làm rollout mắc kẹt.

## 9. Reactive scaling: chọn tín hiệu nào?

### 9.1. CPU utilization

Ưu điểm: đo được ở nhiều runtime và có hỗ trợ HPA. Phù hợp khi throughput và CPU có tương quan khá tốt.

Nhược điểm:

- Service chờ network hoặc DB có CPU thấp nhưng đã bão hòa.
- CPU utilization trong HPA phụ thuộc resource requests.
- CPU throttling và GC có thể khiến behavior khó diễn giải.
- CPU tăng sau khi traffic đã dồn vào Pod.

CPU là tín hiệu hữu ích, **không phải proxy chung cho sức khỏe người dùng**.

### 9.2. Memory usage

Memory là tín hiệu không phải lúc nào cũng có quan hệ tuyến tính với khả năng xử lý. JVM có thể giữ heap/caches dù traffic giảm; scale theo memory có thể rất chậm scale down hoặc không phản ánh tải tức thì.

Bảo vệ OOM bằng requests/limits, heap tuning và monitoring, không chỉ bằng tăng replicas.

### 9.3. RPS

RPS có thể dự báo tải trực tiếp hơn CPU đối với HTTP service. Nhưng cần đo:

- Offered RPS tại edge nếu muốn biết nhu cầu chưa được phục vụ.
- Admitted/served RPS nếu muốn biết lượng được phân tới backend.
- Per-operation cost vì cùng 1 RPS của checkout và health check không tương đương.
- Retries vì outbound attempts có thể tăng nhanh hơn yêu cầu người dùng.

Không scale chỉ từ RPS đến service sau khi rate limiter đã chặn phần lớn nhu cầu: dashboard nội bộ có thể “bình thường” trong lúc khách hàng bị 429.

### 9.4. In-flight requests / concurrency

Số request đang xử lý hoặc outstanding requests phản ánh áp lực trực tiếp khi latency tăng. Hữu ích cho những service hạn chế bởi concurrency/thread pool, nhưng phải kết hợp timeout, queue và workload cost.

Nếu traffic giảm do service đang từ chối nhiều request, in-flight có thể thấp dù trải nghiệm xấu; cần alert từ user-facing SLI.

### 9.5. Queue length và lag

Thích hợp cho worker. Nhưng queue length cần kết hợp:

- Publish/consume rate.
- Processing time.
- Oldest message age.
- Number of active workers.
- Deadlines và DLQ.
- Consumer partition/ordering/quorum.

Đặt mục tiêu concurrency quá cao có thể khiến database hoặc provider bị đánh sập. Queue depth tăng có thể do **downstream bị lỗi**, không do thiếu worker.

### 9.6. Latency và error rate

Latency/error là các **tín hiệu SLO và overload**, không mặc định là metric tốt nhất để scale trực tiếp. Nếu lỗi do config sai, tăng Pod không chữa được. Nếu latency do DB chung chậm, tăng Order Pods có thể làm DB càng chậm.

Dùng chúng làm điều kiện bảo vệ, alert và xác nhận hiệu quả scale; cần phân tích nguyên nhân trước khi cho controller tự tăng công suất theo lỗi.

## 10. Kubernetes HPA: nguyên lý cần hiểu

HPA là controller định kỳ đọc metrics theo loại hỗ trợ, tính desired replicas cho scale target và điều chỉnh theo policies. Với metric utilization, ý tưởng gần đúng là:

\[
desiredReplicas = \left\lceil currentReplicas \times
\frac{currentMetricValue}{desiredMetricValue}\right\rceil.
\]

Công thức minh họa lý luận điều khiển. Implementation thực có tolerance, xử lý metric thiếu, startup behavior, giới hạn min/max và scale policies nên không nhất thiết cho kết quả đúng bằng phép tính tay.

### 10.1. Cấu hình HPA ví dụ

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: order-service-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: order-service
  minReplicas: 6
  maxReplicas: 40
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
      selectPolicy: Max
      policies:
        - type: Pods
          value: 8
          periodSeconds: 60
        - type: Percent
          value: 100
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 20
          periodSeconds: 60
~~~

Cách đọc:

- `minReplicas: 6` giữ số replica nền trong điều kiện controller và cluster hoạt động.
- `maxReplicas: 40` là giới hạn desired, không là cam kết đủ node để chạy 40 Pod.
- Target CPU 60% cần resource requests hợp lý.
- Scale-up policy cho phép controller tăng nhanh theo các giới hạn đã khai báo; **không làm Pod mới Ready tức thì**.
- Scale-down stabilization và rate policy giảm nguy cơ dao động khi tải sụt tạm thời.
- Các số 6, 40, 60%, 300 giây là điểm khởi đầu minh họa; chỉ áp dụng khi phù hợp burst, latency/cost và dependency.

**Chú ý cấu hình đồng thời:** nếu hệ thống có scheduled controller thay đổi số replicas, HPA sẽ tiếp tục reconcile theo `minReplicas`/metrics. Nên có **một nguồn điều khiển rõ ràng** đối với desired/min replicas; tránh script cứ patch replicas nhưng HPA liên tục đưa về số khác.

### 10.2. Scaling policies không thay thế node capacity

Ngay cả khi HPA desired tăng từ 6 lên 20 trong vài giây, scheduler vẫn có thể để 14 Pod Pending nếu thiếu CPU, memory, taints/tolerations, AZ hợp lệ hoặc IP addresses.

### 10.3. Tăng nhanh, giảm chậm

Một chiến lược thông dụng là scale-up quyết đoán hơn để bảo vệ SLO và scale-down thận trọng để tránh flapping khi traffic dao động.

Tuy nhiên giảm quá chậm có thể tốn chi phí; tăng quá nhanh có thể vượt quota DB. Cần đo kết quả thực chứ không chỉ cấu hình policies đẹp.

## 11. Kubernetes Deployment hỗ trợ scale-up có chất lượng

Ví dụ triển khai một Java service trên nhiều AZ:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 6
  selector:
    matchLabels:
      app: order-service
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 2
      maxUnavailable: 1
  template:
    metadata:
      labels:
        app: order-service
    spec:
      terminationGracePeriodSeconds: 40
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: order-service
      containers:
        - name: order
          image: registry.example.org/order-service:2.0.0
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "300m"
              memory: "512Mi"
            limits:
              memory: "1Gi"
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 3
~~~

Ở mức ý tưởng:

- **Request resources:** scheduler dựa trên resource requests để đặt Pod, HPA CPU thường dùng utilization so với requests.
- **Topology spread:** ưu tiên không dồn hết Pod vào một AZ, đồng thời ví dụ dùng `ScheduleAnyway` để không chặn scheduling khi một zone thiếu capacity.
- **Startup probe:** cho app thời gian khởi động hợp lệ trước khi bị liveness xử lý quá sớm.
- **Readiness:** chỉ đưa Pod vào lưu lượng sau khi chuẩn bị đủ theo policy.
- **Rolling update:** có thể tạo tạm Pod vượt replica cũ; cần dự trữ tài nguyên cho maxSurge.
- **Termination grace:** cho in-flight work cơ hội hoàn tất.

Các endpoint Actuator phải được bật trong app và đúng port. Không để liveness kiểm tra toàn bộ remote dependencies, vì một database outage có thể làm tất cả Pod restart đồng loạt.

### 11.1. Readiness quá dễ dãi

Nếu readiness trả 200 ngay khi HTTP server khởi động nhưng cache/JIT chưa ấm, traffic bị đưa vào Pod cold khiến p95 tăng. Cần hiểu **Ready** và **warm capacity**. Có thể dùng progressive routing hoặc warm-up traffic trước khi Pod nhận full load.

### 11.2. Readiness quá chặt

Nếu readiness chờ mọi dependency không thiết yếu đều hoàn hảo, một outage ở notification service khiến Order Pods NotReady dù checkout vẫn có thể chạy với degraded mode. Lúc scale, tất cả Pod mới mắc kẹt; cần định nghĩa dependency bắt buộc theo hợp đồng nghiệp vụ.

### 11.3. Phân bố Pod và node cùng quan trọng

HPA tăng 12 Pod nhưng scheduler xếp cả Pod mới vào một node/AZ do constraints hoặc capacity. Mất node/AZ gây mất nhiều công suất hơn dự tính. Quan sát Ready replicas theo node/zone, không chỉ tổng số.

## 12. Scheduled pre-scaling cho sự kiện biết trước

Giả sử flash sale bắt đầu lúc **20:00** và dự kiến kết thúc 22:00; lịch có sẵn từ sản phẩm/marketing.

Một kế hoạch:

~~~text
19:40  Kiểm tra health, quota, DB capacity và metric ingestion.
19:50  Bắt đầu nâng warm replicas/nodes.
19:55  Đủ Ready + warm capacity, chạy synthetic checks.
20:00  Flash sale bắt đầu; HPA vẫn mở rộng khi cần.
20:00–22:00  Quan sát SLO, traffic, queue age, saturation.
22:15  Khi traffic ổn định, hạ minReplicas từng bước.
22:30+ Theo dõi scale-down và connection draining.
~~~

Thời điểm chính xác cần dựa trên **lead time p95/p99** đã đo, không chọn 10 phút theo trực giác. Nếu node provisioning có thể mất 15 phút lúc cloud thiếu VM, phải chuẩn bị sớm hơn.

### 12.1. Thay đổi minReplicas có quản lý

Có nhiều cách:

- Cấu hình theo GitOps/manifest với một schedule controller có ownership rõ.
- Sử dụng tính năng scheduled scaling của nền tảng orchestration.
- Dùng công cụ như KEDA Cron scaler nếu đã được cài và cấu hình phù hợp.
- Dùng workflow nội bộ tăng min desired capacity theo lịch có kiểm toán và rollback.

**Tránh:** để một CronJob patch Deployment replicas trong khi HPA đồng thời điều khiển replicas mà không quản lý conflict. HPA có thể ghi đè hoặc gây dao động.

### 12.2. KEDA Cron trigger như một ý tưởng

Một số stack hỗ trợ Cron scaler để đặt **minimum desired replicas theo khung thời gian**, kết hợp các trigger còn lại. Cần xác định timezone, thời điểm bắt đầu/kết thúc, daylight-saving behavior nếu có, và semantics khi ngoài cửa sổ. Chi tiết CRD và version phải kiểm tra theo KEDA đang chạy.

Ví dụ yêu cầu ở mức chính sách:

~~~text
Service: order-worker
Normal minimum: 3 replicas
From 19:50 to 22:20 local schedule time:
    Maintain at least 20 replicas
Beyond scheduled minimum:
    Allow reactive scaling up to 50 replicas
After window:
    Return to normal minimum if metrics/SLO permit
~~~

Khung thời gian trên chỉ là kế hoạch minh họa, không thay thế backup khi forecast sai.

### 12.3. Quên scale-down sau sự kiện

Scheduled scaling không có expiration/owner dễ làm số Pod/VM cao mãi sau sale, gây chi phí kéo dài. Cần có rollback, TTL/schedule kết thúc, approval, giám sát và xác nhận scale-down không làm job dở mất state.

## 13. Predictive scaling: dùng dự báo nhưng không tin tuyệt đối

Dự báo có thể dựa vào:

- Traffic lịch sử theo giờ/ngày/tuần.
- Lịch chiến dịch, ngày lễ, thời điểm ra mắt sản phẩm.
- Số lượng người đăng ký/thanh toán dự kiến.
- Message arrival rate hoặc producer schedule.
- Độ trễ tín hiệu leading indicators, ví dụ số lượt thêm vào giỏ tăng trước checkout.
- Các chỉ báo kinh doanh đã được phê duyệt và kiểm soát dữ liệu.

Có thể tính desired warm capacity:

\[
N_{\mathrm{forecast}} =
\left\lceil \frac{\widehat{RPS}_{\mathrm{peak}} \times \mathrm{safetyFactor}}
{C_{\mathrm{safe,pod}}} \right\rceil.
\]

Nếu dự báo peak là 1.800 RPS, safety factor 1,2 và Pod an toàn 140 RPS:

\[
N_{\mathrm{forecast}} = \left\lceil 2.160/140 \right\rceil = 16.
\]

Nhưng cần chọn safety factor theo sai số forecast và chi phí, không mặc định 1,2.

### 13.1. Leading indicator

Một sự kiện “nhiều người đang xem sản phẩm” có thể báo trước lượt checkout vài phút. Nếu correlation ổn định, nó giúp scale Order trước checkout. Nhưng correlation có thể thay đổi do UI, chiến dịch hoặc bot; cần xác minh với số liệu thực.

### 13.2. Model drift và sự cố bất thường

Mẫu tải có thể đổi khi:

- Sản phẩm mở rộng sang thị trường mới.
- Thêm endpoint nặng hoặc thay đổi business process.
- Mất một region khiến traffic chuyển vùng.
- API client thay retry policy.
- Lượng bot/abuse tăng.
- Cập nhật cách đo metric.
- Thay phiên bản làm CPU/throughput mỗi Pod đổi.

Cần theo dõi sai số dự báo, giới hạn max, và cơ chế reactive/load shedding khi forecast thấp hoặc cao hơn thực tế.

### 13.3. Sai số hai chiều

- **Under-forecast:** thiếu capacity, queue/p99/error tăng.
- **Over-forecast:** tăng chi phí, có thể chiếm node/DB connections và gây tác động tới service khác.
- **Sai thời điểm:** đã scale đủ nhưng sau khi đỉnh đến, làm mục tiêu pre-scale thất bại.

Đánh giá forecast bằng **capacity available before demand**, không chỉ bằng MAE/MAPE chung của RPS.

## 14. Warm capacity và warm pools

### 14.1. Warm Pods

Giữ sẵn số Pod Ready lớn hơn nhu cầu bình thường. Đây là lựa chọn đơn giản nhất để hấp thụ burst ngắn, đặc biệt khi startup chậm.

Trade-off: tốn CPU/memory và có thể tăng DB connections dù traffic chưa đến. Cần lựa chọn mức giữ nóng theo SLO và cost.

### 14.2. Warm nodes

Giữ node có tài nguyên dự phòng để Pod được schedule ngay, không chờ VM boot. Có thể thực hiện bằng node pool min size, overprovisioning Pods có mức priority phù hợp hoặc cơ chế warm pool do hạ tầng hỗ trợ.

**Lưu ý:** một Pod chỉ Pending vì thiếu CPU có thể được schedule khi low-priority placeholder bị preempt; nhưng mọi logic priority/preemption phải kiểm soát việc gây ảnh hưởng workload khác. Đây là kỹ thuật cần vận hành cẩn thận.

### 14.3. Image caching

Đóng image gọn, giữ layer ổn định và đưa image tới registry gần cluster giúp giảm pull lag. Pre-pull image phải được cân nhắc về disk, security, image tag/digest và version; không chạy phiên bản cũ chỉ vì image đó đã cache.

### 14.4. Application warm-up

Các công việc warm-up:

- JIT/class loading, framework initialization.
- Connection pool tới DB/HTTP endpoint.
- Cấu hình, routing tables và schema/serialization caches.
- Kết nối broker và consumer subscription.
- Cache dữ liệu nóng có giới hạn.
- TLS/DNS initialization.

Warm-up nên có **giới hạn concurrency** để tránh 100 Pod mới đồng loạt mở 30 kết nối DB, tạo 3.000 connections trước khi nhận request.

### 14.5. Lazy initialization không luôn có lợi

Lazy init giảm startup time nhìn từ Kubernetes nhưng có thể dời độ trễ sang request đầu tiên. Nếu p99 SLO chặt, cần test **first-request latency**, pre-initialize đường nóng hoặc chỉ bật readiness sau mức tối thiểu phù hợp.

## 15. Warm capacity không thể thay cho overload protection

Dù pre-scale đúng, sự kiện ngoài dự báo có thể tăng 10 lần, hoặc database dùng chung bị suy giảm. Cần cơ chế bảo vệ:

### 15.1. Rate limiting và admission control

Giới hạn lượng request vào hệ thống theo user, tenant, operation hoặc capacity hiện có. Phân biệt offered load và admitted load. Nếu gateway trả 429 nhiều, traffic ở Order có thể thấp nhưng user impact lớn; SLI phải tính đến từ chối quá tải theo hợp đồng.

### 15.2. Bounded queues và backpressure

Queue vô hạn cho cảm giác “không mất request” cho đến khi latency vượt SLA, memory tăng và hệ thống crash. Queue có giới hạn, deadline, DLQ và backpressure giúp giữ tài nguyên ổn định.

### 15.3. Concurrency limit và bulkhead

Giới hạn outstanding calls tới DB/Payment. Nếu Payment chậm, không để toàn bộ thread và connection pool của Order bị chiếm. Có thể từ chối/degrade phần gọi phụ nếu contract cho phép.

### 15.4. Retry budget

Một retry được coi là **công việc mới** ở downstream. Khi capacity đã thiếu, retry 3 lần mỗi timeout có thể nhân tải và kéo dài sự cố. Retry có giới hạn, jitter, deadline và idempotency key bắt buộc đối với các side effect.

### 15.5. Circuit Breaker và fallback

Circuit Breaker có thể tránh gửi tiếp request tới dependency đang hỏng. Fallback chỉ là thành công nếu đáp ứng contract nghiệp vụ; không trả HTTP 200 cho một kết quả quan trọng không được xác nhận và gọi là khỏe.

### 15.6. Ưu tiên tác vụ

Khi thiếu capacity, có thể ưu tiên checkout đã xác nhận hơn tác vụ gợi ý sản phẩm hoặc email marketing, nếu product contract cho phép. Cần tách queue/pool hoặc priority policies tránh starvation của tác vụ thấp ưu tiên.

## 16. Không scale quá nhanh vượt khả năng dependency

Giả sử mỗi Order Pod mở tối đa 30 DB connections. Với 10 Pod:

~~~text
10 pods × 30 max connections = 300 theoretical connections.
~~~

Nếu tăng lên 40 Pod:

~~~text
40 × 30 = 1.200 potential connections.
~~~

Nhưng database chỉ cho phép khoảng 500 connections cho ứng dụng này. Scale-up có thể khiến connection acquire failure, timeout hoặc overload trước khi throughput tăng.

Cần:

- Per-Pod pool limits được thiết kế theo tổng replica tối đa.
- Connection proxy/pooling nếu phù hợp.
- Giới hạn concurrency cho truy vấn tốn tài nguyên.
- Quan sát DB active/pending connections và slow queries.
- Đánh giá tỷ lệ cache miss khi Pod mới cold.
- Scale dependency hoặc giảm công việc mỗi request.
- Load test với replica và connection topology thực.

**Autoscaling của một service cần có capacity budget cho toàn bộ dependency bắt buộc.**

### 16.1. Bottleneck dịch chuyển

Sau khi tăng Order Pods, bottleneck có thể chuyển từ CPU Order sang DB, rồi sang Inventory hoặc Payment quota. Tối ưu chỉ một tầng thường không giải quyết mục tiêu throughput end-to-end.

### 16.2. Worker scale và partition limit

Một Kafka consumer group có số partition hữu hạn; tăng consumer vượt số partition có thể tạo consumer idle, không tăng throughput. Với ordering hoặc single-threaded key processing, cần xem partition/key distribution thay vì chỉ tăng Pod.

### 16.3. Network và cloud quota

CPU còn rảnh không bảo đảm có đủ địa chỉ IP, ephemeral ports, NAT capacity, DNS throughput, disk IOPS hay quota API provider. Phải theo dõi các giới hạn cơ sở hạ tầng trong kịch bản peak.

## 17. Rolling deployment cùng lúc với đỉnh tải

Thời điểm sale cũng có thể trùng bản deploy. Rolling update tạo Pod V2, drain V1, trong khi autoscaler đang tăng số replicas. Các rủi ro:

- Pod V2 cold, chưa warm.
- maxSurge cần thêm node capacity.
- maxUnavailable làm giảm Pod Ready.
- Mixed versions có API/schema không tương thích.
- DB migration tạo lock đúng lúc traffic cao.
- Cache invalidation tăng query load.
- New version dùng CPU hoặc memory nhiều hơn version cũ.

Khuyến nghị theo rủi ro:

1. Tránh rollout thay đổi lớn sát sự kiện cực kỳ nhạy cảm nếu tổ chức có freeze policy.
2. Hoàn tất pre-scaling và warm-up trước đỉnh.
3. Canary V2 trên traffic đại diện, đo SLO.
4. Đảm bảo rollouts giữ đủ available capacity.
5. Không phụ thuộc việc scale-up tức thời để bù capacity bị rolling update rút khỏi.
6. Có rollback plan không làm hỏng database schema/event compatibility.

**Không mặc định freeze deployment là giải pháp duy nhất.** Một bản vá bảo mật khẩn cấp có thể phải triển khai trong giờ cao điểm; khi đó cần kiểm soát capacity, rủi ro và giám sát chặt hơn.

## 18. Scale-down cũng có độ trễ và rủi ro

Sau đỉnh, CPU/RPS giảm. Nếu scale-down quá nhanh:

- Queue/job bất đồng bộ chưa hoàn tất.
- Các request dài hoặc streaming đang chạy.
- Cache vừa ấm bị loại rồi phải làm ấm lại nếu traffic tăng lần nữa.
- LB còn gửi request đến Pod đang terminate.
- HPA có thể oscillate khi tải dao động gần threshold.
- KEDA/worker scale quá thấp làm backlog age tăng.

Vì vậy thường cần **cooldown/stabilization**, graceful shutdown, minReplicas thích hợp và kiểm tra lưu lượng/queue trước khi giảm.

### 18.1. Cost versus availability

Giữ warm capacity lâu giúp giảm rủi ro nhưng tăng chi phí. Hãy đo:

- Pod-hours/node-hours chi thêm cho headroom.
- Error budget tiết kiệm được.
- p95/p99 và rejected requests trong thời gian spike.
- Số lần scale không cần thiết do forecast sai.
- DB/redis connection cost hoặc cache usage.
- Chi phí hạ tầng cross-zone.

Một pre-scaling plan tốt cần **trước đỉnh đủ capacity, sau đỉnh hạ đúng lúc và không gây sự cố khi giảm**.

## 19. Quan sát toàn bộ hành trình scale-up

Chỉ nhìn CPU và replica count không đủ. Một dashboard nên có:

| Nhóm | Tín hiệu | Câu hỏi |
| --- | --- | --- |
| User experience | Good request ratio, 5xx/429, p95/p99, business failures | Khách hàng có bị ảnh hưởng không? |
| Demand | Offered RPS, checkout intent, producer rate | Nhu cầu thực tăng bao nhiêu? |
| Supply | Desired/Current/Ready/Available Pods | Công suất mong muốn và đang dùng khác gì? |
| Scheduling | Pending Pods, scheduler reason, AZ distribution | Thiếu tài nguyên hay constraint? |
| Node | Node count/Ready, provisioning time, IP/quota | Hạ tầng mở rộng nhanh thế nào? |
| Startup | Startup duration, image pull, readiness lag | Pod chậm ở pha nào? |
| Warm-up | First-request latency, cache hit, DB connection acquisition | Pod Ready đã chịu tải tốt chưa? |
| Runtime | CPU throttling, GC, threads, in-flight | Tài nguyên nào gần bão hòa? |
| Dependencies | DB pool pending, broker lag, provider 429 | Nơi nào là bottleneck sau scale? |
| Resilience | Retry attempts, circuit state, load shed rate | Scale-up có gây amplification không? |
| Economy | Replicas/node-hours, unused capacity | Headroom có đang quá lớn không? |

### 19.1. Các thời điểm cần timestamp

Ghi lại với mỗi scale-up:

~~~text
T0  demand threshold crossed
T1  metric visible to autoscaler
T2  desiredReplicas increased
T3  new Pod created
T4  Pod scheduled
T5  node ready (if newly provisioned)
T6  container started
T7  Pod Ready
T8  first useful request served
T9  observed throughput/latency stable
~~~

Từ đó phân biệt:

- **Detection delay:** T1−T0.
- **Controller delay:** T2−T1.
- **Placement/provision delay:** T6−T2 theo đường đi phù hợp.
- **Warm-serving delay:** T9−T6.
- **Total effective lead time:** T9−T0.

Đừng chỉ tính từ HPA scale event tới Pod Running, vì đã bỏ qua detection lag và warm-up.

### 19.2. Exemplars, logs và traces

Metric giúp xác nhận ở quy mô lớn. Log/events của scheduler, HPA và node provisioner giúp hiểu tại sao chậm. Trace của các request p99 cao giúp định vị DB pool, cache misses hoặc downstream retries.

Không gắn requestId, userId hoặc raw URL vào metric labels có cardinality lớn; dùng trace/log có phân quyền cho định danh request.

## 20. Ví dụ truy vấn PromQL

Tên metric ở đây là **minh họa**, phải đối chiếu exporter thực tế.

### 20.1. RPS tại service

~~~promql
sum(
  rate(http_server_requests_seconds_count{
    job="order-service",
    uri!~"/actuator.*"
  }[5m])
)
~~~

Cần dùng offered RPS từ gateway để nhận biết nhu cầu bị rate limiting chặn trước service. Trong thời gian đỉnh rất ngắn, cửa sổ 5 phút làm mượt spike; có thể quan sát thêm 30s–1m tùy scrape interval và số mẫu.

### 20.2. HTTP 5xx ratio

~~~promql
sum(rate(http_server_requests_seconds_count{
  job="order-service",
  status=~"5.."
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    job="order-service"
  }[5m])),
  1e-9
)
~~~

Tử/mẫu phải cùng scope. Clamp tránh chia 0 nhưng không làm tỷ lệ có ý nghĩa khi request gần như không tồn tại; alert cần xử lý low traffic và missing metrics.

### 20.3. Latency p95

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      job="order-service"
    }[5m])
  )
)
~~~

Query cần classic histogram bucket được bật. Kết quả ước tính theo phân phối gộp; không lấy trung bình p95 từng Pod. Nếu metric export theo native histogram hoặc namespace khác cần đổi truy vấn.

### 20.4. Desired vs Available Pods

Giả sử exporter Kubernetes có metric phù hợp:

~~~promql
kube_deployment_spec_replicas{
  namespace="production",
  deployment="order-service"
}
~~~

~~~promql
kube_deployment_status_replicas_available{
  namespace="production",
  deployment="order-service"
}
~~~

Gap lớn kéo dài sau scale cho thấy có vấn đề scheduling, startup, readiness hoặc node provisioning. Hãy đọc events của Pod/Node để phân loại.

### 20.5. Queue age và rate

Giả sử worker có custom metrics:

~~~promql
queue_oldest_message_age_seconds{queue="order-events"}
~~~

~~~promql
sum(rate(queue_messages_processed_total{
  queue="order-events"
}[5m]))
~~~

Hai tên `queue_*` trên là ví dụ cần instrument. Queue length/lag tăng không nói đủ khi không biết processing throughput và deadline.

## 21. Cảnh báo khi autoscaling không bắt kịp

Một số quy tắc có thể hữu ích, sau khi hiệu chỉnh theo workload:

| Cảnh báo | Điều kiện gợi ý | Việc cần làm |
| --- | --- | --- |
| User-facing SLO burn | Bad event ratio vượt ngưỡng SLO nhiều cửa sổ | Incident handling theo user impact |
| Desired ≫ Available | Gap kéo dài quá lead time p95 dự kiến | Xem scheduler/node/quota/startup |
| Pending Pods | Pods Pending với insufficient resources/constraints | Xem resource, IP, AZ, affinity |
| Max replicas nhưng saturation cao | HPA chạm max và p95/error xấu | Kiểm tra capacity/dependency, load shed |
| Node provisioning lag | VM/node chậm join cluster | Kiểm tra cloud capacity, quota, subnet |
| Startup/warm-up regression | Pod Ready chậm hơn baseline | Xem image, JVM, cache, DB |
| DB overload sau scale | Connection pending/timeout tăng theo replica | Giảm pool/requests, sửa DB bottleneck |
| Queue deadline risk | Oldest message age tăng tới deadline | Tăng worker nếu downstream chịu được, hoặc backpressure |
| Missing telemetry | Metric scrape/collector outage | Không tin biểu đồ “không thấy lỗi” |
| Overprovisioning kéo dài | Warm replicas duy trì sau campaign | Kiểm tra lịch/cooldown và cost |

**Một alert phải chỉ ra hành động.** Không nên page chỉ vì CPU 70% trong vài phút nếu còn headroom và SLO vẫn tốt; đồng thời không đợi 5xx tăng mới phát hiện pending queue sát deadline.

## 22. Chiến lược theo loại workload

### 22.1. User-facing synchronous API

Ưu tiên capacity có sẵn trước burst vì khách hàng có thời hạn chờ ngắn. Dùng:

- MinReplicas hoặc warm capacity.
- Autoscaling theo CPU/RPS/concurrency có kiểm chứng.
- Readiness và startup tốt.
- Admission control, timeout, retry budget.
- Edge SLI, p95/p99 và 429/5xx observability.
- Scheduled pre-scaling cho campaign biết trước.

### 22.2. Event-driven worker

Queue có thể buffer burst, miễn là deadline nghiệp vụ cho phép. Dùng:

- Queue age/lag/arrival rate.
- Consumer concurrency và partition limits.
- HPA/KEDA theo metric phù hợp.
- DLQ, retry, idempotency.
- Scale-down có thời gian xử lý job.
- Pre-warm worker trước batch lớn nếu backlog deadline chặt.

### 22.3. Batch/ETL

Cần quan tâm completion deadline và giá/compute efficiency hơn HTTP latency. Có thể pre-provision node theo lịch và scale rộng khi job đến, nhưng phải giữ giới hạn DB/storage/network.

### 22.4. Streaming/gRPC/WebSocket

Một instance giữ kết nối dài hạn có thể khó scale traffic bằng tăng replica sau khi connection đã được chọn. Phải thiết kế connection rebalance, reconnect/resume, per-connection capacity và connection draining.

### 22.5. Stateful service

DB, broker và cache có thủ tục scale riêng: rebalance, leader election, replication, consistency, storage resizing. Không giả định có thể tăng throughput tuyến tính theo replica như một REST API stateless.

## 23. Chương trình thử tải phải bộc lộ độ trễ scale

Một bài load test chỉ tăng traffic rất từ từ trong 30 phút có thể khiến HPA luôn kịp và **che việc thiếu headroom cho burst thật**. Cần có nhiều hình dạng tải:

| Kịch bản | Đặc điểm | Điều cần chứng minh |
| --- | --- | --- |
| Baseline | Tải nền ổn định | SLO và capacity nền |
| Ramp | Tăng dần có kiểm soát | Ngưỡng HPA, chất lượng scale |
| Spike | Tăng từ thấp lên cao trong vài giây | Warm capacity và load shedding |
| Step | Tăng thêm một bậc rồi giữ lâu | Lead time và steady-state |
| Sawtooth | Tải lên xuống liên tục | Autoscaling có flapping không |
| Short burst | Đỉnh ngắn hơn thời gian scale-up | Có bảo vệ bằng headroom/queue không |
| Sustained peak | Tải cao vài chục phút | Dependency capacity và cost |
| Scale-down | Tải giảm nhanh | Không mất job, không terminate request |
| AZ failure at peak | Mất capacity khi nhu cầu cao | Dự phòng N−1, routing, quota |
| Dependency slowdown | DB/Payment chậm trong lúc scale | Không gây cascading/retry storm |

### 23.1. Kịch bản flash sale

Giả sử:

- Tải nền: 800 RPS.
- Peak dự kiến: 2.000 RPS.
- Một Pod đạt 140 RPS an toàn.
- HPA từ 6 tới 40.
- Lead time quan sát: 150 giây ở p95.
- Campaign bắt đầu lúc 20:00.

**Phương án A — Reactive only:** bắt đầu với 6 Pod, cho traffic đột ngột tăng 2.000 RPS; đo error/p99 trong 150 giây đầu.

**Phương án B — Pre-scale:** chuẩn bị ít nhất 15 Pod Ready và warm trước 20:00; giữ HPA có thể scale cao hơn nếu đỉnh vượt dự kiến.

**Phương án C — Pre-scale + overload controls:** như B, có rate limit, bounded queue, retry budget, mục tiêu chống cascading failure.

Đo cùng các SLI:

- Good checkout ratio.
- P95/p99 latency.
- 429/5xx và queue oldest age.
- Effective Ready warm capacity.
- DB active/pending connections.
- Retry attempts/RPS downstream.
- Node-hours/cost.

Không chỉ so sánh “số Pod cuối cùng”, vì điều quan trọng là **số request bị ảnh hưởng trước khi Pod mới phục vụ**.

### 23.2. Kịch bản thiếu node

Để kiểm tra hạ tầng, thử trong môi trường được phép:

1. Bắt đầu với node pool gần đầy.
2. Tăng desired replicas.
3. Đo số Pod Pending, thời gian tạo node, quota errors.
4. Ghi T_request_scale → T_node_ready → T_pod_ready → T_effective_capacity.
5. So sánh với test có warm node pool.
6. Kiểm tra topology spread và phân bố AZ.

Cần đảm bảo fault/load test không gây ảnh hưởng production ngoài phạm vi đã phê duyệt.

### 23.3. Kịch bản Pod cold và connection storm

Khởi động 20 Pod đồng thời, theo dõi DB connection, cache miss, JVM startup, first-request p99. Nếu DB bị nghẽn dù RPS chưa tăng, vấn đề nằm ở warm-up/cấu hình pool chứ không ở nhu cầu user thật.

## 24. Runbook khi tải tăng trước khi capacity bổ sung

**Bước 1 — Xác nhận tình trạng:** offered RPS, admitted RPS, errors, p95/p99, queue age và thời điểm peak bắt đầu.

**Bước 2 — Định vị nút nghẽn:** CPU/throttling, in-flight requests, thread/DB pool pending, dependency timeout, broker lag. Không mặc định mọi lỗi là thiếu Pod.

**Bước 3 — Đọc autoscaler:** desired/current/available replicas; có chạm maxReplicas, thiếu metric hay policy limit không?

**Bước 4 — Đọc scheduler/node:** Pods Pending vì CPU/memory, zone constraints, taints, image pull, quota hay node autoscaler lag?

**Bước 5 — Bảo vệ hệ thống:** giới hạn admitted traffic, giảm retry amplification, ưu tiên nghiệp vụ trọng yếu và kích hoạt fallback được thiết kế nếu cần.

**Bước 6 — Thêm capacity đúng tầng:** có thể tăng Pod/node nếu bottleneck ở compute; nếu DB là nút nghẽn phải xử lý DB/connections/throttling trước.

**Bước 7 — Quan sát warm-up:** Pod mới Ready có thực sự phục vụ với latency đạt SLO không, có cache stampede hoặc DB connection storm không?

**Bước 8 — Ổn định và phục hồi:** error budget, p95/p99, backlog, old connections, DLQ, idempotency và kết quả nghiệp vụ.

**Bước 9 — Sau đỉnh:** giảm replica có kiểm soát, đảm bảo không làm mất job/in-flight request, trả capacity về mức hợp lý.

**Bước 10 — Postmortem:** so sánh peak thực với forecast, lead time thực với kế hoạch, thời gian thiếu capacity và biện pháp rút ngắn độ trễ/pre-scale.

**Không sửa đồng thời quá nhiều policies** nếu có thể tránh; thay đổi HPA, node pool và retry cùng lúc dễ che root cause và gây dao động.

## 25. Các tình huống dễ nhầm

### 25.1. HPA desired tăng nhanh nhưng vẫn lỗi

Lý do có thể: Pod Pending, image pull, startup quá lâu, readiness không qua, cache cold, DB quá tải hoặc load balancer chưa route vào Pod mới.

**Bài học:** desiredReplica là quyết định, không phải throughput bổ sung.

### 25.2. CPU thấp nhưng p99 cao

Service chờ DB hoặc Payment; tăng Pod không làm dependency nhanh hơn. Cần trace, DB pool pending, queue age và timeout metrics.

### 25.3. Scale lên rồi hệ thống chậm hơn

Nhiều Pod mở connection, cache miss và retry cùng lúc; DB/NAT/provider quota trở thành bottleneck. Cần concurrency/pool budget và warm-up có kiểm soát.

### 25.4. Scale không xảy ra khi traffic tăng

Có thể metric không phản ánh offered demand vì gateway đang trả 429, CPU còn thấp vì blocked I/O, missing metrics hoặc HPA đã chạm max. Chọn tín hiệu theo bottleneck và user journey.

### 25.5. Replicas giảm khi backlog vẫn còn

Scale-down dựa trên CPU giảm dù consumer đang chờ một dependency chậm; job chưa hoàn tất. Cần queue age/deadline và chính sách drain.

### 25.6. Predictive model bỏ lỡ sự kiện mới

Dự báo dựa vào lịch sử chưa thấy chiến dịch mới, hoặc workload mix thay đổi. Giữ warm baseline, reactive fallback và overload controls.

### 25.7. Scheduled scaling sai timezone

Controller interpret giờ UTC còn lịch marketing dùng giờ địa phương; capacity tăng sau sự kiện. Cần quản lý timezone, DST nếu áp dụng, calendar và kiểm tra lại schedule trước campaign.

### 25.8. Pod “Ready” quá sớm

Startup probe qua nhưng JIT/cache còn cold; p99 xấu ở Pod mới. Đo first-request latency, warm capacity và progressive traffic.

### 25.9. Hard topology spread cản recovery

Khi một AZ unavailable, Pod mới Pending vì `DoNotSchedule` đòi cân bằng. Cần tính runbook để nới constraint có kiểm soát hoặc dự trữ đủ capacity ở những AZ còn lại.

### 25.10. Autoscale mà không có limit bảo vệ chi phí

Một metric lỗi hoặc retry loop tăng desired tới mức rất lớn. Cần maxReplicas, budget/quota, alarm và kiểm soát upstream load.

## 26. Bài tập thực hành

### Bài A — Tính replica

Một Pod đáp ứng 240 RPS trước khi p95 vượt SLO. Đội chọn target utilization tương đương 65% công suất đó. Tải nền 700 RPS và đỉnh 2.300 RPS.

**Hỏi:** số replica kế hoạch tối thiểu là bao nhiêu ở nền và đỉnh?

**Hướng giải:** công suất an toàn mỗi Pod \(240\times0,65=156\) RPS. Nền \(\lceil700/156\rceil=5\). Đỉnh \(\lceil2300/156\rceil=15\). Còn phải xét dependency và N−1 failure.

### Bài B — Lead time

Sale bắt đầu 20:00. Quan sát effective scale-up lead time p95 = 210 giây; cần thêm 90 giây safety margin.

**Hỏi:** bắt đầu pre-scale muộn nhất khi nào?

**Hướng giải:** 210+90=300 giây, tức **19:55**. Nếu muốn có load test/synthetic check sau warm-up, cần thêm thời gian đó trước peak.

### Bài C — Queue trong lúc chờ scale

Producer tăng từ 600 lên 1.200 messages/giây. Consumer đang phục vụ 800 messages/giây trong 2 phút đầu khi chờ scale.

**Hỏi:** backlog tăng khoảng bao nhiêu?

**Hướng giải:** \((1200−800)\times120=48.000\) messages, nếu bỏ qua drop, retry và thay đổi throughput. Phải kiểm tra message age và SLA để biết mức ảnh hưởng.

### Bài D — DB connection budget

Mỗi Order Pod có maximum DB pool 25 connections; HPA max 50 pods; DB chỉ cho phép khoảng 600 connections cho Order.

**Hỏi:** chuyện gì có thể xảy ra? Nên xem xét gì?

**Hướng giải:** tối đa tiềm năng 1.250 connections vượt ngân sách 600. Cần điều chỉnh pool per Pod, proxy/pooling, concurrency, DB scaling hoặc giới hạn HPA trước khi bật scale 50 Pod.

### Bài E — HPA không giúp I/O-bound service

Order CPU 20% nhưng p99 tăng lên 8 giây; DB pool pending và active connections chạm max. HPA CPU không tăng replica.

**Hỏi:** có phải đặt CPU target xuống 10% là đúng?

**Hướng giải:** chưa. Xác minh DB là bottleneck; thêm Pod có thể mở thêm connection và làm xấu hơn. Đo DB acquire latency/lock contention, tối ưu truy vấn/pool và chọn capacity/metric phù hợp.

### Bài F — Forecast sai

Dự báo cần 15 Pod, thực tế chỉ có 200 RPS. Hệ thống giữ 15 Pod thêm 12 giờ vì quên schedule hạ xuống.

**Hỏi:** cải tiến gì?

**Hướng giải:** schedule có end time, TTL/rollback, owner, scale-down stabilization theo metric và cost alert. Không khóa replica mãi sau chiến dịch.

### Bài G — Startup nhanh nhưng throughput thấp

Pod mới Ready trong 10 giây, nhưng 60 giây đầu mỗi Pod chỉ xử lý được 30% throughput bình thường.

**Hỏi:** cần tính lead time ra sao?

**Hướng giải:** capacity bổ sung không thể tính đủ ngay lúc Ready. Cần đo T_ready→T_warm_productive, dùng progressive routing, warm-up và capacity model theo thời gian.

### Bài H — Mất AZ tại đỉnh

Ba AZ mỗi AZ có 6 Pod, mỗi Pod an toàn 140 RPS. Peak 2.000 RPS. Mất AZ lớn nhất.

**Hỏi:** còn đủ công suất app không?

**Hướng giải:** còn 12 Pod × 140 = **1.680 RPS**, thiếu 320 RPS. Cần nhiều warm capacity hơn hoặc được phép giảm tải; HPA chỉ bù sau lag và chưa bảo đảm node ở AZ còn khỏe.

## 27. Checklist trước khi triển khai production

### Năng lực và SLO

- [ ] Đã định nghĩa user journey, SLI availability/latency và peak traffic mục tiêu.
- [ ] Đã load test công suất **đạt SLO** trên mỗi Pod, không dùng CPU tối đa tùy ý.
- [ ] Đã tính base, peak, burst và kịch bản mất Pod/node/AZ.
- [ ] Đã đo effective scale-up lead time p95/p99, gồm warm-up và routing.
- [ ] Có headroom đủ cho burst ngắn hơn lead time hoặc có overload policy rõ.

### Autoscaling

- [ ] Metric dùng cho HPA/KEDA phù hợp bottleneck; source và labels đã được xác nhận.
- [ ] minReplicas/maxReplicas và scale policies có owner và lý do.
- [ ] Node pool, subnet IP, CPU/memory quota đủ cho Pod mới.
- [ ] Topology spread/affinity không làm Pod Pending ngoài dự kiến.
- [ ] Startup/readiness/liveness và graceful termination được thử nghiệm.
- [ ] Scale-down không làm mất job hoặc đóng kết nối đột ngột.
- [ ] Có alert khi desired−available gap kéo dài.

### Chuẩn bị trước đỉnh

- [ ] Lịch campaign và timezone đã được xác nhận.
- [ ] Tính thời điểm pre-scale từ lead time quan sát và margin.
- [ ] Warm Pods/nodes/image/cache/connection được thiết kế không gây stampede.
- [ ] Scheduled controller không tranh quyền với HPA.
- [ ] Reactive scaling vẫn hoạt động khi tải vượt forecast.
- [ ] Có tự kết thúc schedule và hạ capacity khi traffic ổn định.
- [ ] Đã đo chi phí headroom và tác động tới SLO.

### Phụ thuộc và chống quá tải

- [ ] DB/broker/cache/provider có capacity budget khi app replica tăng.
- [ ] DB pool maximum tính tới maxReplicas.
- [ ] Có bounded queue, deadline, retries có giới hạn và backpressure.
- [ ] Có rate limiting/load shedding và ưu tiên nghiệp vụ rõ khi vượt capacity.
- [ ] Có idempotency cho retry thao tác có side effect.
- [ ] Monitoring phát hiện dependency đang chậm thay vì tự động tăng Pod vô hạn.

### Kiểm chứng và vận hành

- [ ] Đã thử burst ngắn, ramp, sustained peak, scale-down và AZ failure.
- [ ] Đo T0→T9 của quá trình scale-up, không chỉ số Pod Running.
- [ ] Dashboard có offered/admitted RPS, 5xx/429, p95/p99, saturation, Ready/Available.
- [ ] Theo dõi Pod Pending, image pull, node provisioning và warm-up latency.
- [ ] Có runbook khi autoscaling trễ hoặc bị chặn bởi quota/dependency.
- [ ] Đã diễn tập phản ứng: scale đúng tầng, load shedding, queue drain, rollback.
- [ ] Có postmortem sau peak để cập nhật lead time và forecast error.

## 28. Tổng kết

**Tự động mở rộng có độ trễ** vì hệ thống phải đo tải, ra quyết định, cấp phát hạ tầng, khởi động và làm ấm ứng dụng trước khi Pod thực sự phục vụ thêm request. Một controller có thể hoạt động đúng mà user-facing SLO vẫn bị vi phạm trong khoảng chờ.

Để phục vụ tải tăng mạnh, hãy **đo lead time thực**, **giữ warm capacity đủ cho burst**, **pre-scale trước thời điểm đã biết**, **duy trì reactive fallback** và **bảo vệ dependency bằng backpressure/rate limit/retry budget**. Khi tính số replica, luôn dùng throughput đạt SLO và xem capacity sau mất miền lỗi, không chỉ tổng replica ở trạng thái bình thường.

Thành công không được đo bằng “HPA đã lên 30 Pods”, mà bằng **đúng lúc khách hàng cần, hệ thống có đủ capacity hữu ích, latency/error vẫn đạt mục tiêu và không gây sự cố thứ cấp ở database, queue hoặc service khác**.
