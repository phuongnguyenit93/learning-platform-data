# Đánh giá chi phí giữ ấm và capacity dự phòng

## 1. Vì sao phải đánh giá warm capacity?

Serverless giúp không phải tự quản lý máy chủ, nhưng không có nghĩa mọi tài nguyên chỉ phát sinh chi phí khi có request. Một số cơ chế giữ sẵn capacity để giảm cold start hoặc bảo đảm khả năng phục vụ ở thời điểm tải tăng. Với AWS Lambda, cơ chế nổi bật là **Provisioned Concurrency**. Nó tạo sẵn execution environment trước khi request đến, giúp giảm độ trễ khởi tạo, nhưng phần capacity đã cấp vẫn phát sinh chi phí trong thời gian được giữ, kể cả lúc ít hoặc không có invocation.

Một quyết định giữ ấm cần trả lời hai câu hỏi cùng lúc:

- Mức latency, availability hoặc khả năng chịu burst nào cần được bảo đảm?
- Phần capacity nhàn rỗi phải trả thêm bao nhiêu và lợi ích đó có đáng giá không?

Đừng xem warm capacity là một công tắc hiệu năng. Đây là một quyết định FinOps có tác động đến SLO, concurrency, chi phí compute, database connections, quota và khả năng scale.

Trong module CLOUD_SERVERLESS, người học cần hiểu cách Java function được kích hoạt bởi HTTP, message hoặc event; cách runtime khởi tạo; cách concurrency tăng giảm; và cách chọn FaaS khi cân bằng cold start, capacity dự phòng và chi phí.

## 2. Phân biệt các khái niệm capacity

Các thuật ngữ gần nhau nhưng giải quyết những vấn đề khác nhau.

| Khái niệm | Mục đích | Có giữ execution environment ấm? | Tính phí capacity nhàn rỗi? |
|---|---|---|---|
| On-demand concurrency | Platform tạo environment theo nhu cầu invocation | Không bảo đảm | Không có khoản provisioned-capacity riêng |
| Provisioned Concurrency (PC) | Khởi tạo sẵn một số Lambda execution environments | Có, trong giới hạn đã cấp | Có |
| Reserved Concurrency (RC) | Đặt quota concurrency riêng cho function và giới hạn mức tối đa của function | Không | Không có phí riêng cho việc reserve concurrency |
| Account concurrency quota | Giới hạn tổng concurrency của account/Region | Không | Không phải warm capacity |
| SnapStart | Khôi phục execution environment từ snapshot để giảm initialization | Không giữ sẵn một environment cho mỗi concurrency | Có thể có phí snapshot cache/restore theo runtime và bảng giá |
| Scheduled warmer | Gọi function định kỳ với hy vọng environment được tái sử dụng | Không bảo đảm | Có chi phí invocation và side effect của lần gọi |
| Provisioned/Minimum instances ở container platform | Giữ sẵn một số instance/container | Có, tùy dịch vụ | Thường có phí khi instance nhàn rỗi, theo mô hình dịch vụ |

Hai nhầm lẫn cần tránh:

- **Reserved Concurrency không phải Provisioned Concurrency.** Reserved Concurrency giữ quota và đặt trần concurrency; nó không khởi tạo sẵn runtime, nên không tự loại bỏ cold start.
- **Provisioned Concurrency không phải giới hạn tối đa.** Nó là số environment được chuẩn bị trước. Nếu tải vượt mức đó, request có thể spill over sang on-demand capacity nếu còn concurrency khả dụng; khi ấy vẫn có thể cold start. Nếu function bị giới hạn bởi Reserved Concurrency, phần vượt trần có thể bị throttle.

## 3. Cold start và warm invocation

Cold start xảy ra khi platform cần chuẩn bị execution environment mới trước khi chạy handler. Với Java, các bước có thể gồm tải runtime, khởi tạo JVM, class loading, framework startup, dependency injection, tạo client và kết nối đến dịch vụ bên ngoài.

Warm invocation sử dụng environment đã được khởi tạo trước đó. Warm environment có thể được tái sử dụng, nhưng không nên giả định platform sẽ giữ nó vô thời hạn hoặc tái sử dụng cho mọi request.

Provisioned Concurrency tạo sẵn environment và thực hiện initialization trước khi request đến. Khi PC đủ cho tải hiện tại, request có thể được xử lý mà không phải chờ initialization thông thường. PC không loại bỏ mọi nguồn latency: handler, database, network, throttling và dependency vẫn có thể chậm.

Đo riêng:

- `Init Duration` và latency của invocation đầu tiên.
- Warm `Duration` và phân vị p50/p95/p99.
- `ProvisionedConcurrencyInvocations`.
- `ProvisionedConcurrencySpilloverInvocations`.
- `ProvisionedConcurrencyUtilization`.
- `ConcurrentExecutions`, `Throttles`, error rate và queue age.

Nếu p99 chủ yếu do database hoặc queue backlog, tăng PC có thể làm tăng chi phí mà không cải thiện trải nghiệm người dùng đáng kể.

## 4. Provisioned Concurrency hoạt động như thế nào?

Provisioned Concurrency được cấu hình trên một **published version hoặc alias** của Lambda, không cấu hình trực tiếp trên `$LATEST`. Lambda chuẩn bị số execution environment tương ứng với mức PC đã đặt.

Ví dụ:

```text
orders-function
  ├── version 41
  ├── version 42
  └── alias production -> version 42
       └── Provisioned Concurrency = 12
```

Trong ví dụ, alias `production` có 12 execution environments được chuẩn bị. Khi deploy version mới, alias có thể được chuyển sang version mới và PC cần được provision cho qualifier tương ứng. Không nên giả định PC của alias cũ tự động chuyển sang version mới.

Một số điểm vận hành:

- PC cần thời gian để chuyển sang trạng thái `READY`; cập nhật capacity không tức thời.
- Chỉ traffic đi đến qualifier được provision mới sử dụng capacity đó.
- PC có thể kết hợp với alias routing/canary, nhưng cần kiểm tra PC của từng version/alias và cách phân phối traffic.
- Nếu PC không đủ, Lambda có thể dùng on-demand concurrency còn khả dụng; các invocation spillover có thể chịu cold start.
- Nếu concurrency quota hoặc Reserved Concurrency không đủ, invocation vượt giới hạn có thể bị throttle.

Tài liệu: [AWS Lambda Provisioned Concurrency](https://docs.aws.amazon.com/lambda/latest/dg/provisioned-concurrency.html).

## 5. Reserved Concurrency khác Provisioned Concurrency ra sao?

Reserved Concurrency (RC) có hai vai trò: dành riêng một phần concurrency trong account cho function và đặt mức concurrency tối đa mà function được sử dụng. Nó giúp bảo vệ các function khác khỏi một function tăng tải không kiểm soát, đồng thời có thể bảo vệ downstream như database.

RC không tạo sẵn execution environment. Một function có RC bằng 50 vẫn có thể cold start khi có request mới.

Ví dụ:

```text
Reserved Concurrency = 30
Provisioned Concurrency = 10

Tối đa function có thể dùng: 30 concurrent invocations
Trong đó có 10 environment được chuẩn bị sẵn
Phần concurrency vượt 10 có thể dùng on-demand nếu quota còn
Phần vượt 30 bị throttle
```

PC không được lớn hơn giới hạn concurrency áp dụng cho function. Account/Region cũng phải có đủ concurrency quota để cấp PC và phục vụ các function khác.

| Trường hợp | Cấu hình phù hợp |
|---|---|
| Cần giới hạn function không được làm cạn database connection | Reserved Concurrency |
| Cần giảm cold start cho API có SLO latency nghiêm ngặt | Provisioned Concurrency hoặc SnapStart tùy workload |
| Cần bảo vệ account capacity cho function quan trọng | Reserved Concurrency |
| Cần vừa giữ một baseline ấm vừa giới hạn tổng tải | Kết hợp PC và RC |
| Chỉ cần function scale theo nhu cầu, cold start chấp nhận được | On-demand concurrency |

Không cộng RC và PC như hai pool capacity độc lập. RC là quota/trần; PC là phần environment đã được chuẩn bị trong giới hạn đó.

## 6. Các thành phần chi phí của Provisioned Concurrency

Khi bật PC, chi phí có thể gồm:

1. **Provisioned capacity charge:** tính theo memory của function, số concurrency được provision và thời gian capacity được cấu hình/duy trì.
2. **Request charge:** số invocation/request vẫn được tính theo pricing model của Lambda.
3. **Execution duration charge:** thời gian code chạy được tính theo quy tắc giá tương ứng với PC và architecture/Region.
4. **Spillover execution:** invocation vượt PC có thể chạy bằng on-demand capacity nếu còn quota; phần này có thể chịu cold start và mức giá on-demand tương ứng.
5. **Chi phí phụ trợ:** API Gateway, SQS, database, NAT/network, logs, traces, metrics, secrets và các dịch vụ được gọi.

Điểm FinOps quan trọng là **capacity charge tiếp tục phát sinh khi PC đang idle**. Nếu giữ 20 environment suốt 24 giờ để phục vụ một đỉnh tải kéo dài 30 phút, phần lớn thời gian capacity có thể không được sử dụng.

Giá cụ thể phụ thuộc Region, architecture, memory, thời điểm và loại invocation. Không dùng một đơn giá cố định từ bài viết làm dự toán; tra [AWS Lambda Pricing](https://aws.amazon.com/lambda/pricing/) và AWS Pricing Calculator tại thời điểm lập ngân sách.

## 7. Công thức ước lượng chi phí capacity nhàn rỗi

Ước lượng phần capacity charge bằng:

```text
PC capacity GB-seconds
  = memory_GB × provisioned_concurrency × provisioned_seconds

PC capacity cost
  = PC capacity GB-seconds × PC price per GB-second
```

Ví dụ giả định:

- Memory: 1 GB.
- Provisioned Concurrency: 8.
- Giữ liên tục: 8 giờ/ngày.

```text
1 GB × 8 concurrency × 8 × 3.600 seconds
= 230.400 GB-seconds mỗi ngày
```

Nếu giữ cùng mức đó 24 giờ/ngày:

```text
1 GB × 8 × 24 × 3.600
= 691.200 GB-seconds mỗi ngày
```

Đây là lượng capacity được provision, chưa phải tổng bill. Cần cộng request, execution duration, spillover và các dịch vụ phụ trợ theo pricing hiện hành. Ví dụ cho thấy lịch scale theo giờ hoạt động có thể giảm phần idle capacity đáng kể nếu traffic thực sự có tính chu kỳ.

## 8. Ước lượng concurrency từ traffic

Một ước lượng cơ bản dựa trên Little’s Law:

```text
Average concurrency ≈ arrival rate (requests/second)
                       × average execution duration (seconds)
```

Ví dụ, function nhận 60 request/giây và thời gian xử lý trung bình 120 ms:

```text
60 × 0,12 = 7,2 concurrent executions trung bình
```

Con số 7,2 không đủ để chọn PC. Traffic có thể burst, duration có phân phối dài, cold start và dependency có thể làm thời gian xử lý tăng. Cần xem phân phối theo cửa sổ ngắn, concurrency peak, p95/p99 duration, số request đồng thời và SLO.

Một cách sizing thực tế:

1. Thu thập request rate theo từng khoảng 1 giây hoặc 1 phút tùy workload.
2. Đo duration khi warm và khi dependency biến động.
3. Tính concurrency yêu cầu ở peak, không chỉ average.
4. Thêm buffer có lý do cho burst/forecast error.
5. Chạy load test và xem spillover/throttle.
6. Chọn PC baseline và cơ chế scale cho phần còn lại.

Không đặt PC bằng đúng concurrency trung bình rồi kỳ vọng không có cold start. PC là capacity sẵn sàng, không phải cam kết toàn bộ traffic sẽ luôn nằm trong capacity đó.

## 9. Sizing theo latency SLO và burst

PC phù hợp khi cold start ảnh hưởng đến một phần đáng kể của request và yêu cầu latency nghiêm ngặt. Hãy xác định:

- Tỷ lệ request có thể chấp nhận cold start.
- p95/p99 latency mục tiêu.
- Mức burst có thể đến trong một giây.
- Thời gian scale PC lên và thời gian warm-up.
- Mức concurrency dự phòng cần duy trì.
- Chi phí khi giữ capacity ngoài giờ.

Ví dụ, API có 100 RPS peak, average duration 150 ms. Average concurrency ước lượng là 15. Nếu traffic đến theo burst và p95 duration là 250 ms, mức concurrency ngắn hạn có thể cao hơn nhiều. Chọn PC 15 chỉ từ average là quá lạc quan. Hãy chạy load test với cùng pattern burst và xem `ProvisionedConcurrencySpilloverInvocations`.

Không phải request nào cũng cần PC. Có thể tách endpoint latency-critical sang function riêng, giữ PC cho function đó và để batch/reporting chạy on-demand.

## 10. Target utilization và phần capacity dự phòng

Nếu PC luôn chạy sát 100% utilization, một burst nhỏ có thể tạo spillover. Nếu PC quá cao so với tải, phần capacity idle làm tăng chi phí.

Một target utilization dưới 100% giúp giữ buffer. Ví dụ target 70% có nghĩa hệ thống cố gắng giữ PC cao hơn mức concurrency dự kiến để còn khoảng trống. Đây là mục tiêu autoscaling, không phải cam kết chính xác về latency hoặc số invocation.

Các metric nên theo dõi:

- `ProvisionedConcurrentExecutions`: số PC đang được dùng.
- `ProvisionedConcurrencyUtilization`: mức sử dụng PC.
- `ProvisionedConcurrencySpilloverInvocations`: invocation không được phục vụ bởi PC.
- `ConcurrentExecutions`: concurrency tổng.
- `Throttles`: invocation bị từ chối do quota/concurrency.
- `Duration`, `Init Duration`, p95/p99 và error rate.

Nếu utilization thấp liên tục và không có SLO benefit rõ, giảm baseline hoặc giới hạn khung giờ. Nếu spillover tăng trong giờ peak, xem lại target, schedule, max capacity và forecast.

## 11. Scale Provisioned Concurrency theo lịch

Nếu traffic có chu kỳ rõ (giờ làm việc, lịch bán hàng, thời gian batch), scheduled scaling có thể provision trước giờ peak và giảm sau khi tải kết thúc.

Ví dụ:

```text
07:30  Tăng PC từ 0 lên 12
08:00  API bắt đầu giờ cao điểm
08:00-17:30  Duy trì baseline 12, autoscale khi cần
18:00  Giảm PC về 0 hoặc mức tối thiểu
```

Phải tăng capacity đủ sớm để Lambda hoàn tất quá trình provision và đạt trạng thái `READY` trước khi traffic đến. Không đặt schedule đúng vào thời điểm peak nếu provisioning mất thời gian.

Scheduled scaling phù hợp với pattern dự đoán được. Với traffic thay đổi theo chiến dịch hoặc sự kiện bất ngờ, kết hợp target tracking hoặc giữ buffer nhỏ. Đừng scale down ngay khi traffic vừa giảm một phút; dùng cooldown/hysteresis để tránh dao động liên tục.

## 12. Autoscaling Provisioned Concurrency

Application Auto Scaling hỗ trợ target tracking và scheduled scaling cho Lambda provisioned concurrency trên alias/version phù hợp. Target tracking có thể điều chỉnh PC để duy trì mức utilization mục tiêu.

Các yếu tố cấu hình:

- Min capacity: mức PC thấp nhất, có thể bằng 0 nếu chấp nhận cold start ngoài giờ.
- Max capacity: giới hạn chi phí và concurrency.
- Target utilization: mức sử dụng mong muốn, thường thấp hơn 100% để giữ buffer.
- Scale-out cooldown: tránh scale lặp quá nhanh.
- Scale-in cooldown: tránh giảm capacity quá sớm.
- Schedule: provision trước các đợt traffic có thể dự đoán.

Autoscaling không loại bỏ hoàn toàn cold start trong burst nhanh hơn tốc độ scale. Nếu cần latency rất thấp ngay ở giây đầu của một spike, cần baseline PC đủ lớn hoặc cơ chế đệm như queue/API async.

Tài liệu: [Application Auto Scaling for Lambda](https://docs.aws.amazon.com/lambda/latest/dg/provisioned-concurrency.html#application-auto-scaling).

## 13. SnapStart là phương án thay thế cho một số workload Java

SnapStart tạo snapshot của execution environment sau initialization khi publish version; các environment mới có thể được khôi phục từ snapshot để giảm thời gian startup. Nó không giữ một số lượng environment luôn sẵn sàng như PC.

| Tiêu chí | Provisioned Concurrency | SnapStart |
|---|---|---|
| Mục tiêu | Giữ sẵn execution environments | Giảm chi phí initialization khi tạo environment |
| Capacity idle | Có thể phát sinh charge khi không có request | Không phải giữ concurrency idle |
| Burst | Phục vụ trong mức PC đã provision; phần vượt có thể spillover | Có thể tạo environment từ snapshot, vẫn cần scale capacity |
| Java startup | Initialization diễn ra trước khi request đến | Restore từ snapshot thay cho khởi tạo đầy đủ |
| Phù hợp | SLO latency nghiêm ngặt, traffic dự đoán hoặc cần baseline nóng | Java cold start cao, traffic biến động, không muốn giữ PC lớn |
| Giới hạn | Cần sizing, quota và chi phí giữ capacity | Cần kiểm tra runtime support, snapshot/restore behavior và state an toàn sau restore |

SnapStart có thể phù hợp hơn nếu cold start là vấn đề chính nhưng traffic không đủ đều để trả tiền PC. Tuy nhiên, SnapStart không đảm bảo không có cold start hoặc latency bằng 0; restore và handler vẫn tốn thời gian. Kiểm tra runtime Java được hỗ trợ, version/alias, hooks và các giá trị cần khởi tạo lại sau restore.

Tài liệu: [AWS Lambda SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html).

## 14. Scheduled warmer không phải capacity guarantee

Một số hệ thống dùng EventBridge Scheduler hoặc cron để gọi function định kỳ với hy vọng giữ environment warm. Cách này có thể tạo invocation đều đặn, nhưng không đảm bảo:

- Invocation tiếp theo sẽ vào đúng environment trước đó.
- Platform không scale in hoặc thay environment.
- Mọi concurrency đều được giữ warm.
- Burst traffic sẽ không tạo environment mới.
- Warm invocation không gây side effect ngoài ý muốn.

Warmer vẫn tạo request, duration, log và có thể gọi downstream. Nếu dùng, handler phải nhận diện payload warm-up và thoát nhanh, an toàn; không chạy nghiệp vụ, không gửi message và không ghi dữ liệu production.

Không dùng warmer như một cam kết SLO. Nếu latency cần được bảo đảm, đánh giá PC hoặc SnapStart. Nếu cold start chấp nhận được, on-demand có thể rẻ hơn.

## 15. Ví dụ tính cost theo khung giờ

Giả sử một Java API cần 1 GB memory và dự kiến cần 10 concurrency trong 8 giờ làm việc. Phần còn lại trong ngày traffic thấp.

| Phương án | PC baseline | Thời gian giữ | Capacity GB-s/ngày (ước lượng) |
|---|---:|---:|---:|
| A: luôn giữ | 10 | 24 giờ | 864.000 |
| B: chỉ giờ làm việc | 10 | 8 giờ | 288.000 |
| C: baseline nhỏ | 3 | 24 giờ | 259.200 |
| D: không PC | 0 | 0 | 0 |

Các giá trị dùng công thức `memory_GB × concurrency × seconds`; chưa bao gồm execution, request, spillover và dịch vụ phụ trợ. Phương án C có thể rẻ hơn B nhưng không đủ phục vụ giờ peak; cần xét SLO và spillover. Phương án D rẻ nhất về PC nhưng có thể có cold start.

Không chọn phương án chỉ theo bảng GB-s. Đo tỷ lệ request thực sự được PC phục vụ, chi phí per successful request và tác động đến p95/p99.

## 16. Tổng chi phí và cost per successful request

Tổng chi phí của function có PC nên được tính theo cấu phần:

```text
Total cost
  = Provisioned Concurrency capacity charge
  + invocation request charge
  + execution duration charge
  + on-demand spillover cost
  + API Gateway / queue / event cost
  + database / cache / connection proxy cost
  + network / NAT / data transfer cost
  + logs / metrics / traces cost

Cost per successful request
  = total cost / successful business operations
```

Đếm invocation thành công ở Lambda không đủ nếu nghiệp vụ thất bại ở downstream hoặc bị retry. Hãy dùng số operation hoàn tất ở domain boundary.

PC có thể làm tăng tổng chi phí nhưng giảm latency tail; khi đó cần đánh giá giá trị nghiệp vụ của SLO. Ví dụ checkout p99 thấp có thể tăng conversion hoặc giảm timeout/retry. Nếu function nội bộ chạy batch không có người dùng chờ, PC có thể không mang lại lợi ích tương xứng.

## 17. Chi phí cơ hội của capacity dự phòng

Capacity dự phòng không chỉ là bill trực tiếp. Nó còn chiếm concurrency quota, account capacity và tài nguyên downstream.

Ví dụ, 40 PC cho một API có thể làm giảm phần concurrency khả dụng cho các function khác trong cùng account/Region. Một function có RC cao có thể giữ quota riêng và khiến function khác thiếu capacity. Vì vậy, capacity planning phải ở cấp account/service portfolio, không chỉ ở một Lambda.

Hãy lập inventory:

- PC theo function alias/version và môi trường.
- RC theo function.
- Account concurrency quota và mức sử dụng peak.
- Reserved capacity của database/cache/provider.
- Các lịch scale và owner chịu trách nhiệm.
- Ngày review/expiry của cấu hình capacity tạm thời.

Đặt cảnh báo khi capacity được provision nhưng không được sử dụng, khi RC không có lý do rõ hoặc khi một function chiếm tỷ lệ lớn quota account.

## 18. Bảo vệ database khi giữ ấm Lambda

PC giữ sẵn nhiều execution environment. Nếu mỗi environment khởi tạo connection pool lớn, database có thể nhận một lượng connection tăng đột ngột ngay khi provision hoặc scale-out.

Ví dụ:

```text
Provisioned Concurrency = 40
Maximum connections per environment = 10
Potential connections = 40 × 10 = 400
```

Đây là giới hạn tiềm năng nếu mỗi environment mở đủ pool; không có nghĩa mọi connection sẽ luôn được mở. Tuy vậy, phải tính cả warm environments, spillover environments, các function khác và connection của ứng dụng ngoài Lambda.

Biện pháp:

- Giữ pool nhỏ và phù hợp với concurrency thật.
- Dùng RDS Proxy hoặc connection proxy phù hợp khi workload cần.
- Tái sử dụng client/connection trong execution environment nhưng xử lý stale connection.
- Giới hạn Lambda concurrency theo khả năng database.
- Theo dõi database connection count, queueing, CPU và lock wait.
- Tránh provision nhiều function đồng thời nếu downstream chưa có capacity.

Warm capacity ở tầng compute có thể làm database quá tải nhanh hơn. PC và RC phải được thiết kế cùng capacity của dependency.

## 19. Tối ưu memory và duration khi dùng PC

PC capacity charge phụ thuộc memory và concurrency được provision. Tăng memory làm tăng capacity charge trên mỗi environment, nhưng có thể tăng CPU và giảm execution duration. Nếu function chạy nhanh hơn, concurrency cần thiết cho cùng throughput có thể giảm.

Vì vậy, hãy benchmark nhiều cấu hình memory:

- Memory thấp: PC charge thấp hơn nhưng handler có thể chạy lâu, concurrency cần cao hơn.
- Memory cao: PC charge cao hơn mỗi environment nhưng handler có thể chạy nhanh hơn và giải phóng capacity sớm hơn.
- Điểm tối ưu phụ thuộc CPU-bound/I/O-bound, JVM startup, GC, payload và downstream.

Đo cost per successful request cho từng cấu hình, không chỉ GB-second hoặc duration. Với Java, kiểm tra GC, heap, native memory và framework startup. Tối ưu code/connection reuse có thể giảm cả duration lẫn concurrency cần thiết.

## 20. Phân bổ warm capacity theo loại workload

Không phải mọi function đều cần PC.

| Workload | Hướng lựa chọn | Lý do |
|---|---|---|
| Public API có p99 nghiêm ngặt | PC baseline hoặc SnapStart; canary theo alias | Request trực tiếp chịu ảnh hưởng cold start |
| Admin API traffic thấp | On-demand hoặc SnapStart | Không đáng trả capacity idle lớn |
| Queue worker xử lý batch | On-demand + queue buffering; RC để bảo vệ downstream | Có thể chấp nhận queue delay và scale theo backlog |
| Scheduled job mỗi ngày | On-demand, SnapStart nếu startup đáng kể | Không cần giữ ấm cả ngày |
| Webhook cần phản hồi nhanh | PC cho endpoint nhận event nếu SLO yêu cầu; xử lý nghiệp vụ async | Tách acceptance latency khỏi processing latency |
| Traffic theo giờ | Scheduled PC + target tracking | Dự đoán được giờ cao điểm |
| Traffic burst không dự đoán | SnapStart/on-demand với buffer; queue nếu nghiệp vụ cho phép | PC cố định lớn có thể rất tốn kém |
| Function gọi database giới hạn connection | RC để giới hạn concurrency, PC chỉ khi latency cần | Bảo vệ downstream trước khi tối ưu cold start |

## 21. Chiến lược hybrid: baseline nóng và on-demand spillover

Một cấu hình thực tế có thể giữ một mức PC nhỏ cho traffic thường xuyên, sau đó để on-demand capacity xử lý phần tăng thêm.

Ví dụ:

```text
Traffic thường xuyên: 5-8 concurrency
Provisioned Concurrency: 10
Reserved Concurrency: 30

0-10 concurrent: ưu tiên PC
10-30 concurrent: có thể spillover sang on-demand
Trên 30: throttle
```

Mô hình này giảm chi phí so với giữ 30 PC nhưng chấp nhận cold start ở phần spillover. Nếu mọi request đều phải đáp ứng latency SLO nghiêm ngặt, phải provision đủ peak hoặc dùng cơ chế khác để hấp thụ burst.

Theo dõi spillover theo từng alias và khung giờ. Nếu spillover hiếm nhưng gây p99 violation nghiêm trọng, cân nhắc tăng PC ở khung giờ đó. Nếu spillover thường xuyên, PC baseline đang quá thấp hoặc forecast không đúng.

## 22. Khi nào nên dùng queue để thay warm capacity?

Nếu caller không cần kết quả ngay, queue có thể hấp thụ burst và cho phép worker scale theo backlog. Producer trả `202 Accepted` sau khi lưu/publish event; worker xử lý khi có capacity.

Queue không thay thế PC trong mọi trường hợp. Nó đổi mục tiêu từ latency đồng bộ sang processing SLA. Cần kiểm soát:

- `ApproximateAgeOfOldestMessage` hoặc event age.
- Queue depth và tốc độ arrival/processing.
- Lambda concurrency và batch size.
- Visibility timeout, retry, DLQ và idempotency.
- Thời hạn nghiệp vụ `expiresAt`.

Nếu worker phải hoàn tất trong vài giây, PC hoặc baseline capacity có thể vẫn cần. Nếu công việc có thể đợi vài phút, on-demand scaling thường kinh tế hơn.

## 23. Các nền tảng serverless khác

Khái niệm warm/minimum capacity cũng xuất hiện ở các nền tảng khác, nhưng cách tính phí và semantics khác nhau:

| Nền tảng | Cơ chế gần tương đương | Điều cần kiểm tra |
|---|---|---|
| AWS Lambda | Provisioned Concurrency, SnapStart | PC idle charge, version/alias, spillover, runtime support |
| Azure Functions | Always Ready / prewarmed instances tùy hosting plan | Plan, số instance tối thiểu, execution/idle billing và scale behavior |
| Google Cloud Run | Minimum instances, startup CPU boost | Instance-based/request-based billing, idle allocation và min instance setting |
| Container/serverless platforms | Minimum tasks/instances hoặc reserved capacity | Có tính phí khi idle không, scale-to-zero, startup time và quota |

Không chuyển trực tiếp công thức giá của Lambda sang Azure Functions hoặc Cloud Run. Đọc pricing model của hosting plan/Region và tính theo cấu hình thực tế.

## 24. FinOps: đặt owner, budget và review

Mỗi cấu hình warm capacity cần có lý do và owner. Một record quản lý có thể gồm:

| Field | Ví dụ |
|---|---|
| Service/function | `orders-api` |
| Environment | `production` |
| Alias/version | `production -> version 42` |
| PC min/max | 4 / 24 |
| RC | 30 |
| Schedule | 07:30–18:00 ngày làm việc |
| Target utilization | 70% |
| SLO | p99 dưới 400 ms |
| Owner | Team Orders |
| Cost center | `CC-ORDERS` |
| Review date | Hàng tháng hoặc sau peak event |

FinOps review nên kiểm tra:

- PC utilization theo giờ/ngày.
- Spillover và throttles.
- Cost per successful request.
- SLO đạt/không đạt trước và sau khi bật PC.
- Chi phí ngoài giờ và capacity không dùng.
- Downstream connection/capacity pressure.
- Forecast sai lệch và lịch scaling.

Nếu không có số liệu chứng minh PC cải thiện SLO hoặc giảm business loss, xem xét hạ baseline, schedule hoặc chuyển sang SnapStart/on-demand.

## 25. Quy trình quyết định bật Provisioned Concurrency

1. **Đo baseline:** cold start, warm latency, p95/p99, traffic profile và cost.
2. **Xác định nguồn chậm:** initialization, framework, network hay downstream.
3. **Thử tối ưu không giữ capacity:** giảm package, tối ưu initialization, tái sử dụng client, SnapStart nếu phù hợp.
4. **Xác định phần request cần warm:** route/alias nào có SLO nghiêm ngặt.
5. **Ước lượng PC:** dùng peak concurrency, burst profile và safety buffer.
6. **Đặt RC:** bảo vệ account/downstream và đặt trần tổng concurrency.
7. **Tính cost:** capacity idle, request, execution, spillover và phụ trợ.
8. **Provision trước:** chờ trạng thái `READY` trước khi chuyển traffic.
9. **Canary:** tăng traffic theo bước, theo dõi spillover, p99, error và cost.
10. **Autoscale/schedule:** đặt min/max, target, cooldown và lịch theo nhu cầu.
11. **Review:** giảm hoặc tắt PC nếu không còn SLO benefit.

## 26. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nhầm RC với PC | Function vẫn cold start dù đã reserve concurrency | Dùng PC nếu mục tiêu là giữ environment ấm |
| Giữ PC 24/7 cho traffic theo giờ | Chi phí idle cao | Scheduled scaling hoặc min capacity nhỏ |
| Đặt PC bằng average concurrency | Burst tạo spillover/cold start | Sizing theo peak và load test |
| PC bằng đúng RC | Không còn room cho spillover; vượt mức dễ throttle | Chọn RC và PC theo mục tiêu khác nhau |
| Provision trên `$LATEST` | Cấu hình không đúng qualifier | Dùng published version/alias |
| Chuyển alias trước khi PC `READY` | Traffic mới có thể cold start | Chờ provisioning hoàn tất rồi chuyển traffic |
| Dùng warmer làm SLO guarantee | Environment không được bảo đảm tái sử dụng | PC hoặc SnapStart phù hợp hơn |
| Chỉ xem Lambda cost | Bỏ sót database, network, logs và API Gateway | Tính cost per successful operation end-to-end |
| PC làm database quá tải | Connection storm và latency tăng | RC, pool nhỏ, RDS Proxy và downstream capacity plan |
| Không đo spillover | Không biết bao nhiêu request dùng on-demand | Dashboard metric PC và alert |
| Không review sau peak event | Capacity tạm trở thành chi phí cố định | Đặt expiry/review owner cho cấu hình |

## 27. Checklist trước production

- [ ] Đã xác định cold start có thực sự vi phạm SLO hay không.
- [ ] Đã phân biệt Provisioned Concurrency và Reserved Concurrency.
- [ ] PC được gắn đúng published version/alias.
- [ ] Đã tính capacity GB-seconds cho khung giờ giữ ấm.
- [ ] Đã tính request, execution, spillover và dịch vụ phụ trợ.
- [ ] Đã đo traffic peak, burst và duration distribution.
- [ ] PC có buffer phù hợp và không chỉ dựa vào average concurrency.
- [ ] RC bảo vệ function/account/downstream và không làm cạn quota vô tình.
- [ ] Có dashboard utilization, spillover, throttles, p95/p99 và cost.
- [ ] Có scheduled scaling/target tracking với min/max/cooldown rõ ràng.
- [ ] Đã chờ PC ở trạng thái `READY` trước khi chuyển traffic.
- [ ] Đã kiểm tra alias/version và canary/rollback.
- [ ] Đã so sánh SnapStart/on-demand trước khi giữ PC lớn.
- [ ] Warmers không tạo side effect và không được xem là guarantee.
- [ ] Database connection pool và downstream capacity đủ cho PC + spillover.
- [ ] Có owner, cost center, budget và ngày review.
- [ ] Đã kiểm tra giá hiện hành theo Region/architecture/runtime.

## Tài liệu tham khảo

- [AWS Lambda Provisioned Concurrency](https://docs.aws.amazon.com/lambda/latest/dg/provisioned-concurrency.html)
- [Application Auto Scaling for Lambda](https://docs.aws.amazon.com/lambda/latest/dg/provisioned-concurrency.html#application-auto-scaling)
- [AWS Lambda Reserved Concurrency](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html)
- [AWS Lambda SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html)
- [AWS Lambda pricing](https://aws.amazon.com/lambda/pricing/)
- [AWS Lambda concurrency](https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html)
- [Amazon RDS Proxy](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.html)
- [Azure Functions scale and hosting](https://learn.microsoft.com/azure/azure-functions/functions-scale)
- [Google Cloud Run minimum instances](https://cloud.google.com/run/docs/configuring/min-instances)

## Kết luận

Warm capacity giúp giảm cold start và giữ latency ổn định, nhưng tạo chi phí ngay cả khi environment nhàn rỗi. Provisioned Concurrency chuẩn bị sẵn Lambda execution environments; Reserved Concurrency chỉ giữ quota và giới hạn concurrency. Hãy sizing PC theo peak traffic và SLO, tính đủ capacity GB-seconds cùng invocation, spillover và dependency cost, rồi dùng schedule/target tracking để giảm idle capacity. Với Java, so sánh thêm SnapStart và tối ưu startup trước khi giữ PC lớn. Cuối cùng, bảo vệ database bằng RC/connection pool phù hợp và review utilization, spillover, p99 cùng cost per successful request định kỳ.
