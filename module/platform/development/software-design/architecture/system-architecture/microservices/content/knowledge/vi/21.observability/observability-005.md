# Chỉ số lưu lượng, lỗi, độ trễ và mức bão hòa trong Microservices

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Quan sát hệ thống.
>
> **Trọng tâm:** Bốn tín hiệu quan sát thiết yếu — **Traffic (lưu lượng), Errors (lỗi), Latency (độ trễ), Saturation (mức bão hòa)** — giúp phân biệt hệ thống đang bận, đang chậm, đang hỏng hay đang gần cạn năng lực xử lý. Bài học diễn giải ý nghĩa nghiệp vụ và kỹ thuật của mỗi tín hiệu, cách đo trên từng service và toàn chuỗi request, cách thiết lập dashboard/cảnh báo và cách xử lý sự cố dựa trên bằng chứng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Định nghĩa chính xác traffic, error rate, latency và saturation với tử số, mẫu số, đơn vị và cửa sổ thời gian phù hợp.
2. Phân biệt **metric của một service** với trải nghiệm **end-to-end** của người dùng trong kiến trúc microservices.
3. Chọn counters, histograms, gauges và nhãn (labels) an toàn để thu thập bốn tín hiệu trên HTTP/gRPC, message queue, database và worker.
4. Đọc p50/p95/p99, tỷ lệ lỗi, lượng request đang xử lý, queue depth và concurrency để tìm bottleneck.
5. Viết và giải thích các truy vấn PromQL minh họa để đo requests/second, error ratio, latency percentile và độ sử dụng connection pool.
6. Liên kết metric với **SLI/SLO/error budget**, thiết kế alert ít nhiễu và truy nguyên bằng log/trace.
7. Thiết kế một bài thử tải hoặc tình huống sự cố có thể xác nhận hệ thống quan sát phản ánh đúng hành vi thực.

Các giá trị ngưỡng và tên metric trong ví dụ là **minh họa**. Chúng cần được điều chỉnh theo workload, HTTP library, Micrometer/OpenTelemetry exporter, latency budget và SLO thực tế của mỗi hệ thống.

## 2. Vì sao bốn tín hiệu này quan trọng?

Một hệ thống microservices có thể gồm nhiều thành phần độc lập:

~~~text
                       ┌──────────────────────┐
Clients ──► Gateway ──►│ Order Service        │
                       │                      ├──► Inventory Service ──► DB
                       └──────────┬───────────┘
                                  │
                                  ├──────────────► Payment Service ──► Provider
                                  │
                                  └──► Message Broker ──► Notification Worker
~~~

Nếu khách hàng nói "không đặt được hàng", chỉ xem CPU Order Service không thể xác định nguyên nhân. Có thể Gateway đang nhận nhiều lưu lượng hơn trước; Payment trả lỗi; Inventory trả thành công nhưng chậm; hoặc worker xử lý queue bị bão hòa.

Bốn tín hiệu trả lời bốn câu hỏi khác nhau:

| Tín hiệu | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Traffic** | Bao nhiêu công việc đang đến/được xử lý? | 500 request/giây vào Order |
| **Errors** | Bao nhiêu công việc không đạt kết quả mong đợi? | 5% request checkout thất bại |
| **Latency** | Một đơn vị công việc mất bao lâu? | p95 checkout = 1,8 giây |
| **Saturation** | Tài nguyên hoặc năng lực xử lý còn dư bao nhiêu? | DB pool dùng 95% connection, queue chờ tăng |

Chúng thường được gọi là **Four Golden Signals** trong thực hành SRE. Dùng cùng nhau mới nhận ra được mẫu hình: traffic tăng có thể làm saturation tăng, kéo latency lên, rồi cuối cùng error rate tăng.

**Không phải quan hệ nào cũng tuyến tính.** Một dependency bên ngoài hỏng có thể gây 5xx ngay cả khi CPU và memory còn thấp. Một service đang bị rate limit có thể trả 429 rất nhanh, khiến latency p95 của các request được chấp nhận vẫn đẹp nhưng người dùng vẫn gặp lỗi. Ngược lại, queue tăng có thể là dấu hiệu sớm hơn error rate.

## 3. Đặt ranh giới đo lường: bên ngoài khác bên trong

### 3.1. Trải nghiệm người dùng và health của service

Xét thao tác **POST /checkout**. Khách hàng quan tâm yêu cầu có hoàn tất hay không và mất bao lâu. Tuy nhiên nội bộ có nhiều lời gọi:

~~~text
User → Gateway [35 ms]
            → Order [25 ms]
                ├── Inventory [140 ms]
                ├── Payment   [800 ms]
                └── DB commit [40 ms]
         → Response
~~~

Nếu các lời gọi được thực hiện tuần tự và không có thời gian chờ khác, latency end-to-end có thể xấp xỉ tổng các thành phần. Nhưng nếu có lời gọi song song, retry, queue, serialization, mạng và scheduling, không thể cộng từng p95 để suy ra p95 của checkout.

**Hai lớp đo bắt buộc phải phân biệt:**

- **Bên ngoài (black-box):** đo tại Gateway, edge, client hoặc synthetic transaction. Đây là tín hiệu về hành vi người dùng thực sự quan sát được.
- **Bên trong (white-box):** đo trên từng service, dependency client, thread pool, queue, DB và runtime. Đây là tín hiệu để chẩn đoán nguyên nhân.

Một dashboard có thể cho biết **checkout p99 cao**; trace liên kết có thể chỉ ra nhiều request đang chờ connection đến Payment. Metric cho biết **mức độ và thời gian** của vấn đề; trace cho biết **đường đi** của một số request; log cho biết **ngữ cảnh sự kiện cụ thể**.

### 3.2. Đơn vị công việc phải rõ ràng

Tùy giao thức, "một request" có thể là:

- Một HTTP/gRPC request của người dùng.
- Một lần gọi downstream HTTP do client thực hiện.
- Một message được consumer tiếp nhận.
- Một job được hoàn tất.
- Một transaction được commit.
- Một record được xử lý trong batch.

Không tự gom các đơn vị khác nhau vào chung một denominator. Ví dụ một checkout phát ra ba lần retry Inventory thì **một yêu cầu người dùng** có thể tạo ra **bốn downstream attempts**. Traffic và error rate ở hai tầng không giống nhau.

## 4. Traffic — đo nhu cầu và khả năng xử lý

### 4.1. Traffic là gì?

Traffic mô tả tốc độ công việc đến hoặc công việc được xử lý trong một khoảng thời gian. Với HTTP, đo bằng **requests per second (RPS)**; với queue, có thể dùng **messages/second**; với batch có thể dùng **items/second**.

Ví dụ trong cửa sổ 5 phút:

[
\mathrm{RPS} = \frac{\text{số request trong cửa sổ}}{\text{số giây của cửa sổ}}
]

Nếu nhận 90.000 request trong 300 giây, traffic trung bình là 300 RPS. Tuy vậy một đợt đột biến 2.000 RPS trong 10 giây có thể bị che bởi trung bình 5 phút.

**Counter tích lũy** là kiểu đo phổ biến cho tổng request từ khi process khởi động. Hệ thống truy vấn dùng `rate(...[5m])` để suy ra tốc độ trung bình và xử lý counter reset khi process restart.

### 4.2. Các cách chia traffic hữu ích

| Chiều phân tích | Ví dụ | Mục đích |
| --- | --- | --- |
| Service | `order-service` vs `payment-service` | Service nào chịu nhu cầu nhiều hơn |
| Operation/route template | `/orders/{id}`, `/checkout` | Endpoint nào đang tăng |
| HTTP method | GET, POST | Phân biệt đọc/ghi khi có ý nghĩa |
| Environment/region/zone | production, region-a | Phát hiện sự cố riêng một vùng |
| Kết quả | success, error, throttled | Tách lưu lượng được phục vụ và bị từ chối |
| Caller/consumer class | gateway, trusted-batch | Biết nguồn nhu cầu theo nhãn được kiểm soát |

**Không đặt ID riêng của từng request, user, session hoặc order vào metric label.** Mỗi giá trị label mới tạo một time series; số tổ hợp tăng nhanh gây quá tải TSDB và tăng chi phí.

### 4.3. Requested, admitted và completed traffic

Để chẩn đoán đầy đủ, phân biệt:

1. **Offered/requested traffic:** số request hoặc message đầu vào hệ thống.
2. **Admitted traffic:** phần được cho phép vào xử lý sau rate limit, authentication, queue capacity.
3. **Completed traffic:** phần kết thúc với outcome xác định.
4. **Rejected/dropped traffic:** phần bị từ chối do limit, overload, timeout, hoặc policy.

Nếu Gateway nhận 1.000 RPS nhưng Order chỉ xử lý 600 RPS, throughput nội bộ có vẻ bình thường trong khi 400 RPS bị chặn. Chỉ nhìn traffic tại Order sẽ đánh giá thấp mức nhu cầu thực và tác động đến người dùng.

### 4.4. Traffic đối với event-driven services

Với Kafka/RabbitMQ hoặc hàng đợi tương tự, cần ít nhất:

- **Publish rate**: producer đưa vào bao nhiêu message/giây.
- **Consume rate**: consumer xử lý thành công bao nhiêu message/giây.
- **Attempt/retry rate**: bao nhiêu lần thử xử lý, có thể lớn hơn số message duy nhất.
- **Lag/backlog**: lượng còn chờ; với hệ thống có offset là số bản ghi chưa theo kịp.
- **Message age**: thời gian message chờ tới khi bắt đầu xử lý.
- **Dead-letter count/rate**: số message bị chuyển sang DLQ.
- **Duplicate/idempotency rate**: bao nhiêu message lặp lại được nhận nhưng không tạo side effect lần hai.

**Message received** khác **message successfully processed**. Một consumer đọc nhanh rồi xử lý thất bại/requeue liên tục không có nghĩa hệ thống đang theo kịp công việc nghiệp vụ.

### 4.5. Traffic tăng: tốt hay xấu?

Traffic tăng có thể là tăng trưởng sản phẩm, chạy batch, retry storm, bot hoặc vòng lặp lỗi. Cần đọc cùng errors, latency và saturation.

Ví dụ:

| Tình huống | Traffic | Errors | Latency | Saturation |
| --- | --- | --- | --- | --- |
| Nhu cầu tăng, còn dư năng lực | Tăng | Ổn định thấp | Ổn định | Tăng nhẹ |
| Hệ thống bắt đầu nghẽn | Tăng | Có thể chưa tăng | p95/p99 tăng | Queue/pool tăng mạnh |
| Retry storm | Downstream attempts tăng mạnh | Cao | Cao | Downstream gần đầy |
| Rate limit bảo vệ đúng | Gateway demand tăng; admitted traffic bị giới hạn | 429 có thể tăng | Admitted latency có thể ổn định | Được giữ trong giới hạn |

Traffic không nói điều gì tốt hay xấu nếu không có bối cảnh và mẫu số phù hợp.

## 5. Errors — đo kết quả không đạt kỳ vọng

### 5.1. Định nghĩa tỷ lệ lỗi

Một tỷ lệ lỗi cơ bản:

[
\mathrm{ErrorRatio} =
\frac{\text{failed requests}}{\text{eligible requests}}
]

Ví dụ 200 request lỗi trong 10.000 request đủ điều kiện:

[
\frac{200}{10{,}000} \times 100\% = 2\%
]

Cần định nghĩa **eligible request** và **failed** trước khi tính. Nếu không, hai đội có thể xuất cùng tên `error_rate` mà đo hai điều khác nhau.

### 5.2. HTTP status không đồng nghĩa toàn bộ với lỗi nghiệp vụ

| Kết quả | Xử lý thường gặp | Câu hỏi cần làm rõ |
| --- | --- | --- |
| 2xx | Thành công về giao thức | Payload có đáp ứng đúng mục đích không? |
| 3xx | Chuyển hướng theo thiết kế | Có tạo vòng lặp hoặc gián đoạn giao diện không? |
| 400 | Input không hợp lệ | Có phải người dùng/caller gửi sai? |
| 401/403 | Thiếu xác thực hoặc quyền | Có vấn đề trong hệ thống authn/authz hay denial dự kiến? |
| 404 | Không thấy tài nguyên | Trường hợp bình thường hay routing bug? |
| 408/499/client disconnect | Không hoàn tất từ góc nhìn nào? | Client đóng kết nối, timeout gateway hay server? |
| 429 | Bị rate limit | Là bảo vệ có chủ đích hay người dùng bị ảnh hưởng? |
| 500/502/503/504 | Lỗi server/downstream | Là lỗi tính trong availability SLI nào? |
| 200 chứa `status=FAILED` | HTTP thành công, nghiệp vụ thất bại | Có nên tính vào product SLI? |

Thông lệ là theo dõi **5xx ratio** như một tín hiệu vận hành quan trọng, nhưng không đủ cho mọi SLI. Ví dụ checkout trả HTTP 200 với `paymentRejectedDueToSystemError` vẫn làm trải nghiệm thất bại. Ngược lại, HTTP 404 khi tra một SKU không tồn tại có thể là kết quả hoàn toàn hợp lệ.

**Tách loại lỗi** để tránh việc dashboard đánh đồng:

- **Server/system failures:** exception không xử lý, timeout, dependency unavailable.
- **Client validation/authorization failures:** request không hợp lệ hoặc thiếu quyền.
- **Throttling/overload:** từ chối vì vượt capacity hoặc quota.
- **Business outcomes:** hết hàng, không đủ số dư, đơn không hợp lệ.
- **Degraded/partial success:** dùng cache cũ, bỏ qua tính năng phụ, trả dữ liệu ước lượng.

Việc xếp vào "bad request" của SLI phụ thuộc **hợp đồng người dùng**. Không loại một loại lỗi khỏi SLI chỉ để làm biểu đồ đẹp hơn.

### 5.3. Error budget và SLO

Giả sử service có SLO:

> Trong 30 ngày, ít nhất 99,9% request checkout hợp lệ hoàn tất thành công.

Khi đó ngân sách request không đạt được phép là:

[
\mathrm{ErrorBudgetFraction} = 1 - 0.999 = 0.001 = 0.1\%
]

Với 1.000.000 request đủ điều kiện trong cửa sổ, ngân sách là **1.000 bad requests**. Đây là **SLO theo request**; không tự chuyển thành "43,2 phút downtime" trừ khi SLO định nghĩa tỷ lệ theo thời gian.

Đặt:

- **SLI:** tỷ lệ request checkout hợp lệ kết thúc đúng nghiệp vụ.
- **SLO:** ngưỡng mục tiêu của SLI trong 30 ngày.
- **Error budget:** lượng hành vi xấu được phép trước khi mất SLO.
- **Burn rate:** tốc độ dùng ngân sách so với tốc độ dự kiến nếu dùng đều trong kỳ.

Burn rate **10×** hàm ý ngân sách đang cạn nhanh gấp mười lần tốc độ trung bình cho phép ở khoảng đo đó; không tự nói hệ thống đã hết toàn bộ budget nếu không xét thời gian còn lại và mức đã tiêu thụ.

### 5.4. Retry làm sai lệch cách đọc errors như thế nào?

Một request người dùng gọi Payment ba lần: hai lần timeout, lần ba thành công.

- **User-facing attempts:** một request cuối cùng có thể được xem là thành công.
- **Payment dependency attempts:** ba lần gọi, hai failure, một success.
- **Saturation:** downstream đã nhận gấp ba lượt công việc so với yêu cầu ban đầu.

Do đó nên đo riêng `user_request_total`, `dependency_attempt_total`, `retry_total`, `final_outcome_total`. Nếu tất cả đều tên "requests" và cộng chung, hệ thống sẽ đánh giá nhầm mức lỗi và lưu lượng.

Retry thao tác ghi cần idempotency: timeout không chứng minh downstream chưa xử lý xong.

### 5.5. Fallback và partial success

Circuit Breaker mở và Order trả cache "có thể còn hàng" với HTTP 200. Đối với màn hình tham khảo, đó có thể là degraded success. Đối với thao tác **giữ hàng**, đó không phải kết quả hoàn tất.

Vì vậy cần metric `fallback_total`, `degraded_response_total`, `business_failure_total`, cùng SLI được định nghĩa theo luồng nghiệp vụ. **Một dashboard chỉ có 5xx=0 chưa đủ chứng minh người dùng đang nhận dịch vụ đúng.**

### 5.6. Lỗi trong xử lý bất đồng bộ

Với queue consumer, `processing_failure_total` cần đi kèm `processing_attempt_total` và `processed_success_total`. Một message fail rồi được retry 5 lần có thể tạo 5 error attempts, nhưng chỉ một job nghiệp vụ chưa hoàn tất.

Thường cần thêm **time to complete**, tỷ lệ completed trước deadline, **DLQ messages**, số job bị treo và tuổi message lớn nhất. Đơn vị SLI có thể là **job duy nhất** thay vì số attempt.

## 6. Latency — đo thời gian, đặc biệt ở phần đuôi phân phối

### 6.1. Latency bắt đầu và kết thúc ở đâu?

Định nghĩa rõ điểm bắt đầu/kết thúc:

- **Client-perceived latency:** từ lúc client gửi request đến khi nhận response/đủ nội dung cần dùng.
- **Gateway latency:** từ khi Gateway nhận request đến khi gửi response.
- **Server processing latency:** từ khi framework nhận yêu cầu tới khi handler hoàn tất.
- **Downstream client latency:** từ lúc service gọi dependency đến khi có kết quả/exception.
- **Queue wait time:** thời gian message chờ được consumer xử lý.
- **Execution time:** thời gian worker thực thi business operation.

Một trace của checkout có thể cho thấy 150 ms networking/queue và 700 ms xử lý Payment; nếu chỉ đo handler Order hoặc chỉ đo DB query sẽ bỏ sót phần mà người dùng phải chờ.

### 6.2. Trung bình và percentile

Giả sử 100 request: 95 request mất 100 ms; 5 request mất 5.000 ms.

Trung bình:
[
\frac{95\times100 + 5\times5000}{100} = 345\mathrm{\ ms}
]

Con số 345 ms không nói rằng **5% khách hàng chịu 5 giây**. Cần xem phân phối:

- **p50:** khoảng 50% request có latency nhỏ hơn hoặc bằng mức này.
- **p90/p95:** mô tả phần lớn trải nghiệm, đặc biệt ở đuôi.
- **p99:** phản ánh nhóm rất chậm; cần đủ số mẫu và độ phân giải phù hợp.
- **Max:** chỉ một request cực đoan; nhạy với outlier.
- **Mean:** dùng để tính toán năng lực hoặc tổng công, nhưng có thể che tail.

Percentile là vị trí trong **phân phối** chứ không phải phần trăm thời gian service khỏe. p95=800 ms nghĩa xấp xỉ 95% mẫu đo không vượt 800 ms theo cách ước tính percentile của hệ thống đang dùng.

### 6.3. Histogram và khác biệt với summary

Một **histogram** ghi số lượng quan sát trong các bucket độ trễ, ví dụ `le=0.1s`, `le=0.25s`, `le=0.5s`, `le=1s`, `+Inf`. Từ tổng bucket theo label thích hợp, Prometheus có thể ước tính p95 trên nhiều replica.

**Summary** có thể cung cấp quantile tính tại client, nhưng quantile đó **không được cộng/trung bình** để suy ra quantile toàn service. Với các dashboard nhiều replica, histogram là lựa chọn thường thuận tiện hơn.

Bucket cần bám sát SLO. Nếu mục tiêu 95% dưới 400 ms mà chỉ có bucket 0.1s và 10s, phép ước tính quantile quá thô để phản ánh mốc 400 ms.

### 6.4. Latency của success và failure

Không chỉ đo request thành công. Timeout có thể mất 3 giây rồi báo lỗi; nếu chỉ ghi latency của success, p95 có thể **giảm** khi hệ thống lỗi nặng.

Nên có:

- Tổng latency của mọi attempt đủ điều kiện.
- Latency tách theo outcome `success`, `failure`, `timeout`, `rejected` khi nhãn được kiểm soát.
- End-to-end latency của user operation.
- Dependency latency để truy nguyên.

Cần tránh hiểu sai: request bị Circuit Breaker từ chối nhanh có latency rất thấp, nhưng không có nghĩa downstream đã khỏe.

### 6.5. Không cộng p95 qua các service

Một request qua Order, Inventory và Payment. Mỗi service đều có p95 < 200 ms không đảm bảo end-to-end p95 < 600 ms:

- Request chậm ở service A và B có thể rơi vào **những request khác nhau**.
- Tính song song, queue, network, timeout, retry làm phân phối tổng khác.
- Percentile không có tính cộng tuyến tính như giá trị trung bình trong mọi trường hợp.

Muốn biết p95 checkout, **đo trực tiếp checkout tại boundary tương ứng**. Trace dùng để tìm thành phần tốn thời gian trong những request chậm.

### 6.6. SLO dựa trên ngưỡng thời gian

Ví dụ:

> 99% request `GET /catalog` hợp lệ hoàn thành trong 300 ms trong 28 ngày.

SLI có thể tính là:

[
\mathrm{GoodLatencyRatio} =
\frac{\#\{\text{eligible requests with duration}\leq300\mathrm{ms}\}}
{\#\{\text{eligible requests}\}}
]

Đây là cách định nghĩa "good events" thường có ý nghĩa với trải nghiệm người dùng. Nếu thêm điều kiện request thành công, phải ghi rõ SLI là `successful AND fast` hay SLI availability/latency riêng biệt. Không được gộp ngầm hai định nghĩa.

## 7. Saturation — còn bao nhiêu năng lực trước khi nghẽn?

### 7.1. Saturation là gì?

Saturation đo mức một resource hoặc thành phần xử lý **đang tiến gần giới hạn khả dụng**. CPU 80% có thể là tín hiệu hữu ích, nhưng nhiều bottleneck không phải CPU:

- Thread/worker pool gần đầy.
- DB connection pool hết connection khả dụng.
- HTTP client connection pool đang chờ lease.
- Queue backlog tăng nhanh hơn tốc độ xử lý.
- Event-loop blocked.
- Memory pressure/GC pauses.
- Disk I/O, network bandwidth, kernel file descriptors.
- Container CPU throttling hoặc giới hạn memory.
- Downstream concurrency quota hoặc provider rate limit.

**Không có một "saturation %" chung cho toàn service.** Hãy xác định tài nguyên khan hiếm thực sự và đo utilization, pending work và thời gian chờ.

### 7.2. Utilization khác với queueing

Nếu thread pool có 100 worker và 95 đang bận, utilization là 95%. Tuy nhiên nếu mỗi tác vụ rất ngắn và queue không tăng, hệ thống có thể vẫn đáp ứng SLO. Ngược lại, DB connection pool mới dùng 60% nhưng DB latency tăng do lock contention, hệ thống vẫn gặp bottleneck.

Một số đo hữu ích đi theo cặp:

| Tài nguyên | Đo mức sử dụng | Đo dấu hiệu chờ/thiếu |
| --- | --- | --- |
| Thread pool | Active / max threads | Queue size, rejected tasks |
| DB pool | Active / max connections | Pending threads, acquire latency |
| CPU | CPU utilization/throttling | Run queue, CPU pressure, request latency |
| Memory/GC | Heap used, RSS, GC pressure | Allocation failure, pause time, OOM |
| Message consumer | Active consumers, processing rate | Backlog, lag, oldest message age |
| Disk/network | IOPS/bandwidth used | I/O wait, retransmits, timeouts |
| Remote provider | In-flight calls, quota used | 429, rejected requests, queueing |

**Saturation là khái niệm về năng lực**, không chỉ một chỉ số host. Một service có nhiều memory trống vẫn có thể nghẽn do 20 connection DB đã đầy.

### 7.3. Little's Law — hiểu concurrency tăng theo latency

Trong hệ thống ổn định với tốc độ đến và hoàn thành gần bằng nhau:

[
L = \lambda W
]

Trong đó:

- `L`: số công việc đang nằm trong hệ thống trung bình.
- `λ`: tốc độ hoàn thành trung bình, ví dụ request/giây.
- `W`: thời gian trung bình trong hệ thống, đơn vị giây.

Ví dụ Order phục vụ 300 RPS, thời gian trung bình trong vùng đo 0,2 giây:

[
L = 300 \times 0.2 = 60\text{ request đang hiện diện trung bình}
]

Nếu dependency chậm làm thời gian tăng lên 0,8 giây trong khi tốc độ vẫn 300 RPS, số request đồng thời kỳ vọng tăng lên khoảng **240**. Một pool giới hạn 100 kết nối hoặc 100 worker có thể bắt đầu chờ và reject, dẫn tới queueing/timeout.

Đây là quan hệ trung bình trong điều kiện ổn định; không dùng để dự đoán chính xác đỉnh ngắn hạn, hệ thống có retry, backpressure hoặc tốc độ đến khác tốc độ hoàn thành.

### 7.4. Backlog tăng cho thấy công suất đang hụt

Ví dụ Notification Worker nhận 1.000 message/phút nhưng chỉ xử lý xong 700 message/phút. Nếu xu hướng giữ nguyên, backlog tăng xấp xỉ 300 message/phút.

Số queue depth là một ảnh chụp; **tốc độ thay đổi backlog**, **tuổi message lâu nhất**, **consumer processing rate** và **thời gian xử lý** cho biết mức rủi ro chậm deadline.

Một queue tồn tại 50.000 message không luôn nguy hiểm nếu job xử lý nhanh và còn nhiều thời gian. Một queue chỉ 500 message có thể nghiêm trọng nếu phải hoàn thành trong 10 giây nhưng consumer đang đứng.

### 7.5. Chỉ số đi trước lỗi

Saturation thường tăng **trước** error rate. Ví dụ:

~~~text
Traffic tăng
   ↓
DB pool active tăng
   ↓
Pending requests chờ connection tăng
   ↓
p95/p99 latency tăng
   ↓
Timeout và HTTP 5xx tăng
~~~

Nếu phát hiện từ pending connection và latency, đội vận hành có cơ hội scale, giảm tải hoặc xử lý truy vấn chậm trước khi khách hàng gặp tỷ lệ lỗi lớn.

Tuy nhiên saturation không luôn đi trước lỗi: DNS sai, certificate hết hạn hoặc cấu hình sai có thể gây thất bại tức thì khi tài nguyên còn rất rảnh.

## 8. Liên hệ giữa bốn tín hiệu bằng các kịch bản

| Kịch bản | Traffic | Errors | Latency | Saturation | Giải thích ưu tiên |
| --- | --- | --- | --- | --- | --- |
| Marketing campaign | Tăng | Thấp | Ổn định | Tăng | Nhu cầu tăng trong headroom hiện có |
| DB pool thiếu connection | Có thể ổn định | Có thể tăng sau | Tail tăng | Pending pool tăng | Bottleneck ở connection/DB |
| Payment Provider hỏng | Bình thường | 5xx/timeout tăng | Có thể cao | CPU không nhất thiết cao | Lỗi dependency |
| Retry storm | Downstream attempts tăng | Cao | Cao | Pool/queue căng | Chính retry làm tăng tải |
| Gateway rate limiting | Offered tăng, admitted thấp | 429 tăng | Thành công vẫn nhanh | Downstream được bảo vệ | Nhu cầu vượt chính sách |
| Worker mất kết nối broker | Publish vẫn tăng | Consumer error hoặc delivery fail | Message age tăng | Lag tăng | Bất đồng bộ chậm |
| Cache mất tác dụng | Traffic bên ngoài không đổi | Có thể tăng | DB/client latency tăng | DB QPS/pool tăng | Cache miss làm tải downstream tăng |
| Process restart | Counters reset | Có thể tạo spike tạm thời | Có thể đổi | Replica còn lại chịu thêm tải | Chú ý rate reset và traffic redistribution |

Mỗi hàng là một **giả thuyết chẩn đoán**. Cần dùng thêm log/trace và thông số dependency để xác nhận nguyên nhân, không suy diễn sự cố chỉ từ một hình dạng biểu đồ.

## 9. Chọn loại metric phù hợp

### 9.1. Counter

Counter chỉ tăng trong vòng đời process, thường dùng cho:

- `http_requests_total`
- `dependency_requests_total`
- `retry_attempts_total`
- `processed_messages_total`
- `failed_jobs_total`

Truy vấn `rate` hoặc `increase` trên counter, không lấy giá trị tích lũy làm RPS. Counter có thể reset khi process restart; hệ thống quan sát cần dùng hàm xử lý reset như `rate`.

### 9.2. Histogram / Timer

Histogram ghi phân phối quan sát như:

- HTTP server request duration.
- HTTP client/dependency request duration.
- Queue wait duration.
- DB connection acquire latency.
- Job processing duration.

Micrometer `Timer` thường đo **số lần và tổng thời gian**, đồng thời có thể xuất bucket để tính percentile nếu bật histogram phù hợp. Việc bật histogram cho mọi nhãn/cardinality có thể rất tốn tài nguyên; nên chọn các metric quan trọng và SLO boundary.

### 9.3. Gauge

Gauge phản ánh trạng thái tức thời:

- Active connections.
- In-flight requests.
- Current queue length.
- Consumer lag.
- CPU/memory usage.
- Thread pool active count.

Gauge có thể lên/xuống và có thể mất khi process chết; không dùng `rate(gauge)` để suy ra công việc đã hoàn thành nếu không có ngữ nghĩa tốc độ rõ ràng.

### 9.4. Up/availability của nguồn thu thập

Metric `up=1` thường chỉ có nghĩa Prometheus scrape target thành công. Nó **không chứng minh** user checkout thành công, business response đúng hoặc database khỏe.

Nếu exporter biến mất, dashboard có thể không hiển thị errors mới. Cần một alert riêng cho **mất dữ liệu giám sát** và `absent()`/scrape health phù hợp. Không coi "không thấy lỗi" là "không có lỗi" khi hệ thống thu thập bị ngắt.

## 10. Metric labels: hữu ích và rủi ro cardinality

Một time series có thể được xác định bởi metric name + bộ labels. Ví dụ:

~~~text
http_server_requests_seconds_count{
  job="order-service",
  method="POST",
  uri="/orders/{id}",
  status="201"
}
~~~

**Labels tốt:**

- `service`, `environment`, `region`, `operation`.
- HTTP method và **route template**, ví dụ `/orders/{id}`.
- Status code hoặc status class; result category ổn định.
- Dependency name trong danh sách kiểm soát.
- Queue/topic/consumer group nếu số lượng hữu hạn và đã được cân nhắc.

**Labels nên tránh:**

- `userId`, `email`, `orderId`, `traceId`, `requestId`.
- Đường dẫn chứa ID thực tế như `/orders/987654`.
- Full URL, query string, raw exception message, SQL statement.
- Header tùy ý hoặc token.
- Giá trị tenant/customer không giới hạn nếu chưa có thiết kế số lượng chuỗi và quyền dữ liệu.

Giả sử một metric có 10 services × 10 routes × 5 status × 3 regions × 100.000 users. Chỉ metric đó có thể tạo ra **150 triệu tổ hợp nhãn**; thêm histogram buckets sẽ nhân số time series nữa. Bởi vậy **trace/log chứa ID chi tiết; metric chứa nhãn có tập giá trị hữu hạn**.

**Lưu ý bảo mật:** không đưa dữ liệu cá nhân/secret vào metric label, exemplar hoặc tag dưới bất kỳ dạng raw nào. Truy vết request cụ thể bằng hệ thống trace/log có phân quyền.

## 11. Kiến trúc thu thập số liệu

Một kiến trúc tham khảo:

~~~text
                        ┌──────────────────────────────┐
Client / Synthetic ────►│ Gateway + Edge Measurements  │
                        └──────────────┬───────────────┘
                                       │
     ┌─────────────────────────────────┴─────────────────────────┐
     │                                                           │
     ▼                                                           ▼
Order Service                                              Other Services
  ├─ HTTP server metrics                                    ├─ request metrics
  ├─ HTTP client metrics                                    ├─ dependency metrics
  ├─ JVM / thread / pools                                   └─ runtime resource data
  └─ trace context
     │
     ├────► Inventory / DB metrics
     ├────► Payment / provider metrics
     └────► Message producer / consumer metrics
                         │
                         ▼
           Metrics endpoint / OTLP exporter
                         │
                         ▼
           Collector / Scrape infrastructure
                         │
                         ▼
                  Time-series backend
                         │
                   ┌─────┴──────┐
                   ▼            ▼
                Dashboard   Alert rules
                   │            │
                   └──► Logs / traces for diagnosis
~~~

Các vai trò điển hình:

- **Instrumentation:** HTTP/gRPC middleware, Micrometer, OpenTelemetry, JVM, DB pool, queue client.
- **Collection:** Prometheus scrape, OpenTelemetry Collector hoặc agent tương ứng.
- **Storage/query:** time-series database có retention và query phù hợp.
- **Presentation/alerting:** Grafana/dashboard, rule engine, incident management.
- **Correlation:** log và distributed trace giữ trace/span ID để đi từ dấu hiệu tổng hợp tới request cụ thể.

Metric không thay thế trace/log, nhưng là cửa ngõ phát hiện dịch vụ hoặc operation nào đang thay đổi ở quy mô lớn.

### 11.1. Chọn điểm đo để tránh đếm trùng

Với HTTP request từ client tới Gateway rồi Order:

- Gateway đếm **external request**.
- Order đếm **service inbound request**.
- Order dependency client đếm **outbound attempts**.
- Inventory đếm **service inbound attempts**.

Không cộng các counter này rồi gọi đó là “số request người dùng”. Mỗi metric có ranh giới khác nhau. Khi dashboard toàn hệ thống, chọn **một boundary chuẩn cho từng SLI**, ví dụ Gateway cho end-to-end request hoặc Order cho business transaction.

### 11.2. Truy vết và sampling

Có thể lấy trace của request chậm để chẩn đoán vì sao p99 tăng, nhưng trace thường bị sampling. **Không suy ra RPS/error rate chính xác chỉ từ tập trace được lấy mẫu** trừ khi đã có phương pháp sampling-adjusted đáng tin. Metric counters/histograms từ toàn lưu lượng thường thích hợp hơn cho SLI.

## 12. Ví dụ PromQL cho bốn tín hiệu

Phần này dùng các metric thông dụng từ **Spring Boot + Micrometer + Prometheus registry**. Với nhiều phiên bản Micrometer, HTTP server Timer có tên meter `http.server.requests` và được export thành `http_server_requests_seconds_count`, `_sum` và `_bucket` khi histogram được bật. Tên metric/labels thực tế cần xem tại `/actuator/prometheus` của chính ứng dụng, vì phiên bản, exporter và quy ước có thể khác.

Giả sử `job="order-service"`, `uri` là route template, `status` là HTTP code. Không dùng truy vấn sau như thể là tên metric đảm bảo tồn tại ở mọi stack.

### 12.1. Traffic — RPS theo route

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_count{
    job="order-service",
    uri!~"/actuator.*"
  }[5m])
)
~~~

- `rate(...[5m])` tính tốc độ theo giây của counter trong 5 phút.
- `sum by (uri)` cộng qua instance/pod cho cùng route.
- `uri` nên là route template, không là URL có ID riêng.
- Nếu muốn toàn service, bỏ `by (uri)` và lọc đúng loại request.

Để xem request tăng đột ngột trong 1 phút, có thể dùng `rate(...[1m])` với độ nhiễu lớn hơn. Với traffic thấp, cửa sổ ngắn dễ gây số liệu thiếu ổn định.

### 12.2. Errors — tỷ lệ HTTP 5xx

~~~promql
sum(
  rate(http_server_requests_seconds_count{
    job="order-service",
    status=~"5.."
  }[5m])
)
/
clamp_min(
  sum(
    rate(http_server_requests_seconds_count{
      job="order-service"
    }[5m])
  ),
  1e-9
)
~~~

Truy vấn cho ra tỷ lệ từ 0 đến 1, có thể nhân 100 để hiển thị phần trăm.

**Cảnh báo mẫu số:** `clamp_min` ngăn chia cho 0 nhưng không biến khoảng **không có request** thành tỷ lệ lỗi có ý nghĩa. Rule alert cần xử lý riêng low traffic/absence và bỏ các route khác ngoài phạm vi SLI. Tử và mẫu phải dùng cùng bộ lọc service, route, method và nhóm request đủ điều kiện.

Nếu chính sách xem 429, 499 hoặc business failure là lỗi của một SLI, phải định nghĩa và đo riêng. Query 5xx ở trên chỉ là **server-error ratio**.

### 12.3. Latency — p95 từ histogram

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{
      job="order-service",
      uri!~"/actuator.*"
    }[5m])
  )
)
~~~

- `histogram_quantile(0.95, ...)` **ước tính** p95 từ bucket.
- `le` là nhãn ranh giới bucket; phải giữ `le` khi gộp histogram cổ điển.
- `sum by (le,uri)` kết hợp các instance trước khi tính percentile.
- Kết quả ở đơn vị **giây** đối với histogram `_seconds_bucket`.
- Query chỉ hoạt động nếu histogram bucket được xuất; có `_count` mà không có `_bucket` thì chưa đủ.

Với native histogram của Prometheus/OpenTelemetry, cú pháp/kiểu dữ liệu có thể khác. Không lấy trung bình p95 của từng pod rồi coi là p95 toàn service.

### 12.4. Latency SLI — tỷ lệ hoàn thành không quá ngưỡng

Nếu histogram có bucket `le="0.5"`:

~~~promql
sum(rate(http_server_requests_seconds_bucket{
  job="order-service",
  uri="/checkout",
  le="0.5"
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    job="order-service",
    uri="/checkout"
  }[5m])),
  1e-9
)
~~~

Đây là tỷ lệ request checkout đo được **≤ 0,5 giây** theo bucket; không tự loại request thất bại. Nếu định nghĩa SLI là "thành công trong 0,5 giây", cần thêm nhãn outcome/status hoặc metric được instrument riêng, đảm bảo cả tử/mẫu cùng loại request.

### 12.5. Saturation — connection pool

Nếu HikariCP xuất gauge:

~~~promql
100 *
hikaricp_connections_active{pool="order-db"}
/
clamp_min(
  hikaricp_connections_max{pool="order-db"},
  1
)
~~~

Kết quả là tỷ lệ phần trăm connection active trên max của **một pool**. Khi có nhiều instance, nên quan sát theo pool + instance, không lấy `sum(active)/max(max)` nếu muốn đo sức chứa toàn cụm. Kèm các metric pending connections, acquire timeouts và acquisition latency để phân biệt pool bận hữu ích với pool nghẽn.

**Metric HikariCP có thể có tên/nhãn khác** theo cấu hình Actuator, registry và client. Hãy đối chiếu endpoint export thực tế thay vì suy đoán.

### 12.6. Saturation — queue consumer

Giả sử hệ thống xuất `queue_messages_ready` và `queue_oldest_message_age_seconds`:

~~~promql
queue_messages_ready{queue="notifications"}
~~~

~~~promql
queue_oldest_message_age_seconds{queue="notifications"}
~~~

Tên metric là **ví dụ minh họa cần được instrument hoặc map từ broker exporter**. Không thể suy ra độ trễ xử lý chỉ từ queue length nếu không biết processing rate, concurrency và message age.

## 13. Spring Boot, Micrometer và OpenTelemetry

### 13.1. Tận dụng metrics sẵn có

Trong Spring Boot, Actuator và Micrometer có thể hỗ trợ HTTP server, JVM, system, connection pool và nhiều client libraries. Khi cần Prometheus exporter, app thường có cấu hình registry và endpoint tương ứng.

Ví dụ thuộc tính minh họa:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 100ms,300ms,500ms,1s,2s
~~~

Giải thích:

- Bật endpoint và exporter phải phù hợp phiên bản Spring Boot/Actuator/Micrometer đang dùng.
- `percentiles-histogram` cho phép xuất phân phối thích hợp khi registry hỗ trợ.
- `slo` thêm các bucket tại những ngưỡng latency quan trọng.
- Cần bảo vệ endpoint metrics qua mạng nội bộ, xác thực và cấu hình hạ tầng phù hợp; không công khai mọi metadata theo mặc định.
- Không tùy ý bật histogram cho toàn bộ metric có cardinality lớn.

Cấu hình trên chỉ minh họa cách diễn đạt; nên xác nhận tên meter và bucket tại endpoint thực tế sau triển khai.

### 13.2. Đo một dependency cụ thể bằng Timer

Giả sử Order gọi Inventory qua một client đã cấu hình timeout. Muốn đo duration, outcome và số lần gọi thực tế đến downstream:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class InventoryGateway {
    private final InventoryClient client;
    private final MeterRegistry registry;

    public InventoryGateway(InventoryClient client, MeterRegistry registry) {
        this.client = client;
        this.registry = registry;
    }

    public StockView getStock(String sku) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return client.getStock(sku);
        } catch (RuntimeException ex) {
            outcome = "error";
            throw ex;
        } finally {
            Timer timer = Timer.builder("dependency.client.duration")
                    .description("Latency of Inventory client attempts")
                    .tag("dependency", "inventory")
                    .tag("operation", "get_stock")
                    .tag("outcome", outcome)
                    .publishPercentileHistogram()
                    .register(registry);
            sample.stop(timer);
        }
    }
}
~~~

`InventoryClient` và `StockView` là interface/kiểu nghiệp vụ minh họa. Trong ứng dụng thật, **phân loại error** cần theo hợp đồng: 404 “SKU không có” có thể là outcome dự kiến, 503/timeout cần được xem là lỗi hạ tầng. Một adapter có thể map exception thành enum outcome ổn định trước khi ghi metrics.

**Không đưa `sku`, exception message hoặc URL thật** vào tags. Việc lặp `Timer.builder(...).register(registry)` theo một số tag hữu hạn thường trả về meter đã đăng ký, nhưng với đường hot path nên cân nhắc cache meter/instrument qua registry và instrumentation framework có sẵn.

Khi có HTTP client instrumentation tự động, tránh tạo thêm metric trùng mục đích không rõ ràng. Có thể giữ metric tự động cho HTTP attempt và một metric riêng cho **business operation** nếu hai ranh giới thực sự khác nhau.

### 13.3. Đo số công việc đang xử lý

Một số metric cần **gauge** của số in-flight, ví dụ số request đang gọi Inventory:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicInteger;

public final class InventoryInFlight {
    private final AtomicInteger active = new AtomicInteger();

    public InventoryInFlight(MeterRegistry registry) {
        registry.gauge(
                "inventory.inflight.requests",
                active
        );
    }

    public void begin() {
        active.incrementAndGet();
    }

    public void end() {
        active.decrementAndGet();
    }
}
~~~

Khi instrument thực tế, gọi `begin()` trước lời gọi và `end()` trong `finally`, kể cả exception, cancellation và timeout. Instance giữ tham chiếu `AtomicInteger` trong suốt vòng đời meter; đừng tạo lại một counter cho từng request.

Một gauge chỉ cho biết in-flight hiện tại; cần kết hợp throughput và request duration để hiểu queueing hoặc xác định pool có đang chạm giới hạn không.

### 13.4. Trace context để nối metric với request

Trên nhiều service, dùng W3C Trace Context/OpenTelemetry hoặc cơ chế propagation tương ứng. Một request có `traceId` xuyên suốt giúp mở trace chậm khi dashboard báo latency tăng.

Tuy nhiên `traceId` **không phải metric label**. Nếu backend hỗ trợ **exemplar**, có thể liên kết một số mẫu histogram với trace được chọn trong phạm vi an toàn. Điều này cho phép người vận hành mở trace từ histogram mà không tạo một time series cho mỗi request.

### 13.5. Metric semantics và versioning

Các semantic convention của OpenTelemetry/Micrometer có thể thay đổi theo version. Ví dụ metric HTTP có thể dùng tên/đơn vị/attributes khác nhau tùy phiên bản. Khi nâng version cần kiểm tra:

- Tên metric cũ và mới.
- Label `uri` hay `http.route`, `status` hay `http.response.status_code`.
- Histogram classic/native và bucket boundaries.
- Đơn vị giây, mili giây hoặc byte.
- Bộ lọc route internal/health.
- Dashboard, recording rule và alert có còn nhận dữ liệu không.

Nên có dashboard provisioning hoặc smoke test về **sự tồn tại và ngữ nghĩa metric** sau deployment để tránh tình trạng service khỏe nhưng biểu đồ trống.

## 14. Thiết kế SLI/SLO cho microservices

### 14.1. Từ nhu cầu người dùng tới SLI

Không chọn SLO chỉ vì một metric sẵn có. Hãy bắt đầu từ user journey.

Ví dụ một nền tảng đặt hàng:

| User journey | Định nghĩa SLI | Ranh giới đo |
| --- | --- | --- |
| Xem catalog | Tỷ lệ GET trả dữ liệu hợp lệ trong 300 ms | Gateway hoặc client |
| Đặt hàng | Tỷ lệ checkout hợp lệ được xác nhận trong 2 giây | Gateway + business outcome |
| Gửi email xác nhận | Tỷ lệ job được gửi trong 60 giây | Worker completion + enqueue time |
| Tra cứu đơn | Tỷ lệ đọc đơn thành công trong 500 ms | Edge/API operation |

Một operation có thể có **availability SLO** và **latency SLO** riêng. Error budget và hành động vận hành cần dựa trên chính SLI đó, thay vì một tỷ lệ 5xx tổng hợp không liên quan.

### 14.2. Định nghĩa numerator/denominator

Ví dụ SLI checkout:

~~~text
Eligible:
  - request POST /checkout hợp lệ đã đến ranh giới được đo
Good:
  - nghiệp vụ checkout thành công
  - hoàn thành trước deadline 2 giây
Bad:
  - request đủ điều kiện nhưng timeout, 5xx,
    kết quả nghiệp vụ thất bại do hệ thống
Excluded theo hợp đồng:
  - request test/synthetic được phân loại riêng
  - validation failure do input sai đã xác định rõ
~~~

Nếu policy chọn không loại một số trường hợp, cần ghi lại rõ. SLI phải có thể truy vấn từ dữ liệu thực tế chứ không chỉ nằm trong tài liệu.

### 14.3. Error-budget burn alert

Ví dụ SLO 99,9% trên 30 ngày, nghĩa là budget fraction 0,1%. Nếu cửa sổ gần đây có bad event ratio 1%, burn rate:

[
\mathrm{BurnRate} = \frac{1\%}{0.1\%} = 10
]

Điều này cho thấy tốc độ tiêu ngân sách gấp 10 lần mức cho phép trung bình. Alert đáng tin nên dùng **nhiều cửa sổ** để xác nhận vừa có ảnh hưởng đáng kể trong khoảng dài, vừa đang xảy ra ở khoảng ngắn.

Gợi ý cách suy nghĩ:

- **Nhanh và nặng:** tỷ lệ bad events cao trong vài phút, có khách hàng bị ảnh hưởng; cần phản ứng kịp.
- **Chậm và kéo dài:** tỷ lệ bad events thấp hơn nhưng liên tục nhiều giờ; có thể tiêu ngân sách đáng kể.
- **Traffic rất thấp:** 1 request lỗi có thể tạo tỷ lệ 100%; cần xem số lượng mẫu và tác động, tránh paging vô ích.

Không tự lấy một ngưỡng burn rate làm tiêu chuẩn chung nếu SLO window và severity khác nhau.

## 15. Dashboard vận hành: xem điều gì trước?

Một dashboard cho một service có thể chia thành:

**Hàng A — người dùng cảm nhận:**

- External RPS theo user journey.
- Request success/bad ratio và số bad requests.
- p50/p95/p99 end-to-end latency.
- Good events ratio so với SLO; error-budget trend.

**Hàng B — service đang hoạt động:**

- Inbound requests theo route/method/status class.
- Outbound dependency latency/error/attempt rate.
- In-flight requests, rejected/throttled requests, retries, circuit-breaker states.
- Deploy/feature flag annotations để đối chiếu thời điểm thay đổi.

**Hàng C — năng lực xử lý:**

- CPU và throttling, memory/GC.
- Thread pool active/queue/rejection.
- DB active/pending/acquire timeouts.
- Broker publish/consume rates, consumer lag, oldest message age.

**Hàng D — chẩn đoán:**

- Danh sách service/dependency có lỗi tăng.
- Link tới trace chậm/lỗi và log có correlation ID.
- Sự kiện deployment, autoscaling, lỗi external provider.

Một dashboard toàn hệ thống nên gợi mở đường đi từ edge SLO tới service và dependency. **Không xếp hàng chục đồ thị CPU vào trang đầu** nếu câu hỏi vận hành ưu tiên là khách hàng có dùng được chức năng chính hay không.

### 15.1. Chọn phép tổng hợp đúng

| Metric | Khi gộp nhiều replica | Sai lầm thường gặp |
| --- | --- | --- |
| RPS | `sum(rate(counter))` | Lấy trung bình RPS từng pod rồi gọi tổng traffic |
| Failure ratio | Sum failed / sum eligible | Trung bình error ratio của pod nhiều tải và pod ít tải |
| Histogram latency | Sum bucket rates rồi `histogram_quantile` | Trung bình p95 của từng pod |
| CPU utilization | Xem theo pod, max/top và weighted tùy mục đích | Chỉ xem average toàn cụm che pod nóng |
| DB pool saturation | Theo pool/instance, xem max hoặc phân bố | Cộng active nhưng lấy max của một pool |
| Queue lag | Theo queue/partition/group thích hợp | Gộp mất partition bị đứng |
| Restarts | Counter increase theo replica | Hiểu counter reset là giá trị giảm bình thường |

Các quyết định này ảnh hưởng trực tiếp tới việc dashboard **có phản ánh sự cố cục bộ** hay không.

## 16. Cảnh báo: hành động được chứ không chỉ thấy số đỏ

Mỗi alert nên trả lời:

1. **Điều gì đang sai?** SLI bị ảnh hưởng, dependency lỗi, saturation sắp chạm giới hạn.
2. **Ai bị ảnh hưởng?** User journey, service, region, tenant class theo phạm vi được phép.
3. **Nghiêm trọng đến đâu?** Error budget, bad requests, traffic và thời gian ảnh hưởng.
4. **Người trực nên kiểm tra gì trước?** Dashboard, trace/log link, dependency, recent deploy.
5. **Có điều kiện tự phục hồi hoặc giảm tải không?** Rate limit, scale, rollback, restart khi phù hợp.

Ví dụ nhóm alert:

| Tên | Tín hiệu | Mức ưu tiên gợi ý |
| --- | --- | --- |
| Checkout SLO burn cao | Bad event ratio vượt budget tốc độ cao ở nhiều cửa sổ | Cảnh báo trực |
| Checkout p99 latency cao kéo dài | Tail latency ảnh hưởng người dùng | Phụ thuộc traffic/SLO |
| Payment dependency 5xx tăng | Downstream attempt errors | Phân tích cùng user impact |
| DB pool pending liên tục | Saturation + waiting | Điều tra bottleneck sớm |
| Queue oldest age vượt deadline | Async job chậm | Có thể page nếu nghiệp vụ yêu cầu |
| Scrape/ingest mất dữ liệu | Monitoring không đáng tin | Cảnh báo riêng về observability |

**Không page chỉ vì CPU 80% trong 2 phút** nếu đó là trạng thái bình thường và không có hành động rõ. Nhưng cũng không đợi error rate tăng mới cảnh báo nếu queue age vượt deadline nghiệp vụ.

### 16.1. Low traffic và missing data

Rất dễ nhầm:

- **0 errors / 0 requests** không cho ra tỷ lệ lỗi có ý nghĩa.
- Không có sample do exporter chết khác với counter có giá trị 0.
- 1 lỗi/1 request = 100%, nhưng tác động tuyệt đối có thể nhỏ.
- SLO dài hạn vẫn có thể bị ảnh hưởng dù cửa sổ ngắn ít mẫu.

Alert cần xử lý tổng số eligible events, yêu cầu dữ liệu đầy đủ, ngưỡng SLO, và cơ chế absence detection phù hợp. Không tự động gán `missing` thành `success`.

## 17. Chẩn đoán sự cố qua bốn tín hiệu

### 17.1. Tình huống A: traffic tăng và CPU bão hòa

**Quan sát:**

- Traffic Order từ 200 lên 900 RPS.
- CPU usage và throttling tăng.
- p95 latency tăng từ 150 ms lên 1,2 giây.
- 5xx tăng sau một vài phút.

**Diễn giải:** một khả năng là capacity thiếu; cần xác nhận CPU có thực sự là bottleneck hay chỉ tăng theo tải.

**Bước tiếp theo:** xem HPA/replica count, CPU limit/throttling, request queue, profile CPU, endpoint nặng, scaling delay và rate limit. Scale có thể giảm áp lực nếu bottleneck ở CPU cục bộ; sẽ không giúp nếu bottleneck thực nằm ở DB chung.

### 17.2. Tình huống B: traffic ổn định, latency tăng, CPU thấp

**Quan sát:** RPS không đổi; p99 checkout tăng gấp 8; CPU các pod Order thấp; DB pool pending tăng.

**Diễn giải:** request đang chờ tài nguyên hoặc network/dependency. CPU thấp không chứng minh service rảnh.

**Bước tiếp theo:** dùng trace kiểm tra span ở DB acquire/query hoặc Payment client; xem DB lock contention, slow query, pool configuration, retry và timeout.

### 17.3. Tình huống C: errors tăng ngay, saturation thấp

**Quan sát:** sau deployment, 403 hoặc 500 tăng; CPU 20%, memory ổn; latency ngắn.

**Diễn giải:** có thể lỗi auth policy, token audience, certificate, route hoặc cấu hình, không phải hết capacity.

**Bước tiếp theo:** so sánh config, deploy time, exception classes, logs và trace. Phân biệt 403 do policy hợp lệ với 403 làm hỏng luồng người dùng. Rollback theo quy trình nếu bản deploy gây regression.

### 17.4. Tình huống D: HTTP 200 ổn nhưng nghiệp vụ bị suy giảm

**Quan sát:** 5xx≈0; checkout trả 200; fallback cache tăng, inventory reservation không được xác nhận.

**Diễn giải:** technical availability chưa phản ánh business correctness.

**Bước tiếp theo:** kiểm tra business outcome, degraded response metric và các dependency đang OPEN; sửa SLI để đếm kết quả mà người dùng thực sự cần.

### 17.5. Tình huống E: queue lag tăng trong khi API khỏe

**Quan sát:** API nhận 202 nhanh, không có 5xx. Notification worker xử lý chậm; message age vượt 10 phút.

**Diễn giải:** công việc bất đồng bộ chưa hoàn tất, không hiện trên latency HTTP ban đầu.

**Bước tiếp theo:** xem publish/consume rates, consumer lag theo partition, worker concurrency, retry/DLQ, broker health, processing duration và deadline nghiệp vụ. SLI cần đo **enqueue-to-completion**.

### 17.6. Tình huống F: p95 đẹp nhưng p99 xấu

**Quan sát:** p95=180 ms, p99=5 giây; chỉ vài request bị kẹt.

**Diễn giải:** có thể hot partition, GC pause, thỉnh thoảng hết DB connection, background task hoặc dependency tail.

**Bước tiếp theo:** xem histogram bucket, max wait, trace của request chậm, percentile theo route và instance. Không tăng toàn bộ timeout chỉ để giảm số lỗi; timeout dài hơn có thể làm giữ tài nguyên lâu hơn.

## 18. Phương pháp tìm bottleneck có hệ thống

Khi người dùng báo "dịch vụ chậm", có thể đi theo chuỗi:

**Bước 1 — xác nhận ảnh hưởng:** thời gian bắt đầu, user journey, region, request count, tỷ lệ bad events và SLO.

**Bước 2 — chọn boundary:** edge latency tăng hay chỉ một service? Nếu edge khỏe nhưng worker chậm, kiểm tra async workflow.

**Bước 3 — đọc traffic:** có spike, thay đổi traffic mix, retry, crawler hay batch? Đừng chỉ xem tổng RPS; một route nặng có thể tăng dù tổng không đổi.

**Bước 4 — đọc errors:** lỗi gì, ở ranh giới nào, số lượng bao nhiêu, có fallback hay partial success không? Phân biệt client/business/system failures.

**Bước 5 — đọc latency:** p50/p95/p99 tăng? Có timeout? Theo route, dependency và instance nào? Dùng trace để định vị span chậm.

**Bước 6 — đọc saturation:** tài nguyên nào gần giới hạn? Xem queue/pending/concurrency cạnh utilization. CPU thấp không loại trừ DB/IO saturation.

**Bước 7 — đối chiếu thời điểm:** recent deploy, schema migration, autoscaling, dependency outage, configuration change, tăng tỷ lệ cache miss.

**Bước 8 — can thiệp có điều kiện:** scale, giảm burst, bật backpressure, rollback, giảm retry, sửa query hoặc khôi phục dependency theo bằng chứng. Sau thay đổi, kiểm tra bốn tín hiệu và SLO để xác nhận hiệu quả.

Đừng sửa nhiều thứ cùng lúc nếu cần xác định nguyên nhân; thay đổi có thể khó truy vết và che tác động của nhau.

## 19. Thiết kế thực nghiệm để hiểu bốn tín hiệu

Một môi trường thử nghiệm có:

- Gateway nhận request.
- Order Service gọi Inventory Service.
- Inventory có chế độ bình thường, thêm độ trễ và trả lỗi có kiểm soát.
- Prometheus/Grafana hoặc hệ thống metrics tương đương.
- Trace với trace ID xuyên hai service.
- Công cụ tạo tải có giới hạn (ví dụ k6, Gatling hoặc công cụ tương tự).

### 19.1. Kịch bản thử nghiệm

| Pha | Điều chỉnh | Dự kiến quan sát |
| --- | --- | --- |
| Baseline | 50 RPS, Inventory 50 ms, 0% lỗi | Traffic ổn; errors thấp; p95 ổn; pool còn dư |
| Traffic burst | Tăng lên 200 RPS trong thời gian ngắn | Inbound RPS tăng; saturation thay đổi theo capacity |
| Slow dependency | Inventory thêm 1,5 giây vào 20% request | p95/p99 tăng; in-flight/pending có thể tăng |
| Error injection | Inventory trả 503 ở 10% request | 5xx/dependency failure ratio tăng |
| Retry enabled | Retry có giới hạn cho lỗi phù hợp | Downstream attempt traffic tăng; cần quan sát load |
| Pool constrained | Giảm connection/thread pool trong môi trường test | Pending queue, acquire latency hoặc rejected tăng |
| Recovery | Đưa latency/lỗi về baseline | Errors/latency giảm, backlog được xử lý dần |

**Điều cần kiểm tra:** Dashboard phải phản ánh thay đổi theo đúng boundary. Khi thêm 503, phải thấy failed calls ở Inventory hoặc Order client; nếu client che 503 thành success, metric cần nhận ra điều đó ở tầng nghiệp vụ.

### 19.2. Một bộ kết quả minh họa

Giả sử môi trường test có ba mốc:

| Metric | Baseline | Inventory chậm | Inventory hỏng |
| --- | ---: | ---: | ---: |
| External RPS | 100 | 100 | 100 |
| Checkout 5xx ratio | 0,1% | 2% | 35% |
| Checkout p95 | 220 ms | 1.800 ms | 2.000 ms |
| Order CPU | 30% | 28% | 25% |
| Inventory client in-flight | 12 | 85 | 90 |
| DB pool pending | 0 | 22 | 0 |

Số liệu giả định minh họa rằng **latency và in-flight có thể tăng khi CPU không tăng**. Ở giai đoạn hỏng, lỗi có thể đến rất nhanh hoặc timeout tùy fault injection; vì vậy latency không luôn chuyển động cùng error rate.

### 19.3. Kiểm tra chất lượng instrumentation

Không chỉ mở dashboard rồi kết luận. Cần xác nhận về mặt kỹ thuật:

- Counter tăng theo số attempt thực, không đếm trùng do proxy/retry.
- Histogram có bucket đáp ứng mốc SLO và đúng đơn vị.
- Metric outcome phân biệt success/failure/timeout/rejected khi cần.
- Route label dùng template; không có user/request ID.
- Counter reset sau restart vẫn không tạo spike giả trong `rate`.
- Khi service bị kill hoặc endpoint metrics không truy cập được, xuất hiện cảnh báo về missing telemetry.
- Queue message age và lag được đo ở đúng consumer group/partition.
- Dashboard gộp across replicas theo đúng phép toán.
- Kết quả event-level có thể được xác minh bằng test client/log/trace trong phạm vi cần thiết.

Đây là **kiểm tra quan sát hệ thống** trong ứng dụng minh họa, khác với việc suy luận chỉ từ một đường biểu đồ.

## 20. Anti-patterns dễ mắc trong microservices

**1. Chỉ đo CPU/memory.** Một service có CPU thấp vẫn chậm vì DB connection, network hoặc thread chờ.

**2. Chỉ đo p50 hoặc average latency.** Hành vi đuôi phân phối có thể ảnh hưởng nhóm người dùng dù giá trị trung bình đẹp.

**3. Dùng p95 từng pod rồi lấy average.** Percentile không cộng/trung bình được theo cách đó; phải aggregate distribution hoặc đo ở ranh giới chung.

**4. Chỉ ghi latency của request thành công.** Timeout chậm bị bỏ khỏi mẫu, làm dashboard có vẻ nhanh hơn khi hệ thống đang hỏng.

**5. Cộng tất cả request counters của Gateway và services.** Một request user tạo nhiều service calls, làm traffic bị nhân lên.

**6. Không phân biệt attempt và operation.** Retry có thể làm downstream failure ratio cao trong khi user-facing success khác.

**7. Coi 200 là thành công tuyệt đối.** Fallback và kết quả nghiệp vụ sai vẫn làm người dùng không đạt mục đích.

**8. Coi 404/429 luôn là lỗi hệ thống hoặc luôn vô hại.** Ý nghĩa phụ thuộc hợp đồng API và SLI.

**9. Gắn `userId`, `orderId`, `traceId` vào metric label.** Gây cardinality explosion và có thể rò dữ liệu.

**10. Dùng một cửa sổ rate rất ngắn cho service ít traffic.** Một request lỗi làm tỷ lệ dao động cực lớn và tạo alert nhiễu.

**11. Dùng một ngưỡng saturation chung cho CPU, connection, queue.** Các nguồn tài nguyên có ý nghĩa và đặc tính giới hạn khác nhau.

**12. Quên monitoring của monitoring.** Scrape target mất nhưng dashboard hiển thị trống hoặc stale; không thể kết luận hệ thống khỏe.

**13. Không tách latency chờ queue và latency xử lý.** Queue chậm có thể bị bỏ ngoài vùng đo service handler.

**14. Không phân biệt offered và admitted traffic.** Load bị rate limit có thể làm downstream vẫn ổn nhưng người dùng chịu lỗi.

**15. Không xem metric theo operation hoặc dependency.** Một route nặng làm toàn service p99 xấu; muốn xử lý đúng phải biết route nào.

**16. Tăng timeout để che tail latency.** Timeout dài hơn có thể làm saturation tăng và đẩy sự cố xuống downstream.

**17. Dùng trace lấy mẫu làm nguồn sự thật của error ratio.** Sampling có thể thiếu các request quan trọng.

**18. Không gắn dashboard với SLO và hành động vận hành.** Đồ thị đẹp nhưng không trả lời khi nào phải phản ứng hoặc mức ảnh hưởng thực tế.

## 21. Bài tập thực hành

### Bài 1 — Tính traffic và failure ratio

Trong 5 phút, Gateway nhận 120.000 checkout requests. Có 100.000 request hợp lệ đi vào Order; 1.000 request hợp lệ thất bại do lỗi hệ thống; 19.000 request bị chặn vì dữ liệu nhập không hợp lệ.

**Câu hỏi:** external RPS là bao nhiêu? Error ratio của tập request hợp lệ là bao nhiêu? Có nên tính 19.000 validation failures là SLO bad requests không?

**Gợi ý:**

- External RPS = 120.000 / 300 = **400 RPS**.
- Failure ratio trong tập hợp lệ = 1.000 / 100.000 = **1%**.
- Quyết định đưa validation failure vào mẫu số/tử phụ thuộc **SLI đã định nghĩa**, không tự động loại hoặc tính vào lỗi hệ thống.

### Bài 2 — Vì sao average latency đánh lừa?

Trong 100 request, có 95 request mất 100 ms và 5 request mất 5.000 ms. Hãy tính average và giải thích vì sao người dùng vẫn có thể phàn nàn dù average chỉ vài trăm ms.

**Hướng giải:** Average **345 ms**, nhưng một nhóm 5% phải chờ khoảng 5 giây. Cần xem histogram/tail percentile và ngữ cảnh operation.

### Bài 3 — Suy luận saturation bằng Little's Law

Một service xử lý 400 RPS với mean latency 250 ms. Nếu latency tăng thành 1 giây nhưng throughput vẫn duy trì 400 RPS, số request đồng thời trung bình biến đổi thế nào?

**Hướng giải:** Ban đầu `L=400×0,25=100`; sau đó `L=400×1=400`. Nếu pool chỉ chịu được 150 request đồng thời, hệ thống có nguy cơ queueing/rejection. Phải đánh giá điều kiện ổn định, backpressure và tài nguyên thực.

### Bài 4 — Đếm retry attempts

Một request thanh toán phát 3 downstream attempts: lần đầu timeout, lần hai HTTP 503, lần ba thành công. Hãy mô tả user-facing availability, dependency error ratio và tổng attempt count.

**Hướng giải:** Tùy deadline/idempotency, operation cuối có thể thành công hoặc quá hạn. Downstream có **3 attempts và 2 errors**; không thể suy ra user success chỉ từ attempt metrics.

### Bài 5 — Dashboard queue

Producer đưa 800 message/phút, consumer hoàn thành 500 message/phút; backlog ban đầu 5.000. Sau 10 phút, dự đoán backlog nếu các tốc độ không đổi và không có drop/retry.

**Hướng giải:** Backlog tăng `(800−500)×10=3.000`, thành **8.000 messages**. Cần xem thêm oldest message age và deadline; queue length đơn độc chưa đủ định nghĩa mức nghiêm trọng.

### Bài 6 — Viết rule vận hành

Một hệ thống có checkout SLO 99,9% trong 30 ngày. Thiết kế alert khi burn rate cao kéo dài, và một cảnh báo sớm khi DB pool pending tăng mà chưa phát sinh 5xx.

**Gợi ý:** Alert thứ nhất phải dựa trên bad event ratio của đúng checkout SLI, window dài/ngắn và số request tối thiểu. Alert thứ hai dùng pool pending/acquire latency kết hợp p95/p99, không chỉ CPU. Mỗi alert cần owner và playbook kiểm tra.

## 22. Checklist trước khi triển khai quan sát production

### Định nghĩa và instrument

- [ ] Có danh sách user journey quan trọng và boundary đo từ góc nhìn người dùng.
- [ ] Traffic đếm theo đơn vị công việc rõ: request, attempt, job, message.
- [ ] Có offered/admitted/completed/rejected khi hệ thống cần phân biệt.
- [ ] Error ratio có tử/mẫu nhất quán; phân biệt technical, business, throttling và degraded.
- [ ] Latency đo cả success, timeout và failure theo chính sách; có p95/p99 và histogram bucket phù hợp SLO.
- [ ] Có saturation của tài nguyên thực: pool, queue, CPU/throttle, concurrency, memory/GC, broker lag.
- [ ] Tách service inbound và downstream outbound attempts.
- [ ] Labels có cardinality kiểm soát; không chứa credential hoặc identifier riêng từng request.

### Dashboard và alert

- [ ] Dashboard thể hiện bốn tín hiệu trên cùng time range, theo service/operation/region.
- [ ] Query aggregate nhiều replica đúng: sum rate, weighted error ratio, aggregate histogram.
- [ ] SLI/SLO có định nghĩa good, bad, eligible, window và owner.
- [ ] Error-budget burn alert phản ánh user impact, có low-traffic handling.
- [ ] Có alert riêng khi metrics pipeline/scrape target không hoạt động.
- [ ] Link sang trace/log và deployment annotations để điều tra nguyên nhân.
- [ ] Có runbook cho dependency failure, queue lag và saturation.

### Kiểm chứng

- [ ] Đã chạy baseline, traffic burst, error injection và slow dependency trong môi trường kiểm thử.
- [ ] Kiểm tra counter reset, histogram buckets, metric names sau restart/upgrade.
- [ ] Kiểm tra số request bị chặn, retry, fallback không bị gộp vào thành công giả.
- [ ] Kiểm tra dashboard không che replica/partition nóng.
- [ ] Có theo dõi chi phí/cardinality, retention và quyền truy cập telemetry.

## 23. Ghi nhớ

Bốn tín hiệu **Traffic – Errors – Latency – Saturation** tạo khung quan sát thực dụng cho microservices:

- **Traffic** cho biết nhu cầu đến và tốc độ công việc được phục vụ.
- **Errors** cho biết mức công việc không đạt kết quả yêu cầu; cần định nghĩa đúng denominator, lỗi kỹ thuật và lỗi nghiệp vụ.
- **Latency** cho biết thời gian xử lý và trải nghiệm, đặc biệt ở phần đuôi p95/p99; phải đo tại đúng boundary và có histogram phù hợp.
- **Saturation** cho biết tài nguyên hoặc năng lực xử lý đang bị dùng tới mức nào; cần nhìn cả utilization, hàng đợi và thời gian chờ.

Khi ghép bốn tín hiệu theo cùng user journey, kết hợp SLI/SLO/error budget và truy nguyên bằng trace/log, người vận hành có thể phân biệt **nhu cầu tăng, phụ thuộc hỏng, xử lý chậm và cạn năng lực**, rồi xác nhận biện pháp khắc phục bằng số liệu thực.
