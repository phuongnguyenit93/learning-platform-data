# jcmd, JFR và phân tích CPU, cấp phát, I/O, khóa

*Tình trạng được đối chiếu với Oracle JDK 26 tại ngày 27/11/2026.*

Khi một ứng dụng Java chậm, tăng CPU, phản hồi thất thường hoặc dùng bộ nhớ ngày càng nhiều, cần tìm bằng chứng ở đúng tầng trước khi thay đổi JVM flags hay viết lại code. Bộ công cụ chẩn đoán tích hợp của JDK gồm:

- **jcmd**: gửi lệnh chẩn đoán đến JVM đang chạy để xem flags, heap, thread, class loading và điều khiển recording.
- **Java Flight Recorder (JFR)**: thu thập sự kiện runtime có timestamp, stack trace và thời lượng với overhead thấp.
- **jfr**: đọc, lọc, tổng hợp và kiểm tra file recording .jfr từ command line.
- **JDK Mission Control (JMC)**: giao diện phân tích recording theo CPU, memory, thread, lock, I/O và GC.

Bài học tập trung vào quy trình thực tế để xác định bottleneck CPU, allocation, I/O và lock contention bằng các công cụ còn được hỗ trợ trong JDK 26. jcmd, JFR và jfr là công cụ chuẩn của JDK; JFR không phải preview hay incubator. JMC là công cụ riêng, cần cài đặt độc lập và không nằm trong bộ cài JDK thông thường.

## 1. Chọn đúng công cụ cho từng câu hỏi

| Câu hỏi cần trả lời | Công cụ nên bắt đầu | Bằng chứng cần tìm |
|---|---|---|
| JVM đang chạy bản nào, với flags gì? | jcmd VM.version, VM.command_line, VM.flags | JDK build, heap size, GC và cấu hình runtime |
| Thread đang chạy hay bị block? | jcmd Thread.print -l, JFR | Stack trace, monitor owner, park/sleep và thời lượng chờ |
| Code nào tiêu thụ CPU? | JFR profile, JMC | Execution samples, hot methods, call tree |
| Thread/class nào cấp phát nhiều object? | JFR allocation events, JMC | Allocation rate, class, thread và allocation stack |
| Ứng dụng chờ file hay mạng ở đâu? | JFR I/O events | File/socket, bytes và thời gian chờ |
| Có lock contention hay không? | JFR monitor/park events, thread dump | Lock bị tranh chấp, thread chờ và thread giữ lock |
| Heap đang tăng hay có dấu hiệu leak? | JFR, GC.class_histogram, heap dump | Class chiếm heap, object còn sống và đường tham chiếu |
| Bộ nhớ ngoài Java heap tăng? | Native Memory Tracking (NMT), OS tools | Native allocation của JVM và vùng nhớ của tiến trình |

Không có một công cụ đơn lẻ trả lời tất cả. jcmd cho ảnh chụp trạng thái tại một thời điểm; JFR cho lịch sử sự kiện trong một khoảng thời gian; JMC giúp kết nối các sự kiện với stack trace và luồng xử lý.

## 2. Tìm đúng JVM và kiểm tra trạng thái ban đầu bằng jcmd

jcmd gửi diagnostic command đến JVM đang chạy. Công cụ phải chạy trên cùng máy với JVM đích và thường cần cùng effective user/group đã khởi chạy JVM. Danh sách command khả dụng phụ thuộc JVM; luôn hỏi chính tiến trình đích thay vì giả định mọi bản JDK đều có cùng command.

Liệt kê các JVM có thể nhìn thấy:

```bash
jcmd -l
```

Lệnh này liệt kê PID và main class của các JVM mà công cụ phát hiện được. Trong container, jcmd -l không nhất thiết liệt kê JVM chạy trong một Docker process riêng; khi đó lấy PID từ namespace của container hoặc công cụ quản lý container.

Kiểm tra command khả dụng của tiến trình:

```bash
jcmd <pid> help
jcmd <pid> help JFR.start
jcmd <pid> help Thread.print
```

Lấy thông tin runtime trước khi profile:

```bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.uptime
jcmd <pid> GC.heap_info
```

Những thông tin này giúp xác nhận:

- JDK build thực tế mà ứng dụng đang chạy.
- JVM arguments và system properties liên quan.
- Heap hiện tại, giới hạn heap và GC configuration.
- Thời gian JVM đã hoạt động.
- Các lần đo có đang so sánh cùng cấu hình hay không.

Không nên thay đổi heap size, GC hoặc JIT flags trước khi lưu lại trạng thái ban đầu. Nếu thay nhiều tham số cùng lúc, sẽ khó xác định thay đổi nào tạo ra kết quả.

## 3. Thread dump bằng Thread.print

Khi ứng dụng có request treo, latency tăng hoặc thread pool không tiến triển, lấy thread dump:

```bash
jcmd <pid> Thread.print
```

Để in thêm thông tin lock thuộc java.util.concurrent:

```bash
jcmd <pid> Thread.print -l
```

Có thể lấy vài thread dump cách nhau một khoảng ngắn, ví dụ 5–10 giây, rồi so sánh stack trace. Một dump chỉ là ảnh chụp tức thời; nhiều dump giống nhau giúp nhận ra thread bị kẹt lâu ở cùng một call path.

Khi đọc thread dump, phân biệt các trạng thái thường gặp:

- **RUNNABLE**: thread đang chạy hoặc sẵn sàng chạy trong JVM; không đồng nghĩa chắc chắn đang chiếm CPU liên tục.
- **BLOCKED**: thread đang chờ lấy intrinsic monitor (synchronized).
- **WAITING**: thread đang chờ một điều kiện khác, thường không có timeout.
- **TIMED_WAITING**: thread đang chờ có timeout, ví dụ sleep() hoặc timed wait.

Các trạng thái không tự chỉ ra nguyên nhân. Hãy đọc stack trace, monitor đang chờ, lock owner và trạng thái của các thread liên quan.

Một số mẫu cần tìm:

| Dấu hiệu | Khả năng cần điều tra |
|---|---|
| Nhiều thread BLOCKED trên cùng monitor | Critical section hoặc lock bị tranh chấp |
| Nhiều thread WAITING tại Future.get() hoặc queue take | Đang chờ công việc, kết quả hoặc dữ liệu |
| Nhiều thread TIMED_WAITING tại Thread.sleep() | Delay có chủ ý, retry/backoff hoặc polling |
| Nhiều thread ở LockSupport.park() | Lock, synchronizer, executor, queue hoặc virtual-thread scheduler |
| Một thread giữ lock nhưng stack đang gọi I/O | I/O nằm bên trong critical section có thể giữ các thread khác chờ |

JDK 26 Thread.print in platform threads và các virtual threads đang mounted; có thể dùng Thread.dump_to_file để lưu dump dạng text hoặc JSON. Với ứng dụng dùng virtual threads, các lệnh Thread.vthread_scheduler và Thread.vthread_pollers cung cấp thêm thông tin về scheduler và I/O pollers. Không suy ra mọi virtual thread đều xuất hiện như một platform thread độc lập trong mọi thời điểm.

## 4. Thu recording JFR từ tiến trình đang chạy

JFR là framework thu thập sự kiện tích hợp trong JDK. Mỗi event có timestamp; event dạng duration có thời điểm bắt đầu và thời lượng, event dạng instant ghi nhận sự kiện tức thời, còn sample event lấy mẫu định kỳ.

JFR có hai cấu hình phổ biến:

| Template | Mục tiêu | Cách dùng |
|---|---|---|
| default.jfc | Ghi liên tục với overhead rất thấp | Theo dõi dài hạn và lưu lịch sử gần nhất |
| profile.jfc | Thu nhiều chi tiết hơn cho phân tích hiệu năng | Recording ngắn khi cần tìm nguyên nhân cụ thể |

Oracle ghi nhận recording profiling theo mặc định thường có overhead dưới 2% ở phần lớn ứng dụng; recording continuous với default settings thường không có ảnh hưởng hiệu năng đo được. Đây là số liệu tham khảo, không phải cam kết cho mọi workload hoặc event configuration.

Lưu ý về độ bao phủ: continuous recording dùng default.jfc không thu heap statistics hoặc allocation profiling. Nếu cần tìm allocation site, hãy thực hiện profile recording ngắn bằng profile.jfc hoặc bật rõ event allocation phù hợp. Heap Statistics bị tắt mặc định vì có thể kích hoạt old GC ở đầu và cuối recording, làm thay đổi pause và kết quả đo latency.

### Recording ngắn có thời hạn

Ví dụ ghi 3 phút bằng profile template:

```bash
jcmd <pid> JFR.start name=incident settings=profile duration=3m filename=incident.jfr
```

Khi hết thời hạn, recording dừng và ghi file theo filename. Có thể đặt delay=20s nếu muốn bỏ qua một đoạn warmup hoặc đợi đến thời điểm tái hiện sự cố:

```bash
jcmd <pid> JFR.start name=incident settings=profile delay=20s duration=3m filename=incident.jfr
```

### Recording thủ công

Nếu cần tự quyết định thời điểm kết thúc:

```bash
jcmd <pid> JFR.start name=incident settings=profile
jcmd <pid> JFR.check
jcmd <pid> JFR.stop name=incident filename=incident.jfr
```

JFR.check cho biết recording đang chạy. JFR.stop dừng recording và ghi dữ liệu ra file nếu có filename; nếu không chỉ định file, dữ liệu recording đó bị loại bỏ.

### Dump dữ liệu mà recording vẫn tiếp tục

Với recording liên tục hoặc recording đang chạy, có thể lưu snapshot hiện tại mà không dừng:

```bash
jcmd <pid> JFR.start name=continuous settings=default disk=true maxage=6h maxsize=512m
jcmd <pid> JFR.check
jcmd <pid> JFR.dump name=continuous filename=incident-snapshot.jfr
```

JFR.dump ghi dữ liệu đã thu thập ra file và recording vẫn tiếp tục. maxage và maxsize giới hạn dữ liệu giữ trên đĩa khi disk=true; chọn giới hạn theo dung lượng ổ đĩa và thời gian cần giữ lịch sử.

Không nên bật profile template trong thời gian dài mà không có lý do. Hãy bắt đầu bằng default continuous recording; khi sự cố xảy ra, dump dữ liệu hoặc thực hiện một profile recording ngắn.

## 5. Đọc file recording bằng công cụ jfr

Sau khi có file .jfr, dùng lệnh jfr trong thư mục bin của cùng JDK để xem dữ liệu.

Tổng quan recording:

```bash
jfr summary incident.jfr
```

Xem metadata và danh sách event thực sự có trong file:

```bash
jfr metadata incident.jfr
jfr view all-views incident.jfr
jfr view all-events incident.jfr
```

In event theo loại:

```bash
jfr print --events jdk.ExecutionSample incident.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait incident.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite incident.jfr
```

Lọc stack trace dài hơn mặc định:

```bash
jfr print --events jdk.ExecutionSample --stack-depth 20 incident.jfr
```

Xuất dữ liệu có cấu trúc để xử lý tiếp:

```bash
jfr print --json --events jdk.SocketRead,jdk.SocketWrite incident.jfr
```

jfr summary cho biết số lượng event và dung lượng từng nhóm. jfr metadata cho biết tên, category và field layout của event. jfr print in các event phù hợp bộ lọc; jfr view tổng hợp dữ liệu theo view có sẵn trong JDK. Tên view có thể thay đổi theo JDK, vì vậy dùng jfr view all-views để xem danh sách thực tế thay vì ghi nhớ tên view từ một phiên bản cũ.

JFR recording có thể mở trong JDK Mission Control để xem các trang Code, Memory, Threads, Locks, I/O và Automated Analysis. JMC không nằm trong cài đặt JDK tiêu chuẩn; hãy dùng bản JMC tương thích với recording/JDK đang phân tích.

## 6. Phân tích CPU: thread nào đang thực thi code?

CPU bottleneck xảy ra khi thread dành phần lớn thời gian thực thi code thay vì chờ I/O, lock hoặc scheduler. Dùng JFR profile để thu method samples và xem:

- jdk.CPULoad: mức sử dụng CPU của JVM và toàn máy theo thời gian.
- jdk.ThreadCPULoad: các thread có hoạt động CPU cao.
- jdk.ExecutionSample: stack trace lấy mẫu trong lúc thread thực thi.
- jdk.NativeMethodSample: mẫu khi thread chạy native method, nếu event được bật.

JFR lấy mẫu thread đang chạy code. Thread đang chờ I/O, ngủ hoặc chờ lock không tạo method samples trong khoảng chờ đó. Vì vậy, nhiều sample ở một method thường cho thấy method đó hoặc các method bên dưới tiêu thụ CPU; ít sample không chứng minh thread không gây latency.

Quy trình phân tích:

1. Mở recording trong JMC và xem CPU Load theo thời gian.
2. So sánh CPU của JVM với CPU toàn máy. Nếu JVM CPU thấp nhưng máy CPU cao, kiểm tra tiến trình khác bằng công cụ OS.
3. Xem Hot Methods để tìm method có nhiều execution samples.
4. Mở Call Tree và lần từ leaf method lên caller để hiểu đường gọi.
5. Phân biệt code ứng dụng với framework, serializer, logging, regex, crypto hoặc code thư viện.
6. Đối chiếu với throughput và latency của cùng khoảng thời gian.

Ví dụ lấy các execution samples:

```bash
jfr print --events jdk.ExecutionSample --stack-depth 30 incident.jfr
```

Không dùng số sample như số lần gọi method chính xác. Đây là dữ liệu lấy mẫu; độ tin cậy phụ thuộc thời gian recording, tần suất sampling và workload. Nếu sample quá ít, tăng thời gian recording hoặc dùng profile ngắn hơn vào đúng thời điểm tải cao.

### CPU cao nhưng không thấy method nóng

Có thể xảy ra khi:

- CPU bị tiêu thụ bởi native code hoặc thư viện ngoài JVM.
- Thread bị preempt hoặc container bị CPU throttling.
- Recording không có đủ sample hoặc không thu event phù hợp.
- CPU cao đến từ process khác trên máy.
- Workload bị giới hạn bởi GC, safepoint hoặc hoạt động hệ thống.

Kết hợp JFR với OS metrics như process CPU, per-thread CPU, container throttling và system load. Không tăng số worker hay thread pool trước khi biết CPU đang bị dùng ở đâu.

## 7. Phân tích allocation: object được tạo ở đâu và bởi ai?

Allocation rate cao có thể khiến GC chạy thường xuyên, tăng CPU và làm latency biến động. Hãy tách ba câu hỏi:

1. Bao nhiêu bộ nhớ được cấp phát trong một giây?
2. Class hoặc thread nào tạo nhiều object nhất?
3. Object đó có sống lâu và làm tăng live set hay chỉ là temporary allocation?

Các event hữu ích:

| JFR event | Dữ liệu cung cấp | Cách dùng |
|---|---|---|
| jdk.ObjectAllocationInNewTLAB | Allocation liên quan đến việc cấp TLAB mới | Tìm stack tạo object trong đường cấp phát TLAB |
| jdk.ObjectAllocationOutsideTLAB | Allocation ngoài TLAB | Tìm object lớn hoặc allocation không dùng TLAB |
| jdk.ObjectAllocationSample | Mẫu allocation theo stack trace | Xác định allocation site có áp lực cao |
| jdk.ThreadAllocationStatistics | Thống kê allocation theo thread | So sánh thread tạo nhiều object |

TLAB (Thread Local Allocation Buffer) là vùng nhỏ mỗi thread dùng để cấp phát object nhanh. Khi TLAB đầy, thread cần lấy buffer mới. Các event TLAB phản ánh hoạt động cấp phát ở ranh giới buffer, không phải bản ghi đầy đủ cho mọi object nhỏ được tạo. Allocation sample cũng là dữ liệu lấy mẫu; không coi số event là số object chính xác.

Trong JMC, xem TLAB Allocations theo class và thread. Tìm allocation site có tổng byte lớn, rồi kiểm tra stack trace để biết object được tạo ở đâu. Ví dụ thường gặp:

- Tạo nhiều chuỗi tạm khi ghép log hoặc format dữ liệu.
- Deserialize object lặp lại ở mỗi request.
- Tạo collection hoặc wrapper trong vòng lặp nóng.
- Copy buffer hoặc tạo byte array cho I/O.
- Chuyển đổi dữ liệu qua nhiều lớp DTO mà không cần thiết.

Nếu allocation rate cao nhưng live set ổn định, có thể vấn đề là temporary allocation chứ chưa phải memory leak. Nếu live set tăng sau mỗi chu kỳ GC, cần kiểm tra object còn được giữ tham chiếu ở đâu.

### So sánh allocation với heap histogram

Lấy histogram:

```bash
jcmd <pid> GC.class_histogram
```

Histogram cho biết số lượng và dung lượng instance theo class tại thời điểm chụp. Đây là snapshot, không cho biết class đó được tạo ở method nào hoặc tốc độ tạo ra sao. So sánh histogram ở nhiều thời điểm có thể gợi ý class tăng liên tục, nhưng cần JFR hoặc heap dump để xác định nguyên nhân.

GC.class_histogram có impact cao tùy kích thước heap và nội dung. Chạy trên production cần cân nhắc thời điểm và ảnh hưởng latency. Heap dump có impact cao hơn và có thể yêu cầu full GC; chỉ thu khi thật sự cần phân tích object graph.

## 8. Phân tích I/O: thread đang chờ file hay mạng?

JFR cung cấp event duration cho file và socket:

- jdk.FileRead
- jdk.FileWrite
- jdk.SocketRead
- jdk.SocketWrite

Các event này cho biết thời gian, số byte và thông tin file hoặc địa chỉ socket tùy event. Dùng chúng để tìm thread thường xuyên chờ đọc/ghi hoặc thao tác có thời lượng bất thường.

```bash
jfr print --events jdk.FileRead,jdk.FileWrite incident.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite incident.jfr
```

Khi phân tích:

1. Xem tổng thời gian chờ và số event của từng loại I/O.
2. Xác định thread thực hiện I/O và stack trace gọi.
3. Với socket, xem remote address/port và số byte truyền.
4. Với file, xem file path, kích thước và tần suất đọc/ghi.
5. Đối chiếu thời điểm I/O chậm với latency request và log của dịch vụ phụ thuộc.

Nếu một thread dành nhiều thời gian ở SocketRead, nguyên nhân có thể nằm ở remote service, network, connection pool hoặc giao thức chứ không phải CPU của JVM. Nếu FileWrite kéo dài, kiểm tra filesystem, storage latency, flush/fsync và lượng dữ liệu ghi.

JFR ghi các event duration vượt threshold được cấu hình. Theo cấu hình mặc định, phần lớn Java Application events chỉ ghi những lần chờ dài hơn 20 ms. Một workload có rất nhiều I/O nhanh dưới ngưỡng có thể không hiện event tương ứng. Không kết luận “không có I/O chậm” chỉ vì recording không chứa event; kiểm tra threshold và bật thu thập chi tiết hơn khi cần.

## 9. Phân tích lock contention và thread parking

Lock contention xảy ra khi nhiều thread cần cùng một tài nguyên đồng bộ và phải chờ nhau. Các event hữu ích:

| Event | Ý nghĩa | Dấu hiệu cần xem |
|---|---|---|
| jdk.JavaMonitorEnter | Thread chờ vào intrinsic monitor | Monitor class, thời lượng, previous owner, stack trace |
| jdk.JavaMonitorWait | Thread gọi Object.wait() và chờ được đánh thức | Thời gian chờ, monitor và stack trace |
| jdk.ThreadPark | Thread bị park bởi synchronizer hoặc cơ chế tương tự | Stack trace, thời lượng park và thread liên quan |
| jdk.ThreadSleep | Thread đang ngủ | Sleep duration và code gọi |

Với synchronized, xem monitor class và thread giữ lock. Với ReentrantLock, semaphore, executor hoặc queue, thread thường park qua LockSupport; xem jdk.ThreadPark và stack trace để nhận diện synchronizer. wait() và lock acquisition không phải cùng một hành vi: JavaMonitorWait phản ánh việc thread chờ điều kiện qua Object.wait(), còn JavaMonitorEnter phản ánh tranh chấp khi vào monitor.

Ví dụ in event:

```bash
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark incident.jfr
```

Cách tìm nguyên nhân:

1. Sắp xếp các event theo thời lượng, tìm lock hoặc stack trace lặp lại.
2. Xem thread đang chờ và thread sở hữu monitor nếu có.
3. Kiểm tra công việc được thực hiện trong critical section.
4. Tìm I/O, logging, serialization hoặc gọi service bên ngoài bên trong vùng giữ lock.
5. So sánh recording khi hệ thống bình thường với recording khi latency tăng.

Ví dụ một logger đồng bộ hoặc cache có một lock chung có thể làm nhiều request chờ nhau. Tối ưu không nhất thiết là đổi loại lock; có thể giảm phạm vi critical section, tránh I/O trong lock, phân vùng dữ liệu hoặc thay đổi mô hình cập nhật.

### Hạ threshold để bắt lock ngắn

Nếu nghi ngờ nhiều lần contention ngắn dưới 20 ms, có thể giảm threshold trong một recording ngắn:

```bash
jcmd <pid> JFR.start name=locks settings=profile duration=30s jdk.JavaMonitorEnter#threshold=5ms jdk.JavaMonitorWait#threshold=5ms jdk.ThreadPark#threshold=5ms
```

Threshold thấp hơn tạo nhiều event hơn, có thể tăng overhead và dung lượng recording. Bắt đầu với khoảng thời gian ngắn, theo dõi tác động lên ứng dụng rồi mới quyết định có cần mở rộng.

## 10. Phân biệt CPU, I/O, lock và GC khi latency tăng

Một request chậm có thể đến từ nhiều nguyên nhân. Dùng thời lượng event và stack trace để phân biệt:

| Quan sát trong recording | Giả thuyết cần kiểm chứng | Bước tiếp theo |
|---|---|---|
| Nhiều jdk.ExecutionSample ở cùng method | Code tiêu thụ CPU | Hot Methods, Call Tree, benchmark method |
| Nhiều jdk.SocketRead kéo dài | Remote service hoặc network chậm | Xem endpoint, connection pool, server phía bên kia |
| Nhiều jdk.FileRead/jdk.FileWrite kéo dài | Storage hoặc file operation là bottleneck | Kiểm tra filesystem, file path, flush và storage latency |
| Nhiều jdk.JavaMonitorEnter cùng monitor | Intrinsic lock contention | Xem owner, stack trace và critical section |
| Nhiều jdk.ThreadPark | Synchronizer, executor hoặc queue đang chờ | Xem stack trace và tín hiệu đánh thức |
| Allocation rate cao, GC thường xuyên | Tạo nhiều temporary object | Tìm allocation site và giảm object churn |
| Live set tăng qua các GC | Có thể có object retention/leak | So sánh heap histogram, heap dump và GC roots |
| GC pause chiếm phần lớn latency | GC ảnh hưởng request | Xem GC pause, heap pressure và allocation rate |
| JVM CPU thấp nhưng host CPU cao | Process khác hoặc OS đang bận | Dùng OS/container metrics |

Không cộng trực tiếp mọi event duration để suy ra latency request: các event có thể xảy ra song song trên nhiều thread. Muốn hiểu request cụ thể, cần liên hệ event với thread, timestamp, trace/request ID (nếu ứng dụng ghi custom JFR event hoặc có correlation data) và khoảng thời gian request đó.

## 11. Đọc GC và allocation cùng nhau

Một heap lớn không tự động đồng nghĩa có memory leak. Phân biệt:

- **Allocation rate cao**: ứng dụng tạo nhiều object trong một đơn vị thời gian.
- **Live set cao**: nhiều object còn được giữ tham chiếu sau GC.
- **Memory leak/retention**: object đáng lẽ không còn cần nhưng vẫn được giữ bởi reference chain.
- **Native memory tăng**: bộ nhớ ngoài Java heap, ví dụ thread stacks, direct buffers, metaspace hoặc native libraries.

JFR có thể hiển thị allocation, GC pause và live set. Khi cần điều tra object retention, có thể tạo heap dump:

```bash
jcmd <pid> GC.heap_dump heap.hprof
```

Heap dump là dữ liệu nhạy cảm và thao tác có impact cao. Nếu chỉ cần tìm class chiếm heap, bắt đầu bằng GC.class_histogram. Chỉ bật path-to-gc-roots trong JFR dump khi thật sự nghi memory leak vì việc thu thập đường đến GC roots có thể gây pause.

Không bật Heap Statistics trong một profile latency thông thường nếu không cần. Oracle lưu ý tính năng này có thể kích hoạt old GC ở đầu và cuối recording, làm thay đổi pause của chính phép đo.

## 12. Theo dõi native memory bằng Native Memory Tracking

JFR allocation tập trung vào object Java. Nếu RSS của tiến trình tăng nhưng heap không tăng tương ứng, cần kiểm tra native memory.

NMT phải được bật khi JVM khởi động:

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Sau khi ứng dụng đã warm up, tạo baseline:

```bash
jcmd <pid> VM.native_memory baseline
```

Sau một khoảng thời gian, lấy chênh lệch:

```bash
jcmd <pid> VM.native_memory summary.diff
```

Có thể dùng detail thay summary nếu cần stack trace chi tiết hơn, nhưng cần đánh giá overhead và dung lượng dữ liệu. NMT theo dõi các vùng cấp phát nội bộ của HotSpot; nó không theo dõi mọi allocation do native library bên ngoài JVM thực hiện. Nếu NMT không giải thích được RSS, tiếp tục dùng công cụ hệ điều hành để kiểm tra native allocator, memory map, direct buffer hoặc thư viện JNI.

## 13. JFR và jcmd trong môi trường production

Một quy trình production nên ưu tiên thu thập ít xâm lấn và tăng mức chi tiết theo giả thuyết:

1. Duy trì continuous recording với default.jfc nếu chính sách vận hành cho phép.
2. Khi incident xảy ra, lưu timestamp, PID, phiên bản JDK, JVM flags và tình trạng tải.
3. Dùng jcmd lấy VM.version, VM.command_line, VM.flags, GC.heap_info và một thread dump nếu cần.
4. Dump JFR quanh khoảng thời gian có vấn đề.
5. Nếu cần thêm dữ liệu, chạy profile recording ngắn với profile.jfc.
6. Chỉ giảm threshold hoặc bật event nặng khi đã có giả thuyết cụ thể.
7. Kiểm tra overhead, dung lượng file và ảnh hưởng lên latency.
8. Lưu recording cùng metadata về release, cấu hình, workload và thời điểm incident.

JFR có overhead thấp nhưng không miễn phí. Profile template có nhiều event hơn default template; giảm threshold làm tăng số event; heap statistics và path-to-GC-roots có thể tạo pause. Mỗi lần tăng độ chi tiết cần đo lại tác động.

Các lệnh GC.class_histogram và GC.heap_dump có impact cao. Không chạy lặp liên tục trên hệ thống nhạy latency nếu chưa đánh giá ảnh hưởng. GC.run chỉ gọi System.gc() và không phải lệnh khắc phục bottleneck; ép GC có thể làm thay đổi hiện tượng đang cần đo.

## 14. Bảo vệ recording và dữ liệu chẩn đoán

JFR có thể chứa stack trace, tên class/method, đường dẫn file, địa chỉ socket, tên thread và custom event fields do ứng dụng tự ghi. Những dữ liệu này có thể tiết lộ cấu trúc hệ thống hoặc thông tin vận hành.

Khi chia sẻ recording:

- Lưu file ở vị trí có quyền truy cập hạn chế.
- Không gửi recording chứa dữ liệu nhạy cảm qua kênh công khai.
- Kiểm tra event và custom payload trước khi chia sẻ.
- Dùng jfr scrub để lọc event, thread hoặc category khi cần giảm dữ liệu nhạy cảm.
- Giữ bản gốc trong vùng bảo mật nếu cần phục vụ điều tra nội bộ.
- Thiết lập thời hạn lưu trữ và xóa file tạm sau khi xử lý.

Ví dụ loại bỏ event không cần thiết trước khi chuyển recording cho nhóm khác:

```bash
jfr scrub --exclude-events jdk.SocketRead,jdk.SocketWrite incident.jfr incident-scrubbed.jfr
```

Scrub có thể giảm dữ liệu nhưng không thay thế việc rà soát bảo mật. Kiểm tra file đầu ra trước khi gửi.

## 15. Quy trình chẩn đoán từ đầu đến cuối

Giả sử p99 latency tăng sau một lần release:

**Bước 1 – Ghi nhận hiện tượng**

Lưu p50/p95/p99, throughput, error rate, CPU, heap, GC và thời điểm bắt đầu suy giảm. So sánh với cùng workload ở release trước.

**Bước 2 – Kiểm tra JVM**

```bash
jcmd -l
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
```

**Bước 3 – Lấy JFR profile ngắn**

```bash
jcmd <pid> JFR.start name=latency-incident settings=profile duration=3m filename=latency-incident.jfr
```

**Bước 4 – Tóm tắt và mở recording**

```bash
jfr summary latency-incident.jfr
jfr view all-views latency-incident.jfr
```

Mở file bằng JMC để xem Code, Memory, Threads, Locks và I/O.

**Bước 5 – Phân loại bottleneck**

- CPU: hot methods và execution samples.
- Allocation/GC: TLAB allocations, allocation sites, GC pauses.
- I/O: file/socket events và thời lượng chờ.
- Locks: monitor enter/wait, thread park và lock owner.
- Native memory: NMT và OS metrics nếu RSS tăng nhưng Java heap không tăng tương ứng.

**Bước 6 – Đặt một giả thuyết cụ thể**

Ví dụ: một method serializer tạo quá nhiều byte array; hoặc một cache lock khiến request thread chờ; hoặc một endpoint phụ thuộc phản hồi chậm.

**Bước 7 – Thử một thay đổi có kiểm soát**

Chỉ thay một yếu tố chính, giữ nguyên workload, dữ liệu và môi trường. Thu lại cùng loại recording để so sánh.

**Bước 8 – Xác nhận bằng chỉ số nghiệp vụ**

Một hot method giảm sample không tự chứng minh hệ thống tốt hơn. Xác nhận p99, throughput, error rate, CPU và bộ nhớ đã cải thiện mà không tạo regression ở luồng khác.

## 16. Công cụ chẩn đoán nên dùng trong JDK hiện nay

Tài liệu Oracle JDK 26 khuyến nghị dùng jcmd thay cho các utility chẩn đoán đời trước như jstack, jinfo và jmap; một số utility đó được đánh dấu experimental. Trong quy trình mới, dùng:

| Mục đích | Công cụ nên dùng |
|---|---|
| Thread dump | jcmd <pid> Thread.print |
| Heap histogram | jcmd <pid> GC.class_histogram |
| Heap dump | jcmd <pid> GC.heap_dump |
| JVM flags và command line | jcmd <pid> VM.flags, VM.command_line |
| JFR control | jcmd <pid> JFR.start/check/dump/stop |
| Đọc recording | jfr summary, jfr view, jfr print |

Không cần thêm --enable-preview, --add-modules hoặc dependency thư viện chỉ để sử dụng các công cụ này. Chúng đi kèm JDK; JMC là ứng dụng riêng để phân tích trực quan.

## 17. Checklist chẩn đoán

- [ ] Đã xác nhận PID và JDK build của JVM đích.
- [ ] Đã kiểm tra JVM arguments, heap và GC configuration.
- [ ] Đã lưu thread dump nếu có dấu hiệu block hoặc deadlock.
- [ ] Đã chọn default.jfc hay profile.jfc theo thời gian và mức chi tiết cần thiết.
- [ ] Đã ghi lại thời điểm, tải, release và triệu chứng của recording.
- [ ] Đã kiểm tra CPU bằng jdk.CPULoad, jdk.ThreadCPULoad và execution samples.
- [ ] Đã kiểm tra allocation theo class/thread và đối chiếu GC.
- [ ] Đã kiểm tra jdk.FileRead, jdk.FileWrite, jdk.SocketRead, jdk.SocketWrite.
- [ ] Đã kiểm tra monitor contention và ThreadPark.
- [ ] Đã xem threshold trước khi kết luận event không tồn tại.
- [ ] Đã cân nhắc overhead của profile, heap statistics, heap dump và GC roots.
- [ ] Đã kiểm tra NMT nếu RSS tăng nhưng Java heap không tăng tương ứng.
- [ ] Đã scrub và bảo vệ recording trước khi chia sẻ.
- [ ] Đã xác nhận cải thiện bằng latency, throughput và tài nguyên trên cùng workload.

## Tài liệu tham chiếu

1. [Oracle Java SE 26 – Diagnostic Tools](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
2. [Oracle Java SE 26 – Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
3. [Oracle Java SE 26 – jcmd Command Reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
4. [Oracle Java SE 26 – jfr Command Reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jfr.html)
5. [Oracle Java SE 26 – jdk.jfr Package API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
6. [Oracle Java SE 26 – Native Memory Tracking](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
7. [Oracle – JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html)

