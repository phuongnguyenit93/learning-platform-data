# Phân biệt thiếu tài nguyên với lỗi cấu hình hoặc mô hình dữ liệu

Một dịch vụ Java dùng cơ sở dữ liệu NoSQL bắt đầu chậm trong giờ cao điểm. Dashboard cho thấy **p99 latency tăng từ 80 ms lên 2 giây**, request timeout xuất hiện và người vận hành đề xuất tăng gấp đôi CPU/RAM của cluster. Nhưng CPU toàn cluster chỉ ở mức 45%. Một người khác cho rằng “thiếu connection pool”, còn nhóm phát triển nghi ngờ truy vấn vừa được thêm vào không dùng đúng index.

Ba giả thuyết đều có thể đúng trong những điều kiện khác nhau:

- **Thiếu tài nguyên (resource saturation):** năng lực xử lý của một thành phần không theo kịp tải; CPU, memory, I/O, network, connection slots, partition throughput hoặc quota bị chạm ngưỡng.
- **Lỗi cấu hình (configuration mismatch):** pool quá nhỏ, timeout không hợp lý, retry không có giới hạn, index chưa được triển khai, read preference không phù hợp, cache TTL sai hoặc provisioned throughput không đúng với tải mong đợi.
- **Lỗi mô hình dữ liệu/access pattern (data-model mismatch):** dùng partition key gây hot key, một truy vấn buộc phải scan, tài liệu phình quá lớn, cập nhật tranh chấp cùng aggregate, cross-partition fan-out, tombstone quá dày hoặc cách lưu dữ liệu không khớp yêu cầu truy cập.

Đôi khi **cả ba cùng xuất hiện**. Một access pattern tồi gây đọc quá nhiều dữ liệu; nó đẩy I/O lên 100%; tăng I/O chỉ dời điểm nghẽn chứ không sửa truy vấn. Một pool cấu hình quá nhỏ làm requests xếp hàng ngay tại JVM trong khi database rảnh; thêm nodes NoSQL không giảm thời gian chờ pool. Một tenant nóng khiến đúng **một phân vùng** quá tải dù trung bình CPU cả cluster vẫn thấp.

Bài học thuộc chương **Quan sát và chẩn đoán** của module **Database No SQL** hướng dẫn cách hình thành giả thuyết, đối chiếu traces/metrics/logs/query plans, tìm đúng phạm vi tài nguyên đang nghẽn, thực hiện thí nghiệm an toàn và chọn giải pháp dựa trên nguyên nhân gốc thay vì dựa vào một biểu đồ đơn lẻ.

> **Nguyên tắc:** “Chậm” là triệu chứng, “CPU cao” là một quan sát, còn “thiếu CPU” là **giả thuyết nguyên nhân**. Chỉ kết luận sau khi biết request nào chậm, chậm ở bước nào, tài nguyên nào bão hòa, tại phạm vi nào và vì sao lượng công việc trên mỗi request thay đổi.

## 1. Phân biệt triệu chứng, chỉ báo và nguyên nhân

Xét sự cố:

~~~text
Symptom:
    GET /orders p99 = 2,000 ms.

Observed indicators:
    DB scanned documents/request tăng 100 lần.
    Disk read bytes/s tăng.
    Database CPU tăng ở hai shards.
    Application queue tăng.

Possible root cause:
    Truy vấn mới không còn tận dụng index sau khi đổi filter/sort.
~~~

Nếu chỉ nhìn CPU cao, dễ đề xuất thêm CPU. Nhưng **nguyên nhân trực tiếp tạo thêm công việc** có thể là access path bị sai.

### 1.1. Triệu chứng phía người dùng

- p95/p99 API tăng, timeout hoặc tỷ lệ lỗi cao hơn.
- Request trả thành công nhưng dữ liệu stale hoặc thiếu.
- Checkout có nhiều retry/conflict, chưa hoàn tất workflow.
- Dashboard đọc nhanh nhưng dữ liệu cuối không còn đúng.
- Một tenant/region bị ảnh hưởng trong khi nhóm khác bình thường.

### 1.2. Chỉ báo đo được

CPU saturation, disk read latency, pool wait time, RU/RCU/WCU throttling, queue age, compaction backlog, documents examined, partition skew hoặc replication lag là **bằng chứng từng phần**.

### 1.3. Nguyên nhân gốc

Một cấu trúc index không phù hợp, key định tuyến sai, client retry storm, quota quá thấp, pod thiếu RAM hoặc thay đổi schema làm bản ghi tăng kích thước có thể là nguyên nhân.

### 1.4. Phân biệt “resource bottleneck” và “resource root cause”

Một ổ đĩa có thể là tài nguyên bão hòa thật, nhưng điều khiến nó bão hòa là một index scan vô ích. Cả hai phát biểu “I/O bottleneck” và “model/query lỗi” có thể đúng, nhưng **quyết định sửa** phải cân nhắc gốc gây thêm I/O.

### 1.5. Đánh giá bằng câu hỏi phản chứng

Nếu tăng gấp đôi CPU mà không đổi query shape, tình trạng còn lặp lại khi traffic tăng không? Nếu thêm đúng index trên staging làm documents examined giảm từ 1 triệu còn 50, vấn đề có phải thiếu RAM thuần túy không? Những câu hỏi phản chứng giúp tránh suy luận một chiều.

## 2. Ba nhóm nguyên nhân và các dấu hiệu điển hình

| Nhóm | Dấu hiệu hỗ trợ | Dấu hiệu không đủ để kết luận | Ví dụ cách xử lý đúng |
|---|---|---|---|
| Thiếu CPU | CPU/CPU throttling ở bottleneck instance cao, run queue tăng, service time tăng | CPU trung bình cluster cao | Scale/tune CPU hoặc giảm công việc |
| Thiếu RAM/cache | Memory pressure, evictions, page faults/GC, read amplification | RSS cao một mình | Giảm working set, memory bound, bổ sung RAM |
| Thiếu I/O | IOPS/throughput chạm giới hạn, latency I/O và queues tăng | Disk utilization 100% một mình | Tối ưu accesses, I/O capacity, compaction |
| Network hạn chế | Bandwidth/retransmits/RTT, connection errors | Chỉ thấy API chậm | Network placement, payload, fan-out |
| Quota/throttling | 429/throttled reads/writes, consumed capacity hoặc RU gần trần | CPU thấp | Tăng quota/capacity hoặc giảm cost/query |
| Pool cấu hình sai | Wait-for-connection cao, DB chưa bão hòa | Số connections bằng max | Tune bounded pool và concurrency |
| Timeout/retry sai | Deadline mismatch, attempts/request cao, retries làm tải khuếch đại | Tỷ lệ timeout cao | Chỉnh timeouts, retry budget, backoff |
| Index/query sai | Scan/examined nhiều, fan-out, sort tốn bộ nhớ | Có tạo một index nào đó | Sửa query/index theo đường truy cập |
| Partition key sai | Một key/shard nóng, toàn cluster còn dư | Cluster CPU thấp | Đổi partitioning/aggregate design |
| Document/schema sai | Value quá lớn, arrays tăng vô hạn, cập nhật cả document tốn kém | Document count chưa nhiều | Tách/giới hạn aggregate, sửa schema |

Không biến bảng thành luật tự động; cùng một metric có thể do nhiều nguyên nhân.

## 3. Một chuỗi quan sát từ request tới ổ đĩa

~~~mermaid
flowchart LR
    USER["Client / Load generator"] --> GATE["Gateway / Rate limiter"]
    GATE --> APP["Java service"]
    APP --> POOL["Client pool / SDK"]
    POOL --> NET["Network / TLS / DNS"]
    NET --> ROUTE["Router / coordinator"]
    ROUTE --> PART["Partition / shard"]
    PART --> IDX["Index / query execution"]
    IDX --> STOR["Cache / disk / log"]
    PART --> REPL["Replication / commit"]
    PART --> CDC["CDC / outbox"]
~~~

Một request có thể chờ ở từng mũi tên. Nếu chỉ ghi `GET /orders took 1.2s`, ta không biết 1.1s là:

- chờ connection trong JVM,
- chờ throttling/quota ở server,
- lấy dữ liệu từ nhiều shards,
- chờ disk I/O,
- retry lỗi mạng,
- hay chờ commit replication.

### 3.1. Thời gian đầu–cuối và thời gian thành phần

Một trace minh họa:

~~~text
End-to-end = 1,220 ms
  gateway wait            10 ms
  auth and mapping        20 ms
  SDK pool wait          900 ms
  wire + DB execution    260 ms
  response serialization  30 ms
~~~

Ở trường hợp này, 900 ms nằm **trước khi DB thực sự xử lý**. Tăng DB CPU trước khi điều tra client pool có thể vô ích.

### 3.2. Tổng các span durations không luôn bằng end-to-end

Nếu có song song/fan-out hoặc nested spans, cộng tất cả durations có thể lớn hơn wall-clock time. Dùng critical path và parent–child timing, không cộng mù.

### 3.3. Trace là bản đồ giả thuyết

Khi có queue time, server execution, read attempts, query plan, connection acquisition và retries, ta có thể thấy tăng thời gian ở đoạn nào **trước** khi đoán lý do.

### 3.4. Observability cần nhiều lớp

Metrics cho xu hướng và saturation; traces cho path của request; logs cho lỗi/decision; query plans và database profiler cho access path; trạng thái dữ liệu để phát hiện hot keys/schema.

## 4. RED và USE: hai lăng kính bổ sung

### 4.1. RED cho requests

**Rate**, **Errors**, **Duration** là ba nhóm chỉ số phù hợp để hiểu tác động lên người dùng:

| RED | Câu hỏi |
|---|---|
| Rate | Bao nhiêu requests/transactions mỗi giây? |
| Errors | Bao nhiêu timeout, 5xx, throttled, rejected? |
| Duration | p50/p95/p99 và phân phối latency thế nào? |

### 4.2. USE cho tài nguyên

**Utilization**, **Saturation**, **Errors** phù hợp khi chẩn đoán một tài nguyên:

| USE | Ví dụ |
|---|---|
| Utilization | CPU busy, disk throughput, connection occupancy |
| Saturation | CPU run queue, I/O queue, pool waiters, pending requests |
| Errors | OOM, disk errors, network retransmits, connection exhaustion |

### 4.3. Bắt đầu bằng RED, khoanh vùng bằng USE

Một API p99 xấu giúp biết **đối tượng bị ảnh hưởng**. USE ở JVM/DB/shard giúp tìm **nơi bão hòa**. Chỉ số saturation phải đọc theo đúng scope; CPU trung bình toàn cluster không thay CPU của một primary shard.

### 4.4. RED không thay correctness

Hệ trả 200 nhanh nhưng reads stale hoặc tạo duplicate Orders vẫn là lỗi. Bổ sung metrics cho invariant violations, CDC lag, idempotency conflict và output reconciliation.

### 4.5. USE không nói nguyên nhân của công việc

Disk I/O 100% có thể do traffic hợp lệ, thiếu disk capacity, một query scan sai hoặc compaction backlog. Hãy đối chiếu với **workload per operation**.

## 5. Đọc metric theo phạm vi, không lấy trung bình che ngoại lệ

Một cluster bốn shards có CPU:

~~~text
shard-A = 98%
shard-B = 27%
shard-C = 24%
shard-D = 26%

Average = 43.75%
~~~

Nếu 60% writes hướng tới shard-A, ứng dụng có thể chậm do **shard-A bão hòa**, dù average 44% trông còn dư.

### 5.1. Scope cần có

Request route, endpoint, operation name, tenant tier, collection/table, logical partition, shard/replica, region/AZ, index/query shape, client instance và time window.

### 5.2. Không đưa ID tùy ý vào metric labels

Mỗi orderId, userId hoặc raw tenantId có thể tạo vô số time series và chứa PII. Dùng bounded groupings như `tenant_tier`, `route`, `operation`, `region`; hot key details có thể điều tra bằng sampling/log có kiểm soát.

### 5.3. Phân biệt read và write

Read p99 có thể tăng do index/replica lag trong khi write latency bình thường. Gộp mọi operation vào một histogram che nguyên nhân.

### 5.4. P99 theo thời gian

Một histogram tích lũy 24 giờ có thể che outage 3 phút. Xem các cửa sổ ngắn phù hợp request volume; tránh kết luận từ percentile khi sample count quá ít.

### 5.5. SLO là yêu cầu trên tác động

Nếu SLO `p99 <= 200ms` với 99,9% request success, một bước làm throughput cao hơn nhưng p99 vượt 500ms không phải cải thiện theo mục tiêu.

## 6. Xác định thay đổi gần thời điểm sự cố

Một sự cố thường có “điểm bắt đầu”:

~~~text
10:00 deploy app v12
10:02 query scan tăng
10:03 source read bytes/s tăng
10:04 disk queue tăng
10:05 API p99 tăng mạnh
~~~

Chuỗi thời gian này hỗ trợ giả thuyết **thay đổi query** gây I/O saturation; chưa phải bằng chứng tuyệt đối cho tới khi so query plan/diff và thí nghiệm phù hợp.

### 6.1. Những thay đổi cần kiểm tra

- Code release, SDK/driver, connection pooling, timeout/retry config.
- Schema/index create/drop, materialized view, partition key strategy.
- Data cardinality, tenant onboarding, flash sale hoặc workload shift.
- Autoscale, node replacement, shard split, leadership/failover.
- TLS/DNS/network route, cross-region traffic.
- Cache expiry/invalidation, TTL job, migration/backfill và CDC consumers.

### 6.2. Correlation không đủ để khẳng định causation

Hai sự kiện cùng lúc có thể do một nguyên nhân khác, như marketing campaign kích hoạt cả cache misses và compaction. Tìm thêm chỉ số công việc/requests tương ứng.

### 6.3. Thay đổi bị bỏ quên: dữ liệu

Không có deploy vẫn có thể chậm do một document phình lên 100 MB, tenant mới lớn gấp 20 lần, tombstone accumulation hoặc dataset vượt cache.

### 6.4. Đặt mốc baseline

So request shape và load cùng giờ/chu kỳ nếu có tính mùa vụ; so tuần trước ở cùng RPS/tenant mix, không chỉ một ngày khác tải.

## 7. CPU: thiếu năng lực hay bị đốt bởi công việc thừa?

CPU tăng là một dấu hiệu **tài nguyên đang làm việc nhiều** nhưng không nói CPU là gốc.

### 7.1. CPU saturation thật

CPU utilization và run queue tại node cần xử lý tăng, thread execution/GC/serialization tốn thời gian, p99 tăng khi offered rate tăng. Scale CPU có thể hữu ích nếu công việc là cần thiết và có khả năng phân tán.

### 7.2. CPU do scan hoặc giải mã dữ liệu thừa

Một request cần 50 Orders nhưng DB quét 2 triệu documents và filter phần lớn. CPU cao là hậu quả của access path. Index/query rewrite có thể giảm CPU nhiều hơn scale.

### 7.3. CPU throttling trong container

Pod bị giới hạn CPU quota có thể bị throttle dù node vật lý còn dư. Cần xem CPU limits/throttled time tại container, không chỉ CPU host tổng.

### 7.4. Client CPU cũng có thể là bottleneck

Java service serialize JSON, nén dữ liệu, kiểm chữ ký hoặc GC nhiều; database CPU thấp. Đề xuất thêm DB shards không chữa CPU client.

### 7.5. Phân biệt user CPU, system CPU và GC

Nếu CPU cao vì GC, gốc có thể là cache quá lớn/allocations từ response mapping. Nếu CPU cao vì syscalls/network, điều tra IO churn. Profiling phải thực hiện an toàn, có sampling.

## 8. Bộ nhớ: OOM, GC, cache miss và fragmentation

### 8.1. Thiếu RAM cho working set

Dataset nóng vượt cache memory dẫn tới eviction, miss ratio tăng, disk reads và latency tăng. Có thể cân nhắc tăng RAM, giảm document size hoặc đổi access pattern.

### 8.2. Không phải RSS cao luôn xấu

Một database có thể dùng page cache/allocator để tối ưu I/O; RSS cao chưa chứng minh memory pressure. Cần metrics page faults, swap, eviction, GC, out-of-memory và memory headroom.

### 8.3. Java heap vs native memory

GC heap ổn nhưng RSS tăng có thể do Netty/direct buffers, mmap, thread stacks hoặc native allocations. Không suy lỗi database từ `OutOfMemoryError` của JVM trước khi phân biệt memory regions.

### 8.4. Cache eviction là hiệu ứng hay nguyên nhân?

Redis/Caffeine loại entries vì thiếu capacity; origin QPS tăng. Cache miss storm có thể khiến database chậm, rồi users retry, gây vòng khuếch đại. Tuy nhiên, cache TTL quá ngắn do cấu hình có thể tạo miss storm **không phải thiếu RAM**.

### 8.5. Document quá lớn

Một field chứa mảng không giới hạn làm tăng allocation, serialization và network. Thêm RAM có thể tạm giảm GC nhưng **mô hình aggregate** mới là vấn đề cần giải.

## 9. Disk I/O và LSM compaction

Nhiều NoSQL dựa trên LSM tree, log/segments, B-tree hoặc các cấu trúc storage khác. Disk latency có thể do foreground reads/writes, page faults hoặc compaction/flush/backup.

### 9.1. Ba đại lượng khác nhau

- **Throughput:** bytes/s.
- **IOPS:** số operations I/O/s.
- **Service latency/queue:** thời gian xử lý/chờ I/O.

Một ổ đạt throughput tối đa với sequential IO có thể khác hiệu năng khi random IOPS nhỏ.

### 9.2. I/O cao là thiếu capacity khi nào?

Nếu cùng access pattern hợp lệ, IO queue/latency tăng tại ngưỡng thiết bị/provisioned IOPS, scale/tune I/O có thể đúng. Nhưng cần xác nhận query không đang đọc số bytes quá lớn vì lọc sai.

### 9.3. Compaction debt

Write-heavy workload có thể nhanh lúc đầu, sau đó compaction backlog tăng, disk reads/writes và p99 tăng. Run 5 phút không đủ; phải đo sustained load và compaction/flush metrics.

### 9.4. TTL/tombstones

Xóa logic/TTL không nhất thiết giải phóng storage tức thời. Quét qua nhiều tombstones có thể làm truy vấn chậm; tạo cách truy cập phải xét retention, tombstone lifecycle và compaction.

### 9.5. Disk full không phải CPU bottleneck

Near-full disk có thể làm compaction, snapshots và writes bị chặn. Scale CPU không giải quyết capacity storage/log/repair.

## 10. Network và đường đi request

### 10.1. RTT và region

Client tại Đông Nam Á gọi trực tiếp primary ở region xa có baseline RTT lớn. DB execution 5 ms nhưng network 180 ms không thể sửa bằng thêm DB CPU.

### 10.2. Network saturation

Payload rất lớn, cross-region replication hoặc fan-out có thể chạm bandwidth. Đo network throughput, TCP retransmits, connection resets, TLS handshake và latency theo hop.

### 10.3. DNS/TLS/connection churn

Ứng dụng tạo client connection mới mỗi request có thể tốn handshake và cạn ephemeral ports. Tái sử dụng client/pools đúng hơn là tăng số nodes NoSQL.

### 10.4. Remote retry

Retries do packet loss/throttling có thể biến một request thành nhiều network calls, gia tăng chính vấn đề đang gặp. Quan sát actual attempts per logical operation.

### 10.5. Follower/replica routing

Read preference chọn replica xa hoặc lag có thể làm read latency/staleness tăng dù leader vẫn khỏe. Kiểm routing/consistency theo deployment.

## 11. Quota/throttling: tài nguyên logic khác CPU vật lý

Trong dịch vụ NoSQL managed, bottleneck có thể là **provisioned request capacity, RU/s, per-partition limits, account quota hoặc rate limiter**, ngay cả khi CPU metrics không cao.

### 11.1. Nhận diện throttle

Tỷ lệ 429/throttled requests, retry-after, consumed capacity gần provisioned budget, SDK retry metrics và queue depth. Phân biệt `THROTTLED` với `NOT_FOUND`.

### 11.2. Aggregate capacity chưa nói per-partition

Toàn table còn dư capacity nhưng một partition key nhận phần lớn requests vẫn có thể bị throttle. Phải đo theo hot key/logical partition/shard khi API hỗ trợ.

### 11.3. Khi nào tăng quota đúng?

Nếu truy vấn hiệu quả, workload hợp lệ, data model cân bằng và lượng request vượt mức provisioned, tăng capacity/autoscale hoặc reservation đúng có thể phù hợp.

### 11.4. Khi nào tăng quota chỉ che lỗi?

Một query scan hàng triệu items do thiếu index tiêu tốn RU/RCU cao; tăng RU khiến chi phí tăng theo số scan mà không giải quyết access path.

### 11.5. Backoff và retry budget

Throttling thường cần bounded exponential backoff/jitter hoặc server-specified retry guidance theo API. Retry ngay liên tục tạo **retry storm** và tăng throttling.

## 12. Connection pool, thread pool và concurrency limits

Giả sử Java SDK có pool tối đa 32 connections, nhưng service nhận 2.000 requests đồng thời. Nếu nhiều operations giữ connection lâu, requests xếp hàng ngay ở client.

### 12.1. Phân biệt pool occupancy và pool wait

Pool có 32/32 connections bận **không tự chứng minh cấu hình sai**; nó có thể phản ánh DB chậm, requests fan-out quá nhiều hoặc pool nhỏ so với workload. Cần xem time-to-acquire, active/idle/waiting, in-flight DB operations.

### 12.2. Pool quá nhỏ

DB server còn capacity, `connection acquisition wait` tăng, tăng pool có kiểm soát làm throughput tốt hơn khi backend chịu được. Nhưng tăng vô hạn có thể tạo overload phía source.

### 12.3. Pool quá lớn

Hàng trăm pods × hàng trăm connections có thể tạo nhiều sockets, context switching, memory pressure và vượt connection limit. Cần tổng capacity across replicas.

### 12.4. Thread blocking trên async SDK

Một service dùng nonblocking driver nhưng gọi `.get()`/`.join()` trên event-loop thread có thể gây starvation. DB idle nhưng API p99 tăng. Điều tra thread dumps/traces ở JVM, không chỉ DB metrics.

### 12.5. Pool wait có thể là hậu quả

Nếu DB execution chậm từ 10 lên 1.000 ms, connections bị giữ lâu hơn và pool chờ tăng. Nâng pool chưa chắc sửa root cause; cần phân tích critical path.

## 13. Timeouts và retry: lỗi cấu hình có thể tạo load

### 13.1. Deadline theo cấp

~~~text
Client total deadline      = 2,000 ms
Gateway request deadline   = 1,800 ms
Service DB operation budget=   800 ms
DB attempt timeout         =   250 ms
Retries with backoff       = within remaining budget
~~~

Các số chỉ minh họa. Timeout phải hợp lý với SLO và các bước sau; không có công thức chung mọi ứng dụng.

### 13.2. Retry vượt deadline

Nếu SDK timeout mỗi attempt 1 giây, cho 5 retries nhưng HTTP timeout 2 giây, retries còn chạy sau khi caller đã bỏ cuộc, tăng tải vô ích nếu không có cancellation/budget.

### 13.3. Retry amplification

\[
A_{\mathrm{retry}} =
\frac{\text{số attempts thực tế}}
     {\text{số logical operations}}.
\]

10.000 logical operations tạo 25.000 attempts thì \(A_{\mathrm{retry}}=2.5\). Nhiều attempts hơn có thể là **hậu quả** của throttling nhưng cũng làm throttling trầm trọng thêm.

### 13.4. Không retry mọi lỗi

Invalid schema, unauthorized tenant, unsupported query và business conditional conflict cần logic riêng. Retry mù có thể không thành công hoặc tạo double business effects.

### 13.5. Unknown commit outcome

Write timeout không chứng minh chưa commit; retry bằng commandId mới có thể gây duplicate. Cần idempotency và authoritative outcome reconciliation, đặc biệt với payment/inventory/Order.

## 14. Consistency, write concern và “chậm vì cấu hình”

Một hệ đọc eventual replica có thể nhanh nhưng stale; một hệ đọc leader/quorum có thể chịu latency cao hơn để đáp ứng yêu cầu nhất quán.

### 14.1. Không tối ưu bằng cách làm yếu contract âm thầm

Nếu tồn kho cần atomic condition/read authoritative, đổi sang eventual reads chỉ để giảm p99 có thể làm sai nghiệp vụ. Tối ưu phải giữ nguyên correctness guarantee.

### 14.2. Write concern/durability

Write ACK sau local memory khác ACK sau durable/quorum commit. So hai cấu hình chỉ có ý nghĩa khi nói rõ mức bảo đảm và fault model.

### 14.3. Read routing

Một change cấu hình khiến reads sang secondary xa hoặc liên tục retry vì replica lag có thể tăng latency. Nhìn route metrics để phân biệt với DB CPU saturation.

### 14.4. Cross-region consensus

Một transaction cần coordination nhiều regions có lower bound network/consensus cost. Thêm vCPU một node không loại bỏ RTT và commit protocol.

### 14.5. “Lỗi” hay tradeoff có chủ đích?

Nếu cấu hình strong consistency là bắt buộc, độ trễ cao hơn có thể là chi phí hợp lệ; phải thay topology/data placement hoặc yêu cầu sản phẩm, không tự gọi nó lỗi cấu hình.

## 15. Phân vùng nóng: mô hình dữ liệu sai dù cluster còn dư

Một hệ có 16 partitions nhưng 70% writes vào `partitionKey=tenant-big`:

~~~text
Partition P7 (tenant-big): at capacity, throttled.
Other 15 partitions: mostly idle.
Cluster-wide average CPU: 30%.
API for tenant-big p99: very high.
~~~

### 15.1. Biểu hiện

Hot key, per-partition throttle, queue age, uneven CPU, conflicts và low cluster-average utilization.

### 15.2. Phân vùng theo dimension nào?

Nếu nghiệp vụ chỉ cần per-Order atomicity, partition theo chỉ `tenantId` có thể gom một tenant khổng lồ; `(tenantId,orderId)` phân tải tốt hơn, nhưng phải đánh giá query requirements.

### 15.3. Random sharding không miễn phí

Thêm shard suffix cho một counter/aggregate có thể tăng throughput nhưng làm mất khả năng atomic read/update ở một key. Cần merge/escrow/transaction design hoặc chấp nhận eventual aggregation.

### 15.4. Hot item vs hot partition

Ngay cả khi dùng hash sharding tốt, mọi writes cập nhật **một item** Inventory có thể tranh lock/CAS. Scale partitions không giảm contention trong một logical aggregate nếu invariant bắt buộc tập trung.

### 15.5. Đổi partition key là migration

Thay key ảnh hưởng indexes, backfill, routing, transaction boundary, CDC và replay. Phải thiết kế expand–migrate–contract và double-read/dual-write có kiểm soát, không đơn giản sửa một field.

## 16. Query plan và index: xem “work done per result”

Một API cần 50 Orders:

~~~text
Before:
    examined = 72 records
    returned = 50 records

After deployment:
    examined = 2,000,000 records
    returned = 50 records
~~~

Tỷ lệ `examined/returned` tăng gần 28.000 lần. Đây là tín hiệu access path đang gây việc thừa, dù disk/CPU lúc đó cũng bị bão hòa.

### 16.1. Những chỉ số hữu ích

- Keys examined / documents scanned / rows read.
- Rows/documents returned.
- Query plan (index seek, scan, filter, sort, fan-out).
- Bytes read/returned, memory for sorting, pages fetched.
- Query retries, timeout and RU/consumed read capacity.

### 16.2. Filter sau scan không giảm chi phí đọc

Một số APIs áp filters sau khi dữ liệu đã được đọc từ storage/index. Phải phân biệt **server filtering** với **access path pruning**; query trả 50 results không nói chỉ đọc 50 rows.

### 16.3. Index phù hợp filter nhưng sai sort

Index trên `tenantId` có thể lọc đúng tenant nhưng vẫn cần sort toàn bộ Order theo `createdAt DESC`. Compound index và query shape cần xem xét theo cardinality, order và access pattern.

### 16.4. Index cũng có chi phí write

Tạo thêm index có thể làm read nhanh hơn nhưng tăng storage, index maintenance và write latency. Đo cả mix trước/sau, không chỉ query nóng.

### 16.5. Index có thể tồn tại nhưng không được dùng

Kiểu dữ liệu không khớp, field expression, collations, sort order, prefix rules, planner statistics hoặc predicate shape có thể khiến planner chọn scan. Đừng kết luận “đã có index nên không phải vấn đề index”.

## 17. Ví dụ MongoDB: tìm query scan

Giả sử collection `orders` lưu:

~~~json
{
  "tenantId": "T1",
  "orderId": "O-100",
  "status": "OPEN",
  "createdAt": "2026-11-14T08:00:00Z",
  "totalMinor": 250000
}
~~~

Một query cần 50 Orders mới nhất:

~~~javascript
db.orders.find({
  tenantId: "T1",
  status: "OPEN"
}).sort({createdAt: -1}).limit(50).explain("executionStats");
~~~

### 17.1. Đọc execution plan

Xem `winningPlan`, index scan/collection scan, `totalDocsExamined`, `totalKeysExamined`, `nReturned` và execution time trong `explain`. Tên fields/plan stages có thể thay theo MongoDB version/engine.

### 17.2. Index candidate

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
~~~

Index này chỉ là candidate cho query minh họa; cần xem cardinality, read/write ratio, query predicates, sort và planner behavior thực, không tự tạo trên production mà thiếu đánh giá.

### 17.3. Thí nghiệm

So plan trước/sau, bytes examined, p99 query và write overhead với dataset đại diện, tránh so trạng thái warm-cache với cold-cache lệch nhau.

### 17.4. Không dùng `explain` như load test

`explain` kiểm một query plan và có chi phí riêng; nó không đo concurrency, GC, backup, write contention hay network SLO của toàn API.

### 17.5. Tài liệu tăng kích thước

Nếu một `Order` chứa history array tăng vô hạn, đọc/tái ghi document có thể rất đắt ngay cả khi index tốt. Khi đó phải sửa aggregate boundary.

## 18. Ví dụ DynamoDB: Query, Scan và capacity

Một ứng dụng lưu Orders trong DynamoDB. `GetItem` bằng primary key và `Query` theo partition key có chi phí khác với `Scan` trên toàn table.

### 18.1. Query đúng key

Nếu model dùng `PK=TENANT#T1`, `SK=ORDER#<id>` và cần liệt kê Orders theo time, phải chắc sort key/index hỗ trợ yêu cầu. Không tự giả định `Query` có thể lọc mọi field nhanh như indexed predicate.

### 18.2. Scan + FilterExpression

Một `Scan` kèm `FilterExpression` có thể đọc nhiều items rồi mới lọc, dẫn đến consumed capacity cao. Việc response chỉ có vài items **không** chứng minh truy cập hiệu quả.

### 18.3. Đo consumed capacity

AWS SDK có các tùy chọn trả `ConsumedCapacity`; metrics throttling, read/write capacity units và hot partition nên được quan sát. API cụ thể khác nhau theo table/index và SDK version.

### 18.4. Low CPU không loại trừ throttling

Managed service có quota/RUs/capacity, không phải lúc nào người dùng cũng thấy CPU từng partition. 429/throttling và partition key skew là tín hiệu quan trọng hơn CPU cluster trung bình.

### 18.5. Provisioning vs model

Nếu workload hiệu quả nhưng consumed capacity chạm quota, tăng capacity có thể đúng. Nếu Scan vô ích mỗi request, đổi GSI/key/query shape thường là can thiệp căn cơ hơn.

## 19. Ví dụ Cassandra/ScyllaDB: partition và tombstone

Wide-column data model thường tối ưu theo partition key và thứ tự clustering columns. Một truy vấn không đúng partition/access path có thể tạo scatter/scan.

### 19.1. Partition key quá rộng

Một tenant lớn nằm trong một logical partition với hàng triệu rows có thể làm đọc/compaction/repair không cân bằng, dù cluster còn capacity.

### 19.2. Partition quá nhỏ hoặc phân tán quá nhiều

Thêm bucketing quá mức khiến một query phải fan-out hàng nghìn buckets, tăng coordinator work và tail latency. Phân vùng cần cân bằng query locality với hotspot.

### 19.3. Tombstone-heavy reads

TTL/DELETE tạo tombstones theo semantics sản phẩm. Truy vấn đọc qua nhiều tombstones có thể chậm, kể cả không có nhiều live rows trả về. Cần đo tombstones scanned, compaction/repair và deletion patterns.

### 19.4. CQL `ALLOW FILTERING`

Không dùng `ALLOW FILTERING` như cách thay data model phù hợp; nó có thể buộc scan/filter tốn tài nguyên. Xem schema, partition key, clustering order và query thực tế.

### 19.5. Phân biệt disk saturation và mô hình

I/O cao cùng tombstone scans có thể là hậu quả của schema/TTL policy. Tăng IOPS là mitigation, còn giới hạn partition growth/bucketing/retention có thể là fix bền vững.

## 20. Ví dụ Cosmos DB: RU và cross-partition query

Cosmos DB for NoSQL thường tính chi phí operations bằng Request Units; request charge phụ thuộc query, document/index size, partitioning và nhiều điều kiện khác.

### 20.1. 429 không tự nghĩa CPU server quá cao

429 có thể là vượt RU budget hoặc giới hạn ở logical/physical partition theo cấu hình. Kiểm retry-after, request charge, throttled rate, partition skew và provisioned/autoscale settings.

### 20.2. Cross-partition fan-out

Một query thiếu partition key có thể phải gửi tới nhiều partitions. Nếu dữ liệu lớn dần, cost và p99 tăng dù query text không đổi.

### 20.3. Chọn partition key theo workload

Một partition key giúp đặt transaction/write locality nhưng phải phân phối request rate hợp lý. Không chọn key chỉ vì nó có cardinality cao nếu business query liên tục cần cross-partition coordination.

### 20.4. Indexing policy

Index tất cả paths có thể tăng write RU, nhưng bỏ index cần thiết có thể tăng query RU. Đo read/write mix, request charge và paths thực.

### 20.5. Kết luận trên cùng semantics

Đừng so queries/cost trong các consistency levels khác nhau như thể công việc giống nhau; source authority và read guarantees cần được giữ.

## 21. Ví dụ Redis: cache pressure hay hot commands?

Redis có thể là cache hoặc source of truth tùy kiến trúc. Một Redis cache chậm có thể do memory eviction, hot keys, blocking commands, network, TTL waves hoặc client connection churn.

### 21.1. Các quan sát thường gặp

~~~text
INFO memory
INFO stats
INFO commandstats
SLOWLOG GET
LATENCY LATEST
MEMORY USAGE <test-key>
~~~

Các lệnh dùng trong môi trường có quyền; thông số, cấu trúc output và các tùy chọn phụ thuộc Redis/managed-service version. Không chạy lệnh tốn kém với toàn keyspace production tùy tiện.

### 21.2. Eviction cao

`evicted_keys` tăng do memory limit có thể làm application cache miss, đẩy QPS xuống NoSQL source. Nếu root là TTL quá ngắn hoặc cache chứa một-off scan results, tăng RAM không chắc tốt bằng sửa admission/TTL.

### 21.3. Hot key

Một key phổ biến có thể saturate một primary/thread hoặc connection path. CPU trung bình Redis cluster thấp không loại trừ hot shard.

### 21.4. Blocking command

Một workload dùng các commands xử lý lượng dữ liệu rất lớn hoặc Lua script chạy lâu có thể chặn các requests khác trong scope của execution model. Điều tra slow commands/commandstats, không chỉ maxmemory.

### 21.5. Redis là nguồn dữ liệu gốc

Nếu Redis lưu trạng thái nghiệp vụ không thể tái tạo, chọn eviction policy để “cứ loại khi đầy” có thể gây mất state. Chẩn đoán performance không được đánh đổi durability/correctness.

## 22. Java service: pool, GC, HTTP và DB driver

Một trace chỉ ghi “DB call took 800ms” có thể bao gồm thời gian lấy connection, SDK retries, TLS, server execution và serialization; tên span không đủ phân rã.

### 22.1. Đo đúng boundary

~~~text
requestReceivedAt
    -> admittedAt
    -> poolAcquireStart/End
    -> dbOperationStart/End
    -> responseSerializeStart/End
    -> responseSentAt
~~~

### 22.2. Thread dumps khi nghi starvation

Nếu nhiều threads BLOCKED/WAITING trên pool/latch/event loop, việc quan sát thread dump/JFR sampling có thể xác định nơi chờ. Thu thông tin có kiểm soát, tránh full heap dump chứa PII nếu không cần.

### 22.3. Connection reuse

Không tạo MongoClient/HTTP client mới mỗi request; một client được tái sử dụng theo lifecycle đúng của SDK thường giúp quản lý connection pools và resources.

### 22.4. GC và allocations

Một query trả hàng trăm MB JSON gây heap allocation/GC; backend execution có thể nhanh nhưng response serialization chậm. Sửa projection/pagination có thể tốt hơn thêm DB nodes.

### 22.5. Reactive và blocking

Dùng reactive SDK nhưng blocking trên event-loop hoặc quá ít worker threads có thể gây starvation. Không áp quy tắc tăng thread count vô hạn; phải đo queueing, stack traces và in-flight limits.

## 23. Java Micrometer: đo latency theo operation và outcome

Ví dụ minh họa cho service có Micrometer:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.Optional;

public interface ProductSource {
    Optional<ProductView> findById(String tenantId, String productId);
}

public record ProductView(String productId, String name) {}

public final class ProductReadService {
    private final ProductSource source;
    private final MeterRegistry registry;

    public ProductReadService(
            ProductSource source,
            MeterRegistry registry) {
        this.source = source;
        this.registry = registry;
    }

    public Optional<ProductView> get(
            String tenantId,
            String productId) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";
        try {
            return source.findById(tenantId, productId);
        } catch (RuntimeException ex) {
            outcome = classify(ex);
            throw ex;
        } finally {
            sample.stop(registry.timer(
                "nosql.client.operation.duration",
                "operation", "product_get_by_id",
                "outcome", outcome
            ));
        }
    }

    private static String classify(RuntimeException ex) {
        // Replace with SDK-specific error taxonomy.
        if (ex instanceof java.util.concurrent.TimeoutException) {
            return "timeout";
        }
        return "error";
    }
}
~~~

Đoạn trên minh họa intent nhưng `TimeoutException` là checked exception, **không trực tiếp là subtype của `RuntimeException`**. Trong implementation thực, cần dùng exception hierarchy và SDK taxonomy đúng; một cách không phụ thuộc hierarchy là phân loại bằng hàm adapter nhận `Throwable`, tránh đặt `instanceof` giữa các type không thể xảy ra trong cùng nhánh compile.

### 23.1. Chọn metric labels ít cardinality

Không tag `productId`, raw tenantId, raw query string hay exception message. Dùng `operation=product_get_by_id`, `outcome=success|timeout|throttled|other`.

### 23.2. Histogram và percentiles

Micrometer registry/exporter có configuration riêng để xuất histograms/SLO buckets. Một Timer chưa tự đảm bảo backend có histogram quantiles đúng; cần setup metrics pipeline.

### 23.3. Đo thêm pool wait

Timer bọc repository call đo cả pool wait nếu driver call chờ bên trong. Muốn tách, dùng SDK pool metrics/instrumentation. Đừng tự coi timer là “DB server execution”.

### 23.4. Outcome `Optional.empty()` không nhất thiết là lỗi

Nếu không tìm thấy product là kết quả hợp lệ, `success` nên có subcategory `not_found` khi cần, không gộp tất cả vào 5xx hoặc infrastructure failure.

### 23.5. Không đưa data/credentials vào tracing

Span attributes nên là loại operation, backend, collection, requestId đã kiểm soát, tenant tier; tránh PII/complete documents/secrets.

## 24. Java: một phiên bản instrumentation có phân loại lỗi an toàn

Với checked exceptions và SDK-specific unchecked exceptions, có thể phân loại chung trên `Throwable`:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class InstrumentedDbCalls {
    @FunctionalInterface
    public interface DbOperation<T> {
        T execute() throws Exception;
    }

    public static <T> T measure(
            MeterRegistry registry,
            String operationName,
            DbOperation<T> action) throws Exception {

        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";
        try {
            return action.execute();
        } catch (Exception e) {
            outcome = classify(e);
            throw e;
        } finally {
            sample.stop(registry.timer(
                "nosql.operation.duration",
                "operation", operationName,
                "outcome", outcome
            ));
        }
    }

    private static String classify(Throwable error) {
        if (error instanceof java.util.concurrent.TimeoutException) {
            return "timeout";
        }
        // Extend with the actual MongoDB/DynamoDB/Cosmos/etc.
        // SDK exception types and stable low-cardinality categories.
        return "error";
    }
}
~~~

### 24.1. Hai timers không phải cùng một loại latency

Đo tại service wrapper khác với server profiler. Khi p99 tăng, so client timer với server execution time để suy ra pool/network/queueing.

### 24.2. Failure categories phải có semantics

Timeout, throttled, business conflict, unauthorized, validation failure và unavailable là các outcome khác nhau. Không retry tất cả giống nhau.

### 24.3. Instrumentation có chi phí

Tracing/logging mọi request với payload lớn có thể làm tăng latency; dùng sampling hợp lý và bounded labels. Instrumentation không được trở thành nguồn performance regression.

### 24.4. Các thao tác bất đồng bộ cần đo tới completion

Nếu `DbOperation` chỉ trả một `CompletableFuture`, timer dừng ngay sau khi trả future, không đo thời gian hoàn tất. Với async code, record timer trong completion callback và xử lý cancellation/exception đúng.

### 24.5. So phiên bản instrumentation

Thêm metric rồi phát hiện 10% latency mới có thể do sampling/tagging/logging. Ghi phiên bản agent/instrumentation trong incident timeline.

## 25. Traces: phân biệt chậm ở client, server hay sau commit

Một trace cho checkout:

~~~text
checkout total                    780 ms
  GET cart                         12 ms
  reserve stock                   450 ms
    pool wait                     300 ms
    DB attempt 1                   90 ms (throttled)
    backoff                        40 ms
    DB attempt 2                   20 ms (commit)
  create Order and outbox          90 ms
  serialize response               20 ms
  other orchestration             208 ms
~~~

Số liệu giả định minh họa và không nhất thiết cộng chính xác do nested/parallel spans.

### 25.1. Tìm critical path

Nếu `reserve stock` chiếm phần lớn và pool wait cao, điều tra concurrency/SDK pool. Nếu server DB attempt nhiều thời gian, xem query/partition/resource tương ứng.

### 25.2. Retry span

Một operation logic có thể có ba DB attempts. Nếu không trace attempts riêng, dễ coi một DB call 900 ms là một query chậm, trong khi nó gồm retries và backoff.

### 25.3. Correlation ID

Liên kết HTTP requestId, commandId, DB requestId, outbox eventId và async workflow ID theo quyền cho phép. Chúng giúp đối soát, không phải mọi ID đều có thể/được log trong một span.

### 25.4. Tail sampling

Các requests chậm thường hiếm, sampling ngẫu nhiên ít có thể bỏ lỡ. Dùng tail-based sampling/slow operation logs theo khả năng stack, cân bằng overhead/privacy.

### 25.5. Async completion khác HTTP ACK

POST trả 202 trong 40 ms nhưng event consumer hoàn tất sau 15 phút; trace transaction nên nối qua correlation/event IDs, metric theo `time_to_final_state` và backlog.

## 26. Triệu chứng “CPU toàn cluster thấp nhưng p99 cao”

Đừng suy ngay “database đủ tài nguyên”. Có ít nhất tám giả thuyết:

1. Một shard/partition nóng, các shards khác nhàn.
2. App connection pool hết slot.
3. Network RTT/region path quá xa.
4. Request quota/RU throttling.
5. Lock/CAS conflicts trên một aggregate.
6. Disk I/O riêng một node rất cao.
7. Replica/leader lag hoặc read routing sai.
8. Async client starvation/GC trong Java.

### 26.1. Dấu hiệu của hot partition

Latency, throttle, CPU hoặc queue chỉ tập trung ở một key range/shard. Đo theo partition hoặc sampling hot keys.

### 26.2. Dấu hiệu pool bottleneck

DB server request count thấp, app active connections đạt giới hạn, pending acquires nhiều, JVM threads WAITING. Tăng pool có giới hạn có thể giúp nếu server còn capacity.

### 26.3. Dấu hiệu network

DB execution thấp, client round-trip cao, RTT/retransmits hoặc DNS/TLS delay tăng; xem topology.

### 26.4. Dấu hiệu lock contention

Nhiều updates cùng entity, version conflicts, retries, application throughput không tăng khi thêm workers. Aggregate design/invariant scope là giới hạn.

### 26.5. Không chọn một giả thuyết trước khi đo

Tìm cùng lúc client/server timings, partition distribution, retry outcomes, request capacity và recent changes.

## 27. Khi CPU rất cao nhưng tăng CPU không phải phương án đầu tiên

Ví dụ:

~~~text
Before:
  GET orders by tenant + status
  examined=100, returned=50

After schema/query change:
  examined=500,000, returned=50
  CPU=95%, disk queue high, p99=1.5s
~~~

### 27.1. “Nhiều việc” khác “nhiều nhu cầu”

Request rate giữ nguyên, số documents examined/request tăng 5.000 lần là một đổi chi phí trên mỗi request. Cần sửa query/index trước khi tính scale.

### 27.2. Tăng CPU vẫn có thể là mitigation

Trong incident, nâng resource tạm thời để bảo vệ khách hàng có thể hợp lý nếu an toàn và có budget; nhưng nên ghi rõ **mitigation**, không gọi là root-cause fix.

### 27.3. Chứng minh bằng work-per-result

So `docsExamined`, RU, bytes read, query execution stats trước/sau theo cùng shape. Giảm nhiều lần công việc và p99 mới hỗ trợ giả thuyết index/access path.

### 27.4. Kiểm tác dụng phụ

Index mới tăng storage, write cost và maintenance. Kế hoạch fix phải kiểm read/write mix chứ không chỉ một query.

## 28. Khi thêm RAM giải quyết được và khi không

### 28.1. Trường hợp nên tăng RAM

Working set hợp lệ vừa vượt cache, page misses và physical reads tăng; cache hit ratio phục hồi khi đủ RAM; data access pattern vẫn hợp lý.

### 28.2. Trường hợp không giải quyết gốc

Query trả 5 MB không cần thiết thay vì 50 KB; document lớn vô hạn; TTL too short; scan một lần đọc toàn dataset, không có locality.

### 28.3. Đánh giá theo miss cost

Cache hit ratio 90% có thể ổn nếu 10% misses rẻ; 99% hit vẫn có thể gây p99 tệ nếu 1% misses là distributed scan. Đo origin QPS và latency.

### 28.4. Memory leak ở client

Cache local không bounded, JVM GC pause và OOM; tăng RAM chỉ kéo dài thời gian tới lỗi. Cần giới hạn entries/weights, TTL và loại retained references.

### 28.5. Benchmark cold/warm

Nếu so trước khi warm cache với sau warm cache, có thể ngộ nhận tăng RAM là nguyên nhân. Thiết kế thí nghiệm có dataset/traffic/temperature tương đương.

## 29. N+1, fan-out và phân trang

Một API lấy 100 Orders, rồi lấy từng Customer/Invoice qua 100 DB calls:

~~~text
1 query list Orders
100 queries fetch linked details
=> 101 round trips, retries, pool slots.
~~~

### 29.1. Triệu chứng

DB CPU không nhất thiết cao nhưng app pool wait/network round trips tăng, request p99 xấu khi page size tăng.

### 29.2. Nguyên nhân ở mô hình/ứng dụng

Chọn aggregate boundary, selective denormalization, batch Get, materialized read model hoặc query shape phù hợp. Không tự nhồi mọi data vào document nếu tăng growth/transaction pressure.

### 29.3. Fan-out tail amplification

API chờ chậm nhất trong N parallel reads; một tail chậm hiếm gặp ở từng shard có thể thường xuyên xuất hiện ở fan-out lớn. Tách số partitions touched/request khỏi CPU average.

### 29.4. Pagination offset vs keyset

Deep offset pagination có thể phải scan/skip nhiều records; continuation token/keyset query có thể hiệu quả hơn tùy API. Không dùng page number tùy ý khi backend không hỗ trợ ổn định.

### 29.5. Result size

Một API trả toàn bộ nested data cho list view có thể bão hòa network/JVM GC. Projection chỉ các fields cần thiết làm giảm cost ở nhiều tầng.

## 30. Tombstones, TTL và lifecycle dữ liệu

Một table lưu event/session có TTL ngắn và rate ghi lớn. Sau nhiều tuần, query đọc lịch sử chậm dù số live rows tương đối thấp.

### 30.1. Vì sao?

Deletion markers/tombstones và compaction/cleanup có thể vẫn phải được truy cập theo storage semantics. Mỗi request phải đi qua nhiều entries không còn live.

### 30.2. Dấu hiệu

Tombstones scanned, compaction backlog, disk bytes read, disk usage growth, read latency theo tuổi dữ liệu hoặc partition lớn.

### 30.3. Đây không chỉ là thiếu disk

Scale disk IOPS có thể làm nhanh hơn tạm thời nhưng nếu write/delete pattern tiếp tục tạo debt nhanh hơn compaction, lỗi sẽ quay lại.

### 30.4. Phương án thiết kế

Chia partition theo time bucket, hạn chế partition growth, chọn retention đúng, tách data nóng/lạnh, dùng TTL/deletion lifecycle phù hợp với replication/repair requirements.

### 30.5. Đừng coi physical cleanup tức thời

TTL đến hạn không luôn đồng nghĩa storage bytes giảm ngay. Monitoring cần phân biệt logical expiry và physical compaction.

## 31. Cache stampede có thể giả dạng DB thiếu tài nguyên

~~~text
10:00 Redis hot keys expire together.
10:00:01 Thousands API requests miss.
10:00:02 Origin DB requests/s x10.
10:00:03 DB CPU and p99 increase.
10:00:04 Application retries create x2 attempts.
~~~

### 31.1. Nguyên nhân gốc có thể là TTL config

Database bị quá tải thật, nhưng điểm kích hoạt là TTL đồng bộ, invalidation burst hoặc cache node restart.

### 31.2. Các metrics cần đối chiếu

Cache hit/miss, expired vs evicted keys, origin QPS, in-flight fills, retry amplification, DB resource metrics và timeline.

### 31.3. Giải pháp

TTL jitter, request coalescing/single-flight, bounded origin concurrency, prewarm có giới hạn, admission policy và timeouts hợp lý. Tăng DB capacity chỉ là một phần.

### 31.4. Cache không có authority

Cache miss không có nghĩa dữ liệu gốc bị xóa. Nếu source timeout, không cache `NOT_FOUND` từ lỗi network rồi biến outage thành mất dữ liệu giả.

### 31.5. Freshness vs availability

Stale-while-revalidate có thể hợp với catalog read, nhưng không được áp cho authorization, balance hoặc reservation quyết định mạnh nếu nghiệp vụ không cho phép.

## 32. CDC, outbox và replication: bottleneck ở sau nguồn

Một write API ACK trong 30 ms nhưng search projection bị trễ 10 phút.

### 32.1. Chậm nằm ở đâu?

Source commit rate, outbox pending age, CDC reader lag, broker backlog, consumer apply latency và index queue; không chỉ DB write p99.

### 32.2. Consumer quá ít resources

Nếu consumer CPU bão hòa, batch processing hợp lệ và partitions phân tải đều, scale workers có thể giúp tới ordering/partition limit.

### 32.3. Consumer data model sai

Một event khiến consumer chạy full collection scan để tìm các projections bị ảnh hưởng, tăng công việc trên mỗi event. Scale workers có thể làm origin quá tải; cần index/materialization hợp lý.

### 32.4. Ordering per key

Consumer không thể tùy ý parallelize events cùng aggregate nếu reducer phụ thuộc thứ tự. Hot key có thể là giới hạn kiến trúc, không phải worker count.

### 32.5. Throttling downstream

Source khỏe nhưng sink search index bị quota; retry storm và backlog tăng. Đo từng stage, không kết luận “NoSQL source chậm” từ độ trễ user nhìn thấy.

## 33. Phân loại lỗi để tránh kết luận sai

| Tình huống | Ý nghĩa | Hướng điều tra |
|---|---|---|
| Timeout trước khi gửi | Pool queue/client deadline | Client concurrency/pool |
| Timeout sau gửi read | Chưa có response trong deadline | Network/server/query/retries |
| Throttled/429 | Quota hoặc resource admission | Partition rate, RU, backoff |
| Connection reset | Đường mạng/connection lifecycle | Pool, network, failover |
| Write conflict/CAS fail | Concurrent update không đạt predicate | Hot aggregate/invariant, retry |
| Business rejection | Out of stock/invalid transition | Đúng nghiệp vụ hay input bug? |
| Not found | Authoritative absence theo contract | Key, replica consistency, deletion |
| Out-of-memory | Heap/native/cache/DB memory | Scope, allocation, bounds |
| Unsupported query/schema | Contract/config/model sai | Không retry như transient |
| Unknown commit result | ACK mất nhưng commit có thể đã xảy ra | Stable commandId, reconciliation |

### 33.1. Business conflict không là hệ hỏng

Hai requests reserve cùng SKU có thể tạo một committed, một rejected đúng nghiệp vụ. Không tăng DB pool tới vô hạn chỉ vì CAS conflicts.

### 33.2. Throttle khác 500

Server có thể chủ ý từ chối để giữ an toàn. Client cần bounded backoff/rate limit, không spam retries rồi ghi là “DB down”.

### 33.3. Unknown outcome không đồng nghĩa failed write

Sau timeout, kiểm commandId/receipt tại source để tránh double apply. Monitoring cũng cần phân biệt `pending_unknown` khỏi `rolled_back`.

### 33.4. Lỗi parse/schema có thể do rollout

Reader cũ gặp schemaVersion mới có thể fail, không liên quan CPU/RAM. Sửa compatibility/migration, không scale.

### 33.5. Luôn lưu phân loại outcome

Một metric `errors=1000` không nói có 900 expected business rejects hay 900 infra timeouts. Taxonomy là phần quan trọng của diagnosis.

## 34. Little's Law và queueing khi tải gần giới hạn

Định luật Little trong hệ ổn định:

\[
L = \lambda W,
\]

với \(L\) là số công việc trung bình trong hệ, \(\lambda\) là arrival/completion rate phù hợp trong steady state, \(W\) là thời gian trung bình.

Nếu 1.000 requests/giây và end-to-end average latency 0,1 s:

\[
L \approx 1{,}000 \times 0.1 = 100
\]

requests đang đồng thời trong hệ.

### 34.1. Nhiều concurrency có thể là hậu quả

Latency tăng làm in-flight requests tăng dù offered rate không đổi. Thread/pool exhaustion có thể đến **sau** khi query chậm, không nhất thiết là gốc.

### 34.2. Mô hình hàng đợi lý tưởng

Trong mô hình M/M/1 lý tưởng, expected response time là \(W=1/(\mu-\lambda)\), với \(\lambda<\mu\). Khi \(\lambda\) tiến gần service rate \(\mu\), \(W\) tăng phi tuyến. Đây là mô hình minh họa, **không phải công thức chính xác cho NoSQL cluster có shards/retries/replication**.

### 34.3. Vì sao tăng tải một ít có thể gây p99 tăng rất nhiều?

Khi bottleneck gần capacity, queueing time áp đảo service time. Cần tìm queue tại CPU, disk, pool, quota hoặc hot partition; không suy từ RPS tăng 10% mà latency chỉ được phép tăng 10%.

### 34.4. Không dùng p99 thay mean trong Little's Law

Phương trình trên nói về averages trong điều kiện xác định; lấy p99 × rate để suy chính xác concurrency là sai.

### 34.5. Overload control

Bounded queue, rate limiting, backpressure, deadlines và load shedding có thể giữ hệ ổn định. Mục tiêu không phải xử lý mọi attempt nếu điều đó làm tất cả requests timeout.

## 35. Quy trình điều tra sự cố theo giả thuyết

Một cách tiếp cận có thứ tự:

1. **Xác định tác động:** endpoint, SLO, tenants, regions, operations bị ảnh hưởng.
2. **Chốt khoảng thời gian:** trước/sau, duration và mốc change.
3. **Phân biệt outcome:** successful, timeout, throttled, business reject, conflict.
4. **Kiểm offered và achieved load:** request rate, attempts, retry amplification.
5. **Đọc traces:** critical path, pool wait, network, server execution, async backlog.
6. **Kiểm client JVM:** CPU throttle, heap/GC, thread starvation, pool metrics.
7. **Kiểm resource server:** CPU/IO/memory/network per node/shard/partition.
8. **Kiểm quota:** RU/RCU/WCU/throttle, per-partition limits.
9. **Kiểm query work:** explain/query plan, scanned vs returned, bytes and index use.
10. **Kiểm dữ liệu:** sizes, hot key, partitions, tombstones, schema versions.
11. **Kiểm phụ thuộc:** cache, CDC, outbox, search, replicas và external services.
12. **Nêu giả thuyết và phản chứng:** mỗi hypothesis có metric dự đoán.
13. **Mitigate an toàn:** rate limit, rollback config, tạm tăng capacity nếu cần.
14. **Thí nghiệm kiểm soát:** staging/canary, một biến, có baseline.
15. **Kiểm correctness:** giữ transaction/consistency/idempotency/invariants.
16. **Đo sau sửa:** p99, errors, resource cost, queue/CDC lag và regression.
17. **Ghi kết luận:** gốc, tác nhân góp phần, evidence, fix và prevention.

### 35.1. Mỗi giả thuyết phải tạo ra dự đoán kiểm được

Ví dụ: “Pool nhỏ làm chậm.” Dự đoán: pool wait cao, DB còn dư, tăng pool từ 32 lên 48 trên canary giúp throughput/p99 tới ngưỡng backend. Nếu pool wait thấp, giả thuyết yếu.

### 35.2. Tránh “chẩn đoán bằng dashboard một ảnh”

Một ảnh CPU 95% tại 10:05 không cho biết CPU tăng trước hay sau retries. Phải đồng bộ timeline và request distributions.

### 35.3. Trong incident ưu tiên tính an toàn

Rollback query mới hoặc giảm tải có thể giảm tác động trước khi điều tra đầy đủ. Nhưng không tắt consistency, xóa dữ liệu hoặc thay partition policy trên production tùy tiện.

## 36. Ma trận giả thuyết và phép kiểm

| Giả thuyết | Bằng chứng cần tìm | Thí nghiệm an toàn |
|---|---|---|
| Thiếu CPU | CPU throttle/run queue tại node nghẽn, service time cao | Đo utilization và thử capacity phù hợp trên canary |
| Pool quá nhỏ | Pending acquire nhiều, DB còn dư | Tăng pool có giới hạn trên staging/canary |
| Retry storm | Attempts/logical op tăng, throttling/latency nối tiếp | Giảm retry budget/jitter, đo origin QPS |
| Index sai | Examined/returned tăng, scan/sort | Explain và thử index trên dataset đại diện |
| Partition key nóng | Per-key/per-shard skew, conflict/throttle | Workload hot-key sandbox, xem routing distribution |
| TTL/cache stampede | Expirations/misses tăng trước origin QPS | TTL jitter, coalescing, prewarm test |
| Compaction debt | Write throughput cao kéo dài, backlog/disk latency | Soak test cùng retention/schema |
| Quota quá thấp | 429 và capacity consumption, query cost hợp lý | Controlled capacity increase và cost tracking |
| Remote network | Server time thấp, client RTT cao | So same-region vs cross-region paths |
| Document growth | Payload bytes/allocations tăng, large hot docs | Bounded projection/schema refactor thử nghiệm |
| CDC consumer chậm | Outbox backlog/feed lag, source write bình thường | Scale/optimize consumer trong test |
| Consistency tradeoff | Latency gắn strong/quorum path | Kiểm topology/protocol; không giảm guarantee vô thức |

### 36.1. Đừng thay nhiều thứ một lần nếu muốn biết nguyên nhân

Scale node, tạo index, đổi TTL và tăng pool cùng lúc có thể phục hồi SLO nhưng không biết phần nào đã sửa root cause. Trong incident có thể mitigate đa biện pháp; sau đó tách experiment có kiểm soát.

### 36.2. Chọn chỉ số chống giả thuyết

Nếu nghi thiếu disk nhưng disk latency không tăng, còn pool wait cao, cần sửa trọng số giả thuyết.

### 36.3. Kết quả âm tính cũng có ích

Thêm RAM không đổi miss ratio/p99 giúp loại bỏ giả thuyết working-set pressure trong điều kiện test đó; không cần gọi thí nghiệm “thất bại”.

## 37. Case study: chậm sau khi thêm bộ lọc trạng thái

Ứng dụng thêm endpoint:

~~~text
GET /orders?tenantId=T1&status=OPEN&sort=createdAtDesc
~~~

Trước đây lấy theo `orderId`. Sau deploy, p99 tăng, DB CPU 95%, disk read tăng.

### 37.1. Quan sát đầu tiên

Throughput requests gần bằng trước, nhưng CPU/request tăng; DB profiler thấy scan hàng trăm nghìn records để trả 50.

### 37.2. Giả thuyết

Index đang chỉ hỗ trợ primary key, không phù hợp tenant+status+createdAt sort.

### 37.3. Kiểm chứng

Dùng explain, so scanned/returned, query shape, index candidate, read/write overhead. Thử trên staging với phân phối tenant/record sizes thực tế.

### 37.4. Can thiệp

Thiết kế index/read model hoặc partition-key access path phù hợp. Nếu business chỉ cần recent Orders, có thể xây projection bounded. Không nhất thiết tăng vCPU liên tục.

### 37.5. Bài học

Resource saturation là **hậu quả đo được**, còn nguyên nhân gốc là **truy vấn/mô hình truy cập**.

## 38. Case study: CPU thấp nhưng tenant lớn bị throttle

Một SaaS có 12 shards. Tenant A chiếm 75% writes, partition key chỉ là tenantId.

### 38.1. Triệu chứng

Tenant A p99 > 3 s và throttled nhiều, tenants khác ổn. CPU trung bình cluster 25%.

### 38.2. Phân tích

Tenant A dồn vào một logical/physical partition hoặc một phần hot keyspace, giới hạn local capacity; các shards khác nhàn rỗi.

### 38.3. Giải pháp tạm thời

Rate limit/batch theo tenant, tăng capacity phù hợp nếu platform cho phép, tránh retry storm; giảm user impact.

### 38.4. Giải pháp dài hạn

Thiết kế partition key theo `(tenantId,entityId)` hoặc bucket phù hợp access pattern/invariant; cân nhắc tenant isolation/dedicated resources. Đánh giá migration và secondary queries.

### 38.5. Bài học

**Global utilization thấp không loại trừ local saturation**. Mọi phép đo capacity cần một đơn vị phân vùng rõ.

## 39. Case study: connection pool làm DB có vẻ chậm

Service Java nhận 3.000 requests đồng thời. Pool tối đa 16 connections, server QPS thấp, pool acquire p99 900 ms.

### 39.1. Giả thuyết ban đầu

“Database chậm” vì repository method mất 1 giây.

### 39.2. Bằng chứng mới

Server execution p99 chỉ 20 ms, pool wait chiếm 900 ms; CPU DB thấp.

### 39.3. Can thiệp

Tune pool size bounded, reduce N+1 calls, set application concurrency budgets, kiểm connections per pod × số pods.

### 39.4. Rủi ro

Tăng pool lên 500 trên 100 pods có thể làm server connection limit và CPU sụp. Cần capacity test và rate limit.

### 39.5. Bài học

Latency ở phương thức “DB call” không chắc là **thời gian DB xử lý**.

## 40. Case study: compaction và TTL tích lũy

Một workload ghi events có TTL 7 ngày, nhiều deletes, luôn tốt trong 5 phút load test nhưng chậm sau vài tuần.

### 40.1. Chỉ báo

Compaction backlog, disk bytes read/write, tombstones scanned tăng; p99 theo read queries già đi.

### 40.2. Không nhầm với traffic bất thường

Request rate có thể không đổi. Work per request tăng do dataset lifecycle và storage debt.

### 40.3. Fix

Xem time bucketing/partition width, TTL/delete patterns, compaction strategy theo vendor và retention; đồng thời đánh giá disk IOPS như mitigation.

### 40.4. Đo lại

So soak benchmark với dữ liệu được “làm già” đại diện, không chỉ seed dataset fresh.

### 40.5. Bài học

Benchmark ngắn trên dữ liệu mới không phản ánh storage lifecycle NoSQL.

## 41. Case study: Redis TTL wave làm NoSQL quá tải

Redis cache được nạp đồng loạt với TTL 5 phút. Đúng phút thứ năm, 90% hot keys expire.

### 41.1. Triệu chứng

Redis expired keys/s và cache miss tăng trước, NoSQL source QPS tăng x10 sau, DB CPU cao và timeout.

### 41.2. Giả thuyết sai

“Database vốn thiếu CPU nên phải scale gấp 10.”

### 41.3. Nguyên nhân chính

TTL đồng bộ và cache stampede; Java retries làm khuếch đại requests.

### 41.4. Fix

TTL jitter, single-flight, bounded origin concurrency, selective warming, appropriate stale fallback cho data cho phép, và sizing nguồn để chịu miss bursts hợp lý.

### 41.5. Bài học

Một resource có thể bị quá tải thật do **cấu hình tầng trước** tạo ra tải bất thường.

## 42. Dashboard tối thiểu cho NoSQL chẩn đoán

| Nhóm | Dashboard/metric |
|---|---|
| User-facing | RPS, 4xx/5xx, timeout, p50/p95/p99, business success |
| Client SDK | Pool wait/active, in-flight, retries, connection errors |
| JVM | CPU/throttling, heap/non-heap, GC, thread pool queues |
| Database nodes | CPU, memory, IOPS, bytes read/write, disk/network latency |
| Partition/shard | Hot keys, requests/partition, per-shard saturation |
| Managed quota | RU/RCU/WCU consumed, throttled, provisioned/autoscale |
| Query | Slow query rate, examined/returned, index use, fan-out |
| Storage lifecycle | Compaction debt, tombstones, TTL, cache hit/miss |
| Replication | Replica lag, quorum failures, failover state |
| Cache | Evictions, expirations, hit ratio, fill concurrency |
| Async | Outbox backlog, CDC lag, consumer delay, DLQ |
| Correctness | Version conflicts, idempotency, lost updates, stale results |
| Cost | RU, IO, storage growth, network egress per successful operation |

### 42.1. Tạo link giữa tầng

Một biểu đồ cache miss nên hiển thị cùng origin QPS và DB p99; một biểu đồ retries nên đi cùng throttle. Tách màn hình quá nhiều có thể làm mất causal timeline.

### 42.2. Đơn vị rõ ràng

Bytes/s khác requests/s, CPU core-seconds khác percent, latency ms khác µs, RU/s khác consumed RUs một request. Label sai đơn vị có thể làm sai kết luận.

### 42.3. Histogram và sample count

Một percentile trên rất ít samples thiếu ổn định. Báo count và cách tính/export histograms.

### 42.4. Alert theo SLO và capacity

Evictions/s tăng không phải lúc nào cũng là incident. Alert khi kéo theo origin latency/throttling hoặc freshness issue.

### 42.5. Chống cardinality explosion

Không tag mọi `orderId`/`sku`/raw tenantId thành timeseries; dùng traces/sampled logs có quyền để điều tra hot identities.

## 43. Thí nghiệm phân biệt thiếu tài nguyên và data-model mismatch

### 43.1. Giữ workload cố định, đổi resource

Test A: cùng dataset/query mix, CPU/RAM/IO capacity khác. Nếu latency giảm theo resource khi bottleneck saturates, capacity là một yếu tố.

### 43.2. Giữ resource cố định, đổi access path

Test B: cùng load, đổi index/query plan, đo `examined/returned`, RU/IO, p99 và write overhead. Nếu work/request giảm sâu, model/query là điểm quan trọng.

### 43.3. Giữ backend, đổi cấu hình pool

Test C: 16/32/64 client connections với concurrency bounded, đo pool wait, backend CPU và p99. Tìm vùng tăng pool còn giúp, không vượt backend capacity.

### 43.4. Thử skew

Test D: uniform keys vs hot 1% keys, cùng total RPS. Nếu hot workload sụp sớm, đó là dấu hiệu partition/lock/aggregate bottleneck.

### 43.5. Chạy đủ lâu

Compaction/TTL debt và autoscaling cần thời gian. Chạy step/ramp/soak với dữ liệu đại diện; báo repeatability, offered vs achieved rate và fault outcomes.

## 44. Phương pháp dùng số liệu để phân biệt ba nhóm

Một thí nghiệm có thể cho:

| Trường hợp | CPU tại shard nghẽn | Scanned/returned | Pool wait | p99 | Gợi ý |
|---|---:|---:|---:|---:|---|
| A | 99% | 1,02 | 3 ms | 700 ms | Capacity có thể là nguyên nhân |
| B | 97% | 20.000 | 4 ms | 1.500 ms | Query/index gây công việc thừa |
| C | 35% | 1,01 | 850 ms | 950 ms | Client pool/config |
| D | Cluster 30%, một partition hot | 1,04 | 8 ms | 1.200 ms | Data partition skew |

**Số trong bảng là dữ liệu giả định minh họa**, không phải số đo hệ thống cụ thể.

### 44.1. Nhận diện capacity thật

Nếu queries hiệu quả, load cao, tài nguyên cụ thể saturates và scale giúp giữ SLO cùng semantics, tăng capacity có cơ sở.

### 44.2. Nhận diện config issue

Nếu server còn dư nhưng pool wait/timeout/retry/route config gây delay, tune configuration và verify tương quan.

### 44.3. Nhận diện model issue

Nếu work per result quá lớn hoặc hot partition/aggregate contention, sửa key/index/document/aggregation workflow. Scale có thể giảm triệu chứng nhưng không loại nguyên nhân.

### 44.4. Rất thường có chuỗi nhân–quả kết hợp

Ví dụ query scan sai → I/O saturation → timeout → retries → pool exhaustion. Chẩn đoán phải viết **chuỗi**, không ép thành duy nhất một nhãn.

## 45. Mẫu incident report ngắn nhưng có bằng chứng

~~~yaml
incident:
  id: "nosql-p99-incident-example"
  scope: "GET /orders by tenant/status"
  start: "2026-11-14T10:00:00Z"
  impactedTenantTier: "shared-high-volume"

impact:
  p99BeforeMs: 100
  p99DuringMs: 1700
  timeoutRate: "8%"
  businessInvariantViolations: 0

observations:
  requestRateChange: "none significant"
  clientPoolWait: "normal"
  databaseCpu: "high on two shards"
  docsExaminedPerResult: "increased dramatically"
  diskReadBytes: "increased"
  latestChange: "new filter/sort query"

hypotheses:
  - "Query not using suitable index"
  - "Insufficient disk IOPS"
  - "Hot tenant partition"

mitigation:
  action: "disable costly query path behind feature flag"
  result: "p99 recovered"

rootCause:
  type: "data-model/access-path mismatch"
  evidence: "execution plan and scanned/returned"

followUp:
  - "evaluate index/read-model design"
  - "test with representative tenant distribution"
  - "add query work-per-result alert"
  - "validate write/index maintenance cost"
~~~

Mẫu này không là chứng cứ đã xảy ra sự cố. Thay các trường bằng logs, traces và thời gian thực trước khi dùng trong postmortem.

## 46. Các ngộ nhận dễ dẫn đến sửa sai

### “CPU cao nên cứ tăng CPU”

Không đủ. CPU cao có thể do scan sai, retry storm, GC hoặc indexing overhead.

### “CPU trung bình cluster thấp nên không thiếu tài nguyên”

Sai. Một partition, primary shard, disk hoặc quota có thể bão hòa riêng.

### “Không thấy 100% CPU thì DB chưa bão hòa”

Sai. I/O, locks, per-partition quotas và network có thể nghẽn trước.

### “Pool đầy chứng minh pool config sai”

Không. DB chậm làm connections bị giữ lâu, pool đầy là hậu quả.

### “Tăng pool luôn làm nhanh”

Không. Có thể làm backend quá tải và tăng timeouts.

### “Retry giúp tăng reliability nên retry vô hạn”

Sai. Retry storm tăng offered load, có thể double-apply khi outcome unknown.

### “429 nghĩa database lỗi nghiêm trọng”

Không hẳn. Nó có thể là admission/throttling theo quota; cần phân loại.

### “Query trả 50 rows chắc chỉ đọc 50 rows”

Sai. Filter/scan có thể examined hàng triệu rows.

### “Có index nghĩa query chắc chắn dùng index”

Không. Phải xem execution plan và query shape.

### “Tăng RAM sẽ chữa mọi scan”

Không. Đọc quá nhiều records vẫn tốn CPU, network, RU và gây contention.

### “NoSQL không có schema nên không thể sai mô hình dữ liệu”

Sai. Partition/access patterns, document boundaries và consistency contracts là schema ngữ nghĩa.

### “Partition key có nhiều giá trị là đủ tốt”

Không. Cần xét phân phối lưu lượng, hot keys và query locality.

### “Không có deploy nghĩa không có regression”

Không. Dữ liệu lớn lên, TTL/tombstones tăng, tenant mix đổi hoặc cache cold cũng gây regression.

### “Latency repository method chính là DB execution”

Không. Có thể gồm pool wait, retries, network và mapping.

### “Timeout của write nghĩa chưa commit”

Không. Cần reconcile stable commandId/outcome.

### “Stale read là do performance chậm”

Chưa chắc. Có thể do consistency/replication/invalidation semantics.

### “Cache miss nghĩa bản ghi ở nguồn không còn”

Không. Cache miss khác authoritative NOT_FOUND.

### “Compaction debt là vấn đề disk đơn giản”

Có thể là lifecycle/retention/schema làm tích lũy công việc.

### “Tăng shard count tự sửa hot item”

Không nếu một logical aggregate vẫn nhận mọi writes và yêu cầu atomicity.

### “Một p99 sau tối ưu đủ chứng minh đã sửa”

Không. Cần so cùng workload, nhiều windows/trials, invariant và resource cost.

### “Benchmark CRUD là benchmark toàn workflow”

Không. Checkout có CAS, outbox, CDC, retries và downstream state.

### “Chỉ cần throughput tăng là tốt”

Không nếu p99, error rate, cost hoặc correctness xấu đi.

## 47. Checklist chẩn đoán trước khi thay đổi production

1. Đã mô tả **triệu chứng người dùng** và SLO chưa?
2. Đã phân tách **read/write/scan/transaction** chưa?
3. Đã chia theo **tenant, partition, shard, region** chưa?
4. Đã đối chiếu **timeline deploy/data changes** chưa?
5. Đã biết **offered vs achieved requests** chưa?
6. Có thấy **retry amplification** và throttled rate không?
7. Trace có **pool wait, network, execution, serialization** không?
8. Đã xem **JVM GC/throttling/thread starvation** chưa?
9. Resource saturation được đo ở **đúng node/key scope** chưa?
10. Query plan có **scan/examined/returned** không?
11. Đã xem **index/filter/sort access path** chưa?
12. Có **hot partition/aggregate conflict** không?
13. Dataset có **large documents, tombstones, growth** không?
14. Có **cache expiry/stampede** trước incident không?
15. Có **CDC/outbox/replica lag** và async backlog không?
16. Timeouts/retries/deadlines có hợp logic không?
17. Read/write **consistency và durability** có bị đổi không?
18. Có một giả thuyết kèm **dự đoán phản chứng** không?
19. Mitigation có an toàn cho **data integrity** không?
20. Thí nghiệm có **baseline, một biến, dataset** tương đương không?
21. Đo sau fix gồm **p99, errors, resource, cost** không?
22. Có kiểm **business outcomes** và no lost updates không?
23. Có kế hoạch **rollback/roll forward** phù hợp không?
24. Có ghi **root cause vs contributing factors** rõ không?

## 48. Bài tập thực hành

### Bài 1 — CPU toàn cluster thấp

Cluster có bốn shards CPU lần lượt 98%, 20%, 25%, 17%; p99 tăng với tenant A. Chỉ ra tại sao CPU average không loại trừ thiếu capacity và metrics cần theo dõi.

### Bài 2 — Pool wait

Java service `getOrder()` mất 1 giây, trong đó 900 ms là chờ connection, DB execution 20 ms. Đề xuất giả thuyết, số liệu cần lấy và giải pháp có giới hạn.

### Bài 3 — Index scan

Một query trả 100 records nhưng scanned 5 triệu documents. Giải thích vì sao thêm index/read model có thể tốt hơn tăng CPU; nêu cách kiểm bằng explain.

### Bài 4 — Write-heavy CPU

CPU DB 95%, throughput không tăng dù giảm request rate nhẹ. Hãy phân biệt CPU thiếu thật, compaction và retry storm bằng metrics/time series.

### Bài 5 — Memory pressure

RSS 90% RAM nhưng cache hit tốt và không swap/eviction. Có đủ kết luận thiếu RAM không? Liệt kê quan sát còn thiếu.

### Bài 6 — JVM GC

DB server khỏe, API p99 tăng cùng GC pause và allocations. Thiết kế cách điều tra document sizes, serialization, in-process cache và thread dumps.

### Bài 7 — Disk 100%

Disk utilization cao khi mới thêm query lọc status, examined/result x100. Phân tích nguyên nhân gốc và mitigation.

### Bài 8 — LSM compaction

Một workload chạy nhanh trong 10 phút nhưng chậm sau 4 giờ. Thiết kế soak test và metrics compaction debt/tombstones cần theo dõi.

### Bài 9 — Managed RU throttling

Cosmos DB báo nhiều 429, CPU server không hiển thị. Cần đo request charge, RU budget, partition distribution và backoff như thế nào?

### Bài 10 — DynamoDB Scan

Một Lambda gọi Scan+FilterExpression cho 10 kết quả nhưng đọc nhiều items. Giải thích vì sao tăng RCU có thể không phải fix căn cơ.

### Bài 11 — MongoDB explain

Viết query `tenantId,status,createdAt DESC`, dùng `explain("executionStats")`, nêu metrics và index candidate cần đánh giá.

### Bài 12 — Cassandra tombstone

Table session nhiều TTL, số live rows thấp nhưng query chậm. Liệt kê thông tin tombstones/compaction/schema cần thu thập.

### Bài 13 — Partition key

Một tenant tạo 70% writes và key chỉ là tenantId. Phân tích hot partition, đổi key và tradeoff transaction/query.

### Bài 14 — Hot aggregate

Một InventoryItem nhận hàng nghìn conditional decrements/giây. Tại sao thêm shards không tự giải quyết? Đề xuất authority/escrow nếu phù hợp.

### Bài 15 — Timeout ladder

Gateway timeout 2s, service timeout 5s, SDK attempt 3s × 3 lần. Chỉ ra bất hợp lý và thiết kế budget an toàn.

### Bài 16 — Retry amplification

10.000 logical operations tạo 30.000 attempts. Tính amplification và phân tích vì sao retry có thể làm throttling tăng.

### Bài 17 — Unknown commit

Một Order write timeout sau commit, service retry với commandId mới. Giải thích rủi ro duplicate và xây flow reconciliation.

### Bài 18 — Replica lag

Read replica có latency thấp nhưng user không thấy update vừa commit. Đây là thiếu CPU hay consistency mismatch? Thiết kế read-your-writes kiểm chứng.

### Bài 19 — Network

DB execution p99=10ms nhưng client p99=250ms qua cross-region link. Lập phương án đo RTT, TLS, retransmits và topology.

### Bài 20 — N+1

Endpoint list 100 Orders tạo 101 DB calls. Đề xuất batching/read model/projection, đo pool wait và network RTT trước–sau.

### Bài 21 — Fan-out

Một API gửi 32 parallel shard requests rồi chờ tất cả. Vì sao tail amplification có thể tăng p99 ngay cả khi mỗi shard p99 tương đối thấp?

### Bài 22 — Cache stampede

Redis hot keys expire cùng thời điểm, origin QPS x10, CPU database cao. Thiết kế timeline chứng minh root ở TTL/cache, cùng giải pháp jitter/coalescing.

### Bài 23 — Redis hot command

Một command xử lý key rất lớn xuất hiện trong slowlog. Vì sao tăng Redis maxmemory không luôn giảm latency? Nêu cách sửa key/data model.

### Bài 24 — CDC backlog

DB commit nhanh, outbox oldest age tăng, sink consumer 100% CPU. Phân biệt thiếu consumer capacity với projection query làm quá nhiều công việc.

### Bài 25 — Tenant fairness

Tenant A spike làm tenant B p99 tăng. Thiết kế noisy-neighbor test và cách đo per-tier QoS/throttling.

### Bài 26 — CPU throttling

Container CPU limit thấp, host còn CPU nhàn. Phân biệt với database CPU saturation bằng metrics throttled periods, JVM performance và node utilization.

### Bài 27 — Java Micrometer

Tạo Timer cho `getProduct`, phân loại outcomes `success`, `timeout`, `throttled`, `other`; chọn low-cardinality labels và giải thích vì sao không tag productId.

### Bài 28 — Tracing

Thiết kế trace chia HTTP, pool wait, SDK attempts, DB server, JSON serialization và async completion. Vì sao tổng durations của nested spans không bằng end-to-end?

### Bài 29 — Thí nghiệm pool

Giữ cùng workload và backend, thử pool 16, 32, 64 connections. Nêu metrics để xác định tăng pool có giúp hay chỉ làm backend overload.

### Bài 30 — Thí nghiệm index

Giữ tài nguyên/traffic cố định, thử query plan trước/sau index. Đo scanned/returned, p99 read, write amplification và storage cost.

### Bài 31 — Capacity vs query model

Hệ A có CPU 99%, scanned/returned=1,05; hệ B CPU 99%, scanned/returned=20.000. Đề xuất ưu tiên xử lý của hai hệ và phương án kiểm chứng.

### Bài 32 — Lỗi schema

Sau rolling deploy, reader Java cũ không nhận biết enum mới. CPU/RAM bình thường nhưng 5xx tăng. Đây là nhóm nguyên nhân nào? Đề xuất compatibility strategy.

### Bài 33 — NoSQL write consistency

Nhóm đề xuất đổi majority durable write sang local ACK để giảm p99. Giải thích vì sao đây không phải tối ưu tương đương nếu nghiệp vụ yêu cầu durability.

### Bài 34 — Incident report

Tự tạo một timeline trước–sau release cho p99 tăng, một query plan sai, disk queue cao và timeout retries. Viết report phân biệt root cause, contributing factors, mitigation và long-term fix.

### Bài 35 — Soak benchmark

Lập kế hoạch test 6 giờ cho hệ có TTL, CDC, backup, multi-tenant hot keys; nêu dataset, offered rate, telemetry, fault rules và correctness gates.

### Bài 36 — Tổng hợp tình huống

Hệ có `GET /orders` p99=2s, cluster average CPU=35%, một shard CPU=98%, Redis miss ratio tăng, client attempts/request=3, query scanned/result=10.000. Hãy xây ít nhất ba chuỗi nhân–quả khả dĩ, metric phản chứng cho mỗi chuỗi và kế hoạch mitigation không đánh đổi correctness.

---

**Kết luận:** Chẩn đoán NoSQL cần đi xa hơn câu hỏi “có thiếu CPU/RAM không?”. **Thiếu tài nguyên** là một trạng thái capacity có thể đo được ở CPU, disk, network, memory, pool hoặc quota, nhưng nó có thể là **hậu quả** của retry, query scan, hot partition hay data lifecycle sai. **Lỗi cấu hình** thường bộc lộ qua pool waits, timeouts/deadline không hợp lý, routing, cache TTL, quotas hoặc consistency settings. **Lỗi mô hình dữ liệu** xuất hiện khi partition key, aggregate boundary, index/query shape, document growth hay cách xử lý TTL/tombstone không khớp access pattern. Hãy bắt đầu bằng **tác động user và SLO**, tách client/server/async latency, đối chiếu RED và USE theo đúng phạm vi, xem **work per request** và phân phối khóa, tạo **giả thuyết có thể bác bỏ**, rồi đo lại sau can thiệp trong khi giữ nguyên **correctness, durability và business invariants**. Mục tiêu không phải làm một biểu đồ CPU đẹp hơn, mà là đưa hệ thống về trạng thái phục vụ đúng, ổn định và có chi phí kiểm soát được.
