# Đo chi phí theo lượt gọi, thời gian chạy và tài nguyên cấp phát

Serverless giúp nhóm phát triển tập trung vào function và event thay vì tự vận hành máy chủ. Tuy nhiên, việc không quản lý VM không có nghĩa chi phí tự động thấp hoặc dễ dự đoán. Hóa đơn có thể phụ thuộc số lượt gọi, thời gian thực thi được tính phí, bộ nhớ hoặc CPU cấp phát, concurrency dự phòng, dung lượng lưu trữ tạm, truyền dữ liệu và các dịch vụ mà function sử dụng.

Muốn kiểm soát chi phí, cần nối được ba lớp dữ liệu: **mức sử dụng** (bao nhiêu invocation và bao lâu), **cấu hình tài nguyên** (memory/CPU/concurrency được cấp) và **đơn giá/billing rule** của nền tảng. Sau đó, tính chi phí trên một kết quả nghiệp vụ thành công thay vì chỉ nhìn tổng hóa đơn. Bài học này trình bày cách đọc các thành phần tính phí, xây dựng công thức ước lượng, phân bổ chi phí theo function và tối ưu mà vẫn giữ SLO.

## 1. Vì sao phải đo chi phí theo invocation?

Một function có thể được gọi hàng triệu lần nhưng mỗi lần chỉ chạy vài mili giây; một function khác được gọi ít hơn nhưng xử lý file lớn trong nhiều phút. Số request đơn thuần không thể cho biết function nào tốn kém hơn.

Đo chi phí theo invocation giúp:

- Xác định function nào tạo phần lớn chi phí.
- Biết chi phí trung bình cho một lần thực thi và một kết quả thành công.
- Phân biệt chi phí do số lần gọi với chi phí do duration hoặc memory tier.
- Phát hiện retry, timeout hoặc event trùng làm tăng lượng thực thi.
- So sánh cấu hình memory/CPU khác nhau.
- Phân bổ chi phí theo service, team, tenant hoặc môi trường.
- Dự báo hóa đơn khi request volume tăng.
- Đánh giá tác động chi phí của provisioned/warm capacity.

Tổng chi phí không chỉ là giá compute. Một function có thể gọi database, queue, object storage, NAT, API bên ngoài và ghi nhiều log. Nếu chỉ đo giá function, nhóm có thể tối ưu một thành phần nhỏ trong khi chi phí lớn nhất nằm ở dependency.

## 2. Những thành phần thường xuất hiện trong billing

Mỗi nhà cung cấp có tên gọi và quy tắc tính phí riêng. Các thành phần thường gặp gồm:

| Thành phần | Cách tính phổ biến | Câu hỏi cần kiểm tra |
|---|---|---|
| Request/invocation | Số lần function được gọi hoặc request được xử lý | Event retry, trigger nội bộ và invocation lỗi có được tính không? |
| Execution duration | Thời gian thực thi được nền tảng tính phí | Đo từ thời điểm nào tới thời điểm nào? Có làm tròn theo đơn vị nào? |
| Allocated memory | Memory cấu hình nhân thời gian tính phí hoặc tier giá | Tính theo memory được cấp hay memory thực dùng? |
| CPU/vCPU | CPU tier hoặc vCPU-time | CPU gắn với memory hay chọn riêng? |
| Provisioned/warm capacity | Thời gian giữ môi trường sẵn sàng và mức tài nguyên giữ lại | Có tính cả lúc không có request không? |
| Ephemeral storage | Dung lượng tạm vượt mức bao gồm nhân thời gian | Phần miễn phí và cách đo dung lượng ra sao? |
| Network | Egress, NAT, private connectivity hoặc transfer liên vùng | Byte nào bị tính phí và theo hướng nào? |
| Observability | Log ingestion, metrics, traces, retention | Dữ liệu nào được ingest và giữ trong bao lâu? |
| Dependency | Database, queue, object storage, workflow, API gateway | Function có làm tăng request hoặc capacity của dịch vụ khác không? |

Không phải nền tảng nào cũng có tất cả thành phần hoặc dùng cùng đơn vị. Một dịch vụ có thể tính GB-second, dịch vụ khác tính vCPU-second và memory-second riêng. Hãy đọc billing specification cho đúng function product, plan, region và runtime.

## 3. Invocation count: đếm đúng lượt gọi

Invocation count là số lần function được thực thi theo định nghĩa của nền tảng. Cần phân biệt:

- Request từ người dùng hoặc API gateway.
- Event do queue, object storage, scheduler hoặc stream phát ra.
- Invocation được gọi đồng bộ bởi service khác.
- Retry sau lỗi hoặc timeout.
- Redelivery khi consumer không acknowledge.
- Invocation chạy lại do orchestration hoặc workflow retry.
- Invocation bị từ chối trước khi function bắt đầu do concurrency/quota.

Số request tại API gateway có thể khác số invocation. Một request có thể kích hoạt nhiều function; một event có thể được retry nhiều lần; một batch invocation có thể xử lý nhiều message trong một lần chạy. Vì vậy, hãy đối chiếu metric invocation của function với số event đầu vào, retry và số tác vụ nghiệp vụ hoàn tất.

### 3.1. Invocation không đồng nghĩa với kết quả thành công

Một invocation có thể:

- Hoàn tất thành công.
- Trả lỗi ứng dụng.
- Timeout.
- Bị runtime kết thúc do memory limit.
- Bị retry và chạy lại.
- Hoàn tất nhưng kết quả nghiệp vụ không hợp lệ.
- Được tính phí dù không tạo ra kết quả hữu ích, tùy billing rule.

Khi đo hiệu quả, nên ghi ít nhất ba số:

1. Tổng invocation được tính phí hoặc được ghi nhận bởi nền tảng.
2. Invocation hoàn tất không lỗi.
3. Tác vụ nghiệp vụ hoàn tất đúng và được xác nhận.

Mẫu số cho cost per success nên là số kết quả hợp lệ, không phải tổng số lần gọi. Nếu một event cần ba lần retry mới hoàn tất, chi phí của cả ba lần cần được tính cho kết quả cuối cùng đó.

## 4. Execution duration và billed duration

Execution duration là thời gian function chạy. Billed duration là thời lượng mà nhà cung cấp dùng để tính phí. Hai giá trị có thể khác nhau do cách đo, làm tròn, minimum billing unit, initialization hoặc loại invocation.

Cần xác minh:

- Thời gian bắt đầu tính từ lúc nhận event, lúc runtime bắt đầu hay sau initialization.
- Thời gian kết thúc có bao gồm serialize response, flush log hoặc cleanup không.
- Cold start/initialization được tính riêng hay gộp vào duration.
- Duration có được làm tròn theo mili giây, khoảng thời gian khác hoặc minimum duration không.
- Async invocation và streaming invocation có quy tắc khác không.
- Request bị timeout được tính theo thời gian thực chạy hay mức tối đa đã cấu hình.
- Provisioned capacity có thành phần tính phí riêng ngoài invocation duration không.

Không lấy wall-clock ở client để thay thế billed duration nếu chưa hiểu khác biệt. Client có thể tính cả DNS, API gateway, queue delay và network latency, trong khi function duration chỉ đo phần thực thi bên trong runtime.

### 4.1. Ví dụ về các mốc thời gian

Một request có thể trải qua:

1. Client gửi request.
2. Gateway xác thực và chuyển request.
3. Nền tảng tìm execution environment hoặc khởi tạo environment mới.
4. Runtime khởi tạo và nạp code.
5. Handler bắt đầu xử lý.
6. Handler gọi dependency và hoàn tất.
7. Runtime gửi response.
8. Gateway trả response cho client.

Billed duration có thể bắt đầu hoặc kết thúc ở một mốc cụ thể trong chuỗi này. Cần đọc định nghĩa chính thức của nhà cung cấp và dùng metric tương ứng để tính.

## 5. Tài nguyên cấp phát và tài nguyên thực sử dụng

Một điểm quan trọng trong serverless là chi phí thường dựa trên tài nguyên được cấu hình hoặc giữ sẵn, không nhất thiết chỉ dựa trên lượng tài nguyên thực tế tiêu thụ.

Ví dụ:

- Memory được cấp là 1 GiB, nhưng peak working set chỉ 350 MiB.
- CPU tier được chọn theo memory, dù function chủ yếu chờ I/O.
- Function giữ provisioned concurrency trong thời gian không có request.
- Ephemeral storage được cấu hình 5 GiB nhưng chỉ dùng 1 GiB.

Các số này phục vụ hai mục đích khác nhau:

- **Allocated resources:** xác định giới hạn và có thể là đầu vào trực tiếp của billing.
- **Utilized resources:** cho biết workload thực tế dùng bao nhiêu và có thể tối ưu cấu hình không.

Nếu billing tính theo memory được cấp, memory utilization thấp không tự động làm hóa đơn giảm. Muốn giảm chi phí, có thể cần hạ memory tier, giảm duration hoặc chọn cấu hình khác, nhưng phải benchmark để tránh làm function chậm hơn và tổng GB-second tăng.

## 6. Công thức chi phí cơ bản

Một mô hình tổng quát cho function:

\[
C_{function} =
C_{requests} + C_{execution} + C_{provisioned}
+ C_{temporary} + C_{other}
\]

Trong đó:

- \(C_{requests}\): phí theo số invocation.
- \(C_{execution}\): phí theo duration và tài nguyên tính phí.
- \(C_{provisioned}\): phí giữ capacity sẵn sàng nếu có.
- \(C_{temporary}\): phí lưu trữ tạm vượt mức bao gồm nếu có.
- \(C_{other}\): các khoản khác do sản phẩm cụ thể quy định.

Với mô hình GB-second đơn giản:

\[
C_{execution} =
N \times T_{billed} \times M_{GB} \times R_{GB-second}
\]

Trong đó:

- \(N\): số invocation.
- \(T_{billed}\): duration tính phí trung bình của mỗi invocation, tính bằng giây.
- \(M_{GB}\): memory cấp phát đổi sang GB theo đơn vị mà nhà cung cấp quy định.
- \(R_{GB-second}\): đơn giá cho một GB-second.

Nếu CPU được tính riêng, cần cộng CPU/vCPU-second theo công thức và đơn giá tương ứng. Không áp dụng công thức GB-second cho nền tảng có mô hình billing khác mà không quy đổi.

### 6.1. Tính chi phí request

Nếu có mức phí theo request:

\[
C_{requests} =
\frac{N_{billable}}{U} \times P_U
\]

Trong đó \(U\) là đơn vị tính giá, ví dụ một triệu request; \(P_U\) là giá của đơn vị đó. Cần xác định invocation nào nằm trong free tier hoặc mức miễn phí và áp dụng theo quy tắc hóa đơn.

### 6.2. Cost per invocation và cost per success

Chi phí trung bình trên mỗi invocation:

\[
C_{per-invocation} =
\frac{C_{function}}{N_{billable}}
\]

Chi phí trên mỗi kết quả nghiệp vụ thành công:

\[
C_{per-success} =
\frac{C_{function} + C_{dependency}}
{N_{successful-business-operations}}
\]

Chỉ số thứ hai thường hữu ích hơn khi function có retry, timeout, batch hoặc xử lý nhiều bước. Nó phản ánh số tiền thực tế để tạo ra một kết quả đúng.

## 7. Ví dụ tính GB-second và chi phí

Giả sử một function có các thông số minh họa:

- 2.000.000 invocation trong tháng.
- Memory cấp phát 1 GiB.
- Billed duration trung bình 0,4 giây.
- Đơn giá minh họa 0,000016 USD/GB-second.
- Phí request được tính riêng và chưa đưa vào phép tính dưới đây.

Tổng GB-second:

\[
2{,}000{,}000 \times 0.4 \times 1
= 800{,}000\ GB\text{-}seconds
\]

Chi phí execution minh họa:

\[
800{,}000 \times 0.000016
= 12.80\ USD
\]

Nếu duration trung bình tăng lên 0,8 giây, với cùng số invocation và memory:

\[
2{,}000{,}000 \times 0.8 \times 1
= 1{,}600{,}000\ GB\text{-}seconds
\]

Chi phí execution tăng gấp đôi thành 25,60 USD theo đơn giá giả định.

Các mức giá chỉ nhằm minh họa công thức, không phải báo giá của AWS, Azure, Google Cloud hoặc bất kỳ nhà cung cấp nào. Hóa đơn thực tế có thể có rounding, free tier, request charge, CPU charge, provisioned capacity và chi phí phụ trợ.

## 8. Ví dụ so sánh memory tier

Một function xử lý cùng một loại event ở ba cấu hình. Giả sử billing tính theo GB-second và bỏ qua request charge để minh họa:

| Cấu hình | Memory cấp phát | Duration trung bình | GB-second/invocation |
|---|---:|---:|---:|
| A | 0,5 GB | 0,80 s | 0,40 |
| B | 1,0 GB | 0,42 s | 0,42 |
| C | 2,0 GB | 0,25 s | 0,50 |

Cấu hình B chạy nhanh hơn A nhưng GB-second gần tương đương. C nhanh nhất nhưng tiêu thụ GB-second cao hơn. Nếu SLO yêu cầu duration dưới 500 ms, A không đạt; B có thể là lựa chọn cân bằng. Nếu latency cần dưới 300 ms, C có thể cần thiết dù cost per invocation cao hơn.

Không nên chỉ chọn cấu hình có GB-second thấp nhất. Cần xem latency, error rate, memory peak, throughput, cold start và chi phí dependency. Cấu hình chậm có thể giữ connection và concurrency lâu hơn, làm tăng chi phí hệ thống ở các tầng khác.

## 9. CPU và cách nền tảng phân bổ CPU ảnh hưởng tới chi phí

Một số nền tảng gắn CPU share với memory tier; tăng memory có thể đồng thời tăng CPU. Một số dịch vụ cho chọn vCPU độc lập hoặc theo các preset. Vì vậy, cùng một memory không đảm bảo cùng CPU giữa các sản phẩm.

Khi benchmark, ghi:

- Memory tier hoặc memory limit.
- CPU share, vCPU hoặc CPU tier nếu nền tảng công bố.
- CPU utilization và throttling.
- Duration p50/p95/p99.
- Throughput và concurrency.
- Cost per successful operation.

Workload CPU-bound như nén, mã hóa, xử lý ảnh hoặc parse dữ liệu lớn có thể chạy nhanh hơn khi được cấp thêm CPU. Workload I/O-bound có thể không cải thiện nhiều nếu thời gian chủ yếu chờ database hoặc API ngoài.

Nếu tăng memory làm CPU tăng theo, duration giảm có thể bù lại chi phí memory cao hơn. Hãy so cost per result thay vì chỉ so đơn giá cấu hình.

## 10. Concurrency và provisioned capacity

Concurrency là số invocation đang chạy đồng thời. Nó ảnh hưởng tới số execution environment, mức tài nguyên cần giữ, khả năng xử lý burst và chi phí capacity.

Cần phân biệt:

- **On-demand concurrency:** nền tảng tạo capacity theo nhu cầu, có thể có cold start.
- **Reserved/maximum concurrency:** giới hạn hoặc dành một phần concurrency theo chính sách của dịch vụ; ý nghĩa billing khác nhau tùy nền tảng.
- **Provisioned concurrency/warm instances:** giữ sẵn execution environment để giảm cold start, thường có phí capacity riêng.
- **Minimum instances:** một số nền tảng container/serverless giữ tối thiểu số instance ngay cả khi không có request.

Không phải mọi loại concurrency đều tạo một khoản phí độc lập. Có dịch vụ dùng concurrency như quota/giới hạn; có dịch vụ tính phí cho capacity được giữ sẵn. Phải phân biệt rõ giới hạn concurrency với provisioned capacity.

### 10.1. Chi phí khi giữ capacity nhàn rỗi

Provisioned capacity có thể cải thiện latency đầu tiên và giảm cold start, nhưng vẫn phát sinh chi phí khi không có request tùy mô hình billing. Đánh giá:

- Tỷ lệ thời gian capacity thực sự được sử dụng.
- Số request trong giờ thấp điểm.
- Cold-start SLO.
- Thời gian cần giữ warm capacity.
- Chi phí provisioned so với chi phí invocation on-demand.
- Khả năng tự động điều chỉnh mức capacity theo lịch hoặc demand.

Nếu workload chỉ có burst ngắn và chấp nhận cold start, giữ capacity 24/7 có thể không kinh tế. Nếu là API giao dịch cần latency ổn định, provisioned capacity có thể đáng chi trả.

## 11. Cold start và duration

Cold start có thể bao gồm việc tạo environment, nạp runtime, tải code/dependency và chạy initialization. Cách tính thời gian và billing của cold start khác nhau theo nền tảng.

Đo riêng:

- Initialization duration.
- Handler duration.
- Total billed duration nếu metric có cung cấp.
- Cold-start count hoặc tỷ lệ cold start.
- Latency p50/p95/p99 của client.
- Tỷ lệ invocation ở warm environment.

Cold start không chỉ ảnh hưởng trải nghiệm người dùng. Nếu initialization được tính phí hoặc giữ capacity trong thời gian dài, nó cũng ảnh hưởng cost. Tuy nhiên, không được tự suy luận phần nào bị tính phí: kiểm tra billing definition của dịch vụ đang dùng.

Các biện pháp tối ưu:

- Giảm package size và dependency không cần thiết.
- Tránh initialization nặng.
- Tái sử dụng client/connection an toàn giữa invocation.
- Dùng runtime phù hợp.
- Chọn provisioned/warm capacity nếu lợi ích latency lớn hơn chi phí.
- Không giữ environment warm bằng cách tạo request giả nếu việc đó vi phạm policy hoặc làm chi phí tăng mà không có giá trị.

## 12. Retry, timeout và invocation trùng

Retry làm tăng số lần thực thi và có thể tăng cost ngay cả khi người dùng chỉ gửi một request ban đầu.

Các nguồn retry:

- Client retry khi timeout hoặc mất kết nối.
- API gateway retry theo policy.
- Event source retry khi function trả lỗi.
- Queue redelivery khi message chưa được acknowledge.
- Workflow retry một step.
- Scheduler phát lại event sau lỗi.
- Người dùng gửi lại thao tác do không nhận được response.

Hãy đo retry count, attempts per successful operation, duplicate event và dead-letter count. Nếu một business operation trung bình cần 1,2 invocation, chi phí trên kết quả thành công cao hơn 20% so với giả định một invocation cho mỗi kết quả, chưa tính thời gian mỗi attempt.

### 12.1. Kiểm soát retry

- Retry chỉ lỗi tạm thời.
- Dùng exponential backoff và jitter.
- Giới hạn số lần thử và tổng thời gian.
- Không retry khi deadline đã hết.
- Dùng idempotency key cho thao tác có side effect.
- Dùng dead-letter queue cho event không thể xử lý.
- Phân biệt lỗi trước khi thực hiện side effect với lỗi sau khi side effect có thể đã hoàn tất.
- Theo dõi cost do retry và tỷ lệ retry thành công.

Retry quá nhiều có thể tạo retry storm: dependency chậm khiến invocation kéo dài, request timeout rồi retry, làm dependency nhận thêm tải và tiếp tục chậm.

## 13. Batch processing và cost per event

Một invocation có thể xử lý một event hoặc một batch nhiều event. Khi dùng batch, chi phí request có thể được chia cho nhiều sự kiện, nhưng duration và memory có thể tăng.

Ví dụ, một invocation xử lý 100 message trong 2 giây. Nếu tính riêng request charge, một lần gọi xử lý được 100 message. Nhưng cost compute vẫn phụ thuộc duration và tài nguyên được cấp.

Chỉ số cần đo:

- Batch size trung bình và tối đa.
- Số event thành công trong batch.
- Số event bị lỗi hoặc retry.
- Duration theo batch size.
- Peak memory.
- Partial batch failure.
- Số message redelivery.
- Cost per successful event.

Batch quá nhỏ làm request overhead tăng; batch quá lớn có thể timeout, tăng memory hoặc khiến một message lỗi làm retry cả batch nếu không hỗ trợ partial failure. Chọn batch size bằng benchmark và semantics của event source.

## 14. Phân bổ chi phí cho function và team

Hóa đơn cloud thường được tổng hợp theo account, project, subscription, region hoặc service. Muốn biết function/team nào tạo chi phí, cần có metadata nhất quán.

Các chiều phân bổ hữu ích:

- Service hoặc function name.
- Environment: dev, test, staging, production.
- Team/owner.
- Cost center.
- Product hoặc tenant nếu billing model hỗ trợ.
- Region.
- Runtime hoặc version.
- Event source.
- Application domain.

Có thể dùng resource tag, label, project/subscription riêng hoặc cost allocation mapping. Không phải mọi khoản phí shared đều có thể gắn trực tiếp vào một function. Khi đó, cần quy tắc phân bổ, ví dụ theo invocation count, data processed, execution duration hoặc mức sử dụng thực tế.

### 14.1. Phân bổ shared cost

Ví dụ, nhiều function cùng dùng một queue và một database. Có thể phân bổ chi phí dependency theo:

- Số request hoặc query phát sinh.
- Số byte đọc/ghi.
- Thời gian connection hoặc compute consumed.
- Số event do từng producer tạo.
- Một tỷ lệ cố định đã thống nhất nếu không có telemetry chi tiết.

Quy tắc phân bổ phải minh bạch và nhất quán. Không nên cộng toàn bộ database bill vào function có nhiều invocation nhất nếu function đó thực tế chỉ tạo query nhẹ.

## 15. Xây dựng dashboard chi phí serverless

Một dashboard hữu ích nên kết hợp usage, performance, reliability và billing.

| Nhóm | Metric hoặc dimension | Câu hỏi |
|---|---|---|
| Volume | Invocation count, event count, retry count | Tải tăng do nhu cầu hay retry? |
| Duration | Average, p50/p95/p99, billed duration | Function có chậm hơn không? |
| Resource | Allocated memory/CPU, peak memory, throttling | Có tier dư hoặc thiếu? |
| Reliability | Success/error/timeout/OOM/DLQ | Chi phí có tạo ra kết quả thành công? |
| Concurrency | Concurrent execution, provisioned capacity, utilization | Có giữ capacity nhàn rỗi? |
| Cost | Request charge, compute charge, provisioned charge | Thành phần nào chiếm phần lớn hóa đơn? |
| Unit economics | Cost per invocation, cost per success, cost per event | Mỗi kết quả nghiệp vụ tốn bao nhiêu? |
| Dependency | DB, queue, storage, network, logs | Chi phí chuyển sang dịch vụ phụ trợ không? |

Dashboard nên hỗ trợ lọc theo function, team, environment, region, version và thời gian. Dùng cùng timezone và cùng khoảng aggregation khi đối chiếu metrics với billing export.

### 15.1. Cảnh báo chi phí và bất thường

Có thể đặt cảnh báo khi:

- Invocation count tăng đột biến so với baseline.
- Average duration hoặc p99 tăng liên tục.
- Retry attempts per success vượt ngưỡng.
- Provisioned capacity utilization thấp kéo dài.
- Cost per successful operation tăng.
- Một function mới tạo chi phí bất thường.
- Egress, NAT hoặc log ingestion tăng mạnh.
- Chi phí tháng dự báo vượt budget.

Cảnh báo cần có ngữ cảnh: function, owner, environment, version, metric thay đổi và link tới dashboard/log. Cảnh báo chỉ dựa trên tổng cost có thể tới quá muộn để xác định nguyên nhân.

## 16. Dự báo chi phí theo workload

Một ước lượng ban đầu có thể dùng:

\[
C_{month} \approx
N_{month} \times
(C_{request/unit} + C_{execution/invocation})
+ C_{provisioned} + C_{dependencies}
\]

Nếu traffic thay đổi theo giờ, không nên chỉ lấy trung bình ngày nhân số ngày. Hãy mô hình hóa:

- Giờ thấp điểm và cao điểm.
- Burst theo event hoặc campaign.
- Retry rate.
- Batch size.
- Duration distribution.
- Memory/CPU tier.
- Provisioned capacity theo lịch.
- Tăng trưởng request volume.
- Chi phí dependency và egress.

Có thể dùng ba kịch bản: low, expected và peak. Kịch bản peak nên tính capacity và concurrency cần thiết để giữ SLO, không chỉ nhân số request.

## 17. Tối ưu chi phí mà vẫn giữ SLO

Tối ưu cần dựa trên cost per successful operation và các ràng buộc latency/reliability.

### 17.1. Giảm duration

- Tối ưu thuật toán và cấu trúc dữ liệu.
- Giảm serialization/deserialization không cần thiết.
- Dùng batch hoặc bulk API để giảm round trip.
- Tái sử dụng connection/client.
- Stream dữ liệu lớn.
- Tránh gọi dependency tuần tự nếu có thể chạy song song an toàn.
- Giảm initialization và package load.
- Dùng cache có TTL và invalidation phù hợp.

Giảm duration có thể giảm compute charge, nhưng cần đo CPU tier và memory allocation. Nếu function chuyển sang chờ dependency lâu, tối ưu code cục bộ có thể ít tác dụng.

### 17.2. Chọn memory/CPU phù hợp

Benchmark nhiều tier với cùng payload và concurrency. Chọn cấu hình đáp ứng SLO với cost per success thấp, có headroom cho input lớn và peak traffic. Không hạ memory chỉ vì utilization trung bình thấp nếu peak memory có thể gây OOM.

### 17.3. Giảm invocation overhead

- Gộp event thành batch khi semantics cho phép.
- Dùng queue để hấp thụ burst và xử lý theo batch.
- Loại bỏ trigger trùng.
- Chặn event không hợp lệ sớm.
- Tránh function gọi function không cần thiết qua nhiều tầng.
- Dùng workflow hoặc worker dài hạn nếu function bị gọi lặp để duy trì một tác vụ dài.

Batch cần xử lý partial failure và idempotency để tránh retry cả nhóm không cần thiết.

### 17.4. Điều chỉnh provisioned capacity

Dựa trên traffic pattern và cold-start SLO để giữ warm capacity theo lịch hoặc demand. Theo dõi utilization và scale policy; tránh giữ mức provisioned cao trong giờ thấp điểm nếu không cần.

### 17.5. Kiểm soát log và telemetry

Log debug quá chi tiết có thể tạo chi phí ingestion và retention lớn. Dùng log level phù hợp, sampling có kiểm soát, structured logging và retention theo mục đích. Không loại bỏ audit hoặc log lỗi cần thiết chỉ để giảm chi phí.

### 17.6. Tối ưu dependency

Một function rẻ có thể làm tăng cost database hoặc NAT. Giảm query dư thừa, dùng cache phù hợp, connection reuse, private endpoint và giới hạn concurrency có thể giảm tổng chi phí. Luôn đo end-to-end cost.

## 18. Ví dụ end-to-end: tính cost per successful event

Giả sử một function xử lý event từ queue trong một tháng:

- 1.000.000 event đầu vào.
- Trung bình 1,08 invocation cho mỗi event do retry.
- 1.080.000 invocation được tính vào usage.
- Memory cấp phát 1 GB.
- Billed duration trung bình 0,5 giây.
- Đơn giá execution giả định 0,000016 USD/GB-second.
- Phí request và dependency được tính riêng.
- 990.000 event hoàn tất thành công.

Tổng GB-second:

\[
1{,}080{,}000 \times 0.5 \times 1
= 540{,}000\ GB\text{-}seconds
\]

Chi phí execution giả định:

\[
540{,}000 \times 0.000016 = 8.64\ USD
\]

Chi phí execution trên mỗi event thành công:

\[
\frac{8.64}{990{,}000}
\approx 0.00000873\ USD/event
\]

Con số này chưa gồm request charge, queue, database, object storage, log và network. Nếu chỉ chia 8,64 USD cho 1.080.000 invocation, ta nhận được cost per invocation nhưng không phản ánh 90.000 event chưa thành công. Để đánh giá unit economics, cần theo dõi cả cost per invocation và cost per successful event.

## 19. Những lỗi thường gặp khi đo chi phí

**Dùng request count thay invocation count.** Một request có thể tạo nhiều invocation hoặc một batch invocation xử lý nhiều event. Đối chiếu các tầng telemetry.

**Dùng duration client thay billed duration.** Client time có thể gồm gateway, network và queue delay. Dùng metric theo định nghĩa billing của nhà cung cấp.

**Dùng memory thực tế thay memory cấp phát.** Nếu giá tính theo tier được cấp, utilization thấp không trực tiếp giảm hóa đơn.

**Bỏ qua retry và redelivery.** Một event có thể tạo nhiều lần chạy. Đo attempts per success.

**Chỉ xem giá function.** Database, queue, NAT, egress, logs và storage có thể chiếm phần đáng kể.

**Lấy average duration làm đại diện.** p95/p99 và timeout có thể tăng chi phí hoặc làm giảm số kết quả thành công.

**Không tách provisioned capacity.** Chi phí giữ môi trường warm có thể tồn tại khi request volume thấp.

**So sánh cấu hình với workload khác nhau.** Payload, batch size, cache và concurrency phải tương đương.

**Không phân bổ shared cost.** Team có thể tối ưu function của mình nhưng làm tăng chi phí dịch vụ dùng chung.

**Dùng giá cũ hoặc sai region/plan.** Đơn giá và free tier có thể thay đổi; lưu thời điểm và nguồn của giả định giá.

## 20. Quy trình triển khai đo lường chi phí

1. Liệt kê function, trigger, region, runtime, owner và environment.
2. Ghi nhận billing model và đơn vị tính phí của từng function product.
3. Thu thập invocation count, billed duration, allocated memory/CPU và concurrency.
4. Ghi retry, timeout, error, OOM và số kết quả nghiệp vụ thành công.
5. Thu thập chi phí dependency, network, storage và observability.
6. Chuẩn hóa tag/label hoặc mapping để phân bổ theo team và service.
7. Tạo dashboard usage, cost, SLO và cost per success.
8. Đặt budget, anomaly detection và cảnh báo theo owner.
9. Benchmark các cấu hình tài nguyên với workload đại diện.
10. Chọn cấu hình đáp ứng SLO và có cost per success hợp lý.
11. Kiểm tra lại hóa đơn/billing export sau khi triển khai.
12. Định kỳ đánh giá lại khi volume, code, runtime, region hoặc pricing thay đổi.

### 20.1. Mẫu bảng ghi nhận benchmark

| Trường | Giá trị cần ghi |
|---|---|
| Function/release | Tên function và image/code revision |
| Region/runtime | Region và runtime version |
| Memory/CPU | Tài nguyên cấp phát |
| Concurrency | Limit, observed peak và provisioned capacity |
| Invocation | Tổng billable invocation và retry |
| Duration | Average, p50, p95, p99 và billed duration |
| Result | Success/error/timeout/OOM và business success |
| Temporary storage | Allocated, peak used và billed amount nếu có |
| Cost | Request, execution, provisioned và dependency |
| Unit cost | Cost per invocation và cost per successful operation |
| SLO | Latency/error threshold và kết quả đạt/không đạt |

## 21. Checklist đo và tối ưu chi phí serverless

- [ ] Đã xác định chính xác invocation count theo định nghĩa nền tảng.
- [ ] Đã tách request đầu vào, invocation, retry và business success.
- [ ] Đã hiểu billed duration và rounding/minimum billing unit.
- [ ] Đã ghi memory/CPU được cấp và mức sử dụng thực tế.
- [ ] Đã tính request charge và execution charge riêng.
- [ ] Đã kiểm tra provisioned/warm capacity và thời gian nhàn rỗi.
- [ ] Đã tính temporary storage, network, NAT và egress nếu có.
- [ ] Đã tính database, queue, object storage, workflow và observability.
- [ ] Đã tính cost per invocation và cost per successful operation.
- [ ] Đã theo dõi retry, timeout, duplicate event và DLQ.
- [ ] Đã benchmark memory/CPU tier với cùng workload.
- [ ] Đã đo duration p50/p95/p99 và kiểm tra SLO.
- [ ] Đã phân bổ chi phí theo owner, service, environment và cost center.
- [ ] Có dashboard và cảnh báo bất thường theo function.
- [ ] Đã lưu giả định giá, region, plan và thời điểm áp dụng.
- [ ] Đã đối chiếu usage estimate với billing export/invoice.
- [ ] Đã đánh giá lại sau thay đổi code, runtime, traffic hoặc pricing.

## 22. Kết luận

Chi phí serverless thường được hình thành từ số lượt gọi, thời gian tính phí và tài nguyên được cấp phát, cộng với capacity giữ sẵn, storage, network, observability và dependency theo mô hình của nhà cung cấp. Invocation count phải được phân biệt với request đầu vào và kết quả nghiệp vụ thành công; billed duration phải được phân biệt với wall-clock phía client; memory/CPU cấp phát phải được phân biệt với mức sử dụng thực tế.

Hãy đo usage và cost cùng SLO, theo dõi retry và timeout, tính cost per invocation lẫn cost per successful operation, rồi phân bổ chi phí theo function/team. Benchmark cấu hình CPU/memory, concurrency và warm capacity bằng workload đại diện; tối ưu duration, batch, dependency và telemetry trong khi vẫn giữ correctness và latency. Khi billing rule được hiểu rõ và dữ liệu usage được nối với kết quả nghiệp vụ, nhóm có thể dự báo hóa đơn, tìm nguồn lãng phí và lựa chọn cấu hình serverless có hiệu quả kinh tế tốt hơn.
