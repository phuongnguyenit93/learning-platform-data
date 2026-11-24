# Cấu hình autoscaling và quan sát khi tăng, giảm tải

Autoscaling giúp hệ thống tự điều chỉnh số lượng máy ảo theo nhu cầu thực tế thay vì giữ một quy mô cố định cả ngày. Khi tải tăng, hệ thống bổ sung instance để duy trì khả năng phục vụ; khi tải giảm, hệ thống loại bớt instance để tránh trả chi phí cho capacity không cần thiết. Tuy nhiên, chỉ bật chính sách scale là chưa đủ. Một cấu hình tốt phải chọn đúng tín hiệu, đặt ngưỡng và khoảng đánh giá hợp lý, bảo vệ request đang chạy khi scale-in, kiểm soát giới hạn tài nguyên và quan sát được toàn bộ quá trình từ lúc metric thay đổi đến khi instance thực sự nhận hoặc ngừng nhận traffic.

Trong module **CLOUD_CORE_SERVICES_COMPUTE**, bài học này hướng dẫn cấu hình autoscaling cho nhóm máy ảo và quan sát hành vi scale-out/scale-in trong vận hành. Nội dung bao gồm cách chọn metric, xây dựng policy, cấu hình min/desired/max capacity, warm-up, cooldown, health check, connection draining, dashboard, alert và thực hành tạo tải. Ví dụ sử dụng một dịch vụ web/API có load balancer, application VM group và queue worker; các khái niệm có thể áp dụng cho cơ chế tương đương trên nhiều nền tảng cloud.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích autoscaling và phân biệt scale-out, scale-in, vertical scaling và scheduled/predictive scaling.
- Xác định metric phù hợp với loại workload thay vì chỉ dựa vào CPU.
- Thiết kế min, desired, max capacity và headroom theo tải, SLO, quota và ngân sách.
- Cấu hình target tracking, step scaling, scheduled scaling và chính sách scale-in an toàn.
- Hiểu vai trò của instance warm-up, cooldown, stabilization window và health check.
- Kết hợp load balancer, readiness, lifecycle hook và connection draining để không cắt request đang chạy.
- Xây dựng dashboard theo dõi metric hạ tầng, metric ứng dụng, scaling activity và chi phí.
- Thực hiện bài lab tăng tải, quan sát scale-out, giảm tải và quan sát scale-in.
- Phân tích tình huống autoscaling không hoạt động, scale quá nhanh hoặc làm quá tải dependency.
- Đặt alert, tiêu chí nghiệm thu và checklist production cho autoscaling.

## 1. Autoscaling là gì?

Autoscaling là cơ chế tự động thay đổi capacity của workload theo metric, lịch hoặc dự báo nhu cầu. Với nhóm máy ảo, capacity thường được điều chỉnh bằng cách tăng hoặc giảm số instance trong một VM group/instance group/scale set.

### 1.1. Các hướng thay đổi capacity

- **Scale-out:** tăng số instance để xử lý thêm request, connection hoặc job.
- **Scale-in:** giảm số instance khi nhu cầu giảm, đồng thời bảo đảm instance bị loại không còn xử lý công việc quan trọng.
- **Vertical scaling:** đổi một instance sang cấu hình CPU, memory, network hoặc storage lớn hơn. Thường cần thao tác resize/restart và không thay thế hoàn toàn scale-out.
- **Scheduled scaling:** thay capacity theo lịch đã biết, ví dụ tăng trước giờ mở cửa hoặc batch window.
- **Predictive scaling:** dùng xu hướng lịch sử hoặc dự báo để chuẩn bị capacity trước khi tải đến, nếu nền tảng và workload hỗ trợ.

Autoscaling không đồng nghĩa với việc mọi tài nguyên bên dưới tự mở rộng. Database, IP subnet, quota, NAT, load balancer, disk IOPS và giới hạn kết nối có thể vẫn cố định. Nếu chỉ tăng application VM mà database không chịu được lượng kết nối mới, autoscaling có thể làm sự cố nghiêm trọng hơn.

### 1.2. Vì sao cần autoscaling?

1. **Duy trì trải nghiệm:** bổ sung capacity khi request rate hoặc concurrency tăng.
2. **Tối ưu chi phí:** loại bớt instance khi tải giảm thay vì chạy peak capacity cả ngày.
3. **Hỗ trợ tính sẵn sàng:** thay instance unhealthy và duy trì số lượng tối thiểu ở nhiều failure domain.
4. **Giảm thao tác thủ công:** phản ứng theo metric nhất quán, có thể kiểm toán.
5. **Hỗ trợ workload biến động:** web/API, worker queue, xử lý batch và các hệ thống có chu kỳ tải.

### 1.3. Giới hạn của autoscaling

Autoscaling chỉ có thể phản ứng sau khi tín hiệu xuất hiện, policy được đánh giá và instance mới khởi tạo xong. Nếu boot VM và khởi động ứng dụng mất vài phút, hệ thống có thể vượt SLO trước khi capacity mới sẵn sàng. Vì vậy, cần kết hợp baseline đủ lớn, headroom, dự báo lịch, tối ưu startup và backpressure.

Autoscaling cũng không tự sửa lỗi code, query chậm, lock contention, memory leak hoặc downstream unavailable. Tăng thêm instance trong các trường hợp này có thể làm tăng áp lực lên dependency.

## 2. Kiến trúc tham chiếu cho bài lab

Bài thực hành dùng dịch vụ web/API giả lập:

- Client tạo request HTTPS.
- Load balancer phân phối request tới application VM group.
- Mỗi VM chạy cùng image/template và service version.
- Autoscaling controller theo dõi metric và thay đổi desired capacity.
- Monitoring thu thập metric hạ tầng, metric ứng dụng và sự kiện scaling.
- Một queue worker group là ví dụ bổ sung để thấy metric phù hợp với background job khác với metric web/API.

~~~mermaid
flowchart TB
    CLIENT[Client / Load Generator] --> LB[Load Balancer]
    LB --> APP[Application VM Group]
    APP --> DB[(Database)]
    APP --> CACHE[(Cache)]
    APP --> QUEUE[(Job Queue)]
    QUEUE --> WORKER[Worker VM Group]
    AS[Autoscaling Controller] --> APP
    AS --> WORKER
    METRICS[Metrics / Logs / Traces] --> DASH[Dashboard and Alerts]
    LB -. request and target metrics .-> METRICS
    APP -. host and app metrics .-> METRICS
    WORKER -. queue and job metrics .-> METRICS
    AS -. scaling activities .-> METRICS
~~~

Trong triển khai thực tế, autoscaling controller và monitoring thường là dịch vụ control plane/managed service của cloud. Sơ đồ mô tả luồng logic, không yêu cầu tự xây một controller riêng.

### 2.1. Luồng scale-out

1. Traffic hoặc queue depth tăng.
2. Metric vượt mục tiêu/threshold trong evaluation window.
3. Scaling policy tính mức capacity cần bổ sung.
4. Desired capacity tăng nhưng không vượt max.
5. VM mới được tạo từ image/template.
6. Instance khởi động agent và ứng dụng, sau đó báo readiness.
7. Health check thành công, load balancer đưa instance vào backend pool.
8. Dashboard xác nhận healthy target count tăng và latency/error trở lại mục tiêu.

### 2.2. Luồng scale-in

1. Metric giảm đủ lâu dưới ngưỡng scale-in.
2. Policy xác định số instance có thể loại bỏ nhưng không thấp hơn min.
3. Hệ thống chọn instance phù hợp và bắt đầu lifecycle termination/draining.
4. Load balancer ngừng gửi request mới tới instance đó.
5. Ứng dụng hoàn tất request/job đang chạy, flush log và đóng connection.
6. Instance bị terminate/deallocate theo cấu hình group.
7. Dashboard xác nhận capacity giảm nhưng SLO, healthy target count và queue age vẫn trong giới hạn.

## 3. Trước khi cấu hình: hiểu workload và mục tiêu

Không chọn threshold theo cảm tính. Trước tiên cần hiểu tải, tốc độ thay đổi, startup time, khả năng xử lý của một instance và mục tiêu dịch vụ.

### 3.1. Thu thập baseline

Đo ít nhất một chu kỳ tải đại diện, bao gồm giờ thấp điểm, giờ cao điểm và batch window nếu có:

- Request/second và request mix.
- Concurrent connections và in-flight requests.
- p50, p95, p99 latency.
- Tỷ lệ request thành công, 4xx/5xx và timeout.
- CPU, memory working set, disk IOPS/latency và network throughput.
- Thread/worker pool saturation và connection pool wait.
- Database connections, query latency, lock và replication lag.
- Queue depth, oldest message age, job duration và retry count.
- Thời gian boot VM, bootstrap ứng dụng và thời gian từ create đến healthy target.

Một metric trung bình có thể che giấu spike ngắn hoặc tail latency. Nên quan sát percentile, max/peak và phân bố theo instance/zone, không chỉ nhìn giá trị trung bình toàn group.

### 3.2. Đo throughput an toàn của một instance

Load test một VM với request mix đại diện. Ghi lại throughput tại thời điểm latency và error vẫn đáp ứng mục tiêu. Không dùng throughput tối đa ngay trước khi CPU 100% làm capacity định mức; cần để lại headroom cho burst, GC, background task và biến động request.

Giả sử một VM xử lý an toàn 120 request/giây tại p95 dưới 250 ms. Nếu mục tiêu utilization là 65%, capacity dùng để lập kế hoạch là:

~~~text
Capacity planning mỗi VM = 120 × 0,65
                         = 78 request/giây
~~~

Nếu traffic peak là 780 request/giây:

~~~text
N = ceil(780 / 78)
  = 10 VM
~~~

Đây là ước tính ban đầu. Cần cộng capacity cho zone failure, deployment surge, thời gian autoscaling phản ứng và các ràng buộc downstream.

### 3.3. Xác định SLO và mục tiêu scale

Ví dụ SLO nội bộ cho API:

- Availability theo request thành công: 99,9% trong cửa sổ tháng.
- p95 latency: dưới 250 ms ở tải mục tiêu.
- p99 latency: dưới 600 ms ở tải mục tiêu.
- Error rate do hệ thống: dưới 0,5%.
- Healthy application targets: luôn ít nhất 2 ở hai zone.
- Queue worker: oldest message age dưới 60 giây trong điều kiện bình thường.

Đây là số liệu giả định cho bài lab. Hệ thống thật phải chọn SLO theo yêu cầu nghiệp vụ, không sao chép các ngưỡng minh họa.

## 4. Chọn metric để kích hoạt autoscaling

Metric tốt phản ánh nhu cầu capacity và có quan hệ với bottleneck. Metric cần có chu kỳ thu thập đủ nhanh, ít nhiễu, có thể phân biệt tải thật với sự cố dependency.

### 4.1. CPU utilization

CPU phù hợp với workload CPU-bound như mã hóa, tính toán, nén, xử lý ảnh hoặc API thực thi nhiều logic. Ví dụ target tracking giữ CPU trung bình của group quanh 60%.

Hạn chế:

- Request có thể chờ database/network nên CPU thấp dù latency cao.
- CPU trung bình group có thể che một instance bị nóng.
- CPU có thể tăng do background task không liên quan request.
- Scale-out có thể làm tổng CPU tăng vì số instance tăng, dù CPU/instance giảm.

Vì vậy cần theo dõi CPU theo instance và theo group, đồng thời so với throughput và latency.

### 4.2. Request count per target

Với web/API sau load balancer, số request trên mỗi target thường gần với nhu cầu xử lý hơn CPU. Ví dụ target 300 request/giây trên mỗi healthy target, được xác định qua load test.

Đảm bảo metric được tính trên target đang nhận traffic và phù hợp với loại request. Một request đọc cache nhẹ và một request tạo báo cáo nặng không có chi phí tương đương; nếu mix thay đổi, request count đơn thuần có thể không đủ.

### 4.3. Concurrent connections và in-flight requests

Hữu ích với WebSocket, long polling, streaming, API request kéo dài hoặc workload có nhiều kết nối đồng thời. Kết hợp với latency và connection pool để tránh scale chỉ vì số connection nhàn rỗi.

### 4.4. Memory utilization

Memory phù hợp với JVM, runtime có heap lớn, cache trong process hoặc workload dễ bị OOM. Tuy nhiên, memory không phải lúc nào cũng là metric mặc định trong hypervisor monitoring; có thể cần agent trong guest OS hoặc custom metric.

Phân biệt memory allocated, working set, cache/buffer, swap và memory pressure. Không scale chỉ vì OS dùng RAM cho filesystem cache nếu workload vẫn có thể thu hồi cache an toàn.

### 4.5. Queue depth và oldest message age

Với background worker, queue depth thể hiện số việc đang chờ; oldest message age thể hiện thời gian job cũ nhất phải đợi. Age thường phản ánh tác động tới người dùng tốt hơn depth khi job duration thay đổi.

Ví dụ:

- Scale-out khi oldest message age vượt 30 giây trong 3 lần đánh giá liên tiếp.
- Giữ ít nhất 2 worker.
- Scale-in khi queue gần rỗng và không có job đang chạy trong một khoảng ổn định.

Phải tính throughput mỗi worker, visibility timeout, retry và giới hạn concurrency của downstream.

### 4.6. Metric latency và error rate

Latency p95/p99 là tín hiệu quan trọng để xác nhận SLO đang chịu áp lực. Có thể dùng latency như tín hiệu phụ hoặc custom metric, nhưng phải lọc nguyên nhân:

- Nếu latency tăng do thiếu application capacity, scale-out có thể giúp.
- Nếu latency tăng do database chậm, scale thêm API VM có thể tăng số query và làm DB quá tải.
- Nếu error rate tăng do dependency outage, scale-out không phải cách khắc phục.

Không dùng error rate làm tín hiệu scale-out duy nhất. Kết hợp dependency health, saturation, request rate và circuit breaker.

### 4.7. Bảng chọn metric theo workload

| Workload | Metric chính | Metric xác nhận | Rủi ro cần kiểm soát |
|---|---|---|---|
| Web/API CPU-bound | CPU/instance hoặc request/target | p95/p99, error rate | CPU average che hotspot |
| API I/O-bound | In-flight request hoặc request/target | Dependency latency, connection wait | Scale làm tăng tải database |
| WebSocket/streaming | Concurrent connections | Network throughput, memory | Connection không đồng nghĩa request work |
| JVM/service memory-heavy | Memory pressure/working set | GC pause, OOM, latency | Metric guest cần agent |
| Queue worker | Oldest message age hoặc queue depth | Job duration, retry, worker busy | Worker tăng quá nhanh gây downstream overload |
| Batch/HPC worker | Pending task count, scheduler backlog | Job completion time, CPU/GPU | Job dài cần checkpoint và drain |

## 5. Thiết kế scaling policy

Một scaling policy quy định metric nào được theo dõi, mục tiêu hoặc threshold, số lượng capacity cần thay đổi và khoảng thời gian đánh giá. Policy phải có hành vi scale-out và scale-in được thiết kế riêng; không nên dùng một ngưỡng duy nhất khiến group liên tục tăng rồi giảm khi metric dao động quanh ranh giới.

### 5.1. Target tracking

Target tracking cố gắng giữ một metric gần giá trị mục tiêu. Ví dụ:

- CPU trung bình group target 60%.
- Request count per target target 300 request/giây.
- Queue worker target 20 message đang chờ trên mỗi worker.

Controller quan sát metric và tự tính số instance cần thêm/bớt. Đây thường là lựa chọn khởi đầu đơn giản cho workload có quan hệ tương đối ổn định giữa capacity và metric.

Lưu ý:

- Chọn metric có thể tăng/giảm theo số instance một cách hợp lý.
- Target không nên đặt sát ngưỡng bão hòa.
- Cần thời gian warm-up để metric không bị hiểu sai khi instance mới vừa khởi động.
- Không để nhiều policy độc lập cùng điều khiển một group mà không hiểu cách chúng phối hợp.

### 5.2. Step scaling

Step scaling chia metric thành các khoảng và thay capacity theo mức độ vượt ngưỡng. Ví dụ cho CPU trung bình:

| CPU trung bình trong evaluation window | Hành động minh họa |
|---:|---|
| 60–70% | Thêm 1 VM |
| Trên 70–85% | Thêm 2 VM |
| Trên 85% | Thêm 4 VM và phát cảnh báo capacity |
| 35–45% | Có thể giảm 1 VM nếu các điều kiện scale-in khác đều đạt |
| Dưới 35% | Có thể giảm 2 VM nếu group còn đủ min/headroom |

Các khoảng trên chỉ minh họa cách phân bậc. Cần kiểm thử độ trễ metric, tốc độ boot và tác động của từng lần scale. Nếu metric tăng rất nhanh, step scaling có thể phản ứng nhanh hơn việc tăng từng VM, nhưng cũng dễ tạo surge lớn.

### 5.3. Simple scaling và cooldown

Simple scaling thường thực hiện một hành động cố định khi alarm chuyển trạng thái, sau đó có cooldown để tránh thực hiện liên tục. Mô hình dễ hiểu nhưng kém linh hoạt hơn target tracking/step scaling với workload biến động mạnh.

Cooldown không phải thời gian chờ bắt buộc sau mọi lần scale trên tất cả nền tảng. Mỗi cloud có semantics riêng về cooldown, warm-up, instance initialization và policy evaluation. Đọc đúng tài liệu dịch vụ trước khi map cấu hình giữa các nhà cung cấp.

### 5.4. Scheduled scaling

Nếu tải có chu kỳ dễ dự đoán, tăng capacity trước giờ cao điểm:

- Tăng min/desired capacity trước giờ mở cửa.
- Giữ capacity qua thời gian cao điểm.
- Hạ baseline sau khi tải kết thúc.

Scheduled scaling giúp tránh đợi metric vượt ngưỡng rồi mới boot VM. Không đặt lịch giảm capacity ngay khi hết giờ nếu còn request dài, queue backlog hoặc traffic hậu cao điểm.

### 5.5. Predictive scaling

Predictive scaling sử dụng dữ liệu lịch sử để dự báo nhu cầu và chuẩn bị capacity. Chỉ phù hợp khi pattern đủ lặp lại, metric có chất lượng và workload không thay đổi quá đột ngột. Dự báo không thay thế reactive scaling vì sự kiện bất thường vẫn có thể xảy ra.

### 5.6. Kết hợp policy

Một cấu hình thường dùng:

- Scheduled/predictive scaling chuẩn bị baseline trước giờ cao điểm.
- Target tracking giữ metric quanh mục tiêu trong vận hành bình thường.
- Step scaling xử lý spike lớn hoặc queue backlog khẩn cấp.
- Health-based replacement duy trì số instance khỏe khi VM lỗi.

Tránh để policy xung đột, ví dụ scheduled scaling đặt desired thấp trong khi target tracking đang cần tăng. Ghi rõ policy nào thay đổi min, desired hoặc max và thứ tự ưu tiên khi nhiều tín hiệu đồng thời xuất hiện.

## 6. Min, desired, max và headroom

VM group thường có ba tham số capacity:

- **Min capacity:** số instance thấp nhất được giữ.
- **Desired capacity:** số instance controller đang cố duy trì.
- **Max capacity:** giới hạn trên của group.

### 6.1. Chọn min capacity

Min cần đủ cho tải nền và yêu cầu availability. Với dịch vụ production cần chịu lỗi một VM, min=1 thường không đủ. Nếu cần phục vụ qua hai zone, cần bảo đảm còn đủ instance ở zone còn lại khi một zone gặp sự cố.

Ví dụ group có min 4 VM, phân bố qua hai zone. Không chỉ nhìn tổng số 4; cần kiểm tra placement policy và số instance có thể còn lại khi một zone bị mất.

### 6.2. Chọn max capacity

Max phải dựa trên:

- Peak demand và burst dự kiến.
- Quota vCPU/GPU theo account/subscription/project và region/family.
- Capacity reservation hoặc khả năng cấp SKU ở zone.
- Subnet IP, NIC, load balancer target và API limits.
- Database connection, cache throughput và downstream rate limit.
- Ngân sách và giới hạn chi phí.

Max quá thấp khiến autoscaling không thể phục vụ peak. Max quá cao có thể tạo hóa đơn lớn hoặc làm database/queue consumer quá tải.

### 6.3. Desired capacity ban đầu

Desired ban đầu phải đủ phục vụ baseline trước khi autoscaling phản ứng. Nếu group khởi động với một VM trong khi tải nền đã yêu cầu bốn VM, hệ thống sẽ liên tục vi phạm SLO trong lúc scale-out.

### 6.4. Headroom và N-1 capacity

Headroom là phần capacity còn trống để xử lý burst, lỗi instance, thời gian boot và deployment. Với kiến trúc đa zone, kiểm tra N-1 capacity: sau khi mất một zone hoặc một phần instance, số VM còn lại có còn đáp ứng tải tối thiểu không.

Ví dụ 12 VM chia đều hai zone, mỗi VM xử lý an toàn 80 request/giây ở utilization mục tiêu. Nếu mất một zone, còn 6 VM:

~~~text
Capacity sau lỗi zone = 6 × 80 = 480 request/giây
~~~

Nếu tải quan trọng cần 700 request/giây thì baseline hiện tại không đáp ứng N-1. Cần tăng baseline, tối ưu throughput, phân phối qua nhiều zone hơn hoặc định nghĩa degraded mode. Autoscaling sau sự cố không bảo đảm đủ capacity nếu zone khác không còn host hoặc quota.

## 7. Warm-up, cooldown và chống dao động

Một VM mới không lập tức trở thành capacity hữu ích. Nó cần được tạo, boot, tải cấu hình, khởi động ứng dụng, warm cache và pass readiness.

### 7.1. Instance warm-up

Warm-up là khoảng thời gian sau khi instance được tạo mà metric chưa nên được xem như metric steady-state của group hoặc instance chưa được dùng làm cơ sở quyết định scale tiếp theo, tùy semantics của autoscaler.

Trong warm-up:

- Không tính instance mới như backend khỏe trước khi readiness pass.
- Không đánh giá CPU thấp trong lúc app chưa nhận traffic như dấu hiệu group dư capacity.
- Tránh kích hoạt thêm nhiều batch chỉ vì instance mới chưa kịp nhận request.
- Theo dõi thời gian create-to-running, running-to-ready và ready-to-first-request riêng.

Warm-up nên được đo từ thực nghiệm. Không chọn một giá trị lớn tùy tiện vì nó làm controller phản ứng chậm; cũng không đặt quá ngắn khiến controller scale liên tục.

### 7.2. Cooldown và stabilization window

Cooldown/stabilization giúp controller tránh phản ứng với dao động ngắn. Ví dụ, chỉ giảm capacity khi metric ở dưới ngưỡng trong 10 phút liên tiếp, thay vì giảm ngay khi CPU giảm một phút.

Scale-out và scale-in có thể cần thời gian khác nhau:

- Scale-out ưu tiên phản ứng đủ nhanh để bảo vệ SLO.
- Scale-in thận trọng hơn để tránh loại capacity ngay trước một đợt tải tăng.

### 7.3. Hysteresis

Hysteresis dùng ngưỡng scale-out và scale-in khác nhau. Ví dụ:

- Scale-out khi CPU vượt 65% trong 3 phút.
- Chỉ xem xét scale-in khi CPU dưới 35% trong 10 phút.

Khoảng cách giữa hai ngưỡng giảm hiện tượng group liên tục tăng/giảm khi metric dao động quanh một điểm. Hãy chọn threshold theo baseline và tải đã đo, không coi 65/35 là chuẩn chung.

### 7.4. Giới hạn tốc độ thay đổi

Đặt giới hạn số VM được thêm/bớt trong một khoảng thời gian nếu nền tảng hỗ trợ. Điều này bảo vệ downstream khỏi một đợt tăng connection đột ngột và giúp operator có thời gian quan sát. Tuy nhiên, giới hạn quá chặt có thể khiến scale-out không theo kịp burst.

## 8. Health check và scale-in an toàn

Autoscaling phải phối hợp với load balancer và vòng đời ứng dụng. Instance chỉ nên nhận traffic khi sẵn sàng, và chỉ nên bị xóa sau khi đã ngừng nhận công việc mới.

### 8.1. Phân biệt liveness, readiness và health của target

- **Liveness:** process có còn hoạt động hay đã rơi vào trạng thái không thể tự phục hồi.
- **Readiness:** ứng dụng đã hoàn tất khởi tạo và có thể phục vụ loại request được phân công.
- **Load balancer target health:** kiểm tra của load balancer quyết định có gửi traffic tới instance không.
- **Auto-repair health:** tín hiệu dùng để thay instance unhealthy trong VM group.

Không nhất thiết mọi health check phải giống nhau. Liveness quá nhạy có thể restart liên tục; readiness phụ thuộc tất cả dependency có thể làm toàn group bị loại khi database gặp sự cố chung.

### 8.2. Graceful shutdown

Khi nhận termination signal, ứng dụng nên:

1. Đánh dấu readiness false hoặc yêu cầu load balancer ngừng gửi request mới.
2. Ngừng nhận job mới từ queue.
3. Hoàn tất request đang chạy trong giới hạn thời gian.
4. Commit/checkpoint hoặc trả job lease về queue.
5. Flush log/metric và đóng connection.
6. Thoát process trước termination deadline.

Nếu request có thời gian xử lý dài hơn termination grace period, cần checkpoint, retry hoặc chuyển công việc sang queue; không thể chỉ tăng timeout vô hạn.

### 8.3. Connection draining

Load balancer cần có thời gian drain đủ dài cho request và connection đang mở. Đặt drain timeout theo phân bố request duration và loại giao thức. WebSocket/streaming có thể cần cơ chế reconnect riêng.

### 8.4. Scale-in protection và lifecycle hook

Với workload stateful hoặc job dài, có thể dùng scale-in protection, lifecycle hook hoặc cơ chế tương đương để trì hoãn terminate khi instance còn công việc. Cần có deadline và cơ chế timeout để không giữ instance mãi mãi.

Không bật protection cho mọi instance vô thời hạn; điều đó làm group không thể scale-in và chi phí tăng không kiểm soát.

### 8.5. Chọn instance bị loại

Nếu có thể, ưu tiên loại instance ít session/connection/job hơn hoặc instance phù hợp với placement/age policy. Tuy nhiên, thuật toán chọn instance phụ thuộc nền tảng. Ứng dụng vẫn phải chịu được việc bất kỳ instance nào bị thay thế.

## 9. Cấu hình autoscaling đa tầng

Một hệ thống có thể có nhiều VM group độc lập. Mỗi group phải scale theo tín hiệu phù hợp với trách nhiệm của nó.

### 9.1. Web/API group

Metric gợi ý:

- Request count per target.
- Concurrent connections.
- CPU/memory theo instance.
- p95/p99 latency và error rate làm metric xác nhận.

Đặt min để duy trì HA, max theo quota và giới hạn database connection. Cần tính tổng connection pool tối đa:

~~~text
Max database connections từ app
= Max application VM × connection pool mỗi VM
~~~

Nếu max group là 30 VM và mỗi VM mở pool tối đa 40 connection, database có thể phải chịu tới 1.200 connection chỉ từ application tier. Giới hạn pool hoặc dùng proxy/pooling phù hợp để không biến autoscaling thành connection storm.

### 9.2. Worker group

Worker nên scale theo queue backlog, oldest message age hoặc số job đang xử lý. Không dùng CPU làm tín hiệu duy nhất nếu job có thời gian chờ I/O dài.

Đặt concurrency mỗi worker, max worker và rate limit downstream. Khi queue trống, chỉ scale-in sau khi không còn job đang chạy hoặc lease có thể được trả an toàn.

### 9.3. Database và cache

Database thường không nên được mở rộng theo cùng policy với application VM. Tăng application capacity có thể làm số connection/query tăng nhanh hơn khả năng database. Dùng connection limit, pool, backpressure, cache và read replica theo chiến lược riêng.

Cache có thể cần tăng memory hoặc shard khi working set vượt capacity. Cache hit ratio giảm có thể là dấu hiệu capacity/TTL/key distribution thay đổi, không nhất thiết chỉ cần thêm API VM.

### 9.4. Thứ tự scale và backpressure

Nếu application và worker cùng tăng, kiểm tra downstream:

- Database có đủ connection và IOPS?
- Queue có giới hạn publish/consume?
- External API có rate limit?
- Cache có thể chịu connection churn?
- Network/NAT có đủ connection/throughput?

Khi downstream bão hòa, giảm concurrency hoặc bật backpressure có thể an toàn hơn scale-out thêm. Autoscaling nên phối hợp với rate limiting, circuit breaker và queue buffering.

## 10. Quan sát autoscaling

Quan sát autoscaling cần trả lời bốn câu hỏi:

1. **Vì sao scale?** Metric nào kích hoạt policy và giá trị đã thay đổi ra sao?
2. **Controller đã làm gì?** Desired capacity, scaling activity và lỗi API có gì thay đổi?
3. **Capacity mới có hữu ích chưa?** Bao nhiêu instance đã healthy và nhận traffic?
4. **Kết quả dịch vụ thế nào?** Latency, error, queue age, availability và chi phí có cải thiện không?

Chỉ nhìn số lượng VM tăng không chứng minh autoscaling thành công. Cần nối sự kiện scaling với metric ứng dụng và trải nghiệm người dùng.

### 10.1. Metric hạ tầng

- Current, desired, min và max instance count.
- Instance state theo từng zone: pending, running, healthy, draining, terminating, unhealthy.
- CPU, memory pressure, disk latency/IOPS và network throughput theo instance.
- Thời gian create-to-running, running-to-ready và ready-to-first-request.
- Autoscaling activity: policy, reason, old/new desired capacity, activity result.
- Quota usage, allocation failure, subnet IP và API throttling.

### 10.2. Metric load balancer

- Request count và request/target.
- Healthy/unhealthy target count.
- Active/new connections.
- Backend response time hoặc target latency.
- 4xx/5xx, timeout và rejected connection.
- Connection draining duration và deregistration event nếu nền tảng cung cấp.

### 10.3. Metric ứng dụng và dependency

- Request rate, success/error rate và p50/p95/p99 latency.
- In-flight request, thread pool, worker pool và queue wait.
- Database connection pool wait, active connection, query latency và lock.
- Cache hit ratio, eviction và memory pressure.
- Queue depth, oldest message age, job duration, retry và dead-letter count.
- External dependency latency, timeout và rate-limit response.

### 10.4. Log và trace

Log nên có timestamp, service, environment, instance ID, zone, deployment version, trace/correlation ID và event type. Ghi lại lifecycle event như startup complete, readiness pass/fail, drain start/end và shutdown reason.

Distributed trace giúp xác định latency tăng ở edge, web, application, database hay external dependency. Khi instance được scale thêm, trace cho biết request có thực sự được phân phối đều hay một target vẫn nhận phần lớn traffic.

Không ghi password, access token, session cookie hoặc payload nhạy cảm vào log. Dùng log tập trung vì log local có thể biến mất khi instance bị terminate.

### 10.5. Dashboard tối thiểu

Một dashboard vận hành nên có các hàng:

| Hàng | Biểu đồ | Câu hỏi |
|---|---|---|
| User impact | Request rate, success/error, p95/p99 latency | Người dùng có đang bị ảnh hưởng? |
| Capacity | Desired/current/min/max và healthy targets | Có đủ capacity thật sự? |
| Scaling | Scaling activity, trigger metric, cooldown/warm-up | Vì sao group thay đổi? |
| Host | CPU, memory, disk, network theo instance | Bottleneck ở tài nguyên nào? |
| Dependency | DB connections/latency, cache hit, queue age | Scale có làm downstream quá tải? |
| Cost | Instance-hours, VM type, scale-out/in event | Capacity có được sử dụng hiệu quả? |

Đặt cùng trục thời gian cho metric kích hoạt, scaling activity, healthy target count và latency để có thể so sánh trước/sau mỗi lần scale.

### 10.6. Alert có ý nghĩa hành động

| Alert | Điều kiện minh họa | Hành động ban đầu |
|---|---|---|
| Thiếu healthy target | Healthy count thấp hơn min trong vài phút | Kiểm tra health check, startup, quota và allocation |
| Group chạm max | Desired capacity bằng max trong khi metric còn vượt target | Kiểm tra max/quota/capacity và downstream |
| Scale-out thất bại | Activity báo insufficient capacity/quota/API error | Xác định scope lỗi, zone/SKU và retry policy |
| Scale thrashing | Scale-out và scale-in lặp lại trong thời gian ngắn | Kiểm tra hysteresis, evaluation window và metric noise |
| Latency vượt SLO | p95/p99 vượt ngưỡng liên tục | Xác định bottleneck; không mặc định tăng VM |
| Queue backlog tăng | Oldest message age vượt SLO | Kiểm tra worker capacity và downstream rate limit |
| Connection pool bão hòa | Pool wait/timeout tăng | Kiểm tra DB capacity, pool size và concurrency |
| Instance drain quá lâu | Drain duration vượt ngưỡng | Kiểm tra request/job dài, shutdown hook và grace period |

Alert nên có severity, owner, dashboard, runbook và bước kiểm tra đầu tiên. Tránh alert chỉ vì CPU tăng trong vài giây nếu không có tác động dịch vụ.

## 11. Ví dụ cấu hình policy ở mức khái niệm

Ví dụ YAML sau mô tả ý định cấu hình cho một application VM group. Đây là cấu trúc minh họa độc lập với nhà cung cấp, không phải manifest có thể áp dụng trực tiếp bằng CLI/API của AWS, Azure hay Google Cloud.

~~~yaml
service:
  name: orders-api
  tier: application

vmGroup:
  zones:
    - zone-a
    - zone-b
  minCapacity: 4
  desiredCapacity: 4
  maxCapacity: 20
  instanceTemplate: orders-api-image-v12
  loadBalancerTarget: orders-api-targets

scaling:
  metric:
    name: requests_per_healthy_target
    target: 300
    unit: requests_per_second
  evaluation:
    period: 60s
    scaleOutDatapoints: 2
    scaleInDatapoints: 10
  behavior:
    scaleOut:
      warmup: 180s
      maxStep: 4
    scaleIn:
      stabilizationWindow: 600s
      maxStep: 1
      requireHealthyCapacity: true
  scheduled:
    - time: "08:45"
      desiredCapacity: 8
    - time: "20:30"
      desiredCapacity: 4

health:
  startupProbe: /startup
  readinessProbe: /ready
  loadBalancerDrain: 90s
  terminationGracePeriod: 120s

observability:
  dimensions:
    - service
    - environment
    - instance_id
    - zone
    - deployment_version
  alerts:
    - no_healthy_targets
    - group_at_max_capacity
    - scaling_activity_failed
    - p95_latency_breaches_slo
~~~

Các giá trị như 300 request/giây, 180 giây warm-up, 600 giây stabilization và 90 giây drain chỉ là ví dụ. Thay bằng kết quả benchmark, request duration, startup time, SLO và semantics thực tế của nền tảng.

### 11.1. Những điểm phải map khi dùng cloud provider

| Khái niệm | AWS | Azure | Google Cloud |
|---|---|---|---|
| Nhóm VM | EC2 Auto Scaling group | Virtual Machine Scale Set | Managed Instance Group |
| Template | Launch template | VM/scale set model | Instance template |
| Scale metric | CloudWatch metric/alarm hoặc metric tích hợp | Azure Monitor metric/alert | Cloud Monitoring metric |
| Scale policy | Target tracking, step, scheduled | Autoscale rules, schedule | Autoscaler policy, schedule |
| Load balancer health | Target group health check | Load Balancer/Backend health probe | Backend service health check |
| Activity history | Scaling activities/CloudTrail/CloudWatch | Activity Log/Autoscale history | Instance group operations/Audit Logs |

Tên chức năng, giới hạn và cách cấu hình có thể thay đổi theo loại group, region và dịch vụ. Dùng tài liệu chính thức của provider khi chuyển cấu hình khái niệm thành resource thực.

## 12. Bài lab: cấu hình và quan sát scale-out/scale-in

### 12.1. Mục tiêu lab

Tạo application VM group sau load balancer, bật autoscaling theo request count hoặc CPU, tạo tải có kiểm soát, quan sát capacity tăng, dừng tải và quan sát capacity giảm. Không dùng production account hoặc workload có dữ liệu quan trọng.

### 12.2. Điều kiện chuẩn bị

- Có quyền tạo VM, VM group, load balancer, monitoring metric và scaling policy trong sandbox.
- Có image/template đã cài ứng dụng web/API mẫu và monitoring agent nếu cần custom metric.
- Có subnet ở ít nhất hai zone và đủ IP cho max capacity.
- Có endpoint health/readiness và access log.
- Có load generator chạy độc lập với VM group đang thử.
- Có budget/quota phù hợp và giới hạn max instance rõ ràng.

### 12.3. Cấu hình ban đầu

Ví dụ:

| Tham số | Giá trị lab |
|---|---:|
| Min capacity | 2 VM |
| Desired capacity | 2 VM |
| Max capacity | 8 VM |
| Zone | 2 zone |
| Scale-out target | 200 request/giây/healthy target |
| Evaluation period | 60 giây |
| Scale-in stabilization | 10 phút |
| Warm-up ước tính | 3 phút |
| Drain timeout | 90 giây |

Ngưỡng cần điều chỉnh nếu VM nhỏ/lớn hơn, ứng dụng có startup khác hoặc request mix nặng hơn. Đảm bảo max 8 VM không vượt quota và database connection budget.

### 12.4. Các bước thực hiện

1. **Tạo VM template:** dùng image có phiên bản ứng dụng cố định, agent metric/log và startup script idempotent.
2. **Tạo load balancer:** cấu hình listener, backend group, health check và timeout.
3. **Tạo VM group:** đặt min=2, desired=2, max=8; phân bố instance trên hai zone.
4. **Đăng ký backend:** chỉ đưa instance vào pool sau khi readiness/health check thành công.
5. **Tạo scaling policy:** chọn request count per healthy target làm metric chính; CPU làm metric xác nhận.
6. **Cấu hình scale-in:** đặt stabilization window, drain timeout và graceful shutdown.
7. **Tạo dashboard:** hiển thị request rate, request/target, CPU, latency, error, desired/current capacity, healthy target count và scaling activity.
8. **Kiểm tra baseline:** gửi tải thấp trong vài phút, xác nhận group ổn định ở 2 VM và không có alert.
9. **Tăng tải theo bậc:** tăng concurrency hoặc request rate mỗi 2–3 phút, không nhảy ngay lên tải cực đại.
10. **Quan sát scale-out:** ghi thời điểm metric vượt target, policy được kích hoạt, instance bắt đầu tạo, readiness pass và request đầu tiên được phục vụ.
11. **Giữ steady-state:** duy trì tải ở mức mới đủ lâu để metric và latency ổn định.
12. **Giảm tải từ từ:** giảm request rate về baseline, sau đó dừng load generator.
13. **Quan sát scale-in:** theo dõi stabilization, drain, termination và healthy capacity sau mỗi lần giảm.
14. **Kiểm tra cuối:** xác nhận group trở về baseline, SLO đạt, không mất request/job và không còn instance hoặc disk lab mồ côi.

### 12.5. Bảng ghi nhận kết quả

| Mốc | Tải gửi | Desired VM | Healthy VM | p95 latency | CPU/VM | Ghi chú |
|---|---:|---:|---:|---:|---:|---|
| Baseline | 100 req/s | 2 | 2 | Ghi số đo | Ghi số đo | Trạng thái ban đầu |
| Ramp 1 | 250 req/s | Ghi số đo | Ghi số đo | Ghi số đo | Ghi số đo | Metric bắt đầu tăng |
| Ramp 2 | 450 req/s | Ghi số đo | Ghi số đo | Ghi số đo | Ghi số đo | Kiểm tra scale-out |
| Peak | 700 req/s | Ghi số đo | Ghi số đo | Ghi số đo | Ghi số đo | Giữ tải ổn định |
| Ramp down | 250 req/s | Ghi số đo | Ghi số đo | Ghi số đo | Ghi số đo | Quan sát stabilization |
| Baseline | 100 req/s | Ghi số đo | Ghi số đo | Ghi số đo | Ghi số đo | Xác nhận scale-in |

Không điền số đo giả định vào báo cáo thực nghiệm. Ghi timestamp và ảnh chụp/dashboard link của từng mốc để có thể đối chiếu scaling activity.

### 12.6. Tiêu chí nghiệm thu lab

- Group không xuống dưới min và không vượt max.
- Instance mới chỉ nhận traffic sau khi healthy/readiness pass.
- Scale-out diễn ra khi metric vượt mục tiêu theo policy.
- Sau scale-out, request/target hoặc CPU giảm về vùng ổn định.
- p95/p99 và error rate không vượt SLO kéo dài.
- Khi tải giảm, group không scale-in ngay lập tức hoặc dao động liên tục.
- Instance bị loại được drain; không có request/job bị cắt hoặc xử lý trùng.
- Dashboard giải thích được vì sao scale và kết quả sau scale.
- Scaling activity không có lỗi quota, capacity, subnet IP hoặc API throttling.

## 13. Thực hành đọc dashboard và timeline

Một cách tốt để phân tích là lập timeline thống nhất:

| Thời điểm | Sự kiện | Metric cần xem | Câu hỏi |
|---|---|---|---|
| T0 | Bắt đầu tăng tải | Request rate, CPU, latency | Tải tăng từ đâu? |
| T1 | Vượt target | Metric kích hoạt, evaluation window | Policy đã đủ điều kiện chưa? |
| T2 | Desired tăng | Scaling activity, quota, API result | Controller yêu cầu thêm bao nhiêu VM? |
| T3 | VM được tạo | Pending/running, boot duration | Cấp phát có chậm hoặc lỗi không? |
| T4 | Readiness pass | Healthy target count | VM đã sẵn sàng thật chưa? |
| T5 | Latency phục hồi | p95/p99, error, request/target | Capacity mới có giải quyết bottleneck? |
| T6 | Tải giảm | Metric, stabilization timer | Scale-in có đủ điều kiện chưa? |
| T7 | Drain/terminate | Active connections, job in-flight | Có mất request hoặc job không? |
| T8 | Về baseline | Current/desired, SLO, cost | Group có ổn định và tiết kiệm hơn? |

### 13.1. Tính scale-out delay

Đo thời gian từ khi metric vượt threshold đến khi instance mới nhận request:

~~~text
Scale-out delay
= policy evaluation delay
  + provisioning time
  + guest boot and bootstrap time
  + application startup time
  + readiness and load balancer registration time
~~~

Ví dụ đo được 60 giây evaluation, 45 giây provisioning, 50 giây boot/bootstrap, 35 giây application startup và 20 giây readiness/registration:

~~~text
Scale-out delay = 60 + 45 + 50 + 35 + 20
                = 210 giây
                = 3 phút 30 giây
~~~

Trong khoảng này, instance cũ phải gánh tải tăng. Nếu không đủ headroom, hãy tăng baseline, giảm startup time, dùng warm pool hoặc scheduled/predictive scaling.

### 13.2. Tính thời gian scale-in

Scale-in có thể chậm hơn scale-out vì cần stabilization, chọn instance, drain request và terminate:

~~~text
Scale-in completion
= stabilization window
  + target deregistration/drain
  + graceful shutdown
  + provider termination time
~~~

Đây là thời gian quan sát để lập kế hoạch, không phải SLA của provider. Ghi rõ phần nào là policy wait và phần nào là lifecycle thực tế.

### 13.3. So sánh trước và sau scale

Không chỉ so sánh CPU trước/sau. Nên đối chiếu:

- Throughput tổng và throughput/instance.
- p95/p99 latency.
- Error/timeout rate.
- Request/target và active connections.
- DB connection/query latency.
- Queue age/job completion.
- Instance-hours và cost per successful request.

Nếu số VM tăng nhưng latency không cải thiện, cần tìm bottleneck khác thay vì tiếp tục tăng max capacity.

## 14. Troubleshooting: khi autoscaling không hoạt động như mong đợi

### 14.1. Metric vượt ngưỡng nhưng desired capacity không tăng

Kiểm tra theo thứ tự:

1. Metric có được thu thập đúng namespace, dimension, unit và period không?
2. Alarm/evaluation window đã đủ datapoint chưa?
3. Scaling policy có đang disable, suspended hoặc bị schedule khác ghi đè không?
4. Group đã ở max capacity chưa?
5. Có quota, policy, IAM permission hoặc API rate limit chặn hành động không?
6. Metric có missing data hoặc statistic không phù hợp không?
7. Scaling activity history có reason/error cụ thể không?

Không tăng max ngay khi chưa biết lý do. Nếu lỗi là thiếu quyền hoặc metric sai, tăng max không giải quyết được.

### 14.2. Desired tăng nhưng không có instance mới

Nguyên nhân thường gặp:

- Quota vCPU/GPU hoặc family quota đã hết.
- Zone/SKU không còn capacity.
- Subnet hết địa chỉ IP.
- Template tham chiếu image đã xóa hoặc sai version.
- IAM/instance profile không đủ quyền.
- Disk, NIC, placement group hoặc accelerator không tương thích.
- Provider API bị throttling.

Đối chiếu scaling activity, compute provisioning event, audit log và quota usage. Nếu capacity zone không có, cân nhắc nhiều instance type tương đương hoặc nhiều zone nếu workload cho phép.

### 14.3. Instance chạy nhưng không healthy

Kiểm tra:

- Startup script có lỗi hoặc chạy quá lâu?
- Secret/config/identity có truy cập được?
- Ứng dụng có bind đúng interface/port?
- Security group/firewall có cho phép health check?
- Health endpoint có timeout hoặc phụ thuộc database/cache không?
- Runtime có OOM, crash loop hoặc lỗi certificate?
- Clock/DNS/network có đúng?

Đừng chỉ tăng health check timeout để che một startup lỗi. Dùng log khởi động và readiness reason để xác định nguyên nhân.

### 14.4. Group scale-out liên tục nhưng latency không giảm

Khả năng cao bottleneck nằm ngoài VM:

- Database query/lock hoặc connection pool bão hòa.
- Cache miss tăng đột biến.
- External API bị rate limit.
- Network/NAT/egress bị nghẽn.
- Một shard/partition nhận phần lớn traffic.
- Request bị serialize trên shared lock hoặc single-thread worker.

Hành động: giới hạn concurrency, bật backpressure, tối ưu query/cache, phân phối tải hoặc tăng capacity dependency theo policy riêng. Không tiếp tục scale application group mù quáng.

### 14.5. Scale-in không xảy ra

Kiểm tra:

- Metric có thấp hơn threshold đủ lâu?
- Stabilization/cooldown còn hiệu lực?
- Min capacity đã đạt chưa?
- Có instance scale-in protection hoặc lifecycle hook chưa hoàn tất?
- Có scheduled policy giữ desired cao?
- Group có placement hoặc zone distribution constraint?
- Instance có session/job dài hoặc không pass drain?

Nếu instance bị bảo vệ vô thời hạn, cần runbook để giải phóng protection an toàn thay vì force terminate.

### 14.6. Scale-in rồi scale-out lại ngay

Đây là dấu hiệu oscillation/thrashing. Nguyên nhân có thể là:

- Threshold scale-in quá gần threshold scale-out.
- Evaluation window quá ngắn.
- Metric noisy hoặc bị ảnh hưởng bởi warm-up.
- Traffic có burst ngắn lặp lại.
- Scale-in làm tải dồn lên instance còn lại khiến metric vượt target.

Khắc phục bằng hysteresis, stabilization dài hơn cho scale-in, giảm step size, đặt minimum capacity phù hợp và kiểm tra metric theo instance.

## 15. Lỗi thiết kế thường gặp

| Lỗi | Tác động | Cách khắc phục |
|---|---|---|
| Chỉ scale theo CPU | Bỏ lỡ bottleneck I/O hoặc queue | Chọn metric theo workload và đo dependency |
| Dùng CPU trung bình group | Một instance có thể quá tải trong khi average thấp | Theo dõi per-instance và request/target |
| Scale-out quá muộn | SLO bị vi phạm trước khi VM mới sẵn sàng | Giữ headroom, warm pool hoặc scheduled scaling |
| Scale-in quá nhanh | Cắt request/job, tạo thrashing | Stabilization, drain và graceful shutdown |
| Min capacity quá thấp | Không đủ HA hoặc baseline | Tính baseline và N-1 capacity |
| Max capacity không có giới hạn | Hóa đơn lớn, DB connection storm | Đặt max theo quota, budget và downstream |
| Không kiểm tra quota/zone | Desired tăng nhưng provisioning thất bại | Theo dõi quota, SKU availability và subnet IP |
| Readiness check quá nông | Instance nhận traffic trước khi sẵn sàng | Kiểm tra trạng thái app thực tế |
| Readiness phụ thuộc mọi dependency | Một lỗi chung loại toàn bộ target | Chỉ kiểm tra dependency bắt buộc cho request |
| Không có dashboard scaling activity | Không giải thích được vì sao scale | Nối metric, policy event và capacity |
| Không đo startup time | Warm-up/cooldown đặt sai | Đo từng giai đoạn create-to-ready |
| Scale worker chỉ theo queue depth | Có thể tăng worker dù job bị chặn downstream | Kết hợp oldest age, busy worker và dependency health |
| Scale thêm API khi DB chậm | Làm database quá tải hơn | Pool, rate limit, cache và backpressure |
| Không phân biệt 4xx và 5xx | Scale do lỗi client không cần capacity | Phân loại error theo nguồn và tác động |
| Gộp metric nhiều environment | Test load kích hoạt production policy | Tách dimension và alarm theo environment |

## 16. Bảo mật và quản trị autoscaling

Autoscaling tạo và xóa tài nguyên tự động nên quyền và audit cần được thiết kế ngay từ đầu.

### 16.1. Least privilege

- Scaling controller chỉ được quyền thay đổi đúng VM group và resource liên quan.
- Instance role chỉ có quyền đọc config/secret và gửi metric/log cần thiết.
- Load generator không dùng credential quản trị cloud.
- Operator có quyền xem scaling activity; quyền thay đổi max capacity nên được kiểm soát.
- Tách quyền deployment, runtime và audit.

### 16.2. Image và bootstrap

Image cần được scan, harden và version hóa. Startup script phải idempotent, không ghi secret vào log hoặc user-data dễ truy cập. Secret lấy từ secret manager bằng short-lived identity.

Không tải package không kiểm soát từ Internet mỗi lần VM boot nếu điều đó làm startup không ổn định. Ưu tiên image/artifact đã kiểm thử và repository được tin cậy.

### 16.3. Audit và traceability

Ghi lại:

- Ai thay đổi min/max hoặc scaling policy.
- Policy version nào được áp dụng.
- Metric/alarm nào kích hoạt.
- Desired capacity trước/sau.
- Instance ID, zone, image version và thời điểm tạo/xóa.
- Activity failure, permission denied và quota error.

Kết hợp audit log của cloud với deployment log và application event để tái dựng sự kiện.

## 17. Chi phí và hiệu quả autoscaling

Autoscaling tối ưu chi phí khi capacity đi theo nhu cầu nhưng không hy sinh SLO. Không nên đánh giá chỉ bằng số VM đã scale-in.

### 17.1. Các thành phần chi phí

- VM instance-hours và loại instance.
- Boot/warm pool capacity nhàn rỗi.
- Disk, snapshot và image storage.
- Load balancer, NAT, public IP và network egress.
- Cross-zone data transfer.
- Monitoring metric, log ingestion, retention và trace.
- Database/cache/queue capacity tăng theo application scale.
- License và support plan.

### 17.2. Chỉ số hiệu quả

- Cost per successful request.
- Cost per completed job.
- Average/peak instance count.
- Idle capacity ratio.
- Scale-out frequency và scale-in frequency.
- Thời gian ở max capacity.
- Tỷ lệ request/job thất bại trong quá trình scaling.

Nếu scale-in tiết kiệm 20% VM-hours nhưng làm tăng timeout hoặc retry gấp đôi, tổng chi phí vận hành có thể cao hơn. Cần so sánh chi phí với chất lượng dịch vụ và chi phí downstream.

### 17.3. Chọn min/max theo budget

Đặt budget alert và giới hạn max capacity. Có thể dùng scheduled scaling cho môi trường không production, nhưng chỉ tắt VM khi dữ liệu và job có thể được phục hồi. Không scale-in hoặc stop database chỉ vì hết giờ nếu ứng dụng vẫn có background work.

### 17.4. Spot/interruptible capacity

Worker stateless, có checkpoint và retry có thể dùng Spot/interruptible VM để giảm chi phí. Không dùng capacity interruptible làm baseline duy nhất cho workload cần availability cao. Cần capacity thay thế, queue retry và theo dõi interruption event.

## 18. Mở rộng bài lab: các tình huống kiểm thử

Chỉ thực hiện trong sandbox được phép. Không cố ý gây quá tải production hoặc dependency dùng chung.

### 18.1. Kiểm thử burst ngắn

- Tăng tải nhanh gấp 3 lần baseline trong 1–2 phút.
- Ghi thời gian metric vượt target, desired tăng và healthy target tăng.
- Kiểm tra p95/p99 trong giai đoạn VM mới khởi động.
- Xác định headroom có đủ hấp thụ burst hay không.

### 18.2. Kiểm thử tải kéo dài

- Giữ tải cao 15–30 phút.
- Xác nhận group ổn định, không tạo instance liên tục.
- Theo dõi CPU/memory, connection pool và database latency.
- Xác nhận policy không vượt max.

### 18.3. Kiểm thử giảm tải

- Giảm tải theo bậc, sau đó dừng hoàn toàn.
- Theo dõi stabilization và thời điểm scale-in bắt đầu.
- Xác minh instance được drain trước khi terminate.
- Xác nhận group không giảm dưới min.

### 18.4. Kiểm thử instance failure

- Trong môi trường lab, chủ động terminate một VM.
- Xác nhận load balancer loại target unhealthy.
- Xác nhận group thay instance nếu health policy yêu cầu.
- Theo dõi thời gian replacement và request error.

### 18.5. Kiểm thử dependency bottleneck

- Dùng test stub hoặc môi trường riêng để tăng latency database giả lập.
- Quan sát CPU, application latency, connection wait và error.
- Xác nhận autoscaling không tăng vô hạn khi bottleneck ở DB.
- Thử rate limit/backpressure và so sánh kết quả.

### 18.6. Kiểm thử quota/capacity limit

- Đặt max group thấp trong lab hoặc dùng quota sandbox có giới hạn.
- Xác nhận alert group-at-max được kích hoạt.
- Xác nhận scaling activity nêu lý do rõ.
- Kiểm tra ứng dụng degraded gracefully hoặc queue giữ backlog an toàn.
- Không làm cạn quota dùng chung với workload quan trọng.

## 19. Bài tập vận dụng

### Bài tập 1: Chọn metric

Một API có CPU trung bình 35%, p95 tăng từ 180 ms lên 900 ms, database connection wait tăng mạnh và request rate không đổi. Có nên tăng application VM ngay không?

**Gợi ý:** Chưa nên scale-out chỉ dựa vào latency. Kiểm tra database connection pool, query latency, lock và giới hạn DB. Tăng VM có thể làm số connection tăng thêm và khiến tình trạng nặng hơn.

### Bài tập 2: Tính capacity

Một instance xử lý an toàn 90 request/giây. Utilization mục tiêu 60%. Peak load là 540 request/giây. Tính số instance tối thiểu theo throughput.

~~~text
Capacity planning mỗi VM = 90 × 0,60 = 54 req/s
N = ceil(540 / 54) = 10 VM
~~~

Sau đó cộng headroom cho zone failure và deployment surge. Không coi 10 VM là kết quả production cuối cùng nếu yêu cầu N-1 chưa được đáp ứng.

### Bài tập 3: Scale-in an toàn

Worker xử lý job trung bình 4 phút. Scale-in stabilization là 2 phút và termination grace period là 60 giây. Cấu hình này có đủ để đảm bảo job hoàn tất không?

**Gợi ý:** Không thể kết luận là đủ. Job dài hơn grace period; cần ngừng nhận job mới, checkpoint hoặc trả lease về queue. Có thể tăng grace period trong giới hạn nền tảng nhưng không thay thế cơ chế phục hồi job.

### Bài tập 4: Group chạm max

Desired capacity bằng max 20 VM, request/target vẫn cao và p99 vượt SLO. Nêu các bước điều tra.

**Gợi ý:** Kiểm tra healthy target count, quota, zone capacity, startup time, request distribution, CPU/memory per VM, database/cache/network bottleneck và budget. Chỉ tăng max sau khi xác nhận downstream và quota có thể chịu được.

### Bài tập 5: Phát hiện thrashing

Group liên tục tăng từ 4 lên 6 VM rồi giảm về 4 trong chu kỳ 5 phút. Nêu ba nguyên nhân và cách sửa.

**Gợi ý:** Threshold quá gần, evaluation window ngắn, warm-up không được tính đúng hoặc tải có burst. Tăng hysteresis/stabilization, đo metric chính xác và giảm scale-in step.

## 20. Checklist production readiness

**Workload và policy**

- [ ] Đã đo baseline, peak, request mix và throughput an toàn mỗi VM.
- [ ] Đã xác định SLO, headroom và N-1 capacity.
- [ ] Metric scale phản ánh bottleneck chính; có metric xác nhận.
- [ ] Target/threshold, evaluation window và scale-in stabilization được benchmark.
- [ ] Min/desired/max phù hợp quota, subnet IP, budget và downstream capacity.
- [ ] Scheduled/predictive scaling chỉ dùng khi pattern đủ tin cậy.

**Lifecycle và health**

- [ ] Image/template được version hóa và harden.
- [ ] Startup script idempotent, không chứa secret.
- [ ] Readiness chỉ pass khi app thực sự sẵn sàng.
- [ ] Instance warm-up được đo từ create đến first request.
- [ ] Scale-in có connection draining, graceful shutdown và timeout.
- [ ] Job dài có checkpoint/retry hoặc lease release.
- [ ] Scale-in protection/lifecycle hook có deadline và runbook.

**Observability**

- [ ] Dashboard có desired/current/min/max và healthy target count.
- [ ] Có metric request rate, request/target, p95/p99 và error rate.
- [ ] Có CPU/memory/disk/network theo instance và zone.
- [ ] Có scaling activity, trigger metric và provisioning failure.
- [ ] Có DB/cache/queue/external dependency metrics.
- [ ] Log/trace tập trung, có instance ID, zone và correlation ID.
- [ ] Alert có owner, severity, dashboard và runbook.

**Resilience và chi phí**

- [ ] Đã test burst, steady load, scale-in và instance failure.
- [ ] Đã test group-at-max và quota/capacity failure trong sandbox.
- [ ] Có backpressure/rate limit để bảo vệ downstream.
- [ ] Có budget/max capacity và theo dõi cost per successful request/job.
- [ ] Đã kiểm tra multi-zone distribution và failover.
- [ ] Đã dọn tài nguyên lab sau thực hành.

## 21. Kết luận

Autoscaling hiệu quả là sự kết hợp giữa capacity planning, metric đúng, policy ổn định, lifecycle an toàn và observability xuyên suốt. Scale-out cần đủ nhanh để bổ sung capacity trước khi SLO bị ảnh hưởng; scale-in cần thận trọng để không cắt request/job hoặc tạo dao động. Min, desired và max phải được đặt theo tải, availability, quota, subnet, budget và khả năng chịu tải của dependency.

Trong vận hành, luôn đối chiếu metric kích hoạt với scaling activity, healthy target count và kết quả ứng dụng. Nếu thêm VM không cải thiện latency hoặc queue age, hãy tìm bottleneck ở database, cache, network hoặc external service thay vì tăng capacity vô hạn. Thực hành load test, quan sát timeline, kiểm thử failure và đo cost per successful request giúp biến autoscaling từ một tùy chọn cấu hình thành cơ chế vận hành có thể kiểm chứng.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Autoscaling | Tự động điều chỉnh capacity theo metric, lịch hoặc dự báo. |
| Scale-out | Tăng số instance để có thêm capacity. |
| Scale-in | Giảm số instance khi nhu cầu thấp hơn. |
| Target tracking | Policy giữ metric gần giá trị mục tiêu. |
| Step scaling | Thay capacity theo các mức vượt threshold. |
| Scheduled scaling | Điều chỉnh capacity theo lịch. |
| Predictive scaling | Dùng lịch sử để dự báo và chuẩn bị capacity. |
| Min/desired/max | Số instance tối thiểu, mong muốn và tối đa của group. |
| Headroom | Capacity dự phòng cho burst, startup delay và failure. |
| Warm-up | Thời gian instance mới cần để trở thành capacity hữu ích. |
| Cooldown | Khoảng hạn chế đánh giá/thực hiện scaling tiếp theo theo semantics của policy. |
| Stabilization window | Khoảng quan sát ổn định trước khi thay đổi capacity, thường quan trọng với scale-in. |
| Hysteresis | Dùng ngưỡng scale-out và scale-in khác nhau để tránh dao động. |
| Readiness | Trạng thái ứng dụng đã sẵn sàng nhận traffic. |
| Connection draining | Ngừng gửi request mới và chờ request đang chạy hoàn tất. |
| Lifecycle hook | Điểm can thiệp vào vòng đời instance trước khi tiếp tục terminate/transition. |
| Queue depth | Số lượng message/job đang chờ trong queue. |
| Oldest message age | Tuổi của message/job cũ nhất còn tồn đọng. |
| Thrashing | Scaling liên tục tăng/giảm do policy hoặc metric dao động. |
| Backpressure | Cơ chế giới hạn đầu vào khi downstream không đủ capacity. |
| SLO | Mục tiêu chất lượng dịch vụ do đội vận hành đặt ra. |
| Cost per successful request | Chi phí để xử lý thành công một request. |
