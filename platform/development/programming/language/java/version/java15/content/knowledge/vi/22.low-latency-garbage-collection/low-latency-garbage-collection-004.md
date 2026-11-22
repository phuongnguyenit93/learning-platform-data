# Độ trễ đuôi khác với thời gian dừng GC trong Java 15+

## 1. Hiểu đúng hai loại độ trễ

Một dịch vụ Java có thể ghi nhận **GC pause dài nhất chỉ 7 ms** nhưng đồng thời có **request p99.9 lên tới 150 ms**. Hai số liệu này không mâu thuẫn, bởi chúng **không đo cùng sự kiện**:

- **Độ trễ đuôi (tail latency)**: các giá trị chậm nhất trong **phân phối thời gian hoàn thành request/operation**. Các chỉ số thường là `p95`, `p99`, `p99.9` và `max`.
- **Thời gian dừng GC (GC pause time)**: độ dài **một lần hoặc một pha tạm dừng các luồng ứng dụng** vì garbage collection; được ghi qua GC logging hoặc Java Flight Recorder (JFR).
- **GC cycle duration**: thời gian toàn bộ chu kỳ thu gom; với collector concurrent, phần lớn hoạt động có thể diễn ra **khi ứng dụng vẫn đang chạy**, nên không thể gộp toàn bộ thời gian chu kỳ thành STW pause.

`ms` là đơn vị chung, nhưng **đơn vị mẫu** khác nhau: mỗi request là một mẫu latency, mỗi pause GC là một mẫu pause. `p99 của request` không phải `p99 của GC`, và `GC max pause` không phải giới hạn cứng cho thời gian một API trả kết quả.

Bài học này áp dụng cho Java 15 và **JDK hiện hành**. Java 15 là mốc ZGC và Shenandoah trở thành các collector sản xuất được hỗ trợ theo JEP 377/JEP 379, nhưng các JDK mới đã thay đổi một số mode/flag; phần dưới chỉ đề xuất cách làm còn áp dụng hiện nay.

## 2. Ranh giới đo thời gian request quan trọng hơn tên metric

Một request có thể đi qua:

~~~text
Client → Proxy/LB → hàng đợi → Java worker → DB/RPC → serialize → network → Client
                    ↑              ↑           ↑
                  queue          CPU/lock      downstream
~~~

Theo mô hình tuần tự đơn giản:

~~~text
request elapsed ≈ queue wait + app work + downstream wait + network/response
~~~

Đây là **sơ đồ khái niệm**, không phải công thức cộng mọi span ở hệ thống chạy song song: khi các RPC chạy đồng thời, có các khoảng thời gian chồng lên nhau. Nên đo **wall elapsed time từ mốc đầu đến mốc cuối của ranh giới được định nghĩa**, rồi dùng breakdown/spans để tìm thời gian đã tiêu hao ở đâu.

| Ranh giới | Bao gồm | Có thể không bao gồm |
| --- | --- | --- |
| Client round-trip | Từ lúc client gửi tới lúc nhận phản hồi | Chi tiết từng JVM/downstream |
| Edge/LB request | Thời gian nhận/phục vụ tại proxy | Một phần mạng client và các bước trước edge |
| Service ingress → response | Từ entry của service đến completion | Queue/transport trước khi vào service |
| Handler/worker execution | Chạy code handler | **Queue trước handler**, I/O sau handler |
| DB/RPC span | Thời gian gọi downstream cụ thể | Phần còn lại của request |
| GC STW pause | Thời gian JVM stop-the-world ở một giai đoạn GC | Queue, DB, network, lock, JIT, toàn bộ request |

**Không dùng metric `handler_duration_ms` như thể nó là trải nghiệm client** nếu request có thể chờ lâu trong queue trước handler. Với API async, không record thời lượng ngay lúc callback vừa enqueue xong nếu response chưa hoàn tất.

### Các nguyên nhân làm tail tăng dù GC pause ngắn

1. Thread pool hoặc event loop bão hòa: request chờ queue.
2. Database/query plan hoặc connection pool chậm: đợi downstream.
3. Retry/timeout/fan-out: một request chờ nhiều dependency.
4. Thread lock contention, blocking I/O, deadlock nhẹ hoặc contention cao.
5. CPU throttling trong container, scheduler, noisy neighbor, page faults.
6. Warm-up: JIT compilation, class loading, cache miss, TLS handshake.
7. Concurrent GC tranh CPU, allocation stall hoặc heap headroom thiếu **mà không cần một GC STW dài**.
8. GC pause thực sự, safepoint synchronization và các giai đoạn dừng khác của JVM.

GC là **một trong nhiều nguyên nhân có thể**, không phải định nghĩa của tail latency.

## 3. Percentile là vị trí trong một phân phối, không phải giá trị bảo đảm

Giả sử sắp xếp **1.000 request** tăng dần theo latency. Với quy tắc **nearest-rank** được dùng trong ví dụ, vị trí của percentile `p` là `ceil(N × p)` với chỉ số bắt đầu từ 1.

| Nhóm mẫu | Số request | Latency mỗi request |
| --- | ---: | ---: |
| Bình thường | 900 | 12 ms |
| Chậm vừa | 90 | 20 ms |
| Chậm do downstream | 9 | 150 ms |
| Chậm do queue | 1 | 600 ms |
| Tổng | **1.000** | |

Vì vị trí 1–900 có giá trị 12, 901–990 có giá trị 20, 991–999 có giá trị 150 và vị trí 1.000 có giá trị 600:

| Chỉ số | Kết quả theo nearest-rank |
| --- | ---: |
| `mean` | **14,55 ms** |
| `p50` | **12 ms** |
| `p90` | **12 ms** |
| `p95` | **20 ms** |
| `p99` | **20 ms** |
| `p99.9` | **150 ms** |
| `max` | **600 ms** |

`p99=20 ms` **không có nghĩa** request nào cũng ≤20 ms; có **10 request >100 ms** trong chính dữ liệu này. `p99.9=150 ms` vẫn không hiển thị một outlier 600 ms ở vị trí cuối.

**Cẩn trọng khi lấy mẫu:** với chỉ 100 request, “p99.9” có độ phân giải rất kém. Khi xem percentile cần biết **số lượng mẫu, thời gian cửa sổ, loại request và phương pháp percentile** (nearest-rank, nội suy hoặc histogram approximation). Các công cụ telemetry khác nhau có thể trả giá trị p99 hơi khác nhau trên cùng một mẫu.

Cũng đừng lấy trung bình `p99` của mỗi pod/phút để gọi đó là `p99` toàn cluster. Percentile **không gộp bằng trung bình percentile**; muốn đo toàn cluster, cần histogram/distribution có định nghĩa bucket, đơn vị và cửa sổ tương thích.

## 4. GC pause là phân phối của **GC events**, không phải requests

Giả sử trong một khoảng quan sát, JVM ghi nhận **bốn sự kiện STW GC** có thời lượng:

~~~text
2 ms, 3 ms, 5 ms, 7 ms
GC event count = 4
GC total pause duration = 17 ms
GC max pause duration = 7 ms
~~~

Bây giờ đặt cạnh 1.000 request ở mục 3:

~~~text
request p99       =  20 ms  (mẫu: 1.000 requests)
request p99.9     = 150 ms  (mẫu: 1.000 requests)
request max       = 600 ms  (mẫu: 1.000 requests)
GC max STW pause  =   7 ms  (mẫu: 4 pause events)
~~~

Điều đúng: **các con số đo những khía cạnh khác nhau**.

Điều sai: “GC max 7 ms nên GC không thể gây 150 ms latency” hoặc “request p99 20 ms nên JVM đã dừng GC 20 ms”. Chỉ số pause **không trực tiếp trả lời** một request đã trải qua bao nhiêu thời gian ở queue, trong safepoint, ở DB hay đang đợi CPU.

### Khi pause ngắn vẫn có thể kéo dài tail

Trong một hệ thống **gần bão hòa**, 7 ms dừng xử lý có thể làm nhiều request mới đến, queue tăng, và cần thêm thời gian để tiêu hóa backlog sau khi JVM chạy lại. Những request đến **sau pause** có thể vẫn chịu queue wait lâu. Đây là một **cơ chế khuếch đại có thể xảy ra**; không có công thức chung “7 ms pause = 150 ms response”.

Ngược lại, nhiều request chậm 150 ms có thể đến từ DB trong khoảng hoàn toàn không có GC pause. Muốn tìm nguyên nhân cần **dữ liệu timeline + span/queue + tài nguyên**, không chỉ hai con số max và p99.

## 5. GC ảnh hưởng ứng dụng theo nhiều cơ chế

### 5.1. Stop-the-world

Ở các pha STW, các thread ứng dụng tạm dừng. Request đang chạy có thể bị kéo dài, nhưng **không phải mọi request trong cửa sổ đều chắc chắn bị ảnh hưởng như nhau**. Thời điểm request bắt đầu, pha GC, queue và các nhánh công việc quyết định tác động.

### 5.2. Concurrent GC cạnh tranh CPU

Collector low-pause có thể chạy nhiều công việc concurrently với application. Pause STW nhỏ là ưu điểm, nhưng GC threads vẫn cần CPU và băng thông bộ nhớ. Nếu container bị giới hạn CPU, throughput ứng dụng có thể giảm và queue tăng. Một cải thiện trên **GC pause chart** có thể không tạo cải thiện tương ứng ở **request p99**.

### 5.3. Allocation stalls và thiếu headroom

Nếu allocation rate cao, heap gần đầy hoặc collector không kịp thu hồi, luồng cấp phát có thể phải chờ. Một số stalls không được biểu diễn bằng một dòng “GC Pause X ms” tương ứng. Cần đo GC/allocation telemetry, CPU, heap occupancy và memory limit; đừng quy mọi stall thành STW.

### 5.4. Safepoint khác GC

JVM có thể cần safepoint vì nhiều lý do; các khoảng chờ đi tới safepoint cũng có ý nghĩa. **Không phải mọi safepoint đều là GC**, và không phải mọi time gap của request đều do safepoint. Log `-Xlog:safepoint` bổ sung thông tin khi điều tra gián đoạn ngoài GC.

### 5.5. Chu kỳ concurrent không phải STW dài

Một GC cycle dài 300 ms có thể gồm nhiều pha concurrent. Đừng nhìn dòng “Concurrent Mark 300 ms” rồi kết luận mọi application thread đứng im 300 ms. Cần đọc đúng **pause events** và giai đoạn concurrent của collector đang dùng.

## 6. Low-latency GC trong Java 15 và các JDK mới

### 6.1. G1

G1 là collector mặc định phổ biến của HotSpot, cố gắng đạt mục tiêu pause với xác suất cao và cân bằng throughput. Ví dụ một cấu hình mang tính minh họa:

~~~bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=100 -jar app.jar
~~~

`-XX:MaxGCPauseMillis=100` là **pause-time goal/hint**, **không phải SLA cứng** cho mỗi GC event, càng không phải `request p99 ≤100 ms`. Thay đổi mục tiêu pause có trade-off với GC overhead, heap và throughput; cần benchmark trước/sau.

Oracle thường khuyến nghị **bắt đầu bằng G1 mặc định và heap sizing hợp lý**, sau đó điều chỉnh có căn cứ nếu không đạt SLO. Không bó cứng young generation theo cách vô hiệu hóa cơ chế điều chỉnh pause của G1 chỉ vì sao chép một công thức tối ưu cũ.

### 6.2. ZGC hiện hành

ZGC tập trung vào các pause rất ngắn thông qua concurrent work. Ví dụ chọn collector:

~~~bash
java -XX:+UseZGC -Xms2g -Xmx2g -jar app.jar
~~~

**2 GiB là giá trị minh họa**, không phải cấu hình phù hợp cho mọi workload. Heap phải có **headroom** cho live set, allocation spikes, concurrent work và container memory limit. Nếu memory quá ít, ứng dụng vẫn có thể bị allocation stalls hoặc giảm throughput.

**Tránh flag lỗi thời:**

- JDK 21 đưa ra **Generational ZGC** (JEP 439).
- JDK 23 dùng generational mode mặc định cho ZGC (JEP 474).
- Từ **JDK 24**, mode **non-generational ZGC đã bị loại bỏ** và cờ `ZGenerational` không còn được dùng như hướng dẫn JDK 21 (JEP 490).

Trong JDK 24+ chỉ cần `-XX:+UseZGC` để chọn ZGC generational. Không sao chép nguyên `-XX:+ZGenerational` hoặc `-XX:-ZGenerational` từ bài viết của các phiên bản cũ.

### 6.3. Shenandoah

Shenandoah là collector hướng đến low-pause; JEP 379 đưa nó thành lựa chọn production ở Java 15. **Khả năng đóng gói và các cờ/mode cụ thể tùy bản phân phối JDK**. Chỉ dùng nếu provider/runtime của bạn hỗ trợ và đã kiểm chứng. Không giả định mọi JVM đều cung cấp cùng collector.

### 6.4. Chọn collector theo **SLO ứng dụng**

| Tiêu chí | Cần đo khi so collector |
| --- | --- |
| Request latency | `p50/p95/p99/p99.9`, max theo endpoint và workload |
| GC | STW pause distribution, tần suất, cause, allocation stalls |
| Throughput | Completed RPS, offered RPS, xử lý mỗi CPU |
| Độ tin cậy | Timeouts, errors, cancellations, dropped requests |
| Tài nguyên | CPU utilization/throttling, RSS, heap, memory limit |
| Vận hành | Hỗ trợ JDK, logging/diagnostics, khả năng tương thích |

**Đừng tối ưu duy nhất một biểu đồ GC pause.** Một collector có pause ngắn hơn nhưng tiêu hao CPU/memory cao hơn có thể khiến tail của toàn dịch vụ xấu đi.

## 7. Đo request latency đúng bằng `System.nanoTime()`

Khi đo elapsed time **trong một JVM**, `System.nanoTime()` thích hợp hơn trừ hai lần `System.currentTimeMillis()` vì đây là đồng hồ monotonic dùng tính khoảng thời gian, không bị ảnh hưởng trực tiếp khi wall clock thay đổi.

~~~java
long startNs = System.nanoTime();
try {
    // Xử lý tác vụ đồng bộ...
    performRequest();
} finally {
    long elapsedNs = System.nanoTime() - startNs;
    // Ghi elapsedNs vào timer/histogram với đơn vị rõ ràng.
}
~~~

**Đây là mã minh họa, chưa độc lập**, vì `performRequest()`/timer là code ứng dụng.

Đối với async `CompletionStage`/reactive HTTP, `finally` ở hàm enqueue thường kết thúc quá sớm. Cần lưu timestamp lúc request đến và record tại **thời điểm response đã hoàn tất theo ranh giới SLO**, kể cả lỗi/timeout. Nếu request chờ trong queue trước khi handler chạy, bắt đầu đo ở handler sẽ **bỏ qua queue wait**.

Không so sánh trực tiếp giá trị tuyệt đối của `nanoTime()` giữa **hai JVM khác nhau**; nó không phải global timestamp. Khi phân tích sự kiện xuyên JVM, lưu trace IDs, process/pod ID, wall timestamp đã đồng bộ và biên độ sai số đồng hồ.

**Các metric nên tách riêng:**

~~~text
edge_request_ms
service_request_ms
worker_queue_wait_ms
application_cpu_or_work_ms
downstream_db_ms
downstream_rpc_ms
gc_pause_stw_ms
allocation_stall_ms
~~~

Mỗi metric cần định nghĩa boundary và đơn vị. Đừng dùng nhãn `latency` chung chung rồi gộp không có ý nghĩa.

## 8. Lấy GC pause từ JVM Unified Logging

Đối với JDK hiện đại, sử dụng `-Xlog` thay vì các flag GC logging cũ:

~~~bash
java -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

`app.jar` là tên file **minh họa**, không có sẵn trong ví dụ Java bên dưới. `gc*` ghi các nhóm log có tag GC; `safepoint` bổ sung sự kiện safepoint; `time,uptime,level,tags` cung cấp metadata phục vụ correlation.

Các bước đọc log:

1. Xác định **collector**, JVM version, process ID/container, thời điểm và timezone.
2. Tìm các dòng **`Pause ... ms`**; phân biệt young pause, mixed/full pause và các loại khác theo collector.
3. Nhận diện các dòng **`Concurrent ...`**: đây không đồng nghĩa app đứng im trong toàn bộ thời gian.
4. Tìm dấu hiệu allocation failure, heap occupancy cao, full GC, bất thường về CPU/safepoint.
5. Đồng bộ với timeline request của **chính instance đó**, không so một GC log của pod A với p99 tổng cluster rồi kết luận.
6. Giới hạn retention/volume; `gc*` có thể tạo nhiều log. Chọn mức ghi và rotation phù hợp production.

**Không dùng `-Xloggc` hoặc `-XX:+PrintGCDetails` như cấu hình khuyến nghị trong JDK hiện hành**, vì logging hiện đại dùng `-Xlog`.

### `-XX:MaxGCPauseMillis` là mục tiêu, không phải telemetry

~~~text
-XX:MaxGCPauseMillis=50
~~~

Chỉ thể hiện JVM được đề nghị cố đạt pause target. Nó không phải quan sát `p99 pause=50`, không chứng minh `GC max=50` và không phải `request p99=50`. Chỉ logs/JFR mới cho thời gian thực tế của event; chỉ application histogram mới cho percentile request.

## 9. Dùng JFR để xem các event GC

Java Flight Recorder (JFR) ghi nhiều event chẩn đoán; có thể tạo recording như sau:

~~~bash
java -XX:StartFlightRecording=filename=app.jfr,settings=profile,dumponexit=true -jar app.jar
~~~

Sau khi file tồn tại, in GC pause events:

~~~bash
jfr print --events jdk.GCPhasePause app.jfr
~~~

`jdk.GCPhasePause` có dữ liệu thời điểm bắt đầu, duration và thông tin nhận diện GC/phase khi event được ghi. Đây là API/tooling hiện hành được Oracle mô tả trong tài liệu điều tra vấn đề hiệu năng.

**Không hiểu nhầm:**

- Không thấy event trong recording ngắn có thể vì chưa có pause, event chưa bật hoặc recording không bao phủ incident.
- Duration của `jdk.GCPhasePause` không phải elapsed time của HTTP request.
- JFR/profile có chi phí quan sát; không bật heavy recording/heap root analysis trên mọi instance vô thời hạn.
- Cần request tracing ở application; JFR **không tự hiểu đầy đủ logic business và downstream timings**.
- Với collector concurrent, xem cả allocation stalls/CPU nếu nghi tác động không nằm ở STW.

### GC MXBeans không tự trả request tail

`GarbageCollectorMXBean.getCollectionCount()` và `getCollectionTime()` hữu ích cho chỉ số tổng nhưng **không tạo ra từng pause event với timestamp**. Không chia tổng thời gian cho count rồi gọi đó là “p99 GC pause”: đó là dạng trung bình, và cách tính `collectionTime` có thể khác theo collector. Dùng GC logs/JFR để điều tra pause duration cụ thể.

## 10. Đối chiếu timeline: correlation vẫn chưa đủ kết luận nhân quả

Ví dụ thời gian minh họa:

~~~text
10:00:01.100  request X vào JVM
10:00:01.105  GC STW pause bắt đầu
10:00:01.112  GC STW pause kết thúc (7 ms)
10:00:01.250  request X hoàn tất (150 ms)
~~~

GC đã trùng thời điểm request, nhưng **không được kết luận nó giải thích toàn bộ 150 ms**. Cần xem request X chờ queue bao lâu, downstream span có chậm không, CPU scheduling và lock wait ra sao.

Ngược lại, request bắt đầu **sau khi GC kết thúc** vẫn có thể gặp backlog từ một đợt gián đoạn trước đó. Phân tích thời gian nên chia các nhóm trước/trong/sau pause và xem queue depth, offered RPS và throughput.

**Quy trình điều tra:**

1. Đồng bộ **instance/pod/PID**, timestamp và ranh giới request latency.
2. Lấy request traces ở các phần đuôi, không chỉ trung bình.
3. Đánh dấu GC pause và safepoint events lên cùng timeline.
4. Xem queue wait, CPU throttling, downstream wait, allocation stall, thread contention.
5. Đối chiếu cả giai đoạn không có GC pause với cùng mức tải.
6. Thử thay đổi có kiểm soát khi đã có giả thuyết: giảm allocation, điều chỉnh heap, thay collector hoặc xử lý bottleneck khác.
7. Đánh giá request SLO, errors và tài nguyên sau thay đổi.

**Có tương quan về thời gian không tự đồng nghĩa có quan hệ nhân quả**; không bỏ qua GC nhưng cũng không đổ lỗi cho GC chỉ dựa vào con số p99 lớn.

## 11. Chương trình Java đầy đủ: tính percentile và so với pause mẫu

Ví dụ dưới đây tạo **dữ liệu tổng hợp có kết quả xác định**. Nó không ép JVM phải chạy GC, vì `System.gc()` có hành vi phụ thuộc collector/flags và sẽ làm benchmark kém thực tế.

Mỗi `Request` có queue, work, downstream, network được cộng **tuần tự**:

- 900 request: `2+5+3+2 = 12 ms`.
- 90 request: `4+6+8+2 = 20 ms`.
- 9 request: `7+8+130+5 = 150 ms`.
- 1 request: `560+10+20+10 = 600 ms`.

Bốn pause GC giả lập `2, 3, 5, 7 ms` là **tập sự kiện độc lập, không có timestamp liên kết với request**. Chúng chỉ giúp thấy hai phép đo khác nhau; **không thể dùng demo này để chứng minh GC gây ra hoặc không gây ra 150 ms**.

Lưu tên file **`TailLatencyVsGCPauseDemo.java`**, mã hóa UTF-8:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

public class TailLatencyVsGCPauseDemo {
    static final class Request {
        final int queueMs, workMs, downstreamMs, networkMs;
        final String bottleneck;

        Request(int queueMs, int workMs, int downstreamMs,
                int networkMs, String bottleneck) {
            this.queueMs = queueMs;
            this.workMs = workMs;
            this.downstreamMs = downstreamMs;
            this.networkMs = networkMs;
            this.bottleneck = bottleneck;
        }

        int endToEndMs() {
            return queueMs + workMs + downstreamMs + networkMs;
        }
    }

    static int nearestRank(List<Integer> sorted, int perMille) {
        if (sorted.isEmpty() || perMille < 1 || perMille > 1000) {
            throw new IllegalArgumentException("Bad percentile");
        }
        int rank = (sorted.size() * perMille + 999) / 1000;
        return sorted.get(rank - 1);
    }

    public static void main(String[] args) {
        List<Request> requests = new ArrayList<>();
        for (int i = 0; i < 900; i++) {
            requests.add(new Request(2, 5, 3, 2, "normal"));
        }
        for (int i = 0; i < 90; i++) {
            requests.add(new Request(4, 6, 8, 2, "moderate"));
        }
        for (int i = 0; i < 9; i++) {
            requests.add(new Request(7, 8, 130, 5, "downstream"));
        }
        requests.add(new Request(560, 10, 20, 10, "queue"));

        List<Integer> durations = new ArrayList<>();
        long totalLatencyMs = 0;
        int over100Ms = 0;
        int slowDownstream = 0;
        int slowQueue = 0;
        int worstQueueMs = 0;
        for (Request req : requests) {
            int latency = req.endToEndMs();
            durations.add(latency);
            totalLatencyMs += latency;
            if (latency > 100) over100Ms++;
            if ("downstream".equals(req.bottleneck)) slowDownstream++;
            if ("queue".equals(req.bottleneck)) slowQueue++;
            worstQueueMs = Math.max(worstQueueMs, req.queueMs);
        }
        Collections.sort(durations);

        // Independent synthetic GC events, not aligned to request times.
        int[] gcStopTheWorldPausesMs = {2, 3, 5, 7};
        int totalPauseMs = 0;
        int maxPauseMs = 0;
        for (int pause : gcStopTheWorldPausesMs) {
            totalPauseMs += pause;
            maxPauseMs = Math.max(maxPauseMs, pause);
        }

        int p50 = nearestRank(durations, 500);
        int p90 = nearestRank(durations, 900);
        int p95 = nearestRank(durations, 950);
        int p99 = nearestRank(durations, 990);
        int p999 = nearestRank(durations, 999);
        int max = durations.get(durations.size() - 1);
        String mean = String.format(Locale.ROOT, "%.2f",
                (double) totalLatencyMs / requests.size());

        System.out.println("requests=" + requests.size());
        System.out.println("meanLatencyMs=" + mean);
        System.out.println("p50LatencyMs=" + p50);
        System.out.println("p90LatencyMs=" + p90);
        System.out.println("p95LatencyMs=" + p95);
        System.out.println("p99LatencyMs=" + p99);
        System.out.println("p999LatencyMs=" + p999);
        System.out.println("maxLatencyMs=" + max);
        System.out.println("requestsOver100Ms=" + over100Ms);
        System.out.println("slowDownstreamRequests=" + slowDownstream);
        System.out.println("slowQueueRequests=" + slowQueue);
        System.out.println("worstQueueMs=" + worstQueueMs);
        System.out.println("gcEvents=" + gcStopTheWorldPausesMs.length);
        System.out.println("gcTotalPauseMs=" + totalPauseMs);
        System.out.println("gcMaxPauseMs=" + maxPauseMs);
        System.out.println("p999GreaterThanGcMax=" + (p999 > maxPauseMs));
        System.out.println("checks=" + (
                requests.size() == 1000
                && "14.55".equals(mean)
                && p50 == 12 && p90 == 12 && p95 == 20 && p99 == 20
                && p999 == 150 && max == 600
                && over100Ms == 10 && slowDownstream == 9
                && slowQueue == 1 && worstQueueMs == 560
                && totalPauseMs == 17 && maxPauseMs == 7));
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 TailLatencyVsGCPauseDemo.java
java TailLatencyVsGCPauseDemo
~~~

Mã chỉ dùng API khả dụng từ Java 15. Đã **biên dịch thành công với `javac --release 15` và `javac --release 17`**, thực thi trên JDK 24. **Đầu ra chính xác:**

~~~text
requests=1000
meanLatencyMs=14.55
p50LatencyMs=12
p90LatencyMs=12
p95LatencyMs=20
p99LatencyMs=20
p999LatencyMs=150
maxLatencyMs=600
requestsOver100Ms=10
slowDownstreamRequests=9
slowQueueRequests=1
worstQueueMs=560
gcEvents=4
gcTotalPauseMs=17
gcMaxPauseMs=7
p999GreaterThanGcMax=true
checks=true
~~~

**Giải thích:**

- `meanLatencyMs=14.55` rất thấp so với max 600; trung bình che phần đuôi.
- `p99LatencyMs=20` nhưng 10 request vượt 100 ms: percentile không phải max.
- `p999LatencyMs=150` và `maxLatencyMs=600`: p99.9 chưa nhất thiết ghi nhận outlier duy nhất.
- `slowDownstreamRequests=9` và `slowQueueRequests=1` mô tả nguyên nhân của các outlier **trong dữ liệu giả lập**, không phải kết luận từ GC thật.
- `gcMaxPauseMs=7` là **max của 4 sự kiện GC khác**. `p999GreaterThanGcMax=true` chỉ đúng về số học; không chứng minh hay bác bỏ nguyên nhân GC.
- `checks=true` xác nhận 1.000 mẫu, phép nearest-rank và thống kê GC mẫu khớp kỳ vọng.

Nếu muốn đo thật, sử dụng instrumentation tại ranh giới request và log/JFR trong giai đoạn tải phù hợp. **Không sửa chương trình để gọi `System.gc()` theo mỗi request** rồi coi đó là thử nghiệm representative: explicit GC có thể bị JVM xử lý khác nhau, tạo workload giả và không phản ánh sự kiện tự nhiên.

## 12. Benchmark đúng: tránh hiện tượng “coordinated omission”

Một load generator chỉ gửi request mới **sau khi request trước hoàn thành** sẽ tự giảm tốc khi hệ thống bị chậm. Như vậy các request đáng lẽ **đến trong lúc server nghẽn** lại không được gửi, khiến histogram latency trông tốt hơn thực tế. Hiện tượng này gọi là *coordinated omission*.

Khi đánh giá tail của API chịu tải liên tục, cần:

1. Nêu rõ mô hình **open-loop** (arrival rate độc lập với completion) hay **closed-loop** (đợi kết quả rồi gửi tiếp).
2. Ghi cả **offered RPS** và **completed RPS**, queue depth, rejected requests và timeout.
3. Có warm-up để tránh nhầm startup/JIT với steady-state; nhưng vẫn phải đo cold-start riêng nếu thuộc SLO.
4. Dùng payload, tenant, route, DB/cache hit ratio và retry mix tương tự production.
5. Giữ CPU quota/container memory/JDK/heap gần tương đương giữa các bản benchmark.
6. Chạy đủ lâu cho các percentile đuôi có số lượng mẫu đáng tin và thu cả lỗi/timed-out requests.
7. Nếu dùng histogram sửa coordinated omission, hiểu giả định, đơn vị và mẫu bổ sung; không tự nhân đôi dữ liệu mà không có căn cứ.

**Cảnh báo:** p99 của **chỉ request thành công** có thể đột ngột giảm khi nhiều request timeout hoặc bị từ chối. Điều đó **không** chứng tỏ service nhanh hơn. Luôn nhìn cùng error rate, timeout và tổng số request.

## 13. Sổ tay điều tra khi p99 cao, GC pause thấp

Giả sử dashboard nói `p99=250 ms`, GC log của **một instance** ghi pause max 6 ms. Quy trình tốt hơn việc đổi collector ngay:

| Bước | Câu hỏi cần giải |
| --- | --- |
| 1. Scope | P99 của endpoint/pod/tenant/time window nào? Có cùng JVM với GC log? |
| 2. Denominator | Có bao nhiêu request? Có lỗi, timeout, drop hay mẫu ít không? |
| 3. Breakdown | Tail nằm ở queue, app CPU, lock, DB/RPC hay serialization? |
| 4. Correlation | GC event, safepoint, allocation stall và request tail có trùng thời gian? |
| 5. Capacity | CPU quota, runnable threads, queue depth, offered RPS, GC concurrent CPU ra sao? |
| 6. Heap | Live set, allocation rate, headroom, GC cycle/pause có dấu hiệu bất thường? |
| 7. Experiment | Thay một yếu tố có kiểm soát, đo lại toàn bộ request SLO và tài nguyên |
| 8. Rollout | Chỉ deploy khi tail, errors, throughput và resource cost cải thiện phù hợp |

**Hướng xử lý theo nguyên nhân:**

- Nếu pause GC dài thật: kiểm tra heap sizing, allocation pressure, G1 tuning hoặc đánh giá low-pause collector nếu phù hợp.
- Nếu GC pause ngắn nhưng allocation stall nhiều: tăng headroom hợp lý hoặc giảm allocation/live set; xem concurrent GC CPU.
- Nếu queue lớn: giới hạn concurrency, backpressure, điều chỉnh worker pool/capacity hoặc giảm thời gian xử lý.
- Nếu DB chậm: query plan, indexing, connection pool, retry policy, timeout budget.
- Nếu CPU throttling: kiểm tra cgroup/quota và máy chủ; đổi collector chưa chắc giải quyết.
- Nếu tail chỉ lần đầu: warm-up, JIT, class loading và cache.
- Nếu edge p99 cao, handler p99 thấp: kiểm tra queue/proxy/network ngoài handler.

**Không đánh đồng tối ưu GC với tối ưu SLO**. Mục tiêu là latency trải nghiệm thực ở workload phù hợp, không phải mọi pause log đều bằng không.

## 14. Các nhầm lẫn phải tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “GC max 5 ms thì request max ≤5 ms” | Request gồm nhiều pha và chờ đợi khác |
| “p99 request là p99 pause” | Hai phân phối và mẫu khác nhau |
| “Một GC cycle 300 ms là STW 300 ms” | Có thể phần lớn là concurrent |
| “ZGC ít pause nên chắc p99 rất tốt” | Queue/CPU/DB/network vẫn có thể làm tail cao |
| “`MaxGCPauseMillis=50` bảo đảm p99≤50” | Soft goal của GC, không phải SLO request |
| “GC không trùng request nên chắc chắn vô can” | Có thể ảnh hưởng gián tiếp qua backlog/CPU |
| “p99=20 nghĩa là mọi request dưới 20” | 1% chậm nhất có thể rất lớn |
| “Cứ có GC thì mọi outlier đều do GC” | Cần chứng cứ critical path, timestamp và capacity |
| “p99 của mỗi pod trung bình thành p99 cluster” | Percentile không cộng gộp bằng trung bình |
| “GC log trống chứng minh GC không chạy” | Có thể do thời gian ghi, mức log hoặc không có pause trong cửa sổ |
| “MXBean collectionTime/count là p99 pause” | Không; đó là phép chia tổng, không phải percentile |
| “Flag ZGenerational cũ dùng nguyên trên JDK 24+” | Mode/flag cũ đã bị loại bỏ |
| “Chỉ cần latency request thành công” | Timeout/drop/errors là một phần trải nghiệm xấu |
| “Gọi System.gc để benchmark tail thật” | Làm méo workload và không có đảm bảo hành vi thống nhất |

## 15. Checklist thiết lập monitoring cho dịch vụ low-latency

- [ ] Định nghĩa SLO p95/p99/p99.9 ở **đúng ranh giới** (client, edge hay service).
- [ ] Có histogram latency, tổng số mẫu, cửa sổ và unit rõ ràng.
- [ ] Thu error/timeout/rejection và offered/completed throughput.
- [ ] Thu queue wait, downstream spans, CPU, lock, GC pause và allocation stall.
- [ ] Gắn metric/trace với pod/process/instance; đồng bộ timestamp khi đối chiếu JFR/GC log.
- [ ] Phân biệt pause STW với concurrent GC cycle và safepoint khác GC.
- [ ] Không dựa duy nhất vào `MaxGCPauseMillis` hoặc max GC pause để báo đạt SLO.
- [ ] Test G1/ZGC với cùng workload, heap/cgroup/quota và so request tail + cost.
- [ ] Tránh hướng dẫn flag ZGC cũ đã bị loại khỏi JDK 24.
- [ ] Kiểm tra coordinated omission, errors và cỡ mẫu trước khi tin dashboard tail.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao GC pause max 7 ms nhưng request p99.9 vẫn là 150 ms?  
Vì chúng đo **khác tập sự kiện**. Request có thể chờ queue, DB, network hoặc chịu ảnh hưởng GC gián tiếp.

**Câu 2.** P99 request 20 ms có loại trừ một request 600 ms không?  
**Không.** P99 là quantile, không phải max.

**Câu 3.** Vì sao không dùng duration của toàn GC cycle để gọi “STW pause”?  
Vì concurrent phases có thể chạy khi application vẫn hoạt động; phải lọc **GC pause event**.

**Câu 4.** Có phải `-XX:MaxGCPauseMillis=50` bảo đảm request p99 dưới 50 ms?  
**Không.** Đó chỉ là mục tiêu GC, không phải SLO.

**Câu 5.** Trên JDK 24+ chọn ZGC bằng cách nào và cần tránh cờ gì?  
Dùng `-XX:+UseZGC`; không dùng lại `-XX:+ZGenerational`/`-XX:-ZGenerational` từ cấu hình cũ.

**Câu 6.** Khi p99 tăng, các metric nào giúp phân biệt GC với queueing?  
GC pauses/JFR, allocation stalls, queue wait/depth, CPU và trace end-to-end cùng timestamp/instance.

**Câu 7.** Vì sao load generator closed-loop có thể đo tail thấp giả tạo?  
Nó gửi ít request hơn trong lúc server chậm, **bỏ sót** các arrival đáng lẽ xếp hàng khi nghẽn.

**Câu 8.** Có thể lấy trung bình p99 từ 5 pod để ra p99 toàn cụm không?  
**Không.** Phải tổng hợp phân phối/histogram thích hợp, không lấy trung bình percentile.

## Tài liệu chính thức còn áp dụng

- Oracle Java SE 25, **Garbage-First (G1) Garbage Collector** (pause goal và concurrent work): https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html
- Oracle Java SE 25, **G1 GC Tuning** (pause/throughput/heap trade-off): https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html
- Oracle Java SE 25, **Ergonomics** (`-XX:MaxGCPauseMillis` là mục tiêu): https://docs.oracle.com/en/java/javase/25/gctuning/ergonomics.html
- Oracle Java SE 25, **The java Command** (`-Xlog` và `StartFlightRecording`): https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- Oracle Java SE 24, **Troubleshoot Performance Issues Using Flight Recorder** (event `jdk.GCPhasePause`): https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html
- Oracle Java SE 24, **JDK 24 Migration — ZGC mode removal**: https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html
- OpenJDK JEP 377 / JEP 379 — ZGC and Shenandoah Production trong Java 15: https://openjdk.org/jeps/377 ; https://openjdk.org/jeps/379
- OpenJDK JEP 439 / JEP 474 / JEP 490 — Generational ZGC và loại bỏ chế độ non-generational: https://openjdk.org/jeps/439 ; https://openjdk.org/jeps/474 ; https://openjdk.org/jeps/490