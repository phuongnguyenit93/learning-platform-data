# Đăng ký MBean ở JVM local và khả năng truy cập của tiến trình khác

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích MBean được đăng ký vào **MBeanServer của một JVM** như thế nào và vì sao đăng ký thành công không đồng nghĩa tiến trình khác tự động truy cập được.
- Phân biệt ba vai trò: đối tượng MBean, MBeanServer và JMX client/JMX connector.
- Hiểu sự khác nhau giữa truy cập từ chính JVM, truy cập local từ tiến trình khác trên cùng máy và kết nối từ máy khác.
- Đăng ký, tìm, gọi thuộc tính/thao tác và hủy đăng ký một MBean bằng Java hoặc Spring Framework.
- Chẩn đoán vấn đề khi một MBean hiển thị trong tiến trình nhưng không xuất hiện ở công cụ bên ngoài, đồng thời thiết kế quyền truy cập quản trị an toàn.

## 1. Mô hình tư duy: nơi đăng ký khác với đường truy cập

Điểm quan trọng nhất của chủ đề này:

> **MBean được đăng ký vào một MBeanServer bên trong JVM. Khả năng quan sát hoặc gọi nó từ tiến trình khác phụ thuộc vào cơ chế kết nối JMX, khả năng truy cập tiến trình, cấu hình bảo mật và môi trường chạy.**

Hình dung hai lớp:

1. **Lớp đăng ký nội bộ:** một ứng dụng Java tạo MBean và đưa nó vào MBeanServer theo một ObjectName.
2. **Lớp truy cập từ bên ngoài:** một client muốn truy cập MBeanServer đó phải có đường kết nối hợp lệ, chẳng hạn cơ chế attach/local management hoặc một JMX connector được cấu hình.

Đăng ký MBean là hành động của JVM đang chạy. Nó **không tạo HTTP API**, không tự mở cổng mạng, không tự biến object thành đối tượng công khai trên toàn hệ thống.

Sơ đồ:

\`\`\`text
JVM A — tiến trình ứng dụng
┌──────────────────────────────────────────────────────┐
│ Java/Spring component                                │
│       │                                              │
│       ▼                                              │
│    MBean ── registerMBean(...) ──► MBeanServer        │
│                                  │                   │
│                                  ├── local Java code │
│                                  └── JMX connector   │
└──────────────────────────────────┬───────────────────┘
                                   │ kết nối hợp lệ
                                   ▼
JVM B — công cụ quản trị/JMX client
  JConsole / VisualVM / custom client
\`\`\`

Một client ở JVM B không thể trực tiếp gọi phương thức Java trên object thuộc heap của JVM A. Client tương tác qua giao thức/kết nối quản trị, MBeanServer bên JVM A phân giải ObjectName và thực thi thao tác trong tiến trình của nó.

## 2. MBeanServer và ObjectName là gì?

**MBeanServer** quản lý đăng ký các MBean trong một JVM. Client có thể dùng nó để:

- Liệt kê hoặc truy vấn tên MBean.
- Đọc/ghi thuộc tính theo quyền và khả năng MBean công bố.
- Gọi operation.
- Đăng ký hoặc hủy đăng ký MBean nếu có quyền.
- Đăng ký listener cho notification khi được hỗ trợ.

**ObjectName** là định danh quản trị, ví dụ:

\`\`\`text
learning.jmx:type=JobQueue,name=Primary
\`\`\`

Trong đó:

- \`learning.jmx\` là domain.
- \`type=JobQueue\` và \`name=Primary\` là các key property.
- Tên phải tuân theo cú pháp ObjectName; cùng một MBeanServer không thể đăng ký hai MBean trùng ObjectName.

Lưu ý ObjectName **không phải URL hoặc tên mạng**. Cùng một ObjectName có thể tồn tại độc lập trong hai JVM khác nhau; cần xác định đúng JVM/connector để tránh thao tác nhầm instance.

Mỗi JVM có thể có nhiều MBeanServer, dù các công cụ chuẩn thường truy cập **platform MBeanServer** do \`ManagementFactory.getPlatformMBeanServer()\` trả về. Những MBean đăng ký ở MBeanServer tùy biến không nhất thiết được hiển thị qua connector trỏ tới platform server.

## 3. Đăng ký MBean trực tiếp trong một JVM

Một Standard MBean có interface với tên kết thúc bằng \`MBean\` tương ứng lớp triển khai. Ví dụ dưới đây tạo bộ đếm nhiệm vụ đã hoàn thành.

### 3.1. Contract quản trị

\`\`\`java
package example.management;

public interface JobCounterMBean {
    long getCompletedJobs();
    void reset();
}
\`\`\`

\`getCompletedJobs()\` được biểu diễn như attribute có thể đọc, còn \`reset()\` là operation. Việc xuất hiện trong interface quản trị mới quyết định tính năng nào được công bố; public method bất kỳ của lớp không tự động trở thành JMX operation.

### 3.2. Lớp triển khai

\`\`\`java
package example.management;

import java.util.concurrent.atomic.AtomicLong;

public class JobCounter implements JobCounterMBean {
    private final AtomicLong completedJobs = new AtomicLong();

    @Override
    public long getCompletedJobs() {
        return completedJobs.get();
    }

    public void recordJobCompleted() {
        completedJobs.incrementAndGet();
    }

    @Override
    public void reset() {
        completedJobs.set(0);
    }
}
\`\`\`

\`recordJobCompleted()\` chỉ phục vụ ứng dụng; nó không thuộc \`JobCounterMBean\`, nên không phải operation của Standard MBean này.

### 3.3. Đăng ký và hủy đăng ký

\`\`\`java
package example.management;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class RegisterLocalMBean {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name =
                new ObjectName("learning.jmx:type=JobCounter,name=Primary");

        JobCounter counter = new JobCounter();

        server.registerMBean(counter, name);

        System.out.println("Registered: " + server.isRegistered(name));
        System.out.println("MBean count: " + server.getMBeanCount());

        // Công việc thực tế có thể tiếp tục tại đây.
        counter.recordJobCompleted();

        // Chỉ hủy đăng ký khi không còn cần giao diện quản trị.
        server.unregisterMBean(name);
    }
}
\`\`\`

Các lệnh trên thực hiện **đăng ký nội bộ**. Để thử bằng JConsole, hãy giữ JVM chạy trong lúc quan sát, chẳng hạn đặt logic trong ứng dụng máy chủ có vòng đời đủ dài. Ví dụ \`main\` ngắn chỉ minh họa API đăng ký/hủy đăng ký; nó thoát quá nhanh để kết nối công cụ bên ngoài.

Nếu \`registerMBean\` gặp ObjectName đã được dùng, API sẽ báo \`InstanceAlreadyExistsException\`. Nếu đối tượng không tuân theo quy tắc MBean, có thể gặp \`NotCompliantMBeanException\`. Nếu hủy đăng ký tên không tồn tại, có thể gặp \`InstanceNotFoundException\`.

## 4. Truy cập MBean từ code trong cùng JVM

Đối với code cùng tiến trình, có thể sử dụng trực tiếp MBeanServer:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name =
        new ObjectName("learning.jmx:type=JobCounter,name=Primary");

if (server.isRegistered(name)) {
    Object value = server.getAttribute(name, "CompletedJobs");

    System.out.println("Completed jobs: " + value);

    server.invoke(
            name,
            "reset",
            new Object[0],
            new String[0]
    );
}
\`\`\`

Tên attribute \`CompletedJobs\` được suy ra từ getter \`getCompletedJobs()\` trong Standard MBean interface. Dù ví dụ dùng object cùng JVM, phần code vẫn tương tác qua giao diện quản trị MBeanServer thay vì tham chiếu trực tiếp tới \`JobCounter\`.

Nếu cần gọi trực tiếp một component nghiệp vụ trong cùng ứng dụng, thông thường inject/service method là cách tự nhiên hơn. JMX có ích khi cần một contract quản trị chung cho tooling và các nhà vận hành.

## 5. JVM khác trên cùng máy có tự nhìn thấy MBean không?

**Không tự động.** MBeanServer không phải một registry toàn máy. Mỗi JVM có không gian bộ nhớ và danh sách MBean riêng.

Tuy nhiên các công cụ JDK như **JConsole** có khả năng phát hiện một số JVM local và dùng cơ chế attach/local management được JDK hỗ trợ để kết nối, tùy hệ điều hành, nhà cung cấp JVM, quyền người dùng và cấu hình bảo mật. Vì thế một ứng dụng chưa chủ động cấu hình JMX port vẫn có thể được công cụ quản trị local nhìn thấy.

Điều này thường khiến người học hiểu nhầm rằng MBean đăng ký ở JVM A “được chia sẻ” cho JVM B. Thực chất JVM B nhận quyền truy cập thông qua một đường kết nối quản trị có sẵn hoặc được kích hoạt.

### Điều kiện thường ảnh hưởng local attach

- JVM đích phải còn đang chạy, và runtime phải hỗ trợ attach/local monitoring tương ứng.
- Người dùng hệ điều hành và chính sách bảo mật phải cho phép thao tác trên tiến trình đích.
- Một số môi trường không hỗ trợ hoặc đã vô hiệu hóa attach, chẳng hạn qua cấu hình JVM hoặc chính sách container.
- Công cụ và JVM cần tương thích; thông tin quản trị có thể bị hạn chế do quyền hoặc mô hình đóng gói runtime.
- Docker/container, namespace tiến trình, quyền filesystem và user namespace có thể khiến JVM không xuất hiện trong danh sách local dù cùng một máy vật lý.

Do đó, **“cùng host” không đồng nghĩa chắc chắn truy cập được**. Cần phân biệt kết nối local thông qua attach với JMX remote qua connector.

## 6. Truy cập từ máy khác: cần connector JMX

Một tiến trình trên máy khác không thể chỉ biết ObjectName rồi truy cập MBeanServer. Ứng dụng phải có cơ chế cung cấp kết nối quản trị từ xa, thông thường thông qua **JMX Remote API** và JMX connector (thường dựa trên RMI trong các cấu hình JDK phổ biến).

Luồng khái niệm:

\`\`\`text
Remote JMX client
    │
    │ endpoint + transport + identity/quyền
    ▼
JMX Connector Server
    │
    ▼
MBeanServer ở JVM mục tiêu
    │
    ├── queryNames(...)
    ├── getAttribute(...)
    └── invoke(...)
\`\`\`

Một cách cấu hình JDK thường gặp cho môi trường kiểm soát là cung cấp các JVM system properties quản lý từ xa; ví dụ:

\`\`\`text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9010
-Djava.rmi.server.hostname=<địa-chỉ-mà-client-truy-cập-được>
\`\`\`

**Đây chỉ là khung tham khảo**, không phải cấu hình có thể sao chép nguyên xi vào production. Cần thiết lập authentication, TLS/SSL, quyền truy cập và giới hạn network phù hợp theo JDK/runtime đang dùng. Không vô hiệu hóa authentication hoặc TLS để tiện kết nối trong môi trường có người khác truy cập. Đừng để cổng JMX lộ công khai ra Internet.

Đặc biệt với RMI, client ban đầu có thể gọi một endpoint rồi nhận stub chứa hostname/port để kết nối tiếp. Vì thế một JMX port đã mở vẫn có thể không dùng được nếu hostname được công bố là \`localhost\`, IP nội bộ sai, hoặc port bổ sung bị chặn bởi firewall/NAT. Cấu hình cùng một port cho registry/RMI endpoint có thể làm đơn giản hóa vận hành trong các setup phù hợp, nhưng vẫn phải kiểm tra thực tế với runtime và hạ tầng.

### Ví dụ client JMX từ tiến trình khác

\`\`\`java
import java.util.Set;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class RemoteJmxClient {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi"
        );

        // Cung cấp môi trường kết nối và thông tin xác thực
        // tương ứng với server trong triển khai thực tế.
        try (JMXConnector connector =
                JMXConnectorFactory.connect(url)) {
            MBeanServerConnection connection =
                    connector.getMBeanServerConnection();

            Set<ObjectName> names =
                    connection.queryNames(
                        new ObjectName("learning.jmx:*"), null
                    );

            names.forEach(System.out::println);
        }
    }
}
\`\`\`

Để chạy client này, phải có **server JMX remote đã cấu hình và được phép truy cập**; giá trị hostname chỉ là ví dụ. \`JMXConnectorFactory.connect(url)\` không tự cấp quyền hay vượt qua authentication. Nếu server yêu cầu credentials, hãy cung cấp qua environment map và một cơ chế quản lý bí mật phù hợp.

## 7. Spring Framework đăng ký MBean vào server nào?

Trong Spring Framework, \`MBeanExporter\` có thể đăng ký các Spring-managed beans thành MBean. Nếu không cấu hình MBeanServer riêng, cách Spring tìm hoặc tạo MBeanServer chịu ảnh hưởng cơ chế lookup và cấu hình exporter; không nên đoán rằng mọi deployment đều dùng chính xác một server mà công cụ bên ngoài đang xem.

Ví dụ:

\`\`\`java
package example.management;

import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxExportConfiguration {

    @Bean
    public JobCounter jobCounter() {
        return new JobCounter();
    }

    @Bean
    public MBeanExporter mBeanExporter(JobCounter counter) {
        MBeanServer platformServer =
                ManagementFactory.getPlatformMBeanServer();

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformServer);
        exporter.setBeans(Map.of(
            "learning.jmx:type=JobCounter,name=Primary",
            counter
        ));

        return exporter;
    }
}
\`\`\`

Ở đây có chủ đích đặt \`setServer(platformServer)\` để MBean được đăng ký tại **platform MBeanServer của chính JVM đang chạy ứng dụng**. Khi Spring khởi tạo và quản lý vòng đời exporter, MBean được đăng ký/hủy đăng ký theo lifecycle tương ứng.

**Nếu dùng annotation-based MBean:** Spring còn hỗ trợ \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, kèm metadata assembler hoặc cơ chế exporter phù hợp. Annotation chỉ mô tả contract; cần có cấu hình xuất bản tương ứng để MBean thực sự xuất hiện.

**Spring Boot:** Spring Boot có cơ chế JMX liên quan Actuator và cấu hình bật/tắt JMX khác nhau theo phiên bản, dependencies và properties. Đừng nhầm MBean do Spring Framework exporter công bố với toàn bộ Actuator endpoints; cần kiểm tra MBeanServer và tên object thật trong ứng dụng.

## 8. Tình huống: đã register thành công nhưng JConsole không thấy

Giả sử log ứng dụng hiển thị:

\`\`\`text
Registered: true
\`\`\`

nhưng JConsole của kỹ sư không hiển thị \`learning.jmx:type=JobCounter,name=Primary\`.

Hãy điều tra theo chuỗi nguyên nhân gần nhất:

1. **Đúng JVM chưa?** Xác nhận PID, ứng dụng, container và môi trường chạy. Nhiều JVM có cùng ObjectName nhưng trạng thái hoàn toàn khác nhau.
2. **Ứng dụng còn chạy không?** Một chương trình demo thoát sau khi register hoặc unregister trước khi người vận hành kết nối sẽ không còn MBean để xem.
3. **Đúng MBeanServer chưa?** Nếu đăng ký vào một MBeanServer tùy biến nhưng công cụ kết nối platform server, danh sách có thể khác nhau.
4. **Đăng ký chưa?** Dùng \`isRegistered(ObjectName)\`, \`queryNames(...)\` và ghi nhận lỗi đăng ký. Lưu ý domain và key property viết đúng; ObjectName phân biệt tên.
5. **Client có quyền kết nối JVM đích không?** Kiểm tra quyền OS, phiên bản JDK, cơ chế attach, policy và process/container namespace.
6. **Đúng kiểu kết nối không?** Local process attach khác với remote JMX URL; remote cần connector server, hostname, port, network và authentication phù hợp.
7. **Có lỗi giao thức/bảo mật?** Kiểm tra lỗi kết nối, TLS, chứng thực, RMI stub hostname/firewall thay vì mặc định lỗi là do MBean chưa đăng ký.

Điểm kiểm chứng đáng tin cậy nhất ở phía server:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName target =
    new ObjectName("learning.jmx:type=JobCounter,name=Primary");

System.out.println(server.isRegistered(target));
System.out.println(server.queryNames(
    new ObjectName("learning.jmx:*"), null
));
\`\`\`

Đoạn trên trả lời câu hỏi: **MBean có được đăng ký tại platform MBeanServer trong JVM hiện tại không?** Nó không đủ chứng minh rằng một tiến trình bất kỳ từ ngoài đã có đường truy cập.

## 9. Bảo mật và quyền vận hành

JMX là một **bề mặt quản trị**, đôi khi cho phép sửa cấu hình, gọi thao tác có tác dụng phụ, xem dữ liệu nhạy cảm hoặc ảnh hưởng tình trạng dịch vụ.

### Khi chỉ cần quản trị trong một máy hoặc một container

Ưu tiên đường truy cập phù hợp với giới hạn quyền tiến trình. Không cấu hình remote connector nếu không có nhu cầu; giới hạn ai có thể attach vào process. Cần hiểu rằng quyền local OS rất mạnh: người có khả năng attach/debug JVM đôi khi đã có khả năng quan sát dữ liệu nhạy cảm.

### Khi cần remote JMX

- Giới hạn cổng trong mạng quản trị/VPN và firewall, không công khai Internet.
- Bật xác thực, bảo vệ credentials và dùng kênh truyền mã hóa khi môi trường yêu cầu.
- Phân quyền đọc/ghi/gọi operation phù hợp; thao tác restart/reset/clear có thể làm thay đổi hành vi ứng dụng.
- Giới hạn các MBean được công bố, tránh đưa password, token hoặc thông tin cá nhân vào attribute hay notification.
- Ghi audit cho operation gây thay đổi trạng thái, ghi rõ instance mục tiêu, identity, thời điểm và kết quả.
- Trong Kubernetes, ưu tiên cơ chế truy cập tạm thời và có kiểm soát (ví dụ kênh mạng quản trị hạn chế), tránh port forward chia sẻ thiếu kiểm soát.
- Không dựa vào ObjectName hoặc tên package như cơ chế bảo mật; ObjectName chỉ là định danh.

Cần nhớ: **đăng ký local không có nghĩa an toàn tuyệt đối**, và **có remote connector không có nghĩa ai cũng truy cập được**. Quyền thực tế phụ thuộc các lớp OS, mạng, JVM và cấu hình JMX.

## 10. So sánh bốn mô hình truy cập

| Mô hình | MBean sống ở đâu? | Điều kiện truy cập | Phù hợp |
|---|---|---|---|
| Code trong cùng JVM gọi MBeanServer | JVM ứng dụng | Có tham chiếu tới MBeanServer đúng | Kiểm tra nội bộ hoặc tích hợp quản trị trong process |
| JConsole/VisualVM local attach | JVM khác trên cùng host/namespace phù hợp | JVM hỗ trợ local attach; quyền OS và môi trường cho phép | Chẩn đoán thủ công trên máy phát triển/server được quản trị |
| JMX remote connector | JVM ứng dụng trên host khác hoặc cùng host | Connector server, endpoint, mạng, authentication/TLS | Công cụ quản trị tập trung trong mạng tin cậy |
| HTTP management endpoint | JVM ứng dụng, nhưng export qua web contract | HTTP server, route, mạng, quyền HTTP | Automation/công cụ đa nền tảng với API contract rõ |

Mô hình JMX local attach và JMX remote đều thao tác trên MBeanServer đích thông qua kết nối thích hợp; chúng không chuyển bản sao object Java giữa các JVM.

## 11. Vòng đời MBean và các lỗi thường gặp

MBean là tài nguyên quản trị gắn với vòng đời đối tượng/ứng dụng:

- **Đăng ký:** \`registerMBean\` hoặc Spring \`MBeanExporter\`.
- **Tồn tại:** có thể được tìm bằng \`queryNames\` và truy cập theo quyền.
- **Hủy đăng ký:** \`unregisterMBean\` hoặc lifecycle Spring exporter.
- **JVM kết thúc:** MBeanServer và các đăng ký của JVM đó biến mất.

Các lỗi đáng nhận diện:

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| \`InstanceAlreadyExistsException\` | ObjectName trùng trên cùng MBeanServer | Kiểm tra đăng ký kép và naming scheme |
| \`NotCompliantMBeanException\` | Class/interface không phù hợp Standard/Dynamic MBean | Kiểm tra \`*MBean\` interface, phương thức, visibility |
| \`InstanceNotFoundException\` | Sai ObjectName hoặc đã unregister | Dùng \`isRegistered\`, \`queryNames\` |
| JConsole không liệt kê JVM | Thiếu quyền attach, PID/namespace/JDK khác | Kiểm tra tiến trình, OS, container và attach |
| Kết nối remote timeout | Host/port, firewall, NAT hoặc RMI stub sai | Kiểm tra connector URL và mạng đầu cuối |
| Kết nối được nhưng operation bị từ chối | Quyền quản trị không phù hợp | Kiểm tra authentication/authorization |
| Nhìn thấy platform MBeans nhưng không thấy custom MBean | Đăng ký sai server, sai tên hoặc chưa tới lifecycle | Xác nhận MBeanServer và ObjectName |

## 12. Bài tập thực hành

Tạo một ứng dụng Java hoặc Spring Framework chạy liên tục, đăng ký \`JobCounter\` tại:

\`\`\`text
learning.jmx:type=JobCounter,name=Primary
\`\`\`

Thực hiện lần lượt:

1. Trong chính JVM ứng dụng, gọi \`isRegistered(...)\` và đọc \`CompletedJobs\`.
2. Mở công cụ JMX local trên cùng máy và thử tìm domain \`learning.jmx\`. Ghi lại PID và loại kết nối thực tế.
3. Chạy thêm một JVM khác có code truy vấn \`ManagementFactory.getPlatformMBeanServer()\`. Quan sát rằng MBean ở JVM thứ nhất **không xuất hiện** trong platform server của JVM thứ hai nếu không có connector.
4. Với môi trường thử nghiệm có kiểm soát và được cấp quyền, thử kết nối JMX connector cấu hình sẵn bằng JMX client; dùng \`queryNames\` và \`getAttribute\`.
5. Hủy đăng ký MBean trong JVM đích. Kiểm tra tên biến mất khỏi cùng MBeanServer; nếu công cụ cache dữ liệu, thực hiện refresh.

**Câu hỏi tự kiểm tra:**

- Vì sao hai JVM có thể cùng đăng ký một ObjectName mà không xung đột?
- Điều gì xảy ra nếu Spring exporter đăng ký MBean vào server khác với server mà JConsole kết nối?
- Nếu một ứng dụng trong Docker không hiện trong danh sách local process của JConsole, bạn cần kiểm tra lớp nào trước?
- Tại sao không nên bật cổng JMX remote không có authentication/TLS chỉ để quan sát một MBean?
- Một client biết ObjectName nhưng không biết endpoint JMX: đã đủ thông tin kết nối chưa?

**Đáp án gợi ý:** ObjectName chỉ duy nhất trong từng MBeanServer; công cụ phải kết nối đúng server; Docker làm thay đổi namespace/quyền attach; JMX mở quyền quản trị nhạy cảm; và ObjectName không thay thế JMX connector endpoint.

## 13. Ghi nhớ cốt lõi

- **Register MBean** nghĩa là đăng ký một đối tượng quản trị trong **MBeanServer của JVM**, không phải công bố nó cho mọi tiến trình.
- **Local JVM** có thể dùng MBeanServer trực tiếp; **JVM khác** cần đường kết nối quản trị thực tế.
- **JConsole local** đôi khi kết nối mà bạn không cấu hình remote port, nhờ cơ chế attach/local management, nhưng vẫn phụ thuộc quyền và môi trường.
- **Remote JMX** cần connector được cấu hình, mạng và bảo mật đúng; ObjectName không phải địa chỉ kết nối.
- Trong Spring Framework, dùng **MBeanExporter** và xác định rõ MBeanServer khi cần bảo đảm MBean xuất hiện tại platform server mong đợi.
- Để chẩn đoán lỗi, xác minh tuần tự: **đúng JVM → còn chạy → đúng server → có đăng ký → kết nối có quyền → mạng/giao thức**.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE — \`ManagementFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html
- Java SE — JMX Remote API: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/package-summary.html
- Oracle Java Management Extensions Technology: https://docs.oracle.com/javase/8/docs/technotes/guides/jmx/
