# Theo dõi lỗi, độ trễ và tín hiệu nghiệp vụ sau thay đổi

Một lần triển khai hoàn tất về mặt kỹ thuật chưa có nghĩa hệ thống đang hoạt động tốt. Lệnh deploy có thể trả về thành công, pod có thể ở trạng thái Ready và endpoint health có thể trả HTTP 200, nhưng người dùng vẫn gặp lỗi thanh toán, thời gian phản hồi tăng hoặc đơn hàng không được ghi nhận. Vì vậy, CI/CD cần có bước kiểm chứng sau triển khai dựa trên dữ liệu thực tế của hệ thống.

Kiểm chứng sau triển khai (post-deployment validation) là quá trình quan sát ứng dụng sau khi thay đổi được đưa vào môi trường, đối chiếu các tín hiệu vận hành và nghiệp vụ với trạng thái trước đó hoặc nhóm đối chứng, rồi quyết định tiếp tục rollout, tạm dừng, rollback hay yêu cầu người vận hành điều tra.

Bài học này tập trung vào ba nhóm tín hiệu quan trọng: **lỗi, độ trễ và kết quả nghiệp vụ**. Các tín hiệu cần được liên kết với phiên bản, artifact digest, cấu hình và thời điểm triển khai để nhóm biết thay đổi nào có thể gây ra tác động. Mục tiêu là phát hiện sớm ảnh hưởng đến người dùng, xác định phạm vi và đưa ra quyết định phát hành dựa trên bằng chứng.

## 1. Vì sao cần kiểm chứng sau triển khai?

Kiểm thử trong CI thường chạy trên dữ liệu và môi trường có kiểm soát. Staging giúp kiểm tra gần với production, nhưng không thể mô phỏng đầy đủ lưu lượng, dữ liệu, hành vi người dùng và các phụ thuộc thực tế. Một thay đổi chỉ bộc lộ vấn đề khi có traffic thật hoặc khi kết hợp với cấu hình, dữ liệu và phiên bản dịch vụ khác.

Một số tình huống thường gặp:

- API vẫn trả phản hồi nhưng tỷ lệ HTTP 5xx tăng ở một nhóm request.
- Thời gian phản hồi trung bình gần như không đổi, nhưng p95 hoặc p99 tăng mạnh.
- Health check thành công nhưng luồng tạo đơn hàng thất bại do một dependency.
- Consumer vẫn chạy nhưng queue lag tăng liên tục.
- Bản phát hành mới xử lý request thành công nhưng ghi nhận sai trạng thái nghiệp vụ.
- Một vùng hoặc một nhóm tenant bị ảnh hưởng trong khi số liệu tổng thể vẫn bình thường.
- Tỷ lệ lỗi chỉ tăng sau vài phút do connection pool cạn hoặc bộ nhớ tăng dần.

Vì vậy, kiểm chứng cần nhìn cả trạng thái kỹ thuật lẫn kết quả người dùng nhận được. Một lần triển khai chỉ nên được xem là ổn định khi các tín hiệu quan trọng nằm trong ngưỡng chấp nhận trong khoảng quan sát phù hợp.

~~~mermaid
flowchart TD
    A["Triển khai artifact mới"] --> B["Gắn release marker và metadata"]
    B --> C["Kiểm tra readiness / smoke test"]
    C --> D["Quan sát lỗi và độ trễ"]
    D --> E["Quan sát saturation và dependency"]
    E --> F["Quan sát tín hiệu nghiệp vụ"]
    F --> G{"Các tín hiệu đạt chính sách?"}
    G -- "Đạt" --> H["Tiếp tục rollout / xác nhận release"]
    G -- "Chưa rõ" --> I["Giữ tỷ lệ traffic và điều tra"]
    G -- "Vi phạm ngưỡng" --> J["Dừng rollout / rollback theo policy"]
    I --> D
~~~

Kiểm chứng sau triển khai không thay thế monitoring liên tục. Nó là giai đoạn tăng cường quan sát quanh một thay đổi cụ thể, nơi nhóm cần liên kết tín hiệu với release và có quyết định rõ ràng.

## 2. Xác định tín hiệu cần theo dõi

Không nên theo dõi mọi metric có sẵn với mức ưu tiên như nhau. Trước khi triển khai, hãy xác định mục tiêu thay đổi và những tín hiệu có thể phản ánh tác động của nó.

Có thể bắt đầu bằng bốn nhóm tín hiệu vận hành thường gọi là golden signals:

| Nhóm | Câu hỏi | Ví dụ |
|---|---|---|
| Traffic | Hệ thống đang nhận bao nhiêu yêu cầu? | Request/second, số job, số kết nối |
| Errors | Bao nhiêu yêu cầu thất bại? | HTTP 5xx, exception, timeout, job retry |
| Latency | Người dùng phải chờ bao lâu? | p50, p95, p99, thời gian xử lý job |
| Saturation | Tài nguyên hoặc dependency còn dư địa không? | CPU, memory, thread pool, connection pool, queue lag |

Với dịch vụ có quy trình nghiệp vụ, cần bổ sung **business signals**:

- Tỷ lệ checkout hoặc thanh toán thành công.
- Số đơn hàng được tạo, xác nhận hoặc hoàn tất.
- Tỷ lệ giao dịch bị từ chối ngoài dự kiến.
- Số bản ghi được xử lý và số bản ghi bị loại.
- Tỷ lệ đồng bộ dữ liệu thành công.
- Thời gian từ lúc nhận sự kiện đến lúc hoàn tất nghiệp vụ.
- Số tác vụ tồn đọng hoặc bị dead-letter.

Mỗi thay đổi nên có một tập tín hiệu chính và một số tín hiệu bảo vệ. Ví dụ, thay đổi API thanh toán cần theo dõi tỷ lệ lỗi API, p95 latency, tỷ lệ thanh toán thành công, timeout từ nhà cung cấp và số giao dịch pending. Chỉ theo dõi CPU và HTTP 200 sẽ không đủ.

## 3. Theo dõi lỗi và tỷ lệ lỗi

Số lượng lỗi tuyệt đối không cho biết đầy đủ mức độ ảnh hưởng. Mười lỗi trong mười triệu request có ý nghĩa khác với mười lỗi trong một trăm request. Vì vậy, nên xem cả số lỗi, tỷ lệ lỗi, lưu lượng và nhóm người dùng bị ảnh hưởng.

### 3.1. Phân loại lỗi theo nguồn

Có thể phân loại:

- **Lỗi ứng dụng:** exception không được xử lý, lỗi validation, lỗi logic hoặc lỗi serialize.
- **Lỗi phụ thuộc:** database timeout, cache unavailable, API bên ngoài trả lỗi.
- **Lỗi hạ tầng:** pod restart, thiếu tài nguyên, network failure hoặc DNS.
- **Lỗi nghiệp vụ:** giao dịch bị từ chối, trạng thái không hợp lệ hoặc quy tắc xử lý sai.
- **Lỗi do client:** request không hợp lệ, người dùng hủy hoặc client gửi lại request.

Không phải mọi HTTP 4xx đều là lỗi của bản phát hành. Ví dụ, 401 hoặc 404 có thể là hành vi bình thường. Cần xác định loại lỗi nào phản ánh sự suy giảm dịch vụ và loại nào là kết quả mong đợi.

### 3.2. Tính tỷ lệ lỗi với mẫu số phù hợp

Tỷ lệ lỗi thường được tính:

\[
\text{Error rate} =
\frac{\text{Số request thất bại}}
{\text{Tổng request được đánh giá}}
\times 100\%
\]

Mẫu số phải nhất quán. Nếu chỉ tính request đã hoàn tất, timeout ở tầng gateway có thể bị bỏ sót. Nếu metric đếm retry nhiều lần, cần phân biệt request gốc với lần thử lại để tránh làm sai tỷ lệ.

Ví dụ PromQL minh họa cho tỷ lệ HTTP 5xx:

~~~promql
sum(rate(http_requests_total{status=~"5.."}[5m]))
/
sum(rate(http_requests_total[5m]))
~~~

Tên metric và label phụ thuộc hệ thống instrumentation. Cần lọc đúng service, route hoặc release khi so sánh. Với canary, nên tính riêng nhóm phiên bản mới và nhóm control.

### 3.3. Phân biệt lỗi tăng do traffic và lỗi tăng do chất lượng

Nếu số request tăng gấp đôi, số lỗi tuyệt đối có thể tăng dù tỷ lệ lỗi không đổi. Ngược lại, một nhóm request nhỏ có thể có tỷ lệ lỗi cao nhưng bị che bởi lưu lượng tổng lớn.

Nên xem đồng thời:

- Số request và số lỗi.
- Tỷ lệ lỗi theo service, route, region và release.
- Phân bố lỗi theo loại exception hoặc dependency.
- Số người dùng hoặc tenant bị ảnh hưởng nếu có thể đo an toàn.
- Thời điểm bắt đầu tăng lỗi so với release marker.

Không tạo metric label từ user ID, email hoặc dữ liệu có cardinality rất cao. Nếu cần điều tra theo người dùng, hãy dùng log/tracing có kiểm soát truy cập và định danh đã được giảm nhạy cảm.

## 4. Theo dõi độ trễ bằng percentile

Độ trễ trung bình có thể che giấu trải nghiệm tệ của một nhóm request. Ví dụ, phần lớn request hoàn thành trong 100 ms nhưng một số request mất 8 giây. Average có thể vẫn trông tốt trong khi người dùng gặp timeout.

Nên theo dõi percentile:

- **p50:** độ trễ ở trung vị, phản ánh trải nghiệm của request điển hình.
- **p90:** 90% request có độ trễ thấp hơn hoặc bằng giá trị này.
- **p95:** hữu ích để quan sát phần đuôi phân phối.
- **p99:** phản ánh nhóm request chậm nhất, thường nhạy với vấn đề tài nguyên hoặc dependency.

Ví dụ truy vấn p95 từ histogram Prometheus:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_request_duration_seconds_bucket[5m])
  )
)
~~~

Khi so sánh, cần giữ cùng đơn vị, cùng cách lấy mẫu và cùng nhóm request. Không so sánh p95 của toàn bộ service với p95 chỉ của một route rồi kết luận bản phát hành gây tăng độ trễ.

### 4.1. Phân biệt latency của ứng dụng và dependency

Độ trễ tổng có thể đến từ:

- Thời gian xử lý trong ứng dụng.
- Truy vấn database.
- Cache miss hoặc cache contention.
- Gọi API bên ngoài.
- Hàng đợi và xử lý bất đồng bộ.
- Network hoặc gateway.
- Thời gian chờ connection/thread pool.

Distributed tracing giúp tìm span chiếm nhiều thời gian trong một request. Metrics cho thấy xu hướng; trace giúp xác định đường đi cụ thể; log cung cấp chi tiết sự kiện. Nên kết hợp cả ba thay vì chỉ nhìn một dashboard latency.

### 4.2. Theo dõi timeout và tail latency

Khi p99 tăng, có thể một nhóm request bị chậm do lock contention, retry dây chuyền, connection pool cạn hoặc dependency có tail latency cao. Retry quá nhiều có thể làm hệ thống tải nặng hơn.

Cần theo dõi timeout, số lần retry, thời gian chờ pool, request in-flight và saturation. Nếu timeout được cấu hình thấp hơn thời gian xử lý hợp lệ của một dependency, hệ thống có thể tạo nhiều lỗi dù dependency cuối cùng vẫn hoàn thành.

## 5. Theo dõi tín hiệu nghiệp vụ

Tín hiệu nghiệp vụ trả lời câu hỏi quan trọng nhất: thay đổi có làm quy trình mà người dùng cần thực hiện hoạt động đúng không?

Một endpoint trả HTTP 200 chưa chắc đồng nghĩa nghiệp vụ thành công. Ví dụ, API tạo đơn có thể trả 200 nhưng đơn không được lưu; payment service có thể nhận yêu cầu nhưng giao dịch bị treo ở trạng thái pending.

### 5.1. Chọn metric theo mục tiêu thay đổi

| Loại thay đổi | Tín hiệu nghiệp vụ cần theo dõi |
|---|---|
| Checkout | Tỷ lệ checkout hoàn tất, số đơn bị bỏ dở, thời gian hoàn tất |
| Thanh toán | Tỷ lệ authorization/capture thành công, pending, duplicate transaction |
| Đăng nhập | Tỷ lệ đăng nhập thành công, lỗi MFA, khóa tài khoản bất thường |
| Xử lý sự kiện | Số sự kiện nhận/xử lý, queue lag, dead-letter và thời gian xử lý |
| Đồng bộ dữ liệu | Số bản ghi đồng bộ, độ trễ đồng bộ, số bản ghi lỗi hoặc lệch |
| Tìm kiếm | Tỷ lệ truy vấn có kết quả, latency, lỗi index hoặc stale data |
| Báo cáo | Tỷ lệ job hoàn tất, độ mới dữ liệu, số dòng và tính nhất quán |

Mỗi metric cần định nghĩa rõ sự kiện bắt đầu, sự kiện hoàn tất, mẫu số và khoảng thời gian. Ví dụ, tỷ lệ thanh toán thành công phải phân biệt giao dịch bị từ chối hợp lệ với lỗi kỹ thuật ngoài dự kiến.

### 5.2. Đo tính đúng đắn của dữ liệu

Một số lỗi không thể phát hiện bằng HTTP status hoặc latency. Ví dụ, một thay đổi mapping có thể ghi nhầm currency, nhân đôi sự kiện hoặc cập nhật sai trạng thái.

Có thể bổ sung:

- Kiểm tra invariant nghiệp vụ.
- Đối chiếu số lượng bản ghi đầu vào và đầu ra.
- Kiểm tra duplicate key hoặc sự kiện xử lý nhiều lần.
- Đối soát tổng tiền, số lượng hoặc checksum theo batch.
- Theo dõi dữ liệu trễ, thiếu hoặc sai thứ tự.
- Kiểm tra tính tương thích schema giữa producer và consumer.

Với dữ liệu tài chính hoặc dữ liệu quan trọng, kiểm tra đối soát phải có phạm vi và quyền rõ ràng. Không nên đưa dữ liệu cá nhân hoặc giá trị giao dịch chi tiết vào metric label.

### 5.3. Xác định tín hiệu sớm và tín hiệu trễ

Một số chỉ số xuất hiện ngay sau deploy, như exception rate hoặc queue lag. Một số chỉ số cần thời gian mới đủ mẫu, như tỷ lệ hoàn tất đơn hàng hoặc tỷ lệ khách hàng quay lại.

Không nên kết luận release an toàn chỉ vì tín hiệu trễ chưa có dữ liệu. Hãy xác định chỉ số nào là điều kiện chặn ngay, chỉ số nào cần quan sát lâu hơn và có thể dùng proxy nào trong thời gian đầu.

## 6. Kết hợp metrics, logs và traces

Ba loại telemetry bổ sung cho nhau:

| Loại | Trả lời câu hỏi | Vai trò sau triển khai |
|---|---|---|
| Metrics | Điều gì đang thay đổi và mức độ lớn đến đâu? | Trend, alert, so sánh release |
| Logs | Sự kiện cụ thể nào đã xảy ra? | Điều tra lỗi và ngữ cảnh |
| Traces | Request đi qua những thành phần nào và chậm ở đâu? | Xác định dependency hoặc span gây lỗi |

Nên gắn các metadata phù hợp với telemetry:

- Service name và environment.
- Release ID hoặc version.
- Artifact digest hoặc build identifier nếu hệ thống hỗ trợ.
- Deployment timestamp hoặc change marker.
- Region, cluster và workload.
- Trace ID hoặc correlation ID trong log.

### 6.1. Release marker

Release marker là sự kiện được ghi nhận đúng thời điểm bắt đầu hoặc hoàn tất triển khai. Marker nên chứa release ID, commit SHA, artifact digest, môi trường, config revision và thời điểm.

Khi dashboard có marker, người vận hành có thể nhìn thấy sự thay đổi lỗi hoặc latency bắt đầu trước hay sau deploy. Marker không chứng minh quan hệ nhân quả, nhưng giúp thu hẹp khoảng điều tra.

Ví dụ metadata phát hành:

~~~json
{
  "release_id": "orders-2026.11.18-03",
  "commit_sha": "8f2a...c91d",
  "artifact_digest": "sha256:...",
  "environment": "production",
  "config_revision": "orders-prod-v12",
  "deployed_at": "2026-11-18T08:30:00Z"
}
~~~

### 6.2. Bảo vệ dữ liệu telemetry

Log và trace có thể chứa thông tin nhạy cảm. Không ghi password, token, session cookie, dữ liệu thẻ hoặc payload cá nhân đầy đủ. Dùng redaction, access control, retention và sampling phù hợp.

Correlation ID giúp nối các log và trace của một request mà không cần ghi thông tin định danh người dùng vào mọi metric. Nếu cần liên kết với tài khoản, hãy dùng cơ chế định danh nội bộ có kiểm soát quyền và thời hạn lưu trữ.

## 7. So sánh với baseline và nhóm đối chứng

Một chỉ số có thay đổi sau deploy không tự chứng minh bản phát hành là nguyên nhân. Traffic có thể tăng theo giờ, chiến dịch marketing có thể làm thay đổi hành vi, hoặc một dependency bên ngoài đang gặp sự cố.

Có hai cách so sánh bổ sung cho nhau:

- **Baseline trước deploy:** so sánh với cùng service và cùng loại traffic trong một khoảng thời gian trước thay đổi.
- **Control group đồng thời:** so sánh phiên bản mới với phiên bản cũ đang nhận traffic cùng thời điểm, ví dụ trong canary.

So sánh đồng thời thường hữu ích hơn khi traffic biến động theo thời gian, nhưng cần bảo đảm hai nhóm tương đương về region, route, loại client và workload.

### 7.1. Chọn cửa sổ quan sát

Cửa sổ quá ngắn có thể bị nhiễu bởi ít request; cửa sổ quá dài có thể làm chậm phát hiện. Cần chọn theo traffic, đặc điểm nghiệp vụ và tốc độ xuất hiện của lỗi.

Ví dụ:

- Dịch vụ có lưu lượng cao có thể phát hiện lỗi kỹ thuật trong vài phút.
- Luồng thanh toán ít giao dịch cần thời gian đủ dài để có mẫu đáng tin.
- Batch chạy theo giờ cần quan sát ít nhất một chu kỳ xử lý liên quan.
- Tác vụ đồng bộ theo ngày cần kiểm tra độ mới và kết quả sau chu kỳ hoàn tất.

Không dùng một khoảng thời gian cố định cho mọi release. Nếu chưa đủ mẫu, trạng thái phù hợp là **INSUFFICIENT_DATA** hoặc tiếp tục quan sát, không tự coi là pass.

### 7.2. Cẩn thận với tỷ lệ trên mẫu nhỏ

Nếu chỉ có 5 request và 1 request lỗi, error rate là 20%, nhưng độ bất định lớn. Nếu có 100.000 request và 1.000 request lỗi, tỷ lệ 1% có ý nghĩa thống kê và vận hành khác.

Nên đặt điều kiện số lượng mẫu tối thiểu trước khi quyết định theo tỷ lệ. Với nghiệp vụ có volume thấp, có thể kết hợp kiểm thử synthetic, kiểm tra invariant và review thủ công.

### 7.3. Xem xét mùa vụ và thay đổi bên ngoài

So sánh trước/sau nên cân nhắc:

- Khung giờ trong ngày và ngày trong tuần.
- Sự kiện hoặc chiến dịch làm thay đổi traffic.
- Sự cố của dependency bên ngoài.
- Thay đổi cấu hình hoặc hạ tầng diễn ra đồng thời.
- Thay đổi routing hoặc tỷ lệ traffic giữa các vùng.

Nếu nhiều thay đổi diễn ra cùng lúc, cần ghi marker riêng cho từng thay đổi để tránh quy kết sai nguyên nhân.

## 8. Theo dõi theo phiên bản và phạm vi ảnh hưởng

Số liệu tổng thể có thể che giấu một lỗi chỉ xuất hiện ở phiên bản mới hoặc một nhóm traffic cụ thể. Cần có khả năng phân tách theo:

- Release ID hoặc version.
- Artifact digest.
- Region, cluster hoặc availability zone.
- Route/API operation.
- Client version hoặc loại request.
- Tenant tier hoặc nhóm tính năng, nếu phù hợp và an toàn.
- Cohort canary và control.

Tránh tạo label có cardinality rất cao như request ID, user ID, email hoặc order ID. Các trường này phù hợp hơn với log/tracing có kiểm soát, không phù hợp để gắn lên mọi time series metric.

Nếu traffic được chuyển qua nhiều instance, cần biết mỗi instance đang chạy release nào. Một lần rollout có thể tồn tại đồng thời nhiều phiên bản; dashboard chỉ gắn nhãn service chung sẽ không phân biệt được tín hiệu của candidate và control.

## 9. Thiết kế giai đoạn kiểm chứng sau deploy

Kiểm chứng nên tăng dần theo mức độ tác động của release và khả năng quan sát. Một luồng tham khảo:

| Giai đoạn | Nội dung | Điều kiện tiếp tục |
|---|---|---|
| Ngay sau deploy | Readiness, process state, endpoint cơ bản, version/digest | Workload sẵn sàng và đúng phiên bản |
| Smoke validation | Luồng nghiệp vụ tối thiểu và dependency chính | Không có lỗi nghiêm trọng |
| Early observation | Error rate, latency, saturation, log và trace | Không vi phạm ngưỡng bảo vệ |
| Business validation | Conversion, transaction success, queue/data correctness | Tín hiệu nghiệp vụ không suy giảm ngoài ngưỡng |
| Progressive rollout | Tăng traffic theo từng bước | Mỗi bước đủ dữ liệu và đạt gate |
| Release confirmation | Ghi nhận kết quả, release marker và bằng chứng | Tất cả gate bắt buộc đạt |

### 9.1. Ngay sau triển khai

Bắt đầu bằng readiness và xác minh phiên bản. Kiểm tra ứng dụng đang chạy đúng artifact digest và config revision được phê duyệt. Nếu version endpoint trả về chỉ là tag mutable, nên bổ sung build ID hoặc digest để xác minh chính xác.

### 9.2. Giai đoạn quan sát sớm

Theo dõi các lỗi có thể xuất hiện ngay: exception, 5xx, timeout, restart, OOM, connection pool và dependency failures. Nếu một chỉ số vượt ngưỡng nghiêm trọng, dừng rollout trước khi tăng traffic.

### 9.3. Giai đoạn quan sát nghiệp vụ

Chờ đủ dữ liệu để đánh giá các chỉ số như tỷ lệ thanh toán, hoàn tất đơn hàng, xử lý queue hoặc độ mới dữ liệu. Nếu tín hiệu nghiệp vụ có độ trễ, hãy đặt thời gian quan sát theo chu kỳ thực tế của nghiệp vụ.

## 10. Canary và progressive delivery

Canary deployment đưa phiên bản mới đến một phần traffic trước khi mở rộng. Mục đích là giới hạn blast radius và dùng traffic thực để kiểm chứng hành vi.

Một tiến trình ví dụ:

1. Triển khai candidate nhưng chưa nhận traffic.
2. Chạy readiness và smoke test.
3. Chuyển một tỷ lệ traffic nhỏ đến candidate.
4. So sánh lỗi, latency và business signals với control.
5. Nếu đạt, tăng traffic theo từng bước.
6. Nếu chưa đủ dữ liệu, giữ nguyên tỷ lệ và quan sát tiếp.
7. Nếu vi phạm gate, dừng rollout và chuyển traffic về phiên bản ổn định.
8. Khi đạt mức traffic và thời gian quan sát yêu cầu, hoàn tất release.

~~~mermaid
flowchart LR
    A["Candidate 0%"] --> B["Smoke test"]
    B --> C["Canary 5%"]
    C --> D["So sánh metrics và business KPIs"]
    D --> E{"Đạt gate?"}
    E -- "Có" --> F["Canary 25%"]
    F --> G["Quan sát lại"]
    G --> H{"Đạt gate?"}
    H -- "Có" --> I["Canary 50% rồi 100%"]
    E -- "Chưa đủ dữ liệu" --> J["Giữ tỷ lệ và chờ"]
    H -- "Chưa đủ dữ liệu" --> J
    J --> D
    E -- "Không" --> K["Dừng rollout / chuyển traffic về bản ổn định"]
    H -- "Không" --> K
~~~

Tỷ lệ 5%, 25% hay 50% chỉ là ví dụ. Mức tăng phải phù hợp với khả năng cô lập, traffic và blast radius. Một hệ thống có ít request hoặc dữ liệu nhạy cảm có thể cần rollout thận trọng hơn.

### 10.1. So sánh canary với control

Cần so sánh các nhóm trong cùng thời gian và điều kiện tương đương. Nếu candidate chỉ nhận traffic từ một region có latency cao hơn, chênh lệch có thể do routing chứ không phải code.

Nên theo dõi:

- Error rate theo cohort.
- p95/p99 latency theo route.
- Resource saturation và dependency errors.
- Business success rate.
- Số lượng request đủ lớn để kết luận.
- Thời gian candidate đã nhận traffic.

Canary analysis nên trả về **PASS**, **FAIL** hoặc **INCONCLUSIVE**. Không nên buộc mọi kết quả thành boolean khi dữ liệu chưa đủ.

## 11. Đặt ngưỡng, SLO và quyết định rollout

Ngưỡng kiểm chứng cần dựa trên SLO, baseline và mức ảnh hưởng chấp nhận được. Không nên dùng một con số chung cho mọi ứng dụng.

Ví dụ về loại điều kiện:

- Error rate của candidate không vượt ngưỡng tuyệt đối đã quy định.
- Error rate của candidate không xấu hơn control quá mức cho phép.
- p95 latency không tăng vượt biên độ chấp nhận.
- Không xuất hiện lỗi nghiêm trọng mới hoặc crash loop.
- Business success rate không giảm vượt ngưỡng.
- Queue lag và dữ liệu tồn đọng không tăng không kiểm soát.
- Số request tối thiểu đã đạt để kết quả có ý nghĩa.

### 11.1. Liên hệ với SLO và error budget

SLO định nghĩa mức độ tin cậy mục tiêu trong một cửa sổ thời gian. Error budget là phần lỗi có thể chấp nhận tương ứng với SLO.

Ví dụ, nếu SLO availability là 99,9% trong cửa sổ được định nghĩa, error budget biểu thị phần không khả dụng còn được phép trong cửa sổ đó. Một release gây tiêu hao error budget nhanh có thể cần dừng rollout, dù chưa vượt một ngưỡng lỗi tức thời.

SLO dài hạn không thay thế gate ngắn hạn sau deploy. Có thể kết hợp:

- Ngưỡng bảo vệ tức thời để phát hiện lỗi nghiêm trọng.
- So sánh candidate/control trong giai đoạn canary.
- Theo dõi burn rate của error budget.
- Business guardrail để bảo vệ quy trình quan trọng.

### 11.2. Định nghĩa ba kết quả rõ ràng

| Kết quả | Ý nghĩa | Hành động |
|---|---|---|
| **PASS** | Đủ dữ liệu và các điều kiện đều đạt | Tiếp tục rollout hoặc xác nhận release |
| **FAIL** | Có điều kiện vượt ngưỡng hoặc lỗi nghiêm trọng | Dừng rollout, rollback hoặc xử lý theo runbook |
| **INCONCLUSIVE** | Chưa đủ mẫu, telemetry thiếu hoặc dependency quan sát lỗi | Giữ tỷ lệ traffic, sửa quan sát hoặc yêu cầu review |

Nếu hệ thống monitoring không có dữ liệu, không thể kết luận ứng dụng an toàn. Cần phân biệt lỗi của ứng dụng với lỗi của hệ thống quan sát, nhưng trạng thái thiếu telemetry bắt buộc không nên tự động trở thành pass.

## 12. Tự động dừng rollout và rollback

Có thể tự động dừng hoặc rollback khi các điều kiện rõ ràng bị vi phạm. Tuy nhiên, rollback phải dựa trên khả năng tương thích và trạng thái dữ liệu.

Các trigger có thể gồm:

- Error rate tăng vượt ngưỡng trong nhiều cửa sổ liên tiếp.
- p95 hoặc p99 latency tăng mạnh so với control.
- Crash loop, OOM hoặc restart liên tục.
- Business success rate giảm rõ rệt.
- Queue lag hoặc dead-letter tăng vượt ngưỡng.
- Có lỗi bảo mật nghiêm trọng hoặc dữ liệu sai.
- Candidate không đạt readiness trong thời hạn.

Không nên rollback chỉ vì một điểm dữ liệu đơn lẻ nếu đó có thể là nhiễu. Có thể yêu cầu ngưỡng kéo dài trong một số cửa sổ, số mẫu tối thiểu hoặc kết hợp nhiều tín hiệu. Với lỗi nghiêm trọng như lộ dữ liệu hoặc sai lệch giao dịch, có thể cần hành động ngay mà không chờ đủ cửa sổ thống kê.

### 12.1. Kiểm tra điều kiện rollback

Trước khi rollback, cần xác định:

- Phiên bản trước còn tồn tại và có thể triển khai lại.
- Artifact digest và cấu hình trước đã được lưu.
- Schema database và event contract còn tương thích.
- Migration có thể đảo ngược hay cần forward fix.
- Credential đã luân chuyển có tương thích với phiên bản trước.
- Việc chuyển traffic có thể thực hiện an toàn.
- Có thể xác minh phiên bản trước hoạt động trở lại.

Nếu không thể rollback an toàn, có thể dừng rollout và yêu cầu người vận hành chọn biện pháp khác. Tự động rollback không phù hợp với mọi thay đổi dữ liệu hoặc migration irreversible.

### 12.2. Xác minh sau rollback

Rollback cũng cần kiểm chứng:

1. Xác nhận traffic đã chuyển về phiên bản ổn định.
2. Xác minh release ID và artifact digest đang chạy.
3. Chạy readiness và smoke test.
4. Quan sát error rate, latency và business signals.
5. Ghi trạng thái rollback cùng nguyên nhân.
6. Giữ lại telemetry của candidate để điều tra.

Không ghi rollback thành công chỉ vì lệnh rollback trả về 0. Cần xác minh trạng thái thực tế và sức khỏe hệ thống.

## 13. Điều tra khi tín hiệu xấu đi sau thay đổi

Khi metric xấu đi, cần xác định phạm vi và tương quan với release trước khi kết luận nguyên nhân.

Một trình tự điều tra:

1. Xác định thời điểm release marker và release ID.
2. So sánh candidate với control hoặc baseline tương ứng.
3. Phân tách theo route, region, workload và loại request.
4. Xem error type, exception và dependency failures.
5. Dùng trace để tìm span có latency hoặc lỗi bất thường.
6. Đối chiếu business events, queue lag và dữ liệu đầu ra.
7. Kiểm tra thay đổi cấu hình, hạ tầng hoặc dependency đồng thời.
8. Quyết định tiếp tục quan sát, dừng rollout, rollback hoặc forward fix.
9. Ghi lại kết quả và liên kết với incident/ticket nếu có.

### Một số tình huống thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| 5xx tăng ngay sau deploy | Exception mới, config sai hoặc dependency không tương thích | Phân loại lỗi, trace và log theo release |
| Average latency bình thường nhưng p99 tăng | Tail latency, pool contention hoặc dependency chậm | Xem histogram, span và thời gian chờ |
| CPU tăng nhưng error rate chưa tăng | Tải xử lý tăng, vòng lặp hoặc tối ưu bị thoái lui | Theo dõi saturation và latency theo cohort |
| Health check đạt nhưng đơn hàng thất bại | Lỗi nghiệp vụ hoặc ghi dữ liệu không đúng | Đối soát business events và database |
| Queue lag tăng dần | Consumer chậm, lỗi retry hoặc throughput giảm | Xem processing rate, retry và dead-letter |
| Chỉ một region bị ảnh hưởng | Routing, config hoặc dependency riêng vùng | Phân tách metric theo region |
| Canary có tỷ lệ lỗi cao nhưng mẫu rất nhỏ | Chưa đủ traffic để kết luận | Trả INCONCLUSIVE và tiếp tục quan sát |
| Không có metric sau deploy | Agent, exporter hoặc telemetry pipeline lỗi | Kiểm tra observability trước khi kết luận release |
| Lỗi xuất hiện trễ | Memory leak, pool exhaustion hoặc batch job | Kéo dài cửa sổ và theo dõi xu hướng |
| Rollback xong vẫn lỗi | Schema/config hoặc dữ liệu đã thay đổi không tương thích | Kiểm tra migration và trạng thái dữ liệu |

Không nên xóa hoặc ghi đè telemetry của candidate sau rollback. Dữ liệu này giúp tìm nguyên nhân gốc và ngăn lỗi tái diễn.

## 14. Ví dụ policy kiểm chứng sau triển khai

Ví dụ dưới đây mô tả policy ở mức khái niệm. Ngưỡng cần được xác định từ SLO, baseline và đặc tính của từng dịch vụ:

~~~yaml
post_deployment_validation:
  release:
    require_release_marker: true
    verify_artifact_digest: true
    verify_config_revision: true

  immediate_checks:
    - readiness
    - smoke_test
    - running_version

  observation:
    metrics:
      - error_rate
      - p95_latency
      - p99_latency
      - saturation
      - dependency_errors
    business_signals:
      - transaction_success_rate
      - queue_lag
      - data_quality_failures
    require_minimum_sample: true

  canary:
    enabled: true
    stages:
      - traffic_percent: 5
      - traffic_percent: 25
      - traffic_percent: 50
      - traffic_percent: 100
    decisions:
      pass: continue
      fail: stop_and_apply_rollback_policy
      inconclusive: hold_and_observe

  rollback:
    require_previous_artifact: true
    require_compatibility_check: true
    verify_after_rollback: true
~~~

Policy thực tế cần ánh xạ metric, query, threshold, cửa sổ, mẫu tối thiểu, người sở hữu và hành động sang hệ thống monitoring/deployment đang dùng. Không nên đặt một threshold duy nhất trong template rồi áp dụng cho mọi service.

## 15. Lộ trình thực hành

Có thể thực hành trên một ứng dụng staging theo các bước:

1. **Chọn mục tiêu release:** ghi rõ thay đổi tác động đến route, dependency hoặc quy trình nghiệp vụ nào.
2. **Chọn tín hiệu:** xác định error rate, p95/p99, saturation và 1–3 business metrics quan trọng.
3. **Định nghĩa metric:** thống nhất tên, đơn vị, mẫu số, label và cách xử lý retry.
4. **Tạo baseline:** thu thập dữ liệu trước deploy theo khung thời gian phù hợp.
5. **Gắn release marker:** lưu release ID, commit SHA, artifact digest, config revision và timestamp.
6. **Kiểm tra ngay sau deploy:** chạy readiness, smoke test và xác minh version/digest.
7. **Quan sát candidate:** phân tách metric theo release hoặc cohort, so sánh với control.
8. **Đặt guardrail:** xác định ngưỡng pass/fail/inconclusive và số mẫu tối thiểu.
9. **Thử progressive rollout:** tăng traffic theo từng bước, chỉ tiếp tục khi gate đạt.
10. **Diễn tập lỗi:** tạo lỗi có kiểm soát trong staging, xác nhận alert, dừng rollout và rollback.
11. **Kiểm tra business correctness:** đối soát kết quả nghiệp vụ và dữ liệu sau thay đổi.
12. **Lưu bằng chứng:** tạo release report gồm telemetry snapshot, quyết định gate và trạng thái cuối.

### Tiêu chí hoàn thành

Người học có thể xem bài thực hành hoàn thành khi chứng minh được:

- Chọn được tín hiệu kỹ thuật và nghiệp vụ phù hợp với mục tiêu thay đổi.
- Tính và diễn giải được error rate với mẫu số rõ ràng.
- Theo dõi p50, p95, p99 và phân biệt average với tail latency.
- Liên kết metrics, logs và traces với release ID.
- So sánh candidate với baseline hoặc control group phù hợp.
- Xử lý trường hợp mẫu nhỏ hoặc telemetry thiếu bằng trạng thái inconclusive.
- Thiết lập guardrail theo SLO, error budget và business impact.
- Thực hiện canary/progressive rollout có điều kiện.
- Dừng rollout hoặc rollback khi tín hiệu vi phạm policy.
- Xác minh lại hệ thống sau rollback.
- Lưu được bằng chứng và truy vết quyết định phát hành.

## Kết luận

Theo dõi lỗi, độ trễ và tín hiệu nghiệp vụ sau thay đổi giúp xác minh phần mềm trong điều kiện vận hành thực tế. Error rate cho biết mức độ thất bại, percentile latency cho thấy trải nghiệm ở phần đuôi, còn business signals xác nhận quy trình người dùng cần thực hiện có thực sự đúng hay không. Metrics, logs và traces cần được gắn với release marker để liên kết sự thay đổi với dữ liệu quan sát.

Một quy trình đáng tin cậy có baseline hoặc control group, cửa sổ quan sát phù hợp, mẫu tối thiểu và kết quả pass/fail/inconclusive rõ ràng. Canary giúp giới hạn phạm vi ảnh hưởng; SLO và business guardrail định hướng quyết định; rollback chỉ được xem là hoàn tất sau khi trạng thái phiên bản trước và sức khỏe hệ thống đã được xác minh. Nhờ đó, pipeline có thể đưa ra quyết định phát hành dựa trên tác động thực tế thay vì chỉ dựa vào việc lệnh triển khai đã chạy xong.

