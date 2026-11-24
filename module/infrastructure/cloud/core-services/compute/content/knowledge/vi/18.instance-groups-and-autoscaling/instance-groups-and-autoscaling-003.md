# Target tracking, step scaling và lịch co giãn

Tự động co giãn (autoscaling) điều chỉnh số lượng tài nguyên compute theo nhu cầu của workload. Khi lưu lượng tăng, hệ thống bổ sung máy ảo, container hoặc worker để giữ hiệu năng; khi nhu cầu giảm, hệ thống thu hẹp nhóm máy để tránh trả chi phí cho capacity nhàn rỗi. Muốn autoscaling hoạt động ổn định, cần chọn đúng tín hiệu tải, đặt giới hạn capacity và phối hợp thời gian khởi động, health check, cân bằng tải cùng quá trình loại bỏ instance.

Ba cách điều khiển thường gặp là **target tracking**, **step scaling** và **scheduled scaling**. Target tracking cố gắng giữ một metric quanh giá trị mục tiêu; step scaling phản ứng theo các mức độ vượt ngưỡng của cảnh báo; scheduled scaling thay đổi capacity theo lịch đã biết trước. Mỗi cách phù hợp với một kiểu nhu cầu khác nhau và có thể kết hợp nếu được thiết kế rõ ràng.

Bài học này đặt các chính sách vào bối cảnh nhóm máy trên đám mây, từ VM instance group đến container service và worker xử lý nền. Sau bài học, bạn có thể:

- Phân biệt cơ chế và trường hợp sử dụng của target tracking, step scaling và scheduled scaling.
- Chọn metric phản ánh đúng tải và năng lực của từng instance.
- Tính capacity tối thiểu, mục tiêu và giới hạn tối đa dựa trên SLO.
- Thiết kế ngưỡng, bước tăng/giảm, thời gian warm-up và cooldown.
- Kết hợp lịch co giãn với chính sách động mà không tạo ra dao động hoặc xung đột.
- Kiểm tra scale-out, scale-in, health check, draining và chi phí sau khi triển khai.

## 1. Nhóm máy và các giới hạn capacity

Một instance group hoặc autoscaling group quản lý một tập máy có cấu hình và vai trò tương tự. Bộ điều khiển có thể tạo hoặc hủy instance để đưa số lượng máy về mức mong muốn.

Ba giá trị cơ bản:

- **Minimum capacity (min):** số instance tối thiểu cần duy trì.
- **Desired capacity (desired):** số instance mà nhóm đang hướng tới.
- **Maximum capacity (max):** số instance tối đa được phép chạy.

Luôn có quan hệ:

\[
min \le desired \le max
\]

Ví dụ, một nhóm web có **min = 2**, **desired = 4**, **max = 12**. Nhóm bắt đầu với bốn instance, có thể tăng lên tối đa mười hai khi tải cao và không giảm dưới hai để giữ năng lực nền.

~~~mermaid
flowchart TD
    M["Min capacity: 2"] --> D["Desired capacity: 4"]
    D --> X["Max capacity: 12"]
    D --> P["Bộ điều khiển autoscaling"]
    P --> A["Tạo instance khi cần"]
    P --> R["Loại instance khi dư capacity"]
~~~

Các giá trị này là giới hạn và trạng thái điều khiển, không phải bằng chứng rằng ứng dụng đang đủ năng lực. Nếu mỗi instance xử lý được 50 request/giây ở SLO yêu cầu, nhóm bốn instance có thể không đủ cho 500 request/giây dù desired capacity đã đúng.

### Desired capacity thay đổi như thế nào?

Chính sách autoscaling quan sát metric hoặc lịch, sau đó yêu cầu bộ điều khiển điều chỉnh desired capacity. Nền tảng chịu trách nhiệm tạo hoặc loại instance, nhưng thời gian thực tế còn phụ thuộc quota, nguồn cung, boot image, cài đặt agent, tải ứng dụng và readiness check.

Autoscaling thường có hai hướng:

- **Scale-out:** tăng số instance để hấp thụ tải.
- **Scale-in:** giảm số instance khi tải giảm.

Scale-out quá chậm có thể khiến dịch vụ vượt SLO trước khi máy mới sẵn sàng. Scale-in quá nhanh có thể kết thúc instance đang xử lý request hoặc job. Vì vậy, chính sách cần tính tới cả tốc độ thay đổi capacity và vòng đời workload.

## 2. Chọn metric phản ánh đúng tải

Chính sách chỉ tốt khi metric đại diện cho vấn đề cần giải quyết. CPU là chỉ số phổ biến nhưng không phải workload nào cũng bị giới hạn bởi CPU.

| Loại workload | Metric có thể dùng | Khi nào hữu ích |
|---|---|---|
| Web/API | CPU utilization, request count per instance/target, concurrent requests, response time | Khi tải request làm tăng CPU, số request hoặc độ trễ |
| Worker xử lý queue | Backlog per worker, age of oldest message, job arrival rate, job completion rate | Khi hàng đợi tăng nhanh hơn khả năng xử lý |
| Batch compute | Số job chờ, thời gian hoàn thành dự kiến, số worker bận | Khi mục tiêu là xử lý hết backlog trong thời hạn |
| Memory-bound service | Memory utilization, working set, page fault hoặc swap | Khi bộ nhớ giới hạn số phiên hoặc gây paging |
| GPU inference | GPU utilization, VRAM, request queue, tokens/s hoặc requests per accelerator | Khi bộ tăng tốc là nút thắt |
| Container service | CPU/memory utilization theo pod hoặc task, request rate, queue depth | Khi điều chỉnh replica hoặc node capacity |

### Metric phải liên hệ với capacity

Target tracking hoạt động tốt khi thay đổi số instance có quan hệ dự đoán được với metric. Ví dụ, nếu tổng request rate giữ nguyên và số instance tăng gấp đôi, request trung bình trên mỗi instance thường giảm gần một nửa khi tải được phân phối đều.

Một số metric tổng thể không tự giảm khi thêm instance. Ví dụ, tổng queue depth có thể vẫn cao sau scale-out vì queue đang chứa backlog cũ. Với worker, metric **messages per worker** hoặc **backlog per capacity unit** thường giúp chính sách hiểu mức tải trên mỗi đơn vị compute tốt hơn. Nếu chỉ dùng tổng queue depth, cần thiết kế step scaling hoặc metric chuyển đổi phù hợp.

Đối với API, **requests per target** thường có ý nghĩa hơn tổng request count của toàn hệ thống. Tuy nhiên, request có thể có chi phí xử lý khác nhau; 100 request đọc cache không tương đương 100 request chạy truy vấn nặng.

### Độ trễ và metric phản hồi chậm

Latency là tín hiệu gần với trải nghiệm người dùng, nhưng thường tăng sau khi capacity đã thiếu. Nếu autoscaler chỉ scale khi p95 vượt SLO, hệ thống có thể phản ứng quá muộn. Có thể kết hợp metric tải sớm hơn như request rate, queue depth hoặc CPU với latency làm điều kiện xác minh và cảnh báo.

Metric cần có:

- Độ phân giải và chu kỳ cập nhật đủ nhanh.
- Dữ liệu ổn định, ít missing point và không bị trễ quá mức.
- Phạm vi đo đúng nhóm máy hoặc workload.
- Đơn vị và phép tổng hợp nhất quán.
- Khả năng phân biệt tải thật với lỗi telemetry.

Không dùng một metric có thể bị thay đổi bởi chính sách khác mà không hiểu vòng phản hồi. Ví dụ, cache hit ratio có thể giảm khi scale-out vì instance mới có cache lạnh; metric này không nên tự nó kích hoạt scale-out vô hạn.

## 3. Target tracking: giữ metric quanh mục tiêu

Target tracking là chính sách tự điều chỉnh desired capacity để đưa một metric về gần giá trị mục tiêu. Có thể hình dung như bộ điều khiển phản hồi:

1. Thu thập metric hiện tại.
2. So sánh metric với target.
3. Ước lượng capacity cần thêm hoặc bớt.
4. Điều chỉnh desired capacity trong giới hạn min/max.
5. Chờ instance khởi động và metric phản ánh trạng thái mới.
6. Tiếp tục điều chỉnh khi tải thay đổi.

Ví dụ, nhóm web đặt mục tiêu CPU trung bình 55%. Khi CPU duy trì trên mức mục tiêu, chính sách tăng số instance; khi CPU thấp hơn trong thời gian đủ ổn định, chính sách có thể giảm capacity.

### Chọn target value

Target value cần được xác định bằng benchmark và SLO. Nếu mỗi instance có thể xử lý 100 request/giây ở p95 dưới 200 ms, nhưng ở 130 request/giây p95 tăng nhanh, không nên đặt target ở mức tối đa 130. Hãy chừa headroom để hấp thụ burst và biến động giữa các instance.

Với CPU utilization, target 50–60% có thể là điểm bắt đầu cho một số web workload, nhưng không phải quy tắc chung. Batch worker có thể chạy CPU cao hơn; dịch vụ nhạy latency cần headroom lớn hơn. Cần đo dưới tải đại diện và kiểm tra khi một instance bị lỗi.

### Ví dụ target tracking cho API

Giả sử benchmark cho thấy một instance xử lý ổn định 100 request/giây trong SLO. Lưu lượng dự kiến là 600 request/giây. Số instance cơ sở theo thông lượng là:

\[
N = \left\lceil \frac{600}{100} \right\rceil = 6
\]

Nếu cần dự phòng một instance lỗi và còn headroom cho burst, nhóm có thể đặt minimum hoặc capacity mục tiêu cao hơn mức tính toán thuần túy. Target tracking theo request count per target sẽ điều chỉnh capacity khi tải thay đổi; min/max vẫn giới hạn phạm vi.

Con số 100 request/giây là kết quả benchmark giả định. Phải đo với phân phối request, payload, dependency và SLO thực tế.

### Ưu điểm và giới hạn

**Ưu điểm:**

- Ít phải tự định nghĩa nhiều ngưỡng scale-out/scale-in.
- Tự điều chỉnh theo tải biến động.
- Phù hợp với metric có quan hệ rõ ràng với capacity.
- Giảm thao tác vận hành khi nhu cầu thay đổi liên tục.

**Giới hạn:**

- Metric có thể trễ hoặc không phản ánh đúng bottleneck.
- Thời gian khởi động instance khiến hệ thống phản ứng chậm.
- Target quá cao làm thiếu headroom; target quá thấp làm tăng chi phí.
- Nếu metric không giảm khi thêm instance, chính sách có thể tiếp tục scale dù đã đủ capacity.
- Scale-in có thể không an toàn với workload stateful hoặc job dài.

Target tracking không phải công tắc tức thời. Cần tính thời gian thu thập metric, đánh giá policy, cấp phát, boot, warm-up và đưa instance vào load balancer.

## 4. Step scaling: phản ứng theo mức độ vượt ngưỡng

Step scaling dùng cảnh báo metric để kích hoạt các điều chỉnh capacity theo nhiều mức. Thay vì cố giữ metric ở một target, người vận hành định nghĩa các dải vượt ngưỡng và mức thay đổi tương ứng.

Ví dụ với CPU utilization:

| Mức độ vượt ngưỡng cảnh báo | Điều chỉnh minh họa |
|---|---:|
| CPU vượt ngưỡng nhẹ | Tăng 1 instance |
| CPU vượt ngưỡng trung bình | Tăng 2 instance |
| CPU vượt ngưỡng cao | Tăng 4 instance |

Các dải thực tế phải được định nghĩa theo cú pháp của nền tảng, không chồng lấn và không để khoảng trống ngoài dự kiến. Một số dịch vụ xác định step adjustment dựa trên mức metric vượt qua alarm threshold; cần đọc đúng semantics của nhà cung cấp trước khi cấu hình.

### Thiết kế alarm và step adjustment

Một policy step scaling cần xác định:

- Metric và phép thống kê, chẳng hạn average CPU hoặc maximum queue age.
- Ngưỡng cảnh báo và số chu kỳ liên tiếp cần vi phạm.
- Khoảng thời gian lấy mẫu và evaluation period.
- Các dải breach và số instance thêm/bớt trong mỗi dải.
- Min/max capacity và giới hạn tốc độ thay đổi.
- Cooldown hoặc warm-up để tránh hành động lặp khi instance mới chưa sẵn sàng.

Ví dụ minh họa cho queue worker:

- Nếu backlog age vượt 30 giây trong 2 chu kỳ, thêm 1 worker.
- Nếu backlog age vượt 60 giây, thêm 3 worker.
- Nếu backlog age vượt 120 giây, thêm 5 worker, trong giới hạn max.
- Chỉ scale-in khi backlog age thấp và số worker bận đã giảm ổn định.

Không nên chỉ scale theo số message trong queue mà bỏ qua tốc độ xử lý mỗi worker. Nếu job mới đến nhanh hơn năng lực xử lý, queue vẫn tiếp tục tăng dù đã thêm vài worker.

### Khi nào step scaling phù hợp?

- Tải tăng đột ngột và cần phản ứng mạnh theo mức độ quá tải.
- Có các ngưỡng vận hành rõ ràng từ SLO hoặc cảnh báo.
- Workload có nhiều mức độ ưu tiên hoặc chi phí xử lý khác nhau.
- Cần kiểm soát mức tăng capacity thay vì để policy tự tính từ target.
- Queue worker cần thêm nhiều consumer khi backlog vượt các mốc nhất định.

Step scaling dễ hiểu nhưng cần hiệu chỉnh. Nếu alarm quá nhạy, policy có thể scale liên tục; nếu alarm yêu cầu quá nhiều chu kỳ, phản ứng sẽ chậm. Tăng capacity theo bước lớn cũng có thể làm quá tải database hoặc dependency phía sau.

## 5. Scheduled scaling: chuẩn bị capacity theo lịch

Scheduled scaling thay đổi capacity tại các thời điểm đã định trước. Cách này phù hợp khi workload có mẫu lặp lại hoặc sự kiện đã biết:

- Cửa hàng trực tuyến thường tăng traffic vào giờ trưa hoặc buổi tối.
- Hệ thống báo cáo chạy batch vào đầu ngày.
- Lớp học hoặc sự kiện trực tuyến có giờ bắt đầu cố định.
- Dịch vụ nội bộ chỉ hoạt động trong giờ làm việc.
- Một đợt import dữ liệu có lịch triển khai rõ ràng.

Ví dụ lịch cho dịch vụ có giờ cao điểm 09:00:

| Thời điểm | Capacity được đặt |
|---|---|
| 08:40 | Tăng minimum/desired để máy mới bắt đầu khởi động |
| 09:00 | Dịch vụ bước vào giờ cao điểm |
| 12:00 | Giữ capacity theo lịch nếu nhu cầu còn cao |
| 18:00 | Hạ minimum về mức nền; dynamic policy tiếp tục bảo vệ nếu tải còn cao |
| 22:00 | Duy trì mức tối thiểu qua đêm |

Lịch cần bắt đầu trước giờ tải đến để tính thời gian cấp phát, boot, cài agent, tải image, warm-up cache và health check. Nếu một VM cần 6 phút mới ready, đặt lịch đúng 09:00 có thể quá muộn.

### Múi giờ và thay đổi lịch

Hãy xác định lịch dùng UTC hay múi giờ địa phương. Nếu dùng múi giờ có daylight saving time, thời điểm thực tế có thể dịch chuyển theo mùa. Một số nền tảng hỗ trợ timezone và tự xử lý DST; nền tảng khác chỉ nhận cron theo UTC.

Lịch cũng cần được cập nhật khi giờ hoạt động thay đổi, ngày nghỉ hoặc sự kiện đặc biệt. Không nên tạo nhiều schedule trùng nhau mà không hiểu quy tắc ưu tiên và cách chúng ghi đè desired/min/max.

### Scheduled scaling không thay thế scaling động

Lịch giúp chuẩn bị capacity trước nhu cầu đã biết. Nếu lưu lượng thực tế cao hơn hoặc thấp hơn dự báo, target tracking hoặc step scaling vẫn có thể cần thiết để điều chỉnh. Một cấu hình phổ biến là:

- Scheduled scaling đặt baseline hoặc minimum cao hơn trước giờ cao điểm.
- Target tracking điều chỉnh theo tải thực tế trong khoảng thời gian đó.
- Step scaling xử lý tình huống backlog hoặc quá tải vượt ngưỡng.

Khi kết hợp, phải xác định rõ policy nào được phép thay đổi desired capacity, policy nào thay đổi min/max và cách nền tảng xử lý nhiều policy cùng lúc.

## 6. So sánh ba chiến lược

| Tiêu chí | Target tracking | Step scaling | Scheduled scaling |
|---|---|---|---|
| Tín hiệu điều khiển | Metric so với target | Alarm và mức breach | Thời gian/lịch |
| Phản ứng | Tự điều chỉnh liên tục theo metric | Điều chỉnh theo các bước đã định nghĩa | Thay đổi capacity vào thời điểm định trước |
| Phù hợp | Tải thay đổi liên tục, metric tỷ lệ với capacity | Burst, backlog hoặc các ngưỡng rõ | Tải có chu kỳ hoặc sự kiện biết trước |
| Công sức hiệu chỉnh | Chọn metric và target tốt | Thiết kế alarm, dải và step | Dự báo lịch và thời gian chuẩn bị |
| Rủi ro chính | Metric sai hoặc phản hồi chậm | Ngưỡng dao động, scale quá mạnh/yếu | Lịch không khớp nhu cầu thực |
| Cách kết hợp | Điều chỉnh quanh capacity nền | Bổ sung phản ứng khi vượt ngưỡng | Đặt baseline trước giờ tải |

Không có một chính sách phù hợp cho mọi workload. Nhiều hệ thống dùng scheduled scaling để chuẩn bị mức nền, sau đó dùng target tracking để xử lý biến động. Step scaling được bổ sung khi cần phản ứng rõ ràng với một tín hiệu vượt ngưỡng.

## 7. Warm-up, cooldown và ổn định vòng điều khiển

Sau khi scale-out, instance mới không lập tức tạo ra capacity hữu ích. Nó có thể cần:

1. Cấp phát từ cloud provider.
2. Boot hệ điều hành hoặc khởi chạy container.
3. Cài đặt/khởi động agent và lấy cấu hình.
4. Nạp model, cache hoặc dữ liệu ban đầu.
5. Đăng ký với load balancer.
6. Vượt qua readiness check.

**Instance warm-up** là khoảng thời gian cần để instance mới sẵn sàng và metric phản ánh năng lực mới. Nếu autoscaler không tính khoảng này, nó có thể tiếp tục scale-out vì metric chưa giảm, dẫn tới tạo dư capacity.

**Cooldown** hoặc stabilization window giúp tránh điều chỉnh liên tục ngay sau một hành động scaling. Tên gọi và semantics khác nhau giữa nền tảng. Một số dịch vụ dùng warm-up cho instance mới, một số dùng cooldown giữa các lần policy hành động; không nên coi chúng là một tham số giống nhau.

### Tránh dao động scale-out/scale-in

Hiện tượng *flapping* xảy ra khi nhóm liên tục tăng rồi giảm capacity. Nguyên nhân có thể là:

- Ngưỡng scale-out và scale-in quá gần nhau.
- Metric nhiễu hoặc cập nhật chậm.
- Instance khởi động lâu nhưng policy đánh giá quá thường xuyên.
- Scale-in làm tải dồn lên các instance còn lại, ngay sau đó lại scale-out.
- Nhiều policy cùng điều khiển một nhóm mà không có quy tắc rõ.

Biện pháp giảm dao động:

- Dùng ngưỡng scale-in thận trọng hơn scale-out.
- Đặt stabilization window phù hợp với thời gian phản hồi của workload.
- Làm mượt metric hoặc yêu cầu nhiều chu kỳ xác nhận.
- Giữ minimum capacity đủ headroom.
- Chỉ scale-in khi queue, latency và mức sử dụng đều ổn định.
- Theo dõi số lần scaling và thời gian từ quyết định tới ready.

## 8. Scale-in an toàn: draining và bảo vệ workload

Scale-in có thể gây gián đoạn nếu instance đang phục vụ request hoặc chạy job dài. Trước khi terminate:

- Ngừng gửi request mới tới instance.
- Dùng connection draining hoặc deregistration delay cho backend.
- Cho phép request đang chạy hoàn tất trong giới hạn thời gian.
- Với worker, ngừng nhận job mới, hoàn tất hoặc trả lại job chưa xử lý.
- Lưu checkpoint nếu tác vụ có thể tiếp tục sau khi instance bị thay thế.
- Bảo đảm dữ liệu bền vững không chỉ nằm trên ổ đĩa tạm của instance.

Một số nền tảng hỗ trợ scale-in protection hoặc instance protection. Có thể dùng để giữ máy đang chạy job quan trọng, nhưng phải có quy trình gỡ bảo vệ sau khi job kết thúc; nếu không, nhóm có thể không scale-in được và chi phí tăng.

Với container orchestration, cần kết hợp readiness, termination grace period, preStop hook, PodDisruptionBudget và xử lý SIGTERM. Với VM group, cần lifecycle hook hoặc cơ chế tương tự để drain trước khi hủy máy.

## 9. Kết hợp autoscaling với load balancer và queue

### Web/API

Load balancer gửi request tới backend healthy. Autoscaler tăng số instance khi CPU, request per target hoặc metric phù hợp vượt mục tiêu. Instance mới chỉ nên nhận traffic sau khi readiness đạt. Khi scale-in, backend được deregister và drain trước khi terminate.

### Queue worker

Queue giữ job khi worker chưa xử lý kịp. Autoscaler có thể theo dõi backlog per worker hoặc age of oldest message. Khi thêm worker, cần bảo đảm dependency như database, API ngoài và object storage chịu được số consumer tăng lên. Nếu worker tăng quá nhanh, downstream có thể bị quá tải dù queue giảm.

### Container service

Autoscaling replica ở tầng pod/task và autoscaling node là hai lớp khác nhau. Nếu tăng replica nhưng cluster không còn node capacity, pod sẽ pending. Nếu tăng node nhưng workload không tăng replica, máy mới có thể nhàn rỗi. Cần phối hợp service-level scaling với cluster/node autoscaling và đặt resource requests/limits đúng.

### Serverless

Nền tảng serverless có thể tự điều chỉnh instance thực thi theo concurrency hoặc request rate, nhưng vẫn có quota và giới hạn concurrency. Cần kiểm tra giới hạn account, cold start, downstream connection pool và retry. Nếu một function scale rất nhanh nhưng mở quá nhiều kết nối database, database có thể trở thành bottleneck.

## 10. Tính capacity và headroom

Một phép tính sơ bộ giúp xác định min/target/max:

\[
N_{required} = \left\lceil \frac{L_{peak}}{C_{safe}} \right\rceil
\]

Trong đó:

- \(L_{peak}\) là tải đỉnh dự kiến.
- \(C_{safe}\) là năng lực an toàn của một instance khi vẫn đáp ứng SLO.
- \(N_{required}\) là số instance tối thiểu theo tải đó.

Nếu cần chịu được một instance lỗi, có thể tính thêm capacity dự phòng:

\[
N_{with\ failure} = N_{required} + N_{failure\ reserve}
\]

Ví dụ, một API dự kiến nhận 800 request/giây. Benchmark xác định mỗi instance xử lý an toàn 100 request/giây ở SLO:

\[
N_{required} = \lceil 800 / 100 \rceil = 8
\]

Nếu muốn chịu được một instance lỗi mà không vi phạm SLO, cần capacity tương đương ít nhất 9 instance theo giả định này. Min có thể được đặt theo mức tải nền và yêu cầu sẵn sàng; max cần đủ cao để hấp thụ peak nhưng không vượt quota, ngân sách hoặc giới hạn dependency.

Đây là phép tính ban đầu. Trong thực tế, hiệu năng không luôn tăng tuyến tính theo số instance vì có overhead mạng, database, cache, contention và phân phối tải không đều. Hãy xác minh bằng load test khi một hoặc nhiều instance bị loại.

## 11. Ví dụ cấu hình kết hợp ba chính sách

Một dịch vụ xử lý đơn hàng có các đặc điểm:

- Tải nền khoảng 150 request/giây.
- Giờ cao điểm đã biết trước từ 09:00 đến 11:00, có thể đạt 600 request/giây.
- Mỗi instance xử lý an toàn 100 request/giây ở SLO.
- Một instance cần khoảng 5 phút để boot, nạp cấu hình và vượt readiness check.

Một thiết kế minh họa:

| Thành phần | Thiết lập tham khảo | Mục đích |
|---|---|---|
| Min capacity | 2 | Giữ mức sẵn sàng nền |
| Desired ban đầu | 2–3 tùy tải hiện tại | Khởi chạy dịch vụ |
| Max capacity | 12 | Giới hạn theo quota và ngân sách |
| Scheduled scaling | 08:50 tăng min/desired lên 7 hoặc 8 | Chuẩn bị trước peak 09:00 |
| Target tracking | Request per target hướng tới khoảng 80–90 request/giây | Điều chỉnh theo tải thực tế |
| Step scaling | Khi error/queue hoặc metric tải vượt mức nghiêm trọng trong thời gian xác nhận, thêm một batch capacity | Phản ứng với burst vượt dự báo |
| Scale-in | Chỉ giảm sau giờ cao điểm khi metric thấp ổn định và backend đã drain | Tránh cắt capacity quá sớm |

Các giá trị là ví dụ thiết kế, không phải công thức dùng nguyên xi. Nếu scheduled policy nâng minimum lên 8, target tracking có thể tăng tiếp khi tải cao. Sau peak, lịch hạ minimum về 2 nhưng target tracking vẫn có thể giữ desired cao hơn nếu tải thực tế chưa giảm. Cần kiểm tra semantics của nền tảng về việc schedule đặt desired hay min/max và cách policy khác tương tác.

## 12. Quy trình triển khai và kiểm thử autoscaling

1. **Đo workload:** thu thập tải nền, peak, burst, thời gian job và SLO.
2. **Benchmark instance:** xác định capacity an toàn của từng loại máy.
3. **Đặt min/max:** tính theo tải nền, khả năng chịu lỗi, quota và ngân sách.
4. **Chọn metric:** xác định metric có quan hệ với capacity và có độ trễ phù hợp.
5. **Cấu hình policy:** tạo target, step hoặc schedule; ghi rõ ai điều khiển min/max/desired.
6. **Cấu hình warm-up và scale-in:** đặt thời gian khởi động, draining và bảo vệ job.
7. **Thử scale-out:** tạo tải tăng dần, đo thời gian tới khi instance ready và metric giảm.
8. **Thử scale-in:** giảm tải, xác minh request/job hoàn tất và instance được loại an toàn.
9. **Thử tình huống lỗi:** quota hết, instance boot lỗi, metric mất dữ liệu hoặc dependency bão hòa.
10. **Theo dõi và hiệu chỉnh:** so sánh SLO, số lần scaling, capacity dư và chi phí.

### Các tình huống kiểm thử cần có

- Tải tăng từ từ và tăng đột ngột.
- Tải giảm nhanh sau giờ cao điểm.
- Một instance unhealthy hoặc bị terminate ngoài kế hoạch.
- Instance mới khởi động chậm hơn bình thường.
- Metric bị trễ hoặc mất dữ liệu.
- Đạt max capacity nhưng tải tiếp tục tăng.
- Scheduled event chạy đúng giờ và xử lý đúng múi giờ.
- Scale-in khi backend có kết nối dài hoặc worker có job đang chạy.

## 13. Quan sát và tối ưu chính sách

Theo dõi không chỉ số instance mà cả chất lượng dịch vụ và chi phí:

| Nhóm | Metric |
|---|---|
| Capacity | Desired, current, min/max, pending, healthy và unhealthy instances |
| Scaling activity | Thời điểm policy kích hoạt, lý do, số instance thêm/bớt, lỗi cấp phát |
| Performance | p50/p95/p99 latency, throughput thành công, error rate |
| Resource | CPU, memory, network, disk, GPU utilization |
| Queue | Backlog, age of oldest message, arrival/completion rate |
| Readiness | Thời gian boot, warm-up, thời gian đăng ký backend |
| Cost | Instance-hours, chi phí idle, chi phí peak và chi phí trên request/job |

Các câu hỏi nên đặt ra sau mỗi lần thử:

- Scale-out bắt đầu khi nào so với lúc SLO bắt đầu xấu?
- Mất bao lâu để instance mới thật sự nhận traffic?
- Target metric có giảm sau khi tăng capacity không?
- Có scale vượt max hoặc chạm quota không?
- Scale-in có làm latency, error hoặc queue age tăng trở lại không?
- Có instance chạy nhưng không nhận workload do health check hoặc registration lỗi không?
- Chi phí capacity dư có tương xứng với mức cải thiện availability không?

Nếu scale-out quá muộn, hãy dùng metric sớm hơn, lịch chuẩn bị hoặc tăng baseline. Nếu scale-out quá mạnh, điều chỉnh step, target hoặc thời gian ổn định. Nếu scale-in gây lỗi, tăng ngưỡng an toàn, kéo dài draining hoặc cải thiện thiết kế stateless/checkpoint.

## 14. Những sai lầm thường gặp

1. **Chỉ dùng CPU cho mọi workload:** queue, memory, I/O hoặc GPU có thể là nút thắt thực sự.
2. **Đặt target bằng năng lực tối đa benchmark:** không còn headroom cho burst hoặc instance lỗi.
3. **Metric không tỷ lệ với capacity:** thêm instance nhưng metric không giảm, khiến autoscaler tiếp tục scale.
4. **Đặt lịch đúng thời điểm tải bắt đầu:** instance chưa kịp boot và warm-up.
5. **Không xác định timezone:** schedule chạy lệch khi chuyển múi giờ hoặc DST.
6. **Alarm quá nhạy:** step scaling kích hoạt lặp lại và gây dao động.
7. **Scale-in ngay khi metric giảm trong một chu kỳ:** workload có thể tăng lại hoặc backend còn request đang chạy.
8. **Không đặt max capacity:** chi phí hoặc tải lên dependency có thể tăng ngoài dự kiến.
9. **Quên quota và nguồn cung:** policy yêu cầu thêm máy nhưng cloud không cấp được.
10. **Tăng worker mà không bảo vệ downstream:** database hoặc API phụ thuộc bị quá tải.
11. **Nhiều policy điều khiển cùng metric mà không hiểu ưu tiên:** desired capacity thay đổi khó dự đoán.
12. **Không kiểm thử scale-in:** máy bị hủy giữa lúc đang xử lý job hoặc giữ trạng thái cục bộ.

## 15. Checklist trước khi đưa autoscaling vào production

- [ ] Đã mô tả tải nền, peak, burst và SLO.
- [ ] Đã benchmark năng lực an toàn của một instance.
- [ ] Đã chọn metric phản ánh đúng bottleneck và quan hệ với capacity.
- [ ] Min, desired và max phù hợp với availability, quota và ngân sách.
- [ ] Target tracking có target và headroom được kiểm chứng.
- [ ] Step scaling có alarm, evaluation period và các dải không chồng lấn.
- [ ] Scheduled scaling dùng đúng timezone và bắt đầu trước thời điểm tải đến.
- [ ] Đã xác định tương tác giữa schedule và policy động.
- [ ] Warm-up, cooldown/stabilization và scale-in protection được cấu hình rõ.
- [ ] Load balancer chỉ gửi traffic tới instance ready.
- [ ] Connection draining và graceful shutdown đã được kiểm thử.
- [ ] Worker có checkpoint/acknowledgement/retry phù hợp.
- [ ] Downstream có đủ capacity khi nhóm scale-out.
- [ ] Có cảnh báo khi chạm max, thiếu quota hoặc scaling activity thất bại.
- [ ] Đã thử scale-out, scale-in, burst, instance failure và metric mất dữ liệu.
- [ ] Có dashboard theo dõi SLO, capacity, scaling activity và chi phí.

## 16. Bài tập vận dụng

Một nhóm worker xử lý ảnh nhận trung bình 300 job/phút, nhưng trong khoảng 10 phút sau mỗi giờ backlog có thể tăng lên 1.200 job/phút. Mỗi worker xử lý ổn định 60 job/phút và cần 3 phút để khởi động. Hệ thống yêu cầu tuổi job cũ nhất dưới 2 phút trong giờ cao điểm. Ban đêm chỉ cần tối thiểu 2 worker để xử lý tác vụ lẻ.

1. Hãy ước lượng số worker cần cho tải 1.200 job/phút nếu không tính headroom.
2. Nên dùng target tracking theo metric nào để phản ánh tải trên mỗi worker?
3. Step scaling có thể dùng những mức backlog age hoặc tốc độ job đến nào để phản ứng với burst?
4. Scheduled scaling nên bắt đầu trước giờ burst bao lâu và vì sao?
5. Khi tải giảm, cần kiểm tra gì trước khi scale-in worker?
6. Những giới hạn nào cần đặt cho max capacity để bảo vệ downstream storage?

Gợi ý: số worker thuần theo năng lực là \(1200/60 = 20\), sau đó bổ sung headroom theo SLO và biến động thực tế. Có thể dùng backlog per worker hoặc age of oldest job làm metric; target phải được benchmark. Vì worker cần 3 phút warm-up, schedule nên bắt đầu trước thời điểm tải đến đủ lâu để worker ready. Trước scale-in, ngừng nhận job mới, hoàn tất hoặc trả lại job chưa xử lý, kiểm tra queue age và khả năng của storage.

## Kết luận

Target tracking phù hợp khi có metric liên hệ rõ với capacity và cần tự điều chỉnh theo tải. Step scaling hữu ích khi cần phản ứng theo các mức vượt ngưỡng cụ thể. Scheduled scaling chuẩn bị capacity trước những chu kỳ hoặc sự kiện đã biết. Muốn ba chính sách hoạt động ổn định, hãy chọn metric đúng, tính min/max và headroom, tính thời gian warm-up, kiểm soát scale-in, phối hợp với load balancer và dependency, rồi kiểm thử cả scale-out lẫn scale-in trước khi đưa vào production.
