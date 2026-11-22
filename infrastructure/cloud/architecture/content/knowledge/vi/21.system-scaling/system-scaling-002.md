# Chọn tín hiệu autoscaling theo lưu lượng, độ trễ và độ dài hàng đợi

## 1. Autoscaling phải phản ứng với nhu cầu trước khi trải nghiệm suy giảm

Autoscaling là cơ chế tự động thay đổi năng lực compute theo nhu cầu. Với ứng dụng cloud, nhu cầu có thể thay đổi theo giờ trong ngày, chiến dịch marketing, sự kiện đột biến, backlog xử lý nền hoặc sự cố ở một dependency. Nếu capacity cố định, hệ thống có thể lãng phí tài nguyên khi ít tải và thiếu tài nguyên khi tải tăng.

Khó khăn lớn nhất không nằm ở việc tăng số máy hay số replica, mà ở việc **chọn đúng tín hiệu để biết khi nào cần scale, scale bao nhiêu và khi nào nên scale-in**. CPU cao có thể là dấu hiệu thiếu compute, nhưng cũng có thể do một truy vấn lỗi hoặc vòng lặp vô hạn. CPU thấp không có nghĩa hệ thống đang khỏe: API có thể đang chờ database, thread pool có thể cạn, queue có thể tăng nhanh và người dùng phải chờ lâu.

Ba nhóm tín hiệu thường hữu ích:

- **Lưu lượng (traffic/demand):** request rate, event rate, số kết nối, số invocation hoặc số tác vụ đến.
- **Độ trễ và chất lượng phục vụ (latency/SLO):** p50/p95/p99 latency, timeout, error rate, thời gian chờ trong pool.
- **Độ dài và tuổi hàng đợi (queue depth/age):** số công việc đang chờ và thời gian công việc cũ nhất đã nằm trong queue.

Mỗi tín hiệu nhìn một lát cắt khác nhau của nhu cầu. Request rate phản ánh lượng công việc đến; latency cho biết người dùng hoặc hệ thống tiêu thụ đang nhận trải nghiệm nào; queue phản ánh phần công việc chưa xử lý và tốc độ backlog tích lũy. Chọn tín hiệu phải dựa vào kiểu workload, SLO, khả năng xử lý mỗi replica, giới hạn downstream và thời gian khởi động capacity.

Trong module **CLOUD_ARCHITECTURE**, autoscaling là một quyết định về khả năng mở rộng, hiệu năng, độ tin cậy, chi phí và vận hành. Một thiết kế tốt không chỉ tăng compute khi metric vượt ngưỡng; nó cần mô hình hóa demand, đo năng lực xử lý, chống dao động, bảo vệ dependency và kiểm thử dưới tải thực tế theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt tín hiệu demand, saturation, latency và backlog.
- Chọn metric phù hợp cho API đồng bộ, worker bất đồng bộ và workload theo lịch.
- Ước lượng capacity theo request rate, concurrency, queue arrival/processing rate và target utilization.
- Thiết kế target tracking, step scaling, scheduled và predictive scaling.
- Thiết lập scale-out/scale-in, cooldown, stabilization và minimum/maximum capacity.
- Nhận biết khi scale compute không giải quyết được bottleneck ở database, cache, network hoặc quota.
- Đánh giá chi phí, SLO, fairness và hành vi autoscaling khi metric lỗi.

## 2. Mô hình nhu cầu và năng lực xử lý

Autoscaling có thể hiểu như vòng điều khiển:

1. Thu thập metric mô tả lượng công việc đến và trạng thái xử lý.
2. So sánh với mục tiêu capacity/SLO.
3. Tính số instance, Pod, task hoặc worker cần bổ sung/loại bỏ.
4. Provision hoặc terminate compute.
5. Đo lại kết quả và điều chỉnh.

~~~mermaid
flowchart LR
    Demand["Traffic / Events / Queue"] --> Service["Ứng dụng / Worker"]
    Service --> Metrics["Metrics: RPS, latency, queue, CPU"]
    Metrics --> Policy["Autoscaling policy"]
    Policy --> Capacity["Desired capacity"]
    Capacity --> Runtime["Pods / Tasks / VM instances"]
    Runtime --> Service
    Service --> SLO["SLO: latency, errors, throughput"]
    SLO --> Metrics
~~~

### 2.1. Demand không đồng nghĩa utilization

| Nhóm | Ví dụ tín hiệu | Trả lời câu hỏi |
| --- | --- | --- |
| Demand | Requests/s, messages/s, active sessions | Có bao nhiêu việc đang đến? |
| Utilization | CPU, memory, worker slots, connection pool use | Tài nguyên hiện tại đang bận đến đâu? |
| Saturation | Thread pool queue, connection waiters, run queue, disk queue | Công việc có phải chờ vì tài nguyên đã đầy? |
| Latency | p95/p99 request duration, queue age, DB wait | Hệ thống đang phục vụ chậm tới mức nào? |
| Quality | Error rate, timeout, throttling, rejected requests | Tải có đang làm hỏng trải nghiệm hoặc SLO? |
| Backlog | Queue depth, oldest message age, pending jobs | Bao nhiêu việc chưa được hoàn thành? |

Utilization thường là tín hiệu tốt khi một workload tiêu thụ tài nguyên tương đối ổn định theo lượng công việc. Với workload I/O-bound, CPU có thể thấp trong khi thread chờ database hoặc network. Với queue worker, queue age có thể phản ánh nhu cầu nghiệp vụ trực tiếp hơn CPU.

### 2.2. Xác định capacity của một replica

Trước khi chọn metric, hãy đo một instance hoặc một Pod có thể phục vụ bao nhiêu công việc trong khi vẫn đáp ứng SLO.

Ví dụ một API instance duy trì p95 dưới 200 ms khi xử lý ổn định 120 request/giây ở workload đã kiểm thử. Nếu hệ thống cần 600 request/giây và muốn giữ headroom, không nên mặc định chỉ cần 5 instance. Cần xét target utilization, burst, phân bố request, cache hit ratio, downstream capacity và lỗi instance.

Capacity phải được đo trong điều kiện tương tự production: cùng CPU/memory limit, cùng network, cùng dependency, cùng loại request và cùng mức concurrency. Kết quả benchmark đơn giản với một endpoint nhẹ không đại diện cho toàn bộ ứng dụng.

## 3. Tín hiệu request rate và lưu lượng đến

Request rate là số request đến trong một đơn vị thời gian, thường là requests per second (RPS), requests per minute hoặc event rate. Đây là tín hiệu demand trực tiếp và thường hữu ích cho stateless API, gateway, web frontend và service có chi phí xử lý tương đối dự đoán được.

### 3.1. Khi nào scale theo request rate?

Phù hợp khi:

- Mỗi request có chi phí xử lý tương đối ổn định.
- Có metric request rate đáng tin cậy từ gateway, load balancer hoặc ứng dụng.
- Hệ thống biết capacity bền vững trên mỗi replica.
- Số replica có quan hệ khá tuyến tính với throughput trong phạm vi vận hành.

Ví dụ, một API image metadata xử lý trung bình 100 request/giây mỗi Pod trong giới hạn latency đã duyệt. Khi traffic tăng lên 800 request/giây, autoscaler có thể tính desired replicas từ capacity mục tiêu.

### 3.2. Công thức capacity theo request rate

Đặt:

- R là tổng request rate dự kiến.
- C là throughput bền vững trên một replica khi đáp ứng SLO.
- U là mức utilization mục tiêu, nằm trong khoảng 0 đến 1.
- N là số replica cần có.

Ước lượng:

**N >= ceil(R / (C × U)).**

Ví dụ R = 800 requests/s, mỗi replica xử lý C = 100 requests/s ở SLO, và target U = 0,7:

**N >= ceil(800 / 70) = 12 replicas.**

Kết quả 12 là sizing ban đầu; cần cộng headroom hoặc capacity dự phòng cho rollout, mất node/AZ và biến động tải. U không nên đặt quá cao nếu traffic burst lớn hoặc thời gian scale-out dài.

### 3.3. Cẩn thận với request có chi phí khác nhau

Một request đọc cache có thể rất nhẹ, trong khi request tạo báo cáo hoặc gọi nhiều service có thể nặng hơn hàng trăm lần. RPS tổng có thể che giấu sự thay đổi mix traffic.

Có thể cải thiện bằng cách:

- Theo dõi RPS theo endpoint, operation class hoặc workload queue.
- Dùng weighted request units khi có cách đo chi phí đáng tin cậy.
- Tách workload nặng thành worker pool riêng để scaling độc lập.
- Dùng concurrency, latency và saturation cùng với RPS để xác nhận.

Không tăng instance chỉ vì endpoint nhẹ có nhiều request nếu bottleneck thực sự nằm ở operation nặng.

### 3.4. Đo traffic ở đúng vị trí

Metric ở load balancer có thể đếm request đến kể cả request bị từ chối hoặc lỗi trước khi vào ứng dụng. Metric ở ứng dụng có thể bỏ sót request chưa được route vì gateway throttling. Cần phân biệt offered load, admitted load, successful throughput và completed throughput.

Nếu ứng dụng trả 429 khi quá tải, completed RPS có thể giảm trong khi offered RPS tăng. Scaling chỉ theo successful RPS có thể phản ứng ngược và làm tình hình xấu hơn. Nên lấy demand từ điểm trước admission control cùng error/throttle metrics.

## 4. Tín hiệu concurrency và số công việc đang xử lý

Concurrency là số request, invocation hoặc job đang được xử lý đồng thời. Nó hữu ích khi công việc giữ tài nguyên trong một khoảng thời gian và số tác vụ đồng thời liên hệ trực tiếp với thread, connection hoặc worker slot.

### 4.1. Liên hệ giữa RPS, concurrency và thời gian xử lý

Theo định luật Little trong hệ thống ổn định:

**L = λ × W**

Trong đó:

- L là số request trung bình đang ở trong hệ thống.
- λ là tốc độ request đến/hoàn thành trung bình.
- W là thời gian trung bình một request ở trong hệ thống.

Ví dụ 200 requests/s với thời gian xử lý trung bình 0,25 giây tương ứng khoảng 50 request đang xử lý đồng thời. Nếu thời gian tăng lên 1 giây mà RPS không đổi, concurrency trung bình tăng lên khoảng 200.

Đây là quan hệ trung bình trong trạng thái ổn định; không dùng nó để suy ra p99 hoặc mô tả chính xác một burst ngắn. Khi hệ thống không ổn định và backlog tăng liên tục, các giả định cân bằng không còn đúng.

### 4.2. Khi nào concurrency là tín hiệu tốt?

- Serverless functions có giới hạn concurrent executions.
- API server có số request inflight hoặc worker threads giới hạn.
- Long-running request, WebSocket hoặc streaming session giữ tài nguyên lâu.
- Worker có số slot xử lý job song song cố định.

Một concurrency cap cũng có thể là cơ chế bảo vệ. Khi downstream chỉ chịu được 300 thao tác đồng thời, không nên autoscale frontend lên mức tạo 2.000 request đồng thời tới database.

### 4.3. Rủi ro khi chỉ dùng concurrency

Concurrency có thể cao do request bị treo. Nếu chỉ scale theo active requests, hệ thống có thể tiếp tục thêm instance trong khi mỗi request chờ một dependency đang outage. Tổng số connection hoặc request tới dependency tăng và làm sự cố lan rộng.

Kết hợp concurrency với latency, timeout, pool wait và dependency health. Có thể giới hạn concurrency trên mỗi replica và toàn dịch vụ, đồng thời dùng circuit breaker hoặc admission control khi downstream không khỏe.

## 5. Tín hiệu latency và SLO

Latency mô tả thời gian hoàn thành thao tác từ góc nhìn người gọi hoặc một span xác định. Với autoscaling, p95/p99 thường hữu ích hơn average vì chúng cho thấy trải nghiệm của nhóm request chậm.

### 5.1. Vì sao p95/p99 quan trọng?

Giả sử 95% request hoàn thành trong 100 ms nhưng 5% mất 3 giây. Average có thể vẫn trông chấp nhận được, trong khi nhóm người dùng có trải nghiệm kém và timeout tăng. SLO thường định nghĩa tỷ lệ request hoàn thành dưới một ngưỡng, vì vậy tail latency là tín hiệu cần quan sát.

Latency tăng có thể do:

- Compute saturation hoặc CPU throttling.
- Thread/connection pool cạn.
- Database lock, slow query hoặc storage latency.
- Network congestion, DNS hoặc dependency ngoài.
- Cache miss, garbage collection hoặc cold start.
- Queueing trong gateway, service mesh hoặc load balancer.

Latency là tín hiệu chất lượng phục vụ, nhưng không phải lúc nào cũng chỉ ra cần thêm compute. Cần phân rã request duration theo queue wait, application processing và dependency spans.

### 5.2. Scale theo latency có độ trễ phản ứng

Latency thường xấu đi sau khi hệ thống bắt đầu thiếu capacity. Nếu autoscaler chỉ chờ p99 vượt SLO mới scale, người dùng đã chịu ảnh hưởng trước lúc replica mới sẵn sàng.

Có thể dùng latency để:

- Kích hoạt scale-out sớm hơn một ngưỡng SLO, có hysteresis.
- Kết hợp request rate để dự đoán capacity cần thêm.
- Xác nhận target tracking đã đưa utilization về vùng mong muốn.
- Điều chỉnh giới hạn concurrency khi dependency đang chậm.

Không scale-in chỉ vì latency thấp trong một khoảng ngắn; latency có thể thấp do traffic giảm tạm thời hoặc cache hit tăng.

### 5.3. Latency metric phải đúng scope

Nên đo latency cho operation và population cụ thể. Một dịch vụ có endpoint health check nhanh nhưng API thực tế chậm không thể coi là khỏe. Metric tổng hợp nhiều endpoint có thể che endpoint quan trọng. Với multi-tenant, latency theo tenant hoặc workload class giúp phát hiện noisy neighbor.

Khi dùng percentile để autoscale, cần kiểm tra metric window và số mẫu. Ở traffic thấp, p99 có thể không ổn định do ít request; nên kết hợp minimum sample count, traffic signal hoặc metric saturation.

## 6. Queue depth và queue age cho workload bất đồng bộ

Worker xử lý message, video, email, báo cáo hoặc batch thường không cần phản hồi đồng bộ ngay cho người gửi. Queue hấp thụ burst và tách tốc độ producer khỏi tốc độ consumer. Trong mô hình này, queue depth và queue age là các tín hiệu demand quan trọng.

### 6.1. Queue depth

Queue depth là số message/job đang chờ chưa được xử lý hoặc chưa được xác nhận theo semantics của queue. Nếu số message liên tục tăng, tốc độ đến đang lớn hơn tốc độ xử lý hoàn tất.

Ưu điểm:

- Phản ánh backlog trực tiếp.
- Hữu ích cho worker có processing time khác nhau nhưng số job có ý nghĩa.
- Dễ dùng làm metric cho KEDA, queue-based autoscaler hoặc custom policy.

Giới hạn:

- 1.000 job nhẹ khác 1.000 job nặng.
- Một queue có thể gồm nhiều priority hoặc tenant.
- Một số queue metric gồm cả in-flight message; cần hiểu định nghĩa.
- Batch size và retry có thể làm depth tăng/giảm không phản ánh throughput thật.

### 6.2. Queue age / oldest message age

Queue age là thời gian message cũ nhất hoặc một message đã chờ trong queue. Đây thường là tín hiệu gần với trải nghiệm nghiệp vụ hơn độ dài queue. Một backlog lớn có thể được chấp nhận nếu worker xử lý rất nhanh; một queue chỉ có vài chục job vẫn có thể vi phạm SLA nếu một job chờ quá lâu.

Ví dụ, email thông báo có thể được gửi trong vòng 2 phút; nếu oldest age vượt 90 giây, hệ thống sắp vi phạm SLA dù queue depth không lớn. Với video transcoding, queue age và thời gian hoàn thành theo loại độ phân giải phản ánh chất lượng dịch vụ tốt hơn chỉ số CPU.

### 6.3. Arrival rate và processing rate

Đặt:

- λ là tốc độ job đến queue (jobs/s).
- μ là tốc độ xử lý hoàn tất của toàn bộ worker pool (jobs/s).
- Q là queue depth.

Nếu λ > μ kéo dài, backlog tăng. Nếu λ < μ, queue có thể giảm. Một mô hình đơn giản:

**Thay đổi backlog mỗi giây ≈ λ − μ.**

Ví dụ queue nhận 150 job/s nhưng worker pool xử lý 100 job/s; backlog tăng khoảng 50 job mỗi giây khi các rate này ổn định. Scale-out cần làm μ tăng đủ để vượt λ và có thể giảm backlog trong thời gian SLA.

Khi job có duration hoặc trọng số khác nhau, đo processing throughput theo loại job hoặc estimated work units thay vì chỉ đếm job.

### 6.4. Tính số worker theo queue target

Nếu một worker xử lý bền vững r jobs/s, có n worker thì μ xấp xỉ n × r trong điều kiện scaling tuyến tính. Với backlog Q cần giảm trong thời hạn T, worker pool phải có throughput:

**μ_target >= λ + Q / T.**

Ví dụ queue có 12.000 job, tiếp tục nhận 40 job/s và muốn làm sạch backlog trong 120 giây:

**μ_target >= 40 + 12.000 / 120 = 140 jobs/s.**

Nếu một worker xử lý 10 jobs/s, ước lượng tối thiểu là 14 worker. Cần thêm headroom, tính retry, downstream limit và thời gian khởi động worker. Phép tính này giả định job đồng nhất và processing rate gần tuyến tính.

## 7. Chọn tín hiệu theo kiểu workload

| Workload | Tín hiệu chính | Tín hiệu bổ trợ | Lý do |
| --- | --- | --- | --- |
| Stateless HTTP API | RPS hoặc concurrent requests | p95/p99 latency, CPU, error/throttle | Demand trực tiếp và SLO phản ánh trải nghiệm |
| API có request cost biến đổi | Weighted RPS hoặc concurrency | Endpoint latency, CPU, downstream wait | RPS tổng không phản ánh chi phí request |
| Queue worker | Queue age hoặc queue depth | Arrival/processing rate, active jobs, CPU | Backlog là nhu cầu chưa hoàn thành |
| Serverless event consumer | Queue/event backlog và concurrent executions | Throttling, duration, downstream errors | Cần giới hạn concurrency để bảo vệ dependency |
| Batch theo lịch | Scheduled capacity hoặc queue of batch tasks | Job duration, CPU/memory, deadline | Nhu cầu biết trước và công việc có deadline |
| Streaming processor | Lag/age theo partition hoặc stream shard | Processing rate, CPU, partition skew | Lag phản ánh dữ liệu đang tụt lại |
| Stateful database | Không scale chỉ theo CPU/RPS đơn giản | Connection, IOPS, lock, storage, replication lag | Scaling cần semantics dữ liệu và giới hạn engine |
| WebSocket/session service | Active sessions và resource/session | Network throughput, memory, message rate | Session giữ tài nguyên lâu hơn request ngắn |

Không có một metric duy nhất nên được dùng cho mọi service. Một hệ thống có thể scale API theo RPS, worker theo oldest queue age và stream processor theo consumer lag; database được scale theo capacity/storage/IO và quy trình riêng.

## 8. Cách tính desired capacity và target utilization

Autoscaler thường cần một target: số request mỗi replica, CPU utilization, số message trên mỗi worker hoặc một mức latency/queue age mục tiêu.

### 8.1. Công thức tổng quát theo utilization

Với một metric utilization có ý nghĩa tương đối tuyến tính, có thể ước lượng:

**Desired replicas = ceil(current replicas × current metric / target metric).**

Ví dụ hiện có 4 Pod, CPU average 80%, target là 60%:

**Desired = ceil(4 × 80 / 60) = 6 Pod.**

Đây là công thức khái niệm thường dùng trong target tracking; controller thực tế còn xét tolerance, missing metrics, readiness, min/max và stabilization.

### 8.2. Target không nên là 100%

Đặt target utilization 100% khiến hệ thống không có headroom cho burst, GC, rollout hoặc node failure. Mục tiêu thường cần thấp hơn mức saturation để có thời gian scale-out. Giá trị phù hợp phải lấy từ load test và khả năng provision capacity.

Headroom không đồng nghĩa lãng phí: nó là một phần của availability/performance budget. Tuy nhiên, headroom quá lớn làm tăng chi phí. Cần đo cost per request và latency khi thay đổi target.

### 8.3. Kết hợp nhiều metric

Khi nhiều metric cùng được dùng, semantics của autoscaler quan trọng. Một policy có thể lấy desired capacity lớn nhất trong các metric để tránh metric này kéo xuống metric kia; một hệ khác có thể dùng composite metric hoặc custom controller. Phải đọc behavior của công cụ triển khai.

Ví dụ:

- RPS đề xuất 12 Pod.
- CPU đề xuất 9 Pod.
- Queue age đề xuất 15 Pod.

Nếu policy lấy mức lớn nhất, desired là 15 Pod để đáp ứng tín hiệu đòi hỏi nhiều capacity nhất. Nhưng nếu queue age tăng do database outage, tăng worker có thể gây thêm áp lực. Cần health gate hoặc concurrency cap theo downstream.

## 9. Các chiến lược autoscaling

### 9.1. Target tracking

Target tracking cố giữ một metric gần giá trị mục tiêu, ví dụ CPU 60%, 100 request/giây mỗi instance hoặc số message trên mỗi worker. Đây là lựa chọn thuận tiện cho workload có quan hệ capacity-metric tương đối rõ.

Ưu điểm là tự điều chỉnh capacity theo metric; giới hạn là metric phải phản ánh demand/capacity đúng và controller cần thời gian hội tụ. Target tracking trên CPU không tự giải quyết queue backlog hoặc downstream bottleneck.

### 9.2. Step scaling

Step scaling thay đổi capacity theo các bậc khi metric vượt những vùng ngưỡng. Ví dụ:

| Tín hiệu queue age | Thay đổi worker |
| --- | --- |
| Dưới 20 giây | Không scale-out |
| 20–45 giây | Thêm 2 worker |
| 45–90 giây | Thêm 5 worker |
| Trên 90 giây | Thêm 10 worker, đồng thời kiểm tra downstream |

Các mức chỉ là ví dụ. Nếu worker khởi động lâu, step lớn có thể giúp bắt kịp burst; nếu downstream có giới hạn cứng, thêm 10 worker có thể gây overload.

### 9.3. Scheduled scaling

Scheduled scaling thay đổi capacity trước thời điểm nhu cầu đã biết, ví dụ traffic tăng mỗi ngày lúc 9 giờ hoặc batch chạy lúc nửa đêm. Nó hữu ích để chuẩn bị warm capacity trước khi event bắt đầu, giảm phụ thuộc vào phản ứng sau khi metric đã tăng.

Scheduled scaling không nên thay hoàn toàn metric-based scaling vì lịch thực tế có thể thay đổi. Nên kết hợp baseline theo lịch với reactive scaling và giới hạn min/max.

### 9.4. Predictive scaling

Predictive scaling dùng dữ liệu lịch sử để dự báo nhu cầu và provision capacity trước thời điểm dự kiến. Phù hợp workload có chu kỳ rõ và đủ dữ liệu lịch sử. Nó có thể thất bại khi hành vi thay đổi đột ngột, chiến dịch mới hoặc sự cố ngoài dự kiến.

Giữ reactive scaling làm lớp bảo vệ cho sai số dự báo; đánh giá forecast accuracy và chi phí capacity provision sớm.

### 9.5. Event-driven scaling

Với queue hoặc event stream, autoscaler có thể dùng queue depth, oldest message age, consumer lag hoặc số event đang chờ. Công cụ như KEDA có thể dùng scaler theo nguồn sự kiện để điều chỉnh replica của workload Kubernetes; phải xác minh metric và scaling semantics của scaler cụ thể.

Scale-to-zero có thể tiết kiệm chi phí khi không có công việc, nhưng cold start làm tăng thời gian xử lý message đầu tiên. Với SLO nghiêm ngặt, giữ một số worker tối thiểu có thể hợp lý hơn.

## 10. Scale-out, scale-in, cooldown và stabilization

Autoscaling là vòng điều khiển có độ trễ. Metric cần thời gian thu thập, controller cần thời gian quyết định, cloud cần thời gian cấp tài nguyên và ứng dụng cần thời gian khởi động, warm cache, đăng ký service discovery và trở nên Ready.

### 10.1. Scale-out nhanh hơn scale-in

Scale-out thường cần phản ứng nhanh để bảo vệ SLO. Scale-in nên thận trọng hơn để tránh loại bỏ capacity ngay khi tải chỉ giảm tạm thời.

- Tăng capacity khi demand vượt target trong cửa sổ ngắn hoặc có dự báo burst đáng tin.
- Giữ capacity sau scale-out đủ lâu để metric ổn định.
- Giảm capacity theo từng bước nhỏ khi metric thấp liên tục trong thời gian dài hơn.
- Không scale-in dưới minimum capacity cần cho availability, warm cache hoặc throughput nền.

Nếu scale-out và scale-in dùng cùng một ngưỡng, metric dao động quanh ngưỡng có thể khiến hệ thống liên tục tạo/xóa instance. Đó là hiện tượng flapping.

### 10.2. Cooldown và stabilization window

Cooldown là khoảng thời gian chờ sau một hành động scaling trước khi thực hiện hành động khác hoặc trước khi đánh giá lại theo semantics của autoscaler. Stabilization window xem xét lịch sử metric/recommendation để tránh phản ứng với spike ngắn hoặc scale-in quá sớm.

Không chọn thời gian tùy ý. Hãy đo thời gian provision VM/Pod/task, health check và startup probe, warm cache/connection pool, chu kỳ scrape/aggregate metric và thời gian cần để thấy hiệu quả của lần scale trước.

Nếu worker mất 90 giây để khởi động mà policy đánh giá lại mỗi 10 giây và tăng mạnh liên tục, hệ thống có thể tạo nhiều worker chưa kịp xử lý backlog. Ngược lại, cooldown quá dài khiến hệ thống phản ứng chậm khi traffic thực sự tăng.

### 10.3. Hysteresis

Hysteresis dùng ngưỡng scale-out và scale-in khác nhau. Ví dụ:

| Metric utilization | Hành động |
| --- | --- |
| Trên 70% liên tục 2 phút | Scale-out |
| Trong khoảng 40–70% | Giữ capacity |
| Dưới 40% liên tục 10 phút | Cho phép scale-in |

Các ngưỡng chỉ minh họa. Hysteresis tạo vùng ổn định giữa hai hành động, giúp tránh flapping khi tải dao động quanh một điểm.

## 11. Provisioning delay và capacity buffer

Autoscaling phản ứng sau khi nhận diện demand; capacity mới không xuất hiện tức thời. Nếu thời gian từ metric tới replica Ready lớn hơn thời gian hệ thống có thể chịu thiếu capacity, reactive scaling đơn thuần không đủ.

### 11.1. Thành phần của scaling delay

**Scaling delay = detection + decision + provisioning + startup + readiness + warm-up.**

Ví dụ:

| Bước | Thời gian giả định |
| --- | ---: |
| Metric window và scrape | 30 giây |
| Controller quyết định | 10 giây |
| VM/Pod provision | 45 giây |
| Ứng dụng startup | 25 giây |
| Readiness và warm-up | 20 giây |
| Tổng gần đúng | 130 giây |

Trong 130 giây đó, hệ thống phải có đủ headroom, queue buffer hoặc cơ chế admission control để giữ trải nghiệm trong mức chấp nhận.

### 11.2. Minimum capacity và headroom

Minimum capacity tạo baseline đủ phục vụ tải nền và che phủ một phần scaling delay. Headroom là phần năng lực chưa dùng tại thời điểm hiện tại, dành cho burst, rollout hoặc mất instance.

Không chỉ tính min replicas theo average traffic. Cần xem tải giờ thấp điểm, burst trước khi autoscaler phản ứng, node/zone có thể mất, rolling deployment cần capacity bổ sung và khả năng dùng warm pool.

### 11.3. Warm pool và pre-warming

Với VM hoặc workload startup lâu, warm pool giữ một số instance đã khởi tạo nhưng chưa phục vụ traffic. Scheduled scaling có thể tăng capacity trước campaign; image caching, pre-pull container image và connection warm-up cũng giảm thời gian sẵn sàng.

Warm capacity phải được tính vào chi phí. Nó cần health check, patching, rotation và xác minh config để không trở thành instance cũ hoặc dễ lỗi.

## 12. Bảo vệ downstream: autoscaling có thể làm sự cố tệ hơn

Autoscaling compute không tạo thêm capacity cho mọi dependency. Nếu mỗi API replica mở 20 connection DB và autoscaler tăng từ 10 lên 100 replica, số connection tiềm năng có thể tăng từ 200 lên 2.000. Nếu database chỉ chịu được 500 connection an toàn, scale-out API có thể biến thiếu compute thành database outage.

### 12.1. Capacity budget end-to-end

Trước khi tăng replicas, xác định capacity của database connection/query throughput/transaction lock, cache connection/command rate/memory, message broker partitions/consumer quota, third-party API rate limit/concurrency, NAT gateway/IP/network bandwidth và shared storage IOPS/throughput.

### 12.2. Downstream-aware scaling

- Scale-out API theo RPS nhưng giới hạn request concurrency trên mỗi replica.
- Scale-out worker theo queue age nhưng giới hạn tổng consumer concurrency.
- Tạm dừng hoặc giảm tốc worker khi DB connection/latency vượt ngưỡng bảo vệ.
- Dùng bulkhead để phân pool connection theo workload class.
- Dùng circuit breaker, rate limiter hoặc queue để hấp thụ demand khi dependency lỗi.

Không đặt scaling policy để giảm compute chỉ vì database đang lỗi nếu điều đó làm backlog và SLA nặng hơn. Cần chọn cách phục vụ suy giảm có kiểm soát: throttle, defer, reject có thông báo hoặc phục vụ read-only/cache tùy nghiệp vụ.

### 12.3. Autoscaling và database

Database thường không scale giống stateless application. Tăng read replica có thể giúp tải đọc; tăng storage hoặc IOPS có thể giải quyết giới hạn lưu trữ; vertical scaling thay đổi compute capacity; sharding thay đổi kiến trúc dữ liệu. Mỗi loại có giới hạn, thời gian áp dụng và tác động consistency riêng.

Không dùng CPU database làm tín hiệu duy nhất. Theo dõi active connections, pool wait, lock wait, IOPS, storage latency, replication lag, cache hit và query p95/p99. Tăng application replicas khi database đã bão hòa thường làm lỗi tăng.

## 13. Queue-based scaling và backpressure

Queue worker cho phép hệ thống tiếp nhận công việc nhanh hơn năng lực xử lý tức thời. Tuy nhiên, queue không làm backlog tự biến mất. Nếu arrival rate vượt processing rate trong thời gian dài, queue age tăng và yêu cầu nghiệp vụ có thể hết hạn.

### 13.1. Mối quan hệ producer, queue và consumer

~~~mermaid
flowchart LR
    Producer["Producers"] --> Q[("Queue / Stream")]
    Q --> W1["Worker 1"]
    Q --> W2["Worker 2"]
    Q --> W3["Worker N"]
    W1 --> Down["Database / External API"]
    W2 --> Down
    W3 --> Down
    Q -. "Depth / age / lag" .-> Scale["Autoscaler"]
    Scale --> W1
~~~

### 13.2. Backpressure

Backpressure là cơ chế điều tiết tốc độ đưa việc vào hoặc lấy việc ra khi downstream không thể xử lý an toàn. Có thể giảm consumer concurrency hoặc prefetch, tạm dừng batch mới khi worker có nhiều in-flight jobs, giới hạn producer rate theo quota downstream, dùng queue priority/deadline và reject/defer tác vụ không thể đáp ứng SLA.

Queue depth có thể tăng vì worker lỗi, message poison, dependency outage hoặc throughput thực sự thiếu. Trước khi scale-out, kiểm tra error/retry rate, dead-letter count và downstream saturation.

### 13.3. Visibility timeout, ack và retry

Với queue có visibility timeout, consumer phải hoàn thành/ack trong khoảng thời gian phù hợp hoặc gia hạn theo semantics dịch vụ. Nếu timeout quá ngắn, message có thể được giao lại khi worker vẫn đang chạy, làm xử lý trùng. Nếu quá dài, một worker chết có thể khiến message phải chờ lâu mới được giao lại.

Autoscaling làm số consumer tăng, nhưng không thay thế idempotency. Tác vụ ghi DB, gửi email hoặc charge payment phải có idempotency key/operation ID để retry không nhân đôi side effect.

### 13.4. Queue age theo SLO

| Loại công việc | SLO minh họa | Tín hiệu chính |
| --- | --- | --- |
| Email xác nhận | Bắt đầu gửi trong 60 giây | Oldest message age |
| Xử lý thumbnail | Hoàn thành trong 3 phút | Age + job completion duration |
| Video encoding | Hoàn thành trong 20 phút theo profile | Age theo loại job + processing rate |
| Batch đối soát | Hoàn thành trước 06:00 | Remaining work + deadline |

Queue age nên được phân loại theo priority/queue nếu các công việc có SLA khác nhau. Một queue chung có thể khiến job ưu tiên thấp chặn job quan trọng nếu không có fairness policy.

## 14. Event stream và autoscaling theo consumer lag

Với Kafka hoặc stream partitioned, consumer group có số partition giới hạn mức parallelism truyền thống. Consumer lag là khoảng cách giữa offset mới nhất và offset đã xử lý/commit của consumer, theo metric của nền tảng.

### 14.1. Lag không chỉ là một con số

Theo dõi:

- Lag theo từng partition, không chỉ tổng group.
- Tuổi event cũ nhất chưa xử lý.
- Ingress bytes/records và consumer processing rate.
- Partition skew/hot key.
- Rebalance frequency, processing error và downstream latency.

Nếu một partition nóng chiếm phần lớn lag, tăng consumer count không thể chia nhỏ partition đó trong cùng group. Cần xử lý key skew, tối ưu consumer hoặc thay đổi topology có kế hoạch.

### 14.2. Giới hạn scale theo partition

Với P partition và consumer group truyền thống:

**Số consumer có thể active tối đa <= P.**

Nếu có 8 partition nhưng autoscaler tạo 20 consumer, ít nhất 12 consumer không được gán partition. Capacity dư làm tăng chi phí mà không tăng tốc xử lý.

Một số nền tảng hỗ trợ cooperative rebalancing, static membership hoặc cơ chế khác để giảm chi phí reassignment; chúng không loại bỏ giới hạn parallelism cơ bản của partition.

### 14.3. Thêm partition có phải cách scale?

Thêm partition có thể tăng parallelism trong tương lai, nhưng thay đổi partition count có thể làm key mapping đổi và ảnh hưởng ordering theo entity. Đánh giá producer partitioner, key distribution, consumer state, retention và migration plan trước khi tăng.

## 15. Kubernetes: HPA, KEDA và node autoscaling

Kubernetes có nhiều lớp scaling; cần phân biệt scaling Pod với scaling node.

### 15.1. Horizontal Pod Autoscaler (HPA)

HPA điều chỉnh số replica của workload như Deployment hoặc StatefulSet dựa trên metric resource hoặc custom/external metrics. CPU/memory utilization thường cần resource requests để tính tỷ lệ. Metric custom có thể là request rate, active requests hoặc queue metric nếu được cung cấp qua adapter phù hợp.

Ví dụ khai báo HPA:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: checkout-api
  namespace: commerce
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: checkout-api
  minReplicas: 3
  maxReplicas: 30
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
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 20
          periodSeconds: 60
~~~

Đây là manifest minh họa, không phải cấu hình dùng chung. Cần kiểm tra metrics-server/custom metrics adapter, requests/limits, readiness, Pod startup time, node capacity và phiên bản Kubernetes. maxReplicas cũng phải phù hợp quota và capacity database.

### 15.2. KEDA và event-driven autoscaling

KEDA cung cấp event-driven scaling cho workload Kubernetes thông qua scaler cho queue, stream, database hoặc nguồn sự kiện được hỗ trợ. KEDA có thể phối hợp với HPA và hỗ trợ scale-to-zero theo loại workload.

Trước khi dùng, xác minh metric scaler đại diện queue depth, lag hay rate nào; authentication/secret và quyền truy vấn metric; polling interval, cooldown và activation threshold; maximum replicas có bảo vệ downstream không; behavior khi metric source không truy cập được; consumer concurrency có giới hạn theo partition/queue quota không.

### 15.3. Cluster/node autoscaling

HPA/KEDA có thể tăng Pod nhưng Pod sẽ Pending nếu cluster không đủ CPU/RAM hoặc node phù hợp. Node autoscaler bổ sung hoặc loại node để đáp ứng scheduling demand. Node startup thường chậm hơn tạo Pod trên node đã có sẵn; do đó cần headroom, node pool phù hợp và quota cloud.

Phải thiết kế cả hai lớp:

1. Pod scaling theo demand/SLO.
2. Node scaling theo Pod Pending, resource requests và node constraints.

Nếu Pod yêu cầu GPU nhưng node pool không có GPU quota, autoscaling không thể tạo capacity. Cần theo dõi quota, subnet IP, instance availability và giới hạn provider.

## 16. Serverless và autoscaling được quản lý bởi nền tảng

Serverless platform có thể tự scale execution environment hoặc concurrency theo cấu hình/quota. Người dùng vẫn phải chọn concurrency cap, provisioned/warm capacity, queue event batch và giới hạn downstream.

### 16.1. Tín hiệu thường cần theo dõi

- Concurrent executions và throttles.
- Invocation/request rate và duration.
- Queue/event source age, backlog hoặc iterator/consumer lag.
- Error rate, timeout và retry count.
- Database connection, proxy saturation và API quota.

Không mặc định serverless scale vô hạn. Provider quota, region capacity, concurrency limit, network attachment và downstream quota đều có thể giới hạn.

### 16.2. Provisioned concurrency / warm capacity

Với API nhạy latency hoặc workload có cold start đáng kể, có thể giữ một phần execution environment warm/provisioned. Điều này giảm startup latency nhưng tạo chi phí ngay cả khi traffic thấp. Chọn baseline theo traffic forecast và SLO, giữ reactive capacity cho burst.

### 16.3. Batch size và event source mapping

Batch size lớn có thể giảm overhead invocation nhưng tăng thời gian xử lý, memory và phạm vi retry. Batch nhỏ tăng invocation và connection churn. Tuning cùng concurrency, visibility timeout, partial batch failure và idempotency.

## 17. Quan sát và điều khiển autoscaling

Autoscaling phải được quan sát như một hệ thống điều khiển, không chỉ xem số replica cuối cùng.

### 17.1. Dashboard tối thiểu

| Nhóm | Metric |
| --- | --- |
| Demand | Offered RPS, admitted RPS, event arrival rate, queue depth |
| Service level | p50/p95/p99 latency, success/error rate, timeout, throttling |
| Saturation | CPU/memory, thread/connection wait, disk/network, active worker slots |
| Queue/stream | Oldest age, lag per partition, arrival vs completion rate, retry/DLQ |
| Scaling controller | Desired/current replicas, scaling event, decision reason, stabilization/cooldown |
| Provisioning | Pending pods, launch time, readiness time, node capacity, quota errors |
| Downstream | DB connections/latency, cache saturation, external API rate limit |
| Cost | Instance/Pod hours, cost per request/job, idle capacity, scale churn |

### 17.2. Correlation và metric hygiene

Ghi lại thời điểm scaling event và correlation với traffic, latency, queue, error và downstream. Dùng cùng cửa sổ thời gian khi phân tích. Metric có nhãn cardinality quá cao hoặc thiếu sample có thể tạo tín hiệu sai. Với autoscaler, metric phải có aggregation phù hợp và behavior rõ khi missing/NaN/stale.

Khi metrics source mất kết nối, không để controller diễn giải “không có metric” thành “không có tải” rồi scale-in nguy hiểm. Xác định fail-safe behavior theo công cụ.

### 17.3. Scaling policy là cấu hình cần review

Version hóa min/max, target, cooldown, scheduled window, metric query, auth và downstream cap trong IaC. Review thay đổi như thay đổi capacity architecture. Cần audit ai đổi max replicas từ 30 lên 300 hoặc target từ 60% xuống 95%.

## 18. Cost, fairness và giới hạn tài nguyên

Autoscaling tối ưu chi phí khi capacity theo nhu cầu nhưng có thể tạo bill lớn nếu metric nhiễu, retry storm hoặc minimum capacity quá cao.

### 18.1. Đo cost efficiency

Các chỉ số hữu ích:

- Cost per successful request hoặc transaction.
- Cost per completed job/video/report.
- Tỷ lệ idle capacity và thời gian chờ capacity mới.
- Số lần scale event và số instance được tạo nhưng chưa Ready.
- Chi phí retry, duplicate processing và queue retention.
- Chi phí data transfer, NAT, logging và downstream theo mức scale.

Đừng giảm target utilization quá thấp chỉ vì muốn latency tốt hơn nếu cost tăng vượt ngân sách. Cần so sánh đường cong cost-latency và tìm điểm phù hợp SLO.

### 18.2. Fairness giữa tenant và workload

Một tenant có thể tạo burst và chiếm toàn bộ worker hoặc connection. Nếu scale theo queue depth tổng, tenant lớn có thể khiến workload của tenant nhỏ chờ lâu.

Giải pháp gồm:

- Queue riêng hoặc logical partition theo tenant/priority khi cần.
- Per-tenant rate limit và concurrency quota.
- Weighted fair scheduling hoặc worker pool dành riêng cho workload critical.
- Metric queue age theo tenant/priority để phát hiện starvation.
- Giới hạn số job lớn đồng thời và quota export/report.

Fairness là yêu cầu sản phẩm và vận hành; không chỉ là bài toán CPU.

## 19. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ scale theo CPU | Bỏ lỡ I/O wait, queue backlog và latency | Kết hợp demand, latency, saturation và queue |
| Scale theo successful RPS | Traffic bị từ chối làm metric giảm, autoscaler scale-in | Đo offered/admitted load và throttle |
| Chỉ dùng average latency | Tail latency xấu bị che giấu | Theo dõi p95/p99 và sample count |
| Scale theo queue depth mà bỏ qua job cost | Queue job nặng/nhẹ bị xem như nhau | Dùng queue age, work units và class |
| Không giới hạn max replicas | Downstream/chi phí bị vượt ngưỡng | Đặt cap theo end-to-end capacity budget |
| Cooldown quá ngắn | Flapping và tạo instance liên tục | Hysteresis, stabilization và đo startup time |
| Scale-in quá nhanh | Request/job đang chạy bị gián đoạn | Graceful shutdown, drain và scale-in stabilization |
| Tăng consumer vượt partition | Consumer idle, không tăng throughput | Tính giới hạn parallelism và xử lý key skew |
| Scale API làm DB quá tải | Connection storm, query latency và cascade failure | Downstream-aware concurrency cap và pool budget |
| Không chuẩn bị node quota/IP | Pod Pending dù HPA đã tăng desired replicas | Kiểm tra quota, subnet IP, node pool và headroom |
| Tin predictive scaling tuyệt đối | Thiếu capacity khi pattern đổi | Reactive guardrail và forecast monitoring |
| Coi metric missing là zero | Scale-in sai khi monitoring lỗi | Missing-data policy an toàn và alert telemetry |

## 20. Bài thực hành: chọn autoscaling signal cho nền tảng đặt hàng

Một nền tảng thương mại điện tử có:

- Checkout API xử lý request đồng bộ, yêu cầu p95 dưới 250 ms.
- Worker gửi email và tạo hóa đơn qua queue.
- Worker xử lý ảnh sản phẩm với processing time khác nhau theo kích thước ảnh.
- Consumer đọc event stream có 24 partition.
- PostgreSQL managed có connection budget đã được phê duyệt và không thể scale tức thời.

Trong campaign, offered traffic tăng gấp 5 trong 3 phút. CPU API chỉ lên 55% nhưng p99 latency tăng; queue email tăng từ 500 lên 18.000 message và oldest age đạt 110 giây. Consumer stream lag tập trung ở 2 partition nóng. Database connection đã đạt 85% ngân sách an toàn.

**Yêu cầu bài làm:**

1. Chọn tín hiệu scale cho checkout API và giải thích vì sao CPU 55% không đủ kết luận còn capacity.
2. Tách offered RPS, admitted RPS, p95/p99, inflight requests, pool wait và database latency trên dashboard.
3. Ước lượng số API replica từ benchmark capacity/replica; chọn target utilization và headroom.
4. Chọn queue depth hay oldest age cho email worker; tính worker throughput cần để giảm backlog trong SLA đã nêu.
5. Chọn tín hiệu cho image worker khi job có chi phí khác nhau; đề xuất work units hoặc queue tách theo class.
6. Giải thích vì sao tăng consumer từ 24 lên 40 không tự giải quyết hot partition; đề xuất cách xử lý skew.
7. Đặt concurrency cap để không làm PostgreSQL vượt connection budget; mô tả backpressure khi DB gần bão hòa.
8. Đề xuất cooldown, stabilization, min/max replicas, warm capacity và scale-in behavior.
9. Xác định behavior khi metric source ngừng cập nhật hoặc downstream database lỗi.
10. Thiết kế load test và chaos test để chứng minh SLO, queue age, recovery và cost.

### Gợi ý đánh giá

Một thiết kế tốt dùng nhiều tín hiệu theo workload: API theo demand/concurrency kết hợp p99 và downstream saturation; email worker theo oldest age/depth và processing rate; image worker theo estimated work units hoặc queue riêng theo class; stream consumer theo lag từng partition và giới hạn parallelism.

Database đang ở 85% connection budget là ràng buộc quan trọng. Scale API/worker không giới hạn có thể tăng connection và làm latency xấu hơn. Phương án cần concurrency cap, pool nhỏ, backpressure hoặc defer công việc, đồng thời xử lý hai partition nóng thay vì chỉ tăng consumer.

## 21. Checklist đưa autoscaling vào production

- [ ] Xác định SLO, offered load, traffic mix và capacity bền vững của mỗi replica.
- [ ] Chọn metric đại diện đúng demand: RPS, concurrency, queue depth/age, lag hoặc work units.
- [ ] Theo dõi p95/p99 latency, error rate, timeout và saturation bên cạnh utilization.
- [ ] Đo provisioning delay từ detection tới Ready/warm capacity.
- [ ] Tính target capacity có headroom cho burst, rollout và failure domain.
- [ ] Đặt min/max replicas, node quota, IP quota và downstream concurrency cap.
- [ ] Có scale-out nhanh và scale-in thận trọng, hysteresis/stabilization phù hợp.
- [ ] Tính queue arrival/processing rate và thời gian làm sạch backlog theo SLA.
- [ ] Có backpressure, rate limit, priority/fairness và idempotency cho worker.
- [ ] Với stream, theo dõi lag theo partition, hot key và giới hạn consumer parallelism.
- [ ] Kiểm tra metric window, sample count, stale/missing data và fail-safe behavior.
- [ ] Đảm bảo graceful shutdown/drain trước scale-in để không mất request/job.
- [ ] Đánh giá dependency capacity: DB, cache, broker, API quota, network, storage và NAT.
- [ ] Version hóa policy trong IaC và audit thay đổi scaling.
- [ ] Load test steady, ramp, spike, sustained peak, scale-in và cold start.
- [ ] Chaos test metric outage, node failure, downstream slowdown và queue retry storm.
- [ ] Theo dõi cost per successful request/job và idle capacity.
- [ ] Có dashboard, alert, runbook và owner chịu trách nhiệm cho scaling policy.

**Ghi nhớ:** Autoscaling tốt chọn tín hiệu phản ánh lượng công việc và khả năng hoàn thành, không chỉ một chỉ số utilization. RPS cho biết demand đến, concurrency cho biết lượng việc đang giữ tài nguyên, latency cho biết trải nghiệm và queue age/depth cho biết backlog. Hãy kết hợp chúng theo loại workload, tính capacity bằng benchmark, đặt headroom và giới hạn downstream, rồi điều khiển scale-out/scale-in với cooldown, stabilization và backpressure. Mục tiêu cuối cùng là đáp ứng SLO với chi phí hợp lý mà không đẩy bottleneck sang database, broker hay dịch vụ phụ thuộc.
