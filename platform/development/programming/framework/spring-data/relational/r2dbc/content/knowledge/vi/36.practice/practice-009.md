# Đo tải, xác định điểm nghẽn và đánh giá lựa chọn R2DBC

## 1. Vì sao phải đo trước khi chọn R2DBC?

R2DBC cho phép ứng dụng Java truy cập cơ sở dữ liệu theo mô hình reactive và non-blocking. Điều đó có thể giúp một ứng dụng WebFlux xử lý nhiều thao tác I/O đồng thời mà không phải giữ một thread riêng trong suốt thời gian chờ database. Tuy nhiên, R2DBC không tự làm cho câu SQL nhanh hơn, không tự tăng capacity của database và không bảo đảm mọi ứng dụng chuyển từ JDBC sang R2DBC sẽ có throughput cao hơn.

Một hệ thống có thể chậm vì nhiều nguyên nhân:

- Query thiếu index hoặc execution plan kém.
- Database CPU, I/O hoặc lock contention cao.
- Connection pool cạn connection hoặc acquire chậm.
- Transaction giữ connection quá lâu.
- Code gọi JDBC hoặc thư viện blocking trên event-loop.
- Reactor pipeline tạo quá nhiều publisher đồng thời.
- Serialization, mapping hoặc xử lý dữ liệu tiêu tốn CPU.
- GC pause, heap pressure hoặc network latency.
- Downstream service chậm.
- Load generator không đủ năng lực tạo tải.

Nếu chỉ nhìn một con số như request/second hoặc thời gian trung bình, nhóm phát triển có thể kết luận sai. Ví dụ, throughput tăng nhưng p99 latency tăng mạnh có thể có nghĩa hệ thống đẩy được nhiều request hơn bằng cách để một số request chờ rất lâu. Hoặc R2DBC làm giảm số thread nhưng database vẫn là bottleneck nên thời gian phản hồi gần như không đổi.

Bài này hướng dẫn cách xây dựng một phép đo có thể lặp lại, tìm bottleneck từ đầu request đến database, và đánh giá R2DBC dựa trên workload thực tế. Kết quả cần trả lời được:

1. Hệ thống hiện tại đáp ứng được bao nhiêu tải trong SLO?
2. Tài nguyên nào chạm giới hạn trước?
3. R2DBC thay đổi throughput, latency, concurrency và chi phí tài nguyên ra sao?
4. Phần cải thiện đến từ mô hình truy cập dữ liệu hay từ thay đổi query, pool, cache hoặc cấu hình khác?
5. R2DBC có đáng chọn cho workload và đội ngũ vận hành hiện tại không?

## 2. Xác định mục tiêu và SLO trước khi chạy load test

Một bài load test không nên bắt đầu bằng câu hỏi "chạy được bao nhiêu request mỗi giây?". Hãy bắt đầu bằng yêu cầu người dùng và giới hạn hệ thống cần đáp ứng.

Ví dụ SLO cho API đọc đơn hàng:

| Chỉ số | Mục tiêu minh họa |
|---|---:|
| Throughput ở tải dự kiến | 500 request/second |
| p95 latency | Dưới 200 ms |
| p99 latency | Dưới 500 ms |
| HTTP 5xx | Dưới 0.1% |
| Acquire timeout | 0 trong tải bình thường |
| Database CPU | Dưới ngưỡng vận hành đã thống nhất |
| Pool pending | Không tăng liên tục |
| Memory | Không tăng không giới hạn trong soak test |

Các con số chỉ minh họa. Mỗi ứng dụng phải đặt SLO theo yêu cầu nghiệp vụ, vùng triển khai, chi phí và baseline hiện tại.

### 2.1. Phân biệt throughput và latency

- **Throughput** là lượng công việc hoàn thành trong một đơn vị thời gian, ví dụ request/second hoặc transaction/second.
- **Latency** là thời gian một request cần để hoàn tất.
- **Concurrency** là số request hoặc thao tác đang hoạt động đồng thời.
- **Error rate** là tỷ lệ request thất bại.
- **Saturation** mô tả mức tài nguyên đã bị sử dụng đến giới hạn hoặc bắt đầu phải xếp hàng.

Các chỉ số liên hệ với nhau nhưng không thay thế nhau. Một hệ thống có thể throughput cao nhưng latency xấu. Một hệ thống latency thấp ở tải nhỏ có thể sụp khi concurrency tăng.

### 2.2. Dùng percentile thay vì chỉ dùng average

Average latency che khuất tail latency. Ví dụ:

- 95 request mất 50 ms.
- 4 request mất 300 ms.
- 1 request mất 5 giây.

Average có thể vẫn trông chấp nhận được, nhưng người dùng gặp request 5 giây sẽ có trải nghiệm rất tệ.

Theo dõi tối thiểu:

- p50: request điển hình ở giữa phân phối.
- p90: 90% request hoàn tất trong thời gian này hoặc nhanh hơn.
- p95: phản ánh phần đuôi thường dùng cho SLO.
- p99: phát hiện những request rất chậm.
- Maximum: hữu ích khi điều tra, nhưng nhạy với outlier và kích thước mẫu.

Không cộng các percentile của từng đoạn để suy ra percentile end-to-end. Ví dụ p95 của gateway cộng p95 của database không nhất thiết bằng p95 toàn request vì các percentile có thể đến từ những request khác nhau. Hãy đo end-to-end và từng span riêng.

### 2.3. Xác định error budget

Nếu SLO cho phép 0.1% lỗi, hãy xác định rõ lỗi nào được tính:
- HTTP 5xx.
- Timeout.
- Connection acquire failure.
- Request bị từ chối vì rate limit.
- Business rejection hợp lệ như insufficient inventory.
- Client cancellation.

Không gộp lỗi nghiệp vụ hợp lệ vào lỗi hạ tầng nếu chúng có ý nghĩa khác nhau. Ngược lại, timeout và acquire failure không nên bị bỏ khỏi error rate chỉ vì chúng không trả 5xx.

## 3. Xây dựng workload đại diện cho production

Một benchmark chỉ có giá trị khi workload gần với cách hệ thống được sử dụng thật.

Không nên chỉ chạy một endpoint đơn giản trả một hàng theo primary key rồi kết luận về toàn bộ ứng dụng. Workload thực tế thường có nhiều loại thao tác và tỷ lệ khác nhau.

Ví dụ profile cho một hệ thống đơn hàng:

| Use case | Tỷ lệ | Đặc điểm |
|---|---:|---|
| Xem order theo ID | 45% | Query ngắn, indexed lookup |
| Tìm kiếm theo trạng thái | 25% | Filter, sort, pagination |
| Tạo order | 10% | Insert và generated ID |
| Cập nhật trạng thái | 10% | Read-modify-write, transaction |
| Lấy lịch sử | 7% | Nhiều hàng, sort theo thời gian |
| Báo cáo tổng hợp | 3% | Query nặng, aggregate |

Đây là profile giả định. Hãy lấy tỷ lệ từ access log, trace, analytics hoặc product requirement đã được ẩn danh.

### 3.1. Ghi lại dữ liệu đầu vào của workload

Cần xác định:

- Số lượng user/tenant.
- Phân bố ID được truy vấn.
- Tỷ lệ cache hit/miss.
- Page size phổ biến và tối đa.
- Tỷ lệ dữ liệu nóng/lạnh.
- Kích thước response.
- Tỷ lệ đọc/ghi.
- Số thao tác database trong mỗi request.
- Tỷ lệ transaction.
- Tần suất lỗi và retry.
- Thời gian chờ downstream.

Một workload luôn truy vấn cùng một ID có thể làm cache CPU/DB hoạt động khác hẳn workload phân bố đều trên hàng triệu bản ghi.

### 3.2. Dùng dữ liệu đủ lớn và có phân bố hợp lý

Dataset quá nhỏ có thể nằm hoàn toàn trong cache và không phản ánh production. Dataset quá lớn nhưng không có phân bố thực tế cũng có thể tạo ra kết quả không hữu ích.

Cân nhắc:
- Số hàng gần với môi trường thật.
- Index giống production.
- Tỷ lệ trạng thái tương tự.
- Phân bố tenant.
- Kích thước cột TEXT/BLOB.
- Foreign key và quan hệ.
- Tỷ lệ dữ liệu được truy cập thường xuyên.
- Mức độ cập nhật đồng thời.

Dữ liệu benchmark nên được tạo tổng hợp hoặc ẩn danh. Không sao chép dữ liệu cá nhân/nhạy cảm vào môi trường test khi không có cơ sở và biện pháp bảo vệ phù hợp.

### 3.3. Tránh một workload chỉ có cache hit

Nếu mỗi lần test đều đọc một tập nhỏ đã nằm trong cache, kết quả có thể đo cache thay vì đo khả năng xử lý database.

Nên có các profile riêng:
- Hot data: phần lớn request truy cập dữ liệu phổ biến.
- Mixed: phân bố gần production.
- Cold/wide: truy vấn phạm vi rộng hơn.
- Write-heavy: nhiều insert/update.
- Read-heavy: chủ yếu đọc.
- Mixed transactional: phối hợp nhiều repository trong một transaction.

Không xóa cache tùy tiện giữa từng request. Hãy định nghĩa rõ test đo warm-cache hay cold-cache và chạy theo quy trình có thể lặp lại.

## 4. Chọn loại kiểm thử tải

Mỗi loại test trả lời một câu hỏi khác nhau.

| Loại test | Mục đích | Ví dụ |
|---|---|---|
| Smoke | Xác nhận hệ thống và script hoạt động | 1-5 user trong thời gian ngắn |
| Load | Đo tải dự kiến | Duy trì 500 RPS |
| Stress | Tìm giới hạn và hành vi khi quá tải | Tăng tải đến khi SLO bị vi phạm |
| Spike | Kiểm tra burst đột ngột | Từ 100 lên 1.000 RPS trong vài giây |
| Soak | Tìm rò rỉ và suy giảm dài hạn | Duy trì tải nhiều giờ |
| Capacity | Tìm mức tải tối đa đáp ứng SLO | Tăng concurrency từng bậc |
| Scalability | Xem hiệu quả khi tăng instance/resource | Tăng replica hoặc CPU |

Không dùng kết quả stress test để thay cho load test. Một hệ thống có thể chịu được 2.000 RPS trong vài giây nhưng không duy trì được 500 RPS trong một giờ.

### 4.1. Load test

Chạy workload ở mức tải dự kiến và cao hơn một chút. Mục tiêu là xác nhận SLO, không phải phá hệ thống.

### 4.2. Stress test

Tăng tải dần để tìm điểm bắt đầu:
- p95/p99 vượt SLO.
- Error rate tăng.
- Pool pending tăng liên tục.
- Database CPU hoặc lock wait bão hòa.
- Event-loop hoặc CPU app chạm giới hạn.

Cần xác định hành vi graceful degradation: từ chối sớm, timeout có kiểm soát và không làm hệ thống sụp dây chuyền.

### 4.3. Spike test

Mô phỏng campaign, batch job hoặc traffic burst. Quan sát pool có tạo connection kịp không, queue có tăng quá nhanh không và hệ thống hồi phục sau burst mất bao lâu.

### 4.4. Soak test

Giữ tải trong thời gian dài để tìm:
- Memory tăng dần.
- Connection leak.
- Pool không trả connection.
- Cache phình lớn.
- Queue tích lũy.
- Thread hoặc scheduler bị nghẽn.
- Retry storm.
- Database session tăng không giảm.

## 5. Open workload model và closed workload model

Cách tạo tải ảnh hưởng mạnh tới kết quả.

### 5.1. Closed model

Closed model giữ một số virtual users. Mỗi user gửi request, chờ response xong rồi mới gửi request tiếp theo.

Khi server chậm, tốc độ gửi request tự giảm vì user đang chờ. Điều này có thể che khuất mức quá tải: server càng chậm thì load generator càng ít tạo request mới.

Closed model hữu ích khi muốn mô phỏng số người dùng đồng thời có hành vi think-time.

### 5.2. Open model

Open model phát request theo tốc độ định trước, ví dụ 500 request/second, không phụ thuộc request trước đã hoàn tất hay chưa.

Nó hữu ích để kiểm tra hệ thống có đáp ứng một arrival rate cụ thể hay không. Khi server chậm, số request đang chờ có thể tăng, thể hiện queueing và saturation.

Cần giới hạn queue ở load generator và theo dõi dropped iterations. Nếu load generator không tạo được tốc độ mong muốn, kết quả không đại diện cho tải yêu cầu.

### 5.3. Coordinated omission

Nếu load generator chỉ gửi request tiếp theo sau khi request trước hoàn tất, những khoảng thời gian server bị treo có thể không được phản ánh đầy đủ trong histogram latency. Đây là vấn đề thường được gọi là coordinated omission.

Chọn workload model phù hợp, dùng công cụ có cách đo arrival rate rõ ràng và xem cả số iteration bị dropped hoặc không khởi chạy đúng lịch.

### 5.4. Đừng nhầm virtual users với concurrency database

100 virtual users không đồng nghĩa có 100 query đồng thời. Một user có thể:
- Chờ think-time.
- Gọi endpoint không truy cập database.
- Gửi request chỉ đọc cache.
- Thực hiện nhiều query tuần tự.
- Giữ một request dài.

Hãy đo request concurrency, active DB operations và pool acquired riêng.

## 6. Chuẩn bị môi trường benchmark công bằng

Để so sánh JDBC và R2DBC, các biến số phải được kiểm soát.

Giữ giống nhau:
- Máy/VM hoặc giới hạn CPU và memory.
- Database version và cấu hình.
- Dataset, schema và index.
- Query semantics và kết quả.
- Network path và TLS.
- Số application replica.
- JVM version và flags.
- Logging level.
- Cache policy.
- Pool size và timeout, trong phạm vi hợp lý cho mỗi driver.
- Load generator và workload.
- Thời gian warm-up.
- Khoảng đo và cách tính percentile.

Ghi lại mọi khác biệt cấu hình. Không ép JDBC và R2DBC dùng cấu hình pool không tương đương chỉ để có cùng một con số, nhưng cũng không để một bên có cache hoặc index khác.

### 6.1. Tách load generator khỏi application host

Nếu load generator chạy cùng máy với ứng dụng, CPU và network có thể bị tranh chấp. Khi ứng dụng tăng tải, load generator cũng chậm lại và làm sai kết quả.

Tốt nhất:
- Chạy load generator trên máy riêng.
- Theo dõi CPU, memory và network của load generator.
- Kiểm tra nó có đạt request rate mục tiêu không.
- Dùng nhiều generator nếu cần tạo tải lớn.
- Đảm bảo generator không trở thành bottleneck.

### 6.2. Giữ database riêng và quan sát được

Trong benchmark, database phải có đủ resource để phân biệt bottleneck app với bottleneck database. Đồng thời, không cấp resource vô hạn cho database nếu production có giới hạn cụ thể.

Theo dõi:
- CPU.
- Memory.
- Disk IOPS/latency.
- Active sessions.
- Running queries.
- Lock waits.
- Buffer/cache hit.
- Replication lag nếu có.
- Connection rejection.

### 6.3. Warm-up và JIT

Java cần thời gian warm-up để:
- Class được load.
- JIT compile hot path.
- Connection pool tạo connection.
- Cache được lấp đầy.
- Query plan/cache ổn định.
- Runtime profile hình thành.

Không lấy vài giây đầu sau startup làm kết quả chính. Tách warm-up khỏi measurement window và áp dụng cùng quy tắc cho cả hai implementation.

### 6.4. Lặp lại và báo cáo độ biến thiên

Chạy mỗi kịch bản nhiều lần. Ghi median hoặc khoảng biến thiên giữa các lần chạy, không chỉ chọn lần tốt nhất.

Nếu kết quả dao động mạnh, tìm nguyên nhân:
- Background jobs.
- Noisy neighbor.
- GC.
- Database checkpoint.
- Cache warmness.
- Network jitter.
- Load generator saturation.

Một cải thiện 2% trong khi độ dao động giữa các lần chạy là 8% chưa phải bằng chứng đáng tin.

## 7. Các chỉ số cần thu thập ở từng lớp

Không thể xác định bottleneck chỉ từ application latency. Hãy quan sát toàn đường đi.

### 7.1. Ở lớp HTTP/API

Theo dõi:
- Request rate.
- In-flight requests.
- p50/p95/p99 latency.
- Status code và error rate.
- Timeout/cancel.
- Request/response bytes.
- Latency theo endpoint và loại use case.

Nếu một endpoint chậm hơn các endpoint khác, hãy phân tách theo route và request class thay vì nhìn tổng.

### 7.2. Ở JVM/application

Theo dõi:
- CPU utilization.
- Heap used/committed.
- Allocation rate.
- GC pause và frequency.
- Thread count.
- Thread state.
- Event-loop utilization hoặc task queue.
- Scheduler queue nếu có.
- CPU profiling/JFR.
- Serialization và mapping time.

R2DBC giảm nhu cầu chờ trên thread cho I/O nhưng không loại bỏ CPU work. Nếu mapping hoặc JSON serialization nặng, CPU vẫn là bottleneck.

### 7.3. Ở connection pool

Theo dõi:
- Acquired.
- Allocated.
- Idle.
- Pending.
- Acquire wait duration nếu có.
- Acquire timeout/error.
- Connection creation time/failure.
- Pool max size và max pending.

Acquired cao không đồng nghĩa active query count. Connection có thể được giữ trong transaction hoặc trong lúc chờ downstream.

### 7.4. Ở database

Theo dõi:
- Query duration theo loại query.
- Execution plan.
- Rows scanned/returned.
- Active sessions và running queries.
- Lock wait và deadlock.
- CPU, memory, I/O.
- Connection limit.
- Transaction duration.
- Slow query.
- Index usage.

Một query có latency cao ở cả JDBC và R2DBC thường gợi ý bottleneck nằm ở SQL, index, database hoặc network thay vì API truy cập.

### 7.5. Ở network và downstream

Theo dõi:
- TCP connection/retransmission.
- RTT.
- DNS/TLS setup nếu có connection mới.
- Downstream p95/p99.
- Retry rate.
- External API timeout.
- Message broker latency.

Nếu transaction R2DBC giữ connection trong khi chờ downstream, pool có thể bão hòa dù database không bận.

## 8. Công cụ đo lường và quan sát

Có thể kết hợp các nhóm công cụ sau:

| Công cụ/nhóm | Mục đích |
|---|---|
| k6, Gatling, JMeter | Tạo HTTP workload |
| wrk/wrk2 hoặc công cụ tương đương | Tạo tải HTTP và đo latency/throughput |
| Spring Boot Actuator | Expose health và application metrics |
| Micrometer | Instrumentation và meter API |
| Prometheus + Grafana | Thu thập, truy vấn và hiển thị time-series |
| OpenTelemetry | Distributed tracing và context propagation |
| Java Flight Recorder (JFR) | Phân tích CPU, allocation, lock và runtime events |
| async-profiler | CPU/allocation profiling |
| Database EXPLAIN/EXPLAIN ANALYZE | Xem execution plan và chi phí query |
| Database monitoring | Session, lock, I/O và query statistics |

Không cần bật tất cả công cụ cùng lúc trong mọi lần chạy. Instrumentation quá nặng có thể làm thay đổi benchmark. Hãy bắt đầu với metrics nhẹ, sau đó chạy profiling riêng khi đã xác định khu vực nghi vấn.

### 8.1. Metrics qua Actuator/Micrometer

Ví dụ expose endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
~~~

Với Prometheus registry, scrape /actuator/prometheus. Tên meter thực tế phụ thuộc instrumentation và phiên bản. Kiểm tra endpoint metrics để xác nhận các meter đang tồn tại.

### 8.2. Distributed tracing

Trace giúp chia request thành các span:
- HTTP server.
- Service logic.
- R2DBC query.
- Downstream HTTP.
- Message publish.

Khi query span ngắn nhưng service span dài, phần chậm có thể nằm ở logic hoặc downstream. Khi query span dài, xem database và execution plan.

Không ghi raw SQL chứa giá trị nhạy cảm hoặc bind parameter vào trace. Dùng statement name, query fingerprint hoặc thông tin đã được mask.

### 8.3. JFR và profiling

JFR hữu ích để xác định:
- Thread đang block ở đâu.
- CPU hot method.
- Allocation hotspot.
- GC pause.
- Lock contention.
- Socket wait và thread scheduling.

Trong ứng dụng reactive, stack trace có thể không biểu diễn toàn bộ luồng nghiệp vụ vì execution chuyển qua nhiều callback và thread. Kết hợp trace ID, Reactor instrumentation và profiler để nối các phần.

## 9. Cách nhận biết bottleneck từ dấu hiệu

Bảng dưới đây là hướng điều tra, không phải kết luận tự động.

| Dấu hiệu | Bottleneck có thể nằm ở | Kiểm tra tiếp |
|---|---|---|
| CPU app cao, DB CPU thấp | Mapping, serialization, business logic hoặc blocking spin | CPU profile/JFR |
| CPU app thấp, DB CPU cao | Query hoặc database workload | Query plan, index, DB metrics |
| Acquired chạm max, pending tăng | Pool saturation hoặc connection giữ lâu | Transaction duration, acquire wait |
| Acquired thấp, pending vẫn tăng | Connection creation/validation/network hoặc metric mismatch | Create failure, connect latency, pool config |
| Query span dài, app CPU thấp | Database, lock hoặc network | EXPLAIN, lock wait, server query stats |
| Service span dài, query span ngắn | Logic, downstream hoặc queueing | Trace child spans |
| p99 cao nhưng p50 tốt | Tail latency, lock, GC, queue hoặc cold path | Histogram, trace mẫu chậm |
| Thread count rất cao trong JDBC | Blocking concurrency/thread-per-request pressure | Thread dump, thread state |
| Event-loop bị block trong WebFlux | Blocking call trên event-loop | BlockHound/JFR/thread dump |
| Memory tăng dần trong soak | Leak, buffer/queue/cache không giới hạn | Heap histogram, allocation profile |
| Database session cao hơn pool allocation | Nhiều instance/service hoặc connection khác | Tổng connection budget |
| Error tăng khi spike | Pool, queue, timeout hoặc DB limit | Error type, pending, DB rejection |

### 9.1. Dấu hiệu event-loop bị block

WebFlux thường dùng một số ít event-loop thread để điều phối nhiều connection. Một đoạn blocking trên event-loop có thể làm nhiều request không liên quan cùng bị chậm.

Tìm:
- JDBC call.
- block(), blockFirst(), blockLast().
- Thread.sleep.
- File I/O blocking.
- SDK đồng bộ.
- Lock hoặc synchronized kéo dài.
- CPU-heavy work không được tách khỏi event-loop.

Có thể dùng BlockHound trong test/development để phát hiện một số blocking call trên thread không cho phép blocking. BlockHound không thay thế profiling và không phát hiện mọi loại bottleneck.

### 9.2. Dấu hiệu database bottleneck

Nếu tăng application replica nhưng throughput không tăng và database CPU/lock wait đã cao, thêm instance có thể làm tình hình xấu hơn.

Hãy:
- Xem execution plan.
- Kiểm tra index.
- Giảm số query mỗi request.
- Tránh N+1.
- Chỉ đọc cột cần thiết.
- Giảm transaction/lock duration.
- Xem cache hoặc read model nếu phù hợp.

Đổi JDBC sang R2DBC không sửa một query plan kém.

### 9.3. Dấu hiệu pool bottleneck

Nếu pool pending tăng trong khi database còn capacity, có thể:
- Pool max size quá thấp.
- Transaction giữ connection lâu.
- Downstream call nằm trong transaction.
- Query/stream chưa kết thúc.
- Connection không được release.
- Acquire timeout hoặc connection validation chậm.

Đừng tăng pool trước khi biết database còn chịu được bao nhiêu session. Pool chỉ là hàng đợi trước database; mở thêm connection có thể đẩy bottleneck sang database.

## 10. Little's Law để hiểu concurrency và queueing

Little's Law mô tả quan hệ trong một hệ thống ổn định:

\[
L = \lambda W
\]

Trong đó:
- \(L\): số công việc trung bình đang ở trong hệ thống.
- \(\lambda\): throughput trung bình (công việc/giây).
- \(W\): thời gian trung bình một công việc ở trong hệ thống.

Ví dụ nếu hệ thống hoàn tất 200 request/second và thời gian phản hồi trung bình là 0.1 giây:

\[
L = 200 \times 0.1 = 20
\]

Trung bình có khoảng 20 request đang ở trong hệ thống.

Đây là cách ước lượng concurrency trung bình, không phải giới hạn pool hoặc số query đồng thời chính xác. Một request có thể thực hiện nhiều query tuần tự hoặc song song, và một số request không dùng database.

### 10.1. Queueing làm latency tăng nhanh gần saturation

Khi utilization của một tài nguyên tiến gần 100%, thời gian chờ có thể tăng rất nhanh. Vì vậy một pool hoạt động ở 99% không nhất thiết hiệu quả hơn pool ở 80% nếu p99 latency trở nên không ổn định.

Hãy giữ headroom phù hợp cho burst, connection creation, maintenance và workload khác. Mức headroom cần dựa trên dữ liệu production chứ không phải một tỷ lệ cố định.

### 10.2. Không áp dụng Little's Law sai phạm vi

Nếu throughput là HTTP RPS, W là HTTP latency thì L là số request trung bình trong hệ thống HTTP. Không thể dùng trực tiếp L đó làm số connection database.

Để ước lượng connection concurrency, cần biết:
- Tỷ lệ request truy cập DB.
- Số lần acquire trên request.
- Thời gian giữ connection.
- Mức song song của query.
- Số pool/replica.

## 11. So sánh JDBC và R2DBC một cách công bằng

Mục tiêu không phải chứng minh R2DBC luôn nhanh hơn. Mục tiêu là tìm mô hình phù hợp với workload, SLO và chi phí vận hành.

### 11.1. Các kịch bản cần so sánh

Nên chạy ít nhất các workload:

1. Read đơn giản theo primary key.
2. Read có filter, sort và pagination.
3. Query nhiều hàng/stream.
4. Insert đơn giản.
5. Update có optimistic locking.
6. Transaction gồm nhiều repository.
7. Mixed workload gần production.
8. Burst và soak test.

Một implementation có thể tốt hơn ở high concurrency nhưng không khác biệt ở tải thấp. Cần biết hệ thống thực sự cần đặc tính nào.

### 11.2. Giữ query semantics giống nhau

JDBC và R2DBC phải:
- Đọc cùng tập dữ liệu.
- Dùng cùng filter/sort.
- Trả cùng projection.
- Có transaction boundary tương đương.
- Dùng cùng index.
- Xử lý lỗi và retry tương đương.
- Áp dụng cùng authorization.
- Không có một bên cache kết quả còn bên kia không.

Nếu implementation R2DBC dùng query tối ưu hơn implementation JDBC, kết quả so sánh là tổng hợp của cả hai thay đổi. Hãy tách benchmark:
- So sánh driver với query tương đương.
- So sánh implementation tối ưu cuối cùng của từng lựa chọn.

Cả hai phép đo đều hữu ích nhưng trả lời câu hỏi khác nhau.

### 11.3. Không so sánh JDBC blocking trực tiếp trên event-loop

JDBC không được gọi trực tiếp trên WebFlux event-loop. Nếu benchmark JDBC trong WebFlux, cần chạy blocking work trên scheduler phù hợp, chẳng hạn boundedElastic hoặc một executor có giới hạn được thiết kế cho workload.

R2DBC chạy theo reactive pipeline. Hãy ghi rõ:
- Thread pool/scheduler của JDBC.
- Số worker.
- Queue limit.
- JDBC connection pool.
- R2DBC connection pool.
- Request concurrency.
- Database session.
- CPU và memory.

Nếu JDBC dùng thread pool không giới hạn hoặc R2DBC dùng pool quá lớn, so sánh sẽ không công bằng.

### 11.4. So sánh resource efficiency, không chỉ latency

R2DBC có thể giữ ít thread hơn khi nhiều request đang chờ I/O. Nhưng nó vẫn sử dụng connection database và vẫn chịu giới hạn query/database.

Đo:
- Throughput ở cùng SLO.
- p95/p99 latency.
- CPU trên mỗi request.
- Memory và allocation.
- Thread count.
- Context switching.
- Connection count.
- Pool wait.
- Database CPU.
- Độ phức tạp code và vận hành.

Nếu R2DBC giảm thread nhưng không cải thiện latency, điều đó vẫn có thể có giá trị nếu workload chủ yếu I/O-bound và giới hạn thread là vấn đề hiện tại. Nhưng nếu ứng dụng nhỏ, tải thấp và JDBC đáp ứng SLO với chi phí vận hành thấp hơn, chuyển đổi có thể không đáng.

### 11.5. Cùng mức tải và cùng SLO

Không so sánh:
- JDBC ở 100 RPS với R2DBC ở 1.000 RPS.
- Một bên warm cache, bên kia cold cache.
- Một bên dùng connection pool, bên kia tạo connection mới.
- Một bên dùng transaction, bên kia không.
- Một bên trả 20 field, bên kia chỉ trả 3 field.

Hãy tạo bảng so sánh ở nhiều mức tải và chỉ xem throughput là tốt khi error rate và latency vẫn nằm trong SLO.

## 12. Ví dụ tạo tải bằng k6

Một script đơn giản có thể kiểm tra API tìm kiếm:

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    search_orders: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 50,
      maxVUs: 300,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.001'],
    http_req_duration: ['p(95)<200', 'p(99)<500'],
  },
};

export default function () {
  const page = Math.floor(Math.random() * 10);
  const response = http.get(
    'https://test.example.com/orders?status=OPEN&page=' +
      page + '&size=20',
    {
      headers: {
        Authorization: 'Bearer ' + __ENV.TEST_TOKEN,
      },
      tags: {
        endpoint: 'order-search',
      },
    }
  );

  check(response, {
    'status is 200': (r) => r.status === 200,
    'response has body': (r) => r.body && r.body.length > 0,
  });
}
~~~

Đây là ví dụ script, không phải cấu hình phù hợp cho mọi hệ thống. Token phải lấy từ secret của môi trường test, không commit vào repository. URL và threshold cần thay bằng endpoint và SLO thật.

### 12.1. Đọc kết quả k6

Quan sát:
- http_reqs: tổng request và rate.
- http_req_duration: latency của HTTP request.
- http_req_failed: tỷ lệ request lỗi.
- dropped_iterations: iteration không thể khởi chạy theo arrival rate do thiếu VU hoặc giới hạn generator.
- vus và vus_max: mức sử dụng virtual users.

Nếu dropped iterations tăng, generator có thể không tạo được tải yêu cầu. Không kết luận server chỉ nhận được đúng RPS mục tiêu nếu generator đã bị giới hạn.

### 12.2. Thêm nhiều scenario

Một script gần production hơn có thể tách:
- Read by ID.
- Search.
- Create.
- Update.
- History.
- Report.

Dùng tỷ lệ tương ứng với workload đã quan sát. Với write test, tạo dữ liệu có key duy nhất hoặc reset fixture có kiểm soát để tránh benchmark bị ảnh hưởng bởi duplicate constraint và dữ liệu tích lũy.

## 13. Đo hiệu năng ở cấp database

### 13.1. Kiểm tra execution plan

Với query chậm, dùng công cụ EXPLAIN của database. Với PostgreSQL, EXPLAIN ANALYZE thực thi query và đo thời gian thực tế, nên chỉ dùng cẩn thận trên môi trường test hoặc query an toàn.

Xem:
- Sequential scan hay index scan.
- Estimated rows so với actual rows.
- Join strategy.
- Sort và hash operation.
- Rows removed by filter.
- Buffer hits/reads.
- Planning time và execution time.

Không tối ưu pool khi query plan là nguyên nhân chính.

### 13.2. Đếm query trên mỗi request

Một request có thể gọi nhiều repository liên tiếp. Nếu một endpoint tạo N+1 query, latency tăng dù từng query riêng lẻ rất nhanh.

Theo dõi:
- Số query/request.
- Tổng database time/request.
- Query fingerprint.
- Số rows đọc.
- Số lần round trip.
- Tỷ lệ query lặp.

Có thể giảm round trip bằng join/projection, batch hoặc query phù hợp. Nhưng không làm một query khổng lồ nếu nó gây plan kém hoặc trả quá nhiều dữ liệu.

### 13.3. Kiểm tra transaction và lock

Transaction dài có thể giữ lock, làm request khác chờ. Theo dõi:
- Transaction age.
- Lock wait.
- Deadlock.
- Idle in transaction.
- Long-running query.
- Commit/rollback latency.

R2DBC không loại bỏ lock semantics của database. Cùng SQL và cùng isolation level vẫn chịu hành vi khóa từ hệ quản trị.

## 14. Đánh giá bottleneck theo từng lớp bằng một quy trình

Khi load test cho kết quả xấu, đừng thay nhiều cấu hình cùng lúc. Hãy điều tra theo trình tự để xác định lớp gây giới hạn.

### Bước 1: Xác nhận load generator

- Có đạt arrival rate yêu cầu không?
- Có dropped iteration không?
- CPU/network generator có bão hòa không?
- Generator có đủ VU và socket không?

### Bước 2: Xác nhận API behavior

- Request có thực hiện đúng use case không?
- Có lỗi validation hoặc auth làm request kết thúc sớm không?
- Có cache hit bất thường không?
- Response có cùng kích thước giữa các lượt không?

### Bước 3: Xem application resource

- CPU app có cao không?
- Heap/GC có bất thường không?
- Event-loop có bị block không?
- Thread/scheduler queue có tăng không?
- Mapping/serialization có chiếm CPU không?

### Bước 4: Xem pool

- Acquired có chạm max không?
- Idle có bằng 0 không?
- Pending có tăng không?
- Acquire timeout có xuất hiện không?
- Connection creation có lỗi không?

### Bước 5: Xem database

- Query latency có tăng không?
- CPU/I/O có cao không?
- Có lock wait/deadlock không?
- Có quá nhiều session không?
- Query plan có thay đổi không?

### Bước 6: Xem downstream và network

- Có HTTP call nằm trong transaction không?
- Downstream latency có tăng không?
- Network RTT/retransmission có bất thường không?
- Retry có khuếch đại tải không?

### Bước 7: Thay một biến và chạy lại

Ví dụ nếu nghi query chậm:
- Chạy EXPLAIN.
- Thêm/điều chỉnh index trong nhánh test.
- Chạy lại cùng workload.
- So sánh latency và DB resource.

Không đồng thời tăng pool, CPU, heap, replica và thay query. Nếu kết quả cải thiện, bạn sẽ không biết thay đổi nào thực sự giải quyết bottleneck.

## 15. Đánh giá lựa chọn R2DBC theo workload

R2DBC thường phù hợp hơn khi:
- Ứng dụng đã dùng WebFlux và cần reactive end-to-end.
- Có nhiều request đồng thời chủ yếu chờ I/O.
- Thread-per-request hoặc blocking pool đang là giới hạn đo được.
- Driver R2DBC cho database mục tiêu ổn định và đáp ứng tính năng cần dùng.
- Đội ngũ hiểu Reactor, cancellation, transaction context và debugging reactive.
- Hệ thống có thể đo lường và vận hành pool reactive.

JDBC có thể phù hợp hơn khi:
- Workload hiện tại đáp ứng SLO với chi phí thấp.
- Phần lớn bottleneck nằm ở query/database chứ không phải thread blocking.
- Ứng dụng dùng JPA sâu với persistence context, lazy loading hoặc ecosystem phụ thuộc.
- Driver R2DBC thiếu tính năng hoặc behavior cần thiết.
- Đội ngũ chưa có khả năng vận hành reactive.
- Migration cost và rủi ro lớn hơn lợi ích đo được.
- Ứng dụng chủ yếu batch/CPU-bound và không có nhu cầu reactive end-to-end.

Không nên chọn chỉ dựa trên benchmark micro của một query. Hãy xem tổng chi phí:
- Hiệu năng ở workload thật.
- Tài nguyên ở mức SLO.
- Chi phí migration.
- Khả năng debug.
- Mức trưởng thành của driver.
- Observability.
- Độ phức tạp code.
- On-call và kỹ năng đội ngũ.

### 15.1. R2DBC không tự giảm số connection database

Một ứng dụng reactive có thể phục vụ nhiều request đồng thời với ít thread hơn, nhưng mỗi thao tác database vẫn cần connection theo thời gian sử dụng. Nếu tăng concurrency quá cao, R2DBC vẫn có thể làm pool pending tăng và database quá tải.

Phải giới hạn concurrency và connection theo capacity database. Không chuyển từ 200 thread JDBC sang 2.000 query R2DBC đồng thời mà không đo.

### 15.2. R2DBC không tự tối ưu SQL

Nếu query cần 800 ms do full table scan, R2DBC không làm query đó thành 20 ms chỉ vì API non-blocking. Thời gian database vẫn chiếm phần lớn latency.

Tối ưu query, index, projection và transaction trước hoặc song song với quyết định driver. Tách riêng tác động của từng thay đổi để biết nguồn cải thiện.

### 15.3. Reactive stack cần nhất quán

Nếu WebFlux gọi JDBC blocking trực tiếp trên event-loop, lợi ích reactive bị phá vỡ. Nếu phải tích hợp JDBC tạm thời, chạy blocking call trên scheduler/executor phù hợp và giới hạn concurrency. Ghi nhận đây là một đoạn blocking trong kiến trúc.

Không phải mọi thành phần trong ứng dụng đều phải reactive bằng mọi giá. Chọn ranh giới theo workload và lợi ích vận hành.

## 16. Ví dụ bảng kết quả benchmark

Giả sử chạy cùng một workload mixed read/write trên môi trường test tương đương:

| Chỉ số | JDBC | R2DBC |
|---|---:|---:|
| Throughput đạt trong SLO | 420 RPS | 610 RPS |
| p50 | 42 ms | 39 ms |
| p95 | 180 ms | 145 ms |
| p99 | 520 ms | 410 ms |
| CPU app | 72% | 64% |
| Heap peak | 1.8 GB | 1.5 GB |
| Thread peak | 420 | 110 |
| DB CPU | 68% | 70% |
| Acquire/pool wait p95 | 12 ms | 18 ms |
| Error rate | 0.08% | 0.06% |

Các số trên hoàn toàn minh họa, không phải kết quả đo thực tế hay dự báo cho mọi ứng dụng.

Cách diễn giải:
- R2DBC đạt throughput cao hơn trong SLO ở workload này.
- p95/p99 cải thiện nhưng pool wait lại tăng nhẹ.
- Thread count giảm đáng kể.
- Database CPU gần như không đổi, cho thấy database vẫn làm lượng công việc tương đương.
- Cần kiểm tra thêm soak test, cancellation, lỗi driver và chi phí vận hành trước quyết định.

Không chỉ nói "R2DBC nhanh hơn 45%". Hãy nói rõ workload, môi trường, mức tải, SLO và độ biến thiên của kết quả.

## 17. Mẫu báo cáo benchmark

Một báo cáo có thể dùng cấu trúc:

~~~text
Tên workload:
Phiên bản ứng dụng:
JDK:
Spring Boot:
Spring Data:
R2DBC driver:
Database version:
Dataset size:
Application replicas:
CPU/memory limit:
JDBC pool configuration:
R2DBC pool configuration:
Load generator:
Test duration:
Warm-up duration:
Arrival model:
Target RPS/concurrency:

Kết quả:
- Throughput:
- p50/p95/p99:
- Error/timeout:
- CPU:
- Heap/GC:
- Thread count:
- Pool acquired/idle/pending:
- Acquire latency:
- DB CPU/I/O:
- Query latency:
- Active sessions:
- Rows/request:
- Response bytes:

Bottleneck quan sát được:
Thay đổi đã thử:
Tác động của thay đổi:
Giới hạn còn lại:
Kết luận và quyết định:
~~~

Báo cáo phải ghi cả cấu hình và điều kiện test. Một con số latency không có workload, dataset và môi trường đi kèm không thể tái lập.

## 18. Những sai lầm thường gặp khi đo tải

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ đo một endpoint đơn giản | Không phản ánh workload production | Dùng workload mix |
| Dataset quá nhỏ | Kết quả chủ yếu phản ánh cache | Dùng dữ liệu đủ lớn và phân bố hợp lý |
| Không warm-up JVM | Đo cả startup/JIT vào kết quả | Tách warm-up khỏi measurement |
| Load generator chạy cùng máy app | Generator cạnh tranh CPU/network | Chạy generator riêng |
| Chỉ xem average latency | Che giấu tail latency | Theo dõi p95/p99 |
| Closed model được coi như fixed RPS | Server chậm làm generator tự giảm tải | Chọn open model khi cần arrival rate cố định |
| Không kiểm tra dropped iterations | Tưởng server nhận đủ tải | Theo dõi khả năng phát tải của generator |
| So sánh query khác nhau | Không biết cải thiện đến từ driver hay SQL | Giữ query semantics giống nhau |
| JDBC chạy trên event-loop | Benchmark không hợp lệ và làm block event-loop | Cô lập JDBC blocking |
| Chỉ đo thread count | Không biết database/pool có bottleneck không | Đo toàn stack |
| Tăng pool để sửa mọi vấn đề | Có thể làm DB quá tải | Tìm nguyên nhân connection hold/query |
| Không theo dõi transaction duration | Bỏ sót connection bị giữ khi chờ downstream | Instrument transaction và trace |
| Không chạy soak test | Bỏ sót leak và suy giảm dài hạn | Chạy test đủ lâu |
| Bật profiler nặng trong mọi lượt | Làm sai số liệu benchmark | Tách performance run và profiling run |
| Chọn kết quả tốt nhất trong nhiều lần | Thiên lệch kết quả | Lặp lại và báo khoảng biến thiên |
| Kết luận R2DBC luôn nhanh hơn | Bỏ qua workload và chi phí migration | Đánh giá theo SLO và tổng chi phí |

## 19. Quy trình thực hành từ đầu đến cuối

1. Xác định SLO và mục tiêu capacity cho từng use case.
2. Thu thập tỷ lệ endpoint, query, page size và read/write từ workload thật.
3. Tạo dataset có kích thước và phân bố phù hợp.
4. Chuẩn hóa môi trường app, database, JVM và network.
5. Chọn load model open/closed phù hợp.
6. Chạy smoke test để xác nhận script và dữ liệu.
7. Warm-up ứng dụng và database theo quy trình cố định.
8. Chạy load test ở tải dự kiến và ghi p50/p95/p99, throughput, error.
9. Chạy stress/spike/soak để tìm saturation và vấn đề dài hạn.
10. Thu thập metrics HTTP, JVM, pool, database và downstream.
11. Dùng trace, JFR và execution plan để xác định bottleneck.
12. Thay một biến mỗi lần và chạy lại cùng workload.
13. Benchmark JDBC và R2DBC với query semantics và SLO tương đương.
14. So sánh resource efficiency, không chỉ latency.
15. Ghi giới hạn, độ biến thiên và chi phí vận hành.
16. Chọn R2DBC chỉ khi kết quả phù hợp mục tiêu và lợi ích vượt chi phí chuyển đổi.

## 20. Bài tập tự kiểm tra

### Bài 1: Throughput và latency

R2DBC đạt 700 RPS nhưng p99 là 2 giây, trong khi JDBC đạt 500 RPS và p99 là 300 ms. Có thể kết luận R2DBC tốt hơn không?

Gợi ý: Không nếu SLO p99 là 500 ms. Throughput cao hơn không bù được việc vi phạm latency SLO.

### Bài 2: Average và percentile

Average latency là 80 ms nhưng p99 là 3 giây. Bạn cần kiểm tra gì?

Gợi ý: Trace các request chậm, query/lock, GC, pool wait, downstream và queueing. Average che giấu tail latency.

### Bài 3: Load generator

k6 được cấu hình 1.000 RPS nhưng dropped iterations tăng. Có thể kết luận server đã xử lý 1.000 RPS không?

Gợi ý: Không. Generator không khởi chạy được toàn bộ iteration theo lịch; cần xác nhận request rate thực tế và capacity của generator.

### Bài 4: Database bottleneck

JDBC và R2DBC có query latency gần như giống nhau, database CPU đạt 95%. Nên điều tra gì trước?

Gợi ý: Query plan, index, rows scanned, lock và database capacity. Thay driver không giải quyết bottleneck SQL/database.

### Bài 5: Pool saturation

R2DBC acquired chạm max, idle bằng 0 và pending tăng. Database CPU thấp. Những nguyên nhân nào cần kiểm tra?

Gợi ý: Transaction dài, downstream call trong transaction, stream chậm, connection leak, pool config hoặc connection validation/create.

### Bài 6: Event-loop

CPU thấp nhưng nhiều request WebFlux cùng chậm và thread dump cho thấy event-loop đang chờ JDBC. Kết luận gì?

Gợi ý: Blocking call trên event-loop đang làm nghẽn nhiều request. Cô lập blocking hoặc chuyển đường truy cập sang non-blocking.

### Bài 7: Workload model

Bạn muốn duy trì đúng 500 request/second bất kể response chậm. Nên dùng open hay closed model?

Gợi ý: Open model với arrival rate cố định, đồng thời theo dõi dropped iterations và queue của generator.

### Bài 8: So sánh công bằng

R2DBC dùng query có index mới, JDBC dùng query cũ. Benchmark chứng minh R2DBC nhanh hơn. Kết luận này có đủ để quy lợi ích cho R2DBC không?

Gợi ý: Không. Cần một phép so sánh query tương đương để tách tác động driver khỏi tối ưu SQL.

### Bài 9: Little's Law

Throughput 100 RPS, average latency 200 ms. Số request trung bình đang ở trong hệ thống khoảng bao nhiêu?

Gợi ý: \(L = 100 \times 0.2 = 20\) request. Đây là concurrency HTTP trung bình, không phải số connection database.

### Bài 10: Quyết định công nghệ

Ứng dụng có 50 RPS, JDBC đáp ứng SLO, database là bottleneck và đội ngũ chưa có kinh nghiệm Reactor. Có nên chuyển R2DBC chỉ để tăng tốc database không?

Gợi ý: Không có cơ sở để kỳ vọng R2DBC làm query nhanh hơn. Hãy tối ưu database trước và đánh giá lợi ích reactive so với chi phí migration/vận hành.

## 21. Ghi nhớ

- Đo tải phải bắt đầu từ SLO và workload đại diện, không phải một con số RPS tùy ý.
- Theo dõi throughput, p50/p95/p99, error rate, concurrency và saturation cùng nhau.
- Average latency không đủ để hiểu tail latency.
- Workload open model giữ arrival rate; closed model giữ số virtual users và phụ thuộc response time.
- Kiểm tra dropped iterations để chắc chắn load generator phát đủ tải.
- Dataset, cache, index, JVM, network và database phải được kiểm soát khi so sánh.
- Tách warm-up khỏi measurement và lặp lại nhiều lần.
- Thu thập telemetry từ HTTP, JVM, R2DBC pool, database, network và downstream.
- Acquired là connection đang được mượn, không phải số query đang chạy.
- Kết hợp pool pending với transaction duration và query latency để tìm nguyên nhân.
- Dùng trace, JFR/profiling và EXPLAIN để xác định bottleneck thay vì thay nhiều cấu hình cùng lúc.
- R2DBC có thể giảm áp lực thread khi I/O-bound concurrency cao; nó không tự tối ưu SQL hoặc tăng database capacity.
- JDBC blocking không được chạy trên WebFlux event-loop; benchmark phải cô lập blocking đúng cách.
- So sánh JDBC/R2DBC với cùng query semantics, dataset, workload, SLO và môi trường.
- Đo resource efficiency, error, tail latency và chi phí vận hành, không chỉ throughput.
- Chạy load, stress, spike và soak test vì mỗi loại phát hiện một dạng giới hạn khác nhau.
- Chọn R2DBC khi lợi ích đo được phù hợp workload và vượt chi phí migration, debugging và vận hành.

Đánh giá R2DBC cần dựa trên bằng chứng từ workload thật. Hãy xác định SLO, tạo tải có kiểm soát, đo từ HTTP đến JVM, pool và database, rồi xử lý bottleneck theo từng lớp. Khi so sánh JDBC với R2DBC trên cùng dữ liệu và cùng hợp đồng, bạn có thể biết mô hình nào đáp ứng tải tốt hơn, dùng tài nguyên hiệu quả hơn và phù hợp với khả năng vận hành của đội ngũ.

