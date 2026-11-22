# 1.3. Phân biệt lỗi chức năng, độ trễ, thông lượng, treo, thiếu bộ nhớ và JVM crash

Khi một dịch vụ Java “không hoạt động bình thường”, mô tả đó chưa đủ để chẩn đoán. Một phản hồi sai, một yêu cầu phản hồi chậm, một hệ thống xử lý được ít việc, một luồng bị kẹt, một JVM hết bộ nhớ và một tiến trình bị lỗi native là những hiện tượng khác nhau. Chúng có thể xuất hiện cùng lúc nhưng cần được **phân loại theo bằng chứng**, rồi mới tìm nguyên nhân gốc.

**Mục tiêu:** từ quan sát có thời điểm và phạm vi rõ ràng, nhận ra loại sự cố, chọn số đo và chứng cứ đầu tiên, tránh kết luận từ một dấu hiệu đơn lẻ. Bài này xây dựng mô hình phân biệt; chưa thay thế quy trình điều tra sâu về deadlock, GC, heap dump hoặc native crash.

## 1. Đặt đúng câu hỏi trước khi chọn công cụ

Xác định **đơn vị bị ảnh hưởng** (một request, nhóm request, một thread, toàn bộ tiến trình, một pod/container hay cả cụm), **cửa sổ thời gian** (bắt đầu/kết thúc, trước/sau thay đổi) và **kỳ vọng** (kết quả nghiệp vụ, SLO, tốc độ xử lý, tiến độ của tác vụ). Cùng một chỉ báo có ý nghĩa khác nhau ở các phạm vi này.

| Nhóm hiện tượng | Câu hỏi quyết định | Bằng chứng nhận diện đầu tiên | Không được suy ra vội |
| --- | --- | --- | --- |
| **Lỗi chức năng** (functional failure) | Kết quả có đúng đặc tả và trạng thái dữ liệu không? | Input, expected/actual output, invariant bị vi phạm, exception/trace | HTTP 200 luôn đúng; HTTP 500 luôn do bug nghiệp vụ |
| **Độ trễ** (latency degradation) | Một công việc hoàn thành mất bao lâu? | Thời gian end-to-end và theo bước, p50/p95/p99 theo endpoint | Trung bình tốt nghĩa là tail latency tốt |
| **Thông lượng** (throughput degradation) | Mỗi đơn vị thời gian hoàn thành được bao nhiêu việc, với tải đầu vào nào? | Arrivals/s, completions/s, success/s, queue depth, saturation | Requests/s thấp tự động là sự cố nếu nhu cầu vốn thấp |
| **Treo/mất tiến độ** (hang/stall) | Tiến trình còn sống nhưng công việc có ngừng tiến triển bất thường không? | Heartbeat/progress marker, thời gian chờ, nhiều thread dump liên tiếp | Một thread ở WAITING/BLOCKED chứng minh JVM deadlock |
| **Thiếu bộ nhớ** (memory exhaustion/pressure) | Có thiếu heap, non-heap, native memory hoặc vượt giới hạn container không? | Loại OOME, heap/GC, RSS, native allocation, cgroup OOM event | Heap used cao đồng nghĩa memory leak |
| **JVM crash** (fatal VM/native failure) | JVM có kết thúc bất thường do lỗi fatal của VM/native code không? | Fatal error log, `hs_err_pid*.log`, tín hiệu như SIGSEGV, core dump | Mọi trường hợp process chết là JVM crash |

Một sự cố có thể có **nhiều nhãn triệu chứng**: ví dụ GC kéo dài gây tăng độ trễ và giảm thông lượng; thread pool cạn khiến request treo; thiếu bộ nhớ có thể dẫn đến tiến trình thoát. Ghi nhận tất cả, rồi phân biệt **triệu chứng đo được**, **cơ chế gây ra** và **nguyên nhân gốc**. Chỉ gọi “crash” khi có chứng cứ phù hợp với kiểu kết thúc đó.

## 2. Nhận diện sâu từng nhóm

### 2.1. Lỗi chức năng: “trả về cái gì?”

Lỗi chức năng xuất hiện khi hành vi quan sát được không khớp hợp đồng: tính sai tiền, trả dữ liệu sai chủ sở hữu, lưu sai trạng thái, làm mất sự kiện, vi phạm quy tắc idempotency, hoặc ném exception thay vì trả kết quả đã cam kết. Một request có thể trả **200 OK nhưng sai nghiệp vụ**; ngược lại một phản hồi 4xx có thể hoàn toàn đúng hợp đồng.

Cách xác minh: lưu input tối thiểu có thể tái hiện, trạng thái phụ thuộc, expected/actual, request ID/trace ID, bản build và đường đi xử lý; đối chiếu test, specification hoặc invariant. Nếu tỷ lệ lỗi tăng đồng thời với timeout, OOME hay crash, cần tìm **nguyên nhân vận hành** đứng sau lỗi trả về, thay vì tự động kết luận thuật toán sai.

### 2.2. Độ trễ: “mất bao lâu để hoàn thành?”

Latency là thời gian từ mốc bắt đầu đến mốc kết thúc của **một lần xử lý**. Phải ghi rõ đo ở client, gateway hay trong JVM; client latency còn có thể gồm DNS, mạng, TLS, retry và hàng đợi. Thời gian từng đoạn (queue wait, DB, lock, GC pause, xử lý ứng dụng) giúp định vị chi phí. Request timeout thường là **kết quả vượt deadline**, chưa chỉ ra nguyên nhân.

Dùng phân vị p50/p95/p99 cùng số mẫu, cửa sổ thời gian, endpoint/loại request và trạng thái thành công hay lỗi. Trung bình có thể che đuôi phân phối; không cộng trực tiếp các p95 của nhiều bước để suy ra p95 end-to-end. Phân vị trên 10 request chỉ minh họa phép tính, chưa đủ đại diện cho một hệ thống sản xuất.

### 2.3. Thông lượng: “xử lý được bao nhiêu việc?”

Thông lượng là số **công việc hoàn thành** trên một đơn vị thời gian: requests/s, transactions/s, messages/s. Phân biệt:
- **Arrival/offered load:** việc đi vào hệ thống mỗi giây.
- **Completion throughput:** việc hoàn tất (kể cả thành công/thất bại nếu phép đếm quy định vậy).
- **Successful throughput:** việc thành công mỗi giây.
- **Concurrency/queue:** việc đang chạy hoặc đang chờ, không phải thông lượng.

Ví dụ trong 30 giây có 240 việc đến, 180 việc hoàn thành, 165 việc thành công: arrival = 8/s, completion = 6/s, success = 5,5/s. Nếu không có hủy/bỏ việc và cách đếm nhất quán, backlog tăng ròng 60. Khi tăng tải mà completion throughput không tăng, queue và latency tăng, hãy nghi **bottleneck/saturation** (CPU, pool, lock, I/O, DB, rate limit). Nếu requests/s thấp chỉ vì không có người dùng, không thể gọi đó là suy giảm khả năng xử lý.

Ở trạng thái ổn định với điều kiện đo và phạm vi nhất quán, định luật Little cho quan hệ trung bình **L = λ × W** (số việc trong hệ thống = tốc độ hoàn thành × thời gian lưu lại). Đây là công cụ kiểm tra tính hợp lý của phép đo, không là bằng chứng tự đủ về nguyên nhân.

### 2.4. Treo: “còn sống nhưng có tiến độ không?”

Một JVM **alive** vẫn có thể không xử lý được việc: deadlock của khóa, đợi I/O không timeout, chờ Future/condition vô hạn, pool cạn, tất cả worker đều bị giữ, livelock hoặc vòng lặp CPU không tạo tiến độ. Có trường hợp chỉ **một request** bị kẹt, còn hệ thống vẫn đáp ứng request khác; phải nêu đúng phạm vi.

Chứng cứ tốt hơn một thread state đơn lẻ là: không có completion/heartbeat mới qua nhiều chu kỳ kỳ vọng, và các thread dump hoặc JFR liên tiếp cho thấy cùng chuỗi chờ/khóa/đường gọi. Thread ở `WAITING`, `TIMED_WAITING` hoặc `BLOCKED` có thể hoàn toàn bình thường (ví dụ worker chờ việc). `RUNNABLE` cũng không bảo đảm tiến độ; nó có thể đang quay vòng hoặc bị kẹt trong native I/O. Dò deadlock Java monitor bằng thread dump hoặc `ThreadMXBean.findDeadlockedThreads()`, nhưng không phải mọi kiểu treo đều là deadlock.

Phân biệt **rất chậm** với **không tiến triển** bằng deadline, số công việc hoàn thành theo thời gian và lặp lại phép quan sát. Không tuyên bố “JVM treo” chỉ vì một lần HTTP timeout.

### 2.5. Thiếu bộ nhớ: “thiếu bộ nhớ loại nào?”

Trong Java 17+, thiếu bộ nhớ không đồng nghĩa với mỗi Java heap. Đọc **đúng thông điệp** và quan sát giới hạn thực tế:

| Dấu hiệu | Hướng điều tra |
| --- | --- |
| `OutOfMemoryError: Java heap space` | Đối tượng sống, retention, heap usage sau GC, kích thước heap; phân biệt tải lớn với leak |
| `OutOfMemoryError: GC overhead limit exceeded` | GC quá thường xuyên nhưng thu hồi ít; xem GC log/heap và áp lực cấp phát |
| `OutOfMemoryError: Metaspace` | Class metadata, class loader và việc tạo/nạp lớp |
| `OutOfMemoryError: Direct buffer memory` | Giới hạn và vòng đời direct buffers, bộ nhớ off-heap |
| `OutOfMemoryError: unable to create native thread` | Giới hạn thread, native memory, pid/OS limits; không kết luận heap đã đầy |
| Container/pod báo **OOMKilled** | Kernel/cgroup giết process khi vượt memory limit; có thể không có Java OOME hay `hs_err` |

Theo dõi heap **used/committed/max**, GC pause/frequency, RSS và giới hạn cgroup. RSS có thể tăng do native buffers, threads, mmap, metaspace hoặc libc dù heap không tăng. Heap gần đầy trước GC không tự chứng minh leak; cần quan sát **live set sau các đợt GC** và đối chiếu với tải. `OutOfMemoryError` cũng không nhất thiết làm **toàn bộ JVM** thoát ngay: tùy thread, handler và mức thiếu tài nguyên.

### 2.6. JVM crash: “vì sao tiến trình kết thúc?”

JVM crash theo nghĩa hẹp là VM/native code gặp **fatal error**, ví dụ SIGSEGV/SIGBUS trên Unix hoặc EXCEPTION_ACCESS_VIOLATION trên Windows, có thể sinh `hs_err_pid*.log` và core dump. Nguồn khả dĩ gồm JNI/JNA/native library, thao tác bộ nhớ không an toàn, JIT/VM/JDK bug hoặc phần cứng; **fatal log là chứng cứ để phân tích**, chưa khẳng định lỗi nằm trong JVM vendor.

Phải tách khỏi:
- `System.exit(...)`, ứng dụng tự dừng, service manager yêu cầu stop.
- Exception không bắt ở thread chính hoặc lỗi khởi động dẫn đến process thoát nhưng không có VM fatal error.
- `SIGTERM` khi triển khai lại, `SIGKILL`/exit 137 do quản trị hoặc OOM killer (cần xác nhận sự kiện OS/container).
- Host restart, container eviction, health check kill/restart.

Nếu tiến trình đã chết, `jcmd`/thread dump sống không còn dùng được; ưu tiên log cuối, exit reason, container events, crash artifact, timestamp và version. Trên Linux, exit 139 có thể gợi ý SIGSEGV; **mã thoát một mình không đủ** để phân biệt crash và nguyên nhân khác.

## 3. Cây quyết định chẩn đoán

Bắt đầu từ **bằng chứng mạnh nhất tại đúng thời điểm xảy ra sự cố**, không từ tên gọi trong ticket.

1. **Tiến trình Java còn sống không?** Nếu **không**, lấy exit code/reason, log ngay trước khi chết, sự kiện OS/container và xem có `hs_err_pid*.log`/core dump. Fatal error xác thực → nhánh **JVM crash**. `OOMKilled` → nhánh **thiếu bộ nhớ do giới hạn OS/container**. Thoát chủ động/triển khai lại → trạng thái dừng tiến trình, chưa được tự xếp vào crash.
2. **Nếu còn sống, hệ thống có tạo tiến độ không?** Đối chiếu completion counters, queue depth, heartbeat và nhiều thread dump khi cần. Không có tiến độ quá deadline hợp lý → ghi **hang/stall**, sau đó phân biệt deadlock, I/O wait, pool exhaustion, livelock hoặc GC dài. Nếu vẫn có tiến độ, chưa gọi là treo toàn hệ thống.
3. **Có chứng cứ về memory pressure hoặc OOME không?** Đối chiếu exact OOME message với heap, non-heap, native, GC, RSS/cgroup. Ghi **memory exhaustion** khi đủ căn cứ; nó có thể đồng thời làm request chậm/treo.
4. **Kết quả có vi phạm hợp đồng không?** Dựa vào expected/actual và invariant; gắn nhãn **lỗi chức năng** cho request/flow bị sai, kể cả process và chỉ số hiệu năng bình thường.
5. **Với việc vẫn hoàn thành, đo riêng latency và throughput.** So sánh p95/p99, arrival/s, completion/s, success/s với baseline ở **cùng loại tải và cùng cửa sổ**. Latency xấu nhưng completion/s ổn → chủ yếu độ trễ; completions/s chạm trần dưới tải tăng → chủ yếu khả năng xử lý; cả hai xấu → có thể chung bottleneck.
6. **Ghép timeline và giả thuyết nhân quả.** Ví dụ: allocation tăng → GC pause tăng → latency tăng → queue dồn → throughput giảm. Cần số liệu thời gian để ủng hộ chuỗi này; các biến cùng biến động chưa chứng minh quan hệ nhân quả.

Kết quả phân loại nên ghi theo mẫu: **“Đối tượng + thời gian + hiện tượng + mức độ + bằng chứng + điều chưa biết”**. Ví dụ: “Service A, 10:02–10:07, p99 từ 150 ms lên 2,4 s, completions/s giữ ~90, nhiều request chờ DB; chậm end-to-end đã xác nhận, nguyên nhân DB đang kiểm tra.”

## 4. Bằng chứng tối thiểu trên Java 17+

Thu thập từ ít xâm lấn đến chuyên sâu; giữ timestamp, timezone, hostname/pod, PID, JDK vendor/version, build, cấu hình giới hạn CPU/memory, lượng tải, log lỗi, request/trace ID. Ưu tiên đối chiếu **khi sự cố diễn ra** và baseline gần trước đó.

**Nếu JVM còn sống và cho phép attach**, các lệnh sau chạy trên máy/container có JDK và quyền truy cập tiến trình tương ứng. Thay 12345 bằng PID thật; không chạy từ máy không nhìn thấy namespace PID.

~~~bash
jcmd 12345 VM.version
jcmd 12345 Thread.print -l
jcmd 12345 GC.heap_info
jcmd 12345 JFR.start name=triage settings=profile duration=60s filename=triage.jfr
~~~

- **Thread dump:** ghi lock ownership, thread state, stack, số lượng pool; so sánh ít nhất hai thời điểm để xem tiến độ/thay đổi, tránh nhầm worker idle với deadlock. Việc attach có thể thất bại nếu JVM không phản hồi hoặc khác quyền.
- **Heap/GC:** `GC.heap_info` là snapshot, không thay cho phân tích retention. GC log/JFR giúp liên hệ pause hoặc allocation với tail latency. Việc tạo heap dump có thể tiêu tốn thời gian, bộ nhớ và dung lượng đĩa; chỉ thực hiện có chủ đích.
- **JFR:** dùng sự kiện execution sample, allocation, GC, thread/lock tùy cấu hình để định hướng; file ghi ra cần đường dẫn có quyền ghi và dung lượng đủ. Profiling cũng có overhead, nên cân nhắc tình trạng sản xuất.
- **Nếu đã thoát:** lấy stderr/stdout cuối, `hs_err`, core dump nếu có, exit code, OS/kernel/cgroup event, lý do restart; `jcmd` không còn gắn vào tiến trình cũ.

Có thể cấu hình thu thập dấu vết khi **khởi chạy ứng dụng** (ví dụ minh họa, cần thư mục ghi được và dung lượng đủ):

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags \
  -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=./dumps \
  -XX:ErrorFile=./hs_err_pid%p.log -jar app.jar
~~~

Lệnh giả định có `app.jar` và thư mục `./dumps` tồn tại. Heap dump, JFR và crash dump có thể chứa dữ liệu ứng dụng nhạy cảm: hạn chế quyền đọc/lưu giữ và không đính kèm công khai. Bật tùy chọn trước sự cố mới có thể thu artifact kịp thời; thiết lập cảnh báo/dung lượng phù hợp để tránh làm đầy đĩa.

## 5. Ví dụ Java: tách ba tốc độ và một phân vị

Chương trình Java 17+ dưới đây tính chỉ số từ **dữ liệu giả định của một cửa sổ 30 giây**. Đây là ví dụ về phép đo, không phải bộ phân loại nguyên nhân. Mười mẫu latency chỉ dùng minh họa cách tính nearest-rank p95; thống kê thực tế cần nhiều mẫu đại diện và phân nhóm endpoint.

~~~java
import java.util.Arrays;
import java.util.Locale;

public class DiagnoseWindow {
    public static void main(String[] args) {
        long arrivals = 240;
        long completions = 180;
        long successes = 165;
        double seconds = 30.0;
        long[] latencyMs = {40, 45, 50, 55, 60, 70, 90, 110, 150, 1200};

        Arrays.sort(latencyMs);
        int rank = (int) Math.ceil(0.95 * latencyMs.length);
        long p95 = latencyMs[rank - 1];

        System.out.printf(Locale.ROOT,
                "incoming=%.1f/s, completed=%.1f/s, success=%.1f/s%n",
                arrivals / seconds, completions / seconds, successes / seconds);
        System.out.printf(Locale.ROOT,
                "p95(sample)=%d ms, backlog change=%d%n",
                p95, arrivals - completions);
    }
}
~~~

Lưu trong **DiagnoseWindow.java**, chạy:

~~~bash
javac DiagnoseWindow.java
java DiagnoseWindow
~~~

Stdout chính xác:

~~~text
incoming=8.0/s, completed=6.0/s, success=5.5/s
p95(sample)=1200 ms, backlog change=60
~~~

**Cách đọc:** yêu cầu đến nhanh hơn mức hoàn tất (8 so với 6/s), trong ví dụ không có drop/cancel nên số việc chưa hoàn tất tăng 60. Completion throughput và successful throughput khác nhau. Mẫu p95 cao nói có tail latency, **không tự chứng minh nguyên nhân là deadlock, GC hay thiếu bộ nhớ**. Để kết luận saturation, cần thêm chuỗi thời gian ở nhiều mức tải, queue, sử dụng tài nguyên và trạng thái dependency. Không so sánh p95 của nhóm request khác loại hoặc cửa sổ không tương thích.

## 6. Sáu tình huống dễ nhầm

**A — Sai kết quả nhưng nhanh:** API phản hồi 200 trong 20 ms với số dư đã cập nhật sai; CPU, GC và requests/s bình thường. **Phân loại:** lỗi chức năng. Việc phải làm: tái hiện input, kiểm tra transaction/invariant và thay đổi logic; không bắt đầu bằng heap dump.

**B — Đuôi latency tăng, khả năng hoàn tất vẫn giữ:** 90 requests/s ổn định nhưng p99 tăng 150 ms → 2,4 s; trace cho thấy các truy vấn DB kéo dài. **Phân loại:** suy giảm latency (nghi DB/queue), chưa đủ bằng chứng suy giảm throughput. Đo bằng cùng endpoint, mức tải và phân vị.

**C — Đụng trần thông lượng:** tải gửi 400 requests/s nhưng chỉ hoàn tất 150/s; queue tăng, deadline bị vượt, CPU hoặc pool đạt giới hạn. **Phân loại:** throughput bottleneck kèm latency và timeout. Tăng timeout không làm tăng năng lực phục vụ; xác minh chỗ bị saturation.

**D — Sống nhưng không tiến độ:** PID còn, health TCP mở, completion counter đứng yên lâu hơn deadline; hai thread dump liên tiếp cho thấy chuỗi lock cycle hoặc các worker đều chờ một dependency không hồi đáp. **Phân loại:** hang/stall ở phạm vi đã chứng minh. `WAITING` ở một worker rảnh một mình không đủ kết luận.

**E — OOME khác với OOMKilled:** log có `java.lang.OutOfMemoryError: Java heap space` → thiếu Java heap cần phân tích live objects/GC; còn pod bị báo `OOMKilled`, không có Java OOME → OS/cgroup giết vì giới hạn bộ nhớ. **Cả hai thuộc nhánh memory**, nhưng cơ chế và bằng chứng điều tra khác nhau. Không tự gán pod OOMKilled thành “JVM native crash”.

**F — VM fatal error khác với dừng bình thường:** stderr có “A fatal error has been detected by the Java Runtime Environment”, `SIGSEGV`, đường dẫn `hs_err_pid12345.log` → có căn cứ về JVM/native crash; còn service bị orchestration gửi SIGTERM rồi thoát theo lifecycle → dừng có chủ đích. Phân tích `hs_err` cùng version/JNI/native stack trước khi quy trách nhiệm cho JDK.

## 7. Những suy luận sai cần tránh

- **Một HTTP 500 = lỗi chức năng.** HTTP status chỉ phản ánh kết quả request; root cause có thể là hết kết nối, timeout, OOME hoặc logic.
- **Latency tăng = throughput giảm.** Một hệ thống có thể giữ completions/s nhưng phân vị đuôi xấu; hoặc throughput thấp vì không có tải.
- **Một request timeout = JVM hang.** Có thể do mạng, dependency, queue, retry hoặc client deadline. Kiểm tra progress và phạm vi.
- **Thread ở BLOCKED/WAITING = deadlock.** Cần quan hệ khóa và sự lặp lại trong nhiều mẫu, không chỉ state đơn lẻ.
- **Heap cao = leak.** Heap có thể chứa live data hợp lệ hoặc tăng tạm; phải nhìn GC, retention, workload và giới hạn.
- **Có OOME = JVM đã crash.** OOME là Java error; tiến trình có thể còn sống. OOMKilled là OS kill; native fatal error là loại khác.
- **Mất PID = JVM crash.** Xác định exit reason trước: deployment, stop, signal, cgroup, fatal error.
- **Tối ưu ngay trước khi đo.** Giữ timeline và baseline, kiểm tra thay đổi gần nhất; nếu không, dễ “sửa” triệu chứng sai hoặc làm mất chứng cứ.

## 8. Checklist khi ghi nhận kết luận

Trước khi chuyển điều tra sang nguyên nhân gốc, bản ghi phải trả lời đủ: **(1)** phạm vi nào và từ lúc nào; **(2)** process còn sống hay đã thoát, bằng chứng của exit reason; **(3)** correctness, latency percentile, arrival/completion/success throughput và tiến độ đang thế nào; **(4)** có OOME/GC/RSS/cgroup hoặc thread/lock evidence hay không; **(5)** nhãn triệu chứng chính/phụ cùng giả thuyết có thể kiểm chứng tiếp; **(6)** dữ liệu nào còn thiếu để tránh khẳng định quá mức.

**Nguyên tắc thực hành:** xác định trước **sai kết quả – chậm mỗi việc – ít việc hoàn thành – không tiến độ – thiếu tài nguyên bộ nhớ – fatal VM/native**, sau đó dùng số liệu và log độc lập để chứng minh, phân biệt triệu chứng với nguyên nhân.