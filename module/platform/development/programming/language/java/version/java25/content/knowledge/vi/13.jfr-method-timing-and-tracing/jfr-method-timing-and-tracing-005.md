# Đọc số lần gọi, thời lượng và stack trace trong ngữ cảnh bản ghi

## 1. Mục tiêu và phạm vi

Bài thuộc chương **Đo và truy vết JFR** của module **JAVA_VERSION_JAVA25**. Java 25 cung cấp các khả năng quan sát quan trọng cho ứng dụng Java hiện đại: Flight Recorder (JFR), method timing và method tracing, CPU sampling, sự kiện tùy biến, cùng các công cụ phân tích bản ghi. Chúng giúp trả lời các câu hỏi:

- Method nào được gọi nhiều nhất trong một luồng nghiệp vụ?
- Một method mất bao lâu theo thời gian thực, gồm cả thời gian chờ I/O hoặc lock?
- Lời gọi nào gây ra độ trễ, và call stack đi qua những lớp nào?
- Sự kiện lock contention, socket wait hoặc exception nào xảy ra trong cùng request/order?
- Kết quả có đủ đại diện để kết luận hay đang thiếu event, filter hoặc stack trace?

**JEP 520 — JFR Method Timing & Tracing** là tính năng chính thức trong JDK 25. JEP này bổ sung hai event:

- `jdk.MethodTiming`: thống kê số lần gọi và thời gian thực thi gần đúng của các method được chọn.
- `jdk.MethodTrace`: ghi từng lần gọi method được chọn, gồm thời điểm, thời lượng, thread và stack trace.

Hai event bổ sung cho các event sampling sẵn có của JFR. Chúng không yêu cầu `--enable-preview`, không cần cài Java agent để instrument toàn bộ ứng dụng và có thể cấu hình bằng command line, `jcmd` hoặc JFR API.

Bài cũng dùng `@Contextual` — annotation JFR được bổ sung trong Java 25 — để gắn thông tin request/transaction vào các event phát sinh trong cùng thread và khoảng thời gian của event context. Đây là cách giúp đọc một bản ghi theo ngữ cảnh nghiệp vụ thay vì chỉ nhìn những event rời rạc.

Sau bài này, bạn có thể:

1. Phân biệt method timing, method trace và method sampling.
2. Chọn event phù hợp với câu hỏi hiệu năng hoặc điều tra lỗi.
3. Lọc method theo class, tên method, constructor, static initializer hoặc annotation.
4. Khởi động recording lúc launch hoặc attach vào JVM đang chạy bằng `jcmd`.
5. Đọc invocation count, minimum, average, maximum và stack trace.
6. Hiểu thời lượng wall-clock khác CPU time như thế nào.
7. Dùng `jfr view`, `jfr print`, `jfr summary` và JDK Mission Control để phân tích bản ghi.
8. Gắn trace ID/order ID bằng `@Contextual`, rồi liên hệ với lock, I/O và các event khác.
9. Giảm overhead và tránh kết luận sai do filter, sampling, threshold hoặc workload không đại diện.

**Phạm vi phiên bản:** ví dụ lệnh và API trong bài nhắm tới HotSpot JDK 25 trở lên. Không sử dụng hướng dẫn profiling đã legacy như `-Xprof`, HPROF hoặc giả định phải cài một agent bytecode bên ngoài mới đo được method timing. Với các tính năng JFR mới của JDK 25, không bật preview.

## 2. JFR lưu điều gì trong một bản ghi?

### 2.1. Recording là tập hợp các event có thời gian

JFR thu thập dữ liệu dưới dạng event. Một event thường có:

- Tên event và metadata.
- Timestamp xác định thời điểm xảy ra.
- Duration nếu event có thời gian bắt đầu/kết thúc.
- Thread phát sinh event.
- Payload như method, số byte, loại lock, địa chỉ socket hoặc thông tin nghiệp vụ.
- Stack trace nếu event được cấu hình ghi stack trace.

Recording được lưu thành file nhị phân `.jfr`. Dùng công cụ `jfr` để tóm tắt, lọc, xem chi tiết hoặc xuất JSON/XML; dùng JDK Mission Control (JMC) để xem timeline, call stack và các trang phân tích chuyên sâu.

Một bản ghi chỉ chứa những event đã được bật và thỏa các điều kiện lọc/threshold/throttle. Vì vậy, **không thấy event không đồng nghĩa sự việc không xảy ra**. Có thể event bị tắt, filter không khớp, threshold quá cao, recording không bao phủ đúng thời gian hoặc dữ liệu đã bị giới hạn.

### 2.2. Phân biệt ba góc nhìn về method

| Cơ chế | Dữ liệu chính | Trả lời câu hỏi | Hạn chế |
| --- | --- | --- | --- |
| `jdk.MethodTiming` | Invocation count, min/average/max elapsed time gần đúng | Method nào được gọi bao nhiêu lần và thời gian tổng thể ra sao? | Dữ liệu tổng hợp, không có stack trace riêng cho từng lần gọi |
| `jdk.MethodTrace` | Một event cho mỗi invocation được chọn, duration, thread, stack trace | Lần gọi cụ thể diễn ra khi nào, qua call stack nào? | Có thể tạo nhiều event; cần filter hẹp và recording ngắn |
| `jdk.ExecutionSample` | Mẫu stack tại những thời điểm JVM lấy mẫu | CPU đang thực thi ở method nào thường xuyên? | Sampling là ước lượng; không đếm chính xác mọi invocation |

JFR còn có những event khác để tìm nguyên nhân của thời gian chờ:

- `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`: chờ hoặc tranh chấp monitor.
- `jdk.ThreadPark`, `jdk.ThreadSleep`: thread bị park hoặc sleep.
- `jdk.SocketRead`, `jdk.SocketWrite`: thời gian chờ I/O mạng.
- `jdk.FileRead`, `jdk.FileWrite`: I/O file.
- `jdk.GarbageCollection` và các event GC liên quan: hoạt động thu gom rác.

Không dùng method timing để kết luận CPU nóng. `jdk.MethodTiming` đo thời gian gần đúng method thực thi theo wall-clock, gồm cả những khoảng chờ trong lúc method đang chạy. Nếu một method mất 200 ms vì đợi database, nó vẫn có thể hiện thời lượng gần 200 ms dù CPU chỉ làm việc một phần nhỏ thời gian đó.

### 2.3. JEP 520 trong Java 25

JEP 520 bổ sung các event `jdk.MethodTiming` và `jdk.MethodTrace`, cùng các tùy chọn cấu hình lọc method. Bạn có thể chọn một method, một class, một nhóm method hoặc method được đánh dấu annotation mà không phải tự viết profiler agent.

| Event | Dữ liệu tiêu biểu | Cách đọc thuận tiện |
| --- | --- | --- |
| `jdk.MethodTiming` | Method, invocations, minimum, average, maximum | `jfr view method-timing recording.jfr` |
| `jdk.MethodTrace` | Start time, duration, event thread, stack trace, method | `jfr view jdk.MethodTrace recording.jfr` |

`jdk.MethodTiming` ghi thống kê theo method được lọc; `jdk.MethodTrace` ghi các invocation riêng. Hãy bắt đầu bằng timing để xác định method đáng nghi, rồi dùng trace để kiểm tra một số lời gọi cụ thể. Nếu trace mọi method của ứng dụng trong thời gian dài, recording có thể tăng nhanh về dung lượng và chi phí xử lý.

## 3. Lọc method cần đo hoặc truy vết

### 3.1. Các dạng filter trong JDK 25

JFR cho phép chỉ định mục tiêu theo nhiều dạng:

| Dạng | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Tên class | `com.acme.orders.OrderService` | Các method của class |
| Class và method | `com.acme.orders.OrderService::placeOrder` | Method cụ thể của class |
| Tên method | `::close` | Method cùng tên ở các class phù hợp |
| Constructor | `com.acme.orders.OrderService::<init>` | Constructor của class |
| Static initializer | `com.acme.orders.OrderService::<clinit>` | Khối khởi tạo static |
| Annotation | `@jakarta.ws.rs.GET` | Method được đánh dấu annotation |
| Nhiều mục tiêu | `A::save;B::load` | Các filter được ngăn bằng dấu chấm phẩy |

Filter có thể được dùng cho `jdk.MethodTiming` và `jdk.MethodTrace`. Tên class/method cần khớp với tên thực tế của bytecode đang chạy, gồm cả tên package đầy đủ.

Ví dụ, với:

~~~java
package com.acme.orders;

public class OrderService {
    public Order placeOrder(Command command) { /* ... */ }
    public void cancelOrder(long id) { /* ... */ }
}
~~~

Filter chọn riêng `placeOrder`:

~~~text
com.acme.orders.OrderService::placeOrder
~~~

Filter chọn hai method:

~~~text
com.acme.orders.OrderService::placeOrder;com.acme.orders.OrderService::cancelOrder
~~~

Dấu `;` thường là ký tự phân tách lệnh trong shell. Khi truyền filter có nhiều mục tiêu, hãy đặt toàn bộ giá trị trong dấu nháy phù hợp với shell đang dùng.

### 3.2. Lọc theo annotation

Nếu framework đánh dấu endpoint bằng annotation, có thể chọn theo annotation thay vì liệt kê từng method:

~~~text
@jakarta.ws.rs.GET
~~~

Ví dụ này phù hợp với method endpoint được đánh dấu `@GET`. Chỉ dùng annotation mà method thực sự có trong ứng dụng. Với annotation class-level hoặc method-level của framework khác, hãy kiểm tra hành vi filter trên JDK 25 và bản ghi thử trước khi đưa vào quy trình production.

Lợi ích là khi thêm endpoint mới có cùng annotation, filter có thể bao phủ endpoint mới mà không phải cập nhật danh sách method. Đổi lại, số method được đo có thể tăng khi ứng dụng mở rộng.

### 3.3. Vì sao nên bắt đầu bằng filter hẹp?

Giả sử ứng dụng có hàng nghìn method. Filter toàn bộ classpath sẽ làm khó việc diễn giải:

- Nhiều method framework và thư viện không liên quan xuất hiện trong kết quả.
- `jdk.MethodTrace` có thể sinh lượng event lớn.
- Dung lượng recording và chi phí phân tích tăng.
- Các method có số invocation cao nhưng thời gian rất nhỏ có thể làm loãng kết quả cần xem.

Quy trình thực tế:

1. Dùng metric ứng dụng hoặc JFR profiling để xác định endpoint/luồng nghi vấn.
2. Dùng `jdk.MethodTiming` cho một class hoặc method.
3. Chọn một vài method có average/max hoặc invocation count đáng chú ý.
4. Dùng `jdk.MethodTrace` cho các method đó trong một khoảng ngắn.
5. Mở stack trace để tìm tầng gọi, framework proxy, callback hoặc dependency.
6. Đối chiếu với event I/O, lock, GC và CPU sampling.

## 4. Đo số lần gọi và thời lượng bằng Method Timing

### 4.1. Chạy ứng dụng cùng recording

Có thể bật method timing ngay khi khởi động JVM:

~~~bash
java '-XX:StartFlightRecording:method-timing=com.acme.orders.OrderService::placeOrder,filename=order-timing.jfr,dumponexit=true' -jar app.jar
~~~

Lệnh trên:

- Bắt đầu một JFR recording khi JVM khởi chạy.
- Lọc `jdk.MethodTiming` cho `OrderService.placeOrder`.
- Ghi kết quả vào `order-timing.jfr` khi JVM thoát.
- Giữ event filter hẹp để kết quả tập trung vào method cần đo.

Với method được gọi nhiều overload, filter theo tên có thể đưa nhiều overload vào kết quả. Khi đọc báo cáo, hãy xem đầy đủ chữ ký method để không gộp nhầm các đường thực thi khác nhau.

### 4.2. Dùng report-on-exit cho một lần chạy ngắn

Khi chỉ cần một bảng thống kê ở cuối tiến trình, JDK 25 hỗ trợ `report-on-exit`:

~~~bash
java '-XX:StartFlightRecording:method-timing=::<clinit>,report-on-exit=method-timing' -jar app.jar
~~~

Ví dụ này đo các static initializer (`<clinit>`) và in báo cáo method timing khi JVM thoát. Nó hữu ích khi điều tra startup và thời gian khởi tạo class.

Báo cáo có dạng:

~~~text
Method Timing

Timed Method                              Invocations  Minimum Time  Average Time  Maximum Time
------------------------------------------------------------------------------------------------
com.acme.Config.<clinit>()                         1       4.2 ms        4.2 ms        4.2 ms
com.acme.Cache.initialize()                        1       8.1 ms        8.1 ms        8.1 ms
com.acme.orders.OrderService.placeOrder(...)      12       1.1 ms        7.8 ms       24.0 ms
~~~

Các con số trên chỉ minh họa hình thức bảng, không phải số đo thực tế.

### 4.3. Đọc invocation count

`Invocations` là số lần method khớp filter được ghi nhận trong phạm vi recording. Khi đọc cần đặt nó cạnh thời lượng và workload:

- Số lần gọi cao, thời lượng trung bình thấp: method có thể là một thao tác nhỏ nhưng xuất hiện thường xuyên.
- Số lần gọi thấp, thời lượng trung bình cao: có thể là thao tác ít xảy ra nhưng chậm.
- Số lần gọi cao, maximum cao hơn average nhiều: có thể có một số invocation bị chậm bất thường.
- Số lần gọi bằng 0 hoặc không có dòng kết quả: kiểm tra filter, event enablement, thời gian recording và việc workload có thật sự gọi method không.

Không xem invocation count là tổng số request HTTP nếu filter đặt ở một method được gọi nhiều lần trong mỗi request. Một endpoint có thể gọi repository nhiều lần, retry hoặc gọi method qua proxy; số lần gọi method không nhất thiết bằng số request.

### 4.4. Đọc minimum, average và maximum

| Cột | Cách hiểu | Câu hỏi tiếp theo |
| --- | --- | --- |
| Minimum Time | Thời lượng nhỏ nhất ước lượng trong các invocation được tổng hợp | Đường chạy nhanh nhất có thực sự đại diện? |
| Average Time | Thời lượng trung bình ước lượng | Có phù hợp với latency mục tiêu? |
| Maximum Time | Thời lượng lớn nhất ước lượng | Invocation nào tạo ra đuôi latency? |

Đây là các giá trị gần đúng. JFR có thể không xác định được minimum hoặc average khi độ phân giải đồng hồ không đủ; giá trị đó có thể bị thiếu. Không coi số liệu thời lượng có nhiều chữ số thập phân là độ chính xác tuyệt đối.

**Average không thay thế percentile.** Một method có average 5 ms nhưng maximum 400 ms có thể tạo ra vấn đề tail latency. `jdk.MethodTiming` cung cấp min/average/max, không phải phân phối percentile đầy đủ của từng invocation. Nếu cần p95/p99, dùng metric/histogram phù hợp hoặc phân tích event trace có chọn lọc.

### 4.5. Xem báo cáo từ file JFR

Sau khi recording kết thúc:

~~~bash
jfr summary order-timing.jfr
jfr view method-timing order-timing.jfr
~~~

`jfr summary` cho biết số lượng event và thông tin tổng quát về file. `jfr view method-timing` hiển thị bảng timing đã tổng hợp.

Có thể xuất event dạng text/JSON để phân tích thêm:

~~~bash
jfr print --events jdk.MethodTiming --exact order-timing.jfr
jfr print --json --events jdk.MethodTiming order-timing.jfr
~~~

Dùng `--exact` khi cần giữ độ chính xác đầy đủ của timestamp/timespan trong bản in. File `.jfr` vẫn là nguồn dữ liệu nhị phân gốc; bản in text không thay thế recording.

## 5. Truy vết từng invocation bằng Method Trace

### 5.1. Khi nào cần trace?

Method timing cho biết method nào có số lần gọi/thời lượng đáng chú ý. Nó không chỉ ra từng lần gọi bắt đầu lúc nào hoặc stack trace của từng invocation.

Dùng `jdk.MethodTrace` khi cần trả lời:

- Method được gọi từ controller, listener, scheduler hay callback nào?
- Lời gọi xảy ra trên thread nào?
- Invocation cụ thể bắt đầu lúc nào và kéo dài bao lâu?
- Call stack đi qua Spring proxy, reflection, transaction interceptor hoặc thư viện nào?
- Một method bị gọi lặp lại do retry hoặc do vòng lặp ở tầng gọi?

### 5.2. Bật Method Trace khi khởi chạy

~~~bash
java '-XX:StartFlightRecording:jdk.MethodTrace#filter=com.acme.orders.OrderService::placeOrder,filename=order-trace.jfr,dumponexit=true' -jar app.jar
~~~

Lệnh này chọn method `placeOrder` cho event `jdk.MethodTrace`. Để ghi nhiều method, dùng filter phân tách bằng dấu chấm phẩy và đặt toàn bộ giá trị trong dấu nháy.

Ví dụ:

~~~bash
java '-XX:StartFlightRecording:jdk.MethodTrace#filter=com.acme.orders.OrderService::placeOrder;com.acme.orders.PaymentService::authorize,filename=order-trace.jfr,dumponexit=true' -jar app.jar
~~~

Không trace tất cả method trong một ứng dụng lớn khi chưa có câu hỏi cụ thể. Một method có thể được gọi hàng chục nghìn lần; mỗi invocation tạo thêm event và stack trace.

### 5.3. Đọc Method Trace

Dùng view tích hợp:

~~~bash
jfr view jdk.MethodTrace order-trace.jfr
~~~

Hoặc in event chi tiết:

~~~bash
jfr print --events jdk.MethodTrace --stack-depth 20 order-trace.jfr
~~~

Một event có dạng khái quát:

~~~text
jdk.MethodTrace {
  startTime = 14:21:10.125
  duration = 43.3 ms
  eventThread = "http-nio-8080-exec-1"
  stackTrace = [
    com.acme.orders.OrderService.placeOrder(...)
    com.acme.orders.OrderController.create(...)
    ...
  ]
  method = com.acme.orders.OrderService.placeOrder(...)
}
~~~

Đây là dữ liệu minh họa. Bản ghi thật có thể hiển thị thêm frame của lambda, reflection, proxy hoặc framework.

**Cách đọc stack trace:**

1. Bắt đầu ở frame gần method được trace nhất.
2. Đi ngược lên các caller để xác định entry point.
3. Nhận diện frame framework như interceptor, proxy hoặc reflection.
4. Tìm frame thuộc mã ứng dụng đầu tiên để xác định tầng nghiệp vụ.
5. So sánh nhiều invocation để xem cùng một call path hay có nhiều đường gọi khác nhau.

Stack trace là ảnh chụp call stack gắn với event. Nó không tự giải thích vì sao method chậm; cần đối chiếu duration, event chờ I/O/lock và dữ liệu nghiệp vụ.

### 5.4. Giới hạn của Method Trace

- Trace chỉ bao gồm method khớp filter.
- Không trace method nghĩa là không có bằng chứng method đó không chạy.
- Stack depth có thể bị giới hạn khi in; tăng `--stack-depth` nếu cần thêm frame.
- Nhiều event có thể làm file lớn và tăng chi phí ghi/đọc.
- Invocation duration là elapsed time, có thể bao gồm blocking hoặc scheduling.
- Một stack trace không đại diện cho toàn bộ request nếu request đi qua nhiều thread hoặc async boundary.

Dùng trace trong một cửa sổ thời gian ngắn và tái hiện workload cần điều tra. Khi đã tìm ra call path, tắt trace hoặc thu hẹp filter.

## 6. Attach vào JVM đang chạy bằng jcmd

Không phải lúc nào cũng có thể restart production process để thêm `-XX:StartFlightRecording`. JDK 25 cho phép điều khiển JFR tại runtime qua `jcmd`.

### 6.1. Tìm PID và kiểm tra recording

~~~bash
jcmd -l
jcmd <pid> JFR.check
jcmd <pid> JFR.check verbose=true
~~~

Thay `<pid>` bằng process ID thực tế. `jcmd` cần chạy trên cùng máy với JVM và bằng effective user/group phù hợp. Dùng `JFR.check verbose=true` để xem event settings của recording đang hoạt động.

### 6.2. Bắt đầu Method Timing cho 60 giây

~~~bash
jcmd <pid> JFR.start name=order-timing settings=profile duration=60s filename=order-timing.jfr jdk.MethodTiming#filter=com.acme.orders.OrderService::placeOrder
~~~

`settings=profile` dùng cấu hình profiling đi kèm JDK. Event setting ở cuối chỉ định filter cho `jdk.MethodTiming`. Khi hết 60 giây, recording được ghi vào file.

### 6.3. Bắt đầu Method Trace ngắn

~~~bash
jcmd <pid> JFR.start name=order-trace settings=profile duration=20s filename=order-trace.jfr jdk.MethodTrace#filter=com.acme.orders.OrderService::placeOrder
~~~

Trace ngắn giúp thu được một số invocation cùng stack trace. Nếu method ít được gọi, hãy kéo dài cửa sổ theo workload thực tế, không mở trace vô hạn.

### 6.4. Dừng hoặc dump recording

Kiểm tra recording:

~~~bash
jcmd <pid> JFR.check verbose=true
~~~

Dừng và ghi file:

~~~bash
jcmd <pid> JFR.stop name=order-trace filename=order-trace.jfr
~~~

Dump dữ liệu trong khi recording vẫn tiếp tục:

~~~bash
jcmd <pid> JFR.dump name=order-timing filename=order-timing-partial.jfr
~~~

Sau đó xem file:

~~~bash
jfr summary order-trace.jfr
jfr view jdk.MethodTrace order-trace.jfr
~~~

Tên recording phải khớp với tên đã dùng khi start. Khi dùng `duration`, JVM tự kết thúc recording khi hết thời gian; khi điều tra thủ công, `JFR.stop` giúp chốt thời điểm và ghi file có kiểm soát.

### 6.5. Nếu command không được hỗ trợ

Các diagnostic command và event setting phụ thuộc JDK đang chạy. Kiểm tra:

~~~bash
jcmd <pid> help
jcmd <pid> help JFR.start
jcmd <pid> JFR.check verbose=true
jfr --help view
~~~

Nếu JVM không có event hoặc tùy chọn như mong đợi, kiểm tra `java -version`, `jcmd` cùng JDK với process và metadata event:

~~~bash
jfr metadata --events jdk.MethodTiming,jdk.MethodTrace
~~~

Không dùng `jcmd` từ JDK cũ để điều khiển một JVM JDK 25 nếu có thể tránh; dùng bộ công cụ đi kèm JDK tương ứng.

## 7. Đọc recording trong ngữ cảnh nghiệp vụ

### 7.1. Vì sao stack trace riêng lẻ chưa đủ?

Một request thường tạo ra nhiều event:

~~~text
POST /orders
  ├── OrderController.create
  ├── OrderService.placeOrder
  ├── PricingService.calculate
  ├── InventoryRepository.reserve
  ├── PaymentClient.authorize
  └── AuditService.publish
~~~

Một `jdk.MethodTrace` có thể cho thấy call stack tại một invocation. Nhưng khi xem `jdk.JavaMonitorWait` hoặc `jdk.SocketRead`, bạn có thể muốn biết event đó thuộc request nào và order nào.

JDK 25 bổ sung annotation `@Contextual` trong `jdk.jfr`. Field được đánh dấu là context được áp dụng cho các event xảy ra trên **cùng thread** từ lúc event context bắt đầu đến khi kết thúc. Khi đọc recording, công cụ có thể hiển thị trace ID hoặc order ID cùng các event liên quan.

### 7.2. Tạo event context cho request

Ví dụ JDK 25:

~~~java
import jdk.jfr.Category;
import jdk.jfr.Contextual;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("com.acme.Trace")
@Label("Request Trace")
@Category({"Application", "Tracing"})
class RequestTraceEvent extends Event {

    @Label("Trace ID")
    @Contextual
    String traceId;

    @Label("Operation")
    @Contextual
    String operation;
}
~~~

Event có duration bao quanh một thao tác:

~~~java
static void traceRequest(String traceId, String operation, Runnable action) {
    RequestTraceEvent event = new RequestTraceEvent();

    if (!event.isEnabled()) {
        action.run();
        return;
    }

    event.traceId = traceId;
    event.operation = operation;
    event.begin();

    try {
        action.run();
    } finally {
        event.end();
        if (event.shouldCommit()) {
            event.commit();
        }
    }
}
~~~

Các field `traceId` và `operation` được đặt trước `begin()`. Trong thời gian event mở, các event cùng thread có thể mang context này. `shouldCommit()` kiểm tra event có được ghi theo setting hiện tại hay không, giúp tránh công việc không cần thiết khi recording không bật hoặc event không đạt threshold.

### 7.3. Gắn order ID cho các event liên quan

~~~java
@Name("com.acme.OrderContext")
@Label("Order Context")
@Category({"Application", "Orders"})
class OrderContextEvent extends Event {

    @Label("Order ID")
    @Contextual
    long orderId;

    @Label("Payment Method")
    String paymentMethod;
}
~~~

Trong luồng xử lý đơn hàng, mở event context trong lúc thực hiện công việc:

~~~java
static void processOrder(long orderId, String paymentMethod, Runnable action) {
    OrderContextEvent event = new OrderContextEvent();

    if (!event.isEnabled()) {
        action.run();
        return;
    }

    event.orderId = orderId;
    event.paymentMethod = paymentMethod;
    event.begin();

    try {
        action.run();
    } finally {
        event.end();
        if (event.shouldCommit()) {
            event.commit();
        }
    }
}
~~~

`orderId` được đánh dấu `@Contextual`, nên có thể xuất hiện cùng các event khác trong cùng thread và khoảng thời gian. `paymentMethod` không được đánh dấu contextual; nó chỉ là payload của `OrderContextEvent`.

Khi xem một event lock contention:

~~~bash
jfr print --events jdk.JavaMonitorEnter recording.jfr
~~~

Bản in có thể hiển thị phần `Context` cùng trace ID/order ID, sau đó là thời lượng chờ, thread và stack trace. Đây là cách nối dữ liệu runtime với nghiệp vụ đang xử lý.

### 7.4. Giới hạn của @Contextual

- Context áp dụng trong cùng thread và trong thời gian event context còn mở.
- Không tự truyền qua executor, thread pool, `CompletableFuture` hoặc reactive scheduler.
- Không thay thế distributed tracing giữa nhiều process/service.
- Không nên đánh dấu quá nhiều field contextual vì parser phải theo dõi trạng thái context trong recording.
- Không đưa token, password, dữ liệu cá nhân hoặc payload nhạy cảm vào context nếu không cần thiết.

Nếu request chuyển thread, hãy thiết kế context event tương ứng tại thread thực thi hoặc dùng cơ chế truyền context phù hợp của framework. `@Contextual` không tự tạo liên kết xuyên thread.

## 8. Kết hợp method timing với các event khác

### 8.1. Method chậm do I/O

Nếu `OrderService.placeOrder` có average cao, hãy xem `jdk.SocketRead`, `jdk.SocketWrite`, `jdk.FileRead` và `jdk.FileWrite` trong cùng khoảng thời gian. JFR Java Application events thường có threshold mặc định; những lần I/O ngắn hơn ngưỡng có thể không xuất hiện.

Ví dụ:

~~~bash
jfr print --events jdk.SocketRead,jdk.SocketWrite recording.jfr
jfr print --events jdk.FileRead,jdk.FileWrite recording.jfr
~~~

Nếu method timing cao và socket read kéo dài trên cùng thread, có thể method đang chờ dịch vụ ngoài. Đừng tối ưu vòng lặp Java trước khi xác định phần thời gian nằm ở đâu.

### 8.2. Method chậm do lock contention

Xem:

~~~bash
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait recording.jfr
~~~

Các event này có thể cho biết monitor nào bị chờ, thread nào đang giữ lock và stack trace của thread chờ. Nếu event context được tạo bằng `@Contextual`, trace ID/order ID có thể giúp liên hệ lock wait với request nghiệp vụ.

### 8.3. Method chậm do CPU

Method timing đo elapsed time, không đo riêng CPU. Khi method mất nhiều thời gian nhưng không có event chờ I/O/lock tương ứng, hãy xem CPU sampling:

~~~bash
jfr view hot-methods recording.jfr
jfr print --events jdk.ExecutionSample recording.jfr
~~~

`jdk.ExecutionSample` lấy mẫu stack khi thread thực thi Java code. Nó giúp xác định nơi CPU dành nhiều thời gian, nhưng không đếm mọi lần gọi method.

JDK 25 còn có JEP 509 — JFR CPU-Time Profiling, event `jdk.CPUTimeSample` dùng để lấy mẫu CPU time và có thể tính cả thời gian thực thi native code. Tính năng này là **experimental** và chỉ hỗ trợ Linux trong JDK 25; không coi nó là API ổn định hoặc mặc định bật trên mọi nền tảng. Nếu cần dùng, hãy kiểm tra tài liệu của đúng bản JDK và ghi rõ trạng thái experimental trong kết quả.

### 8.4. Phân biệt thời lượng method và thời gian CPU

| Quan sát | Diễn giải có thể | Cần kiểm tra thêm |
| --- | --- | --- |
| MethodTiming cao, CPU samples tập trung ở method | Method có thể thực sự tiêu thụ CPU | Algorithm, allocation, JIT, call path |
| MethodTiming cao, nhiều SocketRead | Chờ mạng/dịch vụ ngoài | Remote latency, timeout, connection pool |
| MethodTiming cao, nhiều JavaMonitorWait | Tranh chấp lock | Lock owner, critical section, contention |
| MethodTiming cao, nhiều ThreadPark | Thread chờ synchronization/task | Executor queue, future/join, scheduler |
| MethodTiming cao, GC pause trùng thời điểm | Request có thể bị ảnh hưởng bởi GC | GC pause, allocation rate, heap |
| MethodTiming thấp nhưng request chậm | Bottleneck nằm ngoài method được đo hoặc ở async boundary | Toàn request timeline, downstream service |

## 9. Cấu hình recording và quản lý overhead

### 9.1. Chọn default.jfc hay profile.jfc

JDK đi kèm các cấu hình JFR phổ biến:

- `default.jfc`: thu thập dữ liệu với overhead thấp, phù hợp recording liên tục.
- `profile.jfc`: thu thập nhiều dữ liệu hơn, phù hợp điều tra ngắn hạn khi cần thêm chi tiết.

Có thể chỉ định cấu hình khi start:

~~~bash
java '-XX:StartFlightRecording:settings=profile,filename=profile.jfr,dumponexit=true' -jar app.jar
~~~

Khi cần method-specific event, thêm filter tương ứng. Không mặc định bật mọi event với threshold bằng 0 trong thời gian dài.

### 9.2. Threshold và stack trace

Event JFR có các setting như:

- `enabled`: bật/tắt event.
- `threshold`: chỉ ghi duration event khi vượt ngưỡng.
- `stackTrace`: có ghi stack trace hay không.
- `period`: chu kỳ event định kỳ.
- `throttle`: giới hạn số event trên một đơn vị thời gian.
- `filter`: chọn method cho `jdk.MethodTiming` và `jdk.MethodTrace`.

Ví dụ giảm ngưỡng cho event lock trong một recording ngắn:

~~~bash
java '-XX:StartFlightRecording:jdk.JavaMonitorEnter#threshold=2ms,filename=locks.jfr,dumponexit=true' -jar app.jar
~~~

Ngưỡng thấp thu nhiều event hơn và có thể tăng overhead/dung lượng. Chọn ngưỡng theo câu hỏi điều tra, không hạ tất cả threshold chỉ để “thu càng nhiều càng tốt”.

### 9.3. Đánh giá overhead

JFR profiling recording với cấu hình mặc định thường có overhead thấp; tuy nhiên overhead thực tế phụ thuộc event, filter, stack trace, tần suất và ứng dụng. Method tracing theo invocation có thể tạo nhiều dữ liệu hơn method timing tổng hợp.

Quy tắc vận hành:

1. Bắt đầu bằng recording ngắn, filter hẹp.
2. Theo dõi CPU, heap, file size và latency trong lúc recording.
3. So sánh với baseline không recording nếu cần đo hiệu năng chính xác.
4. Tăng số method hoặc hạ threshold từng bước.
5. Dừng recording khi đã có dữ liệu đủ trả lời câu hỏi.

Không dùng một recording bật nhiều event, trace nhiều method, stack depth rất lớn rồi xem overhead là không đáng kể.

## 10. Các lệnh jfr cần nhớ trong JDK 25

| Lệnh | Mục đích |
| --- | --- |
| `jfr summary file.jfr` | Tóm tắt số lượng event và thông tin file |
| `jfr view method-timing file.jfr` | Xem bảng method timing |
| `jfr view jdk.MethodTrace file.jfr` | Xem method trace |
| `jfr view hot-methods file.jfr` | Xem các method nổi bật theo CPU sampling |
| `jfr print --events jdk.MethodTiming file.jfr` | In event method timing |
| `jfr print --events jdk.MethodTrace --stack-depth 20 file.jfr` | In method trace với stack sâu hơn |
| `jfr metadata --events jdk.MethodTrace file.jfr` | Xem metadata event |
| `jfr print --json file.jfr` | Xuất event dạng JSON |
| `jfr print --exact file.jfr` | In timestamp/timespan với độ chính xác đầy đủ |
| `jfr scrub input.jfr output.jfr` | Loại bỏ dữ liệu nhạy cảm theo event/category/thread filter |

Ví dụ lọc recording trước khi chia sẻ:

~~~bash
jfr scrub --exclude-events jdk.InitialSystemProperty,jdk.InitialEnvironmentVariable input.jfr sanitized.jfr
~~~

Recording có thể chứa system properties, đường dẫn file, địa chỉ mạng, tên thread, trace ID hoặc dữ liệu nghiệp vụ tùy event. Trước khi gửi cho người khác, hãy xem xét dữ liệu nhạy cảm và dùng `jfr scrub` với filter phù hợp. Không mặc định file `.jfr` là vô hại chỉ vì nó là file chẩn đoán.

## 11. Quy trình điều tra từ triệu chứng tới nguyên nhân

### Bước 1 — Xác định câu hỏi

Ví dụ: API `POST /orders` chậm hơn mục tiêu. Xác định cần biết:

- Method nào được gọi nhiều?
- Method nào có elapsed time cao?
- Stack trace invocation chậm đi qua những tầng nào?
- Thời gian bị tiêu tốn trong CPU, lock, network hay GC?

### Bước 2 — Ghi một baseline recording

~~~bash
jcmd <pid> JFR.start name=orders-baseline settings=profile duration=60s filename=orders-baseline.jfr
~~~

Tái hiện workload đại diện. Không thay đổi nhiều JVM flags cùng lúc.

### Bước 3 — Xem tổng quan

~~~bash
jfr summary orders-baseline.jfr
jfr view hot-methods orders-baseline.jfr
~~~

Xác định CPU hotspots, số event, recording duration và xem có thiếu event mong đợi hay không.

### Bước 4 — Đo method timing

~~~bash
jcmd <pid> JFR.start name=orders-timing settings=profile duration=60s filename=orders-timing.jfr jdk.MethodTiming#filter=com.acme.orders.OrderService::placeOrder
~~~

Xem:

~~~bash
jfr view method-timing orders-timing.jfr
~~~

Chọn method có invocation count, average hoặc maximum đáng chú ý.

### Bước 5 — Trace một method cụ thể

~~~bash
jcmd <pid> JFR.start name=orders-trace settings=profile duration=20s filename=orders-trace.jfr jdk.MethodTrace#filter=com.acme.orders.OrderService::placeOrder
~~~

Xem stack trace:

~~~bash
jfr view jdk.MethodTrace orders-trace.jfr
~~~

Tập trung vào caller đầu tiên thuộc mã ứng dụng, thread và khoảng thời gian của invocation.

### Bước 6 — Liên hệ với event chờ

~~~bash
jfr print --events jdk.SocketRead,jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark orders-baseline.jfr
~~~

Nếu cần correlation tốt hơn, thêm `@Contextual` cho trace ID/order ID trong event context của ứng dụng.

### Bước 7 — Kiểm chứng giả thuyết

Sau khi thay đổi code/configuration:

1. Chạy lại cùng workload.
2. Dùng cùng filter và thời lượng recording.
3. So invocation count và min/average/max.
4. So CPU sampling, lock, I/O và GC.
5. Kiểm tra latency thực tế của request.
6. Lưu cả recording và metadata về JDK, JVM flags, workload.

Không kết luận chỉ từ một method timing table. Cần kiểm chứng trên request latency và workload thực tế.

## 12. Bài thực hành: điều tra API đặt hàng

**Tình huống:** API `POST /orders` có latency p95 tăng. Bạn muốn biết `OrderService.placeOrder` chậm do CPU, lock hay database/network.

### Phần A — Bắt đầu recording

1. Khởi động ứng dụng bằng JDK 25.
2. Dùng `jcmd -l` tìm PID.
3. Bắt đầu một recording `profile` trong 60 giây.
4. Gửi workload có tỷ lệ request tương tự production.
5. Dừng recording hoặc đợi hết duration.

**Đạt** khi có file `.jfr`, summary hợp lệ và workload đã được ghi nhận.

### Phần B — Đo số lần gọi và duration

1. Tạo recording mới với filter `OrderService::placeOrder`.
2. Dùng `jfr view method-timing`.
3. Ghi invocation count, minimum, average, maximum.
4. Lặp lại với `PricingService::calculate`.
5. Giải thích vì sao invocation count không nhất thiết bằng số HTTP requests.

**Đạt** khi phân biệt được thống kê tổng hợp theo method với từng invocation.

### Phần C — Trace call stack

1. Bật `jdk.MethodTrace` cho `OrderService::placeOrder` trong 20 giây.
2. Xem bằng `jfr view jdk.MethodTrace`.
3. Xác định caller/controller, proxy/interceptor và method nghiệp vụ.
4. So sánh một số invocation có duration cao và thấp.
5. Giải thích tại sao trace toàn bộ application trong thời gian dài không phù hợp.

**Đạt** khi đọc được stack trace và liên hệ đúng thread/method.

### Phần D — Thêm context nghiệp vụ

1. Tạo event `RequestTraceEvent` có `traceId` và `operation` đánh dấu `@Contextual`.
2. Bao quanh xử lý request bằng event duration.
3. Tạo event `OrderContextEvent` với `orderId` contextual.
4. Ghi một recording có `jdk.JavaMonitorEnter`.
5. Xem event lock và kiểm tra context có được hiển thị cùng event hay không.
6. Giải thích giới hạn context khi request chuyển sang thread khác.

**Đạt** khi correlation được thực hiện trong cùng thread và khoảng thời gian event.

### Phần E — Phân loại bottleneck

1. Xem `jdk.SocketRead` và `jdk.SocketWrite`.
2. Xem `jdk.JavaMonitorEnter` và `jdk.JavaMonitorWait`.
3. Xem `jdk.ThreadPark`.
4. Xem `jdk.ExecutionSample` hoặc JMC hot methods.
5. Xác định phần thời gian nằm ở CPU, I/O, lock hay GC.
6. Viết kết luận dựa trên nhiều event và request latency.

**Đạt** khi không nhầm elapsed time của method với CPU time.

## 13. Các lỗi đọc recording thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `method-timing` không có dòng | Filter sai tên class/method hoặc method không chạy trong recording | Xác minh tên đầy đủ, overload và workload |
| Invocation count thấp hơn số request | Method không được gọi một lần cho mỗi request hoặc request không nằm trong cửa sổ recording | So route, retry, batch và thời gian ghi |
| Average thấp nhưng request p99 cao | Một số invocation có tail lớn hoặc bottleneck ngoài method được chọn | Xem maximum, trace, I/O, lock và GC |
| Method trace có quá nhiều event | Filter quá rộng hoặc method được gọi rất thường xuyên | Thu hẹp filter và giảm thời lượng |
| Stack trace thiếu frame | `--stack-depth` hoặc cấu hình recording giới hạn stack | Tăng stack depth khi in hoặc cấu hình phù hợp |
| Không thấy socket/lock event | Event chưa bật, threshold quá cao hoặc thời gian chờ ngắn hơn ngưỡng | Kiểm tra event settings và điều chỉnh threshold trong recording ngắn |
| Method duration cao nhưng CPU sample thấp | Method chủ yếu chờ I/O, lock hoặc scheduler | Đọc các event thread-stalling |
| Context không xuất hiện cùng event | Context event không bao quanh event cần xem hoặc event chạy trên thread khác | Kiểm tra thời gian event, thread và `@Contextual` |
| File `.jfr` quá lớn | Event rate cao, trace rộng hoặc recording dài | Giảm filter, duration, stack trace hoặc throttle |
| JMC không mở file | File chưa hoàn tất, sai phiên bản tool hoặc file hỏng | Kiểm tra `jfr summary`, copy file hoàn chỉnh và dùng JMC tương thích |

## 14. Checklist khi đo và truy vết method

### Trước recording

- [ ] Ghi JDK vendor/version/build và JVM flags.
- [ ] Xác định câu hỏi cụ thể: invocation count, elapsed time, stack trace hay CPU.
- [ ] Chọn method/class/annotation filter hẹp.
- [ ] Chọn `default.jfc` hoặc `profile.jfc` theo nhu cầu.
- [ ] Xác định duration và vị trí lưu file.
- [ ] Chuẩn bị workload tái hiện được.

### Khi phân tích

- [ ] Xem `jfr summary` để xác nhận recording có dữ liệu.
- [ ] Dùng `jfr view method-timing` cho thống kê.
- [ ] Dùng `jfr view jdk.MethodTrace` cho invocation/stack trace.
- [ ] Phân biệt elapsed time với CPU time.
- [ ] Kiểm tra event I/O, lock, park và GC.
- [ ] Xem thread, timestamp và context nghiệp vụ.
- [ ] Không suy luận rằng event vắng mặt nghĩa là bottleneck không tồn tại.

### Trước khi chia sẻ file

- [ ] Xem xét system properties, environment variables, đường dẫn, địa chỉ mạng và payload.
- [ ] Dùng `jfr scrub` nếu cần loại dữ liệu nhạy cảm.
- [ ] Kiểm tra file đã ghi hoàn chỉnh.
- [ ] Kèm JDK version, JVM flags, workload và thời gian recording.
- [ ] Không gửi trace ID hoặc order ID nhạy cảm ra ngoài phạm vi được phép.

## 15. Câu hỏi tự đánh giá

1. JEP nào bổ sung Method Timing và Method Trace trong Java 25?
2. `jdk.MethodTiming` ghi những chỉ số nào?
3. `jdk.MethodTrace` khác Method Timing như thế nào?
4. Vì sao elapsed time không đồng nghĩa CPU time?
5. Invocation count có nhất thiết bằng số request HTTP không?
6. Filter có thể chọn method theo những cú pháp nào?
7. Khi nào nên lọc theo annotation?
8. Vì sao nên bắt đầu bằng method timing trước method trace?
9. `jfr view method-timing` và `jfr view jdk.MethodTrace` hiển thị gì?
10. Khi nào cần dùng `jfr print --stack-depth`?
11. Làm thế nào để attach recording vào JVM đang chạy bằng `jcmd`?
12. `JFR.check verbose=true` hữu ích ra sao?
13. `@Contextual` trong Java 25 có tác dụng gì?
14. Vì sao `@Contextual` không tự truyền dữ liệu qua executor hoặc thread khác?
15. Làm thế nào để liên hệ lock contention với request ID/order ID?
16. Vì sao không nên trace toàn bộ method của một ứng dụng lớn trong thời gian dài?
17. Những event nào giúp xác định method chậm do network hoặc file I/O?
18. `jdk.ExecutionSample` khác `jdk.MethodTiming` như thế nào?
19. Trạng thái của JEP 509 CPU-Time Profiling trong JDK 25 là gì?
20. Cần lưu những thông tin nào để so sánh hai recording trước/sau tối ưu?

## 16. Tài liệu tham khảo

- [OpenJDK JEP 520 — JFR Method Timing & Tracing](https://openjdk.org/jeps/520): thiết kế method timing và tracing trong JDK 25.
- [Inside Java — What's New for JFR in JDK 25](https://inside.java/2025/06/03/new-jfr-jdk25/): các thay đổi JFR, JEP 518/509/520, `report-on-exit` và `@Contextual`.
- [Inside Java — What's New in Java 25 in 2 Minutes](https://inside.java/2025/10/17/new-in-jdk-25-2-mins/): ví dụ lệnh method timing, method trace và output.
- [Java SE 25 API — Package `jdk.jfr`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/package-summary.html): filter grammar, event settings, threshold, period, stackTrace và throttle.
- [Java SE 25 API — `jdk.jfr.Contextual`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Contextual.html): ngữ nghĩa context trên cùng thread trong khoảng thời gian event.
- [Oracle JDK 25 — The `jfr` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): `print`, `view`, `summary`, `metadata`, `scrub` và các tùy chọn xuất dữ liệu.
- [Oracle JDK 25 — The `jcmd` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop` và event settings.
- [Oracle JDK 25 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-performance-issues-using-jfr.html): cách phân tích CPU, I/O, synchronization, GC và overhead của recording.
- [Oracle JDK 25 — Consolidated Release Notes](https://www.oracle.com/java/technologies/javase/25all-relnotes.html): thay đổi JFR và các event mặc định của JDK 25.

