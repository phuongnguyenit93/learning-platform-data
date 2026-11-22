# Xây dựng tải đại diện và mục tiêu p95, p99 khi đo lường GC trong Java 15+

## 1. Vì sao “GC pause thấp” chưa đủ để đánh giá một ứng dụng?

Khi tối ưu JVM, một dashboard có thể cho thấy **GC stop-the-world pause tối đa chỉ vài mili giây**, trong khi người dùng vẫn gặp **p95 hoặc p99 request latency** cao. Đây không phải mâu thuẫn: hai phép đo mô tả **hai tập sự kiện khác nhau**.

- **Request latency** đo khoảng thời gian một yêu cầu hoàn tất ở **ranh giới đã quy định**: từ client/edge/service ingress tới response completion.
- **GC pause duration** đo thời gian JVM **tạm dừng các luồng ứng dụng** trong một pha stop-the-world.
- **GC cycle duration** có thể bao gồm nhiều công việc diễn ra **concurrent** với ứng dụng; không được đồng nhất toàn bộ cycle với pause.
- **p95/p99** là các vị trí trong **phân phối mẫu** (request hoặc GC pause events); không phải giá trị tối đa hay deadline cứng.

**Tải đại diện (representative workload)** là một mô hình tải phản ánh tương đối trung thực loại request, kích thước payload, số lượng người dùng đồng thời, tần suất cấp phát object, tỷ lệ object sống lâu, cache/DB/RPC, burst và sự bão hòa tài nguyên của hệ thống thực.

**Mục tiêu p95/p99** của một dịch vụ phải bám vào nhu cầu người dùng và **service-level objectives (SLOs)**, ví dụ **95% request ≤50 ms** và **99% request ≤100 ms** trong một cửa sổ đã định nghĩa. Các ngưỡng 50 và 100 ms ở bài này **chỉ là ví dụ**, không phải thông số mặc định do Java, G1, ZGC hoặc Shenandoah bảo đảm.

**Phạm vi phiên bản:** các cách đo như `System.nanoTime()`, Unified Logging `-Xlog`, Java Flight Recorder và histogram/SLO vẫn phù hợp từ Java 15 đến **JDK hiện hành**. Tránh sử dụng các cờ GC logging hoặc collector mode đã lỗi thời.

## 2. Xác định ranh giới SLI trước khi chọn benchmark

Một giao dịch HTTP điển hình:

~~~text
Client ─► Load Balancer ─► Queue ─► Java handler ─► DB / RPC
   ▲                                             │
   └────────── Response ◄──── Serialization ◄─────┘

Có thể chậm do:
network, proxy, queue wait, CPU, lock, memory pressure,
GC pause, allocation stall, database, retry, timeout...
~~~

Nếu chỉ đo tại đầu/cuối handler Java, ta có thể **bỏ sót hàng đợi tại proxy hoặc executor trước handler**. Nếu SLO đo thời gian client nhìn thấy, cần tính cả những khoảng liên quan ở phía client/edge/network.

| SLI hoặc metric | Ranh giới đo | Vì sao cần? |
| --- | --- | --- |
| `client_round_trip_ms` | Client gửi tới nhận kết quả | Gần trải nghiệm người dùng |
| `edge_request_ms` | Edge nhận tới trả response | Có thể chứa proxy/queue |
| `service_request_ms` | Ingress service tới completion | Hữu ích cho service SLO |
| `worker_queue_wait_ms` | Được nhận vào queue tới được xử lý | Nhận diện saturation |
| `downstream_call_ms` | Gọi DB/RPC tới hoàn tất | Tách phụ thuộc |
| `gc_stw_pause_ms` | Bắt đầu tới kết thúc một GC pause | Chỉ số JVM, **khác request** |
| `gc_cycle_ms` | Chu kỳ GC, gồm concurrent work | Không coi là tổng STW |

**Không được cộng thêm một GC pause vào các span request nếu các span ấy đã bao gồm thời gian bị dừng**: sẽ đếm trùng. Với các RPC song song, tổng duration của mọi span có thể lớn hơn thời gian end-to-end thực tế vì chúng chồng lấp.

Khi định nghĩa SLI, phải nêu: **điểm bắt đầu/kết thúc, loại request, trạng thái request nào được tính, cách xử lý lỗi/timeout, đơn vị và cửa sổ đo**. Đây là điều kiện để so các bản GC/JDK công bằng.

## 3. p95, p99 và ngân sách của những request chậm

Với `N` giá trị latency được sắp xếp tăng dần, quy tắc **nearest-rank** đơn giản định nghĩa vị trí của percentile `p` là `ceil(p × N)`, chỉ số từ 1:

~~~text
N = 1000 request đã sắp xếp:
p50 = x[500]
p95 = x[950]
p99 = x[990]
p99.9 = x[999]
max = x[1000]
~~~

Nhiều hệ thống observability dùng histogram và **nội suy quantile**, nên giá trị ước lượng có thể khác một phép nearest-rank trên dữ liệu raw. Không coi chênh lệch nhỏ là lỗi nếu phương pháp và bucket khác nhau.

### Hai SLO minh họa

| Mục tiêu | Trong 1.000 request phải có tối thiểu | Được vượt ngưỡng tối đa |
| --- | ---: | ---: |
| **95% hoàn tất ≤50 ms** | 950 | 50 request >50 ms |
| **99% hoàn tất ≤100 ms** | 990 | 10 request >100 ms |

Cùng một request 250 ms **vượt cả hai ngưỡng**. **Không cộng ngân sách 50 + 10 để tuyên bố có thể có 60 request chậm độc lập**. Nếu có availability SLO, error-budget cho availability là một định nghĩa khác; không tùy tiện bỏ request lỗi/timeout ra khỏi latency denominator.

**Không chọn SLO chỉ bằng cách sao chép p99 hiện tại.** Cần tham khảo kỳ vọng người dùng, độ nhạy của workflow, trải nghiệm ở phía client, mức tác động business và khả năng cung cấp dịch vụ. Ví dụ việc tạo báo cáo lớn có thể có SLO khác API đọc tương tác.

### Ngưỡng percentile không phải max

Giả sử p99 request = 60 ms, vẫn có thể tồn tại request mất 500 ms; chúng nằm ở phần 1% chậm nhất hoặc ở giá trị `max`. Bởi vậy nên quan sát **p50/p95/p99**, max, request count, lỗi, timeout và tần suất các outlier; không chỉ một con số percentile.

**Cỡ mẫu quan trọng:** p99.9 trên 50 request rất thiếu độ phân giải. Mỗi dashboard phải thể hiện số mẫu và time window. Một p99 tính từ vài request trong một phút không đáng được đối xử như một chỉ số tail có ý nghĩa thống kê cao.

## 4. Xây request mix đại diện từ thông tin production

Trước khi đo, thu dữ liệu đã được phép từ metrics/logs/traces:

| Thuộc tính | Cách lấy hoặc mô phỏng có cơ sở | Rủi ro nếu bỏ qua |
| --- | --- | --- |
| **Request types** | Tỷ lệ read/write/search/export/heavy | Benchmark toàn fast path |
| **Payload size** | Phân phối p50/p95/p99 của input/output bytes | Không đo trường hợp payload lớn |
| **Arrival rate** | RPS trung bình/đỉnh, giờ cao điểm, burst | Không thấy hàng đợi và saturation |
| **Concurrency** | Active requests, worker count, connection pools | Nhầm tải thấp với tải thật |
| **Cache hit ratio** | Cache hit/miss và kích thước dữ liệu | Ảo tưởng về CPU/DB latency |
| **Downstream** | DB/RPC latency, retry/timeout, connection pool | Đổ lỗi sai cho GC |
| **Allocation rate** | Bytes/request, bytes/second, object churn | GC hoạt động không giống production |
| **Live set / object age** | Heap occupancy, cache/session retention | Không phát hiện áp lực old generation |
| **CPU/memory limits** | CPU quota, heap size, container RSS, cores | Collector có trade-off khác trên host khác |
| **Failures** | Error rate, timeout, cancel, reject | Tail đẹp giả khi request lỗi bị bỏ |
| **User populations** | Tier/endpoint/tenant group có số lượng đủ | Gộp che những route quan trọng |

**Ví dụ request mix để học** (không phải tỷ lệ từ một ứng dụng có thật): 80% read, 15% write, 4% heavy, 0,9% slow dependency và 0,1% outlier. Mix phải được thay bằng dữ liệu thực tế trước khi dùng làm kết luận production.

Không nên chỉ chạy `new byte[1024]` liên tục rồi gọi đó là bài test representative: tỷ lệ object sống lâu, tham chiếu, allocation rate và hoạt động ngoại vi có thể hoàn toàn khác ứng dụng.

### Phải có nhiều phân bố, không chỉ giá trị trung bình

Nếu 99% payload dài 1 KiB, 1% dài 5 MiB, benchmark chỉ dùng “payload trung bình” có thể **không kích hoạt đường xử lý những payload lớn**. Tương tự với DB latency, allocation rate và batch size.

Nên giữ đủ **đường đi hiếm nhưng có tác động**, ví dụ endpoint thanh toán, export hoặc request có cache miss. Tuy nhiên, đừng cho workload dồn quá nhiều vào các tình huống cực hiếm nếu production không có tỷ lệ đó; điều ấy khiến kết quả không đại diện.

## 5. Các phase kiểm thử cần có

Một benchmark có ý nghĩa thường tách:

1. **Startup/warm-up:** JVM class loading, JIT compilation, cache/connection pools, live set bắt đầu hình thành.
2. **Steady-state:** tốc độ đến và request mix bình thường; quan sát GC cycle, allocation rate và latency khi các chỉ số ổn định.
3. **Expected peak:** lưu lượng cao dự kiến theo traffic profile.
4. **Burst/spike:** tải tăng nhanh, dùng để kiểm tra queue backlog, backpressure và p99.
5. **Soak:** chạy đủ lâu để phát hiện live-set growth, memory leak, promotion, fragmentation và GC pressure.
6. **Recovery:** sau spike giảm tải, quan sát queue, GC CPU, latency và error rate có trở lại bình thường không.
7. **Dependency degradation** (trong môi trường được phép): mô phỏng DB/RPC chậm hoặc timeout để xem failure mode có làm queue tăng không.

**Không có thời gian warm-up/soak cố định cho mọi ứng dụng.** Phải xác nhận metric đã ổn định, GC thật sự xảy ra đủ số lần, caches đã gần mức sử dụng dự kiến và thời lượng đã đủ để thu mẫu p99 đáng tin.

Nếu SLO bao gồm request cold-start, đo startup **riêng** thay vì che đi bằng cách loại warm-up vô điều kiện; nếu SLO là steady-state, có thể tách dữ liệu warm-up khỏi giai đoạn đánh giá chính, nhưng vẫn phải báo nó.

## 6. Open-loop, closed-loop và hiện tượng coordinated omission

### Closed-loop

~~~text
gửi request A → đợi A xong → gửi request B → đợi B xong → ...
~~~

Khi server chậm, generator cũng gửi ít request hơn. Vì thế nó có thể **che đi thời gian những request đáng lẽ đến lúc server đang nghẽn**. Đây là một hình thức thường gặp của **coordinated omission**.

### Open-loop

~~~text
arrival schedule độc lập với thời gian hoàn tất
  t0      t1      t2      t3      t4
  request request request request request
  (một request chưa xong không tự trì hoãn arrival tiếp theo)
~~~

Open-loop thường thích hợp để đo hệ thống có nhiều nguồn gửi request độc lập, nhưng phải kiểm soát **max in-flight requests**, queue và rejected work để không phá hủy môi trường thử. Không phải mọi ứng dụng đều bắt buộc dùng fixed interval; có thể dùng arrival distribution thực tế/Poisson/burst đã thu.

**Phải báo đủ:**

- `offered RPS`: số request được định đưa vào service mỗi giây.
- `completed RPS`: số request hoàn tất mỗi giây.
- `in-flight / queue depth` và thời gian chờ.
- `rejected / dropped / timeout / cancelled`.
- `scheduled arrival vs actual submission` để phát hiện chính generator bị chậm.

Nếu offered RPS tăng nhưng completed RPS giữ nguyên, queue tăng và p99 xấu, đừng chỉ nhìn throughput hoàn tất rồi nói server ổn. Tài nguyên giới hạn hoặc một pause ngắn đúng lúc gần bão hòa có thể tạo hậu quả queue kéo dài.

Một ý tưởng scheduler (pseudocode, **không phải load generator hoàn chỉnh**):

~~~text
nextArrival = monotonicNow()
for mỗi yêu cầu dự kiến:
    nextArrival += plannedInterArrival
    đợi đến nextArrival nếu chưa tới
    nếu đạt giới hạn in-flight: ghi nhận rejection rõ ràng
    ngược lại: submit không đợi request trước hoàn thành
    record scheduledTime, sendTime, completionTime, status
~~~

Nguyên tắc là **không âm thầm bỏ các arrival bị trễ**, và không cho bộ sinh tải trở thành bottleneck. Không nên mặc định kết quả của closed-loop phản ánh latency dưới một arrival rate cố định.

## 7. SLO phải được phân nhóm theo đường đi nghiệp vụ

Nếu API đọc cache trả 10 ms nhưng export báo cáo hợp lệ cần vài giây, histogram chung có thể vô nghĩa đối với cả hai nhóm.

Nên nhóm các operation với kỳ vọng tương đồng:

- Interactive read/search.
- Writes hoặc giao dịch có yêu cầu durability.
- Streaming/batch/export với SLO riêng.
- Những endpoint có kích thước payload hoặc dependency khác biệt đáng kể.
- Customer tier hoặc khu vực nếu cần và đủ số mẫu.

**Không đặt label raw user ID, request ID, session ID hay URL đầy đủ** trên histogram, vì cardinality cao và có thể làm lộ thông tin. Dùng route template/operation class và label set có kiểm soát.

Ví dụ SLO:

~~~text
SLI: service ingress → response completion
Population: interactive API requests
SLO window: rolling 28 days
Objective A: ≥95% requests ≤50 ms
Objective B: ≥99% requests ≤100 ms
Failures/timeouts: được tính theo quy ước SLI, không tự loại
Other route classes: có SLO riêng nếu nhu cầu khác
~~~

Thời gian rolling 28 ngày cũng chỉ là ví dụ. Dashboard 5 phút giúp điều tra spike, **không đồng nghĩa** một bucket p99 5 phút luôn quyết định kết quả SLO 28 ngày.

## 8. Phân biệt p95/p99 request với p95/p99 GC pause

| Phân phối | Mỗi mẫu là gì? | Cách thu |
| --- | --- | --- |
| `request_latency_ms` | Một request, theo boundary SLO | Application/edge histogram/tracing |
| `gc_stw_pause_ms` | Một GC stop-the-world pause event | JVM GC log / JFR `jdk.GCPhasePause` |
| `gc_cycle_duration_ms` | Một toàn chu kỳ GC (có thể concurrent) | GC logs/JFR |
| `queue_wait_ms` | Một request chờ queue | Worker/executor/ingress instrumentation |

Giả sử GC có 100 pauses với 90 event dài 2 ms, 9 event dài 6 ms và 1 event dài 12 ms. Khi đó **GC pause p95 = 6 ms, p99 = 6 ms, max = 12 ms** theo nearest-rank.

Điều này **không nói** request p95 hoặc p99 bằng những giá trị đó. Một request có thể mất 140 ms do DB ngay cả khi JVM chỉ pause 6 ms. Nếu JVM đang bão hòa, một pause ngắn có thể góp phần tạo backlog kéo dài **hơn pause**.

**Không suy quan hệ nhân quả chỉ từ việc hai đồ thị tăng cùng lúc.** Cần timeline GC, request traces, queue depth, CPU, allocation stalls, cùng instance/pod và cửa sổ tương ứng.

### `-XX:MaxGCPauseMillis` không phải request SLO

Với G1:

~~~bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=100 -jar app.jar
~~~

`MaxGCPauseMillis` là **mục tiêu mềm của GC ergonomics**, không phải bảo đảm cứng mọi pause ≤100 ms, cũng không phải ngưỡng cho `request p99`. Những con số chính phải được **đo** từ ứng dụng và JVM.

## 9. Chuẩn bị môi trường so sánh collector

Trước khi kết luận G1, ZGC hoặc Shenandoah tốt hơn:

1. Ghi `java -version`, vendor/build, OS, CPU architecture và container/cgroup.
2. Cố định request mix, payloads, offered load, cache state và downstream behavior.
3. Giữ tương đương heap `-Xms/-Xmx`, CPU quota và memory limit nếu chỉ thay collector.
4. Thu số liệu GC STW pauses, GC CPU/cycles, allocation rate, live set, stalls và OOM.
5. Có warm-up đủ, nhiều lần chạy/forks khi phù hợp, và thống kê độ biến thiên.
6. Kiểm tra offered/completed RPS, queue, error/timeout để tránh cải thiện latency nhờ **drop request**.
7. Không đổi cùng lúc JDK + collector + heap + thread pool + SQL index rồi khẳng định collector là nguyên nhân.
8. So các trường hợp steady, peak, burst, soak; không chỉ thử một tải nhẹ.

Các lệnh chọn collector minh họa (chỉ dùng **một** cấu hình cho mỗi lần chạy, thay `app.jar` bằng ứng dụng thật):

~~~bash
java -XX:+UseG1GC -Xms2g -Xmx2g -jar app.jar
java -XX:+UseZGC -Xms2g -Xmx2g -jar app.jar
java -XX:+UseShenandoahGC -Xms2g -Xmx2g -jar app.jar
~~~

**2 GiB chỉ là giả định mẫu**, không phải heap size phù hợp mọi ứng dụng. Shenandoah có sẵn tùy build/vendor. Với JDK 24+, chế độ non-generational ZGC đã bị loại bỏ (JEP 490); tránh sao chép các cờ `ZGenerational` lỗi thời. Cần kiểm tra tài liệu runtime trước khi dùng collector/mode hiện đại.

**Đánh đổi:** collector ít STW có thể dùng thêm CPU hoặc headroom và ảnh hưởng throughput. Đánh giá hiệu quả bằng **request SLO + errors + throughput + tài nguyên**, không chỉ max pause.

## 10. Thu GC pause bằng Unified JVM Logging

Đối với JDK hiện hành, dùng Unified Logging:

~~~bash
java -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

Trong đó `gc*` ghi nhóm log GC, `safepoint` giúp tách một số dừng do safepoint, `time` và `uptime` cho mốc thời gian phục vụ correlation.

**Đọc log đúng cách:**

- Các dòng GC dạng **`Pause ... ms`** mô tả dừng STW theo collector.
- Các dòng **`Concurrent ...`** không có nghĩa JVM dừng ứng dụng trong toàn bộ giai đoạn.
- `GC cycle duration`, tổng pause time và max pause time là những đại lượng khác nhau.
- Allocation failure, heap pressure, GC concurrent CPU và safepoints có thể giúp giải thích tail.
- Cần gắn log với đúng **service instance/pod/PID**; không so GC log một JVM với request p99 của cả cluster rồi quy nguyên nhân.

Đừng đề xuất các flag GC logging kiểu cũ `-Xloggc` hoặc `-XX:+PrintGCDetails` cho JDK hiện đại; cơ chế hiện hành là `-Xlog`. Ở production phải chọn log level, file rotation và retention phù hợp; `gc*` có thể tạo nhiều dữ liệu.

**Không gọi `System.gc()` trong load test chính để “bắt buộc có GC”.** Explicit GC là một request với JVM, hành vi thay đổi theo collector và flags; nó có thể tạo pattern phi thực tế. Muốn GC xảy ra đại diện, dùng **allocation rate, object lifetime, live set và duration** giống workload thực.

## 11. Java Flight Recorder (JFR) và đối chiếu thời điểm

Ví dụ ghi JFR:

~~~bash
java -XX:StartFlightRecording=filename=load-test.jfr,settings=profile,dumponexit=true -jar app.jar
~~~

Sau khi file tồn tại:

~~~bash
jfr print --events jdk.GCPhasePause load-test.jfr
~~~

Các `jdk.GCPhasePause` events cung cấp thông tin như `startTime`, `duration`, `gcId` và tên phase khi được ghi. Theo tài liệu Oracle, phải xem đúng **pause duration/tổng pause time**, không đồng nhất với toàn bộ GC cycle concurrent.

JFR còn có thể hỗ trợ xem CPU, threads, allocation và những sự kiện runtime khác tùy cấu hình. **Nó không tự biết request nghiệp vụ nào bị chậm** nếu hệ thống không instrument request/trace; cần kết hợp tracing với GC timeline.

Lưu ý:

- Không thấy event trong recording ngắn có thể do không có pause trong cửa sổ, event chưa bật hoặc recording không bao phủ incident.
- `settings=profile` có overhead; chọn mức recording và thời gian phù hợp.
- So các event theo đúng **JVM instance**, cùng timestamps/time zone và sai số đồng hồ.
- `GarbageCollectorMXBean.getCollectionCount()/getCollectionTime()` hữu ích ở mức tổng, nhưng **không trả p99 của từng pause event** với timestamp. Không dùng average collection time/count rồi gọi “p99 GC”.

## 12. Dùng request histogram để đo SLO đúng cách

Các hệ thống như Prometheus có histogram **classic** hoặc **native**. Ví dụ bên dưới giả sử service có classic metric:

~~~text
http_server_request_duration_seconds_bucket{route="/checkout",le="0.05"}
http_server_request_duration_seconds_bucket{route="/checkout",le="0.10"}
...
http_server_request_duration_seconds_count{route="/checkout"}
~~~

Tên metric và label là **giả định để minh họa**, không phải metric mặc định luôn có ở mọi framework. Đơn vị ở đây là **giây**: 50 ms tương đương 0.05 s; 100 ms tương đương 0.10 s.

### Ước lượng p95 trong 5 phút

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_request_duration_seconds_bucket{route="/checkout"}[5m])
  )
)
~~~

### Ước lượng p99 trong 5 phút

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(http_server_request_duration_seconds_bucket{route="/checkout"}[5m])
  )
)
~~~

Đây là PromQL trên **classic histogram**. `histogram_quantile` nội suy theo bucket nên chỉ cho **ước lượng**, không phải nearest-rank chính xác của raw request durations. Cần chọn bucket dày hơn quanh các SLO thresholds. Với **native histogram**, cú pháp và cách gộp khác; tham khảo tài liệu Prometheus cho loại histogram được dùng.

### Kiểm trực tiếp tỷ lệ request ≤50 ms

Nếu đúng bucket `le="0.05"`:

~~~promql
sum(rate(http_server_request_duration_seconds_bucket{route="/checkout",le="0.05"}[5m]))
/
sum(rate(http_server_request_duration_seconds_count{route="/checkout"}[5m]))
~~~

Đây là tỷ lệ những quan sát rơi trong bucket ≤50 ms, nếu metric và filters có cùng population. Dạng **good-event ratio** thường rõ khi theo dõi SLO dạng “95% request ≤50 ms”. Với SLO dài hạn, cần tính theo **toàn window** đã định nghĩa chứ không chỉ một bucket 5 phút.

**Không trung bình p99 từng pod để ra p99 toàn service.** Percentile không cộng gộp như mean. Với classic histogram, gộp các bucket tương thích bằng `sum by (le)` rồi mới tính quantile. Nếu có route/tier khác nhau, giữ những label phân nhóm được yêu cầu.

**Đừng bỏ request lỗi/timeout khỏi denominator chỉ để dashboard đẹp**. Quy tắc ghi nhận lỗi, cancellation, request drop và deadline là một phần của SLI contract.

## 13. Ví dụ Java đầy đủ: request mix, hai tải và p95/p99

Chương trình dưới đây dùng **mẫu tổng hợp có thể tái lập** để minh họa cách tạo request mix và quyết định “đạt/không đạt SLO”. **Nó không phát HTTP traffic, không ngủ để giả lập request và không đo GC thực.** Nhờ vậy stdout **ổn định** giữa các máy; khi đánh giá GC thật cần load generator và JVM telemetry đã mô tả ở trên.

### Mô hình 1.000 request

| Loại | Số mẫu | Queue + CPU + Dependency + Network | Latency cơ sở |
| --- | ---: | --- | ---: |
| Read | 800 | 1 + 3 + 5 + 5 ms | 14 ms |
| Write | 150 | 3 + 8 + 18 + 6 ms | 35 ms |
| Heavy | 40 | 5 + 20 + 25 + 10 ms | 60 ms |
| Slow dependency | 9 | 10 + 10 + 100 + 20 ms | 140 ms |
| Queue outlier | 1 | 300 + 40 + 140 + 20 ms | 500 ms |

**Baseline:** các độ trễ cơ sở. **Burst:** thêm **80 ms thời gian queue giả lập** cho 100 request cuối, minh họa tác động lên tail. Đây không phải mô hình vật lý bắt buộc theo RPS; trong benchmark thật, queue phải được đo từ timestamp thực.

Tập **100 GC pause events giả lập** độc lập: 90 event 2 ms, 9 event 6 ms, 1 event 12 ms. **Không có liên kết timestamp với request**; mục tiêu chỉ là phân biệt hai phân phối.

### Mã `RepresentativeWorkloadSloDemo.java`

Lưu bằng UTF-8:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

public class RepresentativeWorkloadSloDemo {
    static final class Sample {
        final String kind;
        final int queueMs, cpuMs, dependencyMs, networkMs;

        Sample(String kind, int queueMs, int cpuMs,
               int dependencyMs, int networkMs) {
            this.kind = kind;
            this.queueMs = queueMs;
            this.cpuMs = cpuMs;
            this.dependencyMs = dependencyMs;
            this.networkMs = networkMs;
        }

        int latencyMs(int extraQueueMs) {
            return queueMs + cpuMs + dependencyMs + networkMs + extraQueueMs;
        }
    }

    static void add(List<Sample> samples, String kind, int n,
                    int queue, int cpu, int dependency, int network) {
        for (int i = 0; i < n; i++) {
            samples.add(new Sample(kind, queue, cpu, dependency, network));
        }
    }

    static int percentile(List<Integer> sorted, int basisPoints) {
        if (sorted.isEmpty() || basisPoints < 1 || basisPoints > 10000) {
            throw new IllegalArgumentException("invalid percentile");
        }
        int rank = (int) (((long) sorted.size() * basisPoints + 9999) / 10000);
        return sorted.get(rank - 1);
    }

    static List<Integer> latencies(List<Sample> samples, boolean burst) {
        List<Integer> values = new ArrayList<>();
        for (int i = 0; i < samples.size(); i++) {
            int extraQueue = burst && i >= 900 ? 80 : 0;
            values.add(samples.get(i).latencyMs(extraQueue));
        }
        Collections.sort(values);
        return values;
    }

    static int atMost(List<Integer> sorted, int thresholdMs) {
        int count = 0;
        for (int latency : sorted) {
            if (latency <= thresholdMs) count++;
        }
        return count;
    }

    static String mean(List<Integer> sorted) {
        long sum = 0;
        for (int value : sorted) sum += value;
        return String.format(Locale.ROOT, "%.2f",
                (double) sum / sorted.size());
    }

    static void printScenario(String name, List<Integer> sorted) {
        int p95 = percentile(sorted, 9500);
        int p99 = percentile(sorted, 9900);
        System.out.println(name + ".p50Ms=" + percentile(sorted, 5000));
        System.out.println(name + ".p95Ms=" + p95);
        System.out.println(name + ".p99Ms=" + p99);
        System.out.println(name + ".p999Ms=" + percentile(sorted, 9990));
        System.out.println(name + ".maxMs=" + sorted.get(sorted.size() - 1));
        System.out.println(name + ".meanMs=" + mean(sorted));
        System.out.println(name + ".countAtMost50Ms=" + atMost(sorted, 50));
        System.out.println(name + ".countAtMost100Ms=" + atMost(sorted, 100));
        System.out.println(name + ".p95GoalMet=" + (p95 <= 50));
        System.out.println(name + ".p99GoalMet=" + (p99 <= 100));
    }

    public static void main(String[] args) {
        List<Sample> samples = new ArrayList<>();
        add(samples, "read", 800, 1, 3, 5, 5);
        add(samples, "write", 150, 3, 8, 18, 6);
        add(samples, "heavy", 40, 5, 20, 25, 10);
        add(samples, "slow-dependency", 9, 10, 10, 100, 20);
        add(samples, "queue-outlier", 1, 300, 40, 140, 20);

        List<Integer> baseline = latencies(samples, false);
        List<Integer> burst = latencies(samples, true);

        List<Integer> gcPauses = new ArrayList<>();
        for (int i = 0; i < 90; i++) gcPauses.add(2);
        for (int i = 0; i < 9; i++) gcPauses.add(6);
        gcPauses.add(12);
        Collections.sort(gcPauses);

        System.out.println("requests=" + samples.size());
        System.out.println("mix=read:800,write:150,heavy:40,slow:9,outlier:1");
        printScenario("baseline", baseline);
        printScenario("burst", burst);
        System.out.println("gcPauseEvents=" + gcPauses.size());
        System.out.println("gcPause.p95Ms=" + percentile(gcPauses, 9500));
        System.out.println("gcPause.p99Ms=" + percentile(gcPauses, 9900));
        System.out.println("gcPause.maxMs=" + gcPauses.get(gcPauses.size() - 1));
        System.out.println("checks=" + (
                samples.size() == 1000
                && percentile(baseline, 5000) == 14
                && percentile(baseline, 9500) == 35
                && percentile(baseline, 9900) == 60
                && percentile(baseline, 9990) == 140
                && baseline.get(999) == 500
                && "20.61".equals(mean(baseline))
                && atMost(baseline, 50) == 950
                && atMost(baseline, 100) == 990
                && percentile(burst, 9500) == 115
                && percentile(burst, 9900) == 140
                && percentile(burst, 9990) == 220
                && burst.get(999) == 580
                && "28.61".equals(mean(burst))
                && atMost(burst, 50) == 900
                && atMost(burst, 100) == 900
                && gcPauses.size() == 100
                && percentile(gcPauses, 9500) == 6
                && percentile(gcPauses, 9900) == 6
                && gcPauses.get(99) == 12));
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 RepresentativeWorkloadSloDemo.java
java RepresentativeWorkloadSloDemo
~~~

Mã dùng API đã có từ Java 15. Đã biên dịch thành công với **`javac --release 15` và `javac --release 17`**, chạy trên **JDK 24**. Stdout thực tế:

~~~text
requests=1000
mix=read:800,write:150,heavy:40,slow:9,outlier:1
baseline.p50Ms=14
baseline.p95Ms=35
baseline.p99Ms=60
baseline.p999Ms=140
baseline.maxMs=500
baseline.meanMs=20.61
baseline.countAtMost50Ms=950
baseline.countAtMost100Ms=990
baseline.p95GoalMet=true
baseline.p99GoalMet=true
burst.p50Ms=14
burst.p95Ms=115
burst.p99Ms=140
burst.p999Ms=220
burst.maxMs=580
burst.meanMs=28.61
burst.countAtMost50Ms=900
burst.countAtMost100Ms=900
burst.p95GoalMet=false
burst.p99GoalMet=false
gcPauseEvents=100
gcPause.p95Ms=6
gcPause.p99Ms=6
gcPause.maxMs=12
checks=true
~~~

### Ý nghĩa kết quả

- **`baseline.p95Ms=35`, `baseline.p99Ms=60`:** đều đạt mục tiêu SLO mẫu (50/100 ms).
- **`baseline.countAtMost50Ms=950`, `baseline.countAtMost100Ms=990`:** đúng 95% và 99% request nằm trong hai ngưỡng.
- **`baseline.maxMs=500`:** p99 đạt mục tiêu **không có nghĩa** mọi request đều nhanh.
- **`burst.p50Ms=14`:** median không thay đổi vì phần nhanh nhất vẫn chiếm đa số.
- **`burst.p95Ms=115`, `burst.p99Ms=140`:** queue wait bổ sung khiến cả hai mục tiêu bị vi phạm.
- **`burst.countAtMost50Ms=900`, `burst.countAtMost100Ms=900`:** còn 90% request đạt hai ngưỡng.
- **`gcPause.p99Ms=6`, `gcPause.maxMs=12`:** hai số chỉ mô tả **100 GC events mẫu**, không tự giải thích request latency.
- **`checks=true`:** xác nhận toàn bộ phép tính và kết quả mong đợi của demo.

**Giới hạn quan trọng:** không được sử dụng những số liệu tổng hợp này để kết luận GC của máy chạy nhanh/chậm. Không có request HTTP thật, không có phép đo CPU hoặc GC thật, không có arrival scheduling. Demo nhằm làm rõ **thiết kế tải và đọc p95/p99**, trước khi tổ chức benchmark thực sự.

## 14. Chuyển mô hình thành kiểm thử tải thật

### 14.1. Một workload specification có thể review

~~~yaml
# Ví dụ mô tả kế hoạch, KHÔNG phải format chạy trực tiếp của k6/JMeter/Gatling.
test_name: representative-java-gc-load
population: interactive-api
request_mix:
  read: 80%
  write: 15%
  heavy: 4%
  slow_dependency: 0.9%
  rare_outlier: 0.1%
arrival_model: open-loop-with-bursts
phases:
  - warmup
  - baseline_steady
  - expected_peak
  - burst_and_recovery
  - soak
metrics:
  - offered_rps
  - completed_rps
  - response_duration_histogram
  - errors_timeouts_rejections
  - queue_wait
  - allocation_rate_and_live_set
  - gc_stw_pause_events
  - gc_concurrent_cpu_and_stalls
  - cpu_memory_limits
illustrative_objectives:
  min_percent_within_50ms: 95
  min_percent_within_100ms: 99
~~~

Khi triển khai thật, thay tỷ lệ trên bằng dữ liệu production, chọn các biến thiên payload và cache hit/miss, và chuyển cấu hình sang **đúng cú pháp của công cụ load testing**. Không giả định YAML khái niệm trên là chạy được.

### 14.2. Instrument một request Java đúng thời điểm

Đo một xử lý đồng bộ bằng `System.nanoTime()`:

~~~java
long startNs = System.nanoTime();
try {
    // Tác vụ đồng bộ của ứng dụng.
    processRequest();
} finally {
    long elapsedNs = System.nanoTime() - startNs;
    // Ghi vào histogram có đơn vị rõ ràng, không chỉ print ra console.
}
~~~

Đây là **đoạn minh họa chưa độc lập**: `processRequest()` và reporter phải được ứng dụng định nghĩa. Với async/reactive request, đừng record ở lúc gửi task vào queue rồi gọi là end-to-end; record **lúc response completion** theo SLI.

`System.nanoTime()` phù hợp tính elapsed duration trong cùng JVM, nhưng **không** dùng giá trị tuyệt đối của nó để nối timestamps giữa nhiều JVM. Khi tương quan GC và request, dùng wall timestamps đã đồng bộ và trace/instance metadata.

### 14.3. Đưa allocation rate và live set vào phép thử

Đo GC cần nhiều hơn RPS:

- Bytes allocated/request và allocated bytes/second.
- Tỷ lệ object sống qua GC, live-set occupancy, cache/session size.
- Nhiều object ngắn hạn so với object sống lâu; tham chiếu qua các thế hệ.
- CPU quota và memory limit của container.
- GC cycles, STW pauses, allocation stalls, concurrent GC CPU và OOM.
- Thời lượng soak đủ để quan sát cache growth và heap behavior.

Một workload chỉ có một vòng lặp cấp phát object rồi hủy ngay có thể gây nhiều young GC nhưng **không đại diện** cho ứng dụng có cache sống lâu hoặc traffic phụ thuộc DB. Ngược lại, workload hầu như không tạo allocation có thể không kích hoạt GC đủ để so collector.

### 14.4. Bảo đảm phép thử có thể lặp lại

Ghi rõ JDK build, GC flags, heap, cgroup CPU/memory, database version, dataset, traffic seed, generator version, time window và số trial. Nếu dùng traffic replay, cần xử lý an toàn thông tin nhạy cảm và sự cho phép của chủ hệ thống.

Nếu generator bị CPU bottleneck, những request thực tế phát ra không theo planned arrival; phải xem scheduling drift và offered/completed RPS trước khi tin p99.

## 15. Đánh giá A/B không chỉ qua một con số

Để so một thay đổi heap/GC/JDK, nên xuất báo cáo:

| Nhóm | Chỉ số cần có |
| --- | --- |
| **Workload** | Mix, payload, arrivals, offered/completed RPS, active requests |
| **Latency** | p50, p95, p99, p99.9 khi đủ mẫu, max và histogram |
| **Reliability** | Success/error/timeout/reject/cancel, retry rate |
| **GC** | Pause event p95/p99/max, pause frequency, GC cycles, stalls |
| **Heap** | Live set, allocation rate, committed/used heap, OOM |
| **Resources** | CPU utilization, throttling, RSS, memory headroom |
| **Correlations** | Request trace/queue depth và GC timestamps cùng JVM |
| **Conditions** | JDK/OS/container, GC mode, heap, build và test phase |

Cần kết luận theo đúng giả thuyết. Nếu ZGC giảm STW max nhưng tăng GC CPU, làm queue wait và request p99 xấu hơn trong môi trường CPU-limited, chưa thể gọi là cải thiện SLO. Nếu G1 có pause hơi dài nhưng request p99/throughput/errors tốt hơn theo nhu cầu thì vẫn có thể là lựa chọn phù hợp. **Không có collector tối ưu cho mọi workload.**

Không dùng một lần đo ngắn làm bằng chứng tuyệt đối: warm-up, JIT, cache, OS scheduler và downstream variance có thể gây nhiễu lớn. Lặp trial và mô tả độ biến thiên thay vì chọn một run đẹp nhất.

## 16. Những nhầm lẫn thường gặp

| Nhận định sai | Giải thích đúng |
| --- | --- |
| “GC pause p99 bằng request p99” | Khác mẫu và ranh giới đo |
| “GC max 6 ms thì API phải hoàn tất ≤6 ms” | Request còn queue, CPU, DB, network, retries |
| “p99=60 ms nghĩa là request nào cũng ≤60 ms” | 1% request chậm nhất có thể rất lớn |
| “Chỉ cần tải trung bình là representative” | Phải có burst, peak, live set và payload mix |
| “Closed-loop tự động đo tail dưới RPS cố định” | Có nguy cơ coordinated omission |
| “SLO p95 và p99 có thể cộng ngân sách lỗi” | Những request chậm có thể vi phạm cả hai ngưỡng |
| “p99 của nhiều pod lấy trung bình thành p99 cluster” | Cần gộp histogram/distribution tương thích |
| “`MaxGCPauseMillis=50` bảo đảm p99 request 50 ms” | Là pause-time **goal**, không phải response SLO |
| “GC cycle 300 ms nghĩa JVM STW 300 ms” | Có các pha concurrent |
| “GC log có ít event nghĩa collector luôn nhanh” | Cỡ mẫu có thể không đủ |
| “Đo raw p99 trên 10 request là đáng tin” | Không đủ độ phân giải tail |
| “Bỏ request timeout khỏi histogram sẽ không sao” | Che trải nghiệm tệ và làm denominator sai |
| “Gọi `System.gc()` tạo workload GC thật” | Explicit GC có thể làm méo workload |
| “Chỉ p99 giảm là tốt” | Có thể đồng thời tăng errors, drops hoặc giảm throughput |
| “Dùng flag `ZGenerational` cũ ở JDK 24+” | Chế độ non-generational đã bị loại bỏ |
| “Chậm đồng thời với GC nghĩa chắc do GC” | Tương quan chưa đủ; cần trace/timeline/queue |

## 17. Checklist triển khai benchmark và SLO

- [ ] Định nghĩa chính xác request population, boundary, window và cách tính lỗi/timeout.
- [ ] Chọn SLO p95/p99 từ nhu cầu người dùng, không sao chép giá trị mặc định của JVM.
- [ ] Có request mix, payload, downstream và cache hit/miss đại diện.
- [ ] Có allocation rate, live set và object lifetime gần thực tế.
- [ ] Ghi offered RPS, completed RPS, queue depth, concurrency và arrival model.
- [ ] Có warm-up, steady, peak, burst, recovery, soak theo nhu cầu.
- [ ] Kiểm tra generator không nghẽn và không bỏ arrival vì coordinated omission.
- [ ] Có request histogram p95/p99 và đủ cỡ mẫu; giữ error/timeout/rejections.
- [ ] Thu GC `-Xlog:gc*,safepoint` hoặc JFR `jdk.GCPhasePause`.
- [ ] Phân biệt STW pauses với concurrent GC cycle và allocation stalls.
- [ ] Đối chiếu request outliers với GC/CPU/queue/downstream theo cùng instance/time.
- [ ] So sánh các run dưới JDK/GC/heap/quota/workload được kiểm soát.
- [ ] Không dựa duy nhất vào `-XX:MaxGCPauseMillis` để tuyên bố đạt SLO.
- [ ] Không benchmark bằng `System.gc()` làm workload chính.
- [ ] Công bố throughput, CPU/RAM, error, sampling/window và kết luận có giới hạn.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** GC p99 pause là 5 ms, request p99 là 130 ms. Có mâu thuẫn không?  
**Không.** Hai chỉ số đo những sự kiện khác nhau, request còn chịu queue, downstream, CPU và các yếu tố khác.

**Câu 2.** Trong 1.000 request, mục tiêu “95% ≤50 ms” cho phép tối đa bao nhiêu request >50 ms?  
**50** nếu population và quy ước `≤` đúng như đã định nghĩa.

**Câu 3.** Có được cộng ngân sách 50 request >50 ms và 10 request >100 ms thành 60 không?  
**Không**, vì request >100 ms cũng nằm trong tập >50 ms.

**Câu 4.** Vì sao p50 giữ 14 ms nhưng p95 tăng từ 35 lên 115 ms trong demo?  
Vì thời gian queue tăng chỉ ở một phần request; median đại diện nửa nhanh nhất chưa bị ảnh hưởng.

**Câu 5.** Bốn GC pauses có đủ để ước lượng p99 GC ổn định không?  
**Không.** Cần đủ số sự kiện và thời gian quan sát; báo count/window để người đọc đánh giá.

**Câu 6.** Vì sao load generator closed-loop có thể làm p99 trông đẹp?  
Nó tự giảm arrivals khi server chậm, bỏ bớt request đáng lẽ đến lúc nghẽn (coordinated omission).

**Câu 7.** Nếu p99 request giảm nhưng error/timeout tăng, có thể kết luận tối ưu thành công không?  
**Không**; phải xét cùng reliability/throughput và denominator của latency SLI.

**Câu 8.** Vì sao không lấy trung bình p99 của mọi pod thành p99 cluster?  
Percentile không tổng hợp được bằng trung bình; cần gộp histogram/distribution.

**Câu 9.** Khi p99 cao, bước chẩn đoán đầu tiên có nhất thiết đổi collector không?  
**Không.** Kiểm tra scope/window, queue, downstream, CPU, request traces và GC timestamps trước khi chọn thay đổi.

## 19. Tài liệu tham khảo hiện hành

- Oracle Java SE 26 — **Troubleshoot Performance Issues Using Flight Recorder**: `jdk.GCPhasePause`, duration, sum of pauses và nguyên tắc đọc event GC. https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html
- Oracle Java SE 25 — **The java Command**, `-Xlog` và `StartFlightRecording`. https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- Oracle Java SE 25 — **G1 GC Tuning**, pause-time goal, heap/throughput trade-offs. https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html
- OpenJDK JEP 377 (ZGC Production) và JEP 379 (Shenandoah Production), Java 15. https://openjdk.org/jeps/377 ; https://openjdk.org/jeps/379
- OpenJDK JEP 490 — **Remove the Non-Generational ZGC Mode**, JDK 24. https://openjdk.org/jeps/490
- Google SRE Workbook — **Implementing SLOs**: latency good events, thresholds, windows và SLO phân nhóm. https://sre.google/workbook/implementing-slos/
- Prometheus — **Histograms and Summaries**: quy tắc dùng histogram và gộp phân phối. https://prometheus.io/docs/practices/histograms/
- Prometheus — **histogram_quantile**: cú pháp classic/native histogram và cách ước lượng quantiles. https://prometheus.io/docs/prometheus/latest/querying/functions/#histogram_quantile