# Chọn proxy khi muốn tách client khỏi implementation

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** Proxy MBean local  
> **Bài học:** Chọn proxy khi muốn tách client khỏi implementation

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao client quản trị không nên phụ thuộc trực tiếp vào implementation của Spring bean.
- Phân biệt **gọi trực tiếp service** với **gọi MBean qua JMX proxy** trong cùng JVM.
- Hiểu vai trò của \`MBeanServerConnection\`, \`ObjectName\`, management interface và \`MBeanProxyFactoryBean\`.
- Dùng \`JMX.newMBeanProxy\` hoặc Spring \`MBeanProxyFactoryBean\` để gọi operation và đọc attribute.
- Biết cách chọn proxy khi cần một ranh giới quản trị ổn định, đồng thời nhận diện trường hợp injection service trực tiếp phù hợp hơn.
- Xử lý lỗi MBean chưa đăng ký, sai ObjectName, hợp đồng interface không khớp và thay đổi lifecycle.

## 2. Vấn đề thiết kế: client phụ thuộc vào điều gì?

Một ứng dụng có service triển khai:

\`\`\`java
public class CacheService {
    public long currentEntries() { ... }
    public void refresh() { ... }
}
\`\`\`

Nếu công cụ quản trị hoặc một module khác injection trực tiếp \`CacheService\`, module đó phải biết class implementation, các dependency và lifecycle của nó.

\`\`\`text
Admin client
    |
    | trực tiếp gọi Java method
    v
CacheService implementation
\`\`\`

Khi thay class, tách module hoặc chuyển cách expose dữ liệu, client có thể cần biên dịch lại. Nếu mục tiêu là **giao tiếp quản trị qua hợp đồng JMX**, cách phụ thuộc trực tiếp này làm mất lợi ích của lớp management boundary.

Một JMX proxy tạo thêm một tầng:

\`\`\`text
Admin client
    |
    | gọi CacheManagement interface
    v
JMX proxy
    |
    | ObjectName + MBeanServerConnection
    v
MBeanServer
    |
    v
Cache MBean / Spring-managed implementation
\`\`\`

Client chỉ biết giao diện quản trị, \`ObjectName\` và connection. Class nghiệp vụ phía server có thể thay đổi miễn hợp đồng quản trị vẫn tương thích.

**Điểm quan trọng:** tách khỏi implementation không có nghĩa loại bỏ mọi coupling. Client vẫn phụ thuộc vào tên MBean, attribute/operation signature, kiểu dữ liệu và khả năng truy cập MBeanServer.

## 3. Khái niệm proxy MBean local

Một **MBean local proxy** là object Java ở cùng JVM với MBeanServer, cho phép caller sử dụng method Java trong khi framework chuyển lời gọi thành JMX operation hoặc attribute access.

\`\`\`text
Cùng JVM
+--------------------------------------------------+
| Spring admin component                           |
|    |                                             |
|    v                                             |
| CacheManagement proxy                            |
|    |                                             |
|    +--> MBeanServerConnection                    |
|              |                                   |
|              v                                   |
|          MBeanServer                             |
|              |                                   |
|              v                                   |
|     MBean registered by exporter                 |
|              |                                   |
|              v                                   |
|        CacheService/facade                       |
+--------------------------------------------------+
\`\`\`

Vì local proxy không cần network connector, nó có thể được dùng trong cùng process, nhưng vẫn áp dụng quy tắc JMX: ObjectName phải tồn tại, method phải được công bố và chữ ký phải phù hợp.

\`MBeanServer\` triển khai \`MBeanServerConnection\`, nên cùng một kiểu connection có thể làm việc với local server hoặc remote connector. Việc dùng proxy hôm nay không tự bảo đảm sau này chuyển remote mà không sửa gì: cần xem kiểu dữ liệu, exception, bảo mật và độ trễ.

## 4. So sánh injection trực tiếp với proxy

| Tiêu chí | Gọi Spring bean trực tiếp | Gọi qua JMX proxy |
|---|---|---|
| Phụ thuộc vào implementation | Thường biết class/service hoặc business interface | Biết management interface và ObjectName |
| Đường gọi | Java method call | JMX invocation qua server |
| Cần MBean đăng ký | Không | Có |
| Metadata JMX | Không liên quan | Attribute/operation phải được công bố |
| Kiểu dữ liệu | Có thể dùng mọi kiểu Java nội bộ | Nên chọn kiểu JMX/client-compatible |
| Exception | Theo API business | Có thể có lỗi lookup, invoke và connector |
| Lifecycle | Theo Spring bean | Theo cả Spring bean/exporter/MBean registration |
| Khi dùng | Logic nghiệp vụ nội bộ có coupling được chấp nhận | Thành phần quản trị cần ranh giới ổn định |
| Remote-capable | Không mặc định | Có thể đổi connection nếu interface/transport phù hợp |

Proxy không phải “mặc định tốt hơn” cho mọi lời gọi. Nếu một Spring component cần thực hiện nghiệp vụ bình thường trên cùng service, injection interface trực tiếp thường đơn giản và hiệu quả. JMX proxy phù hợp khi client thực sự muốn tuân thủ **management API** của MBean.

## 5. Hợp đồng interface là trung tâm

Để có một proxy ổn định, trước hết thiết kế management interface nhỏ:

\`\`\`java
package example.management;

public interface CacheManagement {
    long getEntryCount();
    void refresh();
}
\`\`\`

Các phương thức này đại diện những gì caller được phép quan sát hoặc điều khiển.

Với Standard MBean, convention interface thường là tên class cộng hậu tố \`MBean\`:

\`\`\`java
public interface CacheMonitorMBean {
    long getEntryCount();
    void refresh();
}
\`\`\`

Với Spring JMX annotation, bean có thể được export thông qua \`@ManagedResource\`, \`@ManagedAttribute\` và \`@ManagedOperation\`. Khi đó proxy interface phía client không nhất thiết phải trùng implementation class, nhưng **tên và chữ ký các method** phải ánh xạ được đến metadata MBean đã đăng ký.

Quan trọng hơn tên interface là hợp đồng JMX thực tế: \`getEntryCount()\` tương ứng attribute \`EntryCount\`, còn \`refresh()\` tương ứng operation \`refresh\`.

## 6. Ví dụ Standard MBean thuần với JMX.newMBeanProxy

### 6.1. Management interface

\`\`\`java
package example.jmx;

public interface CacheMonitorMBean {
    long getEntryCount();
    void refresh();
}
\`\`\`

### 6.2. Implementation

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;

public class CacheMonitor implements CacheMonitorMBean {

    private final AtomicLong entries = new AtomicLong(12);

    @Override
    public long getEntryCount() {
        return entries.get();
    }

    @Override
    public void refresh() {
        entries.incrementAndGet();
    }
}
\`\`\`

\`CacheMonitor\` là implementation, còn \`CacheMonitorMBean\` là contract.

### 6.3. Đăng ký và sử dụng proxy

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.JMX;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class LocalProxyDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "learning.jmx:type=Cache,name=primary"
        );

        server.registerMBean(new CacheMonitor(), name);

        try {
            CacheMonitorMBean proxy = JMX.newMBeanProxy(
                server,
                name,
                CacheMonitorMBean.class,
                false
            );

            System.out.println(proxy.getEntryCount());
            proxy.refresh();
            System.out.println(proxy.getEntryCount());
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Kết quả minh họa:

\`\`\`text
12
13
\`\`\`

Ở đây caller không giữ tham chiếu tới \`CacheMonitor\` đã đăng ký. Nó chỉ giữ proxy, dùng interface và ObjectName để gọi qua MBeanServer.

\`JMX.newMBeanProxy\` là JMX API chuẩn, không phải riêng Spring. Local server được truyền trực tiếp vì \`MBeanServer\` cũng là \`MBeanServerConnection\`.

### Vì sao tên ObjectName có thể khác tên class?

Ví dụ dùng \`type=Cache\` thay vì \`type=CacheMonitor\` hoặc class Java đầy đủ. Điều này chủ đích tách định danh quản trị khỏi tên implementation. Đổi \`CacheMonitor\` thành \`CacheTelemetryAdapter\` không nhất thiết đòi client đổi ObjectName nếu contract vẫn được giữ.

## 7. Spring MBeanProxyFactoryBean

Spring cung cấp \`org.springframework.jmx.access.MBeanProxyFactoryBean\`, một \`FactoryBean\` tạo proxy đến MBean được xác định bởi ObjectName.

Một cấu hình Java:

\`\`\`java
package example.jmx;

import javax.management.MBeanServerConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class ManagementClientConfig {

    @Bean
    public MBeanProxyFactoryBean cacheManagementProxy(
            MBeanServerConnection managementConnection
    ) throws Exception {
        MBeanProxyFactoryBean factory =
            new MBeanProxyFactoryBean();

        factory.setServer(managementConnection);
        factory.setObjectName(
            "learning.jmx:type=Cache,name=primary"
        );
        factory.setProxyInterface(CacheManagement.class);

        return factory;
    }
}
\`\`\`

Client injection:

\`\`\`java
import org.springframework.stereotype.Component;

@Component
public class CacheAdminPanel {

    private final CacheManagement cacheManagement;

    public CacheAdminPanel(CacheManagement cacheManagement) {
        this.cacheManagement = cacheManagement;
    }

    public void displayAndRefresh() {
        System.out.println(cacheManagement.getEntryCount());
        cacheManagement.refresh();
    }
}
\`\`\`

Trong ví dụ, \`CacheManagement\` là management interface được client biết tới. Để sử dụng thành công, MBean tại \`learning.jmx:type=Cache,name=primary\` phải thực sự công bố \`EntryCount\` và \`refresh()\`.

Lưu ý về Spring bean \`MBeanServerConnection\`: cấu hình phải đăng ký một bean connection phù hợp, ví dụ platform MBeanServer hoặc server tùy biến. Không giả định mọi Spring context đều có sẵn một \`MBeanServerConnection\` bean tự động.

### Cấu hình local connection

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServerConnection;

@Bean
public MBeanServerConnection managementConnection() {
    return ManagementFactory.getPlatformMBeanServer();
}
\`\`\`

Để tránh mơ hồ, có thể tạo \`MBeanServer\` bean và dùng cùng object cho exporter lẫn proxy. Nếu exporter dùng server khác platform server, proxy trỏ platform server có thể không tìm thấy MBean.

## 8. Spring export bằng annotation và client proxy

Một Spring bean có thể được xuất bản qua annotation:

\`\`\`java
package example.management;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=Cache,name=primary",
    description = "Primary cache management"
)
public class CacheManagementFacade {

    private final AtomicLong entries = new AtomicLong(12);

    @ManagedAttribute(description = "Cached entry count")
    public long getEntryCount() {
        return entries.get();
    }

    @ManagedOperation(description = "Refresh cache")
    public void refresh() {
        entries.incrementAndGet();
    }
}
\`\`\`

Kích hoạt annotation exporter:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxExportConfig {
}
\`\`\`

Khi context hoàn tất khởi tạo và exporter đăng ký thành công, client có thể dùng \`MBeanProxyFactoryBean\` để gọi các phương thức tương ứng.

\`\`\`text
CacheAdminPanel
      |
      v
CacheManagement (proxy interface)
      |
      v
MBeanProxyFactoryBean proxy
      |
      v
MBeanServerConnection
      |
      v
ObjectName: learning.jmx:type=Cache,name=primary
      |
      v
CacheManagementFacade @ManagedResource
\`\`\`

Client không cần import \`CacheManagementFacade\` từ module server. Đây là lợi ích tách lớp rõ ràng khi muốn quản trị thông qua một API hẹp.

## 9. Proxy chuyển lời gọi thành thao tác JMX thế nào?

Đối với Standard MBean proxy, quy tắc cơ bản:

| Method Java phía client | Ý nghĩa JMX |
|---|---|
| \`getEntryCount()\` | Đọc attribute \`EntryCount\` |
| \`isEnabled()\` | Đọc attribute Boolean \`Enabled\` |
| \`setEnabled(boolean)\` | Ghi attribute \`Enabled\` |
| \`refresh()\` | Invoke operation \`refresh\` |
| \`resize(int)\` | Invoke \`resize\` với signature \`int\` |

Đường gọi operation:

\`\`\`text
proxy.resize(8)
    |
    v
MBeanServerConnection.invoke(
    name,
    "resize",
    new Object[] {8},
    new String[] {"int"}
)
    |
    v
MBean đã đăng ký
\`\`\`

Thực tế proxy handler làm phần chuyển đổi. Client chỉ gọi method Java, nhưng vẫn có exception nếu metadata JMX không tương thích.

Nếu một method phía client đổi từ \`resize(int)\` sang \`resize(long)\`, dù tên vẫn giống, signature JMX đã đổi. Không dựa vào tự động boxing/widening như Java compiler để giả định mọi overload sẽ tương thích.

## 10. Chọn proxy vì tách implementation, không phải vì muốn tránh mọi phụ thuộc

Proxy hữu ích khi client chỉ cần hợp đồng:

\`\`\`java
public interface WorkerControl {
    int getActiveCount();
    void pause();
}
\`\`\`

Implementation có thể là:

\`\`\`text
ThreadPoolWorker
ExecutorServiceAdapter
RemoteWorkerManager
\`\`\`

Nếu cùng export attribute và operation dưới ObjectName ổn định, client không cần biết implementation nào đang thực thi.

Tuy nhiên proxy vẫn phụ thuộc vào:

- ObjectName được chọn.
- MBeanServerConnection có đúng registry hay không.
- Danh sách attribute/operation và chữ ký.
- Kiểu dữ liệu client hiểu được.
- Lifecycle MBean và trạng thái kết nối.
- Quyền truy cập phù hợp.

Vì thế management interface cần được quản lý giống một API. Đừng gắn trực tiếp toàn bộ service interface với nhiều method nội bộ vào proxy rồi hy vọng các method đó tự xuất hiện trong JMX.

## 11. Khi nào nên dùng MBean proxy local?

Một số tình huống phù hợp:

### 11.1. Module quản trị độc lập với module nghiệp vụ

Một module admin trong cùng JVM cần đọc trạng thái và gọi một số operation quản trị, nhưng không muốn phụ thuộc package và class triển khai của service. Proxy qua management interface giúp giữ ranh giới module.

### 11.2. Công cụ vận hành dùng chung đường truy cập JMX

Ứng dụng có cả JConsole, monitoring agent và một admin component local. Nếu tất cả dùng cùng management contract, local proxy giúp admin component không phải xây một đường API riêng trực tiếp tới service.

### 11.3. Có thể chuyển client sang kết nối từ xa

Nếu interface dùng kiểu phù hợp với JMX transport, có thể thay local \`MBeanServerConnection\` bằng connection từ \`JMXConnector\`. Nhưng việc chuyển remote đòi hỏi thêm xử lý network, authentication, latency, serialization và reconnect.

### 11.4. Client cần mock management contract

Một interface hẹp có thể được mock trong unit test của admin module:

\`\`\`java
CacheManagement management = mock(CacheManagement.class);
when(management.getEntryCount()).thenReturn(42L);
\`\`\`

Ví dụ dùng một framework mocking như Mockito trong test. Đây là lợi ích của việc phụ thuộc interface; không bắt buộc phải dùng JMX proxy trong mọi test.

## 12. Khi nào không nên dùng proxy?

Proxy có chi phí cấu hình, lookup và điều kiện runtime. Không nên dùng chỉ để “kiến trúc có thêm tầng” trong các trường hợp:

- Hai Spring bean trong cùng module đang phối hợp logic nghiệp vụ thường ngày.
- Client cần API domain giàu kiểu dữ liệu hoặc transaction boundary phức tạp.
- Không có yêu cầu xuất bản management interface.
- Đường gọi cực kỳ nhạy với độ trễ, tần suất cao và không có lý do đi qua MBeanServer.
- Cần kiểm soát transaction/security ở tầng service mà JMX boundary không được thiết kế để mô phỏng.
- Lời gọi cần context như request identity, tracing hoặc session state không thuộc contract JMX.

Ví dụ:

\`\`\`java
@Service
class OrderProcessor {
    private final PaymentService paymentService;

    OrderProcessor(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
\`\`\`

Đây thường là injection nghiệp vụ thông thường, không nên thay \`PaymentService\` bằng JMX proxy chỉ vì muốn giảm coupling. Muốn tách implementation, có thể inject một **business interface**; không cần vòng qua MBeanServer.

## 13. Chọn management facade thay vì export trực tiếp service

Một service có thể có API rộng:

\`\`\`java
class CacheService {
    void refresh();
    void deleteAllData();
    String getProviderToken();
    void setCriticalFlag(boolean enabled);
}
\`\`\`

Không nên export toàn bộ rồi tạo proxy tới đó.

Thay vào đó:

\`\`\`java
public interface CacheManagement {
    long getEntryCount();
    void refresh();
}
\`\`\`

Facade:

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.management:type=Cache,name=primary"
)
public class CacheManagementFacade {

    private final CacheService cacheService;

    public CacheManagementFacade(CacheService cacheService) {
        this.cacheService = cacheService;
    }

    @ManagedAttribute
    public long getEntryCount() {
        return cacheService.entryCount();
    }

    @ManagedOperation
    public void refresh() {
        cacheService.refresh();
    }
}
\`\`\`

Client proxy chỉ nhìn thấy contract cần thiết. Lợi ích của proxy đến từ **hợp đồng quản trị được chọn lọc**, không phải chỉ từ việc có một object Java tên là proxy.

## 14. ObjectName ổn định quan trọng hơn tên implementation

Giả sử implementation ban đầu tên \`RedisCacheManagementFacade\`, sau đó đổi thành \`CaffeineCacheManagementFacade\`.

Nếu client tìm MBean qua:

\`\`\`text
app.management:type=Cache,name=primary
\`\`\`

nó không cần thay đổi khi class được rename, miễn server tiếp tục đăng ký cùng ObjectName và giữ attribute/operation tương thích.

Ngược lại, nếu ObjectName được suy ra từ class runtime:

\`\`\`text
com.example.cache:type=RedisCacheManagementFacade
\`\`\`

thay class có thể làm client hỏng.

Dùng \`@ManagedResource(objectName = "...")\` hoặc \`ObjectNamingStrategy\` phù hợp để tách tên quản trị khỏi implementation. Cũng không để tên proxy CGLIB/JDK dynamic proxy trở thành hợp đồng quản trị duy nhất.

## 15. Vấn đề vòng đời và thời điểm khởi tạo

Proxy được tạo trong Spring context có thể yêu cầu MBean đích đã sẵn sàng. Nhưng exporter và client proxy có thể cùng khởi tạo trong một context.

\`\`\`text
Context startup
  |
  +-- Tạo business bean
  +-- Tạo exporter
  +-- Register MBean
  +-- Tạo proxy
  +-- Client bắt đầu dùng proxy
\`\`\`

Nếu thứ tự khởi tạo không phù hợp, một proxy có thể cố kết nối tới MBean chưa tồn tại.

Với Spring \`MBeanProxyFactoryBean\`, cần xem xét thiết lập \`connectOnStartup\` của thành phần access phù hợp với phiên bản Spring. Kết nối sớm giúp fail-fast khi MBean thiếu; nếu muốn trì hoãn, cần tổ chức retry/availability logic có giới hạn và hợp đồng startup rõ ràng.

Một cách khác là tách client quản trị thành component chỉ hoạt động sau khi context đã sẵn sàng. Tránh gọi JMX operation từ constructor hoặc \`@PostConstruct\` trước khi exporter hoàn tất lifecycle.

## 16. Sai MBeanServerConnection là lỗi phổ biến

Có thể ứng dụng tạo server riêng:

\`\`\`java
MBeanServer custom = MBeanServerFactory.newMBeanServer(
    "isolated.management"
);
\`\`\`

Exporter đăng ký MBean vào \`custom\`, nhưng proxy dùng:

\`\`\`java
ManagementFactory.getPlatformMBeanServer()
\`\`\`

Khi đó proxy không tìm thấy MBean dù export đã thành công.

Nên cấu hình rõ cùng server:

\`\`\`java
@Bean
public MBeanServer managementServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
\`\`\`

Exporter:

\`\`\`java
@EnableMBeanExport(server = "managementServer")
\`\`\`

Client:

\`\`\`java
@Bean
public MBeanServerConnection managementConnection(
        MBeanServer managementServer
) {
    return managementServer;
}
\`\`\`

Một \`MBeanServer\` là \`MBeanServerConnection\`, vì vậy có thể dùng cùng instance. Không chỉ so tên ObjectName; phải kiểm tra client và exporter có dùng **cùng registry**.

## 17. Exception khi gọi qua proxy

Các trường hợp:

| Lỗi | Tình huống | Hướng xử lý |
|---|---|---|
| \`InstanceNotFoundException\` | ObjectName không được đăng ký | Kiểm tra server, startup và lifecycle |
| \`AttributeNotFoundException\` | Method getter ánh xạ attribute không tồn tại | Đọc \`MBeanInfo\` |
| \`ReflectionException\` | Operation không tồn tại hoặc signature sai | So khớp method/metadata |
| \`MBeanException\` | Operation server-side ném checked exception | Xem exception gốc |
| \`RuntimeMBeanException\` | Implementation ném runtime exception | Xử lý logic/validation |
| \`IOException\` | Remote connector lỗi | Reconnect và giới hạn retry |
| Lỗi Spring JMX access | Exception được proxy/interceptor bọc | Đọc cause và log phù hợp |

Khi dùng Java proxy, một số checked exception JMX có thể được bao bọc trong runtime exception hoặc \`UndeclaredThrowableException\` tùy invocation handler/interface. Vì vậy client nên nhìn nguyên nhân gốc và không mặc định mọi method chỉ ném exception khai báo trên interface.

### Đọc metadata thay vì đoán

\`\`\`java
MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(op.getName());
}

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.println(a.getName());
}
\`\`\`

Các class metadata nằm trong \`javax.management\`. Đối chiếu tên, kiểu và signature với management interface phía client.

## 18. Proxy không tự xử lý unregister/re-register

MBean có thể bị unregister vì Spring context đóng, exporter thay thế registration hoặc ứng dụng khởi động lại.

Proxy phía client vẫn tồn tại dưới dạng object Java và giữ \`ObjectName\`, nhưng lời gọi có thể thất bại khi MBean chưa đăng ký.

\`\`\`text
Proxy tồn tại
    |
    | MBean bị unregister
    v
invoke/getAttribute -> lỗi
    |
    | MBean được register lại cùng ObjectName
    v
Có thể gọi lại nếu contract tương thích
\`\`\`

Không giả định proxy tự khôi phục connection hoặc listener. Trong môi trường local, có thể tổ chức lifecycle rõ ràng giữa exporter và client. Nếu chuyển remote, cần cơ chế kiểm tra trạng thái và reconnect theo chính sách.

## 19. Notification qua proxy

JMX API \`JMX.newMBeanProxy\` có tham số \`notificationBroadcaster\`:

\`\`\`java
CacheMonitorMBean proxy = JMX.newMBeanProxy(
    connection,
    name,
    CacheMonitorMBean.class,
    true
);
\`\`\`

Với tham số \`true\`, proxy có thể hỗ trợ \`NotificationEmitter\` khi MBean server-side có khả năng phát notification.

Một client có thể cast sang \`NotificationEmitter\` và đăng ký listener theo hợp đồng JMX, nhưng phải bảo đảm MBean thực sự công bố và phát notification. Đây là khả năng bổ sung, không bắt buộc cho proxy chỉ đọc attributes/gọi operations.

Trong Spring \`MBeanProxyFactoryBean\`, listener có thể được quản lý bằng API JMX trực tiếp hoặc cấu hình phù hợp; không giả định mọi proxy Spring đều tự động expose notification emitter theo cùng cách.

## 20. Local proxy và chuyển sang remote

Mô hình local:

\`\`\`java
MBeanServerConnection connection =
    ManagementFactory.getPlatformMBeanServer();
\`\`\`

Mô hình remote:

\`\`\`java
JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi"
);

JMXConnector connector =
    JMXConnectorFactory.connect(url);

MBeanServerConnection connection =
    connector.getMBeanServerConnection();
\`\`\`

Phần client proxy có thể tiếp tục sử dụng management interface và ObjectName. Tuy nhiên remote yêu cầu thêm:

- JMX connector server đã được bật đúng.
- Authentication, authorization và TLS khi cần.
- Mạng và RMI endpoint hoạt động.
- Kiểu tham số/trả về serializable hoặc tương thích JMX.
- Xử lý timeout, mất kết nối và lifecycle connector.
- Hạn chế gọi operation có tác dụng phụ khi retry không rõ kết quả trước đó.

\`@EnableMBeanExport\` chỉ export MBean, không tự bật cổng JMX remote. Một client local dùng proxy không tự chứng minh hệ thống đã có remote access an toàn.

## 21. Chi phí và hiệu năng

Mỗi proxy call đi qua tầng JMX invocation, metadata và các lớp adapter phù hợp. So với method call trực tiếp, nó có overhead nhất định, ngay cả trong cùng JVM.

Do đó:

- Không dùng JMX proxy trong đường xử lý nóng với hàng nghìn lời gọi mỗi request.
- Không dùng JMX làm API business có throughput cao.
- Ưu tiên thao tác quản trị có tần suất thấp, có mục tiêu.
- Đừng trả một object graph lớn chỉ để hiển thị vài chỉ số.
- Cân nhắc metrics API chuyên biệt nếu chỉ cần thu thập số liệu tần suất cao.

Proxy giúp giảm coupling ở **management boundary**, không phải tối ưu mọi loại lời gọi.

## 22. Bài tập thực hành

**Bối cảnh:** module \`admin-ui\` và module \`inventory-core\` cùng chạy trong một JVM. \`inventory-core\` có class \`InventoryServiceImpl\`. Admin UI chỉ cần đọc số lượng tồn kho tổng hợp và yêu cầu làm mới số liệu.

**Thiết kế gợi ý:**

Management interface:

\`\`\`java
public interface InventoryManagement {
    long getTotalItems();
    void refreshSnapshot();
}
\`\`\`

Facade phía server:

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.management:type=Inventory,name=main"
)
public class InventoryManagementFacade {

    private final InventoryService service;

    public InventoryManagementFacade(InventoryService service) {
        this.service = service;
    }

    @ManagedAttribute
    public long getTotalItems() {
        return service.totalItems();
    }

    @ManagedOperation
    public void refreshSnapshot() {
        service.refreshSnapshot();
    }
}
\`\`\`

Client phía admin dùng \`MBeanProxyFactoryBean\` với interface \`InventoryManagement\` và ObjectName \`app.management:type=Inventory,name=main\`.

**Câu hỏi:** Khi \`InventoryServiceImpl\` được thay bằng implementation khác, client có phải đổi code không?

Nếu management interface, ObjectName và các kiểu dữ liệu vẫn tương thích, client không cần biết implementation mới.

**Câu hỏi:** Khi nào admin UI không cần JMX proxy?

Nếu hai module chỉ cần một business interface và không có yêu cầu đi qua management boundary, injection trực tiếp interface business có thể đơn giản và phù hợp hơn.

## 23. Câu hỏi tự kiểm tra

1. JMX proxy giúp client tách khỏi implementation ở mức nào?
2. Vì sao proxy vẫn cần ObjectName và đúng MBeanServerConnection?
3. \`JMX.newMBeanProxy\` khác \`MBeanProxyFactoryBean\` ở trách nhiệm cấu hình nào?
4. Tại sao \`getEntryCount()\` thường ánh xạ thành attribute access?
5. Khi nào việc injection service interface trực tiếp tốt hơn proxy MBean?
6. Vì sao nên export management facade thay vì toàn bộ service?
7. MBean bị unregister thì proxy Java đã tạo có tự biến mất không?
8. Chuyển từ local sang remote cần cân nhắc thêm những yếu tố nào?
9. Một interface proxy khai báo method không được MBean export sẽ có kết quả gì?
10. Làm thế nào để kiểm tra hợp đồng MBean sau refactor?

## 24. Ghi nhớ

\`\`\`text
Client phụ thuộc:
  management interface
  + ObjectName
  + MBeanServerConnection

Proxy:
  Java method -> JMX attribute/operation

Server phụ thuộc:
  Spring bean / management facade
  + MBeanExporter
  + MBeanServer registry
\`\`\`

**Kết luận:** chọn MBean proxy local khi mục tiêu là **tách client quản trị khỏi class implementation**, dùng chung hợp đồng JMX rõ ràng và có thể thay đổi implementation phía sau. Không dùng proxy chỉ để thay mọi lời gọi bean nội bộ. Lợi ích thực sự đến từ management interface nhỏ, ObjectName ổn định, registry đúng và lifecycle được quản lý có chủ đích.