# Xây dựng dashboard theo lưu lượng, lỗi, độ trễ và độ bão hòa

Một dashboard vận hành tốt giúp đội ngũ trả lời nhanh bốn câu hỏi: hệ thống đang xử lý bao nhiêu công việc, có bao nhiêu công việc thất bại, người dùng phải chờ bao lâu và tài nguyên còn đủ khả năng đáp ứng tải hay không. Bốn nhóm tín hiệu này thường được gọi là **Four Golden Signals**: Traffic, Errors, Latency và Saturation.

Với workload compute trên cloud, dashboard cần nối được số liệu ở cấp ứng dụng với CPU, bộ nhớ, lưu trữ, mạng, hàng đợi và các dịch vụ phụ thuộc. Chỉ nhìn CPU của một VM không cho biết người dùng có gặp lỗi; chỉ nhìn tỷ lệ lỗi toàn dịch vụ có thể che giấu một instance hoặc một zone đang gặp vấn đề.

Sau bài học, bạn có thể:

- Giải thích và lựa chọn metric cho lưu lượng, lỗi, độ trễ và độ bão hòa.
- Thiết kế dashboard tổng quan và các màn hình drill-down theo service, instance, zone hoặc phiên bản.
- Tính request rate, error rate và latency percentile từ dữ liệu metric phù hợp.
- Kết hợp tín hiệu ứng dụng với CPU, RAM, disk, network và queue để tìm nút thắt.
- Đặt ngưỡng cảnh báo theo SLO và mức ảnh hưởng, tránh cảnh báo chỉ dựa vào một con số tùy ý.
- Tránh cardinality cao, aggregation sai và các biểu đồ dễ gây hiểu nhầm.

## 1. Bốn tín hiệu vàng của hệ thống

Four Golden Signals được dùng để quan sát dịch vụ từ góc nhìn người dùng và khả năng phục vụ của hệ thống.

| Tín hiệu | Câu hỏi | Metric tiêu biểu |
|---|---|---|
| Traffic (lưu lượng) | Có bao nhiêu công việc đang đi vào hoặc được xử lý? | Request/second, transaction/second, message throughput, concurrent requests, bytes in/out |
| Errors (lỗi) | Bao nhiêu công việc thất bại hoặc không đáp ứng kết quả mong đợi? | Error count, error rate, HTTP 5xx, timeout, failed job, retry và exception rate |
| Latency (độ trễ) | Một request hoặc công việc mất bao lâu? | p50, p90, p95, p99 response time; queue wait; dependency latency |
| Saturation (độ bão hòa) | Tài nguyên hoặc hàng đợi đang gần giới hạn đến đâu? | CPU, memory pressure, disk I/O, network capacity, connection pool, queue depth và throttling |

Bốn tín hiệu cần được xem cùng nhau. Traffic tăng có thể là tăng trưởng bình thường hoặc một đợt tấn công. Latency tăng có thể do CPU bão hòa, database chậm hoặc dependency bên ngoài. CPU cao không nhất thiết là sự cố nếu throughput vẫn tăng, latency nằm trong SLO và còn đủ headroom.

    Traffic ─┐
    Errors ──┼──> Đánh giá sức khỏe dịch vụ ──> Dashboard tổng quan
    Latency ─┤                               └─> Drill-down và hành động
    Saturation┘

## 2. Xác định phạm vi và người dùng dashboard

Trước khi tạo panel, hãy xác định dashboard phục vụ ai và quyết định nào cần được đưa ra.

- **Dashboard điều hành/on-call:** cần cho biết dịch vụ có đang ảnh hưởng người dùng không, mức độ nghiêm trọng, thành phần nào bất thường và liên kết đến runbook.
- **Dashboard của đội ứng dụng:** cần drill-down theo route, operation, dependency, phiên bản và kết quả triển khai.
- **Dashboard hạ tầng:** cần xem CPU, RAM, disk, network, instance, node, zone, quota và mức sử dụng theo thời gian.
- **Dashboard năng lực/chi phí:** cần thấy xu hướng traffic, utilization, số instance, headroom và chi phí theo workload.

Một dashboard không nên cố hiển thị mọi metric của mọi hệ thống trên cùng một màn hình. Trang tổng quan cần giúp nhận diện vấn đề trong vài giây; các trang chi tiết phục vụ điều tra nguyên nhân.

### Chọn đơn vị quan sát

Đối với ứng dụng chạy trên nhiều VM hoặc Pod, cần quan sát ở nhiều cấp:

1. **Service/fleet:** tổng traffic, error rate, latency và saturation của toàn dịch vụ.
2. **Instance/Pod:** phát hiện một máy riêng lẻ có CPU cao, OOM, lỗi hoặc latency khác biệt.
3. **Zone/region/node pool:** phát hiện sự cố tập trung theo miền lỗi hoặc nhóm hạ tầng.
4. **Operation/route:** xác định endpoint hoặc tác vụ nào chậm, lỗi hay tiêu thụ nhiều tài nguyên.
5. **Dependency:** đo thời gian và tỷ lệ lỗi khi gọi database, cache, queue hoặc API bên ngoài.

Luôn giữ một biểu đồ tổng hợp để biết tác động toàn dịch vụ, rồi cung cấp liên kết hoặc bộ lọc để xem các chiều chi tiết. Không dùng biểu đồ từng instance thay cho biểu đồ service vì số lượng instance có thể thay đổi khi autoscaling.

## 3. Thiết kế dashboard Traffic

Traffic cho biết tốc độ và khối lượng công việc hệ thống đang tiếp nhận hoặc hoàn tất. Đơn vị cần phù hợp loại workload.

### Metric nên có

| Metric | Đơn vị thường dùng | Ý nghĩa |
|---|---|---|
| Request rate | request/second (RPS) | Số request được nhận hoặc xử lý mỗi giây |
| Transaction rate | transaction/second (TPS) | Số giao dịch nghiệp vụ hoàn tất mỗi giây |
| Message throughput | message/second | Số message được nhận, xử lý hoặc xác nhận mỗi giây |
| Concurrent requests | request đồng thời | Số request đang xử lý tại một thời điểm |
| Bytes in/out | byte/s hoặc bit/s | Lưu lượng dữ liệu vào và ra |
| Active connections | connection | Số kết nối đang mở đến ứng dụng hoặc dependency |
| Queue arrival/completion | message/s | Tốc độ công việc đến so với tốc độ xử lý |

Không đánh đồng request được nhận với request hoàn tất thành công. Một API có thể nhận 1.000 RPS nhưng chỉ hoàn tất 700 RPS nếu hàng đợi tăng hoặc request timeout. Khi có thể, hãy hiển thị cả accepted rate, completed rate và queue depth.

### Panel Traffic đề xuất

- Request rate toàn service theo thời gian.
- Request rate theo route hoặc operation quan trọng.
- Traffic theo phiên bản, region hoặc zone.
- Concurrent requests và active connections.
- Ingress/egress bytes hoặc throughput mạng.
- Queue arrival rate so với processing/completion rate.

### Cách đọc

- Traffic tăng đồng thời latency và error tăng: kiểm tra saturation, autoscaling, giới hạn dependency và khả năng chịu tải.
- Traffic giữ nguyên nhưng completed rate giảm: có thể worker chậm, queue bị nghẽn hoặc dependency gặp sự cố.
- Traffic giảm đột ngột: kiểm tra DNS, load balancer, ingress, client behavior hoặc telemetry pipeline trước khi kết luận người dùng không còn nhu cầu.
- Traffic tăng ở một route hoặc tenant: xác minh đó là tải hợp lệ, thay đổi sản phẩm hay hoạt động bất thường.

## 4. Thiết kế dashboard Errors

Error signal cho biết công việc không đạt kết quả mong muốn. Cần định nghĩa lỗi theo ngữ cảnh của ứng dụng, không chỉ dựa trên HTTP status code.

### Phân loại lỗi

- **Server error:** lỗi do ứng dụng hoặc dịch vụ phía server, ví dụ HTTP 5xx.
- **Client error:** request không hợp lệ hoặc người dùng không có quyền, thường là HTTP 4xx. Một số mã như 429 có thể phản ánh rate limit hoặc quá tải có chủ đích.
- **Timeout:** request hoặc dependency không phản hồi trong thời gian quy định.
- **Dependency failure:** database, cache, queue hoặc API bên ngoài trả lỗi hoặc không truy cập được.
- **Business failure:** giao dịch bị từ chối theo quy tắc nghiệp vụ; không phải lúc nào cũng là lỗi kỹ thuật.
- **Background job failure:** job thất bại, bị retry quá nhiều hoặc bị đưa vào dead-letter queue.

Không nên cộng tất cả HTTP 4xx vào server error rate. Ví dụ, người dùng nhập sai dữ liệu có thể tạo 400 hợp lệ; nhưng 429 tăng đột ngột có thể là dấu hiệu giới hạn năng lực hoặc chính sách rate limit đang kích hoạt quá thường xuyên.

### Tính error rate

Với API, có thể tính tỷ lệ request lỗi kỹ thuật bằng:

    Error rate (%) = (Số request lỗi trong kỳ / Tổng request trong kỳ) × 100

Ví dụ, trong 5 phút có 60.000 request, trong đó 420 request trả lỗi server hoặc timeout:

    Error rate = (420 / 60.000) × 100 = 0,7%

Nếu SLO cho phép tối đa 0,1% lỗi kỹ thuật trong cửa sổ đánh giá, mức 0,7% cần được điều tra. Mẫu số phải nhất quán: loại trừ health check, synthetic request hoặc request nội bộ nếu chúng không thuộc lưu lượng người dùng trong SLO; đồng thời không loại bỏ các request lỗi chỉ để làm tỷ lệ đẹp hơn.

### Panel Errors đề xuất

- Error rate (%) toàn service và theo route.
- Error count theo nhóm 4xx, 5xx, timeout và dependency.
- Top operation hoặc dependency tạo nhiều lỗi nhất.
- Retry rate, failed job và dead-letter queue.
- Error rate theo phiên bản để phát hiện regression sau deployment.
- Số instance/Pod đang restart, OOMKilled hoặc crash loop.

Hiển thị cả tỷ lệ và số lượng. Tỷ lệ 50% trên 2 request có thể chỉ là một lỗi lẻ; 0,2% trên hàng triệu request có thể ảnh hưởng đến hàng nghìn người dùng.

## 5. Thiết kế dashboard Latency

Latency là thời gian từ khi một công việc bắt đầu đến khi hoàn tất theo một ranh giới đo đã xác định. Cần thống nhất điểm bắt đầu và kết thúc để so sánh các phiên bản và thành phần.

### Không chỉ nhìn trung bình

Giả sử 99 request mất 100 ms và một request mất 10 giây. Trung bình là 199 ms, nhưng p99 có thể phản ánh đuôi chậm rất rõ. Với hệ thống tương tác, người dùng bị ảnh hưởng bởi những request chậm dù trung bình vẫn thấp.

Các percentile thường dùng:

- **p50:** median, một nửa request nhanh hơn hoặc bằng giá trị này.
- **p90:** 90% request hoàn tất trong khoảng thời gian này hoặc nhanh hơn.
- **p95:** thể hiện nhóm 5% request chậm nhất trở lên.
- **p99:** giúp theo dõi tail latency, nơi một tỷ lệ nhỏ request có thể chậm nghiêm trọng.
- **Maximum:** giá trị lớn nhất quan sát được; hữu ích để điều tra nhưng nhạy với outlier và lỗi đo.

Nên hiển thị p50 cùng p95/p99. p50 phản ánh trải nghiệm điển hình; p95/p99 cho thấy đuôi phân phối. Không cộng hoặc lấy trung bình các percentile của từng instance để suy ra percentile toàn service; cần tính từ histogram/bucket hoặc dữ liệu phân phối đã được tổng hợp đúng cách.

### Tách các thành phần latency

Thời gian phản hồi tổng có thể bao gồm:

- DNS lookup và kết nối TCP/TLS.
- Thời gian chờ tại load balancer, ingress hoặc queue.
- Thời gian xử lý trong ứng dụng.
- Thời gian chờ CPU, lock, thread pool hoặc connection pool.
- Thời gian gọi database, cache, queue và API bên ngoài.
- Thời gian truyền dữ liệu và serialize/deserialize.

Distributed tracing giúp phân rã thời gian theo từng span. Dashboard latency cho biết có vấn đề; trace giúp xác định đoạn nào chiếm thời gian.

### Panel Latency đề xuất

- p50, p95 và p99 response time theo thời gian.
- Latency theo route, operation và phiên bản.
- Latency theo dependency: database query, cache, queue, external API.
- Queue wait time và processing time riêng biệt.
- Heatmap phân phối latency nếu hệ thống metric hỗ trợ histogram.
- Số request vượt ngưỡng SLO.

Đặt đơn vị rõ ràng (ms hoặc s), giữ cùng ranh giới đo và không trộn client-side latency với server-side latency trong cùng một chuỗi mà không ghi chú.

## 6. Thiết kế dashboard Saturation

Saturation phản ánh mức độ workload đang tiến gần giới hạn tài nguyên hoặc giới hạn phục vụ. CPU utilization là một phần của bức tranh; một dịch vụ có thể bão hòa ở RAM, disk, network, connection pool hoặc queue trong khi CPU vẫn thấp.

### CPU

Theo dõi:

- CPU utilization theo instance, node và toàn fleet.
- CPU usage theo container hoặc process quan trọng.
- CPU throttling đối với container có CPU limit.
- Load average, run queue hoặc CPU pressure.
- CPU credit/burst balance nếu loại instance có cơ chế burst.

CPU cao kéo dài cùng latency tăng và queue tăng thường là dấu hiệu thiếu năng lực hoặc xử lý không hiệu quả. CPU cao nhưng latency tốt và throughput tăng có thể là sử dụng tài nguyên hiệu quả. Hãy đọc theo workload và SLO.

### Memory

Theo dõi:

- Working set/used memory và available memory.
- Memory utilization so với limit hoặc dung lượng VM.
- Swap in/out, page fault hoặc memory pressure.
- OOM kill, container restart và xu hướng memory tăng liên tục.
- Heap, garbage collection và native memory nếu dùng JVM hoặc runtime tương tự.

Không chỉ nhìn free memory. Linux có thể dùng RAM cho page cache; cần xem available memory và working set. Với container, memory limit có thể gây OOM kill ngay cả khi node còn RAM trống.

### Storage và I/O

- Dung lượng đã dùng và tốc độ tăng filesystem.
- IOPS, throughput và read/write latency.
- I/O queue depth hoặc thời gian chờ I/O.
- Disk pressure, inode usage và lỗi filesystem.
- Giới hạn IOPS/throughput của volume hoặc dịch vụ lưu trữ.

CPU thấp nhưng latency cao có thể do tiến trình đang chờ disk I/O. Dung lượng đĩa gần đầy cũng có thể làm ứng dụng lỗi khi ghi log, tạo file tạm hoặc cập nhật dữ liệu.

### Network

- Throughput vào/ra so với giới hạn NIC hoặc instance.
- Packet drops, retransmission và lỗi giao diện.
- Connection count, connection tracking hoặc socket exhaustion.
- Network latency đến dependency và cross-zone/region traffic.
- Giới hạn NAT gateway, load balancer hoặc network service nếu có.

### Queue và giới hạn dịch vụ

- Queue depth và tuổi của message lâu nhất.
- Số worker đang hoạt động so với mức tối đa.
- Connection pool usage, pending acquisition và timeout.
- Thread pool queue, request concurrency và rate limit.
- API quota, database connection limit và giới hạn dịch vụ bên ngoài.

### Panel Saturation đề xuất

- CPU và memory theo instance/node, kèm ngưỡng/quota.
- CPU throttling và OOM/restart.
- Disk I/O latency, IOPS, throughput và dung lượng.
- Network throughput, drops và retransmission.
- Queue depth, oldest message age, worker concurrency.
- Database connection pool, active connections và query wait.
- Autoscaling desired/current/min/max capacity.

## 7. Kết hợp bốn tín hiệu để chẩn đoán

Không có một metric riêng lẻ đủ để giải thích mọi sự cố. Hãy so sánh các tín hiệu trong cùng một cửa sổ thời gian.

| Traffic | Errors | Latency | Saturation | Giả thuyết cần kiểm tra |
|---|---|---|---|---|
| Tăng | Tăng | Tăng | CPU cao | CPU-bound, thiếu instance hoặc autoscaling phản ứng chậm |
| Ổn định | Tăng | Tăng | CPU thấp, disk I/O cao | Database hoặc storage chậm, lock hoặc I/O-bound |
| Ổn định | Tăng | Tăng | Network drops/retransmission | Vấn đề mạng, giới hạn kết nối hoặc đường truyền |
| Ổn định | Thấp | Tăng | Queue depth tăng | Worker không theo kịp tốc độ đến hoặc concurrency bị giới hạn |
| Giảm | Tăng | Tăng | Tài nguyên bình thường | Dependency lỗi, deployment regression, DNS/ingress hoặc client retry |
| Tăng | Thấp | Ổn định | Tài nguyên còn headroom | Tăng trưởng bình thường; tiếp tục theo dõi năng lực và chi phí |
| Ổn định | Thấp | Ổn định | Một instance bão hòa | Hot spot, phân phối tải không đều hoặc cấu hình instance khác biệt |

Đây là các giả thuyết ban đầu, không phải kết luận. Dùng log, trace, deployment event và metric dependency để xác minh.

## 8. Bố cục dashboard thực tế

Một dashboard tổng quan cho service compute có thể gồm các hàng sau:

| Vị trí | Panel | Mục đích |
|---|---|---|
| Hàng 1 | SLO status, request rate, error rate, p95/p99 latency, saturation summary | Nhận diện nhanh tác động người dùng |
| Hàng 2 | Traffic theo route/zone/version; completed rate và queue arrival | Xác định nơi tải tăng hoặc xử lý chậm |
| Hàng 3 | Error rate theo code/dependency/version; failed jobs | Khoanh vùng loại lỗi và thành phần liên quan |
| Hàng 4 | Latency percentile và heatmap; dependency latency | Xác định tail latency và đoạn chậm |
| Hàng 5 | CPU, RAM, throttling, OOM, disk I/O, network | Tìm giới hạn tài nguyên |
| Hàng 6 | Instance count, autoscaling, queue depth, database pool | Kiểm tra năng lực và khả năng mở rộng |
| Hàng 7 | Deployments, maintenance events, incidents và annotation | Đối chiếu thay đổi theo thời gian |

### Quy tắc trình bày

- Đặt tên panel theo câu hỏi vận hành, không chỉ theo tên metric nội bộ.
- Ghi đơn vị, phạm vi, nguồn dữ liệu và cách aggregation.
- Dùng cùng time range và timezone cho các panel có liên quan.
- Đánh dấu deployment, maintenance và incident trên timeline.
- Dùng màu nhất quán cho trạng thái bình thường, cảnh báo và nghiêm trọng; không phụ thuộc màu sắc duy nhất để truyền đạt trạng thái.
- Hiển thị khoảng trống dữ liệu khác với giá trị 0. Không có metric không có nghĩa là không có request hoặc không có lỗi.
- Cung cấp link đến log, trace, runbook và dashboard chi tiết.
- Hạn chế quá nhiều panel; ưu tiên thông tin giúp ra quyết định.

## 9. Thiết kế label và aggregation

Metric thường có label để phân nhóm, ví dụ service, environment, region, zone, instance, route, method, status_class và version.

### Label nên dùng

- **service:** tên service ổn định.
- **environment:** production, staging, development.
- **region/zone:** vị trí triển khai.
- **instance/pod:** để drill-down, không nhất thiết hiển thị tất cả trên trang tổng quan.
- **route hoặc operation:** dùng template route ổn định như /orders/{id}.
- **status_class:** nhóm 2xx, 4xx, 5xx hoặc loại lỗi.
- **version:** phiên bản ứng dụng để so sánh trước/sau deployment.

### Tránh cardinality cao

Không đưa các giá trị thay đổi gần như mỗi request vào label metric, ví dụ:

- User ID, email, session ID hoặc request ID.
- Raw URL có ID tài nguyên hoặc query string tùy biến.
- Nội dung exception, message hoặc payload.
- IP nguồn của từng client nếu tập giá trị lớn và không có nhu cầu rõ ràng.

Cardinality cao làm tăng số time series, bộ nhớ, chi phí ingest và độ trễ truy vấn. Những dữ liệu cần điều tra ở cấp request nên nằm trong log hoặc trace có kiểm soát, được liên kết bằng trace ID; không biến chúng thành label metric.

### Aggregation đúng

- Request rate toàn service: cộng rate của các instance.
- Error rate: tổng số lỗi chia tổng số request trong cùng phạm vi và cửa sổ, không lấy trung bình đơn giản các tỷ lệ instance.
- Latency percentile: tính từ histogram/bucket đã tổng hợp, không lấy trung bình p95 của từng instance.
- CPU fleet: có thể xem cả trung bình có trọng số và giá trị theo instance; trung bình toàn fleet có thể che giấu một node bão hòa.
- Queue depth: tổng số message và tuổi message lâu nhất có thể cần hiển thị riêng; tổng queue không phản ánh độ trễ của message cũ nhất.

## 10. Ví dụ truy vấn PromQL

Các truy vấn sau minh họa cách tính với metric kiểu Prometheus. Tên metric thực tế phụ thuộc framework, exporter và instrumentation. Hãy xác minh metric có đúng semantics, đơn vị và label trước khi dùng trong dashboard.

### Request rate toàn service

    sum by (service) (
      rate(http_server_requests_total[5m])
    )

rate() ước lượng tốc độ tăng counter mỗi giây trong cửa sổ 5 phút. Cộng các instance theo service để xem tổng request rate.

### Tỷ lệ lỗi 5xx

    100 *
    sum by (service) (
      rate(http_server_requests_total{status=~"5.."}[5m])
    )
    /
    sum by (service) (
      rate(http_server_requests_total[5m])
    )

Nếu metric dùng label khác như code hoặc status_class, cần điều chỉnh selector. Bảo đảm request counter ở tử số và mẫu số có cùng cách đếm.

### p95 latency từ histogram

    histogram_quantile(
      0.95,
      sum by (le, service) (
        rate(http_request_duration_seconds_bucket[5m])
      )
    )

Histogram cần có bucket phù hợp với dải latency của ứng dụng. Nếu bucket quá thô hoặc không bao phủ ngưỡng SLO, percentile ước lượng có thể thiếu chính xác.

### CPU utilization theo instance

    100 * (
      1 - avg by (instance) (
        rate(node_cpu_seconds_total{mode="idle"}[5m])
      )
    )

Truy vấn này minh họa cách suy ra phần CPU không idle từ node exporter. Với container hoặc cloud VM, metric và cách tính có thể khác; kiểm tra CPU quota, throttling và cách exporter báo từng core.

### Tỷ lệ CPU throttling của container

    100 *
    sum by (namespace, pod, container) (
      rate(container_cpu_cfs_throttled_periods_total[5m])
    )
    /
    sum by (namespace, pod, container) (
      rate(container_cpu_cfs_periods_total[5m])
    )

Đây là tỷ lệ chu kỳ có throttling theo metric cAdvisor thường gặp. Không đồng nhất nó với phần trăm CPU được sử dụng; cần xem cùng CPU usage và latency.

### Memory working set so với limit

    100 *
    container_memory_working_set_bytes
    /
    container_spec_memory_limit_bytes

Trong môi trường thực tế cần lọc container ứng dụng, loại trừ container không có limit hợp lệ và xử lý giá trị limit bằng 0 hoặc không được xuất.

## 11. Từ dashboard đến cảnh báo theo SLO

Dashboard giúp người vận hành khám phá trạng thái. Alert cần thông báo khi có điều kiện đòi hỏi hành động. Không nên tạo alert cho mọi panel hoặc mọi lần vượt ngưỡng ngắn.

### Chọn ngưỡng theo mục tiêu dịch vụ

Ví dụ, API có SLO:

- 99,9% request hợp lệ hoàn tất thành công trong cửa sổ 30 ngày.
- p95 latency dưới 300 ms cho route tạo đơn.
- Queue message cũ nhất không vượt 60 giây.

Alert nên phản ánh mức tiêu thụ error budget, thời gian vi phạm và số người dùng bị ảnh hưởng. Ngưỡng CPU 80% có thể là cảnh báo capacity, nhưng không nhất thiết là incident nếu latency và error vẫn trong SLO.

### Error budget và burn rate

Với SLO availability 99,9%, error budget là 0,1% số request trong cửa sổ đánh giá. Burn rate cho biết tốc độ tiêu thụ error budget so với tốc độ tương ứng với SLO.

Nếu tỷ lệ lỗi hiện tại là 1% trong khi ngân sách lỗi là 0,1%, tốc độ tiêu thụ theo tỷ lệ là khoảng 10 lần mức cho phép. Nếu tình trạng kéo dài, error budget sẽ cạn nhanh. Alert multi-window có thể kết hợp cửa sổ ngắn để phát hiện sự cố mạnh và cửa sổ dài để tránh báo động do nhiễu ngắn.

### Các nhóm alert hữu ích

- **User impact:** error rate vượt SLO, p95/p99 vượt ngưỡng trong thời gian đủ dài, request success giảm.
- **Capacity:** CPU pressure hoặc throttling kéo dài, memory gần limit, OOM, disk gần đầy, network gần giới hạn.
- **Queue/dependency:** queue age tăng, connection pool cạn, dependency latency/error tăng.
- **Availability:** số instance ready thấp hơn mức tối thiểu, một zone mất backend, autoscaling không tạo được instance.
- **Telemetry health:** metric scrape mất, dashboard không có dữ liệu, log/trace pipeline bị gián đoạn.

Mỗi alert cần có owner, mức độ, điều kiện rõ ràng, link dashboard và runbook. Alert cần hành động ngay nên được gửi đến on-call; cảnh báo xu hướng hoặc capacity có thể vào kênh theo dõi khác.

## 12. Liên kết metric, log và trace

Metric cho biết xu hướng và phạm vi; log ghi lại sự kiện cụ thể; trace cho thấy request đi qua các thành phần nào và mất thời gian ở đâu.

    Request -> API -> Database
                 -> Queue -> Worker

    Metrics: rate / errors / latency / saturation
    Logs: event, exception và trace_id
    Traces: span và dependency timing

Ví dụ điều tra: dashboard cho thấy p99 latency tăng ở API tạo đơn. Người vận hành lọc trace theo route và thấy span database chiếm phần lớn thời gian. Log theo trace ID cho thấy truy vấn bị timeout; dashboard saturation lại cho thấy connection pool gần cạn. Kết hợp ba nguồn giúp xác định vấn đề nằm ở kết nối database hoặc truy vấn thay vì tăng CPU cho VM.

### Quy tắc tương quan

- Dùng trace ID hoặc request ID trong log/trace, không làm label metric có cardinality cao.
- Đồng bộ thời gian giữa ứng dụng, VM, container và dịch vụ phụ thuộc.
- Dùng cùng service name, environment, version và region trong telemetry.
- Che hoặc loại bỏ token, password, dữ liệu cá nhân và payload nhạy cảm.
- Đặt retention và quyền truy cập theo phân loại dữ liệu.

## 13. Quy trình xây dựng dashboard từ đầu

    Xác định người dùng và quyết định cần hỗ trợ
        -> Chọn SLI/SLO và phạm vi service
        -> Instrument traffic, errors, latency
        -> Thu thập saturation và dependency metrics
        -> Chuẩn hóa label, unit và aggregation
        -> Thiết kế overview và drill-down
        -> Đối chiếu log, trace và deployment event
        -> Kiểm thử truy vấn và dữ liệu thiếu
        -> Đặt alert và runbook
        -> Rà soát, loại panel không hữu ích

### Bước 1: xác định câu hỏi vận hành

Viết ra những câu hỏi dashboard phải trả lời, ví dụ: “API có đang lỗi với người dùng không?”, “Phiên bản mới có làm p99 tăng không?”, “Worker có xử lý kịp message không?” hoặc “Một zone có đang bão hòa không?”.

### Bước 2: chọn SLI và SLO

Chọn chỉ số phản ánh trải nghiệm hoặc kết quả nghiệp vụ. Xác định phạm vi request hợp lệ, cách đếm lỗi, ngưỡng latency và cửa sổ đánh giá. Ghi rõ những loại traffic được loại khỏi SLO và lý do.

### Bước 3: instrument ứng dụng

Đếm request và kết quả, đo duration bằng histogram, theo dõi concurrency, queue và dependency. Dùng metric chuẩn hoặc OpenTelemetry instrumentation phù hợp. Đảm bảo counter không reset bất thường và histogram có bucket bao phủ ngưỡng quan trọng.

### Bước 4: thu thập saturation

Lấy metric từ cloud monitoring, node/container exporter, database, storage, load balancer và network. Xác minh đơn vị và ý nghĩa metric theo dịch vụ; không ghép các metric có semantics khác nhau vào cùng panel.

### Bước 5: chuẩn hóa label và aggregation

Thống nhất tên service, environment, version, region và route template. Tránh label chứa ID duy nhất. Xác định panel tổng hợp theo service và panel drill-down theo instance/zone.

### Bước 6: thiết kế overview và drill-down

Đặt bốn tín hiệu vàng ở phần đầu. Bên dưới là breakdown theo route, version, zone, dependency và tài nguyên. Thêm annotation cho deployment, maintenance và incident.

### Bước 7: xác minh dữ liệu

Tạo tải thử có kiểm soát, tạo lỗi thử nghiệm và kiểm tra percentile. Xác nhận dashboard phân biệt zero với no data, không đếm trùng request retry và không bỏ sót instance mới khi autoscaling.

### Bước 8: alert và cải tiến

Tạo alert theo SLO, capacity và telemetry health. Gắn runbook, owner và hành động rõ ràng. Sau incident, xem panel nào hữu ích, panel nào gây nhiễu và bổ sung metric còn thiếu.

## 14. Ví dụ dashboard cho API xử lý đơn hàng

Một API chạy trên nhiều VM hoặc Pod, đặt sau load balancer, ghi đơn vào database và gửi event vào queue. Dashboard overview có thể hiển thị:

| Nhóm | Panel | Ví dụ mục tiêu |
|---|---|---|
| Traffic | Request rate, completed orders/s, active requests | Phát hiện tải tăng và chênh lệch accepted/completed |
| Errors | 5xx rate, timeout, payment dependency failures | Theo dõi lỗi kỹ thuật và phụ thuộc quan trọng |
| Latency | p50/p95/p99 của POST /orders | Đối chiếu SLO và phát hiện tail latency |
| Saturation | CPU, memory, throttling, disk I/O, DB pool, queue age | Xác định tài nguyên hoặc dependency gần giới hạn |
| Availability | Ready instances theo zone, backend healthy | Kiểm tra đủ năng lực khi bảo trì hoặc mất instance |
| Change context | Deployment version, maintenance annotation | Đối chiếu sự cố với thay đổi gần nhất |

Giả sử trong 10 phút:

- Request rate tăng từ 300 lên 650 RPS.
- Error rate 5xx tăng từ 0,05% lên 1,2%.
- p95 latency tăng từ 180 ms lên 900 ms.
- CPU p95 trên các VM API đạt 92%, CPU throttling tăng ở một nhóm container.
- Queue age tăng từ 5 giây lên 75 giây.

Các tín hiệu cùng cho thấy hệ thống đang chịu tải vượt khả năng xử lý hiện tại. Nhóm on-call có thể kiểm tra autoscaling, giới hạn CPU, tốc độ xử lý worker và năng lực database. Nếu chỉ nhìn error rate, nguyên nhân chưa rõ; nếu chỉ nhìn CPU trung bình toàn fleet, nhóm container bị throttling có thể bị che khuất.

Một tình huống khác: traffic không đổi, error rate thấp nhưng p99 tăng mạnh; CPU còn thấp trong khi database query latency và connection pool wait tăng. Khi đó, tăng vCPU cho API có thể không giải quyết được vấn đề. Cần điều tra database, query plan, lock và connection pool.

## 15. Những sai lầm thường gặp

**Chỉ hiển thị CPU và RAM.** Dashboard thiếu traffic, error và latency không cho biết tác động người dùng. Bổ sung bốn tín hiệu vàng ở cấp service.

**Chỉ nhìn trung bình.** Average che giấu tail latency, instance nóng và đợt lỗi ngắn. Dùng percentile, breakdown và biểu đồ theo thời gian.

**Lấy trung bình các error rate hoặc percentile của instance.** Cách tổng hợp này có thể sai khi lưu lượng giữa instance không đều. Tính từ counter/histogram gốc với aggregation phù hợp.

**Đếm mọi 4xx là lỗi server.** Một số 4xx là hành vi hợp lệ của client hoặc quy tắc nghiệp vụ. Phân loại lỗi theo semantics và SLO.

**Dùng label request ID hoặc user ID.** Cardinality tăng mạnh và có thể làm lộ dữ liệu. Đưa định danh chi tiết vào log/trace có kiểm soát.

**Coi no data là zero.** Pipeline metric bị lỗi có thể làm dashboard trống nhưng vẫn hiển thị như hệ thống khỏe. Theo dõi telemetry health riêng.

**Đặt alert cho mọi metric vượt ngưỡng.** Nhiều alert nhiễu khiến on-call bỏ qua cảnh báo. Alert theo SLO, kéo dài đủ lâu và có hành động rõ.

**Không đánh dấu deployment và maintenance.** Khó liên hệ thay đổi với thời điểm latency/error bắt đầu tăng. Thêm annotation hoặc event overlay.

**Đưa quá nhiều biểu đồ vào trang đầu.** Người trực khó nhận diện vấn đề. Giữ overview ngắn và cung cấp drill-down theo nhu cầu.

## 16. Checklist dashboard bốn tín hiệu vàng

### Metric và semantics

- [ ] Traffic có request rate, completed rate hoặc throughput phù hợp workload.
- [ ] Errors phân biệt server error, client error, timeout, dependency và business failure.
- [ ] Latency có p50 và tail percentile p95/p99; đơn vị và ranh giới đo rõ ràng.
- [ ] Saturation bao gồm CPU, memory, storage, network và queue/connection limit phù hợp.
- [ ] Metric có đơn vị, nguồn, label và cách aggregation được ghi rõ.
- [ ] Histogram bucket bao phủ ngưỡng latency/SLO cần quan sát.

### Dashboard và điều tra

- [ ] Overview hiển thị bốn tín hiệu ở cấp service.
- [ ] Có drill-down theo route, version, instance, zone và dependency.
- [ ] Có panel autoscaling, số instance ready và queue khi workload cần.
- [ ] Có annotation cho deployment, maintenance và incident.
- [ ] Có liên kết từ metric sang log, trace và runbook.
- [ ] No data được phân biệt với zero; telemetry pipeline có cảnh báo riêng.

### Chất lượng dữ liệu và cảnh báo

- [ ] Không dùng label có cardinality cao như user ID, request ID hoặc raw URL.
- [ ] Error rate và percentile được tổng hợp đúng từ dữ liệu gốc.
- [ ] SLO, error budget và alert window đã được xác định.
- [ ] Alert có owner, mức độ, điều kiện và hành động cụ thể.
- [ ] Dashboard được kiểm thử bằng tải, lỗi và tình huống dependency thực tế.
- [ ] Quyền truy cập, retention và che dữ liệu nhạy cảm được cấu hình.

## 17. Tự kiểm tra

1. Bốn tín hiệu vàng là gì? Vì sao cần xem chúng cùng nhau?
2. Một service nhận 1.000 RPS nhưng chỉ hoàn tất 700 RPS. Bạn cần xem thêm metric nào để giải thích chênh lệch?
3. Vì sao p95/p99 hữu ích hơn chỉ nhìn latency trung bình trong một API tương tác?
4. Tại sao không nên lấy trung bình p95 của từng instance để tính p95 toàn service?
5. Một tỷ lệ 4xx tăng có luôn là sự cố server không? Cần phân loại như thế nào?
6. CPU thấp nhưng latency và queue age tăng có thể chỉ ra những nút thắt nào?
7. Cardinality cao ảnh hưởng hệ thống metrics ra sao? Những label nào nên tránh?
8. Làm thế nào phân biệt metric bằng 0 với telemetry pipeline không gửi dữ liệu?
9. Alert theo SLO/error budget khác alert theo một ngưỡng CPU cố định như thế nào?
10. Khi p99 của API tăng sau deployment, bạn sẽ dùng metric, log và trace theo thứ tự nào để điều tra?

Dashboard tốt biến dữ liệu vận hành thành câu trả lời có thể hành động. Khi traffic, errors, latency và saturation được định nghĩa nhất quán, tổng hợp đúng và liên kết với log, trace cùng SLO, đội ngũ có thể phát hiện ảnh hưởng sớm, tìm đúng nút thắt và đưa ra quyết định về scale, tối ưu hoặc phục hồi dựa trên bằng chứng.
