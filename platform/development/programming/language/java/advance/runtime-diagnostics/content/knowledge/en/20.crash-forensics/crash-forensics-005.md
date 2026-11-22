# 20.5. Phân biệt dấu hiệu lỗi trong native library, JVM hoặc mã được JIT biên dịch

## Mục tiêu

Khi một ứng dụng Java bị crash, bạn có thể thấy `SIGSEGV`, `SIGBUS`, `SIGILL`, `EXCEPTION_ACCESS_VIOLATION` hoặc một thông báo **`Internal Error`** từ HotSpot. Những dấu hiệu này khác với một Java exception thông thường. File **`hs_err_pid...log`** cho biết instruction đang thực thi ở đâu khi phát hiện lỗi; tuy nhiên **nơi crash không nhất thiết là nơi bug bắt đầu**.

Bài tập trung vào ba tình huống cần phân biệt:

- **Native library**: mã C/C++/JNI/JNA, thư viện `.so`/`.dll` của ứng dụng, vendor, JDK hoặc OS.
- **JVM/HotSpot**: mã bên trong VM, ví dụ GC, VM runtime, interpreter, compiler implementation hoặc các stub.
- **Mã Java đã JIT biên dịch**: machine code do JIT compiler tạo ra từ bytecode Java, được một thread thực thi.

Ngoài ra, phải phân biệt rõ **crash khi compiler thread đang biên dịch method** với **crash khi một application thread đang chạy method đã biên dịch**. Cả hai có thể liên quan JIT nhưng dấu vết khác nhau.

Mục tiêu sau bài:

1. Phân loại ký hiệu frame **`C`, `V`, `v`, `J`, `j`** trong HotSpot fatal error log.
2. Đọc cùng lúc `Problematic frame`, `Current thread`, thread state, `Native frames`, `Java frames`, `Current CompileTask` và `VM_Operation`.
3. Biết giới hạn của các suy luận “C = native bug”, “V = JVM bug”, “J = JIT bug”.
4. Dùng bằng chứng bổ sung như native core dump, loaded libraries, JVM flags, JDK build và phép thử có kiểm soát.
5. Thu thập, lưu và báo cáo crash artefacts an toàn; không cố tình làm crash môi trường production.

Các ví dụ dành cho **HotSpot/OpenJDK 17+**, với Linux là môi trường minh họa chính. Tên trường, tên thread, stack layout và tín hiệu có thể khác theo OS, architecture, JVM vendor hoặc JDK update.

## 1. Phân biệt JVM crash với Java exception và OS kill

| Điều quan sát được | Ý nghĩa khả dĩ | Bằng chứng ưu tiên |
| --- | --- | --- |
| `java.lang.NullPointerException`, `ArrayIndexOutOfBoundsException`, `IllegalStateException` | Java exception được ném theo cơ chế ngôn ngữ | Application stack trace và xử lý exception |
| `java.lang.OutOfMemoryError: Java heap space` | JVM không cấp phát được trong Java heap; **không tự động là native fatal crash** | Heap/GC logs, heap size, live objects |
| HotSpot báo `A fatal error has been detected by the Java Runtime Environment`, `Problematic frame` | JVM phát hiện fatal condition, thường cố ghi `hs_err` rồi dừng process | Fatal error log, native core/minidump |
| Linux `SIGSEGV` / Windows `EXCEPTION_ACCESS_VIOLATION` | Instruction thực thi dẫn đến memory access violation | `pc`/`rip`, `siginfo`, frame, native stack, core |
| `Internal Error`, `guarantee(...) failed`, `assert` | HotSpot phát hiện bất biến nội bộ bị vi phạm | Exact message, JDK version, current thread, VM state |
| Kubernetes `OOMKilled`, kernel `SIGKILL` | Process bị kết thúc từ ngoài JVM; có thể không có fatal error log | Container/kernel events, cgroup memory counters |
| Process tự thoát do shutdown / `System.exit` | Có thể là đường kết thúc hợp lệ/ứng dụng, không phải VM crash | Exit status, lifecycle logs, signal/health events |

**Chỉ thấy process biến mất không chứng minh VM bug.** `SIGKILL` không cho JVM chạy error handler; fatal log có thể không được tạo. Ngược lại, một native memory corruption có thể khiến JVM tự phát hiện lỗi và ghi `hs_err` — không có nghĩa JDK implementation đã tạo ra corruption.

Java `StackOverflowError` từ Java recursion thường khác với **native stack overflow** có thể gây fatal crash. Xem signal, frame và native stack thay vì gộp hai loại này.

## 2. File `hs_err_pid...log`: tìm ở đâu và giữ bằng chứng thế nào?

Với HotSpot, nếu không cấu hình lại, log fatal error thường có tên **`hs_err_pid12345.log`** (12345 là PID). JVM trước hết cố ghi vào **working directory của process**; nếu không được, có thể thử thư mục tạm OS như `/tmp` trên Linux. Lệnh khởi động có thể đặt địa điểm cụ thể:

```bash
java -XX:ErrorFile=/var/log/java/hs_err_pid%p.log -jar app.jar
```

`%p` là placeholder do JVM thay bằng PID. Cần xác minh thư mục tồn tại, quyền ghi, dung lượng và phương án thu thập file trong container. Không dùng một tên tệp cố định cho nhiều JVM nếu có nguy cơ ghi đè dữ liệu.

**Một cuộc điều tra tốt giữ nguyên bản** fatal error log, core/minidump nếu có, stdout/stderr, Java build và native libraries, timestamp, PID/TID/namespace, JVM flags, container image, OS/kernel version, workload đang chạy và những thay đổi vừa deploy. Đừng chỉ chụp màn hình 10 dòng header rồi bỏ mất phần stack/process/system.

File có thể ghi thiếu khi crash quá nghiêm trọng, stack bị hỏng, disk full hoặc error reporter lỗi. Nếu `hs_err` không tồn tại, kiểm tra OS events và nơi lưu log khác **trong phạm vi được phép** trước khi kết luận không có JVM crash.

**Bảo mật:** `hs_err`/core có thể chứa JVM arguments, đường dẫn, environment variables, memory addresses và dữ liệu nhạy cảm. Core có thể chứa dữ liệu bộ nhớ ứng dụng. Giữ quyền truy cập giới hạn và làm sạch nội dung khi chia sẻ bug report.

## 3. Cách đọc header: signal, PC, PID/TID và problematic frame

Mẫu **giả định**:

```text
#
# A fatal error has been detected by the Java Runtime Environment:
#
# SIGSEGV (0xb) at pc=0x00007f5ab0001240, pid=3015, tid=3020
#
# JRE version: OpenJDK Runtime Environment (17.x)
# Java VM: OpenJDK 64-Bit Server VM (17.x, mixed mode, ...)
# Problematic frame:
# C  [libfastcodec.so+0x1240]
#
```

Ở đây:

- `SIGSEGV` là tín hiệu segmentation violation trên Linux. Windows thường dùng mã exception như `EXCEPTION_ACCESS_VIOLATION`.
- `pc=...` (*program counter*) là địa chỉ instruction khi lỗi xảy ra, **không phải dòng mã Java**.
- `pid` xác định process; `tid` xác định native thread gặp lỗi. Trong container, PID namespace có thể khác host.
- `Problematic frame: C [libfastcodec.so+0x1240]` nói instruction thuộc một **native frame** trong thư viện có tên `libfastcodec.so`, ở offset liên quan đến image đã nạp.
- Dòng này gợi ý điều tra library/ABI/JNI, nhưng **không tự chứng minh thư viện gây corruption**. Có thể con trỏ đã bị phá ở nơi khác trước đó.

Một dấu hiệu khác trong Linux fatal log:

```text
siginfo: si_signo: 11 (SIGSEGV), si_code: 1 (SEGV_MAPERR), si_addr: 0x0000000000000000
```

`si_addr` là địa chỉ liên quan đến fault. `0x0` có thể gợi ý null pointer dereference ở native code. `SEGV_MAPERR` thường là address unmapped; `SEGV_ACCERR` liên quan quyền truy cập. Tuy nhiên, không kết luận nguyên nhân gốc chỉ từ `si_addr`: cần registers, instruction ở `pc` và memory mapping.

`SIGBUS`, `SIGILL`, `SIGFPE` hoặc `Internal Error` cũng có nhiều nguồn khác nhau, từ native library, codegen, VM runtime đến OS/hardware. Tên signal chỉ là **loại thất bại được phát hiện**, không phải tên module chịu trách nhiệm.

## 4. Ký hiệu HotSpot frame: chữ hoa, chữ thường rất quan trọng

| Marker | Vùng thực thi | Diễn giải đúng | Không nên kết luận |
| --- | --- | --- | --- |
| **`C`** | Native C/C++/library code | Crash PC nằm trong thư viện native, ví dụ `.so`/`.dll` | Không tự động là bug thư viện bên thứ ba; có thể là JDK native code hoặc corruption trước đó |
| **`V`** | HotSpot VM code | Crash PC nằm trong mã VM, có thể là GC, runtime, compiler implementation | Không tự động là bug của JVM |
| **`v`** | VM-generated stub/adapter | Có thể là runtime transition hoặc generated stub | Không tự động là nguồn bug |
| **`J`** | Compiled Java code | Java bytecode đã được compiler chuyển thành machine code, đang được chạy | Không tự động chứng minh compiler sinh mã sai |
| **`j`** | Interpreted Java code | Java bytecode đang được interpreter thực thi | `j` (chữ thường) **không** tương đương `J` (JIT compiled) |

Một số fatal logs có chú giải dạng `Native frames: (J=compiled Java code, j=interpreted, Vv=VM code, C=native code)`. Đọc **đúng ký hiệu** trong log đích; không trộn kiểu hiển thị của JDK này với JDK khác.

### Sự khác biệt quan trọng nhất về JIT

**Tình huống 1 — compiled code đang chạy:** `Problematic frame: J demo.Algorithm.compute`, current thread là `request-worker`. CPU đang ở machine code **đã được biên dịch**.

**Tình huống 2 — JIT compiler đang tạo code:** `Problematic frame: V [libjvm.so+...]`, `Current thread: C2 CompilerThread0`, có `Current CompileTask`. CPU đang chạy **compiler implementation** của HotSpot.

Dù cả hai nhắc đến JIT, nơi crash và hướng tái hiện khác nhau. Phải đọc **frame + current thread + compile task** thay vì chỉ thấy chữ `JIT` và quy lỗi.

## 5. Nhánh A: native library / JNI / third-party code

Mẫu **giả định**:

```text
# Problematic frame:
# C  [libimagecodec.so+0x23d]

---------------  T H R E A D  ---------------
Current thread: JavaThread "image-worker" [_thread_in_native, id=4220]

Native frames:
C  [libimagecodec.so+0x23d]
C  [libimagecodec.so+0x117]
j  demo.ImageService.decode([B)[I+0
v  ~StubRoutines::call_stub
```

Nhiều dấu hiệu cùng hướng về native:

1. `C` frame chỉ **instruction ở native code**; không phải bytecode Java.
2. `_thread_in_native` cho biết thread đang chạy native/JNI vào thời điểm crash.
3. Stack có nhiều `C` frames trong thư viện codec và một Java caller liên quan.
4. Khi tìm `Dynamic libraries` trong `hs_err`, nên xác minh **đúng đường dẫn và binary build thực tế được load**, không chỉ tên dependency trên build file.
5. Nghi vấn cần kiểm tra: bounds violation, use-after-free, double-free, invalid pointer, JNI reference lifetime, JNI thread attachment, race, allocator mismatch hoặc ABI/architecture incompatibility.

Một `C [libnet.so]` hoặc `C [zip.dll]` cũng là native frame, nhưng có thể thuộc **JDK distribution**. Nếu lỗi nằm trong JDK native library, hãy điều tra đồng thời JDK build, OS, agents và JNI/native caller; đừng gộp nó với “HotSpot VM core” hay tự quy về thư viện của ứng dụng.

### Lỗi trong JNI có thể hiện ra dưới dạng VM frame

Mẫu minh họa kinh điển:

```text
# Problematic frame:
# V  [jvm.dll+0x83d77]

Current thread: JavaThread "main" [_thread_in_vm, id=2896]
Native frames:
V  [jvm.dll+0x83d77]
C  [App.dll+0x1047]
j  demo.NativeService.invoke()V+0
```

Mặc dù **`Problematic frame` là `V`**, stack có native `App.dll` gọi vào VM. Một JNI routine truyền pointer/reference sai có thể khiến HotSpot crash khi xử lý yêu cầu. Do đó hãy kiểm tra **caller chain và JNI contract**, không chỉ dòng đầu.

### Kiểm tra JNI trong môi trường được kiểm soát

```bash
java -Xcheck:jni -jar app.jar
```

`-Xcheck:jni` yêu cầu HotSpot thực hiện kiểm tra thêm khi gọi JNI. Nó có thể phát hiện nhiều kiểu JNI misuse, nhưng **không đảm bảo** tìm mọi bug native/C++ (đặc biệt lỗi con trỏ, data race, stack corruption). Có overhead và một vi phạm nghiêm trọng có thể làm VM dừng. Chỉ bật trong staging/test có quyền và đã chuẩn bị log, không coi như “cờ sửa lỗi”.

Nếu có source native, dùng compiler sanitizers, native debugger và đúng debug symbols trong môi trường phù hợp; đối chiếu lỗi với input/version/threading thay vì suy từ tên library.

## 6. Nhánh B: JVM/HotSpot VM code, GC, safepoint và internal error

Ví dụ:

```text
# Problematic frame:
# V  [libjvm.so+0x4f20]

Current thread: VMThread [id=5100]
VM_Operation: ... (tên operation phụ thuộc phiên bản)
```

Marker `V` cho thấy instruction crash thuộc phần core HotSpot VM. Nhưng **root cause** có thể gồm:

- Bug VM/GC/runtime hoặc một JDK update cụ thể.
- JNI/native library hoặc JVMTI agent làm hỏng heap/object references trước; VM phát hiện muộn trong một GC/safepoint.
- Metadata/code cache/ClassLoader state bất thường, lỗi vùng native memory.
- Hardware/OS/driver hoặc memory corruption ở mức thấp khác.

Nếu current thread là **`VMThread`**, xem `VM_Operation`. Khi operation liên quan GC, cần thêm GC logs, native agent/JNI history, exact GC collector và flags. “Crash xảy ra trong GC” **không chứng minh GC implementation là thủ phạm**.

Nếu header là `Internal Error`, `guarantee(...) failed`, `ShouldNotReachHere` hay `assert`, VM tự báo một invariant bị vi phạm. Mã nguồn/file/line nội bộ (nếu có) và exact JDK build quan trọng. Cùng một internal error string qua hai bản JDK **không đảm bảo** cùng nguyên nhân; ngược lại cùng một lỗi gốc có thể báo khác nhau.

### Current thread state là dấu hiệu, không phải verdict

- `_thread_in_native`: ở native code tại thời điểm báo.
- `_thread_in_vm`: đang ở mã VM.
- `_thread_in_Java`: đang chạy code Java interpreted hoặc compiled.
- `VMThread`, `GC Thread`, `CompilerThread` là vai trò thread. Tên cụ thể thay đổi theo collector/JDK.

Thread state chỉ là **ảnh chụp** ở thời điểm crash. Một native bug có thể làm dữ liệu hỏng hàng giây/phút trước, rồi JVM crash khi GC quét tới đối tượng. Vì vậy cần đối chiếu vùng hỏng và chuỗi sự kiện, không dừng ở một trạng thái.

## 7. Nhánh C: lỗi khi chạy mã Java **đã được JIT biên dịch**

Ví dụ mẫu:

```text
# SIGSEGV (0xb) at pc=0x00007f0000009000, pid=6100, tid=6111
# Problematic frame:
# J 1342 c2 demo.FastHash.mix([B)I

Current thread: JavaThread "request-9" [_thread_in_Java, id=6111]
```

Ý nghĩa:

- `J` là **compiled Java frame**, tức method Java đã được chuyển thành native machine code và **đang chạy**.
- `request-9` là application thread, **không phải** compiler thread đang tạo machine code.
- `c2` trong ví dụ là dấu vết tier tối ưu trên một số HotSpot output; định dạng, ID và tier có thể khác.
- Method `demo.FastHash.mix` được gắn với crash PC. Đây là **method đang chạy lúc phát hiện lỗi**, chưa chắc là method có bug.

Các giả thuyết bao gồm JIT wrong-code generation, bug ở intrinsic/runtime stub, native/JNI/JVMTI corruption, unsafe native access hoặc hardware/OS fault. Mã Java thông thường sai logic sẽ ném exception hoặc trả kết quả sai, **không mặc nhiên tạo SIGSEGV**; vì thế cần kiểm tra cả con đường chuyển đổi native/VM.

### A/B với interpreter mode `-Xint`

```bash
java -Xint -jar app.jar
```

`-Xint` chạy bytecode theo chế độ interpreted-only, không sử dụng JIT compilation cho Java hot methods. Nếu crash lặp lại ổn định ở mixed mode nhưng không xảy ra ở `-Xint`, đây là **tín hiệu hỗ trợ giả thuyết JIT** — vẫn chưa phải chứng minh, vì interpreter làm thay đổi timing, hiệu năng và tương tác concurrency, có thể che giấu native race.

**Không bật `-Xint` trên production như một “fix” mặc định:** throughput/latency có thể giảm mạnh. Chỉ thử trong môi trường cô lập, thống kê tỷ lệ crash qua nhiều lần lặp và giữ input/config cố định.

### A/B chỉ loại trừ một method khỏi JIT

Nếu log cho method cụ thể `demo.FastHash.mix`:

```bash
java -XX:CompileCommand=exclude,demo/FastHash.mix -jar app.jar
```

Cờ HotSpot JDK 17 này ngăn compiler biên dịch method đã chỉ định, làm phạm vi thử nghiệm hẹp hơn `-Xint`. Dùng đúng package/class/method như trong build thật; tên overloaded methods có thể cần signature phù hợp. Giảm crash với cờ này **không nhất thiết** chứng minh JIT bug vì nó cũng đổi timing/inlining và workload. Đây là thử nghiệm phục vụ chẩn đoán, phải đi cùng reproducer và core evidence.

## 8. Nhánh D: HotSpot **CompilerThread đang biên dịch**, không phải compiled Java code đang chạy

Mẫu giả định:

```text
# Problematic frame:
# V  [libjvm.so+0xa321]

Current thread: JavaThread "C2 CompilerThread0" daemon [_thread_in_vm, id=7201]

Current CompileTask:
... demo.MathKernel.fold(I)J ...
```

Điều biết được:

1. Current thread là `C2 CompilerThread0`: compiler implementation của HotSpot đang chạy để **tạo mã máy**.
2. `Problematic frame: V` nói instruction gặp lỗi thuộc VM code, hoàn toàn hợp lý vì JIT compiler được triển khai trong VM runtime.
3. `Current CompileTask` chỉ method đang được compile khi lỗi xảy ra. Java source của method là *đầu vào* của JIT; **không được quy ngay lỗi cho người viết method**.
4. Có thể nghi bug ở compiler IR/optimizer/code generation hoặc native memory corruption gây ảnh hưởng compiler.
5. Cần exact JDK patch level, compiler tier, log compilation (nếu đã có), method bytecode, flags và reproducer.

**Đây là điểm phân biệt cốt lõi:**

| Nhãn | Thread | Frame thường thấy | Giai đoạn |
| --- | --- | --- | --- |
| Crash trong **compiled Java method** | `request-worker` / application thread | `J demo.Class.method` | Chạy **machine code đã sinh ra** |
| Crash trong **JIT compiler implementation** | `C1 CompilerThread` / `C2 CompilerThread` | Thường là `V [libjvm]` | **Đang biên dịch/optimize** một method |
| Java bytecode đang interpreted | Application thread | `j demo.Class.method` | Interpreter, **không** phải JIT execution |

Tên compiler thread và format của `Current CompileTask` thay đổi theo VM/JDK. Các tài liệu lịch sử có ví dụ `CompilerThread0`/`AdapterCompiler` và `-client`; không sao chép nguyên workaround của JVM rất cũ vào JDK 17. Kiểm tra options và implementation của JVM đang dùng.

## 9. Crash site không đồng nghĩa root cause: hai tầng bằng chứng

Mỗi lần phân loại nên viết thành hai câu tách biệt:

- **Quan sát:** “Crash PC ở `C [libx.so]`”, “VM thread đang thực hiện GC”, hoặc “thread `request-7` chạy `J Class.method`”.
- **Giả thuyết:** “Nghi JNI pointer invalid”, “nghi heap corruption/GC interaction”, hoặc “nghi lỗi sinh mã JIT/agent corruption”.

Không biến giả thuyết thành kết luận khi chưa đối chiếu.

### Ví dụ 1: crash ở VM nhưng native là nguồn

Một native library giữ JNI global reference sau khi đã release, khiến object reference không hợp lệ. VM crash khi xử lý reference trong GC. Header có thể là `V [libjvm.so]` và `VM_Operation` liên quan GC. Kết luận “HotSpot GC bug” chỉ từ frame `V` có thể khiến điều tra sai.

### Ví dụ 2: crash ở compiled method nhưng nguyên nhân từ JNI

Native code ghi vượt buffer làm hỏng một object/address. Một giờ sau, request thread chạy method đã JIT compile và SIGSEGV tại `J demo.Index.lookup`. Frame `J` vẫn đúng về **nơi phát hiện**, nhưng lỗi gốc có thể là native corruption trước đó.

### Ví dụ 3: crash khi compiler chạy, code Java là input

`Current thread: C2 CompilerThread0` và `Current CompileTask: demo.Algo.compute` có thể chỉ ra compiler crash khi xử lý bytecode. Nó không nói rằng Java code có pointer lỗi; với code Java hợp lệ, JIT compiler/JVM có trách nhiệm xử lý an toàn. Cần reproducer và JDK/vendor evidence.

### Tín hiệu mạnh hơn một frame

- Một reproducer nhỏ lặp lại cùng crash **trên đúng build**.
- Native core dump và debug symbols khớp build xác nhận instruction/memory.
- Controlled A/B chỉ thay library/agent version hoặc JDK patch level.
- Lỗi biến mất nhất quán sau sửa cụ thể, xác nhận lại ở tải tương đương.
- Crash xảy ra trên nhiều máy hay chỉ một hardware/kernel/image.
- Đối chiếu loaded libraries, GC/JIT flags và lịch sử deploy.

Kể cả khi một workaround chặn được crash, vẫn phân biệt **“ngừng tái hiện trong phép thử”** với **“root cause đã xác nhận”**.

## 10. Bảng triage ba nguồn crash

| Dấu hiệu kết hợp | Hướng điều tra trước | Điều cần loại trừ/đối chiếu |
| --- | --- | --- |
| `C [libthirdparty.so]` + `_thread_in_native` + nhiều `C` frames | Native library/JNI/ABI/ownership | Core, source, loaded binary thực, race/corruption khác |
| `C [libnet.so]` / `C [awt.dll]` thuộc JDK | JDK native library và OS interactions | Native agents, VM/JDK bug, ABI, system dependencies |
| `V [libjvm.so]` + `VMThread` + `VM_Operation` liên quan GC | GC/VM runtime crash site | JNI/agent corruption, collector config, VM bug, hardware |
| `V [jvm.dll]` + stack ngay dưới có `C [App.dll]` | VM crash khi bị native caller gọi | JNI contract/reference misuse; không chốt JVM bug |
| `J demo.Method` + `request-worker` | Compiled Java code đang chạy | JIT wrong-code generation, native memory corruption, agents, intrinsics |
| `V [libjvm]` + `C2 CompilerThread` + `Current CompileTask` | HotSpot compiler đang thực thi | Compiler bug vs corrupted compiler state, method input/JDK build |
| `j demo.Method` | Interpreted frame | Kiểm tra toàn stack/top PC; không gọi đây là JIT compiled frame |
| `v ~StubRoutines` | VM generated stub/adapter | Liền kề native/Java/VM frames và registers |
| `Internal Error` / `guarantee failed` | VM phát hiện invalid internal state | Exact JDK build, file/line, input, flags, memory corruption |
| Không có `hs_err` nhưng `OOMKilled` | OS/container đã kill process | cgroup/host logs, memory limits, exit event, đừng suy native/JIT bug |

**Nhắc lại:** Marker chỉ phân loại **khu vực xảy ra lỗi**. Trong bug do memory corruption, nơi đầu tiên viết sai và nơi cuối cùng crash có thể cách nhau xa về thời gian và stack.

## 11. Quy trình xử lý file fatal error sau sự cố

### Bước 1 — Định danh đúng lần crash

Xác minh timestamp, PID, process/container, Java command, JDK vendor/build, OS kernel/CPU architecture, app release, các library/agents nạp vào, JVM flags, load và thay đổi gần nhất. Đừng nhầm fatal log cũ với lần deploy mới.

### Bước 2 — Bắt đầu từ header

Đọc signal/internal error, `pc`, `pid`/`tid`, `Problematic frame`. Xác định `C/V/v/J/j` và module/method; ghi lại bằng ngôn ngữ quan sát thay vì gán nhãn bug quá sớm.

### Bước 3 — Đọc thread và stack

Trong `THREAD` section, xem `Current thread`, state, native frames và Java frames. Nếu compiler thread → tìm `Current CompileTask`; nếu VMThread → tìm `VM_Operation`; nếu C/native → tìm Java/native transition và library source.

Đừng coi mọi Java stack trace trong `hs_err` là call stack chính xác đến từng method: inlining, corrupt stack và lỗi khi error reporter chạy có thể làm log thiếu hoặc không đầy đủ. Nếu thấy `error occurred during error reporting`, ghi rõ giới hạn dữ liệu.

### Bước 4 — Tìm module và cấu hình thật

Đối chiếu `Dynamic libraries`/memory map với phiên bản thư viện trên disk và trong container image. Xem `VM Arguments`, `java_command`, JDK build, GC/JIT flags, JVMTI agents và JNI dependencies. Offset ở `libfoo.so+0x...` cần **binary và debug symbols đúng build** để có function/source line đáng tin; address-space layout randomization (ASLR) cũng ảnh hưởng địa chỉ.

### Bước 5 — Thu thêm chứng cứ

- **Native core/minidump** (nếu hệ thống đã cấu hình thu thập và có quyền): native backtrace, registers, memory map, disassembly.
- **GC/JVM logs** khi nghi GC/VMThread.
- **JFR/compilation logs** nếu đã bật và có dữ liệu được lưu trước crash; recording có thể không được flush đầy đủ khi process chết đột ngột.
- **OS/kubernetes/kernel events** để loại trừ OOM kill, hardware issues, native memory/resource exhaustion.
- **Heap dump** hữu ích cho object graph/OOME, nhưng **không thay thế native core** khi cần điều tra corrupted C/C++ pointer hoặc JIT machine code.

### Bước 6 — Phép thử có kiểm soát ở staging

- Nghi native: thay đúng native library version hoặc bỏ/tắt agent sau khi có phép thử, dùng `-Xcheck:jni` và native sanitizer khi phù hợp.
- Nghi JIT compiled: so mixed mode với `-Xint` hoặc targeted `-XX:CompileCommand=exclude`; giữ input, workload và cờ còn lại đồng nhất.
- Nghi VM/GC: so crash với GC logs, code source/vendor issue, agent/JNI, đổi collector hoặc JDK update **mỗi lần một biến** nếu được phép.
- Đo tần suất qua nhiều lần tái hiện. Một lần không crash có thể chỉ là race/timing đổi.

### Bước 7 — Báo cáo đúng owner

Thư viện của ứng dụng → nhóm native code. Thư viện bên thứ ba → vendor với symbolic trace/reproducer. Nghi HotSpot/JDK → báo JDK vendor/bug tracker cùng exact version, reproducer, flags, các phép thử, log đã redact và core theo quy định. **Workaround** phải được ghi tách khỏi **root cause confirmed**.

## 12. Lệnh trích những dòng cần đọc từ fatal log (Linux)

Giả sử file đã được xác nhận là bản sao của đúng lần crash:

```bash
grep -n -E 'SIGSEGV|SIGBUS|SIGILL|Internal Error|Problematic frame|Current thread|VM_Operation|Current CompileTask|Native frames|Java frames|Dynamic libraries' hs_err_pid3015.log
```

Đọc phần header và đầu thread section:

```bash
sed -n '1,140p' hs_err_pid3015.log
```

Hai lệnh chỉ đọc. Nếu `grep` không thấy `Current CompileTask`, có thể chỉ là log không có phần ấy; không có nghĩa không xảy ra compilation. Nếu log chỉ còn một phần, tránh điền vào chi tiết chưa quan sát.

Nếu **đã có native core** cùng đúng executable và symbols, có thể dùng debugger trong môi trường cho phép:

```bash
gdb -q /path/to/java /path/to/core
```

Việc phân tích core phải kiểm tra đúng executable/JDK/library build; nếu symbols không khớp, stack/function names có thể sai. Trên Windows, dùng WinDbg/Visual Studio dump tools tương đương. Không khởi động debugger attach lên production process khi chưa được phép.

## 13. Ví dụ Java 17 độc lập: đọc ký hiệu frame mà **không tạo crash**

Chương trình nhỏ dưới đây chỉ phân tích **ba chuỗi log giả lập**. Nó không truy cập native memory, không ném SIGSEGV và không sửa JVM flags. Mục đích là nhìn thấy frame marker tương ứng với loại vùng thực thi; **không tự động tìm root cause**.

Tạo file **`CrashFrameClues.java`**:

```java
public final class CrashFrameClues {
    static String frameKind(String log) {
        boolean afterHeader = false;

        for (String raw : log.split("\\R")) {
            String line = raw.trim();
            if (line.startsWith("#")) {
                line = line.substring(1).trim();
            }

            if (!afterHeader) {
                if (line.equals("Problematic frame:")) {
                    afterHeader = true;
                }
                continue;
            }

            if (line.isEmpty()) {
                continue;
            }

            if (line.length() < 2 || !Character.isWhitespace(line.charAt(1))) {
                return "UNKNOWN";
            }

            return switch (line.charAt(0)) {
                case 'C' -> "NATIVE_FRAME";
                case 'V' -> "VM_FRAME";
                case 'v' -> "VM_STUB_FRAME";
                case 'J' -> "COMPILED_JAVA_FRAME";
                case 'j' -> "INTERPRETED_JAVA_FRAME";
                default -> "UNKNOWN";
            };
        }

        return "UNKNOWN";
    }

    public static void main(String[] args) {
        String[] sampleLogs = {
            "# Problematic frame:\n# C  [libdemo.so+0x20]\n",
            "# Problematic frame:\n# V  [libjvm.so+0x44]\n",
            "# Problematic frame:\n# J 301 c2 demo.Hash.mix([B)I\n"
        };

        for (int i = 0; i < sampleLogs.length; i++) {
            System.out.println("case" + (i + 1) + "="
                    + frameKind(sampleLogs[i]));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 CrashFrameClues.java
java CrashFrameClues
```

**Output chính xác khi chương trình chạy thành công:**

```text
case1=NATIVE_FRAME
case2=VM_FRAME
case3=COMPILED_JAVA_FRAME
```

Diễn giải:

- `case1`: crash instruction trong native code, cần đọc tên library/stack/JNI.
- `case2`: crash instruction trong HotSpot VM; vẫn cần current thread/VM operation/native caller.
- `case3`: compiled Java code đang chạy; cần xem thread, JIT và native corruption.

**Giới hạn cố ý:** code chỉ lấy ký hiệu ngay dưới `Problematic frame` trong **mẫu đơn giản**, không phải parser production chuẩn cho mọi `hs_err` giữa các OS/JDK. Nó không xác thực symbol, registers, corrupted stack hay compile task. Cần đọc file thật bằng con mắt forensic và kiểm tra nhiều phần chứng cứ.

## 14. Phân tích tình huống

### Tình huống A — Sau nâng native image codec thì crash

Một JVM có `C [libcodec.so+...]`, `_thread_in_native`, cùng stack trong `decode`; thử input giống nhau trong staging cho crash đều, rollback native codec làm lỗi biến mất.

**Hướng đúng:** đây là bằng chứng mạnh về native codec hoặc interaction với ABI/OS. Lấy core và symbols, kiểm tra pointer/buffer/lifetime. Nhưng vẫn phân biệt **thư viện gây crash** với **bug thực sự trong thư viện**, vì có thể có bên thứ ba làm hỏng memory.

### Tình huống B — Crash `V [libjvm]` trong GC sau nâng JVMTI agent

Mục `VM_Operation` ghi GC, current thread `VMThread`; agent nạp vào JVM vừa thay đổi. Kết luận “JVM GC bug” sẽ thiếu bước xem JVMTI/JNI có làm corrupt object graph hay không.

**Hướng đúng:** giữ core/GC/JVM logs, làm A/B agent version trong staging, dùng JDK patch đang hỗ trợ, và kiểm tra memory corruption.

### Tình huống C — `J demo.Transform.hash` trên request thread

Crash tái hiện nhiều lần khi chạy compiled code, `-Xint` không tái hiện trong hàng loạt test. Đây là tín hiệu **nghi JIT**, nhưng thay đổi scheduling có thể khiến native race không biểu hiện. Nếu targeted method exclusion cũng làm biến mất crash, giả thuyết JIT càng đáng xem. Vẫn nên cung cấp reproducer và core, kiểm tra JNI/agent.

### Tình huống D — `V [libjvm]` trên `C2 CompilerThread`

`Current CompileTask` ghi `demo.Transform.hash`. Lỗi xảy ra khi compiler **đang tạo mã**, không phải request thread đã thực thi code `J`. Điều tra compiler implementation, bytecode method, tiered flags, exact JDK build và khả năng memory corruption; tránh đổ lỗi cho business logic Java chỉ vì tên method xuất hiện.

## 15. Những sai lầm phổ biến

1. **“`C` luôn là bug thư viện bên thứ ba.”** Không: C chỉ vị trí native frame, kể cả JDK-native/OS-native.
2. **“`V` tức HotSpot chắc chắn là nguyên nhân gốc.”** Có thể native caller đã làm corrupt memory.
3. **“`J` tức Java source gây segfault.”** Nó là JIT-compiled machine code đang chạy, không tự chứng minh lỗi Java source hay JIT compiler.
4. **“`j` nghĩa là JIT.”** `j` chữ thường là interpreted frame; `J` chữ hoa mới là compiled Java frame.
5. **“CompilerThread crash luôn hiện `J`.”** Compiler implementation thường ở `V`; `J` là mã đã biên dịch đang chạy.
6. **“`SIGSEGV` là Java `NullPointerException`.”** Hai cơ chế khác nhau; Java NPE thường không crash VM.
7. **“Crash trong GC thì chỉ cần tăng `-Xmx`.”** Chưa có căn cứ; có thể heap corruption/JNI/VM bug.
8. **“`-Xint` hết crash => chứng minh JIT bug.”** Interpreter đổi hiệu năng/timing, dễ làm race biến mất.
9. **“`-XX:CompileCommand=exclude` là fix không có tác dụng phụ.”** Có thể giảm performance/đổi codegen; chỉ thử có kiểm soát.
10. **“Không có `hs_err` là không crash.”** Có thể bị OS kill hoặc không ghi được file.
11. **“Heap dump đủ điều tra native crash.”** Không thay native core và registers/symbols.
12. **“`libfoo.so+0x10` cho biết ngay dòng source.”** Cần đúng binary, debug symbols và relocation/load map.
13. **“`Current CompileTask` nghĩa là developer viết sai Java method.”** Compiler đang xử lý input bytecode; chưa biết root cause.
14. **“Một lần không tái hiện nghĩa là đã sửa.”** Race/timing-sensitive crash cần nhiều lần A/B.
15. **“Có thể gửi nguyên core/fatal log công khai.”** Chúng có thể chứa bí mật; phải xử lý bảo mật.
16. **“Mọi JVM fatal crash đều là JDK bug.”** Native library, agent, OS, hardware và resource limits đều có thể gây crash.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `Problematic frame: C [libvendor.so+0x3d]`, current thread `_thread_in_native`. Cần làm gì?  
**Đáp án:** Điều tra native code/JNI, đúng binary, stack/core/symbol và input. Chưa khẳng định bug thuộc vendor chỉ từ frame.

**Câu 2.** `Problematic frame: V [jvm.dll]`, stack kế có `C [App.dll]`. Có thể kết luận JVM bug?  
**Đáp án:** Không; VM là crash site, JNI caller có thể truyền reference sai hoặc gây memory corruption.

**Câu 3.** `Problematic frame: J demo.FastPath.run` trên request worker là crash khi JIT compiler đang tạo mã?  
**Đáp án:** Không. Đây là dấu hiệu **đang chạy compiled Java code**.

**Câu 4.** `Problematic frame: V`, current `C2 CompilerThread0`, có `Current CompileTask`. Vì sao khác câu 3?  
**Đáp án:** Compiler thread **đang compile** method, không phải thread ứng dụng thực thi compiled Java machine code.

**Câu 5.** Thử `-Xint` không crash nữa. Đã chứng minh bug JIT chưa?  
**Đáp án:** Chưa. Có thể do compiler, nhưng cũng có thể timing thay đổi che một native race.

**Câu 6.** `VMThread` bị fatal trong `VM_Operation` GC. Cần kiểm tra nguồn nào nữa?  
**Đáp án:** JNI/JVMTI agents, heap corruption, GC logs, collector flags, core, exact JDK build và OS/hardware.

**Câu 7.** Pod bị OOMKilled nhưng không có `hs_err`. Có nên tìm compiled code `J` trước không?  
**Đáp án:** Không; ưu tiên cgroup/kernel memory events vì kernel có thể kill JVM từ ngoài.

**Câu 8.** Vì sao không thể dùng tên `libfoo.so+offset` để khẳng định dòng source?  
**Đáp án:** Cần đúng binary, symbols, build, relocation/ASLR và load addresses. Tên module chỉ là manh mối.

## Tài liệu chính thống

- [Oracle JDK 17 — Troubleshoot System Crashes](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-system-crashes.html)
- [Oracle JDK 17 — Fatal Error Log: header, frame types, thread/process/system](https://docs.oracle.com/en/java/javase/17/troubleshoot/location-fatal-error-log.html)
- [Oracle JDK 17 — `java`: `-Xcheck:jni`, `-Xint`, `-XX:ErrorFile`, `-XX:CompileCommand`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle Java troubleshooting — How to Find and Interpret the HotSpot Fatal Error Log](https://ops.java/troubleshooting/articles/fatal-error-log)
