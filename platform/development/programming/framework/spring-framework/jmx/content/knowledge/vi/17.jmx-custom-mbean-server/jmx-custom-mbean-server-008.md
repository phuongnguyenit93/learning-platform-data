# Kiểm tra server đang được exporter dùng thực tế

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** MBeanServer tùy biến  
> **Bài học:** Kiểm tra server đang được exporter dùng thực tế

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt **Spring ApplicationContext**, **MBeanExporter**, **MBeanServer** và **JMXConnector**.
- Hiểu vì sao MBean đã export thành công nhưng JConsole hoặc một client lại không tìm thấy.
- Xác định **đúng đối tượng MBeanServer mà exporter sử dụng**, không chỉ suy luận từ việc JVM có platform MBeanServer.
- So sánh platform MBeanServer và một server tùy biến được tạo bằng \`MBeanServerFactory\` hoặc cấu hình Spring.
- Kiểm chứng đường đi từ exporter đến registry bằng \`isRegistered\`, \`queryNames\`, \`getMBeanInfo\` và đăng ký một MBean thử nghiệm có chủ đích.
- Thiết kế cấu hình rõ ràng bằng \`@EnableMBeanExport(server = "...")\` hoặc \`MBeanExporter.setServer(...)\`, đồng thời hạn chế lỗi nhiều exporter dùng nhầm server.

## 2. Vấn đề thường gặp

Một ứng dụng Spring có bean được gắn \`@ManagedResource\` và đã bật \`@EnableMBeanExport\`. Log startup không báo lỗi. Nhưng trong JConsole, tab **MBeans** không thấy ObjectName dự kiến.

Kết luận vội vàng: “Spring không export MBean”. Thực tế, còn một khả năng quan trọng: **exporter đăng ký MBean vào một MBeanServer khác với server mà công cụ đang quan sát**.

\`\`\`text
                  Ứng dụng JVM
      +-----------------------------------+
      | Spring ApplicationContext         |
      |     |                             |
      |     v                             |
      | MBeanExporter                     |
      |     |                             |
      |     +----> Custom MBeanServer      |
      |                                   |
      | Platform MBeanServer              |
      +--------------|--------------------+
                     |
                JConsole local attach
                     |
                     v
           Thường quan sát platform server

Kết quả:
  Exporter dùng custom server -> MBean tồn tại
  JConsole dùng platform server -> không nhìn thấy
\`\`\`

Vì thế cần trả lời đúng câu hỏi: **Exporter nào đang chạy, nó dùng MBeanServer nào, và client đang nối vào server nào?**

## 3. Mỗi khái niệm có trách nhiệm riêng

| Thành phần | Vai trò | Điểm cần kiểm tra |
|---|---|---|
| Spring bean | Đối tượng nghiệp vụ/management facade | Bean có được tạo trong context không? |
| \`@ManagedResource\` | Metadata để Spring JMX nhận diện tài nguyên | Có được exporter phù hợp xử lý không? |
| \`MBeanExporter\` | Đăng ký bean thành MBean | Exporter nào, cấu hình server nào? |
| \`AnnotationMBeanExporter\` | Exporter theo annotation metadata | Có được kích hoạt bởi Java config không? |
| \`MBeanServer\` | Registry và cổng thực thi JMX | ObjectName có đăng ký trên **instance server này** không? |
| Platform MBeanServer | Server quản trị chuẩn của JVM | Có phải exporter dùng server này không? |
| Custom MBeanServer | Server bổ sung theo cấu hình ứng dụng | Có được cung cấp cho exporter không? |
| \`JMXConnector\` | Cung cấp kết nối đến server từ client | Connector đang expose server nào? |
| \`MBeanServerConnection\` | Giao diện truy cập server local/remote | Client đang hỏi đúng connection không? |

Một \`ObjectName\` định danh MBean **trong phạm vi một MBeanServer**. Hai server trong cùng JVM có thể có registry khác nhau, và mỗi server có thể đăng ký cùng ObjectName mà trỏ tới MBean khác nhau.

## 4. Platform MBeanServer không nhất thiết là server của exporter

JDK cung cấp:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer platform =
    ManagementFactory.getPlatformMBeanServer();
\`\`\`

Đây là một MBeanServer phục vụ quản trị nền tảng JVM. Công cụ JMX attach vào JVM thường quan sát những MBean được export qua server này.

Nhưng ứng dụng có thể tạo server khác:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer custom =
    MBeanServerFactory.createMBeanServer(
        "custom.management"
    );
\`\`\`

Khi đó:

\`\`\`java
System.out.println(platform == custom); // false
\`\`\`

Hai server không chia sẻ một registry chỉ vì cùng nằm trong JVM. Nếu exporter được trỏ vào \`custom\`, truy vấn trên \`platform\` không tự tìm thấy MBean của custom server.

### Phân biệt create và find

\`MBeanServerFactory.createMBeanServer(domain)\` tạo một server mới và đưa nó vào danh sách MBeanServer có thể được tìm bằng factory trong cơ chế tương ứng. \`MBeanServerFactory.newMBeanServer(domain)\` cũng tạo server mới nhưng không đăng ký nó với factory theo cùng cách. Điều này ảnh hưởng khả năng discovery của code khác.

Không nên tự tạo nhiều server chỉ để “cho chắc”. Việc có nhiều server làm tăng khả năng exporter và client đi lệch registry.

## 5. Đường chọn MBeanServer của Spring exporter

Trong Spring JMX, \`MBeanExporter\` có thể được cấp một \`MBeanServer\` tường minh. Với annotation-driven export, Java configuration có thể xác định server qua tên Spring bean.

Ví dụ:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "jmxServer")
public class JmxConfiguration {

    @Bean
    public MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

\`server = "jmxServer"\` là **tên bean trong Spring context**, không phải hostname, JMX URL hay JMX ObjectName.

Với một exporter tạo thủ công:

\`\`\`java
import org.springframework.jmx.export.MBeanExporter;

MBeanExporter exporter = new MBeanExporter();
exporter.setServer(jmxServer);
\`\`\`

\`setServer\` nhận **object MBeanServer**. Khi đã cấu hình tường minh, việc hỏi server đó trực tiếp đáng tin cậy hơn suy đoán exporter sẽ tự chọn server nào.

Nếu không chỉ định, Spring có cơ chế định vị MBeanServer theo cấu hình và môi trường. Trong hệ thống có nhiều server, một lựa chọn implicit có thể không phù hợp. Hãy làm rõ selection thay vì dựa vào một giả định chung về default.

## 6. Ví dụ thực hành: một exporter, một server xác định

### 6.1. Bean quản trị

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=CacheMonitor,name=main"
)
public class CacheMonitor {

    private volatile long refreshCount;

    @ManagedAttribute
    public long getRefreshCount() {
        return refreshCount;
    }

    public void recordRefresh() {
        refreshCount++;
    }
}
\`\`\`

### 6.2. Cấu hình dùng platform MBeanServer

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan(basePackageClasses = CacheMonitor.class)
@EnableMBeanExport(server = "jmxServer")
public class PlatformJmxConfig {

    @Bean
    public MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

Cấu hình dùng cùng server cho exporter và kiểm tra. Đây là cách hữu ích khi mục tiêu là xem MBean trên JConsole local.

### 6.3. Khởi chạy và kiểm tra

\`\`\`java
package example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class JmxServerProbe {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                     PlatformJmxConfig.class
                 )) {

            MBeanServer configured =
                context.getBean("jmxServer", MBeanServer.class);

            ObjectName name = new ObjectName(
                "learning.jmx:type=CacheMonitor,name=main"
            );

            System.out.println(
                "registered=" + configured.isRegistered(name)
            );
            System.out.println(
                "RefreshCount=" +
                    configured.getAttribute(name, "RefreshCount")
            );

            System.out.println(
                "PID=" + ProcessHandle.current().pid()
            );
            System.in.read();
        }
    }
}
\`\`\`

Khi context khởi tạo và export thành công, \`registered=true\`. Client JConsole kết nối đúng JVM thường tìm thấy \`learning.jmx:type=CacheMonitor,name=main\` trên platform server.

Điểm then chốt: \`context.getBean("jmxServer", MBeanServer.class)\` đọc **server được cấu hình tường minh**, chứ không chọn bất kỳ server nào theo tên domain.

## 7. Khi có MBeanServer tùy biến

Một ứng dụng có thể tạo riêng server:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "isolatedMBeanServer")
public class IsolatedJmxConfiguration {

    @Bean
    public MBeanServer isolatedMBeanServer() {
        return MBeanServerFactory.createMBeanServer(
            "isolated.management"
        );
    }
}
\`\`\`

Đối với cấu hình này, exporter nhắm tới \`isolatedMBeanServer\`. Nếu một client vẫn hỏi:

\`\`\`java
ManagementFactory.getPlatformMBeanServer()
\`\`\`

thì khả năng lớn sẽ không thấy MBean của exporter trên server riêng.

Để kiểm tra đúng:

\`\`\`java
MBeanServer actual =
    context.getBean(
        "isolatedMBeanServer",
        MBeanServer.class
    );

boolean found = actual.isRegistered(
    new ObjectName(
        "learning.jmx:type=CacheMonitor,name=main"
    )
);
\`\`\`

Lưu ý: domain mặc định đặt lúc tạo server không ép mọi MBean thuộc domain đó. MBean được đăng ký bằng \`ObjectName\` cụ thể vẫn có domain riêng như \`learning.jmx\`.

## 8. Xác minh bằng identity thay vì chỉ dựa vào tên

Nếu có hai biến:

\`\`\`java
MBeanServer platform =
    ManagementFactory.getPlatformMBeanServer();

MBeanServer configured =
    context.getBean("jmxServer", MBeanServer.class);
\`\`\`

có thể kiểm tra:

\`\`\`java
System.out.println(
    "sameInstance=" + (platform == configured)
);
\`\`\`

Phép so sánh \`==\` hữu ích khi bạn giữ đúng tham chiếu object local đã cấp cho exporter. Nó không phải là một cơ chế nhận diện server từ xa và không nên dùng với các object proxy/wrapper khác nhau.

Khi một MBeanServer được bọc bởi delegating proxy hoặc adapter, identity của wrapper có thể khác nhau dù truy cập cùng registry. Trong tình huống đó, kiểm tra tính hiện diện của MBean marker hoặc ObjectName cùng metadata thực tế sẽ có giá trị hơn.

## 9. Dùng marker MBean để phân biệt các server

Khi các server có nhiều MBean giống nhau, có thể đăng ký một MBean “marker” riêng cho môi trường kiểm thử.

### 9.1. Interface marker

\`\`\`java
package example.jmx;

public interface ServerMarkerMBean {
    String getMarker();
}
\`\`\`

### 9.2. Implementation

\`\`\`java
package example.jmx;

public class ServerMarker implements ServerMarkerMBean {

    private final String marker;

    public ServerMarker(String marker) {
        this.marker = marker;
    }

    @Override
    public String getMarker() {
        return marker;
    }
}
\`\`\`

### 9.3. Đăng ký vào server dự kiến

\`\`\`java
ObjectName markerName = new ObjectName(
    "learning.jmx:type=ServerMarker,name=probe"
);

configured.registerMBean(
    new ServerMarker("configured-server"),
    markerName
);
\`\`\`

Sau đó so sánh:

\`\`\`java
System.out.println(
    "configured=" + configured.isRegistered(markerName)
);

System.out.println(
    "platform=" + platform.isRegistered(markerName)
);
\`\`\`

Nếu chỉ configured server thấy marker, hai server không dùng cùng registry. Không đăng ký marker tùy tiện vào production; dùng tên không xung đột, có cleanup \`unregisterMBean\` và chỉ làm khi sở hữu server.

Marker cho biết server được code test truy cập, không tự chứng minh exporter đang dùng nó. Để chứng minh mối liên hệ exporter → server, hãy kết hợp với cấu hình \`setServer\` hoặc \`@EnableMBeanExport(server = "...")\` và một **MBean thực sự do exporter đăng ký**.

## 10. Quy trình xác minh exporter đang dùng server nào

Một chuỗi xác minh có thể thực hiện:

1. **Xác định exporter** trong Spring context: annotation exporter, explicit exporter hay auto-configuration.
2. **Xác định cấu hình server** của exporter: bean name trong \`@EnableMBeanExport\` hoặc object truyền vào \`setServer\`.
3. **Truy xuất đúng server** từ cấu hình, không đoán bằng platform server.
4. **Chọn ObjectName** của một MBean thực sự thuộc exporter.
5. **Gọi \`isRegistered\`** trên server đã truy xuất.
6. **Gọi \`getMBeanInfo\`** để xác nhận attribute/operation mà bean công bố.
7. **So sánh với platform server** khi cần chẩn đoán vì sao JConsole không thấy.
8. **Kiểm tra client connection**: JConsole/JMX connector đang trỏ tới registry nào.
9. **Ghi nhận kết quả** bằng ObjectName, server identity hoặc marker đã kiểm chứng.

\`\`\`text
Exporter config -> actual MBeanServer -> isRegistered(ObjectName)
                                 |
                                 v
                           getMBeanInfo
                                 |
                                 v
                     attribute/operation xác thực

Client config ----> MBeanServerConnection -> queryNames
                                 |
                                 v
                Đối chiếu có cùng registry hay không
\`\`\`

## 11. Phân biệt isRegistered, queryNames và getMBeanInfo

### isRegistered

\`\`\`java
boolean exists = server.isRegistered(name);
\`\`\`

Kiểm tra một ObjectName chính xác trên server hiện tại.

### queryNames

\`\`\`java
ObjectName pattern = new ObjectName(
    "learning.jmx:type=CacheMonitor,*"
);

Set<ObjectName> names =
    server.queryNames(pattern, null);
\`\`\`

Hữu ích khi không chắc các key properties bổ sung, ví dụ \`name=main\`, \`node=n1\`. \`queryNames\` trả về tập tên tại thời điểm truy vấn.

### getMBeanInfo

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);
\`\`\`

Giúp kiểm tra MBean thực sự công bố những attribute, operation và notification nào. \`isRegistered=true\` mới chỉ cho biết **có một MBean dưới tên đó**, chưa chắc là bean đúng mà bạn dự định export.

### Ghi chú về race

\`isRegistered\`, \`queryNames\`, \`getMBeanInfo\` là các thao tác riêng. MBean có thể bị unregister giữa những lời gọi. Với hệ thống có MBean động, client vẫn cần xử lý \`InstanceNotFoundException\`.

## 12. Nhiều exporter trong cùng ApplicationContext

Một ứng dụng có thể có:

\`\`\`text
Spring ApplicationContext
   |
   +-- AnnotationMBeanExporter -> Server A
   |
   +-- Explicit MBeanExporter  -> Server B
\`\`\`

Trường hợp này dễ gây nhầm:

- Một bean có thể bị export bởi hơn một exporter nếu cấu hình trùng.
- Một ObjectName có thể được đăng ký trên Server A nhưng không có trên Server B.
- Các client quan sát hai server khác nhau có thể thấy danh sách MBean khác nhau.
- Việc hai exporter dùng cùng server và cùng ObjectName gây xung đột registration.
- \`RegistrationPolicy.REPLACE_EXISTING\` không phải cách sửa mặc định cho cấu hình trùng exporter.

Nếu Spring Boot đã tự cấu hình exporter mà bạn thêm \`@EnableMBeanExport\` hoặc \`MBeanExporter\` thủ công, cần xác định rõ exporter nào là nguồn đăng ký chính. Tùy phiên bản Spring Boot, JMX auto-configuration có thể được bật/tắt bằng property phù hợp; không suy luận chỉ từ tên property mà không quan sát context thực tế.

## 13. Tìm exporter trong Spring context

Có thể kiểm kê bean theo kiểu:

\`\`\`java
import java.util.Map;
import org.springframework.jmx.export.MBeanExporter;

Map<String, MBeanExporter> exporters =
    context.getBeansOfType(MBeanExporter.class);

exporters.forEach((name, exporter) ->
    System.out.println(
        "Exporter bean: " + name
            + ", class=" + exporter.getClass().getName()
    )
);
\`\`\`

\`AnnotationMBeanExporter\` là một dạng exporter, nên có thể xuất hiện trong kết quả khi thuộc hệ kế thừa phù hợp.

Danh sách này cho biết exporter nào **được Spring context biết tới**, nhưng không tự nêu được chính xác server bên trong nếu không có API public để lấy. Đối với server được chọn ngầm, hãy kết hợp bằng chứng từ cấu hình, Spring startup/logging và các MBean đã đăng ký.

Không nên dùng reflection để đọc private field của exporter chỉ nhằm xác định server trong một ứng dụng production. Cấu hình tường minh thường dễ kiểm chứng và bảo trì hơn.

## 14. Dùng cấu hình tường minh để loại bỏ mơ hồ

Nếu bạn kiểm soát exporter, cách đáng tin cậy nhất là cấp một server rõ ràng:

\`\`\`java
@Configuration
public class ExplicitJmxConfiguration {

    @Bean
    public MBeanServer managementServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter exporter(
            MBeanServer managementServer,
            CacheManagementFacade facade
    ) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(managementServer);
        exporter.setBeans(Map.of(
            "app.management:type=Cache,name=primary",
            facade
        ));
        return exporter;
    }
}
\`\`\`

Đây là lựa chọn manual exporter. Nếu dùng annotation-driven export, có thể thay bằng \`@EnableMBeanExport(server = "managementServer")\` và metadata phù hợp.

Đừng vô tình sử dụng cả hai cách cho cùng bean/ObjectName trong cùng MBeanServer.

## 15. Kiểm tra kết nối JConsole và remote connector

### Local JConsole

JConsole thường kết nối tới JVM theo PID và hiển thị MBeans trong platform management server được JMX agent cung cấp. Nếu custom server riêng không được expose cho đường attach đó, MBean của nó không tự động xuất hiện.

Quy trình:

1. Chạy ứng dụng, ghi PID.
2. Chạy \`jconsole\` từ JDK và chọn đúng local JVM.
3. Mở tab MBeans.
4. Tìm domain và ObjectName.
5. Nếu không thấy, xác minh MBean trên server được exporter sử dụng bằng code.
6. Nếu server khác platform, quyết định dùng platform server hoặc cung cấp connector phù hợp.

### Remote JMX

Một \`JMXConnectorServer\` có thể được liên kết với một MBeanServer cụ thể. Client nhận \`MBeanServerConnection\` từ connector đó và thấy registry của server được connector expose.

\`\`\`text
Remote client
   |
   v
JMXConnector
   |
   v
MBeanServerConnection
   |
   v
Server được connector cấu hình
\`\`\`

Chỉ biết cùng URL host hoặc cùng JVM không đủ chứng minh exporter và connector chia sẻ registry. Phải xác nhận connector trỏ tới server nào, hoặc đối chiếu marker/MBean thực sự trong registry.

\`@EnableMBeanExport\` không tự mở remote JMX connector. Khi bật remote, phải cấu hình authentication, authorization, TLS và giới hạn truy cập mạng thích hợp.

## 16. Kiểm thử hai server khác nhau

Một bài test không gây tác động vào platform server có thể tạo hai MBeanServer riêng:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer first =
    MBeanServerFactory.newMBeanServer("first");

MBeanServer second =
    MBeanServerFactory.newMBeanServer("second");

ObjectName name = new ObjectName(
    "test.management:type=ServerMarker,name=probe"
);

first.registerMBean(
    new ServerMarker("first"),
    name
);

System.out.println(first.isRegistered(name));  // true
System.out.println(second.isRegistered(name)); // false
\`\`\`

Chính kết quả này cho thấy ObjectName không phải một địa chỉ toàn cục trong JVM; nó chỉ có ý nghĩa trong registry của server tương ứng.

Khi kết thúc test, unregister marker do test tạo. Không áp dụng thao tác xóa MBean vào server production nếu không xác định được ownership.

## 17. Tình huống client không tìm thấy MBean

### Tình huống A: Exporter dùng custom server

**Dấu hiệu:** code kiểm tra trên custom server trả \`true\`, JConsole local không thấy.

**Cách xử lý:** dùng cùng MBeanServer cho exporter và công cụ, hoặc cấu hình connector truy cập custom server.

### Tình huống B: Có hai Spring context

**Dấu hiệu:** context A có exporter và MBeanServer A, context B có MBeanServer B.

**Cách xử lý:** xác nhận nơi bean được tạo và nơi exporter đăng ký, không coi hai context cùng JVM là dùng chung registry.

### Tình huống C: Exporter chưa chạy

**Dấu hiệu:** bean Spring tồn tại nhưng không có ObjectName trên bất kỳ server dự kiến nào.

**Cách xử lý:** kiểm tra \`@EnableMBeanExport\`, bean discovery, annotation metadata, exporter lifecycle và exception trong startup.

### Tình huống D: Sai ObjectName

**Dấu hiệu:** domain hoặc key properties khác dự kiến.

**Cách xử lý:** truy vấn \`queryNames\` trên server đúng, sau đó đọc \`getCanonicalName()\` và metadata. Không tự suy đoán từ tên class hoặc Spring bean name.

### Tình huống E: Hai exporter giành cùng tên

**Dấu hiệu:** startup có lỗi registration hoặc MBean thay đổi bất ngờ.

**Cách xử lý:** kiểm kê exporter trong context, ownership và RegistrationPolicy, sau đó loại bỏ cấu hình trùng ngoài chủ đích.

### Tình huống F: Remote connector chưa bật

**Dấu hiệu:** local code thấy MBean nhưng remote JConsole không kết nối được.

**Cách xử lý:** cấu hình JMX connector, cổng/địa chỉ mạng, xác thực và TLS phù hợp; đừng xem đây là bằng chứng export thất bại.

## 18. Logging và quan sát tại startup

Trong môi trường nhiều server, nên ghi lại bằng chứng có ích khi ứng dụng khởi tạo:

\`\`\`text
JMX export configuration:
  exporter = annotationMBeanExporter
  serverBean = managementServer
  serverMode = platform
  expectedObjectName = app.management:type=Cache,name=primary
  registered = true
\`\`\`

Đây là mẫu log mong muốn do ứng dụng tự phát, không phải log mà Spring luôn in mặc định. Chỉ ghi dữ liệu cấu hình không nhạy cảm, không dump credentials, userData hoặc object graph.

Đặt health check hoặc startup assertion trong phần quản trị có thể giúp phát hiện exporter vô tình chuyển server sau refactor, đổi cấu hình hoặc thêm một thư viện quản trị khác.

Ví dụ assertion:

\`\`\`java
ObjectName expected = new ObjectName(
    "app.management:type=Cache,name=primary"
);

if (!managementServer.isRegistered(expected)) {
    throw new IllegalStateException(
        "JMX MBean missing on configured server: " + expected
    );
}
\`\`\`

Thực hiện assertion **sau khi exporter hoàn tất registration**. Nếu chạy trong \`@PostConstruct\` của bean nghiệp vụ quá sớm, nó có thể báo lỗi do thứ tự lifecycle chứ không phải exporter đăng ký sai.

## 19. Cân nhắc lifecycle và quyền sở hữu

Khi exporter đăng ký MBean, nó cũng có thể quản lý việc hủy đăng ký khi Spring context đóng. Nếu có custom MBeanServer, cần biết ai tạo và ai chịu trách nhiệm giải phóng server.

Một số điểm vận hành:

- Tránh gọi \`MBeanServerFactory.releaseMBeanServer\` cho server không do module của bạn tạo.
- Không unregister MBean của thành phần khác chỉ vì muốn làm sạch registry.
- Với test, tạo server riêng và xóa đúng các MBean test đã tạo.
- Với application context nhiều tầng, xác định exporter/context nào sở hữu registration.
- Với connector remote, đóng connector server/client theo lifecycle phù hợp.
- Dùng ObjectName duy nhất, nhưng đừng dùng naming policy như một phương án che giấu server selection sai.

Mục tiêu là tránh tình huống “MBean biến mất” vì client đang quan sát server khác, không phải do exporter thực sự unregister.

## 20. Bài tập thực hành

Một ứng dụng có hai server:

\`\`\`java
MBeanServer platform =
    ManagementFactory.getPlatformMBeanServer();

MBeanServer isolated =
    MBeanServerFactory.newMBeanServer("isolated");
\`\`\`

Spring exporter đăng ký \`app.management:type=Queue,name=orders\` vào \`isolated\`.

**Câu 1:** \`platform.isRegistered(name)\` có bắt buộc trả \`true\` không?

Không. Hai server có registry riêng.

**Câu 2:** Vì sao JConsole local có thể không thấy MBean?

Vì JConsole thường quan sát platform server, trong khi exporter đăng ký trên isolated server.

**Câu 3:** Nên kiểm tra điều gì đầu tiên?

Xác định cấu hình exporter được gán server nào; truy vấn \`isRegistered\` trên đúng instance ấy.

**Câu 4:** Nếu muốn JConsole local thấy MBean, có thể làm gì?

Cấu hình exporter dùng platform MBeanServer khi phù hợp, hoặc cung cấp connector/cơ chế truy cập tới server tùy biến.

**Câu 5:** Nếu client remote đã kết nối được tới JVM nhưng không thấy MBean, điều đó chứng minh exporter lỗi không?

Không. Connector có thể expose server khác. Cần so sánh registry mà connector cung cấp với server exporter dùng.

## 21. Câu hỏi tự kiểm tra

1. ObjectName có phải định danh toàn cục cho mọi MBeanServer trong cùng JVM không?
2. \`ManagementFactory.getPlatformMBeanServer()\` có luôn là server của Spring exporter không?
3. \`@EnableMBeanExport(server = "managementServer")\` nhận tên bean hay hostname?
4. \`MBeanExporter.setServer\` nhận loại đối tượng nào?
5. Vì sao \`isRegistered\` phải gọi trên đúng server?
6. Tác dụng của \`MBeanInfo\` sau khi đã thấy ObjectName là gì?
7. Marker MBean chứng minh điều gì, và điều gì nó chưa chứng minh?
8. Vì sao nhiều exporter trong một context dễ làm kết quả JMX khó dự đoán?
9. \`MBeanServerFactory.createMBeanServer\` và \`newMBeanServer\` khác nhau ở khả năng discovery nào?
10. Nếu local JConsole không thấy MBean nhưng custom server có đăng ký, bước xử lý hợp lý tiếp theo là gì?

## 22. Ghi nhớ

\`\`\`text
Spring bean
    |
    v
MBeanExporter
    |
    | phải xác định
    v
MBeanServer thực tế
    |
    +-- isRegistered(ObjectName)
    +-- queryNames(pattern)
    +-- getMBeanInfo(ObjectName)
    |
    v
JMX client/connector phải quan sát CÙNG registry
\`\`\`

**Nguyên tắc cốt lõi:** đừng suy luận server của exporter chỉ từ việc JVM có platform MBeanServer hoặc từ kết quả JConsole. Cấu hình server tường minh, kiểm chứng một ObjectName do exporter đăng ký trên đúng registry, rồi đối chiếu với đường kết nối của client. Khi exporter và client không dùng cùng MBeanServer, MBean có thể được export thành công mà vẫn “vô hình” với công cụ đang quan sát.