# 20.7 Vai trò của jhsdb jstack, jmap, jinfo và clhsdb đối với core hoặc JVM

## 1. Khi JVM đã crash, dùng công cụ nào để nhìn lại trạng thái?

Một dịch vụ Java bất ngờ dừng với `SIGSEGV`/`EXCEPTION_ACCESS_VIOLATION`, có thể còn file `hs_err_pid*.log` và một **core dump**. Lúc đó không còn PID đang chạy để hỏi bằng `jcmd`; file core chứa snapshot bộ nhớ và thread state tại thời điểm hệ điều hành tạo dump. Muốn đọc các cấu trúc HotSpot trong snapshot ấy, JDK cung cấp **`jhsdb`**, công cụ dùng **HotSpot Serviceability Agent (SA)**.

Một tình huống khác: tiến trình còn sống nhưng bị treo, `jcmd`/attach thông thường không phản hồi. `jhsdb` cũng có chế độ attach bằng `--pid`, nhưng **đây là lựa chọn can thiệp mạnh và rủi ro cao**, không nên coi như bản thay thế “an toàn hơn” cho lệnh `jstack`/`jcmd`. Tài liệu Oracle JDK 21 cảnh báo attach SA vào live process có thể làm tiến trình ngừng tiến triển và có khả năng crash khi detach.

Bài này tập trung phân biệt rõ:

- **`jhsdb jstack`:** lấy stack và một số thông tin lock của Java threads, có thể xem mixed Java/native frames khi nền tảng cho phép.
- **`jhsdb jmap`:** xem Java heap, object histogram, class loader statistics hoặc xuất HPROF từ snapshot.
- **`jhsdb jinfo`:** lấy VM flags và Java system properties từ JVM/core.
- **`jhsdb clhsdb`:** mở phiên dòng lệnh tương tác để đi sâu vào thread, object, heap, flags và cấu trúc VM.
- **`--pid` so với cặp `--exe` + `--core`:** chọn đúng live JVM hoặc core offline; không nhầm executable với file `.jar`.

Mục tiêu là **chọn ít rủi ro nhất nhưng đủ thông tin**, đọc đúng điều snapshot có thể chứng minh, và biết khi nào phải chuyển sang native debugger hoặc điều tra thêm.

## 2. Serviceability Agent nhìn thấy gì?

**Serviceability Agent (SA)** nằm trong JDK HotSpot tooling. Nó có hiểu biết về layout nội bộ của JVM (Java threads, Java heap, class metadata, code cache, VM structures), dùng thông tin của tiến trình hoặc core để diễn giải thành dữ liệu có nghĩa với Java.

Hình dung ba tầng bằng chứng:

~~~text
Ứng dụng Java / HotSpot VM
          |
          | Crash hoặc OS ghi snapshot
          v
   Core dump (bộ nhớ + trạng thái thread/mappings)
          |
          | jhsdb + Serviceability Agent + đúng JVM binary/libs
          v
   Java threads / heap / VM flags / class metadata
          |
          +--> jhsdb jstack
          +--> jhsdb jmap
          +--> jhsdb jinfo
          +--> jhsdb clhsdb (tương tác)
~~~

SA khác với native debugger như `gdb`/`lldb`/WinDbg ở chỗ biết **cấu trúc HotSpot** để hiển thị Java stack/object/VM metadata; native debugger lại mạnh về instruction pointer, native registers, machine stack, shared library symbols và tín hiệu crash. Hai nhóm công cụ **bổ trợ nhau**, không thay thế nhau.

**Giới hạn quan trọng:**

1. `jhsdb` là công cụ riêng cho **HotSpot** và có những phần được tài liệu Oracle đánh dấu **experimental/unsupported**; hành vi phụ thuộc JDK version, OS, architecture, collector và mức độ toàn vẹn core.
2. Nếu core **thiếu trang nhớ**, bị truncate hoặc không có đúng thư viện, một số truy vấn có thể không trả được thông tin, báo lỗi symbol hoặc chỉ thấy một phần.
3. Core chỉ chứa **trạng thái tại thời điểm chụp**. Nó không có timeline GC, lock contention, request latency hay diễn biến heap trước đó trừ khi bằng chứng khác cũng đã được ghi.
4. Object histogram từ core là **đếm object trong snapshot có thể đọc được**, không tự chứng minh memory leak hoặc object nào “làm JVM crash”.
5. SA có thể ảnh hưởng nghiêm trọng tới một JVM **còn chạy** khi dùng `--pid`; phải có quyền, kế hoạch dừng/khôi phục và đánh giá tác động.

## 3. Phân biệt PID, core, HPROF và hs_err

| Bằng chứng | Tồn tại khi nào? | Có thể làm gì? | Không nên nhầm |
| --- | --- | --- | --- |
| **Live PID** | JVM vẫn đang chạy; có process ID | Dùng `jcmd`/`jstack` thường; SA `--pid` chỉ khi thực sự cần và chấp nhận rủi ro | PID cũ sau crash có thể đã bị OS tái sử dụng |
| **Core dump** | OS/collector tạo snapshot khi crash hoặc có yêu cầu tạo dump | `jhsdb --exe ... --core ...`, native debugger | Không phải Java heap dump; có thể gồm rất nhiều dữ liệu nhạy cảm |
| **`hs_err_pid*.log`** | HotSpot fatal error handler có thể tạo khi VM gặp fatal error | Đọc crash signal, problematic frame, thread, native libs, VM flags, heap summary | Chỉ là file text, không thể thay `--core` của SA |
| **`.hprof` heap dump** | JVM/tool đã xuất heap dump | MAT, VisualVM, heap dump parser để phân tích object graph/retained size | Không phải OS core; không đưa file HPROF vào `jhsdb --core` |
| **`.jfr` recording** | JFR ghi trước crash hoặc được dump trước đó | JMC/JFR để phân tích events/timeline | Không có full address space như core |
| **Native stack/symbol files** | Native debugger và build artifacts cung cấp | Đối chiếu machine frames, symbol, shared objects | Không tự thay thế metadata nội bộ JVM |

**Không phải cứ có `hs_err_pid` là có core**; chính sách kernel/OS, `ulimit`, `systemd-coredump`, container security và dung lượng đĩa quyết định có tạo/giữ core hay không. Ngược lại, core có thể được tạo khi JVM vẫn còn sống bằng một cơ chế OS phù hợp (chẳng hạn `gcore`), nhưng bản thân thao tác có ảnh hưởng tài nguyên và thường dừng/ngắt tiến trình trong lúc chụp; chỉ thực hiện theo quy trình incident được cho phép.

### Ba điều cần xác minh trước khi mở core

- File đúng thuộc **PID, thời điểm, host/container và bản JDK** nào? Xem `hs_err`, core metadata và release metadata của deployment.
- Có **đúng Java launcher executable và JDK runtime/shared libraries** tại thời điểm crash không? Nếu JVM được tạo qua JNI Invocation API, executable có thể là **launcher tùy biến**, không phải `$JAVA_HOME/bin/java`.
- Core có đầy đủ và người phân tích có quyền truy cập nó không? Core có thể chứa **token, mật khẩu, khóa và dữ liệu người dùng trong memory**, phải hạn chế sao chép/chia sẻ, kiểm soát retention và xóa an toàn sau điều tra.

## 4. Cú pháp jhsdb: sống hay hậu kiểm là hai chế độ loại trừ nhau

Xem lệnh được cài trên JDK hiện tại:

~~~bash
jhsdb --help
jhsdb jstack --help
jhsdb jmap --help
jhsdb jinfo --help
jhsdb clhsdb --help
~~~

Theo JDK 21 và bản HotSpot phù hợp, hai mẫu chính:

~~~bash
# Core trên đĩa: phải có cả --exe và --core.
jhsdb jstack --exe /opt/jdk/bin/java --core /var/crash/core.12345

# Live process: CHỈ dùng khi được phép và chấp nhận rủi ro của SA.
jhsdb jstack --pid 12345
~~~

`--exe` và `--core` **đi thành cặp** trong postmortem mode; `--pid` không dùng chung với `--core`. `--exe` là **đường dẫn native executable đã tạo VM/core**, không phải `service.jar` hay class tên `Main`. `--core` là **OS core dump**, không phải `heap.hprof`.

Các chế độ `jstack`, `jmap`, `jinfo` là **subcommand của `jhsdb`**, khác với các executable truyền thống có tên trùng/na ná:

- `jstack <PID>` thường dùng attach/serviceability interface cho JVM sống.
- `jhsdb jstack --core ... --exe ...` dùng SA đọc **offline core**, hữu ích khi process đã chết hoặc không có kênh attach bình thường.
- `jmap -histo <PID>` và `jcmd <PID> GC.class_histogram` thuộc workflow live; **`jhsdb jmap --histo --core ... --exe ...`** là workflow postmortem có cú pháp khác.
- `jinfo <PID>` truy xuất live VM; **`jhsdb jinfo --flags/--sysprops --core ... --exe ...`** truy xuất dữ liệu có trong snapshot.

Trên JDK 21, `jhsdb debugd` và `--connect` có thể hỗ trợ remote SA, nhưng **đường remote này đã bị đánh dấu deprecated** trong tài liệu và có thêm bề mặt tấn công/quản trị. Bài thực hành ưu tiên **phân tích core cục bộ trong môi trường cách ly**, không khuyên dựng debugd mở công khai.

## 5. `jhsdb jstack` — thread state, Java frames và mixed stack

### Cách gọi trên core

~~~bash
jhsdb jstack --exe /opt/jdk/bin/java --core /var/crash/core.12345
jhsdb jstack --locks --exe /opt/jdk/bin/java --core /var/crash/core.12345
jhsdb jstack --mixed --exe /opt/jdk/bin/java --core /var/crash/core.12345
~~~

- **Không có option bổ sung:** in stack của các Java threads mà SA đọc được tại thời điểm snapshot.
- **`--locks`:** mở rộng thông tin một số `java.util.concurrent` locks/ownable synchronizers mà công cụ có thể suy ra.
- **`--mixed`:** cố gắng kết hợp Java frames và native frames **nếu platform/debug information cho phép**. Không hứa luôn symbolicate đầy đủ C/C++ hoặc thấy cả native async stack.

Đọc một stack trace theo ba chiều:

1. **Thread nào?** Tên thread, Java state, native thread identifier (nếu hiển thị), và có phải thread crash nêu trong `hs_err` hay không.
2. **Đang làm gì?** Java frame nào ở gần đỉnh, có block/wait/park, gọi JNI, GC/runtime hay một đoạn code nghiệp vụ?
3. **Đang đợi ai?** Nếu monitor contention/deadlock, xem lock ownership và các threads liên quan. Một snapshot chỉ cho biết **trạng thái lúc chụp**, chưa cho biết chờ bao lâu hoặc luôn bị deadlock.

Ví dụ **minh họa**, không phải stdout chuẩn của mọi HotSpot version:

~~~text
"sa-lock-contender" ... java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.Worker.run(Worker.java:42)
    - waiting to lock <0x...> (a java.lang.Object)
"sa-lock-owner" ... java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    ...
~~~

Thấy `BLOCKED` là **một dấu hiệu contention tại snapshot**; không tự kết luận deadlock hay thủ phạm crash. Trường hợp `hs_err` chỉ ra problematic frame nằm trong `libnative.so`, dùng thêm **native debugger với chính core và debug symbols** để thấy tín hiệu, registers và C stack; SA không thay tất cả thông tin đó.

### Lựa chọn an toàn hơn khi JVM còn sống

Trước khi cân nhắc SA, có thể thử (với quyền attach và JVM phản hồi):

~~~bash
jcmd <PID> Thread.print -l
jstack -l <PID>
~~~

Hai lệnh trên dùng workflow live quen thuộc; `jstack -l` không phải cùng cấu hình với `jhsdb jstack --locks` dù cùng mục đích xem locks. Nếu JVM không phản hồi, trước tiên kiểm tra trạng thái process bằng OS, quyền attach, PID namespace và mức độ ảnh hưởng tới production; **đừng chuyển máy móc sang `jhsdb --pid` trên service quan trọng**. Tài liệu Oracle cảnh báo SA attach live có thể khiến process bị treo và có thể crash khi detach. Nên phân tích **core/snapshot offline** khi đã có, hoặc chỉ thử `--pid` trên instance có thể hy sinh.

## 6. `jhsdb jmap` — heap summary, object histogram và class loaders

### Những câu hỏi cần trả lời

- Heap tại thời điểm crash dùng khoảng bao nhiêu, collector/region/cấu hình nào?
- Loại object nào chiếm nhiều instances và shallow bytes?
- Class loader nào còn tồn tại, có class loading/churn đáng nghi?
- Có thể lấy một **HPROF** từ core để kiểm tra object graph/offline hay không?

Các lệnh từ **core**:

~~~bash
jhsdb jmap --heap --exe /opt/jdk/bin/java --core /var/crash/core.12345
jhsdb jmap --histo --exe /opt/jdk/bin/java --core /var/crash/core.12345
jhsdb jmap --clstats --exe /opt/jdk/bin/java --core /var/crash/core.12345
jhsdb jmap --binaryheap --dumpfile recovered.hprof \
  --exe /opt/jdk/bin/java --core /var/crash/core.12345
~~~

Ý nghĩa:

| Chế độ | Dữ liệu chính | Lưu ý |
| --- | --- | --- |
| `--heap` | Heap configuration/summary, usage theo collector/cấu trúc VM có thể đọc | Không đồng nghĩa heap dump chứa toàn bộ object graph |
| `--histo` | Histogram các class/object: instance count và bytes | Thường là shallow size, không phải retained size; snapshot có thể không hoàn chỉnh |
| `--clstats` | Class loader statistics/metadata | Dấu hiệu để tiếp tục điều tra class loader leak, không đủ kết luận |
| `--binaryheap --dumpfile file.hprof` | Ghi heap dump HPROF từ snapshot, khi SA hỗ trợ | Rất tốn dung lượng, có dữ liệu nhạy cảm, có thể thất bại nếu core thiếu vùng |

**Không dùng `--dumpfile` đơn lẻ**: theo help của JDK, tùy chọn này chỉ hợp lệ với `--binaryheap`. Có thể có `--gz 1..9` để nén dump theo JDK hỗ trợ; không dùng khi chưa kiểm tra `jhsdb jmap --help`.

Một histogram hiển thị rất nhiều `byte[]` hoặc `String` **chưa** chứng minh Java memory leak. Cần so retained paths/GC roots qua HPROF (nếu xuất được) và xem workload; một snapshot tại crash có thể chứa nhiều dữ liệu đang sống hợp lệ. Nếu JVM crash giữa quá trình cập nhật heap/GC, một số dữ liệu có thể không thể decode; ghi rõ giới hạn đó thay vì “chữa” bằng cách đổi collector khi chưa đủ bằng chứng.

Nếu chỉ cần thông tin heap của JVM **đang khỏe**, thường dùng `jcmd <PID> GC.heap_info` hoặc các công cụ live thích hợp trước; tạo `GC.heap_dump` có tác động CPU/memory/disk đáng kể, cần quyền và kế hoạch tải.

## 7. `jhsdb jinfo` — flags và system properties của VM tại crash

Từ core:

~~~bash
jhsdb jinfo --flags --exe /opt/jdk/bin/java --core /var/crash/core.12345
jhsdb jinfo --sysprops --exe /opt/jdk/bin/java --core /var/crash/core.12345
# Không có --flags/--sysprops: in cả hai loại theo JDK help.
jhsdb jinfo --exe /opt/jdk/bin/java --core /var/crash/core.12345
~~~

**Dùng khi:** cần biết `-Xmx`/`-Xms`, collector, các `-XX` flags, system properties, runtime configuration hoặc dữ liệu classpath/property có liên quan tới crash. Đây là đầu mối để đối chiếu với `hs_err_pid*.log`, deployment manifest/container startup command và thay đổi cấu hình gần đây.

**Không được suy diễn:**

- System properties không giống toàn bộ **environment variables**, startup shell script, command line của OS hay configuration từ remote service.
- Không phải mọi thuộc tính đọc từ core đều đầy đủ nếu VM crash ở trạng thái chưa ổn định/đọc core thiếu dữ liệu.
- Có khả năng lộ secrets trong `-D...` hoặc properties; **lọc/redact** khi đưa log vào ticket và không gửi core cho bên không được phép.
- `jhsdb jinfo` chủ yếu **đọc** trạng thái; đừng nhầm với việc đổi live flags bằng một số tiện ích `jinfo` truyền thống.

Khi JVM còn sống và có kênh attach an toàn, thường bắt đầu bằng:

~~~bash
jcmd <PID> VM.flags
jcmd <PID> VM.command_line
jcmd <PID> VM.system_properties
~~~

Các lệnh này phản ánh JVM **hiện thời**; `jhsdb jinfo --core` phản ánh VM ở **thời điểm snapshot**. Điều đó rất quan trọng nếu deployment đã restart sang cấu hình khác sau crash.

## 8. `jhsdb clhsdb` — công cụ SA tương tác khi lệnh một lần chưa đủ

`clhsdb` (command-line HotSpot debugger) mở môi trường tương tác để khám phá những cấu trúc SA biết. Nó **không phải shell của OS** và các lệnh bên trong (như `jstack`, `jhisto`) không phải executable độc lập bạn chạy trực tiếp bằng Bash.

Mở **core offline**:

~~~bash
jhsdb clhsdb --exe /opt/jdk/bin/java --core /var/crash/core.12345
~~~

Các lệnh thường dùng **sau khi đã vào prompt `clhsdb>`**, chỉ là phiên minh họa:

~~~text
clhsdb> help
clhsdb> threads
clhsdb> jstack
clhsdb> where -a
clhsdb> jhisto
clhsdb> flags
clhsdb> sysprops
clhsdb> pmap
clhsdb> quit
~~~

| Lệnh bên trong CLHSDB | Mục đích |
| --- | --- |
| `help` / `help jstack` | Xem những lệnh thực sự hỗ trợ và tham số theo bản JDK |
| `threads` | Liệt kê Java threads được SA nhận diện |
| `jstack`, `where -a` | Xem Java stacks từ toàn bộ/một nhóm thread theo cú pháp CLI |
| `pstack` (khi có) | Xem mixed native/Java stacks |
| `jhisto` | Histogram object heap được SA đọc |
| `flags`, `sysprops` | VM flags và Java system properties |
| `pmap` | Tổng quan mappings tương tự kiểu `pmap` từ SA |
| `inspect <address>`, `print <expression>` | Đọc object/VM structure khi có địa chỉ và đúng kiểu |
| `quit` | Thoát session SA |

**Lệnh CLHSDB có thể thay đổi theo JDK**, nhất là lệnh nội bộ/địa chỉ struct. Dùng `help` trước khi chạy truy vấn lạ; không copy nguyên kết quả pointer/address từ một build khác để giải mã. Khi muốn đi vào `inspect` hoặc `printas`, phải xác định pointer thuộc loại gì, bộ nhớ còn nguyên vẹn không; thao tác sai dễ gây lỗi công cụ, không chứng minh core “hỏng”.

### Khi nào chọn CLHSDB thay vì ba lệnh tách sẵn?

- Cần **đi theo một thread cụ thể**, sau đó truy vùng VM/object liên quan.
- Muốn kiểm tra **một địa chỉ/metadata** trong hotspot internals do crash gợi ý.
- Cần thử nhiều góc nhìn `threads → jstack → flags → jhisto` mà không chạy nhiều lệnh SA riêng.
- Đang làm postmortem sâu cùng native debugger khi stack hoặc heap summary chưa đủ.

Nếu chỉ cần stack/heap/flags đơn giản, ưu tiên lệnh riêng `jhsdb jstack`/`jmap`/`jinfo` và lưu output dễ review, thay vì bật CLHSDB không mục đích. Với core rất lớn, một số lệnh như `jhisto` hoặc `dumpheap` có thể quét dữ liệu lớn; cần cân nhắc RAM/đĩa.

## 9. Quy trình hậu kiểm chuẩn khi có core

Đây là **workflow xử lý chứng cứ**, không phải yêu cầu cố tình crash ứng dụng. Ví dụ dành cho Linux/HotSpot JDK 17+.

### Bước 1 — Thu thập và bảo quản artifacts

Lưu cùng incident (với quyền truy cập hạn chế):

- Thời gian crash, PID/container ID, release/commit, OS/architecture, version chính xác của `java -version`.
- `hs_err_pid*.log` nếu có, stderr, service logs, JFR recording còn lại và deployment flags.
- **Core dump** hoặc thông tin từ trình quản lý dump OS; nếu dùng systemd, `coredumpctl list`/`coredumpctl info` có thể chỉ ra core bị lưu/rotate ở đâu.
- Bản **JDK executable và shared libraries** tương thích bản JVM khi crash; có thể cần file debug symbols tương ứng.

Kiểm tra kích thước và giới hạn lưu trữ trước khi copy. Core và HPROF có thể lớn hàng GiB, chứa secrets và PII; nên để trong môi trường forensic cách ly. Không tự restart service chỉ để ép crash với `kill -ABRT` trong production; không dùng lab để tạo core khi không được phép.

### Bước 2 — Đọc `hs_err_pid*.log` trước

Tìm:

- Fatal signal / error, **problematic frame** (JVM compiler, GC, JNI/native library hay JIT code).
- **Current thread** và frame tại thời điểm lỗi.
- VM/GC flags, Java/OS version và loaded libraries.
- Phần **native memory**/heap và trạng thái process nếu file còn ghi được.

`hs_err` không đủ cho mọi phân tích nhưng giúp chọn hướng: native segfault cần native stack/library symbols; OOM/native memory cần OS/cgroup/NMT/JFR; deadlock/hang cần thread stacks và locks. Một số crash xảy ra trước khi tạo xong `hs_err` nên dữ liệu có thể thiếu.

### Bước 3 — Dùng JDK/OS khớp với core

Trên máy phân tích, bảo đảm có executable **đúng bản đã tạo core** và các libraries liên quan. Tài liệu OpenJDK về “transported core dumps” nhấn mạnh nhiều core **không chứa code/text pages**, SA phải lấy chúng từ executable và shared objects. Vì vậy **đổi JDK khác phiên bản/build** hoặc thay OS libraries có thể gây lỗi symbol/layout, kết quả không đáng tin.

Khi chuyển core từ container/host khác, kiểm tra:

- CPU architecture (x86_64/aarch64), OS/distro/libc, pointer width và endianness tương thích.
- JDK vendor/build, VM flavor (`server`), `libjvm.so` và hệ thư viện JNI.
- Đường dẫn và nơi nạp libraries; cần chuẩn bị một **analysis image** tái tạo đúng môi trường thay vì giả định JDK mới nhất luôn mở được mọi core.

Ví dụ đường dẫn trong các lệnh sau là minh họa, **không phải file có sẵn trên máy**.

### Bước 4 — Hỏi các câu rẻ trước, sâu sau

~~~bash
jhsdb jinfo --flags --exe /opt/jdk/bin/java --core /var/crash/core.12345
jhsdb jstack --exe /opt/jdk/bin/java --core /var/crash/core.12345
jhsdb jmap --heap --exe /opt/jdk/bin/java --core /var/crash/core.12345
~~~

Nếu có dấu hiệu:

- **Crash trong JNI/native:** thử `jhsdb jstack --mixed`, đồng thời mở core bằng native debugger và matched symbols.
- **Nghi Java heap pressure:** thử `jhsdb jmap --histo`, chỉ export HPROF khi cần object graph/retained references và core đủ bộ nhớ.
- **Nghi classloader/metaspace:** dùng `jhsdb jmap --clstats` và CLHSDB để quan sát class metadata.
- **Thread contention/deadlock:** dùng `jhsdb jstack --locks` hoặc CLHSDB `threads`/`where -a`, đối chiếu lock owner và `hs_err`.

### Bước 5 — Kiểm tra giả thuyết, tránh kết luận quá mức

Cụ thể hóa thành phát hiện có căn cứ: “core tại thời điểm X cho thấy thread T bị BLOCKED trên monitor M, owner O đang ở stack F” hoặc “core có rất nhiều instance class C, cần heap dump/retained path để đánh giá”. Không khẳng định “đây là nguyên nhân duy nhất của crash” khi chưa đối chiếu problematic frame, timeline, GC, OS và lỗi trước đó.

Việc cần sửa phải gắn với **bằng chứng tại crash** và **thử nghiệm tái hiện**. Một core không cho biết tốc độ tăng leak, số request đã bị ảnh hưởng hay trạng thái tương lai của thread.

## 10. Lab Java 17+: tạo JVM có thread WAITING và BLOCKED để hiểu snapshot

Lab này **không tạo crash và không thu core**; nó tạo một JVM sống đủ lâu để người học thử **các công cụ live ít rủi ro** như `jcmd Thread.print`. Mục tiêu là biết stack nào sẽ xuất hiện trong một snapshot, rồi hiểu vì sao `jhsdb jstack` đọc core mang ý nghĩa **trạng thái tại thời điểm chụp**. **Không dùng `jhsdb --pid` vào lab** trừ khi cố tình thử SA attach trong môi trường cô lập và chấp nhận process có thể dừng/crash.

Tạo file **`SaSnapshotLab.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class SaSnapshotLab {
    private static final Object LOCK = new Object();
    private static final CountDownLatch OWNER_READY = new CountDownLatch(1);
    private static final CountDownLatch RELEASE = new CountDownLatch(1);

    private static void ownerTask() {
        synchronized (LOCK) {
            OWNER_READY.countDown();
            try {
                RELEASE.await(); // WAITING khi vẫn giữ monitor LOCK.
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private static void contenderTask() {
        synchronized (LOCK) {
            System.out.println("CONTENDER_ACQUIRED");
        }
    }

    public static void main(String[] args) throws Exception {
        int seconds = 30;
        if (args.length == 1 && args[0].startsWith("--seconds=")) {
            seconds = Integer.parseInt(args[0].substring(10));
            if (seconds < 0 || seconds > 300) {
                throw new IllegalArgumentException("seconds must be 0..300");
            }
        } else if (args.length != 0) {
            throw new IllegalArgumentException("Usage: SaSnapshotLab [--seconds=N]");
        }

        Thread owner = new Thread(SaSnapshotLab::ownerTask, "sa-owner");
        Thread contender = new Thread(
                SaSnapshotLab::contenderTask, "sa-contender");

        owner.start();
        OWNER_READY.await();
        contender.start();

        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        while (contender.getState() != Thread.State.BLOCKED
                && System.nanoTime() < deadline) {
            Thread.sleep(10);
        }
        if (contender.getState() != Thread.State.BLOCKED) {
            RELEASE.countDown();
            throw new IllegalStateException("Could not observe BLOCKED thread");
        }

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("owner=" + owner.getState()
                + " contender=" + contender.getState());

        try {
            Thread.sleep(TimeUnit.SECONDS.toMillis(seconds));
        } finally {
            RELEASE.countDown();
        }
        owner.join();
        contender.join();
        System.out.println("END");
    }
}
~~~

**Cơ chế code:** `sa-owner` giữ `LOCK` rồi chờ `CountDownLatch`, vì vậy đang **WAITING** nhưng vẫn sở hữu intrinsic monitor. `sa-contender` cố đi vào `synchronized (LOCK)` và rơi vào **BLOCKED**. Đây là **contention có chủ đích**, không phải deadlock: main sẽ gọi `RELEASE.countDown()`, owner nhả monitor và contender đi tiếp.

Biên dịch và chạy:

~~~bash
javac -g SaSnapshotLab.java
java SaSnapshotLab
~~~

Output ban đầu có dạng:

~~~text
PID=<PID-thuc-te>
owner=WAITING contender=BLOCKED
~~~

Cửa sổ quan sát mặc định **30 giây**; trong lúc process còn sống, **terminal thứ hai** thay `<PID>` bằng số được in ra:

~~~bash
jcmd <PID> Thread.print -l
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
~~~

Trong thread dump, tìm `sa-owner` đang chờ latch và `sa-contender` đang đợi monitor. Nếu không tìm thấy thread do process đã kết thúc, chạy lại bằng `--seconds=60` để có thời gian xem. Sau khi cửa sổ quan sát đóng, chương trình in:

~~~text
CONTENDER_ACQUIRED
END
~~~

Với `--seconds=1`, toàn bộ lab kết thúc nhanh và stdout dự kiến (ngoại trừ PID thay đổi) là:

~~~text
PID=<PID-thuc-te>
owner=WAITING contender=BLOCKED
CONTENDER_ACQUIRED
END
~~~

Giải thích bằng chứng:

- Một **thread dump live** tại giây thứ 5 cho thấy contender BLOCKED, nhưng nếu lấy dump sau khi RELEASE thì contention đã hết.
- Nếu một **core** được tạo đúng khi contender BLOCKED, SA có thể tìm lại trạng thái ấy dù JVM nguồn không còn chạy; nhưng **lab này không tự tạo core**, và chỉ nên tạo core theo chính sách OS/thử nghiệm đã được phê duyệt.
- Không có một core thì **không thể** tự chạy lệnh mẫu `jhsdb ... --core ...`: `/var/crash/core.12345` chỉ là placeholder minh họa.

## 11. Một ma trận chọn công cụ và tình huống

| Tình trạng | Công cụ ưu tiên | Tránh nhầm |
| --- | --- | --- |
| JVM sống và phản hồi, cần thread dump | `jcmd Thread.print -l`, `jstack -l` | Không vội SA attach `--pid` |
| JVM sống, cần flags/properties | `jcmd VM.flags`, `VM.command_line`, `VM.system_properties` | `jhsdb jinfo` có thể dùng SA nhưng rủi ro quá lớn so nhu cầu |
| JVM sống, cần heap summary/histogram | `jcmd GC.heap_info`, `GC.class_histogram` khi cần | Histogram/dump có chi phí và có thể phản ánh khác nhau theo trạng thái GC |
| JVM đã chết và có core | `jhsdb jstack/jmap/jinfo --exe ... --core ...` | `jcmd` không attach được vào PID đã chết |
| Có core, cần đi sâu HotSpot structures | `jhsdb clhsdb --exe ... --core ...` | CLHSDB không phải Bash; cần matched VM/build |
| Có crash log nhưng không có core | `hs_err_pid` + logs/JFR/OS, tìm vì sao core không được lưu | Không thể dùng log text làm tham số `--core` |
| Nghi native segfault | Native debugger + matched libs/symbols, kết hợp SA nếu core đầy đủ | Mixed Java/native stack không thay register/disassembly |
| Live JVM treo, attach thường thất bại | Đánh giá OS signals/dump, cô lập bản sao hoặc SA `--pid` chỉ khi chấp nhận crash risk | Tài liệu Oracle cảnh báo SA có thể làm JVM treo/crash khi detach |
| Có `heap.hprof` nhưng không có core | MAT/heap analyzer | `jhsdb --core` không đọc HPROF như OS core |

### Lỗi thường gặp và cách chặn

1. **Nhập `--exe service.jar`:** sai; cần **native executable** (thường `bin/java`) tương ứng với VM/core, hoặc launcher thực khi dùng JNI Invocation API.
2. **Nhập mỗi `--core` mà không có `--exe`:** với chế độ core, hai tùy chọn phải đi thành cặp.
3. **Dùng `jhsdb jmap --histo <PID>`:** sai kiểu option; phải là `--pid <PID>` cho SA live hoặc `--exe ... --core ...` cho core.
4. **Dùng `jmap -dump...` truyền thống như cú pháp SA:** sai; `jhsdb jmap` có `--binaryheap --dumpfile`.
5. **Core mở thất bại vì khác JVM/build:** chuẩn bị đúng executable, `libjvm`, shared libraries và OS/architecture tương thích trước khi suy luận core hỏng.
6. **Thấy histogram lớn liền kết luận leak:** chưa có retained paths/lifecycle hoặc so sánh nhiều thời điểm.
7. **Thấy thread BLOCKED liền kết luận deadlock:** BLOCKED là trạng thái snapshot; cần xem lock owner và có vòng chờ hay không.
8. **Khi `jcmd` thất bại, chạy `jhsdb --pid` trên production ngay:** nguy hiểm; live SA attach có thể làm service ngừng tiến triển và crash khi detach.
9. **Chỉ đọc Java stack khi crash là SIGSEGV trong JNI:** cần native stack/symbols và register state.
10. **Copy core lên máy có JDK mới hơn rồi tin mọi kết quả:** HotSpot internals phụ thuộc version/build; khớp binary/runtime trước.
11. **Đưa core hoặc `jinfo --sysprops` công khai vào ticket:** có thể lộ secrets; kiểm soát truy cập và redact.
12. **Đọc “không có lỗi” từ snapshot:** core ghi đúng một thời điểm, có thể thiếu trang/đang giữa GC, không chứng minh không có vấn đề trước đó.

## 12. Checklist hậu kiểm có thể bàn giao

- [ ] Đã xác nhận ứng dụng **đang sống** hay **đã chết**, có đúng core hay chỉ `hs_err`/HPROF/JFR.
- [ ] Đã ghi PID, timestamp, Java/OS/CPU architecture, container namespace, JDK vendor/build và crash signal.
- [ ] Nếu JVM sống, đã ưu tiên `jcmd`/công cụ live và cân nhắc tác động trước khi dùng SA.
- [ ] Nếu dùng core, đã chuẩn bị **đúng `--exe` + `--core`**, không dùng file `.jar`/`.hprof` làm core.
- [ ] Đã đối chiếu executable và shared libraries với build/runtime sinh ra core; có debug symbols khi cần native stack.
- [ ] Đã dùng `jhsdb jstack` cho threads/locks, `jmap` cho heap/classes, `jinfo` cho flags/properties, `clhsdb` khi cần truy sâu.
- [ ] Có diễn giải được Java frames, blocked/waiting và quan hệ lock ownership **mà không kết luận deadlock vội**.
- [ ] Đã tách snapshot evidence khỏi giả thuyết về timeline/leak/causal crash.
- [ ] Đã kiểm tra dữ liệu nhạy cảm trong core/HPROF/system properties và giới hạn người được truy cập.
- [ ] Đã ghi lệnh, phiên bản công cụ, output đáng tin, phần thất bại do thiếu trang/symbol và việc cần làm tiếp.
- [ ] Báo cáo có ba phần: **quan sát được gì, chưa biết gì, phép thử hay chứng cứ nào xác nhận giả thuyết**.

### Nguồn tham khảo chính thức

- Oracle JDK 21 — The `jhsdb` Command (cú pháp, subcommands, cảnh báo live attach): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jhsdb.html
- Oracle JDK 21 — Diagnostic Tools (ưu tiên `jcmd` khi JVM đang sống và postmortem workflow): https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- OpenJDK — Command Line HSDB / CLHSDB commands: https://github.com/openjdk/jdk/blob/master/src/jdk.hotspot.agent/doc/clhsdb.html
- OpenJDK — Debugging Transported Core Dumps, lưu ý thư viện và symbols: https://github.com/openjdk/jdk/blob/master/src/jdk.hotspot.agent/doc/transported_core.html

**Kết luận:** `jhsdb jstack` đọc **thread/lock state**, `jmap` đọc **heap/class-related state**, `jinfo` đọc **VM flags/system properties**, còn `clhsdb` cho phép **đào sâu tương tác** vào cấu trúc HotSpot. Với **core offline**, dùng `--exe + --core` và binary/runtime phù hợp; với **JVM sống**, ưu tiên công cụ attach thông thường vì SA `--pid` có nguy cơ làm ngừng/crash tiến trình.