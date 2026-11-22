# 20.9 Phân biệt JVM tự ghi lỗi với tiến trình bị hệ điều hành chấm dứt

## Mục tiêu học tập

Khi một ứng dụng Java đột nhiên biến mất, có nhiều cơ chế có thể dẫn đến cùng một triệu chứng: service ngừng trả lời, process không còn, pod restart và log dừng giữa chừng. Tuy nhiên, **JVM tự phát hiện lỗi nghiêm trọng rồi ghi fatal error log** và **tiến trình bị hệ điều hành hoặc bộ điều phối chấm dứt** là hai nhánh điều tra khác nhau. Một ngoại lệ Java chưa bắt, một lệnh System.exit, sự kiện container OOMKilled hoặc một SIGSEGV trong thư viện native cũng không được gộp làm một loại “JVM crash”.

Bài học này thuộc chủ đề **Crash và phân tích sau lỗi**, tập trung vào việc nhận diện **ai hoặc cơ chế nào đã khiến tiến trình kết thúc**, bằng chứng nào đáng tin, dấu vết nào có thể vắng mặt và cách điều tra có thứ tự sau sự cố.

Sau bài này, bạn có thể:

1. Phân biệt lỗi Java ở mức ứng dụng, thoát JVM chủ động, HotSpot fatal error, external signal và Linux OOM killer/cgroup OOM kill.
2. Đọc đúng các loại dấu vết: hs_err_pid*.log, stack trace, heap dump, core dump, exit status, kernel logs, cgroup memory.events và container termination reason.
3. Giải thích vì sao **exit code 137 không tự chứng minh OOMKilled**, vì sao **không có hs_err không chứng minh OS kill**, và vì sao một OutOfMemoryError không nhất thiết giết cả JVM.
4. Dựng timeline nguồn–bằng chứng–nguyên nhân từ JVM, OS, service manager và orchestrator mà không nhầm lẫn.
5. Thu thập chứng cứ sớm, có bảo mật và ít xâm lấn, rồi đưa ra kết luận theo mức độ chắc chắn.
6. Thực hành với chương trình Java 17+ mô phỏng những đường thoát **có kiểm soát**, không cố gây cạn kiệt bộ nhớ hay phá JVM thật.

Phạm vi: Java 17+ chạy trên HotSpot/OpenJDK, Linux hoặc container/Kubernetes khi ví dụ OS liên quan. Hành vi logging, exit status, signals, core dumps và công cụ quản trị phụ thuộc OS/JDK/vendor/container runtime. Luôn xác nhận trên môi trường cụ thể; **không dùng các thao tác kill/crash để thử trên dịch vụ production**.

## 1. Đặt đúng câu hỏi: tiến trình chấm dứt theo cơ chế nào?

Khi ứng dụng chết, ít nhất phải tách năm nhóm:

| Nhóm | Mô tả | Bằng chứng thường thấy | Không được suy luận vội |
| --- | --- | --- | --- |
| **Java-level failure** | Một thread ném ngoại lệ không được bắt, kể cả một số OutOfMemoryError | Java exception stack trace, app logs, đôi khi nonzero exit | Không mặc nhiên là fatal JVM crash hoặc OS OOM kill |
| **JVM chủ động kết thúc** | main kết thúc, System.exit, Runtime.halt hoặc chính sách ExitOnOutOfMemoryError | Exit status và log trước khi thoát, hook có thể chạy | Exit code khác 0 chưa chắc do OS gửi tín hiệu |
| **JVM fatal error / native crash** | HotSpot hoặc native code gặp lỗi nghiêm trọng: SIGSEGV, SIGBUS, fatal internal error, intentional CrashOnOutOfMemoryError | hs_err_pid*.log, có thể core dump, signal-related status | Tín hiệu SIGSEGV từ kernel không đồng nghĩa bị OOM killer chấm dứt |
| **External termination** | systemd, operator, deploy controller, liveness probe, timeout, runtime gửi SIGTERM rồi có thể SIGKILL | Service manager/events, signal status, lifecycle records | SIGKILL không nhất thiết do hết bộ nhớ |
| **OS/cgroup OOM kill** | Kernel chọn một hoặc nhiều tasks để kill vì memory pressure/limit | Kernel OOM message, cgroup oom_kill tăng, Kubernetes reason OOMKilled | Heap used thấp không loại trừ tổng memory cgroup vượt giới hạn |

Một process có thể có **nhiều yếu tố góp phần**. Ví dụ native memory tăng làm container vượt memory.max; kernel SIGKILL Java mà không cho JVM chạy fatal-error handler. Hoặc Java code bắt OOME rồi gọi System.exit: có OOME và nonzero exit nhưng không có OOM killer. Vì thế cần phân biệt:

- **Triệu chứng:** process biến mất hoặc application không phục vụ.
- **Cơ chế kết thúc (termination mechanism):** exit thông thường, signal, fatal error hoặc kernel kill.
- **Nguyên nhân sâu (root cause):** code bug, data growth, memory budget, native library, deployment, watchdog, storage failure...
- **Bằng chứng:** loại artifact và nguồn tạo ra nó, có timestamp/instance khớp.

“OS là bên gửi tín hiệu” và “lỗi phát sinh từ JVM/native code” không luôn đối lập tuyệt đối. Ví dụ lỗi truy cập bộ nhớ phát sinh trong native code khiến kernel giao SIGSEGV; JVM có thể bắt tín hiệu, tạo hs_err rồi tiến trình chấm dứt. Khác với việc **kernel OOM killer gửi SIGKILL để thu hồi bộ nhớ**.

## 2. Hiểu ba đường kết thúc rất dễ nhầm

### 2.1. Java exception không tự đồng nghĩa JVM fatal error

Nếu thread ném RuntimeException chưa bắt, runtime thường in stack trace qua uncaught exception handler; **chỉ thread đó kết thúc**. JVM có thể vẫn chạy nếu còn non-daemon threads. Nếu main là thread user cuối cùng, JVM có thể tự kết thúc và shell thấy mã lỗi; đây không phải bằng chứng HotSpot/native crash.

java.lang.OutOfMemoryError là một **Error ở tầng Java**: có thể do heap, metaspace, native thread, direct buffer hoặc một giới hạn khác tùy message và nguồn phát sinh. Nó cũng có thể được ném, bắt hoặc được JVM xử lý theo các flags. Không mặc định có hs_err cho mọi OOME. Một heap dump do -XX:+HeapDumpOnOutOfMemoryError không giống fatal error log.

### 2.2. JVM fatal error là tình huống khác

HotSpot có fatal error reporting khi gặp lỗi không thể tiếp tục an toàn, chẳng hạn lỗi VM internal, memory access fault trong mã native/JVM, một số lỗi native allocation fatal hoặc cấu hình chủ động crash. JVM có thể xuất báo cáo hs_err_pid*.log với “A fatal error has been detected by the Java Runtime Environment”, “Problematic frame”, trạng thái thread, native/Java stack và thông tin VM/OS.

Điểm quan trọng:
- **Có hs_err phù hợp timestamp/PID** là dấu hiệu mạnh rằng cơ chế fatal-error reporting của JVM đã chạy.
- **Có hs_err không tự chứng minh lỗi do mã Java thuần**, vì JNI/native agent/driver/JVM bug hoặc phần cứng đều có thể liên quan.
- **Không thấy hs_err** không chứng minh không có JVM fatal error: JVM có thể không kịp ghi, không có quyền/disk, bị kill đột ngột, file nằm nơi khác, bị xóa hoặc log hỏng một phần.

### 2.3. Bị gửi tín hiệu không mặc định là OOM kill

Trên Linux:
- **SIGTERM (15)** là yêu cầu kết thúc; JVM HotSpot thông thường có cơ hội shutdown có kiểm soát nếu signal handling phù hợp.
- **SIGKILL (9)** không thể bắt, bỏ qua hay chặn bằng shutdown hook: process dừng ngay, không kịp ghi hs_err hoặc heap dump theo lộ trình JVM thông thường.
- **SIGSEGV (11)** là memory access fault; HotSpot có thể xử lý để báo fatal error, nhưng cũng có thể chết trước khi tạo đủ artifact.
- **SIGABRT (6)** có thể xuất hiện khi native code/JVM chủ động abort hoặc từ tác nhân khác; phải kiểm tra nguồn.
- **SIGBUS (7, trên Linux)** có thể liên quan truy cập memory-mapped region hoặc lỗi bộ nhớ/thiết bị; không đủ để gọi OOMKilled.

Cả operator “kill -9”, service manager escalated shutdown và kernel OOM killer đều có thể tạo một trạng thái termination bằng SIGKILL. **Cần biết ai gửi tín hiệu, tại sao và thời điểm nào**, không chỉ đọc số 9.

## 3. Bảng chẩn đoán nhanh theo dấu vết

| Quan sát | Gợi ý hợp lý | Việc cần kiểm chứng |
| --- | --- | --- |
| Có hs_err_pid1234.log mới, header báo SIGSEGV, problematic frame là libxyz.so | JVM/native fatal error xảy ra | Đúng PID/start time? thư viện JNI/agent/JVM version? core dump? |
| App logs có “Exception in thread main” rồi exit 1 | Uncaught Java exception có thể khiến JVM kết thúc | Còn thread sống không? có System.exit trong error handler? |
| App logs có “OutOfMemoryError: Java heap space” | JVM ném Java OOME về heap | Có exit thật? heap dump? heap/GC trend? flags ExitOnOOME? |
| Pod lastState.terminated.reason = OOMKilled, exitCode 137 | Container đã được runtime/orchestrator xác nhận bị OOM kill | Đúng container, thời điểm, cgroup/Node/kernel evidence và memory source |
| Chỉ thấy exitCode 137 | Thường tương thích SIGKILL theo quy ước shell | Kube reason là gì? hệ thống gửi SIGKILL? app có thể exit(137)? |
| ExitCode 143 kèm rollout/termination event | Có thể SIGTERM theo quy ước 128+15 | Deployment/liveness/systemd logs? JVM có shutdown hook không? |
| ExitCode 139, có hs_err SIGSEGV | Native/VM memory fault có khả năng cao | Core/native stack, JVM/JNI/agent, không mặc định OOM killer |
| Không có hs_err, logs dừng đột ngột, memory.events oom_kill tăng | Nghi kernel/cgroup OOM kill | Counters đúng cgroup? kernel log/termination reason? |
| Không có hs_err, process chết sau liveness probe failed | Nghi orchestrator restart | Probe failure reason, grace period, signal/exit code, app hang trước đó |
| Có core dump nhưng không có hs_err | Process chết do fatal signal/core-producing mechanism | Core thuộc PID nào, signal nào, core handler, không vội kết luận JVM bug |
| Service restart nhưng PID cũ không có chứng cứ exit | Có thể rolling deploy, process supervisor, runtime reset | Lifecycle events, previous logs, restart reason, PID/instance mapping |
| OOMKill counters không tăng, app log có exit request | Chưa có bằng chứng kernel OOM kill | Cùng cgroup/khung thời gian? systemd/container audit? |

Bảng chỉ là **định hướng điều tra**, không phải phép suy diễn một–một. Một container có thể nhận SIGTERM rồi SIGKILL sau grace period và cho exit 137, nhưng reason không phải OOMKilled. Một JVM có thể crash native rồi container report generic Error. Exit 1/134/137/139/143 đều cần nguồn bổ trợ.

## 4. Đọc hs_err_pid*.log: khi JVM kịp ghi fatal error

### 4.1. Nội dung thường có

Một HotSpot fatal error log, tùy JDK/version và mức hoàn chỉnh, có thể ghi:

- Header “A fatal error has been detected by the Java Runtime Environment”.
- Signal/code: SIGSEGV, SIGBUS, SIGILL, internal error và địa chỉ liên quan.
- PID, thread ID, thời điểm, VM/version/build, uptime.
- **Problematic frame:** ví dụ mã JIT, libjvm.so, libc.so, thư viện JNI, native agent...
- Current thread, thread state và native/Java stack, dynamic libraries.
- Heap/metaspace, VM arguments, command line, môi trường OS và memory map.
- Instruction pointers/registers hoặc thông tin thấp hơn, không phải lúc nào cũng đầy đủ.

**Đọc đúng:** “Problematic frame” là nơi fault được quan sát hoặc nơi phát hiện lỗi, **không nhất thiết là nơi bắt đầu bug**. Heap corruption có thể xảy ra từ trước; JNI viết sai bộ nhớ làm JVM chết sau đó ở code khác. Một frame libjvm.so không đủ chứng minh “JDK bug” nếu agent/JNI hoặc native corruption gây trước.

### 4.2. Dấu vết mẫu, chỉ để nhận diện

~~~text
# A fatal error has been detected by the Java Runtime Environment:
#
#  SIGSEGV (...) at pc=..., pid=1234, tid=...
#
# Problematic frame:
# C  [libexample.so+...]
#
# An error report file with more information is saved as:
# /var/log/app/hs_err_pid1234.log
~~~

Đây là **mẫu hình thức minh họa**, không phải output của chương trình chạy kèm bài, không phải bảo đảm log luôn giống hệt. C ở dòng frame có thể biểu thị native C/C++ frame theo notation HotSpot; có thể gặp J (compiled Java), V (VM code), j (interpreted Java) và những ký hiệu khác theo version.

### 4.3. Kiểm chứng artifact chính xác

Khi tìm hs_err, cần hỏi:
1. Đường dẫn thực do JVM ghi ở đâu? Startup working directory có phải nơi operator đang đứng không?
2. Có cờ -XX:ErrorFile định hướng output? Giá trị %p có được thay bằng PID không?
3. File có thuộc **đúng process**, đúng instance/container, đúng thời điểm không?
4. Có được ghi đầy đủ hay bị cắt vì disk full, process bị kill giữa lúc báo lỗi?
5. Native library/agent nào trong loaded modules? Có thay version/build ngay trước sự cố?
6. Có core dump tương ứng hoặc symbol/debug information để điều tra sâu không?

Nếu hs_err còn tồn tại nhưng process đã bị restart, **giữ nguyên bản gốc**, ghi thời gian, vị trí, checksum khi cần và hạn chế chia sẻ công khai vì có thể chứa thông tin nhạy cảm.

## 5. Khi nào không có hs_err và điều đó có nghĩa gì?

Nhiều tình huống **không kỳ vọng** có hs_err:

- Java exception hoặc OutOfMemoryError được xử lý ở tầng Java.
- Main thread kết thúc và JVM thoát bình thường.
- System.exit(code) được gọi.
- Runtime.halt(code) kết thúc ngay mà không qua shutdown sequence thông thường.
- Process bị SIGKILL từ operator, service manager hoặc kernel OOM killer.
- Container bị xóa/kill trong khi JVM không có cơ hội thực thi fatal-error handler.

Nhưng **vắng hs_err không đủ chứng minh** các cơ chế trên vì cũng có thể là một JVM fatal error **không ghi được file**: disk full, permission denied, path không tồn tại, filesystem ephemeral bị xóa, JVM quá hỏng, native crash rất sớm, fatal signal và core policy, JVM khác HotSpot hoặc file được lưu nơi khác.

Ngược lại, presence của hs_err không loại trừ external factors: agent native do vận hành cài, lỗi file mapping, thiết bị/OS, process được stop sau khi JVM đã bắt đầu báo fatal error. Cần nối **nhiều nguồn evidence cùng PID/timestamp**.

## 6. Phân biệt Java OutOfMemoryError với kernel/cgroup OOM kill

### 6.1. OutOfMemoryError là sự kiện ở JVM/Java

Ví dụ thông báo:
- java.lang.OutOfMemoryError: Java heap space;
- java.lang.OutOfMemoryError: GC overhead limit exceeded;
- java.lang.OutOfMemoryError: Metaspace;
- java.lang.OutOfMemoryError: Direct buffer memory;
- java.lang.OutOfMemoryError: unable to create native thread.

Chúng phản ánh những vùng/tình huống tài nguyên khác nhau, không có nghĩa OS đã kill process. Một số trường hợp là Java-level OOME do thư viện/lớp Java ném; không phải mọi biến thể đều chắc chắn có heap dump.

Ứng dụng có thể:
- bắt OOME và tiếp tục chạy trong tình trạng suy giảm;
- không bắt được ở một thread, khiến thread kết thúc còn JVM sống;
- thoát vì fatal policy, wrapper hoặc System.exit;
- bị cgroup OOM kill ở thời điểm khác nếu tổng memory vẫn tăng.

**Đừng kết luận “hết heap” chỉ vì pod OOMKilled**: container memory bao gồm nhiều thành phần ngoài Java heap như metaspace, code cache, direct/native buffers, thread stacks, malloc/JNI, page cache và những process khác trong cgroup. Cũng đừng kết luận “OS kill” chỉ vì log có chữ OutOfMemoryError.

### 6.2. JVM HotSpot có các cờ thay đổi đường kết thúc

Các tùy chọn liên quan gồm:
- -XX:+HeapDumpOnOutOfMemoryError: cố tạo heap dump cho một số OOME do JVM phát hiện theo cơ chế hỗ trợ; cần không gian/permission, không bảo đảm cho OS kill.
- -XX:HeapDumpPath=...: đích ghi heap dump khi kích hoạt; kiểm tra path/volume.
- -XX:+ExitOnOutOfMemoryError: chính sách JVM exit khi có OOME.
- -XX:+CrashOnOutOfMemoryError: cố tạo fatal-error crash khi có OOME, dùng trong những trường hợp được thiết kế đặc biệt; không dùng tùy tiện production.
- -XX:ErrorFile=...: nơi ghi HotSpot fatal error log.
- -XX:OnOutOfMemoryError=...: chạy lệnh được cấu hình khi phát hiện OOME trong những điều kiện hỗ trợ; không phải đảm bảo chạy khi kernel SIGKILL.

**Lưu ý:** các cờ không tự thay đổi semantics của memory cgroup. Dù có HeapDumpOnOutOfMemoryError, một SIGKILL có thể xảy ra trước khi JVM biết/ghi được Java OOME. Heap dump cũng có thể gây disk pressure và chứa dữ liệu nhạy cảm.

### 6.3. OS OOM killer đi theo đường khác

Khi Linux kernel thiếu memory theo chính sách hệ thống hoặc một memory cgroup vượt giới hạn, OOM logic có thể chọn task rồi gửi SIGKILL. Với JVM bị chọn, process **không có quyền thương lượng**; shutdown hooks không chạy, JVM không có cơ hội thông thường tạo hs_err/heap dump tại thời điểm kill.

Bằng chứng gần nguồn:
- Kernel log có OOM message và **Killed process** với PID/comm/memory context.
- cgroup v2 memory.events (hoặc memory.events.local) có oom_kill counter tăng **đúng cửa sổ**.
- Container runtime/Kubernetes báo last terminated reason OOMKilled đối với đúng container.
- Metrics memory.current, memory.max, working set/RSS, restartCount, node/container pressure và time series phù hợp.

**Không coi một snapshot sau restart là memory trước crash.** Cgroup cũ có thể bị xóa, counters reset, logs rotate; cần metrics lịch sử hoặc thông tin từ runtime/monitoring.

### 6.4. Cgroup OOM, node OOM, userspace OOM management và eviction

Các hiện tượng không đồng nhất:

| Cơ chế | Bên quyết định | Dấu vết thường gặp |
| --- | --- | --- |
| Memory cgroup vượt limit | Kernel memcg OOM | memory.events oom_kill, container OOMKilled, exit do SIGKILL |
| Node/global memory pressure | Kernel global OOM killer | Kernel OOM message, victim PID, node memory metrics; container status tùy runtime |
| systemd-oomd hoặc daemon quản lý pressure | Userspace daemon chọn cgroup/process để kill | Journal của daemon, cgroup/pressure, signal; có thể **không có kernel OOM message** |
| Kubelet node-pressure eviction | Kubelet evict pod theo eviction policy | Pod events/reason Evicted, kubelet logs; không mặc định là kernel OOMKilled |
| Liveness probe/deploy/timeout | Controller, kubelet, service manager | Probe failures, rollout events, SIGTERM và có thể SIGKILL sau grace |
| Ứng dụng tự thoát vì OOME | JVM hoặc app policy | OOME log/flag, process exit, không nhất thiết OOMKilled |

Khi người vận hành nói “pod bị OOM”, yêu cầu làm rõ **OOMKilled**, **Evicted do MemoryPressure**, **ứng dụng log OOME** hay **node/global kill**. Hướng sửa khác nhau: phân tích live heap, native memory/cgroup budget, capacity node, request/limit/eviction policy, hay lỗi application.

## 7. Exit status và tín hiệu: dùng làm manh mối, không dùng làm phán quyết

### 7.1. Các số thường thấy

Trên shell Linux và nhiều container runtime, một quy ước thường gặp là **128 + signal number** khi process bị tín hiệu kết thúc. Ví dụ:

| Mã quan sát | Có thể tương ứng | Điều kiện xác minh |
| --- | --- | --- |
| 0 | Hoàn tất thành công theo quy ước app | App có thực sự phục vụ/đạt SLO trước khi thoát? |
| 1 | Lỗi chung, uncaught exception, explicit exit(1) | Stack trace, framework exit policy, service manager |
| 134 | 128 + SIGABRT(6) | Fatal/native abort hay tác nhân ngoài? hs_err/core? |
| 137 | 128 + SIGKILL(9) | OOM killer hay kill -9/timeout/probe? |
| 139 | 128 + SIGSEGV(11) | Native/VM memory fault hay signal khác? hs_err/core? |
| 143 | 128 + SIGTERM(15) | Deploy, pod termination, service manager, operator? |

Đây không phải ánh xạ đảm bảo cho mọi OS/shell/runtime. **Exit code tự thân không chứa toàn bộ thông tin ai gửi signal**. Một chương trình Java có thể gọi System.exit(137) và tạo mã 137 **mà không có SIGKILL**. Một wrapper/supervisor có thể ghi status của chính wrapper hoặc biến đổi status của process con.

Trên Linux, cha của process có thể phân biệt **WIFEXITED** với **WIFSIGNALED** trong wait status thô; log orchestrator có thể hiển thị dạng exit code đã chuẩn hóa. Không lấy chuỗi “exitCode: 137” từ dashboard làm bằng chứng hoàn chỉnh rằng kernel đã giết vì hết bộ nhớ.

### 7.2. SIGTERM khác SIGKILL

SIGTERM thường cho chương trình cơ hội:
- nhận tín hiệu theo cơ chế runtime;
- chạy shutdown hooks nếu JVM đang shutdown bình thường và không bị ép;
- giải phóng connections, flush logs, trả readiness false hoặc xử lý drain.

Nhưng SIGTERM cũng có thể không dẫn đến shutdown sạch: process bị treo, hook chạy quá lâu, signal handler thay đổi hoặc sau grace period controller gửi SIGKILL. Sau SIGKILL, không có thêm Java shutdown log; absence của “shutting down” không phân biệt được kernel OOM với operator kill.

**Không thử kill -9 trên dịch vụ thật** chỉ để xác minh mã 137. Nếu cần minh họa, dùng process Java độc lập trong môi trường lab, ghi PID và biết rõ phạm vi.

### 7.3. SIGSEGV có phải “OS chấm dứt” không?

Lỗi truy cập bộ nhớ trong native/JIT/JVM code thường khiến kernel gửi tín hiệu SIGSEGV. Nhưng bản chất của sự cố là **memory fault** trên đường thực thi process; HotSpot thường cố tạo fatal error report. Vì vậy một hs_err SIGSEGV nên đi theo hướng **native/JVM crash analysis**, không bị gộp với external administrative kill.

Nếu JVM dùng JNI, agent monitoring, native library, Unsafe hoặc foreign/native interfaces, không thể chỉ nhìn frame libjvm rồi tự kết luận JVM core có bug; phải xem caller/callee, version, native memory corruption và khả năng tái hiện.

## 8. Bằng chứng từ Linux: kernel, cgroup, service manager

### 8.1. Kernel logs trong đúng cửa sổ thời gian

Các lệnh đọc-only minh họa (tùy distro và quyền):

~~~bash
journalctl -k --since "2026-10-29 09:00:00" \
  --until "2026-10-29 09:20:00"
dmesg -T
~~~

Trong sự cố thực, thay thời gian bằng **incident window đúng theo timezone**; -T hiển thị wall time suy từ kernel timestamps và có thể chịu ảnh hưởng khi clock thay đổi. Ưu tiên journal logs với timestamp chính xác khi có.

Tìm:
- “Out of memory” và “Killed process PID ... (java)”;
- “Memory cgroup out of memory” hoặc các biến thể kernel/distro;
- PID và memory context, cgroup path, node/pod association;
- các dấu hiệu kernel/device lỗi khác nếu phù hợp.

**Thiếu dòng OOM trong dmesg không phủ định OOM kill**: quyền đọc bị giới hạn, ring buffer đã ghi đè, logs không được lưu dài hạn, process bị userspace OOM daemon kill hoặc bạn xem sai node/thời gian.

### 8.2. Cgroup v2 memory counters

Trong **đúng cgroup của container/process** và hệ thống dùng cgroup v2:

~~~bash
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/memory.events.local
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
~~~

Ý nghĩa:
- **memory.events:** counters các trạng thái như low, high, max, oom, oom_kill... tùy kernel/config, thường có tính phân cấp.
- **memory.events.local:** local events của chính cgroup, giúp tránh lẫn propagation từ descendants.
- **memory.current:** lượng memory cgroup đang được tính tại thời điểm đọc.
- **memory.max:** hard memory limit hoặc “max” nếu không giới hạn.
- **oom_kill:** số OOM kills thuộc phạm vi counter. Cần so **delta theo thời gian**, không chỉ một giá trị tích lũy.
- **oom:** số lần cgroup chạm tình huống OOM theo semantics kernel; **không đồng nghĩa số kills**.
- **high/max:** cho thấy pressure hoặc chạm giới hạn tương ứng; cũng không tự chứng minh process đã bị kill.

Cách đọc phải xác minh mount/cgroup path từ /proc/PID/cgroup **trước khi process chết** hoặc từ orchestrator/runtime. /sys/fs/cgroup của container có thể được namespace hóa, giới hạn hiển thị hoặc không phải đúng cgroup trong host view. **Nếu cgroup bị xóa sau restart, không thể đọc lại counter của cgroup cũ từ đường dẫn mới và giả vờ đó là số liệu trước crash.**

Một oom_kill tăng mạnh ở cgroup cha không tự nói victim là Java: trong cùng pod/cgroup có thể có process phụ hoặc descendant khác. Ghép kernel victim PID, container status và timestamps.

### 8.3. systemd và userspace OOM manager

Với service được systemd quản lý:

~~~bash
systemctl status my-java-service
systemctl show my-java-service \
  -p Result -p ExecMainCode -p ExecMainStatus
journalctl -u my-java-service --since "2026-10-29 09:00:00"
journalctl -u systemd-oomd --since "2026-10-29 09:00:00"
~~~

Các tên service và mốc thời gian trên chỉ là ví dụ. systemd có thể báo code=exited hoặc code=killed và status theo signal khi đủ thông tin, cùng restart/timeout/watchdog reason tùy version. Nếu systemd-oomd là tác nhân, journal của nó có thể là bằng chứng chính dù kernel log không ghi “Killed process” theo mẫu kernel OOM killer.

Không đồng nhất “service đang active sau restart” với “JVM cũ không từng chết”. Cần lấy log của **lần process cũ** và restart count.

### 8.4. Core dump không phải bằng chứng độc quyền của JVM

Trên Linux, core dump có thể phát sinh vì signal lỗi fatal cho nhiều chương trình, không riêng JVM. Có thể kiểm tra:

~~~bash
ulimit -c
cat /proc/sys/kernel/core_pattern
coredumpctl list
~~~

Lệnh coredumpctl phụ thuộc hệ thống có systemd-coredump hay không. ulimit/core_pattern ảnh hưởng cách core được tạo/thu hồi; file có thể lớn, bảo mật cao và bị retention xóa. **Không có core dump** không chứng minh process không crash; **có core dump** cũng không tự chứng minh nguyên nhân thuộc JVM core.

Đối với JVM fatal error, core/native stack + hs_err + symbols và version native libraries thường bổ sung nhau; cần đúng PID/timestamp/architecture.

## 9. Kubernetes và container: xem đúng container đã chết

### 9.1. Các lệnh read-only thường dùng

~~~bash
NS=default
POD=example-pod
CONTAINER=example-container

kubectl describe pod "$POD" -n "$NS"
kubectl logs "$POD" -n "$NS" -c "$CONTAINER" --previous
kubectl get pod "$POD" -n "$NS" -o json
~~~

Dùng tên thực và quyền phù hợp. Lệnh --previous truy xuất log của một container instance trước nếu runtime còn giữ; nó **không bảo đảm** có toàn bộ lịch sử nhiều lần restart. Pod events có hạn lưu; JSON có thể chứa metadata nhạy cảm, không phát tán nguyên bản.

Kiểm tra:
- **status.containerStatuses[].lastState.terminated.reason**, exitCode, startedAt, finishedAt, message;
- restartCount của **đúng container** trong pod;
- pod phase/reason và Events: OOMKilled, Evicted, Killing, Unhealthy/liveness, rollout/drain, sandbox changes;
- memory limits/requests, actual resource usage **trước khi chết**, CPU throttling, node MemoryPressure;
- container IDs, pod UID, node ID, process start times để không nhầm pod mới cùng tên logic.

**Reason=OOMKilled** trên trạng thái termination của container là bằng chứng mạnh theo phân loại runtime/orchestrator về một OOM kill. Nhưng vẫn nên đối chiếu kernel/cgroup, container memory breakdown và workload để giải thích **tại sao** vượt giới hạn. **ExitCode=137 nhưng reason=Error** có thể do kill khác; kiểm tra events và shutdown timeline.

### 9.2. Restart sau liveness failure và shutdown escalation

Ví dụ giả định:

~~~text
12:00:00 liveness probe failed
12:00:01 kubelet requested termination (SIGTERM)
12:00:31 grace period expired; SIGKILL
12:00:32 container exit code 137
~~~

Điều này tạo exit 137 **mà không cần kernel OOM killer**. Muốn kết luận phải tìm liveness/probe failure, kubelet events và grace period. Nguyên nhân gốc có thể là JVM deadlock, GC pause, network timeout hoặc probe quá gắt; SIGKILL chỉ là **cơ chế kết thúc cuối cùng**.

Ngược lại một OOMKilled có thể xảy ra dù liveness probes xanh trước đó; kernel kill có thể nhanh hơn đường SIGTERM. Đừng dùng hiện diện/absence của shutdown hook log làm tiêu chí duy nhất.

### 9.3. Docker runtime và tình huống không dùng Kubernetes

Trong môi trường Docker, khi có quyền:

~~~bash
docker inspect --format '{{.State.OOMKilled}} {{.State.ExitCode}} {{.State.FinishedAt}}' example-container
docker logs --timestamps example-container
~~~

Đây là cú pháp minh họa Docker CLI; cần đúng container ID/tên. OOMKilled=true giúp phân biệt runtime báo OOM termination so với những nonzero exits khác. Docker không nhất thiết lưu mọi log đã rotate; phải ghép timestamps, kernel/cgroup records, cấu hình resource limit và nguyên nhân làm memory tăng.

Với ECS/Nomad/containerd hoặc nền tảng khác, tìm termination reason/exit status và events **tương đương**, không suy đoán rằng nơi nào cũng dùng trường status giống Kubernetes.

## 10. Tập hợp bằng chứng: nguồn nào trả lời câu hỏi nào?

| Câu hỏi | Nguồn nên ưu tiên | Giới hạn |
| --- | --- | --- |
| JVM đã tự phát hiện fatal error chưa? | hs_err file và header phù hợp PID/timestamp; JVM stderr | Không thấy file chưa phủ định |
| Có Java-level exception/OOME không? | App logs/stderr, exception stack trace, heap dump và JVM flags | Có OOME không có nghĩa process bị kernel kill |
| Process thoát bình thường hay bị signal? | Parent/supervisor raw wait status, container runtime/service manager | Flattened exitCode có thể mơ hồ |
| Signal là SIGKILL từ ai? | Kernel OOM logs, cgroup oom_kill, orchestrator/events, audit/supervisor | Exit 137 một mình không xác nhận sender |
| Tại sao memory bị cạn? | Memory timeline, container memory.max/current/peak, JVM heap/native memory, process RSS, workload | Snapshot sau restart không đủ |
| Có native/JVM crash? | hs_err, core dump/native stack, loaded libraries, JDK build, agent/JNI | Problematic frame không nhất thiết là root cause |
| Có liveness/probe/rollout? | Pod events, kubelet/controller logs, service manager journal | Events có retention/clock skew |
| Có node-level eviction/OOM? | Node kernel logs, MemoryPressure, eviction messages, kubelet/systemd-oomd | Không nhầm container OOMKilled |
| Crash có xảy ra trước khi bị kill? | Timeline ghép hs_err, manager signals, kernel logs | Cả hai dấu vết có thể xuất hiện trong một chuỗi |
| Có đủ bằng chứng để thay heap? | Heap trend, GC/native memory, cgroup budget, OOM reason | Heap size không giải quyết mọi native/cgroup OOM |

**Một artifact không phải toàn bộ câu chuyện.** Bằng chứng mạnh thường có **hai nguồn độc lập** cùng mô tả cùng PID/instance và thời điểm: ví dụ container lastState OOMKilled + kernel/cgroup oom_kill delta; hoặc hs_err SIGSEGV + core dump/native frame từ đúng process.

## 11. Runbook điều tra một Java process vừa biến mất

### Bước 1 — Chứng minh process đã kết thúc, không chỉ treo

Xác định service instance, container ID, pod UID, PID, process start/end, node và timestamp UTC. Application không trả request có thể do deadlock, pool saturation, network partition, probe fail hoặc process chết. Đừng mặc định “crash” nếu process còn sống.

Nếu process đã chết và supervisor tự restart, ghi **PID cũ** và thời điểm restart. Không dùng dữ liệu jcmd/heap của PID mới để kết luận về bộ nhớ của PID cũ.

### Bước 2 — Thu dấu vết có thể mất sớm

Ưu tiên:
- App stderr/stdout cuối cùng và logs trước restart; logs --previous nếu phù hợp.
- hs_err, heap dump, core dump còn trên persistent volume/working directory.
- Container last termination reason/exitCode/finishedAt; runtime/systemd/kubelet events.
- Kernel logs đúng node và cgroup memory events/monitoring time series.
- Deployment/rollout/health probe/scale-down/eviction events.
- Nếu process chưa chết nhưng báo lỗi: JFR/GC logs/metrics, jcmd hoặc thread dump theo chính sách an toàn.

**Đừng restart/rotate/xóa file và làm mất chứng cứ trước khi lưu nếu hệ thống vẫn an toàn để thu.** Với dịch vụ đang incident, phục hồi availability có thể ưu tiên; ghi lại giới hạn evidence nếu không thể chờ.

### Bước 3 — Nhận diện JVM tự báo fatal error hay không

- Có hs_err phù hợp? Đọc header/signal/problematic frame và JVM arguments.
- Có core dump tương ứng? Thu metadata và native stack theo quyền.
- Có lỗi JVM fatal được in stderr nhưng không ghi được file?
- Có cấu hình ErrorFile, disk path, container ephemeral FS hoặc permission issues giải thích vì sao mất artifact không?
- Nếu không có: **chưa kết luận external kill**, chuyển kiểm tra OS/runtime evidence.

### Bước 4 — Kiểm tra signal/exit reason theo nguồn supervisor

- Đọc exit status và cách mã hóa: exited(code) hay killed(signal)?
- Nếu 137/9: tìm người gửi SIGKILL, OOM killer, liveness grace timeout, manual operator action hoặc userspace OOM daemon.
- Nếu 143/15: tìm rollout, stop command, shutdown timeout và hook behavior.
- Nếu 134/6, 139/11 hoặc fatal hs_err: điều tra native/JVM fault.
- Nếu 1 hoặc custom status: tìm Java exceptions, System.exit và startup/launcher errors.

**Luôn hỏi:** status có thuộc process Java chính hay chỉ entrypoint shell/wrapper? Wrapper có thể xử lý signal/exit code khác JVM.

### Bước 5 — Điều tra memory theo đúng ranh giới

Nếu nghi OOM:
1. Xác định pod/container/node memory limits và memory time series **trước kill**.
2. Xem kernel OOM lines và cgroup oom_kill delta, nhớ cgroup path đúng.
3. Đối chiếu Java heap usage/Xmx, metaspace, direct memory, native malloc/NMT nếu đã bật, thread count/stacks và page cache.
4. Nếu có Java OOME, đọc **message** để biết vùng tài nguyên thất bại; heap dump chỉ dùng khi tạo được và phù hợp loại lỗi.
5. Kiểm tra tổng process/container RSS và các process khác trong cgroup.
6. Đánh giá memory growth, traffic, batch, native library, deploy và known memory budget.

**Heap used thấp không bác bỏ cgroup OOMKilled**; memory usage cgroup bao gồm phần JVM không quản lý trực tiếp và cache. Cũng không cần tăng Xmx nếu container memory limit cố định và native headroom vốn đã thiếu.

### Bước 6 — Xây timeline và giả thuyết cạnh tranh

Một timeline có thể như sau (giả định):

~~~text
14:10:00 Service A starts, pid=3210, Xmx=1GiB, memory.max=1.5GiB
14:10:05 Memory.current rises after a new batch begins
14:12:20 Memory.current approaches memory.max
14:12:21 Kernel records memcg OOM and victim pid=3210
14:12:21 Container lastState reason=OOMKilled, exit=137
14:12:25 New container starts with a new pid
~~~

Dựa trên **kernel victim + container OOMKilled + đúng cgroup và timeline**, nhánh OS kill mạnh. hs_err không có là phù hợp nhưng không phải yếu tố chứng minh chính.

Một timeline khác:

~~~text
14:10:00 Java process pid=3210 starts
14:12:20 hs_err_pid3210.log begins, header SIGSEGV
14:12:20 Core dump process pid=3210 records SIGSEGV
14:12:21 Supervisor restarts service
~~~

Nhánh JVM/native fatal error mạnh; không suy ra kernel OOM kill chỉ vì process mất sau đó.

### Bước 7 — Phân mức tin cậy và quyết định hành động

Dùng các nhãn:
- **Đã xác nhận cơ chế:** có bằng chứng có nguồn và timestamp đủ mạnh.
- **Khả năng cao:** các nguồn khớp nhưng một nguồn quan trọng thiếu.
- **Chưa đủ bằng chứng:** chỉ exit code, chỉ log cuối hoặc chỉ biểu đồ sau restart.
- **Mâu thuẫn:** dấu vết trái nhau cần kiểm tra PID/clock/instance/aggregation.

Hành động theo cơ chế: native crash → core/hs_err/JNI/JDK; Java OOME → heap/native root; OS OOMKill → cgroup budget/memory trend; liveness kill → probe/health/deadlock/queue/GC; controlled exit → app/supervisor logic. Một thay đổi chỉ được coi thành công khi đã xác minh không lặp lại cùng dấu vết và các SLO, memory/CPU guardrails vẫn đạt.

## 12. Demo Java 17+: đường thoát chủ động, không phải JVM crash

Để học **thứ gì có/không có shutdown hook**, dùng chương trình Java chạy độc lập, không tiêu hao bộ nhớ, không gây segmentation fault, không gửi tín hiệu tới process khác. Chương trình giúp chứng minh: một mã exit nonzero **không cần OS OOM killer**, và Runtime.halt có thể kết thúc **không chạy shutdown hook** nhưng vẫn không phải fatal HotSpot crash.

Tạo file **TerminationModesDemo.java**:

~~~java
public final class TerminationModesDemo {

    public static void main(String[] args) {
        String mode = args.length == 0 ? "normal" : args[0];

        Runtime.getRuntime().addShutdownHook(
                new Thread(
                        () -> System.out.println("HOOK: shutdown"),
                        "demo-shutdown-hook"));

        switch (mode) {
            case "normal" -> System.out.println("MODE: normal");
            case "exit" -> {
                System.out.println("MODE: exit");
                System.exit(7);
            }
            case "halt" -> {
                System.out.println("MODE: halt");
                System.out.flush();
                Runtime.getRuntime().halt(9);
            }
            case "throw" -> {
                System.out.println("MODE: throw");
                throw new IllegalStateException("demo-exception");
            }
            default -> System.out.println("MODE: unknown");
        }
    }
}
~~~

Biên dịch với JDK 17+:

~~~bash
javac TerminationModesDemo.java
~~~

Chạy lần lượt từng mode **trong lab shell**, không phải process đang phục vụ traffic:

~~~bash
java TerminationModesDemo normal
java TerminationModesDemo exit
java TerminationModesDemo halt
java TerminationModesDemo throw
~~~

Với mode **normal**, stdout do chương trình tạo:

~~~text
MODE: normal
HOOK: shutdown
~~~

Với mode **exit**, stdout do chương trình tạo:

~~~text
MODE: exit
HOOK: shutdown
~~~

Giải thích theo mode:

| Mode | Exit mechanism | Exit status thông thường | Shutdown hook | hs_err mặc định? |
| --- | --- | --- | --- | --- |
| normal | main kết thúc, JVM shutdown bình thường | 0 | Có | Không |
| exit | System.exit(7) | 7 | Có | Không |
| halt | Runtime.halt(9), chấm dứt ngay | 9 | Không | Không |
| throw | Uncaught IllegalStateException ở main; JVM exit khi không còn non-daemon thread | Thường khác 0 | Có khi JVM shutdown thông thường | Không |

Mode halt in "MODE: halt" và flush stdout trước khi kết thúc; **không** in “HOOK: shutdown”. Mode throw in “MODE: throw”, sau đó có stack trace trên **stderr** với line numbers thay đổi theo file; thứ tự hiển thị giữa stdout/stderr không bảo đảm. Bảng này mô tả hành vi thông thường của ví dụ trên HotSpot, không thay thế đo exit status thực tế ở shell.

Một bước kiểm tra tùy chọn trên Linux shell:

~~~bash
java TerminationModesDemo exit
printf 'exit status=%s\n' "$?"
~~~

Dòng thứ hai của shell theo chương trình này là:

~~~text
exit status=7
~~~

Điểm học tập:
- Exit 7 là do **chính Java gọi System.exit**, không phải OS kill.
- Exit 9 là do **Runtime.halt(9)** trong Java, không chứng minh có SIGKILL(9). **Mã exit = 9 khác signal number = 9.**
- Exception ở Java không biến thành native hs_err.
- Không có hook trong mode halt là một ví dụ vì sao **thiếu shutdown log không chứng minh SIGKILL**.
- Nếu bạn sửa mode exit thành System.exit(137), hệ thống có thể báo exit code 137 **mà không có kernel OOM kill**; chỉ là minh họa cho tính mơ hồ của code.

**Không chạy demo tạo OOME, SIGSEGV hoặc SIGKILL trên production.** Mục đích là nắm semantics của các đường kết thúc an toàn trước khi phân tích sự cố ngoài đời.

## 13. Tình huống A — OOME xuất hiện nhưng process chưa chết

Ví dụ:
- Thread của ứng dụng log “java.lang.OutOfMemoryError: Java heap space”.
- Tại cùng thời điểm không có kernel OOM victim message; memory.events oom_kill không tăng.
- Process Java vẫn có PID cũ và health endpoint còn phản hồi ở mức suy giảm.
- Không có hs_err, chỉ Java stack trace và một heap dump nếu cờ liên quan được bật.

**Diễn giải:** Có Java-level heap allocation failure; chưa có bằng chứng kernel kill. Phải xem GC/heap live-set, allocations và retention, xác minh thread nào chết và hệ thống có thực sự phục hồi. Việc ứng dụng vẫn alive **không** chứng minh OOME vô hại: state có thể bị lỗi hoặc thiếu capacity.

**Sai lầm:** ghi ticket “OOMKilled” chỉ vì nhìn thấy chữ OutOfMemoryError. Hành động phù hợp là điều tra heap/OOME và health status, không mặc định sửa cgroup limit.

## 14. Tình huống B — Pod OOMKilled trong khi Java heap còn headroom

Ví dụ giả định:
- Pod container memory limit 2 GiB; Xmx 1 GiB.
- Metrics trước crash cho thấy heap used khoảng 700 MiB, nhưng container memory usage tiến gần 2 GiB.
- Kernel log cho thấy memcg OOM victim là Java PID; cgroup oom_kill tăng.
- Kubernetes lastState reason=OOMKilled, exitCode=137.
- Không có hs_err hoặc Java OutOfMemoryError stack trace.

**Diễn giải:** Kernel/cgroup kill có evidence mạnh. Nguyên nhân có thể ở native/direct buffer, metaspace, thread stacks, malloc/JNI, memory-mapped/file cache hoặc process khác trong cgroup. Không nên **tăng Xmx** ngay khi limit tổng không đổi.

**Dữ liệu cần lấy:** cgroup memory.stat, container working set/RSS trend, JVM Native Memory Tracking nếu **đã bật trước**, thread count, direct/mapped buffers, metaspace, native allocator và batch/workload. NMT không bao quát hoàn toàn mọi native third-party allocations hoặc toàn bộ page cache. Nếu chưa bật, không thể tái tạo snapshot NMT của process đã bị kill.

## 15. Tình huống C — JVM fatal error trong thư viện native

Ví dụ:
- hs_err_pid5500.log báo SIGSEGV và problematic frame trong một native library.
- Core dump cùng PID/timestamp có signal SIGSEGV.
- Container exit status thường tương thích 139 nếu signal termination được phản ánh theo quy ước runtime.
- Kernel không có bằng chứng OOM kill; orchestrator reason có thể chỉ là Error.

**Diễn giải:** Native/JVM fatal error rất đáng tin; người điều tra nên xem JNI/agent/native library, quyền truy cập bộ nhớ, versions/ABI và JDK builds. Nếu fault trong libjvm, vẫn cần kiểm tra code và extensions native để phân biệt lỗi trực tiếp với memory corruption trước đó.

**Không kết luận:** “Linux tự giết Java vì hết RAM” chỉ dựa trên signal-related exit code. SIGSEGV và SIGKILL là hai cơ chế khác nhau.

## 16. Tình huống D — Liveness probe dẫn tới SIGKILL, không phải OOM

Ví dụ giả định:
- 09:00:00: liveness probe liên tiếp thất bại trong lúc JVM vẫn chạy nhưng thread pool nghẽn.
- 09:00:05: controller gửi SIGTERM, bắt đầu termination grace period.
- 09:00:35: process vẫn chưa thoát; SIGKILL được gửi.
- Container cuối cùng exit 137; reason không phải OOMKilled.
- cgroup oom_kill không tăng và không có kernel OOM victim message.

**Diễn giải:** Exit 137 tương thích SIGKILL do lifecycle shutdown escalation. Root cause ban đầu có thể là deadlock, GC pause, health probe design, workload, network hoặc native hang, cần điều tra riêng. Chỉ tăng memory limit vì thấy 137 là không có cơ sở.

**Dữ liệu tiếp:** previous logs, kubelet events, probe timings, readiness vs liveness, shutdown hook duration, thread dumps nếu đã thu trước kill, latency/CPU/GC/queues trước sự cố.

## 17. Tình huống E — JVM ghi hs_err rồi bị systemd restart

Ví dụ:
- 11:02:10 HotSpot ghi fatal error log từ PID cũ.
- 11:02:11 process chết với signal fault hoặc abort.
- 11:02:12 systemd nhận termination và restart theo Restart=on-failure.
- 11:02:13 PID mới xuất hiện, service trả lời bình thường.

**Diễn giải:** systemd là **tác nhân restart**, không tự động là tác nhân gây fatal error. Việc thấy “systemd started service” sau crash không chứng minh systemd đã kill JVM trước đó. Cần xem **log ngay trước** restart và artifact của PID cũ.

Đặc biệt, app health hiện tại ổn không xóa được bằng chứng lỗi cũ. Các metrics của PID mới không thay cho trạng thái memory/stack lúc PID cũ crash.

## 18. Những ngoại lệ cần nhớ trước khi chốt nguyên nhân

### 18.1. Wrapper/entrypoint shell có thể biến đổi exit code

Container command có thể là shell script hoặc process supervisor, không phải exec trực tiếp java. Kết quả được runtime báo có thể là exit code của PID 1 wrapper, còn Java child đã chết theo cơ chế khác. Điều tra process tree, init/entrypoint behavior, signal forwarding và logs của wrapper. Không suy mã container ra signal của JVM khi không chắc Java là PID 1 hoặc status được truyền nguyên.

### 18.2. Crash report có thể chỉ được ghi một phần

Fatal signal/low disk/low memory có thể cắt ngắn hs_err hoặc core. Một file có header nhưng thiếu problematic frame/threads vẫn có giá trị chứng cứ; chưa đủ để quy root cause. Không xóa file chỉ vì không parse được, nhưng cũng không gọi báo cáo dở dang là full crash analysis.

### 18.3. SIGTERM/SIGINT và shutdown hooks không có SLA đảm bảo

Ngay cả trong đường shutdown bình thường, hook có thể lỗi, kẹt hoặc bị hết grace period. Các hook được khởi động đồng thời theo JVM semantics; thứ tự giữa **nhiều** hooks không được bảo đảm. Log “begin shutdown” có thể tồn tại mà “end shutdown” vắng mặt. Ngược lại absence của hook log có thể do logging buffer, không đủ để chứng minh SIGKILL.

### 18.4. OS có thể phát tín hiệu vì native fault, không phải chủ ý kill

SIGSEGV/SIGBUS phát sinh bởi fault của chương trình là cơ chế hệ điều hành báo lỗi cho process. HotSpot fatal handler có thể ghi hs_err. Khi phân loại, đừng dùng một câu “do OS gửi signal” để xóa đi sự khác biệt giữa **fault xảy ra trong process** và **kill bên ngoài để thu hồi tài nguyên/quản trị**.

### 18.5. Java OutOfMemoryError và native allocation failure không phải lúc nào cùng lộ trình

Một số native memory allocation failure có thể tạo thông báo fatal JVM error, trong khi một số loại resource exhaustion trả về Java OOME. Message và context mới quyết định hướng điều tra; chỉ nhìn chữ “memory” không đủ. Nếu Java đang dùng container CPU/memory quotas, có thể có tương tác giữa heap sizing tự động, native allocations và memory.max.

### 18.6. Core dumps, hs_err và heap dumps trả lời câu hỏi khác nhau

| Artifact | Ghi gì? | Khi nào hữu ích nhất? | Không phải điều gì? |
| --- | --- | --- | --- |
| hs_err | Snapshot fatal state của HotSpot: signal, threads, VM/native context | Native/JVM crash, fatal VM error | Không phải Java heap dump |
| Core dump | Snapshot process memory/registers tại crash theo OS/core policy | Native stack, library versions, memory corruption | Không đảm bảo có khi SIGKILL/OOMKilled |
| Heap dump (.hprof) | Java heap object graph tại thời điểm thu | Java heap leak/retention, một số OOME | Không đại diện mọi native memory hoặc lý do signal |
| GC log/JFR | Runtime timeline/GC/JIT/events đã được ghi | Lịch sử trước lỗi nếu có dữ liệu | Không phải hệ thống lưu vĩnh viễn khi bị SIGKILL |
| Kernel log/cgroup counters | OS memory/signal/resource evidence | OOM victim/pressure/limits | Không chỉ ra object Java nào giữ memory |
| Orchestrator status/events | Container lifecycle/reason/exit code | OOMKilled, Evicted, probe/rollout | Không tự phân tích JNI/JVM root cause |

Một file .jfr từ continuous recording có thể không được dump/flush thành artifact trước SIGKILL. **Đặt dumponexit=true không bảo đảm JFR tồn tại sau SIGKILL.** Muốn giữ lịch sử trước kill, cần thiết kế dump/metrics ngoài process, quyền lưu và retention phù hợp.

## 19. Chuẩn bị trước sự cố: khả năng điều tra thay vì chờ crash

### 19.1. Startup flags theo rủi ro đã cân nhắc

Các ví dụ chỉ dành cho HotSpot/JDK phù hợp và môi trường có quyền ghi:

~~~bash
java \
  -XX:ErrorFile=/var/log/myapp/hs_err_pid%p.log \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/var/log/myapp \
  -Xlog:gc*:file=/var/log/myapp/gc.log:time,uptime,level,tags:filecount=5,filesize=50M \
  -jar app.jar
~~~

Lưu ý:
- /var/log/myapp phải tồn tại/ghi được từ filesystem của JVM đích. Ở container phải hiểu volume mount, ownership và ephemeral storage.
- %p trong HotSpot ErrorFile được thay bằng PID theo hỗ trợ của flag; dùng tên gắn instance khi lưu tập trung để tránh đụng file.
- Heap dump có thể rất lớn, có thể làm đầy storage và tiết lộ secrets. Nếu rủi ro không chấp nhận được, không bật bừa bãi.
- File GC logs có rotate; cần policy lưu đủ đoạn trước sự cố, không để ghi log khiến disk full.
- Tùy chọn HeapDumpOnOOME **không tạo crash artifact khi OS SIGKILL**. ErrorFile dành cho HotSpot fatal reports, không cho mọi Java exceptions.

Không thêm -XX:+CrashOnOutOfMemoryError để “debug OOM” trên production nếu chưa có chính sách/phân tích rủi ro rõ ràng; flag thay đổi chính đường kết thúc và có thể khiến ứng dụng chết ngay.

### 19.2. Telemetry ngoài tiến trình

Để phân biệt JVM crash với OS kill khi process đã biến mất, cần nguồn không chết cùng JVM:

- Container lastState/exit reason, restart counters, pod/container IDs.
- cgroup memory.current/max/events/pressure time series từ exporter/agent.
- Node kernel logs, kubelet/systemd/systemd-oomd logs và event stream.
- JVM heap/nonheap/direct/thread/GC metrics xuất ra monitoring, gắn instance labels.
- CPU throttling, native RSS, process memory, file descriptors và container page cache.
- Deployment, rollout, termination, liveness/readiness events.
- Centralized stdout/stderr, fatal error logs hoặc artifact collector lưu ngoài filesystem ephemeral.

Đặc biệt quan trọng: metrics cần **timestamp, process/container identity và tần suất thu đủ cao**. Một biểu đồ “memory trung bình 5 phút” có thể bỏ lỡ spike ngắn trước OOM kill.

### 19.3. Native Memory Tracking và công cụ hậu kiểm

Nếu dự đoán native memory pressure, có thể cân nhắc bật NMT trước khi chạy process bằng JVM flags phù hợp, sau đó dùng jcmd VM.native_memory khi process còn sống; tính năng có overhead và không bao quát tất cả allocations bên ngoài HotSpot. Khi process bị SIGKILL, jcmd không còn attach được. **Không có NMT snapshot trước crash thì không thể dựng lại snapshot đó từ PID mới.**

Với native crash: core dump, symbols, loaded libraries, hs_err và JVM/JNI agent versions giúp điều tra. Không cố tải bản core lớn hoặc chạy debugger trên production nếu không có quyền/chiến lược bảo mật.

## 20. Cách viết báo cáo không vượt quá bằng chứng

Một báo cáo tốt luôn phân biệt **đã quan sát** với **giả thuyết**. Ví dụ:

**Chưa đủ bằng chứng:**
> Container có exit code 137 lúc 15:04 UTC. Hiện chưa có lastState reason hoặc kernel/cgroup logs; chưa thể kết luận OOMKilled. Cần lấy runtime termination reason, probe/rollout events và memory events đúng cgroup.

**Có cơ sở mạnh cho OS OOM kill:**
> Container X báo lastState reason=OOMKilled, exitCode=137 lúc 15:04 UTC; kernel log xác nhận memcg OOM victim là Java PID 3451 trong cùng cgroup và memory.events oom_kill tăng. Có thể xác nhận cơ chế kết thúc là kernel memory cgroup OOM kill. Nguyên nhân tăng memory cụ thể vẫn cần điều tra heap/native/cache/workload.

**Có cơ sở mạnh cho JVM/native fatal error:**
> hs_err_pid3451.log có header fatal SIGSEGV và problematic frame ở libnative.so, trùng PID/timestamp với core dump. Đây là JVM/native fatal crash; chưa chứng minh libnative.so là nguyên nhân ban đầu nếu có memory corruption từ trước. Không có evidence OOM killer trong cửa sổ đã kiểm tra.

**Không nên viết:**
> “Exit 137 => Java bị hết heap; tăng -Xmx.”

Câu này nhầm **trạng thái kết thúc**, **nguồn memory** và **hành động khắc phục**. Tăng heap dưới một container limit cố định thậm chí có thể làm native headroom giảm và khiến OOMKill thường xuyên hơn.

## 21. Runbook rút gọn khi nhận báo động “JVM chết”

~~~text
[1] Đúng process đã chết?
    |-- Không: điều tra hang/unresponsive/dependency trước
    '-- Có: ghi PID/containerID/podUID/node/start-end UTC
          |
          v
[2] Có hs_err của đúng PID/thời điểm?
    |-- Có: điều tra JVM/native fatal error + core/agents/JDK
    '-- Không hoặc thiếu: chưa kết luận, tiếp tục OS evidence
          |
          v
[3] Exit là normal, explicit code hay signal?
    |-- exit code custom: xem Java exception/System.exit/wrapper
    |-- SIGTERM: xem deploy/probe/service manager/stop
    |-- SIGKILL: xem kernel OOM, cgroup, controller grace, operator
    '-- SIGSEGV/SIGABRT/SIGBUS: xem native/JVM fault/core
          |
          v
[4] OOM evidence?
    |-- reason OOMKilled + đúng kernel/cgroup/time:
    |      xác nhận kernel/cgroup kill, tìm nguồn memory
    |-- Java OutOfMemoryError nhưng không có OS kill:
    |      điều tra JVM exception/resource area
    '-- Chỉ exit 137:
           chưa đủ, thu runtime/kubelet/kernel records
          |
          v
[5] Ghép bằng chứng, phản chứng, scope và quyết định sửa
~~~

Nhánh trên là hướng suy luận, **không phải thứ tự cứng**. Nếu có status OOMKilled rất rõ từ orchestrator, nên thu kernel/cgroup logs ngay vì dễ hết retention, rồi quay lại xem hs_err/Java logs. Nếu chỉ có hs_err nhưng kernel cũng OOM kill về sau, phải dựng timeline xem cái nào xảy ra trước và PID nào bị kill.

## 22. Checklist điều tra và bàn giao

- [ ] Tôi xác nhận process thực sự kết thúc, không chỉ app bị treo.
- [ ] Tôi biết đúng PID, instance, container ID/pod UID, node, start/end time và JVM version.
- [ ] Tôi phân biệt Java exception/OOME, System.exit, Runtime.halt, JVM fatal error, SIGTERM/SIGKILL và OOM killer.
- [ ] Tôi đã tìm hs_err và kiểm tra path/permissions/timestamp; không suy “vắng file = OS kill”.
- [ ] Nếu có hs_err, tôi đọc fatal header, signal, problematic frame, native/JVM frames và VM arguments.
- [ ] Tôi đã lấy process/container status, không chỉ một exit code tổng quát.
- [ ] Với 137, tôi tìm evidence SIGKILL và sender/reason; không tự động coi là OOMKilled.
- [ ] Với OOMKilled, tôi lấy kernel/cgroup memory events và memory trend đúng phạm vi.
- [ ] Tôi không nhầm Java heap OutOfMemoryError với container OOMKilled; có xét native/direct/cache/thread memory.
- [ ] Tôi kiểm tra probe, rollout, grace period, watchdog, systemd-oomd và node eviction.
- [ ] Tôi phân biệt core dump, heap dump, hs_err, JFR/GC logs và kernel evidence.
- [ ] Tôi không dùng PID mới hoặc memory snapshot sau restart làm evidence cho process cũ.
- [ ] Tôi so mốc thời gian theo UTC, hiểu clock skew và log retention.
- [ ] Tôi có ít nhất một giả thuyết cạnh tranh và một phép kiểm chứng có thể bác bỏ giả thuyết chính.
- [ ] Tôi bảo vệ dữ liệu trong hs_err/core/heap dumps và có chính sách lưu, xóa, phân quyền.
- [ ] Kết luận nêu **cơ chế termination**, **root cause giả thuyết**, **độ tin cậy** và **việc cần đo tiếp**.

## 23. Kết luận

Điểm phân biệt quan trọng nhất:

**JVM tự ghi fatal error** nghĩa là cơ chế reporting của VM có cơ hội chạy và có thể tạo **hs_err** (thường kèm signal/native/VM context). **Hệ điều hành hoặc bộ điều phối chấm dứt tiến trình** có thể dùng SIGTERM/SIGKILL; với SIGKILL, JVM không kịp chạy shutdown hooks hoặc tạo những artifact theo quy trình bình thường.

Nhưng thực tế có thêm các nhánh: Java exception, OutOfMemoryError, System.exit, Runtime.halt, native SIGSEGV, kernel/cgroup OOM kill, systemd-oomd, kubelet evictions, liveness restarts và wrapper statuses. Vì vậy không được lấy một dấu vết (exit 137, vắng hs_err, một dòng OOME hay pod restart) làm toàn bộ kết luận.

Một quá trình điều tra tốt đi theo chuỗi:

**Xác minh process/instance → thu hs_err/Java logs → đối chiếu exit/signal/reason → đọc kernel/cgroup/orchestrator timeline → phân biệt cơ chế kết thúc với nguyên nhân sâu → sửa có kiểm chứng.**

### Tài liệu tham khảo

- Oracle JDK 21, Java launcher/HotSpot flags (-XX:ErrorFile, HeapDumpOnOutOfMemoryError...): https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle JDK 21, jcmd (VM flags, JFR, native memory commands khi được hỗ trợ): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java 21, Troubleshooting Guide: https://docs.oracle.com/en/java/javase/21/troubleshoot/
- Linux kernel cgroup v2 (memory.events, memory.events.local, memory.max): https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html
- Linux signal(7): https://man7.org/linux/man-pages/man7/signal.7.html
- Kubernetes, Node-pressure eviction: https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/
- Kubernetes, Debug Running Pods: https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/
