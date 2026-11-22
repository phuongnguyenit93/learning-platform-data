# Đọc `hs_err_pid`, khung gây lỗi và dấu vết ngăn xếp Java hoặc bản địa

Khi Java HotSpot gặp một **fatal error** (lỗi nghiêm trọng làm JVM không thể tiếp tục an toàn), JVM cố gắng tạo báo cáo văn bản thường có tên `hs_err_pid<PID>.log`. Khác với stack trace của Java `Exception` thông thường, báo cáo này có thể ghi **signal/lỗi hệ điều hành, program counter (`pc`), khung lệnh đang gặp lỗi (`Problematic frame`), luồng hiện hành, chuỗi stack Java/native, trạng thái JVM, danh sách thư viện và thông tin hệ thống**. Tài liệu giúp xác định JVM gặp lỗi tại đâu, đi qua ranh giới Java ↔ JNI/Foreign Function & Memory API (FFM) như thế nào, và cần bằng chứng nào để tìm ra nguyên nhân gốc.

**Mục tiêu:** biết tìm đúng log, đọc header và `Problematic frame`, giải mã frame `C/j/J/V/v`, ghép `Native frames` với `Java frames` của đúng thread, phân biệt vị trí phát hiện lỗi với nguyên nhân, và chọn bước điều tra tiếp theo.

## 1. Khi nào có `hs_err_pid` và khi nào không?

Báo cáo được HotSpot ghi khi fatal error handler có cơ hội chạy, ví dụ process gặp `SIGSEGV` trên Linux, `EXCEPTION_ACCESS_VIOLATION` trên Windows, `SIGBUS`/`SIGILL` trong một số tình huống, hoặc JVM phát hiện `Internal Error`. Có thể do native code/JNI/FFM truy cập bộ nhớ không hợp lệ, driver/thư viện hệ thống, JVM/JIT/GC hoặc ảnh hưởng từ memory corruption xuất hiện trước đó.

| Hiện tượng | Có mặc định sinh `hs_err_pid`? | Nguồn bằng chứng phù hợp |
| --- | --- | --- |
| `NullPointerException`, `IOException`, một Java exception thông thường | Không | Application log và Java exception stack trace |
| `OutOfMemoryError` thường gặp ở Java heap | Không bắt buộc | Application log; heap dump nếu bật `-XX:+HeapDumpOnOutOfMemoryError` |
| JVM gặp lỗi native nghiêm trọng và crash handler chạy | HotSpot cố gắng tạo log, không bảo đảm hoàn chỉnh | `hs_err_pid`, stderr, core/minidump nếu có |
| Linux OOM killer gửi `SIGKILL`, container bị cưỡng bức dừng | Thường không: không có cơ hội chạy handler | Kernel/container/pod events, OOMKilled/exit status |
| JVM dừng hợp lệ, `System.exit` | Không | Application logs và exit status |

`hs_err_pid` là **ảnh chụp tại lúc lỗi được phát hiện**, không phải lịch sử đầy đủ trước đó. Nếu stack hoặc heap hỏng nghiêm trọng, HotSpot chỉ ghi được một phần hoặc báo `error occurred during error reporting`. Vì thế “không có log” hay “không có stack” chưa loại trừ được một lỗi native.

## 2. Tìm đúng file và phiên bản JVM

Tên mặc định thường là `hs_err_pid4242.log` (PID `4242` chỉ là ví dụ). Nếu không đặt `-XX:ErrorFile`, HotSpot thử ghi trong **working directory của process**; khi không ghi được có thể chuyển sang thư mục tạm OS (ví dụ `/tmp` trên Linux). Với service/container, working directory có thể khác thư mục dự án.

Có thể chủ động chỉ định vị trí (ví dụ Linux):

~~~bash
java -XX:ErrorFile=/var/log/myapp/hs_err_pid%p.log -jar myapp.jar
~~~

Trong `-XX:ErrorFile`, `%p` được thay bằng PID, `%%` được thay bằng ký tự `%`. Đảm bảo thư mục tồn tại, tài khoản service ghi được và đĩa còn chỗ. Ở Windows có thể dùng `C:/logs/myapp/hs_err_pid%p.log`.

Đầu ra stderr lúc crash đôi khi cho biết đường dẫn báo cáo:

~~~text
# An error report file with more information is saved as:
# /var/log/myapp/hs_err_pid4242.log
~~~

Trước khi đọc nội dung, cần xác nhận:

1. **Đúng incident:** thời điểm, PID, máy/container/pod và bản triển khai trùng với sự cố đang điều tra.
2. **Đúng JVM:** các dòng `JRE version`/`Java VM`, OS và kiến trúc khớp bản chạy thực tế; tránh lấy báo cáo của JDK cũ làm bằng chứng cho lần chạy mới.
3. **Đúng binary:** thư viện cùng tên có thể khác version/build; lưu lại bản ứng dụng, thư viện native và cấu hình runtime tương ứng.
4. **Bảo vệ bằng chứng:** sao chép file gốc để điều tra; ẩn hoặc kiểm soát truy cập thông tin nhạy cảm trong command line, environment variables, đường dẫn nội bộ và memory snapshot trước khi chia sẻ.

Không tìm thấy file ở dự kiến thì kiểm tra stderr, các directory tạm, log supervisor/container, quyền ghi, hết dung lượng và khả năng process đã bị kill từ bên ngoài.

## 3. Bản đồ các mục trong fatal error log

Bố cục và chính tả nhãn thay đổi theo phiên bản HotSpot, hệ điều hành và mức độ hỏng dữ liệu. Những dấu mốc thông dụng gồm:

| Mục/chuỗi | Thông tin cần lấy |
| --- | --- |
| `A fatal error has been detected`, `SIGSEGV` hoặc `Internal Error` | Loại fatal error, code, `pc`, PID, TID |
| `JRE version`, `Java VM` | Build JVM, kiến trúc, hệ điều hành |
| `Problematic frame` | Khung chứa lệnh mà lỗi được ghi nhận |
| `THREAD`, `Current thread` | Thread đang gặp lỗi, loại thread, thread name, native thread id và trạng thái |
| `siginfo`, `Registers`, `Stack`, `Instructions` | Faulting address, thanh ghi và bằng chứng CPU/stack đọc được |
| `Native frames` | Lời gọi native, VM và Java mà HotSpot tái dựng được |
| `Java frames` | Những method Java xuất hiện trong đường gọi |
| `PROCESS`, `VM state`, `VM Arguments` | Trạng thái VM, cờ JVM, agent và thông số runtime |
| `Dynamic libraries` hoặc `Loaded libraries` | Danh sách thư viện được nạp/đường dẫn nếu có |
| `SYSTEM`, `Memory`, `CPU` | Tài nguyên, OS, CPU và môi trường |

**Thứ tự đọc hiệu quả:** header → `Problematic frame` → `Current thread` → `Native frames` và `Java frames` → fault address/registers → thư viện/build/JVM state → tái hiện và xác minh. Đừng dừng ở một dòng `SIGSEGV`.

## 4. Ví dụ log mô phỏng và cách giải nghĩa

Đoạn sau là **log giả lập để học**, được viết theo hình thức thường gặp trên Linux/x86-64. Địa chỉ, phiên bản và tên thư viện chỉ mang tính minh họa; nó không phải bản trích từ một JVM thực. Có thể sao chép nguyên khối vào `sample-hs_err.log` để chạy chương trình Java ở mục 8.

~~~text
#
# A fatal error has been detected by the Java Runtime Environment:
#
#  SIGSEGV (0xb) at pc=0x00007f0012341abc, pid=4242, tid=4250
#
# JRE version: OpenJDK Runtime Environment (21.0.x+example)
# Java VM: OpenJDK 64-Bit Server VM (21.0.x+example, linux-amd64)
# Problematic frame:
# C  [libnativecodec.so+0x1abc]  native_decode+0x2b
#
---------------  T H R E A D  ---------------

Current thread (0x00007f0022001000): JavaThread "import-worker" [_thread_in_native, id=4250, stack(0x00007f0030000000,0x00007f0030100000)]

siginfo: si_signo: 11 (SIGSEGV), si_code: 1, si_addr: 0x0000000000000000

Native frames: (J=compiled Java code, j=interpreted, Vv=VM code, C=native code)
C  [libnativecodec.so+0x1abc]  native_decode+0x2b
C  [libnativebridge.so+0x0200]  Java_com_acme_NativeDecoder_decode0+0x20
j  com.acme.NativeDecoder.decode0([B)I+0
j  com.acme.Worker.process()V+15

Java frames: (J=compiled Java code, j=interpreted, Vv=VM code)
j  com.acme.NativeDecoder.decode0([B)I+0
j  com.acme.Worker.process()V+15
~~~

### Header: signal, `pc`, PID, TID

`SIGSEGV (0xb)` nói rằng OS báo lỗi truy cập bộ nhớ. `pc=0x00007f0012341abc` là **địa chỉ lệnh máy** tại thời điểm báo lỗi, không phải địa chỉ dữ liệu bị truy cập; `pid=4242` là process id; `tid=4250` là **native/OS thread id**, không mặc nhiên bằng `Thread.getId()` hay `Thread.threadId()` phía Java.

`siginfo.si_addr=0x0` là địa chỉ liên quan lỗi truy cập trong log mô phỏng. Nó gợi ý một giả thuyết về null pointer, nhưng chỉ registers/instructions và mã native mới phân biệt được null, pointer hết hạn, địa chỉ được tính sai hoặc các kịch bản khác. Đây **không** phải Java `NullPointerException` thông thường.

### `Problematic frame`: vị trí phát hiện lỗi

`C [libnativecodec.so+0x1abc] native_decode+0x2b` có nghĩa là HotSpot xác định khung native thuộc `libnativecodec.so` ở offset thể hiện trong log, có symbol gợi ý hàm `native_decode` nếu thông tin symbol có sẵn. Đây là **vị trí lệnh lỗi được ghi nhận**, chưa phải bằng chứng hàm `native_decode` chính là nguyên nhân gốc.

Nếu thấy `C [libc.so... memcpy]` thì vấn đề có thể là caller đã truyền buffer hoặc length sai. Tương tự, một khung trong `libjvm.so` có thể là nơi JVM phát hiện dữ liệu native đã bị hỏng trước đó.

### `Current thread`: ai đang thực thi?

Dòng `JavaThread "import-worker" [_thread_in_native, id=4250, ...]` xác nhận Java thread tên `import-worker` đang ở trạng thái native và OS thread id trùng TID báo lỗi. `stack(start,end)` mô tả khoảng stack thread, không phải dung lượng Java heap. Nếu luồng ở `_thread_in_vm` thì nó đang chạy VM code; `_thread_in_Java` là trong Java code; các trạng thái chỉ nói **đang làm gì khi crash**, không quy trách nhiệm tuyệt đối.

### Hai stack kể cùng một đường gọi

Các khung mô phỏng cho thấy đường gọi:

~~~text
Worker.process()
    -> NativeDecoder.decode0(byte[])
        -> JNI bridge Java_com_acme_NativeDecoder_decode0
            -> native_decode()  [crash được ghi nhận tại đây]
~~~

`Native frames` có chuỗi hỗn hợp `C`/`j`; `Java frames` chỉ ra caller Java. Thứ tự in thường từ **khung gần lệnh đang chạy ở trên**, rồi đến caller sâu hơn bên dưới. Stack là **ảnh chụp lời gọi**, không phải nhật ký timeline các sự kiện.

Từ ví dụ chỉ được kết luận: “Tiến trình 4242 gặp SIGSEGV trong thread 4250, lúc đang thực thi native code ở `libnativecodec.so`, với đường gọi từ `Worker.process` qua JNI.” Không đủ bằng chứng để nói `Worker.process` chắc chắn truyền null hoặc code trong `libnativecodec` nhất định có bug.

## 5. Giải mã ký hiệu `C`, `j`, `J`, `V`, `v`

| Frame | Nghĩa trong HotSpot | Cách sử dụng khi điều tra |
| --- | --- | --- |
| `C` | Native C/C++ hoặc thư viện native | `C [libfoo.so+offset]`, `C [foo.dll+offset]`. Có thể thuộc JNI, FFM, OS, JDK hoặc driver |
| `j` | Java interpreted frame | Ví dụ `j com.acme.Worker.process()V+15` |
| `J` | Compiled Java/khung compiled được HotSpot ghi nhận | Gợi ý xem compiled method, JIT, nhưng không chứng minh bug JIT |
| `V` | HotSpot VM frame | Ví dụ `V [libjvm.so+offset]` hoặc `V [jvm.dll+offset]` |
| `v` | VM-generated stub | Ví dụ `v ~StubRoutines::call_stub`; một khâu cầu nối runtime |

Chú giải frame thường xuất hiện sau `Native frames:`; ưu tiên chú giải có ngay trong file bởi cách hiển thị có thể khác ở các bản JDK.

Đọc một khung `J` không có nghĩa Java code đã trực tiếp thao tác địa chỉ native sai; native memory corruption có thể xảy ra trước đó, rồi biểu hiện trong compiled code. Một `V` không tự chứng minh bug HotSpot: xem caller trong native stack và lịch sử các JNI/FFM calls. Một `C` trong `libc` không tự chứng minh bug libc: phải xem tham số mà caller đã chuyển tới.

Với ký pháp Java method descriptor như `decode0([B)I`: `[B` là `byte[]`, `I` là `int` trả về, `V` là `void`, `J` là `long`, `Ljava/lang/String;` là `String`. Hậu tố như `+15` trong dòng frame **không phải số dòng source Java**; cần mapping source/build nếu muốn truy vị trí mã nguồn chính xác.

## 6. Phân biệt stack Java, native và JNI/FFM boundary

**`Native frames`** có thể biểu diễn các khung C/C++, JVM (`V/v`) và Java (`j/J`) trong call stack hỗn hợp mà crash handler tái dựng được. Với JNI thường có symbol export như `Java_com_acme_NativeDecoder_decode0`, nhưng tên chính xác phụ thuộc kiểu đăng ký/binding và symbol availability. Với FFM, Java có thể đi qua `Linker`/`MethodHandle`/generated stub đến hàm C; không phải mọi native frame là JNI.

**`Java frames`** giúp tìm method của ứng dụng đã đưa luồng tới native call. Khi đọc cùng native stack:

1. Xác nhận **đúng current thread**; không trộn stack của các thread khác nhau.
2. Tìm method Java gần biên JNI/FFM nhất và caller phía Java.
3. Trong `Native frames`, xác định bridge/thư viện, các hàm phía native và khung đang fault.
4. So signature C/JNI hoặc `FunctionDescriptor` của FFM; xét pointer, buffer length, alignment, ownership, thread confinement, thời gian sống `Arena/MemorySegment` và ABI thực tế.
5. So loaded library path, version, symbol và debug symbols với build đã chạy.

**Hạn chế quan trọng:** JIT có thể inline hoặc tối ưu hóa frame; native stack unwinding có thể thất bại vì thiếu frame pointers/debug symbols hoặc stack corruption; crash handler có thể dừng giữa chừng. Do đó **thiếu một frame không chứng minh lời gọi đó chưa xảy ra**. Đặc biệt nếu thấy `error occurred during error reporting`, coi stack là không đầy đủ.

`jstack`/`jcmd <PID> Thread.print` chỉ có thể thu trực tiếp từ tiến trình **còn sống**. Sau khi process đã chết, cần báo cáo crash và core/minidump đã ghi; không thể attach để lấy thread dump mới từ PID cũ.

## 7. Bằng chứng phát hiện và nguyên nhân gốc là hai việc khác nhau

Các tình huống dễ quy kết sai:

- `Problematic frame` là `C [libc.so... memcpy]`: libc có thể đang dùng pointer/length sai từ caller; code phá bộ nhớ có thể nằm ở nơi khác.
- `Problematic frame` là `V [libjvm.so...]`: JVM đang chạy trên bộ nhớ/reference đã bị JNI hoặc native code làm hỏng trước đó; cũng có thể là bug JVM.
- `Problematic frame` là `J ...`: có thể là lỗi compiled code/JIT, bug JVM, lỗi phần cứng hoặc corruption cũ.
- Luồng có tên `CompilerThread...`: có thể giúp tìm hướng JIT; không đủ kết luận compiler bug. `VMThread`/`VM_Operation` có thể liên quan GC nhưng corruption trước đó vẫn là khả năng.
- `si_addr=0x0`: phù hợp giả thuyết dereference null trong một số trường hợp; cần kiểm tra instruction/registers, không tự suy ra Java `NullPointerException`.

Hãy ghi rõ ba lớp thông tin:

**Quan sát:** “`SIGSEGV`, `Problematic frame=C libnativecodec.so`, `_thread_in_native`, Java caller `NativeDecoder.decode0`.”

**Giả thuyết:** “Pointer được truyền sang thư viện có thể null/hết hạn; hoặc length sai; hoặc binary và descriptor khác ABI.”

**Xác minh:** “Đối chiếu source C/header, ABI, input, phiên bản .so, registers/core, chạy test tái hiện dưới ASan/UBSan nếu kiểm soát được thư viện.”

Một native buffer overflow có thể xảy ra trước khi JVM crash tại `free`/GC. `hs_err_pid` cho biết thời điểm **phát hiện** và hiện trường crash, không có khả năng tự suy ngược nguyên nhân lịch sử.

## 8. Thực hành an toàn: Java 17 đọc log mô phỏng

Không cần và không nên làm JVM crash để học. Tạo file `sample-hs_err.log` từ **nguyên khối log mô phỏng ở mục 4**. Lưu code sau vào `HsErrReader.java`. Nó chỉ đọc văn bản và rút một số mốc quan trọng; không gọi native code.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class HsErrReader {
    private static String crashLine(List<String> lines) {
        for (String line : lines) {
            String s = line.strip();
            if (s.startsWith("#") &&
                (s.contains(" at pc=") || s.contains("Internal Error ("))) {
                return s;
            }
        }
        return "(không tìm thấy)";
    }

    private static String problematicFrame(List<String> lines) {
        boolean afterLabel = false;
        for (String line : lines) {
            String s = line.strip();
            if (s.equals("# Problematic frame:")) {
                afterLabel = true;
                continue;
            }
            if (afterLabel) {
                if (s.isEmpty() || s.equals("#")) {
                    continue;
                }
                if (s.startsWith("# ")) {
                    return s.substring(2).strip();
                }
                break;
            }
        }
        return "(không tìm thấy)";
    }

    private static String currentThread(List<String> lines) {
        for (String line : lines) {
            if (line.strip().startsWith("Current thread ")) {
                return line.strip();
            }
        }
        return "(không tìm thấy)";
    }

    private static void printFrames(
            List<String> lines, String header, int maxFrames) {
        for (int i = 0; i < lines.size(); i++) {
            if (lines.get(i).strip().startsWith(header)) {
                System.out.println(header);
                int printed = 0;
                for (int j = i + 1; j < lines.size() &&
                        printed < maxFrames; j++) {
                    String line = lines.get(j).strip();
                    if (line.isEmpty()) {
                        break;
                    }
                    System.out.println("  " + line);
                    printed++;
                }
                if (printed == 0) {
                    System.out.println("  (không có dữ liệu)");
                }
                return;
            }
        }
        System.out.println(header + " (không tìm thấy)");
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java HsErrReader <hs_err_file>");
            return;
        }

        List<String> lines = Files.readAllLines(
                Path.of(args[0]), StandardCharsets.UTF_8);

        System.out.println("Crash: " + crashLine(lines));
        System.out.println("Problematic: " + problematicFrame(lines));
        System.out.println("Thread: " + currentThread(lines));
        printFrames(lines, "Native frames:", 8);
        printFrames(lines, "Java frames:", 8);
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac HsErrReader.java
java HsErrReader sample-hs_err.log
~~~

Đầu ra dự kiến khi dùng đúng file ví dụ ở mục 4:

~~~text
Crash: #  SIGSEGV (0xb) at pc=0x00007f0012341abc, pid=4242, tid=4250
Problematic: C  [libnativecodec.so+0x1abc]  native_decode+0x2b
Thread: Current thread (0x00007f0022001000): JavaThread "import-worker" [_thread_in_native, id=4250, stack(0x00007f0030000000,0x00007f0030100000)]
Native frames:
  C  [libnativecodec.so+0x1abc]  native_decode+0x2b
  C  [libnativebridge.so+0x0200]  Java_com_acme_NativeDecoder_decode0+0x20
  j  com.acme.NativeDecoder.decode0([B)I+0
  j  com.acme.Worker.process()V+15
Java frames:
  j  com.acme.NativeDecoder.decode0([B)I+0
  j  com.acme.Worker.process()V+15
~~~

Đây chỉ là **trình đọc nhanh phục vụ học tập**, không phải parser tổng quát cho mọi phiên bản HotSpot. Log thật có thể thiếu section, không hoàn chỉnh, khác kiểu mã hóa hoặc cần khôi phục bằng debugger. `Files.readAllLines` có thể tốn RAM với file lớn; khi xử lý log rất lớn hãy đọc streaming. Không coi kết quả “không tìm thấy” do parser này trả về là bằng chứng mục tương ứng chắc chắn vắng mặt.

## 9. Tìm vị trí các section bằng shell

Ví dụ trên Linux:

~~~bash
grep -nE 'SIGSEGV|SIGBUS|SIGILL|Internal Error|Problematic frame|Current thread|Native frames|Java frames|siginfo|VM state|VM Arguments|Dynamic libraries|Loaded libraries' hs_err_pid4242.log
~~~

Đọc phần đầu file:

~~~bash
sed -n '1,70p' hs_err_pid4242.log
~~~

Trên PowerShell (một dòng lệnh):

~~~powershell
Select-String -Path .\hs_err_pid4242.log -Pattern 'Problematic frame','Current thread','Native frames','Java frames' -Context 2,8
~~~

Khi so nhiều incident, nhóm theo **signal + khung/library/function + build JDK + OS/architecture + phiên bản native library**, không theo một địa chỉ `pc` tuyệt đối: ASLR làm base address khác nhau giữa các lần chạy.

## 10. Khi nào cần native debugger, core/minidump và symbols?

`hs_err_pid` là điểm bắt đầu hữu ích. Muốn chứng minh hành vi con trỏ hoặc lỗi ABI, thường cần **core dump/minidump**, bản `java` và các thư viện **đúng build** cùng debug symbols. Ví dụ nếu đang ở Linux và đã có core file:

~~~bash
gdb /opt/jdk-21/bin/java /var/crash/core.4242
~~~

Trong GDB có thể xem:

~~~text
(gdb) info threads
(gdb) thread apply all bt
(gdb) info sharedlibrary
(gdb) disassemble
~~~

Đây là lệnh minh họa; cần binary, core, debug symbols và đúng kiến trúc OS. Với Windows có thể dùng WinDbg và minidump; với macOS dùng crash report/debugger phù hợp.

Để ánh xạ `[libnativecodec.so+0x1abc]` về hàm/source:

1. Tìm thư viện thật đã load, đường dẫn, phiên bản, build ID; đừng dùng tệp cùng tên nhưng được build khác.
2. Xác định base/load bias và cách offset trong log được biểu diễn. Không ép mọi offset trực tiếp vào `addr2line` nếu chưa hiểu địa chỉ ELF/PE, ASLR và layout.
3. Kết hợp symbol information, disassembly, registers và stack để thấy chính xác instruction truy cập sai địa chỉ, gọi từ đâu và tham số có hợp đồng đúng không.
4. Nếu sở hữu C/C++ code, tái hiện trong môi trường kiểm thử và thử AddressSanitizer/UndefinedBehaviorSanitizer; với JNI, `-Xcheck:jni` phát hiện được **một số** cách dùng JNI API sai.
5. Với FFM, kiểm tra `FunctionDescriptor` và layout theo C ABI, thời gian sống `Arena`/`MemorySegment`, callback, struct alignment và ownership. `-Xcheck:jni` không chứng minh một FFM downcall an toàn.

Khi log ghi `error occurred during error reporting` hoặc thiếu phần stack, nói rõ bằng chứng **không hoàn chỉnh**; core và tái hiện có thể giúp hơn việc suy đoán từ nội dung còn sót.

## 11. Bảng định hướng điều tra sự cố

| Quan sát | Các giả thuyết nên ưu tiên | Kiểm chứng hữu ích |
| --- | --- | --- |
| `SIGSEGV`, `C [libapp.so+...]`, `_thread_in_native` | Invalid pointer, use-after-free, overflow, ABI mismatch | Source C, ABI, binary version, core, sanitizer |
| `C [libc.so+...] memcpy` | Caller truyền sai pointer/length, corruption trước đó | Native caller frames, registers, buffer lifetime |
| `V [libjvm.so+...]` gần wrapper JNI | JNI hỏng reference/state; cũng có thể bug HotSpot | `-Xcheck:jni`, core, đối chiếu JDK build |
| `J ...` ở problematic frame | Compiled-code/JIT vấn đề, hoặc native corruption trước đó | Repro, flags/JDK version, kiểm tra native dependencies |
| `CompilerThread...` là current thread | Cần xem JIT compilation path | Compiler info, JDK build, test môi trường cô lập |
| `VMThread`, `VM_Operation` liên quan GC | GC/heap corruption | GC logs, native writes, core |
| Stack thiếu, báo `error occurred during error reporting` | Crash handler thiếu dữ liệu hoặc stack/memory corruption | Dump, symbol, reproducible test |
| Không có `hs_err_pid`, OS báo OOMKilled | Kernel đã kill process | Kernel/pod metrics, memory limits và events |

**Ký tự frame là chỉ dấu nơi JVM thấy lỗi, không phải bộ phân loại root cause tuyệt đối.** `C` không đồng nghĩa lỗi C, `V` không đồng nghĩa JVM chắc chắn có bug, `J` không đồng nghĩa Java source sai.

## 12. Quy trình 10 bước với một incident

1. **Xác định loại sự cố:** fatal JVM crash hay Java exception hay OOM kill; đối chiếu PID/time/OS/exit reason.
2. **Ghi nguyên các dữ kiện:** signal/error, `pc`, `pid`, `tid`, `JRE version`, `Java VM` và `Problematic frame`.
3. **Đọc `Current thread`:** tên Java thread, loại thread, state, OS thread id; xác nhận khớp thread crash.
4. **Ghép stack:** tìm các native frames gần lệnh lỗi; lần về Java caller qua JNI/FFM từ **đúng thread**.
5. **Phân tích thông tin memory:** `siginfo`, fault address, registers, `Stack`/`Instructions` nếu có; tránh suy đoán chỉ từ `si_addr`.
6. **Kiểm tra runtime:** `VM state`, `VM Arguments`, loaded libraries, JDK/OS/CPU, agents và log GC/concurrency liên quan.
7. **Kiểm tra hợp đồng native:** parameter type/size, `sizeof`, struct layout/alignment, buffer length, pointer lifetime, thread confinement, ABI, JNI references, FFM descriptor.
8. **Lập giả thuyết có thể bác bỏ:** ví dụ JNI truyền length lớn hơn buffer; native code giữ pointer sau khi arena đóng; thư viện version không tương thích. Ghi rõ bằng chứng ủng hộ và còn thiếu.
9. **Tái hiện cô lập:** đúng build/JDK/input, test native riêng trong process/container, dùng `-Xcheck:jni`/sanitizers/debugger/core khi phù hợp; tuyệt đối không cố làm process sản xuất crash để “kiểm chứng”.
10. **Kết luận và phòng ngừa:** nêu nguyên nhân **đã chứng minh** và phạm vi còn chưa chắc, thêm regression test có giá trị, ghi nhận crash signature có version để kiểm tra sau sửa.

Ví dụ một báo cáo incident đạt chuẩn phân biệt bằng chứng:

> “`hs_err_pid4242.log` ghi `SIGSEGV` ở `libnativecodec.so` khi thread `import-worker` đang `_thread_in_native`. Native và Java stack cho thấy lời gọi `Worker.process → NativeDecoder.decode0 → native_decode`. Đây là chứng cứ về **vị trí crash và call path**. Chưa đủ để khẳng định nguyên nhân null pointer hay lỗi thư viện; đang cần kiểm tra buffer contract, binary version và core/sanitizer.”

## 13. Tự kiểm tra

**Câu 1.** `hs_err_pid` và Java exception stack trace khác gì? — Exception thông thường không kết thúc JVM và không tự sinh fatal error log; `hs_err_pid` phản ánh trạng thái HotSpot khi fatal error.

**Câu 2.** `Problematic frame: C [libc.so+...]` chứng minh libc sai? — Không. Caller có thể truyền pointer/length sai hoặc memory corruption đã xảy ra trước đó.

**Câu 3.** Header `tid` có phải Java thread id không? — Không mặc định; trong báo cáo mẫu là native thread id. Đối chiếu `Current thread` để xác định đúng thread và tên Java.

**Câu 4.** `J` chứng minh bug JIT? — Không. Nó giúp nhận diện compiled code; cần loại trừ native corruption và kiểm tra thêm JVM/compiler.

**Câu 5.** Không có `Java frames` nghĩa là không có Java caller? — Không. Handler hoặc stack unwinding có thể không dựng được đầy đủ.

**Câu 6.** Cần gì để xem `libfoo.so+offset` là dòng source nào? — Đúng thư viện/build, debug symbols, mapping offset/load bias và debugger; cùng tên tệp chưa đủ.

**Câu 7.** `-Xcheck:jni` có kiểm tra toàn bộ FFM và native binary không? — Không. Nó giúp phát hiện một số vi phạm JNI API trong môi trường thử nghiệm, không phải bảo chứng native safety.

## Tài liệu chính thức

- [Oracle JDK 25 – Fatal Error Log](https://docs.oracle.com/en/java/javase/25/troubleshoot/location-fatal-error-log.html): location, header, thread/process/system và frame types.
- [Oracle JDK 25 – Troubleshoot System Crashes](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-system-crashes.html): JNI, native, compiled code, VM/GC và debugger.
- [Oracle JDK 25 – java launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:ErrorFile` và cấu hình khởi động.

**Nguyên tắc kết luận:** `hs_err_pid` giúp xác định JVM **phát hiện lỗi gì, ở khung nào, trên luồng nào**. Đọc `Problematic frame` cùng hai loại stack Java/native để khôi phục đường gọi, sau đó đối chiếu binary, ABI và chứng cứ tái hiện mới có thể xác định nguyên nhân gốc.