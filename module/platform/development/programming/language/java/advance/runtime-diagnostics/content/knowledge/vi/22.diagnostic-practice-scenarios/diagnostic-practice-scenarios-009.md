# 22.9. Đọc một fatal error log mẫu và phân loại bằng chứng cần bổ sung

## Mục tiêu

Trong thực tế, một Java process đột ngột biến mất có thể do Java exception không được xử lý, HotSpot gặp **fatal error**, native/JNI code lỗi, OS gửi `SIGKILL` hoặc container bị OOMKilled. Nếu thấy `hs_err_pid*.log`, câu hỏi không chỉ là “`Problematic frame` nằm ở đâu?” mà còn là: **dữ kiện nào đã được xác nhận, giả thuyết nào đang xem xét và còn thiếu bằng chứng nào để chứng minh nguyên nhân gốc?**

Bài thực hành tổng hợp này hướng dẫn bạn đọc một **fatal error log mô phỏng** theo đúng trình tự, tự điền phiếu nhận định và lập danh mục artefact cần thu thập trước khi đưa ra kết luận.

Sau bài học, bạn có thể:

1. Đọc `SIGSEGV`, `pc`, `pid/tid`, `Problematic frame`, `Current thread`, `Native frames`, `Java frames`, `VM Arguments` và `Dynamic libraries`.
2. Phân biệt marker **`C`/`V`/`v`/`J`/`j`**; không nhầm **mã JIT đang chạy** với **compiler thread đang biên dịch**.
3. Phân loại nhận định thành **OBSERVED** (đã thấy trong chứng cứ), **INFERRED** (giả thuyết hợp lý) và **UNKNOWN** (chưa có chứng cứ).
4. Xếp loại chứng cứ cần bổ sung **P0/P1/P2**, xác định nguồn thu thập và câu hỏi kiểm chứng.
5. Đưa ra kế hoạch triage/reproducer/A-B an toàn, có ghi nhận giới hạn và quyền truy cập, không cố tạo crash trên production.

Phạm vi là **HotSpot/OpenJDK 17+ trên Linux**. Trên Windows, macOS, vendor JVM khác hoặc JDK update khác, header, signal, frame hay tên thư viện có thể thay đổi. **Log, PID, thời điểm, thư viện và mọi đường dẫn trong ví dụ hoàn toàn giả lập**; không được dùng như bằng chứng của một incident thực tế.

## 1. Tình huống: dịch vụ giải mã ảnh bị restart bất thường

Một dịch vụ `demo.ImageServer` gọi thư viện native giải mã ảnh qua JNI. Sau một request đầu vào mới, process bị restart. Trong ổ lưu crash còn một bản **trích đoạn** `hs_err_pid7312.log` được đơn giản hóa để học cách đọc.

### 1.1. Fatal error log mẫu

```text
#
# A fatal error has been detected by the Java Runtime Environment:
#
# SIGSEGV (0xb) at pc=0x00007f5a100013d1, pid=7312, tid=7318
#
# JRE version: OpenJDK Runtime Environment (17.x, illustrative build)
# Java VM: OpenJDK 64-Bit Server VM (17.x, mixed mode, linux-amd64)
#
# Problematic frame:
# C  [libatlascodec.so+0x13d1] Java_demo_codec_Decoder_decode+0x51
#
# Core dump will be written. Default location: /var/crash/core.7312
#
---------------  T H R E A D  ---------------
Current thread: JavaThread "decode-io-3" [_thread_in_native, id=7318]

siginfo: si_signo: 11 (SIGSEGV), si_code: 1 (SEGV_MAPERR),
         si_addr: 0x0000000000000000

Native frames: (J=compiled Java code, j=interpreted,
                Vv=VM code, C=native code)
C  [libatlascodec.so+0x13d1] Java_demo_codec_Decoder_decode+0x51
C  [libatlascodec.so+0x1014] codec_unpack+0x24
j  demo.codec.Decoder.decode([B)[B+0
j  demo.service.ImageService.render([B)[B+0
v  ~StubRoutines::call_stub

Java frames: (J=compiled Java code, j=interpreted, Vv=VM code)
j  demo.codec.Decoder.decode([B)[B+0
j  demo.service.ImageService.render([B)[B+0

---------------  P R O C E S S  ---------------
VM Arguments:
jvm_args: -Xmx512m -XX:ErrorFile=/var/crash/hs_err_pid%p.log
java_command: demo.ImageServer

Dynamic libraries:
0x00007f5a10000000-0x00007f5a10005000 /opt/app/native/libatlascodec.so
0x00007f5a20000000-0x00007f5a23000000 /opt/jdk/lib/server/libjvm.so

---------------  S Y S T E M  ---------------
OS: Linux x86_64 (illustrative)
CPU: x86_64 (illustrative)
#
```

**Cách đọc mẫu:** đây chỉ là **trích đoạn dạy học** với một số section được giản lược; không gọi nó là file `hs_err` hoàn chỉnh. Trong mẫu, `pc` được đặt tương ứng vùng memory mapping bắt đầu `0x00007f5a10000000` và offset `0x13d1` trong `libatlascodec.so`. Địa chỉ ấy là dữ liệu hư cấu, không xác định một function/source line trong binary thật. Dòng “Core dump will be written” là thông báo dự kiến; **không khẳng định file core đã có** nếu chưa kiểm tra trên filesystem/core handler.

## 2. Đọc header: chỉ ghi điều đã xuất hiện

| Dấu hiệu trong log | Có thể nói điều gì? | Chưa thể nói điều gì? |
| --- | --- | --- |
| `SIGSEGV (0xb)` | Linux báo segmentation violation tại một instruction trong process | Không tự chứng minh đây là Java `NullPointerException` hoặc bug JVM |
| `pc=0x00007f5a100013d1` | Program counter/instruction pointer khi xảy ra fault | Không phải địa chỉ Java object hay dòng source đã giải mã |
| `pid=7312` | PID JVM tại thời điểm crash | Không chắc trùng host PID nếu process chạy trong PID namespace |
| `tid=7318` | Native thread đã gặp fatal error | Không được dùng `Thread.getId()` của Java để suy trực tiếp OS TID |
| `OpenJDK 17.x` | Nhóm runtime/architecture của mẫu | Chưa đủ exact vendor/JDK patch/build để so known bug |
| `C [libatlascodec.so+0x13d1]` | Instruction ở native frame thuộc một shared library | Chưa chứng minh thư viện đã tạo lỗi gốc |
| `Core dump will be written` | Error reporter dự định tạo core ở đường dẫn đã in | Chưa xác nhận core đã tồn tại, còn đọc được hay chứa đúng lần crash |

### 2.1. `siginfo` và `si_addr`

`SEGV_MAPERR` thường cho biết chương trình truy cập một địa chỉ chưa được map. `si_addr=0x0` gợi ý truy cập gần/null address ở native code, nhưng **không đồng nghĩa đã tìm thấy chính xác con trỏ lỗi**. Để hiểu instruction đọc/ghi địa chỉ nào, cần xem **registers, disassembly, memory mapping và native core**.

`SIGBUS`, `SIGILL`, `SIGFPE` hay `Internal Error` dẫn tới các nhánh điều tra khác nhau; signal name chỉ mô tả loại lỗi được phát hiện. `Internal Error` do HotSpot assertion/guarantee có thể có header khác và không nhất thiết chứa một OS signal thông thường.

### 2.2. Dòng `-Xmx512m` không phải chẩn đoán

`-Xmx512m` là cấu hình giới hạn Java heap, không phải tổng native memory của process. Một fatal `SIGSEGV` trong thư viện C/C++ khác với `OutOfMemoryError: Java heap space`. Không tự đề xuất tăng heap khi chưa có bằng chứng về heap pressure hoặc các điều kiện liên quan.

## 3. `Problematic frame`: phân biệt các marker

Đọc chữ hoa và chữ thường chính xác:

| Marker | Mô tả trong HotSpot fatal log | Bước kiểm chứng ưu tiên |
| --- | --- | --- |
| **`C`** | Native code trong thư viện ứng dụng/vendor/JDK/OS | Xác minh module, binary/build, JNI callers, native symbols/core |
| **`V`** | HotSpot VM code, ví dụ runtime, GC, compiler implementation | Xem current thread, `VM_Operation`, `Current CompileTask`, caller và memory corruption |
| **`v`** | VM-generated stub/adapter code | Xem adjacent frames và registers/native transition |
| **`J`** | Compiled Java code, machine code đã sinh bởi JIT | Xác định method/tier và điều kiện tái hiện; kiểm tra JNI/agent trước khi quy JIT bug |
| **`j`** | Interpreted Java method | Không gọi `j` là compiled JIT code; đọc toàn stack/transition |

**Nguyên tắc mạnh nhất:** marker xác định **nơi instruction xảy ra lỗi**, không nhất thiết là **nơi gây hỏng trạng thái**. Ví dụ JNI viết vượt buffer có thể gây crash sau đó ở `V [libjvm.so]` khi GC đọc reference; một bug VM/JIT cũng có thể xảy ra trong compiler runtime. Chỉ từ `C`, `V` hoặc `J` không thể xác nhận root cause.

Ở log mẫu, `C` là điểm khởi đầu hợp lý để điều tra native library, **không phải bản án đã xác nhận thư viện codec có bug**.

## 4. Đọc `Current thread` và stack để nối Java với native

Trong mẫu:

```text
Current thread: JavaThread "decode-io-3" [_thread_in_native, id=7318]

Native frames:
C  [libatlascodec.so+0x13d1] Java_demo_codec_Decoder_decode+0x51
C  [libatlascodec.so+0x1014] codec_unpack+0x24
j  demo.codec.Decoder.decode([B)[B+0
j  demo.service.ImageService.render([B)[B+0
```

Đây là nhóm dấu hiệu cùng nghiêng về **đường gọi giải mã ảnh Java → native codec**:

1. `Current thread` mang tên `decode-io-3` và ở `_thread_in_native`.
2. Hai frame `C` nằm trong cùng native library, gồm một function có tên gợi ý JNI entrypoint.
3. Các frame `j` cho biết Java caller (trong cách ghi frame mẫu).
4. `tid=7318` ở header đồng nhất với native thread ID trong current thread.

Nhưng phải giữ giới hạn:

- Thread state là **ảnh chụp tại thời điểm crash**, không là lịch sử hành động.
- Native frame stack có thể thiếu Java inlined methods; `Java frames` giúp bổ sung Java call chain khi log còn nguyên.
- `Error occurred during error reporting` (nếu có trong log thật) có thể báo error reporter thất bại khi thu stack; không coi phần thiếu là bằng chứng không có caller.
- Lỗi gốc có thể xuất hiện sớm hơn ở một request/thread/library khác và chỉ lộ ra khi codec hoặc VM đụng vùng nhớ đã hỏng.
- Không dùng **Java thread ID** thay **native TID** nếu muốn ghép OS/core; xem PID namespace.

### Những câu hỏi phải đặt tiếp

- `libatlascodec.so` được build từ commit nào và là bản đang **thực sự được nạp**, hay file trên disk đã đổi sau deploy?
- JNI entrypoint `Java_demo_codec_Decoder_decode` nhận buffer/array nào, có kiểm soát độ dài, lifetime, thread attachment, critical sections, local/global refs không?
- Có phụ thuộc input cụ thể, kích thước ảnh, concurrency, release mới hoặc CPU architecture không?
- `si_addr=0x0` tương ứng instruction nào (đọc hay ghi), registers/stack nào và pointer đã null từ đâu?

**Không nên dùng một ảnh chụp stack để viết kết luận “JNI pointer null” khi chưa có instruction và memory evidence.**

## 5. Phân loại ba mức nhận định

Bài thực hành yêu cầu ghi **OBSERVED / INFERRED / UNKNOWN**, không trộn chúng:

| Nhận định | Nhóm | Lý do |
| --- | --- | --- |
| `SIGSEGV`, `pc`, `pid`, `tid` xuất hiện trong header | **OBSERVED** | Dữ liệu trực tiếp trong log mẫu |
| `Problematic frame` là `C` trong `libatlascodec.so` | **OBSERVED** theo `hs_err` | Log xác nhận crash site ở native module |
| `Current thread` ở `_thread_in_native` | **OBSERVED** | Có dòng thread state |
| Java gọi vào native codec ở stack được in | **OBSERVED** theo stack | Có các frame `j` và `C` trong cùng chain |
| Native codec/JNI có thể truy cập pointer invalid | **INFERRED** | Phù hợp `SIGSEGV` và `si_addr=0`, nhưng chưa có core/disassembly |
| Bug chắc chắn nằm trong native codec source | **UNKNOWN** | Chưa loại trừ memory corruption từ caller, agent, JDK hay OS |
| Core `/var/crash/core.7312` tồn tại và đầy đủ | **UNKNOWN** | Chỉ có thông báo dự định ghi core |
| Exact binary và JDK patch level | **UNKNOWN** | Mẫu thiếu hash/build ID/exact vendor |
| Một input giải mã cụ thể có thể tái hiện lỗi | **UNKNOWN** | Chưa có input/trace/test result |
| GC/JIT là root cause hoặc đã được loại trừ hoàn toàn | **UNKNOWN** | Đoạn trích không có chứng cứ đủ để xác nhận hoặc loại trừ tuyệt đối |
| Process bị OOMKilled thay vì `SIGSEGV` | **CHƯA ĐƯỢC CHỨNG MINH** | Cần đối chiếu OS/pod events và đúng incident |

**Mẫu kết luận sơ bộ tốt:**

> Vụ việc được HotSpot ghi nhận là `SIGSEGV` tại mã native trong `libatlascodec.so`, trên JavaThread `decode-io-3` ở `_thread_in_native`. Đường Java→native codec và `si_addr=0x0` làm tăng nghi vấn lỗi pointer/memory lifetime. **Root cause chưa xác nhận**; ưu tiên giữ log/core/binary, lấy JNI code + input và tái hiện có kiểm soát.

Mẫu này phân biệt **đã quan sát** với **đang giả định**, nên vừa có khả năng hành động vừa không báo cáo quá mức.

## 6. Thiết kế phiếu “bằng chứng cần bổ sung”

Không cần thu mọi log có thể nghĩ ra. Mỗi yêu cầu phải có **ưu tiên, nguồn thu, câu hỏi muốn trả lời, điều kiện kết luận**. Với vụ việc đang diễn ra:

- **P0 – bảo toàn ngay:** thứ có thể mất do pod recycle, log rotation, deployment, ephemeral volume, input retention.
- **P1 – xác minh giả thuyết chính:** core/symbols/native source, JVM/GC/JIT context, reproducer và tương quan thời gian.
- **P2 – điều tra sâu nếu P1 chưa giải thích:** controlled A/B giữa JDK/native releases, sanitizer/hardware/OS variation.

| Ưu tiên | Artefact/dữ kiện cần bổ sung | Nguồn thu | Câu hỏi kiểm chứng |
| --- | --- | --- | --- |
| **P0** | **`hs_err_pid7312.log` đầy đủ**, timestamp + checksum | Crash volume/persistent storage | Log có bị cắt, có thiếu stack/process/system hay báo error reporting failed không? |
| **P0** | **Core file thực tế** (nếu được tạo), đường dẫn và hash | OS core handler, `systemd-coredump`, volume | Có registers, native stack, memory mapping đúng lần crash không? |
| **P0** | Stderr/stdout, kernel/cgroup/pod termination event | Container runtime, orchestrator, OS journal | Restart có phải cùng `SIGSEGV`, hay có sự kiện SIGKILL/OOM riêng? |
| **P0** | Image digest, app release, exact JDK vendor/patch/build + flags | Deployment metadata, `hs_err` `VM Arguments` | Có đủ version để ghép binary/bug database không? |
| **P0** | **`libatlascodec.so` đúng bản đã load**, checksum/build ID | Archived container image và binary artifact | Mã native trong log là build nào, có lệch ABI không? |
| **P0** | Request input/trace/operation, trong phạm vi bảo mật | Tracing, request IDs, retained test fixtures | Có dữ liệu đầu vào và cửa sổ thời gian để tái hiện không? |
| **P1** | Native debug symbols, code và symbolized backtrace | Build artifacts, core + debugger | `pc` nằm ở instruction nào, pointer/register nào gây fault? |
| **P1** | JNI declarations/implementation và memory ownership | Native/Java source đúng build | Có buffer overflow, use-after-free, invalid reference, race, ABI mismatch không? |
| **P1** | Full `Native frames`/`Java frames`, registers, `siginfo` | Bản `hs_err` gốc và core | Stack có JNI caller khác, corrupt stack hoặc VM transition không? |
| **P1** | GC logs, JFR, compilation logs **nếu đã được lưu** | Persistent logs/recording | Có hoạt động VM/GC/JIT trước crash làm thay đổi giả thuyết không? |
| **P1** | OS memory/hardware/network và workload/replica pattern | Metrics, host/container events | Lỗi gắn với memory pressure, hardware hoặc concurrency nào? |
| **P1** | Reproducer an toàn với cùng binary/input | Staging/sandbox | Lỗi có xảy ra lại? Thay một biến có đổi tần suất không? |
| **P2** | A/B native codec/JDK version, JVMTI agents | Test matrix có kiểm soát | Narrow down library, JVM, agent interaction, CPU/OS khác? |
| **P2** | Native sanitizers, targeted compiler/GC experiments | Debug test builds | Có đủ evidence để xác nhận memory corruption hay JVM bug không? |

### Tại sao ưu tiên P0 trước?

Core có thể nằm trên ephemeral volume và bị xóa khi pod thay thế; binary mới có thể ghi đè bản crash; log rotation có thể xóa `hs_err`. Một sửa cấu hình không được đối chứng sau khi mất artefact làm root-cause investigation khó hơn.

Nếu **không có core**, báo đúng “core not available”; đừng ghi “core đã chứng minh pointer null”. Nếu **không có symbols**, chỉ xác minh ở cấp module+offset, không bịa dòng source.

## 7. Hướng xử lý an toàn khi đọc file từ vụ crash

Các lệnh dưới đây **chỉ đọc bản sao** của artefact, không tạo crash hay attach vào production JVM. Dùng chúng trên máy/volume đã được cấp quyền:

### 7.1. Đảm bảo đúng file và checksum

```bash
ls -lh hs_err_pid7312.log
sha256sum hs_err_pid7312.log
file hs_err_pid7312.log
```

`sha256sum` giúp nhận biết artefact có thay đổi khi chuyển giữa nhóm; `file` chỉ mô tả loại dữ liệu sơ bộ, không kiểm tra tính đầy đủ của `hs_err`.

### 7.2. Tìm section quan trọng

```bash
grep -n -E 'SIGSEGV|SIGBUS|SIGILL|Internal Error|Problematic frame|Current thread|siginfo|Native frames|Java frames|Current CompileTask|VM_Operation|VM Arguments|Dynamic libraries|error occurred during error reporting' hs_err_pid7312.log
```

Tiếp theo mở **đủ phần liên quan**, ví dụ header và đầu thread:

```bash
sed -n '1,150p' hs_err_pid7312.log
```

`grep` là công cụ định vị, không thay cho đọc context. Không khẳng định “không có `Current CompileTask`” chỉ vì bản trích hoặc `grep` không thấy; với full log, phần này có thể không được ghi hoặc bị hỏng. Một `hs_err` thực tế có thể dài và chứa rất nhiều phần không nằm trong 150 dòng đầu.

### 7.3. Xác minh đúng native binary

Nếu đã có bản binary được giữ từ đúng image:

```bash
sha256sum libatlascodec.so
file libatlascodec.so
readelf -n libatlascodec.so
```

`readelf -n` có thể cung cấp GNU build ID nếu có. Phải so với image/build mà process đã load, **không phải file hiện tại sau deploy**.

Nếu core thực sự tồn tại và có đúng executable/symbols, có thể dùng debugger **offline**:

```bash
gdb -q /path/to/matching/java /path/to/saved/core
```

Trong debugger, các lệnh như `bt`, `info registers`, `info sharedlibrary` và disassembly ở PC giúp kiểm chứng giả thuyết pointer/mapping. `gdb` không thể đảm bảo backtrace đúng nếu core corrupt hoặc binaries/symbols không khớp. Core có thể chứa secrets trong memory; chỉ sử dụng theo quy trình bảo mật.

**Không tự lấy `libatlascodec.so+0x13d1` và dùng một binary khác bản để tuyên bố đó là dòng mã C++ cụ thể**: offset/load bias, ASLR, relocation, stripped symbols và build ID đều quan trọng.

## 8. Vì sao phải tách JVM crash và OS kill?

Nếu một pod bị restart với exit status 137, điều này thường biểu thị `SIGKILL` nhưng **không tự chứng minh OOMKilled**. Cần đối chiếu `memory.events` ở **đúng cgroup**, kernel logs và termination reason. Kernel OOM kill có thể làm process biến mất mà không có `hs_err` vì JVM không có cơ hội xử lý signal.

Nếu có fatal `hs_err` trùng timestamp, signal và PID với incident, đó là bằng chứng của HotSpot fatal-error handling. Tuy nhiên vẫn cần log orchestrator để hiểu thứ tự các sự kiện (fatal trước hay một restart khác sau). Không dùng exit code thay chứng cứ.

Java `OutOfMemoryError: Java heap space` là tình huống JVM không cấp phát được object trên heap; **không tương đương** native `SIGSEGV` trong log mẫu. `-Xmx512m` không chứng minh heap usage thực tế. Heap dump hữu ích cho object graph/OOME, **không thay native core** khi cần registers và pointer.

## 9. Nếu log cho frame `V`, `J` hoặc compiler thread thì sao?

Mẫu chính nghiêng về native `C`. Hãy luyện quy tắc phân loại những trường hợp khác:

| Mẫu dấu hiệu | Crash site an toàn để ghi | Bằng chứng cần bổ sung |
| --- | --- | --- |
| `C [libvendor.so]`, `_thread_in_native`, JNI caller | Native library instruction | Library binary/symbols, core, native source, JNI boundary |
| `C [libnet.so]` thuộc JDK | JDK native library instruction | Exact JDK build/OS/native agents, core, caller chain |
| `V [libjvm.so]`, `VMThread`, `VM_Operation` GC | VM/GC-related code khi crash | GC/safepoint logs, JNI/agent corruption, heap state, core |
| `V [jvm.dll]` nhưng ngay dưới có `C [App.dll]` | VM instruction với native caller | JNI contract/reference validity, native corruption, core |
| `J demo.Foo.work`, `Current thread` là request worker | **Mã Java đã được JIT compile đang chạy** | JDK build, method/tier, native agents, controlled interpreter A/B |
| `V [libjvm.so]`, `C2 CompilerThread`, `Current CompileTask` | **JIT compiler implementation đang biên dịch** | Compile task, compiler flags/log, exact JDK, A/B/reproducer |
| `j demo.Foo.work` | Interpreted Java frame | Toàn stack và top crash PC; `j` không phải JIT compiled |
| `v ~StubRoutines` | VM-generated stub/transition | Liền kề frames, registers, disassembly |
| `Internal Error` / `guarantee(...) failed` | VM tự phát hiện trạng thái nội bộ không hợp lệ | Exact JDK build/source site, flags, current thread, agent/core |
| Không có `hs_err`, OS báo OOM kill | OS/container đã kill process | Cgroup/kernel events, RSS/memory limits, pod termination evidence |

### 9.1. Hai trạng thái JIT khác nhau

**`Problematic frame: J ...` trên application thread**: PC nằm trong machine code đã được JIT tạo, **đang được thực thi**. Một native library có thể làm hỏng memory trước đó; `J` không tự chứng minh JIT compiler sinh mã sai.

**`Problematic frame: V [libjvm]` trên `C2 CompilerThread` và có `Current CompileTask`**: bản thân **compiler code đang chạy để biên dịch** bytecode method. Method trong CompileTask là **đầu vào**, không chứng minh logic ứng dụng sai.

Nếu chỉ thấy `V`, cần xem **current thread**. Nếu chỉ thấy `J`, cần xem **native agents, thread và memory history**. Nếu log bị cắt, không giả định các phần không hiện là không có.

### 9.2. Những phép thử có kiểm soát, không phải phép chữa bách bệnh

Trong test/staging được cấp quyền:

```bash
java -Xcheck:jni -jar app.jar
java -Xint -jar app.jar
java -XX:CompileCommand=exclude,demo/FastHash.hash -jar app.jar
```

- `-Xcheck:jni` giúp phát hiện một số JNI misuse, **không tìm được mọi bug C/C++ native**; có overhead và có thể làm VM dừng khi lỗi nghiêm trọng được phát hiện.
- `-Xint` chạy Java interpreter-only; crash không tái hiện có thể do JIT hoặc do thay đổi scheduling/timing che data race.
- `-XX:CompileCommand=exclude,...` chỉ loại trừ method được chỉ định trong HotSpot; thay đổi hiệu năng, inlining và thời điểm. Chỉ dùng với đúng tên method và JDK flags hỗ trợ.
- Các phép thử thay đổi **một biến mỗi lần**, lặp lại đủ số lần; không gọi workaround là root cause confirmed nếu chưa có evidence.

## 10. Quy trình triage 7 bước cho log mẫu

**Bước 1 — Bảo toàn P0.** Sao lưu toàn bộ fatal log, core nếu có, stderr, pod/kernel events, exact image binary/JDK; đánh dấu timestamp/PID/TID và hash.

**Bước 2 — Viết nhận định quan sát.** Ví dụ `SIGSEGV`, `C` frame trong `libatlascodec.so`, `decode-io-3` ở native, `si_addr=0x0`. Không tự động đặt bug-owner từ một frame.

**Bước 3 — Xác định data gap.** Có core thật không? Binary/debug symbols có khớp không? Request input nào? Native callers và agents? JDK build? Error reporter có ghi đủ hay không?

**Bước 4 — Xếp giả thuyết.** H1: codec invalid pointer/ownership; H2: JNI caller/agent gây corruption; H3: ABI/version mismatch; H4: OS/JDK/hardware interaction. Thứ tự dựa mức gắn trực tiếp với dấu hiệu, **không khẳng định H1 đúng**.

**Bước 5 — Thu P1 đúng mục tiêu.** Symbolize core, đọc JNI/native source, kiểm tra buffer boundaries, references và threading; đối chiếu metrics/GC/JFR và concurrency tại thời điểm crash nếu log đã được lưu.

**Bước 6 — Reproducer cô lập.** Giữ input và binary tương đương, lặp đủ số lần, thay đúng một biến (codec build/agent/JDK patch). Không di chuyển dữ liệu khách hàng ra ngoài môi trường được phép. Một lần không crash không đủ xác nhận fix.

**Bước 7 — Ghi biên bản và owner.** Dùng mẫu `OBSERVED / INFERRED / UNKNOWN / P0 MISSING / P1 NEXT / OWNER / MITIGATION`. Phân biệt “đã giảm crash bằng rollback” với “đã chứng minh nguyên nhân trong source”.

## 11. Ví dụ Java 17: phân loại 4 mẫu frame **không tạo crash**

Chương trình chỉ đọc **log snippets giả lập**, in nhãn phân loại vùng crash; nó không làm JVM gặp fatal error và không phải forensic parser production.

Tạo file **`FatalLogClueLab.java`**:

```java
public final class FatalLogClueLab {
    static String classify(String snippet) {
        char frame = '?';
        boolean nextIsFrame = false;
        boolean compilerThread = false;

        for (String raw : snippet.split("\\R")) {
            String line = raw.trim();
            if (line.startsWith("#")) {
                line = line.substring(1).trim();
            }

            if (line.startsWith("Current thread:")
                    && line.contains("CompilerThread")) {
                compilerThread = true;
            }

            if (line.equals("Problematic frame:")) {
                nextIsFrame = true;
                continue;
            }
            if (nextIsFrame && !line.isBlank()) {
                if (line.length() >= 2
                        && Character.isWhitespace(line.charAt(1))) {
                    frame = line.charAt(0);
                }
                nextIsFrame = false;
            }
        }

        if (frame == 'V' && compilerThread) {
            return "JIT_COMPILER_THREAD_SITE";
        }
        return switch (frame) {
            case 'C' -> "NATIVE_LIBRARY_SITE";
            case 'V' -> "HOTSPOT_VM_SITE";
            case 'v' -> "VM_STUB_SITE";
            case 'J' -> "JIT_COMPILED_EXECUTION_SITE";
            case 'j' -> "INTERPRETED_JAVA_FRAME";
            default -> "UNKNOWN_SITE";
        };
    }

    public static void main(String[] args) {
        String[] names = {
            "native", "vm", "jit-execution", "jit-compiler"
        };
        String[] excerpts = {
            """
            # Problematic frame:
            # C  [libatlascodec.so+0x13d1]
            Current thread: JavaThread "decode-io-3" [_thread_in_native]
            """,
            """
            # Problematic frame:
            # V  [libjvm.so+0x1020]
            Current thread: VMThread
            """,
            """
            # Problematic frame:
            # J 1234 c2 demo.FastHash.mix([B)I
            Current thread: JavaThread "request-9" [_thread_in_Java]
            """,
            """
            # Problematic frame:
            # V  [libjvm.so+0xa321]
            Current thread: JavaThread "C2 CompilerThread0" [_thread_in_vm]
            Current CompileTask: demo.FastHash.mix([B)I
            """
        };

        for (int i = 0; i < excerpts.length; i++) {
            System.out.println(names[i] + " -> " + classify(excerpts[i]));
        }
    }
}
```

Biên dịch và chạy (JDK 17+):

```bash
javac --release 17 FatalLogClueLab.java
java FatalLogClueLab
```

Kết quả stdout **xác định**:

```text
native -> NATIVE_LIBRARY_SITE
vm -> HOTSPOT_VM_SITE
jit-execution -> JIT_COMPILED_EXECUTION_SITE
jit-compiler -> JIT_COMPILER_THREAD_SITE
```

- Nhãn `NATIVE_LIBRARY_SITE` chỉ vị trí native, **không phải xác nhận nguyên nhân của bug**.
- `HOTSPOT_VM_SITE` cần tra tiếp `VM_Operation`/caller.
- `JIT_COMPILED_EXECUTION_SITE` là **mã JIT đã biên dịch đang chạy**, không chứng minh miscompilation.
- `JIT_COMPILER_THREAD_SITE` là compiler implementation đang chạy trên compiler thread, cần `Current CompileTask`/JDK build.

Mã này **chỉ được thiết kế cho 4 snippets kiểm soát**. `hs_err` thật có thể có nhiều layout, lỗi ghi log, thread state thay đổi, debug symbols khác hoặc frame thiếu; không dùng demo để tự động phân loại **root cause** khi xử lý sự cố nghiêm trọng.

## 12. Mẫu báo cáo ngắn của bài thực hành

```text
INCIDENT: demo.ImageServer / PID 7312 / native TID 7318
STATUS: INVESTIGATING
OBSERVED:
- SIGSEGV, pc=0x00007f5a100013d1
- C frame in libatlascodec.so+0x13d1
- current decode-io-3 thread in native state
- si_addr=0x0; Java->native codec frames
INFERRED:
- native/JNI invalid access is plausible
UNKNOWN:
- exact faulting pointer and root cause
- actual core availability, matching symbols, exact binary/JDK build
P0:
- preserve complete hs_err, core, OS events, binary, release and input
P1:
- symbolize core, inspect JNI ownership, isolate reproducer
NEXT:
- confirm artifacts; perform controlled tests in staging
NOT CONFIRMED:
- JNI/vendor bug, JVM bug, JIT bug or a specific source line
```

Đây là **báo cáo minh họa** dành cho dữ kiện giả lập. Trong thực tế, hãy thêm timeline, request trace, owner và các artefact đã được xác nhận; đừng công bố dữ liệu khách hàng hoặc core tùy tiện.

## 13. Các lỗi tư duy phổ biến

1. **“`C` là lỗi chắc chắn của vendor.”** `C` chỉ native crash site; có thể JDK-native/OS library hay corruption xảy ra trước.
2. **“`V` nghĩa là JVM chắc chắn bug.”** JNI/JVMTI có thể làm hỏng memory khiến VM crash muộn.
3. **“`J` là Java source gây SIGSEGV.”** Nó là compiled Java machine code; phải phân biệt miscompilation và corruption.
4. **“`j` nghĩa là JIT.”** Không: `j` chữ thường là interpreted Java frame.
5. **“CompilerThread crash = compiled Java method đang chạy.”** Compiler thread biên dịch, thường có `V`; compiled execution thường ghi `J`.
6. **“`Core dump will be written` đảm bảo core đã được lưu.”** Không: cần kiểm tra filesystem, core handler và quyền.
7. **“`si_addr=0` xác nhận nguồn pointer null.”** Chỉ gợi ý, cần native registers/disassembly/stack.
8. **“Không có `hs_err` thì không có crash.”** SIGKILL, OOM kill hoặc không ghi được log có thể khiến không có fatal log.
9. **“Heap dump thay cho native core.”** Heap dump mô tả Java object graph, không thay được native pointers/registers.
10. **“Bản `libfoo.so` trên host hiện tại là bản đã crash.”** Có thể đã deploy/replace; cần đúng image/binary hash.
11. **“`-Xint` hết crash chứng minh JIT bug.”** Timing/scheduling thay đổi có thể che native race.
12. **“Một test không tái hiện nghĩa là đã fix.”** Race và corruption hiếm cần nhiều lần đối chứng.
13. **“Có thể gửi nguyên core cho đối tác.”** Core/`hs_err` chứa dữ liệu nhạy cảm; phải tuân thủ access/redaction policy.
14. **“Bài điều tra phải chọn một nguyên nhân ngay.”** Triage tốt có thể kết thúc bằng **chưa xác nhận**, kèm bằng chứng còn thiếu và cách thu tiếp.

## 14. Câu hỏi kiểm tra và đáp án

**Câu 1.** `C [libatlascodec.so]` và `_thread_in_native` là bằng chứng gì?  
**Đáp án:** Instruction fault ở native code và current thread đang ở native. Đó là **OBSERVED**, chưa xác nhận bug thuộc source codec.

**Câu 2.** `Core dump will be written` có đủ để báo “đã có core” không?  
**Đáp án:** Không. Phải kiểm tra core file/core handler, kích thước, checksum và đúng PID/time.

**Câu 3.** Từ `si_addr=0` có khẳng định null pointer được truyền trực tiếp từ Java không?  
**Đáp án:** Không. Cần registers/instruction, JNI native code và memory history.

**Câu 4.** Phần nào của log cho biết native library thật sự nạp ở đâu?  
**Đáp án:** `Dynamic libraries`/memory mapping. Tiếp tục xác nhận đúng image hash/build ID.

**Câu 5.** `V [libjvm.so]` và `VMThread` đang thực hiện GC có xác nhận GC bug không?  
**Đáp án:** Chưa. Có thể GC phát hiện heap/reference đã bị JNI/agent làm hỏng; cần core, GC logs và native evidence.

**Câu 6.** `J demo.Hash.run` khác `V` trên `C2 CompilerThread` thế nào?  
**Đáp án:** `J` trên request thread là **đang thực thi compiled code**; `V` trên compiler thread là **đang biên dịch** một method.

**Câu 7.** Pod bị exit 137 nhưng không có `hs_err` nên kết luận OOME?  
**Đáp án:** Không; xác minh termination event, kernel/cgroup OOM counters, memory pressure và process signal.

**Câu 8.** Nếu pod chuẩn bị bị xóa và core nằm trên ephemeral volume, ưu tiên làm gì?  
**Đáp án:** Giữ P0: full log, core, image/binary, OS events và input hợp lệ trước khi mất; sau đó mới phân tích source/reproducer.

**Câu 9.** Làm sao ghi câu kết luận trong incident ticket khi chỉ có snippet này?  
**Đáp án:** Viết **crash site native + giả thuyết pointer/JNI + root cause chưa xác nhận + P0/P1 cần thu**, không gọi vendor/JDK bug đã confirmed.

## 15. Checklist kết thúc

- [ ] Có timestamp, PID/native TID, container/host và exact app/JDK build.
- [ ] Phân biệt JVM fatal error, Java exception và external OS kill.
- [ ] Đọc `Problematic frame` và giải thích đúng `C/V/v/J/j`.
- [ ] Đã đọc `Current thread`, native/Java frames và giới hạn của bản log.
- [ ] Đã xem `VM_Operation` hoặc `Current CompileTask` nếu có dấu hiệu phù hợp.
- [ ] Có bảng **OBSERVED / INFERRED / UNKNOWN**.
- [ ] Có P0 artefact chưa được bảo toàn, đặc biệt log/core/image/binary/input.
- [ ] Có P1 chứng cứ kiểm định, không chỉ tăng log vô mục đích.
- [ ] Không symbolicate từ binary/symbols khác build.
- [ ] Phép thử có kiểm soát, không gây crash cố ý trên production.
- [ ] Phân biệt workaround với root cause đã được xác minh.
- [ ] Đã hạn chế quyền truy cập và xử lý thông tin nhạy cảm trong `hs_err`/core.

## Tài liệu tham khảo

- [Oracle JDK 17 — Troubleshoot System Crashes](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-system-crashes.html): native code, compiled code, HotSpot compiler thread, VMThread và cách chẩn đoán.
- [Oracle JDK 17 — Fatal Error Log](https://docs.oracle.com/en/java/javase/17/troubleshoot/location-fatal-error-log.html): header/frame markers, thread/process/system sections, vị trí file và giới hạn error reporting.
- [Oracle JDK 17 — Prepare Java for Troubleshooting](https://docs.oracle.com/en/java/javase/17/troubleshoot/prepare-java-troubleshooting.html): thu thập core, `hs_err` và logs trước sự cố.
- [Oracle JDK 17 — Submit a Bug Report](https://docs.oracle.com/en/java/javase/17/troubleshoot/submit-bug-report.html): thông tin/coredump/log và reproducer nên có khi báo lỗi.
- [Oracle JDK 17 — `java` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-XX:ErrorFile`, `-Xcheck:jni`, `-Xint` và `-XX:CompileCommand`.
