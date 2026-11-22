# Đo startup, memory và class loading

Hiệu năng của một ứng dụng Java không chỉ là thời gian xử lý một request. Với ứng dụng modular, đặc biệt là command-line tool, service nhỏ hoặc runtime image được tạo bằng `jlink`, cần quan sát ít nhất ba khía cạnh: **startup latency**, **memory footprint** và **class loading**.

Ba khía cạnh này có liên quan nhưng không thể thay thế cho nhau. Startup time đo thời gian tiến trình đi từ lúc khởi chạy đến một mốc sẵn sàng đã định nghĩa. Memory cần phân biệt heap với bộ nhớ toàn tiến trình. Class-loading log cho biết class nào được nạp, từ đâu và vào thời điểm nào; nó hỗ trợ giải thích startup và footprint nhưng bản thân số lượng class không phải thước đo hiệu năng đầy đủ.

Bài này dùng JDK 21 và các công cụ có sẵn trong JDK như `time`, `Measure-Command`, `jcmd`, `jstat`, Java Flight Recorder (JFR) và Unified Logging.

## 1. Xác định chính xác điều cần đo

Trước khi chạy benchmark, hãy định nghĩa mốc đo:

- **Process startup**: từ lúc hệ điều hành tạo tiến trình Java đến khi tiến trình kết thúc hoặc ghi kết quả đầu tiên.
- **Application ready**: thời điểm ứng dụng thật sự sẵn sàng nhận công việc, ví dụ HTTP health endpoint báo ready hoặc ứng dụng ghi log `READY`.
- **First operation**: thời gian đến khi thao tác đầu tiên hoàn tất. Mốc này có thể bao gồm lazy initialization sau startup.
- **Steady-state latency/throughput**: hiệu năng sau khi JVM đã warm up, JIT compiler và cache đã hoạt động ổn định.

Không nên dùng thời gian process exit làm đại diện cho thời gian ready nếu ứng dụng tiếp tục chạy nền. Với server, hãy đo đến readiness signal; với CLI, có thể đo đến khi lệnh hoàn tất nếu đó là trải nghiệm người dùng cần tối ưu.

Một kết quả đo nên ghi kèm:

- JDK vendor và version.
- OS, CPU architecture và số core.
- Cấu hình JVM như `-Xms`, `-Xmx`, GC và các system property quan trọng.
- Classpath/module path hoặc runtime image đang dùng.
- Root module và các module được resolve.
- Số lần chạy, cách tính median/p95 và điều kiện cold/warm.
- Mốc bắt đầu/kết thúc được sử dụng.

## 2. Đo startup của một tiến trình Java

### Đo thời gian bằng time trên Linux/macOS

Với ứng dụng modular:

~~~bash
/usr/bin/time -f "elapsed=%e sec max_rss=%M KB"   java --module-path mods        --module com.acme.app/com.acme.app.Main
~~~

- `elapsed` là thời gian thực tế từ lúc chạy lệnh đến khi tiến trình kết thúc.
- `max_rss` là maximum resident set size mà hệ điều hành ghi nhận, tính bằng KB trên các hệ thống GNU time phổ biến.

Nếu ứng dụng là server chạy liên tục, lệnh trên chỉ in kết quả sau khi tiến trình kết thúc. Khi đó hãy dùng công cụ đo bên ngoài để ghi thời điểm start và readiness, hoặc để ứng dụng phát ra một mốc `READY` có timestamp.

### Đo bằng PowerShell trên Windows

Với CLI kết thúc sau khi chạy:

~~~powershell
Measure-Command {
    java --module-path mods --module com.acme.app/com.acme.app.Main
}
~~~

Đối tượng trả về chứa `TotalMilliseconds` và các thành phần thời gian. Với server chạy lâu, `Measure-Command` chờ tiến trình kết thúc; cần đo readiness bằng script hoặc health check riêng thay vì chờ server dừng.

### Đo nhiều lần

Một lần chạy không đủ để kết luận. Thời gian có thể thay đổi do:

- OS file cache và disk cache.
- CPU frequency scaling, tải nền và scheduling.
- JIT compilation hoặc cache do ứng dụng tự tạo.
- DNS, database, network hoặc các dependency ngoài JVM.
- Antivirus hoặc filesystem scan trên một số hệ thống.

Hãy chạy nhiều lần trong điều kiện tương đương, ghi từng kết quả và báo cáo median cùng p95 nếu có đủ mẫu. Phân biệt:

- **Cold process**: mỗi lần tạo một tiến trình JVM mới.
- **Warm environment**: JVM mới nhưng OS/file cache đã được làm nóng bởi các lần chạy trước.
- **Warm JVM**: cùng một tiến trình đã xử lý nhiều công việc. Đây là trạng thái khác với startup của một tiến trình mới.

Nếu mục tiêu là startup của ứng dụng sau deploy/restart, cần đo cold process theo quy trình thực tế. Nếu mục tiêu là request latency sau khi service ổn định, hãy benchmark steady state riêng.

### Không nhầm startup với module resolution

Có thể thêm:

~~~bash
java --show-module-resolution   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Tùy chọn này cho biết root và dependency module được resolve. Nó hữu ích khi kiểm tra graph có kéo theo module không cần thiết hay không, nhưng không phải bộ đo thời gian startup chi tiết. Để phân tích thời gian khởi tạo, class loading, GC và JIT, dùng log/JFR.

## 3. Đo memory: heap và process memory

Một ứng dụng Java sử dụng nhiều vùng nhớ. Không thể kết luận tổng memory chỉ từ heap.

### Heap memory

Heap là vùng bộ nhớ JVM dùng cho object Java. Hai tùy chọn thường gặp:

- `-Xms`: kích thước heap ban đầu.
- `-Xmx`: giới hạn heap tối đa.

Ví dụ:

~~~bash
java -Xms256m -Xmx1g   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

`-Xmx1g` không có nghĩa tiến trình luôn dùng 1 GB RAM. Đây là giới hạn heap tối đa. Heap committed và heap used thay đổi theo allocation, GC và cấu hình JVM.

### Process memory / RSS

Bộ nhớ tiến trình có thể bao gồm:

- Heap đã commit.
- Metaspace lưu metadata class.
- Code cache chứa mã máy do JIT compiler tạo.
- Thread stack của các thread.
- Direct byte buffer và native allocation.
- Native library, memory mapping và cấu trúc nội bộ của JVM.

Vì vậy, RSS có thể lớn hơn heap used đáng kể. Ngược lại, heap max lớn không có nghĩa toàn bộ dung lượng đó đã được cấp phát vật lý.

| Chỉ số | Ý nghĩa | Công cụ gợi ý |
|---|---|---|
| Heap used | Object đang chiếm heap | `jcmd GC.heap_info`, GC log |
| Heap committed | Heap JVM đã commit | `jcmd GC.heap_info` |
| Heap max | Giới hạn heap | `-Xmx`, `Runtime.maxMemory()` |
| Process RSS | Bộ nhớ resident toàn tiến trình | `/usr/bin/time -v`, OS process monitor |
| Native memory categories | Các nhóm native memory JVM theo dõi | Native Memory Tracking |
| Metaspace | Metadata class | `jcmd GC.heap_info`, NMT |
| Class count | Số class đã được nạp | Class-loading log, `jcmd` |

## 4. Kiểm tra heap bằng jcmd và jstat

Để inspect một JVM đang chạy, tìm PID của tiến trình:

~~~bash
jcmd -l
~~~

Sau đó xem heap:

~~~bash
jcmd <pid> GC.heap_info
~~~

Output cho biết thông tin heap của JVM tại thời điểm lấy mẫu. Đây là snapshot, không phải mức sử dụng cao nhất trong suốt vòng đời ứng dụng.

Có thể lấy số liệu GC định kỳ bằng `jstat`:

~~~bash
jstat -gc <pid> 1000
~~~

Tham số `1000` yêu cầu lấy mẫu mỗi 1000 ms. Các cột hiển thị dung lượng/cách sử dụng các vùng heap và bộ đếm GC tùy JVM. Dùng `jstat -options` hoặc tài liệu JDK để xem các mode khác.

Một số lệnh hữu ích:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> GC.heap_info
jcmd <pid> VM.classloader_stats
~~~

- `VM.version`: version JVM đang chạy.
- `VM.command_line`: command line và JVM options.
- `GC.heap_info`: thông tin heap.
- `VM.classloader_stats`: thống kê class loader.

Các lệnh `jcmd` thường cần chạy với cùng user và môi trường có quyền attach tới JVM mục tiêu. Một số môi trường container hoặc cấu hình bảo mật có thể hạn chế attach.

## 5. Native Memory Tracking

Heap không bao gồm toàn bộ native memory. JVM có Native Memory Tracking (NMT) để theo dõi một số nhóm native allocation do JVM quản lý.

Bật NMT khi khởi chạy:

~~~bash
java -XX:NativeMemoryTracking=summary   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Có thể chọn `detail` để lấy thông tin chi tiết hơn, nhưng overhead và lượng dữ liệu tăng. NMT phải được bật từ lúc JVM khởi động; không thể bật hồi tố cho một tiến trình đã chạy.

Lấy báo cáo:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

Có thể xem chênh lệch giữa hai mốc bằng baseline:

~~~bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

Baseline/diff giúp quan sát native memory thay đổi theo thời gian. NMT không đo mọi allocation của native code bên ngoài JVM và không thay thế RSS của hệ điều hành. Dùng NMT cùng process monitor để có góc nhìn đầy đủ hơn.

## 6. Đo class loading bằng Unified Logging

Java cung cấp Unified Logging để ghi các sự kiện class loading và unloading.

Ghi class loading ra console:

~~~bash
java -Xlog:class+load=info   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Ghi ra file với timestamp và uptime:

~~~bash
java -Xlog:class+load=info:file=class-load.log:time,uptime,level,tags   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Mỗi sự kiện cho biết class được nạp và nguồn class tương ứng, tùy loại class và JVM. Có thể dùng log để trả lời:

- Class nào được nạp trong startup?
- Class đến từ module/JAR hoặc runtime image nào?
- Một thư viện có kéo theo nhiều class không cần thiết?
- Có class được nạp từ vị trí ngoài dự kiến không?

Có thể ghi cả load và unload:

~~~bash
java -Xlog:class+load=info,class+unload=info   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Class unloading xảy ra khi classloader và class liên quan đủ điều kiện được thu hồi; không phải mọi class đều được unload trong vòng đời ứng dụng. Class trong loader nền tảng hoặc loader sống lâu thường tồn tại đến khi JVM kết thúc.

### Đếm số dòng class loading

Trên Linux/macOS, sau khi có file log:

~~~bash
grep -c "class,load" class-load.log
~~~

Trên PowerShell:

~~~powershell
(Select-String -Path class-load.log -Pattern "class,load").Count
~~~

Số dòng log là số sự kiện được ghi theo cấu hình logging, không phải số class đang còn sống tại thời điểm đo. Một class có thể được load rồi unload; class loader khác nhau cũng có thể nạp cùng tên class trong những trường hợp đặc biệt. Vì vậy, hãy kết hợp số lượng với nguồn class và classloader stats.

## 7. Dùng Java Flight Recorder để xem startup và class loading

Java Flight Recorder (JFR) thu thập sự kiện JVM trong một recording, có thể phân tích bằng Java Mission Control (JMC) hoặc công cụ `jfr`.

Bắt đầu recording từ lúc JVM khởi chạy:

~~~bash
java   -XX:StartFlightRecording=filename=startup.jfr,settings=profile,dumponexit=true   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Với server chạy lâu, có thể attach và bắt đầu recording bằng `jcmd`:

~~~bash
jcmd <pid> JFR.start name=StartupProfile settings=profile filename=startup.jfr
~~~

Khi đã thu đủ dữ liệu:

~~~bash
jcmd <pid> JFR.stop name=StartupProfile
~~~

In một số sự kiện ra text:

~~~bash
jfr summary startup.jfr
jfr print --events jdk.ClassLoad startup.jfr
~~~

Tên event và trường dữ liệu phụ thuộc JDK recording configuration. Trong JMC, có thể xem timeline, class loading, allocation, GC, thread activity và các event liên quan startup.

JFR phù hợp để tìm nguyên nhân tốn thời gian hoặc allocation. Recording `profile` có overhead nhất định; hãy dùng cấu hình nhất quán và tránh so sánh trực tiếp một lần chạy có profiling với lần chạy baseline không instrumentation mà không ghi chú.

## 8. Đo class loading không đồng nghĩa đo startup

Số lượng class được nạp chỉ là một phần của startup. Thời gian startup còn phụ thuộc:

- Bytecode verification và linking.
- Class initialization (static initializer).
- Reflection, service discovery và dependency injection.
- JIT compilation.
- Đọc file JAR/module image và filesystem cache.
- Kết nối network, database hoặc secret/config provider.
- Công việc khởi tạo riêng của framework.

Một ứng dụng có ít class hơn vẫn có thể startup chậm hơn nếu static initializer thực hiện I/O hoặc chờ network. Ngược lại, nhiều class có thể được nạp nhanh nếu phần lớn chỉ là metadata và code nhỏ.

Hãy dùng class-loading log để xác định class nào được nạp và khi nào; dùng JFR để tìm hoạt động chiếm thời gian; dùng timestamp readiness để đo kết quả startup cuối cùng.

## 9. Đo riêng runtime image và module graph

Nếu đang so sánh runtime image được tạo bằng `jlink` với một JDK đầy đủ, cần giữ điều kiện đo giống nhau:

- Cùng ứng dụng và cùng phiên bản bytecode.
- Cùng OS, CPU, JDK release và JVM flags.
- Cùng root module và service-binding policy.
- Cùng dữ liệu đầu vào và cấu hình môi trường.
- Cùng định nghĩa readiness và cách warm/cold.

Có thể xem graph module lúc launch:

~~~bash
runtime/bin/java --show-module-resolution   --module com.acme.app/com.acme.app.Main
~~~

Để xem danh sách module trong runtime image:

~~~bash
runtime/bin/java --list-modules
~~~

Runtime image nhỏ hơn không đảm bảo startup luôn nhanh hơn hoặc RSS luôn thấp hơn. Kích thước image trên disk, số module được resolve, số class được load và memory process là các đại lượng khác nhau. Hãy đo từng chỉ số thay vì suy luận từ kích thước thư mục runtime.

## 10. Quy trình đo lặp lại có thể so sánh

Một quy trình thực tế:

1. Chốt JDK, OS, CPU, JVM flags, module path và phiên bản ứng dụng.
2. Xác định mốc startup, ví dụ log `READY` hoặc thời điểm CLI kết thúc.
3. Chạy nhiều lần với tiến trình JVM mới; lưu thời gian từng lần.
4. Ghi process RSS từ hệ điều hành và heap snapshot bằng `jcmd`.
5. Chạy một lượt có `-Xlog:class+load=info` để thu class-loading log.
6. Chạy một lượt JFR để tìm hoạt động tốn thời gian hoặc allocation.
7. Nếu cần phân tích native memory, chạy với NMT đã bật từ đầu.
8. So sánh median/p95 và ghi rõ các lượt có instrumentation.
9. Thay đổi một yếu tố mỗi lần, ví dụ root set, module path, runtime image hoặc JVM flags.
10. Lặp lại đủ số lần trong cùng điều kiện và lưu log cùng metadata môi trường.

Không nên cộng heap used, RSS và NMT thành một con số memory tổng. Các chỉ số có phạm vi đo khác nhau và có thể chồng lấp. Hãy trình bày chúng riêng.

## 11. Bảng chọn công cụ

| Câu hỏi | Công cụ |
|---|---|
| Tiến trình CLI chạy mất bao lâu? | `/usr/bin/time`, PowerShell `Measure-Command` |
| Server sẵn sàng sau bao lâu? | Readiness timestamp/health check và external timer |
| Heap đang dùng bao nhiêu? | `jcmd GC.heap_info`, `jstat -gc` |
| Tổng process memory/RSS là bao nhiêu? | OS process monitor, `/usr/bin/time -v` |
| JVM native memory chia theo nhóm ra sao? | `-XX:NativeMemoryTracking=summary`, `jcmd VM.native_memory` |
| Class nào được load từ đâu? | `-Xlog:class+load=info` |
| Class loader giữ bao nhiêu class? | `jcmd VM.classloader_stats` |
| Điều gì chiếm thời gian hoặc allocation? | JFR và JMC |
| Module nào được resolve? | `--show-module-resolution` |
| Runtime image có module nào? | `--list-modules` |

## 12. Lỗi thường gặp khi đo

**Dùng `-Xmx` làm số memory thực tế.** `-Xmx` là giới hạn heap, không phải RSS hoặc heap used. Lấy snapshot bằng `jcmd GC.heap_info` và đo RSS từ hệ điều hành.

**Đo server bằng thời gian command trả về.** Server không kết thúc nên timer chờ mãi. Hãy đo đến readiness signal hoặc health endpoint.

**So sánh một lần chạy cold với một lần warm.** OS cache và JIT có thể làm kết quả khác đáng kể. Ghi rõ loại run và lặp lại nhiều lần.

**Bật mọi log trong lượt benchmark chính.** Class-loading log, GC log, JFR và NMT có overhead. Dùng một baseline ít instrumentation và các lượt diagnostic riêng.

**Coi class count là hiệu năng.** Số class không cho biết class initialization có chặn I/O hay không. Dùng JFR và timestamp để tìm phần việc thực sự tốn thời gian.

**NMT thấp hơn RSS nên kết luận process monitor sai.** NMT chỉ theo dõi các nhóm native allocation JVM hỗ trợ; RSS còn có thể chứa memory mapping, native allocation ngoài phạm vi NMT và các vùng khác.

**Không tìm thấy PID bằng jcmd.** Kiểm tra user, container namespace, attach permission và JVM có bật cơ chế attach phù hợp hay không.

## 13. Thực hành

1. Chạy một ứng dụng modular CLI bằng `/usr/bin/time` hoặc `Measure-Command`; ghi thời gian thực tế.
2. Chạy lại ít nhất năm lần với JVM process mới, ghi từng kết quả và tính median.
3. Khởi chạy một service và đo từ process start đến readiness endpoint.
4. Thêm `-Xms256m -Xmx1g`; quan sát heap bằng `jcmd GC.heap_info` và so sánh với RSS.
5. Bật `-XX:NativeMemoryTracking=summary`, lấy baseline và `summary.diff` sau một khoảng hoạt động.
6. Bật `-Xlog:class+load=info`, đếm class load event và kiểm tra nguồn của các class quan trọng.
7. Tạo JFR recording từ lúc startup; dùng `jfr summary` và JMC để tìm event chiếm thời gian.
8. So sánh JDK đầy đủ và runtime image `jlink` trong cùng điều kiện; ghi riêng startup, heap, RSS, class count và module graph.

Để đánh giá ứng dụng Java modular, hãy đo đúng đại lượng và đúng mốc. Startup cần readiness hoặc process timing; memory cần tách heap, native memory và RSS; class loading cần log hoặc JFR để hiểu class nào được nạp và tác động của nó. Khi kết hợp các nguồn này với module resolution, bạn có thể xác định module/dependency nào ảnh hưởng startup và footprint thay vì suy luận chỉ từ số lượng module hoặc kích thước runtime image.
