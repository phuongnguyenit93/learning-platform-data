Câu 1. Khi cần liệt kê các diagnostic command mà một tiến trình HotSpot hỗ trợ, lệnh nào phù hợp?
A. Dùng `javap <pid> help` để liệt kê command chẩn đoán.
B. Dùng `jstat <pid> help` để liệt kê command attach.
C. Dùng `jcmd <pid> help` để liệt kê command của JVM.
D. Dùng `jfr <pid> help` để liệt kê command HotSpot.
Đáp án đúng: C

Câu 2. Khi cần thu thread dump trực tiếp bằng `jcmd`, command nào phù hợp?
A. Dùng `jcmd <pid> VM.flags` để lấy thread dump.
B. Dùng `jcmd <pid> GC.heap_info` để lấy thread dump.
C. Dùng `jcmd <pid> JFR.check` để lấy thread dump.
D. Dùng `jcmd <pid> Thread.print` để lấy thread dump.
Đáp án đúng: D

Câu 3. Một Java process dùng CPU cao trên Linux; cách liên hệ thread OS với Java stack nào hợp lý?
A. Lấy TID nóng bằng `top -H`, đối chiếu `nid` dạng hex trong dump.
B. Lấy PID cha từ `ps`, đối chiếu với Java object ID của mọi thread.
C. Lấy số lượng GC root rồi đối chiếu trực tiếp với thread native.
D. Lấy thread name từ heap dump rồi quy về CPU core đang chạy.
Đáp án đúng: A

Câu 4. Trong thread dump, trạng thái `BLOCKED` thường biểu thị tình huống nào?
A. Thread đang chờ giành monitor lock trước khi vào block đồng bộ.
B. Thread đang xử lý bytecode và tiêu thụ CPU liên tục.
C. Thread đang chờ `LockSupport.park` để nhận tín hiệu.
D. Thread đang ngủ trong `Thread.sleep` theo thời hạn.
Đáp án đúng: A

Câu 5. Một thread ở trạng thái `WAITING` tại `LockSupport.park` cho biết điều gì?
A. Thread đang chiếm CPU ở vòng lặp không có điều kiện dừng.
B. Thread đang sở hữu toàn bộ monitor mà JVM đang cấp phát.
C. Thread đang được JVM biên dịch bằng C2 compiler.
D. Thread chờ tín hiệu, không chứng minh đang tốn CPU.
Đáp án đúng: D

Câu 6. Hai thread giữ hai monitor khác nhau rồi chờ monitor của nhau; đây là dấu hiệu gì?
A. Starvation do CPU thiếu core trong giai đoạn GC.
B. Safepoint bias do interpreter chưa hoàn thành warm-up.
C. GC thrashing do tần suất tạo object tăng mạnh.
D. Deadlock do mỗi thread chờ lock mà thread kia giữ.
Đáp án đúng: D

Câu 7. Vì sao nên lấy nhiều thread dump cách nhau khi điều tra một request bị treo?
A. Nhiều dump chứng minh mọi thread ở `RUNNABLE` đều dùng CPU.
B. Chuỗi dump giúp phân biệt chờ kéo dài với trạng thái thoáng qua.
C. Một dump đã lưu toàn bộ lịch sử stack của mọi thread trước đó.
D. Nhiều dump cho phép tính chính xác heap retained size từng class.
Đáp án đúng: B

Câu 8. Trong Java Management API, interface nào cung cấp số thread và thông tin deadlock?
A. `ThreadMXBean` có thread count và API kiểm tra deadlock.
B. `GarbageCollectorMXBean` tìm deadlock của `ReentrantLock`.
C. `ClassLoadingMXBean` tìm deadlock của `synchronized` blocks.
D. `MemoryMXBean` cung cấp thread count và API tìm deadlocked threads.
Đáp án đúng: A

Câu 9. Muốn lấy CPU time từng Java thread qua JMX, nên chú ý điều kiện gì?
A. Thread CPU time chỉ có thể tính bằng kích thước JVM heap dump.
B. Thread CPU time là thuộc tính có sẵn của MemoryMXBean.
C. CPU time phải được hỗ trợ và có thể cần bật thread CPU timing.
D. CPU time tương đương elapsed wall time của thread đang WAITING.
Đáp án đúng: C

Câu 10. Khi cần ảnh trạng thái object heap để điều tra retention, lệnh nào phù hợp?
A. Dùng `jcmd <pid> JFR.check <path>` để lấy heap dump.
B. Dùng `jcmd <pid> Thread.print <path>` để lấy heap dump.
C. Dùng `jcmd <pid> GC.heap_dump <path>` để lấy heap dump.
D. Dùng `jcmd <pid> VM.flags <path>` để lấy heap dump.
Đáp án đúng: C

Câu 11. Dùng `jcmd <pid> GC.class_histogram` chủ yếu để thu thông tin nào?
A. Thống kê stack trace CPU nóng qua từng instruction.
B. Thống kê mọi request HTTP theo response status code.
C. Thống kê tất cả socket đang mở và TCP state.
D. Thống kê instance count và số byte theo loại class.
Đáp án đúng: D

Câu 12. Trong phân tích heap dump, retained size của một object biểu thị gì?
A. Dung lượng heap được giải phóng nếu loại object khỏi graph tham chiếu.
B. Bộ nhớ native cấp cho mọi thread từng truy cập object.
C. Kích thước dữ liệu sau khi nén heap dump thành file ZIP.
D. Kích thước shallow của header và field riêng object đó.
Đáp án đúng: A

Câu 13. Khi suspected memory leak, dấu hiệu nào đáng ưu tiên so sánh giữa các heap dump?
A. Chênh lệch số thread JVM khi hai lần chạy garbage collection.
B. Số lệnh bytecode do verifier xử lý trước khi có leak.
C. Xem object còn reachable, retained size và chuỗi GC roots.
D. Số frame của method `main` trong mỗi thread dump.
Đáp án đúng: C

Câu 14. Muốn tự tạo heap dump khi HotSpot gặp OutOfMemoryError, cặp option nào phù hợp?
A. Dùng `-XX:+HeapDumpOnOutOfMemoryError` và `-XX:HeapDumpPath=...`.
B. Dùng `-XX:StartFlightRecording` và `-XX:NativeMemoryTracking=...`.
C. Dùng `-XX:+PrintCompilation` và `-XX:LogFile=...`.
D. Dùng `-XX:+UnlockDiagnosticVMOptions` và `-XX:ErrorFile=...`.
Đáp án đúng: A

Câu 15. Muốn bắt đầu recording JFR trên JVM đang chạy, command nào phù hợp?
A. Dùng `jcmd <pid> JFR.start name=diag settings=profile`.
B. Dùng `jcmd <pid> JFR.dump name=diag settings=profile`.
C. Dùng `jcmd <pid> VM.flags name=diag settings=profile`.
D. Dùng `jcmd <pid> JFR.check name=diag settings=profile`.
Đáp án đúng: A

Câu 16. Khi một JFR recording đang chạy, làm gì để ghi dữ liệu ra file mà không dừng recording?
A. Dùng `jcmd <pid> JFR.check name=diag filename=diag.jfr`.
B. Dùng `jcmd <pid> JFR.dump name=diag filename=diag.jfr`.
C. Dùng `jcmd <pid> GC.heap_dump name=diag filename=diag.jfr`.
D. Dùng `jcmd <pid> JFR.stop name=diag filename=diag.jfr`.
Đáp án đúng: B

Câu 17. Trong JFR, event `jdk.ExecutionSample` giúp điều tra vấn đề nào?
A. Khôi phục toàn bộ nội dung của HTTP request trước đó.
B. Ước lượng stack được lấy mẫu khi code tiêu thụ CPU.
C. Truy xuất SQL result của mọi connection JDBC đã mở.
D. Xác định retained size chính xác cho mọi object heap.
Đáp án đúng: B

Câu 18. Muốn tìm hotspot cấp phát object với JFR, nên quan sát loại bằng chứng nào?
A. Allocation events kết hợp stack trace và tốc độ cấp phát.
B. Danh sách TLS certificate kết hợp phiên bản Java bytecode.
C. Thông tin DNS cache kết hợp số class loader đang sống.
D. Thống kê HTTP status code kết hợp dung lượng file JAR.
Đáp án đúng: A

Câu 19. Để giám sát heap usage và GC qua JMX, cặp MBean nào sát mục tiêu?
A. `OperatingSystemMXBean` và `ThreadMXBean` để đọc GC logs.
B. `ClassLoadingMXBean` và `CompilationMXBean` để đo heap.
C. `MemoryMXBean` và `GarbageCollectorMXBean` tương ứng.
D. `ThreadMXBean` và `RuntimeMXBean` để đếm GC pauses.
Đáp án đúng: C

Câu 20. Muốn bật remote JMX cho production, biện pháp bảo vệ nào cần có?
A. Đưa password JMX vào query URL để tránh cấu hình TLS.
B. Bind JMX ra public interface để dashboard tự khám phá.
C. Cho mọi host truy cập cổng JMX trong mạng production.
D. Giới hạn kết nối, xác thực và bảo vệ truyền thông JMX.
Đáp án đúng: D

Câu 21. Với HotSpot JDK 11+, option nào hỗ trợ ghi GC log qua unified logging?
A. Dùng `-Xlog:jfr*:file=gc.log` để ghi unified GC events.
B. Dùng `-XX:+PrintGCDetails:file=gc.log` làm unified log.
C. Dùng `-Xlog:gc*:file=gc.log:time,uptime,level,tags`.
D. Dùng `-Xmx:gc.log` để xuất các sự kiện garbage collector.
Đáp án đúng: C

Câu 22. Khi thấy nhiều GC pause dài trùng lúc p99 latency tăng, bước xác minh nào phù hợp?
A. Xem số lượng class loader rồi quy mọi pause về metaspace.
B. Đối chiếu thời điểm GC pause với p99 latency tăng.
C. Xem số thread RUNNABLE rồi bỏ qua GC log của thời điểm lỗi.
D. Xem riêng giá trị Xmx rồi suy ra toàn bộ độ trễ do GC.
Đáp án đúng: B

Câu 23. Nhật ký cho thấy young GC rất thường xuyên và allocation rate cao; hướng phân tích nào hợp lý?
A. Xem DNS TTL của JVM để giảm lượng object được cấp phát.
B. Xem permission của các file JAR để giảm số lần young GC.
C. Xem số static method để loại bỏ mọi đợt young collection.
D. Xem nguồn cấp phát, kích thước heap và tốc độ thu gom.
Đáp án đúng: D

Câu 24. Sau các lần old/full GC, live heap vẫn tăng dần; nhận định chẩn đoán nào hợp lý?
A. Kết luận JIT inlining thất bại vì heap không giảm về bằng không.
B. Kết luận thread deadlock dù không có thread dump liên quan.
C. Kiểm tra object retention, heap dump và đường dẫn GC roots.
D. Khẳng định memory leak từ một phép đo bất kể thời gian tải.
Đáp án đúng: C

Câu 25. Muốn theo dõi thống kê GC định kỳ trên JVM đang chạy, lệnh nào phù hợp?
A. Dùng `javap -gc <pid> 1000` để lấy số liệu GC định kỳ.
B. Dùng `jlink -gc <pid> 1000` để lấy số liệu GC định kỳ.
C. Dùng `jstat -gc <pid> 1000` để lấy số liệu GC định kỳ.
D. Dùng `jdeps -gc <pid> 1000` để lấy số liệu GC định kỳ.
Đáp án đúng: C

Câu 26. Để `jcmd <pid> VM.native_memory summary` cung cấp thống kê NMT, JVM cần gì?
A. Bật verbose GC log mà không cấu hình Native Memory Tracking.
B. Bật NMT từ startup, ví dụ `-XX:NativeMemoryTracking=summary`.
C. Bật Java assertions trên từng class được nạp vào JVM.
D. Bật heap dump tự động mỗi khi class loader bị unload.
Đáp án đúng: B

Câu 27. RSS của JVM lớn hơn nhiều so với heap used; cách hiểu nào hợp lý?
A. RSS chỉ tăng do đối tượng trong young generation chưa thu gom.
B. RSS gồm cả native stacks, code cache và vùng ngoài heap.
C. RSS chỉ phản ánh live object heap vừa qua full GC.
D. RSS theo định nghĩa phải bằng heap used tại cùng thời điểm đo.
Đáp án đúng: B

Câu 28. Khi nghi ngờ rò rỉ `DirectByteBuffer`, bộ bằng chứng nào hữu ích?
A. Phân tích stack trace thread rồi tính trực tiếp retained bytes.
B. Đếm số class được JIT biên dịch và quy đổi ra direct memory.
C. Quan sát kích thước Metaspace rồi coi đó là direct-buffer usage.
D. Theo dõi direct buffer usage và native memory, đối chiếu heap.
Đáp án đúng: D

Câu 29. CPU process thấp nhưng request latency cao, thread dump hay chờ I/O; hướng điều tra nào phù hợp?
A. Đo độ trễ DB/network, timeout và tình trạng bão hòa.
B. Tắt thread dump vì trạng thái WAITING chứng minh app khỏe.
C. Giảm heap tối đa để buộc garbage collector chạy nhiều hơn.
D. Tăng số compiler threads để đẩy nhanh việc nhận HTTP response.
Đáp án đúng: A

Câu 30. Request treo khi connection pool JDBC đã đầy, bằng chứng nào hữu ích nhất?
A. Quan sát class loading count mà bỏ qua pool metrics.
B. Xem pool active/idle/pending cùng stack chờ connection.
C. Quan sát dung lượng JAR trên đĩa thay vì pool acquisition timeout.
D. Quan sát số JIT compilation và tăng code cache của JVM.
Đáp án đúng: B

Câu 31. Khi lấy heap dump ở production trong sự cố, điều gì cần cân nhắc trước?
A. Heap dump tự xóa object leak khỏi heap khi tạo file xong.
B. Cân nhắc pause, dung lượng và dữ liệu nhạy cảm trong dump.
C. Heap dump thay thế JFR nên không cần các số liệu runtime khác.
D. Heap dump không tác động JVM và không chứa thông tin nhạy cảm.
Đáp án đúng: B

Câu 32. Để kết luận nguyên nhân CPU tăng sau deployment, cách thu thập bằng chứng nào vững?
A. So sánh giá trị Xmx rồi kết luận JIT gây nghẽn CPU.
B. Đếm số file log trong container thay cho profiler.
C. Dựa vào một thread dump rồi quy CPU tăng về deployment.
D. Đối chiếu CPU, JFR, GC, thread sample với mốc deploy.
Đáp án đúng: D
