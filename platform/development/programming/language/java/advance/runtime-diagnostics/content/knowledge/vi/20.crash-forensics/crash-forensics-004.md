# 20.4 Đối chiếu heap, thread, VM flags, hệ điều hành và tài nguyên tại thời điểm crash

## 1. Tư duy điều tra: cùng một sự cố, nhiều lớp bằng chứng

Khi một ứng dụng Java biến mất, restart hoặc không còn phục vụ request, câu hỏi đầu tiên **không phải** “heap có đầy không?” mà là **“tiến trình đã kết thúc theo cơ chế nào, vào thời điểm nào, trên node/container nào?”**. Chỉ sau khi xác định loại kết thúc, ta mới ghép thông tin từ Java heap, threads, VM flags, native memory, hệ điều hành và giới hạn tài nguyên.

Ví dụ ba trường hợp rất khác nhau:

- **HotSpot fatal error:** JVM gặp `SIGSEGV`/`SIGBUS`/`SIGILL` hoặc lỗi nội bộ; có thể tạo `hs_err_pid*.log` và core dump. File báo lỗi thường cho biết thread hiện tại, problematic frame, mã JVM, flags, trạng thái heap và OS.
- **Java `OutOfMemoryError`:** một phép cấp phát thất bại, ví dụ `Java heap space`, `Metaspace`, `Direct buffer memory` hoặc `unable to create native thread`. Đây là **Java Error** và không nhất thiết đồng nghĩa toàn bộ process đã crash ngay; nếu chuẩn bị cấu hình phù hợp, có thể có heap dump.
- **OS/container OOM kill:** Linux kernel hoặc bộ quản lý cgroup có thể gửi `SIGKILL`. JVM **không có cơ hội** chạy error handler, `finally`, shutdown hook hoặc tạo `hs_err`; cần kiểm tra sự kiện OOM của OS, container status và metrics trước khi chết.

Lỗi Java không bắt buộc gây ra JVM fatal error; ngược lại, JVM fatal error không nhất thiết do thiếu Java heap. **Không thấy `hs_err` không chứng minh không có crash.** File có thể không được tạo vì loại kết thúc không đi qua error handler, lỗi quá nghiêm trọng, thiếu dung lượng/quyền ghi hoặc artifact bị mất sau restart.

Bài này là một quy trình điều tra **sau sự cố** và chuẩn bị dữ liệu **trước sự cố**. Mục tiêu không phải liệt kê mọi lệnh mà là **đối chiếu các nguồn theo cùng PID, process start, thời gian, namespace và resource boundary** để có kết luận kiểm chứng được.

Sau bài học, bạn có thể:

1. Phân loại fatal error JVM, Java OOME, OS OOM kill, signal/shutdown và lỗi ứng dụng.
2. Đọc những phần liên quan của `hs_err` và hiểu giới hạn snapshot.
3. Phân biệt Java heap **used/committed/max**, native allocation, OS RSS và cgroup memory.
4. Ghép crash thread/native stack với thread dump, VM flags, JFR/GC logs và giới hạn CPU/memory/PIDs.
5. Dựng timeline bằng các bằng chứng có timestamp; đánh giá độ tin cậy và thử phủ định giả thuyết.
6. Chuẩn bị file, logs và số liệu để lần crash tiếp theo **có thể điều tra**, thay vì chỉ có câu “pod restarted”.

## 2. Trước hết xác định “crash” nghĩa là gì

Từ “crash” trong dashboard có thể chỉ một **container restart**, trong khi JVM có thể đã nhận `SIGTERM` và shutdown bình thường, bị `SIGKILL`, ném một exception không được xử lý ở thread chính, gọi `System.exit`, hoặc gặp fatal VM error. Mỗi loại tạo evidence khác nhau.

| Triệu chứng/kiểu kết thúc | Bằng chứng nên tìm | Điều **không** nên suy luận |
| --- | --- | --- |
| HotSpot fatal error, ví dụ `SIGSEGV` / Windows `EXCEPTION_ACCESS_VIOLATION` | `hs_err_pid*.log`, problematic frame, crash thread, native libraries, core/WER dump | Không phải cứ thấy `libjvm` là chắc JVM bug |
| `OutOfMemoryError: Java heap space` | Application stderr, heap usage/GC trước lỗi, heap dump nếu có, `-Xmx` thực tế | Không mặc định OS đã OOM-kill process |
| `OutOfMemoryError: Metaspace` | Classloader count, metaspace/NMT, `MaxMetaspaceSize` và class unloading | Heap object histogram không giải thích toàn bộ metaspace |
| `OutOfMemoryError: Direct buffer memory` | Buffer allocation, direct-memory budget, RSS/NMT/OS maps | `-Xmx` chưa đầy không loại trừ vấn đề |
| `OutOfMemoryError: unable to create native thread` | Số threads, `-Xss`, OS `ulimit`/PID limit, cgroup `pids.max`, native memory | Tăng `-Xmx` không phải lời giải mặc định |
| OS/cgroup OOM killer gửi `SIGKILL` | Kernel/journal logs, cgroup `memory.events`, container `OOMKilled`, RSS/cgroup usage | Exit code 137 **một mình** không chứng minh OOM |
| `SIGTERM`/shutdown/deployment | Termination reason, orchestration events, shutdown logs, drain deadline | Không xem mọi restart là crash do JVM |
| Uncaught exception hoặc `System.exit(...)` | Application exception, exit code, startup/shutdown logs | Không trông đợi `hs_err` |
| Host reboot/hardware/container runtime failure | Host/kernel logs, node events, boot ID, orchestration status | Không gán nguyên nhân cho một Java frame |

**Exit code** thường được shell/container hiển thị dạng `128 + signal` trên Unix (137 ≈ SIGKILL, 139 ≈ SIGSEGV, 143 ≈ SIGTERM), nhưng cách báo cáo khác nhau theo wrapper/container runtime và có trường hợp process chủ động trả code giống vậy. Cần kiểm tra **termination reason**, signal, kernel events và trùng PID/time. `OOMKilled` từ orchestrator mạnh hơn phỏng đoán dựa trên `137`; nó vẫn cần ghép đúng container instance và thời điểm.

## 3. Ưu tiên bảo toàn chứng cứ trước khi restart dọn sạch dấu vết

Khi incident xảy ra, làm việc theo thứ tự:

1. Ghi **incident ID**, service, deployment revision, image digest, node, pod/container ID, PID (PID bên trong container và PID host nếu có), thời điểm phát hiện và start time của process.
2. Ghi **ngày giờ chuẩn UTC**, timezone của từng log và thời gian JVM đã chạy (uptime). Không trộn giờ địa phương với `uptime` hay thời điểm milliseconds từ một clock khác.
3. Sao lưu **nguyên trạng** `hs_err`, stderr/stdout, GC logs, JFR, heap dump `.hprof`, core/WER dump, application logs và metrics gần thời điểm lỗi.
4. Lấy **termination status** từ OS/orchestrator và kernel/cgroup OOM events, bao gồm sự kiện ngay trước và ngay sau crash.
5. Lưu runtime flags, container memory/CPU/PID limits, JDK build, kernel/OS version, JNI/native library versions, thread counts, RSS, cgroup memory, file-descriptor counts nếu đã thu được.
6. Tạo một timeline và gắn **nguồn + timestamp + độ tin cậy** cho mỗi quan sát; không chuyển giả thuyết thành kết luận trước khi đối chiếu.

**Điểm quan trọng:** sau khi process đã chết, `jcmd <pid> ...` không thể attach vào process đó. Mọi `VM.flags`, `Thread.print`, `GC.heap_info` hay NMT cần được thu **lúc process còn sống**, lấy từ file log `hs_err` / core hoặc từ telemetry được lưu trước đó. Không ghi giá trị của JVM **sau restart** rồi nói đó là trạng thái của JVM **trước crash**.

Nếu có restart tự động, thu cả process **start timestamp** và container instance ID: **PID 1** có thể được tái sử dụng qua nhiều lần restart. Chỉ ghép theo PID là chưa đủ.

### 3.1. Hạn chế tác động lên hiện trường

- Đừng vội xoá pod/container cũ nếu chưa bảo toàn logs/artifacts cần thiết và việc giữ lại không gây hại hệ thống.
- Không chạy heap dump/core dump khổng lồ trên service thiếu disk/memory headroom mà chưa đánh giá tác động.
- Không thay GC flags, `-Xmx` hoặc limit cùng lúc với thu chứng cứ, vì sẽ làm khó so sánh.
- Nếu cần khôi phục dịch vụ ngay, lưu metadata/logs hiện có rồi điều tra trên bản copy; không chặn phục hồi chỉ để chụp một dump quá nguy hiểm.
- Heap dump, core và `hs_err` có thể chứa password, access token, env vars, path và dữ liệu khách hàng. Bảo vệ quyền truy cập, mã hóa và retention phù hợp.

## 4. Bản đồ chứng cứ: mỗi nguồn trả lời câu hỏi gì?

| Nguồn | Dữ liệu liên quan | Dùng để hỏi | Giới hạn |
| --- | --- | --- | --- |
| `hs_err_pid*.log` | Signal, problematic frame, current thread, JVM build/flags, heap/process/OS summary | JVM gặp fatal error ở đâu? Trạng thái sơ bộ khi chết? | Không phải mọi loại kết thúc đều có; phần log có thể thiếu |
| GC logs | Heap before/after GC, pauses, collector, allocation/GC pressure | Heap có cạn liên tục trước crash? | Không đo toàn bộ RSS/native memory |
| `.hprof` | Java object graph/roots, shallow/retained heap | Object nào giữ heap sống khi dump? | Không gồm mọi native allocations; dump có thể trước/sau GC |
| Thread dumps | Thread names/IDs/stacks/states/locks | Thread nào blocked, native, deadlocked, chờ I/O? | Snapshot có thể khác thời điểm crash; thread IDs phải đối chiếu |
| `VM.command_line` / `VM.flags` | JVM flags khởi chạy/hiệu lực | Heap size, GC, thread stack, NMT, container flags là gì? | Lệnh chạy ở JVM khác sau restart không đại diện bản cũ |
| NMT `VM.native_memory` | Native VM allocations theo category, reserved/committed | Metaspace, thread, code cache, internal allocations tăng? | Cần bật NMT; không theo dõi mọi allocation của thư viện ngoài JVM |
| OS process metrics | RSS, VSZ, thread count, FDs, resource limits | OS thấy process dùng memory/threads/file handles bao nhiêu? | RSS không bằng Java heap và không cộng thẳng với NMT |
| Cgroup/container metrics | `memory.current`/`memory.max`/`memory.events`, `pids.current` | Chạm giới hạn container hay bị OOM kill không? | Số liệu là cgroup, có thể gồm page cache và process khác |
| Kernel/system logs | OOM killer, signal, native crash, I/O/disk errors | Có sự kiện bên ngoài JVM trùng thời điểm không? | Có thể không có quyền, log đã rotate hoặc giới hạn retention |
| JFR | GC, thread/monitor, I/O, CPU, execution/alloc events | Xu hướng/hoạt động ngay trước lỗi? | Phải được bật; dữ liệu có threshold/sampling/buffer |
| Orchestrator | Last termination state, restart count, resource limits, node | Ai/điều gì restart container? | Container hiện tại có thể khác container vừa chết |

Cách đúng là **đọc chéo**: ví dụ `memory.current` gần `memory.max` + `oom_kill` tăng + Kubernetes báo `OOMKilled` mới là tập tín hiệu mạnh cho cgroup OOM. Một file `hs_err` có `Current thread _thread_in_native` + `Problematic frame C [libnative.so]` giúp ưu tiên JNI/native library, nhưng vẫn cần kiểm tra core, version, stack và điều kiện tái hiện.

## 5. Đọc file hs_err: ghép thread, heap, flags và OS cùng snapshot

HotSpot cố tạo fatal error log khi gặp lỗi nghiêm trọng. Mặc định thường có dạng `hs_err_pid<PID>.log` ở working directory; có thể cấu hình `-XX:ErrorFile=/path/hs_err_pid%p.log`. Nếu không ghi được ở vị trí dự kiến, việc tìm file phải xét đường dẫn fallback, quyền và filesystem. Format thay đổi theo JDK/build; một crash rất nặng có thể khiến JVM chỉ ghi được phần đầu.

### 5.1. Thứ tự đọc đề xuất

**Bước A — Header và loại lỗi.** Tìm signal/exception, JDK version/build, VM name/architecture, thời điểm crash, PID, uptime, problematic frame. Đừng nhầm `SIGSEGV` trong native code với Java `NullPointerException` thông thường.

**Bước B — Current thread / thread stack.** Xem thread nào gây fatal signal, state nội bộ như `_thread_in_native`, `_thread_in_vm` hoặc `_thread_in_Java`, native TID, Java frames, native frames, `VM_Operation` nếu có. Cần ghép native library đang được gọi và JNI boundary.

**Bước C — Heap và GC.** Xem các vùng heap/metaspace được báo, committed/used nếu có, thông tin collector và GC gần crash. Một snapshot heap **không thay thế** xu hướng after-GC qua nhiều phút.

**Bước D — VM arguments/flags.** Xác định actual `-Xmx`, `-Xms`, collector, `-Xss`, native tracking, container-aware sizing, Java runtime version và các option được áp dụng. So với deployment/config mong đợi.

**Bước E — OS/hardware/resources.** Xem OS/kernel, CPU/architecture, native memory map, thread count, memory/swap, file descriptors/limits nếu có. So với `/proc`/cgroup/kernel log hoặc monitoring cùng thời điểm.

**Bước F — Loaded native libraries / core.** Nếu problematic frame ở thư viện `.so`/`.dll`, kiểm tra đường dẫn, phiên bản, symbol/native stack và những thay đổi gần đây.

Trích đoạn **minh họa**, không phải log của một sự cố thực tế:

```text
# A fatal error has been detected by the Java Runtime Environment:
# SIGSEGV (0xb) at pc=0x00007f00..., pid=4321, tid=4358
# Problematic frame:
# C  [libexamplejni.so+0x1234]

Current thread (0x...): JavaThread "worker-7"
                        [_thread_in_native, id=4358, stack(...)]
...
VM Arguments:
jvm_args: -Xms256m -Xmx768m -XX:+UseG1GC
...
Heap:
garbage-first heap total 262144K, used 153600K ...
```

Đây là một **mẫu phỏng họa định dạng**: địa chỉ và kích thước không đại diện mọi JDK hay collector. Ký tự frame HotSpot thường dùng `C` cho native C/C++ code, `V` cho mã JVM, `J` cho Java code đã biên dịch; phải tham khảo bản build/log cụ thể, không suy ra nguyên nhân bằng một chữ cái.

Với mẫu trên, nhận xét thận trọng là: có fatal signal trong một native frame, ở một worker thread đang trong trạng thái native, trong JVM có heap max theo flag. Không được kết luận “heap thiếu” hay “JNI chắc chắn có bug” chỉ từ bốn dòng; cần core/native symbols, runtime version, thread stack và OS events.

### 5.2. Tại sao file hs_err thiếu không phải bằng chứng âm tính?

Các trường hợp có thể không có `hs_err`:

- OS gửi `SIGKILL`, ví dụ cgroup OOM killer; JVM không xử lý kịp.
- Process bị `System.exit` hoặc thoát khi main kết thúc; đó không phải HotSpot fatal error.
- Lỗi quá nghiêm trọng để error handler chạy xong.
- Disk full, inode hết, mount read-only, thiếu permission, path sai hoặc artifact chỉ tồn tại trong container đã bị xóa.
- Fatal error handler ghi ở working dir hoặc fallback location khác vị trí dự kiến.

Vì vậy khi không thấy file, phải **mở rộng tìm kiếm nguồn** chứ không xem là “không có crash”.

## 6. Đối chiếu Java heap với memory mà hệ điều hành tính

Một trong những sai lầm phổ biến nhất là dùng `-Xmx=768m` rồi cho rằng process chỉ có thể dùng tối đa 768 MiB, hoặc nhìn `heapUsed=300 MiB` và loại trừ hoàn toàn nguy cơ OOM kill container 1 GiB.

### 6.1. Các đại lượng không đồng nghĩa

| Chỉ số | Định nghĩa đúng | Điều không suy ra được |
| --- | --- | --- |
| `heap used` | Java heap hiện đang chứa object/space sử dụng theo JVM metrics | Không phải toàn bộ RSS hay toàn bộ heap committed |
| `heap committed` | Java heap memory đã được JVM cam kết ở mức đo nội bộ | Không phải đúng bằng RSS, và không nhất thiết là live object |
| `heap max` / `-Xmx` | Giới hạn cấu hình cho Java heap | Không phải hard limit của cả process |
| `heap reserved` | Address space dành cho heap | Không phải tất cả đều resident trong RAM |
| Metaspace/class/code cache | Bộ nhớ và vùng quản lý class/JIT khác Java heap | Không tính vào `heap used` |
| Direct/native allocations | Direct ByteBuffers, JNI/native libraries, malloc, thread stacks, runtime internals | Không thể kết luận chỉ từ HPROF |
| `RSS` / `VmRSS` | Các trang bộ nhớ vật lý resident của process theo OS | Không phải Java live heap; có shared mappings |
| `VSZ` / `VmSize` | Virtual address space của process | Không phải RAM thực đang dùng |
| `memory.current` (cgroup v2) | Mức memory charge của cgroup và các descendants | Có thể gồm page cache/kernel memory/other processes; không phải RSS một JVM |
| `memory.max` (cgroup v2) | Hard memory limit của cgroup; `max` nghĩa không có giới hạn này | Không thay `-Xmx`, và chưa chắc giới hạn thực cuối cùng nếu ancestor chặt hơn |
| NMT `reserved/committed` | Nội bộ JVM tracking theo subsystems | Không thay toàn bộ OS RSS và không bao trùm mọi native code |

Nhớ một gần đúng về mô hình, **không phải công thức accounting tuyệt đối**:

```text
Process RSS liên quan đến các trang resident của:
    Java heap
  + metaspace / class metadata
  + JIT code cache
  + thread stacks đã thực sự chạm trang
  + direct/native buffers
  + JVM internals + shared libraries + ...
(Trong số đó có trang shared; các hệ thống accounting có quy tắc riêng.)

Container memory charge liên quan đến:
    memory do JVM và process khác trong cgroup sử dụng
  + một phần file/page cache
  + kernel memory và các charges khác theo cgroup/kernel
(Đây không phải phép cộng đơn giản của RSS nhiều process.)
```

Không dùng một phép trừ `memory.max - Xmx` như headroom **đảm bảo**. Chẳng hạn container được giới hạn **1.024 MiB**, `-Xmx=768 MiB`. Khoảng còn lại trên giấy là 256 MiB, nhưng metaspace, stacks, direct buffers, page cache, OS charges và process khác có thể dùng nhiều hơn. Ngược lại, heap reserved 768 MiB chưa chắc committed/resident đủ 768 MiB tại thời điểm đo.

### 6.2. Java heap OutOfMemoryError

Khi có `java.lang.OutOfMemoryError: Java heap space`:

1. Kiểm tra heap usage, GC logs và `-Xmx` **hiệu lực**; xem live set after GC, tốc độ tăng và allocation pressure.
2. Tìm heap dump được thu cùng quá trình (nếu cấu hình `-XX:+HeapDumpOnOutOfMemoryError` và dump thành công); kiểm tra timestamp/PID, đừng lấy dump từ lần khởi động khác.
3. Phân tích Histogram/Dominator Tree/Paths to GC Roots để tìm object giữ sống bất thường.
4. Đối chiếu workload, cache/session lifecycle, kích thước batch, số request song song và những thay đổi gần đây.
5. Xác định tiến trình **có thực sự kết thúc** vì exception không được xử lý hoặc policy khác không. Một thread bị OOME không đồng nghĩa cả JVM fatal-crashed ngay tức thì.

**Heap dump không phải bằng chứng hoàn hảo cho mọi loại OOME.** Nếu hệ thống thiếu disk, bị OS kill trước khi dump, không có quyền ghi hoặc đang ở trạng thái không thể dump, HPROF có thể vắng mặt. Heap dump còn có thể chứa dữ liệu nhạy cảm và gây pause/IO lớn.

### 6.3. Native/thread/metaspace pressure

Nếu heap used nhỏ nhưng RSS hoặc cgroup memory tăng:

- Kiểm tra `java.nio.DirectByteBuffer`/network buffers, JNI/native libraries, malloc, mmap, thread stacks, classloaders/metaspace, code cache và kernel/page cache.
- Với `unable to create native thread`, xem `Thread.print`, OS thread count (`Threads` trong `/proc/PID/status`), `pids.current/pids.max`, `RLIMIT_NPROC`, `-Xss`, số lượng executor và native address space.
- Với `Metaspace`, xem classloader retention, class count và metaspace limits, thay vì chỉ xem `-Xmx`.
- Với `Direct buffer memory`, xem direct memory settings và allocation lifecycle; JDK may account direct buffers khác với native allocations của thư viện.
- Với native leak, JVM NMT hữu ích nhưng **không đo mọi memory được cấp phát bởi thư viện non-JVM**. Cần thêm OS profiler/counters/maps, và đôi khi core/native debugger.

Đặc biệt, JVM NMT báo `reserved` rất lớn không tự chứng minh RAM đã cạn: **reserved address space khác committed và khác resident physical pages**.

## 7. Thread snapshot: “current thread” khác “all threads”

Từ `hs_err` bạn thường nhận được **Current thread**: thread thực thi nơi phát sinh fatal condition được error handler báo cáo. Từ `Thread.print`/thread dumps bạn nhận trạng thái nhiều thread tại thời điểm dump. Cần phân biệt:

- `_thread_in_native`: thread đang ở native call; hữu ích để khoanh JNI/native boundary, **chưa đủ** để kết luận chính native library là root cause.
- `_thread_in_vm`: đang chạy mã VM. Nếu crash trong GC/VM operation, kiểm tra GC logs, collector và JVM build.
- `_thread_in_Java`: code Java đang chạy, có thể interpreted/compiled; vẫn có thể bị ảnh hưởng bởi native/VM bug, memory corruption hoặc hardware.
- `BLOCKED`, `WAITING`, `TIMED_WAITING` trong Java thread dump: trạng thái snapshot; không tự nói process đã crash vì deadlock.
- `RUNNABLE` trong Java Thread.State không bảo đảm thread đang sử dụng CPU: có thể chờ I/O tại native call.

### 7.1. Ghép thread IDs đúng tầng

Một `hs_err` có thể đưa `id=...` là native OS thread ID (TID); Java `Thread.getId()` hoặc `Thread.threadId()` là Java thread identifier theo API và không được mặc định bằng TID. Linux `top -H`, `ps -L`, `/proc/PID/task` cho OS threads; Java dumps có thể hiện `nid=0x...` theo dạng hex. Nếu đối chiếu, chuyển cơ số đúng và kiểm tra cùng PID/process instance.

Ví dụ **minh họa**:

```text
hs_err:       Current thread ... id=4358
Java dump:    "worker-7" ... nid=0x1106
OS thread:    LWP/TID 4358
```

Ở đây `0x1106` = `4358` hệ thập phân. Phép chuyển số không chứng minh đây là cùng một thread nếu artifact từ **hai lần restart khác nhau**. Phải kiểm tra timestamp và process start.

### 7.2. Ghép native và Java stack

Khi problematic frame nằm trong `libexamplejni.so`, đọc stack để tìm:

- Java method gọi JNI hoặc FFI/native binding nào.
- C/C++ library version, binary build ID, symbol addresses.
- Chỗ có thể access invalid pointer, use-after-free, data race, alignment hoặc ABI mismatch.
- Sự tương quan với các thay đổi gần đây của JDK, native module, OS/kernel hoặc compiler.
- Crash lặp lại cùng frame hay thay đổi ngẫu nhiên, gợi ý memory corruption rộng hơn.

Một frame JVM như `V [libjvm.so]` cũng không đủ kết luận HotSpot bug: memory corruption từ JNI trước đó có thể biểu hiện lúc VM/GC xử lý memory. Nếu nghi native defect, dùng **core/WER dump + native symbols + vendor escalation** theo quy trình cho phép, không chỉ đọc stack top.

Thread dumps trước crash còn giúp xem pool saturation, deadlock và số lượng worker tăng đột biến. Nếu chỉ có dump trước lỗi 20 phút, nó là **trend evidence**, không phải snapshot đúng crash.

### 7.3. Các rủi ro khi thu thread dumps

`jcmd PID Thread.print -l` có thể ảnh hưởng runtime tùy số lượng threads/locks. Trên JDK 21, virtual threads có cơ chế dump/quan sát riêng; không mặc định bản thread dump kiểu truyền thống hiển thị đầy đủ mọi virtual thread với cùng format. Thu sampling nhiều thời điểm, lưu timestamp và kiểu lệnh đã dùng. Không chạy dày đặc trên service quá tải nếu chưa đánh giá tác động.

## 8. VM flags: đọc giá trị có hiệu lực, không chỉ đọc YAML hay Dockerfile

Một deployment có thể khai báo memory limit 1 GiB, JVM dùng `-Xmx` cố định hoặc các cờ sizing theo RAM, startup scripts inject `JAVA_TOOL_OPTIONS`/`_JAVA_OPTIONS`, và Helm chart bổ sung flag khác. Muốn điều tra phải ghi **lệnh JVM thực**, **flags hiệu lực** và **giới hạn OS/container** cùng lúc.

Nhóm cờ nên đối chiếu:

| Nhóm | Cờ/ví dụ | Câu hỏi |
| --- | --- | --- |
| Heap | `-Xms`, `-Xmx`, `-XX:InitialRAMPercentage`, `-XX:MaxRAMPercentage`, `-XX:MaxRAM` | Heap sizing có phù hợp limit container? |
| GC | `-XX:+UseG1GC` hoặc collector khác, `-Xlog:gc*` | Collector nào, GC pressure và pauses ra sao? |
| Metaspace | `-XX:MaxMetaspaceSize` | Metaspace có bị giới hạn hoặc tăng bất thường? |
| Direct memory | `-XX:MaxDirectMemorySize` (nếu set) | Off-heap buffer có mức giới hạn gì? |
| Threads | `-Xss`, `-XX:ActiveProcessorCount` | Thread stack và CPU topology mà JVM dùng? |
| Container | `-XX:+UseContainerSupport`, `-XX:MaxRAMPercentage` | JVM có đọc cgroup constraints phù hợp không? |
| Native tracking | `-XX:NativeMemoryTracking=summary/detail` | Có thể đọc baseline/diff trước crash không? |
| Diagnostics | `-XX:ErrorFile`, `-XX:+HeapDumpOnOutOfMemoryError`, `-XX:HeapDumpPath` | Artifacts sẽ được ghi ở đâu, có disk/quyền không? |
| Crash/GC logs | `-Xlog:gc*,safepoint:...` | Có timeline của GC/safepoints quanh crash không? |

Chú ý:

- `-Xmx` là giới hạn **Java heap**, không phải hard cap tổng RAM của process.
- `-Xss` quy định stack size theo môi trường; nếu có nhiều platform threads, stack reservations và phần đã commit đáng kể.
- `-XX:MaxRAMPercentage` không suy ra một số heap cụ thể nếu không biết môi trường JVM nhìn thấy, giới hạn cgroup, các cờ override và phiên bản JDK.
- Các cờ `Use...` có thể được set bởi ergonomics/runtime; `VM.flags -all` hỗ trợ xem nhiều flags hiện có, nhưng output rất lớn và cần lọc khi lưu.
- `-XX:NativeMemoryTracking=summary` phải được bật ngay lúc khởi động để theo dõi; không thể yêu cầu JVM sau khi chết tái tạo NMT diff chưa từng thu.
- VM command line, system properties và environment variables có thể chứa secret. Không dump toàn bộ vào ticket công khai.

**Cách kiểm chứng khi JVM còn sống** (thay `12345` bằng PID thật):

```bash
jcmd -l
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 VM.info
jcmd 12345 GC.heap_info
jcmd 12345 Thread.print -l
```

Các lệnh này cần có quyền attach và chạy trong namespace/kết nối phù hợp. Chúng có overhead khác nhau; `Thread.print` và một số truy vấn heap có thể tốn tài nguyên. Không chạy với PID cũ sau restart và gắn kết quả vào crash cũ.

## 9. Native Memory Tracking và các con số reserved/committed

### 9.1. NMT quan sát điều gì?

HotSpot Native Memory Tracking (`NMT`) ghi nhận allocation **bên trong JVM** theo nhóm như Java Heap, Class, Thread, Code, GC, Compiler và Internal. Nó **không bao phủ tất cả malloc/mmap của third-party native libraries**; cũng không thay kernel resident memory accounting. NMT có overhead CPU/memory nên cần thử ở môi trường phù hợp.

Nếu khởi động với:

```text
-XX:NativeMemoryTracking=summary
```

Có thể thu snapshot:

```bash
jcmd 12345 VM.native_memory summary scale=MB
jcmd 12345 VM.native_memory baseline
# Chờ sau khi ứng dụng warm-up và chạy workload ...
jcmd 12345 VM.native_memory summary.diff scale=MB
```

`baseline` cần được thiết lập trước lúc đo diff; dùng nhiều mốc có timestamp. Với `detail`, có thể phân tích chi tiết call site nhưng chi phí cao hơn. Nếu NMT báo không bật tracking, không thể phục hồi dữ liệu đó từ một process đã chết.

### 9.2. Vì sao không cộng NMT vào RSS?

NMT có hai nhóm chỉ số:

- **reserved:** vùng virtual address space JVM dành trước.
- **committed:** vùng được JVM cam kết sử dụng theo category.

RSS là **resident memory** OS quan sát; cách accounting có mapping/shared pages, thậm chí JVM commit chưa chắc resident. Cgroup memory lại có thể tính kernel memory/page cache và descendants. Vì vậy không dùng phép toán `NMT committed + RSS`, cũng không dùng `NMT committed == RSS`. Đối chiếu xu hướng và category theo từng nguồn rồi tìm phần chênh có cơ sở.

Ví dụ một process:

```text
NMT Java Heap reserved = 2048 MiB
NMT Java Heap committed = 512 MiB
OS RSS = 700 MiB
container memory.current = 850 MiB
```

Các số này **có thể cùng đúng** nhưng không đồng nhất. RSS gồm resident pages của các vùng khác heap; cgroup memory có thể gồm page cache và charges khác. Đây chỉ là dữ liệu minh họa, không phải kết quả đo từ demo của bài.

## 10. Hệ điều hành và cgroup: khi JVM không tạo được hs_err

### 10.1. Linux: process metrics khi còn sống

Lệnh ví dụ sau dành cho **Linux**, không phải Windows PowerShell. Chỉ chạy khi PID vẫn tồn tại:

```bash
PID=12345
date -u
ps -o pid,ppid,lstart,etime,rss,vsz,nlwp,stat,cmd -p "$PID"
cat "/proc/$PID/status"
cat "/proc/$PID/limits"
cat "/proc/$PID/cgroup"
ls "/proc/$PID/task" | wc -l
```

Các quan sát hữu ích:

- `VmRSS` và `VmSize`: resident / virtual size của process; không nhầm với heap.
- `Threads` hoặc `nlwp`: số OS threads; đối chiếu `unable to create native thread`.
- `Max open files`, `Max processes`, `Max stack size` và các giới hạn trong `/proc/PID/limits`.
- `/proc/PID/cgroup`: process thuộc cgroup nào; đường mount/cgroup namespace có thể cần `/proc/PID/mountinfo` để xác định đúng file metrics.
- `PPID`, process start, command line: tránh ghép nhầm process được restart và tái sử dụng PID.

Sau crash, `/proc/PID` biến mất; phải dựa vào metrics/logs đã lưu hoặc data từ hệ thống giám sát.

### 10.2. Linux cgroup v2

Trong nhiều container cgroup v2, bạn có thể thấy các file:

```bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/pids.current
cat /sys/fs/cgroup/pids.max
```

**Đường dẫn trên chỉ đúng nếu mount/cgroup namespace hiện tại ánh xạ tới cgroup bạn cần điều tra.** Với host, nested cgroup hoặc cgroup v1, đường dẫn và file khác. Đọc `/proc/<PID>/cgroup` và mountinfo để xác định đúng cgroup, không mặc định `/sys/fs/cgroup` trên terminal host là của container đã chết.

Ý nghĩa:

- `memory.current`: mức charge memory hiện tại; không phải RSS riêng JVM.
- `memory.max`: giới hạn hard (hoặc giá trị `max`).
- `memory.events`: counters như `high`, `max`, `oom`, `oom_kill`.
- `pids.current/pids.max`: số lượng tác vụ/giới hạn PID; hữu ích khi process không tạo được thread.

`memory.events` là **counters kể từ vòng đời cgroup**, và trong cgroup v2 một số giá trị là **hierarchical**; `memory.events.local` có thể giúp xem sự kiện riêng của cgroup. Do đó, một giá trị `oom_kill=1` không chứng minh kill của **incident hiện tại** nếu không có timestamp/delta, nếu cgroup chứa nhiều process hoặc đã có sự kiện trước. Nếu quan sát được counter tăng cùng thời điểm container bị `OOMKilled`, bằng chứng mạnh hơn.

Không tự suy luận `memory.current` ở thời điểm bạn đọc **sau restart** bằng chính peak của container **trước crash**: process/cgroup có thể đã bị thay thế, counters bị reset hoặc metrics không còn.

### 10.3. Linux kernel logs

Nếu có quyền và dữ liệu còn lưu:

```bash
journalctl -k --since "2026-10-29 09:55:00" --until "2026-10-29 10:05:00"
dmesg --ctime | grep -Ei 'out of memory|oom-kill|killed process'
```

**Thời gian trong ví dụ chỉ minh họa**, cần thay bằng cửa sổ incident và chú ý timezone mà `journalctl`/`dmesg` hiển thị. Kernel log có thể ghi tên executable, host PID, cgroup path và memory pressure. Không có quyền hoặc log đã rotate thì “không tìm thấy OOM” vẫn không loại trừ hoàn toàn OS kill.

Một số giới hạn khác đáng kiểm tra khi crash không do heap:

- `ulimit`, `RLIMIT_NPROC`, `pids.max` khi thread creation thất bại.
- File descriptors và `EMFILE`/`ENFILE` khi socket/file open thất bại.
- Disk free **và inodes** ở đường chứa dump/log; filesystem read-only hoặc volume đã đầy có thể khiến artifact không được lưu.
- CPU throttling và I/O pressure không nhất thiết gây crash trực tiếp, nhưng có thể khiến timeouts, watchdog/probe restart.
- Swap availability và memory pressure; không quy tất cả memory pressure thành Java heap leak.

### 10.4. Kubernetes/container orchestration

Ví dụ điều tra (thay namespace/pod/container thật):

```bash
kubectl describe pod myapp-abc -n prod
kubectl get pod myapp-abc -n prod -o json
kubectl logs myapp-abc -n prod -c app --previous --timestamps
```

Trong output, tìm:

- `lastState.terminated.reason`, `exitCode`, `finishedAt`, restart count.
- CPU/memory requests & limits của container **đã kết thúc**, không chỉ deployment mới.
- Pod/container ID, node, image digest và events của kubelet.
- `--previous` chỉ hữu ích khi container previous logs còn được runtime giữ và container đã restart trong cùng pod; không giả định luôn còn.
- Metrics time series của container cũ: memory working set/usage, OOM counters, CPU throttling, restarts, file descriptors.

Nếu `reason=OOMKilled` nhưng Java heap used thấp, điều tra thêm direct/native memory, page cache, thread stacks và process khác trong cgroup; không kết luận JVM heap collector lỗi.

### 10.5. Windows hoặc môi trường không dùng Linux

Trên Windows, nguồn tương ứng có thể là **Event Viewer / Windows Event Log**, **Windows Error Reporting (WER)**, process dump, Performance Counters (Private Bytes, Working Set, thread count, handles), service manager logs và giới hạn bộ nhớ của Job Object nếu có. `hs_err` có thể báo `EXCEPTION_ACCESS_VIOLATION` thay vì `SIGSEGV`. Không áp thẳng câu lệnh `/proc` hoặc cgroup Linux cho Windows.

Trên mọi OS, phải ghi JDK vendor/build, architecture, kernel/OS build, CPU/memory limits, binary/native library versions và thời điểm tiến trình kết thúc.

## 11. Chuẩn bị JVM để lần crash sau có dữ liệu

Ví dụ cờ khởi động HotSpot JDK 17+ trên **Linux**, các đường dẫn chỉ minh họa và phải tồn tại, đủ quyền/disk:

```bash
java \
  -XX:ErrorFile=/var/log/myapp/hs_err_pid%p.log \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/var/log/myapp \
  -Xlog:gc*,safepoint:file=/var/log/myapp/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -XX:NativeMemoryTracking=summary \
  -jar app.jar
```

Giải thích:

- `ErrorFile` chỉ vị trí fatal error log (có `%p` để phân biệt PID).
- `HeapDumpOnOutOfMemoryError` yêu cầu dump khi VM bắt gặp các loại OOME hỗ trợ và đủ điều kiện thực hiện. **Không đảm bảo** có dump khi process bị OS gửi SIGKILL, fatal native crash hoặc thiếu disk.
- `HeapDumpPath` chọn thư mục/file dump; một HPROF có thể rất lớn và chứa secrets. Cần đánh giá storage/IO/retention.
- `-Xlog:gc*,safepoint...` lưu GC và safepoint timeline, có rotation theo filecount/filesize. Mất các log cũ nếu rotation quá nhỏ.
- `NativeMemoryTracking=summary` cung cấp NMT để đọc lúc process còn sống, có overhead; không phải chế độ miễn phí.
- Có thể thiết lập JFR liên tục với giới hạn dung lượng và khoảng giữ lại, nhưng **file recording có tồn tại sau crash hay không** phụ thuộc chế độ flush/disk và tình trạng file; kiểm tra môi trường thực tế.

**Không copy nguyên cấu hình ví dụ vào production** khi chưa đánh giá cgroup headroom, disk, secret retention, performance và quyền trên thư mục. Các đường dẫn phải nằm trong volume thực sự được giữ lại nếu container restart.

### 11.1. Chụp trạng thái khi JVM đang sống

Những lệnh dưới đây là **đo sống / trước sự cố hoặc khi điều tra một process đang còn tồn tại**:

```bash
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 GC.heap_info
jcmd 12345 Thread.print -l
jcmd 12345 VM.native_memory summary scale=MB
```

Nếu muốn so sánh native memory sau warm-up:

```bash
jcmd 12345 VM.native_memory baseline
# Thu một lần nữa sau khoảng quan sát hợp lý:
jcmd 12345 VM.native_memory summary.diff scale=MB
```

Nếu NMT không được bật từ startup, các lệnh `summary`/`summary.diff` không đưa ra số liệu NMT cần tìm. Khi thu liên tục, chọn cadence phù hợp, ghi timestamp và giữ vòng đời file/metric rõ ràng.

### 11.2. Lưu ý về heap dump thủ công

`jcmd PID GC.heap_dump file.hprof` là thao tác ảnh hưởng lớn; HotSpot thường yêu cầu **full GC trước dump**, trừ khi dùng tùy chọn khác (ví dụ `-all` trên JDK 21). Điều đó có thể đổi trạng thái heap và pause application. Không dùng lệnh này sau khi process đã chết hoặc khi hệ thống không chịu được tác động. Nếu cần core dump sau fatal error, cấu hình OS/core-pattern/container runtime và permission phải chuẩn bị riêng.

## 12. Java 17+ runnable: tự chụp snapshot đối chiếu trước crash

Không thể dùng Java code chạy **sau** khi JVM đã chết để đọc lại runtime state đã mất. Ví dụ sau đóng vai trò **chụp evidence lúc còn sống**: timestamp UTC, PID, JVM uptime, Java/OS version, heap used/committed/max, non-heap memory, thread count và trạng thái thread. Đầu ra có thể gửi vào một hệ thống logs an toàn; chương trình mẫu chỉ in stdout để chạy độc lập.

Tạo file **`CrashContextSnapshot.java`**:

```java
import java.lang.management.*;
import java.time.Instant;
import java.util.EnumMap;
import java.util.Map;

public final class CrashContextSnapshot {
    private static String mebibytes(long bytes) {
        return bytes < 0 ? "unknown" : Long.toString(bytes / 1_048_576);
    }

    public static void main(String[] args) {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        OperatingSystemMXBean os = ManagementFactory.getOperatingSystemMXBean();

        MemoryUsage heap = memory.getHeapMemoryUsage();
        MemoryUsage nonHeap = memory.getNonHeapMemoryUsage();
        Map<Thread.State, Integer> states = new EnumMap<>(Thread.State.class);
        for (Thread.State state : Thread.State.values()) {
            states.put(state, 0);
        }
        ThreadInfo[] infos = threads.getThreadInfo(threads.getAllThreadIds(), 0);
        for (ThreadInfo info : infos) {
            if (info != null) {
                states.merge(info.getThreadState(), 1, Integer::sum);
            }
        }

        System.out.println("captureUtc=" + Instant.now());
        System.out.println("pid=" + ProcessHandle.current().pid()
                + " uptimeMs=" + runtime.getUptime());
        System.out.println("javaVersion=" + System.getProperty("java.version"));
        System.out.println("os=" + os.getName() + "/" + os.getArch());
        System.out.println("heapUsedMiB=" + mebibytes(heap.getUsed())
                + " heapCommittedMiB=" + mebibytes(heap.getCommitted())
                + " heapMaxMiB=" + mebibytes(heap.getMax()));
        System.out.println("nonHeapUsedMiB=" + mebibytes(nonHeap.getUsed()));
        System.out.println("liveThreads=" + threads.getThreadCount()
                + " states=" + states);
        System.out.println("snapshotComplete");
    }
}
```

Biên dịch/chạy bằng Java 17+:

```bash
javac --release 17 CrashContextSnapshot.java
java CrashContextSnapshot
```

Ví dụ **stdout đã kiểm thử trên một máy Windows/JDK 24**, số liệu môi trường và thời điểm không phải output cố định:

```text
captureUtc=2026-10-29T11:09:24.922191200Z
pid=4452 uptimeMs=52
javaVersion=24.0.2
os=Windows 11/amd64
heapUsedMiB=0 heapCommittedMiB=2048 heapMaxMiB=30208
nonHeapUsedMiB=1
liveThreads=7 states={NEW=0, RUNNABLE=5, BLOCKED=0, WAITING=1, TIMED_WAITING=1, TERMINATED=0}
snapshotComplete
```

Dòng cuối **`snapshotComplete`** là marker ổn định khi chương trình chạy thành công. Những con số trước nó thay đổi tùy JVM, số processors, startup, flags và OS. `heapUsedMiB=0` trong mẫu chỉ phản ánh làm tròn xuống MiB ở tiến trình ngắn, **không có nghĩa Java heap không có đối tượng**.

### 12.1. Cần hiểu giới hạn snapshot mẫu

- `MemoryMXBean` cho Java heap và non-heap do VM quản lý, **không đo đầy đủ RSS, native malloc hoặc cgroup memory.current**.
- `getThreadCount()` và `getAllThreadIds()` là snapshot không atomic; thread có thể đến/đi giữa hai phép đọc. Bảng trạng thái chỉ mô tả thời điểm mẫu, không phải số thread tại crash tương lai.
- `ProcessHandle.current().pid()` là PID trong namespace mà JVM nhìn thấy. Container host có thể nhìn PID khác.
- `RuntimeMXBean.getUptime()` hỗ trợ xác định tuổi tiến trình khi chụp; để ghép crash cần thêm process start timestamp, deployment ID và container ID.
- Bài cố ý **không in toàn bộ JVM arguments/system properties/environment** để tránh vô tình xuất secrets. Để lưu flags, dùng công cụ chẩn đoán với cơ chế lưu trữ và lọc thông tin nhạy cảm.
- Nếu muốn dữ liệu dùng cho hậu kiểm, phải thu snapshot **định kỳ/nhờ monitoring đang hoạt động**, không chỉ chạy chương trình một lần sau khi crash.
- Không trộn số `heapMaxMiB` của demo JVM với memory limit của một service khác. Khi điều tra thật, chạy instrumentation hoặc jcmd trên chính service cần quan sát.

Mục tiêu bài thực hành là cho thấy **kết hợp được nhiều chiều**: timestamp + PID + uptime + heap + threads + JDK + OS. Nó không chứng minh căn nguyên crash. Bằng chứng OS/container phải thu riêng.

## 13. Dựng một timeline có thể kiểm chứng

Giả sử (dữ liệu **hoàn toàn giả định**) một container Java ở node Linux có `memory.max = 1024 MiB`, JVM `-Xmx=768 MiB`:

| Mốc UTC | Nguồn | Quan sát | Diễn giải ban đầu |
| --- | --- | --- | --- |
| 10:00:00 | JVM/GC metrics | Heap used sau GC 360 MiB | Chưa thấy dấu hiệu heap sát Xmx |
| 10:00:20 | OS metrics | RSS JVM tăng từ 670 lên 850 MiB | Có memory growth ngoài live heap hoặc heap resident tăng |
| 10:00:30 | cgroup metrics | `memory.current` 1.010/1.024 MiB | Rất gần hard limit theo cgroup |
| 10:00:31 | Kernel/cgroup events | `oom_kill` counter tăng từ 0 lên 1 | Có OOM kill thuộc phạm vi counter được theo dõi |
| 10:00:31 | Orchestrator | Container trước kết thúc `reason=OOMKilled` | Bằng chứng mạnh rằng cgroup/OS kill đã xảy ra |
| 10:00:32 | Service | Pod/container restart, PID trong container lại là 1 | Process mới, không ghép heap của nó vào process cũ |

**Kết luận hợp lý:** nguyên nhân *kết thúc trực tiếp* rất có khả năng là **OS/container OOM kill**. Số liệu heap sau GC 360 MiB không chứng minh Java heap leak; cần xem direct/native memory, page cache, threads hoặc process khác trong cgroup để giải thích tại sao `memory.current` chạm limit. Nếu cgroup là parent chứa nhiều descendants, `memory.events` có thể phản ánh một process khác; ghép container IDs, event logs và PID victim để củng cố.

**Không kết luận hợp lý:** “JVM chết vì `-Xmx=768 MiB` nên phải tăng `-Xmx` lên 1 GiB.” Cách này có thể làm headroom cho native memory **tệ hơn** khi container hard limit vẫn 1 GiB.

### 13.1. Điều gì làm yếu giả thuyết OOM kill?

- Không có cgroup/OS OOM events **trùng thời gian hoặc victim**, container terminated reason là lỗi readiness/shutdown.
- Exit code 137 do người vận hành dùng `kill -9` hoặc watchdog gửi SIGKILL.
- Metrics `memory.current` thuộc một cgroup **khác** (node/parent) với container vừa chết.
- Chỉ có snapshot **sau restart**, không có trend trước đó.
- `oom_kill` đã khác 0 trước incident, không có delta; hoặc hierarchical counter phản ánh descendant khác.

Một kết luận nên thể hiện **độ tin cậy và bằng chứng còn thiếu**, thay vì ép mọi nguồn thành một câu chuyện duy nhất.

## 14. Hai kịch bản đối chứng: khi “crash vì memory” là chẩn đoán sai

### 14.1. Kịch bản A — fatal native crash trong JNI

Dữ kiện giả định:

- `hs_err` cùng PID/start time báo `SIGSEGV` và `Problematic frame: C [libcompressionjni.so+offset]`.
- Current thread là worker đang ở `_thread_in_native`.
- Heap after-GC ổn định, cgroup memory còn headroom.
- Core stack cho thấy lời gọi JNI liên quan phiên bản thư viện vừa thay đổi.

**Giả thuyết ưu tiên:** lỗi native library, ABI, memory safety hoặc điều kiện gọi JNI. **Chưa thể kết luận** chỉ từ frame top: lỗi ghi đè memory xảy ra sớm hơn có thể biểu hiện tại địa chỉ crash hiện tại.

Bước tiếp: đối chiếu binary build ID, symbols, JNI boundary, input gây crash, concurrency và thay đổi JDK/native library; dùng debugger/core dưới quy trình an toàn; kiểm thử tái hiện trên staging nếu có thể. Việc tăng heap tùy tiện không giải quyết một access violation.

### 14.2. Kịch bản B — tạo thread thất bại, Java heap vẫn trống

Dữ kiện giả định:

- Application log có `OutOfMemoryError: unable to create native thread`.
- `pids.current` gần `pids.max` hoặc `Threads` tăng nhanh.
- `-Xss` tương đối lớn và có nhiều platform threads.
- Heap used thấp hơn `-Xmx` đáng kể.

**Giả thuyết ưu tiên:** chạm giới hạn PID/thread hoặc native resources, không phải một Java heap object leak mặc định.

Bước tiếp: đếm thread creation rate, executor policy, thread stacks, cgroup PID limit, OS `RLIMIT_NPROC`; xem có thread leak do tạo executor vô hạn không. Phân biệt Java exception làm main kết thúc với kernel OOM kill thật sự.

### 14.3. Kịch bản C — heap thực sự cạn

Dữ kiện giả định:

- `OutOfMemoryError: Java heap space` xuất hiện trên stderr.
- GC logs cho thấy heap used sau major/full GC vẫn gần `-Xmx` trong nhiều chu kỳ.
- HPROF cùng incident có lượng lớn cache/session objects bị giữ sống không phù hợp business lifecycle.
- Không có kernel OOM kill tại thời điểm lỗi.

**Giả thuyết ưu tiên:** live set quá lớn hoặc memory leak/giới hạn heap không phù hợp workload. HPROF là bằng chứng về **object graph**, GC logs là bằng chứng về **xu hướng**. Cần kết hợp cả hai, không gọi “leak” chỉ vì retained size lớn một lần.

## 15. Quy trình triage thực tế theo từng nhánh

```text
Ứng dụng biến mất/restart
         |
         v
Có termination reason, exit code, timestamp, process instance?
         |
         +--- Chưa ---> bảo toàn logs + orchestrator/OS metadata
         |
         v
Có Java/HotSpot fatal hs_err hoặc core khớp PID/time?
         |
         +--- Có ---> đọc signal + thread + frame + flags + heap + OS
         |           kiểm tra native/JVM/GC, so với core và build IDs
         |
         +--- Không ---> Có OOME trên Java stderr/heap dump?
                         |
                         +--- Có ---> phân loại heap/metaspace/direct/thread
                         |           đối chiếu GC, NMT, RSS, limits
                         |
                         +--- Không ---> Có OOMKilled/kernel OOM/SIGKILL?
                                         |
                                         +--- Có ---> kiểm tra cgroup/RSS/
                                         |           page cache/native/threads
                                         |
                                         +--- Không ---> kiểm tra SIGTERM,
                                                     deploy, probe, exit,
                                                     host crash, application log
```

Đây là **cây ra quyết định để ưu tiên điều tra**, không phải phân loại loại trừ lẫn nhau tuyệt đối. Một service có thể có Java OOME rồi bị watchdog kill, hoặc native memory tăng dẫn tới cgroup OOM kill, hoặc lỗi JNI làm heap corruption rồi crash trong GC. Timeline giúp phân biệt **nguyên nhân nền** với **sự kiện kết thúc trực tiếp**.

Một kết luận incident chất lượng nên ghi:

- **Observed:** bằng chứng đã nhìn thấy, gồm nguồn, đường dẫn/ID, timestamp.
- **Likely mechanism:** fatal JVM error, Java OOME, SIGKILL/OOMKilled, signal/shutdown...
- **Candidate root cause:** cấu hình memory, JNI/native bug, thiếu heap, thread leak, resource exhaustion...
- **Counter-evidence:** dữ kiện không ủng hộ giả thuyết.
- **Missing evidence:** heap dump, NMT baseline, kernel log, process IDs...
- **Next check / mitigation:** phép đo hoặc thay đổi nhỏ để xác minh, cùng rủi ro khi thực hiện.

## 16. Những sai lầm thường gặp khi ghép bằng chứng

**Sai 1 — Thấy `-Xmx` thấp hơn container limit và kết luận không thể OOMKill.** JVM còn native memory, thread stacks, code cache, metaspace, page cache và cgroup charges.

**Sai 2 — Dùng heap dump như snapshot của tất cả RAM.** HPROF chủ yếu chứa Java object graph; cần OS metrics/NMT/native tools cho phần ngoài heap.

**Sai 3 — Đếm `reserved` là RAM đã dùng.** Address space reserved ≠ committed ≠ resident.

**Sai 4 — Chỉ dùng `exitCode=137`.** SIGKILL có nhiều nguyên nhân. Cần reason, kernel/cgroup events, process victim và timeline.

**Sai 5 — Không thấy `hs_err` nên loại trừ fatal error.** Artifact có thể không được tạo/giữ, hoặc VM bị OS kill mà không có cơ hội ghi.

**Sai 6 — Thấy `Problematic frame V [libjvm]` là kết luận JVM bug.** JNI memory corruption, native libraries hoặc hardware có thể khiến JVM báo lỗi ở vị trí khác với nguyên nhân.

**Sai 7 — Dùng thread dump của JVM sau restart.** PID có thể lặp lại; phải so start time/container ID và timestamp.

**Sai 8 — Đọc `nid` như Java Thread ID.** `nid` thường là native ID có thể viết hex; cần quy đổi đúng để khớp OS TID.

**Sai 9 — Cộng NMT committed + RSS hoặc coi chúng bằng nhau.** Hai hệ đo khác nhau; so xu hướng/category, không cộng đúp.

**Sai 10 — Dùng `memory.events oom_kill=1` một lần đo để quy cho incident.** Counter cần delta và phạm vi cgroup; có thể là sự kiện cũ/hierarchical.

**Sai 11 — Sửa nhiều flags cùng lúc để “test”.** Thay `-Xmx`, GC, thread pool và container limit đồng thời làm khó xác định yếu tố đã tác động.

**Sai 12 — Kết luận leak từ một đồ thị heap lớn.** Retained heap lớn có thể hợp lệ; cần so workload, lifecycle và nhiều snapshot.

**Sai 13 — Thu heap dump khi hệ thống gần hết disk khiến incident trầm trọng hơn.** Dump có chi phí lớn; chuẩn bị volume, retention và thời điểm thu.

**Sai 14 — Dùng timestamp local chưa chuyển UTC hoặc JVM uptime như epoch.** Dễ ghép nhầm log trước/sau restart. Giữ timezone, process start và source của mọi timestamp.

**Sai 15 — Bỏ qua OS PIDs/files/swap/FD limits.** Không phải mọi resource exhaustion là thiếu Java heap.

**Sai 16 — Đăng `hs_err`/core/heap dump công khai.** Artifacts có thể chứa secrets và dữ liệu riêng tư; cần redaction/controlled access.

## 17. Bài tập phân tích và đáp án

### Bài tập 1 — Heap thấp nhưng container bị kill

Container limit 1024 MiB, `-Xmx=768m`. Trước restart, heap used sau GC 350 MiB, OS RSS 890 MiB; `memory.current` 1015 MiB, `oom_kill` tăng, Kubernetes báo `OOMKilled`.

**Câu hỏi:** Có thể kết luận heap leak không? Cần kiểm tra gì nữa?

*Đáp án:* Chưa. Bằng chứng mạnh cho cgroup/OS OOM kill, nhưng heap live thấp chưa chứng minh leak. Cần breakdown native/direct/metaspace/thread/page cache, cgroup descendants, NMT nếu có, kernel victim info và metrics trend. Không tăng `-Xmx` mặc định.

### Bài tập 2 — Native SIGSEGV ở libjvm

`hs_err` báo `SIGSEGV`, `Current thread _thread_in_vm`, problematic frame trong `libjvm`. Không có `OutOfMemoryError`.

**Câu hỏi:** Có chắc JDK có bug?

*Đáp án:* Không. Cần core/native stack, JDK exact build, GC logs, JNI/native library list, memory corruption evidence và bước tái hiện. Có thể là lỗi VM, nhưng frame trong VM cũng có thể là nơi biểu hiện lỗi do mã native khác gây ra.

### Bài tập 3 — PID trùng nhưng uptime khác

Lúc 10:00 có file `hs_err_pid1.log`; lúc 10:02 bạn chạy `jcmd 1 VM.flags` trong container mới và thấy flags khác.

**Câu hỏi:** Dữ liệu nào phản ánh crash lúc 10:00?

*Đáp án:* `hs_err` và các artifact có cùng container/process instance, không phải `jcmd` của JVM mới dù PID cũng là 1. Xác định process start/container ID, deployment version và timestamps.

### Bài tập 4 — Cộng RSS và NMT

NMT committed=600 MiB, OS RSS=720 MiB. Có thể báo process dùng `1320 MiB`?

*Đáp án:* Không. NMT và RSS có phần giao và cách accounting khác nhau; cộng sẽ đếm trùng, không phải memory footprint thật.

### Bài tập 5 — Không có hs_err, exit code 143

Container kết thúc 143 ngay khi rollout. Kernel không có OOM evidence, ứng dụng có log shutdown hook.

*Đáp án:* Điều tra `SIGTERM`/rollout và graceful shutdown trước, không mặc định fatal JVM crash.

### Bài tập 6 — oom_kill=3 nhưng không có delta

Bạn chỉ có một snapshot `memory.events` sau restart với `oom_kill=3`.

*Đáp án:* Không thể khẳng định ba lần OOM xảy ra trong incident này. Cần lịch sử counter, phạm vi cgroup, process victims và orchestrator/kernellog cùng thời điểm.

### Bài tập 7 — Thread count chạm giới hạn

Java stderr `unable to create native thread`; `pids.current=500`, `pids.max=512`, platform threads tăng đột biến.

*Đáp án:* Ưu tiên kiểm tra thread leak, executor pool, cgroup PID limit và OS thread stacks; đây không phải bằng chứng Java heap full.

## 18. Checklist hậu kiểm và chuẩn bị sự cố tiếp theo

- [ ] Xác nhận kiểu kết thúc bằng exit status, reason, signal, Java stderr, `hs_err` và kernel events.
- [ ] Ghép đúng **PID + process start + container ID/node + thời gian UTC**; không nhầm JVM sau restart.
- [ ] Bảo toàn `hs_err`, GC logs, HPROF, core/WER, JFR, ứng dụng logs và dashboard metrics trước khi artifact bị xóa.
- [ ] Nếu có `hs_err`, đã xem signal, current thread, problematic frame, JVM build, heap, flags, OS và libraries.
- [ ] Đã phân biệt Java heap **used/committed/max** với native memory, RSS, VSZ và cgroup charge.
- [ ] Có trend trước crash cho heap after-GC, RSS, `memory.current/max`, native memory, thread count, FDs và CPU.
- [ ] Đã xem `memory.events` **delta**/phạm vi cgroup, kernel OOM victim và orchestrator termination state.
- [ ] Đã kiểm tra thread name/ID/nid và snapshot timing; không đánh đồng Java thread với OS TID.
- [ ] Đã đối chiếu **VM flags hiệu lực** với config thực tế, `-Xmx`, `-Xss`, collector, direct/metaspace, container sizing và NMT.
- [ ] NMT được bật từ startup nếu định dùng; không trông đợi tổng NMT bằng RSS.
- [ ] Đã hiểu các lệnh `jcmd` chỉ áp dụng cho tiến trình **còn sống**, thu có giới hạn ảnh hưởng.
- [ ] Có bằng chứng phủ định hoặc mâu thuẫn, không chọn một nguyên nhân từ một chỉ số riêng lẻ.
- [ ] Artifact nhạy cảm được bảo vệ, redacted và lưu theo thời hạn quy định.
- [ ] Báo cáo có observed evidence, likely mechanism, root-cause hypothesis, confidence, missing data và next checks.

**Kết luận cần nhớ:** Crash là một **sự kiện tại ranh giới JVM–OS–container**. Heap dump cho biết object graph; thread snapshots cho biết execution/locks tại thời điểm thu; VM flags giải thích cấu hình; OS và cgroup cho biết resource charge/limits/kill; `hs_err` giúp soi fatal VM errors. Chỉ khi **ghép những mảnh này theo cùng một process và timeline**, ta mới phân biệt được Java heap exhaustion, native pressure, thread/PID exhaustion, OS OOM kill, native SIGSEGV hoặc shutdown thông thường.

## Tài liệu đối chiếu

- OpenJDK/Java Operations — [How to Find and Interpret the Java HotSpot Fatal Error Log](https://ops.java/troubleshooting/articles/fatal-error-log/): các thành phần của `hs_err`, error header, current thread, heap/OS sections.
- Oracle JDK 21 — [Prepare Java for Troubleshooting](https://docs.oracle.com/en/java/javase/21/troubleshoot/prepare-java-troubleshooting.html): thu fatal log, core, heap dump, JFR/GC logs.
- Oracle JDK 21 — [`jcmd` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `VM.flags`, `VM.command_line`, `Thread.print`, `GC.heap_info`, `VM.native_memory` và overhead.
- Oracle JDK 21 — [`java` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): JVM flags, `-Xmx`, ErrorFile, NMT và diagnostic options.
- Oracle JDK 21 — [Diagnostic Tools / Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): NMT reserved/committed, baseline/diff và giới hạn theo dõi memory ngoài JVM.
- Linux Kernel — [Control Group v2 documentation](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html): `memory.current`, `memory.max`, `memory.events` và cách accounting.
- Kubernetes — [Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): limits, memory enforcement và OOM behavior.
- Oracle Java 21 — [`MemoryMXBean`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html) và [`ThreadMXBean`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): heap/non-heap snapshots và thread data.
- Oracle JDK 21 — [`jfr` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): kiểm tra JFR evidence sau khi dump.