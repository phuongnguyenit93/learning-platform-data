# Đo độ trễ, thông lượng và mức dùng tài nguyên trên tải tương đương

Trong **Java Advance Compatibility Migration**, nâng JDK có thể làm thay đổi hiệu năng dù chức năng nghiệp vụ vẫn đúng. Ứng dụng chạy trên JDK mới có thể giảm thời gian GC nhưng tăng CPU, cải thiện throughput ở tải vừa nhưng làm p99 latency tệ hơn ở tải cao, hoặc giảm heap usage trong khi tổng memory của container tăng vì thread stacks, code cache và native allocations. Vì vậy, việc ứng dụng khởi động được và bộ test chức năng đều xanh chưa đủ để kết luận migration đạt yêu cầu.

Bài **Đo độ trễ, thông lượng và mức dùng tài nguyên trên tải tương đương** thuộc chương **JVM và hiệu năng** hướng dẫn thiết kế một phép so sánh đáng tin cậy giữa **baseline** (JDK/runtime hiện tại) và **candidate** (JDK/runtime mục tiêu). Trọng tâm là giữ hai bên nhận cùng loại yêu cầu, lưu lượng đến, phân bố dữ liệu, điều kiện tài nguyên và phương pháp đo; sau đó đánh giá phân phối latency, successful throughput, CPU, memory, GC, lỗi và khả năng vận hành dài hạn.

Không thể kết luận một JDK nhanh hơn chỉ vì một câu số liệu như “cải thiện 15%”. Một phát biểu có giá trị kỹ thuật cần kèm workload, mức tải, SLO, cấu hình JVM, tài nguyên, số lần đo và mức biến thiên. Mục tiêu cuối cùng là **quyết định có thể review được**: tiếp tục rollout, điều chỉnh cấu hình, điều tra regression hay rollback.

## 1. Xác định câu hỏi hiệu năng cần trả lời

Trước khi chọn công cụ benchmark, hãy xác định câu hỏi cụ thể:

- Với cùng traffic và request mix, người dùng chờ nhanh hơn hay chậm hơn?
- Bản mới xử lý được bao nhiêu **giao dịch thành công** mỗi giây?
- Tại mức tải nào p95/p99 latency hoặc tỷ lệ lỗi vượt SLO?
- CPU consumption trên mỗi request thành công có thay đổi không?
- Heap, RSS, native memory, thread count và GC pressure có tăng?
- Startup, warm-up, long-running behavior và headroom ra sao?
- Khác biệt đến từ JDK, GC defaults, framework, database hay môi trường đo?
- Nếu rolling deployment, dữ liệu từ production canary có cùng workload với baseline?

Các phép đo thường thuộc nhiều cấp:

| Cấp độ | Mục tiêu | Metric thường dùng |
|---|---|---|
| Microbenchmark | So một thuật toán hoặc Java API | ns/op, ops/s, B/op |
| Component benchmark | So một module hoặc adapter | operations/s, latency, allocations |
| Service benchmark | So một ứng dụng JVM hoàn chỉnh | p50/p95/p99, success RPS, CPU, RSS, GC |
| End-to-end benchmark | So trải nghiệm qua network và dependencies | E2E latency, errors, retries |
| Capacity test | Tìm giới hạn trong ngân sách SLO | Max sustainable throughput |
| Soak test | Tìm leak, drift, vấn đề lâu dài | RSS trend, heap-after-GC, latency trend |

**Không dùng microbenchmark để thay service test**. Một thay đổi cải thiện tốc độ xử lý chuỗi 20% có thể gần như không tác động nếu 95% thời gian request dành cho truy vấn database.

## 2. Định nghĩa latency và ranh giới đo

**Latency** là thời gian operation diễn ra giữa hai mốc được định nghĩa. Đối với HTTP service cần phân biệt:

1. **Client-observed response time:** từ khi client gửi request đến khi nhận đủ response theo hợp đồng.
2. **Server request handling time:** thời gian trong app server, có thể không bao gồm network hoặc queue ở gateway.
3. **Downstream latency:** thời gian gọi database, broker, HTTP API khác.
4. **Queueing time:** thời gian request chờ worker, connection hoặc executor.
5. **GC/safepoint pause:** một nguyên nhân có thể làm nhiều request chậm, nhưng không phải toàn bộ response latency.

Hai phiên bản phải dùng **cùng measurement boundary**. So p99 server processing của baseline với p99 end-to-end của candidate là sai từ thiết kế.

### 2.1. Đo phân phối thay vì chỉ trung bình

| Metric | Cách hiểu |
|---|---|
| p50 | 50% mẫu có latency không vượt giá trị này |
| p90 | 90% mẫu không vượt giá trị này |
| p95 | 95% mẫu không vượt giá trị này |
| p99 | 99% mẫu không vượt giá trị này |
| p99.9 | 99,9% mẫu không vượt giá trị này; cần nhiều mẫu |
| Mean | Trung bình số học, nhạy với outliers |
| Max | Latency lớn nhất trong cửa sổ đã đo |
| Timeouts | Những yêu cầu không hoàn tất trong deadline |

Ví dụ hoàn toàn giả định:

~~~text
A: mean=70 ms, p50=45 ms, p95=160 ms, p99=400 ms
B: mean=65 ms, p50=40 ms, p95=150 ms, p99=900 ms
~~~

Nếu SLO yêu cầu p99 dưới 500 ms, bản B là **tail regression nghiêm trọng**, dù mean và p50 tốt hơn.

### 2.2. Không loại timeout khỏi phép đánh giá

Một request timeout có thể không có latency hoàn chỉnh trong histogram success. Nếu candidate có nhiều timeout hơn nhưng report chỉ chứa request thành công, p99 thậm chí có thể đẹp hơn một cách giả tạo.

Luôn báo cả:
- Latency distribution theo success/error hoặc theo policy.
- Request count, error count và timeout count.
- Deadline/timeout threshold.
- Retries, rejected hoặc dropped operations.
- Tỷ lệ thành công trên **logical requests**, không chỉ HTTP attempts.

## 3. Throughput là số operation đã hoàn thành

**Throughput** thường tính bằng request/second, transaction/second, message/second hoặc MB/s. Phải phân biệt các đại lượng:

| Metric | Ý nghĩa |
|---|---|
| Offered load | Tốc độ request dự kiến phát sinh |
| Actual arrivals | Tốc độ request thực sự được gửi/nhận |
| Completed throughput | Tốc độ operation hoàn tất |
| Successful throughput | Tốc độ operation hoàn tất hợp lệ |
| Failed/rejected throughput | Tốc độ trả lỗi hoặc bị từ chối |
| Dropped arrivals | Lịch gửi request không thực hiện được vì load generator bận |

Ví dụ bộ tạo tải được cấu hình **400 arrivals/s**, nhưng chỉ gửi được 370 và server hoàn tất thành công 350. Không thể báo hệ thống đạt “400 RPS throughput” chỉ vì script đặt `rate=400`.

### 3.1. Throughput phải gắn với business output

Trong API thanh toán, throughput hữu ích có thể là số **payment intents được xử lý đúng một lần**, không phải số HTTP attempts. Một logical request có thể tạo 3 attempts do retry. Nếu chỉ đo attempts/s, hệ thống có nhiều retry có thể trông như xử lý nhiều hơn dù output nghiệp vụ không tăng.

Đối với messaging, phân biệt:
- Messages consumed/s.
- Unique events processed/s.
- Business state transitions/s.
- Redeliveries, duplicates và DLQ.
- Consumer lag và backlog growth.

## 4. Resource usage: không chỉ nhìn CPU hoặc heap

Trong migration, resource efficiency nên được đánh giá cùng throughput và latency.

| Nhóm | Metric | Điều cần chú ý |
|---|---|---|
| CPU | Core-seconds, utilization, throttling | Cores thực dùng và cgroup quota |
| Heap | Used/committed/max, after-GC live set | Allocation churn và GC |
| Non-heap | Metaspace, code cache | Class loading, JIT |
| Native | Thread stacks, direct buffers, JNI allocations | RSS có thể tăng dù heap giảm |
| GC | Count, pause duration, total pause, allocation | Throughput vs pause trade-off |
| Threads | Live/runnable/blocked, executor queues | Contention và starvation |
| Disk | IOPS, read/write bytes, fsync/latency | Log, DB và spill |
| Network | Bytes/s, connection count, retransmits | HTTP/2, TLS, downstream |
| Container | Working set, memory limit, OOM kills | Resource budget thực |
| Dependencies | DB/broker latency, pool saturation | Bottleneck có thể nằm ngoài JVM |

**Heap used không phải RSS**. Một ứng dụng có heap used 700 MiB vẫn có thể dùng 1,8 GiB RSS vì metaspace, code cache, direct memory và native allocations.

### 4.1. CPU-seconds trên mỗi request thành công

Một metric cho hiệu quả CPU:

\[
\text{CPU seconds per successful request}
=
\frac{\text{CPU core-seconds consumed}}{\text{successful requests}}
\]

Ví dụ ở cùng workload trong một cửa sổ 60 giây:

~~~text
A: 1.2 CPU cores * 60s / 12,000 success = 0.006 CPU-s/request
B: 1.0 CPU cores * 60s / 12,000 success = 0.005 CPU-s/request
~~~

B dùng ít CPU hơn cho cùng output, **nếu request mix, tỷ lệ success và dữ liệu thật sự tương đương**. Nhưng metric này không tự chứng minh p99 hoặc memory budget tốt hơn.

## 5. “Tải tương đương” nghĩa là gì?

Hai bài test được coi là nhận tải tương đương khi các yếu tố chính quyết định chi phí xử lý được kiểm soát hoặc được ghi nhận với lý do rõ.

| Yếu tố | Nên giữ tương đương | Vì sao |
|---|---|---|
| Request mix | Endpoint, HTTP methods, read/write ratio | Operation có cost khác |
| Arrival pattern | Offered RPS, bursts, think time | Ảnh hưởng queueing |
| Concurrency | Connections, inflight, client workers | Thay bottleneck |
| Payload | JSON bytes, nesting, schema | Serialization cost |
| Dataset | Row count, cardinality, indexes | Query performance |
| Data access | Hot/cold key distribution | Cache hit ratio |
| Cache state | Cold/warm, TTL, eviction policy | Thay latency/CPU |
| Dependencies | DB, broker, downstream performance | I/O có thể chi phối |
| Resource limits | CPU, RAM, disk, network | Throttling và capacity |
| Replicas/routing | Instance count, placement, affinity | Load skew |
| JVM options | Heap/GC flags theo phép so sánh | Trộn nhiều biến nếu không kiểm soát |
| Tool settings | Version, metrics boundary | Sai lệch dụng cụ đo |
| Warm-up/time | Thời lượng và điểm lấy mẫu | JIT/GC không đồng nhất |

**Tương đương không nhất thiết là mọi tham số phải giống nhau trong mọi phép thử.** Nếu mục tiêu là so **default configuration as shipped**, mỗi JDK có thể dùng default ergonomics riêng, nhưng báo cáo phải ghi rằng đang so hai cấu hình mặc định tổng thể. Nếu mục tiêu cô lập ảnh hưởng JIT/runtime, nên cố định heap/GC và thay JDK trong tổ hợp có hỗ trợ.

### 5.1. Workload specification mẫu

~~~yaml
benchmark:
  scenario: "orders-read-write"
  warmup: "10m"
  steady: "20m"
  offeredRate: "300 requests_per_second"
  requestMix:
    getOrder: 0.65
    listOrders: 0.20
    createOrder: 0.10
    cancelOrder: 0.05
  data:
    orders: 1000000
    customers: 100000
    distribution: "privacy-safe-production-like"
    seed: 20261112
  constraints:
    errorsMaxPercent: 0.5
    p99MaxMilliseconds: 800
~~~

Đây là **mẫu mô tả workload**, không phải định dạng mà mọi load test tool có thể đọc trực tiếp. Khi triển khai, tạo configuration/fixtures phù hợp với k6, Gatling, JMeter hoặc công cụ nội bộ được chọn.

### 5.2. Dataset và cache ảnh hưởng mạnh

Cùng 300 RPS nhưng:
- A chỉ đọc 1.000 order IDs nóng trong cache.
- B đọc 1 triệu IDs ngẫu nhiên từ database.

Kết quả không còn so riêng JDK. Cần thống nhất record cardinality, size, phân bố request, cache warming, DB state, transaction side effects và order of operations.

Với write tests, phải reset/backfill dữ liệu giữa các lượt; nếu không, bảng/index có thể lớn dần và làm các lượt sau chậm hơn.

## 6. Open-loop, closed-loop và coordinated omission

### 6.1. Closed-loop load

Trong mô hình closed-loop, một virtual user thường gửi request tiếp theo sau khi request trước kết thúc:

~~~text
Send -> Wait -> Receive -> Think -> Send next
~~~

Nếu server chậm, tốc độ gửi của client tự giảm. Điều này phù hợp với các bài test mô phỏng số người dùng và think time ổn định, nhưng có thể **che mức độ chậm khi external arrival rate trên thực tế vẫn tiếp diễn**.

### 6.2. Open-loop load

Trong open-loop, request được lên lịch theo arrival rate tương đối độc lập với response của request trước:

~~~text
t=0 ms     request 1
t=5 ms     request 2
t=10 ms    request 3
t=15 ms    request 4
~~~

Khi server chậm, inflight requests và queues tăng. Đây thường là mô hình thích hợp để so capacity dưới **cùng offered RPS**.

Tuy nhiên, nếu bộ tạo tải không đủ VUs, CPU, sockets hoặc network, nó có thể không gửi đúng lịch. Vì vậy phải quan sát **actual sent, dropped/late arrivals, load generator CPU, client errors** và không chỉ tin vào tham số rate.

### 6.3. Coordinated omission

**Coordinated omission** là lỗi đo khiến những operation đáng lẽ phát sinh trong khoảng server bị chậm/dừng không được tính đủ vào latency distribution.

Ví dụ server pause 3 giây, một client closed-loop có thể chỉ ghi một request chậm vì nó không phát thêm request trong lúc chờ. Nếu external workload vẫn tạo 100 RPS, nhiều request lẽ ra bị ảnh hưởng hơn.

Giảm sai lệch bằng cách:
- Chọn mô hình arrival phù hợp với thực tế.
- Dùng load generator/histogram có phương pháp xử lý coordinated omission được hiểu rõ.
- Ghi cả offered và completed RPS.
- Theo dõi queue/inflight/dropped iterations.
- Không lọc timeout khỏi báo cáo.

Không có mô hình open-loop nào luôn đúng cho mọi ứng dụng. **Chọn load model theo câu hỏi nghiệp vụ**, chứ không chọn vì dễ tạo đồ thị đẹp.

## 7. Thiết kế baseline–candidate và phân tách nguyên nhân

Một thí nghiệm đơn giản:

~~~text
        Baseline                   Candidate
        JDK old                    JDK new
           |                          |
      Same application commit and artifact when possible
           |                          |
      Same workload, dataset, topology, resource limits
           |                          |
      Same metrics boundary and measurement method
           |                          |
      Compare latency / throughput / resources / errors
~~~

Nếu nâng JDK cùng Spring Boot, Hibernate và Netty, kết quả là **bundle migration benchmark**, không thể tự gán mọi cải thiện/regression cho JDK.

Khi tổ hợp phiên bản được hỗ trợ, có thể tách các nhánh:

| Nhánh | JDK | Framework/dependency | Mục đích |
|---|---|---|---|
| A | Cũ | Cũ | Baseline production |
| B | Mới | Cũ | Tác động riêng của JDK |
| C | Mới | Mới | Bundle migration |
| D | Cũ | Mới | Tác động framework nếu tổ hợp được hỗ trợ |

Không chạy một tổ hợp **không được hỗ trợ** để ép đủ ma trận. Nếu chỉ có A và C là hợp lệ, kết luận cần nói rõ không thể cô lập tác động riêng của JDK.

### 7.1. Run metadata phải tái lập được

Ví dụ một record có các placeholder:

~~~text
runId: A-001
gitCommit: COMMIT_SHA
artifactSha256: ARTIFACT_HASH
jdkVendor: VENDOR
jdkVersion: MAJOR_PATCH_BUILD
frameworkVersion: VERSION
containerImageDigest: IMAGE_DIGEST
gc: GC_AND_OPTIONS
xmsXmx: HEAP_VALUES
containerCpu: CPU_LIMIT
containerMemory: MEMORY_LIMIT
instanceCount: 1
datasetSeed: SEED
loadToolVersion: TOOL_VERSION
loadScenario: orders-v1-300rps
warmup: 10m
measurement: 20m
~~~

Lưu thêm hostname/node type, OS/kernel version, test start/end và dashboards/log links khi quy trình yêu cầu. **Không coi các placeholder là dữ liệu thực tế**.

## 8. Kiểm soát CPU và môi trường vật lý/ảo hóa

JVM performance phụ thuộc CPU microarchitecture, số core, SMT, NUMA, CPU frequency, thermal/power policy và contention từ các process khác.

Trong container, phải xét:
- CPU requests và limits.
- Cpuset/quota và core counts mà JVM nhận diện.
- Container CPU throttling periods/time.
- Số GC/compiler/application threads.
- CPU frequency/turbo và noisy neighbors.
- Pod placement và node type.

Một container có 2 vCPU quota không tương đương một process không limit trên host 2 physical cores. **Same nominal CPU count** không tự bảo đảm same effective compute capacity.

### 8.1. CPU throttling làm méo p99

Nếu application cần thêm CPU trong một burst nhưng bị quota, request queue sẽ tăng. Candidate có thể có CPU efficiency tốt hơn ở steady state nhưng gặp tail latency tệ hơn do JIT/GC burst trong container nhỏ.

Khi đọc kết quả, kiểm tra song song:
- CPU core-seconds.
- Quota/limit.
- Throttled time.
- Runnable thread count.
- Request queue length và p99.

Không kết luận một JDK có GC pause tệ hơn chỉ từ p99 khi throttling đang cao.

## 9. Kiểm soát memory, heap và native allocations

Những biến cần ghi:
- Container memory limit và swap policy.
- `-Xms`, `-Xmx` hoặc percent-based JVM flags.
- Heap used/committed/max.
- RSS/working set.
- Metaspace, code cache, thread stacks.
- Direct ByteBuffer/off-heap caches.
- JNI/native allocations.
- File cache và các memory metrics của cgroup.

Ví dụ, baseline dùng max heap 2 GiB nhưng candidate dùng heap ergonomic 3 GiB trên container 4 GiB có thể làm memory/GC behavior khác. Đây là khác biệt đáng đo khi dùng defaults, nhưng không phải phép so “cùng heap size”.

### 9.1. Heap after GC và memory leak

Heap used dao động lên xuống theo GC cycle là bình thường. Cần chú ý hơn khi:
- After-GC live set tăng liên tục dù workload ổn định.
- Old generation occupancy không quay lại mức cũ.
- RSS tăng lâu dài trong khi heap gần như ổn định.
- Direct memory, native allocations hoặc thread count tăng không giới hạn.
- GC frequency/pause tăng theo thời gian.
- Container bị OOM kill.

Một soak test dài có thể phát hiện vấn đề mà bài đo 5 phút không thấy.

## 10. JVM flags và default ergonomics

Nâng JDK có thể thay các tối ưu JIT, GC heuristics, khả năng nhận diện container, compiler threads và runtime defaults. Có hai mục tiêu test khác nhau:

**Equalized settings:** cố định cùng collector, heap, CPU/RAM và các flags hỗ trợ trên cả hai JDK để giảm số biến.

**Defaults as shipped:** để mỗi JDK dùng default của chính nó, vẫn pin tài nguyên container và workload, nhằm mô phỏng deployment thật nếu không có tuning riêng.

Hai phép đo đều có giá trị nhưng **không trộn vào cùng một kết luận**. Nếu JDK candidate chuyển GC collector hoặc tuning flags không còn được hỗ trợ, cần ghi rõ constraint và lý do.

### 10.1. Kiểm tra JVM version và flags

Trên runtime phù hợp:

~~~bash
java -version
java -XX:+PrintFlagsFinal -version
~~~

Với process đang chạy và quyền chẩn đoán tương ứng:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~

`jcmd` có thể không có trong runtime image tối giản hoặc bị policy hạn chế. Không mở rộng quyền production chỉ để thu benchmark nếu có cách an toàn hơn.

## 11. Startup, warm-up và steady state

JVM thường cần thời gian để:
- Load và initialize classes.
- Khởi tạo dependency injection/application context.
- Chạy JIT compilation và profile-guided optimization.
- Warm database connections, caches và thread pools.
- Trải qua GC cycles để đạt trạng thái tương đối ổn định.

Không nên dùng kết quả 10 giây đầu rồi gọi đó là throughput steady state. Cũng không nên **bỏ startup khỏi đánh giá** nếu startup latency thuộc SLO, ví dụ autoscaling, serverless, short-lived workers.

### 11.1. Phân đoạn phép đo

| Giai đoạn | Đánh giá | Metrics |
|---|---|---|
| Cold start | Khởi động cho đến ready | Startup time, peak CPU/RSS |
| Warm-up | JVM/cache/pool đạt trạng thái ổn định | JIT, cache hit, latency trend |
| Steady state | Hiệu năng xử lý tải ổn định | p50/p95/p99, RPS, CPU/request |
| Burst | Tăng tải đột ngột | Queue, errors, time to recover |
| Soak | Hoạt động dài | Memory drift, GC, FDs, threads |

Một cửa sổ 10 phút warm-up là **ví dụ**, không phải chân lý cho mọi service. Xác nhận steady behavior qua latency trend, compilation activity, cache hit ratio và resource graphs.

## 12. Đo đường cong tải và điểm bão hòa

Một service có thể nhanh hơn ở 100 RPS nhưng chậm hơn ở 500 RPS. Nên đo một dải tải:

~~~text
50 -> 100 -> 200 -> 300 -> 400 -> 500 RPS
~~~

Ở từng mức:
- Giữ cùng workload mix và dataset distribution.
- Warm-up/measurement theo quy trình.
- Thu offered/actual/successful RPS.
- Thu latency percentiles, errors, timeouts.
- Thu CPU/RSS/GC, queues và downstream metrics.
- Quan sát load generator không bị nghẽn.

**Knee point** là vùng hệ thống bắt đầu bão hòa: tăng offered load ít tăng successful throughput nhưng latency, queue và error tăng nhanh.

### 12.1. SLO-constrained capacity

Ví dụ điều kiện nghiệm thu giả định:
- p99 dưới 800 ms.
- Error/timeout không quá 0,5%.
- Không có queue tăng không giới hạn.
- Không vượt memory/container budget.
- Không bị CPU throttling nghiêm trọng.

Capacity hữu ích là **mức tải bền vững cao nhất vẫn thỏa toàn bộ SLO/resource constraints**, không phải RPS cực đại trong khi đa số request đã timeout.

## 13. Ví dụ bộ tạo tải constant-arrival-rate với k6

Một script minh họa cho endpoint đọc, sử dụng k6:

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    orderReads: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '10m',
      preAllocatedVUs: 80,
      maxVUs: 400,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.005'],
    http_req_duration: ['p(95)<300', 'p(99)<800'],
    dropped_iterations: ['count==0'],
  },
};

export default function () {
  const base = __ENV.BASE_URL || 'http://127.0.0.1:8080';
  const orderId = 1 + Math.floor(Math.random() * 100000);
  const response = http.get(base + '/orders/' + orderId);

  check(response, {
    'expected status': (r) => r.status === 200,
  });
}
~~~

Đây là **script minh họa**, cần sửa endpoint, authentication, fixture/dataset và thresholds theo hệ thống. Nếu một số order ID không tồn tại, `404` có thể là response nghiệp vụ hợp lệ chứ không phải lỗi hiệu năng; phải thiết kế test data và expected status nhất quán.

Số 200 chỉ là **offered arrival rate**. Kết quả phải xem actual sent, successful completed, dropped iterations, error/timeout, VU utilization và CPU/network của máy phát tải.

### 13.1. Write workload và idempotency

Không dùng giao dịch production thật để load test payment, email hoặc fulfillment. Nếu đo create/update:
- Chuẩn bị dữ liệu kiểm thử riêng không chứa PII.
- Đảm bảo idempotency và unique business keys.
- Reset hoặc reconcile DB giữa runs.
- Không kích hoạt email/SMS/payment thật.
- Xác minh rollback, retry và transaction state.
- Ghi dataset growth, index size và write amplification.

Một benchmark làm hỏng dữ liệu hoặc phát side effects thật không phải quy trình chấp nhận được.

## 14. Percentile và vấn đề tổng hợp thống kê

### 14.1. Không lấy trung bình các p99

p99 của 60 cửa sổ một phút **không bằng** trung bình p99 của 60 cửa sổ ấy. Percentile là phép đo trên phân phối mẫu, không cộng tuyến tính.

Nếu cần aggregate:
- Dùng raw samples, hoặc
- Merge histograms/quantile sketches theo phương pháp được công cụ hỗ trợ.
- Ghi bucket configuration và độ chính xác xấp xỉ.
- Không dùng `avg(p99)` như global p99.

### 14.2. Số mẫu đủ lớn

p99 phản ánh 1% phần đuôi. Nếu chỉ có 100 requests, rất ít mẫu quyết định p99; kết luận dễ nhiễu. p99.9 còn đòi hỏi nhiều mẫu hơn. Báo rõ sample count, test duration, timeout và số lượt lặp.

Một chênh lệch 3 ms có thể không có ý nghĩa nếu độ biến thiên run-to-run là ±20 ms. Không nên xem mọi chênh lệch hiển thị trên dashboard đều là regression thật.

### 14.3. Phân nhóm metrics

Có thể phân tích theo:
- Endpoint/operation.
- HTTP status/error class.
- Payload size cohort.
- Runtime/JDK version.
- Instance hoặc node group.
- Cache hit/miss hoặc DB query class.

Không gắn user IDs/order IDs trực tiếp vào metric labels vì chi phí cardinality và quyền riêng tư.

## 15. GC: đo pause và chi phí CPU, không chỉ số lần collection

GC có thể thay đổi khi đổi JDK, GC collector hoặc heap size. Metrics nên thu:
- GC count, pause count, total pause time.
- Pause duration distribution khi đủ mẫu.
- Allocation rate, bytes/request.
- Heap occupancy trước/sau GC.
- Promotion/old-gen pressure.
- Concurrent GC CPU.
- Safepoint time và thread states.

### 15.1. GC pause không phải toàn bộ request latency

Một pause 100 ms có thể tác động nhiều requests cùng lúc. Nhưng một p99 latency 2 giây có thể do database lock 1,9 giây, connection pool queue hoặc CPU throttling. Cần kết hợp request traces và mốc thời gian GC/JFR để tìm tương quan; **đừng suy luận nhân quả chỉ vì hai biểu đồ tăng cùng lúc**.

### 15.2. GC logging

Ví dụ HotSpot hỗ trợ unified logging:

~~~bash
java \
  -Xms2g -Xmx2g \
  -Xlog:gc*,safepoint:file=/var/log/orders/gc.log:time,uptime,level,tags:filecount=5,filesize=20m \
  -jar orders.jar
~~~

Phải tạo thư mục log và cấp quyền phù hợp. GC log formats/tags có thể khác theo JDK/collector. Logging cũng có overhead I/O; khi dùng để so sánh, bật instrumentation tương đương hoặc đánh giá overhead riêng.

### 15.3. Collector trade-offs

Một collector ưu tiên tail latency có thể tiêu thụ thêm CPU hoặc memory; một collector tối ưu throughput có thể cho pauses dài hơn. Không có collector tốt nhất cho mọi ứng dụng. Khi chuyển từ G1 sang ZGC hoặc cấu hình khác, hãy báo phép đo là **JDK + GC configuration** chứ không gán mọi delta cho Java compiler/JIT.

## 16. Memory leak, RSS và native memory

JVM process memory có nhiều phần:

~~~text
Process RSS / memory
   |
   +-- Java heap
   +-- Metaspace and class metadata
   +-- JIT code cache
   +-- Thread stacks
   +-- Direct buffers / off-heap caches
   +-- JNI and native libraries
   +-- Memory mappings / runtime structures
~~~

Với soak test, quan sát:
- Heap after GC có ổn định không?
- RSS có tăng dù heap ổn định không?
- Thread count/FD count tăng không dừng?
- Direct/native memory có tăng cùng với network throughput?
- Container có tiến sát OOM limit?
- GC pause tăng dần theo thời gian?

### 16.1. Native Memory Tracking

Trên một số JVM HotSpot có thể bật NMT lúc khởi động:

~~~bash
java -XX:NativeMemoryTracking=summary -jar orders.jar
~~~

Rồi xem summary khi runtime và quyền chẩn đoán cho phép:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

NMT có overhead và không phân loại toàn bộ allocations bên ngoài JVM; cần hiểu giới hạn công cụ. Không so NMT-enabled candidate với NMT-disabled baseline rồi quy toàn bộ CPU difference cho JDK.

### 16.2. Heap dump và dữ liệu nhạy cảm

Heap dump có thể gây pause, memory pressure và chứa token/PII/secret. Không lấy heap dump trên production chỉ để tạo thêm metrics khi chưa có lý do, quyền và storage policy. Bắt đầu bằng counters/JFR/NMT phù hợp và chỉ lấy dump khi thật sự cần điều tra.

## 17. JFR và profiling

**Java Flight Recorder (JFR)** cho phép thu sự kiện JVM để điều tra:
- CPU hotspots và sampling.
- Allocation rate/stack traces.
- GC và safepoints.
- Lock contention, thread states và parks.
- Class loading và JIT activity.
- Một số socket/file I/O events.

Ví dụ chạy một recording ngắn với quyền cần thiết:

~~~bash
jcmd <pid> JFR.start name=perf settings=profile duration=120s filename=/tmp/perf.jfr
jcmd <pid> JFR.check
~~~

Có thể dùng JDK Mission Control hoặc công cụ phân tích JFR để kiểm các events.

### 17.1. Kiểm soát overhead đo

JFR không có overhead bằng 0; event settings, sampling và duration ảnh hưởng chi phí. Ghi JDK version, event set, sampling thresholds, duration và phương pháp phân tích. Nếu performance delta chỉ vài phần trăm, chạy thêm nhánh không profiling để xác nhận kết luận.

### 17.2. Sử dụng profiling để kiểm giả thuyết

Ví dụ:
- CPU/request tăng → xem stack samples/JIT/inlining.
- p99 tăng → xem GC pause, monitor contention, thread parks.
- RSS tăng → xem allocation, native memory, thread counts.
- Throughput giảm → xem queueing/downstream waits.
- Cold start chậm → xem class loading và framework init.

Profiling chỉ ra nơi tốn thời gian hoặc allocations, **chưa tự chứng minh nguyên nhân**. Sau khi sửa, chạy lại benchmark cùng workload để xác nhận hiệu quả.

## 18. JMH cho microbenchmark có kiểm soát

**Java Microbenchmark Harness (JMH)** là công cụ phù hợp để kiểm một giả thuyết về hiệu năng ở mức method/algorithm. Nó hỗ trợ warm-up, measurement iterations, forks, states và cách dùng kết quả để tránh một số lỗi đo micro thông thường.

Một vòng lặp tự dùng `System.nanoTime()` có thể sai do:
- Dead-code elimination.
- Constant folding.
- JIT compilation warm-up.
- Inlining/deoptimization khác nhau.
- Class loading/GC trộn vào phép đo.
- Benchmark overhead lớn so với operation được đo.

### 18.1. Ví dụ JMH

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 10, time = 1)
@Fork(3)
public class MapLookupBenchmark {
    private Map<Integer, String> data;
    private int index;

    @Setup(Level.Trial)
    public void setup() {
        data = new HashMap<>();
        for (int i = 0; i < 10000; i++) {
            data.put(i, "value-" + i);
        }
    }

    @Benchmark
    public String lookup() {
        index = (index + 1) % 10000;
        return data.get(index);
    }
}
~~~

Muốn chạy cần JMH dependencies và annotation processing/plugin phù hợp với build, compiler và JDK. Đây là bài mẫu cho một operation, **không thể ngoại suy trực tiếp ra HTTP throughput**, nơi network, serialization, database và queueing có ảnh hưởng lớn.

## 19. Application metrics, tracing và downstream behavior

Một request path thường gồm:

~~~text
Client -> Gateway -> Server queue -> Authentication
       -> Business work -> Database / HTTP downstream
       -> Serialization -> Response
~~~

Khi client p99 tăng, cần phân biệt:
- Chờ ở ingress/load balancer.
- Chờ trong executor hoặc connection pool.
- CPU-bound work.
- GC/JIT/safepoint stalls.
- DB/query/cache misses.
- Network/TLS và remote dependency.
- Response serialization.

Dùng tracing/metrics để tìm request segments chậm. **Không cộng p99 của các segment thành p99 tổng**: quantiles của các phân phối không cộng tuyến tính.

### 19.1. Little's Law

Trong điều kiện hệ thống ổn định:

\[
L = \lambda W
\]

Ở đó:
- \(L\): số operation trung bình đang trong hệ thống.
- \(\lambda\): throughput trung bình trong trạng thái ổn định.
- \(W\): thời gian trung bình trong hệ thống.

Ví dụ 200 request/s và mean response time 0,1 s gợi ý trung bình khoảng 20 requests in-flight theo boundary phù hợp. Công thức không trực tiếp dự đoán p99; nếu queue liên tục phát triển hoặc nhiều requests bị drop, cần xem lại giả định.

## 20. Lặp lại, thứ tự thử nghiệm và độ biến thiên

Một lượt A rồi một lượt B dễ bị bias do:
- CPU frequency/power/thermal state.
- Warm/cold caches.
- Background jobs, DB maintenance.
- JIT compilation phase.
- Network jitter, noisy neighbors.
- Thời điểm GC và dataset changes.

Có thể dùng nhiều lượt A/B với thứ tự cân bằng:

~~~text
A1 -> B1 -> B2 -> A2 -> A3 -> B3
~~~

Mỗi lượt dùng cùng workload/dataset reset policy, có warm-up và measurement windows đã chốt.

### 20.1. Báo variability, không chỉ một con số

Với p99, throughput và CPU/request:
- Lưu giá trị từng run và sample counts.
- Báo median/min/max hoặc dispersion giữa runs.
- Khi cần dùng confidence interval, chọn phương pháp phù hợp với dữ liệu correlated/time series; không coi mọi request trong một run là phép lặp độc lập.
- Phân biệt statistical significance với business significance.

Ví dụ chênh 1% nhưng run-to-run noise 5% không đủ chứng cứ cho kết luận chắc chắn. Ngược lại p99 tăng 25% và vượt SLO liên tục là vấn đề vận hành ngay cả khi không cần mô hình thống kê phức tạp.

## 21. Bảng so sánh mẫu và cách diễn giải

**Các số sau là giả định minh họa, không phải dữ liệu benchmark thực tế:**

| Chỉ số tại 300 offered RPS | Baseline A | Candidate B | Diễn giải |
|---|---:|---:|---|
| Actual sent RPS | 300 | 300 | Load tương đương |
| Successful RPS | 298 | 299 | B tốt hơn nhẹ |
| Error + timeout | 0,7% | 0,3% | B có độ tin cậy tốt hơn |
| p50 latency | 55 ms | 50 ms | B tốt hơn |
| p95 latency | 160 ms | 145 ms | B tốt hơn |
| p99 latency | 420 ms | 510 ms | **B có tail regression** |
| CPU cores trung bình | 2,1 | 1,9 | B tiết kiệm CPU |
| CPU throttled time | 0 | 0 | Không bị quota che |
| Process RSS | 1,8 GiB | 2,0 GiB | B tăng memory |
| Heap after GC | 0,70 GiB | 0,65 GiB | Live heap B giảm |
| Total GC pause/phút | 0,8 s | 0,5 s | B giảm pause tổng |
| DB p99 | 220 ms | 350 ms | Cần điều tra downstream |

Nếu SLO p99 là 500 ms, candidate B **không đạt gate** mặc dù mean/median, CPU và GC có cải thiện. Nếu RAM budget là 1,9 GiB RSS, B có thêm một vấn đề footprint. Đây là lý do quyết định migration phải xét **nhiều chỉ số và ngân sách**.

### 21.1. Tính phần trăm thay đổi

\[
\Delta \% =
\frac{\text{candidate} - \text{baseline}}
{\text{baseline}}\times 100\%
\]

Ví dụ p99 từ 400 lên 500 ms là +25%, **xấu hơn** nếu mục tiêu giảm latency. Successful throughput +25% thường là **tốt hơn** nếu error rate và SLO không bị vi phạm. Không áp chung cách tô màu “positive delta” cho mọi metric.

## 22. Performance gates và quyết định rollout

Một gate cần có cả **absolute thresholds** và **regression limits**, ví dụ minh họa:

~~~yaml
performanceGate:
  workload: "orders-steady-300rps"
  measuredWindow: "20m-after-10m-warmup"
  latency:
    p99MaxMs: 500
    p95RegressionMaxPercent: 10
  throughput:
    successfulMinRps: 295
  reliability:
    errorAndTimeoutMaxPercent: 0.5
  resources:
    cpuPerSuccessRegressionMaxPercent: 10
    rssMaxGiB: 2.2
  loadGenerator:
    requireDroppedIterationsZero: true
~~~

Đây là policy minh họa, không phải schema mặc định cho một tool. Ngưỡng phải được lấy từ SLO, error budget, capacity planning và ràng buộc chi phí của hệ thống.

### 22.1. Absolute vs relative gate

Nếu baseline p99 đã 900 ms và candidate đạt 850 ms, đó là **cải thiện** nhưng vẫn **chưa đạt SLO** 500 ms. Nếu baseline 100 ms và candidate 110 ms, regression là 10% nhưng hai bên vẫn có thể đạt yêu cầu tuyệt đối; quyết định phụ thuộc policy.

### 22.2. Gắn gate với business-critical paths

Đừng chỉ gate endpoint GET phổ biến nếu payment/checkout có SLO nghiêm ngặt. Nên có:
- Read-heavy scenario.
- Write-heavy scenario.
- Latency-sensitive critical path.
- Burst/capacity scenario.
- GC/allocation-heavy scenario khi có.
- Soak stability.

Một release có thể nâng RPS của read operations nhưng khiến write transaction chậm hoặc duplicate nếu retry logic khác.

## 23. Benchmark trên container và Kubernetes

Khi chạy trong container, cần ghi:
- Container image digest/JDK vendor-build.
- CPU requests, limits và throttling.
- Memory limits, RSS/working set và OOM events.
- Number of replicas, instance type, node architecture.
- HPA/VPA policies nếu có.
- Ingress/LB routing, session affinity.
- Database/broker capacity và pool settings.

Nếu autoscaler tự tăng replicas của candidate nhưng baseline giữ nguyên replica count, không được gọi đó là cải thiện **per-instance performance**. Có thể làm hai bài khác nhau:
1. **Per-replica capacity** với số replicas cố định.
2. **System-level autoscaling behavior** với scaling policy tương đương.

### 23.1. Production canary không tự động là benchmark tương đương

Canary có thể nhận nhóm tenant hoặc session khác:
- Request mix không giống baseline.
- Data hotness/cache behavior khác.
- Node type và CPU khác.
- Canary ít tải nên chưa chạm saturation.
- Other services/backends chịu tải biến thiên.

Canary hữu ích để đánh giá **an toàn vận hành trong traffic thật**, nhưng muốn kết luận riêng tác động JVM có thể cần controlled replay/paired instances hoặc phân tích cohort tương đương.

## 24. Bài tập thực hành thiết kế thí nghiệm

**Bối cảnh giả định:** Orders service đang dùng JDK 17, dự kiến lên JDK 21. Service có read-heavy API, một số writes và database PostgreSQL. SLO p99 GET dưới 600 ms tại 400 RPS; error không quá 0,5%; container có giới hạn 4 vCPU/4 GiB RAM.

### 24.1. Kế hoạch A/B

1. Pin một application commit/artifact và dependency graph nếu mục tiêu cô lập JDK.
2. Dùng hai container images chỉ khác JDK vendor/version; ghi digest.
3. Pin hoặc ghi rõ GC, heap và JVM flags của mỗi bên.
4. Tạo dataset privacy-safe với một triệu orders, seed và access distribution cố định.
5. Giữ database, query indexes và connection pool policy tương đương.
6. Chạy warm-up trước measurement.
7. Đo 200, 300, 400, 500 RPS với request mix đã chốt.
8. Thu success RPS, p50/p95/p99, timeouts, dropped arrivals.
9. Thu CPU/RSS/heap-after-GC, GC pauses, queues, DB latency.
10. Lặp A/B nhiều lần, cân bằng thứ tự và reset dữ liệu.
11. Chạy soak test đủ dài để quan sát memory/resource drift.
12. Nếu có regression, lấy JFR/GC logs/profile và kiểm lại sau khi sửa.
13. Áp performance gate trước khi chấp nhận canary/rollout.

### 24.2. Khi kết quả trái chiều

Giả sử candidate giảm CPU 8%, nhưng p99 ở 400 RPS tăng 30%. Có thể do:
- GC/JIT behavior ở tải cao.
- CPU throttling/queueing.
- DB connection pool config mặc định thay.
- Request/data distribution không đồng đều.
- Load generator đạt không đủ arrival rate.
- Dependency/framework thay behavior mà đội benchmark chưa ghi.

Đừng kết luận “JDK mới chậm” hay “JDK mới tốt” trước khi phân tích điều kiện của phép đo và nguyên nhân tại đúng tầng.

### 24.3. Mẫu kết luận có giới hạn rõ

Một báo cáo hợp lệ có thể mô tả:

> Với cùng workload Orders 400 RPS, resource limits và dataset đã pin, candidate cải thiện CPU efficiency nhưng p99 latency vượt ngưỡng gate. Do đó chưa chấp nhận rollout toàn bộ. Các run metrics, workload configuration, GC logs và JFR profiles được lưu để điều tra.

Đây là **mẫu cách trình bày**, không phải một kết luận thực về JDK 21 nói chung.

## 25. Các sai lầm hay gặp

- **So p99 nhưng request mix khác:** không cùng workload.
- **Chỉ nhìn RPS gửi, không nhìn RPS hoàn tất:** nhầm offered với throughput.
- **Bỏ timeout/error khỏi report:** làm latency đẹp giả.
- **Closed-loop che coordinated omission:** tail latency bị đánh giá thấp.
- **Load generator nghẽn:** script không đạt arrivals định cấu hình.
- **Dataset/cardinality/cache state khác:** không còn đo tác động runtime.
- **Dùng mean thay p99 cho API nhạy latency:** bỏ sót tail regression.
- **Tính global p99 bằng avg các p99 buckets:** sai về thống kê.
- **Đo ngay sau startup và gọi steady state:** bỏ qua JIT/cache warm-up.
- **Bỏ cold start khỏi bài toán autoscaling:** đánh giá thiếu một SLO.
- **So heap used với process RSS:** không cùng khái niệm.
- **Quên CPU quota/throttling:** resource environment khác.
- **Chỉ đo một lần:** dễ nhiễu do CPU, cache và GC timing.
- **Đổi JDK, framework, GC và DB driver cùng lúc:** không cô lập nguyên nhân.
- **Nghĩ p99 tăng chắc do GC:** có thể do queue/DB/TLS.
- **Chỉ dùng JMH để kết luận về HTTP service:** thiếu network/I/O/DB.
- **Bật JFR ở một bên nhưng không bên kia:** overhead measurement khác.
- **Không reset data sau write load:** run sau có data/index khác.
- **Canary traffic khác baseline:** có selection bias.
- **Tăng replicas rồi báo cải thiện per-instance capacity:** không tương đương.
- **Không lưu artifact/JDK/build metadata:** không tái lập được kết quả.
- **Không test logic nghiệp vụ dưới tải:** nhanh nhưng trả sai vẫn thất bại.

## 26. Checklist trước khi duyệt performance migration

- [ ] Đã ghi JDK vendor, version/build và image digest baseline/candidate.
- [ ] Đã xác định source commit, artifact checksum, dependency versions và JVM flags.
- [ ] Đã tách phép đo JDK riêng với bundle framework migration khi có thể.
- [ ] Workload có request mix, arrival pattern, payload distribution, dataset/seed rõ.
- [ ] Đã kiểm soát cache state, DB/broker/downstream conditions.
- [ ] Đã pin/ghi CPU/RAM limits, node type, replica count và network topology.
- [ ] Đã kiểm tra load generator đủ tài nguyên, không drop arrivals ngoài dự kiến.
- [ ] Đã chọn open-loop/closed-loop theo business goal và xét coordinated omission.
- [ ] Đã tách cold start, warm-up, steady, burst và soak khi liên quan.
- [ ] Đã đo cùng boundary với đủ mẫu p50/p95/p99 và error/timeout counts.
- [ ] Đã báo actual arrivals, successful throughput và retry attempts.
- [ ] Không tổng hợp global percentiles bằng trung bình bucket percentiles.
- [ ] Đã thu CPU core-seconds, CPU throttling và CPU per success.
- [ ] Đã thu heap, RSS, non-heap/native memory khi cần.
- [ ] Đã theo dõi GC pause/count, heap-after-GC và allocation rate.
- [ ] Đã đối chiếu queue, DB/broker/network latency để tìm bottleneck.
- [ ] Đã lặp benchmark nhiều lần và báo run-to-run variation.
- [ ] Có absolute SLO gates cùng regression thresholds.
- [ ] Đã test production target load và capacity headroom.
- [ ] Đã chạy soak test khi có rủi ro leak/RSS drift.
- [ ] Có JFR/GC/profile evidence khi cần điều tra regression.
- [ ] Đã xác minh business correctness và side effects dưới tải.
- [ ] Đã lưu run metadata, raw metrics/histograms và rollback/canary decision.

## 27. Tài liệu tham khảo

Những nguồn sau giúp triển khai công cụ và hiểu semantics, cần dùng đúng version đã pin trong dự án:

- [OpenJDK JMH](https://github.com/openjdk/jmh): microbenchmark Java, warm-up, forks, benchmark states.
- [JDK jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): truy vấn JVM flags, GC và điều khiển JFR.
- [JDK java Launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): JVM options và `-Xlog`.
- [Java Flight Recorder API](https://docs.oracle.com/en/java/javase/21/jfapi/): JFR events và recording.
- [JDK Mission Control](https://openjdk.org/projects/jmc/): phân tích JFR và profiling.
- [Grafana k6 Documentation](https://grafana.com/docs/k6/latest/): arrival-rate load, metrics, thresholds và dropped iterations.
- [HdrHistogram](https://github.com/HdrHistogram/HdrHistogram): histogram latency và coordinated omission.
- [Micrometer Reference](https://docs.micrometer.io/micrometer/reference/): JVM/application metrics và timers.

Tài liệu “latest” có thể khác release đang chạy. Với báo cáo hiệu năng của hệ thống nội bộ, quan trọng hơn cả là **giữ workload profile, metric definitions, test duration, raw samples/histograms và môi trường đo đủ để tái lập**.

## 28. Kết luận

**Đo hiệu năng khi nâng JDK là một phép so sánh có kiểm soát, không phải chạy vài request rồi so thời gian trung bình.** Latency phải được đo cùng boundary với đủ p95/p99 và timeout data; throughput phải phân biệt offered load với successful completions; resource usage phải xét CPU throttling, heap, RSS, GC, native memory và downstream dependencies.

Quy trình đáng tin cậy là **đóng băng workload/dataset → pin runtime và tài nguyên → warm-up → đo nhiều điểm tải → thu latency/throughput/errors/resources → lặp A/B → điều tra bằng JFR/GC/profiling → so với SLO/capacity gates → canary/rollback có bằng chứng**. Khi phép đo thực sự dùng **tải tương đương**, team có thể phân biệt cải thiện thật với hiệu ứng cache, load generator, GC defaults hoặc thay đổi framework, từ đó quyết định nâng Java trên cơ sở kỹ thuật và vận hành an toàn.
