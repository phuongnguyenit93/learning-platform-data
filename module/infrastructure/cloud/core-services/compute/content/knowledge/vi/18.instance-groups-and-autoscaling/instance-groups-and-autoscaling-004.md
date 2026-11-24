# Lựa chọn metric theo CPU, độ trễ, độ sâu hàng đợi hoặc mức đồng thời

Autoscaling điều chỉnh số lượng máy hoặc worker dựa trên tín hiệu phản ánh nhu cầu và khả năng phục vụ của hệ thống. Chọn metric không phù hợp có thể khiến nhóm máy scale quá muộn, tăng giảm liên tục hoặc tạo thêm tải lên dependency đang quá tải. CPU utilization là tín hiệu phổ biến, nhưng không đại diện cho mọi workload. API có thể bị giới hạn bởi latency của database; worker có thể bị backlog trong queue dù CPU thấp; dịch vụ giữ nhiều kết nối có thể cạn concurrency trước khi CPU đạt ngưỡng.

Metric tốt cần liên hệ trực tiếp với mục tiêu dịch vụ, phản ánh tình trạng cần thêm hoặc bớt capacity, có thể đo ổn định và có cách diễn giải rõ ràng khi số instance thay đổi. Bài học này trình bày cách chọn và kết hợp CPU, latency, queue depth và concurrency cho instance group, VM worker và các mô hình compute cloud.

## 1. Autoscaling cần đo điều gì?

Autoscaling thường điều khiển desired capacity của một nhóm máy trong giới hạn min/max. Bộ điều khiển thu thập metric, so sánh với mục tiêu hoặc ngưỡng rồi đề xuất scale out hay scale in.

Một hệ thống cần theo dõi ba khía cạnh:

- **Nhu cầu:** lượng công việc đang đến, ví dụ request/giây, message/giây, số phiên hoặc số job.
- **Saturation:** mức sử dụng tài nguyên có thể làm giới hạn throughput, ví dụ CPU, memory, connection pool hoặc concurrency.
- **Chất lượng dịch vụ:** thời gian phản hồi, tỷ lệ lỗi, thời gian chờ queue và SLO.

Metric nhu cầu cho biết có bao nhiêu công việc cần xử lý. Metric saturation cho biết capacity hiện tại đang gần giới hạn hay chưa. Metric chất lượng dịch vụ cho biết người dùng hoặc hệ thống phía sau đang chịu tác động như thế nào. Một policy hiệu quả thường kết hợp ít nhất một tín hiệu về nhu cầu hoặc saturation với guardrail chất lượng.

### Metric không đồng nghĩa với mục tiêu autoscaling

Ví dụ, mục tiêu có thể là giữ p95 latency dưới SLO. CPU chỉ là một tín hiệu để tăng capacity khi CPU-bound. Nếu latency tăng do database chậm, tăng số VM web có thể làm số kết nối tới database tăng và khiến sự cố nặng hơn. Do đó, cần chọn metric dựa trên nguyên nhân mà thêm compute có thể giải quyết.

## 2. Các nhóm metric thường dùng

| Metric | Phản ánh | Phù hợp với | Rủi ro khi dùng đơn lẻ |
|---|---|---|---|
| CPU utilization | Mức bận của CPU | Workload CPU-bound, web/API tính toán nhiều | Không phát hiện tốt I/O wait, queue backlog hoặc giới hạn concurrency |
| Memory utilization / working set | Mức tiêu thụ RAM | Workload có footprint tăng theo request hoặc cache | RAM có thể không giảm khi tải giảm; scale-in có thể không giải quyết memory leak |
| Request rate | Nhu cầu request đến | API/web có chi phí request tương đối đồng đều | Request có độ phức tạp khác nhau; rate không cho biết backend có đang quá tải |
| p95/p99 latency | Trải nghiệm ở đuôi phân phối | Dịch vụ đồng bộ có SLO latency | Có thể tăng do dependency, network hoặc lỗi; thường là tín hiệu trễ |
| Queue depth / backlog | Công việc chưa xử lý | Worker bất đồng bộ, batch, event consumer | Số lượng message không thể hiện độ tuổi hoặc chi phí từng message |
| Age of oldest message | Thời gian chờ của công việc lâu nhất | Queue cần đáp ứng deadline/SLO | Có thể phản ứng chậm nếu metric cập nhật thưa hoặc message bị poison |
| Concurrency / in-flight requests | Số công việc đang xử lý cùng lúc | API, proxy, server giữ session, worker | Cần chuẩn hóa theo capacity mỗi instance và giới hạn runtime |
| Active connections | Số kết nối đang mở | Dịch vụ giữ kết nối lâu, WebSocket, database proxy | Kết nối nhàn rỗi có thể không tiêu thụ nhiều compute |
| Custom work per instance | Nhu cầu đã chuẩn hóa theo capacity | Workload có cost khác nhau theo job | Cần xây dựng metric và bảo đảm dữ liệu đúng |

Không nên thu thập mọi metric rồi đưa tất cả vào một policy mà không xác định vai trò. Mỗi metric cần có lý do sử dụng, owner, đơn vị, chu kỳ cập nhật và hành động tương ứng.

## 3. CPU utilization: dễ dùng nhưng không đủ cho mọi workload

CPU utilization đo tỷ lệ thời gian CPU thực hiện công việc trong một khoảng lấy mẫu. Với workload CPU-bound, khi CPU duy trì cao và latency hoặc queue cũng tăng, thêm instance thường làm tăng tổng năng lực xử lý.

### Khi CPU là metric phù hợp

- Mã ứng dụng thực hiện nhiều phép tính trên mỗi request.
- Worker xử lý ảnh, mã hóa, nén hoặc tính toán dữ liệu.
- Mỗi request có chi phí CPU tương đối ổn định.
- Throughput tăng gần tuyến tính theo số vCPU hoặc số instance trong phạm vi đã kiểm chứng.

### Khi CPU có thể gây hiểu nhầm

- Ứng dụng chờ database, network hoặc storage: CPU thấp nhưng latency cao.
- Một thread bão hòa trên máy nhiều core: CPU tổng thể có thể thấp dù ứng dụng bị giới hạn.
- Container bị CPU throttling do limit: utilization nhìn từ node có thể không phản ánh đầy đủ giới hạn của container.
- Instance burstable hết credit: hiệu năng giảm dù metric trung bình không thể hiện đúng trạng thái.
- Một số workload dùng GPU: CPU thấp không có nghĩa GPU còn capacity.

Nếu dùng CPU, nên đo đúng phạm vi cần scale: per-instance hoặc per-container thay vì chỉ nhìn tổng CPU của cả nhóm. Trung bình nhóm có thể che giấu một instance bị nóng trong khi các instance khác nhàn rỗi.

### Chọn target CPU

Không có một ngưỡng chung cho mọi ứng dụng. Chọn mục tiêu bằng thử nghiệm tải: tăng traffic theo từng bước, quan sát CPU, latency, error rate và throughput; tìm vùng mà ứng dụng còn headroom để xử lý burst và thời gian khởi tạo instance mới. Mục tiêu autoscaling thường cần thấp hơn mức bão hòa để có thời gian scale out trước khi hàng đợi hoặc latency tăng mạnh.

## 4. Độ trễ: metric gần với trải nghiệm người dùng

Latency đo thời gian hoàn thành request hoặc tác vụ. Với dịch vụ đồng bộ, p95/p99 thường hữu ích hơn trung bình vì phản ánh nhóm request chậm mà người dùng dễ nhận thấy.

### Vì sao nên dùng percentile?

Giả sử 95% request hoàn tất trong 200 ms nhưng 5% còn lại mất 4 giây. Trung bình có thể trông chấp nhận được trong khi một phần người dùng gặp trải nghiệm rất xấu. p95 cho biết ngưỡng mà 95% request hoàn tất không vượt qua; p99 nhạy hơn với đuôi chậm nhưng cũng dễ dao động khi lượng mẫu ít.

### Latency phù hợp khi nào?

- Backend có khả năng tăng throughput khi thêm instance.
- Request được phân phối tương đối đồng đều qua load balancer.
- Có thể đo latency ở đúng điểm cần scale, ví dụ backend processing time thay vì tổng thời gian bao gồm DNS/client/network ngoài phạm vi.
- Dependency có đủ capacity để phục vụ thêm request.

### Giới hạn khi scale theo latency

Latency thường là tín hiệu sau khi hệ thống đã bắt đầu chịu tải. Khi p95 tăng, có thể đã có queue, lock contention hoặc database quá tải. Nếu nguyên nhân là dependency dùng chung, scale out frontend có thể làm tăng concurrency và khiến dependency chậm hơn.

Nên tách các thành phần thời gian bằng distributed tracing: thời gian ở ứng dụng, database, cache, queue và API ngoài. Dùng backend latency để scale compute khi chính backend là bottleneck; dùng alert hoặc circuit breaker cho dependency bị lỗi.

### Dùng latency cùng guardrail

Có thể scale out khi latency vượt mục tiêu đồng thời request rate hoặc CPU cho thấy tải tăng. Tuy nhiên, nếu yêu cầu bảo vệ SLO, không nên đợi mọi metric cùng vượt ngưỡng mới scale out: một metric bão hòa rõ ràng có thể đủ để tăng capacity. Scale-in nên thận trọng hơn và chỉ xảy ra khi latency ổn định trong một khoảng thời gian.

## 5. Queue depth và backlog cho workload bất đồng bộ

Worker thường nhận message từ queue, xử lý rồi acknowledge. Nếu tốc độ message đến lớn hơn tốc độ xử lý, backlog tăng. Queue depth cho biết có bao nhiêu công việc đang chờ; đây là tín hiệu trực tiếp cho nhu cầu worker.

### Queue depth

Queue depth hữu ích khi:

- Công việc có thể chờ trong queue thay vì phải xử lý ngay.
- Worker có thể scale ngang độc lập.
- Message được phân phối tương đối đều và có thể xử lý song song.
- Hệ thống có giới hạn rõ về số job mỗi worker xử lý cùng lúc.

Chỉ nhìn tổng số message có thể gây hiểu nhầm. Một nghìn message nhẹ có thể xử lý nhanh; một trăm message nặng có thể cần nhiều phút. Nên bổ sung message age, tốc độ đến, tốc độ xử lý và độ phức tạp của job.

### Backlog trên mỗi worker

Một metric hữu ích là số message đang chờ chia cho số worker đang hoạt động:

\[
\text{Backlog per worker} =
\frac{\text{Visible queue messages}}{\text{Healthy active workers}}
\]

Ví dụ, 1.200 message và 6 worker khỏe tạo ra backlog khoảng 200 message mỗi worker. Nếu mục tiêu là 50 message/worker, hệ thống cần tăng capacity. Đây là phép ước lượng đơn giản; cần điều chỉnh nếu worker có kích thước khác nhau hoặc message có chi phí xử lý khác nhau.

Không chia cho desired capacity nếu một phần instance chưa healthy. Dùng số worker thực sự nhận và xử lý job để tránh đánh giá thấp backlog trong lúc scale out.

### Age of oldest message

Age of oldest message đo thời gian message lâu nhất đã chờ. Metric này phù hợp khi mục tiêu là hoàn tất công việc trong deadline. Queue có thể có depth cao nhưng worker xử lý nhanh và message age thấp; ngược lại, queue depth nhỏ vẫn có thể có một message bị kẹt quá lâu.

Nếu oldest age tăng liên tục dù worker count tăng, có thể có poison message, partition nóng, consumer lỗi hoặc dependency bị nghẽn. Tăng worker không nhất thiết giải quyết được vấn đề.

### Ước lượng số worker

Giả sử mỗi worker xử lý trung bình 10 message/giây, tốc độ đến là 80 message/giây và muốn duy trì headroom 25%. Capacity mục tiêu trên mỗi worker cần được đặt thấp hơn throughput tối đa đo được. Số worker có thể ước lượng từ tốc độ đến chia cho throughput mục tiêu mỗi worker, sau đó làm tròn lên và cộng giới hạn dự phòng.

\[
N_{workers} \approx
\left\lceil \frac{\lambda_{in}}{\mu_{target}} \right\rceil
\]

Trong đó \(\lambda_{in}\) là tốc độ message đến và \(\mu_{target}\) là tốc độ xử lý an toàn mỗi worker. Công thức không tính trực tiếp backlog hiện tại; nếu cần xóa backlog trong một khoảng thời gian, phải cộng throughput cần thiết để xử lý phần tồn đọng.

Một cách ước lượng bổ sung:

\[
\text{Required processing rate} =
\text{Incoming rate} +
\frac{\text{Current backlog}}{\text{Desired drain time}}
\]

Ví dụ, queue có 6.000 message, tốc độ đến 40 message/giây và mục tiêu xóa backlog trong 300 giây. Hệ thống cần xử lý khoảng 40 + 6.000/300 = 60 message/giây. Nếu một worker xử lý an toàn 10 message/giây, cần khoảng 6 worker, chưa tính headroom và giới hạn dependency.

## 6. Concurrency và số công việc đang xử lý

Concurrency là số request, task hoặc connection đang được xử lý đồng thời. Nó phù hợp với ứng dụng mà giới hạn phục vụ liên quan đến số slot xử lý hơn là CPU.

Ví dụ:

- Một API server có giới hạn 200 request in-flight mỗi VM.
- Một worker có thể xử lý tối đa 8 job đồng thời do RAM mỗi job lớn.
- Một function runtime có concurrency limit theo instance hoặc theo service.
- Một proxy giữ nhiều kết nối lâu nhưng mỗi kết nối tiêu thụ ít CPU.

### Chuẩn hóa concurrency theo capacity

Tổng concurrency của cả nhóm không đủ để quyết định scale nếu số instance đang thay đổi. Có thể dùng concurrency trung bình trên mỗi instance:

\[
\text{Concurrency per instance} =
\frac{\text{Total in-flight work}}{\text{Healthy instances}}
\]

Nếu mục tiêu là giữ dưới 120 request in-flight mỗi instance và hiện có 4 instance khỏe, tổng concurrency mục tiêu khoảng 480. Khi số instance thay đổi, metric per-instance giúp policy giữ mức tải tương đối ổn định.

### Concurrency không phải lúc nào cũng là tải compute

Một WebSocket nhàn rỗi có thể tồn tại lâu nhưng tiêu thụ ít CPU; một request thực hiện truy vấn nặng có thể chiếm nhiều CPU và RAM. Cần phân biệt active connection với in-flight request hoặc active job. Chọn metric gần với tài nguyên thực sự bị giới hạn.

### Giới hạn connection pool và dependency

Khi scale out, tổng số kết nối tới database thường tăng theo số instance nhân với pool size. Nếu database chỉ chịu được 1.000 connection, cấu hình 20 instance với pool 100 có thể vượt giới hạn ngay cả khi mỗi VM còn CPU. Cần đưa capacity của dependency vào giới hạn autoscaling và thiết kế pool, proxy hoặc queue phù hợp.

## 7. Metric tổng, metric trên mỗi instance và metric chuẩn hóa

Một sai lầm phổ biến là dùng tổng metric để điều khiển số instance mà không tính số instance hiện tại.

| Kiểu metric | Ví dụ | Khi phù hợp | Rủi ro |
|---|---|---|---|
| Aggregate | Tổng CPU, tổng queue depth, tổng request | Đo nhu cầu toàn hệ thống hoặc backlog tổng | Tăng tự nhiên khi số instance tăng; khó đặt target cố định |
| Average per instance | CPU trung bình, request/instance | Target tracking theo năng lực mỗi máy | Trung bình che giấu một target nóng hoặc mất cân bằng |
| Maximum per instance | CPU cao nhất hoặc latency cao nhất | Phát hiện hot spot | Một target lỗi có thể kích hoạt scale out không cần thiết |
| Normalized work | Backlog/worker, request/instance, active job/worker | So sánh với capacity hiện có | Cần mẫu số chính xác và không stale |
| Rate | Request/giây, message/giây | Đo tốc độ nhu cầu | Không thể hiện độ phức tạp hoặc backlog hiện tại |

Khi dùng metric per-instance, chỉ tính instance healthy và sẵn sàng nhận tải. Khi dùng aggregate, xác định rõ policy có cần scale theo tổng nhu cầu hay theo mức sử dụng trung bình.

## 8. Target tracking, step scaling và scheduled scaling

Các autoscaling service có nhiều kiểu policy. Tên và hành vi khác nhau, nhưng có thể nhóm như sau:

### Target tracking

Target tracking giữ một metric quanh giá trị mục tiêu. Ví dụ, giữ CPU trung bình khoảng một mức đã kiểm thử hoặc giữ backlog mỗi worker dưới một ngưỡng. Bộ điều khiển tự tính mức thay đổi capacity theo chênh lệch giữa metric hiện tại và mục tiêu.

Phù hợp khi metric phản ánh trực tiếp mức tải trên mỗi đơn vị capacity và có thể đo ổn định. Cần tránh metric thay đổi theo số instance theo cách làm controller khó hội tụ.

### Step scaling

Step scaling dùng các khoảng metric để quyết định thay đổi số instance theo từng bước. Ví dụ, khi backlog/worker vượt ngưỡng đầu tiên thì thêm 1 worker; nếu vượt ngưỡng cao hơn thì thêm 3 worker. Cách này phù hợp khi hệ thống cần phản ứng khác nhau theo mức độ tải.

### Simple scaling

Simple scaling thường thực hiện một thay đổi capacity theo alarm rồi áp dụng cooldown trước khi quyết định tiếp theo. Nó dễ hiểu nhưng có thể phản ứng chậm với tải thay đổi nhanh.

### Scheduled hoặc predictive scaling

Scheduled scaling phù hợp với tải có lịch rõ, ví dụ tăng capacity trước giờ làm việc hoặc chiến dịch. Predictive scaling dùng lịch sử để dự báo nhu cầu nếu nền tảng hỗ trợ. Dù dự báo tốt, vẫn nên có policy phản ứng với tải thực tế để xử lý sai số.

## 9. Kết hợp nhiều metric

Một workload có thể bị giới hạn bởi nhiều tài nguyên. Dùng một metric duy nhất có thể bỏ sót bottleneck; dùng quá nhiều metric với điều kiện phức tạp có thể khiến policy khó dự đoán.

### Quy tắc scale out và scale in khác nhau

Scale out nên ưu tiên bảo vệ SLO: nếu một metric saturation quan trọng vượt ngưỡng, có thể tăng capacity. Scale in nên bảo thủ hơn: chỉ giảm khi các metric chính đều ổn định trong một khoảng thời gian và không có backlog cần xử lý.

Ví dụ với API:

- Scale out khi CPU per instance cao **hoặc** request per instance vượt capacity đã benchmark.
- Cảnh báo khi p95 latency vượt SLO.
- Không scale out thêm nếu database connection pool đã bão hòa; thay vào đó bảo vệ database và điều tra dependency.
- Chỉ scale in khi CPU, request per instance và latency đều thấp ổn định.

Ví dụ với worker:

- Scale out theo backlog per worker hoặc age of oldest message.
- Giới hạn số worker theo capacity database/API mà worker gọi.
- Không scale in khi còn job dài đang chạy hoặc queue age vượt mục tiêu.
- Dùng checkpoint và graceful shutdown để tránh mất công việc khi scale in.

### Hạn chế xung đột giữa policy

Nếu nhiều policy cùng điều khiển một nhóm, một policy có thể yêu cầu scale out trong khi policy khác yêu cầu scale in. Cần hiểu cách provider kết hợp policy, thường có cơ chế ưu tiên tăng capacity hoặc lấy thay đổi lớn hơn, nhưng không nên dựa vào giả định chung. Tốt hơn là thiết kế một policy rõ ràng hoặc xác định thứ tự ưu tiên và kiểm thử hành vi kết hợp.

## 10. Chu kỳ đo, cooldown và ổn định autoscaling

Metric cần có chu kỳ cập nhật phù hợp với tốc độ thay đổi workload. Nếu dữ liệu cập nhật mỗi 5 phút nhưng burst xảy ra trong 30 giây, autoscaling phản ứng quá muộn. Nếu metric quá nhiễu và policy đánh giá mỗi vài giây, nhóm máy có thể scale lên xuống liên tục.

### Các khoảng thời gian cần phối hợp

- **Metric period:** khoảng thời gian tổng hợp dữ liệu.
- **Evaluation window:** số điểm dữ liệu hoặc thời gian dùng để đánh giá alarm.
- **Instance warm-up:** thời gian VM boot, bootstrap và trở thành healthy.
- **Cooldown/stabilization:** khoảng chờ sau thay đổi để metric phản ánh capacity mới.
- **Health check grace period:** thời gian cho instance khởi tạo trước khi đánh giá sức khỏe theo policy.
- **Scale-in stabilization:** thời gian cần giữ tải thấp trước khi giảm capacity.

Nếu scale out mất 2 phút mới có target healthy, policy cần phản ứng đủ sớm để backlog không vượt SLO trong thời gian chờ. Có thể dùng scheduled/predictive scaling hoặc capacity buffer cho workload có burst nhanh.

### Hysteresis

Hysteresis dùng ngưỡng scale out và scale in khác nhau để tránh dao động. Ví dụ, scale out khi CPU vượt ngưỡng cao; chỉ scale in khi CPU thấp hơn một ngưỡng thấp hơn trong thời gian dài hơn. Cách này tạo vùng ổn định thay vì bật/tắt capacity quanh một điểm duy nhất.

### Warm-up và metric sau scale out

Instance mới có thể chưa nhận traffic ngay, nên CPU trung bình toàn nhóm giảm sau khi thêm máy. Nếu policy phản ứng quá nhanh với sự sụt giảm này, nó có thể scale in ngay sau scale out. Dùng warm-up period hoặc metric chỉ tính target đang phục vụ; xác minh cách autoscaling service xử lý instance mới.

## 11. Tránh scale sai khi dependency bị giới hạn

Autoscaling compute không tự tạo thêm năng lực cho database, cache, network gateway hoặc API ngoài. Khi dependency là bottleneck, tăng số worker có thể làm tình hình xấu hơn.

Các guardrail cần cân nhắc:

- Giới hạn max instance theo số connection an toàn của database.
- Dùng connection pool, proxy hoặc semaphore để giới hạn concurrency downstream.
- Scale worker theo backlog nhưng đặt max concurrency theo throughput dependency.
- Dùng circuit breaker và backoff để giảm request khi dependency lỗi.
- Theo dõi queue age và error rate cùng với CPU/concurrency.
- Tách pool cho workload có mức ưu tiên khác nhau để một loại job không chiếm hết capacity.

Nếu latency tăng đồng thời database CPU, lock wait hoặc connection count tăng, không nên chỉ tăng web instance. Cần xử lý truy vấn, pool, cache hoặc capacity của dependency.

## 12. Xây dựng custom metric có chất lượng

Một số workload cần metric riêng như job weight, số byte còn phải xử lý, số inference token đang chờ hoặc số session hoạt động. Custom metric có thể hữu ích hơn CPU nếu phản ánh trực tiếp đơn vị công việc.

### Nguyên tắc thiết kế

1. **Đơn vị rõ ràng:** message, request, job-second, byte, token hoặc work unit.
2. **Có định nghĩa mẫu số:** per instance, per healthy worker hay tổng hệ thống.
3. **Cập nhật đủ thường xuyên:** phù hợp với thời gian scale và thời gian xử lý.
4. **Không stale:** phân biệt giá trị bằng 0 với không có dữ liệu.
5. **Có giới hạn và kiểm tra:** phát hiện metric âm, đột biến không hợp lệ hoặc mất telemetry.
6. **Có thể liên kết với capacity:** benchmark để biết một instance xử lý an toàn bao nhiêu work unit.

### Ví dụ custom metric

Một worker xử lý tài liệu có thể phát metric `pending_work_units` thay vì chỉ đếm số file. File PDF nhỏ có 1 work unit, tài liệu scan lớn có nhiều trang có thể được quy đổi thành nhiều unit dựa trên kích thước hoặc số trang. Policy scale theo pending work units trên mỗi worker sẽ phản ánh tải tốt hơn nếu phép quy đổi tương quan với thời gian xử lý.

Không nên đưa ID người dùng, request ID hoặc label có cardinality rất cao vào metric dimension nếu hệ thống metrics tính phí hoặc bị giới hạn cardinality. Dùng tag/label tổng quát như service, environment, queue và worker pool.

## 13. Ví dụ chọn metric cho các workload

| Workload | Metric chính | Metric phụ/guardrail | Lý do |
|---|---|---|---|
| API CPU-bound | CPU per instance hoặc request per instance | p95 latency, error rate | CPU phản ánh saturation; latency bảo vệ SLO |
| API chờ database | In-flight request hoặc request per instance có giới hạn | DB connection, query latency, error rate | CPU thấp không phát hiện pool hoặc dependency bị nghẽn |
| Worker xử lý message | Backlog per worker | Oldest message age, processing rate, downstream capacity | Đo lượng công việc đang chờ và deadline |
| Batch job | Pending work units / estimated remaining duration | Job age, completion deadline | Số job có thể khác nhau rất lớn về chi phí |
| WebSocket service | Active sessions per instance | Memory, network throughput, reconnect rate | Session lâu dài có thể tiêu thụ connection và RAM |
| GPU inference | Requests hoặc tokens per GPU/instance | GPU utilization, VRAM, p95 latency | CPU không phản ánh saturation của accelerator |
| Video transcoding | Queue work units hoặc job duration estimate | GPU/CPU utilization, storage throughput | Chi phí mỗi job phụ thuộc codec, độ phân giải và thời lượng |
| Serverless worker | Concurrency và queue age | Throttle, duration, downstream connection | Runtime có thể giới hạn concurrency trước khi CPU là bottleneck |

### Ví dụ API web

Một API có 4 VM. Benchmark cho thấy mỗi VM xử lý ổn định khoảng 150 request/giây ở p95 latency dưới mục tiêu. Với headroom, nhóm đặt target 100 request/giây mỗi VM. Khi tổng request tăng lên 700 request/giây, capacity cần khoảng 7 VM theo target đã chọn. Policy target tracking theo request per healthy instance có thể tăng capacity; CPU và p95 latency dùng làm guardrail để xác nhận giả định.

Đây là con số minh họa. Capacity thực tế cần benchmark theo request mix, dependency, cache hit ratio và cấu hình máy.

### Ví dụ worker queue

Một queue có 9.000 message. Mục tiêu backlog là 300 message mỗi worker; hiện có 10 worker khỏe nên backlog/worker là 900. Autoscaler cần tăng worker. Tuy nhiên, nếu mỗi worker mở 20 database connection và database chỉ cho phép thêm 100 connection, không thể tăng worker tùy ý. Phải giới hạn worker, giảm pool hoặc tăng capacity database trước.

### Ví dụ dịch vụ inference GPU

CPU của VM chỉ 25%, nhưng GPU utilization gần bão hòa, VRAM còn ít và p95 latency tăng. Scale theo CPU sẽ không kích hoạt. Metric phù hợp hơn là request/token trên mỗi GPU, GPU utilization hoặc queue age, kết hợp VRAM và latency. Nếu model load mất 3 phút, cần warm-up period và capacity dự phòng để xử lý burst.

## 14. Kiểm thử và hiệu chỉnh policy

Không chọn target chỉ dựa trên kinh nghiệm chung. Cần kiểm thử dưới tải đại diện:

1. Xác định SLO, request mix, message size và dependency.
2. Đo throughput an toàn của một instance/worker/GPU.
3. Tăng tải theo bước và ghi lại CPU, latency, queue, concurrency, memory và lỗi.
4. Xác định metric nào thay đổi trước khi SLO suy giảm.
5. Chọn target và ngưỡng có headroom cho thời gian khởi tạo máy.
6. Thử burst, tải tăng chậm, tải giảm, dependency chậm và mất một zone.
7. Kiểm tra scale out có đạt capacity kịp thời không và scale in có làm gián đoạn job không.
8. Điều chỉnh cooldown, warm-up, min/max capacity và scale-in protection.

Theo dõi cả thời gian từ metric vượt ngưỡng đến khi target mới healthy. Nếu quá trình này dài hơn thời gian backlog tăng tới giới hạn, cần capacity buffer, scheduled scaling hoặc cải thiện thời gian boot/bootstrap.

## 15. Troubleshooting autoscaling metric

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| CPU cao nhưng không scale out | Alarm/policy sai, metric không publish, max capacity đã đạt | Kiểm tra alarm state, policy, quota và max size |
| Scale out liên tục dù latency không đổi | Metric aggregate tăng theo số instance hoặc target sai | Kiểm tra metric normalization và mẫu số |
| Queue lớn nhưng worker không tăng | Queue metric stale, quyền publish hoặc policy không gắn đúng group | Kiểm tra metric timestamp, IAM và autoscaling activity |
| Worker tăng nhưng oldest message age vẫn cao | Job bị kẹt, partition nóng hoặc dependency chậm | Kiểm tra consumer error, poison message và downstream |
| Scale out rồi scale in ngay | Warm-up/cooldown không phù hợp, metric bị pha loãng | Kiểm tra instance warm-up, stabilization và hysteresis |
| p95 latency cao nhưng không scale | Metric không được thu thập đúng scope hoặc alarm window quá dài | Kiểm tra percentile, sample count và evaluation period |
| Scale out làm database lỗi nặng hơn | Concurrency downstream vượt capacity | Giới hạn pool, worker max và circuit breaker |
| Một VM nóng nhưng average thấp | Aggregate che giấu hot spot hoặc traffic không đều | Xem per-instance/max metric, stickiness và target health |
| Scale in làm mất job | Không có draining/checkpoint hoặc termination quá sớm | Kiểm tra lifecycle hook và graceful shutdown |
| Metric mất dữ liệu bị hiểu là 0 | Missing-data policy sai | Phân biệt no data với zero và cảnh báo telemetry |

Khi điều tra, đối chiếu metric với autoscaling activity history, instance lifecycle, target health và log ứng dụng theo cùng mốc thời gian.

## 16. Checklist chọn metric

**Hiểu workload:**

- [ ] Xác định đơn vị công việc và tốc độ đến.
- [ ] Xác định bottleneck thường gặp: CPU, RAM, I/O, network, GPU, connection hay dependency.
- [ ] Xác định SLO về latency, throughput, queue age hoặc completion time.
- [ ] Đo capacity an toàn trên mỗi instance/worker.

**Thiết kế metric:**

- [ ] Chọn metric chính gắn với bottleneck hoặc nhu cầu.
- [ ] Xác định aggregate hay per-instance/per-worker.
- [ ] Dùng healthy capacity làm mẫu số khi chuẩn hóa.
- [ ] Có metric phụ để phát hiện dependency hoặc chất lượng dịch vụ.
- [ ] Định nghĩa đơn vị, chu kỳ cập nhật, missing data và owner.

**Cấu hình policy:**

- [ ] Chọn target tracking, step, scheduled hoặc predictive phù hợp.
- [ ] Đặt min/max capacity theo quota và dependency.
- [ ] Cấu hình warm-up, cooldown, stabilization và hysteresis.
- [ ] Bảo vệ job dài và connection khi scale in.
- [ ] Kiểm tra cách nhiều policy kết hợp nếu có hơn một metric.

**Kiểm thử:**

- [ ] Thử tải tăng nhanh, tăng chậm và giảm tải.
- [ ] Thử dependency chậm hoặc không khả dụng.
- [ ] Xác minh scale out hoàn tất trước khi SLO bị vi phạm.
- [ ] Xác minh scale in không làm mất request hoặc job.
- [ ] Đo chi phí và tỷ lệ capacity nhàn rỗi sau hiệu chỉnh.

## Kết luận

CPU phù hợp với workload bị giới hạn bởi tính toán; latency phản ánh chất lượng phục vụ nhưng có thể là tín hiệu trễ; queue depth và oldest message age phù hợp với worker bất đồng bộ; concurrency phù hợp khi số công việc đồng thời là giới hạn chính. Metric nên được chuẩn hóa theo số instance hoặc worker khỏe, kết hợp với dependency guardrail và SLO. Hãy benchmark để xác định capacity an toàn, chọn policy có warm-up/cooldown và hysteresis phù hợp, rồi kiểm thử cả scale out lẫn scale in. Một policy tốt tăng máy khi thêm capacity thực sự cải thiện khả năng phục vụ và giảm máy khi hệ thống có đủ headroom mà không làm gián đoạn công việc.
