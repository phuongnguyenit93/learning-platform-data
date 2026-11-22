# Thuộc tính server và defaultDomain của AnnotationMBeanExporter trong Spring Framework JMX

## Mục tiêu

Khi xuất các Spring bean thành JMX MBean, hai cấu hình dễ bị nhầm là **server** và **defaultDomain**. Cả hai xuất hiện trong khu vực thiết lập exporter, nhưng chúng giải quyết hai vấn đề khác nhau:

- **server** quyết định MBean được đăng ký vào **MBeanServer nào**.
- **defaultDomain** cung cấp một **domain mặc định cho chiến lược đặt ObjectName** của exporter trong những trường hợp không có domain được chỉ định tường minh.

Đây là hai trục độc lập: chọn đúng MBeanServer không tự làm ObjectName đúng; đổi domain không chuyển MBean sang một MBeanServer khác. Trong ứng dụng Spring có nhiều context, server hoặc các exporter khác nhau, phân biệt hai cấu hình này giúp tránh lỗi không tìm thấy MBean, xung đột tên và khó kiểm soát vòng đời.

Bài học này tập trung vào cấu hình JMX annotation-based export bằng Spring Framework, thường thông qua \`AnnotationMBeanExporter\` hoặc cơ chế tương đương của \`@EnableMBeanExport\`. Các ví dụ minh họa cần được điều chỉnh theo phiên bản Spring Framework và cách Spring Boot auto-configuration đang được bật trong dự án.

Sau bài học, bạn có thể:

1. Giải thích cách exporter chọn MBeanServer đích.
2. Hiểu sự khác biệt giữa server, default domain của MBeanServer và defaultDomain của exporter.
3. Xác định khi nào defaultDomain có tác dụng và khi nào ObjectName đã được khai báo tường minh.
4. Viết cấu hình Spring Java và annotation có chủ đích cho một hoặc nhiều MBeanServer.
5. Chẩn đoán trường hợp JConsole thấy sai MBean, ObjectName bị trùng hoặc exporter đăng ký vào server ngoài ý muốn.
6. Thiết kế namespace và ownership rõ ràng trong nhiều Spring ApplicationContext.

## 1. Ba đối tượng, ba trách nhiệm

Mô hình tối thiểu:

\`\`\`text
Spring bean
    |
    | @ManagedResource + @ManagedAttribute + @ManagedOperation
    v
AnnotationMBeanExporter
    |
    | server = MBeanServer cụ thể
    | naming strategy + defaultDomain
    v
MBeanServer
    |
    | registry: ObjectName -> MBean
    v
JMX client (JConsole, script, monitoring)
\`\`\`

Một MBean luôn được xác định trong **một MBeanServer cụ thể** bằng **một ObjectName cụ thể**. Ví dụ:

\`\`\`text
MBeanServer: platform server của JVM A
ObjectName:  com.example.inventory:type=CacheMetrics,name=ProductCache
\`\`\`

Cũng ObjectName đó có thể tồn tại trong MBeanServer khác mà không xung đột ở mức JMX registry. Ngược lại, hai bean đăng ký cùng ObjectName vào **cùng một** server sẽ xung đột, trừ khi người viết chủ động cấu hình chính sách xử lý đăng ký phù hợp.

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| MBeanServer | Platform server, server do container tạo, server riêng | Nơi chứa đăng ký MBean |
| Domain của ObjectName | \`com.example.inventory\` | Namespace logic trong registry |
| Key properties của ObjectName | \`type=CacheMetrics,name=ProductCache\` | Phân biệt các instance cùng domain |
| \`server\` trên exporter | \`MBeanServer\` bean được inject | MBeanServer được exporter dùng |
| \`defaultDomain\` trên exporter | \`com.example.inventory\` | Domain fallback mà chiến lược đặt tên sử dụng khi cần |

Nhớ rằng **ObjectName đầy đủ gồm domain và key property list**. Đổi \`defaultDomain\` không tự thay đổi \`type\`, \`name\` hoặc \`instance\`.

## 2. Thuộc tính server: đăng ký MBean vào đâu?

\`AnnotationMBeanExporter\` là một cơ chế của Spring JMX hỗ trợ tìm các bean có metadata quản trị và xuất chúng tới một \`MBeanServer\`. Nó kế thừa khả năng quản lý registration từ cơ chế exporter của Spring.

Cấu hình \`server\` về mặt khái niệm là một tham chiếu đến đối tượng thực hiện \`javax.management.MBeanServer\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JmxServerConfig {

    @Bean
    public MBeanServer applicationMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

Khi exporter được cấu hình dùng bean này, mọi MBean do exporter quản lý sẽ được đăng ký trong **platform MBeanServer của JVM hiện tại**. Platform server còn chứa các JVM management MXBean như memory, threads và class loading. Vì thế có thể nhìn thấy MBean ứng dụng và MBean nền tảng trên cùng một registry.

Đặt \`server\` là một server riêng sẽ chuyển nơi đăng ký đối với exporter đó:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DedicatedJmxServerConfig {

    @Bean(destroyMethod = "")
    public MBeanServer dedicatedMBeanServer() {
        return MBeanServerFactory.createMBeanServer("com.example.private");
    }
}
\`\`\`

Ví dụ chỉ minh họa việc tạo server riêng. Khi dùng server riêng trong hệ thống thật, component sở hữu phải quản lý registration, connector, shutdown và \`MBeanServerFactory.releaseMBeanServer(server)\` nếu server do factory tạo và đang được factory theo dõi. \`destroyMethod = ""\` không làm việc đó; nó chỉ tránh Spring suy luận một method destroy tự động cho bean reference. Đừng tạo server riêng chỉ vì muốn đổi namespace: một platform server có thể chứa nhiều domain.

### 2.1 server không phải địa chỉ mạng

Giá trị \`server\` ở đây là một **đối tượng MBeanServer**, không phải URL, hostname hay port JMX. Truy cập từ xa là trách nhiệm của JMX connector và cấu hình bảo mật.

\`\`\`text
Exporter ───── register ─────> MBeanServer
                                  ^
                                  |
                       JMXConnectorServer
                                  ^
                                  |
                              Remote client
\`\`\`

Một server có thể tồn tại và chứa các MBean ngay cả khi không có connector từ xa nào đang chạy. Ngược lại, remote client kết nối đến một connector gắn với **server khác** sẽ không thấy những MBean vừa export dù thao tác đăng ký đã thành công.

### 2.2 Để Spring tự tìm server hay chỉ định tường minh?

Cơ chế exporter của Spring có thể tìm MBeanServer theo chiến lược mặc định nếu không được cung cấp server cụ thể. Tuy nhiên lựa chọn runtime/container, classpath, cấu hình và số lượng server đang tồn tại có thể làm hành vi khó đoán nếu không hiểu thiết lập. Với ứng dụng có yêu cầu vận hành rõ ràng, việc cung cấp \`MBeanServer\` được chọn tường minh giúp giảm bất định.

Nếu ứng dụng thực sự chỉ dùng một platform server, một cấu hình đơn giản và nhất quán thường phù hợp. Nếu ứng dụng chạy trong container hoặc chung JVM với nhiều sản phẩm, hãy xác định server mà connector và hệ thống monitoring sẽ truy cập trước khi export.

## 3. defaultDomain: đặt tên trong cùng một server

\`ObjectName\` JMX có dạng:

\`\`\`text
<domain>:<key1>=<value1>,<key2>=<value2>,...
\`\`\`

Ví dụ:

\`\`\`text
com.example.orders:type=Queue,name=Pending
\`\`\`

Trong ví dụ:

- Domain là \`com.example.orders\`.
- Key properties là \`type=Queue,name=Pending\`.
- Toàn bộ chuỗi là \`ObjectName\`.

\`defaultDomain\` của exporter thường được sử dụng bởi chiến lược đặt tên (naming strategy), chẳng hạn \`MetadataNamingStrategy\`, để chọn domain khi metadata không cung cấp một ObjectName/domain rõ ràng. Điều này **không tương đương** thay đổi server, domain mặc định nội tại của server, hoặc toàn bộ ObjectName được định nghĩa tường minh.

Hình dung:

\`\`\`text
Exporter A
  server = platformMBeanServer
  defaultDomain = "com.example.orders"
      |
      +-- Bean QueueStats --> com.example.orders:name=queueStats,type=...
      +-- Bean WorkerStats --> com.example.orders:name=workerStats,type=...

Exporter B
  server = platformMBeanServer
  defaultDomain = "com.example.billing"
      |
      +-- Bean InvoiceStats --> com.example.billing:name=invoiceStats,type=...
\`\`\`

Hai exporter dùng **cùng server** nhưng có domain khác nhau. Nếu đặt tên đầy đủ phù hợp, chúng không xung đột.

Ngược lại:

\`\`\`text
Exporter A -> server X -> com.example.orders:type=Queue,name=Main
Exporter B -> server Y -> com.example.orders:type=Queue,name=Main
\`\`\`

Ở đây hai đăng ký không xung đột vì khác server, dù ObjectName giống nhau. Các client vẫn phải kết nối đúng server để thấy đối tượng cần quan sát.

### 3.1 defaultDomain không ghi đè ObjectName tường minh

Xét bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.explicit:type=Cache,name=ProductCache",
    description = "Metrics for product cache"
)
public class ProductCacheMetrics {
}
\`\`\`

Nếu exporter dùng \`defaultDomain = "com.example.fallback"\`, bean vẫn yêu cầu \`com.example.explicit:type=Cache,name=ProductCache\` theo metadata tường minh. Thay defaultDomain không phải cách đổi tên bean đã chỉ định đầy đủ ObjectName.

Nguyên tắc thiết kế: những MBean cần ObjectName ổn định để được external monitoring gọi có thể công bố tên đầy đủ rõ ràng; default domain có ích khi muốn thống nhất tên cho các bean do naming strategy tạo.

## 4. Ba domain có thể dễ bị nhầm

Cần phân biệt:

1. **Domain trong ObjectName cụ thể**: \`com.example.app\` trong \`com.example.app:type=Pool,name=Primary\`.
2. **Default domain của MBeanServer**: giá trị do implementation của server xác định hoặc dùng trong các trường hợp ObjectName/domain tương ứng theo JMX.
3. **defaultDomain của Spring exporter/naming strategy**: cấu hình cấp ứng dụng cho cách tạo tên.

Một server riêng có thể được tạo với default domain:

\`\`\`java
MBeanServer server =
    MBeanServerFactory.createMBeanServer("com.example.serverDefault");
\`\`\`

Sau đó Spring exporter vẫn có thể cấu hình naming strategy với \`defaultDomain="com.example.application"\`. Hai giá trị này không nhất thiết giống nhau.

\`server.getDefaultDomain()\` trả về default domain do server báo cáo; nó **không chứng minh** mọi MBean trong server đều thuộc domain đó. Một registry có thể chứa hàng chục domain khác nhau.

Ví dụ:

\`\`\`java
System.out.println(server.getDefaultDomain());
System.out.println(server.getDomains().length);
\`\`\`

\`getDomains()\` cho biết các domain hiện có với MBean đã đăng ký, còn \`getDefaultDomain()\` cho biết domain mặc định của server. Nếu đang kiểm tra MBean Spring bị “mất”, tra cứu **đúng ObjectName** hoặc \`queryNames\` theo domain/keys phù hợp.

## 5. Cấu hình AnnotationMBeanExporter

Tùy cách cấu hình ứng dụng, có thể dùng trực tiếp \`AnnotationMBeanExporter\` hoặc cơ chế \`@EnableMBeanExport\` tạo exporter. Hai ví dụ dưới đây thể hiện ý định cấu hình; nên chọn một cách export chính trong mỗi phạm vi để tránh đăng ký trùng.

### 5.1 Khai báo AnnotationMBeanExporter trực tiếp

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

@Configuration
public class DirectExporterConfiguration {

    @Bean
    public MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public AnnotationMBeanExporter annotationMBeanExporter(
            MBeanServer jmxServer) {
        AnnotationMBeanExporter exporter = new AnnotationMBeanExporter();
        exporter.setServer(jmxServer);
        exporter.setDefaultDomain("com.example.application");
        return exporter;
    }
}
\`\`\`

Trong dự án thực tế, tránh vừa khai báo exporter trực tiếp vừa để một exporter tự động khác đăng ký cùng MBean. Tên chính xác, cách khởi tạo và hook lifecycle phụ thuộc phiên bản Spring Framework; kiểm tra API đang dùng khi nâng cấp.

Bean được annotate:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    description = "Worker state and control operations"
)
public class ImportWorkerAdmin {

    private volatile boolean paused;

    @ManagedAttribute
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation(description = "Request pausing new work")
    public void pause() {
        paused = true;
    }
}
\`\`\`

Metadata không chỉ định \`objectName\` tường minh. Naming strategy của exporter sẽ sinh tên theo quy tắc được cấu hình; \`defaultDomain\` giúp điều chỉnh domain fallback. Cấu trúc key property chính xác của tên được sinh phụ thuộc chiến lược đặt tên hiện hành, vì vậy khi client hoặc alert rule cần một ObjectName cố định, hãy kiểm tra tên thực tế trong registry và quản lý hợp đồng tên rõ ràng.

### 5.2 Dùng @EnableMBeanExport

Spring cung cấp annotation để bật export MBean có metadata:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(
    defaultDomain = "com.example.application",
    server = "jmxServer"
)
public class AnnotationDrivenJmxConfiguration {
}
\`\`\`

Cách này tham chiếu bean tên \`jmxServer\` nếu được khai báo trong context. Ví dụ server:

\`\`\`java
@Bean
public MBeanServer jmxServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
\`\`\`

Giá trị \`server\` ở \`@EnableMBeanExport\` là **tên bean MBeanServer trong Spring context** theo hợp đồng annotation, trong khi \`setServer\` của exporter nhận **đối tượng MBeanServer**. Sự khác nhau này quan trọng: không điền host:port vào \`server\` của annotation.

Khi dùng Spring Boot, JMX export có thể được điều khiển bởi cấu hình Boot. Cần thống nhất một cơ chế khai báo để không tạo exporter trùng nhau. Không suy luận rằng \`@EnableMBeanExport\` tự bật remote JMX connector.

## 6. Ví dụ tổng hợp: hai domain, cùng platform MBeanServer

Giả sử ứng dụng có hai nhóm MBean:

- \`InventoryMetrics\`: báo cáo số lượng item chờ đồng bộ.
- \`BillingMetrics\`: báo cáo thống kê hóa đơn.

Cả hai có thể đăng ký trong platform server:

\`\`\`text
platform MBeanServer
  ├── com.example.inventory:type=Metrics,name=SyncQueue
  └── com.example.billing:type=Metrics,name=InvoiceQueue
\`\`\`

Để bảo đảm tên chính xác, chỉ định ObjectName tường minh trong annotation:

\`\`\`java
@Component
@ManagedResource(
    objectName = "com.example.inventory:type=Metrics,name=SyncQueue")
class InventoryMetrics {
    @ManagedAttribute
    public long getPendingCount() {
        return 0L;
    }
}

@Component
@ManagedResource(
    objectName = "com.example.billing:type=Metrics,name=InvoiceQueue")
class BillingMetrics {
    @ManagedAttribute
    public long getPendingCount() {
        return 0L;
    }
}
\`\`\`

Trường hợp này, \`defaultDomain\` không cần tham gia đặt tên cho hai MBean vì chúng đã khai báo ObjectName đầy đủ. Cấu hình exporter vẫn cần trỏ vào server mà monitoring sẽ truy cập.

Nếu loại bỏ \`objectName\` tường minh và muốn mỗi nhóm có default domain riêng, cần cấu hình các exporter và phạm vi bean mà chúng chịu trách nhiệm theo cách không quét/export trùng nhau. Chỉ tạo hai exporter với defaultDomain khác nhau nhưng cùng quét toàn bộ context không tự chia nhóm MBean.

## 7. Nhiều MBeanServer trong một JVM

Mô hình nhiều server:

\`\`\`text
                   Spring ApplicationContext
                             |
                   +---------+---------+
                   |                   |
             Exporter A           Exporter B
             server = X           server = Y
             domain = app         domain = internal
                   |                   |
              Server X             Server Y
                   |                   |
              Connector X          Connector Y
\`\`\`

Các quyết định cần rõ:

- Server nào chứa MBean JVM/runtime và server nào chứa MBean ứng dụng?
- Có cần hai connector không, hay chỉ local access?
- Monitoring client dùng connector nào?
- Ai sở hữu vòng đời server riêng?
- Hai exporter có quét cùng bean hay không?
- Có chính sách bảo mật khác nhau trên từng connector không?

Mỗi MBeanServer có registry riêng. Hai server không tự đồng bộ MBean. Nếu đã register một MBean vào server X, thay \`defaultDomain\` trên exporter Y không làm MBean “xuất hiện” trong server Y. Muốn di chuyển phải thay đích đăng ký theo quy trình lifecycle.

### 7.1 Dùng server riêng không đồng nghĩa bảo mật tự động

Tách server có thể hữu ích cho cấu trúc quản trị và phạm vi export, nhưng không tự đảm bảo phân quyền. Quyền của connector, khả năng truy cập local, ranh giới JVM, authentication, TLS và policy cho từng operation vẫn phải được kiểm soát. Một remote connector trỏ nhầm server có thể làm lộ MBean nội bộ hoặc khiến monitoring không nhìn thấy dữ liệu mong muốn.

## 8. Registration policy và xung đột tên

Trong cùng một MBeanServer, \`ObjectName\` cần duy nhất. Nếu exporter cố đăng ký tên đã tồn tại, có thể xuất hiện \`InstanceAlreadyExistsException\` hoặc hành vi theo chính sách đăng ký đã cấu hình.

Ví dụ:

\`\`\`text
Exporter A → platform server
   com.example.app:type=Worker,name=Main

Exporter B → platform server
   com.example.app:type=Worker,name=Main
\`\`\`

Dù exporter B có \`defaultDomain="com.example.other"\`, nếu annotation của bean B vẫn khai báo đúng ObjectName \`com.example.app:type=Worker,name=Main\`, xung đột vẫn xảy ra. Đổi defaultDomain không giải quyết sự cố này.

Những tình huống cần xem xét:

| Tình huống | Cách xử lý |
|---|---|
| Hai context export cùng tên vào cùng server | Phân định ownership, namespace theo context/instance |
| Một bean được quét bởi hai exporter | Thu hẹp phạm vi export hoặc thống nhất một exporter |
| Bean có ObjectName tường minh sai | Sửa metadata và các client phụ thuộc tên |
| Context cũ chưa unregister MBean | Sửa lifecycle cleanup; không xóa MBean không sở hữu |
| Hai server khác nhau có cùng ObjectName | Không xung đột registry, nhưng cần chọn connector đúng |

Chính sách thay thế MBean có thể gây tác động đến thành phần khác; chỉ dùng khi ownership và thời điểm thay thế được thiết kế rõ ràng.

## 9. Chẩn đoán: không thấy MBean trong JConsole

Giả sử ứng dụng log rằng exporter đã đăng ký thành công, nhưng JConsole không thấy \`com.example.application:type=Worker,...\`.

Đi theo thứ tự:

1. **Xác nhận đúng JVM**: JConsole đang kết nối vào tiến trình ứng dụng nào?
2. **Xác nhận đúng MBeanServer**: exporter dùng platform server hay server riêng? Connector có trỏ đúng server đó không?
3. **Kiểm tra ObjectName thực tế**: bean có \`@ManagedResource(objectName=...)\` không? \`defaultDomain\` có được naming strategy dùng không?
4. **Kiểm tra exporter có hoạt động**: context có bật JMX annotation export? Có bean được quét phù hợp?
5. **Kiểm tra lỗi registration**: có collision, malformed ObjectName hoặc exception khi khởi tạo?
6. **Kiểm tra vòng đời**: context/exporter đã bị shutdown hoặc MBean đã được unregister chưa?

Một phép kiểm tra qua API:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

MBeanServer platform = ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> applicationNames = platform.queryNames(
    new ObjectName("com.example.application:*"),
    null
);
applicationNames.forEach(System.out::println);
\`\`\`

Nếu \`applicationNames\` rỗng, điều đó chỉ chứng minh không có ObjectName khớp trong **platform server được truy vấn** ở thời điểm đọc. Có thể exporter đã đăng ký ở server khác hoặc domain khác. Thử query đúng server được exporter dùng và in các ObjectName thực tế, thay vì vội kết luận bean không được export.

### 9.1 MBeanInfo giúp xác định điều gì?

Khi tìm được MBean, \`server.getMBeanInfo(name)\` cho biết attributes, operations, notification metadata. Nó giúp xác minh nội dung interface được export, nhưng không giải thích trực tiếp vì sao \`defaultDomain\` đã chọn một tên nhất định. Để hiểu naming, cần xem annotation/strategy và cấu hình exporter.

## 10. Kiểm tra cấu hình bằng phép thử nhỏ

Một integration test nên khởi tạo Spring context có đúng exporter và bean, rồi đọc registry:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class JmxExporterConfigurationTest {

    @Test
    void mbeanAppearsInSelectedServer() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.inventory:type=Metrics,name=SyncQueue");

        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                     DirectExporterConfiguration.class,
                     InventoryMetrics.class)) {

            assertTrue(server.isRegistered(name));
            assertNotNull(server.getMBeanInfo(name));
        }

        assertFalse(server.isRegistered(name));
    }
}
\`\`\`

Để ví dụ chạy được trong dự án cụ thể, cần bảo đảm exporter trỏ vào platform server, bean có annotation và ObjectName đúng, không có test song song hoặc registration khác dùng cùng tên. Nếu test dùng một cấu hình exporter khác có scanning/registration lifecycle khác, hãy điều chỉnh fixture cho đúng. Không nên cho test xóa MBean theo tên bất kỳ để “dọn môi trường” vì đó có thể là MBean của test khác.

Với \`defaultDomain\`, có thể tạo một bean không chỉ định ObjectName đầy đủ và kiểm tra domain thực tế được naming strategy chọn. Assert theo hợp đồng naming strategy được cấu hình, không giả định một mẫu key properties luôn giống nhau trên mọi phiên bản.

## 11. Vòng đời và ownership

Một exporter được Spring quản lý thường dọn các MBean do nó đăng ký khi exporter bị destroy. Nhưng **MBeanServer dùng chung** có thể sống lâu hơn context:

\`\`\`text
JVM tạo platform MBeanServer
     |
Spring Context A tạo exporter
     |  register com.example.a:...
     |
Spring Context B tạo exporter
     |  register com.example.b:...
     |
Context A đóng
     |  unregister các MBean do A quản lý
     |
Platform server vẫn sống
     |  MBean do B quản lý vẫn tồn tại
\`\`\`

Nếu một bean được đăng ký thủ công ngoài exporter, chính code đăng ký phải quản lý cleanup. Không release platform server chỉ vì một context đóng. Nếu dùng server do factory tạo, cần xác định component sở hữu và quản lý việc release sau khi dọn connector/registration phù hợp.

Đổi \`server\` trong cấu hình vào lúc chạy không nên được xem như thao tác di chuyển MBean tự động. Nếu cần chuyển registry, hãy thiết kế shutdown exporter cũ và đăng ký lại qua exporter mới có kiểm soát. Đổi \`defaultDomain\` cũng có thể thay ObjectName được sinh ở lần đăng ký tiếp theo, khiến alert/script cũ không tìm được MBean; phải xem đây là thay đổi hợp đồng quản trị.

## 12. Lỗi cấu hình thường gặp

### 12.1 Điền URL vào server của @EnableMBeanExport

Sai về ý nghĩa:

\`\`\`java
@EnableMBeanExport(server = "service.example.com:9999")
\`\`\`

Giá trị \`server\` của annotation là tên **Spring bean** tham chiếu đến \`MBeanServer\`, không phải địa chỉ connector. Hãy định nghĩa bean \`MBeanServer\` và dùng đúng tên bean.

### 12.2 Đổi defaultDomain và chờ MBean tự xuất hiện trên server khác

Domain chỉ giải quyết namespace của ObjectName. Nếu client kết nối đến server Y còn exporter đăng ký vào X, thay defaultDomain không giúp nhìn thấy MBean trên Y.

### 12.3 Cho hai exporter quét cùng một tập bean

Nếu hai exporter cùng phát hiện và đăng ký một bean với cùng ObjectName vào cùng server, có thể xung đột. Việc mỗi exporter có tên bean khác nhau trong Spring context không đảm bảo namespace JMX khác nhau.

### 12.4 Mặc định annotation objectName được viết lại

Một ObjectName đầy đủ từ \`@ManagedResource\` là lựa chọn đặt tên cụ thể của bean. \`defaultDomain\` không phải công cụ ghi đè tất cả annotation.

### 12.5 Nhầm default domain của server và exporter

\`server.getDefaultDomain()\` là metadata của MBeanServer. \`exporter.setDefaultDomain(...)\` ảnh hưởng cách exporter/naming strategy tạo tên theo cấu hình. Cả hai có thể có giá trị khác nhau.

### 12.6 Quên kiểm tra Spring Boot JMX auto-configuration

Trong Spring Boot, cấu hình JMX export chịu ảnh hưởng của cài đặt Boot và auto-configuration. Khi thêm \`@EnableMBeanExport\` hoặc exporter thủ công, hãy xác định liệu có cơ chế khác đã kích hoạt cùng chức năng. Các lỗi “duplicate MBean” thường bắt nguồn từ export trùng và lifecycle hơn là bản thân server/defaultDomain.

## 13. Quy tắc thiết kế vận hành

Với mỗi nhóm MBean, nên ghi rõ:

- **Registry**: server nào nhận registration? Ai sở hữu server? Có dùng chung không?
- **Namespace**: domain và key properties nào? ObjectName tường minh hay do naming strategy sinh?
- **Exporter**: exporter nào chịu trách nhiệm đăng ký và unregister? Có bị quét trùng không?
- **Client**: JConsole/monitoring kết nối tới server nào? Tên MBean được dùng trong dashboard có ổn định không?
- **Security**: connector có xác thực, mã hóa và phân quyền thích hợp không?
- **Lifecycle**: sau restart context, MBean có thể được đăng ký lại cùng tên mà không collision không?
- **Change management**: đổi defaultDomain có gây đứt gãy script/alert đang phụ thuộc ObjectName không?

Mẫu tài liệu cấu hình:

\`\`\`text
JMX server: JVM platform MBeanServer
Exporter: AnnotationMBeanExporter của application context chính
Default domain: com.example.inventory
ObjectName đặc biệt:
  com.example.inventory:type=Cache,name=Catalog
  com.example.inventory:type=Queue,name=ImportJobs
Remote connector: được cấu hình riêng tại hạ tầng quản trị
Ownership: Spring context quản lý exporter registrations
\`\`\`

Khi có nhiều môi trường deployment, tránh đưa secret, user ID hoặc payload nhạy cảm vào ObjectName. Domain nên mang nghĩa module hoặc ứng dụng, không phải nơi chứa thông tin runtime thay đổi liên tục.

## 14. Bài tập củng cố

**Bài 1.** Một exporter dùng platform server và \`defaultDomain="com.example.alpha"\`. Bean A có \`@ManagedResource(objectName="com.example.explicit:type=Cache,name=A")\`. Hỏi bean A thuộc domain nào khi đăng ký? **Đáp án:** \`com.example.explicit\`, vì ObjectName đã tường minh.

**Bài 2.** Exporter X dùng server X và exporter Y dùng server Y, nhưng cả hai đăng ký \`com.example:type=Worker,name=Main\`. Có xung đột ở JMX registry không? **Đáp án:** không, vì namespace ObjectName chỉ yêu cầu duy nhất trong từng server. Client phải chọn đúng server.

**Bài 3.** Hai exporter cùng dùng platform server, cùng đăng ký cùng ObjectName. Đổi \`defaultDomain\` của một exporter thành \`com.example.other\` có chắc sửa lỗi? **Đáp án:** không; nếu tên được ghi tường minh, defaultDomain không ảnh hưởng. Cần sửa ownership/namespace hoặc phạm vi export.

**Bài 4.** JConsole kết nối JVM đúng nhưng không thấy MBean. Nêu ba thứ cần kiểm tra trước: **server đích của exporter**, **connector đang kết nối server nào**, và **ObjectName thực tế có xuất hiện trong registry nào**.

**Bài 5.** Hãy viết cấu hình Spring dùng một bean \`MBeanServer\` đặt tên \`applicationServer\`, rồi tham chiếu nó qua \`@EnableMBeanExport(server = "applicationServer", defaultDomain = "com.example.ops")\`. Giải thích vì sao \`"applicationServer"\` là tên bean thay vì host.

## Tổng kết

Trong Spring Framework JMX, \`server\` và \`defaultDomain\` của exporter có hai trách nhiệm độc lập. **server chọn registry JMX nơi các MBean được đăng ký**; **defaultDomain điều chỉnh domain mặc định khi naming strategy cần tạo ObjectName**. Không có cấu hình nào tự thay thế cấu hình còn lại. Với AnnotationMBeanExporter, thiết kế tốt bắt đầu từ việc xác định MBeanServer đích, chọn ObjectName ổn định, phân định exporter sở hữu registration và kiểm tra registry thực tế sau startup/shutdown. Nhờ vậy, hoạt động quản trị dễ quan sát, tránh trùng tên và duy trì hợp đồng với JMX client qua các lần nâng cấp ứng dụng.
