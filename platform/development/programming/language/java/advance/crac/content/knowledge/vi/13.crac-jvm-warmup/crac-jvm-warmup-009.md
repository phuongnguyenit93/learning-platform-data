# Kiểm tra hiệu năng sau restore thay vì suy ra từ trạng thái trước checkpoint

Checkpoint CRaC lưu trạng thái của tiến trình JVM tại một thời điểm để có thể khôi phục tiến trình nhanh hơn. Tuy nhiên, số liệu hiệu năng đo trước checkpoint chỉ mô tả điều kiện tại thời điểm đó. Sau restore, JVM có thể chạy trên một môi trường có CPU, bộ nhớ, network, database, cache và tải khác. Ứng dụng cũng có thể cần làm mới tài nguyên hoặc làm nóng lại một số đường xử lý.

Vì vậy, không nên kết luận ứng dụng vẫn nhanh như trước checkpoint chỉ vì ảnh được tạo từ một phiên chạy đã warm-up. Cần đo lại hiệu năng sau restore theo các giai đoạn cụ thể, từ lúc tiến trình được khôi phục, lúc dependency sẵn sàng, đến khi hệ thống đạt trạng thái phục vụ ổn định.

Một phép đo hữu ích cần trả lời:

- Ứng dụng mất bao lâu để chuyển từ restore đến readiness?
- Request đầu tiên và các request đầu sau restore có độ trễ ra sao?
- Throughput, tỷ lệ lỗi và latency percentile có trở lại mức mong đợi không?
- CPU, heap, GC, thread, code cache và RSS thay đổi thế nào?
- Cache, database pool, DNS, TLS và các kết nối bên ngoài đã thực sự sẵn sàng chưa?
- Có cần warm-up thêm hoặc điều chỉnh cấu hình sau restore không?

## 1. Vì sao phải đo lại sau restore?

CRaC giúp khôi phục trạng thái tiến trình đã checkpoint. Nó không đóng băng toàn bộ môi trường bên ngoài. Trong khoảng thời gian giữa checkpoint và restore, nhiều điều kiện có thể thay đổi:

| Yếu tố | Điều có thể thay đổi sau restore |
|---|---|
| CPU và kiến trúc máy | CPU model, số core được cấp, CPU quota, frequency và contention |
| Bộ nhớ | Memory limit, cgroup pressure, NUMA placement, RSS và áp lực reclaim |
| JIT compiler | Các quyết định tối ưu có thể cần thích nghi với runtime hoặc phần cứng hiện tại |
| Heap và GC | Heap occupancy, allocation rate, GC pause và mức độ phân mảnh |
| Code cache | Dung lượng code đã biên dịch, trạng thái compiler và việc tái biên dịch |
| Cache ứng dụng | Cache còn dữ liệu nhưng có thể stale, hoặc cần nạp lại |
| Database | Connection cũ mất hiệu lực, endpoint failover hoặc database đang quá tải |
| Network và DNS | Địa chỉ, route, TLS session hoặc độ trễ mạng thay đổi |
| Tải hệ thống | Số request đồng thời, traffic pattern và các instance cạnh tranh tài nguyên |
| Filesystem | Page cache, file mapping, storage latency và volume có thể khác |

Một ảnh checkpoint được tạo sau warm-up không phải cam kết rằng mọi request sau restore sẽ có cùng latency. Dữ liệu heap được khôi phục có thể giúp giảm thời gian khởi động, nhưng một số trạng thái phụ thuộc hệ điều hành hoặc dịch vụ bên ngoài vẫn cần được kiểm tra và tái lập.

### Trạng thái trước checkpoint không đại diện cho điều kiện sau restore

Ví dụ, trước checkpoint:

- JVM đã biên dịch một số hot method.
- Cache ứng dụng đã được nạp.
- Database pool có nhiều connection đang hoạt động.
- DNS đã được phân giải.
- TLS connection đã được thiết lập.
- CPU đang nhàn rỗi và không có instance khác tranh tài nguyên.

Sau restore:

- Connection pool có thể phải tạo lại.
- DNS có thể trỏ đến endpoint mới.
- Cache có thể hết hạn hoặc dữ liệu đã thay đổi.
- CPU quota có thể thấp hơn.
- JIT có thể tiếp tục biên dịch hoặc điều chỉnh tối ưu.
- Request đầu tiên có thể kích hoạt class loading, lazy initialization hoặc đường code chưa được chạy trước đó.

Do đó, cần tách hiệu năng của JVM khỏi hiệu năng của ứng dụng và các dependency. Một endpoint chậm sau restore có thể do database reconnect hoặc cache miss, không nhất thiết do JIT hay GC.

## 2. Phân biệt các mốc thời gian sau restore

Không dùng một mốc duy nhất gọi là “startup time” cho mọi mục tiêu. Nên ghi lại các thời điểm:

1. **Restore started**: nền tảng bắt đầu khôi phục ảnh.
2. **Process restored**: JVM tiếp tục thực thi sau restore.
3. **Resources restored**: các CRaC Resource bắt buộc đã xử lý callback.
4. **Application ready**: ứng dụng có thể nhận traffic theo readiness policy.
5. **First request completed**: request đầu tiên hoàn tất.
6. **Warm-up completed**: các đường xử lý cần thiết đã đạt điều kiện warm-up.
7. **Steady state**: throughput và latency ổn định trong cửa sổ đo đã chọn.

Các khoảng thời gian có ý nghĩa khác nhau:

| Chỉ số thời gian | Cách tính | Ý nghĩa |
|---|---|---|
| Restore duration | Process restored − Restore started | Thời gian runtime khôi phục tiến trình |
| Resource recovery duration | Resources restored − Process restored | Thời gian tái lập tài nguyên |
| Time to ready | Application ready − Process restored | Thời gian từ khi JVM tiếp tục đến khi nhận traffic |
| First-request latency | Thời gian hoàn tất request đầu tiên − thời điểm nhận request | Chi phí request đầu sau restore |
| Warm-up duration | Warm-up completed − Application ready | Thời gian đạt điều kiện warm-up |
| Time to steady state | Steady state − Process restored | Thời gian đạt hiệu năng ổn định |

Nên dùng clock đơn điệu như System.nanoTime() để đo khoảng thời gian trong cùng một tiến trình. Dùng Instant hoặc timestamp UTC để ghi mốc sự kiện phục vụ đối chiếu giữa các hệ thống. Không lấy timestamp từ hai máy khác nhau trừ đi nhau nếu chưa xử lý sai lệch đồng hồ.

## 3. Những chỉ số cần theo dõi

Đo hiệu năng sau restore cần nhiều góc nhìn. Một con số latency trung bình hoặc thời gian restore không đủ để kết luận.

### Latency

Theo dõi ít nhất:

- P50: độ trễ ở phân vị 50, đại diện cho request điển hình.
- P90/P95: độ trễ ở phần lớn request, giúp nhận ra tail latency.
- P99: độ trễ ở nhóm request chậm nhất, quan trọng với hệ thống nhạy latency.
- Maximum: dùng để điều tra spike, không nên dùng một mình làm SLO.
- First-request latency: độ trễ của request đầu sau khi readiness mở.

Trung bình có thể che khuất một nhóm request rất chậm. Ví dụ, P50 vẫn tốt nhưng P99 tăng mạnh vì connection pool tạo connection mới hoặc JIT compilation xảy ra trong một số request.

### Throughput và lỗi

Theo dõi:

- Requests per second hoặc operations per second.
- Số request đang chạy đồng thời.
- Tỷ lệ HTTP 5xx, timeout và lỗi nghiệp vụ.
- Tỷ lệ retry và số lần retry.
- Số connection được tạo mới, đóng hoặc thất bại.
- Queue depth và thời gian chờ trong queue.

Throughput cần được so sánh dưới cùng tải đầu vào. Nếu một lần đo có ít request hơn, throughput thấp hơn chưa chắc là regression. Ngược lại, throughput cao trong khi error rate tăng cũng không phải cải thiện.

### CPU và bộ nhớ

Theo dõi:

- CPU utilization và CPU throttling của container.
- Heap used, committed và max.
- Allocation rate và số lần GC.
- GC pause duration và tổng thời gian GC.
- Non-heap memory, Metaspace và Code Cache.
- RSS, container memory và memory pressure.
- Số thread, trạng thái thread và context switching nếu có.

Heap used thấp không đồng nghĩa tiến trình dùng ít RAM. RSS có thể cao do thread stack, direct buffer, native memory, mapped file hoặc các vùng khác ngoài heap. CPU utilization cao có thể do JIT compilation, GC, warm-up, tải request hoặc retry dependency.

### Dependency và cache

Theo dõi:

- Thời gian tạo database pool và thời gian lấy connection.
- Connection validation failure và SQLState.
- Query latency và timeout.
- Cache hit ratio, miss ratio và refresh duration.
- DNS lookup duration và lỗi phân giải.
- TLS handshake duration và lỗi handshake.
- Message broker reconnect, consumer rejoin và queue lag.

Đo riêng các dependency giúp xác định nguyên nhân. Nếu request chậm đồng thời với database connection retry, việc tăng heap hoặc đổi GC có thể không giải quyết được vấn đề.

## 4. Lấy số liệu JVM sau restore

Java Management API cung cấp các MXBean để đọc số liệu runtime. Các giá trị dưới đây nên được ghi ở nhiều mốc, chẳng hạn ngay sau restore, sau readiness và sau warm-up.

Ví dụ:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.ThreadMXBean;
import java.util.List;
import java.util.Locale;

public final class JvmMetrics {

    private static final long MIB = 1024L * 1024L;

    private JvmMetrics() {
    }

    public static void print(String phase) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = memory.getHeapMemoryUsage();
        MemoryUsage nonHeap = memory.getNonHeapMemoryUsage();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();

        System.out.printf(
                Locale.ROOT,
                "phase=%s heap_used_mib=%.1f heap_committed_mib=%.1f heap_max_mib=%.1f%n",
                phase,
                mib(heap.getUsed()),
                mib(heap.getCommitted()),
                mib(heap.getMax())
        );

        System.out.printf(
                Locale.ROOT,
                "phase=%s nonheap_used_mib=%.1f live_threads=%d peak_threads=%d%n",
                phase,
                mib(nonHeap.getUsed()),
                threads.getThreadCount(),
                threads.getPeakThreadCount()
        );

        List<GarbageCollectorMXBean> collectors =
                ManagementFactory.getGarbageCollectorMXBeans();

        for (GarbageCollectorMXBean gc : collectors) {
            System.out.printf(
                    Locale.ROOT,
                    "phase=%s gc=%s count=%d time_ms=%d%n",
                    phase,
                    gc.getName(),
                    gc.getCollectionCount(),
                    gc.getCollectionTime()
            );
        }
    }

    private static double mib(long bytes) {
        return bytes < 0 ? -1.0 : bytes / (double) MIB;
    }
}
~~~

Các bộ đếm GC là số tích lũy từ lúc JVM khởi động. Để so sánh một khoảng thời gian, ghi hai snapshot rồi tính chênh lệch count và time. Giá trị âm có thể biểu thị collector không cung cấp số liệu.

Heap và non-heap trong ví dụ là số liệu JVM, không phải RSS. Để đo RSS và container memory, dùng công cụ hệ điều hành hoặc cgroup. Không thay RSS bằng heap committed.

### Theo dõi JIT và class loading

JIT compilation và class loading có thể ảnh hưởng latency sau restore. Có thể quan sát:

- Số lượng compilation và thời gian compilation qua JMX hoặc JFR.
- Compiler activity và code cache.
- Class loading count và thời gian load class.
- Deoptimization hoặc uncommon trap nếu profile JFR/JVM hỗ trợ.
- CPU tăng trong giai đoạn warm-up.

Không giả định code cache hoặc profiling data trước checkpoint bảo đảm mọi hot path sẽ giữ hiệu năng như cũ. Các giả định tối ưu hóa có thể không còn phù hợp khi tải, CPU hoặc trạng thái dependency thay đổi. Hãy quan sát hành vi compiler và latency thực tế.

### Dùng JFR để phân tích

Java Flight Recorder (JFR) có thể thu thập sự kiện về:

- Execution samples và hot methods.
- JIT compilation.
- Garbage collection và pause.
- Object allocation.
- Thread scheduling và monitor contention.
- Socket/file I/O và một số sự kiện runtime.

Có thể bắt đầu một recording sau restore để thu thập giai đoạn cần quan sát. Ví dụ với jcmd:

~~~bash
jcmd <pid> JFR.start name=after-restore settings=profile duration=5m filename=after-restore.jfr
~~~

Kiểm tra các tùy chọn hỗ trợ bằng lệnh help của JFR trên đúng JDK. Profile recording có overhead; chọn thời lượng và settings phù hợp. Nếu cần so sánh với baseline trước checkpoint, tạo recording có cùng settings và cùng khoảng tải. Không mặc định recording đang chạy trước checkpoint sẽ tiếp tục ghi đúng file hoặc đúng thời điểm sau restore; xác minh recording bằng JFR.check và bắt đầu recording mới khi cần.

## 5. Thiết kế cửa sổ đo sau restore

Một phép đo nên chia thành các cửa sổ để không trộn lẫn khôi phục tài nguyên, warm-up và steady state.

### Cửa sổ A — Ngay sau restore

Ghi nhận:

- Thời điểm process tiếp tục.
- PID, hostname và incarnation ID hiện tại.
- Heap, non-heap, thread count.
- Trạng thái CRaC Resource.
- Thời gian callback và lỗi phục hồi.

Ở giai đoạn này, ứng dụng có thể chưa ready. Không gửi tải nghiệp vụ chỉ để đo latency nếu dependency chưa được phục hồi.

### Cửa sổ B — Sau khi dependency sẵn sàng

Khi database, broker, listener và credential đã được xác minh:

- Ghi thời gian từ restore đến readiness.
- Ghi thời gian tạo pool và số connection.
- Ghi cache hit ratio ban đầu.
- Xác nhận readiness/admission được mở.
- Ghi nhận request đầu tiên.

Đây là lúc có thể đo trải nghiệm thực tế của request đầu sau restore. Không bỏ qua request đầu rồi chỉ báo cáo steady state nếu mục tiêu triển khai yêu cầu latency tốt ngay sau khi instance nhận traffic.

### Cửa sổ C — Warm-up

Chạy các thao tác warm-up đã xác định trước:

- Request đại diện cho hot path.
- Truy vấn database nhẹ và có kiểm soát.
- Nạp cache cần thiết.
- Khởi tạo serializer, template hoặc cấu trúc lazy.
- Kích hoạt đường xử lý cần JIT biên dịch.

Warm-up nên dùng dữ liệu và tải gần với thực tế, nhưng phải giới hạn chi phí. Không gọi hàng loạt endpoint gây side effect hoặc ghi dữ liệu nghiệp vụ chỉ để làm nóng JVM.

### Cửa sổ D — Steady state

Sau khi warm-up hoàn tất, đo trong một khoảng thời gian đủ dài và dưới tải ổn định:

- Throughput.
- P50/P95/P99 latency.
- Error rate.
- CPU, memory và GC.
- Dependency latency.
- Queue depth và connection pool.

Steady state cần được xác định bằng tiêu chí có thể quan sát, không chỉ dựa vào một khoảng sleep cố định. Ví dụ, yêu cầu throughput và latency nằm trong biên độ ổn định qua nhiều cửa sổ liên tiếp.

## 6. So sánh baseline đúng cách

Để đánh giá CRaC có cải thiện trải nghiệm khởi động và hiệu năng sau restore hay không, cần có baseline phù hợp.

Nên phân biệt ít nhất ba luồng:

| Luồng | Cách chạy | Mục đích |
|---|---|---|
| Fresh start | Khởi động JVM mới từ đầu | Baseline khởi động thông thường |
| CRaC restore | Khôi phục từ ảnh checkpoint | Đo thời gian restore và hiệu năng sau restore |
| CRaC restore + warm-up | Restore rồi chạy warm-up có kiểm soát | Đo hiệu năng sau giai đoạn chuẩn bị |

Nếu có số liệu trước checkpoint, lưu chúng như một baseline lịch sử. Không dùng chúng thay cho phép đo sau restore.

### Giữ điều kiện so sánh tương đương

Khi so sánh, cố gắng giữ giống nhau:

- Phiên bản ứng dụng và dependency.
- JDK distribution, version và JVM flags.
- GC collector, heap size và container memory limit.
- CPU quota, số core và loại máy.
- Database version, dataset và trạng thái cache.
- Request mix, concurrency, thời lượng và tốc độ tải.
- TLS, DNS, network path và load balancer.
- Cấu hình connection pool và warm-up.

Nếu môi trường khác nhau, ghi lại khác biệt. Không gán thay đổi latency cho CRaC khi CPU quota, database hoặc tải đầu vào cũng thay đổi.

### Lặp lại phép đo

Chạy nhiều lần restore từ ảnh tương đương và dùng nhiều lần fresh start làm đối chứng. Báo cáo median và độ phân tán, không chỉ chọn lần chạy tốt nhất.

Nếu một lần restore nhanh nhưng các lần khác có tail latency lớn, cần tìm nguyên nhân như connection storm, JIT activity, cache miss hoặc contention. Một kết quả đơn lẻ không đủ để kết luận.

## 7. Đo request đầu tiên và tail latency

Request đầu tiên sau restore thường có đặc điểm khác steady state. Nó có thể kích hoạt:

- Tạo connection mới.
- DNS lookup và TLS handshake.
- Lazy initialization của framework hoặc thư viện.
- Class loading và JIT compilation.
- Cache miss hoặc refresh.
- Khởi tạo thread hoặc executor.

Nên ghi riêng:

1. Latency request đầu tiên.
2. Latency của nhóm request đầu (ví dụ 10, 100 hoặc 1.000 request tùy lưu lượng).
3. P50/P95/P99 trong giai đoạn warm-up.
4. P50/P95/P99 sau khi steady state.

Nếu hệ thống có nhiều route, đo từng nhóm route chính. Một endpoint health nhẹ không đại diện cho API đọc/ghi database hoặc endpoint xử lý CPU nặng.

### Không dùng average làm kết luận duy nhất

Giả sử hai phiên bản có cùng latency trung bình 40 ms. Phiên bản A có P99 là 80 ms; phiên bản B có P99 là 600 ms vì một số request phải tạo lại connection. Trung bình không thể hiện được sự khác biệt về trải nghiệm của nhóm request chậm.

Khi đặt SLO, dùng percentile phù hợp với yêu cầu dịch vụ và theo dõi error rate. Phân tích tail latency cùng queueing time, connection acquisition time và dependency latency.

## 8. Warm-up cache và dependency

CRaC có thể giữ dữ liệu cache trong heap, nhưng cache tồn tại trong bộ nhớ không đồng nghĩa cache còn hợp lệ.

### Cache ứng dụng

Với mỗi cache, xác định:

- Dữ liệu có thể giữ qua thời gian checkpoint hay không.
- TTL có thể đã hết trong lúc tiến trình tạm dừng hay không.
- Có version hoặc invalidation signal từ hệ thống bên ngoài không.
- Cache miss có gây tải đột biến lên database không.
- Có cần nạp trước một tập key phổ biến không.

Cache có thể được giữ nếu dữ liệu vẫn hợp lệ và có chính sách invalidation rõ ràng. Nếu dữ liệu có thể stale, refresh hoặc loại bỏ cache trước khi mở traffic.

### Database pool

Sau restore, connection cũ có thể không dùng được. Đo:

- Thời gian tạo pool.
- Thời gian lấy connection đầu tiên.
- Thời gian validation.
- Connection creation rate.
- Query latency và error rate.

Đừng coi pool object còn trong heap là bằng chứng pool đã sẵn sàng.

### DNS, TLS và HTTP client

Đo DNS lookup, TLS handshake và thời gian thiết lập connection mới. Nếu client giữ connection pool cũ, hãy dùng lifecycle được thư viện hỗ trợ để đóng và tạo lại hoặc làm mới connection. Kiểm tra credential và certificate hiện hành.

### Message broker

Sau restore, consumer có thể phải rejoin group hoặc nhận lại partition. Đo thời gian reconnect, rejoin, consumer lag và thời gian đến message đầu tiên được xử lý. Xác minh offset, ack và idempotency để tránh xử lý trùng.

## 9. Phân tích GC, heap và native memory

Sau restore, heap used có thể cao do cache được giữ lại. Điều này không tự động là lỗi. Cần xem allocation rate, GC frequency, pause time và heap occupancy theo thời gian.

Một số mẫu chẩn đoán:

| Quan sát | Khả năng cần kiểm tra |
|---|---|
| Heap used cao nhưng ổn định, GC ít | Cache hoặc object graph được giữ chủ đích |
| Heap used tăng liên tục | Leak hoặc cache không có giới hạn |
| GC pause tăng sau restore | Allocation burst, heap pressure hoặc collector behavior |
| RSS cao nhưng heap thấp | Native memory, thread stack, direct buffer, mapping |
| CPU tăng cùng compilation | JIT đang biên dịch hot path |
| CPU tăng cùng GC | Allocation pressure hoặc heap sizing |
| P99 tăng nhưng CPU thấp | Network, database, queueing hoặc lock contention |

Không gọi System.gc() chỉ để làm số heap đẹp hơn trong benchmark. Full GC có thể gây pause và thay đổi hành vi ứng dụng. Chỉ thử nghiệm GC chủ động khi có giả thuyết và đo cả lợi ích lẫn chi phí.

Nếu cần Native Memory Tracking, JVM phải được khởi động với cấu hình phù hợp, ví dụ:

~~~bash
-XX:NativeMemoryTracking=summary
~~~

Sau đó có thể xem thống kê bằng jcmd nếu JVM hỗ trợ:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

Native Memory Tracking có overhead và không bao quát mọi allocation từ thư viện native bên ngoài JVM. Kết hợp số liệu NMT với RSS và cgroup memory.

## 10. CPU quota, throttling và môi trường chạy

Ứng dụng restore trên container có thể được cấp CPU quota khác với môi trường tạo checkpoint. CPU quota thấp làm JIT compilation, warm-up, GC và request processing chậm hơn.

Ghi lại:

- Số CPU mà JVM nhìn thấy.
- CPU quota và throttling của cgroup.
- CPU utilization theo container và host.
- Load average hoặc mức cạnh tranh CPU.
- CPU model/architecture nếu môi trường có thể thay đổi.

Đừng chỉ nhìn số core mà JVM báo. Container có thể nhìn thấy nhiều CPU nhưng bị giới hạn quota. Kiểm tra cấu hình cgroup và metric throttling của nền tảng.

Tương tự, memory limit thấp hơn có thể làm GC thường xuyên hơn hoặc khiến tiến trình bị OOMKilled. So sánh RSS, heap và container memory limit trong cùng một cửa sổ.

## 11. Tự động hóa phép đo sau restore

Có thể tạo một bộ đo nhỏ ghi sự kiện lifecycle và snapshot JVM. Ví dụ sau dùng System.nanoTime() để đo khoảng thời gian trong cùng process, đồng thời ghi timestamp UTC để đối chiếu log.

~~~java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;

public final class RestoreTimeline {

    private final AtomicLong processStartNanos =
            new AtomicLong(System.nanoTime());
    private final AtomicLong restoreNanos = new AtomicLong();
    private final AtomicLong readyNanos = new AtomicLong();

    public void markRestored() {
        long now = System.nanoTime();
        // Start a new measurement window for this process incarnation.
        processStartNanos.set(now);
        restoreNanos.set(now);
        readyNanos.set(0);
        log("process_restored");
    }

    public void markReady() {
        readyNanos.compareAndSet(0, System.nanoTime());
        log("application_ready");
    }

    public long timeToReadyMillis() {
        long restored = restoreNanos.get();
        long ready = readyNanos.get();
        if (restored == 0 || ready == 0 || ready < restored) {
            return -1;
        }
        return (ready - restored) / 1_000_000;
    }

    private void log(String event) {
        System.out.printf(
                "event=%s timestamp=%s uptime_ms=%d%n",
                event,
                Instant.now(),
                (System.nanoTime() - processStartNanos.get()) / 1_000_000
        );
    }
}
~~~

Trong ứng dụng thật, gọi markRestored() từ callback hoặc điểm điều phối phù hợp sau khi JVM đã restore; gọi markReady() chỉ sau khi listener và dependency bắt buộc sẵn sàng. Nếu cần phân biệt từng restore attempt, tạo một ID mới cho lần chạy và gắn nó vào log.

Ví dụ trên chỉ đo khoảng thời gian trong process. Thời gian từ lúc orchestrator bắt đầu restore đến lúc process chạy cần được đo ở lớp điều phối vì code Java chưa chạy trong khoảng đó.

## 12. Xác định điều kiện warm-up hoàn tất

Không nên dùng một sleep cố định như “đợi 30 giây rồi mở traffic” nếu không có số liệu hỗ trợ. Thời gian warm-up phụ thuộc:

- Tải và request mix.
- Số hot path cần kích hoạt.
- JIT compilation và class loading.
- Cache và dependency.
- CPU quota và memory pressure.
- Kích thước dữ liệu và số kết nối cần tạo.

Có thể định nghĩa tiêu chí warm-up bằng các điều kiện quan sát:

- Các route quan trọng đã được gọi bằng request đại diện.
- Cache hit ratio đạt ngưỡng phù hợp.
- Database pool có số connection tối thiểu cần thiết.
- Throughput ổn định qua một số cửa sổ đo liên tiếp.
- P95/P99 nằm trong biên độ mục tiêu.
- Error rate và GC pause nằm trong giới hạn.

Warm-up phải idempotent hoặc chỉ chạy một lần cho mỗi incarnation. Không thực hiện side effect nghiệp vụ khi gọi request warm-up. Nếu warm-up có thể kéo dài, giữ readiness hoặc route admission theo chính sách triển khai.

## 13. Điều tra regression sau restore

Khi hiệu năng sau restore kém hơn baseline, đi từ chỉ số tổng thể đến thành phần:

### Bước 1 — Xác định phạm vi

- Chỉ request đầu chậm hay toàn bộ steady state chậm?
- Tất cả route chậm hay chỉ route truy cập database?
- Chỉ một instance bị ảnh hưởng hay mọi instance?
- Latency tăng cùng error rate, CPU, GC hoặc dependency latency?

### Bước 2 — Kiểm tra dependency

Đo database connection acquisition, query latency, DNS, TLS, broker reconnect và cache miss. Nếu dependency chậm, tối ưu JVM có thể không cải thiện được request.

### Bước 3 — Kiểm tra JVM

So sánh heap, allocation, GC pause, compilation activity, class loading, thread count và code cache. Dùng JFR hoặc profiler phù hợp để xác định hot path và contention.

### Bước 4 — Kiểm tra môi trường

Đối chiếu CPU quota, throttling, memory limit, RSS, filesystem và network. Một ảnh restore trên máy có tài nguyên thấp hơn có thể tạo kết quả khác dù code và JVM flags không đổi.

### Bước 5 — Điều chỉnh có giả thuyết

Chỉ thay đổi một nhóm yếu tố mỗi lần, ví dụ warm-up route, pool size hoặc CPU limit. Chạy lại cùng workload và so sánh latency percentile, throughput, error rate và tài nguyên.

## 14. Ví dụ bảng kết quả đo

Một báo cáo nên ghi rõ cửa sổ và điều kiện đo. Bảng dưới là ví dụ minh họa, không phải ngưỡng khuyến nghị chung:

| Chỉ số | Fresh start sau warm-up | Restore ngay sau ready | Restore sau warm-up |
|---|---:|---:|---:|
| Time to ready | 18 s | 2.4 s | 2.4 s |
| First request | 210 ms | 340 ms | 95 ms |
| P50 latency | 42 ms | 68 ms | 40 ms |
| P95 latency | 95 ms | 190 ms | 92 ms |
| P99 latency | 180 ms | 510 ms | 175 ms |
| Throughput | 1,000 req/s | 720 req/s | 1,020 req/s |
| Error rate | 0.1% | 1.2% | 0.1% |

Trong ví dụ, restore giúp rút ngắn time to ready nhưng request đầu và tail latency còn cao. Sau warm-up, hiệu năng trở về gần baseline. Kết quả cho thấy startup nhanh và steady-state performance là hai mục tiêu khác nhau; cần báo cáo cả hai.

Khi lập báo cáo thật, ghi rõ:

- Phiên bản ứng dụng/JDK và JVM flags.
- CPU, memory limit và môi trường triển khai.
- Database/cache state.
- Request mix và concurrency.
- Số lần lặp.
- Độ dài mỗi cửa sổ đo.
- Cách tính percentile và error rate.

## 15. Các lỗi đo lường thường gặp

| Cách đo chưa phù hợp | Vì sao gây hiểu sai | Cách làm tốt hơn |
|---|---|---|
| Dùng số liệu trước checkpoint làm kết quả sau restore | Môi trường và dependency có thể đã thay đổi | Đo snapshot mới sau restore |
| Chỉ báo cáo thời gian restore | Không thể hiện time to ready hoặc request latency | Đo từng mốc lifecycle |
| Chỉ dùng latency trung bình | Che khuất tail latency | Báo P50/P95/P99 và error rate |
| Đo ngay khi dependency chưa sẵn sàng | Kết quả chủ yếu phản ánh lỗi phục hồi | Tách resource recovery khỏi workload performance |
| Dùng workload khác nhau | Không thể so sánh công bằng | Giữ request mix và concurrency nhất quán |
| Chỉ đo một lần | Dễ bị ảnh hưởng bởi biến động môi trường | Lặp lại và báo độ phân tán |
| Dùng sleep cố định để kết luận warm-up | Không phản ánh trạng thái thật | Định nghĩa điều kiện warm-up bằng metric |
| Chỉ nhìn heap used | Bỏ qua native memory và RSS | Đo cả heap, non-heap, RSS và cgroup |
| Chỉ nhìn CPU utilization | Không phân biệt JIT, GC, request và retry | Kết hợp JFR và dependency metrics |
| Bật traffic trước khi readiness | Request lỗi làm méo benchmark và ảnh hưởng người dùng | Giữ admission đóng cho đến khi sẵn sàng |

## 16. Checklist đo hiệu năng sau restore

### Trước khi tạo baseline

- [ ] Ghi phiên bản ứng dụng, JDK, GC và JVM flags.
- [ ] Ghi CPU model/quota, memory limit và cấu hình container.
- [ ] Ghi trạng thái database, cache, broker và network.
- [ ] Xác định request mix, concurrency và thời lượng đo.
- [ ] Xác định mốc restore, resource-ready, application-ready và steady state.

### Sau restore

- [ ] Tạo incarnation ID mới và ghi PID/host hiện tại để chẩn đoán.
- [ ] Ghi time to ready và thời gian từng CRaC Resource.
- [ ] Chỉ gửi workload nghiệp vụ sau khi readiness cho phép.
- [ ] Đo request đầu tiên và nhóm request đầu.
- [ ] Đo P50/P95/P99, throughput và error rate.
- [ ] Ghi heap, non-heap, GC, thread, compilation và code cache nếu có.
- [ ] Đo RSS, cgroup memory, CPU quota và throttling.
- [ ] Đo database pool, query latency, cache hit ratio, DNS/TLS và broker reconnect.
- [ ] Ghi JFR trong cửa sổ cần điều tra nếu cần.

### So sánh và cải thiện

- [ ] Có baseline fresh start và baseline restore.
- [ ] So sánh cùng workload và điều kiện tài nguyên.
- [ ] Lặp lại phép đo nhiều lần.
- [ ] Tách request đầu, warm-up và steady state.
- [ ] Xác định nguyên nhân trước khi thay JVM flags hoặc GC.
- [ ] Đo lại sau mỗi thay đổi và giữ đầy đủ số liệu.

CRaC có thể rút ngắn thời gian khôi phục ứng dụng, nhưng hiệu năng sau restore phải được xác nhận bằng số liệu của chính lần chạy đó. Hãy đo time to ready, request đầu, warm-up và steady state; theo dõi JVM, hệ điều hành và dependency; rồi so sánh với baseline dưới cùng điều kiện. Cách này giúp phân biệt lợi ích khởi động nhanh với hiệu năng phục vụ thực tế và phát hiện sớm các regression do JIT, GC, cache hoặc môi trường bên ngoài.
