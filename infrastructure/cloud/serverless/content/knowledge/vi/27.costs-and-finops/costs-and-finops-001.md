# Lập mô hình chi phí function theo lưu lượng và thời gian chạy

Chi phí của một function serverless phụ thuộc vào số lần gọi, thời gian xử lý, tài nguyên được cấp và các dịch vụ mà function sử dụng. Một function có ít invocation nhưng chạy lâu với memory lớn có thể tốn hơn function được gọi thường xuyên nhưng hoàn tất nhanh. Một workload có trung bình thấp nhưng burst lớn cũng có thể phát sinh chi phí khác do scale-out, capacity giữ sẵn và các dịch vụ phụ trợ.

Để lập mô hình chi phí có ích, cần nối ba lớp dữ liệu:

1. **Nhu cầu nghiệp vụ:** số operation thành công, số event/request đến và mức tăng trưởng.
2. **Hành vi runtime:** số invocation thực tế, retry, batch size, duration, memory/CPU, concurrency và cold start.
3. **Hóa đơn hạ tầng:** request, compute, capacity giữ sẵn, queue, API gateway, network, logs, traces, storage và downstream services.

Không nên ước tính chi phí chỉ bằng số invocation nhân với một đơn giá. Cần mô hình cả thời gian chạy, mức tài nguyên, retry và chi phí ngoài function để biết một operation nghiệp vụ thực sự tốn bao nhiêu.

## 1. Những yếu tố tạo nên chi phí serverless

Tùy nhà cung cấp và mô hình billing, một ứng dụng Java serverless có thể phát sinh các nhóm chi phí sau:

| Nhóm chi phí | Driver thường gặp | Ví dụ |
|---|---|---|
| Invocation/request | Số lần function được gọi | HTTP request, event invocation |
| Compute duration | Thời gian chạy và tài nguyên cấp | GB-second, vCPU-second, GiB-second |
| Capacity giữ sẵn | Mức concurrency/instance provisioned hoặc minimum | Provisioned concurrency, min instances |
| Event và queue | Số operation broker/API | SQS request, Pub/Sub operation, EventBridge event |
| API ingress | Request và dữ liệu qua gateway/load balancer | API Gateway, HTTP load balancing |
| Network | Data transfer, NAT, cross-zone/region | Egress, VPC connector, NAT processing |
| Observability | Log ingestion, retention, query, trace | CloudWatch Logs, Cloud Logging, tracing backend |
| Storage | Payload, artifact, snapshot, temporary storage | Object storage, container registry, ephemeral storage |
| Downstream | Database, cache, external API và dịch vụ dùng chung | Database capacity, connection proxy, payment provider |
| Security/operations | Secret, key, audit và monitoring | KMS operations, secret access, security logs |

Một số dịch vụ được tính phí theo request, số byte, thời gian giữ dữ liệu hoặc capacity đã cấp. Đơn giá và quy tắc billing khác nhau theo provider, region, runtime, architecture, tier và thời điểm. Mô hình nên dùng các biến đơn giá lấy từ bảng giá hiện hành của môi trường triển khai, không hard-code giá từ một ví dụ học tập.

## 2. Tách business operation khỏi function invocation

Một thao tác nghiệp vụ không nhất thiết tương ứng với một invocation.

Ví dụ, một đơn hàng có thể:

- Gọi API function để tiếp nhận order.
- Gửi một event vào queue.
- Gọi function giữ tồn kho.
- Gọi function capture payment.
- Gọi function tạo shipment.
- Retry một hoặc nhiều bước.
- Gửi event thông báo sau khi hoàn tất.

Một business operation có thể tạo nhiều invocation trên nhiều function. Ngược lại, một invocation có thể xử lý một batch gồm nhiều message.

Vì vậy cần phân biệt:

- **business_operations:** số ý định nghiệp vụ duy nhất.
- **messages_published:** số message được publish.
- **function_invocations:** số lần function thực sự chạy.
- **successful_operations:** số operation nghiệp vụ hoàn tất.
- **retry_attempts:** số lần xử lý bổ sung do retry/redelivery.
- **failed_or_rejected_operations:** số operation không hoàn tất.

Đây là nền tảng để tính cost per operation và tránh nhầm số invocation với số khách hàng hoặc số đơn hàng.

### 2.1. Ước lượng số invocation

Với HTTP function một request trên mỗi invocation:

\[
N_{\text{invocations}} \approx
N_{\text{requests}} \times A
\]

Trong đó \(A\) là số attempt trung bình cho mỗi request, bao gồm retry do client hoặc nền tảng.

Với message consumer nhận batch:

\[
N_{\text{invocations}} \approx
\frac{N_{\text{messages processed across attempts}}}
{B_{\text{effective}}}
\]

Trong đó \(B_{\text{effective}}\) là batch size thực tế, không nhất thiết bằng batch size tối đa đã cấu hình. Batch không phải lúc nào cũng đầy; batching window, concurrency, payload limit, partial failure và retry có thể làm thay đổi số invocation.

Với workflow nhiều function:

\[
N_{\text{total invocations}} =
\sum_{f=1}^{F} N_f
\]

Hãy tính riêng từng function hoặc nhóm function có memory, duration và pricing khác nhau. Không lấy tổng business operation nhân một hệ số duy nhất nếu đường đi của các operation khác nhau.

## 3. Mô hình compute theo duration và tài nguyên

Một mô hình phổ biến của FaaS tính compute theo tài nguyên cấp nhân thời gian billable. Với function dùng memory cố định:

\[
U_{\text{compute}} =
N_{\text{invocations}}
\times D_{\text{billable}}
\times M_{\text{GB}}
\]

Trong đó:

- \(N_{\text{invocations}}\): số invocation được tính phí.
- \(D_{\text{billable}}\): thời gian billable trung bình, tính bằng giây.
- \(M_{\text{GB}}\): memory được cấp, quy đổi sang GB theo quy tắc provider.
- \(U_{\text{compute}}\): lượng compute unit, ví dụ GB-second.

Chi phí compute có thể ước tính:

\[
C_{\text{compute}} =
U_{\text{compute}} \times R_{\text{compute}}
\]

Chi phí request:

\[
C_{\text{request}} =
\frac{N_{\text{invocations}}}{1.000.000}
\times R_{\text{request per million}}
\]

Tổng chi phí function cơ bản:

\[
C_{\text{function}} =
C_{\text{request}} + C_{\text{compute}}
\]

Đây là mô hình khái quát. Một số provider dùng vCPU-second và GiB-second riêng; một số có mức tối thiểu, bước làm tròn duration hoặc cách tính CPU khác. Hãy thay lượng compute và rate bằng đúng billing dimensions của nền tảng đang dùng.

### 3.1. Ví dụ tính compute

Giả sử một HTTP function có số liệu dự báo trong một tháng:

- 2.600.000 invocation đã bao gồm retry.
- Memory cấp: 512 MiB, tương đương khoảng 0,5 GiB trong ví dụ.
- Billable duration trung bình: 240 ms, tương đương 0,24 giây.

Compute usage ước tính:

\[
2.600.000 \times 0,24 \times 0,5
= 312.000\ \text{GB-second}
\]

Chi phí function:

\[
C_{\text{function}} =
2,6 \times R_{\text{request per million}}
+ 312.000 \times R_{\text{GB-second}}
\]

Các rate ở đây là biến để điền theo bảng giá hiện hành. Ví dụ không đại diện cho giá của AWS, Google Cloud, Azure hoặc bất kỳ region cụ thể nào.

### 3.2. Tách duration thành các thành phần

Duration cần được đo nhất quán. Với Java, thời gian có thể bao gồm:

- Initialization/runtime startup.
- Framework/context initialization.
- Handler execution.
- Dependency calls.
- Serialization và response handling.

Tùy nền tảng, initialization có thể được tính vào billable duration hoặc có quy tắc billing riêng. Hãy đọc semantics billing của provider. Đừng cộng Init Duration vào duration lần nữa nếu metric billable đã bao gồm phần đó.

Đối với message consumer, nên phân biệt thời gian message chờ trong queue với thời gian function thực sự chạy. Queue wait làm tăng age và có thể kéo dài SLA, nhưng không nhất thiết là compute duration được tính phí cho function.

### 3.3. Giá niêm yết và chi phí thực trả

Khi chọn rate cho mô hình, xác định đang tính **usage cost theo giá niêm yết** hay **effective cost sau ưu đãi**. Hai con số phục vụ mục đích khác nhau:

- Giá niêm yết giúp so sánh mức tiêu thụ giữa cấu hình và provider.
- Effective rate phản ánh Savings Plans, committed-use discounts, enterprise discount hoặc hợp đồng đã phân bổ.
- Free tier, credits và promotional balance có thể làm hóa đơn thực trả thấp hơn trong một giai đoạn nhưng không nhất thiết giảm mức tiêu thụ tài nguyên.
- Thuế, support plan và khoản phí cấp tài khoản nên được tính riêng nếu mục tiêu là dự báo tổng invoice.

Không trừ free tier hoặc credits hai lần. Khi báo cáo, giữ riêng gross usage, discount/credit và net cost để người đọc hiểu vì sao hóa đơn khác với mức tiêu thụ.

## 4. Duration trung bình và phân phối latency

Average duration hữu ích cho dự báo tổng compute, nhưng có thể che khuất các nhóm request chậm.

Ví dụ:

- 90% request xử lý trong 100 ms.
- 9% xử lý trong 400 ms.
- 1% xử lý trong 5 giây.

Average không cho biết tail latency và không đủ để lập kế hoạch timeout, concurrency hoặc provisioned capacity.

Nên theo dõi:

- p50 duration.
- p90/p95 duration.
- p99 duration.
- Maximum duration.
- Duration theo function version, route hoặc loại message.
- Duration theo kết quả success/retry/error.

Để dự báo hóa đơn, dùng tổng billable duration hoặc average được tính từ phân phối và số lượng từng loại request. Để thiết kế capacity và SLO, dùng thêm percentile và peak concurrency.

Nếu có nhiều class workload, hãy tính riêng:

\[
U_{\text{compute}} =
\sum_{k=1}^{K}
N_k \times D_k \times M_k
\]

Trong đó \(k\) là nhóm request, ví dụ create-order, generate-report hoặc resize-image.

## 5. Retry làm tăng số lần tính phí

Retry là một phần của độ tin cậy nhưng cũng là một driver chi phí. Một message có thể tạo nhiều invocation nếu function lỗi, timeout, bị throttling hoặc không ack kịp.

Nếu trung bình một operation có \(A\) attempt:

\[
N_{\text{attempts}} =
N_{\text{logical operations}} \times A
\]

Ví dụ 2 triệu operation và 1,08 attempt trung bình:

\[
N_{\text{attempts}} =
2.000.000 \times 1,08
= 2.160.000
\]

Phần 160.000 attempt bổ sung làm tăng request, compute và có thể cả queue/API operations.

Retry có thể còn làm tăng chi phí downstream nếu mỗi attempt gọi database hoặc provider. Đo retry theo nguyên nhân:

- Throttling.
- Timeout.
- Network error.
- Business rejection.
- Poison message.
- Dependency unavailable.
- Duplicate delivery.

Không phải mọi retry đều tốn duration giống nhau. Một attempt thất bại sau 20 ms khác một attempt timeout sau 30 giây. Dùng duration thực tế của từng nhóm attempt khi forecast.

### 5.1. Retry storm và chi phí khuếch đại

Khi dependency quá tải, retry đồng loạt có thể làm request count và compute tăng trong khi tỷ lệ thành công giảm. Hệ thống có thể trả tiền cho nhiều lần xử lý nhưng không tạo thêm business value.

Các biện pháp giảm chi phí retry không làm mất độ tin cậy:

- Phân loại lỗi retryable và permanent.
- Exponential backoff và jitter.
- Giới hạn số attempt.
- Dùng idempotency để retry an toàn.
- Circuit breaker khi downstream liên tục lỗi.
- DLQ cho message không thể xử lý sau policy.
- Giảm concurrency khi dependency quá tải.
- Reconcile kết quả không rõ trước khi gọi lại side effect.

Đừng giảm retry một cách máy móc chỉ để giảm hóa đơn. Mục tiêu là giảm lần thử vô ích và giữ tỷ lệ hoàn tất nghiệp vụ.

## 6. Batch size ảnh hưởng đến chi phí như thế nào?

Với event-driven function, batch có thể gom nhiều message vào một invocation. Điều này giảm số lần invocation và overhead khởi tạo handler, nhưng không có nghĩa compute giảm theo cùng tỷ lệ.

Một batch lớn có thể:

- Giảm request/invocation charge.
- Giảm số lần tạo execution environment trong một số workload.
- Tăng memory và duration do giữ nhiều payload.
- Tăng thời gian chờ để gom batch.
- Tăng phạm vi message bị retry nếu batch-level failure.
- Tạo thêm compute do xử lý lại record đã thành công nếu không dùng partial batch response.

Hãy đo batch size thực tế và duration theo batch size. Mô hình có thể dùng:

\[
C_{\text{batch compute}} =
N_{\text{batch invocations}}
\times D_{\text{batch}}
\times M_{\text{GB}}
\times R_{\text{compute}}
\]

Thêm request charge cho số batch invocation và queue operations theo provider.

Ví dụ 1 triệu message với effective batch size 10 có thể tạo xấp xỉ 100.000 invocation nếu batch đầy và không có retry. Nếu batch thực tế trung bình chỉ có 4 message, số invocation gần 250.000. Dùng số liệu thực từ event source mapping thay vì batch size tối đa.

Không tăng batch size chỉ để giảm invocation. Kiểm tra payload limit, memory, processing duration, message age, timeout và partial failure behavior.

## 7. Memory và CPU: nhiều tài nguyên hơn có thể rẻ hơn

Với một số FaaS, memory allocation đồng thời quyết định hoặc ảnh hưởng lượng CPU được cấp. Tăng memory có thể làm Java function xử lý nhanh hơn, giảm duration và giảm compute tổng.

Giả sử:

- Cấu hình A: 512 MiB, chạy 800 ms.
- Cấu hình B: 1.024 MiB, chạy 300 ms.

Compute usage tương đối:

\[
U_A = 0,5 \times 0,8 = 0,4\ \text{GB-second}
\]

\[
U_B = 1,0 \times 0,3 = 0,3\ \text{GB-second}
\]

Trong ví dụ, cấu hình B dùng compute unit ít hơn dù memory gấp đôi. Nếu request pricing và các khoản khác không đổi, compute cost có thể thấp hơn.

Nhưng không nên giả định tăng memory luôn giảm chi phí. Một function bị chờ database hoặc API có thể không nhanh hơn khi tăng CPU. Cần benchmark các mức memory/CPU trên cùng input và concurrency.

### 7.1. Quy trình memory tuning

1. Chọn một bộ input đại diện.
2. Chạy từng mức memory/CPU trong môi trường tương đương.
3. Đo duration, p95/p99, memory peak và lỗi.
4. Tính compute usage cho mỗi cấu hình.
5. Tính cost per successful operation.
6. Chọn cấu hình đáp ứng SLO với chi phí và headroom phù hợp.
7. Kiểm tra lại dưới burst/concurrency thực tế.

Với Java, quan sát thêm heap, garbage collection, thread count, class loading, connection pool và native memory. Memory allocation của nền tảng không đồng nghĩa toàn bộ phần đó là Java heap.

## 8. Cold start và capacity giữ sẵn

Cold start có thể ảnh hưởng cả latency và chi phí. Tuy nhiên, tác động billing phụ thuộc provider và cách triển khai.

Khi mô hình chi phí, tách:

- Số lần khởi tạo mới.
- Thời gian initialization.
- Thời gian handler.
- Billable duration theo quy tắc provider.
- Capacity được giữ sẵn.
- Chi phí snapshot/restore hoặc cấu hình đặc biệt nếu có.

Nếu initialization được tính trong billable duration, phần compute bổ sung có thể ước lượng:

\[
U_{\text{init}} =
N_{\text{cold starts}} \times D_{\text{billable init}} \times M_{\text{GB}}
\]

Chỉ dùng công thức này nếu init duration chưa nằm trong tổng billable duration đã đo. Nếu đã bao gồm, không cộng lần nữa.

### 8.1. Provisioned concurrency và minimum instances

Capacity giữ sẵn có thể giảm cold start nhưng tạo chi phí khi không có request. Mô hình cần tách:

- Chi phí capacity provisioned theo thời gian.
- Chi phí invocation và compute khi capacity được sử dụng.
- Số giờ/ngày capacity được bật.
- Số lượng capacity giữ sẵn theo lịch.
- Phần request vượt capacity provisioned và chạy theo cơ chế scale khác.

Với AWS Lambda, Provisioned Concurrency có pricing dimension riêng ngoài request/duration usage; cách tính cụ thể phụ thuộc region và cấu hình. Với Cloud Run hoặc nền tảng container serverless, minimum instances có billing semantics theo CPU allocation/instance-based billing và trạng thái instance. Đọc bảng giá và cấu hình thực tế trước khi tính.

Không so sánh cold start cost với warm cost mà bỏ qua chi phí capacity giữ sẵn. Hãy so sánh tổng chi phí theo lịch traffic và latency SLO.

### 8.2. Khi nào nên giữ capacity?

Có thể cân nhắc provisioned/minimum capacity khi:

- p95/p99 cold latency vi phạm SLO.
- Traffic có thể dự báo theo giờ.
- Function xử lý giao dịch cần latency ổn định.
- Chi phí giữ sẵn thấp hơn tác động kinh doanh của latency.
- Có đủ traffic ổn định để sử dụng capacity đã cấp.

Nếu traffic rất thưa và latency cho phép, scale-to-zero thường kinh tế hơn. Nếu traffic liên tục và utilization cao, cần so sánh FaaS với container/service chạy liên tục theo tổng chi phí compute và vận hành.

## 9. Concurrency và traffic shape

Tổng invocation trong tháng không mô tả đầy đủ traffic. Hai workload có cùng 10 triệu invocation có thể có chi phí khác nhau:

- Workload A phân bố đều trong 30 ngày.
- Workload B tập trung trong các đợt burst ngắn.
- Workload C có peak theo giờ và cần capacity giữ sẵn.
- Workload D nhận burst lớn khiến scale-out, retry, throttling hoặc queue age tăng.

Concurrency trung bình trong trạng thái ổn định có thể ước lượng bằng Little's Law:

\[
C_{\text{avg}} \approx \lambda \times D
\]

Trong đó \(\lambda\) là arrival rate (request/giây), \(D\) là thời gian xử lý trung bình (giây).

Ví dụ 120 request/giây với duration 0,24 giây:

\[
C_{\text{avg}} \approx 120 \times 0,24 = 28,8
\]

Con số này là concurrency trung bình lý tưởng, không phải cấu hình max concurrency. Peak concurrency cần được đo hoặc mô hình từ traffic burst, tail duration và khả năng scale của nền tảng.

Concurrency có thể tác động đến chi phí gián tiếp:

- Tăng connection và request tới database.
- Tăng throttling và retry.
- Tăng số instance hoặc capacity provisioned.
- Tạo nhiều log/trace hơn.
- Làm cache hit rate thay đổi.
- Làm downstream autoscale hoặc tính phí theo capacity.

## 10. Queue có chi phí riêng

Một event-driven function không chỉ tốn compute. Queue/broker có thể tính theo:

- Số request/API operation.
- Số message publish/receive/delete/ack.
- Payload size hoặc data volume.
- Storage duration và retention.
- Throughput unit, partition hoặc capacity provisioned.
- Cross-region replication hoặc data transfer.
- Dead-letter và replay operations.

Ví dụ, một message đi qua producer, queue, consumer và DLQ có thể tạo nhiều broker operations. Khi retry tăng, số receive/ack hoặc redelivery cũng tăng.

Với SQS, Pub/Sub, Kafka và Azure Service Bus, billing dimensions khác nhau. Kafka tự quản lý có thể tính theo broker instance/storage/network; dịch vụ Kafka managed có thể tính theo capacity/throughput hoặc partition. Không dùng một công thức queue chung thay cho bảng giá provider.

### 10.1. Retention và backlog

Queue giữ message lâu hơn có thể làm tăng storage hoặc capacity cost tùy dịch vụ. Backlog lớn cũng có thể kéo dài thời gian consumer chạy và tăng compute trong các giờ drain.

Chi phí backlog không chỉ là storage:

- Consumer cần chạy lâu hơn để drain.
- Message có thể retry nhiều lần.
- DLQ cần lưu và replay.
- Business operation hoàn tất trễ, có thể tạo chi phí hỗ trợ hoặc SLA penalty.
- Database và downstream có thể phải scale để xử lý backlog.

Theo dõi oldest message age, backlog, arrival rate, ack rate và estimated drain time cùng với cost.

## 11. API gateway, ingress và workflow charges

HTTP function thường nằm sau API Gateway, load balancer, ingress hoặc authentication layer. Mỗi lớp có thể có request charge, capacity charge hoặc data processing fee.

Workflow orchestration cũng có thể được tính phí theo số state transition, execution hoặc thời gian chạy tùy dịch vụ. Một workflow có nhiều state nhỏ và retry nhiều có thể tốn hơn workflow có ít state hơn dù tổng compute Lambda tương đương.

Mô hình cần ghi nhận:

- Số API request và kích thước payload.
- Số gateway/load balancer request.
- Số workflow execution.
- Số state transition hoặc task operation.
- Số lần retry/redrive.
- Thời gian workflow chờ callback nếu dịch vụ tính phí theo duration.
- Các integration request tới dịch vụ khác.

Không giả định Wait state hoặc callback chờ lâu luôn miễn phí; cách tính phụ thuộc dịch vụ và loại workflow.

## 12. Network và egress

Network là phần dễ bị bỏ sót trong mô hình chi phí:

- Internet egress.
- Cross-region data transfer.
- Cross-zone transfer.
- NAT gateway hourly/processing.
- VPC connector hoặc private networking.
- Data transfer giữa function và database ở region/zone khác.
- API provider trả dữ liệu lớn.
- Log/trace export sang region hoặc vendor khác.

Một function nhỏ có thể có compute cost thấp nhưng network cost cao nếu xử lý file lớn hoặc gọi nhiều service qua NAT.

Đo byte vào/ra theo operation class và region. Khi function truy cập database private, xem chi phí NAT, connector hoặc network architecture thực tế. Không đưa dữ liệu nhạy cảm vào telemetry chỉ để phân bổ network cost.

## 13. Logs, metrics và traces cũng là chi phí

Debug logging quá chi tiết có thể tạo lượng log lớn hơn dữ liệu nghiệp vụ. Mỗi invocation có thể ghi nhiều dòng; retry và burst làm log volume tăng theo traffic.

Các driver:

- Log ingestion volume.
- Log retention duration.
- Query scan volume.
- Metrics time series và cardinality.
- Trace span volume và sampling.
- Export/network cost tới observability vendor.
- Alerting và dashboard query.

Ví dụ, log toàn bộ request/response JSON cho mỗi message có thể làm tăng storage, query cost và rủi ro lộ dữ liệu.

### 13.1. Kiểm soát observability cost

- Dùng structured log và chỉ ghi field cần thiết.
- Không log secret, token, payment data hoặc payload nhạy cảm.
- Chọn retention theo yêu cầu vận hành và audit.
- Sampling trace có chiến lược; giữ trace lỗi/slow request theo policy.
- Tránh metric label có cardinality cao như message ID, order ID hoặc customer ID.
- Dùng log level phù hợp giữa production và test.
- Theo dõi GB log/ngày và chi phí trên mỗi 1.000 operation.

Không giảm telemetry đến mức mất khả năng điều tra. Mục tiêu là thu đúng tín hiệu với volume và retention phù hợp.

## 14. Chi phí downstream có thể lớn hơn function

Một function xử lý 200 ms có thể gọi database query 3 lần, đọc object storage, gọi payment API và publish event. Compute function chỉ là một phần của cost per operation.

Cần tính:

- Database instance/serverless capacity, storage và I/O.
- Cache capacity và request.
- Object storage request và bytes.
- KMS/secret operations.
- NAT và data transfer.
- External API usage hoặc provider fees.
- Search/indexing và analytics.
- Queue và event bus.
- Shared platform cost phân bổ cho service.

Nếu nhiều function cùng dùng database, không gán toàn bộ database bill cho một function. Dùng query count, connection time, storage usage, tenant/service tag hoặc allocation rule được thống nhất để phân bổ chi phí dùng chung.

Một kiến trúc có compute function rẻ nhưng cần database luôn bật với capacity lớn có thể đắt hơn một container service dùng chung database đó. Hãy so sánh toàn bộ đường đi của operation.

## 15. Tính cost per successful business operation

Một metric FinOps hữu ích là chi phí trên mỗi operation nghiệp vụ hoàn tất:

\[
C_{\text{per success}} =
\frac{C_{\text{allocated total}}}
{N_{\text{successful unique operations}}}
\]

Tử số cần gồm các chi phí liên quan đã phân bổ: function, request, queue, gateway, network, observability, storage và downstream. Mẫu số là số operation duy nhất hoàn tất, không phải số invocation hoặc số attempt.

Ví dụ:

- Tổng chi phí được phân bổ cho order service: 1.200 đơn vị tiền trong tháng.
- Có 400.000 order hoàn tất duy nhất.

\[
C_{\text{per order}} =
\frac{1.200}{400.000}
= 0,003
\]

Đơn vị tiền ở đây chỉ là đơn vị minh họa. Cần thống nhất currency và cách phân bổ shared cost.

Theo dõi cost per success theo:

- Service/function.
- Environment.
- Operation type.
- Tenant hoặc customer segment nếu policy cho phép.
- Region.
- Release/version.
- Kênh hoặc nguồn traffic.

Không dùng số invocation làm mẫu số vì retry tăng có thể khiến cost per invocation trông giảm dù số operation thành công không đổi.

## 16. Mẫu bảng mô hình chi phí

Có thể lập một bảng dự báo theo tháng với các cột:

| Biến | Ý nghĩa | Nguồn dữ liệu |
|---|---|---|
| Business operations | Số intent nghiệp vụ duy nhất | Product analytics/domain metrics |
| Attempts per operation | Số lần xử lý trung bình | Retry/delivery metrics |
| Invocations per operation | Số function call trên mỗi intent | Trace/workflow map |
| Batch size thực tế | Số message mỗi invocation | Event source metrics |
| Billable duration | Duration theo billing semantics | Provider billing/runtime metrics |
| Memory/CPU allocation | Tài nguyên cấu hình | Deployment config |
| Request unit price | Đơn giá invocation | Pricing calculator/current price list |
| Compute rate | Đơn giá compute unit | Pricing calculator/current price list |
| Provisioned capacity | Capacity và thời gian giữ sẵn | Platform configuration |
| Queue/API/network | Request, byte, retention và egress | Service metrics/billing export |
| Observability | Log, metric, trace volume | Observability usage |
| Downstream allocation | Chi phí database/cache/provider | Cost allocation/usage metrics |
| Successful operations | Số operation hoàn tất duy nhất | Domain metrics |

Tính riêng low/base/high scenario. Mỗi scenario cần nêu rõ giả định về traffic, attempt rate, duration, batch size, peak concurrency và capacity giữ sẵn.

## 17. Ví dụ dự báo theo ba kịch bản

Giả sử một Java function xử lý lệnh tạo báo cáo. Bảng sau dùng số liệu giả định để minh họa cách lập forecast:

| Biến | Low | Base | High |
|---|---:|---:|---:|
| Business operations/tháng | 500.000 | 1.000.000 | 2.000.000 |
| Attempts trung bình | 1,01 | 1,05 | 1,15 |
| Invocations/operation | 1 | 1 | 1 |
| Memory | 512 MiB | 512 MiB | 1.024 MiB |
| Billable duration | 200 ms | 300 ms | 450 ms |
| Provisioned capacity | 0 | Theo giờ cao điểm | Cao hơn base |

Số invocation:

\[
N = \text{Operations} \times \text{Attempts}
\]

Compute usage:

\[
U = N \times D_{\text{seconds}} \times M_{\text{GB}}
\]

| Kịch bản | Invocation ước tính | Compute usage minh họa |
|---|---:|---:|
| Low | 505.000 | 50.500 GB-second |
| Base | 1.050.000 | 157.500 GB-second |
| High | 2.300.000 | 1.035.000 GB-second |

High scenario có memory gấp đôi base, duration dài hơn và attempt rate cao hơn nên compute tăng mạnh. Khi dùng bảng này trong thực tế, cần bổ sung request charge, capacity giữ sẵn và các dịch vụ phụ trợ.

Forecast không phải cam kết hóa đơn. Hãy thay giả định bằng dữ liệu billing/runtime sau mỗi chu kỳ và cập nhật theo traffic thực tế.

## 18. Phân tích độ nhạy

Sensitivity analysis cho biết biến nào tác động lớn nhất đến chi phí:

- Số operation tăng 20%.
- Retry rate tăng từ 1,02 lên 1,15 attempt/operation.
- Duration tăng 30% do downstream latency.
- Memory tăng một bậc để giảm duration.
- Batch size tăng nhưng message age cũng tăng.
- Provisioned capacity được bật thêm 8 giờ/ngày.
- Log volume tăng do debug logging.
- Egress tăng do payload lớn.

Với mô hình compute tuyến tính, nếu invocation tăng 20% và các yếu tố khác giữ nguyên, compute usage cũng tăng xấp xỉ 20%. Nhưng nếu concurrency tăng làm throttling/retry tăng, tổng chi phí có thể tăng nhanh hơn.

Hãy xếp hạng các biến theo mức tác động và khả năng kiểm soát. Thường duration, retry, memory/CPU, batch behavior và downstream cost đáng được đo kỹ.

## 19. So sánh FaaS với container hoặc service chạy liên tục

FaaS thường phù hợp với workload biến động, có thể scale-to-zero và không cần duy trì process liên tục. Container/service chạy liên tục có thể kinh tế hơn khi utilization cao, traffic ổn định hoặc cần xử lý lâu dài.

So sánh cần tính:

| Yếu tố | FaaS | Container/service |
|---|---|---|
| Billing compute | Theo invocation/duration hoặc compute unit | Theo instance/vCPU/memory theo thời gian |
| Scale-to-zero | Thường có | Phụ thuộc nền tảng và cấu hình |
| Capacity giữ sẵn | Có thể có charge riêng | Instance/min replica luôn có chi phí |
| Cold start | Có thể ảnh hưởng latency | Có thể giảm bằng instance luôn chạy |
| Traffic burst | Nền tảng tự scale trong giới hạn | Cần autoscaling/capacity planning |
| Runtime duration | Có giới hạn theo dịch vụ | Linh hoạt hơn tùy nền tảng |
| Operational overhead | Ít quản lý server hơn | Quản lý service/container và scaling |

Không có điểm hòa vốn chung. Hãy dùng traffic theo giờ, utilization, memory/CPU, min capacity, retry và downstream cost để mô hình hóa cả hai phương án. Nếu cả hai dùng cùng database hoặc queue, giữ phần shared cost nhất quán trong phép so sánh.

## 20. FinOps: đo, phân bổ, tối ưu và kiểm soát

FinOps là vòng lặp hợp tác giữa engineering, finance và product để hiểu chi phí theo giá trị tạo ra.

Một vòng lặp thực tế:

1. **Measure:** thu thập usage, billing export và business metrics.
2. **Allocate:** gắn cost với service, team, environment và owner.
3. **Forecast:** dự báo theo low/base/high traffic.
4. **Optimize:** điều chỉnh duration, memory, batch, retry, capacity và data transfer.
5. **Govern:** đặt budget, alert, ownership và review định kỳ.
6. **Learn:** so sánh cost per success trước/sau thay đổi.

### 20.1. Tagging và allocation

Gắn nhãn tài nguyên theo quy ước thống nhất, ví dụ:

~~~text
service = orders-api
team = commerce-platform
environment = production
cost_center = CC-042
owner = team-orders
module = cloud-serverless
~~~

Không phải mọi chi phí đều có thể gắn tag trực tiếp. Với shared database, network hoặc observability platform, cần allocation rule dựa trên usage metric hoặc tỷ lệ đã thống nhất.

Đảm bảo tag được áp dụng cho function, queue, state machine, log group, storage, database và network resources khi dịch vụ hỗ trợ. Kiểm tra tài nguyên không có owner để tránh chi phí không được phân bổ.

### 20.2. Budget và anomaly detection

Thiết lập:

- Budget theo service/team/environment.
- Alert khi forecast vượt ngân sách.
- Alert khi daily spend tăng bất thường.
- Theo dõi cost per operation và cost per success.
- Theo dõi retry rate, duration và log volume.
- Review resource giữ sẵn không được sử dụng.
- Phát hiện tài nguyên test/staging tồn tại quá lâu.

Một hóa đơn tăng có thể do traffic hợp lệ, retry storm, log verbosity, egress hoặc resource provisioned. Alert cần đi kèm usage metric để xác định nguyên nhân.

## 21. Tối ưu chi phí mà vẫn giữ SLO

Các lựa chọn tối ưu nên gắn với nguyên nhân:

| Dấu hiệu | Hướng tối ưu |
|---|---|
| Duration cao do CPU | Benchmark memory/CPU cao hơn |
| Duration cao do API chậm | Timeout hợp lý, connection reuse, giảm call thừa |
| Retry rate cao | Sửa lỗi gốc, backoff/jitter, idempotency |
| Batch nhỏ thường xuyên | Điều chỉnh batching window và batch size |
| Batch lớn gây timeout | Giảm batch hoặc xử lý partial failure |
| Cold latency vi phạm SLO | So sánh provisioned/min capacity với tác động latency |
| Log volume cao | Structured log, sampling và retention |
| Egress/NAT cao | Tối ưu data path và placement |
| Database cost cao | Query/index/pooling và capacity tuning |
| Capacity giữ sẵn idle | Điều chỉnh lịch và mức provisioned |

Không tối ưu compute bằng cách tăng timeout để tránh lỗi nếu điều đó khiến invocation chạy lâu và tính phí nhiều hơn. Không bỏ logging cần thiết hoặc giảm retry quan trọng chỉ để giảm bill.

Mỗi thay đổi nên được so sánh theo cả hai chỉ số:

\[
\Delta C = C_{\text{after}} - C_{\text{before}}
\]

\[
\Delta SLO = SLO_{\text{after}} - SLO_{\text{before}}
\]

Một thay đổi tốt giảm cost per successful operation trong khi vẫn đáp ứng latency, reliability và correctness requirements.

## 22. Guardrails để tránh chi phí bất ngờ

Đặt giới hạn và cảnh báo cho:

- Maximum function duration/timeout.
- Memory/CPU allocation.
- Reserved/max concurrency.
- Queue batch size và retry count.
- DLQ depth và redrive rate.
- Provisioned concurrency/min instances.
- Ephemeral storage và payload size.
- Log retention và trace sampling.
- Egress và cross-region transfer.
- Database connection pool và capacity.
- Budget theo ngày/tháng.
- Cost per successful operation.

Các guardrail cần phù hợp với nghiệp vụ. Ví dụ, max concurrency bảo vệ database nhưng có thể làm backlog tăng; alert cần báo cả downstream saturation và message age để vận hành biết trade-off.

## 23. Quy trình lập mô hình chi phí function

1. **Xác định business unit.** Một order, payment attempt, event hoặc report là một operation?
2. **Vẽ execution path.** Liệt kê tất cả function, queue, API, workflow và downstream service.
3. **Thu thập traffic.** Số operation theo ngày/giờ, burst, tăng trưởng và seasonality.
4. **Đo runtime.** Invocation, attempt, duration, memory/CPU, batch size và cold start.
5. **Ước lượng compute.** Tính billable compute unit theo semantics provider.
6. **Tính request và event charges.** Function, queue, gateway và workflow operations.
7. **Bổ sung capacity giữ sẵn.** Provisioned concurrency, min instances và thời gian bật.
8. **Bổ sung network/observability/storage.** Egress, NAT, logs, traces và retention.
9. **Phân bổ downstream.** Database, cache, object storage và external services.
10. **Lập low/base/high scenario.** Nêu giả định retry, duration, batch và traffic shape.
11. **Tính cost per success.** Chia tổng chi phí được phân bổ cho operation duy nhất hoàn tất.
12. **Đối chiếu hóa đơn.** So forecast với billing export và điều chỉnh giả định.
13. **Đặt budget và alert.** Theo dõi cost anomaly cùng usage/quality signals.
14. **Review sau thay đổi.** So cost, latency, reliability và business outcome.

## 24. Câu hỏi tự kiểm tra

- Vì sao số business operation khác số function invocation?
- Những thành phần nào tạo chi phí function serverless?
- GB-second hoặc compute unit được tính từ những biến nào?
- Vì sao phải kiểm tra billing semantics trước khi cộng initialization duration?
- Retry làm tăng chi phí theo những cách nào?
- Batch size ảnh hưởng invocation count và retry cost ra sao?
- Vì sao tăng memory đôi khi giảm compute cost?
- Cold start và provisioned capacity tác động đến cost như thế nào?
- Traffic burst ảnh hưởng concurrency và billing ra sao?
- Queue, API gateway, network và observability có những cost driver nào?
- Vì sao cost per successful operation hữu ích hơn cost per invocation?
- Cần phân bổ shared database cost như thế nào?
- Khi nào nên so sánh FaaS với container chạy liên tục?
- FinOps cần những bước measure, allocate, forecast và optimize nào?
- Những guardrail nào giúp phát hiện chi phí tăng bất thường?


