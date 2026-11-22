# JConsole là gì? Giám sát và quản lý JVM bằng giao diện đồ họa

**JConsole (Java Monitoring and Management Console)** là công cụ GUI đi kèm JDK để giám sát và quản lý ứng dụng Java đang chạy. JConsole sử dụng công nghệ **Java Management Extensions (JMX)**, kết nối tới một JVM và hiển thị dữ liệu do JVM hoặc ứng dụng công bố qua các MBean.

JConsole giúp quan sát mức dùng CPU, bộ nhớ, số lượng thread, class loading, thông tin runtime và các MBean. Công cụ phù hợp để học JMX, kiểm tra ứng dụng trong môi trường development, prototype và điều tra nhanh một số vấn đề vận hành.

## 1. JConsole giải quyết vấn đề gì?

Khi một ứng dụng Java chạy lâu, người vận hành thường cần biết:

- Heap đang dùng bao nhiêu và có xu hướng tăng hay giảm?
- Garbage Collector chạy bao nhiêu lần và mất bao nhiêu thời gian?
- Số thread hiện tại có tăng bất thường không?
- Thread nào đang bị BLOCKED hoặc WAITING?
- Có deadlock giữa các thread không?
- Có bao nhiêu class đang được nạp hoặc đã được unload?
- JVM đang chạy phiên bản nào, đã chạy bao lâu và được khởi động với những tham số nào?
- Ứng dụng có công bố metric hoặc thao tác quản trị riêng không?

JConsole gom nhiều thông tin này vào một giao diện có biểu đồ, danh sách và cây MBean. Thay vì phải tự viết chương trình đọc từng MXBean, người học có thể kết nối trực tiếp tới JVM và quan sát dữ liệu.

JConsole là công cụ monitoring và management. Nó không thay thế profiler, Java Flight Recorder (JFR), heap dump analyzer hoặc hệ thống metrics tập trung. Khi cần tìm nguyên nhân sâu của CPU cao, allocation nhiều hoặc latency bất thường, hãy kết hợp JConsole với công cụ chuyên biệt.

## 2. JConsole hoạt động dựa trên JMX

JMX (Java Management Extensions) là công nghệ chuẩn của Java để giám sát và quản lý tài nguyên. JVM cung cấp sẵn instrumentation, còn ứng dụng có thể đăng ký thêm thành phần quản trị của riêng mình.

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| JMX client | Công cụ kết nối để đọc dữ liệu hoặc gọi thao tác quản lý; JConsole là một JMX client. |
| MBean | Đối tượng công bố thuộc tính, operation và có thể có notification. |
| MBean Server | Registry trong JVM quản lý các MBean đã đăng ký. |
| Platform MXBeans | Các MBean do JVM cung cấp sẵn, ví dụ Memory, Threading, Runtime, ClassLoading và GarbageCollector. |
| JMX connector | Kênh giao tiếp giữa client và MBean Server, dùng local attach hoặc remote transport như RMI. |

JConsole đọc platform MXBeans để hiển thị những tab chuẩn. Nếu ứng dụng đăng ký custom MBean, JConsole cũng có thể hiển thị MBean đó trong tab **MBeans**.

Ví dụ, JVM có MBean `java.lang:type=Memory` để cung cấp thông tin bộ nhớ. Một ứng dụng thương mại điện tử có thể đăng ký `com.example:type=OrderService` để công bố số đơn hàng, trạng thái queue hoặc operation bảo trì.

## 3. JConsole nằm ở đâu và cách khởi động

JConsole là công cụ của JDK, executable nằm trong thư mục:

~~~text
JDK_HOME/bin/jconsole
~~~

Kiểm tra môi trường:

~~~bash
java -version
jconsole -version
jconsole -help
~~~

Nếu thư mục `JDK_HOME/bin` đã có trong `PATH`, chỉ cần chạy:

~~~bash
jconsole
~~~

Khi không truyền đối số, JConsole mở hộp thoại kết nối và liệt kê các JVM local mà tài khoản hiện tại có quyền quan sát. Chọn ứng dụng rồi nhấn **Connect**.

Có thể khởi động và kết nối thẳng tới một process:

~~~bash
jconsole 12345
~~~

Trong đó `12345` là PID của JVM. Có thể tìm PID bằng:

~~~bash
jcmd -l
~~~

Hoặc:

~~~bash
jps -l
~~~

Trên Windows, JConsole là ứng dụng GUI nên lệnh có thể không in thông tin ra cửa sổ terminal. Tài liệu trợ giúp có thể hiển thị trong cửa sổ riêng hoặc hộp thoại tùy môi trường.

## 4. Các cách kết nối tới JVM

JConsole hỗ trợ ba dạng connection thường gặp:

| Dạng kết nối | Cú pháp | Mục đích |
|---|---|---|
| Local process | `jconsole <pid>` | Kết nối JVM trên cùng máy thông qua cơ chế local attach. |
| Remote host và port | `jconsole host:port` | Kết nối JMX agent từ xa đã được bật trên JVM đích. |
| JMX Service URL | `jconsole service:jmx:...` | Kết nối một JMX connector bằng service URL đầy đủ. |

### Kết nối local

~~~bash
jconsole
~~~

Trong hộp thoại **New Connection**, chọn JVM ở danh sách Local Process. Hoặc truyền PID trực tiếp:

~~~bash
jconsole 12345
~~~

Trên Java SE hiện đại, JConsole có thể dùng Attach API để bật local management agent khi kết nối nếu JVM đích hỗ trợ dynamic attach. Thông thường không cần thêm `-Dcom.sun.management.jmxremote` khi chỉ giám sát local.

JConsole và ứng dụng cần chạy dưới cùng user ID vì cơ chế local sử dụng quyền truy cập file của hệ điều hành. Nếu JVM đã tắt attach mechanism, không hỗ trợ attach hoặc nằm trong một PID namespace khác, kết nối local có thể không thực hiện được.

### Kết nối remote

Remote monitoring cần bật JMX agent trên JVM đích. Ví dụ, JVM được cấu hình với port `7091` thì có thể mở:

~~~bash
jconsole app-server.example.com:7091
~~~

Hoặc mở JConsole không có đối số, chọn Remote Process rồi nhập host, port và credential theo cấu hình JMX agent.

### Kết nối bằng JMX Service URL

Một RMI JMX agent dùng URL thường có dạng:

~~~text
service:jmx:rmi:///jndi/rmi://app-server.example.com:7091/jmxrmi
~~~

JMX Service URL hữu ích khi kết nối tới connector tùy chỉnh hoặc hệ thống quản lý không dùng cấu hình mặc định. Nếu connector cần thư viện bên ngoài JDK, phải cung cấp connector classes cho JVM chạy JConsole.

## 5. Sáu tab chính của JConsole

Sau khi kết nối thành công, giao diện chuẩn có sáu tab:

| Tab | Nội dung |
|---|---|
| Overview | Tổng quan CPU, memory, thread count và class loading. |
| Memory | Heap, non-heap, memory pools và GC. |
| Threads | Danh sách thread, state, stack trace và deadlock detection. |
| Classes | Số class đã load, đang load và đã unload. |
| VM | Uptime, CPU time, JVM arguments, classpath và thông tin runtime. |
| MBeans | Các platform MXBeans và custom MBeans do ứng dụng đăng ký. |

Có thể kết nối nhiều JVM cùng lúc qua menu **Connection → New Connection**. Biểu tượng trạng thái kết nối ở góc trên cho phép ngắt hoặc kết nối lại tới JVM đang chạy.

## 6. Overview — nhìn nhanh sức khỏe JVM

Tab **Overview** hiển thị các biểu đồ chính trên một màn hình:

- CPU usage.
- Memory usage.
- Số thread đang hoạt động.
- Số class đã load.

Mục tiêu của tab này là giúp quan sát mối liên hệ giữa các chỉ số. Ví dụ, nếu số thread tăng cùng lúc CPU tăng, có thể cần kiểm tra thread pool hoặc workload. Nếu memory tăng liên tục, cần kiểm tra heap và GC ở tab Memory.

Overview là nơi tốt để bắt đầu điều tra, nhưng không đủ để xác định nguyên nhân gốc. Một biểu đồ tăng không tự chứng minh có memory leak hoặc CPU bottleneck.

JConsole có thể lưu dữ liệu biểu đồ thành CSV: nhấp chuột phải vào biểu đồ, chọn **Save data as...**, rồi chọn tệp đích. CSV thường có cột timestamp và các giá trị đo, thuận tiện để mở trong spreadsheet.

## 7. Memory — theo dõi heap, non-heap và GC

Tab **Memory** hiển thị mức dùng bộ nhớ theo thời gian, gồm heap, non-heap và các memory pool mà JVM cung cấp.

Các chỉ số cơ bản:

| Chỉ số | Ý nghĩa |
|---|---|
| Used | Bộ nhớ hiện đang được sử dụng. Trước GC, số liệu có thể bao gồm cả object không còn reachable nhưng chưa được thu hồi. |
| Committed | Lượng bộ nhớ JVM đã được hệ điều hành cấp hoặc bảo đảm cho JVM sử dụng. |
| Max | Mức tối đa mà memory manager có thể dùng; giá trị có thể không xác định hoặc thay đổi tùy pool. |
| GC time | Tổng thời gian JVM đã dành cho garbage collection. |
| GC count | Số lần collection của collector tương ứng. |

Heap chứa object và array được ứng dụng cấp phát. Non-heap chứa dữ liệu runtime như class metadata và JIT code cache. Các memory pool cụ thể phụ thuộc collector và phiên bản JVM.

### Perform GC

Tab Memory có nút **Perform GC** để yêu cầu JVM thực hiện garbage collection. Đây là thao tác chủ động, có thể làm ứng dụng tạm dừng hoặc tăng tải.

Không nhấn Perform GC liên tục để chữa memory leak. GC chỉ thu hồi object không còn reachable; nếu ứng dụng vẫn giữ reference tới object không cần thiết, bộ nhớ sẽ không được giải phóng. Hãy quan sát xu hướng sau GC và điều tra object retention bằng heap dump/profiler khi cần.

## 8. Threads — xem thread và phát hiện deadlock

Tab **Threads** liệt kê các thread đang hoạt động. Chọn một thread để xem:

- Tên thread.
- Trạng thái hiện tại.
- Stack trace.
- Các frame đang thực thi hoặc đang chờ.

Biểu đồ thread count thường hiển thị số thread sống và số thread sống cao nhất (peak). Bộ lọc tên thread giúp thu hẹp danh sách khi ứng dụng có nhiều thread.

JConsole còn có nút **Detect Deadlock**. Khi phát hiện chu trình deadlock, giao diện mở phần hiển thị các thread liên quan. Trên JVM hiện đại, chức năng này có thể phát hiện deadlock liên quan object monitor và ownable synchronizers như các lock trong `java.util.concurrent`.

Khi điều tra:

1. Xem thread nào đang `BLOCKED`, `WAITING` hoặc `TIMED_WAITING`.
2. Chọn thread để đọc stack trace.
3. Xem monitor hoặc synchronizer mà thread đang chờ.
4. Tìm thread đang giữ lock đó.
5. Dùng Detect Deadlock và kiểm tra owner/waiter nếu ứng dụng có dấu hiệu treo.

Một thread WAITING trong thread pool có thể hoàn toàn bình thường. Cần đọc stack và hiểu mục đích của thread trước khi kết luận ứng dụng bị kẹt.

## 9. Classes — theo dõi class loading

Tab **Classes** hiển thị số class được JVM nạp vào bộ nhớ theo thời gian.

Các số liệu thường gặp:

- Current classes loaded: số class hiện đang được nạp.
- Total classes loaded: tổng số class đã được nạp từ khi JVM khởi động, bao gồm class sau đó đã unload.
- Total classes unloaded: số class đã được gỡ khỏi JVM.

Nếu current class count tăng liên tục, có thể ứng dụng đang tạo class động, sử dụng nhiều classloader hoặc nạp module/plugin theo cách cần kiểm tra. Tuy nhiên, số class tăng không tự chứng minh có classloader leak.

Có thể bật class loading verbose output từ giao diện khi cần xem chi tiết hơn. Bật logging có thể làm tăng lượng log và overhead, vì vậy chỉ dùng trong thời gian cần thiết.

## 10. VM — thông tin về tiến trình Java

Tab **VM** cung cấp thông tin tổng quan về JVM đang được giám sát, chẳng hạn:

- Uptime.
- Process CPU time.
- Tổng thời gian JIT compilation.
- Số thread đang sống, peak và daemon thread.
- Tổng số thread đã được tạo.
- Số class hiện tại, tổng số class đã load và unload.
- Heap size, committed memory và maximum heap.
- Collector, số lần GC và tổng thời gian GC.
- VM arguments.
- Classpath và library path.

VM arguments là tham số truyền cho JVM, ví dụ `-Xms`, `-Xmx` và `-Dproperty=value`. Chúng khác với đối số truyền cho `main(String[] args)`.

Thông tin này giúp xác nhận JVM đang chạy với cấu hình nào, nhưng không thay thế việc đọc cấu hình triển khai hoặc secret manager. Không chia sẻ ảnh chụp tab VM công khai nếu nó làm lộ đường dẫn nội bộ, tên service hoặc thông tin nhạy cảm.

## 11. MBeans — xem và quản lý thành phần JMX

Tab **MBeans** hiển thị cây các MBean được đăng ký trong platform MBean Server.

Mỗi MBean có thể công bố:

- **Attributes:** dữ liệu có thể đọc, và đôi khi có thể ghi.
- **Operations:** phương thức có thể được gọi qua JMX.
- **Notifications:** sự kiện mà MBean có thể phát ra cho client đã đăng ký lắng nghe.

Một số platform MBean thường gặp:

| ObjectName | Nội dung |
|---|---|
| `java.lang:type=Memory` | Heap và non-heap memory usage. |
| `java.lang:type=Threading` | Thread count, thread information và deadlock operations. |
| `java.lang:type=Runtime` | Uptime, VM name và input arguments. |
| `java.lang:type=ClassLoading` | Class loading/unloading metrics. |
| `java.lang:type=GarbageCollector,name=...` | Thông tin về từng garbage collector. |
| `java.lang:type=OperatingSystem` | Thông tin hệ điều hành và process. |

MBean có thể cho phép thay đổi thuộc tính hoặc gọi operation. Ví dụ, custom MBean có thể cung cấp operation reset counter, đổi chế độ ứng dụng hoặc yêu cầu refresh cache. Hãy kiểm tra tác động của operation trước khi gọi, đặc biệt khi kết nối production.

## 12. Tạo custom MBean để xem trong JConsole

Ứng dụng có thể tự đăng ký MBean để công bố metric nghiệp vụ. Với Standard MBean, interface có tên `<ClassName>MBean` và class triển khai có tên tương ứng.

Ví dụ tạo một MBean theo dõi số request:

Tệp `src/com/acme/DemoMonitorMBean.java`:

~~~java
package com.acme;

public interface DemoMonitorMBean {
    long getRequestCount();
    String getStatus();
    String getLastUpdated();
    void resetRequestCount();
}
~~~

Tệp `src/com/acme/DemoMonitor.java`:

~~~java
package com.acme;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;

public class DemoMonitor implements DemoMonitorMBean {
    private final AtomicLong requestCount = new AtomicLong();
    private volatile String status = "STARTING";
    private volatile String lastUpdated = Instant.now().toString();

    public void recordRequest() {
        requestCount.incrementAndGet();
        status = "RUNNING";
        lastUpdated = Instant.now().toString();
    }

    @Override
    public long getRequestCount() {
        return requestCount.get();
    }

    @Override
    public String getStatus() {
        return status;
    }

    @Override
    public String getLastUpdated() {
        return lastUpdated;
    }

    @Override
    public void resetRequestCount() {
        requestCount.set(0);
    }
}
~~~

Tệp `src/com/acme/JConsoleDemo.java`:

~~~java
package com.acme;

import java.lang.management.ManagementFactory;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import javax.management.ObjectName;

public class JConsoleDemo {
    public static void main(String[] args) throws Exception {
        DemoMonitor monitor = new DemoMonitor();

        ManagementFactory.getPlatformMBeanServer().registerMBean(
                monitor, new ObjectName("demo:type=Monitor"));

        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor(r -> {
                    Thread thread = new Thread(r, "demo-request-generator");
                    thread.setDaemon(true);
                    return thread;
                });

        scheduler.scheduleAtFixedRate(
                monitor::recordRequest, 0, 1, TimeUnit.SECONDS);

        System.out.println("JConsoleDemo ready");
        Thread.sleep(60_000);
        scheduler.shutdownNow();
    }
}
~~~

MBean được đăng ký với ObjectName `demo:type=Monitor`. JConsole sẽ hiển thị nó dưới domain `demo` trong tab MBeans. `RequestCount`, `Status`, `LastUpdated` là các attribute; `resetRequestCount` là operation.

## 13. Biên dịch và chạy ví dụ Java 17+

Từ thư mục gốc của dự án:

~~~bash
javac --release 17 -d out \
  src/com/acme/DemoMonitorMBean.java \
  src/com/acme/DemoMonitor.java \
  src/com/acme/JConsoleDemo.java
~~~

Chạy ứng dụng:

~~~bash
java -cp out com.acme.JConsoleDemo
~~~

Stdout chính xác:

~~~text
JConsoleDemo ready
~~~

Ứng dụng đăng ký MBean, tăng request counter mỗi giây và giữ JVM hoạt động khoảng một phút.

Mở terminal thứ hai, tìm PID:

~~~bash
jcmd -l
~~~

Kết nối:

~~~bash
jconsole <pid>
~~~

Trong hộp thoại local, chọn process `com.acme.JConsoleDemo` rồi nhấn **Connect**. Mở tab **MBeans**, tìm domain `demo`, chọn `Monitor`:

- Xem `RequestCount` tăng theo thời gian.
- Xem `Status` chuyển sang `RUNNING`.
- Xem `LastUpdated`.
- Chọn operation `resetRequestCount` để đặt counter về 0 trong ví dụ thử nghiệm.

JConsole có thể kết nối local bằng Attach API và tự bật local management agent nếu JVM hỗ trợ. Không cần bật remote JMX port chỉ để chạy ví dụ local này.

## 14. Bật remote JMX cho JConsole

Để giám sát JVM từ máy khác, bật JMX agent trên JVM đích khi khởi chạy.

Ví dụ cấu hình hai cổng cố định cho RMI registry và RMI connector:

~~~bash
java \
  -Dcom.sun.management.jmxremote.port=7091 \
  -Dcom.sun.management.jmxremote.rmi.port=7092 \
  -Djava.rmi.server.hostname=monitor.example.com \
  -Dcom.sun.management.jmxremote.registry.ssl=true \
  -Dcom.sun.management.jmxremote.ssl.need.client.auth=true \
  -jar service.jar
~~~

Các thuộc tính quan trọng:

- `com.sun.management.jmxremote.port`: cổng JMX RMI registry.
- `com.sun.management.jmxremote.rmi.port`: cổng cố định cho RMI connector.
- `java.rmi.server.hostname`: địa chỉ mà RMI stub công bố; hữu ích khi máy có nhiều network interface.
- `com.sun.management.jmxremote.registry.ssl`: bật bảo vệ SSL cho RMI registry.
- `com.sun.management.jmxremote.ssl.need.client.auth`: yêu cầu client certificate.

JMX remote agent mặc định bật SSL và password authentication. Ví dụ trên vẫn cần cấu hình keystore/truststore, certificate và password/access files phù hợp với môi trường. Nếu cố định hai cổng, firewall cần cho phép kết nối tới cả hai cổng từ máy giám sát được phép.

Trên client:

~~~bash
jconsole monitor.example.com:7091
~~~

Nếu cần chỉ định JMX Service URL, có thể nhập URL trong lựa chọn Remote Process.

## 15. Bảo mật JMX và quyền readonly/readwrite

Remote JMX có thể đọc thông tin JVM và gọi operation để thay đổi ứng dụng. Nếu cấu hình không an toàn, người truy cập trái phép có thể xem dữ liệu nội bộ hoặc điều khiển tiến trình.

Các cơ chế bảo vệ:

- **Password authentication:** xác thực người dùng qua password file hoặc login module.
- **Access file:** quy định role được `readonly` hay `readwrite`.
- **SSL/TLS:** mã hóa kết nối và xác thực server.
- **SSL client certificate:** xác thực máy client khi cấu hình mutual TLS.
- **Firewall/network ACL:** chỉ cho phép máy giám sát được phê duyệt kết nối.
- **File permissions:** password file phải giới hạn quyền đọc/ghi cho owner.

Ví dụ access file:

~~~properties
monitorRole readonly
controlRole readwrite
~~~

`readonly` cho phép đọc MBean attributes và nhận notifications. `readwrite` có thể đọc/ghi attributes và gọi operations; quyền này có thể làm thay đổi trạng thái ứng dụng.

Password file chuẩn của JMX lưu mật khẩu dạng clear text và được Oracle mô tả là phù hợp cho development. Không dùng mật khẩu đăng nhập cá nhân; dùng credential riêng, giới hạn quyền file và chọn cơ chế xác thực phù hợp cho production.

Không đặt `com.sun.management.jmxremote.authenticate=false` hoặc tắt SSL trên một cổng remote có thể truy cập từ mạng không tin cậy. Khi bỏ cả xác thực và mã hóa, bất kỳ người nào biết hoặc đoán được host và port đều có thể truy cập dữ liệu quản lý, thậm chí gọi operation thay đổi ứng dụng.

Oracle cũng lưu ý nguy cơ RMI registry không bảo vệ: kẻ tấn công có thể dựng registry giả trước registry hợp lệ để đánh cắp credential client. Với môi trường cần remote JMX an toàn, cấu hình SSL cho registry và client authentication theo hướng dẫn JDK; không chỉ bật SSL cho connector rồi mặc định registry đã an toàn.

## 16. Các tùy chọn dòng lệnh của JConsole

| Tùy chọn | Chức năng |
|---|---|
| `-interval=n` | Đặt chu kỳ cập nhật biểu đồ theo giây; mặc định là 4 giây. |
| `-notile` | Không tự sắp xếp các cửa sổ ban đầu khi kết nối nhiều JVM. |
| `-pluginpath path` | Nạp JConsole plugin từ thư mục hoặc JAR được chỉ định. |
| `-version` | In phiên bản chương trình. |
| `-help` hoặc `--help` | Hiển thị trợ giúp. |
| `-J<flag>` | Truyền JVM argument cho chính tiến trình JConsole. |

Ví dụ tăng khoảng cập nhật:

~~~bash
jconsole -interval=8
~~~

Kết nối remote với khoảng cập nhật 5 giây:

~~~bash
jconsole -interval=5 monitor.example.com:7091
~~~

Truyền heap size cho JVM chạy JConsole:

~~~bash
jconsole -J-Xmx512m
~~~

`-J-Xmx512m` áp dụng cho JVM của JConsole, không thay đổi heap của ứng dụng đang được giám sát.

## 17. JConsole plugin và custom tabs

JConsole hỗ trợ plugin để thêm tab hoặc nội dung giám sát tùy chỉnh. Plugin triển khai `com.sun.tools.jconsole.JConsolePlugin` và được khai báo trong service provider file:

~~~text
META-INF/services/com.sun.tools.jconsole.JConsolePlugin
~~~

File này chứa tên đầy đủ của class plugin. Nạp plugin bằng:

~~~bash
jconsole -pluginpath /path/to/plugin.jar
~~~

Plugin hữu ích khi tổ chức có metric hoặc thao tác quản trị riêng mà muốn trình bày trực tiếp trong giao diện JConsole. Chỉ nạp plugin từ nguồn tin cậy vì plugin chạy trong JVM của công cụ giám sát và có thể truy cập dữ liệu của client.

## 18. Giới hạn và tác động khi sử dụng

JConsole rất hữu ích cho development, nhưng cần hiểu giới hạn:

- JConsole tự tiêu thụ CPU và memory; khi chạy local trên production, nó có thể ảnh hưởng tới hệ thống đang đo.
- Remote monitoring giúp tách tải của giao diện khỏi máy chạy ứng dụng.
- Biểu đồ là dữ liệu lấy mẫu theo chu kỳ, không phải trace liên tục ở mức từng method.
- JConsole không tự xác định nguyên nhân memory leak; cần heap dump và công cụ phân tích object retention.
- CPU chart không thay thế profiler hoặc JFR khi cần tìm method gây CPU cao.
- Một số thao tác trong MBeans có thể thay đổi trạng thái ứng dụng.
- JVM cần hỗ trợ JMX/Attach và tài khoản cần đủ quyền để kết nối.
- Local attach có thể bị giới hạn bởi user, container/PID namespace, filesystem permissions hoặc `-XX:+DisableAttachMechanism`.
- Remote JMX cần cấu hình network, port, authentication và TLS đúng.
- Thread count hoặc heap usage bất thường là dấu hiệu điều tra, không phải kết luận tự động về lỗi.

Trong Windows, local monitoring dựa trên quyền file ở thư mục temporary; Oracle lưu ý cơ chế này không được hỗ trợ trên FAT vì filesystem không cung cấp đủ access control.

## 19. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jconsole is not recognized` | JDK bin chưa nằm trong PATH hoặc đang dùng runtime không có tool. | Kiểm tra `JAVA_HOME` và chạy `JDK_HOME/bin/jconsole`. |
| Không thấy process trong Local Process | Khác user, JVM không attachable, attach bị tắt hoặc process ở namespace khác. | Dùng cùng user, kiểm tra `jcmd -l`, container và `DisableAttachMechanism`. |
| Process hiển thị nhưng không Connect được | JVM không hỗ trợ attach hoặc management agent không thể bật. | Kiểm tra loại JVM, quyền file và cấu hình attach. |
| Remote connection refused | JMX agent chưa bật, sai port hoặc firewall chặn. | Kiểm tra `jmxremote.port`, `jmxremote.rmi.port` và network ACL. |
| Remote connection timeout | RMI stub công bố sai hostname hoặc connector port không truy cập được. | Kiểm tra `java.rmi.server.hostname`, RMI port và firewall. |
| Authentication failed | Sai username/password hoặc access/password file không hợp lệ. | Kiểm tra role có trong cả hai file và quyền file. |
| SSL handshake failed | Certificate không được tin cậy, hostname không khớp hoặc client certificate thiếu. | Kiểm tra keystore, truststore, certificate chain và SSL client-auth. |
| MBeans tab không thấy MBean riêng | Ứng dụng chưa đăng ký MBean hoặc ObjectName khác dự kiến. | Kiểm tra `MBeanServer.registerMBean` và ObjectName. |
| Biểu đồ cập nhật chậm | Update interval lớn hoặc JVM/connection bị quá tải. | Điều chỉnh `-interval=n` và kiểm tra tác động tới ứng dụng. |
| JConsole làm ứng dụng chậm | Giám sát local và cập nhật biểu đồ tạo thêm overhead. | Giảm tần suất, chỉ mở tab cần thiết hoặc dùng remote JConsole. |

## 20. Quy trình giám sát JVM bằng JConsole

Khi bắt đầu điều tra một ứng dụng:

1. Xác định JVM bằng `jcmd -l` hoặc `jps -l`.
2. Dùng `jconsole <pid>` để kết nối local, hoặc cấu hình JMX remote an toàn rồi kết nối `host:port`.
3. Xem Overview để nhận biết CPU, memory, thread count và class loading.
4. Mở Memory để xem heap, non-heap và GC.
5. Mở Threads để xem stack trace, state và Detect Deadlock.
6. Mở Classes để theo dõi class loading/unloading.
7. Mở VM để xác nhận uptime, JVM arguments và runtime configuration.
8. Mở MBeans để xem platform MXBeans hoặc custom MBeans.
9. Chỉ gọi operation có tác động khi hiểu rõ quyền và hậu quả.
10. Lưu CSV hoặc diagnostic data cần thiết, bảo vệ thông tin nhạy cảm và ngắt kết nối khi hoàn tất.

JConsole là giao diện trực quan để quan sát JMX instrumentation của JVM và ứng dụng. Hiểu các tab, cách kết nối local/remote và quyền của MBean giúp người vận hành đọc số liệu đúng, phát hiện dấu hiệu bất thường và tránh thao tác quản trị không mong muốn.

## Tài liệu tham khảo

- Oracle JDK 24 — [The jconsole Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jconsole.html).
- Oracle JDK 24 — [Using JConsole](https://docs.oracle.com/en/java/javase/24/management/using-jconsole.html).
- Oracle JDK 24 — [Monitoring and Management Using JMX Technology](https://docs.oracle.com/en/java/javase/24/management/monitoring-and-management-using-jmx-technology.html).
- Oracle JDK 24 — [Monitoring and Management Guide (PDF)](https://docs.oracle.com/en/java/javase/24/management/java-se-monitoring-and-management-guide.pdf).
