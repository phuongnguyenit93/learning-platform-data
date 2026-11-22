# Event trong Java Flight Recorder (JFR)

**Java Flight Recorder (JFR)** là framework thu thập sự kiện và dữ liệu profiling được tích hợp trong JDK. JFR ghi lại những gì JVM và ứng dụng đang làm theo dòng thời gian, gồm CPU, thread, garbage collection, allocation, class loading, exception, file I/O, socket I/O và các sự kiện do ứng dụng tự định nghĩa.

Một **event JFR** là bản ghi có timestamp, thông tin loại sự kiện và payload. Tùy loại event, bản ghi có thể có duration, stack trace, thread, class hoặc các trường dữ liệu riêng. Một file recording có thể chứa hàng nghìn hoặc hàng triệu event; công cụ phân tích dùng các event này để dựng timeline, thống kê và tìm bottleneck.

JFR hữu ích khi cần trả lời những câu hỏi như:

- Thread nào sử dụng CPU nhiều nhất?
- Method nào xuất hiện thường xuyên trong các CPU samples?
- Garbage collection diễn ra khi nào và pause bao lâu?
- Object allocation tăng ở khu vực code nào?
- Thread bị block do monitor hoặc lock nào?
- Ứng dụng chờ file, socket hoặc database trong bao lâu?
- Class nào được nạp hoặc unload trong giai đoạn incident?
- Request nào chậm hơn ngưỡng mong muốn?
- Một hành vi nghiệp vụ cụ thể có tương quan với GC, lock contention hoặc I/O không?

Bài này tập trung vào event model, các nhóm event thường dùng, cách cấu hình recording, cách đọc file .jfr và cách tạo custom event bằng Java 17+. Tên event, settings và dữ liệu sẵn có phụ thuộc JDK release, JVM và template được chọn; hãy kiểm tra metadata của recording thực tế trước khi xây dựng phân tích tự động.

## 1. JFR và event model

JFR thu thập dữ liệu ở dạng event có timestamp. Event được ghi vào recording repository/buffer và có thể được lưu thành file nhị phân .jfr để phân tích sau.

Mô hình tổng quát:

~~~text
Java application + HotSpot JVM
             |
             | JVM events / application events
             v
       Java Flight Recorder
             |
             | timestamped events
             v
    Recording buffers / repository
             |
             | dump
             v
          file.jfr
             |
       +-----+------+
       |            |
       v            v
 JDK Mission     jfr command /
 Control (JMC)   JFR consumer API
       |            |
       +-----+------+
             |
             v
   Timeline, tables, charts,
   event details and analysis
~~~

JFR và JDK Mission Control (JMC) thường được dùng cùng nhau:

- JFR thu thập dữ liệu từ JVM và ứng dụng.
- JMC mở file recording, hiển thị timeline, biểu đồ, bảng và kết quả phân tích tự động.
- Công cụ jfr dòng lệnh tóm tắt, lọc và in event.
- API jdk.jfr.consumer cho phép ứng dụng khác đọc hoặc xử lý event bằng Java code.

JFR phù hợp cho profiling và chẩn đoán khi ứng dụng đang chạy. Recording có thể được bắt đầu lúc JVM khởi động hoặc trong runtime bằng jcmd/JMC.

## 2. Bốn dạng event thường gặp

JDK phân loại event theo cách chúng được phát sinh và ghi nhận. Bốn dạng quan trọng là duration, instant, sample và custom event.

### Duration event

Duration event có thời điểm bắt đầu và kết thúc. Event thể hiện một hoạt động kéo dài trong một khoảng thời gian.

Ví dụ:

- Thread chờ monitor.
- Thread chờ một hoạt động I/O.
- Garbage collection phase.
- Một method hoặc tác vụ nghiệp vụ được instrument.
- Thời gian xử lý một request.

Duration giúp trả lời hoạt động bắt đầu lúc nào, kết thúc lúc nào và mất bao lâu.

Một event duration do ứng dụng tự tạo thường dùng:

~~~java
event.begin();
// Thực hiện công việc cần đo
event.end();
event.commit();
~~~

JFR ghi timestamp và duration của event khi commit.

### Instant event

Instant event diễn ra tại một thời điểm và được ghi ngay khi commit. Event không cần đo khoảng thời gian bắt đầu/kết thúc.

Ví dụ:

- Một exception được ném.
- Một thread được tạo.
- Một trạng thái hoặc mốc nghiệp vụ xảy ra.
- Một lần thay đổi cấu hình.

Với custom instant event, chỉ cần gán field và gọi commit mà không cần begin/end.

### Sample event

Sample event được ghi theo chu kỳ hoặc theo một cơ chế lấy mẫu. Nó cung cấp ảnh chụp định kỳ về trạng thái hệ thống.

Ví dụ:

- CPU load.
- Execution sample của thread.
- Một số thống kê JVM được phát ra theo chu kỳ.

Sampling giúp ước lượng hành vi theo thời gian với chi phí thấp hơn việc instrument và ghi mọi lần gọi method. Vì là lấy mẫu, dữ liệu không nhất thiết bao phủ mọi lần thực thi.

### Custom event

Custom event do ứng dụng hoặc thư viện định nghĩa để ghi dữ liệu đặc thù của nghiệp vụ.

Ví dụ:

- OrderProcessed: đơn hàng được xử lý.
- SlowHttpRequest: HTTP request vượt ngưỡng.
- SqlOperation: thao tác SQL đã hoàn thành.
- PaymentAttempt: lần thử thanh toán.
- CacheLookup: kết quả và thời gian truy cập cache.

Custom event giúp ghép dữ liệu nghiệp vụ với event JVM. Khi request chậm, có thể xem cùng khoảng thời gian đó có GC pause, thread contention, CPU saturation hoặc socket read chậm hay không.

## 3. Cấu trúc của một event

Một event thường có các thành phần:

| Thành phần | Ý nghĩa |
|---|---|
| Event name/type | Tên định danh của loại event |
| Timestamp | Thời điểm event bắt đầu hoặc được ghi nhận |
| Duration | Thời lượng nếu là duration event |
| Thread | Thread liên quan, khi event cung cấp thông tin này |
| Stack trace | Call stack tại thời điểm event được ghi, nếu được bật |
| Payload fields | Dữ liệu mô tả event |
| Metadata | Label, description, category, unit và thông tin hiển thị |

Ví dụ minh họa:

~~~text
com.acme.OrderProcessed {
  startTime = 10:15:20.120
  duration = 42.5 ms
  orderId = "ORD-105"
  itemCount = 3
  succeeded = true
  eventThread = "http-worker-7"
}
~~~

Đây là dữ liệu giả lập để minh họa cấu trúc, không phải output cố định của một JVM.

### Timestamp và duration

Timestamp giúp đặt event vào đúng vị trí trên timeline. Duration cho biết event kéo dài bao lâu. Khi phân tích performance, hãy so sánh duration của event với SLA hoặc latency budget của ứng dụng.

Instant event không có duration theo nghĩa đo một khoảng thực thi. Duration event có start time và end time. Sample event được ghi ở thời điểm lấy mẫu.

### Stack trace

Stack trace cho biết call path liên quan tới event, giúp truy về method hoặc call site gây ra hoạt động.

Không phải event nào cũng có stack trace. Stack trace có thể bị tắt trong event settings, bị giới hạn độ sâu hoặc không có trong một số event mẫu.

Stack trace sâu hơn cung cấp thêm chi tiết nhưng có thể tăng dung lượng và overhead. Chỉ tăng stack depth khi câu hỏi chẩn đoán cần đến nó.

### Payload fields

Payload là các field bổ sung mô tả sự kiện. Ví dụ custom event có thể ghi orderId, số lượng item và kết quả xử lý.

Chỉ ghi những trường có giá trị chẩn đoán. Không đưa password, access token, session cookie, nội dung request riêng tư hoặc dữ liệu cá nhân không cần thiết vào payload.

## 4. Các nhóm event dựng sẵn của JVM

JFR có nhiều event được tích hợp sẵn. Template quyết định event nào được bật, ngưỡng nào được áp dụng và có thu thập stack trace hay không.

Các tên dưới đây là ví dụ thường gặp; event khả dụng và field có thể thay đổi theo JDK và recording settings.

### CPU và execution

| Event ví dụ | Thông tin |
|---|---|
| jdk.CPULoad | CPU load của process/JVM và máy |
| jdk.ExecutionSample | Stack sample của thread đang thực thi |
| jdk.NativeMethodSample | Sample liên quan tới native execution khi được hỗ trợ |

Dùng các event này để tìm method hoặc call path xuất hiện thường xuyên trong CPU samples, đồng thời so sánh CPU của JVM với CPU tổng thể của máy.

ExecutionSample là sampling data, không phải danh sách đầy đủ mọi method call. Một method xuất hiện nhiều trong sample thường là ứng viên cần điều tra, nhưng cần đọc cùng workload và thời gian thực thi.

### Thread và synchronization

| Event ví dụ | Thông tin |
|---|---|
| jdk.ThreadStart | Thread được tạo |
| jdk.ThreadEnd | Thread kết thúc |
| jdk.JavaMonitorEnter | Thread chờ vào synchronized monitor |
| jdk.JavaMonitorWait | Thread chờ trên monitor |
| jdk.ThreadPark | Thread bị park |
| jdk.ThreadSleep | Thread đang sleep |

Các event này giúp phát hiện lock contention, thread chờ lâu, thread lifecycle bất thường và thời gian ứng dụng không thực thi vì phải đợi tài nguyên.

Với JavaMonitorEnter, chú ý duration và stack trace. Nhiều event có duration dài trên cùng monitor có thể cho thấy một vùng synchronized đang giới hạn throughput.

### Garbage collection và memory

| Event ví dụ | Thông tin |
|---|---|
| jdk.GarbageCollection | Một chu kỳ GC |
| jdk.GCPhasePause | Một GC pause phase |
| jdk.GCHeapSummary | Thông tin heap tại các mốc GC |
| jdk.ObjectAllocationSample | Sample về allocation |
| jdk.MetaspaceSummary | Thông tin về Metaspace khi event được bật |

Dùng nhóm này để xem GC pause, heap usage, allocation pressure và thay đổi live set. Không kết luận memory leak chỉ từ một event hoặc một lần heap tăng; cần so sánh nhiều mốc thời gian và workload tương đương.

### Class loading và exception

| Event ví dụ | Thông tin |
|---|---|
| jdk.ClassLoad | Class được nạp |
| jdk.ClassUnload | Class được unload |
| jdk.JavaExceptionThrow | Exception được ném |

Nếu số class tăng liên tục và class unload thấp, hãy kiểm tra class loader lifecycle, dynamic proxy, generated classes và plugin reload. Exception event có thể giúp tìm exception được ném thường xuyên, kể cả những exception được catch ngay sau đó.

### File và network I/O

| Event ví dụ | Thông tin |
|---|---|
| jdk.FileRead | Hoạt động đọc file |
| jdk.FileWrite | Hoạt động ghi file |
| jdk.SocketRead | Hoạt động đọc socket |
| jdk.SocketWrite | Hoạt động ghi socket |

I/O event hữu ích khi latency không nằm ở CPU hoặc GC mà do chờ file system, socket hoặc dịch vụ bên ngoài. Cần xem duration, kích thước I/O, thread và stack trace nếu được ghi.

### Xác nhận event khả dụng

Không nên giả định một event luôn tồn tại hoặc được bật trong mọi recording. Có thể xem metadata của file:

~~~bash
jfr metadata recording.jfr
~~~

Lọc metadata theo category hoặc event:

~~~bash
jfr metadata --categories GC recording.jfr
jfr metadata --events jdk.CPULoad recording.jfr
~~~

Có thể xem danh sách event type trong file bằng:

~~~bash
jfr view types recording.jfr
~~~

Metadata cho biết event name, category và field layout. Đây là căn cứ tốt hơn việc viết parser dựa trên một danh sách event cố định.

## 5. Recording settings: default và profile

JFR đi kèm hai template thông dụng trong thư mục:

~~~text
JAVA_HOME/lib/jfr/
  default.jfc
  profile.jfc
~~~

Hai template này kiểm soát event nào được ghi, ngưỡng duration, sampling period, stack trace và các setting khác.

| Template | Mục đích | Đặc điểm |
|---|---|---|
| default.jfc | Continuous recording và quan sát thường xuyên | Thu thập tập dữ liệu hữu ích với overhead thấp |
| profile.jfc | Profiling có mục tiêu trong thời gian ngắn | Thu thập nhiều event hơn, có thể tăng overhead |

default.jfc thường phù hợp cho recording chạy liên tục và theo dõi dài hạn. Theo tài liệu JFR API, template này thường có overhead dưới 1%, nhưng kết quả thực tế phụ thuộc workload và settings.

Một giới hạn quan trọng: template default trong JDK 26 không thu thập heap statistics hoặc allocation profiling. Nếu cần phân tích allocation hoặc xu hướng heap, hãy dùng profile hoặc custom settings phù hợp.

profile.jfc thu thập nhiều dữ liệu hơn, ví dụ thông tin allocation và stack trace chi tiết hơn. Dùng trong khoảng thời gian ngắn để tìm nguyên nhân cụ thể, sau đó quay lại cấu hình nhẹ hơn nếu cần recording liên tục.

### Không nên bật tất cả event

Bật nhiều event, giảm threshold quá thấp hoặc lấy sample quá thường xuyên có thể:

- Tăng lượng dữ liệu recording.
- Tăng CPU và bộ nhớ dùng cho ghi event.
- Tăng dung lượng file.
- Làm tăng overhead ứng dụng.
- Tạo quá nhiều event khiến việc phân tích khó hơn.

Hãy chọn event theo câu hỏi cần trả lời, không theo nguyên tắc thu thập mọi thứ.

## 6. Hai kiểu recording thường dùng

### Time-fixed recording

Time-fixed recording chạy trong một khoảng thời gian xác định rồi kết thúc.

Ví dụ:

- Profiling 2 phút khi tái hiện request chậm.
- Thu thập 5 phút khi CPU tăng cao.
- Ghi trong một bài load test.
- Theo dõi một lần deploy hoặc warm-up.

Time-fixed recording thường dùng profile.jfc để có nhiều dữ liệu hơn.

### Continuous recording

Continuous recording chạy lâu dài, giữ lại dữ liệu gần đây trong buffer/repository. Khi cần điều tra, người vận hành dump khoảng dữ liệu liên quan ra file.

Nếu buffer hoặc repository đạt giới hạn, dữ liệu cũ nhất có thể bị loại bỏ để dành chỗ cho dữ liệu mới. Vì vậy, continuous recording phù hợp để lưu lịch sử gần nhất trước incident.

default.jfc là lựa chọn phổ biến cho continuous recording. Có thể giới hạn tuổi dữ liệu và dung lượng để tránh recording chiếm đĩa không kiểm soát.

## 7. Bắt đầu recording khi JVM khởi động

Dùng startup option StartFlightRecording:

~~~bash
java -XX:StartFlightRecording:settings=default,duration=5m,name=boot,filename=boot.jfr -jar app.jar
~~~

Ví dụ này bắt đầu recording khi ứng dụng chạy, dùng default settings, ghi trong 5 phút và lưu file boot.jfr.

Có thể đặt delay:

~~~bash
java -XX:StartFlightRecording:delay=20s,duration=2m,settings=profile,name=startup-profile,filename=startup.jfr -jar app.jar
~~~

JVM chờ 20 giây rồi bắt đầu recording trong 2 phút. Cách này hữu ích khi muốn bỏ qua giai đoạn khởi tạo ban đầu hoặc chỉ thu thập một giai đoạn xác định.

### Dump recording khi JVM thoát

~~~bash
java -XX:StartFlightRecording:settings=default,dumponexit=true,filename=shutdown.jfr -jar app.jar
~~~

dumponexit yêu cầu JVM ghi recording ra file khi shutdown. Cần đảm bảo thư mục output tồn tại và process có quyền ghi.

### Recording liên tục từ startup

~~~bash
java -XX:StartFlightRecording:settings=default,disk=true,maxage=6h,maxsize=1g -XX:FlightRecorderOptions:repository=/var/tmp/jfr -jar app.jar
~~~

Ví dụ này giữ dữ liệu tối đa 6 giờ và giới hạn dung lượng disk repository ở 1 GB. Đường dẫn repository phải có đủ dung lượng và quyền ghi.

## 8. Bắt đầu recording trong runtime bằng jcmd

Nếu JVM đã chạy, dùng jcmd thay vì restart chỉ để bật recording.

Tìm PID:

~~~bash
jcmd -l
~~~

Kiểm tra các command JFR:

~~~bash
jcmd 2125 help JFR.start
~~~

Bắt đầu recording 5 phút:

~~~bash
jcmd 2125 JFR.start name=incident settings=profile duration=5m filename=/secure/records/incident.jfr
~~~

Các thành phần:

- PID 2125 là ví dụ; thay bằng PID thực tế.
- name giúp định danh recording.
- settings chọn default hoặc profile.
- duration giới hạn thời gian.
- filename chỉ định file output.

Nếu chỉ cần ghi nhẹ và liên tục, chọn settings=default. Nếu đang điều tra CPU, allocation, lock contention hoặc latency trong thời gian ngắn, có thể chọn profile.

### Kiểm tra recording đang chạy

~~~bash
jcmd 2125 JFR.check
~~~

Xem chi tiết event settings:

~~~bash
jcmd 2125 JFR.check verbose=true
~~~

### Dump snapshot nhưng tiếp tục recording

~~~bash
jcmd 2125 JFR.dump name=incident filename=/secure/records/incident-snapshot.jfr
~~~

JFR.dump ghi dữ liệu hiện có ra file trong khi recording vẫn tiếp tục. Đây là lựa chọn hữu ích để lấy snapshot giữa một incident mà không kết thúc quá trình thu thập.

Có thể giới hạn khoảng thời gian dump bằng begin, end, maxage hoặc maxsize theo cú pháp JDK hiện tại.

### Dừng recording và lưu file

~~~bash
jcmd 2125 JFR.stop name=incident filename=/secure/records/incident-final.jfr
~~~

JFR.stop kết thúc recording và lưu dữ liệu vào file chỉ định. Nếu không cung cấp filename, dữ liệu recording có thể bị loại bỏ khi stop; hãy kiểm tra cú pháp của JDK đích trước khi dừng.

## 9. Cấu hình recording liên tục bằng jcmd

Có thể tạo recording rolling:

~~~bash
jcmd 2125 JFR.start name=rolling settings=default disk=true maxage=6h maxsize=1g
~~~

Ý nghĩa:

- disk=true ghi dữ liệu vào disk repository.
- maxage=6h giới hạn dữ liệu lưu tối đa 6 giờ.
- maxsize=1g giới hạn dung lượng dữ liệu.
- name=rolling giúp nhận diện recording.

Khi incident xảy ra, dump dữ liệu:

~~~bash
jcmd 2125 JFR.dump name=rolling filename=/secure/records/incident-window.jfr
~~~

Recording rolling vẫn tiếp tục chạy sau dump. Nếu muốn kết thúc hẳn:

~~~bash
jcmd 2125 JFR.stop name=rolling filename=/secure/records/rolling-final.jfr
~~~

Đừng để recording liên tục không có giới hạn maxage/maxsize nếu không có kế hoạch quản lý dung lượng và retention.

## 10. Event settings: enabled, threshold, period và stackTrace

Event settings quyết định event nào được ghi và ghi với mức chi tiết nào.

| Setting | Ý nghĩa | Ví dụ |
|---|---|---|
| enabled | Bật/tắt event | true hoặc false |
| threshold | Chỉ ghi duration event đạt ngưỡng | 10 ms |
| period | Chu kỳ phát event định kỳ | 1 s |
| stackTrace | Có ghi stack trace hay không | true hoặc false |
| throttle | Giới hạn tốc độ phát event | 100/s |
| filter | Lọc một số event theo class/method hoặc annotation, tùy event hỗ trợ | java.util.HashMap |

### enabled

Nếu enabled=false, event không được ghi. Bật event chỉ có ý nghĩa khi recording đang chạy và settings cho phép event đó.

### threshold

Threshold là duration tối thiểu để event được ghi. Ví dụ threshold 10 ms cho JavaMonitorEnter nghĩa là các lần monitor contention ngắn hơn ngưỡng sẽ không được ghi.

Threshold phù hợp khi chỉ muốn tập trung vào hoạt động chậm đáng kể. Nếu đặt quá cao, các contention ngắn nhưng xảy ra rất nhiều có thể bị bỏ qua.

### period

Period áp dụng cho periodic event hoặc event lấy mẫu. Ví dụ CPU Load được lấy mỗi giây:

~~~text
jdk.CPULoad#period=1 s
~~~

Giảm period làm tăng tần suất sample và có thể tăng lượng dữ liệu.

### stackTrace

stackTrace=true yêu cầu ghi stack trace khi event được phát. Stack trace giúp xác định call path nhưng có thể tăng chi phí và kích thước recording.

### throttle

Throttle giới hạn tốc độ phát event. Ví dụ 100/s giới hạn event không vượt quá khoảng 100 lần mỗi giây theo setting tương ứng.

### filter

Một số event hỗ trợ filter để giới hạn class/method hoặc annotation cần theo dõi. Không phải event nào cũng có filter setting; xem metadata hoặc help của JFR API để xác định.

## 11. Tạo custom .jfc settings

Không cần chỉnh sửa trực tiếp default.jfc hoặc profile.jfc. Hãy tạo file mới dựa trên một template có sẵn:

~~~bash
jfr configure --input profile.jfc --output incident.jfc jdk.JavaMonitorEnter#threshold=5ms
~~~

Ví dụ tạo cấu hình mới với threshold lock contention 5 ms. File incident.jfc là bản riêng; template gốc được giữ nguyên.

Có thể thêm event setting riêng bằng dấu cộng trước tên event:

~~~bash
jfr configure --input default.jfc --output app-events.jfc +com.acme.OrderProcessed#enabled=true
~~~

Dùng custom configuration khi cần ghi event cụ thể, thay đổi sampling period, threshold hoặc stack trace.

Khi dùng JFR.start, có thể chọn file settings:

~~~bash
jcmd 2125 JFR.start name=custom settings=/etc/acme/incident.jfc duration=5m filename=incident.jfr
~~~

Event setting có thể truyền trực tiếp trong JFR.start theo dạng event-name#setting=value. Khi setting trên command line trùng với cấu hình trong JFC, giá trị truyền trực tiếp được ưu tiên.

## 12. Đọc file recording bằng lệnh jfr

File .jfr là file nhị phân. Không nên mở bằng text editor để đọc trực tiếp.

### Xem summary

~~~bash
jfr summary incident.jfr
~~~

Summary cho biết thông tin recording, thời gian, dung lượng và số lượng event theo loại. Đây là bước đầu tiên để xác nhận file có dữ liệu và hiểu event nào chiếm phần lớn recording.

### In toàn bộ event

~~~bash
jfr print incident.jfr
~~~

Output có thể rất dài. Nên lọc event cần quan sát.

### Lọc event theo tên

~~~bash
jfr print --events jdk.GarbageCollection,jdk.CPULoad incident.jfr
~~~

### Lọc theo category

~~~bash
jfr print --categories GC incident.jfr
~~~

### Xuất JSON

~~~bash
jfr print --json --events jdk.GarbageCollection incident.jfr
~~~

JSON hoặc XML phù hợp khi cần tích hợp với công cụ xử lý dữ liệu, nhưng hãy dùng parser theo schema của recording và JDK thực tế.

### Điều chỉnh độ sâu stack trace

~~~bash
jfr print --stack-depth 20 incident.jfr
~~~

Stack trace mặc định được giới hạn ở độ sâu nhất định. Tăng độ sâu giúp xem call path sâu hơn nhưng có thể làm output lớn.

### Xem các view tổng hợp

~~~bash
jfr view all-views incident.jfr
jfr view all-events incident.jfr
~~~

Có thể xem một event type như một view:

~~~bash
jfr view jdk.GarbageCollection incident.jfr
~~~

### Xem metadata

~~~bash
jfr metadata incident.jfr
~~~

Metadata cho biết event name, category và field layout. Dùng để kiểm tra tên event và field trước khi viết code xử lý recording.

## 13. Phân tích recording bằng JDK Mission Control

JDK Mission Control (JMC) cung cấp giao diện trực quan để phân tích file .jfr. JMC không nhất thiết được cài cùng JDK thông thường; tải từ trang chính thức và dùng phiên bản tương thích.

Một quy trình phân tích:

1. Mở JMC và chọn file recording.
2. Xem Overview để kiểm tra khoảng thời gian và số lượng event.
3. Mở Automated Analysis Results để xem các cảnh báo và heuristic.
4. Kiểm tra CPU/Code để tìm method và package sử dụng nhiều CPU.
5. Kiểm tra Threads và Locks để tìm contention, thread park hoặc wait.
6. Kiểm tra Memory và Garbage Collections để xem heap, allocation và pause.
7. Kiểm tra I/O để tìm file hoặc socket operation kéo dài.
8. Mở Event Browser để xem event type và field cụ thể.
9. Chọn một khoảng thời gian đáng chú ý và drill down vào event tương ứng.
10. Đối chiếu với log, metric, trace và thời điểm incident.

### CPU và Code

Xem CPU load, execution samples, top methods và stack trace. Nếu CPU process cao, tìm method xuất hiện thường xuyên trong sample. Nếu CPU thấp nhưng request chậm, kiểm tra thread waiting, lock hoặc I/O.

### Threads và Locks

Xem thread activity, thread state và monitor contention. Một lock có nhiều event duration dài có thể là bottleneck. Kiểm tra cả thread giữ lock và thread đang chờ.

### Memory và GC

Xem heap usage, allocation rate, object allocation samples, GC events và pause duration. Heap tăng rồi giảm sau GC có thể là hành vi bình thường; live set tăng dần qua thời gian mới là tín hiệu cần điều tra sâu.

### I/O

Xem file read/write và socket read/write duration. I/O event kéo dài có thể cho thấy ứng dụng chờ storage, network hoặc dịch vụ ngoài.

### Event Browser

Event Browser liệt kê event type và thống kê theo từng loại. Có thể tạo custom page để tập trung vào một event cụ thể.

## 14. Tạo custom event bằng Java API

JFR API nằm trong module jdk.jfr. Có thể tạo event bằng cách kế thừa lớp jdk.jfr.Event và khai báo các field cần ghi.

Các annotation hữu ích:

| Annotation | Vai trò |
|---|---|
| @Name | Tên event ổn định |
| @Label | Tên hiển thị thân thiện |
| @Description | Mô tả event hoặc field |
| @Category | Nhóm event trong công cụ phân tích |
| @Threshold | Ngưỡng duration mặc định |
| @StackTrace | Bật/tắt stack trace mặc định |
| @Period | Chu kỳ cho event định kỳ |

Ví dụ event nghiệp vụ OrderProcessed:

~~~java
@Name("com.acme.OrderProcessed")
@Label("Order Processed")
@Category({"Acme", "Orders"})
@Description("Records the processing of an order")
static class OrderProcessed extends Event {
    @Label("Order ID")
    String orderId;

    @Label("Item Count")
    int itemCount;

    @Label("Succeeded")
    boolean succeeded;
}
~~~

### Các kiểu field được hỗ trợ

Event class hỗ trợ:

- Primitive: boolean, char, byte, short, int, long, float, double.
- String.
- Thread.
- Class.

Array, enum và các reference type khác không được ghi như field event thông thường. Static field cũng không được đưa vào payload. Hãy dùng field đơn giản và rõ nghĩa để JMC hiển thị dễ hiểu.

### Đo duration event

~~~java
OrderProcessed event = new OrderProcessed();
event.begin();

// Thực hiện công việc

event.end();
if (event.shouldCommit()) {
    event.commit();
}
~~~

begin bắt đầu đo thời gian, end kết thúc khoảng đo và commit ghi event. shouldCommit kiểm tra event có được bật và có thỏa threshold trước khi ghi. Có thể dùng nó để tránh tạo payload tốn kém khi event không được lưu.

### Ghi instant event

Với event không cần duration:

~~~java
OrderStatusChanged event = new OrderStatusChanged();
event.orderId = "ORD-105";
event.status = "PAID";
event.commit();
~~~

Không cần gọi begin/end cho event instant.

## 15. Ví dụ Java 17+: ghi custom event vào file JFR

Ví dụ này tạo recording, ghi 5 event OrderProcessed, dừng recording và xuất file orders.jfr.

Cấu trúc:

~~~text
project/
  src/
    com/acme/JfrEventDemo.java
  out/
~~~

Tệp src/com/acme/JfrEventDemo.java:

~~~java
package com.acme;

import java.nio.file.Path;

import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class JfrEventDemo {

    @Name("com.acme.OrderProcessed")
    @Label("Order Processed")
    @Category({"Acme", "Orders"})
    @Description("Records the processing of an order")
    static class OrderProcessed extends Event {
        @Label("Order ID")
        String orderId;

        @Label("Item Count")
        int itemCount;

        @Label("Succeeded")
        boolean succeeded;
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("orders.jfr");

        try (Recording recording =
                     new Recording(Configuration.getConfiguration("default"))) {
            recording.setName("orders-demo");
            recording.enable(OrderProcessed.class);
            recording.start();

            for (int i = 1; i <= 5; i++) {
                OrderProcessed event = new OrderProcessed();
                event.begin();
                Thread.sleep(10);
                event.end();

                if (event.shouldCommit()) {
                    event.orderId = "ORD-" + i;
                    event.itemCount = i;
                    event.succeeded = true;
                    event.commit();
                }
            }

            recording.stop();
            recording.dump(output);
        }

        System.out.println("RECORDING=orders.jfr");
        System.out.println("EVENTS=5");
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 --add-modules jdk.jfr -d out src/com/acme/JfrEventDemo.java
~~~

Chạy:

~~~bash
java --add-modules jdk.jfr -cp out com.acme.JfrEventDemo
~~~

Stdout chính xác:

~~~text
RECORDING=orders.jfr
EVENTS=5
~~~

File orders.jfr được tạo trong working directory. Event duration bao gồm khoảng thời gian từ begin đến end; payload ghi order ID, số lượng item và trạng thái xử lý.

### Xem custom event

Xem summary:

~~~bash
jfr summary orders.jfr
~~~

In riêng custom event:

~~~bash
jfr print --events com.acme.OrderProcessed orders.jfr
~~~

Kết quả có timestamp và duration thực tế, nên các con số thời gian thay đổi theo máy. Hãy kiểm tra orderId, itemCount và succeeded để xác nhận payload được ghi.

## 16. Đọc recording bằng JFR consumer API

Ngoài lệnh jfr, Java code có thể đọc event trong file bằng package jdk.jfr.consumer.

Ví dụ:

~~~java
import java.io.IOException;
import java.nio.file.Path;

import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrReader {
    public static void main(String[] args) throws IOException {
        Path file = Path.of(args[0]);

        try (RecordingFile recording = new RecordingFile(file)) {
            while (recording.hasMoreEvents()) {
                RecordedEvent event = recording.readEvent();

                if (event.getEventType().getName()
                        .equals("com.acme.OrderProcessed")) {
                    System.out.println(
                            event.getString("orderId")
                            + " items="
                            + event.getInt("itemCount")
                            + " success="
                            + event.getBoolean("succeeded"));
                }
            }
        }
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 --add-modules jdk.jfr -d out src/com/acme/JfrReader.java
~~~

Chạy:

~~~bash
java --add-modules jdk.jfr -cp out com.acme.JfrReader orders.jfr
~~~

Stdout:

~~~text
ORD-1 items=1 success=true
ORD-2 items=2 success=true
ORD-3 items=3 success=true
ORD-4 items=4 success=true
ORD-5 items=5 success=true
~~~

Thứ tự event trong ví dụ theo thứ tự tạo. Với recording lớn, tránh đọc toàn bộ file vào memory nếu không cần; xử lý tuần tự qua RecordingFile hoặc EventStream phù hợp hơn.

## 17. Event streaming trong runtime

Nếu cần nhận event khi chúng phát sinh, có thể dùng RecordingStream từ jdk.jfr.consumer.

Ví dụ:

~~~java
import jdk.jfr.Configuration;
import jdk.jfr.consumer.RecordingStream;

public final class LiveJfrEvents {
    public static void main(String[] args) throws Exception {
        try (RecordingStream stream =
                     new RecordingStream(Configuration.getConfiguration("default"))) {
            stream.onEvent("jdk.GarbageCollection",
                    event -> System.out.println(event));
            stream.onEvent("jdk.CPULoad",
                    event -> System.out.println(event));
            stream.start();
        }
    }
}
~~~

RecordingStream tạo stream event từ JVM hiện tại. Ví dụ này lắng nghe GC và CPU Load; chương trình tiếp tục chạy cho đến khi stream được đóng hoặc process kết thúc.

Event streaming phù hợp khi ứng dụng cần phản ứng với event hoặc chuyển event sang hệ thống khác. Cần kiểm soát tốc độ xử lý, queue, backpressure và quyền truy cập dữ liệu để tránh consumer chậm làm tăng bộ nhớ.

## 18. Tạo event nghiệp vụ có ích

Custom event có giá trị nhất khi giúp liên kết thời gian xử lý nghiệp vụ với hành vi JVM.

Ví dụ với HTTP request:

| Field | Ý nghĩa |
|---|---|
| route | Tên route đã chuẩn hóa |
| method | HTTP method |
| statusCode | HTTP status |
| duration | Thời gian xử lý |
| result | Thành công/thất bại |
| tenantTier | Nhóm tenant nếu cần phân tích |
| requestId | ID tương quan đã được làm sạch |

Ví dụ với SQL:

| Field | Ý nghĩa |
|---|---|
| operation | SELECT, INSERT, UPDATE |
| datasource | Tên datasource |
| duration | Thời gian thực thi |
| rows | Số dòng trả về hoặc ảnh hưởng |
| success | Kết quả |

Không ghi raw SQL chứa dữ liệu người dùng, credential hoặc parameter nhạy cảm. Thường chỉ cần operation name, datasource, duration và số lượng.

### Chọn field có cardinality hợp lý

Không nên tạo event field với dữ liệu có hàng triệu giá trị duy nhất nếu không cần. Request ID có thể hữu ích để truy vết một request nhưng sẽ tạo cardinality lớn. Chỉ giữ nó trong recording ngắn hoặc khi có yêu cầu tương quan rõ ràng.

Với monitoring dài hạn, dùng route template thay cho URL đầy đủ và nhóm giá trị thành bucket khi phù hợp.

## 19. Phân tích CPU, memory, GC, lock và I/O

### CPU bottleneck

1. Mở CPU/Code view.
2. Xem CPU load theo thời gian.
3. Xem ExecutionSample và top methods.
4. Chọn khoảng CPU tăng cao.
5. Mở stack trace để xác định call path.
6. Đối chiếu thread và workload trong cùng khoảng.

CPU cao có thể do vòng lặp tính toán, serialization, regex, compression hoặc xử lý dữ liệu lớn. Một method xuất hiện trong nhiều samples là gợi ý, không phải bằng chứng duy nhất.

### Memory allocation

1. Xem allocation rate và allocation samples.
2. Tìm class tạo nhiều object.
3. Xem top allocation methods.
4. So sánh heap usage qua thời gian.
5. Nếu nghi memory leak, thu thập thêm heap dump và phân tích retained heap/GC roots.

Allocation nhiều không đồng nghĩa với leak. Object tạm thời được GC thu hồi có thể làm GC pressure tăng nhưng live set vẫn ổn định.

### Garbage collection

1. Xem các GC event trên timeline.
2. Kiểm tra pause duration.
3. Xem heap trước và sau GC.
4. Đối chiếu allocation rate và live set.
5. Kiểm tra collector phase và thời điểm request latency tăng.

Nếu request chậm trùng với GC pause, xác định pause đó có phải nguyên nhân chính hay chỉ cùng xuất hiện trong một giai đoạn tải cao.

### Lock contention

1. Xem JavaMonitorEnter và các synchronization event.
2. Tìm duration dài hoặc số lần chờ cao.
3. Kiểm tra monitor/class và stack trace.
4. Tìm thread đang giữ lock.
5. Đối chiếu với throughput và latency.

Một lock contention event đơn lẻ không đủ kết luận bottleneck. Cần xem tổng thời gian chờ, tần suất và số thread bị ảnh hưởng.

### I/O latency

1. Xem FileRead/FileWrite và SocketRead/SocketWrite.
2. Lọc operation có duration lớn.
3. Xem thread, endpoint hoặc file metadata nếu có.
4. Đối chiếu với log của dịch vụ ngoài.
5. Kiểm tra timeout, retry và pool saturation.

## 20. Chọn threshold và sampling period

Threshold và period ảnh hưởng trực tiếp tới lượng dữ liệu.

| Mục tiêu | Cách chọn |
|---|---|
| Chỉ tìm lock wait đáng kể | Đặt threshold theo latency cần quan sát |
| Theo dõi CPU liên tục | Dùng sampling period phù hợp, tránh quá dày |
| Điều tra request chậm | Tạo custom duration event và threshold theo SLA |
| Tìm allocation | Chọn profile hoặc event allocation phù hợp |
| Theo dõi GC | Bật GC event và pause details |
| Ghi liên tục production | Bắt đầu với default.jfc |

Ví dụ giảm threshold lock contention xuống 5 ms:

~~~text
jdk.JavaMonitorEnter#threshold=5ms
~~~

Ví dụ sample CPU Load mỗi giây:

~~~text
jdk.CPULoad#period=1 s
~~~

Threshold thấp hơn có thể thu thập nhiều event hơn. Period ngắn hơn làm tăng tần suất sample. Không chọn giá trị cực nhỏ nếu chưa đo overhead và dung lượng recording.

## 21. Overhead và giới hạn recording

JFR được thiết kế để thu thập dữ liệu runtime với overhead thấp, nhưng overhead không bằng không.

Các yếu tố ảnh hưởng:

- Số lượng event được bật.
- Tần suất sample.
- Threshold duration.
- Có ghi stack trace hay không.
- Stack depth.
- Tốc độ event của ứng dụng.
- Kích thước payload custom event.
- Thời gian recording.
- Cấu hình default hay profile.

Một số event hoặc settings có thể gây thêm chi phí và trong một số trường hợp kích hoạt GC để thu thập thông tin. Hãy thử nghiệm trên staging hoặc trong một cửa sổ tải đại diện trước khi mở rộng recording.

### Giới hạn dung lượng

Dùng maxage và maxsize để giới hạn dữ liệu trên disk. Với continuous recording, buffer có thể loại bỏ dữ liệu cũ nhất khi đạt giới hạn.

Không để file recording tích lũy vô hạn. Theo dõi disk usage, đặt retention và xóa file sau khi điều tra hoàn tất.

### path-to-gc-roots

Tùy chọn này thu thập đường dẫn tới GC roots để hỗ trợ tìm memory leak. Việc thu thập có thể mất thời gian và làm ứng dụng pause trong một khoảng ngắn.

Chỉ bật khi có nghi ngờ memory leak:

~~~bash
jcmd 2125 JFR.start name=leak-check settings=profile duration=5m path-to-gc-roots=true filename=leak-check.jfr
~~~

Không bật path-to-gc-roots trong mọi recording production.

## 22. Bảo vệ dữ liệu trong file JFR

Recording có thể chứa nhiều thông tin nội bộ:

- Tên thread, class, package và method.
- Stack trace và call path.
- System properties và JVM configuration.
- File path, socket metadata và endpoint.
- Event payload do ứng dụng tự ghi.
- Dữ liệu nghiệp vụ nếu custom event thiết kế không cẩn thận.

Biện pháp bảo vệ:

1. Chỉ ghi event và field cần thiết.
2. Không đưa password, token, cookie hoặc raw request body vào event.
3. Chuẩn hóa route, hostname và SQL metadata khi phù hợp.
4. Lưu file trong thư mục có quyền đọc giới hạn.
5. Mã hóa khi lưu hoặc chuyển giao theo chính sách tổ chức.
6. Giới hạn thời gian retention.
7. Kiểm tra file trước khi gửi ra ngoài tổ chức.
8. Scrub event hoặc thread không cần thiết trước khi chia sẻ.
9. Ghi lại ai thu thập, thời điểm và mục đích.
10. Xóa bản sao tạm khi kết thúc điều tra.

Có thể dùng jfr scrub để loại một số event, category hoặc thread:

~~~bash
jfr scrub --exclude-events jdk.SocketRead,jdk.SocketWrite input.jfr sanitized.jfr
~~~

Scrub giúp loại bớt nội dung nhưng không thay thế việc kiểm tra thủ công. Hãy xác minh file sanitized trước khi chia sẻ vì dữ liệu nhạy cảm có thể còn nằm trong event khác hoặc custom payload.

## 23. Troubleshooting JFR

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| jcmd không thấy JVM | PID sai, container namespace hoặc khác user | Dùng jcmd -l/ps trong đúng môi trường và xác nhận quyền attach |
| JFR.start không được hỗ trợ | JVM không có Flight Recorder hoặc command không khả dụng | Kiểm tra JDK/JVM và jcmd PID help |
| Không có custom event trong file | Event chưa được enable hoặc recording không chạy khi commit | Enable event trong recording và kiểm tra JFR.check |
| Event xuất hiện nhưng thiếu field | Field type không được hỗ trợ hoặc field là static | Dùng primitive/String/Thread/Class và field instance |
| Không thấy event duration ngắn | Threshold cao hơn duration thực tế | Kiểm tra event threshold và hạ có kiểm soát |
| File .jfr quá lớn | Event quá nhiều, period quá ngắn hoặc stack trace sâu | Dùng default, tăng threshold, giới hạn maxage/maxsize |
| File recording không được tạo | Sai filename, thư mục không có quyền ghi hoặc recording chưa stop/dump | Kiểm tra đường dẫn, quyền và JFR.stop/JFR.dump |
| JFR.dump không dừng recording | Đây là hành vi bình thường | Dùng JFR.stop nếu muốn kết thúc recording |
| JFR.stop không lưu file | Không truyền filename | Cung cấp filename khi cần giữ dữ liệu |
| JMC không mở file | File không hoàn chỉnh, phiên bản hoặc dữ liệu không tương thích | Kiểm tra jfr summary và dùng JMC phù hợp |
| Không thấy allocation data | default.jfc không bật allocation profiling | Dùng profile hoặc custom settings |
| Recording không có heap statistics | default.jfc không thu thập heap statistics | Chọn settings phù hợp và đo overhead |
| Stack trace quá ngắn | Stack depth hoặc setting bị giới hạn | Kiểm tra stackTrace và cấu hình stack depth |
| File chứa dữ liệu nhạy cảm | Event payload hoặc system metadata có thông tin nội bộ | Scrub, giới hạn quyền truy cập và retention |

## 24. Quy trình thực hành phân tích một incident

1. Xác định triệu chứng: CPU cao, request chậm, GC pause, lock contention hoặc I/O chậm.
2. Xác định PID và JDK của ứng dụng.
3. Kiểm tra recording đang chạy bằng JFR.check.
4. Nếu có continuous recording, dump khoảng thời gian incident.
5. Nếu chưa có recording, bắt đầu một recording phù hợp bằng jcmd.
6. Chọn default cho thu thập nhẹ hoặc profile cho điều tra ngắn hạn.
7. Giới hạn duration, maxage và maxsize.
8. Dùng jfr summary để xác nhận file và số lượng event.
9. Mở file trong JMC hoặc lọc bằng jfr print/view.
10. Chọn khoảng thời gian latency bất thường.
11. Đối chiếu CPU, GC, threads, locks, memory và I/O.
12. Dùng stack trace để truy về code path.
13. Kiểm tra log/metric/trace để xác nhận giả thuyết.
14. Chỉ bật thêm event hoặc hạ threshold nếu recording hiện tại chưa đủ dữ liệu.
15. Ghi lại kết luận, mức độ chắc chắn và cách tái hiện.
16. Bảo vệ và xóa file theo retention sau khi hoàn tất.

## 25. Ghi nhớ

- JFR là framework event collection và profiling tích hợp trong JDK.
- Event có timestamp, type, payload và có thể có duration/stack trace.
- Bốn dạng thường gặp là duration, instant, sample và custom event.
- JFR ghi các nhóm event về CPU, threads, locks, GC, memory, class loading, exceptions và I/O.
- default.jfc phù hợp cho continuous recording với overhead thấp; profile.jfc thu thập nhiều dữ liệu hơn và có overhead cao hơn.
- default.jfc không thu thập heap statistics hoặc allocation profiling trong cấu hình mặc định của JDK 26.
- Có thể bắt đầu recording lúc startup bằng StartFlightRecording hoặc runtime bằng jcmd JFR.start.
- JFR.check xem recording, JFR.dump tạo snapshot và tiếp tục recording, JFR.stop kết thúc recording.
- maxage và maxsize giúp giới hạn dữ liệu continuous recording.
- Event settings gồm enabled, threshold, period, stackTrace và throttle.
- Custom event được tạo bằng cách kế thừa jdk.jfr.Event và khai báo field được hỗ trợ.
- begin/end đo duration; commit ghi event; shouldCommit giúp tránh công việc payload khi event không được ghi.
- jfr summary, print, view, metadata, configure và scrub hỗ trợ kiểm tra, lọc và quản lý file recording.
- JMC giúp xem timeline, CPU, memory, GC, threads, locks và I/O.
- JFR không thay thế log, metric hoặc distributed tracing; các nguồn dữ liệu bổ sung bối cảnh cho incident.
- File .jfr có thể chứa stack trace, system metadata và dữ liệu nghiệp vụ; phải bảo vệ như dữ liệu production.

## Tài liệu tham khảo chính thức

- [Diagnostic Tools — JDK 26, Flight Recorder](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [The jfr Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jfr.html)
- [The java Command — StartFlightRecording, JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [jdk.jfr Package Summary — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [Event API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [Recording API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Flight Recorder API Programmer's Guide — JDK 26](https://docs.oracle.com/en/java/javase/26/jfapi/)
- [JFR Consumer API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/consumer/package-summary.html)
- [JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html)