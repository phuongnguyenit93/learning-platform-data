# Kết hợp dữ liệu phương thức với yêu cầu chậm, khóa, I/O và GC

## Mục tiêu bài học

Một request HTTP chậm không tự cho biết nguyên nhân nằm ở đoạn code nào. Nó có thể dành phần lớn thời gian trong một method xử lý nghiệp vụ, chờ database socket, chờ monitor lock, đợi thread được đánh thức hoặc bị ảnh hưởng bởi garbage collection (GC). **Java Flight Recorder (JFR)** thu thập các sự kiện của JVM trên cùng trục thời gian; từ Java 25, **JEP 520 — JFR Method Timing & Tracing** còn cho phép instrument có chọn lọc các method để ghi thời gian thực thi và stack trace của lời gọi.

Bài **Kết hợp dữ liệu phương thức với yêu cầu chậm, khóa, I/O và GC** thuộc chương **Đo và truy vết JFR** của module **JAVA_VERSION_JAVA25**. Nội dung dùng hai event chính thức trong JDK 25:

- **`jdk.MethodTiming`:** tổng hợp số lần gọi, thời gian nhỏ nhất, trung bình và lớn nhất của các method đã chọn.
- **`jdk.MethodTrace`:** ghi từng lần gọi được chọn, gồm thời điểm bắt đầu, thời lượng, thread và stack trace.

Hai event này bổ sung cho sampling, không thay thế profiler lấy mẫu, distributed tracing hoặc metrics của ứng dụng. Chúng đặc biệt hữu ích khi đã khoanh vùng một số method nghi vấn và cần bằng chứng chi tiết hơn.

Sau bài học, bạn có thể:

1. Phân biệt method timing, method tracing và execution sampling.
2. Chọn method bằng filter theo class, method, constructor hoặc annotation.
3. Bật `jdk.MethodTiming` và `jdk.MethodTrace` bằng JVM options, `jcmd`, JFC hoặc JFR API.
4. Đọc dữ liệu invocation count, min/average/max, duration và stack trace.
5. Đối chiếu method events với lock contention, socket/file I/O, thread state và GC events.
6. Phân tích một request chậm theo mốc thời gian và thread, nhận biết trường hợp thời gian chờ bị nhầm với CPU time.
7. Giới hạn instrumentation để tránh làm thay đổi đáng kể hiệu năng của hệ thống.
8. Hiểu giới hạn liên kết request ID và cách bổ sung application event khi cần tương quan nghiệp vụ.

> **Phiên bản:** JEP 520 là tính năng chính thức trong JDK 25, không cần preview flag. Các ví dụ dùng HotSpot JDK 25 và công cụ JFR đi kèm JDK. Method timing/tracing dùng bytecode instrumentation và có thể tạo overhead đáng kể; chỉ bật cho một tập method hẹp trong khoảng điều tra có kiểm soát.

## 1. Bắt đầu từ một yêu cầu chậm

Giả sử endpoint `POST /orders` có p95 tăng từ 180 ms lên 1,4 giây. Metrics cho biết latency tăng, nhưng chưa trả lời được nguyên nhân. Một request có thể đi qua:

~~~mermaid
flowchart TD
    HTTP["HTTP request<br/>POST /orders"] --> CTRL["OrderController"]
    CTRL --> SVC["OrderService.placeOrder"]
    SVC --> INV["InventoryService.reserve"]
    SVC --> DB["OrderRepository.save"]
    DB --> JDBC["JDBC / Socket I/O"]
    INV --> LOCK["Shared inventory lock"]
    GC["GC pause / GC work"] -. "có thể ảnh hưởng thời gian thực" .-> SVC
    LOCK -. "wait / contention" .-> INV
    JDBC -. "I/O duration" .-> DB
~~~

Một số giả thuyết thường gặp:

- `OrderService.placeOrder` thực hiện quá nhiều validation hoặc chuyển đổi dữ liệu.
- `InventoryService.reserve` chờ một monitor lock do nhiều request cập nhật cùng SKU.
- `OrderRepository.save` chờ socket read từ database.
- GC pause xảy ra đúng lúc request đang chạy.
- Một method ít được gọi nhưng có thời gian thực thi rất dài làm tăng tail latency.

JFR có thể giúp trả lời những câu hỏi khác nhau bằng cách kết hợp:

| Nguồn bằng chứng | Câu hỏi |
|---|---|
| MethodTiming | Method nào được gọi bao nhiêu lần, thời gian min/average/max ra sao? |
| MethodTrace | Lần gọi cụ thể bắt đầu khi nào, kéo dài bao lâu, được gọi từ stack nào? |
| ExecutionSample | Stack nào thường xuất hiện khi thread đang chạy Java code? |
| JavaMonitorEnter / ThreadPark | Thread có chờ lock hoặc park không? |
| SocketRead / SocketWrite / FileRead / FileWrite | I/O nào kéo dài và trên thread nào? |
| GarbageCollection / GCPhasePause | Có GC event hoặc pause nào trùng cửa sổ request chậm? |
| Custom application event | Request hoặc operation nghiệp vụ nào đang được đo? |

**Không bắt đầu bằng cách instrument toàn bộ ứng dụng.** Trước tiên dùng metrics, trace hoặc JFR sampling để khoanh vùng endpoint, module và một số method nghi vấn. Sau đó mới dùng JEP 520 để đo hoặc truy vết có chọn lọc.

## 2. JEP 520 trong Java 25

JEP 520 bổ sung hai JFR event dùng bytecode instrumentation:

| Event | Nội dung | Phù hợp khi |
|---|---|---|
| `jdk.MethodTiming` | Số invocation và thống kê thời gian theo method trong từng chu kỳ phát event | Cần số liệu tổng hợp cho một nhóm method đã chọn |
| `jdk.MethodTrace` | Mỗi invocation được chọn tạo event riêng, có start time, duration, thread và stack trace | Cần điều tra một lần gọi chậm hoặc tìm caller |

JFR instrument bytecode của các method phù hợp filter để ghi nhận thời điểm vào/ra. Việc này được JVM thực hiện, không yêu cầu sửa thân method đang được đo hoặc cài Java agent bên ngoài.

### 2.1. MethodTiming: thống kê tổng hợp

`jdk.MethodTiming` duy trì thống kê cho từng method được chọn. Một event summary có thể chứa:

- `method`: tên method.
- `startTime`: thời điểm phát summary.
- `invocations`: số lần gọi được tính trong khoảng tổng hợp.
- `minimum`: thời lượng nhỏ nhất.
- `average`: thời lượng trung bình.
- `maximum`: thời lượng lớn nhất.

Event được phát theo setting `period`. Có thể điều chỉnh chu kỳ tổng hợp trong cấu hình JFR; hãy kiểm tra giá trị đang dùng thay vì giả định mọi recording có cùng khoảng phát.

Ví dụ kết quả tổng hợp minh họa:

~~~text
Timed Method                              Invocations  Minimum Time  Average Time  Maximum Time
----------------------------------------  -----------  ------------  ------------  ------------
OrderService.placeOrder                         1250       4.2 ms       18.7 ms      142.0 ms
InventoryService.reserve                        1250       0.1 ms        8.4 ms      118.0 ms
OrderRepository.save                            1250       2.0 ms       12.3 ms       90.0 ms
~~~

Các số trên chỉ minh họa cách đọc. Nếu `InventoryService.reserve` có maximum cao nhưng average thấp, có thể một số ít request gặp contention hoặc chờ I/O. Cần xem thêm MethodTrace và các event khác để xác định nguyên nhân.

**Giới hạn:** MethodTiming là dữ liệu tổng hợp theo method, không phải một record riêng cho từng request. Không thể lấy average của một method rồi kết luận chính xác thời gian của một HTTP request cụ thể.

### 2.2. MethodTrace: chi tiết từng invocation

`jdk.MethodTrace` ghi một event cho mỗi lần gọi method phù hợp filter. Event có thể chứa:

- `startTime`: thời điểm method được gọi.
- `duration`: thời gian thực đã trôi qua trong invocation.
- `method`: method được instrument.
- `eventThread`: thread thực hiện lời gọi.
- `stackTrace`: call stack cho biết đường đi tới method.

Ví dụ:

~~~text
jdk.MethodTrace {
  startTime = 14:23:01.125
  duration = 184.2 ms
  method = com.example.orders.InventoryService.reserve()
  eventThread = "http-nio-8080-exec-12"
  stackTrace = [
    com.example.orders.OrderService.placeOrder(...)
    com.example.orders.OrderController.create(...)
    ...
  ]
}
~~~

MethodTrace hữu ích khi cần biết **lần gọi nào** bị chậm và caller nào dẫn tới nó. Tuy nhiên, event được ghi cho từng invocation và có stack trace nên thường tốn chi phí hơn MethodTiming.

### 2.3. Khác biệt với sampling

| Tiêu chí | Execution sampling | MethodTiming | MethodTrace |
|---|---|---|---|
| Cách thu thập | Lấy mẫu stack theo thời điểm | Instrument method được chọn, tổng hợp invocation | Instrument method được chọn, ghi từng invocation |
| Bao phủ lời gọi | Thống kê, có thể bỏ lỡ method ngắn/hiếm | Đếm các invocation phù hợp filter | Ghi từng invocation phù hợp filter |
| Stack trace | Stack sample tại thời điểm lấy mẫu | Không nhằm ghi stack cho từng lần gọi | Có stack trace của invocation |
| Dữ liệu thời gian | Tỷ lệ sample, không phải duration từng lần gọi | Min/average/max tổng hợp | Duration từng invocation |
| Overhead | Thường phù hợp quan sát rộng | Tăng theo số method và tần suất gọi | Có thể cao do event và stack cho mỗi lần gọi |
| Phạm vi sử dụng | Tìm vùng nghi vấn | Đo có mục tiêu | Điều tra sâu một số lời gọi |

**Chiến lược hiệu quả:** dùng sampling để tìm hotspot, MethodTiming để so sánh các method nghi vấn, sau đó MethodTrace để điều tra một vài method cụ thể. Không dùng MethodTrace như một profiler tổng quát chạy liên tục trên hàng trăm method nóng.

## 3. Chọn method bằng filter

JFR hỗ trợ filter theo class, method, constructor và annotation. Filter không phải regex tổng quát; hãy dùng đúng grammar được JDK 25 công bố.

| Dạng filter | Ví dụ | Ý nghĩa |
|---|---|---|
| Tên class | `com.example.OrderService` | Chọn các method instrument được trong class |
| Class và method | `com.example.OrderService::placeOrder` | Chọn method cụ thể |
| Method không chỉ class | `::close` | Chọn method có tên đó ở các class phù hợp |
| Constructor | `com.example.Connection::<init>` | Chọn constructor của class |
| Static initializer | `::<clinit>` | Chọn static initializer |
| Annotation | `@com.example.Profiled` | Chọn class/method được gắn annotation |
| Nhiều target | `A::method;B::method` | Kết hợp nhiều filter |

Ví dụ filter cho một service:

~~~text
com.example.orders.OrderService::placeOrder
~~~

Ví dụ theo dõi method tạo và đóng file descriptor:

~~~text
java.io.FileDescriptor::<init>;java.io.FileDescriptor::close
~~~

Các filter được phân tách bằng dấu chấm phẩy. Khi truyền trên shell, hãy quote toàn bộ JVM option để dấu chấm phẩy không bị shell hiểu là dấu kết thúc câu lệnh.

### 3.1. Filter theo class

Khi chỉ rõ class:

~~~text
com.example.orders.OrderService
~~~

JFR có thể instrument các method đủ điều kiện trong class. Điều này tiện khi chưa biết method nào trong class đang tốn thời gian, nhưng có thể tạo lượng instrumentation lớn nếu class có nhiều method hoặc được gọi thường xuyên.

Hãy bắt đầu với một method cụ thể. Chỉ mở rộng ra cả class khi đã kiểm tra số method và overhead trong môi trường test.

### 3.2. Filter theo annotation

Có thể đánh dấu method cần quan sát bằng annotation có retention runtime:

~~~java
package com.example.observability;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
public @interface ProfiledOperation {
}
~~~

Áp dụng:

~~~java
package com.example.orders;

import com.example.observability.ProfiledOperation;

public class OrderService {

    @ProfiledOperation
    public void placeOrder(CreateOrder command) {
        // Logic tạo đơn.
    }
}
~~~

Sau đó dùng filter:

~~~text
@com.example.observability.ProfiledOperation
~~~

Ưu điểm là có thể bật instrumentation cho các method đã được nhóm phát triển đánh dấu mà không thêm mã đo thời gian vào từng method. Annotation chỉ là metadata chọn method; nó không tự tạo recording và không tự gắn request ID vào event.

### 3.3. Giới hạn của filter

- Không có wildcard tùy ý như `com.example.*`.
- Không chỉ định overload bằng danh sách kiểu tham số trong filter grammar.
- Nếu tên method bị overload, filter theo tên có thể áp dụng cho các overload phù hợp trong class.
- Các method không có bytecode để instrument, như abstract hoặc native method, không thuộc phạm vi đo này.
- Không dùng filter quá rộng cho package JDK hoặc chính nội bộ JFR.

Khi filter không khớp, kiểm tra tên class/method thực tế, class loader, annotation retention và event setting trước khi kết luận JFR không hoạt động.

## 4. Bật MethodTiming khi khởi chạy JVM

Java 25 hỗ trợ option cấu hình `method-timing` trong JFR recording. Ví dụ:

~~~bash
java '-XX:StartFlightRecording:method-timing=com.example.orders.OrderService::placeOrder,filename=method-timing.jfr,duration=2m' -jar app.jar
~~~

Lệnh này yêu cầu JFR tổng hợp timing cho method được chọn trong khoảng recording hai phút. Sau khi recording kết thúc, xem kết quả:

~~~bash
jfr view method-timing method-timing.jfr
~~~

Để đo nhiều method:

~~~bash
java '-XX:StartFlightRecording:method-timing=com.example.orders.OrderService::placeOrder;com.example.inventory.InventoryService::reserve,filename=service-timing.jfr,duration=2m' -jar app.jar
~~~

Trong Bash, PowerShell và CI runner, quote option để giữ dấu chấm phẩy bên trong filter. Nếu dùng file JFC, có thể cấu hình event `jdk.MethodTiming` với `enabled`, `filter` và `period`.

### 4.1. Đặt chu kỳ phát summary

MethodTiming tổng hợp dữ liệu rồi phát summary theo setting `period`. Ví dụ cấu hình trực tiếp:

~~~bash
java '-XX:StartFlightRecording:method-timing=com.example.orders.OrderService::placeOrder,jdk.MethodTiming#period=10s,filename=method-timing.jfr,duration=2m' -jar app.jar
~~~

Giá trị `10s` là chu kỳ phát summary, không phải thời gian method được phép chạy. Nếu chu kỳ quá dài, một summary có thể gộp nhiều giai đoạn workload; nếu quá ngắn, có thể tạo thêm event summary. Chọn chu kỳ dựa trên mục tiêu quan sát và kiểm tra lại setting trong recording.

### 4.2. Dùng annotation filter

~~~bash
java '-XX:StartFlightRecording:method-timing=@com.example.observability.ProfiledOperation,filename=profiled-methods.jfr,duration=3m' -jar app.jar
~~~

JFR chọn các class/method được đánh dấu bởi annotation phù hợp. Hãy chắc rằng annotation có runtime retention và đã được nạp bởi ứng dụng.

## 5. Bật MethodTrace để xem từng lời gọi

Để truy vết một method:

~~~bash
java '-XX:StartFlightRecording:method-trace=com.example.orders.OrderService::placeOrder,filename=method-trace.jfr,duration=60s' -jar app.jar
~~~

Xem event:

~~~bash
jfr view jdk.MethodTrace method-trace.jfr
~~~

Hoặc in các event:

~~~bash
jfr print --events jdk.MethodTrace method-trace.jfr
~~~

MethodTrace tạo event cho từng invocation phù hợp. Nếu method chạy hàng chục nghìn lần mỗi giây, file recording có thể lớn nhanh và overhead có thể ảnh hưởng kết quả đo.

### 5.1. Chỉ ghi lời gọi vượt ngưỡng

Để giảm dữ liệu, dùng threshold cho event MethodTrace:

~~~bash
java '-XX:StartFlightRecording:settings=profile,jdk.MethodTrace#filter=com.example.orders.OrderService::placeOrder,jdk.MethodTrace#threshold=100ms,filename=slow-methods.jfr,duration=2m' -jar app.jar
~~~

Threshold lọc theo duration của event. Trong ví dụ, chỉ các lần gọi đủ dài theo ngưỡng mới được ghi. Đây là cách tập trung vào tail calls mà không phải giữ mọi invocation trong file.

Ngưỡng phải dựa trên latency thực tế. Nếu đặt quá cao, các lời gọi chậm vừa phải sẽ bị bỏ qua; nếu quá thấp, số event có thể tăng mạnh.

### 5.2. Chọn MethodTiming hay MethodTrace?

| Câu hỏi điều tra | Chọn |
|---|---|
| Method này được gọi bao nhiêu lần? | MethodTiming |
| Thời gian trung bình và cực đại là bao nhiêu? | MethodTiming |
| Lần gọi chậm cụ thể bắt đầu khi nào? | MethodTrace |
| Ai gọi method chậm đó? | MethodTrace |
| Có một số ít invocation hiếm gây lỗi? | MethodTrace với filter hẹp |
| Cần thống kê nhiều method nhưng overhead hạn chế hơn trace | MethodTiming |
| Cần quan sát rộng toàn bộ ứng dụng | Bắt đầu bằng sampling/metrics |

Không bật cả hai event cho nhiều method chỉ vì có thể làm được. Chọn event theo câu hỏi cần trả lời.

## 6. Điều khiển recording bằng jcmd khi JVM đang chạy

Không nhất thiết phải restart service để bắt đầu một recording điều tra. JFR có thể được điều khiển qua `jcmd`:

~~~bash
jcmd -l
jcmd 12345 JFR.start name=OrderMethodTiming settings=profile method-timing=com.example.orders.OrderService::placeOrder duration=2m
~~~

Thay `12345` bằng PID của JVM. Khi recording hoàn tất, dump dữ liệu:

~~~bash
jcmd 12345 JFR.dump name=OrderMethodTiming filename=/tmp/order-method-timing.jfr
~~~

Với MethodTrace:

~~~bash
jcmd 12345 JFR.start name=OrderMethodTrace settings=profile method-trace=com.example.orders.OrderService::placeOrder duration=60s
~~~

Sau đó:

~~~bash
jcmd 12345 JFR.dump name=OrderMethodTrace filename=/tmp/order-method-trace.jfr
~~~

Kiểm tra recording đang chạy:

~~~bash
jcmd 12345 JFR.check verbose=true
~~~

`jcmd` phải chạy trên cùng máy hoặc trong môi trường process namespace thích hợp, với quyền user phù hợp. Trong container/Kubernetes, cần truy cập đúng PID namespace và bảo đảm công cụ tương thích với JDK của process.

### 6.1. Lưu ý khi dùng nhiều recording

JFR có thể chạy nhiều recording đồng thời. Các filter được áp dụng có thể được kết hợp giữa những recording hoạt động cùng lúc. Điều này có nghĩa một method có thể được instrument bởi nhiều recording; chi phí tổng cộng sẽ phụ thuộc vào tập filter đang có hiệu lực.

Trước khi mở recording thứ hai, kiểm tra các recording hiện hành:

~~~bash
jcmd 12345 JFR.check
~~~

Kết thúc recording sau khi lấy đủ dữ liệu:

~~~bash
jcmd 12345 JFR.stop name=OrderMethodTrace filename=/tmp/order-method-trace.jfr
~~~

Đừng để recording trace chuyên sâu chạy mãi sau khi sự cố đã được xử lý.

## 7. Cấu hình bằng file JFC

Trong hệ thống cần tái lập quy trình điều tra, lưu filter vào JFC để review và version control.

Ví dụ `orders-method-timing.jfc`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration version="2.0" label="Orders Method Timing">
  <event name="jdk.MethodTiming">
    <setting name="enabled">true</setting>
    <setting name="period">10 s</setting>
    <setting name="filter">
      com.example.orders.OrderService::placeOrder;
      com.example.inventory.InventoryService::reserve
    </setting>
  </event>
</configuration>
~~~

Chạy:

~~~bash
java '-XX:StartFlightRecording:settings=orders-method-timing.jfc,filename=orders-timing.jfr,duration=3m' -jar app.jar
~~~

Ví dụ `orders-method-trace.jfc`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration version="2.0" label="Orders Method Trace">
  <event name="jdk.MethodTrace">
    <setting name="enabled">true</setting>
    <setting name="threshold">100 ms</setting>
    <setting name="stackTrace">true</setting>
    <setting name="filter">
      com.example.orders.OrderService::placeOrder;
      com.example.inventory.InventoryService::reserve
    </setting>
  </event>
</configuration>
~~~

Không ghi đè `default.jfc` hoặc `profile.jfc` đi kèm JDK. Tạo file tùy chỉnh riêng, bắt đầu từ một cấu hình phù hợp nếu cần thêm event lock, I/O hoặc GC.

## 8. Dùng JFR API để cấu hình có lập trình

Khi một integration test hoặc diagnostic tool cần quản lý recording, có thể dùng `jdk.jfr.Recording`.

~~~java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Recording;

public final class MethodRecordingExample {

    public static void main(String[] args) throws Exception {
        try (Recording recording = new Recording()) {
            recording.setName("OrdersMethodDiagnostics");
            recording.setToDisk(true);
            recording.setMaxAge(Duration.ofMinutes(5));
            recording.setMaxSize(256L * 1024 * 1024);

            recording.enable("jdk.MethodTiming")
                    .with("filter",
                            "com.example.orders.OrderService::placeOrder")
                    .withPeriod(Duration.ofSeconds(10));

            recording.enable("jdk.MethodTrace")
                    .with("filter",
                            "com.example.inventory.InventoryService::reserve")
                    .withThreshold(Duration.ofMillis(100))
                    .withStackTrace();

            recording.start();

            runRepresentativeWorkload();

            recording.stop();
            recording.dump(Path.of("orders-methods.jfr"));
        }
    }

    private static void runRepresentativeWorkload() {
        // Gọi workload của ứng dụng trong môi trường kiểm thử.
    }
}
~~~

Ví dụ minh họa cách bật hai event trong một recording:

- MethodTiming tổng hợp `OrderService.placeOrder` mỗi 10 giây.
- MethodTrace ghi những invocation `InventoryService.reserve` vượt threshold 100 ms và có stack trace.

Nếu project dùng JPMS, module chứa code cần khai báo:

~~~java
module com.example.diagnostics {
    requires jdk.jfr;
}
~~~

Không dùng recording API để instrument mọi method ở mỗi lần chạy ứng dụng. Hãy giữ filter hẹp và giới hạn recording duration/retention.

## 9. Đối chiếu method events với lock contention

Một method có duration 300 ms không có nghĩa CPU đã chạy 300 ms. Method có thể dành phần lớn thời gian chờ monitor lock.

JFR có event `jdk.JavaMonitorEnter` ghi nhận tình huống thread chờ monitor. Khi nghi contention:

1. Dùng MethodTiming để xác định method có maximum/average cao.
2. Dùng MethodTrace cho method nghi vấn, đặt threshold phù hợp.
3. Bật event lock liên quan trong cùng recording.
4. Đối chiếu timestamp, event thread và stack trace.
5. Xác định object monitor và code path đang giữ lock nếu dữ liệu event cung cấp.

Ví dụ recording:

~~~bash
java '-XX:StartFlightRecording:settings=profile,jdk.MethodTiming#filter=com.example.inventory.InventoryService::reserve,jdk.MethodTrace#filter=com.example.inventory.InventoryService::reserve,jdk.MethodTrace#threshold=50ms,filename=inventory-lock.jfr,duration=2m' -jar app.jar
~~~

Nếu cần bật event monitor cụ thể, kiểm tra setting của JDK đang chạy và cấu hình:

~~~text
jdk.JavaMonitorEnter#enabled=true
~~~

### 9.1. Cách diễn giải

Giả sử MethodTrace ghi:

- `InventoryService.reserve`: 280 ms trên thread `http-nio-8080-exec-12`.
- Cùng thread có event monitor enter kéo dài trong phần lớn cửa sổ đó.
- Stack cho thấy request đi qua `OrderService.placeOrder`.

Đây là bằng chứng hỗ trợ giả thuyết contention. Cần xác định lock owner, vùng critical section và số thread cạnh tranh trước khi thay đổi code.

Không kết luận mọi method dài đều do lock. Nếu không có monitor event, method vẫn có thể chờ socket, thread park, semaphore hoặc service bên ngoài.

## 10. Đối chiếu với socket và file I/O

Database query hoặc remote call thường xuất hiện dưới dạng socket I/O ở thread thực thi. MethodTrace giúp thấy method nào bao quanh thao tác đó; event socket giúp xác định thời lượng I/O.

Các event thường dùng:

- `jdk.SocketRead`
- `jdk.SocketWrite`
- `jdk.FileRead`
- `jdk.FileWrite`

Ví dụ cấu hình threshold để tập trung I/O dài:

~~~bash
java '-XX:StartFlightRecording:settings=profile,jdk.SocketRead#threshold=20ms,jdk.SocketWrite#threshold=20ms,jdk.MethodTrace#filter=com.example.orders.OrderRepository::save,jdk.MethodTrace#threshold=50ms,filename=orders-io.jfr,duration=2m' -jar app.jar
~~~

Sau đó xem:

~~~bash
jfr view jdk.MethodTrace orders-io.jfr
jfr view jdk.SocketRead orders-io.jfr
jfr view jdk.SocketWrite orders-io.jfr
~~~

Tên view có thể được kiểm tra bằng:

~~~bash
jfr help view
jfr view all-views orders-io.jfr
~~~

### 10.1. Phân biệt method duration và socket duration

Ví dụ một method repository kéo dài 220 ms, trong khi socket read kéo dài 190 ms trên cùng thread và khoảng thời gian:

- Phần lớn thời gian method có thể nằm trong chờ database response.
- Không nên tối ưu vòng lặp Java bên trong method nếu nó chỉ chiếm vài mili giây.
- Kiểm tra query plan, network, connection pool, database load và timeout.

Method duration là thời gian thực đã trôi qua trong invocation, có thể bao gồm thời gian chờ I/O và lock. Nó không phải CPU time thuần.

## 11. Đối chiếu với garbage collection

GC có thể ảnh hưởng đến thời gian phản hồi của request, đặc biệt khi có stop-the-world pause. Trong cùng recording, có thể xem:

- `jdk.GarbageCollection`
- `jdk.GCPhasePause` và các event phase tương ứng nếu có trong JDK/GC đang dùng.
- `jdk.GCHeapSummary`
- Allocation events và các sự kiện liên quan đến object lifetime.

Ví dụ:

~~~bash
java '-XX:StartFlightRecording:settings=profile,jdk.MethodTrace#filter=com.example.orders.OrderService::placeOrder,jdk.MethodTrace#threshold=100ms,filename=orders-gc.jfr,duration=3m' -jar app.jar
~~~

Trong JMC hoặc `jfr view`, đối chiếu timeline:

1. MethodTrace của request chậm bắt đầu và kết thúc lúc nào?
2. Có GC pause nào trùng với khoảng thời gian đó?
3. Có allocation pressure tăng trước GC không?
4. Pause có đủ dài để giải thích phần lớn latency tăng không?
5. Có nhiều request khác bị ảnh hưởng cùng cửa sổ không?

Một GC event xuất hiện gần thời điểm request chậm chưa đủ chứng minh GC là nguyên nhân. Cần so sánh khoảng thời gian, pause duration, thread và nhiều request cùng lúc.

### 11.1. GC pause và thời gian method

MethodTrace đo thời gian thực của invocation; nếu thread bị ảnh hưởng bởi stop-the-world pause trong khi method đang chạy, duration có thể bao gồm khoảng pause đó. Điều này giúp giải thích vì sao method có wall-clock duration lớn dù CPU work của method không nhiều.

Dùng execution sampling, GC events và allocation data để phân biệt:

- CPU-bound: thread thực sự chạy nhiều Java code.
- Wait-bound: thread chờ lock hoặc I/O.
- GC-affected: thời gian bị ảnh hưởng bởi pause hoặc GC pressure.

## 12. Ghép timeline cho một request chậm

Một quy trình điều tra thực tế có thể làm theo thứ tự:

~~~mermaid
flowchart TD
    A["Metrics/APM phát hiện p95 tăng"] --> B["Chọn cửa sổ và endpoint"]
    B --> C["JFR sampling tìm method/stack nghi vấn"]
    C --> D["MethodTiming tổng hợp các method đã chọn"]
    D --> E["MethodTrace ghi invocation chậm"]
    E --> F["Đối chiếu lock, socket/file I/O, GC"]
    F --> G["Xác định giả thuyết và kiểm tra bằng workload"]
    G --> H["Sửa nguyên nhân, benchmark lại"]
~~~

### 12.1. Kịch bản mẫu

Dashboard cho biết `POST /orders` có p95 1,2 giây. JFR ghi nhận:

| Bằng chứng | Quan sát giả định | Gợi ý |
|---|---|---|
| MethodTiming | `placeOrder` average 80 ms, max 950 ms | Có tail invocation bất thường |
| MethodTiming | `reserve` average 12 ms, max 870 ms | Method inventory đáng điều tra |
| MethodTrace | Một lần `reserve` kéo dài 820 ms | Có invocation cụ thể bị chậm |
| JavaMonitorEnter | Thread request chờ monitor 760 ms | Có khả năng contention |
| SocketRead | Không có socket read dài tương ứng | Database không phải giả thuyết ưu tiên |
| GCPhasePause | Không có pause trùng cửa sổ | GC không giải thích được phần lớn delay |

Đây là dữ liệu minh họa. Nếu các event cho thấy method chờ monitor, bước tiếp theo là kiểm tra critical section, object lock, số thread cạnh tranh và thời gian giữ lock.

### 12.2. Không ghép nhầm aggregate với một request

MethodTiming tổng hợp nhiều invocation theo method và chu kỳ phát. Nó không lưu request ID và không cung cấp từng invocation riêng. Một request chậm có thể bị che bởi average của hàng nghìn request nhanh.

Dùng MethodTiming để phát hiện method đáng chú ý, rồi dùng MethodTrace có threshold để xem từng invocation. Để xác định request nghiệp vụ cụ thể, cần đối chiếu thêm application trace/log hoặc custom JFR event có correlation ID đã được kiểm soát.

## 13. Tương quan với request ID và tracing

JFR MethodTrace cung cấp event thread, start time, duration và stack trace, nhưng **không tự ghi HTTP request ID, method arguments hay instance fields**. Không thể giả định JFR tự biết một invocation thuộc request nào trong hệ thống.

Có ba cách tiếp cận:

1. Dùng timestamp, thread name/ID và stack trace để khoanh vùng nếu request xử lý đồng bộ trên thread đó.
2. Đối chiếu với distributed trace hoặc structured logs có request/correlation ID.
3. Tạo application-specific JFR event chứa một correlation ID đã được phép lưu, rồi so sánh timeline với MethodTrace và các event JVM.

### 13.1. Ví dụ custom JFR event cho operation

~~~java
package com.example.observability;

import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("com.example.OrderOperation")
@Label("Order Operation")
@Category({"Application", "Orders"})
public final class OrderOperationEvent extends Event {

    @Label("Request ID")
    public String requestId;

    @Label("Operation")
    public String operation;
}
~~~

Dùng event quanh thao tác:

~~~java
OrderOperationEvent event = new OrderOperationEvent();

if (!event.shouldCommit()) {
    orderService.placeOrder(command);
    return;
}

event.requestId = safeOpaqueRequestId;
event.operation = "place-order";
event.begin();

try {
    orderService.placeOrder(command);
} finally {
    event.end();
    event.commit();
}
~~~

Đây là custom event của ứng dụng, không phải event được JEP 520 tự thêm correlation ID vào. Nếu dùng JPMS, module chứa event cần `requires jdk.jfr;`.

Chỉ ghi một ID opaque đã được kiểm soát, không đưa email, token, access credential hoặc payload nhạy cảm vào recording. File JFR cần được bảo vệ và có retention policy như các artifact chẩn đoán khác.

### 13.2. Tracing vẫn có vai trò riêng

OpenTelemetry/Micrometer Tracing quản lý trace/span và propagation qua HTTP, messaging hoặc service boundary. JFR MethodTrace cung cấp chi tiết instrumentation method bên trong một JVM. Hai hệ thống bổ sung nhau:

- Trace cho biết request đi qua service nào và latency ở từng span.
- JFR cho biết method cụ thể bên trong JVM mất bao lâu và call stack ra sao.
- Custom JFR event có thể thêm correlation ID ứng dụng để nối timeline.
- JFR không thay thế distributed trace context hoặc W3C propagation.

## 14. Overhead và giới hạn instrumentation

JEP 520 không đặt mục tiêu giữ overhead của method timing/tracing dưới mức mục tiêu thường dùng cho JFR continuous recording. Bytecode instrumentation có thể ảnh hưởng đáng kể khi instrument nhiều method hoặc method rất nóng.

| Cấu hình | Chi phí tương đối | Khuyến nghị |
|---|---|---|
| Sampling rộng | Thường thấp hơn method instrumentation | Bắt đầu để tìm vùng nghi vấn |
| MethodTiming trên vài method | Thấp hơn MethodTrace nhưng tăng theo số invocation/method | Dùng để thống kê một nhóm nhỏ |
| MethodTrace trên method hiếm | Có thể chấp nhận trong cửa sổ ngắn | Dùng khi cần stack của từng lần gọi |
| MethodTrace trên method trong tight loop | Rất cao, event volume lớn | Tránh |
| Instrument cả package/JDK | Có thể gây overhead lớn và rủi ro instrumentation recursion | Không dùng như cấu hình mặc định |

JEP 520 nêu rõ mục tiêu không phải là duy trì overhead dưới mức 1% thường hướng tới của JFR. Hãy kiểm tra chi phí thực tế theo workload; không giả định MethodTrace miễn phí chỉ vì event được ghi bằng JFR.

### 14.1. Quy trình giảm overhead

1. Chạy sampling để tìm method nghi vấn.
2. Dùng MethodTiming trên số ít method để xác nhận thống kê.
3. Chỉ dùng MethodTrace cho một vài method và khoảng thời gian ngắn.
4. Đặt threshold để lọc invocation không đủ chậm.
5. Giới hạn duration và dung lượng recording.
6. So sánh throughput, p95/p99 và CPU trước/sau instrumentation.
7. Tắt recording ngay khi đã có bằng chứng.

### 14.2. Tránh instrument method nội bộ của JFR

JFR dùng code riêng để ghi và xử lý event. Nếu filter bao phủ những method mà quá trình instrumentation gọi ngược lại, có thể phát sinh recursion hoặc hành vi bất thường. JFR có cơ chế tránh một số trường hợp nhưng JEP ghi nhận đây là rủi ro cần lưu ý.

Không dùng filter rộng trên `jdk.jfr`, `jdk.internal` hoặc toàn bộ JDK. Nếu cần đo code thư viện, chọn method cụ thể và kiểm tra trong staging trước.

## 15. Các giới hạn của JEP 520

| Giới hạn | Hệ quả |
|---|---|
| Không ghi method arguments | Không dùng MethodTrace để xem giá trị tham số |
| Không ghi instance fields | Không thể suy ra trạng thái object đầy đủ từ event |
| Abstract/native methods không có bytecode phù hợp | Không thể instrument như method Java thông thường |
| Không phải mọi interface method đều có body | Chỉ các method có bytecode phù hợp mới có thể được chọn |
| Filter không chọn overload theo signature | Tên method overload có thể chọn nhiều overload |
| Không có wildcard tổng quát | Cần filter theo class/method/annotation |
| MethodTrace ghi mỗi invocation | Event volume và overhead có thể lớn |
| MethodTiming là aggregate | Không thay thế truy vết từng request |
| Không có request ID mặc định | Cần tracing/log/custom event để tương quan nghiệp vụ |

Nếu mục tiêu là biết method nhận tham số gì, hãy dùng tracing có instrumentation phù hợp, application logging đã redaction hoặc custom JFR event có field được chọn lọc. Không cố dùng JFR method tracing để thu thập toàn bộ object state.

## 16. Phân tích một số tình huống điển hình

### 16.1. Startup chậm do static initializer

Dùng filter `::<clinit>` để đo static initializer:

~~~bash
java '-XX:StartFlightRecording:method-timing=::<clinit>,filename=startup-methods.jfr,dumponexit=true' -jar app.jar
~~~

Xem kết quả:

~~~bash
jfr view method-timing startup-methods.jfr
~~~

Nếu một static initializer có thời gian lớn, kiểm tra nó có thực hiện classpath scan, đọc file hoặc khởi tạo client không cần thiết. Có thể cân nhắc lazy initialization nếu phù hợp với semantics ứng dụng.

### 16.2. Tìm nơi mở và đóng resource không cân bằng

Theo dõi constructor và close method:

~~~bash
java '-XX:StartFlightRecording:method-trace=java.io.FileDescriptor::<init>;java.io.FileDescriptor::close,filename=file-descriptor.jfr,duration=3m' -jar app.jar
~~~

So sánh các lần tạo và đóng theo thời gian, thread và stack trace. Đây là manh mối để tìm đường code không giải phóng resource; không chỉ dựa vào tổng số event vì có resource vẫn đang mở hợp lệ tại thời điểm dump.

### 16.3. Endpoint có latency không đồng đều

Dùng annotation hoặc class/method filter cho endpoint handler. MethodTiming cho biết endpoint nào có average/max cao; MethodTrace với threshold chỉ ghi những invocation dài. Sau đó đối chiếu database socket, lock và GC.

Nếu endpoint được gọi qua proxy/framework, method được instrument có thể là controller method hoặc service method phía dưới. Hãy chọn vị trí đo đúng câu hỏi: controller cho tổng thời gian handler; repository/service cho một phần xử lý cụ thể.

## 17. Ma trận kiểm thử nghiệm thu

| Mã | Thao tác | Kết quả mong đợi |
|---|---|---|
| M1 | Bật MethodTiming cho một method | Summary có invocation count và min/average/max |
| M2 | Bật MethodTrace cho một method | Mỗi invocation được chọn có start time, duration, thread và stack |
| M3 | Filter theo class | Các method phù hợp trong class được instrument |
| M4 | Filter theo class::method | Chỉ method có tên tương ứng được chọn |
| M5 | Filter theo annotation runtime | Các class/method được đánh dấu phù hợp được chọn |
| M6 | Filter nhiều target bằng dấu chấm phẩy | Các target được kết hợp |
| M7 | Dùng MethodTrace threshold | Invocation ngắn hơn ngưỡng bị loại theo setting |
| M8 | Dùng MethodTiming period | Summary được phát theo chu kỳ cấu hình |
| M9 | Dùng jcmd JFR.start | Recording bắt đầu trên JVM đang chạy |
| M10 | Dùng jfr view method-timing | Đọc được bảng thống kê method |
| M11 | Dùng jfr view/print MethodTrace | Đọc được từng invocation và stack |
| M12 | Đối chiếu JavaMonitorEnter | Xác định được thời gian chờ lock nếu có |
| M13 | Đối chiếu SocketRead/Write | Xác định được I/O trùng cửa sổ method chậm |
| M14 | Đối chiếu GC events | Nhận diện pause/GC pressure trùng thời gian request |
| M15 | Chạy MethodTrace trên method nóng | Đo được overhead và giới hạn event volume |
| M16 | Dùng custom application event | Liên kết timeline với request/correlation ID đã kiểm soát |

## 18. Bài thực hành tổng hợp

Bạn có một Spring Boot service với endpoint `POST /orders`. p95 latency tăng đột biến khi có nhiều request cùng cập nhật tồn kho.

Thực hiện:

1. Ghi baseline metrics và distributed trace cho endpoint.
2. Chạy JFR sampling để tìm stack nghi vấn.
3. Bật MethodTiming cho `OrderService.placeOrder` và `InventoryService.reserve`.
4. So sánh invocation count, average và maximum để xác định method có tail bất thường.
5. Bật MethodTrace cho `InventoryService.reserve` với threshold 100 ms trong recording 60 giây.
6. Đối chiếu `jdk.JavaMonitorEnter` và `jdk.ThreadPark` trong cùng recording.
7. Kiểm tra socket read/write và GC events để loại trừ I/O/GC nếu phù hợp.
8. Dùng request ID từ structured logs hoặc custom application event để khoanh vùng một số request.
9. Thay đổi logic lock hoặc vùng critical section trong môi trường kiểm thử.
10. Chạy lại cùng workload và so sánh latency, method duration, lock events và overhead instrumentation.

**Sản phẩm nghiệm thu:** lệnh JFR start/dump/stop, filter/JFC, hai file recording đã được bảo vệ, bảng method timing, một số MethodTrace mẫu, timeline lock/I/O/GC, giả thuyết nguyên nhân và benchmark trước/sau. Giải thích rõ dữ liệu nào là aggregate, dữ liệu nào là invocation cụ thể và giới hạn liên kết request ID.

## 19. Checklist vận hành production

- Bắt đầu bằng metrics, trace hoặc sampling để khoanh vùng.
- Chọn method filter cụ thể, không instrument cả package theo mặc định.
- Dùng MethodTiming cho thống kê tổng hợp và MethodTrace cho invocation cần điều tra.
- Dùng threshold cho MethodTrace nếu chỉ quan tâm lời gọi chậm.
- Giới hạn duration và retention của recording.
- Đo overhead bằng workload gần production.
- Đối chiếu timestamp/thread với lock, I/O và GC events.
- Không coi method duration là CPU time thuần.
- Không coi MethodTiming aggregate là thời gian của một request cụ thể.
- Không kỳ vọng JFR MethodTrace tự ghi request ID hoặc method arguments.
- Dùng custom JFR event hoặc tracing/logging đã kiểm soát khi cần correlation.
- Không instrument nội bộ JFR hoặc các method JDK rộng.
- Bảo vệ file JFR, giới hạn quyền truy cập và retention.
- Tắt recording chuyên sâu khi đã thu đủ bằng chứng.

## Tài liệu tham khảo chính thức

- [JEP 520 — JFR Method Timing & Tracing](https://openjdk.org/jeps/520): thiết kế hai event, bytecode instrumentation, filter grammar, mục tiêu và giới hạn.
- [Inside.java — What's New in Java 25: JFR Method Timing & Tracing](https://inside.java/2025/10/17/new-in-jdk-25-2-mins/): ví dụ chính thức về `jdk.MethodTrace`, `method-timing` và `jfr view`.
- [Oracle Java SE 25 — Package jdk.jfr](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/package-summary.html): filter grammar và event settings.
- [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:StartFlightRecording` và cách cấu hình event.
- [Oracle Java SE 25 — The jcmd Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`.
- [Oracle Java SE 25 — The jfr Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): `jfr view`, `jfr print`, `jfr summary`.
- [Oracle JDK 25 Migration Guide — Significant Changes](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): xác nhận JFR Method Timing and Tracing dùng bytecode instrumentation trong Java 25.
- [Oracle Java SE 25 — JFR Event API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Event.html): custom event, `begin`, `end`, `shouldCommit` và `commit`.
