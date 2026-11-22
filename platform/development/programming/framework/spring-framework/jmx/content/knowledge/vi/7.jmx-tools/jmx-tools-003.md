# jcmd, JVM flags và quan hệ với JMX

## 1. Mục tiêu

Khi vận hành một ứng dụng Java/Spring Framework, ta thường gặp ba nhóm công cụ và cơ chế:

- **\`jcmd\`**: công cụ dòng lệnh gửi các *diagnostic commands* tới một JVM đang chạy.
- **JVM flags/system properties**: tham số lúc khởi động JVM hoặc tùy chọn chẩn đoán, điều khiển một số hành vi JVM, trong đó có agent quản lý và remote JMX.
- **JMX (Java Management Extensions)**: API và hạ tầng cho phép đọc thuộc tính, gọi thao tác quản trị qua \`MBeanServer\`, có thể thông qua client cục bộ hoặc connector từ xa.

Chúng liên quan chặt chẽ nhưng không đồng nghĩa. Một JVM có thể cho \`jcmd\` kết nối cục bộ dù chưa bật remote JMX. Một ứng dụng có thể đăng ký MBean trong platform MBeanServer dù chưa có endpoint mạng. Ngược lại, bật cổng remote JMX chưa bảo đảm Spring bean đã được xuất thành MBean.

Sau bài học, bạn có thể:

1. Phân biệt diagnostic commands của \`jcmd\` với operations/attributes của JMX.
2. Xem các tiến trình JVM và liệt kê lệnh được hỗ trợ bởi từng JVM.
3. Dùng \`jcmd\` kiểm tra command line, system properties, flags, threads và heap theo đúng mục đích.
4. Hiểu vai trò của \`-Dcom.sun.management.jmxremote.*\`, \`-Djava.rmi.server.hostname\` và các JVM flags khác.
5. Mô tả đường đi từ Spring JMX exporter tới MBeanServer và JMX client.
6. Khoanh vùng lỗi giữa local attach, JVM options, remote connector, RMI, mạng và Spring export.
7. Sử dụng công cụ chẩn đoán một cách có kiểm soát, không tự ý mở kênh quản trị ra Internet.

## 2. Sơ đồ tư duy: ba con đường quan sát cùng một JVM

\`\`\`text
                             ỨNG DỤNG JAVA / SPRING
                                      |
                    +-----------------+------------------+
                    |                                    |
             JVM diagnostics                      Platform MBeanServer
                    |                                    |
               Attach API                         JVM built-in MBeans
                    |                            + Spring-exported MBeans
                 jcmd PID                                 |
                    |                         +-----------+-------------+
                    |                         |                         |
             diagnostic commands         local JMX client           JMX connector
             (Thread.print, GC.*,        (JConsole, tooling)           |
              VM.flags, ...)                                      RMI/network/TLS/auth
                                                                       |
                                                                 remote JMX client
\`\`\`

Ba đường có thể cùng trả lời một câu hỏi vận hành, ví dụ “JVM dùng bao nhiêu heap?”; nhưng **đầu vào, quyền cần thiết, cách kết nối và kết quả** khác nhau.

| Cơ chế | Đối tượng tương tác | Ví dụ | Đặc điểm |
|---|---|---|---|
| \`jcmd\` | Diagnostic command handler trong target JVM | \`jcmd <pid> VM.flags\` | Thường qua cơ chế attach cục bộ |
| JVM startup flags | JVM ngay khi khởi động | \`-Xmx512m\`, \`-D...\` | Có thể quyết định cấu hình ban đầu |
| JMX | MBeanServer và MBean được đăng ký | \`getAttribute\`, \`invoke\` | API quản trị có metadata và ObjectName |
| Remote JMX | Connector tới MBeanServer | JConsole qua service URL | Cần cấu hình mạng và bảo mật riêng |

Không nên suy luận “chạy được \`jcmd\`” nghĩa là cổng remote JMX đang mở, hoặc “có remote JMX” nghĩa là có thể thực hiện mọi diagnostic command.

## 3. Công cụ jcmd là gì?

\`jcmd\` được phân phối cùng JDK. Cú pháp phổ biến:

\`\`\`text
jcmd [<pid> | <main-class>] <command> [arguments]
\`\`\`

Cách dùng thực tế:

\`\`\`bash
jcmd -l
jcmd 12345 help
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
\`\`\`

\`12345\` là ví dụ PID, thay bằng PID thật. Khi dùng \`jcmd -l\`, các tiến trình JVM hiện có thể được liệt kê tùy hệ điều hành, phân quyền và cơ chế JVM attach. Một JVM chạy trong container khác, namespace khác hoặc dưới người dùng khác có thể không xuất hiện trong danh sách.

### 3.1. Vì sao cần \`help\` theo PID?

Những diagnostic command khả dụng khác nhau theo bản JDK, vendor, build và cài đặt JVM; một số lệnh có điều kiện hoặc gây tác động vận hành. Vì vậy thay vì sao chép “danh sách lệnh chắc chắn có”, hãy hỏi JVM đích:

\`\`\`bash
jcmd <pid> help
jcmd <pid> help Thread.print
jcmd <pid> help GC.heap_dump
\`\`\`

\`help <command>\` mô tả cú pháp và tùy chọn thực tế mà JVM đó hỗ trợ.

### 3.2. Nhóm lệnh thường dùng

| Diagnostic command | Mục đích chính | Tình huống sử dụng |
|---|---|---|
| \`VM.version\` | Xem thông tin JVM | Xác định bản JDK/vendor |
| \`VM.command_line\` | Xem command line khởi động JVM | Kiểm tra JVM options và classpath/module path |
| \`VM.flags\` | Xem JVM flags | Đối chiếu giá trị hiện hành |
| \`VM.system_properties\` | Xem Java system properties | Xác nhận \`-D...\` hoặc property runtime |
| \`Thread.print\` | In thread dump | Chẩn đoán deadlock, blocked threads |
| \`GC.heap_info\` | Thông tin heap | Quan sát bộ nhớ |
| \`GC.class_histogram\` | Thống kê instance theo class | Điều tra chiếm dụng bộ nhớ |
| \`GC.heap_dump\` | Ghi heap dump ra file | Phân tích sâu vấn đề bộ nhớ |
| \`JFR.start\` / \`JFR.dump\` | Điều khiển Java Flight Recorder khi hỗ trợ | Ghi dữ liệu chẩn đoán theo thời gian |
| \`ManagementAgent.status\` | Trạng thái management agent khi hỗ trợ | Kiểm tra quản lý/JMX agent |
| \`ManagementAgent.start\` / \`start_local\` / \`stop\` | Điều khiển management agent khi hỗ trợ | Lab hoặc vận hành được cấp quyền |

**Lưu ý:** một số lệnh như heap dump hoặc histogram có thể gây tạm dừng đáng kể, tiêu tốn CPU/dung lượng đĩa, và tạo file chứa dữ liệu nhạy cảm. Chỉ dùng khi hiểu tác động và có quyền vận hành.

## 4. Thực hành jcmd trên ứng dụng Java nhỏ

Ví dụ Java thuần để quan sát một tiến trình còn sống:

\`\`\`java
// DemoJvm.java
public class DemoJvm {
    public static void main(String[] args) throws Exception {
        System.out.println("PID = " + ProcessHandle.current().pid());
        System.out.println("Application is running...");
        Thread.sleep(300_000);
    }
}
\`\`\`

Biên dịch và khởi động với JDK:

\`\`\`bash
javac DemoJvm.java
java -Xms64m -Xmx256m -Ddemo.environment=lab DemoJvm
\`\`\`

Mở terminal khác, lấy PID chương trình đã in hoặc chạy:

\`\`\`bash
jcmd -l
\`\`\`

Tiếp theo thay \`<pid>\` bằng PID thực tế:

\`\`\`bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
jcmd <pid> Thread.print
jcmd <pid> GC.heap_info
\`\`\`

Kết quả cần tự quan sát:

- \`VM.version\` trả thông tin phiên bản JVM đang chạy.
- \`VM.command_line\` giúp nhận diện cách tiến trình được khởi động.
- \`VM.flags\` thể hiện các JVM flags được áp dụng; không nhất thiết phản ánh mọi system property \`-D\`.
- \`VM.system_properties\` chứa property \`demo.environment=lab\`.
- \`Thread.print\` chứa thread \`main\` đang ngủ.
- \`GC.heap_info\` hiển thị dữ liệu bộ nhớ theo collector/JDK đang dùng.

Không dùng \`VM.flags\` như nơi duy nhất xác nhận \`-Dcom.sun.management.*\`: đây là system properties, nên \`VM.system_properties\` và command line thường thích hợp hơn.

## 5. Phân biệt JVM flag với system property

Người học rất dễ gom mọi tham số \`java ...\` vào một khái niệm “JVM flag”. Về kỹ thuật nên phân biệt:

### 5.1. JVM options

\`\`\`bash
java -Xms128m -Xmx512m -XX:+UseG1GC DemoJvm
\`\`\`

\`-Xms\`, \`-Xmx\`, \`-XX:...\` là các tùy chọn điều khiển JVM. Cấu hình hợp lệ tùy bản JVM và vendor. \`jcmd <pid> VM.flags\` giúp xem nhiều flag hiện hành; \`VM.command_line\` giúp xem cách khởi động.

### 5.2. Java system properties

\`\`\`bash
java -Ddemo.environment=lab -Dfeature.enabled=true DemoJvm
\`\`\`

\`-Dkey=value\` tạo Java system property, có thể đọc bằng:

\`\`\`java
String env = System.getProperty("demo.environment");
\`\`\`

Thông tin cũng có thể xuất hiện qua:

\`\`\`bash
jcmd <pid> VM.system_properties
\`\`\`

Các cấu hình \`com.sun.management.jmxremote.*\` được truyền dưới dạng **system properties** với tiền tố \`-D\`. Chúng liên quan management agent/JMX connector; không nên gọi chúng là \`-XX\` flags.

### 5.3. Không phải mọi cấu hình đều có thể thay đổi khi JVM đang chạy

Một số VM flags có thể được JVM hỗ trợ thay đổi động; nhiều flag khác cần restart và có phạm vi giá trị chặt chẽ. Một system property có thể bị code Java thay đổi nhưng điều này **không có nghĩa management agent tự đọc lại và cấu hình lại endpoint**. Với JMX remote, hãy sử dụng cơ chế management agent được JVM hỗ trợ và xác minh thực tế; nếu thay đổi startup properties, thông thường cần khởi động lại JVM với cấu hình mới.

## 6. JMX hoạt động ở đâu trong JVM?

JVM có sẵn một số platform MXBeans, chẳng hạn:

- \`java.lang:type=Memory\` cho bộ nhớ.
- \`java.lang:type=Threading\` cho thread.
- \`java.lang:type=Runtime\` cho thông tin runtime.
- \`java.lang:type=ClassLoading\` cho tải class.
- \`java.lang:type=OperatingSystem\` cho thông tin hệ điều hành/JVM.

Các MBean này có thể được truy cập qua \`ManagementFactory.getPlatformMBeanServer()\` trong cùng JVM:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class ReadMemoryMBean {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName memory =
            new ObjectName("java.lang:type=Memory");

        Object heapUsage =
            server.getAttribute(memory, "HeapMemoryUsage");

        System.out.println(heapUsage);
    }
}
\`\`\`

Giá trị \`HeapMemoryUsage\` được biểu diễn dưới dạng JMX Open Data khi đi qua generic MBeanServer API, thường là \`CompositeData\`; không nên giả định nó luôn là đối tượng \`MemoryUsage\` Java gốc khi sử dụng đường API này.

**Phân biệt:** \`jcmd <pid> GC.heap_info\` và \`server.getAttribute(memory, "HeapMemoryUsage")\` đều liên quan heap, nhưng đi qua hai API và cấu trúc dữ liệu khác nhau. Đừng coi một diagnostic command như một MBean operation có cùng tên.

## 7. Spring Framework JMX nằm ở tầng nào?

Spring Framework cung cấp tích hợp để xuất các Spring-managed objects qua JMX. Các thành phần phổ biến:

- \`@ManagedResource\` xác định bean/resource quản trị.
- \`@ManagedAttribute\` công khai attribute.
- \`@ManagedOperation\` công khai operation.
- \`MBeanExporter\` đăng ký bean lên \`MBeanServer\`.
- \`@EnableMBeanExport\` có thể kích hoạt cấu hình export theo annotation.

Ví dụ minh họa:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "training.spring:type=Worker,name=Primary",
    description = "Worker runtime status")
public class WorkerStatus {
    private volatile boolean enabled = true;

    @ManagedAttribute
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
\`\`\`

Với ứng dụng đã cấu hình JMX export đầy đủ, MBean có thể được tìm bằng JConsole hoặc JMX client.

\`\`\`text
Spring bean
   ↓
Spring MBeanExporter / annotation metadata
   ↓
JVM MBeanServer
   ↓
JMX client local hoặc connector từ xa
\`\`\`

**MBeanExporter không tự mở một cổng TCP remote JMX.** Việc truy cập remote cần connector/agent phù hợp và chính sách bảo mật riêng. Đồng thời, chạy được \`jcmd\` không chứng minh Spring bean đã được export; cần kiểm tra ObjectName thực tế.

## 8. Local attach, local JMX và remote JMX

### 8.1. Local attach

\`jcmd\` thường tương tác với JVM trên cùng host bằng cơ chế attach. Khả năng attach phụ thuộc user/process owner, OS permissions, namespace/container, JDK/JVM implementation và cấu hình bảo mật. Một số JVM có thể được khởi động với tùy chọn hạn chế attach, ví dụ \`-XX:+DisableAttachMechanism\` trên HotSpot khi được hỗ trợ.

Không khẳng định \`jcmd\` sẽ hoạt động với mọi PID chỉ vì tiến trình tồn tại.

### 8.2. Local JMX

JConsole có thể kết nối với JVM cục bộ qua cơ chế attach/management agent được JDK hỗ trợ. Từ đó người dùng thấy các platform MBeans và MBean do ứng dụng đăng ký.

\`\`\`bash
jconsole
\`\`\`

Trong GUI, chọn tiến trình Java được phép truy cập. Một số trường hợp local JMX cần management agent được kích hoạt hoặc khởi tạo; điều kiện thay đổi theo JDK, tiến trình và quyền.

### 8.3. Remote JMX

Remote JMX cần một connector lắng nghe mạng hoặc cơ chế truy cập từ xa tương đương. Trong JDK HotSpot, các system properties \`com.sun.management.jmxremote.*\` thường được dùng để cấu hình management agent hỗ trợ JMX/RMI.

Các nhóm thiết lập quan trọng:

| Property | Ý nghĩa |
|---|---|
| \`com.sun.management.jmxremote\` | Kích hoạt agent quản lý theo cơ chế JVM hỗ trợ |
| \`com.sun.management.jmxremote.port\` | Cổng RMI registry dành cho remote monitoring |
| \`com.sun.management.jmxremote.rmi.port\` | Cổng RMI connector server để tránh cổng động |
| \`java.rmi.server.hostname\` | Host/IP RMI stub công bố cho client |
| \`com.sun.management.jmxremote.authenticate\` | Thiết lập xác thực của remote agent |
| \`com.sun.management.jmxremote.ssl\` | Thiết lập SSL/TLS của remote agent |
| \`com.sun.management.jmxremote.password.file\` | Nơi lấy thông tin xác thực khi dùng password file |
| \`com.sun.management.jmxremote.access.file\` | Chính sách quyền truy cập khi dùng access file |

Các thiết lập và giá trị hợp lệ phải đối chiếu tài liệu của **bản JDK đang triển khai**. Chỉ nên bật JMX remote trên mạng quản trị được bảo vệ.

### 8.4. Vì sao RMI có thể dùng nhiều cổng?

JMX/RMI thường có bước tra cứu qua RMI registry rồi kết nối đến remote object được quảng bá. Nếu cổng connector server được chọn động, firewall có thể cho phép registry nhưng chặn kết nối tiếp theo. Ngoài cổng, \`java.rmi.server.hostname\` phải trỏ tới địa chỉ client thực sự truy cập được.

Ví dụ URL JMX/RMI thường gặp:

\`\`\`text
service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi
\`\`\`

URL này cho biết nơi lookup connector trong registry. Nó không bảo đảm RMI stub bên trong quảng bá cùng hostname/cổng đó.

## 9. Dùng jcmd để quan sát management agent

Một số bản JDK/HotSpot cung cấp các lệnh:

\`\`\`bash
jcmd <pid> help ManagementAgent.status
jcmd <pid> ManagementAgent.status
\`\`\`

Nếu JVM hỗ trợ, \`ManagementAgent.status\` giúp xem trạng thái agent. Tùy phiên bản, các lệnh \`ManagementAgent.start\`, \`ManagementAgent.start_local\` hoặc \`ManagementAgent.stop\` có thể cho phép khởi động/dừng thành phần management.

**Không tự chạy \`ManagementAgent.start\` trên JVM production chỉ để thử.** Lệnh này có thể làm thay đổi trạng thái quản trị và khả năng truy cập. Trước tiên dùng \`help\`, hiểu cú pháp, quyền, cổng, TLS/xác thực và ảnh hưởng vận hành.

Thay vì giả định agent đang chạy từ một \`-D\` property, nên kết hợp quan sát:

1. \`VM.command_line\` cho cấu hình khởi động.
2. \`VM.system_properties\` cho giá trị property hiện hành.
3. \`ManagementAgent.status\` nếu có.
4. Kiểm tra JMX connection thực tế từ client được phép.
5. Kiểm tra ObjectName MBean dự kiến.

Một property có mặt chưa đủ chứng minh client từ xa truy cập được.

## 10. Đối chiếu cùng một vấn đề bằng jcmd và JMX

### 10.1. Heap memory

\`\`\`bash
jcmd <pid> GC.heap_info
\`\`\`

Qua JMX:

\`\`\`java
Object usage = connection.getAttribute(
    new ObjectName("java.lang:type=Memory"),
    "HeapMemoryUsage");
\`\`\`

Cả hai giúp quan sát bộ nhớ, nhưng dữ liệu và cách trình bày có thể khác.

### 10.2. Threads

\`\`\`bash
jcmd <pid> Thread.print
\`\`\`

Qua JMX, \`java.lang:type=Threading\` cung cấp attributes/operations liên quan thread. Một client có thể gọi \`ThreadMXBean\` qua proxy hoặc JMX API, nhưng không có lý do để kỳ vọng MBean operation tên \`Thread.print\`.

### 10.3. JVM arguments

\`\`\`bash
jcmd <pid> VM.command_line
\`\`\`

Qua Java/JMX, RuntimeMXBean có thể cung cấp input arguments:

\`\`\`java
var runtime = java.lang.management.ManagementFactory
    .getRuntimeMXBean();
System.out.println(runtime.getInputArguments());
\`\`\`

Hai cách có thể phù hợp mục tiêu khác nhau. Dữ liệu lệnh và arguments có thể chứa thông tin nhạy cảm; hạn chế log/chia sẻ nguyên trạng ở môi trường thật.

### 10.4. Spring business MBeans

\`\`\`text
training.spring:type=Worker,name=Primary
\`\`\`

MBean nghiệp vụ này được Spring export (khi đã cấu hình đúng). \`jcmd\` không biến mọi \`@ManagedAttribute\` của Spring thành diagnostic command. Để đọc \`Enabled\`, dùng JMX client:

\`\`\`java
connection.getAttribute(
    new ObjectName("training.spring:type=Worker,name=Primary"),
    "Enabled");
\`\`\`

## 11. Quy trình xử lý sự cố theo tầng

Khi JMX không hoạt động như mong đợi, hãy xác định tầng lỗi trước.

### Tình huống A: \`jcmd -l\` không thấy JVM

Kiểm tra cùng host/container namespace, quyền người dùng, JDK tools, PID và cơ chế attach. Nếu JVM chạy trong container, có thể cần thực thi công cụ trong cùng namespace/container theo chính sách vận hành. Không mặc định nguyên nhân là lỗi Spring.

### Tình huống B: \`jcmd <pid> ...\` bị lỗi attach

Kiểm tra tiến trình có đang chạy, quyền OS, user owner, filesystem/temp, khả năng attach, chính sách bảo mật và cờ JVM ngăn attach. Một số lệnh có thể không được JVM đích hỗ trợ dù attach thành công.

### Tình huống C: jcmd hoạt động, JConsole không thấy Spring MBean

Kiểm tra \`MBeanExporter\`, \`@EnableMBeanExport\`, annotation metadata, \`ObjectName\` và MBeanServer đích. \`jcmd\` và JMX export là hai cơ chế độc lập.

### Tình huống D: Local JConsole thấy MBean, remote JConsole lỗi

Xác nhận remote connector/agent đã được bật; xem trạng thái agent, registry và RMI server port, hostname được công bố, firewall/routing, xác thực, TLS và truststore. Không chỉ mở cổng đầu tiên rồi kết luận cấu hình RMI đúng.

### Tình huống E: Remote client kết nối được nhưng operation thất bại

Phân biệt lỗi không tìm thấy ObjectName, method signature không khớp, quyền truy cập không đủ hoặc exception do MBean thực thi. Kiểm tra metadata qua \`getMBeanInfo\`; không quy lỗi mạng khi JMX connection đã thành công.

### Tình huống F: Cấu hình JVM flag không như dự kiến

So sánh command line khởi động, \`VM.flags\`, \`VM.system_properties\` và cấu hình do process manager/container truyền vào. Có thể có tham số bị ghi đè hoặc sai vị trí trên câu lệnh. Với \`java\`, các JVM options thường cần đứng trước main class hoặc \`-jar\` để được JVM xử lý.

## 12. Thực hành: từ jcmd tới JMX trên cùng JVM

### Bài thực hành 1 — Chẩn đoán JVM

1. Chạy \`DemoJvm\` với \`-Xmx256m -Ddemo.environment=lab\`.
2. Dùng \`jcmd -l\` tìm PID.
3. Dùng \`VM.command_line\`, \`VM.flags\`, \`VM.system_properties\`.
4. Chỉ ra đâu là JVM flag, đâu là Java system property.
5. Dùng \`Thread.print\` để tìm thread main.

**Tiêu chí hoàn thành:** có thể giải thích nguồn từng giá trị mà không nhầm \`-D\` với \`-XX\`.

### Bài thực hành 2 — Kiểm tra platform MBean

1. Khởi động JVM đơn giản có \`ManagementFactory.getPlatformMBeanServer()\`.
2. In \`ObjectName\` của \`java.lang:type=Memory\`.
3. Đọc \`HeapMemoryUsage\` qua \`MBeanServerConnection\`.
4. Quan sát memory bằng \`jcmd GC.heap_info\`.
5. Giải thích sự khác nhau giữa diagnostic command và MBean attribute.

**Tiêu chí hoàn thành:** hiểu hai kênh quan sát cùng một JVM có thể biểu diễn dữ liệu khác nhau.

### Bài thực hành 3 — Spring JMX

1. Tạo Spring bean \`WorkerStatus\`.
2. Bật JMX export phù hợp.
3. Kết nối JConsole local tới JVM.
4. Xác nhận \`training.spring:type=Worker,name=Primary\` xuất hiện.
5. Thay đổi \`Enabled\` qua JMX và kiểm tra giá trị.

**Tiêu chí hoàn thành:** phân biệt được việc Spring export MBean với việc JDK quản lý tiến trình.

### Bài thực hành 4 — Phân tích remote JMX trên giấy

Giả sử registry ở cổng 9010 và RMI server ở cổng 9011, được công bố với hostname \`jmx.internal.example\`. Vẽ đường kết nối của một client trong mạng quản trị và liệt kê:

- Cổng registry và RMI server mà firewall cần cho phép.
- DNS hoặc địa chỉ RMI stub phải giải được từ client.
- Cách xác thực, mã hóa và hạn chế máy nguồn.
- Lệnh \`jcmd\`/quan sát cần thực hiện để biết agent được bật hay chưa.
- Một thử nghiệm kết nối hợp lệ, không làm thay đổi trạng thái nghiệp vụ.

Không cần mở endpoint thật để hiểu kiến trúc RMI. Khi thực hành trong lab, dùng môi trường cô lập và cấu hình bảo mật đúng.

## 13. Những lỗi hiểu sai phổ biến

| Nhận định sai | Cách hiểu đúng |
|---|---|
| “jcmd là JMX command-line client cho mọi MBean.” | jcmd dùng diagnostic commands; không phải client tổng quát cho mọi MBean operation |
| “Bật Spring JMX là có cổng remote.” | Spring export lên MBeanServer; remote connector là cấu hình riêng |
| “\`-D...\` đều là \`-XX\` JVM flag.” | \`-D\` tạo Java system property |
| “\`jcmd -l\` phải thấy mọi JVM trên host.” | Có giới hạn quyền, namespace, attach và implementation |
| “Có \`jmxremote.port\` là chắc chắn kết nối được.” | Còn RMI endpoint, hostname, firewall, TLS, xác thực |
| “JMX remote kết nối lỗi nên MBean không tồn tại.” | MBean có thể đang tồn tại trên local MBeanServer |
| “Dùng heap dump là thao tác đọc nhẹ.” | Heap dump có thể tốn tài nguyên và chứa dữ liệu nhạy cảm |
| “Nếu \`VM.system_properties\` đã thay đổi thì management agent tự reconfigure.” | Cần cơ chế agent hỗ trợ hoặc restart/cấu hình lại có chủ đích |

## 14. Câu hỏi tự kiểm tra

1. Khác biệt về giao diện lập trình giữa jcmd và JMX là gì?
2. \`VM.flags\` và \`VM.system_properties\` cung cấp loại thông tin nào?
3. Vì sao một Spring MBean có thể tồn tại dù không mở remote JMX port?
4. Tại sao remote JMX qua RMI có thể phải đi qua hai endpoint?
5. \`java.rmi.server.hostname\` ảnh hưởng bước kết nối nào?
6. Trong trường hợp jcmd không attach được, nên kiểm tra yếu tố nào?
7. Vì sao không thể dùng \`jcmd\` để gọi tùy ý một operation \`@ManagedOperation\`?
8. Khi remote client kết nối được nhưng không thấy ObjectName, vấn đề thuộc tầng nào?
9. Những rủi ro của \`GC.heap_dump\` và \`VM.system_properties\` trong vận hành là gì?
10. Muốn kiểm tra remote JMX đã hoạt động, cần thêm bằng chứng nào ngoài startup flags?

## 15. Tài liệu tham khảo

- Oracle JDK 21 — \`jcmd\` tool: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — Monitoring and Management: https://docs.oracle.com/en/java/javase/21/management/
- Java SE 21 — \`ManagementFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html

**Ghi nhớ:** \`jcmd\` chẩn đoán JVM bằng diagnostic commands; JVM flags và system properties điều chỉnh cấu hình khởi động hoặc hành vi runtime; JMX cung cấp hợp đồng quản trị qua MBeanServer. Khi gặp sự cố, kiểm tra đúng tầng và bằng chứng từ JVM đích trước khi điều chỉnh cấu hình hoặc mở quyền truy cập mạng.
