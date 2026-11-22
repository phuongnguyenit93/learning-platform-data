# MBeanServerFactoryBean và exposePlatformMBeanServer trong Spring Framework JMX

## 1. Mục tiêu bài học

Trong Spring Framework, một \`MBeanServer\` là nơi các MBean được đăng ký để JMX clients đọc trạng thái hoặc gọi operations. Khi cấu hình ứng dụng, ta thường muốn **dùng lại platform MBeanServer của JVM** thay vì tạo một registry mới, bởi platform server đã chứa nhiều JVM MXBeans và thường là server được công cụ quản trị cục bộ tìm thấy.

\`MBeanServerFactoryBean\` của Spring giúp chọn hoặc tạo một \`MBeanServer\`. Một lựa chọn quan trọng là **\`exposePlatformMBeanServer\`**: cơ chế cấu hình liên quan tới việc ưu tiên phơi bày platform MBeanServer có sẵn cho Spring-managed components khi không tìm thấy server theo cách khác.

Cần hiểu rõ sự khác nhau giữa:

- **Tìm một MBeanServer hiện hữu:** sử dụng server đã có.
- **Sử dụng platform MBeanServer:** chọn server do JVM cung cấp qua \`ManagementFactory.getPlatformMBeanServer()\`.
- **Tạo MBeanServer mới:** tạo registry khác, có lifecycle và tập MBean riêng.
- **Export bean:** đăng ký object thành MBean vào server đã chọn; việc này do \`MBeanExporter\` thực hiện, không phải do \`MBeanServerFactoryBean\`.

Sau bài học, bạn có thể lựa chọn cấu hình server phù hợp, tránh MBean biến mất khỏi JConsole do đăng ký nhầm server và kiểm thử tính nhất quán giữa Spring JMX exporter với platform JMX.

## 2. MBeanServer đóng vai trò gì?

Một MBeanServer là registry và API điều phối MBean:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.lang.management.ManagementFactory;

MBeanServer platform =
    ManagementFactory.getPlatformMBeanServer();

ObjectName memory = new ObjectName("java.lang:type=Memory");
System.out.println(platform.isRegistered(memory));
\`\`\`

JVM platform MBeanServer thường chứa các platform MXBeans, ví dụ \`java.lang:type=Memory\`, \`java.lang:type=Threading\` và \`java.lang:type=Runtime\`.

MBeanServer không phải là một cổng mạng. Tạo server không tự mở JMX/RMI connector; ngược lại, một remote connector phải được liên kết với server cụ thể và có cấu hình bảo mật riêng.

\`\`\`text
Application bean
      |
      v
 MBeanExporter
      |
      | register MBean
      v
  MBeanServer
      |
      +--> Java platform MXBeans
      +--> Application MBeans
      |
      v
JMX client via MBeanServerConnection
      |
      +--> Local tooling
      +--> Connector (nếu có)
\`\`\`

**Điểm cần nhớ:** một JVM có thể có **nhiều MBeanServer**, nhưng một client JMX chỉ nhìn thấy các MBean nằm trên server mà client thực sự kết nối tới.

## 3. MBeanServerFactoryBean là gì?

\`org.springframework.jmx.support.MBeanServerFactoryBean\` là một Spring \`FactoryBean<MBeanServer>\` dùng để cung cấp một \`MBeanServer\` cho container. Nó có thể tìm server hiện hữu hoặc tạo server theo các tùy chọn đã cấu hình.

Những tùy chọn cần nhận biết:

| Tùy chọn | Ý nghĩa chính |
|---|---|
| \`locateExistingServerIfPossible\` | Cố tìm MBeanServer đã tồn tại trước khi tạo mới |
| \`agentId\` | Dùng agent ID để định vị server đã được đăng ký phù hợp |
| \`defaultDomain\` | Đặt default domain khi tạo MBeanServer mới |
| \`registerWithFactory\` | Chỉ định server mới được tạo có đăng ký với \`MBeanServerFactory\` để có thể được định vị sau này không |
| \`exposePlatformMBeanServer\` | Điều chỉnh lựa chọn/exposure của platform MBeanServer trong quá trình xác định server |
| \`MBeanServer\` được inject vào exporter | Xác định chính xác registry chứa MBean ứng dụng |

**Không nhầm:** tùy chọn của FactoryBean liên quan đến việc **tạo hoặc tìm server**. Nó không quyết định Spring bean nào sẽ trở thành MBean và không tự expose tất cả bean trong ApplicationContext.

## 4. exposePlatformMBeanServer có tác dụng gì?

Tên \`exposePlatformMBeanServer\` dễ khiến người học nghĩ rằng cấu hình này mở platform JMX ra bên ngoài JVM. Đây là cách hiểu sai.

Về bản chất, lựa chọn liên quan platform MBeanServer là vấn đề **server nào được cung cấp/sử dụng trong container Spring**. Khi một platform MBeanServer được cung cấp, exporter có thể đăng ký application MBeans cùng nơi với các JVM platform MXBeans.

\`\`\`text
JVM
 |
 +-- Platform MBeanServer
 |       |
 |       +-- java.lang:type=Memory
 |       +-- java.lang:type=Threading
 |       +-- com.example:type=Worker,name=Primary
 |
 +-- Custom MBeanServer (nếu tạo riêng)
         |
         +-- custom.domain:type=Plugin,name=A
\`\`\`

Nếu exporter dùng custom server, một JConsole local thông thường vốn quan sát platform server không mặc nhiên nhìn thấy \`custom.domain:type=Plugin,name=A\`.

### 4.1. “Expose” khác “Remote access”

Cần phân biệt rõ:

\`\`\`text
Expose platform server to Spring components:
  cho bean/exporter trong JVM nhận một MBeanServer reference

Expose JMX remotely:
  khởi tạo connector/management agent và thiết lập
  network, RMI/transport, authentication, encryption
\`\`\`

\`exposePlatformMBeanServer\` **không** có nghĩa JVM mở cổng TCP JMX. Cấu hình remote JMX là trách nhiệm khác và cần kiểm soát quyền, TLS, mạng quản trị phù hợp.

### 4.2. Không tự suy ra lựa chọn mặc định

Các phiên bản Spring Framework và cách khởi tạo \`MBeanServerFactoryBean\` có thể có mặc định khác nhau hoặc thêm ràng buộc. Khi dự án yêu cầu bảo đảm dùng đúng platform MBeanServer, cách ít mơ hồ nhất là cấu hình tường minh:

\`\`\`java
@Bean
public MBeanServer mbeanServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
\`\`\`

Đây là một cách thay thế việc phụ thuộc gián tiếp vào FactoryBean. Trong dự án sử dụng FactoryBean, hãy cấu hình các setter được hỗ trợ bởi phiên bản Spring cụ thể và kiểm tra output server thực tế.

## 5. Sự khác biệt giữa \`locateExistingServerIfPossible\` và \`exposePlatformMBeanServer\`

Hai lựa chọn có mục tiêu liên quan nhưng không nên coi là đồng nghĩa.

- \`locateExistingServerIfPossible\` thể hiện ý định ưu tiên sử dụng MBeanServer hiện hữu thay vì tạo mới.
- \`exposePlatformMBeanServer\` thể hiện chính sách liên quan đến platform MBeanServer mà Spring có thể sử dụng hoặc cung cấp trong quá trình tìm server.
- \`agentId\` giúp chọn server phù hợp khi nhiều server đã được đăng ký với MBeanServerFactory.
- \`defaultDomain\` có ý nghĩa khi server được **tạo mới**, không biến tất cả ObjectName của MBean thành một domain cố định.

Một câu hỏi vận hành cần đặt ra: **MBeanServer cuối cùng có phải chính object trả bởi \`ManagementFactory.getPlatformMBeanServer()\` không?**

\`\`\`java
boolean sameInstance =
    configuredServer ==
    ManagementFactory.getPlatformMBeanServer();
\`\`\`

Nếu \`sameInstance\` là \`true\`, exporter đăng ký vào \`configuredServer\` sẽ đăng ký trên platform server. Nếu là \`false\`, cần xác định bạn có đang sử dụng server riêng hoặc server khác đã tồn tại hay không.

### 5.1. Khi có nhiều MBeanServer

Một JVM có thể lưu nhiều server trong danh sách quản lý của JMX factory. Việc “tìm server đã có” không đủ để bảo đảm server được chọn là platform server nếu có nhiều candidates và không chỉ định rõ điều kiện.

Trong môi trường cần tính quyết định cao, nên inject tường minh platform server hoặc dùng server có tên/qualifier rõ ràng để tránh chọn nhầm.

## 6. Cấu hình Spring bằng MBeanServerFactoryBean

Một ví dụ cấu hình Spring Framework:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class ServerConfig {

    @Bean
    public MBeanServerFactoryBean mbeanServer() {
        MBeanServerFactoryBean factory =
            new MBeanServerFactoryBean();

        factory.setLocateExistingServerIfPossible(true);
        return factory;
    }
}
\`\`\`

Khi Spring khởi tạo bean, \`FactoryBean\` sẽ cung cấp một \`MBeanServer\` cho các bean khác. Trong ví dụ này, cấu hình yêu cầu tìm server hiện có nếu có thể, nhưng bạn vẫn cần kiểm tra server được trả về trong môi trường thực tế.

Nếu phiên bản Spring đang dùng cung cấp setter cho \`exposePlatformMBeanServer\`, hãy tham chiếu Javadoc tương ứng trước khi dùng. Không giả định rằng mọi phiên bản đều đặt option tại cùng class hoặc giữ cùng signature.

**Phương án rõ ràng hơn khi yêu cầu tuyệt đối là platform server:**

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ExplicitPlatformServerConfig {
    @Bean
    public MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

Ưu điểm: lựa chọn server minh bạch, ít phụ thuộc vào trạng thái các MBeanServer khác. Không khai báo đồng thời hai bean \`MBeanServer\` giống nhau nếu exporter inject theo type mà không có qualifier, vì có thể tạo ambiguity.

## 7. Kết hợp MBeanServerFactoryBean với MBeanExporter

Để export một object Spring, cần cấu hình \`MBeanExporter\`:

\`\`\`java
package example.jmx;

import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class ExporterConfig {

    @Bean
    public WorkerMonitor workerMonitor() {
        return new WorkerMonitor();
    }

    @Bean
    public MethodNameBasedMBeanInfoAssembler assembler() {
        MethodNameBasedMBeanInfoAssembler assembler =
            new MethodNameBasedMBeanInfoAssembler();
        assembler.setManagedMethods(
            "getCompletedJobs", "isEnabled", "setEnabled");
        return assembler;
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer mbeanServer,
            WorkerMonitor workerMonitor,
            MethodNameBasedMBeanInfoAssembler assembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setAssembler(assembler);
        exporter.setBeans(Map.of(
            "com.example:type=WorkerMonitor,name=Primary",
            workerMonitor));
        exporter.setRegistrationPolicy(
            RegistrationPolicy.FAIL_ON_EXISTING);
        return exporter;
    }
}
\`\`\`

Bean nghiệp vụ:

\`\`\`java
package example.jmx;

public class WorkerMonitor {
    private volatile boolean enabled = true;
    private int completedJobs;

    public int getCompletedJobs() {
        return completedJobs;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public void jobCompleted() {
        if (enabled) {
            completedJobs++;
        }
    }
}
\`\`\`

Ví dụ hướng đến minh họa **wiring** và quản trị, không phải mô hình concurrency production. Nếu counter được cập nhật đa luồng, dùng primitive đồng bộ/atomic và định nghĩa semantics thích hợp.

### 7.1. Flow khởi tạo

\`\`\`text
Spring context refresh
     |
     +--> Tạo/tìm MBeanServer
     |
     +--> Khởi tạo WorkerMonitor
     |
     +--> Tạo MBeanExporter, inject đúng MBeanServer
     |
     +--> Exporter đăng ký WorkerMonitor dưới ObjectName
     |
     v
MBeanServer có application MBean
\`\`\`

Sau đó client có thể đọc \`CompletedJobs\` hoặc \`Enabled\` từ ObjectName đã đăng ký.

## 8. Kiểm chứng MBeanServer thực tế mà exporter sử dụng

Một chương trình Spring nhỏ:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

public final class Main {
    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    ServerConfig.class,
                    ExporterConfig.class)) {

            MBeanServer configured =
                context.getBean(MBeanServer.class);

            MBeanServer platform =
                ManagementFactory.getPlatformMBeanServer();

            System.out.println(
                "Same as platform: " + (configured == platform));

            ObjectName name = new ObjectName(
                "com.example:type=WorkerMonitor,name=Primary");

            System.out.println(
                "Registered in configured server: " +
                configured.isRegistered(name));

            System.out.println(
                "Registered in platform server: " +
                platform.isRegistered(name));

            System.out.println(
                "CompletedJobs = " +
                configured.getAttribute(name, "CompletedJobs"));

            Thread.sleep(60_000);
        }
    }
}
\`\`\`

Kết quả dự kiến:

- \`configured.isRegistered(name)\` là \`true\` nếu exporter đăng ký thành công.
- \`platform.isRegistered(name)\` chỉ là \`true\` khi export đi vào platform server, hoặc khi tên ấy được đăng ký ở đó theo đường khác.
- \`configured == platform\` là bằng chứng trực tiếp về identity server.

Nếu \`configured == platform\` là \`false\` và JConsole chỉ nhìn platform server, việc không thấy MBean ứng dụng không phải bằng chứng exporter thất bại.

## 9. Tạo MBeanServer mới có những hệ quả gì?

Một MBeanServer được tạo mới là một JMX registry độc lập. Ví dụ:

\`\`\`java
MBeanServer isolated =
    javax.management.MBeanServerFactory.newMBeanServer(
        "isolated.example");
\`\`\`

Nó không tự chứa toàn bộ platform MXBeans giống server của \`ManagementFactory\`, trừ khi chúng được đăng ký theo cơ chế thích hợp. Trong nhiều tình huống, chỉ cần platform server để quản trị ứng dụng đơn giản.

### 9.1. Lợi ích của server riêng

- Cô lập integration tests, tránh collision với MBean của JVM và ứng dụng khác.
- Cung cấp registry riêng cho một module hoặc plugin.
- Chủ động quản lý vòng đời và tập ObjectName theo yêu cầu.

### 9.2. Chi phí của server riêng

- Client phải biết đang kết nối tới server nào.
- JConsole local có thể không thấy registry đó.
- Muốn remote access cần connector được liên kết đến server riêng.
- Dễ cấu hình exporter A trên platform, exporter B trên custom server mà không chủ đích.
- Cleanup server và registrations phải rõ ràng.

Nếu mục tiêu là một dashboard thống nhất cho JVM, tạo nhiều server riêng có thể gây khó khăn không cần thiết.

## 10. Lifecycle và ownership của server

Cần tách hai loại vòng đời:

**Vòng đời MBeanServer**: ai tạo, ai quản lý và có cần release server?

**Vòng đời MBean registration**: exporter nào đăng ký và unregister ObjectName khi context đóng?

\`\`\`text
MBeanServerFactoryBean (nếu tạo server)
        |
        v
     MBeanServer
        ^
        |
   MBeanExporter --> register
   MBeanExporter --> unregister on context shutdown
\`\`\`

Nếu dùng platform MBeanServer, nó thuộc JVM và nhiều thành phần khác dùng chung; không nên release toàn bộ server khi một context đóng. Exporter chỉ nên hủy đăng ký những MBean thuộc quyền quản lý của mình.

Nếu dùng server do FactoryBean tạo riêng, cần xác định chính sách release theo lifecycle của FactoryBean. Tránh giữ một connector remote hoạt động sau khi server/module tương ứng đã dừng.

## 11. Quan hệ với Spring Boot và auto-configuration

Spring Framework và Spring Boot không có mặc định giống nhau ở mọi phiên bản. Spring Boot có cơ chế auto-configuration JMX và thiết lập như \`spring.jmx.enabled\` ở một số phiên bản.

Khi dùng Boot, cần xác minh:

1. Auto-configuration JMX có đang bật không?
2. Boot đang dùng \`MBeanServer\` nào?
3. Có custom \`MBeanServerFactoryBean\` hoặc \`MBeanServer\` bean override không?
4. Có \`MBeanExporter\` được tạo tự động và một exporter custom trùng nhau không?
5. Các Actuator endpoints JMX (nếu bật) có trùng ObjectName hoặc khác domain không?

Không thêm một FactoryBean chỉ vì “cần JMX” mà chưa xem Boot đã cung cấp MBeanServer/exporter hay chưa. Tránh cấu hình trùng exporter dẫn đến \`InstanceAlreadyExistsException\`.

## 12. Chẩn đoán lỗi liên quan exposePlatformMBeanServer

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Spring exporter báo đăng ký thành công, JConsole không thấy MBean | Exporter dùng custom server | So \`configured == platform\` |
| Chỉ thấy JVM MXBeans, không thấy app MBean | Exporter chưa export hoặc sai server/tên | Kiểm tra \`isRegistered\`, ObjectName, logs |
| Không tìm thấy \`MBeanServer\` trong context | FactoryBean chưa khai báo hoặc không được scan | Kiểm tra bean definitions |
| Có nhiều bean MBeanServer nên inject lỗi | Nhiều cấu hình cùng tạo server | Dùng qualifier hoặc một bean chính rõ ràng |
| \`InstanceAlreadyExistsException\` | Hai exporter đăng ký cùng tên trên một server | Kiểm tra policy và ownership |
| JMX remote không thấy MBean | Connector gắn server khác | So server reference và endpoint |
| Platform server có MBean nhưng app vẫn không nhận | Annotation/assembler/exporter chưa hoạt động | Đọc MBeanInfo và config |
| Khi restart context xuất hiện MBean cũ | Exporter không unregister hoặc ownership sai | Kiểm tra lifecycle |
| Tùy chọn \`exposePlatformMBeanServer\` không thấy trong IDE | API/phiên bản hoặc thành phần không khớp | Đối chiếu Javadoc phiên bản dự án |

Nếu test cần phân biệt các server, so **object identity** của \`MBeanServer\` bằng \`==\`, không chỉ so default domain hay chuỗi class name.

## 13. Khi nào nên chọn phương án nào?

| Nhu cầu | Hướng cấu hình |
|---|---|
| Ứng dụng đơn, muốn JConsole thấy app MBean cùng JVM MBeans | Inject tường minh platform MBeanServer |
| Muốn Spring chọn/tìm server đã tồn tại | MBeanServerFactoryBean với locating phù hợp |
| Muốn server riêng cho integration test | \`MBeanServerFactory.newMBeanServer()\` hoặc factory cấu hình tạo mới |
| Nhiều ApplicationContext dùng chung registry | Một \`MBeanServer\` được chia sẻ và inject vào các exporter |
| Plugin cần isolation | Cân nhắc server riêng, lifecycle và connector |
| Remote JMX | Cấu hình ConnectorServer/management agent độc lập, có bảo mật |
| Spring Boot có JMX auto-configuration | Kiểm tra cấu hình sẵn trước khi thêm exporter/factory |

Một nguyên tắc tốt là **quyết định MBeanServer theo yêu cầu quan sát của client**, rồi mới cấu hình exporter. Nếu dashboard hoặc JConsole kỳ vọng platform server, cần bảo đảm bean thực sự được đăng ký vào đó.

## 14. Bài tập thực hành

### Bài tập A — So sánh hai server

1. Tạo platform server bằng \`ManagementFactory.getPlatformMBeanServer()\`.
2. Tạo một server riêng bằng \`MBeanServerFactory.newMBeanServer()\`.
3. Đăng ký một Standard MBean demo vào server riêng.
4. Kiểm tra \`isRegistered\` trên cả hai server.
5. Giải thích vì sao JConsole local có thể không thấy demo MBean trong server riêng.

### Bài tập B — Spring FactoryBean

1. Tạo \`MBeanServerFactoryBean\` như mục 6.
2. Lấy \`MBeanServer\` từ Spring context.
3. So sánh với platform server bằng \`==\`.
4. Thay cấu hình locating/creating theo API phiên bản Spring dùng trong lab.
5. Ghi lại lựa chọn server và giải thích dựa trên cấu hình.

### Bài tập C — Exporter wiring

1. Tạo \`WorkerMonitor\` và \`MBeanExporter\`.
2. Inject server từ FactoryBean.
3. Kiểm tra ObjectName bằng \`isRegistered\`.
4. Gọi \`getAttribute\` trên **chính server đã inject**.
5. Đổi server của exporter sang một server khác và quan sát sự khác biệt.

### Bài tập D — Context lifecycle

Khởi động một ApplicationContext với exporter, kiểm tra ObjectName đã đăng ký, đóng context rồi kiểm tra unregistration. Khi dùng platform server, xác nhận JVM platform MXBeans vẫn tồn tại sau khi context đóng.

### Bài tập E — Spring Boot

Trong một ứng dụng Spring Boot test, ghi lại những bean loại \`MBeanServer\` và \`MBeanExporter\` có mặt. Bổ sung một cấu hình custom có chủ đích, rồi đối chiếu tập ObjectNames trước/sau. Không thay đổi remote JMX settings trong bài tập này.

## 15. Câu hỏi tự kiểm tra

1. \`MBeanServerFactoryBean\` và \`MBeanExporter\` khác nhau ở trách nhiệm nào?
2. Platform MBeanServer có gì đặc biệt so với server tạo mới?
3. Tại sao cùng JVM có thể có nhiều MBeanServer?
4. \`exposePlatformMBeanServer\` có mở cổng mạng không?
5. Nếu exporter dùng server riêng, JConsole local sẽ luôn thấy app MBean chứ?
6. Làm thế nào xác minh hai server references là cùng một object?
7. \`locateExistingServerIfPossible\` có bảo đảm chọn đúng platform server khi nhiều server cùng tồn tại không?
8. Khi nào nên tạo server riêng cho integration tests?
9. Vì sao \`RegistrationPolicy\` không phải công cụ chọn MBeanServer?
10. Khi dùng Spring Boot, tại sao nên kiểm tra auto-configuration trước khi thêm FactoryBean?

## 16. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — \`MBeanServerFactoryBean\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/MBeanServerFactoryBean.html
- Spring Framework API — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 — \`ManagementFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html
- Java SE 21 — \`MBeanServerFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerFactory.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html

**Ghi nhớ:** \`MBeanServerFactoryBean\` quyết định server nào được cấp cho Spring; \`MBeanExporter\` đưa bean vào server ấy. \`exposePlatformMBeanServer\` liên quan lựa chọn/exposure của platform server trong JVM, **không phải** mở cổng remote JMX. Cách chắc chắn nhất để tránh nhầm registry là so identity server và xác nhận ObjectName trong đúng MBeanServer mà exporter đang sử dụng.
