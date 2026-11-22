# Load test, capacity test và kiểm chứng autoscaling

Một API có thể chạy tốt với vài chục người dùng nhưng chậm hoặc trả lỗi khi traffic tăng gấp mười lần. Một Auto Scaling Group có thể tăng số EC2 instance đúng như cấu hình nhưng người dùng vẫn thấy latency cao vì database connection pool đã cạn, hàng đợi bị tồn đọng hoặc load balancer chưa đưa instance mới vào phục vụ. Vì vậy, kiểm thử hiệu năng cần đo toàn bộ workload và xác minh rằng hệ thống mở rộng, giữ ổn định rồi thu hẹp capacity đúng cách.

Trong AWS, load test giúp đo hành vi ứng dụng dưới tải thực tế; capacity test xác định mức tải bền vững và giới hạn của từng thành phần; autoscaling test kiểm chứng chính sách điều chỉnh compute khi nhu cầu thay đổi. Các phép thử này kết hợp CloudWatch, Application Load Balancer, EC2 Auto Scaling, Application Auto Scaling, ECS, Lambda, database metrics và công cụ tạo tải phân tán.

Trong hệ sinh thái **CLOUD_PROVIDERS_AWS**, người học cần biết chuyển yêu cầu nghiệp vụ thành SLO có thể đo, tạo workload giống production, tính capacity theo dữ liệu benchmark, tìm bottleneck, xác minh scale-out/scale-in và kiểm soát quota/chi phí. Mục tiêu cuối cùng là chứng minh ứng dụng đáp ứng throughput, latency, error rate và availability khi tải bình thường, tải đỉnh và tải tăng đột biến.

## 1. Phân biệt load test, capacity test và autoscaling test

Ba phép thử liên quan nhưng trả lời các câu hỏi khác nhau.

| Phép thử | Câu hỏi chính | Kết quả cần thu được |
|---|---|---|
| Load test | Ứng dụng hoạt động ra sao dưới workload dự kiến? | Throughput, latency, error rate và hành vi các dependency |
| Capacity test | Workload chịu được tối đa bao nhiêu trước khi vi phạm SLO? | Sustainable capacity, bottleneck và breaking point |
| Autoscaling test | Hệ thống có bổ sung/loại bỏ capacity đúng lúc và đúng mức không? | Scale-out delay, scale-in behavior, stability và SLO trong lúc scaling |

Một load test có thể đạt yêu cầu dù không có autoscaling, nếu capacity được provision sẵn. Ngược lại, autoscaling có thể thay đổi số instance đúng cấu hình nhưng vẫn không đủ nhanh để xử lý traffic spike. Cần đánh giá riêng cả hiệu năng ứng dụng và hành vi scaling.

## 2. Xác định SLO và tiêu chí chấp nhận trước khi tạo tải

Không nên bắt đầu bằng câu hỏi "chạy được bao nhiêu request mỗi giây?". Trước tiên, xác định người dùng cần trải nghiệm gì và hệ thống phải đáp ứng điều kiện nào.

Ví dụ SLO cho một API đặt hàng:

| Chỉ số | Tiêu chí minh họa |
|---|---|
| Throughput | 800 request/second trong 30 phút |
| Latency | p95 dưới 250 ms, p99 dưới 700 ms |
| Error rate | HTTP 5xx và lỗi ứng dụng dưới 0,5% |
| Availability | Không mất toàn bộ khả năng phục vụ khi một instance/AZ lỗi |
| Recovery | Capacity bổ sung sẵn sàng trong vòng 3 phút |
| Data correctness | Không tạo đơn trùng hoặc mất giao dịch |

Các con số trên chỉ là ví dụ. SLO thật phải xuất phát từ hợp đồng dịch vụ, hành vi người dùng, business impact và benchmark của workload.

Phân biệt:

- **SLO:** mục tiêu độ tin cậy hoặc hiệu năng nội bộ.
- **SLI:** số liệu đo thực tế, ví dụ p95 latency hoặc tỷ lệ request thành công.
- **SLA:** cam kết dịch vụ với khách hàng, có thể kèm điều khoản bồi hoàn.
- **Threshold của test:** điều kiện để một lần chạy được đánh dấu pass/fail.

Đặt threshold cho từng user journey quan trọng, không chỉ cho endpoint health check. Một trang có thể trả HTTP 200 nhưng mất dữ liệu, xử lý sai nghiệp vụ hoặc trả response thiếu field.

## 3. Các loại kiểm thử hiệu năng

| Loại test | Mô tả | Mục đích |
|---|---|---|
| Smoke test | Tải rất thấp trong thời gian ngắn | Xác nhận script, dữ liệu và endpoint hoạt động |
| Load test | Tải đại diện cho traffic dự kiến | Xác minh SLO ở mức tải bình thường/đỉnh |
| Stress test | Tăng tải vượt capacity dự kiến | Tìm breaking point và cách hệ thống suy giảm |
| Spike test | Tăng tải rất nhanh rồi giảm | Kiểm tra phản ứng trước traffic burst |
| Soak/endurance test | Giữ tải ổn định trong thời gian dài | Tìm memory leak, connection leak, queue growth và degradation |
| Capacity test | Tăng tải có kiểm soát đến giới hạn | Đo throughput bền vững và số lượng resource cần thiết |
| Scalability test | Thay đổi tải và/hoặc capacity theo nhiều mức | Kiểm tra hiệu quả scale-up/scale-out |
| Failover/resilience test | Kết hợp tải với lỗi instance, AZ hoặc dependency | Xác minh workload duy trì SLO và phục hồi |

Một chương trình kiểm thử thường chạy smoke trước, sau đó load, spike, soak và capacity. Chỉ chạy stress test sau khi đã xác định ngưỡng bảo vệ và cách dừng an toàn.

## 4. Mô hình workload: virtual users và arrival rate

Hai cách phổ biến để mô phỏng người dùng:

- **Closed workload model:** số virtual users cố định; mỗi user gửi request, chờ response và think time rồi mới gửi request tiếp. Khi hệ thống chậm, tốc độ tạo request tự giảm.
- **Open workload model:** test đặt trước arrival rate, ví dụ 500 request/second, độc lập với response time. Nếu hệ thống chậm, số request đang chờ tăng lên.

Closed model phù hợp với hành vi người dùng tương tác có thời gian chờ. Open model phù hợp khi muốn xác minh hệ thống có xử lý được tốc độ request đầu vào cố định hay không.

Nếu dùng closed model để kiểm tra hệ thống quá tải, latency tăng có thể làm load generator tự giảm request rate và che giấu bottleneck. Chọn workload model theo mục tiêu test và luôn ghi nhận actual request rate.

### Little's Law

Với hệ thống ổn định, số request đang xử lý trung bình có thể ước lượng bằng:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\): số request đang in-flight (concurrency trung bình).
- \(\lambda\): arrival rate, tính bằng request/second.
- \(W\): thời gian response trung bình, tính bằng second.

Ví dụ 300 request/second với response time trung bình 0,4 giây tương ứng khoảng 120 request đang in-flight. Công thức giúp ước lượng concurrency, connection pool và số worker cần thiết; nó không thay thế benchmark thực tế.

## 5. Thiết kế user journey và phân phối traffic

Một workload production thường gồm nhiều endpoint và loại thao tác. Chỉ gọi một endpoint health check không phản ánh tải thực.

Ví dụ tỷ trọng request của ứng dụng thương mại điện tử:

| User journey | Tỷ trọng | Đặc điểm |
|---|---:|---|
| Xem danh mục/sản phẩm | 45% | Read-heavy, cache có thể phát huy hiệu quả |
| Tìm kiếm | 20% | Có thể tạo tải CPU hoặc search cluster |
| Đăng nhập/xác thực | 10% | Phụ thuộc identity provider và token validation |
| Thêm giỏ hàng | 15% | Có write, concurrency và consistency |
| Tạo đơn/thanh toán giả lập | 10% | Nhiều dependency, cần idempotency |

Thiết kế test cần mô phỏng:

- Tỷ lệ read/write.
- Kích thước request/response.
- Think time và hành vi retry.
- Cache hit/miss ratio.
- Phân phối tenant/user/product.
- Số lượng request đồng thời trên mỗi user.
- Authentication và session behavior.
- Các dependency như database, queue, payment sandbox và external API.

Không gọi hệ thống thanh toán thật hoặc dịch vụ bên thứ ba bằng dữ liệu thử nghiệm nếu chưa có môi trường sandbox và sự chấp thuận phù hợp.

## 6. Chuẩn bị môi trường production-like

Kết quả test chỉ có giá trị khi môi trường đủ giống production ở các yếu tố ảnh hưởng hiệu năng:

- Instance/task size, số AZ và load balancer.
- Container image, runtime, application configuration.
- Database engine/version, parameter group, storage và connection pool.
- Cache, queue, network path và security group.
- Autoscaling policy, min/max capacity và warmup.
- Data volume, data distribution và index.
- TLS, authentication, logging và tracing.

Nếu test trên môi trường nhỏ hơn production, không nhân kết quả theo tỷ lệ CPU hoặc số instance một cách máy móc. Cache, network, database contention, shard/partition và quota có thể thay đổi phi tuyến.

Ưu tiên dựng môi trường bằng Infrastructure as Code để cấu hình test và production có thể so sánh. Ghi lại mọi khác biệt như instance family, storage class, dataset size và service quota.

## 7. An toàn dữ liệu và phạm vi kiểm thử

Sử dụng dữ liệu tổng hợp hoặc bản sao production đã loại bỏ thông tin nhạy cảm. Gắn test run ID vào header, record hoặc partition để tách test data khỏi báo cáo nghiệp vụ thật.

Trước khi chạy:

1. Xác định endpoint và account/Region đích.
2. Xác nhận chủ sở hữu workload và cửa sổ test.
3. Kiểm tra quota của dịch vụ và giới hạn load generator.
4. Đặt giới hạn request rate, duration và số virtual users.
5. Chuẩn bị alarm, dashboard và người trực theo dõi.
6. Xác định điều kiện dừng ngay nếu production bị ảnh hưởng.
7. Kiểm tra AWS policy hiện hành nếu traffic pattern có thể bị xem như DoS/DDoS hoặc có nguồn phát tải bên ngoài.

AWS Well-Architected khuyến nghị test trên môi trường production-like, dùng dữ liệu synthetic/sanitized và đo toàn bộ workload. Nếu thực hiện load test trên production, phải giới hạn blast radius, tránh ảnh hưởng người dùng và đánh dấu test data để không làm sai báo cáo. https://docs.aws.amazon.com/wellarchitected/2024-06-27/framework/perf_process_culture_load_test.html

## 8. Công cụ tạo tải

| Công cụ | Điểm mạnh | Khi phù hợp |
|---|---|---|
| k6 | Script JavaScript, thresholds, dễ tích hợp CI/CD | API và HTTP workloads |
| Apache JMeter | Nhiều protocol/plugin, GUI và distributed mode | Workload HTTP, JDBC, JMS và hệ thống legacy |
| Locust | Python, user behavior tùy biến | Mô phỏng journey phức tạp |
| Artillery | Script gọn, HTTP/WebSocket và cloud execution | API, realtime và CI performance checks |
| Distributed Load Testing on AWS | Quản lý test runners phân tán, dashboard và baseline | Tải lớn, multi-Region và test lặp lại |

**Distributed Load Testing on AWS** là giải pháp mã nguồn mở do AWS cung cấp. Hướng dẫn hiện hành hỗ trợ JMeter, k6, Locust và test HTTP endpoint; có thể phân phối runner qua nhiều Region, lên lịch chạy và so sánh baseline. Dashboard cung cấp latency percentile, error analysis và artifacts. https://docs.aws.amazon.com/solutions/latest/distributed-load-testing-on-aws/solution-overview.html

Không mặc định một load generator có thể tạo vô hạn request. CPU, network, file descriptor, ephemeral port, DNS và số worker của generator đều có thể trở thành bottleneck.

## 9. Tránh load generator trở thành bottleneck

Khi generator quá tải, kết quả có thể cho thấy ứng dụng chậm trong khi nguyên nhân thực tế nằm ở máy tạo tải.

Theo dõi generator:

- CPU, memory và network utilization.
- Số virtual users và actual arrival rate.
- Dropped iterations hoặc request scheduling delay.
- Socket/connection errors.
- DNS resolution và TLS handshake rate.
- File descriptor và ephemeral port usage.
- Số worker/container đang tạo tải.

Nếu generator đạt 100% CPU hoặc không tạo đủ request như kịch bản, tăng số runner hoặc phân phối test qua nhiều AZ/Region. Ghi rõ số runner và tổng arrival rate trong báo cáo.

## 10. Định nghĩa kịch bản test có thể lặp lại

Một test scenario nên có:

- Test ID và version của script.
- Endpoint/base URL và Region.
- Workload model: closed hoặc open.
- Ramp-up, steady-state, spike và ramp-down duration.
- Virtual users hoặc arrival rate mục tiêu.
- Request mix và dữ liệu test.
- Thresholds cho latency/error/throughput.
- Tags để phân biệt test run và môi trường.
- Điều kiện dừng và người chịu trách nhiệm.

Giữ script và test data version trong source control. Khi so sánh hai lần chạy, chỉ thay đổi một nhóm biến tại một thời điểm để biết nguyên nhân của chênh lệch.

## 11. Ví dụ k6: ramp-up, steady-state và threshold

Ví dụ dưới đây gửi request tới API catalog, tăng tải từ thấp lên 300 virtual users, giữ tải rồi giảm dần. Thay URL, endpoint path và threshold theo SLO thực tế.

~~~javascript
import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  stages: [
    { duration: "2m", target: 50 },
    { duration: "3m", target: 150 },
    { duration: "10m", target: 150 },
    { duration: "3m", target: 300 },
    { duration: "5m", target: 300 },
    { duration: "2m", target: 0 }
  ],
  thresholds: {
    http_req_failed: ["rate<0.005"],
    http_req_duration: ["p(95)<250", "p(99)<700"],
    checks: ["rate>0.995"]
  }
};

export default function () {
  const response = http.get(
    __ENV.BASE_URL + "/catalog",
    {
      headers: {
        "X-Test-Run": __ENV.TEST_RUN_ID || "load-test"
      },
      tags: { journey: "catalog" }
    }
  );

  check(response, {
    "status is 200": (r) => r.status === 200,
    "body is not empty": (r) => r.body && r.body.length > 0
  });

  sleep(1);
}
~~~

Chạy:

~~~bash
BASE_URL=https://test.example.internal \
TEST_RUN_ID=release-2026-11-20 \
k6 run catalog-load.js
~~~

Threshold trong k6 quyết định test pass/fail dựa trên metric tổng hợp. sleep(1) tạo think time; nếu cần arrival rate cố định, hãy dùng executor kiểu constant-arrival-rate hoặc ramping-arrival-rate thay vì chỉ tăng số VU.

## 12. Xác định capacity bằng benchmark từng thành phần

Trước khi test toàn hệ thống, benchmark các thành phần có ảnh hưởng lớn:

- API/application server.
- Database read/write path.
- Cache hit/miss.
- Queue producer/consumer.
- External API hoặc service quota.
- Serialization, compression và TLS.
- Storage throughput và IOPS.

Mục tiêu là tìm throughput bền vững của từng thành phần trong khi vẫn đạt SLO. Không lấy throughput tối đa khi latency đã tăng mạnh hoặc error rate đã vượt ngưỡng làm capacity production.

Ví dụ một ECS task xử lý ổn định 120 request/second với p95 dưới 250 ms và error rate dưới 0,1%. Nếu ở 150 request/second latency tăng lên 1,2 giây, capacity an toàn nên được tính từ vùng 120 hoặc thấp hơn theo headroom đã chọn.

## 13. Ước lượng số instance/task cần thiết

Một ước lượng ban đầu:

\[
N = \left\lceil \frac{\lambda_{peak} \times (1 + H)}{C_{safe}} \right\rceil
\]

Trong đó:

- \(\lambda_{peak}\): peak request rate dự kiến.
- \(H\): tỷ lệ headroom.
- \(C_{safe}\): throughput bền vững của một instance/task vẫn đáp ứng SLO.
- \(N\): số instance/task cần thiết ở mức peak.

Ví dụ:

- Peak demand: 900 request/second.
- Headroom: 25%.
- Benchmark an toàn: 90 request/second/task.

\[
N = \left\lceil \frac{900 \times 1.25}{90} \right\rceil
  = \lceil 12.5 \rceil = 13
\]

Có thể đặt ECS service minCapacity=3, desiredCapacity=3, maxCapacity=16, sau đó xác minh autoscaling đạt ít nhất 13 task khi tải peak. Cần tính thêm khả năng mất một AZ, quota Fargate/EC2, subnet IP, database connection và capacity của dependency.

Đây là mô hình capacity planning ban đầu. Nếu request có nhiều loại với chi phí CPU/I/O khác nhau, nên tính theo workload mix và benchmark user journey thay vì một RPS trung bình.

## 14. Chọn metric phù hợp cho autoscaling

Metric scaling phải phản ánh mức bận của scalable target và thay đổi có quan hệ hợp lý với capacity.

| Workload | Metric có thể dùng | Lưu ý |
|---|---|---|
| EC2 Auto Scaling Group | ASGAverageCPUUtilization | Phù hợp khi CPU tăng theo traffic |
| EC2 ASG sau ALB | ALBRequestCountPerTarget | Đo request trên mỗi target, không phải tổng request của load balancer |
| ECS service | ECSServiceAverageCPUUtilization | CPU trung bình của task |
| ECS service | ECSServiceAverageMemoryUtilization | Hữu ích nếu memory là giới hạn chính |
| ECS service sau ALB | ALBRequestCountPerTarget | Target là request trung bình trên mỗi task |
| Lambda | LambdaProvisionedConcurrencyUtilization cho target tracking provisioned concurrency; ConcurrentExecutions và Throttles để quan sát | Kiểm tra concurrency quota, request rate, duration và cold start |
| DynamoDB provisioned | Read/Write capacity utilization | Kiểm tra partition-level throttling và burst behavior |
| Queue workers | Backlog per worker/task | Queue depth đơn thuần có thể không tỷ lệ thuận với số worker |

Với target tracking, metric nên giảm khi capacity tăng. Ví dụ, khi số ECS task tăng gấp đôi, request count trên mỗi task thường giảm tương ứng nếu workload được phân phối đều. Tổng RequestCount của ALB không giảm khi thêm target, nên không dùng metric tổng này để target tracking EC2 ASG.

Latency và error rate vẫn là SLI quan trọng, nhưng thường nên dùng để đánh giá SLO/alarms và điều tra bottleneck thay vì dùng trực tiếp làm target tracking metric nếu chúng không thay đổi tỷ lệ thuận với capacity.

## 15. Các kiểu autoscaling trên AWS

| Kiểu scaling | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Target tracking | Duy trì metric gần target value | Workload biến động liên tục |
| Step scaling | Áp dụng mức tăng/giảm khác nhau theo độ lệch khỏi alarm | Cần kiểm soát adjustment theo mức quá tải |
| Scheduled scaling | Đặt min/max/desired capacity theo lịch | Có peak theo giờ/ngày đã biết |
| Predictive scaling | Dự báo nhu cầu từ lịch sử và chuẩn bị capacity trước | Workload có pattern lặp lại |
| Simple scaling | Thay đổi capacity theo alarm và cooldown | Hệ thống cũ hoặc yêu cầu đơn giản; thường ưu tiên target/step hơn |

Target tracking thường là điểm bắt đầu tốt cho ECS service và EC2 ASG. Scheduled hoặc predictive scaling có thể chuẩn bị capacity trước giờ cao điểm; dynamic scaling xử lý sai lệch thực tế.

Không bật nhiều policy cùng điều khiển một metric theo cách xung đột. Với ECS, nhiều target tracking policies có thể cùng tồn tại nếu dùng metric khác nhau: scale-out xảy ra khi bất kỳ policy nào yêu cầu; scale-in chỉ xảy ra khi tất cả policy có scale-in bật đều cho phép. https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-autoscaling-targettracking.html

## 16. Target tracking cho EC2 Auto Scaling

EC2 Auto Scaling hỗ trợ predefined metrics như:

- ASGAverageCPUUtilization.
- ASGAverageCPUUtilizationHighResolution.
- ASGAverageNetworkIn.
- ASGAverageNetworkOut.
- ALBRequestCountPerTarget.

Với custom metric, cần đảm bảo metric phản ánh utilization của mỗi đơn vị capacity. Dùng metric interval một phút hoặc nhanh hơn nếu service hỗ trợ và workload cần phản ứng nhanh. EC2 basic monitoring thường có chu kỳ 5 phút; detailed monitoring cung cấp chu kỳ 1 phút.

Target tracking tự tạo và quản lý CloudWatch alarms liên quan. Không sửa hoặc xóa các alarm do scaling policy quản lý trực tiếp; thay đổi policy qua Auto Scaling API/console.

## 17. Target tracking cho ECS service

ECS Service Auto Scaling điều chỉnh desired task count thông qua Application Auto Scaling.

Metric phổ biến:

- ECSServiceAverageCPUUtilization.
- ECSServiceAverageMemoryUtilization.
- ALBRequestCountPerTarget.

Ví dụ đăng ký scalable target và policy CPU target tracking:

~~~bash
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/production-cluster/catalog-api \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 3 \
  --max-capacity 16
~~~

~~~bash
aws application-autoscaling put-scaling-policy \
  --policy-name catalog-cpu-target-55 \
  --service-namespace ecs \
  --resource-id service/production-cluster/catalog-api \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 55.0,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
    },
    "ScaleOutCooldown": 60,
    "ScaleInCooldown": 180,
    "DisableScaleIn": false
  }'
~~~

Target 55% chỉ là ví dụ. Chọn target từ benchmark, thời gian khởi động task và headroom cần thiết. Kiểm tra ECS service events, task placement, Fargate/EC2 capacity và subnet IP khi scale-out.

## 18. Scale-out delay: vì sao instance mới chưa phục vụ ngay?

Scale-out gồm nhiều giai đoạn:

1. Metric được thu thập và alarm/policy đánh giá.
2. Scaling service cập nhật desired capacity.
3. EC2/Fargate capacity được cấp.
4. Instance/task khởi động, pull image và chạy bootstrap.
5. Ứng dụng load model/cache/configuration.
6. Health check pass.
7. Target được đăng ký và bắt đầu nhận traffic.

Tổng thời gian này là scale-out delay. Nếu ứng dụng cần 4 phút để khởi động, policy chỉ phản ứng sau khi CPU vượt target thì có thể quá muộn cho spike kéo dài 1 phút.

Giải pháp:

- Duy trì min capacity đủ cho baseline và burst đầu tiên.
- Dùng scheduled/predictive scaling khi peak có thể dự báo.
- Giảm image size và startup work.
- Preload cache hoặc model artifact khi phù hợp.
- Chọn metric sớm hơn điểm bão hòa.
- Dùng queue để hấp thụ burst nếu latency cho phép.
- Kiểm tra warm pool hoặc provisioned capacity khi workload cần.

## 19. Phân biệt instance warmup, health-check grace period và cooldown

Ba khái niệm thường bị nhầm:

| Cấu hình | Mục đích |
|---|---|
| Default instance warmup | Khoảng thời gian instance mới cần ổn định trước khi đóng góp vào aggregated metrics và cho phép scale-in dynamic |
| Health check grace period | Tránh đánh dấu instance mới unhealthy quá sớm khi ứng dụng còn khởi tạo |
| Cooldown | Chủ yếu điều tiết các scaling activity của simple scaling policy giữa các lần thay đổi capacity |

EC2 Auto Scaling khuyến nghị cấu hình default instance warmup cho target tracking và step scaling. Giá trị cần đo từ thời gian khởi động thực tế; 300 giây có thể dùng làm điểm bắt đầu khi chưa có dữ liệu, không phải giá trị đúng cho mọi ứng dụng.

Health check grace period mặc định khác nhau theo cách tạo ASG: console thường đặt 300 giây, CLI/SDK mặc định 0 giây. Không đặt grace period quá dài vì có thể trì hoãn thay thế instance thực sự lỗi.

Target tracking và step scaling không cần chờ simple scaling cooldown trước khi scale-out; chúng dùng instance warmup để tránh phản ứng quá mức. Simple scaling thường không phải lựa chọn ưu tiên cho hệ thống mới.

## 20. Scale-in an toàn

Scale-in có thể gây gián đoạn nếu chọn nhầm instance/task đang xử lý request dài hoặc có state cục bộ.

Kiểm tra:

- ALB deregistration delay/connection draining.
- ECS deployment/termination behavior.
- Graceful shutdown và signal handling của ứng dụng.
- Queue visibility timeout và message acknowledgment.
- Lifecycle hooks nếu cần hoàn tất công việc trước khi terminate.
- Session/state externalization vào cache/database.
- Scale-in protection nếu có instance đặc biệt cần giữ.

Scale-in thường nên chậm hơn scale-out để tránh dao động liên tục. Sau khi traffic giảm, quan sát latency, error rate và queue backlog trước khi kết luận capacity có thể thu hẹp.

## 21. Kiểm thử autoscaling theo từng pha

Một kịch bản kiểm thử có thể gồm:

| Pha | Tải | Hành vi mong đợi |
|---|---|---|
| Baseline | 20% peak | Min capacity phục vụ ổn định |
| Ramp-up | Tăng dần lên 100% peak | Scale-out bắt đầu trước khi SLO vi phạm kéo dài |
| Steady state | Giữ peak 20–30 phút | Capacity ổn định, p95/p99 và errors trong ngưỡng |
| Spike | Tăng nhanh lên 150% peak | Không mất toàn bộ service; queue/overload được kiểm soát |
| Ramp-down | Giảm về 20% peak | Scale-in không gây lỗi hoặc giảm availability |
| Idle | Không có traffic | Capacity về min theo policy |
| Repeat | Lặp lại 2–3 chu kỳ | Không có resource leak hoặc scaling oscillation |

Ghi lại thời điểm load bắt đầu, metric vượt target, scaling activity, task/instance ready, traffic được phân phối và SLO trở lại bình thường. Những timestamp này giúp tính scale-out delay thực tế.

## 22. Kiểm chứng autoscaling bằng bằng chứng

Đừng chỉ nhìn số lượng instance trong console. Cần ghép các nguồn dữ liệu:

- CloudWatch metrics của ứng dụng và hạ tầng.
- CloudWatch alarms và scaling activity history.
- EC2 Auto Scaling activity history hoặc ECS service events.
- ALB target health và request distribution.
- Test runner metrics: actual RPS, VUs, dropped iterations.
- Application logs, distributed traces và database metrics.
- Service Quotas và throttling metrics.

Một lần test pass cần chứng minh:

1. Tải thực tế đạt mức đã định nghĩa.
2. SLO được đáp ứng trong giai đoạn steady-state.
3. Scale-out diễn ra trong thời gian mục tiêu.
4. Instance/task mới thực sự healthy và nhận traffic.
5. Không có bottleneck mới ở database, queue hoặc downstream.
6. Scale-in không làm tăng lỗi hoặc latency bất thường.
7. Capacity sau test trở về min/desired phù hợp.

## 23. CloudWatch metrics theo từng lớp

| Lớp | Metric nên quan sát | Tín hiệu cần chú ý |
|---|---|---|
| ALB | RequestCount, TargetResponseTime, HTTPCode_Target_5XX_Count, HealthyHostCount, TargetConnectionErrorCount | Target chậm, unhealthy hoặc lỗi kết nối |
| EC2 | CPUUtilization, NetworkIn, NetworkOut, EBS IOPS/throughput | CPU/network/storage saturation |
| ECS | CPUUtilization, MemoryUtilization, RunningTaskCount, task placement failures | Task thiếu CPU/memory hoặc không đặt được task |
| Lambda | Invocations, Duration, Errors, Throttles, ConcurrentExecutions, ProvisionedConcurrencyUtilization | Concurrency/requests-per-second quota và cold start |
| API Gateway | Count, Latency, IntegrationLatency, 4XXError, 5XXError | Throttling hoặc integration backend chậm |
| RDS/Aurora | CPUUtilization, DatabaseConnections, read/write latency, IOPS và free storage | DB trở thành bottleneck |
| DynamoDB | ConsumedRead/WriteCapacityUnits, Read/WriteThrottleEvents, latency | Partition hot spot hoặc throughput limit |
| SQS | ApproximateNumberOfMessagesVisible, ApproximateAgeOfOldestMessage, in-flight messages | Consumer không xử lý kịp producer |

Metric và dimension cụ thể tùy dịch vụ, engine, Region và chế độ monitoring. Dùng percentile statistics cho latency khi metric hỗ trợ; average có thể che giấu tail latency.

## 24. Đọc latency percentile đúng cách

Latency trung bình có thể thấp dù một phần nhỏ request rất chậm. Ví dụ:

- p50 = 80 ms: một nửa request hoàn thành trong 80 ms hoặc nhanh hơn.
- p95 = 240 ms: 95% request hoàn thành trong 240 ms hoặc nhanh hơn.
- p99 = 900 ms: 1% request chậm hơn 900 ms.

Nếu API có 1 triệu request/ngày, p99 đại diện khoảng 10.000 request chậm hơn ngưỡng p99. Đây có thể là trải nghiệm đáng kể với người dùng.

Theo dõi latency theo endpoint, status code, request size, tenant và dependency. Không gộp health check, static content và checkout vào cùng một percentile nếu các journey có yêu cầu khác nhau.

## 25. Kiểm thử Lambda concurrency và throttling

Lambda on-demand tự động mở rộng execution environments nhưng vẫn chịu concurrency quota, requests-per-second quota và tốc độ tăng concurrency. Application Auto Scaling có thể điều chỉnh provisioned concurrency theo metric utilization. Vì vậy, một test cần theo dõi cả concurrency lẫn RPS; không nhầm metric quan sát như ConcurrentExecutions/Throttles với predefined target-tracking metric cho provisioned concurrency.

Ước lượng concurrency:

\[
\text{Concurrency} \approx \text{RPS} \times \text{Average Duration (seconds)}
\]

Ví dụ 400 RPS với duration trung bình 0,25 giây cần khoảng 100 concurrent executions. Nếu duration tăng lên 1 giây, cùng RPS cần khoảng 400 concurrency.

Kiểm tra:

- Account concurrency quota và reserved concurrency.
- Provisioned concurrency nếu cần giảm cold start.
- Throttles và concurrent executions.
- Duration p95/p99 và memory utilization.
- Event source mapping batch size, maximum concurrency và queue age.
- Downstream database/API có chịu được concurrency tăng không.

Không tăng concurrency Lambda mà không kiểm tra connection pool của RDS hoặc quota của API bên ngoài. Lambda scale nhanh có thể làm dependency quá tải trước khi Lambda đạt giới hạn.

## 26. Kiểm thử queue và worker autoscaling

Với workload bất đồng bộ, queue giúp hấp thụ burst nhưng không loại bỏ giới hạn capacity.

Theo dõi:

- ApproximateNumberOfMessagesVisible.
- ApproximateAgeOfOldestMessage.
- Number of messages received/deleted.
- Worker concurrency/task count.
- Processing duration và retry rate.
- Dead-letter queue depth.

Một metric hữu ích cho worker scaling là backlog trên mỗi worker:

\[
\text{Backlog per worker} =
\frac{\text{Visible messages}}{\max(\text{Active workers}, 1)}
\]

Queue depth tổng có thể không phù hợp làm target tracking metric vì nó không tự giảm tỷ lệ khi số worker tăng. Có thể dùng metric backlog-per-worker hoặc step scaling dựa trên queue age/depth.

Test cả trường hợp producer dừng nhưng backlog còn lớn để xác minh hệ thống drain queue và scale-in sau khi xử lý xong.

## 27. Kiểm thử database và giới hạn downstream

Autoscaling application tier có thể làm database quá tải. Khi số task tăng, số connection cũng có thể tăng theo.

Ví dụ:

- 10 ECS tasks × 30 database connections/task = 300 connections.
- Scale lên 25 tasks có thể tạo 750 connections.
- Nếu database chỉ hỗ trợ an toàn 500 connections cho workload này, application scale-out có thể khiến database từ chối kết nối.

Kiểm tra:

- Connection pool size và connection reuse.
- Query latency, lock wait, deadlock và slow query.
- Read/write IOPS, throughput và storage latency.
- CPU, memory và database connection count.
- Read replica lag và failover time.
- Cache hit ratio và hot key.
- Retry storm khi database chậm.

Giới hạn max task/instance phải tương thích với capacity của database. Cân nhắc RDS Proxy, caching, read replicas, queue hoặc giới hạn concurrency ở application tier.

## 28. Kiểm tra service quotas trước capacity test

Service quota có thể là giới hạn thật trước khi compute hoặc application đạt saturation.

Kiểm tra quota cho:

- EC2 instance vCPU theo family và Region.
- Fargate vCPU, ECS tasks và ENI/subnet IP.
- Lambda concurrency và request rate.
- API Gateway throttling.
- NAT Gateway connections/throughput.
- ALB target count và connection behavior.
- RDS database connections/storage/IOPS.
- DynamoDB throughput và partition behavior.
- Kinesis shards/throughput hoặc on-demand limits.
- SQS API throughput và message size.

Nếu cần tăng quota, gửi yêu cầu trước test đủ sớm để được xử lý. Một lần test bị throttling do quota không đồng nghĩa application code đã đạt breaking point.

## 29. Kiểm tra resilience khi đang chịu tải

Autoscaling không thay thế high availability. Kiểm thử khả năng chịu lỗi trong điều kiện tải giúp phát hiện capacity reserve chưa đủ.

Các kịch bản:

- Một EC2 instance hoặc ECS task bị terminate.
- Một Availability Zone không thể nhận traffic.
- Một database reader failover.
- Cache node restart hoặc mất kết nối.
- Queue consumer bị dừng.
- Downstream API trả lỗi hoặc tăng latency.
- Load generator hoặc một Region tạo tải bị gián đoạn.

Theo dõi SLO trong và sau lỗi, thời gian phát hiện, thời gian phục hồi, queue backlog và số lần retry. Chỉ chạy fault injection trên môi trường được phê duyệt và có rollback/stop condition.

AWS Fault Injection Service có thể giúp thực hiện controlled experiments trên tài nguyên được hỗ trợ. Dùng nó để kiểm tra resilience hypothesis; load generator vẫn cần tạo workload phù hợp để mô phỏng áp lực thật.

## 30. Test trong CI/CD và so sánh regression

Không phải mọi commit đều cần chạy một bài load test hàng giờ. Có thể phân tầng:

| Giai đoạn pipeline | Test | Thời gian tham khảo |
|---|---|---|
| Pull request | Smoke/performance sanity trên endpoint chính | Vài phút |
| Pre-release | Load test theo workload đại diện | 10–30 phút |
| Release candidate | Capacity/spike/scale-out test | 30–90 phút |
| Định kỳ | Soak và multi-AZ resilience test | Vài giờ |
| Trước event lớn | Peak forecast, quota và recovery game day | Theo kế hoạch |

Lưu baseline cho p50/p95/p99, RPS, error rate, CPU/memory và scale-out delay. So sánh theo cùng môi trường, data set và test profile.

Một regression có thể được xác định khi p95 tăng hơn ngưỡng cho phép, error rate vượt SLO hoặc throughput an toàn giảm đáng kể. Không kết luận regression từ một lần chạy đơn lẻ nếu test environment có biến động; lặp lại và xem confidence/variance.

## 31. Đọc kết quả và tìm bottleneck

Khi SLO không đạt, tìm bottleneck theo thứ tự từ ngoài vào trong:

1. Load generator có tạo đủ RPS không?
2. DNS/TLS/load balancer có gây latency không?
3. Ứng dụng có CPU, memory, thread hoặc connection pool saturation không?
4. Database/cache có lock, IOPS hoặc connection bottleneck không?
5. Queue có backlog tăng liên tục không?
6. External API có throttle hoặc latency cao không?
7. Autoscaling có khởi động đúng lúc và đủ nhanh không?
8. Quota hoặc subnet IP có ngăn capacity mới được tạo không?

Dùng distributed tracing để phân rã thời gian request theo dependency. Một API p95 900 ms có thể bao gồm 80 ms ở gateway, 120 ms ở application, 600 ms ở database và 100 ms ở external API. Scale application tier không giải quyết database query chậm.

## 32. Troubleshooting autoscaling thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| CPU cao nhưng không scale | Policy không gắn đúng scalable target, metric/alarm thiếu dữ liệu hoặc max capacity đã đạt | Kiểm tra policy, CloudWatch alarm, desired/max capacity và scaling activities |
| Scale-out bắt đầu quá muộn | Metric interval dài, threshold quá cao hoặc warmup/boot time lớn | Dùng metric sớm hơn, giảm startup time, scheduled/predictive scaling |
| Instance mới unhealthy | Grace period quá ngắn, app khởi động chậm hoặc health check sai | Đo startup time, sửa health check và grace period |
| Instance tăng nhưng latency không giảm | Database, cache, network hoặc downstream là bottleneck | Dùng traces và dependency metrics để xác định giới hạn |
| Task không được placement | Fargate/EC2 capacity, subnet IP, CPU/memory hoặc quota thiếu | Kiểm tra ECS events, capacity provider, ENI và quota |
| Scale-out liên tục nhiều lần | Warmup không phù hợp, metric nhiễu hoặc policy xung đột | Cấu hình default instance warmup, smoothing và policy nhất quán |
| Scale-in làm request lỗi | Connection draining/graceful shutdown không đúng | Sửa deregistration delay, SIGTERM handling và task shutdown |
| Không scale-in khi tải thấp | Min capacity cao, alarm không về OK, scale-in disabled hoặc policy khác còn yêu cầu capacity | Kiểm tra tất cả policy và min/max capacity |
| Lambda bị throttle | Concurrency/RPS quota hoặc reserved concurrency thấp | Xem Throttles, ConcurrentExecutions và Service Quotas |
| Queue age tăng dù worker tăng | Worker xử lý chậm, poison messages hoặc downstream throttle | Kiểm tra processing duration, DLQ và downstream capacity |
| ALB p95 tăng nhưng CPU thấp | Network, connection, target response hoặc database chậm | Xem TargetResponseTime, TargetConnectionErrorCount và tracing |
| Test RPS thấp hơn mục tiêu | Generator cạn CPU/network hoặc closed model tự giảm tốc | Phân tán generator, kiểm tra dropped iterations và dùng open model |

## 33. Mẫu báo cáo capacity và autoscaling

Mỗi lần test nên lưu:

| Trường | Giá trị cần ghi |
|---|---|
| Test ID / commit | Mã test và phiên bản ứng dụng |
| Environment | Account, Region, AZ, cấu hình hạ tầng |
| Workload | User journey, request mix, data volume, open/closed model |
| Load profile | Ramp-up, steady, spike, ramp-down và duration |
| Peak achieved | RPS, concurrency và số request thành công |
| Latency | p50, p90, p95, p99 theo journey |
| Errors | HTTP 4xx/5xx, timeout, application errors, throttles |
| Capacity | Min/desired/max, số task/instance và database connections |
| Scaling | Trigger time, scale-out delay, scale-in delay, warmup |
| Bottlenecks | Thành phần giới hạn và bằng chứng |
| Cost | Compute, database, load generator, logs và data transfer |
| Decision | Pass/fail, capacity được khuyến nghị và việc cần làm |

Lưu dashboard, raw test output, application logs, trace IDs và scaling activity history để có thể tái lập kết luận.

## 34. Ví dụ end-to-end: kiểm chứng ECS service autoscaling

Một API catalog chạy trên ECS Fargate sau Application Load Balancer. Benchmark cho thấy mỗi task xử lý an toàn 90 RPS ở p95 dưới 250 ms. Peak demand dự kiến 900 RPS, headroom 25%, nên capacity planning đề xuất 13 task. Service có min 3, max 16 task và target tracking CPU 55%.

### Kịch bản

1. Chạy smoke test ở 20 RPS để xác nhận script và test data.
2. Tăng tải theo các bậc 100, 300, 600, 900 RPS.
3. Giữ 900 RPS trong 20 phút.
4. Tạo spike lên 1.200 RPS trong 2 phút.
5. Giảm tải về 100 RPS rồi về 0.
6. Lặp lại chu kỳ để xem scaling có dao động không.

### Dashboard

- Load generator: actual RPS, VUs, dropped iterations.
- ALB: RequestCount, TargetResponseTime p95/p99, HealthyHostCount, target 5xx.
- ECS: CPUUtilization, MemoryUtilization, RunningTaskCount, service events.
- Application: request duration, thread/connection pool, errors.
- Database: CPU, connections, read/write latency và query waits.
- Application Auto Scaling: scaling activities và desired task count.

### Tiêu chí pass

- 900 RPS trong 20 phút, p95 dưới 250 ms, p99 dưới 700 ms.
- Error rate dưới 0,5%.
- Service scale lên tối thiểu 13 task trước khi SLO bị vi phạm kéo dài.
- Tất cả task mới healthy và nhận traffic qua ALB.
- Spike 1.200 RPS không làm mất toàn bộ khả năng phục vụ; nếu SLO bị vượt tạm thời, thời gian phục hồi nằm trong mục tiêu đã thống nhất.
- Sau ramp-down, service scale về min 3 task mà không làm tăng 5xx hoặc mất request.
- Database và downstream vẫn nằm trong capacity an toàn.

Nếu CPU thấp nhưng latency cao, không tiếp tục tăng task theo cảm tính. Dùng tracing và database metrics để xác định bottleneck. Nếu target tracking phản ứng quá chậm, xem lại metric, target value, metric interval, task startup và scheduled scaling.

~~~mermaid
flowchart TD
    A[Define SLO and workload] --> B[Build production-like environment]
    B --> C[Benchmark each dependency]
    C --> D[Estimate safe capacity]
    D --> E[Configure autoscaling and warmup]
    E --> F[Generate distributed load]
    F --> G[Observe app, ALB, compute and database]
    G --> H{SLO and scaling pass?}
    H -->|No| I[Find bottleneck and tune]
    I --> F
    H -->|Yes| J[Save baseline and capacity report]
~~~

## 35. Checklist trước khi xác nhận production capacity

- [ ] SLO cho throughput, latency, error rate và recovery được thống nhất.
- [ ] Workload mix đại diện cho user journey thật.
- [ ] Chọn open/closed model phù hợp và ghi actual arrival rate.
- [ ] Môi trường test đủ giống production.
- [ ] Test data đã synthetic hoặc sanitized.
- [ ] Load generator không phải bottleneck.
- [ ] Đã kiểm tra service quotas, subnet IP và dependency limits.
- [ ] Đã benchmark sustainable capacity của từng thành phần.
- [ ] Có headroom và capacity dự phòng khi mất một AZ/instance.
- [ ] Autoscaling metric tỷ lệ phù hợp với capacity.
- [ ] Min/max capacity, target value và scaling policies được kiểm tra.
- [ ] Default instance warmup và health check grace period dựa trên số đo.
- [ ] Scale-out và scale-in đều được kiểm thử.
- [ ] CloudWatch dashboard/alarms bao phủ ALB, compute, database, queue và Lambda.
- [ ] Có kiểm tra throttling, backlog, 5xx và tail latency.
- [ ] Có test spike, soak và failure scenario phù hợp.
- [ ] Có điều kiện dừng và người theo dõi test.
- [ ] Kết quả có raw artifacts, scaling history và report.
- [ ] Chi phí test và chi phí peak capacity được ước lượng.
- [ ] Có baseline và ngưỡng regression cho các lần release sau.

## 36. Ghi nhớ

Load test xác minh ứng dụng đáp ứng workload dự kiến; capacity test xác định throughput bền vững và giới hạn; autoscaling test chứng minh hệ thống bổ sung và thu hẹp capacity đúng lúc. Một kết quả tốt phải dựa trên SLO, user journey thực tế, dữ liệu an toàn và môi trường production-like.

Capacity cần được tính từ benchmark trong vùng còn đáp ứng SLO, có headroom và dự phòng cho dependency/AZ. Metric autoscaling phải phản ánh utilization của scalable target; target tracking thường phù hợp cho workload biến động, còn scheduled/predictive scaling giúp chuẩn bị trước peak. Instance warmup, health-check grace period và cooldown giải quyết các vấn đề khác nhau, cần được cấu hình từ thời gian khởi tạo và hành vi thực tế.

CloudWatch, ALB metrics, ECS/EC2/Lambda metrics, database telemetry, queue age và load generator output phải được đọc cùng nhau. Khi scale-out không cải thiện latency, hãy tìm bottleneck ở dependency hoặc quota trước khi tăng thêm compute. Lưu baseline, báo cáo capacity và scaling activity để biến kiểm thử thành một phần lặp lại được của quy trình phát hành.

## Tài liệu tham khảo

- [AWS Well-Architected: Load Test Your Workload](https://docs.aws.amazon.com/wellarchitected/2024-06-27/framework/perf_process_culture_load_test.html)
- [AWS Well-Architected: Test Scaling and Performance Requirements](https://docs.aws.amazon.com/wellarchitected/2024-06-27/framework/rel_testing_resiliency_test_non_functional.html)
- [Distributed Load Testing on AWS](https://docs.aws.amazon.com/solutions/latest/distributed-load-testing-on-aws/solution-overview.html)
- [Distributed Load Testing on AWS Features](https://docs.aws.amazon.com/solutions/latest/distributed-load-testing-on-aws/features.html)
- [AWS Prescriptive Guidance: Load Testing Tools](https://docs.aws.amazon.com/prescriptive-guidance/latest/load-testing/tools.html)
- [Target Tracking for Amazon EC2 Auto Scaling](https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-scaling-target-tracking.html)
- [Default Instance Warmup for EC2 Auto Scaling](https://docs.aws.amazon.com/autoscaling/ec2/userguide/ec2-auto-scaling-default-instance-warmup.html)
- [EC2 Auto Scaling Cooldowns](https://docs.aws.amazon.com/autoscaling/ec2/userguide/ec2-auto-scaling-scaling-cooldowns.html)
- [EC2 Auto Scaling Health Check Grace Period](https://docs.aws.amazon.com/autoscaling/ec2/userguide/health-check-grace-period.html)
- [Step and Simple Scaling Policies](https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-scaling-simple-step.html)
- [Application Auto Scaling Target Tracking](https://docs.aws.amazon.com/autoscaling/application/userguide/application-auto-scaling-target-tracking.html)
- [How Target Tracking Scaling Works](https://docs.aws.amazon.com/autoscaling/application/userguide/target-tracking-scaling-policy-overview.html)
- [Create a Target Tracking Policy for ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/target-tracking-create-policy.html)
- [ECS Service Auto Scaling Target Tracking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-autoscaling-targettracking.html)
- [ECS Service Utilization Metrics](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service_utilization.html)
- [CloudWatch Metrics for Application Load Balancers](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-cloudwatch-metrics.html)
- [Lambda Scaling Behavior](https://docs.aws.amazon.com/lambda/latest/dg/scaling-behavior.html)
- [Understanding Lambda Concurrency](https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html)
- [Lambda Quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)
- [Monitor Application Auto Scaling with CloudWatch](https://docs.aws.amazon.com/autoscaling/application/userguide/monitoring-cloudwatch.html)
