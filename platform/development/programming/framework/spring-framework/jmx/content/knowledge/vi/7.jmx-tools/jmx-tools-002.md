# Java Mission Control và cách quan sát thông tin quản trị

## Mục tiêu

Sau bài này, bạn có thể dùng **Java Mission Control (JMC)** để kết nối đến một JVM đang chạy, khám phá các MBean qua JMX, đọc thông tin quản trị, thực hiện thao tác có kiểm soát và phân biệt công việc của **JMX Console** với **Java Flight Recorder (JFR)**. Bạn cũng biết cách xác minh việc Spring Framework đã xuất MBean đúng, xử lý vấn đề thường gặp khi MBean không hiển thị và lựa chọn công cụ phù hợp để giám sát hoặc phân tích sự cố.

## 1. Java Mission Control là gì?

Java Mission Control là bộ công cụ quan sát và phân tích ứng dụng Java. JMC có giao diện đồ họa để làm việc với JVM đang chạy và phân tích dữ liệu Java Flight Recorder. Trong các bản JMC hiện đại, công cụ được phát hành độc lập với JDK; phiên bản, gói cài đặt và các màn hình cụ thể phụ thuộc bản JMC đang dùng.

Hai nhóm chức năng cần phân biệt:

| Công cụ | Dữ liệu trọng tâm | Mục đích |
| --- | --- | --- |
| **JMX Console / MBean Browser** | Trạng thái và thao tác quản trị được JVM/MBean công bố | Xem metric hiện tại, thuộc tính MBean, operation, notification; giám sát trực tiếp |
| **Java Flight Recorder (JFR)** | Sự kiện được ghi lại trong một khoảng thời gian | Phân tích CPU, allocation, GC, thread, I/O, lock và sự kiện hiệu năng có ngữ cảnh thời gian |

JMC hỗ trợ cả hai nhu cầu nhưng không nên đồng nhất chúng: **JMX cung cấp giao diện quản trị và trạng thái**, còn **JFR cung cấp dữ liệu sự kiện để phân tích hành vi của JVM theo thời gian**. Có thể dùng JMX để xem số lượng connection hiện tại, rồi dùng JFR để tìm đoạn code tạo allocation cao hoặc thread bị chặn trong cùng giai đoạn.

Trong bài Spring Framework JMX, tập trung vào **JMX Console**, đặc biệt là MBean Browser và cách xem dữ liệu do Spring xuất.

## 2. Kiến trúc kết nối

Một phiên quan sát qua JMC có thể hình dung:

```text
+---------------------------+
| Java Mission Control      |
| - JVM Browser             |
| - JMX Console             |
| - MBean Browser           |
| - Graphs / Notifications  |
+-------------+-------------+
              |
              | JMX connection
              v
+---------------------------+
| Java process / JVM        |
| MBeanServer               |
|  + java.lang:*            |
|  + java.nio:*             |
|  + com.example:*          |
|  + Spring-exported MBeans |
+---------------------------+
```

Trong JVM, `MBeanServer` quản lý các MBean đăng ký bằng `ObjectName`. JMC là **JMX client**, sử dụng các API tương tự `MBeanServerConnection` để khám phá `ObjectName`, đọc `MBeanInfo`, lấy attribute, gọi operation và đăng ký notification listener.

Điểm cốt lõi: JMC chỉ hiển thị những gì JVM và MBean đã công bố. Nếu một Spring bean không được export thành MBean, việc mở JMC không tự biến bean đó thành đối tượng JMX có thể quản trị.

Một JVM thường có **platform MBeanServer** chứa các MBean hệ thống như `java.lang:type=Memory`, `java.lang:type=Threading`, các MBean quản lý garbage collection, và MBean do ứng dụng đăng ký. Tập MBean cụ thể phụ thuộc JVM, các module và cấu hình chạy.

## 3. Chuẩn bị môi trường

Để thực hành, cần:

- JDK được hỗ trợ để chạy ứng dụng Java/Spring.
- Java Mission Control đã cài tương thích với môi trường và JVM cần quan sát.
- Một ứng dụng Java đang chạy.
- Quyền kết nối JMX phù hợp với JVM đích.

Đối với **local JVM**, JMC thường có thể phát hiện process qua cơ chế quản lý/attach do JDK cung cấp, tùy hệ điều hành, quyền người dùng, cấu hình JVM và khả năng attach. Nếu process không xuất hiện, kiểm tra tài khoản chạy JVM, container namespace, quyền attach và JMC/JDK compatibility.

Đối với **remote JVM**, ứng dụng phải công bố endpoint quản trị cho phép kết nối từ xa. JMX qua RMI có thể yêu cầu cấu hình port registry và port RMI được tường lửa cho phép; việc có một cổng mở chưa chắc đủ nếu RMI stub quảng bá hostname/port không thể truy cập. Cần cấu hình authentication, TLS và network access thích hợp. Tránh mở remote JMX công khai ra Internet.

Một ví dụ cấu hình thử nghiệm trong mạng cô lập:

```bash
java \
  -Dcom.sun.management.jmxremote \
  -Dcom.sun.management.jmxremote.port=9010 \
  -Dcom.sun.management.jmxremote.rmi.port=9010 \
  -Djava.rmi.server.hostname=127.0.0.1 \
  -Dcom.sun.management.jmxremote.authenticate=false \
  -Dcom.sun.management.jmxremote.ssl=false \
  -jar app.jar
```

**Chỉ dùng ví dụ tắt xác thực và TLS khi thử nghiệm trên máy cá nhân hoặc môi trường được cô lập.** Không mang cấu hình `authenticate=false` và `ssl=false` vào môi trường production. Với máy ở xa, hostname và firewall phải phù hợp với tuyến kết nối thực tế; ví dụ `127.0.0.1` chỉ có ý nghĩa khi kết nối trực tiếp cùng máy hoặc qua tunnel được cấu hình đúng.

Trong ứng dụng Spring Boot, việc xuất Spring beans thành MBean có thể cần bật cài đặt JMX và cấu hình exporter tương ứng. Đừng suy luận rằng mọi bean Spring đều xuất hiện tự động trong JMC.

## 4. Kết nối local JVM bằng JMC

Quy trình tổng quát (tên menu có thể khác nhau theo phiên bản JMC):

1. Khởi chạy ứng dụng Java hoặc Spring Boot và giữ process hoạt động.
2. Mở Java Mission Control.
3. Tìm **JVM Browser** và danh sách JVM cục bộ.
4. Chọn đúng process dựa trên main class, PID hoặc tên ứng dụng.
5. Mở **JMX Console** cho JVM được chọn.
6. Truy cập khu vực **MBean Browser** hoặc tab quản lý tương đương.

Khi kết nối thành công, bạn thường thấy các nhóm MBean (domain) như `java.lang`, `java.nio`, `com.sun.management` nếu JVM hỗ trợ, và domain riêng của ứng dụng.

Nếu cần xác nhận đã chọn đúng JVM, hãy quan sát `java.lang:type=Runtime` (tên JVM, thời gian bắt đầu, uptime nếu được công bố) hoặc `java.lang:type=Memory`. Tránh kết luận chỉ từ tên process vì trên máy có thể chạy nhiều instance giống nhau.

**Mẹo:** với các JVM ngắn hạn, giữ ứng dụng sống đủ lâu để quan sát. Không bật chế độ remote JMX chỉ vì local browser chưa hiển thị process: trước tiên kiểm tra môi trường local attach.

## 5. MBean Browser tổ chức thông tin như thế nào?

Trong JMX, mỗi MBean có `ObjectName`:

```text
java.lang:type=Memory
java.lang:type=Threading
com.example.orders:type=Queue,name=PaymentQueue
```

JMC thường nhóm các MBean theo **domain** và các key property. Cách hiển thị dạng cây hoặc bộ lọc có thể khác nhau giữa các phiên bản, nhưng nguồn thông tin là metadata JMX.

Khi chọn một MBean, các phần thường quan sát được gồm:

- **Attributes:** dữ liệu trạng thái có thể đọc hoặc ghi.
- **Operations:** phương thức quản trị có thể gọi.
- **Notifications:** khả năng phát sự kiện và nơi đăng ký listener nếu công cụ hỗ trợ.
- **Metadata:** tên lớp, mô tả, chữ ký, kiểu dữ liệu và các thông tin từ `MBeanInfo`.

Ví dụ với:

```text
com.example.orders:type=Queue,name=PaymentQueue
```

một giao diện MBean có thể công bố:

```text
Attributes
  PendingCount          int       read-only
  Paused                boolean   read-write
  LastErrorCode         String    read-only

Operations
  clearCompleted()      void
  retryFailed(int max)  int

Notifications
  com.example.orders.queue.backlog
```

Những mục này chỉ xuất hiện nếu implementation và metadata thực tế công bố chúng. JMC không tự suy ra mọi method public của class là operation JMX.

## 6. Đọc attributes: quan sát trạng thái hiện tại

Attribute là thông tin dễ quan sát nhất qua JMC. Với MBean `java.lang:type=Memory`, bạn có thể xem các attribute tương tự `HeapMemoryUsage` hoặc `NonHeapMemoryUsage`.

Ví dụ `HeapMemoryUsage` được biểu diễn bằng kiểu dữ liệu có cấu trúc và thường hiển thị các trường:

```text
init
used
committed
max
```

Giá trị này đến từ `MemoryUsage` được biểu diễn qua MXBean/Open Data. Tùy JMC, bạn có thể mở rộng các trường hoặc xem dưới dạng bảng.

Để đọc dữ liệu ứng dụng, xem domain của ứng dụng và chọn attribute `PendingCount` hoặc `Paused`.

Phân biệt:

- **Read-only:** JMX cho phép đọc, không cho ghi thông qua giao diện MBean.
- **Read-write:** JMX cho phép đọc và ghi; sửa giá trị có thể ảnh hưởng hệ thống đang chạy.
- **Write-only:** có thể có về mặt hợp đồng nhưng ít phù hợp với việc quan sát trên UI.

Một attribute có thể tốn chi phí khi đọc. Nếu getter truy vấn database hoặc tính toán phức tạp, JMC poll liên tục có thể gây tải. Nên dùng getter nhanh, snapshot nhỏ và thống kê được cập nhật trước.

Một attribute cấu trúc phức tạp có thể khó hiển thị trong UI, nhất là với Standard MBean công bố kiểu domain tùy ý. MXBean/Open Data giúp tăng khả năng tương tác của các công cụ JMX.

## 7. Operations: thao tác quản trị phải được thực hiện có chủ đích

Một operation có thể thay đổi trạng thái ứng dụng, ví dụ:

```text
retryFailed(maxCount=10)
clearCompleted()
pauseConsumer()
resetMetrics()
```

JMC thường liệt kê tên operation, tham số và kiểu trả về, đồng thời cho phép gọi khi client có quyền và công cụ hỗ trợ.

Trước khi gọi operation:

1. Kiểm tra `ObjectName` đúng process/tài nguyên.
2. Đọc mô tả operation và các tham số.
3. Xác nhận tác động và quyền hạn thích hợp.
4. Ghi nhận trạng thái trước khi gọi, ví dụ `PendingCount`.
5. Chỉ gọi operation trên môi trường được phép và quan sát kết quả.

Trong JMX, `MBeanOperationInfo.getImpact()` có thể báo `INFO`, `ACTION`, `ACTION_INFO` hoặc `UNKNOWN`, nhưng đó là **metadata mô tả**, không phải biện pháp bảo mật. Operation `resetMetrics()` vẫn cần kiểm soát quyền truy cập, dù giao diện đánh dấu cách nào.

Ví dụ operation nhận tham số nguyên:

```java
connection.invoke(
    new ObjectName("com.example.orders:type=Queue,name=PaymentQueue"),
    "retryFailed",
    new Object[] { 10 },
    new String[] { "int" }
);
```

JMC thực hiện lời gọi tương đương thông qua kết nối JMX khi người dùng kích hoạt trên giao diện. Chữ ký tham số phải khớp với metadata operation.

## 8. Notifications: quan sát sự kiện từ MBean

Một MBean có thể phát notification nếu triển khai `NotificationBroadcaster` hoặc `NotificationEmitter`. Metadata `MBeanNotificationInfo` cho biết các loại notification có thể phát, ví dụ:

```text
com.example.orders.queue.backlog
com.example.orders.queue.paused
com.example.orders.queue.resumed
```

JMC hoặc công cụ JMX khác có thể cho phép đăng ký listener tới MBean và xem notification nhận được. Màn hình và khả năng cụ thể tùy phiên bản JMC.

Notification thường chứa:

- `type`: mã loại sự kiện.
- `source`: nguồn phát.
- `sequenceNumber`: số thứ tự do bên phát quản lý.
- `timeStamp`: thời điểm tạo sự kiện.
- `message`: mô tả.
- `userData`: dữ liệu bổ sung, nếu có.

**Thông tin “MBean có thể phát notification” không đồng nghĩa sẽ xuất hiện sự kiện ngay khi mở tab.** Bạn phải đăng ký nhận trước khi sự kiện được phát; JMX notification mặc định không phải lịch sử sự kiện có thể replay. Ngắt kết nối hoặc listener bị gỡ có thể khiến client bỏ lỡ thông báo.

Để debug, hãy gây ra sự kiện ở môi trường thử nghiệm sau khi listener đã được gắn, thay vì chỉ tìm một event được phát trong quá khứ.

## 9. Ví dụ Java: một MBean có thể quan sát bằng JMC

Ví dụ sau tạo một Standard MBean tên `QueueMonitor` và đăng ký trong platform MBeanServer. Các kiểu public lồng nhau giúp demo được viết trong một file duy nhất.

Lưu thành `JmcJmxDemo.java`:

```java
import java.lang.management.ManagementFactory;
import java.util.concurrent.CountDownLatch;
import javax.management.*;

public class JmcJmxDemo {
    public interface QueueMonitorMBean {
        int getPendingCount();
        boolean isPaused();
        void setPaused(boolean paused);
        void clear();
    }

    public static class QueueMonitor extends NotificationBroadcasterSupport
            implements QueueMonitorMBean {
        private volatile int pending = 42;
        private volatile boolean paused;
        private long sequence;

        @Override
        public int getPendingCount() {
            return pending;
        }

        @Override
        public boolean isPaused() {
            return paused;
        }

        @Override
        public void setPaused(boolean paused) {
            this.paused = paused;
        }

        @Override
        public void clear() {
            pending = 0;
            sendNotification(new Notification(
                "com.example.queue.cleared",
                this,
                ++sequence,
                System.currentTimeMillis(),
                "Queue was cleared"
            ));
        }

        @Override
        public MBeanNotificationInfo[] getNotificationInfo() {
            return new MBeanNotificationInfo[] {
                new MBeanNotificationInfo(
                    new String[] { "com.example.queue.cleared" },
                    Notification.class.getName(),
                    "Emitted when queue is cleared"
                )
            };
        }
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.demo:type=Queue,name=Payments"
        );
        server.registerMBean(new QueueMonitor(), name);

        System.out.println("JMX object: " + name);
        System.out.println("PID: " + ProcessHandle.current().pid());
        System.out.println("Open JMC and connect to this JVM.");
        System.out.println("Press Ctrl+C to stop.");

        CountDownLatch forever = new CountDownLatch(1);
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            try {
                if (server.isRegistered(name)) {
                    server.unregisterMBean(name);
                }
            } catch (Exception ignored) {
                // JVM is shutting down
            }
        }));
        forever.await();
    }
}
```

Chạy:

```bash
javac JmcJmxDemo.java
java JmcJmxDemo
```

Sau đó trong JMC:

1. Chọn process `JmcJmxDemo` theo PID đã in ra.
2. Mở JMX Console, chuyển đến MBean Browser.
3. Tìm domain `com.example.demo` và MBean có `type=Queue,name=Payments`.
4. Đọc `PendingCount` (ban đầu 42) và `Paused` (ban đầu false).
5. Thử sửa `Paused` trong môi trường demo nếu UI hỗ trợ.
6. Đăng ký xem notification `com.example.queue.cleared`, rồi gọi operation `clear`.
7. Kiểm tra `PendingCount` đổi về 0 và notification phát ra.

Không phải mọi phiên bản JMC đều dùng cùng tên tab hoặc cách tương tác, nhưng logic JMX và `ObjectName` là như nhau.

## 10. Quan sát MBean được Spring Framework export

Trong ứng dụng Spring, bạn có thể đánh dấu một bean quản trị với annotation:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.orders:type=OrderMonitor",
    description = "Order processing monitor"
)
public class OrderMonitor {
    private volatile boolean paused;

    @ManagedAttribute(description = "Number of pending orders")
    public int getPendingCount() {
        return 21;
    }

    @ManagedAttribute
    public boolean isPaused() {
        return paused;
    }

    @ManagedAttribute
    public void setPaused(boolean paused) {
        this.paused = paused;
    }

    @ManagedOperation(description = "Reset local statistics")
    public void resetStatistics() {
        // Reset counters
    }
}
```

`@ManagedResource` mô tả MBean, `@ManagedAttribute` chỉ định attribute được xuất và `@ManagedOperation` chỉ định operation. Bean chỉ xuất hiện trong JMC khi **Spring JMX exporter hoạt động và đăng ký thành công** trên MBeanServer mà JMC đang kết nối.

Ví dụ ứng dụng Spring Framework có thể dùng `@EnableMBeanExport`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxExportConfig {
}
```

Cấu hình auto-export ở Spring Boot có thể khác tùy phiên bản và property, vì vậy cần xác định cơ chế xuất MBean đang thực sự được bật trong ứng dụng. Không nên tạo nhiều exporter đăng ký trùng cùng `ObjectName`.

Khi JMC kết nối tới đúng JVM, tìm:

```text
com.example.orders:type=OrderMonitor
  Attributes
    PendingCount
    Paused
  Operations
    resetStatistics()
```

Nếu không thấy, kiểm tra exporter, annotation, `ObjectName` và thông báo lỗi đăng ký trong log.

## 11. JMX Console: xem biểu đồ và theo dõi diễn biến

JMC có những view hỗ trợ biểu đồ hoặc giám sát giá trị theo thời gian. Tùy phiên bản, người dùng có thể thêm các thuộc tính số vào biểu đồ, theo dõi trạng thái JVM và so sánh biến động.

Một kịch bản thực tế:

- Theo dõi `HeapMemoryUsage.used` để quan sát mức dùng heap.
- Theo dõi `ThreadCount` trong `java.lang:type=Threading`.
- Theo dõi `com.example.orders:type=OrderMonitor` / `PendingCount`.
- Khi queue tăng nhanh, xem thêm GC activity hoặc CPU của JVM.

Đừng nhầm số liệu được poll trên JMX Console với dữ liệu lịch sử bền vững. Biểu đồ live thường phản ánh khoảng thời gian client đang kết nối và thu thập. Nếu cần giám sát dài hạn, cảnh báo hoặc retention, triển khai hệ thống metrics phù hợp; JMC chủ yếu phục vụ khám phá và chẩn đoán tương tác.

Một getter JMX tính toán tốn kém khi poll có thể tăng tải ứng dụng. Hãy quan sát chi phí của thuộc tính trước khi đặt tần suất lấy mẫu cao.

## 12. Java Flight Recorder bổ sung cho JMX ra sao?

JFR ghi các event của JVM và ứng dụng để phân tích nguyên nhân hiệu năng. Tùy JDK và cấu hình, có thể tạo recording trực tiếp qua JMC hoặc qua `jcmd`:

```bash
jcmd <PID> JFR.start name=diagnostic settings=profile duration=60s filename=diagnostic.jfr
```

Thay `<PID>` bằng PID thực tế của JVM. Cần quyền và môi trường hỗ trợ attach/JFR. Các tùy chọn và event có thể thay đổi theo phiên bản JDK; kiểm tra `jcmd <PID> help JFR.start` khi cần.

Trong JMC, mở file `.jfr` để phân tích các nhóm thông tin như CPU, memory allocation, GC, thread, lock hoặc I/O nếu recording có thu thập chúng.

Ví dụ chuỗi điều tra:

1. Dùng MBean Browser xem `PendingCount` tăng và `Paused=false`.
2. Dùng JMX Console xem số thread và heap hiện tại.
3. Tạo recording JFR trong khoảng xảy ra sự cố.
4. Phân tích thread state hoặc blocking trong JFR để xác định điểm nghẽn.
5. Quay lại JMX để xác minh thay đổi trong ứng dụng sau khi khắc phục.

Đây là hai lớp dữ liệu bổ trợ: **JMX trả lời “trạng thái và điều khiển lúc này là gì?”; JFR trả lời “trong khoảng thời gian vừa qua JVM đã làm gì?”**. Không phải mọi metric JMX tự động có trong file JFR và không phải mọi JFR event đều trở thành MBean attribute.

## 13. Lỗi thường gặp khi dùng JMC

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| JVM không xuất hiện trong local JVM Browser | Khác user, container namespace, thiếu quyền attach hoặc process đã thoát | Kiểm tra PID, user chạy JVM, attach support và JDK/JMC |
| Không kết nối được remote JMX | Sai host/port, firewall, RMI hostname/port không truy cập được | Kiểm tra endpoint quản trị và network path |
| Connection bị từ chối authentication/TLS | Cấu hình bảo mật không khớp | Xác nhận credentials, certificate, giao thức |
| Không thấy MBean Spring | Exporter chưa bật, bean chưa export, tên domain khác, đăng ký lỗi | Kiểm tra `MBeanExporter`, annotation, ObjectName và log |
| Thấy MBean nhưng thiếu attribute/operation | Metadata chỉ công bố một phần, proxy/interface khác kỳ vọng | Đọc `MBeanInfo`, kiểm tra hợp đồng MBean và exporter |
| Attribute báo lỗi khi đọc | Getter ném exception, kiểu dữ liệu khó xử lý, MBean đã hủy đăng ký | Kiểm tra log, signature, lifecycle |
| Operation bị lỗi | Sai tham số, không đủ quyền, lỗi nghiệp vụ | Xác minh signature và nguyên nhân exception |
| Notification không xuất hiện | Chưa đăng ký listener hoặc sự kiện chưa phát | Gắn listener trước khi kích hoạt sự kiện |
| Biểu đồ biến mất sau ngắt kết nối | Dữ liệu live chưa được lưu thành lịch sử bền vững | Dùng metrics storage hoặc recording JFR khi phù hợp |

Nếu báo lỗi `InstanceNotFoundException`, MBean có thể đã biến mất hoặc JVM/endpoint không còn đúng. Với `NotCompliantMBeanException` khi đăng ký, cần kiểm tra interface Standard MBean/MXBean, proxy, metadata hoặc kiểu dữ liệu được công bố.

## 14. Quyền và an toàn khi quản trị qua JMX

JMX có thể cho phép thay đổi cấu hình, xóa cache, reset số liệu, tạm dừng xử lý hoặc gọi operation ảnh hưởng nghiệp vụ. Vì thế:

- Giới hạn truy cập JMX cho người hoặc hệ thống vận hành được ủy quyền.
- Với remote JMX, sử dụng xác thực, TLS và hạn chế mạng khi thích hợp; không phơi bày cổng quản trị cho Internet công khai.
- Tránh công bố secrets, access token, mật khẩu hoặc dữ liệu cá nhân qua attributes, notifications và operation results.
- Kiểm tra tham số cho operation; không xem JMX Console là hàng rào bảo mật.
- Trên production, chỉ thực hiện operation thay đổi trạng thái khi có quy trình vận hành tương ứng.
- Hạn chế attribute quá lớn và getter blocking; một client JMX có thể poll thường xuyên.
- Tách JMC client và JMX server; khi client disconnect, JVM ứng dụng vẫn chạy bình thường nếu không có tác động khác.

## 15. Bài tập thực hành

1. Chạy `JmcJmxDemo` và kết nối local bằng JMC. Ghi lại tên domain, `ObjectName` và các attribute đọc được.
2. Gọi `clear()` sau khi đăng ký notification listener. Ghi nhận `PendingCount` và notification.
3. Xuất `OrderMonitor` qua Spring JMX và so sánh giao diện hiển thị với Standard MBean thuần Java.
4. Tìm `java.lang:type=Memory` và `java.lang:type=Threading`. Chọn hai attribute phù hợp để theo dõi sự tăng tải.
5. Tạo JFR recording trong 60 giây khi ứng dụng làm việc và so sánh mục đích sử dụng dữ liệu JFR với các attribute JMX live.
6. Mô tả nguyên nhân có thể nếu JMC thấy `java.lang` nhưng không thấy domain ứng dụng; liệt kê vị trí kiểm tra trong Spring.

## 16. Câu hỏi tự kiểm tra

- Java Mission Control dùng JMX Console và Java Flight Recorder cho những nhiệm vụ khác nhau ra sao?
- `ObjectName` giúp bạn tìm đúng MBean như thế nào?
- Vì sao một Spring bean có `@ManagedResource` chưa chắc xuất hiện trong MBean Browser?
- Tại sao không nên gọi operation thay đổi trạng thái production chỉ để thử giao diện?
- Metadata `MBeanNotificationInfo` khác gì với việc đã nhận được một notification?
- Nếu remote JMX kết nối được port registry nhưng client vẫn lỗi, cần kiểm tra yếu tố RMI nào?
- Khi cần tìm nguyên nhân CPU spike theo thời gian, nên dùng JFR hay chỉ xem attributes trong JMX Console?

**Ghi nhớ:** JMC giúp khám phá và quản trị JVM qua JMX bằng JMX Console/MBean Browser, đồng thời phân tích hiệu năng theo thời gian bằng JFR. Với Spring Framework, chỉ các MBean đã export và đăng ký thành công mới hiện trong JMC. Quan sát attribute để hiểu trạng thái, cân nhắc kỹ trước khi gọi operation, và dùng JFR khi cần tìm nguyên nhân hiệu năng.