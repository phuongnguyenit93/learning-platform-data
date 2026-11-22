# 3.3 Thu thập phiên bản, nhà cung cấp JDK, kiến trúc và đối số JVM thực tế

## Mục tiêu học tập

Khi một ứng dụng Java gặp lỗi khác nhau giữa máy phát triển, CI, container và production, câu hỏi đầu tiên không chỉ là “đã cài Java mấy?”. Cần chứng minh **tiến trình đang phục vụ yêu cầu thực sự chạy bằng JVM nào, do nhà cung cấp nào phát hành, trên kiến trúc gì và với những đối số/cờ nào**. Những dữ kiện này là cơ sở để giải thích khác biệt về garbage collector, JIT, module access, TLS, native library, giới hạn bộ nhớ và hành vi của công cụ chẩn đoán.

Sau bài này, bạn có thể:

- Nhận diện đúng **PID và phiên chạy cụ thể**, kể cả khi một máy có nhiều JDK/JVM, container và process vừa restart.
- Thu thập phiên bản runtime, vendor, tên và phiên bản VM, Java home, OS/CPU architecture từ **chính JVM đích**.
- Phân biệt đối số JVM lúc khởi động, đối số của chương trình, system properties và các **VM flags có giá trị hiệu lực tại thời điểm đo**.
- Dùng `jcmd`, Java Management API và công cụ hệ điều hành phù hợp, biết khi nào `java -version`/biến `JAVA_HOME` có thể gây hiểu nhầm.
- Lưu bằng chứng có thời điểm, nguồn và mức độ chắc chắn, đồng thời loại bỏ thông tin nhạy cảm khỏi báo cáo sự cố.

## 1. Chính xác phải thu thập những gì?

Một “runtime fingerprint” có thể gồm các trường dưới đây. Không nhất thiết cần tất cả cho mọi ca, nhưng khi điều tra lỗi tương thích hoặc bất đồng giữa môi trường, thiếu một trong những nhóm chính có thể khiến kết luận sai.

| Nhóm | Dữ liệu nên có | Câu hỏi được trả lời |
| --- | --- | --- |
| Danh tính tiến trình | PID, máy/container/pod, thời điểm tiến trình bắt đầu, tên/phiên bản ứng dụng | Có đúng **lần chạy** đang xảy ra lỗi không? |
| Java runtime | `java.version`, `java.runtime.version`, `Runtime.version()`, `java.home` | Java đang chạy thuộc feature/patch/build nào, được nạp từ runtime image nào? |
| Nhà cung cấp/bản VM | `java.vendor`, `java.vm.vendor`, `java.vm.name`, `java.vm.version` | Bản phân phối JDK/runtime và implementation JVM thực sự là gì? |
| Kiến trúc/nền tảng | `os.name`, `os.version`, `os.arch`, kiến trúc host/container khi cần | JVM đích được dựng cho x86-64, AArch64 hay kiến trúc nào? |
| Startup command | Java launcher/đường dẫn thực thi, main class/JAR/module, JVM options, tham số ứng dụng | Tiến trình được khởi tạo như thế nào? |
| Runtime state | `VM.flags`, `VM.flags -all`, system properties đang có hiệu lực | JVM hiện dùng heap/GC/flags nào, kể cả các lựa chọn mặc định/ergonomic? |
| Nguồn cấu hình | service unit, container spec, start script, IDE/CI, `JDK_JAVA_OPTIONS`, `JAVA_TOOL_OPTIONS` | Các lựa chọn phát sinh từ đâu, có bị ghi đè không? |
| Bằng chứng | UTC timestamp, phương pháp lấy dữ liệu, bản ghi đã loại bí mật, lỗi attach nếu có | Bằng chứng được thu lúc nào, đáng tin đến đâu? |

Điểm mấu chốt: **phiên bản Java, vendor và cờ khởi động là thuộc tính của một tiến trình cụ thể**, không suy ra chắc chắn từ terminal hiện tại, máy build, file cấu hình dự kiến hay câu trả lời của một container khác.

## 2. Phân biệt JDK, Java runtime, Java launcher và JVM

- **JDK (Java Development Kit):** bản phân phối có các thành phần phát triển như `javac` cùng runtime; tùy image có thể có `jcmd`, `jfr`, `jlink`... Một ứng dụng có thể chạy trong **runtime image tối giản** không chứa compiler/công cụ chẩn đoán.
- **Java launcher (`java`):** chương trình khởi động JVM. Dòng `java -version` mô tả **chương trình `java` đang được shell chọn lúc đó**. Nó có thể hoàn toàn khác executable dùng để tạo service đang chạy.
- **JVM implementation:** máy ảo chạy bytecode, chẳng hạn HotSpot hoặc OpenJ9; cung cấp thông tin qua các property `java.vm.*`. Hai bản phân phối JDK cùng phiên bản Java có thể có đặc điểm VM, build hoặc tùy chọn khác nhau.
- **Java runtime image:** môi trường thực thi ứng dụng đang dùng, thường được chỉ bởi `java.home`. Nó có thể là JDK đầy đủ, image riêng tạo bởi `jlink`, hoặc runtime đi cùng một bản đóng gói ứng dụng.

Ví dụ: máy chủ cài `JAVA_HOME` trỏ tới JDK 21, còn service được start bằng đường dẫn tuyệt đối tới runtime 17 trong một container. Chạy `java -version` ngoài container cho ra Java 21 **không thể chứng minh** service dùng Java 21. Muốn biết sự thật, lấy thông tin từ JVM có đúng PID, process-start time và namespace.

Tương tự, `javac -version` cho biết compiler của **môi trường đang gọi lệnh**; không tự cho biết class được build bằng `--release` nào, lại càng không xác nhận JVM nào đang chạy class đó. Phiên bản bytecode được biên dịch và phiên bản runtime là hai thuộc tính cần kiểm chứng riêng khi gặp `UnsupportedClassVersionError`.

## 3. Xác định đúng tiến trình trước khi đọc thông tin JVM

**Bước 1 – Khoanh vùng:** ghi tên service, môi trường, host/container/pod và thời điểm xảy ra sự cố. Nếu có nhiều replica, phải xác định replica đang phục vụ request lỗi; dữ liệu một replica khác không đủ để giải thích sự cố.

**Bước 2 – Xác nhận PID:** với JDK có `jcmd`, lệnh:

```bash
jcmd -l
```

có thể liệt kê các JVM nhìn thấy được cùng PID và thông tin main class/command. Tuy nhiên, theo hướng dẫn `jcmd` của JDK 21, việc liệt kê **không bao gồm một số tiến trình trong Docker namespace riêng**; có thể cần công cụ OS và thực thi lệnh trong đúng container. Không tùy tiện chọn JVM đầu danh sách.

Trên Linux, nếu biết PID từ process manager, có thể kiểm tra thông tin OS của PID:

```bash
ps -p 12345 -o pid,ppid,lstart,etime,comm,args
```

**12345 chỉ là PID giả định**. Dòng `args` có thể chứa token/mật khẩu; chỉ xem trong terminal được kiểm soát, **không đẩy nguyên văn** lên ticket/chat. PID được tái sử dụng sau restart; gắn PID với **process start time** để tránh đọc nhầm lần chạy mới.

Trên Windows/PowerShell, với quyền phù hợp có thể xem:

```powershell
Get-Process -Id 12345
Get-CimInstance Win32_Process -Filter 'ProcessId = 12345' |
    Select-Object ProcessId, ExecutablePath, CommandLine
```

Thông tin command line trên Windows cũng có thể chứa bí mật. `Get-Process` xác nhận một process tồn tại nhưng chưa chắc đó là đúng JVM nếu chỉ nhìn tên `java`/`javaw`; cần đối chiếu thời điểm bắt đầu, executable, application và deployment.

**Bước 3 – Ràng buộc identity với dữ liệu JVM:** ngay trước khi chẩn đoán, đối chiếu PID và startup time với service/instance ID, version ứng dụng, log startup, container ID hoặc deployment revision. Khi có JVM tự báo PID, ưu tiên ghép với process metadata của cùng môi trường.

**Bước 4 – Kiểm tra có thể attach:** `jcmd` cần công cụ phù hợp, quyền tương thích và khả năng tiếp cận JVM đích; attach có thể bị vô hiệu hóa bằng JVM option, bị chặn bởi policy/container, namespace khác hoặc không có `jcmd` trong image. Lỗi attach **không chứng minh** ứng dụng không chạy Java.

## 4. Bộ lệnh read-only với JDK 21: hỏi trực tiếp JVM đang chạy

Sau khi kiểm tra PID và quyền truy cập, dùng công cụ `jcmd` tương thích với VM đích; trong môi trường HotSpot/JDK 21, một phiên chẩn đoán điển hình là:

```bash
jcmd 12345 help
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 VM.flags -all
jcmd 12345 VM.uptime
```

Ý nghĩa từng lệnh:

| Lệnh | Thu được điều gì? | Giới hạn diễn giải |
| --- | --- | --- |
| `jcmd 12345 help` | Danh sách diagnostic command JVM đích hỗ trợ | Command thay đổi theo implementation và phiên bản; không giả định mọi JVM đều có cùng lệnh |
| `VM.version` | Thông tin phiên bản VM hiện chạy | Không phải kết quả `java -version` của terminal |
| `VM.command_line` | Thông tin command line dùng khởi tạo VM | Có thể chứa secrets, Java/VM options và app command; không phản ánh mọi thay đổi runtime sau launch |
| `VM.flags` | Những VM flag/value có hiệu lực mà lệnh này trình bày | Không phải toàn bộ tham số launcher hoặc đối số ứng dụng |
| `VM.flags -all` | Tập flag JVM được hỗ trợ và giá trị hiện tại, có thể có dấu hiệu nguồn/default theo VM | Dài và phụ thuộc HotSpot/phiên bản; không có nghĩa mọi flag là startup option do người vận hành tự đặt |
| `VM.uptime` | Uptime tiến trình JVM | Dùng đối chiếu lần chạy/PID; không thay thế start timestamp và release ID |

Theo tài liệu Oracle JDK 21, các command trên có tác động **thấp**, nhưng “thấp” không đồng nghĩa 0; cân nhắc chính sách vận hành và log audit. **Đặc biệt `VM.command_line` có khả năng chứa bí mật**; đọc ở nơi kiểm soát, chỉ công bố bản đã lọc.

Để đọc các thuộc tính Java/OS hiện tại, `VM.system_properties` có sẵn trên HotSpot:

```bash
jcmd 12345 VM.system_properties
```

Không đưa toàn bộ stdout lên nơi công khai. Một số ứng dụng lưu `-Dpassword`, `-Dtoken`, URL chứa credential, truststore password hoặc key ở system properties; chính lệnh đọc không làm thay đổi JVM, nhưng **đầu ra có rủi ro lộ dữ liệu**.

Trên Linux/macOS, nếu cần chỉ một số key phi nhạy cảm, có thể lọc đầu ra cục bộ:

```bash
jcmd 12345 VM.system_properties |
  grep -E '^(java\.(version|runtime\.version|vendor|vm\.(name|vendor|version)|home)|os\.(name|arch|version))='
```

Đoạn trên **chỉ trình bày** các property khớp biểu thức regex; các giá trị lấy từ JVM thực tế. Với các hệ thống kiểm soát đầu ra nghiêm ngặt, nên dùng một công cụ/chương trình thu **allowlist ngay tại nguồn** thay cho lệnh in toàn bộ rồi lọc. Nếu thuộc tính nào không xuất hiện, ghi nhận nó không có thay vì suy diễn.

Khi hỗ trợ HotSpot, `VM.info` còn cung cấp thông tin môi trường/trạng thái rộng hơn, nhưng thường không cần cho bước thu identity cơ bản và có thể tăng lượng dữ liệu phải xử lý. Chỉ dùng nếu cần thêm ngữ cảnh và xem lại trường thông tin trước khi lưu.

## 5. Đọc đúng phiên bản và nhà cung cấp

### 5.1 Những property không được đánh đồng

| Trường | Ý nghĩa |
| --- | --- |
| `java.version` | Version runtime Java, chẳng hạn nhánh `17.0.x` hoặc `21.0.x` |
| `java.runtime.version` | Chuỗi version runtime chi tiết hơn nếu runtime cung cấp; thường kèm build |
| `Runtime.version()` | API Java 9+ cho cấu trúc phiên bản runtime; `feature()` lấy feature release như 17 hoặc 21 |
| `java.specification.version` | Phiên bản đặc tả Java SE mà runtime hỗ trợ; không phải patch/build/vendor |
| `java.version.date` | Ngày phát hành runtime nếu runtime có thuộc tính đó |
| `java.vendor` | Vendor **runtime/distribution** theo thông tin được công bố |
| `java.vm.name` | Tên VM implementation |
| `java.vm.vendor` | Vendor VM implementation |
| `java.vm.version` | Chuỗi version/build của VM |
| `java.home` | Đường dẫn môi trường runtime trong process, không mặc nhiên là `JAVA_HOME` của shell |

Không thể suy ra vendor chỉ từ số `21.0.4`; các vendor có thể cung cấp cùng feature/patch release nhưng khác build, CA/certificates, chính sách patch và native libraries. Tên `OpenJDK` trong dòng `java -version` **không xác định duy nhất** công ty phát hành bản phân phối. Tên `HotSpot` hay `OpenJ9` thể hiện implementation VM chứ không nhất thiết trùng tên vendor của package.

Khi kiểm tra một sự cố tương thích, cần ghi **đủ bộ version + runtime vendor + VM name/vendor/version**, không chỉ “Java 21”. Nếu cần kiểm chứng bản vá CVE cụ thể, đối chiếu dữ liệu phát hành và nguồn image/runtime của đúng vendor; chỉ dựa vào version major là không đủ.

### 5.2 Quy tắc so sánh version

- `Runtime.version().feature()` cho biết **feature release**, hữu ích khi cần điều kiện API/bytecode. `21` và `17` là các phiên bản feature khác nhau.
- Chuỗi build/patch cần giữ nguyên từ JVM đích; **không tự đoán** build metadata theo Java feature. Một JDK 21 chạy trên máy build chưa chắc giống JDK 21.0.x trên máy production.
- `java.vm.version` và `java.runtime.version` có thể dùng định dạng khác nhau tùy vendor; không nối hoặc thay thế tùy ý.
- Một image có runtime Java 21 vẫn có thể chạy class bytecode được biên dịch cho Java 17; chiều ngược lại không tự đúng. Khi kiểm tra `UnsupportedClassVersionError`, cần xác minh **class-file major version** của artifact bị lỗi và runtime version đích.

### 5.3 Không dùng shell như bằng chứng duy nhất

Các lệnh:

```bash
command -v java
java -version
javac -version
```

chỉ mô tả các executable/phiên bản mà **terminal đang truy cập**. Trên máy có `PATH`, `JAVA_HOME`, alternatives, SDK manager, IDE, Gradle toolchain, `jlink` image hoặc container, kết quả đó có thể khác JVM service đang chạy.

Trên PowerShell:

```powershell
Get-Command java
java -version
javac -version
$env:JAVA_HOME
```

Các lệnh có giá trị để kiểm tra **môi trường đang thao tác**, nhưng muốn chứng minh thuộc tính JVM service, phải đọc từ **process đó**. Dòng `java -version` của một container cũng chỉ đúng với process mới được tạo bởi `java` tìm thấy trong container ấy, chưa chắc khớp service dùng executable riêng.

## 6. Xác định kiến trúc: JVM, hệ điều hành và host có thể khác nhau

`os.arch` trong Java system properties mô tả tên kiến trúc nền tảng nhìn từ runtime Java, thường có giá trị như `amd64`, `x86_64`, `aarch64` hoặc `x86` tùy JVM/OS. `os.name` và `os.version` cho bối cảnh OS. Khi cần bằng chứng bitness hay ABI native, cần đối chiếu thêm **kiến trúc binary JVM/native library và kiến trúc process**, không tự suy luận chỉ từ tên biến môi trường host.

Phân biệt ba lớp:

1. **Host/hardware:** CPU kiến trúc vật lý của máy hoặc node.
2. **OS/container:** OS kernel và execution environment; container thường chia sẻ kernel host nhưng có image/runtime riêng, có thể chạy lớp giả lập khi nền tảng khác.
3. **JVM đích:** binary JVM và native libraries mà process thực sự nạp. `os.arch` từ JVM đích giúp định vị sự khác biệt với host.

Ví dụ giả định: laptop dùng CPU ARM64 nhưng container chạy image `linux/amd64` qua emulation; `uname -m` trên host có thể báo ARM64 trong khi JVM trong image tự nhận `amd64`. Kết luận về JNI, native codec, agent hay JIT phải dùng kiến trúc **JVM thực chạy** và các thư viện native tương ứng, không dùng hostname hoặc kết quả `uname` ngoài container làm bằng chứng duy nhất.

Trên Linux, lệnh sau đọc kiến trúc kernel của **môi trường đang chạy lệnh**, không trực tiếp xác nhận bitness của một JVM khác namespace:

```bash
uname -m
```

Cũng không được nhầm `os.arch` với cấu hình **memory** của VM: `-Xmx2g` mô tả ngưỡng Java heap, không chứng minh CPU architecture, và RSS của process có thể bao gồm native memory ngoài heap. Container memory/CPU quota còn ảnh hưởng kích thước heap được chọn theo tỷ lệ, thread count và performance; khi điều tra, ghi riêng resource limits cùng VM flags nếu liên quan.

### Dấu hiệu thường gặp trong lỗi kiến trúc

- `UnsatisfiedLinkError`, “wrong ELF class”, “mach-o wrong architecture”, lỗi nạp DLL/`.so`/`.dylib`: kiểm tra `os.arch`, ABI, bitness của **process và native library**.
- Native agent cung cấp bản `linux-amd64` nhưng JVM chạy `aarch64`: đối chiếu distribution/architecture của agent và Java runtime image.
- Performance khác nhau giữa hai node dù cùng Java feature release: so sánh vendor/build, architecture, container resource limits, effective GC/JIT flags và workload, không gán ngay cho version major.

## 7. Phân biệt bốn lớp “đối số JVM thực tế”

Hãy xem một dòng khởi động minh họa:

```bash
java -Xms256m -Xmx2g -XX:+UseG1GC -Ddiag.region=ap-southeast-1 \
     -jar service.jar --batch-size=100
```

Đây là lệnh **minh họa** và không bảo đảm ứng dụng nào cũng hiểu `--batch-size`. Ý nghĩa các phần:

| Thành phần | Nhóm | Cách xác minh |
| --- | --- | --- |
| `java` | Executable launcher | Process executable/OS metadata, `java.home` và identity của JVM |
| `-Xms256m` | JVM startup heap option | `VM.command_line`, `RuntimeMXBean.getInputArguments()`; giá trị runtime liên quan là `InitialHeapSize` |
| `-Xmx2g` | JVM startup heap limit | Command line; kiểm tra `MaxHeapSize` bằng `VM.flags`/`VM.flags -all` |
| `-XX:+UseG1GC` | VM flag do người cấu hình | Command line và effective flags (tên/hỗ trợ khác theo VM) |
| `-Ddiag.region=...` | System property lúc khởi động | `VM.command_line` hoặc VM input args; property hiện tại qua `System.getProperty` |
| `-jar service.jar` | Launcher chọn artifact | Command line/OS metadata; runtime image không chứa thông tin hash artifact mặc định |
| `--batch-size=100` | **Đối số ứng dụng**, nằm sau `-jar` | `main(String[] args)`, app config hoặc command line; không nằm trong danh sách VM input arguments |

**Lớp A – JVM input arguments tại startup:** `ManagementFactory.getRuntimeMXBean().getInputArguments()` phản ánh input arguments chuyển vào VM theo implementation; thường có `-X`, `-XX`, `-D`, `--add-opens`, `-javaagent` nếu được truyền vào VM. Theo API Java, danh sách này **không chứa đối số của `main()`**, và không bảo đảm chứa mọi tùy chọn của chính `java` launcher.

**Lớp B – Command line lúc khởi động:** `jcmd PID VM.command_line` mô tả lệnh dùng để khởi tạo VM; tùy implementation, cách hiển thị và mức phục hồi nguyên chuỗi shell có thể khác nhau. Quote/expansion của shell, wrapper script và `@argfile` có thể khiến thứ tự/cú pháp gốc trong file deploy khác dạng VM nhìn thấy. Command line cũng có thể gồm app arguments và thông tin nhạy cảm.

**Lớp C – System properties đang tồn tại:** `System.getProperty("key")`/`VM.system_properties` lấy **giá trị hiện tại**. Một property có thể được đặt qua `-D` lúc startup rồi đổi qua `System.setProperty` trong code. Do đó **giá trị hiện tại không chứng minh mọi nguồn và giá trị ở thời điểm launch**.

**Lớp D – VM flags đang có hiệu lực:** `jcmd PID VM.flags` và `VM.flags -all` cho thấy state/giá trị được VM hỗ trợ trình bày. JVM có thể tự chọn flags theo ergonomics, CPU/RAM/container; không thấy một `-XX` option trong startup không có nghĩa VM không có giá trị cho flag đó. Một số flag được hỗ trợ thay đổi động; **current value** có thể khác startup value. `VM.flags` không tương đương “tập nguyên văn toàn bộ command line”.

### “Nguồn cấu hình dự kiến” không bằng “giá trị thực tế”

| Nguồn | Điều có thể chứng minh | Điều chưa thể chứng minh |
| --- | --- | --- |
| Dockerfile hoặc manifest Deployment | Image/config **được khai báo** | Replica đang chạy được tạo từ digest nào, entrypoint đã biến đổi gì |
| CI/Gradle toolchain | JDK dùng để build/compile theo cấu hình | JDK nào đã thực thi service |
| Shell `JAVA_HOME`, `PATH` | Môi trường của terminal hiện tại | Môi trường lúc service launch, executable được wrapper chọn |
| Service unit/start script | Các tùy chọn dự định cấp cho process | Các biến env, options file, override, restart ngoài ý muốn |
| `VM.command_line` + `RuntimeMXBean` | Input startup mà JVM báo cáo | Toàn bộ config app hiện tại và mọi VM flag ergonomic |
| `VM.flags -all` + system properties | State VM/property tại thời điểm đọc | Ai đã thay chúng, và mọi tham số command line ban đầu |

Hai biến môi trường rất dễ bị bỏ sót:

- **`JDK_JAVA_OPTIONS`**: được Java launcher hỗ trợ để đưa thêm tùy chọn vào trước các đối số launcher; giá trị trong runtime của service có thể không giống shell đang kiểm tra.
- **`JAVA_TOOL_OPTIONS`**: có thể đưa VM options từ môi trường khi khởi tạo VM trong các điều kiện được hỗ trợ; hành vi cụ thể phụ thuộc launcher/VM. Không giả định chuỗi env đó tự động được ghi đầy đủ trong báo cáo `VM.command_line`.

Ngoài ra còn wrapper script, IDE run configuration, biến môi trường của orchestrator, launch arguments từ systemd/Windows service và `@argfile`. Khi thấy sai khác, đối chiếu **startup input + runtime flag/property + nguồn deploy thực tế**. Đừng suy diễn “mọi flags trong `VM.flags -all` đều do operator truyền”, cũng đừng nghĩ option có chữ `-D` luôn phản ánh app đã dùng giá trị đó để cấu hình mọi thành phần: một số framework chỉ đọc property một lần lúc startup.

## 8. Thực hành Java 17+: in runtime fingerprint từ chính JVM

Đây là cách chủ động thu thập khi attach không khả dụng: dùng API Java có sẵn trong ứng dụng để xuất ra **allowlist thuộc tính không chứa credential**. Ví dụ chạy được với JDK 17+; kết quả version/vendor/architecture phụ thuộc máy nên không gán một dòng stdout giả định cho chúng.

Tạo tệp **`RuntimeFingerprint.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.time.Instant;
import java.util.List;

public final class RuntimeFingerprint {
    private static String property(String name) {
        return System.getProperty(name, "(khong-co)");
    }

    public static void main(String[] args) {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();

        // Hai dòng đầu xác định nhờ chính lệnh thực hành bên dưới.
        System.out.println("diag.mode=" + property("diag.mode"));
        System.out.println("applicationArgs.count=" + args.length);

        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.println("startTimeUtc=" +
                Instant.ofEpochMilli(runtime.getStartTime()));

        for (String name : List.of(
                "java.version",
                "java.runtime.version",
                "java.specification.version",
                "java.vendor",
                "java.vm.name",
                "java.vm.vendor",
                "java.vm.version",
                "java.home",
                "os.name",
                "os.version",
                "os.arch")) {
            System.out.println(name + "=" + property(name));
        }

        System.out.println("runtimeFeature=" + Runtime.version().feature());

        List<String> heapStartupArgs = runtime.getInputArguments().stream()
                .filter(s -> s.startsWith("-Xms") || s.startsWith("-Xmx"))
                .toList();
        System.out.println("selectedHeapInputArgs=" + heapStartupArgs);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac RuntimeFingerprint.java
java -Xms64m -Xmx256m -Ddiag.mode=lab RuntimeFingerprint alpha beta
```

**Hai dòng stdout đầu tiên chính xác** cho lệnh thực hành (không phụ thuộc hệ điều hành):

```text
diag.mode=lab
applicationArgs.count=2
```

Các dòng sau gồm PID, thời điểm JVM được khởi tạo, version, vendor, runtime home, OS arch và `selectedHeapInputArgs`; **giá trị phụ thuộc runtime thực sự**. Với HotSpot/JDK tiêu chuẩn, các heap input arguments minh họa thường là `-Xms64m` và `-Xmx256m`, nhưng đừng coi mọi implementation buộc phải hiển thị chúng cùng dạng; hãy kiểm tra dữ liệu thu được.

Giải thích cơ chế:

- `ProcessHandle.current().pid()` xác định PID của **JVM đang chạy đoạn code này**, thay vì phỏng đoán PID từ tên `java` trên máy.
- `RuntimeMXBean.getStartTime()` cho epoch milliseconds xấp xỉ lúc VM khởi động; chuyển sang `Instant` để ghi thời gian UTC có thể tương quan với logs và uptime.
- `System.getProperty(...)` lấy giá trị **hiện tại**, không bảo đảm là giá trị bất biến từ thời điểm launch.
- `Runtime.version().feature()` chỉ là **feature release**; muốn giữ patch/build, phải lưu thêm chuỗi version chi tiết.
- `getInputArguments()` lọc chỉ `-Xms`/`-Xmx` để minh họa giới hạn thông tin, không in tất cả `-D`/agents vì nhiều ứng dụng chứa bí mật trong JVM arguments.
- `alpha` và `beta` là **đối số ứng dụng**, vì vậy `args.length == 2`; chúng không biến thành input arguments của JVM.

Lưu ý: đây là chương trình **mẫu được khởi chạy mới**, do đó chỉ mô tả **process mẫu đó**. Muốn chứng minh service đang lỗi dùng những giá trị nào, cần chạy cơ chế thu tương đương **bên trong đúng service**, hoặc dùng `jcmd`/JMX truy cập đúng PID. Đừng chạy `RuntimeFingerprint` trong một container mới rồi gán kết quả cho container production đã hoạt động nhiều ngày.

### Mở rộng qua JMX/Management API

Nếu ứng dụng đã có endpoint quản trị bảo mật phù hợp, có thể truy vấn `RuntimeMXBean` và bộ property **allowlist** từ chính service. MBean `java.lang:type=Runtime` có thông tin runtime như VM vendor, VM version, start time và input arguments. Không mở JMX remote vô điều kiện để tiện đọc version: endpoint quản trị phải có authentication, authorization, network restrictions và chính sách tiết lộ thông tin. Một endpoint diagnostics tùy biến nên xuất **chỉ các key được duyệt**, tránh cung cấp toàn bộ environment hoặc system properties.

Cần nhớ `RuntimeMXBean.getInputArguments()` có thể chứa secrets, còn `getSystemProperties()` có thể trả nhiều trường nhạy cảm. Dù API đó là read-only, **việc công bố đầu ra** vẫn phải tuân thủ phạm vi chia sẻ dữ liệu.

## 9. Một lượt thu thập bằng terminal: trình tự áp dụng được trong sự cố

Giả sử đang điều tra một process HotSpot/JDK 21 có PID **12345** trong đúng host/container. Lưu thời gian UTC của phiên đo và xác nhận PID thuộc đúng service **trước mỗi lần thu mới** nếu có autoscaling/restart.

```bash
# Kiểm tra các command có trên JVM đích.
jcmd 12345 help

# Version/build VM thực sự.
jcmd 12345 VM.version

# Startup command; chỉ dùng trong terminal có quyền, phải redact khi chia sẻ.
jcmd 12345 VM.command_line

# Giá trị flag hiện tại mà VM hỗ trợ báo cáo.
jcmd 12345 VM.flags

# Dùng khi cần điều tra default, ergonomics hoặc origin chi tiết.
jcmd 12345 VM.flags -all

# Uptime phục vụ đối chiếu đúng lần khởi động.
jcmd 12345 VM.uptime
```

Dòng lệnh trên **không thay đổi VM flags**. `jcmd` không tự có mặt trên mọi image, và một `jcmd` từ JDK khác vendor/version có thể không hỗ trợ đầy đủ các diagnostics của VM mục tiêu. Dùng công cụ phù hợp nhất với runtime/implementation khi có thể. Không khẳng định thứ tự hay output chính xác của `VM.command_line` nếu chưa đọc thực tế.

### Nếu attach bị từ chối hoặc không tìm thấy PID

Kiểm tra theo thứ tự:

1. **Đúng namespace chưa?** Process có thể chạy trong container khác; PID `1` trong container không nhất thiết là PID `1` ở host. `jcmd -l` phía host có thể không liệt kê container JVM.
2. **Đúng user/permission chưa?** Theo tài liệu Oracle JDK 21, `jcmd` cần chạy trên cùng máy và với effective user/group phù hợp. Service account và chính sách hệ thống có thể ngăn attach.
3. **Công cụ có trong image chưa?** Runtime `jlink`/distroless tối giản có thể không chứa `jcmd` hoặc shell. Không vội sửa/khởi động lại container chỉ để đưa thêm công cụ vào khi đang xử lý incident.
4. **JVM có tắt attach không?** Một số cấu hình có thể vô hiệu cơ chế attach, hoặc runtime khác HotSpot không hỗ trợ cùng tập lệnh.
5. **PID đã restart chưa?** So PID, start time, container ID và deployment revision với lúc ghi nhận sự cố.
6. **Có đường đọc từ bên trong ứng dụng không?** Dùng endpoint diagnostics/JMX đã được kiểm soát để truy vấn runtime identity; ghi rõ nguồn, tránh giả định dữ liệu từ process khác tương đương.

Trong Kubernetes, vị trí lấy bằng chứng quan trọng không kém câu lệnh: cần ghép **pod UID/container ID, image digest, node, restart count và PID trong namespace**. Nhiều pod có cùng tên logic hoặc cùng image tag nhưng không nhất thiết giống image digest/runtime flags tại thời điểm đọc.

### Khi chỉ có OS process metadata

OS có thể cung cấp executable path và raw command line, nhưng không bảo đảm hiển thị **all VM flags sau khi JVM chọn defaults** hoặc **system properties hiện tại**. Một script `/bin/sh -c ...`, Windows service wrapper hoặc process supervisor còn có thể làm người đọc nhầm **wrapper process** với JVM con. Ghi nguồn OS và mức độ chắc chắn; không tự nâng kết quả `ps`/Task Manager thành kết luận về GC hoặc heap đang dùng.

## 10. Đối chiếu cấu hình dự kiến với cấu hình đang có hiệu lực

Khi manifest nói `-Xmx2g` nhưng heap/GC hoạt động khác dự đoán, đừng dừng ở việc tìm chuỗi `-Xmx2g` trong YAML:

1. Xác nhận **đúng process** và phiên bản runtime/VM; kiểm tra Java executable, vendor, architecture và thời điểm startup.
2. Đọc **startup input** bằng `VM.command_line` và/hoặc `RuntimeMXBean.getInputArguments()` sau khi được cấp quyền.
3. Đọc **effective flags** bằng `VM.flags`/`VM.flags -all`, gồm `MaxHeapSize`, `InitialHeapSize`, GC options và flags có liên quan; phân biệt giá trị byte với cách viết `m`/`g` trong CLI.
4. Đối chiếu nguồn cấu hình: image entrypoint, process manager, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, options file, command line override, container limit và phiên bản VM.
5. Nếu chỉ đang so sánh môi trường, đọc trạng thái **đã tồn tại**; đừng dùng `VM.set_flag` để “thử” thay đổi cấu hình production trong bước thu thập identity.
6. Ghi rõ một flag nào là **explicit**, **ergonomic/default** hoặc **thay đổi lúc runtime** nếu công cụ/bằng chứng hỗ trợ; không gán nguồn khi không chắc.

Ví dụ `-Xmx` thường liên hệ với effective VM flag `MaxHeapSize`, nhưng các trường không nhất thiết hiển thị cùng cú pháp. Với môi trường container-aware, JVM có thể tính heap từ memory limits khi không truyền `-Xmx`. Một `MaxHeapSize` có giá trị không tự chứng minh người vận hành đã gõ `-Xmx`; cần dùng startup input và nguồn deployment để kết luận.

Lệnh `java -XX:+PrintFlagsFinal -version` (nếu VM hỗ trợ) cũng hiển thị các flag **của JVM mới được tạo bởi lệnh đó**. Nó có thể hữu ích khi dựng môi trường tái hiện, nhưng không thay thế `jcmd PID VM.flags -all` cho process đang chạy.

## 11. Thu và chia sẻ bằng chứng an toàn, có thể đối chiếu

**Nguyên tắc tối thiểu:** phần thông tin cần gửi ra ngoài phải là bản **đã xử lý bí mật và chỉ chứa các trường liên quan**. Đối số JVM, environment variables, system properties, shell history, URL, command line và các file cấu hình đều có thể mang token/password/path riêng tư.

Những dữ liệu đặc biệt cần kiểm tra trước khi lưu/chia sẻ:

- `-D...` có chứa password, access token, API key, JDBC URL có credential, proxy authentication hoặc truststore password.
- `-javaagent:`, `-agentpath:`, `--module-path` và `-cp` có thể lộ đường dẫn nội bộ.
- Application arguments sau `-jar`/main class có thể chứa secret; `jcmd -l`/OS `ps args` cũng có thể hiển thị chúng.
- `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` và toàn bộ environment có thể chứa dữ liệu nhạy cảm ngoài phạm vi câu hỏi về runtime.
- JMX hoặc `VM.system_properties` có thể lấy dữ liệu ứng dụng do framework/code bổ sung mà không liên quan đến JDK identity.

**Cách báo cáo:** lưu `java.version`, `java.runtime.version`, `java.vendor`, `java.vm.*`, `os.arch`, PID/process start time, tên source và một danh sách options **được phép công bố** (ví dụ heap/GC flags đã được kiểm tra). Với bí mật, dùng nhãn `[REDACTED]` trong bản báo cáo mà **không giữ lại giá trị hoặc số ký tự của token**. Không lưu raw `VM.command_line` trong tài liệu chia sẻ chung.

Một mẫu ghi nhận minh họa, **dữ liệu giả định**, là:

```yaml
captureTimeUtc: "2026-10-29T08:10:00Z"
scope:
  service: "catalog-api"
  environment: "staging"
  instance: "catalog-api-2"
  processId: 12345
  processStartUtc: "2026-10-29T07:42:00Z"
runtime:
  javaVersion: "21.0.4"
  javaRuntimeVersion: "21.0.4+7"
  javaVendor: "Vendor A"
  vmName: "OpenJDK 64-Bit Server VM"
  vmVendor: "Vendor A"
  vmVersion: "21.0.4+7"
  javaHome: "/opt/java/runtime"
platform:
  osName: "Linux"
  osArch: "amd64"
vm:
  explicitOptionsReviewed: ["-Xms256m", "-Xmx2g", "-XX:+UseG1GC"]
  effectiveMaxHeapSizeBytes: 2147483648
  commandLineShared: "REDACTED"
evidence:
  commands: ["VM.version", "VM.command_line", "VM.flags", "VM.system_properties"]
  source: "Attached to the target JVM using jcmd"
  incompleteFields: []
```

Không sử dụng các giá trị trên như “default của Java 21”: đó là **mẫu cấu trúc**, không phải output thực tế của bất kỳ process nào. Khi áp dụng, sửa mọi giá trị bằng dữ liệu từ JVM tương ứng và chỉ lưu những command đã chạy thật; nếu chưa lấy được trường nào, đánh dấu `unavailable` kèm lý do thay vì điền số gần đúng.

Muốn so sánh hai bản deploy, lập bảng chênh lệch theo **cùng trường**: process start, Java runtime full version, vendor, VM name/build, `os.arch`, effective heap/GC flags, các options explicit đã redact và hash/digest artifact/container nếu có. So sánh cùng timestamp hoặc cùng pha workload; tránh nhầm thay đổi do restart/deploy với thay đổi do runtime flag.

## 12. Tình huống điển hình

### Tình huống A – “Cả hai server đều dùng Java 21” nhưng một server lỗi

Server A và B đều báo `java -version` là Java 21 khi SSH vào, nhưng lỗi chỉ xuất hiện trên B. Đây mới là dữ liệu của **shell**. Điều tra trên đúng service PID ở cả hai:

1. Ghi PID, thời điểm process startup, container ID và build ứng dụng.
2. Lấy `VM.version`, `java.runtime.version`, `java.vendor`, `java.vm.name`, `java.vm.version`.
3. Đối chiếu `os.arch`, đường dẫn `java.home`, image digest và architecture.
4. So sánh startup args và effective flags sau khi redact.
5. Chỉ sau khi xác nhận khác biệt mới dựng lại lỗi hoặc kết luận phiên bản/vendor có liên hệ.

Kết quả có thể cho thấy service B thực tế chạy Java 17, một runtime build khác, kiến trúc khác hoặc thêm agent/flag dù terminal đang mặc định Java 21. Nếu mọi trường đều giống, những dữ liệu này giúp **loại bỏ một số giả thuyết cấu hình**, chưa loại bỏ lỗi workload, application state hoặc điều kiện mạng.

### Tình huống B – “Manifest đã khai báo `-Xmx2g`, sao JVM lại dùng heap khác?”

Bắt đầu từ `VM.command_line` để biết VM nhận input gì, rồi `VM.flags`/`VM.flags -all` để biết `MaxHeapSize` hiện tại. Kiểm tra service wrapper/entrypoint, override của deployment, container memory limits và các env/options files. Nếu chỉ đọc manifest mà bỏ qua process state, có thể chẩn đoán sai nguồn memory pressure. Nếu đọc mỗi `MaxHeapSize` mà không biết startup options, không phân biệt được explicit `-Xmx` với giá trị ergonomics.

### Tình huống C – Native library chạy tốt ở local nhưng không load được trong production

Thu `os.arch` từ JVM của cả hai nơi, ghi `java.vm.name`, version/vendor và binary type của JNI/native artifact. Kiểm tra OS, libc/ABI và dependency của library. Đừng lấy `uname -m` từ host thay cho kiến trúc process trong container. Một image cùng tag có thể trỏ tới variant ARM64 và amd64 khác nhau; so theo **digest + platform** nếu đang điều tra phân phối image.

### Tình huống D – Không thể dùng `jcmd` trong production image

Nếu runtime bị tối giản hoặc attach bị policy chặn, dùng telemetry/management endpoint được thiết kế sẵn để đưa ra allowlist thông tin ở mục 1. Nếu không có bằng chứng từ process, ghi mức độ hạn chế; đừng dùng `java -version` ở một debug container mới như lời khẳng định cho JVM đang chạy. Quyết định bổ sung chẩn đoán cho lần deploy sau cần qua quy trình phù hợp; bước thu identity không tự động cấp quyền thay runtime đang chạy.

## 13. Những nhầm lẫn cần tránh

| Nhầm lẫn | Điều đúng hơn |
| --- | --- |
| “`java -version` trên terminal là phiên bản JVM production.” | Terminal có thể dùng executable khác. Hỏi trực tiếp đúng process và xác nhận PID/start time. |
| “`JAVA_HOME` quyết định mọi JVM trên máy.” | Wrapper, service manager, đường dẫn tuyệt đối, image/container và toolchain có thể chọn runtime khác. |
| “`java.version` đủ để biết bản vá/vendor.” | Cần full runtime/build, distribution vendor và VM information, đôi khi cả image digest. |
| “`java.vendor` và `java.vm.vendor` luôn giống nhau.” | Hai property có ý nghĩa khác nhau; ghi nguyên văn thay vì suy đoán. |
| “`os.arch` của host luôn bằng của JVM.” | Container/emulation/native ABI có thể khác; lấy từ JVM thực tế. |
| “`VM.command_line` và `VM.flags -all` là cùng một thứ.” | Một bên là startup input, bên kia trình bày current flags, gồm default/ergonomic theo VM. |
| “Có `MaxHeapSize` nghĩa là có `-Xmx` được truyền từ operator.” | VM có thể chọn heap tự động; cần đối chiếu startup args và nguồn cấu hình. |
| “`RuntimeMXBean.getInputArguments()` chứa toàn bộ tham số sau `-jar`.” | Nó loại trừ `main()` args và không buộc chứa mọi launcher option. |
| “System properties đang xem luôn đúng bằng `-D` lúc launch.” | Ứng dụng có thể gọi `System.setProperty`; state hiện tại không chứng minh lịch sử. |
| “Không tìm được PID trong `jcmd -l` nghĩa là ứng dụng không chạy Java.” | PID namespace, container, quyền và công cụ có thể làm process không được liệt kê. |
| “Log raw command line tiện cho debug nên không có rủi ro.” | Đối số và system properties có thể chứa password/token; chỉ chia sẻ bản đã lọc. |
| “`-XX:+PrintFlagsFinal -version` mô tả service đang chạy.” | Đây là thông tin của **JVM mới** do lệnh đó tạo ra. |

## 14. Bài tập tự kiểm tra

**Câu 1.** Shell trên host báo JDK 21, nhưng JVM của service trả `java.version=17.0.x`. Nên ghi phiên bản nào trong báo cáo incident?

**Trả lời:** runtime 17.0.x của **đúng service process**, cùng vendor/build và nguồn đọc. JDK 21 của shell có thể ghi như một quan sát về môi trường, không dùng thay thế sự thật của service.

**Câu 2.** `RuntimeMXBean.getInputArguments()` không có `--batch-size=100`, có phải lệnh launch thiếu tham số?

**Trả lời:** không. Nếu `--batch-size=100` đứng sau main class hoặc `-jar service.jar`, đó là app argument; API trả JVM input arguments, không trả `main(String[] args)`.

**Câu 3.** `VM.flags -all` báo `MaxHeapSize` nhưng `VM.command_line` không thấy `-Xmx`. Có mâu thuẫn không?

**Trả lời:** không. `MaxHeapSize` luôn có giá trị được JVM xác định, có thể bằng default/ergonomics hoặc giới hạn tài nguyên môi trường, không buộc do explicit `-Xmx`.

**Câu 4.** Container trên host ARM64 báo `os.arch=amd64` từ chính service. Nên dựa vào giá trị nào khi tìm native library?

**Trả lời:** cần điều tra architecture/ABI của **JVM process và native artifact**. Giá trị JVM `os.arch=amd64` là dữ kiện trọng yếu; host ARM64 không tự chứng minh library ARM64 có thể được process amd64 nạp.

**Câu 5.** Có thể gửi ngay output `VM.command_line` và `VM.system_properties` vào ticket hay không?

**Trả lời:** chỉ khi đã kiểm tra và loại thông tin nhạy cảm theo chính sách. Lý tưởng là thu **allowlist** các trường cần thiết và ghi rằng dữ liệu nhạy cảm đã được loại khỏi bản chia sẻ.

**Câu 6.** `jcmd` không attach được vì service chạy với UID khác. Có nên dùng `java -version` ở shell của người điều tra để kết luận JVM version?

**Trả lời:** không. Cần dùng quyền và phương thức thu được phép, hoặc endpoint in-process đã có; ghi trạng thái **chưa xác minh** nếu chưa thể lấy dữ liệu từ đúng JVM đích.

## 15. Checklist thực hành cho một incident

- Xác nhận đúng **service, host/container, PID và start time**; khi có thể ghi application build/deployment digest.
- Thu từ đúng JVM: **Java runtime version đầy đủ; `java.vendor`; `java.vm.name`, `java.vm.vendor`, `java.vm.version`; `java.home`; `os.name` và `os.arch`**.
- Thu startup VM options và active flags bằng công cụ được hỗ trợ; ghi rõ **nguồn**, time UTC, command, tool version và giới hạn attach.
- Tách **VM input arguments**, **app arguments**, **system properties hiện tại** và **effective VM flags**.
- So sánh các nguồn dự kiến (manifest/IDE/service script/CI/JDK env) với **thông tin thực**; chú ý container architecture, resources, env injection và phiên bản runtime image.
- Kiểm tra/redact secrets trước khi lưu file hay gửi báo cáo; chỉ dùng các dữ kiện có thể kiểm chứng và đánh dấu trường chưa đọc được.

**Nguyên tắc kết luận:** dữ liệu của JVM đích tại đúng thời điểm có giá trị hơn cấu hình được kỳ vọng. Thu version, vendor, architecture và arguments chỉ hữu ích khi chúng **được gắn với đúng process, đúng lần khởi động, nguồn đáng tin cậy và diễn giải đúng phạm vi**.

### Tài liệu tham khảo chính thức

- [Oracle JDK 21 — The `jcmd` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `jcmd -l`, `VM.version`, `VM.command_line`, `VM.flags`, `VM.system_properties`, yêu cầu về user/host.
- [Oracle JDK 21 — The `java` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): launcher, `-D`, `-X`, `-XX`, `@argfile`, `JDK_JAVA_OPTIONS` và phân biệt app arguments.
- [Java SE 21 — `System` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html): Java runtime, VM, OS properties.
- [Java SE 21 — `RuntimeMXBean` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/RuntimeMXBean.html): input arguments, start time, VM name/vendor/version và hệ thống quản trị.
- [Java SE 21 — `ProcessHandle` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html): PID và thông tin của process hiện hành.
