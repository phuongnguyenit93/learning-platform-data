# 20.3 Đọc header lỗi, problematic frame, current thread và danh sách thư viện

## Mục tiêu bài học

Khi HotSpot/OpenJDK gặp lỗi nghiêm trọng khiến JVM không thể tiếp tục, runtime thường cố ghi tệp `hs_err_pid<PID>.log`. Bốn phần quan trọng nhất để **khoanh vùng crash** là:

1. **Header lỗi:** signal hoặc exception, `pc`, `pid`, `tid`, JRE/JVM build và nền tảng.
2. **Problematic frame:** mã đang thực thi tại điểm phát hiện lỗi, loại frame và module/offset.
3. **Current thread:** thread JVM/OS gắn với fatal error, trạng thái và native/Java stack.
4. **Danh sách thư viện:** các thư viện native đã nạp, đường dẫn binary và memory mapping, giúp xác định đúng phiên bản module.

Sau bài này bạn có thể đọc bốn phần theo đúng thứ tự, phân biệt các ký hiệu frame `C`/`V`/`v`/`J`/`j`, nối địa chỉ lệnh với library, lập giả thuyết và ghi rõ giới hạn bằng chứng. Nội dung dùng HotSpot/OpenJDK Java 17+; ví dụ Java đã chạy kiểm chứng ở JDK 24. Cấu trúc báo cáo có thể khác theo hệ điều hành, phiên bản và tình trạng crash; log đôi khi bị cắt dở.

**Nguyên tắc:** `Problematic frame` cho biết *nơi lỗi biểu hiện*, không tự chứng minh *nguyên nhân gốc*. Native code có thể làm hỏng memory từ trước, rồi JVM mới phát hiện vấn đề trong một frame khác.

## 1. Phân biệt fatal crash với exception Java và OS kill

| Hiện tượng | Đặc trưng | Bằng chứng nên tìm |
| --- | --- | --- |
| `NullPointerException` hoặc `IllegalArgumentException` | Exception bình thường từ mã Java, có thể được catch | Application stack trace/log |
| `OutOfMemoryError: Java heap space` | Lỗi bộ nhớ Java có thể tạo Throwable; không tự động là fatal native crash | GC/heap/log; chưa chắc có `hs_err` |
| `SIGSEGV`, `SIGBUS`, `SIGILL` | Signal nghiêm trọng trên Unix khi VM/native code không thể tiếp tục | `hs_err`, core dump, OS logs |
| `EXCEPTION_ACCESS_VIOLATION` | Lỗi truy cập bộ nhớ theo cơ chế Windows | `hs_err`, dump nếu có |
| `Internal Error`, VM assertion/`guarantee` | Runtime phát hiện invariant bị vi phạm | Header, VM thread/stack, JVM build |
| Container `OOMKilled`, OS `SIGKILL` | Process bị kernel/orchestrator kết thúc ngoài JVM | cgroup/OS/pod events; có thể **không có `hs_err`** |

Không có `hs_err` **không đồng nghĩa** không crash. Trong một lỗi nặng, error handler có thể không ghi được hết file; lỗi quyền ghi, disk đầy hoặc bị kill cứng cũng có thể khiến file không tồn tại. Một Java exception thông thường không thể tự diễn giải thành native segmentation fault.

Khác biệt cần giữ:

- **Crash site:** instruction/PC đang được thực thi khi OS/VM phát hiện fatal error.
- **Fault address:** vị trí bộ nhớ liên quan thao tác truy cập gây fault (nếu log cung cấp), không nhất thiết bằng PC.
- **Root cause:** bug/dữ liệu/môi trường đã tạo ra tình trạng lỗi; có thể nằm ở thread khác, thư viện khác hoặc xảy ra sớm hơn.

## 2. Tìm và bảo quản báo cáo đúng cách

Một tên mặc định thường gặp là `hs_err_pid4242.log`. HotSpot thường thử ghi tại working directory, có thể thử thư mục tạm khi không ghi được; file thực tế được thông báo trên console nếu quá trình logging đủ hoàn chỉnh. Có thể đặt đường dẫn trước khi khởi động:

```bash
java -XX:ErrorFile=/var/log/myapp/hs_err_pid%p.log -jar app.jar
```

`%p` đại diện PID theo cú pháp HotSpot; đường dẫn và `app.jar` chỉ là ví dụ. Thư mục phải tồn tại, ghi được và có đủ dung lượng. Lỗi này không phải một sự kiện có thể bắt an toàn bằng `try/catch` của ứng dụng để đổi path sau crash.

Ngay khi có sự cố, ghi **timestamp**, host/pod/container, PID, JDK vendor/build, đường dẫn file, kích thước và checksum. Sao lưu log gốc cùng core/crash dump khi được phép; không ghi đè file khi chạy lại. Nhiều crash trên các lần khởi động có thể trùng PID, nên đừng dựa vào basename để phân biệt.

`hs_err` có thể chứa command-line arguments, environment variables, file paths, usernames, network addresses, đôi khi cả chuỗi nhạy cảm trong dump. Chỉ chia sẻ bản sao được redaction; giữ bản gốc ở nơi có quyền truy cập phù hợp.

### Xem nhanh bốn vùng

Linux/macOS (thay tên file thật):

```bash
sed -n '1,90p' hs_err_pid4242.log
grep -nE 'Problematic frame:|Current thread|Native frames:|Java frames:|Dynamic libraries:' hs_err_pid4242.log
```

Windows PowerShell:

```powershell
Select-String -Path '.\hs_err_pid4242.log' -Pattern 'Problematic frame:','Current thread','Native frames:','Java frames:','Dynamic libraries:'
```

Lệnh chỉ tìm vị trí. Phải đọc các dòng xung quanh nhãn và kết hợp các vùng, không chỉ trích một dòng có symbol đáng nghi.

## 3. Mẫu log giả lập để học cách đọc

Đây là **dữ liệu mô phỏng**, không phải log thật; PID, địa chỉ, thư viện và hàm đều chỉ minh họa.

```text
# A fatal error has been detected by the Java Runtime Environment:
#
#  SIGSEGV (0xb) at pc=0x00007f00001002a4, pid=4242, tid=4249
#
# JRE version: OpenJDK Runtime Environment (21.0.5+11)
# Java VM: OpenJDK 64-Bit Server VM (21.0.5+11, linux-amd64)
# Problematic frame:
# C  [libsamplecodec.so+0x2a4]  decode_image+0x24
#
---------------  T H R E A D  ---------------
Current thread (0x00007f0000001000): JavaThread "decoder-worker" [_thread_in_native, id=4249]
Native frames:
C  [libsamplecodec.so+0x2a4]  decode_image+0x24
j  example.Decoder.run()V+12

Dynamic libraries:
0x00007f0000100000-0x00007f0000120000 /opt/app/lib/libsamplecodec.so
0x00007f0000200000-0x00007f0000300000 /usr/lib/libc.so.6

VM Arguments:
```

Đọc từng vùng:

- Header: `SIGSEGV` trong process `pid=4242`, native thread `tid=4249`, tại program counter `pc=0x00007f00001002a4`.
- Problematic frame: `C` cho native code, module `libsamplecodec.so` tại offset `0x2a4`, symbol `decode_image+0x24`.
- Current thread: `JavaThread "decoder-worker"` đang ở `_thread_in_native` và mang native ID `4249`. Native stack nhắc lại `libsamplecodec.so`; Java caller giúp tìm nghiệp vụ đã gọi native.
- Libraries: `/opt/app/lib/libsamplecodec.so` đã nạp tại dải địa chỉ bao phủ PC. Đường dẫn thực gợi ý binary ứng dụng đang dùng, không phải chỉ tên file có thể trùng nơi khác.

**Kết luận tạm thời đúng:** ưu tiên điều tra native codec, JNI/FFM boundary, lifetime của buffer, binary build và input khi crash. **Kết luận quá mức:** “đã xác nhận một bug ở `decode_image`” — chưa đủ, vì memory corruption có thể phát sinh trước.

## 4. Đọc header lỗi một cách có hệ thống

### Signal/exception nói gì?

| Header field | Nghĩa ban đầu | Cần tránh |
| --- | --- | --- |
| `SIGSEGV` | OS báo truy cập bộ nhớ không hợp lệ hoặc protection violation | Không tự chứng minh null pointer hoặc thư viện cụ thể gây corruption |
| `SIGBUS` | Lỗi truy cập bus/memory mapping theo nền tảng | Không mặc định do hỏng phần cứng |
| `SIGILL` | Instruction không hợp lệ trong ngữ cảnh thực thi | Không mặc định “JIT bug” |
| `SIGABRT` | Tiến trình bị abort, có thể do assertion/VM/native code chủ động gọi abort | Không mặc định libc là root cause |
| `EXCEPTION_ACCESS_VIOLATION` | Access violation trên Windows | Xem exception parameters, frame, stack, dump |
| `Internal Error`/`assert`/`guarantee` | HotSpot nhận thấy invariant thất bại | Phải tìm assertion detail và thread/operation cụ thể |
| `pc=0x...` | Địa chỉ instruction đang gây ra lỗi/được báo | Không phải chắc chắn địa chỉ dữ liệu lỗi |
| `pid=...` | Process identifier | Không phải Java thread ID |
| `tid=...` | Native/OS thread identifier | Không nhất thiết bằng Java `Thread.getId()` |
| `JRE version` | Runtime distribution/version/build | Không đủ để định danh mọi native library |
| `Java VM` | VM build, mode, OS, architecture, flags (tùy format) | Không tự xác định root cause |

Ví dụ:

```text
#  SIGSEGV (0xb) at pc=0x00007f00001002a4, pid=4242, tid=4249
```

Đây là **bản tóm tắt fault**, không phải báo cáo ai đã làm hỏng bộ nhớ. Nếu log có `siginfo`, `si_addr` hay exception code và fault address, đọc riêng: **PC là địa chỉ lệnh, fault address có thể là địa chỉ dữ liệu**. Không được coi hai trường là một.

Ghi lại vendor, JDK update/build, architecture, JVM flags, thời điểm crash và OS/container. Một vấn đề chỉ có ở JDK build hoặc CPU architecture cụ thể sẽ khó tái hiện nếu báo cáo chỉ nói “Java 21”.

### SIGABRT và VM internal error

`SIGABRT` có thể xuất hiện khi JVM hoặc native library cố ý gọi abort vì đã phát hiện trạng thái không hợp lệ. Khi problematic frame thuộc `abort`/`raise` của libc, phải xem **assertion/internal error text và caller stack**; điểm dừng cuối tại libc không chứng minh lỗi nằm trong libc.

## 5. Problematic frame: đọc ký hiệu, module và offset

Đây thường là dòng đáng chú ý nhất ở phần đầu:

```text
# Problematic frame:
# C  [libsamplecodec.so+0x2a4]  decode_image+0x24
```

| Marker | Loại frame HotSpot | Cách đặt giả thuyết |
| --- | --- | --- |
| `C` | Native C/C++ code | JNI/JNA/FFM/native module, driver, ABI hoặc dữ liệu đầu vào |
| `V` | VM frame | HotSpot runtime/GC/JIT/VM operation; vẫn cần loại trừ memory corruption ngoài VM |
| `v` | VM-generated stub | Code stub/chuyển tiếp runtime/compiled ↔ native |
| `J` | Compiled Java code | Method đã JIT compile, machine code/optimization state |
| `j` | Interpreted Java frame | Bytecode method đang chạy bằng interpreter |

Các dấu và format có thể khác theo JVM/version, thậm chí thiếu symbol. Dùng bảng trên làm **hướng phân loại**, không là phán quyết.

Dòng `C` cho biết PC thuộc native code; `[libsamplecodec.so+0x2a4]` ghi module và offset; `decode_image+0x24` là symbol/offset nếu được biết. Khi binary bị strip, có thể chỉ còn module+offset. **Bắt buộc đối chiếu binary chính xác của lần crash** nếu muốn symbolicate; cùng basename nhưng khác build dẫn đến lời giải mã sai.

### Đối chiếu các trường hợp khác

```text
# V  [libjvm.so+0x123abc]  SomeVMFunction+0x20
# J 1234 c2 example.Parser.parse([B)I (146 bytes) @ 0x00007f...
```

Hai dòng này là **hai dạng frame giả định khác nhau**, không phải hai dòng bắt buộc của cùng crash. Với `V` trong `libjvm.so`, điều tra VM operation, GC/compiler thread, JDK build, core và khả năng native memory corruption xảy ra trước đó. Với `J`, lưu method/compilation info và xem các crash lặp lại; chưa đủ để kết luận JVM compiler bug.

Những kết luận vội phải tránh:

- “`libjvm.so` xuất hiện ⇒ JVM chắc chắn sai.”
- “`libc.so` xuất hiện ⇒ OS chắc chắn sai.”
- “`J` xuất hiện ⇒ một `NullPointerException` của Java làm JVM crash.”
- “Tên vendor library xuất hiện ⇒ vendor đó chắc chắn gây ra lỗi.”
- “Có offset giống lần trước ⇒ cùng root cause” khi build/JDK/ASLR chưa được đối chiếu.

**Vị trí lỗi ≠ nguồn gốc hỏng bộ nhớ.** Dangling pointer, use-after-free, buffer overflow hoặc race từ earlier native operation có thể biểu hiện muộn ở một module khác.

## 6. Current thread: thread nào đang gây fatal error?

Ví dụ từ mẫu:

```text
Current thread (0x00007f0000001000): JavaThread "decoder-worker" [_thread_in_native, id=4249]
```

| Phần | Ý nghĩa |
| --- | --- |
| `0x00007f...` | Con trỏ tới cấu trúc thread nội bộ HotSpot, hữu ích khi debug sâu |
| `JavaThread` | Loại thread JVM; không nhất thiết là thread duy nhất trong process |
| `"decoder-worker"` | Tên Java thread ghi tại thời điểm crash |
| `_thread_in_native` | Thread đang trong vùng native execution/transition phù hợp |
| `id=4249` | OS/native thread ID; đối chiếu `tid` ở header khi có |
| `stack(...)` nếu có | Dải memory stack và kích thước vùng stack để chẩn đoán |

Các trạng thái thường gặp: `_thread_in_Java`, `_thread_in_native`, `_thread_in_vm`, `_thread_blocked`, hậu tố `_trans` cho trạng thái chuyển tiếp. **Thread state là ngữ cảnh, không phải nguyên nhân.**

Current thread có thể là `CompilerThread`, `VMThread` hoặc GC worker chứ không phải một request handler. Nếu là compiler thread, tìm `Current CompileTask`; nếu là VM thread, tìm VM operation/GC phase. Không coi thiếu tên endpoint là bằng chứng thiếu thread.

### Đọc stack theo hai lớp

```text
Native frames:
C  [libsamplecodec.so+0x2a4]  decode_image+0x24
j  example.Decoder.run()V+12

Java frames:
j  example.Decoder.run()V+12
j  example.Decoder.main([Ljava/lang/String;)V+7
```

Native frames đưa ra call path nhìn từ native/VM stack (vẫn có thể có frame Java); Java frames giúp tìm Java call chain và đôi khi các method được inline. Stack có thể thiếu hoặc lỗi unwind do chính crash/corruption.

Đọc theo thứ tự:

1. Top native frame có khớp problematic frame?
2. Các caller ngay dưới là JNI bridge, native lib, VM, hay Java method?
3. State `_thread_in_native` có nhất quán với `C` frame?
4. Java caller biểu thị nghiệp vụ nào; input và buffer được truyền qua bridge ra sao?
5. Có dấu hiệu recursion/stack exhaustion, crash ở compiler/GC thread hoặc stack corrupted không?
6. Có nhiều crash cùng top symbol và cùng workload không?

**Current thread ≠ mọi thread của JVM.** Phần `Java Threads`/`Other Threads` trong hs_err có thể liệt kê các thread khác; ký hiệu `=>` trong thread list đánh dấu thread hiện tại. Thread phát hiện crash chưa chắc là thread ban đầu đã ghi hỏng memory.

## 7. Danh sách thư viện: tìm đúng binary, không chỉ basename

Ví dụ:

```text
Dynamic libraries:
0x00007f0000100000-0x00007f0000120000 /opt/app/lib/libsamplecodec.so
0x00007f0000200000-0x00007f0000300000 /usr/lib/libc.so.6
```

Phần này (tên section/format có thể khác) giúp tìm:

- **Đường dẫn module** thực tế: `/opt/app/lib/libsamplecodec.so`, `C:\app\bin\codec.dll` hoặc `.dylib` trên macOS.
- **Memory mapping range** của module khi log có. Mẫu `pc=0x00007f00001002a4` nằm trong range của codec.
- **Chủ sở hữu binary**: app tự cung cấp, dependency JNI/JNA/FFM, thư viện hệ thống hay JVM runtime.
- **Build ID/checksum/version**: phải lấy từ artifact thực tế; đừng suy phiên bản từ basename hoặc source tree hiện tại.
- **Kiến trúc và ABI**: x86-64 vs AArch64, 32/64-bit, compiler/libc/driver compatibility, dependencies.

Trong mẫu, PC trừ base giả định cho `0x2a4`. Trên binary thực, cần xem load bias, ASLR, segment mapping và symbol information trước khi coi kết quả đó là chính xác file offset. Địa chỉ tuyệt đối của hai crash có thể khác dù cùng bug; khi gom nhóm nên dùng **library path/build ID + relative offset/symbol + signal**, kèm stack.

**Thư viện loaded không có nghĩa đã thực thi tại thời điểm crash; đã thực thi không tự đồng nghĩa nó tạo ra nguyên nhân gốc.** Danh sách có thể thiếu do log ghi dở. Nếu tên module trong problematic frame khác đường dẫn trong library list, kiểm tra mapping, symlink, multiple copies và build chính xác.

Khi có core/crash dump và debug symbols, debugger phù hợp (gdb/lldb/WinDbg) có thể xác định instruction, register, call stack và pointer. Dùng binary/symbols **cùng build**; symbols sai build sẽ đưa ra method/source line sai.

## 8. Ghép bốn vùng thành giả thuyết, không phán đoán từ một dấu

| Tổ hợp tín hiệu | Giả thuyết ưu tiên | Điều còn thiếu |
| --- | --- | --- |
| `SIGSEGV` + `C` module ứng dụng + `_thread_in_native` | Điều tra native pointer/buffer ownership, ABI, JNI contract | Core/symbols, input, nguồn tạo corruption |
| `SIGABRT` + libc `abort`/`raise` | Có thể xảy ra assertion/chủ động abort | Assertion text và caller stack, không đổ lỗi libc |
| `V` `libjvm.so` + `VMThread`/GC worker | VM/GC state hoặc corruption biểu hiện tại JVM | JVM build, logs, core, native code liên quan |
| `J` compiled Java | JIT-compiled instruction hoặc state bị hỏng | Reproduction, compiled method info, JVM/runtime khác |
| `CompilerThread` + `Current CompileTask` | Điều tra đường biên dịch method và compiler state | JDK build, reproducer, native corruption bên ngoài |
| `C` tại JNI lib + native/Java stack nhất quán | Khoanh vùng native boundary có cơ sở | Kiểm tra symbol đúng build và lifetime của dữ liệu |
| Header có lỗi nhưng danh sách thư viện không có | Có thể log incomplete/format khác | Core/OS logs; không suy chắc không load |
| Không có hs_err, pod OOMKilled | OS/cgroup kill khác fatal VM crash | Kernel/container events, memory metrics |

### Case A: thư viện native gây nghi ngờ

Header `SIGSEGV`, problematic frame `C [libcodec.so+offset]`, current thread `JavaThread "image-worker" [_thread_in_native]` và full path của codec trong mapping: ưu tiên kiểm tra native decode, input bytes, ownership và phiên bản lib. Tuy nhiên có thể vùng nhớ bị hỏng từ một thư viện khác; kết luận chỉ là **nghi vấn ưu tiên**.

### Case B: abort/assert trong VM

Header báo `Internal Error` hoặc `SIGABRT`, problematic frame nằm trong VM hoặc libc abort, current thread là compiler thread. Hãy tìm **assertion message**, compiler task, Java VM build và stack phía dưới. Đừng kết luận “libc bug” hoặc “compiler bug” trước khi có reproduction/cùng binary và loại trừ memory corruption từ native code khác.

### Case C: Java compiled frame xuất hiện

Một frame `J` trong hot method có thể dẫn đến giả thuyết compiler/runtime hoặc dữ liệu bị hỏng. Nhưng Java exceptions thông thường không làm process segmentation fault; cần đối chiếu native memory/JNI/Unsafe/FFM nếu app có dùng, rồi kiểm chứng bằng core/symbols và nhiều lần tái hiện.

## 9. Thực hành Java 17+: đọc một log giả lập mà không gây crash

Chương trình sau đọc một chuỗi `hs_err` **giả lập** rồi in các vùng thông tin. Nó có thể nhận file ngoài làm đối số, nhưng là **parser minh họa**, không hỗ trợ mọi format `hs_err`: section headers có thể khác, một file fatal có thể hỏng/thiếu, tên exception khác hoặc danh sách thư viện trình bày cách khác. Với incident thật phải kiểm tra file gốc.

```java
// File: HsErrFourZonesDemo.java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class HsErrFourZonesDemo {
    private static final String SAMPLE = """
            # A fatal error has been detected by the Java Runtime Environment:
            #
            #  SIGSEGV (0xb) at pc=0x00007f00001002a4, pid=4242, tid=4249
            #
            # JRE version: OpenJDK Runtime Environment (21.0.5+11)
            # Java VM: OpenJDK 64-Bit Server VM (21.0.5+11, linux-amd64)
            # Problematic frame:
            # C  [libsamplecodec.so+0x2a4]  decode_image+0x24
            #
            ---------------  T H R E A D  ---------------
            Current thread (0x00007f0000001000): JavaThread "decoder-worker" [_thread_in_native, id=4249]
            Native frames:
            C  [libsamplecodec.so+0x2a4]  decode_image+0x24
            j  example.Decoder.run()V+12

            Dynamic libraries:
            0x00007f0000100000-0x00007f0000120000 /opt/app/lib/libsamplecodec.so
            0x00007f0000200000-0x00007f0000300000 /usr/lib/libc.so.6

            VM Arguments:
            """;

    private static String unprefix(String line) {
        return line.replaceFirst("^#\\s*", "").trim();
    }

    public static void main(String[] args) throws Exception {
        if (args.length > 1) {
            throw new IllegalArgumentException("Use zero args or one log path");
        }
        String content = args.length == 0 ? SAMPLE : Files.readString(Path.of(args[0]));
        String signal = "(not found)";
        String jre = "(not found)";
        String vm = "(not found)";
        String frame = "(not found)";
        String thread = "(not found)";
        boolean expectFrame = false;
        boolean inLibraries = false;
        List<String> libraries = new ArrayList<>();

        for (String raw : content.split("\\R")) {
            String line = raw.trim();
            if (line.startsWith("#  SIG") ||
                    line.startsWith("#  EXCEPTION_")) {
                signal = unprefix(line);
            }
            if (line.startsWith("# JRE version:")) {
                jre = unprefix(line);
            }
            if (line.startsWith("# Java VM:")) {
                vm = unprefix(line);
            }
            if (line.equals("# Problematic frame:")) {
                expectFrame = true;
                continue;
            }
            if (expectFrame && line.startsWith("#") && !line.equals("#")) {
                frame = unprefix(line);
                expectFrame = false;
            }
            if (line.startsWith("Current thread (")) {
                thread = line;
            }
            if (line.equals("Dynamic libraries:")) {
                inLibraries = true;
                continue;
            }
            if (inLibraries) {
                if (line.isEmpty() || line.endsWith("Arguments:")) {
                    inLibraries = false;
                } else if (line.contains("/") || line.contains("\\")) {
                    libraries.add(line);
                }
            }
        }
        System.out.println("signal=" + signal);
        System.out.println("jre=" + jre);
        System.out.println("vm=" + vm);
        System.out.println("frame=" + frame);
        System.out.println("thread=" + thread);
        System.out.println("libraries=" + libraries.size());
        for (String lib : libraries) {
            System.out.println("library=" + lib);
        }
    }
}
```

Lưu tên file **`HsErrFourZonesDemo.java`** và chạy bằng JDK 17+:

```bash
javac HsErrFourZonesDemo.java
java HsErrFourZonesDemo

# Tùy chọn: thử với file log có sẵn
java HsErrFourZonesDemo hs_err_pid4242.log
```

**Stdout khi không có đối số** đã được biên dịch/chạy kiểm chứng trên OpenJDK 24:

```text
signal=SIGSEGV (0xb) at pc=0x00007f00001002a4, pid=4242, tid=4249
jre=JRE version: OpenJDK Runtime Environment (21.0.5+11)
vm=Java VM: OpenJDK 64-Bit Server VM (21.0.5+11, linux-amd64)
frame=C  [libsamplecodec.so+0x2a4]  decode_image+0x24
thread=Current thread (0x00007f0000001000): JavaThread "decoder-worker" [_thread_in_native, id=4249]
libraries=2
library=0x00007f0000100000-0x00007f0000120000 /opt/app/lib/libsamplecodec.so
library=0x00007f0000200000-0x00007f0000300000 /usr/lib/libc.so.6
```

Đầu ra `libraries=2` nghĩa là **hai dòng mapping trong ví dụ**, không có nghĩa mọi `hs_err` có hai thư viện. Parser tìm nhãn đơn giản và đọc toàn bộ file vào RAM (`Files.readString`), nên không phù hợp file rất lớn hoặc định dạng thay đổi; không sử dụng kết quả nó trả về như bằng chứng pháp y độc lập. Ví dụ **không** dùng JNI và **không** gây crash thực sự.

Điều người học cần rút ra: thông tin từ bốn vùng giúp xây một **giả thuyết có thể điều tra**; các trường được trích đúng không tự động chứng minh nguyên nhân gốc.

## 10. Runbook xử lý crash và báo cáo có trách nhiệm

**Bước 1 — Chốt artifact:** ghi đường dẫn `hs_err`, timestamp, checksum, size, PID, JVM build; lưu bản gốc an toàn. Kiểm tra file có thiếu phần cuối do crash nặng không.

**Bước 2 — Đọc header:** ghi loại signal/exception, PC, PID, TID, Java VM version, architecture. Nếu `SIGABRT`/internal assertion, đọc thêm thông báo assertion.

**Bước 3 — Đọc frame:** sao nguyên văn loại C/V/v/J/j, module, symbol và offset. Không gán thủ phạm chỉ vì thư viện chứa PC.

**Bước 4 — Đọc current thread:** thread type/name/state/OS ID, native stack, Java frames, JVM compile task hoặc VM operation nếu có. Không nhầm Java thread ID với native tid.

**Bước 5 — Kiểm tra libraries:** full path và mapping của module liên quan, phiên bản/build ID từ binary triển khai; đối chiếu OS/architecture/JDK.

**Bước 6 — Tập hợp bối cảnh:** deployment gần nhất, JNI/FFM/JNA/Unsafe, driver/native libraries, OS/core dump, cgroup OOM events, lặp lại hay ngẫu nhiên. Không chạy `jcmd` trên PID đã chết.

**Bước 7 — Lập giả thuyết, thử an toàn:** chọn 1–3 giả thuyết; nêu bằng chứng ủng hộ/chống và phép kiểm chứng trong môi trường kiểm thử, không cố làm crash production.

**Bước 8 — Báo kết luận có mức tin cậy:** “đã khoanh vùng”, “nghi mạnh”, hoặc “đã xác nhận” chỉ khi có đủ core/symbols, reproduction và/hoặc fix/rollback được đo kiểm.

### Mẫu báo cáo

```text
Incident: thời gian, host/container/pod, PID và file hs_err gốc.
Header: signal/exception, pc, tid, JVM vendor/version/build, architecture.
Problematic frame: loại C/V/v/J/j, module, symbol và offset.
Current thread: type, name, state, native ID và 3-5 frames đầu.
Libraries: full path + mapping; binary version/build ID/checksum.
Related evidence: application/OS logs, core, JDK/native deployment changes.
Hypotheses: nguyên nhân khả dĩ và bằng chứng ủng hộ/chưa loại trừ.
Next action: thử nghiệm, artifact cần lấy và người phụ trách.
Confidence: preliminary / likely / confirmed và lý do.
```

### Checklist trước khi kết luận

- [ ] Đã phân biệt Java exception, fatal JVM crash và OS/cgroup kill.
- [ ] Có đúng file, thời điểm, PID, JVM build và bằng chứng file hoàn chỉnh hay bị cắt.
- [ ] Đã đọc `pc` như instruction pointer, không nhầm với fault data address.
- [ ] Đã phân loại problematic frame C/V/v/J/j và giữ nguyên module+offset.
- [ ] Đã đọc current thread/native TID, trạng thái, native stack và Java stack.
- [ ] Đã phân biệt stack của crash thread với các threads khác.
- [ ] Đã tìm full path/library mapping và binary build tương ứng.
- [ ] Không đồng nhất “loaded library” với “bug owner”.
- [ ] Đã bảo quản/redact dữ liệu nhạy cảm trước khi chia sẻ.
- [ ] Đã xác định bằng chứng cần thêm để nâng kết luận từ giả thuyết lên xác nhận.

### Câu hỏi tự kiểm tra

1. `Problematic frame: C [libcodec.so+...]` chứng minh bug ở codec? **Chưa.** Chỉ xác nhận instruction của module tại crash site; corruption có thể xảy ra trước.
2. `SIGABRT` và top frame `abort` trong libc nghĩa libc lỗi? **Chưa.** Cần tìm nguyên nhân code/JVM gọi abort.
3. `tid` có bằng `Thread.getId()` không? **Không được mặc định.** Một bên là OS/native thread ID, bên kia là Java ID.
4. Vì sao phải đọc danh sách dynamic libraries? **Tìm đúng binary/path/mapping**, tránh nhầm nhiều file cùng tên.
5. Frame `V` trong `libjvm.so` đủ kết luận JVM bug? **Chưa.** Cần đúng build, thread context, core và loại trừ corruption từ nơi khác.
6. Nếu pod bị OOMKilled và không có `hs_err`, được gọi segfault không? **Không.** Đó là bằng chứng OS/cgroup kill, cần điều tra theo hướng phù hợp.

**Kết luận:** Header trả lời **crash gì, ở tiến trình/thread nào**; problematic frame cho **lệnh/module phát hiện lỗi**; current thread và stack cho **ngữ cảnh thực thi**; danh sách thư viện cho **binary thực tế và mapping**. Chỉ sau khi kết hợp các vùng này với artifact, core, deployment history và phép tái hiện mới có thể nói về nguyên nhân gốc với mức tin cậy cao.

## Tài liệu tham khảo

- OpenJDK/Java Operations — *How to Find and Interpret the Java HotSpot Fatal Error Log*: https://ops.java/troubleshooting/articles/fatal-error-log/
- Oracle JDK 21 — *Troubleshooting Guide*: https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-guide.pdf
- Oracle JDK 22 — *Troubleshoot System Crashes*: https://docs.oracle.com/en/java/javase/22/troubleshoot/troubleshoot-system-crashes.html
- Oracle JDK 24 — *Fatal Error Log*: https://docs.oracle.com/en/java/javase/24/troubleshoot/location-fatal-error-log.html
