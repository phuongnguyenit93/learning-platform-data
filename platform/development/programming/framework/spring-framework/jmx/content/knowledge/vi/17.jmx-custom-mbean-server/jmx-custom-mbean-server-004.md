# Spring Framework JMX: Đăng ký bean vào MBeanServer đã tồn tại

## 1. Mục tiêu và bối cảnh

Trong Java Management Extensions (JMX), \`MBeanServer\` là nơi lưu registry những MBean đang được quản trị. Spring Framework cung cấp \`MBeanExporter\` để export Spring bean thành MBean và đăng ký chúng vào một server.

Trong ứng dụng thực tế, server cần dùng có thể **đã tồn tại** trước khi Spring context khởi tạo:

- JVM có platform \`MBeanServer\` được tạo bởi Java ManagementFactory.
- Application server hoặc framework hosting đã tạo server riêng.
- Một module nền tảng của ứng dụng đã tạo và đăng ký \`MBeanServer\` trong cùng JVM.
- Nhiều \`ApplicationContext\` cần cùng dùng một MBeanServer để quản trị nhất quán.

Khi đó không nên tạo thêm MBeanServer chỉ vì muốn export vài bean. Hướng tiếp cận là **xác định đúng server có sẵn, đưa server đó cho exporter, đăng ký bean vào server ấy, và kiểm tra lại đúng registry**.

Bài học giúp trả lời:

1. Phân biệt platform MBeanServer với các MBeanServer khác trong cùng JVM.
2. Tìm hoặc inject một MBeanServer đã tồn tại.
3. Cấu hình Spring \`MBeanExporter.setServer(...)\` hoặc hạ tầng annotation-driven để sử dụng server đó.
4. Tránh lỗi đăng ký trùng ObjectName, double-export và vòng đời cleanup không rõ ràng.
5. Xác minh từ Java/JConsole rằng bean thật sự nằm trong server mong muốn.

\`\`\`text
                         Một JVM
+------------------------------------------------------------+
|                                                            |
|  Existing MBeanServer                                      |
|  (platform hoặc server do host tạo)                         |
|            ^                                               |
|            | registerMBean(Object, ObjectName)             |
|            |                                               |
|       MBeanExporter (Spring)                               |
|            ^                                               |
|            |                                               |
|     Spring ApplicationContext                              |
|       +-- serviceControl                                   |
|       +-- cacheControl                                     |
|       +-- queueControl                                     |
|                                                            |
|  JMX client --> đúng MBeanServer / endpoint --> MBeans      |
+------------------------------------------------------------+
\`\`\`

**Nguyên tắc:** ObjectName chỉ duy nhất trong phạm vi một MBeanServer. Nếu exporter đăng ký bean vào server A nhưng client đọc server B, client có thể báo không tìm thấy MBean dù bước export đã thành công.

## 2. MBeanServer và MBeanServerFactory: không nhầm hai việc

Các API quan trọng của JMX:

| API | Vai trò |
|---|---|
| \`javax.management.MBeanServer\` | Registry MBean, hỗ trợ register/unregister, read/write attribute và invoke operation |
| \`java.lang.management.ManagementFactory.getPlatformMBeanServer()\` | Lấy platform MBeanServer chuẩn của JVM, tạo khi cần |
| \`javax.management.MBeanServerFactory.createMBeanServer(...)\` | Tạo một MBeanServer mới và thêm vào danh sách MBeanServer có thể tìm qua factory |
| \`javax.management.MBeanServerFactory.findMBeanServer(...)\` | Tìm các MBeanServer đã được đăng ký/giữ bởi factory trong JVM theo agent ID |
| \`org.springframework.jmx.support.MBeanServerFactoryBean\` | Spring FactoryBean có khả năng locate existing hoặc tạo server mới tùy cấu hình |
| \`org.springframework.jmx.support.MBeanServerConnectionFactoryBean\` | Hỗ trợ lấy connection đến MBeanServer; cần phân biệt local server và remote connection |
| \`org.springframework.jmx.export.MBeanExporter\` | Export bean Spring thành MBean và đăng ký vào MBeanServer được cấu hình |

Hai cách tạo server:

\`\`\`java
MBeanServer platform = ManagementFactory.getPlatformMBeanServer();
MBeanServer newServer = MBeanServerFactory.createMBeanServer(
    "com.example.private"
);
\`\`\`

Không nhất thiết hai reference này trỏ cùng registry. \`platform\` là server do JVM quản lý; \`newServer\` là một server khác. Nếu exporter dùng \`newServer\`, JConsole hoặc script chỉ nhìn platform server có thể không thấy MBean.

Khi đề bài là **đăng ký vào server đã tồn tại**, hãy ưu tiên tìm đúng server hoặc inject reference được tạo sẵn, không chủ động tạo server mới nếu chưa có yêu cầu.

## 3. Cách đơn giản nhất: dùng platform MBeanServer hiện có

Ứng dụng Java thường có platform MBeanServer:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer platformServer =
    ManagementFactory.getPlatformMBeanServer();
\`\`\`

\`getPlatformMBeanServer()\` trả platform server chuẩn và khởi tạo nếu nó chưa được tạo; vì vậy “đã tồn tại” ở đây thường có nghĩa JVM đã có hoặc sẽ cung cấp cùng một platform server theo contract.

Spring configuration:

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PlatformJmxServerConfig {

    @Bean
    public MBeanServer managementMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

Sau đó inject bean \`MBeanServer\` này vào exporter:

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;

@Bean
public MBeanExporter exporter(
        MBeanServer managementMBeanServer,
        WorkerControl workerControl) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(managementMBeanServer);
    exporter.setBeans(Map.of(
        "com.example.app:type=WorkerControl,name=primary",
        workerControl
    ));
    return exporter;
}
\`\`\`

Tại đây, \`setServer\` quan trọng hơn tên của Spring bean \`managementMBeanServer\`: exporter nhận **object MBeanServer cụ thể** và sử dụng object đó để đăng ký.

Nếu trong context có nhiều bean cùng kiểu \`MBeanServer\`, hãy dùng \`@Qualifier\` hoặc cấu hình dependency rõ ràng để không inject nhầm server.

## 4. Ví dụ đầy đủ: đăng ký Standard MBean vào server sẵn có

Định nghĩa Standard MBean:

\`\`\`java
package com.example.jmx;

public interface WorkerControlMBean {
    boolean isPaused();
    int getWorkerCount();
    void pause();
    void resume();
}
\`\`\`

Implementation:

\`\`\`java
package com.example.jmx;

public class WorkerControl implements WorkerControlMBean {
    private volatile boolean paused;
    private volatile int workerCount = 8;

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public int getWorkerCount() {
        return workerCount;
    }

    @Override
    public void pause() {
        paused = true;
    }

    @Override
    public void resume() {
        paused = false;
    }
}
\`\`\`

Spring configuration:

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class WorkerJmxConfig {

    @Bean
    public MBeanServer existingServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public WorkerControl workerControl() {
        return new WorkerControl();
    }

    @Bean
    public MBeanExporter workerExporter(
            MBeanServer existingServer,
            WorkerControl workerControl) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(existingServer);
        exporter.setBeans(Map.of(
            "com.example.app:type=WorkerControl,name=primary",
            workerControl
        ));
        return exporter;
    }
}
\`\`\`

MBean này có giao diện quản trị dựa vào \`WorkerControlMBean\`. \`MBeanExporter\` chịu trách nhiệm đăng ký, còn hợp đồng getter/operation đã được Java Standard MBean xác định.

Nếu dùng Spring Boot hoặc \`@EnableMBeanExport\` đồng thời, cần kiểm tra có exporter khác đang cố đăng ký cùng object/name hay không. Một bean nên có một nơi chịu trách nhiệm đăng ký để tránh xung đột vòng đời.

## 5. Nếu bean là POJO có Spring JMX annotations

Một Spring POJO không triển khai \`XxxMBean\` vẫn có thể export thông qua metadata/ModelMBean.

Ví dụ:

\`\`\`java
package com.example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=CacheControl,name=products",
    description = "Controls the product cache"
)
public class CacheControl {

    private volatile boolean enabled = true;

    @ManagedAttribute(description = "Cache enabled flag")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(description = "Update cache enabled flag")
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation(description = "Clear cache content")
    public void clearCache() {
        // gọi component cache thực ở đây
    }
}
\`\`\`

Để cấu hình một explicit exporter vào đúng MBeanServer và dùng annotation metadata:

\`\`\`java
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

@Bean
AnnotationJmxAttributeSource jmxAttributeSource() {
    return new AnnotationJmxAttributeSource();
}

@Bean
MetadataMBeanInfoAssembler jmxAssembler(
        AnnotationJmxAttributeSource source) {
    MetadataMBeanInfoAssembler assembler =
        new MetadataMBeanInfoAssembler();
    assembler.setAttributeSource(source);
    return assembler;
}

@Bean
MBeanExporter cacheExporter(
        MBeanServer existingServer,
        CacheControl cacheControl,
        MetadataMBeanInfoAssembler assembler) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(existingServer);
    exporter.setAssembler(assembler);
    exporter.setBeans(Map.of(
        "com.example.app:type=CacheControl,name=products",
        cacheControl
    ));
    return exporter;
}
\`\`\`

Cấu hình này kết hợp hai phần độc lập:
- **Server selection:** \`setServer(existingServer)\`.
- **Member selection:** \`setAssembler(assembler)\`, lấy metadata từ annotations.

Đừng nhầm việc chọn server với việc chọn JMX attributes/operations. Đăng ký thành công vào đúng server không đảm bảo POJO expose đúng member nếu assembler khác ý định.

## 6. Tìm một MBeanServer do container/application server tạo

Trong một JVM có thể có nhiều MBeanServer. Nếu host đã tạo server trước khi Spring khởi động, cần cơ chế phát hiện hoặc nhận trực tiếp reference.

### 6.1. Tìm theo agentId qua MBeanServerFactory

Java JMX hỗ trợ:

\`\`\`java
import java.util.ArrayList;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

ArrayList<MBeanServer> servers =
    MBeanServerFactory.findMBeanServer(null);

for (MBeanServer server : servers) {
    System.out.println(server.getDefaultDomain());
}
\`\`\`

\`findMBeanServer(null)\` trả danh sách server được factory giữ/biết đến, không phải cam kết tìm được mọi MBeanServer được tạo theo mọi con đường hoặc đang tồn tại trên toàn hệ thống. Tên domain mặc định giúp gợi ý nhưng **không phải định danh đủ duy nhất** giữa các server.

Khi host cung cấp agent ID đã biết, có thể dùng:

\`\`\`java
ArrayList<MBeanServer> selected =
    MBeanServerFactory.findMBeanServer(agentId);
\`\`\`

Cần xác định agent ID theo contract của hosting environment. Không chọn ngẫu nhiên phần tử đầu tiên trong danh sách nếu nhiều server phù hợp.

### 6.2. Nhận server trực tiếp từ container

Nhiều môi trường server có API, JNDI binding hoặc Spring bean đã cung cấp \`MBeanServer\`. Khi có API chính thức, **inject reference** là cách ít mơ hồ nhất:

\`\`\`java
@Configuration
public class HostJmxConfiguration {

    @Bean("hostMBeanServer")
    public MBeanServer hostMBeanServer(
            HostMBeanServerProvider provider) {
        return provider.getMBeanServer();
    }
}
\`\`\`

Ở đây \`HostMBeanServerProvider\` là interface giả định do môi trường tích hợp cung cấp, không phải class mặc định của Java/Spring. Ý tưởng là kết nối adapter host với Spring DI.

Đối với các container cụ thể, cách lấy reference phải theo tài liệu và quyền truy cập của container đó. Không nên dùng tên class giả định như một API có thật.

## 7. Spring MBeanServerFactoryBean: locate existing và fallback

Spring cung cấp \`org.springframework.jmx.support.MBeanServerFactoryBean\`, thường dùng khi muốn để Spring tìm một server có sẵn hoặc tạo một server trong trường hợp không tìm thấy.

Ví dụ:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Bean
MBeanServerFactoryBean mbeanServerFactory() {
    MBeanServerFactoryBean factory =
        new MBeanServerFactoryBean();
    factory.setLocateExistingServerIfPossible(true);
    return factory;
}
\`\`\`

Khi bật \`locateExistingServerIfPossible\`, factory cố tìm server hiện có; tùy cấu hình, nếu không tìm được, nó có thể tạo server mới.

**Lưu ý quan trọng:** nếu yêu cầu là *phải dùng đúng server đã tồn tại*, chính sách “nếu không tìm thấy thì tạo” không bảo đảm mục tiêu. Đó là fallback tạo registry mới và có thể che lỗi không tìm đúng server của host.

Với nhu cầu strict reuse:
- Dùng injection từ provider được host hỗ trợ.
- Hoặc dùng Spring utility locate existing với yêu cầu báo lỗi nếu không tìm thấy.
- Đặt kiểm tra identity/marker MBean sau khi locate để xác nhận đúng server.

### 7.1. JmxUtils.locateMBeanServer

Spring có helper:

\`\`\`java
import javax.management.MBeanServer;
import org.springframework.jmx.support.JmxUtils;

MBeanServer server = JmxUtils.locateMBeanServer();
\`\`\`

Phương thức này tìm MBeanServer theo các cơ chế Spring hỗ trợ và có thể throw nếu không tìm thấy. Các overload có thể nhận agent ID tùy API. Khi có nhiều server trong JVM, cần sử dụng tham số hoặc cơ chế lựa chọn chính xác, tránh phụ thuộc thứ tự tìm.

Tài liệu Spring version đang dùng là nguồn xác định hành vi cụ thể, đặc biệt với container-managed MBeanServer.

## 8. Cấu hình bean MBeanServer được inject tường minh

Một cách rõ ownership là tạo Spring bean tên cố định cho server mà application mong muốn dùng:

\`\`\`java
@Configuration
public class ExistingServerConfig {

    @Bean("applicationMBeanServer")
    public MBeanServer applicationMBeanServer() {
        return java.lang.management.ManagementFactory
            .getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter applicationExporter(
            @Qualifier("applicationMBeanServer")
            MBeanServer applicationMBeanServer,
            CacheControl cacheControl,
            MetadataMBeanInfoAssembler assembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(applicationMBeanServer);
        exporter.setAssembler(assembler);
        exporter.setBeans(Map.of(
            "com.example.app:type=CacheControl,name=products",
            cacheControl
        ));
        return exporter;
    }
}
\`\`\`

Trong ví dụ, cần có imports \`Configuration\`, \`Bean\`, \`Qualifier\`, \`MBeanServer\`, \`MBeanExporter\`, \`Map\` và các class domain tương ứng. Về mặt DI, \`@Qualifier\` tránh trường hợp nhiều \`MBeanServer\` bean cùng tồn tại khiến Spring không biết chọn đối tượng nào.

Nếu host đã có bean \`MBeanServer\`, **không nhất thiết khai báo lại bean mới**; có thể inject trực tiếp vào exporter theo qualifier/bean name mà host cung cấp. Cách tốt nhất là hiểu context đang có gì và reuse reference hiện hữu.

## 9. Annotation-driven exporter có thể dùng server có sẵn không?

Có. Khi dùng Spring annotation-driven JMX, infrastructure exporter cũng cần một server đích. Trong Java configuration, \`@EnableMBeanExport\` hỗ trợ tham chiếu đến MBeanServer bean phù hợp trong context:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "applicationMBeanServer")
public class AnnotationJmxConfig {

    @Bean("applicationMBeanServer")
    public MBeanServer applicationMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public CacheControl cacheControl() {
        return new CacheControl();
    }
}
\`\`\`

Ý nghĩa: Spring annotation exporter được trỏ đến server bean có tên \`applicationMBeanServer\`, thay vì tự dựa vào một server khác do convention hoặc auto-config.

Trong dự án, cần kiểm tra signature/thuộc tính annotation theo phiên bản Spring đang dùng. Nếu Boot cũng thiết lập JMX auto-configuration, đảm bảo chỉ một exporter chịu trách nhiệm đăng ký cùng bean.

## 10. Bean đã export nhưng client không nhìn thấy

Một lỗi phổ biến:

\`\`\`java
MBeanServer serverA =
    ManagementFactory.getPlatformMBeanServer();

MBeanServer serverB =
    MBeanServerFactory.createMBeanServer("other");

exporter.setServer(serverB);

// Client lại truy vấn:
serverA.getAttribute(name, "MaxConnections");
\`\`\`

Trong trường hợp này, \`name\` có thể được đăng ký ở B nhưng không tồn tại ở A. Client báo \`InstanceNotFoundException\`.

Cách chẩn đoán:

\`\`\`java
boolean a = serverA.isRegistered(name);
boolean b = serverB.isRegistered(name);

System.out.printf(
    "serverA=%s, serverB=%s%n",
    a,
    b
);
\`\`\`

Thường cần xác định:
- Server đích exporter thực sự sử dụng là server nào?
- Spring context nào sở hữu exporter?
- JConsole/remote connector kết nối vào MBeanServer nào?
- Nếu có nhiều MBeanServer, endpoint JMX của host đang công bố registry nào?

Không giải quyết bằng cách đăng ký bean vào **mọi** MBeanServer theo thói quen: việc đó có thể dẫn tới duplicate metrics, khó kiểm soát quyền quản trị và rối ownership khi shutdown.

## 11. Đăng ký trực tiếp bằng JMX API và dùng Spring exporter khác nhau thế nào?

Có thể đăng ký thủ công:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.app:type=WorkerControl,name=primary"
);

server.registerMBean(new WorkerControl(), name);
\`\`\`

Đường này phù hợp khi ứng dụng chủ động quản lý vòng đời JMX mà không muốn dùng Spring exporter. Nhưng nếu bean đã nằm trong Spring context, \`MBeanExporter\` thường tiện hơn vì:
- Có thể đăng ký nhiều bean theo mapping.
- Có thể sử dụng metadata assembler để export POJO.
- Có naming strategies và registration policies.
- Tích hợp lifecycle của \`ApplicationContext\`.
- Có support notification listener và notification publisher.
- Đỡ phải tự viết cleanup/unregister cho từng bean.

Đừng làm cả hai với cùng ObjectName trừ khi thực sự có lý do và quy tắc ownership riêng; \`MBeanExporter\` không tự hiểu một registration thủ công là “của nó”.

## 12. Trùng ObjectName trong shared MBeanServer

Khi nhiều Spring contexts hoặc module cùng dùng một server, trùng ObjectName là lỗi dễ gặp:

\`\`\`text
Context A:
  com.example.app:type=WorkerPool,name=default

Context B:
  com.example.app:type=WorkerPool,name=default
\`\`\`

Cả hai có thể cùng dùng tên đó trong code, nhưng một \`MBeanServer\` không thể chứa hai MBean dưới cùng ObjectName.

Các hướng thiết kế:
1. Nếu là **cùng một tài nguyên**, chỉ một context/exporter nên sở hữu registration.
2. Nếu là **hai tài nguyên khác nhau**, bổ sung key như \`context\`, \`service\`, \`name\`, \`instance\` để phân biệt.
3. Nếu bean A đã được host export trước, Spring không nên tự register trùng.
4. Tránh bật \`IGNORE_EXISTING\` hoặc \`REPLACE_EXISTING\` để che collision mà không biết hậu quả.

Ví dụ namespace:

\`\`\`text
com.example.app:type=WorkerPool,context=admin,name=default
com.example.app:type=WorkerPool,context=public,name=default
\`\`\`

Nếu cùng một Spring application có nhiều replica nằm ở các JVM khác nhau, mỗi JVM có MBeanServer riêng nên có thể dùng cùng ObjectName logic. Monitoring nên phân biệt endpoint/target thay vì bắt buộc nhét pod ID vào mọi ObjectName.

## 13. Lifecycle: server có sẵn không đồng nghĩa Spring sở hữu server

Một phân biệt đặc biệt quan trọng:

- **MBeanServer tồn tại trước Spring**: thường do JVM hoặc host quản lý. Spring không nên tự tắt/release server trừ khi API tích hợp quy định rõ quyền sở hữu.
- **MBean được exporter đăng ký**: exporter cần quản lý unregister khi ApplicationContext dừng theo lifecycle của nó.
- **MBean của module khác**: dù cùng server, không được unregister tùy tiện.

Ví dụ:

\`\`\`text
Host starts
  |
  +-- creates/owns MBeanServer
  |
  +-- Spring Context A starts
  |       +-- exports MBean A
  |
  +-- Spring Context B starts
  |       +-- exports MBean B
  |
  +-- Context A stops
  |       +-- unregisters MBean A only
  |
  +-- Context B still running
  |       +-- MBean B remains registered
  |
  +-- Host stops
          +-- manages MBeanServer lifecycle
\`\`\`

Không nhầm \`unregisterMBean(name)\` với việc tắt toàn bộ \`MBeanServer\`.

Với nhiều exporter đăng ký trùng cùng một name và có registration policy replace/ignore, ownership có thể trở nên khó đoán. Tốt hơn là một ObjectName có một owner rõ.

## 14. Kiểm tra đăng ký thực tế

Một lớp kiểm tra nhỏ:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxRegistrationInspector {

    public static void inspect(
            MBeanServer server,
            ObjectName name) throws Exception {

        System.out.println("Registered: "
            + server.isRegistered(name));

        if (!server.isRegistered(name)) {
            return;
        }

        MBeanInfo info = server.getMBeanInfo(name);

        System.out.println("MBean class: "
            + info.getClassName());

        for (var attribute : info.getAttributes()) {
            System.out.printf(
                "Attribute=%s, type=%s, readable=%s, writable=%s%n",
                attribute.getName(),
                attribute.getType(),
                attribute.isReadable(),
                attribute.isWritable()
            );
        }

        for (var operation : info.getOperations()) {
            System.out.println(
                "Operation: " + operation.getName()
            );
        }
    }
}
\`\`\`

Sử dụng:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.app:type=WorkerControl,name=primary"
);

JmxRegistrationInspector.inspect(existingServer, name);
\`\`\`

Điều nên kiểm tra:
- Đúng server được inject từ host/platform?
- ObjectName có hợp lệ và thực sự được register?
- Contract JMX có các attributes/operations mong muốn?
- Script/JConsole có kết nối đúng endpoint tương ứng không?
- Có MBean khác cùng domain/name bị bỏ sót hoặc bị thay thế không?

Nếu cần khám phá nhiều MBean, dùng pattern:

\`\`\`java
ObjectName pattern = new ObjectName(
    "com.example.app:type=WorkerControl,*"
);

for (ObjectName candidate :
        existingServer.queryNames(pattern, null)) {
    System.out.println(candidate.getCanonicalName());
}
\`\`\`

## 15. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| \`InstanceAlreadyExistsException\` | Shared server đã có MBean với ObjectName đó | Kiểm tra owner, naming và double-export |
| \`InstanceNotFoundException\` khi client gọi | Client đang dùng server khác hoặc ObjectName sai | So \`isRegistered\` ở đúng server |
| Không thấy bean trong JConsole | Endpoint/registry được công bố không phải server exporter dùng | Kiểm tra connector/server host |
| \`NotCompliantMBeanException\` | Bean không tuân thủ JMX contract và không được adapter phù hợp | Dùng Standard MBean hoặc Spring ModelMBean assembler |
| \`MalformedObjectNameException\` | ObjectName sai cú pháp | Tạo tên theo convention, quote/validate values |
| Metadata thiếu operation | Assembler không công bố member | Đọc \`MBeanInfo\`, kiểm tra annotations |
| Spring startup lỗi vì server bean | Không locate được server, nhiều candidates | Kiểm tra injection/qualifier/host API |
| Export thành công nhưng mất sau shutdown | Exporter unregister MBean theo lifecycle | Xác định owner và thứ tự context dừng |
| Server tạo mới ngoài ý muốn | Factory có fallback create | Dùng strict locate/injection |
| Script đọc platform server nhưng MBean ở custom server | Nhầm registry | Dùng cùng server/connection mà exporter sử dụng |

Lỗi có thể được Spring bọc trong startup exception; cần xem cause chain bên dưới, đặc biệt \`InstanceAlreadyExistsException\` và \`NotCompliantMBeanException\`.

## 16. Quy trình triển khai vào ứng dụng

Một quy trình có thể áp dụng:

### Bước 1 — Xác định nguồn server

Chọn một trong:
- Platform MBeanServer của JVM.
- Server do application server/container cung cấp.
- Server do một module nền tảng tạo trước.

Nếu yêu cầu strict reuse, cấu hình phải **fail fast** khi server cần dùng không tồn tại, thay vì tạo một server mới âm thầm.

### Bước 2 — Đưa reference server vào Spring

Sử dụng một Spring bean \`MBeanServer\`, hoặc inject provider adapter của host. Dùng tên/qualifier rõ nếu có nhiều servers.

### Bước 3 — Thiết kế ObjectName

Ví dụ:

\`\`\`text
com.example.platform:type=CacheControl,service=catalog,name=products
com.example.platform:type=QueueControl,service=orders,name=shipping
\`\`\`

Tên phải không trùng trong server và ổn định qua restart khi client/dashboard dùng nó.

### Bước 4 — Chọn exporter

- Standard/Dynamic MBean: có thể export trực tiếp với \`MBeanExporter\`.
- POJO Spring: dùng \`MBeanInfoAssembler\`/annotation infrastructure tương ứng.
- Nếu annotation-driven, trỏ exporter đến server bean đã xác định.

### Bước 5 — Khởi động và xác minh

Đọc log đăng ký, chạy \`isRegistered\`, \`getMBeanInfo\`, thử read-only attribute qua server.

### Bước 6 — Kiểm tra shutdown

Dừng một Spring context, xác nhận MBean thuộc context đó được unregister; các MBean từ host/context khác phải tiếp tục tồn tại nếu owner của chúng chưa dừng.

### Bước 7 — Kiểm tra môi trường vận hành

Remote JMX phải được bảo vệ bằng authentication, authorization, transport security và network access controls phù hợp. Không expose JMX endpoint công khai chỉ để “xem cho nhanh”.

## 17. Bài thực hành

### Bài 1: Platform server và server mới

Cho:

\`\`\`java
MBeanServer a =
    ManagementFactory.getPlatformMBeanServer();

MBeanServer b =
    MBeanServerFactory.createMBeanServer("private");
\`\`\`

Nếu export bean vào \`b\` nhưng client truy vấn \`a\`, vì sao \`InstanceNotFoundException\` có thể xảy ra?

**Giải thích:** \`a\` và \`b\` là hai registry độc lập. Bean đăng ký ở \`b\` không tự xuất hiện trong \`a\`.

### Bài 2: Cấu hình exporter đúng server

Điền phần cần thiết:

\`\`\`java
MBeanExporter exporter = new MBeanExporter();
// Đặt server đã inject vào exporter
exporter.setServer(existingServer);
\`\`\`

### Bài 3: Shared server với hai Spring contexts

Hai contexts đều export \`com.example.app:type=Worker,name=default\`. Hãy đề xuất cách đặt tên và ownership.

**Gợi ý:** thêm \`context=admin/public\` hoặc role logic; chỉ một context owner của mỗi MBean. Không dùng replace/ignore để che cấu hình sai.

### Bài 4: Strict reuse

Vì sao \`locateExistingServerIfPossible(true)\` có thể chưa đủ nếu yêu cầu “phải dùng server host đã tạo”?

**Gợi ý:** nếu không tìm thấy server, factory có thể tạo registry mới. Cần strict locate/inject và kiểm tra server identity.

### Bài 5: Trạng thái sau shutdown

Context A export MBean A, context B export MBean B vào cùng MBeanServer của host. Context A dừng, điều gì nên xảy ra?

**Gợi ý:** MBean A được cleanup theo owner A; MBean B vẫn tồn tại nếu B còn hoạt động, host MBeanServer vẫn sống.

### Bài 6: Bean thường có annotation

Một \`CacheControl\` chỉ có \`@ManagedResource\` và \`@ManagedAttribute\`, không có Standard MBean interface. Vì sao \`setServer(existingServer)\` vẫn chưa đủ?

**Gợi ý:** còn cần metadata/ModelMBean adapter hoặc annotation-driven export đúng cách để tạo hợp đồng JMX cho POJO.

## 18. Ghi nhớ

**Đăng ký Spring bean vào MBeanServer đã tồn tại** là bài toán kết nối exporter với **đúng server reference**, không phải bài toán tạo server mới. Hãy nhận server từ platform API hoặc provider của host, inject nó vào Spring, rồi cấu hình \`MBeanExporter.setServer(existingServer)\` hay annotation-driven infrastructure trỏ đến server bean đó.

Phân biệt rõ **owner của MBeanServer** với **owner của từng MBean registration**, bảo đảm ObjectName không trùng, và xác minh bằng \`isRegistered\`, \`MBeanInfo\` trong chính server đã chọn. Khi host có nhiều server, strict discovery và explicit injection giúp tránh “export thành công nhưng công cụ không nhìn thấy” — một lỗi JMX rất phổ biến trong các ứng dụng Spring nhiều context.