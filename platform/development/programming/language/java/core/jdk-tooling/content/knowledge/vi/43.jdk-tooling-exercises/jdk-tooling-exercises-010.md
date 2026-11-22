# Profiling Java bằng Java Flight Recorder (JFR)

## Mục tiêu

Sau bài này, bạn có thể giải thích JFR và vai trò của JDK Mission Control (JMC); hiểu event, recording, template và buffer; bắt đầu/dừng recording khi khởi chạy ứng dụng hoặc khi JVM đang chạy; tạo continuous recording có giới hạn dung lượng/thời gian; đọc file .jfr bằng công cụ dòng lệnh và JMC; phân tích CPU, allocation, garbage collection, thread, lock và I/O; tạo custom JFR event trong Java; điều chỉnh event settings; xây dựng quy trình profiling có thể lặp lại; và xử lý các lỗi thường gặp khi thu thập hoặc phân tích dữ liệu.

## 1. JFR là gì?

**Java Flight Recorder (JFR)** là hệ thống thu thập sự kiện và dữ liệu chẩn đoán/profiling được tích hợp trong JVM của các JDK hiện đại. JFR ghi lại các sự kiện có timestamp về ứng dụng, JVM và môi trường chạy để developer có thể phân tích hành vi đã xảy ra.

Một recording có thể cung cấp thông tin về:

- CPU activity và stack trace của các thread đang chạy.
- Object allocation và tốc độ cấp phát bộ nhớ.
- Garbage collection, heap behavior và GC pause.
- Thread state, monitor contention, lock wait và thread park.
- File I/O, socket I/O và các khoảng chờ.
- Class loading, JIT compilation và hoạt động nội bộ của JVM.
- Custom event do ứng dụng định nghĩa để đánh dấu thao tác nghiệp vụ.

JFR phù hợp để điều tra vấn đề hiệu năng xuất hiện trong một khoảng thời gian cụ thể, kể cả khi lỗi chỉ xảy ra trong môi trường staging hoặc production và khó tái hiện trên máy developer.

### JFR không phải là bộ đếm thời gian cho từng dòng code

JFR thu thập nhiều loại event. Một số event đo duration; một số ghi lại sự kiện tức thời; một số lấy mẫu định kỳ. CPU profiling thường dựa trên thread sampling, vì vậy tỷ lệ sample giúp nhận diện vùng code tiêu tốn CPU nhưng không phải số lần gọi method chính xác.

Hãy dùng recording để hình thành giả thuyết, sau đó đối chiếu với code, metrics, logs và phép đo lặp lại. Một biểu đồ hoặc một stack trace riêng lẻ không đủ để kết luận nguyên nhân gốc.

## 2. Phân biệt JFR, JMC, jcmd và jfr

Bốn thành phần thường được dùng cùng nhau nhưng đảm nhiệm các việc khác nhau.

| Thành phần | Vai trò |
|---|---|
| JFR | Thu thập và lưu event từ JVM vào file recording |
| JDK Mission Control (JMC) | Mở, trực quan hóa và phân tích file recording; cũng có thể điều khiển JVM |
| jcmd | Gửi diagnostic command tới JVM đang chạy, ví dụ start, check, dump và stop recording |
| jfr | Công cụ dòng lệnh để đọc summary, in event, xem metadata, lọc và cấu hình recording |

JFR nằm trong JDK/JVM. JMC là ứng dụng phân tích riêng và không nằm trong cài đặt JDK thông thường; cần cài JMC tương thích với recording/JDK đang sử dụng.

JFR và JMC tạo thành một quy trình:

~~~text
Java application
       |
       v
JVM + JFR records events
       |
       v
Flight recording (.jfr)
       |
       +------> jfr CLI
       |
       +------> JDK Mission Control
                    |
                    v
            Charts / tables / stack traces
                    |
                    v
             Performance investigation
~~~

jcmd là một cách điều khiển recording trong lúc ứng dụng đang chạy. Bạn không cần sửa source code hoặc khởi động lại JVM chỉ để bắt đầu một recording runtime nếu JVM cho phép diagnostic command.

## 3. Event là đơn vị dữ liệu của JFR

Một event thường có:

- **Timestamp:** thời điểm event xảy ra.
- **Duration:** khoảng thời gian event kéo dài, nếu là duration event.
- **Thread/context:** thread hoặc ngữ cảnh liên quan.
- **Payload:** các trường dữ liệu mô tả event.
- **Stack trace:** vị trí code liên quan nếu event được cấu hình thu stack trace.

Các nhóm event chính:

| Nhóm | Cách hoạt động | Ví dụ |
|---|---|---|
| Duration event | Có thời điểm bắt đầu và kết thúc | Lock wait, file/socket I/O |
| Instant event | Ghi nhận một thời điểm | Một thao tác hoặc trạng thái JVM |
| Sample event | Thu thập theo chu kỳ | CPU/thread sample |
| Custom event | Do ứng dụng hoặc tool định nghĩa | OrderProcessed, PaymentAttempt |

JFR có sẵn nhiều event cho JVM và runtime. Ứng dụng có thể bổ sung custom event để ghi lại thời gian xử lý một request, nghiệp vụ thanh toán hoặc thao tác quan trọng.

### Event settings

Mỗi event có thể được cấu hình theo các thuộc tính như:

- enabled: bật/tắt event.
- threshold: chỉ ghi duration event khi thời gian vượt ngưỡng.
- period: chu kỳ thu thập đối với periodic event.
- stackTrace: có lưu stack trace hay không.
- throttle: giới hạn tốc độ event trong một số trường hợp.

Ví dụ, nếu chỉ quan tâm lock wait kéo dài hơn 10 ms, có thể dùng threshold để bỏ qua các lần chờ rất ngắn. Hạ threshold sẽ thu được nhiều chi tiết hơn nhưng cũng có thể làm recording lớn hơn và tăng overhead.

## 4. Recording template: default và profile

JDK cung cấp hai cấu hình JFR phổ biến trong thư mục JAVA_HOME/lib/jfr:

| Template | Mục đích | Mức dữ liệu |
|---|---|---|
| default.jfc | Continuous monitoring và chẩn đoán tổng quát | Ít event hơn, overhead thấp |
| profile.jfc | Profiling ngắn hạn để tìm bottleneck | Nhiều event hơn, overhead cao hơn |

Chọn default khi cần ghi liên tục và giữ lại một cửa sổ dữ liệu gần đây. Chọn profile khi cần nhiều thông tin hơn về method, allocation và hoạt động của ứng dụng trong một khoảng thời gian ngắn.

Không nên mặc định dùng profile cho recording liên tục dài ngày. Nhiều event hơn thường đồng nghĩa với nhiều dữ liệu hơn, file lớn hơn và tác động lớn hơn lên workload.

### Time-fixed recording

Time-fixed recording chạy trong một khoảng thời gian xác định rồi tự dừng. Đây là lựa chọn phù hợp khi:

- Muốn tái hiện một workload cụ thể.
- Đang chạy load test hoặc benchmark.
- Cần phân tích một lần latency spike.
- Muốn lấy profile ngắn trong giờ cao điểm.

### Continuous recording

Continuous recording chạy lâu dài và giữ lại một cửa sổ dữ liệu gần đây. Khi giới hạn dung lượng hoặc tuổi dữ liệu đạt đến, dữ liệu cũ được loại bỏ để giữ phần mới hơn.

Đây là lựa chọn hữu ích khi lỗi xuất hiện bất chợt và không thể biết trước lúc nào cần bắt đầu profiling. Khi incident xảy ra, dump phần recording liên quan rồi phân tích sau.

## 5. Kiểm tra JDK và công cụ trước khi profiling

Xác nhận runtime:

~~~bash
java -version
javac -version
jcmd -l
jfr --version
~~~

Các lệnh jcmd và jfr thường nằm trong thư mục bin của JDK. Hãy dùng công cụ thuộc JDK tương thích với JVM mục tiêu để tránh khác biệt version hoặc thiếu diagnostic command.

Xem trợ giúp JFR:

~~~bash
jcmd <PID> help JFR.start
jcmd <PID> help JFR.dump
jcmd <PID> help JFR.stop
jfr --help
jfr --help print
~~~

Thay PID bằng process ID thật. Không nhập dấu ngoặc nhọn vào lệnh.

jcmd cần chạy trên cùng máy với JVM và thông thường phải dùng cùng effective user/group đã khởi chạy JVM. Với process trong container, PID có thể khác PID trên host; hãy xác định PID trong đúng process namespace/container trước khi gọi jcmd.

JMC có thể tải riêng từ trang JDK Mission Control. Mở file .jfr bằng JMC sau khi recording đã được tạo.

## 6. Bắt đầu recording ngay khi khởi chạy ứng dụng

Có thể dùng JVM option -XX:StartFlightRecording để bắt đầu thu thập ngay khi ứng dụng khởi động.

Ví dụ recording 90 giây với profile template:

~~~bash
java \
  -XX:StartFlightRecording:settings=profile,duration=90s,filename=build/profile.jfr \
  -jar app.jar
~~~

Các tham số:

- settings=profile: dùng profile template.
- duration=90s: tự dừng sau 90 giây.
- filename=build/profile.jfr: lưu recording vào file chỉ định.
- -jar app.jar: khởi chạy ứng dụng.

Có thể ghi lại khi JVM kết thúc bằng dumponexit=true:

~~~bash
java \
  -XX:StartFlightRecording:settings=profile,dumponexit=true,filename=build/exit.jfr \
  -jar app.jar
~~~

Nếu không khai báo duration, recording tiếp tục chạy cho tới khi được dừng hoặc JVM kết thúc. dumponexit=true yêu cầu JVM ghi recording ra file khi shutdown.

### Chọn thời điểm bắt đầu

Có thể trì hoãn thời điểm bắt đầu:

~~~bash
java \
  -XX:StartFlightRecording:settings=profile,delay=30s,duration=60s,filename=build/delayed.jfr \
  -jar app.jar
~~~

Ví dụ này chờ 30 giây sau khi JVM khởi động rồi thu thập trong 60 giây. Cách này hữu ích nếu muốn bỏ qua startup/warmup và tập trung vào giai đoạn workload ổn định.

### Giới hạn dung lượng recording

Với recording ghi ra disk, có thể giới hạn tuổi và kích thước dữ liệu:

~~~bash
java \
  -XX:StartFlightRecording:settings=default,disk=true,maxage=6h,maxsize=512M,dumponexit=true,filename=build/continuous.jfr \
  -jar app.jar
~~~

maxage và maxsize giúp kiểm soát dữ liệu lưu trên disk. Hãy chọn giới hạn phù hợp với tốc độ phát sinh event, dung lượng ổ đĩa và thời gian cần giữ dữ liệu.

## 7. Bắt đầu recording trên JVM đang chạy bằng jcmd

Đây là cách thường dùng khi cần profiling một ứng dụng đã triển khai mà không muốn restart.

Liệt kê JVM process:

~~~bash
jcmd -l
~~~

Ví dụ output minh họa:

~~~text
8124 com.example.CheckoutApplication
9130 org.example.Worker
~~~

Giả sử PID của ứng dụng cần kiểm tra là 8124.

Bắt đầu recording:

~~~bash
jcmd 8124 JFR.start name=checkout-profile settings=profile duration=120s filename=/tmp/checkout-profile.jfr
~~~

Kiểm tra recording đang chạy:

~~~bash
jcmd 8124 JFR.check name=checkout-profile
~~~

JFR sẽ tự dừng sau 120 giây và ghi file theo filename đã chỉ định.

### Recording không giới hạn thời gian

Có thể bắt đầu recording và tự quyết định lúc dừng:

~~~bash
jcmd 8124 JFR.start name=incident settings=profile
~~~

Kiểm tra:

~~~bash
jcmd 8124 JFR.check name=incident verbose=true
~~~

Dump dữ liệu hiện có trong khi recording vẫn chạy:

~~~bash
jcmd 8124 JFR.dump name=incident filename=/tmp/incident-snapshot.jfr
~~~

JFR.dump tạo file snapshot; recording gốc vẫn tiếp tục chạy.

Khi đã thu thập đủ dữ liệu, dừng và lưu phần cuối:

~~~bash
jcmd 8124 JFR.stop name=incident filename=/tmp/incident-final.jfr
~~~

Nếu dùng JFR.stop mà không chỉ định filename, dữ liệu có thể bị loại bỏ thay vì được lưu ra file. Hãy chỉ định filename khi cần giữ recording.

### Dump một khoảng thời gian gần đây

JFR.dump hỗ trợ giới hạn theo tuổi dữ liệu hoặc khoảng thời gian. Ví dụ:

~~~bash
jcmd 8124 JFR.dump name=incident maxage=15m filename=/tmp/incident-last-15m.jfr
~~~

Lệnh này lưu phần dữ liệu gần đây theo giới hạn 15 phút. Hãy xác nhận recording có dữ liệu trong khoảng thời gian đó.

## 8. Duy trì continuous recording cho ứng dụng production

Một continuous recording có thể được khởi chạy cùng ứng dụng bằng cấu hình low-overhead:

~~~bash
java \
  -XX:StartFlightRecording:settings=default,disk=true,maxage=6h,maxsize=512M,dumponexit=true,filename=/var/log/myapp/shutdown.jfr \
  -jar app.jar
~~~

Trong ví dụ:

- settings=default chọn cấu hình ít overhead.
- disk=true cho phép ghi dữ liệu ra disk repository.
- maxage=6h giữ dữ liệu tối đa sáu giờ.
- maxsize=512M giới hạn dung lượng dữ liệu.
- dumponexit=true ghi recording khi JVM shutdown.
- filename xác định file đầu ra khi dump lúc shutdown.

Khi incident xảy ra, có thể dùng jcmd để dump phần dữ liệu cần điều tra trong khi JVM vẫn hoạt động.

### Vì sao phải giới hạn recording?

Nếu không đặt giới hạn phù hợp, dữ liệu recording có thể tăng liên tục và chiếm dung lượng ổ đĩa. Cần quản lý:

- Dung lượng repository và file dump.
- Thời gian giữ dữ liệu.
- Quyền đọc file recording.
- Nơi lưu trữ và thời hạn xóa.
- Quy trình chuyển file sang môi trường phân tích.
- Dung lượng còn trống trong container/host.

Continuous recording giúp lưu lại bối cảnh trước incident. Tuy vậy, nó không thay thế metrics và alerting; hãy dùng metrics để phát hiện bất thường, rồi dùng JFR để tìm nguyên nhân.

## 9. Thu recording bằng giao diện JDK Mission Control

JMC có thể kết nối với JVM và điều khiển recording.

Quy trình cơ bản:

1. Mở JDK Mission Control.
2. Trong JVM Browser, chọn JVM cần kiểm tra.
3. Nhấn chuột phải và chọn Start Flight Recording.
4. Chọn nơi lưu file.
5. Chọn Time Fixed hoặc Continuous recording.
6. Chọn template Continuous hoặc Profiling.
7. Điều chỉnh event settings/threshold nếu cần.
8. Bắt đầu recording.
9. Dump hoặc stop recording khi đã thu thập đủ dữ liệu.

Với continuous recording, JMC cho phép chọn giới hạn tuổi hoặc dung lượng dữ liệu cần giữ. Bạn cũng có thể dump toàn bộ recording, phần gần đây hoặc một khoảng thời gian cụ thể.

JMC còn có thể cấu hình trigger để tự động bắt đầu recording khi một điều kiện được đáp ứng, tùy cấu hình JMX và quyền quản trị JVM.

## 10. Đọc file recording bằng công cụ jfr

File .jfr là file nhị phân. Công cụ jfr đi kèm JDK hỗ trợ đọc và chuyển dữ liệu thành dạng con người có thể xem.

### Xem summary

~~~bash
jfr summary build/profile.jfr
~~~

Summary giúp kiểm tra:

- Thời gian bắt đầu và kết thúc.
- Tổng số event.
- Event type nào xuất hiện nhiều.
- Dung lượng recording.
- Event settings và thông tin tổng quát.

Nếu file không có event mong đợi, hãy xem lại template, thời gian recording và event threshold.

### In toàn bộ event

~~~bash
jfr print build/profile.jfr
~~~

Có thể tạo output JSON:

~~~bash
jfr print --json build/profile.jfr
~~~

Hoặc XML:

~~~bash
jfr print --xml build/profile.jfr
~~~

### Lọc theo event

~~~bash
jfr print --events jdk.ExecutionSample build/profile.jfr
~~~

Lọc theo category:

~~~bash
jfr print --categories "Java Application" build/profile.jfr
~~~

Tên event/category cần khớp metadata trong recording và phiên bản JDK. Có thể dùng jfr metadata để kiểm tra event names và field layout.

### Xem các view tổng hợp

~~~bash
jfr view all-views build/profile.jfr
jfr view all-events build/profile.jfr
~~~

Sau đó chọn view cụ thể được công cụ liệt kê:

~~~bash
jfr view <view-name> build/profile.jfr
~~~

### Kiểm tra metadata

~~~bash
jfr metadata build/profile.jfr
~~~

Metadata cho biết event types, category, fields và các thông tin cần thiết để hiểu dữ liệu trong recording.

## 11. Phân tích recording bằng JMC

Mở file .jfr bằng JMC. Recording thường mở trang Automated Analysis Results với các nhóm kết quả về Java Application, JVM Internals và Environment.

Hãy bắt đầu từ thời điểm ứng dụng chậm hoặc gặp lỗi, sau đó drill down vào event và stack trace tương ứng.

### CPU và method profiling

Mục tiêu là tìm code path tiêu thụ CPU.

Trong JMC:

1. Mở Code/Method Profiling hoặc Threads view.
2. Chọn đúng khoảng thời gian xảy ra vấn đề.
3. Xem các thread có nhiều CPU sample.
4. Mở stack trace và tìm package/method nổi bật.
5. Kiểm tra code và dependency tương ứng.
6. So sánh với recording baseline khi workload bình thường.

CPU execution sample cho biết thread đang thực thi ở đâu tại thời điểm lấy mẫu. Một method xuất hiện nhiều trong sample thường đáng chú ý, nhưng số sample không phải số lần gọi method chính xác.

Phân biệt:
- CPU-bound: thread liên tục chạy và chiếm CPU.
- Waiting: thread chờ I/O, lock, condition hoặc scheduler.
- Blocked: thread đang đợi monitor lock.
- Parked: thread tạm dừng chờ điều kiện hoặc synchronization.

Một ứng dụng có latency cao không nhất thiết đang tiêu thụ CPU cao. Hãy xem thread state để xác định nó đang chạy hay đang chờ.

### Allocation và memory

Nếu ứng dụng tạo quá nhiều object:

1. Mở Memory/Allocation view.
2. Xem allocation rate theo thời gian.
3. Tìm class hoặc stack trace tạo nhiều object.
4. Kiểm tra object có được tạo lặp trong hot path không.
5. Đánh giá temporary object, collection growth, boxing, string conversion và buffer allocation.
6. So sánh allocation rate trước và sau khi sửa.

Allocation cao có thể làm tăng GC frequency và CPU time. Tuy nhiên, allocation cao không tự động có nghĩa memory leak.

Memory leak thường liên quan đến object không còn cần thiết nhưng vẫn được giữ tham chiếu. Hãy kiểm tra live set/retained object và đường tham chiếu bằng công cụ phù hợp; JFR có thể giúp xác định thời điểm và allocation site.

### Garbage collection

Trong GC view, kiểm tra:

- Số lần GC.
- Thời gian pause.
- Thời lượng và khoảng cách giữa các GC.
- Allocation rate trước GC.
- Heap usage trước và sau GC.
- Concurrent GC activity nếu collector sử dụng.
- Các thời điểm GC trùng với latency spike.

Heap tăng rồi giảm sau GC có thể là allocation tạm thời bình thường. Nếu sau mỗi GC, live set tăng dần qua nhiều chu kỳ, cần điều tra object retention.

Không kết luận GC là nguyên nhân chỉ vì thấy một pause. Đối chiếu pause với request latency và workload.

### Lock contention và synchronization

Trong Threads/Locks view, tìm:

- Thread bị blocked lâu.
- Lock instance có nhiều waiter.
- Stack trace của thread đang giữ lock.
- Monitor enter/wait duration.
- Lock contention trùng với latency spike.

Một lock có nhiều waiter có thể tuần tự hóa công việc. Kiểm tra critical section có đang làm I/O, gọi service bên ngoài hoặc thực hiện tính toán lâu khi đang giữ lock hay không.

Nếu hạ threshold để bắt các lock wait ngắn hơn, recording có thể tạo nhiều event hơn. Hãy chọn ngưỡng phù hợp với latency mục tiêu.

### File và socket I/O

Trong I/O view, xem:

- Read/write duration.
- Socket wait.
- File operation kéo dài.
- Thread nào bị ảnh hưởng.
- Stack trace gọi I/O.
- Thời điểm I/O chậm có trùng với downstream latency không.

I/O chậm có thể xuất phát từ network, storage, remote service hoặc queueing. JFR giúp tìm call site và duration; cần đối chiếu với network metrics, server logs và tracing để xác định hệ thống gây chậm.

## 12. Đọc recording theo câu hỏi điều tra

Không nên xem mọi event theo thứ tự ngẫu nhiên. Bắt đầu bằng một câu hỏi cụ thể.

| Triệu chứng | View/event nên xem | Điều cần xác minh |
|---|---|---|
| CPU tăng cao | Execution samples, Threads, Code | Hot stack và thread đang chạy |
| Request latency tăng | Thread, I/O, Locks | Thời gian chạy và thời gian chờ |
| GC pause dài | Garbage Collection, Memory | Pause, heap và allocation |
| Memory tăng dần | Allocation, GC, Heap/Old Object | Allocation site và object retention |
| Thread bị nghẽn | Threads, Monitor/Locks | Blocked, parked và lock owner |
| Disk/network chậm | File I/O, Socket I/O | Call site và duration |
| Startup chậm | Class loading, JIT, startup events | Khởi tạo class, compile và dependency |

Một quy trình hữu ích:

1. Đánh dấu thời gian triệu chứng bằng metrics/logs.
2. Mở recording và chọn đúng time range.
3. Xác định thread hoặc event có tương quan với triệu chứng.
4. Mở stack trace.
5. Xác nhận bằng code và dependency.
6. Đưa ra giả thuyết có thể kiểm tra.
7. Sửa một yếu tố.
8. Thu recording mới dưới workload tương đương.
9. So sánh trước/sau.

## 13. Điều chỉnh event settings và threshold

Các file .jfc định nghĩa event nào được ghi và cách thu thập.

Không nên chỉnh trực tiếp file template mặc định trong JDK. Tạo bản cấu hình riêng để có thể review, version control và dùng lại.

Ví dụ tạo cấu hình mới từ profile template:

~~~bash
jfr configure \
  --input "$JAVA_HOME/lib/jfr/profile.jfc" \
  --output build/jfr-custom.jfc \
  jdk.JavaMonitorEnter#threshold=5ms
~~~

Lệnh này tạo cấu hình mới với ngưỡng monitor enter 5 ms. Kiểm tra cú pháp và event name bằng jfr help configure và metadata của JDK mục tiêu nếu event khác giữa các version.

Sử dụng cấu hình:

~~~bash
java \
  -XX:StartFlightRecording:settings=build/jfr-custom.jfc,duration=120s,filename=build/custom-profile.jfr \
  -jar app.jar
~~~

Một số nguyên tắc:

- Bật event cần cho câu hỏi điều tra.
- Đặt threshold đủ thấp để bắt bottleneck nhưng không thu quá nhiều event.
- Chỉ bật stack trace khi cần xác định call site.
- Tránh bật nhiều event chi tiết trong thời gian dài nếu chưa đánh giá overhead.
- Lưu cấu hình cùng tài liệu profiling để tái sử dụng.

### Stack depth

JFR lưu stack trace với độ sâu giới hạn. Tăng stack depth có thể giúp thấy nhiều tầng call hơn nhưng cũng có thể làm recording tốn tài nguyên hơn.

Hãy tăng khi stack hiện tại chưa đủ ngữ cảnh và kiểm tra ảnh hưởng trên workload thực tế. Không tăng giá trị tối đa chỉ vì muốn có nhiều dữ liệu.

## 14. Tạo custom event trong Java

JFR cho phép ứng dụng ghi lại dữ liệu nghiệp vụ bằng cách kế thừa jdk.jfr.Event.

Custom event hữu ích khi event hệ thống không cho biết thao tác nghiệp vụ nào đang chạy. Ví dụ, ta muốn đo thời gian xử lý một đơn hàng và ghi order ID, số item và trạng thái.

### Ví dụ Java 17+

Tạo file src/JfrDemo.java:

~~~java
import java.nio.file.Path;

import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;

public class JfrDemo {

    @Name("com.example.OrderProcessed")
    @Label("Order Processed")
    @Category({"Application", "Orders"})
    @Description("Measures the processing time of one order")
    @StackTrace(false)
    static class OrderProcessed extends Event {
        @Label("Order ID")
        String orderId;

        @Label("Item Count")
        int itemCount;

        @Label("Status")
        String status;
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("orders.jfr");
        Configuration config = Configuration.getConfiguration("default");

        try (Recording recording = new Recording(config)) {
            recording.setName("orders-demo");
            recording.setToDisk(true);
            recording.enable(OrderProcessed.class);
            recording.start();

            for (int i = 1; i <= 3; i++) {
                OrderProcessed event = new OrderProcessed();
                event.orderId = "ORD-" + i;
                event.itemCount = i * 2;
                event.status = "OK";

                event.begin();
                processOrder();
                event.end();

                if (event.shouldCommit()) {
                    event.commit();
                }
            }

            recording.stop();
            recording.dump(output);
        }

        System.out.println("Recording saved: orders.jfr");
    }

    private static void processOrder() throws InterruptedException {
        Thread.sleep(20);
    }
}
~~~

Compile bằng JDK 17+:

~~~bash
mkdir -p out
javac --release 17 -d out src/JfrDemo.java
java -cp out JfrDemo
~~~

Stdout:

~~~text
Recording saved: orders.jfr
~~~

File orders.jfr được tạo trong working directory.

### Giải thích code

- OrderProcessed extends Event: định nghĩa event type.
- @Name: tạo event name ổn định để cấu hình và lọc.
- @Label, @Category, @Description: cung cấp metadata dễ đọc trong JMC.
- @StackTrace(false): không thu stack trace cho từng custom event này.
- begin() và end(): đo duration của một lần xử lý.
- shouldCommit(): kiểm tra event có được ghi theo event settings/threshold hay không.
- commit(): gửi event vào JFR.
- Recording: tạo recording bằng cấu hình default, bật custom event, start, stop và dump ra file.

JFR hỗ trợ các primitive Java và một số reference type như String, Thread, Class cho event fields. Array, enum và các reference type khác không tự động trở thành event field được hỗ trợ. Hãy dùng kiểu dữ liệu được API hỗ trợ và kiểm tra metadata của event.

### Vì sao dùng shouldCommit?

Việc tạo payload có thể tốn chi phí. Nếu event đang bị disable hoặc duration thấp hơn threshold, shouldCommit() có thể trả về false.

Với payload đắt tiền, chỉ tính dữ liệu bổ sung khi event có khả năng được ghi:

~~~java
OrderProcessed event = new OrderProcessed();

event.begin();
processOrder();
event.end();

if (event.shouldCommit()) {
    event.orderId = buildExpensiveDiagnosticId();
    event.itemCount = countItems();
    event.status = "OK";
    event.commit();
}
~~~

Ví dụ này chỉ minh họa cách trì hoãn phần tính toán payload. Trong code thực tế, hãy gán các field cần thiết theo thời điểm phù hợp để dữ liệu phản ánh đúng thao tác đang đo.

### Chọn điểm đặt custom event

Đặt event ở ranh giới có ý nghĩa nghiệp vụ, ví dụ:

- Một request được xử lý.
- Một lần gọi payment provider.
- Một batch import hoàn tất.
- Một lần xử lý message.
- Một bước trong workflow.

Không tạo event cho mọi vòng lặp nhỏ hoặc getter đơn giản. Event quá dày có thể làm recording lớn và tăng overhead.

Không ghi password, access token, session ID, thông tin cá nhân, request body hoặc dữ liệu nhạy cảm vào event field. Chọn identifier đã được giả danh hoặc mã correlation không chứa bí mật.

## 15. Điều khiển JFR bằng Recording API

Ngoài jcmd, ứng dụng có thể điều khiển recording bằng API trong module jdk.jfr.

Một recording được tạo từ Configuration hoặc settings map, sau đó cấu hình trước khi start.

Ví dụ rút gọn:

~~~java
Configuration config = Configuration.getConfiguration("default");

try (Recording recording = new Recording(config)) {
    recording.setName("application-diagnostic");
    recording.setMaxAge(Duration.ofHours(1));
    recording.setMaxSize(256L * 1024 * 1024);
    recording.setToDisk(true);
    recording.start();

    runWorkload();

    recording.stop();
    recording.dump(Path.of("application.jfr"));
}
~~~

Đoạn này cần các import:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;
~~~

Ý nghĩa:

- setMaxAge: giới hạn tuổi dữ liệu được giữ.
- setMaxSize: giới hạn dung lượng dữ liệu.
- setToDisk(true): cho phép ghi dữ liệu vào disk repository.
- start(): bắt đầu recording.
- stop(): dừng recording.
- dump(Path): xuất dữ liệu thành file .jfr.
- close(): giải phóng dữ liệu/tài nguyên của recording.

Nếu không đặt maxAge hoặc maxSize, recording lưu trên disk có thể tăng không giới hạn. Hãy đặt giới hạn cho recording dài hạn.

Trong ví dụ này, runWorkload() là method của ứng dụng, không phải API JFR. Thay bằng thao tác thực tế cần quan sát.

## 16. Đánh giá overhead và chất lượng recording

JFR được thiết kế để thu thập dữ liệu với overhead thấp, nhưng overhead không bằng không và phụ thuộc vào ứng dụng, event settings, template, tần suất event và thời gian ghi.

Một số nguyên tắc:

- Bắt đầu với default cho continuous recording.
- Dùng profile trong khoảng ngắn khi cần thêm chi tiết.
- Đo ảnh hưởng của recording bằng benchmark/load test đại diện.
- Không bật event chi tiết nếu chưa có câu hỏi cụ thể.
- Giới hạn maxage và maxsize.
- Chỉ tăng stack depth khi cần.
- Kiểm tra dung lượng file và tốc độ phát sinh event.

### Cẩn trọng với Heap Statistics

Heap Statistics có thể kích hoạt full/old garbage collection ở đầu và cuối quá trình thu thập để lấy thông tin heap. Điều này có thể tạo pause và làm sai lệch phép đo latency.

Chỉ bật khi đang điều tra memory leak hoặc cần phân tích live set. Khi đo latency hoặc GC pause, hãy cân nhắc loại event này ra khỏi recording.

### Cẩn trọng với Path to GC Roots

Thu thập đường đi tới GC roots có thể tốn thời gian và gây pause. Chỉ bật khi có giả thuyết memory leak cụ thể. Không bật cho mọi recording liên tục.

## 17. Quy trình profiling có thể lặp lại

Một lần profiling tốt cần có mục tiêu và điều kiện đo rõ ràng.

### Trước khi recording

1. Ghi lại triệu chứng: CPU cao, latency tăng, GC pause, memory growth hay I/O chậm.
2. Ghi lại timestamp hoặc khoảng thời gian xảy ra.
3. Ghi lại JDK version, JVM flags và môi trường chạy.
4. Xác nhận workload và traffic đủ đại diện.
5. Chọn template và duration.
6. Xác định nơi lưu recording và quyền truy cập.
7. Kiểm tra disk space và giới hạn file.

### Trong lúc recording

1. Không thay đổi nhiều biến cấu hình cùng lúc.
2. Ghi lại thời điểm bắt đầu/kết thúc.
3. Ghi lại request, batch hoặc incident ID liên quan.
4. Quan sát metrics bên ngoài để xác định cửa sổ cần phân tích.
5. Dump recording gần thời điểm triệu chứng.

### Sau recording

1. Chạy jfr summary.
2. Mở file trong JMC.
3. Chọn đúng time range.
4. Tìm event/thread có tương quan với triệu chứng.
5. Đọc stack trace và event payload.
6. Đưa ra một giả thuyết có thể kiểm chứng.
7. Thay đổi một yếu tố.
8. Lặp lại recording dưới workload tương đương.
9. So sánh CPU, allocation, pause, lock wait hoặc I/O duration.

### Ghi lại kết quả

Một report profiling nên lưu:

| Trường | Nội dung |
|---|---|
| Application | Tên service/build/version |
| JDK | Vendor, version và runtime |
| Environment | OS, CPU, memory, container limits |
| Workload | Request rate, scenario, test duration |
| Recording | Template, start/end, file size |
| Symptom | CPU, latency, memory, GC, lock hoặc I/O |
| Finding | Event, thread, stack trace và time range |
| Hypothesis | Nguyên nhân dự kiến |
| Change | Code/config được điều chỉnh |
| Before/after | Metrics và recording so sánh |
| Limitation | Thiếu event, sampling interval hoặc dữ liệu không đủ |

## 18. JFR trong production và bảo mật dữ liệu

JFR có thể dùng để điều tra ứng dụng production vì được tích hợp trong JVM và hỗ trợ continuous recording với overhead thấp. Tuy vậy, cần đo overhead theo workload thật và áp dụng chính sách quản lý dữ liệu.

Recording có thể chứa:

- Thread names và stack traces.
- Class/package và method names.
- JVM arguments hoặc system properties.
- File paths, hostnames và thông tin môi trường.
- Custom event payload do ứng dụng ghi.
- Metadata giúp suy ra hành vi hoặc cấu trúc nội bộ của service.

Không mặc định chia sẻ file .jfr ra ngoài tổ chức. Hãy kiểm soát quyền đọc, thời hạn lưu và kênh truyền file.

### Lọc dữ liệu trước khi chia sẻ

Có thể dùng jfr scrub để loại event, category hoặc thread không cần thiết:

~~~bash
jfr scrub \
  --exclude-threads "HealthCheck*" \
  --exclude-events "jdk.SomeSensitiveEvent" \
  input.jfr sanitized.jfr
~~~

Tên event/thread trong ví dụ chỉ minh họa; hãy chọn filter dựa trên metadata thực tế của recording.

Scrub theo event/thread không thay thế review thủ công. Kiểm tra custom event payload, command-line values và thông tin nhạy cảm trước khi chia sẻ recording.

### Giới hạn quyền điều khiển JVM

jcmd cho phép gửi diagnostic command đến JVM. Chỉ cấp quyền cho operator đáng tin cậy và bảo vệ host/container nơi JVM chạy. Không mở diagnostic access hoặc JMX management rộng ra mạng công cộng.

## 19. JFR khác gì heap dump, thread dump và metrics?

| Công cụ | Dữ liệu | Câu hỏi phù hợp |
|---|---|---|
| JFR | Event theo thời gian, sample, duration, stack | Điều gì đã xảy ra trong giai đoạn chậm? |
| Heap dump | Object graph tại một thời điểm | Object nào đang được giữ trong heap? |
| Thread dump | Thread state và stack tại một thời điểm | Thread đang chạy, blocked hay deadlocked? |
| Metrics | Số liệu tổng hợp theo thời gian | Khi nào hệ thống bất thường và mức độ ra sao? |
| Logs | Sự kiện nghiệp vụ/application message | Request hoặc operation nào lỗi? |
| Distributed tracing | Span giữa nhiều service | Latency nằm ở service/downstream nào? |

JFR không thay thế các công cụ này. Nó bổ sung dữ liệu runtime chi tiết để liên hệ triệu chứng với thread, allocation, GC, lock và I/O.

Ví dụ:
- Metrics phát hiện p99 latency tăng.
- Distributed trace chỉ ra service thanh toán chậm.
- JFR cho thấy thread của service đang chờ socket I/O.
- Log/correlation ID giúp xác định downstream request cụ thể.

Kết hợp các nguồn giúp tránh quy nhầm nguyên nhân cho JVM khi vấn đề nằm ở network hoặc service khác.

## 20. Lỗi thường gặp và cách xử lý

### jcmd -l không thấy JVM

**Nguyên nhân:** dùng sai user, process nằm trong container namespace khác, JVM chạy trên host khác hoặc PID không được liệt kê.

**Cách xử lý:** chạy trên đúng host/container; dùng cùng effective user/group; xác định PID trong đúng namespace; kiểm tra jcmd PID help.

### jcmd báo attach không được

**Nguyên nhân:** quyền user khác, attach listener bị tắt, container policy hoặc JVM không hỗ trợ diagnostic attach theo cách đang dùng.

**Cách xử lý:** kiểm tra quyền process, runtime và attach settings; xem log JVM; nếu không thể attach, cấu hình recording lúc startup bằng -XX:StartFlightRecording.

### Không tìm thấy file .jfr

**Nguyên nhân:** chưa stop/dump recording, sai working directory, đường dẫn không ghi được hoặc JVM kết thúc trước khi dump.

**Cách xử lý:** kiểm tra filename trong JFR.start; dùng JFR.check; chỉ định đường dẫn tuyệt đối có quyền ghi; dùng dumponexit=true nếu cần dump lúc shutdown.

### Recording file rỗng hoặc thiếu event

**Nguyên nhân:** template không bật event mong muốn, recording quá ngắn, event threshold quá cao hoặc workload chưa tạo event.

**Cách xử lý:** chạy jfr summary và jfr metadata; kiểm tra template; điều chỉnh event settings; thu lại trong workload có triệu chứng.

### CPU profile không chỉ ra method rõ ràng

**Nguyên nhân:** recording quá ngắn, sample quá ít, thread không hoạt động trong time range hoặc bottleneck là waiting/I/O thay vì CPU.

**Cách xử lý:** thu lâu hơn trong khoảng workload ổn định; xem Threads và I/O; kiểm tra time range; đối chiếu với metrics.

### JFR file quá lớn

**Nguyên nhân:** dùng profile template quá lâu, bật quá nhiều event, threshold thấp hoặc custom event phát sinh quá dày.

**Cách xử lý:** dùng default cho continuous recording; giới hạn duration/maxage/maxsize; giảm event/stack trace; thêm throttle hoặc threshold phù hợp.

### JMC không mở được recording

**Nguyên nhân:** file chưa hoàn tất, bị truncate, version JMC quá cũ hoặc file được copy khi đang ghi.

**Cách xử lý:** dump recording bằng JFR.dump hoặc stop đúng cách; kiểm tra file bằng jfr summary; cập nhật JMC tương thích; copy file sau khi dump hoàn tất.

### Không thấy custom event

**Nguyên nhân:** event không được enable, class chưa được load, field type không được hỗ trợ, recording không chạy hoặc event bị threshold loại.

**Cách xử lý:** gọi recording.enable(EventClass.class); kiểm tra event.isEnabled()/shouldCommit(); kiểm tra metadata bằng jfr metadata; xác nhận recording chứa event name.

### Kết quả profiling khác benchmark

**Nguyên nhân:** workload, warmup, JDK, CPU, memory limit hoặc event settings khác nhau.

**Cách xử lý:** chuẩn hóa workload và môi trường; ghi rõ JDK/JVM flags; thu baseline và recording với cùng thời gian; không so sánh trực tiếp hai recording có điều kiện khác nhau.

### Latency tăng khi bật Heap Statistics

**Nguyên nhân:** Heap Statistics có thể kích hoạt old/full GC để thu heap data.

**Cách xử lý:** tắt event này khi đo latency; chỉ bật trong phiên điều tra memory leak/live set có kiểm soát.

### JFR.stop nhưng không có file

**Nguyên nhân:** không truyền filename nên dữ liệu recording có thể bị loại bỏ.

**Cách xử lý:** dừng với filename=/path/to/output.jfr; kiểm tra file tồn tại và chạy jfr summary.

### Recording chứa dữ liệu nhạy cảm

**Nguyên nhân:** custom event hoặc metadata có chứa identifier, đường dẫn, system property hoặc thông tin request.

**Cách xử lý:** hạn chế quyền truy cập; scrub event/thread không cần; kiểm tra payload; xóa file theo retention policy; không gửi file chưa review ra ngoài.

## 21. Bài tập thực hành

### Bài 1 — Thu recording từ ứng dụng

1. Chạy một Java application hoặc service mẫu.
2. Dùng jcmd -l tìm PID.
3. Bắt đầu recording 60 giây bằng settings=profile.
4. Gửi workload ổn định trong khoảng recording.
5. Kiểm tra file .jfr được tạo.
6. Chạy jfr summary và mở file bằng JMC.

Kết quả cần ghi lại: JDK version, template, thời lượng, dung lượng file và số event.

### Bài 2 — Tìm bottleneck

1. Chọn một workload có CPU hoặc latency cao.
2. Mở Threads/Code/Memory/I/O view.
3. Tìm time range có vấn đề.
4. Xác định thread, event và stack trace nổi bật.
5. Viết một giả thuyết về nguyên nhân.
6. Đề xuất thay đổi có thể kiểm chứng.

Không chỉ ghi “method A chậm”; cần chỉ ra nó đang dùng CPU, chờ lock hay chờ I/O và bằng chứng trong recording.

### Bài 3 — Ghi custom business event

1. Compile và chạy JfrDemo.
2. Mở orders.jfr bằng JMC.
3. Tìm event com.example.OrderProcessed.
4. Xem duration, order ID, item count và status.
5. Thay Thread.sleep bằng một thao tác xử lý khác.
6. Thu recording lại và so sánh duration.

### Bài 4 — So sánh default và profile

1. Thu một recording bằng default.
2. Chạy cùng workload và thu một recording bằng profile.
3. So sánh số event, file size và dữ liệu method/allocation.
4. Ghi nhận overhead quan sát được.
5. Đề xuất template phù hợp cho continuous monitoring và profiling ngắn hạn.

## 22. Checklist trước khi kết luận profiling

### Thu thập

- [ ] Đã xác định đúng JVM/PID và user.
- [ ] JDK/JFR version phù hợp.
- [ ] Template phù hợp mục tiêu.
- [ ] Recording bao phủ đúng thời gian xảy ra triệu chứng.
- [ ] Có workload đủ đại diện.
- [ ] Có giới hạn dung lượng/thời gian.
- [ ] File .jfr đã được dump hoàn chỉnh.

### Phân tích

- [ ] Đã kiểm tra summary và event metadata.
- [ ] Đã chọn đúng time range.
- [ ] Đã phân biệt CPU, waiting, blocked và I/O.
- [ ] Đã đọc stack trace/event payload.
- [ ] Đã đối chiếu metrics, logs hoặc traces.
- [ ] Đã ghi giả thuyết có thể kiểm chứng.
- [ ] Không coi sample count là số lần gọi method chính xác.

### Vận hành và bảo mật

- [ ] Đã đo overhead trên workload phù hợp.
- [ ] Không bật event tốn kém khi không cần.
- [ ] Recording có retention và access control.
- [ ] Không có dữ liệu nhạy cảm ngoài ý muốn.
- [ ] Đã review/scrub file trước khi chia sẻ.
- [ ] Đã lưu thông tin môi trường và cấu hình để tái lập.

## 23. Tài liệu tham khảo chính thức

- [JDK Mission Control User Guide — Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html) — event types, templates, time-fixed/continuous recording, cách thu và phân tích recording.
- [JDK Mission Control User Guide](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/jdk-mission-control.html) — JMC, JVM Browser, JMX Console và Flight Recorder.
- [The jcmd Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html) — JFR.start, JFR.check, JFR.dump, JFR.stop và diagnostic command.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — StartFlightRecording, event settings, max age/size và repository options.
- [jfr — Parse and Print Flight Recorder Files](https://dev.java/learn/jvm/monitoring-troubleshooting/monitoring/jfr/) — jfr summary, print, view, metadata, configure, scrub và file handling.
- [Configuring the JDK Flight Recorder — Dev.java](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/) — .jfc, default.jfc, profile.jfc và event settings.
- [Event — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Event.html) — định nghĩa custom event, field types, begin, end, commit và shouldCommit.
- [Recording — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html) — điều khiển recording bằng Java API, giới hạn dung lượng và dump.
- [jdk.jfr Package — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/package-summary.html) — event metadata, event settings và Flight Recorder API.
- [Troubleshoot Performance Issues Using Flight Recorder — Java SE 11](https://docs.oracle.com/en/java/javase/11/troubleshoot/troubleshoot-performance-issues-using-jfr.html) — overhead, heap statistics và lưu ý khi phân tích performance.

JFR giúp ghi lại hành vi thực tế của JVM và ứng dụng để điều tra sau khi vấn đề xảy ra. Hãy chọn recording template theo mục tiêu, thu đúng time range, phân tích event và stack trace bằng JMC hoặc jfr, rồi xác minh giả thuyết bằng workload tương đương. Một quy trình tốt vừa thu đủ dữ liệu để tìm bottleneck, vừa giới hạn overhead, dung lượng và quyền truy cập recording.
