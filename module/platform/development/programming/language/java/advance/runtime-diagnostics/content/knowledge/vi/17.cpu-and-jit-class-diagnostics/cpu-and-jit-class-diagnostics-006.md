# 17.6 Compiler.queue, Compiler.codecache và sự kiện biên dịch trong JFR

## Mục tiêu

Khi CPU tăng vào giai đoạn warm-up, độ trễ thất thường sau khi deploy, hoặc JVM thông báo code cache gần đầy, người vận hành cần phân biệt **công việc biên dịch đang chờ**, **nơi chứa mã máy đã biên dịch** và **lịch sử các lần biên dịch**. Ba góc nhìn tương ứng trong HotSpot là:

- **jcmd PID Compiler.queue**: ảnh chụp các method đang **xếp hàng chờ JIT compile**.
- **jcmd PID Compiler.codecache**: ảnh chụp **bố cục, mức sử dụng và giới hạn code cache** tại thời điểm gọi, tùy phiên bản JVM.
- **JFR compiler/code-cache events**: chuỗi sự kiện **qua thời gian**, giúp biết method nào được compile, khoảng thời gian compile, compiler nào tham gia, code cache biến động và có sự cố code cache full hay không.

Sau bài này, bạn sẽ biết chạy các lệnh an toàn, diễn giải đúng các trường quan trọng, chọn JFR events cần xem, tương quan theo thời điểm, tránh nhầm compile CPU với application CPU và thực hành bằng Java 17+.

**Phạm vi chính:** HotSpot/OpenJDK 17–21, ưu tiên tên command và event trong JDK 21. Tên event, field, threshold, cách chia code cache hoặc định dạng đầu ra có thể thay đổi theo bản JDK/vendor và cấu hình. Khi phân tích thật, hỏi JVM trực tiếp bằng **jcmd PID help** và file JFR bằng **jfr metadata**.

## 1. Từ bytecode đến JIT và code cache

Java source được biên dịch thành bytecode. Trong HotSpot, JVM có thể thực thi bytecode bằng interpreter trước, theo dõi mức độ “nóng” của method/loop, rồi đưa những đoạn phù hợp vào **JIT compilation** để tạo machine code. Mã máy đó được quản lý trong **code cache**. Đây là một trong những cơ chế giải thích vì sao cùng workload có thể nhanh hơn sau khi JVM đã warm-up.

~~~text
Ứng dụng gọi method / chạy loop
                |
                v
     Interpreter và profiling
                |
     Hot method / OSR candidate
                |
                v
          Compile queue
                |
        Compiler thread(s)
          C1 hoặc C2
                |
                v
    JIT machine code (nmethod)
                |
                v
            Code cache
                |
           CPU thực thi
~~~

Đồ thị trên là mô hình khái niệm; HotSpot có các tối ưu, chuyển tier, compile lại, OSR và deoptimization phức tạp hơn. **C1** thường ưu tiên tốc độ compile và profiling; **C2** đầu tư nhiều tối ưu hơn với chi phí compile có thể lớn. Với tiered compilation, method có thể được compile ở nhiều level, và mức level không nhất thiết tăng đơn điệu cho mọi method.

- **Compile task** là một công việc biên dịch đang chờ hoặc đang xử lý.
- **Compiled method/nmethod** là sản phẩm mã máy, có thể được sử dụng, trở nên not entrant/zombie, bị deopt hoặc cuối cùng được reclaim.
- **Code cache** là vùng dành cho mã được JVM tạo và các phần mã hỗ trợ runtime; **không phải Java heap** và không chứa object instances như histogram.
- **JFR** ghi các event liên quan quá trình này khi được enable và vượt threshold; nó không phải bản sao tự động của output jcmd.

### Vì sao cần ba nguồn?

Một lúc queue dài không nói được bao nhiêu code cache còn trống. Một code cache gần đầy không nói được method nào đang compile chậm. Một JFR event Compilation kéo dài không chứng minh người dùng bị latency đúng ở thời điểm đó. **Phải ghép snapshot (queue/cache) với timeline (JFR) và metric CPU/latency.**

## 2. Compiler.queue: những method nào đang chờ biên dịch?

Trên JVM HotSpot đang chạy, xác định PID rồi hỏi trợ giúp:

~~~bash
jcmd -l
jcmd <PID> help Compiler.queue
jcmd <PID> Compiler.queue
~~~

Thay **<PID>** bằng process ID thật; nếu đang trong shell Linux/macOS có thể dùng biến **PID=12345** rồi **jcmd "$PID" Compiler.queue**. Công cụ **jcmd** cần truy cập JVM đích với quyền phù hợp. Với JVM trong container, phải xác định đúng PID/namespace và cách attach.

Theo tài liệu **jcmd của JDK 21**, **Compiler.queue** in các method đang xếp hàng chờ compile; tác động được đánh giá **Low**. Đây là **snapshot rất ngắn**, không phải log lịch sử, và không bao gồm mọi method đã compile xong.

### Cách đọc

Một output minh họa có thể có tên C1/C2 compilation queues và danh sách compile tasks; tên cột, thứ tự và chi tiết thực tế thay đổi theo JVM:

~~~text
C1 compile queue:
  ...  app.service.Worker::handle (... bytes)

C2 compile queue:
  ...  app.core.Parser::parse (... bytes)
~~~

Các dòng trên **không phải stdout chính xác** cần mong đợi. Một JVM có thể in **queue empty** hoặc chỉ một trong các loại compile queue. Số item tại thời điểm chụp có thể bằng 0 ngay cả khi trong giây trước diễn ra hàng chục hoặc hàng trăm compilations.

### Khi nào queue dài đáng chú ý?

Khi liên tục lấy mẫu trên workload tương tự, queue lớn lên và không kịp rút đi có thể chỉ ra **compiler backlog**: mã nóng đang chờ được tối ưu, JVM phải chạy interpreter hoặc code ở tier thấp lâu hơn. Nguyên nhân có thể là bùng nổ method mới sau startup, code generation động, class loading, giới hạn CPU/container CPU throttling, compiler threads bận, hoặc workload có nhiều phương thức được compile.

**Không suy từ một queue snapshot rằng JIT bị treo.** Queue có thể đang tăng tạm thời trong warm-up rồi giảm. Nên đo lặp trong khoảng xảy ra sự cố, ghi thời điểm, CPU, số compilation hoàn tất và code cache status. Với ứng dụng đã ổn định, queue rỗng thường là bình thường.

**Queue không cho biết duration đã chờ của mọi task.** Để phân tích điều gì thực sự được compile và mất bao lâu, cần JFR **jdk.Compilation** cùng các event bổ sung nếu được enable.

## 3. Compiler.codecache: nơi chứa mã JIT đã được biên dịch

Các lệnh:

~~~bash
jcmd <PID> help Compiler.codecache
jcmd <PID> Compiler.codecache
~~~

Trong JDK 21, command này in bố cục và ranh giới của code cache, tác động **Low**. Nhiều build HotSpot cũng in sức chứa, phần đã dùng, max_used, free và phạm vi địa chỉ.

Ví dụ cấu trúc output **chỉ để nhận diện**, số giả định:

~~~text
CodeHeap 'non-profiled nmethods': size=120000Kb used=40000Kb max_used=42000Kb free=80000Kb
CodeHeap 'profiled nmethods':     size=120000Kb used=25000Kb max_used=28000Kb free=95000Kb
CodeHeap 'non-nmethods':           size=5000Kb used=3000Kb max_used=3200Kb free=2000Kb
...
~~~

Không lấy các số giả định làm ngưỡng mặc định của JDK. Bản JDK không bật segmented code cache có thể báo một vùng duy nhất; output có thể là bytes/Kb hoặc có thêm thống kê khác.

### 3.1. Segmented Code Cache

Khi bật **-XX:+SegmentedCodeCache**, HotSpot có thể chia thành:

| Code heap | Chứa gì về cơ bản | Cách đọc |
| --- | --- | --- |
| **non-nmethods** | Phần mã runtime hỗ trợ, adapters, stubs hoặc các mã không phải nmethod | Không coi tất cả là Java methods ứng dụng |
| **profiled nmethods** | Mã JIT có instrumentation/profiling, thường liên quan các tier thấp hơn | Tăng khi JVM đang học đặc điểm workload |
| **non-profiled nmethods** | Mã đã tối ưu, thường liên quan level cao hơn | Tăng trong quá trình compile các hot methods |

Theo Oracle JDK 21, segmented cache được bật mặc định khi tiered compilation được bật và **ReservedCodeCacheSize từ 240 MB trở lên**; với cấu hình khác có thể không chia như vậy. Các segments có giới hạn riêng và **không tự resize trong lúc chạy**.

Vì vậy “tổng free còn nhiều” không đủ để loại trừ áp lực ở **một code heap cụ thể**. Nếu code cache được phân đoạn, phải xem từng segment, không chỉ tổng.

### 3.2. used, max_used, free, reserved và committed

- **used** trong output code cache biểu thị dung lượng do các code blobs/nmethods sử dụng theo cách HotSpot báo tại thời điểm đo.
- **max_used** thường là đỉnh sử dụng được VM ghi nhận trong vòng đời liên quan, không phải dung lượng tối đa cấu hình.
- **free** là phần còn trống trong code heap theo cách HotSpot tính; chưa phản ánh đầy đủ mức phân mảnh và khả năng phân bổ cho một blob có kích thước/đặc tính cụ thể.
- **ReservedCodeCacheSize** là giới hạn vùng code cache dự trữ; không đồng nghĩa lượng RAM resident.
- **reserved**, **committed** và **resident** là các khái niệm khác nhau. Nếu so với NMT/OS, phải đối chiếu cùng loại metric và phạm vi.

**Code cache không phải Java heap**: giảm sử dụng heap object không trực tiếp xóa compiled machine code, và GC heap thông thường không phải giải pháp tổng quát cho áp lực code cache.

### 3.3. Code cache đầy xảy ra điều gì?

HotSpot có thể không cấp phát được thêm code blob ở code heap phù hợp; JVM có thể báo cảnh báo code cache full, dừng/giảm JIT compilation tạm thời, loại bỏ mã không còn hữu ích thông qua code sweeper và có cơ chế phục hồi tùy phiên bản/cấu hình.

Các hệ quả có thể thấy là:

1. Method nóng mới không được compile lên tier mong muốn.
2. CPU ứng dụng và latency thay đổi vì chạy interpreter hoặc compiled code kém tối ưu hơn.
3. Compiler queue và hoạt động compile có thể biến động bất thường.
4. Có thể xuất hiện event JFR **jdk.CodeCacheFull**, và khi JIT hoạt động trở lại có thể thấy **jdk.JITRestart**.

**Không kết luận có code cache full chỉ vì free thấp**: cần kết hợp warning/JFR event, runtime status, từng segment, sweep activity và xu hướng. Một lần chạm ngưỡng đã được khắc phục không tương đương “JIT bị vô hiệu hóa vĩnh viễn”.

### 3.4. Giới hạn và cấu hình liên quan

Oracle JDK 21 tài liệu hóa các cờ **-XX:ReservedCodeCacheSize**, **-XX:+SegmentedCodeCache** và, khi chia segment, **-XX:NonNMethodCodeHeapSize**, **-XX:ProfiledCodeHeapSize**, **-XX:NonProfiledCodeHeapSize**.

**Không tăng ReservedCodeCacheSize theo phản xạ.** Điều chỉnh cần dựa trên số liệu cache usage, code sweeper, compilation demand, giới hạn bộ nhớ native của host/container và thí nghiệm có kiểm soát. Một giới hạn lớn hơn có thể tăng không gian địa chỉ reserve, không lập tức có nghĩa RSS sẽ tăng bằng mức reserve.

## 4. JFR: lịch sử compiler và code-cache events

JFR bổ sung **timeline** giúp giải thích trước/sau một lần jcmd snapshot. Các tên event dưới đây là những event thường gặp ở HotSpot/JDK 17–21; tập chính xác và field nên kiểm tra bằng metadata của file hoặc JDK thực tế.

| Event type thường gặp | Vai trò | Thông tin cần xem |
| --- | --- | --- |
| **jdk.Compilation** | Kết quả một compilation attempt | Thời điểm, duration, method, compiler, compile level, compile ID, success, OSR nếu có |
| **jdk.CompilerPhase** | Một pha trong quá trình compile | Pha nào lâu, compile ID dùng liên kết về compilation |
| **jdk.CompilerStatistics** | Thống kê hoạt động compiler | Compile count, thời gian compile, bailout/invalidations... tùy schema |
| **jdk.CompilerConfiguration** | Thông số cấu hình compiler | Cách JVM/tiered compiler được thiết lập |
| **jdk.CompilationFailure** | Thông tin compilation failure | Compile ID và lý do, khi event được bật |
| **jdk.CodeCacheConfiguration** | Cấu hình các code heaps | Capacity, các thành phần liên quan theo schema |
| **jdk.CodeCacheStatistics** | Số liệu code heap tại các mốc | Code heap type, capacity, unallocated/free, số entry, full count... |
| **jdk.CodeCacheFull** | Sự cố code heap không còn chỗ phù hợp | Thời điểm, heap/type, capacity và dấu hiệu hết chỗ |
| **jdk.JITRestart** | JIT được khởi động lại sau khi ngừng | Tương quan với sweeping/giải phóng code cache |
| **jdk.CodeSweeperStatistics** | Hoạt động quét/thu hồi compiled code | Xem code sweeper có reclaim không |
| **jdk.Deoptimization** | Method compiled gặp giả định không còn đúng và deopt | Tương quan với thay đổi tier hoặc performance |

**Cảnh báo:** một số event có thể được **disabled**, có **threshold lớn**, chỉ phát **periodic/everyChunk**, hoặc không được JVM phiên bản hiện tại hỗ trợ. Việc event type xuất hiện trong metadata **không đảm bảo có instance trong recording**. Không dựa vào bảng này để giả định Count phải lớn hơn 0.

### 4.1. Compile ID và method

Các compilation events có thể mang **compileId**, **method**, **compiler**, **compileLevel**, **duration** và trạng thái thành công. **compileId** giúp nối một Compilation với CompilerPhase hoặc CompilationFailure **trong cùng bối cảnh JVM/recording** khi các type đều được ghi. Không dùng compileId làm khóa toàn cục giữa nhiều JVM khởi động lại hoặc file từ các process khác nhau.

Trong một số schema HotSpot cũ, tên trường thành công của **jdk.Compilation** được ghi là **succeded** (khác chính tả tiếng Anh thường dùng **succeeded**). **Đừng tự sửa tên field trong parser**: chạy **jfr metadata --events jdk.Compilation file.jfr** để lấy tên nguyên văn đúng phiên bản.

**Một method có thể có nhiều compilation IDs** vì compile lại, thay compile level, OSR hoặc invalidation. Không đếm mỗi Compilation event thành một “method khác nhau”.

### 4.2. Compilation duration có phải thời gian request chậm?

Không. Duration của **jdk.Compilation** là thời gian một compilation attempt theo ngữ nghĩa event, không phải duration của method khi ứng dụng thực thi nó. Hoạt động compile thường ở compiler threads riêng.

Ví dụ một C2 compilation kéo dài 300 ms không có nghĩa request gọi method đó mất 300 ms. Tuy nhiên compile có thể tiêu thụ CPU, tranh tài nguyên khi container bị giới hạn và ảnh hưởng warm-up. Cần tương quan **compiler activity**, CPU load/thread CPU, **request latency** và thời điểm.

### 4.3. Compiler Statistics có thể là counters tích lũy

Các event thống kê có thể đưa ra **counter tăng dần** hoặc snapshot tại chu kỳ/chunk. Nếu so hai thời điểm, lấy **delta giữa các mốc** trong cùng JVM; không coi một giá trị counter cuối là số compilation chỉ của một giây. Nếu file thiếu đầu giai đoạn JVM, counter có thể đã lớn trước khi recording bắt đầu.

CodeCacheStatistics cũng có thể là snapshot định kỳ. Khoảng cách giữa các instances do **period** hoặc chunk rotation quyết định. Không mặc định chúng có độ phân giải một giây.

### 4.4. Ghi nhận CodeCacheFull và CompilerPhase

**jdk.CodeCacheFull** là chỉ báo rất mạnh để xét vấn đề hết code cache trong khoảng ghi. Ngược lại **Count=0 không chứng minh code cache chưa từng đầy**: event có thể bị tắt, recording không bao phủ sự cố, hoặc không có event instance được ghi.

**jdk.CompilerPhase** có thể tạo nhiều dữ liệu và có threshold; chỉ bật ở độ chi tiết cần thiết khi điều tra compiler latency cụ thể. Nó không tự động lưu tất cả optimization decisions, và không thay thế công cụ compiler log chuyên sâu.

## 5. Thao tác JFR: kiểm tra file trước khi kết luận

Sau khi có file **compiler.jfr**, bắt đầu bằng:

~~~bash
jfr summary compiler.jfr
jfr metadata --events jdk.Compilation,jdk.CompilerStatistics,jdk.CodeCacheStatistics,jdk.CodeCacheFull compiler.jfr
jfr print --events jdk.Compilation compiler.jfr
jfr print --events jdk.CodeCacheStatistics,jdk.CodeCacheFull compiler.jfr
~~~

- **summary** xác nhận Start, Duration, event types, **Count** và kích thước event records (**Size**).
- **metadata** cho biết type name, category và field schema thật.
- **print** hiển thị instances với timestamp, duration và các field.
- **--events** giới hạn loại event muốn in; không cần in toàn bộ file lớn.

Một event có **Count=0** có nghĩa file không chứa event instances đó; không có nghĩa hoạt động chưa xảy ra trong thực tế. Kiểm tra recording settings và thời điểm thu.

**Size trong jfr summary là kích thước dữ liệu event đã serialize trong recording**, không phải code cache dùng bao nhiêu byte; muốn đo byte của code cache phải xem output Compiler.codecache hoặc field memory tương ứng trong JFR.

### 5.1. Đọc trực tiếp schema của type

~~~bash
jfr metadata --events jdk.Compilation compiler.jfr
jfr metadata --events jdk.CodeCacheStatistics compiler.jfr
jfr metadata --events jdk.CodeCacheFull compiler.jfr
~~~

Đặc biệt kiểm tra field, đơn vị, category và type có hỗ trợ trên JDK đang ghi. Nếu bỏ tham số file, **jfr metadata** mô tả các type của **JDK đang chạy công cụ jfr**, có thể khác schema trong recording được gửi từ một JVM khác.

### 5.2. Kiểm tra effective settings

Với JVM đang ghi JFR:

~~~bash
jcmd <PID> JFR.check verbose=true
~~~

Lệnh này hiển thị thông tin recording cùng settings (khi có hỗ trợ). Cần đối chiếu **jdk.Compilation enabled/threshold**, **jdk.CompilerPhase threshold**, **jdk.CodeCacheStatistics period**, và tên recording. Các profile **default.jfc** và **profile.jfc** là bộ cấu hình hữu ích, nhưng không mặc định mọi event đều bật hoặc threshold=0.

Nếu dùng **jcmd JFR.start**, theo tài liệu JDK 21 có thể đặt các event settings theo dạng **eventName#setting=value** khi cần. Tuy nhiên mỗi thay đổi threshold có chi phí ghi dữ liệu; chỉ chọn mức phù hợp với thời gian và phạm vi incident.

### 5.3. Correlation theo thời gian

Một quy trình nhất quán:

1. Ghi **timestamp**, timezone, PID/JVM instance và workload.
2. Lấy **jcmd Compiler.queue**, **Compiler.codecache** ở các mốc T0/T1/T2.
3. Xác nhận file JFR phủ cùng mốc T0–T2 và chính JVM đó.
4. Xem **CompilerStatistics/Compilation** quanh khoảng queue tăng.
5. Xem **CodeCacheStatistics/CodeCacheFull/JITRestart** quanh khoảng free giảm hoặc code cache full.
6. Đối chiếu **CPU load**, CPU throttling và response latency ở cùng timestamp.
7. Chỉ kết luận nguyên nhân khi dữ liệu gợi cùng một chuỗi hợp lý và phép đo lặp lại xác nhận.

### Một ví dụ minh họa

~~~text
09:10:00  deploy; application load tăng
09:10:08  Compiler.queue: nhiều tasks đang chờ
09:10:10  JFR: nhiều Compilation events, thời gian compile đáng kể
09:10:15  Compiler.queue: gần rỗng, code cache used tăng
09:10:35  request latency giảm khi workload ổn định
~~~

Mô hình này *phù hợp với warm-up JIT* nhưng **chưa chứng minh** nó là nguyên nhân duy nhất. Nếu cùng thời điểm CPU bị cgroup throttling, GC pause hoặc database latency tăng, cần phân tích thêm.

## 6. Quy trình chẩn đoán theo tình huống

### 6.1. CPU cao ngay sau khi khởi động

1. Kiểm tra compiler queue nhiều lần trong giai đoạn warm-up; xem nó rút dần hay tăng mãi.
2. Xem Compilation events/JFR stats và CPU của compiler threads nếu có.
3. Xem CPU application, request throughput, GC và code cache usage.
4. Nếu CPU tăng thoáng qua rồi ổn định, đó có thể là chi phí JIT bình thường. Nếu queue liên tục phình và throughput giảm, điều tra **CPU resources**, class/method churn, code generation, compiler flags và warm-up strategy.

Không giả định “CPU cao sau deploy” đương nhiên là JIT; có thể còn startup I/O, dependency injection, cache warmup, GC hoặc khởi tạo connection.

### 6.2. Độ trễ tăng sau thời gian dài chạy ổn định

1. Chụp **Compiler.codecache** và kiểm tra từng code heap.
2. Xem trong JFR có **CodeCacheFull** hoặc thay đổi **CodeCacheStatistics** không.
3. Tìm **JITRestart**, code sweeper activity, compiler queue và Compilation events trước/sau mốc trễ.
4. Kiểm tra deoptimization/class redefinition hoặc workload mới khiến code cần compile lại.
5. Tránh kết luận code cache gây lỗi nếu không có mối tương quan. Heap/GC/lock contention/I/O cũng có thể gây triệu chứng tương tự.

### 6.3. Queue rỗng nhưng ứng dụng chậm

Queue rỗng chỉ nói không có compile tasks đang chờ ở thời điểm snapshot. Ứng dụng vẫn có thể chậm vì I/O, lock, GC, CPU throttling, code kém tối ưu, deoptimization, hoặc JIT compilation bị tắt và không enqueue thêm tasks.

Kiểm tra thêm **compiler status**, codecache, JFR CodeCacheFull/Compilation events, CPU/JFR ExecutionSample và ứng dụng metrics. Không dùng **queue empty** như bằng chứng “JIT khỏe” hoặc “không có bottleneck”.

### 6.4. Code cache rất đầy nhưng không có CodeCacheFull event

Khả năng là chưa từng có allocation failure, có sweeper giải phóng code, recording trượt sự cố, event disabled hoặc code heap chỉ gần ngưỡng. Xem **ảnh chụp theo nhiều thời điểm**, free của từng code heap, event settings và warnings của JVM.

“Đầy 90%” không phải một ngưỡng lỗi vạn năng. Hãy đặt vấn đề dựa trên tốc độ tăng, loại code heap, hoạt động sweeper, reserved size và business impact.

### 6.5. Compiler event count tăng nhưng code cache used giảm

Không mâu thuẫn. Mã mới có thể được compile trong khi mã cũ bị reclaim bởi code sweeper; mã sau deoptimization hoặc replacement cũng có vòng đời riêng. Compilation count không phải số lượng code blobs còn sống. Xem **CodeCacheStatistics**, **CodeSweeperStatistics**, codelist nếu cần và tương quan thời gian.

## 7. So sánh nhanh ba công cụ

| Tiêu chí | Compiler.queue | Compiler.codecache | JFR compilation/code-cache events |
| --- | --- | --- | --- |
| Kiểu dữ liệu | Snapshot hiện tại | Snapshot hiện tại | Timeline nhiều event |
| Đối tượng | Compile tasks đang chờ | Các code heaps và mã đã lưu | Attempts, stats, failures, code-cache events |
| Có tên method | Có thể có | Thường không đủ chi tiết; dùng codelist | Có thể ở jdk.Compilation |
| Có compile duration | Không | Không | Có ở duration events nếu thu |
| Biết tình trạng thiếu code cache | Không trực tiếp | Dấu hiệu free/used/bounds | CodeCacheFull và Statistics |
| Biết lịch sử trước mốc hiện tại | Không | max_used có thể gợi đỉnh; không có timeline đầy đủ | Có, trong khoảng recording |
| Kết luận CPU nguyên nhân | Không đủ | Không đủ | Cần tương quan với CPU/latency metrics |
| Dùng khi nào | Hỏi “đang chờ gì?” | Hỏi “còn chỗ cho code không?” | Hỏi “điều gì đã diễn ra và khi nào?” |

## 8. Java 17+ thực hành: tạo workload có thể kích hoạt JIT

Ví dụ sau liên tục gọi một phương thức xử lý số học. Nó không cần phụ thuộc ngoài JDK, in các mốc xác định và giữ JVM chạy để bạn lấy snapshot bằng jcmd. **Không đảm bảo phương thức chắc chắn compile ở tier cụ thể hay queue không rỗng**: quyết định JIT phụ thuộc flags, JVM, CPU, thời điểm và optimization.

Tạo file **JitCompilerProbe.java**:

~~~java
public final class JitCompilerProbe {
    private static volatile long result;

    private static long compute(long seed) {
        long value = seed;
        for (int i = 0; i < 120; i++) {
            value = (value * 1_664_525L + 1_013_904_223L)
                    ^ (value >>> 11);
        }
        return value;
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("START: prepare to inspect JIT");
        Thread.sleep(5_000L);

        System.out.println("WORK: running repeated methods");
        for (int pass = 0; pass < 40; pass++) {
            for (int i = 0; i < 20_000; i++) {
                result ^= compute(i + pass);
            }
            Thread.sleep(100L);
        }

        System.out.println("END: workload finished");
        Thread.sleep(20_000L);
    }
}
~~~

Biên dịch bằng **JDK 17+**:

~~~bash
javac JitCompilerProbe.java
~~~

Chạy với JFR profile trên HotSpot. Trong một shell thông thường, đặt toàn bộ tùy chọn StartFlightRecording trong dấu ngoặc kép để ký tự **#** của event setting được chuyển nguyên vẹn:

~~~bash
java "-XX:StartFlightRecording=filename=jit-compiler-demo.jfr,settings=profile,dumponexit=true,jdk.Compilation#enabled=true,jdk.Compilation#threshold=0ms" JitCompilerProbe
~~~

Chương trình có thời gian ngủ trước/sau workload để có thể chạy jcmd từ terminal thứ hai. **Output của chính chương trình** theo đúng thứ tự, bỏ qua thông điệp JVM có thể tự in lúc bắt đầu JFR:

~~~text
START: prepare to inspect JIT
WORK: running repeated methods
END: workload finished
~~~

**Không in result** vì giá trị đó không phải mục tiêu đo, nhưng biến volatile khiến kết quả tính toán có tác động quan sát được và giúp tránh tối ưu bỏ toàn bộ phép tính. Đừng giả định số Compilation events hay dung lượng code cache sẽ giống nhau trên mọi máy.

### 8.1. Terminal thứ hai: xem queue và cache trong lúc JVM còn chạy

~~~bash
jcmd -l
jcmd <PID> Compiler.queue
jcmd <PID> Compiler.codecache
jcmd <PID> JFR.check verbose=true
~~~

Lặp riêng **Compiler.queue** vài lần khi chương trình đang in WORK; queue có thể rỗng giữa các đợt rất ngắn. Nếu được, ghi timestamp cho từng snapshot.

**Câu hỏi cần quan sát**: có queued tasks không, nhóm code heap nào tăng used, mức free của từng segment thế nào, recording có bật jdk.Compilation theo threshold yêu cầu không.

### 8.2. Sau khi chương trình tự thoát: xem file JFR

~~~bash
jfr summary jit-compiler-demo.jfr
jfr metadata --events jdk.Compilation,jdk.CompilerStatistics,jdk.CodeCacheStatistics,jdk.CodeCacheFull jit-compiler-demo.jfr
jfr print --events jdk.Compilation jit-compiler-demo.jfr
jfr print --events jdk.CodeCacheStatistics,jdk.CodeCacheFull jit-compiler-demo.jfr
~~~

Không có stdout cố định cho những lệnh này, do JVM có thể compile các method thư viện bên cạnh method **JitCompilerProbe.compute**, số events phụ thuộc workload và JFR settings, và thời gian hiện tại khác nhau. Phần profile có thể không bật tất cả event types nêu trong bảng; **summary** xác nhận file thực sự chứa những gì.

**Nếu không thấy compilation**: kiểm tra JFR file có phủ thời gian WORK không, đúng JVM hay không, event type được hỗ trợ không, event settings có hiệu lực không, và liệu JVM có đang chạy interpreter-only (**-Xint**), AOT/special mode hoặc code cache JIT bị ảnh hưởng không. Không tự suy đoán một nguyên nhân từ một file trống.

### 8.3. Một lần thử tùy chọn về log compiler

Trong môi trường **demo**, có thể chạy với:

~~~bash
java -XX:+PrintCompilation JitCompilerProbe
~~~

JVM sẽ in log compile tasks vào stdout/stderr ngoài ba dòng của chương trình, cho phép đối chiếu compile IDs, levels và method names với quan sát JFR. Tập log nhiều hay ít phụ thuộc runtime, và nó **không phải một phiên bản thay thế của JFR**. Không bật PrintCompilation tràn lan trên production vì log có thể rất lớn; nên kiểm chứng trên môi trường có kiểm soát.

## 9. Đọc JFR bằng cách nối compileId và timeline

Một ví dụ giả định (không phải output thực tế):

~~~text
T0: jdk.Compilation
    compileId = 150
    compiler = C2
    method = app.Parser::parse
    compileLevel = 4
    duration = 125 ms

T1: jdk.CompilerPhase
    compileId = 150
    phase = ... optimization ...
    duration = 80 ms

T2: jdk.CodeCacheStatistics
    code heap = non-profiled nmethods
    unallocated/free có xu hướng giảm
~~~

Cách đọc:

1. **Compilation** cho biết attempt của method parse mất khoảng 125 ms theo event.
2. **CompilerPhase** cùng compileId có thể giải thích pha nào tốn thời gian, nếu recording thực sự bật/ghi pha đó.
3. **CodeCacheStatistics** cho thấy trạng thái code heap ở một mốc. Nó không bắt buộc có event cho từng nmethod cụ thể, nên không suy “125 ms compilation đã tiêu đúng X bytes của cache” nếu không có dữ liệu field/đối chiếu đủ mức.
4. Ghép cùng **CPU load/latency** mới đánh giá tác động end-to-end.

**Không nhầm compileLevel=4 luôn tương đương mọi JDK/vendor “tối ưu thành công”.** Trong HotSpot tiered compilation phổ biến, level 4 thường tương ứng C2 optimized, nhưng phải xem compiler và success status trong schema thực tế.

## 10. Khi nghi code cache full: bằng chứng nào đủ mạnh?

Giả sử JFR có các sự kiện CodeCacheFull, rồi CodeCacheStatistics báo vùng non-profiled gần hết unallocated capacity, và latency tăng khi JVM dùng ít compiled methods mới hơn.

Đó là **chuỗi bằng chứng đáng điều tra**. Muốn khẳng định code cache là nguyên nhân chính, tiếp tục:

- Xem **Compiler.codecache** từng segment và thời điểm.
- Xem warning/logs liên quan code cache/JIT stopped, **JITRestart**, code sweeper statistics nếu có.
- Xác minh request latency/CPU thay đổi **cùng khoảng** và không bị GC/IO/network giải thích tốt hơn.
- Đối chiếu cấu hình **ReservedCodeCacheSize**, segmented code heap sizes và workload có tăng class/method generation không.
- Chạy thí nghiệm có kiểm soát về cache sizing hoặc workload rồi đo lại.

**Thao tác giải quyết phải dựa trên nguyên nhân**: ví dụ ứng dụng tạo class/method động không giới hạn nên cần quản lý lifecycle/code generation; hoặc code heap sizing không phù hợp với số method thường xuyên cần compiled code. Chỉ tăng giới hạn có thể trì hoãn triệu chứng nếu demand tiếp tục tăng không giới hạn.

## 11. Bẫy suy luận thường gặp

1. **“Compiler.queue đang rỗng nên không có JIT activity.”** Sai: queue có thể xử lý rất nhanh; compilation đã hoàn tất sẽ biến mất khỏi snapshot.
2. **“Queue dài một lần là JVM bị treo.”** Sai: có thể là warm-up hợp lệ. Cần xu hướng nhiều mốc.
3. **“Compiler.codecache used là Java heap used.”** Sai: code cache chứa mã máy và runtime code, không phải objects trong heap.
4. **“ReservedCodeCacheSize là RAM vật lý đang tiêu thụ.”** Sai: reserve, commit và resident là đại lượng khác nhau.
5. **“Tổng free nhiều thì mọi segment còn đủ chỗ.”** Sai nếu segmented code cache có một segment gần đầy.
6. **“JFR Compilation duration là request latency.”** Sai: duration đo compiler attempt; phải tương quan với request và CPU.
7. **“Mỗi compilation event ứng với một method duy nhất.”** Sai: cùng method có thể compile ở nhiều tier và nhiều lần.
8. **“JFR Count=0 chứng minh chưa có compile.”** Sai: có thể event disabled, threshold lọc, recording không phủ giai đoạn hoặc data thiếu.
9. **“CodeCacheFull event vắng mặt nghĩa là cache khỏe.”** Sai: kiểm tra settings, coverage, codecache snapshots.
10. **“CompilerPhase luôn có tất cả phases.”** Sai: event có thể bị tắt/lọc theo threshold, và schema/implementation thay đổi.
11. **“CompilerStatistics compileCount là số compile chỉ trong recording.”** Có thể sai vì counter tích lũy; cần đọc schema và so **delta**.
12. **“Code cache gần đầy là bằng chứng memory leak.”** Sai: compiled code có lifecycle, sweeper reclaim; cần xem nhu cầu code và thời gian.
13. **“Tăng code cache size luôn làm CPU nhanh hơn.”** Sai: còn phụ thuộc workload, memory pressure, tiered compilation và hiệu quả tối ưu; cần thử nghiệm.
14. **“JIT compile chậm chắc chắn tiêu thụ CPU của request thread.”** Sai: compiler threads thường riêng; tranh CPU tổng hệ thống vẫn có thể ảnh hưởng, đặc biệt trong container giới hạn CPU.
15. **“Compile ID có thể gộp trực tiếp từ nhiều JVM.”** Sai: ID chỉ có ý nghĩa trong đúng bối cảnh VM/session.
16. **“Dùng jcmd với PID bất kỳ hay container PID host là tương đương.”** Sai: đúng namespace/quyền attach mới trả dữ liệu của JVM bạn định chẩn đoán.
17. **“Có method trong codelist là method đó đang chạy.”** Sai: codelist nói về mã compiled tồn tại, không phải CPU sampling.
18. **“PrintCompilation cho kết quả lịch sử giống JFR.”** Sai: đó là compiler log; JFR có event metadata, timestamps và timeline riêng.

## 12. Bài tập tự kiểm tra

**Câu 1.** Một JVM mới khởi động, Compiler.queue thấy 30 tasks, sau 10 giây queue rỗng, CodeCache.used tăng và latency giảm. Giả thuyết hợp lý?  
**Đáp án:** warm-up JIT đang hoàn thành. Cần đối chiếu JFR Compilation events, CPU và traffic để xác thực; chưa kết luận là vấn đề cần sửa.

**Câu 2.** CodeHeap profiled còn 3 MB free, non-profiled còn 90 MB free. Có được nói “code cache còn 93 MB nên không có rủi ro” không?  
**Đáp án:** không. Code heaps có giới hạn độc lập; cần xem loại heap nào đang cần allocation và code cache full events.

**Câu 3.** JFR summary cho jdk.Compilation Count=0 nhưng Compiler.codecache used đã lên 60 MB. Mâu thuẫn không?  
**Đáp án:** không. Mã có thể đã được compile trước recording, event disabled hoặc bị threshold lọc. Summary không mô tả lịch sử ngoài file.

**Câu 4.** Một method xuất hiện ba lần trong JFR Compilation với compile IDs và levels khác nhau. Có nghĩa ứng dụng có ba method Java khác tên?  
**Đáp án:** không. Có thể cùng method được compile nhiều lần qua tier, OSR hoặc compile lại.

**Câu 5.** CodeCacheFull xảy ra cùng thời điểm latency tăng. Đã đủ chứng minh causality chưa?  
**Đáp án:** chưa. Đây là tương quan mạnh; cần xem JIT status, compiler queue, CPU/GC/I/O, hiệu quả code cache sweeping và thí nghiệm đối chiếu.

**Câu 6.** Muốn biết một compiler task **đang chờ** thì dùng gì? Muốn biết **đã compile bao lâu** thì dùng gì? Muốn biết **code cache còn bao nhiêu** thì dùng gì?  
**Đáp án:** Compiler.queue; JFR jdk.Compilation duration; Compiler.codecache/JFR CodeCacheStatistics.

**Câu 7.** CodeCacheStatistics báo free giảm rồi tăng trở lại nhưng Compilation Count vẫn tăng. Có sai số liệu không?  
**Đáp án:** không nhất thiết; code sweeper có thể reclaim code cũ trong lúc compiler tạo code mới.

**Câu 8.** JFR CompilerPhase có cùng compileId với một event Compilation nhưng không có đủ các pha. Cần kiểm tra gì?  
**Đáp án:** settings/threshold/event coverage và schema; đừng giả định file ghi toàn bộ các pha internal.

## 13. Tài liệu tra cứu

- [Oracle JDK 21 — jcmd: Compiler.queue, Compiler.codecache, Compiler.codelist, JFR.check](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — java launcher: ReservedCodeCacheSize, SegmentedCodeCache, code-heap size flags, PrintCompilation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Oracle JDK 21 — jfr command: summary, metadata, print](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle JDK 21 — jdk.jfr package: event settings and thresholds](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [Oracle Java Mission Control — JFR Event Constants: compiler/cache event type names](https://docs.oracle.com/javacomponents/jmc/api/flightrecorder/constant-values.html)
- [OpenJDK JFR event metadata definitions](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/jfr/metadata/metadata.xml) — tra theo **tag phiên bản JDK thực tế** để tránh khác schema.
