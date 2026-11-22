# 1.7 Chọn công cụ chẩn đoán Java theo câu hỏi cần trả lời và mức ảnh hưởng cho phép

Khi một ứng dụng Java có vấn đề trên môi trường thật, câu hỏi quan trọng đầu tiên không phải là “dùng `jstack`, `jmap` hay profiler nào?”, mà là **“cần chứng minh điều gì, phải quan sát tín hiệu nào, và hệ thống chịu được mức can thiệp đến đâu?”**. Một công cụ cho nhiều dữ liệu vẫn là lựa chọn sai nếu dữ liệu không trả lời câu hỏi, bỏ lỡ thời điểm lỗi, hoặc bản thân công cụ làm tình trạng nghiêm trọng hơn.

**Kết quả mong đợi:** người học biết chuyển triệu chứng thành câu hỏi kiểm chứng được; chọn telemetry, thread dump, Java Flight Recorder (JFR), công cụ GC, heap dump, Native Memory Tracking (NMT) hoặc profiler đúng thứ tự; xác định chi phí vận hành; và biết khi nào cần dừng hoặc nâng mức thu thập.

## 1. Chẩn đoán dựa trên câu hỏi, không dựa trên tên công cụ

Một chuỗi suy luận chẩn đoán có năm phần:

1. **Triệu chứng quan sát được:** ví dụ p99 latency tăng từ 200 ms lên 2 s; CPU process tăng; container bị OOMKilled.
2. **Câu hỏi cụ thể:** “Thời gian mất ở CPU, chờ khóa, I/O hay GC?”; “RSS tăng do Java heap hay bộ nhớ native?”.
3. **Bằng chứng phân biệt các giả thuyết:** CPU theo tiến trình và luồng; sự kiện GC; thread stack ở nhiều thời điểm; biểu đồ heap sau GC; phân bổ native theo nhóm.
4. **Ngân sách ảnh hưởng:** được phép thêm bao nhiêu tải CPU, dùng bao nhiêu RAM/đĩa, có chấp nhận tạm dừng ứng dụng hay không, có quyền truy cập JVM hay không.
5. **Quy tắc kết luận:** dữ liệu nào sẽ ủng hộ hoặc bác bỏ giả thuyết và cần mẫu lặp lại đến đâu.

Ví dụ, “API chậm” chưa đủ để lập tức dump heap. Đầu tiên cần biết lỗi có tập trung vào một endpoint, một instance, một khoảng thời gian hay tất cả; request có chờ downstream; CPU, GC, lock contention có cùng thời điểm tăng không. Heap dump thường không trực tiếp trả lời câu hỏi về độ trễ request.

**Tách ba lớp quan sát:**

- **Bên ngoài JVM:** latency, throughput, error rate, queue depth, CPU, RSS, I/O, network, giới hạn cgroup/container. Đây thường là lớp có thể xem đầu tiên và ít can thiệp nhất nếu telemetry đã sẵn có.
- **Bên trong JVM theo thời gian:** heap/GC metrics, thread count, JFR events, GC logs, profiler mẫu. Hữu ích khi vấn đề biến thiên theo tải hoặc chỉ xuất hiện thoáng qua.
- **Ảnh chụp cấu trúc tại một thời điểm:** thread dump, class histogram, heap dump, thông tin class loader. Hữu ích để thấy trạng thái và đối tượng cụ thể, nhưng một ảnh chụp đơn lẻ không chứng minh xu hướng hoặc nguyên nhân.

## 2. Đo “mức ảnh hưởng cho phép” như thế nào?

Mức ảnh hưởng không chỉ là phần trăm CPU. Một lệnh có thể ít tốn CPU trung bình nhưng gây **safepoint/pause**, tăng bộ nhớ đột biến, ghi ra hàng GB dữ liệu, làm lộ thông tin trong heap/stack, hoặc yêu cầu quyền không có trên production.

| Ngân sách thực hành | Ví dụ thu thập | Tác động cần tính đến | Cách dùng |
| --- | --- | --- | --- |
| **T0 — chỉ đọc telemetry đã có** | dashboard, traces, logs, metric CPU/RSS/cgroup | Chủ yếu là chi phí đọc dữ liệu ngoài hệ thống; không chủ động gắn vào JVM | Bắt đầu mặc định khi sự cố đang diễn ra |
| **T1 — truy vấn ngắn, giới hạn** | `jcmd VM.version`, `VM.flags`, `JFR.check`; `jstat -gc` với số mẫu hữu hạn | Quyền attach, lượng đầu ra, tần suất lấy mẫu | Lấy bối cảnh và số liệu trước khi nâng cấp |
| **T2 — snapshot hoặc ghi nhận theo thời gian có kiểm soát** | `jcmd Thread.print`, `GC.heap_info`, JFR `settings=default` trong một khoảng giới hạn | Thread dump/heap info có thể cần phối hợp với JVM; số luồng lớn làm dump đắt hơn; JFR dùng CPU/RAM/đĩa | Khi T0–T1 chưa phân biệt được giả thuyết |
| **T3 — profiling/ghi log chi tiết** | JFR `settings=profile` ngắn hạn; profiler lấy mẫu; tracing/logging mức cao; NMT đã được bật | Overhead tùy cài đặt, tốc độ sự kiện, tải và môi trường; log/recording có thể tăng rất nhanh | Thực hiện có thời hạn, đo ảnh hưởng, có kế hoạch dừng |
| **T4 — thu thập nặng hoặc có thể làm gián đoạn** | `GC.class_histogram`, `GC.heap_dump`; debug dừng tại breakpoint; agent hoặc instrumentation thay đổi hành vi | Có thể gây pause, Full GC, tốn I/O và dung lượng lớn, thay đổi trạng thái tiến trình | Chỉ khi bằng chứng cần thiết tương xứng với chi phí và đã có cửa sổ/điều kiện an toàn |

Đây là **thang quyết định thực hành**, không phải nhãn “Impact” chính thức của JDK. Ví dụ tài liệu `jcmd` gán `Thread.print` mức **Medium** phụ thuộc số thread; `GC.heap_info` là **Medium**; `GC.class_histogram` và `GC.heap_dump` là **High**. `JFR.start` có thể được ghi là **Low**, nhưng **recording `profile` phát sinh nhiều chi phí hơn `default`**. Phải xem `jcmd <pid> help <command>` và đo trên workload thực tế; không bảo đảm một lệnh “low impact” sẽ an toàn tuyệt đối.

Trước khi chạy, nên ghi rõ:

- **Ngưỡng dừng:** CPU phụ tăng đáng kể so với baseline, p99 tăng hoặc lỗi tăng, JVM pause xuất hiện, đĩa sắp đầy, dịch vụ mất ổn định.
- **Giới hạn thu thập:** khoảng thời gian, tần suất mẫu, kích thước recording, thư mục đầu ra, thời hạn giữ dữ liệu.
- **Khả năng thu hồi:** có thể dừng recording/logging, giảm tần suất, xóa artifact đúng quy trình; heap dump đã bắt đầu có thể không dễ hủy mà không có tác dụng phụ.
- **Phạm vi dữ liệu:** heap dump, system properties, stack trace, JFR và logs có thể chứa dữ liệu nghiệp vụ, tham số, tên người dùng hoặc đường dẫn nhạy cảm.

## 3. Ma trận chọn công cụ theo câu hỏi

| Câu hỏi cần trả lời | Tín hiệu cần xem | Bắt đầu với | Khi nào nâng cấp | Rủi ro/cảnh báo |
| --- | --- | --- | --- | --- |
| **CPU tăng do phần nào?** | CPU process/luồng, thời gian CPU theo stack, GC CPU | OS metrics và trace đang có; JFR lấy mẫu thời gian ngắn | JFR `profile` hoặc profiler sampling có stack CPU khi cần quy trách nhiệm cho method | `RUNNABLE` trong dump không đồng nghĩa đang chiếm CPU; sampling có sai số |
| **p95/p99 chậm vì chờ gì?** | Request trace, queue wait, socket I/O, lock, GC pause | Tracing + metrics + JFR `default` | Thread dump theo chuỗi, JFR `profile`, phân tích sự kiện monitor/park/IO | Một thread dump không chứng minh “chậm do khóa” |
| **Ứng dụng treo/deadlock?** | Threads `BLOCKED`, lock owner, chu trình chờ, thay đổi giữa các thời điểm | Hai đến ba thread dump cách nhau phù hợp; `jcmd Thread.print -l` | JFR lock events hoặc phân tích lock graph khi dump không đủ | Dump nhiều lần trên JVM hàng nghìn thread có thể gây ảnh hưởng |
| **GC có gây giật/throughput giảm?** | GC frequency, pause, live heap sau GC, allocation rate | GC metrics/log đã bật; `jstat -gc`; JFR GC events | GC logging có giới hạn, JFR chi tiết; histogram nếu nghi giữ đối tượng | Không kích `System.gc()` chỉ để “thử”; nó làm thay đổi bằng chứng |
| **Java heap có thật sự rò rỉ?** | Live set sau nhiều chu kỳ GC, slope theo tải, retained objects | Heap metrics theo thời gian + JFR allocation/GC | `GC.class_histogram` rồi heap dump và phân tích retained path khi cần | Histogram/dump có impact cao; một snapshot không chứng minh leak |
| **RSS/container memory tăng nhưng heap ổn?** | RSS/PSS, cgroup, direct buffers, native stacks, metaspace, code cache | OS/container metrics + JVM heap/metaspace summary | `VM.native_memory summary` và `summary.diff` nếu NMT đã bật | NMT không bao quát mọi malloc của thư viện native; cần bật sớm |
| **OOM xảy ra ở đâu?** | Loại OOME, stderr, GC logs, cgroup OOMKilled, heap/native size | Phân loại `Java heap space`, `Metaspace`, `Direct buffer memory` hay kernel kill | Heap dump lúc OOME nếu đã cấu hình, hoặc NMT/native tooling đúng nhánh | OOMKilled có thể xảy ra mà JVM không kịp tạo heap dump |
| **Metaspace/class loader tăng?** | Loaded/unloaded classes, metaspace, số class loader | `VM.metaspace basic`, class loading metrics | `VM.classloader_stats` hoặc phân tích heap khi nghi class loader bị giữ | Nhiều class được nạp tự nó chưa đủ kết luận leak |
| **Thông lượng thấp nhưng CPU thấp?** | Hàng đợi, thread pool saturation, connection pool, downstream latency | Metrics/traces ứng dụng, pool metrics, thread dumps | JFR socket/file/lock/park events phù hợp | Đừng chỉ nhìn CPU và kết luận ứng dụng “rảnh” |
| **Crash/JVM native lỗi?** | `hs_err_pid*.log`, core dump, exit code, hệ điều hành, container events | Thu thập log crash và trạng thái hệ thống | Phân tích core/offline bằng công cụ phù hợp bản JDK | Attach công cụ live không giúp tiến trình đã chết; core có dữ liệu nhạy cảm |

**Nguyên tắc chọn:** dùng công cụ **ít ảnh hưởng nhất nhưng đủ phân biệt giả thuyết**. Nếu quan sát thời gian giải thích được lỗi, chưa cần heap dump; nếu câu hỏi cần quan hệ giữ tham chiếu, histogram theo class không thay thế được retained-graph của heap dump.

## 4. Hiểu sức mạnh và giới hạn của từng nhóm công cụ

### 4.1. Metrics, logs, distributed traces

Metrics cho biết **mức độ và xu hướng**; tracing cho biết **request đã tiêu thời gian ở đâu**; logs ghi **sự kiện và ngữ cảnh lỗi**. Các nguồn đã triển khai trước sự cố thường có chi phí bổ sung rất nhỏ khi đọc. Luôn so sánh với baseline cùng loại tải và cùng instance, kèm thời điểm, timezone và đơn vị đo.

Không nhầm CPU của host với CPU tiến trình Java; không nhầm memory limit cgroup với `-Xmx`. RSS bao gồm nhiều thành phần ngoài Java heap; heap used tăng trong một chu kỳ GC bình thường không tự động là leak. Log quá chi tiết, đồng bộ và nhiều thông tin nhạy cảm cũng có overhead; “log là miễn phí” là giả định sai.

### 4.2. `jcmd` và `jstat`: chụp nhanh hoặc lấy mẫu nhẹ

`jcmd` gửi diagnostic commands vào JVM đang chạy; **danh sách lệnh phụ thuộc JDK, vendor, JVM và phiên bản**. Dùng `jcmd <pid> help` để xem lệnh hiện có và nhãn tác động. `VM.version`, `VM.flags` và `JFR.check` thường là bước lấy bối cảnh. `GC.heap_info` cho thông tin heap ở một thời điểm; đừng xem nó như biểu đồ phát triển lâu dài.

`jstat -gc` đọc bộ đếm GC theo khoảng lặp đã định, hữu ích để xác định thay đổi tần suất/khối lượng GC. Những con số đó không tự trả lời “đối tượng nào giữ heap”. Phải đọc đúng collector và ý nghĩa các trường của phiên bản JDK; kiểm tra với log hoặc JFR khi cần phân tích pause.

### 4.3. Thread dump: tốt cho “đang chờ gì?”, kém cho xu hướng dài hạn

`jcmd <pid> Thread.print -l` ghi stack của các thread và thông tin khóa. So sánh **nhiều snapshot** lấy trong đúng thời điểm xảy ra lỗi; tìm thread bị kẹt ở cùng chỗ, lock owner, dấu hiệu deadlock, hàng loạt request chờ cùng resource. State `WAITING`/`TIMED_WAITING` có thể hoàn toàn bình thường ở thread pool; `RUNNABLE` có thể đang ở native I/O. Không suy ra thủ phạm từ một state hay một frame.

Với **virtual threads** (JDK 21+), một số dump/công cụ truyền thống không hiện đủ từng virtual thread như mong đợi. Tra cứu khả năng dump virtual thread của đúng JDK, và ưu tiên JFR hoặc lệnh virtual-thread-aware tương ứng khi cần.

### 4.4. JFR và Java Mission Control (JMC)

JFR ghi sự kiện theo timestamp (CPU, GC, allocation, lock, thread, I/O… tùy event bật). Dùng `settings=default` để bắt đầu với recording có overhead thấp; khi cần stack/sự kiện chi tiết hơn, chạy `settings=profile` **trong một khoảng ngắn**. Bản ghi `.jfr` có thể phân tích bằng công cụ `jfr` hoặc giao diện JMC.

JFR có tính lấy mẫu, ngưỡng và cấu hình sự kiện: **không thấy event không đồng nghĩa không xảy ra hiện tượng**. Recording phải trùng thời điểm lỗi và đúng tiến trình. Cấu hình theo dõi heap statistics, đường đến GC roots, stack sâu hoặc mọi allocation có thể tạo overhead đáng kể; chỉ bật khi câu hỏi thật sự cần.

### 4.5. Class histogram và heap dump: phân biệt “nhiều object” với “ai giữ object”

`GC.class_histogram` thống kê số lượng và kích thước object theo class tại thời điểm đo. Đây là bước định hướng khi nghi tập hợp objects bất thường; lệnh được JDK xếp **High impact**. Nó không nói chính xác root nào đang giữ object và dễ bị nhiễu do workload nhất thời.

`GC.heap_dump` tạo file HPROF để điều tra retained size, dominator tree và GC roots. Đây là lựa chọn muộn vì có thể tạo pause đáng kể, tiêu thụ I/O/đĩa lớn; mặc định lệnh có thể yêu cầu Full GC (tùy tùy chọn), làm thay đổi trạng thái trước khi chụp. File có thể chứa password, token, payload khách hàng: lưu, truyền và xóa theo chính sách bảo mật. Không dump heap chỉ để giải thích spike CPU hay request timeout khi chưa có dấu hiệu vấn đề nằm ở heap.

### 4.6. NMT và công cụ OS cho bộ nhớ native

NMT là tính năng HotSpot để theo dõi các nhóm bộ nhớ mà JVM quản lý. Muốn xem `VM.native_memory summary`, JVM thường phải được **khởi chạy từ đầu** với `-XX:NativeMemoryTracking=summary` (hoặc `detail`); việc bật NMT có overhead. Đặt baseline khi ổn định rồi so `summary.diff` để tìm nhóm tăng: Thread, Class, Code, GC, Internal… NMT không đo toàn bộ cấp phát từ thư viện native không thuộc JVM; ghép thêm RSS/PSS, cgroup và native profiler của hệ điều hành.

Nếu `heap used` không tăng mà RSS tăng, **đừng mặc định là Java heap leak**. Có thể là direct buffers, stack theo số thread, class metadata, JIT code cache, memory-mapped files, allocator/native libraries hoặc đặc tính kế toán bộ nhớ của container.

### 4.7. Profiler sampling, debugger và instrumentation

Sampling profiler (ví dụ async-profiler trên môi trường hỗ trợ) có thể cho CPU/alloc/lock hotspots và flame graph, nhưng quyền truy cập native/perf, cách stack được lấy, tần suất mẫu và cấu hình JVM quyết định overhead và độ chính xác. Xác minh phiên bản, quyền OS/container và đo ảnh hưởng trên hệ thống tương tự trước khi dùng production.

Debugger breakpoint, tracing mọi lời gọi hàm, instrument/agent động hoặc bật debug logs diện rộng có thể thay đổi timing và hành vi; trên hệ thống nhạy latency, ưu tiên mẫu giới hạn và phân tích offline. Không coi attach agent hay sửa JVM flags là hành động “chỉ đọc”.

## 5. Quy trình chọn công cụ trong một sự cố

**Bước 1 — Khoanh vùng.** Ghi rõ instance/pod, PID, thời điểm lỗi, phiên bản JDK/JVM, điều kiện tải, trạng thái GC, giới hạn CPU/RAM/đĩa. Định nghĩa câu hỏi có thể kiểm chứng: “Có phải ≥50% thời gian request nằm ở chờ pool connection?” là giả thuyết, không phải kết luận sẵn.

**Bước 2 — Thu thập lớp T0.** So sánh latency, throughput, errors, CPU, RSS, heap, GC pause, thread/queue/pool metrics, downstream traces trong cùng cửa sổ thời gian. Chọn nhánh CPU, wait/lock, heap/GC, native memory hoặc crash.

**Bước 3 — Đặt ngân sách quan sát.** Ghi khoảng đo (ví dụ 60 giây), chi phí chấp nhận được, khả năng pause, dung lượng đĩa và chỗ lưu artifact; nêu lệnh dừng cho recording. Đánh dấu liệu dữ liệu có nhạy cảm.

**Bước 4 — Lấy đúng bằng chứng mức T1–T2.** Chọn một hoặc vài lệnh có thể phân biệt các giả thuyết. Với lỗi theo thời gian: ưu tiên metric/JFR; với treo/khóa: so sánh nhiều thread dumps; với OOM: phân biệt heap, metaspace, native và OOMKilled trước.

**Bước 5 — Đọc kết quả và bác bỏ giả thuyết.** Ví dụ CPU process thấp, GC pause ít, nhưng traces cho thấy thời gian chờ DB tăng: tiếp tục khảo sát pool/downstream; profiler CPU có thể chưa giải quyết được câu hỏi này. Luôn ghi quan sát **và** lý do kết luận.

**Bước 6 — Chỉ nâng T3–T4 khi còn khoảng trống bằng chứng.** Ghi rõ “vì sao snapshot/recording nhẹ chưa đủ”, chi phí dự đoán, điều kiện vận hành, và cách quản lý file. Nếu tác động vượt ngân sách, dừng, chuyển sang staging/canary hoặc lên kế hoạch thu thập lúc phù hợp.

**Bước 7 — Kết thúc có kiểm chứng.** Tắt recording/log bổ sung, lưu bằng chứng có timestamp và điều kiện tải, đối chiếu metrics trước/sau khi thu thập, hạn chế truy cập artifact. Một bài chẩn đoán tốt kết thúc bằng quyết định tiếp theo cụ thể, không phải đống dữ liệu không được giải thích.

## 6. Lệnh thực hành trên HotSpot JDK 17+ (Linux/macOS)

Các ví dụ dưới đây **chỉ minh họa việc lựa chọn và thực hiện quan sát**, không tự chạy lệnh lên production. Thay `12345` bằng PID của **đúng JVM**; chạy bằng user/quyền phù hợp ở cùng môi trường PID namespace. `jcmd` và `jfr` nằm trong bộ JDK; một image runtime tối giản có thể không cài các công cụ này. Đường dẫn `/tmp` là ví dụ Linux: dùng thư mục có đủ dung lượng và quyền, được phép lưu artifact.

### 6.1. Bắt đầu bằng định danh JVM và bộ đếm GC

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.flags
jcmd 12345 help Thread.print
jcmd 12345 GC.heap_info
jstat -gc 12345 1000 5
```

`jstat` trong ví dụ lấy **5 mẫu**, cách nhau **1.000 ms**, sau đó kết thúc; đây là lấy mẫu có giới hạn. `VM.flags` và `VM.version` giúp diễn giải collector/heap/JDK tương ứng. `GC.heap_info` có nhãn Medium nên không nên gọi liên tục ở tần suất cao chỉ vì lệnh in ra ít dòng. Output cụ thể tùy JVM, collector, tải và thời điểm đo; không gán trước một giá trị GC hay heap cố định.

### 6.2. Khi request bị treo, so sánh thread dumps

```bash
jcmd 12345 Thread.print -l > thread-1.txt
sleep 10
jcmd 12345 Thread.print -l > thread-2.txt
```

Chỉ thực hiện trong cửa sổ có triệu chứng; khoảng cách 10 giây là ví dụ, điều chỉnh theo thời lượng lỗi và mức tác động. So khóa đang sở hữu/chờ, stack lặp, số thread bất thường và trạng thái request. Đừng kết luận deadlock từ một thread ở `BLOCKED`; cần chu trình chờ hoặc bằng chứng tương đương. Với số lượng thread lớn, giảm số lần dump.

### 6.3. Khi cần bằng chứng theo dòng thời gian, ghi JFR có thời hạn

```bash
jcmd 12345 JFR.start name=triage settings=default duration=60s filename=/tmp/triage.jfr
jcmd 12345 JFR.check
# Sau khi recording đủ thời gian và file đã được ghi:
jfr summary /tmp/triage.jfr
jfr print --events jdk.CPULoad,jdk.GarbageCollection /tmp/triage.jfr
```

`settings=default` thường là điểm bắt đầu phù hợp; JFR mặc định theo dõi những event được cấu hình trong `default.jfc`. `JFR.check` dùng xác minh recording đang chạy. Khi cần tìm CPU stack/allocation chi tiết hơn, **sau khi đánh giá ngân sách tác động** có thể chọn một recording ngắn với `settings=profile`. Kiểm tra file đã xuất hiện trước khi chạy `jfr summary`; nếu không có event mong muốn, xem event/settings trước khi kết luận.

### 6.4. Khi nghi native memory tăng và NMT đã bật từ startup

```bash
jcmd 12345 VM.native_memory summary
jcmd 12345 VM.native_memory baseline
# Lặp lại sau một khoảng thời gian/tải có chủ đích:
jcmd 12345 VM.native_memory summary.diff
```

`summary.diff` so với baseline; nếu JVM báo NMT chưa bật, cần lập kế hoạch khởi động lại với cấu hình theo dõi phù hợp, **không suy diễn từ kết quả trống**. NMT không phải bộ đo mọi bộ nhớ native của ứng dụng.

### 6.5. Khi đã đủ lý do nâng lên thu thập mức cao

```bash
jcmd 12345 help GC.class_histogram
jcmd 12345 help GC.heap_dump
# Chỉ chạy sau đánh giá pause, I/O, dung lượng và dữ liệu nhạy cảm:
jcmd 12345 GC.class_histogram > histogram.txt
jcmd 12345 GC.heap_dump /secure/heap-12345.hprof
```

Các lệnh dưới chú thích là **High impact**, không phải bước khám ban đầu. `GC.heap_dump` mặc định có thể yêu cầu Full GC; không đổi sang tùy chọn `-all` một cách máy móc để “giảm ảnh hưởng” vì tập đối tượng thu được và chi phí vẫn có thể khác nhu cầu phân tích. Dung lượng HPROF cần dự trù tương ứng kích thước heap, và file phải được bảo vệ.

## 7. Ba tình huống quyết định cụ thể

**Tình huống A — p99 tăng, CPU tiến trình tăng, nhưng GC pause bình thường.**

- Câu hỏi: ứng dụng dùng CPU vào method nào, hay đang có chờ xen kẽ?
- Bắt đầu: tương quan p99 với CPU, request traces, GC và throughput; xác định một instance đại diện.
- Công cụ kế tiếp: JFR có thời hạn để nhìn CPU samples/stacks và event theo thời gian; profiler sampling phù hợp nếu JFR chưa đủ.
- Không làm vội: heap dump; không có bằng chứng rằng vấn đề nằm ở object retention.
- Kết luận hợp lệ cần: cùng thời điểm tải, stack/hotspot lặp đủ mẫu, phân biệt CPU application với GC/runtime/OS.

**Tình huống B — container dần sát giới hạn memory, heap used sau GC gần như ổn định.**

- Câu hỏi: bộ nhớ tăng nằm ngoài heap ở đâu? JVM internal hay thư viện native/cgroup?
- Bắt đầu: RSS/PSS, cgroup memory, heap committed/used, direct buffer metrics, thread count, metaspace.
- Nếu NMT bật: lấy `VM.native_memory summary`, baseline và diff qua một chu kỳ tải. Nếu không bật: dùng telemetry OS/native hiện có và lập kế hoạch bật NMT ở lần restart phù hợp.
- Không làm vội: GC heap dump chỉ vì container memory tăng; HPROF không đại diện toàn bộ native allocation.
- Kết luận hợp lệ cần: nhóm memory tăng theo thời gian và phép đo được đối chiếu cùng điều kiện tải.

**Tình huống C — API timeout, CPU thấp, số request pending tăng.**

- Câu hỏi: thread bị nghẽn tại lock, connection pool, downstream network hay hàng đợi?
- Bắt đầu: request trace, thread-pool/connection-pool metrics, lỗi và latency downstream.
- Nếu cần snapshot: hai hay ba thread dumps trong lúc lỗi, so owner/waiter và stack lặp; nếu chờ I/O/lock biến thiên nhanh thì dùng JFR events phù hợp.
- Không làm vội: CPU profiler cho vấn đề chủ yếu là waiting; không giả định `WAITING` = deadlock.
- Kết luận hợp lệ cần: chứng cứ chờ ở một resource cụ thể, số lượng request ảnh hưởng và tín hiệu thời gian tương ứng.

## 8. Các bẫy diễn giải và sai lầm thường gặp

1. **Chọn công cụ trước câu hỏi.** Thu cả heap dump, thread dump và profiler rồi mới nghĩ xem tìm gì tạo rủi ro lớn và nhiều dữ liệu nhiễu.
2. **Xem một thời điểm là một xu hướng.** Heap used, `RUNNABLE`, class histogram hoặc một CPU sample đơn lẻ không chứng minh leak, deadlock hay hotspot.
3. **Bỏ qua khác biệt JVM.** Danh sách `jcmd`, tác động và khả năng thu thập virtual thread tùy JDK/vendor/collector; phải hỏi `help` trên đúng JVM.
4. **Nhầm lẫn Java heap với RAM tiến trình.** `-Xmx` không giới hạn toàn bộ RSS; OOMKilled từ kernel/cgroup có thể khác `OutOfMemoryError` của JVM.
5. **Không đo chi phí của phép đo.** Thread dump trên hàng nghìn thread, JFR profile lâu, logging mọi request và heap dump có thể thay đổi chính latency đang điều tra.
6. **Không gắn thời gian và context.** Thiếu timestamp/timezone, PID/pod, version, loại tải và thời điểm thay đổi cấu hình làm dữ liệu khó đối chiếu.
7. **Kết luận khi “không thấy event”.** Sampling, JFR thresholds, tắt event hoặc recording bỏ lỡ cửa sổ lỗi đều có thể là lý do.
8. **Bỏ qua bảo mật dữ liệu.** Heap dump và recording chứa thông tin có thể nhạy cảm; quyền đọc, nơi lưu và thời hạn giữ cần được kiểm soát.
9. **Lặp lệnh High impact để có nhiều mẫu.** Nhiều histogram hoặc heap dump liên tiếp có thể làm pause/I/O nghiêm trọng hơn và phá trạng thái tự nhiên.
10. **Nhầm correlation với causation.** CPU tăng cùng p99 có thể do một nguyên nhân thứ ba; cần stack, trace hoặc chuỗi sự kiện để kiểm chứng cơ chế.

## 9. Mẫu ghi lại quyết định chọn công cụ

| Trường | Ví dụ ghi chép |
| --- | --- |
| Câu hỏi | “P99 tăng do CPU hay chờ connection pool?” |
| Phạm vi | Instance/pod A, PID đã xác minh, JDK/GC cụ thể |
| Cửa sổ triệu chứng | 14:05–14:10, timezone và tải/throughput |
| Bằng chứng đã có | p99, CPU, heap, GC pause, traces, pool queue |
| Ngân sách can thiệp | Chấp nhận recording 60 s; không chấp nhận Full GC hoặc heap dump |
| Công cụ chọn | JFR `default` 60 s và hai thread dumps nếu vẫn thiếu bằng chứng |
| Kết quả mong đợi | Thời gian chờ hoặc CPU stack cùng thời điểm request chậm |
| Tiêu chí dừng | Lỗi/p99 xấu đi khi thu thập, đĩa hoặc resource vượt ngưỡng đã định |
| Kết luận/hành động | Giả thuyết được ủng hộ/bác bỏ, artifact lưu đúng chỗ, bước tiếp theo |

**Câu tự kiểm tra:** Nếu chỉ được làm **một** phép đo tiếp theo và không được gây Full GC, phép đo nào giúp phân biệt tốt nhất hai giả thuyết hàng đầu? Hãy trả lời bằng **câu hỏi → tín hiệu → công cụ → mức ảnh hưởng → kết luận có thể rút ra**, không chỉ bằng tên công cụ.

## Tài liệu tham khảo

- Oracle, [`jcmd` command reference (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): cú pháp, tùy chọn và nhãn Impact của từng lệnh.
- Oracle, [Diagnostic Tools (JDK 21)](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): JFR, thread dumps, native memory và quy trình phân tích.
- Oracle, [`jfr` command reference (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): `summary`, `print` và các thao tác với recording.

Khi áp dụng, ưu tiên tài liệu đúng **phiên bản JDK của tiến trình mục tiêu** và trợ giúp tại chỗ `jcmd <pid> help`.