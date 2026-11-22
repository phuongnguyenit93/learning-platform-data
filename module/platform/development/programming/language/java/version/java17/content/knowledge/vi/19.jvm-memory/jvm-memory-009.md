# Đo trên tải thực tế trước khi thay tham số JVM trong Java 17

## 1. Vì sao không nên chỉnh JVM theo cảm tính?

Khi ứng dụng Java chậm, dùng nhiều RAM hoặc thường xuyên chạy garbage collection (GC), phản ứng quen thuộc là tăng `-Xmx`, đổi garbage collector hoặc thêm nhiều cờ `-XX`. Tuy nhiên, một tham số JVM chỉ tác động đến một phần của hệ thống. Tăng heap có thể làm giảm số lần GC nhưng cũng làm tăng lượng bộ nhớ được phép sử dụng và có thể khiến pause dài hơn. Đổi collector có thể cải thiện latency trong một workload nhưng làm throughput hoặc mức tiêu thụ CPU thay đổi.

Không có một bộ tham số tối ưu cho mọi ứng dụng. Kết quả phụ thuộc vào:

- Loại workload: request/response, batch, streaming, xử lý ảnh, tính toán số hay tác vụ nền.
- Phân bố tải: đều, theo đợt, burst, giờ cao điểm hoặc nhiều tenant.
- Kích thước và vòng đời object: nhiều object ngắn hạn, object sống lâu, cache lớn hay mảng lớn.
- CPU, RAM, ổ đĩa, mạng và giới hạn container.
- Phiên bản JDK, garbage collector, framework, thư viện native và cấu hình triển khai.

**Nguyên tắc:** đo một baseline bằng workload đại diện trước, xác định nút thắt có bằng chứng, thay một yếu tố có mục tiêu rồi đo lại trong điều kiện tương đương. Không thay tham số chỉ vì một bài viết, một máy khác hoặc một lần chạy đơn lẻ cho kết quả có vẻ tốt.

Sau bài học, người học cần:

1. Xây dựng workload kiểm thử gần với tải thật.
2. Thu thập latency, throughput, CPU, heap, GC, thread và native memory.
3. Dùng JFR, unified GC logging, JMX và công cụ chẩn đoán JDK 17.
4. Phân biệt heap pressure với áp lực bộ nhớ ngoài heap hoặc giới hạn container.
5. Xác định khi nào cần thay tham số JVM và khi nào cần sửa ứng dụng.
6. Thiết kế phép thử có baseline, tiêu chí chấp nhận, khả năng lặp lại và phương án quay lui.

## 2. Đo cái gì trước khi chỉnh JVM?

Một báo cáo hiệu năng không nên chỉ có một con số RAM hoặc một ảnh chụp CPU. Cần quan sát nhiều tín hiệu cùng lúc để hiểu hệ thống đang bị giới hạn ở đâu.

### 2.1. Latency và throughput

Hai nhóm chỉ số chính của ứng dụng:

- **Latency:** thời gian hoàn thành một thao tác hoặc request.
- **Throughput:** số thao tác hoàn thành trong một đơn vị thời gian, ví dụ requests/second hoặc records/second.

Đừng chỉ báo cáo latency trung bình. Một hệ thống có average tốt nhưng một nhóm request bị chậm nghiêm trọng vẫn có thể gây trải nghiệm kém. Nên đo:

| Chỉ số | Ý nghĩa |
|---|---|
| p50 | 50% thao tác hoàn thành trong thời gian này hoặc nhanh hơn |
| p90 | 90% thao tác hoàn thành trong thời gian này hoặc nhanh hơn |
| p95 | 95% thao tác hoàn thành trong thời gian này hoặc nhanh hơn |
| p99 | 99% thao tác hoàn thành trong thời gian này hoặc nhanh hơn |
| max | Thời gian lớn nhất quan sát được; nhạy với outlier |
| Throughput | Số thao tác hoàn thành trong một khoảng thời gian |
| Error rate | Tỷ lệ request/thao tác thất bại |

Đặt tiêu chí trước khi chạy, chẳng hạn p95 dưới một ngưỡng, p99 không vượt ngưỡng khác, throughput đạt mức yêu cầu và error rate không tăng. Các ngưỡng phải xuất phát từ SLA/SLO hoặc yêu cầu nghiệp vụ của hệ thống, không lấy một con số chung cho mọi dự án.

### 2.2. CPU và mức độ bão hòa

Theo dõi:

- CPU utilization của tiến trình JVM và container/host.
- Số core CPU thực tế được cấp.
- Thời gian thread chạy, chờ, block hoặc bị scheduler trì hoãn.
- Tỷ lệ CPU user/system và các tiến trình khác cạnh tranh tài nguyên.

CPU cao có thể do tính toán nghiệp vụ, allocation quá nhiều, GC, serialization, logging hoặc lock contention. CPU thấp nhưng latency cao thường gợi ý chờ I/O, lock, thread pool cạn hoặc phụ thuộc dịch vụ bên ngoài. Không thể kết luận nguyên nhân chỉ từ phần trăm CPU.

Trong container, hãy phân biệt số CPU của host với quota CPU được cấp cho container. JVM hiện đại nhận biết giới hạn container, nhưng cấu hình deployment, quota và giới hạn thực tế vẫn cần được đo và xác nhận.

### 2.3. Heap: không chỉ nhìn Xmx

Các thông tin cần theo dõi:

- Heap đã commit và heap đã sử dụng.
- Heap occupancy sau các chu kỳ GC.
- Mức tăng heap trong một khoảng thời gian.
- Allocation rate: lượng object được cấp phát trên mỗi giây.
- Live set: phần object còn sống sau khi GC thu hồi các object không còn reachable.
- Tần suất và thời gian của các lần GC.

`-Xmx` là giới hạn trên của Java heap, không phải tổng RAM mà tiến trình JVM có thể sử dụng. Heap còn phải chia sẻ giới hạn bộ nhớ với metaspace, code cache, thread stack, direct buffer, cấu trúc native của JVM, thư viện native và các vùng nhớ khác.

Nếu heap tăng mạnh trong lúc tải tăng rồi giảm sau GC, đó có thể là allocation bình thường. Nếu mức heap sau GC liên tục tăng qua các chu kỳ tương đương, cần điều tra object sống lâu, cache, listener, ThreadLocal hoặc tham chiếu bị giữ ngoài ý muốn.

### 2.4. GC: pause, tần suất và lượng công việc

Không chỉ đếm số lần GC. Hãy xem:

- Số lần young/minor collection và old/mixed/full collection.
- Thời gian pause của từng loại và tổng thời gian dừng.
- Tỷ lệ thời gian ứng dụng bị dừng vì GC.
- Heap trước và sau mỗi chu kỳ.
- Allocation rate và tốc độ thu hồi.
- Concurrent GC có cạnh tranh CPU với ứng dụng không.
- Có Full GC bất thường, evacuation failure hoặc allocation failure không.

Một lần GC kéo dài không tự động có nghĩa phải đổi collector. Có thể nguyên nhân là heap quá nhỏ, live set quá lớn, allocation burst, object graph lớn, CPU thiếu hoặc ứng dụng giữ tham chiếu không cần thiết.

### 2.5. Bộ nhớ ngoài heap và tài nguyên tiến trình

Nếu container bị OOM hoặc RSS tăng trong khi heap vẫn thấp, hãy xem xét:

- Metaspace: metadata của class.
- Compressed class space.
- Code cache chứa mã JIT đã biên dịch.
- Thread stack: số thread và kích thước stack mỗi thread.
- Direct byte buffer và các vùng native memory.
- Thư viện native/JNI.
- Bộ nhớ do hệ điều hành và các mapping của tiến trình quản lý.

Các dấu hiệu lỗi khác nhau:

| Dấu hiệu | Vùng cần điều tra trước |
|---|---|
| `OutOfMemoryError: Java heap space` | Heap, live set, allocation, object retention |
| `OutOfMemoryError: Metaspace` | Số class được nạp, class loader leak, metadata |
| `OutOfMemoryError: Direct buffer memory` | Direct buffer, pool, vòng đời buffer và giới hạn direct memory |
| `unable to create native thread` | Số thread, giới hạn PID/thread, stack và native memory |
| Container bị OOMKilled nhưng JVM không ném OOME | Tổng RSS/container memory, native memory, giới hạn cgroup |

Không tăng `-Xmx` để sửa mọi loại OOM. Nếu nguyên nhân là native memory hoặc số thread, tăng heap có thể làm tình hình tệ hơn vì heap chiếm thêm phần ngân sách RAM còn lại.

## 3. Tạo workload đại diện

Chất lượng phép đo phụ thuộc trước hết vào workload. Một benchmark nhỏ chỉ tạo vài object hoặc gọi một method trong vòng lặp không thể đại diện cho một hệ thống production nhiều request, nhiều dữ liệu và nhiều phụ thuộc.

### 3.1. Lấy workload từ hành vi thực tế

Mô tả các đặc trưng quan trọng:

- Tỷ lệ đọc/ghi, loại endpoint hoặc loại job.
- Kích thước request, response và bản ghi.
- Phân bố dữ liệu: phổ biến, hiếm, payload nhỏ/lớn.
- Tỷ lệ cache hit/miss.
- Số kết nối đồng thời.
- Tỷ lệ tác vụ CPU-bound và I/O-bound.
- Thời điểm burst, batch window và giờ cao điểm.
- Các dependency bên ngoài như database, cache, queue, HTTP service.

Nếu có production telemetry, dùng số liệu đã được ẩn danh hoặc tổng hợp để xây dựng workload kiểm thử. Không sao chép dữ liệu nhạy cảm hoặc thông tin cá nhân sang môi trường thử nghiệm khi không có cơ sở phù hợp.

### 3.2. Tải cần có nhiều pha

Một phép thử hữu ích thường gồm:

1. **Warm-up:** khởi động ứng dụng, nạp class, JIT compile và làm nóng cache.
2. **Ramp-up:** tăng tải dần tới mức mục tiêu.
3. **Steady state:** giữ tải ổn định đủ lâu để quan sát GC và memory behavior.
4. **Peak/burst:** kiểm tra khả năng chịu đỉnh nếu production có burst.
5. **Soak:** chạy đủ lâu để phát hiện tăng bộ nhớ, thread hoặc resource theo thời gian.
6. **Cool-down:** giảm tải và quan sát tài nguyên được giải phóng ra sao.

Không lấy thời gian startup hoặc vài giây đầu làm đại diện cho throughput ổn định. JIT, class loading, connection pool và cache có thể khiến hành vi ban đầu khác đáng kể.

### 3.3. Dùng load generator độc lập

Nếu load generator chạy cùng máy hoặc cùng container với JVM đang đo, nó cạnh tranh CPU, RAM, network và I/O. Kết quả có thể phản ánh sự tranh chấp giữa ứng dụng và công cụ tạo tải thay vì năng lực ứng dụng.

Khi có thể, chạy load generator ở máy/container riêng. Đồng bộ đồng hồ, ghi lại cấu hình, giữ tải theo kịch bản xác định và theo dõi cả generator để chắc chắn chính nó không trở thành bottleneck.

### 3.4. Kiểm tra cả tải thấp và tải cao

Tải thấp giúp phát hiện overhead cố định và latency cơ bản. Tải cao giúp bộc lộ saturation, queueing, GC pressure và contention. Chỉ đo ở một mức tải có thể bỏ sót hành vi quan trọng.

Không tăng tải tới mức vượt xa mọi giới hạn chỉ để tạo ra OOM rồi kết luận cấu hình không tốt. Hãy định nghĩa mức tải hợp lệ, mức đỉnh dự kiến và mức thử sức chịu tải riêng.

## 4. Baseline: ghi lại điều kiện trước khi thay đổi

Trước khi chỉnh bất kỳ tham số JVM nào, lưu lại một baseline có thể lặp lại.

### 4.1. Ghi cấu hình runtime

Thu thập:

- Phiên bản và bản phân phối JDK.
- Lệnh khởi chạy đầy đủ và toàn bộ JVM flags.
- GC đang sử dụng.
- Heap min/max, container memory limit và CPU quota.
- Hệ điều hành, kernel, kiến trúc CPU và số core được cấp.
- Phiên bản ứng dụng, framework, dependency và cấu hình ứng dụng.
- Các biến môi trường có ảnh hưởng tới runtime.

Có thể kiểm tra phiên bản:

~~~bash
java -version
~~~

Với tiến trình đang chạy, dùng `jcmd` để xem flags và thông tin VM:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> VM.command_line
~~~

`<pid>` là process ID của JVM cần quan sát. Không đưa thông tin bí mật trong command line hoặc environment vào báo cáo công khai.

### 4.2. Ghi cấu hình tài nguyên

Ví dụ một deployment container cần ghi:

| Hạng mục | Giá trị cần lưu |
|---|---|
| Memory limit | Giới hạn RAM của container |
| CPU quota/limit | Số CPU hoặc quota thực tế |
| JVM heap | `-Xms`, `-Xmx` hoặc phần trăm RAM |
| Thread count | Số thread tại steady state và peak |
| Direct memory | Giới hạn và mức sử dụng nếu ứng dụng dùng NIO/direct buffer |
| Replica count | Số instance cùng chia sẻ hạ tầng |
| Load profile | Request/s, concurrency, payload distribution |

Một phép thử trên máy 16 GB RAM không thể so trực tiếp với container giới hạn 2 GB nếu không tính đến sự khác biệt tài nguyên.

### 4.3. Lưu kết quả có thể so sánh

Mỗi lần chạy nên có một mã thử nghiệm và lưu:

- Git commit/build version.
- JVM flags.
- Workload và seed dữ liệu nếu có.
- Thời gian warm-up, ramp-up, steady state và soak.
- p50/p95/p99, throughput, error rate.
- CPU, heap, GC, thread, native memory.
- Log, JFR recording và ghi chú sự kiện bất thường.

Nếu thay nhiều yếu tố cùng lúc, rất khó biết yếu tố nào tạo ra khác biệt.

## 5. Dùng Java Flight Recorder để quan sát ứng dụng

Java Flight Recorder (JFR) là công cụ ghi sự kiện của JVM và ứng dụng, có sẵn trong JDK 17. JFR có thể cung cấp dữ liệu về GC, allocation, thread scheduling, lock contention, I/O, class loading và nhiều sự kiện runtime khác.

### 5.1. Bắt đầu recording từ command line

Có thể khởi động ứng dụng với recording:

~~~bash
java -XX:StartFlightRecording=filename=baseline.jfr,settings=profile,dumponexit=true -jar app.jar
~~~

`settings=profile` là cấu hình ghi profile có nhiều sự kiện hữu ích hơn cấu hình mặc định nhẹ. Recording có thể tăng overhead và tạo file lớn hơn; hãy đo tác động trong môi trường phù hợp.

### 5.2. Bắt đầu recording cho tiến trình đang chạy

Với JVM đã khởi động, dùng `jcmd`:

~~~bash
jcmd <pid> JFR.start name=baseline settings=profile duration=120s filename=baseline.jfr
~~~

Có thể kiểm tra recording:

~~~bash
jcmd <pid> JFR.check
~~~

Hoặc dump một recording đang chạy:

~~~bash
jcmd <pid> JFR.dump name=baseline filename=baseline.jfr
~~~

Các lệnh cụ thể và tùy chọn phụ thuộc phiên bản JDK; dùng `jcmd <pid> help JFR.start` trên đúng runtime để xem cú pháp được hỗ trợ.

### 5.3. Đọc JFR

Mở file `.jfr` bằng Java Mission Control (JMC) tương thích. Tập trung vào:

- **Garbage Collections:** thời điểm, loại GC, pause và heap occupancy.
- **Allocation in new TLAB / outside TLAB:** nơi phát sinh allocation.
- **Object statistics:** lớp nào tạo nhiều object hoặc chiếm nhiều bộ nhớ.
- **Thread activity:** thread đang chạy, chờ, blocked hoặc park.
- **Lock instances/contention:** monitor hoặc lock gây tranh chấp.
- **Socket/File I/O:** thao tác I/O kéo dài.
- **CPU samples:** stack nào sử dụng CPU nhiều.

JFR giúp đặt câu hỏi đúng hơn. Ví dụ, nếu allocation rate cao, hãy tìm call stack tạo object nhiều; nếu p99 tăng cùng GC pause, kiểm tra correlation giữa request latency và sự kiện GC; nếu CPU thấp nhưng thread blocked, điều tra lock hoặc dependency I/O.

### 5.4. Không bật mọi sự kiện ở mức cao một cách tùy tiện

JFR có nhiều mức cấu hình và sự kiện. Recording quá chi tiết trong thời gian dài có thể tăng overhead, dung lượng file và dữ liệu cần phân tích. Bắt đầu với profile phù hợp, chọn khoảng thời gian đại diện, rồi chỉ bật thêm sự kiện khi có giả thuyết cụ thể.

## 6. GC logging bằng Unified Logging

Java 9+ dùng unified logging. Trong Java 17, cấu hình GC log bằng `-Xlog` thay vì dựa vào các tùy chọn logging GC cũ.

### 6.1. Bật log GC

Ví dụ:

~~~bash
java -Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

Giải thích:

- `gc*` ghi nhóm sự kiện GC và các tag liên quan.
- `safepoint` ghi thông tin safepoint.
- `file=logs/gc.log` ghi ra file.
- `time,uptime,level,tags` thêm timestamp, uptime, level và tag.
- `filecount=5` giữ tối đa năm file log luân phiên.
- `filesize=20M` giới hạn kích thước mỗi file khoảng 20 MB.

Đường dẫn log cần tồn tại hoặc có quyền ghi phù hợp. Với container, cần xác định nơi lưu log và cơ chế thu thập để tránh lấp đầy filesystem.

### 6.2. Chọn mức chi tiết

Để quan sát ngắn gọn hơn:

~~~bash
-Xlog:gc:file=logs/gc.log:time,uptime,level,tags
~~~

Để điều tra sâu hơn, có thể bật các tag cụ thể như `gc+heap` hoặc `gc+ergo`. Đừng bật log chi tiết hơn mức cần thiết trong mọi môi trường mà không tính chi phí I/O và dung lượng.

### 6.3. Đọc các tín hiệu trong GC log

Hãy đối chiếu:

- Thời điểm GC với p95/p99 latency.
- Heap trước/sau collection.
- Tần suất young collection.
- Có old/mixed/full collection hay không.
- Pause time và thời gian concurrent phase.
- Có dấu hiệu allocation failure hoặc evacuation failure không.

Một log GC không thể tự kết luận object nào đang giữ heap. Nếu nghi ngờ leak, kết hợp heap dump, JFR allocation/object statistics và phân tích reference path.

## 7. Dùng jcmd và các công cụ chẩn đoán JDK

`jcmd` là công cụ đa năng để gửi diagnostic command tới JVM. Dùng đúng PID và runtime tương ứng.

### 7.1. Liệt kê command hỗ trợ

~~~bash
jcmd <pid> help
~~~

Xem trợ giúp của một command:

~~~bash
jcmd <pid> help GC.heap_info
~~~

### 7.2. Thông tin heap

~~~bash
jcmd <pid> GC.heap_info
~~~

Lệnh cung cấp thông tin tổng quan heap và collector theo runtime. Dùng nó để quan sát trạng thái tại một thời điểm; cần nhiều mẫu theo thời gian để thấy xu hướng.

### 7.3. Thread dump

~~~bash
jcmd <pid> Thread.print
~~~

Thread dump giúp phát hiện thread bị block, deadlock, pool cạn hoặc chờ I/O. Một dump đơn lẻ chỉ là snapshot; khi điều tra deadlock hoặc lock contention, có thể lấy nhiều dump cách nhau một khoảng thời gian để so sánh stack.

### 7.4. Class histogram

~~~bash
jcmd <pid> GC.class_histogram
~~~

Histogram cho biết số lượng instance và tổng dung lượng ước tính theo class. Đây là công cụ chẩn đoán có thể gây tác động đáng kể, tùy kích thước heap và tùy chọn runtime. Không chạy lặp liên tục trên production mà không đánh giá ảnh hưởng.

### 7.5. Heap dump

~~~bash
jcmd <pid> GC.heap_dump /path/to/heap.hprof
~~~

Heap dump hữu ích khi điều tra memory leak hoặc object retention. Nó có thể tốn thời gian, dung lượng đĩa và gây pause; file dump có thể chứa dữ liệu nhạy cảm trong object. Chỉ tạo khi có kế hoạch lưu trữ, bảo vệ và phân tích phù hợp.

### 7.6. jstat

`jstat` vẫn là công cụ JDK có thể dùng để quan sát thống kê GC theo chu kỳ:

~~~bash
jstat -gcutil <pid> 1000
~~~

Ví dụ lấy mẫu mỗi 1000 milliseconds. Đây là snapshot định kỳ; không thay thế GC log hoặc JFR khi cần hiểu nguyên nhân và call stack.

## 8. Native Memory Tracking và bộ nhớ ngoài heap

Nếu RSS/container memory cao trong khi Java heap không cao tương ứng, có thể bật Native Memory Tracking (NMT) để xem một phần phân bổ native memory do HotSpot quản lý.

### 8.1. Bật NMT khi JVM khởi động

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Hoặc mức chi tiết hơn:

~~~bash
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~

NMT có overhead về bộ nhớ và CPU. Không thể bật đầy đủ hồi tố cho một tiến trình đã chạy nếu JVM chưa khởi động với tùy chọn này.

### 8.2. Xem tổng quan

~~~bash
jcmd <pid> VM.native_memory summary
~~~

Để lấy baseline rồi so sánh:

~~~bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

Lặp lại snapshot ở các giai đoạn tương đương để quan sát category nào tăng. NMT có thể cung cấp thông tin về Java Heap, Class, Thread, Code, GC, Compiler và các category nội bộ khác.

### 8.3. Giới hạn của NMT

NMT theo dõi phân bổ native memory của HotSpot theo phạm vi được hỗ trợ; nó **không phải phép đo đầy đủ mọi byte RSS của tiến trình**. Native allocation từ thư viện bên thứ ba, driver hoặc thành phần ngoài phạm vi NMT có thể không được phản ánh đầy đủ.

Vì vậy hãy đối chiếu:

- NMT.
- Heap usage và GC log.
- RSS/container memory từ hệ điều hành hoặc nền tảng container.
- Direct buffer pool và các JMX metrics phù hợp.
- Thread count, stack và thư viện native nếu có.

Không cộng các category NMT một cách máy móc rồi coi kết quả bằng chính xác RSS; có thể có vùng dùng chung, reserved/committed khác nhau và phần ngoài phạm vi theo dõi.

## 9. JMX và các metric runtime

Java Management Extensions (JMX) cung cấp MBean để quan sát JVM. Một số MBean hữu ích:

| MBean/nhóm | Chỉ số cần quan sát |
|---|---|
| `java.lang:type=Memory` | Heap/non-heap usage, pending finalization count |
| `java.lang:type=MemoryPool,name=*` | Usage theo memory pool |
| `java.lang:type=GarbageCollector,name=*` | Collection count và collection time |
| `java.lang:type=Threading` | Thread count, peak thread count, daemon count |
| `java.lang:type=OperatingSystem` | CPU load và thông tin hệ điều hành mà JVM cung cấp |
| `java.nio:type=BufferPool,name=direct` | Direct buffer count, memory used, total capacity |

Tên và attribute cụ thể cần tra theo MBean của runtime đang dùng. Có thể quan sát qua JConsole, Java Mission Control hoặc hệ thống metrics tích hợp JMX phù hợp.

### 9.1. Theo dõi heap và non-heap

`MemoryMXBean` cung cấp `getHeapMemoryUsage()` và `getNonHeapMemoryUsage()`. Đây là dữ liệu tổng quan, không thay thế việc phân tích từng memory pool.

### 9.2. Theo dõi collector

`GarbageCollectorMXBean` cung cấp collection count và collection time tích lũy. Chênh lệch giữa hai snapshot giúp ước tính hoạt động GC trong khoảng đo.

Collection time từ MBean không nhất thiết tương đương tổng wall-clock time bị người dùng cảm nhận là pause, đặc biệt với collector có concurrent phase. Dùng GC log/JFR để hiểu chi tiết hơn.

### 9.3. Bảo vệ endpoint quản trị

Không mở JMX remote không xác thực ra mạng công cộng. Nếu bật remote management, cấu hình authentication, TLS, firewall và quyền truy cập phù hợp. JMX có thể phơi bày thông tin nhạy cảm và một số thao tác quản trị có tác động lớn.

## 10. Đọc kết quả để xác định nút thắt

Một chỉ số đơn lẻ hiếm khi đủ. Hãy tìm mối liên hệ giữa các metric.

### 10.1. Heap tăng nhanh, GC thường xuyên, pause ảnh hưởng latency

Các khả năng:

- Allocation rate cao.
- Heap quá nhỏ so với live set và allocation burst.
- Nhiều object trung gian từ serialization, mapping hoặc logging.
- Cache hoặc object graph giữ lại quá nhiều dữ liệu.

Hướng điều tra:

1. Dùng JFR xem allocation theo class/call stack.
2. Đối chiếu heap trước/sau GC và GC pause.
3. Xác định live set sau collection.
4. Nếu live set hợp lý nhưng heap quá chật, thử tăng heap trong giới hạn container.
5. Nếu object bị giữ ngoài ý muốn, sửa retention trước khi tăng heap.

### 10.2. Heap sau GC tăng dần qua các chu kỳ tương đương

Đây có thể là dấu hiệu memory leak hoặc cache tăng không giới hạn, nhưng cần loại trừ workload thay đổi và warm-up.

Hướng điều tra:

- Chạy soak test với workload ổn định.
- So sánh heap occupancy sau GC ở các thời điểm tương đương.
- Dùng heap dump ở hai thời điểm để so sánh dominator tree và retained size.
- Kiểm tra static collection, cache, listener, ThreadLocal, executor queue và class loader.

Không kết luận leak chỉ từ việc heap trước GC tăng; object ngắn hạn có thể được thu hồi ở chu kỳ tiếp theo.

### 10.3. Heap thấp nhưng RSS cao

Điều tra non-heap/native memory:

- NMT nếu được bật.
- Direct buffer pool.
- Số lượng thread và stack.
- Metaspace/class loading.
- JNI hoặc thư viện native.
- Memory mapping và giới hạn container.

Tăng `-Xmx` có thể làm giảm headroom cho những vùng này. Hãy xác định nguồn memory trước.

### 10.4. CPU cao nhưng GC không đáng kể

Có thể ứng dụng đang bị giới hạn bởi:

- Thuật toán tốn CPU.
- Serialization/compression/encryption.
- Regex hoặc xử lý chuỗi.
- Lock contention và retry loop.
- Logging hoặc chuyển đổi dữ liệu quá nhiều.

Dùng JFR CPU samples hoặc profiler phù hợp để tìm hot method. Thay GC flag không giải quyết một vòng lặp tính toán đắt đỏ.

### 10.5. CPU thấp nhưng latency cao

Điều tra:

- Thread blocked/waiting/parked.
- Database, HTTP, file I/O.
- Connection pool hoặc thread pool cạn.
- Lock contention.
- Queueing và backpressure.
- Timeout/retry giữa các dịch vụ.

JFR, thread dump và metrics của dependency thường hữu ích hơn việc thay heap size.

### 10.6. Pause GC ngắn nhưng p99 vẫn cao

Latency p99 có thể bị chi phối bởi request chờ I/O, lock, scheduler hoặc dependency chậm. Đối chiếu timestamp của request với GC event, JFR thread events và tracing. Đừng mặc định mọi spike latency đều do GC.

## 11. Thay tham số JVM có kiểm soát

Khi đã có giả thuyết và dữ liệu baseline, mới thử thay đổi. Mỗi thay đổi phải gắn với một mục tiêu có thể đo.

### 11.1. Thay một yếu tố mỗi lần

Ví dụ:

| Thử nghiệm | Thay đổi | Giả thuyết cần kiểm chứng |
|---|---|---|
| A | Tăng `-Xmx` trong giới hạn RAM | Heap quá nhỏ làm GC quá thường xuyên |
| B | Điều chỉnh `-Xms` | Heap resize/commit behavior ảnh hưởng startup hoặc latency |
| C | Đổi GC | Collector hiện tại không đáp ứng latency/throughput mục tiêu |
| D | Điều chỉnh thread stack | Quá nhiều thread khiến native memory bị áp lực |
| E | Điều chỉnh direct memory | Ứng dụng dùng direct buffer và gặp giới hạn tương ứng |

Không đổi A, B, C và D cùng lúc rồi kết luận nguyên nhân. Nếu nhiều thay đổi là bắt buộc, tách thành các thử nghiệm riêng hoặc dùng thiết kế thí nghiệm có thể phân tích tác động.

### 11.2. Bắt đầu từ heap sizing có cơ sở

`-Xms` đặt heap ban đầu/tối thiểu theo cách JVM quản lý heap; `-Xmx` đặt giới hạn heap tối đa.

Ví dụ:

~~~bash
java -Xms512m -Xmx2g -jar app.jar
~~~

Không chọn hai giá trị này chỉ từ RAM host. Với container, tổng ngân sách còn phải dành cho non-heap, native memory, thread stack và các tiến trình khác trong container.

Có thể dùng `-XX:MaxRAMPercentage` để JVM tính giới hạn heap theo lượng RAM khả dụng mà runtime nhận diện:

~~~bash
java -XX:MaxRAMPercentage=60 -jar app.jar
~~~

Con số 60 chỉ là ví dụ, không phải khuyến nghị mặc định. Xác minh JVM đang nhận đúng container memory limit và dành đủ headroom cho các vùng ngoài heap. Dùng `jcmd <pid> VM.flags` và metrics runtime để kiểm tra cấu hình thực tế.

### 11.3. Không tăng heap để che memory leak

Nếu live set tiếp tục tăng do tham chiếu bị giữ, tăng `-Xmx` chỉ trì hoãn thời điểm hết bộ nhớ. Có thể tạm giảm áp lực trong khi điều tra, nhưng giải pháp phải xử lý nguyên nhân retention hoặc đặt giới hạn cache/queue phù hợp.

### 11.4. Không đổi collector khi chưa biết bottleneck

G1 là lựa chọn mặc định phổ biến trên cấu hình server-class trong Java 17. ZGC là collector production có trong JDK 17 và có thể phù hợp với mục tiêu pause latency thấp; lựa chọn còn phụ thuộc phân phối JDK, cấu hình, heap và workload.

Không có collector nào luôn tốt hơn. Khi thử collector khác:

1. Giữ workload, tài nguyên và các tham số khác như baseline.
2. Đo throughput, p95/p99, CPU, GC pause và memory overhead.
3. Chạy đủ lâu qua steady state và soak.
4. Kiểm tra phiên bản/distribution có hỗ trợ collector và tính năng cần dùng.

Không dùng các cờ GC đã bị loại bỏ như `-XX:+UseConcMarkSweepGC` trên Java 17. Không quay lại tuning dựa trên PermGen; class metadata hiện được quản lý trong Metaspace.

### 11.5. Thận trọng với metaspace, direct memory và thread stack

Các tham số như `-XX:MaxMetaspaceSize`, `-XX:MaxDirectMemorySize` và `-Xss` ảnh hưởng những vùng khác nhau. Chỉ thay khi đã đo đúng vùng:

- Giảm `-Xss` có thể giảm native stack footprint mỗi thread, nhưng stack quá nhỏ có thể gây `StackOverflowError`.
- Giới hạn metaspace quá thấp có thể gây `OutOfMemoryError: Metaspace` khi ứng dụng nạp nhiều class hoặc có class loader leak.
- Giới hạn direct memory quá thấp có thể gây `OutOfMemoryError: Direct buffer memory`.

Không chỉnh các tham số này để giải quyết một triệu chứng heap nếu chưa có bằng chứng liên quan.

## 12. Container và giới hạn bộ nhớ

Trong môi trường container, cần hiểu chênh lệch giữa:

- Memory limit của container.
- Heap max mà JVM chọn.
- Heap committed/used.
- Non-heap và native memory.
- RSS của tiến trình.
- Page cache hoặc memory của tiến trình khác trong cùng container.

JDK 17 có hỗ trợ nhận diện container trên các nền tảng được hỗ trợ, nhưng vẫn phải xác minh cgroup/quota thực tế và cấu hình JVM. Một heap được đặt sát memory limit có thể khiến tiến trình bị hệ điều hành/container kill trước khi JVM có cơ hội ném Java OOME.

### 12.1. Ví dụ ngân sách bộ nhớ

Giả sử container có giới hạn 2 GiB. Không nên mặc định cấp toàn bộ 2 GiB cho heap. Một ngân sách minh họa có thể dành:

| Thành phần | Ngân sách ví dụ |
|---|---:|
| Java heap tối đa | 1.2 GiB |
| Metaspace, code cache và cấu trúc JVM | 160 MiB |
| Thread stacks | 180 MiB |
| Direct/native buffers và thư viện native | 220 MiB |
| Headroom cho dao động và overhead khác | Phần còn lại |

Đây chỉ là cách tư duy phân bổ, không phải công thức. Số thực tế phải được đo từ tiến trình và workload; một ứng dụng Netty có thể cần direct memory khác xa ứng dụng batch đơn giản.

### 12.2. Quan sát cgroup và container

Kết hợp metric từ nền tảng container/orchestrator với JMX/JFR/NMT. Ghi nhận:

- Memory working set/RSS và limit.
- CPU usage, quota throttling.
- OOMKilled/restart count.
- Heap usage và GC.
- Thread count và native memory.

Nếu JVM bị kill do container OOM, log Java có thể không có stack trace OOME. Cần xem event từ container runtime hoặc orchestrator.

## 13. Thiết kế một phép thử A/B có thể tin cậy

Một phép thử cấu hình nên có quy trình rõ ràng:

### Bước 1: Viết giả thuyết

Ví dụ: “Heap tối đa hiện tại làm G1 phải thu gom quá thường xuyên ở steady state; tăng heap trong giới hạn container sẽ giảm GC pressure mà không làm RSS vượt limit.”

Giả thuyết tốt dự đoán metric nào phải thay đổi và metric nào không được xấu đi.

### Bước 2: Ghi baseline

Chạy workload đại diện với cấu hình hiện tại. Thu p50/p95/p99, throughput, error rate, CPU, heap, GC và memory ngoài heap.

### Bước 3: Thay một tham số

Chỉ thay `-Xmx` hoặc một biến được giả thuyết đề cập. Giữ nguyên build, dataset, load profile, CPU/memory limit và các cờ khác.

### Bước 4: Lặp lại phép đo

Chạy warm-up và steady-state tương đương. Thực hiện nhiều lần để tránh kết luận từ một run bất thường. Nếu có noise từ môi trường dùng chung, ghi nhận và chạy lại.

### Bước 5: So sánh theo tiêu chí

Ví dụ bảng:

| Metric | Baseline | Candidate | Mục tiêu |
|---|---:|---:|---|
| Throughput | Ghi số đo | Ghi số đo | Không giảm ngoài ngưỡng |
| p95 latency | Ghi số đo | Ghi số đo | Không vượt SLO |
| p99 latency | Ghi số đo | Ghi số đo | Cải thiện hoặc giữ trong SLO |
| GC pause time | Ghi số đo | Ghi số đo | Giảm nếu đó là giả thuyết |
| CPU | Ghi số đo | Ghi số đo | Không tăng quá ngân sách |
| RSS | Ghi số đo | Ghi số đo | Còn headroom trong container |
| Error rate | Ghi số đo | Ghi số đo | Không tăng |

Không chỉ so giá trị trung bình; xem phân bố, biến động và các lần chạy lặp.

### Bước 6: Quyết định và giữ khả năng rollback

Chỉ giữ thay đổi nếu mục tiêu đạt được và không tạo regression quan trọng ở metric khác. Lưu cấu hình cũ, cấu hình mới và kết quả đo để có thể quay lại nhanh.

## 14. Những sai lầm phổ biến khi benchmark JVM

### 14.1. Đo quá ngắn

Một phép thử vài giây có thể chỉ đo class loading và JIT warm-up. Hãy đo qua steady state và đủ lâu để thấy GC behavior.

### 14.2. Không cố định workload

So sánh hai cấu hình với dataset, concurrency hoặc request mix khác nhau không cho kết luận nhân quả đáng tin cậy.

### 14.3. Chỉ xem heap trước GC

Heap trước GC cao không nhất thiết là leak. Quan sát occupancy sau collection và xu hướng qua nhiều chu kỳ.

### 14.4. Chỉ xem CPU hoặc RAM

CPU thấp không có nghĩa ứng dụng khỏe; thread có thể đang chờ. Heap thấp không có nghĩa RSS thấp; native memory có thể tăng.

### 14.5. Bật profiler quá nặng trong phép đo cuối

Profiler hoặc log quá chi tiết có thể làm thay đổi workload. Dùng instrumentation phù hợp, đo overhead và giữ cùng cách quan sát giữa baseline và candidate.

### 14.6. Chạy load generator cùng máy mà không tính tài nguyên

Load generator cạnh tranh CPU/RAM với JVM. Tách riêng hoặc theo dõi mức sử dụng của nó.

### 14.7. Thay nhiều cờ cùng lúc

Khi throughput thay đổi, không biết cờ nào gây ra. Thử một biến mỗi lần hoặc dùng thiết kế thí nghiệm có thể phân tích.

### 14.8. Tối ưu một metric làm hỏng metric khác

Giảm GC pause nhưng tăng CPU hoặc memory quá mức có thể không phù hợp. Tối ưu theo SLO và ngân sách tổng thể, không theo một con số đơn lẻ.

### 14.9. Dựa vào tuning flag cũ

Tài liệu hoặc script cũ có thể chứa flag đã deprecated/removed. Kiểm tra với đúng JDK 17:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Và tra JDK 17 documentation. Không sao chép flag của PermGen, CMS hoặc một collector không còn hỗ trợ.

## 15. Checklist trước và sau khi thay tham số

**Trước khi thay:**

- [ ] Workload đại diện và có thể lặp lại.
- [ ] Đã có baseline latency, throughput và error rate.
- [ ] Đã ghi CPU, heap, GC, thread, native memory và container limit.
- [ ] Có giả thuyết gắn với một bottleneck cụ thể.
- [ ] Đã ghi JDK version, flags và build version.
- [ ] Đã chọn tiêu chí chấp nhận và giới hạn rollback.

**Sau khi thay:**

- [ ] Chỉ thay yếu tố đã định trong thử nghiệm.
- [ ] Warm-up và steady-state tương đương baseline.
- [ ] So sánh p95/p99, throughput, error rate.
- [ ] So sánh GC, heap, CPU và RSS/native memory.
- [ ] Chạy đủ lâu để quan sát xu hướng và soak behavior.
- [ ] Ghi lại kết quả, cấu hình và quyết định giữ/rollback.

## 16. Ví dụ kịch bản thu thập dữ liệu trên Java 17

Một lần chạy có thể khởi động ứng dụng với GC logging và JFR:

~~~bash
java \
  -Xms512m \
  -Xmx1536m \
  -Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -XX:StartFlightRecording=filename=logs/baseline.jfr,settings=profile,dumponexit=true \
  -jar app.jar
~~~

Các giá trị heap chỉ là cấu hình minh họa. Trong một thử nghiệm thật, dùng cấu hình đang được đánh giá và giữ nguyên các yếu tố khác giữa baseline/candidate.

Trong lúc chạy, ghi metrics ứng dụng (request rate, latency percentile, error rate), CPU và container memory. Nếu cần quan sát tiến trình:

~~~bash
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
jcmd <pid> Thread.print
jcmd <pid> JFR.check
~~~

Nếu đã bật NMT từ đầu:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

Sau khi kết thúc:

1. Lưu GC log, JFR recording và metric timeline.
2. Ghi lại thời điểm warm-up, steady-state, peak và soak.
3. Đối chiếu spike latency với GC, thread và I/O events.
4. Xác định một bottleneck có bằng chứng.
5. Đề xuất một thay đổi nhỏ, đo lại rồi so sánh.

## 17. Bài tập thực hành

### Bài 1 — Lập baseline

Chọn một ứng dụng Java 17. Xác định ba endpoint hoặc job chính, tỷ lệ tải, payload size và mức concurrency. Tạo bảng ghi p50/p95/p99, throughput, error rate, CPU, heap và GC ở steady state.

### Bài 2 — Phân biệt heap pressure và native pressure

Một container bị OOMKilled trong khi heap usage cao nhất chỉ bằng một nửa `-Xmx`. Hãy liệt kê vùng cần kiểm tra: metaspace, direct buffer, thread stack, JNI/native library, RSS và cgroup limit. Giải thích vì sao tăng heap có thể làm vấn đề nghiêm trọng hơn.

### Bài 3 — Đọc GC log

Bật `-Xlog:gc*` cho workload ổn định. Ghi lại số lần young/mixed/full GC, pause duration, heap trước/sau collection và tỷ lệ thời gian pause. So sánh với p99 latency theo timestamp.

### Bài 4 — Dùng JFR tìm allocation

Ghi một JFR profile trong steady state. Xác định ba class hoặc call stack tạo nhiều allocation. Đề xuất cách kiểm tra xem allocation đó là cần thiết, object trung gian có thể tránh hay cache có thể giới hạn.

### Bài 5 — Thử một thay đổi

Đặt giả thuyết heap hiện tại quá nhỏ. Chạy baseline, tăng `-Xmx` trong giới hạn container, giữ nguyên workload và các tham số khác. So sánh GC pause, throughput, p99, CPU và RSS. Viết quyết định giữ hoặc rollback kèm số liệu.

### Bài 6 — Điều tra p99 cao nhưng GC ít

Dùng JFR hoặc thread dump để tìm thread blocked/parked, lock contention và I/O chậm. Giải thích vì sao đổi garbage collector có thể không cải thiện tình huống này.

### Bài 7 — Thiết kế soak test

Chạy workload cố định đủ lâu. So sánh heap occupancy sau GC, thread count, metaspace và RSS qua các khoảng thời gian. Xác định tín hiệu nào có thể gợi ý leak và cần heap dump/NMT/JFR nào để điều tra tiếp.

## 18. Tiêu chí hoàn thành

Người học hoàn thành bài khi có thể:

1. Giải thích vì sao phải đo workload thực tế trước khi thay JVM flags.
2. Thiết kế warm-up, ramp-up, steady-state, peak và soak test.
3. Thu thập latency percentile, throughput, error rate, CPU, heap, GC và native memory.
4. Dùng JFR và unified GC logging trên Java 17.
5. Dùng jcmd, jstat, JMX và NMT đúng phạm vi.
6. Phân biệt Java heap với tổng memory/RSS của tiến trình và container.
7. Nhận diện khi nào vấn đề nằm ở allocation, live set, native memory, thread, I/O hoặc CPU.
8. Viết giả thuyết và thay một tham số có kiểm soát.
9. So sánh baseline/candidate theo cùng workload và tiêu chí chấp nhận.
10. Tránh tuning flag legacy và có khả năng rollback nếu thay đổi gây regression.

## 19. Tài liệu chính thức

- [Java SE 17 Troubleshooting Guide — JFR](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): các công cụ chẩn đoán và ghi dữ liệu runtime.
- [Java SE 17 JFR Runtime Guide](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-configurations.html): cấu hình và sử dụng Flight Recorder.
- [Java SE 17 Troubleshooting — GC Logging](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-collector-implementation.html): thông tin GC và cơ chế thu thập log.
- [Java SE 17 man page — java](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): JVM options và unified logging.
- [Java SE 17 man page — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): diagnostic commands.
- [Java SE 17 man page — jstat](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): thống kê JVM.
- [Java SE 17 Troubleshooting — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html): phạm vi và cách sử dụng NMT.
- [Java SE 17 Management Extensions Guide](https://docs.oracle.com/en/java/javase/17/management/): JMX và các management interface.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): Flight Recorder trong JDK.
**Ghi nhớ:** JVM tuning là một bài toán thực nghiệm. Workload phải đại diện, baseline phải đo được và phép thử phải kiểm soát. Chỉ thay tham số khi dữ liệu chỉ ra bottleneck phù hợp; đánh giá đồng thời latency, throughput, CPU, heap, GC và tổng bộ nhớ để không cải thiện một chỉ số bằng cách làm hỏng phần còn lại.
