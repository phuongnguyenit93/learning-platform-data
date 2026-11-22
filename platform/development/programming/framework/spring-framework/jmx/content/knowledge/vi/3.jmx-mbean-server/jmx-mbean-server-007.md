# MBeanServer nền tảng và MBeanServer do ứng dụng tạo

## 1. MBeanServer là gì?

Trong Java Management Extensions (JMX), \`MBeanServer\` là nơi đăng ký, tra cứu và thao tác với các MBean (Managed Bean). Một MBean đại diện cho khả năng quan sát hoặc điều khiển một thành phần như bộ nhớ, thread, cache, job hoặc dịch vụ nghiệp vụ. Client dùng \`ObjectName\` để tìm MBean, đọc/ghi attribute và gọi operation qua \`MBeanServer\` hoặc một JMX connector.

Cùng một JVM có thể tồn tại nhiều \`MBeanServer\`. Hai lựa chọn phổ biến là:

- **Platform MBeanServer**: instance dùng chung được JVM cung cấp qua \`ManagementFactory.getPlatformMBeanServer()\`. Java platform MXBeans và nhiều thư viện quản trị thường dùng instance này.
- **Application-created MBeanServer**: instance do ứng dụng hoặc framework tạo qua \`MBeanServerFactory.createMBeanServer(domain)\` hoặc cách cấu hình tương đương. Nó có vùng đăng ký MBean riêng, không tự động chứa toàn bộ MXBean của platform server.

Điểm cần hiểu: **MBeanServer là sổ đăng ký và bộ điều phối trong tiến trình JVM; JMX remote connector là con đường để một client ở bên ngoài truy cập nó.** Tạo một MBeanServer không đồng nghĩa mở cổng mạng.

## 2. So sánh hai cách chọn server

| Tiêu chí | Platform MBeanServer | Application-created MBeanServer |
| --- | --- | --- |
| Cách lấy | \`ManagementFactory.getPlatformMBeanServer()\` | \`MBeanServerFactory.createMBeanServer("com.example.app")\` |
| Chủ sở hữu | JVM và các thành phần chia sẻ platform server | Ứng dụng/framework tạo và quản lý vòng đời |
| Nội dung ban đầu | Platform MXBeans cho JVM | Thường là registry mới, tách khỏi platform MBeans |
| Phạm vi ObjectName | Chia sẻ namespace đăng ký với các thư viện dùng platform server | Namespace đăng ký riêng cho server này |
| Công cụ kết nối | Công cụ local JMX thường có thể truy cập platform server theo cấu hình JVM | Cần công bố/đưa server đó vào connector thích hợp nếu muốn client ngoài truy cập |
| Tình huống phù hợp | Quản trị JVM và ứng dụng trong một điểm chung; lựa chọn phổ biến | Cách ly tập MBean của subsystem, nhúng một môi trường quản trị riêng, kiểm thử |
| Rủi ro chính | Xung đột \`ObjectName\`; phơi bày quá nhiều MBean nếu cấu hình connector rộng | Tưởng rằng công cụ JMX sẽ tự phát hiện; vòng đời và connector phải tự quản lý |

\`defaultDomain\` của server không phải một cơ chế phân quyền, không tạo tenant isolation về bảo mật. Các domain trong \`ObjectName\` là tên logic; đăng ký cùng \`ObjectName\` trên hai server khác nhau vẫn là hai bản ghi độc lập.

## 3. Platform MBeanServer: chọn khi muốn dùng hệ sinh thái JVM

Ví dụ lấy server nền tảng và truy vấn JVM MXBean chuẩn:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class PlatformServerExample {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        ObjectName memory = new ObjectName("java.lang:type=Memory");

        System.out.println("Registered: " + server.isRegistered(memory));
        System.out.println("HeapMemoryUsage: " +
                server.getAttribute(memory, "HeapMemoryUsage"));
    }
}
\`\`\`

\`HeapMemoryUsage\` là một thuộc tính của Memory MXBean được ánh xạ qua JMX; client đọc dữ liệu mà không cần phụ thuộc vào class cài đặt của JVM. Lưu ý \`javax.management\` là namespace JMX thuộc Java SE; không thay bằng \`jakarta.management\` chỉ vì ứng dụng dùng Spring Framework phiên bản mới hoặc Jakarta EE.

Ưu điểm của platform server là tập trung quan sát JVM và MBean ứng dụng, thuận tiện cho JConsole, VisualVM và hệ thống monitor đã kết nối platform server. Nhược điểm là nhiều subsystem cùng chia sẻ một registry, vì thế đặt tên và quản lý quyền phải nhất quán.

## 4. Tạo một MBeanServer riêng

Ứng dụng có thể tạo registry riêng:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

public class PrivateServerExample {
    public static void main(String[] args) throws Exception {
        MBeanServer privateServer =
                MBeanServerFactory.createMBeanServer("com.example.private");

        try {
            ObjectName name = new ObjectName(
                "com.example.private:type=Counter,name=Operations"
            );

            privateServer.registerMBean(new Counter(), name);
            System.out.println(privateServer.getAttribute(name, "Count"));
        } finally {
            MBeanServerFactory.releaseMBeanServer(privateServer);
        }
    }

    public interface CounterMBean {
        int getCount();
        void reset();
    }

    public static class Counter implements CounterMBean {
        private int count = 42;
        public int getCount() { return count; }
        public void reset() { count = 0; }
    }
}
\`\`\`

Đây là **Standard MBean**: interface công khai mang hậu tố \`MBean\` ứng với implementation. Với code production, nên đặt interface và implementation ở các lớp top-level hoặc static public rõ ràng, cung cấp thread-safety cho trạng thái mutable và unregister MBean theo vòng đời trước khi release server.

\`MBeanServerFactory.createMBeanServer()\` tạo server và đưa nó vào danh sách server mà factory theo dõi; \`newMBeanServer()\` tạo server nhưng không thêm vào danh sách ấy. \`releaseMBeanServer()\` chỉ thích hợp cho server tạo bằng \`createMBeanServer()\`, không dùng cho platform server. Release khỏi factory không thay thế việc đóng connector hoặc dọn toàn bộ tài nguyên do ứng dụng sở hữu.

**Tách registry không có nghĩa tách bộ nhớ hoặc process.** Những MBean trên hai server vẫn chạy trong cùng JVM, có thể tham chiếu tới cùng service hoặc trạng thái nếu bạn chủ động cung cấp. Nếu một connector chỉ trỏ tới server A, client của connector đó sẽ không tự nhìn thấy registry B.

## 5. Cách Spring Framework tìm và dùng MBeanServer

Trong Spring JMX, \`MBeanExporter\` chịu trách nhiệm xuất các bean thành MBean và đăng ký chúng với một \`MBeanServer\`. Spring có thể tìm server hiện có bằng \`MBeanServerFactoryBean\` hoặc sử dụng một bean server cụ thể được inject. Quyết định quan trọng là **xác định chính xác exporter đang dùng instance nào**.

Ví dụ Spring configuration chọn platform server một cách tường minh:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class PlatformJmxConfig {
    @Bean
    public MBeanExporter mbeanExporter(ExampleAdminMBean admin) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(ManagementFactory.getPlatformMBeanServer());
        exporter.setBeans(
            java.util.Map.of("com.example:type=ExampleAdmin", admin)
        );
        return exporter;
    }
}
\`\`\`

Đối tượng được đăng ký phải tuân theo mô hình MBean hợp lệ (Standard MBean, MXBean, DynamicMBean hoặc đã được assembler của Spring hỗ trợ). Khi dùng annotation \`@ManagedResource\`, cần cấu hình metadata assembler/naming strategy phù hợp hoặc sử dụng auto-configuration được cung cấp.

Ví dụ dùng server riêng và chỉ định exporter:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class IsolatedJmxConfig {
    @Bean(destroyMethod = "")
    public MBeanServer isolatedMBeanServer() {
        return MBeanServerFactory.createMBeanServer(
            "com.example.isolated"
        );
    }

    @Bean
    public MBeanExporter isolatedExporter(
            MBeanServer isolatedMBeanServer,
            ExampleAdminMBean admin) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(isolatedMBeanServer);
        exporter.setBeans(
            java.util.Map.of("com.example.isolated:type=ExampleAdmin", admin)
        );
        return exporter;
    }
}
\`\`\`

Trong cấu hình thứ hai, \`destroyMethod=""\` không giải phóng server; đó chỉ là cách tránh suy diễn một destroy method của bean. Nếu ứng dụng sở hữu server này, hãy quản lý cleanup tường minh bằng lifecycle bean, gọi \`MBeanServerFactory.releaseMBeanServer(server)\` ở lúc đóng context sau khi exporter đã unregister MBean; đồng thời đóng các JMXConnectorServer do ứng dụng tạo. Với môi trường production, ưu tiên cấu hình vòng đời gọn để tránh tài nguyên còn đăng ký khi tạo lại context.

Spring Boot có thể tự tạo cấu hình JMX khi bật \`spring.jmx.enabled=true\`. Khi đã có \`MBeanExporter\` do Boot cấu hình, không tạo thêm exporter cùng quản lý tập MBean nếu không chủ ý; có thể dẫn đến đăng ký trùng hoặc exporter trỏ nhầm server. Kiểm tra bean \`MBeanServer\`, \`MBeanExporter\` và tính tương thích với phiên bản Boot thực tế.

## 6. Đăng ký cùng ObjectName trên hai server khác nhau

Một \`ObjectName\` được định danh trong **một MBeanServer**; không có namespace toàn JVM độc lập với server.

\`\`\`java
MBeanServer platform =
        java.lang.management.ManagementFactory.getPlatformMBeanServer();
MBeanServer isolated =
        javax.management.MBeanServerFactory.createMBeanServer("custom");

ObjectName name =
        new ObjectName("com.example:type=Cache,name=Local");

// Có thể tồn tại trên cả hai registry nếu mỗi registration hợp lệ.
platform.registerMBean(new CacheAdmin(), name);
isolated.registerMBean(new CacheAdmin(), name);
\`\`\`

Đây là hai đăng ký tách biệt. Nhưng đăng ký \`name\` lần hai trên **cùng một server** sẽ gây \`InstanceAlreadyExistsException\`, trừ khi framework dùng chính sách xử lý collision mà bạn cấu hình. Không nên dựa vào chế độ thay thế MBean mặc định nếu chưa hiểu ảnh hưởng của nó đến tiến trình vận hành.

Khi cần xem server nào đang giữ MBean, hãy kiểm tra trên chính instance:

\`\`\`java
boolean inPlatform = platform.isRegistered(name);
boolean inIsolated = isolated.isRegistered(name);
\`\`\`

## 7. Vì sao công cụ bên ngoài có thể không thấy MBean?

Tình huống thường gặp: application log nói “MBean registered” nhưng JConsole không hiện mục tương ứng.

Hãy lần theo các ranh giới:

1. **Đúng JVM chưa?** JConsole/VisualVM đang attach tới process nào?
2. **Đúng server chưa?** Bean nằm trong platform server hay server riêng? Dùng chính instance đã truyền vào exporter để gọi \`isRegistered(name)\`.
3. **Tên đúng chưa?** \`ObjectName\` phải khớp domain và key properties. Dùng \`queryNames(pattern, null)\` để dò trong đúng server.
4. **Connector đang trỏ đâu?** Connector được tạo với \`MBeanServer\` nào thì chỉ xuất registry ấy.
5. **Có quyền đọc không?** Connector có thể yêu cầu authentication, TLS và phân quyền. Không tắt bảo mật để chẩn đoán production.
6. **Lúc nào đăng ký?** Bean/exporter có thể được tạo sau khi client kết nối hoặc đã unregister khi đóng Spring context.

Ví dụ truy vấn những tên đang được đăng ký:

\`\`\`java
ObjectName pattern = new ObjectName("com.example:*");

for (ObjectName candidate : platform.queryNames(pattern, null)) {
    System.out.println(candidate);
}
\`\`\`

Nếu query trên platform server trống nhưng trên isolated server có kết quả thì đây là khác biệt registry, không phải sự cố của MBean.

## 8. Kết nối từ xa với server riêng

Một \`JMXConnectorServer\` nhận một \`MBeanServer\` cụ thể. Ví dụ API cốt lõi:

\`\`\`java
import java.util.Map;
import javax.management.MBeanServer;
import javax.management.remote.JMXConnectorServer;
import javax.management.remote.JMXConnectorServerFactory;
import javax.management.remote.JMXServiceURL;

MBeanServer server = /* isolated server đã tạo */ null;
JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi"
);

// Minh họa chữ ký API; URL RMI/JNDI cần registry và cấu hình mạng phù hợp.
// Không dùng môi trường Map rỗng làm cấu hình remote production.
JMXConnectorServer connector =
    JMXConnectorServerFactory.newJMXConnectorServer(
        url, Map.of(), server
    );
\`\`\`

Đoạn này minh họa điểm gắn \`server\`, **không phải cấu hình có thể chạy ngay**: cần khởi tạo RMI registry, gán server thật, start/stop connector và thiết lập xác thực, TLS, hạn chế cổng/host. Trong triển khai thật, tránh vô tình phơi JMX ra Internet và không để operation nguy hiểm truy cập công khai.

Nếu chỉ muốn JMX nội bộ qua local attach, thường không cần connector từ xa. Nếu muốn giám sát JVM lẫn app trong một kết nối, platform server thường là lựa chọn trực tiếp hơn.

## 9. Kiểm thử sự tách biệt và vòng đời

Một phép kiểm thử hữu ích là tạo server riêng, đăng ký MBean rồi khẳng định platform server không chứa tên đó:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

class MBeanServerIsolationTest {
    @Test
    void registrationIsScopedToOneServer() throws Exception {
        MBeanServer isolated =
            MBeanServerFactory.createMBeanServer("test");
        ObjectName name =
            new ObjectName("com.example.test:type=Counter,name=One");

        try {
            isolated.registerMBean(new PrivateServerExample.Counter(), name);

            assertTrue(isolated.isRegistered(name));
            assertFalse(
                ManagementFactory.getPlatformMBeanServer()
                    .isRegistered(name)
            );
        } finally {
            if (isolated.isRegistered(name)) {
                isolated.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(isolated);
        }
    }
}
\`\`\`

Trong dự án thật, dùng tên duy nhất cho phép thử, không giả định platform server chắc chắn sạch nếu test khác chạy song song và không dùng lại tên đã có. Cần kiểm tra startup/shutdown của Spring context để chắc chắn exporter đăng ký và unregister trên **cùng một MBeanServer**.

Một bộ kiểm thử tích hợp nên xác nhận: server được chọn đúng, MBean có \`ObjectName\` mong đợi, attribute/operation thực hiện được, collision xử lý như thiết kế, và resources được giải phóng sau khi context đóng.

## 10. Quyết định kiến trúc theo nhu cầu

**Chọn platform server** khi cần quan sát JVM và ứng dụng cùng chỗ, tương thích tốt với tooling và không có yêu cầu cách ly registry đặc biệt. Đây thường là phương án đơn giản cho ứng dụng Spring đơn JVM.

**Chọn server riêng** khi thật sự cần vùng đăng ký riêng cho một module, embedded container, phần mềm host nhiều subsystem hoặc một ứng dụng test cần setup/teardown độc lập. Việc chọn này đồng thời kéo theo trách nhiệm quản lý exporter, connector và lifecycle.

Không dùng server riêng như lớp bảo vệ dữ liệu duy nhất. Bảo mật JMX phải được thiết kế ở connector/transport, quyền truy cập, thao tác được phép, network policy và cơ chế xác thực của ứng dụng.

## 11. Lỗi tư duy hay gặp

- **“Mỗi JVM chỉ có một MBeanServer.”** Sai: có thể tạo nhiều registry, nhưng platform server là instance chuẩn được dùng rộng rãi.
- **“Có MBeanServer là JConsole sẽ thấy.”** Sai: client nhìn registry mà connector/attach cho phép truy cập.
- **“Cùng ObjectName là cùng MBean.”** Sai khi ObjectName ở hai server khác nhau.
- **“Đổi default domain là tách biệt an toàn.”** Sai: domain là cách đặt tên, không phải chính sách bảo mật.
- **“Release server sẽ đóng tất cả connector.”** Không nên giả định; quản lý tài nguyên sở hữu riêng.
- **“Spring luôn chọn đúng server mình nghĩ.”** Không nên giả định; cấu hình hoặc inject instance tường minh khi có nhiều server.

## 12. Ghi nhớ

\`MBeanServer\` là phạm vi đăng ký MBean. **Platform MBeanServer** là điểm quản trị JVM phổ biến và thuận tiện; **MBeanServer do ứng dụng tạo** là một registry độc lập cần quản lý riêng. Khi dùng Spring, hãy xác định exporter đăng ký vào server nào, client kết nối tới server nào và vòng đời registration/connector ra sao. Hiểu đúng ba mối quan hệ đó giải quyết phần lớn sự cố “đã export MBean nhưng không thấy” và tránh vô tình ràng buộc kiến trúc với một kênh quản trị.
