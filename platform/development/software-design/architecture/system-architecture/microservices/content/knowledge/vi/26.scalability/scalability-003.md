# Đo thông lượng, độ trễ và mức sử dụng tài nguyên trong microservices

## 1. Bối cảnh: đo lường trước khi mở rộng

Khả năng mở rộng (scalability) của microservices không được chứng minh bằng số lượng service, số pod hay việc có bật autoscaling. Một hệ thống chỉ có khả năng mở rộng khi có thể xử lý thêm khối lượng công việc trong giới hạn chất lượng dịch vụ và chi phí chấp nhận được. Để xác định giới hạn đó, cần đo đồng thời **thông lượng (throughput)**, **độ trễ (latency)** và **mức sử dụng cùng độ bão hòa tài nguyên (utilization và saturation)**.

Ví dụ, catalog-service tăng từ 100 lên 250 request/giây nhưng độ trễ p99 nhảy từ 180 ms lên 4 giây và connection pool của database đã cạn. Nếu chỉ nhìn thông lượng, nhóm có thể tưởng hệ thống đang mở rộng hiệu quả. Nếu chỉ nhìn CPU, nhóm có thể bỏ qua nghẽn cơ sở dữ liệu hoặc hàng đợi. Nếu chỉ nhìn latency trung bình, nhóm bỏ sót nhóm người dùng có trải nghiệm rất chậm.

Ba nhóm phép đo cần được đặt trong cùng bối cảnh: **loại tải**, **phiên bản triển khai**, **phạm vi môi trường**, **cửa sổ thời gian**, **độ chính xác của instrument** và **mức lỗi**.

Sau bài này, người học có thể:
1. Định nghĩa các metric và đơn vị đo phù hợp cho API đồng bộ, message processing và batch worker.
2. Phân biệt throughput, latency, concurrency, utilization, saturation và error rate.
3. Thiết kế instrumentation, dashboard và truy vấn phân vị trên dữ liệu histogram.
4. Dùng phép đo để tìm bottleneck ở service, mạng, database, cache và message broker.
5. Thực hiện load test có kiểm soát, giải thích đường cong thông lượng–độ trễ–tài nguyên.
6. Lựa chọn tín hiệu autoscaling, SLO và cảnh báo phù hợp với trải nghiệm người dùng.

## 2. Ba trụ cột và các phép đo đi kèm

| Nhóm | Đại lượng | Đơn vị thường dùng | Câu hỏi chính |
| --- | --- | --- | --- |
| Throughput | Request hoàn thành | req/s, req/min | Mỗi giây hệ thống phục vụ bao nhiêu request? |
| Throughput | Tác vụ hoặc thông điệp xử lý xong | jobs/s, messages/s | Worker tiêu thụ được bao nhiêu đơn vị công việc? |
| Throughput | Dữ liệu vận chuyển | bytes/s, MiB/s | Network hoặc storage chuyển bao nhiêu byte? |
| Latency | Thời gian phản hồi | ms, s | Một request mất bao lâu từ góc nhìn đo được? |
| Latency | Thời gian chờ hàng đợi | ms, s | Tác vụ mất bao lâu trước khi bắt đầu được xử lý? |
| Latency | Phân vị | p50, p95, p99 | Bao nhiêu phần trăm yêu cầu được phục vụ trong ngưỡng? |
| Resource | CPU | CPU cores, % quota | Workload dùng bao nhiêu thời gian CPU? |
| Resource | RAM/heap | MiB, % limit | Bộ nhớ và heap đang dùng bao nhiêu? |
| Resource | Kết nối và thread | active/max, pending | Pool hoặc executor còn khả năng nhận việc? |
| Resource | Disk/network I/O | IOPS, bytes/s, queue depth | Đường dữ liệu có bị nghẽn hay không? |
| Saturation | Queue length, lag, throttle | số phần tử, ms, % | Nhu cầu đã vượt năng lực xử lý chưa? |
| Reliability | Error rate | % hoặc errors/s | Có bao nhiêu công việc thất bại? |

Không nên diễn giải một metric đơn lẻ. Thông lượng tăng có thể đi cùng lỗi tăng. CPU thấp có thể là dấu hiệu dịch vụ bị chặn trên I/O, chứ không có nghĩa còn nhiều năng lực xử lý hữu ích.

**Utilization** mô tả lượng tài nguyên đã sử dụng so với năng lực hoặc hạn mức được cấp. **Saturation** mô tả áp lực chờ đợi, tranh chấp hoặc bị giới hạn khi nhu cầu gần hoặc vượt khả năng phục vụ. Hai khái niệm liên quan nhưng không đồng nhất: CPU utilization cao chưa chắc đã có queue; CPU utilization thấp vẫn có thể có queue do hết connection pool.

## 3. Xác định mục tiêu đo trước khi chọn công cụ

Trước khi bật metric hàng loạt, cần xác định:
- **Đơn vị công việc:** HTTP request, RPC, giao dịch checkout, event, job hay byte?
- **Điểm bắt đầu/kết thúc:** từ client gửi đến khi nhận response, từ gateway đến service, từ lúc message được tạo đến xử lý thành công?
- **Điều kiện thành công:** HTTP 2xx không luôn tương đương nghiệp vụ thành công; retry và duplicate có thể khiến số đếm sai.
- **Nhóm phân tích:** service, operation/route, môi trường, phiên bản, region, availability zone, instance, consumer group.
- **Khoảng quan sát:** 1 phút, 5 phút, 1 giờ, giờ cao điểm hay cả ngày?
- **Ngân sách độ trễ:** ví dụ checkout p95 dưới ngưỡng dựa trên SLO của sản phẩm; ngưỡng phải do hệ thống xác lập.
- **Tải mục tiêu và kế hoạch tăng trưởng:** hiện tại bao nhiêu req/s, kỳ vọng tăng bao nhiêu, burst tồn tại bao lâu?

Mỗi số liệu cần ghi rõ scope. Câu “độ trễ là 200 ms” thiếu thông tin: latency của route nào, tại đâu, ở phân vị nào, trong cửa sổ nào, có bao gồm request lỗi và timeout hay không?

Trong microservices, nên đo cả **chỉ số sản phẩm nhìn từ bên ngoài** và **chỉ số năng lực phục vụ nội bộ**. Hệ thống có thể giữ throughput nội bộ ổn định nhờ trả về lỗi nhanh; từ góc nhìn khách hàng, kết quả vẫn là thất bại.

## 4. Đo thông lượng (throughput)

### 4.1. Định nghĩa

Thông lượng là số đơn vị công việc hoàn thành trong một đơn vị thời gian:

**Throughput = số công việc hoàn thành / thời lượng quan sát**

Nếu một service hoàn thành 18.000 request hợp lệ trong 3 phút, thông lượng trung bình là 18.000 / 180 = **100 req/s**. Đây là số trung bình của cửa sổ 3 phút, không cho biết peak trong từng giây.

Cần phân biệt:
- **Arrival rate (offered load):** request/tác vụ đến hệ thống trên mỗi giây.
- **Completion rate:** request/tác vụ xử lý xong trên mỗi giây.
- **Successful throughput:** số hoàn thành đúng nghiệp vụ trên mỗi giây.
- **Accepted throughput:** số được nhận vào xử lý; có thể chưa hoàn thành.

Khi arrival rate liên tục cao hơn completion rate, queue hoặc lượng request đang chờ thường tăng. Có những tình huống hệ thống từ chối tải quá mức theo chủ đích bằng HTTP 429 hoặc backpressure; khi đó completion rate có thể thấp nhưng hệ thống bảo vệ được phần còn lại.

### 4.2. Đếm đúng đơn vị

Với HTTP đồng bộ, request counter thường tăng khi request hoàn thành và có đủ method, route, status. Có thể phân tích theo:
- Tổng request/s tới gateway.
- Request/s tới từng service hoặc operation.
- Successful request/s của nghiệp vụ.
- Request lỗi 4xx, 5xx, timeout, canceled.
- Retry rate: một hành động người dùng có thể tạo nhiều HTTP request.
- Request size/response size nếu tải biến thiên theo dữ liệu.

Với event-driven service, cần tách:
- **Published messages/s:** tốc độ tạo message.
- **Consumed messages/s:** tốc độ nhận thông điệp.
- **Successfully processed messages/s:** tốc độ xử lý hoàn thành.
- **Failed/retried messages/s:** tốc độ lỗi và xử lý lại.
- **Duplicate/deduplicated messages:** các bản tin lặp được nhận biết.
- **Consumer lag/backlog:** phần việc chưa được xử lý.

Không lấy số lần gọi handler làm số giao dịch nghiệp vụ thành công khi handler có retry, ack và duplicate delivery.

### 4.3. Counter, rate và cửa sổ thời gian

Counter là đại lượng tăng dần rồi có thể reset khi process restart. Muốn biểu diễn req/s, hệ thống metric thường tính **rate** trên một khoảng thời gian. Ví dụ trong Prometheus:

~~~promql
sum(
  rate(http_server_requests_seconds_count{
    job="catalog-service"
  }[5m])
)
~~~

Truy vấn trên là ví dụ phụ thuộc tên metric thực tế do exporter/Micrometer cung cấp. Nó tính tốc độ trung bình 5 phút của số lần quan sát request, không phải giá trị tức thời chính xác từng mili giây.

Muốn phân loại theo HTTP route:

~~~promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count{
    job="catalog-service"
  }[5m])
)
~~~

Với dữ liệu Prometheus, nhãn đường dẫn nên là **route template** như /products/{id}, không phải URL thật chứa product ID. Gắn từng ID vào metric tạo cardinality rất lớn.

Trong hệ thống có nhiều instance, phải cộng rate của từng counter trước. Không cộng raw counter rồi mới lấy rate qua các lần restart vì reset có thể bị che khuất. Với phép đo theo region hoặc environment, filter hoặc group theo các nhãn đó để tránh trộn dữ liệu không cùng mục tiêu.

### 4.4. Burst, throughput hữu ích và giới hạn

Thông lượng trung bình 100 req/s có thể che giấu đỉnh 1.000 req/s trong vài giây. Cần xem cả rate cửa sổ ngắn, số kết nối đồng thời và độ sâu hàng đợi. Tuy nhiên cửa sổ quá ngắn dễ nhiễu do scrape interval hoặc traffic ít. Chọn cửa sổ phù hợp với thời gian phản ứng của hệ thống.

Tại điểm bão hòa, tăng offered load có thể làm completion throughput gần như không tăng, trong khi latency và lỗi tăng mạnh. Đường cong này là bằng chứng rõ hơn về giới hạn capacity so với việc chỉ nhìn CPU.

## 5. Đo độ trễ (latency)

### 5.1. Độ trễ có nhiều định nghĩa

**Client-observed latency** bao gồm quá trình client chờ kết quả, chịu ảnh hưởng DNS, kết nối, TLS, mạng, proxy và server. **Server-side request duration** được đo từ lúc server bắt đầu xử lý theo vị trí instrumentation đến lúc hoàn tất response. **Dependency latency** là thời gian gọi database, cache hoặc dịch vụ khác. **Queue waiting time** là thời gian tác vụ chờ trước khi worker bắt đầu thực thi.

Các con số này không thể thay thế cho nhau:

~~~text
Client gửi request
  → DNS / connect / TLS
  → Gateway / load balancer
  → Service nhận request
  → Chờ thread/connection/queue
  → Xử lý nghiệp vụ
  → Database hoặc RPC downstream
  → Serialize và gửi response
  → Mạng về client
Client nhận response
~~~

Đo ở gateway phản ánh trải nghiệm qua nhiều lớp hơn đo trong controller. Đo ở controller hoặc repository vẫn có ích để tìm nguyên nhân nhưng không phản ánh toàn bộ thời gian người dùng chờ.

Với message processing, nên đo ít nhất **time in queue**, **processing duration**, **end-to-end event age**. Một worker xử lý mỗi event trong 30 ms nhưng backlog khiến event chờ 12 phút không được coi là đáp ứng yêu cầu thời gian thực.

### 5.2. Trung bình, phân vị và đuôi phân phối

Giả sử 100 request có 95 request hoàn thành trong 100 ms và 5 request mất 4.000 ms. Latency trung bình là:

**(95 × 100 + 5 × 4.000) / 100 = 295 ms.**

Giá trị trung bình không cho thấy một nhóm nhỏ chịu độ trễ rất cao. Cần xem thêm:
- **p50:** trung vị, 50% số đo không vượt mức này.
- **p90/p95:** mức mà 90%/95% số đo không vượt.
- **p99:** mức mà 99% số đo không vượt, hữu ích để theo dõi tail latency.
- **Max:** có thể hữu ích trong debug nhưng dễ nhiễu, phụ thuộc cửa sổ và lượng mẫu.

Không so sánh p99 của 30 request với p99 của 3 triệu request như hai ước lượng có độ tin cậy ngang nhau. Phân vị với ít mẫu rất không ổn định; luôn hiển thị **sample count** cùng khoảng thời gian.

### 5.3. Histogram và quantile

Histogram lưu số quan sát vào các bucket (thường có nhãn **le** cho giới hạn trên), tổng số mẫu và tổng duration. Nhờ vậy có thể kết hợp các instance để ước tính phân vị:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      job="catalog-service",
      uri="/products/{id}"
    }[5m])
  )
)
~~~

Ví dụ này áp dụng cho **classic Prometheus histogram** với duration theo giây. Các nhãn phải phản ánh exporter thực tế. Nếu dùng native histograms, cú pháp và cách aggregation khác; cần chọn đúng loại dữ liệu. Kết quả p95 là **ước lượng dựa trên phân bố bucket**, không phải percentile chính xác của raw samples.

Để theo dõi theo route và giữ phân nhóm:

~~~promql
histogram_quantile(
  0.99,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{
      job="catalog-service"
    }[5m])
  )
)
~~~

**Không lấy trung bình các p95 hoặc p99 của từng instance** để ra p95 toàn service. Quantile không cộng gộp theo cách đó. Cần gộp histogram bucket rồi mới tính quantile, hoặc tính từ tập mẫu gốc nếu có.

**Bucket boundaries phải khớp SLO.** Nếu service có ngưỡng latency 300 ms, nên có bucket tại hoặc gần ngưỡng này để tính tỷ lệ request đạt chuẩn. Ví dụ một histogram chỉ có bucket 1 s và 5 s không đủ độ phân giải cho chính sách 300 ms.

### 5.4. Cách tính tỷ lệ request trong ngưỡng

Với classic histogram có bucket le="0.3" (300 ms), tỷ lệ request dưới hoặc bằng 300 ms:

~~~promql
sum(rate(http_server_requests_seconds_bucket{
  job="catalog-service",
  le="0.3"
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  job="catalog-service"
}[5m]))
~~~

Chỉ áp dụng khi bộ bucket có thật giá trị 0.3 và time series đúng cùng phạm vi. Đây là tỷ lệ theo thời gian quan sát, cần xử lý tình huống mẫu bằng 0 khi dựng alert hoặc dashboard. Việc đạt latency có thể cần loại trừ hoặc phân loại riêng request lỗi; phải thống nhất với định nghĩa SLI.

### 5.5. Timeout và canceled request

Một lỗi đo lường thường gặp là timer chỉ ghi duration khi request thành công. Timeout, client cancel, retry và exception bị bỏ khỏi histogram, khiến latency dashboard trông tốt nhất khi production đang lỗi nặng.

Thiết kế cần:
- Ghi duration của toàn bộ kết quả có thể quan sát theo nhãn outcome.
- Đếm timeout, cancellation và retry thành các loại riêng.
- Đặt rõ điểm dừng timer khi server không biết client đã nhận response hay chưa.
- Không chỉ dựa vào server-side metrics để đo phần request bị chặn ở gateway hoặc network.
- Kết hợp probe từ bên ngoài để quan sát trải nghiệm đầu cuối.

## 6. Quan hệ giữa thông lượng, concurrency và độ trễ

**Concurrency** là số công việc đang được xử lý hoặc đang ở trong hệ thống tại cùng một thời điểm. Nó khác throughput: 100 request đồng thời không có nghĩa là 100 request/giây.

Trong một hệ thống ổn định, với đơn vị và phạm vi đo nhất quán, định luật Little cho quan hệ:

**L = λ × W**

Trong đó:
- **L:** số công việc trung bình đang ở trong hệ thống.
- **λ:** tốc độ hoàn thành trung bình khi hệ thống ở trạng thái ổn định.
- **W:** thời gian lưu trú trung bình của một công việc trong cùng phạm vi.

Ví dụ catalog-service phục vụ trung bình 120 req/s và thời gian lưu trú trung bình là 0,15 s: số request trung bình đang xử lý/chờ trong phạm vi này xấp xỉ **18**. Nếu vẫn giữ 120 req/s nhưng W tăng lên 0,8 s, L xấp xỉ **96**. Đây là dấu hiệu cần điều tra queue, dependency hoặc xử lý chậm.

Không lấy p95 thay cho **W trung bình** trong công thức Little. Cũng không áp dụng công thức một cách máy móc cho giai đoạn overload khi hàng đợi đang tăng không ngừng hoặc dữ liệu đo có request thất bại bị loại ra.

### 6.1. Quy luật hàng đợi và điểm gãy

Khi nhu cầu tiến sát capacity, thời gian đợi thường tăng nhanh và trở nên biến động, dù throughput không tăng tương ứng. Với workload có nhiều variability, queueing effect có thể xuất hiện trước khi CPU đạt 100%.

Ví dụ:
- Tải 50 req/s: p95 100 ms, CPU 30%, lỗi thấp.
- Tải 120 req/s: p95 180 ms, CPU 70%, lỗi thấp.
- Tải 150 req/s: p95 900 ms, CPU 85%, thread pool pending tăng.
- Tải 180 req/s: successful throughput chỉ 155 req/s, p95 vài giây, timeout tăng.

Các giá trị trên là minh họa, không phải giới hạn mặc định của service. Dấu hiệu quan trọng là **successful throughput ngừng tăng** đồng thời queue, latency hoặc lỗi tăng mạnh.

## 7. Đo mức sử dụng tài nguyên và độ bão hòa

### 7.1. CPU: cores, quota và throttling

CPU có thể đo theo CPU seconds/s, tương đương số core đang được dùng. Ví dụ service sử dụng 0,7 CPU seconds mỗi giây thì tương đương khoảng **0,7 core** trong cửa sổ đó.

Một truy vấn minh họa từ container metrics:

~~~promql
sum by (pod) (
  rate(container_cpu_usage_seconds_total{
    namespace="production",
    container="catalog"
  }[5m])
)
~~~

Kết quả xấp xỉ số core CPU tiêu thụ trên từng pod, không phải phần trăm nếu chưa chia cho năng lực hoặc limit phù hợp. Với Kubernetes, CPU request, CPU limit và hiệu quả scheduler có ý nghĩa khác nhau:
- **Request:** tài nguyên được dùng cho quyết định scheduling và một số cơ chế phân chia.
- **Limit:** trần tài nguyên có thể dẫn tới CFS throttling.
- **Usage:** số CPU thực tế dùng.
- **Throttling:** thời gian/chù kỳ workload bị giới hạn dù còn nhu cầu xử lý.

CPU 60% của limit không tự nói lên CPU còn 40% capacity hữu ích; bottleneck có thể nằm ở một thread, lock hoặc cgroup throttling. Quan sát thêm CPU usage theo container, số thread bận, run queue và latency.

### 7.2. Bộ nhớ: heap, RSS, working set và OOM

Trong ứng dụng Java:
- **JVM heap used:** vùng heap đang được đối tượng sử dụng.
- **Heap committed/max:** dung lượng JVM đã commit và trần cấu hình, có thể khác container memory limit.
- **Non-heap/direct/native memory:** metaspace, thread stacks, direct buffers, thư viện native.
- **Container working set/RSS:** góc nhìn hệ điều hành về bộ nhớ hoạt động, không đồng nhất với heap.
- **GC pause và allocation rate:** chỉ dấu áp lực cấp phát/thu gom.
- **OOMKilled/restarts:** tín hiệu đã chạm giới hạn hoặc lỗi bộ nhớ.

Một service có heap 50% nhưng memory working set gần limit vẫn có thể bị OOM do native allocations, direct buffers, số thread lớn hoặc phần bộ nhớ khác. Ngược lại, heap used cao chưa đủ để kết luận memory leak: cần xem sau GC, phân bổ theo thời gian và profile khi cần.

Nên đo đồng thời heap, non-heap, container memory, số lần restart, GC pause, allocation rate và throughput để biết tăng tài nguyên có thật sự cải thiện năng lực xử lý hay không.

### 7.3. Database và connection pool

Microservice có thể bị giới hạn bởi connection pool ngay cả khi CPU thấp. Những metric hữu ích:
- Active connections, idle connections, max connections.
- Pending acquire requests, acquire wait time.
- Query latency p95/p99, số truy vấn đang chờ.
- Database CPU, I/O, lock waits, slow query, connection cap.
- Transaction duration và tỷ lệ deadlock/retry.

Ví dụ pool tối đa 20 kết nối đã có 20 active, pending acquire liên tục tăng, p95 của API tăng nhưng CPU ứng dụng chỉ 25%. Tăng số replica có thể làm **tổng số kết nối tranh chấp database cao hơn**, khiến tình hình xấu đi. Cần tối ưu query, index, transaction length, pool sizing và năng lực database trước khi tùy tiện scale service.

### 7.4. Thread pool và executor

Với server xử lý blocking hoặc worker executor:
- Active threads / configured max.
- Queue depth / queue capacity.
- Task wait time, rejection count.
- Task execution time.
- Lock contention và blocked thread.

Queue không giới hạn có thể giữ throughput hiển thị ổn trong thời gian đầu nhưng tạo backlog và memory pressure. Queue có giới hạn, admission control và backpressure thường giúp hệ thống thể hiện lỗi sớm, bảo vệ những request đã nhận.

### 7.5. Message broker

Với Kafka hay broker tương đương, quan sát producer rate, consumer processing rate, lag theo partition/consumer group, retry, rebalance, batch size và thời gian chờ. Lag tăng khi inbound lớn hơn capacity xử lý trong thời gian dài.

Không coi lag đơn vị “số message” và tuổi message là cùng một metric: 1.000 message nhỏ có thể dễ xử lý hơn 50 message lớn; latency thực tế cần đo từ thời điểm event được ghi/được tạo tới lúc hoàn thành, có quản lý đồng hồ và timestamp đúng nguồn.

### 7.6. Disk, network và external dependencies

Các nút thắt khác gồm:
- Disk IOPS, throughput, latency, queue depth, available space.
- Network throughput, TCP retransmission, connection errors.
- DNS/connect/TLS time cho outbound calls.
- Rate limiting, 429, quota từ dịch vụ ngoài.
- Cache hit ratio và latency khi cache miss.
- Service mesh/proxy CPU, queue và timeout.

Nếu một API chậm do upstream quota, scale thêm pod có thể tăng lượng request bị từ chối. Cần phân biệt service đang thiếu năng lực xử lý với phụ thuộc ngoài đang giới hạn lưu lượng.

## 8. Từ RED và USE đến một dashboard có ích

Hai cách tiếp cận bổ trợ:

**RED** (Rate, Errors, Duration): tập trung dịch vụ phục vụ request. Đo tốc độ request, lỗi và phân phối duration theo service/route.

**USE** (Utilization, Saturation, Errors): tập trung tài nguyên. Đo mức sử dụng, áp lực chờ và lỗi tài nguyên của CPU, RAM, network, disk, connection pool, thread pool.

Một dashboard theo microservice có thể chia:

| Nhóm bảng | Các biểu đồ nên có |
| --- | --- |
| Trải nghiệm/SLI | Request rate, success rate, p50/p95/p99, SLO compliance |
| Traffic | Request/s theo route, method, region, version; request size |
| Errors | 5xx/s, timeout/s, rejected/s, retry rate, lỗi nghiệp vụ |
| CPU | Cores sử dụng, request/limit, throttling, restarts |
| Memory/GC | Heap, working set, pause GC, allocation, OOM |
| Dependencies | Database query latency, pool pending, outbound RPC, cache hit |
| Asynchronous | Message arrival/process rate, consumer lag, event age |
| Release | Thời điểm deploy, image digest, config revision, canary ratio |

Mỗi panel phải hiển thị đúng **environment**, **service**, **version**, **region**, phạm vi thời gian và đơn vị. Tránh trình bày p99 không có số lượng mẫu hoặc vẽ hai trục với đơn vị khác nhau mà không ghi chú.

**Một dashboard dùng để triage**, không nhất thiết thay thế mọi dashboard chuyên sâu. Khi phát hiện điểm gãy, chuyển sang trace, database performance view hoặc profiler để xác nhận nguyên nhân.

## 9. Instrumentation trong ứng dụng Java/Spring Boot

Với Spring Boot, Micrometer và Actuator là lựa chọn phổ biến để xuất metric. Việc thêm registry (ví dụ Prometheus), mở endpoint nội bộ và cấu hình collector cần tuân thủ bảo mật của từng môi trường.

Mẫu cấu hình mang tính minh họa:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  metrics:
    tags:
      application: catalog-service
~~~

Cần bổ sung dependency actuator và registry tương ứng theo cách dự án đang tổ chức, đồng thời bảo vệ endpoint; không mặc định công khai prometheus actuator ra internet.

Với HTTP server, Micrometer có thể cung cấp metric duration theo route/status. Tên metric ở ứng dụng có thể là dạng dấu chấm, khi export sang Prometheus được chuẩn hóa theo naming convention và đơn vị, ví dụ các series có hậu tố _seconds_count hoặc _seconds_bucket. Phải **xem metric được export thật** trước khi copy PromQL vào dashboard.

### 9.1. Đo thời gian xử lý một thao tác nghiệp vụ

Ví dụ đo một đường xử lý riêng bằng Micrometer Timer.Sample:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class PriceLookupService {
    private final MeterRegistry registry;
    private final PricingClient pricingClient;

    public PriceLookupService(MeterRegistry registry, PricingClient pricingClient) {
        this.registry = registry;
        this.pricingClient = pricingClient;
    }

    public Price lookup(String productId) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";
        try {
            return pricingClient.fetchPrice(productId);
        } catch (RuntimeException ex) {
            outcome = "failure";
            Counter.builder("catalog.price_lookup.errors")
                .tag("reason", "dependency_error")
                .register(registry)
                .increment();
            throw ex;
        } finally {
            Timer.builder("catalog.price_lookup.duration")
                .tag("outcome", outcome)
                .publishPercentileHistogram()
                .register(registry);
            sample.stop(registry.timer(
                "catalog.price_lookup.duration",
                "outcome", outcome
            ));
        }
    }
}
~~~

Đoạn trên minh họa cách khởi động và dừng sample ở mọi kết quả; class PricingClient và Price là thành phần giả định cần dự án cung cấp. Trong triển khai thực, nên **khai báo cấu hình histogram trên meter tương ứng** thay vì tạo Timer.builder không được dùng để stop như trong ví dụ. Cách gọn và nhất quán hơn là giữ một Timer hoặc sử dụng MeterFilter/distribution configuration ở cấp registry và gọi sample.stop trên chính meter đã cấu hình. Điều này tránh hiểu sai rằng gọi builder riêng tự thay đổi timer của cùng tên ở dòng tiếp theo.

Ví dụ thay thế phần finally nếu đã cấu hình histogram cho metric bằng MeterFilter:

~~~java
finally {
    Timer timer = registry.timer(
        "catalog.price_lookup.duration",
        "outcome", outcome
    );
    sample.stop(timer);
}
~~~

Chú ý không dùng productId làm nhãn metric. Mỗi ID tạo một series mới và có thể làm nghẽn time-series database. Nếu cần truy theo productId, dùng logs/traces với chính sách bảo mật phù hợp.

### 9.2. Tag có cardinality thấp

Nhãn nên giữ số giá trị hữu hạn, ví dụ:
- service, environment, region, version.
- method, route template, outcome, status code/nhóm status.
- dependency name, operation type, consumer group (nếu được quản lý).

Tránh:
- userId, productId, orderId.
- full URL có query string.
- requestId, traceId trong metric labels.
- exception message không chuẩn hóa.
- tenant ID có số lượng không kiểm soát.

Metric có cardinality cao làm tăng chi phí lưu trữ, chậm query và có thể làm mất tín hiệu đúng lúc sự cố.

### 9.3. Dùng trace để giải thích độ trễ

Một trace đầu cuối có thể gồm:
- API Gateway: 20 ms.
- order-service: xử lý tổng 400 ms.
- inventory-service: gọi outbound 260 ms.
- Database inventory: query 220 ms.
- Serialization và network: phần còn lại.

Các span có thể lồng nhau, **không cộng bừa tất cả duration** vì thời gian của parent thường đã bao gồm child. Trace cho biết đường đi critical path, chỗ đợi, retry và downstream bottleneck. Metric cho biết xu hướng và quy mô; trace cho biết cấu trúc của một lần thực thi.

Sampling có thể làm traces không đại diện đầy đủ cho toàn bộ request, nhất là tail latency hiếm gặp. Không lấy phân vị từ một số ít trace đã lấy mẫu tùy ý rồi coi là latency toàn service. Dùng metric histogram làm tín hiệu thống kê chính và trace để điều tra.

## 10. Truy vấn PromQL tham khảo

Các ví dụ giả định metric Prometheus classic histogram được export bởi ứng dụng và có label như job, uri, status. Cần thay tên metric/label bằng dữ liệu quan sát thực tế. Mỗi truy vấn phải chọn cùng môi trường và tập instance cần đánh giá.

**Tổng request/s của catalog:**

~~~promql
sum(rate(http_server_requests_seconds_count{
  job="catalog-service"
}[5m]))
~~~

**Tỷ lệ lỗi HTTP 5xx:**

~~~promql
sum(rate(http_server_requests_seconds_count{
  job="catalog-service",
  status=~"5.."
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    job="catalog-service"
  }[5m])),
  0.000001
)
~~~

**Độ trễ p95 theo operation:**

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{
      job="catalog-service"
    }[5m])
  )
)
~~~

**Average request duration (giây) theo toàn service:**

~~~promql
sum(rate(http_server_requests_seconds_sum{
  job="catalog-service"
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    job="catalog-service"
  }[5m])),
  0.000001
)
~~~

**JVM heap used (byte), cộng các memory pool:**

~~~promql
sum by (job) (
  jvm_memory_used_bytes{
    job="catalog-service",
    area="heap"
  }
)
~~~

**CPU cores trên từng pod:**

~~~promql
sum by (pod) (
  rate(container_cpu_usage_seconds_total{
    namespace="production",
    container="catalog"
  }[5m])
)
~~~

**Ví dụ ghi chú khi dựng dashboard:** Truy vấn chia sử dụng clamp_min để tránh phép chia cho 0 khi không có request, nhưng khi đó kết quả có thể bị hiểu nhầm là tỷ lệ có dữ liệu. Dashboard production cần bổ sung điều kiện tối thiểu về request count hoặc biểu thị trạng thái “không đủ mẫu”, thay vì coi vùng không có traffic là SLI tốt.

Các metric Kubernetes/container có thể đến từ cAdvisor/kubelet, metrics server hoặc collector tùy cluster. Cấu hình label của cluster không mặc định giống mọi ví dụ. Phần PromQL nhằm minh họa phép biến đổi và ý nghĩa thống kê, không thay thế việc khám phá series thực tế.

## 11. Đo end-to-end qua nhiều service

Một hành trình đặt hàng có thể là:

~~~text
Client → API Gateway → order-service → inventory-service → database
                       |
                       +→ payment-service → external payment gateway
                       |
                       +→ message broker → notification-service
~~~

Có ít nhất bốn lát cắt:
1. **Client-side:** thời gian người dùng chờ tạo đơn; bao gồm gateway và mạng.
2. **Order API:** request duration tới khi trả kết quả nhận đơn; có thể chưa gửi thông báo xong.
3. **Dependency:** thời gian inventory, payment và database; cần nhìn call rate, timeout/retry.
4. **Async completion:** thời gian từ event phát hành tới thông báo được xử lý thành công.

Nếu order API trả 202 Accepted sau 30 ms nhưng job phía sau mất 15 phút, API latency tốt chưa chứng minh yêu cầu nghiệp vụ hoàn tất đúng hạn. Cần đo **business completion latency** từ thời điểm chấp nhận đến trạng thái kết thúc.

Khi xác định SLO, hãy phân biệt:
- **Synchronous SLI:** thời gian và kết quả request đồng bộ.
- **Asynchronous SLI:** độ tuổi công việc, tỷ lệ hoàn thành trong deadline và backlog.
- **Business SLI:** đơn hàng hoàn tất, thanh toán được xác nhận, tồn kho nhất quán.

Cần tránh đếm một giao dịch hai lần khi đã có retry hoặc compensating transaction. Liên kết metric với trace/log bằng service, version, environment và correlation identifier trong hệ thống quan sát, không đưa toàn bộ correlation ID thành label metric.

## 12. Thu thập và duy trì tính tin cậy của phép đo

Pipeline quan sát có thể gồm ứng dụng xuất metric → collector/scraper → time-series database → dashboard/alert. Mỗi tầng đều có rủi ro:

- Scrape interval quá thưa làm mất peak ngắn.
- Exporter restart làm counter reset; truy vấn raw counter gây kết luận sai.
- Clock skew khiến timestamp span hoặc event age sai.
- Collector quá tải làm mất metric hoặc trace.
- Sampling thiếu điều kiện tạo sai lệch tail latency.
- Cardinality cao làm tăng ingestion/cost và chậm query.
- Label không thống nhất khiến aggregation trộn các service hoặc môi trường khác nhau.
- Metric ghi chỉ ở luồng thành công, bỏ qua timeout và exception.
- Các endpoint được expose rộng có thể tiết lộ thông tin nội bộ.

Quy trình triển khai instrument:
1. Định nghĩa tên metric, type, đơn vị và nhãn.
2. Định nghĩa điểm bắt đầu/kết thúc mỗi phép đo và cách xử lý lỗi.
3. Ghi nhận metric theo hành vi runtime thực.
4. Xác thực series được export ở non-production.
5. Tạo dashboard với cửa sổ và aggregation đúng.
6. Tạo alert theo SLO và impact, không theo một ngưỡng ngẫu nhiên.
7. Đo overhead của instrumentation và collector.
8. Theo dõi tình trạng của chính pipeline observability.

Giữ sự tương thích khi đổi tên metric, vì dashboard và alert có thể phụ thuộc tên cũ. Các histogram bucket và nhãn cũng là một phần của hợp đồng observability cần quản lý khi sửa đổi.

## 13. Thiết kế load test để đánh giá năng lực mở rộng

Mục tiêu load test là trả lời: ở mức offered load nào hệ thống bắt đầu không đáp ứng SLO, vì tài nguyên hoặc dependency nào, và thay đổi capacity có giúp cải thiện hay không?

### 13.1. Mô hình tải

**Closed workload:** một số user ảo cố định gửi request, thường bắt đầu vòng sau khi vòng trước xong. Khi latency tăng, tốc độ tạo request có thể tự giảm. Nếu không nhận diện đặc điểm này, test có thể che giấu bão hòa.

**Open workload:** tải tới theo một tốc độ đặt trước, ít phụ thuộc tốc độ phản hồi; phù hợp kiểm tra capacity trước arrival rate cụ thể và phát hiện backlog, miễn máy phát tải đủ năng lực và bộ đo ghi đúng sự kiện.

Nên chọn mô hình phản ánh hành vi thật, hoặc dùng cả hai để thấy sự khác biệt. Tình huống tải thường gồm:
- **Baseline:** tốc độ vận hành thường ngày.
- **Ramp-up:** tăng dần tới tải mục tiêu.
- **Stress:** vượt năng lực để tìm điểm gãy và cơ chế bảo vệ.
- **Spike:** tăng đột ngột trong thời gian ngắn.
- **Soak:** duy trì tải trong nhiều giờ để thấy leak, GC, pool exhaustion.
- **Recovery:** giảm tải và quan sát queue, latency, memory có hồi phục không.

### 13.2. Trước khi chạy test

Chốt môi trường, image digest, config revision, database size, dataset, phiên bản dependency và topology. Kiểm tra dữ liệu test không gây side effect ngoài môi trường; xác nhận load generator, network và collector đủ khả năng đo.

Chạy warm-up nếu muốn đo trạng thái ổn định, nhất là ứng dụng Java có JIT, cache, connection pools. Báo cáo phải ghi rõ có loại warm-up khỏi kết quả hay không, và không dùng các lần chạy khác nhau về traffic mix để so sánh trực tiếp.

### 13.3. Ví dụ k6: giữ arrival rate mục tiêu

~~~javascript
import http from "k6/http";
import { check } from "k6";

export const options = {
  scenarios: {
    catalog_steady: {
      executor: "constant-arrival-rate",
      rate: 80,
      timeUnit: "1s",
      duration: "5m",
      preAllocatedVUs: 100,
      maxVUs: 300
    }
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500"]
  }
};

export default function () {
  const response = http.get(
    __ENV.BASE_URL + "/api/products/sample-product",
    { tags: { operation: "product_lookup" } }
  );
  check(response, {
    "request returned 200": (r) => r.status === 200
  });
}
~~~

Ví dụ trên giả định environment variable BASE_URL trỏ đến một endpoint **test/staging được phép tải**, và sample-product là fixture tồn tại. Các ngưỡng 1% lỗi, p95 500 ms và arrival rate 80 req/s chỉ để minh họa, cần thay bằng SLO và yêu cầu capacity thực tế. Không dùng script để bắn tải vào production nếu chưa có kế hoạch và thẩm quyền vận hành phù hợp.

**Điểm đọc kết quả:** k6 có thể cho thấy iteration không được lên lịch đúng tốc độ mong muốn nếu thiếu VU hoặc máy phát tải bão hòa. Phải kiểm tra requested rate so với actual rate, dropped iterations, CPU/network máy tạo tải và tỷ lệ lỗi. Nếu bộ phát không đủ sức phát request, không thể dùng kết quả để kết luận backend chịu tải tốt.

Thời gian http_req_duration của k6 phản ánh những thành phần cụ thể của giai đoạn HTTP request; nó không đồng nghĩa toàn bộ thời gian browser render hay transaction end-to-end. Khi cần đo trải nghiệm người dùng, kết hợp synthetic/browser telemetry hoặc RUM.

### 13.4. Một lần test nên lưu gì?

Tối thiểu:
- Mục tiêu, workload model và traffic mix.
- Image digest, config revision, data volume, replica count, CPU/memory request/limit.
- Ngày giờ và duration của từng giai đoạn tải.
- Offered load, completed throughput, successful throughput, error rate.
- p50/p95/p99 client latency và server latency.
- CPU cores/quota/throttling, memory/GC, DB pool, broker lag, network.
- Các sự kiện scaling, deployment, restart, GC bất thường.
- Kết luận điểm bắt đầu vi phạm SLO và evidence nguyên nhân.

Không chỉ lưu một ảnh dashboard cuối. Kết quả có giá trị khi còn đủ thông tin để lặp lại thử nghiệm và đối chiếu những thay đổi sau này.

## 14. Phân tích ví dụ: dịch vụ bắt đầu bão hòa

Giả sử một chạy thử catalog-service giữ số pod ở mức 3, dữ liệu và cấu hình không đổi:

| Offered load | Successful throughput | p95 latency | Error rate | CPU / pod | Pool pending |
| --- | --- | --- | --- | --- | --- |
| 60 req/s | 60 req/s | 90 ms | 0,1% | 28% | 0 |
| 120 req/s | 119 req/s | 130 ms | 0,3% | 52% | 0 |
| 180 req/s | 176 req/s | 240 ms | 0,8% | 73% | 2 |
| 220 req/s | 195 req/s | 900 ms | 8,0% | 78% | 40 |
| 260 req/s | 197 req/s | 2.300 ms | 18,0% | 80% | 105 |

*Toàn bộ số liệu trên là minh họa, không phản ánh một hệ thống thực tế.*

Từ bảng có thể quan sát:
- Ở 60–180 req/s, throughput vẫn theo gần offered load và latency tăng vừa phải.
- Từ 220 req/s, successful throughput gần chững lại trong khi p95 và lỗi tăng mạnh.
- Pool pending tăng nhanh là tín hiệu cần xem database query, pool size và thời gian chờ.
- CPU ~80% có thể có áp lực nhưng **chưa đủ bằng chứng** CPU là bottleneck chính.

Hướng điều tra:
1. So trace để xác định latency ở handler, database hay downstream call.
2. Kiểm tra connection acquire wait, query time, locks, transaction scope.
3. Xem request mix có thay đổi theo tải hay không.
4. Kiểm tra timeout, retry amplification và việc các request lỗi có được tính.
5. Tối ưu nút thắt rồi chạy lại cùng kịch bản; nếu cần thêm replica, phải kiểm tra tổng connection cap của database.

Nếu p95 mục tiêu là 300 ms và tỷ lệ lỗi tối đa 1%, capacity thực nghiệm của cấu hình trên chỉ có thể báo cáo theo tải đã **quan sát đủ điều kiện**, ví dụ 180 req/s ở kịch bản này. Không suy ra có thể phục vụ ổn định 200 req/s chỉ vì successful throughput đỉnh đạt 197 req/s trong một lần thử.

## 15. Đo hiệu quả horizontal scaling

**Horizontal scaling** thêm hoặc bớt instance. Một phép thử cơ bản giữ workload và cấu hình không đổi, chỉ thay replica count:

| Replica | Offered load | Successful throughput | p95 | CPU tổng | DB connections |
| --- | --- | --- | --- | --- | --- |
| 1 | 100 req/s | 95 req/s | 480 ms | 0,9 core | 12 |
| 2 | 100 req/s | 100 req/s | 180 ms | 1,1 core | 22 |
| 4 | 100 req/s | 100 req/s | 150 ms | 1,4 core | 38 |

Đây là ví dụ minh họa. Thêm instance cải thiện độ trễ ở cùng tải, nhưng không nhất thiết tăng throughput khi offered load vẫn là 100 req/s. Muốn đo capacity tăng bao nhiêu, cần nâng offered load theo từng cấu hình và tìm tải cao nhất vẫn đáp ứng SLO.

Có thể dùng **scale efficiency** theo capacity đạt SLO:

**E = (capacity_N / capacity_1) / N**

Nếu 1 replica chịu được 100 req/s và 4 replica chịu được 320 req/s ở cùng ngưỡng SLO, hiệu suất mở rộng tương đối là (320/100)/4 = **0,80**. Đây là một cách so sánh gần đúng; cần giữ dataset, giới hạn dependency và workload tương đương. Nếu database trở thành shared bottleneck thì hiệu quả sẽ suy giảm khi thêm replica.

Một dịch vụ không stateful vẫn có thể gặp rào cản mở rộng từ:
- Database write lock hoặc connection cap.
- Cache hot key, cold cache sau scaling.
- Broker partition count hoặc consumer group limits.
- API rate limit của bên thứ ba.
- Distributed lock và giao dịch đồng bộ.
- Hàng đợi hay coordinator tập trung.

Vì vậy, đo cả dịch vụ **và** shared resources khi đánh giá khả năng mở rộng.

## 16. Autoscaling: chọn đúng tín hiệu và cửa sổ

HPA/KEDA hoặc hệ thống autoscaling khác có thể scale dựa trên CPU, memory, request rate, concurrency, queue depth hoặc consumer lag. Một metric hữu ích phải có quan hệ đủ rõ với nhu cầu năng lực và có thể đo ổn định.

**CPU-based:** hợp lý với workload CPU-bound, nhưng có thể phản ứng sai khi app chờ database. CPU utilization cũng phải hiểu theo CPU request/limit, không nhầm với % node.

**Request rate per replica:** có thể hữu ích khi chi phí xử lý mỗi request tương đối đồng nhất. Nếu request mix biến thiên mạnh, cần phân loại theo operation hoặc bổ sung latency/error metrics.

**In-flight requests/concurrency:** gần với nhu cầu đồng thời, thích hợp cho một số gateway/server, nhưng cần giới hạn thread, pool, memory và cách instrument.

**Queue length/consumer lag:** thường hữu ích với worker async, nhưng cần ước lượng processing rate, độ tuổi công việc, throughput và giới hạn của broker.

Một công thức trực giác cho điều khiển tỷ lệ là:

**desiredReplicas ≈ ceil(currentReplicas × currentMetric / targetMetric)**

Đây chỉ là nguyên lý tỷ lệ cơ bản; thuật toán thực tế còn có stabilization window, tolerance, min/max replicas, lịch sử metric, scale-up/down policies và độ trễ startup. Không xem công thức này là toàn bộ cách hoạt động của Kubernetes HPA.

Rủi ro khi autoscale:
1. Scale quá muộn: request đã timeout trước khi pod mới ready.
2. Scale lên gây stampede: nhiều pod cùng mở database connections, làm DB quá tải.
3. Scale dao động: metric ngắn hạn hoặc cache warm-up tạo tăng/giảm liên tục.
4. Scale theo metric không có ý nghĩa: memory cao do cache không hẳn là tín hiệu tải cần thêm pod.
5. Cạn quota/cluster capacity: autoscaler muốn thêm pod nhưng không schedule được.
6. Không scale được shared dependency: pod tăng nhưng database hoặc third-party quota không đổi.

Thiết kế autoscaling nên đi kèm queue/backpressure, readiness, startup time, resource limits, headroom, max capacity và cảnh báo khi scale không đạt mục tiêu.

## 17. SLO, error budget và cảnh báo

**SLI (Service Level Indicator)** là chỉ số quan sát như tỷ lệ request đáp ứng được điều kiện hoặc độ trễ. **SLO (Service Level Objective)** là mục tiêu định lượng trên SLI trong một cửa sổ. **Error budget** là lượng sai lệch còn được chấp nhận theo SLO.

Ví dụ minh họa cho API xem sản phẩm:
- Availability SLI: tỷ lệ request hợp lệ được phản hồi đúng theo tiêu chí thành công.
- Latency SLI: tỷ lệ request hợp lệ được hoàn thành trong 300 ms, đo tại gateway.
- SLO: 99,9% số request thỏa điều kiện availability trong 30 ngày.
- Có thể có SLO riêng cho latency, không đánh đồng với availability.

Với 1.000.000 request hợp lệ trong kỳ và mục tiêu 99,9% thành công, error budget theo số request là **1.000 request**. Đây là số minh họa theo cách đếm request; error budget thực tế phụ thuộc định nghĩa SLI, loại request và chính sách loại trừ.

Cảnh báo nên dựa trên:
- Burn rate của error budget qua nhiều cửa sổ.
- p95/p99 vượt ngưỡng SLO kèm lượng mẫu đủ.
- Successful throughput giảm trong khi arrival rate không giảm.
- Queue/lag tăng cùng tuổi công việc vượt deadline.
- Pool pending, CPU throttling, memory/OOM hoặc restart có tác động tới người dùng.

Không nên page on-call chỉ vì CPU 80% trong 30 giây nếu service vẫn ổn định và workload đã thiết kế sử dụng CPU cao. Có thể dùng cảnh báo dự báo capacity hoặc ticket cho xu hướng dài hạn; paging ưu tiên dấu hiệu tác động người dùng cần phản ứng ngay.

## 18. Những lỗi đo lường phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chỉ xem latency trung bình | Che giấu tail latency | Xem p50/p95/p99 và count |
| Cộng hoặc lấy trung bình các p99 | Phân vị không cộng gộp | Gộp histogram rồi tính quantile |
| Chỉ đếm HTTP 2xx | Bỏ sót lỗi, timeout, tác vụ chưa hoàn thành | Đếm cả arrival, completion, failure, retry |
| Dùng RPM nhưng đọc thành RPS | Lệch 60 lần | Ghi đơn vị trên mọi panel |
| Đếm message received là message succeeded | Retry/duplicate làm thổi phồng hiệu quả | Định nghĩa successful processing riêng |
| Dùng CPU % mà không rõ denominator | Lẫn node, request và container limit | Ghi CPU cores/quota và throttling |
| Chỉ theo dõi heap | Bỏ sót direct memory và native allocations | Đo container memory và JVM memory |
| Lấy p99 từ quá ít mẫu | Giá trị rất nhiễu | Hiển thị sample count và cửa sổ |
| Dùng full URL/user ID làm label | Cardinality bùng nổ | Dùng route template và nhãn hữu hạn |
| Bỏ request timeout khỏi timer | Hệ thống lỗi lại có biểu đồ latency đẹp | Instrument tất cả outcome |
| Load generator không đạt rate | Đánh giá sai capacity | Đo offered/actual rate và dropped iterations |
| Scale thêm pod khi database bão hòa | Tăng pressure lên điểm nghẽn | Đo dependency và thử thay đổi có kiểm soát |
| So sánh test khác workload | Không xác định được tác động tối ưu | Cố định scenario, data, config và window |
| Bỏ qua version/environment labels | Trộn before/after và staging/prod | Gắn nhãn release và phạm vi thống nhất |

## 19. Quy trình thực hành từng bước

Một nhóm muốn đánh giá catalog-service có đáp ứng kế hoạch tăng trưởng cần đi theo quy trình:

**Bước 1 — Chốt SLO và workload.** Xác định sản phẩm cần phục vụ bao nhiêu req/s ở giờ cao điểm, các route phổ biến, phân bố payload và ngưỡng latency/error.

**Bước 2 — Đảm bảo đo đúng.** Bật request counters, duration histograms, outcome labels, traces, CPU/memory, GC, DB pool, queue và network. Kiểm tra export thực tế và dashboard theo service/environment/version.

**Bước 3 — Đo baseline.** Chạy tải hiện tại đủ thời gian, ghi artifact digest, dataset, replica count và kết quả p50/p95/p99, success throughput, error rate, resource utilization.

**Bước 4 — Tăng offered load.** Thực hiện ramp-up rồi steady state ở từng mốc. Theo dõi successful throughput cùng latency, errors, queue, pool và CPU. Đánh dấu điểm bắt đầu vi phạm SLO.

**Bước 5 — Khoanh vùng bottleneck.** Dựa trên trace và metric resource: CPU-bound, GC/memory, connection pool, query/lock, network, broker lag hay external quota. Tránh kết luận chỉ từ một biểu đồ.

**Bước 6 — Thử thay đổi có kiểm soát.** Có thể tăng replica, tối ưu query, thêm index, điều chỉnh thread/pool, caching, giảm fan-out hoặc xử lý async. Mỗi lần thay một biến chính để nhận biết tác dụng.

**Bước 7 — So sánh lại.** Chạy cùng workload và dữ liệu, đánh giá capacity đạt SLO, chi phí, độ ổn định, lỗi và thời gian phục hồi khi tải giảm.

**Bước 8 — Kết nối với vận hành.** Chuyển kết quả thành capacity baseline, autoscaling policy, alert, dashboard, runbook và kế hoạch test định kỳ trước thay đổi lớn.

## 20. Bài tập áp dụng

Hệ thống gồm api-gateway, order-service, inventory-service và payment-service. Khi tải tăng, người dùng phản ánh checkout chậm. Dashboard có dữ liệu minh họa:

| Mốc tải | Arrival | Success throughput | Checkout p95 | CPU order | Pending DB acquire | Payment p95 |
| --- | --- | --- | --- | --- | --- | --- |
| A | 80 req/s | 79 req/s | 220 ms | 35% | 0 | 100 ms |
| B | 140 req/s | 137 req/s | 450 ms | 48% | 15 | 110 ms |
| C | 190 req/s | 152 req/s | 2.400 ms | 53% | 90 | 120 ms |

Câu hỏi:
1. Với dữ liệu trên, successful throughput có tăng tương ứng arrival rate ở mọi mốc không?
2. Vì sao chưa nên kết luận order-service bị nghẽn CPU?
3. Phép đo nào giúp chứng minh hoặc bác bỏ giả thuyết DB connection pool bão hòa?
4. Nếu order-service xử lý 100 req/s với thời gian lưu trú trung bình 250 ms trong trạng thái ổn định, concurrency trung bình trong phạm vi đo xấp xỉ bao nhiêu?
5. Hãy viết một truy vấn PromQL minh họa p95 latency theo route; giải thích vì sao không lấy trung bình p95 của các instance.
6. Khi tăng từ 2 lên 4 replica, metric nào của database có thể xấu đi ngay cả khi CPU ứng dụng giảm?
7. Hãy đề xuất một load test ramp-up và danh sách bằng chứng cần giữ để so sánh trước/sau tối ưu.
8. Nếu checkout API trả 202 sau 30 ms nhưng event hoàn tất đơn chờ 10 phút, cần bổ sung SLI nào?
9. Chọn điều kiện dừng canary khi release mới làm p99 tăng, nhưng sample count của route hiếm còn quá nhỏ.
10. Phân biệt thời gian xử lý event, event age và consumer lag trong một hệ thống hàng đợi.

Gợi ý cho câu 4: theo định luật Little, L = 100 × 0,25 = **25 công việc trung bình** đang ở trong phạm vi đo, với giả định hệ thống ổn định và các phép đo nhất quán.

Một phương án thực hành hoàn chỉnh phải xác định được **người dùng đang chịu tác động gì**, **service và dependency nào gây ra**, **chỉ số nào cho thấy giới hạn capacity**, và **sau thay đổi có cải thiện trong cùng điều kiện kiểm thử hay không**.

## 21. Ghi nhớ

- **Throughput** đo số công việc hoàn thành mỗi đơn vị thời gian; phải phân biệt offered load, completion rate và successful throughput.
- **Latency** là phân phối thời gian chờ; p95/p99 và count giúp nhìn tail latency tốt hơn một giá trị trung bình đơn lẻ.
- **Utilization và saturation** liên quan nhưng khác nhau; queue, throttling, connection pool và lag thường giải thích bottleneck mà CPU đơn lẻ không thể hiện.
- **Metric, trace và logs** bổ trợ: metric chỉ ra xu hướng, trace chỉ ra critical path, logs cung cấp ngữ cảnh sự kiện.
- **Đo theo service, route, environment, version và time window**; dùng nhãn có cardinality giới hạn.
- **Không cộng các percentiles**; với classic histogram, gộp bucket trước rồi dùng histogram_quantile.
- **Load test phải đo cả máy tạo tải** và có workload đại diện, điều kiện thực nghiệm lặp lại được.
- **Scale chỉ hiệu quả khi nút thắt thật sự được cải thiện**; thêm pod có thể làm quá tải tài nguyên dùng chung.
- **SLO gắn phép đo với trải nghiệm người dùng** và giúp biến dữ liệu thành quyết định phát hành, cảnh báo, tối ưu hay mở rộng.
