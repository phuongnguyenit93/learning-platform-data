# Độ trễ mở rộng, dung lượng tối thiểu và khoảng ổn định

## 1. Autoscaling không làm năng lực tăng tức thời

Khi traffic tăng nhanh, hệ thống cần thêm instance, pod, task hoặc worker để tiếp tục đáp ứng request. Autoscaling giúp điều chỉnh số lượng tài nguyên theo tải, nhưng có một khoảng thời gian từ lúc tải thực sự tăng đến khi capacity mới có thể phục vụ. Khoảng này có thể bao gồm thời gian thu thập metric, đánh giá policy, gọi API cấp tài nguyên, chờ compute được provision, khởi động máy, pull image, khởi tạo ứng dụng, warm cache và vượt readiness check.

Nếu hệ thống chỉ bắt đầu scale khi latency đã vượt ngưỡng, capacity mới có thể đến quá muộn. Trong lúc chờ, hàng đợi tăng, request timeout, retry làm tải tăng thêm và dependency có thể quá tải. Ngược lại, nếu scale-in quá nhanh ngay khi metric giảm, tài nguyên có thể bị thu hồi trước khi đợt tải tiếp theo đến hoặc trong lúc request đang xử lý.

Ba khái niệm trong bài có liên hệ trực tiếp:

- **Scaling lag / scale-out delay:** thời gian từ khi có tín hiệu cần thêm năng lực đến khi năng lực mới thực sự usable.
- **Minimum capacity / baseline capacity:** mức tài nguyên tối thiểu cần duy trì để phục vụ tải nền, chịu lỗi và đáp ứng yêu cầu latency trong lúc autoscaling.
- **Stabilization window:** khoảng thời gian quan sát và làm trơn quyết định scale, đặc biệt để tránh scale-in ngay sau một nhịp tải giảm ngắn hoặc phản ứng quá mức với metric nhiễu.

Trong module **CLOUD_ARCHITECTURE**, đây là quyết định kiến trúc có ảnh hưởng đến độ tin cậy, hiệu năng, khả năng mở rộng, chi phí và vận hành. Mục tiêu không phải giữ thật nhiều máy hay scale nhanh bằng mọi giá; mục tiêu là duy trì đủ năng lực trong thời gian cần thiết, theo SLO và đặc tính tải thực tế.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân rã scaling lag thành các thành phần đo được.
2. Tính baseline/minimum capacity theo tải nền, headroom và khả năng chịu lỗi.
3. Chọn metric và ngưỡng scale-out/scale-in phù hợp.
4. Thiết kế stabilization window, cooldown và warm pool để hạn chế phản ứng dao động.
5. Phân biệt capacity được cấp với capacity thực sự sẵn sàng phục vụ.
6. Kiểm tra tác động autoscaling tới database, queue, network và downstream dependency.
7. Đặt SLO, dashboard và bài kiểm thử cho burst, ramp-up, spike và tải kéo dài.

## 2. Vòng đời một quyết định scale-out

Một policy có thể phát hiện CPU tăng nhanh, nhưng workload chưa chắc đã có thêm năng lực ngay. Cần nhìn toàn bộ chuỗi:

~~~mermaid
flowchart LR
    A["Traffic / backlog tăng"] --> B["Metric collection"]
    B --> C["Autoscaler evaluation"]
    C --> D["Capacity request"]
    D --> E["Provision compute"]
    E --> F["Boot / schedule"]
    F --> G["Image pull / init"]
    G --> H["Readiness / warm-up"]
    H --> I["Usable capacity"]
~~~

Tổng scaling lag có thể được mô hình hóa:

\[
T_{usable} =
T_{observe} + T_{decision} + T_{provision}
+ T_{startup} + T_{ready}
\]

Trong đó:

- **Observe:** chờ metric scrape, aggregation hoặc event được nhận.
- **Decision:** autoscaler tính toán số lượng cần thêm, áp dụng min/max và policy.
- **Provision:** cloud provider cấp VM/node hoặc scheduler tìm tài nguyên.
- **Startup:** boot OS/runtime, pull image, mount volume, load model và khởi động process.
- **Ready:** health/readiness probe thành công, cache hoặc connection pool đủ sẵn sàng.

Đây là mô hình để phân tích, không phải công thức cho rằng mọi giai đoạn luôn nối tiếp hoàn toàn. Một số tác vụ chạy song song hoặc được cache; cần đo thực tế theo percentile.

### 2.1. Các khoảng thời gian cần đo

| Thành phần | Điểm bắt đầu/kết thúc | Nguyên nhân làm chậm |
|---|---|---|
| Metric delay | Tải đổi → metric phản ánh | Scrape interval, aggregation window, telemetry pipeline |
| Evaluation delay | Metric sẵn sàng → policy quyết định | Controller sync interval, threshold, scale policy |
| Provision delay | Yêu cầu → VM/node/task được cấp | Cloud quota, capacity shortage, node provisioning |
| Scheduling delay | Pod/task pending → được đặt lên compute | Thiếu CPU/memory, affinity, taint, resource fragmentation |
| Startup delay | Được cấp → process khởi động | OS boot, image pull, dependency initialization |
| Readiness delay | Process start → nhận traffic | Health check, warm cache, model loading, connection setup |
| Routing delay | Ready → traffic thực sự đến | Endpoint propagation, load balancer health, DNS/service discovery |

Đừng đo duy nhất thời gian API autoscaler trả về thành công. Instance có thể đã tồn tại nhưng chưa nhận traffic; pod có thể ở trạng thái Running mà readiness vẫn fail.

## 3. Tải thay đổi nhanh hơn khả năng scale

### 3.1. Ví dụ về burst

Giả sử một API ban đầu nhận 1.000 request/giây. Một chiến dịch làm traffic tăng lên 4.000 request/giây trong vòng 20 giây. Mỗi replica xử lý an toàn 250 request/giây; hệ thống ban đầu có 6 replica.

- Capacity ban đầu: 6 × 250 = 1.500 request/giây.
- Capacity cần để phục vụ 4.000 request/giây: ít nhất 16 replica theo phép chia lý thuyết.
- Thiếu hụt ngay khi burst: 2.500 request/giây.
- Nếu scale-out cần 90 giây, hệ thống phải chịu thiếu hụt trong khoảng thời gian đáng kể.

Con số 16 chưa tính headroom, phân phối traffic không đều, p99 latency, lỗi replica và giới hạn dependency. Nếu đặt mục tiêu sử dụng tối đa 70% capacity trong trạng thái bình thường, capacity cần thiết còn cao hơn:

\[
N = \left\lceil \frac{4000}{250 \times 0.70} \right\rceil = 23
\]

Ví dụ này cho thấy scale-out phản ứng sau khi burst bắt đầu có thể không đủ. Cần baseline cao hơn, scheduled/predictive scaling, warm pool hoặc cơ chế buffer như queue tùy loại workload.

### 3.2. Các kiểu tải

| Kiểu tải | Đặc điểm | Cách ứng phó thường phù hợp |
|---|---|---|
| **Steady growth** | Tăng dần trong vài phút/giờ | Reactive autoscaling thường đủ nếu lag được đo |
| **Sharp spike** | Tăng mạnh trong vài giây | Baseline/headroom, pre-scale, queue hoặc admission control |
| **Predictable peak** | Có lịch rõ theo ngày/chiến dịch | Scheduled scaling kết hợp reactive scaling |
| **Bursty arrivals** | Đợt tải ngắn, không đều | Buffer queue, concurrency cap, scale theo backlog |
| **Long-running growth** | Mức tải cao kéo dài | Scale capacity, kiểm tra quota, tối ưu bottleneck và cost |
| **Sudden drop** | Tải giảm nhanh | Stabilization scale-in, drain và bảo vệ request đang chạy |

Không có một policy duy nhất tối ưu cho mọi loại tải. Với interactive API, latency trong burst rất quan trọng. Với batch queue, có thể chấp nhận backlog trong một khoảng thời gian nếu age không vượt SLA.

## 4. Baseline và minimum capacity

**Minimum capacity** là mức tài nguyên thấp nhất mà hệ thống duy trì dù metric hiện tại thấp. Nó giúp đảm bảo ứng dụng không phải bắt đầu từ zero hoặc chờ quá lâu để khôi phục năng lực tối thiểu.

Minimum capacity có thể được biểu diễn bằng:

- Số instance/replica tối thiểu.
- Số node hoặc worker tối thiểu trong cluster.
- Số warm execution environments hoặc warm pool entries.
- Mức provisioned concurrency cho function.
- Số connection/partition/consumer tối thiểu.
- Capacity dự phòng cho failure domain hoặc maintenance.

### 4.1. Minimum không nhất thiết bằng một

Chạy một replica có thể đủ cho môi trường dev, nhưng production cần xét:

- Khả năng chịu lỗi khi một replica/node/zone ngừng hoạt động.
- Rolling deployment có cần capacity để thay thế instance cũ không?
- Workload có session/state gắn với instance không?
- Traffic nền tối thiểu và mục tiêu latency là gì?
- Warm-up có lâu không?
- Có cần duy trì ít nhất một instance ở mỗi zone không?

Một minimum capacity có thể được tính theo yêu cầu availability và topology, không chỉ trung bình traffic.

### 4.2. Tính baseline theo throughput

Giả sử:

- Peak traffic dự kiến: 2.400 request/giây.
- Một replica xử lý an toàn: 300 request/giây.
- Mục tiêu utilization tối đa: 60%.
- Cần chịu mất một replica mà vẫn giữ được tải mục tiêu.

Capacity mỗi replica tại mức utilization mục tiêu:

\[
300 \times 0.60 = 180 \text{ request/giây}
\]

Số replica hoạt động cần thiết:

\[
N_{active} = \left\lceil \frac{2400}{180} \right\rceil = 14
\]

Nếu cần chịu mất một replica:

\[
N_{total} = N_{active} + 1 = 15
\]

Đây là cách tính minh họa; hệ thống nhiều zone có thể yêu cầu phân bổ dự phòng khác. Cũng cần load test để xác định throughput an toàn thay vì lấy thông số tối đa của benchmark.

### 4.3. Minimum, desired và maximum

| Tham số | Ý nghĩa | Câu hỏi thiết kế |
|---|---|---|
| **Minimum** | Không scale thấp hơn mức này | Đủ chịu tải nền và lỗi đơn lẻ không? |
| **Desired** | Mức hiện tại autoscaler muốn đạt | Có phản ánh metric và policy không? |
| **Maximum** | Trần autoscaling | Có đủ headroom nhưng không vượt khả năng DB/quota/chi phí? |

Maximum không chỉ là giới hạn compute. Nếu tăng replica từ 20 lên 100 nhưng database chỉ chịu được 40 connection mới, autoscaling có thể làm outage nặng hơn.

## 5. Warm pool, pre-warming và provisioned capacity

Để giảm scaling lag, hệ thống có thể duy trì tài nguyên đã khởi tạo một phần hoặc chuẩn bị trước.

| Cơ chế | Ý nghĩa | Phù hợp với |
|---|---|---|
| **Baseline replicas** | Luôn giữ một số process/replica hoạt động | API, worker cần phản hồi nhanh |
| **Warm pool** | Giữ instance đã boot hoặc ở trạng thái khởi tạo một phần để cấp nhanh | VM/compute có startup chậm |
| **Provisioned concurrency** | Chuẩn bị sẵn execution environment cho function theo cấu hình dịch vụ | Serverless function nhạy cold start |
| **Scheduled pre-scale** | Tăng desired capacity trước thời điểm peak dự đoán | Bán vé, campaign, lịch báo cáo |
| **Predictive scaling** | Dự báo tải và cấp capacity trước | Workload có pattern lịch sử ổn định |
| **Image/model prefetch** | Tải image, package hoặc model trước | Container lớn, inference workload |
| **Connection/cache warm-up** | Chuẩn bị pool và cache trước khi nhận tải lớn | DB-bound API hoặc ứng dụng phụ thuộc cache |

Warm resource có chi phí giữ sẵn và có thể trở nên stale nếu code/config thay đổi. Cần quy định cách refresh, health check, expiry và bảo vệ credential.

### 5.1. Khi nào không cần warm pool?

- Workload có thể scale từ zero mà vẫn đạt SLO.
- Task chạy nền chấp nhận delay.
- Cold start rất ngắn so với latency budget.
- Chi phí duy trì warm capacity lớn hơn lợi ích latency.
- Traffic khó dự đoán và có buffer phù hợp.

## 6. Chọn metric cho autoscaling

Metric tốt cần phản ánh mức bận hoặc nhu cầu thực tế, có quan hệ với bottleneck và thay đổi đủ sớm để policy phản ứng.

| Metric | Khi hữu ích | Hạn chế |
|---|---|---|
| CPU utilization | Workload CPU-bound, request load tương quan với CPU | Không phản ánh chờ I/O, queue hay memory pressure |
| Memory utilization | Workload có memory pressure rõ | Scale-out không giải quyết leak; metric có thể không giảm khi idle do cache |
| Request rate | API có chi phí xử lý tương đối ổn định | Không phản ánh request complexity |
| Concurrent requests / in-flight | Mỗi instance có giới hạn concurrency | Cần đo đúng thời gian request và capacity per instance |
| Queue depth | Worker xử lý bất đồng bộ | Depth đơn thuần không tính tốc độ xử lý và tuổi message |
| Queue age / oldest message | Liên hệ trực tiếp với freshness/SLA | Cần metric đáng tin và scale theo tốc độ drain |
| Latency p95/p99 | Phát hiện người dùng bắt đầu bị ảnh hưởng | Là tín hiệu trễ; có thể scale sau khi SLO đã vi phạm |
| DB connection/CPU/lock | Phát hiện bottleneck data layer | Có thể cho thấy cần bảo vệ/constrain app scale hơn là scale thêm |
| Custom business metric | Workload có cost/request khác nhau | Cần instrumentation và quản lý metric chất lượng |

Không nên autoscale chỉ theo CPU nếu bottleneck thực tế là database connection hoặc external API quota. Thêm replica có thể làm tăng số request song song và khiến downstream sụp đổ.

### 6.1. Queue backlog và tốc độ xử lý

Với queue, số message hiện có chưa đủ để quyết định. Cần ước lượng:

- Backlog \(B\): số message chờ.
- Arrival rate \(\lambda\): message đến mỗi giây.
- Service rate mỗi worker \(\mu\): message xử lý mỗi giây.
- Số worker \(N\): capacity xử lý tổng xấp xỉ \(N\mu\).

Backlog giảm khi:

\[
N\mu > \lambda
\]

Nếu muốn drain backlog trong thời gian \(T\), capacity cần xấp xỉ:

\[
N\mu \geq \lambda + \frac{B}{T}
\]

Đây là mô hình đơn giản giả định tốc độ ổn định, bỏ qua retry, batch size và phân phối thời gian xử lý. Dùng nó làm ước lượng ban đầu rồi kiểm chứng bằng workload thực.

## 7. Stabilization window, cooldown và hysteresis

Autoscaler có thể dao động nếu metric vượt ngưỡng rồi giảm ngay sau một đợt scale. Scale-out rồi scale-in liên tục làm tăng chi phí, gây churn connection, cache miss và deployment instability.

**Stabilization window** là cửa sổ dùng để xem xét các recommendation/metric gần đây trước khi thực hiện scale, nhất là scale-in. **Cooldown** là khoảng thời gian sau một hành động scale trong đó policy hạn chế hoặc trì hoãn quyết định tiếp theo. **Hysteresis** là dùng ngưỡng scale-out và scale-in khác nhau để tránh bật/tắt liên tục quanh một điểm.

### 7.1. Minh họa hysteresis

~~~mermaid
flowchart TD
    M["Observe utilization"] --> High{"Above scale-out threshold?"}
    High -->|Yes| Out["Scale out"]
    High -->|No| Low{"Below scale-in threshold long enough?"}
    Low -->|Yes| Stable{"Minimum capacity and drain safe?"}
    Stable -->|Yes| In["Scale in gradually"]
    Stable -->|No| Keep["Keep capacity"]
    Low -->|No| Keep
    Out --> Window["Stabilization / cooldown"]
    In --> Window
    Keep --> M
    Window --> M
~~~

Ví dụ, scale-out khi CPU trên 65% liên tục 2 phút, nhưng chỉ scale-in khi CPU dưới 35% liên tục 10 phút và không có queue age/latency tăng. Hai ngưỡng và hai cửa sổ khác nhau tạo khoảng đệm.

### 7.2. Không dùng cooldown để che lỗi metric

Cooldown quá dài có thể làm hệ thống không tăng capacity đủ nhanh trong đợt traffic tiếp theo. Cooldown quá ngắn có thể tạo oscillation. Nên dùng metric window và policy có cơ sở; tách scale-out nhanh khỏi scale-in thận trọng nếu công cụ hỗ trợ.

### 7.3. Scale-in cần drain

Trước khi loại bỏ capacity:

- Ngừng nhận request mới hoặc message mới vào instance sắp dừng.
- Chờ request in-flight và task đang xử lý hoàn tất trong grace period.
- Đảm bảo queue message chưa ack có thể được giao lại an toàn.
- Thực hiện preStop/graceful shutdown khi nền tảng hỗ trợ.
- Tránh terminate đồng thời quá nhiều replica hoặc tất cả replica của một zone.

Scale-in không an toàn có thể làm request lỗi, message duplicate hoặc transaction bị gián đoạn. Idempotency và graceful termination là phần của kiến trúc scaling.

## 8. Chọn ngưỡng và cửa sổ metric

Ngưỡng scale nên được xây dựng từ capacity test, latency SLO, error budget và quan hệ tải/capacity. Một quy trình:

1. Load test để xác định throughput an toàn của một instance ở latency mục tiêu.
2. Đo thời gian scale-out từ metric signal đến usable capacity ở p50/p95/p99.
3. Xác định headroom cần thiết để chịu tải trong khoảng scaling lag.
4. Chọn threshold dưới vùng saturation, không đợi CPU hoặc latency đạt 100%.
5. Dùng aggregation window đủ để lọc nhiễu nhưng không làm phản ứng quá trễ.
6. Chọn scale-in threshold thấp hơn và stabilization window dài hơn.
7. Kiểm tra nhiều kịch bản: ramp-up, spike, burst ngắn, tải kéo dài và tải giảm đột ngột.

### 8.1. Metric window ảnh hưởng phản ứng

| Cửa sổ | Ưu điểm | Rủi ro |
|---|---|---|
| Rất ngắn | Phản ứng nhanh với spike | Nhiễu, scale quá mức |
| Trung bình | Làm trơn dao động nhỏ | Có thể trễ với burst rất nhanh |
| Dài | Ổn định, ít false trigger | Hệ thống có thể quá tải trước khi quyết định |

Không có thời lượng mặc định đúng cho mọi hệ thống. Cần chọn theo sampling interval, scaling lag, tải và hậu quả nếu phản ứng trễ.

## 9. Tính headroom để sống qua scaling lag

Baseline capacity cần đủ phục vụ tải trong khoảng chờ capacity mới. Nếu tải tăng nhanh hơn khả năng khởi tạo instance, headroom hoặc buffer phải hấp thụ thiếu hụt.

Ví dụ:

- Capacity đang có: 2.000 request/giây.
- Tải nền: 1.200 request/giây.
- Tải có thể tăng tuyến tính thêm 1.000 request/giây trong 60 giây.
- Scaling lag p95: 90 giây.

Trong 90 giây đầu, hệ thống chưa có capacity mới. Nếu tải tăng đều 1.000 request/giây trong 60 giây rồi giữ ở 2.200, capacity 2.000 không đủ ở cuối quá trình ramp-up. Cần tăng baseline hoặc có buffer/admission control, bởi scale-out chỉ sẵn sàng sau thời điểm hệ thống đã thiếu capacity.

Một cách mô hình hóa là so sánh **demand tích lũy** với **capacity tích lũy** trong scaling lag, không chỉ so tải cuối với capacity cuối.

Với queue-based system, backlog có thể hấp thụ chênh lệch tạm thời nếu age vẫn nằm trong SLA. Với synchronous API, queue ở gateway không phải lúc nào cũng tồn tại; có thể cần load shedding, 429/503 có kiểm soát hoặc giới hạn concurrency.

## 10. Không scale ứng dụng vượt quá downstream

Scale-out tăng số caller đồng thời tới database, cache, payment provider, object storage và internal API. Nếu không có giới hạn, autoscaling có thể chuyển bottleneck từ app sang dependency.

### 10.1. Connection amplification

Giả sử mỗi replica mở tối đa 40 DB connections. Khi scale từ 10 lên 50 replica:

\[
Connections_{max} = 50 \times 40 = 2000
\]

Nếu database chỉ hỗ trợ an toàn 600 connection cho workload này, scale-out có thể làm DB cạn connection và kéo toàn bộ ứng dụng xuống.

Giải pháp có thể gồm:

- Connection pool nhỏ và được đo đúng.
- Database proxy/pooler.
- Concurrency cap ở app.
- Queue để giới hạn tốc độ ghi.
- Read/write separation hoặc cache có kiểm soát.
- Tách workload và quota theo tenant/priority.

### 10.2. Scale policy nhiều tầng

| Thành phần | Cơ chế scale | Guardrail |
|---|---|---|
| API replicas | Request rate, concurrency, CPU | Max replicas, connection pool và rate limit |
| Worker | Queue age/backlog | Giới hạn concurrent job và downstream quota |
| Database | Vertical/read replica/partition tùy engine | Connection, IOPS, lock, replication lag |
| Cache | Node/shard/replica | Memory, eviction, hot key và failover |
| External API consumer | Worker concurrency | Provider quota, Retry-After và circuit breaker |

Autoscaling cần được thiết kế như một hệ thống nhiều lớp, không chỉ là một policy cho web tier.

## 11. Scale-to-zero và cold start

Một số serverless hoặc container platform hỗ trợ scale-to-zero để không giữ capacity khi không có tải. Điều này giảm chi phí idle nhưng request đầu tiên phải chịu thời gian khởi động.

Scale-to-zero phù hợp khi:

- Workload không yêu cầu response nhanh ngay request đầu.
- Traffic ít hoặc gián đoạn dài.
- Có queue hoặc asynchronous API để hấp thụ request.
- Cold start nằm trong SLA hoặc có thể thông báo trạng thái processing.

Không phù hợp nếu:

- API có latency SLO nghiêm ngặt cả request đầu.
- Initialization tải model lớn, kết nối dependency chậm.
- Có traffic khó dự đoán nhưng burst rất lớn.
- Consumer cần duy trì session/connection liên tục.

Có thể kết hợp minimum instance, provisioned concurrency hoặc scheduled prewarming. Cần đo cold start riêng với steady-state latency.

## 12. Scheduled và predictive scaling

Nếu tải có thể dự báo từ lịch sử, lịch kinh doanh hoặc sự kiện đã biết, có thể chuẩn bị capacity trước khi metric reactive vượt ngưỡng.

Ví dụ:

- 30 phút trước giờ phát hành vé, tăng baseline.
- Trước batch settlement, chuẩn bị worker và database capacity.
- Trước livestream/campaign, warm cache và scale edge/application.

Predictive scaling cần:

- Lịch hoặc lịch sử đủ tin cậy.
- Phân biệt ngày thường, cuối tuần và sự kiện đặc biệt.
- Giới hạn chi phí và maximum capacity.
- Reactive scaling làm safety net nếu dự báo sai.
- Cơ chế scale-in sau peak với stabilization.

Dự báo không thay thế reactive control. Nếu chiến dịch bất ngờ có traffic gấp đôi dự kiến, hệ thống vẫn cần phản ứng hoặc giới hạn tải.

## 13. Kubernetes HPA, Cluster Autoscaler và node provisioning

Trong Kubernetes, scaling có thể xảy ra ở nhiều lớp:

- **Horizontal Pod Autoscaler (HPA):** điều chỉnh replica count của workload dựa trên metric.
- **Cluster Autoscaler/node autoscaling:** thêm hoặc loại node khi pod không schedule được hoặc capacity dư theo policy.
- **Vertical Pod Autoscaler (VPA):** đề xuất hoặc điều chỉnh CPU/memory request theo cấu hình và mode của công cụ.

HPA tăng số pod không có nghĩa đã có node để chạy chúng. Pod có thể Pending nếu cluster thiếu CPU/memory hoặc ràng buộc placement. Node autoscaler cần thời gian tạo VM, boot, join cluster và sẵn sàng; image pull và readiness còn mất thêm thời gian.

~~~mermaid
flowchart TD
    Metric["CPU / memory / custom metric"] --> HPA["HPA increases desired pods"]
    HPA --> Pending{"Enough schedulable node capacity?"}
    Pending -->|Yes| Schedule["Scheduler places pods"]
    Pending -->|No| NodeAuto["Node autoscaler requests nodes"]
    NodeAuto --> Boot["Provision and join node"]
    Boot --> Schedule
    Schedule --> Pull["Pull image and initialize"]
    Pull --> Ready["Readiness passes"]
    Ready --> Serve["Pods serve traffic"]
~~~

Nên đo riêng thời gian HPA decision, pod scheduling, node provisioning và readiness. Nếu HPA phản ứng nhanh nhưng node provisioning mất 3 phút, cần baseline node capacity, overprovisioning hoặc warm node pool cho workload nhạy latency.

## 14. Function/serverless: concurrency và provisioned capacity

Serverless giảm công quản lý instance nhưng không có nghĩa capacity vô hạn hoặc luôn sẵn sàng tức thời.

Các giới hạn quan trọng:

- Account/region concurrency quota.
- Reserved/provisioned concurrency theo function.
- Burst scaling behavior và ramp rate của nền tảng.
- Execution duration, memory, payload và connection quota.
- Downstream DB/API concurrency.
- Cold start và initialization package/model.

Với API nhạy latency, provisioned concurrency hoặc minimum instances có thể giảm cold start. Với event consumer, có thể scale theo queue age nhưng cần giới hạn batch/concurrency để không làm DB/provider quá tải.

Nếu cần scale nhanh từ zero, kiến trúc bất đồng bộ có thể trả accepted/job ID, enqueue công việc và xử lý khi worker sẵn sàng. Client cần truy vấn trạng thái thay vì giữ request mở trong lúc chờ worker khởi tạo.

## 15. Load shedding và graceful degradation

Khi demand vượt maximum capacity hoặc dependency không thể đáp ứng, hệ thống cần cách bảo vệ core path.

- Rate limit theo tenant/client để phân phối capacity công bằng.
- Reject sớm request không quan trọng hoặc có chi phí cao.
- Ưu tiên transaction quan trọng hơn báo cáo/analytics.
- Cache read-only hoặc phục vụ stale response trong phạm vi nghiệp vụ chấp nhận.
- Queue công việc có thể xử lý sau.
- Tắt feature phụ bằng feature flag khi cần.
- Circuit breaker và timeout để tránh request chờ vô hạn ở dependency.

Load shedding không phải autoscaling thất bại; nó là guardrail bảo vệ hệ thống khi giới hạn vật lý, quota hoặc downstream không cho phép tăng thêm.

## 16. Quan sát scaling lag và hiệu quả policy

Nên đo từ lúc metric vượt threshold tới lúc capacity thực sự được dùng.

| Metric | Ý nghĩa |
|---|---|
| Desired vs current replicas | Autoscaler muốn bao nhiêu, hiện có bao nhiêu |
| Pending pods/tasks | Nhu cầu chưa được placement |
| Provisioning duration | Thời gian cloud cấp compute |
| Startup duration | Thời gian process khởi động |
| Readiness duration | Thời gian tới khi nhận traffic |
| Scale-out lag p50/p95/p99 | Độ trễ mở rộng thực tế |
| CPU/memory/request utilization | Mức sử dụng resource |
| Queue depth và oldest age | Backlog và mức trễ công việc |
| Latency/error/timeout | Trải nghiệm người dùng trong lúc scale |
| Scale-in churn | Tần suất tạo/xóa capacity |
| Downstream saturation | DB connection, cache, API quota |
| Cost per served request/job | Chi phí cho năng lực thực sự phục vụ |

### 16.1. Dashboard nên trả lời được

1. Metric nào kích hoạt scale?
2. Từ trigger đến desired capacity mất bao lâu?
3. Khi nào compute mới được cấp?
4. Khi nào instance/pod bắt đầu ready?
5. Khi nào load balancer đưa traffic vào?
6. Trong khoảng chờ, latency và queue age thay đổi ra sao?
7. Sau scale-out, bottleneck có chuyển sang database hoặc dependency không?
8. Scale-in có gây request reset, queue redelivery hoặc churn không?

### 16.2. Alert theo SLO và saturation

Alert hữu ích có thể gồm:

- Latency/error budget burn tăng trong khi current capacity thấp hơn desired.
- Pending pod/task kéo dài vượt ngưỡng.
- Oldest queue message age gần chạm SLA.
- Scaling lag p95 cao hơn baseline đã xác nhận.
- Maximum replicas/node quota đã chạm nhưng demand vẫn tăng.
- Database connection/CPU/lock saturation khi app scale-out.
- Tài nguyên warm/minimum cao nhưng utilization kéo dài rất thấp.

## 17. Case study: API đặt phòng trong chiến dịch khuyến mại

**Bối cảnh:** API đặt phòng thường nhận 500 request/giây, tăng tới 3.000 request/giây trong vài phút khi chiến dịch bắt đầu. Một replica xử lý an toàn 200 request/giây ở latency mục tiêu. Scale-out từ metric trigger tới readiness mất p95 75 giây. Database chịu được tối đa 800 connection cho ứng dụng. Mục tiêu API p95 dưới 300 ms và không xác nhận đặt trùng.

### 17.1. Phân tích baseline

Ở mức utilization mục tiêu 65%, mỗi replica nên nhận tối đa:

\[
200 \times 0.65 = 130 \text{ request/giây}
\]

Số replica để phục vụ 500 request/giây:

\[
N_{base} = \left\lceil \frac{500}{130} \right\rceil = 4
\]

Đây mới là baseline theo throughput lý thuyết. Cần thêm khả năng chịu lỗi, phân vùng zone và headroom trong 75 giây scale lag. Nếu yêu cầu phục vụ phần lớn peak ngay lập tức, cần pre-scale/scheduled capacity hoặc buffer thay vì chỉ tăng theo CPU sau khi campaign bắt đầu.

### 17.2. Phân tích database connection

Nếu mỗi replica mở tối đa 30 DB connections và có 24 replica, connection tối đa:

\[
24 \times 30 = 720
\]

Con số này gần giới hạn 800, chưa tính maintenance, migration job và các service khác. Cần pool nhỏ hơn, proxy/pooler hoặc quota connection riêng, đồng thời load test trên peak.

### 17.3. Policy đề xuất để thử nghiệm

| Thành phần | Đề xuất ban đầu | Cách xác minh |
|---|---|---|
| API minimum replicas | Duy trì baseline theo tải thường và failure domain | Load test, zone failure |
| Scheduled pre-scale | Tăng trước giờ khuyến mại theo lịch | So sánh chi phí với latency khi reactive-only |
| Reactive scale-out | Dùng request concurrency và utilization, không chỉ CPU | Burst test ngắn và ramp-up |
| Scale-in | Ngưỡng thấp hơn, cửa sổ dài hơn, drain request | Test tải dao động quanh ngưỡng |
| DB pool | Giới hạn tổng connection toàn bộ replica | Kiểm tra 800 connection và headroom |
| Admission control | Giới hạn request/tenant khi chạm maximum | Đảm bảo không xác nhận booking sai |
| Booking write | Conditional update/transaction bảo vệ availability | Concurrent booking test |

Các tham số phải được hiệu chỉnh từ thử nghiệm; bảng là phương án thiết kế ban đầu, không phải cấu hình production sẵn dùng.

### 17.4. Tiêu chí nghiệm thu

- Đo được p50/p95/p99 scaling lag từ metric trigger đến usable capacity.
- Campaign ramp-up không làm latency p95 vượt SLO quá error budget cho phép.
- Database connection không vượt capacity đã cấp.
- Scale-in không cắt request đang chạy hoặc làm mất message.
- Maximum capacity và load shedding có hành vi xác định.
- Không xác nhận hai booking cho cùng inventory trong test cạnh tranh.
- Chi phí baseline/pre-scale được so sánh với chi phí incident và latency degradation.

## 18. Kiểm thử autoscaling

Không nên chỉ kiểm thử bằng cách tăng CPU thủ công. Cần mô phỏng hình dạng tải và đo toàn bộ vòng đời.

| Bài test | Kịch bản | Điều cần xác minh |
|---|---|---|
| Ramp-up | Tăng traffic đều | Threshold và lag có đủ sớm? |
| Spike | Tăng mạnh trong vài giây | Baseline/buffer có chịu được không? |
| Sustained peak | Giữ tải cao lâu | Maximum và dependency có đủ capacity? |
| Oscillation | Tải lên xuống quanh threshold | Stabilization/hysteresis có tránh churn? |
| Sudden drop | Traffic giảm nhanh | Scale-in có drain an toàn? |
| Node/zone failure | Mất một failure domain | Minimum/headroom có chịu được? |
| Cold start | Scale từ zero hoặc minimum thấp | Request đầu có nằm trong SLA? |
| Dependency throttle | DB/API trả 429/timeout | Scale có bị giới hạn và backpressure không? |
| Quota exhaustion | Cloud quota hoặc maximum đạt trần | Alert, degradation và recovery có rõ? |

Trong mỗi test ghi lại traffic, metric signal, desired/current capacity, pod/node state, readiness, latency, errors, queue age, downstream saturation và chi phí.

## 19. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Nghĩ autoscaler làm capacity tăng tức thời | Burst vượt năng lực trước khi instance sẵn sàng | Đo scaling lag và duy trì headroom |
| Minimum đặt quá thấp | Cold start và latency spike | Tính baseline theo tải nền, failure và warm-up |
| Scale-out theo CPU duy nhất | Bỏ lỡ backlog/I/O hoặc làm DB quá tải | Kết hợp metric gắn với bottleneck |
| Scale-in cùng threshold với scale-out | Dao động liên tục | Hysteresis và stabilization window |
| Cooldown quá dài | Không scale kịp đợt tải kế tiếp | Tách policy scale-out nhanh và scale-in thận trọng |
| Chỉ xem instance Running | Capacity chưa ready hoặc chưa nhận traffic | Đo readiness và routing delay |
| HPA tăng pod nhưng không tính node provisioning | Pod Pending, không có năng lực thật | Phối hợp pod/node autoscaling và warm node capacity |
| Scale app vô hạn | DB/partner API bị quá tải | Max capacity, pool limit, backpressure và admission control |
| Không drain trước scale-in | Request/message bị gián đoạn | Graceful shutdown và idempotency |
| Dùng predictive scaling mà không reactive fallback | Forecast sai gây thiếu hoặc dư capacity | Kết hợp scheduled/predictive với reactive guardrail |
| Không kiểm thử peak và failure | Policy chỉ hoạt động trong tải bình thường | Load, spike, oscillation và zone failure test |

## 20. Checklist review scaling policy

### Đo lường và capacity

- [ ] Đã đo scaling lag p50/p95/p99 từ trigger đến usable capacity.
- [ ] Tách metric delay, decision, provisioning, startup, readiness và routing.
- [ ] Baseline/minimum dựa trên throughput an toàn, utilization mục tiêu và failure domain.
- [ ] Maximum được giới hạn theo compute, cloud quota và downstream capacity.
- [ ] Headroom đủ hấp thụ demand trong khoảng scaling lag hoặc có buffer/load shedding.

### Policy

- [ ] Metric scaling phản ánh bottleneck thực tế.
- [ ] Scale-out threshold và aggregation window dựa trên load test/SLO.
- [ ] Scale-in threshold thấp hơn và có stabilization window.
- [ ] Cooldown không làm trì hoãn scale-out cần thiết.
- [ ] Warm pool/pre-scale/provisioned capacity được đánh giá theo cost/latency.
- [ ] Scale-in có drain/graceful shutdown và bảo vệ in-flight work.

### Dependencies và vận hành

- [ ] Database connection, cache, queue và external API có concurrency guardrail.
- [ ] Dashboard thể hiện desired/current/ready capacity, lag, queue age và SLO.
- [ ] Alert khi pending, max capacity, quota, downstream saturation hoặc scale-in churn.
- [ ] Có load test cho spike, ramp-up, sustained, oscillation, cold start và failure.
- [ ] Có runbook khi autoscaler không scale, scale quá mức hoặc đạt maximum.
- [ ] Đo chi phí baseline/warm capacity và cost per served request/job.

## 21. Bài tập thực hành

**Bối cảnh:** một API xử lý đặt phòng có tải nền 300 request/giây, thường tăng lên 2.000 request/giây trong 30 giây đầu của một chiến dịch. Một instance xử lý an toàn 150 request/giây ở mục tiêu p95; thời gian từ metric trigger đến readiness p95 là 60 giây. Mỗi instance có thể mở 20 DB connections; database chịu được tối đa 500 connections cho toàn ứng dụng. Hệ thống hiện scale-out khi CPU trên 75% và scale-in khi CPU dưới 75%.

Hãy thiết kế lại policy:

1. Tính số instance tối thiểu theo tải nền và mức utilization mục tiêu do bạn chọn.
2. Tính capacity cần cho peak và số instance dự phòng nếu mất một instance.
3. Phân tích thiếu hụt trong 60 giây scaling lag khi tải tăng nhanh.
4. Đề xuất baseline, scheduled pre-scale, warm pool hoặc queue buffer.
5. Chọn metric ngoài CPU và ngưỡng scale-out/scale-in khác nhau.
6. Thiết kế stabilization window, cooldown và graceful scale-in.
7. Kiểm tra connection amplification với giới hạn 500 DB connections.
8. Xác định hành vi khi maximum capacity đạt trần.
9. Thiết kế load test cho ramp-up, spike, oscillation và sudden drop.
10. Đặt dashboard/alert và tiêu chí nghiệm thu theo p95 latency, errors, ready capacity và cost.

**Gợi ý tự kiểm tra:** Không chỉ tính instance theo peak mà bỏ qua 60 giây chưa có capacity mới. Không cho phép mỗi instance mở connection vô hạn. Scale-in không được làm mất request. Nếu không thể giữ đủ baseline cho peak, hãy xác định buffer, admission control hoặc degradation mà sản phẩm chấp nhận.

## 22. Ghi nhớ

Scaling lag là khoảng cách giữa lúc hệ thống nhận ra cần thêm năng lực và lúc capacity mới thực sự phục vụ được. Minimum capacity và headroom giúp hệ thống sống qua khoảng chờ đó; warm pool, scheduled/predictive scaling và provisioned capacity có thể rút ngắn thời gian phản ứng nhưng làm tăng chi phí giữ sẵn tài nguyên.

Stabilization window, cooldown và hysteresis giữ autoscaling khỏi dao động; scale-in cần drain request và bảo vệ công việc đang chạy. Policy phải dựa trên metric phản ánh bottleneck, giới hạn downstream, SLO và kiểm thử theo các dạng tải thật. Một hệ thống scale tốt không chỉ tăng replica nhanh, mà còn giữ database, queue và dependency trong giới hạn an toàn, đồng thời có phương án load shedding khi maximum capacity đã đạt.
