# Đọc attribute như lời gọi phương thức Java qua proxy MBean local trong Spring Framework JMX

## 1. Mục tiêu học tập

Trong JMX thuần Java, muốn lấy giá trị một attribute ta thường dùng \`MBeanServerConnection.getAttribute(ObjectName, String)\`. Spring Framework cho phép tạo **proxy local** cho MBean để code ứng dụng gọi một phương thức Java quen thuộc như \`monitor.getActiveJobs()\`, trong khi phía sau proxy chuyển lời gọi đó thành yêu cầu JMX tới MBeanServer.

Ví dụ khái niệm:

\`\`\`java
int jobs = monitor.getActiveJobs();
\`\`\`

Trông giống lời gọi tới Java object thông thường, nhưng thực chất có thể đi qua:

\`\`\`text
Java caller
    |
    v
MBean proxy: monitor.getActiveJobs()
    |
    v
MBeanServerConnection.getAttribute(objectName, "ActiveJobs")
    |
    v
MBeanServer → MBean đã đăng ký
    |
    v
Giá trị attribute được trả về cho Java caller
\`\`\`

Sau bài học, bạn sẽ:

1. Phân biệt gọi getter trực tiếp trên target object với gọi getter qua JMX proxy.
2. Giải thích vai trò của \`MBeanProxyFactoryBean\` và \`MBeanClientInterceptor\`.
3. Định nghĩa management interface Java tương thích với attribute JMX.
4. Cấu hình local proxy dùng đúng \`MBeanServer\` và \`ObjectName\`.
5. Kiểm tra việc gọi \`getXxx()\` hoặc \`isXxx()\` thực sự đọc attribute \`Xxx\`.
6. Hiểu cách xử lý type, exceptions, lifecycle, timeout và kết nối.
7. Viết integration test xác minh cả metadata lẫn hành vi quan sát qua proxy.

## 2. Local proxy MBean là gì?

Proxy MBean local là một đối tượng Java do Spring tạo ra, có thể được inject vào bean khác dưới một **management interface**. Khi caller gọi method trên proxy, Spring chuyển lời gọi sang JMX API.

Ví dụ:

\`\`\`java
public interface WorkerManagement {
    int getActiveJobs();
    boolean isEnabled();
}
\`\`\`

Một component sử dụng:

\`\`\`java
@Service
public class WorkerDashboardService {
    private final WorkerManagement management;

    public WorkerDashboardService(WorkerManagement management) {
        this.management = management;
    }

    public int currentJobs() {
        return management.getActiveJobs();
    }
}
\`\`\`

Nếu \`management\` là JMX proxy, \`getActiveJobs()\` không nhất thiết chạy trên cùng Java instance với logic nghiệp vụ. Proxy gọi vào MBeanServer bằng ObjectName đã cấu hình.

**“Local”** ở đây chỉ cách kết nối: proxy có thể sử dụng trực tiếp một \`MBeanServer\` cùng JVM. Không cần RMI hoặc endpoint mạng. Spring cũng hỗ trợ client JMX dùng connection từ xa theo cấu hình khác; hành vi Java interface phía caller có thể tương tự nhưng lỗi transport và security khác nhiều.

## 3. Phân biệt ba cách đọc cùng một số liệu

Giả sử MBean chứa attribute \`ActiveJobs\`.

### 3.1. Đọc Java object trực tiếp

\`\`\`java
int count = workerStatus.getActiveJobs();
\`\`\`

Đây là lời gọi trực tiếp nếu \`workerStatus\` thực sự tham chiếu tới target object. Nó không kiểm tra MBean đã đăng ký hoặc attribute được JMX công bố hay chưa.

### 3.2. Đọc bằng MBeanServerConnection

\`\`\`java
Object value = connection.getAttribute(
    new ObjectName("training.spring:type=Worker,name=Primary"),
    "ActiveJobs");
int count = (Integer) value;
\`\`\`

Cách này làm việc ở tầng JMX client và cần biết ObjectName, tên attribute và kiểu trả về.

### 3.3. Đọc qua Spring MBean proxy

\`\`\`java
int count = managementProxy.getActiveJobs();
\`\`\`

Spring proxy dựa trên interface để tạo API Java, nhưng lời gọi vẫn được chuyển tới \`MBeanServerConnection\`. Người dùng proxy không cần tự viết \`getAttribute\` tại mỗi vị trí.

| Tiêu chí | Java object trực tiếp | MBeanServerConnection | Spring MBean proxy |
|---|---|---|---|
| Có cần đăng ký MBean? | Không | Có | Có |
| Caller phải biết ObjectName? | Không | Có | Không, nếu cấu hình proxy đã chứa |
| Có đi qua JMX metadata/dispatch? | Không | Có | Có |
| Có kiểm tra hợp đồng quản trị thực tế? | Không | Có | Có |
| Return type tại caller | Theo method Java | Thường \`Object\` | Theo interface Java |
| Có thể dùng remote connection? | Không theo mặc định | Có | Có nếu client interceptor được cấu hình |
| Lỗi khi MBean biến mất | Không áp dụng | JMX exception | Thường được Spring proxy chuyển tiếp/wrap |

Proxy không có nghĩa việc đọc attribute là miễn phí hoặc chắc chắn thành công. Vẫn có thể xảy ra lỗi lookup, quyền truy cập, mapping kiểu hoặc MBean bị unregister.

## 4. Getter Java biến thành attribute JMX

Trong JMX, method của management interface như:

\`\`\`java
int getActiveJobs();
boolean isEnabled();
String getVersion();
\`\`\`

được hiểu theo quy ước property:

\`\`\`text
getActiveJobs() → attribute ActiveJobs
isEnabled()    → attribute Enabled
getVersion()   → attribute Version
\`\`\`

Những attribute này phải thực sự có trong \`MBeanInfo\` của MBean được đăng ký.

Ví dụ metadata:

\`\`\`text
ObjectName: training.spring:type=Worker,name=Primary

ActiveJobs:
  type=int
  readable=true
  writable=false

Enabled:
  type=boolean
  readable=true
  writable=true

Version:
  type=java.lang.String
  readable=true
  writable=false
\`\`\`

Nếu interface có \`getActiveJobs()\` nhưng MBean chỉ expose \`RunningTasks\`, proxy không thể tự suy ra hai tên đồng nghĩa. Cần đồng bộ naming contract.

### 4.1. Read-only là gì?

Nếu MBean chỉ công khai getter \`getActiveJobs()\`, JMX client có thể đọc nhưng không được dùng \`setAttribute\` cho \`ActiveJobs\`. Proxy chỉ có getter cũng chỉ cho caller thao tác đọc. Tuy nhiên tính read-only thật sự phải được bảo đảm bởi MBean metadata \`isWritable=false\`, không chỉ bằng việc interface của một client thiếu setter.

### 4.2. Boolean getter

\`boolean isEnabled()\` thường ánh xạ tới \`Enabled\`. Cũng có thể dùng \`boolean getEnabled()\`. Nếu chọn \`isXxx()\`, nên dùng primitive \`boolean\` và giữ nhất quán quy ước JavaBeans. Khi mismatch, xem \`MBeanAttributeInfo\` để biết tên/type thực tế.

## 5. Ví dụ hoàn chỉnh: Standard MBean và Spring local proxy

Ta xây dựng MBean với hai thuộc tính và một interface tương ứng.

### 5.1. Interface quản trị

File \`WorkerStatusMBean.java\`:

\`\`\`java
package example.jmx;

public interface WorkerStatusMBean {
    int getActiveJobs();
    boolean isEnabled();
}
\`\`\`

### 5.2. Implementation

File \`WorkerStatus.java\`:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class WorkerStatus implements WorkerStatusMBean {
    private final AtomicInteger activeJobs = new AtomicInteger();
    private volatile boolean enabled = true;

    @Override
    public int getActiveJobs() {
        return activeJobs.get();
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    public void jobStarted() {
        if (enabled) {
            activeJobs.incrementAndGet();
        }
    }

    public void jobFinished() {
        activeJobs.updateAndGet(previous ->
            Math.max(0, previous - 1));
    }
}
\`\`\`

Đây là Standard MBean: tên class \`WorkerStatus\` và interface \`WorkerStatusMBean\` tuân theo quy tắc đặt tên JMX. Interface chỉ có getter nên cả hai attribute ở trạng thái read-only qua JMX.

### 5.3. Spring configuration tạo server, MBean và proxy

File \`JmxConfig.java\`:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

import java.util.Map;

@Configuration
public class JmxConfig {

    @Bean
    public MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public WorkerStatus workerStatus() {
        return new WorkerStatus();
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer mbeanServer,
            WorkerStatus workerStatus) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setBeans(Map.of(
            "example.jmx:type=WorkerStatus,name=Primary",
            workerStatus));
        return exporter;
    }

    @Bean
    public MBeanProxyFactoryBean workerStatusProxy(
            MBeanServer mbeanServer) throws Exception {

        MBeanProxyFactoryBean factory =
            new MBeanProxyFactoryBean();

        factory.setServer(mbeanServer);
        factory.setObjectName(new ObjectName(
            "example.jmx:type=WorkerStatus,name=Primary"));
        factory.setProxyInterface(WorkerStatusMBean.class);
        return factory;
    }
}
\`\`\`

Spring \`MBeanProxyFactoryBean\` tạo một Java proxy dựa vào management interface và ObjectName. Thường client bean được inject bằng **type của sản phẩm FactoryBean**, nghĩa là \`WorkerStatusMBean\`, không phải chính instance \`MBeanProxyFactoryBean\`.

Nếu trong context đã có bean \`workerStatus()\` cũng implement \`WorkerStatusMBean\`, inject \`WorkerStatusMBean\` theo type có thể trở nên ambiguous vì có cả target và proxy. Dùng \`@Qualifier("workerStatusProxy")\` hoặc tên bean rõ ràng để chắc chắn nhận proxy.

### 5.4. Chương trình sử dụng

\`\`\`java
package example.jmx;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    JmxConfig.class)) {

            WorkerStatus target =
                context.getBean(WorkerStatus.class);

            WorkerStatusMBean proxy =
                context.getBean(
                    "workerStatusProxy",
                    WorkerStatusMBean.class);

            System.out.println(
                "Before: " + proxy.getActiveJobs()); // 0

            target.jobStarted();
            target.jobStarted();

            System.out.println(
                "After: " + proxy.getActiveJobs()); // 2
            System.out.println(
                "Enabled: " + proxy.isEnabled());  // true
        }
    }
}
\`\`\`

Trong ví dụ, \`proxy.getActiveJobs()\` là API Java nhưng giá trị đi qua MBeanServer. \`target.jobStarted()\` là logic nội bộ được dùng để thay đổi state; client quản trị chỉ cần getter.

**Giới hạn về vòng đời:** proxy cần MBean đã được đăng ký trước khi gọi. Nếu server chưa có ObjectName, getter proxy thất bại dù Java interface và proxy bean đã được tạo thành công.

## 6. Vì sao không nên coi proxy là target object?

Hai object có vai trò khác nhau:

\`\`\`text
WorkerStatus target:
    implements business/management methods

WorkerStatusMBean proxy:
    implements interface for JMX client,
    forwards calls through MBeanServer
\`\`\`

Nếu caller nhận target trực tiếp, \`getActiveJobs()\` chạy ngay trong Java object và có thể vẫn thành công dù exporter không hoạt động. Nếu nhận proxy, lời gọi phụ thuộc vào MBean registration. Điều này hữu ích khi bạn muốn kiểm thử contract JMX hoặc tách consumer khỏi implementation.

Một sai sót thường gặp trong Spring là inject cùng type \`WorkerStatusMBean\` mà không có qualifier và vô tình nhận target. Khi đó test “proxy hoạt động” là kết luận sai.

### 6.1. Cách xác nhận đang dùng proxy

Trong môi trường test:

\`\`\`java
System.out.println(proxy.getClass().getName());
System.out.println(target.getClass().getName());
System.out.println(proxy == target); // false
\`\`\`

Tên class proxy là implementation detail, không nên hard-code. Có thể dùng assert rằng instance proxy khác target và đọc JMX metadata để chứng minh dữ liệu đến từ server.

## 7. MBeanProxyFactoryBean và MBeanClientInterceptor

Trong Spring JMX:

- \`MBeanProxyFactoryBean\` cung cấp một client proxy bean có management interface.
- \`MBeanClientInterceptor\` xử lý các invocation từ proxy và giao tiếp với \`MBeanServerConnection\`.
- \`MBeanExporter\` chịu trách nhiệm đăng ký server-side MBean.
- \`MBeanServer\` nhận và dispatch các yêu cầu đọc attribute hoặc gọi operation.

\`\`\`text
Spring caller
    |
    v
MBeanProxyFactoryBean-created proxy
    |
    v
MBeanClientInterceptor
    |
    v
MBeanServerConnection
    |
    v
MBeanServer
    |
    v
Managed MBean
\`\`\`

Không cấu hình \`MBeanExporter\` thay cho \`MBeanProxyFactoryBean\`: exporter và proxy phục vụ hai phía của kết nối JMX. Exporter là server-side; proxy là client-side.

### 7.1. Local vs remote

Khi \`setServer(mbeanServer)\` cung cấp một \`MBeanServerConnection\` cùng JVM, proxy đọc trực tiếp qua JMX server local. Nếu không inject server và dùng \`JMXServiceURL\` cùng \`JMXConnector\` theo cách Spring hỗ trợ, có thể truy cập remote MBeanServer.

Remote path bổ sung xác thực, mạng, TLS, RMI và thời gian chờ; không nên mặc định có cùng tính khả dụng với lời gọi local.

## 8. Kết quả trả về và mapping kiểu

Java caller kỳ vọng kiểu khai báo trên management interface:

\`\`\`java
int getActiveJobs();
boolean isEnabled();
\`\`\`

Nhưng JMX API cơ sở trả \`Object\`. Spring proxy thực hiện cơ chế chuyển kết quả về kiểu method tương ứng. Vì thế metadata và kiểu trả về phải tương thích.

Các tình huống cần cẩn trọng:

- MBean trả \`Integer\` cho attribute \`int\` — boxing/unboxing bình thường.
- MBean trả \`null\` cho getter primitive \`int\` — không thể unbox thành \`int\`.
- MBean công bố \`String\` nhưng interface khai \`int\` — type mismatch.
- MXBean trả \`CompositeData\` cho một kiểu phức tạp — cần proxy/interface và mapping Open Types phù hợp.
- Attribute bị đổi tên sau nâng cấp exporter — getter proxy không còn tìm thấy tên mong đợi.

Không nhầm Spring proxy JMX với một client REST có khả năng tự chuyển đổi mọi kiểu dữ liệu. Hợp đồng JMX cần được giữ rõ ràng và kiểm thử.

## 9. Kiểm tra metadata trước khi gọi proxy

Trước khi kỳ vọng \`getActiveJobs()\` hoạt động, hãy kiểm tra MBean:

\`\`\`java
import javax.management.*;
import java.util.Arrays;

ObjectName objectName = new ObjectName(
    "example.jmx:type=WorkerStatus,name=Primary");

MBeanInfo info = server.getMBeanInfo(objectName);

MBeanAttributeInfo attribute =
    Arrays.stream(info.getAttributes())
        .filter(a -> a.getName().equals("ActiveJobs"))
        .findFirst()
        .orElseThrow();

System.out.println(attribute.getType());       // int
System.out.println(attribute.isReadable());    // true
System.out.println(attribute.isWritable());    // false
\`\`\`

Nếu \`ActiveJobs\` không có trong \`MBeanInfo\`, lỗi có thể nằm ở Standard MBean interface, annotation assembler, ObjectName hoặc exporter configuration chứ không phải ở Java getter caller.

## 10. Đọc attribute với \`isEnabled()\`

Một management interface có thể khai báo:

\`\`\`java
public interface FeatureManagement {
    boolean isEnabled();
}
\`\`\`

Khi MBean tương ứng được export đúng contract, Spring proxy đọc attribute \`Enabled\`.

Cần xác minh tên và \`isIs()\`/boolean semantics trong metadata, đặc biệt khi dùng MXBean hoặc annotation-exported bean với metadata assembler tùy chỉnh. Tránh đặt đồng thời \`getEnabled()\` và \`isEnabled()\` không nhất quán trên cùng interface.

Một client có thể viết:

\`\`\`java
boolean active = featureManagement.isEnabled();
\`\`\`

Không cần tự xây dựng \`new ObjectName(...)\` trong mỗi business caller, vì proxy đã được cấu hình tập trung.

## 11. Đọc attribute từ một Spring-exported bean thay vì Standard MBean

Proxy cũng có thể làm việc với một MBean do \`@ManagedResource\` và \`@ManagedAttribute\` export, miễn là interface của client khớp **JMX interface được công bố thực tế**.

Bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "example.jmx:type=QueueView,name=Orders")
public class QueueView {
    private volatile int pendingCount;

    @ManagedAttribute
    public int getPendingCount() {
        return pendingCount;
    }
}
\`\`\`

Client interface:

\`\`\`java
public interface QueueViewManagement {
    int getPendingCount();
}
\`\`\`

Proxy configuration:

\`\`\`java
@Bean
public MBeanProxyFactoryBean queueViewProxy(MBeanServer server)
        throws Exception {
    MBeanProxyFactoryBean factory =
        new MBeanProxyFactoryBean();
    factory.setServer(server);
    factory.setObjectName(new ObjectName(
        "example.jmx:type=QueueView,name=Orders"));
    factory.setProxyInterface(QueueViewManagement.class);
    return factory;
}
\`\`\`

Chú ý: \`QueueView\` cần thực sự được MBeanExporter hoặc annotation export infrastructure đăng ký. Việc có \`@ManagedResource\` trên class chưa đủ. Nếu Spring application đã dùng \`@EnableMBeanExport\`, hãy kiểm tra exporter do framework tạo và tránh thêm exporter khác đăng ký cùng ObjectName.

## 12. Lỗi thường gặp khi getter proxy thất bại

### 12.1. \`InstanceNotFoundException\` / MBean chưa đăng ký

Nếu MBean đã bị unregister hoặc proxy chỉ tới sai ObjectName, lời gọi không thể tới target.

Cách xử lý:

1. Kiểm tra \`server.isRegistered(name)\`.
2. Query tên theo domain.
3. Xác minh exporter đã chạy.
4. Xem ApplicationContext hoặc plugin lifecycle.
5. Kiểm tra xem proxy và exporter có dùng cùng MBeanServer hay không.

### 12.2. \`AttributeNotFoundException\`

Proxy tìm \`ActiveJobs\`, nhưng MBean không expose attribute ấy hoặc tên khác.

Cách xử lý: xem \`getMBeanInfo(name).getAttributes()\`, kiểm tra naming của getter trong interface và metadata assembler.

### 12.3. Type mismatch

Getter interface khai \`int\`, nhưng JMX attribute thực tế có kiểu \`String\` hoặc \`CompositeData\`. Hãy giữ kiểu contract thống nhất hoặc sử dụng interface được thiết kế đúng cho MXBean/Open Type.

### 12.4. Proxy bị inject sai

Nếu context có cả target \`WorkerStatus\` và \`MBeanProxyFactoryBean\` product cùng implement \`WorkerStatusMBean\`, inject theo type có thể chọn nhầm hoặc gây ambiguity. Dùng qualifier hoặc bean name rõ ràng.

### 12.5. Sai MBeanServer

MBeanExporter dùng server mới tạo riêng nhưng MBean proxy được inject platform server. Client thấy MBean không tồn tại.

Cách xử lý: cấu hình cả exporter và proxy nhận **cùng MBeanServer reference**.

### 12.6. Lỗi quyền hoặc remote transport

Với JMX remote, getter cũng có thể thất bại vì authentication, authorization, TLS, mạng hoặc connector bị mất. Đừng coi method signature Java giống nhau là bảo đảm cùng exception semantics. Kiểm tra error chain và xác định lỗi xảy ra trước hay sau khi gửi request.

## 13. Kiểm thử proxy như một JMX client

Unit test gọi trực tiếp \`target.getActiveJobs()\` không xác nhận proxy routing. Test phải khởi động Spring context, lấy bean proxy bằng đúng tên và đọc qua JMX.

Ví dụ JUnit 5:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class LocalProxyTest {
    @Test
    void proxyReadsAttributeViaMBeanServer() throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    JmxConfig.class)) {

            MBeanServer server =
                context.getBean(MBeanServer.class);

            ObjectName name = new ObjectName(
                "example.jmx:type=WorkerStatus,name=Primary");

            assertTrue(server.isRegistered(name));

            WorkerStatus target =
                context.getBean(WorkerStatus.class);

            WorkerStatusMBean proxy =
                context.getBean(
                    "workerStatusProxy",
                    WorkerStatusMBean.class);

            assertNotSame(target, proxy);

            assertEquals(0, proxy.getActiveJobs());

            target.jobStarted();
            assertEquals(1, proxy.getActiveJobs());

            assertEquals(
                server.getAttribute(name, "ActiveJobs"),
                proxy.getActiveJobs());
        }
    }
}
\`\`\`

Test này chứng minh giá trị từ proxy khớp giá trị ở MBeanServer. Nếu cần xác minh mạnh hơn rằng proxy thực sự dùng JMX, có thể tạm unregister MBean trong test fixture cô lập và xác nhận getter proxy thất bại, sau đó cleanup. Không thực hiện unregister phá hoại trên shared production MBeanServer.

### 13.1. Kiểm thử read-only

Client interface không có setter không đủ kết luận MBean read-only. Kiểm tra:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);
MBeanAttributeInfo active =
    java.util.Arrays.stream(info.getAttributes())
        .filter(a -> a.getName().equals("ActiveJobs"))
        .findFirst()
        .orElseThrow();

assertTrue(active.isReadable());
assertFalse(active.isWritable());
\`\`\`

Nếu một exporter thay đổi metadata để cho phép ghi, một client khác vẫn có thể gọi \`setAttribute\` dù proxy hiện tại chỉ có getter. Vì vậy phải kiểm tra contract server-side.

## 14. Proxy và nhiều ApplicationContext

Trong ứng dụng nhiều context, exporter và client proxy có thể ở các nơi khác nhau:

\`\`\`text
Root context:
  MBeanServer
  MBeanExporter
  WorkerStatus MBean

Child context:
  MBeanProxyFactoryBean
  DashboardController
\`\`\`

Child có thể inject server bean từ parent nếu context hierarchy cho phép. Cần đảm bảo child proxy tham chiếu đúng ObjectName được root exporter đăng ký.

Ngược lại, nếu exporter nằm trong child context và proxy nằm ở root, root không tự lookup bean con. Khi đó cần wiring tường minh hoặc tái cấu trúc ownership.

Nếu plugin context bị đóng và MBean bị unregister, một proxy còn sống trong context khác không tự động tạo lại MBean. Lời gọi sau đó có thể thất bại. Consumer nên xử lý lifecycle và discovery phù hợp.

## 15. Quan hệ với Spring AOP proxy

JMX proxy local là **client proxy** hướng đến MBeanServer; còn Spring AOP proxy thường là proxy quanh business bean để áp dụng transaction, caching, security hoặc tracing. Hai lớp có thể cùng tồn tại nhưng có vai trò khác nhau.

\`\`\`text
Client bean
    |
    v
JMX client proxy
    |
    v
MBeanServer
    |
    v
Exported MBean adapter
    |
    v
Spring business bean (có thể là AOP proxy)
    |
    v
Target logic
\`\`\`

Không nhầm \`MBeanProxyFactoryBean\` với cấu hình \`@Transactional\`. JMX client proxy không tự bảo đảm transaction của target; transaction phụ thuộc bean và lời gọi có đi qua AOP advice đúng cách hay không.

Nếu sau khi bật AOP getter proxy không hoạt động, hãy kiểm tra cả hai phía:

1. Client proxy có đúng interface/ObjectName/server?
2. MBean exporter có còn expose attribute không?
3. AOP proxy có làm thay đổi method visibility/metadata không?
4. MBeanInfo thực tế có còn attribute đó không?

## 16. Khi nào dùng local proxy?

**Nên cân nhắc** khi:

- Một thành phần muốn đọc các MBean attributes qua interface Java có type rõ ràng.
- Bạn cần consumer tách khỏi implementation hoặc thậm chí không có class target trên classpath.
- Cùng một client contract có thể dùng local hôm nay và remote theo cấu hình ngày sau.
- Bạn muốn kiểm thử đường đi quản trị thực, không chỉ gọi Java object.

**Không nhất thiết cần** khi:

- Cùng service đã có Java API trực tiếp phù hợp, không cần JMX boundary.
- Bạn chỉ cần đọc số liệu thường xuyên và có thể lấy trực tiếp từ metrics API.
- Chi phí dispatch, lỗi JMX và complexity configuration không đem lại lợi ích.
- Proxy được dùng như cách lách quyền truy cập hoặc business service boundaries.

Với monitoring có throughput cao, công cụ metrics chuyên dụng có thể phù hợp hơn việc gọi JMX attribute trong mỗi request nghiệp vụ.

## 17. Bài tập thực hành

### Bài tập A — Đọc attribute qua hai đường

Chạy ví dụ \`WorkerStatus\`. Đọc \`ActiveJobs\` qua \`server.getAttribute\` và \`proxy.getActiveJobs()\`. Chứng minh kết quả bằng nhau và giải thích hai API khác nhau như thế nào.

### Bài tập B — Đổi ObjectName sai

Đổi proxy ObjectName sang \`example.jmx:type=WorkerStatus,name=Missing\`, giữ exporter như cũ. Gọi getter và quan sát lỗi. Trả ObjectName đúng rồi kiểm tra lại.

### Bài tập C — Đổi getter name

Đổi \`getActiveJobs()\` trong client interface thành \`getRunningJobs()\` nhưng không thay đổi MBean. Quan sát lỗi và xác định attribute thực tế qua \`MBeanInfo\`.

### Bài tập D — Read-only metadata

Dùng \`MBeanAttributeInfo\` để khẳng định \`ActiveJobs\` chỉ đọc. Thử set attribute từ MBeanServer trong test cô lập và ghi nhận lỗi thích hợp.

### Bài tập E — Hai ApplicationContext

Đưa exporter/server vào root context và proxy vào child context. Xác minh proxy gọi được getter. Sau khi đóng root, xác nhận lời gọi từ child proxy thất bại hoặc xử lý lifecycle theo contract.

### Bài tập F — Annotation-based MBean

Thay Standard MBean bằng \`@ManagedResource\` và \`@ManagedAttribute\` với ObjectName tương đương. Cấu hình annotation export và kiểm tra client proxy vẫn đọc được khi \`MBeanInfo\` công bố đúng \`ActiveJobs\`.

## 18. Câu hỏi tự kiểm tra

1. \`MBeanProxyFactoryBean\` khác \`MBeanExporter\` ở trách nhiệm nào?
2. \`getActiveJobs()\` trên client proxy ánh xạ tới JMX API nào?
3. Vì sao direct Java getter thành công chưa chứng minh MBean proxy hoạt động?
4. Tên attribute từ \`isEnabled()\` thường là gì?
5. Vì sao proxy và exporter phải dùng cùng MBeanServer?
6. \`MBeanInfo\` giúp xác minh điều gì trước khi gọi proxy?
7. Nếu MBean bị unregister, proxy còn hoạt động bình thường không?
8. Tại sao inject \`WorkerStatusMBean\` theo type có thể bị ambiguity?
9. JMX proxy local khác AOP transaction proxy như thế nào?
10. Vì sao return type và metadata JMX phải tương thích?

## 19. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — \`MBeanProxyFactoryBean\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanProxyFactoryBean.html
- Spring Framework API — \`MBeanClientInterceptor\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanClientInterceptor.html
- Java SE 21 — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — \`MBeanAttributeInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html

**Ghi nhớ:** Spring local MBean proxy biến một lời gọi getter như \`getActiveJobs()\` thành thao tác đọc attribute JMX. Interface của proxy phải khớp metadata MBean, còn proxy và exporter phải hướng đến cùng MBeanServer và ObjectName. Proxy giúp code client dễ dùng hơn nhưng không loại bỏ yêu cầu quản lý registration, lỗi JMX và tính tương thích của hợp đồng quản trị.
