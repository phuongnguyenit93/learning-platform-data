# Thu tệp dump, ký hiệu gỡ lỗi và thông tin thư viện để tái hiện sự cố JNI/native

## 1. Vì sao cần thu thập đủ ba nhóm chứng cứ?

Sự cố ở ranh giới Java ↔ mã native thường khó tái hiện vì có nhiều lớp tham gia: bytecode Java, mã JIT, JNI hoặc FFM, thư viện C/C++, thư viện hệ thống, trình nạp động của hệ điều hành và chính JVM. Một báo cáo chỉ ghi “`SIGSEGV` ở `libfoo.so`” thường chưa đủ tìm nguyên nhân.

Một bộ chứng cứ tốt phải trả lời đồng thời:

1. **Điều gì xảy ra tại thời điểm lỗi?** → fatal-error log của HotSpot, **OS core/minidump**, call stack của các thread, signal/exception, thanh ghi, mapping bộ nhớ.
2. **Địa chỉ máy tương ứng hàm và dòng mã nào?** → **debug symbols** khớp chính xác binary: DWARF/ELF trên Linux, dSYM trên macOS, PDB trên Windows; nếu thiếu, stack có thể chỉ còn địa chỉ hoặc `??`.
3. **Đúng phiên bản thư viện nào đang được nạp?** → file nhị phân triển khai thực tế, build ID/UUID/GUID, hash, ABI, các thư viện phụ thuộc, JDK và OS, đường dẫn nạp, tùy chọn JVM.

**Dump + symbols + binaries/metadata cùng một build** mới giúp chuyên gia chuyển từ địa chỉ máy sang stack có tên hàm/dòng nguồn và chạy lại sự cố trong một môi trường tương đương. Tệp dump không tự chứa đầy đủ mã nguồn, tệp symbol không thay thế dump, và hai bản `libfoo.so` cùng tên nhưng khác build **không được dùng lẫn**.

### Phân biệt loại dump ngay từ đầu

| Hiện tượng | Chứng cứ ưu tiên | Không nên nhầm với |
| --- | --- | --- |
| JVM chết vì `SIGSEGV`, `SIGABRT`, `EXCEPTION_ACCESS_VIOLATION` hoặc fatal error | `hs_err_pid<pid>.log` + OS core/dump + native symbols + binary identity | `.hprof` chỉ mô tả Java heap, không phải toàn bộ tiến trình |
| `java.lang.OutOfMemoryError` / nghi ngờ leak Java heap | `.hprof`, GC logs, JFR, heap histogram, memory metrics | Không phải mọi OOME đều làm JVM crash hay tạo OS core |
| Ứng dụng bị treo, deadlock, JNI call kẹt | Nhiều **thread dumps** cách nhau một khoảng thời gian, JFR, native thread stacks | Thread dump không chứa đầy đủ register/stack memory như OS core |
| Lỗi thư viện không nạp được: `UnsatisfiedLinkError` | Stack trace Java, tên thư viện, đường dẫn tìm kiếm, ABI/dependency, version | Chưa chắc cần core dump vì tiến trình còn chạy |
| Sai kết quả / hỏng dữ liệu sau JNI | Input tối thiểu, kết quả kỳ vọng/thực tế, log + sanitizers/`-Xcheck:jni` | Một địa chỉ trong core không xác định ngay thao tác ghi sai trước đó |

**Ưu tiên thời điểm:** thu những thứ mất khi process kết thúc trước khi restart hoặc redeploy: `/proc/<pid>/maps`, lệnh chạy, trạng thái thư viện và thread dump; sau crash, thu `hs_err` và OS core/dump. Lưu nguyên gốc một bản chỉ đọc rồi mới tạo bản đã ẩn thông tin nhạy cảm để chia sẻ.

## 2. Khởi động JVM với dữ liệu chẩn đoán có chủ đích

Ví dụ trên Linux, với đường dẫn có quyền ghi và dung lượng phù hợp:

```bash
mkdir -p /var/tmp/jvm-diag
# Thực hiện trong launcher/service của chính ứng dụng:
java -XX:ErrorFile=/var/tmp/jvm-diag/hs_err_pid%p.log \
     -XX:+CreateCoredumpOnCrash \
     -jar app.jar
```

- `-XX:ErrorFile=...` chỉ định nơi lưu **HotSpot fatal error log**; `%p` mở rộng thành PID, tránh đè nhau giữa các sự cố. Nếu không đặt cờ, HotSpot thường thử tạo `hs_err_pid<pid>.log` tại working directory rồi fallback tới thư mục tạm khi không ghi được.
- `-XX:+CreateCoredumpOnCrash` yêu cầu HotSpot cho phép tạo core/minidump khi có fatal error. Trên nhiều bản HotSpot cờ đã bật sẵn; **JVM flag không thể vượt qua** giới hạn kernel, service manager, container, quyền truy cập và bộ nhớ đĩa. Kiểm tra cờ thực tế theo bản JDK đang chạy.
- `-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/tmp/jvm-diag` là cấu hình **riêng cho heap dump khi OOME**. Không nhầm nó với OS core của một `SIGSEGV`.
- `-Xcheck:jni` tăng kiểm tra các lời gọi JNI sai hợp đồng (tham chiếu, `JNIEnv` sai thread, exception đang pending...). Có giá trị ở môi trường tái hiện, nhưng tăng overhead, thay đổi timing và không phát hiện mọi lỗi memory corruption.

Nếu chạy trên JDK 24+ và thao tác JNI chưa được cấp quyền, xử lý riêng các cảnh báo native access theo chính sách phiên bản JDK. Cảnh báo native access **không đồng nghĩa** crash và không thể thay thế bằng việc thu core dump.

### Nếu tiến trình vẫn đang sống

Thu metadata **trước khi stop/restart**, bằng đúng tài khoản có thể attach vào JVM:

```bash
PID=12345  # Thay bằng PID thực của tiến trình Java
jcmd "$PID" VM.command_line > jvm-command-line.txt
jcmd "$PID" VM.flags > jvm-flags.txt
jcmd "$PID" VM.info > jvm-info.txt
jcmd "$PID" Thread.print -l > threads-1.txt
sleep 5
jcmd "$PID" Thread.print -l > threads-2.txt

readlink -f "/proc/$PID/exe" > java-executable.txt
cp "/proc/$PID/maps" proc-maps.txt
cp "/proc/$PID/limits" proc-limits.txt
cat /proc/sys/kernel/core_pattern > core-pattern.txt
```

`jcmd` cần cùng host và quyền phù hợp với JVM; container PID namespace, attach policy và khác user có thể khiến công cụ không tìm thấy/không attach được. Trong bộ nhớ mapping, `/proc/PID/maps` cho biết thư viện nào được map vào tiến trình tại thời điểm đọc. Sau khi tiến trình chết, đường dẫn `/proc/PID/...` không còn. Thu thêm log ứng dụng, timestamp có múi giờ, thời điểm lỗi và deployment ID để liên kết bằng PID.

Với JFR đã bật: `jcmd "$PID" JFR.dump filename=/var/tmp/jvm-diag/before-crash.jfr` có thể lấy bản ghi trước khi restart. Kiểm tra lệnh được JVM đích hỗ trợ bằng `jcmd "$PID" help`. Nếu chưa bật recording thì không thể “lấy lại” JFR quá khứ.

**Giới hạn:** một lệnh `jcmd` có thể fail nếu JVM đã crash, bị treo hoặc attach bị vô hiệu hóa. Không diễn giải lỗi attach là chứng cứ rằng Java heap hay native code sai.

## 3. Linux: tìm, lấy và xác minh OS core dump

### 3.1. Hiểu nơi kernel ghi core

Các điểm kiểm soát chính:

```bash
ulimit -c
cat /proc/sys/kernel/core_pattern
cat /proc/sys/kernel/core_uses_pid
```

- `ulimit -c 0` có thể ngăn tạo core dạng file; để bật cho **process con của shell tái hiện**, dùng `ulimit -c unlimited` trước lệnh `java`. Giá trị này không tự thay đổi giới hạn của dịch vụ systemd đã chạy.
- Nếu `core_pattern` bắt đầu bằng ký tự `|`, dump được chuyển cho **handler** (chẳng hạn `systemd-coredump`), không mặc nhiên thành file `core` ở current directory.
- Với service systemd, kiểm tra `LimitCORE`, cấu hình `systemd-coredump`, `Storage` và `ProcessSizeMax`, quyền và quota. Không nên thay sysctl toàn host chỉ để kiểm tra một ứng dụng.
- Trong Docker/Kubernetes, dump còn chịu cấu hình của host kernel, container runtime, mount lưu trữ, namespace và khả năng truy cập handler của host. Một container có `ulimit -c unlimited` vẫn có thể không lưu được core nếu host không thu nhận.

Nếu hệ thống dùng `systemd-coredump`, kiểm tra như sau:

```bash
coredumpctl list java
coredumpctl info 12345
coredumpctl dump 12345 --output=core.java.12345
```

Ở đây `12345` là PID từ fatal-error log/incident (thay bằng giá trị thực); có nhiều sự cố cùng PID do tái sử dụng PID thì đối chiếu thêm timestamp, executable và boot ID. `coredumpctl info` có thể liệt kê entry dù file core đã bị xóa do retention hoặc quyền không cho đọc. Trạng thái `truncated`/`missing`/`error` không tạo được bản dump đầy đủ để phân tích. Nếu không dùng systemd, tìm file theo `core_pattern` và chính sách thu core của host.

Sau khi có file, kiểm chứng bằng:

```bash
file core.java.12345
ls -lh core.java.12345
sha256sum core.java.12345
```

File nhận được phải tương ứng crash và kiến trúc cần phân tích; core kích thước 0 byte hoặc bị truncate không dùng như full core. Đừng đoán vị trí dump chỉ từ tên `core` vì hệ điều hành có thể đổi cách đặt tên hoặc chuyển sang service handler.

### 3.2. Phân tích native call stack với GDB

Cần bản executable `java` và các shared libraries **khớp bản lúc crash**. Trên máy chẩn đoán có `gdb` và symbols tương ứng:

```bash
gdb --batch \
  -ex "set pagination off" \
  -ex "info sharedlibrary" \
  -ex "info threads" \
  -ex "thread apply all bt full" \
  /path/to/same-jdk/bin/java /path/to/core.java.12345 \
  > gdb-backtrace.txt
```

Từ output, tìm thread gây signal, phần trên của stack, các khung JNI, các hàm của thư viện ứng dụng, khả năng symbol `??`, và luồng khác đang giữ mutex/tài nguyên. `info sharedlibrary` cho biết GDB có nạp thông tin thư viện và symbols hay chưa. Có thể mở tương tác `gdb /path/to/java /path/to/core` rồi dùng `thread <N>`, `bt full`, `frame <N>`, `info locals` khi debug info phù hợp.

Dùng Serviceability Agent để thử lấy góc nhìn **Java + native** của HotSpot:

```bash
jhsdb jstack --exe /path/to/same-jdk/bin/java \
             --core /path/to/core.java.12345 --mixed \
  > mixed-stacks.txt
```

`jhsdb` phụ thuộc phiên bản JVM, kiến trúc, core đầy đủ và native libraries liên quan; không đảm bảo xử lý mọi dump. Nếu công cụ báo không khớp JVM, hãy mang **đúng JDK distribution/build** vào môi trường phân tích thay vì giải mã core bằng một JDK khác chỉ vì cùng major version. Khi thiếu `.debug`/`debuginfo` của `libjvm.so` hoặc thư viện native, một số frame sẽ không có tên/dòng nguồn.

## 4. Windows: WER/ProcDump, PDB và WinDbg

Trên Windows, OS user-mode crash dump thường có đuôi `.dmp`, khác với Java heap dump `.hprof`.

**Windows Error Reporting (WER) LocalDumps:** cấu hình theo executable, ví dụ khóa registry:

```text
HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\java.exe
    DumpType   REG_DWORD       2
    DumpCount  REG_DWORD       5
    DumpFolder REG_EXPAND_SZ   C:\jvm-dumps
```

`DumpType=2` yêu cầu full user-mode dump, `1` là minidump. Tạo thư mục trước, cấp ACL ghi cho **tài khoản chạy process**, có dung lượng đủ và cấu hình bằng quyền quản trị theo quy định máy. Khóa theo `java.exe` áp dụng cho mọi process cùng tên executable, nên cân nhắc impact nhiều ứng dụng; application-server launcher riêng có thể dùng executable khác. WER không được kích hoạt mặc định cho mọi crash, và một số crash handler/postmortem debugger có thể ảnh hưởng việc thu WER dump.

Với **Sysinternals ProcDump**, có thể gắn vào PID riêng và yêu cầu full dump khi unhandled exception:

```powershell
procdump.exe -accepteula -ma -e 12345 C:\jvm-dumps
```

Ở đây `12345` là PID thật; `-ma` là full dump, `-e` theo dõi exception chưa được xử lý; tùy luồng xử lý exception của JVM, trigger có thể không tạo đúng file mong muốn. Thu cả `hs_err_pid*.log` khi có và xác nhận dump thực sự xuất hiện. Tránh dùng trigger “first-chance” `-e 1` vô tội vạ với JVM vì dễ tạo nhiều dump rất lớn.

Mở dump trong **WinDbg**, thiết lập symbol server cho Windows và đường dẫn PDB nội bộ khớp bản build:

```text
.symfix C:\symbol-cache
.sympath+ C:\secure-pdbs
.reload /f
lm
.ecxr
k
!analyze -v
```

Các lệnh trên là **lệnh bên trong WinDbg**, không gõ trực tiếp vào PowerShell. `lm` liệt kê DLL; `lmvm <module>` chi tiết một module; `.ecxr` chuyển sang exception context khi dump có exception record. PDB phải khớp **GUID + Age** của DLL/EXE, không chỉ trùng tên `foo.pdb`. Lưu đúng runtime DLL, PDB tương ứng và version của Windows/JDK.

## 5. macOS: crash report, core và dSYM

Trên macOS, hệ thống có thể ghi **crash report `.ips`** dưới `~/Library/Logs/DiagnosticReports/` hoặc nơi quản trị hệ thống quy định. Báo cáo này thường có exception, binary images, UUID và backtrace, **không phải full core**. Nếu có core và LLDB hỗ trợ đọc:

```bash
lldb -c /path/to/core /path/to/java
```

Trong LLDB:

```text
(lldb) thread backtrace all
(lldb) image list
(lldb) image lookup --address 0xADDRESS
```

`0xADDRESS` là địa chỉ thực trong phiên debug, cần thay đúng giá trị trong dump; các lệnh chỉ minh họa thao tác LLDB. Thu file `.dylib` khớp phiên bản cùng bundle `.dSYM` và mã nguồn cùng commit. So khớp UUID thay vì dựa vào file name:

```bash
dwarfdump --uuid /path/to/libfoo.dylib
dwarfdump --uuid /path/to/libfoo.dylib.dSYM
```

Core trên macOS còn phụ thuộc chính sách crash reporting, quyền, giới hạn và nơi lưu của OS. Khi chỉ có `.ips`, hãy dùng UUID/binary images để symbolicate theo công cụ macOS phù hợp; không gọi nó là full memory dump.

## 6. Lưu debug symbols và nhận diện đúng thư viện native

### 6.1. “Có debug symbols” nghĩa là gì?

| Nền tảng | File triển khai | Debug information cần giữ | Khóa nhận dạng |
| --- | --- | --- | --- |
| Linux/ELF | `libfoo.so`, `java`, `libjvm.so` | DWARF trong binary hoặc file `.debug`/gói debuginfo tách rời | ELF **Build ID** và/hoặc `.gnu_debuglink` (CRC); hash của deployed binary |
| Windows/PE | `foo.dll`/`java.exe` | **PDB** tương ứng | PDB **GUID + Age** và hash DLL/EXE |
| macOS/Mach-O | `libfoo.dylib`, executable/framework | **dSYM** bundle hoặc DWARF phù hợp | Mach-O **UUID** cho đúng architecture slice |

**Không thể tái tạo symbol của một build đã bị strip nếu không còn bản không strip, file debug riêng hoặc artifact CI gốc.** Cùng semantic version, cùng commit hoặc cùng tên thư viện vẫn chưa đảm bảo cùng build: compiler, flags, link order và dependency có thể làm thay đổi layout địa chỉ.

Trên Linux, khi build thư viện JNI, nên sinh thông tin gỡ lỗi và build ID; ví dụ:

```bash
gcc -g -O2 -fno-omit-frame-pointer -fPIC -shared \
    -Wl,--build-id -o libfoo.so foo.c

# Giữ bản gỡ lỗi trước khi strip bản triển khai:
objcopy --only-keep-debug libfoo.so libfoo.so.debug
strip --strip-debug libfoo.so
objcopy --add-gnu-debuglink=libfoo.so.debug libfoo.so

readelf -n libfoo.so
sha256sum libfoo.so libfoo.so.debug
```

Đây là **mẫu quy trình build** cho nguồn C thuần; JNI thật còn cần include headers của JDK và có thể cần liên kết thư viện phụ thuộc. Trong CI, lưu riêng `libfoo.so.debug` và bản `libfoo.so` **sau strip** đã thực sự phát hành. GDB có thể tìm debug file qua `.gnu_debuglink`, Build ID hoặc `debuginfod`; cấu hình nơi đặt symbol và hạn chế truy cập phù hợp.

Khi nhận incident, thu chứng cứ danh tính:

```bash
file /opt/app/lib/libfoo.so
readelf -n /opt/app/lib/libfoo.so
readelf -d /opt/app/lib/libfoo.so
nm -D /opt/app/lib/libfoo.so
sha256sum /opt/app/lib/libfoo.so
java -version
uname -a
```

- `readelf -n`: nếu toolchain phát sinh build ID, ghi chính xác giá trị đó.
- `readelf -d`: mục `NEEDED` cho biết dependency trực tiếp mà ELF khai báo; nó không xác nhận phiên bản dependency nào đã được dynamic loader chọn khi chạy.
- `nm -D`: xem dynamic/exported symbols, không đồng nghĩa có đầy đủ line numbers.
- `sha256sum`: fingerprint của **file đã triển khai**; hash file ở image mới có thể khác bản đang map trong tiến trình cũ sau một rolling update.
- `java -version`/`uname -a`: khởi điểm; còn phải thu JDK vendor/build, architecture, libc/musl/glibc và phiên bản container image.

Có thể xem `ldd` trên thư viện **tin cậy** để kiểm tra resolution, nhưng nó phản ánh môi trường **đang kiểm tra** và có thể không giống runtime ở sự cố; với binary không tin cậy, ưu tiên đọc tĩnh bằng `readelf -d`. Nếu ứng dụng dùng `dlopen`/`System.load`, nhiều thư viện **không nằm trong `DT_NEEDED`** và chỉ hiện trong runtime mappings/loader traces.

### 6.2. ASLR và symbolicate địa chỉ

Một dòng `Problematic frame: C [libfoo.so+0x1a2b]` chỉ ra địa chỉ tương đối của một frame trong thư viện, nhưng chưa chứng minh lỗi thuộc đúng hàm hoặc dòng nguồn. Với ASLR, **runtime PC tuyệt đối** thay đổi giữa các lần chạy. Cách an toàn nhất là nạp **đúng core + binary + debug symbols** trong GDB/LLDB và lấy `bt`, `info symbol`/`image lookup`.

Nếu dùng `addr2line` thủ công trên Linux:

```bash
addr2line -C -f -i -e /path/to/exact/libfoo.so.debug 0x1a2b
```

`0x1a2b` chỉ là **ví dụ**: phải chuyển runtime PC thành địa chỉ/ELF VMA phù hợp với load bias và mapping của binary thực tế trước khi tra. Không gửi nguyên địa chỉ tuyệt đối từ `hs_err` vào `addr2line` rồi tin kết quả; vị trí `??:0` thường báo thiếu debug symbols hoặc địa chỉ sai. Compiler optimization, inline, tail calls và ghi đè bộ nhớ có thể khiến backtrace/dòng nguồn không khớp một cách tuyệt đối.

## 7. Đọc `hs_err_pid` để định hướng nguyên nhân

Bắt đầu bằng các trường (tên/mức độ hiện diện có thể khác giữa phiên bản JVM):

- **Signal/exception**: `SIGSEGV`, `SIGBUS`, `SIGABRT`, `EXCEPTION_ACCESS_VIOLATION`; fault PC, PID, thread ID.
- **Problematic frame**: ký hiệu `C` (native C/C++), `V` (mã JVM), `J` (mã JIT Java), `j` (Java interpreted), cùng tên lib hoặc phương thức.
- **Current thread / native frames / Java frames**: thời điểm chuyển qua JNI, call chain, lock, trạng thái luồng.
- **Dynamic libraries / memory mappings**: tên, địa chỉ load, đường dẫn thư viện; dùng để so phiên bản và vị trí.
- **VM Arguments, System, Environment**: bản JDK, flags, OS/CPU; những trường này có thể chứa thông tin nhạy cảm và có thể không hoàn chỉnh nếu error handler không ghi xong.

Ví dụ **trích đoạn minh họa**, không phải output của chương trình chạy bên dưới:

```text
# SIGSEGV (0xb) at pc=0x..., pid=12345, tid=...
# Problematic frame:
# C  [libfoo.so+0x1a2b]
```

Chỉ có thể kết luận rằng tín hiệu được ghi nhận khi thực thi native frame thuộc `libfoo.so`. **Chưa thể kết luận** thư viện đó là thủ phạm: ghi vượt mảng ở thư viện A có thể làm hỏng heap và crash muộn trong `malloc`/`free` hoặc mã JVM. Đối chiếu nhiều core, ngữ cảnh thread, symbols, version thư viện và mô hình tái hiện.

Có thể bật `-Xcheck:jni` để phát hiện một số sai phạm giao thức JNI khi chạy lại, hoặc biên dịch thư viện native với **AddressSanitizer/UndefinedBehaviorSanitizer** trong bản kiểm thử tương thích. Sanitizer và debug flags có thể thay layout/timing, vì vậy lưu cả một lần tái hiện trên binary production chính xác và một lần tái hiện có instrumentation.

## 8. Thực hành: tạo JNI library, thu symbols và chủ động tái hiện crash

Ví dụ hoàn chỉnh này chạy trên **Linux x86_64 hoặc aarch64 tương ứng**, JDK 17+ cùng `gcc`/`binutils`. Nó có hai chế độ: mặc định **an toàn**, hoặc `--crash` chủ động phát `SIGSEGV`. **Chỉ chạy chế độ crash trong máy/VM/container thí nghiệm được phép hủy tiến trình; không chạy trong dịch vụ sản xuất.** Tín hiệu có chủ đích chỉ kiểm tra đường đi thu dump, không thay thế tình huống memory corruption thực.

### Bước A — `NativeIncidentLab.java`

```java
public final class NativeIncidentLab {
    static {
        System.loadLibrary("incidentdemo");
    }

    private static native int multiply(int left, int right);
    private static native void simulateSignal();

    public static void main(String[] args) throws InterruptedException {
        System.out.println("result=" + multiply(6, 7));

        if (args.length == 1 && "--pause".equals(args[0])) {
            Thread.sleep(30000);
        } else if (args.length == 1 && "--crash".equals(args[0])) {
            System.out.flush();
            simulateSignal();
        }
    }
}
```

`--pause` giữ JVM sống 30 giây để thu `/proc/PID/maps`/`jcmd`. `--crash` đi qua JNI để phát tín hiệu; mặc định chỉ tính tích 6 × 7.

### Bước B — `NativeIncidentLab.c`

```c
#include "NativeIncidentLab.h"
#include <signal.h>

JNIEXPORT jint JNICALL Java_NativeIncidentLab_multiply(
        JNIEnv *env, jclass clazz, jint left, jint right) {
    (void)env;
    (void)clazz;
    return left * right;
}

JNIEXPORT void JNICALL Java_NativeIncidentLab_simulateSignal(
        JNIEnv *env, jclass clazz) {
    (void)env;
    (void)clazz;
    raise(SIGSEGV);
}
```

`raise(SIGSEGV)` là tác động có chủ đích để kiểm thử capture pipeline; frame trực tiếp gây tín hiệu có thể nằm ở libc, còn `Java_NativeIncidentLab_simulateSignal` ở sâu hơn trong backtrace. Do đó chỉ nhìn `Problematic frame` sẽ gây hiểu nhầm rằng “libc lỗi”.

### Bước C — build có debug symbols

```bash
# Chạy trong thư mục chứa hai file nguồn:
javac -h . NativeIncidentLab.java
gcc -g -O0 -fno-omit-frame-pointer -fPIC -shared \
    -Wl,--build-id \
    -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
    -o libincidentdemo.so NativeIncidentLab.c

file libincidentdemo.so
readelf -n libincidentdemo.so
sha256sum libincidentdemo.so
```

`javac -h` sinh `NativeIncidentLab.h` để chữ ký JNI phía C khớp Java. `JAVA_HOME` phải trỏ đúng JDK chứa `include/jni.h`. `-g` tạo DWARF, `-O0` dễ quan sát dòng nguồn trong lab; `-fno-omit-frame-pointer` hỗ trợ stack unwinding. Trình liên kết GNU thông thường tạo Build ID với cờ được chỉ định.

### Bước D — thử an toàn, đối chiếu stdout

```bash
java -Djava.library.path="$PWD" NativeIncidentLab
```

**Stdout chính xác** (không tính cảnh báo JVM trên stderr):

```text
result=42
```

Trên JDK 24+, để loại trừ cảnh báo native access không liên quan bài này, có thể thêm `--enable-native-access=ALL-UNNAMED` vào lệnh `java` vì class nằm trên classpath. Trên JDK 17–23 không dùng cờ này.

### Bước E — chủ động thu dữ liệu trước khi crash

```bash
mkdir -p artifacts
java -Djava.library.path="$PWD" NativeIncidentLab --pause &
PID=$!

# Thực hiện trong 30 giây trước khi process thoát:
cp "/proc/$PID/maps" artifacts/proc-maps.txt
cp "/proc/$PID/limits" artifacts/proc-limits.txt
jcmd "$PID" VM.command_line > artifacts/jvm-command-line.txt
wait "$PID"
```

Lệnh có thể đòi quyền attach; PID/namespace phải trỏ tới process Java đang chạy. Khi hết 30 giây, Java thoát bình thường; đây là bước **thu thông tin trước sự cố**, chưa tạo core.

### Bước F — chỉ ở môi trường lab: tạo crash và lấy dump

```bash
ulimit -c unlimited
java -XX:+CreateCoredumpOnCrash \
     -XX:ErrorFile="$PWD/artifacts/hs_err_pid%p.log" \
     -Djava.library.path="$PWD" \
     NativeIncidentLab --crash
```

Stdout trước khi crash vẫn là:

```text
result=42
```

Process sau đó dừng bất thường; mã thoát, stderr, tên `hs_err` và sự tồn tại/vị trí core phụ thuộc signal handling và cấu hình hệ điều hành. **Không tự khẳng định luôn có core.** Kiểm tra `artifacts/hs_err_pid*.log` và `coredumpctl` hoặc `core_pattern`; nếu có core, sao chép sang `artifacts/` rồi dùng GDB/`jhsdb` như mục 3. Thư viện mang `-g` sẽ cho khả năng nhận ra `Java_NativeIncidentLab_simulateSignal` trong native stack khi dump đủ thông tin.

Để chứng minh pipeline symbols hoạt động: đọc Build ID của bản `libincidentdemo.so` đã tạo, lưu nó cùng core, dùng GDB mở đúng executable Java và dump rồi kiểm tra có frame `simulateSignal`. Đừng dựa vào số địa chỉ PC, PID hay số thứ tự frame trong ví dụ vì chúng khác nhau giữa lần chạy.

## 9. Gói thông tin tái hiện sự cố có thể chuyển giao

Một “incident bundle” hữu dụng nên có cấu trúc và liên kết rõ:

```text
incident-12345/
├── repro.md                 # thời điểm, cách chạy, input, expected/actual
├── hs_err_pid12345.log       # nguyên bản được bảo vệ
├── core.java.12345           # Linux core (hoặc crash.dmp trên Windows)
├── native-backtrace.txt      # gdb/lldb/windbg; nội dung đã kiểm chứng
├── java-threads.txt          # jcmd/jhsdb, nếu thu được
├── proc-maps.txt             # mappings trước crash, nếu thu được
├── jvm-flags.txt
├── os-and-jdk.txt
├── binaries/
│   ├── libfoo.so             # đúng deployed build, không phải bản build lại
│   └── build-info.txt        # SHA-256, Build ID, kiến trúc, dependency
├── symbols/
│   └── libfoo.so.debug       # khớp Build ID hoặc debuglink
└── SHA256SUMS                # hash các artifact thực sự hiện diện
```

`repro.md` tối thiểu cần ghi: ngày giờ và timezone; host/container image **digest**; release commit/build pipeline ID; bản JDK đầy đủ (vendor/update/build/architecture); kernel/OS và libc; command line + JVM flags có liên quan (đã ẩn secret); input tối thiểu/seed/data shape; số luồng; tải hệ thống và điều kiện lặp; kết quả kỳ vọng/thực tế; bước chạy 1–2–3; tỉ lệ tái hiện (ví dụ 3/10 lần); dấu hiệu thành công của phép tái hiện; link artifact và checksum.

Ghi riêng **mức độ tái hiện**:

- *Reproduced*: thực sự chạy lại cùng trigger và thu được triệu chứng nhất quán.
- *Matched signature*: không tái hiện trực tiếp nhưng stack/signal/build evidence trùng sự cố.
- *Not yet reproduced*: mới có giả thuyết hoặc symbols chưa match; không được báo đã tìm nguyên nhân.

Để gửi nhóm khác, cung cấp danh sách những file **thực có**, chỉ rõ file nào thiếu và vì sao (kernel core disabled, dump bị truncate, JDK khác build, quyền attach, file symbol đã mất). Hash giúp phát hiện bundle bị thay đổi trên đường chuyển.

## 10. Checklist QA và lỗi rất thường gặp

| Dấu hiệu / sai lầm | Vì sao nguy hiểm | Cách kiểm tra/sửa |
| --- | --- | --- |
| Chỉ giữ `hs_err`, không có core | Thiếu register/memory/state để chứng minh native memory corruption | Chuẩn bị core capture trước khi crash, xác minh `core_pattern`/handler/giới hạn, hoặc nêu rõ core không khả dụng |
| Chỉ có `.hprof` cho `SIGSEGV` | `.hprof` không chứa đầy đủ native stacks và mapped memory | Thu OS core/dmp; chỉ dùng heap dump nếu cũng cần điều tra Java objects |
| `gdb` hiển thị `??`, `No debugging symbols found` | Bản binary strip hoặc thiếu file DWARF đúng build | Đối chiếu Build ID, `.gnu_debuglink`, symbol directory/`debuginfod`; lấy bản từ CI artifact |
| Stack trace khớp tên nhưng địa chỉ sai | Dùng file lib cùng tên khác binary/ABI, hoặc trừ ASLR load bias sai | So hash, Build ID/UUID/PDB GUID+Age, mapping đúng tiến trình |
| `UnsatisfiedLinkError` khi tái hiện | Thiếu thư viện, sai loader path/ABI/transitive dependencies | Kiểm tra `System.loadLibrary`, `java.library.path`, ELF NEEDED, architecture, container base image |
| `hs_err` chỉ ra `libc`/`libjvm` | Nơi crash không nhất thiết là nơi làm hỏng bộ nhớ | Phân tích toàn bộ thread stack và thời điểm lỗi; thử `-Xcheck:jni`/sanitizer ở lab |
| Đổi JVM, GC, compiler flags và libc cùng lúc | Không xác định biến nào làm lỗi biến mất/xuất hiện | Giữ baseline đúng artifact gốc, thay **một biến mỗi lượt** |
| Chỉ thu một thread dump của process treo | Khó nhận ra progress/deadlock/blocked JNI | Thu 2–3 mẫu cách nhau thời gian, lưu timestamp/stack đồng thời |
| File core rất nhỏ hoặc báo `missing` | Retention, quota, dump filter, quyền hoặc truncation | Kiểm tra `coredumpctl info`, resource limit, storage và kích thước trước khi phân tích |
| Chia sẻ core/log công khai | Dump có thể chứa tokens, dữ liệu người dùng, khóa và vùng nhớ nhạy cảm | Giữ bản gốc trong kho có ACL; chỉ gửi bản/đường chia sẻ được phê duyệt, áp dụng retention và mã hóa phù hợp |

**Chuẩn nghiệm thu:** có cách chạy lại hoặc điều kiện trigger có thể kiểm chứng; phiên bản JDK/OS/dependency được ghi; hash/build identity của native binaries rõ; symbols đúng build; artifact dump/log có thời điểm gắn với PID; báo cáo native + Java stack đã symbolicate khi khả thi; mọi thiếu sót được liệt kê; dữ liệu nhạy cảm được kiểm soát.

### Câu hỏi tự kiểm tra

1. Một bản `.so` và `.debug` cùng tên nhưng Build ID khác nhau. Có thể dùng để tìm dòng lỗi không? **Không**: phải lấy symbols cùng build.
2. `hs_err_pid` ghi `C [libbar.so+0x1234]`. Đã đủ chứng minh bug nằm ở `libbar.so`? **Chưa**: memory corruption có thể xảy ra trước đó ở thư viện khác.
3. Đã bật `-XX:+CreateCoredumpOnCrash` nhưng không có file `core` trong thư mục chạy. Điều gì cần kiểm tra? **`ulimit`/service limit, `core_pattern`, systemd handler, quyền, quota, container/host policy**, và `coredumpctl`.
4. Process đang treo và cần quan sát tiến triển, nên lấy gì trước khi restart? **Nhiều thread dumps theo thời gian**, JFR và runtime mappings nếu lấy được.
5. Bản deploy đúng nhưng `addr2line` vẫn hiện `??`. Nguyên nhân nào cần loại trừ? **Symbols thiếu hoặc mismatch, địa chỉ ELF VMA/load bias sai, file bị strip, compiler optimization**.

## 11. Tài liệu chuẩn để đối chiếu theo hệ điều hành và phiên bản

- [Oracle JDK Troubleshooting Guide — Troubleshoot System Crashes](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-system-crashes.html) — `hs_err`, fatal frame, JNI native crash.
- [Oracle JDK Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html) và [`jcmd` Reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html) — live diagnostics, thread/JFR/heap dump.
- [`jhsdb` Reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jhsdb.html) — đọc Java/native stacks từ core.
- [Inside Java — Failed to write core dump](https://inside.java/2021/04/30/failed-writing-core-dump/) — `CreateCoredumpOnCrash` và rào cản OS.
- [systemd coredumpctl](https://www.freedesktop.org/software/systemd/man/latest/coredumpctl.html) — liệt kê và xuất Linux core.
- [GNU GDB — Separate Debug Files](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Separate-Debug-Files.html) — Build ID, `debuglink` và `debuginfod`.
- [Microsoft — Collecting User-Mode Dumps](https://learn.microsoft.com/en-us/windows/win32/wer/collecting-user-mode-dumps) và [Sysinternals ProcDump](https://learn.microsoft.com/en-us/sysinternals/downloads/procdump) — Windows `.dmp`/WER.
- [LLDB command map](https://lldb.llvm.org/use/map.html) — thread, image, symbol trong LLDB.

Khi tái hiện một lỗi JNI/native, hãy giữ **bản binary đang chạy**, **debug symbols khớp binary** và **dấu vết runtime tại thời điểm lỗi** như ba phần của một chứng cứ duy nhất. Chỉ khi chúng được nối bằng build identity, timestamp, PID và bước tái hiện cụ thể thì một crash mới có thể được phân tích và kiểm chứng đáng tin cậy.
