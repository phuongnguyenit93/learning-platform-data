# 4.4 Nhóm lệnh thông tin VM, luồng, heap, compiler, JFR và native memory

## Mục tiêu học tập

`jcmd` là tiện ích của JDK gửi **diagnostic command** đến một JVM đang chạy. Khi điều tra Java production, người vận hành thường thấy nhiều lệnh trong `jcmd <PID> help` nhưng không biết lệnh nào chỉ đọc trạng thái, lệnh nào tạo snapshot nặng, lệnh nào kích hoạt recording, và lệnh nào chỉ có ích nếu JVM đã được cấu hình từ lúc khởi động. Bài này hệ thống hóa sáu nhóm: **VM information, threads, heap/GC, compiler/JIT, Java Flight Recorder (JFR) và Native Memory Tracking (NMT)**.

Sau bài học, bạn có thể:

- Chọn nhóm lệnh theo **triệu chứng** thay vì chạy hàng loạt lệnh không cần thiết.
- Diễn giải được các kết quả thường gặp: VM startup flags, trạng thái thread/lock, histogram lớp, code cache, JFR recording và NMT reserved/committed.
- Phân biệt **lệnh chỉ quan sát** với lệnh làm thay đổi trạng thái JVM hoặc có tác động cao như `GC.heap_dump`, `GC.class_histogram`, `JFR.start`, `VM.native_memory baseline`.
- Thực hiện một lượt chẩn đoán an toàn trên HotSpot/JDK 21, xác minh tên lệnh qua `help`, gắn bằng chứng với đúng PID/thời điểm và giữ thông tin nhạy cảm trong phạm vi được phép.
- Hiểu **giới hạn của từng công cụ**: thread dump không phải CPU profile, heap histogram không tự chứng minh leak, JFR không ghi lại quá khứ khi trước đó chưa bật, NMT không đồng nghĩa với tổng RSS của process.

Các ví dụ chính dùng **HotSpot JDK 21**. Danh sách diagnostic command và cú pháp có thể thay đổi theo vendor, VM implementation, phiên bản JDK và quyền truy cập. Luôn kiểm tra lệnh thực có trên JVM đích trước khi áp dụng.

## 1. Cách đọc hệ thống lệnh jcmd

### 1.1 Xác định đúng PID và xem trợ giúp

Trong terminal có JDK `jcmd`, lệnh:

```bash
jcmd -l
```

có thể liệt kê các tiến trình Java mà công cụ nhìn thấy. Danh sách này **có thể không bao gồm JVM trong namespace/container riêng**. Nếu biết PID từ systemd, Kubernetes, Windows service hoặc process manager, phải đối chiếu service, container/pod, process start time và JVM thực tế; PID đơn độc có thể bị tái sử dụng sau restart.

Với PID thật của một JVM HotSpot đang chạy:

```bash
jcmd 12345 help
jcmd 12345 help VM.flags
jcmd 12345 help Thread.print
jcmd 12345 help JFR.start
```

**12345 chỉ là PID minh họa**, phải thay bằng PID đã xác minh. `help` cho biết tên và options **mà JVM đích hỗ trợ**, vì vậy an toàn hơn việc copy lệnh từ môi trường hoặc bài viết dùng JDK khác. Nếu `jcmd 12345 help` báo lệnh không tồn tại, không tự suy đoán tên mới; kiểm tra phiên bản, implementation và tài liệu tương ứng.

`jcmd` gửi yêu cầu đến JVM trên **cùng máy**, cần effective user/group và quyền attach phù hợp. Container PID namespace, policy bảo mật, image runtime tối giản, một JVM khởi động với attach bị vô hiệu hoặc implementation khác HotSpot đều có thể ngăn truy cập. Một lỗi attach không chứng minh tiến trình không phải Java.

### 1.2 Đừng hiểu “diagnostic” nghĩa là không can thiệp

Trong tài liệu `jcmd`, mỗi command có **Impact: Low / Medium / High**, là ước lượng ảnh hưởng tương đối, không phải cam kết thời gian chạy. Phần lớn lệnh thông tin VM nhẹ; thread dump có thể tốn chi phí theo số lượng thread; histogram và heap dump có thể tác động mạnh; start/stop JFR làm thay đổi hoạt động thu thập; NMT baseline thay đổi mốc so sánh.

| Mức/nhóm tác động | Ví dụ | Ý nghĩa vận hành |
| --- | --- | --- |
| Đọc trạng thái, thường nhẹ | `VM.version`, `VM.flags`, `Compiler.queue`, `Compiler.codecache`, `JFR.check` | Lấy snapshot nhanh; vẫn nên giới hạn tần suất và quyền truy cập |
| Quan sát có chi phí theo kích thước dữ liệu | `Thread.print`, `GC.heap_info`, `VM.metaspace`, `VM.native_memory summary` | Đo overhead, không chạy vòng lặp quá dày trên nhiều replica |
| Snapshot nặng/khối lượng lớn | `GC.class_histogram`, `GC.heap_dump` | Có thể dừng thread/đòi safepoint hoặc GC, tốn CPU, I/O, disk và thời gian |
| Điều khiển trạng thái chẩn đoán | `JFR.start`, `JFR.dump`, `JFR.stop`, `VM.native_memory baseline` | Tạo/đổi recording hoặc đặt mốc đo; có mục tiêu, thời hạn, quyền và đường lưu rõ ràng |
| Thay đổi hoạt động JVM, tránh khi chỉ cần đọc | `GC.run`, `VM.set_flag`, `VM.log`, `Compiler.directives_add` | Không thuộc bước thu thông tin thụ động; phải xem xét riêng tác động và rollback |

Việc lệnh in ra “thống kê” không đủ để coi nó rẻ. Đặc biệt, `GC.heap_dump` có thể yêu cầu **full GC** trước khi tạo dump theo mặc định; tài liệu JDK 21 nêu ngoại lệ khi chọn `-all`. Không dùng lệnh `GC.run` để “kiểm tra GC” khi chỉ cần quan sát: nó thực hiện lời gọi tương đương `System.gc()`.

### 1.3 Bản đồ sáu nhóm

```text
jcmd <PID> help
      |
      +-- VM.*          -> VM version, command line, flags, properties, uptime
      +-- Thread.*      -> stack, thread state, lock evidence
      +-- GC.*          -> heap info, object histogram, heap dump (cẩn trọng)
      +-- Compiler.*    -> JIT queue, code cache, compiled methods
      +-- JFR.*         -> xem/bắt đầu/dump/dừng Java Flight Recording
      +-- VM.native_memory -> native memory theo NMT (nếu bật từ startup)
```

Một tên lệnh không phải API tương đương trên mọi JVM. Ví dụ `Thread.dump_to_file` xuất hiện trong các JDK mới hơn, nhưng **không nên giả định có trong HotSpot JDK 21**; bài này dùng `Thread.print` là lệnh được tài liệu JDK 21 mô tả. Tương tự, command thuộc JVM implementation khác có thể có tên/cú pháp khác; hãy lấy `help` từ **chính target VM**.

## 2. Nhóm VM: nhận diện phiên chạy và cấu hình thực tế

Các lệnh thông tin VM nên được dùng đầu tiên vì chúng giúp đảm bảo bạn đang phân tích đúng phiên chạy, và giúp người khác tái tạo kết quả.

```bash
jcmd 12345 VM.version
jcmd 12345 VM.uptime
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 VM.flags -all
jcmd 12345 VM.system_properties
```

### 2.1 Ý nghĩa và giới hạn

| Lệnh | Bằng chứng thu được | Giới hạn cần nhớ |
| --- | --- | --- |
| `VM.version` | Tên/version/build VM đang chạy | Không phải `java -version` do terminal hiện tại gọi |
| `VM.uptime` | Thời gian JVM đã hoạt động; `-date` có thể thêm ngày theo lệnh | Kết hợp process start time khi có nhiều lần restart; không xác nhận app đã healthy |
| `VM.command_line` | Thông tin JVM command line lúc khởi động | Có thể chứa secret, startup arguments không phản ánh mọi thay đổi lúc chạy |
| `VM.flags` | Các VM flag và giá trị hiện hành được command trình bày | Không đồng nghĩa toàn bộ original shell command line |
| `VM.flags -all` | Các flags được VM hỗ trợ, gồm giá trị hiện hành/default/ergonomic tùy implementation | Không có nghĩa mọi flag do operator truyền từ CLI |
| `VM.system_properties` | Java system properties tại thời điểm đọc | Có thể bị code đổi qua `System.setProperty`; đầu ra dễ lộ credentials |

Trên HotSpot JDK 21, `VM.info` có thể cung cấp báo cáo environment/trạng thái rộng hơn và thường nhẹ, nhưng có thể chứa nhiều dữ liệu nội bộ. Khi cần chuyên sâu, dùng `jcmd 12345 help VM.info` để xác nhận tính khả dụng trước, rồi kiểm tra phạm vi chia sẻ đầu ra.

**Phân biệt ba lớp cấu hình:**

1. **Input lúc startup**: `-Xms`, `-Xmx`, `-XX`, `-D`, `-javaagent` và các VM options ứng dụng nhận lúc khởi động. Xem qua `VM.command_line` và khi phù hợp `RuntimeMXBean.getInputArguments()`.
2. **VM flags hiệu lực hiện tại**: `VM.flags`/`VM.flags -all` có thể gồm những giá trị được VM chọn bằng ergonomics dựa trên JDK/GC/memory/container limits, hoặc đã được thay đổi tại runtime nếu hỗ trợ.
3. **Application arguments**: tham số sau main class hoặc `-jar app.jar` do `main(String[] args)`/framework xử lý; không nên gộp với VM input arguments.

Ví dụ, `-Xmx2g` là startup option, trong khi `MaxHeapSize` là tên flag thể hiện giới hạn heap mà JVM dùng. Nếu `VM.flags -all` có `MaxHeapSize` nhưng `VM.command_line` không chứa `-Xmx`, có thể JVM tự xác định giá trị từ defaults hoặc memory limits. Hai kết quả không mâu thuẫn.

**Bảo mật:** `VM.command_line` và `VM.system_properties` có thể chứa JDBC URL, `-Dpassword`, token, đường dẫn nội bộ, truststore credentials. Không đăng nguyên stdout lên ticket/chat chung. Thu bằng quy trình được phép, lọc allowlist key và redact trước khi lưu; dữ liệu chẩn đoán có thể làm lộ bí mật dù lệnh chỉ đọc.

### 2.2 Khi nào chọn nhóm VM?

- JVM “đang chạy JDK 21” nhưng phát sinh `UnsupportedClassVersionError`: xác minh đúng `VM.version`, vendor, runtime properties, class-file compatibility; `java -version` của SSH shell có thể thuộc một JDK khác.
- GC/heap trên production không giống YAML: so sánh `VM.command_line`, `VM.flags`, process/container limits; không giả định giá trị dự kiến bằng giá trị JVM dùng.
- Chỉ một replica lỗi: lấy fingerprint VM/JVM và app build của **replica lỗi** và replica đối chứng, gắn PID/start time/UTC.
- Sau restart có kết quả chẩn đoán khác: kiểm tra `VM.uptime`, process start time và deployment metadata để không trộn bằng chứng của hai lần chạy.

Nhóm VM trả lời **“đây là tiến trình nào, với điều kiện thực thi nào?”**, không tự trả lời nguyên nhân CPU cao hay request treo.

## 3. Nhóm luồng: Thread.print và bằng chứng tranh chấp

### 3.1 Cú pháp và mục đích

```bash
jcmd 12345 Thread.print
jcmd 12345 Thread.print -l
jcmd 12345 Thread.print -e
```

Trên HotSpot JDK 21:

- `Thread.print` in stack trace và trạng thái các thread mà command hỗ trợ quan sát; hữu ích để tìm thread ở `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`.
- `Thread.print -l` bổ sung thông tin về **`java.util.concurrent` locks** khi có thể; giúp nhận diện quan hệ chờ lock trong một snapshot.
- `Thread.print -e` bật thông tin thread mở rộng theo implementation; vẫn phải dựa trên chính output để biết trường nào có mặt.

Theo tài liệu JDK 21, impact của `Thread.print` là **Medium**, phụ thuộc số lượng thread. Một server có hàng nghìn thread có thể tạo output rất lớn; đừng tự đặt cron dump mỗi vài mili-giây hoặc chạy mọi replica cùng lúc mà không đánh giá chi phí.

### 3.2 Cách đọc kết quả

Ví dụ **mô phỏng rút gọn**, không phải stdout từ một JVM cụ thể:

```text
"worker-17" ... java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.OrderService.update(OrderService.java:87)
    - waiting to lock <0x...> (a java.lang.Object)
"worker-4" ... java.lang.Thread.State: TIMED_WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
```

Giải thích:

- `BLOCKED` thường chỉ việc thread muốn vào monitor do thread khác giữ, không đồng nghĩa CPU process bị bão hòa.
- `WAITING`/`TIMED_WAITING` có thể là hoạt động bình thường (queue, pool, timer, sleep), phải đối chiếu ngữ cảnh.
- `RUNNABLE` không luôn có nghĩa thread liên tục dùng CPU; nó còn phụ thuộc cách JVM/OS biểu diễn trạng thái.
- Một stack snapshot cho biết **vị trí tại thời điểm chụp**, chưa cho biết phương thức đó chiếm bao nhiêu phần trăm CPU tổng thể.
- Dữ liệu locks có thể giúp dựng giả thuyết contention/deadlock, nhưng cần đối chiếu các thread liên quan, owner, dumps ở nhiều mốc và JFR lock/park events khi phù hợp.

### 3.3 Lấy nhiều snapshot có kiểm soát

Khi request treo ngẫu nhiên, thay vì kết luận từ một dump, có thể lấy vài snapshot có timestamp trong khoảng sự cố, ví dụ một snapshot lúc đầu, một lúc giữa, một lúc gần kết thúc. Khoảng cách phụ thuộc độ dài hiện tượng; dữ liệu phải gắn service/PID/start time để không trộn với lần restart.

Không dùng đường dẫn `jcmd 12345 Thread.print > threads.txt` nếu chưa biết terminal đang chạy ở đâu và file có được phép lưu không. **Redirection bằng `>` là hành động của shell**, nên file tạo trên máy chạy shell, trong khi heap/JFR dump do VM tạo theo đường dẫn của **process đích**. Đây là khác biệt quan trọng khi chẩn đoán qua container hoặc remote shell.

Đối với **virtual threads** (JDK 21), dữ liệu một số command truyền thống không mặc nhiên liệt kê mọi virtual thread ở trạng thái unmounted. Không được suy luận “không có virtual thread nào chờ” chỉ vì chúng không xuất hiện trong `Thread.print`. Với ứng dụng virtual-thread-heavy, dùng JFR và cơ chế thread dump/hệ quan sát phù hợp JDK/implementation; tra `help` trước khi dựa vào cú pháp từ bản Java mới hơn.

## 4. Nhóm heap/GC: GC.heap_info, histogram và heap dump

Ba lệnh sau nhìn có vẻ cùng chủ đề nhưng mục tiêu và tác động khác nhau:

```bash
jcmd 12345 GC.heap_info
jcmd 12345 GC.class_histogram
jcmd 12345 GC.heap_dump /path/approved/heap-12345.hprof
```

Lệnh cuối **chỉ là ví dụ cú pháp**, có thể tạo file nhiều GB và ảnh hưởng lớn. **Không chạy heap dump trên production chỉ vì đang học nhóm lệnh.**

### 4.1 GC.heap_info: ảnh chụp cấu trúc/hiện trạng heap

`GC.heap_info` cung cấp thông tin tổng quan Java heap theo collector/JDK đích, có impact **Medium**. Dùng khi cần hiểu heap size/usage, region/generation và bối cảnh GC tại thời điểm thu thập. Output phụ thuộc collector, phiên bản JVM và trạng thái, nên không cố định mọi field.

Ví dụ thực hành khái niệm: heap `used` là lượng Java heap đang được sử dụng theo cách VM báo cáo ở thời điểm đo; **không phải toàn bộ resident set size (RSS)**, cũng không chứng minh có memory leak nếu chỉ từ một lần chụp. Một quá trình Java còn có threads stacks, metaspace, code cache, direct/native memory và memory mappings.

Khi heap dùng nhiều, so sánh nhiều thời điểm và workload (đặc biệt sau GC), đo allocation rate, GC pause và memory limits. Heap cao nhưng ổn định có thể bình thường; heap tăng qua nhiều chu kỳ dưới tải tương đương có thể cần phân tích sâu hơn.

### 4.2 GC.class_histogram: phân bố object theo lớp

`GC.class_histogram` hiển thị số lượng instance và bytes theo class, hữu ích để phát hiện lớp có số object lớn bất thường như `byte[]`, `char[]`, `java.util.HashMap$Node` hoặc một DTO cụ thể. Tài liệu JDK 21 đánh dấu **Impact: High**.

```bash
jcmd 12345 help GC.class_histogram
jcmd 12345 GC.class_histogram -all
```

Với `-all`, command bao gồm cả **unreachable objects** thay vì chỉ đối tượng theo chế độ mặc định. Phạm vi này có thể gây thay đổi kết luận vì các object chưa được GC thu hồi không phải tất cả đều còn được ứng dụng giữ tham chiếu. Đừng đồng nhất histogram với live heap growth hoặc retained size.

Điều histogram **không tự cung cấp**: object graph/chuỗi tham chiếu giữ object, retained size theo root, lifecycle và đường cấp phát. Nếu `byte[]` đứng đầu về bytes, bạn mới biết loại object chiếm chỗ đáng kể **tại thời điểm đo**; chưa biết ai đang giữ chúng, liệu đó là cache hợp lệ hay leak, hoặc phần lớn sẽ được thu hồi trong kỳ GC tiếp theo.

Không chạy histogram liên tục để tạo “profile allocation”: nó là thao tác snapshot có impact cao, không phải sampling nhẹ của allocation. Nếu cần chỗ phát sinh allocation, cân nhắc JFR allocation events và dữ liệu GC theo mục tiêu.

### 4.3 GC.heap_dump: tạo HPROF để phân tích object graph

`GC.heap_dump` tạo file heap dump, thường cho phép phân tích với Eclipse Memory Analyzer/JMC hoặc công cụ tương ứng. Trên JDK 21, tài liệu ghi tác động **High** theo heap size/content; **mặc định yêu cầu full GC nếu không chỉ định `-all`**. Vì vậy tác động không chỉ là I/O ghi file mà còn có thể là pause và thay đổi trạng thái heap tại lúc đo.

```bash
# Cú pháp tham khảo; CHỈ CHẠY khi đã đánh giá chi phí và có quyền.
jcmd 12345 GC.heap_dump /path/approved/heap-12345.hprof
```

Trước khi thu: kiểm tra dung lượng đĩa/filesystem của tiến trình JVM, tên file duy nhất, quyền truy cập, timeout, tác động dịch vụ và chính sách lưu xóa. Đường dẫn là nơi **JVM đích** sẽ ghi file; file không tự xuất hiện trên laptop chạy lệnh nếu JVM nằm trong container/máy khác. Heap dump có thể chứa password, token, dữ liệu cá nhân, chuỗi request và giá trị object nhạy cảm.

Không dùng `-all` như “chế độ ít tốn chi phí chắc chắn an toàn”: nó đổi tập object được thu (bao gồm unreachable) và cách tương tác với GC, vẫn có thể tạo dump lớn. Nếu chỉ muốn biết heap tổng quát, hãy chọn `GC.heap_info` trước. Đặt tên lệnh, tùy chọn và mục tiêu rõ ràng để tránh tình huống nhân viên chạy full heap dump khi chỉ định lấy “heap stats”.

### 4.4 Các lệnh GC có tính điều khiển

`GC.run` yêu cầu JVM gọi `System.gc()`; `GC.run_finalization` yêu cầu gọi `System.runFinalization()`. Chúng có thể gây tác động và không phải snapshot thụ động. Đừng dùng `GC.run` như một “trình đo chuẩn” để xác minh tình trạng production, vì chính thao tác đó có thể làm thay đổi dữ liệu mà bạn định quan sát.

**Chọn theo vấn đề:** heap pressure → `GC.heap_info` cùng GC events; nghi một class giữ quá nhiều object → histogram có kiểm soát; cần tìm retained references → heap dump khi có ngân sách tác động và quyền; nghi tốc độ allocation cao → JFR allocation profiling thay vì lặp histogram liên tục.

## 5. Nhóm Compiler/JIT: Compiler.queue, codecache, codelist

Java HotSpot có cơ chế JIT compilation. Khi ứng dụng warm-up, code được biên dịch từ bytecode sang native machine code để tăng hiệu năng; danh sách compile queue và code cache phản ánh các hoạt động này nhưng không đồng nghĩa thời gian xử lý request hay số lần một method được gọi.

```bash
jcmd 12345 Compiler.queue
jcmd 12345 Compiler.codecache
jcmd 12345 Compiler.codelist
jcmd 12345 Compiler.directives_print
```

### 5.1 Compiler.queue

`Compiler.queue` liệt kê những phương thức **đang chờ compilation** tại thời điểm gọi, impact **Low** theo tài liệu JDK 21. Queue lớn/duy trì dài dưới một workload cụ thể có thể gợi ý thời gian warm-up hoặc áp lực compiler, nhưng cần đối chiếu throughput, CPU, JFR/compiler events, JIT compiler threads và trạng thái hệ thống.

**Queue trống không có nghĩa** không còn compilation đã/đang diễn ra, không có code interpreted, hoặc ứng dụng đã đạt hiệu năng steady-state. Đây chỉ là snapshot của hàng đợi mà command phản ánh.

### 5.2 Compiler.codecache

`Compiler.codecache` hiển thị layout và giới hạn vùng **code cache** nơi HotSpot lưu compiled native code, impact **Low**. Khi log/JFR cho thấy code cache đầy hoặc compilation bị hạn chế, command này giúp kiểm tra các vùng code heap và dung lượng còn lại.

Code cache thuộc **native memory của JVM**, không nằm trong Java heap `-Xmx`. Vì vậy GC heap còn trống **không loại trừ** code cache pressure. Tên code heap và layout phụ thuộc VM/JDK/options; không suy luận tất cả các vùng đều luôn tồn tại.

### 5.3 Compiler.codelist

`Compiler.codelist` liệt kê các compiled methods còn sống trong code cache, impact **Medium**. Danh sách có thể rất dài; dùng khi điều tra compiler state hoặc muốn đối chiếu một method có compiled code không. Method không xuất hiện ở một snapshot **không chứng minh** method chưa bao giờ thực thi, vì có thể interpreted, bị deoptimized, compiled entry đã thay đổi hoặc không còn nằm trong cache.

### 5.4 Compiler.directives_print và các lệnh khác

`Compiler.directives_print` chỉ in các **compiler directives đang hoạt động**. Trái lại, `Compiler.directives_add`, `Compiler.directives_clear`, `Compiler.directives_remove` thay đổi directives, nên không nên dùng trong lượt read-only diagnostics. `Compiler.perfmap` trên Linux tạo file map dùng với `perf`, cũng có side effect ghi file.

Tình huống: ứng dụng chậm trong 30 giây đầu rồi ổn. Hãy so sánh warm-up và steady-state bằng request latency/CPU/JFR, kết hợp `Compiler.queue`, `Compiler.codecache`, `VM.flags` và dữ liệu compiler events. **Đừng kết luận “JIT là nguyên nhân” chỉ vì queue từng có method**; queue là một bằng chứng cần so với thời gian sự cố.

## 6. Nhóm JFR: bắt dòng thời gian CPU, allocation, GC và lock

Java Flight Recorder (JFR) thu events và samples của JVM/ứng dụng để phân tích hoạt động **theo thời gian**. Một file `.jfr` thường có nhiều loại sự kiện: CPU execution samples, allocations, GC pauses, threads, locks, I/O... phụ thuộc **settings** và event thresholds. JFR vừa là công cụ điều khiển recording qua `jcmd`, vừa tạo dữ liệu quan sát/profiling.

### 6.1 Xem recording đang chạy (đọc trạng thái)

```bash
jcmd 12345 JFR.check
jcmd 12345 JFR.check name=triage
jcmd 12345 JFR.check name=triage verbose
```

Nếu không chỉ định `name`, `JFR.check` thông báo các recording hiện hoạt. `verbose` có thể hiển thị event settings; áp dụng theo `help` của JVM đích. Không có active recording **không chứng minh JFR không thể chạy**, và không có JFR file cũ không có nghĩa JVM chưa từng recording trước đó.

### 6.2 Thu nhanh 60 giây bằng profile settings

Khi có mục tiêu rõ ràng và đã đánh giá overhead, có thể ghi một phiên JFR giới hạn:

```bash
jcmd 12345 JFR.start name=triage settings=profile duration=60s filename=triage.jfr
jcmd 12345 JFR.check
```

- `name=triage` đặt tên recording để tham chiếu bằng `JFR.check`/`JFR.stop`.
- `settings=profile` dùng preset tăng chi tiết hơn `default`, thường phù hợp **thời lượng ngắn**; không gán overhead cố định cho mọi workload.
- `duration=60s` yêu cầu recording có thời lượng giới hạn và tự dừng sau khoảng đó. Nếu chỉ định `filename`, file được ghi khi recording dừng theo cấu hình.
- `filename=triage.jfr` là đường dẫn mà **JVM đích** có quyền ghi; đường dẫn tương đối cần hiểu theo working directory của process đích.
- Nếu incident kết thúc trước khi recording bắt đầu, nội dung chỉ mô tả **giai đoạn sau đó**, không tự khôi phục dữ liệu quá khứ.

Sau khi file xuất hiện, dùng `jfr summary` để xem loại/số lượng events, hoặc mở qua JDK Mission Control (JMC). Nội dung có thể biến đổi theo collector, settings, workloads và sampling; không bịa số CPU hay GC từ một ví dụ chưa chạy.

```bash
jfr summary triage.jfr
```

Lệnh `jfr` ở trên là công cụ đọc file **trong JDK**, không phải diagnostic command gắn vào process qua `jcmd`. Bạn cần file có thể đọc được từ môi trường đang phân tích.

### 6.3 Rolling recording: giữ bằng chứng trước incident

Khi sự cố ngắn và khó lặp lại, một recording `default` với giới hạn có thể giữ một khoảng lịch sử:

```bash
jcmd 12345 JFR.start name=rolling settings=default disk=true maxage=15m maxsize=256m
jcmd 12345 JFR.check name=rolling
```

Khi nhận được alert trong lúc recording còn chạy:

```bash
jcmd 12345 JFR.dump name=rolling filename=incident.jfr maxage=10m
```

Khi không còn cần duy trì recording:

```bash
jcmd 12345 JFR.stop name=rolling
```

Cần hiểu ba thao tác:

1. `JFR.start` **bắt đầu recording** và tác động lên trạng thái thu thập. Khi không đặt `duration`, mặc định recording có thể chạy cho tới khi dừng.
2. `JFR.dump` **xuất dữ liệu hiện có ra file nhưng recording vẫn tiếp tục chạy**. `maxage` trên dump chỉ giới hạn phần lịch sử được đưa vào file; không thể chứa events bị loại trước đó.
3. `JFR.stop` **dừng recording**. Nó không giống `JFR.dump`; cần phân biệt để tránh vừa mất monitoring sớm, vừa quên dừng recording dài hạn.

`maxage=15m` của recording là giới hạn tuổi dữ liệu; `maxsize=256m` là giới hạn dung lượng trên đĩa. Với tốc độ sự kiện cao, dữ liệu cũ có thể bị loại trước 15 phút dù tuổi chưa tới hạn. `settings=default` có chi phí nhẹ hơn `profile` trong điều kiện thông thường nhưng vẫn có overhead và cần quản lý retention.

Các lệnh như `JFR.configure` thay đổi cấu hình recorder; `path-to-gc-root` có thể kéo dài công việc và ảnh hưởng pause. Không thêm options này bừa bãi vào bài toán CPU latency thông thường. File JFR có thể chứa tên class/method, stack, path, URL, property và các giá trị nhạy cảm tùy event; bảo vệ quyền truy cập như một artifact production.

### 6.4 Diễn giải JFR đúng cách

- **CPU samples** cho biết phân bố stack trong thời gian được lấy mẫu, không tự biểu diễn mọi request hay mọi stack frame từng chạy.
- **Allocation events** chỉ ra vị trí tạo object trong phạm vi sampling/event settings; không đồng nghĩa retained objects/leak.
- **GC events** có timestamp/pause duration, giúp so với p99 latency, nhưng trùng thời điểm không tự chứng minh GC là nguyên nhân duy nhất.
- **Lock/park events** cần kiểm tra threshold/settings, các thread liên quan và workload.
- Một recording 60 giây **không đại diện** cho sự cố hiếm xảy ra mỗi 2 giờ nếu thời điểm đo sai. Chọn thời lượng và trigger theo tính chất incident.

## 7. Nhóm Native Memory: VM.native_memory và điều kiện NMT

### 7.1 Native Memory Tracking là gì?

Native Memory Tracking (**NMT**) là tính năng của **HotSpot** theo dõi nhiều vùng cấp phát native/internal memory của JVM: Java heap reserved/committed, class/metaspace, thread, code, GC, compiler và một số subsystem khác. Nó rất hữu ích khi **RSS/process memory tăng nhưng Java heap used không tăng tương ứng**.

Điều NMT **không phải**:

- NMT không đồng nghĩa với số byte resident của process được OS/container báo cáo.
- NMT không theo dõi đầy đủ mọi cấp phát do **JNI/third-party native code** và một số vùng JDK libraries; output có thể bỏ sót phần memory ngoài phạm vi NMT.
- NMT `reserved` là không gian địa chỉ ảo được giữ, không đồng nghĩa RAM vật lý đang dùng. `committed` là vùng VM đã commit trong phạm vi theo dõi; nó cũng không đồng nghĩa chính xác RSS.
- NMT report không thay thế heap dump để tìm Java object giữ tham chiếu.

Trên HotSpot, NMT **mặc định tắt** và cần được bật ở **lúc JVM khởi động**:

```bash
# Ví dụ khởi chạy mới, không phải lệnh điều khiển PID đang chạy:
java -XX:NativeMemoryTracking=summary -jar application.jar
```

Có hai mức chính: `summary` để xem theo category, `detail` để xem call site chi tiết; `detail` tốn overhead hơn và phải được chọn phù hợp từ startup. Oracle mô tả overhead của NMT có thể khoảng **5–10%**, vì vậy không coi đây là tùy chọn miễn phí cho mọi production workload.

**Không thể bật NMT từ off lên summary/detail bằng `jcmd` trên HotSpot đang chạy**; chỉ có thể dừng theo hỗ trợ VM, việc dừng có thể không khởi động lại được trong process đó. Nếu thấy “Native memory tracking is not enabled”, đừng chạy `VM.native_memory baseline` lặp đi lặp lại hoặc mặc nhiên kết luận RSS tăng là không có vấn đề. Muốn có NMT lần sau phải chọn startup option và kế hoạch deployment thích hợp.

### 7.2 Cú pháp báo cáo, baseline và diff

Khi JVM **đã chạy với NMT enabled**:

```bash
jcmd 12345 VM.native_memory summary
jcmd 12345 VM.native_memory summary scale=MB
jcmd 12345 VM.native_memory baseline
jcmd 12345 VM.native_memory summary.diff
```

- `summary`: ảnh tổng hợp **reserved/committed** theo category và tổng giá trị trong phạm vi NMT.
- `scale=MB`: đổi đơn vị trình bày; không phải thay đổi memory consumption.
- `baseline`: đặt **mốc so sánh mới**, là thay đổi state của cơ chế đo NMT (không trực tiếp thay thế cấu hình ứng dụng).
- `summary.diff`: chênh lệch với baseline gần nhất; nếu chưa baseline, không có thông tin so sánh thích hợp.
- `detail`/`detail.diff`: cần NMT được bật ở **detail** và dữ liệu call site phù hợp; không kỳ vọng nhận stack call site chi tiết từ `summary`.

Khi dùng `detail`, ví dụ:

```bash
# Chỉ phù hợp nếu JVM được khởi động với -XX:NativeMemoryTracking=detail.
jcmd 12345 VM.native_memory detail
jcmd 12345 VM.native_memory detail.diff
```

NMT `baseline` không tự ghi “chất lượng baseline” — nếu đặt mốc lúc JVM còn khởi động, class loading/JIT, memory tăng tự nhiên sau đó có thể bị nhầm là leak. Hãy chọn baseline sau warm-up và so sánh **cùng pha workload**, đủ nhiều thời điểm.

### 7.3 Ví dụ diễn giải NMT

Giả sử output minh họa:

```text
Total: reserved=4000MB, committed=900MB
- Java Heap (reserved=2048MB, committed=512MB)
- Thread    (reserved=220MB, committed=30MB)
- Code      (reserved=250MB, committed=64MB)
...
```

Đây là **số giả định để giải thích thuật ngữ**, không phải stdout định dạng chính xác của một JVM. Bạn không thể kết luận “JVM đang dùng 4 GB RAM” vì số reserved là 4 GB. Bạn cũng không thể kết luận RSS đúng 900 MB vì committed memory của NMT không đo mọi native allocation và không bằng resident pages của OS.

Giả sử `summary.diff` sau 20 phút báo category `Thread` committed tăng 80 MB; lúc này cần hỏi liệu có tăng thread count/stack memory, thay đổi workload, hay một cơ chế tạo thread không được thu hồi. Nếu `Code` tăng trong giai đoạn warm-up, đó có thể là JIT compilation bình thường. Nếu `Class`/metaspace tăng, kiểm tra classloaders và class unloading. **Diff là bằng chứng xu hướng, chưa phải nguyên nhân leak**.

### 7.4 Kết hợp với công cụ khác

- **Heap lớn**: so `GC.heap_info`, heap usage/GC metrics, allocation, histogram nếu cần.
- **Metaspace/class growth**: `VM.metaspace` hoặc `VM.classloader_stats` nếu JVM hỗ trợ; `VM.metaspace basic` trên HotSpot JDK 21 cho thống kê gọn, impact tùy options.
- **Thread/native stack growth**: `Thread.print`, thread count, OS/process thread count và NMT category `Thread`.
- **Code cache**: `Compiler.codecache` và NMT category `Code`.
- **RSS tăng nhưng NMT ổn định**: có thể liên quan native allocations ngoài phạm vi NMT, mappings, direct/native libraries hoặc tính chất resident pages; cần số liệu OS/container và các công cụ native hợp lệ để tiếp tục.

Không cộng nhầm Java heap `used` vào NMT total như thể hai phần hoàn toàn tách biệt: NMT đã tính phạm vi Java Heap reserved/committed. Không dùng NMT category như phân loại object của heap histogram; chúng là **hai cấp quan sát khác nhau**.

## 8. Bảng lựa chọn lệnh theo triệu chứng

| Triệu chứng/câu hỏi | Bắt đầu bằng | Nếu cần sâu hơn | Tránh nhầm lẫn |
| --- | --- | --- | --- |
| Service đang chạy JVM nào và với cờ nào? | `VM.version`, `VM.uptime`, `VM.flags` | `VM.command_line`, selected properties đã redact | Startup input khác effective flags; không dùng `java -version` của shell thay cho target |
| Request bị treo hoặc lock contention | `Thread.print` (vài snapshot), metrics | `Thread.print -l`, JFR lock/park events | Một `WAITING` stack không phải deadlock |
| CPU process cao, cần hotspot | Metrics CPU, `JFR.check` | JFR profile được giới hạn hoặc CPU profiler phù hợp | `Thread.print` đơn lẻ không phải CPU profile |
| Heap gần giới hạn/GC dày | `GC.heap_info`, GC logs/JFR events | Histogram hoặc heap dump có kiểm soát | Heap snapshot không chứng minh leak |
| Nghi class nào giữ nhiều object | `GC.class_histogram` nếu chi phí cho phép | `GC.heap_dump` và phân tích retained references | Histogram counts không cho biết reference graph |
| Warm-up/JIT chậm | `Compiler.queue`, `Compiler.codecache` | `Compiler.codelist`, JFR compiler events, flags | Queue tại 1 thời điểm không kết luận nguyên nhân latency |
| Native memory/RSS tăng | Heap + OS RSS + NMT status | `VM.native_memory summary`/diff **nếu NMT enabled** | Reserved ≠ committed ≠ RSS; NMT không bao phủ mọi native allocation |
| Incident ngắn/hiếm | Metrics, logs, JFR recording sẵn có | `JFR.dump` phần lịch sử còn giữ, capture chi tiết khi trigger | JFR bắt đầu muộn không ghi lại sự kiện trước đó |

Thứ tự trên là **điểm khởi đầu**, không buộc mọi incident đều dùng tất cả nhóm lệnh. Mục tiêu là chọn **ít lệnh nhất nhưng đủ bằng chứng**.

## 9. Bài thực hành Java 17+: JVM mẫu để thử sáu nhóm

Tạo file **`JcmdLab.java`**. Chương trình giữ một JVM tồn tại trong 120 giây, tạo một background thread ở trạng thái ngủ và tính một số phép toán đơn giản. Nó đủ để quan sát PID, threads, heap, compiler state và thử JFR/NMT trên môi trường học. Không dùng một production JVM làm mục tiêu cho các lệnh có impact cao trong bài thực hành.

```java
public final class JcmdLab {
    private static volatile long result;

    public static void main(String[] args) throws InterruptedException {
        System.out.println("JcmdLab READY");
        System.out.println("PID=" + ProcessHandle.current().pid());

        Thread sleeper = new Thread(() -> {
            try {
                Thread.sleep(120_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "demo-sleeper");

        sleeper.start();

        long sum = 0;
        for (long i = 0; i < 2_000_000; i++) {
            sum += i % 7;
        }
        result = sum;

        sleeper.join();
        System.out.println("JcmdLab DONE");
    }
}
```

Biên dịch và chạy bằng JDK 17+ (các ví dụ command jcmd nhắm **HotSpot JDK 21**):

```bash
javac JcmdLab.java
java -XX:NativeMemoryTracking=summary JcmdLab
```

**Dòng stdout đầu tiên chính xác**:

```text
JcmdLab READY
```

Dòng tiếp theo là `PID=<số PID thật>`; sau khi background thread ngủ đủ 120 giây, chương trình in `JcmdLab DONE`. Thời gian chạy và PID không cố định; có thể dừng sớm bằng Ctrl+C. Lệnh có `-XX:NativeMemoryTracking=summary` **chỉ áp dụng cho JVM demo mới khởi động**; đây không phải thao tác bật NMT cho một JVM đang chạy.

Trong terminal khác, dùng PID mà chương trình in, ví dụ **12345**:

```bash
jcmd 12345 help
jcmd 12345 VM.version
jcmd 12345 VM.uptime
jcmd 12345 VM.flags
jcmd 12345 Thread.print
jcmd 12345 GC.heap_info
jcmd 12345 Compiler.queue
jcmd 12345 Compiler.codecache
jcmd 12345 JFR.check
jcmd 12345 VM.native_memory summary
```

Kỳ vọng có cơ sở:

- `VM.version` xác nhận runtime của **JcmdLab**, `VM.uptime` tăng theo thời gian thực.
- `Thread.print` có thể cho thấy thread tên `demo-sleeper` ở trạng thái ngủ/timed waiting **nếu thu trước khi nó kết thúc**. Không khẳng định số thread, thứ tự hay mọi stack đều giống nhau trên các máy.
- `GC.heap_info` có dữ liệu về heap tùy collector; `Compiler.queue` có thể trống vì demo rất nhỏ, không coi đó là lỗi.
- `JFR.check` trước khi start thường chưa có recording do demo tạo; JVM có thể có recording khác do startup options.
- `VM.native_memory summary` có dữ liệu NMT theo category vì JVM demo được start với `summary`; các con số phụ thuộc môi trường.

Nếu muốn thử thu JFR ngắn trên **JcmdLab**:

```bash
jcmd 12345 JFR.start name=lab settings=profile duration=20s filename=jcmd-lab.jfr
jcmd 12345 JFR.check
```

Chạy khi JVM còn sống đủ lâu (trong vòng 120 giây). Sau 20 giây, kiểm tra file ở filesystem mà JVM demo dùng; đọc bằng `jfr summary jcmd-lab.jfr`. Nội dung không có stdout cố định vì activity và JVM quyết định events/samples.

Để thực hành `baseline`/diff, chỉ trên JVM demo có NMT:

```bash
jcmd 12345 VM.native_memory baseline
jcmd 12345 VM.native_memory summary.diff
```

Hai lần đo gần nhau có thể có mức thay đổi nhỏ hoặc dao động; không kỳ vọng sẽ thấy “memory leak” vì chương trình này không tạo leak. Thực hành ưu tiên các lệnh quan sát; không cần `GC.heap_dump` hay `GC.class_histogram` để hoàn thành bài, vì chúng có tác động cao và không bổ sung nhiều giá trị cho demo nhỏ.

### Những điều QA cần đối chiếu trong bài thực hành

1. Mọi lệnh dùng **PID thật**, không copy `12345` sang process không liên quan.
2. `jcmd` chạy trong môi trường có quyền attach, tương thích JVM và namespace; process chưa kết thúc.
3. `VM.native_memory` hoạt động do startup flag `-XX:NativeMemoryTracking=summary`, không vì lệnh `jcmd` tự bật NMT.
4. `JFR.start` có thể tạo dữ liệu tùy workload/setting; `JFR.check` chỉ cho biết trạng thái recording.
5. `Thread.print` là snapshot; thông tin thread `demo-sleeper` có thể biến mất sau 120 giây.
6. `GC.heap_info`, `Compiler.queue`, `NMT` được đọc và diễn giải theo **giá trị thực**, không chép số mẫu giả vào báo cáo.

## 10. Quy trình chẩn đoán production theo mức can thiệp

### Bước 1: Đặt câu hỏi và chọn tiến trình

Ghi sự cố, `t_start`/`t_detect`, service, pod/container/node, PID, process start time, version/deploy revision và phạm vi request. Một số công cụ in command line có secrets; quyết định ngay nguồn lưu và mức chia sẻ dữ liệu.

### Bước 2: Lấy bằng chứng nhẹ và fingerprint

Thường bắt đầu với `VM.version`, `VM.uptime`, `VM.flags` và vài chỉ số hệ điều hành/JVM đã có. Nếu cần command line, đọc trong môi trường hạn chế quyền và **redact**. Đừng chạy đồng thời hàng loạt heap dumps hoặc profile trên tất cả các replica.

### Bước 3: Chọn nhóm theo triệu chứng

- **Threads/locks** nếu latency cao nhưng CPU thấp hoặc request stuck.
- **GC.heap_info** nếu heap/GC có dấu hiệu bất thường.
- **Compiler.queue/codecache** nếu nghi slow startup hoặc JIT/cache pressure.
- **JFR** để phân tích timeline CPU/allocation/GC/lock theo đúng pha sự cố.
- **NMT** nếu native memory tăng và JVM đã bật NMT; nếu NMT tắt, ghi giới hạn thay vì tìm cách bật trực tiếp trong process.

### Bước 4: Đặt ngân sách tác động

Với mỗi lệnh, ghi Impact, duration, output size, disk space, CPU/memory overhead, số replica, quyền và điều kiện dừng. Nếu cần histogram/heap dump, chỉ chạy sau khi cân nhắc ảnh hưởng full GC/pause, khả năng chứa dữ liệu nhạy cảm và nơi ghi file.

### Bước 5: Đọc bằng chứng theo đúng ngữ nghĩa

Phân biệt snapshots với dữ liệu theo thời gian; tách **correlation** và **causation**. Một JVM có nhiều threads `WAITING` chưa chắc deadlock; `byte[]` chiếm heap lớn chưa chắc leak; `Code` NMT tăng sau startup chưa chắc vấn đề; GC event trùng latency spike cần kiểm tra traffic, blocking và các yếu tố khác.

### Bước 6: Kết thúc các thao tác có trạng thái

Nếu tự bật JFR không giới hạn, cần xác định thời điểm dừng/dump và làm sạch artifact. NMT baseline chỉ là mốc mới và không cần/không nên reset bừa bãi trong lúc người khác đang so sánh; không dùng `VM.native_memory shutdown` trừ khi thật sự muốn tắt NMT và hiểu không thể bật lại qua `jcmd`. Heap dump/JFR file phải được quản lý theo quyền truy cập, retention và chính sách dữ liệu.

### Bước 7: Báo cáo và tái kiểm tra

Nêu rõ lệnh thực đã chạy, timestamp UTC, version/JDK, PID/start time, flags liên quan, các giá trị quan sát **và giới hạn phép đo**. Sau can thiệp có kiểm soát, dùng metrics/JFR/trace so cùng điều kiện tải để đánh giá kết quả. Nếu không có bằng chứng tại thời điểm incident, ghi “không đủ dữ liệu” thay vì dùng kết quả hiện tại để kết luận ngược về quá khứ.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Giải thích đúng |
| --- | --- |
| `jcmd -l` liệt kê mọi JVM trên host và trong mọi container. | PID namespace, quyền và implementation ảnh hưởng danh sách; cần định danh đúng target. |
| Tất cả lệnh `jcmd` đều chỉ đọc và an toàn tuyệt đối. | `JFR.start/stop` đổi trạng thái recording; histogram/dump impact cao; `GC.run` kích hoạt GC. |
| `VM.flags` là nguyên văn những gì operator truyền lúc khởi động. | Nó cho thấy flag/value hiện hành, có thể có default/ergonomics và runtime changes. |
| Một `Thread.print` đủ để kết luận CPU hotspot hay deadlock. | Chỉ là snapshot; cần nhiều mốc, lock owners, profile/metrics và bối cảnh tải. |
| `Thread.print` của JDK 21 bao gồm mọi unmounted virtual thread. | Không mặc nhiên; cần công cụ/recording phù hợp JDK và trạng thái virtual threads. |
| `GC.heap_info` bằng RSS của process. | Java heap là một phần memory của process; còn native memory, code cache, stacks, mappings. |
| `GC.class_histogram` cho biết chính xác đối tượng gây leak. | Histogram thống kê theo class, không chỉ ra đường tham chiếu giữ object. |
| `GC.heap_dump` chỉ tạo file, không tác động đến ứng dụng. | Có thể full GC, pause và I/O lớn; chứa dữ liệu nhạy cảm. |
| `Compiler.queue` rỗng nghĩa là JVM không dùng JIT. | Queue là ảnh tại một thời điểm; compiled methods vẫn có thể tồn tại trong code cache. |
| `JFR.check` trống nghĩa là JVM không thể dùng JFR. | Chỉ cho thấy recording hiện có; JVM có thể hỗ trợ start mới. |
| Bật `JFR.start` sau incident thì vẫn xem được nguyên nhân cũ. | Recording chỉ giữ lịch sử nếu đã được bật/giữ dữ liệu trước đó. |
| `JFR.dump` dừng recording. | Dump xuất dữ liệu, recording vẫn tiếp tục; dừng bằng `JFR.stop`. |
| `VM.native_memory summary` tự bật NMT nếu chưa có. | NMT phải được bật từ startup; report không bật cơ chế theo dõi. |
| NMT `reserved` là số RAM process đang dùng. | Reserved address space khác committed và khác RSS. |
| NMT bao phủ mọi cấp phát native từ JNI/third-party libraries. | NMT có phạm vi internal HotSpot, còn những vùng ngoài phạm vi cần công cụ bổ sung. |
| NMT diff tăng chắc chắn là memory leak. | Có thể là warm-up, compiler, class loading, thread count hoặc thay đổi workload. |

## 12. Câu hỏi tự đánh giá

**1.** Service có 600 request đang treo, CPU thấp. Nên chạy `GC.heap_dump` ngay không?

**Trả lời:** không. Bắt đầu từ request/queue/pool metrics, `Thread.print` (một vài snapshot) và lock/wait evidence; nếu cần, JFR lock/park events. Heap dump có tác động lớn và chưa trực tiếp trả lời luồng đang chờ gì.

**2.** `VM.flags -all` cho thấy `MaxHeapSize` nhưng `VM.command_line` không có `-Xmx`. Có mâu thuẫn không?

**Trả lời:** không. JVM có thể chọn heap theo default/ergonomics/resource limits. Startup arguments và effective flags là hai lớp dữ liệu khác nhau.

**3.** Code cache tăng trong vài phút warm-up, `Compiler.queue` có hàng đợi. Có đủ kết luận JIT lỗi không?

**Trả lời:** chưa đủ. JIT compilation và code cache growth là hoạt động bình thường lúc warm-up. Đối chiếu latency, CPU, codecache status, compiler events, flags và các mốc steady-state.

**4.** JVM chưa bật NMT; có thể chạy `jcmd PID VM.native_memory baseline` để bắt đầu theo dõi memory không?

**Trả lời:** không. Trên HotSpot phải bật NMT bằng `-XX:NativeMemoryTracking=summary` hoặc `detail` từ lúc khởi động. Nếu chưa bật, dùng dữ liệu OS/heap/JFR thích hợp và ghi giới hạn.

**5.** NMT báo `reserved=5 GB`, `committed=1.2 GB`, hệ điều hành báo RSS 1.4 GB. Có thể cộng 5 + 1.2 + 1.4 không?

**Trả lời:** không. Chúng là các khái niệm/đơn vị thống kê khác nhau, nhiều phần chồng lấn. Reserved không phải RAM resident; committed NMT không phải RSS và NMT không bao phủ mọi cấp phát native.

**6.** Một JFR rolling recording đang chạy. Muốn lưu 10 phút gần nhất mà vẫn tiếp tục thu, chọn lệnh nào?

**Trả lời:** `jcmd PID JFR.dump name=<recording> filename=<file> maxage=10m` nếu recording đang chạy, còn giữ đủ dữ liệu và file có đường dẫn hợp lệ. `JFR.dump` không dừng recording; chỉ `JFR.stop` khi thực sự muốn kết thúc.

**7.** `GC.class_histogram` thấy nhiều `byte[]`. Có thể kết luận leak trong cache không?

**Trả lời:** chưa. Cần kiểm tra live objects, reference chains/retained sizes, lifecycle và xu hướng qua thời gian. Một histogram lớn có thể phản ánh workload hợp lệ.

**8.** Sau `JFR.start settings=profile duration=60s` thấy CPU process tăng. Có chứng minh ứng dụng gốc vốn CPU cao không?

**Trả lời:** chưa. Recording có overhead; so baseline trước/sau, chọn settings/thời lượng và workload tương đương. Đừng bỏ qua chi phí đo khi diễn giải nguyên nhân.

## 13. Ghi nhớ nhanh

- **VM** trả lời *“JVM này là ai, đang cấu hình thế nào?”*.
- **Thread** trả lời *“các luồng đang ở đâu và chờ tài nguyên nào tại thời điểm chụp?”*.
- **Heap/GC** trả lời *“Java heap và các loại object đang phân bố thế nào?”*, với chi phí tăng mạnh khi dùng histogram/dump.
- **Compiler/JIT** trả lời *“VM đang compile gì, code cache ra sao?”*.
- **JFR** cung cấp *“timeline events/samples trong một cửa sổ đo”*, cần recording được bật đúng thời điểm.
- **NMT** cung cấp *“reserved/committed native/internal JVM theo category và chênh lệch từ baseline”*, **chỉ khi đã bật NMT từ startup**.

Chọn lệnh dựa trên **triệu chứng, độ sâu bằng chứng cần có, mức ảnh hưởng và quyền truy cập**. Khi thu bằng chứng, ghi đúng PID, phiên chạy, timestamp, settings và giới hạn phép đo; diễn giải mỗi snapshot trong bối cảnh thay vì gán ngay nguyên nhân gốc.

### Tài liệu tham khảo

- [Oracle JDK 21 — The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): danh sách command và cú pháp Impact, `VM.*`, `Thread.print`, `GC.*`, `Compiler.*`, `JFR.*`, `VM.native_memory`.
- [Oracle JDK 21 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html): cách bật `-XX:NativeMemoryTracking`, baseline/diff, reserved/committed, giới hạn NMT và overhead.
- [Oracle Java SE 21 — Java Flight Recorder API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/module-summary.html): event recording, cấu hình và phạm vi API JFR.
- [Oracle JDK 21 — The jfr Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): đọc/tóm tắt file `.jfr` và công cụ phân tích file.
