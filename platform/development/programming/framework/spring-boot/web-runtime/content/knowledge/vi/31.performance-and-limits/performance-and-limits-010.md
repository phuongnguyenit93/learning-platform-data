# Đo tải với dữ liệu, mức đồng thời và thời gian chạy đại diện thực tế trong Spring Boot

## 1. Mục tiêu: kết quả tải phải phản ánh hệ thống sẽ chạy trong thực tế

Một ứng dụng Spring Boot có thể trả HTTP 200 trong 5 ms khi chỉ có một người thử `curl`. Kết quả đó **không chứng minh** ứng dụng đạt SLO khi có hàng trăm phiên người dùng, dữ liệu tăng theo thời gian, PostgreSQL chứa hàng triệu dòng, cache hoạt động không đồng đều, và tải kéo dài đủ lâu để connection pool, GC, bộ nhớ hoặc downstream bộc lộ giới hạn.

Đo tải có giá trị phải mô tả đồng thời **ba trục**:

1. **Dữ liệu đại diện:** số bản ghi, dung lượng, độ rộng payload, phân bố dữ liệu, khóa nóng/lạnh, cache hit/miss, phân bố theo tenant, loại request đọc/ghi và tốc độ phát sinh dữ liệu.
2. **Tải và mức đồng thời đại diện:** số người dùng đang thao tác, tốc độ đến của request/transaction (RPS/TPS), thời gian nghĩ (think time), số yêu cầu đang xử lý, burst/peak, mức song song với DB hoặc các dịch vụ khác.
3. **Thời gian chạy đại diện:** warm-up, ổn định, đỉnh tải, spike, soak dài hạn, chạy vào lúc hệ thống có batch/backup/autoscaling và quan sát đủ chu kỳ GC/cache/connection leaks.

**Thông điệp chính:** số VUs lớn không tự chứng minh hệ thống chịu tải tốt; 1.000 dòng dữ liệu giả không thay 10 triệu dòng thật; bài test 30 giây không thay một giờ vận hành. Cần đo **latency p95/p99, thông lượng hoàn tất, tỷ lệ lỗi, dropped iterations, mức sử dụng tài nguyên và tính đúng của phản hồi** tại mức tải và cấu hình đã công bố.

Bài viết tập trung Spring Boot web runtime (Spring MVC/Tomcat, JDBC/HikariCP/PostgreSQL, Actuator/Micrometer) và k6 làm load generator. Có project tự chạy với **Spring Boot 3.5.16, Java 17+, Maven, PostgreSQL qua Docker Compose**, cơ sở dữ liệu mẫu **200.000 sản phẩm**, hỗn hợp 80% đọc chi tiết, 15% tìm kiếm, 5% ghi sự kiện, cùng k6 open-model và closed-model. Các giá trị cấu hình/tải ở đây là **mẫu học tập**, không phải số liệu đo thực tế hay đề xuất SLO mặc định cho mọi doanh nghiệp.

### Kết quả học tập

Sau bài này có thể:

- Thiết kế workload từ traffic và dữ liệu đã quan sát ở production.
- Phân biệt user, virtual user, session, RPS, throughput, in-flight request và DB connections.
- Chọn **closed workload** hoặc **open arrival rate** đúng mục đích; tránh coordinated omission.
- Chọn ramp-up, steady-state, peak, stress, soak đủ dài để phát hiện lỗi.
- Dùng k6 kiểm tra correctness và thresholds theo endpoint thay vì chỉ tổng trung bình.
- Đọc metrics Spring Boot/Tomcat/Hikari/JVM/PostgreSQL để xác định nút thắt.
- Báo cáo một kết quả có thể tái lập và biết những giới hạn không thể suy diễn từ lab.

## 2. Xác định mục tiêu và câu hỏi trước khi chọn công cụ

Bắt đầu bằng một **câu hỏi kiểm định** cụ thể, ví dụ:

> Với cấu hình 2 instance Spring MVC, mỗi instance 2 vCPU/2 GiB RAM, một PostgreSQL ở cấu hình gần production, 500.000 sản phẩm và traffic hỗn hợp như quan sát, liệu hệ thống duy trì **200 HTTP requests/giây trong 30 phút** với p95 dưới 300 ms, p99 dưới 800 ms và lỗi hệ thống dưới 0,5% không?

Câu này xác định: topology, data volume, traffic mix, arrival rate, duration và ngưỡng chấp nhận. Các con số trên **chỉ minh họa dạng giả thuyết**; SLO thật phải lấy từ nhu cầu sản phẩm, telemetry và capacity budget.

### Những mục đích test khác nhau

| Loại test | Câu hỏi | Profile có ý nghĩa |
| --- | --- | --- |
| **Smoke** | Script, auth, dữ liệu và endpoint có hoạt động? | Vài VUs/RPS trong 1–3 phút, assert response |
| **Baseline** | Hệ thống hiện tại ở tải thấp có độ trễ nào? | Cố định môi trường, tải ổn định, nhiều lần lặp |
| **Load/capacity** | Đạt p95/p99/errors ở normal/peak load? | Dữ liệu + traffic thật, steady-state |
| **Stress** | Điểm nào bắt đầu mất SLO/giới hạn? | Tăng dần RPS/VUs, tìm capacity knee |
| **Spike** | Điều gì xảy ra khi arrival rate tăng nhanh? | Thay đổi rate đột ngột, theo dõi queue/recovery |
| **Soak/endurance** | Có rò rỉ, suy giảm pool/heap/DB sau lâu không? | 1–4 giờ hoặc dài hơn theo chu kỳ thực |
| **Scale test** | Autoscaling tăng/giảm có bắt kịp không? | Ramps tương thích HPA, startup, cooldown |
| **Recovery test** | Sau upstream timeout/DB failover có hồi phục không? | Fault injection có kiểm soát và rollback |

Không đo để “đạt điểm cao nhất trong benchmark”. Mục tiêu là chứng minh **khả năng phục vụ workload đã định nghĩa** hoặc chỉ ra giới hạn cùng nguyên nhân, có bằng chứng.

## 3. Dữ liệu đại diện: số lượng dòng chỉ là điểm bắt đầu

### 3.1. Tối thiểu phải mô tả những chiều dữ liệu nào?

| Chiều | Ví dụ cần đo | Vì sao thay đổi kết quả |
| --- | --- | --- |
| **Cardinality** | 200 nghìn, 2 triệu, 20 triệu sản phẩm | Index size, working set, DB/cache efficiency |
| **Kích thước dòng** | Tên 30 ký tự vs mô tả 10 KiB | I/O, network, serialization, heap allocations |
| **Phân bố khóa** | 70% yêu cầu vào 10% sản phẩm hot | Cache hit và row contention khác uniform |
| **Phân bố danh mục/tenant** | Books 50%, electronics 30%, home 20% | Selectivity/partition skew, tenant fairness |
| **Tỷ lệ read/write** | 80% detail, 15% search, 5% events | DB writes/WAL, locks, query mix |
| **Kiểu tra cứu** | ID point lookup, filter, sort, offset deep | Query plans và index utilization khác nhau |
| **Tỷ lệ tồn tại** | Hầu hết ID hợp lệ; một số 404 thật | Đúng phân bố lỗi và load đường error handling |
| **Cache state** | Cold, warm, hot-key hit rate | Warm cache có thể che disk/DB bottleneck |
| **Chu kỳ dữ liệu** | Events tăng 5% workload mỗi phút | Table/index bloat, autovacuum, disk use |
| **Đặc tính đa tenant** | Một tenant nhiều bản ghi và traffic | Noisy neighbor, fairness |
| **Tỷ lệ payload** | P50/P95 payload request/response | Bandwidth/compression/GC |
| **Tài nguyên downstream** | DB, Redis, payment latency/errors | Tail latency và contention hệ thống |

Giữ **phân bố** quan trọng không kém tổng row count. Một database 1 triệu rows nhưng bài test luôn GET `/products/1` có thể trả cực nhanh vì tất cả request trúng cache, không mô phỏng người dùng thực.

### 3.2. Tránh hai cách sinh dữ liệu gây kết luận sai

**Sai 1: chỉ sinh 100 bản ghi rồi gọi lại mãi.** Index và toàn bộ working set dễ nằm trong RAM. Query plan, cache hit và disk pressure khác production.

**Sai 2: random đều mọi ID.** Traffic thường có heavy-tail/hot items; một tỷ lệ nhỏ SKU hoặc danh mục chiếm phần lớn truy cập. Random uniform có thể **đánh giá thấp cache hit** và **đánh giá thấp hot-key contention**. Nên dùng phân bố thực tế từ logs đã tổng hợp hoặc generator Zipf/weighted buckets.

### 3.3. Tạo bộ dữ liệu có thể tái lập

Thực hành:

- Chọn dataset **synthetic/anonymized**; không copy PII, access token hoặc payment details production.
- Cố định seed/algorithm, số dòng, tỷ lệ categories, schema/index và version generator.
- Ghi thông số dataset vào test report.
- Duy trì nhiều dataset: `small` để smoke, `representative` tương ứng mức hiện tại, `growth` tương ứng 6–12 tháng.
- So sánh query plan sau `ANALYZE`; xác nhận statistics phù hợp và index tồn tại.
- Kiểm tra số dòng, min/max ID, phân bố danh mục, row/page size và DB size trước test.
- Reset dataset hoặc ghi rõ trạng thái đã tích lũy cho lần lặp sau; không so kết quả A/B khi một bên có 10 triệu events còn bên kia có 100 nghìn.

Dataset demo ở mục 9 là **200.000 products**, categories 50%/30%/20%, 70% lượt xem dự kiến vào 10% ID đầu và 30% vào toàn bộ ID. Đây là phân bố minh họa để luyện kỹ thuật, **không phải dữ liệu sản xuất của một công ty cụ thể**.

### 3.4. Cẩn thận với cache và tính đúng

Cần test cả cold/warm cache khi business cần, nhưng không trộn thành một số liệu p95 duy nhất:

- **Cold cache:** DB page cache/Redis/application cache chưa có dữ liệu; phản ánh rollout/restart, không phải mọi request.
- **Warm cache:** sau warm-up, hot keys được load; phản ánh steady-state của phần lớn traffic.
- **Cache invalidation:** writes có làm stale dữ liệu? Có thể cải thiện latency mà trả dữ liệu sai.
- **Query plan stability:** optimizer có dùng cùng index sau khi dữ liệu phình to và statistics thay đổi không?

Cùng một API 200 nhanh hơn 50% nhưng trả stale price hoặc mất event thì **không đạt correctness**. Load testing không được đánh đổi đúng dữ liệu lấy tốc độ.

## 4. Concurrency: VUs, requests đang xử lý và RPS là ba biến khác nhau

### 4.1. Định nghĩa

- **User/session:** người dùng hoặc phiên có các hành động và khoảng nghỉ; một user có thể tạo nhiều request.
- **Virtual User (VU) của k6:** một thực thể thực thi JavaScript iterations; số VUs **không bằng** số người dùng Internet đang mở trình duyệt.
- **Arrival rate:** tốc độ bắt đầu iterations/transactions theo thời gian, ví dụ 50 iterations/s.
- **Request rate (RPS):** số HTTP requests được gửi hoặc hoàn tất mỗi giây; một iteration có thể chứa 1 hoặc nhiều requests.
- **Concurrency/in-flight:** số requests đang xử lý/chờ trong hệ thống tại một thời điểm.
- **Throughput:** số requests hoặc business transactions hoàn tất thành công trong một giây; cần nói rõ định nghĩa.
- **Thread count:** số Java/servlet worker threads, không đồng nghĩa in-flight requests hoặc connection count.
- **DB pool active:** số database connections đang mượn, không đồng nghĩa số request HTTP đang xử lý.

### 4.2. Little's Law là phép kiểm tra, không phải công thức tạo VUs

Trong hệ thống ổn định, với arrival rate `λ` (requests/giây), mean response time `W` (giây) và mean concurrent in-flight requests `L`:

```text
L ≈ λ × W
```

Ví dụ **minh họa toán học**: 50 requests/s và thời gian trong hệ thống trung bình 0,2 s → khoảng 10 requests đồng thời. Nếu latency tăng lên 1 s trong khi arrival rate vẫn 50/s, khoảng 50 requests đồng thời. Khi hệ thống bắt đầu queue/drops/errors, điều kiện ổn định có thể không còn; đừng áp công thức như bằng chứng khả năng chịu tải.

**Không thay `W` bằng p95** trong công thức Little's Law. Công thức liên quan **mean** cùng ranh giới đo, không phải percentiles. Nếu một transaction gồm nhiều HTTP calls, còn phải phân biệt transaction concurrency với HTTP request concurrency.

### 4.3. Closed workload: số VUs cố định

K6 executor `constant-vus` hoặc `ramping-vus` mô phỏng một số actor/phiên đồng thời:

```text
VU -> gọi HTTP -> chờ response -> nghĩ 1–3 giây -> gọi tiếp
```

Nếu server chậm, VU chờ lâu hơn, số requests/s **tự giảm**. Đây là hành vi hợp lý cho một số loại user sessions; nhưng nếu production arrival rate vẫn tiếp tục tăng khi backend chậm, closed model có thể che overload (**coordinated omission**).

Dùng closed model khi muốn kiểm tra một số user sessions/think-time hoặc journey cụ thể. Đừng suy rằng “100 VUs = 100 RPS”.

### 4.4. Open workload: arrival rate độc lập response

K6 `constant-arrival-rate` và `ramping-arrival-rate` **lên lịch bắt đầu iterations theo tốc độ đặt trước**, miễn có đủ VUs. Phù hợp hệ thống cần mô phỏng traffic arrival từ Internet, queue hoặc event stream.

```text
Mốc mỗi 20 ms: bắt đầu iteration mới (~50/s)
      |
      +----> HTTP request A (có thể chờ 100 ms)
      +----> HTTP request B (có thể chờ 500 ms)
      +----> HTTP request C ...
```

Ở open model, **VU chỉ là tài nguyên để khởi tạo iterations đúng lịch**. Nếu VUs không đủ vì quá ít pre-allocation hoặc SUT quá chậm, k6 ghi `dropped_iterations`. Khi đó **achieved rate thấp hơn target**, và không được báo “hệ thống đạt 100 RPS” chỉ dựa trên config `rate:100`.

Khi mỗi iteration đúng **một HTTP request**, target iterations/s gần bằng target requests/s nếu không drops. Nếu iteration chứa login + catalog + checkout (3 requests), 50 iterations/s không phải 50 HTTP RPS, mà có thể tạo ~150 HTTP requests/s. Phải báo cáo cả hai cấp.

### 4.5. Chọn số VUs cho arrival rate

Lấy estimate ban đầu từ `arrival rate × average iteration duration`, cộng headroom cho variance/tail. Ví dụ 50 iterations/s × 0,2s ≈ 10 VUs, nhưng có thể cần nhiều hơn nếu latency p99 dài, payload parsing, auth, think time hoặc nhiều requests/iteration.

- `preAllocatedVUs`: số VUs sẵn sàng trước test.
- `maxVUs`: giới hạn cấp phát bổ sung; cấp phát trong runtime cũng gây overhead.
- `dropped_iterations`: số iterations lẽ ra bắt đầu nhưng không có VU rảnh hoặc bị giới hạn.

**Đừng chữa mọi dropped iterations bằng cách tăng VUs vô hạn**. Nếu latency SUT tăng, cần điều tra DB/thread pool/CPU; nếu generator CPU quá tải hoặc initial VUs quá ít, cần sửa generator. Phân biệt bằng metrics ở cả hai phía.

## 5. Thời gian chạy đại diện: warm-up, steady-state, peak và soak

### 5.1. Vì sao 10–30 giây không đủ?

Một bài test quá ngắn có thể bị ảnh hưởng bởi:

- JVM class loading, JIT warm-up, dynamic recompilation.
- PostgreSQL buffer cache chưa nóng hoặc đã nóng từ lần chạy trước.
- Hikari connection pool chưa đạt hành vi ổn định.
- GC chưa đi qua đủ chu kỳ.
- Autoscaling chưa kịp thêm replicas hoặc hoàn thành rolling rollout.
- Database checkpoint, autovacuum, WAL, background jobs, cache expiration chưa xảy ra.
- Connection leak/memory leak tích lũy quá chậm để xuất hiện.
- Hệ thống logging/metrics collector chưa có đủ mẫu p99.

Do đó, **thời lượng là một phần của thiết kế workload**, không phải chỉ lựa chọn để tiết kiệm thời gian.

### 5.2. Một profile ví dụ

| Giai đoạn | Mức tải minh họa | Thời lượng minh họa | Cần quan sát |
| --- | --- | --- | --- |
| Smoke | 1–5 RPS | 1–3 phút | Script, schema, correctness |
| Warm-up | 10–20 RPS | 3–5 phút | JIT, pool, cache, DB buffer |
| Baseline | 50 RPS | 10–15 phút | p95/p99, errors, CPU, connections |
| Expected peak | 100 RPS | 15–30 phút | SLO, autoscaling, queue |
| Stress | 100 → 150 → 200 RPS | 5–10 phút mỗi bậc | Capacity knee và degrade mode |
| Spike | 20 → 200 → 20 RPS | Vài phút mỗi bậc | Burst, queue, recovery |
| Soak | 60–80 RPS | 1–4 giờ hoặc hơn | Heap, GC, WAL, bloat, pool |
| Recovery | Theo scenario | Theo thời gian failover | Error budget và hồi phục |

**Không có một con số thời gian đúng cho mọi hệ thống.** Nếu peak thật kéo dài 45 phút, test peak 3 phút là thiếu. Nếu workload có batch chạy mỗi 30 phút, soak 20 phút có thể bỏ lỡ. Nếu cần đánh giá memory leak mỗi 6 giờ, bài 1 giờ không đủ.

### 5.3. Tách metric theo giai đoạn

Không báo một p95 duy nhất trộn warm-up, steady-state và ramp-down. Cần đo theo test run/stage hoặc tag/series time range; đặc biệt **bỏ warm-up khỏi quyết định steady-state SLO**, nhưng vẫn lưu warm-up như một phase riêng cho release-readiness.

Ví dụ baseline chạy 3 lần với cùng dataset/hardware và ghi nhận variance; một lần “đẹp” không đủ. Nếu p95 biến động lớn, xem host noisy neighbor, cache state, background tasks hoặc autoscaling timing.

## 6. Metrics phải quan sát cùng lúc

### 6.1. Bốn nhóm kết quả từ k6

| Metric | Đọc thế nào | Lưu ý |
| --- | --- | --- |
| `http_reqs` | Số HTTP requests được gửi; rate tổng | Có thể bao gồm requests thất bại |
| `http_req_duration` | Sending + waiting + receiving | Không bao gồm toàn bộ DNS/connection setup |
| `http_req_waiting` | Thời gian chờ byte đầu tiên (TTFB) | Hỗ trợ phân biệt upstream processing |
| `http_req_failed` | Tỷ lệ request thất bại theo k6 expected-response policy | Không thay business correctness checks |
| `checks` | Tỷ lệ assertions như status/body đúng | Phải kiểm tra, không chỉ status 200 |
| `iterations` | Số k6 business iterations | Có thể khác HTTP requests |
| `iteration_duration` | Thời gian một iteration | Bao gồm logic script, nhiều calls, think time |
| `vus`/`vus_max` | Virtual users đang hoạt động/cấp phát | Không bằng HTTP concurrency |
| `dropped_iterations` | Iterations không được khởi chạy đúng lịch | Target load **không đạt** |
| `data_received`/`data_sent` | Dung lượng network | Cần xét payload sizes/headers |

Theo tài liệu k6, `http_req_duration` đo `sending + waiting + receiving`. Khi cần phân tích TLS/DNS/connection reuse, xem thêm `http_req_blocked`, `http_req_connecting` và `http_req_tls_handshaking`. Browser perceived latency còn có render/JS/user interaction, không đồng nhất hoàn toàn với k6 HTTP timing.

### 6.2. Percentiles và lỗi

Giả sử có 10.000 request với p95 = 300 ms: tối thiểu khoảng 95% số requests được đo hoàn tất không quá 300 ms. p99 là ngưỡng khoảng 99% — phản ánh tail latency nhưng cần đủ mẫu.

**Không đánh giá chỉ bằng avg** vì 99 requests 10 ms và một request 5.000 ms vẫn có average thấp hơn trải nghiệm tệ của người dính timeout.

Một phép đo cần:

- p50/p90/p95/p99 **theo endpoint hoặc operation class**;
- latency của successful requests và error responses; lỗi nhanh không được làm p95 nhìn “đẹp” giả;
- error rate HTTP + business correctness failures;
- achieved RPS, expected RPS và dropped iterations;
- time series theo phút để thấy drift, không chỉ summary cuối bài.

Với sample ít, p99 có độ bất định cao. Đừng khẳng định “p99 đạt SLO” khi chỉ có 50 requests cho endpoint hiếm. Cần số mẫu đủ theo interval, confidence/repeats và workload mix.

### 6.3. Server Spring Boot/Tomcat

Khi thêm Actuator/Micrometer và cấu hình metrics hợp lệ, có thể theo dõi:

- `http.server.requests`: số/laten­cy HTTP server requests theo method/status/route (tùy instrumentation).
- `jvm.memory.used`, `jvm.gc.pause`: heap/GC pressure.
- `process.cpu.usage`, `system.cpu.usage`: CPU cùng host/process.
- `tomcat.threads.busy` và `tomcat.threads.current` khi Tomcat metrics được bật/bind.
- `jdbc.connections.active`, `jdbc.connections.idle`, `jdbc.connections.max`: pool utilization.
- `hikaricp.connections.pending`, `hikaricp.connections.timeout` và các metrics Hikari khi có.
- `process.files.open`, threads và network sockets nếu runtime/environment hỗ trợ.

Tên/nhãn chính xác phụ thuộc Spring Boot/metrics registry và instrumentation. **Không giả định mọi metric đều tự có** hoặc Actuator JSON metrics phù hợp Prometheus scraping. Cần thêm `micrometer-registry-prometheus` nếu muốn endpoint `/actuator/prometheus`.

### 6.4. Database PostgreSQL

Một load test nghiêm túc cần đọc PostgreSQL đồng thời:

- `pg_stat_activity`: active connections, wait_event, long transactions.
- `pg_stat_database`: commits/rollbacks, block hits/reads, temp files, deadlocks.
- `pg_stat_statements` (nếu được bật/được cấp quyền): latency/total time của query templates.
- `EXPLAIN (ANALYZE, BUFFERS)` trên query đại diện, lưu ý câu lệnh thực thi query và có overhead.
- Index scan vs sequential scan, sort/spill, lock waits, WAL bytes/checkpoints.
- Autovacuum, table/index growth, disk usage và IOPS.

**Nhiều threads đang bận không chứng minh CPU là bottleneck.** Có thể chúng đang đợi Hikari connection, DB locks, upstream HTTP hoặc file I/O. Cần xem wait states và traces.

## 7. Thiết kế workload dựa trên telemetry thay vì suy đoán

### 7.1. Nguồn để ước lượng profile

Thu thập dưới hình thức **aggregate, đã loại PII**:

1. Log/metrics HTTP theo route templates, method và HTTP status class.
2. RPS normal, peak 1 phút/5 phút/giờ và tốc độ thay đổi (burst).
3. Latency p50/p95/p99 từng operation, size request/response.
4. Số active sessions, requests/user/session, think time và hành trình thường gặp.
5. Phân bố product IDs/categories/tenants **sau khi ẩn danh**, tỷ lệ hot/cold keys.
6. Tỷ lệ cache hit/miss, DB query plan, connection pool, retry.
7. Tỷ lệ 4xx do người dùng (không đếm như server failure khi expected).
8. Tốc độ tạo/đổi dữ liệu theo thời gian, retention/cleanup jobs.
9. Theo dõi background tasks, events, batch jobs và autoscaling.
10. Kích thước dataset hiện tại + dự báo tăng trưởng.

Đừng copy access logs thô có IP, cookie, Authorization, user IDs hoặc PII vào một công cụ benchmark bên ngoài. Có thể tổng hợp top route proportions, percentiles và synthetic parameter distributions mà không đưa bí mật vào testcase.

### 7.2. Ví dụ traffic mix minh họa

| Operation | Xác suất trong một HTTP request | Kiểu data | Tác động |
| --- | --- | --- | --- |
| GET `/api/products/{id}` | 80% | 70% hot IDs, 30% toàn miền | Point lookup/cache |
| GET `/api/products/search` | 15% | Categories weighted 50/30/20; offset nhiều mức | Index scan và pagination |
| POST `/api/events` | 5% | Product ID hợp lệ + session key synthetic | INSERT, WAL và table growth |

Tổng 100%. Với k6 script ở mục 10, mỗi iteration **gửi đúng một HTTP request**, nên target iterations/s có thể quy đổi trực tiếp sang target HTTP requests/s khi không dropped iterations. Ở hệ thống thật một transaction có thể gồm nhiều calls; lúc đó phải ghi rõ conversion.

### 7.3. Dữ liệu "thật" không chỉ là danh sách IDs

Một search endpoint với 1.000 đồng nhất items có thể dùng query plan khác khi database có 10 triệu rows, categories không cân bằng và nhiều offset lớn. Test phải xác nhận:

- Row count, category selectivity và indexes.
- Kích thước working set có vượt RAM không.
- Update/write pattern có tạo churn/locks/WAL.
- Query parameter distributions: offset, sort, filter combinations.
- Payload/chunking, gzip, connection reuse, TLS.
- Auth costs, token refresh, session store nếu production dùng.
- Downstream failures/latency distribution nếu có.

Không cần tự sao chép dữ liệu production. Synthetic dataset được tạo dựa trên **thống kê thật** thường đủ để đo mà không làm lộ thông tin.

## 8. Chuẩn bị môi trường benchmark có thể tái lập

### 8.1. Những thông tin bắt buộc ghi trong report

| Nhóm | Nội dung cần đóng băng |
| --- | --- |
| Source/build | Git revision, artifact checksum, JDK/Boot version |
| SUT topology | Số pods/instances, vCPU/RAM, JVM args, web threads |
| DB | PostgreSQL version, connection limits, pool size, indexes |
| Network | Load generator ở đâu, TLS, LB/CDN/proxy, latency RTT |
| Dataset | Seed/version, row count, size, skew, preexisting events |
| Traffic | Mix/weights, RPS/VUs, read/write, think time |
| Time | Warm-up, steady, peak, soak, timezone và ngày chạy |
| Cache | Cold/warm, TTL, CDN/Redis config |
| SLO | p95/p99/errors/drop thresholds và sampling rules |
| Infrastructure | Autoscale policy, sidecars, monitors, background jobs |

Đo trên laptop và kết luận “production chịu được 1.000 RPS” là không hợp lệ. Lab ở bài này giúp học kỹ thuật; capacity planning production cần môi trường gần production, isolation và quy trình được phê duyệt.

### 8.2. Không test không được phép

Chỉ gửi tải tới **localhost hoặc môi trường đã được owner cho phép**, với RPS, IP nguồn, thời gian và data reset được phê duyệt. Không gửi scripts tải cao tới API public hoặc hệ thống đối tác thật mà chưa thống nhất quota, ảnh hưởng và rollback. Tránh tạo payment/email/order side effects thật khi đo tải.

### 8.3. Tách load generator khỏi SUT khi đo nghiêm túc

Chạy k6 và PostgreSQL trên cùng laptop tạo **resource contention**. K6 có thể tự hết CPU/sockets trước khi Spring Boot chạm giới hạn. Cho đo tải thực, dùng host load generator độc lập, kiểm tra CPU/memory/network của generator và phân tán khi cần. So sánh observed target vs achieved rate.

### 8.4. Repeatability và sai số

- Chạy cùng scenario ít nhất vài lần, so median/p95/time series.
- Đổi một biến mỗi thí nghiệm: ví dụ pool 10 → 20 connections, giữ dataset/tải giống nhau.
- Giữ SUT cùng warmed state hoặc đánh dấu cold-start rõ.
- Không so p95 từ 2 phút ở 5.000 rows với 30 phút ở 2 triệu rows như thể chỉ khác một property.
- Đừng quên DB background processes, OS page cache và autoscaling.
- Ghi lỗi và “dropped iteration” bên cạnh các kết quả tốc độ.

## 9. Project Spring Boot đầy đủ với PostgreSQL và dữ liệu không tầm thường

### 9.1. Kịch bản của lab

Ta dựng một **API sản phẩm và sự kiện**:

- 200.000 products trong PostgreSQL.
- `GET /api/products/{id}` đọc theo primary key.
- `GET /api/products/search?category=books&limit=20&offset=100` tìm category có index.
- `POST /api/events` ghi event VIEW/CART. **Mỗi POST là một sự kiện**, không auto-retry vì có thể tạo duplicate.
- Actuator `health,metrics` chạy trên loopback port 9091 để quan sát.
- k6 tạo mix 80/15/5, hot-key skew, mức RPS và duration do người chạy chọn.

Demo dùng PostgreSQL qua Docker Compose để phản ánh JDBC pool/SQL/index/WAL tốt hơn H2 in-memory. Tuy nhiên **một Postgres container trên cùng laptop vẫn không phải production PostgreSQL cluster**; không dùng kết quả lab để suy luận capacity thật.

### 9.2. Cấu trúc thư mục

```text
realistic-load-demo/
├── pom.xml
├── compose.yaml
├── db/
│   └── init.sql
├── load/
│   ├── open-model.js
│   └── closed-model.js
└── src/
    └── main/
        ├── java/com/example/loadstudy/
        │   ├── LoadStudyApplication.java
        │   ├── Product.java
        │   ├── ProductRepository.java
        │   ├── ProductsController.java
        │   └── EventsController.java
        └── resources/
            └── application.properties
```

Các tệp nguồn dưới đây là **toàn bộ mã của lab tối thiểu**, không cần một API partner bên ngoài. Bạn cần **JDK 17+, Maven, Docker Compose và k6** để chạy đầy đủ. `docker compose` chỉ cấp PostgreSQL; Spring Boot và k6 chạy bằng lệnh riêng trên host.

### 9.3. `pom.xml` hoàn chỉnh

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>realistic-load-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot BOM quản lý tương thích của Spring JDBC/Tomcat/Jackson/HikariCP/PostgreSQL driver. Không ghim từng Spring Framework artifact sang một phiên bản khác để “tối ưu benchmark”. `Spring Boot 3.5.16` được cố định nhằm tái lập lab; khi triển khai production hãy dùng một nhánh Boot đang được bảo trì theo chính sách tổ chức.

### 9.4. `compose.yaml`: PostgreSQL local

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: perfdb
      POSTGRES_USER: perf
      POSTGRES_PASSWORD: dev-only-password
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - ./db/init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U perf -d perfdb"]
      interval: 5s
      timeout: 3s
      retries: 30
```

- Port DB bind loopback **host**, không publish DB ra Internet.
- Password `dev-only-password` chỉ là giá trị **demo**. Không đưa credential lab vào production.
- `db/init.sql` chạy khi PostgreSQL container khởi tạo database data directory lần đầu; nếu đã có persistent volume/data, script **không tự chạy lại**.
- `postgres:16` cố định major version nhưng minor/digest có thể thay theo thời gian; trong benchmark so sánh nghiêm túc cần **pin image digest** và ghi config PostgreSQL.
- Nếu cổng 5432 đang bận, đổi published host port và JDBC URL tương ứng.

### 9.5. `db/init.sql`: 200.000 products có index và một bảng ghi sự kiện

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    category TEXT NOT NULL,
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE visit_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    session_key VARCHAR(64) NOT NULL,
    event_type VARCHAR(16) NOT NULL
        CHECK (event_type IN ('VIEW', 'CART')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed deterministic: 50% books, 30% electronics, 20% home.
INSERT INTO products (id, category, price_cents, stock, created_at)
SELECT
    n,
    CASE
        WHEN n % 10 < 5 THEN 'books'
        WHEN n % 10 < 8 THEN 'electronics'
        ELSE 'home'
    END,
    1000 + ((n * 37) % 100000),
    (n * 29) % 200,
    now() - (n % 365) * INTERVAL '1 day'
FROM generate_series(1, 200000) AS seq(n);

CREATE INDEX idx_products_category_id
    ON products(category, id);

CREATE INDEX idx_visit_events_product_time
    ON visit_events(product_id, created_at DESC);

ANALYZE products;
```

**Tính chất dataset có thể kiểm tra:**

- Đúng **200.000** products có IDs 1..200000.
- 100.000 rows `books`, 60.000 `electronics`, 40.000 `home` do modulo 10.
- Mỗi giá `price_cents` ở khoảng 1.000..100.999, có stock 0..199.
- `created_at` trải nhiều ngày, thay vì mọi row có cùng timestamp.
- Index `(category,id)` giúp truy vấn category + `ORDER BY id`.
- `visit_events` ban đầu trống; tăng theo các POST trong load test, tạo WAL và disk/index growth.

Đây vẫn là dữ liệu **synthetic có công thức đơn giản**, không tái hiện correlation/hotspot thật của mọi hệ thống. Với workload doanh nghiệp, điều chỉnh schema, data size, payload width và distribution theo telemetry.

### 9.6. `LoadStudyApplication.java`

```java
package com.example.loadstudy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoadStudyApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoadStudyApplication.class, args);
    }
}
```

### 9.7. `Product.java`

```java
package com.example.loadstudy;

public record Product(
        long id,
        String category,
        int priceCents,
        int stock) {
}
```

Record Java 17 giúp tạo DTO rõ kiểu. Tên JSON output theo Jackson là `priceCents`, không phải SQL column `price_cents`. Điều này quan trọng khi viết assertions ở k6.

### 9.8. `ProductRepository.java` dùng JdbcTemplate và SQL parameterized

```java
package com.example.loadstudy;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductRepository {

    private final JdbcTemplate jdbc;

    public ProductRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<Product> find(long id) {
        List<Product> results = jdbc.query(
                """
                SELECT id, category, price_cents, stock
                FROM products
                WHERE id = ?
                """,
                (rs, row) -> new Product(
                        rs.getLong("id"),
                        rs.getString("category"),
                        rs.getInt("price_cents"),
                        rs.getInt("stock")),
                id);
        return results.stream().findFirst();
    }

    public List<Product> search(
            String category, int limit, int offset) {
        return jdbc.query(
                """
                SELECT id, category, price_cents, stock
                FROM products
                WHERE category = ?
                ORDER BY id
                LIMIT ? OFFSET ?
                """,
                (rs, row) -> new Product(
                        rs.getLong("id"),
                        rs.getString("category"),
                        rs.getInt("price_cents"),
                        rs.getInt("stock")),
                category, limit, offset);
    }

    public long appendEvent(
            long productId, String sessionKey,
            String eventType) {
        Long id = jdbc.queryForObject(
                """
                INSERT INTO visit_events
                    (product_id, session_key, event_type)
                VALUES (?, ?, ?)
                RETURNING id
                """,
                Long.class, productId, sessionKey, eventType);
        if (id == null) {
            throw new IllegalStateException(
                    "INSERT did not return an event id");
        }
        return id;
    }
}
```

**Giải thích:**

- SQL dùng bind parameters `?`, tránh tự nối input vào SQL.
- `find` là point lookup theo primary key; `search` dùng category/index và offset pagination.
- `appendEvent` dùng cú pháp PostgreSQL `INSERT ... RETURNING id`; demo chủ ý không portable sang mọi database.
- Mỗi HTTP GET/POST dùng một số thao tác JDBC được điều phối qua HikariCP.
- Bảng events không chứa PII và không có logic idempotency. **Không retry POST một cách mù quáng** khi network timeout, vì có thể insert trùng.
- Search với `OFFSET 5000` chỉ là một mức độ phân trang; với offset vài triệu, keyset pagination có thể cần thiết để tránh scan bỏ qua quá nhiều rows.

### 9.9. `ProductsController.java`

```java
package com.example.loadstudy;

import java.util.List;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/products")
public class ProductsController {

    private static final Set<String> CATEGORIES =
            Set.of("books", "electronics", "home");

    private final ProductRepository products;

    public ProductsController(ProductRepository products) {
        this.products = products;
    }

    @GetMapping("/{id}")
    public ResponseEntity<Product> byId(
            @PathVariable long id) {
        if (id < 1 || id > 200000) {
            return ResponseEntity.notFound().build();
        }
        return products.find(id)
                .map(ResponseEntity::ok)
                .orElseGet(() ->
                        ResponseEntity.notFound().build());
    }

    @GetMapping("/search")
    public List<Product> search(
            @RequestParam String category,
            @RequestParam(defaultValue = "0") int offset,
            @RequestParam(defaultValue = "20") int limit) {

        if (!CATEGORIES.contains(category)
                || offset < 0 || offset > 5000
                || limit < 1 || limit > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Invalid search parameters");
        }

        return products.search(category, limit, offset);
    }
}
```

`GET /api/products/search` dùng literal path, nên Spring MVC ưu tiên nó so với biến `/{id}`. Input validation giới hạn category/offset/limit, tránh query không kiểm soát và đảm bảo test có phạm vi. `byId` đang giới hạn ID 1..200000 **theo dataset lab**; trong production không nên hardcode kích thước dữ liệu vào controller.

### 9.10. `EventsController.java`: ghi sự kiện hợp lệ

```java
package com.example.loadstudy;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

record EventInput(
        @Min(1) long productId,
        @NotBlank @Size(max = 64) String sessionKey,
        @NotBlank @Pattern(regexp = "VIEW|CART") String eventType) {
}

@RestController
@RequestMapping("/api/events")
public class EventsController {

    private final ProductRepository products;

    public EventsController(ProductRepository products) {
        this.products = products;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Map<String, Long> append(
            @Valid @RequestBody EventInput input) {
        long id = products.appendEvent(
                input.productId(),
                input.sessionKey(),
                input.eventType());
        return Map.of("id", id);
    }
}
```

Mỗi POST hợp lệ tạo một row `visit_events` và trả **HTTP 201** với JSON chứa một ID dương. Trong database mới không có sự kiện nào, ID đầu thường là 1; **không hardcode expected ID=1** trong benchmark do lặp test hoặc transaction rollback có thể tăng sequence.

Lưu ý: tính đúng của endpoint demo là **ghi một event cho mỗi request được chấp nhận**, không phải checkout/payment. Với thao tác tài chính production cần idempotency key, transactional semantics, auth và consistency khác.

### 9.11. `application.properties`

```properties
spring.application.name=realistic-load-demo

# Lab chỉ nghe HTTP từ host local.
server.port=8080
server.address=127.0.0.1

# PostgreSQL do Docker Compose publish trên localhost.
spring.datasource.url=jdbc:postgresql://127.0.0.1:5432/perfdb
spring.datasource.username=${DB_USER:perf}
spring.datasource.password=${DB_PASSWORD:dev-only-password}

# Pool có kích thước hữu hạn để quan sát saturation.
spring.datasource.hikari.maximum-pool-size=16
spring.datasource.hikari.minimum-idle=4
spring.datasource.hikari.connection-timeout=2000
spring.datasource.hikari.pool-name=perfPool

# Điều chỉnh có chủ đích cho lab, không phải default production.
server.tomcat.threads.max=64

# Actuator localhost-only cho health và metrics.
management.server.port=9091
management.server.address=127.0.0.1
management.endpoints.web.exposure.include=health,metrics
management.endpoint.health.show-details=never
```

Trong lab, cả main app và Actuator chỉ lắng nghe loopback. **Đừng benchmark từ máy khác** khi vẫn giữ `server.address=127.0.0.1`; nếu chuyển sang môi trường được phê duyệt, bind network phù hợp và bảo vệ endpoint/security. Actuator `metrics` được expose trên loopback **chỉ để quan sát local**; production không nên mở public.

`server.tomcat.threads.max=64` và Hikari max pool 16 là **giá trị giả định để có thể quan sát giới hạn**, không phải cấu hình tối ưu chung. Một servlet thread chờ Hikari có thể tăng latency dù CPU chưa đầy.

## 10. K6: workload mở với 80% detail, 15% search, 5% write

### 10.1. Tại sao chọn arrival-rate executor?

Bài này muốn giữ **tốc độ yêu cầu bắt đầu theo giây** độc lập latency SUT. Khi backend chậm, backlog/in-flight và tail latency tăng phải được nhìn thấy. Do mỗi iteration làm đúng một request, target iterations/s gần tương đương target HTTP RPS nếu không có dropped iterations.

K6 hỗ trợ `constant-arrival-rate` với `rate`, `timeUnit`, `duration` và `preAllocatedVUs`. Không đặt `sleep()` cuối iteration vì arrival-rate executor đã tự điều tiết tốc độ bắt đầu.

### 10.2. `load/open-model.js` — script hoàn chỉnh

```javascript
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE_URL || 'http://127.0.0.1:8080';
const PRODUCTS = Number(__ENV.PRODUCTS || '200000');
const TARGET_RPS = Number(__ENV.RPS || '20');
const VUS = Number(__ENV.VUS || '80');
const DURATION = __ENV.DURATION || '5m';

export const options = {
  scenarios: {
    mixedTraffic: {
      executor: 'constant-arrival-rate',
      rate: TARGET_RPS,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: VUS,
      maxVUs: VUS,
      gracefulStop: '15s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
    'http_req_duration{operation:detail}': [
      'p(95)<300', 'p(99)<800',
    ],
    'http_req_duration{operation:search}': [
      'p(95)<600',
    ],
    'http_req_duration{operation:event}': [
      'p(95)<800',
    ],
    dropped_iterations: ['count<1'],
  },
  summaryTrendStats: [
    'avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max',
  ],
};

// 70% đọc nhóm 10% IDs hot, 30% đọc toàn miền.
function randomProductId() {
  const hotCount = Math.max(1, Math.floor(PRODUCTS * 0.1));
  const range = Math.random() < 0.70 ? hotCount : PRODUCTS;
  return 1 + Math.floor(Math.random() * range);
}

// Tỷ lệ categories tương ứng seed SQL: 50/30/20.
function randomCategory() {
  const p = Math.random();
  if (p < 0.50) return 'books';
  if (p < 0.80) return 'electronics';
  return 'home';
}

function detail() {
  const id = randomProductId();
  const res = http.get(
    `${BASE}/api/products/${id}`,
    { tags: { name: 'GET /api/products/{id}', operation: 'detail' } },
  );
  check(res, {
    'detail HTTP 200 and correct id':
      (r) => r.status === 200 && Number(r.json('id')) === id,
  });
}

function search() {
  const category = randomCategory();
  const offsets = [0, 0, 20, 100, 1000, 5000];
  const offset = offsets[Math.floor(Math.random() * offsets.length)];
  const url = `${BASE}/api/products/search?category=${category}&limit=20&offset=${offset}`;
  const res = http.get(url, {
    tags: { name: 'GET /api/products/search', operation: 'search' },
  });
  check(res, {
    'search HTTP 200 and JSON array':
      (r) => r.status === 200 && Array.isArray(r.json()),
  });
}

function writeEvent() {
  const id = randomProductId();
  const session = `run-${__ENV.RUN_ID || 'local'}-vu-${__VU}-it-${__ITER}`;
  const payload = JSON.stringify({
    productId: id,
    sessionKey: session,
    eventType: Math.random() < 0.9 ? 'VIEW' : 'CART',
  });
  const res = http.post(`${BASE}/api/events`, payload, {
    headers: { 'Content-Type': 'application/json' },
    tags: { name: 'POST /api/events', operation: 'event' },
  });
  check(res, {
    'event HTTP 201 and positive id':
      (r) => r.status === 201 && Number(r.json('id')) > 0,
  });
}

export default function () {
  const p = Math.random();
  if (p < 0.80) {
    detail();
  } else if (p < 0.95) {
    search();
  } else {
    writeEvent();
  }
}
```

**Ý nghĩa của script:**

- `RPS`/`DURATION`/`VUS` có thể đổi bằng k6 `-e`; mặc định **20 iterations/s trong 5 phút**.
- `PRODUCTS=200000` phải khớp dataset; nếu đổi seed, cập nhật biến k6.
- `preAllocatedVUs` bằng `maxVUs` để tránh cấp phát VUs động; nếu có drops, cần xác định do SUT chậm, generator giới hạn hay preallocation quá ít.
- Mỗi iteration chọn đúng **một** branch ⇒ một HTTP request; tỉ lệ 80/15/5 đạt gần đúng theo số lần bốc thăm, không chắc đúng tuyệt đối khi sample nhỏ.
- `tags.name`/`operation` có cardinality thấp để nhóm endpoint. Không tự tag productId/sessionKey vào metric name/tag.
- `RUN_ID` nên là chuỗi synthetic ngắn (dưới khoảng 16 ký tự), tránh vượt `session_key VARCHAR(64)` khi cùng các VU/iteration suffix.
- GET chọn IDs đã seed; search chỉ dùng category/offset hợp lệ; POST mỗi lần có sessionKey synthetic.
- `checks` xác nhận **status và nội dung** cơ bản. HTTP 200 với wrong product ID không được tính thành công chỉ vì status.
- Thresholds ví dụ p95/p99/error/drops **là ngưỡng luyện tập**, không phải SLO của hệ thống cụ thể.
- Khi k6 không có đủ VUs để phát target, `dropped_iterations` >0 khiến threshold fail; không được báo achieved rate bằng rate cấu hình.

**Giới hạn của script:** phân bố random này chỉ mang tính học tập; không tái hiện login, user journeys đa bước, TLS, CDN, cookies, pagination thật, retry và multi-tenant. Để đo production, điều chỉnh từ telemetry, không mặc định 80/15/5 hay 70% hot.

### 10.3. K6 không giống trình duyệt đầy đủ

K6 HTTP executor không render DOM, chạy JS frontend hoặc tải mọi ảnh/CSS như browser. Nếu SLA là user-perceived page load, cần thêm browser-level tests/RUM. Nếu SLA là API backend latency, HTTP-level k6 phù hợp hơn. Không quy số VU k6 thành số tab trình duyệt hoặc concurrent website visitors trực tiếp.

### 10.4. Lưu ý về read/write và trạng thái test

Ở 20 RPS × 5 phút, nếu đạt mọi iterations, khoảng **6.000 HTTP requests** và **~300 POST events** theo kỳ vọng toán học; số thực có thể khác do random, errors, dropped iterations và thời gian thực. Đây **không** phải kết quả đo đã chạy.

Bài soak 80 RPS × 2 giờ, với 5% POST, có **kỳ vọng** 28.800 events nếu toàn bộ tải được thực thi đúng; cần theo dõi table size/WAL/autovacuum và dùng cleanup/reset đúng môi trường.

## 11. K6 closed model: session và think time

Nếu cần mô phỏng nhóm người dùng liên tục thao tác và nghĩ giữa các hành động, dùng `constant-vus`. File `load/closed-model.js`:

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = __ENV.BASE_URL || 'http://127.0.0.1:8080';

export const options = {
  scenarios: {
    users: {
      executor: 'constant-vus',
      vus: Number(__ENV.VUS || '30'),
      duration: __ENV.DURATION || '5m',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
  },
};

export default function () {
  const id = 1 + Math.floor(Math.random() * 200000);
  const res = http.get(
    `${BASE}/api/products/${id}`,
    { tags: { name: 'GET /api/products/{id}', operation: 'detail' } },
  );
  check(res, { 'detail result': r => r.status === 200 });
  sleep(1 + Math.random() * 2);
}
```

Đây là một scenario **khác** để nghiên cứu, không phải thay thế trực tiếp kết quả open-model:

- Mỗi VU GET rồi nghỉ 1–3 giây; nếu server chậm, iteration lâu hơn ⇒ RPS giảm.
- `VUS=30` **không** có nghĩa 30 HTTP requests đồng thời tại mọi thời điểm.
- Không dùng closed-model result để khẳng định hệ thống chịu được arrival-rate target cố định.
- Khi muốn mô phỏng user journey, có thể phát triển login → search → detail → cart → checkout và think time đúng distribution, rồi đo **business transactions/s**.

## 12. Chạy lab từng bước và kiểm tra dữ liệu

### 12.1. Khởi động PostgreSQL

Từ thư mục `realistic-load-demo`:

```bash
docker compose up -d
docker compose ps
docker compose logs db --tail=20
```

Chờ healthcheck DB báo healthy và init SQL hoàn tất. Lần đầu cần tải image và tạo 200.000 rows, mất thời gian tùy máy; không giả định ngay lập tức sẵn sàng.

### 12.2. Kiểm tra seed SQL

```bash
docker compose exec -T db psql -U perf -d perfdb \
  -c "SELECT COUNT(*) AS product_count FROM products;"

docker compose exec -T db psql -U perf -d perfdb \
  -c "SELECT category, COUNT(*) FROM products GROUP BY category ORDER BY category;"

docker compose exec -T db psql -U perf -d perfdb \
  -c "SELECT COUNT(*) AS event_count FROM visit_events;"
```

Kết quả **trên database vừa khởi tạo**:

```text
product_count = 200000
books         = 100000
electronics   = 60000
home          = 40000
event_count   = 0
```

Đây là **giá trị SQL kỳ vọng**, không phải nguyên văn table formatting của psql. Nếu dùng volume từ lần chạy trước, data hoặc event_count có thể khác.

### 12.3. Build và chạy Spring Boot

JDK 17+, Maven, PostgreSQL healthy:

```bash
mvn clean package
java -jar target/realistic-load-demo-1.0.0.jar
```

Nếu dùng IDE, chắc chắn chạy từ đúng project và `application.properties`. Nếu cổng 8080/9091/5432 bận, sửa cấu hình và cập nhật URL trong k6.

### 12.4. Smoke test HTTP

Ở terminal khác:

```bash
curl -i http://127.0.0.1:8080/api/products/42

curl -i "http://127.0.0.1:8080/api/products/search?category=books&offset=0&limit=2"

curl -i -X POST http://127.0.0.1:8080/api/events \
  -H "Content-Type: application/json" \
  --data '{"productId":42,"sessionKey":"demo-1","eventType":"VIEW"}'
```

Với `GET /api/products/42`, expected status **200**, body JSON chứa đúng các trường:

```json
{"id":42,"category":"books","priceCents":2554,"stock":18}
```

Vì `42 % 10 = 2` nên category `books`; `1000 + 42×37 = 2554`; `42×29 % 200 = 18`. Thứ tự JSON keys không phải hợp đồng.

Search `books` với limit 2 trả một **mảng gồm hai products**; IDs bắt đầu theo các category rows hợp lệ và sắp xếp tăng dần. POST hợp lệ trả **HTTP 201** cùng JSON chứa ID sự kiện dương, ví dụ dạng:

```json
{"id":1}
```

**ID 1 chỉ đúng khi bảng mới hoàn toàn và chưa có INSERT nào khác**. Những lần chạy tiếp theo ID có thể lớn hơn; assertions chỉ yêu cầu ID dương. Đừng reset bảng đang được hệ thống khác dùng.

### 12.5. Metrics từ Actuator

Sau khi gọi vài requests:

```bash
curl -i http://127.0.0.1:9091/actuator/health

curl -s http://127.0.0.1:9091/actuator/metrics

curl -s http://127.0.0.1:9091/actuator/metrics/http.server.requests

curl -s http://127.0.0.1:9091/actuator/metrics/jdbc.connections.active
```

Đây là endpoint **metrics JSON**, không phải Prometheus text. Số metrics thực hiển thị phụ thuộc instrumentation và runtime; không tự cam kết một giá trị hoặc danh sách name cố định. Trong production phải bảo vệ Actuator bằng network/auth, không mở metrics public.

### 12.6. Warm-up rồi chạy baseline

Khi k6 được cài theo tài liệu chính thức:

```bash
k6 run -e RPS=10 -e VUS=40 -e DURATION=3m \
  load/open-model.js

k6 run -e RPS=50 -e VUS=100 -e DURATION=10m \
  --summary-export=baseline-50rps.json \
  load/open-model.js
```

Ngưỡng k6 có thể fail trên laptop yếu; fail là **thông tin cần điều tra**, không phải lỗi phải che. So với report production, 10 phút là một baseline học tập, không đảm bảo đủ mọi chu kỳ background/GC.

### 12.7. Đo peak và kiểm tra giới hạn

```bash
k6 run -e RPS=100 -e VUS=150 -e DURATION=15m \
  --summary-export=peak-100rps.json \
  load/open-model.js

k6 run -e RPS=150 -e VUS=250 -e DURATION=10m \
  --summary-export=stress-150rps.json \
  load/open-model.js
```

**Chỉ chạy với máy và môi trường được phép chịu tải.** Các con số trên để dạy cách profile; không phải mục tiêu SLO hay định mức an toàn cho laptop. Trước khi nâng tải, quan sát errors, dropped iterations, Hikari pending, DB CPU/disk, k6 generator CPU và dung lượng dữ liệu phát sinh.

### 12.8. Đo session-based closed model

```bash
k6 run -e VUS=30 -e DURATION=5m \
  load/closed-model.js
```

Lưu kết quả separate, **không so RPS trực tiếp** với open model nếu không mô tả rõ think time và transaction model.

### 12.9. Kiểm tra event growth và reset lab

```bash
docker compose exec -T db psql -U perf -d perfdb \
  -c "SELECT COUNT(*) FROM visit_events;"

docker compose exec -T db psql -U perf -d perfdb \
  -c "SELECT pg_size_pretty(pg_total_relation_size('visit_events'));"
```

Để reset database local demo **khi chắc chắn không có dữ liệu cần giữ**:

```bash
docker compose down -v
docker compose up -d
```

**Cảnh báo:** `down -v` xóa volumes của Compose project, không chạy trên môi trường có dữ liệu cần bảo toàn. Trong hệ thống thật cần quy trình seed/cleanup riêng được phê duyệt, snapshot và dữ liệu synthetic.

## 13. Thiết kế stress, spike và soak vượt bài baseline

### 13.1. Ramping arrival rate theo nhiều bậc

Nếu cần mô phỏng biến thiên đến của requests, dùng k6 `ramping-arrival-rate`. **Snippet cấu hình** thay cho phần `scenarios` trong `open-model.js`:

```javascript
scenarios: {
  ramped: {
    executor: 'ramping-arrival-rate',
    startRate: 10,
    timeUnit: '1s',
    preAllocatedVUs: 150,
    maxVUs: 150,
    stages: [
      { target: 50, duration: '3m' },
      { target: 50, duration: '10m' },
      { target: 100, duration: '3m' },
      { target: 100, duration: '15m' },
      { target: 10, duration: '3m' },
    ],
  },
},
```

Đây là **fragment của object options**, không phải file JS độc lập. Tổng scheduled phase là **34 phút**; tốc độ có thể biến thiên tuyến tính trong các đoạn ramp. Phân tích p95 theo từng stage/time window, không trộn toàn bộ 34 phút.

### 13.2. Stress test tìm capacity knee

Tăng từng mức (ví dụ 20 → 50 → 80 → 100 → 120 RPS) và giữ đủ thời gian ở mỗi bậc. Điểm bắt đầu có thể thấy:

- p95/p99 tăng nhanh hơn RPS.
- Throughput không tăng theo arrival rate.
- `dropped_iterations` tăng vì VUs hết do iterations dài.
- Hikari pending/timeout và DB locks tăng.
- Tomcat worker threads busy gần max.
- CPU throttling, GC pauses hoặc network queues tăng.
- Tỷ lệ 503/timeout tăng và hệ thống cần thời gian hồi phục.

Điểm chạm SLO trước khi crash là **giới hạn hữu ích hơn** một con số “tối đa 500 RPS” khi 40% requests đã lỗi.

### 13.3. Spike và autoscaling

Ở cluster có autoscaler:

- Kiểm tra time-to-scale-out và startup/readiness.
- Đánh giá connection pool của **mỗi replica** có khiến tổng DB connections vượt DB max không.
- Thử burst và phục hồi sau spike, không chỉ trạng thái cuối.
- Đảm bảo load generator phát được target rate trong khi SUT scaling.
- Lưu các sự kiện HPA, scheduling delays, image pull, warm cache.

Autoscaler không tức thời; một spike ngắn có thể làm queue/timeout tăng trước khi replicas mới Ready.

### 13.4. Soak test và data growth

Bài soak 1–4 giờ (hoặc lâu hơn tùy chu kỳ) cần quan sát **time series**:

- Heap sau GC có quay về baseline không?
- Hikari active/pending/timeout có trôi dần lên không?
- DB connections, locks và long transactions có tích tụ không?
- Table events/WAL/bloat tăng có làm p95 drift không?
- Background jobs/autovacuum/checkpoints có gây latency spikes không?
- Log/disk/temp file có đầy không?
- Có memory/resource leaks ở HTTP clients, JDBC connections, thread pools không?

Một bài soak được coi là có ý nghĩa khi **duy trì workload đại diện** và có quan sát đủ dài. Bài test “chạy 4 giờ nhưng chỉ một VU” không tự chứng minh peak endurance.

## 14. Phân tích kết quả: phân biệt bottleneck thật với vấn đề generator

### 14.1. Quy tắc đọc kết quả đúng thứ tự

1. Kiểm tra **test có gửi đúng workload không**: target RPS/VUs, operation mix, dataset, duration.
2. Xem **achieved HTTP throughput**; nếu thấp hơn target, kiểm tra `dropped_iterations` và generator utilization.
3. Xem **correctness** và error rate; response nhanh nhưng 500/404 hàng loạt là thất bại.
4. Xem p50/p95/p99 **riêng theo endpoint**, không chỉ tổng.
5. Đồng bộ mốc thời gian với CPU, GC, Tomcat, Hikari, PostgreSQL và network.
6. Tìm điểm thay đổi theo stage, xác định candidate bottleneck.
7. Thử thay **một biến** với cùng workload/dataset để xác minh giả thuyết.
8. Lặp test và báo variance; không kết luận từ một lần “đẹp”.

### 14.2. Minh họa toán học không phải số đo

Nếu đặt mục tiêu 100 iterations/s trong 10 phút, tổng scheduled iterations kỳ vọng là khoảng **60.000**. Nếu mỗi iteration làm đúng một request nhưng k6 chỉ gửi được 45.000 và ghi 15.000 dropped iterations, **không** báo kết quả là “đạt 100 RPS”. Achieved rate trung bình gần 75 req/s nếu 45.000 requests trải đúng 600 giây, còn độ phân bố theo thời gian cần xem thêm.

Nếu p95 detail <300ms nhưng search p95 >1s, tổng p95 có thể trông đạt do detail chiếm 80%. Vì vậy dùng **thresholds theo operation**; thao tác hiếm như checkout/payment còn cần latency/error metric riêng.

### 14.3. Ma trận triệu chứng → giả thuyết → phép thử

| Triệu chứng | Giả thuyết cần kiểm tra | Bằng chứng |
| --- | --- | --- |
| CPU 95%, GC thấp, throughput flat | CPU bound | CPU profile/flamegraph, request mix |
| CPU thấp, Tomcat busy max | Blocking waits/threads | Thread dumps, Hikari pending, downstream latency |
| Hikari pending tăng, active=max | DB connection pool saturated | `jdbc.connections.active`, Hikari metrics |
| DB CPU cao, queries chậm | Query/index/data volume | `EXPLAIN ANALYZE BUFFERS`, pg_stat_statements |
| DB lock waits | Hot-row writes/transaction contention | pg_locks, pg_stat_activity |
| p95 tăng theo thời gian, heap sau GC tăng | Leak/retained memory | JFR/heap analysis, GC logs |
| p99 spikes mỗi phút | Scheduled jobs/checkpoints | Time-aligned app/DB events |
| `dropped_iterations` có ngay ở tải thấp | VUs/generator allocation quá nhỏ | Generator CPU, VUs, iteration duration |
| Drops xuất hiện sau khi SUT latency tăng | Backpressure/capacity knee | VU usage, SUT metrics, RPS time series |
| GET ID nóng nhanh, random IDs chậm | Cache working set | Cache hit ratio, DB buffers |
| Search offset lớn chậm | Pagination scan/index | Query plan, LIMIT/OFFSET costs |
| POST event chậm sau soak dài | DB/WAL/index growth | Table size, vacuum, disk IO |
| Lỗi 429 tăng | Rate limiter/upstream quota | Response headers, quota stats |
| Lỗi 503/504 qua proxy nhưng app logs ít | LB/proxy timeout/upstream networking | Proxy access/error logs |
| K6 host CPU 100%, SUT rảnh | Generator bottleneck | Generator metrics, split generators |
| HTTP 200 nhưng checks fail | Sai payload/business logic | Response validation và logs |
| Latency giảm nhưng errors tăng | Fail-fast/fast error che tail | Latency successful vs failed riêng |
| HPA tăng replicas nhưng DB chậm hơn | Tổng pools vượt năng lực DB | Sum pool maxima, PostgreSQL connections |

Một giả thuyết chỉ được tin sau khi có **bằng chứng giữa các tầng**. Không tăng Tomcat threads lên 2.000 chỉ vì thấy latency tăng: nếu DB chỉ cho 16 connections, nhiều threads có thể khiến queue và memory tệ hơn.

### 14.4. K6 generator cũng phải được benchmark

K6 thực thi JavaScript assertions và tạo HTTP traffic. Nếu load generator CPU/network cạn, `dropped_iterations` hoặc kết quả latency có thể phản ánh **client test harness**, không phải server. Kiểm tra OS CPU, RAM, connection limits, NIC và DNS, so sánh khi chạy từ một host khác. Với production-like load lớn, dùng distributed load generation có quan sát tổng.

## 15. Phân biệt workload hợp lệ và thao tác gây tác dụng phụ

### 15.1. Test requests thành công chưa chắc business đúng

Những điều cần assert ngoài HTTP status:

- `GET product/{id}` trả **đúng ID**, không phải cached response của ID khác.
- Search trả array đúng category, sort và pagination.
- POST được ghi đúng **một event** theo request semantics.
- Không mất write dưới tải; row counts/WAL/storage phù hợp.
- Idempotency key nếu dùng payments/orders bảo vệ trước retries.
- Authz/tenant data isolation không bị phá dưới concurrency.
- 5xx/timeout/429 được xử lý theo contract.

Script lab đang check đơn giản (ID, JSON array, event ID); ứng dụng thật cần contract assertions sâu hơn, nhưng không làm mỗi VU parse payload rất lớn nếu làm thay đổi profile một cách không kiểm soát.

### 15.2. Không tạo dữ liệu bất hợp pháp

Test write-heavy nên dùng dữ liệu synthetic, đúng FK, validation và business rules. Nếu test tạo 500.000 event rows làm DB đầy, cần cleanup/retention. Nếu test order/payment/email thật, phải có sandbox idempotency rõ, tắt external side effects hoặc dùng downstream stubs hợp lệ và **không** gửi charge/email cho người thật.

### 15.3. Dữ liệu cố định và mutable

Cần phân biệt:

- Dataset tĩnh dùng cho GET/search: ổn định giữa các runs.
- Dữ liệu sinh bởi POST: tăng trong test; ảnh hưởng DB load.
- Cache state: warm/cold phải ghi lại.
- Tenant/user sessions: có thể đòi token/cookie lifecycle.
- Background cleanup/batch: có thể thay row counts trong test.

Nếu một lần test A đọc 200.000 rows và ghi 1.000 events, còn test B ghi 1 triệu events trước khi đo, hai phép thử **không cùng điều kiện ban đầu**.

## 16. Thiết kế báo cáo benchmark không đánh lạc hướng

Một báo cáo tối thiểu nên có:

```text
Benchmark name:
Code revision / Spring Boot / JDK:
Environment: pods/CPU/RAM/DB/network/region:
Data: row counts, size, skew, preloaded events:
Workload: GET detail/search/POST events = 80/15/5:
Arrival model: constant-arrival-rate:
Target iterations/s and expected HTTP RPS:
Achieved RPS and dropped iterations:
Warm-up / steady-state / peak / soak windows:
Per-operation sample count and p50/p95/p99:
HTTP error rate and failed business checks:
CPU, JVM heap/GC, Tomcat busy:
Hikari active/pending/max/timeout:
PostgreSQL CPU/IO/locks/query plans/WAL:
SLO pass/fail with exact thresholds:
Evidence: k6 summary, time series, logs/traces:
Limitations: topology mismatch, unmodeled cache/auth:
Decision: pass / capacity limit / investigate:
```

Đây là **mẫu các trường cần điền từ kết quả đo thật**, không phải số liệu benchmark đã thực hiện. Khi báo cáo cho stakeholder, cần phân biệt:

- **Configured target** vs **achieved throughput**.
- **Successful requests** vs **all attempted requests**.
- **Open-model target rate** vs **closed-model measured RPS**.
- **Percentiles per operation** vs tổng hợp.
- **Measured results** vs **estimations/mô phỏng toán học**.
- **Lab limits** vs production guarantees.

### 16.1. Cách đặt một kết luận phù hợp

Mẫu kết luận có điều kiện, **không được điền bằng số giả**:

> “Trong môi trường đã ghi cấu hình, với dataset X và workload Y, hệ thống đạt thông lượng Z trong cửa sổ steady-state T; p95/p99 và errors/drops thỏa hoặc không thỏa ngưỡng đã định. Bottleneck quan sát được liên quan ..., bằng chứng gồm .... Kết quả không trực tiếp áp dụng cho production nếu topology/data/network khác.”

Không dùng câu “Spring Boot chịu được 10.000 user đồng thời” chỉ vì k6 hiển thị 10.000 VUs trong một bài ngắn, khi chưa có số RPS, response time, errors và độ dài test.

## 17. Những sai lầm phổ biến cần tránh

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Dùng 1 bản ghi/1 SKU | Cache và index đều cực kỳ nhỏ | Dữ liệu đủ cardinality/width/skew |
| Chỉ đọc GET, bỏ writes | Không tạo locks/WAL/DB growth | Dùng read/write mix đúng |
| Random đều IDs | Bỏ hot-key skew | Weighted distribution/Zipf từ telemetry |
| Dùng H2 để kết luận PostgreSQL production | Khác optimizer, concurrency, WAL | Dùng engine/topology gần thật |
| Chỉ benchmark một endpoint | p95 tổng không đại diện checkout/search | Theo route/operation mix |
| “100 VUs = 100 RPS” | VUs là executors, không phải arrival rate | Báo target vs actual RPS |
| Closed model đo open arrival demand | Latency chậm làm RPS tự giảm | Chọn arrival-rate executor |
| Không xem dropped iterations | Tải mong muốn chưa phát đủ | Threshold drops và generator metrics |
| Thêm sleep trong arrival-rate iteration | Có thể làm VU thiếu/giảm target | Để executor pace, mô hình nghĩ ở closed/journey |
| Báo p95 tổng, bỏ p99/endpoint | Endpoint hiếm bị che | Thresholds per operation |
| Count lỗi nhưng bỏ correctness | 200 JSON sai vẫn được tính OK | Assertions body/business |
| Trộn warm-up vào kết quả steady | JIT/cache làm méo số đo | Phân tách stage/time windows |
| Chạy 30 giây rồi kết luận endurance | Chưa qua GC/DB maintenance/leaks | Soak đủ chu kỳ |
| K6 và SUT cùng laptop, không đo client | Generator contention | Host độc lập + metrics generator |
| So hai runs với dataset khác | Thay đổi card/size ảnh hưởng plans | Seed/reset có kiểm soát |
| Khi tăng VUs bị chậm liền tăng Tomcat threads | Có thể DB pool/CPU mới là nghẽn | Phối hợp Tomcat/Hikari/DB metrics |
| Chỉ nhìn CPU | Thread waits/IO không thể hiện | Thread dump, Hikari pending, DB wait |
| Dùng cache warm rồi kết luận cold-start | Không phản ánh restart/rollout | Chạy profile cold và warm riêng |
| Không kiểm tra 429/5xx | Latency nhanh do fast failures | Errors theo status và success-only latency |
| Tăng tải production/partner không xin phép | Gây downtime/quota billing | Test staging được phê duyệt |
| Đưa PII vào seed/k6 output | Rò dữ liệu | Synthetic/anonymized generator |
| Báo performance "đảm bảo" từ laptop | Môi trường không tương đương | Ghi giới hạn và revalidate production-like |
| Không pin image/version | Kết quả benchmark đổi âm thầm | Pin Boot/JDK/PG/image digest và artifact |
| Không lưu config/RPS/latency raw | Không tái lập hoặc điều tra được | Lưu artifacts/metrics/time series |

## 18. Bài tập thực hành

### Bài A — tăng dataset mà không đổi code

Thay `generate_series(1, 200000)` bằng `generate_series(1, 2000000)`, sửa check ID range trong controller và `PRODUCTS` trong k6. Giữ traffic mix và RPS. So sánh `EXPLAIN (ANALYZE, BUFFERS)`, p95 search, DB size, heap và Hikari. **Không** tự kết luận mọi query sẽ chậm hơn 10 lần: index/cache/optimizer có thể thay đổi phi tuyến.

### Bài B — thay hot-key skew

Chạy ba profile: 10% hot, 70% hot, 95% hot (giữ dataset, RPS, duration và random seed strategy tương đương). Đo cache hit, DB CPU, p95 point GET. Phân tích vì sao skew có thể giúp reads nhưng tăng contention nếu hot key bị update đồng thời.

### Bài C — closed vs open cùng điều kiện

Chạy 30 VUs có think time 1–3 giây, ghi achieved RPS. Sau đó chạy arrival-rate theo đúng RPS vừa đo. So p95/p99 và behavior khi tăng thời gian chờ giả lập ở backend. Giải thích tại sao closed RPS giảm khi server chậm còn open model cố giữ arrival rate.

### Bài D — tìm knee theo capacity

Chạy 20/40/60/80 RPS, giữ mỗi mức đủ lâu, ghi p95, p99, errors, dropped iterations, Hikari pending và CPU. Vẽ đường latency theo achieved RPS, tìm đoạn tăng mạnh. Không thêm load khi SUT đã bị lỗi vượt ngưỡng an toàn của môi trường.

### Bài E — tăng concurrency của DB pool

Giữ SUT/tải/dataset, thử Hikari max 8, 16, 24; đo wait time và DB CPU. Kết luận có điều kiện: tăng pool có thể giảm wait nhưng cũng có thể tăng DB contention. Không giả định pool lớn nhất luôn nhanh nhất.

### Bài F — soak có write growth

Chạy 1–2 giờ tại mức tải được phép, quan sát `visit_events` rows/index size, PostgreSQL WAL, autovacuum, p95 theo từng 5 phút. So heap sau GC và Hikari pending để tìm drift. Tránh nhầm table growth hợp lệ với memory leak.

### Bài G — sai lệch metric do HTTP 500 nhanh

Thay stub để 20% requests trả 500 ngay. Tính p95 gộp và p95 successful requests, error rate. Giải thích vì sao aggregate latency có thể trông thấp nhưng chất lượng dịch vụ tệ.

### Bài H — thời điểm bận batch

Chạy benchmark khi có batch maintenance hợp lệ (có phê duyệt) và khi không có, giữ workload khác giống nhau. So DB locks/IO, p99 spikes, CPU và queue. Nếu chỉ chạy vào ban đêm yên tĩnh thì không đại diện cho peak ban ngày.

## 19. Câu hỏi tự đánh giá

1. **Một bộ 10.000 dữ liệu random uniform đã đại diện production chưa?** Chưa; còn distribution, size, skew, read/write, indexes và cache.
2. **100 VUs có bằng 100 concurrent HTTP requests không?** Không. VU có thể ngủ, chờ hoặc tạo nhiều requests.
3. **100 VUs có tự tạo 100 RPS không?** Không; RPS phụ thuộc iteration duration và think time.
4. **Open model khác closed model ở đâu?** Open lên lịch arrival rate độc lập response; closed có actor/VU đợi trước iteration tiếp.
5. **`dropped_iterations` nghĩa gì?** Số iterations không được k6 khởi chạy theo lịch, có thể do VUs/generator không đủ hoặc SUT chậm.
6. **Nếu test target 100 RPS nhưng achieved 75 RPS, có thể kết luận pass 100 RPS không?** Không.
7. **Little's Law dùng p95 để tính concurrency được không?** Không; quan hệ stable-state dùng mean duration tương ứng.
8. **Vì sao cần warm-up?** JIT, connection pool, caches và database buffers cần đạt trạng thái phù hợp.
9. **Vì sao cần soak?** Tìm memory/pool leak, GC drift, DB growth/checkpoint và background effects.
10. **p95 tổng có thể che endpoint search chậm không?** Có, nếu search chiếm ít traffic.
11. **SUT CPU thấp nhưng latency cao có vô lý không?** Không, có thể đang chờ DB connections/locks/network.
12. **Spring Boot Actuator metrics đủ thay k6 không?** Không, server metrics không thay request arrival/correctness generator.
13. **K6 HTTP metrics đo browser render time không?** Không; cần browser/RUM nếu đo trải nghiệm người dùng.
14. **Hai runs khác kích thước dữ liệu có so sánh A/B sạch không?** Không.
15. **DB tăng pool từ 16 lên 64 có luôn tốt hơn không?** Không; có thể làm DB overload.
16. **HTTP 200 với wrong product ID có pass không?** Không, cần correctness assertion.
17. **POST event có thể retry vô điều kiện không?** Không, có nguy cơ duplicate.
18. **Có được chạy stress lên hệ thống đối tác public không xin phép không?** Không.
19. **Tại sao cần xem cả generator CPU?** Để phân biệt k6 bottleneck và SUT bottleneck.
20. **Điều kiện một kết luận benchmark đáng tin?** Workload/data/duration rõ, achieved load, errors/checks, p95/p99, server/DB metrics, repeats và giới hạn môi trường được ghi nhận.

## 20. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Actuator Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html): Micrometer Observation, metrics và tracing.
- [Spring Boot 3.5 — Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html): HTTP server metrics, DataSource/HikariCP, JVM metrics.
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): cấu hình Tomcat/threads và web runtime.
- [Spring Boot 3.5 — Data SQL/JdbcTemplate](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): datasource, JDBC và connection pool.
- [Grafana k6 — Executors](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/): các loại scenario executors.
- [Grafana k6 — Constant Arrival Rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/): open-model, rate/timeUnit/VUs.
- [Grafana k6 — Ramping Arrival Rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-arrival-rate/): thay đổi arrival rate theo stages.
- [Grafana k6 — Dropped Iterations](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/dropped-iterations/): tìm nguyên nhân không đạt target arrival.
- [Grafana k6 — Built-in Metrics](https://grafana.com/docs/k6/latest/using-k6/metrics/reference/): `http_req_duration`, `http_req_failed`, `http_reqs` và network timings.
- [Grafana k6 — Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/): kiểm định p95/p99/errors/drops.
- [Grafana k6 — Environment Variables](https://grafana.com/docs/k6/latest/using-k6/environment-variables/): `-e` và `__ENV`.
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_activity và thống kê runtime.
- [PostgreSQL — Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): execution plans và performance analysis.
- [PostgreSQL — Set Returning Functions](https://www.postgresql.org/docs/current/functions-srf.html): `generate_series` dùng seed data.
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): lifecycle/readiness ảnh hưởng traffic và scale.

**Kết luận:** Một phép đo tải Spring Boot có giá trị phải đồng thời đại diện cho **dữ liệu**, **tốc độ đến và mức đồng thời**, **thời gian chạy**, **tỷ lệ thao tác và tính đúng của kết quả**, đồng thời có metrics từ k6, JVM/Tomcat/HikariCP và PostgreSQL. Luôn công bố **target vs achieved**, p95/p99 theo operation, errors/dropped iterations, warm-up/steady-state/soak, dataset và giới hạn môi trường. Không biến một con số RPS cao trong lab thành lời hứa về production capacity khi chưa có workload và bằng chứng tương ứng.