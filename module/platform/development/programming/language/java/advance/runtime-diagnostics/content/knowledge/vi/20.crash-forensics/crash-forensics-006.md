# 20.6. Core dump, executable và yêu cầu tương thích JDK hoặc kiến trúc khi phân tích

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt **core dump/crash dump của tiến trình** với `hs_err_pid*.log`, Java heap dump `.hprof`, thread dump và JFR `.jfr`.
- Giải thích vì sao phân tích sau crash cần **core + executable thực sự đã chạy + thư viện native/JDK tương ứng**, chứ không chỉ một tệp `core`.
- Kiểm tra tính phù hợp của **OS, định dạng dump, kiến trúc CPU, 32/64-bit, JDK vendor/version/build, `libjvm`, native libraries và debug symbols**.
- Thực hiện workflow Linux với `file`, `readelf`, `sha256sum`, `coredumpctl`, `jhsdb` và `gdb`; hiểu điều gì khác trên Windows/macOS.
- Nhận diện trường hợp **không có core, core bị cắt/thiếu mapping, binary lệch bản**, cùng các rủi ro bảo mật khi lưu/chia sẻ dump.

**Phạm vi:** HotSpot/OpenJDK trong quá trình **phân tích sau lỗi (postmortem)**. Ví dụ tập trung Linux ELF core; Windows và macOS có dump/debugger/định dạng khác. Lệnh minh họa không tự tạo crash trên hệ thống thật. Một bản core từ tiến trình có thể chứa dữ liệu cực kỳ nhạy cảm; mọi bước cần tuân theo chính sách bảo mật.

## 1. Trước hết: bạn đang có loại hiện vật nào?

Khi ứng dụng Java bị lỗi, không phải mọi tệp có chữ *dump* đều dùng được với cùng công cụ.

| Hiện vật | Nội dung chính | Công cụ thường dùng | Điều không nên nhầm |
|---|---|---|---|
| **Linux core file (ELF core)** | Ảnh chụp **một phần hoặc nhiều phần** address space, trạng thái thread/registers tại thời điểm process chết hoặc chụp dump | `gdb`, `jhsdb` với executable, libs phù hợp | Không phải một snapshot bảo đảm chứa toàn bộ RAM; có thể thiếu mapping |
| **Windows process dump `.dmp`** | Dump tiến trình theo loại full/minidump và chính sách thu thập | WinDbg/Windows debugger tương thích | Không mặc nhiên là ELF core dùng với Linux `gdb`/`jhsdb` |
| **macOS core/crash report** | Core có định dạng/phạm vi riêng; crash report có stack/metadata | `lldb` và công cụ Apple | Không phải Linux ELF; crash report không tự đồng nghĩa full core |
| **`hs_err_pid*.log`** | Báo cáo fatal error do HotSpot có thể sinh: signal/exception, problematic frame, JVM, OS, native libraries, registers/stack khi có | Trình đọc text, phân tích thủ công | Không phải tệp chứa toàn bộ process memory |
| **Java heap dump `.hprof`** | Object graph/heap Java tại lúc chụp | Eclipse MAT, VisualVM/heap analyzer | Không thay thế native frames/registers của core |
| **Thread dump** | Stack/trạng thái thread tại thời điểm chụp | `jcmd`, JFR/JMC, công cụ đọc text | Không chứa đầy đủ memory image và registers |
| **JFR `.jfr`** | Chuỗi event theo thời gian: GC, CPU samples, allocation, threads, I/O... nếu được bật | `jfr` CLI, JDK Mission Control | Không phải một post-crash core snapshot |

**Core dump** hữu ích nhất khi JVM/process **chết do native fault** như `SIGSEGV`, `SIGBUS`, `SIGILL` hoặc `SIGABRT` trên Linux (tùy OS/signal/config). Nó cho phép hỏi: thread nào gặp fault, instruction pointer ở đâu, registers gì, Java/native stacks có ra sao, code và data tại địa chỉ đó thuộc binary/library nào.

**Lưu ý:** Java exception thông thường (`NullPointerException` trong code Java, chẳng hạn) **không tự tạo OS core dump**. `OutOfMemoryError` trong Java cũng không mặc nhiên tạo core; container/kernel OOM killer thường kết thúc bằng `SIGKILL`, vốn **không sinh core theo cơ chế signal crash**. Nếu chỉ có `ExitCode=137` trong container, ưu tiên kiểm tra cgroup/OOM events trước khi tìm core.

## 2. Vì sao core không đủ? Cần đúng executable và các thư viện

Trong Linux ELF, core chủ yếu giữ trạng thái process và những vùng memory được hệ điều hành chọn ghi. Các đoạn code, symbol table, debug info và một số mapped pages có thể **không nằm đầy đủ trong core**. Native debugger cần **executable** và các **shared libraries** tương ứng để ghép địa chỉ trong core với mã máy, hàm và stack.

Giả sử Java crash ở native code:

```text
Core:   PC = 0x7f...; TID = ...; registers; mappings; memory pages
          |
          +--- executable đã chạy: /opt/runtime/bin/java
          |
          +--- JVM library: /opt/runtime/lib/server/libjvm.so
          |
          +--- native/JNI libraries: libfoo.so, libbar.so, libc.so...
          |
          +--- debug symbols (nếu có): debuginfo, build-id, symbol files
          v
GDB: native backtrace, registers, instruction/symbol gần fault
jhsdb: cố gắng giải mã Java threads/HotSpot VM structures/heap
```

Nếu dùng **executable khác** hoặc `libjvm.so` sau khi đã upgrade:

- Debugger có thể vẫn mở được core, nhưng dùng symbol hoặc offsets **sai**.
- Stack có thể hiện `??`, frame vô nghĩa, sai địa chỉ hoặc dừng khi đọc dữ liệu JVM.
- Serviceability Agent trong `jhsdb` có thể không nhận ra layout/cấu trúc HotSpot, dù hai JDK đều ghi “Java 21”.
- Một kết quả mở được file **không chứng minh** mọi frame hay đối tượng đã được phân tích đúng.

**Khái niệm quan trọng:**

- **JDK version** là nhãn version (`21.0.x`, `24.0.x`), **không phải fingerprint đầy đủ**.
- **JDK vendor/distribution/build** cho biết sản phẩm và build cụ thể; ngay trong cùng một major version có thể khác patch, native layout, compiler flags hoặc native binary.
- **Executable** là *binary thực sự khởi động tiến trình*: thường là `bin/java`, nhưng JNI Invocation API hoặc custom launcher có thể khiến executable là một binary khác. Không mặc định `app.jar` chính là executable mà `jhsdb --exe` cần.
- **`libjvm`** là thư viện HotSpot native; riêng tên file giống nhau không chứng minh hash/build giống nhau.
- **Native/JNI/shared libraries** và libc/loader cũng ảnh hưởng việc dựng native backtrace; symbol packages phải khớp bản build.

### Một quy tắc thực hành

Để giảm sai số, ưu tiên **tái dựng đúng image/runtime của lần crash**: cùng OS ABI, CPU architecture, bộ binary JDK và thư viện được dùng, thêm debug symbols khớp **build ID** nếu có. Lưu bản sao có hash từ deployment artifact/container image, thay vì tải đại một JDK “cùng major” sau khi sự cố xảy ra.

Không phải mọi phép đọc sơ bộ đều yêu cầu exact build tuyệt đối: GDB có thể cho biết một số register/thread hoặc file format ngay cả khi symbols thiếu. Nhưng đối với **kết luận sâu về HotSpot object/heap/Java stack**, đồng nhất build là mục tiêu có giá trị đặc biệt cao; đừng coi dữ liệu từ bản lệch là đáng tin khi chưa xác minh.

## 3. Bảng kiểm tương thích trước khi mở core

| Lớp đối chiếu | Cần xác minh | Nếu sai sẽ thế nào? |
|---|---|---|
| **Định dạng** | Linux ELF core, Windows dump, macOS Mach-O core/crash report | Công cụ không mở được hoặc hiểu sai định dạng |
| **Kiến trúc máy** | `x86_64/amd64`, `aarch64/arm64`, ARM 32-bit... | Debugger native/SA không hỗ trợ cross-target; register và instruction set khác |
| **Word size & ABI** | 32/64-bit, endianness, ABI và OS phù hợp | Layout pointer/stack/register không tương thích |
| **Executable build** | Byte-for-byte binary hoặc build ID/hash phù hợp với thời điểm core | Symbol address/stack mapping có thể lệch |
| **JDK vendor/build/patch** | Java runtime/VM version, vendor, HotSpot implementation, build tương ứng | HotSpot SA có thể giải mã sai cấu trúc nội bộ |
| **`libjvm` và thư viện JDK** | Bản đã nạp khi crash, đúng đường dẫn/build ID | Native frames/HotSpot offsets có thể không khớp |
| **JNI/native libraries và libc** | Đúng versions, symbols, loader và đường dẫn mapping | Thiếu frame hoặc symbol trong thư viện gây crash |
| **Debug symbols** | Symbols cho executable/`libjvm`/native libs phải cùng build ID | Backtrace vẫn có thể có addresses nhưng ít tên hàm, file/line |
| **Tính toàn vẹn core** | File đầy đủ, hash, không truncate, đủ mappings được dump | Truy vấn memory/stack thất bại hoặc dữ liệu thiếu |
| **Bộ công cụ phân tích** | Phiên bản `gdb`/`jhsdb` tương thích hệ/bản JDK/định dạng | Gặp lỗi parser, Unsupported OS/CPU, symbol mismatch |

**Không đồng nhất các lớp:** cùng `os.arch=amd64` không bảo đảm cùng CPU feature set, libc hoặc binary. Cùng Java `21` không bảo đảm cùng `21.0.x+build`. Và một binary có hash đúng **không làm file core bị thiếu trang trở thành hoàn chỉnh**.

Đối với x86-64 so với AArch64, dùng `file`/`readelf` ở cả executable và core (trên Linux) để kiểm tra `Machine`, `Class` và `Data`. Việc phân tích cross-architecture chỉ khả thi khi debugger thật sự hỗ trợ target và đủ file/runtime tương ứng; với `jhsdb` không nên mặc định phân tích tùy ý từ một kiến trúc khác.

## 4. Thu thập hiện vật đúng lúc: trước khi rollout thay JDK/image

Một incident có thể bị mất khả năng phân tích khi team chỉ giữ file `core`, còn hệ thống CI/CD thay runtime sau restart. Khi vẫn còn truy cập metadata hợp pháp, ưu tiên giữ:

1. **Core file hoặc Windows dump** và checksum.
2. **`hs_err_pid*.log`** gắn cùng PID/incident (nếu HotSpot tạo được).
3. **Executable gốc**, toàn bộ JDK/runtime image đã dùng, đặc biệt `lib/server/libjvm.so` trên Linux HotSpot.
4. **Các native shared libraries** của ứng dụng/JNI, libc/loader liên quan, phiên bản OS/container image và bộ debug symbols tương ứng.
5. **Application JAR/config/flags/command line** của phiên bản deployment đã crash; log và JFR nếu đã được thu.
6. **Metadata tương quan:** UTC timestamp, PID/TID (lưu ý namespace container), host/pod/container ID, image **digest** chứ không chỉ tag, architecture và crash signal/exit code.

Nếu ứng dụng chạy trong container, hãy lưu **image digest** hoặc artifact bất biến. Một tag như `latest` hoặc `release-2026` có thể đã được trỏ sang image mới; chạy lại tag đó không bảo đảm lấy đúng thư viện đã map ở thời điểm crash.

### Trên Linux, khi tiến trình vẫn còn sống

Các lệnh sau **chỉ đọc thông tin**. Thay PID bằng số thực:

```bash
PID=12345

readlink -f "/proc/$PID/exe"
cat "/proc/$PID/cmdline" | tr '\0' ' '
grep -E 'libjvm|libc\.so|libjli|\.so' "/proc/$PID/maps"
cat "/proc/$PID/limits" | grep -i 'core file'
```

Thông tin `/proc/$PID/exe` giúp biết binary **thực sự đang chạy**, nhưng sau crash process đã biến mất, link này không còn. `/proc/$PID/maps` là các **mapping của lúc quan sát**; nếu thư viện đã thay thế/xóa sau đó, đường dẫn không đủ để khôi phục byte-for-byte version gốc. Những lệnh có thể yêu cầu quyền đọc đối với process khác; `cmdline` còn có thể chứa tham số nhạy cảm nên không chia sẻ bừa bãi.

Nếu tiến trình đã chết, dùng `hs_err`, metadata systemd-coredump, deployment inventory, container image digest, OS package database và các artifact đã lưu từ trước. Đừng khẳng định bản JDK trên **máy hiện tại** là bản đã crash khi có deployment thay thế.

## 5. Vì sao có khi không thấy core? Kiểm tra chính sách Linux

### 5.1. Hạn mức và cơ chế ghi

Trước khi chạy workload trong một môi trường **được phép cấu hình**, kiểm tra:

```bash
ulimit -c
cat /proc/sys/kernel/core_pattern
```

`ulimit -c` là soft core-file-size limit của **shell hiện tại**, không nhất thiết đúng limit của service đã chạy trước đó. `ulimit -c unlimited` trong shell chỉ ảnh hưởng shell và các process con; với systemd service thường cần cấu hình `LimitCORE=` hoặc chính sách service/container liên quan. Một `core_pattern` bắt đầu bằng ký tự `|` nghĩa là core được chuyển đến **user-space handler**, chẳng hạn `systemd-coredump`, thay vì xuất hiện như file `core` trong working directory.

Các lý do khác khiến file không xuất hiện:

- Crash không phát sinh signal có action dump core; ví dụ `SIGKILL` từ OOM killer.
- Cờ dumpable, quyền file/directory, container permissions, policy bảo mật hoặc quota không cho ghi.
- Filesystem đầy, core quá lớn, pipeline collector bị giới hạn, retention đã xóa.
- Mapping được loại theo `coredump_filter` hoặc `MADV_DONTDUMP`, làm **nội dung core thiếu một phần**.
- Một số trường hợp HotSpot tự ghi error log nhưng OS không tạo core; không có bằng chứng đủ để mặc định rằng cả hai luôn đi cùng nhau.

### 5.2. Nếu host dùng systemd-coredump

Khi đã xác định máy sử dụng `systemd-coredump`, với quyền thích hợp:

```bash
coredumpctl list
coredumpctl info 12345
coredumpctl dump 12345 -o core.12345
```

Thay `12345` bằng PID của incident. `coredumpctl` có thể không được cài, dữ liệu có thể bị giới hạn quyền/trữ lượng hoặc đã hết hạn retention; `PID` có thể trùng qua thời gian, nên đối chiếu **timestamp, executable, unit/host** trong metadata. Tệp trích xuất được phải lưu ở nơi an toàn.

Không chạy `kill -SEGV`, `kill -ABRT` hay ép crash lên production chỉ để thử core collection. Nếu cần test chính sách, dùng process thử nghiệm có chủ đích trong môi trường cách ly được phê duyệt.

### 5.3. hs_err và vị trí lưu

Khi HotSpot gặp fatal error, nó thường cố viết `hs_err_pid*.log`, nhưng thành công phụ thuộc trạng thái process và quyền filesystem. Có thể đặt đường dẫn mong muốn qua tùy chọn HotSpot:

```bash
java -XX:ErrorFile=/secure/java-crashes/hs_err_pid%p.log -jar app.jar
```

Ví dụ chỉ có ý nghĩa khi `/secure/java-crashes` tồn tại và process có quyền ghi; không tự tạo thư mục. Đường dẫn và tên tùy triển khai. Trong log, xem **JRE/VM version, problematic frame, signal/exception, current thread, native frames, dynamic libraries và memory map** khi có, đồng thời đọc thông điệp core dump location. Tệp log này là **bằng chứng đối chiếu**, không phải executable hoặc core.

## 6. Xác minh file và architecture trên Linux

Giả sử bạn đã đặt hiện vật trong một thư mục điều tra chỉ người được phép đọc, với file `core.12345` và bản executable đã lưu. Thay các đường dẫn minh họa bằng đường dẫn hiện có.

```bash
file /secure/incident/core.12345
file /secure/incident/jdk/bin/java

readelf -h /secure/incident/core.12345
readelf -h /secure/incident/jdk/bin/java

readelf -n /secure/incident/jdk/bin/java
readelf -n /secure/incident/jdk/lib/server/libjvm.so

sha256sum /secure/incident/core.12345 \
          /secure/incident/jdk/bin/java \
          /secure/incident/jdk/lib/server/libjvm.so

uname -m
```

Ý nghĩa:

- `file` nhận diện nhanh ELF core, binary ELF, kiến trúc và class 32/64-bit theo metadata; không đảm bảo file core chứa **đủ mọi trang**.
- `readelf -h` đọc ELF header: `Class`, `Data`, `Machine`, `Type`; có thể phát hiện mismatch 32/64-bit hoặc x86-64/AArch64.
- `readelf -n` hiển thị ELF notes, đôi khi có `Build ID` để đối chiếu binary và bộ debug symbols; không bảo đảm mọi build có build-id.
- `sha256sum` xác nhận byte integrity giữa bản lưu/bản chuyển, **không tự chứng minh** file được sinh từ cùng tiến trình nếu bạn không có checksum/inventory đáng tin tại thời điểm crash.
- `uname -m` báo architecture **máy đang phân tích**, không phải máy đã tạo core. Nếu đem core sang máy khác, kết luận architecture phải dựa trên **core/executable**, không dựa vào `uname` hiện tại.

Tệp `libjvm.so` có thể ở đường dẫn khác hoặc không hiện diện nếu VM không phải HotSpot/Linux thông thường. Dùng image/runtime gốc; không tự giả định cấu trúc khi phân phối JDK khác.

### 6.1. Các mức độ khớp không giống nhau

| Kết quả | Diễn giải |
|---|---|
| Core và executable đều ELF64 x86-64 | **Mới chỉ qua kiểm tra định dạng/architecture** |
| Cùng Java major `21` nhưng khác vendor hoặc patch | Chưa đáng tin cho phân tích HotSpot SA chuyên sâu; cần đúng build |
| Executable hash đúng nhưng `libjvm.so` đã bị thay sau deployment | Native symbols/HotSpot memory layout vẫn có thể sai |
| Build ID của `libjvm.so` khớp bản debug symbols | Khả năng dựng tên native functions/file:line tốt hơn |
| Core mở được nhưng thiếu một mapping quan trọng | Một số memory/stack/heap query sẽ thất bại dù executable đúng |
| Phân tích trên host khác OS/arch | Phải có debugger và target support tương ứng; không giả định `jhsdb`/`gdb` dùng được mọi tổ hợp |

## 7. Phân tích Java/HotSpot core bằng jhsdb (Serviceability Agent)

**`jhsdb`** là công cụ trong JDK sử dụng **Serviceability Agent (SA)** để đọc cấu trúc VM/Java từ tiến trình hoặc core. Đây là công cụ **experimental và unsupported** theo tài liệu Oracle Java SE 21. Nó phụ thuộc nhiều vào nội bộ HotSpot nên **càng cần JDK tương ứng**. Các ví dụ bên dưới minh họa cú pháp documented; không phải kết quả chạy trên một core thực ở đây.

### 7.1. Lệnh cơ bản với core và executable

```bash
jhsdb jstack \
  --exe /secure/incident/jdk/bin/java \
  --core /secure/incident/core.12345

jhsdb jstack --mixed \
  --exe /secure/incident/jdk/bin/java \
  --core /secure/incident/core.12345

jhsdb jinfo \
  --exe /secure/incident/jdk/bin/java \
  --core /secure/incident/core.12345
```

- `jhsdb jstack` cố dựng **Java threads/stack traces** từ core.
- `--mixed` cố bổ sung native frames khi nền tảng/tool hỗ trợ; không cam kết luôn dựng được mọi frame.
- `jhsdb jinfo` có thể lấy thông tin VM flags/properties.
- Có thể dùng `jhsdb jmap --heap` hoặc `--histo` với cặp `--exe`/`--core` khi khả năng của tool và core cho phép; phân tích heap lớn có thể tốn tài nguyên.

Nếu cần khám phá tương tác với cấu trúc HotSpot:

```bash
jhsdb clhsdb \
  --exe /secure/incident/jdk/bin/java \
  --core /secure/incident/core.12345
```

Lệnh sẽ mở **CLI debugger** tương tác. `jhsdb hsdb` là giao diện GUI khi có môi trường phù hợp. Không chạy những lệnh này trên production core chưa được cấp quyền; core chứa dữ liệu tiến trình, và tool có thể xử lý file không đáng tin, nên ưu tiên sandbox chẩn đoán cách ly.

**`--exe` là binary thực sự đã tạo core**, không phải tùy tiện file Java bytecode/JAR. Nếu ứng dụng nhúng JVM qua JNI Invocation API, executable có thể là native launcher khác `bin/java`. Không đổi `--exe` thành một `java` mới cài chỉ để làm command chạy được.

### 7.2. Cảnh báo quan trọng về attach live

Theo tài liệu Oracle, **attach `jhsdb` trực tiếp bằng `--pid` vào JVM đang chạy có thể làm process treo và có nguy cơ crash khi debugger detach**. Bài này tập trung **postmortem `--exe` + `--core`**. Không biến lệnh live attach thành routine production, đặc biệt khi sự cố đã có core để phân tích offline.

### 7.3. Diễn giải lỗi từ Serviceability Agent

Những biểu hiện như “không nhận ra VM layout”, lỗi đọc address, thiếu symbols hoặc stack bất thường có thể do:

- Sai `--exe` hoặc file thuộc **JDK khác build/vendor/version**.
- Thư viện `libjvm`/runtime không tương ứng với core.
- CPU architecture/OS ABI khác hoặc SA phiên bản dùng không hỗ trợ combination đó.
- Core thiếu mapping, bị truncate/corrupt hoặc thiếu page quan trọng.
- Core được tạo bởi một **native launcher** không phải file `bin/java` đã chỉ định.
- VM gặp hỏng memory thật tại thời điểm crash: một vài cấu trúc đã bị ghi đè, kể cả khi artifacts hoàn toàn đúng.

**Phân biệt “tool không phân tích được” với “tìm thấy lỗi ở ứng dụng”.** Phải xác nhận artifact compatibility và completeness trước khi kết luận vùng memory hỏng do bug.

## 8. Phân tích native crash với GDB và đúng symbols

**GDB** đọc ELF core cùng executable để xem **native frames, registers, thread states**. Nó không tự hiểu object graph của HotSpot theo cách `jhsdb` làm; khi JVM chạy JIT-compiled Java, GDB có thể chỉ thấy native entry/VM frames hoặc địa chỉ code cache mà không dựng đầy đủ Java stack.

### 8.1. Mở core

```bash
gdb -q /secure/incident/jdk/bin/java /secure/incident/core.12345
```

Trong phiên GDB (các dòng sau là **lệnh tương tác**, không phải stdout):

```text
info files
info sharedlibrary
info threads
thread apply all bt
bt full
info registers
```

- `info files`: quan sát executable, sections và các thông tin file của phiên debug.
- `info sharedlibrary`: xem các shared libraries GDB biết và trạng thái symbol.
- `info threads`: các OS threads trong core.
- `thread apply all bt`: dựng native backtrace cho các thread, giúp xem crash thread, JNI frames, libc/VM internals.
- `bt full`: chi tiết locals ở **thread đang chọn** nếu symbols/debug info cho phép.
- `info registers`: register values (ở thread đang chọn) để xem PC/SP, pointers và trạng thái fault.

Các lệnh này **không** làm core “chạy lại”; chúng đọc snapshot sau crash. Nếu bạn không có debug symbols, vẫn có thể đọc addresses/một số exported symbols, nhưng nhiều frame có thể thành `??`, không có file/line/locals.

### 8.2. Khi GDB đọc nhầm thư viện của máy phân tích

Nếu core đến từ container hoặc host khác, đường dẫn trong mappings có thể trùng nhưng **nội dung file trên máy phân tích khác**. GDB có thể báo missing shared libraries hoặc dùng bản host không phù hợp.

Cách điều tra là cung cấp **bản sao thư viện gốc** với cây đường dẫn thích hợp và cấu hình `sysroot`/`solib-search-path` theo tài liệu GDB, chẳng hạn:

```text
(gdb) set sysroot /secure/incident/rootfs
(gdb) set solib-search-path /secure/incident/native-libs
(gdb) info sharedlibrary
```

Đây là ví dụ **lệnh tương tác GDB**; phải có rootfs/native libs thực sự lấy từ container/image gốc, không tạo chúng bằng cách tự cài một gói cùng tên. Tùy cách GDB đã đọc libraries, có thể cần **khởi động lại phiên GDB hoặc reload symbols** sau khi sửa search path.

**Debug symbols cũng phải khớp build**: symbol package đúng tên nhưng build ID khác có thể gây stack sai hoặc thiếu line numbers. Khi có build ID, kiểm tra với `readelf -n` và hệ thống phân phối debuginfo. Có thể cùng **source code** mà binary khác do compiler flags hoặc linker; “cùng commit” chưa chắc cùng native address layout.

### 8.3. Tìm nguyên nhân từ “problematic frame”

Nếu `hs_err_pid*.log` nói:

```text
# SIGSEGV ... 
# Problematic frame:
# C  [libexample.so+0x1234]  example_call+0x...
```

Đây chỉ là **dạng minh họa**, không phải log từ một crash cụ thể. Hướng phân tích:

1. Xác nhận library `libexample.so` từ **image/deployment bị crash**, không lấy bản mới nhất.
2. Đối chiếu core thread/PC và native backtrace của GDB.
3. Kiểm tra JNI arguments, buffer/pointer lifetime, concurrency, memory corruption hoặc lỗi trong library.
4. Phân biệt **faulting instruction** với **root cause**: ghi đè bộ nhớ có thể xảy ra sớm hơn rồi crash ở một hàm khác.
5. Bổ sung sanitizer, test tái hiện native và vendor bug reports khi phù hợp.

Không kết luận “lỗi ở JVM” chỉ vì frame nằm trong `libjvm.so`: lỗi JNI hoặc memory corruption trước đó cũng có thể khiến VM crash. Ngược lại, có bug JVM thực sự, nên giữ đúng build và incident evidence để kiểm tra release notes/vendor support.

## 9. Java 17+ runnable: ghi lại manifest môi trường trước khi crash

**Mục đích:** luyện cách thu thập metadata runtime để sau này đối chiếu core với executable/JDK, **không** tạo crash và không giả vờ có sẵn core thật. Java API không thể tự xác nhận mọi mapping và checksum của native libraries; vì vậy ví dụ cung cấp dữ liệu **tham khảo**, phải ghép với OS tools và deployment inventory.

Tạo file **`CrashArtifactManifest.java`**:

```java
import java.nio.file.Path;
import java.util.Locale;

public class CrashArtifactManifest {
    private static void show(String name, String value) {
        System.out.println(name + "=" + value);
    }

    public static void main(String[] args) {
        String javaHome = System.getProperty("java.home");
        boolean windows = System.getProperty("os.name").toLowerCase(Locale.ROOT)
                .contains("windows");
        Path candidateJava = Path.of(javaHome, "bin",
                windows ? "java.exe" : "java");

        show("java.version", System.getProperty("java.version"));
        show("java.runtime.version", System.getProperty("java.runtime.version"));
        show("java.vm.name", System.getProperty("java.vm.name"));
        show("java.vm.version", System.getProperty("java.vm.version"));
        show("java.vm.vendor", System.getProperty("java.vm.vendor"));
        show("os.name", System.getProperty("os.name"));
        show("os.arch", System.getProperty("os.arch"));
        show("os.version", System.getProperty("os.version"));
        show("java.home", javaHome);
        show("candidate.java", candidateJava.toString());
        show("actual.command", ProcessHandle.current().info().command()
                .orElse("(unavailable)"));
        show("pid", Long.toString(ProcessHandle.current().pid()));
        System.out.println("Inventory complete");
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac --release 17 CrashArtifactManifest.java
java CrashArtifactManifest
```

Chương trình in **các khóa với giá trị phụ thuộc máy**. Ví dụ đầu ra rút gọn trên một máy Java 24 (**chỉ là minh họa, không phải stdout cố định**):

```text
java.version=24.0.2
java.runtime.version=24.0.2+12
java.vm.name=OpenJDK 64-Bit Server VM
java.vm.version=24.0.2+12
java.vm.vendor=...
os.name=...
os.arch=amd64
os.version=...
java.home=...
candidate.java=...
actual.command=...
pid=...
Inventory complete
```

Dòng cuối **`Inventory complete`** là cố định; PID, đường dẫn, OS/vendor/version **không cố định**. Ví dụ đã được biên dịch bằng `javac --release 17` và chạy thành công trên OpenJDK 24.

**Đọc output thế nào:**

- `java.vm.version` và `java.runtime.version` giúp nhận dạng build; khi có nhiều runtime trên máy, không chỉ dựa vào `java -version` của shell hiện tại.
- `java.home` và `candidate.java` là **ứng viên**, không phải bảo đảm binary thực sự đã khởi động. Trong ứng dụng nhúng JVM, `jlink` runtime image, custom launcher hoặc symlink, vị trí và executable có thể khác.
- `actual.command` lấy từ `ProcessHandle` có thể không được OS/JVM cho phép cung cấp, nên in `(unavailable)`; cũng không thay thế xác thực bằng hash/build ID.
- `os.arch` mô tả JVM/OS architecture theo thuộc tính Java, không phải kiểm tra ELF header của core tương lai.
- `pid` giúp liên kết log/dump, nhưng PID có thể tái sử dụng và khác nhau giữa host/container namespaces.

Trong production, thay vì tùy tiện in `java.home`/command line ra log công cộng, thu manifest dưới quyền vận hành, bảo vệ dữ liệu và lưu kèm deployment ID/image digest. Tập hợp cả file `hs_err`, JDK image và native libs sau khi xảy ra sự cố.

## 10. Khi phân tích trên Windows hoặc macOS

### 10.1. Windows

Trên Windows, process dump thường có đuôi `.dmp` và được mở bằng **WinDbg/Windows Debugger** với executable/DLL và **PDB symbols** phù hợp. Crash reports có thể dẫn đến minidump hoặc full dump; một **minidump chỉ chứa subset** memory/thông tin được collector cấu hình, nên nhiều biến/heap pages có thể không sẵn có.

Các điểm cần kiểm tra là **x64/ARM64/32-bit**, exception code, module versions, DLLs, PDB GUID/age, và mức độ đầy đủ của dump. Không dùng máy phân tích Linux ELF rồi giả định mở được mọi file `.dmp`. Đường dẫn `.dll` và cơ chế tải PDB khác với Linux `.so`/debuginfo. Khả năng dùng `jhsdb` với một loại Windows dump cụ thể còn tùy JDK/platform/định dạng, phải kiểm tra hỗ trợ thực tế.

### 10.2. macOS

Trên macOS, **Mach-O/dSYM** và **LLDB** là những công cụ/định dạng phổ biến để dựng native stack. Cần kiểm tra Apple Silicon `arm64` so với Intel `x86_64`, executable/framework/dylib versions và dSYM UUID phù hợp. Một **macOS crash report** thường cung cấp metadata/stack mà không bao gồm toàn bộ memory như core. Không đổi `.crash`/`.ips` thành `core` rồi áp lệnh Linux.

**Bài học chung:** core/dump phải được đọc bằng debugger hiểu **định dạng + CPU architecture + OS ABI** tương ứng, cùng binary/symbols của build đã crash. Khả năng phân tích khác kiến trúc/máy là **tính năng cần được xác minh**, không phải mặc định.

## 11. Sáu tình huống chẩn đoán thường gặp

| Hiện tượng | Giả thuyết cần kiểm tra | Bước xác minh |
|---|---|---|
| Có `core` nhưng `jhsdb` báo không đọc được VM | JDK/SA không đúng vendor/build, libjvm khác hoặc core thiếu trang | So build ID/hash của JDK, library mapping, format và completeness |
| GDB mở core nhưng nhiều `??` trong native stack | Thiếu debug symbols, bản thư viện lệch, optimized code hoặc corrupted stack | `info sharedlibrary`, rootfs/lib đúng, build IDs/debuginfo và `hs_err` |
| Core là ELF64 AArch64, công cụ chạy trên x86-64 | Target architecture/tool không tương thích | `readelf -h`, cross-target support; dùng môi trường phù hợp |
| Cùng tên `libjvm.so` nhưng stack đi vào offsets vô lý | Binary JDK đã bị thay bởi deployment mới | Tìm runtime image theo **digest/hash lúc crash**, không dùng bản mới |
| Process exit 137 trong Kubernetes, không có core | Cgroup/kernel OOM kill bằng SIGKILL | Pod last state, node logs, memory events, RSS/cgroup; không chờ core |
| `hs_err` tồn tại nhưng không có core | Limit/policy, disk/permission, systemd collector hoặc crash không dump được | `core_pattern`, `coredumpctl`, `ulimit/LimitCORE`, quota, dumpable |
| Core có data nhưng `jhsdb jmap` thiếu một vùng heap | Mappings không được dump, core truncated hoặc VM memory corrupted | `coredump_filter`, kiểm tra file size/collector, native maps |

**Tình huống A — Cùng JDK major, khác build.** Service chạy `21.0.5+...`, sau incident team nâng lên `21.0.6+...`. Tải bản `21.0.6` để phân tích core cũ có thể khiến SA không đọc được layout. Cách đúng là lấy lại runtime `21.0.5` **đúng distribution/build và libraries** từ release artifact hoặc container digest. Nếu không thể, vẫn có thể thử native GDB trên core để tìm một số signals/threads, nhưng phải báo rõ giới hạn độ tin cậy.

**Tình huống B — JVM được nhúng.** Process là `/opt/app/native-launcher` gọi JNI Invocation API để tạo JVM. `jhsdb --exe /opt/jdk/bin/java` có thể sai vì đó không phải executable đã tạo core. Phải lấy `native-launcher` tương ứng và các JDK libraries đã nạp.

**Tình huống C — Core từ container.** Team sao chép mỗi `core.1234` ra host, GDB vô tình dùng `/usr/lib/libc.so` của host. Native frames khác lạ. Giải pháp: giữ **image/rootfs gốc**, chỉ định GDB search path để dùng đúng libs và kiểm chứng build ID. Đừng tự tin kết luận root cause khi library mapping chưa khớp.

**Tình huống D — Core sau lỗi native nhưng Java heap histogram không dựng được.** Đây không nhất thiết là “Java heap trống”: có thể SA không tương thích, dump thiếu memory hoặc chính VM structures bị corruption. Hãy ưu tiên `hs_err`, native backtrace, registers, artifacts và tái hiện phù hợp.

**Tình huống E — Crash chỉ xuất hiện trên ARM.** Kiểm tra ARM64 image, JNI/native libraries, các optimized intrinsic/JIT paths và kernel/OS ABI. Không lấy x86-64 binary cùng source để phân tích ARM64 core rồi suy luận về instruction pointer.

**Tình huống F — Lỗi tưởng là native crash nhưng thực ra OOM kill.** Có exit 137, không thấy `hs_err`, không core. Điều tra event cgroup/OS và OOM pressure trước; nếu không có signal tạo dump thì không có cơ sở yêu cầu jhsdb đọc file core không tồn tại.

## 12. Bảo mật và tính nguyên vẹn của core

Core có thể chứa **passwords, tokens, TLS keys, customer data, heap objects, URLs, session information, request payloads** và nội dung đang có trong process memory. Trước khi thu/chuyển:

1. Xác định người **được phép** thu dump và mục đích điều tra; tuân theo quy trình incident/security.
2. Dùng thư mục có quyền chặt, mã hóa lưu trữ/chuyển giao và retention có hạn.
3. Ghi **hash SHA-256** và metadata để phát hiện thay đổi; không tự sửa/truncate core rồi coi vẫn là nguyên bản.
4. Tránh gửi core hoặc `hs_err` lên issue tracker/ticket công khai; error log cũng có thể chứa command line, environment và đường dẫn.
5. Phân tích trong môi trường được cách ly và có quyền, ưu tiên bản **copy**; không cài debugger mở port tùy tiện lên production.
6. Giữ cùng bộ artifacts ở dạng có thể tái lập, nhưng chỉ trong thời gian chính sách cho phép; hủy an toàn khi hết nhu cầu.

Dung lượng core có thể rất lớn. Trước khi cấu hình lưu hàng loạt, lập ngân sách disk, storage quota và cơ chế retention; crash nhiều lần có thể làm đầy filesystem nếu không kiểm soát.

## 13. Quy trình postmortem ngắn gọn có thể lặp lại

**Giai đoạn A — Xác minh sự cố**

1. Xác định **fatal JVM/native crash** hay Java exception, shutdown bình thường, SIGKILL/OOMKill.
2. Thu `hs_err`/OS signal/exit code, timestamp, PID/TID, host/pod, JDK build, image digest, application logs/JFR.
3. Xác nhận core/dump có thực sự được tạo, nằm ở collector nào và có đủ quyền truy cập.

**Giai đoạn B — Khóa tính đúng đắn của artifacts**

4. Sao lưu core, **executable thật**, JDK runtime (có `libjvm`), native libraries và debug symbols tương ứng.
5. Ghi checksum; xác minh core format/architecture; đối chiếu version/vendor/build/OS ABI và library build IDs.
6. Kiểm tra dấu hiệu core bị truncated, file thiếu, permission/sparse/filtered mapping.

**Giai đoạn C — Chọn công cụ đúng tầng**

7. Dùng `hs_err` để xác định problematic frame/signal/VM và library nghi vấn.
8. Trên Linux, dùng **GDB** với matching binary/libs để xem native crash; dùng **jhsdb với `--exe --core`** để cố dựng Java/HotSpot state khi phiên bản tool hỗ trợ.
9. Nếu symbol hoặc SA mismatch, sửa **artifact/tool compatibility** trước khi đưa kết luận từ stack/heap.

**Giai đoạn D — Tìm root cause và kiểm chứng**

10. Phân biệt điểm xảy ra fault với chỗ memory corruption/vi phạm invariant xảy ra sớm hơn.
11. Tìm testcase tái hiện trong môi trường cách ly; đối chiếu JNI/library/JVM patch release notes nếu nghi native bug.
12. Ghi **kết luận kèm mức độ tin cậy**, các file/symbols được xác minh và giới hạn của core; không nói “đã xác định root cause” chỉ vì thấy một frame.

### Những sai lầm cần tránh

- **“Có core là đủ, không cần executable.”** Sai: debugger thường cần binary và libraries để ánh xạ memory/địa chỉ sang code.
- **“Cùng Java 21 là chắc chắn tương thích.”** Sai: vendor, patch, build, architecture và HotSpot layout vẫn khác.
- **“Dùng `java` mới nhất để debug core cũ sẽ tốt hơn.”** Không nhất thiết, và có thể gây SA mismatch nghiêm trọng.
- **“`file core` nhận ra ELF64 nghĩa là core đầy đủ.”** Sai: header không chứng minh mọi page được lưu.
- **“`hs_err` và core cùng nội dung.”** Sai: một là text fatal-error report; một là memory/process snapshot.
- **“GDB báo `??` nghĩa là JVM không có stack.”** Sai: thường do symbol/library mismatch hoặc thiếu debug info; cũng có thể do corruption.
- **“Không có core là không phải crash.”** Sai: limits, handler, dumpable, disk, signal hoặc retention đều có thể ngăn core.
- **“Heap dump `.hprof` phân tích như ELF core.”** Sai: khác format, phạm vi và công cụ.
- **“Dùng native `gdb` đủ để hiểu mọi Java object.”** Sai: GDB không tự nắm HotSpot object model; cần SA phù hợp.
- **“Có thể tự do chia sẻ core vì chỉ chứa stack trace.”** Sai: core có thể chứa secrets và dữ liệu cá nhân.
- **“Thấy `libjvm.so` trong fault frame là chắc chắn bug HotSpot.”** Sai: JNI hoặc memory corruption từ trước có thể gây fault trong VM.

### Tự kiểm tra

1. Nếu process dùng JDK `21.0.5` đã crash, nhưng server vừa cập nhật lên JDK `21.0.6`, những file/version nào phải tìm lại trước khi chạy `jhsdb`?
2. Vì sao `gdb` có thể mở core nhưng không in ra tên đầy đủ của native frames?
3. Vì sao `--exe` của `jhsdb` có thể không phải `bin/java` với ứng dụng dùng JNI Invocation API?
4. Với file ELF core x86-64 và bản executable ARM64, bạn sẽ phát hiện mismatch bằng công cụ nào?
5. Tại sao exit code 137 hoặc Java `OutOfMemoryError` không tự bảo đảm có core?
6. `hs_err_pid*.log`, `.hprof`, `.jfr` và `core` trả lời các câu hỏi khác nhau ra sao?
7. Nếu core đã được lấy ra khỏi container, vì sao bản libc/native libraries trên host phân tích có thể gây kết luận sai?
8. Khi phải chuyển core cho nhóm hỗ trợ bên ngoài, những bước nào bảo vệ cả tính toàn vẹn lẫn bí mật dữ liệu?

## Tài liệu tham khảo

- [Oracle Java SE 21 — `jhsdb` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jhsdb.html): `--exe`/`--core`, các chế độ `jstack`/`jmap`/`jinfo` và trạng thái experimental.
- [Oracle Java SE 21 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): `jhsdb` với core, mixed Java/native stack và postmortem tools.
- [Oracle Java SE 21 — Prepare Java for Troubleshooting](https://docs.oracle.com/en/java/javase/21/troubleshoot/prepare-java-troubleshooting.html): thu core, fatal error log và các hiện vật cần giữ.
- [Linux `core(5)` — man-pages](https://man7.org/linux/man-pages/man5/core.5.html): core limits, `core_pattern`, filtered mappings và systemd-coredump.
- [GDB Manual — Executable and Core Files](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Files.html): cách GDB dùng binary, core, symbols và sysroot/shared-library search path.
- [GDB Manual — Core File Generation](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Core-File-Generation.html): core như snapshot memory/process status và `gcore` trong ngữ cảnh được phép.
