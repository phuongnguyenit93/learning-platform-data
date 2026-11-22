# Đo hiệu năng toàn luồng trước khi tối ưu từng thành phần

## 1. Mục tiêu

Trong kiến trúc Software Design, System Architecture và Microservices, một thao tác người dùng có thể đi qua frontend, API Gateway, nhiều dịch vụ, cache, database, broker và hệ thống bên ngoài. Việc một hàm Java chạy nhanh hơn 50% không có nghĩa toàn bộ hành trình người dùng nhanh hơn 50%. Nếu thời gian chờ ở một dependency khác mới là nút thắt, thay đổi cục bộ có thể gần như không tạo ra lợi ích nhìn thấy được.

**Nguyên tắc chủ đạo: đo hiệu năng toàn luồng (end-to-end) trên hành trình và tải đại diện, xác định đường đi quyết định thời gian hoàn tất, sau đó mới chọn thành phần để tối ưu.**

Bài học giúp người đọc:

- Phân biệt latency từ người dùng, thời gian API server, thời gian từng span và thời gian hoàn tất nghiệp vụ.
- Xác định phạm vi đo, SLI/SLO, baseline và traffic profile trước khi thay đổi hệ thống.
- Đọc distributed traces, waterfall, service dependency và critical path để tìm vị trí chặn tiến độ.
- Hiểu percentiles, tail latency, concurrency, throughput, error rate, saturation và hàng đợi.
- Chọn cách kiểm tra CPU, database, cache, mạng, queue, lock, external dependency sau khi có bằng chứng toàn luồng.
- Thiết kế phép thử có đối chứng để xác nhận tối ưu thực sự cải thiện kết quả của người dùng.
- Tránh tối ưu nhầm một thành phần không nằm trên critical path hoặc cải thiện latency nhưng làm sai dữ liệu.
- Triển khai dashboard, tracing, load test và quy trình theo dõi regression hiệu năng.

## 2. Vì sao tối ưu từng thành phần trước dễ gây sai lầm?

Giả sử một request tạo đơn mất tổng cộng 2.000 ms:

| Công đoạn | Thời gian quan sát |
|---|---:|
| Nhận request, xác thực | 100 ms |
| Đọc thông tin giỏ hàng | 150 ms |
| Tính giá/khuyến mãi | 100 ms |
| Chờ Payment Provider | 1.450 ms |
| Ghi Order | 150 ms |
| Trả response | 50 ms |
| **Tổng (giả định tuần tự)** | **2.000 ms** |

Nếu tối ưu phần tính giá từ 100 ms còn 20 ms, tổng lý tưởng giảm từ 2.000 xuống 1.920 ms, tức khoảng 4%, dù riêng thành phần đã nhanh hơn 80%.

Ngược lại, nếu điều tra thấy lời gọi Payment đang retry hai lần hoặc chờ connection pool không cần thiết, xử lý nguyên nhân này có thể mang lại cải thiện lớn hơn. Nhưng chỉ biết Payment dài 1.450 ms chưa đủ kết luận lỗi tại Provider: khoảng đó có thể bao gồm network, client-side queue, timeout, retry/backoff hoặc xử lý ở Payment Service.

Từ đó có ba bài học:

1. **Tối ưu cục bộ không tương đương tối ưu toàn hệ thống.** Cần đo hiệu quả trên end-to-end latency.
2. **Span dài không tự là nguyên nhân gốc.** Cần phân tách đoạn chờ, xử lý, retry và quan hệ phụ thuộc.
3. **Một số thành phần chạy song song.** Tổng duration của các span không bằng tổng thời gian người dùng chờ.

Nếu chỉ dựa vào profiler của một service, đội phát triển có thể mất nhiều ngày tối ưu CPU nơi request chỉ tiêu 2% thời gian, trong khi chưa xem các dependency đang chặn response.

## 3. Định nghĩa "toàn luồng" theo mục tiêu người dùng

Trước khi đo, phải thống nhất **điểm bắt đầu** và **điểm kết thúc**. Có ít nhất bốn phạm vi đo thường gặp:

| Phạm vi | Điểm bắt đầu | Điểm kết thúc | Mục tiêu |
|---|---|---|---|
| Trải nghiệm người dùng | Người dùng bắt đầu thao tác | UI hiển thị kết quả sử dụng được | End-user latency |
| Client/network | Client gửi request | Client nhận response đầy đủ | Client-observed API latency |
| Server request | API/Gateway nhận request | Server phát response | Server-side latency |
| Nghiệp vụ bất đồng bộ | Tạo yêu cầu nghiệp vụ | Kết quả nghiệp vụ thật sự hoàn tất | Business completion latency |

Ví dụ POST /reports trả 202 Accepted trong 50 ms nhưng báo cáo chỉ sẵn sàng sau 8 phút:

~~~text
T0: người dùng yêu cầu tạo báo cáo
T1: API trả 202 Accepted
T2: message được consumer lấy từ queue
T3: worker hoàn tất file
T4: người dùng nhìn thấy link download
~~~

Trong trường hợp này:

- HTTP API latency = T1 - T0.
- Queue waiting time = T2 - lúc enqueue.
- Processing time = T3 - T2.
- Business completion latency = T3 - T0.
- User-visible completion latency = T4 - T0.

Một dashboard chỉ đo HTTP 202 có thể báo "rất nhanh" trong khi người dùng vẫn đợi nhiều phút. Phải lựa chọn phạm vi phù hợp với cam kết sản phẩm.

### 3.1. Backend nhanh chưa chắc frontend nhanh

Giao diện có thể bị chậm vì JavaScript bundle lớn, hydration, rendering, API waterfall trên trình duyệt, retry hoặc hiển thị skeleton quá lâu. Cần thêm Real User Monitoring (RUM), browser timings và client-side spans khi trải nghiệm tương tác là mục tiêu.

Ví dụ API phản hồi trong 150 ms nhưng UI mất 1.200 ms để render danh sách lớn. Tối ưu SQL từ 150 xuống 100 ms chỉ cải thiện một phần nhỏ thời gian người dùng nhận được giao diện sẵn sàng.

### 3.2. Không đo lẫn các loại hành trình

Đăng nhập, tìm kiếm, thanh toán, tải dashboard và export dữ liệu có traffic, dependency và SLO khác nhau. Tránh dùng một con số "latency trung bình toàn ứng dụng" làm mục tiêu chung.

Mỗi hành trình trọng yếu nên có contract riêng về điểm bắt đầu, kết thúc, outcome, người dùng/cohort, loại dữ liệu và trạng thái thành công.

## 4. SLI, SLO và performance budget

**SLI (Service Level Indicator)** là phép đo chất lượng, ví dụ tỷ lệ checkout hoàn tất dưới hai giây và không sai dữ liệu.

**SLO (Service Level Objective)** là mục tiêu đặt trên SLI trong một cửa sổ, ví dụ 99% checkout hợp lệ hoàn tất trong 2 giây trong 28 ngày.

**Performance budget** là cách phân bổ ngân sách thời gian của toàn luồng thành các mục tiêu/giới hạn con nhằm định hướng thiết kế.

Ví dụ:

~~~text
SLO: 99% GET /product-page có kết quả đúng dưới 1.000 ms

Ngân sách tham khảo:
  Client/network        150 ms
  Gateway/auth           80 ms
  Product API           200 ms
  Inventory/Pricing     250 ms (fan-out)
  Render/UI             200 ms
  Dự phòng              120 ms
~~~

Các số trên chỉ là phân bổ thiết kế, không phải mọi yêu cầu đều có đúng cấu trúc đó. Với fan-out song song, ngân sách phải dựa vào nhánh chặn, không cộng thẳng duration của các child span trùng thời gian.

Một performance budget hữu ích khi:

- Dựa trên mục tiêu cuối cùng có ý nghĩa với người dùng.
- Mỗi phần có chủ sở hữu, metric và cách đo cụ thể.
- Có dự phòng cho network variance, GC và tail latency.
- Được điều chỉnh khi topology hoặc dependency thay đổi.
- Không bị dùng như lý do tối ưu cục bộ không cần thiết.

**Chỉ số thành công cần kết hợp tốc độ với tính đúng đắn.** Một endpoint trả nhanh dữ liệu sai hoặc response bị cắt bớt không phải một cải thiện hiệu năng hợp lệ.

## 5. Các thước đo bắt buộc trước khi tối ưu

Một số chỉ số thường được xem như "golden signals" của vận hành:

| Nhóm | Đo điều gì | Ví dụ |
|---|---|---|
| Latency | Thời gian hoàn tất, phân bố và tail | p50/p95/p99 checkout |
| Traffic | Lượng yêu cầu và mức tải | RPS theo route, requests/second/Pod |
| Errors | Lỗi kỹ thuật/nghiệp vụ | 5xx, timeout, checkout failed |
| Saturation | Mức độ chạm trần tài nguyên | CPU throttling, DB pool wait |
| Concurrency | Công việc đang xử lý/chờ | In-flight HTTP, active threads |
| Queue | Công việc chưa được xử lý | Queue depth, oldest message age |
| Correctness | Hệ thống có hoàn thành đúng không | Đơn không trùng, tiền không sai |
| Cost | Tài nguyên cho một đơn vị công việc | CPU-seconds/request, DB queries/request |

Không chỉ lấy latency trung bình. Hai hệ thống có cùng average 200 ms nhưng một hệ thống p99 = 3.000 ms và hệ thống kia p99 = 400 ms sẽ tạo trải nghiệm rất khác cho nhóm người dùng chậm nhất.

### 5.1. Mean, median, p95 và p99

- **Mean:** trung bình cộng; nhạy với các giá trị rất lớn.
- **Median/p50:** một nửa request có latency thấp hơn hoặc bằng ngưỡng.
- **p95:** khoảng 95% request có latency không vượt quá ngưỡng.
- **p99:** khoảng 99% request nằm trong ngưỡng, phần đuôi còn lại có thể chậm hơn.

Ví dụ 99 request mất 100 ms, một request mất 10.000 ms. Trung bình xấp xỉ 199 ms, dễ làm người đọc tưởng hệ thống ổn, trong khi một người dùng chờ 10 giây.

Cần biểu diễn p95/p99 cùng **số mẫu, traffic mix và khoảng thời gian**. Với canary chỉ vài chục request, p99 có độ bất định lớn. Không dùng p99 của 100 request như thể nó đáng tin bằng p99 của một triệu request.

### 5.2. Không lấy trung bình các percentile

Nếu từng instance báo p95 riêng, trung bình các p95 **không** phải p95 toàn hệ thống. Cần tổng hợp phân bố gốc hoặc histogram buckets đúng cách rồi tính percentile trên phân bố đã hợp nhất.

Điều này quan trọng khi tính p95 across pods, regions, services hoặc version. Phải kiểm tra các histogram có cùng đơn vị và bucket scheme phù hợp trước khi gộp.

### 5.3. Đừng để lỗi bị loại khỏi mẫu đo một cách vô hình

Nếu request timeout bị ghi nhận như thất bại nhưng không có latency sample trong histogram, p95 của các request thành công có thể trông tốt hơn khi hệ thống đang tệ đi.

Theo dõi cùng nhau:

- Latency của thành công.
- Latency/cancellation/timeout của thất bại.
- Success rate và tỷ lệ deadline met.
- Business completion outcome.
- Số request bỏ cuộc trước khi nhận kết quả.

Một phép đo hiệu năng cần mô tả rõ điều kiện lọc, không chỉ đưa một số p95 không có ngữ cảnh.

## 6. Thiết lập baseline trước mọi thay đổi

**Baseline** là tập số liệu trước khi tối ưu, được lấy trong điều kiện có thể tái hiện và đủ đại diện. Ghi nhận:

1. Commit/image digest, service versions, cấu hình, feature flags và schema.
2. Hạ tầng: CPU, memory, pod/node count, region, autoscaling policy.
3. Dữ liệu: kích thước bảng, số lượng bản ghi, index, cache state.
4. Tải: RPS, concurrency, mix route, request payload, tenant/region.
5. Môi trường: staging hay production, dependencies thật hay giả lập.
6. Kết quả: p50/p95/p99, throughput, error rate, queue lag, saturation.
7. Trace/log: một số request nhanh/chậm/lỗi có cùng correlation context.
8. Business outcome: thành công, duplicate, thiếu event, data freshness.

Một baseline không gồm lưu lượng và dữ liệu thường khó dùng để so sánh. Ví dụ SQL chạy nhanh trên bảng 10.000 hàng ở staging nhưng chậm trên bảng 100 triệu hàng ở production.

### 6.1. Baseline từ production và từ lab khác nhau

Production metrics giúp biết hành vi thực, tỷ lệ route và mức tải. Load-test environment giúp lặp lại điều kiện và thực hiện đối chứng. Cần sử dụng cả hai theo đúng mục đích.

Không chạy tải nguy hiểm lên production nếu chưa có kế hoạch an toàn. Với hệ thống tài chính, dùng synthetic transaction hoặc sandbox được kiểm soát, không tạo giao dịch thật không thể hoàn tác.

## 7. Phân rã request bằng distributed tracing

**Trace** mô tả hành trình của một yêu cầu qua các service. **Span** biểu diễn một đơn vị công việc có start/end, parent, thuộc tính và event.

Sơ đồ:

~~~text
User -> Gateway -> Checkout Service
                      |
                      +---> Cart Service ------> Database
                      |
                      +---> Inventory Service -> Redis/DB
                      |
                      +---> Pricing Service ---> Cache
                      |
                      +---> Payment Service ---> Provider
                      |
                      +---> Order Service -----> Database
~~~

Một trace có thể gồm:

~~~text
Trace checkout-abc
  Gateway.POST /checkout          0 -------------------- 1900
    Checkout.POST /checkout      20 ------------------ 1880
      cart.read                  30 ------- 250
      inventory.reserve        260 ------------ 760
      pricing.calculate        260 ------ 460
      payment.authorize        800 ----------------- 1610
      order.persist           1640 -------- 1800
~~~

Đây là ví dụ thời gian tương đối. Người phân tích cần hỏi:

- Các bước có thực sự nối tiếp hay chạy song song?
- Thời điểm nào service bắt đầu chờ kết quả từ một dependency?
- Có khoảng trống giữa các span cho công việc chưa instrument?
- CLIENT span và SERVER span của một RPC có chênh lệch bất thường?
- Có retry, timeout, queue wait, lock wait hoặc connection wait?
- Trace ID, span ID và parent relationship có được propagate đúng không?
- Một span ERROR có được retry/fallback thành công hay là nguyên nhân request thất bại?

Span duration dài có thể chủ yếu là thời gian chờ, không nhất thiết là CPU. Nên kết hợp span events, profiler, dependency metrics và logs thay vì quy toàn bộ thời gian cho code của service sở hữu span.

### 7.1. Trace context xuyên dịch vụ

Với HTTP, W3C Trace Context thường truyền traceparent và tracestate. Instrumentation tạo CLIENT span phía gọi và SERVER span phía nhận; các span giữ trace context để kết nối waterfall.

Với thread pool, reactive streams, message queues và batch jobs, context có thể bị mất nếu không được capture/restore đúng. Một trace bị thiếu span không chứng minh bước đó không chạy; có thể là sampling, exporter drop hoặc instrumentation gap.

### 7.2. Attributes và events có thể hành động

Thông tin hữu ích:

- service.name và service.version.
- Route template, HTTP method, status/outcome.
- DB operation/system và dependency name.
- Queue name, message age, retry attempt.
- Cache hit/miss và key class (không phải raw key nhạy cảm).
- Event tại fork, join, transaction commit hoặc provider response.
- Trace ID để mở log tương ứng.

Tránh ghi access token, cookie, mật khẩu, dữ liệu cá nhân nhạy cảm hoặc toàn bộ payload vào trace.

## 8. Critical path: hiểu đoạn thời gian thực sự chặn kết quả

**Critical path** là chuỗi bước có quan hệ phụ thuộc quyết định thời điểm yêu cầu hoàn tất. Việc tối ưu một nhánh ngoài critical path có thể làm nhánh đó nhanh hơn nhưng không cải thiện tổng latency.

### 8.1. Trường hợp tuần tự

Nếu request phải qua A -> B -> C -> D không overlap:

~~~text
A: 100 ms
B: 300 ms
C: 700 ms
D: 100 ms

Total = 100 + 300 + 700 + 100 = 1200 ms
~~~

Tối ưu C từ 700 xuống 350 ms giảm total lý tưởng xuống 850 ms.

### 8.2. Trường hợp song song

Giả sử A, B, C chạy cùng lúc rồi phải đợi **tất cả** trước Payment:

~~~text
            +---- A: 300 ms ----+
Checkout ---+---- B: 700 ms ----+---- Join ---- Payment: 400 ms
            +---- C: 450 ms ----+
                                                  |
                                               Save: 100 ms
~~~

Tổng lý tưởng:

~~~text
Total = max(300,700,450) + 400 + 100 = 1200 ms
~~~

B là nhánh chặn tại điểm join. Nếu A giảm từ 300 còn 50 ms, total không đổi. Nếu B giảm còn 400 ms, C = 450 ms sẽ trở thành nhánh chặn; total còn khoảng 950 ms.

Đây là ví dụ về **nút thắt di chuyển**: sau khi tối ưu một phần, phải đo lại vì phần khác có thể thành critical path mới.

### 8.3. Parent span không được cộng trùng

Một parent span có duration 1.200 ms có thể bao phủ child span 700 ms, 400 ms và các khoảng local work. Không cộng 1.200 + 700 + 400 để tính end-to-end: parent đã chứa thời gian con. Các child overlap cũng không được cộng như thực thi tuần tự.

Nếu không biết rõ join policy, timestamp hoặc asynchronous relationships, critical path chỉ là **giả thuyết**; bổ sung event tại điểm đồng bộ hoặc kiểm tra code thực thi để xác định.

### 8.4. First-success, quorum và speculative calls

Không phải mọi nhánh song song đều chờ tất cả. Một hệ thống có thể kết thúc khi replica nhanh nhất trả kết quả hợp lệ hoặc khi đạt quorum. Khi đó nhánh dài nhất không nhất thiết chi phối response.

Do vậy, waterfall timeline chỉ là một phần của bằng chứng; cần biết dependency semantics của từng giai đoạn.

## 9. Ví dụ toàn luồng: Checkout 1.800 ms

Dữ liệu trace giả định:

| Span | Bắt đầu (ms) | Kết thúc (ms) | Duration (ms) |
|---|---:|---:|---:|
| checkout.root | 0 | 1800 | 1800 |
| authenticate | 20 | 100 | 80 |
| cart.read | 120 | 280 | 160 |
| inventory.reserve | 300 | 1050 | 750 |
| price.calculate | 300 | 520 | 220 |
| shipping.quote | 300 | 680 | 380 |
| payment.authorize | 1080 | 1640 | 560 |
| order.save | 1660 | 1750 | 90 |
| response.encode | 1750 | 1800 | 50 |

Giả định inventory, pricing và shipping bắt đầu song song ở mốc 300, Payment chỉ bắt đầu sau khi cả ba hoàn tất.

Đường đi quan trọng đi qua authenticate, cart.read, inventory.reserve, payment.authorize, order.save và response.encode. Tổng duration của các bước trên là 1.690 ms. Phần còn lại 110 ms đến từ các khoảng 0–20, 100–120, 280–300, 1050–1080 và 1640–1660; cần giải thích bằng local work, scheduling, network hoặc instrumentation thiếu.

Nếu Shipping giảm từ 380 xuống 100 ms, tổng request vẫn gần 1.800 ms. Nếu Inventory giảm từ 750 xuống 300 ms, Shipping trở thành nhánh chặn. Payment có thể bắt đầu khoảng 710 ms thay vì 1080 ms, tổng giảm xấp xỉ 370 ms nếu những yếu tố khác giữ nguyên.

**Kết luận:** để chọn tối ưu, cần định lượng tác động lên điểm join và end-to-end latency, không chỉ so độ dài từng thanh span.

## 10. Amdahl's Law: giới hạn của tối ưu cục bộ

Amdahl's Law giúp ước lượng mức cải thiện tối đa khi chỉ một phần workload được tăng tốc.

Nếu tỷ lệ thời gian của phần tối ưu là p và nó chạy nhanh hơn s lần, speedup toàn hệ thống lý tưởng:

~~~text
Speedup = 1 / ((1 - p) + p/s)
~~~

Ví dụ một thành phần chiếm 20% total và được tăng tốc gấp 4:

~~~text
p = 0,2
s = 4
Speedup = 1 / (0,8 + 0,2/4)
        = 1 / 0,85
        ≈ 1,176
~~~

Tổng hệ thống chỉ nhanh hơn khoảng 17,6% lý tưởng, chưa tính overhead mới. Nếu thành phần chỉ chiếm 2% thời gian, tăng tốc vô hạn cũng chỉ cải thiện tối đa xấp xỉ 2%.

**Giới hạn áp dụng:** công thức trên minh họa trường hợp công việc có phần thời gian đóng góp vào total theo mô hình đơn giản. Với các nhánh song song, critical path và điểm join mới quyết định lợi ích. Một công việc tiêu nhiều CPU nhưng nằm ngoài critical path có thể không thay đổi user-visible latency.

Amdahl's Law là công cụ đặt kỳ vọng trước khi đầu tư tối ưu, không thay thế trace và thực nghiệm.

## 11. Phân tích latency theo layer

Sau khi biết critical path, mới đào sâu vào layer tương ứng:

| Layer | Điều cần đo | Vấn đề thường gặp |
|---|---|---|
| Browser/UI | Navigation, render, long tasks, API waterfalls | JavaScript nặng, nhiều request nối tiếp |
| Edge/Gateway | Proxy wait, TLS, routing, rate limiting | Connection queue, timeout |
| Application | CPU profile, threads, allocations, lock | Serialization, thread starvation |
| Network | RTT, connection setup, retransmission, payload | DNS/TLS, packet loss |
| Cache | Hit ratio, miss penalty, eviction, stale reads | Stampede, TTL, key design |
| Database | Query plan, lock wait, pool acquire, I/O | N+1, missing index, slow join |
| Queue/Broker | Enqueue/dequeue time, lag, consumer rate | Hot partition, retries |
| External API | Client/server spans, retries, quota | Provider latency, 429, timeout |
| Infrastructure | CPU throttling, GC, scheduling, autoscaling | Pod Pending, cold start |

Đào sâu nên có thứ tự: toàn luồng -> giai đoạn -> dependency -> nội bộ thành phần. Việc đo mọi thứ quá chi tiết ngay từ đầu có thể tốn chi phí và khiến tín hiệu quan trọng bị che lấp.

## 12. Đo cache trước khi chọn cache làm giải pháp

Thêm cache có thể giảm số lần gọi DB hoặc external dependency, nhưng cũng có chi phí: miss handling, invalidation, serialization, mạng, memory, nhất quán dữ liệu và nguy cơ stampede.

Cần biết:

- Bao nhiêu request đang phải chờ đọc dữ liệu giống nhau?
- Thành phần đọc dữ liệu đó có nằm trên critical path không?
- Tỷ lệ cache hit hiện tại là bao nhiêu?
- Hit và miss khác nhau bao nhiêu về latency?
- TTL và độ mới dữ liệu chấp nhận được là gì?
- Nếu cache miss hàng loạt, DB có chịu nổi tải đột biến không?
- Cache key có phụ thuộc tenant, permission hoặc locale không?
- Thêm cache có làm sai kết quả hoặc lộ dữ liệu không?

### 12.1. Tính kỳ vọng hiệu quả hit/miss

Ví dụ một thao tác đọc có thời gian:

~~~text
Cache hit:   5 ms
Cache miss: 120 ms
Hit rate:    80%

Expected read latency xấp xỉ:
0,8 × 5 + 0,2 × 120 = 28 ms
~~~

Đây là phép tính trung bình đơn giản; **tail latency** có thể bị chi phối bởi các cache miss. Với 20% miss, p95 của thao tác đọc vẫn thường nằm trong nhóm miss và có thể cao hơn nhiều so với hit.

Nếu thao tác cache này chạy song song với một nhánh Payment 500 ms và luôn hoàn tất trước điểm join, giảm read từ 120 xuống 28 ms có thể không làm end-to-end latency cải thiện trong phần lớn request.

### 12.2. Cache stampede và thundering herd

Khi một key phổ biến hết hạn, nhiều request cùng cache miss và đánh xuống database. Cần đo miss rate và số query/giây khi TTL hết hạn, không chỉ hit ratio trung bình.

Các kỹ thuật có thể áp dụng tùy bài toán:

- Jitter TTL để tránh đồng loạt hết hạn.
- Request coalescing/single-flight cho cùng key.
- Background refresh hoặc stale-while-revalidate khi hợp đồng cho phép.
- Bounded concurrency và rate limiting khi refresh.
- Negative caching cho trường hợp phù hợp.
- Cache warm-up trước các mốc traffic dự báo.
- Đặt TTL theo khả năng chịu dữ liệu cũ và chính sách invalidation.

Không cache kết quả phân quyền hoặc dữ liệu nhạy cảm mà bỏ scope tenant/user. Một tối ưu latency chỉ hợp lệ khi vẫn giữ correctness và security.

## 13. Đo truy vấn database sau khi đã biết DB nằm trên đường chặn

Một trace có DB span 800 ms; nhưng span đó có thể chứa:

~~~text
Chờ lấy connection: 520 ms
Chờ lock:           180 ms
Thực thi SQL:        60 ms
Network/result:      40 ms
Total:              800 ms
~~~

Nếu đội phát triển tối ưu SQL 60 ms xuống 30 ms, total chỉ giảm khoảng 30 ms. Thay vào đó cần kiểm tra pool saturation, transaction giữ connection, lock contention và concurrency.

### 13.1. N+1 queries

Ví dụ API lấy 100 đơn hàng, sau đó query từng customer:

~~~text
SELECT orders...        25 ms
get customer #1          9 ms
get customer #2          8 ms
...
get customer #100        9 ms
~~~

Ngay cả khi từng query chỉ 9 ms, tổng có thể lớn do số lần round trip. Có thể dùng batch fetch, JOIN đúng chỗ, prefetch hoặc đổi API contract. Nhưng phải đánh giá query plan, dữ liệu lặp và chi phí memory để tránh biến một trăm query nhỏ thành một JOIN khổng lồ thiếu kiểm soát.

### 13.2. Query plan và dữ liệu đại diện

Dùng EXPLAIN/EXPLAIN ANALYZE hoặc công cụ tương đương theo database, quan sát index usage, rows scanned, sort, hash join, lock waits, I/O và buffer hits. Không chạy truy vấn nguy hiểm trên production khi chưa có quy trình phù hợp.

Một query có thể nhanh ở staging vì bảng nhỏ và cache nóng, chậm ở production do cardinality, skew hoặc index khác. Baseline và dữ liệu tải phải đủ đại diện.

## 14. Đo request xuyên network và external service

Với một RPC:

~~~text
Service A CLIENT span: 0 --------------------- 700 ms
Service B SERVER span:    100 -------- 450 ms
~~~

Chênh lệch không tự bằng "network latency". CLIENT span có thể bao gồm connection pool, DNS/TLS, serialization, proxy queue, retry, response download. SERVER span có thể thiếu phần xử lý trước/sau interceptor.

Khi CLIENT lâu hơn SERVER nhiều, kiểm tra:

- Client connection pool wait.
- DNS, TCP connect, TLS handshake.
- Proxy/load balancer queue.
- Request/response payload size.
- HTTP/2 stream concurrency.
- Timeout/retry attempts và backoff.
- Clock skew và propagation/instrumentation.
- Provider rate limit hoặc 429.
- Bất thường một region/AZ.

Một lời gọi bên ngoài không phải lúc nào tối ưu được tại server của mình; có thể giảm số lượt gọi, batching, asynchronous workflow, concurrency limit, caching hợp lệ hoặc cải thiện hợp đồng dữ liệu.

## 15. Retry, timeout và deadline làm tăng thời gian toàn luồng

Ví dụ client gọi inventory ba lần:

~~~text
Attempt 1: 250 ms -> timeout
Backoff 1: 200 ms
Attempt 2: 250 ms -> timeout
Backoff 2: 400 ms
Attempt 3: 200 ms -> success
Total xấp xỉ: 1300 ms
~~~

Nếu chỉ nhìn thời gian attempt thứ ba 200 ms, có thể tưởng dependency nhanh. Nhưng request end-to-end đã tiêu 1.300 ms cho retry và chờ.

Cần đo:

- Số attempts/request và tỷ lệ retry.
- Timeout per attempt và overall deadline.
- Backoff và jitter.
- Idempotency của thao tác.
- Downstream load do retries.
- Phân loại lỗi có retry được không.
- Số request thành công sau retry nhưng chậm vượt SLO.

Một request deadline 1.000 ms không nên để ba tầng service mỗi tầng tự retry 3 lần mà không chia ngân sách; retry amplification làm quá tải dependency và tăng tail latency.

Tối ưu phù hợp có thể là sửa thời gian chờ, dùng timeout/deadline nhất quán, cache hoặc giảm số RPC; không mặc định tăng số retries để tăng success rate nếu làm quá tải hệ thống.

## 16. Throughput, concurrency và Little's Law

Trong một hệ thống ổn định, Little's Law:

~~~text
L = lambda × W

L = số công việc trung bình trong hệ thống
lambda = throughput trung bình (công việc/giây)
W = thời gian trung bình một công việc ở trong hệ thống (giây)
~~~

Ví dụ:

~~~text
Throughput: 300 request/giây
Mean response time: 0,4 giây
Average in-flight work: 300 × 0,4 = 120
~~~

Nếu thời gian trung bình tăng lên 2 giây trong khi throughput vẫn 300 RPS, số công việc hiện diện có thể gần 600. Tình huống này có thể làm cạn thread pool, connection pool và memory, rồi khuếch đại latency.

Đừng suy rằng chỉ cần tăng số replica sẽ sửa được. Nếu W tăng vì DB đã quá tải, thêm application Pods có thể làm DB chịu nhiều request đồng thời hơn.

### 16.1. Utilization và hàng đợi

Khi tài nguyên gần capacity, thời gian chờ có thể tăng phi tuyến. Vì vậy throughput đạt 95% capacity không có nghĩa latency chỉ xấu hơn 5%.

Đo:

- CPU usage và throttling.
- Thread pool/worker pool queue depth.
- DB connection acquire wait.
- Lock contention.
- Network and I/O saturation.
- Queue wait và broker lag.
- Autoscaler desired/current/ready replicas.

Saturation và queueing thường giải thích vì sao p99 tăng trong khi CPU trung bình chưa chạm 100%.

## 17. Load testing phải giống hành vi thực

Một benchmark gọi liên tục GET /healthz không cho biết Checkout chịu được bao nhiêu đơn hàng mỗi giây. Một workload đại diện cần mô tả:

- Tỷ lệ các route/business journey.
- Payload size và biến thể phức tạp.
- Dữ liệu production-like nhưng an toàn.
- Cache hot/cold mix.
- Số user đồng thời và tốc độ request đến.
- Think time giữa các thao tác người dùng.
- Tỷ lệ tạo/sửa/đọc; contention và transaction.
- Phân bố region, network RTT và client type.
- External dependency thật, mock hay sandbox.
- Error/timeout và retry policy.
- Autoscaling, startup và số node.

Một load test nên có các giai đoạn:

1. **Baseline:** tải thấp ổn định.
2. **Ramp-up:** tăng dần để tìm điểm SLO bắt đầu bị vi phạm.
3. **Steady load:** giữ tải mục tiêu đủ lâu, xem memory/GC/queue.
4. **Burst/spike:** tăng đột ngột, đo headroom và time-to-scale.
5. **Stress:** vượt capacity có kiểm soát, quan sát overload behavior.
6. **Soak:** duy trì lâu để phát hiện leak, pool exhaustion và cache drift.
7. **Ramp-down:** giảm tải, xem hệ thống hồi phục và drain.
8. **Dependency degraded:** mô phỏng DB slow/provider timeout để kiểm tra resilience.

Không nên làm stress/soak trên production nếu chưa được cấp phép và có phương án bảo vệ người dùng.

## 18. Closed-loop, open-loop và coordinated omission

Đây là một sai lầm đo hiệu năng dễ bỏ qua.

**Closed-loop load generator** thường chờ request trước hoàn thành mới gửi request tiếp theo cho virtual user. Khi hệ thống chậm, tốc độ phát request thực có thể giảm. Như vậy benchmark vô tình giảm tải đúng lúc service quá tải, làm latency thống kê trông tốt hơn so với tình huống traffic thật vẫn đến theo lịch.

**Open-loop/arrival-rate model** gửi request theo tốc độ đến định trước, tách khỏi tốc độ phản hồi, phù hợp để kiểm tra service chịu một arrival rate mục tiêu thế nào. Cần đủ năng lực load generator để duy trì rate và ghi nhận request không thể phát đúng lịch.

**Coordinated omission** là tình huống thời gian hệ thống ngừng tiến triển không được ghi đầy đủ vào thống kê latency do cách phát hoặc đo request. Khi latency tăng, một số phép đo bỏ qua những lần phát lẽ ra đã xảy ra; tail latency bị đánh giá thấp.

Cách kiểm chứng:

- Ghi planned vs actual arrival rate.
- Ghi cả dropped iterations, timeouts và failed requests.
- Biết công cụ dùng closed-loop hay constant-arrival-rate.
- Dùng load generator đủ CPU/network để không thành bottleneck.
- Đo client-observed latency cùng server-side metrics.
- Không báo latency chỉ cho successful requests mà giấu lượng request không được gửi hoặc đã timeout.

Công cụ k6, Gatling, JMeter hay các công cụ khác có chế độ phát tải khác nhau; đọc rõ semantics của scenario và executor trước khi diễn giải kết quả.

## 19. Ví dụ k6 đo một hành trình API

Ví dụ dùng k6 để đo một endpoint đọc catalog dưới tải tăng, đồng thời kiểm tra response status. Đây là bài test minh họa; URL và traffic profile phải thay theo môi trường.

~~~javascript
import http from "k6/http";
import { check } from "k6";

export const options = {
  scenarios: {
    browse_catalog: {
      executor: "ramping-arrival-rate",
      startRate: 20,
      timeUnit: "1s",
      preAllocatedVUs: 50,
      maxVUs: 250,
      stages: [
        { target: 20, duration: "1m" },
        { target: 100, duration: "3m" },
        { target: 100, duration: "5m" },
        { target: 20, duration: "2m" }
      ]
    }
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500"]
  }
};

export default function () {
  const res = http.get("https://staging.example.com/api/catalog?category=books");
  check(res, {
    "HTTP 200": (r) => r.status === 200,
    "body not empty": (r) => r.body && r.body.length > 0
  });
}
~~~

Mốc p95 500 ms và error 1% là ví dụ, không phải ngưỡng mặc định. Với hành trình checkout thực, cần setup user/cart, xác thực và tạo dữ liệu không xâm hại production; không nên lặp giao dịch thanh toán thật.

Lưu ý:

- http_req_duration đo góc nhìn k6 cho request ở phạm vi công cụ; nó không bao gồm mọi thao tác render frontend.
- Threshold trên HTTP 200 chưa bảo đảm correctness nghiệp vụ.
- Phải theo dõi dropped_iterations, VU utilization, CPU của load generator và thành công đạt arrival rate.
- Với nhiều route, tạo journey thực thay vì một endpoint duy nhất.
- Dùng môi trường và dữ liệu có khả năng chịu tải; mô phỏng external dependency khi hợp lý nhưng ghi rõ giả định.
- Nếu request cần idempotency, tạo request ID và test data theo hợp đồng để tránh double-write.

## 20. Metrics và PromQL cho toàn luồng

Giả định hệ thống xuất classic HTTP request histogram theo tên http_server_requests_seconds và có các labels job, uri, status. Đây là ví dụ phổ biến; tên metric và label thực tế khác nhau theo framework/exporter.

### 20.1. RPS theo route

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_count{job="checkout"}[5m])
)
~~~

### 20.2. Tỷ lệ lỗi 5xx

~~~promql
sum(
  rate(http_server_requests_seconds_count{
    job="checkout",status=~"5.."
  }[5m])
)
/
sum(
  rate(http_server_requests_seconds_count{job="checkout"}[5m])
)
~~~

Khi mẫu số thiếu hoặc bằng 0, cần hiển thị request volume và giá trị không xác định đúng cách. Không xem series mất dữ liệu là error rate bằng 0.

### 20.3. p95 latency theo route

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{
      job="checkout"
    }[5m])
  )
)
~~~

Đây là classic histogram query. Với native histograms hoặc tên mới theo OpenTelemetry, cú pháp và metric có thể khác. Không gộp histogram có bucket/đơn vị không tương thích.

### 20.4. Lượng request trong khoảng đo

~~~promql
sum by (uri) (
  increase(http_server_requests_seconds_count{
    job="checkout"
  }[10m])
)
~~~

Các tỷ lệ và percentile cần được xem cùng số request/đơn vị thời gian, đặc biệt khi chia cohort, canary hay region. Không thêm userId hoặc raw URL chứa dữ liệu nhạy cảm vào labels.

### 20.5. Kết hợp metrics với traces

Metrics xác nhận vấn đề ở quy mô tổng thể; traces giúp giải thích một request chậm cụ thể. Nếu backend hỗ trợ exemplars, có thể chọn trace đại diện từ histogram latency.

Không dùng tập trace chỉ lưu error/slow requests để suy ra tỷ lệ lỗi toàn hệ thống; tail sampling đã làm sai phân bố mẫu có chủ đích.

## 21. Instrumentation với OpenTelemetry trong Java

Auto-instrumentation thường tạo spans cho inbound HTTP, outbound HTTP, JDBC và nhiều framework. Với các bước nghiệp vụ không rõ trong trace, có thể thêm INTERNAL span thủ công.

Ví dụ:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public final class CheckoutApplicationService {
    private final Tracer tracer;
    private final PricingClient pricing;

    public CheckoutApplicationService(Tracer tracer, PricingClient pricing) {
        this.tracer = tracer;
        this.pricing = pricing;
    }

    public PriceQuote calculatePrice(Cart cart) {
        Span span = tracer.spanBuilder("checkout.calculate-price")
                .setSpanKind(SpanKind.INTERNAL)
                .startSpan();
        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("business.operation", "calculate-price");
            PriceQuote quote = pricing.calculate(cart);
            span.addEvent("checkout.pricing.completed");
            return quote;
        } catch (RuntimeException e) {
            span.recordException(e);
            span.setStatus(StatusCode.ERROR, "price calculation failed");
            throw e;
        } finally {
            span.end();
        }
    }
}
~~~

PricingClient, Cart và PriceQuote là type nghiệp vụ cần định nghĩa. Tracer phải được cấp qua SDK/agent phù hợp. Nếu HTTP client đã được instrument tự động, CLIENT span của lời gọi Pricing sẽ xuất hiện dưới INTERNAL span.

Cần chú ý:

- Không tạo span cho từng dòng code hoặc mỗi item trong vòng lặp lớn.
- Tên span ổn định theo operation, không chứa userId/orderId.
- Các bước fork/join, cache hit/miss, retry scheduled và transaction commit có thể ghi events.
- Với thread pool/reactive streams, cần propagate context đúng.
- Đảm bảo exporter/collector không gây overhead vượt mức chấp nhận.
- Không gửi token, cookie, mật khẩu hoặc payload riêng tư vào spans.

## 22. Phân tích CPU, allocation và garbage collection

Sau khi trace chỉ ra đoạn local processing dài, có thể dùng CPU profiler, allocation profiler và GC logs/metrics.

### 22.1. CPU profile

Xem call stacks tiêu thụ CPU trong khoảng tải đại diện. Những vị trí thường đáng kiểm tra:

- JSON serialization/deserialization.
- Regex hoặc thuật toán có độ phức tạp xấu.
- Mapping DTO/entity quá nhiều.
- Mã hóa/giải mã và compression.
- Sắp xếp, grouping hoặc xử lý collection lớn.
- Logging quá nhiều làm tạo string không cần thiết.
- Cache hash/computation hoặc lock contention.

Profiler không nhất thiết nói latency người dùng; một hàm tiêu nhiều CPU trên background thread có thể không nằm trên critical path của request đang chậm.

### 22.2. Allocation và GC

Với Java, allocations tạo áp lực GC; khi heap chật hoặc GC pause tăng, p99 có thể xấu dù p50 còn tốt. Theo dõi:

- Allocation rate (bytes/second).
- Young/old generation collection count/duration.
- GC pause distribution.
- Heap used/committed/max.
- Safepoint time, thread count.
- CPU throttling và container memory limits.

Một tối ưu allocation có thể có lợi lớn tại tải cao nhưng không thấy khác biệt ở microbenchmark tải thấp. Cần đo ở tải khiến GC hoặc CPU thực sự ảnh hưởng tới SLO.

## 23. Phân tích hiệu năng của queue và workflow bất đồng bộ

Trong event-driven systems, API có thể trả 202 rất nhanh nhưng downstream completion chậm vì queue backlog.

Đo các mốc:

~~~text
T0: nhận yêu cầu tạo báo cáo
T1: message được enqueue
T2: consumer bắt đầu xử lý
T3: consumer hoàn thành
T4: người dùng nhận thông báo sẵn sàng
~~~

Các metric:

- Queue wait = T2 - T1.
- Processing time = T3 - T2.
- End-to-end business time = T4 - T0.
- Arrival rate vs processing rate.
- Oldest message age.
- Retry/redelivery/DLQ.
- Lag theo partition/consumer group.
- Số job đang active, timeout/cancel.

Nếu tăng số worker làm processing time riêng từng job không đổi nhưng queue wait giảm từ 5 phút xuống 30 giây, đó có thể là cải thiện end-to-end rất lớn. Nếu queue có hot partition hoặc dependency quota chung, tăng worker có thể không giải quyết.

Khi một nghiệp vụ kéo dài nhiều giờ, không nên cố giữ một trace root span mở vô hạn. Dùng span links/correlation IDs, business events và completion metrics để nối các chặng hợp lý.

## 24. Đo từ frontend tới backend

Một trang web có thể có thời gian:

~~~text
Browser request start      T=0
HTML response              T=150 ms
JavaScript download        T=400 ms
Hydration/render           T=850 ms
API data request complete  T=1.350 ms
UI ready for interaction   T=1.500 ms
~~~

Nếu chỉ đo server-side HTML latency 150 ms sẽ bỏ sót phần lớn trải nghiệm. Với web, cần xem các chỉ số phù hợp như navigation timings, resource waterfall, main-thread long tasks và các Core Web Vitals liên quan (ví dụ LCP/INP tùy mục tiêu), nhưng không dùng một chỉ số thay cho toàn bộ business journey.

Các câu hỏi:

- Có API waterfall nối tiếp không cần thiết ở frontend?
- Có request trùng, overfetch hoặc payload quá lớn?
- Bundle có quá nhiều JavaScript trên tuyến trọng yếu?
- Có layout shift/re-render hoặc main-thread blocking?
- Browser cache/CDN có hit ratio phù hợp không?
- Có gọi API trước khi UI thật sự cần dữ liệu không?
- User trên mạng chậm hoặc thiết bị yếu có hành vi khác không?

Mỗi tối ưu frontend cũng cần đo lại end-to-end; giảm payload nhưng tăng thời gian parse/CPU có thể không cải thiện tổng.

## 25. Error budget và cân bằng tốc độ với độ tin cậy

Thời gian phản hồi nhanh hơn bằng cách bỏ kiểm tra tính đúng đắn, không chờ transaction commit hoặc tắt xác thực không phải tối ưu hợp lệ.

Với SLO "99% checkout hoàn tất đúng trong 2 giây", phải xem cả:

- Request có hoàn tất trước deadline?
- Kết quả có đúng và nhất quán?
- Payment và Order có khớp không?
- Có giao dịch trùng do retry?
- Các lỗi có được trả đúng nghĩa thay vì che bằng HTTP 200?
- Nếu công việc được đưa sang async, người dùng có nhận được kết quả cuối đúng hạn?

Một thay đổi có thể giảm p95 của HTTP 200 nhưng tăng số transaction phải xử lý lại. Khi đó business completion latency và error budget có thể xấu hơn.

**Ưu tiên tính đúng đắn và an toàn dữ liệu** trước khi tối ưu con số đẹp trên dashboard.

## 26. Thiết kế thí nghiệm tối ưu có đối chứng

Một tối ưu có chất lượng nên bắt đầu từ một giả thuyết kiểm chứng được.

Ví dụ:

**Quan sát:** p95 GET /product-details tăng lên 900 ms tại 800 RPS. Trace cho thấy DB read 650 ms trên critical path, trong đó connection acquire wait 500 ms.

**Giả thuyết:** transaction giữ connection lâu và pool cạn; giảm thời gian giữ connection sẽ giảm DB pool wait, cải thiện end-to-end p95 mà không cần tăng pool.

**Can thiệp:** rút ngắn transaction, tách lời gọi external ra khỏi transaction và giới hạn concurrency đúng chỗ.

**Giữ nguyên:** tải, dữ liệu, số Pod, DB configuration, cache state, test duration và các phiên bản không liên quan.

**Đo sau thay đổi:**

- Pool acquire wait p50/p95.
- Active/idle/waiting connections.
- DB query duration.
- End-to-end GET /product-details p50/p95/p99.
- HTTP error/timeout và business correctness.
- CPU, memory và throughput trên mỗi Pod.

**Tiêu chí thành công:** latency end-to-end cải thiện có thể lặp lại, không tăng lỗi/saturation và không phá tính nhất quán.

### 26.1. Baseline và candidate phải tương đồng

Nếu baseline chạy 4 Pod còn candidate chạy 16 Pod, không thể quy toàn bộ chênh lệch cho tối ưu code. Nếu candidate có cache nóng còn baseline cache lạnh, kết quả cũng bị sai lệch.

Ghi rõ:

- Version/commit/artifact.
- Requests/second và test profile.
- Số Pod, requests/limits, node type.
- Database size và index.
- Cache warm/cold.
- External provider latency hoặc mock behavior.
- Môi trường và thời gian đo.
- Phân bố latency và số mẫu.
- Error/correctness checks.

### 26.2. A/B hoặc canary thực tế

Nếu có thể triển khai stable và candidate song song, so sánh cùng thời gian với cohort tương đồng. Canary phải xem traffic allocation thực tế và sample size. Một số thay đổi cần kiểm chứng trên dữ liệu production-like nhưng có rủi ro về tính đúng đắn; không nên dùng canary chưa có guardrail để thử thay đổi gây side effect nguy hiểm.

Tương quan sau deploy chưa đủ chứng minh nguyên nhân; cần xem thay đổi dependency, traffic mix và external incidents.

## 27. Ưu tiên tối ưu theo tác động thay vì mức độ hấp dẫn

Một bảng ưu tiên:

| Ứng viên | Có trên critical path? | Có thể giảm total? | Rủi ro | Quyết định |
|---|---|---|---|---|
| Bỏ N+1 DB queries | Có | Cao | Vừa | Ưu tiên |
| Tối ưu JSON mapping 20 ms | Có nhưng nhỏ | Thấp | Thấp | Sau |
| Cache bước chạy song song hoàn tất sớm | Không trong trace hiện tại | Gần 0 | Vừa | Chưa ưu tiên |
| Giảm retry do provider timeout | Có | Rất cao nếu nguyên nhân được xác nhận | Vừa/cao | Điều tra và ưu tiên |
| Tăng Pod khi DB đã nghẽn | Có thể không | Không chắc; có thể tệ hơn | Cao | Không tăng mù |
| Thay synchronous export bằng async | Đổi phạm vi đo | Cải thiện HTTP, chưa chắc business completion | Vừa | Cần SLO mới |

Một cách ước lượng giá trị:

~~~text
Expected benefit =
  End-to-end latency reduction
  × frequency of impacted journey
  × business/user importance
  - engineering/risk/cost tradeoffs
~~~

Không cần biến biểu thức trên thành một công thức tiền tệ tuyệt đối; nó giúp nhắc rằng thành phần có duration dài chưa chắc là nơi tối ưu đáng đầu tư nhất.

### 27.1. Tối ưu giảm tải cho cả hệ thống

Đôi khi thay đổi ngoài critical path của một request vẫn có giá trị vì làm giảm contention chung. Ví dụ giảm CPU background jobs không làm một request đơn lẻ nhanh ngay nhưng giảm saturation, khiến p99 toàn hệ thống tốt hơn ở giờ cao điểm. Hãy đánh giá tác động theo phân bố tải và tài nguyên chung, không chỉ một trace.

## 28. Bẫy khi đọc kết quả tối ưu

1. **Chỉ đo microbenchmark:** không thấy network, DB, queue và contention.
2. **Đo average thay vì tail:** bỏ sót p95/p99 và timeout.
3. **Bỏ request lỗi khỏi thống kê:** latency trông đẹp khi availability giảm.
4. **Dùng traffic khác giữa before/after:** tạo cải thiện giả.
5. **Đo trên data quá nhỏ:** query plan không phản ánh production.
6. **Không làm nóng JIT/cache:** kết quả lẫn startup và steady state.
7. **Chạy trên máy phát tải yếu:** benchmark bị giới hạn bởi client.
8. **Không tính sampling bias:** trace được lưu thiên về request lỗi/chậm.
9. **Cộng duration parent-child:** đếm trùng thời gian.
10. **Chọn span dài nhất mà không xem critical path:** tối ưu nhầm nhánh song song.
11. **Chỉ nhìn CPU service:** không thấy DB pool wait hoặc queue lag.
12. **Quên external quota và retries:** tăng Pod tạo thêm timeout.
13. **Cache dữ liệu không có invalidation đúng:** tăng tốc nhưng trả kết quả sai.
14. **Không xét long-tail input:** một số payload/tenant có hành vi khác biệt.
15. **Không version metadata:** kết quả test không truy về code/config cụ thể.
16. **Không kiểm tra correctness:** biến asynchronous thành nhanh giả bằng trả kết quả trước khi hoàn tất.
17. **Không đo sau deploy:** cải thiện trên staging nhưng regression ở production.
18. **Không tính autoscaling/cold start:** p95 tốt steady state nhưng flash sale vẫn lỗi.

## 29. Một runbook điều tra hiệu năng chậm

### Bước 1 — Xác nhận ảnh hưởng người dùng

Xác định hành trình, loại user, region, thời gian bắt đầu, success/error rate và SLO bị vi phạm. Có cần đo tới khi UI sẵn sàng hoặc job hoàn tất không?

### Bước 2 — Lập baseline

Ghi p50/p95/p99, request volume, concurrency, queue metrics, deployment versions và traffic mix trong khoảng trước/sau sự cố.

### Bước 3 — Xem biểu đồ tổng quan

So traffic, latency, error, saturation. Kiểm tra deployment, config, feature flag, database migration và provider outage gần thời điểm biến động.

### Bước 4 — Lấy traces đại diện

Chọn nhanh/chậm/lỗi trong cùng route/cohort. Đọc root, waterfall, các nhánh song song, retries, timeout, async links và instrumentation gaps.

### Bước 5 — Xác định critical path

Tìm điểm join và dependency chặn response hoặc business completion. Tránh cộng parent/child trùng hoặc các nhánh song song.

### Bước 6 — Đào sâu đúng layer

Nếu là DB: pool wait/locks/query plan. Nếu CPU: profiler/GC. Nếu cache: hit/miss, stampede, stale reads. Nếu queue: lag/oldest age. Nếu network: CLIENT/SERVER span, TLS, retries.

### Bước 7 — Xác định giả thuyết và dự báo tác động

Mô tả rõ vì sao can thiệp sẽ giảm latency end-to-end và ước lượng giới hạn cải thiện.

### Bước 8 — Thử nghiệm có đối chứng

Giữ cùng traffic/data/environment; đo cả thành phần, total, correctness, errors và resource cost. Dùng nhiều lượt nếu có biến động.

### Bước 9 — Triển khai có giám sát

Dùng canary/rolling/feature flag phù hợp và giám sát SLI, latency theo version, business outcomes. Có kế hoạch rollback nếu regression.

### Bước 10 — Đo lại và cập nhật bottleneck

Tối ưu có thể khiến critical path chuyển chỗ. Đừng giả định sau tối ưu hệ thống tiếp tục bị chặn ở cùng dependency.

## 30. Ví dụ kiểm chứng cải thiện có giá trị

Một hệ thống Search API có baseline tại 500 RPS:

| Chỉ số | Trước tối ưu | Sau tối ưu |
|---|---:|---:|
| RPS thực | 500 | 500 |
| p50 Search | 220 ms | 170 ms |
| p95 Search | 980 ms | 530 ms |
| p99 Search | 1.850 ms | 1.100 ms |
| Error rate | 0,40% | 0,35% |
| DB connection wait p95 | 520 ms | 110 ms |
| Mean SQL execution | 70 ms | 68 ms |
| Business correctness | Đạt | Đạt |
| Pod count | 8 | 8 |

Nếu traffic, dữ liệu, environment và các dependency khác tương đồng, bảng gợi ý rằng việc giảm pool wait có liên quan chặt tới cải thiện p95 end-to-end. SQL gần như không đổi, cho thấy không nhất thiết phải thêm index mới là giảm latency.

Nhưng vẫn phải kiểm tra nhiều lượt, histogram, request distribution và trace để chắc rằng kết quả không chỉ là hiệu ứng cache warm hoặc traffic mix.

Nếu p95 cải thiện nhưng p99 xấu hơn, cần tìm workload nhóm đuôi bị ảnh hưởng. Một tối ưu không nhất thiết đồng đều cho mọi cohort.

## 31. Bài tập thực hành

Một API Recommendations cần ba engine chạy song song rồi hợp nhất:

~~~text
T0 = 0 ms: bắt đầu request
T = 40 ms: khởi tạo cả ba lời gọi
Engine A: trả tại T = 480 ms
Engine B: trả tại T = 630 ms
Engine C: trả tại T = 390 ms
Combine: 90 ms, bắt đầu sau khi cả ba trả
Render: 30 ms, bắt đầu sau Combine
~~~

### Câu hỏi 1

Request hoàn tất lúc nào, bỏ qua overhead khác?

**Đáp án:** max(480,630,390) + 90 + 30 = **750 ms**. Các mốc engine đã là thời điểm tuyệt đối tính từ T0.

### Câu hỏi 2

Trong ba engine, nhánh nào đang chặn điểm hợp nhất?

**Đáp án:** Engine B, vì trả kết quả cuối cùng ở T=630 ms.

### Câu hỏi 3

Nếu Engine A được tối ưu từ T=480 xuống T=280, tổng request giảm không?

**Đáp án:** Không. Engine B vẫn trả ở T=630, nên Combine chưa thể bắt đầu trước đó.

### Câu hỏi 4

Nếu Engine B trả sớm hơn 250 ms, request hoàn tất lúc nào?

**Đáp án:** Engine B trả tại T=380, Engine A vẫn T=480, nên total = 480 + 90 + 30 = **600 ms**.

### Câu hỏi 5

Nếu service đổi logic chỉ cần 2 trong 3 engine, có thể dùng công thức max của cả ba nữa không?

**Đáp án:** Không. Phải xét điều kiện thành công, lỗi và chính sách join mới. Không tự đổi semantics nghiệp vụ chỉ để tăng tốc.

### Câu hỏi 6

Nếu Engine B có cache miss 10% request, phần lớn request có hit nhanh, nên xem mean hay p99?

**Đáp án:** Xem cả phân bố theo cache hit/miss, p95/p99 và end-to-end SLO. Một số ít miss có thể chi phối tail latency, nhưng phải xác định miss có nằm trên critical path khi xảy ra hay không.

### Câu hỏi 7

Nếu tối ưu Engine B làm response nhanh hơn nhưng kết quả thiếu dữ liệu quan trọng, được xem là thành công không?

**Đáp án:** Không. Tối ưu phải giữ hợp đồng nghiệp vụ và correctness.

## 32. Checklist trước khi tối ưu

- [ ] Đã xác định hành trình người dùng và điểm bắt đầu/kết thúc của phép đo.
- [ ] Đã tách HTTP latency khỏi business completion latency nếu có async.
- [ ] Có SLI/SLO và performance budget rõ.
- [ ] Baseline ghi version, tải, data, cache state và hạ tầng.
- [ ] Có p50/p95/p99, request volume, success/error và saturation.
- [ ] Có trace context liên kết các microservices, DB và queue quan trọng.
- [ ] Đã tìm critical path chứ không chỉ span dài nhất.
- [ ] Không cộng trùng parent-child và child spans song song.
- [ ] Đã kiểm tra retry/backoff, timeout, connection pool và lock wait.
- [ ] Nếu tối ưu cache, đã xem hit/miss, invalidation, stampede và correctness.
- [ ] Nếu tối ưu SQL, đã xem pool/lock/query plan trên dữ liệu đại diện.
- [ ] Load test có traffic mix, payload, concurrency và error semantics phù hợp.
- [ ] Đã tránh coordinated omission và theo dõi dropped iterations.
- [ ] Có giả thuyết, mức cải thiện dự kiến và phép thử có đối chứng.
- [ ] Có kiểm tra lỗi, dữ liệu đúng và chi phí tài nguyên sau thay đổi.
- [ ] Đã đo lại end-to-end sau rollout, không chỉ benchmark một hàm.
- [ ] Đã xác định bottleneck mới sau khi tối ưu cũ.
- [ ] Có regression monitoring và runbook nếu chỉ số xấu đi.

## 33. Ghi nhớ

Hiệu năng của microservice không đồng nghĩa hiệu năng của sản phẩm. Người dùng quan tâm thời gian hoàn tất một hành trình và kết quả có đúng hay không; hệ thống có thể tiêu thời gian ở browser, proxy, CPU, database, network, queue hoặc external provider.

**Quy trình hiệu quả là đo tổng thể trước, phân rã theo trace và critical path, kiểm tra dependency đang chặn, rồi mới can thiệp thành phần.** Amdahl's Law nhắc rằng tối ưu một phần nhỏ khó tạo cải thiện lớn; xử lý các nhánh chạy song song còn cần hiểu điểm join. Sau khi tối ưu, bottleneck có thể chuyển sang nơi khác.

Dùng metrics để biết mức độ và xu hướng, traces để biết đường đi của request, logs/profilers để hiểu nguyên nhân, load test để kiểm chứng dưới tải đại diện và business metrics để bảo đảm tính đúng đắn.

**Một tối ưu chỉ được coi là thành công khi phép đo end-to-end cải thiện lặp lại được trong điều kiện tương đương, không làm tăng lỗi, không phá hợp đồng dữ liệu và đem lại lợi ích có thể cảm nhận được cho người dùng.**