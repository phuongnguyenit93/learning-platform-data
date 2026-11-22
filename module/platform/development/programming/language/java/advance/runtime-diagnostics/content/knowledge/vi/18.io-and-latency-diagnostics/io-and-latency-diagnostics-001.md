# 18.1 Phân biệt ứng dụng chậm vì tính toán với chậm vì chờ tài nguyên

## 1. Bài toán chẩn đoán: thời gian request đã trôi qua ở đâu?

Một API Java trả kết quả sau **1.000 ms** không có nghĩa CPU đã tính toán liên tục trong một giây. Trong một request có thể đồng thời tồn tại nhiều nguyên nhân chậm:

- **CPU-bound:** thread thực sự dùng CPU để tính toán, mã hóa JSON, nén, phân tích cú pháp, tìm kiếm, mã hóa/giải mã, xử lý dữ liệu, thuật toán có độ phức tạp cao hoặc spin.
- **I/O-bound:** thread/luồng xử lý phải chờ disk, file, socket, database, HTTP/gRPC service, DNS, TLS, storage hoặc một hệ thống ngoài.
- **Resource/coordination-bound:** chờ lấy connection từ pool, chờ lock, queue, semaphore, rate limiter, thread pool hoặc executor không còn worker rảnh.
- **CPU scheduling-bound:** công việc có thể chạy được nhưng chưa nhận đủ CPU vì host cạnh tranh, container CPU quota/throttling, run queue dài, ưu tiên scheduler.
- **JVM/system pauses:** GC stop-the-world, safepoint, class loading, JIT compilation, paging, kernel/scheduler… có thể làm tăng latency mà không giống một CPU hot loop đơn giản.

**Mục tiêu** là xác định **nhánh nào nằm trên critical path của request**, kèm bằng chứng đo được. Không kết luận nguyên nhân chỉ từ một biểu đồ CPU, trạng thái `RUNNABLE` hoặc một thread dump.

Bài này tập trung vào cách **phân biệt tính toán với chờ tài nguyên** bằng wall-clock time, CPU time, metrics, thread dump, JFR và tracing; có ví dụ Java 17+ độc lập để tự kiểm chứng.

## 2. Hai đồng hồ quan trọng nhất: wall time và CPU time

**Wall-clock elapsed time** là thời gian thực đã trôi qua từ khi bắt đầu tới khi kết thúc một đoạn xử lý, kể cả khi thread chưa được scheduler cho chạy hoặc đang chờ I/O/lock.

**Thread CPU time** là tổng thời gian CPU thực thi instruction cho **platform thread đó** ở user mode và system mode. Một thread có thể mất 500 ms wall time để chờ network nhưng chỉ dùng vài mili giây CPU; ngược lại một vòng lặp tính toán bận khoảng 500 ms wall thường tích lũy CPU time gần 500 ms nếu được scheduler cấp CPU liên tục.

| Loại thời gian | Nguồn đo Java | Dùng để trả lời | Cảnh báo |
| --- | --- | --- | --- |
| Wall elapsed | `System.nanoTime()` lấy hiệu giữa hai mốc | Caller đã chờ bao lâu? | Bao gồm CPU, I/O wait, queue, scheduling và nhiều dạng pause khác. |
| Current thread CPU | `ThreadMXBean.getCurrentThreadCpuTime()` | Platform thread này đã thực sự dùng bao nhiêu CPU? | Có thể không hỗ trợ/tắt mặc định; không hỗ trợ virtual thread qua API này. |
| Process CPU | OS/JMX process CPU time hoặc telemetry process | Tổng CPU của **mọi thread** trong process đã dùng bao nhiêu? | Có thể nhiều hơn wall time vì nhiều CPU core chạy song song. |
| CPU của máy/container | OS/container monitoring | Host hoặc CPU quota có bão hòa không? | Phải hiểu mẫu số theo core/quota; CPU 25% có thể tương ứng một core bận 100%. |
| Thời gian dependency | Distributed tracing, DB/HTTP client metrics | Chờ database, pool, socket, remote service bao lâu? | Cần cùng trace/timestamp, không thể suy ra chính xác từ process CPU. |

Công thức chẩn đoán **chỉ có ý nghĩa gần đúng cho một platform thread được đo trên cùng khoảng thời gian**:

```text
elapsed = endNanoTime - startNanoTime
threadCpu = endThreadCpuTime - startThreadCpuTime

cpu_fraction ≈ threadCpu / elapsed
remaining_elapsed ≈ elapsed - threadCpu
```

Nếu thread có **200 ms wall, 190 ms CPU**, đoạn đó có nhiều thời gian on-CPU. Nếu **200 ms wall, 2 ms CPU**, gần như toàn bộ elapsed không phải CPU execution của thread ấy. Nhưng **198 ms còn lại không thể tự gọi là “network wait”**: có thể đang chờ pool, monitor, park, GC pause, scheduling hoặc CPU throttling. Để phân loại phải lấy bằng chứng ở các lớp khác.

Độ chính xác CPU clock do JVM/OS quyết định. Số đo rất ngắn hoặc làm tròn miligiây có thể cho tỷ lệ hơi vượt 1.0; đừng dùng một ngưỡng cứng cho microbenchmark. `System.nanoTime()` được dùng để **lấy hiệu thời gian**, không dùng như Unix timestamp và không nên so sánh các mốc lấy từ JVM/clock không liên hệ.

## 3. CPU-bound và wait-bound khác nhau như thế nào?

### Khi chậm vì tính toán

Một thread lặp trong codec, parser, regex, thuật toán `O(n²)`, JSON serialization, encryption, validation hay mã nghiệp vụ. Với workload ổn định, dấu hiệu thường gặp:

1. CPU time của thread đang thực thi tăng gần tương ứng với elapsed time.
2. Process/container CPU hoặc một core bão hòa, đặc biệt khi lượng request tăng.
3. JFR execution samples tập trung lặp lại ở một số call stacks/hot methods.
4. Thay đổi cấu trúc dữ liệu, giảm số phép tính hoặc cache kết quả làm giảm CPU time **và** latency.

**CPU-bound không bắt buộc phải là 100% CPU của cả máy.** Trên máy 16 core, **một** thread giữ kín một core có thể chỉ hiện khoảng 6,25% CPU toàn máy nếu dashboard lấy 16 core làm mẫu số. Với endpoint nối tiếp và chỉ có một worker thực thi bước nặng, một core bão hòa vẫn giới hạn throughput.

### Khi chậm vì chờ tài nguyên

Thời gian chờ có thể phát sinh từ:

- **Network/DB:** socket read chờ response, remote DB đang chạy query, server khác đang quá tải, timeout/retry.
- **Pool:** HTTP connection pool hoặc JDBC pool hết slot; thread chờ acquisition dù database thực tế chưa nhận query.
- **Locks:** Java monitor `synchronized`, `ReentrantLock`, condition, semaphore.
- **Queue/executor:** request đợi slot xử lý; worker rảnh hay busy, queue length và time in queue là dữ liệu quyết định.
- **File/storage:** đọc file, fsync, page cache miss, disk queue.
- **Scheduler:** thread có việc làm nhưng chờ CPU vì quota hoặc tranh chấp host.

Dấu hiệu thường gặp: wall time tăng, thread CPU time thấp; tracing hiển thị các span dependency/pool lớn; JFR có sự kiện `SocketRead`, `ThreadPark`, `JavaMonitorEnter` hoặc thread dump có stack tương ứng. **Tuy nhiên, ứng dụng event-loop/async có thể không có một platform thread “đứng chờ” cho mỗi request**: cần theo dõi future, callback, queue và trace ở cấp request thay vì chỉ nhìn thread states.

### Tình trạng pha trộn

Không nhất thiết chọn chỉ một nhãn. Request có thể tính toán 80 ms, chờ lấy DB connection 100 ms, chạy query 650 ms và serialize response 70 ms. Một thread có thể vừa CPU-bound ở pha parse, vừa I/O-bound ở pha DB. Mục tiêu chẩn đoán là nhận biết **đoạn có tác động lớn nhất** và đánh giá mức đóng góp của từng đoạn.

## 4. Phân rã một request theo critical path

Ví dụ **minh họa** request chậm 990 ms trong một luồng xử lý tuần tự:

| Giai đoạn | Wall time | CPU hay chờ? | Bằng chứng cần có |
| --- | ---: | --- | --- |
| Chờ trong application queue | 120 ms | Chờ scheduler/worker slot | Queue latency/in-flight, executor metrics |
| Chờ lấy JDBC connection | 180 ms | Chờ connection pool | Pool acquire time, active/idle/pending |
| DB thực thi + network round-trip | 540 ms | Phần lớn chờ hệ ngoài; database có thể đang CPU-bound | DB server timings, SQL plan, socket events |
| Business validation/compute | 90 ms | Có thể CPU-bound | Thread CPU delta, execution samples |
| Serialize response | 60 ms | Thường CPU, đôi khi chờ output | CPU samples, write events |
| **Tổng** | **990 ms** | **Pha chờ chiếm ưu thế** | Tổng hợp tracing/measurements |

Nếu chỉ nhìn CPU của Java process, mức thấp không đủ để chứng minh DB chậm; phải phân biệt **pool wait (DB chưa nhận request)** và **query/remote wait (DB đã nhận)**. Một query 540 ms có thể do CPU server cao, lock trong database, I/O của DB, query plan kém hoặc mạng. Mỗi giả thuyết cần bằng chứng phía DB.

Với **công việc song song**, không cộng cơ học thời lượng các span con: hai remote calls cùng mất 400 ms nhưng được chạy song song có thể chỉ đóng góp khoảng 400 ms, không phải 800 ms, vào critical path. CPU time tổng của nhiều threads có thể vượt elapsed của request; đó là điều bình thường khi chạy đồng thời trên nhiều core.

Để giải thích p99, phân tích request **thực sự nằm trong nhóm p99**, không chỉ lấy average của tất cả request hoặc histogram của toàn bộ JVM.

## 5. Checklist các chỉ số phải thu trước khi mở profiler

Chọn một khung thời gian xác định, ví dụ 5 phút khi p95/p99 tăng, và ghi lại release, load, số lượng core/quota, GC, errors, timeout. Thu tối thiểu:

| Nhóm đo | Chỉ số | Vì sao |
| --- | --- | --- |
| Request | RPS/throughput, concurrency/in-flight, p50/p95/p99 theo route, errors, retries | Xác nhận phạm vi và liên hệ tốc độ tải với latency |
| CPU process | Process CPU usage/time, CPU user/system, top threads | Xem CPU execution có tăng không và ở thread nào |
| CPU host/container | Core count, CPU quota, throttling, run queue/pressure, CPU steal | Nhận biết bị giới hạn CPU dù biểu đồ % thấp |
| JVM | GC pause duration, allocation rate, safepoints, thread count | Tránh quy nhầm GC pause thành chờ network |
| Thread pool | Active threads, queue size, queue wait, rejected tasks | Tìm bottleneck xếp hàng dù CPU chưa bão hòa |
| DB pool | Active/idle/pending, connection acquisition time, timeout count | Phân biệt pool exhaustion với DB query chậm |
| Database | Query latency percentiles, active queries, lock waits, pool/connection count | Xem sự cố thuộc JDBC client hay DB server |
| Network/remote | HTTP/gRPC client duration, response code, DNS/TLS timings, connection reuse, retries | Xác nhận external service đang chậm |
| Filesystem | File I/O duration, disk saturation, read/write bytes, filesystem latency | Xác nhận storage là nơi chờ |
| Lock | Contended monitors, park events, lock owner/waiter | Phát hiện serialization và contention |

Một chỉ số riêng lẻ chỉ là **gợi ý**, không phải kết luận. Gắn tên thread/request/span, timestamp và phiên bản release để các bằng chứng có thể nối với nhau. Thông số trên **host nhiều ứng dụng** cần chia rõ process/cgroup, tránh lấy CPU máy làm CPU Java service.

## 6. Ma trận triệu chứng để chọn giả thuyết đầu tiên

| Quan sát đồng thời | Giả thuyết ưu tiên | Kiểm tra ngay | Không nên kết luận |
| --- | --- | --- | --- |
| Latency tăng, một/một vài core bận, thread CPU cao | CPU-bound ở hot method hoặc busy spin | JFR CPU samples, thread CPU deltas, stack trace lặp | “Toàn host CPU dưới 100%, nên không thể CPU-bound” |
| Latency tăng, process CPU thấp, `SocketRead` dài | Chờ remote response/DB/network | Dependency spans, DB/server latency, retries | “CPU thấp nghĩa là tối ưu CPU” |
| Latency tăng, JDBC pool pending tăng, active=max | Pool exhaustion/connection hold quá lâu | Pool acquire histogram, checkout duration, long transaction | “Chắc chắn DB query chậm” |
| Latency tăng, `BLOCKED` cùng monitor lặp lại | Lock contention | Dump nhiều lần, JFR `JavaMonitorEnter`, lock owner | “Nhiều thread tức CPU thiếu” |
| Latency tăng, task queue tăng, worker bận hết | Executor saturation hoặc upstream flood | Pool active/queue/service time, backpressure | “Chỉ cần tăng thread pool” |
| Latency tăng, process CPU gần quota, throttling tăng | Cgroup CPU limit/scheduling | `cpu.stat`, request CPU demand, host pressure | “CPU dashboard 30% nên còn 70% dư” |
| Latency spike trùng GC pause | JVM stop-the-world hoặc GC pressure | JFR GC phases, GC logs | “Network timeout gây GC” |
| Chỉ p99 tăng, average ổn | Tail latency, queueing, retries, lock, GC hay remote outlier | Trace slow request, histograms, correlated time series | “Service nói chung CPU-bound” |

Với workload thay đổi, CPU và latency tăng cùng lúc có thể chỉ vì **traffic tăng**. So sánh cùng RPS, kích thước payload, tỷ lệ cache miss, dataset và concurrency trước–sau; xác định **một thay đổi nhân quả** thay vì tương quan chung.

## 7. Đọc thread dump đúng: `RUNNABLE` không đồng nghĩa đang ăn CPU

Java `Thread.State` là trạng thái do JVM báo cáo, **không phải trạng thái scheduler của OS**:

| Java state | Cách hiểu | Lưu ý khi chẩn đoán |
| --- | --- | --- |
| `RUNNABLE` | Đang có khả năng thực thi trong JVM | Có thể đang chạy, đang chờ được cấp CPU hoặc nằm trong thao tác native I/O; không chứng minh CPU-bound. |
| `BLOCKED` | Chờ lấy **Java intrinsic monitor** để vào/re-enter `synchronized` | Liên hệ lock owner và số lần lặp trong dump; không phải mọi loại chờ đều là `BLOCKED`. |
| `WAITING` | Chờ vô thời hạn, ví dụ `Object.wait()`, `Thread.join()`, `LockSupport.park()` | Có thể là idle worker, queue, future hoặc connection pool; nhiều thread chờ không tự là lỗi. |
| `TIMED_WAITING` | Chờ có hạn, ví dụ `Thread.sleep()`, timed park/wait/join | Hợp lý cho scheduler/timer; stack quyết định chờ có nằm trên critical path không. |
| `NEW`/`TERMINATED` | Chưa chạy/đã kết thúc | Ít giá trị chẩn đoán request latency hiện tại. |

**Hai lỗi suy luận đặc biệt nguy hiểm:**

- Thấy `RUNNABLE` trong `SocketDispatcher.read0` hoặc native I/O và kết luận “mã CPU-bound”: có thể thread **đang chờ dữ liệu** ở tầng hệ điều hành. Đối chiếu thread CPU delta, JFR socket event và trạng thái OS.
- Thấy rất nhiều thread `WAITING`/`TIMED_WAITING` và kết luận “mọi thread đều nghẽn”: nhiều worker đang nhàn rỗi là hoàn toàn bình thường. Phải phân biệt **những request chậm thực sự** đang chờ ở đâu.

Một thread dump là ảnh chụp tức thời. Lấy **nhiều ảnh cách nhau** trong chính khoảng sự cố để xem một stack/lock bị lặp bền vững hay chỉ tình cờ; snapshot một lần có thể bỏ qua đợt chờ ngắn hoặc luôn bắt thread tại điểm đợi thông thường.

## 8. Thu thread dumps và ghép với CPU threads

Dưới đây là lệnh chẩn đoán **trên đúng Java process**, không đặt trong Java source. Thay `<PID>` bằng số process ID thật:

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> Thread.print -l
```

`Thread.print -l` hiển thị thread stacks cùng thông tin locks của `java.util.concurrent` khi runtime hỗ trợ. Đọc tên thread, stack, `nid` và lock owner/waiter. Thường cần ba hoặc nhiều snapshot **cách nhau khoảng 1–2 giây** khi sự cố đang diễn ra, thay vì cố định một ảnh bất kỳ.

**Trên Linux** (lệnh OS minh họa; yêu cầu quyền và công cụ có sẵn):

```bash
top -H -p <PID>
pidstat -t -p <PID> 1 5
ps -L -p <PID> -o pid,tid,stat,pcpu,comm
```

Các lệnh trên giúp xem **OS threads** nào dùng CPU tại thời điểm đo. Khi ghép với thread dump HotSpot, `nid` thường biểu diễn native thread ID ở dạng hex; chuyển decimal TID từ Linux sang hex bằng `printf '%x\n' <TID>` (thay số thật) rồi tìm `nid=0x...`. Mối liên hệ này áp dụng cho **platform/native threads**; virtual threads không có một OS thread riêng cố định.

**Đọc theo cặp bằng chứng:**

1. OS thấy một TID dùng gần trọn một core trong nhiều mẫu.
2. Java dump cùng `nid` liên tục ở một hot loop/call stack.
3. JFR execution samples và thread CPU delta củng cố vị trí mã đang tiêu CPU.

Lúc đó giả thuyết CPU-bound mạnh hơn đáng kể so với chỉ thấy một thread ở `RUNNABLE`. Nếu OS thấy TID hầu như không dùng CPU nhưng Java stack nằm trong `park`/pool acquisition hoặc `SocketRead` thì chuyển sang phân tích nguyên nhân chờ.

**Quyền và môi trường:** `jcmd` cần attach được vào JVM đích với quyền phù hợp, cùng máy/PID namespace. Container image có thể không mang `jcmd`. Lệnh `jcmd 0` không phải lựa chọn an toàn trong production vì có thể gửi lệnh tới nhiều process; luôn xác định đúng PID. Lấy dump quá dày trên hệ thống nhiều thread cũng có chi phí; dùng khoảng lấy mẫu hợp lý.

## 9. Dùng JFR để đối chiếu CPU và sự kiện chờ

Java Flight Recorder giúp thu **time series** thay vì chỉ một ảnh thread dump. Trên HotSpot hỗ trợ, lấy recording ngắn khi incident diễn ra:

```bash
jcmd <PID> JFR.start name=latency settings=profile duration=120s filename=/tmp/latency.jfr
jcmd <PID> JFR.check name=latency
```

Sau khi recording kết thúc và file được tạo:

```bash
jfr summary /tmp/latency.jfr
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad,jdk.ExecutionSample /tmp/latency.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite /tmp/latency.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark,jdk.ThreadSleep /tmp/latency.jfr
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause /tmp/latency.jfr
```

Hoặc mở `/tmp/latency.jfr` bằng **JDK Mission Control (JMC)** để xem CPU, Hot Methods, Call Tree, I/O, thread stalls, locks và GC theo timeline.

**Phân biệt event đúng:**

| JFR event | Câu hỏi | Giới hạn |
| --- | --- | --- |
| `jdk.CPULoad` | JVM/host dùng CPU thế nào theo thời gian? | Không xác định trực tiếp đoạn method đã tiêu CPU. |
| `jdk.ThreadCPULoad` | Platform thread nào có CPU activity cao? | Không phải per-request critical path; phụ thuộc dữ liệu thu. |
| `jdk.ExecutionSample` | Các stack nào thường xuất hiện khi mã đang chạy? | **Lấy mẫu**, không phải đếm thời gian CPU chính xác tuyệt đối; lệ thuộc tần suất và số mẫu. |
| `jdk.SocketRead` / `SocketWrite` | Socket I/O có thời gian chờ dài hay không? | Có threshold; hoạt động async/higher-level có thể không hiện thành một event chặn tương ứng. |
| `jdk.FileRead` / `FileWrite` | File/storage I/O kéo dài ở đâu? | Event coverage/threshold/đặc điểm cache ảnh hưởng kết quả. |
| `jdk.JavaMonitorEnter` | Thread chờ để vào `synchronized` bao lâu? | Không bao quát mọi loại lock/concurrency primitive. |
| `jdk.JavaMonitorWait` | Thread gọi monitor wait trong bao lâu? | Khác monitor-enter contention, cần đọc đúng event. |
| `jdk.ThreadPark` / `ThreadSleep` | Park/sleep chiếm bao lâu? | Park có thể là idle worker, queue, pool hoặc backpressure; stack/correlation mới cho biết. |
| `jdk.GarbageCollection` / `jdk.GCPhasePause` | GC/pause có trùng thời điểm latency spike? | Một GC event không tự giải thích mọi request tail latency. |

Một số sự kiện stall/I/O mặc định chỉ ghi **khi duration vượt ngưỡng**, thường khoảng **20 ms** trong cấu hình phổ biến; kiểm tra file `.jfc` và `JFR.check ... verbose=true` của JVM thực tế. Không thấy `SocketRead` **không chứng minh không có I/O**: nhiều hoạt động ngắn dưới threshold hoặc async I/O có thể không xuất hiện. Nếu cần giảm ngưỡng, thực hiện recording **ngắn**, đo overhead, tránh bật đầy đủ mọi stack trace liên tục trên production.

**Execution samples không phải waiting-time profile**: một thread đang ngủ/chờ network có thể ít hoặc không được CPU sampler bắt, trong khi request vẫn chậm. Đọc execution samples cùng stall events và tracing; đừng lấy số CPU samples làm phần trăm wall time request.

## 10. Tracing để tách chờ network, DB, pool và queue

Điểm mạnh của distributed tracing là đặt thời gian vào **request context**. Một trace tốt nên ghi:

- `request.received` và `handler.start`: request chờ nhận worker hoặc middleware bao lâu?
- `pool.acquire.start` / `pool.acquire.end`: thời gian **chờ connection**, chưa phải DB query.
- `db.query.start` / `db.query.end`: thời gian client quan sát cho query; tách server execution/DB lock nếu phía DB hỗ trợ.
- `http.client.request`: thời gian chờ DNS, connect, TLS, gửi request, nhận response; bao gồm retry nếu client tự retry.
- `serialization` / `response.write`: phần CPU tạo payload và thời gian socket write có chặn hay không.
- `message.queue.wait` và `worker.process`: thời gian đợi queue so với service time.

Mỗi span cần phân biệt **client observed duration** và **server processing duration**. Ví dụ một query mất 400 ms theo Java client nhưng DB reported execution 40 ms; khoảng còn lại có thể do **chờ pool, mạng, driver, fetch result, lock hoặc hàng đợi**. Không được kết luận “SQL chậm 400 ms” nếu chưa tách được các đoạn.

Trên đường async, không nên coi thời gian thread park là thời gian request. Một request có thể chuyển qua nhiều threads/futures/virtual threads. Hãy mang trace ID/request ID đi xuyên suốt; so sánh traces của p50 và p99 trên cùng endpoint.

**Gợi ý logging có kiểm soát:**

```java
long started = System.nanoTime();
try {
    // Gọi dependency hoặc đoạn xử lý cần đo.
} finally {
    long elapsedNanos = System.nanoTime() - started;
    long elapsedMs = java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
    // Ghi span/metric đã gắn route, dependency, status; tránh label cardinality cao.
}
```

Đây là **mảnh minh họa**, không phải chương trình độc lập; cần thay phần comment bằng tác vụ thực. Dùng `nanoTime()` cho duration thay vì trừ hai `currentTimeMillis()` dễ bị tác động bởi thay đổi wall clock. Không log request payload bí mật hoặc một label metric cho từng user/request ID gây bùng cardinality.

## 11. Thực hành Java 17+: đo CPU time so với thời gian chờ socket thực

Ví dụ sau tạo **hai pha có thể tái hiện** trong một JVM:

1. `compute`: thread chính làm phép tính trong khoảng 400 ms bằng vòng lặp.
2. `socket_read`: thread chính đọc một byte từ TCP socket loopback; một thread khác chờ 400 ms rồi mới gửi byte. Thời gian chậm là **chờ dữ liệu từ socket**, không phải CPU-heavy computation của thread chính.

Cả hai pha đo bằng **hai đồng hồ**: `System.nanoTime()` và `ThreadMXBean.getCurrentThreadCpuTime()` trên **platform main thread**. Java code độc lập, không gọi dịch vụ ngoài.

Lưu thành **`CpuVsWaitDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class CpuVsWaitDemo {
    private static volatile long checksum;

    @FunctionalInterface
    interface Work {
        void run() throws Exception;
    }

    private static void measure(
            String name, Work work, ThreadMXBean bean, boolean cpuAvailable)
            throws Exception {
        long wallStart = System.nanoTime();
        long cpuStart = cpuAvailable ? bean.getCurrentThreadCpuTime() : -1L;

        work.run();

        long wallEnd = System.nanoTime();
        long cpuEnd = cpuAvailable ? bean.getCurrentThreadCpuTime() : -1L;

        long wallMs = TimeUnit.NANOSECONDS.toMillis(wallEnd - wallStart);
        long cpuMs = (cpuStart >= 0L && cpuEnd >= 0L)
                ? TimeUnit.NANOSECONDS.toMillis(cpuEnd - cpuStart)
                : -1L;

        String cpuText = cpuMs >= 0L ? Long.toString(cpuMs) : "N/A";
        String ratio = cpuMs >= 0L
                ? String.format(Locale.ROOT, "%.2f",
                        (double) cpuMs / Math.max(1L, wallMs))
                : "N/A";

        System.out.printf(Locale.ROOT,
                "%s wall_ms=%d thread_cpu_ms=%s cpu_wall_ratio=%s%n",
                name, wallMs, cpuText, ratio);
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        boolean cpuAvailable = bean.isCurrentThreadCpuTimeSupported();

        if (cpuAvailable && !bean.isThreadCpuTimeEnabled()) {
            try {
                bean.setThreadCpuTimeEnabled(true);
            } catch (UnsupportedOperationException | SecurityException ignored) {
                cpuAvailable = false;
            }
        }
        if (cpuAvailable) {
            cpuAvailable = bean.isThreadCpuTimeEnabled();
        }

        // Case 1: Tính toán có dùng CPU trên thread chính.
        measure("compute", () -> {
            long deadline =
                    System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(400);
            long value = 1L;
            while (System.nanoTime() < deadline) {
                value = value * 1664525L + 1013904223L;
            }
            checksum = value; // Giữ kết quả để vòng lặp không vô nghĩa.
        }, bean, cpuAvailable);

        // Case 2: Chờ một TCP socket trên loopback, không cần Internet.
        try (ServerSocket server =
                     new ServerSocket(0, 1, InetAddress.getLoopbackAddress())) {
            server.setSoTimeout(3000);

            Thread responder = new Thread(() -> {
                try (Socket peer = server.accept()) {
                    Thread.sleep(400); // Giả lập remote service trả lời chậm.
                    peer.getOutputStream().write(7);
                } catch (Exception ex) {
                    System.err.println(
                            "responder_error=" + ex.getClass().getSimpleName());
                }
            }, "demo-responder");

            responder.start();
            measure("socket_read", () -> {
                try (Socket client = new Socket(
                        InetAddress.getLoopbackAddress(),
                        server.getLocalPort())) {
                    client.setSoTimeout(3000);
                    int response = client.getInputStream().read();
                    if (response != 7) {
                        throw new IllegalStateException("Unexpected response");
                    }
                }
            }, bean, cpuAvailable);
            responder.join();
        }

        System.out.println("DONE");
    }
}
```

Biên dịch/chạy bằng **JDK 17+**, trong môi trường cho phép tạo TCP loopback socket:

```bash
javac --release 17 CpuVsWaitDemo.java
java CpuVsWaitDemo
```

Các số `wall_ms`/`thread_cpu_ms`/`cpu_wall_ratio` **thay đổi theo OS, CPU quota, JIT, scheduler và tải máy**, vì vậy không có một bộ số stdout chính xác chung cho mọi máy. Chương trình in hai dòng số đo có tiền tố `compute` rồi `socket_read`, và cuối cùng in **chính xác**:

```text
DONE
```

Một lần kiểm thử trên JDK 24 có pattern **compute khoảng 400 ms wall với CPU gần wall; socket_read khoảng 400 ms wall nhưng CPU của thread chính gần 0 ms**. Đây là kết quả minh họa, không phải bảo đảm. Trong môi trường CPU throttling hoặc cạnh tranh scheduler, `compute` có thể dùng ít CPU time hơn wall; điều đó minh họa lý do cần đo tài nguyên hệ điều hành khi phân loại.

### Giải thích và giới hạn thí nghiệm

- `compute` không đọc mạng; nó giữ thread bận trong vòng lặp có điều kiện thời gian. `checksum` là biến `volatile` để kết quả được sử dụng ở mức có thể quan sát.
- `socket_read` gọi `InputStream.read()`; thread responder cố ý gửi muộn. Đây là **chờ socket thực trên loopback**, nhưng thời gian server delay do `Thread.sleep` tạo ra trong ví dụ, không phải mô phỏng đầy đủ network congestion.
- `ThreadMXBean` chỉ đếm CPU của **thread đang được đo**, không cộng CPU của responder, GC hay mọi worker trong JVM. Với một API dùng nhiều threads, per-request CPU cần cách đo tương thích với hệ thống xử lý đồng thời.
- `cpu_wall_ratio` là heuristic, không phải nhãn “100% CPU-bound” bắt buộc. Làm tròn millis và thời điểm lấy mẫu có thể tạo giá trị hơi lớn hơn 1.0.
- Nếu JVM không hỗ trợ hoặc không cho bật thread CPU time, output sẽ ghi `N/A`; không được thay bằng số 0 và kết luận thread không dùng CPU.
- Socket có timeout để thí nghiệm không treo vô hạn nếu thiếu phản hồi. Nếu policy sandbox chặn loopback/TCP, chương trình có thể lỗi I/O; hãy chạy trong môi trường cho phép Java mở loopback socket.

**Bước mở rộng:** thay delay ở responder bằng một truy vấn SQL/HTTP request có thể đo được; gắn start/end span và chụp JFR. Khi ấy phải đo **pool wait, remote duration, thread CPU** riêng; không giả định tất cả thời gian bên trong API call là chờ network.

## 12. Cách phân loại sự cố qua các kịch bản production

### Kịch bản A — CPU high, request chậm và một hot method nổi bật

**Quan sát:** p99 tăng khi request rate tăng; một worker TID dùng gần một core, thread CPU delta cao; JFR hot methods lặp tại một regex parser hoặc thuật toán lọc danh sách lớn.

**Giả thuyết:** endpoint **CPU-bound** ở đoạn xử lý. **Hành động:** xác định độ phức tạp với input thực, so sánh CPU/request trước–sau, áp dụng thuật toán/structure phù hợp, giảm parse/serialize lặp, cache có giới hạn, benchmark bằng tải tương đương. **Không** vội tăng thread count: nhiều thread hơn trên core đã bão hòa có thể tăng context switching và hàng đợi.

### Kịch bản B — CPU Java thấp, JDBC query call mất 700 ms

**Quan sát:** trace cho thấy 700 ms trong DB client; Java process CPU thấp. **Nhánh chờ:** cần xem pool acquisition là bao nhiêu, query được DB nhận lúc nào, query plan và server execution, DB lock wait, round-trip/network, fetch result và retries.

**Hành động:** nếu `pool.acquire` mất 600 ms nhưng DB execution chỉ 50 ms, xử lý pool/connection hold/thời gian transaction; tăng pool size vô điều kiện có thể làm DB quá tải. Nếu pool acquire 2 ms nhưng DB server query mất 650 ms, tối ưu SQL/index/transaction isolation và nguồn tài nguyên DB. **Không** gộp cả hai thành “network chậm”.

### Kịch bản C — Thread dump nhiều `WAITING` trong pool và queue dài

**Quan sát:** executor queue depth tăng, worker active=max, CPU process chưa hẳn cao. Một số thread đang `park` đợi completion/future hoặc connection; đây có thể là hậu quả của công việc chờ remote, không phải nguyên nhân gốc.

**Hành động:** đo `queue_wait_ms` và `service_time_ms` riêng; kiểm tra worker bận vì CPU hay chờ I/O. Nếu toàn bộ workers chờ remote, tăng worker đôi khi chỉ dồn thêm requests sang remote và gây **cascading failure**. Cân nhắc bounded queues, timeout, backpressure, bulkhead và giới hạn concurrency có căn cứ.

### Kịch bản D — CPU thấp nhưng `BLOCKED` tăng với cùng monitor

**Quan sát:** nhiều thread đợi vào cùng `synchronized`; JFR `jdk.JavaMonitorEnter` chứa contention kéo dài, thread dump cùng lock owner liên tục.

**Hành động:** giảm critical section, chuyển I/O ra ngoài monitor, dùng dữ liệu bất biến hoặc thiết kế concurrency phù hợp. Xác minh lock holder có đang chờ remote trong synchronized block hay không: **một** call I/O bên trong lock có thể làm chậm hàng trăm request khác, dù process CPU thấp.

### Kịch bản E — CPU trên dashboard không cao nhưng process bị throttle

**Quan sát:** container được cấp quota nhỏ, cgroup `cpu.stat` có `nr_throttled`/`throttled_usec` tăng cùng latency; ứng dụng có nhiều runnable tasks nhưng không được cấp CPU đủ thường xuyên.

**Hành động:** xác định CPU quota/period, throttled duration, CPU requests/limits và host contention; giảm CPU demand hoặc điều chỉnh quota/scheduling theo nhu cầu. **CPU utilization thấp so với toàn host không chứng minh có CPU capacity cho container**. Đọc số liệu theo interval chứ không chỉ nhìn counter tích lũy.

### Kịch bản F — Latency spike đồng thời với GC stop-the-world

**Quan sát:** nhiều endpoint cùng chậm cùng mốc, JFR `jdk.GCPhasePause`/GC logs cho thấy pause. Java handler có thể không cộng nhiều thread CPU time trong khoảng pause nhưng wall latency của request vẫn tăng.

**Hành động:** kiểm tra allocation rate, heap pressure, collector, pause distribution; cải thiện allocation hoặc cấu hình GC nếu dữ liệu chứng minh. Không suy “CPU thấp nên chắc I/O” khi có GC pause hoặc safepoint.

### Kịch bản G — Storage chậm ở bước đọc file

**Quan sát:** JFR `jdk.FileRead` dài, Linux disk I/O latency/queue tăng. Nhưng nếu file nằm hoàn toàn trong page cache hoặc dùng async I/O, quan hệ không đơn giản.

**Hành động:** đối chiếu file size, read pattern, throughput, filesystem, disk capacity và I/O wait phía OS. Tránh quy mọi `FileRead` event cho thiết bị lưu trữ: một số thời gian nằm trong hệ thống file, cache, kernel hoặc shared storage.

### Kịch bản H — HTTP client wait vì DNS/retry/connection pool

**Quan sát:** end-to-end outbound HTTP 900 ms, phía server đích xử lý 80 ms; còn lại có thể là DNS, TCP connect, TLS handshake, queue trong client pool, keep-alive thất bại hoặc retry.

**Hành động:** bật instrumentation cho các giai đoạn client; xem connection reuse, DNS cache, timeouts, retry backoff, server side metrics. Trong tracing, đánh dấu **attempts** riêng thay vì gán toàn bộ 900 ms cho một network round-trip.

## 13. Tại sao “CPU 100%” và “CPU 10%” dễ đánh lừa?

CPU percentage cần biết **mẫu số**:

- Với máy 8 logical CPUs, một thread bận một core ~100% theo công cụ `top` định nghĩa 100% là một core, nhưng chỉ khoảng 12,5% nếu dashboard chuẩn hóa trên cả 8 core.
- Một ứng dụng có hai thread CPU-heavy và hai core có thể có process CPU tương đương 200% theo `top`; đây không có nghĩa đồng hồ sai.
- Container có CPU quota 0,5 core dù host có 16 core: workload cần một core có thể bị throttle mạnh, trong khi biểu đồ trên host rất thấp.
- `load average` bao gồm các loại tasks mà Linux tính vào hệ đo, không phải “CPU utilization %”. Load cao có thể gợi ý runnable contention hoặc tasks chờ I/O; cần điều tra bằng số liệu cụ thể.
- CPU time tăng không chứng minh tiến trình có throughput tốt: busy spin, retry loops, excessive polling, GC hoặc lock contention dạng spin có thể đốt CPU mà không hoàn thành request.

Dùng **CPU time theo khoảng**, CPU quota, số core khả dụng và latency/throughput tương ứng. Với process sử dụng CPU cao nhưng app thread CPU time không tương ứng, điều tra GC threads, JVM background, JIT compiler, native threads hoặc profiler sampling.

## 14. Queueing và saturation: CPU không nhất thiết bão hòa mới có p99 xấu

Nếu arrival rate gần service capacity, **queue time** có thể tăng rất mạnh ngay trước khi metric tổng bộc lộ rõ. Little's Law cho một hệ ở trạng thái ổn định:

```text
L = λ × W

L: số request/job trung bình trong hệ
λ: throughput trung bình (job/giây)
W: thời gian trong hệ trung bình (giây)
```

Ví dụ minh họa: **50 request/giây** và **W=0,4 giây** tương ứng **L≈20 requests in-flight** nếu điều kiện ổn định của hệ phù hợp. Không dùng công thức này để khẳng định p99 vì nó liên hệ **giá trị trung bình** và không tự chỉ ra phân bố tail latency. Trong hệ nhiều lớp queue/pool, cần instrument **mỗi** vùng để tìm nút thắt.

Dấu hiệu cơ bản:

- **CPU saturated + queue tăng:** xem CPU-heavy workers, runnable backlog và khả năng scale/optimize.
- **CPU không saturated + queue tăng:** xem blocking tasks, pool exhaustion, downstream bottleneck, giới hạn concurrency hoặc coordinator thread.
- **Concurrency tăng nhưng throughput không tăng:** đang chạm một giới hạn ở critical path; đẩy thêm concurrency có thể làm p99 xấu hơn.

**Chú ý throughput/cause:** khi I/O-bound, tăng concurrency có thể cải thiện utilization nếu remote chưa quá tải. Nhưng nếu remote đã nghẽn, tăng concurrency làm latency và timeout tăng, chứ không giải quyết nguyên nhân.

## 15. Quy trình điều tra có thể lặp lại từ ngoài vào trong

**Bước 1 — Khóa thời gian sự cố và phạm vi.** Ghi endpoint, p95/p99, RPS, payload, số instances, release, vùng triển khai, request IDs và thời điểm. Đừng lấy JFR ở giờ traffic thấp để giải thích incident buổi trưa.

**Bước 2 — Phân tích CPU capacity.** Xem process CPU, CPU per core, quota/throttling, host pressure và GC. Nếu CPU cao trên vài threads, ưu tiên CPU sampling; nếu CPU thấp, chưa kết luận và chuyển sang tracing/queue.

**Bước 3 — Khoanh vùng critical path.** Dùng distributed trace của slow requests: handler CPU work, task queue, connection pool, DB, remote HTTP, filesystem, serialization và response write. Tách time in queue khỏi time in service. Ghi rõ span song song.

**Bước 4 — Kiểm tra bằng JVM evidence.** Lấy vài thread dumps, JFR ngắn có events CPU/I/O/locks/GC, và một tập metrics phụ thuộc. Bắt đầu bằng cấu hình JFR `profile` ngắn, không bật quá nhiều event đặc thù khi chưa biết cần gì.

**Bước 5 — Chọn giả thuyết có thể bác bỏ.** Ví dụ: “80% p99 nằm ở JDBC pool acquire do connection bị giữ lâu” thay vì “DB có vấn đề”. Dự kiến bằng chứng: pending pool, checkout time, số transactions dài, trace.

**Bước 6 — Thay một biến có kiểm soát.** Tối ưu query, giảm/đổi retry, thử pool timeout, giảm payload hoặc sửa thuật toán. So sánh với cùng RPS/concurrency, cùng data distribution và cấu hình CPU quota. Đo **CPU time/request, critical-path wait time, error rate và p99** sau thay đổi.

**Bước 7 — Xác nhận không dời bottleneck.** Sau tối ưu một đoạn compute, DB có thể trở thành nút thắt kế tiếp; tăng pool size có thể làm DB saturation. Monitor tài nguyên toàn tuyến, không chỉ một chart đã cải thiện.

## 16. Virtual threads và asynchronous I/O: giới hạn của công cụ truyền thống

Từ Java 21, virtual threads có thể phục vụ rất nhiều thao tác chờ I/O mà không giữ một OS thread riêng trong toàn bộ thời gian chờ. Do đó:

- **Không** suy mỗi virtual thread `WAITING`/`TIMED_WAITING` là một OS thread bị lãng phí.
- `java.lang.management.ThreadMXBean` theo dõi **platform threads**, không cung cấp thread CPU time trực tiếp cho từng virtual thread qua các API truyền thống. Một virtual thread có thể chạy trên nhiều carrier/platform threads ở các thời điểm khác nhau.
- OS `top -H`, `pidstat -t` và các `nid` trong thread dump chủ yếu phản ánh **kernel/platform threads**; không dùng chúng để đếm và ánh xạ 1–1 toàn bộ virtual requests.
- Với virtual thread request, đo wall time theo **request/span**, các event JFR hỗ trợ trên JDK đích và số liệu pool/DB/HTTP; không chia CPU time của carrier cho một request tùy ý.
- Với reactive/event-loop, một request có thể không có thread “đứng chờ” riêng; tracing và queue/callback durations mới chỉ ra thời gian chờ thực.

Virtual threads **không làm network/DB nhanh hơn** và không chữa một downstream đã quá tải. Chúng giảm chi phí giữ thread khi nhiều tác vụ chờ. Nếu bottleneck là CPU computation, vẫn cần CPU capacity và tối ưu mã; nếu bottleneck là DB pool nhỏ hoặc query chậm, virtual thread count tăng có thể chỉ làm queue dài hơn.

## 17. Các sai lầm chẩn đoán thường gặp

| Sai lầm | Vì sao sai | Phương án đúng |
| --- | --- | --- |
| “CPU thấp nên chắc chắn chờ network” | Có thể chờ lock/pool, GC pause, CPU quota, idle, hoặc queue | Thu trace + JFR + OS metrics |
| “`RUNNABLE` nghĩa là thread đang chạy trên CPU” | JVM state không bằng OS running state | Ghép OS TID CPU time và stack/JFR |
| “Nhiều `WAITING` nghĩa là deadlock” | Worker idle, `park`, timer là bình thường | Tìm critical path, owner/waiter, deadlock evidence |
| “`BLOCKED` nghĩa là blocked I/O” | Java `BLOCKED` là chờ intrinsic monitor | Xem stack/lock và JFR `JavaMonitorEnter` |
| “CPU process 100% nghĩa là toàn máy hết CPU” | 100% có thể là một core | Biết số core/quota và dashboard mẫu số |
| “Một JFR event 700 ms là DB server xử lý 700 ms” | Client duration gồm network/pool/fetch/retry | Tách client span và server timings |
| “Không có `SocketRead` là không chờ I/O” | Threshold/async path/recording settings có thể bỏ event | Kiểm tra `.jfc`, summary, stack và trace |
| “CPU samples chiếm 80% nên 80% wall của request dùng CPU” | CPU sampling không đo off-CPU request time | So sánh CPU clock và request latency |
| “CPU delta thấp = không thiếu CPU” | OS scheduler/quota có thể làm thread chờ CPU | Xem throttling, run queue, host contention |
| “Chỉ cần tăng threads/pool là nhanh” | Có thể dồn tải vào resource đã bão hòa | Tìm giới hạn throughput, bounded concurrency |
| “Tổng span durations bằng wall request” | Các span có thể overlap | Tính critical path, xem parallel fan-out |
| “Trace average tốt nghĩa là p99 tốt” | Tail requests có thể lệch xa average | Xem p95/p99 và trace slow outliers |
| “Dùng `System.currentTimeMillis()` trừ nhau để đo latency chính xác” | Wall clock có thể chỉnh và độ phân giải thấp | Dùng hiệu `System.nanoTime()` |
| “Với virtual thread thì tính CPU time như platform thread” | `ThreadMXBean` không theo dõi CPU từng virtual thread | Dùng JFR/OS CPU và request-level metrics |

## 18. Checklist trước khi xác nhận nguyên nhân gốc

- [ ] Đã xác định route/request cohort, thời gian, RPS, p95/p99, release, core/quota và workload.
- [ ] Đã đo **wall** và **CPU** khác nhau trên **cùng một khoảng/thread** khi cách đo cho phép.
- [ ] Đã kiểm tra process/per-core CPU, container CPU throttling và OS scheduling.
- [ ] Đã xem GC pause và JVM background activity trùng mốc incident hay không.
- [ ] Đã lấy nhiều thread dumps hoặc JFR có đủ CPU/I/O/lock/park/GC events.
- [ ] Không suy CPU-bound từ `RUNNABLE` hoặc I/O-bound chỉ từ CPU thấp.
- [ ] Đã tách executor queue, DB pool acquisition, DB query, remote HTTP/timeout/retry, file I/O và serialization trên critical path.
- [ ] Đã kiểm tra threshold/coverage của JFR và xác minh recording đúng thời điểm.
- [ ] Đã dùng metrics phía downstream để phân biệt **client chờ** với **server tính toán/chờ**.
- [ ] Đã tính đến request xử lý đồng thời, virtual threads và async I/O; không cộng sai các span song song.
- [ ] Đã đưa ra giả thuyết cụ thể, có cách bác bỏ, rồi thay đổi một biến với cùng tải.
- [ ] Đã đo lại latency distribution, throughput, CPU/request, queue time và errors để chứng minh cải thiện thực.

## 19. Tài liệu chính thức để học sâu

1. Oracle JDK 26, *Troubleshoot Performance Issues Using Flight Recorder* — phân biệt CPU bottlenecks, I/O, synchronization, GC, sự kiện `jdk.ExecutionSample`, `jdk.SocketRead`, `jdk.JavaMonitorEnter` và thresholds: https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html
2. Java SE 21, `ThreadMXBean` — per-thread CPU time, hỗ trợ platform threads và các giới hạn: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html
3. Java SE 21, `Thread.State` — định nghĩa `RUNNABLE`, `BLOCKED`, `WAITING` và `TIMED_WAITING`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html
4. Oracle JDK 21 `jcmd` manual — `Thread.print`, `JFR.start` và diagnostic commands: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
5. Java SE 21, `System.nanoTime()` — đồng hồ đo hiệu khoảng thời gian: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()
6. Java SE 21, `TimeUnit` — chuyển đổi đơn vị thời gian: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeUnit.html
7. Oracle JDK Mission Control — phân tích JFR recordings và timeline: https://www.oracle.com/java/technologies/jdk-mission-control.html

**Kết luận:** “Ứng dụng chậm” phải được chia thành **thời gian CPU thực thi, thời gian chờ dependency/lock/pool/queue, thời gian chờ được scheduler cấp CPU, và pause của JVM**. Wall time cho biết người dùng đã đợi bao lâu; thread CPU time cho biết riêng một platform thread đã tiêu bao nhiêu CPU; JFR, thread dumps, tracing và metrics hệ điều hành mới cho biết **phần chờ nằm ở đâu**. Kết luận tốt nhất là kết luận có số đo trên critical path và có thể kiểm chứng lại sau thay đổi.
