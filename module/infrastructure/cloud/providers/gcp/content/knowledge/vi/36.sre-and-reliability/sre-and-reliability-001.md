# Áp dụng phương pháp SRE cho dịch vụ trên GCP

Một dịch vụ chạy ổn định trên Google Cloud không chỉ cần hạ tầng có khả năng tự mở rộng. Đội ngũ còn phải biết người dùng đang trải nghiệm dịch vụ ra sao, mức độ gián đoạn nào có thể chấp nhận, khi nào cần can thiệp và làm thế nào để giảm sự cố lặp lại. Site Reliability Engineering (SRE) cung cấp phương pháp để trả lời những câu hỏi đó bằng các chỉ số đo được, tự động hóa và quy trình vận hành có kỷ luật.

SRE kết hợp kỹ thuật phần mềm với vận hành hệ thống. Thay vì chỉ phản ứng khi máy chủ báo lỗi, đội ngũ bắt đầu từ trải nghiệm người dùng, đặt mục tiêu độ tin cậy, theo dõi error budget và cải thiện thiết kế dịch vụ theo dữ liệu thực tế. Trên GCP, các nguyên tắc này có thể áp dụng cho Cloud Run, Google Kubernetes Engine (GKE), Compute Engine, Cloud SQL, Pub/Sub và các hệ thống phân tán kết hợp nhiều dịch vụ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của SRE và phân biệt SLI, SLO, SLA và error budget.
- Chọn chỉ số độ tin cậy phản ánh trải nghiệm người dùng.
- Thiết lập cách quan sát dịch vụ bằng Cloud Monitoring, Cloud Logging, Cloud Trace và các công cụ liên quan.
- Thiết kế cảnh báo theo tốc độ tiêu thụ error budget.
- Tổ chức trực vận hành, xử lý sự cố và viết postmortem không quy lỗi cá nhân.
- Áp dụng canary, rollback, tự động hóa và quản lý toil.
- Thiết kế khả năng chịu lỗi, năng lực phục vụ và khôi phục thảm họa cho workload trên GCP.

## 1. SRE là gì và vì sao cần áp dụng?

SRE là cách vận hành dịch vụ bằng các phương pháp kỹ thuật có thể đo lường và tự động hóa. Mục tiêu là giữ cho dịch vụ đủ tin cậy đối với người dùng trong khi vẫn cho phép nhóm phát triển phát hành tính năng thường xuyên.

SRE không đồng nghĩa với việc tối đa hóa uptime bằng mọi giá. Một hệ thống có thể đạt uptime cao nhưng vẫn chậm, trả dữ liệu sai hoặc không hoàn thành giao dịch quan trọng. Ngược lại, đầu tư quá mức vào độ tin cậy có thể làm tăng chi phí và làm chậm đổi mới mà không tạo thêm giá trị tương xứng cho người dùng.

SRE giúp đội ngũ cân bằng ba mục tiêu:

- **Trải nghiệm người dùng:** các luồng quan trọng hoạt động đúng, đủ nhanh và có thể sử dụng.
- **Tốc độ thay đổi:** nhóm có thể phát hành, sửa lỗi và cải tiến sản phẩm.
- **Chi phí vận hành:** tài nguyên, trực ca và công sức bảo trì nằm trong mức tổ chức có thể duy trì.

### SRE và vận hành truyền thống

Trong cách vận hành chỉ dựa vào phản ứng, nhóm thường theo dõi CPU, RAM, số lượng instance và xử lý cảnh báo khi một ngưỡng kỹ thuật bị vượt. Các chỉ số này hữu ích để chẩn đoán, nhưng chưa chắc cho biết người dùng có gặp vấn đề hay không.

SRE bổ sung một lớp đo lường theo dịch vụ:

1. Xác định hành trình hoặc thao tác quan trọng của người dùng.
2. Định nghĩa điều gì được xem là một sự kiện tốt.
3. Đặt mục tiêu chất lượng trong một khoảng thời gian.
4. Đo mức tiêu thụ error budget.
5. Dùng dữ liệu để quyết định tốc độ phát hành, đầu tư độ tin cậy và tự động hóa.

Một dịch vụ thanh toán có thể chạy trên các VM khỏe mạnh nhưng giao dịch vẫn thất bại vì kết nối Cloud SQL cạn kiệt. Một dịch vụ Cloud Run có thể trả HTTP 200 nhưng mất nhiều giây mới hoàn tất yêu cầu. SRE hướng việc giám sát vào kết quả mà người dùng thực sự nhận được.

## 2. SLI, SLO, SLA và error budget

Đây là bốn khái niệm nền tảng để đưa độ tin cậy thành mục tiêu có thể quản lý.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| SLI (Service Level Indicator) | Chỉ số đo chất lượng dịch vụ | Tỷ lệ request thành công và hoàn tất dưới 300 ms |
| SLO (Service Level Objective) | Mục tiêu cần đạt cho một SLI trong một cửa sổ thời gian | 99,9% request hợp lệ đạt điều kiện trong 30 ngày |
| SLA (Service Level Agreement) | Cam kết dịch vụ với khách hàng, có thể kèm điều khoản bồi hoàn | Cam kết availability theo hợp đồng |
| Error budget | Mức lỗi được phép xảy ra trong cửa sổ SLO mà vẫn đạt mục tiêu | 0,1% request được phép không đạt |

SLI là phép đo; SLO là mục tiêu nội bộ hoặc mục tiêu vận hành; SLA là cam kết bên ngoài. SLO thường được đặt chặt chẽ hơn hoặc có khoảng đệm so với SLA để nhóm có thời gian phát hiện và khắc phục trước khi vi phạm cam kết.

### Chọn SLI từ góc nhìn người dùng

Một SLI tốt phản ánh điều mà người dùng quan tâm, có thể đo ổn định và có mẫu số rõ ràng. Một số nhóm SLI phổ biến:

| Nhóm SLI | Cách đo | Câu hỏi cần trả lời |
|---|---|---|
| Availability | Số sự kiện thành công / tổng sự kiện hợp lệ | Người dùng có hoàn thành thao tác không? |
| Latency | Tỷ lệ request hoàn thành dưới ngưỡng thời gian | Dịch vụ có đủ nhanh không? |
| Throughput | Số request hoặc tác vụ hoàn thành trong một đơn vị thời gian | Dịch vụ có xử lý đủ tải không? |
| Freshness | Tỷ lệ dữ liệu được cập nhật trong thời hạn quy định | Dữ liệu có đủ mới không? |
| Correctness | Tỷ lệ kết quả đáp ứng quy tắc nghiệp vụ | Dịch vụ có trả kết quả đúng không? |
| Durability | Tỷ lệ dữ liệu được giữ nguyên và có thể truy xuất | Dữ liệu có bị mất hoặc hỏng không? |

Không phải dịch vụ nào cũng cần tất cả SLI. Với API thanh toán, availability, latency và correctness của giao dịch thường quan trọng. Với pipeline dữ liệu, freshness, completeness và correctness có thể quan trọng hơn latency của từng request.

### Định nghĩa request tốt và request hợp lệ

Trước khi tính SLI, đội ngũ cần thống nhất:

- Request nào thuộc phạm vi đo?
- Health check, bot, request nội bộ hoặc retry có được tính không?
- Lỗi do người dùng gửi dữ liệu không hợp lệ có được tính là lỗi dịch vụ không?
- HTTP 429 do giới hạn năng lực có được xem là bad event không?
- Request timeout sau khi client ngắt kết nối được xử lý ra sao?
- Một giao dịch nhiều bước chỉ được xem là thành công khi nào?

Không có một quy tắc HTTP status chung cho mọi dịch vụ. Ví dụ, 4xx có thể là lỗi đầu vào do người dùng, nhưng 429 do hệ thống quá tải có thể là lỗi trải nghiệm mà SLO cần tính. Hãy định nghĩa điều kiện good event theo hợp đồng API và hành trình thực tế.

### Ví dụ xây dựng SLO cho API checkout

Giả sử API checkout nhận các request hợp lệ từ ứng dụng mua sắm. Đội ngũ định nghĩa một request tốt khi:

- Giao dịch hoàn tất theo quy tắc nghiệp vụ.
- Phản hồi thành công được trả về.
- Thời gian xử lý dưới 300 ms.

SLO mẫu:

**Trong mỗi cửa sổ 30 ngày, ít nhất 99,9% request checkout hợp lệ phải hoàn tất thành công trong vòng 300 ms.**

Đây là SLO theo request: tử số là số request tốt, mẫu số là tổng request hợp lệ. Một request chỉ được tính tốt khi thỏa cả điều kiện kết quả và latency.

Để đo riêng hai khía cạnh, có thể định nghĩa hai SLO:

- Availability: ít nhất 99,9% request hợp lệ hoàn tất thành công trong 30 ngày.
- Latency: ít nhất 99% request hợp lệ hoàn tất dưới 300 ms trong 30 ngày.

Hai SLO giúp xác định sự cố do lỗi chức năng hay do hiệu năng. SLO kết hợp phù hợp khi trải nghiệm chỉ được xem là tốt nếu đồng thời thỏa cả hai điều kiện.

## 3. Tính error budget và dùng nó để ra quyết định

Error budget là phần sự kiện xấu mà dịch vụ có thể có trong kỳ đánh giá mà vẫn đạt SLO.

Công thức với request-based SLO:

~~~text
Error budget = (1 - SLO goal) × số eligible events trong kỳ
~~~

Ví dụ SLO là 99,9%, nghĩa là tỷ lệ lỗi cho phép là 0,1%. Nếu trong kỳ có 1.000.000 request hợp lệ:

~~~text
Error budget = (1 - 0,999) × 1.000.000
             = 1.000 request lỗi
~~~

Nếu SLI được đo bằng thời gian availability thay vì số request, cùng mục tiêu 99,9% trong 30 ngày tương đương khoảng 43,2 phút không sẵn sàng liên tục. Không được lấy con số thời gian này áp dụng trực tiếp cho request-based SLO; hai loại SLI có mẫu số và cách tính khác nhau.

### Error budget policy

Error budget tạo cơ sở thống nhất giữa nhóm sản phẩm, phát triển và vận hành. Một policy mẫu có thể là:

| Trạng thái budget | Quyết định tham khảo |
|---|---|
| Còn trên 50% | Tiếp tục phát hành theo quy trình bình thường, vẫn theo dõi SLO |
| Còn 25–50% | Tăng mức kiểm tra, ưu tiên sửa lỗi và giảm thay đổi có rủi ro cao |
| Còn dưới 25% | Yêu cầu đánh giá reliability trước khi phát hành tính năng lớn |
| Đã cạn | Tạm dừng thay đổi không thiết yếu có rủi ro, tập trung khắc phục nguyên nhân làm mất budget |

Các ngưỡng trên chỉ là ví dụ. Tổ chức cần thống nhất policy theo mức độ quan trọng của dịch vụ, cam kết với khách hàng và mức rủi ro chấp nhận được. Policy cũng nên có ngoại lệ rõ ràng cho bản vá bảo mật khẩn cấp hoặc thay đổi cần thiết để khôi phục dịch vụ.

Error budget không nhằm phạt nhóm phát triển. Nó giúp mọi bên cùng nhìn thấy chi phí của sự cố và quyết định có căn cứ khi cần chọn giữa tốc độ phát hành và độ tin cậy.

## 4. Thiết kế observability cho dịch vụ trên GCP

Observability là khả năng hiểu trạng thái nội tại của hệ thống từ telemetry mà hệ thống phát ra. Ba loại tín hiệu phổ biến là metrics, logs và traces; mỗi loại trả lời một nhóm câu hỏi khác nhau.

| Telemetry | Vai trò | Công cụ GCP thường dùng |
|---|---|---|
| Metrics | Đo xu hướng và trạng thái theo thời gian | Cloud Monitoring, Managed Service for Prometheus |
| Logs | Ghi sự kiện và ngữ cảnh chi tiết | Cloud Logging |
| Traces | Theo dõi một request qua nhiều thành phần | Cloud Trace, OpenTelemetry |
| Error events | Nhóm và theo dõi lỗi ứng dụng | Error Reporting |
| Profiling | Phân tích CPU và heap để tìm điểm nghẽn | Cloud Profiler |

Google Cloud Observability cung cấp các công cụ để thu thập, truy vấn, hiển thị và cảnh báo từ những tín hiệu này. Tùy runtime, có thể dùng telemetry tích hợp sẵn hoặc cài agent/collector.

### Bốn golden signals

Bốn tín hiệu thường được dùng để bắt đầu giám sát một dịch vụ là:

1. **Latency:** thời gian xử lý request. Nên phân biệt latency thành công và latency của request lỗi vì lỗi trả về nhanh có thể làm số trung bình đẹp hơn trong khi người dùng vẫn không hoàn thành thao tác.
2. **Traffic:** lượng request, message hoặc tác vụ mà hệ thống đang nhận.
3. **Errors:** tỷ lệ thao tác thất bại, bao gồm lỗi ứng dụng, timeout và lỗi phụ thuộc.
4. **Saturation:** mức độ tài nguyên hoặc hàng đợi đang tiến gần giới hạn, chẳng hạn CPU, memory, connection pool, concurrency hoặc backlog.

Golden signals là điểm khởi đầu để quan sát dịch vụ. Chúng không thay thế SLI/SLO: CPU thấp không chứng minh checkout thành công, còn error rate thấp có thể che giấu lỗi dữ liệu hoặc độ trễ cao.

### Chọn telemetry theo loại workload

| Workload GCP | Tín hiệu nên theo dõi |
|---|---|
| Cloud Run service | Request count, request latency, response code, instance/concurrency, startup và lỗi revision |
| GKE | Request theo service, pod readiness, restart, CPU/memory, node pressure, ingress và network |
| Compute Engine | CPU, memory, disk I/O, network, process và tình trạng VM/instance group |
| Cloud SQL | Connection count, query latency, CPU, storage, lock, replication lag và lỗi kết nối |
| Pub/Sub | Backlog, oldest unacked message age, publish/delivery rate, redelivery và dead-letter |
| Data pipeline | Thời điểm dữ liệu mới nhất, số bản ghi xử lý, số bản ghi lỗi và thời gian hoàn tất batch |

Với Compute Engine, Ops Agent có thể thu thập metrics và logs của hệ điều hành. Với GKE, Managed Service for Prometheus có thể thu thập metrics Prometheus từ workload. Ứng dụng đa nền tảng có thể instrument bằng OpenTelemetry để gửi traces, metrics và logs đến backend quan sát tương ứng.

### Liên kết logs, metrics và traces

Để điều tra một request chậm:

- Metrics cho thấy latency tăng vào thời điểm nào và ảnh hưởng bao nhiêu phần trăm traffic.
- Logs cho biết request gặp lỗi gì, input hoặc dependency nào liên quan.
- Trace cho thấy request đi qua API gateway, Cloud Run, Pub/Sub và Cloud SQL mất bao lâu ở từng bước.
- Error Reporting giúp nhóm các lỗi ứng dụng lặp lại.
- Profiler giúp tìm hàm hoặc đường thực thi tiêu tốn CPU/heap khi cần.

Nên dùng structured logging, có severity, service name, version và trace identifier khi phù hợp. Tránh đưa token, mật khẩu, dữ liệu cá nhân hoặc payload nhạy cảm vào log. Giới hạn nhãn metric có cardinality cao như user ID, email hoặc request ID; các giá trị duy nhất không phù hợp làm metric label vì có thể làm tăng chi phí và ảnh hưởng truy vấn.

## 5. Xây dựng SLO và cảnh báo trong Cloud Monitoring

Cloud Monitoring có Service Monitoring và SLO API để mô tả service, SLI, mục tiêu và compliance period. Có thể tạo SLO từ metrics hoặc cấu hình SLI theo loại service và nguồn dữ liệu hỗ trợ.

Một SLO nên có các thành phần:

- Service và owner chịu trách nhiệm.
- SLI definition, gồm numerator và denominator hoặc điều kiện good event.
- Goal, ví dụ 99,9%.
- Compliance period, ví dụ rolling 30 days hoặc calendar month.
- Nguồn telemetry và cách loại trừ traffic không thuộc phạm vi.
- Alert policy và kênh thông báo.

### Ví dụ SLI bằng PromQL

Giả sử ứng dụng xuất một counter tên **http_server_requests_total** với nhãn **service** và **sli_outcome**. Ứng dụng gắn **sli_outcome="good"** khi request thỏa định nghĩa thành công đã thống nhất.

Tỷ lệ request tốt trong 5 phút:

~~~promql
sum(rate(http_server_requests_total{
  service="checkout",
  sli_outcome="good"
}[5m]))
/
sum(rate(http_server_requests_total{
  service="checkout"
}[5m]))
~~~

Đây là ví dụ metric tùy chỉnh do ứng dụng instrument, không phải tên metric mặc định của mọi workload GCP. Cần xử lý trường hợp mẫu số bằng 0 và xác định cửa sổ đo phù hợp. Khi tạo SLO dài hạn, Cloud Monitoring đánh giá SLI trên compliance period đã cấu hình, không chỉ dựa trên một cửa sổ 5 phút.

Ví dụ đo tỷ lệ request có latency dưới 300 ms bằng histogram Prometheus:

~~~promql
sum(rate(http_server_request_duration_seconds_bucket{
  service="checkout",
  le="0.3"
}[5m]))
/
sum(rate(http_server_request_duration_seconds_count{
  service="checkout"
}[5m]))
~~~

Ví dụ thứ hai giả định ứng dụng xuất histogram có bucket tại 0,3 giây và metric count tương ứng. Hãy kiểm tra metric thực tế và quy ước instrument trước khi dùng truy vấn trong môi trường production.

### Alert theo burn rate

Burn rate cho biết error budget đang bị tiêu thụ nhanh đến mức nào so với tốc độ cần thiết để giữ SLO.

~~~text
Burn rate = tỷ lệ bad events thực tế / tỷ lệ bad events cho phép
~~~

Với SLO 99,9%, tỷ lệ lỗi cho phép là 0,1%. Nếu trong khoảng đo có 1,44% request lỗi:

~~~text
Burn rate = 1,44% / 0,1% = 14,4
~~~

Nếu tốc độ này kéo dài, budget 30 ngày sẽ bị tiêu thụ hết trong khoảng 30 / 14,4 = 2,08 ngày. Burn rate cao có thể báo hiệu sự cố đang diễn ra trước khi SLO cuối kỳ bị vi phạm.

Nên kết hợp nhiều cửa sổ thời gian để phân biệt sự cố nghiêm trọng với nhiễu ngắn hạn. Ví dụ, một policy có thể kiểm tra burn rate trên cửa sổ 1 giờ và 5 phút; một policy khác dùng 6 giờ và 30 phút. Các cặp cửa sổ, ngưỡng và thời gian duy trì phải được điều chỉnh theo traffic và mức độ quan trọng của service.

Cảnh báo nên được chia theo hành động:

- **Page/on-call:** lỗi người dùng tăng nhanh, budget bị tiêu thụ mạnh hoặc dịch vụ không thể hoàn thành thao tác quan trọng.
- **Ticket/work queue:** budget suy giảm từ từ, độ trễ tăng nhẹ hoặc tài nguyên sắp chạm ngưỡng nhưng chưa ảnh hưởng nghiêm trọng.
- **Dashboard/trend:** tín hiệu phục vụ phân tích dài hạn, capacity planning và cải thiện kiến trúc.

Không nên gửi page cho mọi lần CPU tăng hoặc một pod restart đơn lẻ. Hãy ưu tiên cảnh báo dựa trên triệu chứng và ảnh hưởng tới SLO; metrics hạ tầng hỗ trợ xác định nguyên nhân sau khi cảnh báo xảy ra.

## 6. Tổ chức incident response và on-call

Khi có sự cố, mục tiêu đầu tiên là giảm ảnh hưởng đến người dùng và khôi phục dịch vụ. Việc tìm nguyên nhân gốc cần thiết nhưng không được làm chậm hành động giảm thiểu tác động.

Một quy trình incident response có thể gồm:

1. **Detect:** cảnh báo từ SLO, monitoring hoặc báo cáo người dùng.
2. **Triage:** xác định mức độ nghiêm trọng, phạm vi ảnh hưởng, service và dependency liên quan.
3. **Declare:** chỉ định incident commander và mở kênh điều phối phù hợp.
4. **Mitigate:** rollback, giảm traffic, tắt feature flag, chuyển sang chế độ degraded hoặc cô lập dependency.
5. **Communicate:** cập nhật trạng thái, ảnh hưởng và thời điểm cập nhật tiếp theo cho các bên liên quan.
6. **Recover:** xác nhận service trở lại mức chất lượng chấp nhận được và theo dõi để tránh tái phát ngay.
7. **Review:** tổng hợp timeline, nguyên nhân đóng góp, hiệu quả phản ứng và action items.

### Vai trò trong incident

Với sự cố lớn, nên phân chia trách nhiệm:

- **Incident commander:** điều phối, ưu tiên công việc và ra quyết định tổng thể.
- **Operations lead:** điều tra kỹ thuật, thực hiện giảm thiểu và khôi phục.
- **Communications lead:** cập nhật trạng thái cho khách hàng, quản lý và nhóm liên quan.
- **Scribe:** ghi timeline, quyết định, tác động và hành động đã thực hiện.

Một người có thể đảm nhiệm nhiều vai trò trong sự cố nhỏ, nhưng cần làm rõ ai đang chịu trách nhiệm để tránh nhiều người cùng thay đổi production mà không phối hợp.

### Runbook và escalation

Runbook nên ghi:

- Triệu chứng và alert liên quan.
- Cách xác định service, revision, cluster hoặc dependency bị ảnh hưởng.
- Dashboard và log query cần mở.
- Các bước giảm thiểu đã được kiểm chứng.
- Điều kiện rollback hoặc failover.
- Người hoặc nhóm cần escalation.
- Các bước xác nhận phục hồi và cách ghi nhận sự cố.

Runbook phải được cập nhật sau khi hệ thống thay đổi. Một tài liệu không còn khớp với production có thể làm sự cố kéo dài hơn.

### Postmortem không quy lỗi cá nhân

Sau sự cố đáng kể, nhóm nên viết postmortem tập trung vào hệ thống và điều kiện dẫn đến lỗi. Nội dung thường có:

- Tóm tắt và mức ảnh hưởng.
- Timeline phát hiện, phản ứng và khôi phục.
- Những gì đã xảy ra và vì sao hệ thống cho phép tình huống đó xảy ra.
- Điều gì hoạt động tốt và điều gì gây chậm trễ.
- Action items, owner và thời hạn.

Blameless postmortem không có nghĩa là bỏ qua trách nhiệm. Mục tiêu là hiểu vì sao một quyết định hợp lý trong bối cảnh lúc đó vẫn dẫn đến kết quả xấu, rồi cải thiện guardrail, quy trình, telemetry hoặc thiết kế để giảm khả năng tái diễn.

## 7. Giảm toil bằng tự động hóa

Toil là công việc vận hành lặp đi lặp lại, thủ công, có tính phản ứng và không tạo ra giá trị lâu dài tương xứng. Ví dụ:

- Mỗi lần deploy đều phải thực hiện cùng một chuỗi lệnh thủ công.
- Nhân viên trực ca phải xóa queue hoặc restart workload theo cùng một quy trình.
- Nhóm vận hành phải tổng hợp số liệu SLO bằng tay mỗi tuần.
- Một cảnh báo nhiễu luôn cần người mở ticket rồi đóng lại.

Đội ngũ SRE cần đo toil và tìm cơ hội tự động hóa. Ưu tiên công việc có tần suất cao, rủi ro thao tác lớn hoặc làm chậm phản ứng khi có sự cố.

Ví dụ tự động hóa trên GCP:

| Công việc | Cách cải thiện |
|---|---|
| Deploy lặp lại | Cloud Build và Cloud Deploy với pipeline chuẩn |
| Kiểm tra SLO | Cloud Monitoring dashboard và alert policy |
| Phát hiện lỗi ứng dụng | Error Reporting và log-based metrics |
| Mở rộng workload | Cloud Run autoscaling, GKE autoscaler hoặc Managed Instance Group autoscaling |
| Xử lý message lỗi | Dead-letter topic, retry có giới hạn và quy trình replay |
| Phát hiện drift cấu hình | Terraform plan, policy validation và quy trình review |
| Tạo báo cáo vận hành | Truy vấn metrics/logs và xuất báo cáo theo lịch |

Tự động hóa cần guardrail. Ví dụ, tự động restart workload có thể che giấu memory leak; tự động retry không giới hạn có thể làm dependency quá tải. Hãy xác định điều kiện kích hoạt, giới hạn số lần, timeout, quyền thực thi và cách rollback trước khi tự động hóa thao tác production.

## 8. Phát hành an toàn với canary và rollback

Một thay đổi mới có thể làm giảm độ tin cậy ngay cả khi unit test và integration test đều thành công. SRE dùng progressive delivery để giảm số người dùng bị ảnh hưởng khi phát hiện lỗi.

### Canary deployment

Canary triển khai phiên bản mới cho một phần traffic trước, quan sát SLI và tăng dần tỷ lệ nếu kết quả tốt. Ví dụ:

~~~text
Phiên bản cũ: 100%
        |
        v
Canary 5% traffic
        |
        v
Đánh giá error rate, latency và business metrics
        |
        +---- Không đạt ---> Dừng rollout / rollback
        |
        v
Canary 25% -> 50% -> 100%
~~~

Với Cloud Run, traffic có thể được chia giữa các revision. Với GKE, có thể dùng Cloud Deploy và cấu hình chiến lược canary phù hợp với service networking hoặc Gateway API. Cloud Deploy hỗ trợ canary rollout theo các phase phần trăm và có thể kết hợp deploy analysis để đánh giá metrics trước khi chuyển phase.

### Điều kiện đánh giá canary

Không chỉ quan sát số pod hoặc trạng thái deploy. Hãy so sánh phiên bản mới với phiên bản ổn định về:

- Error rate và latency theo SLI.
- Tỷ lệ hoàn tất thao tác nghiệp vụ.
- Tỷ lệ timeout và lỗi dependency.
- CPU, memory, restart và saturation.
- Queue backlog hoặc độ trễ xử lý message.
- Chi phí trên mỗi request hoặc tác vụ nếu thay đổi ảnh hưởng đến hiệu suất tài nguyên.

Nếu canary có traffic thấp, số liệu có thể chưa đủ đại diện. Có thể cần tăng thời gian quan sát, kiểm thử chủ động hoặc dùng dữ liệu staging phù hợp trước khi tăng tỷ lệ.

### Rollback và feature flag

Rollback đưa workload về phiên bản đã biết là hoạt động tốt. Feature flag cho phép tắt một tính năng mà không cần deploy lại toàn bộ ứng dụng. Hai kỹ thuật có thể phối hợp:

- Nếu lỗi do code mới, rollback về release ổn định.
- Nếu lỗi nằm ở một tính năng, tắt feature flag để giảm ảnh hưởng.
- Nếu schema database đã thay đổi không tương thích, rollback ứng dụng có thể chưa đủ; cần thiết kế migration theo hướng backward-compatible.
- Nếu dữ liệu đã bị ghi sai, cần quy trình sửa dữ liệu và xác minh integrity, không chỉ rollback binary.

Rollback phải được diễn tập. Một nút rollback không có ích nếu release trước không còn tương thích với schema, secret, API hoặc cấu hình hiện tại.

## 9. Thiết kế resilience cho workload GCP

Resilience là khả năng duy trì hoặc khôi phục chức năng khi một thành phần gặp lỗi. Không có một mẫu kiến trúc duy nhất cho mọi service; cần bắt đầu từ SLO, RTO/RPO và failure mode của dependency.

### Timeout, retry và backoff

Một request qua nhiều service có thể bị nhân thời gian chờ nếu mỗi dependency dùng timeout quá dài. Hãy đặt timeout rõ ràng cho từng hop và bảo đảm tổng thời gian xử lý nằm trong ngân sách latency của request.

Retry cần có:

- Exponential backoff để tăng dần khoảng chờ.
- Jitter để tránh nhiều client retry cùng lúc.
- Giới hạn số lần thử và deadline tổng.
- Idempotency key hoặc cơ chế chống ghi trùng cho thao tác có side effect.
- Quy tắc phân loại lỗi retry được và lỗi không nên retry.

Không retry vô hạn lỗi 4xx hoặc lỗi cấu hình. Nếu dependency đang quá tải, retry dồn dập có thể khuếch đại sự cố. Circuit breaker, concurrency limit và rate limit giúp ngăn workload tiếp tục gửi traffic vào thành phần đang mất khả năng phục vụ.

### Queue và xử lý bất đồng bộ

Pub/Sub có thể tách producer khỏi consumer, hấp thụ burst và cho phép xử lý lại message. Tuy nhiên, queue cũng có thể tích tụ khi consumer chậm hoặc message liên tục lỗi.

Cần theo dõi oldest unacked message age, backlog, delivery attempts và dead-letter topic. Consumer nên idempotent để message được gửi lại không tạo giao dịch trùng. Đặt retry policy, ack deadline và dead-letter policy phù hợp với loại công việc.

### Failure domain và high availability

Đối với workload quan trọng:

- Triển khai qua nhiều zone khi runtime và dịch vụ hỗ trợ.
- Dùng load balancing và health check để ngừng gửi traffic tới instance không khỏe.
- Cấu hình autoscaling nhưng vẫn đặt giới hạn quota và capacity.
- Xác định dependency nào là single point of failure.
- Kiểm tra hành vi khi mất zone, mất kết nối database hoặc một vùng cloud bị gián đoạn.
- Với multi-region, thiết kế replication, routing, consistency và failover trước khi sự cố xảy ra.

Chạy hai instance trong cùng một zone không bảo vệ được trước sự cố của zone. Multi-region cũng không tự động giải quyết mọi vấn đề: dữ liệu có thể chưa replicate, failover có thể gây split-brain hoặc tăng latency. Phải thử nghiệm đường khôi phục với dữ liệu và traffic gần thực tế.

### Degraded mode và graceful degradation

Khi một dependency không thiết yếu bị lỗi, service có thể tiếp tục cung cấp chức năng cốt lõi. Ví dụ, trang sản phẩm vẫn hiển thị thông tin đã cache khi hệ thống đề xuất sản phẩm tạm thời ngừng hoạt động. Tính năng phụ có thể bị tắt trong khi checkout vẫn hoạt động.

Cần xác định rõ:

- Chức năng nào là critical path.
- Dữ liệu nào có thể dùng từ cache và trong bao lâu.
- Khi nào trả stale data, thông báo lỗi hoặc yêu cầu thử lại.
- Hành động nào cần dừng để tránh ghi dữ liệu không nhất quán.

## 10. Capacity planning và hiệu năng

Autoscaling giúp tăng hoặc giảm tài nguyên theo tải, nhưng không thay thế capacity planning. Một dịch vụ có thể không scale kịp burst, chạm quota, hết connection database hoặc bị giới hạn bởi dependency không thể mở rộng tương ứng.

Hãy xác định:

- Traffic trung bình, peak và burst.
- Tốc độ tăng trưởng dự kiến.
- Mức concurrency và resource request/limit.
- Quota theo project, region và API.
- Giới hạn connection, throughput và storage của database.
- Thời gian khởi động instance mới và khả năng warm-up.
- Chi phí tại mức tải bình thường và tải đỉnh.

### Ví dụ theo runtime

**Cloud Run:** theo dõi request latency, concurrency, instance count, startup latency và giới hạn max instances. Nếu max instances quá thấp, dịch vụ có thể trả lỗi hoặc tăng latency khi tải tăng. Nếu đặt quá cao mà Cloud SQL không chịu được số kết nối đồng thời, database có thể trở thành nút thắt.

**GKE:** theo dõi pod resource usage, pending pods, HPA, cluster autoscaler, node pool capacity, restart và readiness. HPA có thể tăng replica nhưng cluster vẫn cần node capacity để schedule pod. Resource request không phù hợp có thể khiến scheduler phân bổ sai hoặc workload bị eviction.

**Compute Engine:** với Managed Instance Group, theo dõi autoscaling, instance health, CPU, disk và network. Kiểm tra quota và thời gian tạo VM; autoscaling không thể tạo thêm capacity nếu project hoặc region đã chạm giới hạn.

Load test cần mô phỏng cả traffic bình thường, burst, dependency chậm và lỗi. Sau mỗi lần thử, hãy cập nhật mô hình capacity, SLO và giới hạn autoscaling.

## 11. Backup, disaster recovery và SLO cho khôi phục

Độ tin cậy không chỉ là uptime. Một hệ thống có thể hoạt động liên tục nhưng mất dữ liệu hoặc không thể khôi phục sau khi xóa nhầm. Cần đặt mục tiêu cho backup và disaster recovery.

Hai chỉ số quan trọng:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa tổ chức chấp nhận mất, thường được biểu diễn bằng thời gian.
- **RTO (Recovery Time Objective):** thời gian tối đa để khôi phục dịch vụ về mức hoạt động chấp nhận được.

Ví dụ, RPO 15 phút nghĩa là trong kịch bản thảm họa, mục tiêu là giới hạn dữ liệu bị mất trong khoảng 15 phút gần nhất. RTO 2 giờ nghĩa là nhóm cần khôi phục dịch vụ trong tối đa 2 giờ. Đây là mục tiêu thiết kế và diễn tập, không phải cam kết tự động từ việc bật backup.

Trên GCP, có thể phối hợp backup của Cloud SQL, snapshot/policy cho Persistent Disk, backup của GKE và dữ liệu lưu trữ theo dịch vụ. Cần kiểm tra tính nhất quán của backup, retention, encryption, quyền truy cập và vị trí lưu bản sao.

Một kế hoạch DR nên có:

1. Danh sách service và dependency theo thứ tự khôi phục.
2. RPO/RTO được chủ sở hữu nghiệp vụ phê duyệt.
3. Backup và replication đã cấu hình.
4. Runbook failover/failback, bao gồm DNS, load balancer, secret và quyền IAM.
5. Cách xác minh tính toàn vẹn dữ liệu sau khôi phục.
6. Lịch diễn tập và bằng chứng thời gian khôi phục thực tế.

Backup chưa từng restore thử không phải là bằng chứng đủ về khả năng khôi phục.

## 12. Quy trình SRE mẫu cho một dịch vụ trên GCP

Giả sử hệ thống thương mại điện tử gồm:

- Cloud Run xử lý API checkout.
- Cloud SQL lưu đơn hàng.
- Pub/Sub phát sự kiện sau khi tạo đơn.
- Một consumer trên GKE xử lý hóa đơn và thông báo.
- Cloud Monitoring, Logging và Trace thu thập telemetry.

Một chu trình SRE có thể được tổ chức như sau:

| Giai đoạn | Việc cần làm | Bằng chứng |
|---|---|---|
| Define | Xác định critical user journey, SLI và SLO | Tài liệu SLO có owner và cửa sổ đo |
| Instrument | Thu thập metrics, logs, traces và business events | Dashboard và trace liên kết được request |
| Alert | Tạo alert theo SLO burn rate và dependency | Alert có ngưỡng, owner và runbook |
| Operate | Trực ca, triage và xử lý sự cố | Incident timeline và cập nhật trạng thái |
| Improve | Viết postmortem, xử lý action items và giảm toil | Issue có owner, deadline và xác minh |
| Release | Canary, đánh giá metrics và rollback khi cần | Rollout có kết quả verify |
| Recover | Kiểm tra backup, failover và restore | Kết quả diễn tập RTO/RPO |

SLO ví dụ cho checkout:

- 99,9% request hợp lệ hoàn tất thành công trong 30 ngày.
- 99% request hợp lệ hoàn tất trong 300 ms.
- 99% message hóa đơn được xử lý trong 5 phút sau khi publish.

Các mục tiêu này chỉ là ví dụ để thảo luận. Chủ sở hữu sản phẩm và kỹ thuật cần xác định SLI, traffic eligibility, thời gian đo và mục tiêu thực tế dựa trên dữ liệu người dùng.

Nếu Cloud SQL chậm làm checkout vượt latency SLO, trace giúp xác định thời gian nằm ở truy vấn database hay ở application. Nếu Pub/Sub backlog tăng nhưng checkout vẫn thành công, có thể đây là vấn đề freshness của luồng hóa đơn thay vì availability của API. Việc tách SLO theo user journey giúp nhóm ưu tiên đúng thành phần cần khắc phục.

## 13. Các sai lầm thường gặp khi áp dụng SRE

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Dùng CPU làm SLI duy nhất | Không phản ánh trải nghiệm người dùng | Đo good events, latency và kết quả nghiệp vụ |
| Đặt SLO 100% | Không có error budget thực tế để quản lý thay đổi | Chọn mục tiêu có thể đo và gắn với mức rủi ro chấp nhận |
| Không định nghĩa eligible request | Mẫu số thay đổi tùy cách tính, SLI thiếu nhất quán | Ghi rõ traffic nào được tính và lý do loại trừ |
| Page theo mọi metric | Alert fatigue, sự cố quan trọng bị bỏ lỡ | Page theo user impact và burn rate |
| Retry không giới hạn | Khuếch đại tải và làm dependency suy sụp | Timeout, backoff, jitter, retry limit và idempotency |
| Canary chỉ kiểm tra deploy thành công | Lỗi nghiệp vụ có thể đến người dùng | So sánh SLI, business metrics và saturation |
| Có backup nhưng không diễn tập restore | RTO/RPO thực tế không đạt | Diễn tập phục hồi định kỳ |
| Postmortem quy lỗi cá nhân | Nhân viên ngại báo cáo và lỗi hệ thống tái diễn | Tập trung vào điều kiện, guardrail và cải tiến |
| Tự động hóa không có guardrail | Thao tác sai có thể lan rộng | Giới hạn phạm vi, quyền, retry và cơ chế rollback |

## 14. Checklist SRE trước khi đưa service lên production

- [ ] Có service owner, người trực và đường escalation.
- [ ] Critical user journey đã được xác định.
- [ ] SLI có numerator, denominator, eligibility và nguồn telemetry rõ ràng.
- [ ] SLO có goal, compliance period và error budget policy.
- [ ] Cloud Monitoring dashboard hiển thị latency, traffic, errors, saturation và SLO.
- [ ] Alert policy ưu tiên user impact và burn rate; mỗi page có runbook.
- [ ] Logs có cấu trúc, traces được liên kết và không ghi dữ liệu nhạy cảm không cần thiết.
- [ ] Dependency có timeout, retry có giới hạn, backoff, jitter và idempotency khi cần.
- [ ] Có health check, autoscaling, quota/capacity plan và giới hạn tài nguyên.
- [ ] Release có canary hoặc progressive rollout và rollback đã kiểm thử.
- [ ] Incident response có vai trò, kênh liên lạc và postmortem.
- [ ] Toil được đo và có kế hoạch tự động hóa.
- [ ] Backup, restore, failover và RTO/RPO đã được diễn tập.
- [ ] Các action items sau incident có owner, deadline và cách xác minh.

## Kết luận

Áp dụng SRE trên GCP bắt đầu từ trải nghiệm người dùng: định nghĩa SLI, đặt SLO và quản lý error budget. Cloud Monitoring, Logging, Trace và các công cụ observability giúp đo chất lượng, phát hiện bất thường và điều tra sự cố. Canary, rollback, autoscaling, resilience patterns, backup và DR giảm tác động của thay đổi hoặc lỗi hạ tầng. Khi kết hợp incident response, postmortem và tự động hóa toil, đội ngũ có thể cải thiện độ tin cậy liên tục mà vẫn duy trì tốc độ phát triển.

## Tài liệu tham khảo

- [Google Cloud: SRE and service monitoring concepts](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring)
- [Cloud Monitoring: Service Level Objectives API](https://docs.cloud.google.com/monitoring/api/ref_v3/rest/v3/services.serviceLevelObjectives)
- [Cloud Monitoring: Alerting on your burn rate](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/alerting-on-budget-burn-rate)
- [Google Cloud Observability overview](https://docs.cloud.google.com/stackdriver/docs)
- [Cloud Monitoring documentation](https://docs.cloud.google.com/monitoring/docs)
- [Cloud Logging documentation](https://docs.cloud.google.com/logging/docs)
- [Cloud Trace documentation](https://docs.cloud.google.com/trace/docs)
- [Managed Service for Prometheus](https://docs.cloud.google.com/stackdriver/docs/managed-prometheus)
- [Cloud Deploy: Canary deployment strategy](https://docs.cloud.google.com/deploy/docs/deployment-strategies/canary)
- [Cloud Deploy: Canary deployments to Cloud Run](https://docs.cloud.google.com/deploy/docs/deployment-strategies/canary/cloud-run)
- [Cloud Deploy: Roll back a target](https://docs.cloud.google.com/deploy/docs/roll-back)
- [Google Cloud: Reliability and disaster recovery](https://cloud.google.com/architecture/dr-scenarios-planning-guide)

