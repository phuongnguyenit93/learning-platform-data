# Phân biệt MBeanExporter với MBeanServerFactoryBean trong Spring Framework JMX

## 1. Mục tiêu bài học

Khi tích hợp Java Management Extensions (JMX) vào Spring Framework, hai lớp có tên gần nhau thường dễ gây nhầm lẫn:

- **\`MBeanExporter\`**: đưa các đối tượng ứng dụng (thường là Spring beans) ra giao diện quản trị JMX bằng cách đăng ký chúng dưới dạng MBean.
- **\`MBeanServerFactoryBean\`**: cung cấp một \`MBeanServer\` cho Spring container, bằng cách tìm một server có sẵn hoặc tạo server mới theo cấu hình.

Hai thành phần làm những công việc khác nhau nhưng có thể phối hợp: *factory cung cấp nơi đăng ký; exporter đưa đối tượng vào nơi đó*. Bài này tập trung vào mối quan hệ ấy, vòng đời, cách cấu hình, lựa chọn MBeanServer và cách chẩn đoán lỗi.

Sau bài này, bạn có thể:

1. Giải thích sự khác biệt giữa một **MBeanServer** và một **MBean được đăng ký**.
2. Xác định trách nhiệm của \`MBeanExporter\` so với \`MBeanServerFactoryBean\`.
3. Cấu hình exporter dùng một MBeanServer được chỉ định.
4. Phân biệt tìm server hiện có, tạo server mới và sử dụng platform MBeanServer.
5. Giải thích vì sao có MBeanServer không đồng nghĩa với việc MBean của ứng dụng đã xuất hiện.
6. Kiểm tra vòng đời đăng ký/hủy đăng ký khi Spring ApplicationContext khởi động và đóng.
7. Không nhầm hai thành phần trên với JMX connector server dùng cho kết nối từ xa.

## 2. Bức tranh tổng thể: ba tầng độc lập

Một ứng dụng Spring có thể chứa ba tầng liên quan đến JMX:

\`\`\`text
+------------------------------------------------------+
| Spring ApplicationContext                            |
|                                                      |
|  WorkerService, CacheMonitor, QueueMonitor           |
|             |                                        |
|             v                                        |
|      MBeanExporter                                   |
|             | registerMBean                          |
|             v                                        |
|      MBeanServer <----- MBeanServerFactoryBean       |
|             |                tạo/tìm/cung cấp         |
+-------------|----------------------------------------+
              |
      MBeanServerConnection
              |
   +----------+--------------+
   |                         |
Local JMX client       JMX ConnectorServer
   |                         |
JConsole                 Network / remote JMX
\`\`\`

**Điểm cần phân biệt:** \`MBeanServerFactoryBean\` không tự lựa chọn các business bean sẽ được export, còn \`MBeanExporter\` không phải là server chứa MBean. Một connector cho remote access lại thuộc trách nhiệm khác: truyền yêu cầu JMX đến một MBeanServer qua một kết nối được bảo vệ.

| Thành phần | Câu hỏi nó trả lời | Đầu vào quan trọng | Kết quả |
|---|---|---|---|
| \`MBeanServerFactoryBean\` | “MBeanServer nào sẽ được cung cấp?” | Agent ID, cấu hình locating/creating | Một đối tượng \`MBeanServer\` |
| \`MBeanExporter\` | “Những đối tượng nào được đăng ký dưới tên nào?” | Beans, ObjectNames, assembler, naming strategy, server | Các MBean được đăng ký trong server |
| \`MBeanServer\` | “Registry quản lý những MBean nào?” | \`ObjectName\`, MBean instance | Registry và API JMX management |
| JMX ConnectorServer | “Client ngoài JVM kết nối bằng cách nào?” | Server, protocol/URL, xác thực, mạng | Endpoint truy cập từ xa |

Đừng coi việc tạo ra một \`MBeanServer\` là “bật JMX remote”; thao tác đó không mở cổng mạng.

## 3. MBeanServerFactoryBean làm gì?

\`org.springframework.jmx.support.MBeanServerFactoryBean\` là một Spring \`FactoryBean\` dùng để cung cấp một instance \`javax.management.MBeanServer\`. Nó có thể tìm server hiện có hoặc tạo server theo cấu hình thích hợp.

Các cấu hình liên quan:

- \`locateExistingServerIfPossible\`: điều chỉnh việc ưu tiên/tìm MBeanServer đã tồn tại.
- \`agentId\`: phục vụ tìm kiếm MBeanServer đã đăng ký với \`MBeanServerFactory\` theo agent ID (tùy cơ chế locating).
- \`defaultDomain\`: domain mặc định khi tạo server mới, không đồng nghĩa với domain bắt buộc của mọi ObjectName.
- \`registerWithFactory\`: điều khiển việc đăng ký server được tạo với \`MBeanServerFactory\`, ảnh hưởng khả năng tìm qua factory API.
- Một cấu hình khác có thể cung cấp server hiện có trực tiếp, chẳng hạn \`ManagementFactory.getPlatformMBeanServer()\`.

Những lựa chọn này quan trọng khi cần dùng chung server với phần khác của JVM hoặc cần tách riêng MBean registry cho một môi trường kiểm thử.

### 3.1. Vì sao Spring cần FactoryBean?

Spring container quản lý các bean thường bằng cách gọi constructor hoặc factory method. \`FactoryBean<T>\` là cơ chế để một bean cung cấp một đối tượng khác kiểu \`T\`. Với \`MBeanServerFactoryBean\`, Spring bean được truy xuất thông thường có kiểu \`MBeanServer\` để exporter hoặc thành phần khác inject.

Có thể hình dung:

\`\`\`text
Spring bean definition: mbeanServerFactory
          |
          v
    MBeanServerFactoryBean
          |
          v
     getObject() = MBeanServer
\`\`\`

Đây là cơ chế tạo/chọn server, không phải cơ chế tự động scan và đăng ký tất cả Spring bean.

### 3.2. Platform MBeanServer và server khác

JDK cung cấp platform MBeanServer:

\`\`\`java
MBeanServer platformServer =
    java.lang.management.ManagementFactory.getPlatformMBeanServer();
\`\`\`

Các platform MXBeans của JVM (Memory, Threading, Runtime...) thường gắn với platform MBeanServer. Nếu exporter đăng ký ứng dụng vào platform server, một client local kết nối tới platform server có thể thấy cả JVM MBeans lẫn application MBeans.

Một server tạo riêng có thể là registry tách biệt:

\`\`\`java
MBeanServer privateServer =
    javax.management.MBeanServerFactory.newMBeanServer();
\`\`\`

Client nhìn vào platform MBeanServer **không mặc nhiên thấy** MBean đăng ký trên một server khác. Đây là nguyên nhân phổ biến của tình huống “MBeanExporter chạy, nhưng JConsole không thấy bean”.

## 4. MBeanExporter làm gì?

\`org.springframework.jmx.export.MBeanExporter\` là thành phần hỗ trợ export các Spring-managed objects hoặc các đối tượng do cấu hình chỉ định thành MBean trong một server.

Các nhiệm vụ thường gặp:

1. Nhận tập object cần export, ví dụ \`Map<String, Object>\`.
2. Tạo ObjectName thích hợp (hoặc dùng tên đã cung cấp).
3. Quyết định cách ánh xạ Java bean thành MBean, dùng các assembler/metadata thích hợp.
4. Đăng ký MBean qua \`MBeanServer.registerMBean\`.
5. Xử lý chính sách đăng ký trùng tên theo \`RegistrationPolicy\`.
6. Theo dõi và hủy đăng ký các MBean mà exporter quản lý khi lifecycle kết thúc.

Các thành phần liên quan:

| Thành phần | Vai trò |
|---|---|
| \`MBeanExporter\` | Orchestrate đăng ký và hủy đăng ký MBean |
| \`MBeanInfoAssembler\` | Xác định attributes, operations và metadata được expose |
| \`ObjectNamingStrategy\` | Xác định ObjectName |
| \`MBeanServer\` | Server nhận registration |
| \`RegistrationPolicy\` | Chiến lược khi ObjectName đã tồn tại |
| \`@ManagedResource\` | Metadata annotation của object quản trị |
| \`@ManagedAttribute\`, \`@ManagedOperation\` | Chỉ định members được công khai khi dùng annotation assembler |

**Lưu ý:** exporter có thể nhận một bean bình thường và biến nó thành MBean bằng cơ chế Spring, hoặc đăng ký một đối tượng đã tuân theo hợp đồng JMX. Hành vi cụ thể phụ thuộc cấu hình assembler, naming strategy, autodetection và loại object.

## 5. Ví dụ Spring: tạo MBeanServer và dùng MBeanExporter

Ví dụ Java configuration cho một ứng dụng Spring Framework không phụ thuộc Spring Boot.

### 5.1. Bean nghiệp vụ quản trị

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class TaskMonitor {
    private final AtomicInteger completed = new AtomicInteger();
    private volatile boolean enabled = true;

    public int getCompletedTasks() {
        return completed.get();
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public void reset() {
        completed.set(0);
    }

    public void taskCompleted() {
        if (enabled) {
            completed.incrementAndGet();
        }
    }
}
\`\`\`

Ở bước đầu, lớp này là Java object thông thường. Việc có getter, setter và method \`reset\` chưa đủ để một JMX client tìm thấy nó; cần export vào MBeanServer.

### 5.2. Cấu hình tường minh hai thành phần

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;
import org.springframework.jmx.support.MBeanServerFactoryBean;
import org.springframework.jmx.support.RegistrationPolicy;

import javax.management.MBeanServer;
import java.util.Map;

@Configuration
public class JmxConfig {

    @Bean
    public TaskMonitor taskMonitor() {
        return new TaskMonitor();
    }

    @Bean
    public MBeanServerFactoryBean mbeanServer() {
        MBeanServerFactoryBean factory =
            new MBeanServerFactoryBean();
        factory.setLocateExistingServerIfPossible(true);
        return factory;
    }

    @Bean
    public MethodNameBasedMBeanInfoAssembler jmxAssembler() {
        MethodNameBasedMBeanInfoAssembler assembler =
            new MethodNameBasedMBeanInfoAssembler();
        assembler.setManagedMethods(
            "getCompletedTasks", "isEnabled",
            "setEnabled", "reset");
        return assembler;
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer mbeanServer,
            TaskMonitor taskMonitor,
            MethodNameBasedMBeanInfoAssembler jmxAssembler) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setAssembler(jmxAssembler);
        exporter.setBeans(Map.of(
            "example.jmx:type=TaskMonitor,name=Primary",
            taskMonitor));
        exporter.setRegistrationPolicy(
            RegistrationPolicy.FAIL_ON_EXISTING);
        return exporter;
    }
}
\`\`\`

Ở đây:

1. \`mbeanServer()\` khai báo FactoryBean để tạo/tìm MBeanServer.
2. Spring inject sản phẩm \`MBeanServer\` của factory vào exporter.
3. \`jmxAssembler()\` chỉ định các method được expose qua JMX.
4. \`mbeanExporter()\` đăng ký \`TaskMonitor\` với tên cụ thể.
5. JMX client kết nối **đúng MBeanServer đó** mới nhìn thấy ObjectName.

Đây là ví dụ minh họa cơ chế tường minh. Trong dự án thực tế, cần chọn assembler và policy phù hợp với hợp đồng quản trị; đừng tự động export toàn bộ public methods của service nếu chúng không được thiết kế làm API quản trị.

### 5.3. Chạy một ApplicationContext nhỏ

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class Main {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(JmxConfig.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                "example.jmx:type=TaskMonitor,name=Primary");

            System.out.println("Registered: " +
                server.isRegistered(name));

            System.out.println("CompletedTasks: " +
                server.getAttribute(name, "CompletedTasks"));

            context.getBean(TaskMonitor.class).taskCompleted();

            System.out.println("CompletedTasks after event: " +
                server.getAttribute(name, "CompletedTasks"));

            Thread.sleep(60_000);
        }
    }
}
\`\`\`

Khi chạy với dependencies Spring Context phù hợp và classpath chứa các lớp ví dụ, kết quả mong đợi là:

\`\`\`text
Registered: true
CompletedTasks: 0
CompletedTasks after event: 1
\`\`\`

Điểm kiểm chứng: dùng \`context.getBean(MBeanServer.class)\` đọc trực tiếp server do factory cung cấp. Nếu dùng \`ManagementFactory.getPlatformMBeanServer()\` mà exporter đã đăng ký vào một server khác, kết quả \`isRegistered\` có thể khác.

## 6. Phân biệt “tìm server” và “tạo server”

### 6.1. Tìm server hiện có

Một ứng dụng JVM có thể có sẵn platform MBeanServer hoặc server đã được tạo từ một thành phần khác. Khi muốn JMX của ứng dụng xuất hiện trên server được các công cụ quản trị dùng chung, cần cấu hình cho exporter dùng đúng server.

Có thể chọn platform MBeanServer tường minh bằng Java configuration:

\`\`\`java
@Bean
public MBeanServer mbeanServer() {
    return java.lang.management.ManagementFactory
        .getPlatformMBeanServer();
}
\`\`\`

Đây là một lựa chọn thay cho FactoryBean trong trường hợp ta chỉ cần platform server; không cần tạo MBeanServer mới. Nếu đồng thời có một FactoryBean khác cùng cung cấp \`MBeanServer\`, phải dùng qualifier hoặc wiring rõ ràng để tránh ambiguity.

### 6.2. Tạo server mới

Một ứng dụng có lý do tách riêng server, chẳng hạn kiểm thử, cô lập namespace hoặc xây dựng connector chuyên dụng:

\`\`\`java
@Bean
public MBeanServer isolatedMBeanServer() {
    return javax.management.MBeanServerFactory.newMBeanServer(
        "isolated.training");
}
\`\`\`

Khi đó exporter phải dùng \`isolatedMBeanServer\`. Một local JConsole gắn với platform server không nhất thiết thấy server riêng đó. Nếu cần remote access tới server riêng, phải tạo và cấu hình JMXConnectorServer gắn chính server ấy.

### 6.3. FactoryBean và server lifecycle

\`MBeanServerFactoryBean\` có thể tạo server và quản lý vòng đời server do nó tạo. Khi context đóng, cần hiểu server được release như thế nào và những MBean nào còn tồn tại. Trong môi trường dùng chung platform server, không nên tự ý release một server mà các thành phần khác đang sử dụng.

Định hướng vận hành:

- Server được tạo riêng cho test: kết thúc test thì cleanup resources của test.
- Platform server dùng chung: exporter chỉ quản lý các MBean nó đăng ký.
- Nhiều ApplicationContext trong một JVM: có chiến lược naming và ownership rõ ràng.
- Context restart: đảm bảo unregister trước khi register lại nếu cùng ObjectName.

## 7. Autodetection, annotation và exporter

Không phải lúc nào cũng khai báo \`setBeans\` cho từng đối tượng. Spring có khả năng phát hiện MBean đủ điều kiện và hỗ trợ annotations, tùy cấu hình. Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "example.jmx:type=Worker,name=Primary")
public class WorkerManagement {
    private volatile boolean enabled = true;

    @ManagedAttribute
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation
    public void disable() {
        enabled = false;
    }
}
\`\`\`

Có thể dùng \`@EnableMBeanExport\` hoặc một cấu hình \`MBeanExporter\` với \`AnnotationJmxAttributeSource\` và metadata assembler để export loại bean này. Nhưng:

- Annotation trên class không phải là một MBeanServer.
- FactoryBean không tự scan annotation rồi đăng ký bean.
- Exporter cần được cấu hình, được Spring khởi tạo và dùng server thích hợp.
- Nếu ứng dụng đã có exporter tự động, không nên thêm exporter thứ hai đăng ký cùng ObjectName.

## 8. RegistrationPolicy: hành vi khi tên đã tồn tại

Một \`ObjectName\` chỉ có thể đại diện cho một MBean tại một thời điểm trong cùng MBeanServer. Khi exporter gặp tên trùng, chính sách đăng ký quyết định hành vi.

Các policy thường gặp:

| Policy | Ý nghĩa | Rủi ro/ứng dụng |
|---|---|---|
| \`FAIL_ON_EXISTING\` | Báo lỗi khi tên đã đăng ký | Hữu ích để phát hiện cấu hình trùng |
| \`IGNORE_EXISTING\` | Giữ đăng ký có sẵn và bỏ qua registration mới | Có thể khiến client thấy bean cũ ngoài dự kiến |
| \`REPLACE_EXISTING\` | Thay registration hiện có | Phải hiểu ownership và tác động tới client khác |

Trong ví dụ đào tạo, \`FAIL_ON_EXISTING\` giúp lỗi dễ được phát hiện. Trong production, chọn policy theo hợp đồng vòng đời và quyền quản trị. Không dùng \`REPLACE_EXISTING\` như cách mặc định che lỗi đặt tên trùng.

**Quan trọng:** policy là trách nhiệm của exporter khi đăng ký, không thuộc chức năng cốt lõi của \`MBeanServerFactoryBean\`.

## 9. MBeanServerFactoryBean không phải ConnectorServerFactoryBean

Một sự nhầm lẫn khác đến từ các tên lớp Spring JMX:

- \`MBeanServerFactoryBean\`: cung cấp MBeanServer.
- \`MBeanExporter\`: đăng ký MBean.
- \`ConnectorServerFactoryBean\`: hỗ trợ tạo JMX connector server để client có thể kết nối theo cấu hình URL/protocol.

Ví dụ sơ đồ:

\`\`\`text
MBeanServerFactoryBean
         |
         v
    MBeanServer
      ^      ^
      |      |
MBeanExporter ConnectorServerFactoryBean
(register)       (remote access)
\`\`\`

Có một MBeanServer và exporter hoạt động không có nghĩa remote JMX đã được mở. Bật connector remote phải được xem là thao tác quản trị bảo mật cao: cần mạng riêng, kiểm soát truy cập và mã hóa phù hợp. Không mở cổng JMX công cộng chỉ để nhìn MBean trong JConsole.

### 9.1. RMI, firewall và credentials

Remote JMX/RMI có thể dùng registry port và cổng connector server riêng. Địa chỉ được công bố trong RMI stub cần reachable từ client; nếu hostname/port sai, client có thể kết nối tới registry nhưng thất bại ở bước tiếp theo. Dùng cấu hình bảo mật phù hợp với JDK và hạ tầng; xác thực và TLS không được bỏ qua khi triển khai thực.

Để học \`MBeanExporter\` và \`MBeanServerFactoryBean\`, ưu tiên gọi API trên local MBeanServer hoặc kiểm tra qua JConsole local, chưa cần cấu hình remote connector.

## 10. Kiểm thử: exporter và factory hoạt động đúng chưa?

Có thể dùng các kiểm tra sau trong một Spring integration test:

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import static org.junit.jupiter.api.Assertions.*;

class SpringJmxWiringTest {

    @Test
    void exporterRegistersOnConfiguredServer() throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    JmxConfig.class)) {

            MBeanServer server =
                context.getBean(MBeanServer.class);

            ObjectName name = new ObjectName(
                "example.jmx:type=TaskMonitor,name=Primary");

            assertTrue(server.isRegistered(name));
            assertEquals(
                0,
                server.getAttribute(name, "CompletedTasks"));

            server.setAttribute(name,
                new javax.management.Attribute("Enabled", false));
            assertEquals(
                false,
                server.getAttribute(name, "Enabled"));
        }
    }
}
\`\`\`

Giá trị của test này là kiểm tra đúng **server được inject vào exporter**, không chỉ xem ApplicationContext đã có bean \`TaskMonitor\` hay chưa.

Các kiểm tra nên thực hiện tùy bài toán:

1. ObjectName được đăng ký chính xác.
2. Metadata và operations đúng hợp đồng quản trị.
3. Attribute được đọc/ghi theo khai báo.
4. Khi context đóng, exporter unregister các MBean thuộc quyền quản lý của nó.
5. Không có duplicate ObjectName khi khởi tạo context lặp lại.
6. Nếu dùng server riêng, các client truy vấn đúng server đó.
7. Remote connection (nếu có) được kiểm thử riêng, có bảo mật.

## 11. Tình huống lựa chọn cấu hình

### Tình huống A: Ứng dụng Spring đơn giản chỉ cần JMX local

Mục tiêu: JConsole local xem application MBean cùng JVM MBeans.

Giải pháp: export ứng dụng vào platform MBeanServer hoặc để cấu hình Spring xác định server phù hợp; không nhất thiết cần \`MBeanServerFactoryBean\` riêng.

### Tình huống B: Nhiều module cùng JVM, cần một registry JMX thống nhất

Mục tiêu: các MBean cùng xuất hiện trong một MBeanServer.

Giải pháp: cấu hình inject cùng \`MBeanServer\` cho các exporter, định danh ObjectName tránh trùng giữa modules; tránh mỗi module tạo một registry ngầm.

### Tình huống C: Kiểm thử integration độc lập

Mục tiêu: chạy test song song và không làm bẩn platform server.

Giải pháp: dùng MBeanServer riêng cho từng test hoặc fixture, inject tường minh vào exporter, cleanup khi đóng context.

### Tình huống D: Có yêu cầu remote JMX

Mục tiêu: client quản trị từ một máy khác truy cập các MBean được phép.

Giải pháp: trước hết xác định MBeanServer đích và exporter, sau đó cấu hình connector/agent remote an toàn; xác minh từng tầng (registration, connector, mạng, TLS, credentials) thay vì chỉ thêm một FactoryBean.

### Tình huống E: Spring bean xuất hiện trong context nhưng JConsole không thấy

Nguyên nhân có thể là: không có exporter, exporter chưa scan/đăng ký bean, ObjectName khác dự kiến, hoặc exporter dùng server khác platform server mà JConsole đang kết nối.

## 12. Những lỗi thường gặp và cách xác định nguyên nhân

| Triệu chứng | Nguyên nhân khả dĩ | Cách xác minh |
|---|---|---|
| \`getBean(MBeanServer.class)\` thất bại | Chưa có bean server hoặc có nhiều candidate | Kiểm tra bean definitions và wiring |
| Có \`MBeanServer\` nhưng \`isRegistered(name)=false\` | Chưa export hoặc đăng ký sai server/tên | Kiểm tra MBeanExporter và ObjectName |
| \`InstanceAlreadyExistsException\` | Hai exporter hoặc context cùng đăng ký một tên | Kiểm tra lifecycle, registration policy |
| JConsole local thấy JVM MBeans nhưng thiếu Spring MBeans | Exporter sử dụng server khác hoặc export không thành công | So server identity và danh sách ObjectName |
| Remote JMX timeout | Connector/RMI hoặc mạng sai | Kiểm tra endpoint, hostname, firewall |
| Bean có annotation nhưng không export | Thiếu exporter/annotation assembler hoặc scan | Kiểm tra @EnableMBeanExport, metadata |
| Sau restart xuất hiện MBean cũ | Cleanup/unregistration không đúng | Kiểm tra ownership và việc đóng context |
| Operation không xuất hiện | Assembler chỉ expose một số method | Đọc MBeanInfo của MBean thực tế |

Khi debug, hãy lấy bằng chứng theo thứ tự:

\`\`\`text
1. ApplicationContext có TaskMonitor?
2. ApplicationContext có MBeanServer?
3. MBeanExporter có sử dụng server đó?
4. MBeanServer.isRegistered(ObjectName) == true?
5. MBeanServer.getMBeanInfo(name) có metadata đúng?
6. Client JMX có đang kết nối tới đúng server?
7. Nếu remote: connector, hostname, TLS, network, auth đã đúng?
\`\`\`

Chuỗi này giúp phân biệt lỗi export, lỗi registry và lỗi remote connector mà không phải thay đổi bừa cấu hình.

## 13. Câu hỏi tự kiểm tra

1. \`MBeanExporter\` có tự tạo một MBeanServer khác cho mỗi bean không?
2. \`MBeanServerFactoryBean\` có tự export tất cả các Spring bean không?
3. Nếu có MBeanServer nhưng chưa đăng ký application MBean, JConsole sẽ thấy gì?
4. Lý do nào khiến exporter dùng server riêng nhưng JConsole local không thấy MBean?
5. \`RegistrationPolicy\` được cấu hình ở thành phần nào?
6. Vai trò của \`MBeanInfoAssembler\` và \`ObjectNamingStrategy\` là gì?
7. Nếu Spring bean có \`@ManagedResource\`, thành phần nào chịu trách nhiệm đưa nó vào server?
8. Khác biệt giữa \`MBeanServerFactoryBean\` và \`ConnectorServerFactoryBean\` là gì?
9. Khi nào cần dùng chung platform MBeanServer thay vì tạo server riêng?
10. Làm sao kiểm tra chính xác exporter đăng ký MBean vào server nào?

## 14. Bài tập

### Bài tập 1 — Thay đổi MBeanServer

Dùng ví dụ \`JmxConfig\` và thử:

- Cấu hình exporter inject platform MBeanServer.
- Cấu hình exporter inject một server mới tạo qua \`MBeanServerFactory.newMBeanServer()\`.
- So sánh kết quả \`isRegistered(name)\` trên platform server và server riêng.
- Giải thích vì sao client chỉ thấy MBean của server nó đang kết nối.

### Bài tập 2 — Thử duplicate ObjectName

Tạo hai bean cùng được export với \`example.jmx:type=TaskMonitor,name=Primary\`. Quan sát \`FAIL_ON_EXISTING\`; sau đó tìm hiểu \`IGNORE_EXISTING\` và \`REPLACE_EXISTING\` trong môi trường lab để nêu hậu quả từng chính sách.

### Bài tập 3 — Kiểm tra lifecycle

Khởi động context, xác nhận \`isRegistered=true\`. Đóng context, kiểm tra MBean không còn tồn tại theo contract unregistration của exporter. Khởi động lại context với cùng ObjectName và xác nhận không còn conflict.

### Bài tập 4 — Annotation metadata

Thay \`MethodNameBasedMBeanInfoAssembler\` bằng một cấu hình annotation assembler phù hợp, thêm \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` vào bean. Quan sát metadata trước/sau và rút ra kết luận về việc assembler quyết định những member nào được expose.

## 15. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — \`MBeanServerFactoryBean\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/MBeanServerFactoryBean.html
- Spring Framework API — \`ConnectorServerFactoryBean\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/ConnectorServerFactoryBean.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 API — \`ManagementFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html

**Ghi nhớ:** \`MBeanServerFactoryBean\` chọn hoặc tạo nơi lưu trữ MBean; \`MBeanExporter\` quyết định object nào và ObjectName nào được đăng ký vào nơi đó. Một JMX connector server lại giải quyết truy cập từ xa. Phân biệt ba trách nhiệm này là chìa khóa để cấu hình Spring JMX chính xác và chẩn đoán sự cố hiệu quả.
