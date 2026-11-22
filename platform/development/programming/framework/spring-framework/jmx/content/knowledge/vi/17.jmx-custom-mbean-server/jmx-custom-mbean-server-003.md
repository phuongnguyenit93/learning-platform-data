# PlatformMBeanServer của JVM trong Spring Framework JMX

## 1. Tổng quan

Trong Java Management Extensions (JMX), **MBeanServer** là thành phần đăng ký, tra cứu và thực thi các lời gọi quản trị lên MBean. Một JVM có thể có nhiều MBeanServer, nhưng nền tảng Java cung cấp một **platform MBeanServer** dùng chung cho các MBean nền tảng của JVM và có thể dùng cho MBean của ứng dụng.

API quan trọng nhất:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
\`\`\`

Trong Spring Framework JMX, \`MBeanExporter\` có thể đăng ký Spring-managed beans vào platform MBeanServer, giúp các client như JConsole, VisualVM hoặc remote JMX client quan sát và gọi các thuộc tính/thao tác quản trị.

**Tư duy cốt lõi:** platform MBeanServer là registry JMX ở phạm vi **JVM**, không phải registry Spring bean, không phải HTTP server và cũng không phải cơ chế remote connection tự động.

Bài học này giúp bạn:
- Hiểu platform MBeanServer được JVM cung cấp và khác gì MBeanServer do ứng dụng tạo.
- Biết cách lấy và kiểm tra platform MBeanServer bằng \`ManagementFactory\`.
- Phân biệt \`MBeanServer\`, \`MBeanServerConnection\` và JMX connector.
- Cấu hình Spring \`MBeanExporter\` đăng ký đúng server mong muốn.
- Hiểu platform MXBeans và vùng tên \`java.lang\`, \`java.nio\`, \`com.sun.management\` khi triển khai thực tế.
- Phân tích rủi ro trùng ObjectName, nhiều ApplicationContext, lifecycle và bảo mật.
- Chọn đúng khi nên dùng platform server hoặc một MBeanServer tùy biến.

## 2. Platform MBeanServer là gì?

\`ManagementFactory.getPlatformMBeanServer()\` trả về **platform MBeanServer** của JVM hiện hành. Nếu chưa có, API khởi tạo server nền tảng; các lần gọi tiếp theo trong cùng JVM trả về đối tượng platform server đã được tạo.

\`\`\`java
MBeanServer first = ManagementFactory.getPlatformMBeanServer();
MBeanServer second = ManagementFactory.getPlatformMBeanServer();

System.out.println(first == second); // true trong cùng JVM
\`\`\`

Platform server là nơi Java runtime đăng ký những MXBeans tiêu chuẩn phản ánh trạng thái JVM, chẳng hạn:

- \`MemoryMXBean\`: heap/non-heap memory và thao tác liên quan.
- \`ThreadMXBean\`: thông tin thread, deadlock/CPU time trong phạm vi hỗ trợ.
- \`RuntimeMXBean\`: thông tin runtime và JVM.
- \`ClassLoadingMXBean\`: class loading.
- \`GarbageCollectorMXBean\`: thống kê garbage collector.
- \`MemoryPoolMXBean\`: memory pools.
- \`OperatingSystemMXBean\`: thông tin hệ điều hành theo API và implementation.
- \`CompilationMXBean\`: thông tin JIT compilation nếu JVM hỗ trợ.
- \`BufferPoolMXBean\`: buffer pools.

Không phải mọi implementation cung cấp mọi extension hoặc cùng tập MBeans bổ sung. Các MXBeans và ObjectNames chuẩn có thể kiểm tra bằng API Java và trên runtime thực tế.

### Khác với việc tự tạo MBeanServer

Java có \`MBeanServerFactory.createMBeanServer(...)\` để tạo server mới:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer custom = MBeanServerFactory.createMBeanServer(
    "com.example.custom"
);
\`\`\`

Server mới này **không tự trở thành platform MBeanServer** và không đương nhiên chứa toàn bộ platform MXBeans đã đăng ký ở server nền tảng. MBean được đăng ký ở custom server cũng không tự xuất hiện trong platform server.

Hãy hình dung:

\`\`\`text
                  JVM Process
               +-------------------+
               |                   |
               | Platform Server   |
               |  java.lang:*      |
               |  app MBeans (A)   |
               |                   |
               | Custom Server     |
               |  app MBeans (B)   |
               |                   |
               +-------------------+
\`\`\`

Một JMX client kết nối đến server A không tự nhìn thấy MBeans chỉ đăng ký ở server B.

## 3. MBeanServer, MBeanServerConnection và Connector

Ba khái niệm dễ nhầm:

| Thành phần | Vai trò |
|---|---|
| \`MBeanServer\` | Registry/runtime JMX trong JVM, hỗ trợ đăng ký và hủy đăng ký MBeans |
| \`MBeanServerConnection\` | Interface quản trị và truy vấn MBeans có thể dùng từ local hoặc qua connection |
| \`JMXConnector\` | Đối tượng client quản lý kết nối tới một JMX connector server |
| \`JMXConnectorServer\` | Thành phần server-side đưa một MBeanServer ra giao thức kết nối từ xa |
| \`MBeanExporter\` | Spring component đăng ký Spring beans vào MBeanServer được chọn |

\`MBeanServer\` mở rộng \`MBeanServerConnection\` và cung cấp thêm các thao tác đăng ký. Vì vậy local code có thể dùng server trực tiếp:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
server.queryNames(null, null);
\`\`\`

Còn remote client thường nhận \`MBeanServerConnection\`:

\`\`\`java
MBeanServerConnection connection =
    connector.getMBeanServerConnection();
\`\`\`

**Lấy được platform MBeanServer không tự mở cổng mạng.** Việc quan sát từ xa phụ thuộc connector configuration, authentication, authorization và cấu hình network của JVM/application.

## 4. Khởi tạo platform MBeanServer và kiểm tra ObjectNames

Ví dụ Java thuần:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

public class PlatformServerInspector {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        System.out.println("Default domain: "
            + server.getDefaultDomain());

        System.out.println("MBean count: "
            + server.getMBeanCount());

        Set<ObjectName> platformNames = server.queryNames(
            new ObjectName("java.lang:*"),
            null
        );

        for (ObjectName name : platformNames) {
            System.out.println(name.getCanonicalName());
        }
    }
}
\`\`\`

Ví dụ output có thể chứa:

\`\`\`text
java.lang:type=Memory
java.lang:type=Runtime
java.lang:type=Threading
java.lang:type=ClassLoading
java.lang:type=GarbageCollector,name=...
java.lang:type=MemoryPool,name=...
\`\`\`

Tên và số lượng MBeans phụ thuộc runtime; GC và memory pool names khác nhau theo JVM, collector và cấu hình.

### Default domain không quyết định mọi MBean

\`server.getDefaultDomain()\` trả về default domain của server. Điều này **không có nghĩa** mọi MBean phải nằm trong domain ấy; Java platform MXBeans có domain chuẩn riêng như \`java.lang\`.

Khi tự đăng ký MBean, nên dùng domain tường minh do ứng dụng sở hữu, ví dụ \`com.example.orders\`, tránh tranh chấp với những domain hệ thống.

## 5. Platform MXBean và trạng thái JVM

Platform MXBeans là giao diện chuẩn để đọc dữ liệu vận hành từ JVM.

Ví dụ đọc memory trực tiếp:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;

MemoryMXBean memory = ManagementFactory.getMemoryMXBean();

System.out.println(
    "Heap used: " + memory.getHeapMemoryUsage().getUsed()
);
\`\`\`

Bạn cũng có thể truy cập qua MBeanServer bằng ObjectName:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName memoryName =
    new ObjectName(ManagementFactory.MEMORY_MXBEAN_NAME);

Object heapUsage =
    server.getAttribute(memoryName, "HeapMemoryUsage");

System.out.println(heapUsage);
\`\`\`

Vì \`MemoryMXBean\` là MXBean, dữ liệu composite như \`MemoryUsage\` có thể được biểu diễn bằng \`CompositeData\` tại JMX boundary.

\`\`\`java
import javax.management.openmbean.CompositeData;

CompositeData usage = (CompositeData) heapUsage;
long used = (Long) usage.get("used");

System.out.println("Used heap bytes: " + used);
\`\`\`

Cách gọi trực tiếp \`ManagementFactory.getMemoryMXBean()\` tiện khi code đang ở trong JVM. Cách đi qua \`MBeanServerConnection\` hữu ích cho công cụ quản trị chung, kể cả remote.

### Một platform server, nhiều nguồn thông tin

Platform MBeanServer có thể chứa:
- Platform MXBeans do JVM đăng ký.
- MBeans của thư viện hoặc framework.
- MBeans do Spring \`MBeanExporter\` đăng ký.
- MBeans do code ứng dụng trực tiếp đăng ký.

Đừng kết luận MBean là platform MXBean chỉ vì nó nằm trong platform MBeanServer. **Nguồn gốc của server** khác với **nguồn gốc của từng MBean**.

## 6. Spring MBeanExporter và platform server

Trong Spring Framework, \`MBeanExporter\` có property \`server\`. Chỉ định platform server rõ ràng:

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxExportConfiguration {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            MBeanServer platformMBeanServer,
            QueueMonitor queueMonitor) {

        MBeanExporter exporter = new MBeanExporter();

        exporter.setServer(platformMBeanServer);
        exporter.setBeans(java.util.Map.of(
            "com.example.orders:type=Queue,name=Orders",
            queueMonitor
        ));

        return exporter;
    }
}
\`\`\`

Đoạn này giả định \`QueueMonitor\` đã là một Standard MBean hợp lệ hoặc được exporter adaptation phù hợp. Với POJO dùng \`@ManagedResource\`/\`@ManagedAttribute\`, cần assembler/annotation export tương ứng.

### Standard MBean minh họa

\`\`\`java
public interface QueueMonitorMBean {
    int getPendingCount();
    void resetStatistics();
}

public class QueueMonitor implements QueueMonitorMBean {
    private volatile int pendingCount;

    @Override
    public int getPendingCount() {
        return pendingCount;
    }

    @Override
    public void resetStatistics() {
        pendingCount = 0;
    }
}
\`\`\`

Từ góc nhìn Spring:

\`\`\`text
ApplicationContext
     |
     +-- QueueMonitor bean
     |
     +-- MBeanExporter bean
               |
               v
       platform MBeanServer
               |
               +-- java.lang:type=Memory
               +-- java.lang:type=Threading
               +-- com.example.orders:type=Queue,name=Orders
\`\`\`

Một ưu điểm của việc chỉ định server là tránh nhầm lẫn khi JVM có nhiều MBeanServer và JMX client đang quan sát platform server.

## 7. Dùng Spring MBeanServerFactoryBean

Spring cung cấp \`org.springframework.jmx.support.MBeanServerFactoryBean\` để lấy hoặc tạo MBeanServer theo cấu hình.

Ví dụ cách khai báo một server bean:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class JmxServerConfiguration {

    @Bean
    public MBeanServerFactoryBean mBeanServer() {
        MBeanServerFactoryBean factory =
            new MBeanServerFactoryBean();
        factory.setLocateExistingServerIfPossible(true);
        return factory;
    }
}
\`\`\`

Factory bean này hữu ích trong cấu hình Spring JMX, nhưng cần phân biệt rõ cơ chế locate/create với việc yêu cầu **đúng platform server**.

\`locateExistingServerIfPossible\` không phải là lời cam kết phổ quát rằng server được lấy luôn là \`ManagementFactory.getPlatformMBeanServer()\` trong mọi JVM. Nếu ứng dụng cần đảm bảo chính xác platform server, việc truyền trực tiếp đối tượng từ \`ManagementFactory.getPlatformMBeanServer()\` là cách rõ ràng hơn.

### Spring tự tìm MBeanServer thế nào?

Nếu \`MBeanExporter\` không được truyền \`server\`, Spring có thể dùng cơ chế lookup MBeanServer theo môi trường và cấu hình hỗ trợ. Khi chỉ có một server, việc sử dụng thường đơn giản. Nhưng trong JVM chứa nhiều MBeanServers (application servers, plugin environments, multiple contexts), lookup có thể khiến việc kiểm chứng trở nên khó hiểu.

Do đó:

- Nếu yêu cầu là “export vào platform server của JVM”, hãy cấu hình server tường minh.
- Nếu yêu cầu là “export vào server do container cấp”, lấy đúng reference theo container.
- Nếu yêu cầu là cô lập JMX registry, tạo riêng custom server và nối exporter/connector vào server đó.

## 8. Khi nào platform MBeanServer là lựa chọn phù hợp?

Platform server thường phù hợp khi:

- Ứng dụng Java/Spring chạy trong một JVM có ownership rõ ràng.
- Muốn nhìn chung JVM MXBeans và application MBeans qua một công cụ.
- Không cần phân vùng registry theo các ứng dụng khác nhau trong cùng JVM.
- Các ObjectNames có convention ổn định, tránh trùng.
- JMX remote được quản lý ở phạm vi một JVM/process.
- Tooling giám sát đang dựa trên platform JMX endpoint.

Ưu điểm:

1. **Sẵn có:** không cần khởi tạo registry riêng.
2. **Tích hợp với JVM metrics:** các platform MXBeans ở cùng server.
3. **Tương thích tooling:** nhiều công cụ Java management quen với platform MBeanServer.
4. **Đơn giản hóa vận hành:** một registry JMX quan trọng cho ứng dụng và JVM.
5. **Thích hợp cho Spring JMX:** exporter có thể đăng ký thêm application MBeans.

Tuy nhiên, dùng platform server cũng có nghĩa những module cùng JVM chia sẻ namespace và một số ràng buộc vận hành. Điều này cần quản lý tốt khi có nhiều Spring ApplicationContexts hoặc bên thứ ba đăng ký MBeans.

## 9. Khi nào nên cân nhắc MBeanServer tùy biến?

Custom MBeanServer phù hợp trong một số kiến trúc:

- Application server cần nhiều JMX registries với ownership khác nhau.
- Công cụ kiểm thử cần registry độc lập để không can thiệp platform server.
- Một embedded component muốn kiểm soát server riêng, connector riêng và lifecycle riêng.
- Nhiều ứng dụng chạy cùng JVM nhưng cần tách tập MBeans về mặt khám phá/quản trị.
- Framework cần cung cấp một MBeanServer được cấu hình theo conventions riêng.

Ví dụ tạo custom server:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer custom =
    MBeanServerFactory.createMBeanServer(
        "com.example.embedded"
    );
\`\`\`

Sau đó:

\`\`\`java
MBeanExporter exporter = new MBeanExporter();
exporter.setServer(custom);
\`\`\`

Một client kết nối tới platform server sẽ không tự nhìn thấy MBeans trong custom server. Cần cấu hình JMX connector liên kết với custom server nếu muốn truy cập từ xa.

### Custom server không tự là ranh giới bảo mật

Tạo nhiều MBeanServers tách namespace quản trị, nhưng không tự thay thế authentication/authorization. Các đối tượng chạy trong cùng JVM vẫn có thể có quyền tương tác bằng Java references, tùy kiến trúc. Security boundary thực sự cần được thực thi ở connector hoặc lớp quản trị phù hợp.

## 10. ObjectName collision trong platform server

Một MBeanServer không cho đăng ký đồng thời hai MBeans khác nhau bằng cùng một \`ObjectName\`.

Ví dụ:

\`\`\`text
com.example.orders:type=Queue,name=Orders
\`\`\`

Nếu hai Spring contexts cùng export một MBean với tên ấy vào platform server, có thể xảy ra trùng tên.

\`\`\`text
Context A -> MBeanExporter -> platform server -> ObjectName X
Context B -> MBeanExporter -> platform server -> ObjectName X
                                                ^
                                               conflict
\`\`\`

Spring có \`RegistrationPolicy\`:

- \`FAIL_ON_EXISTING\`: lỗi khi tên đã tồn tại.
- \`IGNORE_EXISTING\`: giữ đăng ký hiện hữu.
- \`REPLACE_EXISTING\`: thay đăng ký hiện hữu theo chính sách.

Dù là chế độ nào, nên hiểu ownership trước khi dùng. \`REPLACE_EXISTING\` có thể tác động đến MBean thuộc context hoặc library khác, còn \`IGNORE_EXISTING\` có thể khiến người vận hành tưởng một bean mới đã được export.

### Naming convention nên có

Một quy tắc hữu ích:

\`\`\`text
com.example.<module>:type=<Type>,name=<Name>,instance=<Instance>
\`\`\`

Ví dụ:

\`\`\`text
com.example.orders:type=Queue,name=Orders,instance=node1
com.example.orders:type=Queue,name=Orders,instance=node2
\`\`\`

Với các giá trị động, dùng \`ObjectName\` API và \`ObjectName.quote(value)\` khi cần để bảo vệ dấu phân cách và ký tự wildcard. Đừng tự nối giá trị chưa escape vào chuỗi \`domain:key=value\`.

## 11. Kiểm tra MBean đã đăng ký trên server nào

Một trong những lỗi phổ biến là Spring exporter đã chạy nhưng JConsole không thấy MBean.

Quy trình kiểm tra:

1. Xác định exporter nhận \`MBeanServer\` nào (qua \`setServer\` hoặc cấu hình Spring).
2. Kiểm tra ObjectName của bean đích.
3. Gọi \`isRegistered(name)\` trên chính server ấy.
4. Nếu client là remote, kiểm tra connector server có gắn với đúng MBeanServer không.
5. Kiểm tra authentication, authorization và network.
6. Nếu tên xuất hiện nhưng attribute/operation thiếu, kiểm tra assembler/metadata.

Ví dụ:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer platform =
    ManagementFactory.getPlatformMBeanServer();

ObjectName target = new ObjectName(
    "com.example.orders:type=Queue,name=Orders"
);

boolean registered = platform.isRegistered(target);

System.out.println(registered);
\`\`\`

Nếu kết quả false, các nguyên nhân có thể:
- Bean chưa được exporter chọn.
- Exporter đang dùng MBeanServer khác.
- ObjectName thực tế khác kỳ vọng.
- Đăng ký thất bại hoặc bean đã được unregister.
- Spring context chưa khởi động hoàn toàn hoặc đã đóng.

Điều này không chứng minh Spring bean đã bị xóa khỏi ApplicationContext; Spring bean và JMX MBean là hai registry khác nhau.

## 12. Dùng MBeanInfo để xác minh interface quản trị

Sau khi xác minh đã đăng ký:

\`\`\`java
import javax.management.MBeanInfo;

MBeanInfo info = platform.getMBeanInfo(target);

System.out.println("Description: " + info.getDescription());

for (var attr : info.getAttributes()) {
    System.out.printf(
        "Attribute=%s, type=%s, readable=%s, writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (var op : info.getOperations()) {
    System.out.println("Operation: " + op.getName());
}
\`\`\`

Khi kết nối remote, có thể gọi cùng những operations tương ứng trên \`MBeanServerConnection\`.

Vì platform server có thể chứa nhiều loại MBeans, \`MBeanInfo\` giúp phân biệt exposed API của từng MBean. Không nên chỉ nhìn một ObjectName rồi cho rằng tất cả method của underlying Java object đều có thể được gọi từ JMX.

## 13. JMX remote và platform MBeanServer

Platform server có thể được truy cập qua JMX connector nếu connector được cấu hình phù hợp. Ví dụ client remote:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    ObjectName name =
        new ObjectName("java.lang:type=Memory");

    System.out.println(connection.isRegistered(name));
}
\`\`\`

Ví dụ này minh họa client API, giả định JMX connector tại địa chỉ trên đã được cấu hình trước. Nó không tự khởi tạo connector hay bảo đảm port 9010 đang mở.

### Bảo mật

Nếu truy cập từ xa, cần xét:

- Chỉ mở cổng cho mạng/host được phép.
- Authentication và authorization phù hợp.
- Mã hóa kết nối nếu bối cảnh yêu cầu.
- Kiểm soát operation có thể thay đổi state JVM hoặc ứng dụng.
- Không đưa credentials vào source/log.
- Không mở JMX remote ra Internet công khai.

JMX là giao diện quản trị có thể nhạy cảm; platform MBeanServer có cả MBeans JVM và MBeans ứng dụng, vì vậy quyền truy cập quá rộng có thể làm lộ dữ liệu vận hành hoặc cho phép các thao tác không mong muốn.

## 14. Platform server và Spring Boot

Trong ứng dụng Spring Boot, việc đăng ký JMX có thể chịu ảnh hưởng của auto-configuration và property \`spring.jmx.enabled\`. Tùy phiên bản/cấu hình, Boot có thể tạo exporter hoặc quản lý JMX exposure của các thành phần khác như Actuator.

Cần phân biệt:

- Spring Framework \`MBeanExporter\`: đăng ký Spring beans làm MBeans.
- Spring Boot JMX auto-configuration: quyết định và cấu hình khả năng export.
- Spring Boot Actuator JMX endpoints: expose những endpoint quản trị cụ thể qua JMX khi được bật/cấu hình.
- Platform MXBeans: do JVM cung cấp, độc lập với Spring application.

**Không suy ra:** Bật HTTP Actuator nghĩa là mọi Spring bean trở thành MBean, hoặc có platform MBeanServer nghĩa là JMX remote port đã bật.

Để tránh xung đột, kiểm tra exporter thực tế trong ApplicationContext trước khi thêm \`@EnableMBeanExport\` hoặc một \`MBeanExporter\` thứ hai.

## 15. Kiểm thử với platform MBeanServer

### 15.1. Unit test và integration test

Dùng platform MBeanServer trong integration test có lợi vì giống môi trường JVM thông thường. Nhưng có điểm bất lợi: nhiều test chạy cùng JVM có thể chia sẻ registry và trùng ObjectName.

Ví dụ:

\`\`\`java
MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.testing:type=Counter,name=Test1"
);

if (server.isRegistered(name)) {
    throw new IllegalStateException(
        "Unexpected existing test MBean"
    );
}
\`\`\`

Sau test cần cleanup đăng ký thuộc ownership của test, hoặc đóng Spring context có exporter chịu trách nhiệm unregister. Không tự ý unregister platform MBeans thuộc hệ thống hoặc MBeans do component khác sở hữu.

### 15.2. Khi nào test nên dùng custom server?

Nếu nhiều test parallel cùng JVM hoặc test cần môi trường registry độc lập, một custom MBeanServer có thể tránh collision:

\`\`\`java
MBeanServer isolated =
    MBeanServerFactory.createMBeanServer("test.domain");
\`\`\`

Truyền \`isolated\` vào \`MBeanExporter\` của test và chỉ kiểm tra trên server đó.

Khi dùng \`createMBeanServer\`, test cần quản lý lifecycle và release/dereference phù hợp để tránh giữ registry không cần thiết sau khi hoàn tất. Tuyệt đối không dọn dẹp bừa bãi các MBeans thuộc JVM platform server.

## 16. Các sai lầm thường gặp

**Sai lầm 1: “Mỗi Spring ApplicationContext có platform MBeanServer riêng.”**  
Không đúng. Platform MBeanServer thuộc phạm vi JVM và được chia sẻ bởi các contexts trong JVM đó.

**Sai lầm 2: “Đã lấy platform server thì JConsole remote chắc chắn truy cập được.”**  
Không đúng. Remote connector và network/security là cấu hình riêng.

**Sai lầm 3: “Tạo MBeanServer mới vẫn tự có java.lang:type=Memory.”**  
Không đúng. Custom server không tự động là platform server hoặc chứa đầy đủ platform MXBeans.

**Sai lầm 4: “Tên bean Spring giống tên MBean.”**  
Không đúng. JMX định danh bằng \`ObjectName\`, Spring container định danh bằng bean name.

**Sai lầm 5: “MBean đã có trên một server thì mọi JMX client đều nhìn thấy.”**  
Không đúng. Client phải kết nối với connector/server chứa đăng ký đó.

**Sai lầm 6: “Có thể thay thế MBean tùy ý để sửa conflict.”**  
Không đúng. Cần xác định ownership và dùng registration policy phù hợp, tránh tác động đến MBean của thành phần khác.

**Sai lầm 7: “MBeanServer chỉ chứa platform MXBeans.”**  
Không đúng. Có thể đăng ký application MBeans, bao gồm các bean do Spring export.

**Sai lầm 8: “MBeanServer tùy biến là cơ chế security isolation hoàn chỉnh.”**  
Không đúng. Nó tách registry nhưng không tự thay thế kiểm soát truy cập.

## 17. Bài tập thực hành

### Bài tập A — Khảo sát platform server

1. Tạo Java class gọi \`ManagementFactory.getPlatformMBeanServer()\`.
2. In \`getDefaultDomain()\` và \`getMBeanCount()\`.
3. Query \`java.lang:*\`.
4. Xác định ObjectName của Memory, Runtime và Threading.
5. Dùng \`getMBeanInfo()\` để xem attributes/operations.

### Bài tập B — Xuất Spring bean

1. Tạo Standard MBean \`QueueMonitorMBean\` và class triển khai.
2. Đăng ký implementation thành Spring bean.
3. Tạo \`MBeanExporter\` và truyền platform server qua \`setServer\`.
4. Dùng \`setBeans\` export với \`com.example.training:type=Queue,name=Demo\`.
5. Kiểm tra \`isRegistered()\` và \`getMBeanInfo()\`.
6. Đóng context, xác minh lifecycle unregister khi phù hợp.

### Bài tập C — So sánh platform và custom server

1. Tạo custom server với \`MBeanServerFactory.createMBeanServer()\`.
2. Register một test MBean vào custom server.
3. Query cùng ObjectName trên platform server.
4. Giải thích vì sao kết quả khác nhau.
5. Chỉ định custom server cho một exporter riêng trong test.

### Bài tập D — Xung đột nhiều contexts

1. Tạo hai Spring contexts dùng cùng platform MBeanServer.
2. Cho mỗi context export MBean với cùng ObjectName.
3. Quan sát lỗi hoặc registration policy.
4. Thay đổi naming để names khác nhau.
5. Kiểm tra đúng hai MBeans trên cùng server.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** \`ManagementFactory.getPlatformMBeanServer()\` trả về gì?  
**Trả lời:** Platform MBeanServer của JVM đang chạy, dùng cho platform MXBeans và có thể đăng ký application MBeans.

**Câu 2.** Một JVM có thể có bao nhiêu MBeanServer?  
**Trả lời:** Có thể có nhiều server, nhưng một platform MBeanServer được lấy qua ManagementFactory trong JVM đó.

**Câu 3.** Spring \`MBeanExporter\` có bắt buộc dùng platform server không?  
**Trả lời:** Không. Có thể cấu hình \`MBeanServer\` khác bằng \`setServer()\`.

**Câu 4.** Tại sao JConsole không thấy một MBean đã đăng ký ở custom server?  
**Trả lời:** JConsole có thể đang kết nối đến platform server hoặc connector khác, không phải server chứa MBean đó.

**Câu 5.** Tạo custom MBeanServer có tự bảo vệ quyền gọi operation chưa?  
**Trả lời:** Chưa. Cần access control phù hợp cho đường truy cập thực tế.

**Câu 6.** Có nên đăng ký application MBean vào domain \`java.lang\` không?  
**Trả lời:** Thông thường không. Hãy dùng domain riêng của ứng dụng để tránh nhầm lẫn và collision.

**Câu 7.** Vì sao hai Spring contexts trong một JVM có thể xung đột JMX?  
**Trả lời:** Chúng có thể cùng export một ObjectName vào platform MBeanServer dùng chung.

## 19. Ghi nhớ

- **Platform MBeanServer thuộc JVM**, truy cập bằng \`ManagementFactory.getPlatformMBeanServer()\`.
- Một JVM có thể có nhiều MBeanServers; platform server là một server đặc biệt được nền tảng quản lý.
- Platform server chứa các JVM platform MXBeans và có thể chứa application MBeans.
- Spring \`MBeanExporter\` có thể export vào platform server qua \`setServer()\`, hoặc dùng một server khác.
- \`ObjectName\` là khóa trong mỗi MBeanServer; tránh trùng domain/key properties.
- \`MBeanServer\` không tự mở remote connector. Truy cập từ xa là trách nhiệm cấu hình kết nối và bảo mật.
- Khi có nhiều Spring contexts, tests hoặc module trong cùng JVM, cần quản lý ownership, naming và lifecycle.
- Dùng \`isRegistered()\`, \`queryNames()\` và \`getMBeanInfo()\` trên **đúng server** để xác minh trạng thái thực tế.

### Tài liệu tham khảo

- Java SE 21 API — \`ManagementFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 API — \`MBeanServerFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerFactory.html
- Java SE 21 API — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 API — Platform MXBeans: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/package-summary.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — \`MBeanServerFactoryBean\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/MBeanServerFactoryBean.html
