# Ghi kết luận từ dữ liệu đo và phân biệt bằng chứng với suy đoán

*Java Advance – networking · Nhóm: Thực nghiệm mạng · Java 17+*

## 1. Một kết luận tốt phải nói được điều gì?

Trong thực nghiệm mạng, người học thường đo ping, latency HTTP, throughput, số lỗi hoặc tỷ lệ timeout rồi viết ngay: “bản mới nhanh hơn”, “mạng chậm”, “TCP mất gói”, “TLS gây trễ” hoặc “server chịu được 10.000 người dùng”. Những câu này **có thể là giả thuyết**, nhưng chưa trở thành kết luận chỉ vì có vài con số.

Một báo cáo đúng cần phân biệt:

1. **Quan sát (observation):** điều được đo/ghi lại trong điều kiện cụ thể, ví dụ “trong 12 lần thử với dataset minh họa, bản A có 10 lần status 200, một status 503, một timeout”.
2. **Bằng chứng (evidence):** quan sát kèm nguồn, công cụ, cách đo, thời gian, điều kiện, số mẫu, tính toàn vẹn và khả năng tái kiểm tra.
3. **Suy luận (inference):** điều ta suy ra từ bằng chứng, ví dụ “những lần hoàn tất của B có median thấp hơn A trong mẫu này”.
4. **Giả thuyết (hypothesis):** lời giải thích hoặc dự đoán cần thử, ví dụ “cấu hình connection reuse làm giảm thời gian hoàn tất HTTP”.
5. **Kết luận có giới hạn (bounded conclusion):** phát biểu được bằng chứng đỡ, **nêu rõ phạm vi và độ bất định**.
6. **Khuyến nghị/hành động (decision):** thay đổi hoặc phép đo tiếp theo dựa trên kết quả và rủi ro, không tự đồng nhất với sự thật đã được chứng minh.

**Quy tắc vàng:** “Đo được X” không mặc nhiên chứng minh “Y gây ra X”, “mọi môi trường đều có X” hoặc “X sẽ tiếp tục xảy ra ở tải khác”.

~~~text
Câu hỏi thực nghiệm
       |
       v
Giả thuyết + tiêu chí đo + kế hoạch thử
       |
       v
Ghi raw observations / metadata / lỗi
       |
       v
Làm sạch có kiểm soát + phân tích thống kê
       |
       v
Bằng chứng cụ thể (n, units, conditions, distributions)
       |
       v
So sánh với giả thuyết và khả năng giải thích khác
       |
       v
Kết luận có phạm vi + mức bất định + hạn chế
       |
       v
Quyết định / lần thử tiếp theo / kiểm chứng độc lập
~~~

Mục tiêu bài này không phải “khiến bảng số liệu trông thuyết phục”, mà là biến một phép đo networking thành **lập luận có thể kiểm tra, có thể bác bỏ và không gây hiểu nhầm**.

## 2. Bằng chứng khác suy đoán như thế nào?

| Loại phát biểu | Ví dụ về HTTP networking | Có thể khẳng định đến đâu? |
|---|---|---|
| **Dữ kiện đã ghi** | “Lần #17, GET /ping nhận HTTP 200 và 4 byte body.” | Mô tả đúng bản ghi và cách đo |
| **Số liệu tổng hợp** | “Trong 100 requests, 98 thành công, 2 timeout.” | Đúng với 100 phép thử đã ghi, nếu không bỏ mẫu |
| **So sánh quan sát** | “Median các phản hồi thành công của B là 13,5 ms, A là 14,5 ms.” | Chỉ trong mẫu và cách chọn success |
| **Giả thuyết** | “B nhanh hơn nhờ bật keep-alive.” | Cần thí nghiệm cô lập connection reuse |
| **Suy đoán thiếu dữ liệu** | “p95 giảm nên B chắc chắn tối ưu hơn ở production.” | Chưa đủ: khác tải, lỗi, mẫu nhỏ, confounders |
| **Phán đoán nguyên nhân** | “503 xảy ra vì ThreadPoolExecutor quá ít thread.” | Cần metrics/executor traces chứng minh nghẽn |
| **Dự đoán** | “B sẽ giữ p95 thấp ở 500 concurrent users.” | Cần load test đúng mức concurrency |
| **Kết luận có giới hạn** | “Trong 5 lượt chạy trên host thử nghiệm, B có median thấp hơn; chưa thấy bằng chứng đủ mạnh để quy cho cấu hình mới.” | Có bằng chứng và thừa nhận bất định |

### 2.1. Cách viết một câu kết luận có trách nhiệm

Thay vì:

> B nhanh hơn A 50% nhờ HTTP/2, nên đưa B lên production ngay.

Hãy viết:

> Trong cùng cấu hình tải 100 RPS, trên một host thử nghiệm, qua 5 lượt chạy độc lập, thời gian hoàn tất **của các request thành công** ở B có median thấp hơn A. Tuy vậy, phép thử chưa cô lập HTTP/2 khỏi connection pooling, tỷ lệ lỗi ở hai phiên bản còn khác nhau và chưa đo tải production. Kết quả hiện **ủng hộ giả thuyết B có latency thấp hơn trong điều kiện thử**, chưa xác nhận nguyên nhân hoặc độ lợi ở production.

Các con số “100 RPS, 5 lượt” trong mẫu câu **chỉ là cách soạn báo cáo**, không phải kết quả của chương trình Java trong bài.

### 2.2. Ba động từ nên dùng chính xác

- **“Quan sát thấy”**: khi nói về số liệu trực tiếp.
- **“Phù hợp với/ủng hộ giả thuyết”**: khi kết quả nhất quán với một giải thích nhưng còn alternatives.
- **“Chứng minh nguyên nhân”**: chỉ dùng rất thận trọng khi thiết kế thử nghiệm và loại trừ confounders thực sự đủ mạnh; với hoạt động thực tế có nhiễu, thường dùng “có bằng chứng nhân quả dưới các giả định ...”.

Không “lách” sự không chắc chắn bằng cách bỏ hoàn toàn phần điều kiện đo. Một kết quả chính xác đến 6 chữ số thập phân cũng có thể là **sai hướng kết luận**.

## 3. Bắt đầu từ câu hỏi có thể kiểm chứng

Một câu hỏi tốt chỉ rõ **đối tượng, phép đo, điều kiện so sánh và tiêu chí quyết định**.

| Câu hỏi mơ hồ | Câu hỏi có thể thử |
|---|---|
| “Server nhanh không?” | “Với 20 clients giữ 10 requests đồng thời mỗi client, HTTP GET 1 KiB có p95 end-to-end dưới 100 ms không?” |
| “HTTP/2 có tốt hơn HTTP/1.1?” | “Trên cùng host/path/TLS/payload, ở concurrency 50, p95 completion latency và request success rate khác thế nào?” |
| “Proxy gây chậm?” | “Giữ nguyên origin/payload/client, khi bật proxy thì connect phase và full-response latency thay đổi bao nhiêu?” |
| “DNS gây lỗi?” | “Trong các lần thử lỗi, có bao nhiêu lỗi `UnknownHostException` và bao nhiêu lỗi TCP connect?” |
| “Cache có hiệu quả?” | “Đối với hit/miss được dán nhãn, full-response bytes/s và elapsed time khác ra sao sau warmup?” |
| “Server có chịu 1.000 user?” | “Với traffic mix, session model và SLA xác định, hệ thống chịu được bao nhiêu RPS/concurrency trước khi p95 hoặc error rate vượt ngưỡng?” |

**Đừng bắt đầu với câu kết luận muốn viết rồi lựa chọn metric thuận ý.** Chọn hypotheses, metrics, sample size và quyết định phân tích **trước khi thấy kết quả**, nếu có thể.

## 4. Định nghĩa rõ metric: đang đo thời gian của việc gì?

Trong mạng, “latency” có rất nhiều nghĩa:

~~~text
Client starts operation
    |
    +-- DNS lookup (có thể dùng cache)
    +-- TCP connect (có thể reuse socket, nên bỏ qua)
    +-- TLS handshake (có thể session resume hoặc connection reuse)
    +-- write request bytes
    +-- network transit + server queue + server processing
    +-- receive HTTP response headers       <-- TTFB-like point
    +-- receive/decode full response body    <-- Full completion point
    |
Client operation complete
~~~

**TTFB (time to first byte)**, thời gian nhận headers và **thời gian nhận đủ body** không nhất thiết bằng nhau. Với streaming, server có thể gửi headers 200 sau 5 ms rồi mất 40 giây để gửi hết body. Nếu ghi “latency 5 ms” mà không ghi điểm kết thúc đo, kết luận vô nghĩa.

### 4.1. Bảng các metric thường gặp

| Metric | Định nghĩa cần ghi trong báo cáo | Cạm bẫy |
|---|---|---|
| TCP connect time | Từ trước thao tác connect đến khi TCP kết nối thành công, theo tool | DNS/proxy/TLS có nằm trong điểm đo không? |
| DNS resolve time | Thời gian tra cứu hostname | Cache và resolver policy có thay đổi? |
| TLS handshake time | Từ bắt đầu tới hoàn tất handshake TLS | Full handshake khác resumption |
| Headers latency | Từ bắt đầu operation tới khi nhận headers | Body có thể chưa về |
| Full-body latency | Từ trước gửi request tới khi body hoàn tất | Cần nêu body handler/stream consumption |
| RTT | Round-trip của gói/ping hoặc giao thức được chỉ rõ | ICMP ping không đại diện cho HTTP latency |
| Throughput | Tổng bytes/giây hoặc requests/giây | Byte nào, ở tầng nào, có tính retries? |
| Goodput | Payload hữu ích/giây | Không bằng TCP line rate |
| Error rate | Số attempts lỗi / toàn bộ attempts | Không xóa timeout/503 khỏi denominator |
| Timeout rate | Số attempts hết hạn / attempts | Timeout có thể khác limit ở server |
| Concurrency | Số operations đang hoạt động đồng thời | Không phải RPS |
| Tail latency | p95/p99 trên tập quan sát định nghĩa trước | Mẫu ít và filtering có thể làm sai lệch tail |

Trong `java.net.http.HttpClient`, `BodyHandlers.ofByteArray()` gom toàn bộ response body vào `byte[]` trước khi response hoàn tất. Với `BodyHandlers.ofInputStream()`, `HttpResponse<InputStream>` có thể được trả về **trước khi body đọc hết**. Thời gian quanh `send(...)` phải được mô tả theo **BodyHandler cụ thể**, không suy chung cho mọi loại body.

### 4.2. Độ phân giải và đồng hồ

Java `System.nanoTime()` cung cấp nguồn thời gian độ phân giải cao **chỉ nên dùng để tính elapsed time**, không phải đồng hồ thời gian thực/cross-process clock. Theo Java SE 17 Javadoc:

~~~java
long start = System.nanoTime();
// Thực hiện một operation cần đo.
long elapsedNs = System.nanoTime() - start;
double elapsedMs = elapsedNs / 1_000_000.0;
~~~

**Không dùng hai giá trị `nanoTime` thu thập từ hai JVM/máy khác nhau để tính trực tiếp network one-way latency.** Origin của nguồn thời gian là tùy ý. Số nanosecond của đơn vị API **không bảo đảm độ phân giải thực tới từng nanosecond**. Dùng `Instant.now()`/wall clock cho timestamp liên hệ thời điểm thực nghiệm; dùng `nanoTime()` *delta trong cùng JVM* cho duration.

Thêm rằng client-side timing bao gồm nhiều thành phần: scheduling, request construction nếu nằm trong điểm đo, queuing, DNS nếu chưa cache, TCP/TLS nếu chưa reuse, server time, network, đọc body và body handler. Nó **không tự cô lập thời gian server xử lý**.

## 5. p50, p95, p99, trung bình và độ biến thiên

Nếu có một danh sách latency của **successful responses**, có thể tính:

- **Mean**: tổng thời gian / số mẫu; nhạy với outlier.
- **Median (p50)**: điểm giữa phân phối sau khi sắp xếp; với n chẵn thường lấy trung bình của hai vị trí giữa.
- **p95/p99**: phân vị đuôi; cần nêu **cách tính** vì các thư viện dùng interpolation/rank khác nhau.
- **Min/max**: biên quan sát; max có thể do event hiếm, không thay cho p99.
- **Distribution/histogram**: biểu diễn tải/phân phối tốt hơn một con số duy nhất.
- **Error/timeout rates**: nên được báo cạnh latency, vì chỉ tính successful response gây survivor bias.

### 5.1. Ví dụ dữ liệu tổng hợp có chủ ý

Bộ dữ liệu **giả lập để học cách kết luận**, không được thu từ mạng thực:

~~~text
A (10 successes, ms): 10,11,12,13,14,15,16,17,18,100
B (10 successes, ms):  9,10,11,12,13,14,15,16,17,19

A: 12 attempts = 10 success + 1 HTTP 503 + 1 timeout
B: 12 attempts = 10 success + 2 HTTP 503 + 0 timeout
~~~

Nếu dùng **nearest-rank percentile** với rank = `ceil(p*n)` (xếp tăng dần, 1-based):

| Metric | A | B | Điều được phép nói |
|---|---:|---:|---|
| Attempts | 12 | 12 | Bằng số lần thử |
| HTTP 200 | 10 | 10 | 10/12 = 83,3% success |
| HTTP 503 | 1 | 2 | B có nhiều 503 hơn trong mẫu |
| Timeout | 1 | 0 | A có một timeout trong mẫu |
| Median success latency | 14,5 ms | 13,5 ms | B thấp hơn 1,0 ms ở successful samples |
| p95 nearest-rank success latency | 100 ms | 19 ms | B thấp hơn trong phép tính mẫu |
| Failure proportion | 2/12 | 2/12 | Cùng 16,7% attempts không thành công |

**Không được kết luận** “B giảm p95 81%, chắc chắn tốt hơn production”. Với 10 successful samples, p95 nearest-rank **chính là giá trị lớn nhất** (rank `ceil(0.95*10)=10`). Chỉ cần thay một outlier là p95 thay đổi rất lớn. Hơn nữa, B có hai HTTP 503, A có một 503 và một timeout: cơ chế lỗi khác nhau và latency của failures không được tính vào phân vị success.

### 5.2. Selection bias khi chỉ giữ request hoàn tất

Tình huống:

~~~text
A: 100 requests -> 80 succeeded (all fast), 20 timed out
B: 100 requests -> 99 succeeded (slower), 1 timed out
~~~

Nếu chỉ vẽ latency 80 successful requests ở A rồi nói “A nhanh hơn”, có thể vô tình **xóa 20 requests tệ nhất**. Phải báo `attempts, successes, HTTP errors, timeouts, cancellations` theo cùng denominator, bên cạnh latency thành công. Timeout là dữ liệu **censored** theo giới hạn phép thử: nó chứng tỏ không hoàn tất trước deadline, không cung cấp thời điểm hoàn tất thật.

**Không âm thầm thay timeouts bằng 0 ms**, cũng không tự gán chúng thành 1000 ms rồi gọi đó là observed latency. Nếu muốn “effective latency with failures” hoặc SLO violation, hãy định nghĩa metric riêng từ đầu và ghi rõ cách xử lý censored observations.

### 5.3. n nhỏ không đo được tail đáng tin

Để phân tích p99, 10 mẫu hiển nhiên không đủ; ngay cả 100 mẫu, nearest-rank p99 dựa vào gần cuối danh sách nên độ bất định có thể rất lớn. Trong traffic thực có burst/autocorrelation, “100 request liên tiếp” không giống 100 independent samples. Cần nhiều samples, **nhiều lượt chạy**, độ phủ các load levels và phân tích sai số phù hợp.

**Không có một số n thần kỳ** bảo đảm p95/p99 chính xác trong mọi hệ thống; kích thước mẫu còn phụ thuộc độ biến thiên, mức effect cần phát hiện, xác suất error, independence và yêu cầu confidence.

## 6. Phân biệt tương quan và nhân quả

Thấy B thấp latency hơn A chưa chứng minh **thay đổi duy nhất** trong B là nguyên nhân. Có nhiều biến gây nhiễu:

| Nhóm nhiễu | Ví dụ | Tác động tới nhận định |
|---|---|---|
| JVM warmup | JIT compile, class loading, GC | B chạy sau có thể được lợi từ trạng thái JVM |
| Caches | DNS cache, HTTP keep-alive, TLS session resumption, OS page cache | Request sau thường khác request đầu |
| Network | RTT, packet loss, congestion, route, proxy | Sự khác biệt đến từ đường mạng |
| Server state | Queue length, thread pool, DB connection pool | Request phải chờ downstream |
| Payload | Request/response byte size, JSON shape, compression | Khác lượng dữ liệu truyền |
| Protocol | HTTP/1.1 vs HTTP/2, keep-alive, redirect | Thay đổi nhiều yếu tố cùng lúc |
| Concurrency | 1, 10, 100 in-flight requests | Latency và error rate biến thiên theo tải |
| Resource limits | CPU throttling, memory, kernel socket buffers, open FDs | Tăng đuôi latency |
| Clock/instrumentation | Đồng hồ khác máy, điểm bắt đầu/kết thúc khác | So sánh sai metric |
| Environment | JDK patch level, OS, TLS settings, proxy config | Kết quả không cùng điều kiện |
| Order/time | A đo buổi sáng, B đo sau restart tối | Time-of-day confounding |
| Measurement overhead | Debug logs, JFR, packet capture bật ở một nhánh | Công cụ đo thay đổi performance |

Để tăng bằng chứng nhân quả:

1. **Chỉ đổi một biến chính** khi có thể, ví dụ bật/tắt keep-alive với cùng client JDK, endpoint, payload và tải.
2. **Chạy xen kẽ/randomize thứ tự**: A-B-B-A hoặc random blocks, không mặc định A tất cả rồi B tất cả.
3. **Warmup tương đương** và tách measurements trước/sau warmup; nếu cold-start là đối tượng nghiên cứu, đo riêng cold-start thay vì loại bỏ.
4. **Lặp theo nhiều khối thời gian và môi trường**, ghi run ID để không gộp nhầm independent runs với requests phụ thuộc nhau.
5. **Giữ và ghi failures**, tránh chỉ tính requests thành công.
6. **Dùng confidence intervals / phân tích uncertainty** nếu kết luận yêu cầu độ tin cậy thống kê; không biến một lần run thành bằng chứng phổ quát.

Không có ngẫu nhiên hóa/đối chứng hoàn hảo trong một số thử nghiệm production; khi đó phải nói rõ đây là **observational evidence**, không diễn đạt như controlled causal experiment.

## 7. Thiết kế một thí nghiệm mạng có thể lặp lại

Một kế hoạch thử nên được viết trước khi chạy. Mẫu:

| Thuộc tính kế hoạch | Cần ghi |
|---|---|
| Research question | So sánh gì? Ví dụ HTTP/1.1 với HTTP/2 ở tải cố định |
| H0 / H1 | H0: không có khác biệt trên metric đã chọn; H1: có thay đổi hướng xác định |
| Primary metric | Ví dụ p95 full-body latency trong successful requests |
| Reliability guardrail | Ví dụ `success_rate >= 99.9%` trong điều kiện tải đã mô tả |
| Secondary metrics | p50, p99, RPS, bytes/s, 4xx/5xx/timeouts |
| Load model | Open/closed loop, RPS, concurrency, ramp-up, duration |
| Payload/URL | Cùng URI template, body size, HTTP method, response expectations |
| Network scope | Loopback/LAN/WAN, DNS/proxy/TLS, geographic region |
| Environment | Host/CPU/memory, OS, JDK version, flags, container limits |
| Client settings | HttpClient version, pooling/reuse, timeouts, redirects |
| Server settings | Thread pools, executors, rate limits, data source |
| Warmup | Số requests/time và cách loại khỏi measured sample |
| Trial ordering | Randomized/interleaved/paired |
| Data capture | CSV/JSON schema, units, error categories, timestamps, run ID |
| Analysis plan | Percentile convention, confidence intervals, outlier policy |
| Decision threshold | Cải thiện tối thiểu có ý nghĩa và allowable error impact |
| Stop conditions | Quá tải, tăng errors, giới hạn tác động tới production |
| Security | Không ghi credentials/full tokens/raw private URLs |

Điều kiện có thể không hoàn toàn cố định; quan trọng là **ghi lại biến nào bị kiểm soát và biến nào chưa được kiểm soát**. Không khẳng định thí nghiệm “công bằng” chỉ vì cùng một laptop.

### 7.1. Open-loop và closed-loop load

- **Closed-loop**: một số virtual users/concurrent clients chờ response xong rồi mới phát request tiếp. Khi server chậm, **tốc độ phát request tự giảm**.
- **Open-loop**: requests được phát theo lịch/tốc độ đặt trước, không chờ request trước hoàn tất. Nếu tải vượt khả năng, **queue length và latency có thể tăng nhanh**.

Nếu đo hệ thống bằng closed-loop rồi tuyên bố “chịu được 1.000 RPS” mà test thực chất chỉ phát được 400 RPS dưới overload, kết luận không phản ánh nhu cầu đầu vào. Ghi rõ **offered load, achieved throughput, drop/error rate, concurrency và queueing**.

### 7.2. Các lần chạy độc lập và nhãn điều kiện

Mẫu nhật ký cấu hình:

~~~yaml
experiment_id: http-compare-2026-11-01
run_id: run-03
variant: candidate
environment: controlled-lab
network: loopback
java_version: "17"
http_version: "HTTP/1.1"
method: GET
route_template: /ping
request_body_bytes: 0
expected_response_bytes: 4
warmup_requests: 3
measured_requests: 5
timeout_ms: 3000
metric: elapsed_client_nanoTime_to_full_body
latency_unit: ns
analysis: descriptive_only
~~~

Đây là **mẫu schema minh họa**, không phải metadata tự động xuất từ demo và không chứng minh chính JVM đang chạy là Java 17 (demo đã được compile với `--release 17` nhưng runtime dùng phiên bản JDK thực tế). `java_version` nên lấy từ đúng môi trường đang chạy thay vì hardcode.

## 8. Cách ghi raw observations đủ để kiểm tra

Một record dữ liệu có thể có:

~~~csv
experiment_id,run_id,variant,iteration,phase,http_status,error_category,elapsed_ns,body_bytes
exp1,run01,A,1,measured,200,NONE,12000000,4
exp1,run01,A,2,measured,503,HTTP_503,18000000,4
exp1,run01,A,3,measured,,TIMEOUT,,0
~~~

Đây là **ví dụ tổng hợp, không phải CSV do chương trình dưới đây tạo ra**. Với timeout trước response, trường `http_status` và elapsed completion có thể để trống hoặc lưu **duration until timeout** trong field khác, không giả vờ biết server hoàn tất lúc nào. Nếu có status 503, ghi nó là **HTTP error response**, không gộp vào `IOException`.

Mỗi record nên có:

- Đơn vị cụ thể: `elapsed_ns` là nanoseconds, `elapsed_ms` là milliseconds; đừng trộn.
- Run ID, variant, iteration, warmup/measured phase.
- HTTP status **nếu có**, error class/category và nguyên nhân kết thúc.
- Message/body size và protocol/connection state nếu thực sự đo.
- Wall-clock timestamp có timezone để tương quan logs, nhưng duration đo bằng monotonic elapsed.
- Metadata môi trường/phiên bản và config **được lưu riêng hoặc liên kết bằng experiment ID**.
- Những requests thất bại, cancelled, timeout và interrupted vẫn nằm trong tập attempts.
- Không lưu raw secret, URI có token, cookies hoặc personal data.

**Data provenance:** lưu command, version/revision của chương trình đo, định nghĩa schema và phương pháp xử lý. Nếu file được chỉnh sửa/filter, ghi **các biến đổi** và giữ bản raw đã bảo vệ để audit; có thể thêm cryptographic checksum/hash để phát hiện sửa file ngoài ý muốn.

### 8.1. Log metric không phải packet trace

Một CSV do HTTP client ghi từ `System.nanoTime` là **evidence của client-observed duration**, không tự chỉ ra TCP retransmissions, packet loss hay DNS time. Muốn kết luận về packet loss/RTT/server queue, cần đo tương ứng bằng packet capture, socket metrics, server instrumentation hoặc distributed trace với clock boundaries được hiểu đúng.

**ICMP ping != TCP connect != HTTP full-body latency.** Không lấy một metric thay thế metric khác mà không giải thích mối liên hệ.

## 9. Java 17: chương trình thử nghiệm hoàn chỉnh

Ví dụ sau làm **hai việc tách biệt**:

1. Phân tích **dataset synthetic** A/B có 12 attempts mỗi bên, gồm HTTP 200, HTTP 503 và timeout. Nó in exact median và p95 theo công thức được nêu, nhưng **đây không phải benchmark thật**.
2. Tạo một HTTP server **loopback 127.0.0.1** bằng `jdk.httpserver`, dùng `HttpClient` của JDK 17 tạo 3 warmup requests (không tính vào dữ liệu) rồi đo **5 requests thực** bằng `System.nanoTime()`. `BodyHandlers.ofByteArray()` đảm bảo body đã được gom khi `send` trả về. Kết quả latency thực biến thiên, nên stdout mặc định chỉ báo tính hợp lệ và số mẫu; bật `--csv` để in những giá trị `elapsed_ns` thực tế, **không giả vờ có stdout latency cố định**.

**Giới hạn:** năm phép thử loopback chỉ kiểm tra pipeline đo, **không thể kết luận performance của production**, và dữ liệu synthetic chỉ minh họa cách phân tích/viết kết luận.

### 9.1. File EvidenceInferenceDemo.java

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class EvidenceInferenceDemo {
    record Trial(int status, double elapsedMs, boolean timeout) {}
    record Sample(int iteration, int status, long elapsedNs, int bodyBytes) {}

    static double median(List<Double> numbers) {
        List<Double> sorted = new ArrayList<>(numbers);
        sorted.sort(Double::compare);
        int n = sorted.size();
        if (n == 0) throw new IllegalArgumentException("No successes");
        return n % 2 == 0
                ? (sorted.get(n / 2 - 1) + sorted.get(n / 2)) / 2
                : sorted.get(n / 2);
    }

    static double nearestRank(List<Double> numbers, double probability) {
        List<Double> sorted = new ArrayList<>(numbers);
        sorted.sort(Double::compare);
        if (sorted.isEmpty() || probability <= 0 || probability > 1) {
            throw new IllegalArgumentException();
        }
        return sorted.get((int) Math.ceil(probability * sorted.size()) - 1);
    }

    static List<Trial> trials(double[] successes, int http503, int timeouts) {
        List<Trial> rows = new ArrayList<>();
        for (double millis : successes) rows.add(new Trial(200, millis, false));
        for (int n = 0; n < http503; n++) {
            rows.add(new Trial(503, 30, false));
        }
        for (int n = 0; n < timeouts; n++) {
            rows.add(new Trial(0, 200, true));
        }
        return rows;
    }

    static double printSummary(String name, List<Trial> rows) {
        List<Double> successes = new ArrayList<>();
        int http503 = 0, timeouts = 0;
        for (Trial row : rows) {
            if (row.status() == 200) successes.add(row.elapsedMs());
            if (row.status() == 503) http503++;
            if (row.timeout()) timeouts++;
        }
        double med = median(successes);
        double p95 = nearestRank(successes, 0.95);
        System.out.printf(Locale.ROOT,
                "%s attempts=%d ok=%d http503=%d timeouts=%d median_ms=%.1f p95_nearest_rank_ms=%.1f%n",
                name, rows.size(), successes.size(), http503, timeouts,
                med, p95);
        return med;
    }

    static List<Sample> measureLoopback() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/ping", exchange -> {
            byte[] reply = "PONG".getBytes(StandardCharsets.US_ASCII);
            exchange.sendResponseHeaders(200, reply.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(reply);
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/ping");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3)).build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(3)).GET().build();

            // Explicit warmup: does not enter the measured data set.
            for (int i = 0; i < 3; i++) {
                HttpResponse<byte[]> warmup = client.send(
                        request, HttpResponse.BodyHandlers.ofByteArray());
                if (warmup.statusCode() != 200) throw new IllegalStateException();
            }

            List<Sample> samples = new ArrayList<>();
            for (int i = 1; i <= 5; i++) {
                long start = System.nanoTime();
                HttpResponse<byte[]> response = client.send(
                        request, HttpResponse.BodyHandlers.ofByteArray());
                long elapsed = System.nanoTime() - start;
                samples.add(new Sample(i, response.statusCode(), elapsed,
                        response.body().length));
            }
            return samples;
        } finally {
            server.stop(0);
        }
    }

    public static void main(String[] args) throws Exception {
        List<Trial> baseline = trials(
                new double[]{10,11,12,13,14,15,16,17,18,100}, 1, 1);
        List<Trial> candidate = trials(
                new double[]{9,10,11,12,13,14,15,16,17,19}, 2, 0);
        System.out.println("dataset=synthetic_not_a_real_benchmark");
        double baseMedian = printSummary("baseline", baseline);
        double candMedian = printSummary("candidate", candidate);
        System.out.printf(Locale.ROOT,
                "observed_median_delta_ms=%.1f%n", candMedian - baseMedian);
        System.out.println("claim=descriptive_only_not_causal");

        List<Sample> measured = measureLoopback();
        System.out.println("loopback_samples=" + measured.size());
        System.out.println("loopback_all_status_200=" + measured.stream()
                .allMatch(s -> s.status() == 200));
        System.out.println("loopback_all_body_4=" + measured.stream()
                .allMatch(s -> s.bodyBytes() == 4));
        System.out.println("loopback_elapsed_positive=" + measured.stream()
                .allMatch(s -> s.elapsedNs() > 0));

        if (Arrays.asList(args).contains("--csv")) {
            System.out.println("iteration,status,elapsed_ns,body_bytes");
            for (Sample s : measured) {
                System.out.printf(Locale.ROOT, "%d,%d,%d,%d%n",
                        s.iteration(), s.status(), s.elapsedNs(), s.bodyBytes());
            }
        }
    }
}
~~~

### 9.2. Lệnh biên dịch và chạy

JDK 17 trở lên, không cần thư viện ngoài. `jdk.httpserver` là module chuẩn cung cấp local server:

~~~bash
javac --release 17 --add-modules jdk.httpserver EvidenceInferenceDemo.java
java --add-modules jdk.httpserver EvidenceInferenceDemo
~~~

**Stdout mặc định đã kiểm chứng với `javac --release 17` trên OpenJDK 24:**

~~~text
dataset=synthetic_not_a_real_benchmark
baseline attempts=12 ok=10 http503=1 timeouts=1 median_ms=14.5 p95_nearest_rank_ms=100.0
candidate attempts=12 ok=10 http503=2 timeouts=0 median_ms=13.5 p95_nearest_rank_ms=19.0
observed_median_delta_ms=-1.0
claim=descriptive_only_not_causal
loopback_samples=5
loopback_all_status_200=true
loopback_all_body_4=true
loopback_elapsed_positive=true
~~~

Với chế độ xuất **measured values thực**, chạy:

~~~bash
java --add-modules jdk.httpserver EvidenceInferenceDemo --csv
~~~

Sau các dòng mặc định, chương trình in:

~~~csv
iteration,status,elapsed_ns,body_bytes
~~~

rồi **năm dòng có elapsed_ns thay đổi theo lần chạy và máy**. Đây là dữ liệu đo thật từ loopback. **Không chép cố định năm con số stdout** hoặc tuyên bố những con số đó là kết quả benchmark ổn định. Chương trình đã được thử chạy chế độ `--csv` và nhận đúng năm records với `status=200`, `body_bytes=4`.

### 9.3. Vì sao hai nguồn dữ liệu không được nhập nhằng?

| Nguồn | Vai trò | Có thể kết luận |
|---|---|---|
| `baseline/candidate` hardcoded arrays | Dữ liệu **giả lập** để minh họa phân vị và lỗi | Phép tính/logic báo cáo đúng với mảng đã cho |
| `measureLoopback()` | Đo elapsed thật bằng `nanoTime` quanh `HttpClient.send` | Năm request loopback được ghi với status, body bytes, duration |
| Các dòng `loopback_all_...=true` | Kiểm tra integrity cơ bản của 5 samples | **Không** chứng minh p95 production hoặc HTTP/2/TLS performance |
| `--csv` | Xuất dữ liệu đo thật từng request | Có thể xem và phân tích run này; phải giữ metadata |

Một phép thử **toy** làm rõ pipeline không trở thành production benchmark chỉ vì đo bằng timer độ phân giải cao. Nó không tải nặng server, không có WAN latency, TLS, DNS lookup điển hình, packet loss, proxy hay distribution thực tế.

### 9.4. Đọc kết quả synthetic đúng cách

- B có median success latency 13,5 ms, A 14,5 ms. **Độ chênh quan sát là -1,0 ms**. Không biết đây là cải thiện thật hay nhiễu, vì dữ liệu được tạo thủ công.
- B có p95 nearest-rank 19 ms, A 100 ms. Vì chỉ có 10 successes mỗi bên, p95 là **max**, nên con số dễ gây ảo tưởng tail performance.
- Cả hai đều có 10/12 successful attempts. A có 1 timeout + 1 HTTP 503; B có 2 HTTP 503. Nếu chỉ xem success latency mà bỏ lỗi, có thể chọn nhầm phương án.
- Không thể khẳng định “B tối ưu hơn do keep-alive/HTTP2” vì **không hề có một thay đổi kỹ thuật A/B được triển khai và đo trong dataset synthetic**.
- Để có bằng chứng thật, cần chạy A/B trên cùng endpoint, cùng tải, đủ mẫu, xen kẽ có kiểm soát và ghi error/timeout categories.

## 10. Cách tính hiệu ứng và bất định

Một so sánh tốt không chỉ có “A=20, B=18”, mà xác định **effect size** và độ không chắc chắn.

### 10.1. Chênh lệch tuyệt đối và phần trăm

~~~text
absolute_difference = metric_B - metric_A
relative_change_pct = (metric_B - metric_A) / metric_A * 100%

Ví dụ synthetic median:
A = 14.5 ms
B = 13.5 ms
absolute = -1.0 ms
relative ≈ -6.9%
~~~

**Điều kiện:** phần trăm chỉ có ý nghĩa khi denominator hợp lý và metric định nghĩa nhất quán; nếu A gần 0, tỷ lệ phần trăm rất dễ gây hiểu lầm. Đặc biệt không tính “% nhanh hơn” từ p95 của **hai tập success bị filter khác nhau** rồi bỏ qua error rate.

### 10.2. Confidence interval không phải lời hứa

Có thể tính confidence interval cho mean, median, tỷ lệ lỗi hoặc effect phù hợp với thiết kế thống kê. Nhưng:

- Sampling procedure, independence và distribution assumptions quyết định phép tính có đáng tin hay không.
- Requests kế tiếp có thể tương quan theo cache, connection reuse, background load hoặc queue; bootstrap từng request như độc lập có thể đánh giá sai độ bất định.
- Với repeated experimental runs, có thể dùng **run-level summaries**, paired differences, hoặc resampling theo block/run khi appropriate.
- “95% CI” không có nghĩa “95% xác suất parameter cố định nằm trong interval đã nhận” theo cách diễn giải frequentist thông thường.
- Nếu quan sát rất ít failures, “không thấy lỗi” không đồng nghĩa true error rate bằng 0; cần upper bound/thử nhiều hơn.
- p99 từ rất ít sample không đáng tin dù code vẫn tính được một số.

Bài này không ép người học tự viết kiểm định thống kê khi chưa có dữ liệu đủ tốt. Trước hết cần **định nghĩa mẫu và quá trình lấy mẫu**.

### 10.3. P-value không thay cho effect size hay reproducibility

Một p-value nhỏ không đồng nghĩa thay đổi đủ lớn về mặt vận hành; một phép thử có p-value không nhỏ cũng không chứng minh hai phiên bản giống nhau. Với networking, hãy luôn nhìn thêm effect size, confidence interval, error budget, tail behavior, chi phí tài nguyên và khả năng lặp lại.

Đặc biệt **không thử 30 metrics, chọn metric “đẹp nhất”, rồi trình bày như primary metric đã định trước**. Nếu phân tích hậu nghiệm, gắn nhãn *exploratory* và yêu cầu một phép thử độc lập.

## 11. Cách phát biểu khi dữ liệu chống lại kỳ vọng

Nếu kỳ vọng B nhanh hơn mà data đo cho thấy B có nhiều 503 và tail latency cao, không nên “giải thích hộ” bằng cách loại outliers hoặc lấy một run thuận lợi.

Báo cáo tốt:

> Giả thuyết B giảm latency không được hỗ trợ bởi dữ liệu thu được trong test này. Có chênh lệch giữa các lượt chạy nhưng p95 và tỷ lệ lỗi chưa cải thiện nhất quán. Chúng tôi chưa xác định được nguyên nhân; cần kiểm tra queue saturation, GC và network path bằng instrumentation phù hợp.

Không viết:

> B vẫn tốt hơn vì máy thử nghiệm bị nhiễu.

Nếu nghi ngờ nhiễu, đó **là giả thuyết mới** cần test, không phải giấy phép phủ nhận observations.

### 11.1. Thiếu bằng chứng khác bằng chứng ngược lại

- **Không thấy khác biệt** trong mẫu nhỏ ≠ chứng minh hai bản tương đương.
- **Không thấy timeout** trong 10 lần thử ≠ hệ thống không bao giờ timeout.
- **Không thấy packet loss trong client logs** ≠ không có retransmission/loss ở TCP.
- **Không thấy SSLHandshakeException** ≠ mọi client đều tin certificate.
- **Một lần p95 giảm** ≠ protocol change gây cải thiện.

Khi câu hỏi vượt sức chứng minh, ghi **“chưa đủ bằng chứng để kết luận”** và chỉ ra phép thử cần bổ sung.

## 12. Các nhầm lẫn thường gặp trong Java networking

| Kết luận vội | Vì sao chưa đủ | Bằng chứng bổ sung cần |
|---|---|---|
| “TCP không mất gói vì HTTP 200.” | TCP có thể retransmit nhưng request vẫn thành công | TCP metrics/packet capture phù hợp |
| “TLS gây chậm vì HTTPS chậm hơn HTTP.” | TLS có thể khác origin, keep-alive, proxy, payload | Isolate handshake/reuse và các biến |
| “Server chậm vì getResponseCode mất 500 ms.” | Client timing có network, DNS, proxy, TLS, queue | Server-side spans/metrics được correlation |
| “HTTP/2 luôn nhanh hơn.” | Multiplexing có lợi/hại tùy tải/path và config | So sánh cùng điều kiện ở các load levels |
| “Latency p95 thấp hơn nên reliability cao hơn.” | Tail latency của successes có thể ẩn 503/timeouts | Success/error/timeout rates cùng denominator |
| “100% success nên không có lỗi.” | n nhỏ và traffic không đại diện | Nhiều runs/cases/loads, confidence bounds |
| “0 ms trên đồng hồ là request tức thời.” | Clock resolution/rounding | `nanoTime` delta và đơn vị đủ chi tiết |
| “JFR có GC pause nên GC gây mọi tail spikes.” | Chỉ là tương quan thời điểm | Correlate pause/runs, test dưới controlled GC |
| “B nhanh hơn vì runs B chạy sau.” | Warm caches/JIT chính là confounder | Order randomization, warmup control |
| “CPU thấp nên server không quá tải.” | Có thể bottleneck I/O, DB pool, locks | Queue length, blocked time, downstream |
| “Một TCP connection = một request.” | HTTP/2 multiplex streams | In-flight requests và stream metrics riêng |
| “Một request timeout là 3000 ms latency.” | Timeout là deadline/censoring, completion không quan sát | Ghi timeout category và waited duration riêng |
| “Tăng số samples tự động sửa mọi bias.” | Bias từ cách lấy mẫu không tự mất | Sampling design và instrumentation đúng |

## 13. Viết một báo cáo thực nghiệm có thể audit

Cấu trúc khuyến nghị theo thứ tự:

1. **Câu hỏi và phạm vi:** điều gì cần biết, tại sao.
2. **Giả thuyết/tiêu chí trước đo:** primary metric, expected effect, guardrails.
3. **Môi trường và cấu hình:** JDK/OS/hardware/network/proxy/TLS/HTTP version/load/payload.
4. **Phương pháp:** điểm start/end của timer, warmup, số runs/attempts, thứ tự variants.
5. **Kết quả quan sát:** raw IDs, số attempts, success/error/timeout, distribution, percentile convention.
6. **So sánh:** effect size, uncertainty, tính nhất quán qua runs.
7. **Hạn chế:** nhiễu chưa cô lập, sampling bias, data missing, missing client/server instrumentation.
8. **Kết luận có điều kiện:** câu phát biểu đúng phạm vi, không gán nguyên nhân khi chưa chứng minh.
9. **Quyết định/hành động:** triển khai, giữ nguyên, rollback hoặc thử thêm; nêu điều kiện kích hoạt.

### 13.1. Mẫu biên bản có thể dùng lại

~~~markdown
# Báo cáo: [Câu hỏi thực nghiệm]

## Phạm vi
Đối tượng, môi trường, phiên bản, thời điểm và traffic model.

## Giả thuyết trước đo
H0: ...
H1: ...
Primary metric và success/error guardrail: ...

## Phương pháp
Công cụ, điểm đo, warmup, n, order, timeout, protocol, payload,
CPU/memory/JDK/network conditions, cách xử lý missing samples.

## Bằng chứng
- Run IDs / data locations / checksum
- Tổng attempts, 2xx, 4xx, 5xx, timeout, cancel
- Latency p50/p95/p99 và định nghĩa success population
- Throughput/error rate và variation theo run
- Instrumentation logs/traces (đã loại thông tin nhạy cảm)

## Quan sát
Các số liệu đo được, kèm đơn vị, mẫu và điều kiện.

## Giải thích và giả thuyết thay thế
Điều gì phù hợp với dữ liệu; những confounders còn tồn tại.

## Kết luận có giới hạn
Chúng tôi quan sát ..., trong điều kiện ....
Chưa có bằng chứng để khẳng định ....
Mức độ tin cậy/hạn chế ....

## Quyết định và phép thử tiếp theo
Hành động, người phụ trách, điều kiện kiểm tra và rollback criteria.
~~~

**Đây là template để người học điền từ dữ liệu thực của họ**; không phải kết quả tự động được tạo bởi chương trình. Với một bài học Knowledge, không thay bằng chữ “đã chứng minh” nếu không có phép thử thực tế.

### 13.2. Ví dụ viết lại kết luận từ dữ liệu demo

**Không tốt:**

> B giảm p95 từ 100 xuống 19 ms, nhanh hơn 81%, đã chứng minh tối ưu cache thành công.

**Đúng phạm vi:**

> Trong **dataset synthetic** gồm 12 attempts mỗi variant (mỗi bên có 10 HTTP 200), median latency của successes là 14,5 ms ở A và 13,5 ms ở B; p95 nearest-rank lần lượt là 100 ms và 19 ms. A có một HTTP 503 và một timeout; B có hai HTTP 503. Đây là dữ liệu giả lập nên chỉ minh họa phép tính. Với n=10 successes, p95 nearest-rank bằng max và không đủ ổn định để suy diễn tail latency thực. **Không có bằng chứng từ dữ liệu này rằng thay đổi cache/HTTP/2 gây cải thiện performance.** Cần một thí nghiệm có kiểm soát với đủ mẫu, cùng tải và phân loại lỗi rõ ràng.

Câu đúng dài hơn nhưng giúp người đọc không hành động sai vì nhìn nhầm một metric.

## 14. Đưa ra quyết định dưới bất định

Không phải nghiên cứu nào cũng cần kết luận “A tốt hơn B”. Có ít nhất bốn nhóm kết quả hợp lý:

| Tình huống | Kết luận | Hành động |
|---|---|---|
| Effect nhất quán, guardrails đạt, phép thử đủ mạnh | Có bằng chứng ủng hộ thay đổi trong phạm vi đo | Canary/rollout có monitoring và rollback |
| Effect nhỏ hơn mức đáng quan tâm | Không thấy lợi ích vận hành rõ trong phạm vi thử | Giữ cấu hình hoặc tối ưu khu vực khác |
| Kết quả biến thiên, lỗi tăng hoặc dữ liệu thiếu | Chưa đủ bằng chứng quyết định | Lặp lại/thiết kế lại experiment |
| Reliability xấu đi rõ rệt dù latency successes giảm | Không chấp nhận đánh đổi theo guardrail | Ưu tiên sửa lỗi và kiểm chứng lại |

**Đừng “chọn metric đẹp nhất” để bỏ qua error budget.** Nếu p50 cải thiện nhưng 503 tăng, cần phân tích SLO mục tiêu và tác động người dùng trước khi khuyến nghị rollout.

### 14.1. Độ tin cậy của kết luận cũng có mức độ

Một cách báo cáo hữu ích:

- **Cao trong phạm vi thử:** metrics định nghĩa rõ, đủ nhiều independent runs, ít confounders, confidence intervals/guardrails ủng hộ.
- **Trung bình:** evidence nhất quán nhưng còn giới hạn về traffic mix hoặc duration.
- **Thấp:** chỉ một run, n ít, thiếu failure data, môi trường khác, không rõ method.
- **Không thể đánh giá:** không có raw records/provenance hoặc metrics bị mất nghĩa.

Đây là **thang mô tả nội bộ**, không phải một chuẩn thống kê phổ quát. Không tự chuyển sang xác suất 90%/99% nếu không có mô hình định lượng hợp lệ.

## 15. Gợi ý thí nghiệm tiếp theo sau kết quả demo

Sau khi hiểu kết quả synthetic và pipeline loopback, người học có thể thực hiện một phép thử thật (trên tài nguyên **được phép kiểm thử**, không dùng load test không được phê duyệt trên public APIs):

1. Chọn một thay đổi có thể bật/tắt, ví dụ dùng `HttpClient` reuse so với tạo client mới, **nhưng giữ mọi yếu tố khác nhất quán**.
2. Dùng một server local với payload cố định, chuyển từ 5 lần lên số mẫu đáng kể và chia thành nhiều runs.
3. Ghi từng attempt vào CSV: variant, run ID, timestamp, status, exception, elapsedNs và bodyBytes. Bảo vệ dữ liệu nhạy cảm.
4. Thử cả cold start và warm connection riêng; không gộp.
5. Randomize/interleave thứ tự A/B và đánh dấu run/phase.
6. So sánh median/tail latency **cùng với** success/error/timeout rates và queue/concurrency.
7. Sau loopback, nếu cần nghiên cứu mạng, thêm LAN/WAN với RTT/proxy/TLS được đo riêng.
8. Chỉ viết nguyên nhân khi có supporting instrumentation hoặc design đủ cô lập.

**Lưu ý quan trọng:** việc tạo `HttpClient` mới liên tục không phải một thực hành nên đem lên production chỉ để “tối ưu”; đó có thể là biến thí nghiệm, cần cleanup/lifecycle và cùng request semantics.

## 16. Các sai lầm thống kê và trình bày phổ biến

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Báo p95 mà không nêu n/method | Không so được và có thể là max của n nhỏ | Ghi population, n, percentile definition |
| Chỉ đo successful requests | Ẩn timeouts/503, selection bias | Báo attempts và failures đầy đủ |
| Lấy trung bình của p95 nhiều runs rồi gọi global p95 | Percentile không tuyến tính | Gộp raw samples có điều kiện hoặc báo per-run distribution |
| Dùng `System.currentTimeMillis()` đo đoạn rất ngắn | Độ phân giải/clock adjustment | Dùng `System.nanoTime()` delta |
| So đồng hồ từ hai máy không sync | One-way latency sai | Clock-sync/trace model hoặc đo client end-to-end |
| Thời điểm bắt đầu A và B khác nhau | Cache/JIT/cold-start confound | Quy định điểm đo thống nhất |
| Đo HTTP headers nhưng viết “download complete” | Body chưa tiêu thụ | Đo tới end of body |
| Không tính cancelled/timeout attempts | Denominator sai | Ghi terminal outcome mọi attempt |
| Lấy dữ liệu synthetic làm production evidence | Kết luận sai hoàn toàn | Gắn nhãn synthetic rõ ở dữ liệu và báo cáo |
| Xóa outliers vì “không đẹp” | Tail bị bóp méo | Chỉ loại theo rule đặt trước và báo cả raw |
| Dùng nhiều comparisons rồi chọn p-value nhỏ | False positives | Pre-register primary metric/adjust multiple testing |
| Suy từ một CPU profile ra nguyên nhân mạng | Có thể bottleneck bên ngoài JVM | Bổ sung network/server/queue metrics |
| Quên version/config/trafﬁc | Không thể tái hiện | Lưu experiment manifest |
| Dùng nhiều chữ số sau dấu phẩy | False precision | Độ chính xác tương ứng clock/sampling |
| Ghi kết luận quá chắc | Khuyến nghị sai/khó kiểm toán | Bounded claims, alternatives, uncertainties |
| Ghi raw credentials trong logs/CSV | Rủi ro bảo mật | Route templates, redaction, synthetic accounts |

### 16.1. Percentile không cộng/trung bình tùy ý

Nếu run 1 có 10 samples và run 2 có 10.000 samples, lấy trung bình `(p95_run1+p95_run2)/2` cho mỗi run trọng số ngang nhau **không bằng p95 của 10.010 observations**. Khi cần global distribution, tính từ raw samples theo plan, hoặc phân tích run-level variability riêng. Nếu các runs có tải khác nhau, cũng không gộp âm thầm.

### 16.2. False precision khi ghi đơn vị

Một tool in latency `0.783219 ms` không có nghĩa kết luận phải chính xác đến sáu chữ số lẻ. Timer precision, scheduling và network noise có thể lớn hơn rất nhiều. Nên ghi đủ precision cho analysis, nhưng trình bày kết luận với độ chính xác hợp lý và CI/variability.

## 17. Checklist trước khi ký một kết luận networking

**Định nghĩa phép đo**

- [ ] Câu hỏi, hypothesis, primary metric và guardrails được ghi trước khi xem data.
- [ ] Latency là connect, headers, first byte hay full-body? Cùng đơn vị?
- [ ] Dùng `nanoTime` delta trong cùng JVM, không trộn clocks giữa hosts.
- [ ] Có phân biệt HTTP status với transport exception và timeout?
- [ ] Có đo đúng protocol/version/payload/traffic model dự kiến?

**Tính đầy đủ và so sánh**

- [ ] Attempts, successes, 4xx/5xx, timeouts, cancels và dropped requests có đủ?
- [ ] Không bỏ outlier/failed requests tùy tiện.
- [ ] n, number of runs, warmup, concurrency và order được ghi.
- [ ] Có kiểm tra cache/JIT/GC/proxy/TLS/DNS/OS confounders?
- [ ] Percentile method và dataset population rõ ràng.
- [ ] Confidence interval/uncertainty phù hợp với cách lấy mẫu.

**Kết luận và hành động**

- [ ] Từng claim chỉ dựa vào quan sát trong phạm vi có dữ liệu.
- [ ] Có nêu giả thuyết thay thế và những điều chưa đủ bằng chứng.
- [ ] Không suy nhân quả chỉ vì A/B khác số.
- [ ] Có effect size, guardrail, ngưỡng rollout/rollback khi cần.
- [ ] Có hướng thử nghiệm tiếp theo và cách tái hiện.
- [ ] Không đưa token, URI nhạy cảm hoặc thông tin cá nhân vào raw observations.

## 18. Câu hỏi tự kiểm tra

**1. “HTTP GET trả status 200 trong 5 request loopback” là bằng chứng của điều gì?** Là bằng chứng 5 requests cụ thể đã nhận status 200 trong test đó; không chứng minh production luôn thành công.

**2. “B có p95 thấp hơn A” có chứng minh B gây cải thiện?** Không. Cần thiết kế kiểm soát confounders, nhiều mẫu và phân tích uncertainty.

**3. Vì sao phải ghi n cùng p95/p99?** Vì tail percentiles trên n nhỏ cực kỳ không ổn định.

**4. n=10 dùng nearest-rank p95 thì lấy phần tử thứ mấy?** Thứ 10, tức max.

**5. Median thành công của A trong dữ liệu demo là bao nhiêu?** 14,5 ms.

**6. Median thành công của B trong dữ liệu demo là bao nhiêu?** 13,5 ms.

**7. Hai phương án có cùng tỷ lệ thành công không?** Trong dataset synthetic, đều 10/12; nhưng loại lỗi khác nhau.

**8. Vì sao timeout không nên xóa khỏi attempts?** Vì làm success rate và phân tích survivorship bias sai.

**9. `getResponseCode` mất 100 ms có nghĩa server xử lý 100 ms?** Không; thời gian phía client có network/proxy/TLS/queue và điểm đo.

**10. Vì sao `nanoTime` không dùng để đo one-way latency giữa hai JVM?** Origin của nguồn clock khác nhau, không có wall-clock synchronization.

**11. `BodyHandlers.ofInputStream()` có thể khiến send xong trước khi body đọc hết?** Có; phải đo tới EOF/close nếu mục tiêu là full-body time.

**12. Demo có dùng HTTP/2 hay TLS không?** Không, ép HTTP/1.1 trên loopback và không có HTTPS.

**13. Dòng `dataset=synthetic_not_a_real_benchmark` bảo vệ người đọc khỏi ngộ nhận gì?** Nó khẳng định A/B numbers không được đo từ server thật.

**14. Cờ `--csv` dùng để làm gì?** Xuất năm elapsed_ns measurements thực từ loopback, giá trị thay đổi mỗi lần chạy.

**15. Khi A chạy trước và B chạy sau, nhiễu nào thường gặp?** JIT warmup, caches, connection reuse, background load.

**16. Có thể lấy trung bình các p95 per-run rồi gọi là global p95?** Không, phân vị không cộng tuyến tính.

**17. Một confidence interval tự động loại bỏ sampling bias?** Không, phải phù hợp với thiết kế lấy mẫu và independence.

**18. Không thấy 503 trong 20 requests nghĩa server không bao giờ trả 503?** Không; chỉ chưa quan sát trong mẫu đó.

**19. Nên làm gì nếu dữ liệu không hỗ trợ giả thuyết ban đầu?** Ghi rõ, xem alternatives và lên kế hoạch thử bổ sung, không bỏ dữ liệu bất lợi.

**20. Kết luận tốt cần có gì?** Claim, số liệu và phạm vi, điều kiện, cách đo, uncertainty, hạn chế và bước tiếp theo.

## 19. Tài liệu chính thức và hướng học thêm

- [Java SE 17 – System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): duration trong một JVM; nanosecond precision khác nanosecond resolution.
- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, client reuse, HTTP version và body handling.
- [Java SE 17 – HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofByteArray` vs `ofInputStream` và thời điểm body hoàn tất.
- [Java SE 17 – HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request timeout, methods và URI.
- [Java SE 17 – HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): tạo local HTTP server để kiểm thử.
- [Java SE 17 – HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): response status/body và closing.
- [Java SE 17 – Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder.html): công cụ thu thập runtime events khi cần quan sát JVM sâu hơn.
- [OpenJDK JMH](https://github.com/openjdk/jmh): harness benchmark Java micro/macro phù hợp với JVM behavior; **microbenchmark không thay thế** end-to-end networking load test.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): status codes và HTTP request/response semantics.
- [RFC 9113 – HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): streams và multiplexing; lưu ý số TCP connections không đồng nghĩa số requests.

**Ghi nhớ:** Một biểu đồ chỉ trở thành bằng chứng khi biết **đo cái gì, đo như thế nào, mẫu gồm những gì và điều kiện ra sao**. Viết rõ observations, hypotheses, effect sizes, failure rates, uncertainties và alternative explanations. Kết luận networking tốt thường có giới hạn: **“Trong điều kiện X, chúng tôi quan sát Y; điều đó ủng hộ/không ủng hộ Z; chưa thể khẳng định W; phép thử tiếp theo là Q.”**
